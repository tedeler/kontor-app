"""M31: Monatsbericht und weitere Berichte (berichte.md 6; E-282) – REST, kern.

Kleiner Bestand mit eigener Rechnung: feste Miete als Serie, Einkäufe, Erstattung, Gehalt, Umbuchung,
Kreditrate (nur der Zinsanteil zählt), Zinsbuchung auf dem Darlehenskonto, Anfangsbestand (neutral).
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m9 import oeffne, sicherung
from tests.hilfen.m31 import BERICHTE, monat

pytestmark = pytest.mark.kern


@pytest.fixture
def bestand(api):
    k = {"giro": api.konto("Girokonto", "girokonto")["id"], "spar": api.konto("Tagesgeld", "sparkonto")["id"],
         "darlehen": api.konto("Darlehen Fiktiv", "kreditkonto")["id"],
         "miete": api.konto("Miete", "aufwand")["id"], "leb": api.konto("Lebensmittel", "aufwand")["id"],
         "zins": api.konto("Zinsen", "aufwand")["id"], "gehalt": api.konto("Gehalt", "ertrag")["id"],
         "ek": api.konto("Anfangsbestand", "eigenkapital")["id"]}
    api.post("/api/kredite", json={
        "name": "Darlehen Fiktiv", "konto_id": k["darlehen"], "zahlungskonto_id": k["giro"],
        "zins_konto_id": k["zins"], "restschuld": 1_000_000, "stand_datum": "2025-01-15", "sollzins": 36_000,
        "rate": 50_000, "erste_faelligkeit": "2025-02-01",
        "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktivbank AG"}]}, erwartet=201)
    e = {n: api.empfaenger(n)["id"] for n in ("Vermieter Fiktiv", "Supermarkt Fiktiv", "Bäckerei Fiktiv",
                                               "Arbeitgeber Fiktiv", "Fiktivbank AG")}
    for m in ("2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"):
        api.buchung(f"{m}-01", [(k["giro"], -80000), (k["miete"], 80000)], empfaenger_id=e["Vermieter Fiktiv"],
                    verwendungszweck="Miete")
    api.buchung("2026-04-10", [(k["giro"], 50000), (k["ek"], -50000)], verwendungszweck="Anfangsbestand")
    api.buchung("2026-05-06", [(k["giro"], -4550), (k["leb"], 4550)], empfaenger_id=e["Supermarkt Fiktiv"])
    api.buchung("2026-05-13", [(k["giro"], -1230), (k["leb"], 1230)], empfaenger_id=e["Bäckerei Fiktiv"])
    api.buchung("2026-05-14", [(k["giro"], 1000), (k["leb"], -1000)], empfaenger_id=e["Supermarkt Fiktiv"],
                verwendungszweck="Erstattung")
    api.buchung("2026-05-28", [(k["giro"], 300000), (k["gehalt"], -300000)], empfaenger_id=e["Arbeitgeber Fiktiv"])
    api.buchung("2026-05-20", [(k["giro"], -10000), (k["spar"], 10000)], verwendungszweck="Sparen")
    api.buchung("2026-05-02", [(k["giro"], -50000), (k["darlehen"], 48000), (k["zins"], 2000)],
                empfaenger_id=e["Fiktivbank AG"], verwendungszweck="Rate")
    api.buchung("2026-05-31", [(k["darlehen"], -700), (k["zins"], 700)], verwendungszweck="Zinsbelastung")
    api.buchung("2026-06-03", [(k["giro"], -999), (k["leb"], 999)], empfaenger_id=e["Supermarkt Fiktiv"])
    return api, k


def test_monatsbericht_mit_vorgabekonten(bestand):
    api, k = bestand
    m = monat(api, monat="2026-05")
    assert m["monat"] == "2026-05"
    assert m["konto_ids"] == sorted([k["giro"], k["spar"]]), "Bestandskonten ohne Darlehenskonto"
    assert m["ausgaben"] == 80000 + 4550 + 1230 - 1000 + 2000, "Erstattung mindert, von der Rate nur der Zins"
    assert m["einnahmen"] == 300000
    assert m["umbuchungen"] == 1
    assert (m["fest"], m["variabel"]) == (80000, m["ausgaben"] - 80000), "Miete als Serie ist fest"


def test_monatsbericht_mit_auswahl(bestand):
    api, k = bestand
    m = monat(api, monat="2026-05", konto_id=[k["darlehen"], k["giro"]])
    assert m["konto_ids"] == sorted([k["giro"], k["darlehen"]])
    assert m["ausgaben"] == 80000 + 4550 + 1230 - 1000 + 2000 + 700, "Zinsbelastung des Darlehenskontos zählt"
    nur = monat(api, monat="2026-05", konto_id=k["spar"])
    assert (nur["konto_ids"], nur["ausgaben"], nur["einnahmen"], nur["umbuchungen"]) == ([k["spar"]], 0, 0, 1)


def test_anfangsbestand_ist_keine_einnahme(bestand):
    api, k = bestand
    m = monat(api, monat="2026-04")
    assert (m["einnahmen"], m["ausgaben"], m["fest"]) == (0, 80000, 80000)
    leer = monat(api, monat="2024-01")
    assert (leer["ausgaben"], leer["einnahmen"], leer["umbuchungen"], leer["fest"], leer["variabel"]) == (0,) * 5


def test_vorgabe_laufender_monat(api):
    assert monat(api)["monat"] == dt.date.today().isoformat()[:7]


@pytest.mark.parametrize("params,code", [
    ({"monat": "2026-5"}, "validierung"), ({"monat": "2026-13"}, "validierung"), ({"monat": "Mai"}, "validierung"),
    ({"monat": "2026-05-01"}, "validierung"), ({"konto_id": "x"}, "validierung"), ({"unbekannt": "1"}, "validierung"),
    ({"konto_id": 999999}, "referenz_unbekannt"), ("aufwand", "konto_ungueltig")])
def test_monatsbericht_fehler(bestand, params, code):
    api, k = bestand
    if params == "aufwand":
        params = {"konto_id": k["miete"]}
    r = monat(api, erwartet=422, **params)
    assert fehlercode(r) == code
    if code == "referenz_unbekannt":
        assert r.json()["fehler"]["details"]["konto_ids"] == [999999]


@pytest.mark.parametrize("name", BERICHTE)
def test_weitere_berichte_lesend(bestand, name):
    api, k = bestand
    a0 = letzte_aenderung_id(api)
    m0, _ = oeffne(sicherung(api))
    assert isinstance(api.get(f"/api/berichte/{name}", erwartet=200).daten, dict)
    assert fehlercode(api.get(f"/api/berichte/{name}", params={"unbekannt_xyz": "1"}, erwartet=422)) == "validierung"
    assert aenderungen_seit(api, a0) == []
    m1, _ = oeffne(sicherung(api))
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])


@pytest.mark.parametrize("name", BERICHTE)
def test_weitere_berichte_ohne_buchungen(api, name):
    assert isinstance(api.get(f"/api/berichte/{name}", erwartet=200).daten, dict)


def test_monatsbericht_lesend(bestand):
    api, k = bestand
    a0 = letzte_aenderung_id(api)
    monat(api, monat="2026-05")
    assert aenderungen_seit(api, a0) == []
