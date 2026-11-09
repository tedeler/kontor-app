"""Kredite: Annuitätendarlehen ohne Kontozugriff (kredite.md, Meilenstein 5).

- Ein Kredit speichert nur Parameter, Erkennungsbedingungen, die Zuordnung der Raten zu Buchungen und die
  durchgeführten Jahresabgleiche. Die gebuchte Restschuld ist der negative Saldo des Darlehenskontos.
- Der Tilgungsplan ist eine reine Funktion der Parameter (``tilgungsplan``). Gerechnet wird ausschließlich mit
  ganzen Zahlen: Der Zins einer Periode ist ein Bruch ``Zähler / (Basis · 1 000 000)``, der kaufmännisch auf ganze
  Cent gerundet wird (``(2·Z + N) // (2·N)``); Tilgung = Rate − Zins.
- Zuordnungen und Abgleiche liegen in eigenen Tabellen (``kredit_zuordnung``, ``kredit_abgleich``) ohne
  Fremdschlüssel auf Buchungen. Am Ende jeder protokollierten Operation entfernt ``verwaiste_entfernen``
  Zuordnungen gelöschter Buchungen (bzw. setzt ``buchung_id`` eines Abgleichs auf null) – in derselben Änderung
  (kredite.md 2.3).
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
from collections.abc import Mapping
from typing import Any

from . import buch, regeln
from .buch import BESTAND, ApiFehler, nicht_gefunden, sichere_id
from .fehler import KreditRateZuKlein
from .validierung import BETRAG_MAX, Validierungsfehler, datum_gueltig, fehler_eintrag, ist_int, json_koerper

MAX_RATEN = 1200
METHODEN = ("30/360", "act/360", "act/365")
TOLERANZ = 5  # Tage (kredite.md 4.1)
SOLLZINS_MAX = 1_000_000
PARAMETER = ("restschuld", "stand_datum", "sollzins", "zinsmethode", "rate", "erste_faelligkeit", "sondertilgungen")
PARAMETER_PFLICHT = ("restschuld", "stand_datum", "sollzins", "rate", "erste_faelligkeit")
AENDERBAR = ("name", "zahlungskonto_id", "zins_konto_id", "restschuld", "stand_datum", "sollzins", "zinsmethode",
             "rate", "erste_faelligkeit", "sondertilgungen", "bedingungen", "aktiv")
NEU_FELDER = AENDERBAR + ("konto_id", "saldo_angleichen")
NEU_PFLICHT = ("name", "konto_id", "zahlungskonto_id", "zins_konto_id", "restschuld", "stand_datum", "sollzins",
               "rate", "erste_faelligkeit", "bedingungen")


# ================================================================ Kalender


def monat_plus(d: dt.date, n: int) -> dt.date:
    """``d`` um ``n`` Kalendermonate verschoben, Tag auf das Monatsende begrenzt (kredite.md 1)."""
    jahr, monat = divmod(d.year * 12 + (d.month - 1) + n, 12)
    monat += 1
    return dt.date(jahr, monat, min(d.day, calendar.monthrange(jahr, monat)[1]))


def tage(methode: str, a: dt.date, b: dt.date) -> int:
    if methode == "30/360":  # 30E/360
        return 360 * (b.year - a.year) + 30 * (b.month - a.month) + (min(b.day, 30) - min(a.day, 30))
    return (b - a).days


def basis(methode: str) -> int:
    return 365 if methode == "act/365" else 360


# ============================================================== Validierung


def _datum(wert: Any, python: bool) -> str | None:
    """Datum als Text (YYYY-MM-DD); in Python auch ``datetime.date`` (nicht ``datetime``)."""
    if python and isinstance(wert, dt.date) and not isinstance(wert, dt.datetime):
        return wert.isoformat()
    if datum_gueltig(wert):
        return wert
    return None


def _betrag(wert: Any, minimum: int = 1) -> bool:
    return ist_int(wert) and minimum <= wert <= BETRAG_MAX


def parameter_pruefen(d: Mapping, ort: list, fehler: list[dict], python: bool = False,
                      pflicht: bool = True) -> dict:
    """Prüft die Planparameter (Schema ``KreditParameter``); liefert die normalisierten Werte (Daten als Text).

    Die Bedingungen ``erste_faelligkeit > stand_datum`` und ``Sondertilgung.datum > stand_datum`` prüft
    ``parameter_beziehungen`` (beim Ändern erst am zusammengeführten Ergebnis)."""
    aus: dict[str, Any] = {}
    if pflicht:
        for k in PARAMETER_PFLICHT:
            if k not in d:
                fehler.append(fehler_eintrag(ort + [k], "Pflichtfeld fehlt."))
    for k in ("restschuld", "rate"):
        if k in d:
            if not _betrag(d[k]):
                fehler.append(fehler_eintrag(ort + [k], f"Ganzzahl in Cent von 1 bis {BETRAG_MAX} erwartet."))
            else:
                aus[k] = d[k]
    if "sollzins" in d:
        if not ist_int(d["sollzins"]) or not 0 <= d["sollzins"] <= SOLLZINS_MAX:
            fehler.append(fehler_eintrag(ort + ["sollzins"], "Ganzzahl in Millionstel von 0 bis 1 000 000 erwartet."))
        else:
            aus["sollzins"] = d["sollzins"]
    for k in ("stand_datum", "erste_faelligkeit"):
        if k in d:
            w = _datum(d[k], python)
            if w is None:
                fehler.append(fehler_eintrag(ort + [k], "Datum im Format YYYY-MM-DD erwartet."))
            else:
                aus[k] = w
    if "zinsmethode" in d:
        if not isinstance(d["zinsmethode"], str) or d["zinsmethode"] not in METHODEN:
            fehler.append(fehler_eintrag(ort + ["zinsmethode"], "Erlaubt sind: 30/360, act/360, act/365."))
        else:
            aus["zinsmethode"] = d["zinsmethode"]
    if "sondertilgungen" in d:
        st = d["sondertilgungen"]
        if not isinstance(st, list):
            fehler.append(fehler_eintrag(ort + ["sondertilgungen"], "Liste erwartet."))
        else:
            if len(st) > 100:
                fehler.append(fehler_eintrag(ort + ["sondertilgungen"], "Höchstens 100 Sondertilgungen."))
            liste = []
            for i, s in enumerate(st):
                o = ort + ["sondertilgungen", i]
                if not isinstance(s, dict):
                    fehler.append(fehler_eintrag(o, "Objekt {datum, betrag} erwartet."))
                    continue
                ok = True
                for k in s:
                    if k not in ("datum", "betrag"):
                        fehler.append(fehler_eintrag(o + [k], "Unbekanntes Feld."))
                        ok = False
                datum = _datum(s.get("datum"), python) if "datum" in s else None
                if datum is None:
                    fehler.append(fehler_eintrag(o + ["datum"], "Datum im Format YYYY-MM-DD erwartet."))
                    ok = False
                if "betrag" not in s or not _betrag(s["betrag"]):
                    fehler.append(fehler_eintrag(o + ["betrag"], f"Ganzzahl in Cent von 1 bis {BETRAG_MAX} erwartet."))
                    ok = False
                if ok:
                    liste.append({"datum": datum, "betrag": s["betrag"]})
            # gespeichert nach datum aufsteigend, bei gleichem Datum in Eingabereihenfolge (stabil)
            aus["sondertilgungen"] = sorted(liste, key=lambda x: x["datum"])
    return aus


def parameter_beziehungen(p: Mapping, ort: list, fehler: list[dict]) -> None:
    """kredite.md 2.1 Schritt 1: ``erste_faelligkeit > stand_datum``, Sondertilgungen nach ``stand_datum``."""
    stand = p.get("stand_datum")
    if stand is None:
        return
    if p.get("erste_faelligkeit") is not None and p["erste_faelligkeit"] <= stand:
        fehler.append(fehler_eintrag(ort + ["erste_faelligkeit"], "Die erste Fälligkeit muss nach dem Stichtag liegen."))
    for i, s in enumerate(p.get("sondertilgungen") or []):
        if s["datum"] <= stand:
            fehler.append(fehler_eintrag(ort + ["sondertilgungen", i, "datum"],
                                         "Eine Sondertilgung muss nach dem Stichtag liegen."))


# ============================================================ Tilgungsplan


def plan_berechnen(p: Mapping) -> dict:
    """kredite.md 3 für bereits geprüfte Parameter; wirft ``KreditRateZuKlein``."""
    methode = p.get("zinsmethode") or "30/360"
    stand = dt.date.fromisoformat(p["stand_datum"])
    erste = dt.date.fromisoformat(p["erste_faelligkeit"])
    rate, satz = p["rate"], p["sollzins"]
    nenner = basis(methode) * 1_000_000
    sonder = [(dt.date.fromisoformat(s["datum"]), s["betrag"]) for s in (p.get("sondertilgungen") or [])]
    sonder.sort(key=lambda x: x[0])  # stabil: Eingabereihenfolge bei gleichem Datum
    r = p["restschuld"]
    zeilen: list[dict] = []
    beginn = stand
    j = 0  # nächste noch nicht angewendete Sondertilgung
    for i in range(1, MAX_RATEN + 1):
        f = monat_plus(erste, i - 1)
        laenge = 30 if methode == "30/360" and i > 1 else tage(methode, beginn, f)
        vorher = r
        zaehler = 0
        lage = 0
        summe_sonder = 0
        while j < len(sonder) and sonder[j][0] <= beginn:  # nur bei i = 1 möglich; Validierung schließt es aus
            j += 1
        while j < len(sonder) and sonder[j][0] <= f:
            datum, betrag = sonder[j]
            pos = min(laenge, tage(methode, beginn, datum))
            zaehler += r * satz * (pos - lage)
            lage = pos
            wirksam = min(betrag, r)
            r -= wirksam
            summe_sonder += wirksam
            j += 1
        zaehler += r * satz * (laenge - lage)
        zins = (2 * zaehler + nenner) // (2 * nenner)  # ⌊z + 1/2⌋ für z ≥ 0
        if r + zins <= rate:
            zahlung, tilgung, schluss = r + zins, r, True
        else:
            zahlung, tilgung, schluss = rate, rate - zins, False
        if schluss and zahlung == 0:
            break
        zeilen.append({"nr": i, "faelligkeit": f.isoformat(), "zinstage": laenge, "restschuld_vorher": vorher,
                       "sondertilgung": summe_sonder, "zins": zins, "tilgung": tilgung, "rate": zahlung,
                       "restschuld_nachher": r - tilgung})
        r -= tilgung
        beginn = f
        if schluss:
            break
    else:
        raise KreditRateZuKlein("Der Tilgungsplan endet nicht innerhalb von 1 200 Raten; die Rate ist zu klein.")
    return {"zeilen": zeilen, "anzahl_raten": len(zeilen), "summe_zins": sum(z["zins"] for z in zeilen),
            "summe_tilgung": sum(z["tilgung"] for z in zeilen),
            "summe_sondertilgung": sum(z["sondertilgung"] for z in zeilen),
            "letzte_faelligkeit": zeilen[-1]["faelligkeit"] if zeilen else None}


def _rate_zu_klein() -> ApiFehler:
    return ApiFehler(422, "kredit_rate_zu_klein",
                     "Mit dieser Rate endet der Tilgungsplan nicht innerhalb von 1 200 Raten (100 Jahren).")


def tilgungsplan(parameter: Mapping[str, object]) -> dict:
    """python-api.md 12.3: Tilgungsplan als JSON-Objekt ``Tilgungsplan``; ``ValueError`` bei ungültigen
    Parametern, ``KreditRateZuKlein``, wenn der Plan nicht innerhalb von 1 200 Raten endet."""
    if not isinstance(parameter, Mapping):
        raise ValueError("Parameter müssen ein Mapping sein.")
    fehler: list[dict] = []
    for k in parameter:
        if k not in PARAMETER:
            fehler.append(fehler_eintrag([k], "Unbekanntes Feld."))
    p = parameter_pruefen(parameter, [], fehler, python=True)
    if not fehler:
        parameter_beziehungen(p, [], fehler)
    if fehler:
        raise ValueError("Ungültige Kreditparameter: " + "; ".join(
            f"{'.'.join(str(x) for x in e['ort'])}: {e['meldung']}" for e in fehler))
    return plan_berechnen(p)


def plan_koerper(roh: bytes) -> dict:
    """``POST /api/kredite/tilgungsplan``: Körper ``KreditParameter`` (422 ``validierung``)."""
    d = json_koerper(roh)
    if not isinstance(d, dict):
        raise Validierungsfehler([fehler_eintrag(["body"], "JSON-Objekt erwartet.")])
    fehler: list[dict] = []
    for k in d:
        if k not in PARAMETER:
            fehler.append(fehler_eintrag(["body", k], "Unbekanntes Feld."))
    p = parameter_pruefen(d, ["body"], fehler)
    if not fehler:
        parameter_beziehungen(p, ["body"], fehler)
    if fehler:
        raise Validierungsfehler(fehler)
    return p


def plan_rest(p: dict) -> dict:
    try:
        return plan_berechnen(p)
    except KreditRateZuKlein:
        raise _rate_zu_klein() from None


# ============================================================ Kredit-Körper


def _bedingungen_pruefen(bs: Any, ort: list, fehler: list[dict]) -> list[dict] | None:
    if not isinstance(bs, list):
        fehler.append(fehler_eintrag(ort, "Liste erwartet."))
        return None
    if not 1 <= len(bs) <= 20:
        fehler.append(fehler_eintrag(ort, "1 bis 20 Bedingungen erforderlich."))
    for i, b in enumerate(bs):
        if isinstance(b, dict) and "feld" in b and b["feld"] not in regeln.TEXTFELDER:
            fehler.append(fehler_eintrag(ort + [i, "feld"], "Erlaubt sind: empfaenger, verwendungszweck."))
            continue
        regeln._bedingung_pruefen(b, ort + [i], fehler)
    return [{"feld": b["feld"], "operator": b["operator"], "wert": b["wert"]}
            for b in bs if isinstance(b, dict) and {"feld", "operator", "wert"} == set(b)]


def kredit_koerper(roh: bytes, neu: bool) -> dict:
    """Prüft den Körper von ``POST`` (``KreditNeu``) bzw. ``PATCH`` (``KreditAenderung``) streng (Schema)."""
    d = json_koerper(roh)
    if not isinstance(d, dict):
        raise Validierungsfehler([fehler_eintrag(["body"], "JSON-Objekt erwartet.")])
    return kredit_pruefen(d, neu)


def kredit_pruefen(d: dict, neu: bool) -> dict:
    fehler: list[dict] = []
    erlaubt = NEU_FELDER if neu else AENDERBAR
    for k in d:
        if k not in erlaubt:
            fehler.append(fehler_eintrag(["body", k], "Unbekanntes oder nicht änderbares Feld."))
    if neu:
        for k in NEU_PFLICHT:
            if k not in d:
                fehler.append(fehler_eintrag(["body", k], "Pflichtfeld fehlt."))
    aus = parameter_pruefen(d, ["body"], fehler, pflicht=False)
    if "name" in d:
        n = d["name"]
        if not isinstance(n, str) or not 1 <= len(n.strip()) <= 200:
            fehler.append(fehler_eintrag(["body", "name"], "1–200 Zeichen (ohne Rand-Leerraum)."))
        else:
            aus["name"] = n.strip()
    for k in ("konto_id", "zahlungskonto_id", "zins_konto_id"):
        if k in d and k in erlaubt:
            if not ist_int(d[k]):
                fehler.append(fehler_eintrag(["body", k], "Ganzzahl erwartet."))
            else:
                aus[k] = d[k]
    for k in ("aktiv", "saldo_angleichen"):
        if k in d and k in erlaubt:
            if not isinstance(d[k], bool):
                fehler.append(fehler_eintrag(["body", k], "Wahrheitswert erwartet."))
            else:
                aus[k] = d[k]
    if "bedingungen" in d:
        bs = _bedingungen_pruefen(d["bedingungen"], ["body", "bedingungen"], fehler)
        if bs is not None:
            aus["bedingungen"] = bs
    if fehler:
        raise Validierungsfehler(fehler)
    return aus


def _vollstaendig_pruefen(con, k: dict, eigene_id: int | None) -> None:
    """kredite.md 2.1 Schritte 1–6 (ohne Schema) für einen vollständigen Kredit ``k``."""
    fehler: list[dict] = []
    parameter_beziehungen(k, ["body"], fehler)
    if fehler:
        raise Validierungsfehler(fehler)
    ids = {k["konto_id"], k["zahlungskonto_id"], k["zins_konto_id"]}
    arten = {}
    for kid in ids:
        r = buch.konto_zeile(con, sichere_id(kid))
        if r is not None:
            arten[kid] = r["art"]
    fehlend = sorted(ids - set(arten))
    if fehlend:
        raise ApiFehler(422, "referenz_unbekannt", "Ein Konto des Kredits existiert nicht.", {"konto_ids": fehlend})
    if arten[k["konto_id"]] != "kreditkonto":
        raise ApiFehler(422, "konto_ungueltig", "Das Darlehenskonto muss ein Konto der Art „Kreditkonto“ sein.")
    if arten[k["zahlungskonto_id"]] not in BESTAND or k["zahlungskonto_id"] == k["konto_id"]:
        raise ApiFehler(422, "konto_ungueltig",
                        "Das Zahlungskonto muss ein Bestandskonto und vom Darlehenskonto verschieden sein.")
    if arten[k["zins_konto_id"]] != "aufwand":
        raise ApiFehler(422, "kategorie_ungueltig", "Das Zinskonto muss ein Aufwandskonto sein.")
    if eigene_id is None:
        r = con.execute("SELECT id FROM kredit WHERE konto_id = ?", (k["konto_id"],)).fetchone()
        if r is not None:
            raise ApiFehler(409, "kredit_konto_belegt", "Für dieses Darlehenskonto gibt es bereits einen Kredit.",
                            {"kredit_id": r["id"]})
    plan_rest(k)


# ===================================================================== CRUD


def kredit_dict(con, r) -> dict:
    """Schema ``Kredit`` = Protokollform des Objekts ``kredit`` (protokoll.md 11.1)."""
    zu = [{"faelligkeit": z["faelligkeit"], "buchung_id": z["buchung_id"]} for z in con.execute(
        "SELECT faelligkeit, buchung_id FROM kredit_zuordnung WHERE kredit_id = ? ORDER BY faelligkeit", (r["id"],))]
    ab = [{"jahr": a["jahr"], "restschuld": a["restschuld"], "zinsen": a["zinsen"], "buchung_id": a["buchung_id"]}
          for a in con.execute("SELECT jahr, restschuld, zinsen, buchung_id FROM kredit_abgleich WHERE kredit_id = ?"
                               " ORDER BY jahr", (r["id"],))]
    return {"id": r["id"], "name": r["name"], "konto_id": r["konto_id"], "zahlungskonto_id": r["zahlungskonto_id"],
            "zins_konto_id": r["zins_konto_id"], "restschuld": r["restschuld"], "stand_datum": r["stand_datum"],
            "sollzins": r["sollzins"], "zinsmethode": r["zinsmethode"], "rate": r["rate"],
            "erste_faelligkeit": r["erste_faelligkeit"], "sondertilgungen": json.loads(r["sondertilgungen"]),
            "bedingungen": json.loads(r["bedingungen"]), "aktiv": bool(r["aktiv"]), "zuordnungen": zu,
            "abgleiche": ab}


def formen(con, ids: list[int]) -> dict[int, dict]:
    aus = {}
    for teil in buch._stueckweise(sorted(set(ids))):
        for r in con.execute(f"SELECT * FROM kredit WHERE id IN ({buch._platzhalter(len(teil))})", teil).fetchall():
            aus[r["id"]] = kredit_dict(con, r)
    return aus


def kredite_liste(con) -> list[dict]:
    return [kredit_dict(con, r) for r in con.execute("SELECT * FROM kredit ORDER BY id").fetchall()]


def kredit_lesen(con, kid: int) -> dict:
    r = con.execute("SELECT * FROM kredit WHERE id = ?", (sichere_id(kid),)).fetchone()
    if r is None:
        raise nicht_gefunden("Der Kredit")
    return kredit_dict(con, r)


def _zeile_werte(k: dict) -> tuple:
    return (k["name"], k["konto_id"], k["zahlungskonto_id"], k["zins_konto_id"], k["restschuld"], k["stand_datum"],
            k["sollzins"], k["zinsmethode"], k["rate"], k["erste_faelligkeit"],
            json.dumps(k["sondertilgungen"], ensure_ascii=False), json.dumps(k["bedingungen"], ensure_ascii=False),
            1 if k["aktiv"] else 0)


_SPALTEN = ("name, konto_id, zahlungskonto_id, zins_konto_id, restschuld, stand_datum, sollzins, zinsmethode, rate,"
            " erste_faelligkeit, sondertilgungen, bedingungen, aktiv")


def einfuegen(con, k: dict) -> int:
    """Legt einen Kredit an (mit ``id``, ``zuordnungen`` und ``abgleiche``, falls angegeben – für Rückgängig)."""
    kid = con.execute(f"INSERT INTO kredit (id, {_SPALTEN}) VALUES (?, {', '.join('?' * 13)})",
                      (k.get("id"),) + _zeile_werte(k)).lastrowid
    con.executemany("INSERT INTO kredit_zuordnung (kredit_id, faelligkeit, buchung_id) VALUES (?, ?, ?)",
                    [(kid, z["faelligkeit"], z["buchung_id"]) for z in k.get("zuordnungen", [])])
    con.executemany("INSERT INTO kredit_abgleich (kredit_id, jahr, restschuld, zinsen, buchung_id) VALUES (?, ?, ?, ?, ?)",
                    [(kid, a["jahr"], a["restschuld"], a["zinsen"], a["buchung_id"]) for a in k.get("abgleiche", [])])
    return kid


def saldo(con, konto_id: int, stichtag: str) -> int:
    r = con.execute("SELECT COALESCE(SUM(s.betrag), 0) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                    " WHERE s.konto_id = ? AND b.datum <= ?", (konto_id, stichtag)).fetchone()
    return r["n"]


def kredit_anlegen(con, d: dict) -> dict:
    k = {"zinsmethode": "30/360", "sondertilgungen": [], "aktiv": True, **d}
    angleichen = k.pop("saldo_angleichen", True)
    _vollstaendig_pruefen(con, k, None)
    kid = einfuegen(con, k)
    if angleichen:
        x = -k["restschuld"] - saldo(con, k["konto_id"], k["stand_datum"])
        if x != 0:
            from .pflege import korrektur_id
            buch.buchung_einfuegen(con, k["stand_datum"], None, "Anfangsbestand " + k["name"], "bestaetigt",
                                   [{"konto_id": k["konto_id"], "betrag": x, "memo": ""},
                                    {"konto_id": korrektur_id(con), "betrag": -x, "memo": ""}])
    return kredit_lesen(con, kid)


def kredit_aendern(con, kid: int, d: dict) -> dict:
    alt = kredit_lesen(con, kid)
    neu = {**alt, **d}
    _vollstaendig_pruefen(con, neu, kid)
    con.execute(f"UPDATE kredit SET ({_SPALTEN}) = ({', '.join('?' * 13)}) WHERE id = ?", _zeile_werte(neu) + (kid,))
    return kredit_lesen(con, kid)


def kredit_loeschen(con, kid: int) -> None:
    kredit_lesen(con, kid)
    con.execute("DELETE FROM kredit WHERE id = ?", (kid,))


def parameter_von(k: dict) -> dict:
    return {f: k[f] for f in PARAMETER}


def plan_des_kredits(con, kid: int) -> dict:
    return plan_rest(parameter_von(kredit_lesen(con, kid)))


# ================================================================== Bezüge


def kredite_mit_konto(con, konto_id: int) -> list[int]:
    return [r["id"] for r in con.execute(
        "SELECT id FROM kredit WHERE ? IN (konto_id, zahlungskonto_id, zins_konto_id) ORDER BY id", (konto_id,))]


def konto_pruefen(con, konto_id: int) -> None:
    """kredite.md 2.3, loeschen.md 7: 409 ``konto_in_verwendung`` mit ``details.kredit_ids``."""
    ids = kredite_mit_konto(con, konto_id)
    if ids:
        raise ApiFehler(409, "konto_in_verwendung", "Ein Kredit verweist auf das Konto; zuerst den Kredit ändern"
                        " oder löschen.", {"kredit_ids": ids})


def verwaiste_entfernen(con) -> None:
    """Zuordnungen gelöschter Buchungen entfallen, ``buchung_id`` eines Abgleichs wird null (kredite.md 2.3)."""
    con.execute("DELETE FROM kredit_zuordnung WHERE NOT EXISTS (SELECT 1 FROM buchung b"
                " WHERE b.id = kredit_zuordnung.buchung_id)")
    con.execute("UPDATE kredit_abgleich SET buchung_id = NULL WHERE buchung_id IS NOT NULL AND NOT EXISTS"
                " (SELECT 1 FROM buchung b WHERE b.id = kredit_abgleich.buchung_id)")


BEZUG_SQL = (
    "SELECT 1 FROM kredit k WHERE NOT EXISTS (SELECT 1 FROM konto x WHERE x.id = k.konto_id)"
    " OR NOT EXISTS (SELECT 1 FROM konto x WHERE x.id = k.zahlungskonto_id)"
    " OR NOT EXISTS (SELECT 1 FROM konto x WHERE x.id = k.zins_konto_id)",
    "SELECT 1 FROM kredit_zuordnung z WHERE NOT EXISTS (SELECT 1 FROM buchung b WHERE b.id = z.buchung_id)"
    " OR NOT EXISTS (SELECT 1 FROM kredit k WHERE k.id = z.kredit_id)",
    "SELECT 1 FROM kredit_abgleich a WHERE (a.buchung_id IS NOT NULL AND NOT EXISTS"
    " (SELECT 1 FROM buchung b WHERE b.id = a.buchung_id)) OR NOT EXISTS (SELECT 1 FROM kredit k WHERE k.id = a.kredit_id)",
    "SELECT 1 FROM kredit GROUP BY konto_id HAVING COUNT(*) > 1",
)


# =========================================================== Ratenerkennung


class Ratenplan:
    """Zeilen eines Kreditplans nach Fälligkeit und die bereits vergebenen Fälligkeiten (kredite.md 4.1)."""

    def __init__(self, k: dict) -> None:
        self.kredit = k
        try:
            self.zeilen = {dt.date.fromisoformat(z["faelligkeit"]): z for z in plan_berechnen(parameter_von(k))["zeilen"]}
        except KreditRateZuKlein:  # pragma: no cover - beim Anlegen/Ändern ausgeschlossen
            self.zeilen = {}
        self.vergeben = {z["faelligkeit"] for z in k["zuordnungen"]}

    def passend(self, datum: dt.date, betrag: int) -> dict | None:
        beste = None
        for abstand in range(0, TOLERANZ + 1):
            for f in (datum - dt.timedelta(days=abstand), datum + dt.timedelta(days=abstand)):
                z = self.zeilen.get(f)
                if z is None or z["faelligkeit"] in self.vergeben or betrag != -z["rate"]:
                    continue
                if beste is None or f < dt.date.fromisoformat(beste["faelligkeit"]):
                    beste = z
            if beste is not None:
                return beste
        return None

    def trifft(self, sicht: regeln.Sicht) -> bool:
        return all(regeln._trifft(b, sicht) for b in self.kredit["bedingungen"])


def aufteilung(k: dict, z: dict) -> list[dict]:
    """Zins- und Tilgungssplit einer Rate (kredite.md 4.1); der Zinssplit steht auch bei Zins 0 in der Buchung."""
    return [{"konto_id": k["zins_konto_id"], "betrag": z["zins"], "memo": "Zinsanteil"},
            {"konto_id": k["konto_id"], "betrag": z["tilgung"], "memo": "Tilgungsanteil"}]


def zuordnung_eintragen(con, kid: int, faelligkeit: str, bid: int) -> None:
    con.execute("INSERT INTO kredit_zuordnung (kredit_id, faelligkeit, buchung_id) VALUES (?, ?, ?)",
                (kid, faelligkeit, bid))


class SyncErkennung:
    """Stufe 0 der Synchronisation (kredite.md 4.2): aktive Kredite mit dem Konto als Zahlungskonto."""

    def __init__(self, con, konto_id: int) -> None:
        self.plaene = [Ratenplan(kredit_dict(con, r)) for r in con.execute(
            "SELECT * FROM kredit WHERE aktiv = 1 AND zahlungskonto_id = ? ORDER BY id", (konto_id,)).fetchall()]

    def erkennen(self, sicht: regeln.Sicht, datum: dt.date, betrag: int) -> tuple[Ratenplan, dict] | None:
        for p in self.plaene:
            if not p.trifft(sicht):
                continue
            z = p.passend(datum, betrag)
            if z is not None:
                return p, z
        return None


def zuordnen(con, kid: int, buchung_ids: list[int] | None, trocken: bool) -> dict:
    """``POST /api/kredite/{id}/zuordnen`` (kredite.md 4.3)."""
    k = kredit_lesen(con, kid)
    if buchung_ids is not None:
        fehlend = sorted(set(buchung_ids) - buch._vorhandene_buchungen(con, buchung_ids))
        if fehlend:
            raise ApiFehler(422, "referenz_unbekannt", "Unbekannte Buchungen.", {"buchung_ids": fehlend})
    if trocken:
        con.execute("SAVEPOINT kredit_zuordnen")
    try:
        return _zuordnen(con, k, buchung_ids, trocken)
    finally:
        if trocken:
            con.execute("ROLLBACK TO kredit_zuordnen")
            con.execute("RELEASE kredit_zuordnen")


def _zuordnen(con, k: dict, buchung_ids: list[int] | None, trocken: bool) -> dict:
    zk = k["zahlungskonto_id"]
    sql = ("SELECT DISTINCT b.id AS id FROM buchung b JOIN split s ON s.buchung_id = b.id"
           " WHERE s.konto_id = ? AND s.betrag < 0"
           " AND NOT EXISTS (SELECT 1 FROM kredit_zuordnung z WHERE z.buchung_id = b.id)")
    ids = [r["id"] for r in con.execute(sql, (zk,))]
    if buchung_ids is not None:
        erlaubt = set(buchung_ids)
        ids = [i for i in ids if i in erlaubt]
    art_von = buch.kontoarten(con)
    kandidaten = []
    for teil in buch._stueckweise(sorted(ids)):
        for b in buch.buchungen_laden(con, teil, art_von=art_von):
            sp = b["splits"]
            if buch.ist_gesperrt(b) or len(sp) != 2:
                continue
            zahl = [s for s in sp if s["konto_id"] == zk and s["betrag"] < 0]
            if len(zahl) != 1:
                continue
            andere = sp[1] if sp[0] is zahl[0] else sp[0]
            if art_von[andere["konto_id"]] in BESTAND:
                continue
            sicht = regeln.Sicht(b["empfaenger"]["name"] if b["empfaenger"] else None, b["verwendungszweck"],
                                 zahl[0]["betrag"], {zk})
            if not all(regeln._trifft(x, sicht) for x in k["bedingungen"]):
                continue
            kandidaten.append((b, zahl[0]))
    kandidaten.sort(key=lambda bz: (bz[0]["datum"], bz[0]["id"]))
    plan = Ratenplan(k)
    aus = []
    for b, s in kandidaten:
        z = plan.passend(dt.date.fromisoformat(b["datum"]), s["betrag"])
        if z is None:
            continue
        plan.vergeben.add(z["faelligkeit"])
        aus.append({"buchung_id": b["id"], "faelligkeit": z["faelligkeit"], "zins": z["zins"], "tilgung": z["tilgung"]})
        con.execute("DELETE FROM split WHERE buchung_id = ? AND id <> ?", (b["id"], s["id"]))
        con.execute("UPDATE split SET position = 0 WHERE id = ?", (s["id"],))
        con.executemany("INSERT INTO split (buchung_id, position, konto_id, betrag, memo) VALUES (?, ?, ?, ?, ?)",
                        [(b["id"], i + 1, t["konto_id"], t["betrag"], t["memo"]) for i, t in enumerate(aufteilung(k, z))])
        con.execute("UPDATE buchung SET status = 'vorlaeufig' WHERE id = ?", (b["id"],))
        buch.vorschlag_entfernen(con, [b["id"]])
        zuordnung_eintragen(con, k["id"], z["faelligkeit"], b["id"])
    return {"trocken": trocken, "geprueft": len(kandidaten), "anzahl": len(aus), "zuordnungen": aus}


# ============================================================ Jahresabgleich


def jahresabgleich(con, kid: int, d: dict) -> dict:
    """``POST /api/kredite/{id}/jahresabgleich`` (kredite.md 5)."""
    k = kredit_lesen(con, kid)
    jahr, trocken = d["jahr"], d.get("trocken", False)
    if any(a["jahr"] == jahr for a in k["abgleiche"]):
        raise ApiFehler(409, "kredit_jahr_abgeglichen", f"Für {jahr} gibt es bereits einen Jahresabgleich.")
    if trocken:
        con.execute("SAVEPOINT kredit_abgleich")
    try:
        return _abgleichen(con, k, d, trocken)
    finally:
        if trocken:
            con.execute("ROLLBACK TO kredit_abgleich")
            con.execute("RELEASE kredit_abgleich")


def _abgleichen(con, k: dict, d: dict, trocken: bool) -> dict:
    jahr = d["jahr"]
    stichtag = f"{jahr:04d}-12-31"
    anfang = f"{jahr:04d}-01-01"
    rs_berechnet = -saldo(con, k["konto_id"], stichtag)
    eigene = sorted({z["buchung_id"] for z in k["zuordnungen"]}
                    | {a["buchung_id"] for a in k["abgleiche"] if a["buchung_id"] is not None})
    zinsen_berechnet = 0
    im_jahr = []
    zugeordnet = {z["buchung_id"] for z in k["zuordnungen"]}
    for teil in buch._stueckweise(eigene):
        ph = buch._platzhalter(len(teil))
        r = con.execute(f"SELECT COALESCE(SUM(s.betrag), 0) AS n FROM split s JOIN buchung b ON b.id = s.buchung_id"
                        f" WHERE b.id IN ({ph}) AND s.konto_id = ? AND b.datum BETWEEN ? AND ?",
                        teil + [k["zins_konto_id"], anfang, stichtag]).fetchone()
        zinsen_berechnet += r["n"]
        im_jahr += [r["id"] for r in con.execute(
            f"SELECT id FROM buchung WHERE id IN ({ph}) AND datum BETWEEN ? AND ? AND status <> 'abgeglichen'",
            teil + [anfang, stichtag]) if r["id"] in zugeordnet]
    dr = d["restschuld"] - rs_berechnet
    dz = d["zinsen"] - zinsen_berechnet
    splits = []
    if dz or dr:
        from .pflege import korrektur_id
        if dz:
            splits.append({"konto_id": k["zins_konto_id"], "betrag": dz, "memo": "Zinskorrektur"})
        if dr:
            splits.append({"konto_id": k["konto_id"], "betrag": -dr, "memo": "Restschuldkorrektur"})
        if dr != dz:
            splits.append({"konto_id": korrektur_id(con), "betrag": dr - dz, "memo": ""})
    korrektur = None
    if splits:
        bid = buch.buchung_einfuegen(con, stichtag, None, f"Jahresabgleich {jahr} {k['name']}", "abgeglichen", splits)
        korrektur = bid
    im_jahr.sort()
    con.executemany("UPDATE buchung SET status = 'abgeglichen' WHERE id = ?", [(i,) for i in im_jahr])
    buch.vorschlag_entfernen(con, im_jahr)
    con.execute("INSERT INTO kredit_abgleich (kredit_id, jahr, restschuld, zinsen, buchung_id) VALUES (?, ?, ?, ?, ?)",
                (k["id"], jahr, d["restschuld"], d["zinsen"], korrektur))
    return {"kredit_id": k["id"], "jahr": jahr, "trocken": trocken, "restschuld": d["restschuld"],
            "zinsen": d["zinsen"], "restschuld_berechnet": rs_berechnet, "zinsen_berechnet": zinsen_berechnet,
            "differenz_restschuld": dr, "differenz_zinsen": dz, "korrektur_splits": splits,
            "korrektur_buchung": None if korrektur is None or trocken else buch.buchung_lesen(con, korrektur),
            "abgeglichen_buchung_ids": im_jahr}


__all__ = ["tilgungsplan", "monat_plus", "KreditRateZuKlein"]
