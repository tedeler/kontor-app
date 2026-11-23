"""Großer Datensatz für die Leistungstests von Meilenstein 7 (``spec/api/leistung.md`` 1).

Genau 50 000 Buchungen 2019–2024 als KMyMoney-Datei. Der Datensatz wird nur auf Abruf erzeugt
(``python -m generator --gross``), nicht eingecheckt (E-134); ``fixtures/MANIFEST.json`` enthält unter
``auf_abruf`` die SHA-256 der erzeugten Dateien. Die Erwartung ist eine kompakte Zusammenfassung der
bekannten Wahrheit (``kmy.erwartung``) plus Probewerte für Filter.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import Counter

from .iban import fiktive_iban
from .kmy import KBuch, KKonto, KSplit, als_xml, erwartung, packe_gzip
from .szenarien import _Sammler

ANZAHL = 50_000
BEGINN = dt.date(2019, 1, 1)
ENDE = dt.date(2024, 12, 31)
ZEBRA = "ZEBRA4711"
ZEBRA_ANZAHL = 250
PROBE_EMPFAENGER = "Leistungsprobe Ölmühle GmbH"
PROBE_ANZAHL = 500

G1, G2, TG, KK, EK = "A000001", "A000002", "A000003", "A000004", "A000009"
BESTAND = (G1, G2, TG, KK)

_OBER = ["Lebensmittel", "Wohnen", "Mobilität", "Versicherungen", "Freizeit", "Gesundheit", "Kleidung",
         "Bildung", "Haushalt"]
_UNTER = ["Grundbedarf", "Spezialitäten", "Abos", "Reparaturen", "Sonstiges"]
_STAMM = ["Müller", "Bäcker", "Grün", "Süd", "Nord", "Öko", "Fluss", "Berg", "Wald", "Stern", "Licht",
          "Hafen", "Brücke", "Garten", "Mühle", "Quelle", "Feld", "Insel", "Turm", "Tal"]
_ART = ["Markt", "Laden", "Werkstatt", "Dienst", "Handel", "Studio", "Kontor", "Haus", "Center", "Shop"]
_FORM = ["GmbH", "KG", "e. K.", "AG"]
_WOERTER = ["Einkauf", "Rechnung", "Beitrag", "Abschlag", "Bestellung", "Kartenzahlung", "Lastschrift",
            "Gebühr", "Erstattung", "Überweisung", "Wocheneinkauf", "Reparatur"]


def _tag(rng: random.Random) -> dt.date:
    return BEGINN + dt.timedelta(days=rng.randrange((ENDE - BEGINN).days + 1))


def gross_buch(startwert: int) -> tuple[KBuch, dict]:
    """Liefert das Buch und die Probewerte (Merkmale, die die Tests als Filter verwenden)."""
    rng = random.Random(startwert * 7 + 7)
    b = KBuch(erstellt="2018-12-31", geaendert="2025-01-02")
    b.konten = [
        KKonto(G1, "Girokonto Haushalt", 1, "AStd::Asset", eroeffnet="2018-01-01", iban=fiktive_iban(7001),
               nummer="7001"),
        KKonto(G2, "Girokonto Partner", 1, "AStd::Asset", eroeffnet="2018-01-01", iban=fiktive_iban(7002),
               nummer="7002"),
        KKonto(TG, "Tagesgeld", 2, "AStd::Asset", eroeffnet="2018-01-01", iban=fiktive_iban(7003), nummer="7003"),
        KKonto(KK, "Kreditkarte", 4, "AStd::Liability", eroeffnet="2018-01-01"),
        KKonto(EK, "Anfangsbestand", 16, "AStd::Equity"),
    ]
    n = 100
    kategorien: list[str] = []  # Unterkategorien (Aufwand)
    ober_von: dict[str, str] = {}
    for name in _OBER:
        n += 1
        oid = f"A{n:06d}"
        b.konten.append(KKonto(oid, name, 13, "AStd::Expense"))
        for u in _UNTER:
            n += 1
            kid = f"A{n:06d}"
            b.konten.append(KKonto(kid, f"{name} – {u}", 13, oid))
            kategorien.append(kid)
            ober_von[kid] = oid
    n += 1
    EINK = f"A{n:06d}"
    b.konten.append(KKonto(EINK, "Einkommen", 12, "AStd::Income"))
    ertrag = {}
    for u in ("Gehalt", "Nebenjob", "Erstattungen"):
        n += 1
        ertrag[u] = f"A{n:06d}"
        b.konten.append(KKonto(ertrag[u], u, 12, EINK))
    n += 1
    KAP = f"A{n:06d}"
    b.konten.append(KKonto(KAP, "Kapitalerträge", 12, "AStd::Income"))
    n += 1
    ertrag["Zinsen"] = f"A{n:06d}"
    b.konten.append(KKonto(ertrag["Zinsen"], "Zinsen", 12, KAP))

    # Empfänger: 399 erzeugte und der Probe-Empfänger, je mit fester Kategorie
    namen: list[str] = []
    gesehen: set[str] = set()
    while len(namen) < 399:
        name = f"{rng.choice(_STAMM)}{rng.choice(_ART).lower()} {rng.choice(_STAMM)} {rng.choice(_FORM)}"
        if name not in gesehen:
            gesehen.add(name)
            namen.append(name)
    namen.append(PROBE_EMPFAENGER)
    b.empfaenger = [(f"P{i + 1:06d}", name) for i, name in enumerate(namen)]
    probe_pid = b.empfaenger[-1][0]
    kat_von = {pid: rng.choice(kategorien) for pid, _ in b.empfaenger}
    kat_von[probe_pid] = kategorien[0]  # Lebensmittel – Grundbedarf
    b.tags = [(f"G{i + 1:06d}", t) for i, t in enumerate(
        ["Urlaub", "Steuer", "Geschenk", "Kinder", "Auto", "Garten", "Gesundheit", "Haus", "Reise", "Hobby",
         "Arbeit", "Größere Anschaffung"])]
    tag_ids = [t[0] for t in b.tags]

    s = _Sammler()
    zaehler = 0

    def neu(datum, splits, memo, *, umbuchung=False, kategorie=None):
        nonlocal zaehler
        zaehler += 1
        s.neu(datum, splits, memo=memo, umbuchung=umbuchung, wahre_kategorie=kategorie)

    # Anfangsbestände
    for konto, betrag in ((G1, 350_000), (G2, 180_000), (TG, 1_200_000), (KK, -45_000)):
        neu(BEGINN, [KSplit(konto, betrag, memo="Anfangsbestand"), KSplit(EK, -betrag)], "Anfangsbestand")
    # Gehälter und Zinsen
    monat = BEGINN
    while monat <= ENDE:
        tag = monat.replace(day=28)
        for konto, betrag, pid in ((G1, 412_000, b.empfaenger[0][0]), (G2, 354_000, b.empfaenger[1][0])):
            neu(tag, [KSplit(konto, betrag, memo=f"Gehalt {tag:%m/%Y}", empfaenger=pid),
                      KSplit(ertrag["Gehalt"], -betrag, empfaenger=pid)], f"Gehalt {tag:%m/%Y}",
                kategorie=ertrag["Gehalt"])
        if monat.month % 3 == 0:
            z = rng.randrange(500, 3000)
            neu(tag, [KSplit(TG, z, memo="Zinsgutschrift"), KSplit(ertrag["Zinsen"], -z)], "Zinsgutschrift",
                kategorie=ertrag["Zinsen"])
        # Kreditkartenausgleich und Sparrate (Umbuchungen)
        for von, nach, betrag, text in ((G1, KK, rng.randrange(20_000, 90_000), "Kreditkartenabrechnung"),
                                        (G1, TG, 25_000, "Sparrate"), (G2, TG, 15_000, "Sparrate")):
            d = monat.replace(day=3)
            neu(d, [KSplit(von, -betrag, memo=text), KSplit(nach, betrag, memo=text)], text, umbuchung=True)
        monat = (monat.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    # weitere Umbuchungen bis gut 2 %
    while zaehler < 1_100:
        betrag = rng.randrange(1_000, 50_000)
        von, nach = rng.choice([(G1, G2), (G2, G1), (TG, G1), (G1, TG)])
        neu(_tag(rng), [KSplit(von, -betrag, memo="Umbuchung"), KSplit(nach, betrag, memo="Umbuchung")],
            "Umbuchung", umbuchung=True)
    # Splitbuchungen (gut 3 %)
    for _ in range(1_550):
        pid = rng.choice(b.empfaenger[:-1])[0]
        teile = rng.sample(kategorien, rng.choice((3, 3, 4)))
        betraege = [rng.randrange(200, 9_000) for _ in teile]
        konto = rng.choice((G1, G1, G2, KK))
        memo = f"Sammelkauf {rng.choice(_WOERTER)}"
        splits = [KSplit(konto, -sum(betraege), memo=memo, empfaenger=pid)]
        splits += [KSplit(k, w, memo=f"Teil {i + 1}", empfaenger=pid) for i, (k, w) in enumerate(zip(teile, betraege))]
        neu(_tag(rng), splits, memo)
    # Einzelbuchungen bis genau ANZAHL; Probe-Empfänger und ZEBRA gezielt verteilt
    rest = ANZAHL - zaehler
    probe_pos = set(rng.sample(range(rest), PROBE_ANZAHL))
    uebrig = [i for i in range(rest) if i not in probe_pos]
    zebra_pos = set(rng.sample(uebrig, ZEBRA_ANZAHL))
    for i in range(rest):
        pid = probe_pid if i in probe_pos else rng.choice(b.empfaenger[2:-1])[0]
        konto = rng.choices((G1, G2, KK), weights=(55, 25, 20))[0]
        betrag = -int(rng.lognormvariate(6.2, 0.9)) - 1
        betrag = max(betrag, -250_000)
        if i in zebra_pos:
            memo = f"Rechnung {ZEBRA} Nr. {i}"
        else:
            memo = f"{rng.choice(_WOERTER)} {rng.randrange(1, 10_000)}"
        tags = [rng.choice(tag_ids)] if rng.random() < 0.1 else []
        kat = kat_von[pid]
        neu(_tag(rng), [KSplit(konto, betrag, memo=memo, empfaenger=pid, tags=tags),
                        KSplit(kat, -betrag, empfaenger=pid)], memo, kategorie=kat)
    b.buchungen = s.buchungen()
    assert len(b.buchungen) == ANZAHL
    return b, {"probe_empfaenger": PROBE_EMPFAENGER, "zebra": ZEBRA, "ober_von": ober_von}


def erzeuge_gross(startwert: int) -> tuple[bytes, dict]:
    """Liefert (gzip-Bytes von gross.kmy, kompakte Erwartung)."""
    buch, info = gross_buch(startwert)
    datei = packe_gzip(als_xml(buch))
    e = erwartung(buch, fixture="gross/gross.kmy", format_="kmy-gzip")
    buchungen = e["buchungen"]
    konto_name = {k["extern_id"]: k["name"] for k in e["konten"]}
    eltern = {k["extern_id"]: k["eltern_extern_id"] for k in e["konten"]}

    def im_teilbaum(kid: str | None, wurzel: str) -> bool:
        while kid is not None:
            if kid == wurzel:
                return True
            kid = eltern.get(kid)
        return False

    lebensmittel = next(k["extern_id"] for k in e["konten"] if k["name"] == "Lebensmittel")
    giro = "kmy:" + G1
    urlaub = next(t["extern_id"] for t in e["tags"] if t["name"] == "Urlaub")
    jahr = "2023"
    betrag_min, betrag_max = 5_000, 20_000
    proben = {
        "konto": {"name": konto_name[giro],
                  "anzahl": sum(1 for x in buchungen if any(s["konto_extern_id"] == giro for s in x["splits"]))},
        "zeitraum": {"von": f"{jahr}-01-01", "bis": f"{jahr}-12-31",
                     "anzahl": sum(1 for x in buchungen if x["datum"].startswith(jahr))},
        "kategorie": {"name": "Lebensmittel", "anzahl": sum(
            1 for x in buchungen if any(im_teilbaum(s["konto_extern_id"], lebensmittel) for s in x["splits"]))},
        "empfaenger": {"name": PROBE_EMPFAENGER, "anzahl": sum(1 for x in buchungen
                                                                if x["empfaenger"] == PROBE_EMPFAENGER)},
        "zebra": {"text": ZEBRA.lower(), "anzahl": sum(1 for x in buchungen if ZEBRA in x["verwendungszweck"])},
        "betrag": {"min": betrag_min, "max": betrag_max,
                   "anzahl": sum(1 for x in buchungen if betrag_min <= x["umsatz"] <= betrag_max)},
        "tag": {"name": "Urlaub", "anzahl": sum(1 for x in buchungen if urlaub in x["tags"])},
        "kombination": {"konto": konto_name[giro], "von": f"{jahr}-01-01", "bis": f"{jahr}-12-31",
                        "suche": ZEBRA.lower(), "anzahl": sum(
                            1 for x in buchungen if x["datum"].startswith(jahr) and ZEBRA in x["verwendungszweck"]
                            and any(s["konto_extern_id"] == giro for s in x["splits"]))},
    }
    erw = {
        "fixture": "gross/gross.kmy",
        "startwert": startwert,
        "ergebnis": e["ergebnis"],
        "anzahl": {"buchungen": len(buchungen), "konten": len(e["konten"]), "empfaenger": len(e["empfaenger"]),
                   "tags": len(e["tags"]), "splits": sum(len(x["splits"]) for x in buchungen),
                   "umbuchungen": sum(1 for x in buchungen if x["umbuchung"])},
        "salden": {k["name"]: k["saldo"] for k in e["konten"] if not k["ist_kategorie"]},
        "summen": e["summen"],
        "warnungen": Counter(w["code"] for w in e["warnungen"]),
        "jahre": dict(sorted(Counter(x["datum"][:4] for x in buchungen).items())),
        "proben": proben,
    }
    return datei, erw
