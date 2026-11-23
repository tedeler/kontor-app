"""Testdaten für Meilenstein 2: Bank-Synchronisation und Regel-Kategorisierung.

Erzeugt (alles synthetisch, fester Startwert):

- ``mock/sync_daten.json``: Mock-Datendatei (``kontor-mock-daten`` Version 1)
  mit drei Bankkonten (Giro, Tagesgeld, Kreditkarte) und Umsätzen von Januar
  bis Juni 2024, inklusive Störfällen (Vormerkungen, Storno, zweimal derselbe
  Kaffee, fehlende Gegenpartei, Leerraum im Namen, Umlaute, langer und leerer
  Verwendungszweck, Betrag 0, gleicher Betrag an fremde IBAN). Optionaler
  Schlüssel ``bank.tan`` (richtige Mock-TAN, plugins.md 7.2).
- ``mock/sync_daten_pin.json``: dieselben Daten mit ``bank.pin`` (Mock-PIN).
- ``kmy/sync_altbestand.kmy``: KMyMoney-Altbestand bis 15.02.2024 mit
  denselben IBANs für den Abgleich beim Abruf (synchronisation.md 4.4):
  exakte, per ``ekey`` passende, ähnliche und mehrdeutige Treffer sowie eine
  importierte Umbuchung, deren beide Bankseiten zusammengeführt werden.
- ``sync/regeln.json``: Kategorien, Konten und ein Regelsatz mit
  überlappenden Regeln, Gleichstand, inaktiver Regel, Betrags-, Konto- und
  Umlautbedingungen (kategorisierung.md).
- ``mock/sync_daten.erwartung.json``: bekannte Wahrheit je Umsatz (richtige
  Kategorie, Ergebnis des Regelsatzes, Ergebnis des Abgleichs mit dem
  Altbestand), Stichtage für zeitlich fortlaufende Abrufe.

Die Ergebnisse von Regeln und Abgleich sind von Hand konstruiert (Fallklasse
je Umsatz) und werden in ``tests/generator`` mit einem unabhängigen Orakel
gegengeprüft.
"""

from __future__ import annotations

import datetime as dt
import random

from .iban import fiktive_iban
from .kmy import KBuch, KBuchung, KKonto, KSplit

GIRO = fiktive_iban(8001)
SPAR = fiktive_iban(8002)
KREDIT = fiktive_iban(8003)
FREMD = fiktive_iban(8999)
INHABER = "Erika Mustermann (fiktiv)"
PIN = "PIN-ATTRAPPE-4711-SYNTHETISCH"
TAN = "TAN-ATTRAPPE-0815"
STUFEN = ["2024-02-15", "2024-04-30", "2024-06-30"]
ALTBESTAND_BIS = "2024-02-15"
POSTFACH_1 = "sync.eins@example.invalid"
POSTFACH_2 = "sync.zwei@example.invalid"

LANGER_ZWECK = ("Sammelbestellung Nr. 2024-04-12 – Lieferung an Musterweg 1, Musterstadt; Artikel: "
                "Gießkanne, Schürze, Küchenwaage, Blumentöpfe (Ton), Ölkännchen & Zubehör; "
                "Rückfragen über das fiktive Kundenportal. ") * 6

KATEGORIEN = [
    ("Gehalt", "ertrag"), ("Zinsertrag", "ertrag"), ("Miete", "aufwand"), ("Strom", "aufwand"),
    ("Lebensmittel", "aufwand"), ("Café & Restaurant", "aufwand"), ("Tanken", "aufwand"),
    ("Abos", "aufwand"), ("Sonstiges", "aufwand"),
]


