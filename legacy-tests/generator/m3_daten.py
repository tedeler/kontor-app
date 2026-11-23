"""Testdaten für Meilenstein 3: Umbuchungen, Abstimmung, Empfänger-Aliase, Volltextsuche.

Erzeugt (alles synthetisch, fester Startwert):

- ``mock/m3_daten.json``: Mock-Datendatei (``kontor-mock-daten`` Version 1)
  mit drei Bankkonten (Giro, Tagesgeld, Kreditkarte) und Umsätzen von Januar
  bis Juni 2024. Gezielt eingebaut: Umbuchungen mit gleichem Tag, 2 und 3
  Tagen Abstand (zusammenzuführen), 4 Tagen Abstand (nicht), über eine
  Stufengrenze (nachträglich), gleicher Betrag an fremde IBAN, mehrdeutige
  Seiten, widersprechende und fehlende Gegen-IBAN; Empfängernamen in
  mehreren Schreibweisen (Groß/klein, Umlaut ausgeschrieben, Akzent, zerlegte
  Umlaute in NFD, Rechtsform), ß/ss, Ligatur, Vormerkung.
- ``m3/stammdaten.json``: Kategorien, Empfänger mit Aliasen und
  Standardkategorien, ein kleiner Regelsatz.
- ``kmy/m3_aliase.kmy``: kleines KMyMoney-Buch, dessen Empfänger nach dem
  Anlegen der Stammdaten über Aliase zugeordnet werden.
- ``m3/suche.json``: Suchanfragen mit erwarteten Treffern für den Zustand
  „nur synchronisiert“ (ohne Stammdaten, Regeln, Umbuchungserkennung).
- ``mock/m3_daten.erwartung.json``: bekannte Wahrheit (Umbuchungspaare je
  Stufe, Gründe der Nicht-Zusammenführung, Empfänger- und Kategoriezuordnung
  mit Stammdaten, Kontoauszüge für die Abstimmung).

Die Wahrheit wird je Fall von Hand festgelegt und mit einer
Kontrollrechnung nach ``spec/api/buchhaltungspflege.md`` abgeglichen;
``tests/generator/test_m3_daten.py`` prüft sie zusätzlich mit einem
unabhängigen Orakel (``tests/hilfen/m3_orakel.py``).
"""

from __future__ import annotations

import datetime as dt
import random
import re
import unicodedata

from .iban import fiktive_iban
from .kmy import KBuch, KBuchung, KKonto, KSplit

GIRO = fiktive_iban(9001)
SPAR = fiktive_iban(9002)
KREDIT = fiktive_iban(9003)
FREMD = fiktive_iban(9999)
INHABER = "Erika Mustermann (fiktiv)"
KARTE = "Testbank Kartenservice (fiktiv)"
STUFEN = ["2024-02-29", "2024-04-30", "2024-06-30"]
VON = "2024-01-01"
FENSTER = 3
KONTO_NAMEN = {GIRO: "Girokonto", SPAR: "Tagesgeld", KREDIT: "Kreditkarte"}

NFD_BAECKER = unicodedata.normalize("NFD", "Bäckerei Müller")
assert NFD_BAECKER != "Bäckerei Müller"

KATEGORIEN = [("Gehalt", "ertrag"), ("Zinsertrag", "ertrag"), ("Miete", "aufwand"), ("Strom", "aufwand"),
              ("Lebensmittel", "aufwand"), ("Café & Restaurant", "aufwand"), ("Freizeit", "aufwand"),
              ("Abos", "aufwand"), ("Sonstiges", "aufwand")]

