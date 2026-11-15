"""Filter aus dem Kontextmenü (D-158): gleicher und ähnlicher Empfänger, gleicher und ähnlicher Verwendungszweck."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30))))


def _buchung(c, giro, kat, name, zweck):
    empf = c.post("/api/empfaenger", json={"name": name}).json()["id"]
    r = c.post("/api/buchungen", json={"datum": "2024-01-01", "empfaenger_id": empf, "verwendungszweck": zweck,
                                       "splits": [{"konto_id": giro, "betrag": -100}, {"konto_id": kat, "betrag": 100}]})
    assert r.status_code == 201, r.text
    return empf, r.json()["id"]


def _ids(c, **params):
    r = c.get("/api/buchungen", params={"pro_seite": 50, **params})
    assert r.status_code == 200, r.text
    return {b["id"] for b in r.json()["eintraege"]}


def test_zweck_gleich_und_aehnlich(tmp_path):
    c = _client(tmp_path)
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Miete", "art": "aufwand"}).json()["id"]
    _, rate = _buchung(c, giro, kat, "Hausbank", "Rate 2024-02-01 (Testdaten)")
    _, rate2 = _buchung(c, giro, kat, "Autobank", "Rate 2024-03-01 (Testdaten)")
    _, miete = _buchung(c, giro, kat, "Vermieter", "Miete Juni")
    _, leer = _buchung(c, giro, kat, "Kiosk", "")
    assert _ids(c, zweck_gleich="Rate 2024-02-01 (Testdaten)") == {rate}
    assert _ids(c, zweck_gleich="rate 2024-02-01 (testdaten)") == {rate}
    assert _ids(c, zweck_aehnlich="Rate 2024-02-01 (Testdaten)") == {rate, rate2}
    assert _ids(c, zweck_aehnlich="Miete Juli") == {miete}
    assert _ids(c, zweck_leer="true") == {leer}
    assert _ids(c, verwendungszweck="Rate") == {rate, rate2}


def test_empfaenger_aehnlich(tmp_path):
    c = _client(tmp_path)
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Kauf", "art": "aufwand"}).json()["id"]
    amazon, a = _buchung(c, giro, kat, "AMAZON PAYMENTS EUROPE", "Kauf")
    eu, e = _buchung(c, giro, kat, "AMAZON EU", "Kauf 2")
    haus, h = _buchung(c, giro, kat, "Hausbank Baufinanz", "Rate")
    auto, u = _buchung(c, giro, kat, "Autobank Mobil", "Rate 2")
    assert _ids(c, empfaenger_aehnlich="AMAZON PAYMENTS EUROPE") == {a, e}
    assert _ids(c, empfaenger_aehnlich="Hausbank") == {h}
    assert u not in _ids(c, empfaenger_aehnlich="Hausbank Baufinanz")
    assert _ids(c, empfaenger_id=amazon) == {a}
    assert auto != amazon
