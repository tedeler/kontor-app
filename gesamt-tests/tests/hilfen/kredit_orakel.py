"""Unabhängiges Orakel für Tilgungspläne (kredite.md 3) mit exakten Brüchen.

Getrennt vom Generator geschrieben (dort ``Decimal``); dient Hypothesis-Tests und dem Generator-Test als
Gegenrechnung. Keine Gleitkommazahlen.
"""

from __future__ import annotations

import calendar
import datetime as dt
from fractions import Fraction

MAX_RATEN = 1200


class RateZuKlein(Exception):
    pass


def monat_plus(d: dt.date, n: int) -> dt.date:
    jahr, monat = divmod(d.year * 12 + (d.month - 1) + n, 12)
    monat += 1
    return dt.date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1]))


def zinstage(methode: str, a: dt.date, b: dt.date) -> int:
    if methode == "30/360":
        return 360 * (b.year - a.year) + 30 * (b.month - a.month) + min(b.day, 30) - min(a.day, 30)
    return (b - a).days


def basis(methode: str) -> int:
    return 365 if methode == "act/365" else 360


def kaufmaennisch(x: Fraction) -> int:
    """⌊x + 1/2⌋ für x ≥ 0."""
    assert x >= 0
    return (x + Fraction(1, 2)).__floor__()


def _datum(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(x)


def plan(p: dict) -> dict:
    """Tilgungsplan im Schema ``Tilgungsplan``; wirft ``RateZuKlein``."""
    methode = p.get("zinsmethode", "30/360")
    stand, erste = _datum(p["stand_datum"]), _datum(p["erste_faelligkeit"])
    rate, satz = p["rate"], Fraction(p["sollzins"], 1_000_000)
    sonder = [(_datum(s["datum"]), s["betrag"]) for s in p.get("sondertilgungen", [])]
    sonder = [x for _, x in sorted(enumerate(sonder), key=lambda iv: (iv[1][0], iv[0]))]
    r = p["restschuld"]
    zeilen: list[dict] = []
    beginn = stand
    for i in range(1, MAX_RATEN + 1):
        f = monat_plus(erste, i - 1)
        laenge = 30 if methode == "30/360" and i > 1 else zinstage(methode, beginn, f)
        vorher = r
        exakt = Fraction(0)
        lage = 0
        summe_sonder = 0
        for datum, betrag in sonder:
            if beginn < datum <= f:
                pos = min(laenge, zinstage(methode, beginn, datum))
                exakt += r * satz * (pos - lage) / basis(methode)
                lage = pos
                wirksam = min(betrag, r)
                r -= wirksam
                summe_sonder += wirksam
        exakt += r * satz * (laenge - lage) / basis(methode)
        zins = kaufmaennisch(exakt)
        if r + zins <= rate:
            zahlung, tilgung, schluss = r + zins, r, True
        else:
            zahlung, tilgung, schluss = rate, rate - zins, False
        zeilen.append({"nr": i, "faelligkeit": f.isoformat(), "zinstage": laenge, "restschuld_vorher": vorher,
                       "sondertilgung": summe_sonder, "zins": zins, "tilgung": tilgung, "rate": zahlung,
                       "restschuld_nachher": r - tilgung})
        r -= tilgung
        beginn = f
        if schluss:
            break
    else:
        raise RateZuKlein()
    return {"zeilen": zeilen, "anzahl_raten": len(zeilen), "summe_zins": sum(z["zins"] for z in zeilen),
            "summe_tilgung": sum(z["tilgung"] for z in zeilen),
            "summe_sondertilgung": sum(z["sondertilgung"] for z in zeilen),
            "letzte_faelligkeit": zeilen[-1]["faelligkeit"]}


def plan_oder_fehler(p: dict) -> dict:
    try:
        return plan(p)
    except RateZuKlein:
        return {"fehler": "kredit_rate_zu_klein"}


def exakte_restschuld(p: dict, n: int) -> Fraction:
    """Restschuld nach n Raten ohne jede Rundung (nur ohne Sondertilgungen und ohne Schlussrate sinnvoll)."""
    methode = p.get("zinsmethode", "30/360")
    stand, erste = _datum(p["stand_datum"]), _datum(p["erste_faelligkeit"])
    satz = Fraction(p["sollzins"], 1_000_000)
    r = Fraction(p["restschuld"])
    beginn = stand
    for i in range(1, n + 1):
        f = monat_plus(erste, i - 1)
        laenge = 30 if methode == "30/360" and i > 1 else zinstage(methode, beginn, f)
        r = r - (p["rate"] - r * satz * laenge / basis(methode))
        beginn = f
    return r


def pruefe_plan_eigenschaften(pl: dict, p: dict) -> None:
    """Invarianten aus kredite.md 3.5 (unabhängig von der Rechnung)."""
    z = pl["zeilen"]
    assert pl["anzahl_raten"] == len(z)
    r = p["restschuld"]
    for i, zeile in enumerate(z, 1):
        assert zeile["nr"] == i
        assert zeile["restschuld_vorher"] == r, f"Zeile {i}: restschuld_vorher {zeile['restschuld_vorher']} ≠ {r}"
        assert zeile["rate"] == zeile["zins"] + zeile["tilgung"], f"Zeile {i}: Zins + Tilgung ≠ Rate"
        assert zeile["restschuld_nachher"] == r - zeile["sondertilgung"] - zeile["tilgung"], f"Zeile {i}"
        assert zeile["zins"] >= 0 and zeile["sondertilgung"] >= 0
        assert zeile["faelligkeit"] == monat_plus(_datum(p["erste_faelligkeit"]), i - 1).isoformat()
        if i < len(z):
            assert zeile["rate"] == p["rate"], f"Zeile {i}: nur die letzte Rate darf abweichen"
        r = zeile["restschuld_nachher"]
    assert z, "ein Plan hat mindestens eine Zeile"
    assert z[-1]["restschuld_nachher"] == 0 and z[-1]["rate"] <= p["rate"]
    assert pl["letzte_faelligkeit"] == z[-1]["faelligkeit"]
    assert pl["summe_tilgung"] + pl["summe_sondertilgung"] == p["restschuld"]
    assert pl["summe_zins"] == sum(x["zins"] for x in z)
