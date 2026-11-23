"""Testdaten für Meilenstein 4: GnuCash-Dateien, Lerndaten, Split-Vorlagen.

Erzeugt (alles synthetisch, fester Startwert, ``erzeuge_m4`` liefert
``{Pfad: Bytes}`` und Beschreibungen):

- ``gnc/*.gnucash``: GnuCash-XML (gzip und unkomprimiert) und GnuCash-SQLite
  mit bekannter Wahrheit (``*.erwartung.json``, berechnet aus dem Modell nach
  ``spec/api/gnucash.md``) sowie Störfälle (leer, beschädigt, falsches
  Format, Inhaltsfehler) für beide Formate.
- ``gnc/ueberlappung.sqlite.gnucash``: das Standardbuch ab März 2023 als
  SQLite; die Erwartung enthält das Ergebnis eines Imports nach
  ``kmy/standard_bis_2023.kmy`` (Zuordnung, Dublettenerkennung) und die
  wahre Herkunft jeder Buchung.
- ``kmy/m4_lernen_training.kmy``,
  ``gnc/m4_lernen_training.gnucash``, ``mock/m4_lernen.json``,
  ``m4/lernen.erwartung.json``: Lerndatensatz mit bekannter Kategorie,
  Trennung 80/20 nach Datum (``spec/api/lernmodell.md`` 6).
- ``mock/m4_vorlagen.json``, ``m4/vorlagen.json``,
  ``mock/m4_vorlagen.erwartung.json``: Sammelabbuchungen für Split-Vorlagen
  mit Beitragsänderung (Szenario ``beitragsaenderung``) und Abweichungen um
  einen Cent (``spec/api/vorlagen.md``).
"""

from __future__ import annotations

import datetime as dt
import random
import re

from .gnucash import (GBuch, GBuchung, GKonto, GSplit, aus_kbuch, als_gnc_sqlite, als_gnc_xml, datum_text,
                      fehler_erwartung, gnc_erwartung, guid, sqlite_aus_sql)
from .iban import fiktive_iban, ungueltige_iban
from .kmy import FEHLT, KBuch, als_xml, erwartung, packe_gzip
from .m4_lernen import EMPFAENGER, GIRO_IBAN, KREDIT_IBAN, TEIL_TRAINING, lern_buch
from .szenarien import LANGER_TEXT, minimal_buch, standard_buch

UEBERLAPPUNG_AB = "2023-03-01"


# ------------------------------------------------------------ Normalisierung (datenmodell.md 1)
def _norm(s: str) -> str:
    return s.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def _ekey(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(s))


