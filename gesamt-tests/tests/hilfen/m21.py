"""Hilfen für Meilenstein-21-Tests (Berichte mit Einzelbuchungen, Zoom; Sprungziel mittig) – oberflaeche.md 31."""

from __future__ import annotations

import datetime as dt

from .api import Api

VON, BIS = "2024-01-01", "2024-03-31"

#: Lage einer Zeile zur Mitte ihres Scrollbereichs (nächster senkrecht rollbarer Vorfahre, sonst das Fenster)
JS_LAGE = """id => {
    const row = document.querySelector(`[data-testid="buchung-${id}"]`);
    let c = row.parentElement;
    while (c && c !== document.body) {
        const s = getComputedStyle(c);
        if (/(auto|scroll)/.test(s.overflowY) && c.scrollHeight > c.clientHeight) break;
        c = c.parentElement;
    }
    const r = row.getBoundingClientRect();
    let oben, hoehe, kann, links;
    if (c && c !== document.body) {
        const b = c.getBoundingClientRect();
        oben = b.top; hoehe = c.clientHeight; links = c.scrollLeft;
        kann = c.scrollTop > 0 && c.scrollTop < c.scrollHeight - c.clientHeight - 1;
    } else {
        oben = 0; hoehe = window.innerHeight; links = window.scrollX;
        const se = document.scrollingElement;
        kann = se.scrollTop > 0 && se.scrollTop < se.scrollHeight - se.clientHeight - 1;
    }
    return {abstand: Math.abs((r.top + r.height / 2) - (oben + hoehe / 2)), zeile: r.height, kann, links,
            unten: r.bottom, oben: r.top};
}"""


def berichtsdaten(api: Api) -> dict:
    k = {"giro": api.konto("Girokonto")["id"], "spar": api.konto("Tagesgeld", "sparkonto")["id"],
         "leb": api.konto("Lebensmittel", "aufwand")["id"], "zins": api.konto("Zinsen", "ertrag")["id"]}
    markt = api.empfaenger("Markt (fiktiv)")["id"]
    g, s, leb, zins = k["giro"], k["spar"], k["leb"], k["zins"]
    b = {
        "b1": api.buchung("2024-01-01", [(g, -1000), (leb, 1000)], verwendungszweck="Neujahr")["id"],
        "b2": api.buchung("2024-01-15", [(g, -2000), (leb, 2000)], empfaenger_id=markt,
                          verwendungszweck="Wocheneinkauf")["id"],
        "b3": api.buchung("2024-01-15", [(g, -5000), (s, 5000)], verwendungszweck="Sparen")["id"],
        "b4": api.buchung("2024-03-10", [(s, 300), (zins, -300)], verwendungszweck="Zinsen")["id"],
        "b5": api.buchung("2024-03-10", [(leb, 300), (g, -400), (s, 100)], verwendungszweck="Gemischt")["id"],
        "spaet": api.buchung("2024-04-02", [(g, -50), (leb, 50)], verwendungszweck="Danach")["id"],
    }
    return {"k": k, "b": b}


def viele(api: Api, konto: int, gegen: int, anzahl: int = 300) -> list[int]:
    """``anzahl`` Buchungen an verschiedenen Tagen; Rückgabe nach Datum absteigend (Vorgabesortierung -datum)."""
    start = dt.date(2023, 1, 1)
    ids = [api.buchung((start + dt.timedelta(days=i)).isoformat(), [(konto, -(100 + i)), (gegen, 100 + i)],
                       verwendungszweck=f"Posten {i}")["id"] for i in range(anzahl)]
    return list(reversed(ids))


def de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"
