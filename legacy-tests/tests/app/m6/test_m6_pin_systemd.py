"""M6: PIN über systemd-creds aus ``$CREDENTIALS_DIRECTORY`` (fints.md 5, synchronisation.md 18.1, E-115)."""

from __future__ import annotations

import logging

import pytest

from tests.hilfen.api import Api, fehlercode
from tests.hilfen.m2 import SYNC_DATEN_PIN, db_dateien, lade_sync, mock_config, status

FALSCH = "SYNTH-FALSCHE-PIN-0815"


@pytest.fixture(scope="module")
def pin():
    return lade_sync()[1]["pin"]


def _app(tmp_path, inhalt: str | None, **felder):
    creds = tmp_path / "creds"
    creds.mkdir(exist_ok=True)
    if inhalt is not None:
        (creds / "kontor-bank-pin").write_text(inhalt, encoding="utf-8")
    config = mock_config(tmp_path, daten=SYNC_DATEN_PIN, bank_pin_quelle="systemd-creds", credentials_verzeichnis=creds,
                         **felder)
    return Api(config), creds


def _sync(api):
    return api.post("/api/sync", json={"von": "2024-01-01"}, erwartet=200).daten


@pytest.mark.kern
@pytest.mark.parametrize("ende", ["\n", "\r\n", ""])
def test_pin_aus_datei(tmp_path, pin, ende, netz_gesperrt):
    api, _ = _app(tmp_path, pin + ende)
    s = status(api)
    assert (s["pin_quelle"], s["pin_vorhanden"]) == ("systemd-creds", True)
    assert _sync(api)["status"] == "erfolgreich" and api.alle_buchungen()


@pytest.mark.kern
def test_nur_ein_zeilenumbruch_entfernt(tmp_path, pin, netz_gesperrt):
    api, _ = _app(tmp_path, pin + "\n\n")
    assert _sync(api)["fehler"]["code"] == "bank_pin_falsch"


@pytest.mark.kern
@pytest.mark.parametrize("inhalt", [None, "", "\n"])
def test_datei_fehlt_oder_leer(tmp_path, inhalt, netz_gesperrt):
    api, _ = _app(tmp_path, inhalt)
    assert status(api)["pin_vorhanden"] is False
    lauf = _sync(api)
    assert (lauf["status"], lauf["fehler"]["code"]) == ("fehlgeschlagen", "bank_pin_fehlt")


@pytest.mark.kern
def test_datei_wird_bei_bedarf_gelesen(tmp_path, pin, netz_gesperrt):
    api, creds = _app(tmp_path, None)
    assert _sync(api)["fehler"]["code"] == "bank_pin_fehlt"
    (creds / "kontor-bank-pin").write_text(pin, encoding="utf-8")
    assert status(api)["pin_vorhanden"] is True
    assert _sync(api)["status"] == "erfolgreich"


@pytest.mark.kern
def test_falsche_pin_sperrt_bis_zum_neustart(tmp_path, pin, netz_gesperrt):
    api, creds = _app(tmp_path, FALSCH)
    assert _sync(api)["fehler"]["code"] == "bank_pin_falsch"
    (creds / "kontor-bank-pin").write_text(pin, encoding="utf-8")
    assert status(api)["pin_vorhanden"] is False, "kein erneuter Versuch mit der Quelle bis zum Neustart"
    assert _sync(api)["fehler"]["code"] == "bank_pin_fehlt"
    neu = Api(api.config)
    assert status(neu)["pin_vorhanden"] is True and _sync(neu)["status"] == "erfolgreich"


@pytest.mark.kern
@pytest.mark.parametrize("methode,koerper", [("PUT", {"pin": "SYNTH-EINGABE-PIN"}), ("PUT", {"pin": 12}),
                                             ("PUT", {"x": "SYNTH-UNBEKANNT"}), ("DELETE", None)])
def test_eingabe_gesperrt(tmp_path, pin, methode, koerper, netz_gesperrt):
    api, _ = _app(tmp_path, pin)
    r = api.anfrage(methode, "/api/sync/pin", json=koerper, erwartet=409)
    assert fehlercode(r) == "pin_quelle_systemd"
    assert "SYNTH-EINGABE-PIN" not in r.text and "SYNTH-UNBEKANNT" not in r.text
    assert status(api)["pin_vorhanden"] is True


@pytest.mark.kern
def test_vorgabe_eingabe(mock_api):
    assert status(mock_api)["pin_quelle"] == "eingabe"


@pytest.mark.kern
def test_pin_nirgends(tmp_path, pin, caplog, capfd, netz_gesperrt):
    caplog.set_level(logging.DEBUG)
    api, _ = _app(tmp_path, pin + "\n")
    _sync(api)
    raus, err = capfd.readouterr()
    texte = [caplog.text, raus, err, api.get("/api/sync/status", erwartet=200).text,
             api.get("/api/sync/laeufe", erwartet=200).text, api.get("/api/benachrichtigungen", erwartet=200).text]
    assert all(pin not in t for t in texte)
    for d in db_dateien(api):
        assert pin.encode() not in d.read_bytes()
