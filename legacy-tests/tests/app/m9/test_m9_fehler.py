"""M9: ungültige, fremde und manipulierte Sicherungen (sicherung.md 5.1, E-093).

Die Tests kennen das Schema von kontor.sqlite nicht. Sie verändern Manifest und Datenbank nur
schemaunabhängig (zusätzliche View/Tabelle/Trigger, gelöschte Tabelle, zerstörte Bytes) und rechnen
``datenbank_sha256`` nach, damit genau die gewünschte Prüfstufe greift. In jedem Fall ändert sich nichts.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m9 import (aenderungsanzahl, baue, db_veraendert, einspielen, erste_tabelle, kleiner_bestand,
                             lesezustand, neu_verpackt, oeffne, sicherung, ungueltig)

pytestmark = pytest.mark.kern


@pytest.fixture
def lage(api, tmp_path):
    """Quelle mit kleinem Bestand; Ziel `api` mit anderem Bestand. Liefert (api, manifest, db, prüfen)."""
    from tests.hilfen.api import neue_api

    quelle = neue_api(tmp_path / "quelle")
    kleiner_bestand(quelle, "Q")
    manifest, db = oeffne(sicherung(quelle))
    kleiner_bestand(api, "Z")
    vorher, n = lesezustand(api, vorlagen=False), aenderungsanzahl(api)

    def unveraendert():
        assert lesezustand(api, vorlagen=False) == vorher, "ungültige Sicherung hat den Zustand verändert"
        assert aenderungsanzahl(api) == n, "ungültige Sicherung hat eine Änderung erzeugt"

    yield api, manifest, db, unveraendert
    unveraendert()


def _zip(*paare) -> bytes:
    return baue(list(paare))


def test_kontrolle_gueltig(lage):
    """Gegenprobe: die unveränderte Sicherung wird im Probelauf angenommen."""
    api, m, db, _ = lage
    assert einspielen(api, neu_verpackt(m, db), trocken=True).daten["geaendert"] is True


def test_feld_datei_fehlt(lage):
    api, *_ = lage
    r = api.post("/api/sicherung/einspielen", params={"bestaetigt": "true"}, erwartet=422)
    assert fehlercode(r) == "validierung"


def test_datei_leer(lage):
    ungueltig(lage[0], b"", "datei_leer")


@pytest.mark.parametrize("inhalt", [b"kein zip", b"PK\x03\x04kaputt", json.dumps({"format": "x"}).encode()])
def test_kein_zip(lage, inhalt):
    ungueltig(lage[0], inhalt, "kein_zip")


def test_zip_inhalt(lage):
    api, m, db, _ = lage
    mj = json.dumps(m).encode()
    faelle = {
        "nur manifest": _zip(("manifest.json", mj)),
        "nur datenbank": _zip(("kontor.sqlite", db)),
        "zusätzlicher Eintrag": _zip(("manifest.json", mj), ("kontor.sqlite", db), ("liesmich.txt", b"x")),
        "Pfadangabe": _zip(("../manifest.json", mj), ("kontor.sqlite", db)),
        "Unterverzeichnis": _zip(("manifest.json", mj), ("daten/kontor.sqlite", db)),
        "doppelt": _zip(("manifest.json", mj), ("kontor.sqlite", db), ("kontor.sqlite", db)),
        "leeres ZIP": _zip(),
    }
    # Verzeichniseintrag
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("manifest.json", mj)
        z.writestr("kontor.sqlite", db)
        z.writestr(zipfile.ZipInfo("ordner/"), b"")
    faelle["Verzeichnis"] = puffer.getvalue()
    for name, daten in faelle.items():
        try:
            ungueltig(api, daten, "zip_inhalt")
        except AssertionError as e:
            raise AssertionError(f"Fall {name!r}: {e}") from None


def test_manifest_ungueltig(lage):
    api, m, db, _ = lage
    ohne = {k: v for k, v in m.items() if k != "schemaversion"}
    faelle = {
        "kein JSON": b"{nicht json",
        "kein Objekt": b"[1, 2]",
        "kein UTF-8": json.dumps(m, ensure_ascii=False).encode("utf-16"),
        "Feld fehlt": json.dumps(ohne).encode(),
        "unbekanntes Feld": json.dumps({**m, "extra": 1}).encode(),
        "falscher Typ": json.dumps({**m, "formatversion": "1"}).encode(),
        "anzahl kein Objekt": json.dumps({**m, "anzahl": [1]}).encode(),
        "inhalt_sha256 Form": json.dumps({**m, "inhalt_sha256": "XYZ"}).encode(),
        "modus unbekannt": json.dumps({**m, "modus": "test"}).encode(),
    }
    for name, roh in faelle.items():
        try:
            ungueltig(api, _zip(("manifest.json", roh), ("kontor.sqlite", db)), "manifest_ungueltig")
        except AssertionError as e:
            raise AssertionError(f"Fall {name!r}: {e}") from None


def test_format_unbekannt(lage):
    api, m, db, _ = lage
    ungueltig(api, neu_verpackt({**m, "format": "gnucash"}, db), "format_unbekannt")


@pytest.mark.parametrize("feld", ["formatversion", "schemaversion"])
def test_version_nicht_unterstuetzt(lage, feld):
    api, m, db, _ = lage
    ungueltig(api, neu_verpackt({**m, feld: 10**6}, db), "version_nicht_unterstuetzt")


def test_datenbank_pruefsumme(lage):
    api, m, db, _ = lage
    ungueltig(api, neu_verpackt({**m, "datenbank_sha256": "0" * 64}, db, db_sha_neu=False), "datenbank_pruefsumme")
    # veränderte Datei ohne nachgerechnete Prüfsumme
    anders = db_veraendert(db, "CREATE TABLE fremd_x (a INTEGER)")
    ungueltig(api, neu_verpackt(m, anders, db_sha_neu=False), "datenbank_pruefsumme")


@pytest.mark.parametrize("art", ["zufall", "abgeschnitten", "kopf_zerstoert"])
def test_datenbank_ungueltig(lage, art):
    api, m, db, _ = lage
    kaputt = {"zufall": bytes(range(256)) * 64, "abgeschnitten": db[: len(db) // 2],
              "kopf_zerstoert": b"\x00" * 100 + db[100:]}[art]
    ungueltig(api, neu_verpackt(m, kaputt), "datenbank_ungueltig")


def test_datenbank_fremd(lage):
    """Views, Trigger, zusätzliche und fehlende Tabellen werden abgelehnt (E-093)."""
    api, m, db, _ = lage
    tab = erste_tabelle(db)
    faelle = {
        "View": db_veraendert(db, "CREATE VIEW kontor_fremd_v AS SELECT 1 AS x"),
        "zusätzliche Tabelle": db_veraendert(db, "CREATE TABLE kontor_fremd_t (x INTEGER)"),
        "Trigger": db_veraendert(db, f'CREATE TRIGGER kontor_fremd_tr AFTER INSERT ON "{tab}" BEGIN SELECT 1; END'),
        "fehlende Tabelle": db_veraendert(db, f'DROP TABLE "{tab}"'),
        "zusätzliche Spalte": db_veraendert(db, f'ALTER TABLE "{tab}" ADD COLUMN kontor_fremd_s TEXT'),
    }
    for name, daten in faelle.items():
        try:
            ungueltig(api, neu_verpackt(m, daten), "datenbank_fremd")
        except AssertionError as e:
            raise AssertionError(f"Fall {name!r}: {e}") from None


def test_inhalt_pruefsumme(lage):
    api, m, db, _ = lage
    ungueltig(api, neu_verpackt({**m, "inhalt_sha256": "f" * 64}, db), "inhalt_pruefsumme")
    anzahl = dict(m["anzahl"])
    anzahl["konto"] += 1
    ungueltig(api, neu_verpackt({**m, "anzahl": anzahl}, db), "inhalt_pruefsumme")


def test_reihenfolge_der_pruefungen(lage):
    """5.1: Bei mehreren Mängeln gilt der erste Grund der Tabelle."""
    api, m, db, _ = lage
    fremd = db_veraendert(db, "CREATE VIEW kontor_fremd_v AS SELECT 1 AS x")
    ungueltig(api, neu_verpackt({**m, "format": "x", "datenbank_sha256": "0" * 64}, db, db_sha_neu=False),
              "format_unbekannt")
    ungueltig(api, neu_verpackt({**m, "schemaversion": 10**6}, b"kaputt"), "version_nicht_unterstuetzt")
    ungueltig(api, neu_verpackt({**m, "inhalt_sha256": "f" * 64}, fremd), "datenbank_fremd")
    ungueltig(api, neu_verpackt({**m, "datenbank_sha256": "0" * 64, "inhalt_sha256": "f" * 64}, db,
                                db_sha_neu=False), "datenbank_pruefsumme")


def test_modus_nach_dateipruefung(lage):
    """5.1: Erst die Datei, dann der Modus (eine kaputte Mock-Sicherung meldet sicherung_ungueltig)."""
    api, m, db, _ = lage
    ungueltig(api, neu_verpackt({**m, "modus": "mock"}, b"kaputt"), "datenbank_ungueltig")
    r = einspielen(api, neu_verpackt({**m, "modus": "mock"}, db), erwartet=409)
    assert fehlercode(r) == "sicherung_modus"
