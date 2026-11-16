"""Regel-Kategorisierung und Vorschläge (kategorisierung.md, Meilenstein 2).

Regeln: feste Zuordnungen mit UND-verknüpften Bedingungen auf Empfänger,
Verwendungszweck, Regelbetrag und Konto – oder (D-175) mit einem Ausdruck der Kontor-Ausdruckssprache
(``ausdruck.py``). Ein Ausdruck wird als einzige Bedingung ``{"feld": "ausdruck", "operator": "ausdruck",
"wert": <Baum>}`` in ``bedingungen`` gespeichert; der Baum hält Verweise als IDs. Reihenfolge: ``prioritaet``
aufsteigend, dann ``id``; die erste passende aktive Regel gewinnt. Gesetzte
Kategorien sind Vorschläge, bis sie bestätigt oder erledigt sind.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from . import ausdruck, buch
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


AUSDRUCK = "ausdruck"


def ist_ausdruck(bedingungen: list) -> bool:
    return len(bedingungen) == 1 and isinstance(bedingungen[0], dict) and bedingungen[0].get("feld") == AUSDRUCK


def baum(bedingungen: list) -> dict | None:
    return bedingungen[0]["wert"] if ist_ausdruck(bedingungen) else None


def konto_verweise(bedingungen: list) -> set[int]:
    """Alle Konten (Bestandskonten und Kategorien), auf die Bedingungen verweisen."""
    b = baum(bedingungen)
    if b is not None:
        return ausdruck.verweise(b, "konto") | ausdruck.verweise(b, "kategorie")
    return {x["wert"] for x in bedingungen if isinstance(x, dict) and x.get("feld") == "konto_id"}


def konto_verweise_ersetzen(bedingungen: list, alt: int, neu: int) -> list:
    b = baum(bedingungen)
    if b is not None:
        b = ausdruck.verweise_ersetzen(ausdruck.verweise_ersetzen(b, "konto", alt, neu), "kategorie", alt, neu)
        return [{"feld": AUSDRUCK, "operator": AUSDRUCK, "wert": b}]
    return [{**x, "wert": neu} if x["feld"] == "konto_id" and x["wert"] == alt else x for x in bedingungen]


def regel_koerper(roh: bytes, neu: bool, intern: bool = False) -> dict:
    """Prüft den Körper von POST/PATCH /api/regeln streng (422 ``validierung``).

    ``ausdruck`` (Text) ersetzt ``bedingungen`` (D-175); genau eines von beiden. ``intern``: Prüfung einer
    Sicherung, dort darf ``bedingungen`` die gespeicherte Ausdrucksform enthalten."""
    d = json_koerper(roh)
    fehler: list[dict] = []
    if not isinstance(d, dict):
        raise Validierungsfehler([fehler_eintrag(["body"], "JSON-Objekt erwartet.")])
    erlaubt = ("name", "aktiv", "prioritaet", "kategorie_id", "bedingungen", "ausdruck")
    for k in d:
        if k not in erlaubt:
            fehler.append(fehler_eintrag(["body", k], "Unbekanntes Feld."))
    if neu:
        for k in ("name", "kategorie_id"):
            if k not in d:
                fehler.append(fehler_eintrag(["body", k], "Pflichtfeld fehlt."))
        if "bedingungen" not in d and "ausdruck" not in d:
            fehler.append(fehler_eintrag(["body", "bedingungen"], "Pflichtfeld fehlt (oder „ausdruck“)."))
    if "bedingungen" in d and "ausdruck" in d:
        fehler.append(fehler_eintrag(["body", "ausdruck"], "Nur eines von „bedingungen“ und „ausdruck“."))
    if "ausdruck" in d:
        a = d["ausdruck"]
        if not isinstance(a, str):
            fehler.append(fehler_eintrag(["body", "ausdruck"], "Zeichenkette erwartet."))
        elif not a.strip() or len(a) > ausdruck.MAX_AUSDRUCK:
            fehler.append(fehler_eintrag(["body", "ausdruck"], f"1–{ausdruck.MAX_AUSDRUCK} Zeichen, nicht nur Leerraum."))

    aus: dict[str, Any] = {}
    if "ausdruck" in d and isinstance(d["ausdruck"], str):
        aus["ausdruck"] = d["ausdruck"]
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
            if intern and ist_ausdruck(bs):
                if set(bs[0]) != {"feld", "operator", "wert"} or not isinstance(bs[0]["wert"], dict):
                    fehler.append(fehler_eintrag(["body", "bedingungen", 0], "Ungültige Ausdrucksform."))
                aus["bedingungen"] = bs
            else:
                for i, b in enumerate(bs):
                    _bedingung_pruefen(b, ["body", "bedingungen", i], fehler)
                aus["bedingungen"] = [{"feld": b["feld"], "operator": b["operator"], "wert": b["wert"]}
                                      for b in bs if isinstance(b, dict) and len(b) == 3]
    if fehler:
        raise Validierungsfehler(fehler)
    return aus


def ausdruck_uebersetzen(con, text: str) -> dict:
    """Ausdruck (Kontext ``regel``) → gespeicherter Baum; 422 ``ausdruck_ungueltig`` mit ``details.fehler``."""
    try:
        return ausdruck.uebersetzen(text, "regel", ausdruck.Bezuege.laden(con)).baum
    except ausdruck.AusdruckFehler as e:
        raise ApiFehler(422, "ausdruck_ungueltig", e.fehler[0]["meldung"], {"fehler": e.fehler}) from None


def _bezuege_pruefen(con, d: dict) -> None:
    if "ausdruck" in d:
        d["bedingungen"] = [{"feld": AUSDRUCK, "operator": AUSDRUCK, "wert": ausdruck_uebersetzen(con, d.pop("ausdruck"))}]
        return _bezuege_pruefen(con, d)
    if "kategorie_id" in d:
        r = buch.konto_zeile(con, d["kategorie_id"])
        if r is None or r["art"] not in KATEGORIEARTEN:
            raise ApiFehler(422, "kategorie_ungueltig", "Die Kategorie muss ein Aufwands- oder Ertragskonto sein.")
    if "bedingungen" in d and ist_ausdruck(d["bedingungen"]):
        bz = ausdruck.Bezuege.laden(con)
        b = baum(d["bedingungen"])
        fehlt = sorted(ausdruck.verweise(b, "konto") - set(bz.konto_pfad)
                       | ausdruck.verweise(b, "kategorie") - set(bz.kategorie_pfad))
        if fehlt:
            raise ApiFehler(422, "referenz_unbekannt", "Der Ausdruck verweist auf ein unbekanntes Konto.",
                            {"konto_ids": fehlt})
    elif "bedingungen" in d:
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


def regel_dict(r, bez: ausdruck.Bezuege | None = None) -> dict:
    """Protokollform (ohne ``bez``) bzw. API-Form mit ``ausdruck`` (kanonischer Text, auch für alte Regeln)."""
    d = {"id": r["id"], "name": r["name"], "aktiv": bool(r["aktiv"]), "prioritaet": r["prioritaet"],
         "kategorie_id": r["kategorie_id"], "bedingungen": json.loads(r["bedingungen"])}
    if bez is not None:
        d["ausdruck"] = ausdruck_text(d["bedingungen"], bez)
        d["ausdruck_form"] = "ausdruck" if ist_ausdruck(d["bedingungen"]) else "bedingungen"
    return d


def regeln_liste(con, mit_ausdruck: bool = True) -> list[dict]:
    bez = ausdruck.Bezuege.laden(con) if mit_ausdruck else None
    return [regel_dict(r, bez) for r in con.execute("SELECT * FROM regel ORDER BY prioritaet, id")]


def regel_lesen(con, rid: int) -> dict:
    r = con.execute("SELECT * FROM regel WHERE id = ?", (sichere_id(rid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Die Regel")
    return regel_dict(r, ausdruck.Bezuege.laden(con))


# ----------------------------------------------- alte Bedingungen als Ausdruck


def bedingungen_als_baum(bedingungen: list) -> dict:
    """Übersetzt alte Bedingungen in einen gleichbedeutenden Baum (Konzept 9; Regelbetrag mit Vorzeichen)."""
    b = baum(bedingungen)
    if b is not None:
        return b
    teile: list[dict] = []
    for x in bedingungen:
        f, op, w = x["feld"], x["operator"], x["wert"]
        if f in TEXTFELDER:
            feld = {"t": "feld", "name": "empfänger" if f == "empfaenger" else "verwendungszweck"}
            if op == "enthaelt":
                teile.append({"t": "kette", "terme": [{"t": "text", "wert": w}, feld], "ops": ["in"]})
            elif op == "gleich":
                teile.append({"t": "kette", "terme": [feld, {"t": "text", "wert": w}], "ops": ["=="]})
            else:
                teile.append({"t": "methode", "feld": feld["name"], "name": "startswith", "muster": w,
                              "case": False, "fold": True})
        elif f == "konto_id":
            teile.append({"t": "kette", "terme": [{"t": "feld", "name": "konto"},
                                                  {"t": "ref", "art": "konto", "id": w}], "ops": ["=="]})
        else:
            teile.append(_betrag_baum(op, w))
    return teile[0] if len(teile) == 1 else {"t": "und", "teile": teile}


def _betrag_baum(op: str, w: int) -> dict:
    def vgl(o: str, cent: int) -> dict:
        return {"t": "kette", "terme": [{"t": "feld", "name": "betrag"}, {"t": "betrag", "cent": cent}], "ops": [o]}

    def rtg(o: str, wert: str) -> dict:
        return {"t": "kette", "terme": [{"t": "feld", "name": "richtung"}, {"t": "auswahl", "wert": wert}], "ops": [o]}

    a = abs(w)
    if op == "gleich":
        if w == 0:
            return vgl("==", 0)
        return {"t": "und", "teile": [rtg("==", "ausgabe" if w < 0 else "einnahme"), vgl("==", a)]}
    if op == "mindestens":   # Regelbetrag >= w
        if w <= 0:
            return {"t": "oder", "teile": [rtg("!=", "ausgabe"), vgl("<=", a)]}
        return {"t": "und", "teile": [rtg("==", "einnahme"), vgl(">=", a)]}
    if w >= 0:               # hoechstens: Regelbetrag <= w
        return {"t": "oder", "teile": [rtg("!=", "einnahme"), vgl("<=", a)]}
    return {"t": "und", "teile": [rtg("==", "ausgabe"), vgl(">=", a)]}


def ausdruck_text(bedingungen: list, bez: ausdruck.Bezuege) -> str:
    return ausdruck.drucken(bedingungen_als_baum(bedingungen), bez)


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


def reihenfolge_setzen(con, ids: list[int]) -> list[dict]:
    """POST /api/regeln/reihenfolge (Konzept 6.3): vollständige ID-Liste → Priorität 10, 20, …"""
    vorhanden = [r["id"] for r in con.execute("SELECT id FROM regel ORDER BY prioritaet, id")]
    if sorted(ids) != sorted(vorhanden):
        raise ApiFehler(422, "validierung", "Die Liste muss jede Regel genau einmal enthalten.",
                        {"fehlend": sorted(set(vorhanden) - set(ids)), "unbekannt": sorted(set(ids) - set(vorhanden))})
    if len(ids) * 10 > PRIO_MAX:
        raise ApiFehler(422, "validierung", "Zu viele Regeln.")
    for i, rid in enumerate(ids):
        con.execute("UPDATE regel SET prioritaet = ? WHERE id = ? AND prioritaet <> ?", ((i + 1) * 10, rid, (i + 1) * 10))
    return regeln_liste(con)


# =============================================================== Auswertung


Sicht = ausdruck.Sicht   # Was eine Regel von einer Buchung sieht (kategorisierung.md 4, D-175)


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
    regeln = [r for r in regeln_liste(con, mit_ausdruck=False) if r["aktiv"]]
    if regel_ids is not None:
        erlaubt = set(regel_ids)
        regeln = [r for r in regeln if r["id"] in erlaubt]
    return regeln


def trifft(r: dict, s: Sicht) -> bool:
    b = baum(r["bedingungen"])
    if b is not None:
        return ausdruck.auswerten(b, s, dt.date.today())
    return all(_trifft(x, s) for x in r["bedingungen"])


def erste_regel(regeln: list[dict], s: Sicht) -> dict | None:
    for r in regeln:
        if trifft(r, s):
            return r
    return None


def vorschlag_setzen(con, buchung_id: int, split_id: int, bisheriges_konto: int, regel: dict) -> None:  # noqa: D401
    """Setzt die Kategorie der Regel als Vorschlag (kategorisierung.md 5)."""
    con.execute("UPDATE split SET konto_id = ? WHERE id = ?", (regel["kategorie_id"], split_id))
    alt = con.execute("SELECT vorher_konto_id FROM vorschlag WHERE buchung_id = ?", (buchung_id,)).fetchone()
    vorher = alt["vorher_konto_id"] if alt is not None else bisheriges_konto
    con.execute("INSERT INTO vorschlag (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id)"
                " VALUES (?, ?, ?, 'regel', ?) ON CONFLICT(buchung_id) DO UPDATE SET"
                " kategorie_id = excluded.kategorie_id, regel_id = excluded.regel_id, quelle = excluded.quelle, sicherheit = NULL,"
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
            if buch.ist_gesperrt(b):
                continue
            gegen = buch._gegensplit(b, art_von)
            if gegen is None:
                continue
            if nur_unkategorisiert and b["kategorie_id"] is not None:
                continue
            geprueft += 1
            r = erste_regel(regeln, ausdruck.sicht_aus_buchung(b, art_von))
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
    # M2: abgeglichene Buchungen sind immer gesperrt; ab M3 ist bei abgestimmten nur das Ablehnen gesperrt (5.4).
    if b["status"] == "abgeglichen" or (aktion == "ablehnen" and buch.ist_gesperrt(b)):
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
    if aktion == "ablehnen":
        gesperrt = [b["id"] for b in buchungen if buch.ist_gesperrt(b)]
        if gesperrt:
            raise ApiFehler(409, "buchung_gesperrt", "Gesperrte Buchungen: Ablehnen ist nicht möglich.",
                            {"buchung_ids": gesperrt})
    for b in buchungen:
        _entscheiden(con, b, aktion, art_von)
    return {"geaendert": sorted(ids), "anzahl": len(ids)}


# ======================================================= Testbereich (D-175)

WIRKUNGEN = ("neu", "abweichend", "bereits_so", "verdeckt", "uebersprungen", "treffer")
TESTMENGE_VORGABE = "datum in -12m"


def _test_regel(con, d: dict) -> tuple[dict, int | None, int | None]:
    """(Baum, Kategorie, ID der ersetzten Regel) aus dem Körper von /test bzw. /erklaeren."""
    rid = d.get("regel_id")
    gespeichert = regel_lesen(con, rid) if rid is not None else None
    if d.get("ausdruck") is not None:
        b = ausdruck_uebersetzen(con, d["ausdruck"])
    elif gespeichert is not None:
        b = bedingungen_als_baum(gespeichert["bedingungen"])
    else:
        raise ApiFehler(422, "validierung", "„ausdruck“ oder „regel_id“ angeben.")
    kat = d.get("kategorie_id", gespeichert["kategorie_id"] if gespeichert else None)
    if kat is not None:
        r = buch.konto_zeile(con, kat)
        if r is None or r["art"] not in KATEGORIEARTEN:
            raise ApiFehler(422, "kategorie_ungueltig", "Die Kategorie muss ein Aufwands- oder Ertragskonto sein.")
    return b, kat, rid


def _testmenge(con, text: str | None, heute: dt.date, konto_id: int | None = None) -> list[int]:
    """Buchungen der Testmenge (Filterausdruck), optional nur mit einem Split auf ``konto_id`` (Quellkonto)."""
    if konto_id is not None:
        r = buch.konto_zeile(con, konto_id)
        if r is None or r["art"] not in BESTAND:
            raise ApiFehler(422, "konto_ungueltig", "Das Quellkonto muss ein Bestandskonto sein.", {"feld": "konto_id"})
        alle = [r["id"] for r in con.execute(
            "SELECT id FROM buchung WHERE id IN (SELECT buchung_id FROM split WHERE konto_id = ?)"
            " ORDER BY datum DESC, id DESC", (konto_id,))]
    else:
        alle = [r["id"] for r in con.execute("SELECT id FROM buchung ORDER BY datum DESC, id DESC")]
    if text is None:
        text = TESTMENGE_VORGABE
    if not text.strip():
        return alle
    b = ausdruck.filter_baum(con, text)
    return ausdruck.filtern(con, b, alle, None, heute, buch.buchungen_laden)


def _bewerten(con, baum_: dict, kat: int | None, rid: int | None, ids: list[int], heute: dt.date,
              mit_zeilen: bool = True) -> tuple[list[dict], list[int]]:
    """Wirkung der (ungespeicherten) Regel je Buchung der Testmenge (Konzept 5.3)."""
    art_von = kontoarten(con)
    andere = [r for r in regeln_liste(con, mit_ausdruck=False) if r["aktiv"] and r["id"] != rid]
    if rid is not None:
        eigene = con.execute("SELECT prioritaet FROM regel WHERE id = ?", (rid,)).fetchone()["prioritaet"]
        andere = [r for r in andere if (r["prioritaet"], r["id"]) < (eigene, rid)]
    aw = ausdruck.Auswerter(heute, markieren=mit_zeilen)
    zeilen: list[dict] = []
    nicht_erfasst: list[int] = []
    for teil in buch._stueckweise(ids):
        for b in buch.buchungen_laden(con, teil, art_von=art_von):
            s = ausdruck.sicht_aus_buchung(b, art_von)
            aw.markierungen = []
            if not aw.wahr(baum_, s):
                if kat is not None and b["kategorie_id"] == kat:
                    nicht_erfasst.append(b["id"])
                continue
            z: dict[str, Any] = {"buchung_id": b["id"], "datum": b["datum"], "betrag": s.regelbetrag,
                                 "empfaenger": b["empfaenger"]["name"] if b["empfaenger"] else None,
                                 "verwendungszweck": b["verwendungszweck"], "konto_ids": sorted(s.konten),
                                 "kategorie_vorher": b["kategorie_id"], "kategorie_nachher": kat,
                                 "verdeckt_von": None, "grund": None, "markierungen": list(aw.markierungen)}
            gegen = buch._gegensplit(b, art_von)
            if buch.ist_gesperrt(b) or b["status"] == "abgeglichen":
                z["wirkung"], z["grund"] = "uebersprungen", "gesperrt"
            elif gegen is None:
                z["wirkung"], z["grund"] = "uebersprungen", "splitbuchung"
            else:
                vor = erste_regel(andere, s)
                if vor is not None:
                    z["wirkung"] = "verdeckt"
                    z["verdeckt_von"] = {"id": vor["id"], "name": vor["name"]}
                elif kat is None:
                    z["wirkung"] = "treffer"
                elif b["kategorie_id"] == kat:
                    z["wirkung"] = "bereits_so"
                elif b["kategorie_id"] is None:
                    z["wirkung"] = "neu"
                else:
                    z["wirkung"] = "abweichend"
            zeilen.append(z)
    return zeilen, nicht_erfasst


def testen(con, d: dict, heute: dt.date) -> dict:
    """POST /api/regeln/test (Konzept 6.4): Lesezugriff, kein Protokolleintrag."""
    baum_, kat, rid = _test_regel(con, d)
    ids = _testmenge(con, d.get("testmenge"), heute, d.get("konto_id"))
    zeilen, nicht_erfasst = _bewerten(con, baum_, kat, rid, ids, heute)
    zaehlung = {w: 0 for w in WIRKUNGEN}
    for z in zeilen:
        zaehlung[z["wirkung"]] += 1
    gewaehlt = [z for z in zeilen if not d.get("wirkung") or z["wirkung"] in d["wirkung"]]
    seite, pro = d.get("seite") or 1, d.get("pro_seite") or 100
    return {"testmenge_anzahl": len(ids), "anzahl": len(zeilen), "zaehlung": zaehlung,
            "gesamt": len(gewaehlt), "seite": seite, "pro_seite": pro,
            "treffer": gewaehlt[(seite - 1) * pro: seite * pro],
            "nicht_erfasst": {"anzahl": len(nicht_erfasst), "buchung_ids": nicht_erfasst[:200]}}


def erklaeren(con, d: dict, heute: dt.date) -> dict:
    """POST /api/regeln/erklaeren (Konzept 6.5)."""
    baum_, _kat, _rid = _test_regel(con, d)
    b = buch.buchung_lesen(con, d["buchung_id"])
    art_von = kontoarten(con)
    bez = ausdruck.Bezuege.laden(con)
    knoten = ausdruck.erklaeren(baum_, ausdruck.sicht_aus_buchung(b, art_von), heute, bez)
    return {"buchung_id": b["id"], "ergebnis": knoten["ergebnis"], "baum": knoten}


def regel_anwenden(con, rid: int, d: dict, heute: dt.date) -> dict:
    """POST /api/regeln/{id}/anwenden (Konzept 6.6): wie der Testbereich zeigt; verdeckte Treffer nicht."""
    regel = regel_lesen(con, rid)
    baum_ = bedingungen_als_baum(regel["bedingungen"])
    ids = d.get("buchung_ids") or _testmenge(con, d.get("testmenge"), heute, d.get("konto_id"))
    zeilen, _ = _bewerten(con, baum_, regel["kategorie_id"], rid, ids, heute, mit_zeilen=False)
    ziel = {"neu", "abweichend"} if d.get("abweichende_ueberschreiben") else {"neu"}
    art_von = kontoarten(con)
    geaendert = []
    for z in zeilen:
        if z["wirkung"] not in ziel:
            continue
        b = buch.buchung_lesen(con, z["buchung_id"])
        gegen = buch._gegensplit(b, art_von)
        vorschlag_setzen(con, b["id"], gegen["id"], gegen["konto_id"], regel)
        geaendert.append(b["id"])
    return {"geaendert": sorted(geaendert), "anzahl": len(geaendert)}