def _passend(a: str | None, b: str | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return bool(_ekey(a)) and _ekey(a) == _ekey(b)


# ================================================================ Sonderfälle

def sonderfaelle_gbuch() -> GBuch:
    P = "sonder"
    g = lambda n: guid(f"{P}:{n}")  # noqa: E731
    gb = GBuch(buch_guid=g("buch"), root_guid=g("root"), vorlagen=True)
    R = gb.root_guid
    iban_giro = fiktive_iban(6001)
    giro_eingabe = " ".join(iban_giro[i:i + 4] for i in range(0, len(iban_giro), 4)).lower()
    iban_alt = fiktive_iban(6003)
    K = gb.konten
    K += [
        GKonto(g("giro"), "Girokonto Ünïcödé & <Test> \"Haupt\"", "BANK", R, code=giro_eingabe,
               beschreibung="Hauptkonto – fiktiv"),
        GKonto(g("kasse"), "Bargeld", "CASH", R),
        GKonto(g("anlage"), "Sonstiges Vermögen", "ASSET", R),
        GKonto(g("forderung"), "Forderungen", "RECEIVABLE", R),
        GKonto(g("verbindl"), "Verbindlichkeiten", "PAYABLE", R),
        GKonto(g("karte"), "Kreditkarte", "CREDIT", R, code="1200"),
        GKonto(g("alt"), "Altkonto (versteckt)", "BANK", R, code=iban_alt, versteckt=True),
        GKonto(g("doppelt"), "Zweitkonto gleiche IBAN", "BANK", R, code=iban_alt),
        GKonto(g("falsch"), "Konto mit falscher IBAN", "BANK", R, code=ungueltige_iban(6004)),
        GKonto(g("depot"), "Aktie Fiktiv AG", "STOCK", R),
        GKonto(g("usd"), "Dollarkonto", "BANK", R, waehrung="USD"),
        GKonto(g("ek"), "Anfangsbestand", "EQUITY", R),
        GKonto(g("haushalt"), "Haushalt", "EXPENSE", R),
        GKonto(g("kueche"), "Küche", "EXPENSE", g("haushalt")),
        GKonto(g("geraete"), "Geräte", "EXPENSE", g("kueche")),
        GKonto(g("klein"), "Kleingeräte & Zubehör", "EXPENSE", g("geraete")),
        GKonto(g("geschenke"), "Geschenke", "EXPENSE", R, beschreibung="Präsente – fiktiv"),
        GKonto(g("erstattung"), "Erstattungen", "INCOME", R),
        GKonto(g("falschkat"), "Falsch einsortierte Ausgabe", "EXPENSE", g("erstattung")),
        GKonto(g("unterdepot"), "Unter dem Depot", "EXPENSE", g("depot")),
        GKonto(g("freizeit"), "Platzhalter Freizeit", "EXPENSE", R, platzhalter=True),
        GKonto(g("kino"), "Kino", "EXPENSE", g("freizeit")),
        GKonto(g("sammel"), "Sammelposten", "EXPENSE", R),
    ]
    teile = [g(f"teil{i}") for i in range(12)]
    K += [GKonto(teile[i], f"Teil {i + 1:02d}", "EXPENSE", g("sammel")) for i in range(12)]

    B = gb.buchungen
    n = [0]

    def neu(datum: str, splits: list[GSplit], **kw) -> None:
        n[0] += 1
        for k, s in enumerate(splits):
            s.guid = s.guid or g(f"split:{n[0]}:{k}")
        B.append(GBuchung(g(f"trn:{n[0]}"), datum, splits, **kw))

    d = datum_text
    neu(d("2023-01-01"), [GSplit(g("giro"), 100000, memo="Start"), GSplit(g("ek"), -100000)],
        beschreibung="", notiz="Anfangsbestand")
    neu(d("2023-01-02"), [GSplit(g("alt"), 5000), GSplit(g("ek"), -5000)], notiz="Anfangsbestand Altkonto")
    neu(d("2023-01-05"), [GSplit(g("giro"), -1234), GSplit(g("klein"), 1234)],
        beschreibung="Bäckerei Größenwahn – Inh. Jürgen Weiß", notiz=LANGER_TEXT, wahre_kategorie=g("klein"))
    neu(d("2023-01-06"), [GSplit(g("giro"), -2000, memo=FEHLT), GSplit(g("geschenke"), 2000, memo=FEHLT)],
        beschreibung=FEHLT, notiz=FEHLT, wahre_kategorie=g("geschenke"))
    werte = [101 * (i + 1) for i in range(12)]
    neu(d("2023-02-01"), [GSplit(g("giro"), -sum(werte), memo="Sammelrechnung")]
        + [GSplit(teile[i], w, memo=f"Position {i + 1} – Ä{i}") for i, w in enumerate(werte)],
        beschreibung="Ça va? Café „Zum Ölfass“ <&> 'Zitat' \"doppelt\"", notiz="Sammelrechnung mit zwölf Positionen")
    neu(d("2023-02-02"), [GSplit(g("giro"), -1234, wert_text="-617/50", sql_wert=(-617, 50)),
                          GSplit(g("geschenke"), 1234, wert_text="617/50", sql_wert=(617, 50))],
        beschreibung="Ärger GmbH", notiz="Gekürzter Bruch", wahre_kategorie=g("geschenke"))
    neu(d("2023-02-03"), [GSplit(g("giro"), -1200, wert_text="-12", sql_wert=(-12, 1)),
                          GSplit(g("geschenke"), 1200, wert_text="12", sql_wert=(12, 1))],
        beschreibung="Ärger GmbH", notiz="Ganze Euro ohne Nenner", wahre_kategorie=g("geschenke"))
    neu(d("2023-02-04"), [GSplit(g("giro"), -123, wert_text="-1230/1000", sql_wert=(-1230, 1000)),
                          GSplit(g("erstattung"), 123, wert_text="1230/1000", sql_wert=(1230, 1000))],
        notiz="Nenner 1000")
    neu(d("2023-03-01"), [GSplit(g("giro"), -999, memo="Ohne Kategorie")], beschreibung="  ☕ Emoji-Kiosk 🙂  ",
        notiz="Buchung ohne Gegenbuchung")
    neu(d("2023-03-02"), [GSplit(g("giro"), -1000), GSplit(g("erstattung"), 900)], notiz="Unausgeglichen um 1 Euro")
    neu(d("2023-03-03"), [GSplit(g("geschenke"), 0, memo="Nullsplit")], notiz="Nur ein Nullsplit")
    neu(d("2023-03-04"), [GSplit(g("alt"), -5000), GSplit(g("giro"), 5000)], notiz="Auflösung Altkonto",
        umbuchung=True)
    neu(d("2023-03-05"), [GSplit(g("kasse"), -1500), GSplit(g("geschenke"), 1500)],
        beschreibung="☕ Emoji-Kiosk 🙂", notiz="Barzahlung ☕🙂", sql_datum="20230305105900")
    neu("2023-03-06 23:59:59 -0100", [GSplit(g("giro"), -800), GSplit(g("falschkat"), 800)],
        notiz="Falsch einsortiert", sql_datum="2023-03-06 23:59:59")
    neu(d("2023-03-07"), [GSplit(g("giro"), -3000), GSplit(g("depot"), 3000)], beschreibung="Broker (fiktiv)",
        notiz="Kauf Wertpapier")
    neu(d("2023-03-08"), [GSplit(g("usd"), -1000), GSplit(g("geschenke"), 1000)], notiz="Ausgabe vom Dollarkonto")
    neu(d("2023-03-09"), [GSplit(g("giro"), -2500), GSplit(g("geschenke"), 2500)], beschreibung="Shop in USA",
        notiz="Einkauf in USD", waehrung="USD")
    neu(d("2023-03-10"), [GSplit(g("giro"), -1700), GSplit(g("kino"), 1700)], beschreibung="Kino Lichtspiel",
        notiz="Zwei Karten", wahre_kategorie=g("kino"))
    neu(d("2023-03-11"), [GSplit(g("anlage"), 4000), GSplit(g("forderung"), -1000), GSplit(g("verbindl"), -3000)],
        notiz="Umbuchung zwischen Vermögen und Verbindlichkeiten", umbuchung=True)
    neu(d("2023-03-12"), [GSplit(g("karte"), -2599), GSplit(g("haushalt"), 2599)],
        beschreibung="Ça va? Café „Zum Ölfass“ <&> 'Zitat' \"doppelt\"", notiz="Kartenzahlung\nZeile 2",
        wahre_kategorie=g("haushalt"))
    neu(d("2023-03-13"), [GSplit(g("giro"), -330), GSplit(g("geschenke"), 330)], beschreibung="Ärger GmbH",
        notiz="")
    neu(d("2023-03-14"), [GSplit(g("doppelt"), 700), GSplit(g("ek"), -700)], notiz="Zweitkonto")
    neu(d("2023-03-15"), [GSplit(g("falsch"), 800), GSplit(g("unterdepot"), -800)], notiz="Auf Unterkonto des Depots")
    return gb


# ================================================================ Störfälle

def _xml_text(gb: GBuch) -> str:
    return als_gnc_xml(gb).decode("utf-8")


def stoerfaelle(minimal: GBuch, minimal_kmy_xml: bytes) -> list[tuple[str, bytes, str, str | None, str, list]]:
    """(Pfad, Bytes, Fehlercode, Format, Beschreibung, erwartete Referenzen)."""
    x = _xml_text(minimal)
    t0, t1 = minimal.buchungen[0], minimal.buchungen[1]
    k_giro = minimal.konten[0].guid
    aus = []
    gz = lambda s: packe_gzip(s.encode("utf-8"))  # noqa: E731
    aus.append(("gnc/leer.gnucash", b"", "import_datei_leer", None, "0 Bytes", []))
    aus.append(("gnc/leer_gzip.gnucash", packe_gzip(b""), "import_datei_leer", "gnc-xml-gzip",
                "gzip mit leerem Inhalt", []))
    voll = gz(x)
    aus.append(("gnc/abgeschnitten.gnucash", voll[: len(voll) // 2], "import_datei_beschaedigt", "gnc-xml-gzip",
                "gzip nach der Hälfte abgeschnitten", []))
    aus.append(("gnc/kaputtes_xml.gnucash", gz(x.replace("</gnc:book>", "</gnc:buch>")), "import_datei_beschaedigt",
                "gnc-xml-gzip", "gzip ok, XML nicht wohlgeformt", []))
    aus.append(("gnc/kein_xml.gnucash", "Dies ist keine GnuCash-Datei.\nÄÖÜ\n".encode("utf-8"),
                "import_format_ungueltig", None, "Klartext ohne gzip, SQLite und XML", []))
    aus.append(("gnc/kmy_datei.gnucash", packe_gzip(minimal_kmy_xml), "import_format_ungueltig", "gnc-xml-gzip",
                "KMyMoney-Datei (Wurzel KMYMONEY-FILE)", []))
    zwei = als_gnc_xml(minimal, buecher=2)
    aus.append(("gnc/zwei_buecher.gnucash", packe_gzip(zwei), "import_format_ungueltig", "gnc-xml-gzip",
                "zwei gnc:book in einer Datei", []))
    ent = x.replace('<?xml version="1.0" encoding="utf-8" ?>\n',
                    '<?xml version="1.0" encoding="utf-8" ?>\n<!DOCTYPE gnc-v2 [\n <!ENTITY a "aaaaaaaaaa">\n'
                    ' <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n <!ENTITY datei SYSTEM "file:///etc/hostname">\n]>\n')
    ent = ent.replace("<trn:description>Supermarkt Frischekorb</trn:description>",
                      "<trn:description>&b;</trn:description>", 1)
    assert "&b;" in ent
    aus.append(("gnc/entitaeten.gnucash", ent.encode("utf-8"), "import_format_ungueltig", "gnc-xml",
                "DTD mit Entitätsdeklarationen (unkomprimiert)", []))
    unbekannt = guid("unbekanntes-konto")
    inh = x.replace(f'<split:account type="guid">{k_giro}</split:account>',
                    f'<split:account type="guid">{unbekannt}</split:account>', 1)
    # zweite Transaktion ohne Splits
    anfang = inh.index("<trn:splits>", inh.index(t1.guid))
    ende = inh.index("</trn:splits>", anfang) + len("</trn:splits>")
    inh = inh[:anfang] + "<trn:splits/>" + inh[ende:]
    aus.append(("gnc/inhalt_ungueltig.gnucash", gz(inh), "import_inhalt_ungueltig", "gnc-xml-gzip",
                "Split auf unbekanntes Konto, Transaktion ohne Split", sorted([t0.guid, t1.guid])))
    bet = x.replace("<split:value>-2500/100</split:value>", "<split:value>-1/3</split:value>", 1)
    assert bet != x
    aus.append(("gnc/betrag_ungueltig.gnucash", gz(bet), "import_inhalt_ungueltig", "gnc-xml-gzip",
                "Betrag 1/3 nicht in Cent darstellbar", [t1.guid]))
    dat = x.replace("<ts:date>2024-02-02 10:59:00 +0000</ts:date>", "<ts:date>2024-02-30 10:59:00 +0000</ts:date>", 1)
    assert dat != x
    aus.append(("gnc/datum_ungueltig.gnucash", gz(dat), "import_inhalt_ungueltig", "gnc-xml-gzip",
                "Buchungsdatum 2024-02-30", [t1.guid]))
    pf = re.sub(r"<split:value>-2500/100</split:value>\s*", "", x, count=1)
    assert pf != x
    aus.append(("gnc/pflichtfeld_fehlt.gnucash", gz(pf), "import_inhalt_ungueltig", "gnc-xml-gzip",
                "Split ohne split:value", [t1.guid]))
    root = x.replace(f'<split:account type="guid">{minimal.konten[2].guid}</split:account>',
                     f'<split:account type="guid">{minimal.root_guid}</split:account>', 1)
    assert root != x
    aus.append(("gnc/split_auf_wurzel.gnucash", gz(root), "import_inhalt_ungueltig", "gnc-xml-gzip",
                "Split bucht auf das Wurzelkonto (ROOT)", [t0.guid]))
    eltern = x.replace(f'<act:parent type="guid">{minimal.root_guid}</act:parent>',
                       f'<act:parent type="guid">{unbekannt}</act:parent>', 1)
    aus.append(("gnc/eltern_unbekannt.gnucash", gz(eltern), "import_inhalt_ungueltig", "gnc-xml-gzip",
                "act:parent verweist auf unbekanntes Konto", [k_giro]))
    # SQLite
    s = bytearray(als_gnc_sqlite(minimal))
    kaputt = bytes(s[:100]) + bytes((i * 37 + 11) % 256 for i in range(4096 - 100)) + bytes(s[4096:8192])
    aus.append(("gnc/sqlite_kaputt.gnucash", kaputt, "import_datei_beschaedigt", "gnc-sqlite",
                "SQLite-Kopf mit zerstörter erster Seite", []))
    aus.append(("gnc/sqlite_fremd.gnucash", sqlite_aus_sql(
        "CREATE TABLE notizen(id integer primary key, text text); INSERT INTO notizen VALUES (1, 'fiktiv');"),
        "import_format_ungueltig", "gnc-sqlite", "SQLite-Datei ohne GnuCash-Tabellen", []))
    aus.append(("gnc/sqlite_zwei_buecher.gnucash", als_gnc_sqlite(minimal, buecher=2), "import_format_ungueltig",
                "gnc-sqlite", "zwei Zeilen in books", []))
    kaputt_sql = GBuch(minimal.buch_guid, minimal.root_guid, list(minimal.konten),
                       [GBuchung(t0.guid, t0.datum, [GSplit(unbekannt, t0.splits[0].wert, guid=t0.splits[0].guid),
                                                     t0.splits[1]], beschreibung=t0.beschreibung, notiz=t0.notiz),
                        GBuchung(t1.guid, t1.datum, [GSplit(t1.splits[0].konto, -2500, sql_wert=(-2500, 0),
                                                            guid=t1.splits[0].guid), t1.splits[1]],
                                 beschreibung=t1.beschreibung, notiz=t1.notiz)])
    aus.append(("gnc/sqlite_inhalt_ungueltig.gnucash", als_gnc_sqlite(kaputt_sql), "import_inhalt_ungueltig",
                "gnc-sqlite", "Split auf unbekanntes Konto, value_denom 0", sorted([t0.guid, t1.guid])))
    return aus


# ============================================================ Überlappung

def ueberlappung(startwert: int, kmy_erw: dict) -> tuple[GBuch, dict]:
    """Standardbuch ab UEBERLAPPUNG_AB als GnuCash; Erwartung für den Import nach standard_bis_2023.kmy."""
    kb = standard_buch(startwert)
    teil = [b for b in kb.buchungen if b.datum[:10] >= UEBERLAPPUNG_AB]
    gb, abb = aus_kbuch(kb, "ueberlappung", buchungen=teil)
    erw = gnc_erwartung(gb, fixture="gnc/ueberlappung.sqlite.gnucash", format_="gnc-sqlite")
    zu_kmy = {"gnc:" + g: "kmy:" + k for k, g in abb.items()}
    klasse = {k["extern_id"]: k["art"] for k in kmy_erw["konten"]}
    bestand = {e for e, a in klasse.items() if a in ("girokonto", "sparkonto", "kreditkonto")}
    vorhanden = kmy_erw["buchungen"]

    def bsplits(b: dict, abbild) -> list[tuple[str, int]]:
        return [(abbild(s["konto_extern_id"]), s["betrag"]) for s in b["splits"]
                if abbild(s["konto_extern_id"]) in bestand]

    def tage(a: str, b: str) -> int:
        return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)

    index: dict[tuple[str, int], list[dict]] = {}
    for c in vorhanden:
        for kx in {(s["konto_extern_id"], s["betrag"]) for s in c["splits"]}:
            index.setdefault(kx, []).append(c)
    E: dict[str, set[str]] = {}
    A: dict[str, set[str]] = {}
    for b in erw["buchungen"]:
        e, a = set(), set()
        for k, x in bsplits(b, lambda s: zu_kmy.get(s, s)):
            for c in index.get((k, x), []):
                if c["datum"] == b["datum"] and _passend(b["empfaenger"], c["empfaenger"]):
                    e.add(c["extern_id"])
                elif tage(c["datum"], b["datum"]) <= 3:
                    a.add(c["extern_id"])
        E[b["extern_id"]] = e
        A[b["extern_id"]] = a - e
    ergebnis = {"zusammengefuehrt": {}, "verdacht": [], "neu": []}
    for b in erw["buchungen"]:
        i = b["extern_id"]
        e = E[i]
        if len(e) == 1 and not any(next(iter(e)) in E[j] for j in E if j != i):
            ergebnis["zusammengefuehrt"][i] = next(iter(e))
        elif e | A[i]:
            ergebnis["verdacht"].append({"extern_id": i, "kandidaten": sorted(e | A[i]),
                                         "grund": "mehrdeutig" if e else "aehnlich",
                                         "wahr": ("kmy:" + b["quelle"]) if b["datum"] <= "2023-12-31" else None})
            ergebnis["neu"].append(i)
        else:
            ergebnis["neu"].append(i)
    for i, c in ergebnis["zusammengefuehrt"].items():
        q = next(b["quelle"] for b in erw["buchungen"] if b["extern_id"] == i)
        assert c == "kmy:" + q, (i, c, q)
    namen = {e["name"] for e in erw["empfaenger"]}
    erw["nach_kmy"] = {
        "vorher": "kmy/standard_bis_2023.kmy",
        "ergebnis": {"konten_neu": 0, "konten_vorhanden": erw["ergebnis"]["konten_neu"], "kategorien_neu": 0,
                     "kategorien_vorhanden": erw["ergebnis"]["kategorien_neu"], "empfaenger_neu": 0,
                     "empfaenger_vorhanden": len(namen), "tags_neu": 0, "tags_vorhanden": 0,
                     "buchungen_neu": len(ergebnis["neu"]), "buchungen_vorhanden": 0,
                     "buchungen_zusammengefuehrt": len(ergebnis["zusammengefuehrt"]),
                     "buchungen_zur_pruefung": len(ergebnis["verdacht"]), "buchungen_uebersprungen": 0,
                     "splits_neu": sum(len(b["splits"]) for b in erw["buchungen"] if b["extern_id"] in ergebnis["neu"])},
        "konto_zuordnung": zu_kmy,
        "zusammengefuehrt": ergebnis["zusammengefuehrt"],
        "verdacht": ergebnis["verdacht"],
        "neu": ergebnis["neu"],
        "nach_aufloesen": "kmy/standard.kmy",
    }
    return gb, erw


# ================================================================ Lerndaten

def lerndaten(startwert: int) -> dict:
    kb, wahrheit = lern_buch(startwert)
    letzte = max(w["datum"] for w in wahrheit if w["teil"] == "training")
    trainings_ids = {w["id"] for w in wahrheit if w["teil"] == "training"}
    einfache = {w["id"] for w in wahrheit}
    tb = KBuch(konten=kb.konten, empfaenger=kb.empfaenger, tags=kb.tags,
               buchungen=[b for b in kb.buchungen if b.id in trainings_ids
                          or (b.id not in einfache and b.datum[:10] <= letzte)])
    gb, _ = aus_kbuch(tb, "lernen")
    pruef = [w for w in wahrheit if w["teil"] == "pruefung"]
    iban = {"A000001": GIRO_IBAN, "A000002": KREDIT_IBAN}
    umsaetze = []
    for n, w in enumerate(pruef, start=1):
        w["umsatz_id"] = f"L-{n:05d}"
        umsaetze.append({"umsatz_id": w["umsatz_id"], "iban": iban[w["konto"]], "buchungstag": w["datum"],
                         "valuta": w["datum"], "betrag": w["betrag"], "waehrung": "EUR",
                         "gegenpartei_name": w["empfaenger"], "gegenpartei_iban": None,
                         "verwendungszweck": w["verwendungszweck"], "vormerkung": False, "storno": False})
    mock = {"format": "kontor-mock-daten", "version": 1, "bank": {"konten": [
        {"iban": GIRO_IBAN, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto",
         "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"},
        {"iban": KREDIT_IBAN, "bic": "TESTDEFFXXX", "name": "Kreditkarte", "art": "kreditkonto",
         "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"}], "umsaetze": umsaetze},
        "mail": {"postfaecher": ["haushalt.eins@example.invalid"], "nachrichten": []}}
    erw = {
        "beschreibung": "Lerndatensatz (lernmodell.md 6): je einfacher Buchung Empfänger, Verwendungszweck, "
                        "Regelbetrag, erfasste und richtige Kategorie (Name), Teil training/pruefung; "
                        "Prüfbuchungen mit umsatz_id in mock/m4_lernen.json",
        "teil_training": TEIL_TRAINING, "mindestgenauigkeit": 0.85, "mindestabdeckung": 0.70,
        "letztes_trainingsdatum": letzte, "erstes_pruefdatum": pruef[0]["datum"],
        "ibans": {"giro": GIRO_IBAN, "kredit": KREDIT_IBAN},
        "kategorien": sorted({w["wahr"] for w in wahrheit} | {w["kategorie"] for w in wahrheit}),
        "empfaenger": [n for _, n in EMPFAENGER],
        "buchungen": wahrheit,
    }
    return {"kbuch": kb, "training": tb, "gbuch": gb, "mock": mock, "erwartung": erw}


# ================================================================ Vorlagen

V_GIRO = fiktive_iban(5101)
V_KATEGORIEN = [("Haftpflicht", "aufwand"), ("Hausrat", "aufwand"), ("Unfall", "aufwand"), ("KFZ", "aufwand"),
                ("Rechtsschutz", "aufwand"), ("Strom", "aufwand"), ("Gas", "aufwand"), ("Wasser", "aufwand"),
                ("Lebensmittel", "aufwand"), ("Gehalt", "ertrag"), ("Erstattungen", "ertrag"),
                ("Versicherungen", "aufwand")]
V_VORLAGEN = [
    {"name": "Versicherung monatlich", "prioritaet": 10,
     "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktiva Versicherung AG"},
                     {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Verträge 0001/0002/0003"}],
     "teile": [{"kategorie": "Haftpflicht", "betrag": 650, "memo": "Privathaftpflicht Nr. 0001"},
               {"kategorie": "Hausrat", "betrag": 1290, "memo": "Hausrat Nr. 0002"},
               {"kategorie": "Unfall", "betrag": 1850, "memo": "Unfall Nr. 0003"}]},
    {"name": "Versicherung jährlich", "prioritaet": 20,
     "bedingungen": [{"feld": "empfaenger", "operator": "beginnt_mit", "wert": "fiktiva versicherung"},
                     {"feld": "verwendungszweck", "operator": "beginnt_mit", "wert": "jahresbeitrag"}],
     "teile": [{"kategorie": "KFZ", "betrag": 41200, "memo": "KFZ Nr. 0004"},
               {"kategorie": "Rechtsschutz", "betrag": 18900, "memo": "Rechtsschutz Nr. 0005"}]},
    {"name": "Stadtwerke Abschlag", "prioritaet": 30,
     "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "STADTWERKE"},
                     {"feld": "verwendungszweck", "operator": "beginnt_mit", "wert": "Abschlag"},
                     {"feld": "konto_id", "operator": "gleich", "wert": {"iban": V_GIRO}}],
     "teile": [{"kategorie": "Strom", "betrag": 6500, "memo": "Strom"},
               {"kategorie": "Gas", "betrag": 4200, "memo": "Gas"},
               {"kategorie": "Wasser", "betrag": 2100, "memo": "Wasser"}]},
]
V_ANGEPASST = {"vorlage": "Versicherung monatlich",
               "teile": [{"kategorie": "Haftpflicht", "betrag": 650, "memo": "Privathaftpflicht Nr. 0001"},
                         {"kategorie": "Hausrat", "betrag": 1340, "memo": "Hausrat Nr. 0002 (neuer Beitrag)"},
                         {"kategorie": "Unfall", "betrag": 1850, "memo": "Unfall Nr. 0003"}]}
