"""Mock-Datendatei (Format ``kontor-mock-daten`` Version 1, plugins.md 4).

Liefert synthetische Bankumsätze für ein Girokonto und ein Sparkonto im Jahr
2024 sowie Mails für zwei Postfächer unter example.invalid. Dazu eine
Erwartungsdatei mit der bekannten Wahrheit (Kategorie je Umsatz,
Umbuchungspaare, Vormerkungen, Storno).
"""

from __future__ import annotations

import datetime as dt
import random

from .iban import fiktive_iban

GIRO = fiktive_iban(7001)
SPAR = fiktive_iban(7002)
FREMD = fiktive_iban(7999)  # fremde Gegenpartei (nicht eigenes Konto)
POSTFACH_1 = "haushalt.eins@example.invalid"
POSTFACH_2 = "haushalt.zwei@example.invalid"


def mock_daten(startwert: int) -> tuple[dict, dict]:
    rng = random.Random(startwert + 1)
    umsaetze: list[dict] = []
    wahrheit: dict[str, str | None] = {}
    paare: list[list[str]] = []
    zaehler = [0]

    def neu(iban: str, tag: dt.date, betrag: int, name: str | None, gegen_iban: str | None,
            zweck: str, kategorie: str | None, vormerkung: bool = False, storno: bool = False) -> str:
        zaehler[0] += 1
        uid = f"U-{zaehler[0]:06d}"
        umsaetze.append({
            "umsatz_id": uid, "iban": iban, "buchungstag": tag.isoformat(),
            "valuta": None if vormerkung else tag.isoformat(), "betrag": betrag, "waehrung": "EUR",
            "gegenpartei_name": name, "gegenpartei_iban": gegen_iban, "verwendungszweck": zweck,
            "vormerkung": vormerkung, "storno": storno,
        })
        wahrheit[uid] = kategorie
        return uid

    for monat in range(1, 13):
        def tag(t: int) -> dt.date:
            return dt.date(2024, monat, t)
        neu(GIRO, tag(28), 335000, "Arbeitgeber Muster GmbH", FREMD, f"LOHN/GEHALT {monat:02d}/2024", "Gehalt")
        neu(GIRO, tag(1), -98000, "Wohnbau Beispiel eG", FREMD, f"Miete {monat:02d}/2024", "Miete")
        neu(GIRO, tag(5), -9200, "Stadtwerke Musterstadt", FREMD, "Abschlag Strom", "Strom")
        a = neu(GIRO, tag(25), -30000, "Erika Mustermann", SPAR, "Sparrate", None)
        b = neu(SPAR, tag(25), 30000, "Erika Mustermann", GIRO, "Sparrate", None)
        paare.append([a, b])
        for _ in range(rng.randint(4, 7)):
            neu(GIRO, tag(rng.randint(1, 27)), -rng.randint(800, 9000), "Supermarkt Frischekorb", None,
                f"Kartenzahlung {rng.randint(1, 999):03d}", "Lebensmittel")
        for _ in range(rng.randint(1, 3)):
            neu(GIRO, tag(rng.randint(1, 27)), -rng.randint(300, 1100), "Café Bohne", None,
                "Kartenzahlung Café", "Café & Restaurant")
    # Storno
    neu(GIRO, dt.date(2024, 5, 14), -12999, "Kaufhaus Beispiel", None, "Bestellung 4711", "Sonstiges")
    neu(GIRO, dt.date(2024, 5, 15), 12999, "Kaufhaus Beispiel", None, "STORNO Bestellung 4711", "Sonstiges",
        storno=True)
    # gleicher Betrag an fremde IBAN (keine Umbuchung)
    neu(GIRO, dt.date(2024, 6, 25), -30000, "Fremde Person (fiktiv)", FREMD, "Darlehen privat", "Sonstiges")
    # Vormerkungen am Jahresende
    neu(GIRO, dt.date(2024, 12, 30), -4599, "Tankstelle Blitz", None, "Vorgemerkt: Tanken", "Tanken",
        vormerkung=True)
    neu(GIRO, dt.date(2024, 12, 31), -1250, "Café Bohne", None, "Vorgemerkt: Café „Ölfass“ & Co.",
        "Café & Restaurant", vormerkung=True)
    umsaetze.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))

    nachrichten: list[dict] = []
    for n in range(1, 41):
        postfach = POSTFACH_1 if n % 2 else POSTFACH_2
        tag = dt.date(2024, 1, 1) + dt.timedelta(days=rng.randint(0, 365))
        stunde, minute = rng.randint(6, 22), rng.randint(0, 59)
        betrag = rng.randint(500, 20000)
        nachrichten.append({
            "nachricht_id": f"M-{n:06d}", "postfach": postfach,
            "empfangen": f"{tag.isoformat()}T{stunde:02d}:{minute:02d}:00Z",
            "absender": "bestellung@shop.example.invalid" if n % 3 else "zahlung@pay.example.invalid",
            "betreff": f"Ihre Bestellung Nr. {1000 + n} – Bestätigung",
            "text": (f"Hallo Erika,\nvielen Dank für Ihre Bestellung Nr. {1000 + n}.\n"
                     f"Gesamtbetrag: {betrag // 100},{betrag % 100:02d} EUR\nIhr fiktiver Shop (Testdaten)"),
        })
    nachrichten.sort(key=lambda m: (m["empfangen"], m["nachricht_id"]))

    daten = {
        "format": "kontor-mock-daten",
        "version": 1,
        "bank": {
            "konten": [
                {"iban": GIRO, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto",
                 "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"},
                {"iban": SPAR, "bic": None, "name": "Tagesgeld", "art": "sparkonto",
                 "inhaber": "Erika Mustermann (fiktiv)", "waehrung": "EUR"},
            ],
            "umsaetze": umsaetze,
        },
        "mail": {"postfaecher": [POSTFACH_1, POSTFACH_2], "nachrichten": nachrichten},
    }
    erwartung = {
        "fixture": "mock/mock_daten.json",
        "wahre_kategorie": wahrheit,
        "umbuchungspaare": paare,
        "vormerkungen": [u["umsatz_id"] for u in umsaetze if u["vormerkung"]],
        "stornos": [u["umsatz_id"] for u in umsaetze if u["storno"]],
        "anzahl_umsaetze": {GIRO: sum(u["iban"] == GIRO for u in umsaetze),
                            SPAR: sum(u["iban"] == SPAR for u in umsaetze)},
        "saldo_veraenderung": {GIRO: sum(u["betrag"] for u in umsaetze if u["iban"] == GIRO),
                               SPAR: sum(u["betrag"] for u in umsaetze if u["iban"] == SPAR)},
        "anzahl_nachrichten": {POSTFACH_1: sum(m["postfach"] == POSTFACH_1 for m in nachrichten),
                               POSTFACH_2: sum(m["postfach"] == POSTFACH_2 for m in nachrichten)},
    }
    return daten, erwartung
