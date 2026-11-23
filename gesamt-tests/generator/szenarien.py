"""Aufbau der KMyMoney-Testbücher.

Alle Daten sind synthetisch: fiktive Empfänger, Test-IBANs mit BLZ 00000000,
Adressen unter example.invalid. Zufall nur über ``random.Random(startwert)``
mit fester Aufrufreihenfolge.
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import ROUND_HALF_UP, Decimal

from .iban import fiktive_iban, ungueltige_iban
from .kmy import FEHLT, KBuch, KBuchung, KKonto, KSplit


def _tid(n: int) -> str:
    return f"T{n:018d}"


def _werktag(d: dt.date) -> dt.date:
    """Wochenende → folgender Montag (Wochenendverschiebung)."""
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def _monatsende(jahr: int, monat: int) -> dt.date:
    if monat == 12:
        return dt.date(jahr, 12, 31)
    return dt.date(jahr, monat + 1, 1) - dt.timedelta(days=1)


def _rund(x: Decimal) -> int:
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class _Sammler:
    """Sammelt Buchungen, sortiert sie stabil nach Datum und vergibt IDs."""

    def __init__(self) -> None:
        self._roh: list[tuple[str, int, dict]] = []

    def neu(self, datum: dt.date | str, splits: list[KSplit], **kw) -> None:
        d = datum.isoformat() if isinstance(datum, dt.date) else datum
        self._roh.append((d[:10], len(self._roh), {"datum": d, "splits": splits, **kw}))

    def buchungen(self) -> list[KBuchung]:
        aus = []
        for n, (_, _, kw) in enumerate(sorted(self._roh, key=lambda r: (r[0], r[1])), start=1):
            aus.append(KBuchung(id=_tid(n), **kw))
        return aus


def _einfach(s: _Sammler, datum, konto: str, kategorie: str, betrag: int, empf: str = "",
             memo: str = "", tags: list[str] | None = None) -> None:
    """Einfache Buchung Bestandskonto ↔ Kategorie; betrag aus Sicht des Kontos."""
    s.neu(datum, [
        KSplit(konto, betrag, memo=memo, empfaenger=empf, tags=list(tags or [])),
        KSplit(kategorie, -betrag, memo="", empfaenger=empf),
    ], memo=memo, wahre_kategorie=kategorie)


def _umbuchung(s: _Sammler, datum, von: str, nach: str, betrag: int, memo: str,
               empf: str = "") -> None:
    s.neu(datum, [
        KSplit(von, -betrag, memo=memo, empfaenger=empf),
        KSplit(nach, betrag, memo=memo, empfaenger=empf),
    ], memo=memo, umbuchung=True)


# =================================================================== standard


def standard_buch(startwert: int, bis: dt.date | None = None) -> KBuch:
    """Drei Jahre Haushaltsbuch 2022–2024 (T 21: realistische Muster, Störfälle)."""
    rng = random.Random(startwert)
    b = KBuch()
    G, SP, KK, DH, DA, ALT = "A000001", "A000002", "A000003", "A000004", "A000005", "A000006"
    EK = "A000010"
    GEH, ZINS_E = "A000020", "A000021"
    LEB, WOHN, MIETE, STROM = "A000030", "A000031", "A000032", "A000033"
    MOB, TANK = "A000034", "A000035"
    VERS, HAFT, HAUS, UNF = "A000036", "A000037", "A000038", "A000039"
    FREI, STREAM, CAFE = "A000040", "A000041", "A000042"
    KZINS, SONST = "A000043", "A000044"
    b.konten = [
        KKonto(G, "Girokonto", 1, "AStd::Asset", eroeffnet="2015-04-01", iban=fiktive_iban(1001), nummer="1001"),
        KKonto(SP, "Tagesgeld", 2, "AStd::Asset", eroeffnet="2018-02-01", iban=fiktive_iban(1002), nummer="1002"),
        KKonto(KK, "Kreditkarte", 4, "AStd::Liability", eroeffnet="2019-06-01"),
        KKonto(DH, "Darlehen Haus", 5, "AStd::Liability", eroeffnet="2020-01-01",
               beschreibung="Annuitätendarlehen 2,10 % – fiktiv"),
        KKonto(DA, "Darlehen Auto", 5, "AStd::Liability", eroeffnet="2021-07-01",
               beschreibung="Annuitätendarlehen 3,90 % – fiktiv"),
        KKonto(ALT, "Altes Sparbuch", 2, "AStd::Asset", eroeffnet="2001-01-01",
               iban=fiktive_iban(1006), geschlossen=True, nummer="1006"),
        KKonto(EK, "Anfangsbestand", 16, "AStd::Equity"),
        KKonto(GEH, "Gehalt", 12, "AStd::Income"),
        KKonto(ZINS_E, "Zinserträge", 12, "AStd::Income"),
        KKonto(LEB, "Lebensmittel", 13, "AStd::Expense"),
        KKonto(WOHN, "Wohnen", 13, "AStd::Expense"),
        KKonto(MIETE, "Miete", 13, WOHN),
        KKonto(STROM, "Strom", 13, WOHN),
        KKonto(MOB, "Mobilität", 13, "AStd::Expense"),
        KKonto(TANK, "Tanken", 13, MOB),
        KKonto(VERS, "Versicherungen", 13, "AStd::Expense"),
        KKonto(HAFT, "Haftpflicht", 13, VERS),
        KKonto(HAUS, "Hausrat", 13, VERS),
        KKonto(UNF, "Unfall", 13, VERS),
        KKonto(FREI, "Freizeit", 13, "AStd::Expense"),
        KKonto(STREAM, "Streaming", 13, FREI),
        KKonto(CAFE, "Café & Restaurant", 13, FREI),
        KKonto(KZINS, "Kreditzinsen", 13, "AStd::Expense"),
        KKonto(SONST, "Sonstiges", 13, "AStd::Expense"),
    ]
    P_AG, P_WB, P_SW, P_SM, P_TS, P_VS, P_ST, P_CB, P_BM, P_TB, P_KH = (
        f"P{n:06d}" for n in range(1, 12))
    b.empfaenger = [
        (P_AG, "Arbeitgeber Muster GmbH"),
        (P_WB, "Wohnbau Beispiel eG"),
        (P_SW, "Stadtwerke Musterstadt"),
        (P_SM, "Supermarkt Frischekorb"),
        (P_TS, "Tankstelle Blitz"),
        (P_VS, "Fiktiva Versicherung AG"),
        (P_ST, "Streamio Media (fiktiv)"),
        (P_CB, "Café Bohne"),
        (P_BM, "Müller & Söhne Bäckerei"),
        (P_TB, "Testbank (fiktiv)"),
        (P_KH, "Kaufhaus „Übermaß“ <Sonderposten> & Co."),
    ]
    G_URL, G_STEU, G_GESCH = "G000001", "G000002", "G000003"
    b.tags = [(G_URL, "Urlaub"), (G_STEU, "Steuer"), (G_GESCH, "Geschäftlich")]

    s = _Sammler()
    # Anfangsbestände
    start = dt.date(2022, 1, 1)
    for konto, betrag in ((G, 350000), (SP, 1000000), (ALT, 120000), (DH, -15000000), (DA, -1500000)):
        s.neu(start, [KSplit(konto, betrag, memo="Anfangsbestand"), KSplit(EK, -betrag)],
              memo="Anfangsbestand")
    _umbuchung(s, dt.date(2022, 1, 14), ALT, SP, 120000, "Auflösung Sparbuch")

    rest_haus, rest_auto = Decimal(15000000), Decimal(1500000)
    kk_offen = 0
    kk_monat: list[int] = []
    for jahr in (2022, 2023, 2024):
        for monat in range(1, 13):
            erster = dt.date(jahr, monat, 1)
            # Gehalt
            gehalt = 335000 if (jahr, monat) >= (2023, 4) else 320000
            _einfach(s, _werktag(dt.date(jahr, monat, 28)), G, GEH, gehalt, P_AG,
                     f"LOHN/GEHALT {monat:02d}/{jahr}")
            # Miete
            miete = 98000 if jahr == 2024 else 95000
            _einfach(s, _werktag(erster), G, MIETE, -miete, P_WB, f"Miete {monat:02d}/{jahr} Musterweg 1")
            # Strom (Betragsänderung)
            strom = 9200 if (jahr, monat) >= (2023, 3) else 8500
            _einfach(s, _werktag(dt.date(jahr, monat, 5)), G, STROM, -strom, P_SW,
                     f"Abschlag Strom Vertrag 4711-{jahr}")
            # Streaming (ausbleibende Zahlung 08/2023, Preisänderung 2024)
            if (jahr, monat) != (2023, 8):
                abo = 1499 if jahr == 2024 else 1299
                _einfach(s, dt.date(jahr, monat, 12), G, STREAM, -abo, P_ST, "Abo Streamio Premium")
            # Sammelabbuchung Versicherung (Beitragsänderung 07/2023)
            hausrat = 1290 if (jahr, monat) >= (2023, 7) else 1200
            teile = [(HAFT, 650, "Privathaftpflicht Nr. 0001"), (HAUS, hausrat, "Hausrat Nr. 0002"),
                     (UNF, 1850, "Unfall Nr. 0003")]
            gesamt = sum(t[1] for t in teile)
            memo = f"Beiträge {monat:02d}/{jahr} Verträge 0001/0002/0003"
            s.neu(_werktag(erster), [KSplit(G, -gesamt, memo=memo, empfaenger=P_VS, tags=[G_STEU])]
                  + [KSplit(k, w, memo=m, empfaenger=P_VS) for k, w, m in teile], memo=memo)
            # Darlehen (Zins kaufmännisch gerundet, Tilgung = Rate − Zins)
            for konto, rate, satz, attr in ((DH, 80000, Decimal("0.021"), "haus"),
                                            (DA, 35000, Decimal("0.039"), "auto")):
                rest = rest_haus if attr == "haus" else rest_auto
                zins = _rund(rest * satz / 12)
                tilg = rate - zins
                memo = f"Rate {'Darlehen Haus' if attr == 'haus' else 'Darlehen Auto'} {monat:02d}/{jahr}"
                s.neu(_werktag(dt.date(jahr, monat, 15)), [
                    KSplit(G, -rate, memo=memo, empfaenger=P_TB),
                    KSplit(konto, tilg, memo="Tilgung", empfaenger=P_TB),
                    KSplit(KZINS, zins, memo="Zinsen", empfaenger=P_TB),
                ], memo=memo)
                if attr == "haus":
                    rest_haus -= tilg
                else:
                    rest_auto -= tilg
            # Umbuchung aufs Tagesgeld
            _umbuchung(s, _monatsende(jahr, monat), G, SP, 15000, "Sparrate Tagesgeld")
            # Kreditkartenabrechnung des Vormonats
            if kk_monat:
                summe = sum(kk_monat)
                _umbuchung(s, _werktag(dt.date(jahr, monat, 20)), G, KK, summe,
                           "Kreditkartenabrechnung", empf=P_TB)
                kk_offen -= summe
                kk_monat = []
            # Einkäufe mit Kreditkarte
            for _ in range(rng.randint(2, 4)):
                tag = rng.randint(1, 28)
                betrag = rng.randint(990, 15999)
                ziel = rng.choice([SONST, CAFE, SONST])
                empf = P_KH if ziel == SONST else P_CB
                _einfach(s, dt.date(jahr, monat, tag), KK, ziel, -betrag, empf,
                         "Kartenzahlung " + ("Kaufhaus" if ziel == SONST else "Café"))
                kk_monat.append(betrag)
                kk_offen += betrag
            # Zufällige Einzelkäufe vom Girokonto
            sommer = monat in (7, 8)
            for empf, kat, n_min, n_max, b_min, b_max, text in (
                (P_SM, LEB, 6, 10, 1500, 12000, "Einkauf Filiale"),
                (P_TS, TANK, 2, 3, 4000, 9000, "Tankstelle Säule"),
                (P_CB, CAFE, 2, 5, 250, 1200, "Kartenzahlung Café"),
                (P_BM, LEB, 3, 6, 180, 950, "Brötchen & Brezeln"),
            ):
                for _ in range(rng.randint(n_min, n_max)):
                    tag = rng.randint(1, 28)
                    betrag = rng.randint(b_min, b_max)
                    tags = [G_URL] if sommer and rng.random() < 0.3 else []
                    if empf == P_TS and rng.random() < 0.2:
                        tags.append(G_GESCH)
                    _einfach(s, dt.date(jahr, monat, tag), G, kat, -betrag, empf,
                             f"{text} {rng.randint(1, 999):03d}", tags)
            # Zinsen Tagesgeld quartalsweise
            if monat in (3, 6, 9, 12):
                _einfach(s, _monatsende(jahr, monat), SP, ZINS_E, rng.randint(800, 2500), P_TB,
                         f"Zinsen Q{monat // 3}/{jahr}")
        # Störfälle je Jahr
        # zweimal derselbe Kaffee am selben Tag (echte gleiche Buchungen)
        kaffee_tag = dt.date(jahr, 3, 17)
        for _ in range(2):
            _einfach(s, kaffee_tag, G, CAFE, -340, P_CB, "Kartenzahlung Café Cappuccino")
        # Kauf und Storno
        kauf = dt.date(jahr, 10, 9)
        _einfach(s, kauf, G, SONST, -24999, P_KH, "Kaufhaus Bestellung 0815 <Sonderposten> & \"Rabatt\"")
        _einfach(s, kauf + dt.timedelta(days=1), G, SONST, 24999, P_KH,
                 "STORNO: Kaufhaus Bestellung 0815 – Gutschrift")
        # Sonderzeichen und Umlaute
        _einfach(s, dt.date(jahr, 12, 22), G, SONST, -4711, P_KH,
                 "Geschenke: Ölgemälde, Würfelspiel & Bücher – „Weihnachten“ ☃ €")

    b.buchungen = s.buchungen()
    if bis is not None:
        b.buchungen = [t for t in b.buchungen if t.datum[:10] <= bis.isoformat()]
    return b


# =================================================================== minimal


def minimal_buch() -> KBuch:
    b = KBuch()
    b.konten = [
        KKonto("A000001", "Girokonto", 1, "AStd::Asset", eroeffnet="2024-01-01", iban=fiktive_iban(3001)),
        KKonto("A000002", "Lebensmittel", 13, "AStd::Expense"),
        KKonto("A000003", "Gehalt", 12, "AStd::Income"),
    ]
    b.empfaenger = [("P000001", "Arbeitgeber Muster GmbH"), ("P000002", "Supermarkt Frischekorb")]
    b.tags = [("G000001", "Haushalt")]
    s = _Sammler()
    _einfach(s, "2024-01-31", "A000001", "A000003", 100000, "P000001", "Gehalt Januar")
    _einfach(s, "2024-02-02", "A000001", "A000002", -2500, "P000002", "Wocheneinkauf", ["G000001"])
    b.buchungen = s.buchungen()
    return b


# ================================================================ sonderfaelle

LANGER_TEXT = ("Sehr langer Verwendungszweck mit Umlauten äöü ÄÖÜ ß und Zeichen <>&\"' – "
               * 80)[:5000]


def sonderfaelle_buch() -> KBuch:
    b = KBuch()
    giro, bar, alt, falsch, doppelt, sonst_v, ek, kk = (f"A{n:06d}" for n in range(1, 9))
    iban_alt = fiktive_iban(2003)
    iban_giro = fiktive_iban(2001)
    giro_eingabe = " ".join(iban_giro[i:i + 4] for i in range(0, len(iban_giro), 4)).lower()
    b.konten = [
        KKonto(giro, "Girokonto Ünïcödé & <Test> \"Haupt\"", 1, "AStd::Asset", iban=giro_eingabe),
        KKonto(bar, "Bargeld", 3, "AStd::Asset"),
        KKonto(alt, "Altkonto (geschlossen)", 1, "AStd::Asset", iban=iban_alt, geschlossen=True),
        KKonto(falsch, "Konto mit falscher IBAN", 2, "AStd::Asset", iban=ungueltige_iban(2004)),
        KKonto(doppelt, "Zweitkonto gleiche IBAN", 2, "AStd::Asset", iban=iban_alt),
        KKonto(sonst_v, "Sonstiges Vermögen", 9, "AStd::Asset"),
        KKonto(ek, "Anfangsbestand", 16, "AStd::Equity"),
        KKonto(kk, "Kreditkarte", 4, "AStd::Liability", eroeffnet="2023-13-45",
               beschreibung=FEHLT, waehrung=FEHLT),
        KKonto("A000010", "Haushalt", 13, "AStd::Expense"),
        KKonto("A000011", "Küche", 13, "A000010"),
        KKonto("A000012", "Geräte", 13, "A000011"),
        KKonto("A000013", "Kleingeräte & Zubehör", 13, "A000012"),
        KKonto("A000014", "Geschenke", 13, "AStd::Expense"),
        KKonto("A000015", "Spenden", 13, "AStd::Expense"),
        KKonto("A000016", "Erstattungen", 12, "AStd::Income"),
        KKonto("A000017", "Falsch einsortierte Ausgabe", 13, "A000016"),
        KKonto("A000019", "Sammelposten", 13, "AStd::Expense"),
    ] + [KKonto(f"A{20 + i:06d}", f"Teil {i + 1:02d}", 13, "A000019") for i in range(12)]
    b.empfaenger = [
        ("P000001", "Bäckerei Größenwahn – Inh. Jürgen Weiß"),
        ("P000002", "Ça va? Café „Zum Ölfass“ <&> 'Zitat' \"doppelt\""),
        ("P000003", "Ärger GmbH"),
        ("P000004", "Ärger GmbH"),
        ("P000005", "☕ Emoji-Kiosk 🙂"),
    ]
    b.tags = [("G000001", "Urlaub"), ("G000002", "urlaub"), ("G000003", "Steuer 2023 – §35a")]
    s = _Sammler()
    s.neu("2023-01-01", [KSplit(giro, 100000, memo="Start"), KSplit(ek, -100000)], memo="Anfangsbestand")
    s.neu("2023-01-01", [KSplit(alt, 5000), KSplit(ek, -5000)], memo="Anfangsbestand Altkonto")
    s.neu("2023-01-01", [KSplit(bar, 20000), KSplit(ek, -20000)], memo="Anfangsbestand Bargeld")
    # sehr langer Verwendungszweck
    _einfach(s, "2023-01-05", giro, "A000013", -1234, "P000001", LANGER_TEXT)
    # ohne Empfänger, ohne memo-Attribute
    s.neu("2023-01-06", [KSplit(giro, -2000, memo=FEHLT, empfaenger=FEHLT),
                         KSplit("A000014", 2000, memo=FEHLT, empfaenger=FEHLT)],
          memo=FEHLT, wahre_kategorie="A000014")
    # Split mit 13 Teilen (12 Kategorien + Konto), Tags auf verschiedenen Splits
    werte = [101 * (i + 1) for i in range(12)]
    teile = [KSplit(giro, -sum(werte), memo="Sammelrechnung", empfaenger="P000002", tags=["G000001"])]
    for i, w in enumerate(werte):
        teile.append(KSplit(f"A{20 + i:06d}", w, memo=f"Position {i + 1} – Ä{i}",
                            empfaenger="P000002", tags=(["G000002", "G000003"] if i == 3 else [])))
    s.neu("2023-02-01", teile, memo="Sammelrechnung mit zwölf Positionen")
    # gekürzte Brüche und ganze Zahlen
    s.neu("2023-02-02", [KSplit(giro, -1234, wert_text="-617/50", empfaenger="P000003"),
                         KSplit("A000014", 1234, wert_text="617/50", empfaenger="P000003")],
          memo="Gekürzter Bruch", wahre_kategorie="A000014")
    s.neu("2023-02-03", [KSplit(giro, -1200, wert_text="-12", empfaenger="P000004"),
                         KSplit("A000014", 1200, wert_text="12", empfaenger="P000004")],
          memo="Ganze Euro ohne Nenner", wahre_kategorie="A000014")
    s.neu("2023-02-04", [KSplit(giro, -123, wert_text="-1230/1000"),
                         KSplit("A000015", 123, wert_text="1230/1000")],
          memo="Nenner 1000", wahre_kategorie="A000015")
    # nur ein Split
    s.neu("2023-03-01", [KSplit(giro, -999, memo="Ohne Kategorie", empfaenger="P000005")],
          memo="Buchung ohne Gegenbuchung")
    # unausgeglichen
    s.neu("2023-03-02", [KSplit(giro, -1000), KSplit("A000015", 900)], memo="Unausgeglichen um 1 Euro")
    # Split mit Betrag 0
    s.neu("2023-03-03", [KSplit(giro, -500), KSplit("A000014", 500), KSplit("A000015", 0, memo="Nullsplit")],
          memo="Mit Nullsplit")
    # geschlossenes Konto: Umbuchung auf 0
    _umbuchung(s, "2023-03-04", alt, giro, 5000, "Auflösung Altkonto")
    # Bargeld
    _einfach(s, "2023-03-05", bar, "A000014", -1500, "P000005", "Barzahlung ☕🙂")
    # Kategorie unter falscher Klasse
    _einfach(s, "2023-03-06", giro, "A000017", -800, "", "Falsch einsortiert")
    # Datum mit Zeitanteil
    _einfach(s, "2023-06-01T00:00:00", giro, "A000016", 4200, "P000003", "Erstattung mit Zeitstempel")
    # Empfänger nur am zweiten Split
    s.neu("2023-06-02", [KSplit(giro, -700, empfaenger=""), KSplit("A000014", 700, empfaenger="P000001")],
          memo="Empfänger am zweiten Split", wahre_kategorie="A000014")
    # Kreditkarte
    _einfach(s, "2023-06-03", kk, "A000014", -2599, "P000002", "Kartenzahlung")
    # zweimal derselbe Kaffee
    for _ in range(2):
        _einfach(s, "2023-06-04", giro, "A000014", -330, "P000002", "Kaffee")
    # Zeilenumbruch im Verwendungszweck
    _einfach(s, "2023-06-05", giro, "A000015", -100, "P000005", "Zeile 1\nZeile 2")
    # Sonstiges Vermögen
    _umbuchung(s, "2023-06-06", giro, sonst_v, 10000, "Wertanlage (fiktiv)")
    b.buchungen = s.buchungen()
    return b


# ============================================================== fremdwaehrung


def fremdwaehrung_buch() -> KBuch:
    b = KBuch()
    b.konten = [
        KKonto("A000001", "Girokonto", 1, "AStd::Asset", iban=fiktive_iban(5001)),
        KKonto("A000002", "US-Konto", 1, "AStd::Asset", waehrung="USD"),
        KKonto("A000003", "Depot", 7, "AStd::Asset"),
        KKonto("A000004", "Aktie Beispiel AG", 15, "A000003"),
        KKonto("A000005", "Sparunterkonto", 2, "A000002", iban=fiktive_iban(5005)),
        KKonto("A000006", "Anfangsbestand", 16, "AStd::Equity"),
        KKonto("A000007", "Lebensmittel", 13, "AStd::Expense"),
        KKonto("A000008", "Gebühren", 13, "AStd::Expense"),
    ]
    b.empfaenger = [("P000001", "Supermarkt Frischekorb"), ("P000002", "Broker (fiktiv)")]
    s = _Sammler()
    s.neu("2024-01-01", [KSplit("A000001", 200000), KSplit("A000006", -200000)], memo="Anfangsbestand")
    _einfach(s, "2024-01-02", "A000001", "A000007", -4500, "P000001", "Einkauf")
    s.neu("2024-01-03", [KSplit("A000002", 50000), KSplit("A000006", -50000)], memo="Anfangsbestand USD")
    _umbuchung(s, "2024-01-04", "A000001", "A000002", 10000, "Überweisung auf US-Konto")
    s.neu("2024-01-05", [KSplit("A000001", -3000), KSplit("A000007", 3000)], memo="Einkauf in USD",
          waehrung="USD", wahre_kategorie="A000007")
    _umbuchung(s, "2024-01-06", "A000001", "A000003", 25000, "Kauf Wertpapier", empf="P000002")
    _einfach(s, "2024-01-07", "A000001", "A000008", -995, "P000002", "Depotgebühr")
    _umbuchung(s, "2024-01-08", "A000001", "A000005", 7000, "Sparrate")
    b.buchungen = s.buchungen()
    return b


# ================================================================== dubletten


def dubletten_buch() -> KBuch:
    b = KBuch()
    b.konten = [
        KKonto("A000001", "Girokonto", 1, "AStd::Asset", iban=fiktive_iban(4001)),
        KKonto("A000002", "Lebensmittel", 13, "AStd::Expense"),
        KKonto("A000003", "Café", 13, "AStd::Expense"),
        KKonto("A000004", "Tanken", 13, "AStd::Expense"),
        KKonto("A000005", "Strom", 13, "AStd::Expense"),
        KKonto("A000006", "Streaming", 13, "AStd::Expense"),
    ]
    b.empfaenger = [
        ("P000001", "Supermarkt Frischekorb"),
        ("P000002", "Café Bohne"),
        ("P000003", "Tankstelle Blitz"),
        ("P000004", "Stadtwerke Musterstadt GmbH"),
        ("P000005", "BAECKEREI MUELLER"),
        ("P000006", "Streamio"),
    ]
    G = "A000001"
    roh = [  # (datum, kategorie, betrag, empfänger)
        ("2024-03-01", "A000002", -2350, "P000001"),
        ("2024-03-05", "A000003", -320, "P000002"),
        ("2024-03-10", "A000003", -450, "P000002"),
        ("2024-03-10", "A000003", -450, "P000002"),
        ("2024-03-16", "A000004", -6000, "P000003"),
        ("2024-03-20", "A000005", -8900, "P000004"),
        ("2024-03-25", "A000002", -275, "P000005"),
        ("2024-03-28", "A000002", -1000, ""),
        ("2024-03-29", "A000002", -5000, "P000001"),
        ("2024-03-06", "A000006", -1999, "P000006"),
    ]
    b.buchungen = []
    for n, (d, kat, betrag, empf) in enumerate(roh, start=1):
        b.buchungen.append(KBuchung(
            id=_tid(n), datum=d, memo=f"Dublettentest {n}", wahre_kategorie=kat,
            splits=[KSplit(G, betrag, memo=f"Dublettentest {n}", empfaenger=empf),
                    KSplit(kat, -betrag, empfaenger=empf)]))
    return b


DUBLETTEN_VORBESTAND = {
    "konten": [
        {"ref": "K_GIRO", "name": "Girokonto Vorbestand", "art": "girokonto", "iban": fiktive_iban(4001)},
        {"ref": "K_LEBENSMITTEL", "name": "Lebensmittel", "art": "aufwand", "iban": None},
        {"ref": "K_CAFE", "name": "Café", "art": "aufwand", "iban": None},
    ],
    "empfaenger": [
        {"ref": "E_SUPERMARKT", "name": "Supermarkt Frischekorb"},
        {"ref": "E_CAFE", "name": "Café Bohne"},
        {"ref": "E_TANKSTELLE", "name": "Tankstelle Blitz"},
        {"ref": "E_STADTWERKE", "name": "Stadtwerke Musterstadt"},
        {"ref": "E_BAECKEREI", "name": "Bäckerei Müller"},
        {"ref": "E_STREAMIO", "name": "Streamio"},
    ],
    # betrag aus Sicht des Girokontos; Gegensplit auf kategorie
    "buchungen": [
        {"ref": "V1", "datum": "2024-03-01", "betrag": -2350, "empfaenger": "E_SUPERMARKT", "kategorie": "K_LEBENSMITTEL"},
        {"ref": "V2", "datum": "2024-03-05", "betrag": -320, "empfaenger": "E_CAFE", "kategorie": "K_CAFE"},
        {"ref": "V3", "datum": "2024-03-05", "betrag": -320, "empfaenger": "E_CAFE", "kategorie": "K_CAFE"},
        {"ref": "V4", "datum": "2024-03-10", "betrag": -450, "empfaenger": "E_CAFE", "kategorie": "K_CAFE"},
        {"ref": "V5", "datum": "2024-03-15", "betrag": -6000, "empfaenger": "E_TANKSTELLE", "kategorie": "K_LEBENSMITTEL"},
        {"ref": "V6", "datum": "2024-03-20", "betrag": -8900, "empfaenger": "E_STADTWERKE", "kategorie": "K_LEBENSMITTEL"},
        {"ref": "V7", "datum": "2024-03-25", "betrag": -275, "empfaenger": "E_BAECKEREI", "kategorie": "K_LEBENSMITTEL"},
        {"ref": "V8", "datum": "2024-03-28", "betrag": -1000, "empfaenger": None, "kategorie": "K_LEBENSMITTEL"},
        {"ref": "V9", "datum": "2024-03-02", "betrag": -1999, "empfaenger": "E_STREAMIO", "kategorie": "K_LEBENSMITTEL"},
        {"ref": "V10", "datum": "2024-03-01", "betrag": -2351, "empfaenger": "E_SUPERMARKT", "kategorie": "K_LEBENSMITTEL"},
    ],
}

# Von Hand nach datenmodell.md 10.4 hergeleitet (siehe Kommentare).
DUBLETTEN_ERWARTUNG = {
    "zusammengefuehrt": {
        "T000000000000000001": "V1",  # gleiches Datum, Betrag, Empfänger
        "T000000000000000007": "V7",  # BAECKEREI MUELLER ~ Bäckerei Müller (ekey gleich)
        "T000000000000000008": "V8",  # beide ohne Empfänger
    },
    "verdachte": [
        {"buchung": "T000000000000000002", "kandidaten": ["V2", "V3"], "grund": "mehrdeutig"},
        {"buchung": "T000000000000000003", "kandidaten": ["V4"], "grund": "mehrdeutig"},
        {"buchung": "T000000000000000004", "kandidaten": ["V4"], "grund": "mehrdeutig"},
        {"buchung": "T000000000000000005", "kandidaten": ["V5"], "grund": "aehnlich"},
        {"buchung": "T000000000000000006", "kandidaten": ["V6"], "grund": "aehnlich"},
    ],
    "neu_ohne_verdacht": ["T000000000000000009", "T000000000000000010"],
    "ergebnis": {
        "erfolgreich": True,
        "format": "kmy-gzip",
        "konten_neu": 0,
        "konten_vorhanden": 1,
        "kategorien_neu": 3,
        "kategorien_vorhanden": 2,
        "empfaenger_neu": 2,
        "empfaenger_vorhanden": 4,
        "tags_neu": 0,
        "tags_vorhanden": 0,
        "buchungen_neu": 7,
        "buchungen_vorhanden": 0,
        "buchungen_zusammengefuehrt": 3,
        "buchungen_zur_pruefung": 5,
        "buchungen_uebersprungen": 0,
        "splits_neu": 14,
    },
    "konten_zuordnung": {"kmy:A000001": "K_GIRO", "kmy:A000002": "K_LEBENSMITTEL", "kmy:A000003": "K_CAFE"},
}


# ===================================================== defekte/ungültige Dateien


def inhalt_ungueltig_buch() -> KBuch:
    """Gültiges XML, aber letzte Transaktion verweist auf unbekanntes Konto."""
    b = minimal_buch()
    b.buchungen.append(KBuchung(id=_tid(3), datum="2024-02-03", memo="Verweis ins Leere", splits=[
        KSplit("A000001", -100), KSplit("A999999", 100)]))
    return b


def betrag_ungueltig_buch() -> KBuch:
    b = minimal_buch()
    b.buchungen.append(KBuchung(id=_tid(3), datum="2024-02-03", memo="Drittel", splits=[
        KSplit("A000001", None, wert_text="-1/3"), KSplit("A000002", None, wert_text="1/3")]))
    return b


def datum_ungueltig_buch() -> KBuch:
    b = minimal_buch()
    b.buchungen.append(KBuchung(id=_tid(3), datum="2023-02-30", memo="Kein Datum", splits=[
        KSplit("A000001", -100), KSplit("A000002", 100)]))
    return b


def pflichtfeld_fehlt_buch() -> KBuch:
    """SPLIT ohne value-Attribut (wird beim Schreiben entfernt)."""
    b = minimal_buch()
    b.buchungen.append(KBuchung(id=_tid(3), datum="2024-02-03", memo="Ohne Wert", splits=[
        KSplit("A000001", -100), KSplit("A000002", None, wert_text="__ENTFERNEN__")]))
    return b
