"""M27: Dubletten anlegen und vorschlagen (sammel.md 4, protokoll.md 21; E-249, E-250) – REST, kern."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m2 import setze_zeit
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import pruefe_eintraege
from tests.hilfen.m27 import bestand, dubletten, kontoarten, vorschlaege_soll

pytestmark = pytest.mark.kern


@pytest.fixture
def api(tmp_path):
    a = neue_api(tmp_path, mock_modus=True)
    a.g = a.konto("Girokonto")["id"]
    a.s = a.konto("Tagesgeld", "sparkonto")["id"]
    a.leb = a.konto("Lebensmittel", "aufwand")["id"]
    return a


def _b(api, datum, betrag, eid=None, konto=None):
    felder = {"empfaenger_id": eid} if eid else {}
    return api.buchung(datum, [(konto or api.g, betrag), (api.leb, -betrag)], **felder)["id"]


def _anlegen(api, ids, erwartet=201):
    return api.post("/api/dubletten", json={"buchung_ids": ids}, erwartet=erwartet)


# ------------------------------------------------------------------ 4.1 Anlegen


def test_anlegen_felder_protokoll_rueckgaengig(api):
    setze_zeit(api, "2024-06-05T10:00:00Z")
    a, b, c = (_b(api, "2024-06-01", -100 * i) for i in (1, 2, 3))
    v, a0 = bestand(api), letzte_aenderung_id(api)
    d = _anlegen(api, [c, a]).daten
    assert {k: d[k] for k in ("buchung_id", "kandidat_ids", "grund", "status", "erstellt_am")} == {
        "buchung_id": c, "kandidat_ids": [a], "grund": "aehnlich", "status": "offen",
        "erstellt_am": "2024-06-05T10:00:00Z"}
    assert d in dubletten(api)
    neu = aenderungen_seit(api, a0)
    assert [(x["quelle"], x["aktion"], x["gruppe"]) for x in neu] == [("manuell", "dublette_anlegen", None)]
    assert [(e["objekt"], e["objekt_id"], e["art"]) for e in neu[0]["eintraege"]] == [("verdacht", d["id"], "angelegt")]
    n = bestand(api)
    pruefe_eintraege(neu[0], v, n)
    u = api.post(f"/api/aenderungen/{neu[0]['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == v and d not in dubletten(api)
    pruefe_eintraege(u, n, v)
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == n
    # mehrdeutig bei mehr als zwei, Kandidaten aufsteigend
    d3 = _anlegen(api, [b, c, a]).daten
    assert (d3["buchung_id"], d3["kandidat_ids"], d3["grund"]) == (b, [a, c], "mehrdeutig")


def test_anlegen_immer_auch_bei_bestehendem_verdacht(api):
    a, b = _b(api, "2024-06-01", -100), _b(api, "2024-06-01", -100)
    d1, d2 = _anlegen(api, [a, b]).daten, _anlegen(api, [a, b]).daten
    assert d1["id"] != d2["id"]


def test_rueckgaengig_nach_aufloesen_konflikt(api):
    a, b = _b(api, "2024-06-01", -100), _b(api, "2024-06-01", -100)
    a0 = letzte_aenderung_id(api)
    d = _anlegen(api, [a, b]).daten
    (anlegen,) = aenderungen_seit(api, a0)
    api.post(f"/api/dubletten/{d['id']}/aufloesen", json={"entscheidung": "keine_dublette"}, erwartet=200)
    assert fehlercode(api.post(f"/api/aenderungen/{anlegen['id']}/rueckgaengig", erwartet=409)) == \
        "rueckgaengig_konflikt"


def test_zusammenfuehren_entfernt_erste(api):
    a, b = _b(api, "2024-06-01", -100), _b(api, "2024-06-01", -100)
    d = _anlegen(api, [a, b]).daten
    api.post(f"/api/dubletten/{d['id']}/aufloesen", json={"entscheidung": "zusammenfuehren", "behalten_id": b},
             erwartet=200)
    assert api.get(f"/api/buchungen/{a}").status_code == 404
    assert api.get(f"/api/buchungen/{b}").status_code == 200


@pytest.mark.parametrize("body", [{}, {"buchung_ids": [1]}, {"buchung_ids": [1, 1]}, {"buchung_ids": "1,2"},
                                  {"buchung_ids": list(range(1, 52))}, {"buchung_ids": [1, 2], "x": 1},
                                  {"buchung_ids": [1, 2.5]}, {"buchung_ids": None}])
def test_validierung(api, body):
    _b(api, "2024-06-01", -1)
    _b(api, "2024-06-01", -2)
    a0 = letzte_aenderung_id(api)
    assert fehlercode(api.post("/api/dubletten", json=body, erwartet=422)) == "validierung"
    assert aenderungen_seit(api, a0) == []


def test_unbekannte_buchungen(api):
    a = _b(api, "2024-06-01", -1)
    r = _anlegen(api, [999999, a, 999998], erwartet=422)
    assert fehlercode(r) == "referenz_unbekannt"
    assert r.json()["fehler"]["details"] == {"buchung_ids": [999998, 999999]}
    assert dubletten(api) == []


# ------------------------------------------------------------------ 4.2 Vorschläge


def _pruefe_vorschlaege(api, **params):
    verdachte = dubletten(api)
    liste = dubletten(api, vorschlaege="ja", **params)
    gespeichert = dubletten(api, **params)
    assert liste[:len(gespeichert)] == gespeichert, "gespeicherte Verdachte zuerst, unverändert"
    soll = vorschlaege_soll(api.alle_buchungen(), kontoarten(api), verdachte)
    assert liste[len(gespeichert):] == soll
    return soll


def test_vorschlaege_regel(api):
    e1, e2 = api.empfaenger("Laden (fiktiv)")["id"], api.empfaenger("Kiosk (fiktiv)")["id"]
    a = [_b(api, "2024-06-01", -500, e1) for _ in range(3)]          # Dreiergruppe
    _b(api, "2024-06-01", 500, e1)                                    # anderes Vorzeichen
    _b(api, "2024-06-02", -500, e1)                                   # anderes Datum
    _b(api, "2024-06-01", -500, e2)                                   # anderer Empfänger
    _b(api, "2024-06-01", -500)                                       # ohne Empfänger
    _b(api, "2024-06-01", -500)
    s1 = _b(api, "2024-06-01", -500, e2, konto=api.s)                 # Spargruppe zu e2: gleicher Zahlungsbetrag
    assert dubletten(api) == [] and dubletten(api, vorschlaege="nein") == []
    soll = _pruefe_vorschlaege(api)
    assert {"buchung_id": a[0], "kandidat_ids": a[1:]}.items() <= soll[0].items()
    assert len(soll) == 2, "Dreiergruppe von e1 und Paar von e2 (Konto egal)"
    assert soll[1]["kandidat_ids"] == [s1]
    # ein Paar bewertet → je unbewertetem Paar ein Vorschlag
    a0 = letzte_aenderung_id(api)
    d = _anlegen(api, [a[0], a[1]]).daten
    assert aenderungen_seit(api, a0)[0]["aktion"] == "dublette_anlegen"
    soll = _pruefe_vorschlaege(api)
    paare = [(v["buchung_id"], v["kandidat_ids"]) for v in soll]
    assert (a[0], [a[2]]) in paare and (a[1], [a[2]]) in paare and (a[0], [a[1]]) not in paare
    # aufgelöst zählt weiter als bewertet; status-Filter
    api.post(f"/api/dubletten/{d['id']}/aufloesen", json={"entscheidung": "keine_dublette"}, erwartet=200)
    _pruefe_vorschlaege(api)
    _pruefe_vorschlaege(api, status="offen")
    for s in ("zusammengefuehrt", "keine_dublette"):
        assert dubletten(api, vorschlaege="ja", status=s) == dubletten(api, status=s), "keine Vorschläge"
    # alle Paare bewertet → nichts
    _anlegen(api, [a[0], a[2], a[1]])
    paare = [(v["buchung_id"], v["kandidat_ids"]) for v in _pruefe_vorschlaege(api)]
    assert not any(p[0] in a for p in paare)


def test_vorschlaege_ohne_wirkung_und_parameter(api):
    e = api.empfaenger("Doppelt (fiktiv)")["id"]
    _b(api, "2024-06-01", -700, e)
    _b(api, "2024-06-01", -700, e)
    v, a0 = bestand(api), letzte_aenderung_id(api)
    assert len(dubletten(api, vorschlaege="ja")) == 1
    assert bestand(api) == v and aenderungen_seit(api, a0) == []
    for wert in ("JA", "true", "1", ""):
        assert fehlercode(dubletten(api, erwartet=422, vorschlaege=wert)) == "validierung"
