"""Hilfen für Meilenstein 27 (``sammel.md``, ``mail.md`` 6.6; E-249 bis E-251).

Alle Erwartungen werden unabhängig aus der REST-Darstellung des Buchbestands nach den Regeln der Definition
berechnet (Label „Verdächtig“ mit robustem z, Filter, Dublettenvorschläge, ``warum`` der Mail-Zuordnung).
"""

from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations

from .api import Api
from .normal import ekey, norm

ZAHLUNGSKONTEN = ("girokonto", "sparkonto")
BESTAETIGT = ("bestaetigt", "abgeglichen")
UNBESTAETIGT = ("importiert", "vorlaeufig")


# ------------------------------------------------------------------ Begriffe (sammel.md 0)
def kontoarten(api: Api) -> dict[int, str]:
    return {k["id"]: k["art"] for k in api.konten()}


def zahlungsbetrag(b: dict, arten: dict[int, str]) -> int | None:
    """Summe der Splits auf Zahlungskonten, nur wenn sie auf genau einem Zahlungskonto liegen."""
    splits = [s for s in b["splits"] if arten.get(s["konto_id"]) in ZAHLUNGSKONTEN]
    if len({s["konto_id"] for s in splits}) != 1:
        return None
    return sum(s["betrag"] for s in splits)


