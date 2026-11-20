"""D-219: Die Standardkategorie je Empfänger ist entfallen; vorhandene werden zu Regeln."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kontor import db
from kontor.app import create_app


def test_feld_wird_nicht_mehr_angenommen(client):
    kat = client.post("/api/konten", json={"name": "Essen", "art": "aufwand"}).json()["id"]
    r = client.post("/api/empfaenger", json={"name": "Markt", "standardkategorie_id": kat})
    assert r.status_code == 422, r.text
    e = client.post("/api/empfaenger", json={"name": "Markt", "standardkategorie_id": None}).json()
    assert e["standardkategorie_id"] is None
    assert client.patch(f"/api/empfaenger/{e['id']}", json={"standardkategorie_id": kat}).status_code == 422


def test_altbestand_wird_zu_regeln(config):
    c = TestClient(create_app(config))
    kat = c.post("/api/konten", json={"name": "Essen", "art": "aufwand"}).json()["id"]
    c.post("/api/regeln", json={"name": "Vorhanden", "kategorie_id": kat,
                                "bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": "x"}]})
    e = c.post("/api/empfaenger", json={"name": "Markt", "aliase": ["MARKT GMBH"]}).json()
    c.post("/api/empfaenger", json={"name": "Ohne"})
    con = db.verbinde(config.aktive_datenbank)
    con.execute("UPDATE empfaenger SET standardkategorie_id = ? WHERE id = ?", (kat, e["id"]))
    con.close()
    c = TestClient(create_app(config))
    regeln = c.get("/api/regeln").json()
    assert [(r["name"], r["kategorie_id"]) for r in regeln] == [("Vorhanden", kat), ("Markt", kat)]
    assert regeln[1]["prioritaet"] > regeln[0]["prioritaet"]
    assert all(x["standardkategorie_id"] is None for x in c.get("/api/empfaenger").json())
    letzte = c.get("/api/aenderungen").json()["eintraege"][0]
    assert letzte["beschreibung"].startswith("Standardkategorien in Regeln umgewandelt")
    # zweiter Start legt nichts mehr an
    assert len(TestClient(create_app(config)).get("/api/regeln").json()) == 2