V_STUFEN = ["2024-06-30", "2024-09-30", "2024-12-31"]
V_BEITRAG_AB = "2024-07"


def _gesamt(teile: list[dict]) -> int:
    return -sum(t["betrag"] for t in teile)


def vorlagendaten(startwert: int) -> dict:
    rng = random.Random(startwert + 41)
    umsaetze: list[dict] = []
    fall: dict[str, dict] = {}

    def neu(tag: dt.date, betrag: int, name: str | None, zweck: str, meta: dict, **extra) -> None:
        uid = f"V-{len(umsaetze) + 1:04d}"
        umsaetze.append({"umsatz_id": uid, "iban": V_GIRO, "buchungstag": tag.isoformat(), "valuta": tag.isoformat(),
                         "betrag": betrag, "waehrung": "EUR", "gegenpartei_name": name, "gegenpartei_iban": None,
                         "verwendungszweck": zweck, "vormerkung": False, "storno": False, **extra})
        fall[uid] = meta

    mon, jahr_v, stadt = V_VORLAGEN
    for monat in range(1, 13):
        erster = dt.date(2024, monat, 1)
        while erster.weekday() >= 5:
            erster += dt.timedelta(days=1)
        extra = {}
        if f"2024-{monat:02d}" >= V_BEITRAG_AB:
            extra["betrag_beitragsaenderung"] = _gesamt(V_ANGEPASST["teile"])
        neu(erster, _gesamt(mon["teile"]), "Fiktiva Versicherung AG",
            f"Beiträge {monat:02d}/2024 Verträge 0001/0002/0003", {"vorlage": mon["name"]}, **extra)
        # Stadtwerke: im Oktober 1 Cent mehr, im November 1 Cent weniger (keine Toleranz)
        betrag = _gesamt(stadt["teile"]) + {10: -1, 11: 1}.get(monat, 0)
        neu(dt.date(2024, monat, 5), betrag, "Stadtwerke Musterstadt GmbH",
            f"Abschlag {monat:02d}/2024 Kundennummer 4711 Strom Gas Wasser", {"vorlage": stadt["name"]})
        neu(dt.date(2024, monat, 28), 330000, "Arbeitgeber Muster GmbH", f"LOHN/GEHALT {monat:02d}/2024",
            {"vorlage": None})
        for _ in range(rng.randint(2, 4)):
            neu(dt.date(2024, monat, rng.randint(2, 27)), -rng.randint(800, 9000), "Supermarkt Frischekorb",
                "Einkauf Filiale", {"vorlage": None})
    neu(dt.date(2024, 3, 15), _gesamt(jahr_v["teile"]), "Fiktiva Versicherung AG", "Jahresbeitrag 2024 Verträge 0004/0005",
        {"vorlage": jahr_v["name"]})
    neu(dt.date(2024, 4, 18), 12000, "Fiktiva Versicherung AG", "Erstattung Schaden 0003", {"vorlage": None})
    # Stadtwerke-Muster ohne Abschlag: keine Vorlage, keine Abweichung
    neu(dt.date(2024, 9, 20), -4711, "Stadtwerke Musterstadt GmbH", "Jahresabrechnung 2023 Nachzahlung",
        {"vorlage": None})
    umsaetze.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))

    teile_von = {v["name"]: v["teile"] for v in V_VORLAGEN}

    def ergebnis(u: dict, szenario: str, angepasst: bool) -> dict:
        v = fall[u["umsatz_id"]]["vorlage"]
        betrag = u["betrag"]
        if szenario == "beitragsaenderung" and "betrag_beitragsaenderung" in u:
            betrag = u["betrag_beitragsaenderung"]
        if v is None:
            return {"ergebnis": "keine", "betrag": betrag}
        teile = V_ANGEPASST["teile"] if angepasst and v == V_ANGEPASST["vorlage"] else teile_von[v]
        if _gesamt(teile) == betrag:
            return {"ergebnis": "gesplittet", "vorlage": v, "betrag": betrag,
                    "splits": [{"kategorie": t["kategorie"], "betrag": t["betrag"], "memo": t["memo"]} for t in teile]}
        return {"ergebnis": "abweichung", "vorlage": v, "betrag": betrag, "gesamtbetrag": _gesamt(teile)}

    def stufe(u: dict) -> int:
        return next(i for i, s in enumerate(V_STUFEN) if u["buchungstag"] <= s)

    erw = {
        "beschreibung": "Split-Vorlagen (vorlagen.md): Ergebnis je Umsatz in den Szenarien normal und "
                        "beitragsaenderung. Ablauf beitragsaenderung: Abruf zu jeder Stufe (mock_heute), nach "
                        "Stufe 2 wird die Vorlage auf m4/vorlagen.json 'angepasst' geändert.",
        "iban": V_GIRO, "stufen": V_STUFEN, "beitrag_ab": V_BEITRAG_AB, "anpassung_nach_stufe": 1,
        "normal": {u["umsatz_id"]: ergebnis(u, "normal", False) for u in umsaetze},
        "beitragsaenderung": {u["umsatz_id"]: {**ergebnis(u, "beitragsaenderung", stufe(u) == 2), "stufe": stufe(u)}
                              for u in umsaetze},
    }
    # Benachrichtigungen (vorlagen.md 6): je (Vorlage, Betrag) eine, solange ungelesen
    for sz in ("normal", "beitragsaenderung"):
        schl = []
        for u in umsaetze:
            e = erw[sz][u["umsatz_id"]]
            if e["ergebnis"] == "abweichung" and (e["vorlage"], e["betrag"]) not in schl:
                schl.append((e["vorlage"], e["betrag"]))
        erw[f"benachrichtigungen_{sz}"] = [{"vorlage": v, "betrag": b} for v, b in schl]
    mock = {"format": "kontor-mock-daten", "version": 1, "bank": {"konten": [
        {"iban": V_GIRO, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto",
         "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"}], "umsaetze": umsaetze},
        "mail": {"postfaecher": ["haushalt.eins@example.invalid"], "nachrichten": []}}
    stamm = {"beschreibung": "Kategorien und Split-Vorlagen (vorlagen.md); kategorie = Name, konto_id-Wert "
                             "{\"iban\": …} auf das Konto mit dieser IBAN abbilden",
             "kategorien": [{"name": n, "art": a} for n, a in V_KATEGORIEN], "vorlagen": V_VORLAGEN,
             "angepasst": V_ANGEPASST}
    return {"mock": mock, "erwartung": erw, "stammdaten": stamm}


