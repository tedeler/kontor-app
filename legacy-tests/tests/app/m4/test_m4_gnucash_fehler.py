"""M4: Fehlerfälle beim GnuCash-Import – verständliche Meldung, kein Teilimport (gnucash.md 2, 4.1, 5; T 5)."""

from __future__ import annotations

import gzip
import os
import sqlite3

import pytest
from hypothesis import given, strategies as st

from generator.gnucash import als_gnc_sqlite, als_gnc_xml, guid
from generator.kmy import packe_gzip
from tests.app.test_import_fehler import pruefe_fehlschlag
from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode, neue_config
from tests.hilfen.m3 import alle_aenderungen
from tests.hilfen.m4 import GNC, gnc_erwartung, import_gnc
from tests.hilfen.pfade import KMY

DEFEKT = ["leer", "leer_gzip", "abgeschnitten", "kaputtes_xml", "kein_xml", "kmy_datei", "zwei_buecher", "entitaeten",
          "inhalt_ungueltig", "betrag_ungueltig", "datum_ungueltig", "pflichtfeld_fehlt", "split_auf_wurzel",
          "eltern_unbekannt", "sqlite_kaputt", "sqlite_fremd", "sqlite_zwei_buecher", "sqlite_inhalt_ungueltig"]


def gnc_fehlerhaft(api, inhalt: bytes, code: str, format_: str | None) -> dict:
    """Import über REST, der fehlschlagen muss; am Buch, an den Importvorgängen und am Protokoll ändert sich nichts."""
    vorher = api.zustand()
    importe = api.get("/api/importe", erwartet=200).daten
    n = len(alle_aenderungen(api))
    r = import_gnc(api, inhalt, erwartet=422)
    f = r.json()["fehler"]
    assert f["code"] == code, f
    assert f["meldung"].strip()
    pruefe_fehlschlag(f["details"], code, format_)
    assert api.zustand() == vorher, "fehlgeschlagener Import hat das Buch verändert (Teilimport)"
    assert api.get("/api/importe", erwartet=200).daten == importe
    assert len(alle_aenderungen(api)) == n, "fehlgeschlagener Import erzeugt eine Änderung im Protokoll"
    return f["details"]


@pytest.mark.kern
@pytest.mark.parametrize("name", DEFEKT)
def test_defekte_fixtures(api, name):
    erw = gnc_erwartung(name)
    # Vorbestand, damit „nichts geändert“ etwas bedeutet
    import_gnc(api, GNC / "sonderfaelle.gnucash")
    d = gnc_fehlerhaft(api, (GNC / f"{name}.gnucash").read_bytes(), erw["fehler_code"], erw["format"])
    if erw["fehler_code"] == "import_inhalt_ungueltig":
        refs = {f["referenz"] for f in d["fehler"]}
        assert set(erw["referenzen"]) <= refs, f"Referenzen {refs} statt mindestens {erw['referenzen']}"


@pytest.mark.parametrize("name", ["leer", "kein_xml", "sqlite_fremd", "inhalt_ungueltig", "sqlite_inhalt_ungueltig"])
def test_defekte_python_api(tmp_path, name):
    erw = gnc_erwartung(name)
    config = neue_config(tmp_path)
    e = kontor.modul("kontor.importer.gnucash").importiere_gnucash(config, GNC / f"{name}.gnucash")
    assert e.erfolgreich is False and e.import_id is None and e.format == erw["format"]
    assert e.fehler and e.fehler[0].code == erw["fehler_code"]
    api = Api(config)
    assert api.get("/api/importe", erwartet=200).daten == [] and api.konten() == []


def test_ohne_datei_feld(api):
    assert fehlercode(api.post("/api/import/gnucash", files={"anders": ("x", b"<a/>", "text/xml")},
                               erwartet=422)) == "validierung"


def test_gnucash_datei_am_kmymoney_endpunkt(api):
    """M1 unverändert: eine GnuCash-Datei ist für den KMyMoney-Import kein gültiges Format."""
    for name in ("minimal", "minimal.sqlite"):
        r = api.post("/api/import/kmymoney",
                     files={"datei": ("x.gnucash", (GNC / f"{name}.gnucash").read_bytes(), "application/octet-stream")},
                     erwartet=422)
        assert fehlercode(r) == "import_format_ungueltig"


@pytest.mark.kern
def test_kmymoney_datei_am_gnucash_endpunkt(api):
    gnc_fehlerhaft(api, (KMY / "minimal.kmy").read_bytes(), "import_format_ungueltig", "gnc-xml-gzip")
    gnc_fehlerhaft(api, (KMY / "minimal_unkomprimiert.kmy").read_bytes(), "import_format_ungueltig", "gnc-xml")


def test_sqlite_in_gzip_ist_kein_format(api):
    """gnucash.md 2 Schritt 2: SQLite wird nie entpackt; entpackte Bytes ohne '<' → Formatfehler."""
    gnc_fehlerhaft(api, packe_gzip((GNC / "minimal.sqlite.gnucash").read_bytes()), "import_format_ungueltig", None)


def test_xml_mit_bom_und_leerraum(api):
    erw = gnc_erwartung("minimal_unkomprimiert")
    roh = (GNC / "minimal_unkomprimiert.gnucash").read_bytes()
    r = import_gnc(api, b"\xef\xbb\xbf" + roh).daten  # BOM vor der XML-Deklaration ist wohlgeformt
    assert r["format"] == "gnc-xml" and r["buchungen_neu"] == erw["ergebnis"]["buchungen_neu"]


