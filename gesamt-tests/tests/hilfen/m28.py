"""Hilfen für Meilenstein-28-Tests (Oberfläche aus ``feature/sammel``, ``oberflaeche.md`` 37, E-252 bis E-255).

Nur über die Spezifikation: ``data-testid``, ARIA-Attribute, Adressen und REST-Abfragen, deren Ergebnis der Test
selbst stellt (erwartete Listen, Summen der Periodenbalken).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from urllib.parse import parse_qs, urlsplit

from .m8 import tid

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
#: Reihenfolge der Einträge einer Buchungsauswahl (Desktop, ohne Alt, 37.9)
KM_REIHENFOLGE = ["km-kategorie", "km-tags", "km-splitten", "km-dublette", "km-vorschlag-annehmen",
                  "km-vorschlag-ablehnen", "km-bearbeiten", "km-status", "km-bestaetigen", "km-filter", "km-mehrfach",
                  "km-gegenbuchung", "km-dokument-anhaengen", "km-dokument-mail", "km-dokumente-ansehen",
                  "km-loeschen"]


def abfrage(seite) -> dict[str, list[str]]:
    return parse_qs(urlsplit(seite.url).query)


def menue(seite) -> list[str]:
    return tid(seite, "kontextmenue").locator('[role="menuitem"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")


TIEFEN = ("jahr", "monat", "abschnitt", "tag")


def abschnitt(datum: str) -> str:
    """M31 (oberflaeche.md 40.5): Abschnitt ``JJJJ-MM-a1`` … ``-a4`` (1.–7., 8.–14., 15.–21., 22.–Ende)."""
    tag = int(datum[8:10])
    return f"{datum[:7]}-a{min((tag - 1) // 7 + 1, 4)}"


def perioden_soll(buchungen: list[dict], *, absteigend: bool = True, tiefe: str = "tag") -> dict[str, dict]:
    """Schlüssel → {eingang, ausgang, summe, anzahl, ebene} aus dem Feld ``betrag`` der Buchungsliste (37.6);
    ab M31 mit der Ebene ``abschnitt`` zwischen Monat und Tag und bis zur gewählten Tiefe (40.5, E-287)."""
    ebenen = TIEFEN[:TIEFEN.index(tiefe) + 1]
    aus: dict[str, dict] = defaultdict(lambda: {"eingang": 0, "ausgang": 0, "summe": 0, "anzahl": 0})
    for b in buchungen:
        d = b["datum"]
        schluessel = {"jahr": d[:4], "monat": d[:7], "abschnitt": abschnitt(d), "tag": d}
        for ebene in ebenen:
            x = aus[schluessel[ebene]]
            x["ebene"] = ebene
            if b["betrag"] > 0:
                x["eingang"] += b["betrag"]
            else:
                x["ausgang"] += b["betrag"]
            x["summe"] += b["betrag"]
            x["anzahl"] += 1
    return dict(aus)


def perioden_text(schluessel: str) -> str:
    if len(schluessel) == 4:
        return schluessel
    if len(schluessel) == 7:
        return f"{MONATE[int(schluessel[5:]) - 1]} {schluessel[:4]}"
    if "-a" in schluessel:                    # M31: „08.–14.11.“, „22.–29.02.“ (40.5)
        import calendar

        j, m, n = int(schluessel[:4]), int(schluessel[5:7]), int(schluessel[-1])
        von = 7 * (n - 1) + 1
        bis = calendar.monthrange(j, m)[1] if n == 4 else 7 * n
        return f"{von:02d}.\u2013{bis:02d}.{m:02d}."
    return dt.date.fromisoformat(schluessel).strftime("%d.%m.%Y")


def anzahl_text(n: int) -> str:
    return "1 Buchung" if n == 1 else f"{n} Buchungen"


def balken(seite) -> list[tuple[str, str]]:
    """(Ebene, Schlüssel) der gezeichneten Periodenbalken in Dokumentreihenfolge."""
    return [tuple(x) for x in tid(seite, "buchungsliste").locator('[role="row"][data-periode]').evaluate_all(
        "els => els.map(e => [e.getAttribute('data-ebene'), e.getAttribute('data-periode')])")]  # Tupel (W-021)


def leere_woerter(text: str) -> list[str]:
    import re
    return re.findall(r"\b(null|None|undefined)\b", text)
