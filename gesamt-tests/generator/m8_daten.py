"""Datensätze für die Oberflächentests von Meilenstein 8 (``spec/api/oberflaeche.md``).

``m8/oberflaeche.kmy``: kleines Haushaltsbuch 2024 mit Kategorienbaum (drei Ebenen), Umlauten, einem
HTML-artigen Verwendungszweck (Prüfung „nur als Text“), einer Splitbuchung, Tags, einem geschlossenen Konto
und einem Darlehenskonto für den Kreditabgleich. ``m8/viele.kmy``: ein Konto mit 450 Buchungen für das
seitenweise Laden der Liste (200 je Seite).

Die Erwartungen (bekannte Wahrheit) kommen aus ``kmy.erwartung`` und werden um oberflächenspezifische
Angaben ergänzt: Kategorienpfade, Baumreihenfolge, Filterfälle mit den erwarteten Buchungen (aus dem Modell
berechnet, nicht aus einer Ausgabe der Anwendung). Alle Daten sind synthetisch.
"""

from __future__ import annotations

import datetime as dt
import random
import unicodedata

from .iban import fiktive_iban
from .kmy import KBuch, KKonto, KSplit, als_xml, erwartung, packe_gzip
from .szenarien import _Sammler, _einfach, _umbuchung, _werktag

GIRO, TAGESGELD, SPARBUCH, KARTE, DARLEHEN = "A000001", "A000002", "A000003", "A000004", "A000005"
LEBENSMITTEL, WOHNEN, MIETE, STROM, FREIZEIT, KINO, HAUSHALT, MOBIL, ZINSEN, KINO_3D = (
    "A000010", "A000011", "A000012", "A000013", "A000014", "A000015", "A000016", "A000017", "A000018", "A000019")
GEHALT, ERSTATTUNG = "A000020", "A000021"

EMPF = [
    ("P000001", "Arbeitgeber Muster GmbH"),
    ("P000002", "Supermarkt Frischekorb"),
    ("P000003", "Bäckerei Körnchen"),
    ("P000004", "Stadtwerke Beispielstadt"),
    ("P000005", "Hausverwaltung Fiktiv"),
    ("P000006", "Kino Lichtspiel"),
    ("P000007", "Tankstelle Ölquelle"),
    ("P000008", "Fiktivbank AG"),
    ("P000009", "Café Übersee"),
]
TAGS = [("G000001", "Urlaub"), ("G000002", "Steuer"), ("G000003", "Geschenk")]

#: wörtlich darzustellender Verwendungszweck (oberflaeche.md 1 Nr. 5)
HTML_TEXT = '<img src=x onerror=alert(1)> & "Café" <b>fett</b>'
UMLAUT_ZWECK = "Brötchen für Jürgens Geburtstag"