def test_sqlite_datei_bleibt_unveraendert(tmp_path):
    """gnucash.md 4.1: nur lesend geöffnet, keine Nebendateien."""
    quelle = tmp_path / "quelle"
    quelle.mkdir()
    pfad = quelle / "buch.gnucash"
    inhalt = (GNC / "minimal.sqlite.gnucash").read_bytes()
    pfad.write_bytes(inhalt)
    os.utime(pfad, (1_000_000_000, 1_000_000_000))
    (tmp_path / "db").mkdir()
    config = neue_config(tmp_path / "db")
    assert kontor.modul("kontor.importer.gnucash").importiere_gnucash(config, pfad).erfolgreich
    assert pfad.read_bytes() == inhalt
    assert os.stat(pfad).st_mtime == 1_000_000_000
    assert sorted(p.name for p in quelle.iterdir()) == ["buch.gnucash"]


def _sql_minimal() -> bytes:
    from generator.gnucash import aus_kbuch
    from generator.szenarien import minimal_buch
    gb, _ = aus_kbuch(minimal_buch(), "minimal")
    return als_gnc_sqlite(gb)


def _sql_aendern(sql: str) -> bytes:
    con = sqlite3.connect(":memory:")
    con.deserialize(_sql_minimal())
    con.executescript(sql)
    con.commit()
    return con.serialize()


@pytest.mark.kern
@pytest.mark.parametrize("sql,code", [
    ("DROP TABLE splits;", "import_format_ungueltig"),
    ("DROP TABLE books;", "import_format_ungueltig"),
    ("ALTER TABLE transactions DROP COLUMN post_date;", "import_format_ungueltig"),
    ("DELETE FROM books;", "import_format_ungueltig"),
    ("UPDATE accounts SET name = '' WHERE account_type = 'BANK';", "import_inhalt_ungueltig"),
    ("UPDATE transactions SET post_date = '2024-13-01 10:59:00' WHERE description LIKE 'Super%';",
     "import_inhalt_ungueltig"),
    ("UPDATE splits SET value_num = 1, value_denom = 3 WHERE rowid = 1;", "import_inhalt_ungueltig"),
    ("UPDATE splits SET value_num = 1000000000000000, value_denom = 1 WHERE rowid = 1;", "import_inhalt_ungueltig"),
    ("DELETE FROM splits WHERE tx_guid = (SELECT guid FROM transactions LIMIT 1);", "import_inhalt_ungueltig"),
], ids=["ohne_splits", "ohne_books", "ohne_spalte", "kein_buch", "name_leer", "datum", "drittel", "zu_gross",
        "ohne_split"])
def test_sqlite_stoerungen(api, sql, code):
    gnc_fehlerhaft(api, _sql_aendern(sql), code, "gnc-sqlite")


def test_sqlite_ohne_optionale_tabellen(api):
    """commodities und slots sind optional: Währung dann EUR, Verwendungszweck leer."""
    r = import_gnc(api, _sql_aendern("DROP TABLE commodities; DROP TABLE slots;")).daten
    assert r["erfolgreich"] and r["buchungen_neu"] == 2
    assert {b["verwendungszweck"] for b in api.alle_buchungen()} == {""}


def test_sqlite_altes_datumsformat(api):
    r = import_gnc(api, _sql_aendern("UPDATE transactions SET post_date = '20240131105900' "
                                     "WHERE description LIKE 'Arbeit%';")).daten
    assert r["erfolgreich"]
    assert sorted(b["datum"] for b in api.alle_buchungen()) == ["2024-01-31", "2024-02-02"]


def test_sqlite_vorlagenbaum_wird_ignoriert(api):
    """Konten und Transaktionen außerhalb des Hauptbaums gehören nicht zum Buch (gnucash.md 4.2)."""
    erw = gnc_erwartung("sonderfaelle.sqlite")
    r = import_gnc(api, GNC / "sonderfaelle.sqlite.gnucash").daten
    assert r["buchungen_neu"] + r["buchungen_uebersprungen"] == erw["summen"]["anzahl_transaktionen_in_datei"]
    assert not any("Template" in k["name"] for k in api.konten())


@given(st.binary(min_size=1, max_size=300))
def test_zufaellige_bytes_nie_serverfehler(api_fabrik, daten):
    """Beliebige Bytes führen zu 200 oder 422, nie zu 5xx; bei 422 bleibt das Buch leer."""
    api = api_fabrik()
    r = import_gnc(api, daten, erwartet=(200, 422))
    if r.status_code == 422:
        assert api.konten() == [] and api.alle_buchungen() == []


@pytest.mark.parametrize("schaden", ["value", "account", "datum"])
def test_inhaltsfehler_listen_alle_transaktionen(api, schaden):
    """gnucash.md 5: alle gefundenen Fehler mit Referenz, kein Teilimport."""
    from generator.gnucash import aus_kbuch
    from generator.szenarien import standard_buch
    gb, _ = aus_kbuch(standard_buch(4711, bis=__import__("datetime").date(2022, 3, 31)), "fehlerliste")
    kaputt = gb.buchungen[3], gb.buchungen[7]
    for t in kaputt:
        if schaden == "value":
            t.splits[0].wert_text = "12,5"
        elif schaden == "account":
            t.splits[1].konto = guid("weg")
        else:
            t.datum = "kein Datum"
    d = gnc_fehlerhaft(api, gzip.compress(als_gnc_xml(gb), mtime=0), "import_inhalt_ungueltig", "gnc-xml-gzip")
    assert {kaputt[0].guid, kaputt[1].guid} <= {f["referenz"] for f in d["fehler"]}
