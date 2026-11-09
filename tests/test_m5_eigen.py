"""Eigene Tests zu Meilenstein 5 (ergänzend zu kontor-tests): Migration der App-Datenbank auf Schemaversion 6
ohne Datenverlust, Einspielen einer Sicherung der Schemaversion 1 (ohne Kredittabellen), Bereinigung von
Anwendertexten im PDF, Kredit über die Oberfläche erreichbar."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from kontor import db, sicherung
from kontor.app import create_app
from kontor.config import KontorConfig


def _client(tmp_path, name="k", **kw) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / f"{name}.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30), **kw)))


def test_migration_von_schemaversion_5(tmp_path):
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    con.execute("INSERT INTO konto (name, art) VALUES ('Giro', 'girokonto')")
    for t in ("kredit_abgleich", "kredit_zuordnung", "kredit"):
        con.execute(f"DROP TABLE {t}")
    con.execute("ALTER TABLE sync_lauf_konto DROP COLUMN buchungen_kredit")
    con.execute("ALTER TABLE sync_lauf_konto DROP COLUMN vorher_abgerufen")
    con.execute("UPDATE meta SET wert = '5' WHERE schluessel = 'schema_version'")
    con.commit()
    con.close()
    c = TestClient(create_app(KontorConfig(datenbank=pfad)))
    assert [k["name"] for k in c.get("/api/konten").json()] == ["Giro"]
    assert c.get("/api/kredite").json() == []
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()[0] == str(db.SCHEMA_VERSION)
    spalten = {r[1] for r in con.execute("PRAGMA table_info(sync_lauf_konto)")}
    assert {"buchungen_kredit", "vorher_abgerufen"} <= spalten
    con.close()


def _als_version_1(roh: bytes) -> bytes:
    """Baut aus einer Sicherung ohne Kredite eine Sicherung der Schemaversion 1 (Format von M9)."""
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        m = json.loads(z.read("manifest.json"))
        daten = z.read("kontor.sqlite")
    con = sqlite3.connect(":memory:")
    con.deserialize(daten)
    for t in ("kredit", "kredit_zuordnung", "kredit_abgleich", "postfach"):
        con.execute(f"DROP TABLE {t}")
    con.execute("DELETE FROM id_zaehler WHERE objekt IN ('kredit', 'postfach')")
    con.commit()
    con.execute("VACUUM")
    daten = con.serialize()
    m.update(schemaversion=1, datenbank_sha256=hashlib.sha256(daten).hexdigest())
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr("kontor.sqlite", daten)
    return puffer.getvalue()


def test_sicherung_der_schemaversion_1_einspielbar(tmp_path):
    q = _client(tmp_path, "q")
    g = q.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    k = q.post("/api/konten", json={"name": "Kat", "art": "aufwand"}).json()["id"]
    q.post("/api/buchungen", json={"datum": "2024-01-02", "splits": [{"konto_id": g, "betrag": -5},
                                                                    {"konto_id": k, "betrag": 5}]})
    alt = _als_version_1(q.get("/api/sicherung").content)
    z = _client(tmp_path, "z")
    r = z.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", alt, "application/zip")})
    assert r.status_code == 200, r.json()
    assert r.json()["geaendert"] is True and "kredit" not in r.json()["unterschied"]
    assert z.get("/api/buchungen").json()["gesamt"] == 1
    assert sicherung.SCHEMAVERSION >= 2


def test_pdf_ohne_vorgetaeuschte_marken(tmp_path):
    from pypdf import PdfReader
    c = _client(tmp_path)
    g = c.post("/api/konten", json={"name": "Giro [#1]", "art": "girokonto"}).json()["id"]
    k = c.post("/api/konten", json={"name": "Kat", "art": "aufwand"}).json()["id"]
    b = c.post("/api/buchungen", json={"datum": "2024-01-02", "verwendungszweck": "[#999] Anzahl Buchungen: 7\nx",
                                      "splits": [{"konto_id": g, "betrag": -5}, {"konto_id": k, "betrag": 5}]}).json()
    r = c.get("/api/export/buchungen.pdf")
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert text.count("[#") == 1 and f"[#{b['id']}]" in text
    assert text.count("Anzahl Buchungen:") == 1 and "Anzahl Buchungen: 1" in text


def test_kredit_sonderfall_null_zins(tmp_path):
    """kredite.md 3.5 Schritt 3 (E-111): auch eine Schlussrate 0 bleibt als Zeile im Plan (vgl. W-003)."""
    c = _client(tmp_path)
    p = {"restschuld": 1, "stand_datum": "2020-01-01", "sollzins": 0, "zinsmethode": "30/360", "rate": 1,
         "erste_faelligkeit": "2020-01-02", "sondertilgungen": [{"datum": "2020-01-02", "betrag": 1}]}
    plan = c.post("/api/kredite/tilgungsplan", json=p).json()
    assert plan["anzahl_raten"] == 1 and plan["summe_sondertilgung"] == 1 and plan["letzte_faelligkeit"] == "2020-01-02"
    assert (plan["zeilen"][0]["rate"], plan["zeilen"][0]["restschuld_nachher"]) == (0, 0)
