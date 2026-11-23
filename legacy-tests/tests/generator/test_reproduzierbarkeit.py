"""Der Generator erzeugt reproduzierbar dieselben Bytes wie die eingecheckten Fixtures."""

import gzip
import hashlib
import json
import sqlite3
import zlib

import pytest

from generator.__main__ import erzeuge, manifest
from generator.gnucash import sqlite_fingerabdruck
from generator import STARTWERT
from tests.hilfen.pfade import FIXTURES


@pytest.fixture(scope="module")
def erzeugt():
    return {k: v for k, v in erzeuge(STARTWERT).items()}


def test_zwei_laeufe_byte_gleich(erzeugt):
    zweiter = erzeuge(STARTWERT)
    assert erzeugt.keys() == zweiter.keys()
    for name in erzeugt:
        assert erzeugt[name] == zweiter[name], f"{name} unterscheidet sich zwischen zwei Läufen"


def test_anderer_startwert_andere_daten():
    a = erzeuge(STARTWERT)["kmy/standard.kmy"]
    b = erzeuge(STARTWERT + 1)["kmy/standard.kmy"]
    assert gzip.decompress(a) != gzip.decompress(b)


def test_eingecheckte_fixtures_vollstaendig(erzeugt):
    vorhanden = {str(p.relative_to(FIXTURES)) for p in FIXTURES.rglob("*") if p.is_file()
                 and p.relative_to(FIXTURES).parts[0] != "gross"}  # auf Abruf erzeugt (E-134)
    soll = {k for k in erzeugt if k != "_beschreibung"} | {"MANIFEST.json"}
    assert vorhanden == soll, f"fehlen: {soll - vorhanden}, überzählig: {vorhanden - soll}"


def test_eingecheckte_fixtures_gleich(erzeugt):
    """Gleiche Bytes; gzip-Dateien bei anderer zlib-Version nur gleicher Inhalt."""
    m = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    gleiche_zlib = m["zlib_version"] == zlib.ZLIB_RUNTIME_VERSION
    for name, inhalt in erzeugt.items():
        if name == "_beschreibung":
            continue
        datei = (FIXTURES / name).read_bytes()
        if inhalt[:16] == b"SQLite format 3\x00" and m.get("sqlite_version") != sqlite3.sqlite_version:
            # andere SQLite-Version: gleicher logischer Inhalt genügt (Seitenaufteilung darf abweichen)
            assert sqlite_fingerabdruck(datei) == m["dateien"][name]["sqlite_inhalt"] == sqlite_fingerabdruck(inhalt), name
        elif inhalt[:2] == b"\x1f\x8b" and not gleiche_zlib:
            try:
                assert gzip.decompress(datei) == gzip.decompress(inhalt), name
            except (EOFError, OSError, zlib.error):
                assert hashlib.sha256(datei).hexdigest() == m["dateien"][name]["sha256"]
        else:
            assert datei == inhalt, f"{name}: eingecheckte Datei weicht vom Generator ab – neu erzeugen?"


def test_manifest_aktuell(erzeugt):
    m = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    neu = json.loads(manifest(erzeugt, STARTWERT))
    assert m["startwert"] == STARTWERT
    assert m["dateien"].keys() == neu["dateien"].keys()
    for name, e in m["dateien"].items():
        assert e["sha256"] == hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), name


def test_gzip_kopf_ohne_zeitstempel_und_dateiname(erzeugt):
    for name, inhalt in erzeugt.items():
        if inhalt[:2] == b"\x1f\x8b" and len(inhalt) >= 10:
            assert inhalt[4:8] == b"\x00\x00\x00\x00", f"{name}: mtime im gzip-Kopf gesetzt"
            assert inhalt[3] & 0x08 == 0, f"{name}: Dateiname im gzip-Kopf"
