"""Eigene Tests zu Meilenstein 3 (ergänzend zu kontor-tests): Migration, Protokoll-Details, Entscheidungen."""

from __future__ import annotations

import datetime as dt
import pathlib
import sqlite3

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

SCHEMA_M2 = pathlib.Path(__file__).parent / "daten" / "schema_m2.sql"


def _client(tmp_path, **kw) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30), **kw)))


def test_migration_von_schemaversion_2_ohne_datenverlust(tmp_path):
    """Eine Datenbank aus M2 (mit Vorschlag) wird beim Start auf Schemaversion 3 gebracht."""
    pfad = tmp_path / "k.sqlite3"
    con = sqlite3.connect(pfad)
    con.executescript(SCHEMA_M2.read_text(encoding="utf-8"))
    con.executescript("""
        INSERT INTO meta VALUES ('schema_version', '2');
        INSERT INTO konto (id, name, art, iban) VALUES (1, 'Giro', 'girokonto', NULL);
        INSERT INTO konto (id, name, art) VALUES (2, 'Lebensmittel', 'aufwand');
        INSERT INTO konto (id, name, art, extern_id) VALUES (3, 'Unkategorisiert', 'eigenkapital',
                                                             'kontor:unkategorisiert');
        INSERT INTO empfaenger (id, name) VALUES (1, 'Markt');
        INSERT INTO buchung (id, datum, empfaenger_id, verwendungszweck, status)
            VALUES (1, '2024-01-02', 1, 'Einkauf', 'importiert');
        INSERT INTO split (id, buchung_id, position, konto_id, betrag, memo) VALUES (1, 1, 0, 1, -500, '');
        INSERT INTO split (id, buchung_id, position, konto_id, betrag, memo) VALUES (2, 1, 1, 2, 500, '');
        INSERT INTO regel (id, name, aktiv, prioritaet, kategorie_id, bedingungen)
            VALUES (1, 'Markt', 1, 100, 2, '[{"feld": "empfaenger", "operator": "enthaelt", "wert": "markt"}]');
        INSERT INTO vorschlag VALUES (1, 2, 1, 'regel', 3);
    """)
    con.commit()
    con.close()
    c = TestClient(create_app(KontorConfig(datenbank=pfad)))
    b = c.get("/api/buchungen/1").json()
    assert b["vorschlag"] == {"kategorie_id": 2, "regel_id": 1, "quelle": "regel", "vorher_konto_id": 3}
    assert b["gegen_iban"] is None and b["abgestimmt"] is False and b["ist_umbuchung"] is False
    assert [s["abstimmung_id"] for s in b["splits"]] == [None, None]
    assert c.get("/api/empfaenger/1").json() == {"id": 1, "name": "Markt", "extern_id": None, "aliase": [],
                                                 "standardkategorie_id": None}
    # Neue Funktionen arbeiten auf der migrierten Datenbank
    assert c.patch("/api/empfaenger/1", json={"aliase": ["MARKT GMBH"], "standardkategorie_id": 2}).status_code == 200
    r = c.post("/api/abstimmungen", json={"konto_id": 1, "stichtag": "2024-01-31", "saldo": -500}).json()
    assert r["abgestimmt"] is True
    alle = c.get("/api/aenderungen").json()
    assert [a["aktion"] for a in alle["eintraege"]] == ["abstimmung_anlegen", "empfaenger_aendern"]
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()[0] == "4"
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name = 'vorschlag'").fetchone()[0]
    assert "standardkategorie" in sql
    con.close()


def test_tag_umbenennen_rueckgaengig_behaelt_zuordnungen(tmp_path):
    c = _client(tmp_path)
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    lm = c.post("/api/konten", json={"name": "LM", "art": "aufwand"}).json()["id"]
    t = c.post("/api/tags", json={"name": "Urlaub"}).json()["id"]
    b = c.post("/api/buchungen", json={"datum": "2024-01-01", "tag_ids": [t], "splits": [
        {"konto_id": g, "betrag": -1}, {"konto_id": lm, "betrag": 1}]}).json()["id"]
    c.patch(f"/api/tags/{t}", json={"name": "Ferien"})
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    assert c.get(f"/api/buchungen/{b}").json()["tags"] == [{"id": t, "name": "Urlaub"}]


def test_probelauf_loeschen_verbraucht_keine_ids(tmp_path):
    """Der Probelauf läuft in einem Sicherungspunkt; ein dabei angelegtes „Unkategorisiert“ verschwindet."""
    c = _client(tmp_path)
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    lm = c.post("/api/konten", json={"name": "LM", "art": "aufwand"}).json()["id"]
    c.post("/api/buchungen", json={"datum": "2024-01-01", "splits": [
        {"konto_id": g, "betrag": -1}, {"konto_id": lm, "betrag": 1}]})
    r = c.post(f"/api/konten/{lm}/loeschen", json={"buchungen": "unkategorisiert", "konflikte": "behalten",
                                                   "trocken": True}).json()
    assert r["ziel_konto_id"] is None and r["aenderung_id"] is None
    neu = c.post("/api/konten", json={"name": "Neu", "art": "aufwand"}).json()["id"]
    assert neu == lm + 1


def test_tan_und_pin_nie_im_protokoll(tmp_path):
    c = _client(tmp_path, mock_szenario="tan_erforderlich")
    c.put("/api/sync/pin", json={"pin": "geheim-4711"})
    lauf = c.post("/api/sync", json={}).json()
    tan = c.get(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}").json()
    assert tan["status"] == "offen"
    text = c.get("/api/aenderungen", params={"pro_seite": 500}).text
    assert "geheim-4711" not in text
