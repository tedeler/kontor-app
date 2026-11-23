"""Meilenstein 4 der Wegwerf-Referenz: Lernmodell und Split-Vorlagen. KEIN Anwendungscode.

Das Lernmodell wird bei jeder Vorhersage neu aus dem Buch gezählt (einfach,
nicht schnell). Mutanten über ``kontor.mutant(name)``.
"""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict
from fractions import Fraction
from typing import Annotated, Literal

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from . import mutant
from .buch import KLASSE, MAX, Fehler, ekey, norm

SCHWELLE = Fraction(7, 10)


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _v(ort, meldung):
    return Fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ort, "meldung": meldung}])


# ================================================================ Lernmodell
def merkmale(empf: str | None, zweck: str, betrag: int) -> set[str]:
    m: set[str] = set()
    if empf is not None and ekey(empf):
        m.add("e:" + ekey(empf))
    woerter: list[str] = []
    for w in re.split(r"[^a-z0-9]+", norm(zweck)):
        if len(w) >= 3 and re.search(r"[a-z]", w) and w not in woerter:
            woerter.append(w)
            if len(woerter) == 20:
                break
    m |= {"v:" + w for w in woerter}
    if mutant("lern_ohne_betrag"):
        return m
    m.add("b:0" if betrag == 0 else "b:" + ("+" if betrag > 0 else "-") + str(len(str(abs(betrag)))))
    return m


