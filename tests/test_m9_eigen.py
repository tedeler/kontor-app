"""Eigene Tests zu Meilenstein 9 (ergänzend zu kontor-tests): Rückgängig-Ketten mit Bankkonto-Zustand,
lesende Python-Sicherung, Schema der Sicherungsdatei, Migration auf Schemaversion 5, Laufsperre."""

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


def _einspielen(c, daten, **params):
    return c.post("/api/sicherung/einspielen", params={"bestaetigt": "true", **params},
                  files={"datei": ("s.zip", daten, "application/zip")})


def test_rueckgaengig_kette_mit_bankkonto_zustand(tmp_path):
    """Einspielen → Rückgängig → Wiederholen → Rückgängig: Bankkonto-Zustand und Kennungen folgen jedes Mal."""
    c = _client(tmp_path)
    assert c.post("/api/sync", json={"von": "2024-01-01"}).status_code == 200
    s0 = c.get("/api/sicherung").content
    z0 = c.get("/api/sync/konten").json()
    giro = sorted(z["iban"] for z in z0)[0]
    kid = next(z["konto_id"] for z in z0 if z["iban"] == giro)
    assert c.post(f"/api/konten/{kid}/loeschen", json={"buchungen": "loeschen", "konflikte": "behalten"}).status_code == 200
    assert c.post(f"/api/sync/konten/{giro}/entscheidung", json={"aktion": "ignorieren", "buchungen": "alle"}).status_code == 200
    z1 = c.get("/api/sync/konten").json()
    assert z1 != z0
    aid = _einspielen(c, s0).json()["aenderung_id"]
    assert c.get("/api/sync/konten").json() == z0
    u = c.post(f"/api/aenderungen/{aid}/rueckgaengig").json()
    assert c.get("/api/sync/konten").json() == z1
    w = c.post(f"/api/aenderungen/{u['id']}/rueckgaengig").json()
    assert c.get("/api/sync/konten").json() == z0
    c.post(f"/api/aenderungen/{w['id']}/rueckgaengig")
    assert c.get("/api/sync/konten").json() == z1
    # Kennungen: im Zustand z1 sind die Umsätze des gelöschten Kontos vergessen worden? Nein – „ignorieren“
    # überspringt das Konto; der nächste Lauf bucht nichts doppelt.
    lauf = c.post("/api/sync", json={}).json()
    assert all(k["buchungen_neu"] == 0 for k in lauf["konten"])


def test_python_sicherung_aendert_die_datei_nicht(tmp_path):
    c = _client(tmp_path)
    c.post("/api/konten", json={"name": "Giro", "art": "girokonto"})
    config = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True)
    pfad = config.aktive_datenbank
    vorher = hashlib.sha256(pfad.read_bytes()).hexdigest()
    roh = sicherung.erstelle_sicherung(config)
    assert hashlib.sha256(pfad.read_bytes()).hexdigest() == vorher
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        m = json.loads(z.read("manifest.json"))
        daten = z.read("kontor.sqlite")
    assert m["schemaversion"] == sicherung.SCHEMAVERSION and m["anzahl"]["konto"] == 1
    con = sqlite3.connect(":memory:")
    con.deserialize(daten)
    tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tabellen == set(sicherung.SPALTEN), "nur die Tabellen der Sicherung, kein Protokoll"
    assert "aenderung" not in tabellen


def test_migration_auf_schemaversion_5(tmp_path):
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    con.execute("DROP TABLE sicherung_zustand")
    con.execute("UPDATE meta SET wert = '4' WHERE schluessel = 'schema_version'")
    con.commit()
    con.close()
    c = TestClient(create_app(KontorConfig(datenbank=pfad)))
    assert c.get("/api/status").status_code == 200
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()[0] == str(db.SCHEMA_VERSION)
    assert con.execute("SELECT 1 FROM sqlite_master WHERE name = 'sicherung_zustand'").fetchone()
    con.close()


def test_laufsperre_waehrend_des_einspielens(tmp_path):
    """sicherung.md 7: hält jemand die Laufsperre, antwortet das Einspielen mit 409 sync_laeuft."""
    app = create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 30)))
    c = TestClient(app)
    daten = c.get("/api/sicherung").content
    c.post("/api/konten", json={"name": "Neu", "art": "aufwand"})
    with app.state.sync.ohne_lauf():
        r = _einspielen(c, daten)
        assert r.status_code == 409 and r.json()["fehler"]["code"] == "sync_laeuft"
        r = c.post("/api/sync", json={"von": "2024-01-01"})
        assert r.status_code == 409 and r.json()["fehler"]["code"] == "sync_laeuft"
    assert _einspielen(c, daten).json()["geaendert"] is True


def test_unbekannte_spalte_im_inhalt_wird_nicht_gelesen(tmp_path):
    """Ein Text mit falschem Typ in einer Zahlenspalte ist inhalt_ungueltig, kein 500."""
    c = _client(tmp_path)
    c.post("/api/konten", json={"name": "Giro", "art": "girokonto"})
    roh = c.get("/api/sicherung").content
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        m = json.loads(z.read("manifest.json"))
        daten = z.read("kontor.sqlite")
    con = sqlite3.connect(":memory:")
    con.deserialize(daten)
    con.execute("UPDATE konto SET geschlossen = 'ja'")
    con.commit()
    neu = con.serialize()
    m["datenbank_sha256"] = hashlib.sha256(neu).hexdigest()
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr("kontor.sqlite", neu)
    r = _einspielen(c, puffer.getvalue(), trocken="true")
    assert r.status_code == 422 and r.json()["fehler"]["details"] == {"grund": "inhalt_ungueltig"}
