"""Eigene M7-Tests: Migration auf Schemaversion 8, Anmeldedaten nicht in der Sicherung, CSRF-Ableitung."""

from __future__ import annotations

import io
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from kontor import anmeldung, db, sicherung
from kontor.app import create_app
from kontor.config import KontorConfig

PASSWORT = "Synthetisch-Eigen-2026"


def test_migration_von_schemaversion_7(tmp_path):
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    con.execute("INSERT INTO konto (name, art) VALUES ('Alt', 'girokonto')")
    con.execute("DROP TABLE sitzung")
    con.execute("DROP TABLE anmeldung_konto")
    con.execute("UPDATE meta SET wert = '7' WHERE schluessel = 'schema_version'")
    con.commit()
    con.close()
    c = KontorConfig(datenbank=pfad, anmeldung=True)
    anmeldung.passwort_setzen(c, PASSWORT)
    client = TestClient(create_app(c))
    assert client.post("/api/anmeldung", json={"passwort": PASSWORT}).status_code == 200
    assert [k["name"] for k in client.get("/api/konten").json()] == ["Alt"]
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()[0] == "8"
    con.close()


def test_sicherung_ohne_anmeldetabellen(tmp_path):
    c = KontorConfig(datenbank=tmp_path / "k.sqlite3", anmeldung=True)
    anmeldung.passwort_setzen(c, PASSWORT)
    daten = sicherung.erstelle_sicherung(c)
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        roh = z.read("kontor.sqlite")
    ziel = tmp_path / "s.sqlite"
    ziel.write_bytes(roh)
    con = sqlite3.connect(ziel)
    tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    con.close()
    assert not tabellen & {"sitzung", "anmeldung_konto"}
    assert b"scrypt$" not in daten


def test_csrf_aus_token_abgeleitet():
    a, b = anmeldung.csrf_token("a" * 43), anmeldung.csrf_token("b" * 43)
    assert a != b and len(a) == 43 and a == anmeldung.csrf_token("a" * 43)
    assert "Anmeldedienst()" == repr(anmeldung.Anmeldedienst(KontorConfig(datenbank="/tmp/x.sqlite3")))
