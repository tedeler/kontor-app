"""Berichte: Kontostandsverlauf und Einnahmen/Ausgaben (berichte.md 1–3, Meilenstein 5). Nur lesend."""

from __future__ import annotations

import bisect
import datetime as dt
from collections import defaultdict

from . import buch
from .buch import BESTAND, ApiFehler

INTERVALLE = ("tag", "woche", "monat", "jahr")
MAX_PUNKTE = 5000


def _zu_gross() -> ApiFehler:
    return ApiFehler(422, "bericht_zu_gross", f"Der Bericht hätte mehr als {MAX_PUNKTE} Stichtage bzw. Perioden;"
                     " bitte einen kürzeren Zeitraum oder ein größeres Intervall wählen.")


def _ist_ende(d: dt.date, intervall: str) -> bool:
    if intervall == "tag":
        return True
    if intervall == "woche":
        return d.isoweekday() == 7
    morgen = d + dt.timedelta(days=1)
    if intervall == "monat":
        return morgen.month != d.month
    return morgen.year != d.year


def _naechstes_ende(d: dt.date, intervall: str) -> dt.date:
    """Kleinstes Intervallende ≥ d."""
    if intervall == "tag":
        return d
    if intervall == "woche":
        return d + dt.timedelta(days=7 - d.isoweekday())
    if intervall == "monat":
        erster = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        return erster - dt.timedelta(days=1)
    return dt.date(d.year, 12, 31)


def zeitraum(con, von: str | None, bis: str | None, heute: str) -> tuple[str, str]:
    """berichte.md 1: Vorgaben für ``von``/``bis``; 422 bei ``von > bis``."""
    if bis is None:
        bis = heute
    if von is None:
        r = con.execute("SELECT MIN(datum) AS d FROM buchung").fetchone()
        von = bis if r["d"] is None else min(r["d"], bis)
    if von > bis:
        raise ApiFehler(422, "validierung", "von darf nicht nach bis liegen.",
                        [{"ort": ["query", "von"], "meldung": "von darf nicht nach bis liegen."}])
    return von, bis


def stichtage(von: str, bis: str, intervall: str) -> list[str]:
    """berichte.md 2: ``von``, alle Intervallenden dazwischen, ``bis`` (höchstens 5 000, sonst 422)."""
    a, b = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
    aus = [a]
    e = _naechstes_ende(a + dt.timedelta(days=1), intervall) if a < b else b
    while e < b:
        aus.append(e)
        if len(aus) > MAX_PUNKTE:
            raise _zu_gross()
        e = _naechstes_ende(e + dt.timedelta(days=1), intervall)
    if b > a:
        aus.append(b)
    if len(aus) > MAX_PUNKTE:
        raise _zu_gross()
    return [x.isoformat() for x in aus]


def perioden(von: str, bis: str, intervall: str) -> list[tuple[str, str]]:
    """berichte.md 1: Intervalle, die ``[von, bis]`` schneiden, auf ``[von, bis]`` beschnitten."""
    a, b = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
    aus = []
    beginn = a
    while beginn <= b:
        ende = min(_naechstes_ende(beginn, intervall), b)
        aus.append((beginn.isoformat(), ende.isoformat()))
        if len(aus) > MAX_PUNKTE:
            raise _zu_gross()
        beginn = ende + dt.timedelta(days=1)
    return aus


def _konten_pruefen(con, ids: list[int]) -> dict[int, dict]:
    konten = {k["id"]: k for k in buch.konten_liste(con)}
    fehlend = sorted({i for i in ids if i not in konten})
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Konten.", {"konto_ids": fehlend})
    return konten


