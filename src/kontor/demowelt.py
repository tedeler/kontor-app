"""Demodaten, Teil 1: die erfundene Welt eines Haushalts (Feature ``demodaten``).

Erzeugt reproduzierbar, was eine Bank und zwei Postfächer über einen erfundenen Haushalt wüssten: Umsätze eines
Girokontos und eines Sparbuchs, Bestell-, Zahlungs- und Rechnungsmails. Daraus entsteht die Mock-Datendatei
(``plugins.md`` 7) für die Mock-Plugins der Testinstanz; ``demodaten.aufbauen`` baut damit über die Schnittstellen
der Anwendung den Buchbestand.

Alles ist erfunden: Namen, Beträge, Bestellnummern; IBANs sind Test-IBANs mit Bankleitzahl 00000000, Mailadressen
liegen unter ``example.invalid``. Hier wird nichts gelesen – weder eine Datenbank noch eine Datei.

Jeder Umsatz trägt seine „Wahrheit“ (Kategorie als Pfad, Tags): So ordnet der Aufbau die Buchungen zu, wie es ein
Anwender über die Zeit getan hätte. Jeder Monat hat seinen eigenen Zufallsstrom; ein anderer Zeitraum ändert die
Umsätze der gemeinsamen Monate deshalb nicht.
"""

from __future__ import annotations

import calendar
import datetime as dt
import random
from dataclasses import dataclass, field

from .plugins.mock_daten import test_iban

UTC = dt.timezone.utc
VORRAT_TAGE = 60          # so weit über „heute“ hinaus liegen schon Umsätze und Mails für spätere Abrufe bereit

GIRO = test_iban(2026001)
SPARBUCH = test_iban(2026002)
INHABER = "Erika und Max Mustermann (Demodaten)"
POSTFAECHER = ("erika.mustermann@example.invalid", "max.mustermann@example.invalid")
ANFANG_GIRO = 284_317
ANFANG_SPARBUCH = 1_265_000

# Kategorien als Pfad „Ober:Unter“; Reihenfolge = Reihenfolge des Anlegens
AUFWAND = ("Wohnen", "Wohnen:Nebenkosten", "Wohnen:Energie", "Lebensmittel", "Mobilität", "Mobilität:Tanken",
           "Mobilität:Bahn & ÖPNV", "Freizeit", "Freizeit:Restaurant", "Einkäufe", "Versicherungen & Gesundheit",
           "Zinsen")
ERTRAG = ("Einkommen", "Einkommen:Gehalt")

# Kredite: Die Raten stehen als gewöhnliche Abbuchungen im Girokonto; die Aufteilung in Zins und Tilgung macht Kontor.
WOHNUNG = {"name": "Wohnungsdarlehen", "bank": "Baufinanz Musterbank AG", "zweck": "DARLEHEN 4711-0815 RATE",
           "restschuld": 18_640_000, "sollzins": 34_500, "rate": 86_500, "tag": 28}
AUTO = {"name": "Autokredit", "bank": "Autobank Beispiel GmbH", "zweck": "KREDITVERTRAG 77123 RATE",
        "restschuld": 1_480_000, "sollzins": 49_000, "rate": 28_900, "tag": 15}
SONDERTILGUNG = 500_000
STADTWERKE = "Stadtwerke Musterstadt"
ABSCHLAG_ALT, ABSCHLAG_NEU = 14_500, 15_800     # der neue Abschlag passt nicht mehr zur Split-Vorlage
ABSCHLAG_TEILE = (("Wohnen:Energie", 11_000, "Strom und Gas"), ("Wohnen:Nebenkosten", 3_500, "Wasser"))

MAERKTE = (("Supermarkt Frischekorb", "FRISCHEKORB MUSTERSTADT", 1800, 9500, 8),
           ("Discounter Preisfuchs", "PREISFUCHS FIL. 204", 900, 5200, 6),
           ("Biomarkt Grünkern", "BIOMARKT GRUENKERN", 1200, 6400, 3),
           ("Bäckerei Kornblume", "BAECKEREI KORNBLUME", 280, 1450, 5))