def _regeln() -> list[dict]:
    """Regelsatz in Anlegereihenfolge (IDs steigen in dieser Reihenfolge)."""
    def text(feld, op, wert):
        return {"feld": feld, "operator": op, "wert": wert}

    def betrag(op, wert):
        return {"feld": "betrag", "operator": op, "wert": wert}

    def konto(iban):
        return {"feld": "konto_id", "operator": "gleich", "wert": {"iban": iban}}

    return [
        {"name": "Alles mit e (inaktiv)", "aktiv": False, "prioritaet": 1, "kategorie": "Sonstiges",
         "bedingungen": [text("verwendungszweck", "enthaelt", "e")]},
        {"name": "Gehalt", "aktiv": True, "prioritaet": 10, "kategorie": "Gehalt",
         "bedingungen": [text("empfaenger", "enthaelt", "Arbeitgeber"), betrag("mindestens", 100000)]},
        {"name": "Miete", "aktiv": True, "prioritaet": 20, "kategorie": "Miete",
         "bedingungen": [text("verwendungszweck", "beginnt_mit", "MIETE")]},
        {"name": "Strom", "aktiv": True, "prioritaet": 20, "kategorie": "Strom",
         "bedingungen": [text("empfaenger", "gleich", "stadtwerke musterstadt")]},
        {"name": "Café", "aktiv": True, "prioritaet": 30, "kategorie": "Café & Restaurant",
         "bedingungen": [text("empfaenger", "enthaelt", "café")]},
        {"name": "Bäckerei", "aktiv": True, "prioritaet": 35, "kategorie": "Lebensmittel",
         "bedingungen": [text("empfaenger", "enthaelt", "Bäckerei")]},
        {"name": "Supermarkt", "aktiv": True, "prioritaet": 40, "kategorie": "Lebensmittel",
         "bedingungen": [text("empfaenger", "enthaelt", "FRISCHEKORB")]},
        {"name": "Kaufhaus groß", "aktiv": True, "prioritaet": 45, "kategorie": "Sonstiges",
         "bedingungen": [text("empfaenger", "enthaelt", "kaufhaus"), betrag("hoechstens", -10000)]},
        {"name": "Kartenzahlung", "aktiv": True, "prioritaet": 50, "kategorie": "Sonstiges",
         "bedingungen": [text("verwendungszweck", "enthaelt", "kartenzahlung")]},
        {"name": "Tankstelle", "aktiv": True, "prioritaet": 60, "kategorie": "Tanken",
         "bedingungen": [text("empfaenger", "beginnt_mit", "tankstelle")]},
        {"name": "Blitz (Gleichstand, verliert)", "aktiv": True, "prioritaet": 60, "kategorie": "Sonstiges",
         "bedingungen": [text("empfaenger", "enthaelt", "blitz")]},
        {"name": "Abo Kreditkarte", "aktiv": True, "prioritaet": 70, "kategorie": "Abos",
         "bedingungen": [konto(KREDIT), text("verwendungszweck", "enthaelt", "abo")]},
        {"name": "Zinsen Tagesgeld", "aktiv": True, "prioritaet": 80, "kategorie": "Zinsertrag",
         "bedingungen": [konto(SPAR), betrag("mindestens", 1), text("verwendungszweck", "enthaelt", "zins")]},
        {"name": "Streaming (spät angelegt, Vorrang)", "aktiv": True, "prioritaet": 5, "kategorie": "Abos",
         "bedingungen": [text("verwendungszweck", "enthaelt", "streamingdienst"), betrag("gleich", -1299)]},
    ]


# Erwartetes Regelergebnis je Fallklasse (von Hand nach kategorisierung.md 1/4 bestimmt)
_REGEL_FUER_FALL = {
    "gehalt": "Gehalt", "miete": "Miete", "strom": "Strom", "strom_gmbh": None, "cafe": "Café",
    "baecker": "Bäckerei", "super": "Supermarkt", "kaufhaus_gross": "Kaufhaus groß", "kaufhaus_klein": None,
    "storno": None, "kiosk_karte": "Kartenzahlung", "kiosk_leer": None, "tanken": "Tankstelle",
    "abo_kredit": "Streaming (spät angelegt, Vorrang)", "abo_giro": "Streaming (spät angelegt, Vorrang)",
    "zinsen": "Zinsen Tagesgeld", "umbuchung": None, "online": None, "bargeld": None, "lang": None,
    "null": None, "fremd": None, "vormerkung": None, "abo_kk_musik": "Abo Kreditkarte", "abo_giro_musik": None,
}


