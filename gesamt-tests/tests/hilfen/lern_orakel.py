"""Unabhängige Umsetzung des Lernmodells aus spec/api/lernmodell.md (Orakel für Tests).

Naive Bayes mit Laplace-Glättung, exakt mit ``fractions.Fraction``; kein
Bezug zur Anwendung.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction

from .normal import ekey, norm

SCHWELLE = Fraction(7, 10)
MAX_WOERTER = 20
MAX_KANDIDATEN = 5


def merkmale(empfaenger: str | None, verwendungszweck: str, betrag: int) -> list[str]:
    """lernmodell.md 2: Merkmalsmenge (Reihenfolge ohne Bedeutung)."""
    m: list[str] = []
    if empfaenger is not None and ekey(empfaenger):
        m.append("e:" + ekey(empfaenger))
    woerter: list[str] = []
    for w in re.split(r"[^a-z0-9]+", norm(verwendungszweck)):
        if len(w) >= 3 and re.search(r"[a-z]", w) and w not in woerter:
            woerter.append(w)
            if len(woerter) == MAX_WOERTER:
                break
    m += ["v:" + w for w in woerter]
    if betrag == 0:
        m.append("b:0")
    else:
        m.append("b:" + ("+" if betrag > 0 else "-") + str(len(str(abs(betrag)))))
    return m


@dataclass(frozen=True)
class Vorhersage:
    kategorie_id: int | None
    sicherheit: int | None
    kandidaten: list[tuple[int, int]]  # (kategorie_id, Sicherheit in Promille)

    def als_json(self) -> dict:
        return {"kategorie_id": self.kategorie_id, "sicherheit": self.sicherheit,
                "kandidaten": [{"kategorie_id": k, "sicherheit": s} for k, s in self.kandidaten]}


KEINE = Vorhersage(None, None, [])


class Modell:
    """Zählungen über die Trainingsbeispiele (Merkmale, Kategorie)."""

    def __init__(self, beispiele: list[tuple[list[str], int]]) -> None:
        self.n = len(beispiele)
        self.nk: Counter = Counter()
        self.nf: Counter = Counter()
        self.nkf: dict[str, Counter] = defaultdict(Counter)
        for m, c in beispiele:
            self.nk[c] += 1
            for f in set(m):
                self.nf[f] += 1
                self.nkf[f][c] += 1

    def vorhersage(self, m: list[str]) -> Vorhersage:
        bekannt = sorted({f for f in m if self.nf[f] > 0})
        if not any(f[0] in "ev" for f in bekannt):
            return KEINE
        s: dict = {}
        for c, nc in self.nk.items():
            p = Fraction(nc, self.n)
            for f in bekannt:
                p *= Fraction(self.nkf[f][c] + 1, nc + 2)
            s[c] = p
        summe = sum(s.values())
        reihe = sorted(((p / summe, c) for c, p in s.items()), key=lambda x: (-x[0], x[1]))
        kand = [(c, int(p * 1000)) for p, c in reihe[:MAX_KANDIDATEN]]
        p, c = reihe[0]
        if p >= SCHWELLE:
            return Vorhersage(c, int(p * 1000), kand)
        return Vorhersage(None, None, kand)


def bewerte(wahrheit: list[dict], kat_id=lambda name: name) -> dict:
    """Training auf teil=training, Prüfung auf teil=pruefung (lernmodell.md 6)."""
    train = [(merkmale(w["empfaenger"], w["verwendungszweck"], w["betrag"]), kat_id(w["kategorie"]))
             for w in wahrheit if w["teil"] == "training"]
    modell = Modell(train)
    pruef = [w for w in wahrheit if w["teil"] == "pruefung"]
    vorher = [modell.vorhersage(merkmale(w["empfaenger"], w["verwendungszweck"], w["betrag"])) for w in pruef]
    vorgeschlagen = sum(v.kategorie_id is not None for v in vorher)
    richtig = sum(v.kategorie_id is not None and v.kategorie_id == kat_id(w["wahr"]) for v, w in zip(vorher, pruef))
    return {"pruefung": len(pruef), "vorgeschlagen": vorgeschlagen, "richtig": richtig,
            "genauigkeit": Fraction(richtig, vorgeschlagen) if vorgeschlagen else Fraction(0),
            "abdeckung": Fraction(vorgeschlagen, len(pruef)) if pruef else Fraction(0),
            "vorhersagen": vorher, "modell": modell}
