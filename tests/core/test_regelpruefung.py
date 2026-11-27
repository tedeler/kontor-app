"""Core-Tests zum Feature „regelpruefung“: automatisch angelegte Regeln auf Inkonsistenzen prüfen (D-307).

- ``GET /api/regeln/pruefung`` prüft jede aktive automatisch angelegte Regel gegen die Bedingungen ihrer Anlage
  (lernmodell.md 9.1: mindestens 5 Zuordnungen zur Kategorie der Regel, mindestens 95 % aller Buchungen des
  Empfängers, mindestens 95 % im Fenster von 365 Tagen bis zu seiner jüngsten Buchung). Gilt eine nicht mehr,
  erscheint die Regel mit ``grund`` und kurzem ``hinweis``. Nur lesend; eigene und deaktivierte Regeln nicht.
- Das Löschen einer automatischen Regel sperrt den Empfänger nicht mehr: Sie darf später wieder entstehen. Eine
  deaktivierte automatische Regel verhindert eine neue, solange sie besteht.
- Die Regelansicht zeigt Regeln mit Hinweis zuerst und deaktivierte Regeln in einem eigenen Bereich ganz unten.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

JS = Path(__file__).resolve().parents[2] / "src/kontor/web/oeffentlich/app/regeleditor.js"


@pytest.fixture
def auto(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "kontor.sqlite3", regeln_automatisch=True)))
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = {n: c.post("/api/konten", json={"name": n, "art": "aufwand"}).json()["id"]
           for n in ("Lebensmittel", "Drogerie")}
    emp = {n: c.post("/api/empfaenger", json={"name": n}).json()["id"] for n in ("Frischekorb", "Glanz")}
    heute = dt.date.today()

    def buchen(empf, kategorie, tage_her=10):
        r = c.post("/api/buchungen", json={
            "datum": (heute - dt.timedelta(days=tage_her)).isoformat(), "empfaenger_id": emp[empf],
            "verwendungszweck": "Kartenzahlung",
            "splits": [{"konto_id": g, "betrag": -1234}, {"konto_id": kat[kategorie], "betrag": 1234}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def umhaengen(bid, kategorie):
        r = c.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": kat[kategorie]})
        assert r.status_code == 200, r.text

    return c, buchen, umhaengen, kat, emp


def automatische(c):
    return [r for r in c.get("/api/regeln").json() if r.get("automatisch")]


def pruefung(c):
    r = c.get("/api/regeln/pruefung")
    assert r.status_code == 200, r.text
    return {x["regel_id"]: x for x in r.json()["regeln"]}


def test_stimmige_regel_ohne_hinweis(auto):
    c, buchen, _u, _kat, _emp = auto
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    assert len(automatische(c)) == 1
    assert pruefung(c) == {}


def test_zu_wenige_zuordnungen(auto):
    c, buchen, umhaengen, _kat, _emp = auto
    ids = [buchen("Frischekorb", "Lebensmittel", 10 + i) for i in range(5)]
    (r,) = automatische(c)
    umhaengen(ids[0], "Drogerie")
    p = pruefung(c)
    assert set(p) == {r["id"]}
    assert p[r["id"]]["grund"] == "anzahl"
    assert "4" in p[r["id"]]["hinweis"] and "Lebensmittel" in p[r["id"]]["hinweis"]


def test_anteil_unter_95_prozent(auto):
    c, buchen, umhaengen, _kat, _emp = auto
    ids = [buchen("Frischekorb", "Lebensmittel", 10 + i) for i in range(20)]
    (r,) = automatische(c)
    umhaengen(ids[0], "Drogerie")          # 19 von 20 = 95 %: noch stimmig
    assert pruefung(c) == {}
    umhaengen(ids[1], "Drogerie")          # 18 von 20 = 90 %
    p = pruefung(c)[r["id"]]
    assert p["grund"] == "anteil" and "90 %" in p["hinweis"]


def test_fenster_der_letzten_zwoelf_monate(auto):
    c, buchen, _u, _kat, _emp = auto
    for i in range(40):
        buchen("Frischekorb", "Lebensmittel", 800 + i)   # alt, außerhalb des Fensters
    (r,) = automatische(c)
    for i in range(3):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    buchen("Frischekorb", "Drogerie", 5)                 # gesamt 43 von 44, im Fenster 3 von 4
    p = pruefung(c)[r["id"]]
    assert p["grund"] == "fenster" and "75 %" in p["hinweis"]


def test_bearbeitete_kategorie_zaehlt(auto):
    c, buchen, umhaengen, kat, _emp = auto
    ids = [buchen("Frischekorb", "Lebensmittel", 10 + i) for i in range(5)]
    (r,) = automatische(c)
    for b in ids:
        umhaengen(b, "Drogerie")
    assert set(pruefung(c)) == {r["id"]}
    assert c.patch(f"/api/regeln/{r['id']}", json={"kategorie_id": kat["Drogerie"]}).status_code == 200
    assert pruefung(c) == {}


def test_nur_aktive_automatische_regeln_und_nur_lesend(auto):
    c, buchen, umhaengen, kat, _emp = auto
    ids = [buchen("Frischekorb", "Lebensmittel", 10 + i) for i in range(5)]
    (r,) = automatische(c)
    umhaengen(ids[0], "Drogerie")
    c.post("/api/regeln", json={"name": "Eigen", "kategorie_id": kat["Drogerie"], "bedingungen": [
        {"feld": "empfaenger", "operator": "gleich", "wert": "Frischekorb"}]})
    vorher = c.get("/api/aenderungen").json()["eintraege"]
    assert set(pruefung(c)) == {r["id"]}
    assert c.get("/api/aenderungen").json()["eintraege"] == vorher
    assert c.patch(f"/api/regeln/{r['id']}", json={"aktiv": False}).status_code == 200
    assert pruefung(c) == {}


def test_geloeschte_automatische_regel_entsteht_wieder(auto):
    c, buchen, _u, _kat, emp = auto
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    (r,) = automatische(c)
    assert c.delete(f"/api/regeln/{r['id']}").status_code in (200, 204)
    e = c.get(f"/api/empfaenger/{emp['Frischekorb']}").json()
    assert "lernregel_gesperrt" not in e
    buchen("Frischekorb", "Lebensmittel", 3)
    (neu,) = automatische(c)
    assert neu["empfaenger_id"] == emp["Frischekorb"] and neu["id"] != r["id"]


def test_deaktivierte_automatische_regel_verhindert_neue(auto):
    c, buchen, _u, _kat, _emp = auto
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    (r,) = automatische(c)
    assert c.patch(f"/api/regeln/{r['id']}", json={"aktiv": False}).status_code == 200
    buchen("Frischekorb", "Lebensmittel", 3)
    assert [x["id"] for x in automatische(c)] == [r["id"]]


def test_oberflaeche_kennt_hinweise_und_bereich_deaktiviert():
    js = JS.read_text(encoding="utf-8")
    for teil in ("/api/regeln/pruefung", "regel-hinweis-", "regeln-deaktiviert", "Deaktiviert (",
                 "legt Kontor für diesen Empfänger keine neue an"):
        assert teil in js, teil
