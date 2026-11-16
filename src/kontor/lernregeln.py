"""Automatisch angelegte Regeln aus dem Gelernten (Feature `lernmodell-transparenz`, D-179).

Wurde ein Empfänger mindestens ``MINDESTANZAHL``-mal derselben Kategorie zugeordnet, betrifft diese Kategorie
mindestens 95 % seiner Buchungen insgesamt und mindestens 95 % in den ``FENSTER_TAGE`` Tagen bis zu seiner jüngsten
Buchung (einzelne Fehlgriffe verhindern die Regel also nicht, ein Wechsel der Kategorie schon), legt Kontor die Regel „Empfänger ist <Name>“ → Kategorie an. Grundlage ist
dieselbe Trainingsmenge wie beim Lernmodell (lernmodell.md 3: Kategorie gesetzt, kein offener Vorschlag).

Die Regel steht am Ende der Regelliste, ist in ``regel_automatisch`` als automatisch angelegt vermerkt und sonst
eine gewöhnliche Regel. Löscht der Nutzer sie, sperrt ``empfaenger_lernregel_sperre`` den Empfänger, damit sie
nicht wieder entsteht. Keine Regel entsteht, wenn der Empfänger eine Standardkategorie hat oder eine aktive Regel
seine jüngste Buchung schon trifft.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from . import buch, lernmodell, regeln
from .buch import BESTAND

MINDESTANZAHL = 5
MINDESTANTEIL = (95, 100)  # Anteil der Kategorie an allen Buchungen des Empfängers in der Trainingsmenge
FENSTER_TAGE = 365
AKTION = "regel_automatisch"


def betroffene_empfaenger(eintraege: list[dict]) -> set[int]:
    """Empfänger der Buchungen, die eine Änderung berührt hat (vorher und nachher)."""
    aus: set[int] = set()
    for e in eintraege:
        if e["objekt"] != "buchung":
            continue
        for form in (e["vorher"], e["nachher"]):
            if form and form.get("empfaenger_id") is not None:
                aus.add(form["empfaenger_id"])
    return aus


def _trainingsbuchungen(con, empfaenger_ids: list[int]) -> dict[int, list[tuple[str, int, int]]]:
    """Je Empfänger: (Datum, Buchungs-ID, Kategorie) der Buchungen in der Trainingsmenge."""
    kopf: dict[int, tuple[int, str]] = {}
    for teil in buch._stueckweise(sorted(empfaenger_ids)):
        for r in con.execute(f"SELECT id, empfaenger_id, datum FROM buchung WHERE empfaenger_id IN"
                             f" ({buch._platzhalter(len(teil))})", teil):
            kopf[r["id"]] = (r["empfaenger_id"], r["datum"])
    je: dict[int, list[tuple[str, int, int]]] = defaultdict(list)
    if not kopf:
        return je
    for bid, (_m, kat, offen) in lernmodell.buchungsmerkmale(con, list(kopf)).items():
        if kat is not None and not offen:
            eid, datum = kopf[bid]
            je[eid].append((datum, bid, kat))
    return je


def _kategorie(beispiele: list[tuple[str, int, int]], heute: dt.date) -> int | None:
    """Die eindeutige gelernte Kategorie oder None (Bedingungen siehe Modulbeschreibung)."""
    kat, anzahl = Counter(k for _d, _b, k in beispiele).most_common(1)[0]
    if anzahl < MINDESTANZAHL or anzahl * MINDESTANTEIL[1] < len(beispiele) * MINDESTANTEIL[0]:
        return None
    juengste = dt.date.fromisoformat(max(d for d, _b, _k in beispiele))
    grenze = (min(heute, juengste) - dt.timedelta(days=FENSTER_TAGE)).isoformat()
    juengere = [k for d, _b, k in beispiele if d >= grenze]
    gleich = sum(k == kat for k in juengere)
    if not juengere or gleich * MINDESTANTEIL[1] < len(juengere) * MINDESTANTEIL[0]:
        return None
    return kat


def _schon_erfasst(con, regelliste: list[dict], name: str, buchung_id: int) -> bool:
    """Trifft eine aktive Regel die Buchung bereits (dann entstünde nur eine verdeckte Regel)?"""
    art_von = buch.kontoarten(con)
    b = buch.buchungen_laden(con, [buchung_id], art_von=art_von)[0]
    bestand = [s for s in b["splits"] if art_von[s["konto_id"]] in BESTAND]
    sicht = regeln.Sicht(name, b["verwendungszweck"], sum(s["betrag"] for s in bestand),
                         {s["konto_id"] for s in bestand})
    return regeln.erste_regel(regelliste, sicht) is not None




def anlegen(con, empfaenger_ids: set[int], heute: dt.date) -> list[dict]:
    """Legt die fälligen automatischen Regeln für diese Empfänger an; gibt die neuen Regeln zurück."""
    if not empfaenger_ids:
        return []
    ids = sorted(empfaenger_ids)
    ph_teile = list(buch._stueckweise(ids))
    gesperrt: set[int] = set()
    vorhanden: set[int] = set()
    kandidaten: dict[int, tuple[str, int | None]] = {}
    for teil in ph_teile:
        ph = buch._platzhalter(len(teil))
        gesperrt |= {r[0] for r in con.execute(
            f"SELECT empfaenger_id FROM empfaenger_lernregel_sperre WHERE empfaenger_id IN ({ph})", teil)}
        vorhanden |= {r[0] for r in con.execute(
            f"SELECT empfaenger_id FROM regel_automatisch WHERE empfaenger_id IN ({ph})", teil)}
        for r in con.execute(f"SELECT id, name, standardkategorie_id FROM empfaenger WHERE id IN ({ph})", teil):
            kandidaten[r["id"]] = (r["name"], r["standardkategorie_id"])
    pruefen = [e for e in ids if e in kandidaten and e not in gesperrt and e not in vorhanden
               and kandidaten[e][1] is None and (kandidaten[e][0] or "").strip()]
    if not pruefen:
        return []
    beispiele = _trainingsbuchungen(con, pruefen)
    aktive = regeln.aktive_regeln(con)
    neu = []
    for eid in pruefen:
        bsp = beispiele.get(eid)
        if not bsp:
            continue
        kat = _kategorie(bsp, heute)
        if kat is None:
            continue
        name = kandidaten[eid][0].strip()[:200]
        juengste = max(bsp)[1]
        if _schon_erfasst(con, aktive, name, juengste):
            continue
        r = regeln.regel_anlegen(con, {"name": name, "kategorie_id": kat,
                                       "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": name}]})
        con.execute("INSERT INTO regel_automatisch (regel_id, empfaenger_id) VALUES (?, ?)", (r["id"], eid))
        neu.append(regeln.regel_lesen(con, r["id"]))
        aktive.append(neu[-1])
    return neu


def beschreibung(con, neu: list[dict]) -> str:
    if len(neu) == 1:
        return f"Regel „{neu[0]['name']} → {buch.konto_zeile(con, neu[0]['kategorie_id'])['name']}“ automatisch angelegt"
    return f"{len(neu)} Regeln automatisch angelegt"
