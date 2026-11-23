"""Meilenstein 6 in der Wegwerf-Referenz (KEIN Anwendungscode): Geheimnisspeicher, Zustellung per Plugin,
TAN-Erinnerungen, PIN aus systemd-creds, Postfächer, OAuth2-Anmeldung, Mail-Abruf.

Alles im Arbeitsspeicher des Buchs; die Referenz ist klein und nicht für den Betrieb gedacht.
"""

from __future__ import annotations

import base64
import binascii
import copy
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import ssl
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from . import mutant
from .buch import Fehler
from .fehler import (KontorFehler, MailAnmeldungFehlt, MailOAuthFehler, MailTokenAbgelaufen, MailTokenWiderrufen)
from .plugins import erzeuge_benachrichtigungs_plugin, erzeuge_mail_plugin
from .plugins.benachrichtigung import PushNachricht

UTC = dt.timezone.utc
SCOPE = "https://mail.google.com/"
SCHREIBBAR = ("ntfy_token", "oauth_client_secret")
PRIORITAET = {"tan_erforderlich": 4, "tan_erinnerung": 4, "mail_token_abgelaufen": 4, "mail_token_widerrufen": 4}


def zs(d: dt.datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def zeit(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeheimnisEingabe(M):
    wert: Annotated[StrictStr, Field(min_length=1, max_length=4096)]


Filter = Annotated[list[Annotated[StrictStr, Field(min_length=1, max_length=200)]], Field(max_length=50)]


class PostfachNeu(M):
    adresse: Annotated[StrictStr, Field(min_length=3, max_length=254)]
    bezeichnung: Annotated[StrictStr, Field(max_length=200)] = ""
    ordner: Annotated[StrictStr, Field(min_length=1, max_length=200)] = "INBOX"
    absender_filter: Filter = []
    aktiv: StrictBool = True


class PostfachAenderung(M):
    bezeichnung: Annotated[StrictStr, Field(max_length=200)] = None
    ordner: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    absender_filter: Filter = None
    aktiv: StrictBool = None


class Abschluss(M):
    antwort_url: Annotated[StrictStr, Field(min_length=1, max_length=8192)]


def _v(meldung: str) -> Fehler:
    return Fehler(422, "validierung", meldung, [{"ort": ["body"], "meldung": meldung}])


# ================================================================ Geheimnisspeicher (geheimnisse.md)
class Geheimnisse:
    def __init__(self, config, buch, dienst) -> None:
        self.c, self.buch, self.dienst = config, buch, dienst

    def quelle(self) -> tuple[str, Path]:
        c = self.c
        if c.credentials_verzeichnis is not None and (c.credentials_verzeichnis / "kontor-geheimnisschluessel").exists():
            return "systemd-creds", c.credentials_verzeichnis / "kontor-geheimnisschluessel"
        return "datei", c.geheimnis_schluessel_datei or c.aktive_datenbank.with_suffix(".schluessel")

    def _schluessel(self) -> bytes | None:
        _, pfad = self.quelle()
        try:
            roh = pfad.read_bytes().strip()
            k = base64.b64decode(roh, validate=True)
        except (OSError, binascii.Error, ValueError):
            return None
        return k if len(k) == 32 else None

    def uebersicht(self) -> dict:
        q, pfad = self.quelle()
        eintraege = [{"name": n, "gesetzt_am": e["gesetzt_am"], "lesbar": self.lesen(n) is not None}
                     for n, e in sorted(self.buch.geheimnisse.items())]
        return {"schluessel": {"quelle": q, "vorhanden": pfad.exists(), "gueltig": self._schluessel() is not None},
                "eintraege": eintraege}

    def schreiben(self, name: str, wert: str) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
        q, pfad = self.quelle()
        if not pfad.exists() and q == "datei":
            pfad.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64encode(secrets.token_bytes(32)) + b"\n")
        k = self._schluessel()
        if k is None:
            raise Fehler(409, "geheimnis_schluessel_ungueltig", "Der Geheimnisschlüssel ist ungültig")
        nonce = secrets.token_bytes(12)
        ct = AESGCM(k).encrypt(nonce, wert.encode(), name.encode())
        self.buch.geheimnisse[name] = {"nonce": nonce, "ct": ct, "gesetzt_am": zs(self.dienst.jetzt())}
        if mutant("geheimnis_klartext"):
            with open(self.c.aktive_datenbank, "ab") as f:
                f.write(wert.encode())

    def lesen(self, name: str) -> str | None:
        from cryptography.exceptions import InvalidTag  # noqa: PLC0415
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415
        e = self.buch.geheimnisse.get(name)
        k = self._schluessel()
        if e is None or k is None:
            return None
        try:
            return AESGCM(k).decrypt(e["nonce"], e["ct"], name.encode()).decode()
        except InvalidTag:
            return None

    def loeschen(self, name: str) -> None:
        self.buch.geheimnisse.pop(name, None)


# ================================================================ HTTP für OAuth (geheimnisse.md 7)
class _OhneUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def post_formular(config, url: str, felder: dict, timeout: int) -> tuple[int | None, dict]:
    kontext = ssl.create_default_context(cafile=str(config.tls_ca_datei) if config.tls_ca_datei else None)
    oeffner = urllib.request.build_opener(_OhneUmleitung, urllib.request.HTTPSHandler(context=kontext),
                                          urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=urlencode(felder).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with oeffner.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError):
        return None, {}


# ================================================================ Dienst M6
class M6:
    def __init__(self, app: FastAPI, config, buch) -> None:
        self.c, self.buch = config, buch
        self.dienst = app.state.dienst
        self.g = Geheimnisse(config, buch, self.dienst)
        self.plugin = None
        self.plugin_erzeugt = False
        self.naechster: dict[int, dt.datetime] = {}
        self.letzter_fehler = None
        self.zustell_sperre = threading.Lock()
        self.erinnert: dict[int, int] = {}
        self.anmeldungen: dict[str, dict] = {}
        self.abruf_laeuft = False
        self.abruf_sperre = threading.Lock()
        d = self.dienst
        if config.bank_pin_quelle == "systemd-creds":
            d.pin_lesen = self._pin_systemd
        d.neu_gemeldet = self.zustellen_neue
        alt_takt = d.takt

        def takt():
            with d.sperre:
                d.pruefe_ablauf()
                self.erinnerungen()
                self.zustellen_neue()
                self.mail_pruefen()
                lauf = alt_takt()
                self.zustellen_neue()
                if self._mail_faellig():
                    self.abruf()
                self.zustellen_neue()
                self.zustellen_faellige()
                return lauf
        d.takt = takt

    # ------------------------------------------------------------ PIN (fints.md 5)
    def _pin_systemd(self):
        if self.dienst.pin_gesperrt:
            return None
        try:
            t = (self.c.credentials_verzeichnis / "kontor-bank-pin").read_text(encoding="utf-8")
        except OSError:
            return None
        if t.endswith("\r\n"):
            t = t[:-2]
        elif t.endswith("\n"):
            t = t[:-1]
        return t or None

    # ------------------------------------------------------------ Zustellung (benachrichtigungen.md 4)
    def _plugin(self):
        if not self.plugin_erzeugt:
            self.plugin = erzeuge_benachrichtigungs_plugin(self.c, token_quelle=lambda: self.g.lesen("ntfy_token"))
            self.plugin_erzeugt = True
        return self.plugin

    def zustellen_neue(self) -> None:
        for b in sorted(self.buch.benachr.values(), key=lambda x: x["id"]):
            if "zustellung" in b:
                continue
            b["zustellversuche"], b["zugestellt_am"] = 0, None
            if self._plugin() is None:
                b["zustellung"] = "keine"
                continue
            b["zustellung"] = "ausstehend"
            self._versuch(b)
        if mutant("zustellung_doppelt"):
            for b in self.buch.benachr.values():
                if b.get("zustellung") == "zugestellt" and b["zustellversuche"] == 1:
                    self._versuch(b, erneut=True)

    def _push(self, b: dict) -> PushNachricht:
        titel = ("[Mock] " if self.c.mock_modus and not mutant("ntfy_ohne_mock_praefix") else "") + b["titel"]
        link = None
        if b["link"] and self.c.oeffentliche_url:
            link = self.c.oeffentliche_url.rstrip("/") + b["link"]
        return PushNachricht(b["id"], titel, b["text"], link, PRIORITAET.get(b["art"], 3), (b["art"],), b["schluessel"])

    def _versuch(self, b: dict, erneut: bool = False) -> None:
        with self.zustell_sperre:
            if b["zustellung"] not in ("ausstehend",) and not erneut:
                return
            b["zustellversuche"] += 1
            jetzt = self.dienst.jetzt()
            try:
                self._plugin().senden(self._push(b))
            except Exception as e:  # noqa: BLE001
                self.letzter_fehler = {"code": getattr(e, "code", "benachrichtigung_fehler"),
                                       "meldung": getattr(e, "meldung", "") or "Zustellung fehlgeschlagen",
                                       "zeitpunkt": zs(jetzt)}
                if b["zustellversuche"] >= self.c.zustellung_max_versuche and not mutant("zustellung_ohne_grenze"):
                    b["zustellung"] = "aufgegeben"
                else:
                    self.naechster[b["id"]] = jetzt + dt.timedelta(minutes=self.c.zustellung_wiederholung_minuten)
                return
            b["zustellung"], b["zugestellt_am"] = "zugestellt", zs(jetzt)

    def zustellen_faellige(self, alle: bool = False) -> dict:
        versucht = zugestellt = 0
        if mutant("zustellung_ohne_wiederholung") and not alle:
            return {"versucht": 0, "zugestellt": 0}
        for b in sorted(self.buch.benachr.values(), key=lambda x: x["id"]):
            if b.get("zustellung") != "ausstehend":
                continue
            if not alle and self.naechster.get(b["id"], dt.datetime.min.replace(tzinfo=UTC)) > self.dienst.jetzt():
                continue
            versucht += 1
            self._versuch(b)
            zugestellt += b["zustellung"] == "zugestellt"
        return {"versucht": versucht, "zugestellt": zugestellt}

    def status(self) -> dict:
        z = [b.get("zustellung") for b in self.buch.benachr.values()]
        return {"plugin": self.c.benachrichtigung_plugin, "ausstehend": z.count("ausstehend"),
                "zugestellt": z.count("zugestellt"), "aufgegeben": z.count("aufgegeben"),
                "letzter_fehler": self.letzter_fehler}

    # ------------------------------------------------------------ TAN-Erinnerungen (benachrichtigungen.md 5)
    def erinnerungen(self) -> None:
        intervall, anzahl = self.c.tan_erinnerung_minuten, self.c.tan_erinnerung_anzahl
        if intervall <= 0:
            return
        jetzt = self.dienst.jetzt()
        for t in self.buch.tan.values():
            if t["status"] != "offen" and not mutant("tan_erinnerung_nach_antwort"):
                continue
            if jetzt > zeit(t["gueltig_bis"]):
                continue
            k = int((jetzt - zeit(t["erstellt_am"])).total_seconds() // (intervall * 60))
            n = k if mutant("tan_erinnerung_ohne_grenze") else min(k, anzahl)
            m = self.erinnert.get(t["id"], 0)
            if n >= 1 and n > m:
                nummern = range(m + 1, n + 1) if mutant("tan_erinnerung_nachholen") else [n]
                for x in nummern:
                    self._melden("tan_erinnerung", f"tan_erinnerung:{t['id']}:{x}", "Erinnerung: TAN erforderlich",
                                 f"Die Bank wartet weiterhin auf eine TAN ({t['challenge'][:80]}).", f"/tan/{t['id']}",
                                 einmal=True)
                self.erinnert[t["id"]] = n

    def _melden(self, art, schluessel, titel, text, link, *, einmal: bool) -> None:
        b = self.buch
        if any(x["schluessel"] == schluessel and (einmal or not x["gelesen"]) for x in b.benachr.values()):
            return
        bid = b.neue_id("benachrichtigung")
        b.benachr[bid] = {"id": bid, "art": art, "schluessel": schluessel, "titel": titel, "text": text, "link": link,
                          "erstellt_am": zs(self.dienst.jetzt()), "gelesen": False}
        self.zustellen_neue()

    # ------------------------------------------------------------ Postfächer (mail.md 2)
    def _betrieb(self, adresse: str) -> dict:
        return self.buch.mail_betrieb.setdefault(adresse.casefold(), {
            "anmeldung": "fehlt", "anmeldung_nr": 0, "angemeldet_am": None, "laeuft_ab_am": None,
            "letzter_abruf_am": None, "letzter_erfolg_am": None, "letzter_fehler": None})

    def _postfach(self, pid: int) -> dict:
        if pid not in self.buch.postfaecher:
            raise Fehler(404, "nicht_gefunden", "Postfach nicht gefunden")
        return self.buch.postfaecher[pid]

    def postfach_status(self, p: dict) -> dict:
        b = self._betrieb(p["adresse"])
        anm = "nicht_erforderlich" if self.c.mock_modus else b["anmeldung"]
        return {"postfach_id": p["id"], "anmeldung": anm, "anmeldung_nr": b["anmeldung_nr"],
                "angemeldet_am": b["angemeldet_am"], "laeuft_ab_am": b["laeuft_ab_am"] if anm == "angemeldet" else None,
                "letzter_abruf_am": b["letzter_abruf_am"], "letzter_erfolg_am": b["letzter_erfolg_am"],
                "letzter_fehler": b["letzter_fehler"],
                "nachrichten": len(self.buch.mail_spiegel.get(p["adresse"].casefold(), {}))}

    def postfach_entfernen(self, p: dict) -> None:
        a = p["adresse"].casefold()
        self.buch.mail_betrieb.pop(a, None)
        self.buch.mail_spiegel.pop(a, None)
        self.g.loeschen("mail_token:" + a)

    # ------------------------------------------------------------ Tokens (mail.md 4, 5)
    def _tokens(self, adresse: str) -> dict | None:
        roh = self.g.lesen("mail_token:" + adresse.casefold())
        return json.loads(roh) if roh else None

    def _tokens_setzen(self, adresse: str, t: dict) -> None:
        self.g.schreiben("mail_token:" + adresse.casefold(), json.dumps(t))

    def _ablauf_melden(self, p: dict, art: str) -> None:
        b = self._betrieb(p["adresse"])
        b["anmeldung"] = "abgelaufen" if art == "mail_token_abgelaufen" else "widerrufen"
        self.g.loeschen("mail_token:" + p["adresse"].casefold())
        text = ("Die Mail-Anmeldung ist abgelaufen. Bitte neu anmelden." if art == "mail_token_abgelaufen"
                else "Die Mail-Anmeldung wurde widerrufen. Bitte neu anmelden.")
        self._melden(art, f"{art}:{p['id']}:{b['anmeldung_nr']}", "Mail-Anmeldung erforderlich", text,
                     f"/mail/postfaecher/{p['id']}", einmal=True)

    def _pruefe_ablauf(self, p: dict) -> None:
        if self.c.mock_modus:
            return
        b = self._betrieb(p["adresse"])
        if b["anmeldung"] != "angemeldet" or not b["laeuft_ab_am"]:
            return
        a = zeit(b["laeuft_ab_am"])
        jetzt = self.dienst.jetzt()
        if jetzt >= a and not mutant("oauth_ablauf_ignoriert"):
            self._ablauf_melden(p, "mail_token_abgelaufen")
        elif jetzt >= a - dt.timedelta(hours=self.c.oauth_vorwarnung_stunden):
            self._melden("mail_token_laeuft_ab", f"mail_token_laeuft_ab:{p['id']}:{b['anmeldung_nr']}",
                         "Mail-Anmeldung läuft bald ab", "Die Mail-Anmeldung läuft bald ab. Bitte neu anmelden.",
                         f"/mail/postfaecher/{p['id']}", einmal=not mutant("vorwarnung_jeder_takt"))

    def mail_pruefen(self) -> None:
        for p in list(self.buch.postfaecher.values()):
            self._pruefe_ablauf(p)

    def zugang(self, adresse: str, erneuern: bool) -> str:
        p = next(x for x in self.buch.postfaecher.values() if x["adresse"].casefold() == adresse.casefold())
        b = self._betrieb(adresse)
        self._pruefe_ablauf(p)
        if b["anmeldung"] == "fehlt":
            raise MailAnmeldungFehlt("Nicht angemeldet")
        if b["anmeldung"] == "abgelaufen":
            raise MailTokenAbgelaufen("Anmeldung abgelaufen")
        if b["anmeldung"] == "widerrufen":
            raise MailTokenWiderrufen("Anmeldung widerrufen")
        t = self._tokens(adresse)
        if t is None:
            raise MailAnmeldungFehlt("Keine Tokens")
        jetzt = self.dienst.jetzt()
        if not erneuern and t.get("access") and jetzt < zeit(t["access_bis"]) - dt.timedelta(seconds=60):
            return t["access"]
        secret = self.g.lesen("oauth_client_secret")
        if not secret or not self.c.oauth_client_id:
            raise MailOAuthFehler("OAuth-Client fehlt")
        status, antwort = post_formular(self.c, self.c.oauth_token_url, {
            "grant_type": "refresh_token", "refresh_token": t["refresh"], "client_id": self.c.oauth_client_id,
            "client_secret": secret}, self.c.oauth_timeout_sekunden)
        if status == 200 and antwort.get("access_token"):
            t["access"] = antwort["access_token"]
            t["access_bis"] = zs(jetzt + dt.timedelta(seconds=int(antwort.get("expires_in", 3600))))
            if antwort.get("refresh_token"):
                t["refresh"] = antwort["refresh_token"]
                self._ablauf_setzen(b, t, antwort, jetzt)
            self._tokens_setzen(adresse, t)
            return t["access"]
        if antwort.get("error") == "invalid_grant":
            a = b["laeuft_ab_am"]
            abgelaufen = a is not None and jetzt >= zeit(a) - dt.timedelta(hours=1)
            if mutant("oauth_widerruf_als_ablauf"):
                abgelaufen = True
            self._ablauf_melden(p, "mail_token_abgelaufen" if abgelaufen else "mail_token_widerrufen")
            raise (MailTokenAbgelaufen if abgelaufen else MailTokenWiderrufen)("Refresh-Token abgelehnt")
        raise MailOAuthFehler("Tokenerneuerung fehlgeschlagen")

    def _ablauf_setzen(self, b: dict, t: dict, antwort: dict, jetzt: dt.datetime) -> None:
        b["laeuft_ab_am"] = None
        if antwort.get("refresh_token_expires_in") is not None and not mutant("oauth_ablauf_feld_ignoriert"):
            b["laeuft_ab_am"] = zs(jetzt + dt.timedelta(seconds=int(antwort["refresh_token_expires_in"])))
        elif self.c.oauth_refresh_gueltig_stunden > 0:
            b["laeuft_ab_am"] = zs(jetzt + dt.timedelta(hours=self.c.oauth_refresh_gueltig_stunden))

    def anmeldung_starten(self, pid: int) -> dict:
        p = self._postfach(pid)
        if self.c.mock_modus:
            raise Fehler(409, "nur_echtmodus", "Anmeldung nur im Echtmodus")
        if not self.c.oauth_client_id or not self.g.lesen("oauth_client_secret"):
            raise Fehler(409, "oauth_client_fehlt", "OAuth-Client nicht eingerichtet")
        for s, a in list(self.anmeldungen.items()):
            if a["pid"] == pid:
                del self.anmeldungen[s]
        state = secrets.token_urlsafe(24)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if mutant("oauth_ohne_pkce"):
            challenge = verifier
        bis = self.dienst.jetzt() + dt.timedelta(minutes=10)
        self.anmeldungen[state] = {"pid": pid, "verifier": verifier, "bis": bis}
        q = urlencode({"response_type": "code", "client_id": self.c.oauth_client_id,
                       "redirect_uri": self.c.oauth_redirect_uri, "scope": SCOPE, "state": state,
                       "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline",
                       "prompt": "consent", "login_hint": p["adresse"]})
        u = self.c.oauth_autorisierung_url
        return {"autorisierung_url": u + ("&" if "?" in u else "?") + q, "gueltig_bis": zs(bis)}

    def anmeldung_abschliessen(self, parameter: dict) -> dict:
        if self.c.mock_modus:
            raise Fehler(409, "nur_echtmodus", "Anmeldung nur im Echtmodus")
        state = parameter.get("state")
        a = self.anmeldungen.get(state or "")
        if a is None or self.dienst.jetzt() > a["bis"]:
            raise Fehler(422, "oauth_zustand_ungueltig", "Anmeldung unbekannt oder abgelaufen")
        del self.anmeldungen[state]
        if parameter.get("error"):
            raise Fehler(422, "oauth_abgelehnt", "Die Anmeldung wurde abgelehnt")
        if not parameter.get("code"):
            raise Fehler(422, "oauth_zustand_ungueltig", "Code fehlt")
        p = self._postfach(a["pid"])
        status, antwort = post_formular(self.c, self.c.oauth_token_url, {
            "grant_type": "authorization_code", "code": parameter["code"], "redirect_uri": self.c.oauth_redirect_uri,
            "client_id": self.c.oauth_client_id, "client_secret": self.g.lesen("oauth_client_secret") or "",
            "code_verifier": a["verifier"]}, self.c.oauth_timeout_sekunden)
        if status != 200:
            raise Fehler(409, "oauth_fehler", "Tokenaustausch fehlgeschlagen",
                         {"error": antwort.get("error")} if antwort.get("error") else None)
        if SCOPE not in str(antwort.get("scope", "")).split():
            raise Fehler(422, "oauth_scope_fehlt", "Der Scope fehlt")
        if not antwort.get("refresh_token"):
            raise Fehler(422, "oauth_kein_refresh_token", "Kein Refresh-Token")
        jetzt = self.dienst.jetzt()
        b = self._betrieb(p["adresse"])
        t = {"refresh": antwort["refresh_token"], "access": antwort.get("access_token"),
             "access_bis": zs(jetzt + dt.timedelta(seconds=int(antwort.get("expires_in", 3600)))), "ausgestellt": zs(jetzt)}
        self._ablauf_setzen(b, t, antwort, jetzt)
        self._tokens_setzen(p["adresse"], t)
        b["anmeldung"], b["anmeldung_nr"], b["angemeldet_am"] = "angemeldet", b["anmeldung_nr"] + 1, zs(jetzt)
        for x in self.buch.benachr.values():
            if any(x["schluessel"].startswith(f"{art}:{p['id']}:") for art in (
                    "mail_token_laeuft_ab", "mail_token_abgelaufen", "mail_token_widerrufen", "mail_fehler")):
                x["gelesen"] = True
        return self.postfach_status(p)

    def abmelden(self, pid: int) -> None:
        p = self._postfach(pid)
        if self.c.mock_modus:
            raise Fehler(409, "nur_echtmodus", "Abmelden nur im Echtmodus")
        t = self._tokens(p["adresse"])
        if t:
            post_formular(self.c, self.c.oauth_widerruf_url, {"token": t["refresh"]}, self.c.oauth_timeout_sekunden)
        self.g.loeschen("mail_token:" + p["adresse"].casefold())
        b = self._betrieb(p["adresse"])
        b["anmeldung"], b["laeuft_ab_am"] = "fehlt", None

    # ------------------------------------------------------------ Abruf (mail.md 6)
    def _mail_faellig(self) -> bool:
        if self.c.mail_intervall_minuten <= 0:
            return False
        zeiten = [zeit(b["letzter_abruf_am"]) for p in self.buch.postfaecher.values()
                  if (b := self.buch.mail_betrieb.get(p["adresse"].casefold())) and b["letzter_abruf_am"]]
        return not zeiten or max(zeiten) + dt.timedelta(minutes=self.c.mail_intervall_minuten) <= self.dienst.jetzt()

    def abruf(self) -> dict:
        with self.abruf_sperre:
            if self.abruf_laeuft:
                raise Fehler(409, "mail_abruf_laeuft", "Es läuft bereits ein Abruf")
            self.abruf_laeuft = True
        try:
            return self._abruf()
        finally:
            self.abruf_laeuft = False

    def _abruf(self) -> dict:
        from .plugins.imap import ImapPostfach  # noqa: PLC0415
        start = self.dienst.jetzt()
        aktive = sorted((p for p in self.buch.postfaecher.values() if p["aktiv"]), key=lambda p: p["id"])
        plugin = erzeuge_mail_plugin(self.c, postfaecher=[ImapPostfach(p["adresse"], p["ordner"]) for p in aktive],
                                     zugang=self.zugang)
        if self.c.mock_modus:
            plugin.setze_heute(self.dienst.heute())
        for p in aktive:
            self._pruefe_ablauf(p)
        ergebnisse: dict[int, dict] = {}

        def eins(p):
            ergebnisse[p["id"]] = self._postfach_abruf(plugin, p, start)
        if mutant("mail_nacheinander"):
            for p in aktive:
                eins(p)
        else:
            faeden = [threading.Thread(target=eins, args=(p,)) for p in aktive]
            for f in faeden:
                f.start()
            for f in faeden:
                f.join()
        return {"gestartet_am": zs(start), "beendet_am": zs(self.dienst.jetzt()),
                "postfaecher": [ergebnisse[p["id"]] for p in aktive]}

    def _postfach_abruf(self, plugin, p: dict, start: dt.datetime) -> dict:
        b = self._betrieb(p["adresse"])
        if b["letzter_erfolg_am"]:
            seit = zeit(b["letzter_erfolg_am"]) - dt.timedelta(hours=self.c.mail_ueberlappung_stunden)
        else:
            seit = start - dt.timedelta(days=self.c.mail_erstabruf_tage)
        e = {"postfach_id": p["id"], "adresse": p["adresse"], "status": "erfolgreich", "seit": zs(seit),
             "nachrichten_gesamt": 0, "nachrichten_neu": 0, "nachrichten_vorhanden": 0, "nachrichten_gefiltert": 0,
             "fehler": None}
        if not self.c.mock_modus and b["anmeldung"] in ("fehlt", "abgelaufen", "widerrufen"):
            e["status"] = "anmeldung_erforderlich"
            return e
        b["letzter_abruf_am"] = zs(start)
        try:
            liste = plugin.nachrichten(p["adresse"], seit)
        except KontorFehler as x:
            return self._abruf_fehler(p, b, e, x)
        except Exception:  # noqa: BLE001
            return self._abruf_fehler(p, b, e, KontorFehler("Fehler des Mail-Plugins"))
        spiegel = self.buch.mail_spiegel.setdefault(p["adresse"].casefold(), {})
        filt = [f.casefold() for f in p["absender_filter"]]
        for n in liste:
            e["nachrichten_gesamt"] += 1
            if n.nachricht_id in spiegel:
                e["nachrichten_vorhanden"] += 1
            elif filt and not any(f in n.absender.casefold() for f in filt) and not mutant("mail_filter_ignoriert"):
                e["nachrichten_gefiltert"] += 1
            else:
                spiegel[n.nachricht_id] = {"id": self.buch.neue_id("mail_nachricht"), "nachricht_id": n.nachricht_id,
                                           "empfangen": zs(n.empfangen), "absender": n.absender, "betreff": n.betreff,
                                           "text": n.text}
                e["nachrichten_neu"] += 1
        b["letzter_erfolg_am"], b["letzter_fehler"] = zs(start), None
        return e

    def _abruf_fehler(self, p, b, e, x) -> dict:
        code = getattr(x, "code", "plugin_fehler")
        e.update(status="fehlgeschlagen", fehler={"code": code, "meldung": x.meldung or code})
        b["letzter_fehler"] = e["fehler"]
        if code in ("mail_token_abgelaufen", "mail_token_widerrufen") and not self.c.mock_modus:
            return e
        if code == "mail_token_abgelaufen":
            self._melden("mail_token_abgelaufen", f"mail_token_abgelaufen:{p['id']}:0", "Mail-Anmeldung abgelaufen",
                         "Die Mail-Anmeldung ist abgelaufen.", f"/mail/postfaecher/{p['id']}", einmal=True)
        else:
            self._melden("mail_fehler", f"mail_fehler:{p['id']}:{code}", "Mail-Abruf fehlgeschlagen",
                         "Der Abruf des Postfachs ist fehlgeschlagen.", f"/mail/postfaecher/{p['id']}", einmal=False)
        return e

    def nachrichten(self, postfach_id: int | None) -> list[dict]:
        aus = []
        for p in self.buch.postfaecher.values():
            if postfach_id is not None and p["id"] != postfach_id:
                continue
            for n in self.buch.mail_spiegel.get(p["adresse"].casefold(), {}).values():
                aus.append({"id": n["id"], "postfach_id": p["id"], **{k: n[k] for k in (
                    "nachricht_id", "empfangen", "absender", "betreff", "text")}})
        return sorted(aus, key=lambda n: (n["empfangen"], n["postfach_id"], n["nachricht_id"]))


# ================================================================ REST
def _adresse_ok(a: str) -> bool:
    return 3 <= len(a) <= 254 and a.count("@") == 1 and all(a.split("@")) and not re.search(r"\s", a)


def m6_einbinden(app: FastAPI, config, buch) -> None:
    m6 = M6(app, config, buch)
    app.state.m6 = m6
    dienst = m6.dienst

    @app.middleware("http")
    async def zustellung(request: Request, call_next):
        if config.bank_pin_quelle == "systemd-creds" and request.url.path == "/api/sync/pin" \
                and request.method in ("PUT", "DELETE"):
            return JSONResponse({"fehler": {"code": "pin_quelle_systemd", "meldung": "Die PIN kommt aus systemd-creds",
                                            "details": None}}, status_code=409, headers={"X-Kontor-Modus": "mock" if
                                                                                         config.mock_modus else "echt"})
        antwort = await call_next(request)
        m6.zustellen_neue()
        return antwort

    # ------------------------------------------------------------ Geheimnisse
    @app.get("/api/geheimnisse")
    def geheimnisse():
        return m6.g.uebersicht()

    def _name(name: str) -> str:
        if name not in SCHREIBBAR:
            raise Fehler(404, "nicht_gefunden", "Geheimnis unbekannt")
        return name

    @app.put("/api/geheimnisse/{name}", status_code=204)
    async def geheimnis_setzen(name: str, request: Request):
        _name(name)
        try:
            d = GeheimnisEingabe.model_validate_json(await request.body())
        except Exception:  # noqa: BLE001 - Validierungsfehler ohne den Wert
            raise _v("Ungültiger Körper") from None
        m6.g.schreiben(name, d.wert)
        return Response(status_code=204)

    @app.delete("/api/geheimnisse/{name}", status_code=204)
    def geheimnis_loeschen(name: str):
        m6.g.loeschen(_name(name))
        return Response(status_code=204)

    # ------------------------------------------------------------ Zustellung
    @app.get("/api/benachrichtigungen/zustellung")
    def zustell_status():
        return m6.status()

    @app.post("/api/benachrichtigungen/zustellen")
    def zustellen():
        return m6.zustellen_faellige(alle=True)

    @app.post("/api/benachrichtigungen/test")
    def test_benachrichtigung():
        """M8, benachrichtigungen.md 8 (E-138)."""
        p = m6._plugin()
        if p is None:
            raise Fehler(409, "kein_benachrichtigungs_plugin", "Kein Benachrichtigungs-Plugin konfiguriert", {})
        if config.benachrichtigung_plugin == "mock" and not mutant("m8_test_in_mock_liste"):
            return {"plugin": "mock", "zugestellt": True, "gesendet": False, "fehler": None}
        titel = ("[Mock] " if config.mock_modus else "") + "Kontor: Test-Benachrichtigung"
        link = config.oeffentliche_url.rstrip("/") + "/einstellungen" if config.oeffentliche_url else None
        n = PushNachricht(0, titel, "Diese Test-Benachrichtigung wurde in den Einstellungen ausgelöst.", link, 3,
                          ("test",), "test:" + zs(m6.dienst.jetzt()))
        try:
            p.senden(n)
        except Exception as e:  # noqa: BLE001
            return {"plugin": config.benachrichtigung_plugin, "zugestellt": False, "gesendet": True,
                    "fehler": {"code": "benachrichtigung_fehler",
                               "meldung": getattr(e, "meldung", "") or "Zustellung fehlgeschlagen",
                               "status": getattr(e, "details", {}).get("status")}}
        return {"plugin": config.benachrichtigung_plugin, "zugestellt": True, "gesendet": True, "fehler": None}

    @app.get("/api/mock/zustellungen")
    def mock_zustellungen():
        if not config.mock_modus:
            raise Fehler(409, "nur_mock_modus", "Nur im Mock-Modus verfügbar")
        p = m6._plugin()
        return [{**n.__dict__, "tags": list(n.tags)} for n in getattr(p, "gesendet", [])]

    # ------------------------------------------------------------ Postfächer
    @app.get("/api/mail/postfaecher")
    def postfaecher():
        return [copy.deepcopy(p) for p in sorted(buch.postfaecher.values(), key=lambda p: p["id"])]

    @app.post("/api/mail/postfaecher", status_code=201)
    def postfach_anlegen(d: PostfachNeu):
        if not _adresse_ok(d.adresse):
            raise _v("Adresse ungültig")
        if len(set(d.absender_filter)) != len(d.absender_filter):
            raise _v("Filter doppelt")
        if any(p["adresse"].casefold() == d.adresse.casefold() for p in buch.postfaecher.values()):
            raise Fehler(409, "postfach_existiert", "Postfach existiert bereits")
        pid = buch.neue_id("postfach")
        buch.postfaecher[pid] = {"id": pid, **d.model_dump()}
        return copy.deepcopy(buch.postfaecher[pid])

    @app.get("/api/mail/postfaecher/{postfach_id}")
    def postfach_lesen(postfach_id: int):
        return copy.deepcopy(m6._postfach(postfach_id))

    @app.patch("/api/mail/postfaecher/{postfach_id}")
    def postfach_aendern(postfach_id: int, d: PostfachAenderung):
        p = m6._postfach(postfach_id)
        felder = {k: v for k, v in d.model_dump().items() if k in d.model_fields_set}
        if any(v is None for v in felder.values()):
            raise _v("null nicht erlaubt")
        if "absender_filter" in felder and len(set(felder["absender_filter"])) != len(felder["absender_filter"]):
            raise _v("Filter doppelt")
        p.update(felder)
        return copy.deepcopy(p)

    @app.delete("/api/mail/postfaecher/{postfach_id}", status_code=204)
    def postfach_loeschen(postfach_id: int):
        p = m6._postfach(postfach_id)
        m6.postfach_entfernen(p)
        del buch.postfaecher[postfach_id]
        return Response(status_code=204)

    @app.get("/api/mail/postfaecher/{postfach_id}/status")
    def postfach_status(postfach_id: int):
        p = m6._postfach(postfach_id)
        m6._pruefe_ablauf(p)
        return m6.postfach_status(p)

    @app.post("/api/mail/postfaecher/{postfach_id}/anmeldung")
    def anmeldung_starten(postfach_id: int):
        return m6.anmeldung_starten(postfach_id)

    @app.delete("/api/mail/postfaecher/{postfach_id}/anmeldung", status_code=204)
    def abmelden(postfach_id: int):
        m6.abmelden(postfach_id)
        return Response(status_code=204)

    @app.post("/api/mail/anmeldung/abschluss")
    def abschluss(d: Abschluss):
        q = {k: v[0] for k, v in parse_qs(urlsplit(d.antwort_url).query).items()}
        return m6.anmeldung_abschliessen(q)

    @app.get("/oauth2/rueckruf", response_class=HTMLResponse)
    def rueckruf(request: Request):
        try:
            m6.anmeldung_abschliessen(dict(request.query_params))
        except Fehler:
            return HTMLResponse("<!DOCTYPE html><html><body><p>Anmeldung fehlgeschlagen.</p></body></html>",
                                status_code=400)
        return HTMLResponse("<!DOCTYPE html><html><body><p>Anmeldung erfolgreich.</p></body></html>")

    @app.post("/api/mail/abruf")
    def mail_abruf():
        return m6.abruf()

    @app.get("/api/mail/nachrichten")
    def mail_nachrichten(postfach_id: int | None = None, seite: int = Query(1, ge=1),
                         pro_seite: int = Query(50, ge=1, le=500)):
        alle = m6.nachrichten(postfach_id)
        return {"eintraege": alle[(seite - 1) * pro_seite: seite * pro_seite], "gesamt": len(alle), "seite": seite,
                "pro_seite": pro_seite}

    del dienst


__all__ = ["m6_einbinden"]
