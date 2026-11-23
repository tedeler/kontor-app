"""Lerndaten für Meilenstein 4: Haushaltsbuch mit bekannter Kategorie je Buchung.

Erzeugt ein KMyMoney-Buch über drei Jahre (2022–2024) mit einem Girokonto
und einer Kreditkarte, dessen einfache Buchungen (Bestandskonto ↔ eine
Kategorie) eine bekannte, richtige Kategorie haben (``wahre_kategorie``).
Damit das Lernmodell (``spec/api/lernmodell.md``) eine echte Aufgabe hat,
sind eingebaut:

- Empfänger mit genau einer Kategorie (Gehalt, Miete, Strom, Abos …),
- Empfänger mit mehreren Kategorien, unterscheidbar nur am
  Verwendungszweck (Kaufhaus, Versandhandel, Supermarkt),
- Empfänger mit mehreren Kategorien, unterscheidbar nur am Betrag
  (Tankstelle: Tanken gegen Shop-Einkauf),
- neue Empfänger erst im letzten Jahr (ohne Vorgeschichte),
- Erstattungen (positive Beträge) desselben Empfängers,
- etwa 4 % falsch eingeordnete Buchungen (Bedienfehler: die *erfasste*
  Kategorie weicht von der richtigen ab; gespeichert wird die erfasste,
  die richtige steht in der Erwartung),
- Umbuchungen und eine Sammelbuchung (keine Trainingsbeispiele).

Alles synthetisch, Zufall nur über ``random.Random(startwert + 40)``.
"""

from __future__ import annotations

import datetime as dt
import random

from .iban import fiktive_iban
from .kmy import KBuch, KBuchung, KKonto, KSplit

GIRO_IBAN = fiktive_iban(4001)
KREDIT_IBAN = fiktive_iban(4002)
TEIL_TRAINING = 0.8  # T 21: ältere 80 % Training, neueste 20 % Prüfung

KONTEN = [
    ("A000001", "Girokonto", 1, "AStd::Asset"),
    ("A000002", "Kreditkarte", 4, "AStd::Liability"),
    ("A000003", "Anfangsbestand", 16, "AStd::Equity"),
    ("A000010", "Gehalt", 12, "AStd::Income"),
    ("A000011", "Erstattungen", 12, "AStd::Income"),
    ("A000020", "Wohnen", 13, "AStd::Expense"),
    ("A000021", "Miete", 13, "A000020"),
    ("A000022", "Strom", 13, "A000020"),
    ("A000023", "Internet", 13, "A000020"),
    ("A000030", "Lebensmittel", 13, "AStd::Expense"),
    ("A000031", "Drogerie", 13, "AStd::Expense"),
    ("A000032", "Haushalt", 13, "AStd::Expense"),
    ("A000033", "Kleidung", 13, "AStd::Expense"),
    ("A000034", "Elektronik", 13, "AStd::Expense"),
    ("A000035", "Bücher", 13, "AStd::Expense"),
    ("A000036", "Tanken", 13, "AStd::Expense"),
    ("A000037", "Café", 13, "AStd::Expense"),
    ("A000038", "Restaurant", 13, "AStd::Expense"),
    ("A000039", "Sport", 13, "AStd::Expense"),
    ("A000040", "Spenden", 13, "AStd::Expense"),
    ("A000041", "Abos", 13, "AStd::Expense"),
    ("A000042", "Gesundheit", 13, "AStd::Expense"),
    ("A000043", "Versicherungen", 13, "AStd::Expense"),
    ("A000044", "Geschenke", 13, "AStd::Expense"),
]
KAT = {name: kid for kid, name, typ, _ in KONTEN if typ in (12, 13)}
GIRO, KREDIT, EK = "A000001", "A000002", "A000003"

