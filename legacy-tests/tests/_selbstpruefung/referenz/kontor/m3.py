"""Meilenstein 3 der Wegwerf-Referenz: Protokoll, Rückgängig, Empfänger, Erfassen, Umbuchungen, Abstimmung, Suche.

KEIN Anwendungscode. Das Protokoll entsteht hier generisch aus Vorher/Nachher-Abzügen des ganzen
Buchs im Arbeitsspeicher – einfach, aber nicht als Vorbild gedacht. Mutanten über ``kontor.mutant(name)``.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
import unicodedata
from typing import Annotated, Literal

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from . import mutant
from .buch import KLASSE, MAX, Fehler, ekey, namen_pruefen, norm

OBJEKTE = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage", "kredit",
           "postfach"]
TABELLE = {"konto": "konten", "empfaenger": "empfaenger", "tag": "tags", "buchung": "buchungen", "regel": "regeln",
           "verdacht": "verdachte", "abstimmung": "abstimmungen", "vorlage": "vorlagen", "kredit": "kredite",
           "postfach": "postfaecher"}
UNK = "kontor:unkategorisiert"
KORR = "kontor:korrektur"


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _v(ort, meldung):
    return Fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ort, "meldung": meldung}])


# ================================================================ Protokoll
def _buchung_form(b: dict) -> dict:
    return {"id": b["id"], "datum": b["datum"], "empfaenger_id": b["empfaenger_id"],
            "verwendungszweck": b["verwendungszweck"], "status": b["status"],
            "splits": [{"id": s["id"], "konto_id": s["konto_id"], "betrag": s["betrag"], "memo": s["memo"],
                        "abstimmung_id": s.get("abstimmung_id")} for s in b["splits"]],
            "tag_ids": sorted(b["tag_ids"]), "extern_ids": sorted(b["extern_ids"]),
            "vorschlag": dict(b["vorschlag"]) if b.get("vorschlag") else None, "gegen_iban": b.get("gegen_iban")}


def protokollform(buch) -> dict:
    from .m5 import bereinigen
    bereinigen(buch)
    z: dict = {}
    for k in buch.konten.values():
        z[("konto", k["id"])] = buch.konto_json(k)
    for e in buch.empfaenger.values():
        z[("empfaenger", e["id"])] = {"id": e["id"], "name": e["name"], "extern_id": e["extern_id"],
                                      "aliase": sorted(e.get("aliase", [])),
                                      "standardkategorie_id": e.get("standardkategorie_id")}
        if e.get("wiederkehrend"):  # M25 (wiederkehrend.md 9.4): nur bei eigener Einstellung
            z[("empfaenger", e["id"])]["wiederkehrend"] = dict(e["wiederkehrend"])
    for t in buch.tags.values():
        z[("tag", t["id"])] = {"id": t["id"], "name": t["name"], "extern_id": t["extern_id"]}
    for b in buch.buchungen.values():
        z[("buchung", b["id"])] = _buchung_form(b)
    for r in buch.regeln.values():
        z[("regel", r["id"])] = copy.deepcopy(r)
    for v in buch.verdachte.values():
        z[("verdacht", v["id"])] = copy.deepcopy(v)
    for a in buch.abstimmungen.values():
        z[("abstimmung", a["id"])] = dict(a)
    from .m4 import vorlage_json
    for v in getattr(buch, "vorlagen", {}).values():
        z[("vorlage", v["id"])] = vorlage_json(v)
    for k in getattr(buch, "kredite", {}).values():
        z[("kredit", k["id"])] = copy.deepcopy(k)
    for p in getattr(buch, "postfaecher", {}).values():
        z[("postfach", p["id"])] = copy.deepcopy(p)
    for k in buch.gemerkt:
        z[("kennung", k)] = True
    return z


def protokolliere(buch, vorher: dict, quelle: str, aktion: str, gruppe: str | None, zeit: str, text: str,
                  rueckgaengig_von: list[int] | None = None) -> dict | None:
    nachher = protokollform(buch)
    eintraege, plus, minus = [], [], []
    for schl in set(vorher) | set(nachher):
        a, b = vorher.get(schl), nachher.get(schl)
        if a == b:
            continue
        if schl[0] == "kennung":
            (plus if b else minus).append(schl[1])
            continue
        eintraege.append({"objekt": schl[0], "objekt_id": schl[1],
                          "art": "angelegt" if a is None else "geloescht" if b is None else "geaendert",
                          "vorher": copy.deepcopy(a), "nachher": copy.deepcopy(b)})
    if not eintraege and not plus and not minus:
        if mutant("aenderung_ohne_wirkung") and quelle == "manuell":
            return _neu(buch, quelle, aktion, gruppe, zeit, text, [], [], [], rueckgaengig_von)
        return None
    eintraege.sort(key=lambda e: (OBJEKTE.index(e["objekt"]), e["objekt_id"]))
    return _neu(buch, quelle, aktion, gruppe, zeit, text, eintraege, plus, minus, rueckgaengig_von)


def _neu(buch, quelle, aktion, gruppe, zeit, text, eintraege, plus, minus, von) -> dict:
    aid = buch.neue_id("aenderung")
    a = {"id": aid, "zeitpunkt": zeit, "quelle": quelle, "aktion": aktion, "beschreibung": text, "gruppe": gruppe,
         "eintraege": eintraege, "rueckgaengig_von": sorted(von or []), "_plus": sorted(plus), "_minus": sorted(minus)}
    buch.aenderungen[aid] = a
    return a


def rueckgaengig_durch(buch, aid: int) -> int | None:
    for u in sorted(buch.aenderungen.values(), key=lambda x: x["id"]):
        if aid in u["rueckgaengig_von"] and rueckgaengig_durch(buch, u["id"]) is None:
            return u["id"]
    return None


def aenderung_json(buch, a: dict) -> dict:
    return {**{k: copy.deepcopy(v) for k, v in a.items() if not k.startswith("_")},
            "rueckgaengig_durch": rueckgaengig_durch(buch, a["id"])}


def _setze(buch, objekt: str, oid: int, form: dict | None) -> None:
    tab = getattr(buch, TABELLE[objekt])
    if form is None:
        tab.pop(oid, None)
        return
    f = copy.deepcopy(form)
    if objekt == "konto":
        f.pop("waehrung"), f.pop("ist_kategorie")
    elif objekt == "vorlage":
        f.pop("gesamtbetrag")
    elif objekt == "buchung":
        f["tag_ids"] = set(f["tag_ids"])
        if mutant("undo_splits_neue_ids"):
            for s in f["splits"]:
                s["id"] = buch.neue_id("split")
    tab[oid] = f


def bezuege_ok(buch) -> bool:
    if mutant("undo_ohne_bezugspruefung"):
        return True
    k = buch.konten
    for x in k.values():
        e, seen = x["eltern_id"], set()
        while e is not None:
            if e not in k or e in seen or e == x["id"]:
                return False
            seen.add(e)
            e = k[e]["eltern_id"]
    for b in buch.buchungen.values():
        if any(s["konto_id"] not in k or (s.get("abstimmung_id") is not None
                                          and s["abstimmung_id"] not in buch.abstimmungen) for s in b["splits"]):
            return False
        if b["empfaenger_id"] is not None and b["empfaenger_id"] not in buch.empfaenger:
            return False
        if not b["tag_ids"] <= set(buch.tags):
            return False
        v = b.get("vorschlag")
        if v and v["regel_id"] is not None and v["regel_id"] not in buch.regeln:
            return False
    for r in buch.regeln.values():
        if r["kategorie_id"] not in k or any(c["feld"] == "konto_id" and c["wert"] not in k for c in r["bedingungen"]):
            return False
    for e in buch.empfaenger.values():
        if e.get("standardkategorie_id") is not None and e["standardkategorie_id"] not in k:
            return False
    if any(a["konto_id"] not in k for a in buch.abstimmungen.values()):
        return False
    for v in buch.vorlagen.values():
        if any(t["kategorie_id"] not in k for t in v["teile"]) or any(
                c["feld"] == "konto_id" and c["wert"] not in k for c in v["bedingungen"]):
            return False
    for v in buch.verdachte.values():
        if v["status"] == "offen" and not ({v["buchung_id"], *v["kandidat_ids"]} <= set(buch.buchungen)):
            return False
    from .m5 import kredit_bezuege_ok
    if not kredit_bezuege_ok(buch):
        return False

    def eindeutig(xs):
        xs = list(xs)
        return len(xs) == len(set(xs))
    return (eindeutig(x["iban"] for x in k.values() if x["iban"]) and eindeutig(e["name"] for e in buch.empfaenger.values())
            and eindeutig(ekey(a) for e in buch.empfaenger.values() for a in e.get("aliase", []))
            and eindeutig(t["name"].casefold() for t in buch.tags.values())
            and eindeutig(p["adresse"].casefold() for p in getattr(buch, "postfaecher", {}).values()))


def rueckgaengig(buch, ids: list[int], zeit: str, *, leer_fehler: bool = False) -> dict:
    vorher = protokollform(buch)
    sync_vorher = copy.deepcopy(buch.sync_konten)
    sync_gesetzt = False
    neu = buch.kopie()
    for aid in sorted(ids, reverse=True):
        a = neu.aenderungen[aid]
        jetzt = protokollform(neu)
        if not mutant("undo_ohne_zustandspruefung"):
            for e in a["eintraege"]:
                if jetzt.get((e["objekt"], e["objekt_id"])) != e["nachher"]:
                    raise Fehler(409, "rueckgaengig_konflikt", "Das Objekt wurde inzwischen verändert",
                                 {"objekt": e["objekt"], "objekt_id": e["objekt_id"]})
        for e in a["eintraege"]:
            _setze(neu, e["objekt"], e["objekt_id"], e["vorher"])
        if not mutant("undo_kennungen_bleiben"):
            neu.gemerkt -= set(a["_plus"])
        neu.gemerkt |= set(a["_minus"])
        if "_sync" in a:  # protokoll.md 10.2: Einspielen einer Sicherung
            neu.sync_konten = copy.deepcopy(a["_sync"][0])
            sync_gesetzt = True
    if not bezuege_ok(neu):
        raise Fehler(409, "rueckgaengig_konflikt", "Bezüge oder Eindeutigkeit wären verletzt")
    namen_pruefen(neu.konten)   # M32 (sammel3.md 1.2): nach Zustand und Bezügen
    # protokoll.md 6.4: nur Einträge, deren Konto durch dieses Rückgängig entfernt wurde
    for iban, z in list(neu.sync_konten.items()) if not sync_gesetzt else []:
        if z["konto_id"] in buch.konten and z["konto_id"] not in neu.konten:
            if z.get("_wiederhergestellt") == z["konto_id"] and not mutant("undo_wiederherstellung_eintrag_weg"):
                z.pop("_entscheidung", None)
            else:
                del neu.sync_konten[iban]
    buch.uebernehme(neu)
    u = protokolliere(buch, vorher, "rueckgaengig", "rueckgaengig", None, zeit, "Rückgängig gemacht",
                      rueckgaengig_von=list(ids))
    if u is None and leer_fehler and not mutant("m15_bis_leer_200"):
        # M15 (E-190): Nettowirkung leer → nichts zurückzunehmen; es hat sich nichts geändert
        raise Fehler(409, "bereits_rueckgaengig", "Nichts zurückzunehmen")
    if u is None:  # nur möglich, wenn sich nichts geändert hat
        u = _neu(buch, "rueckgaengig", "rueckgaengig", None, zeit, "Rückgängig gemacht", [], [], [], list(ids))
    if sync_gesetzt:
        u["_sync"] = (sync_vorher, copy.deepcopy(buch.sync_konten))
    return u


# ===================================================================== Empfänger
def aliase_bereinigen(liste: list) -> list[str]:
    if not isinstance(liste, list) or len(liste) > 100:
        raise _v(["body", "aliase"], "Liste mit höchstens 100 Einträgen erwartet")
    aus, schl = [], set()
    for i, a in enumerate(liste):
        if not isinstance(a, str):
            raise _v(["body", "aliase", i], "Text erwartet")
        a = a.strip()
        if not (1 <= len(a) <= 200) or not ekey(a):
            raise _v(["body", "aliase", i], "Alias ungültig")
        if ekey(a) not in schl:
            schl.add(ekey(a))
            aus.append(a)
    return sorted(aus)


def _alias_gleich(a: str, b: str) -> bool:
    return a == b if mutant("alias_ohne_ekey") else bool(ekey(a)) and ekey(a) == ekey(b)


def alias_treffer(buch, name: str | None) -> dict | None:
    if name is None:
        return None
    for e in buch.empfaenger.values():
        if any(_alias_gleich(name, a) for a in e.get("aliase", [])):
            return e
    return None


def empfaenger_suchen(buch, name: str | None) -> dict | None:
    if name is None or not name.strip():
        return None
    n = name.strip()
    return next((e for e in buch.empfaenger.values() if e["name"] == n), None) or alias_treffer(buch, n)


def empfaenger_fuer_name(buch, name: str) -> int:
    e = empfaenger_suchen(buch, name)
    return e["id"] if e else buch.empfaenger_anlegen(name.strip(), rest=False)["id"]


def _alias_frei(buch, aliase: list[str], eigene_id: int | None) -> None:
    for a in aliase:
        for e in buch.empfaenger.values():
            if e["id"] != eigene_id and any(ekey(x) == ekey(a) for x in e.get("aliase", [])):
                raise Fehler(409, "alias_existiert", "Alias gehört bereits zu einem anderen Empfänger",
                             {"alias": a, "empfaenger_id": e["id"]})


def _keine_stdkat(kid) -> None:
    """M32 (sammel3.md 2.1): am Empfänger nur noch null."""
    if kid is not None and not mutant("m32_standardkategorie_bleibt"):
        raise Fehler(422, "kategorie_ungueltig", "Keine Standardkategorie mehr")


def _stdkat(buch, kid) -> None:
    if kid is not None and (type(kid) is not int or kid not in buch.konten
                            or buch.konten[kid]["art"] not in ("aufwand", "ertrag")):
        raise Fehler(422, "kategorie_ungueltig", "Keine Kategorie")


def zusammenfuehren_empfaenger(buch, ziel_id: int, quelle_ids: list[int], name: str | None = None) -> dict:
    if ziel_id not in buch.empfaenger:
        raise Fehler(404, "nicht_gefunden", "Empfänger nicht gefunden")
    if ziel_id in quelle_ids:
        raise _v(["body", "quelle_ids"], "Ziel darf keine Quelle sein")
    unbekannt = sorted(i for i in quelle_ids if i not in buch.empfaenger)
    if unbekannt:
        raise Fehler(422, "referenz_unbekannt", "Empfänger unbekannt", {"empfaenger_ids": unbekannt})
    z = buch.empfaenger[ziel_id]
    q = sorted((buch.empfaenger[i] for i in quelle_ids), key=lambda e: e["id"])
    # M11, buchhaltungspflege.md 10: optionaler neuer Name
    if name is not None and any(e["name"] == name for e in buch.empfaenger.values()
                                if e["id"] != ziel_id and e["id"] not in quelle_ids):
        raise Fehler(409, "empfaenger_existiert", "Empfänger existiert bereits", {"name": name})
    alter_name = z["name"]
    neuer_name = name if name is not None and not mutant("zusammenfuehren_name_ignoriert") else alter_name
    dritte = {ekey(a) for e in buch.empfaenger.values() if e["id"] != ziel_id and e["id"] not in quelle_ids
              for a in e.get("aliase", [])}
    neu, schl = [], set()
    kandidaten = list(z["aliase"]) + ([alter_name] if neuer_name != alter_name
                                      and not mutant("zusammenfuehren_alter_name_fehlt") else []) + \
        ([] if mutant("zusammenfuehren_ohne_alias") else [x for e in q for x in [e["name"], *e["aliase"]]])
    for a in kandidaten:
        k = ekey(a)
        if not k or k == ekey(neuer_name) or k in schl or k in dritte:
            continue
        schl.add(k)
        neu.append(a)
    for b in buch.buchungen.values():
        if b["empfaenger_id"] in quelle_ids:
            b["empfaenger_id"] = ziel_id
    for e in q:
        del buch.empfaenger[e["id"]]
    z["aliase"] = sorted(neu)
    z["name"] = neuer_name
    return z


# ===================================================================== Umbuchungen
def kandidat(buch, b: dict) -> bool:
    if len(b["splits"]) != 2 or buch.gesperrt(b):
        return False
    bank = [s for s in b["splits"] if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand"]
    gegen = [s for s in b["splits"] if KLASSE[buch.konten[s["konto_id"]]["art"]] != "bestand"]
    return len(bank) == 1 and len(gegen) == 1 and bank[0]["betrag"] != 0 and \
        buch.konten[gegen[0]["konto_id"]]["extern_id"] == UNK


def _bank(buch, b):
    return next(s for s in b["splits"] if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand")


def passen(buch, x: dict, y: dict, fenster: int, *, streng: bool = True) -> bool:
    sx, sy = _bank(buch, x), _bank(buch, y)
    if sx["konto_id"] == sy["konto_id"] or sx["betrag"] != -sy["betrag"]:
        return False
    if not streng:
        return True
    tage = abs((dt.date.fromisoformat(x["datum"]) - dt.date.fromisoformat(y["datum"])).days)
    if (tage >= fenster if mutant("umbuchung_fenster_exklusiv") else tage > fenster):
        return False
    if mutant("umbuchung_ohne_iban"):
        return True
    ix, iy = buch.konten[sx["konto_id"]]["iban"], buch.konten[sy["konto_id"]]["iban"]
    gx, gy = x.get("gegen_iban"), y.get("gegen_iban")
    if (gx is not None and gx != iy) or (gy is not None and gy != ix):
        return False
    return (gx is not None and gx == iy) or (gy is not None and gy == ix)


def eindeutige_paare(buch, fenster: int) -> list[tuple[int, int]]:
    c = [b for b in buch.buchungen.values() if kandidat(buch, b)]
    p = {b["id"]: {y["id"] for y in c if y["id"] != b["id"] and passen(buch, b, y, fenster)} for b in c}
    aus: list[tuple[int, int]] = []
    benutzt: set[int] = set()
    for x, ys in sorted(p.items()):
        if len(ys) != 1:
            continue
        (y,) = ys
        if mutant("umbuchung_ohne_eindeutigkeit"):
            if x in benutzt or y in benutzt:
                continue
        elif p[y] != {x}:
            continue
        paar = (min(x, y), max(x, y))
        if paar not in aus:
            aus.append(paar)
            benutzt |= set(paar)
    return sorted(aus)


def umbuchung_zusammenfuehren(buch, xid: int, yid: int) -> dict:
    x, y = buch.buchungen[min(xid, yid)], buch.buchungen[max(xid, yid)]
    x["splits"] = [_bank(buch, x), _bank(buch, y)]
    x["extern_ids"] = sorted(set(x["extern_ids"]) | set(y["extern_ids"]))
    x["tag_ids"] = x["tag_ids"] | y["tag_ids"]
    x["vorschlag"] = None
    buch.buchung_loeschen(y["id"])
    return x


# ======================================================================== Suche
def snorm(s: str) -> str:
    if not mutant("suche_ohne_nfc"):
        s = unicodedata.normalize("NFC", s)
    s = norm(s)
    if mutant("suche_ohne_akzente"):
        return s
    return "".join(z for z in unicodedata.normalize("NFKD", s) if unicodedata.category(z) != "Mn")


def treffer(woerter: list[str], felder: list[str]) -> bool:
    fs = [snorm(f) for f in felder if f]
    if mutant("suche_oder"):
        return any(any(w in f for f in fs) for w in woerter)
    return all(any(w in f for f in fs) for w in woerter)


# ======================================================================= Modelle
class EmpfaengerNeu(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    aliase: list = []
    standardkategorie_id: StrictInt | None = None


class EmpfaengerAenderung(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    aliase: list = None
    standardkategorie_id: StrictInt | None = None


class Zusammenfuehren(M):
    quelle_ids: Annotated[list[StrictInt], Field(min_length=1, max_length=100)]
    name: StrictStr = None   # M11; null ist ungültig


class Erfassen(M):
    art: Literal["ausgabe", "einnahme", "umbuchung", "korrektur"]
    datum: StrictStr
    konto_id: StrictInt
    betrag: Annotated[StrictInt, Field(ge=-MAX, le=MAX)]
    kategorie_id: StrictInt | None = None
    gegenkonto_id: StrictInt = None
    empfaenger_id: StrictInt | None = None
    empfaenger_name: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    verwendungszweck: Annotated[StrictStr, Field(max_length=10000)] = ""
    memo: Annotated[StrictStr, Field(max_length=10000)] = ""
    tag_ids: list[StrictInt] = []
    status: Literal["importiert", "vorlaeufig", "bestaetigt"] = "bestaetigt"


class Erkennen(M):
    trocken: StrictBool = False


class UmbZus(M):
    buchung_ids: Annotated[list[StrictInt], Field(min_length=2, max_length=2)]


class AbstEingabe(M):
    konto_id: StrictInt
    stichtag: StrictStr
    saldo: Annotated[StrictInt, Field(ge=-MAX, le=MAX)]
    trocken: StrictBool = False


class RueckgaengigEingabe(M):
    aenderung_ids: Annotated[list[StrictInt], Field(min_length=1, max_length=1000)] = None
    gruppe: Annotated[StrictStr, Field(min_length=1)] = None
    bis_id: StrictInt = None   # M15, protokoll.md 6.2a


def _datum(s: str, ort) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        raise _v(ort, "Datum erwartet")
    try:
        dt.date.fromisoformat(s)
    except ValueError:
        raise _v(ort, "Datum ungültig") from None
    return s


# ====================================================================== Routen
MANUELL = [
    ("POST", r"/api/konten", "konto_anlegen"), ("PATCH", r"/api/konten/\d+", "konto_aendern"),
    ("DELETE", r"/api/konten/\d+", "konto_loeschen"), ("POST", r"/api/buchungen", "buchung_anlegen"),
    ("POST", r"/api/konten/\d+/loeschen", "konto_loeschen_mit_buchungen"),
    ("POST", r"/api/buchungen/erfassen", "buchung_erfassen"), ("PATCH", r"/api/buchungen/\d+", "buchung_aendern"),
    ("DELETE", r"/api/buchungen/\d+", "buchung_loeschen"), ("PUT", r"/api/buchungen/\d+/splits", "splits_ersetzen"),
    ("PUT", r"/api/buchungen/\d+/kategorie", "kategorie_setzen"),
    ("POST", r"/api/buchungen/mehrfach/kategorie", "mehrfach_kategorie"),
    ("POST", r"/api/buchungen/mehrfach/tags", "mehrfach_tags"),
    ("POST", r"/api/buchungen/mehrfach/aendern", "mehrfach_aendern"),
    ("POST", r"/api/buchungen/mehrfach/loeschen", "mehrfach_loeschen"),
    ("POST", r"/api/buchungen/mehrfach/verschieben", "mehrfach_verschieben"),
    ("POST", r"/api/buchungen/\d+/vorschlag", "vorschlag_entscheiden"),
    ("POST", r"/api/buchungen/mehrfach/vorschlag", "mehrfach_vorschlag"),
    ("POST", r"/api/tags", "tag_anlegen"), ("PATCH", r"/api/tags/\d+", "tag_umbenennen"),
    ("DELETE", r"/api/tags/\d+", "tag_loeschen"), ("POST", r"/api/empfaenger", "empfaenger_anlegen"),
    ("PATCH", r"/api/empfaenger/\d+", "empfaenger_aendern"), ("DELETE", r"/api/empfaenger/\d+", "empfaenger_loeschen"),
    ("POST", r"/api/empfaenger/\d+/zusammenfuehren", "empfaenger_zusammenfuehren"),
    ("PUT", r"/api/empfaenger/\d+/wiederkehrend", "wiederkehrend_filter_setzen"),
    ("DELETE", r"/api/empfaenger/\d+/wiederkehrend", "wiederkehrend_filter_setzen"),
    ("POST", r"/api/dubletten/\d+/aufloesen", "dublette_aufloesen"), ("POST", r"/api/regeln", "regel_anlegen"),
    ("PATCH", r"/api/regeln/\d+", "regel_aendern"), ("DELETE", r"/api/regeln/\d+", "regel_loeschen"),
    ("POST", r"/api/regeln/anwenden", "regeln_anwenden"), ("POST", r"/api/abstimmungen", "abstimmung_anlegen"),
    ("DELETE", r"/api/abstimmungen/\d+", "abstimmung_aufheben"),
    ("POST", r"/api/umbuchungen/zusammenfuehren", "umbuchung_zusammenfuehren"),
    ("POST", r"/api/umbuchungen/erkennen", "umbuchung_erkennen"),
    ("POST", r"/api/mail/postfaecher", "postfach_anlegen"), ("PATCH", r"/api/mail/postfaecher/\d+", "postfach_aendern"),
    ("DELETE", r"/api/mail/postfaecher/\d+", "postfach_loeschen"),
]
QUELLE = {"regeln_anwenden": "regeln", "umbuchung_erkennen": "umbuchung"}


def m3_einbinden(app: FastAPI, config, buch) -> None:
    dienst = app.state.dienst

    def jetzt() -> str:
        return dienst.jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")

    @app.middleware("http")
    async def protokoll(request: Request, call_next):
        aktion = next((a for m, p, a in MANUELL if request.method == m and re.fullmatch(p, request.url.path)), None)
        if aktion is None:
            return await call_next(request)
        if mutant("protokoll_fehlt_mehrfach_tags") and aktion == "mehrfach_tags":
            return await call_next(request)
        vorher = protokollform(buch)
        antwort = await call_next(request)
        if antwort.status_code < 400:
            protokolliere(buch, vorher, QUELLE.get(aktion, "manuell"), aktion, None, jetzt(), f"Aktion {aktion}")
        return antwort

    # --------------------------------------------------------- Empfänger
    @app.patch("/api/empfaenger/{empfaenger_id}")
    def empfaenger_aendern(empfaenger_id: int, d: EmpfaengerAenderung):
        if empfaenger_id not in buch.empfaenger:
            raise Fehler(404, "nicht_gefunden", "Empfänger nicht gefunden")
        e = buch.empfaenger[empfaenger_id]
        felder = d.model_fields_set
        neu = dict(e)
        if "name" in felder:
            if d.name is None or not d.name.strip():
                raise _v(["body", "name"], "Name leer")
            n = d.name.strip()
            if any(x["name"] == n and x["id"] != empfaenger_id for x in buch.empfaenger.values()):
                raise Fehler(409, "empfaenger_existiert", "Empfänger existiert")
            neu["name"] = n
        if "aliase" in felder:
            if d.aliase is None:
                raise _v(["body", "aliase"], "null nicht erlaubt")
            neu["aliase"] = aliase_bereinigen(d.aliase)
            _alias_frei(buch, neu["aliase"], empfaenger_id)
        if "standardkategorie_id" in felder:
            _keine_stdkat(d.standardkategorie_id)
            _stdkat(buch, d.standardkategorie_id)
            neu["standardkategorie_id"] = d.standardkategorie_id
        e.update(neu)
        return e

    @app.delete("/api/empfaenger/{empfaenger_id}", status_code=204)
    def empfaenger_loeschen(empfaenger_id: int):
        if empfaenger_id not in buch.empfaenger:
            raise Fehler(404, "nicht_gefunden", "Empfänger nicht gefunden")
        if any(b["empfaenger_id"] == empfaenger_id for b in buch.buchungen.values()):
            raise Fehler(409, "empfaenger_in_verwendung", "Empfänger hat Buchungen")
        del buch.empfaenger[empfaenger_id]
        return Response(status_code=204)

    @app.post("/api/empfaenger/{empfaenger_id}/zusammenfuehren")
    def empfaenger_zusammen(empfaenger_id: int, d: Zusammenfuehren):
        if len(set(d.quelle_ids)) != len(d.quelle_ids):
            raise _v(["body", "quelle_ids"], "doppelt")
        name = None
        if d.name is not None:
            name = d.name.strip()
            if not 1 <= len(name) <= 200:
                raise _v(["body", "name"], "Name ungültig")
        return zusammenfuehren_empfaenger(buch, empfaenger_id, d.quelle_ids, name)

    # ---------------------------------------------------------- Erfassen
    @app.post("/api/buchungen/erfassen", status_code=201)
    def erfassen(d: Erfassen):
        _datum(d.datum, ["body", "datum"])
        felder = d.model_fields_set
        if d.art == "korrektur" and d.betrag == 0 or d.art != "korrektur" and d.betrag <= 0:
            raise _v(["body", "betrag"], "Betrag ungültig")
        if d.art == "umbuchung":
            if "gegenkonto_id" not in felder or "kategorie_id" in felder:
                raise _v(["body", "gegenkonto_id"], "Umbuchung braucht gegenkonto_id und keine Kategorie")
        elif "gegenkonto_id" in felder:
            raise _v(["body", "gegenkonto_id"], "nur bei Umbuchung")
        if "empfaenger_id" in felder and "empfaenger_name" in felder:
            raise _v(["body", "empfaenger_name"], "nicht zusammen mit empfaenger_id")
        if d.empfaenger_name is not None and not d.empfaenger_name.strip():
            raise _v(["body", "empfaenger_name"], "leer")
        for kid in [d.konto_id] + ([d.gegenkonto_id] if d.art == "umbuchung" else []):
            if kid not in buch.konten:
                raise Fehler(422, "referenz_unbekannt", "Konto unbekannt")
        if d.empfaenger_id is not None and d.empfaenger_id not in buch.empfaenger:
            raise Fehler(422, "referenz_unbekannt", "Empfänger unbekannt")
        if any(t not in buch.tags for t in d.tag_ids):
            raise Fehler(422, "referenz_unbekannt", "Tag unbekannt")
        for kid in [d.konto_id] + ([d.gegenkonto_id] if d.art == "umbuchung" else []):
            if KLASSE[buch.konten[kid]["art"]] != "bestand":
                raise Fehler(422, "konto_ungueltig", "Kein Bestandskonto")
        if d.art == "umbuchung" and d.gegenkonto_id == d.konto_id:
            raise Fehler(422, "konto_ungueltig", "Gleiche Konten")
        if d.kategorie_id is not None:
            _stdkat(buch, d.kategorie_id)
        from .m2 import unkategorisiert
        eid = d.empfaenger_id
        if d.empfaenger_name is not None:
            eid = empfaenger_fuer_name(buch, d.empfaenger_name)
        vorschlag = None
        b_ = d.betrag
        if d.art == "umbuchung":
            splits = [(d.konto_id, -b_), (d.gegenkonto_id, b_)]
        else:
            g = d.kategorie_id
            if g is None and d.art != "korrektur":
                e = buch.empfaenger.get(eid) if eid is not None else None
                lern = None
                if not (e and e.get("standardkategorie_id") is not None) and config.lernmodell_automatisch:
                    from .m4 import Lernmodell
                    vz = -1 if d.art == "ausgabe" else 1
                    lern = Lernmodell(buch).vorhersage(e["name"] if e else None, d.verwendungszweck, vz * d.betrag)
                if e and e.get("standardkategorie_id") is not None:
                    g = e["standardkategorie_id"]
                    vorschlag = {"kategorie_id": g, "regel_id": None, "quelle": "standardkategorie",
                                 "vorher_konto_id": unkategorisiert(buch)}
                elif lern and lern["kategorie_id"] is not None:
                    g = lern["kategorie_id"]
                    vorschlag = {"kategorie_id": g, "regel_id": None, "quelle": "lernmodell",
                                 "vorher_konto_id": unkategorisiert(buch), "sicherheit": lern["sicherheit"]}
                else:
                    g = unkategorisiert(buch)
            if g is None:
                g = next((k["id"] for k in buch.konten.values() if k["extern_id"] == KORR), None) or \
                    buch.konto_anlegen({"name": "Korrekturen", "art": "eigenkapital"}, extern_id=KORR)["id"]
            vz = {"ausgabe": -1, "einnahme": 1, "korrektur": 1}[d.art]
            splits = [(d.konto_id, vz * b_), (g, -vz * b_)]
        b = buch.buchung_anlegen({"datum": d.datum, "empfaenger_id": eid, "verwendungszweck": d.verwendungszweck,
                                  "status": d.status, "tag_ids": d.tag_ids,
                                  "splits": [{"konto_id": k, "betrag": x, "memo": d.memo} for k, x in splits]})
        b["vorschlag"] = vorschlag
        return buch.buchung_json(b)

    # -------------------------------------------------------- Umbuchungen
    @app.post("/api/umbuchungen/erkennen")
    def erkennen(d: Erkennen | None = Body(None)):
        d = d or Erkennen()
        paare = eindeutige_paare(buch, config.umbuchung_fenster_tage)
        if not d.trocken:
            for x, y in paare:
                umbuchung_zusammenfuehren(buch, x, y)
        return {"trocken": d.trocken, "anzahl": len(paare),
                "paare": [{"behalten_id": x, "entfernt_id": y} for x, y in paare]}

    @app.post("/api/umbuchungen/zusammenfuehren")
    def umb_zus(d: UmbZus):
        ids = d.buchung_ids
        if ids[0] == ids[1]:
            raise _v(["body", "buchung_ids"], "zwei verschiedene IDs")
        unbekannt = sorted(i for i in ids if i not in buch.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        gesperrt = sorted(i for i in ids if buch.gesperrt(buch.buchungen[i]))
        if gesperrt:
            raise Fehler(409, "buchung_gesperrt", "Buchung gesperrt", {"buchung_ids": gesperrt})
        x, y = (buch.buchungen[i] for i in ids)
        if not (kandidat(buch, x) and kandidat(buch, y) and passen(buch, x, y, 0, streng=False)):
            raise Fehler(422, "keine_umbuchung", "Keine passenden Seiten einer Umbuchung")
        return buch.buchung_json(umbuchung_zusammenfuehren(buch, x["id"], y["id"]))

    # --------------------------------------------------------- Abstimmung
    @app.get("/api/abstimmungen")
    def abstimmungen(konto_id: int | None = None):
        return [a for a in sorted(buch.abstimmungen.values(), key=lambda a: a["id"])
                if konto_id is None or a["konto_id"] == konto_id]

    @app.post("/api/abstimmungen")
    def abstimmen(d: AbstEingabe):
        _datum(d.stichtag, ["body", "stichtag"])
        if d.konto_id not in buch.konten:
            raise Fehler(422, "referenz_unbekannt", "Konto unbekannt")
        if KLASSE[buch.konten[d.konto_id]["art"]] != "bestand":
            raise Fehler(422, "konto_ungueltig", "Kein Bestandskonto")

        def bis(b):
            return b["datum"] < d.stichtag if mutant("abstimmung_stichtag_exklusiv") else b["datum"] <= d.stichtag
        berechnet = sum(s["betrag"] for b in buch.buchungen.values() if bis(b) for s in b["splits"]
                        if s["konto_id"] == d.konto_id)
        m = [s for b in buch.buchungen.values() if bis(b) for s in b["splits"]
             if s["konto_id"] == d.konto_id and s.get("abstimmung_id") is None]
        stimmt = d.saldo == berechnet
        neu = None
        if (stimmt or mutant("abstimmung_trotz_differenz")) and not d.trocken:
            aid = buch.neue_id("abstimmung")
            neu = {"id": aid, "konto_id": d.konto_id, "stichtag": d.stichtag, "saldo": d.saldo, "erstellt_am": jetzt()}
            buch.abstimmungen[aid] = neu
            for s in m:
                s["abstimmung_id"] = aid
        return {"konto_id": d.konto_id, "stichtag": d.stichtag, "saldo": d.saldo, "berechneter_saldo": berechnet,
                "differenz": d.saldo - berechnet, "stimmt": stimmt, "abgestimmt": neu is not None,
                "anzahl_splits": len(m), "abstimmung": dict(neu) if neu else None}

    def _abst(aid):
        if aid not in buch.abstimmungen:
            raise Fehler(404, "nicht_gefunden", "Abstimmung nicht gefunden")
        return buch.abstimmungen[aid]

    @app.get("/api/abstimmungen/{abstimmung_id}")
    def abstimmung_lesen(abstimmung_id: int):
        return _abst(abstimmung_id)

    @app.delete("/api/abstimmungen/{abstimmung_id}", status_code=204)
    def abstimmung_aufheben(abstimmung_id: int):
        a = _abst(abstimmung_id)
        letzte = max((x for x in buch.abstimmungen.values() if x["konto_id"] == a["konto_id"]),
                     key=lambda x: (x["stichtag"], x["id"]))
        if letzte["id"] != a["id"]:
            raise Fehler(409, "abstimmung_nicht_letzte", "Nur die letzte Abstimmung kann aufgehoben werden")
        for b in buch.buchungen.values():
            for s in b["splits"]:
                if s.get("abstimmung_id") == abstimmung_id:
                    s["abstimmung_id"] = None
        del buch.abstimmungen[abstimmung_id]
        return Response(status_code=204)

    # -------------------------------------------------------------- Suche
    @app.get("/api/suche")
    def suche(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(50, ge=1, le=500)):
        w = [snorm(x) for x in q.split()]
        if not w:
            raise _v(["query", "q"], "kein Wort")
        konten = [buch.konto_json(k) for k in sorted(buch.konten.values(), key=lambda k: k["id"])
                  if treffer(w, [k["name"], k["iban"] or "", k["notiz"]])]
        emp = [e for e in sorted(buch.empfaenger.values(), key=lambda e: e["id"])
               if treffer(w, [e["name"], *e.get("aliase", [])])]
        tags = [buch.tag_json(t) for t in sorted(buch.tags.values(), key=lambda t: t["id"]) if treffer(w, [t["name"]])]
        bs = []
        for b in sorted(buch.buchungen.values(), key=lambda b: (b["datum"], b["id"]), reverse=True):
            f = [b["verwendungszweck"]] + [s["memo"] for s in b["splits"]] + \
                [buch.tags[t]["name"] for t in b["tag_ids"]] + [buch.konten[s["konto_id"]]["name"] for s in b["splits"]]
            if b["empfaenger_id"] is not None:
                f.append(buch.empfaenger[b["empfaenger_id"]]["name"])
            if treffer(w, f):
                bs.append(b)
        return {"q": q, "konten": konten, "empfaenger": emp, "tags": tags,
                "buchungen": [buch.buchung_json(b) for b in bs[:limit]], "buchungen_gesamt": len(bs)}

    # ---------------------------------------------------------- Protokoll
    @app.get("/api/aenderungen")
    def aenderungen(quelle: list[Literal["manuell", "import", "sync", "regeln", "umbuchung", "rueckgaengig",
                                       "sicherung"]] = Query([]),
                    aktion: str | None = Query(None, min_length=1), gruppe: str | None = Query(None, min_length=1),
                    objekt: Literal["konto", "empfaenger", "tag", "buchung", "regel", "verdacht",
                                    "abstimmung"] | None = None,
                    objekt_id: int | None = None, wirksam: bool | None = None, seite: int = Query(1, ge=1),
                    pro_seite: int = Query(50, ge=1, le=500)):
        if objekt_id is not None and objekt is None:
            raise _v(["query", "objekt_id"], "nur mit objekt")
        aus = []
        for a in sorted(buch.aenderungen.values(), key=lambda a: a["id"], reverse=True):
            if quelle and a["quelle"] not in quelle:
                continue
            if aktion and a["aktion"] != aktion or gruppe and a["gruppe"] != gruppe:
                continue
            if objekt and not any(e["objekt"] == objekt and (objekt_id is None or e["objekt_id"] == objekt_id)
                                  for e in a["eintraege"]):
                continue
            if wirksam is not None and (rueckgaengig_durch(buch, a["id"]) is None) != wirksam:
                continue
            aus.append(a)
        return {"eintraege": [aenderung_json(buch, a) for a in aus[(seite - 1) * pro_seite: seite * pro_seite]],
                "gesamt": len(aus), "seite": seite, "pro_seite": pro_seite}

    @app.post("/api/aenderungen/rueckgaengig")
    def mehrere_rueckgaengig(d: RueckgaengigEingabe):
        felder = d.model_fields_set
        if len(felder) != 1 or getattr(d, next(iter(felder))) is None:
            raise _v(["body"], "genau eines von aenderung_ids, gruppe, bis_id")
        if "bis_id" in felder:
            if d.bis_id not in buch.aenderungen:
                raise Fehler(404, "nicht_gefunden", "Änderung nicht gefunden")
            # protokoll.md 6.2a: absteigend jede im Zwischenstand wirksame Änderung ≥ bis_id – das sind alle
            ids = [i for i in buch.aenderungen if (i > d.bis_id if mutant("m15_bis_ohne_bis_id") else i >= d.bis_id)]
            if mutant("m15_bis_ohne_paare"):
                ids = [i for i in ids if rueckgaengig_durch(buch, i) is None]
            if not ids:
                raise Fehler(409, "bereits_rueckgaengig", "Nichts zurückzunehmen")
            with dienst.sperre:
                return aenderung_json(buch, rueckgaengig(buch, ids, jetzt(), leer_fehler=True))
        if "aenderung_ids" in felder:
            ids = d.aenderung_ids
            if len(set(ids)) != len(ids):
                raise _v(["body", "aenderung_ids"], "doppelt")
            unbekannt = sorted(i for i in ids if i not in buch.aenderungen)
            if unbekannt:
                raise Fehler(422, "referenz_unbekannt", "Änderungen unbekannt", {"aenderung_ids": unbekannt})
            nicht = sorted(i for i in ids if rueckgaengig_durch(buch, i) is not None)
            if nicht:
                raise Fehler(409, "bereits_rueckgaengig", "Bereits rückgängig gemacht", {"aenderung_ids": nicht})
        else:
            alle = [a["id"] for a in buch.aenderungen.values() if a["gruppe"] == d.gruppe]
            if not alle:
                raise Fehler(422, "referenz_unbekannt", "Gruppe unbekannt")
            ids = [i for i in alle if rueckgaengig_durch(buch, i) is None]
            if not ids:
                raise Fehler(409, "bereits_rueckgaengig", "Bereits rückgängig gemacht")
        with dienst.sperre:
            return aenderung_json(buch, rueckgaengig(buch, ids, jetzt()))

    @app.get("/api/aenderungen/{aenderung_id}")
    def aenderung_lesen(aenderung_id: int):
        if aenderung_id not in buch.aenderungen:
            raise Fehler(404, "nicht_gefunden", "Änderung nicht gefunden")
        return aenderung_json(buch, buch.aenderungen[aenderung_id])

    @app.post("/api/aenderungen/{aenderung_id}/rueckgaengig")
    def eine_rueckgaengig(aenderung_id: int):
        if aenderung_id not in buch.aenderungen:
            raise Fehler(404, "nicht_gefunden", "Änderung nicht gefunden")
        if rueckgaengig_durch(buch, aenderung_id) is not None:
            raise Fehler(409, "bereits_rueckgaengig", "Bereits rückgängig gemacht")
        with dienst.sperre:
            return aenderung_json(buch, rueckgaengig(buch, [aenderung_id], jetzt()))


def empfaenger_anlegen(buch, d: EmpfaengerNeu) -> dict:
    aliase = aliase_bereinigen(d.aliase)
    _keine_stdkat(d.standardkategorie_id)
    _stdkat(buch, d.standardkategorie_id)
    n = d.name.strip()
    if not n:
        raise _v(["body", "name"], "Name leer")
    if any(e["name"] == n for e in buch.empfaenger.values()):
        raise Fehler(409, "empfaenger_existiert", "Empfänger existiert")
    _alias_frei(buch, aliase, None)
    e = buch.empfaenger_anlegen(n)
    e["aliase"], e["standardkategorie_id"] = aliase, d.standardkategorie_id
    return e
