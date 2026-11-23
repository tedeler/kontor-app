"""M25: REST der Betragsfilter, Protokoll, Rückgängig, Empfänger löschen/zusammenführen, Sicherung
(wiederkehrend.md 9.3, 9.4; E-239)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m9 import einspielen, inhalt_sha256, oeffne, sicherung
from tests.hilfen.m25 import (
    VORGABE_PFAD, bestand, einstellungen, filter_loeschen, filter_setzen, protokollformen, vorgabe,
)

pytestmark = pytest.mark.kern

OBJEKTE_M9 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]
TOL = {"modus": "toleranz", "toleranz_prozent": 15, "mindestbetrag": None}
MIN = {"modus": "mindestschwelle", "toleranz_prozent": None, "mindestbetrag": 100000}
AUS = {"modus": "aus", "toleranz_prozent": None, "mindestbetrag": None}


@pytest.fixture
def api(tmp_path):
    return neue_api(tmp_path)


def _orte(r) -> list[list]:
    assert fehlercode(r) == "validierung", r.text
    return sorted(list(d["ort"]) for d in r.json()["fehler"]["details"])


# ------------------------------------------------------------------ Vorgabe
def test_ausgelieferte_vorgabe(api):
    assert einstellungen(api) == {"vorgabe": {"modus": "toleranz", "toleranz_prozent": 10}, "empfaenger": []}


def test_vorgabe_setzen_ohne_protokoll(api):
    a0 = letzte_aenderung_id(api)
    assert vorgabe(api, "aus").daten == {"modus": "aus", "toleranz_prozent": None}
    assert einstellungen(api)["vorgabe"] == {"modus": "aus", "toleranz_prozent": None}
    for p in (0, 100, 25):
        assert vorgabe(api, "toleranz", p).daten == {"modus": "toleranz", "toleranz_prozent": p}
    assert einstellungen(api)["vorgabe"] == {"modus": "toleranz", "toleranz_prozent": 25}
    r = api.put(VORGABE_PFAD, json={"modus": "aus", "toleranz_prozent": None, "mindestbetrag": None}, erwartet=200)
    assert r.daten == {"modus": "aus", "toleranz_prozent": None}, "null-Parameter dürfen stehen"
    assert letzte_aenderung_id(api) == a0, "kein Protokolleintrag"


@pytest.mark.parametrize("koerper,orte", [
    ({"modus": "mindestschwelle", "mindestbetrag": 1000}, [["body", "modus"]]),
    ({"modus": "toleranz"}, [["body", "toleranz_prozent"]]),
    ({"modus": "toleranz", "toleranz_prozent": 101}, [["body", "toleranz_prozent"]]),
    ({"modus": "toleranz", "toleranz_prozent": -1}, [["body", "toleranz_prozent"]]),
    ({"modus": "aus", "toleranz_prozent": 10}, [["body", "toleranz_prozent"]]),
    ({"modus": "toleranz", "toleranz_prozent": 10, "mindestbetrag": 500}, [["body", "mindestbetrag"]]),
])
def test_vorgabe_fachliche_pruefung(api, koerper, orte):
    r = api.put(VORGABE_PFAD, json=koerper, erwartet=422)
    assert [o[:2] for o in _orte(r)] == orte
    assert einstellungen(api)["vorgabe"] == {"modus": "toleranz", "toleranz_prozent": 10}


@pytest.mark.parametrize("koerper", [
    {}, {"modus": "manchmal"}, {"modus": "toleranz", "toleranz_prozent": True}, {"modus": "toleranz",
    "toleranz_prozent": "10"}, {"modus": "toleranz", "toleranz_prozent": 10.0}, {"modus": "aus", "x": 1},
])
def test_vorgabe_schema(api, koerper):
    assert fehlercode(api.put(VORGABE_PFAD, json=koerper, erwartet=422)) == "validierung"


# ------------------------------------------------------------------ Empfänger
def test_empfaenger_setzen_lesen_sortiert(api):
    b = api.empfaenger("Zeitung (fiktiv)")["id"]
    a = api.empfaenger("Arbeitgeber (fiktiv)")["id"]
    c = api.empfaenger("Arbeitgeber (fiktiv) 2")["id"]
    r = filter_setzen(api, b, modus="toleranz", toleranz_prozent=15).daten
    assert r == {"empfaenger": {"id": b, "name": "Zeitung (fiktiv)"}, **TOL}
    assert filter_setzen(api, a, modus="mindestschwelle", mindestbetrag=100000).daten == {
        "empfaenger": {"id": a, "name": "Arbeitgeber (fiktiv)"}, **MIN}
    assert filter_setzen(api, c, modus="aus").daten == {"empfaenger": {"id": c, "name": "Arbeitgeber (fiktiv) 2"},
                                                        **AUS}
    e = einstellungen(api)
    assert [x["empfaenger"]["id"] for x in e["empfaenger"]] == [a, c, b], "nach Name, dann ID"
    assert e["empfaenger"][0] == {"empfaenger": {"id": a, "name": "Arbeitgeber (fiktiv)"}, **MIN}
    for x in api.get("/api/empfaenger", erwartet=200).daten:
        assert "wiederkehrend" not in x, "GET /api/empfaenger bleibt unverändert"


@pytest.mark.parametrize("koerper,orte", [
    ({"modus": "toleranz"}, [["body", "toleranz_prozent"]]),
    ({"modus": "toleranz", "toleranz_prozent": 101}, [["body", "toleranz_prozent"]]),
    ({"modus": "mindestschwelle"}, [["body", "mindestbetrag"]]),
    ({"modus": "mindestschwelle", "mindestbetrag": 0}, [["body", "mindestbetrag"]]),
    ({"modus": "mindestschwelle", "mindestbetrag": -100}, [["body", "mindestbetrag"]]),
    ({"modus": "mindestschwelle", "mindestbetrag": 1000000000000}, [["body", "mindestbetrag"]]),
    ({"modus": "aus", "mindestbetrag": 5}, [["body", "mindestbetrag"]]),
    ({"modus": "mindestschwelle", "mindestbetrag": 5, "toleranz_prozent": 3}, [["body", "toleranz_prozent"]]),
    ({"modus": "toleranz", "mindestbetrag": 5}, [["body", "mindestbetrag"], ["body", "toleranz_prozent"]]),
])
def test_empfaenger_fachliche_pruefung(api, koerper, orte):
    e = api.empfaenger("Laden (fiktiv)")["id"]
    a0 = letzte_aenderung_id(api)
    r = filter_setzen(api, e, erwartet=422, **koerper)
    assert [o[:2] for o in _orte(r)] == orte, "alle Verstöße gemeinsam"
    assert einstellungen(api)["empfaenger"] == [] and letzte_aenderung_id(api) == a0


def test_empfaenger_pruefreihenfolge(api):
    e = api.empfaenger("Laden (fiktiv)")["id"]
    assert fehlercode(api.put(f"/api/empfaenger/{e}/wiederkehrend", json={"modus": True}, erwartet=422)) == \
        "validierung"
    assert fehlercode(api.put("/api/empfaenger/9999/wiederkehrend", json={"modus": 1}, erwartet=422)) == \
        "validierung", "Schema vor unbekanntem Empfänger"
    assert fehlercode(api.put("/api/empfaenger/9999/wiederkehrend", json={"modus": "toleranz"}, erwartet=404)) == \
        "nicht_gefunden", "unbekannt vor fachlicher Prüfung"
    assert fehlercode(api.put("/api/empfaenger/9999/wiederkehrend", json={"modus": "x"}, erwartet=422)) == \
        "validierung"
    assert fehlercode(filter_loeschen(api, 9999, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(filter_loeschen(api, e, erwartet=404)) == "nicht_gefunden", "ohne eigene Einstellung"


# ------------------------------------------------------------------ Protokoll
def test_protokoll_rueckgaengig_wiederholen(api):
    e = api.empfaenger("Arbeitgeber (fiktiv)")["id"]
    v, a0 = bestand(api), letzte_aenderung_id(api)
    filter_setzen(api, e, modus="toleranz", toleranz_prozent=15)
    n = bestand(api)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "wiederkehrend_filter_setzen", None)
    form = protokollformen(a)
    assert set(form) == {("empfaenger", e)}
    art, vorher, nachher = form[("empfaenger", e)]
    assert art == "geaendert" and vorher == v[("empfaenger", e)] and nachher == n[("empfaenger", e)]
    assert "wiederkehrend" not in vorher and nachher["wiederkehrend"] == TOL
    a1 = letzte_aenderung_id(api)
    filter_setzen(api, e, modus="toleranz", toleranz_prozent=15)
    assert letzte_aenderung_id(api) == a1, "gleiche Einstellung: keine Änderung"
    filter_setzen(api, e, modus="mindestschwelle", mindestbetrag=100000)
    (b,) = aenderungen_seit(api, a1)
    assert protokollformen(b)[("empfaenger", e)][2]["wiederkehrend"] == MIN
    u = api.post(f"/api/aenderungen/{b['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == n and einstellungen(api)["empfaenger"][0]["modus"] == "toleranz"
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert einstellungen(api)["empfaenger"][0]["modus"] == "mindestschwelle"
    a2 = letzte_aenderung_id(api)
    filter_loeschen(api, e)
    (c,) = aenderungen_seit(api, a2)
    assert (c["aktion"], c["quelle"]) == ("wiederkehrend_filter_setzen", "manuell")
    art, vorher, nachher = protokollformen(c)[("empfaenger", e)]
    assert art == "geaendert" and vorher["wiederkehrend"] == MIN and "wiederkehrend" not in nachher
    assert einstellungen(api)["empfaenger"] == []
    api.post(f"/api/aenderungen/{c['id']}/rueckgaengig", erwartet=200)
    assert einstellungen(api)["empfaenger"][0]["modus"] == "mindestschwelle"
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=409)


def test_empfaenger_loeschen_nimmt_einstellung_mit(api):
    e = api.empfaenger("Altvertrag (fiktiv)")["id"]
    filter_setzen(api, e, modus="aus")
    v, a0 = bestand(api), letzte_aenderung_id(api)
    api.delete(f"/api/empfaenger/{e}", erwartet=204)
    assert einstellungen(api)["empfaenger"] == []
    (a,) = aenderungen_seit(api, a0)
    art, vorher, nachher = protokollformen(a)[("empfaenger", e)]
    assert art == "geloescht" and vorher["wiederkehrend"] == AUS and nachher is None
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == v and einstellungen(api)["empfaenger"][0]["modus"] == "aus"


def test_zusammenfuehren(api):
    ziel = api.empfaenger("Arbeitgeber (fiktiv)")["id"]
    q1 = api.empfaenger("Arbeitgeber Alt (fiktiv)")["id"]
    q2 = api.empfaenger("Arbeitgeber Neu (fiktiv)")["id"]
    filter_setzen(api, ziel, modus="toleranz", toleranz_prozent=15)
    filter_setzen(api, q1, modus="mindestschwelle", mindestbetrag=100000)
    v, a0 = bestand(api), letzte_aenderung_id(api)
    api.post(f"/api/empfaenger/{ziel}/zusammenfuehren", json={"quelle_ids": [q1, q2]}, erwartet=200)
    e = einstellungen(api)["empfaenger"]
    assert [(x["empfaenger"]["id"], x["modus"]) for x in e] == [(ziel, "toleranz")], "Ziel behält seine Einstellung"
    (a,) = aenderungen_seit(api, a0)
    assert protokollformen(a)[("empfaenger", q1)][1]["wiederkehrend"] == MIN
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == v


# ------------------------------------------------------------------ Sicherung
def test_sicherung_rundreise(tmp_path):
    quelle = neue_api(tmp_path / "q")
    ohne = {}
    for name, body in (("Toleranz (fiktiv)", {"modus": "toleranz", "toleranz_prozent": 15}),
                       ("Schwelle (fiktiv)", {"modus": "mindestschwelle", "mindestbetrag": 100000}),
                       ("Aus (fiktiv)", {"modus": "aus"}), ("Ohne (fiktiv)", None)):
        e = quelle.empfaenger(name)["id"]
        ohne[name] = e
        if body:
            filter_setzen(quelle, e, **body)
    vorgabe(quelle, "toleranz", 30)
    soll = einstellungen(quelle)["empfaenger"]
    m, _ = oeffne(sicherung(quelle))
    assert m["schemaversion"] >= 6
    bs = bestand(quelle)
    inhalt = {o: [bs[k] for k in sorted(k for k in bs if k[0] == o)] for o in OBJEKTE_M9}
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt), "Prüfsumme über die Empfängerform mit wiederkehrend"
    ziel = neue_api(tmp_path / "z")
    vorgabe(ziel, "aus")
    einspielen(ziel, sicherung(quelle))
    assert einstellungen(ziel) == {"vorgabe": {"modus": "aus", "toleranz_prozent": None}, "empfaenger": soll}, \
        "eigene Einstellungen kommen mit, die Vorgabe der Instanz nicht"
    assert bestand(ziel) == bs
    m2, _ = oeffne(sicherung(ziel))
    assert m2["inhalt_sha256"] == m["inhalt_sha256"]


def test_pruefsumme_ohne_einstellungen_unveraendert(tmp_path):
    a = neue_api(tmp_path / "a")
    a.empfaenger("Laden (fiktiv)")
    m0, _ = oeffne(sicherung(a))
    vorgabe(a, "aus")
    m1, _ = oeffne(sicherung(a))
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"]), "Vorgabe nicht in der Sicherung"
    bs = bestand(a)
    inhalt = {o: [bs[k] for k in sorted(k for k in bs if k[0] == o)] for o in OBJEKTE_M9}
    assert m1["inhalt_sha256"] == inhalt_sha256(inhalt)
