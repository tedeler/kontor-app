"""Wiederkehrende Buchungen und unerwartete Buchungen (wiederkehrend.md, Meilenstein 5).

Die Erkennung ist eine Funktion des Buchbestands ohne eigenen Zustand: Bei jeder Abfrage werden die Einträge
(Buchung mit Empfänger × Bestandskonto) gebildet, je (Konto, Empfänger, Richtung) gruppiert und von der jüngsten
Zahlung rückwärts zu einer Kette mit dem Rhythmus monatlich, vierteljährlich oder jährlich verbunden. Nichts davon
wird gespeichert, protokolliert oder gesichert. Benachrichtigungen entstehen nur bei der Prüfung (4, 5); je
Ereignisschlüssel höchstens eine (gelesen oder nicht, E-100).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from . import buch
from .buch import ApiFehler
from .kredite import monat_plus
from .text import euro

T = 5
RHYTHMEN = (("monatlich", 1, 3), ("vierteljaehrlich", 3, 3), ("jaehrlich", 12, 2))
RHYTHMUS_TEXT = {"monatlich": "monatlich", "vierteljaehrlich": "vierteljährlich", "jaehrlich": "jährlich"}


@dataclass(frozen=True)
class Eintrag:
    konto_id: int
    empfaenger_id: int
    empfaenger_name: str
    richtung: str
    datum: str
    buchung_id: int
    betrag: int

    @property
    def gruppe(self) -> tuple[int, int, str]:
        return (self.konto_id, self.empfaenger_id, self.richtung)


def eintraege(con, stichtag: str | None = None, buchung_ids: list[int] | None = None) -> list[Eintrag]:
    """wiederkehrend.md 2.1 (sortiert nach Gruppe, Datum, Buchung)."""
    sql = ("SELECT b.id AS bid, b.datum AS datum, b.empfaenger_id AS eid, e.name AS ename, s.konto_id AS kid,"
           " SUM(s.betrag) AS x FROM buchung b JOIN empfaenger e ON e.id = b.empfaenger_id"
           " JOIN split s ON s.buchung_id = b.id JOIN konto k ON k.id = s.konto_id"
           " WHERE k.art IN ('girokonto','sparkonto','kreditkonto')"
           " AND NOT EXISTS (SELECT 1 FROM kredit kr WHERE kr.konto_id = s.konto_id)")
    par: list = []
    if stichtag is not None:
        sql += " AND b.datum <= ?"
        par.append(stichtag)
    if buchung_ids is not None:
        sql += f" AND b.id IN ({buch._platzhalter(len(buchung_ids))})"
        par.extend(buchung_ids)
    sql += " GROUP BY b.id, s.konto_id HAVING SUM(s.betrag) <> 0"
    aus = [Eintrag(r["kid"], r["eid"], r["ename"], "ausgabe" if r["x"] < 0 else "einnahme", r["datum"], r["bid"],
                   r["x"]) for r in con.execute(sql, par)]
    aus.sort(key=lambda e: (e.gruppe, e.datum, e.buchung_id))
    return aus


def gruppen(eintr: list[Eintrag]) -> dict[tuple[int, int, str], list[Eintrag]]:
    g: dict[tuple[int, int, str], list[Eintrag]] = defaultdict(list)
    for e in eintr:
        g[e.gruppe].append(e)
    for v in g.values():
        v.sort(key=lambda e: (e.datum, e.buchung_id))
    return g


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def serie(gruppe: list[Eintrag], stichtag: dt.date | None) -> dict | None:
    """wiederkehrend.md 2.2–2.4; ``None``, wenn die Gruppe keine Serie ist."""
    for name, m, mindest in RHYTHMEN:
        j = len(gruppe) - 1
        while j > 0 and abs((_d(gruppe[j].datum) - monat_plus(_d(gruppe[j - 1].datum), m)).days) <= T:
            j -= 1
        kette = gruppe[j:]
        if len(kette) < mindest:
            continue
        letzte = _d(kette[-1].datum)
        f, f2 = monat_plus(letzte, m), monat_plus(letzte, 2 * m)
        status = None
        if stichtag is not None:
            tol = dt.timedelta(days=T)
            status = "aktiv" if stichtag <= f + tol else "ausbleibend" if stichtag <= f2 + tol else "beendet"
        e0 = kette[-1]
        return {"schluessel": f"{e0.konto_id}:{e0.empfaenger_id}:{e0.richtung}", "konto_id": e0.konto_id,
                "empfaenger": {"id": e0.empfaenger_id, "name": e0.empfaenger_name}, "richtung": e0.richtung,
                "rhythmus": name, "anzahl": len(kette), "erste": kette[0].datum, "letzte": kette[-1].datum,
                "betrag": e0.betrag, "jahreskosten": -e0.betrag * (12 // m), "naechste_faelligkeit": f.isoformat(),
                "status": status, "buchung_ids": [e.buchung_id for e in kette]}
    return None


def uebersicht(con, stichtag: str) -> dict:
    """``GET /api/wiederkehrend`` (2.5)."""
    h = _d(stichtag)
    serien = []
    for _, g in sorted(gruppen(eintraege(con, stichtag)).items(),
                       key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] != "ausgabe")):
        s = serie(g, h)
        if s is not None:
            serien.append(s)
    return {"stichtag": stichtag, "serien": serien,
            "summe_jahreskosten": sum(s["jahreskosten"] for s in serien
                                      if s["richtung"] == "ausgabe" and s["status"] != "beendet")}


# ================================================================ Ereignisse


def _ereignisse(con, buchung_ids: list[int], heute: str) -> list[dict]:
    """wiederkehrend.md 3 in Entstehungsreihenfolge (ohne Entprellung): je Ereignis art, schluessel, titel, text,
    link."""
    aus: list[dict] = []
    ids = sorted(set(buchung_ids))
    if ids:
        alle = eintraege(con)
        g = gruppen(alle)
        je_buchung: dict[int, list[Eintrag]] = defaultdict(list)
        for e in alle:
            je_buchung[e.buchung_id].append(e)
        for teil in buch._stueckweise(ids):
            koepfe = {r["id"]: r for r in con.execute(
                "SELECT b.id, b.datum, b.empfaenger_id, e.name AS ename FROM buchung b"
                " LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                f" WHERE b.id IN ({buch._platzhalter(len(teil))})", teil)}
            for bid in teil:
                b = koepfe.get(bid)
                eig = sorted(je_buchung.get(bid, []), key=lambda e: e.konto_id)
                if b is None or not eig:
                    continue
                ausgabe = next((e for e in eig if e.richtung == "ausgabe"), None)
                if ausgabe is not None:
                    frueher = con.execute(
                        "SELECT 1 FROM buchung WHERE empfaenger_id = ? AND id <> ? AND (datum < ? OR (datum = ? AND id < ?))"
                        " LIMIT 1", (b["empfaenger_id"], bid, b["datum"], b["datum"], bid)).fetchone()
                    if frueher is None:
                        aus.append({"art": "neuer_empfaenger", "schluessel": f"neuer_empfaenger:{b['empfaenger_id']}",
                                    "titel": f"Neuer Empfänger: {b['ename']}",
                                    "text": f"Erste Zahlung an „{b['ename']}“ über {euro(ausgabe.betrag)} am "
                                            f"{_de(b['datum'])}. Bitte prüfen, ob die Buchung erwartet ist.",
                                    "link": f"/buchungen/{bid}"})
                for e in eig:
                    hist = [x for x in g[e.gruppe] if (x.datum, x.buchung_id) < (e.datum, e.buchung_id)]
                    s = serie(hist, None) if hist else None
                    if (s is not None and abs((_d(e.datum) - _d(s["naechste_faelligkeit"])).days) <= T
                            and e.betrag != s["betrag"]):
                        aus.append({"art": "wiederkehrend_betrag", "schluessel": f"wiederkehrend_betrag:{bid}",
                                    "titel": f"Geänderter Betrag: {e.empfaenger_name}",
                                    "text": f"Die {RHYTHMUS_TEXT[s['rhythmus']]}e Zahlung an bzw. von "
                                            f"„{e.empfaenger_name}“ am {_de(e.datum)} beträgt {euro(e.betrag)} statt "
                                            f"bisher {euro(s['betrag'])}.",
                                    "link": f"/buchungen/{bid}"})
                        break
    for s in uebersicht(con, heute)["serien"]:
        if s["status"] == "ausbleibend":
            aus.append({"art": "wiederkehrend_ausbleibend",
                        "schluessel": f"wiederkehrend_ausbleibend:{s['schluessel']}:{s['naechste_faelligkeit']}",
                        "titel": f"Zahlung ausgeblieben: {s['empfaenger']['name']}",
                        "text": f"Die {RHYTHMUS_TEXT[s['rhythmus']]}e Zahlung "
                                f"{'an' if s['richtung'] == 'ausgabe' else 'von'} „{s['empfaenger']['name']}“ über "
                                f"{euro(s['betrag'])}, fällig am {_de(s['naechste_faelligkeit'])}, ist nicht "
                                "eingegangen.",
                        "link": "/wiederkehrend"})
    return aus


def _de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def pruefen(con, buchung_ids: list[int], heute: str, jetzt: str) -> list[dict]:
    """Erzeugt die Benachrichtigungen neuer Ereignisse (4 Schritt 3) und gibt sie in Entstehungsreihenfolge
    zurück. ``con`` muss in einer Schreibtransaktion sein."""
    neu = []
    for e in _ereignisse(con, buchung_ids, heute):
        if con.execute("SELECT 1 FROM benachrichtigung WHERE schluessel = ? LIMIT 1", (e["schluessel"],)).fetchone():
            continue
        nid = con.execute("INSERT INTO benachrichtigung (art, schluessel, titel, text, link, erstellt_am, gelesen)"
                          " VALUES (?, ?, ?, ?, ?, ?, 0)",
                          (e["art"], e["schluessel"], e["titel"], e["text"], e["link"], jetzt)).lastrowid
        neu.append(buch._benachrichtigung_dict(
            con.execute("SELECT * FROM benachrichtigung WHERE id = ?", (nid,)).fetchone()))
    return neu


def pruefen_rest(con, buchung_ids: list[int], heute: str, jetzt: str) -> dict:
    """``POST /api/wiederkehrend/pruefen``."""
    fehlend = sorted(set(buchung_ids) - buch._vorhandene_buchungen(con, buchung_ids)) if buchung_ids else []
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    return {"stichtag": heute, "benachrichtigungen": pruefen(con, buchung_ids, heute, jetzt)}


__all__ = ["uebersicht", "pruefen"]
