"""M4: Split-Vorlagen – Anlegen, Validierung, Reihenfolge, Ändern, Löschen, Bezüge (vorlagen.md 1, 2; K 8)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m4 import bestand, pruefe_eintraege


@pytest.fixture
def k(api):
    return {"giro": api.konto("Giro")["id"], "spar": api.konto("Spar", "sparkonto")["id"],
            "haft": api.konto("Haftpflicht", "aufwand")["id"], "haus": api.konto("Hausrat", "aufwand")["id"],
            "erst": api.konto("Erstattung", "ertrag")["id"], "ek": api.konto("EK", "eigenkapital")["id"]}


def _body(k, **felder):
    b = {"name": "Versicherung", "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktiva AG"}],
         "teile": [{"kategorie_id": k["haft"], "betrag": 650, "memo": "Vertrag 1"},
                   {"kategorie_id": k["haus"], "betrag": 1290}]}
    b.update(felder)
    return b


@pytest.mark.kern
def test_anlegen_und_lesen(api, k):
    v = api.post("/api/vorlagen", json=_body(k, name="  Versicherung  "), erwartet=201).daten
    assert v == {"id": v["id"], "name": "Versicherung", "aktiv": True, "prioritaet": 100,
                 "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktiva AG"}],
                 "teile": [{"kategorie_id": k["haft"], "betrag": 650, "memo": "Vertrag 1"},
                           {"kategorie_id": k["haus"], "betrag": 1290, "memo": ""}],
                 "gesamtbetrag": -1940}
    assert api.get(f"/api/vorlagen/{v['id']}", erwartet=200).daten == v
    assert api.get("/api/vorlagen", erwartet=200).daten == [v]
    w = api.post("/api/vorlagen", json=_body(k, name="Zwei"), erwartet=201).daten
    assert w["prioritaet"] == 110, "Vorgabe: größte vorhandene Priorität + 10"


@pytest.mark.kern
def test_gesamtbetrag_und_vorzeichen(api, k):
    """Teile in Soll-Sicht; ein Erstattungsteil darf negativ sein, die Summe nicht 0 (vorlagen.md 1)."""
    v = api.post("/api/vorlagen", json=_body(k, teile=[{"kategorie_id": k["haft"], "betrag": 5000},
                                                       {"kategorie_id": k["erst"], "betrag": -1200}]),
                 erwartet=201).daten
    assert v["gesamtbetrag"] == -3800
    gleich = api.post("/api/vorlagen", json=_body(k, teile=[{"kategorie_id": k["haft"], "betrag": 100},
                                                            {"kategorie_id": k["haft"], "betrag": 200}]),
                      erwartet=201).daten
    assert gleich["gesamtbetrag"] == -300, "mehrere Teile dürfen dieselbe Kategorie haben"


@pytest.mark.kern
@pytest.mark.parametrize("aenderung", [
    {"bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Beitrag"}]},
    {"bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "X"},
                     {"feld": "betrag", "operator": "gleich", "wert": -1940}]},
    {"bedingungen": []},
    {"teile": [{"kategorie_id": 0, "betrag": 650}]},
    {"teile": "keine"},
    {"teile": [{"kategorie_id": 1, "betrag": 0}, {"kategorie_id": 1, "betrag": 5}]},
    {"teile": [{"kategorie_id": 1, "betrag": 500}, {"kategorie_id": 1, "betrag": -500}]},
    {"teile": [{"kategorie_id": 1, "betrag": 5.0}, {"kategorie_id": 1, "betrag": 5}]},
    {"teile": [{"kategorie_id": 1, "betrag": 5, "farbe": "rot"}, {"kategorie_id": 1, "betrag": 5}]},
    {"name": "   "}, {"name": "x" * 201}, {"prioritaet": -1}, {"prioritaet": 1000001}, {"aktiv": "ja"},
    {"unbekannt": 1},
], ids=["ohne_empfaenger", "betrag_bedingung", "keine_bedingung", "ein_teil", "teile_text", "teil_null", "summe_null",
        "float", "teil_extra", "name_leer", "name_lang", "prio_neg", "prio_gross", "aktiv_text", "extra"])
def test_validierung(api, k, aenderung):
    body = _body(k, **aenderung)
    for t in body["teile"] if isinstance(body["teile"], list) else []:
        if t.get("kategorie_id") == 1:
            t["kategorie_id"] = k["haft"]
    assert fehlercode(api.post("/api/vorlagen", json=body, erwartet=422)) == "validierung"
    v = api.post("/api/vorlagen", json=_body(k), erwartet=201).daten
    assert fehlercode(api.patch(f"/api/vorlagen/{v['id']}", json=aenderung, erwartet=422)) in (
        "validierung", "kategorie_ungueltig")
    assert api.get("/api/vorlagen", erwartet=200).daten == [v]


@pytest.mark.kern
def test_kategorie_und_konto_bezuege(api, k):
    for kid in (k["giro"], k["ek"], 9999):
        body = _body(k, teile=[{"kategorie_id": kid, "betrag": 100}, {"kategorie_id": k["haft"], "betrag": 1}])
        assert fehlercode(api.post("/api/vorlagen", json=body, erwartet=422)) == "kategorie_ungueltig"
    for kid in (k["haft"], 9999):
        body = _body(k, bedingungen=[{"feld": "empfaenger", "operator": "enthaelt", "wert": "x"},
                                     {"feld": "konto_id", "operator": "gleich", "wert": kid}])
        assert fehlercode(api.post("/api/vorlagen", json=body, erwartet=422)) == "referenz_unbekannt"
    ok = api.post("/api/vorlagen", json=_body(k, bedingungen=[
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "x"},
        {"feld": "konto_id", "operator": "gleich", "wert": k["giro"]}]), erwartet=201).daten
    assert ok["bedingungen"][1]["wert"] == k["giro"]
    assert api.get("/api/vorlagen", erwartet=200).daten == [ok]


@pytest.mark.kern
def test_reihenfolge_nach_prioritaet_und_id(api, k):
    a = api.post("/api/vorlagen", json=_body(k, name="A", prioritaet=50), erwartet=201).daten
    b = api.post("/api/vorlagen", json=_body(k, name="B", prioritaet=10), erwartet=201).daten
    c = api.post("/api/vorlagen", json=_body(k, name="C", prioritaet=50), erwartet=201).daten
    d = api.post("/api/vorlagen", json=_body(k, name="D"), erwartet=201).daten
    assert d["prioritaet"] == 60
    assert [v["name"] for v in api.get("/api/vorlagen", erwartet=200).daten] == ["B", "A", "C", "D"]
    api.patch(f"/api/vorlagen/{c['id']}", json={"prioritaet": 0}, erwartet=200)
    assert [v["id"] for v in api.get("/api/vorlagen", erwartet=200).daten] == [c["id"], b["id"], a["id"], d["id"]]


@pytest.mark.kern
def test_aendern_ersetzt_listen(api, k):
    v = api.post("/api/vorlagen", json=_body(k), erwartet=201).daten
    neu = api.patch(f"/api/vorlagen/{v['id']}", json={"teile": [
        {"kategorie_id": k["haft"], "betrag": 650}, {"kategorie_id": k["haus"], "betrag": 1340, "memo": "neu"},
        {"kategorie_id": k["haus"], "betrag": 10}]}, erwartet=200).daten
    assert neu["gesamtbetrag"] == -2000 and len(neu["teile"]) == 3 and neu["teile"][0]["memo"] == ""
    assert (neu["name"], neu["bedingungen"], neu["prioritaet"], neu["aktiv"]) == (
        v["name"], v["bedingungen"], v["prioritaet"], v["aktiv"])
    aus = api.patch(f"/api/vorlagen/{v['id']}", json={"aktiv": False, "name": "Alt"}, erwartet=200).daten
    assert (aus["aktiv"], aus["name"], aus["teile"]) == (False, "Alt", neu["teile"])
    assert api.get(f"/api/vorlagen/{v['id']}", erwartet=200).daten == aus


def test_nicht_gefunden(api, k):
    assert fehlercode(api.get("/api/vorlagen/77", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.patch("/api/vorlagen/77", json={"aktiv": False}, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.delete("/api/vorlagen/77", erwartet=404)) == "nicht_gefunden"


@pytest.mark.kern
def test_konto_mit_vorlage_nicht_loeschbar(api, k):
    """vorlagen.md 1: DELETE /api/konten → 409 konto_in_verwendung (Teil-Kategorie oder Bedingung konto_id)."""
    api.post("/api/vorlagen", json=_body(k, bedingungen=[
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "x"},
        {"feld": "konto_id", "operator": "gleich", "wert": k["spar"]}]), erwartet=201)
    for kid in (k["haft"], k["spar"]):
        assert fehlercode(api.delete(f"/api/konten/{kid}", erwartet=409)) == "konto_in_verwendung"
    api.delete(f"/api/konten/{k['erst']}", erwartet=204)


@pytest.mark.kern
def test_protokoll_anlegen_aendern_loeschen(api, k):
    """protokoll.md 9: je Operation genau eine Änderung mit genau dem Vorlagen-Eintrag; ohne Wirkung keine."""
    z0, a0 = bestand(api), letzte_aenderung_id(api)
    v = api.post("/api/vorlagen", json=_body(k), erwartet=201).daten
    z1 = bestand(api)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "vorlage_anlegen", None)
    pruefe_eintraege(a, z0, z1)
    api.patch(f"/api/vorlagen/{v['id']}", json={"name": v["name"], "aktiv": True}, erwartet=200)
    assert aenderungen_seit(api, a["id"]) == [], "Setzen gleicher Werte erzeugt keine Änderung"
    api.patch(f"/api/vorlagen/{v['id']}", json={"prioritaet": 5}, erwartet=200)
    z2 = bestand(api)
    (b,) = aenderungen_seit(api, a["id"])
    assert b["aktion"] == "vorlage_aendern"
    pruefe_eintraege(b, z1, z2)
    api.delete(f"/api/vorlagen/{v['id']}", erwartet=204)
    (c,) = aenderungen_seit(api, b["id"])
    assert c["aktion"] == "vorlage_loeschen"
    pruefe_eintraege(c, z2, bestand(api))
    # rückgängig in umgekehrter Reihenfolge
    for aend, ziel in ((c, z2), (b, z1), (a, z0)):
        api.post(f"/api/aenderungen/{aend['id']}/rueckgaengig", erwartet=200)
        assert bestand(api) == ziel
    assert fehlercode(api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=409)) == "bereits_rueckgaengig"


def test_rueckgaengig_bezugspruefung(api, k):
    """protokoll.md 9.1: Wiederherstellen einer Vorlage, deren Kategorie fehlt → rueckgaengig_konflikt."""
    v = api.post("/api/vorlagen", json=_body(k), erwartet=201).daten
    a0 = letzte_aenderung_id(api)
    api.delete(f"/api/vorlagen/{v['id']}", erwartet=204)
    (weg,) = aenderungen_seit(api, a0)
    api.delete(f"/api/konten/{k['haus']}", erwartet=204)
    r = api.post(f"/api/aenderungen/{weg['id']}/rueckgaengig", erwartet=409)
    assert fehlercode(r) == "rueckgaengig_konflikt"
    assert api.get("/api/vorlagen", erwartet=200).daten == []


@pytest.mark.kern
@pytest.mark.parametrize("variante", ["elternkonto", "unkategorisiert", "loeschen"])
def test_konto_loeschen_mit_vorlagen(api, k, variante):
    """loeschen.md 6: elternkonto stellt um, die anderen Varianten löschen die Vorlage; rückgängig machbar."""
    eltern = api.konto("Versicherungen", "aufwand")["id"]
    kind = api.konto("Unfall", "aufwand", eltern_id=eltern)["id"]
    v = api.post("/api/vorlagen", json=_body(k, teile=[{"kategorie_id": kind, "betrag": 100, "memo": "U"},
                                                       {"kategorie_id": eltern, "betrag": 200}]),
                 erwartet=201).daten
    andere = api.post("/api/vorlagen", json=_body(k, name="Andere"), erwartet=201).daten
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    probe = api.post(f"/api/konten/{kind}/loeschen", json={"buchungen": variante, "konflikte": "behalten",
                                                           "trocken": True}, erwartet=200).daten
    assert bestand(api) == vorher, "Probelauf ändert auch an Vorlagen nichts"
    r = api.post(f"/api/konten/{kind}/loeschen", json={"buchungen": variante, "konflikte": "behalten"},
                 erwartet=200).daten
    ohne = ("trocken", "aenderung_id", "ziel_konto_id")
    assert {f: x for f, x in r.items() if f not in ohne} == {f: x for f, x in probe.items() if f not in ohne}
    assert not {"vorlagen_geaendert", "vorlagen_geloescht"} & set(r), "E-094: Antwort unverändert"
    if variante == "elternkonto":
        neu = api.get(f"/api/vorlagen/{v['id']}", erwartet=200).daten
        assert neu["teile"] == [{"kategorie_id": eltern, "betrag": 100, "memo": "U"},
                                {"kategorie_id": eltern, "betrag": 200, "memo": ""}], "nicht zusammengefasst"
        assert neu["gesamtbetrag"] == -300
    else:
        assert fehlercode(api.get(f"/api/vorlagen/{v['id']}", erwartet=404)) == "nicht_gefunden"
    assert api.get(f"/api/vorlagen/{andere['id']}", erwartet=200).daten == andere
    (a,) = aenderungen_seit(api, a0)
    assert a["aktion"] == "konto_loeschen_mit_buchungen"
    pruefe_eintraege(a, vorher, bestand(api))
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher
