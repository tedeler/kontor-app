"""REST-Schicht der Wegwerf-Referenz (nur die von ``kern``-Tests genutzten Endpunkte). KEIN Anwendungscode."""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Literal

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, \
    model_validator
from starlette.exceptions import HTTPException

from . import __version__, mutant
from .buch import MAX, Fehler, buch_fuer
from .config import KontorConfig
from .importer.kmymoney import importiere_bytes
from .importer.gnucash import importiere_gnc_bytes
from .m2 import m2_einbinden, planer_lebenszyklus
from .m3_loeschen import m3_loeschen_einbinden
from . import m3
from .m4 import m4_einbinden


def _datum(s: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", s):
        raise ValueError("Datum im Format YYYY-MM-DD erwartet")
    dt.date.fromisoformat(s)
    return s


def _eindeutig(v: list[int]) -> list[int]:
    if len(set(v)) != len(v):
        raise ValueError("IDs doppelt")
    return v


Datum = Annotated[StrictStr, AfterValidator(_datum)]
Betrag = Annotated[float, Field(ge=-MAX, le=MAX)] if mutant("betrag_float") else Annotated[
    StrictInt, Field(ge=-MAX, le=MAX)]
Kontoart = Literal["girokonto", "sparkonto", "kreditkonto", "aufwand", "ertrag", "eigenkapital"]
Status = Literal["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"]
IdListe = Annotated[list[StrictInt], Field(min_length=1), AfterValidator(_eindeutig)]


class M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KontoNeu(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    art: Kontoart
    eltern_id: StrictInt | None = None
    iban: StrictStr | None = None
    geschlossen: StrictBool = False
    eroeffnet_am: Datum | None = None
    notiz: Annotated[StrictStr, Field(max_length=10000)] = ""


class KontoAenderung(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] = None
    eltern_id: StrictInt | None = None
    iban: StrictStr | None = None
    geschlossen: StrictBool = None
    eroeffnet_am: Datum | None = None
    notiz: Annotated[StrictStr, Field(max_length=10000)] = None


class SplitNeu(M):
    konto_id: StrictInt
    betrag: Betrag
    memo: Annotated[StrictStr, Field(max_length=10000)] = ""


class BuchungNeu(M):
    datum: Datum
    empfaenger_id: StrictInt | None = None
    verwendungszweck: Annotated[StrictStr, Field(max_length=10000)] = ""
    status: Literal["importiert", "vorlaeufig", "bestaetigt"] = "bestaetigt"
    splits: list[SplitNeu]
    tag_ids: list[StrictInt] = []


class BuchungAenderung(M):
    datum: Datum = None
    empfaenger_id: StrictInt | None = None
    verwendungszweck: Annotated[StrictStr, Field(max_length=10000)] = None
    status: Status = None
    tag_ids: list[StrictInt] = None


class SplitsErsetzen(M):
    splits: list[SplitNeu]


class KategorieSetzen(M):
    kategorie_id: StrictInt


class MehrfachKategorie(M):
    buchung_ids: IdListe
    kategorie_id: StrictInt


class MehrfachTags(M):
    buchung_ids: IdListe
    hinzufuegen: list[StrictInt] = []
    entfernen: list[StrictInt] = []


class MehrfachAenderung(M):
    """M12, datenmodell.md 17.2."""
    buchung_ids: IdListe
    status: Status = None
    datum: Datum = None
    empfaenger_id: StrictInt | None = None
    verwendungszweck: Annotated[StrictStr, Field(max_length=10000)] = None
    entsperren: StrictBool = False

    @model_validator(mode="after")
    def _mindestens_ein_feld(self):
        if not self.model_fields_set & {"status", "datum", "empfaenger_id", "verwendungszweck"}:
            raise ValueError("mindestens ein Feld")
        for f in ("status", "datum", "verwendungszweck"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} darf nicht null sein")
        return self


class TagEingabe(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=100)]


class EmpfaengerNeu(M):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]


