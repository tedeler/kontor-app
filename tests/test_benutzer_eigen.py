"""Eigene Tests zum Feature benutzer (D-324), die mehrere Apps brauchen (nicht in den Core-Tests: Zeitbudget)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def test_ohne_benutzer_leere_liste(client):
    assert client.get("/api/benutzer").json() == {"benutzer": []}


def test_neustart_mit_anderen_benutzern_laesst_tags_stehen(tmp_path):
    """Wer aus der Konfiguration verschwindet, behält seine Bestätigungs-Tags (gewöhnliche Tags)."""
    pfad = tmp_path / "k.sqlite3"
    c = TestClient(create_app(KontorConfig(datenbank=pfad, benutzer=["Anna", "Ben"])))
    c.post("/api/tags", json={"name": "Anna-Bestätigt"})
    c.post("/api/tags", json={"name": "Ben-Bestätigt"})
    c = TestClient(create_app(KontorConfig(datenbank=pfad, benutzer=["Clara"])))
    assert sorted(t["name"] for t in c.get("/api/tags").json()) == ["Anna-Bestätigt", "Ben-Bestätigt"]
    assert c.get("/api/benutzer").json() == {"benutzer": ["Clara"]}
