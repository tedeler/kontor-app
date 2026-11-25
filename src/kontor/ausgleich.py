"""Ausgleichsbuchungen des Saldoabgleichs aufräumen (Feature ``ausgleich-aufraeumen``, D-280, kontostand.md 5).

Der Saldoabgleich (``sync._saldo_abgleichen``) bucht je Lauf seine Differenz gegen „Korrekturen“. Meldet die Bank den
neuen Kontostand vor dem Umsatz (oder steht eine eigene Buchung vor der Bank im Buch), entstehen kurz nacheinander
zwei Ausgleichsbuchungen, die sich ganz oder teilweise aufheben. Regeln für zwei Ausgleichsbuchungen desselben Kontos
im Abstand von höchstens ``FRIST_TAGE``:

- Summe 0: Das Paar entfällt ohne Nachfrage – beim Abruf (statt die zweite zu buchen, wird die erste gelöscht), nach
  einem Zusammenführen und einmalig für den Altbestand.
- Summe ungleich 0: Die Oberfläche fragt, ob beide zu einer Buchung mit der Summe zusammengeführt werden.

Als Ausgleichsbuchung gilt nur, was noch so dasteht, wie der Abgleich es gebucht hat: Kennung ``saldo:…``, genau
zwei Splits (Konto und „Korrekturen“), nicht abgestimmt oder abgeglichen. Von Hand umgebuchte bleiben unberührt.
Die Entscheidung „getrennt lassen“ ist Betriebszustand in ``meta`` (nicht im Protokoll, nicht in der Sicherung).
"""

from __future__ import annotations

import datetime as dt
import json

from . import buch, db, pflege
from .validierung import ApiFehler

FRIST_TAGE = 7
_GETRENNT = "saldo_paare_getrennt"
_ALTBESTAND = "saldo_altbestand_aufgeraeumt"
BESCHREIBUNG_ALTBESTAND = "Ausgleichsbuchungen aufgehoben (Altbestand)"


def buchungen(con, konto_id: int | None = None) -> list[dict]:
    """Unveränderte Ausgleichsbuchungen (alle Konten oder eines), nach Konto, Datum, Nummer."""
    korrektur = con.execute("SELECT id FROM konto WHERE extern_id = ?", (pflege.KORREKTUR,)).fetchone()
    if korrektur is None:
        return []
    zeilen = con.execute(
        "SELECT b.id AS id, b.datum AS datum, s.konto_id AS konto_id, s.betrag AS betrag FROM buchung b"
        " JOIN split s ON s.buchung_id = b.id AND s.konto_id <> :k"
        " JOIN split g ON g.buchung_id = b.id AND g.konto_id = :k AND g.betrag = -s.betrag"
        " WHERE b.status <> 'abgeglichen' AND s.betrag <> 0"
        " AND b.id IN (SELECT buchung_id FROM buchung_extern WHERE extern_id LIKE 'saldo:%')"
        " AND (SELECT COUNT(*) FROM split x WHERE x.buchung_id = b.id) = 2"
        + (" AND s.konto_id = :konto" if konto_id is not None else "")
        + " ORDER BY s.konto_id, b.datum, b.id", {"k": korrektur["id"], "konto": konto_id}).fetchall()
    return [dict(z) for z in zeilen if not buch.ist_gesperrt(buch.buchung_lesen(con, z["id"]))]


def _tage(a: str, b: str) -> int:
    return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)


def gegenstueck(con, konto_id: int, stichtag: str, differenz: int) -> int | None:
    """Die jüngste Ausgleichsbuchung des Kontos innerhalb der Frist, die ``differenz`` genau aufhebt."""
    passend = [b for b in buchungen(con, konto_id)
               if b["betrag"] == -differenz and _tage(b["datum"], stichtag) <= FRIST_TAGE]
    return passend[-1]["id"] if passend else None


def aufraeumen(con) -> list[list[int]]:
    """Paare mit Summe 0 innerhalb der Frist löschen (älteste zuerst, jede Buchung höchstens einmal)."""
    paare: list[list[int]] = []
    alle = buchungen(con)
    weg: set[int] = set()
    for i, a in enumerate(alle):
        if a["id"] in weg:
            continue
        for b in alle[i + 1:]:
            if b["konto_id"] != a["konto_id"] or _tage(a["datum"], b["datum"]) > FRIST_TAGE:
                break
            if b["id"] not in weg and b["betrag"] == -a["betrag"]:
                weg.update((a["id"], b["id"]))
                paare.append([a["id"], b["id"]])
                break
    for bid in sorted(weg):
        buch.buchung_loeschen(con, bid)
    return paare


