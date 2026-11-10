"""Sammelpaket: Buchungen von einem Bestandskonto auf ein anderes verschieben (D-110).

Verschoben wird je Buchung der Split auf dem Quellkonto; Betrag, Memo, Gegensplits, Status, Tags und
Herkunftskennungen bleiben. Die Auswahl ist entweder eine Liste von Buchungen oder die Herkunft (Gruppe eines
Imports ``import:<id>`` oder Synchronisationslaufs ``sync:<id>``) – dann alle noch vorhandenen Buchungen, die diese
Herkunft angelegt hat und die einen Split auf dem Quellkonto haben.
"""

from __future__ import annotations

import re
from typing import Any

from . import buch
from .validierung import ApiFehler

_GRUPPE = re.compile(r"^(import|sync):(\d+)$")


def _bestandskonto(con, konto_id: int, feld: str) -> dict:
    r = buch.konto_zeile(con, konto_id)
    if r is None:
        raise ApiFehler(422, "referenz_unbekannt", "Das Konto existiert nicht.", {"feld": feld})
    if r["art"] not in buch.BESTAND:
        raise ApiFehler(422, "konto_ungueltig", "Verschieben ist nur zwischen Bestandskonten möglich.",
                        {"feld": feld})
    return buch.konto_dict(r)


def _angelegt_von(con, gruppe: str) -> set[int]:
    """IDs der Buchungen, die eine Änderung dieser Gruppe angelegt hat (unabhängig davon, ob sie noch existieren)."""
    return {r["objekt_id"] for r in con.execute(
        "SELECT e.objekt_id FROM aenderung a JOIN aenderung_eintrag e ON e.aenderung_id = a.id"
        " WHERE a.gruppe = ? AND e.objekt = 'buchung' AND e.art = 'angelegt'", (gruppe,))}


def _auf_konto(con, konto_id: int) -> set[int]:
    return {r["buchung_id"] for r in con.execute("SELECT DISTINCT buchung_id FROM split WHERE konto_id = ?",
                                                (konto_id,))}


def _gruppe_text(con, gruppe: str) -> tuple[str, str | None]:
    m = _GRUPPE.match(gruppe)
    if m is None:
        return gruppe, None
    art, nr = m.group(1), int(m.group(2))
    if art == "import":
        r = con.execute("SELECT art, dateiname, importiert_am FROM importvorgang WHERE id = ?", (nr,)).fetchone()
        if r is None:
            return f"Import {nr}", None
        name = {"kmymoney": "KMyMoney", "gnucash": "GnuCash"}.get(r["art"], r["art"])
        return f"{name}-Import {r['dateiname'] or ''}".strip(), r["importiert_am"]
    r = con.execute("SELECT gestartet_am FROM sync_lauf WHERE id = ?", (nr,)).fetchone()
    return f"Synchronisation #{nr}", (r["gestartet_am"] if r else None)


def herkunft(con, konto_id: int) -> list[dict]:
    """``GET /api/konten/{id}/herkunft``: Importe und Synchronisationsläufe mit Buchungen auf diesem Konto."""
    buch.konto_lesen(con, konto_id)  # 404
    auf = _auf_konto(con, konto_id)
    je: dict[str, set[int]] = {}
    for r in con.execute(
            "SELECT a.gruppe, e.objekt_id FROM aenderung a JOIN aenderung_eintrag e ON e.aenderung_id = a.id"
            " WHERE (a.gruppe LIKE 'import:%' OR a.gruppe LIKE 'sync:%')"
            " AND e.objekt = 'buchung' AND e.art = 'angelegt'"):
        if r["objekt_id"] in auf:
            je.setdefault(r["gruppe"], set()).add(r["objekt_id"])
    ergebnis = []
    for gruppe, ids in je.items():
        text, zeit = _gruppe_text(con, gruppe)
        ergebnis.append({"gruppe": gruppe, "art": gruppe.split(":", 1)[0], "beschreibung": text,
                         "zeitpunkt": zeit, "anzahl": len(ids)})
    ergebnis.sort(key=lambda e: (e["zeitpunkt"] or "", e["gruppe"]), reverse=True)
    return ergebnis


def verschieben(con, d: dict) -> dict:
    """``POST /api/buchungen/mehrfach/verschieben`` (D-110), atomar.

    Prüfreihenfolge: Quell- und Zielkonto (422 ``referenz_unbekannt`` / ``konto_ungueltig``; gleich → 422
    ``validierung`` schon in der Anfrageprüfung), unbekannte Buchungen bzw. Gruppe (422 ``referenz_unbekannt``), Buchungen ohne Split auf dem
    Quellkonto oder schon mit Split auf dem Zielkonto (422 ``verschieben_unmoeglich``), gesperrte Buchungen
    (409 ``buchung_gesperrt``)."""
    von, nach = d["von_konto_id"], d["nach_konto_id"]
    _bestandskonto(con, von, "von_konto_id")
    _bestandskonto(con, nach, "nach_konto_id")
    auf_von = _auf_konto(con, von)
    if "buchung_ids" in d:
        ids = sorted(d["buchung_ids"])
        fehlend = sorted(set(ids) - buch._vorhandene_buchungen(con, ids))
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
        ohne = [b for b in ids if b not in auf_von]
    else:
        angelegt = _angelegt_von(con, d["gruppe"])
        if not angelegt:
            raise ApiFehler(422, "referenz_unbekannt", "Keine Buchungen mit dieser Herkunft.")
        ids = sorted(angelegt & auf_von)
        ohne = []
    auf_nach = _auf_konto(con, nach)
    doppelt = [b for b in ids if b in auf_nach]
    if ohne or doppelt:
        raise ApiFehler(422, "verschieben_unmoeglich",
                        "Einige Buchungen liegen nicht auf dem Quellkonto oder schon auf dem Zielkonto.",
                        {"buchung_ids": sorted(set(ohne) | set(doppelt))})
    gesperrt = [b["id"] for b in buch.buchungen_laden(con, ids) if buch.ist_gesperrt(b)] if ids else []
    if gesperrt:
        raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen können nicht verschoben werden.",
                        {"buchung_ids": gesperrt})
    for teil in buch._stueckweise(ids):
        con.execute(f"UPDATE split SET konto_id = ? WHERE konto_id = ? AND buchung_id IN"
                    f" ({buch._platzhalter(len(teil))})", [nach, von, *(buch.sichere_id(x) for x in teil)])
    return {"verschoben": ids, "anzahl": len(ids)}


__all__: list[Any] = ["herkunft", "verschieben"]
