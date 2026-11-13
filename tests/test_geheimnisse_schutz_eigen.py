"""Entwicklungstests für das Feature „geheimnisse“ (Branch feature/geheimnisse, D-129): Schutz der Geheimnisse mit
dem Login-Passwort (Schlüsselhülle), Entsperren über Login und Dialog, Passwortwechsel und -zurücksetzen, gemerkte
Bank-PIN. Synthetische Werte; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kontor import anmeldung, db
from kontor.app import create_app
from kontor.config import KontorConfig

PASSWORT = "ein-langes-testpasswort-1"
GEHEIM = "fiktives-client-secret-123"


def neu(tmp_path, **kw):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=False, planer_starten=False, **kw)
    return TestClient(create_app(cfg)), cfg


def lesbar(c) -> dict:
    return {e["name"]: e["lesbar"] for e in c.get("/api/geheimnisse").json()["eintraege"]}


@pytest.fixture
def geschuetzt(tmp_path):
    c, cfg = neu(tmp_path)
    anmeldung.passwort_setzen(cfg, PASSWORT)
    assert c.put("/api/geheimnisse/oauth_client_secret", json={"wert": GEHEIM}).status_code == 204
    assert c.put("/api/geheimnisse/ntfy_token", json={"wert": "fiktiver-ntfy-token"}).status_code == 204
    r = c.post("/api/geheimnisse/schutz", json={"passwort": PASSWORT})
    assert r.status_code == 200, r.text
    assert r.json() == {"aktiv": True, "entsperrt": True, "gesperrt": False, "geschuetzt": 1, "pin_gemerkt": False}
    return c, cfg, tmp_path


def test_ohne_schutz_unveraendert(tmp_path):
    c, _ = neu(tmp_path)
    assert c.get("/api/geheimnisse/schutz").json()["aktiv"] is False
    assert c.post("/api/geheimnisse/schutz", json={"passwort": PASSWORT}).status_code == 409  # kein Login-Passwort
    assert c.put("/api/sync/pin/gemerkt", json={"pin": "12345"}).status_code == 409


def test_falsches_passwort_und_doppelt(tmp_path):
    c, cfg = neu(tmp_path)
    anmeldung.passwort_setzen(cfg, PASSWORT)
    r = c.post("/api/geheimnisse/schutz", json={"passwort": "falsch-falsch-falsch"})
    assert r.status_code == 403 and "falsch-falsch" not in r.text
    assert c.post("/api/geheimnisse/schutz", json={"passwort": PASSWORT}).status_code == 200
    assert c.post("/api/geheimnisse/schutz", json={"passwort": PASSWORT}).status_code == 409


def test_neustart_gesperrt_entsperren_und_sperren(geschuetzt):
    c, cfg, tmp_path = geschuetzt
    con = db.verbinde(cfg.aktive_datenbank)
    roh = b"".join(bytes(r[0]) for r in con.execute("SELECT chiffre FROM geheimnis"))
    huelle = con.execute("SELECT * FROM geheimnis_huelle").fetchone()
    con.close()
    assert GEHEIM.encode() not in roh and PASSWORT.encode() not in bytes(huelle["chiffre"])
    c2, _ = neu(tmp_path)                                    # Neustart: Datenschlüssel fehlt
    assert c2.get("/api/geheimnisse/schutz").json()["gesperrt"] is True
    assert lesbar(c2) == {"ntfy_token": True, "oauth_client_secret": False}
    r = c2.put("/api/geheimnisse/oauth_client_secret", json={"wert": "x"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "geheimnisse_gesperrt"
    assert c2.post("/api/geheimnisse/entsperren", json={"passwort": "falsch-falsch-falsch"}).status_code == 403
    assert c2.post("/api/geheimnisse/entsperren", json={"passwort": PASSWORT}).json()["entsperrt"] is True
    assert lesbar(c2) == {"ntfy_token": True, "oauth_client_secret": True}
    assert c2.post("/api/geheimnisse/sperren").json()["gesperrt"] is True
    assert lesbar(c2)["oauth_client_secret"] is False


def test_login_entsperrt(geschuetzt):
    _, _, tmp_path = geschuetzt
    c, _ = neu(tmp_path, anmeldung=True)
    assert c.post("/api/anmeldung", json={"passwort": PASSWORT}).status_code == 200
    assert c.get("/api/geheimnisse/schutz").json()["entsperrt"] is True
    assert lesbar(c)["oauth_client_secret"] is True


def test_ausschalten_und_zuruecksetzen(geschuetzt):
    c, cfg, tmp_path = geschuetzt
    assert c.post("/api/geheimnisse/schutz/ausschalten", json={"passwort": PASSWORT}).json()["aktiv"] is False
    c2, _ = neu(tmp_path)
    assert lesbar(c2)["oauth_client_secret"] is True          # wieder nur Systemschlüssel
    assert c2.post("/api/geheimnisse/schutz", json={"passwort": PASSWORT}).status_code == 200
    anmeldung.passwort_setzen(cfg, "ein-ganz-neues-passwort-2")  # Zurücksetzen ohne altes Passwort
    c3, _ = neu(tmp_path)
    assert c3.get("/api/geheimnisse/schutz").json()["aktiv"] is False
    assert lesbar(c3) == {"ntfy_token": True}                 # geschützte Geheimnisse verloren


def test_passwortwechsel_verpackt_neu(geschuetzt):
    _, _, tmp_path = geschuetzt
    c, _ = neu(tmp_path, anmeldung=True)
    csrf = c.post("/api/anmeldung", json={"passwort": PASSWORT}).json()["csrf_token"]
    r = c.put("/api/anmeldung/passwort", headers={"X-Kontor-CSRF": csrf, "Origin": "http://testserver"},
              json={"altes_passwort": PASSWORT, "neues_passwort": "ein-ganz-neues-passwort-2"})
    assert r.status_code == 200, r.text
    c2, _ = neu(tmp_path)
    assert c2.post("/api/geheimnisse/entsperren", json={"passwort": PASSWORT}).status_code == 403
    assert c2.post("/api/geheimnisse/entsperren", json={"passwort": "ein-ganz-neues-passwort-2"}).status_code == 200
    assert lesbar(c2)["oauth_client_secret"] is True


def test_pin_merken_neustart_und_vergessen(geschuetzt):
    c, cfg, tmp_path = geschuetzt
    assert c.put("/api/sync/pin/gemerkt", json={"pin": "12345"}).status_code == 204
    assert c.get("/api/geheimnisse/schutz").json()["pin_gemerkt"] is True
    c2, _ = neu(tmp_path)
    assert c2.get("/api/sync/status").json()["pin_vorhanden"] is False      # gesperrt: keine PIN
    c2.post("/api/geheimnisse/entsperren", json={"passwort": PASSWORT})
    assert c2.get("/api/sync/status").json()["pin_vorhanden"] is True       # gemerkte PIN ohne Eingabe
    assert c2.delete("/api/sync/pin").status_code == 204                    # „PIN verwerfen“ vergisst auch sie
    assert c2.get("/api/sync/status").json()["pin_vorhanden"] is False
    assert c2.get("/api/geheimnisse/schutz").json()["pin_gemerkt"] is False
