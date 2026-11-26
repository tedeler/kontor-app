"""Sonderposten in den Berichten (Feature „sonderposten“, D-300, berichte.md 7).

Eine Buchung mit dem Tag „Sonderposten“ (Name ohne Groß- und Kleinschreibung; nur Tags der Buchung, nicht des
Empfängers) ist eine einmalige Ausnahme wie ein Autokauf. Die Berichte über Einnahmen und Ausgaben lassen sie mit
``sonderposten=ohne`` (Vorgabe) aus und nennen sie in einem eigenen Abschnitt; ``mit`` zählt sie wie bisher. Kein
eigener Zustand: Markiert wird über den Tag.
"""

from __future__ import annotations

import datetime as dt

NAME = "Sonderposten"
MODI = ("ohne", "mit")


def tag_id(con) -> int | None:
    r = con.execute("SELECT id FROM tag WHERE lower(name) = lower(?) ORDER BY id LIMIT 1", (NAME,)).fetchone()
    return r["id"] if r else None


def buchung_ids(con, tid: int | None) -> set[int]:
    if tid is None:
        return set()
    return {r[0] for r in con.execute("SELECT buchung_id FROM buchung_tag WHERE tag_id = ?", (tid,))}


def modus_lesen(q) -> str:
    """Parameter ``sonderposten`` einer Abfrage (``ohne`` als Vorgabe)."""
    return q.auswahl("sonderposten", MODI) or "ohne"


class Trennung:
    """Ergebnis von ``trennen``: die Posten für die Rechnung und die Sonderposten (für den Abschnitt)."""

    def __init__(self, modus: str, tid: int | None, sonder: list):
        self.modus = modus
        self.tag_id = tid
        self.sonder = sonder

    def abschnitt(self, von: dt.date | None = None, bis: dt.date | None = None) -> dict:
        ps = [p for p in self.sonder if (von is None or p.datum >= von) and (bis is None or p.datum <= bis)]
        ps.sort(key=lambda p: (p.datum, p.id))
        return {"modus": self.modus, "tag_id": self.tag_id, "anzahl": len(ps),
                "ausgaben": sum(p.netto for p in ps),
                "einnahmen": sum(p.betrag for p in ps if p.art == "einnahme"),
                "eintraege": [p.kurz() for p in ps]}


def trennen(con, posten: list, modus: str) -> tuple[list, Trennung]:
    """Posten aus ``monatsbericht._laden`` aufteilen. Mit ``ohne`` fehlen die Sonderposten in der ersten Liste."""
    tid = tag_id(con)
    ids = buchung_ids(con, tid)
    sonder = [p for p in posten if p.id in ids]
    rest = [p for p in posten if p.id not in ids] if modus == "ohne" else posten
    return rest, Trennung(modus, tid, sonder)


__all__ = ["NAME", "MODI", "tag_id", "buchung_ids", "modus_lesen", "trennen", "Trennung"]