def median(werte: list[int]) -> int:
    w = sorted(werte)
    n = len(w)
    return w[n // 2] if n % 2 else (w[n // 2 - 1] + w[n // 2]) // 2


def mad(werte: list[int]) -> int:
    m = median(werte)
    return median([abs(x - m) for x in werte])


def robustes_z(w: int, m: int, d: int) -> int | None:
    """z in Hundertsteln; ``None`` = unbestimmt."""
    skala = d * 14826 // 10000
    if skala == 0:
        return 0 if w == m else None
    return abs(w - m) * 100 // skala


def stark(z: int | None) -> bool:
    return z is None or z >= 350


# ------------------------------------------------------------------ Label (sammel.md 1.2)
def verdacht_soll(buchungen: list[dict], arten: dict[int, str]) -> dict[int, str | None]:
    """Buchungs-ID → erwarteter ``grund`` (oder ``None`` = kein Feld) für alle übergebenen Buchungen; die Liste muss
    alle Buchungen des Buchbestands enthalten (Regel über alle Buchungen des Empfängers)."""
    je_empfaenger: dict[int, list[dict]] = defaultdict(list)
    for b in buchungen:
        if b["empfaenger"]:
            je_empfaenger[b["empfaenger"]["id"]].append(b)
    aus: dict[int, str | None] = {}
    for b in buchungen:
        aus[b["id"]] = None
        if b["status"] in BESTAETIGT or not b["empfaenger"]:
            continue
        alle = je_empfaenger[b["empfaenger"]["id"]]
        bestaetigte = [x for x in alle if x["status"] in BESTAETIGT]
        if not bestaetigte:
            aus[b["id"]] = "empfaenger"
            continue
        werte = [z for z in (zahlungsbetrag(x, arten) for x in bestaetigte) if z is not None]
        w = zahlungsbetrag(b, arten)
        if len(werte) < 4 or w is None:
            continue
        m, d = median(werte), mad(werte)
        if d == 0:
            if abs(w - m) * 100 > abs(m) * 50 and abs(w - m) >= 2000:
                aus[b["id"]] = "betrag"
        elif stark(robustes_z(w, m, d)):
            aus[b["id"]] = "betrag"
    return aus


def verdacht_ist(buchungen: list[dict]) -> dict[int, str | None]:
    return {b["id"]: (b["verdacht"]["grund"] if "verdacht" in b else None) for b in buchungen}


def pruefe_text(b: dict) -> None:
    """Vom Text nur: beginnt mit „Der “ und enthält den Empfängernamen (sammel.md 1.2)."""
    t = b["verdacht"]["text"]
    assert t.startswith("Der "), t
    assert b["empfaenger"]["name"] in t, (b["empfaenger"]["name"], t)


def alle_mit_verdacht(api: Api, **params) -> list[dict]:
    aus, seite = [], 1
    while True:
        d = api.get("/api/buchungen", params={**params, "verdacht": "ja", "seite": seite, "pro_seite": 500},
                    erwartet=200).daten
        aus.extend(d["eintraege"])
        if len(aus) >= d["gesamt"] or not d["eintraege"]:
            return aus
        seite += 1


# ------------------------------------------------------------------ Filter (sammel.md 3)
def woerter(text: str) -> list[str]:
    aus: list[str] = []
    for teil in re.split(r"[^a-z0-9]", norm(text)):
        if len(teil) >= 4 and not teil.isdigit() and teil not in aus:
            aus.append(teil)
    return aus


def zweck_aehnlich(zweck: str, wert: str) -> bool:
    w = woerter(wert)
    if w:
        return any(x in norm(zweck) for x in w)
    return norm(zweck) == norm(wert)


def _anfang(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def texte_aehnlich(a: str, b: str) -> bool:
    ka, kb = ekey(a), ekey(b)
    return bool(ka) and bool(kb) and _anfang(ka, kb) >= 4


def empfaenger_aehnlich(empfaenger: dict, wert: str) -> bool:
    return any(texte_aehnlich(x, wert) for x in [empfaenger["name"], *empfaenger.get("aliase", [])])


def filter_soll(buchungen: list[dict], empfaenger: dict[int, dict], **f) -> list[int]:
    """IDs (in Reihenfolge von ``buchungen``) nach den Filtern aus 3, UND-verknüpft."""
    aus = []
    for b in buchungen:
        z = b["verwendungszweck"]
        if f.get("zweck_leer"):
            if z != "":
                continue
        elif "zweck_gleich" in f and norm(z) != norm(f["zweck_gleich"]):
            continue
        if "zweck_aehnlich" in f and not zweck_aehnlich(z, f["zweck_aehnlich"]):
            continue
        if "empfaenger_aehnlich" in f:
            if not b["empfaenger"] or not empfaenger_aehnlich(empfaenger[b["empfaenger"]["id"]],
                                                              f["empfaenger_aehnlich"]):
                continue
        aus.append(b["id"])
    return aus


# ------------------------------------------------------------------ Dublettenvorschläge (sammel.md 4.2)
def vorschlaege_soll(buchungen: list[dict], arten: dict[int, str], verdachte: list[dict]) -> list[dict]:
    gruppen: dict[tuple, list[int]] = defaultdict(list)
    for b in buchungen:
        z = zahlungsbetrag(b, arten)
        if b["empfaenger"] and z is not None:
            gruppen[(b["datum"], b["empfaenger"]["id"], z)].append(b["id"])
    mengen = [{v["buchung_id"], *v["kandidat_ids"]} for v in verdachte]

    def bewertet(a: int, b: int) -> bool:
        return any(a in m and b in m for m in mengen)
    aus = []
    for ids in gruppen.values():
        if len(ids) < 2:
            continue
        ids = sorted(ids)
        paare = list(combinations(ids, 2))
        offen = [p for p in paare if not bewertet(*p)]
        if len(offen) == len(paare):
            aus.append((ids[0], ids[1:]))
        else:
            aus.extend((a, [b]) for a, b in offen)
    return [{"vorschlag": True, "id": None, "buchung_id": a, "kandidat_ids": k, "grund": "gleich",
             "status": "offen", "erstellt_am": None} for a, k in sorted(aus)]


def dubletten(api: Api, erwartet=200, **params):
    r = api.get("/api/dubletten", params=params or None, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


# ------------------------------------------------------------------ Mail-Zuordnung (mail.md 6.6.1)
def _klein(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def warum_soll(buchung: dict, erwartung: dict) -> str:
    """``buchung`` in der Form der Erwartungsantwort (``verwendungszweck``, ``empfaenger`` als Text)."""
    zweck = _klein(buchung["verwendungszweck"] or "")
    empf = _klein(buchung["empfaenger"] or "")
    for art, wert in (("Kennung", erwartung["kennung"]), ("Referenz", erwartung["referenz"])):
        k = _klein(wert or "")
        if len(k) < 6:
            continue
        if k in zweck:
            return f"Die {art} „{wert}“ steht im Verwendungszweck."
        if k in empf:
            return f"Die {art} „{wert}“ steht beim Empfänger."
    namen = [n for n in (erwartung.get("anbieter") or "", erwartung["haendler"]) if len(n) >= 3]
    if erwartung.get("anbieter") == "amazon" or "amazon" in erwartung["haendler"].lower():
        namen.append("amzn")
    roh_z, roh_e = (buchung["verwendungszweck"] or "").lower(), (buchung["empfaenger"] or "").lower()
    if abs(buchung["betrag"]) == erwartung["betrag"] and any(n.lower() in roh_z or n.lower() in roh_e
                                                             for n in namen):
        return "Der Betrag stimmt, und der Name des Händlers oder Anbieters steht in der Buchung."
    return "Manuell zugeordnet. Kennung, Betrag und Name erklären die Buchung nicht von selbst."


def mails(api: Api, erwartet=200, **params):
    r = api.get("/api/mail/nachrichten", params=params or None, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


# ------------------------------------------------------------------ Bestand (protokoll.md 21)
def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Bestand wie M25 (Empfängerform mit ``wiederkehrend``); ``tags`` der Empfänger kommen aus
    ``GET /api/empfaenger`` (Feld fehlt ohne Tags, sammel.md 2)."""
    from .m25 import bestand as bestand_m25

    aus = bestand_m25(api)
    for (o, i), v in aus.items():
        if o == "empfaenger" and "tags" in v:
            assert v["tags"], "tags fehlt ohne Tags (minItems 1)"
            assert v["tags"] == sorted(v["tags"], key=lambda t: (t["name"], t["id"])), "tags nach (name, id)"
    return aus


def tags_von(api: Api, eid: int) -> list[str]:
    e = api.get(f"/api/empfaenger/{eid}", erwartet=200).daten
    return [t["name"] for t in e.get("tags", [])]
