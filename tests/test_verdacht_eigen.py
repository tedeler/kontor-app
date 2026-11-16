"""Verdächtige Buchungen (D-157): neuer Empfänger oder stark abweichender Betrag, weg nach Bestätigung."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30))))


def _geruest(c):
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Miete", "art": "aufwand"}).json()["id"]
    return giro, kat


def _buchung(c, giro, kat, name, cent, status, datum="2024-01-01"):
    empf = c.post("/api/empfaenger", json={"name": name}).json()["id"]
    return empf, _an(c, giro, kat, empf, cent, status, datum)


def _an(c, giro, kat, empf, cent, status, datum):
    r = c.post("/api/buchungen", json={"datum": datum, "empfaenger_id": empf, "status": status,
                                       "splits": [{"konto_id": giro, "betrag": -cent},
                                                  {"konto_id": kat, "betrag": cent}]})
    assert r.status_code == 201, r.text
    return r.json()


def test_nur_unbestaetigt_und_weg_nach_bestaetigung(tmp_path):
    c = _client(tmp_path)
    giro, kat = _geruest(c)
    _, b = _buchung(c, giro, kat, "Neue Firma", 4200, "importiert")
    assert "verdacht" not in b   # nie in Antworten schreibender Aufrufe (D-171)
    b = c.get(f"/api/buchungen/{b['id']}", params={"verdacht": "ja"}).json()
    assert b["verdacht"]["grund"] == "empfaenger"
    assert "Neue Firma" in b["verdacht"]["text"]
    assert "nur in unbestätigten" in b["verdacht"]["text"]
    best = c.patch(f"/api/buchungen/{b['id']}", json={"status": "bestaetigt"}).json()
    assert "verdacht" not in best


def test_gleicher_betrag_ist_nicht_verdaechtig(tmp_path):
    c = _client(tmp_path)
    giro, kat = _geruest(c)
    empf, _ = _buchung(c, giro, kat, "Vermieter", 80000, "bestaetigt", "2024-01-01")
    for monat in ("02", "03", "04"):
        _an(c, giro, kat, empf, 80000, "bestaetigt", f"2024-{monat}-01")
    neu = _an(c, giro, kat, empf, 80000, "importiert", "2024-05-01")
    assert "verdacht" not in c.get(f"/api/buchungen/{neu['id']}", params={"verdacht": "ja"}).json()


def test_starker_abweichender_betrag(tmp_path):
    c = _client(tmp_path)
    giro, kat = _geruest(c)
    empf, _ = _buchung(c, giro, kat, "Vermieter", 80000, "bestaetigt", "2024-01-01")
    for monat in ("02", "03", "04"):
        _an(c, giro, kat, empf, 80000, "bestaetigt", f"2024-{monat}-01")
    neu = _an(c, giro, kat, empf, 250000, "vorlaeufig", "2024-05-01")
    v = c.get(f"/api/buchungen/{neu['id']}", params={"verdacht": "ja"}).json()["verdacht"]
    assert v["grund"] == "betrag"
    assert "2.500,00 €" in v["text"] and "800,00 €" in v["text"]
    klein = _an(c, giro, kat, empf, 81000, "importiert", "2024-05-02")
    assert "verdacht" not in c.get(f"/api/buchungen/{klein['id']}", params={"verdacht": "ja"}).json()
    c.patch(f"/api/buchungen/{neu['id']}", json={"status": "abgeglichen"})
    assert "verdacht" not in c.get(f"/api/buchungen/{neu['id']}", params={"verdacht": "ja"}).json()


def test_streuung_mit_robustem_z(tmp_path):
    c = _client(tmp_path)
    giro, kat = _geruest(c)
    empf = c.post("/api/empfaenger", json={"name": "Markt"}).json()["id"]
    for i, cent in enumerate((10000, 12000, 8000, 11000, 9000)):
        _an(c, giro, kat, empf, cent, "bestaetigt", f"2024-01-{i + 1:02d}")
    neu = _an(c, giro, kat, empf, 80000, "importiert", "2024-02-01")
    v = c.get(f"/api/buchungen/{neu['id']}", params={"verdacht": "ja"}).json()["verdacht"]
    assert v["grund"] == "betrag" and "robustes z" in v["text"]
    liste = c.get("/api/buchungen", params={"empfaenger_id": empf, "pro_seite": 20, "verdacht": "ja"}).json()["eintraege"]
    markiert = [b for b in liste if "verdacht" in b]
    assert [b["id"] for b in markiert] == [neu["id"]]
