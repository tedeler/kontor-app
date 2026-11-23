"""Hilfen für Meilenstein-23-Tests (Schutz der Geheimnisse, gemerkte PIN, App-Passwort) – nur über die Spezifikation.

``geheimnisschutz.md``; Prüfmerkmale E-229 bis E-231. Die Konfigurationen setzen ``anmeldung`` immer ausdrücklich,
damit der Anmeldelauf (E-125) sie nicht verändert: Die Tests richten das Login-Passwort selbst ein.
"""

from __future__ import annotations

import base64
import json
import secrets
from pathlib import Path

from .api import Api, fehlercode, neue_config
from .m2 import SYNC_DATEN_PIN, mock_config
from .m6 import mail_felder
from .m7 import NEUES_PASSWORT, PASSWORT, anmeldung

FALSCH = "Falsches-Testpasswort-0000"
PIN = json.loads(SYNC_DATEN_PIN.read_text(encoding="utf-8"))["bank"]["pin"]
FALSCHE_PIN = "SYNTH-FALSCHE-PIN-2323"
#: synthetisches App-Passwort in der Schreibweise von Google (Vierergruppen) und ohne Leerraum
APP_PASSWORT = "sytk abcd efgh m23x"
APP_ROH = "sytkabcdefghm23x"
AUS = {"aktiv": False, "entsperrt": False, "gesperrt": False, "geschuetzt": 0, "pin_gemerkt": False}
ENDPUNKTE = ("/api/geheimnisse/schutz", "/api/geheimnisse/schutz/ausschalten", "/api/geheimnisse/entsperren")

__all__ = ["PASSWORT", "NEUES_PASSWORT", "fehlercode"]


# ------------------------------------------------------------------ Konfiguration
def eingerichtet(config, passwort: str = PASSWORT):
    anmeldung().passwort_setzen(config, passwort)
    return config


def m23_mock_config(basis: Path, *, passwort: str | None = PASSWORT, daten: Path | None = SYNC_DATEN_PIN, **felder):
    felder.setdefault("anmeldung", False)
    config = mock_config(basis, daten=daten, **felder)
    return eingerichtet(config, passwort) if passwort else config


def m23_mock_api(basis: Path, **kw) -> Api:
    return Api(m23_mock_config(basis, **kw))


def m23_echt_config(basis: Path, imap=None, *, passwort: str | None = PASSWORT, oauth=None, **felder):
    felder.setdefault("anmeldung", False)
    f = mail_felder(imap, oauth, mail_erstabruf_tage=3650) if (imap is not None or oauth is not None) else {}
    f.update(felder)
    config = neue_config(basis, **f)
    return eingerichtet(config, passwort) if passwort else config


def m23_echt_api(basis: Path, imap=None, **kw) -> Api:
    return Api(m23_echt_config(basis, imap, **kw))


def neustart(api: Api) -> Api:
    """Neue App-Instanz auf derselben Datenbank (geheimnisschutz.md: Neustart)."""
    return Api(api.config)


def schluessel_tauschen(api: Api) -> None:
    """Ersetzt die Schlüsseldatei durch einen anderen gültigen Schlüssel (geheimnisse.md 2)."""
    c = api.config
    datei = c.geheimnis_schluessel_datei or c.aktive_datenbank.with_suffix(".schluessel")
    datei.write_bytes(base64.b64encode(secrets.token_bytes(32)) + b"\n")


# ------------------------------------------------------------------ REST-Kurzformen
def schutz(api: Api) -> dict:
    return api.get("/api/geheimnisse/schutz", erwartet=200).daten


def einschalten(api: Api, passwort: str = PASSWORT, erwartet=200):
    return api.post("/api/geheimnisse/schutz", json={"passwort": passwort}, erwartet=erwartet)


def ausschalten(api: Api, passwort: str = PASSWORT, erwartet=200):
    return api.post("/api/geheimnisse/schutz/ausschalten", json={"passwort": passwort}, erwartet=erwartet)


def entsperren(api: Api, passwort: str = PASSWORT, erwartet=200):
    return api.post("/api/geheimnisse/entsperren", json={"passwort": passwort}, erwartet=erwartet)


def sperren(api: Api) -> dict:
    return api.post("/api/geheimnisse/sperren", erwartet=200).daten


def merken(api: Api, pin: str = PIN, erwartet=204):
    return api.put("/api/sync/pin/gemerkt", json={"pin": pin}, erwartet=erwartet)


def eintraege(api: Api) -> dict[str, bool]:
    """Name → lesbar aus ``GET /api/geheimnisse``."""
    return {e["name"]: e["lesbar"] for e in api.get("/api/geheimnisse", erwartet=200).daten["eintraege"]}


def pin_vorhanden(api: Api) -> bool:
    return api.get("/api/sync/status", erwartet=200).daten["pin_vorhanden"]


def lauf(api: Api) -> dict:
    return api.post("/api/sync", json={"von": "2024-01-01"}, erwartet=200).daten


def app_passwort(api: Api, pid: int, passwort: str = APP_PASSWORT, erwartet=200):
    return api.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": passwort}, erwartet=erwartet)


def code(r) -> str:
    return fehlercode(r)
