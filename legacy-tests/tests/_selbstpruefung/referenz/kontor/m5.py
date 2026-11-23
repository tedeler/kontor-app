"""Meilenstein 5 der Wegwerf-Referenz: Kredite, wiederkehrende Buchungen, Berichte, Export. KEIN Anwendungscode.

Alles wird bei jeder Anfrage neu aus dem Buch im Arbeitsspeicher berechnet (einfach, nicht schnell).
Mutanten über ``kontor.mutant(name)``.
"""

from __future__ import annotations

import calendar
import copy
import csv
import datetime as dt
import io
import json
import re
from fractions import Fraction
from typing import Annotated, Literal

from fastapi import FastAPI, Query
from fastapi.responses import Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from . import mutant
from .buch import KLASSE, MAX, Fehler

TOLERANZ = 5
RHYTHMEN = [("monatlich", 1, 3), ("vierteljaehrlich", 3, 3), ("jaehrlich", 12, 2)]
KORR = "kontor:korrektur"
UNK = "kontor:unkategorisiert"


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _datum(s: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        raise ValueError("Datum im Format YYYY-MM-DD erwartet")
    dt.date.fromisoformat(s)
    return s


def _v(ort, meldung) -> Fehler:
    return Fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ort, "meldung": meldung}])


Datum = Annotated[StrictStr, AfterValidator(_datum)]
Kbetrag = Annotated[StrictInt, Field(ge=1, le=MAX)]
Methode = Literal["30/360", "act/360", "act/365"]


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sonder(M):
    datum: Datum
    betrag: Kbetrag


class BedText(M):
    feld: Literal["empfaenger", "verwendungszweck"]
    operator: Literal["enthaelt", "gleich", "beginnt_mit"]
    wert: Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r"\S")]


class Parameter(M):
    restschuld: Kbetrag
    stand_datum: Datum
    sollzins: Annotated[StrictInt, Field(ge=0, le=1_000_000)]
    zinsmethode: Methode = "30/360"
    rate: Kbetrag
    erste_faelligkeit: Datum
    sondertilgungen: Annotated[list[Sonder], Field(max_length=100)] = []


class KreditNeu(Parameter):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    konto_id: StrictInt
    zahlungskonto_id: StrictInt
    zins_konto_id: StrictInt
    bedingungen: Annotated[list[BedText], Field(min_length=1, max_length=20)]
    aktiv: StrictBool = True
    saldo_angleichen: StrictBool = True


