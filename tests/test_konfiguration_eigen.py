"""D-235: Seite und Schnittstelle „Konfiguration“ (gesetzte Umgebungsvariablen und geltende Werte)."""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from kontor import config_anzeige
from kontor.app import create_app
from kontor.config import KontorConfig


def test_anzeige_umgebung_und_wirksame_werte(tmp_path):
    umgebung = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_MAIL_ABGLEICH": "1", "KONTOR_PORT": "8081",
                "KONTOR_TIPPFEHLER": "x", "KONTOR_FINTS_BENUTZER": "erika-geheim", "PATH": "/usr/bin", "HOME": "/root"}
    config = KontorConfig.from_env({k: v for k, v in umgebung.items() if k != "KONTOR_TIPPFEHLER"})
    a = config_anzeige.anzeige(config, umgebung)
    env = {e["variable"]: e for e in a["umgebung"]}
    assert sorted(env) == ["KONTOR_DATENBANK", "KONTOR_FINTS_BENUTZER", "KONTOR_MAIL_ABGLEICH", "KONTOR_PORT",
                           "KONTOR_TIPPFEHLER"]                       # nichts außerhalb von KONTOR_…
    assert env["KONTOR_MAIL_ABGLEICH"] == {"variable": "KONTOR_MAIL_ABGLEICH", "wert": "1", "verborgen": False,
                                           "bekannt": True}
    assert env["KONTOR_TIPPFEHLER"]["bekannt"] is False
    assert env["KONTOR_FINTS_BENUTZER"]["wert"] is None and env["KONTOR_FINTS_BENUTZER"]["verborgen"] is True
    w = {e["name"]: e for e in a["wirksam"]}
    assert set(w) == {f.name for f in dataclasses.fields(KontorConfig)}
    assert w["mail_abgleich"] == {"name": "mail_abgleich", "variable": "KONTOR_MAIL_ABGLEICH", "gesetzt": True,
                                  "wert": True, "vorgabe": False, "geaendert": True, "verborgen": False}
    assert w["port"]["wert"] == 8081 and w["port"]["geaendert"] is True
    assert w["mail_bestellnummer"]["gesetzt"] is False and w["mail_bestellnummer"]["geaendert"] is False
    assert w["fints_benutzer"]["wert"] == "verborgen" and "erika-geheim" not in repr(a)
    assert w["credentials_verzeichnis"]["variable"] == "CREDENTIALS_DIRECTORY"


def test_schnittstelle_und_seite(tmp_path, monkeypatch):
    monkeypatch.setenv("KONTOR_MAIL_BESTELLNUMMER", "1")
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mail_bestellnummer=True)))
    a = c.get("/api/konfiguration").json()
    assert any(e["variable"] == "KONTOR_MAIL_BESTELLNUMMER" and e["wert"] == "1" for e in a["umgebung"])
    assert next(e for e in a["wirksam"] if e["name"] == "mail_bestellnummer")["wert"] is True
    assert c.get("/konfiguration").status_code == 200 and "navlink-konfiguration" in c.get("/").text
