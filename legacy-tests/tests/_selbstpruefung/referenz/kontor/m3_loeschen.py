"""M3 der Wegwerf-Referenz: Konten mit Buchungen löschen (spec/api/loeschen.md). KEIN Anwendungscode.

Das Änderungsprotokoll entsteht über die Middleware in ``m3.py``; hier wird nur
die ID der entstehenden Änderung vorausberechnet. Mutanten über ``kontor.mutant(name)``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, StrictBool

from . import mutant
from .buch import Fehler, namen_pruefen
from .m2 import UNK, unkategorisiert


class KontoLoeschen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buchungen: Literal["loeschen", "elternkonto", "unkategorisiert"]
    konflikte: Literal["loeschen", "behalten"]
    gesperrte_einbeziehen: StrictBool = False
    trocken: StrictBool = False


def _memo(memos: list[str]) -> str:
    aus: list[str] = []
    for m in memos:
        if m and m not in aus:
            aus.append(m)
    return " / ".join(aus)


def ausfuehren(buch, k: int, d: KontoLoeschen) -> dict:
    kk = buch._konto(k)
    from .m5 import kreditbezug
    kreditbezug(buch, k)
    if d.buchungen == "elternkonto" and kk["eltern_id"] is None:
        raise Fehler(422, "kein_elternkonto", "Wurzelkonto hat kein Elternkonto")
    if d.buchungen == "unkategorisiert" and kk["extern_id"] == UNK:
        raise Fehler(422, "ziel_ungueltig", "„Unkategorisiert“ kann nicht nach „Unkategorisiert“ gelöscht werden")
    betroffen = sorted(b["id"] for b in buch.buchungen.values() if any(s["konto_id"] == k for s in b["splits"]))
    gesperrt = sorted(i for i in betroffen if buch.gesperrt(buch.buchungen[i]))
    if gesperrt and not d.trocken and not d.gesperrte_einbeziehen and not mutant("loeschen_sperre_ignoriert"):
        raise Fehler(409, "buchung_gesperrt", "Gesperrte Buchungen betroffen", {"buchung_ids": gesperrt})

    arbeit = buch.kopie()
    if d.buchungen == "elternkonto":
        z = kk["eltern_id"]
    elif d.buchungen == "unkategorisiert":
        z = unkategorisiert(arbeit)
    else:
        z = None

    abst_weg = [] if mutant("loeschen_abstimmung_bleibt") else sorted(
        a["id"] for a in arbeit.abstimmungen.values() if a["konto_id"] == k)
    for b in arbeit.buchungen.values():
        for s in b["splits"]:
            if s.get("abstimmung_id") in abst_weg:
                s["abstimmung_id"] = None
    for a in abst_weg:
        del arbeit.abstimmungen[a]

    unterkonten = sorted(x["id"] for x in arbeit.konten.values() if x["eltern_id"] == k)
    for u in unterkonten:
        arbeit.konten[u]["eltern_id"] = None if mutant("loeschen_unterkonten_wurzel") else kk["eltern_id"]

    geloescht: list[int] = []
    konflikt: list[int] = []
    for bid in betroffen:
        b = arbeit.buchungen[bid]
        if d.buchungen == "loeschen":
            geloescht.append(bid)
            continue
        for s in b["splits"]:
            if s["konto_id"] == k:
                s["konto_id"] = z
        b["vorschlag"] = None if not mutant("loeschen_vorschlag_bleibt") else b["vorschlag"]
        if all(s["konto_id"] == z for s in b["splits"]) and not mutant("loeschen_ohne_konflikt"):
            konflikt.append(bid)
            if d.konflikte == "loeschen":
                geloescht.append(bid)
            continue
        if mutant("loeschen_ohne_zusammenfassen"):
            continue
        gruppe = [i for i, s in enumerate(b["splits"]) if s["konto_id"] == z and s.get("abstimmung_id") is None]
        if len(gruppe) >= 2:
            erst = b["splits"][gruppe[0]]
            erst["betrag"] = sum(b["splits"][i]["betrag"] for i in gruppe)
            erst["memo"] = _memo([b["splits"][i]["memo"] for i in gruppe])
            b["splits"] = [s for i, s in enumerate(b["splits"]) if i not in gruppe[1:]]
    for bid in geloescht:
        del arbeit.buchungen[bid]
        for vid in [v["id"] for v in arbeit.verdachte.values() if v["status"] == "offen"
                    and (v["buchung_id"] == bid or bid in v["kandidat_ids"])]:
            del arbeit.verdachte[vid]

    geaendert_r: list[int] = []
    geloescht_r: list[int] = []
    for r in list(arbeit.regeln.values()):
        bezug = r["kategorie_id"] == k or any(c["feld"] == "konto_id" and c["wert"] == k for c in r["bedingungen"])
        if not bezug:
            continue
        if d.buchungen == "elternkonto":
            if r["kategorie_id"] == k:
                r["kategorie_id"] = z
            for c in r["bedingungen"]:
                if c["feld"] == "konto_id" and c["wert"] == k:
                    c["wert"] = z
            geaendert_r.append(r["id"])
        else:
            del arbeit.regeln[r["id"]]
            geloescht_r.append(r["id"])
            for b in arbeit.buchungen.values():
                if b.get("vorschlag") and b["vorschlag"]["regel_id"] == r["id"]:
                    b["vorschlag"]["regel_id"] = None
    geaendert_v: list[int] = []
    geloescht_v: list[int] = []
    for v in list(arbeit.vorlagen.values()):
        bezug = any(t["kategorie_id"] == k for t in v["teile"]) or any(
            c["feld"] == "konto_id" and c["wert"] == k for c in v["bedingungen"])
        if not bezug:
            continue
        if d.buchungen == "elternkonto":
            for t in v["teile"]:
                if t["kategorie_id"] == k:
                    t["kategorie_id"] = z
            for c in v["bedingungen"]:
                if c["feld"] == "konto_id" and c["wert"] == k:
                    c["wert"] = z
            geaendert_v.append(v["id"])
        else:
            del arbeit.vorlagen[v["id"]]
            geloescht_v.append(v["id"])
    geaendert_e: list[int] = []
    for e in arbeit.empfaenger.values():
        if e.get("standardkategorie_id") == k and not mutant("loeschen_standardkategorie_bleibt"):
            e["standardkategorie_id"] = z if d.buchungen == "elternkonto" else None
            geaendert_e.append(e["id"])
    del arbeit.konten[k]
    namen_pruefen(arbeit.konten)   # M32: hochrutschende Unterkonten (sammel3.md 1.2), auch im Probelauf

    aenderung_id = None
    if not d.trocken or mutant("loeschen_trocken_schreibt"):
        buch.uebernehme(arbeit)
        if not d.trocken:  # die Middleware protokolliert danach genau eine Änderung
            aenderung_id = buch.zaehler.get("aenderung", 0) + 1
    elif d.buchungen == "unkategorisiert" and all(x["extern_id"] != UNK for x in buch.konten.values()):
        z = None
    return {
        "konto_id": k, "trocken": d.trocken, "buchungen": d.buchungen, "konflikte": d.konflikte,
        "ziel_konto_id": z, "buchungen_betroffen": betroffen, "buchungen_geloescht": sorted(geloescht),
        "buchungen_umgebucht": sorted(set(betroffen) - set(geloescht)), "konfliktbuchungen": konflikt,
        "gesperrt": gesperrt, "unterkonten": unterkonten, "regeln_geaendert": sorted(geaendert_r),
        "regeln_geloescht": sorted(geloescht_r), "empfaenger_geaendert": sorted(geaendert_e),
        "abstimmungen_geloescht": abst_weg, "aenderung_id": aenderung_id,

    }


def m3_loeschen_einbinden(app: FastAPI, buch) -> None:
    @app.post("/api/konten/{konto_id}/loeschen")
    def konto_loeschen_mit_buchungen(konto_id: int, d: KontoLoeschen):
        return ausfuehren(buch, konto_id, d)