def regelbetrag(buch, b: dict) -> int:
    return sum(s["betrag"] for s in b["splits"] if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand")


def buchung_merkmale(buch, b: dict) -> set[str]:
    e = buch.empfaenger[b["empfaenger_id"]]["name"] if b["empfaenger_id"] is not None else None
    return merkmale(e, b["verwendungszweck"], regelbetrag(buch, b))


class Lernmodell:
    def __init__(self, buch) -> None:
        self.n, self.nk, self.nf, self.nkf = 0, Counter(), Counter(), defaultdict(Counter)
        for b in buch.buchungen.values():
            kat = buch.kategorie_id(b)
            if kat is None or (b.get("vorschlag") is not None and not mutant("lern_vorschlaege_trainieren")):
                continue
            self.n += 1
            self.nk[kat] += 1
            for f in buchung_merkmale(buch, b):
                self.nf[f] += 1
                self.nkf[f][kat] += 1

    def zustand(self, automatisch: bool) -> dict:
        return {"trainingsbuchungen": self.n, "kategorien": len(self.nk), "merkmale": len(self.nf),
                "automatisch": automatisch, "schwelle_promille": 700}

    def vorhersage_m(self, m: set[str]) -> dict:
        bekannt = sorted(f for f in m if self.nf[f] > 0)
        if not any(f[0] in "ev" for f in bekannt) and not mutant("lern_nur_betrag"):
            return {"kategorie_id": None, "sicherheit": None, "kandidaten": []}
        if not bekannt:
            return {"kategorie_id": None, "sicherheit": None, "kandidaten": []}
        s = {}
        for c, nc in self.nk.items():
            p = Fraction(nc, self.n)
            for f in bekannt:
                p *= Fraction(self.nkf[f][c] + (0 if mutant("lern_ohne_glaettung") else 1), nc + 2)
            s[c] = p
        summe = sum(s.values()) or Fraction(1)
        reihe = sorted(((p / summe, c) for c, p in s.items()), key=lambda x: (-x[0], x[1]))
        kand = [{"kategorie_id": c, "sicherheit": int(p * 1000)} for p, c in reihe[:5]]
        p, c = reihe[0]
        schwelle = Fraction(1, 2) if mutant("lern_schwelle_halb") else SCHWELLE
        if p >= schwelle:
            return {"kategorie_id": c, "sicherheit": int(p * 1000), "kandidaten": kand}
        return {"kategorie_id": None, "sicherheit": None, "kandidaten": kand}

    def vorhersage(self, empf, zweck, betrag) -> dict:
        return self.vorhersage_m(merkmale(empf, zweck, betrag))


# ================================================================ Vorlagen
def vorlage_json(v: dict) -> dict:
    return {**copy.deepcopy(v), "gesamtbetrag": -sum(t["betrag"] for t in v["teile"])}


def _ordnung(buch) -> list[dict]:
    return sorted(buch.vorlagen.values(), key=lambda v: (v["prioritaet"], v["id"]))


def _trifft(c: dict, empf: str | None, zweck: str, konten: set[int]) -> bool:
    if c["feld"] == "konto_id":
        return c["wert"] in konten
    x = empf if c["feld"] == "empfaenger" else zweck
    if x is None:
        return False
    nx, nw = norm(x), norm(c["wert"])
    return {"enthaelt": nw in nx, "gleich": nx == nw, "beginnt_mit": nx.startswith(nw)}[c["operator"]]


def erkenne(buch, empf: str | None, zweck: str, konten: set[int], r: int, ids: list[int] | None = None):
    k = [v for v in _ordnung(buch) if (v["aktiv"] or mutant("vorlage_inaktiv_greift"))
         and (ids is None or v["id"] in ids) and all(_trifft(c, empf, zweck, konten) for c in v["bedingungen"])]
    if not k:
        return "keine", None
    for v in k:
        g = -sum(t["betrag"] for t in v["teile"])
        if g == r or (mutant("vorlage_toleranz") and abs(g - r) <= 1):
            return "treffer", v
        if mutant("vorlage_nur_erste"):
            break
    return "abweichung", k[0]


def teil_splits(buch, v: dict) -> list[dict]:
    return [{"id": buch.neue_id("split"), "konto_id": t["kategorie_id"], "betrag": t["betrag"],
             "memo": "" if mutant("vorlage_ohne_memo") else t["memo"], "abstimmung_id": None} for t in v["teile"]]


class Bedingung(M):
    feld: Literal["empfaenger", "verwendungszweck", "konto_id", "betrag"]
    operator: StrictStr
    wert: StrictStr | StrictInt


class Teil(M):
    kategorie_id: StrictInt
    betrag: Annotated[StrictInt, Field(ge=-MAX, le=MAX)]
    memo: Annotated[StrictStr, Field(max_length=10000)] = ""


class VorlageNeu(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    aktiv: StrictBool = True
    prioritaet: Annotated[StrictInt, Field(ge=0, le=1_000_000)] | None = None
    bedingungen: Annotated[list[Bedingung], Field(min_length=1, max_length=20)]
    teile: Annotated[list[Teil], Field(min_length=2, max_length=50)]


class VorlageAenderung(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    aktiv: StrictBool = None
    prioritaet: Annotated[StrictInt, Field(ge=0, le=1_000_000)] = None
    bedingungen: Annotated[list[Bedingung], Field(min_length=1, max_length=20)] = None
    teile: Annotated[list[Teil], Field(min_length=2, max_length=50)] = None


def _pruefe(buch, name, bedingungen, teile) -> tuple[str | None, list[dict] | None, list[dict] | None]:
    if name is not None and not name.strip():
        raise _v(["body", "name"], "leer")
    bed = None
    if bedingungen is not None:
        bed = []
        for i, c in enumerate(bedingungen):
            ort = ["body", "bedingungen", i]
            if c.feld == "betrag":
                raise _v(ort, "Betragsbedingungen sind bei Vorlagen nicht erlaubt")
            if c.feld == "konto_id":
                if c.operator != "gleich" or not isinstance(c.wert, int):
                    raise _v(ort, "konto_id: gleich, Ganzzahl")
            else:
                if c.operator not in ("enthaelt", "gleich", "beginnt_mit") or not isinstance(c.wert, str) \
                        or not c.wert.strip() or len(c.wert) > 200:
                    raise _v(ort, "Textbedingung ungültig")
            bed.append({"feld": c.feld, "operator": c.operator, "wert": c.wert})
        if not any(c["feld"] == "empfaenger" for c in bed) and not mutant("vorlage_ohne_empfaenger"):
            raise _v(["body", "bedingungen"], "mindestens eine Empfänger-Bedingung")
    tl = None
    if teile is not None:
        if any(t.betrag == 0 for t in teile) or sum(t.betrag for t in teile) == 0:
            raise _v(["body", "teile"], "Teilbetrag 0 oder Summe 0")
        tl = [{"kategorie_id": t.kategorie_id, "betrag": t.betrag, "memo": t.memo} for t in teile]
    if tl is not None:
        for t in tl:
            if t["kategorie_id"] not in buch.konten or buch.konten[t["kategorie_id"]]["art"] not in ("aufwand", "ertrag"):
                raise Fehler(422, "kategorie_ungueltig", "Teil-Kategorie ungültig")
    if bed is not None:
        for c in bed:
            if c["feld"] == "konto_id" and (c["wert"] not in buch.konten
                                            or KLASSE[buch.konten[c["wert"]]["art"]] != "bestand"):
                raise Fehler(422, "referenz_unbekannt", "Konto der Bedingung unbekannt")
    return (name.strip() if name is not None else None), bed, tl


class LernAnwenden(M):
    buchung_ids: Annotated[list[StrictInt], Field(min_length=1)] = None
    trocken: StrictBool = False


class VorlagenAnwenden(M):
    buchung_ids: Annotated[list[StrictInt], Field(min_length=1)] = None
    vorlage_ids: Annotated[list[StrictInt], Field(min_length=1)] = None
    nur_unkategorisiert: StrictBool = True
    trocken: StrictBool = False


class LernMerkmale(M):
    empfaenger: Annotated[StrictStr, Field(max_length=200)] | None = None
    verwendungszweck: Annotated[StrictStr, Field(max_length=10000)] = ""
    betrag: Annotated[StrictInt, Field(ge=-MAX, le=MAX)]


class LernBuchung(M):
    buchung_id: StrictInt


class LernAnfrage(M):
    eintraege: Annotated[list[LernBuchung | LernMerkmale], Field(min_length=1, max_length=1000)]


def _ids_pruefen(buch, ids, tab, feld):
    if ids is None:
        return
    if len(set(ids)) != len(ids):
        raise _v(["body", feld], "doppelte IDs")
    unbekannt = sorted(i for i in ids if i not in tab)
    if unbekannt:
        raise Fehler(422, "referenz_unbekannt", "Unbekannte IDs", {feld: unbekannt})


def m4_einbinden(app: FastAPI, config, buch) -> None:
    from . import m3
    m3.MANUELL[:0] = [("POST", r"/api/vorlagen/anwenden", "vorlagen_anwenden"),
                      ("POST", r"/api/vorlagen", "vorlage_anlegen"), ("PATCH", r"/api/vorlagen/\d+", "vorlage_aendern"),
                      ("DELETE", r"/api/vorlagen/\d+", "vorlage_loeschen"),
                      ("POST", r"/api/lernmodell/anwenden", "lernmodell_anwenden")]
    m3.QUELLE.update({"vorlagen_anwenden": "vorlage", "lernmodell_anwenden": "lernmodell"})
    if mutant("vorlage_protokoll_fehlt"):
        m3.MANUELL[:] = [x for x in m3.MANUELL if x[2] != "vorlagen_anwenden"]

    # ---------------------------------------------------------- Lernmodell
    @app.get("/api/lernmodell")
    def lern_zustand():
        return Lernmodell(buch).zustand(config.lernmodell_automatisch)

    @app.post("/api/lernmodell/vorhersage")
    def lern_vorhersage(d: LernAnfrage):
        ids = [e.buchung_id for e in d.eintraege if isinstance(e, LernBuchung)]
        unbekannt = sorted({i for i in ids if i not in buch.buchungen})
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        m = Lernmodell(buch)
        aus = []
        for e in d.eintraege:
            if isinstance(e, LernBuchung):
                aus.append(m.vorhersage_m(buchung_merkmale(buch, buch.buchungen[e.buchung_id])))
            else:
                aus.append(m.vorhersage(e.empfaenger, e.verwendungszweck, e.betrag))
        return {"ergebnisse": aus}

    @app.post("/api/lernmodell/anwenden")
    def lern_anwenden(d: LernAnwenden):
        from .m2 import unkategorisiert
        _ids_pruefen(buch, d.buchung_ids, buch.buchungen, "buchung_ids")
        m = Lernmodell(buch)
        geprueft, aend = 0, []
        for b in sorted(buch.buchungen.values(), key=lambda b: b["id"]):
            if d.buchung_ids is not None and b["id"] not in d.buchung_ids:
                continue
            if len(buch.gegensplits(b)) != 1 or buch.kategorie_id(b) is not None or buch.gesperrt(b):
                continue
            geprueft += 1
            v = m.vorhersage_m(buchung_merkmale(buch, b))
            if v["kategorie_id"] is not None:
                aend.append((b, v))
        if not d.trocken:
            for b, v in aend:
                g = buch.gegensplits(b)[0]
                alt = b["splits"][g]["konto_id"]
                b["splits"][g]["konto_id"] = v["kategorie_id"]
                b["vorschlag"] = {"kategorie_id": v["kategorie_id"], "regel_id": None, "quelle": "lernmodell",
                                  "vorher_konto_id": alt, "sicherheit": v["sicherheit"]}
        return {"geprueft": geprueft, "anzahl": len(aend), "trocken": d.trocken,
                "aenderungen": [{"buchung_id": b["id"], "kategorie_id": v["kategorie_id"],
                                 "sicherheit": v["sicherheit"]} for b, v in aend]}

    # ------------------------------------------------------------ Vorlagen
    def _vorlage(vid):
        if vid not in buch.vorlagen:
            raise Fehler(404, "nicht_gefunden", "Vorlage nicht gefunden")
        return buch.vorlagen[vid]

    @app.get("/api/vorlagen")
    def vorlagen():
        return [vorlage_json(v) for v in _ordnung(buch)]

    @app.post("/api/vorlagen", status_code=201)
    def vorlage_anlegen(d: VorlageNeu):
        name, bed, tl = _pruefe(buch, d.name, d.bedingungen, d.teile)
        prio = d.prioritaet
        if prio is None:
            prio = max((v["prioritaet"] for v in buch.vorlagen.values()), default=90) + 10
        v = {"id": buch.neue_id("vorlage"), "name": name, "aktiv": d.aktiv, "prioritaet": prio, "bedingungen": bed,
             "teile": tl}
        buch.vorlagen[v["id"]] = v
        return vorlage_json(v)

    @app.get("/api/vorlagen/{vorlage_id}")
    def vorlage_lesen(vorlage_id: int):
        return vorlage_json(_vorlage(vorlage_id))

    @app.patch("/api/vorlagen/{vorlage_id}")
    def vorlage_aendern(vorlage_id: int, d: VorlageAenderung):
        v = _vorlage(vorlage_id)
        f = d.model_fields_set
        name, bed, tl = _pruefe(buch, d.name if "name" in f else None, d.bedingungen if "bedingungen" in f else None,
                                d.teile if "teile" in f else None)
        for feld, wert in (("name", name), ("bedingungen", bed), ("teile", tl)):
            if feld in f:
                if wert is None:
                    raise _v(["body", feld], "darf nicht null sein")
                v[feld] = wert
        for feld in ("aktiv", "prioritaet"):
            if feld in f:
                if getattr(d, feld) is None:
                    raise _v(["body", feld], "darf nicht null sein")
                v[feld] = getattr(d, feld)
        return vorlage_json(v)

    @app.delete("/api/vorlagen/{vorlage_id}", status_code=204)
    def vorlage_loeschen(vorlage_id: int):
        _vorlage(vorlage_id)
        del buch.vorlagen[vorlage_id]
        return Response(status_code=204)

    @app.post("/api/vorlagen/anwenden")
    def vorlagen_anwenden(d: VorlagenAnwenden):
        from .m2 import sicht
        _ids_pruefen(buch, d.buchung_ids, buch.buchungen, "buchung_ids")
        _ids_pruefen(buch, d.vorlage_ids, buch.vorlagen, "vorlage_ids")
        geprueft, aend, abw = 0, [], []
        for b in sorted(buch.buchungen.values(), key=lambda b: b["id"]):
            if d.buchung_ids is not None and b["id"] not in d.buchung_ids:
                continue
            bestand = [i for i, s in enumerate(b["splits"]) if KLASSE[buch.konten[s["konto_id"]]["art"]] == "bestand"]
            if len(buch.gegensplits(b)) != 1 or len(bestand) != 1 or buch.gesperrt(b):
                continue
            if d.nur_unkategorisiert and buch.kategorie_id(b) is not None:
                continue
            geprueft += 1
            e, zweck, r, konten = sicht(buch, b)
            art, v = erkenne(buch, e, zweck, konten, r, d.vorlage_ids)
            if art == "treffer":
                aend.append((b, v, bestand[0]))
            elif art == "abweichung":
                abw.append({"buchung_id": b["id"], "vorlage_id": v["id"], "betrag": r,
                            "gesamtbetrag": -sum(t["betrag"] for t in v["teile"])})
        if not d.trocken:
            for b, v, i in aend:
                b["splits"] = [b["splits"][i]] + teil_splits(buch, v)
                b["vorschlag"] = None
        return {"geprueft": geprueft, "anzahl": len(aend), "trocken": d.trocken,
                "aenderungen": [{"buchung_id": b["id"], "vorlage_id": v["id"]} for b, v, _ in aend],
                "abweichungen": abw}