EMPFAENGER = [
    ("P000001", "Arbeitgeber Muster GmbH"),
    ("P000002", "Wohnbau Beispiel eG"),
    ("P000003", "Stadtwerke Musterstadt"),
    ("P000004", "Netzfunk Internet (fiktiv)"),
    ("P000005", "Supermarkt Frischekorb"),
    ("P000006", "Drogeriemarkt Glanz"),
    ("P000007", "Kaufhaus Übermaß"),
    ("P000008", "Paketwelt Versand (fiktiv)"),
    ("P000009", "Tankstelle Blitz"),
    ("P000010", "Café Bohne"),
    ("P000011", "Trattoria Fittizia"),
    ("P000012", "Turnverein Musterstadt e.V."),
    ("P000013", "Hilfswerk Beispiel e.V."),
    ("P000014", "Streamio Media (fiktiv)"),
    ("P000015", "Apotheke am Markt"),
    ("P000016", "Krankenkasse Muster"),
    ("P000017", "Bäckerei Sonnenschein"),
    ("P000018", "Bioladen Grünkern"),        # neu ab Mitte 2024
    ("P000019", "Elektro Funke (fiktiv)"),   # neu ab Mitte 2024
    ("P000020", "Fiktiva Versicherung AG"),
]
E = {name: pid for pid, name in EMPFAENGER}