FRISCHEKORB_ALIAS = "FRISCHEKORB SAGT DANKE"
LOKALE = ("Trattoria Bella Vista", "Sushi Hanami", "Burgerwerk Musterstadt", "Café Zeitlos",
          "Lieferdienst Schnellteller")
FREIZEIT = (("Lichtspielhaus Musterstadt", 1800, 3600), ("Stadtbad Wellenreich", 900, 2200),
            ("Buchhandlung Seitenweise", 1200, 4800), ("Kletterhalle Griffbereit", 1400, 3200))
LAEDEN = (("Drogeriemarkt Seifenblase", "Einkäufe", 600, 4200, 30), ("Baumarkt Hammerwerk", "Einkäufe", 1500, 14000, 7),
          ("Modehaus Fadenlauf", "Einkäufe", 2500, 16000, 7), ("Apotheke am Rathaus", "Versicherungen & Gesundheit", 500, 3800, 10))
ARTIKEL = ("Ladekabel USB-C", "Kinderbuch Sternenreise", "Brotdose Edelstahl", "Druckerpapier 500 Blatt",
           "Fahrradlicht Set", "Kaffeefilter 200 Stück", "Bluetooth-Lautsprecher", "Gartenhandschuhe",
           "Puzzle 1000 Teile", "Trinkflasche 0,75 l", "LED-Leuchtmittel 4er", "Schreibtischlampe",
           "Wanderkarte Mittelgebirge", "Staubsaugerbeutel 10er", "Regenjacke Kinder", "Bettwäsche Baumwolle")
PAYPAL = (("Buchhandlung Seitenweise", "Freizeit"), ("Spielwaren Kunterbunt", "Einkäufe"),
          ("Konzertkasse Klangraum", "Freizeit"), ("Fahrradladen Kettenblatt", "Mobilität"),
          ("Tee-Kontor Blattwerk", "Lebensmittel"))
# Urlaubsziele wechseln von Jahr zu Jahr (sonst sähen sie wie jährliche Verträge aus): (Monat, Jahr gerade?)
URLAUB = {(7, True): ("Ferienhaus Nordseeblick", 89_000, ("Fährlinie Inselhopper", "Fischbude Kutterglück",
                                                         "Strandkorbverleih Sandburg", "Inselbäckerei Dünenkorn")),
          (7, False): ("Campingplatz Seeufer", 52_000, ("Bootsverleih Wellengang", "Seeterrasse Abendrot",
                                                        "Hofladen Wiesengrund", "Minigolf Seepark")),
          (2, True): ("Berghütte Alpenrose", 64_000, ("Skiverleih Pistenflitzer", "Bergbahn Gipfelblick",
                                                      "Gasthof Zur Gams", "Sennerei Almglück")),
          (2, False): ("Stadthotel Altmarkt", 41_000, ("Museum der Stadtgeschichte", "Brauhaus Am Dom",
                                                       "Stadtrundfahrt Altstadt", "Konditorei Zuckerwerk"))}
# Neue Empfänger ohne Vorgeschichte rund um „heute“: (Tage ab heute, Name, Betrag von, bis, Kategorie)
NEUE = ((-17, "Eisdiele Venezia", 600, 1900, "Freizeit:Restaurant"), (-13, "Gartencenter Blütenmeer", 1800, 7400, "Einkäufe"),
        (-9, "Schuhhaus Sohlenreich", 4900, 12900, "Einkäufe"), (-6, "Tierarztpraxis Pfotenglück", 3800, 9800,
                                                                 "Versicherungen & Gesundheit"),
        (-2, "Weinhandlung Rebenhang", 1500, 6800, "Lebensmittel"), (-1, "Eisdiele Venezia", 600, 1900, "Freizeit:Restaurant"),
        (0, "Parkhaus Am Markt", 300, 1200, "Mobilität"), (3, "Gartencenter Blütenmeer", 1800, 7400, "Einkäufe"),
        (9, "Fotostudio Lichtblick", 2900, 8900, "Freizeit"), (16, "Weinhandlung Rebenhang", 1500, 6800, "Lebensmittel"))