def oberflaeche_buch(startwert: int) -> KBuch:
    zufall = random.Random(startwert * 8 + 1)
    b = KBuch(erstellt="2023-12-31", geaendert="2025-01-02")
    b.konten = [
        KKonto(GIRO, "Girokonto", 1, "AStd::Asset", eroeffnet="2024-01-01", iban=fiktive_iban(8001)),
        KKonto(TAGESGELD, "Tagesgeld", 2, "AStd::Asset", eroeffnet="2024-01-01", iban=fiktive_iban(8002)),
        KKonto(SPARBUCH, "Altes Sparbuch", 2, "AStd::Asset", eroeffnet="2020-01-01", geschlossen=True),
        KKonto(KARTE, "Kreditkarte", 4, "AStd::Liability", eroeffnet="2024-01-01"),
        KKonto(DARLEHEN, "Darlehen Fiktivbank", 5, "AStd::Liability", eroeffnet="2024-01-01"),
        KKonto(LEBENSMITTEL, "Lebensmittel", 13, "AStd::Expense"),
        KKonto(WOHNEN, "Wohnen", 13, "AStd::Expense"),
        KKonto(MIETE, "Miete", 13, WOHNEN),
        KKonto(STROM, "Strom", 13, WOHNEN),
        KKonto(FREIZEIT, "Freizeit", 13, "AStd::Expense"),
        KKonto(KINO, "Kino", 13, FREIZEIT),
        KKonto(KINO_3D, "3D-Vorstellungen", 13, KINO),
        KKonto(HAUSHALT, "Haushalt", 13, "AStd::Expense"),
        KKonto(MOBIL, "Mobilität", 13, "AStd::Expense"),
        KKonto(ZINSEN, "Zinsen", 13, "AStd::Expense"),
        KKonto(GEHALT, "Gehalt", 12, "AStd::Income"),
        KKonto(ERSTATTUNG, "Erstattungen", 12, "AStd::Income"),
    ]
    b.empfaenger = list(EMPF)
    b.tags = list(TAGS)
    s = _Sammler()
    for monat in range(1, 13):
        _einfach(s, _werktag(dt.date(2024, monat, 1)), GIRO, MIETE, -95000, "P000005", f"Miete {monat:02d}/2024")
        _einfach(s, _werktag(dt.date(2024, monat, 5)), GIRO, STROM, -6500 - 100 * (monat % 3), "P000004",
                 f"Abschlag Strom {monat:02d}/2024")
        _einfach(s, dt.date(2024, monat, 28), GIRO, GEHALT, 310000, "P000001", f"Gehalt {monat:02d}/2024")
        for tag in (9, 21):
            betrag = -(2000 + zufall.randrange(0, 6000, 5))
            _einfach(s, _werktag(dt.date(2024, monat, tag)), GIRO, LEBENSMITTEL, betrag, "P000002",
                     "Wocheneinkauf")
    for i, monat in enumerate((2, 4, 6, 8, 10, 12), start=1):
        _einfach(s, dt.date(2024, monat, 14), GIRO, LEBENSMITTEL, -(350 + 25 * i), "P000003",
                 UMLAUT_ZWECK if i == 3 else "Brötchen")
    for i, monat in enumerate((3, 5, 7, 11), start=1):
        _einfach(s, dt.date(2024, monat, 17), GIRO, KINO, -(1200 + 100 * i), "P000006", "Kinokarten",
                 ["G000001"] if monat == 7 else None)
    _einfach(s, dt.date(2024, 9, 18), GIRO, KINO_3D, -1890, "P000006", "3D-Film")
    for i, monat in enumerate((1, 3, 5, 7, 9, 11), start=1):
        _einfach(s, dt.date(2024, monat, 12), GIRO, MOBIL, -(6000 + 150 * i), "P000007", "Tanken")
    for monat in (3, 6, 9, 12):
        _umbuchung(s, dt.date(2024, monat, 15), GIRO, TAGESGELD, 50000, "Sparrate")
    # Splitbuchung: Einkauf auf zwei Kategorien
    s.neu(dt.date(2024, 4, 20), [
        KSplit(GIRO, -5500, memo="Großeinkauf", empfaenger="P000002"),
        KSplit(LEBENSMITTEL, 4000, memo="Essen", empfaenger="P000002"),
        KSplit(HAUSHALT, 1500, memo="Putzmittel", empfaenger="P000002"),
    ], memo="Großeinkauf")
    _einfach(s, dt.date(2024, 5, 3), GIRO, ERSTATTUNG, 4250, "P000004", "Erstattung Abrechnung 2023", ["G000002"])
    _einfach(s, dt.date(2024, 6, 8), GIRO, HAUSHALT, -2999, "P000009", HTML_TEXT, ["G000003"])
    _einfach(s, dt.date(2024, 10, 2), GIRO, HAUSHALT, -1999, "", "Barkauf ohne Empfänger")
    for i in range(10):
        _einfach(s, dt.date(2024, 1 + i, 3 + i), KARTE, FREIZEIT if i % 2 else LEBENSMITTEL,
                 -(1500 + 333 * i), "P000009" if i % 2 else "P000002", f"Kartenzahlung {i + 1}")
    b.buchungen = s.buchungen()
    return b


