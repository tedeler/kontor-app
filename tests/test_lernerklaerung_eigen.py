"""Transparenz des Lernmodells (D-179): Erklärung je Buchung, Übersicht, Einstellungen der Instanz."""

from __future__ import annotations

from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


@pytest.fixture(scope="module")
def mock(tmp_path_factory):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path_factory.mktemp("m") / "m.sqlite3", mock_modus=True)))
    assert c.post("/api/mock/lerndaten").status_code == 200
    return c


def _buchung(c, text):
    r = c.get("/api/buchungen", params={"suche": text, "pro_seite": 5})
    return [b for b in r.json()["eintraege"] if text.lower() in b["verwendungszweck"].lower()][0]


def test_erklaerung_ist_exakt(mock):
    b = _buchung(mock, "Lieferando")
    e = mock.get(f"/api/buchungen/{b['id']}/lernmodell").json()
    v = mock.post("/api/lernmodell/vorhersage", json={"eintraege": [{"buchung_id": b["id"]}]}).json()["ergebnisse"][0]
    assert e["kandidaten"] == v["kandidaten"] and e["kategorie_id"] == v["kategorie_id"]
    assert e["grund"] in ("vorschlag", "unter_schwelle")
    # Verhältnis P(beste)/P(zweite) = Produkt aller Faktoren (Grundwert und bekannte Merkmale), bis auf Abrundung
    produkt = Fraction(e["grundwert"]["faktor_promille"], 1000)
    for m in e["merkmale"]:
        if m["bekannt"]:
            produkt *= Fraction(m["faktor_promille"], 1000)
    p1, p2 = (k["sicherheit"] for k in e["kandidaten"][:2])
    assert p2 == 0 or abs(produkt - Fraction(p1, max(p2, 1))) / produkt < Fraction(1, 5)
    assert e["aehnliche"] and all(a["kategorie_id"] for a in e["aehnliche"])
    wort = [m for m in e["merkmale"] if m["merkmal"] == "v:lieferando"][0]
    assert wort["anzahl_kategorie"] >= 1 and wort["faktor_promille"] > 1000


def test_gruende(mock):
    unbekannt = mock.post("/api/buchungen", json={"datum": "2026-11-01", "verwendungszweck": "xyzzy plugh",
                                                   "splits": [{"konto_id": 1, "betrag": -100}, {"konto_id": 2, "betrag": 100}]})
    assert unbekannt.status_code == 201, unbekannt.text
    e = mock.get(f"/api/buchungen/{unbekannt.json()['id']}/lernmodell").json()
    assert e["grund"] == "unbekannt" and e["kandidaten"] == [] and e["beste_kategorie_id"] is None
    assert mock.get("/api/buchungen/999999/lernmodell").status_code == 404
    amazon = _buchung(mock, "Amazon.de")
    assert mock.get(f"/api/buchungen/{amazon['id']}/lernmodell").json()["grund"] in ("unter_schwelle", "vorschlag")


def test_uebersicht(mock):
    u = mock.get("/api/lernmodell/uebersicht").json()
    p = u["pruefung"]
    assert u["trainingsbuchungen"] > 2000 and p["pruefbuchungen"] > 400
    assert p["richtig"] * 100 >= p["vorschlaege"] * 90 and p["vorschlaege"] * 100 >= p["pruefbuchungen"] * 80
    assert [s["schwelle_promille"] for s in p["je_schwelle"]] == list(range(500, 1000, 50))
    assert sum(v["anzahl"] for v in p["verlaesslichkeit"]) == p["pruefbuchungen"] - p["ohne_einschaetzung"]
    assert any(k["merkmale"] for k in u["kategorie_liste"])


def test_schwelle_einstellen(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True)))
    c.post("/api/mock/lerndaten")
    amazon = _buchung(c, "Amazon.de")
    vorher = c.post("/api/lernmodell/vorhersage", json={"eintraege": [{"buchung_id": amazon["id"]}]}).json()["ergebnisse"][0]
    assert c.put("/api/lernmodell/einstellungen", json={"schwelle_promille": 400}).status_code == 422
    assert c.put("/api/lernmodell/einstellungen", json={"schwelle_promille": 700, "x": 1}).status_code == 422
    r = c.put("/api/lernmodell/einstellungen", json={"schwelle_promille": 500})
    assert r.status_code == 200 and r.json()["schwelle_promille"] == 500
    assert c.get("/api/lernmodell").json()["schwelle_promille"] == 500
    nachher = c.post("/api/lernmodell/vorhersage", json={"eintraege": [{"buchung_id": amazon["id"]}]}).json()["ergebnisse"][0]
    oben = vorher["kandidaten"][0]["sicherheit"]
    assert (nachher["kategorie_id"] is not None) == (oben >= 500)


def test_automatische_regeln_per_einstellung(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True)))
    assert c.get("/api/lernmodell/einstellungen").json()["regeln_automatisch"] is False
    c.put("/api/lernmodell/einstellungen", json={"regeln_automatisch": True})
    c.post("/api/mock/lerndaten")
    assert any(r.get("automatisch") for r in c.get("/api/regeln").json())