class DubletteAufloesen(M):
    entscheidung: Literal["zusammenfuehren", "keine_dublette"]
    behalten_id: StrictInt | None = None


def _fehler(status: int, code: str, meldung: str, details=None) -> JSONResponse:
    return JSONResponse({"fehler": {"code": code, "meldung": meldung or code, "details": details}}, status)


def _validierung(ort: list, meldung: str) -> JSONResponse:
    return _fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ort, "meldung": meldung}])


def _felder(m: BaseModel) -> dict:
    return {f: getattr(m, f) for f in m.model_fields_set}


def create_app(config: KontorConfig | None = None) -> FastAPI:
    if config is None:
        raise NotImplementedError("Die Referenz braucht eine Konfiguration")
    buch = buch_fuer(config.aktive_datenbank)
    modus = "mock" if config.mock_modus else "echt"
    app = FastAPI(lifespan=planer_lebenszyklus)

    @app.middleware("http")
    async def kopf(request: Request, call_next):
        antwort = await call_next(request)
        if request.url.path.startswith("/api"):
            antwort.headers["X-Kontor-Modus"] = modus
        return antwort

    @app.exception_handler(RequestValidationError)
    async def _v(request, exc):
        return _fehler(422, "validierung", "Ungültige Anfrage",
                       [{"ort": [str(x) if not isinstance(x, int) else x for x in e["loc"]], "meldung": e["msg"]}
                        for e in exc.errors()])

    @app.exception_handler(HTTPException)
    async def _h(request, exc):
        if exc.status_code == 405:
            return _fehler(405, "methode_nicht_erlaubt", "Methode nicht erlaubt")
        if exc.status_code == 404:
            return _fehler(404, "nicht_gefunden", "Nicht gefunden")
        return _fehler(exc.status_code, "interner_fehler", str(exc.detail))

    @app.exception_handler(Fehler)
    async def _f(request, exc: Fehler):
        return _fehler(exc.status, exc.code, exc.meldung, exc.details)

    @app.get("/", response_class=HTMLResponse)
    def oberflaeche():
        from .m8 import huelle
        return huelle(config)

    @app.get("/api/status")
    def status():
        return {"version": __version__, "modus": modus, "mock": config.mock_modus,
                "hinweis": "Mock-Modus aktiv" if config.mock_modus else None,
                "mock_szenario": config.mock_szenario if config.mock_modus else None,
                "plugins": {"bank": {"name": config.bank_plugin, "mock": config.mock_modus},
                            "mail": {"name": config.mail_plugin, "mock": config.mock_modus}}}

    # ------------------------------------------------------------ Konten
    @app.get("/api/konten")
    def konten(art: list[Kontoart] | None = Query(None), geschlossen: bool | None = None):
        return [buch.konto_json(k) for k in sorted(buch.konten.values(), key=lambda k: k["id"])
                if (not art or k["art"] in art) and (geschlossen is None or k["geschlossen"] == geschlossen)]

    @app.post("/api/konten", status_code=201)
    def konto_anlegen(d: KontoNeu):
        return buch.konto_json(buch.konto_anlegen(d.model_dump()))

    @app.get("/api/konten/{konto_id}")
    def konto_lesen(konto_id: int):
        return buch.konto_json(buch._konto(konto_id))

    @app.patch("/api/konten/{konto_id}")
    def konto_aendern(konto_id: int, d: KontoAenderung):
        return buch.konto_json(buch.konto_aendern(konto_id, _felder(d)))

    @app.delete("/api/konten/{konto_id}", status_code=204)
    def konto_loeschen(konto_id: int):
        buch.konto_loeschen(konto_id)
        return Response(status_code=204)

    @app.get("/api/kategorien")
    def kategorien():
        return [buch.konto_json(k) for k in sorted(buch.konten.values(), key=lambda k: k["id"])
                if k["art"] in ("aufwand", "ertrag")]

    @app.get("/api/kontenuebersicht")
    def uebersicht(stichtag: dt.date | None = None):
        return buch.uebersicht(stichtag.isoformat() if stichtag else None)

    # --------------------------------------------------------- Buchungen
    @app.get("/api/buchungen")
    def liste(konto_id: int | None = None, unterkonten: bool = False, von: dt.date | None = None, bis: dt.date | None = None,
              betrag_min: int | None = None, betrag_max: int | None = None, kategorie_id: int | None = None,
              unterkategorien: bool = False, tag_id: list[int] = Query([]), empfaenger_id: int | None = None,
              ohne_empfaenger: bool = False, verwendungszweck: str | None = Query(None, min_length=1),
              suche: str | None = Query(None, min_length=1), status: list[Status] = Query([]),
              sortierung: Literal["datum", "-datum", "betrag", "-betrag", "empfaenger", "-empfaenger"] = "datum",
              seite: int = Query(1, ge=1), pro_seite: int = Query(50, ge=1, le=500), vorschlag: bool | None = None,
              abgestimmt: bool | None = None):
        if von and bis and von > bis:
            return _validierung(["query", "von"], "von > bis")
        if betrag_min is not None and betrag_max is not None and betrag_min > betrag_max:
            return _validierung(["query", "betrag_min"], "betrag_min > betrag_max")
        return buch.liste({"konto_id": konto_id, "unterkonten": unterkonten, "von": von.isoformat() if von else None,
                           "bis": bis.isoformat() if bis else None, "betrag_min": betrag_min,
                           "betrag_max": betrag_max, "kategorie_id": kategorie_id, "unterkategorien": unterkategorien,
                           "tag_id": tag_id, "empfaenger_id": empfaenger_id, "ohne_empfaenger": ohne_empfaenger,
                           "verwendungszweck": verwendungszweck, "suche": suche, "status": status,
                           "sortierung": sortierung, "seite": seite, "pro_seite": pro_seite,
                           "vorschlag": vorschlag, "abgestimmt": abgestimmt})

    @app.post("/api/buchungen", status_code=201)
    def buchung_anlegen(d: BuchungNeu):
        return buch.buchung_json(buch.buchung_anlegen(d.model_dump()))

    m2_einbinden(app, config, buch)
    m3_loeschen_einbinden(app, buch)
    m3.m3_einbinden(app, config, buch)
    m4_einbinden(app, config, buch)
    from .sicherung import sicherung_einbinden
    sicherung_einbinden(app, config, buch)
    from .m5 import m5_einbinden
    m5_einbinden(app, config, buch)
    from .m6 import m6_einbinden
    m6_einbinden(app, config, buch)

    @app.post("/api/buchungen/mehrfach/kategorie")
    def mehrfach_kategorie(d: MehrfachKategorie):
        return buch.mehrfach_kategorie(d.buchung_ids, d.kategorie_id)

    @app.post("/api/buchungen/mehrfach/tags")
    def mehrfach_tags(d: MehrfachTags):
        return buch.mehrfach_tags(d.buchung_ids, d.hinzufuegen, d.entfernen)

    @app.post("/api/buchungen/mehrfach/aendern")
    def mehrfach_aendern(d: MehrfachAenderung):
        felder = {f: getattr(d, f) for f in d.model_fields_set if f not in ("buchung_ids", "entsperren")}
        return buch.mehrfach_aendern(d.buchung_ids, felder, d.entsperren)

    @app.get("/api/buchungen/{buchung_id}")
    def buchung_lesen(buchung_id: int):
        return buch.buchung_json(buch._buchung(buchung_id))

    @app.patch("/api/buchungen/{buchung_id}")
    def buchung_aendern(buchung_id: int, d: BuchungAenderung):
        return buch.buchung_json(buch.buchung_aendern(buchung_id, _felder(d)))

    @app.delete("/api/buchungen/{buchung_id}", status_code=204)
    def buchung_loeschen(buchung_id: int):
        buch.buchung_loeschen(buchung_id)
        return Response(status_code=204)

    @app.put("/api/buchungen/{buchung_id}/splits")
    def splits_ersetzen(buchung_id: int, d: SplitsErsetzen):
        return buch.buchung_json(buch.splits_ersetzen(buchung_id, [s.model_dump() for s in d.splits]))

    @app.put("/api/buchungen/{buchung_id}/kategorie")
    def kategorie_setzen(buchung_id: int, d: KategorieSetzen):
        return buch.buchung_json(buch.kategorie_setzen(buchung_id, d.kategorie_id))

    # ------------------------------------------------- Tags, Empfänger
    @app.get("/api/tags")
    def tags():
        return [buch.tag_json(t) for t in sorted(buch.tags.values(), key=lambda t: t["id"])]

    @app.post("/api/tags", status_code=201)
    def tag_anlegen(d: TagEingabe):
        return buch.tag_json(buch.tag_anlegen(d.name))

    @app.patch("/api/tags/{tag_id}")
    def tag_umbenennen(tag_id: int, d: TagEingabe):
        return buch.tag_json(buch.tag_umbenennen(tag_id, d.name))

    @app.delete("/api/tags/{tag_id}", status_code=204)
    def tag_loeschen(tag_id: int):
        buch.tag_loeschen(tag_id)
        return Response(status_code=204)

    @app.get("/api/empfaenger")
    def empfaenger():
        return sorted(buch.empfaenger.values(), key=lambda e: e["id"])

    @app.post("/api/empfaenger", status_code=201)
    def empfaenger_anlegen(d: m3.EmpfaengerNeu):
        return m3.empfaenger_anlegen(buch, d)

    @app.get("/api/empfaenger/{empfaenger_id}")
    def empfaenger_lesen(empfaenger_id: int):
        if empfaenger_id not in buch.empfaenger:
            raise Fehler(404, "nicht_gefunden", "Empfänger nicht gefunden")
        return buch.empfaenger[empfaenger_id]

    # ------------------------------------------------ Import, Dubletten
    @app.post("/api/import/kmymoney")
    async def importieren(datei: UploadFile = File(...)):
        e = importiere_bytes(buch, await datei.read(), datei.filename,
                             jetzt=app.state.dienst.jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")).als_dict()
        if not e["erfolgreich"]:
            return _fehler(422, e["fehler"][0]["code"], e["fehler"][0]["meldung"], e)
        return e

    @app.post("/api/import/gnucash")
    async def importieren_gnucash(datei: UploadFile = File(...)):
        e = importiere_gnc_bytes(buch, await datei.read(), datei.filename,
                                 jetzt=app.state.dienst.jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")).als_dict()
        if not e["erfolgreich"]:
            return _fehler(422, e["fehler"][0]["code"], e["fehler"][0]["meldung"], e)
        return e

    @app.get("/api/importe")
    def importe():
        return buch.importe

    @app.get("/api/dubletten")
    def dubletten(status: Literal["offen", "zusammengefuehrt", "keine_dublette"] | None = None):
        return [v for v in sorted(buch.verdachte.values(), key=lambda v: v["id"])
                if status is None or v["status"] == status]

    @app.post("/api/dubletten/{verdacht_id}/aufloesen")
    def aufloesen(verdacht_id: int, d: DubletteAufloesen):
        return buch.verdacht_aufloesen(verdacht_id, d.entscheidung, d.behalten_id)

    from .m8 import m8_einbinden
    m8_einbinden(app, config)
    from .m13 import m13_einbinden
    m13_einbinden(app, config, modus)
    from .m15 import m15_einbinden
    m15_einbinden(app, config, buch)
    from .m16 import m16_einbinden
    m16_einbinden(app, buch)
    from .m25 import m25_einbinden
    m25_einbinden(app, buch)

    from .m7 import m7_einbinden, sicherheit_einbinden
    sicherheit_einbinden(app, config, m7_einbinden(app, config, modus), modus)
    return app