def _regel_eval_generator(regeln: list[dict], u: dict) -> str | None:
    """Kontrollrechnung des Generators (die Tests haben ein eigenes Orakel)."""
    def norm(s):
        return s.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")

    name = (u["gegenpartei_name"] or "").strip() or None
    reihen = sorted(enumerate(regeln), key=lambda x: (x[1]["prioritaet"], x[0]))
    for _, r in reihen:
        if not r["aktiv"]:
            continue
        ok = True
        for b in r["bedingungen"]:
            if b["feld"] in ("empfaenger", "verwendungszweck"):
                x = name if b["feld"] == "empfaenger" else u["verwendungszweck"]
                if x is None:
                    ok = False
                else:
                    nx, nw = norm(x), norm(b["wert"])
                    ok = {"enthaelt": nw in nx, "gleich": nx == nw, "beginnt_mit": nx.startswith(nw)}[b["operator"]]
            elif b["feld"] == "betrag":
                ok = {"gleich": u["betrag"] == b["wert"], "mindestens": u["betrag"] >= b["wert"],
                      "hoechstens": u["betrag"] <= b["wert"]}[b["operator"]]
            else:
                ok = u["iban"] == b["wert"]["iban"]
            if not ok:
                break
        if ok:
            return r["name"]
    return None


