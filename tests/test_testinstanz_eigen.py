"""Eigene Tests zum Feature `testinstanz` (D-205): Datenkopie ohne Geheimnisse, Ablauf des Einrichtens mit
untergeschobenen Befehlen, ausgelieferte Unit und Umgebungsdatei. Ohne Netz, ohne systemd; nur synthetische Daten."""

from __future__ import annotations

import pathlib
import sqlite3
from importlib import resources

import pytest
from fastapi.testclient import TestClient

from kontor import db
from kontor import testinstanz as T
from kontor.app import create_app
from kontor.config import KontorConfig

GEHEIM = b"SYNTHETISCHER-CHIFFRETEXT-0123456789"


def _hauptinstanz(tmp_path: pathlib.Path) -> tuple[T.Orte, pathlib.Path]:
    """Synthetische Hauptinstanz: Datenbank mit Buchbestand, Geheimnis, TAN-Anforderung und Bankzugang."""
    haupt = tmp_path / "haupt" / "kontor.sqlite3"
    haupt.parent.mkdir()
    db.schema_anlegen(haupt)
    con = sqlite3.connect(haupt)
    con.execute("INSERT INTO empfaenger (name) VALUES ('Bäckerei Beispiel')")
    con.execute("INSERT INTO geheimnis (name, nonce, chiffre, gesetzt_am) VALUES ('bank_pin', x'00', ?, '2026-01-01')",
                (GEHEIM,))
    con.executemany("INSERT INTO meta (schluessel, wert) VALUES (?, ?)",
                    [("bank_fints_url", "https://bank.example.invalid/fints"), ("bank_fints_benutzer", "TESTKENNUNG"),
                     ("bank_diagnose", "1"), ("wk_filter_modus", "toleranz")])
    con.commit()
    con.close()
    env = tmp_path / "etc" / "kontor.env"
    env.parent.mkdir()
    env.write_text(f"# Hauptinstanz\nKONTOR_PORT=8000\nKONTOR_DATENBANK={haupt}\n", encoding="utf-8")
    orte = T.Orte(haupt_env=env, programm=tmp_path / "opt", daten=tmp_path / "var",
                  env=tmp_path / "etc" / "kontor-test.env", unit=tmp_path / "systemd" / T.DIENST, benutzer=None)
    return orte, haupt


class _Befehle:
    """Zeichnet Befehle auf; ``git clone`` legt einen Quellbaum mit Marke an."""

    def __init__(self, fehler: str | None = None) -> None:
        self.liste: list[list[str]] = []
        self.fehler = fehler

    def __call__(self, args: list[str]) -> None:
        self.liste.append(args)
        if self.fehler and self.fehler in args:
            raise T.TestinstanzFehler("untergeschobener Fehler")
        if args[:2] == ["git", "clone"]:
            ziel = pathlib.Path(args[-1])
            ziel.mkdir(parents=True)
            (ziel / "MARKE").write_text(args[args.index("--branch") + 1], encoding="utf-8")

    def kurz(self) -> list[str]:
        return [" ".join(pathlib.Path(a[0]).name if i == 0 else a[i] for i in range(min(2, len(a)))) for a in self.liste]


# ------------------------------------------------------------------ Branchname und Umgebungsdatei


@pytest.mark.parametrize("name", ["feature/testinstanz", "main", "feature/UX-Mobile_2", "v1.2"])
def test_branchname_gueltig(name):
    assert T.branch_pruefen(name) == name


@pytest.mark.parametrize("name", ["", "-x", "--upload-pack=x", "a..b", "a b", "a;b", "feature/", "a//b", "x.lock",
                                  "/abs", "a\nb", "$(x)"])
def test_branchname_ungueltig(name):
    with pytest.raises(T.TestinstanzFehler):
        T.branch_pruefen(name)


