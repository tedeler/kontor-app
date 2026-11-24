"""Core-Tests zum Feature „testinstanz-platz“ (D-256): Die Datenkopie der Testinstanz braucht nur noch etwa einmal
die Größe der Datenbank an freiem Platz, prüft ihn vorher und nennt bei SQLite-Fehlern die Ursache."""

from __future__ import annotations

import pathlib
import sqlite3
from collections import namedtuple

import pytest

from kontor import db
from kontor import testinstanz as T

GEHEIM = b"SYNTHETISCHER-CHIFFRETEXT-0123456789"


def _haupt(tmp_path: pathlib.Path, auto_vacuum: bool) -> pathlib.Path:
    haupt = tmp_path / "haupt.sqlite3"
    con = sqlite3.connect(haupt)   # mit auto_vacuum (D-255) oder wie ein Bestand aus der Zeit davor
    con.execute(f"PRAGMA auto_vacuum = {'INCREMENTAL' if auto_vacuum else 'NONE'}")
    con.execute("CREATE TABLE platzhalter (x)")
    con.close()
    db.schema_anlegen(haupt)
    con = sqlite3.connect(haupt)
    con.execute("INSERT INTO geheimnis (name, nonce, chiffre, gesetzt_am) VALUES ('bank_pin', x'00', ?, '2026-01-01')",
                (GEHEIM,))
    # Füllstoff, damit die Kopie nennenswert groß ist und freie Seiten entstehen können
    con.executemany("INSERT INTO empfaenger (name) VALUES (?)", [(f"Empfänger {i} (fiktiv)" + "x" * 200,)
                                                                for i in range(1000)])
    con.commit()
    con.close()
    return haupt


@pytest.mark.parametrize("auto_vacuum", [True, False])
def test_kopie_ohne_geheimnisse_und_ohne_freie_seiten(tmp_path, auto_vacuum):
    haupt = _haupt(tmp_path, auto_vacuum)
    ziel = tmp_path / "test" / "kopie.sqlite3"
    T.daten_kopieren(haupt, ziel)
    assert GEHEIM not in ziel.read_bytes()
    con = sqlite3.connect(ziel)
    assert con.execute("SELECT count(*) FROM empfaenger").fetchone() == (1000,)
    assert con.execute("PRAGMA freelist_count").fetchone() == (0,)
    con.close()
    assert not list(ziel.parent.glob("*.neu")) and not list(ziel.parent.glob("*-journal"))


def test_zu_wenig_platz_wird_vorher_gemeldet(tmp_path, monkeypatch):
    haupt = _haupt(tmp_path, True)
    ziel = tmp_path / "test" / "kopie.sqlite3"
    T.daten_kopieren(haupt, ziel)
    alt = ziel.read_bytes()
    platz = namedtuple("platz", "total used free")
    monkeypatch.setattr(T.shutil, "disk_usage", lambda _p: platz(10 ** 9, 10 ** 9, 1000))
    with pytest.raises(T.TestinstanzFehler, match="Platz"):
        T.daten_kopieren(haupt, ziel)
    assert ziel.read_bytes() == alt, "vor dem Kopieren abgebrochen: die alte Kopie bleibt"


def test_alte_kopie_zaehlt_als_frei(tmp_path, monkeypatch):
    """Die alte Kopie wird vor dem Kopieren entfernt; ihr Platz steht der neuen zur Verfügung."""
    haupt = _haupt(tmp_path, True)
    ziel = tmp_path / "test" / "kopie.sqlite3"
    T.daten_kopieren(haupt, ziel)
    groesse = haupt.stat().st_size
    platz = namedtuple("platz", "total used free")
    # frei ist nur etwas mehr als die halbe Datenbank; zusammen mit der alten Kopie reicht es
    monkeypatch.setattr(T.shutil, "disk_usage", lambda _p: platz(10 ** 9, 10 ** 9, groesse // 2 + 4096))
    T.daten_kopieren(haupt, ziel)
    con = sqlite3.connect(ziel)
    assert con.execute("SELECT count(*) FROM empfaenger").fetchone() == (1000,)
    con.close()


def test_sqlite_fehler_nennt_die_ursache(tmp_path):
    kaputt = tmp_path / "kaputt.sqlite3"
    kaputt.write_bytes(b"keine Datenbank, nur Text " * 400)
    with pytest.raises(T.TestinstanzFehler) as e:
        T.daten_kopieren(kaputt, tmp_path / "test" / "kopie.sqlite3")
    assert "OperationalError" in str(e.value) or "DatabaseError" in str(e.value)
    assert "not a database" in str(e.value), str(e.value)
