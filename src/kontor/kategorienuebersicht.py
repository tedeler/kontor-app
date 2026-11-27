"""Beträge für die Kategorienseite (Feature ``kategorien-uebersicht``, D-311). Nur lesend.

``GET /api/kategorien/uebersicht?zeitraum=…`` liefert je Kategorie (Art ``aufwand``/``ertrag``) die Summe im Zeitraum
einschließlich Unterkategorien, den eigenen Anteil, die Zahl der Buchungen, den Tag der letzten Buchung (überhaupt) und
den Verlauf. Ausgaben und Einnahmen sind positiv (Ausgaben = Summe der Splits, Einnahmen = negative Summe). Sonderposten
zählen mit: Die Seite zeigt, was auf den Kategorien gebucht ist.

Verlauf (D-320): kumuliert über genau den gewählten Zeitraum, je Abschnitt der Stand seit Beginn des Zeitraums; der
letzte Wert ist die Summe der Zeile. Abschnitte je Tag (Monat, Vormonat, 30 Tage), je Monat (12 Monate, Jahr,
Vorjahr); „gesamt“ von der ersten bis zur letzten Buchung (mindestens bis heute) je Monat (bis 24 Monate),
Quartal (bis 96 Monate) oder Jahr.
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections import defaultdict

from . import buch

ZEITRAEUME = ("monat", "vormonat", "30tage", "12monate", "jahr", "vorjahr", "gesamt")
VORGABE = "12monate"


def _monat_plus(j: int, m: int, n: int) -> tuple[int, int]:
    i = j * 12 + (m - 1) + n
    return i // 12, i % 12 + 1


def _monatsende(j: int, m: int) -> dt.date:
    nj, nm = _monat_plus(j, m, 1)
    return dt.date(nj, nm, 1) - dt.timedelta(days=1)


def grenzen(zeitraum: str, heute: dt.date) -> tuple[str | None, str | None, tuple[int, int]]:
    """(von, bis, letzter Monat des Verlaufs)."""
    j, m = heute.year, heute.month
    if zeitraum == "monat":
        return dt.date(j, m, 1).isoformat(), _monatsende(j, m).isoformat(), (j, m)
    if zeitraum == "vormonat":
        vj, vm = _monat_plus(j, m, -1)
        return dt.date(vj, vm, 1).isoformat(), _monatsende(vj, vm).isoformat(), (vj, vm)
    if zeitraum == "30tage":
        return (heute - dt.timedelta(days=29)).isoformat(), heute.isoformat(), (j, m)
    if zeitraum == "12monate":
        vj, vm = _monat_plus(j, m, -11)
        return dt.date(vj, vm, 1).isoformat(), _monatsende(j, m).isoformat(), (j, m)
    if zeitraum == "jahr":
        return f"{j}-01-01", f"{j}-12-31", (j, 12)
    if zeitraum == "vorjahr":
        return f"{j - 1}-01-01", f"{j - 1}-12-31", (j - 1, 12)
    return None, None, (j, m)


def _abschnitte(zeitraum: str, von: str | None, bis: str | None, erste: str | None,
                letzte: str | None, heute: dt.date) -> tuple[str, list[str]]:
    """(Art, Enddaten der Abschnitte) des Verlaufs; das letzte Enddatum ist das Ende des Zeitraums."""
    if zeitraum in ("monat", "vormonat", "30tage"):
        a, e = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
        return "tag", [(a + dt.timedelta(days=i)).isoformat() for i in range((e - a).days + 1)]
    if von is not None:
        a, e = dt.date.fromisoformat(von), dt.date.fromisoformat(bis)
        aj, am, ej, em = a.year, a.month, e.year, e.month
        art, schritt = "monat", 1
    else:   # gesamt: von der ersten bis zur letzten Buchung (mindestens bis heute)
        a = dt.date.fromisoformat(erste) if erste else heute
        e = max(dt.date.fromisoformat(letzte), heute) if letzte else heute
        n = (e.year - a.year) * 12 + e.month - a.month + 1
        if n <= 24:
            art, schritt, aj, am = "monat", 1, a.year, a.month
        elif n <= 96:
            art, schritt, aj, am = "quartal", 3, a.year, (a.month - 1) // 3 * 3 + 1
        else:
            art, schritt, aj, am = "jahr", 12, a.year, 1
        ej, em = e.year, e.month
    enden = []
    j, m = aj, am
    while (j, m) <= (ej, em):
        j2, m2 = _monat_plus(j, m, schritt - 1)
        enden.append(_monatsende(j2, m2).isoformat())
        j, m = _monat_plus(j, m, schritt)
    return art, enden


def uebersicht(con, zeitraum: str, heute: str) -> dict:
    von, bis, _ = grenzen(zeitraum, dt.date.fromisoformat(heute))
    konten = {r["id"]: dict(r) for r in con.execute(
        "SELECT id, art, eltern_id FROM konto WHERE art IN ('aufwand', 'ertrag')")}
    unk = con.execute("SELECT id FROM konto WHERE extern_id = ?", (buch.UNKATEGORISIERT,)).fetchone()
    unk_id = unk["id"] if unk else None
    vz = {k: (1 if v["art"] == "aufwand" else -1) for k, v in konten.items()}

    bedingung, par = "", []
    if von is not None:
        bedingung, par = " AND b.datum BETWEEN ? AND ?", [von, bis]
    eigen: dict[int, int] = defaultdict(int)
    buchungen: dict[int, set[int]] = defaultdict(set)
    unk_anzahl = unk_summe = 0
    for r in con.execute("SELECT s.konto_id AS k, s.buchung_id AS b, SUM(s.betrag) AS n FROM split s"
                         " JOIN buchung b ON b.id = s.buchung_id JOIN konto k ON k.id = s.konto_id"
                         " WHERE (k.art IN ('aufwand', 'ertrag') OR k.id = ?)" + bedingung
                         + " GROUP BY s.konto_id, s.buchung_id", [unk_id, *par]):
        if r["k"] == unk_id:
            unk_anzahl += 1
            unk_summe += r["n"]
            continue
        eigen[r["k"]] += vz[r["k"]] * r["n"]
        buchungen[r["k"]].add(r["b"])
    # D-320: Beträge je Tag im Zeitraum, in Abschnitte einsortiert und danach aufsummiert
    tage = con.execute("SELECT s.konto_id AS k, b.datum AS d, SUM(s.betrag) AS n FROM split s"
                       " JOIN buchung b ON b.id = s.buchung_id JOIN konto k ON k.id = s.konto_id"
                       " WHERE k.art IN ('aufwand', 'ertrag')" + bedingung + " GROUP BY s.konto_id, b.datum",
                       par).fetchall()
    verlauf_art, verlauf_bis = _abschnitte(zeitraum, von, bis, min((r["d"] for r in tage), default=None),
                                           max((r["d"] for r in tage), default=None), dt.date.fromisoformat(heute))
    verlauf: dict[int, list[int]] = defaultdict(lambda: [0] * len(verlauf_bis))
    for r in tage:
        verlauf[r["k"]][bisect.bisect_left(verlauf_bis, r["d"][:10])] += vz[r["k"]] * r["n"]
    for werte in verlauf.values():
        for n in range(1, len(werte)):
            werte[n] += werte[n - 1]
    letzte = {r["k"]: r["d"] for r in con.execute(
        "SELECT s.konto_id AS k, MAX(b.datum) AS d FROM split s JOIN buchung b ON b.id = s.buchung_id"
        " JOIN konto k ON k.id = s.konto_id WHERE k.art IN ('aufwand', 'ertrag') GROUP BY s.konto_id")}

    # Unterkategorien aufrollen: je Kategorie die Menge ihres Teilbaums (Eltern gleicher Art)
    kinder: dict[int, list[int]] = defaultdict(list)
    for i, k in konten.items():
        e = k["eltern_id"]
        if e in konten and konten[e]["art"] == k["art"]:
            kinder[e].append(i)

    def teilbaum(i: int) -> list[int]:
        aus, offen = [], [i]
        while offen:
            x = offen.pop()
            aus.append(x)
            offen.extend(kinder.get(x, []))
        return aus

    zeilen = []
    summen = {"ausgaben": 0, "einnahmen": 0}
    for i in sorted(konten):
        t = teilbaum(i)
        menge: set[int] = set().union(*(buchungen.get(x, set()) for x in t))
        tage = [letzte[x] for x in t if x in letzte]
        zeilen.append({"id": i, "summe": sum(eigen.get(x, 0) for x in t), "eigen": eigen.get(i, 0),
                       "anzahl": len(menge), "letzte": max(tage) if tage else None,
                       "verlauf": [sum(verlauf[x][n] for x in t if x in verlauf) for n in range(len(verlauf_bis))]})
        summen["ausgaben" if konten[i]["art"] == "aufwand" else "einnahmen"] += eigen.get(i, 0)
    return {"zeitraum": zeitraum, "von": von, "bis": bis, "heute": heute, "verlauf_art": verlauf_art,
            "verlauf_bis": verlauf_bis,
            "kategorien": zeilen, "summen": summen,
            "unkategorisiert": {"konto_id": unk_id, "anzahl": unk_anzahl, "summe": unk_summe}}


__all__ = ["VORGABE", "ZEITRAEUME", "grenzen", "uebersicht"]
