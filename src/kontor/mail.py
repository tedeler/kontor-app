"""Postfächer, OAuth2-Anmeldung, Tokens und Mail-Abruf (mail.md, Meilenstein 6).

- Postfächer sind Buchbestand (protokolliert über ``app.aendern``); ihr Betriebszustand (``postfach_zustand``),
  ihre Tokens (Geheimnis ``mail_token:<adresse>``) und ihr Spiegel (``mail_nachricht``) hängen an der Adresse
  (``casefold``) und entfallen mit dem Postfach (``geheimnisse.verwaiste_entfernen``).
- Offene Anmeldungen (``state``, ``code_verifier``) leben nur im Arbeitsspeicher dieses Dienstes.
- Codes, Tokens, ``state`` und ``code_verifier`` erscheinen nie in Antworten, Logs oder Fehlermeldungen.
"""

from __future__ import annotations

import base64
import concurrent.futures
import datetime as dt
import hashlib
import http.client
import json
import logging
import secrets
import threading
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from . import buch, db
from .config import KontorConfig
from .fehler import (KontorFehler, MailAnmeldungFehlt, MailOAuthFehler, MailTokenAbgelaufen, MailTokenWiderrufen)
from .geheimnisse import Geheimnisspeicher, mail_name, passwort_name
from .netz import http_anfrage
from .validierung import ApiFehler, Feld, Validierungsfehler, fehler_eintrag, pruefe_objekt

log = logging.getLogger("kontor.mail")
UTC = dt.timezone.utc
SCOPE = "https://mail.google.com/"
_VERIFIER_ZEICHEN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
ANMELDUNG_GUELTIG = dt.timedelta(minutes=10)

S = Feld
FILTER = S("str_liste", min_len=1, max_len=200, max_items=50)
POSTFACH_NEU = {"adresse": S("str", pflicht=True), "bezeichnung": S("str", max_len=200),
                "ordner": S("str", min_len=1, max_len=200), "absender_filter": FILTER, "aktiv": S("bool")}
POSTFACH_AENDERUNG = {k: v for k, v in POSTFACH_NEU.items() if k != "adresse"}
ABSCHLUSS = {"antwort_url": S("str", pflicht=True, min_len=1, max_len=8192)}


def zeit_text(z: dt.datetime) -> str:
    return z.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def zeit_lesen(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def adresse_gueltig(a: str) -> bool:
    return (isinstance(a, str) and 3 <= len(a) <= 254 and a.count("@") == 1 and not any(c.isspace() for c in a)
            and all(a.split("@")))


# ================================================================ Postfächer (Buchbestand)


def postfach_dict(r) -> dict:
    return {"id": r["id"], "adresse": r["adresse"], "bezeichnung": r["bezeichnung"], "ordner": r["ordner"],
            "absender_filter": json.loads(r["absender_filter"]), "aktiv": bool(r["aktiv"])}


def formen(con, ids: list[int]) -> dict[int, dict]:
    aus = {}
    for teil in buch._stueckweise(sorted(set(ids))):
        for r in con.execute(f"SELECT * FROM postfach WHERE id IN ({buch._platzhalter(len(teil))})", teil):
            aus[r["id"]] = postfach_dict(r)
    return aus


def einfuegen(con, f: dict) -> None:
    """Protokollform → Zeile (Rückgängig, Sicherung)."""
    con.execute("INSERT INTO postfach (id, adresse, adresse_cf, bezeichnung, ordner, absender_filter, aktiv)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f["id"], f["adresse"], f["adresse"].casefold(), f["bezeichnung"], f["ordner"],
                 json.dumps(f["absender_filter"], ensure_ascii=False), 1 if f["aktiv"] else 0))


def _filter_pruefen(d: dict) -> None:
    f = d.get("absender_filter")
    if f is not None and len(set(f)) != len(f):
        raise Validierungsfehler([fehler_eintrag(["body", "absender_filter"], "Einträge müssen eindeutig sein.")])


def postfach_koerper(roh: bytes, neu: bool) -> dict:
    from .validierung import json_koerper
    daten = json_koerper(roh)
    fehler: list[dict] = []
    d = pruefe_objekt(daten, POSTFACH_NEU if neu else POSTFACH_AENDERUNG, ["body"], fehler)
    if neu and "adresse" in d and isinstance(d["adresse"], str) and not adresse_gueltig(d["adresse"]):
        fehler.append(fehler_eintrag(["body", "adresse"], "Ungültige E-Mail-Adresse."))
    if fehler:
        raise Validierungsfehler(fehler)
    _filter_pruefen(d)
    return d


def postfach_lesen(con, pid: int) -> dict:
    r = con.execute("SELECT * FROM postfach WHERE id = ?", (buch.sichere_id(pid),)).fetchone()
    if r is None:
        raise buch.nicht_gefunden("Das Postfach")
    return postfach_dict(r)


