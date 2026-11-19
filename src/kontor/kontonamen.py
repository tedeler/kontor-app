"""Eindeutige Kontonamen je Hierarchieebene (D-218).

Unter demselben Elternkonto darf ein Name nur einmal vorkommen; verglichen wird ohne Groß-/Kleinschreibung und
ohne Leerraum am Rand (``schluessel``). Auf der obersten Ebene gilt das je Kontoklasse (Bestand, Aufwand, Ertrag,
Eigenkapital), weil jede Klasse ihren eigenen Baum bildet.

- ``pruefen`` lehnt einen Zustand mit gleichnamigen Geschwistern ab (409 ``konto_existiert``); ``protokoll.
  protokolliert`` ruft es am Ende jeder Änderung auf, die Konten berührt.
- ``bereinigen`` stellt die Eindeutigkeit her: gleichnamige Kategorien werden zusammengeführt, alle anderen
  Konten (Bestandskonten, Eigenkapital, Kategorien mit Kreditbezug) bekommen einen Zusatz „(2)“. Benutzt beim
  Start (Altbestand), nach Importen und nach dem Einspielen einer Sicherung.
"""

from __future__ import annotations

from collections import defaultdict

from . import db
from .validierung import ApiFehler

_KLASSE = {"girokonto": "bestand", "sparkonto": "bestand", "kreditkonto": "bestand",
           "aufwand": "aufwand", "ertrag": "ertrag", "eigenkapital": "eigenkapital"}
_KATEGORIEN = ("aufwand", "ertrag")
NAME_MAX = 200
BESCHREIBUNG = "Gleichnamige Konten bereinigt"


def schluessel(name: str) -> str:
    return name.strip().casefold()


def _ebene(art: str, eltern_id: int | None) -> tuple:
    return (eltern_id, _KLASSE[art] if eltern_id is None else None)


def _konten(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, name, art, eltern_id, extern_id FROM konto ORDER BY id")]


def doppelte(con) -> list[list[dict]]:
    """Gruppen gleichnamiger Geschwister (je Gruppe nach ID sortiert), nach kleinster ID geordnet."""
    gruppen: dict[tuple, list[dict]] = defaultdict(list)
    for k in _konten(con):
        gruppen[(*_ebene(k["art"], k["eltern_id"]), schluessel(k["name"]))].append(k)
    return [g for g in gruppen.values() if len(g) > 1]


def pruefen(con) -> None:
    """409 ``konto_existiert``, wenn es gleichnamige Konten auf einer Ebene gibt."""
    gruppen = doppelte(con)
    if not gruppen:
        return
    g = gruppen[0]
    if g[0]["eltern_id"] is None:
        ort = "Auf der obersten Ebene"
    else:
        eltern = con.execute("SELECT name FROM konto WHERE id = ?", (g[0]["eltern_id"],)).fetchone()
        ort = f"Unter „{eltern['name']}“"
    raise ApiFehler(409, "konto_existiert", f"{ort} gibt es bereits ein Konto mit dem Namen „{g[0]['name']}“."
                    " Namen dürfen auf einer Ebene nur einmal vorkommen.",
                    {"konto_ids": sorted(k["id"] for gr in gruppen for k in gr)})


def freier_name(con, name: str, art: str, eltern_id: int | None, eigene_id: int | None = None) -> str:
    """``name`` oder, wenn auf der Ebene vergeben, ``name (2)``, ``name (3)`` …"""
    ebene = _ebene(art, eltern_id)
    belegt = {schluessel(k["name"]) for k in _konten(con)
              if k["id"] != eigene_id and _ebene(k["art"], k["eltern_id"]) == ebene}
    if schluessel(name) not in belegt:
        return name
    n = 2
    while True:
        zusatz = f" ({n})"
        kandidat = name.strip()[:NAME_MAX - len(zusatz)].rstrip() + zusatz
        if schluessel(kandidat) not in belegt:
            return kandidat
        n += 1


def _umbenennen(con, k: dict) -> dict:
    neu = freier_name(con, k["name"], k["art"], k["eltern_id"], k["id"])
    con.execute("UPDATE konto SET name = ? WHERE id = ?", (neu, k["id"]))
    return {"art": "umbenannt", "konto_id": k["id"], "name_alt": k["name"], "name": neu}


def _zusammenfuehren(con, ziel: dict, quelle: dict) -> dict | None:
    from . import buch, kredite, pflege
    try:
        kredite.konto_pruefen(con, quelle["id"])
    except ApiFehler:
        return None
    konten = {i: buch.konto_dict(buch.konto_zeile(con, i)) for i in (ziel["id"], quelle["id"])}
    betroffen = sorted(r["buchung_id"] for r in con.execute(
        "SELECT DISTINCT buchung_id FROM split WHERE konto_id = ?", (quelle["id"],)))
    pflege._zusammenfuehren_ausfuehren(con, konten, [quelle["id"]], ziel["id"], True, betroffen, [])
    return {"art": "zusammengefuehrt", "konto_id": quelle["id"], "ziel_id": ziel["id"], "name": quelle["name"]}


def bereinigen(con) -> list[dict]:
    """Stellt die Eindeutigkeit her (innerhalb der laufenden Transaktion) und berichtet, was geschah.

    Ziel einer Zusammenführung ist das Konto mit der kleinsten ID. Unterkategorien wandern mit unter das Ziel;
    entstehen dadurch neue gleichnamige Geschwister, werden auch sie bereinigt."""
    bericht: list[dict] = []
    while True:
        gruppen = doppelte(con)
        if not gruppen:
            return bericht
        for g in gruppen:
            # technische Konten („Unkategorisiert“, „Korrekturen“) behalten ihren Namen
            g.sort(key=lambda k: (not (k["extern_id"] or "").startswith("kontor:"), k["id"]))
            ziel = g[0]
            for k in g[1:]:
                if con.execute("SELECT 1 FROM konto WHERE id = ?", (k["id"],)).fetchone() is None:
                    continue
                schritt = _zusammenfuehren(con, ziel, k) if k["art"] in _KATEGORIEN else None
                bericht.append(schritt or _umbenennen(con, k))


def altbestand_bereinigen(pfad) -> list[dict]:
    """Beim Start: gleichnamige Konten des Bestands einmalig bereinigen (eine Änderung im Protokoll)."""
    from . import protokoll
    con = db.verbinde(pfad)
    try:
        if not doppelte(con):
            return []
        bericht: list[dict] = []
        with protokoll.protokolliert(con, "manuell", "kategorien_zusammenfuehren", db.jetzt_utc(),
                                     beschreibung=BESCHREIBUNG):
            bericht.extend(bereinigen(con))
        return bericht
    finally:
        con.close()