def kontostand(con, f: dict, heute: str) -> dict:
    """``GET /api/berichte/kontostand`` (berichte.md 2)."""
    konten = _konten_pruefen(con, f["konto_id"])
    von, bis = zeitraum(con, f["von"], f["bis"], heute)
    tage = stichtage(von, bis, f["intervall"])
    ids = sorted(set(f["konto_id"])) if f["konto_id"] else [k for k in sorted(konten) if konten[k]["art"] in BESTAND]
    menge: dict[int, set[int]] = {}
    for k in ids:
        menge[k] = buch.nachfahren(con, k) if f["unterkonten"] else {k}
    alle = sorted(set().union(*menge.values())) if menge else []
    # Summen je Konto und Datum bis ``bis``, kumuliert
    verlauf: dict[int, tuple[list[str], list[int]]] = {}
    roh: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for teil in buch._stueckweise(alle):
        for r in con.execute(
                "SELECT s.konto_id AS k, b.datum AS d, SUM(s.betrag) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                f" WHERE s.konto_id IN ({buch._platzhalter(len(teil))}) AND b.datum <= ? GROUP BY s.konto_id, b.datum",
                teil + [bis]):
            roh[r["k"]].append((r["d"], r["n"]))
    for k in alle:
        daten, summen, laufend = [], [], 0
        for d, n in sorted(roh.get(k, [])):
            laufend += n
            daten.append(d)
            summen.append(laufend)
        verlauf[k] = (daten, summen)

    def wert(k: int, s: str) -> int:
        daten, summen = verlauf[k]
        i = bisect.bisect_right(daten, s)
        return summen[i - 1] if i else 0

    reihen = [{"konto_id": k, "name": konten[k]["name"], "art": konten[k]["art"],
               "werte": [sum(wert(u, s) for u in menge[k]) for s in tage]} for k in ids]
    return {"von": von, "bis": bis, "intervall": f["intervall"], "unterkonten": f["unterkonten"], "stichtage": tage,
            "reihen": reihen}


def einnahmen_ausgaben(con, f: dict, heute: str) -> dict:
    """``GET /api/berichte/einnahmen-ausgaben`` (berichte.md 3)."""
    konten = _konten_pruefen(con, f["konto_id"])
    if any(konten[k]["art"] not in BESTAND for k in f["konto_id"]):
        raise ApiFehler(422, "konto_ungueltig", "Nur Bestandskonten (Giro-, Spar-, Kreditkonto) sind erlaubt.")
    von, bis = zeitraum(con, f["von"], f["bis"], heute)
    pers = perioden(von, bis, f["intervall"])
    unk = con.execute("SELECT id FROM konto WHERE extern_id = ?", (buch.UNKATEGORISIERT,)).fetchone()
    unk_id = unk["id"] if unk else None
    sql = ("SELECT b.datum AS d, s.konto_id AS k, SUM(s.betrag) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
           " WHERE b.datum BETWEEN ? AND ?")
    par: list = [von, bis]
    if f["konto_id"]:
        ks = sorted(set(f["konto_id"]))
        sql += (f" AND EXISTS (SELECT 1 FROM split x WHERE x.buchung_id = b.id AND x.konto_id IN"
                f" ({buch._platzhalter(len(ks))}))")
        par += ks
    sql += " GROUP BY b.datum, s.konto_id"
    enden = [p[1] for p in pers]
    werte = [{"einnahmen": 0, "ausgaben": 0, "nicht_kategorisiert": 0} for _ in pers]
    kat: dict[int, int] = defaultdict(int)
    for r in con.execute(sql, par):
        art = konten[r["k"]]["art"]
        i = bisect.bisect_left(enden, r["d"])
        if art == "ertrag":
            werte[i]["einnahmen"] -= r["n"]
            kat[r["k"]] += r["n"]
        elif art == "aufwand":
            werte[i]["ausgaben"] += r["n"]
            kat[r["k"]] += r["n"]
        elif r["k"] == unk_id:
            werte[i]["nicht_kategorisiert"] += r["n"]
    perioden_aus = []
    gesamt = {"einnahmen": 0, "ausgaben": 0, "saldo": 0, "nicht_kategorisiert": 0}
    for (a, b), w in zip(pers, werte):
        p = {"von": a, "bis": b, "einnahmen": w["einnahmen"], "ausgaben": w["ausgaben"],
             "saldo": w["einnahmen"] - w["ausgaben"], "nicht_kategorisiert": w["nicht_kategorisiert"]}
        perioden_aus.append(p)
        for k in gesamt:
            gesamt[k] += p[k]
    # Kategorien mit mindestens einem berücksichtigten Split (auch wenn die Summe 0 ist)
    vorhanden = set()
    sql2 = sql.replace("SELECT b.datum AS d, s.konto_id AS k, SUM(s.betrag) AS n", "SELECT DISTINCT s.konto_id AS k") \
        .replace(" GROUP BY b.datum, s.konto_id", "")
    for r in con.execute(sql2, par):
        if konten[r["k"]]["art"] in ("aufwand", "ertrag"):
            vorhanden.add(r["k"])
    kategorien = [{"kategorie_id": k, "name": konten[k]["name"], "art": konten[k]["art"], "summe": kat.get(k, 0)}
                  for k in sorted(vorhanden)]
    return {"von": von, "bis": bis, "intervall": f["intervall"], "perioden": perioden_aus, "gesamt": gesamt,
            "kategorien": kategorien}


__all__ = ["kontostand", "einnahmen_ausgaben", "stichtage", "perioden"]
