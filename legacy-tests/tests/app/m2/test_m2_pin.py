"""M2: PIN nur im Arbeitsspeicher, nie in Logs, Datenbank, Antworten oder Fehlern (synchronisation.md 12, K 6)."""

from __future__ import annotations

import logging

import pytest

from tests.hilfen.api import Api, fehlercode
from tests.hilfen.m2 import (
    SYNC_DATEN_PIN, alle_antworten, benachrichtigungen, db_dateien, lade_sync, mock_config, status, sync,
)

FALSCH = "FALSCH-PIN-0000-SYNTHETISCH"


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def papi(tmp_path):
    return Api(mock_config(tmp_path, daten=SYNC_DATEN_PIN))


def _pin(api, pin):
    return api.put("/api/sync/pin", json={"pin": pin}, erwartet=204)


@pytest.mark.kern
def test_ohne_pin_scheitert_der_lauf(papi, netz_gesperrt):
    lauf = sync(papi, von="2024-01-01")
    assert (lauf["status"], lauf["konten"], lauf["fehler"]["code"]) == ("fehlgeschlagen", [], "bank_pin_fehlt")
    assert benachrichtigungen(papi)[0]["schluessel"] == "sync_fehler:bank_pin_fehlt"
    assert status(papi)["pin_vorhanden"] is False and papi.alle_buchungen() == []


@pytest.mark.kern
def test_pin_eingeben_und_synchronisieren(papi, sd, netz_gesperrt):
    _, erw = sd
    _pin(papi, erw["pin"])
    assert status(papi)["pin_vorhanden"] is True
    lauf = sync(papi, von="2024-01-01")
    assert lauf["status"] == "erfolgreich" and papi.alle_buchungen()
    assert status(papi)["pin_vorhanden"] is True
    papi.delete("/api/sync/pin", erwartet=204)
    papi.delete("/api/sync/pin", erwartet=204)
    assert status(papi)["pin_vorhanden"] is False
    assert sync(papi)["fehler"]["code"] == "bank_pin_fehlt"


@pytest.mark.kern
def test_falsche_pin_wird_verworfen(papi, sd, netz_gesperrt):
    _, erw = sd
    _pin(papi, FALSCH)
    lauf = sync(papi)
    assert (lauf["status"], lauf["fehler"]["code"]) == ("fehlgeschlagen", "bank_pin_falsch")
    assert status(papi)["pin_vorhanden"] is False, "falsche PIN darf nicht erneut verwendet werden"
    assert sync(papi)["fehler"]["code"] == "bank_pin_fehlt"
    _pin(papi, erw["pin"])
    assert sync(papi, von="2024-01-01")["status"] == "erfolgreich"


def test_pin_ueberschreiben(papi, sd, netz_gesperrt):
    _, erw = sd
    _pin(papi, FALSCH)
    _pin(papi, erw["pin"])
    assert sync(papi, von="2024-01-01")["status"] == "erfolgreich"


def test_neustart_vergisst_pin(tmp_path, sd, netz_gesperrt):
    _, erw = sd
    config = mock_config(tmp_path, daten=SYNC_DATEN_PIN)
    a = Api(config)
    _pin(a, erw["pin"])
    b = Api(config)
    assert status(b)["pin_vorhanden"] is False
    assert sync(b)["fehler"]["code"] == "bank_pin_fehlt"


@pytest.mark.parametrize("koerper,geheim", [
    ({"pin": 98765432101}, "98765432101"), ({"pin": ""}, None), ({"pin": "GEHEIM-" + "7" * 130}, "7" * 130),
    ({"pin": "GEHEIM-PIN-UNBEKANNTES-FELD", "x": 1}, "GEHEIM-PIN-UNBEKANNTES-FELD"), ({}, None),
    ({"pin": ["GEHEIM-PIN-IN-LISTE"]}, "GEHEIM-PIN-IN-LISTE"),
], ids=["zahl", "leer", "zu_lang", "feld_unbekannt", "fehlt", "liste"])
def test_validierung_ohne_echo(papi, koerper, geheim, netz_gesperrt):
    r = papi.put("/api/sync/pin", json=koerper, erwartet=422)
    assert fehlercode(r) == "validierung"
    if geheim:
        assert geheim not in r.text, "Validierungsfehler dürfen den übergebenen Wert nicht enthalten"
    assert status(papi)["pin_vorhanden"] is False


@pytest.mark.kern
def test_pin_nirgends_zu_finden(papi, sd, caplog, capfd, netz_gesperrt):
    caplog.set_level(logging.DEBUG)
    _, erw = sd
    antworten = []
    for pin in (FALSCH, erw["pin"]):
        antworten.append(papi.put("/api/sync/pin", json={"pin": pin}, erwartet=204).text)
        antworten.append(papi.post("/api/sync", json={"von": "2024-01-01"}, erwartet=200).text)
    antworten.append(papi.put("/api/sync/pin", json={"pin": erw["pin"], "zuviel": True}, erwartet=422).text)
    antworten.append(alle_antworten(papi))
    raus, err = capfd.readouterr()
    texte = antworten + [caplog.text, raus, err] + [r.getMessage() for r in caplog.records]
    for geheim in (erw["pin"], FALSCH):
        for text in texte:
            assert geheim not in text
        for datei in db_dateien(papi):
            assert geheim.encode() not in datei.read_bytes(), f"PIN in {datei.name}"
        assert all(geheim not in repr(r.args) for r in caplog.records)


def test_pin_im_echtmodus_annehmbar(api, netz_gesperrt):
    api.put("/api/sync/pin", json={"pin": "PIN-ECHTMODUS-ATTRAPPE"}, erwartet=204)
    assert status(api)["pin_vorhanden"] is True
    netz_gesperrt.versuche.clear()