def postfaecher_liste(con) -> list[dict]:
    return [postfach_dict(r) for r in con.execute("SELECT * FROM postfach ORDER BY id")]


def postfach_anlegen(con, d: dict) -> dict:
    a = d["adresse"]
    if con.execute("SELECT 1 FROM postfach WHERE adresse_cf = ?", (a.casefold(),)).fetchone():
        raise ApiFehler(409, "postfach_existiert", "Ein Postfach mit dieser Adresse existiert bereits.")
    pid = con.execute("INSERT INTO postfach (adresse, adresse_cf, bezeichnung, ordner, absender_filter, aktiv)"
                      " VALUES (?, ?, ?, ?, ?, ?)",
                      (a, a.casefold(), d.get("bezeichnung", ""), d.get("ordner", "INBOX"),
                       json.dumps(d.get("absender_filter", []), ensure_ascii=False),
                       1 if d.get("aktiv", True) else 0)).lastrowid
    return postfach_lesen(con, pid)


def postfach_aendern(con, pid: int, d: dict) -> dict:
    alt = postfach_lesen(con, pid)
    neu = {**alt, **d}
    if neu != alt:
        con.execute("UPDATE postfach SET bezeichnung = ?, ordner = ?, absender_filter = ?, aktiv = ? WHERE id = ?",
                    (neu["bezeichnung"], neu["ordner"], json.dumps(neu["absender_filter"], ensure_ascii=False),
                     1 if neu["aktiv"] else 0, pid))
    return postfach_lesen(con, pid)


def postfach_loeschen(con, pid: int) -> None:
    postfach_lesen(con, pid)
    con.execute("DELETE FROM postfach WHERE id = ?", (pid,))
    # Anmeldung (ohne Widerruf), Spiegel und Betriebszustand entfallen in derselben Transaktion
    # (protokoll.protokolliert ruft geheimnisse.verwaiste_entfernen auf).


def pruefe_inhalt(zeilen: list[tuple]) -> bool:
    """sicherung.md 2.6: Postfachzeilen (id, adresse, bezeichnung, ordner, absender_filter, aktiv) gültig."""
    gesehen = set()
    for _id, adresse, bezeichnung, ordner, filt, _aktiv in zeilen:
        if not adresse_gueltig(adresse) or adresse.casefold() in gesehen:
            return False
        gesehen.add(adresse.casefold())
        if not isinstance(bezeichnung, str) or len(bezeichnung) > 200:
            return False
        if not isinstance(ordner, str) or not 1 <= len(ordner) <= 200:
            return False
        try:
            f = json.loads(filt)
        except (TypeError, ValueError):
            return False
        if (not isinstance(f, list) or len(f) > 50 or len(set(map(str, f))) != len(f)
                or any(not isinstance(x, str) or not 1 <= len(x) <= 200 for x in f)):
            return False
    return True


# ================================================================ Dienst (Betriebszustand, OAuth, Abruf)


@dataclass
class _Anmeldung:
    adresse_cf: str
    postfach_id: int
    code_verifier: str
    gueltig_bis: dt.datetime

    def __repr__(self) -> str:
        return f"_Anmeldung(postfach_id={self.postfach_id})"