def lern_buch(startwert: int) -> tuple[KBuch, list[dict]]:
    """Liefert das Buch und je einfacher Buchung die bekannte Wahrheit.

    Wahrheit je Buchung: ``{"id", "datum", "empfaenger", "verwendungszweck",
    "betrag" (Regelbetrag), "kategorie" (erfasst), "wahr" (richtig),
    "fehlerhaft" (bool)}``.
    """
    rng = random.Random(startwert + 40)
    b = KBuch()
    ibans = {GIRO: GIRO_IBAN, KREDIT: KREDIT_IBAN}
    b.konten = [KKonto(kid, name, typ, eltern, iban=ibans.get(kid)) for kid, name, typ, eltern in KONTEN]
    b.empfaenger = list(EMPFAENGER)
    roh: list[tuple] = []  # (datum, nr, konto, betrag, empf, text, wahr)

    def neu(datum: dt.date, konto: str, betrag: int, empf: str, text: str, wahr: str) -> None:
        roh.append((datum, len(roh), konto, betrag, empf, text, wahr))

    def tag(j: int, m: int, t: int) -> dt.date:
        d = dt.date(j, m, min(t, 28))
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        return d

    kaufhaus = [("Kleidung", ["Jacke", "Hose", "Schuhe", "Pullover", "Kleidung"]),
                ("Elektronik", ["Kopfhörer", "Ladekabel", "Elektro", "Lautsprecher"]),
                ("Haushalt", ["Töpfe", "Handtücher", "Haushaltswaren", "Bettwäsche"]),
                ("Geschenke", ["Geschenk", "Geschenkgutschein"])]
    versand = [("Bücher", ["Buch", "Taschenbuch", "Roman"]), ("Elektronik", ["Elektronik", "Akku", "Ladekabel"]),
               ("Kleidung", ["Kleidung", "Schuhe"]), ("Haushalt", ["Haushaltswaren", "Lampe"])]

    for jahr in (2022, 2023, 2024):
        for monat in range(1, 13):
            neu(tag(jahr, monat, 28), GIRO, 345000 if jahr >= 2023 else 330000, "Arbeitgeber Muster GmbH",
                f"LOHN/GEHALT {monat:02d}/{jahr}", "Gehalt")
            neu(tag(jahr, monat, 1), GIRO, -98000, "Wohnbau Beispiel eG", f"Miete {monat:02d}/{jahr} Musterweg 1",
                "Miete")
            neu(tag(jahr, monat, 5), GIRO, -8900 if jahr < 2024 else -9400, "Stadtwerke Musterstadt",
                f"Abschlag Strom Kundennummer 4711 {monat:02d}/{jahr}", "Strom")
            neu(tag(jahr, monat, 3), GIRO, -3999, "Netzfunk Internet (fiktiv)", f"Rechnung Internet {monat:02d}/{jahr}",
                "Internet")
            neu(dt.date(jahr, monat, 12), KREDIT, -1299, "Streamio Media (fiktiv)", "Abo Streamio Premium", "Abos")
            neu(tag(jahr, monat, 2), GIRO, -3500, "Turnverein Musterstadt e.V.", f"Mitgliedsbeitrag {monat:02d}/{jahr}",
                "Sport")
            if monat in (1, 7):
                neu(tag(jahr, monat, 10), GIRO, -rng.randint(18000, 26000), "Fiktiva Versicherung AG",
                    f"Beitrag Hausrat und Haftpflicht {jahr}", "Versicherungen")
            if monat == 12:
                neu(dt.date(jahr, 12, 15), GIRO, -rng.choice([2500, 5000, 10000]), "Hilfswerk Beispiel e.V.",
                    "Spende Winterhilfe", "Spenden")
            # Supermarkt: meist Lebensmittel, am Verwendungszweck erkennbar auch Drogerie/Haushalt
            for _ in range(rng.randint(6, 9)):
                r = rng.random()
                if r < 0.84:
                    text, kat = f"Einkauf Filiale {rng.randint(1, 40):03d}", "Lebensmittel"
                elif r < 0.92:
                    text, kat = f"Drogerieartikel Filiale {rng.randint(1, 40):03d}", "Drogerie"
                else:
                    text, kat = f"Haushaltswaren Filiale {rng.randint(1, 40):03d}", "Haushalt"
                neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, -rng.randint(800, 14000),
                    "Supermarkt Frischekorb", text, kat)
            for _ in range(rng.randint(3, 6)):
                neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, -rng.randint(180, 990), "Bäckerei Sonnenschein",
                    f"Kartenzahlung {rng.randint(1, 999):03d}", "Lebensmittel")
            for _ in range(rng.randint(1, 3)):
                neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, -rng.randint(300, 2500), "Drogeriemarkt Glanz",
                    f"Einkauf Markt {rng.randint(1, 20):02d}", "Drogerie")
            # Tankstelle: Tanken (großer Betrag) gegen Shop (kleiner Betrag), gleicher Verwendungszweck
            for _ in range(rng.randint(2, 4)):
                if rng.random() < 0.75:
                    betrag, kat = -rng.randint(4000, 9500), "Tanken"
                else:
                    betrag, kat = -rng.randint(150, 950), "Lebensmittel"
                neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, betrag, "Tankstelle Blitz",
                    f"Kartenzahlung Station {rng.randint(1, 9)}", kat)
            for _ in range(rng.randint(2, 5)):
                neu(dt.date(jahr, monat, rng.randint(1, 28)), KREDIT, -rng.randint(280, 1400), "Café Bohne",
                    "Kartenzahlung Café", "Café")
            for _ in range(rng.randint(0, 2)):
                neu(dt.date(jahr, monat, rng.randint(1, 28)), KREDIT, -rng.randint(2500, 9000), "Trattoria Fittizia",
                    "Kartenzahlung Restaurant", "Restaurant")
            # Kaufhaus und Versand: Kategorie nur am Verwendungszweck erkennbar
            for _ in range(rng.randint(1, 3)):
                kat, woerter = rng.choice(kaufhaus)
                neu(dt.date(jahr, monat, rng.randint(1, 28)), KREDIT, -rng.randint(1500, 15000), "Kaufhaus Übermaß",
                    f"{rng.choice(woerter)} Bon {rng.randint(1000, 9999)}", kat)
            for _ in range(rng.randint(1, 3)):
                kat, woerter = rng.choice(versand)
                neu(dt.date(jahr, monat, rng.randint(1, 28)), KREDIT, -rng.randint(900, 12000),
                    "Paketwelt Versand (fiktiv)",
                    f"Bestellung {rng.randint(100, 999)}-{rng.randint(1000000, 9999999)} {rng.choice(woerter)}", kat)
            if rng.random() < 0.5:
                neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, -rng.randint(500, 4500), "Apotheke am Markt",
                    "Kartenzahlung Apotheke", "Gesundheit")
            if rng.random() < 0.25:
                neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, rng.randint(1500, 12000), "Krankenkasse Muster",
                    f"Erstattung Rechnung {rng.randint(10000, 99999)}", "Erstattungen")
            if rng.random() < 0.15:
                neu(dt.date(jahr, monat, rng.randint(1, 28)), KREDIT, rng.randint(1500, 9000), "Kaufhaus Übermaß",
                    f"Gutschrift Rückgabe Bon {rng.randint(1000, 9999)}", "Erstattungen")
            # neue Empfänger im letzten Halbjahr (ohne Vorgeschichte)
            if (jahr, monat) >= (2024, 7):
                for _ in range(rng.randint(1, 3)):
                    neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, -rng.randint(900, 6000), "Bioladen Grünkern",
                        f"Einkauf Laden {rng.randint(1, 9)}", "Lebensmittel")
                if rng.random() < 0.5:
                    neu(dt.date(jahr, monat, rng.randint(1, 28)), GIRO, -rng.randint(1500, 20000),
                        "Elektro Funke (fiktiv)", f"Ladekabel und Zubehör Bon {rng.randint(100, 999)}", "Elektronik")

    roh.sort(key=lambda r: (r[0], r[1]))
    kategorien = sorted(KAT)
    wahrheit: list[dict] = []
    buchungen: list[KBuchung] = []
    n = 0

    def tid() -> str:
        nonlocal n
        n += 1
        return f"T{n:018d}"

    for konto, betrag in ((GIRO, 250000), (KREDIT, 0)):
        buchungen.append(KBuchung(id=tid(), datum="2022-01-01", memo="Anfangsbestand",
                                  splits=[KSplit(konto, betrag, memo="Anfangsbestand"), KSplit(EK, -betrag)]))
    for datum, _, konto, betrag, empf, text, wahr in roh:
        erfasst = wahr
        if rng.random() < 0.04:
            erfasst = rng.choice([k for k in kategorien if k != wahr])
        i = tid()
        pid = E[empf]
        buchungen.append(KBuchung(id=i, datum=datum.isoformat(), memo=text, wahre_kategorie=KAT[wahr], splits=[
            KSplit(konto, betrag, memo="", empfaenger=pid), KSplit(KAT[erfasst], -betrag, memo="", empfaenger=pid)]))
        wahrheit.append({"id": i, "datum": datum.isoformat(), "empfaenger": empf, "verwendungszweck": text,
                         "betrag": betrag, "konto": konto, "kategorie": erfasst, "wahr": wahr,
                         "fehlerhaft": erfasst != wahr})
    # Monatliche Kreditkartenabrechnung als Umbuchung und eine Sammelbuchung (keine Trainingsbeispiele)
    for jahr in (2022, 2023, 2024):
        for monat in range(1, 13):
            buchungen.append(KBuchung(id=tid(), datum=f"{jahr}-{monat:02d}-25", memo="Kreditkartenabrechnung",
                                      umbuchung=True, splits=[KSplit(GIRO, -10000), KSplit(KREDIT, 10000)]))
    buchungen.append(KBuchung(id=tid(), datum="2023-05-02", memo="Sammelrechnung", splits=[
        KSplit(GIRO, -5000, empfaenger=E["Kaufhaus Übermaß"]), KSplit(KAT["Kleidung"], 3000),
        KSplit(KAT["Haushalt"], 2000)]))
    b.buchungen = buchungen
    # Trennung nach Datum (bei Gleichstand nach ID): ältere 80 % Training
    grenze = int(len(wahrheit) * TEIL_TRAINING)
    for k, w in enumerate(wahrheit):
        w["teil"] = "training" if k < grenze else "pruefung"
    return b, wahrheit