# ================================================================ alles

def erzeuge_m4(startwert: int, kmy_erw_bis_2023: dict) -> tuple[dict[str, object], dict[str, str]]:
    """Liefert ({Pfad: Bytes oder JSON-Objekt}, {Pfad: Beschreibung})."""
    d: dict[str, object] = {}
    besch: dict[str, str] = {}

    def gueltig(pfad: str, gb: GBuch, fmt: str, text: str) -> None:
        if fmt == "gnc-sqlite":
            d[pfad] = als_gnc_sqlite(gb)
        else:
            x = als_gnc_xml(gb)
            d[pfad] = packe_gzip(x) if fmt == "gnc-xml-gzip" else x
        e = gnc_erwartung(gb, fixture=pfad, format_=fmt)
        e["startwert"] = startwert
        d[pfad.replace(".gnucash", ".erwartung.json")] = e
        besch[pfad] = text

    mini, _ = aus_kbuch(minimal_buch(), "minimal")
    gueltig("gnc/minimal.gnucash", mini, "gnc-xml-gzip", "Kleinstes Buch (wie kmy/minimal.kmy) als GnuCash-XML, gzip")
    gueltig("gnc/minimal_unkomprimiert.gnucash", mini, "gnc-xml", "Wie minimal.gnucash, unkomprimiertes XML")
    gueltig("gnc/minimal.sqlite.gnucash", mini, "gnc-sqlite", "Wie minimal.gnucash, GnuCash-SQLite")
    sf = sonderfaelle_gbuch()
    gueltig("gnc/sonderfaelle.gnucash", sf, "gnc-xml",
            "Sonderfälle als unkomprimiertes XML: Umlaute, langer Verwendungszweck, ohne Beschreibung, tiefe "
            "Kategorien, 13 Splits, versteckt, Kontoarten, IBAN-Fälle, Brüche, Ausgleich, Überspringen, Vorlagen")
    gueltig("gnc/sonderfaelle.sqlite.gnucash", sf, "gnc-sqlite",
            "Dieselben Sonderfälle als GnuCash-SQLite (inkl. Datum im 14-Ziffern-Format, Vorlagenbaum)")
    std, _ = aus_kbuch(standard_buch(startwert), "standard")
    gueltig("gnc/standard.gnucash", std, "gnc-xml-gzip", "Standardbuch 2022–2024 (wie kmy/standard.kmy) als GnuCash-XML")
    gb, erw = ueberlappung(startwert, kmy_erw_bis_2023)
    d["gnc/ueberlappung.sqlite.gnucash"] = als_gnc_sqlite(gb)
    erw["startwert"] = startwert
    d["gnc/ueberlappung.erwartung.json"] = erw
    besch["gnc/ueberlappung.sqlite.gnucash"] = ("Standardbuch ab 01.03.2023 als SQLite; überschneidet sich mit "
                                                "kmy/standard_bis_2023.kmy (Erwartung nach_kmy)")
    for pfad, inhalt, code, fmt, text, refs in stoerfaelle(mini, als_xml(minimal_buch())):
        d[pfad] = inhalt
        e = fehler_erwartung(pfad, code, fmt, text)
        e["referenzen"] = refs
        d[pfad.replace(".gnucash", ".erwartung.json")] = e
        besch[pfad] = text

    lern = lerndaten(startwert)
    d["kmy/m4_lernen_training.kmy"] = packe_gzip(als_xml(lern["training"]))
    e = erwartung(lern["training"], fixture="kmy/m4_lernen_training.kmy", format_="kmy-gzip")
    e["startwert"] = startwert
    d["kmy/m4_lernen_training.erwartung.json"] = e
    besch["kmy/m4_lernen_training.kmy"] = "M4: nur die älteren 80 % des Lerndatensatzes (Training)"
    x = als_gnc_xml(lern["gbuch"])
    d["gnc/m4_lernen_training.gnucash"] = packe_gzip(x)
    besch["gnc/m4_lernen_training.gnucash"] = ("M4: Trainingsteil des Lerndatensatzes als GnuCash-XML (gleicher Inhalt "
                                               "wie kmy/m4_lernen_training.kmy; Erwartung dort)")
    d["mock/m4_lernen.json"] = lern["mock"]
    besch["mock/m4_lernen.json"] = "M4: Prüfbuchungen des Lerndatensatzes (neueste 20 %) als Bankumsätze"
    lern["erwartung"]["startwert"] = startwert
    d["m4/lernen.erwartung.json"] = lern["erwartung"]
    besch["m4/lernen.erwartung.json"] = "M4: bekannte Wahrheit des Lerndatensatzes (Kategorie, Teil, Fehler)"

    v = vorlagendaten(startwert)
    d["mock/m4_vorlagen.json"] = v["mock"]
    besch["mock/m4_vorlagen.json"] = ("M4: Sammelabbuchungen 2024 (Versicherung monatlich/jährlich, Stadtwerke) mit "
                                      "betrag_beitragsaenderung ab Juli und Abweichungen um 1 Cent")
    v["erwartung"]["startwert"] = startwert
    d["mock/m4_vorlagen.erwartung.json"] = v["erwartung"]
    besch["mock/m4_vorlagen.erwartung.json"] = "M4: Ergebnis je Umsatz (gesplittet, abweichung, keine) je Szenario"
    d["m4/vorlagen.json"] = v["stammdaten"]
    besch["m4/vorlagen.json"] = "M4: Kategorien, Split-Vorlagen und die angepasste Vorlage nach der Beitragsänderung"
    return d, besch
