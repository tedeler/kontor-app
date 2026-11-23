"""M23: Betrieb (LimitCORE), Zurücksetzen des Passworts, Sicherung (geheimnisschutz.md 2.4, 3, 7, 11; E-229)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hilfen.m6 import CLIENT_SECRET, NTFY_TOKEN, geheimnis_setzen
from tests.hilfen.m7 import NEUES_PASSWORT, PASSWORT, anmeldung, betriebsdatei
from tests.hilfen.m9 import einspielen, enthaelt, oeffne, sicherung
from tests.hilfen.m23 import (
    AUS, PIN, einschalten, eintraege, entsperren, m23_mock_api, merken, neustart, pin_vorhanden, schutz,
    sperren,
)
from tests.hilfen.systemd import Unit

pytestmark = pytest.mark.kern

REPO = Path(__file__).resolve().parents[3]


def test_unit_limitcore():
    u = Unit(betriebsdatei("kontor.service"))
    assert u.werte("Service", "LimitCORE") == ["0"]


def _gefuellt(tmp_path) -> object:
    api = m23_mock_api(tmp_path)
    geheimnis_setzen(api, "ntfy_token", NTFY_TOKEN)
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    einschalten(api)
    merken(api)
    return api


def test_passwort_setzen_loescht_geschuetzte(tmp_path, netz_gesperrt):
    api = _gefuellt(tmp_path)
    assert schutz(api)["geschuetzt"] == 2
    anmeldung().passwort_setzen(api.config, NEUES_PASSWORT)
    b = neustart(api)
    assert schutz(b) == AUS
    assert eintraege(b) == {"ntfy_token": True}, "ntfy_token bleibt"
    assert pin_vorhanden(b) is False
    assert schutz(api)["aktiv"] is False, "die laufende Instanz sieht die Wirkung bei der nächsten Anfrage"
    einschalten(b, NEUES_PASSWORT)
    sperren(b)
    entsperren(b, NEUES_PASSWORT)


def _umgebung(config) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("KONTOR_") or k.startswith("KONTOR_TESTS_")
           or k == "KONTOR_MUTANT"}
    env.pop("CREDENTIALS_DIRECTORY", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.environ.get("PYTHONPATH", ""), str(REPO)]))
    env["KONTOR_DATENBANK"] = str(config.datenbank)
    env["KONTOR_MOCK_MODUS"] = "1"
    return env


def test_kommandozeile_meldet_anzahl(tmp_path, netz_gesperrt):
    api = _gefuellt(tmp_path)
    r = subprocess.run([sys.executable, "-m", "kontor.anmeldung", "passwort-setzen"], env=_umgebung(api.config),
                       input=NEUES_PASSWORT + "\n", capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    aus = r.stdout + r.stderr
    assert "2" in aus, "Anzahl der gelöschten Geheimnisse als Hinweis"
    for w in (NEUES_PASSWORT, PIN, CLIENT_SECRET, "oauth_client_secret", "bank_pin"):
        assert w not in aus, w
    b = neustart(api)
    assert schutz(b) == AUS and eintraege(b) == {"ntfy_token": True}
    ohne = _gefuellt(tmp_path / "ohne")
    ohne.post("/api/geheimnisse/schutz/ausschalten", json={"passwort": PASSWORT}, erwartet=200)
    r = subprocess.run([sys.executable, "-m", "kontor.anmeldung", "passwort-setzen"], env=_umgebung(ohne.config),
                       input=NEUES_PASSWORT + "\n", capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    assert eintraege(neustart(ohne)) == {"ntfy_token": True, "oauth_client_secret": True}, "ohne Schutz unverändert"


def test_sicherung_ohne_schutz_und_geheimnisse(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    api.konto("Girokonto")
    m0, _ = oeffne(sicherung(api))
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    einschalten(api)
    merken(api)
    daten = sicherung(api)
    m1, _ = oeffne(daten)
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])
    for w in (PIN, CLIENT_SECRET, PASSWORT):
        assert not enthaelt(daten, w), w
    ziel = m23_mock_api(tmp_path / "ziel")
    einspielen(ziel, daten)
    assert schutz(ziel) == AUS and eintraege(ziel) == {}, "Einspielen bringt weder Schutz noch Geheimnisse"
    zweite = m23_mock_api(tmp_path / "zweite")
    zweite.konto("Sparkonto", "sparkonto")
    b = neustart(api)
    einspielen(b, sicherung(zweite))
    assert {k: schutz(b)[k] for k in ("aktiv", "entsperrt", "gesperrt", "geschuetzt")} == {
        "aktiv": True, "entsperrt": False, "gesperrt": True, "geschuetzt": 2}, "Einspielen ändert den Schutz nicht"
    entsperren(b)
    assert schutz(b) == {"aktiv": True, "entsperrt": True, "gesperrt": False, "geschuetzt": 2, "pin_gemerkt": True}
    assert eintraege(b) == {"bank_pin": True, "oauth_client_secret": True}
