"""Core-Tests zum Feature „buchung-teilen“ (D-304): Kontextmenü „Teilen…“ einer Buchung mit Kurztext und Link auf das
Kontoblatt mit markierter Buchung. Das Teilen selbst geschieht im Browser (Teilen-Funktion des Geräts, sonst
Zwischenablage); hier geprüft werden der Eintrag und das Sprungziel des Links."""

from __future__ import annotations


def test_kontextmenue_hat_teilen(auslieferung):
    js = auslieferung.get("/oeffentlich/app/konto.js").text
    assert 'tid: "km-teilen"' in js
    assert "navigator.share" in js and "navigator.clipboard" in js


def test_link_ziel_ist_das_kontoblatt_mit_sprungziel(client):
    """Der geteilte Link `/konten/<id>?buchung=<id>` ist eine Seite der Oberfläche (Sprungziel D-118, kein Filter)."""
    konto = client.post("/api/konten", json={"name": "Giro T", "art": "girokonto"}).json()["id"]
    r = client.get(f"/konten/{konto}", params={"buchung": 1})
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