STAMM_EMPFAENGER = [
    {"name": "Stadtwerke Musterstadt", "aliase": ["STADTWERKE MUSTERSTADT GMBH", "SWM Energie"],
     "standardkategorie": "Strom"},
    {"name": "Bäckerei Müller", "aliase": ["Baeckerei Mueller"], "standardkategorie": "Lebensmittel"},
    {"name": "Café Bohne", "aliase": ["Cafe Bohne", "CAFÉ BOHNE"], "standardkategorie": None},
    {"name": "Supermarkt Frischekorb", "aliase": [], "standardkategorie": "Lebensmittel"},
]
STAMM_REGELN = [
    {"name": "Nachzahlung", "aktiv": True, "prioritaet": 10, "kategorie": "Sonstiges",
     "bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": "nachzahlung"}]},
    {"name": "Café", "aktiv": True, "prioritaet": 20, "kategorie": "Café & Restaurant",
     "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "café bohne"}]},
    {"name": "Streaming", "aktiv": True, "prioritaet": 30, "kategorie": "Abos",
     "bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": "abo"}]},
]


# ------------------------------------------------------------ Normalisierung
def norm(s: str) -> str:
    return s.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def ekey(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


def snorm(s: str) -> str:
    t = unicodedata.normalize("NFKD", norm(unicodedata.normalize("NFC", s)))
    return "".join(z for z in t if unicodedata.category(z) != "Mn")


def m3_daten(startwert: int) -> dict[str, object]:
    rng = random.Random(startwert + 3)
    umsaetze: list[dict] = []
    meta: dict[str, dict] = {}
    benutzt: set[int] = set()
    zaehler = [0]

    def einzig(lo: int, hi: int) -> int:
        """Betrag, dessen Absolutwert sonst nirgends vorkommt (keine zufälligen Umbuchungspaare)."""
        while True:
            b = rng.randint(lo, hi)
            if b not in benutzt:
                benutzt.add(b)
                return b

    def neu(iban, tag, betrag, name, gegen, zweck, fall, *, kategorie=None, vormerkung=False, paar=None) -> str:
        zaehler[0] += 1
        uid = f"M-{zaehler[0]:05d}"
        benutzt.add(abs(betrag))
        umsaetze.append({
            "umsatz_id": uid, "iban": iban, "buchungstag": tag.isoformat(),
            "valuta": None if vormerkung else tag.isoformat(), "betrag": betrag, "waehrung": "EUR",
            "gegenpartei_name": name, "gegenpartei_iban": gegen, "verwendungszweck": zweck,
            "vormerkung": vormerkung, "storno": False,
        })
        meta[uid] = {"fall": fall, "kategorie": kategorie, "paar": paar}
        return uid

    D = dt.date
    for b in (25000, 335000, 98000, 11111, 12121, 13131, 20000, 5000, 7777, 3030, 1299, 1234, 1301, 4040):
        benutzt.add(b)

    # ------------------------------------------------------ Monatsmuster
    stadtwerke = ["Stadtwerke Musterstadt", "STADTWERKE MUSTERSTADT GMBH", "Stadtwerke Musterstadt GmbH",
                  "SWM Energie", "Stadtwerke Musterstadt", "  stadtwerke musterstadt gmbh  "]
    baecker = ["Bäckerei Müller", "BAECKEREI MUELLER", NFD_BAECKER, "Bäckerei Müller", "Baeckerei Mueller",
               "BÄCKEREI MÜLLER"]
    cafe = ["Café Bohne", "Cafe Bohne", "CAFÉ BOHNE", "Café Bohne", "cafe bohne", "Café Bohne"]
    for m in range(1, 7):
        neu(GIRO, D(2024, m, 1), -25000, INHABER, SPAR, f"Sparrate {m:02d}/2024", "umbuchung_gleicher_tag",
            paar=f"spar-{m}")
        neu(SPAR, D(2024, m, 1), 25000, INHABER, GIRO, f"Sparrate {m:02d}/2024", "umbuchung_gleicher_tag",
            paar=f"spar-{m}")
        neu(GIRO, D(2024, m, 3), -98000, "Wohnbau Beispiel eG", FREMD, f"Miete {m:02d}/2024", "miete",
            kategorie="Miete")
        zweck = "Nachzahlung Strom 2023" if m == 2 else "Abschlag Strom"
        neu(GIRO, D(2024, m, 6), -einzig(8000, 9900), stadtwerke[m - 1], FREMD, zweck, "strom",
            kategorie="Sonstiges" if m == 2 else "Strom")
        neu(GIRO, D(2024, m, 9), -einzig(300, 1200), baecker[m - 1], None, "Brötchen", "baecker",
            kategorie="Lebensmittel")
        neu(GIRO, D(2024, m, 12), -einzig(300, 1500), cafe[m - 1], None, "Kartenzahlung Café", "cafe",
            kategorie="Café & Restaurant")
        if m <= 5:
            # Kreditkartenausgleich: Kreditkartenseite ohne Gegen-IBAN, zwei Tage später
            x = einzig(20000, 60000)
            neu(GIRO, D(2024, m, 15), -x, KARTE, KREDIT, f"Kreditkarte Ausgleich {m:02d}/2024",
                "umbuchung_kredit_ohne_iban", paar=f"kredit-{m}")
            neu(KREDIT, D(2024, m, 17), x, KARTE, None, f"Ausgleich {m:02d}/2024", "umbuchung_kredit_ohne_iban",
                paar=f"kredit-{m}")
        for _ in range(2):
            neu(GIRO, D(2024, m, rng.randint(1, 27)), -einzig(1500, 9000), "Supermarkt Frischekorb", None,
                f"Kartenzahlung {rng.randint(100, 999)}", "super", kategorie="Lebensmittel")
        neu(GIRO, D(2024, m, 28), 335000, "Arbeitgeber Muster GmbH", FREMD, f"LOHN/GEHALT {m:02d}/2024",
            "gehalt", kategorie="Gehalt")
        neu(KREDIT, D(2024, m, 10), -1299, "Streamio", None, "Abo Streamingdienst", "abo", kategorie="Abos")

    # --------------------------------------------------------- Einzelfälle
    neu(GIRO, D(2024, 3, 8), -11111, INHABER, SPAR, "Umbuchung Rücklage", "umbuchung_3_tage", paar="drei")
    neu(SPAR, D(2024, 3, 11), 11111, INHABER, GIRO, "Umbuchung Rücklage", "umbuchung_3_tage", paar="drei")
    neu(GIRO, D(2024, 3, 20), -12121, INHABER, SPAR, "Umbuchung Urlaub", "umbuchung_4_tage")
    neu(SPAR, D(2024, 3, 24), 12121, INHABER, GIRO, "Umbuchung Urlaub", "umbuchung_4_tage")
    neu(GIRO, D(2024, 4, 29), -13131, INHABER, SPAR, "Umbuchung Monatsende", "umbuchung_stufengrenze",
        paar="grenze")
    neu(SPAR, D(2024, 5, 2), 13131, INHABER, GIRO, "Umbuchung Monatsende", "umbuchung_stufengrenze",
        paar="grenze")
    neu(GIRO, D(2024, 2, 10), -20000, INHABER, SPAR, "Umbuchung Februar", "umbuchung_neben_fremd", paar="fremd")
    neu(SPAR, D(2024, 2, 10), 20000, INHABER, GIRO, "Umbuchung Februar", "umbuchung_neben_fremd", paar="fremd")
    neu(GIRO, D(2024, 2, 10), -20000, "Fremde Person (fiktiv)", FREMD, "Darlehen privat", "fremde_iban",
        kategorie="Sonstiges")
    neu(GIRO, D(2024, 5, 20), -5000, INHABER, SPAR, "Dauerauftrag A", "umbuchung_mehrdeutig")
    neu(GIRO, D(2024, 5, 20), -5000, INHABER, SPAR, "Dauerauftrag B", "umbuchung_mehrdeutig")
    neu(SPAR, D(2024, 5, 20), 5000, INHABER, GIRO, "Dauerauftrag", "umbuchung_mehrdeutig")
    neu(GIRO, D(2024, 6, 5), -7777, INHABER, KREDIT, "Umbuchung falsche IBAN", "umbuchung_iban_widerspruch")
    neu(SPAR, D(2024, 6, 5), 7777, INHABER, GIRO, "Umbuchung falsche IBAN", "umbuchung_iban_widerspruch")
    neu(GIRO, D(2024, 6, 12), -3030, INHABER, None, "Übertrag ohne IBAN", "umbuchung_ohne_iban")
    neu(SPAR, D(2024, 6, 12), 3030, INHABER, None, "Übertrag ohne IBAN", "umbuchung_ohne_iban")
    neu(SPAR, D(2024, 3, 28), 1234, "Testbank (fiktiv)", None, "Zinsen 1. Quartal 2024", "zinsen",
        kategorie="Zinsertrag")
    neu(SPAR, D(2024, 6, 28), 1301, "Testbank (fiktiv)", None, "Zinsen 2. Quartal 2024", "zinsen",
        kategorie="Zinsertrag")
    neu(GIRO, D(2024, 4, 18), -einzig(2000, 6000), "Möbelhaus Groß & Söhne", None,
        "Lieferung Hauptstraße 5, Musterstadt", "strasse", kategorie="Sonstiges")
    neu(GIRO, D(2024, 5, 24), -einzig(1000, 3000), "Kino am Markt", None, "Kinoﬁlm Abend (2 Karten)",
        "ligatur", kategorie="Freizeit")
    neu(KREDIT, D(2024, 6, 14), -einzig(1000, 3000), "MUSIKSCHULE STRASSER", None, "Gitarrenkurs Juni",
        "strasse", kategorie="Freizeit")
    neu(GIRO, D(2024, 6, 29), -4040, "Supermarkt Frischekorb", None, "Vorgemerkt: Einkauf", "vormerkung",
        kategorie="Lebensmittel", vormerkung=True)

    umsaetze.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    gebucht = [u for u in umsaetze if not u["vormerkung"]]

    # ---------------------------------------------------- Umbuchungen
    stufen_paare, endstand = _umbuchungen_simulieren(gebucht, FENSTER)
    paare_soll = {}
    for uid, m in meta.items():
        if m["paar"]:
            paare_soll.setdefault(m["paar"], []).append(uid)
    soll = {tuple(sorted(v)) for v in paare_soll.values()}
    ist = {tuple(sorted((p["behalten"], p["entfernt"]))) for p in endstand}
    assert soll == ist, (soll ^ ist)
    gruende = {
        "umbuchung_4_tage": "zeitfenster", "umbuchung_mehrdeutig": "mehrdeutig",
        "umbuchung_iban_widerspruch": "iban", "umbuchung_ohne_iban": "iban", "fremde_iban": "iban",
    }
    in_paar = {u for p in endstand for u in (p["behalten"], p["entfernt"])}
    nicht = {uid: gruende[m["fall"]] for uid, m in meta.items() if m["fall"] in gruende}
    assert not (set(nicht) & in_paar)
    grenze = next(p for p in endstand if meta[p["behalten"]]["paar"] == "grenze")
    assert grenze in stufen_paare[2] and all(grenze != p for p in stufen_paare[1])

    # ------------------------------------------------- Stammdaten-Wahrheit
    stamm = _stammdaten_wahrheit(umsaetze)
    for uid, w in stamm.items():
        if meta[uid]["kategorie"] is not None and w["kategorie"] is not None:
            assert w["kategorie"] == meta[uid]["kategorie"], (uid, w, meta[uid])

    # ------------------------------------------------------- Abstimmung
    auszuege = []
    for iban in (GIRO, SPAR, KREDIT):
        for m in range(1, 7):
            ende = (D(2024, m + 1, 1) - dt.timedelta(days=1)) if m < 12 else D(2024, 12, 31)
            saldo = sum(u["betrag"] for u in gebucht if u["iban"] == iban and u["buchungstag"] <= ende.isoformat())
            anzahl = sum(1 for u in gebucht if u["iban"] == iban
                         and (D(2024, m, 1).isoformat() <= u["buchungstag"] <= ende.isoformat()))
            auszuege.append({"iban": iban, "stichtag": ende.isoformat(), "saldo": saldo, "neue_splits": anzahl})
    falsch = [{"iban": GIRO, "stichtag": "2024-03-31", "saldo": next(
        a["saldo"] for a in auszuege if a["iban"] == GIRO and a["stichtag"] == "2024-03-31") - 1, "differenz": -1},
        {"iban": KREDIT, "stichtag": "2024-02-29", "saldo": next(
            a["saldo"] for a in auszuege if a["iban"] == KREDIT and a["stichtag"] == "2024-02-29") + 250,
         "differenz": 250}]

    # ----------------------------------------------------------- Suche
    suche = _suche(gebucht)

    bank = {
        "konten": [
            {"iban": GIRO, "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto", "inhaber": INHABER,
             "waehrung": "EUR"},
            {"iban": SPAR, "bic": "TESTDEFFXXX", "name": "Tagesgeld", "art": "sparkonto", "inhaber": INHABER,
             "waehrung": "EUR"},
            {"iban": KREDIT, "bic": None, "name": "Kreditkarte", "art": "kreditkonto", "inhaber": INHABER,
             "waehrung": "EUR"},
        ],
        "umsaetze": umsaetze,
    }
    mail = {"postfaecher": ["m3.eins@example.invalid"], "nachrichten": []}
    daten = {"format": "kontor-mock-daten", "version": 1, "bank": bank, "mail": mail}

    stammdaten = {
        "beschreibung": "Stammdaten für Meilenstein 3 (buchhaltungspflege.md 2): zuerst Kategorien anlegen, dann "
                        "Empfänger mit Aliasen und Standardkategorie (Name der Kategorie → ID), dann Regeln in "
                        "Listenreihenfolge.",
        "kategorien": [{"name": n, "art": a} for n, a in KATEGORIEN],
        "empfaenger": STAMM_EMPFAENGER,
        "regeln": STAMM_REGELN,
    }

    erwartung = {
        "fixture": "mock/m3_daten.json",
        "von": VON,
        "stufen": STUFEN,
        "fenster_tage": FENSTER,
        "ibans": {"giro": GIRO, "spar": SPAR, "kredit": KREDIT, "fremd": FREMD},
        "iban_reihenfolge": sorted([GIRO, SPAR, KREDIT]),
        "konto_namen": KONTO_NAMEN,
        "fall": {u["umsatz_id"]: meta[u["umsatz_id"]]["fall"] for u in umsaetze},
        "wahre_kategorie": {u["umsatz_id"]: meta[u["umsatz_id"]]["kategorie"] for u in umsaetze},
        "vormerkungen": [u["umsatz_id"] for u in umsaetze if u["vormerkung"]],
        "umbuchungen": {
            "endstand": endstand,
            "je_stufe": stufen_paare,
            "nicht_zusammengefuehrt": nicht,
        },
        "stammdaten": stamm,
        "auszuege": auszuege,
        "auszuege_falsch": falsch,
        "anzahl_gebucht": {i: sum(u["iban"] == i for u in gebucht) for i in (GIRO, SPAR, KREDIT)},
        "saldo": {i: sum(u["betrag"] for u in gebucht if u["iban"] == i) for i in (GIRO, SPAR, KREDIT)},
        "nfd_name": NFD_BAECKER,
    }
    return {"daten": daten, "erwartung": erwartung, "stammdaten": stammdaten, "suche": suche,
            "kbuch": _alias_buch(), "kbuch_erwartung": _alias_buch_erwartung()}


def _passen(x: dict, y: dict, fenster: int) -> bool:
    if x["iban"] == y["iban"] or x["betrag"] != -y["betrag"] or x["betrag"] == 0:
        return False
    if abs((dt.date.fromisoformat(x["buchungstag"]) - dt.date.fromisoformat(y["buchungstag"])).days) > fenster:
        return False
    gx, gy = x["gegenpartei_iban"], y["gegenpartei_iban"]
    if (gx is not None and gx != y["iban"]) or (gy is not None and gy != x["iban"]):
        return False
    return gx == y["iban"] or gy == x["iban"]


def _umbuchungen_simulieren(gebucht: list[dict], fenster: int) -> tuple[list[list[dict]], list[dict]]:
    """Kontrollrechnung nach buchhaltungspflege.md 4.3/4.4 für Abrufe Stufe für Stufe.

    Alle Buchungen sind Kandidaten (ohne Regeln und Stammdaten landet jeder Umsatz auf
    „Unkategorisiert“); Buchungs-IDs steigen in Verarbeitungsreihenfolge.
    """
    reihenfolge = sorted({u["iban"] for u in gebucht})
    kandidaten: list[dict] = []  # Umsätze in ID-Reihenfolge
    stufen_paare: list[list[dict]] = []
    alle: list[dict] = []
    vorher = "0000-00-00"
    for stufe in STUFEN:
        diese: list[dict] = []
        for iban in reihenfolge:
            neue = [u for u in gebucht if u["iban"] == iban and vorher < u["buchungstag"] <= stufe]
            kandidaten.extend(neue)
            if not neue:
                continue
            p = {u["umsatz_id"]: [v for v in kandidaten if v is not u and _passen(u, v, fenster)] for u in kandidaten}
            neu_ids = {u["umsatz_id"] for u in neue}
            weg = set()
            for u in kandidaten:
                if len(p[u["umsatz_id"]]) != 1:
                    continue
                v = p[u["umsatz_id"]][0]
                if [w["umsatz_id"] for w in p[v["umsatz_id"]]] != [u["umsatz_id"]]:
                    continue
                if kandidaten.index(u) > kandidaten.index(v):
                    continue
                if not ({u["umsatz_id"], v["umsatz_id"]} & neu_ids):
                    continue
                diese.append({"behalten": u["umsatz_id"], "entfernt": v["umsatz_id"]})
                weg |= {u["umsatz_id"], v["umsatz_id"]}
            kandidaten = [u for u in kandidaten if u["umsatz_id"] not in weg]
        stufen_paare.append(diese)
        alle.extend(diese)
        vorher = stufe
    return stufen_paare, alle


def _stammdaten_wahrheit(umsaetze: list[dict]) -> dict[str, dict]:
    """Empfänger und Kategorie je gebuchtem Umsatz nach Anlegen der Stammdaten (buchhaltungspflege.md 2.3/2.5)."""
    exakt = {e["name"]: e for e in STAMM_EMPFAENGER}
    alias = {ekey(a): e for e in STAMM_EMPFAENGER for a in e["aliase"]}
    aus = {}
    for u in umsaetze:
        if u["vormerkung"]:
            continue
        n = (u["gegenpartei_name"] or "").strip() or None
        e = None
        if n is not None:
            e = exakt.get(n) or alias.get(ekey(n))
        name = e["name"] if e else n
        regel = None
        for r in sorted(STAMM_REGELN, key=lambda r: r["prioritaet"]):
            ok = True
            for b in r["bedingungen"]:
                x = name if b["feld"] == "empfaenger" else u["verwendungszweck"]
                if x is None:
                    ok = False
                    break
                nx, nw = norm(x), norm(b["wert"])
                ok = {"enthaelt": nw in nx, "gleich": nx == nw, "beginnt_mit": nx.startswith(nw)}[b["operator"]]
                if not ok:
                    break
            if ok:
                regel = r
                break
        if regel:
            kat, quelle = regel["kategorie"], "regel"
        elif e and e["standardkategorie"]:
            kat, quelle = e["standardkategorie"], "standardkategorie"
        else:
            kat, quelle = None, None
        aus[u["umsatz_id"]] = {"empfaenger": name, "stamm_empfaenger": e["name"] if e else None,
                               "kategorie": kat, "quelle": quelle, "regel": regel["name"] if regel else None}
    return aus


SUCHANFRAGEN = ["bäckerei", "BAECKEREI müller", "cafe", "café bohne", "strasse", "STRAßE", "tagesgeld zins",
                "Miete 03", "kinofilm", "mustermann umbuchung", "kreditkarte abo", "gibtsnicht", "groß söhne",
                "  sparrate   02/2024 "]


def _suche(gebucht: list[dict]) -> dict:
    """Erwartete Treffer für den Zustand „nur synchronisiert“ (buchhaltungspflege.md 6)."""
    def felder(u: dict) -> list[str]:
        f = [u["verwendungszweck"], KONTO_NAMEN[u["iban"]], "Unkategorisiert"]
        n = (u["gegenpartei_name"] or "").strip()
        if n:
            f.append(n)
        return f

    empfaenger = sorted({(u["gegenpartei_name"] or "").strip() for u in gebucht} - {""})
    anfragen = []
    for q in SUCHANFRAGEN:
        woerter = [snorm(w) for w in q.split()]

        def trifft(fs: list[str]) -> bool:
            return all(any(w in snorm(f) for f in fs) for w in woerter)

        treffer = sorted((u for u in gebucht if trifft(felder(u))),
                         key=lambda u: (u["buchungstag"], u["umsatz_id"]), reverse=True)
        anfragen.append({
            "q": q,
            "buchungen": [u["umsatz_id"] for u in treffer],
            "empfaenger": sorted(e for e in empfaenger if trifft([e])),
            "konten": sorted(n for n in list(KONTO_NAMEN.values()) + ["Unkategorisiert"] if trifft([n])),
        })
    return {"beschreibung": "Suchanfragen gegen den Zustand nach einem Abruf von mock/m3_daten.json "
                            "(von 2024-01-01 bis 2024-06-30) ohne Stammdaten, Regeln und Umbuchungserkennung. "
                            "buchungen: Umsatz-IDs der Treffer, nach buchungstag absteigend (die Reihenfolge bei "
                            "gleichem Datum ergibt sich aus den Buchungs-IDs und wird im Test geprüft); "
                            "empfaenger, konten: Namen der Treffer, aufsteigend.",
            "anfragen": anfragen}


def _alias_buch() -> KBuch:
    b = KBuch(erstellt="2024-01-01", geaendert="2024-03-01")
    G = "A000001"
    b.konten = [
        KKonto(G, "Girokonto", 1, "AStd::Asset", eroeffnet="2024-01-01", iban=GIRO),
        KKonto("A000002", "Strom", 13, "AStd::Expense"),
        KKonto("A000003", "Lebensmittel", 13, "AStd::Expense"),
        KKonto("A000004", "Anfangsbestand", 16, "AStd::Equity"),
    ]
    b.empfaenger = [("P000001", "STADTWERKE MUSTERSTADT GMBH"), ("P000002", "Supermarkt Frischekorb"),
                    ("P000003", "Neuer Laden (fiktiv)"), ("P000004", "baeckerei mueller")]
    b.tags = []
    b.buchungen = [
        KBuchung("T000000000000000001", "2023-12-01", [KSplit(G, 100000, memo="Anfangsbestand"),
                                                       KSplit("A000004", -100000)], memo="Anfangsbestand"),
        KBuchung("T000000000000000002", "2023-12-06", [KSplit(G, -8800, empfaenger="P000001"),
                                                       KSplit("A000002", 8800, empfaenger="P000001")],
                 memo="Abschlag Strom 12/2023", wahre_kategorie="A000002"),
        KBuchung("T000000000000000003", "2023-12-09", [KSplit(G, -2345, empfaenger="P000002"),
                                                       KSplit("A000003", 2345, empfaenger="P000002")],
                 memo="Kartenzahlung", wahre_kategorie="A000003"),
        KBuchung("T000000000000000004", "2023-12-11", [KSplit(G, -1999, empfaenger="P000003"),
                                                       KSplit("A000003", 1999, empfaenger="P000003")],
                 memo="Einkauf", wahre_kategorie="A000003"),
        KBuchung("T000000000000000005", "2023-12-12", [KSplit(G, -480, empfaenger="P000004"),
                                                       KSplit("A000003", 480, empfaenger="P000004")],
                 memo="Brötchen", wahre_kategorie="A000003"),
    ]
    return b


def _alias_buch_erwartung() -> dict:
    """Zuordnung der KMyMoney-Empfänger, nachdem die Stammdaten-Empfänger angelegt sind (2.3)."""
    return {
        "P000001": {"empfaenger": "Stadtwerke Musterstadt", "regel": "alias"},
        "P000002": {"empfaenger": "Supermarkt Frischekorb", "regel": "name"},
        "P000003": {"empfaenger": "Neuer Laden (fiktiv)", "regel": "neu"},
        "P000004": {"empfaenger": "Bäckerei Müller", "regel": "alias"},
    }