def sync_daten(startwert: int) -> dict[str, object]:
    rng = random.Random(startwert + 2)
    benutzt: dict[str, set[int]] = {GIRO: set(), SPAR: set(), KREDIT: set()}
    umsaetze: list[dict] = []
    meta: dict[str, dict] = {}
    zaehler = [0]

    def einzig(iban: str, lo: int, hi: int) -> int:
        while True:
            b = -rng.randint(lo, hi)
            if b not in benutzt[iban]:
                benutzt[iban].add(b)
                return b

    def neu(iban, tag, betrag, name, gegen_iban, zweck, kategorie, fall, *, vormerkung=False, storno=False,
            abgleich="neu", kmy=None) -> str:
        zaehler[0] += 1
        uid = f"S-{zaehler[0]:05d}"
        benutzt[iban].add(betrag)
        umsaetze.append({
            "umsatz_id": uid, "iban": iban, "buchungstag": tag.isoformat(),
            "valuta": None if vormerkung else tag.isoformat(), "betrag": betrag, "waehrung": "EUR",
            "gegenpartei_name": name, "gegenpartei_iban": gegen_iban, "verwendungszweck": zweck,
            "vormerkung": vormerkung, "storno": storno,
        })
        meta[uid] = {"kategorie": kategorie, "fall": fall, "abgleich": "vormerkung" if vormerkung else abgleich,
                     "kmy": kmy}
        return uid

    D = dt.date
    # Feste Beträge vorab reservieren, damit Zufallsbeträge sie nie treffen
    for b in (-98000, -9200, -30000, 335000, -350, -480, -2222, -1299, -3333, -2999, -12999, 12999, -10000,
              -9999, -5000, -420, -2599, -1500, 0, 30000, -2007):
        benutzt[GIRO].add(b)
    for b in (30000, 1234, 1301):
        benutzt[SPAR].add(b)
    for b in (-1299, -4500, -899):
        benutzt[KREDIT].add(b)
    benutzt[GIRO].add(-899)

    # ------------------------------------------------------------ Monatsmuster
    for m in range(1, 7):
        def im_alt(tag: dt.date) -> bool:
            return tag.isoformat() <= ALTBESTAND_BIS

        t = D(2024, m, 3)
        neu(GIRO, t, -98000, "Wohnbau Beispiel eG", FREMD, f"Miete {m:02d}/2024", "Miete", "miete",
            abgleich="exakt" if im_alt(t) else "neu", kmy={"payee": "Wohnbau Beispiel eG"} if im_alt(t) else None)
        t = D(2024, m, 5)
        if m == 4:
            neu(GIRO, t, -9200, "Stadtwerke Musterstadt GmbH", FREMD, "Abschlag Strom", "Strom", "strom_gmbh")
        else:
            neu(GIRO, t, -9200, "Stadtwerke Musterstadt", FREMD, "Abschlag Strom", "Strom", "strom",
                abgleich="exakt" if im_alt(t) else "neu",
                kmy={"payee": "Stadtwerke Musterstadt"} if im_alt(t) else None)
        t = D(2024, m, 28)
        neu(GIRO, t, 335000, "Arbeitgeber Muster GmbH", FREMD, f"LOHN/GEHALT {m:02d}/2024", "Gehalt", "gehalt",
            abgleich="exakt" if im_alt(t) else "neu",
            kmy={"payee": "Arbeitgeber Muster GmbH"} if im_alt(t) else None)
        # Sparrate Giro -> Tagesgeld (Umbuchung, beide Seiten)
        t = D(2024, m, 25)
        if im_alt(t):
            ref = f"umbuchung-{m}"
            neu(GIRO, t, -30000, INHABER, SPAR, "Sparrate", None, "umbuchung", abgleich="umbuchung",
                kmy={"umbuchung": ref})
            neu(SPAR, t, 30000, INHABER, GIRO, "Sparrate", None, "umbuchung", abgleich="umbuchung",
                kmy={"umbuchung": ref})
        else:
            neu(GIRO, t, -30000, INHABER, SPAR, "Sparrate", None, "umbuchung")
            neu(SPAR, t, 30000, INHABER, GIRO, "Sparrate", None, "umbuchung")
        # Kreditkartenausgleich Giro -> Kreditkarte (am 15.)
        t = D(2024, m, 15)
        x = -einzig(GIRO, 15000, 60000)
        benutzt[KREDIT].add(x)
        neu(GIRO, t, -x, "Testbank Kartenservice (fiktiv)", KREDIT, f"Kreditkarte Ausgleich {m:02d}/2024", None,
            "umbuchung", abgleich="exakt" if im_alt(t) else "neu",
            kmy={"payee": "Testbank Kartenservice (fiktiv)", "kategorie": "Kreditkartenabrechnung"}
            if im_alt(t) else None)
        neu(KREDIT, t, x, "Testbank Kartenservice (fiktiv)", GIRO, f"Ausgleich {m:02d}/2024", None, "umbuchung")
        # Supermarkt
        for i in range(rng.randint(4, 6)):
            t = D(2024, m, rng.randint(1, 27))
            b = einzig(GIRO, 800, 9000)
            if m == 1 and i == 0:
                fall_abgleich, kmy = ("neu", None)  # fehlt im Altbestand
            elif im_alt(t):
                fall_abgleich, kmy = ("exakt", {"payee": "Supermarkt Frischekorb"})
            else:
                fall_abgleich, kmy = ("neu", None)
            neu(GIRO, t, b, "Supermarkt Frischekorb", None, f"Kartenzahlung {rng.randint(1, 999):03d}",
                "Lebensmittel", "super", abgleich=fall_abgleich, kmy=kmy)
        # Café
        for i in range(rng.randint(1, 2)):
            t = D(2024, m, rng.randint(1, 27))
            b = einzig(GIRO, 300, 1100)
            if m == 1 and i == 0:
                t = D(2024, 1, 9)
                fall_abgleich, kmy = ("aehnlich", {"payee": "Café Bohne", "datum": "2024-01-10"})
            elif im_alt(t):
                fall_abgleich, kmy = ("exakt", {"payee": "Café Bohne"})
            else:
                fall_abgleich, kmy = ("neu", None)
            neu(GIRO, t, b, "Café Bohne", None, "Kartenzahlung Café", "Café & Restaurant", "cafe",
                abgleich=fall_abgleich, kmy=kmy)
        # Bäckerei mit wechselnder Schreibweise
        t = D(2024, m, 11)
        name = "Bäckerei Korn & Söhne" if m % 2 else "BAECKEREI KORN & SOEHNE"
        kmy_name = "Baeckerei Korn & Soehne" if m % 2 else "Bäckerei Korn & Söhne"
        neu(GIRO, t, einzig(GIRO, 250, 900), name, None, "Brötchen und Brot", "Lebensmittel", "baecker",
            abgleich="exakt" if im_alt(t) else "neu", kmy={"payee": kmy_name} if im_alt(t) else None)
        # Tankstelle
        t = D(2024, m, 17)
        if m == 1:
            neu(GIRO, t, einzig(GIRO, 4000, 8000), "Tankstelle Blitz", None, "Tanken", "Tanken", "tanken",
                abgleich="aehnlich", kmy={"payee": "Tankstelle Blitz Nord"})
        else:
            neu(GIRO, t, einzig(GIRO, 4000, 8000), "Tankstelle Blitz", None, "Tanken", "Tanken", "tanken")
        # Kreditkarte: Streaming-Abo und Onlinekäufe
        neu(KREDIT, D(2024, m, 10), -1299, "Streamio", None, "Abo Streamingdienst", "Abos", "abo_kredit")
        for _ in range(rng.randint(1, 2)):
            neu(KREDIT, D(2024, m, rng.randint(1, 27)), einzig(KREDIT, 1000, 6000), "Onlineshop Beispiel", None,
                f"Bestellung {rng.randint(100, 999)}", "Sonstiges", "online")

    # --------------------------------------------------------- Einzelfälle
    neu(GIRO, D(2024, 1, 12), -5000, None, None, "Bargeldauszahlung Automat 12", "Sonstiges", "bargeld",
        abgleich="exakt", kmy={"payee": None})
    neu(GIRO, D(2024, 1, 20), -480, "Café Bohne", None, "Kartenzahlung Café", "Café & Restaurant", "cafe",
        abgleich="mehrdeutig_kmy_doppelt", kmy={"payee": "Café Bohne", "anzahl": 2})
    neu(GIRO, D(2024, 2, 7), -2222, "Supermarkt Frischekorb", None, "Kartenzahlung 222", "Lebensmittel", "super",
        abgleich="mehrdeutig_bank_doppelt", kmy={"payee": "Supermarkt Frischekorb", "gruppe": "2222"})
    neu(GIRO, D(2024, 2, 7), -2222, "Supermarkt Frischekorb", None, "Kartenzahlung 222", "Lebensmittel", "super",
        abgleich="mehrdeutig_bank_doppelt", kmy={"payee": "Supermarkt Frischekorb", "gruppe": "2222"})
    # Vormerkung, die später gebucht erscheint
    neu(GIRO, D(2024, 2, 14), -3333, "Tankstelle Blitz", None, "Vorgemerkt: Tanken", "Tanken", "vormerkung",
        vormerkung=True)
    neu(GIRO, D(2024, 2, 16), -3333, "Tankstelle Blitz", None, "Tanken", "Tanken", "tanken")
    neu(GIRO, D(2024, 2, 20), -5000, None, None, "Bargeldauszahlung Automat 17", "Sonstiges", "bargeld")
    neu(GIRO, D(2024, 3, 5), -350, "Café Bohne", None, "Kartenzahlung Café", "Café & Restaurant", "cafe")
    neu(GIRO, D(2024, 3, 5), -350, "Café Bohne", None, "Kartenzahlung Café", "Café & Restaurant", "cafe")
    neu(GIRO, D(2024, 3, 10), -12999, "Kaufhaus Beispiel", None, "Bestellung 4711", "Sonstiges", "kaufhaus_gross")
    neu(GIRO, D(2024, 3, 12), 12999, "Kaufhaus Beispiel", None, "STORNO Bestellung 4711", "Sonstiges", "storno",
        storno=True)
    neu(GIRO, D(2024, 3, 18), -420, "  Kiosk Ecke  ", None, "Kartenzahlung Zeitschrift", "Sonstiges", "kiosk_karte")
    neu(SPAR, D(2024, 3, 29), 1234, "Testbank (fiktiv)", None, "Zinsen 1. Quartal 2024", "Zinsertrag", "zinsen")
    neu(GIRO, D(2024, 4, 8), -10000, "Kaufhaus Beispiel", None, "Bestellung 5000", "Sonstiges", "kaufhaus_gross")
    neu(GIRO, D(2024, 4, 9), -9999, "Kaufhaus Beispiel", None, "Bestellung 5001", "Sonstiges", "kaufhaus_klein")
    neu(GIRO, D(2024, 4, 12), -2599, "Versandhandel Ähnlich & Co.", None, LANGER_ZWECK, "Sonstiges", "lang")
    neu(KREDIT, D(2024, 4, 30), -4500, "Onlineshop Beispiel", None, "Vorgemerkt: Bestellung", "Sonstiges",
        "vormerkung", vormerkung=True)
    neu(GIRO, D(2024, 5, 10), -1299, "Streamio", None, "Abo Streamingdienst", "Abos", "abo_giro")
    neu(GIRO, D(2024, 5, 20), -1500, "Kiosk Ecke", None, "", "Sonstiges", "kiosk_leer")
    neu(KREDIT, D(2024, 5, 21), -899, "Klangwelle (fiktiv)", None, "Abo Musikdienst", "Abos", "abo_kk_musik")
    neu(GIRO, D(2024, 6, 21), -899, "Klangwelle (fiktiv)", None, "Abo Musikdienst", "Abos", "abo_giro_musik")
    neu(GIRO, D(2024, 6, 3), 0, "Testbank (fiktiv)", None, "Kontoführung 06/2024 (0,00 EUR)", "Sonstiges", "null")
    neu(GIRO, D(2024, 6, 25), -30000, "Fremde Person (fiktiv)", FREMD, "Darlehen privat", "Sonstiges", "fremd")
    neu(SPAR, D(2024, 6, 28), 1301, "Testbank (fiktiv)", None, "Zinsen 2. Quartal 2024", "Zinsertrag", "zinsen")
    neu(GIRO, D(2024, 6, 29), -2999, "Café Bohne", None, "Vorgemerkt: Café", "Café & Restaurant", "vormerkung",
        vormerkung=True)

    umsaetze.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    regeln = _regeln()

    # ------------------------------------------------------ Regelergebnisse
    kat_der_regel = {r["name"]: r["kategorie"] for r in regeln}
    regel_ergebnis: dict[str, dict | None] = {}
    for u in umsaetze:
        m = meta[u["umsatz_id"]]
        soll = _REGEL_FUER_FALL[m["fall"]]
        kontrolle = None if u["vormerkung"] else _regel_eval_generator(regeln, u)
        assert soll == kontrolle or m["fall"] == "vormerkung", (u["umsatz_id"], m["fall"], soll, kontrolle)
        if m["fall"] == "vormerkung":
            soll = None
        regel_ergebnis[u["umsatz_id"]] = None if soll is None else {"regel": soll, "kategorie": kat_der_regel[soll]}
        if soll is not None:
            assert kat_der_regel[soll] == m["kategorie"], (u["umsatz_id"], soll)

    # ---------------------------------------------------------- Altbestand
    kbuch, abgleich = _altbestand(umsaetze, meta, rng)

    bank = {
        "konten": [
            {"iban": GIRO, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto", "inhaber": INHABER,
             "waehrung": "EUR"},
            {"iban": SPAR, "bic": "TESTDEFFXXX", "name": "Tagesgeld", "art": "sparkonto", "inhaber": INHABER,
             "waehrung": "EUR"},
            {"iban": KREDIT, "bic": None, "name": "  Kreditkarte  ", "art": "kreditkonto", "inhaber": INHABER,
             "waehrung": "EUR"},
        ],
        "umsaetze": umsaetze,
        "tan": TAN,
    }
    mail = {
        "postfaecher": [POSTFACH_1, POSTFACH_2],
        "nachrichten": [
            {"nachricht_id": f"SM-{n:04d}", "postfach": POSTFACH_1 if n % 2 else POSTFACH_2,
             "empfangen": f"2024-0{n}-0{n}T09:30:00Z", "absender": "bestellung@shop.example.invalid",
             "betreff": f"Bestellung {n} (fiktiv)", "text": "Synthetische Testnachricht."}
            for n in range(1, 5)
        ],
    }
    daten = {"format": "kontor-mock-daten", "version": 1, "bank": bank, "mail": mail}
    daten_pin = {"format": "kontor-mock-daten", "version": 1, "bank": {**bank, "pin": PIN}, "mail": mail}

    regeldatei = {
        "beschreibung": "Regelsatz für Meilenstein 2 (kategorisierung.md). Konten und Kategorien zuerst anlegen, "
                        "dann die Regeln in Listenreihenfolge; konto_id-Werte {\"iban\": …} auf die ID des Kontos "
                        "mit dieser IBAN abbilden, kategorie auf die ID der Kategorie mit diesem Namen.",
        "kategorien": [{"name": n, "art": a} for n, a in KATEGORIEN],
        "konten": [{"name": "Girokonto", "art": "girokonto", "iban": GIRO},
                   {"name": "Tagesgeld", "art": "sparkonto", "iban": SPAR},
                   {"name": "Kreditkarte", "art": "kreditkonto", "iban": KREDIT}],
        "regeln": regeln,
    }

    gebucht = [u for u in umsaetze if not u["vormerkung"]]
    erwartung = {
        "fixture": "mock/sync_daten.json",
        "stufen": STUFEN,
        "altbestand_bis": ALTBESTAND_BIS,
        "pin": PIN,
        "tan": TAN,
        "ibans": {"giro": GIRO, "spar": SPAR, "kredit": KREDIT, "fremd": FREMD},
        "konto_namen": {GIRO: "Girokonto", SPAR: "Tagesgeld", KREDIT: "Kreditkarte"},
        "wahre_kategorie": {u["umsatz_id"]: meta[u["umsatz_id"]]["kategorie"] for u in umsaetze},
        "fall": {u["umsatz_id"]: meta[u["umsatz_id"]]["fall"] for u in umsaetze},
        "vormerkungen": [u["umsatz_id"] for u in umsaetze if u["vormerkung"]],
        "stornos": [u["umsatz_id"] for u in umsaetze if u["storno"]],
        "regel_ergebnis": regel_ergebnis,
        "abgleich_altbestand": abgleich,
        "saldo_veraenderung": {i: sum(u["betrag"] for u in gebucht if u["iban"] == i) for i in (GIRO, SPAR, KREDIT)},
        "anzahl_gebucht": {i: sum(u["iban"] == i for u in gebucht) for i in (GIRO, SPAR, KREDIT)},
    }
    return {"daten": daten, "daten_pin": daten_pin, "erwartung": erwartung, "kbuch": kbuch,
            "regeln": regeldatei}


