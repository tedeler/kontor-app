"""Lernmodell zur Kategorisierung (lernmodell.md, Meilenstein 4).

Naive Bayes über binäre Merkmale mit Laplace-Glättung, exakt mit
``fractions.Fraction`` gerechnet (keine Gleitkommazahlen). Das Modell hat
keinen eigenen Zustand: Es wird bei jeder Abfrage aus dem aktuellen
Buchbestand trainiert (Trainingsmenge = kategorisierte Buchungen ohne
offenen Vorschlag, lernmodell.md 1 und 3). Training erzeugt daher nie eine
Änderung im Protokoll, und Rückgängig stellt das Modell automatisch wieder her.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction

from . import buch
from .buch import BESTAND, KATEGORIEARTEN, ApiFehler
from .text import ekey, norm

SCHWELLE = Fraction(7, 10)
SCHWELLE_PROMILLE = 700
MAX_WOERTER = 20
MAX_KANDIDATEN = 5
_TRENNER = re.compile(r"[^a-z0-9]+")
_BUCHSTABE = re.compile(r"[a-z]")


def merkmale(empfaenger: str | None, verwendungszweck: str, betrag: int) -> frozenset[str]:
    """lernmodell.md 2: Merkmalsmenge M = E ∪ V ∪ B."""
    m: set[str] = set()
    if empfaenger is not None:
        k = ekey(empfaenger)
        if k:
            m.add("e:" + k)
    woerter: list[str] = []
    for w in _TRENNER.split(norm(verwendungszweck or "")):
        if len(w) >= 3 and _BUCHSTABE.search(w) and w not in woerter:
            woerter.append(w)
            if len(woerter) == MAX_WOERTER:
                break
    m.update("v:" + w for w in woerter)
    if betrag == 0:
        m.add("b:0")
    else:
        m.add("b:" + ("+" if betrag > 0 else "-") + str(len(str(abs(betrag)))))
    return frozenset(m)


@dataclass(frozen=True)
class Vorhersage:
    kategorie_id: int | None
    sicherheit: int | None
    kandidaten: tuple[tuple[int, int], ...]

    def als_dict(self) -> dict:
        return {"kategorie_id": self.kategorie_id, "sicherheit": self.sicherheit,
                "kandidaten": [{"kategorie_id": k, "sicherheit": s} for k, s in self.kandidaten]}


KEINE = Vorhersage(None, None, ())


def _promille(p: Fraction) -> int:
    return (1000 * p.numerator) // p.denominator


class Modell:
    """Zählungen über die Trainingsmenge (lernmodell.md 3)."""

    def __init__(self, beispiele: list[tuple[frozenset[str], int]]) -> None:
        self.n = len(beispiele)
        self.nk: Counter[int] = Counter()
        self.nf: Counter[str] = Counter()
        self.nkf: dict[str, Counter[int]] = defaultdict(Counter)
        for m, c in beispiele:
            self.nk[c] += 1
            for f in m:
                self.nf[f] += 1
                self.nkf[f][c] += 1

    def vorhersage(self, m: frozenset[str]) -> Vorhersage:
        bekannt = [f for f in m if self.nf[f] > 0]
        if not any(f[0] in "ev" for f in bekannt):
            return KEINE
        s: dict[int, Fraction] = {}
        for c, nc in self.nk.items():
            zaehler, nenner = nc, self.n
            for f in bekannt:
                zaehler *= self.nkf[f][c] + 1
                nenner *= nc + 2
            s[c] = Fraction(zaehler, nenner)
        summe = sum(s.values())
        reihe = sorted(((p / summe, c) for c, p in s.items()), key=lambda x: (-x[0], x[1]))
        kandidaten = tuple((c, _promille(p)) for p, c in reihe[:MAX_KANDIDATEN])
        p, c = reihe[0]
        if p >= SCHWELLE:
            return Vorhersage(c, _promille(p), kandidaten)
        return Vorhersage(None, None, kandidaten)


# ============================================================ Buchbestand


def buchungsmerkmale(con, ids: list[int] | None = None) -> dict[int, tuple[frozenset[str], int | None, bool]]:
    """Je Buchung: (Merkmale, Kategorie nach datenmodell.md 3.2, offener Vorschlag?)."""
    art_von = buch.kontoarten(con)
    kopf: dict[int, tuple[str | None, str]] = {}
    splits: dict[int, list[tuple[int, int]]] = defaultdict(list)
    offen: set[int] = set()
    if ids is None:
        teile = [None]
    else:
        teile = list(buch._stueckweise(sorted(set(ids))))
    for teil in teile:
        wo, par = ("", []) if teil is None else (f" WHERE b.id IN ({buch._platzhalter(len(teil))})", teil)
        for r in con.execute("SELECT b.id, e.name, b.verwendungszweck FROM buchung b"
                             f" LEFT JOIN empfaenger e ON e.id = b.empfaenger_id{wo}", par):
            kopf[r[0]] = (r[1], r[2])
        wo_s = "" if teil is None else f" WHERE s.buchung_id IN ({buch._platzhalter(len(teil))})"
        for r in con.execute(f"SELECT s.buchung_id, s.konto_id, s.betrag FROM split s{wo_s}", par):
            splits[r[0]].append((r[1], r[2]))
        wo_v = "" if teil is None else f" WHERE buchung_id IN ({buch._platzhalter(len(teil))})"
        offen |= {r[0] for r in con.execute(f"SELECT buchung_id FROM vorschlag{wo_v}", par)}
    aus = {}
    for bid, (name, zweck) in kopf.items():
        sp = splits[bid]
        gegen = [k for k, _ in sp if art_von.get(k) not in BESTAND]
        kat = gegen[0] if len(gegen) == 1 and art_von.get(gegen[0]) in KATEGORIEARTEN else None
        regelbetrag = sum(b for k, b in sp if art_von.get(k) in BESTAND)
        aus[bid] = (merkmale(name, zweck, regelbetrag), kat, bid in offen)
    return aus


def trainieren(con) -> Modell:
    """Trainingsmenge T: kategorie_id ≠ null und vorschlag = null (lernmodell.md 3)."""
    beispiele = [(m, kat) for _bid, (m, kat, offen) in sorted(buchungsmerkmale(con).items())
                 if kat is not None and not offen]
    return Modell(beispiele)


def zustand(con, automatisch: bool) -> dict:
    m = trainieren(con)
    return {"trainingsbuchungen": m.n, "kategorien": len(m.nk), "merkmale": sum(1 for f in m.nf if m.nf[f] > 0),
            "automatisch": automatisch, "schwelle_promille": SCHWELLE_PROMILLE}


def vorhersagen(con, eintraege: list[dict]) -> dict:
    """POST /api/lernmodell/vorhersage (5.3): alle gegen dieselbe Trainingsmenge, ohne Wirkung."""
    ids = [e["buchung_id"] for e in eintraege if "buchung_id" in e]
    bekannt = buchungsmerkmale(con, ids) if ids else {}
    fehlend = sorted(set(ids) - set(bekannt))
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    modell = trainieren(con)
    aus = []
    for e in eintraege:
        if "buchung_id" in e:
            m = bekannt[e["buchung_id"]][0]
        else:
            m = merkmale(e.get("empfaenger"), e.get("verwendungszweck", ""), e["betrag"])
        aus.append(modell.vorhersage(m).als_dict())
    return {"ergebnisse": aus}


def vorschlag_setzen(con, buchung_id: int, split_id: int, vorher_konto_id: int, v: Vorhersage) -> None:
    """Setzt die Kategorie des Lernmodells als Vorschlag (lernmodell.md 5.1)."""
    con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (v.kategorie_id, split_id))
    con.execute("INSERT INTO vorschlag (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id, sicherheit)"
                " VALUES (?, ?, NULL, 'lernmodell', ?, ?) ON CONFLICT(buchung_id) DO UPDATE SET"
                " kategorie_id = excluded.kategorie_id, regel_id = NULL, quelle = excluded.quelle,"
                " vorher_konto_id = excluded.vorher_konto_id, sicherheit = excluded.sicherheit",
                (buchung_id, v.kategorie_id, vorher_konto_id, v.sicherheit))


def anwenden(con, buchung_ids: list[int] | None, trocken: bool) -> dict:
    """POST /api/lernmodell/anwenden (5.2)."""
    if buchung_ids is not None:
        fehlend = sorted(set(buchung_ids) - buch._vorhandene_buchungen(con, buchung_ids))
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    modell = trainieren(con)
    art_von = buch.kontoarten(con)
    if buchung_ids is None:
        ids = [r["id"] for r in con.execute("SELECT id FROM buchung ORDER BY id")]
    else:
        ids = sorted(set(buchung_ids))
    geprueft = 0
    aenderungen = []
    for teil in buch._stueckweise(ids):
        for b in buch.buchungen_laden(con, teil, art_von=art_von):
            if buch.ist_gesperrt(b) or b["kategorie_id"] is not None:
                continue
            gegen = buch._gegensplit(b, art_von)
            if gegen is None or art_von[gegen["konto_id"]] != "eigenkapital":
                continue
            geprueft += 1
            regelbetrag = sum(s["betrag"] for s in b["splits"] if art_von[s["konto_id"]] in BESTAND)
            v = modell.vorhersage(merkmale(b["empfaenger"]["name"] if b["empfaenger"] else None,
                                           b["verwendungszweck"], regelbetrag))
            if v.kategorie_id is None:
                continue
            aenderungen.append({"buchung_id": b["id"], "kategorie_id": v.kategorie_id, "sicherheit": v.sicherheit})
            if not trocken:
                vorschlag_setzen(con, b["id"], gegen["id"], gegen["konto_id"], v)
    return {"geprueft": geprueft, "anzahl": len(aenderungen), "trocken": trocken, "aenderungen": aenderungen}


__all__ = ["merkmale", "Modell", "Vorhersage", "trainieren", "zustand", "vorhersagen", "anwenden"]