def viele_buch(startwert: int) -> KBuch:
    zufall = random.Random(startwert * 8 + 2)
    b = KBuch(erstellt="2022-12-31", geaendert="2025-01-02")
    b.konten = [
        KKonto("A000001", "Haushaltskonto", 1, "AStd::Asset", eroeffnet="2023-01-01", iban=fiktive_iban(8101)),
        KKonto("A000002", "Lebensmittel", 13, "AStd::Expense"),
    ]
    b.empfaenger = [("P000001", "Supermarkt Frischekorb")]
    s = _Sammler()
    tag = dt.date(2023, 1, 2)
    for n in range(450):
        _einfach(s, tag, "A000001", "A000002", -(100 + zufall.randrange(0, 9000)), "P000001", f"Einkauf {n + 1:03d}")
        if n % 3 == 2:
            tag += dt.timedelta(days=1)
    b.buchungen = s.buchungen()
    return b


# ---------------------------------------------------------------- Erwartung
def _norm(s: str) -> str:
    """Vergleich für Text-Filter wie datenmodell.md (casefold mit Umlautfaltung, NFC) – nur für die Fälle hier."""
    s = unicodedata.normalize("NFC", s).casefold()
    return s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def _pfade(buch: KBuch) -> dict[str, str]:
    namen = {k.id: k for k in buch.konten}

    def pfad(kid: str) -> str:
        k = namen[kid]
        return k.name if k.eltern not in namen else pfad(k.eltern) + " › " + k.name
    return {k.id: pfad(k.id) for k in buch.konten}


def _baum(buch: KBuch, klasse: int) -> list[str]:
    """Kategorien einer Klasse in Baumreihenfolge (Geschwister nach Name), als extern_id."""
    kinder: dict[str, list[KKonto]] = {}
    for k in buch.konten:
        if k.typ == klasse:
            kinder.setdefault(k.eltern, []).append(k)
    aus: list[str] = []

    def schluessel(k: KKonto) -> str:
        return _norm(k.name)

    def gehe(eltern: str) -> None:
        for k in sorted(kinder.get(eltern, []), key=schluessel):
            aus.append("kmy:" + k.id)
            gehe(k.id)
    gehe("AStd::Expense" if klasse == 13 else "AStd::Income")
    return aus


