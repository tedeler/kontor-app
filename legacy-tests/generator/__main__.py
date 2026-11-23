"""Erzeugt alle Fixtures: ``python -m generator [--ziel fixtures] [--startwert 4711]``."""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sqlite3
import zlib
from pathlib import Path

from . import GENERATOR_VERSION, STARTWERT
from .gnucash import sqlite_fingerabdruck
from .kmy import als_xml, erwartung, fehler_erwartung, packe_gzip
from .m3_daten import m3_daten
from .m4_daten import erzeuge_m4
from .m5_daten import erzeuge_m5
from .m6_daten import erzeuge_m6
from .m7_gross import erzeuge_gross
from .m8_daten import erzeuge_m8
from .mock_daten import mock_daten
from .sync_daten import sync_daten
from .szenarien import (
    DUBLETTEN_ERWARTUNG,
    DUBLETTEN_VORBESTAND,
    betrag_ungueltig_buch,
    datum_ungueltig_buch,
    dubletten_buch,
    fremdwaehrung_buch,
    inhalt_ungueltig_buch,
    minimal_buch,
    pflichtfeld_fehlt_buch,
    sonderfaelle_buch,
    standard_buch,
)


def _json(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def erzeuge(startwert: int = STARTWERT) -> dict[str, bytes]:
    """Liefert {relativer Pfad: Bytes} für alle Fixtures (ohne MANIFEST)."""
    dateien: dict[str, bytes] = {}
    beschreibung: dict[str, str] = {}

    def gueltig(name: str, buch, *, gz: bool = True, text: str) -> None:
        xml = als_xml(buch)
        dateien[name] = packe_gzip(xml) if gz else xml
        erw = erwartung(buch, fixture=name, format_="kmy-gzip" if gz else "kmy-xml")
        erw["startwert"] = startwert
        dateien[name.replace(".kmy", ".erwartung.json")] = _json(erw)
        beschreibung[name] = text

    def defekt(name: str, daten: bytes, code: str, fmt: str | None, text: str) -> None:
        dateien[name] = daten
        dateien[name.replace(".kmy", ".erwartung.json")] = _json(fehler_erwartung(name, code, fmt, text))
        beschreibung[name] = text

    gueltig("kmy/standard.kmy", standard_buch(startwert),
            text="Drei Jahre Haushaltsbuch 2022–2024 mit Girokonto, Tagesgeld, Kreditkarte, zwei Darlehen")
    gueltig("kmy/standard_bis_2023.kmy", standard_buch(startwert, bis=dt.date(2023, 12, 31)),
            text="Dasselbe Buch, nur Transaktionen bis 31.12.2023 (gleiche IDs) – für inkrementellen Import")
    gueltig("kmy/minimal.kmy", minimal_buch(), text="Kleinstes Buch: ein Konto, zwei Kategorien, zwei Buchungen")
    gueltig("kmy/minimal_unkomprimiert.kmy", minimal_buch(), gz=False,
            text="Wie minimal.kmy, aber unkomprimiertes XML")
    gueltig("kmy/sonderfaelle.kmy", sonderfaelle_buch(),
            text="Umlaute/Sonderzeichen, langer Verwendungszweck, ohne Empfänger, tiefe Kategorien, 13 Splits, "
                 "geschlossenes Konto, Brüche, Ausgleich, Nullsplit, Warnfälle")
    gueltig("kmy/fremdwaehrung.kmy", fremdwaehrung_buch(),
            text="Fremdwährungskonto, Depot und Aktie (übersprungen) samt betroffener Buchungen")

    # Dubletten: Erwartung um Vorbestand und Dublettenergebnis ergänzen
    buch = dubletten_buch()
    xml = als_xml(buch)
    dateien["kmy/dubletten.kmy"] = packe_gzip(xml)
    erw = erwartung(buch, fixture="kmy/dubletten.kmy", format_="kmy-gzip")
    erw["startwert"] = startwert
    erw["vorbestand"] = DUBLETTEN_VORBESTAND
    erw["dubletten"] = DUBLETTEN_ERWARTUNG
    dateien["kmy/dubletten.erwartung.json"] = _json(erw)
    beschreibung["kmy/dubletten.kmy"] = "Import gegen manuellen Vorbestand: eindeutige, mehrdeutige, ähnliche Dubletten"

    minimal_xml = als_xml(minimal_buch())
    defekt("kmy/leer.kmy", b"", "import_datei_leer", None, "0 Bytes")
    defekt("kmy/leer_gzip.kmy", packe_gzip(b""), "import_datei_leer", "kmy-gzip", "gzip mit leerem Inhalt")
    voll = packe_gzip(minimal_xml)
    defekt("kmy/abgeschnitten.kmy", voll[: len(voll) // 2], "import_datei_beschaedigt", "kmy-gzip",
           "gzip nach der Hälfte abgeschnitten")
    kaputt = minimal_xml.replace(b"</TRANSACTIONS>", b"</TRANSAKTIONEN>")
    defekt("kmy/kaputtes_xml.kmy", packe_gzip(kaputt), "import_datei_beschaedigt", "kmy-gzip",
           "gzip ok, XML nicht wohlgeformt")
    gnc = ('<?xml version="1.0" encoding="utf-8" ?>\n<gnc-v2 xmlns:gnc="http://www.gnucash.org/XML/gnc">\n'
           ' <gnc:count-data cd:type="book" xmlns:cd="http://www.gnucash.org/XML/cd">1</gnc:count-data>\n'
           '</gnc-v2>\n').encode()
    defekt("kmy/falsches_format.kmy", packe_gzip(gnc), "import_format_ungueltig", None,
           "gzip mit wohlgeformtem XML, aber Wurzel gnc-v2 (GnuCash)")
    defekt("kmy/kein_xml.kmy", "Dies ist keine KMyMoney-Datei.\nÄÖÜ\n".encode("utf-8"),
           "import_format_ungueltig", None, "Klartext ohne gzip und ohne XML")
    entit = minimal_xml.replace(
        b"<!DOCTYPE KMYMONEY-FILE>",
        b'<!DOCTYPE KMYMONEY-FILE [\n <!ENTITY a "aaaaaaaaaa">\n <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
        b' <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">\n <!ENTITY datei SYSTEM "file:///etc/hostname">\n]>')
    # Die externe Entität wird nur deklariert, nicht verwendet: so ist die Datei
    # für jeden Parser wohlgeformt, und nur die DTD-Regel (10.1 Schritt 5) greift.
    entit = entit.replace(b'memo="Wocheneinkauf"', b'memo="&c;"', 1)
    defekt("kmy/entitaeten.kmy", packe_gzip(entit), "import_format_ungueltig", None,
           "DTD mit Entitätsdeklarationen (Expansion, externe Entität)")
    defekt("kmy/inhalt_ungueltig.kmy", packe_gzip(als_xml(inhalt_ungueltig_buch())),
           "import_inhalt_ungueltig", "kmy-gzip", "Letzte Transaktion verweist auf unbekanntes Konto A999999")
    defekt("kmy/betrag_ungueltig.kmy", packe_gzip(als_xml(betrag_ungueltig_buch())),
           "import_inhalt_ungueltig", "kmy-gzip", "Betrag 1/3 nicht in Cent darstellbar")
    defekt("kmy/datum_ungueltig.kmy", packe_gzip(als_xml(datum_ungueltig_buch())),
           "import_inhalt_ungueltig", "kmy-gzip", "postdate 2023-02-30")
    pf = als_xml(pflichtfeld_fehlt_buch()).replace(
        b' value="__ENTFERNEN__" shares="__ENTFERNEN__"', b' shares="100/100"')
    assert b"__ENTFERNEN__" not in pf
    defekt("kmy/pflichtfeld_fehlt.kmy", packe_gzip(pf), "import_inhalt_ungueltig", "kmy-gzip",
           "SPLIT ohne value-Attribut")

    daten, erw_mock = mock_daten(startwert)
    erw_mock["startwert"] = startwert
    dateien["mock/mock_daten.json"] = _json(daten)
    dateien["mock/mock_daten.erwartung.json"] = _json(erw_mock)
    beschreibung["mock/mock_daten.json"] = "Mock-Datendatei für Bank- und Mail-Mock (Jahr 2024)"

    # Meilenstein 2: Synchronisation und Regeln
    s = sync_daten(startwert)
    dateien["mock/sync_daten.json"] = _json(s["daten"])
    dateien["mock/sync_daten_pin.json"] = _json(s["daten_pin"])
    s["erwartung"]["startwert"] = startwert
    dateien["mock/sync_daten.erwartung.json"] = _json(s["erwartung"])
    beschreibung["mock/sync_daten.json"] = ("M2: Bankumsätze Jan.–Juni 2024 für Giro, Tagesgeld, Kreditkarte mit "
                                            "Störfällen; bank.tan für das TAN-Szenario")
    beschreibung["mock/sync_daten_pin.json"] = "M2: wie sync_daten.json, zusätzlich bank.pin (synthetische Mock-PIN)"
    beschreibung["mock/sync_daten.erwartung.json"] = ("M2: bekannte Wahrheit je Umsatz (Kategorie, Regelergebnis, "
                                                      "Abgleich mit Altbestand), Stichtage")
    gueltig("kmy/sync_altbestand.kmy", s["kbuch"],
            text="M2: KMyMoney-Altbestand bis 15.02.2024 mit denselben IBANs für den Abgleich beim Abruf")
    dateien["sync/regeln.json"] = _json(s["regeln"])
    beschreibung["sync/regeln.json"] = "M2: Kategorien, Konten und Regelsatz (Priorität, Gleichstand, inaktiv)"

    # Meilenstein 3: Umbuchungen, Abstimmung, Empfänger-Aliase, Volltextsuche
    m3 = m3_daten(startwert)
    dateien["mock/m3_daten.json"] = _json(m3["daten"])
    m3["erwartung"]["startwert"] = startwert
    dateien["mock/m3_daten.erwartung.json"] = _json(m3["erwartung"])
    beschreibung["mock/m3_daten.json"] = ("M3: Bankumsätze Jan.–Juni 2024 mit Umbuchungen (gleicher Tag, 2/3/4 Tage, "
                                          "Stufengrenze, fremde/fehlende/widersprechende IBAN, mehrdeutig), "
                                          "Namensvarianten, NFD, ß, Ligatur")
    beschreibung["mock/m3_daten.erwartung.json"] = ("M3: Umbuchungspaare je Stufe, Gründe, Empfänger/Kategorie mit "
                                                    "Stammdaten, Kontoauszüge für die Abstimmung")
    dateien["m3/stammdaten.json"] = _json(m3["stammdaten"])
    beschreibung["m3/stammdaten.json"] = "M3: Kategorien, Empfänger mit Aliasen und Standardkategorie, Regeln"
    dateien["m3/suche.json"] = _json(m3["suche"])
    beschreibung["m3/suche.json"] = "M3: Suchanfragen mit erwarteten Treffern (Umlaute, ß, Akzente, NFD, Ligatur)"
    kb = m3["kbuch"]
    dateien["kmy/m3_aliase.kmy"] = packe_gzip(als_xml(kb))
    erw_kb = erwartung(kb, fixture="kmy/m3_aliase.kmy", format_="kmy-gzip")
    erw_kb["startwert"] = startwert
    erw_kb["alias_zuordnung"] = m3["kbuch_erwartung"]
    dateien["kmy/m3_aliase.erwartung.json"] = _json(erw_kb)
    beschreibung["kmy/m3_aliase.kmy"] = "M3: kleines Buch, dessen Empfänger über Aliase der Stammdaten zugeordnet werden"

    # Meilenstein 4: GnuCash, Lerndaten, Split-Vorlagen
    erw_bis = erwartung(standard_buch(startwert, bis=dt.date(2023, 12, 31)), fixture="kmy/standard_bis_2023.kmy",
                        format_="kmy-gzip")
    m4, m4_text = erzeuge_m4(startwert, erw_bis)
    for name, inhalt in m4.items():
        dateien[name] = inhalt if isinstance(inhalt, bytes) else _json(inhalt)
    beschreibung.update(m4_text)

    # Meilenstein 5: Kredite, wiederkehrende Buchungen, Berichte, Export
    std_erw = erwartung(standard_buch(startwert), fixture="kmy/standard.kmy", format_="kmy-gzip")
    m5, m5_text = erzeuge_m5(startwert, std_erw)
    for name, inhalt in m5.items():
        dateien[name] = _json(inhalt)
    beschreibung.update(m5_text)

    # Meilenstein 6: FinTS-Attrappe, Postfächer, Benachrichtigungen
    m6, m6_text = erzeuge_m6(startwert)
    for name, inhalt in m6.items():
        dateien[name] = inhalt if isinstance(inhalt, bytes) else _json(inhalt)
    beschreibung.update(m6_text)

    # Meilenstein 8: Oberfläche
    m8, m8_text = erzeuge_m8(startwert)
    for name, inhalt in m8.items():
        dateien[name] = inhalt if isinstance(inhalt, bytes) else _json(inhalt)
    beschreibung.update(m8_text)

    dateien["_beschreibung"] = _json(beschreibung)
    return dateien


def manifest(dateien: dict[str, bytes], startwert: int) -> bytes:
    beschreibung = json.loads(dateien["_beschreibung"])
    eintraege = {}
    for name, inhalt in sorted(dateien.items()):
        if name == "_beschreibung":
            continue
        e = {"sha256": hashlib.sha256(inhalt).hexdigest(), "groesse": len(inhalt)}
        if inhalt[:16] == b"SQLite format 3\x00":
            e["sqlite_inhalt"] = sqlite_fingerabdruck(inhalt)
        if inhalt[:2] == b"\x1f\x8b":
            try:
                e["sha256_entpackt"] = hashlib.sha256(gzip.decompress(inhalt)).hexdigest()
            except (EOFError, OSError, zlib.error):
                e["sha256_entpackt"] = None
        if name in beschreibung:
            e["beschreibung"] = beschreibung[name]
        eintraege[name] = e
    return _json({
        "generator_version": GENERATOR_VERSION,
        "startwert": startwert,
        "zlib_version": zlib.ZLIB_RUNTIME_VERSION,
        "sqlite_version": sqlite3.sqlite_version,
        "dateien": eintraege,
        "auf_abruf": auf_abruf(startwert),
    })


def gross_dateien(startwert: int = STARTWERT) -> dict[str, bytes]:
    """M7: großer Datensatz für Leistungstests (nur auf Abruf, nicht eingecheckt, E-134)."""
    datei, erw = erzeuge_gross(startwert)
    return {"gross/gross.kmy": datei, "gross/gross.erwartung.json": _json(erw)}


def auf_abruf(startwert: int) -> dict:
    """Prüfsummen der auf Abruf erzeugten Dateien (``python -m generator --gross``)."""
    aus = {}
    for name, inhalt in sorted(gross_dateien(startwert).items()):
        e = {"sha256": hashlib.sha256(inhalt).hexdigest(), "groesse": len(inhalt)}
        if inhalt[:2] == b"\x1f\x8b":
            e["sha256_entpackt"] = hashlib.sha256(gzip.decompress(inhalt)).hexdigest()
        aus[name] = e
    return aus


def schreibe_gross(ziel: Path, startwert: int = STARTWERT) -> list[Path]:
    geschrieben = []
    for name, inhalt in gross_dateien(startwert).items():
        pfad = ziel / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(inhalt)
        geschrieben.append(pfad)
    return geschrieben


def schreibe(ziel: Path, startwert: int = STARTWERT) -> list[Path]:
    dateien = erzeuge(startwert)
    geschrieben = []
    for name, inhalt in dateien.items():
        if name == "_beschreibung":
            continue
        pfad = ziel / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(inhalt)
        geschrieben.append(pfad)
    m = ziel / "MANIFEST.json"
    m.write_bytes(manifest(dateien, startwert))
    geschrieben.append(m)
    return geschrieben


def main() -> None:
    p = argparse.ArgumentParser(description="Kontor-Testdatengenerator")
    p.add_argument("--ziel", type=Path, default=Path(__file__).resolve().parent.parent / "fixtures")
    p.add_argument("--startwert", type=int, default=STARTWERT)
    p.add_argument("--gross", action="store_true",
                   help="nur den großen Datensatz für Leistungstests nach <ziel>/gross/ schreiben (M7, nicht eingecheckt)")
    a = p.parse_args()
    for pfad in (schreibe_gross if a.gross else schreibe)(a.ziel, a.startwert):
        print(pfad)


if __name__ == "__main__":
    main()
