"""Bankzugang (FinTS) aus der Weboberfläche: Speicherung und wirksame Konfiguration (D-192).

Gespeichert werden nur Angaben ohne Geheimnischarakter – Server-URL, Bankleitzahl, Benutzerkennung, Kunden-ID,
Produkt-ID, TAN-Verfahren und die bei der Bank abgerufenen Konten mit ihrer Auswahl. Die PIN gehört nie dazu.
Alles liegt als Betriebszustand in ``meta`` (Schlüssel ``bank_…``): nicht im Änderungsprotokoll, nicht in der
Datensicherung. Ohne gespeicherten Wert gilt die Vorbelegung aus der Konfiguration (``KONTOR_FINTS_*``).
"""

from __future__ import annotations

import base64
import dataclasses
import json
import secrets

from .config import KontorConfig
from . import db
from .fehler import KonfigurationsFehler, TanAbgelaufen, TanErforderlich, TanUngueltig
from .plugins.bank import BankKonto
from .text import iban_gueltig, iban_normalisieren
from .validierung import ApiFehler, fehler_eintrag

# Feld der Schnittstelle → Feld der Konfiguration
FELDER = {"url": "fints_url", "blz": "fints_blz", "benutzer": "fints_benutzer", "kunden_id": "fints_kunden_id",
          "produkt_id": "fints_produkt_id", "tan_verfahren": "fints_tan_verfahren"}
PFLICHT = ("url", "blz", "benutzer", "produkt_id")
# Ändert sich eines dieser Felder, gehören die abgerufenen Konten zu einem anderen Zugang und entfallen.
_ZUGANG = ("url", "blz", "benutzer", "kunden_id")
_KONTEN = "bank_konten"
MELDUNGEN = {"url": "Gültige https-Adresse erwartet (http nur für diesen Rechner).", "blz": "Genau 8 Ziffern erwartet.",
             "benutzer": "1 bis 64 Zeichen erwartet.", "kunden_id": "1 bis 64 Zeichen erwartet.",
             "produkt_id": "1 bis 25 Zeichen erwartet.", "tan_verfahren": "Genau 3 Ziffern erwartet."}


def _gespeichert(con) -> dict[str, str]:
    return {r["schluessel"][len("bank_fints_"):]: r["wert"]
            for r in con.execute("SELECT schluessel, wert FROM meta WHERE schluessel LIKE 'bank!_fints!_%' ESCAPE '!'")}


def werte(con, config: KontorConfig) -> dict[str, str | None]:
    """Wirksame Werte: gespeichert, sonst Vorbelegung aus der Konfiguration."""
    g = _gespeichert(con)
    return {f: g.get(f, getattr(config, c)) for f, c in FELDER.items()}


def wirksame_config(con, config: KontorConfig) -> KontorConfig:
    g = _gespeichert(con)
    if not g:
        return config
    try:
        return dataclasses.replace(config, **{FELDER[f]: w for f, w in g.items() if f in FELDER})
    except KonfigurationsFehler:
        return config  # unlesbar gewordene Werte nie anwenden; die Oberfläche zeigt sie zum Korrigieren


def konten(con) -> list[dict]:
    r = con.execute("SELECT wert FROM meta WHERE schluessel = ?", (_KONTEN,)).fetchone()
    if r is None:
        return []
    try:
        liste = json.loads(r["wert"])
    except ValueError:
        return []
    return [k for k in liste if isinstance(k, dict) and isinstance(k.get("iban"), str)]


def aktive_bankkonten(con) -> list[BankKonto] | None:
    """Ausgewählte Konten als ``BankKonto``; None, solange noch keine Konten abgerufen wurden."""
    liste = konten(con)
    if not liste:
        return None
    return [BankKonto(k["iban"], k.get("bic") or None, k.get("name") or "", k.get("art") or "girokonto",
                      k.get("inhaber") or "", "EUR") for k in liste if k.get("aktiv")]


def lesen(con, config: KontorConfig) -> dict:
    w = werte(con, config)
    g = _gespeichert(con)
    aenderbar = config.bank_plugin == "fints"
    return {**w, "plugin": config.bank_plugin, "aenderbar": aenderbar,
            "gespeichert": sorted(g), "vollstaendig": all(w[f] for f in PFLICHT), "konten": konten(con)}


