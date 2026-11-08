"""Eigene Tests zu Entscheidungen aus Meilenstein 2 (ergänzend zu kontor-tests)."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.plugins.mock_bank import qr_bild


def _client(tmp_path, **kw) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30), **kw)))


def test_vorgabeprioritaet_gedeckelt(tmp_path):
    """D-031: Vorgabepriorität höchstens 1 000 000."""
    c = _client(tmp_path)
    kat = c.post("/api/konten", json={"name": "Café", "art": "aufwand"}).json()["id"]
    bed = [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": "x"}]
    c.post("/api/regeln", json={"name": "a", "kategorie_id": kat, "bedingungen": bed, "prioritaet": 999_995})
    r = c.post("/api/regeln", json={"name": "b", "kategorie_id": kat, "bedingungen": bed}).json()
    assert r["prioritaet"] == 1_000_000


def test_eingebauter_datensatz_synchronisiert(tmp_path):
    c = _client(tmp_path)
    lauf = c.post("/api/sync", json={}).json()
    assert lauf["status"] == "erfolgreich" and len(lauf["konten"]) == 2
    assert all(k["buchungen_neu"] > 0 for k in lauf["konten"])
    # Die Umbuchung Giro → Tagesgeld erscheint auf beiden Seiten als eigene Buchung gegen „Unkategorisiert“
    # (Umbuchungserkennung ist M3).
    assert c.post("/api/sync", json={}).json()["konten"][0]["buchungen_neu"] == 0


def test_qr_bild_deterministisch_ohne_kennung():
    a, b = qr_bild("MOCK-TAN-2024-06-30"), qr_bild("MOCK-TAN-2024-06-30")
    assert a == b and a.startswith(b"\x89PNG\r\n\x1a\n") and b"MOCK-TAN" not in a
    assert qr_bild("MOCK-TAN-2024-07-01") != a


def test_tan_bild_nur_bei_offener_anforderung(tmp_path):
    c = _client(tmp_path, mock_szenario="tan_erforderlich")
    lauf = c.post("/api/sync", json={}).json()
    tid = lauf["tan_anforderung_id"]
    assert c.get(f"/api/tan-anforderungen/{tid}/bild").headers["content-type"] == "image/png"
    c.post(f"/api/tan-anforderungen/{tid}/abbrechen")
    assert c.get(f"/api/tan-anforderungen/{tid}/bild").status_code == 404
    assert c.get(f"/api/tan-anforderungen/{tid}").json()["hat_bild"] is True