def test_hauptdatenbank_aus_umgebungsdatei(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    assert T.hauptdatenbank(orte.haupt_env) == haupt
    orte.haupt_env.write_text("KONTOR_PORT=8000\n", encoding="utf-8")
    with pytest.raises(T.TestinstanzFehler):
        T.hauptdatenbank(orte.haupt_env)
    with pytest.raises(T.TestinstanzFehler):
        T.hauptdatenbank(tmp_path / "fehlt.env")


# ------------------------------------------------------------------ Datenkopie


def test_kopie_ohne_geheimnisse_und_bankzugang(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    T.daten_kopieren(haupt, orte.datenbank)
    con = sqlite3.connect(orte.datenbank)
    assert con.execute("SELECT name FROM empfaenger").fetchall() == [("Bäckerei Beispiel",)]
    assert con.execute("SELECT count(*) FROM geheimnis").fetchone() == (0,)
    schluessel = {r[0] for r in con.execute("SELECT schluessel FROM meta")}
    con.close()
    assert not {s for s in schluessel if s.startswith("bank_fints_")} and "bank_diagnose" not in schluessel
    assert {"schema_version", "wk_filter_modus"} <= schluessel
    roh = orte.datenbank.read_bytes()
    assert GEHEIM not in roh and b"TESTKENNUNG" not in roh, "auch nicht in freien Seiten der Kopie"
    assert not list(orte.daten.glob("*.neu")) and not list(orte.daten.glob("*-wal"))


def test_hauptinstanz_bleibt_unveraendert(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    vorher = haupt.read_bytes()
    T.daten_kopieren(haupt, orte.datenbank)
    assert haupt.read_bytes() == vorher
    con = sqlite3.connect(haupt)
    assert con.execute("SELECT chiffre FROM geheimnis").fetchone() == (GEHEIM,)
    con.close()


def test_kopie_einer_laufenden_wal_datenbank(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    offen = sqlite3.connect(haupt)
    offen.execute("PRAGMA journal_mode = WAL")
    offen.execute("INSERT INTO empfaenger (name) VALUES ('Noch im WAL')")
    offen.commit()
    try:
        T.daten_kopieren(haupt, orte.datenbank)
    finally:
        offen.close()
    con = sqlite3.connect(orte.datenbank)
    assert con.execute("SELECT count(*) FROM empfaenger").fetchone() == (2,)
    con.close()


def test_erneute_kopie_ersetzt_die_alte(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    T.daten_kopieren(haupt, orte.datenbank)
    con = sqlite3.connect(orte.datenbank)
    con.execute("INSERT INTO empfaenger (name) VALUES ('Nur in der Testinstanz')")
    con.commit()
    con.close()
    T.daten_kopieren(haupt, orte.datenbank)
    con = sqlite3.connect(orte.datenbank)
    assert con.execute("SELECT name FROM empfaenger").fetchall() == [("Bäckerei Beispiel",)]
    con.close()


def test_kopie_nie_auf_die_hauptdatenbank(tmp_path):
    _, haupt = _hauptinstanz(tmp_path)
    with pytest.raises(T.TestinstanzFehler):
        T.daten_kopieren(haupt, haupt)
    with pytest.raises(T.TestinstanzFehler):
        T.daten_kopieren(tmp_path / "fehlt.sqlite3", tmp_path / "ziel.sqlite3")


# ------------------------------------------------------------------ Einrichten und Stoppen


def test_einrichten_ablauf(tmp_path):
    orte, _ = _hauptinstanz(tmp_path)
    b = _Befehle()
    meldung = T.einrichten("feature/abc", orte, b)
    assert "feature/abc" in meldung
    kurz = b.kurz()
    assert kurz[:3] == ["git clone", "systemctl daemon-reload", "systemctl stop"]
    assert kurz[4:] == ["pip install", "systemctl start"] and len(kurz) == 6
    assert b.liste[3][1:3] == ["-m", "venv"] and b.liste[3][3] == str(orte.venv)
    assert b.liste[0][-2] == "https://github.com/tedeler/kontor-app" and "--branch" in b.liste[0]
    assert b.liste[4][-2:] == ["--editable", str(orte.quelle)]
    assert (orte.quelle / "MARKE").read_text() == "feature/abc" and not (orte.programm / "src.neu").exists()
    assert orte.datenbank.is_file() and orte.unit.is_file() and orte.env.is_file()
    assert orte.daten.stat().st_mode & 0o777 == 0o700 and orte.datenbank.stat().st_mode & 0o777 == 0o600


def test_einrichten_erneut_wechselt_branch_und_behaelt_umgebungsdatei(tmp_path):
    orte, _ = _hauptinstanz(tmp_path)
    T.einrichten("feature/abc", orte, _Befehle())
    orte.env.write_text(orte.env.read_text() + "KONTOR_PORT=8090\n", encoding="utf-8")
    (orte.venv / "bin").mkdir(parents=True)
    (orte.venv / "bin" / "pip").write_text("", encoding="utf-8")
    b = _Befehle()
    T.einrichten("feature/xyz", orte, b)
    assert (orte.quelle / "MARKE").read_text() == "feature/xyz"
    assert orte.env.read_text().endswith("KONTOR_PORT=8090\n")
    assert not any(a[1:3] == ["-m", "venv"] for a in b.liste), "vorhandene Umgebung wird weiterbenutzt"


def test_unbekannter_branch_laesst_alles_stehen(tmp_path):
    orte, _ = _hauptinstanz(tmp_path)
    T.einrichten("feature/abc", orte, _Befehle())
    b = _Befehle(fehler="clone")
    with pytest.raises(T.TestinstanzFehler):
        T.einrichten("feature/gibt-es-nicht", orte, b)
    assert len(b.liste) == 1, "weder gestoppt noch installiert"
    assert (orte.quelle / "MARKE").read_text() == "feature/abc" and orte.datenbank.is_file()


def test_einrichten_ohne_hauptdatenbank(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    haupt.unlink()
    b = _Befehle()
    with pytest.raises(T.TestinstanzFehler):
        T.einrichten("feature/abc", orte, b)
    assert b.liste == []


def test_stoppen(tmp_path):
    orte, _ = _hauptinstanz(tmp_path)
    T.einrichten("feature/abc", orte, _Befehle())
    b = _Befehle()
    T.stoppen(orte, b)
    assert b.liste == [["systemctl", "stop", T.DIENST]] and orte.datenbank.is_file()
    T.stoppen(orte, _Befehle(), loeschen=True)
    assert not orte.datenbank.exists() and orte.quelle.is_dir()


def test_nur_als_root(monkeypatch, capsys):
    monkeypatch.setattr(T.os, "geteuid", lambda: 1000)
    assert T.main(["stoppen"]) == 2
    assert "root" in capsys.readouterr().err


# ------------------------------------------------------------------ ausgelieferte Dateien


def _umgebung(text: str) -> dict[str, str]:
    paare = (z.split("=", 1) for z in text.splitlines() if z.strip() and not z.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in paare}


def test_ausgelieferte_umgebungsdatei():
    b = resources.files("kontor.betrieb")
    test = _umgebung(b.joinpath("kontor-test.env").read_text(encoding="utf-8"))
    haupt = _umgebung(b.joinpath("kontor.env").read_text(encoding="utf-8"))
    c = KontorConfig.from_env(test)
    assert c.mock_modus and c.bank_plugin == "mock" and c.mail_plugin == "mock"
    assert c.aktive_datenbank == T.Orte().datenbank
    assert c.update_pruefen is False and c.update_verzeichnis is None
    assert c.sync_intervall_minuten == 0 and c.mail_intervall_minuten == 0
    assert c.port == 8081 and c.port != int(haupt["KONTOR_PORT"]) and c.anmeldung is True
    assert haupt["KONTOR_DATENBANK"] not in test.values()
    assert not any("/var/lib/kontor/" in w for w in test.values()), "kein Pfad im Datenverzeichnis der Hauptinstanz"
    assert not {k for k in test if "FINTS" in k or "NTFY" in k or "OAUTH" in k or "PIN" in k}


def test_ausgelieferte_unit():
    b = resources.files("kontor.betrieb")
    unit = b.joinpath(T.DIENST).read_text(encoding="utf-8")
    haupt = b.joinpath("kontor.service").read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/kontor/kontor-test.env" in unit
    assert "ExecStart=/opt/kontor-test/venv/bin/python -m kontor\n" in unit
    assert "StateDirectory=kontor-test\n" in unit and "InaccessiblePaths=-/var/lib/kontor\n" in unit
    assert "LoadCredential" not in unit, "die Testinstanz bekommt keine Geheimnisse"
    assert "[Install]" not in unit, "startet nicht von selbst"
    haertung = [z for z in haupt.splitlines() if z.startswith(("Protect", "Restrict", "Private", "NoNew", "System",
                                                              "Capability", "Ambient", "Lock", "LimitCORE", "User="))]
    assert haertung and all(z in unit.splitlines() for z in haertung), "gleiche Härtung wie der Hauptdienst"


def test_testinstanz_startet_im_mock_modus_auf_der_kopie(tmp_path):
    orte, haupt = _hauptinstanz(tmp_path)
    T.daten_kopieren(haupt, orte.datenbank)
    vorher = haupt.read_bytes()
    umgebung = _umgebung(resources.files("kontor.betrieb").joinpath("kontor-test.env").read_text(encoding="utf-8"))
    umgebung |= {"KONTOR_MOCK_DATENBANK": str(orte.datenbank), "KONTOR_DATENBANK": str(orte.daten / "unbenutzt.sqlite3"),
                 "KONTOR_ANMELDUNG": "0"}
    del umgebung["KONTOR_ERLAUBTE_NETZE"]  # der Testclient kommt nicht aus einem privaten Netz
    with TestClient(create_app(KontorConfig.from_env(umgebung))) as c:
        status = c.get("/api/status").json()
        assert status["mock"] is True and status["plugins"]["bank"]["mock"] is True
        assert "Bäckerei Beispiel" in c.get("/api/empfaenger").text
        assert c.get("/api/update").json()["automatisch"] is False
    assert haupt.read_bytes() == vorher and not (orte.daten / "unbenutzt.sqlite3").exists()