def _nur_fints(config: KontorConfig) -> None:
    if config.bank_plugin != "fints":
        raise ApiFehler(409, "bankzugang_nicht_aenderbar",
                        "Der Bankzugang lässt sich nur mit dem FinTS-Plugin einstellen.")


def setzen(con, d: dict, config: KontorConfig) -> dict:
    """Übernimmt die übergebenen Felder; ``null`` oder leer entfernt den gespeicherten Wert (Vorbelegung gilt)."""
    _nur_fints(config)
    vorher = werte(con, config)
    neu = dict(_gespeichert(con))
    for f in FELDER:
        if f not in d:
            continue
        w = d[f]
        if w is None or w == "":
            neu.pop(f, None)
        else:
            neu[f] = w
    fehler = []
    for f, w in neu.items():  # je Feld prüfen, damit die Meldung das Feld nennt und nie den Wert
        try:
            dataclasses.replace(config, **{FELDER[f]: w})
        except KonfigurationsFehler:
            fehler.append(fehler_eintrag(["body", f], MELDUNGEN[f]))
    if fehler:
        raise ApiFehler(422, "validierung", "Die Anfrage ist ungültig.", fehler)
    con.execute("DELETE FROM meta WHERE schluessel LIKE 'bank!_fints!_%' ESCAPE '!'")
    con.executemany("INSERT INTO meta (schluessel, wert) VALUES (?, ?)",
                    [("bank_fints_" + f, w) for f, w in neu.items()])
    nachher = werte(con, config)
    if any(vorher[f] != nachher[f] for f in _ZUGANG):
        con.execute("DELETE FROM meta WHERE schluessel = ?", (_KONTEN,))
    return lesen(con, config)


def konten_uebernehmen(con, bankkonten: list[BankKonto]) -> list[dict]:
    """Speichert die von der Bank gemeldeten Konten; die bisherige Auswahl bleibt, neue Konten sind ausgewählt."""
    alt = {k["iban"]: bool(k.get("aktiv")) for k in konten(con)}
    neu = [{"iban": k.iban, "bic": k.bic, "name": k.name, "art": k.art, "inhaber": k.inhaber,
            "aktiv": alt.get(k.iban, True)} for k in sorted(bankkonten, key=lambda k: k.iban)]
    _konten_schreiben(con, neu)
    return neu


def konten_waehlen(con, ibans: list[str], config: KontorConfig) -> dict:
    _nur_fints(config)
    liste = konten(con)
    bekannt = {k["iban"] for k in liste}
    gewaehlt = set()
    fehler = []
    for i, roh in enumerate(ibans):
        n = iban_normalisieren(roh)
        if not iban_gueltig(n) or n not in bekannt:
            fehler.append(fehler_eintrag(["body", "ibans", i], "Kein abgerufenes Konto mit dieser IBAN."))
        gewaehlt.add(n)
    if fehler:
        raise ApiFehler(422, "validierung", "Die Anfrage ist ungültig.", fehler)
    for k in liste:
        k["aktiv"] = k["iban"] in gewaehlt
    _konten_schreiben(con, liste)
    return lesen(con, config)


def _konten_schreiben(con, liste: list[dict]) -> None:
    con.execute("INSERT INTO meta (schluessel, wert) VALUES (?, ?) ON CONFLICT(schluessel)"
                " DO UPDATE SET wert = excluded.wert", (_KONTEN, json.dumps(liste, ensure_ascii=False)))


# ================================================================ Dienste mit Bankverbindung
# ``dienst`` ist der ``SyncDienst`` der App: Er hält Plugin, PIN und Laufsperre. Alles hier läuft unter der
# Laufsperre, damit nie zwei FinTS-Dialoge gleichzeitig offen sind.


class _Gesperrt:
    def __init__(self, dienst) -> None:
        self.dienst = dienst

    def __enter__(self) -> None:
        _nur_fints(self.dienst.config)
        if not self.dienst._sperre.acquire(blocking=False):
            raise ApiFehler(409, "sync_laeuft", "Es läuft bereits eine Synchronisation.")
        if self.dienst.tan_offen():
            self.dienst._sperre.release()
            raise ApiFehler(409, "tan_offen", "Eine Synchronisation wartet auf eine TAN. Bitte erst die TAN "
                            "eingeben oder die Anforderung abbrechen.")

    def __exit__(self, *_a) -> None:
        self.dienst._sperre.release()


