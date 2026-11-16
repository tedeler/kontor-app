"""Synthetische Lerndaten nach echten Mustern deutscher Kontoauszüge (Feature `lernmodell-transparenz`).

Erzeugt reproduzierbar (fester Startwert) genau ``ANZAHL`` Buchungen eines Girokontos mit wechselnden
Verwendungszwecken (Uhrzeiten, Terminals, Bestell-, Kunden- und Mandatsnummern), wie sie Banken liefern.
Alle Namen, Nummern und IBANs sind erfunden bzw. Beispielwerte; keine echten Bank- oder Kartendaten.

Eingebaute Schwierigkeiten für das Lernmodell:

- eindeutige Empfänger (Miete, Gehalt, Abos, Versicherungen …),
- Sammelzahler, bei denen nur der Verwendungszweck die Kategorie verrät (PayPal: Händler im Zweck),
- Sammelzahler ohne Hinweis (Amazon: Bestellnummer ohne Artikel, Kategorie gemischt),
- gleiche Empfänger mit zwei Kategorien, unterscheidbar am Zweck (Tankstelle: Kraftstoff gegen Shop),
- Gutschriften desselben Empfängers (Pfand, Rücksendung, Steuererstattung),
- neue Empfänger erst in der Prüfzeit (ohne Vorgeschichte),
- Umbuchungen auf eigene Konten (Kreditkarte, Tagesgeld, Bausparvertrag) – keine Kategorie, kein Lernbeispiel,
- etwa 3 % falsch erfasste Kategorien (Bedienfehler; ``wahr`` hält die richtige).

Teilung wie lernmodell.md 6: die älteren 80 % (nach Datum) sind kategorisiert (Training), die neuesten 20 %
stehen auf „Unkategorisiert“ und sind die Prüfbuchungen.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import random
import string

ANZAHL = 3000
ENDE = dt.date(2026, 10, 31)
TEIL_TRAINING = 0.8
FEHLERQUOTE = 0.03
MONATE = ("JAN", "FEB", "MRZ", "APR", "MAI", "JUN", "JUL", "AUG", "SEP", "OKT", "NOV", "DEZ")

AUFWAND = ("Miete", "Lebensmittel", "Lieferdienst", "Kleidung", "Freizeit", "Bücher", "Elektronik", "Haushalt",
           "Drogerie", "Energie", "Versicherungen", "Telefon & Internet", "Abos", "Tanken", "Steuern & Abgaben",
           "Rundfunk", "Gesundheit", "Auto", "Reisen", "Sport", "Privat", "Blumen")
ERTRAG = ("Gehalt", "Kindergeld")
EIGENE = {"Kreditkarte": "kreditkonto", "Tagesgeld": "sparkonto", "Bausparvertrag": "sparkonto"}
KATEGORIEN = AUFWAND + ERTRAG


def _ziffern(rng, n):
    return "".join(rng.choice(string.digits) for _ in range(n))


def _alnum(rng, n):
    return "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def _zeit(rng, d, von=7, bis=21):
    return f"{d:%d.%m} {rng.randint(von, bis):02d}:{rng.randint(0, 59):02d}"


def _tage(rng, monat_start, anzahl_mittel):
    """Zufällige Tage eines Monats; Anzahl schwankt um den Mittelwert."""
    n = max(0, round(rng.gauss(anzahl_mittel, max(0.5, anzahl_mittel ** 0.5 / 1.5))))
    letzter = (monat_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return sorted(monat_start + dt.timedelta(days=rng.randint(0, letzter.day - 1)) for _ in range(n))


def _werktag(d):
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def _monat(rng, m: dt.date, aus: list) -> None:
    """Alle Buchungen eines Monats (Datum, Empfänger, Zweck, Betrag in Cent, Kategorie bzw. eigenes Konto)."""
    def neu(d, empf, zweck, betrag, kat):
        aus.append({"datum": d, "empfaenger": empf, "verwendungszweck": zweck, "betrag": betrag, "wahr": kat})

    jahr, mm = m.year, m.month
    miete = 115000 if (jahr, mm) >= (2025, 1) else 108000
    neu(_werktag(m), "Hausverwaltung Lindenhof GmbH",
        f"MIETE {MONATE[mm - 1]} {jahr} WHG 3.OG LINKS KD-NR 40711", -miete, "Miete")
    gehalt = rng.randint(338000, 345000) + (jahr - 2023) * 6000
    neu(_werktag(m.replace(day=27)) if mm != 12 else _werktag(m.replace(day=20)), "Muster Technik AG",
        f"LOHN/GEHALT {mm:02d}/{jahr} PERS-NR 00815", gehalt, "Gehalt")
    if mm == 11:
        neu(_werktag(m.replace(day=27)), "Muster Technik AG", f"WEIHNACHTSGELD {jahr} PERS-NR 00815",
            rng.randint(150000, 170000), "Gehalt")
    abschlag = {2023: 10500, 2024: 12400, 2025: 11800, 2026: 11800}.get(jahr, 10500)
    neu(_werktag(m.replace(day=5)), "Stadtwerke Beispielstadt",
        f"SEPA-LASTSCHRIFT ABSCHLAG STROM/GAS VERTR 7700123 MANDAT SW-000123 GLAEUBIGER-ID DE98ZZZ00000000001",
        -abschlag, "Energie")
    if mm == 3:
        neu(_werktag(m.replace(day=18)), "Stadtwerke Beispielstadt",
            f"JAHRESABRECHNUNG {jahr - 1} VERTR 7700123 GUTHABEN RG {_ziffern(rng, 10)}",
            rng.randint(3000, 25000), "Energie")
    neu(_werktag(m.replace(day=5)), "Allianz Versicherungs-AG",
        f"LASTSCHRIFT KFZ-HAFTPFLICHT VS-NR AS-4711-0815 FAELLIG 01.{mm:02d}.{jahr}", -4672, "Versicherungen")
    if mm == 1:
        neu(_werktag(m.replace(day=15)), "Allianz Versicherungs-AG",
            f"LASTSCHRIFT HAUSRAT VS-NR HR-2207-1133 JAHRESBEITRAG {jahr}", -rng.choice((11890, 12450)),
            "Versicherungen")
    neu(_werktag(m.replace(day=6)), "Telekom Deutschland GmbH",
        f"Kundenkonto 1234567890 RG {_ziffern(rng, 12)}/{mm:02d}.{jahr} MOBILFUNK", -rng.choice((3995, 3995, 4290)),
        "Telefon & Internet")
    neu(_werktag(m.replace(day=6)), "Telekom Deutschland GmbH",
        f"Kundenkonto 1234567890 RG {_ziffern(rng, 12)}/{mm:02d}.{jahr} MAGENTA ZUHAUSE M", -3995,
        "Telefon & Internet")
    neu(m.replace(day=7), "Netflix International B.V.", f"NETFLIX.COM MITGLIEDSCHAFT P{_ziffern(rng, 10)}",
        -1399 if jahr >= 2025 else -1299, "Abos")
    neu(m.replace(day=7), "Spotify AB", f"Spotify Premium Family P{_alnum(rng, 9)}", -1799, "Abos")
    neu(_werktag(m.replace(day=10)), "Barclays Bank Ireland PLC",
        f"KREDITKARTENABRECHNUNG {(m - dt.timedelta(days=1)):%m/%Y} KONTO ****4321", -rng.randint(15000, 70000),
        "Kreditkarte")
    neu(_werktag(m.replace(day=11)), "Bausparkasse Musterhaus", f"SPARRATE BSV 12345678 {mm:02d}/{jahr}", -10000,
        "Bausparvertrag")
    neu(_werktag(m.replace(day=3)), "Max Mustermann",
        f"Miete Garage {('Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember')[mm - 1]} Stellplatz 7",
        -6000, "Auto")
    neu(_werktag(m.replace(day=21)), "Fitnessstudio Kraftwerk",
        f"MITGLIEDSBEITRAG {(m + dt.timedelta(days=32)):%m/%Y} MITGL-NR 2207 MANDAT FK-2207", -2990, "Sport")
    neu(_werktag(m.replace(day=23)), "Familienkasse Beispielregion", f"KINDERGELD {mm:02d}/{jahr} KG-NR 123FK456789",
        25500 if jahr >= 2025 else 25000, "Kindergeld")
    if mm in (1, 4, 7, 10):
        neu(_werktag(m.replace(day=14)), "Rundfunk ARD ZDF DRadio",
            f"BEITRAGSNR 123 456 789 3 MONATE {mm:02d}-{mm + 2:02d}/{jahr}", -5508, "Rundfunk")
    if mm in (2, 5, 8, 11):
        q = (mm + 1) // 3
        neu(_werktag(m.replace(day=15)), "Stadtkasse Beispielstadt",
            f"GRUNDSTEUER Q{q}/{jahr} KASSENZEICHEN 5.5501.123456.7", -8740, "Steuern & Abgaben")
    if mm == 6:
        neu(_werktag(m.replace(day=13)), "Finanzamt Musterstadt",
            f"EINKOMMENSTEUER {jahr - 1} STNR 123/456/78901 ERSTATTUNG", rng.randint(30000, 120000),
            "Steuern & Abgaben")

    for d in _tage(rng, m, 8):
        neu(d, "REWE Markt GmbH", f"KARTENZAHLUNG {_zeit(rng, d)} REWE SAGT DANKE {_ziffern(rng, 4)} KARTE 1234",
            -rng.randint(800, 12000), "Lebensmittel")
    for d in _tage(rng, m, 1):
        neu(d, "REWE Markt GmbH", f"RUECKZAHLUNG PFAND KARTE 1234 {_zeit(rng, d)}", rng.randint(25, 600),
            "Lebensmittel")
    for d in _tage(rng, m, 4):
        neu(d, "EDEKA Neukauf Sommer", f"GIROCARD {_zeit(rng, d)} TERMINAL 6612{_ziffern(rng, 4)} KARTE 1234",
            -rng.randint(600, 9000), "Lebensmittel")
    for d in _tage(rng, m, 4):
        neu(d, "Lidl sagt Danke", f"KARTENZAHLUNG {_zeit(rng, d)} LIDL FIL {rng.choice(('0815', '0815', '1203'))} KARTE 1234",
            -rng.randint(700, 7000), "Lebensmittel")
    for d in _tage(rng, m, 8):
        neu(d, "Bäckerei Müller & Söhne", f"GIROCARD {_zeit(rng, d, 6, 12)} BAECKEREI MUELLER KARTE 1234",
            -rng.randint(250, 1600), "Lebensmittel")
    for d in _tage(rng, m, 3):
        neu(d, "dm-drogerie markt", f"GIROCARD {_zeit(rng, d)} DM FIL {rng.choice(('1477', '1477', '0932'))} KARTE 1234",
            -rng.randint(300, 4500), "Drogerie")
    for d in _tage(rng, m, 3):
        neu(d, "Shell Station Hauptstr. 12",
            f"KARTENZAHLUNG {_zeit(rng, d)} TANKSTELLE {rng.choice(('SUPER E10', 'SUPER E10', 'SUPER E5'))} "
            f"{rng.randint(300, 550) // 10},{rng.randint(0, 9)}L", -rng.randint(5000, 9500), "Tanken")
    for d in _tage(rng, m, 1):
        neu(d, "Shell Station Hauptstr. 12", f"KARTENZAHLUNG {_zeit(rng, d)} TANKSTELLE SHOP", -rng.randint(250, 1800),
            "Lebensmittel")
    paypal = (("Lieferando", "Lieferdienst", 1800, 4500, 3), ("Zalando", "Kleidung", 2500, 12000, 1),
              ("Steam", "Freizeit", 500, 6000, 0.6), ("Thalia", "Bücher", 900, 3500, 0.5),
              ("MediaMarkt", "Elektronik", 1500, 30000, 0.4), ("eBay", "Haushalt", 800, 9000, 0.8))
    for haendler, kat, lo, hi, rate in paypal:
        for d in _tage(rng, m, rate):
            text = rng.choice((f", Ihr Einkauf bei {haendler}", f" {haendler}", f", Ihr Einkauf bei {haendler} GmbH"))
            neu(d, "PayPal Europe S.a.r.l. et Cie S.C.A", f"10{_ziffern(rng, 11)} PP.{_ziffern(rng, 4)}.PP .{text}",
                -rng.randint(lo, hi), kat)
    for d in _tage(rng, m, 4):
        kat = rng.choices(("Haushalt", "Elektronik", "Bücher", "Drogerie"), (40, 25, 20, 15))[0]
        neu(d, "Amazon Payments Europe S.C.A.",
            f"{rng.choice(('305', '028', '302'))}-{_ziffern(rng, 7)}-{_ziffern(rng, 7)} Amazon.de {_alnum(rng, 16)}",
            -rng.randint(800, 9000), kat)
    for d in _tage(rng, m, 0.5):
        kat = rng.choices(("Haushalt", "Elektronik", "Bücher", "Drogerie"), (40, 25, 20, 15))[0]
        neu(d, "Amazon Payments Europe S.C.A.",
            f"ERSTATTUNG {rng.choice(('305', '028'))}-{_ziffern(rng, 7)}-{_ziffern(rng, 7)} Amazon.de RUECKSENDUNG",
            rng.randint(800, 6000), kat)
    for d in _tage(rng, m, 1):
        betrag, text = rng.choice(((rng.randint(1500, 6000), "Danke fuers Auslegen Konzertkarten"),
                                   (rng.randint(800, 3000), "Pizza gestern"),
                                   (-rng.randint(2000, 5000), "Anteil Geschenk Oma"),
                                   (rng.randint(5000, 20000), "Rueckzahlung Urlaub Ferienwohnung"),
                                   (-rng.randint(1000, 4000), "Kino und Essen")))
        neu(d, "Anna Beispiel", text, betrag, "Privat")
    for d in _tage(rng, m, 0.5):
        neu(d, "Eigenes Tagesgeld", "UMBUCHUNG AUF TAGESGELD DE00000000001234567890", -rng.choice((20000, 50000)),
            "Tagesgeld")
    for d in _tage(rng, m, 0.5):
        neu(d, "IKEA Deutschland GmbH & Co. KG", f"IKEA BEISPIELSTADT KARTE 1234 {_zeit(rng, d, 10, 19)}",
            -rng.randint(1500, 40000), "Haushalt")
    for d in _tage(rng, m, 0.3):
        neu(d, "Zahnarztpraxis Dr. Muster", f"RECHNUNG R-{d.year}-{_ziffern(rng, 4)} PATIENT 4711 "
            f"{rng.choice(('PZR', 'FUELLUNG', 'KONTROLLE'))}", -rng.randint(4000, 25000), "Gesundheit")
    for d in _tage(rng, m, 0.7):
        strecke = rng.choice(("BERLIN-HAMBURG", "HAMBURG-BERLIN", "BERLIN-LEIPZIG", "LEIPZIG-BERLIN", "BERLIN-KOELN"))
        neu(d, "Deutsche Bahn Fernverkehr AG", f"DB FAHRKARTE AUFTRAG {_alnum(rng, 6)} {strecke} {d:%d.%m}",
            -rng.randint(1790, 12990), "Reisen")


def erzeugen(startwert: int = 2026) -> list[dict]:
    """Genau ``ANZAHL`` Buchungen, nach (Datum, laufende Nummer) geordnet, mit Teil training/pruefung."""
    rng = random.Random(startwert)
    roh: list[dict] = []
    m = dt.date(2021, 1, 1)
    while m <= ENDE:
        _monat(rng, m, roh)
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    # Neue Empfänger erst in der Prüfzeit (ohne Vorgeschichte)
    for d, empf, zweck, betrag, kat in (
            (dt.date(2026, 9, 12), "Apotheke am Rathaus", "GIROCARD 12.09 10:41 APOTHEKE AM RATHAUS KARTE 1234", -1695,
             "Gesundheit"),
            (dt.date(2026, 10, 2), "Blumen Rosengarten", "KARTENZAHLUNG 02.10 16:20 BLUMEN ROSENGARTEN KARTE 1234",
             -2450, "Blumen"),
            (dt.date(2026, 10, 9), "Kaufland Beispielstadt", "KARTENZAHLUNG 09.10 18:03 KAUFLAND KARTE 1234", -5312,
             "Lebensmittel")):
        roh.append({"datum": d, "empfaenger": empf, "verwendungszweck": zweck, "betrag": betrag, "wahr": kat})
    roh = [b for b in roh if b["datum"] <= ENDE]
    roh.sort(key=lambda b: b["datum"])
    roh = roh[-ANZAHL:]
    grenze = int(len(roh) * TEIL_TRAINING)
    for i, b in enumerate(roh):
        b["nr"] = i + 1
        b["teil"] = "training" if i < grenze else "pruefung"
        b["erfasst"] = b["wahr"]
        if b["wahr"] in KATEGORIEN and b["teil"] == "training" and rng.random() < FEHLERQUOTE:
            b["erfasst"] = rng.choice([k for k in KATEGORIEN if k != b["wahr"]])
    return roh


def als_csv(buchungen: list[dict]) -> str:
    """CSV im Format des Auftraggebers, ergänzt um Kategorie (erfasst), richtige Kategorie und Teil."""
    f = io.StringIO()
    w = csv.writer(f, delimiter=";", lineterminator="\n")
    w.writerow(("Datum", "Empfänger/Sender", "Verwendungszweck", "Betrag", "Kategorie", "Richtige Kategorie", "Teil"))
    for b in buchungen:
        e, c = divmod(abs(b["betrag"]), 100)
        w.writerow((b["datum"].isoformat(), b["empfaenger"], b["verwendungszweck"],
                    f"{'-' if b['betrag'] < 0 else ''}{e},{c:02d}",
                    b["erfasst"] if b["teil"] == "training" else "", b["wahr"], b["teil"]))
    return f.getvalue()


def laden(client, buchungen: list[dict]) -> dict:
    """Legt Konten, Kategorien, Empfänger und Buchungen über die REST-Schnittstelle an.

    Trainingsbuchungen erhalten ihre erfasste Kategorie, Prüfbuchungen stehen auf „Unkategorisiert“.
    Gibt ``{"ids": {nr: buchung_id}, "kategorien": {name: id}, "konten": {name: id}}`` zurück.
    """
    def konto(name, art):
        r = client.post("/api/konten", json={"name": name, "art": art})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    giro = konto("Girokonto", "girokonto")
    eigene = {n: konto(n, a) for n, a in EIGENE.items()}
    kat = {n: konto(n, "aufwand") for n in AUFWAND} | {n: konto(n, "ertrag") for n in ERTRAG}
    unk = konto("Unkategorisiert", "eigenkapital")
    anfang = konto("Anfangsbestand", "eigenkapital")
    client.post("/api/buchungen", json={"datum": buchungen[0]["datum"].isoformat(), "verwendungszweck": "Anfangsbestand",
                                        "splits": [{"konto_id": giro, "betrag": 500000},
                                                   {"konto_id": anfang, "betrag": -500000}]})
    empf: dict[str, int] = {}
    ids = {}
    for b in buchungen:
        if b["empfaenger"] not in empf:
            r = client.post("/api/empfaenger", json={"name": b["empfaenger"]})
            assert r.status_code == 201, r.text
            empf[b["empfaenger"]] = r.json()["id"]
        if b["erfasst"] in eigene:
            gegen = eigene[b["erfasst"]]
        else:
            gegen = kat[b["erfasst"]] if b["teil"] == "training" else unk
        r = client.post("/api/buchungen", json={
            "datum": b["datum"].isoformat(), "empfaenger_id": empf[b["empfaenger"]],
            "verwendungszweck": b["verwendungszweck"],
            "splits": [{"konto_id": giro, "betrag": b["betrag"]}, {"konto_id": gegen, "betrag": -b["betrag"]}]})
        assert r.status_code == 201, r.text
        ids[b["nr"]] = r.json()["id"]
    return {"ids": ids, "kategorien": kat, "konten": {"Girokonto": giro, **eigene, "Unkategorisiert": unk}}


if __name__ == "__main__":  # pragma: no cover - Hilfe zum Ansehen: CSV auf die Standardausgabe
    import sys
    sys.stdout.write(als_csv(erzeugen()))
