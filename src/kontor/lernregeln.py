"""Automatisch angelegte Regeln aus dem Gelernten (Feature `lernmodell-transparenz`, D-179).

Wurde ein Empfänger mindestens ``MINDESTANZAHL``-mal derselben Kategorie zugeordnet, betrifft diese Kategorie
mindestens 95 % seiner Buchungen insgesamt und mindestens 95 % in den ``FENSTER_TAGE`` Tagen bis zu seiner jüngsten
Buchung (einzelne Fehlgriffe verhindern die Regel also nicht, ein Wechsel der Kategorie schon), legt Kontor die Regel „Empfänger ist <Name>“ → Kategorie an. Grundlage ist
dieselbe Trainingsmenge wie beim Lernmodell (lernmodell.md 3: Kategorie gesetzt, kein offener Vorschlag).

Die Regel steht am Ende der Regelliste, ist in ``regel_automatisch`` als automatisch angelegt vermerkt und sonst
eine gewöhnliche Regel. Löscht der Nutzer sie, darf sie später wieder entstehen (D-307); eine deaktivierte
automatische Regel verhindert eine neue, solange sie besteht. Keine Regel entsteht, wenn eine Regel mit Kategorie
seine jüngste Buchung schon trifft, aktiv oder deaktiviert (eine übernommene Regel wirkt so weiter). Die Tabelle
``empfaenger_lernregel_sperre`` wird nicht mehr geschrieben und nicht mehr beachtet; frühere Sperren bleiben als
Daten stehen, damit Protokoll und Sicherung unverändert bleiben.

``pruefen`` (D-307) vergleicht jede aktive automatische Regel mit denselben Bedingungen und meldet, welche nicht
mehr gilt.
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


def _anteil_fehlt(gleich: int, gesamt: int) -> bool:
    return gesamt == 0 or gleich * MINDESTANTEIL[1] < gesamt * MINDESTANTEIL[0]


def _fenster(beispiele: list[tuple[str, int, int]], heute: dt.date) -> list[int]:
    """Kategorien der Buchungen im Fenster bis zur jüngsten Buchung (bzw. bis heute, falls früher)."""
    juengste = dt.date.fromisoformat(max(d for d, _b, _k in beispiele))
    grenze = (min(heute, juengste) - dt.timedelta(days=FENSTER_TAGE)).isoformat()
    return [k for d, _b, k in beispiele if d >= grenze]


def verletzt(beispiele: list[tuple[str, int, int]], kat: int, heute: dt.date) -> tuple[str, int, int] | None:
    """Erste nicht erfüllte Bedingung für Kategorie ``kat``: (Grund, Anzahl mit ``kat``, Anzahl gesamt) oder None."""
    if not beispiele:
        return ("keine_buchungen", 0, 0)
    anzahl = sum(k == kat for _d, _b, k in beispiele)
    if anzahl < MINDESTANZAHL:
        return ("anzahl", anzahl, len(beispiele))
    if _anteil_fehlt(anzahl, len(beispiele)):
        return ("anteil", anzahl, len(beispiele))
    juengere = _fenster(beispiele, heute)
    gleich = sum(k == kat for k in juengere)
    if _anteil_fehlt(gleich, len(juengere)):
        return ("fenster", gleich, len(juengere))
    return None


def _kategorie(beispiele: list[tuple[str, int, int]], heute: dt.date) -> int | None:
    """Die eindeutige gelernte Kategorie oder None (Bedingungen siehe Modulbeschreibung)."""
    kat = Counter(k for _d, _b, k in beispiele).most_common(1)[0][0]
    return None if verletzt(beispiele, kat, heute) else kat


def _schon_erfasst(con, regelliste: list[dict], name: str, buchung_id: int) -> bool:
    """Trifft eine Regel die Buchung bereits (aktiv: es entstünde nur eine verdeckte Regel; deaktiviert: der Nutzer
    hat sich gegen diese Zuordnung entschieden, D-307)?"""
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
    vorhanden: set[int] = set()
    kandidaten: dict[int, tuple[str, int | None]] = {}
    for teil in ph_teile:
        ph = buch._platzhalter(len(teil))
        vorhanden |= {r[0] for r in con.execute(
            f"SELECT empfaenger_id FROM regel_automatisch WHERE empfaenger_id IN ({ph})", teil)}
        for r in con.execute(f"SELECT id, name, standardkategorie_id FROM empfaenger WHERE id IN ({ph})", teil):
            kandidaten[r["id"]] = (r["name"], r["standardkategorie_id"])
    pruefen = [e for e in ids if e in kandidaten and e not in vorhanden
               and kandidaten[e][1] is None and (kandidaten[e][0] or "").strip()]
    if not pruefen:
        return []
    beispiele = _trainingsbuchungen(con, pruefen)
    alle = regeln.regeln_liste(con, mit_ausdruck=False)
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
        if _schon_erfasst(con, alle, name, juengste):
            continue
        r = regeln.regel_anlegen(con, {"name": name, "kategorie_id": kat,
                                       "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": name}]})
        con.execute("INSERT INTO regel_automatisch (regel_id, empfaenger_id) VALUES (?, ?)", (r["id"], eid))
        neu.append(regeln.regel_lesen(con, r["id"]))
        alle.append(neu[-1])
    return neu


def beschreibung(con, neu: list[dict]) -> str:
    if len(neu) == 1:
        return f"Regel „{neu[0]['name']} → {buch.konto_zeile(con, neu[0]['kategorie_id'])['name']}“ automatisch angelegt"
    return f"{len(neu)} Regeln automatisch angelegt"


_GRUND_TEXT = {
    "keine_buchungen": "Keine kategorisierten Buchungen von {e} mehr.",
    "anzahl": "Nur noch {n} von {m} Buchungen in {k}; nötig sind mindestens 5.",
    "anteil": "Nur noch {p} % der Buchungen in {k} ({n} von {m}); nötig sind 95 %.",
    "fenster": "In den 12 Monaten bis zur jüngsten Buchung nur {p} % in {k} ({n} von {m}); nötig sind 95 %.",
}


def pruefen(con, heute: dt.date) -> dict:
    """GET /api/regeln/pruefung (D-307): aktive automatische Regeln, deren Anlagebedingungen nicht mehr gelten.

    Gleiche Bedingungen wie beim Anlegen (Modulbeschreibung), gemessen an der Kategorie der Regel. Regeln ohne
    Kategorie und Regeln, deren Empfänger nicht mehr besteht, bleiben außen vor. Nur lesend."""
    zeilen = con.execute("SELECT r.id, r.kategorie_id, ra.empfaenger_id, e.name FROM regel r"
                         " JOIN regel_automatisch ra ON ra.regel_id = r.id JOIN empfaenger e ON e.id = ra.empfaenger_id"
                         " WHERE r.aktiv = 1 AND r.kategorie_id IS NOT NULL ORDER BY r.id").fetchall()
    beispiele = _trainingsbuchungen(con, sorted({z["empfaenger_id"] for z in zeilen})) if zeilen else {}
    aus = []
    for z in zeilen:
        befund = verletzt(beispiele.get(z["empfaenger_id"], []), z["kategorie_id"], heute)
        if befund is None:
            continue
        grund, n, m = befund
        k = buch.konto_zeile(con, z["kategorie_id"])["name"]
        p = n * 100 // m if m else 0
        aus.append({"regel_id": z["id"], "grund": grund, "anzahl": n, "gesamt": m,
                    "hinweis": _GRUND_TEXT[grund].format(e=z["name"], n=n, m=m, k=f"„{k}“", p=p)})
    return {"regeln": aus}
