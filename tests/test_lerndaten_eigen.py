"""Lernmodell und automatische Regeln auf 3000 Buchungen nach echten Kontoauszugsmustern (tests/lerndaten.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

from . import lerndaten


def test_lerndaten_sind_reproduzierbar():
    a, b = lerndaten.erzeugen(), lerndaten.erzeugen()
    assert len(a) == lerndaten.ANZAHL and a == b
    assert sum(x["teil"] == "pruefung" for x in a) == lerndaten.ANZAHL // 5


def test_genauigkeit_mit_automatischen_regeln(tmp_path):
    b = lerndaten.erzeugen()
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", regeln_automatisch=True)))
    info = lerndaten.laden(c, b)
    name_von = {v: k for k, v in info["kategorien"].items()}
    pruef = [x for x in b if x["teil"] == "pruefung" and x["wahr"] in lerndaten.KATEGORIEN]
    auto = [r for r in c.get("/api/regeln").json() if r.get("automatisch")]
    assert "Shell Station Hauptstr. 12" not in {r["name"] for r in auto}  # zwei Kategorien: keine Regel
    assert "Amazon Payments Europe S.C.A." not in {r["name"] for r in auto}
    assert "REWE Markt GmbH" in {r["name"] for r in auto}
    c.post("/api/regeln/anwenden", json={"nur_unkategorisiert": True})
    c.post("/api/lernmodell/anwenden", json={})
    vorschlaege = richtig = 0
    for x in pruef:
        v = c.get(f"/api/buchungen/{info['ids'][x['nr']]}").json()["vorschlag"]
        if v:
            vorschlaege += 1
            richtig += name_von[v["kategorie_id"]] == x["wahr"]
    # Messung 2026-11-16: nur Lernmodell 99,2 % bei 89,0 % Abdeckung; mit Regeln 99,2 % bei 89,5 %
    assert richtig * 1000 >= vorschlaege * 990
    assert vorschlaege * 1000 >= len(pruef) * 890
