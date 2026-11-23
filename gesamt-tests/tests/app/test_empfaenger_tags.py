"""Empfänger und Tags (datenmodell.md 5 und 6, T 4)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode


# --------------------------------------------------------------- Empfänger


def test_empfaenger_anlegen_lesen(api):
    e = api.empfaenger("  Bäckerei „Größenwahn“ & Söhne ☕ ")
    assert e["name"] == "Bäckerei „Größenwahn“ & Söhne ☕" and e["extern_id"] is None
    assert api.get(f"/api/empfaenger/{e['id']}", erwartet=200).daten == e
    f = api.empfaenger("Zweiter")
    assert f["id"] > e["id"]
    assert api.get("/api/empfaenger", erwartet=200).daten == [e, f]


def test_empfaenger_eindeutig_exakt(api):
    api.empfaenger("Café Bohne")
    assert fehlercode(api.post("/api/empfaenger", json={"name": "Café Bohne"}, erwartet=409)) == "empfaenger_existiert"
    assert fehlercode(api.post("/api/empfaenger", json={"name": " Café Bohne "},
                               erwartet=409)) == "empfaenger_existiert"
    # exakter Vergleich: andere Schreibweise ist ein anderer Empfänger
    api.empfaenger("CAFÉ BOHNE")
    api.empfaenger("Cafe Bohne")
    assert len(api.get("/api/empfaenger", erwartet=200).daten) == 3


@pytest.mark.parametrize("koerper", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 201}, {"name": 5},
                                     {"name": "A", "extern_id": "kmy:P1"}])
def test_empfaenger_validierung(api, koerper):
    assert fehlercode(api.post("/api/empfaenger", json=koerper, erwartet=422)) == "validierung"
    assert api.get("/api/empfaenger", erwartet=200).daten == []


# -------------------------------------------------------------------- Tags


def _buchung(api, konten, tag_ids=(), datum="2024-01-01"):
    g, a = konten
    return api.buchung(datum, [(g, -100), (a, 100)], tag_ids=list(tag_ids))


@pytest.fixture
def konten(api):
    return api.konto()["id"], api.konto("Lebensmittel", "aufwand")["id"]


def test_tag_anlegen(api):
    t = api.tag("  Urlaub 2024 – Ölfass ")
    assert t == {"id": t["id"], "name": "Urlaub 2024 – Ölfass", "extern_id": None, "anzahl_buchungen": 0}
    assert api.get("/api/tags", erwartet=200).daten == [t]


@pytest.mark.parametrize("zweiter", ["Urlaub", "URLAUB", "urlaub", " Urlaub "])
def test_tag_eindeutig_casefold(api, zweiter):
    api.tag("Urlaub")
    assert fehlercode(api.post("/api/tags", json={"name": zweiter}, erwartet=409)) == "tag_existiert"


def test_tag_casefold_sz(api):
    api.tag("Straße")
    assert fehlercode(api.post("/api/tags", json={"name": "STRASSE"}, erwartet=409)) == "tag_existiert"


@pytest.mark.parametrize("koerper", [{}, {"name": ""}, {"name": "  "}, {"name": "x" * 101}, {"name": None}])
def test_tag_validierung(api, koerper):
    assert fehlercode(api.post("/api/tags", json=koerper, erwartet=422)) == "validierung"


def test_mehrere_tags_je_buchung(api, konten):
    t1, t2, t3 = api.tag("C"), api.tag("A"), api.tag("B")
    b = _buchung(api, konten, [t3["id"], t1["id"], t3["id"], t2["id"]])
    assert b["tags"] == [{"id": t["id"], "name": t["name"]} for t in (t1, t2, t3)], "nach id, ohne Doppelte"
    assert api.buchung_lesen(b["id"])["tags"] == b["tags"]
    assert {t["id"]: t["anzahl_buchungen"] for t in api.get("/api/tags", erwartet=200).daten} == {
        t1["id"]: 1, t2["id"]: 1, t3["id"]: 1}


def test_tag_unbekannt_bei_buchung(api, konten):
    g, a = konten
    r = api.post("/api/buchungen", json={"datum": "2024-01-01", "splits": [
        {"konto_id": g, "betrag": -1}, {"konto_id": a, "betrag": 1}], "tag_ids": [4711]}, erwartet=422)
    assert fehlercode(r) == "referenz_unbekannt"
    assert api.alle_buchungen() == []


def test_umbenennen_wirkt_auf_alle_buchungen(api, konten):
    t = api.tag("Urlab")
    andere = api.tag("Steuer")
    bs = [_buchung(api, konten, [t["id"]]) for _ in range(3)] + [_buchung(api, konten, [andere["id"]])]
    r = api.patch(f"/api/tags/{t['id']}", json={"name": " Urlaub "}, erwartet=200).daten
    assert r == {"id": t["id"], "name": "Urlaub", "extern_id": None, "anzahl_buchungen": 3}
    for b in bs[:3]:
        assert api.buchung_lesen(b["id"])["tags"] == [{"id": t["id"], "name": "Urlaub"}]
    assert api.buchung_lesen(bs[3]["id"])["tags"] == [{"id": andere["id"], "name": "Steuer"}]


def test_umbenennen_konflikte(api):
    t = api.tag("Urlaub")
    api.tag("Steuer")
    assert fehlercode(api.patch(f"/api/tags/{t['id']}", json={"name": "STEUER"}, erwartet=409)) == "tag_existiert"
    # nur Groß-/Kleinschreibung des eigenen Namens ändern ist erlaubt
    assert api.patch(f"/api/tags/{t['id']}", json={"name": "URLAUB"}, erwartet=200).daten["name"] == "URLAUB"
    assert fehlercode(api.patch(f"/api/tags/{t['id']}", json={"name": " "}, erwartet=422)) == "validierung"
    assert [x["name"] for x in api.get("/api/tags", erwartet=200).daten] == ["URLAUB", "Steuer"]


def test_tag_loeschen_entfernt_nur_zuordnung(api, konten):
    t = api.tag("Weg")
    bleibt = api.tag("Bleibt")
    b = _buchung(api, konten, [t["id"], bleibt["id"]])
    vorher = api.buchung_lesen(b["id"])
    api.delete(f"/api/tags/{t['id']}", erwartet=204)
    nachher = api.buchung_lesen(b["id"])
    assert nachher == {**vorher, "tags": [{"id": bleibt["id"], "name": "Bleibt"}]}
    assert [x["id"] for x in api.get("/api/tags", erwartet=200).daten] == [bleibt["id"]]
    api.patch(f"/api/tags/{t['id']}", erwartet=404, json={"name": "x"})
    # Name ist danach wieder frei, neue ID
    neu = api.tag("Weg")
    assert neu["id"] > t["id"]
    assert api.salden()[konten[0]]["saldo"] == -100


def test_tags_per_patch_ersetzen(api, konten):
    t1, t2 = api.tag("A"), api.tag("B")
    b = _buchung(api, konten, [t1["id"]])
    r = api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": [t2["id"], t2["id"]]}, erwartet=200).daten
    assert r["tags"] == [{"id": t2["id"], "name": "B"}]
    r = api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": []}, erwartet=200).daten
    assert r["tags"] == []
    assert fehlercode(api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": [4711]},
                                erwartet=422)) == "referenz_unbekannt"
    assert api.buchung_lesen(b["id"])["tags"] == []