@dataclass(frozen=True)
class Umsatz:
    """Ein Bankumsatz samt Wahrheit: ``kategorie`` als Pfad, ``None`` bei Umbuchungen und Kreditraten."""

    konto: str                 # "giro" | "sparbuch"
    datum: dt.date
    betrag: int
    name: str
    zweck: str
    kategorie: str | None = None
    tags: tuple[str, ...] = ()
    gegen_iban: str | None = None
    merkmal: str | None = None   # Besonderheit für den Aufbau: rate_wohnung, rate_auto, sondertilgung, beleg, bar …
    nr: str = ""

    @property
    def iban(self) -> str:
        return GIRO if self.konto == "giro" else SPARBUCH


@dataclass(frozen=True)
class Mail:
    postfach: int
    empfangen: dt.datetime
    absender: str
    betreff: str
    text: str
    nr: str = ""
    haendler: str | None = None   # PayPal: Händler der Zahlung (zum Zuordnen von Hand im Aufbau)
    betrag: int | None = None


@dataclass
class Welt:
    heute: dt.date
    start: dt.date
    umsaetze: list[Umsatz] = field(default_factory=list)
    mails: list[Mail] = field(default_factory=list)

    def mock_daten(self) -> dict:
        """Die Welt im Format ``kontor-mock-daten`` Version 1 (plugins.md 7)."""
        def konto(iban, name, art):
            return {"iban": iban, "bic": "TESTDEFFXXX", "name": name, "art": art, "inhaber": INHABER,
                    "waehrung": "EUR"}
        return {
            "format": "kontor-mock-daten", "version": 1,
            "bank": {
                "konten": [konto(GIRO, "Girokonto", "girokonto"), konto(SPARBUCH, "Sparbuch", "sparkonto")],
                "anfangssalden": {GIRO: ANFANG_GIRO, SPARBUCH: ANFANG_SPARBUCH},
                "umsaetze": [{"umsatz_id": u.nr, "iban": u.iban, "buchungstag": u.datum.isoformat(),
                              "valuta": u.datum.isoformat(), "betrag": u.betrag, "waehrung": "EUR",
                              "gegenpartei_name": u.name, "gegenpartei_iban": u.gegen_iban,
                              "verwendungszweck": u.zweck, "vormerkung": False, "storno": False}
                             for u in self.umsaetze]},
            "mail": {
                "postfaecher": list(POSTFAECHER),
                "nachrichten": [{"nachricht_id": m.nr, "postfach": POSTFAECHER[m.postfach],
                                 "empfangen": m.empfangen.strftime("%Y-%m-%dT%H:%M:%SZ"), "absender": m.absender,
                                 "betreff": m.betreff, "text": m.text} for m in self.mails]}}


# ---------------------------------------------------------------------------------------------------- Hilfen

def monat_plus(j: int, m: int, n: int) -> tuple[int, int]:
    j, m = divmod(j * 12 + (m - 1) + n, 12)
    return j, m + 1


def _tag(j: int, m: int, d: int) -> dt.date:
    return dt.date(j, m, min(d, calendar.monthrange(j, m)[1]))


