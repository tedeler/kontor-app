"""M16: Begründung je Buchung ``GET /api/buchungen/{id}/wiederkehrend`` (wiederkehrend.md 8; Definition M16
Abschnitt 2; E-195).

Erwartungen aus ``tests/hilfen/m16.erwartung`` (unabhängige Referenz der Kette) und handgerechnet; Texte nur als
nicht leer geprüft.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import wiederkehrend_orakel as wo
from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m5 import Kreditbuch, WIEDER_MOCK, lade_wiederkehrend, mock_api, sync
from tests.hilfen.m16 import (Abo, begruendung, begruendung_api, eintrag, kredite, pruefe_begruendung, pruefe_texte,
                              uebersicht)

STICHTAG = "2024-12-31"


def _serie_abo(api):
    a = Abo(api)
    e = a.empfaenger("Fiktiv-Stream GmbH")
    ids = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15"], -1_299)
    return a, e, ids


# ------------------------------------------------------------------ Fehlerfälle und Stichtag
@pytest.mark.kern
def test_unbekannte_buchung_404(api):
    _, _, ids = _serie_abo(api)
    r = begruendung_api(api, max(ids) + 1000, "2024-04-30", erwartet=404)
    assert fehlercode(r) == "nicht_gefunden"


@pytest.mark.kern
@pytest.mark.parametrize("params", [{"stichtag": "2024-02-30"}, {"stichtag": "morgen"}, {"stichtag": ""},
                                    {"stichtag": "2024-04-30", "rhythmus": "monatlich"}, {"tag": "2024-04-30"}])
def test_ungueltige_parameter_422(api, params):
    _, _, ids = _serie_abo(api)
    r = api.get(f"/api/buchungen/{ids[0]}/wiederkehrend", params=params, erwartet=422)
    assert fehlercode(r) == "validierung"


@pytest.mark.kern
def test_vorgabe_stichtag_heute_und_kein_protokoll(tmp_path):
    api = neue_api(tmp_path, mock_modus=True, mock_heute=dt.date(2024, 4, 20))
    _, _, ids = _serie_abo(api)
    a0 = letzte_aenderung_id(api)
    vorher = api.alle_buchungen()
    r = begruendung(api, ids[-1])
    assert r["stichtag"] == "2024-04-20" and r["buchung_id"] == ids[-1]
    assert r == begruendung(api, ids[-1], "2024-04-20")
    pruefe_begruendung(api, ids[-1], "2024-04-20")
    assert letzte_aenderung_id(api) == a0, "die Begründung erzeugt keine Änderung im Protokoll"
    assert api.alle_buchungen() == vorher


@pytest.mark.kern
def test_stichtag_filtert_spaetere_buchungen(api):
    a, e, ids = _serie_abo(api)
    r = pruefe_begruendung(api, ids[3], "2024-04-14")
    assert r["urteil"] == "ausgeschlossen" and r["eintraege"] == [], "nach dem Stichtag"
    r = pruefe_begruendung(api, ids[2], "2024-04-14")
    x = eintrag(r)
    assert (x["gruppe_anzahl"], x["juengste"]["buchung_id"], x["serie"]["buchung_ids"]) == (3, ids[2], ids[:3])
    assert x["serie"]["status"] == "aktiv" and r["stichtag"] == "2024-04-14"
    r = pruefe_begruendung(api, ids[1], "2024-03-01")
    assert r["urteil"] == "nicht_wiederkehrend" and eintrag(r)["urteil"] == "keine_serie"


# ------------------------------------------------------------------ Urteile und Rollen
@pytest.mark.kern
def test_urteile_und_rollen(api):
    a = Abo(api)
    e = a.empfaenger()
    # vor_beginn (15.01.), Lücke, Glieder 15.03.–15.05., zusätzlich am 16.05. (anderer Betrag)
    i = a.buchen(e, ["2024-01-15", "2024-03-15", "2024-04-15", "2024-05-15", "2024-05-16"], [-999] * 4 + [-50])
    r = {b: pruefe_begruendung(api, b, "2024-05-31") for b in i}
    assert [r[b]["urteil"] for b in i] == ["nicht_wiederkehrend", "wiederkehrend", "wiederkehrend",
                                          "wiederkehrend", "zusaetzlich"]
    assert [(eintrag(r[b])["urteil"], eintrag(r[b])["glied"]) for b in i] == [
        ("vor_beginn", None), ("glied", 1), ("glied", 2), ("glied", 3), ("zusaetzlich", None)]
    assert eintrag(r[i[0]])["buchungen"] == [
        {"buchung_id": i[4], "datum": "2024-05-16", "betrag": -50, "rolle": "zusaetzlich", "glied": None},
        {"buchung_id": i[3], "datum": "2024-05-15", "betrag": -999, "rolle": "glied", "glied": 3},
        {"buchung_id": i[2], "datum": "2024-04-15", "betrag": -999, "rolle": "glied", "glied": 2},
        {"buchung_id": i[1], "datum": "2024-03-15", "betrag": -999, "rolle": "glied", "glied": 1},
        {"buchung_id": i[0], "datum": "2024-01-15", "betrag": -999, "rolle": "vor_beginn", "glied": None}]
    x = eintrag(r[i[0]])
    assert (x["konto"], x["richtung"], x["datum"], x["betrag"]) == (
        {"id": a.giro, "name": "Girokonto"}, "ausgabe", "2024-01-15", -999)
    assert [s["ergebnis"] for s in x["rhythmen"][0]["schritte"]] == ["anker", "verbunden", "verbunden", "bruch"]


@pytest.mark.kern
def test_einnahme_und_umbuchung_mit_zwei_eintraegen(api):
    a = Abo(api)
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    e = a.empfaenger("Erika Mustermann (fiktiv)")
    ids = [api.buchung(t, [(a.giro, -2_500), (spar, 2_500)], empfaenger_id=e)["id"]
           for t in ("2024-01-01", "2024-02-01", "2024-03-01")]
    r = pruefe_begruendung(api, ids[2], "2024-03-31")
    assert r["urteil"] == "wiederkehrend"
    assert [(x["konto"]["id"], x["richtung"], x["betrag"], x["urteil"]) for x in r["eintraege"]] == sorted(
        [(a.giro, "ausgabe", -2_500, "glied"), (spar, "einnahme", 2_500, "glied")])
    assert r["ausgeschlossen"] == []
    serien = {(s["konto_id"], s["richtung"]): s for s in uebersicht(api, "2024-03-31")["serien"]}
    for x in r["eintraege"]:
        assert x["serie"] == serien[(x["konto"]["id"], x["richtung"])]


# ------------------------------------------------------------------ ausgeschlossen
@pytest.mark.kern
def test_ausgeschlossen_ohne_empfaenger(api):
    a = Abo(api)
    ids = a.buchen(None, ["2024-01-15", "2024-02-15", "2024-03-15"])
    r = begruendung(api, ids[2], "2024-03-31")
    pruefe_texte(r)
    assert (r["urteil"], r["eintraege"]) == ("ausgeschlossen", [])


@pytest.mark.kern
def test_ausgeschlossen_summe_null_und_nur_kategorien(api):
    a = Abo(api)
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    e = a.empfaenger()
    null = api.buchung("2024-03-01", [(a.giro, -100), (a.giro, 100)], empfaenger_id=e)["id"]
    r = pruefe_begruendung(api, null, "2024-03-31")
    assert r["urteil"] == "ausgeschlossen" and r["eintraege"] == []
    assert [(x["konto"], x["grund"]) for x in r["ausgeschlossen"]] == [({"id": a.giro, "name": "Girokonto"},
                                                                         "summe_null")]
    teil = api.buchung("2024-03-02", [(a.giro, -100), (a.giro, 100), (spar, -40), (a.kat, 40)], empfaenger_id=e)["id"]
    r = pruefe_begruendung(api, teil, "2024-03-31")
    assert r["urteil"] == "nicht_wiederkehrend"
    assert [x["konto"]["id"] for x in r["eintraege"]] == [spar]
    assert [(x["konto"]["id"], x["grund"]) for x in r["ausgeschlossen"]] == [(a.giro, "summe_null")]
    kat2 = api.konto("Sonstiges", "aufwand")["id"]
    nur = api.buchung("2024-03-03", [(a.kat, -100), (kat2, 100)], empfaenger_id=e)["id"]
    r = pruefe_begruendung(api, nur, "2024-03-31")
    assert (r["urteil"], r["eintraege"], r["ausgeschlossen"]) == ("ausgeschlossen", [], [])


@pytest.mark.kern
def test_ausgeschlossen_darlehenskonto(api):
    kb = Kreditbuch(api)
    ids = []
    for t in ("2024-02-01", "2024-03-01", "2024-04-01"):
        ids.append(api.buchung(t, [(kb.giro, -50_000), (kb.zinsen, 3_000), (kb.darlehen, 47_000)],
                               empfaenger_id=kb.bank)["id"])
    kb.anlegen(saldo_angleichen=False)
    r = pruefe_begruendung(api, ids[2], "2024-04-30")
    assert r["urteil"] == "wiederkehrend"
    assert [x["konto"]["id"] for x in r["eintraege"]] == [kb.giro]
    assert [(x["konto"]["id"], x["grund"]) for x in r["ausgeschlossen"]] == [(kb.darlehen, "darlehenskonto")]
    nur = api.buchung("2024-04-15", [(kb.darlehen, -100), (kb.zinsen, 100)], empfaenger_id=kb.bank)["id"]
    r = pruefe_begruendung(api, nur, "2024-04-30")
    assert r["urteil"] == "ausgeschlossen" and r["eintraege"] == []
    assert [(x["konto"]["id"], x["grund"]) for x in r["ausgeschlossen"]] == [(kb.darlehen, "darlehenskonto")]


# ------------------------------------------------------------------ Übereinstimmung mit der Übersicht
@pytest.fixture(scope="module")
def voll(tmp_path_factory):
    """Nur lesend: Mock-Datensatz M5 (Abos, Daueraufträge, Lastschriften, Supermarkt, Lücken)."""
    _, erw = lade_wiederkehrend()
    api = mock_api(tmp_path_factory.mktemp("m16voll"), WIEDER_MOCK, "2025-01-15")
    sync(api, von=erw["von"], bis=erw["bis"])
    return api


@pytest.mark.kern
@pytest.mark.parametrize("stichtag", ["2023-03-31", "2024-07-20", "2024-12-31"])
def test_begruendung_stimmt_mit_uebersicht_ueberein(voll, stichtag):
    """Definition 2.1: dieselben Einträge und dieselbe Erkennung wie GET /api/wiederkehrend; je Gruppe die erste
    und jüngste Buchung sowie jede zehnte gegen die Referenz, alle gegen die Übersicht."""
    buchungen, konten = voll.alle_buchungen(), voll.konten()
    serien = {s["schluessel"]: s for s in uebersicht(voll, stichtag)["serien"]}
    assert uebersicht(voll, stichtag) == wo.uebersicht(buchungen, konten, [], stichtag)
    gruppen = wo.gruppen(wo.eintraege([b for b in buchungen if b["datum"] <= stichtag], konten, []))
    for (k, emp, richtung), g in gruppen.items():
        schl = f"{k}:{emp}:{richtung}"
        auswahl = {g[0]["buchung_id"], g[-1]["buchung_id"], *(x["buchung_id"] for x in g[::10])}
        for bid in sorted(auswahl):
            r = pruefe_begruendung(voll, bid, stichtag)
            x = eintrag(r, k)
            assert x["serie"] == serien.get(schl)
            assert (x["urteil"] == "glied") == (schl in serien and bid in serien[schl]["buchung_ids"])
    nach = [b for b in buchungen if b["datum"] > stichtag]
    if nach:
        assert begruendung(voll, nach[0]["id"], stichtag)["urteil"] == "ausgeschlossen"


@pytest.mark.kern
def test_kredite_der_referenz_werden_beruecksichtigt(api):
    """Hilfsprüfung: ohne Kredit ist das Darlehenskonto ein gewöhnliches Bestandskonto (2.1)."""
    kb = Kreditbuch(api)
    b = api.buchung("2024-02-01", [(kb.giro, -50_000), (kb.zinsen, 3_000), (kb.darlehen, 47_000)],
                    empfaenger_id=kb.bank)["id"]
    assert kredite(api) == []
    r = pruefe_begruendung(api, b, "2024-02-29")
    assert [x["konto"]["id"] for x in r["eintraege"]] == sorted([kb.giro, kb.darlehen])