def _altbestand(umsaetze: list[dict], meta: dict[str, dict], rng: random.Random) -> tuple[KBuch, dict]:
    """KMyMoney-Altbestand bis ALTBESTAND_BIS und erwartetes Abgleichergebnis je Umsatz."""
    b = KBuch(erstellt="2023-10-31", geaendert="2024-02-16")
    G, S = "A000001", "A000002"
    kat_ids = {"Gehalt": ("A000010", 12), "Miete": ("A000011", 13), "Strom": ("A000012", 13),
               "Lebensmittel": ("A000013", 13), "Café & Restaurant": ("A000014", 13), "Tanken": ("A000015", 13),
               "Kreditkartenabrechnung": ("A000016", 13), "Sonstiges": ("A000017", 13)}
    b.konten = [
        KKonto(G, "Girokonto", 1, "AStd::Asset", eroeffnet="2023-01-01", iban=GIRO),
        KKonto(S, "Tagesgeld", 2, "AStd::Asset", eroeffnet="2023-01-01", iban=SPAR),
    ] + [KKonto(kid, name, typ, "AStd::Income" if typ == 12 else "AStd::Expense")
         for name, (kid, typ) in kat_ids.items()] + [
        KKonto("A000018", "Anfangsbestand", 16, "AStd::Equity"),
    ]
    payees: dict[str, str] = {}

    def payee(name: str | None) -> str:
        if name is None:
            return ""
        if name not in payees:
            payees[name] = f"P{len(payees) + 1:06d}"
        return payees[name]

    roh: list[tuple[str, int, dict]] = []  # (datum, reihenfolge, daten)

    def buchung(datum: str, splits: list[KSplit], memo: str, ref: str, kategorie: str | None,
                umbuchung: bool = False) -> None:
        roh.append((datum, len(roh), {"datum": datum, "splits": splits, "memo": memo, "ref": ref,
                                       "kategorie": kategorie, "umbuchung": umbuchung}))

    def einfach(datum, konto, kat, betrag, name, memo, ref):
        p = payee(name)
        buchung(datum, [KSplit(konto, betrag, memo=memo, empfaenger=p),
                        KSplit(kat_ids[kat][0], -betrag, empfaenger=p)], memo, ref, kat)

    # Anfangsbestand und Vorgeschichte (Nov./Dez. 2023), Beträge nie in der Nähe von Bankumsätzen
    buchung("2023-11-01", [KSplit(G, 500000, memo="Anfangsbestand"), KSplit("A000018", -500000)],
            "Anfangsbestand", "vor-anfang", None)
    buchung("2023-11-01", [KSplit(S, 1000000, memo="Anfangsbestand"), KSplit("A000018", -1000000)],
            "Anfangsbestand", "vor-anfang-spar", None)
    vor = 0
    for m in (11, 12):
        einfach(f"2023-{m}-03", G, "Miete", -98000, "Wohnbau Beispiel eG", f"Miete {m}/2023", f"vor-{vor}")
        vor += 1
        einfach(f"2023-{m}-05", G, "Strom", -9200, "Stadtwerke Musterstadt", "Abschlag Strom", f"vor-{vor}")
        vor += 1
        einfach(f"2023-{m}-28", G, "Gehalt", 335000, "Arbeitgeber Muster GmbH", f"LOHN/GEHALT {m}/2023",
                f"vor-{vor}")
        vor += 1
        p = payee(INHABER)
        buchung(f"2023-{m}-25", [KSplit(G, -30000, memo="Sparrate", empfaenger=p),
                                 KSplit(S, 30000, memo="Sparrate", empfaenger=p)], "Sparrate", f"vor-{vor}", None,
                umbuchung=True)
        vor += 1
        for _ in range(3):
            einfach(f"2023-{m}-{rng.randint(1, 26):02d}", G, "Lebensmittel", -(rng.randint(80, 899) * 10 + 7),
                    "Supermarkt Frischekorb", "Kartenzahlung alt", f"vor-{vor}")
            vor += 1
    # Nur im Altbestand, ohne Bankgegenstück (Betrag endet auf 7: nie ein Bankbetrag in der Nähe)
    einfach("2024-01-30", G, "Sonstiges", -2007, "Flohmarkt (fiktiv)", "Barzahlung", "nur-kmy")

    # Gegenstücke zu Bankumsätzen
    abgleich: dict[str, dict] = {}
    umbuchungen: dict[str, list[str]] = {}
    gruppen: dict[str, list[str]] = {}
    for u in umsaetze:
        uid, m = u["umsatz_id"], meta[u["umsatz_id"]]
        art = m["abgleich"]
        if art in ("neu", "vormerkung"):
            abgleich[uid] = {"ergebnis": art}
            continue
        konto = G if u["iban"] == GIRO else S
        kat = (m["kmy"] or {}).get("kategorie") or m["kategorie"]
        if art == "exakt":
            ref = f"k-{uid}"
            einfach(u["buchungstag"], konto, kat, u["betrag"], m["kmy"]["payee"], u["verwendungszweck"], ref)
            abgleich[uid] = {"ergebnis": "zusammengefuehrt", "mit": [ref]}
        elif art == "aehnlich":
            ref = f"k-{uid}"
            einfach(m["kmy"].get("datum", u["buchungstag"]), konto, kat, u["betrag"], m["kmy"]["payee"],
                    u["verwendungszweck"], ref)
            abgleich[uid] = {"ergebnis": "zur_pruefung", "grund": "aehnlich", "kandidaten": [ref]}
        elif art == "mehrdeutig_kmy_doppelt":
            refs = [f"k-{uid}-a", f"k-{uid}-b"]
            for ref in refs:
                einfach(u["buchungstag"], konto, kat, u["betrag"], m["kmy"]["payee"], u["verwendungszweck"], ref)
            abgleich[uid] = {"ergebnis": "zur_pruefung", "grund": "mehrdeutig", "kandidaten": refs}
        elif art == "mehrdeutig_bank_doppelt":
            gruppe = m["kmy"]["gruppe"]
            ref = f"k-gruppe-{gruppe}"
            if gruppe not in gruppen:
                einfach(u["buchungstag"], konto, kat, u["betrag"], m["kmy"]["payee"], u["verwendungszweck"], ref)
            gruppen.setdefault(gruppe, []).append(uid)
            abgleich[uid] = {"ergebnis": "zur_pruefung", "grund": "mehrdeutig", "kandidaten": [ref]}
        elif art == "umbuchung":
            ref = f"k-{m['kmy']['umbuchung']}"
            if m["kmy"]["umbuchung"] not in umbuchungen:
                p = payee(INHABER)
                buchung(u["buchungstag"], [KSplit(G, -30000, memo="Sparrate", empfaenger=p),
                                           KSplit(S, 30000, memo="Sparrate", empfaenger=p)], "Sparrate", ref, None,
                        umbuchung=True)
            umbuchungen.setdefault(m["kmy"]["umbuchung"], []).append(uid)
            abgleich[uid] = {"ergebnis": "zusammengefuehrt", "mit": [ref]}
        else:  # pragma: no cover
            raise AssertionError(art)

    # IDs nach Datum vergeben; Referenzen auf KMyMoney-Transaktions-IDs abbilden
    b.empfaenger = [(pid, name) for name, pid in payees.items()]
    b.tags = []
    ref_zu_tid: dict[str, str] = {}
    b.buchungen = []
    for n, (_, _, kw) in enumerate(sorted(roh, key=lambda r: (r[0], r[1])), start=1):
        tid = f"T{n:018d}"
        ref_zu_tid[kw["ref"]] = tid
        kat = kw["kategorie"]
        b.buchungen.append(KBuchung(id=tid, datum=kw["datum"], splits=kw["splits"], memo=kw["memo"],
                                    wahre_kategorie=kat_ids[kat][0] if kat else None, umbuchung=kw["umbuchung"]))
    for e in abgleich.values():
        for feld in ("mit", "kandidaten"):
            if feld in e:
                e[feld] = sorted(ref_zu_tid[r] for r in e[feld])
    return b, abgleich
