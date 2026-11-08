"""Regel-Kategorisierung und Vorschläge (kategorisierung.md, Meilenstein 2).

Regeln: feste Zuordnungen mit UND-verknüpften Bedingungen auf Empfänger,
Verwendungszweck, Regelbetrag und Konto. Reihenfolge: ``prioritaet``
aufsteigend, dann ``id``; die erste passende aktive Regel gewinnt. Gesetzte
Kategorien sind Vorschläge, bis sie bestätigt oder erledigt sind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import buch
from .buch import BESTAND, KATEGORIEARTEN, ApiFehler, kontoarten, nicht_gefunden, sichere_id
from .text import norm
from .validierung import BETRAG_MAX, Validierungsfehler, fehler_eintrag, ist_int, json_koerper

PRIO_MAX = 1_000_000
TEXTFELDER = ("empfaenger", "verwendungszweck")
TEXT_OPS = ("enthaelt", "gleich", "beginnt_mit")
BETRAG_OPS = ("gleich", "mindestens", "hoechstens")


# ============================================================== Validierung


def _bedingung_pruefen(b: Any, ort: list, fehler: list[dict]) -> None:
    if not isinstance(b, dict):
        fehler.append(fehler_eintrag(ort, "Bedingung muss ein Objekt {feld, operator, wert} sein."))
        return
    for k in b:
        if k not in ("feld", "operator", "wert"):
            fehler.append(fehler_eintrag(ort + [k], "Unbekanntes Feld."))
    for k in ("feld", "operator", "wert"):
        if k not in b:
            fehler.append(fehler_eintrag(ort + [k], "Pflichtfeld fehlt."))
    if any(k not in b for k in ("feld", "operator", "wert")):
        return
    feld, op, wert = b["feld"], b["operator"], b["wert"]
    if feld in TEXTFELDER:
        if op not in TEXT_OPS:
            fehler.append(fehler_eintrag(ort + ["operator"], f"Erlaubt sind: {', '.join(TEXT_OPS)}."))
        if not isinstance(wert, str):
            fehler.append(fehler_eintrag(ort + ["wert"], "Zeichenkette erwartet."))
        elif not 1 <= len(wert) <= 200 or not wert.strip():
            fehler.append(fehler_eintrag(ort + ["wert"], "1–200 Zeichen, nicht nur Leerraum."))
    elif feld == "betrag":
        if op not in BETRAG_OPS:
            fehler.append(fehler_eintrag(ort + ["operator"], f"Erlaubt sind: {', '.join(BETRAG_OPS)}."))
        if not ist_int(wert):
            fehler.append(fehler_eintrag(ort + ["wert"], "Betrag muss eine Ganzzahl in Cent sein."))
        elif not -BETRAG_MAX <= wert <= BETRAG_MAX:
            fehler.append(fehler_eintrag(ort + ["wert"], "Betrag liegt außerhalb des zulässigen Bereichs."))
    elif feld == "konto_id":
        if op != "gleich":
            fehler.append(fehler_eintrag(ort + ["operator"], "Erlaubt ist: gleich."))
        if not ist_int(wert):
            fehler.append(fehler_eintrag(ort + ["wert"], "Konto-ID (Ganzzahl) erwartet."))
    else:
        fehler.append(fehler_eintrag(ort + ["feld"], "Erlaubt sind: empfaenger, verwendungszweck, betrag, konto_id."))


def regel_koerper(roh: bytes, neu: bool) -> dict:
    """Prüft den Körper von POST/PATCH /api/regeln streng (422 ``validierung``)."""
    d = json_koerper(roh)
    fehler: list[dict] = []
    if not isinstance(d, dict):
        raise Validierungsfehler([fehler_eintrag(["body"], "JSON-Objekt erwartet.")])
    erlaubt = ("name", "aktiv", "prioritaet", "kategorie_id", "bedingungen")
    for k in d:
        if k not in erlaubt:
            fehler.append(fehler_eintrag(["body", k], "Unbekanntes Feld."))
    if neu:
        for k in ("name", "kategorie_id", "bedingungen"):
            if k not in d:
                fehler.append(fehler_eintrag(["body", k], "Pflichtfeld fehlt."))
    aus: dict[str, Any] = {}
    if "name" in d:
        n = d["name"]
        if not isinstance(n, str):
            fehler.append(fehler_eintrag(["body", "name"], "Zeichenkette erwartet."))
        elif not 1 <= len(n.strip()) <= 200:
            fehler.append(fehler_eintrag(["body", "name"], "1–200 Zeichen (ohne Rand-Leerraum)."))
        else:
            aus["name"] = n.strip()
    if "aktiv" in d:
        if not isinstance(d["aktiv"], bool):
            fehler.append(fehler_eintrag(["body", "aktiv"], "Wahrheitswert erwartet."))
        aus["aktiv"] = d["aktiv"]
    if "prioritaet" in d:
        p = d["prioritaet"]
        if not ist_int(p) or not 0 <= p <= PRIO_MAX:
            fehler.append(fehler_eintrag(["body", "prioritaet"], f"Ganzzahl von 0 bis {PRIO_MAX} erwartet."))
        aus["prioritaet"] = p
    if "kategorie_id" in d:
        if not ist_int(d["kategorie_id"]):
            fehler.append(fehler_eintrag(["body", "kategorie_id"], "Ganzzahl erwartet."))
        aus["kategorie_id"] = d["kategorie_id"]
    if "bedingungen" in d:
        bs = d["bedingungen"]
        if not isinstance(bs, list):
            fehler.append(fehler_eintrag(["body", "bedingungen"], "Liste erwartet."))
        else:
            if not 1 <= len(bs) <= 20:
                fehler.append(fehler_eintrag(["body", "bedingungen"], "1 bis 20 Bedingungen erforderlich."))
            for i, b in enumerate(bs):
                _bedingung_pruefen(b, ["body", "bedingungen", i], fehler)
            aus["bedingungen"] = [{"feld": b["feld"], "operator": b["operator"], "wert": b["wert"]}
                                  for b in bs if isinstance(b, dict) and len(b) == 3]
    if fehler:
        raise Validierungsfehler(fehler)
    return aus


def _bezuege_pruefen(con, d: dict) -> None:
    if "kategorie_id" in d:
        r = buch.konto_zeile(con, d["kategorie_id"])
        if r is None or r["art"] not in KATEGORIEARTEN:
            raise ApiFehler(422, "kategorie_ungueltig", "Die Kategorie muss ein Aufwands- oder Ertragskonto sein.")
    if "bedingungen" in d:
        unbekannt = []
        for b in d["bedingungen"]:
            if b["feld"] == "konto_id":
                r = buch.konto_zeile(con, b["wert"])
                if r is None or r["art"] not in BESTAND:
                    unbekannt.append(b["wert"])
        if unbekannt:
            raise ApiFehler(422, "referenz_unbekannt", "Eine Bedingung verweist auf kein Bestandskonto.",
                            {"konto_ids": sorted(set(unbekannt))})


# ===================================================================== CRUD


def regel_dict(r) -> dict:
    return {"id": r["id"], "name": r["name"], "aktiv": bool(r["aktiv"]), "prioritaet": r["prioritaet"],
            "kategorie_id": r["kategorie_id"], "bedingungen": json.loads(r["bedingungen"])}


def regeln_liste(con) -> list[dict]:
    return [regel_dict(r) for r in con.execute("SELECT * FROM regel ORDER BY prioritaet, id")]


def regel_lesen(con, rid: int) -> dict:
    r = con.execute("SELECT * FROM regel WHERE id = ?", (sichere_id(rid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Die Regel")
    return regel_dict(r)


def regel_anlegen(con, d: dict) -> dict:
    _bezuege_pruefen(con, d)
    prio = d.get("prioritaet")
    if prio is None:
        r = con.execute("SELECT MAX(prioritaet) AS m FROM regel").fetchone()
        prio = 100 if r["m"] is None else min(r["m"] + 10, PRIO_MAX)
    cur = con.execute("INSERT INTO regel (name, aktiv, prioritaet, kategorie_id, bedingungen) VALUES (?, ?, ?, ?, ?)",
                      (d["name"], 1 if d.get("aktiv", True) else 0, prio, d["kategorie_id"],
                       json.dumps(d["bedingungen"], ensure_ascii=False)))
    return regel_lesen(con, cur.lastrowid)


def regel_aendern(con, rid: int, d: dict) -> dict:
    alt = regel_lesen(con, rid)
    _bezuege_pruefen(con, d)
    neu = {**alt, **d}
    con.execute("UPDATE regel SET name = ?, aktiv = ?, prioritaet = ?, kategorie_id = ?, bedingungen = ? WHERE id = ?",
                (neu["name"], 1 if neu["aktiv"] else 0, neu["prioritaet"], neu["kategorie_id"],
                 json.dumps(neu["bedingungen"], ensure_ascii=False), rid))
    return regel_lesen(con, rid)


def regel_loeschen(con, rid: int) -> None:
    regel_lesen(con, rid)
    con.execute("UPDATE vorschlag SET regel_id = NULL WHERE regel_id = ?", (rid,))
    con.execute("DELETE FROM regel WHERE id = ?", (rid,))


# =============================================================== Auswertung


@dataclass
class Sicht:
    """Was eine Regel von einer Buchung sieht (kategorisierung.md 4)."""
    empfaenger: str | None
    verwendungszweck: str
    regelbetrag: int
    konten: set[int] = field(default_factory=set)


def _trifft(b: dict, s: Sicht) -> bool:
    feld, op, wert = b["feld"], b["operator"], b["wert"]
    if feld in TEXTFELDER:
        text = s.empfaenger if feld == "empfaenger" else s.verwendungszweck
        if text is None:
            return False
        t, w = norm(text), norm(wert)
        return (w in t) if op == "enthaelt" else (t == w) if op == "gleich" else t.startswith(w)
    if feld == "betrag":
        return (s.regelbetrag == wert if op == "gleich" else s.regelbetrag >= wert if op == "mindestens"
                else s.regelbetrag <= wert)
    if feld == "konto_id":
        return wert in s.konten
    return False


def aktive_regeln(con, regel_ids: list[int] | None = None) -> list[dict]:
    regeln = [r for r in regeln_liste(con) if r["aktiv"]]
    if regel_ids is not None:
        erlaubt = set(regel_ids)
        regeln = [r for r in regeln if r["id"] in erlaubt]
    return regeln


def erste_regel(regeln: list[dict], s: Sicht) -> dict | None:
    for r in regeln:
        if all(_trifft(b, s) for b in r["bedingungen"]):
            return r
    return None


def vorschlag_setzen(con, buchung_id: int, split_id: int, bisheriges_konto: int, regel: dict) -> None:
    """Setzt die Kategorie der Regel als Vorschlag (kategorisierung.md 5)."""
    con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (regel["kategorie_id"], split_id))
    alt = con.execute("SELECT vorher_konto_id FROM vorschlag WHERE buchung_id = ?", (buchung_id,)).fetchone()
    vorher = alt["vorher_konto_id"] if alt is not None else bisheriges_konto
    con.execute("INSERT INTO vorschlag (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id)"
                " VALUES (?, ?, ?, 'regel', ?) ON CONFLICT(buchung_id) DO UPDATE SET"
                " kategorie_id = excluded.kategorie_id, regel_id = excluded.regel_id, quelle = excluded.quelle,"
                " vorher_konto_id = excluded.vorher_konto_id",
                (buchung_id, regel["kategorie_id"], regel["id"], vorher))


def anwenden(con, buchung_ids: list[int] | None, regel_ids: list[int] | None, nur_unkategorisiert: bool,
             trocken: bool) -> dict:
    """POST /api/regeln/anwenden (kategorisierung.md 3)."""
    if buchung_ids is not None:
        fehlend = sorted(set(buchung_ids) - buch._vorhandene_buchungen(con, buchung_ids))
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    if regel_ids is not None:
        vorhanden = {r["id"] for r in con.execute("SELECT id FROM regel")}
        fehlend = sorted(set(regel_ids) - vorhanden)
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Regeln.", {"regel_ids": fehlend})
    regeln = aktive_regeln(con, regel_ids)
    art_von = kontoarten(con)
    if buchung_ids is None:
        ids = [r["id"] for r in con.execute("SELECT id FROM buchung WHERE status <> 'abgeglichen' ORDER BY id")]
    else:
        ids = sorted(set(buchung_ids))
    geprueft = 0
    aenderungen = []
    for teil in buch._stueckweise(ids):
        for b in buch.buchungen_laden(con, teil, art_von=art_von):
            if b["status"] == "abgeglichen":
                continue
            gegen = buch._gegensplit(b, art_von)
            if gegen is None:
                continue
            if nur_unkategorisiert and b["kategorie_id"] is not None:
                continue
            geprueft += 1
            bestand = [s for s in b["splits"] if art_von[s["konto_id"]] in BESTAND]
            sicht = Sicht(b["empfaenger"]["name"] if b["empfaenger"] else None, b["verwendungszweck"],
                          sum(s["betrag"] for s in bestand), {s["konto_id"] for s in bestand})
            r = erste_regel(regeln, sicht)
            if r is None or gegen["konto_id"] == r["kategorie_id"]:
                continue
            aenderungen.append({"buchung_id": b["id"], "regel_id": r["id"], "kategorie_id": r["kategorie_id"]})
            if not trocken:
                vorschlag_setzen(con, b["id"], gegen["id"], gegen["konto_id"], r)
    return {"geprueft": geprueft, "anzahl": len(aenderungen), "trocken": trocken, "aenderungen": aenderungen}


# ================================================================ Vorschläge


def _entscheiden(con, b: dict, aktion: str, art_von: dict[int, str]) -> None:
    v = b["vorschlag"]
    if aktion == "ablehnen":
        gegen = buch._gegensplit(b, art_von)
        ziel = v["vorher_konto_id"]
        if buch.konto_zeile(con, ziel) is None:
            ziel = buch.unkategorisiert_id(con)
        if gegen is not None:
            con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (ziel, gegen["id"]))
    buch.vorschlag_entfernen(con, [b["id"]])


def vorschlag_entscheiden(con, bid: int, aktion: str) -> dict:
    b = buch.buchung_lesen(con, bid)
    if b["status"] == "abgeglichen":
        raise buch._gesperrt()
    if b["vorschlag"] is None:
        raise ApiFehler(409, "kein_vorschlag", "Die Buchung hat keinen offenen Vorschlag.")
    art_von = kontoarten(con)
    _entscheiden(con, b, aktion, art_von)
    return buch.buchung_lesen(con, bid)


def mehrfach_vorschlag(con, ids: list[int], aktion: str) -> dict:
    fehlend = sorted(set(ids) - buch._vorhandene_buchungen(con, ids))
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    art_von = kontoarten(con)
    buchungen = buch.buchungen_laden(con, sorted(ids), art_von=art_von)
    ohne = [b["id"] for b in buchungen if b["vorschlag"] is None]
    if ohne:
        raise ApiFehler(409, "kein_vorschlag", "Einige Buchungen haben keinen offenen Vorschlag.",
                        {"buchung_ids": ohne})
    for b in buchungen:
        _entscheiden(con, b, aktion, art_von)
    return {"geaendert": sorted(ids), "anzahl": len(ids)}
