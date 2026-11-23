"""WEGWERF-REFERENZ M15: mehrfach/loeschen, mehrfach/verschieben, Herkunft, gelesene Zuordnungsmeldungen.

Kein Anwendungscode, kein Vorbild für die Implementierung. „Rückgängig bis“ steht in ``m3.py``, das Überspringen
unbekannter Bankkonten in ``m2.py``. Das Protokoll entsteht wie immer generisch in ``m3`` (Tabelle ``MANUELL``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from . import mutant
from .buch import KLASSE, Fehler


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Loeschen(M):
    buchung_ids: Annotated[list[StrictInt], Field(min_length=1)]


class Verschieben(M):
    von_konto_id: StrictInt
    nach_konto_id: StrictInt
    buchung_ids: Annotated[list[StrictInt], Field(min_length=1)] | None = None
    gruppe: Annotated[StrictStr, Field(min_length=1)] | None = None


def _v(meldung: str) -> Fehler:
    return Fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ["body"], "meldung": meldung}])


def gruppen_buchungen(buch, gruppe: str) -> set[int] | None:
    """IDs der von Änderungen der Gruppe angelegten Buchungen; None, wenn keine Buchung angelegt wurde."""
    ids = {e["objekt_id"] for a in buch.aenderungen.values() if a["gruppe"] == gruppe
           for e in a["eintraege"] if e["objekt"] == "buchung" and e["art"] == "angelegt"}
    return ids or None


def m15_einbinden(app: FastAPI, config, buch) -> None:
    @app.middleware("http")
    async def zuordnung_gelesen(request: Request, call_next):
        antwort = await call_next(request)
        pfad = request.url.path
        if antwort.status_code < 400 and ((request.method == "POST" and pfad == "/api/konten") or (
                request.method == "PATCH" and pfad.startswith("/api/konten/"))) \
                and not mutant("m15_zuordnung_ungelesen"):
            ibans = {k["iban"] for k in buch.konten.values() if k["iban"]}
            for x in buch.benachr.values():
                if x["schluessel"].startswith("konto_nicht_zugeordnet:") and x["schluessel"].split(":", 1)[1] in ibans:
                    x["gelesen"] = True
        return antwort

    @app.post("/api/buchungen/mehrfach/loeschen")
    def loeschen(d: Loeschen):
        ids = d.buchung_ids
        if len(set(ids)) != len(ids):
            raise _v("doppelte IDs")
        unbekannt = sorted(i for i in ids if i not in buch.buchungen)
        if unbekannt:
            raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
        gesperrt = sorted(i for i in ids if buch.gesperrt(buch.buchungen[i]))
        if mutant("m15_loeschen_nicht_atomar"):
            for i in ids:
                if i not in gesperrt:
                    buch.buchung_loeschen(i)
            if not gesperrt:
                return {"geloescht": sorted(ids), "anzahl": len(ids)}
        if gesperrt:
            raise Fehler(409, "buchung_gesperrt", "Gesperrte Buchungen", {"buchung_ids": gesperrt})
        for i in sorted(ids):
            buch.buchung_loeschen(i)
        return {"geloescht": sorted(ids), "anzahl": len(ids)}

    def _konto(kid: int, feld: str) -> None:
        if kid not in buch.konten:
            raise Fehler(422, "referenz_unbekannt", "Konto unbekannt", {"feld": feld})
        if KLASSE[buch.konten[kid]["art"]] != "bestand":
            raise Fehler(422, "konto_ungueltig", "Kein Bestandskonto", {"feld": feld})

    @app.post("/api/buchungen/mehrfach/verschieben")
    def verschieben(d: Verschieben):
        felder = d.model_fields_set
        if ("buchung_ids" in felder) == ("gruppe" in felder) or d.von_konto_id == d.nach_konto_id:
            raise _v("genau eines von buchung_ids, gruppe; Konten verschieden")
        if "buchung_ids" in felder and (d.buchung_ids is None or len(set(d.buchung_ids)) != len(d.buchung_ids)):
            raise _v("buchung_ids ungültig")
        if "gruppe" in felder and d.gruppe is None:
            raise _v("gruppe ungültig")
        von, nach = d.von_konto_id, d.nach_konto_id
        _konto(von, "von_konto_id")
        _konto(nach, "nach_konto_id")
        if d.buchung_ids is not None:
            unbekannt = sorted(i for i in d.buchung_ids if i not in buch.buchungen)
            if unbekannt:
                raise Fehler(422, "referenz_unbekannt", "Buchungen unbekannt", {"buchung_ids": unbekannt})
            wahl = sorted(d.buchung_ids)
        else:
            angelegt = gruppen_buchungen(buch, d.gruppe)
            if angelegt is None:
                raise Fehler(422, "referenz_unbekannt", "Gruppe ohne angelegte Buchungen")
            wahl = sorted(i for i in angelegt if i in buch.buchungen
                          and any(s["konto_id"] == von for s in buch.buchungen[i]["splits"]))

        def unmoeglich():
            return sorted(i for i in wahl if not any(s["konto_id"] == von for s in buch.buchungen[i]["splits"])
                          or any(s["konto_id"] == nach for s in buch.buchungen[i]["splits"]))

        def gesperrt():
            return sorted(i for i in wahl if buch.gesperrt(buch.buchungen[i]))
        pruefungen = [(unmoeglich, 422, "verschieben_unmoeglich"), (gesperrt, 409, "buchung_gesperrt")]
        if mutant("m15_verschieben_reihenfolge"):
            pruefungen.reverse()
        for f, status, code in pruefungen:
            ids = f()
            if ids:
                raise Fehler(status, code, "Verschieben nicht möglich", {"buchung_ids": ids})
        for i in wahl:
            for s in buch.buchungen[i]["splits"]:
                if s["konto_id"] == von:
                    s["konto_id"] = nach
                    if mutant("m15_verschieben_neue_split_id"):
                        s["id"] = buch.neue_id("split")
        return {"verschoben": wahl, "anzahl": len(wahl)}

    @app.get("/api/konten/{konto_id}/herkunft")
    def herkunft(konto_id: int):
        if konto_id not in buch.konten:
            raise Fehler(404, "nicht_gefunden", "Konto nicht gefunden")
        gruppen = sorted({a["gruppe"] for a in buch.aenderungen.values()
                          if a["gruppe"] and a["gruppe"].split(":")[0] in ("import", "sync")})
        aus = []
        for g in gruppen:
            ids = gruppen_buchungen(buch, g) or set()
            treffer = [i for i in ids if (i in buch.buchungen or mutant("m15_herkunft_geloeschte"))
                       and (i not in buch.buchungen
                            or any(s["konto_id"] == konto_id for s in buch.buchungen[i]["splits"]))]
            if not treffer:
                continue
            art, nr = g.split(":")
            if art == "import":
                vorgang = next((x for x in buch.importe if x["id"] == int(nr)), None)
                zeit = vorgang["importiert_am"] if vorgang else None
                text = f"Import {vorgang['dateiname'] if vorgang else nr}"
            else:
                lauf = buch.laeufe.get(int(nr))
                zeit = lauf["gestartet_am"] if lauf else None
                text = f"Synchronisation #{nr}"
            aus.append({"gruppe": g, "art": art, "beschreibung": text, "zeitpunkt": zeit, "anzahl": len(treffer)})
        aus.sort(key=lambda x: (x["zeitpunkt"] is not None, x["zeitpunkt"] or ""), reverse=True)
        return aus