def oberflaeche_erwartung(startwert: int) -> dict:
    buch = oberflaeche_buch(startwert)
    erw = erwartung(buch, fixture="m8/oberflaeche.kmy", format_="kmy-gzip")
    erw["startwert"] = startwert
    giro = "kmy:" + GIRO
    buchungen = erw["buchungen"]

    def auf_giro(b: dict) -> int | None:
        werte = [s["betrag"] for s in b["splits"] if s["konto_extern_id"] == giro]
        return sum(werte) if werte else None

    giro_b = [b for b in buchungen if auf_giro(b) is not None]
    pfade = _pfade(buch)
    unter_wohnen = {"kmy:" + k for k in (WOHNEN, MIETE, STROM)}

    def ids(liste):
        return sorted(b["extern_id"] for b in liste)

    faelle = [
        {"name": "zeitraum_maerz", "parameter": {"von": "2024-03-01", "bis": "2024-03-31"},
         "erwartet": ids(b for b in giro_b if "2024-03-01" <= b["datum"][:10] <= "2024-03-31")},
        {"name": "betrag_ausgaben_50_bis_100", "parameter": {"betrag_min": -10000, "betrag_max": -5000},
         "erwartet": ids(b for b in giro_b if -10000 <= auf_giro(b) <= -5000)},
        {"name": "verwendungszweck_umlaut", "parameter": {"verwendungszweck": "jürgens"},
         "erwartet": ids(b for b in giro_b if "juergens" in _norm(b["verwendungszweck"]))},
        {"name": "kategorie_wohnen_mit_unterkategorien",
         "parameter": {"kategorie_extern_id": "kmy:" + WOHNEN, "unterkategorien": True},
         "erwartet": ids(b for b in giro_b if b["kategorie_extern_id"] in unter_wohnen)},
        {"name": "tag_urlaub", "parameter": {"tag_extern_id": "kmy:G000001"},
         "erwartet": ids(b for b in giro_b if "kmy:G000001" in b["tags"])},
        {"name": "empfaenger_baeckerei", "parameter": {"empfaenger_name": "Bäckerei Körnchen"},
         "erwartet": ids(b for b in giro_b if b["empfaenger"] == "Bäckerei Körnchen")},
        {"name": "ohne_empfaenger", "parameter": {"ohne_empfaenger": True},
         "erwartet": ids(b for b in giro_b if not b["empfaenger"])},
    ]
    for f in faelle:
        assert f["erwartet"], f["name"]
    erw["m8"] = {
        "konten": {"giro": giro, "tagesgeld": "kmy:" + TAGESGELD, "sparbuch_geschlossen": "kmy:" + SPARBUCH,
                   "kreditkarte": "kmy:" + KARTE, "darlehen": "kmy:" + DARLEHEN, "zinsen": "kmy:" + ZINSEN,
                   "lebensmittel": "kmy:" + LEBENSMITTEL, "wohnen": "kmy:" + WOHNEN, "miete": "kmy:" + MIETE,
                   "strom": "kmy:" + STROM, "freizeit": "kmy:" + FREIZEIT, "kino": "kmy:" + KINO,
                   "kino_3d": "kmy:" + KINO_3D, "haushalt": "kmy:" + HAUSHALT, "mobilitaet": "kmy:" + MOBIL,
                   "gehalt": "kmy:" + GEHALT, "erstattungen": "kmy:" + ERSTATTUNG},
        "pfade": {"kmy:" + k: v for k, v in pfade.items()},
        "baum_aufwand": _baum(buch, 13),
        "baum_ertrag": _baum(buch, 12),
        "giro_anzahl": len(giro_b),
        "giro_saldo": sum(auf_giro(b) for b in giro_b),
        "html_text": HTML_TEXT,
        "umlaut_zweck": UMLAUT_ZWECK,
        "split_buchung": next(b["extern_id"] for b in giro_b if len(b["splits"]) == 3),
        "filterfaelle": faelle,
    }
    return erw


def erzeuge_m8(startwert: int) -> tuple[dict[str, object], dict[str, str]]:
    dateien: dict[str, object] = {}
    text: dict[str, str] = {}
    dateien["m8/oberflaeche.kmy"] = packe_gzip(als_xml(oberflaeche_buch(startwert)))
    dateien["m8/oberflaeche.erwartung.json"] = oberflaeche_erwartung(startwert)
    text["m8/oberflaeche.kmy"] = ("M8: Haushaltsbuch 2024 für Oberflächentests (Kategorienbaum, Umlaute, "
                                  "HTML-artiger Text, Splitbuchung, Tags, geschlossenes Konto, Darlehen)")
    text["m8/oberflaeche.erwartung.json"] = ("M8: bekannte Wahrheit, Kategorienpfade und Baumreihenfolge, "
                                             "Filterfälle mit erwarteten Buchungen")
    v = viele_buch(startwert)
    dateien["m8/viele.kmy"] = packe_gzip(als_xml(v))
    ev = erwartung(v, fixture="m8/viele.kmy", format_="kmy-gzip")
    ev["startwert"] = startwert
    dateien["m8/viele.erwartung.json"] = ev
    text["m8/viele.kmy"] = "M8: ein Konto mit 450 Buchungen (seitenweises Laden der Buchungsliste)"
    text["m8/viele.erwartung.json"] = "M8: bekannte Wahrheit zu viele.kmy"
    return dateien, text
