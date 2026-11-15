"""Mail-Blatt: abgerufene Mails tragen ihre Zuordnung (D-147)."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.plugins.mock_daten import _amazon_bestellung


def test_nachricht_nennt_zuordnung_und_buchung(tmp_path):
    c = TestClient(create_app(KontorConfig(
        datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 15), mail_abgleich=True)))
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Onlinekäufe", "art": "aufwand"}).json()["id"]
    nr, cent, _ = _amazon_bestellung(2024, 6)
    r = c.post("/api/buchungen/erfassen", json={
        "art": "ausgabe", "datum": "2024-06-11", "konto_id": giro, "betrag": cent,
        "kategorie_id": kat, "empfaenger_name": "AMAZON PAYMENTS EUROPE (fiktiv)",
        "verwendungszweck": f"{nr} AMZN Mktp DE Testdaten"})
    assert r.status_code == 201, r.text
    for adresse in ("haushalt.eins@example.invalid", "haushalt.zwei@example.invalid"):
        assert c.post("/api/mail/postfaecher", json={"adresse": adresse}).status_code == 201
    assert c.post("/api/mail/abruf").status_code == 200
    antwort = c.get("/api/mail/nachrichten", params={"pro_seite": 50}).json()
    mails = antwort["eintraege"]
    amazon = next(m for m in mails if "Bestellung" in m["betreff"] and "Amazon" in m["betreff"])
    assert amazon["zuordnung"][0]["kennung"] == nr
    buchung = amazon["zuordnung"][0]["buchungen"][0]
    assert buchung["konto_id"] == giro
    assert nr in buchung["warum"] and "Verwendungszweck" in buchung["warum"]
    assert antwort["stand"]["gesamt"] >= 1 and antwort["stand"]["zugeordnet"] >= 1
    paypal = next(m for m in mails if m["absender"].startswith("service@paypal"))
    assert paypal["zuordnung"] and paypal["zuordnung"][0]["buchungen"] == []
    assert any(m["zuordnung"] == [] for m in mails)
    assert c.get("/mail").status_code == 200
    assert 'data-testid="navlink-mail"' in c.get("/").text
