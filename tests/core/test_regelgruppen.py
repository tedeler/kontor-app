"""Core-Tests zum Feature „regelgruppen“: eigene Regeln vor automatisch angelegten, Übernehmen als eigene Regel.

- Die Regelliste und die Auswertung führen alle eigenen Regeln vor allen automatisch angelegten (D-179); innerhalb
  jeder Gruppe gilt weiter ``prioritaet``, dann ``id``.
- ``POST /api/regeln/reihenfolge`` behält die Gruppen bei: Die Reihenfolge innerhalb jeder Gruppe kommt aus der Liste.
- ``POST /api/regeln/{id}/uebernehmen`` macht aus einer automatisch angelegten Regel eine eigene am Ende der eigenen
  Regeln; der Empfänger bekommt keine neue automatische Regel mehr. Eine Änderung im Protokoll, rückgängig zu machen.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


@pytest.fixture
def auto(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "kontor.sqlite3", regeln_automatisch=True)))
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = {n: c.post("/api/konten", json={"name": n, "art": "aufwand"}).json()["id"]
           for n in ("Lebensmittel", "Drogerie", "Unklar")}
    emp = {n: c.post("/api/empfaenger", json={"name": n}).json()["id"] for n in ("Frischekorb", "Glanz", "Neu")}
    heute = dt.date.today()

    def buchen(empf, kategorie, tage_her=10, zweck="Kartenzahlung"):
        r = c.post("/api/buchungen", json={
            "datum": (heute - dt.timedelta(days=tage_her)).isoformat(), "empfaenger_id": emp[empf],
            "verwendungszweck": zweck,
            "splits": [{"konto_id": g, "betrag": -1234}, {"konto_id": kat[kategorie], "betrag": 1234}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def lernen(empf, kategorie):
        for i in range(5):
            buchen(empf, kategorie, 20 + i)

    return c, buchen, lernen, kat, emp


def regeln(c):
    r = c.get("/api/regeln")
    assert r.status_code == 200, r.text
    return r.json()


def eigene_regel(c, name, kat, wert, **mehr):
    r = c.post("/api/regeln", json={"name": name, "kategorie_id": kat, **mehr, "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": wert}]})
    assert r.status_code == 201, r.text
    return r.json()


def test_liste_fuehrt_eigene_regeln_vor_automatischen(auto):
    c, _buchen, lernen, kat, _emp = auto
    lernen("Frischekorb", "Lebensmittel")
    eigen = eigene_regel(c, "Pfand", kat["Unklar"], "Pfand")
    liste = regeln(c)
    assert [r.get("automatisch", False) for r in liste] == [False, True]
    assert liste[0]["id"] == eigen["id"]
    # auch mit kleinerer Priorität der automatischen Regel
    assert liste[1]["prioritaet"] < liste[0]["prioritaet"]


def test_eigene_regel_gewinnt_gegen_aeltere_automatische(auto):
    c, buchen, lernen, kat, _emp = auto
    lernen("Frischekorb", "Lebensmittel")
    (a,) = [r for r in regeln(c) if r.get("automatisch")]
    eigene_regel(c, "Bonus", kat["Drogerie"], "Bonusheft")
    bid = buchen("Frischekorb", "Unklar", 2, zweck="Bonusheft Einkauf")
    r = c.post("/api/regeln/anwenden", json={"buchung_ids": [bid], "nur_unkategorisiert": False})
    assert r.status_code == 200, r.text
    b = c.get(f"/api/buchungen/{bid}").json()
    assert b["kategorie_id"] == kat["Drogerie"], (b, a)
    # Testbereich: die automatische Regel ist von der eigenen verdeckt
    t = c.post("/api/regeln/test", json={"regel_id": a["id"], "testmenge": ""})
    assert t.status_code == 200, t.text
    zeile = [z for z in t.json()["treffer"] if z["buchung_id"] == bid][0]
    assert zeile["wirkung"] == "verdeckt", zeile


def test_reihenfolge_behaelt_die_gruppen(auto):
    c, _buchen, lernen, kat, _emp = auto
    lernen("Frischekorb", "Lebensmittel")
    lernen("Glanz", "Drogerie")
    e1 = eigene_regel(c, "Eins", kat["Unklar"], "eins")["id"]
    e2 = eigene_regel(c, "Zwei", kat["Unklar"], "zwei")["id"]
    a1, a2 = [r["id"] for r in regeln(c) if r.get("automatisch")]
    r = c.post("/api/regeln/reihenfolge", json={"regel_ids": [a2, e2, a1, e1]})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()] == [e2, e1, a2, a1]
    assert [x["id"] for x in regeln(c)] == [e2, e1, a2, a1]


def test_uebernehmen_macht_eigene_regel_am_ende_der_eigenen(auto):
    c, buchen, lernen, kat, emp = auto
    lernen("Frischekorb", "Lebensmittel")
    lernen("Glanz", "Drogerie")
    e1 = eigene_regel(c, "Eins", kat["Unklar"], "eins")["id"]
    a1, a2 = [r["id"] for r in regeln(c) if r.get("automatisch")]
    vorher = c.get(f"/api/regeln/{a2}").json()
    r = c.post(f"/api/regeln/{a2}/uebernehmen")
    assert r.status_code == 200, r.text
    neu = r.json()
    assert "automatisch" not in neu and "empfaenger_id" not in neu
    assert (neu["name"], neu["kategorie_id"], neu["bedingungen"], neu["aktiv"]) == (
        vorher["name"], vorher["kategorie_id"], vorher["bedingungen"], vorher["aktiv"])
    assert [x["id"] for x in regeln(c)] == [e1, a2, a1]
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["aktion"] == "regel_uebernehmen" and vorher["name"] in a["beschreibung"]
    # eine neue eigene Regel kommt danach, aber weiter vor die automatischen
    e3 = eigene_regel(c, "Drei", kat["Unklar"], "drei")["id"]
    assert [x["id"] for x in regeln(c)] == [e1, a2, e3, a1]
    # Rückgängig: wieder automatisch und an alter Stelle
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    r2 = c.get(f"/api/regeln/{a2}").json()
    assert r2.get("automatisch") is True and r2["empfaenger_id"] == vorher["empfaenger_id"]
    assert r2["prioritaet"] == vorher["prioritaet"]


def test_geloeschte_uebernommene_regel_entsteht_nicht_wieder_automatisch(auto):
    c, buchen, lernen, _kat, _emp = auto
    lernen("Frischekorb", "Lebensmittel")
    (a,) = [r["id"] for r in regeln(c) if r.get("automatisch")]
    assert c.post(f"/api/regeln/{a}/uebernehmen").status_code == 200
    assert c.delete(f"/api/regeln/{a}").status_code in (200, 204)
    buchen("Frischekorb", "Lebensmittel", 3)
    assert regeln(c) == []


def test_uebernehmen_nur_fuer_automatische_regeln(auto):
    c, _buchen, _lernen, kat, _emp = auto
    e = eigene_regel(c, "Eins", kat["Unklar"], "eins")["id"]
    r = c.post(f"/api/regeln/{e}/uebernehmen")
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "regel_nicht_automatisch", r.text
    assert c.post("/api/regeln/999999/uebernehmen").status_code == 404


def test_oberflaeche_zeigt_zwei_abschnitte(client):
    js = client.get("/oeffentlich/app/regeleditor.js").text
    for tid in ("regeln-eigene", "regeln-automatisch", "regeln-automatisch-sortierung", "regeln-automatisch-suche",
                "regel-als-eigene-", "/uebernehmen"):
        assert tid in js, tid