class KreditAenderung(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    zahlungskonto_id: StrictInt = None
    zins_konto_id: StrictInt = None
    restschuld: Kbetrag = None
    stand_datum: Datum = None
    sollzins: Annotated[StrictInt, Field(ge=0, le=1_000_000)] = None
    zinsmethode: Methode = None
    rate: Kbetrag = None
    erste_faelligkeit: Datum = None
    sondertilgungen: Annotated[list[Sonder], Field(max_length=100)] = None
    bedingungen: Annotated[list[BedText], Field(min_length=1, max_length=20)] = None
    aktiv: StrictBool = None


class Zuordnen(M):
    buchung_ids: Annotated[list[StrictInt], Field(max_length=10000)] = None
    trocken: StrictBool = False


class Abgleich(M):
    jahr: Annotated[StrictInt, Field(ge=1900, le=9999)]
    restschuld: Annotated[StrictInt, Field(ge=0, le=MAX)]
    zinsen: Annotated[StrictInt, Field(ge=0, le=MAX)]
    trocken: StrictBool = False


class Pruefen(M):
    buchung_ids: Annotated[list[StrictInt], Field(max_length=10000)] = []


# ================================================================ Tilgungsplan
def monat_plus(d: dt.date, n: int) -> dt.date:
    j, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return dt.date(j, m + 1, min(d.day, calendar.monthrange(j, m + 1)[1]))


def tage(methode: str, a: dt.date, b: dt.date) -> int:
    if methode == "30/360" and not mutant("kredit_30_360_tatsaechliche_tage"):
        return 360 * (b.year - a.year) + 30 * (b.month - a.month) + min(b.day, 30) - min(a.day, 30)
    return (b - a).days


def basis(methode: str, jahr: int) -> int:
    if methode == "act/365":
        return 366 if mutant("kredit_act365_schaltjahr") and calendar.isleap(jahr) else 365
    return 360


def runde(x: Fraction) -> int:
    if mutant("kredit_rundung_abschneiden"):
        return x.__floor__()
    return (x + Fraction(1, 2)).__floor__()


def pruefe_parameter(p: dict) -> None:
    if p["erste_faelligkeit"] <= p["stand_datum"]:
        raise _v(["body", "erste_faelligkeit"], "muss nach stand_datum liegen")
    if any(s["datum"] <= p["stand_datum"] for s in p["sondertilgungen"]):
        raise _v(["body", "sondertilgungen"], "Datum muss nach stand_datum liegen")


def plan(p: dict) -> dict:
    m = p["zinsmethode"]
    stand, erste = _d(p["stand_datum"]), _d(p["erste_faelligkeit"])
    satz = Fraction(p["sollzins"], 1_000_000)
    sonder = [(_d(s["datum"]), s["betrag"]) for s in p["sondertilgungen"]]
    r = p["restschuld"]
    zeilen = []
    beginn = stand
    for i in range(1, 1201):
        f = monat_plus(erste, i - 1) if not mutant("kredit_monatsende_verkettet") else (
            erste if i == 1 else monat_plus(beginn, 1))
        laenge = 30 if (m == "30/360" and i > 1 and not mutant("kredit_30_360_tatsaechliche_tage")) \
            else tage(m, beginn, f)
        vorher, lage, z, st = r, 0, Fraction(0), 0
        for datum, betrag in sonder:
            if beginn < datum <= f:
                pos = laenge if mutant("kredit_sondertilgung_periodenende") else min(laenge, tage(m, beginn, datum))
                z += r * satz * (pos - lage) / basis(m, f.year)
                lage = pos
                w = betrag if mutant("kredit_sondertilgung_unbegrenzt") else min(betrag, r)
                r -= w
                st += w
        z += r * satz * (laenge - lage) / basis(m, f.year)
        zins = runde(z)
        if r + zins <= p["rate"]:
            rate, tilgung, ende = r + zins, r, True
        else:
            rate, tilgung, ende = p["rate"], p["rate"] - zins, False
        zeilen.append({"nr": i, "faelligkeit": f.isoformat(), "zinstage": laenge, "restschuld_vorher": vorher,
                       "sondertilgung": st, "zins": zins, "tilgung": tilgung, "rate": rate,
                       "restschuld_nachher": r - tilgung})
        r -= tilgung
        beginn = f
        if ende:
            break
    else:
        raise Fehler(422, "kredit_rate_zu_klein", "Der Plan endet nicht innerhalb von 1 200 Raten")
    return {"zeilen": zeilen, "anzahl_raten": len(zeilen), "summe_zins": sum(x["zins"] for x in zeilen),
            "summe_tilgung": sum(x["tilgung"] for x in zeilen),
            "summe_sondertilgung": sum(x["sondertilgung"] for x in zeilen),
            "letzte_faelligkeit": zeilen[-1]["faelligkeit"]}


def parameter_von(k: dict) -> dict:
    return {f: k[f] for f in ("restschuld", "stand_datum", "sollzins", "zinsmethode", "rate", "erste_faelligkeit",
                              "sondertilgungen")}


def _sortiert(st: list[dict]) -> list[dict]:
    return [x for _, x in sorted(enumerate(st), key=lambda ix: (ix[1]["datum"], ix[0]))]


# ================================================================ Kredite: Bezüge
def kreditbezug(buch, kid: int) -> None:
    """kredite.md 2.3, loeschen.md 7."""
    if mutant("kredit_konto_loeschbar"):
        return
    ids = sorted(k["id"] for k in buch.kredite.values()
                 if kid in (k["konto_id"], k["zahlungskonto_id"], k["zins_konto_id"]))
    if ids:
        raise Fehler(409, "konto_in_verwendung", "Ein Kredit verweist auf das Konto", {"kredit_ids": ids})


def bereinigen(buch) -> None:
    """Zuordnungen gelöschter Buchungen entfallen, Abgleiche verlieren die Korrekturbuchung (kredite.md 2.3)."""
    if mutant("kredit_loeschen_zuordnung_bleibt"):
        return
    for k in getattr(buch, "kredite", {}).values():
        k["zuordnungen"] = [z for z in k["zuordnungen"] if z["buchung_id"] in buch.buchungen]
        for a in k["abgleiche"]:
            if a["buchung_id"] is not None and a["buchung_id"] not in buch.buchungen:
                a["buchung_id"] = None


def kredit_bezuege_ok(buch) -> bool:
    kr = list(getattr(buch, "kredite", {}).values())
    for k in kr:
        if any(x not in buch.konten for x in (k["konto_id"], k["zahlungskonto_id"], k["zins_konto_id"])):
            return False
        if any(z["buchung_id"] not in buch.buchungen for z in k["zuordnungen"]):
            return False
        if any(a["buchung_id"] is not None and a["buchung_id"] not in buch.buchungen for a in k["abgleiche"]):
            return False
    ks = [k["konto_id"] for k in kr]
    return len(ks) == len(set(ks))


def _pruefe_kredit(buch, d: dict, kid: int | None) -> None:
    pruefe_parameter(d)
    unbekannt = sorted({d[f] for f in ("konto_id", "zahlungskonto_id", "zins_konto_id") if d[f] not in buch.konten})
    if unbekannt:
        raise Fehler(422, "referenz_unbekannt", "Konto unbekannt", {"konto_ids": unbekannt})
    k = buch.konten
    if k[d["konto_id"]]["art"] != "kreditkonto":
        raise Fehler(422, "konto_ungueltig", "Darlehenskonto muss ein Kreditkonto sein")
    if KLASSE[k[d["zahlungskonto_id"]]["art"]] != "bestand" or d["zahlungskonto_id"] == d["konto_id"]:
        raise Fehler(422, "konto_ungueltig", "Zahlungskonto ungültig")
    if k[d["zins_konto_id"]]["art"] != "aufwand":
        raise Fehler(422, "kategorie_ungueltig", "Zinskonto muss eine Aufwandskategorie sein")
    andere = [x["id"] for x in buch.kredite.values() if x["konto_id"] == d["konto_id"] and x["id"] != kid]
    if andere:
        raise Fehler(409, "kredit_konto_belegt", "Für dieses Konto gibt es schon einen Kredit", {"kredit_id": andere[0]})
    plan(parameter_von(d))


def saldo(buch, konto_id: int, stichtag: str) -> int:
    return sum(s["betrag"] for b in buch.buchungen.values() if b["datum"] <= stichtag for s in b["splits"]
               if s["konto_id"] == konto_id)


def korrekturen(buch) -> int:
    return next((k["id"] for k in buch.konten.values() if k["extern_id"] == KORR), None) or \
        buch.konto_anlegen({"name": "Korrekturen", "art": "eigenkapital"}, extern_id=KORR)["id"]


# ================================================================ Raten
def STATUS_RATE() -> str:  # noqa: N802
    return "bestaetigt" if mutant("kredit_status_bestaetigt") else "vorlaeufig"


def rate_splits(k: dict, zeile: dict) -> list[dict]:
    return [{"konto_id": k["zins_konto_id"], "betrag": zeile["zins"], "memo": "Zinsanteil"},
            {"konto_id": k["konto_id"], "betrag": zeile["tilgung"], "memo": "Tilgungsanteil"}]


def zuordnung_eintragen(k: dict, faelligkeit: str, bid: int) -> None:
    k["zuordnungen"] = sorted(k["zuordnungen"] + [{"faelligkeit": faelligkeit, "buchung_id": bid}],
                              key=lambda z: z["faelligkeit"])


def _bedingungen(k: dict, empf: str | None, zweck: str) -> bool:
    from .m4 import _trifft
    return all(_trifft(c, empf, zweck, set()) for c in k["bedingungen"])


def passende_zeile(k: dict, datum: str, betrag: int, belegt: set[str]) -> dict | None:
    try:
        zeilen = plan(parameter_von(k))["zeilen"]
    except Fehler:
        return None
    tol = 0 if mutant("kredit_toleranz_null") else TOLERANZ
    d = _d(datum)
    kand = [z for z in zeilen if z["rate"] > 0 and -z["rate"] == betrag and z["faelligkeit"] not in belegt
            and abs((d - _d(z["faelligkeit"])).days) <= tol]
    if not kand:
        return None
    return min(kand, key=lambda z: (abs((d - _d(z["faelligkeit"])).days), z["faelligkeit"]))


def sync_treffer(buch, konto_id: int, empf: str | None, zweck: str, datum: str, betrag: int):
    if mutant("kredit_sync_nicht_aufgeteilt"):
        return None
    for k in sorted(buch.kredite.values(), key=lambda x: x["id"]):
        if not k["aktiv"] or k["zahlungskonto_id"] != konto_id or not _bedingungen(k, empf, zweck):
            continue
        z = passende_zeile(k, datum, betrag, {x["faelligkeit"] for x in k["zuordnungen"]})
        if z is not None:
            return k, z
    return None


def zuordnen(buch, k: dict, ids: list[int] | None, trocken: bool) -> dict:
    zugeordnet = {z["buchung_id"] for x in buch.kredite.values() for z in x["zuordnungen"]}
    pruef = []
    for b in buch.buchungen.values():
        if ids is not None and b["id"] not in ids:
            continue
        if buch.gesperrt(b) or b["id"] in zugeordnet or len(b["splits"]) != 2:
            continue
        auf = [s for s in b["splits"] if s["konto_id"] == k["zahlungskonto_id"] and s["betrag"] < 0]
        rest = [s for s in b["splits"] if s not in auf]
        if len(auf) != 1 or len(rest) != 1 or KLASSE[buch.konten[rest[0]["konto_id"]]["art"]] == "bestand":
            continue
        e = buch.empfaenger[b["empfaenger_id"]]["name"] if b["empfaenger_id"] is not None else None
        if _bedingungen(k, e, b["verwendungszweck"]):
            pruef.append(b)
    pruef.sort(key=lambda b: (b["datum"], b["id"]))
    belegt = {z["faelligkeit"] for z in k["zuordnungen"]}
    aus = []
    for b in pruef:
        zahl = next(s for s in b["splits"] if s["konto_id"] == k["zahlungskonto_id"])
        z = passende_zeile(k, b["datum"], zahl["betrag"], belegt)
        if z is None:
            continue
        belegt.add(z["faelligkeit"])
        aus.append({"buchung_id": b["id"], "faelligkeit": z["faelligkeit"], "zins": z["zins"], "tilgung": z["tilgung"]})
        if not trocken:
            b["splits"] = [zahl] + [{"id": buch.neue_id("split"), **s, "abstimmung_id": None}
                                    for s in rate_splits(k, z)]
            b["status"] = STATUS_RATE()
            b["vorschlag"] = None
            zuordnung_eintragen(k, z["faelligkeit"], b["id"])
    return {"trocken": trocken, "geprueft": len(pruef), "anzahl": len(aus), "zuordnungen": aus}


def jahresabgleich(buch, k: dict, d: Abgleich, jetzt) -> dict:
    if any(a["jahr"] == d.jahr for a in k["abgleiche"]):
        raise Fehler(409, "kredit_jahr_abgeglichen", "Für dieses Jahr gibt es schon einen Abgleich")
    s = f"{d.jahr:04d}-12-31"
    if mutant("kredit_abgleich_gegen_plan"):
        z = [x for x in plan(parameter_von(k))["zeilen"] if x["faelligkeit"] <= s]
        rest_b = z[-1]["restschuld_nachher"] if z else k["restschuld"]
    else:
        rest_b = -saldo(buch, k["konto_id"], s)
    ids = {z["buchung_id"] for z in k["zuordnungen"]} | {a["buchung_id"] for a in k["abgleiche"] if a["buchung_id"]}
    zins_b = sum(sp["betrag"] for i in ids if i in buch.buchungen for sp in buch.buchungen[i]["splits"]
                 if buch.buchungen[i]["datum"].startswith(f"{d.jahr:04d}-") and sp["konto_id"] == k["zins_konto_id"])
    dr, dz = d.restschuld - rest_b, d.zinsen - zins_b
    korr = next((x["id"] for x in buch.konten.values() if x["extern_id"] == KORR), None)
    splits = []
    if dz:
        splits.append({"konto_id": k["zins_konto_id"], "betrag": dz, "memo": "Zinskorrektur"})
    if dr:
        splits.append({"konto_id": k["konto_id"], "betrag": -dr, "memo": "Restschuldkorrektur"})
    if dr != dz:
        if korr is None and not d.trocken:
            korr = korrekturen(buch)
        splits.append({"konto_id": korr, "betrag": dr - dz, "memo": ""})
    abg = sorted(z["buchung_id"] for z in k["zuordnungen"] if z["buchung_id"] in buch.buchungen
                 and buch.buchungen[z["buchung_id"]]["datum"].startswith(f"{d.jahr:04d}-")
                 and buch.buchungen[z["buchung_id"]]["status"] != "abgeglichen")
    ergebnis = {"kredit_id": k["id"], "jahr": d.jahr, "trocken": d.trocken, "restschuld": d.restschuld,
                "zinsen": d.zinsen, "restschuld_berechnet": rest_b, "zinsen_berechnet": zins_b,
                "differenz_restschuld": dr, "differenz_zinsen": dz, "korrektur_splits": splits,
                "korrektur_buchung": None, "abgeglichen_buchung_ids": abg}
    if d.trocken:  # ein noch nicht vorhandenes Konto „Korrekturen“ hat konto_id null
        return ergebnis
    neu_id = None
    if splits:
        teile = [splits] if not (mutant("kredit_korrektur_zwei_buchungen") and dz and dr) else [
            [splits[0], {"konto_id": korrekturen(buch), "betrag": -dz, "memo": ""}],
            [splits[1], {"konto_id": korrekturen(buch), "betrag": dr, "memo": ""}]]
        for t in teile:
            nb = buch.buchung_anlegen({"datum": s, "empfaenger_id": None,
                                       "verwendungszweck": f"Jahresabgleich {d.jahr} {k['name']}",
                                       "status": "abgeglichen", "splits": t})
            neu_id = neu_id or nb["id"]
        ergebnis["korrektur_buchung"] = buch.buchung_json(buch.buchungen[neu_id])
    if not mutant("kredit_abgleich_ohne_status"):
        for i in abg:
            buch.buchungen[i]["status"] = "abgeglichen"
    k["abgleiche"] = sorted(k["abgleiche"] + [{"jahr": d.jahr, "restschuld": d.restschuld, "zinsen": d.zinsen,
                                               "buchung_id": neu_id}], key=lambda a: a["jahr"])
    return ergebnis


# ================================================================ Wiederkehrende Buchungen
def _eintraege(buch, bis: str | None = None) -> list[dict]:
    darlehen = {k["konto_id"] for k in buch.kredite.values()}
    aus = []
    for b in buch.buchungen.values():
        if b["empfaenger_id"] is None or (bis is not None and b["datum"] > bis):
            continue
        summe: dict[int, int] = {}
        for s in b["splits"]:
            if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand" and s["konto_id"] not in darlehen:
                summe[s["konto_id"]] = summe.get(s["konto_id"], 0) + s["betrag"]
        for k, x in sorted(summe.items()):
            if x:
                aus.append({"k": k, "e": b["empfaenger_id"], "r": "ausgabe" if x < 0 else "einnahme",
                            "datum": b["datum"], "id": b["id"], "x": x})
    return aus


def _gruppen(eintr: list[dict]) -> dict:
    g: dict = {}
    for e in eintr:
        g.setdefault((e["k"], e["e"], e["r"]), []).append(e)
    for v in g.values():
        v.sort(key=lambda e: (e["datum"], e["id"]))
    return g


def _serie(buch, gruppe: list[dict], stichtag: dt.date | None) -> dict | None:
    tol = 0 if mutant("wieder_ohne_toleranz") else TOLERANZ
    from . import m25
    filt = m25.filter_fuer(buch, gruppe[0]["e"]) if gruppe else None
    for name, m, mindest in RHYTHMEN:
        if filt and filt["modus"] != "aus":  # M25: Kette mit Betragsfilter (wiederkehrend.md 9.2)
            kt = m25.kette(gruppe, m, filt)
            kette = [gruppe[i] for i in kt["glieder"]]
            if len(kette) >= mindest and m25.mehrheit_verletzt(gruppe, kt, filt):
                continue
        elif mutant("wieder_kette_mit_luecke"):  # alte Kette (bis M15) mit überbrückter Lücke
            j = len(gruppe) - 1
            while j > 0:
                a, b = _d(gruppe[j - 1]["datum"]), _d(gruppe[j]["datum"])
                if abs((b - monat_plus(a, m)).days) <= tol or abs((b - monat_plus(a, 2 * m)).days) <= tol:
                    j -= 1
                else:
                    break
            kette = gruppe[j:]
        else:  # M16: Kette mit zusätzlichen Zahlungen (wiederkehrend.md 2.2)
            from .m16 import kette as m16_kette
            kette = [gruppe[i] for i in m16_kette(gruppe, m, tol)["glieder"]]
        if len(kette) < mindest:
            continue
        letzte = _d(kette[-1]["datum"])
        f, f2 = monat_plus(letzte, m), monat_plus(letzte, 2 * m)
        status = None
        if stichtag is not None:
            grenze = 0 if mutant("wieder_ausbleibend_ohne_toleranz") else TOLERANZ
            status = "aktiv" if stichtag <= f + dt.timedelta(days=grenze) else \
                "ausbleibend" if stichtag <= f2 + dt.timedelta(days=TOLERANZ) else "beendet"
        e = kette[-1]
        faktor = 12 if mutant("wieder_jahreskosten_monatlich") else 12 // m
        emp = buch.empfaenger[e["e"]]
        return {"schluessel": f"{e['k']}:{e['e']}:{e['r']}", "konto_id": e["k"],
                "empfaenger": {"id": emp["id"], "name": emp["name"]}, "richtung": e["r"], "rhythmus": name,
                "anzahl": len(kette), "erste": kette[0]["datum"], "letzte": e["datum"], "betrag": e["x"],
                "jahreskosten": -e["x"] * faktor, "naechste_faelligkeit": f.isoformat(), "status": status,
                "buchung_ids": [x["id"] for x in kette]}
    return None


def uebersicht(buch, stichtag: str) -> dict:
    h = _d(stichtag)
    serien = []
    for schl, g in sorted(_gruppen(_eintraege(buch, stichtag)).items(), key=lambda kv: (kv[0][0], kv[0][1],
                                                                                        kv[0][2] != "ausgabe")):
        s = _serie(buch, g, h)
        if s:
            serien.append(s)
    return {"stichtag": stichtag, "serien": serien,
            "summe_jahreskosten": sum(s["jahreskosten"] for s in serien
                                      if s["richtung"] == "ausgabe" and s["status"] != "beendet")}


def pruefen(dienst, ids: list[int]) -> list[dict]:
    buch = dienst.buch
    heute = dienst.heute().isoformat()
    neu: list[dict] = []

    def melden(art, schl, titel, text, link):
        if any(x["schluessel"] == schl and (not x["gelesen"] or not mutant("wieder_entprellung_ungelesen"))
               for x in buch.benachr.values()):
            return
        bid = buch.neue_id("benachrichtigung")
        buch.benachr[bid] = {"id": bid, "art": art, "schluessel": schl, "titel": titel, "text": text, "link": link,
                             "erstellt_am": dienst.jetzt().strftime("%Y-%m-%dT%H:%M:%SZ"), "gelesen": False}
        dienst.neu_gemeldet()
        neu.append(buch.benachr[bid])

    alle = _eintraege(buch)
    g = _gruppen(alle)
    for bid in sorted(ids):
        b = buch.buchungen[bid]
        eig = [e for e in alle if e["id"] == bid]
        name = buch.empfaenger[b["empfaenger_id"]]["name"] if b["empfaenger_id"] is not None else ""
        if any(e["r"] == "ausgabe" or mutant("wieder_neuer_empfaenger_einnahme") for e in eig):
            frueher = [x for x in buch.buchungen.values() if x["empfaenger_id"] == b["empfaenger_id"]
                       and x["id"] != bid and (x["datum"], x["id"]) < (b["datum"], bid)]
            if not frueher:
                melden("neuer_empfaenger", f"neuer_empfaenger:{b['empfaenger_id']}", "Neuer Empfänger",
                       f"Erste Abbuchung an „{name}“ über {eig[0]['x'] / 100:.2f} €.", f"/buchungen/{bid}")
        for e in eig:
            from . import m25
            if not m25._zul(m25.filter_fuer(buch, e["e"]), e) and not mutant("m25_meldung_unter_schwelle"):
                continue
            hist = [x for x in g[(e["k"], e["e"], e["r"])] if (x["datum"], x["id"]) < (e["datum"], e["id"])]
            s = _serie(buch, hist, None) if hist else None
            if s and abs((_d(b["datum"]) - _d(s["naechste_faelligkeit"])).days) <= TOLERANZ and e["x"] != s["betrag"]:
                melden("wiederkehrend_betrag", f"wiederkehrend_betrag:{bid}", "Betrag geändert",
                       f"„{name}“: bisher {s['betrag'] / 100:.2f} €, jetzt {e['x'] / 100:.2f} €.", f"/buchungen/{bid}")
                break
    for s in uebersicht(buch, heute)["serien"]:
        if s["status"] == "ausbleibend":
            melden("wiederkehrend_ausbleibend",
                   f"wiederkehrend_ausbleibend:{s['schluessel']}:{s['naechste_faelligkeit']}", "Zahlung ausgeblieben",
                   f"Die {s['rhythmus']}e Zahlung „{s['empfaenger']['name']}“ zum {s['naechste_faelligkeit']} fehlt.",
                   "/wiederkehrend")
    return neu


# ================================================================ Berichte
def _ende(d: dt.date, intervall: str) -> bool:
    morgen = d + dt.timedelta(days=1)
    return {"tag": True, "woche": d.isoweekday() == 7, "monat": morgen.month != d.month,
            "jahr": morgen.year != d.year}[intervall]


def _zeitraum(buch, von, bis, heute) -> tuple[dt.date, dt.date]:
    b = bis or heute
    if von is None:
        daten = [_d(x["datum"]) for x in buch.buchungen.values()]
        von = min(min(daten), b) if daten else b
    if von > b:
        raise _v(["query", "von"], "von > bis")
    return von, b


def stichtage(von: dt.date, bis: dt.date, intervall: str) -> list[dt.date]:
    aus = [von]
    if intervall == "tag" and (bis - von).days + 1 > 5000:
        raise Fehler(422, "bericht_zu_gross", "Zu viele Stichtage")
    d = von + dt.timedelta(days=1)
    while d < bis:
        if _ende(d, intervall):
            aus.append(d)
        d += dt.timedelta(days=1)
    if bis > von:
        aus.append(bis)
    if len(aus) > 5000:
        raise Fehler(422, "bericht_zu_gross", "Zu viele Stichtage")
    return aus


def perioden(von: dt.date, bis: dt.date, intervall: str) -> list[tuple[dt.date, dt.date]]:
    if intervall == "tag" and (bis - von).days + 1 > 5000:
        raise Fehler(422, "bericht_zu_gross", "Zu viele Perioden")
    aus, a = [], von
    while a <= bis:
        e = a
        while e < bis and not _ende(e, intervall):
            e += dt.timedelta(days=1)
        aus.append((a, e))
        a = e + dt.timedelta(days=1)
    if len(aus) > 5000:
        raise Fehler(422, "bericht_zu_gross", "Zu viele Perioden")
    return aus


def _konten_pruefen(buch, ids: list[int]) -> list[int]:
    unbekannt = sorted({i for i in ids if i not in buch.konten})
    if unbekannt:
        raise Fehler(422, "referenz_unbekannt", "Konto unbekannt", {"konto_ids": unbekannt})
    return sorted(set(ids))


# ================================================================ Export
def betrag_text(c: int) -> str:
    if mutant("csv_betrag_punkt"):
        return f"{c / 100:.2f}"
    return ("-" if c < 0 else "") + f"{abs(c) // 100},{abs(c) % 100:02d}"


def csv_bytes(buch, eintraege: list[dict]) -> bytes:
    puffer = io.StringIO(newline="")
    w = csv.writer(puffer, delimiter=";", quotechar='"', lineterminator="\r\n")
    w.writerow(["buchung_id", "datum", "empfaenger", "verwendungszweck", "status", "kategorie", "tags", "extern_ids",
                "gegen_iban", "split_nr", "split_id", "konto_id", "konto", "betrag", "memo", "abstimmung_id"])
    for j in eintraege:
        kat = buch.konten[j["kategorie_id"]]["name"] if j["kategorie_id"] else ""
        splits = j["splits"][:1] if mutant("csv_nur_erster_split") else j["splits"]
        for n, s in enumerate(splits, 1):
            w.writerow([j["id"], j["datum"], j["empfaenger"]["name"] if j["empfaenger"] else "", j["verwendungszweck"],
                        j["status"], kat, json.dumps([t["name"] for t in j["tags"]], ensure_ascii=False),
                        json.dumps(j["extern_ids"], ensure_ascii=False), j["gegen_iban"] or "", n, s["id"],
                        s["konto_id"], buch.konten[s["konto_id"]]["name"], betrag_text(s["betrag"]), s["memo"],
                        "" if s.get("abstimmung_id") is None else s["abstimmung_id"]])
    return ("" if mutant("csv_ohne_bom") else "﻿").encode("utf-8") + puffer.getvalue().encode("utf-8")


def pdf_bytes(eintraege: list[dict]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    def sauber(t: str, n: int) -> str:
        t = re.sub(r"\s+", " ", t)[:n]
        return t.encode("cp1252", "replace").decode("cp1252")

    puffer = io.BytesIO()
    c = canvas.Canvas(puffer, pagesize=A4)
    c.setFont("Helvetica", 9)
    y = 800
    c.drawString(40, y, f"Kontor – Buchungen. Anzahl Buchungen: {len(eintraege)}")
    y -= 20
    for j in eintraege:
        if y < 40:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = 800
        jj, mm, tt = j["datum"].split("-")
        empf = j["empfaenger"]["name"] if j["empfaenger"] else ""
        c.drawString(40, y, f"[#{j['id']}] {tt}.{mm}.{jj} {betrag_text(j['betrag'])} {sauber(empf, 30)} "
                            f"{sauber(j['verwendungszweck'], 50)}")
        y -= 12
    c.save()
    return puffer.getvalue()


# ================================================================ REST
def m5_einbinden(app: FastAPI, config, buch) -> None:
    from . import m3
    dienst = app.state.dienst
    if not mutant("kredit_protokoll_fehlt"):
        m3.MANUELL.extend([
            ("POST", r"/api/kredite", "kredit_anlegen"), ("PATCH", r"/api/kredite/\d+", "kredit_aendern"),
            ("DELETE", r"/api/kredite/\d+", "kredit_loeschen"), ("POST", r"/api/kredite/\d+/zuordnen", "kredit_zuordnen"),
            ("POST", r"/api/kredite/\d+/jahresabgleich", "kredit_jahresabgleich")])
        m3.MANUELL[:] = list(dict.fromkeys(m3.MANUELL))
        m3.QUELLE["kredit_zuordnen"] = "kredit"

    def _kredit(kid: int) -> dict:
        if kid not in buch.kredite:
            raise Fehler(404, "nicht_gefunden", "Kredit nicht gefunden")
        return buch.kredite[kid]

    @app.get("/api/kredite")
    def kredite():
        return [copy.deepcopy(k) for k in sorted(buch.kredite.values(), key=lambda k: k["id"])]

    @app.post("/api/kredite", status_code=201)
    def kredit_anlegen(d: KreditNeu):
        x = d.model_dump()
        x["name"] = x["name"].strip()
        if not x["name"]:
            raise _v(["body", "name"], "leer")
        angleichen = x.pop("saldo_angleichen")
        x["sondertilgungen"] = _sortiert(x["sondertilgungen"])
        _pruefe_kredit(buch, x, None)
        k = {"id": buch.neue_id("kredit"), **{f: x[f] for f in (
            "name", "konto_id", "zahlungskonto_id", "zins_konto_id", "restschuld", "stand_datum", "sollzins",
            "zinsmethode", "rate", "erste_faelligkeit", "sondertilgungen", "bedingungen", "aktiv")},
             "zuordnungen": [], "abgleiche": []}
        buch.kredite[k["id"]] = k
        if angleichen:
            diff = -k["restschuld"] - saldo(buch, k["konto_id"], k["stand_datum"])
            if diff:
                buch.buchung_anlegen({"datum": k["stand_datum"], "empfaenger_id": None,
                                      "verwendungszweck": "Anfangsbestand " + k["name"], "status": "bestaetigt",
                                      "splits": [{"konto_id": k["konto_id"], "betrag": diff, "memo": ""},
                                                 {"konto_id": korrekturen(buch), "betrag": -diff, "memo": ""}]})
        return copy.deepcopy(k)

    @app.post("/api/kredite/tilgungsplan")
    def tilgungsplan(d: Parameter):
        p = d.model_dump()
        p["sondertilgungen"] = _sortiert(p["sondertilgungen"])
        pruefe_parameter(p)
        return plan(p)

    @app.get("/api/kredite/{kredit_id}")
    def kredit_lesen(kredit_id: int):
        return copy.deepcopy(_kredit(kredit_id))

    @app.patch("/api/kredite/{kredit_id}")
    def kredit_aendern(kredit_id: int, d: KreditAenderung):
        k = _kredit(kredit_id)
        neu = copy.deepcopy(k)
        for f in d.model_fields_set:
            v = getattr(d, f)
            if v is None:
                raise _v(["body", f], "darf nicht null sein")
            neu[f] = [x.model_dump() for x in v] if f in ("sondertilgungen", "bedingungen") else v
        neu["name"] = neu["name"].strip()
        if not neu["name"]:
            raise _v(["body", "name"], "leer")
        neu["sondertilgungen"] = _sortiert(neu["sondertilgungen"])
        _pruefe_kredit(buch, neu, kredit_id)
        k.update(neu)
        return copy.deepcopy(k)

    @app.delete("/api/kredite/{kredit_id}", status_code=204)
    def kredit_loeschen(kredit_id: int):
        _kredit(kredit_id)
        del buch.kredite[kredit_id]
        return Response(status_code=204)

    @app.get("/api/kredite/{kredit_id}/plan")
    def kredit_plan(kredit_id: int):
        return plan(parameter_von(_kredit(kredit_id)))

    @app.post("/api/kredite/{kredit_id}/zuordnen")
    def kredit_zuordnen(kredit_id: int, d: Zuordnen):
        k = _kredit(kredit_id)
        ids = d.buchung_ids
        if ids is not None:
            if len(set(ids)) != len(ids):
                raise _v(["body", "buchung_ids"], "doppelt")
            unbekannt = sorted(i for i in ids if i not in buch.buchungen)
            if unbekannt:
                raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        return zuordnen(buch, k, ids, d.trocken)

    @app.post("/api/kredite/{kredit_id}/jahresabgleich")
    def kredit_abgleich(kredit_id: int, d: Abgleich):
        return jahresabgleich(buch, _kredit(kredit_id), d, dienst.jetzt())

    # ------------------------------------------------------ wiederkehrend
    @app.get("/api/wiederkehrend")
    def wiederkehrend(stichtag: dt.date | None = None):
        return uebersicht(buch, (stichtag or dienst.heute()).isoformat())

    @app.post("/api/wiederkehrend/pruefen")
    def wiederkehrend_pruefen(d: Pruefen):
        ids = d.buchung_ids
        if len(set(ids)) != len(ids):
            raise _v(["body", "buchung_ids"], "doppelt")
        unbekannt = sorted(i for i in ids if i not in buch.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        neu = pruefen(dienst, ids)
        return {"stichtag": dienst.heute().isoformat(), "benachrichtigungen": neu}

    # ------------------------------------------------------ Berichte
    @app.get("/api/berichte/kontostand")
    def bericht_kontostand(konto_id: list[int] = Query([]), von: dt.date | None = None, bis: dt.date | None = None,
                           intervall: Literal["tag", "woche", "monat", "jahr"] = "monat", unterkonten: bool = False):
        ids = _konten_pruefen(buch, konto_id) if konto_id else sorted(
            k["id"] for k in buch.konten.values() if KLASSE[k["art"]] == "bestand")
        a, b = _zeitraum(buch, von, bis, dienst.heute())
        st = stichtage(a, b, intervall)
        reihen = []
        for kid in ids:
            menge = buch.nachfahren(kid) if unterkonten and not mutant("bericht_ohne_unterkonten") else {kid}
            werte = []
            for s in st:
                grenze = s.isoformat()
                werte.append(sum(sp["betrag"] for x in buch.buchungen.values()
                                 if (x["datum"] < grenze if mutant("bericht_stichtag_exklusiv") else x["datum"] <= grenze)
                                 for sp in x["splits"] if sp["konto_id"] in menge))
            k = buch.konten[kid]
            reihen.append({"konto_id": kid, "name": k["name"], "art": k["art"], "werte": werte})
        return {"von": a.isoformat(), "bis": b.isoformat(), "intervall": intervall, "unterkonten": unterkonten,
                "stichtage": [s.isoformat() for s in st], "reihen": reihen}

    @app.get("/api/berichte/einnahmen-ausgaben")
    def bericht_ea(konto_id: list[int] = Query([]), von: dt.date | None = None, bis: dt.date | None = None,
                   intervall: Literal["tag", "woche", "monat", "jahr"] = "monat"):
        ids = _konten_pruefen(buch, konto_id) if konto_id else []
        if any(KLASSE[buch.konten[i]["art"]] != "bestand" for i in ids):
            raise Fehler(422, "konto_ungueltig", "Nur Bestandskonten")
        a, b = _zeitraum(buch, von, bis, dienst.heute())
        per = perioden(a, b, intervall)
        auswahl = [x for x in buch.buchungen.values() if a.isoformat() <= x["datum"] <= b.isoformat()
                   and (not ids or any(s["konto_id"] in ids for s in x["splits"]))]
        art = {k["id"]: k["art"] for k in buch.konten.values()}
        unk = {k["id"] for k in buch.konten.values() if k["extern_id"] == UNK}
        aus, kat = [], {}
        for pa, pe in per:
            ein = ausg = nk = 0
            for x in auswahl:
                if not pa.isoformat() <= x["datum"] <= pe.isoformat():
                    continue
                for s in x["splits"]:
                    if mutant("bericht_umbuchung_als_ausgabe"):
                        if KLASSE[art[s["konto_id"]]] == "bestand":
                            ausg += -s["betrag"] if s["betrag"] < 0 else 0
                            ein += s["betrag"] if s["betrag"] > 0 else 0
                        continue
                    if art[s["konto_id"]] == "ertrag":
                        ein -= s["betrag"]
                    elif art[s["konto_id"]] == "aufwand":
                        ausg += s["betrag"]
                    elif s["konto_id"] in unk:
                        nk += s["betrag"]
            aus.append({"von": pa.isoformat(), "bis": pe.isoformat(), "einnahmen": ein, "ausgaben": ausg,
                        "saldo": ein - ausg, "nicht_kategorisiert": nk})
        for x in auswahl:
            for s in x["splits"]:
                if art[s["konto_id"]] in ("aufwand", "ertrag"):
                    kat[s["konto_id"]] = kat.get(s["konto_id"], 0) + s["betrag"]
        return {"von": a.isoformat(), "bis": b.isoformat(), "intervall": intervall, "perioden": aus,
                "gesamt": {f: sum(p[f] for p in aus) for f in ("einnahmen", "ausgaben", "saldo", "nicht_kategorisiert")},
                "kategorien": [{"kategorie_id": i, "name": buch.konten[i]["name"], "art": art[i], "summe": v}
                               for i, v in sorted(kat.items())]}

    # ------------------------------------------------------ Export
    def _liste(p: dict):
        if p["von"] and p["bis"] and p["von"] > p["bis"]:
            raise _v(["query", "von"], "von > bis")
        if p["betrag_min"] is not None and p["betrag_max"] is not None and p["betrag_min"] > p["betrag_max"]:
            raise _v(["query", "betrag_min"], "betrag_min > betrag_max")
        p = {**p, "von": p["von"].isoformat() if p["von"] else None, "bis": p["bis"].isoformat() if p["bis"] else None,
             "seite": 1, "pro_seite": 10 ** 9}
        return buch.liste(p)["eintraege"]

    def export(endung: str, media: str, erzeuge):
        def handler(konto_id: int | None = None, unterkonten: bool = False, von: dt.date | None = None, bis: dt.date | None = None,
                    betrag_min: int | None = None, betrag_max: int | None = None, kategorie_id: int | None = None,
                    unterkategorien: bool = False, tag_id: list[int] = Query([]), empfaenger_id: int | None = None,
                    ohne_empfaenger: bool = False, verwendungszweck: str | None = Query(None, min_length=1),
                    suche: str | None = Query(None, min_length=1),
                    status: list[Literal["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"]] = Query([]),
                    sortierung: Literal["datum", "-datum", "betrag", "-betrag", "empfaenger", "-empfaenger"] = "datum",
                    vorschlag: bool | None = None, abgestimmt: bool | None = None):
            e = _liste({"konto_id": konto_id, "unterkonten": unterkonten, "von": von, "bis": bis, "betrag_min": betrag_min,
                        "betrag_max": betrag_max, "kategorie_id": kategorie_id, "unterkategorien": unterkategorien,
                        "tag_id": tag_id, "empfaenger_id": empfaenger_id, "ohne_empfaenger": ohne_empfaenger,
                        "verwendungszweck": verwendungszweck, "suche": suche, "status": status,
                        "sortierung": sortierung, "vorschlag": vorschlag, "abgestimmt": abgestimmt})
            name = f"kontor-buchungen-{dienst.heute().strftime('%Y%m%d')}.{endung}"
            return Response(erzeuge(e), media_type=media,
                            headers={"Content-Disposition": f'attachment; filename="{name}"'})
        app.get(f"/api/export/buchungen.{endung}")(handler)

    export("csv", "text/csv; charset=utf-8", lambda e: csv_bytes(buch, e))
    export("pdf", "application/pdf", pdf_bytes)