def _getrennt(con) -> set[tuple[int, int]]:
    r = con.execute("SELECT wert FROM meta WHERE schluessel = ?", (_GETRENNT,)).fetchone()
    try:
        return {(int(a), int(b)) for a, b in json.loads(r["wert"])} if r else set()
    except (ValueError, TypeError):
        return set()


def paare(con) -> list[dict]:
    """Offene Paare mit Summe ungleich 0: aufeinanderfolgende Ausgleichsbuchungen eines Kontos innerhalb der Frist,
    über die noch nicht entschieden wurde."""
    getrennt = _getrennt(con)
    alle = buchungen(con)
    erg: list[dict] = []
    i = 0
    while i + 1 < len(alle):
        a, b = alle[i], alle[i + 1]
        if (a["konto_id"] != b["konto_id"] or _tage(a["datum"], b["datum"]) > FRIST_TAGE
                or a["betrag"] + b["betrag"] == 0 or (a["id"], b["id"]) in getrennt):
            i += 1
            continue
        name = con.execute("SELECT name FROM konto WHERE id = ?", (a["konto_id"],)).fetchone()["name"]
        erg.append({"konto_id": a["konto_id"], "konto_name": name, "summe": a["betrag"] + b["betrag"],
                    "buchungen": [{"id": x["id"], "datum": x["datum"], "betrag": x["betrag"]} for x in (a, b)]})
        i += 2
    return erg


def _paar(con, ids: list[int]) -> tuple[dict, dict]:
    gefunden = {b["id"]: b for b in buchungen(con)}
    a, b = (gefunden.get(i) for i in sorted(ids))
    if (a is None or b is None or a["konto_id"] != b["konto_id"] or _tage(a["datum"], b["datum"]) > FRIST_TAGE):
        raise ApiFehler(409, "kein_ausgleichspaar",
                        "Die beiden Buchungen sind kein Paar von Ausgleichsbuchungen desselben Kontos innerhalb "
                        f"von {FRIST_TAGE} Tagen (oder wurden inzwischen geändert).")
    return (a, b) if (a["datum"], a["id"]) <= (b["datum"], b["id"]) else (b, a)


def zusammenfuehren(con, ids: list[int]) -> dict:
    """Zwei Ausgleichsbuchungen zu einer mit der Summe: die spätere bleibt (Datum, Status, Kennung), die frühere
    entfällt. Bei Summe 0 entfallen beide. Danach entfallen Paare, die sich nun genau aufheben."""
    frueh, spaet = _paar(con, ids)
    summe = frueh["betrag"] + spaet["betrag"]
    buch.buchung_loeschen(con, frueh["id"])
    if summe == 0:
        buch.buchung_loeschen(con, spaet["id"])
    else:
        buch.splits_schreiben(con, spaet["id"], [{"konto_id": spaet["konto_id"], "betrag": summe, "memo": ""},
                                                 {"konto_id": pflege.korrektur_id(con), "betrag": -summe, "memo": ""}])
    aufgehoben = aufraeumen(con)
    bleibt = summe != 0 and not any(spaet["id"] in p for p in aufgehoben)
    return {"buchung_id": spaet["id"] if bleibt else None, "summe": summe, "konto_id": spaet["konto_id"]}


def getrennt_lassen(con, ids: list[int]) -> None:
    """Entscheidung merken: über dieses Paar nicht mehr fragen (Betriebszustand; Transaktion beim Aufrufer)."""
    frueh, spaet = _paar(con, ids)
    gemerkt = _getrennt(con) | {(frueh["id"], spaet["id"])}
    con.execute("INSERT INTO meta (schluessel, wert) VALUES (?, ?) ON CONFLICT(schluessel) DO UPDATE SET"
                " wert = excluded.wert", (_GETRENNT, json.dumps(sorted(gemerkt))))


def altbestand_aufraeumen(pfad) -> list[list[int]]:
    """Beim Start, einmalig je Datenbank: Paare mit Summe 0 aus der Zeit vor D-280 entfernen (eine Änderung)."""
    from . import protokoll
    con = db.verbinde(pfad)
    try:
        if con.execute("SELECT 1 FROM meta WHERE schluessel = ?", (_ALTBESTAND,)).fetchone():
            return []
        entfernt: list[list[int]] = []
        with protokoll.protokolliert(con, "manuell", "saldoausgleich_aufraeumen", db.jetzt_utc(),
                                     beschreibung=BESCHREIBUNG_ALTBESTAND):
            entfernt.extend(aufraeumen(con))
            con.execute("INSERT OR IGNORE INTO meta (schluessel, wert) VALUES (?, '1')", (_ALTBESTAND,))
        return entfernt
    finally:
        con.close()
