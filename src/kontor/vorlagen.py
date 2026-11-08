"""Split-Vorlagen für Sammelabbuchungen (vorlagen.md, Meilenstein 4).

Eine Vorlage erkennt Buchungen über Bedingungen wie eine Regel (mindestens
eine auf den Empfänger, keine auf den Betrag) und teilt sie in feste
Teilbeträge auf. Es gibt keine Toleranz: Nur ein exakt passender
Gesamtbetrag ist ein Treffer, sonst eine Abweichung.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import buch, regeln
from .buch import BESTAND, KATEGORIEARTEN, ApiFehler, kontoarten, nicht_gefunden, sichere_id
from .validierung import BETRAG_MAX, Validierungsfehler, fehler_eintrag, ist_int, json_koerper

PRIO_MAX = 1_000_000
FELDER = ("empfaenger", "verwendungszweck", "konto_id")


# ============================================================== Validierung


def _teil_pruefen(t: Any, ort: list, fehler: list[dict]) -> dict | None:
    if not isinstance(t, dict):
        fehler.append(fehler_eintrag(ort, "Teil muss ein Objekt {kategorie_id, betrag, memo} sein."))
        return None
    ok = True
    for k in t:
        if k not in ("kategorie_id", "betrag", "memo"):
            fehler.append(fehler_eintrag(ort + [k], "Unbekanntes Feld."))
            ok = False
    for k in ("kategorie_id", "betrag"):
        if k not in t:
            fehler.append(fehler_eintrag(ort + [k], "Pflichtfeld fehlt."))
            ok = False
    if "kategorie_id" in t and not ist_int(t["kategorie_id"]):
        fehler.append(fehler_eintrag(ort + ["kategorie_id"], "Ganzzahl erwartet."))
        ok = False
    if "betrag" in t:
        b = t["betrag"]
        if not ist_int(b):
            fehler.append(fehler_eintrag(ort + ["betrag"], "Betrag muss eine Ganzzahl in Cent sein."))
            ok = False
        elif b == 0 or not -BETRAG_MAX <= b <= BETRAG_MAX:
            fehler.append(fehler_eintrag(ort + ["betrag"], "Betrag ungleich 0 im zulässigen Bereich erwartet."))
            ok = False
    memo = t.get("memo", "")
    if not isinstance(memo, str) or len(memo) > 10000:
        fehler.append(fehler_eintrag(ort + ["memo"], "Zeichenkette mit höchstens 10 000 Zeichen erwartet."))
        ok = False
    return {"kategorie_id": t["kategorie_id"], "betrag": t["betrag"], "memo": memo} if ok else None


def vorlage_koerper(roh: bytes, neu: bool) -> dict:
    """Prüft den Körper von POST/PATCH /api/vorlagen streng (422 ``validierung``)."""
    d = json_koerper(roh)
    if not isinstance(d, dict):
        raise Validierungsfehler([fehler_eintrag(["body"], "JSON-Objekt erwartet.")])
    fehler: list[dict] = []
    erlaubt = ("name", "aktiv", "prioritaet", "bedingungen", "teile")
    for k in d:
        if k not in erlaubt:
            fehler.append(fehler_eintrag(["body", k], "Unbekanntes Feld."))
    if neu:
        for k in ("name", "bedingungen", "teile"):
            if k not in d:
                fehler.append(fehler_eintrag(["body", k], "Pflichtfeld fehlt."))
    aus: dict[str, Any] = {}
    if "name" in d:
        n = d["name"]
        if not isinstance(n, str) or not 1 <= len(n.strip()) <= 200:
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
    if "bedingungen" in d:
        bs = d["bedingungen"]
        if not isinstance(bs, list):
            fehler.append(fehler_eintrag(["body", "bedingungen"], "Liste erwartet."))
        else:
            if not 1 <= len(bs) <= 20:
                fehler.append(fehler_eintrag(["body", "bedingungen"], "1 bis 20 Bedingungen erforderlich."))
            for i, b in enumerate(bs):
                ort = ["body", "bedingungen", i]
                if isinstance(b, dict) and b.get("feld") not in FELDER and "feld" in b:
                    fehler.append(fehler_eintrag(ort + ["feld"], "Erlaubt sind: empfaenger, verwendungszweck,"
                                                                 " konto_id (keine Betragsbedingung)."))
                    continue
                regeln._bedingung_pruefen(b, ort, fehler)
            if not any(isinstance(b, dict) and b.get("feld") == "empfaenger" for b in bs):
                fehler.append(fehler_eintrag(["body", "bedingungen"],
                                             "Mindestens eine Bedingung auf den Empfänger ist erforderlich."))
            aus["bedingungen"] = [{"feld": b["feld"], "operator": b["operator"], "wert": b["wert"]}
                                  for b in bs if isinstance(b, dict) and len(b) == 3
                                  and {"feld", "operator", "wert"} == set(b)]
    if "teile" in d:
        ts = d["teile"]
        if not isinstance(ts, list):
            fehler.append(fehler_eintrag(["body", "teile"], "Liste erwartet."))
        else:
            if not 2 <= len(ts) <= 50:
                fehler.append(fehler_eintrag(["body", "teile"], "2 bis 50 Teile erforderlich."))
            teile = [_teil_pruefen(t, ["body", "teile", i], fehler) for i, t in enumerate(ts)]
            if all(t is not None for t in teile) and teile and sum(t["betrag"] for t in teile) == 0:
                fehler.append(fehler_eintrag(["body", "teile"], "Die Summe der Teilbeträge darf nicht 0 sein."))
            aus["teile"] = [t for t in teile if t is not None]
    if fehler:
        raise Validierungsfehler(fehler)
    return aus


def _bezuege_pruefen(con, d: dict) -> None:
    if "teile" in d:
        for t in d["teile"]:
            r = buch.konto_zeile(con, t["kategorie_id"])
            if r is None or r["art"] not in KATEGORIEARTEN:
                raise ApiFehler(422, "kategorie_ungueltig",
                                "Jeder Teil braucht eine Kategorie (Aufwands- oder Ertragskonto).")
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


def vorlage_dict(r) -> dict:
    teile = json.loads(r["teile"])
    return {"id": r["id"], "name": r["name"], "aktiv": bool(r["aktiv"]), "prioritaet": r["prioritaet"],
            "bedingungen": json.loads(r["bedingungen"]), "teile": teile,
            "gesamtbetrag": -sum(t["betrag"] for t in teile)}


def vorlagen_liste(con) -> list[dict]:
    return [vorlage_dict(r) for r in con.execute("SELECT * FROM vorlage ORDER BY prioritaet, id")]


def vorlage_lesen(con, vid: int) -> dict:
    r = con.execute("SELECT * FROM vorlage WHERE id = ?", (sichere_id(vid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Die Vorlage")
    return vorlage_dict(r)


def _schreiben(con, v: dict) -> None:
    con.execute("UPDATE vorlage SET name = ?, aktiv = ?, prioritaet = ?, bedingungen = ?, teile = ? WHERE id = ?",
                (v["name"], 1 if v["aktiv"] else 0, v["prioritaet"], json.dumps(v["bedingungen"], ensure_ascii=False),
                 json.dumps(v["teile"], ensure_ascii=False), v["id"]))


def einfuegen(con, v: dict) -> int:
    """Legt eine Vorlage an (mit ``id``, falls angegeben – für Rückgängig)."""
    return con.execute(
        "INSERT INTO vorlage (id, name, aktiv, prioritaet, bedingungen, teile) VALUES (?, ?, ?, ?, ?, ?)",
        (v.get("id"), v["name"], 1 if v["aktiv"] else 0, v["prioritaet"],
         json.dumps(v["bedingungen"], ensure_ascii=False), json.dumps(v["teile"], ensure_ascii=False))).lastrowid


def vorlage_anlegen(con, d: dict) -> dict:
    _bezuege_pruefen(con, d)
    prio = d.get("prioritaet")
    if prio is None:
        r = con.execute("SELECT MAX(prioritaet) AS m FROM vorlage").fetchone()
        prio = 100 if r["m"] is None else min(r["m"] + 10, PRIO_MAX)
    vid = einfuegen(con, {"name": d["name"], "aktiv": d.get("aktiv", True), "prioritaet": prio,
                          "bedingungen": d["bedingungen"], "teile": d["teile"]})
    return vorlage_lesen(con, vid)


def vorlage_aendern(con, vid: int, d: dict) -> dict:
    alt = vorlage_lesen(con, vid)
    _bezuege_pruefen(con, d)
    neu = {**alt, **d}
    _schreiben(con, neu)
    return vorlage_lesen(con, vid)


def vorlage_loeschen(con, vid: int) -> None:
    vorlage_lesen(con, vid)
    con.execute("DELETE FROM vorlage WHERE id = ?", (vid,))


def verweist_auf(v: dict, konto_id: int) -> bool:
    return (any(t["kategorie_id"] == konto_id for t in v["teile"])
            or any(b["feld"] == "konto_id" and b["wert"] == konto_id for b in v["bedingungen"]))


def konto_in_vorlagen(con, konto_id: int) -> bool:
    return any(verweist_auf(v, konto_id) for v in vorlagen_liste(con))


def konto_loeschen(con, konto_id: int, ziel_id: int | None) -> None:
    """loeschen.md 6: Verweise auf ``konto_id`` auf ``ziel_id`` umstellen bzw. Vorlagen löschen."""
    for v in vorlagen_liste(con):
        if not verweist_auf(v, konto_id):
            continue
        if ziel_id is None:
            con.execute("DELETE FROM vorlage WHERE id = ?", (v["id"],))
            continue
        v["teile"] = [{**t, "kategorie_id": ziel_id} if t["kategorie_id"] == konto_id else t for t in v["teile"]]
        v["bedingungen"] = [{**b, "wert": ziel_id} if b["feld"] == "konto_id" and b["wert"] == konto_id else b
                            for b in v["bedingungen"]]
        _schreiben(con, v)


# =============================================================== Erkennung


@dataclass(frozen=True)
class Erkennung:
    art: str  # "treffer", "abweichung", "keine"
    vorlage: dict | None


KEINE = Erkennung("keine", None)


def aktive(con, vorlage_ids: list[int] | None = None) -> list[dict]:
    vs = [v for v in vorlagen_liste(con) if v["aktiv"]]
    if vorlage_ids is not None:
        erlaubt = set(vorlage_ids)
        vs = [v for v in vs if v["id"] in erlaubt]
    return vs


def erkennen(vorlagen: list[dict], sicht: regeln.Sicht) -> Erkennung:
    """vorlagen.md 3; ``vorlagen`` in Reihenfolge (Priorität, ID), nur aktive."""
    kandidaten = [v for v in vorlagen if all(regeln._trifft(b, sicht) for b in v["bedingungen"])]
    if not kandidaten:
        return KEINE
    for v in kandidaten:
        if v["gesamtbetrag"] == sicht.regelbetrag:
            return Erkennung("treffer", v)
    return Erkennung("abweichung", kandidaten[0])


def teile_splits(v: dict) -> list[dict]:
    return [{"konto_id": t["kategorie_id"], "betrag": t["betrag"], "memo": t["memo"]} for t in v["teile"]]


def anwenden(con, buchung_ids: list[int] | None, vorlage_ids: list[int] | None, nur_unkategorisiert: bool,
             trocken: bool) -> dict:
    """POST /api/vorlagen/anwenden (vorlagen.md 5)."""
    if buchung_ids is not None:
        fehlend = sorted(set(buchung_ids) - buch._vorhandene_buchungen(con, buchung_ids))
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    if vorlage_ids is not None:
        vorhanden = {r["id"] for r in con.execute("SELECT id FROM vorlage")}
        fehlend = sorted(set(vorlage_ids) - vorhanden)
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Vorlagen.", {"vorlage_ids": fehlend})
    vs = aktive(con, vorlage_ids)
    art_von = kontoarten(con)
    if buchung_ids is None:
        ids = [r["id"] for r in con.execute("SELECT id FROM buchung ORDER BY id")]
    else:
        ids = sorted(set(buchung_ids))
    geprueft = 0
    aenderungen, abweichungen = [], []
    for teil in buch._stueckweise(ids):
        for b in buch.buchungen_laden(con, teil, art_von=art_von):
            if buch.ist_gesperrt(b) or buch._gegensplit(b, art_von) is None:
                continue
            bestand = [s for s in b["splits"] if art_von[s["konto_id"]] in BESTAND]
            if len(bestand) != 1:
                continue
            if nur_unkategorisiert and b["kategorie_id"] is not None:
                continue
            geprueft += 1
            s = bestand[0]
            sicht = regeln.Sicht(b["empfaenger"]["name"] if b["empfaenger"] else None, b["verwendungszweck"],
                                 s["betrag"], {s["konto_id"]})
            e = erkennen(vs, sicht)
            if e.art == "treffer":
                aenderungen.append({"buchung_id": b["id"], "vorlage_id": e.vorlage["id"]})
                if not trocken:
                    _aufteilen(con, b["id"], s, e.vorlage)
            elif e.art == "abweichung":
                abweichungen.append({"buchung_id": b["id"], "vorlage_id": e.vorlage["id"], "betrag": s["betrag"],
                                     "gesamtbetrag": e.vorlage["gesamtbetrag"]})
    return {"geprueft": geprueft, "anzahl": len(aenderungen), "trocken": trocken, "aenderungen": aenderungen,
            "abweichungen": abweichungen}


def _aufteilen(con, bid: int, s: dict, v: dict) -> None:
    """Bestandskonto-Split bleibt (ID, Betrag, Memo) an erster Stelle, danach die Teile (neue Split-IDs)."""
    con.execute("DELETE FROM split WHERE buchung_id = ? AND id <> ?", (bid, s["id"]))
    con.execute("UPDATE split SET position = 0 WHERE id = ?", (s["id"],))
    con.executemany("INSERT INTO split (buchung_id, position, konto_id, betrag, memo) VALUES (?, ?, ?, ?, ?)",
                    [(bid, i + 1, t["konto_id"], t["betrag"], t["memo"]) for i, t in enumerate(teile_splits(v))])
    buch.vorschlag_entfernen(con, [bid])


__all__ = ["vorlage_koerper", "vorlagen_liste", "vorlage_lesen", "vorlage_anlegen", "vorlage_aendern",
           "vorlage_loeschen", "erkennen", "anwenden", "konto_in_vorlagen", "konto_loeschen"]