def _mit_con(dienst, f, *args):
    con = dienst._con()
    try:
        with db.transaktion(con):
            return f(con, *args)
    finally:
        con.close()


def zugang_setzen(dienst, d: dict) -> dict:
    with _Gesperrt(dienst):
        ergebnis = _mit_con(dienst, setzen, d, dienst.config)
        dienst.plugin_verwerfen()
        return ergebnis


def zugang_konten_waehlen(dienst, ibans: list[str]) -> dict:
    with _Gesperrt(dienst):
        return _mit_con(dienst, konten_waehlen, ibans, dienst.config)


def _vollstaendig(dienst) -> None:
    if not _mit_con(dienst, lesen, dienst.config)["vollstaendig"]:
        raise ApiFehler(409, "bankzugang_unvollstaendig", "Der Bankzugang ist noch nicht vollständig eingestellt "
                        "(Server-Adresse, Bankleitzahl, Benutzerkennung und Produkt-ID).")


def tan_verfahren(dienst) -> dict:
    """Fragt die Bank nach den erlaubten TAN-Verfahren (nur Synchronisierungsdialog, keine TAN)."""
    with _Gesperrt(dienst):
        _vollstaendig(dienst)
        plugin = dienst._plugin_holen()
        try:
            liste = plugin.tan_verfahren()
        except Exception as e:  # noqa: BLE001 - Pluginfehler führen nie zu 5xx
            code, meldung = dienst._pluginfehler(e)
            raise ApiFehler(409, code, meldung) from None
        return {"verfahren": [{"code": c, "name": n} for c, n in liste]}


def konten_abrufen(dienst, vorgang: str | None, tan: str | None) -> dict:
    """Ruft die Konten bei der Bank ab und speichert sie. Verlangt die Bank eine TAN, enthält die Antwort
    ``tan_erforderlich`` mit einem Vorgang; derselbe Aufruf mit ``vorgang`` und ``tan`` setzt fort."""
    from .plugins.bank import TanAntwort
    with _Gesperrt(dienst):
        _vollstaendig(dienst)
        plugin = dienst._plugin_holen()
        try:
            if vorgang is not None:
                offen = dienst.zugang_tan
                if offen is None or not secrets.compare_digest(offen[0], vorgang) or not tan:
                    raise ApiFehler(409, "tan_nicht_offen", "Die TAN-Anforderung ist nicht mehr offen.")
                bankkonten = plugin.konten(tan=TanAntwort(offen[1], tan))
            else:
                bankkonten = plugin.konten()
        except ApiFehler:
            raise
        except TanErforderlich as e:
            v = secrets.token_urlsafe(16)
            dienst.zugang_tan = (v, str(e.anforderung_id))
            bild = None
            if isinstance(e.bild, (bytes, bytearray)) and e.bild_mime_typ in ("image/png", "image/jpeg", "image/gif"):
                bild = f"data:{e.bild_mime_typ};base64," + base64.b64encode(bytes(e.bild)).decode("ascii")
            return {"konten": None, "tan_erforderlich": {
                "vorgang": v, "challenge": (e.challenge or "").strip() or "Bitte TAN eingeben", "bild": bild}}
        except TanUngueltig:
            raise ApiFehler(422, "tan_ungueltig", "Die TAN wurde von der Bank nicht akzeptiert.") from None
        except TanAbgelaufen:
            dienst.zugang_tan = None
            raise ApiFehler(409, "tan_abgelaufen", "Die TAN-Anforderung ist abgelaufen.") from None
        except Exception as e:  # noqa: BLE001 - Pluginfehler führen nie zu 5xx
            dienst.zugang_tan = None
            code, meldung = dienst._pluginfehler(e)
            raise ApiFehler(409, code, meldung) from None
        dienst.zugang_tan = None
        return {"konten": _mit_con(dienst, konten_uebernehmen, bankkonten), "tan_erforderlich": None}
