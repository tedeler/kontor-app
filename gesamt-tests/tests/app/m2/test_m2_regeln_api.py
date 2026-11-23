"""M2: Regeln – CRUD, Validierung, Reihenfolge, Vorgabepriorität, Bezüge (kategorisierung.md 1, 2)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode


def _iban(n: int) -> str:
    from generator.iban import fiktive_iban
    return fiktive_iban(n)


@pytest.fixture
def k(api):
    """Konten und Kategorien für Regeltests."""
    return {
        "giro": api.konto("Giro", iban=_iban(5101)),
        "spar": api.konto("Spar", "sparkonto", iban=_iban(5102)),
        "lebensmittel": api.konto("Lebensmittel", "aufwand"),
        "gehalt": api.konto("Gehalt", "ertrag"),
        "eigen": api.konto("Eigenkapital", "eigenkapital"),
    }


def _regel(kat_id, **felder):
    return {"name": "Supermarkt", "kategorie_id": kat_id,
            "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"}], **felder}


@pytest.mark.kern
def test_anlegen_lesen_vorgaben(api, k):
    r = api.post("/api/regeln", json=_regel(k["lebensmittel"]["id"], name="  Supermarkt  "), erwartet=201).daten
    assert r == {"id": r["id"], "name": "Supermarkt", "aktiv": True, "prioritaet": 100,
                 "kategorie_id": k["lebensmittel"]["id"],
                 "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"}]}
    assert api.get(f"/api/regeln/{r['id']}", erwartet=200).daten == r
    r2 = api.post("/api/regeln", json=_regel(k["gehalt"]["id"], prioritaet=7), erwartet=201).daten
    r3 = api.post("/api/regeln", json=_regel(k["gehalt"]["id"]), erwartet=201).daten
    assert (r2["prioritaet"], r3["prioritaet"]) == (7, 110), "Vorgabe: größte Priorität + 10"
    r4 = api.post("/api/regeln", json=_regel(k["gehalt"]["id"], prioritaet=1000000, aktiv=False), erwartet=201).daten
    assert r4["aktiv"] is False and r4["prioritaet"] == 1000000
    r5 = api.post("/api/regeln", json=_regel(k["gehalt"]["id"], prioritaet=0), erwartet=201).daten
    assert r5["prioritaet"] == 0
    assert r["id"] < r2["id"] < r3["id"] < r4["id"] < r5["id"]


@pytest.mark.kern
def test_reihenfolge_prioritaet_dann_id(api, k):
    ids = {}
    for name, p in [("c", 50), ("a", 10), ("b", 50), ("d", 10), ("e", 0)]:
        ids[name] = api.post("/api/regeln", json=_regel(k["lebensmittel"]["id"], name=name, prioritaet=p),
                             erwartet=201).daten["id"]
    liste = api.get("/api/regeln", erwartet=200).daten
    assert [r["name"] for r in liste] == ["e", "a", "d", "c", "b"]


def test_alle_bedingungsarten(api, k):
    bed = [{"feld": "empfaenger", "operator": "gleich", "wert": "Ä"},
           {"feld": "empfaenger", "operator": "beginnt_mit", "wert": "x"},
           {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Miete"},
           {"feld": "betrag", "operator": "gleich", "wert": -999999999999},
           {"feld": "betrag", "operator": "mindestens", "wert": 0},
           {"feld": "betrag", "operator": "hoechstens", "wert": 999999999999},
           {"feld": "konto_id", "operator": "gleich", "wert": k["spar"]["id"]}]
    r = api.post("/api/regeln", json=_regel(k["gehalt"]["id"], bedingungen=bed), erwartet=201).daten
    assert r["bedingungen"] == bed
    zwanzig = [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": f"w{i}"} for i in range(20)]
    api.post("/api/regeln", json=_regel(k["gehalt"]["id"], bedingungen=zwanzig), erwartet=201)


TEXT = {"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"}


@pytest.mark.kern
@pytest.mark.parametrize("aendern", [
    lambda b: {kk: v for kk, v in b.items() if kk != "name"},
    lambda b: {kk: v for kk, v in b.items() if kk != "kategorie_id"},
    lambda b: {kk: v for kk, v in b.items() if kk != "bedingungen"},
    lambda b: {**b, "name": "   "},
    lambda b: {**b, "name": "n" * 201},
    lambda b: {**b, "bedingungen": []},
    lambda b: {**b, "bedingungen": [TEXT] * 21},
    lambda b: {**b, "bedingungen": [{**TEXT, "feld": "kategorie"}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "operator": "regex"}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "operator": "mindestens"}]},
    lambda b: {**b, "bedingungen": [{"feld": "betrag", "operator": "enthaelt", "wert": 5}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "wert": 5}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "wert": ""}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "wert": "   "}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "wert": "w" * 201}]},
    lambda b: {**b, "bedingungen": [{"feld": "betrag", "operator": "gleich", "wert": "100"}]},
    lambda b: {**b, "bedingungen": [{"feld": "betrag", "operator": "gleich", "wert": 1.0}]},
    lambda b: {**b, "bedingungen": [{"feld": "betrag", "operator": "gleich", "wert": True}]},
    lambda b: {**b, "bedingungen": [{"feld": "betrag", "operator": "gleich", "wert": 10 ** 12}]},
    lambda b: {**b, "bedingungen": [{"feld": "konto_id", "operator": "enthaelt", "wert": 1}]},
    lambda b: {**b, "bedingungen": [{"feld": "konto_id", "operator": "gleich", "wert": "1"}]},
    lambda b: {**b, "bedingungen": [{**TEXT, "zusatz": 1}]},
    lambda b: {**b, "prioritaet": -1},
    lambda b: {**b, "prioritaet": 1000001},
    lambda b: {**b, "prioritaet": "5"},
    lambda b: {**b, "aktiv": "ja"},
    lambda b: {**b, "unbekannt": 1},
], ids=["ohne_name", "ohne_kategorie", "ohne_bedingungen", "name_leer", "name_lang", "keine_bedingung",
        "21_bedingungen", "feld_unbekannt", "regex", "operator_falsch_text", "operator_falsch_betrag",
        "text_als_zahl", "text_leer", "text_leerraum", "text_lang", "betrag_text", "betrag_float", "betrag_bool",
        "betrag_zu_gross", "konto_operator", "konto_text", "bedingung_zusatzfeld", "prio_negativ", "prio_gross",
        "prio_text", "aktiv_text", "feld_zusatz"])
def test_validierung(api, k, aendern):
    r = api.post("/api/regeln", json=aendern(_regel(k["lebensmittel"]["id"])), erwartet=422)
    assert fehlercode(r) == "validierung"
    assert api.get("/api/regeln", erwartet=200).daten == []


@pytest.mark.parametrize("art", ["giro", "eigen", "unbekannt"])
def test_kategorie_ungueltig(api, k, art):
    kid = 4711 if art == "unbekannt" else k[art]["id"]
    assert fehlercode(api.post("/api/regeln", json=_regel(kid), erwartet=422)) == "kategorie_ungueltig"
    r = api.post("/api/regeln", json=_regel(k["lebensmittel"]["id"]), erwartet=201).daten
    assert fehlercode(api.patch(f"/api/regeln/{r['id']}", json={"kategorie_id": kid}, erwartet=422)) == \
        "kategorie_ungueltig"
    assert api.get(f"/api/regeln/{r['id']}", erwartet=200).daten == r


@pytest.mark.parametrize("art", ["lebensmittel", "eigen", "unbekannt"])
def test_konto_bedingung_braucht_bestandskonto(api, k, art):
    kid = 4711 if art == "unbekannt" else k[art]["id"]
    body = _regel(k["lebensmittel"]["id"], bedingungen=[{"feld": "konto_id", "operator": "gleich", "wert": kid}])
    assert fehlercode(api.post("/api/regeln", json=body, erwartet=422)) == "referenz_unbekannt"


def test_aendern(api, k):
    r = api.post("/api/regeln", json=_regel(k["lebensmittel"]["id"], prioritaet=5), erwartet=201).daten
    r2 = api.patch(f"/api/regeln/{r['id']}", json={"name": " Neu "}, erwartet=200).daten
    assert r2 == {**r, "name": "Neu"}
    neue_bed = [{"feld": "betrag", "operator": "hoechstens", "wert": -5001}]
    r3 = api.patch(f"/api/regeln/{r['id']}", json={"bedingungen": neue_bed, "aktiv": False, "prioritaet": 9,
                                                   "kategorie_id": k["gehalt"]["id"]}, erwartet=200).daten
    # W-028 (E-314): ``ausdruck`` (ab M30) ist der kanonische Text der neuen Bedingungen und wird nicht verglichen
    ohne_a = lambda d: {f: w for f, w in d.items() if f != "ausdruck"}  # noqa: E731
    assert ohne_a(r3) == ohne_a({**r2, "bedingungen": neue_bed, "aktiv": False, "prioritaet": 9,
                                 "kategorie_id": k["gehalt"]["id"]})
    assert api.get(f"/api/regeln/{r['id']}", erwartet=200).daten == r3
    for koerper in ({"bedingungen": []}, {"name": ""}, {"aktiv": None}, {"id": 5}):
        assert fehlercode(api.patch(f"/api/regeln/{r['id']}", json=koerper, erwartet=422)) == "validierung"
    assert api.get(f"/api/regeln/{r['id']}", erwartet=200).daten == r3


def test_loeschen_und_404(api, k):
    r = api.post("/api/regeln", json=_regel(k["lebensmittel"]["id"]), erwartet=201).daten
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    for antw in (api.get(f"/api/regeln/{r['id']}", erwartet=404), api.delete(f"/api/regeln/{r['id']}", erwartet=404),
                 api.patch(f"/api/regeln/{r['id']}", json={"name": "x"}, erwartet=404)):
        assert fehlercode(antw) == "nicht_gefunden"
    assert api.get("/api/regeln", erwartet=200).daten == []
    neu = api.post("/api/regeln", json=_regel(k["lebensmittel"]["id"]), erwartet=201).daten
    assert neu["id"] > r["id"], "IDs werden nie wiederverwendet"


@pytest.mark.kern
def test_konto_mit_regelbezug_nicht_loeschbar(api, k):
    """E-043: Kategorie oder Bedingungskonto einer Regel kann nicht gelöscht werden."""
    body = _regel(k["lebensmittel"]["id"], bedingungen=[{"feld": "konto_id", "operator": "gleich",
                                                          "wert": k["spar"]["id"]}])
    r = api.post("/api/regeln", json=body, erwartet=201).daten
    for kid in (k["lebensmittel"]["id"], k["spar"]["id"]):
        assert fehlercode(api.delete(f"/api/konten/{kid}", erwartet=409)) == "konto_in_verwendung"
    api.delete(f"/api/konten/{k['gehalt']['id']}", erwartet=204)
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    api.delete(f"/api/konten/{k['lebensmittel']['id']}", erwartet=204)
    api.delete(f"/api/konten/{k['spar']['id']}", erwartet=204)