def _werktag(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def _euro(cent: int) -> str:
    return f"{cent // 100},{cent % 100:02d} €"


def _ziffern(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def _karte(rng: random.Random, d: dt.date, laden: str) -> str:
    return f"KARTENZAHLUNG {d:%d.%m} {rng.randint(7, 21):02d}:{rng.randint(0, 59):02d} {laden} KARTE 4711"


def _zeit(d: dt.date, stunde: int, minute: int) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, stunde, minute, tzinfo=UTC)


def aenderungsmonat(heute: dt.date) -> tuple[int, int]:
    """Monat, ab dem die Stadtwerke den höheren Abschlag einziehen (kurz vor „heute“)."""
    d = heute - dt.timedelta(days=25)
    return d.year, d.month


# ---------------------------------------------------------------------------------------------------- Monat

class _Monat:
    """Alle Umsätze und Mails eines Kalendermonats."""

    def __init__(self, welt: Welt, j: int, m: int, startwert: int, kennung: str | None = None) -> None:
        self.w, self.j, self.m = welt, j, m
        self.kennung = kennung or f"{j:04d}{m:02d}"
        self.rng = random.Random(f"kontor-demo-{startwert}-{self.kennung}")
        self.tage = calendar.monthrange(j, m)[1]
        self.nr = 0

    def u(self, d: dt.date, betrag: int, name: str, zweck: str, kategorie: str | None = None, *, konto: str = "giro",
          tags: tuple[str, ...] = (), gegen_iban: str | None = None, merkmal: str | None = None) -> None:
        self.nr += 1
        self.w.umsaetze.append(Umsatz(konto, d, betrag, name, zweck, kategorie, tags, gegen_iban, merkmal,
                                      nr=f"D{self.kennung}-{self.nr:03d}"))

    def mail(self, postfach: int, wann: dt.datetime, absender: str, betreff: str, text: str, **mehr) -> None:
        self.nr += 1
        self.w.mails.append(Mail(postfach, wann, absender, betreff, text,
                                 nr=f"M{self.kennung}-{self.nr:03d}", **mehr))

    def tag(self, d: int) -> dt.date:
        return _tag(self.j, self.m, d)

    def zufallstag(self) -> dt.date:
        return self.tag(self.rng.randint(1, self.tage))

    def anzahl(self, mittel: float) -> int:
        """Ganzzahlige Anzahl um den Mittelwert (0,6 heißt: in sechs von zehn Monaten einmal)."""
        n, rest = divmod(mittel, 1)
        return int(n) + (1 if self.rng.random() < rest else 0) + self.rng.choice((-1, 0, 0, 1)) * (n >= 3)

    # ------------------------------------------------------------------------------------ feste Posten
    def einkommen(self) -> None:
        j, m = self.j, self.m
        stufe = max(0, min(3, j - 2023))
        self.u(_werktag(self.tag(27)), 258_000 + 6_500 * stufe, "Nordlicht Software GmbH",
               f"LOHN/GEHALT {m:02d}/{j} PERSONALNR 004711", "Einkommen:Gehalt")
        self.u(_werktag(self.tag(15)), 152_400 + 3_100 * stufe, "Stadt Musterstadt",
               f"BEZUEGE {m:02d}/{j} PERS.NR. 0815", "Einkommen:Gehalt")
        self.u(_werktag(self.tag(8)), 25_000 + 500 * max(0, min(2, j - 2024)), "Familienkasse Musterstadt",
               f"KG 123FK456789 {m:02d}/{j} KINDERGELD", "Einkommen")
        if m == 5:
            self.u(_werktag(self.tag(19)), 38_000 + self.rng.randint(0, 42_000), "Finanzamt Musterstadt",
                   f"ERSTATTUNG EINKOMMENSTEUER {j - 1} STEUERNR 99/999/99999", "Einkommen", tags=("Steuer",))

    def wohnen(self) -> None:
        j, m = self.j, self.m
        self.u(_werktag(self.tag(3)), -(31_500 if j < 2026 else 32_800), "Hausverwaltung Lindenhof GmbH",
               f"HAUSGELD {m:02d}/{j} WE 12 LINDENHOF 7", "Wohnen:Nebenkosten")
        abschlag = ABSCHLAG_NEU if (j, m) >= aenderungsmonat(self.w.heute) else ABSCHLAG_ALT
        d = _werktag(self.tag(10))
        self.u(d, -abschlag, STADTWERKE, f"ABSCHLAG STROM GAS WASSER {m:02d}/{j} VK 300412", None, merkmal="abschlag")
        self.mail(0, _zeit(d - dt.timedelta(days=4), 6, 30), "service@stadtwerke-musterstadt.example.invalid",
                  f"Ihr Abschlag für {m:02d}/{j} wird am {d:%d.%m.%Y} eingezogen",
                  f"Guten Tag Frau Mustermann,\n\nfür Ihr Vertragskonto 300412 ziehen wir am {d:%d.%m.%Y} den "
                  f"Abschlag von {_euro(abschlag)} ein.\n\nIhre Stadtwerke Musterstadt (Demodaten)\n")
        self.u(_werktag(self.tag(5)), -3_999, "Glasfaser Nordnetz GmbH",
               f"RECHNUNG {j}{m:02d}-{_ziffern(self.rng, 6)} KD-NR 558812", "Wohnen")
        self.u(_werktag(self.tag(12)), -3_998, "Mobilfunk Funkwelle",
               f"MOBILFUNK 2 VERTRAEGE {m:02d}/{j} KD 7001234", "Wohnen")
        if m == 4:
            diff = self.rng.choice((-1, 1)) * self.rng.randint(4_000, 23_000)
            self.u(_werktag(self.tag(22)), diff, "Hausverwaltung Lindenhof GmbH",
                   f"NEBENKOSTENABRECHNUNG {j - 1} WE 12 {'GUTHABEN' if diff > 0 else 'NACHZAHLUNG'}",
                   "Wohnen:Nebenkosten", merkmal="beleg")

    def kredite(self) -> None:
        j, m = self.j, self.m
        for k, merkmal in ((WOHNUNG, "rate_wohnung"), (AUTO, "rate_auto")):
            self.u(self.tag(k["tag"]), -k["rate"], k["bank"], f"{k['zweck']} {m:02d}/{j}", None, merkmal=merkmal)
        if (j, m) == sondertilgung_monat(self.w):
            d = self.tag(10)
            self.u(d - dt.timedelta(days=2), -SONDERTILGUNG, INHABER, "UMBUCHUNG FUER SONDERTILGUNG", None,
                   konto="sparbuch", gegen_iban=GIRO)
            self.u(d - dt.timedelta(days=2), SONDERTILGUNG, INHABER, "UMBUCHUNG FUER SONDERTILGUNG", None,
                   gegen_iban=SPARBUCH)
            self.u(d, -SONDERTILGUNG, WOHNUNG["bank"], "DARLEHEN 4711-0815 SONDERTILGUNG", None,
                   merkmal="sondertilgung")

    def vertraege(self) -> None:
        j, m = self.j, self.m
        self.u(_werktag(self.tag(1)), -2_890, "Sicherland Versicherung AG",
               f"KRANKENZUSATZ VS-NR 40112233 BEITRAG {m:02d}/{j}", "Versicherungen & Gesundheit")
        if m == 1:
            self.u(_werktag(self.tag(2)), -(58_900 + 1_100 * (j - 2023)), "Sicherland Versicherung AG",
                   f"KFZ-VERSICHERUNG M-US 4711 JAHRESBEITRAG {j}", "Versicherungen & Gesundheit", tags=("Auto",))
        if m == 3:
            self.u(_werktag(self.tag(1)), -7_400, "Sicherland Versicherung AG",
                   f"PRIVATHAFTPFLICHT VS-NR 40112299 JAHRESBEITRAG {j}", "Versicherungen & Gesundheit")
        if m == 6:
            self.u(_werktag(self.tag(1)), -11_800, "Sicherland Versicherung AG",
                   f"HAUSRAT VS-NR 40112277 JAHRESBEITRAG {j}", "Versicherungen & Gesundheit")
        # Preiserhöhung beim Streaming: die Serie wiederkehrender Buchungen ändert ihren Betrag
        self.u(_werktag(self.tag(9)), -(1_299 if (j, m) < monat_plus(self.w.heute.year, self.w.heute.month, -7)
                                         else 1_399),
               "Filmkiste Streaming", f"FILMKISTE ABO {m:02d}/{j} KD 99887766", "Freizeit")
        self.u(_werktag(self.tag(17)), -1_099, "Musikstrom", f"MUSIKSTROM FAMILIE {m:02d}/{j}", "Freizeit")
        self.u(_werktag(self.tag(20)), -2_490, "Morgenpost Verlag", f"MORGENPOST DIGITAL ABO {m:02d}/{j}",
               "Freizeit")
        # Das Fitnessstudio ist gekündigt: seit vier Monaten bleibt die Abbuchung aus
        if (j, m) < monat_plus(self.w.heute.year, self.w.heute.month, -4):
            self.u(_werktag(self.tag(2)), -3_490, "Fitnessclub Aktivpark",
                   f"MITGLIEDSBEITRAG {m:02d}/{j} MITGL-NR 20418", "Freizeit")
        self.u(_werktag(self.tag(4)), -(4_900 if j < 2025 else 5_800), "Verkehrsverbund Musterstadt",
               f"DEUTSCHLANDTICKET ABO {m:02d}/{j} ABO-NR 771200", "Mobilität:Bahn & ÖPNV")
        d = _werktag(self.tag(2))
        self.u(d, -60_000, INHABER, "DAUERAUFTRAG SPAREN", None, gegen_iban=SPARBUCH)
        self.u(d, 60_000, INHABER, "DAUERAUFTRAG SPAREN", None, konto="sparbuch", gegen_iban=GIRO)
        if m in (3, 6, 9, 12):
            self.u(self.tag(31), 1_800 + self.rng.randint(0, 2_600), "Musterbank AG", f"ZINSEN {(m + 2) // 3}. QUARTAL {j}",
                   "Einkommen", konto="sparbuch")

    # --------------------------------------------------------------------------------- Alltag
    def alltag(self) -> None:
        rng = self.rng
        for name, laden, von, bis, mittel in MAERKTE:
            for _ in range(self.anzahl(mittel)):
                d = self.zufallstag()
                anzeige = name
                if name.endswith("Frischekorb") and rng.random() < 0.15:
                    anzeige = FRISCHEKORB_ALIAS    # die Bank nennt den Markt manchmal anders: ein Alias
                self.u(d, -rng.randint(von, bis), anzeige, _karte(rng, d, laden), "Lebensmittel")
        for _ in range(self.anzahl(2.6)):
            d = self.zufallstag()
            self.u(d, -rng.randint(4_200, 8_900), "Tankstelle Sternfahrt",
                   _karte(rng, d, f"STERNFAHRT STATION {rng.choice((12, 12, 47))}"), "Mobilität:Tanken",
                   tags=("Auto",))
        for _ in range(self.anzahl(0.6)):
            d = self.zufallstag()
            strecke = rng.choice(("MUSTERSTADT-HAMBURG", "HAMBURG-MUSTERSTADT", "MUSTERSTADT-LEIPZIG"))
            self.u(d, -rng.randint(1_790, 11_900), "Bahnreise Fernverkehr",
                   f"FAHRKARTE AUFTRAG {_ziffern(rng, 6)} {strecke} {d:%d.%m}", "Mobilität:Bahn & ÖPNV")
        for _ in range(self.anzahl(5)):
            d = self.zufallstag()
            lokal = rng.choice(LOKALE)
            self.u(d, -rng.randint(1_400, 7_800), lokal, _karte(rng, d, lokal.upper()), "Freizeit:Restaurant")
        for _ in range(self.anzahl(2)):
            d = self.zufallstag()
            name, von, bis = rng.choice(FREIZEIT)
            self.u(d, -rng.randint(von, bis), name, _karte(rng, d, name.upper()), "Freizeit")
        for name, kategorie, von, bis, zehntel in LAEDEN:
            for _ in range(self.anzahl(zehntel / 10)):
                d = self.zufallstag()
                self.u(d, -rng.randint(von, bis), name, _karte(rng, d, name.upper()), kategorie)

    def amazon(self) -> None:
        for _ in range(self.anzahl(3)):
            self.bestellung(self.zufallstag())

    def bestellung(self, bestellt: dt.date, tage_bis_abbuchung: int | None = None) -> None:
        rng = self.rng
        nummer = f"30{rng.randint(2, 6)}-{_ziffern(rng, 7)}-{_ziffern(rng, 7)}"
        artikel = rng.sample(ARTIKEL, rng.choice((1, 1, 2, 3)))
        preise = [rng.randint(499, 4_999) for _ in artikel]
        summe = sum(preise)
        zeilen = "".join(f"1 x {a} {_euro(p)}\n" for a, p in zip(artikel, preise))
        self.mail(0, _zeit(bestellt, rng.randint(7, 22), rng.randint(0, 59)),
                  "bestellbestaetigung@amazon.example.invalid",
                  f"Ihre Amazon.de Bestellung von „{artikel[0]}“" + (" und weiteren Artikeln" if len(artikel) > 1 else ""),
                  f"Hallo Erika,\n\nvielen Dank für Ihre Bestellung.\nBestellnr. {nummer}\n\n{zeilen}"
                  f"Gesamtsumme: {_euro(summe)}\n\n(Demodaten)\n")
        self.u(bestellt + dt.timedelta(days=tage_bis_abbuchung or rng.randint(1, 3)), -summe,
               "AMAZON PAYMENTS EUROPE S.C.A.",
               f"{nummer} AMZN Mktp DE", "Einkäufe")
        if rng.random() < 0.12:      # Rücksendung: Erstattung samt Mail
            zurueck = bestellt + dt.timedelta(days=rng.randint(8, 16))
            self.mail(0, _zeit(zurueck, 9, 30), "rueckgabe@amazon.example.invalid",
                      f"Ihre Erstattung für die Bestellung {nummer}",
                      f"Hallo Erika,\n\nfür Ihre Rücksendung zur Bestellnr. {nummer}\n"
                      f"Erstattungsbetrag: {_euro(preise[0])}\n\n(Demodaten)\n")
            self.u(zurueck + dt.timedelta(days=2), preise[0], "AMAZON PAYMENTS EUROPE S.C.A.",
                   f"{nummer} AMZN Mktp DE ERSTATTUNG", "Einkäufe")

    def paypal(self) -> None:
        rng = self.rng
        for _ in range(self.anzahl(2)):
            self.zahlung(self.zufallstag())
        if rng.random() < 0.5:
            d = self.zufallstag()
            self.mail(1, _zeit(d, 5, 45), "neuigkeiten@fahrradladen-kettenblatt.example.invalid",
                      "Inspektion fürs Rad: jetzt Termin sichern",
                      "Hallo Max,\n\nIhr Rad freut sich auf die Inspektion.\n\nFahrradladen Kettenblatt (Demodaten)\n")

    def zahlung(self, d: dt.date) -> None:
        rng = self.rng
        haendler, kategorie = rng.choice(PAYPAL)
        betrag = rng.randint(990, 8_900)
        code = "".join(rng.choice("0123456789ABCDEFGHJKLMNPRSTUVWXY") for _ in range(17))
        self.mail(1, _zeit(d, rng.randint(8, 22), rng.randint(0, 59)), "service@paypal.example.invalid",
                  f"Sie haben eine Zahlung an {haendler} gesendet",
                  f"Hallo Max,\n\nSie haben {_euro(betrag)} an {haendler} gesendet.\n"
                  f"Transaktionscode: {code}\nGesendeter Betrag: -{_euro(betrag)}\n"
                  "Bezahlt mit\nLastschrift Musterbank (Demodaten)\n", haendler=haendler, betrag=betrag)
        self.u(d + dt.timedelta(days=rng.randint(1, 2)), -betrag, "PayPal Europe S.a.r.l. et Cie S.C.A",
               f"PP.{_ziffern(rng, 4)}.PP . {haendler}, Ihr Einkauf bei {haendler}", kategorie, merkmal="paypal")

    def besonderes(self) -> None:
        j, m, rng = self.j, self.m, self.rng
        if (m, j % 2 == 0) in URLAUB:
            unterkunft, preis, vorort = URLAUB[m, j % 2 == 0]
            tags = (f"Urlaub {j}",)
            self.u(self.tag(3), -(preis + rng.randint(0, 9_000)), unterkunft,
                   f"BUCHUNG {_ziffern(rng, 6)} MUSTERMANN ANREISE {self.tag(14):%d.%m.%Y}", "Freizeit",
                   tags=tags, merkmal="beleg")
            for i in range(rng.randint(5, 8)):
                d = self.tag(14 + rng.randint(0, 6))
                name = rng.choice(vorort)
                self.u(d, -rng.randint(900, 9_800), name, _karte(rng, d, name.upper()), "Freizeit", tags=tags)
        if m == 9:
            self.u(_werktag(self.tag(18)), -rng.randint(28_000, 86_000), "Autohaus Radwechsel",
                   f"RECHNUNG {j}-{_ziffern(rng, 4)} INSPEKTION M-US 4711", "Mobilität", tags=("Auto",),
                   merkmal="beleg")
        if m in (3, 10):
            self.u(_werktag(self.tag(24)), -rng.randint(6_000, 24_000), "Zahnarztpraxis Dr. Beispiel",
                   f"RECHNUNG {_ziffern(rng, 5)} VOM {self.tag(11):%d.%m.%Y}", "Versicherungen & Gesundheit", merkmal="beleg")
        if (j * 12 + m) % 17 == 0:      # Möbel gibt es nur alle anderthalb Jahre
            self.u(_werktag(self.tag(6)), -rng.randint(39_000, 129_000), "Möbelhaus Wohnidee",
                   f"AUFTRAG {_ziffern(rng, 7)} LIEFERUNG", "Einkäufe", merkmal="beleg")

    def alles(self) -> None:
        for teil in (self.einkommen, self.wohnen, self.kredite, self.vertraege, self.alltag, self.amazon,
                     self.paypal, self.besonderes):
            teil()


def sondertilgung_monat(welt: Welt) -> tuple[int, int] | None:
    """Der November des Vorjahres, wenn er ganz im Zeitraum liegt (sonst gibt es keine Sondertilgung)."""
    j = welt.heute.year - 1
    return (j, 11) if welt.start <= dt.date(j, 11, 1) else None


def welt(heute: dt.date, monate: int = 36, startwert: int = 2026) -> Welt:
    """Die Welt von ``monate`` Monaten vor dem Monat von ``heute`` bis ``VORRAT_TAGE`` Tage danach."""
    if not 1 <= monate <= 240:
        raise ValueError("monate muss zwischen 1 und 240 liegen.")
    j, m = monat_plus(heute.year, heute.month, -monate)
    w = Welt(heute=heute, start=dt.date(j, m, 1))
    ende = heute + dt.timedelta(days=VORRAT_TAGE)
    while (j, m) <= (ende.year, ende.month):
        _Monat(w, j, m, startwert).alles()
        j, m = monat_plus(j, m, 1)
    rng = random.Random(f"kontor-demo-{startwert}-neu-{heute.isoformat()}")
    for i, (tage, name, von, bis, kategorie) in enumerate(NEUE):
        d = heute + dt.timedelta(days=tage)
        w.umsaetze.append(Umsatz("giro", d, -rng.randint(von, bis), name, _karte(rng, d, name.upper()), kategorie,
                                 nr=f"DNEU-{i + 1:03d}"))
    # Bestellungen und Zahlungen rund um „heute“: die ersten Abrufe der Vorführung bringen sicher neue Mails,
    # und die Abbuchung zur Bestellung von vorgestern kommt gleich mit (die Mail hängt sich an die Buchung)
    dazu = _Monat(w, heute.year, heute.month, startwert, kennung=f"H{heute:%Y%m%d}")
    for tage in (-2, 1, 5, 11, 19):
        dazu.bestellung(heute + dt.timedelta(days=tage), tage_bis_abbuchung=1)
    for tage in (0, 4, 13):
        dazu.zahlung(heute + dt.timedelta(days=tage))
    w.umsaetze = sorted((u for u in w.umsaetze if w.start <= u.datum <= ende), key=lambda u: (u.datum, u.nr))
    w.mails = sorted((x for x in w.mails if w.start <= x.empfangen.date() <= ende),
                     key=lambda x: (x.empfangen, x.nr))
    return w
