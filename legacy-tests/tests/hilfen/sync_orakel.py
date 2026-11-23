"""Unabhängige Umsetzung der M2-Regeln für Erwartungswerte (ohne App, ohne Generator-Code).

- ``regel_fuer``: erste passende aktive Regel (kategorisierung.md 1, 4).
- ``abgleich``: Abgleich der Umsätze eines Kontos mit vorhandenen Buchungen
  (synchronisation.md 4.4, Regeln aus datenmodell.md 10.4).
- ``erwartete_buchungen``: Buchungen, die ein Lauf aus Umsätzen anlegt (4.2).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .normal import norm, passend


# ---------------------------------------------------------------- Regeln


@dataclass
class Sicht:
    """Was eine Regel von einer Buchung sieht."""
    empfaenger: str | None
    verwendungszweck: str
    regelbetrag: int
    konten: set[int] = field(default_factory=set)


def bedingung_trifft(b: dict, s: Sicht) -> bool:
    feld, op, wert = b["feld"], b["operator"], b["wert"]
    if feld in ("empfaenger", "verwendungszweck"):
        x = s.empfaenger if feld == "empfaenger" else s.verwendungszweck
        if x is None:
            return False
        nx, nw = norm(x), norm(wert)
        if op == "enthaelt":
            return nw in nx
        if op == "gleich":
            return nx == nw
        if op == "beginnt_mit":
            return nx.startswith(nw)
        raise AssertionError(op)
    if feld == "betrag":
        return {"gleich": s.regelbetrag == wert, "mindestens": s.regelbetrag >= wert,
                "hoechstens": s.regelbetrag <= wert}[op]
    if feld == "konto_id":
        return wert in s.konten
    raise AssertionError(feld)


def ordne(regeln: list[dict]) -> list[dict]:
    """Regeln mit ``id`` in Auswertungsreihenfolge (prioritaet, id)."""
    return sorted(regeln, key=lambda r: (r["prioritaet"], r["id"]))


def regel_fuer(regeln: list[dict], s: Sicht) -> dict | None:
    for r in ordne(regeln):
        if r["aktiv"] and all(bedingung_trifft(b, s) for b in r["bedingungen"]):
            return r
    return None


def sicht_umsatz(u: dict, konto_id: int) -> Sicht:
    name = (u["gegenpartei_name"] or "").strip() or None
    return Sicht(name, u["verwendungszweck"], u["betrag"], {konto_id})


# --------------------------------------------------------------- Abgleich


@dataclass
class Kandidat:
    id: object
    datum: str
    empfaenger: str | None
    splits: list[tuple[object, int]]  # (konto, betrag)


def abgleich(umsaetze: list[dict], konto: object, kandidaten: list[Kandidat]) -> dict[str, dict]:
    """Ergebnis je umsatz_id: zusammengefuehrt (mit), zur_pruefung (grund, kandidaten) oder neu.

    ``umsaetze`` sind die zu prüfenden Umsätze eines Kontos (ohne Vormerkungen, ohne gemerkte).
    """
    E: dict[str, set] = {}
    A: dict[str, set] = {}
    for u in umsaetze:
        name = (u["gegenpartei_name"] or "").strip() or None
        e, a = set(), set()
        for c in kandidaten:
            if not any(k == konto and b == u["betrag"] for k, b in c.splits):
                continue
            if c.datum == u["buchungstag"] and passend(name, c.empfaenger):
                e.add(c.id)
            elif abs((dt.date.fromisoformat(c.datum) - dt.date.fromisoformat(u["buchungstag"])).days) <= 3:
                a.add(c.id)
        E[u["umsatz_id"]], A[u["umsatz_id"]] = e, a - e
    aus = {}
    for u in umsaetze:
        uid = u["umsatz_id"]
        e = E[uid]
        if len(e) == 1:
            (c,) = e
            if not any(c in E[v["umsatz_id"]] for v in umsaetze if v["umsatz_id"] != uid):
                aus[uid] = {"ergebnis": "zusammengefuehrt", "mit": [c]}
                continue
        if e or A[uid]:
            aus[uid] = {"ergebnis": "zur_pruefung", "grund": "mehrdeutig" if e else "aehnlich",
                        "kandidaten": sorted(e | A[uid])}
        else:
            aus[uid] = {"ergebnis": "neu"}
    return aus


# ----------------------------------------------------------- Übernahme


def im_zeitraum(umsaetze: list[dict], iban: str, von: dt.date, bis: dt.date, heute: dt.date) -> list[dict]:
    """Was das Mock-Plugin für (iban, von, bis) bei ``heute`` liefert (plugins.md 2/3)."""
    aus = [u for u in umsaetze if u["iban"] == iban
           and von.isoformat() <= u["buchungstag"] <= bis.isoformat() and u["buchungstag"] <= heute.isoformat()]
    return sorted(aus, key=lambda u: (u["buchungstag"], u["umsatz_id"]))


def kennung(u: dict) -> str:
    return f"bank:{u['iban']}:{u['umsatz_id']}"


def erwartete_buchung(u: dict, konto_id: int, gegenkonto_id: int) -> dict:
    """Vergleichbare Sicht einer aus ``u`` angelegten Buchung (synchronisation.md 4.2)."""
    name = (u["gegenpartei_name"] or "").strip() or None
    return {
        "datum": u["buchungstag"],
        "empfaenger": name,
        "verwendungszweck": u["verwendungszweck"],
        "status": "importiert",
        "splits": [(konto_id, u["betrag"], ""), (gegenkonto_id, -u["betrag"], "")],
        "extern_ids": [kennung(u)],
        "tags": [],
    }


def sicht_buchung(b: dict) -> dict:
    """Gleiche Sicht für eine Buchung aus der API."""
    return {
        "datum": b["datum"],
        "empfaenger": b["empfaenger"]["name"] if b["empfaenger"] else None,
        "verwendungszweck": b["verwendungszweck"],
        "status": b["status"],
        "splits": [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]],
        "extern_ids": b["extern_ids"],
        "tags": b["tags"],
    }