class MailDienst:
    def __init__(self, config: KontorConfig, jetzt: Callable[[], dt.datetime], geheimnisse: Geheimnisspeicher) -> None:
        self.config = config
        self.pfad = config.aktive_datenbank
        self._jetzt = jetzt
        self._geheim = geheimnisse
        self._offen: dict[str, _Anmeldung] = {}
        self._zustand = threading.Lock()
        self._abruf = threading.Lock()
        self._token_sperre = threading.Lock()
        self._mock_plugin = None

    def __repr__(self) -> str:
        return "MailDienst()"

    def _con(self):
        return db.verbinde(self.pfad)

    def jetzt_text(self) -> str:
        return zeit_text(self._jetzt())

    # ------------------------------------------------------------ Betriebszustand
    def _zustand_zeile(self, con, adresse_cf: str):
        return con.execute("SELECT * FROM postfach_zustand WHERE adresse_cf = ?", (adresse_cf,)).fetchone()

    @staticmethod
    def _zustand_sichern(con, adresse_cf: str) -> None:
        con.execute("INSERT OR IGNORE INTO postfach_zustand (adresse_cf) VALUES (?)", (adresse_cf,))

    def status_dict(self, con, p: dict) -> dict:
        cf = p["adresse"].casefold()
        z = self._zustand_zeile(con, cf)
        anzahl = con.execute("SELECT COUNT(*) FROM mail_nachricht WHERE adresse_cf = ?", (cf,)).fetchone()[0]
        anmeldung = "nicht_erforderlich" if self.config.mock_modus else (z["anmeldung"] if z else "fehlt")
        return {
            "postfach_id": p["id"], "anmeldung": anmeldung, "anmeldung_nr": z["anmeldung_nr"] if z else 0,
            "angemeldet_am": z["angemeldet_am"] if z else None,
            "laeuft_ab_am": z["laeuft_ab_am"] if z and anmeldung == "angemeldet" else None,
            "letzter_abruf_am": z["letzter_abruf_am"] if z else None,
            "letzter_erfolg_am": z["letzter_erfolg_am"] if z else None,
            "letzter_fehler": ({"code": z["fehler_code"], "meldung": z["fehler_meldung"]}
                               if z and z["fehler_code"] else None),
            "nachrichten": anzahl,
        }

    def status(self, con, pid: int) -> dict:
        return self.status_dict(con, postfach_lesen(con, pid))

    # ------------------------------------------------------------ OAuth: Anmeldung (mail.md 4)
    def _nur_echt(self) -> None:
        if self.config.mock_modus:
            raise ApiFehler(409, "nur_echtmodus", "Im Mock-Modus ist keine Anmeldung nötig (und keine möglich).")

    def _client_secret(self, con) -> str | None:
        return self._geheim.lesen(con, "oauth_client_secret")

    def anmeldung_starten(self, pid: int) -> dict:
        con = self._con()
        try:
            p = postfach_lesen(con, pid)
            self._nur_echt()
            if not self.config.oauth_client_id or not self._client_secret(con):
                raise ApiFehler(409, "oauth_client_fehlt", "Für die Anmeldung fehlen OAuth-Client-ID oder "
                                "Client-Secret des eigenen Google-Cloud-Projekts.")
        finally:
            con.close()
        state = secrets.token_urlsafe(32)
        verifier = "".join(secrets.choice(_VERIFIER_ZEICHEN) for _ in range(64))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
        bis = self._jetzt() + ANMELDUNG_GUELTIG
        cf = p["adresse"].casefold()
        with self._zustand:
            for k in [k for k, v in self._offen.items() if v.adresse_cf == cf or v.gueltig_bis < self._jetzt()]:
                del self._offen[k]  # eine frühere offene Anmeldung desselben Postfachs verfällt
            self._offen[state] = _Anmeldung(cf, p["id"], verifier, bis)
        c = self.config
        parameter = {"response_type": "code", "client_id": c.oauth_client_id, "redirect_uri": c.oauth_redirect_uri,
                     "scope": SCOPE, "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
                     "access_type": "offline", "prompt": "consent", "login_hint": p["adresse"]}
        trenner = "&" if "?" in c.oauth_autorisierung_url else "?"
        return {"autorisierung_url": c.oauth_autorisierung_url + trenner + urllib.parse.urlencode(parameter),
                "gueltig_bis": zeit_text(bis)}

    def anmeldung_abschliessen(self, parameter: dict[str, str]) -> dict:
        """mail.md 4.3 mit den Abfrageparametern der Umleitungs-URL."""
        self._nur_echt()
        state = parameter.get("state") or ""
        with self._zustand:
            offen = self._offen.pop(state, None) if state else None  # jeder state gilt höchstens einmal
        if offen is None or offen.gueltig_bis < self._jetzt():
            raise ApiFehler(422, "oauth_zustand_ungueltig", "Die Anmeldung ist unbekannt, abgelaufen oder schon "
                            "abgeschlossen. Bitte neu starten.")
        if parameter.get("error"):
            raise ApiFehler(422, "oauth_abgelehnt", "Die Anmeldung wurde beim Anbieter abgelehnt.")
        code = parameter.get("code")
        if not code:
            raise ApiFehler(422, "oauth_zustand_ungueltig", "Die Umleitungs-URL enthält keinen Autorisierungscode.")
        con = self._con()
        try:
            r = con.execute("SELECT * FROM postfach WHERE id = ? AND adresse_cf = ?",
                            (offen.postfach_id, offen.adresse_cf)).fetchone()
            if r is None:
                raise ApiFehler(422, "oauth_zustand_ungueltig", "Das Postfach dieser Anmeldung gibt es nicht mehr.")
            secret = self._client_secret(con)
            if not self.config.oauth_client_id or not secret:
                raise ApiFehler(409, "oauth_client_fehlt", "OAuth-Client-ID oder Client-Secret fehlen.")
            c = self.config
            status, antwort = self._token_anfrage({"grant_type": "authorization_code", "code": code,
                                                    "redirect_uri": c.oauth_redirect_uri, "client_id": c.oauth_client_id,
                                                    "client_secret": secret, "code_verifier": offen.code_verifier})
            del secret, code
            if status is None:
                raise ApiFehler(409, "oauth_fehler", "Der OAuth-Anbieter ist nicht erreichbar.", {"error": None})
            if status != 200 or not isinstance(antwort, dict):
                fehler = antwort.get("error") if isinstance(antwort, dict) and isinstance(antwort.get("error"), str) \
                    else None
                raise ApiFehler(409, "oauth_fehler", "Der OAuth-Anbieter hat den Tokentausch abgelehnt.",
                                {"error": fehler})
            scope = antwort.get("scope")
            if not isinstance(scope, str) or SCOPE not in scope.split():
                raise ApiFehler(422, "oauth_scope_fehlt", "Die Zustimmung umfasst nicht den Zugriff auf Gmail "
                                "(Scope https://mail.google.com/).")
            refresh = antwort.get("refresh_token")
            if not isinstance(refresh, str) or not refresh:
                raise ApiFehler(422, "oauth_kein_refresh_token", "Der Anbieter hat keinen Refresh-Token geliefert.")
            access = antwort.get("access_token") if isinstance(antwort.get("access_token"), str) else None
            jetzt = self._jetzt()
            tokens = {"refresh_token": refresh, "access_token": access,
                      "access_ablauf": zeit_text(jetzt + dt.timedelta(seconds=_sekunden(antwort.get("expires_in")))),
                      "ausgestellt": zeit_text(jetzt)}
            ablauf = self._refresh_ablauf(jetzt, antwort)
            with db.transaktion(con):
                self._geheim.setzen(con, mail_name(r["adresse"]), json.dumps(tokens))
                self._zustand_sichern(con, offen.adresse_cf)
                con.execute("UPDATE postfach_zustand SET anmeldung = 'angemeldet', anmeldung_nr = anmeldung_nr + 1,"
                            " angemeldet_am = ?, laeuft_ab_am = ? WHERE adresse_cf = ?",
                            (zeit_text(jetzt), ablauf, offen.adresse_cf))
                for art in ("mail_token_laeuft_ab", "mail_token_abgelaufen", "mail_token_widerrufen", "mail_fehler"):
                    praefix = f"{art}:{r['id']}:"
                    con.execute("UPDATE benachrichtigung SET gelesen = 1 WHERE gelesen = 0 AND substr(schluessel, 1, ?)"
                                " = ?", (len(praefix), praefix))
            return self.status_dict(con, postfach_dict(r))
        finally:
            con.close()

    def _refresh_ablauf(self, ausgestellt: dt.datetime, antwort: dict) -> str | None:
        """mail.md 5.2."""
        sek = antwort.get("refresh_token_expires_in")
        if type(sek) is int and sek >= 0:
            return zeit_text(ausgestellt + dt.timedelta(seconds=sek))
        stunden = self.config.oauth_refresh_gueltig_stunden
        if stunden == 0:
            return None
        return zeit_text(ausgestellt + dt.timedelta(hours=stunden))

    def _token_anfrage(self, formular: dict[str, str]) -> tuple[int | None, object]:
        """POST an oauth_token_url; (Status, JSON) oder (None, None) bei Verbindungsfehler/Zeitüberschreitung."""
        c = self.config
        try:
            a = http_anfrage(c, "POST", c.oauth_token_url, urllib.parse.urlencode(formular).encode("ascii"),
                             {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                             c.oauth_timeout_sekunden)
        except (OSError, http.client.HTTPException):
            return None, None
        try:
            daten = json.loads(a.koerper.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            daten = None
        return a.status, daten

    def abmelden(self, pid: int) -> None:
        con = self._con()
        try:
            p = postfach_lesen(con, pid)
            self._nur_echt()
            if con.execute("SELECT 1 FROM geheimnis WHERE name = ?", (passwort_name(p["adresse"]),)).fetchone():
                self.app_passwort_loeschen(pid)  # D-130: Abmelden entfernt auch das App-Passwort
                return
            name = mail_name(p["adresse"])
            roh = self._geheim.lesen(con, name)
            if roh is not None:
                try:
                    refresh = json.loads(roh).get("refresh_token")
                except ValueError:
                    refresh = None
                if refresh:
                    c = self.config
                    try:
                        http_anfrage(c, "POST", c.oauth_widerruf_url,
                                     urllib.parse.urlencode({"token": refresh}).encode("ascii"),
                                     {"Content-Type": "application/x-www-form-urlencoded"}, c.oauth_timeout_sekunden)
                    except (OSError, http.client.HTTPException):
                        pass  # Fehler beim Widerruf werden ignoriert (mail.md 4.4)
            cf = p["adresse"].casefold()
            with db.transaktion(con):
                self._geheim.loeschen(con, name)
                self._zustand_sichern(con, cf)
                con.execute("UPDATE postfach_zustand SET anmeldung = 'fehlt', laeuft_ab_am = NULL WHERE adresse_cf = ?",
                            (cf,))
        finally:
            con.close()

    # ------------------------------------------------------------ Tokens im Betrieb (mail.md 5)
    def _melden(self, con, art: str, pid: int, nr: int, entprellung: str = "einmal") -> None:
        texte = {
            "mail_token_laeuft_ab": ("Mail-Anmeldung läuft bald ab",
                                     "Die Anmeldung eines Postfachs läuft bald ab (Testmodus des Google-Projekts). "
                                     "Bitte das Postfach in den Einstellungen erneut anmelden."),
            "mail_token_abgelaufen": ("Mail-Anmeldung abgelaufen",
                                      "Die Anmeldung eines Postfachs ist abgelaufen; Mails werden nicht mehr "
                                      "abgerufen. Bitte das Postfach erneut anmelden."),
            "mail_token_widerrufen": ("Mail-Anmeldung widerrufen",
                                      "Der Zugriff auf ein Postfach wurde beim Anbieter widerrufen; Mails werden "
                                      "nicht mehr abgerufen. Bitte das Postfach erneut anmelden."),
        }
        titel, text = texte[art]
        buch.benachrichtigung_anlegen(con, art, f"{art}:{pid}:{nr}", titel, text, f"/mail/postfaecher/{pid}",
                                      self.jetzt_text(), entprellung)

    def _ende(self, con, r, art: str) -> None:
        """Tokens löschen, Status setzen, einmal je Anmeldung melden (abgelaufen/widerrufen)."""
        cf = r["adresse_cf"]
        z = self._zustand_zeile(con, cf)
        nr = z["anmeldung_nr"] if z else 0
        with db.transaktion(con):
            self._geheim.loeschen(con, mail_name(r["adresse"]))
            self._zustand_sichern(con, cf)
            con.execute("UPDATE postfach_zustand SET anmeldung = ?, laeuft_ab_am = NULL WHERE adresse_cf = ?",
                        ("abgelaufen" if art == "mail_token_abgelaufen" else "widerrufen", cf))
            self._melden(con, art, r["id"], nr)

    def anmeldungen_pruefen(self, nur_adresse: str | None = None) -> None:
        """mail.md 5.3: Ablauf (proaktiv) und Vorwarnung für jedes angemeldete Postfach mit bekanntem Ablauf."""
        if self.config.mock_modus:
            return
        jetzt = self._jetzt()
        con = self._con()
        try:
            zeilen = con.execute("SELECT p.id, p.adresse, p.adresse_cf, z.anmeldung_nr, z.laeuft_ab_am FROM postfach p"
                                 " JOIN postfach_zustand z ON z.adresse_cf = p.adresse_cf"
                                 " WHERE z.anmeldung = 'angemeldet' AND z.laeuft_ab_am IS NOT NULL").fetchall()
            for r in zeilen:
                if nur_adresse is not None and r["adresse_cf"] != nur_adresse:
                    continue
                ablauf = zeit_lesen(r["laeuft_ab_am"])
                if jetzt >= ablauf:
                    self._ende(con, r, "mail_token_abgelaufen")
                elif jetzt >= ablauf - dt.timedelta(hours=self.config.oauth_vorwarnung_stunden):
                    with db.transaktion(con):
                        self._melden(con, "mail_token_laeuft_ab", r["id"], r["anmeldung_nr"])
        finally:
            con.close()

    def zugang(self, adresse: str, erneuern: bool) -> str:
        """mail.md 5.1: Access-Token für das IMAP-Plugin."""
        cf = adresse.casefold()
        with self._token_sperre:
            con = self._con()
            try:
                z = self._zustand_zeile(con, cf)
                stand = z["anmeldung"] if z else "fehlt"
                if stand == "abgelaufen":
                    raise MailTokenAbgelaufen("Die Anmeldung des Postfachs ist abgelaufen.")
                if stand == "widerrufen":
                    raise MailTokenWiderrufen("Der Zugriff auf das Postfach wurde widerrufen.")
                if stand != "angemeldet":
                    raise MailAnmeldungFehlt("Das Postfach ist nicht angemeldet.")
            finally:
                con.close()
            self.anmeldungen_pruefen(cf)
            con = self._con()
            try:
                r = con.execute("SELECT p.id, p.adresse, p.adresse_cf, z.anmeldung, z.laeuft_ab_am FROM postfach p"
                                " JOIN postfach_zustand z ON z.adresse_cf = p.adresse_cf WHERE p.adresse_cf = ?",
                                (cf,)).fetchone()
                if r is None:
                    raise MailAnmeldungFehlt("Das Postfach ist nicht angemeldet.")
                if r["anmeldung"] == "abgelaufen":
                    raise MailTokenAbgelaufen("Die Anmeldung des Postfachs ist abgelaufen.")
                name = mail_name(r["adresse"])
                roh = self._geheim.lesen(con, name)
                if roh is None:
                    raise MailAnmeldungFehlt("Die Anmeldedaten des Postfachs sind nicht lesbar; bitte neu anmelden.")
                tokens = json.loads(roh)
                jetzt = self._jetzt()
                if (not erneuern and tokens.get("access_token") and tokens.get("access_ablauf")
                        and jetzt < zeit_lesen(tokens["access_ablauf"]) - dt.timedelta(seconds=60)):
                    return tokens["access_token"]
                return self._erneuern(con, r, tokens)
            finally:
                con.close()

    def _erneuern(self, con, r, tokens: dict) -> str:
        c = self.config
        secret = self._client_secret(con)
        if not secret or not c.oauth_client_id:
            raise MailOAuthFehler("Das OAuth-Client-Secret fehlt oder ist nicht lesbar.")
        status, antwort = self._token_anfrage({"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                                                "client_id": c.oauth_client_id, "client_secret": secret})
        del secret
        if status == 200 and isinstance(antwort, dict) and isinstance(antwort.get("access_token"), str):
            jetzt = self._jetzt()
            tokens["access_token"] = antwort["access_token"]
            tokens["access_ablauf"] = zeit_text(jetzt + dt.timedelta(seconds=_sekunden(antwort.get("expires_in"))))
            ablauf_neu = None
            if isinstance(antwort.get("refresh_token"), str) and antwort["refresh_token"]:
                tokens["refresh_token"] = antwort["refresh_token"]
                tokens["ausgestellt"] = zeit_text(jetzt)
                ablauf_neu = self._refresh_ablauf(jetzt, antwort)
            with db.transaktion(con):
                self._geheim.setzen(con, mail_name(r["adresse"]), json.dumps(tokens))
                if ablauf_neu is not None or (isinstance(antwort.get("refresh_token"), str)
                                              and antwort["refresh_token"]):
                    con.execute("UPDATE postfach_zustand SET laeuft_ab_am = ? WHERE adresse_cf = ?",
                                (ablauf_neu, r["adresse_cf"]))
            return tokens["access_token"]
        if isinstance(antwort, dict) and antwort.get("error") == "invalid_grant":
            ablauf = r["laeuft_ab_am"]
            if ablauf is not None and self._jetzt() >= zeit_lesen(ablauf) - dt.timedelta(hours=1):
                self._ende(con, r, "mail_token_abgelaufen")
                raise MailTokenAbgelaufen("Die Anmeldung des Postfachs ist abgelaufen.")
            self._ende(con, r, "mail_token_widerrufen")
            raise MailTokenWiderrufen("Der Zugriff auf das Postfach wurde widerrufen.")
        raise MailOAuthFehler("Das Access-Token konnte nicht erneuert werden.")

    # ------------------------------------------------------------ Abruf (mail.md 6)
    def _plugin(self, postfaecher: list[dict]):
        from .plugins import erzeuge_mail_plugin
        from .plugins.imap import ImapPasswortPostfach, ImapPostfach
        if self.config.mock_modus:
            if self._mock_plugin is None:
                self._mock_plugin = erzeuge_mail_plugin(self.config)
            if hasattr(self._mock_plugin, "setze_heute"):
                self._mock_plugin.setze_heute(self._jetzt().date())
            return self._mock_plugin
        con = self._con()
        try:
            mit_pw = {r[0] for r in con.execute("SELECT name FROM geheimnis WHERE name LIKE 'mail_passwort:%'")}
        finally:
            con.close()
        return erzeuge_mail_plugin(self.config, postfaecher=[
            ImapPasswortPostfach(p["adresse"], p["ordner"], passwort=lambda a=p["adresse"]: self._app_passwort(a))
            if passwort_name(p["adresse"]) in mit_pw else ImapPostfach(p["adresse"], p["ordner"])
            for p in postfaecher], zugang=self.zugang)

    # ------------------------------------------------------------ D-130: App-Passwort statt OAuth2
    def _app_passwort(self, adresse: str) -> str | None:
        con = self._con()
        try:
            return self._geheim.lesen(con, passwort_name(adresse))
        finally:
            con.close()

    def app_passwort_setzen(self, pid: int, passwort: str) -> dict:
        """Prüft Anmeldung und Ordner mit dem App-Passwort und speichert es erst danach (geschützt, wenn der Schutz
        der Geheimnisse eingeschaltet ist). Das Postfach gilt dann ohne Ablauf als angemeldet."""
        from .plugins import erzeuge_mail_plugin
        from .plugins.imap import ImapPasswortPostfach
        self._nur_echt()
        passwort = "".join(passwort.split())  # Google zeigt das App-Passwort in Vierergruppen mit Leerzeichen
        if not passwort:
            raise ApiFehler(422, "validierung", "Bitte das App-Passwort eingeben.")
        con = self._con()
        try:
            p = postfach_lesen(con, pid)
            if self._geheim.gesperrt(con):
                raise ApiFehler(409, "geheimnisse_gesperrt", "Die Geheimnisse sind gesperrt; bitte zuerst entsperren.")
        finally:
            con.close()
        plugin = erzeuge_mail_plugin(self.config, postfaecher=[
            ImapPasswortPostfach(p["adresse"], p["ordner"], passwort=lambda: passwort)], zugang=None)
        try:
            anzahl = plugin._pruefen(p["adresse"])
        except KontorFehler as e:
            code, meldung = _fehler_von(e)
            raise ApiFehler(422, code, meldung) from None
        cf = p["adresse"].casefold()
        con = self._con()
        try:
            with db.transaktion(con):
                self._geheim.setzen(con, passwort_name(p["adresse"]), passwort)
                self._geheim.loeschen(con, mail_name(p["adresse"]))  # kein OAuth2-Token daneben
                self._zustand_sichern(con, cf)
                con.execute("UPDATE postfach_zustand SET anmeldung = 'angemeldet', anmeldung_nr = anmeldung_nr + 1,"
                            " angemeldet_am = ?, laeuft_ab_am = NULL, fehler_code = NULL, fehler_meldung = NULL"
                            " WHERE adresse_cf = ?", (self.jetzt_text(), cf))
        finally:
            con.close()
        return {"postfach_id": p["id"], "ordner": p["ordner"], "nachrichten_im_ordner": anzahl}

    def app_passwort_loeschen(self, pid: int) -> None:
        con = self._con()
        try:
            p = postfach_lesen(con, pid)
            cf = p["adresse"].casefold()
            with db.transaktion(con):
                if con.execute("SELECT 1 FROM geheimnis WHERE name = ?", (passwort_name(p["adresse"]),)).fetchone():
                    self._geheim.loeschen(con, passwort_name(p["adresse"]))
                    con.execute("UPDATE postfach_zustand SET anmeldung = 'fehlt', laeuft_ab_am = NULL"
                                " WHERE adresse_cf = ?", (cf,))
        finally:
            con.close()

    def abruf(self) -> dict:
        if not self._abruf.acquire(blocking=False):
            raise ApiFehler(409, "mail_abruf_laeuft", "Es läuft bereits ein Mail-Abruf.")
        try:
            beginn = self._jetzt()
            con = self._con()
            try:
                if self._geheim.gesperrt(con):  # D-129: ohne Datenschlüssel keine Zugangsdaten
                    raise ApiFehler(409, "geheimnisse_gesperrt", "Die Geheimnisse sind gesperrt; bitte mit dem "
                                    "Login-Passwort entsperren, dann ist der Abruf wieder möglich.")
                aktive = [postfach_dict(r) for r in con.execute("SELECT * FROM postfach WHERE aktiv = 1 ORDER BY id")]
            finally:
                con.close()
            ergebnisse: list[dict] = []
            if aktive:
                plugin = self._plugin(aktive)
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(aktive),
                                                           thread_name_prefix="kontor-mail") as pool:
                    ergebnisse = list(pool.map(lambda p: self._postfach_abrufen(plugin, p, beginn), aktive))
            return {"gestartet_am": zeit_text(beginn), "beendet_am": self.jetzt_text(), "postfaecher": ergebnisse}
        finally:
            self._abruf.release()

    def _seit(self, z, beginn: dt.datetime) -> dt.datetime:
        if z is not None and z["letzter_erfolg_am"]:
            return zeit_lesen(z["letzter_erfolg_am"]) - dt.timedelta(hours=self.config.mail_ueberlappung_stunden)
        return beginn - dt.timedelta(days=self.config.mail_erstabruf_tage)

    def _postfach_abrufen(self, plugin, p: dict, beginn: dt.datetime) -> dict:
        cf = p["adresse"].casefold()
        self.anmeldungen_pruefen(cf)
        con = self._con()
        try:
            z = self._zustand_zeile(con, cf)
            seit = self._seit(z, beginn)
            aus = {"postfach_id": p["id"], "adresse": p["adresse"], "status": "erfolgreich", "seit": zeit_text(seit),
                   "nachrichten_gesamt": 0, "nachrichten_neu": 0, "nachrichten_vorhanden": 0,
                   "nachrichten_gefiltert": 0, "fehler": None}
            if not self.config.mock_modus and (z["anmeldung"] if z else "fehlt") != "angemeldet":
                aus["status"] = "anmeldung_erforderlich"
                return aus
            with db.transaktion(con):
                self._zustand_sichern(con, cf)
                con.execute("UPDATE postfach_zustand SET letzter_abruf_am = ? WHERE adresse_cf = ?",
                            (zeit_text(beginn), cf))
            try:
                liste = plugin.nachrichten(p["adresse"], seit)
            except Exception as e:  # noqa: BLE001 - ein Pluginfehler führt nie zu 5xx
                code, meldung = _fehler_von(e)
                with db.transaktion(con):
                    con.execute("UPDATE postfach_zustand SET fehler_code = ?, fehler_meldung = ? WHERE adresse_cf = ?",
                                (code, meldung, cf))
                    if isinstance(e, (MailTokenAbgelaufen, MailTokenWiderrufen)) and not self.config.mock_modus:
                        pass  # Status und Benachrichtigung schon in zugang (mail.md 6.3)
                    elif isinstance(e, MailTokenAbgelaufen):
                        self._melden(con, "mail_token_abgelaufen", p["id"], 0)
                    else:
                        buch.benachrichtigung_anlegen(
                            con, "mail_fehler", f"mail_fehler:{p['id']}:{code}", "Mail-Abruf fehlgeschlagen",
                            f"Der Abruf eines Postfachs ist fehlgeschlagen (Fehler „{code}“). Kontor versucht es beim "
                            "nächsten Abruf erneut; bereits abgerufene Mails bleiben erhalten.",
                            f"/mail/postfaecher/{p['id']}", self.jetzt_text(), "ungelesen")
                aus.update(status="fehlgeschlagen", fehler={"code": code, "meldung": meldung})
                return aus
            filt = [f.casefold() for f in p["absender_filter"]]
            with db.transaktion(con):
                for n in liste:
                    aus["nachrichten_gesamt"] += 1
                    if con.execute("SELECT 1 FROM mail_nachricht WHERE adresse_cf = ? AND nachricht_id = ?",
                                   (cf, n.nachricht_id)).fetchone():
                        aus["nachrichten_vorhanden"] += 1
                        continue
                    if filt and not any(f in n.absender.casefold() for f in filt):
                        aus["nachrichten_gefiltert"] += 1
                        continue
                    con.execute("INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff,"
                                " text) VALUES (?, ?, ?, ?, ?, ?)",
                                (cf, n.nachricht_id, zeit_text(n.empfangen), n.absender, n.betreff, n.text))
                    aus["nachrichten_neu"] += 1
                con.execute("UPDATE postfach_zustand SET letzter_erfolg_am = ?, fehler_code = NULL, fehler_meldung = NULL"
                            " WHERE adresse_cf = ?", (zeit_text(beginn), cf))
            return aus
        finally:
            con.close()

    def faellig(self) -> bool:
        """mail.md 6.4."""
        if self.config.mail_intervall_minuten <= 0:
            return False
        con = self._con()
        try:
            if con.execute("SELECT 1 FROM postfach WHERE aktiv = 1").fetchone() is None:
                return False
            if self._geheim.gesperrt(con):
                return False
            r = con.execute("SELECT MAX(z.letzter_abruf_am) FROM postfach p JOIN postfach_zustand z"
                            " ON z.adresse_cf = p.adresse_cf").fetchone()[0]
        finally:
            con.close()
        if r is None:
            return True
        return zeit_lesen(r) + dt.timedelta(minutes=self.config.mail_intervall_minuten) <= self._jetzt()

    def nachrichten_liste(self, con, postfach_id: int | None, seite: int, pro_seite: int) -> dict:
        wo, par = "", []
        if postfach_id is not None:
            wo, par = " WHERE p.id = ?", [buch.sichere_id(postfach_id)]
        basis = " FROM mail_nachricht n JOIN postfach p ON p.adresse_cf = n.adresse_cf" + wo
        gesamt = con.execute("SELECT COUNT(*)" + basis, par).fetchone()[0]
        zeilen = con.execute("SELECT n.*, p.id AS postfach_id" + basis
                             + " ORDER BY n.empfangen, p.id, n.nachricht_id LIMIT ? OFFSET ?",
                             par + [pro_seite, (seite - 1) * pro_seite]).fetchall()
        return {"eintraege": [{"id": r["id"], "postfach_id": r["postfach_id"], "nachricht_id": r["nachricht_id"],
                               "empfangen": r["empfangen"], "absender": r["absender"], "betreff": r["betreff"],
                               "text": r["text"]} for r in zeilen],
                "gesamt": gesamt, "seite": seite, "pro_seite": pro_seite}


def _sekunden(wert) -> int:
    return wert if type(wert) is int and wert >= 0 else 3600


def _fehler_von(e: BaseException) -> tuple[str, str]:
    if isinstance(e, KontorFehler):
        return e.code, (e.meldung or "").strip() or "Fehler des Mail-Plugins."
    log.warning("Unerwarteter Fehler im Mail-Plugin: %s", type(e).__name__)
    return "mail_fehler", "Unerwarteter Fehler im Mail-Plugin."


__all__ = ["MailDienst"]
