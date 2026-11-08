"""App-Fabrik und REST-Endpunkte (python-api.md 4, openapi.yaml).

Jede Anfrage öffnet eine eigene SQLite-Verbindung auf
``config.aktive_datenbank``; schreibende Operationen laufen in einer
Transaktion. Mehrere Apps im selben Prozess teilen keinen Zustand.
"""

from __future__ import annotations

import functools
import logging
import pathlib
from collections.abc import Callable
from typing import Any

import fastapi
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from . import __version__, buch, db
from .config import KontorConfig
from .importer.kmymoney import importiere_bytes
from .validierung import (BETRAG_MAX, STATUS, ApiFehler, Feld, Query, Validierungsfehler, fehler_eintrag,
                          pruefe_koerper)
from .validierung import KONTOARTEN

log = logging.getLogger("kontor")

WEB = pathlib.Path(__file__).parent / "web"
MOCK_HINWEIS = "Mock-Modus: Es werden ausschließlich synthetische Testdaten verwendet (eigene Mock-Datenbank)."


def fehler_antwort(status: int, code: str, meldung: str, details: Any = None) -> JSONResponse:
    return JSONResponse({"fehler": {"code": code, "meldung": meldung, "details": details}}, status_code=status)


class ModusHeader:
    """Reine ASGI-Middleware: setzt ``X-Kontor-Modus`` an jeder Antwort unter /api/."""

    def __init__(self, app, modus: str) -> None:
        self.app = app
        self.modus = modus.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (scope["path"] == "/api" or scope["path"].startswith("/api/")):
            return await self.app(scope, receive, send)

        async def senden(nachricht):
            if nachricht["type"] == "http.response.start":
                kopf = [(k, v) for k, v in nachricht.get("headers", []) if k.lower() != b"x-kontor-modus"]
                kopf.append((b"x-kontor-modus", self.modus))
                nachricht = {**nachricht, "headers": kopf}
            await send(nachricht)

        try:
            await self.app(scope, receive, senden)
        except Exception:  # pragma: no cover - letzte Absicherung
            log.exception("Unbehandelter Fehler")
            antwort = fehler_antwort(500, "interner_fehler", "Interner Fehler.")
            antwort.headers["x-kontor-modus"] = self.modus.decode()
            await antwort(scope, receive, send)


# ---------------------------------------------------------------- Schemas

S = Feld
KONTO_NEU = {
    "name": S("str", pflicht=True, strip=True, min_len=1, max_len=200),
    "art": S("enum", pflicht=True, werte=KONTOARTEN),
    "eltern_id": S("int", nullbar=True),
    "iban": S("str", nullbar=True),
    "geschlossen": S("bool"),
    "eroeffnet_am": S("datum", nullbar=True),
    "notiz": S("str", max_len=10000),
}
KONTO_AENDERUNG = {k: v for k, v in KONTO_NEU.items() if k != "art"}
KONTO_AENDERUNG["name"] = S("str", strip=True, min_len=1, max_len=200)
SPLIT_NEU = {
    "konto_id": S("int", pflicht=True),
    "betrag": S("betrag", pflicht=True),
    "memo": S("str", max_len=10000),
}
BUCHUNG_NEU = {
    "datum": S("datum", pflicht=True),
    "empfaenger_id": S("int", nullbar=True),
    "verwendungszweck": S("str", max_len=10000),
    "status": S("enum", werte=("importiert", "vorlaeufig", "bestaetigt")),
    "splits": S("objekte", pflicht=True, unter=SPLIT_NEU),
    "tag_ids": S("int_liste"),
}
BUCHUNG_AENDERUNG = {
    "datum": S("datum"),
    "empfaenger_id": S("int", nullbar=True),
    "verwendungszweck": S("str", max_len=10000),
    "status": S("enum", werte=STATUS),
    "tag_ids": S("int_liste"),
}
SPLITS_ERSETZEN = {"splits": S("objekte", pflicht=True, unter=SPLIT_NEU)}
KATEGORIE = {"kategorie_id": S("int", pflicht=True)}
MEHRFACH_KATEGORIE = {
    "buchung_ids": S("int_liste", pflicht=True, min_items=1, eindeutig=True),
    "kategorie_id": S("int", pflicht=True),
}
MEHRFACH_TAGS = {
    "buchung_ids": S("int_liste", pflicht=True, min_items=1, eindeutig=True),
    "hinzufuegen": S("int_liste"),
    "entfernen": S("int_liste"),
}
TAG_EINGABE = {"name": S("str", pflicht=True, strip=True, min_len=1, max_len=100)}
EMPFAENGER_NEU = {"name": S("str", pflicht=True, strip=True, min_len=1, max_len=200)}
DUBLETTE_AUFLOESEN = {
    "entscheidung": S("enum", pflicht=True, werte=("zusammenfuehren", "keine_dublette")),
    "behalten_id": S("int"),
}


# ------------------------------------------------------------- App-Fabrik


def _index_html(config: KontorConfig) -> str:
    vorlage = (WEB / "index.html").read_text(encoding="utf-8")
    if config.mock_modus:
        hinweis = ('<div id="mock-hinweis" class="mock-hinweis" role="status">'
                   '<strong>Mock-Modus</strong> – nur synthetische Testdaten, eigene Mock-Datenbank'
                   f' (Szenario: {config.mock_szenario}). Keine Verbindung zu Bank oder Mailserver.</div>')
        klasse = "mock"
    else:
        hinweis, klasse = "", "echt"
    return (vorlage.replace("<!--MODUS-HINWEIS-->", hinweis).replace("{{MODUS}}", klasse)
            .replace("{{VERSION}}", __version__))


def create_app(config: KontorConfig | None = None) -> fastapi.FastAPI:
    if config is None:
        config = KontorConfig.from_env()
    pfad = config.aktive_datenbank
    db.schema_anlegen(pfad)  # vor der Rückkehr: Datei und Schema existieren
    modus = "mock" if config.mock_modus else "echt"

    app = fastapi.FastAPI(title="Kontor", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.add_middleware(ModusHeader, modus=modus)

    @app.exception_handler(StarletteHTTPException)
    async def http_fehler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return fehler_antwort(404, "nicht_gefunden", "Der angeforderte Pfad existiert nicht.")
        if exc.status_code == 405:
            return fehler_antwort(405, "methode_nicht_erlaubt", "Diese Methode ist für den Pfad nicht erlaubt.")
        return fehler_antwort(exc.status_code, "validierung" if exc.status_code < 500 else "interner_fehler",
                              str(exc.detail) or "Fehler.")

    @app.exception_handler(RequestValidationError)
    async def validierungs_fehler(request: Request, exc: RequestValidationError):
        details = [fehler_eintrag(list(e.get("loc", [])), str(e.get("msg", ""))) for e in exc.errors()]
        return fehler_antwort(422, "validierung", "Die Anfrage ist ungültig.", details or None)

    def mit_db(funktion: Callable, schreibend: bool = False):
        def ausfuehren(*args):
            con = db.verbinde(pfad)
            try:
                if schreibend:
                    with db.transaktion(con):
                        return funktion(con, *args)
                return funktion(con, *args)
            finally:
                con.close()
        return ausfuehren

    def endpunkt(methode: str, pfad_vorlage: str, status: int = 200):
        def deko(f):
            @functools.wraps(f)
            async def wrapper(request: Request):
                try:
                    ergebnis = await f(request)
                except ApiFehler as e:
                    return fehler_antwort(e.status, e.code, e.meldung, e.details)
                except Exception:
                    log.exception("Interner Fehler bei %s %s", request.method, request.url.path)
                    return fehler_antwort(500, "interner_fehler", "Interner Fehler.")
                if isinstance(ergebnis, Response):
                    return ergebnis
                if status == 204:
                    return Response(status_code=204)
                return JSONResponse(ergebnis, status_code=status)
            app.add_api_route(pfad_vorlage, wrapper, methods=[methode], include_in_schema=False)
            return wrapper
        return deko

    async def lesen(f: Callable, *args):
        return await run_in_threadpool(mit_db(f), *args)

    async def schreiben(f: Callable, *args):
        return await run_in_threadpool(mit_db(f, schreibend=True), *args)

    async def koerper(request: Request, schema: dict) -> dict:
        return pruefe_koerper(await request.body(), schema)

    def pid(request: Request, name: str) -> int:
        return request.path_params[name]

    # ------------------------------------------------------------ Status
    @endpunkt("GET", "/api/status")
    async def status(request: Request):
        return {
            "version": __version__,
            "modus": modus,
            "mock": config.mock_modus,
            "hinweis": MOCK_HINWEIS if config.mock_modus else None,
            "mock_szenario": config.mock_szenario if config.mock_modus else None,
            "plugins": {"bank": {"name": config.bank_plugin, "mock": config.bank_plugin == "mock"},
                        "mail": {"name": config.mail_plugin, "mock": config.mail_plugin == "mock"}},
        }

    # ------------------------------------------------------------ Konten
    @endpunkt("GET", "/api/konten")
    async def konten_liste(request: Request):
        q = Query(request.query_params)
        arten = q.auswahlen("art", KONTOARTEN)
        geschlossen = q.wahrheitswert("geschlossen")
        q.pruefen()
        return await lesen(buch.konten_liste, arten, geschlossen)

    @endpunkt("POST", "/api/konten", 201)
    async def konto_anlegen(request: Request):
        d = await koerper(request, KONTO_NEU)
        return await schreiben(buch.konto_anlegen, d)

    @endpunkt("GET", "/api/konten/{konto_id:int}")
    async def konto_lesen(request: Request):
        return await lesen(buch.konto_lesen, pid(request, "konto_id"))

    @endpunkt("PATCH", "/api/konten/{konto_id:int}")
    async def konto_aendern(request: Request):
        d = await koerper(request, KONTO_AENDERUNG)
        return await schreiben(buch.konto_aendern, pid(request, "konto_id"), d)

    @endpunkt("DELETE", "/api/konten/{konto_id:int}", 204)
    async def konto_loeschen(request: Request):
        return await schreiben(buch.konto_loeschen, pid(request, "konto_id"))

    @endpunkt("GET", "/api/kategorien")
    async def kategorien(request: Request):
        return await lesen(buch.konten_liste, ["aufwand", "ertrag"], None)

    @endpunkt("GET", "/api/kontenuebersicht")
    async def kontenuebersicht(request: Request):
        q = Query(request.query_params)
        stichtag = q.datum("stichtag")
        q.pruefen()
        return await lesen(buch.kontenuebersicht, stichtag)

    # --------------------------------------------------------- Buchungen
    @endpunkt("GET", "/api/buchungen")
    async def buchungen_liste(request: Request):
        q = Query(request.query_params)
        f: dict[str, Any] = {
            "konto_id": q.ganzzahl("konto_id"),
            "von": q.datum("von"),
            "bis": q.datum("bis"),
            "betrag_min": q.ganzzahl("betrag_min"),
            "betrag_max": q.ganzzahl("betrag_max"),
            "kategorie_id": q.ganzzahl("kategorie_id"),
            "unterkategorien": q.wahrheitswert("unterkategorien") or False,
            "tag_id": q.ganzzahlen("tag_id"),
            "empfaenger_id": q.ganzzahl("empfaenger_id"),
            "ohne_empfaenger": q.wahrheitswert("ohne_empfaenger") or False,
            "verwendungszweck": q.text("verwendungszweck", 1),
            "suche": q.text("suche", 1),
            "status": q.auswahlen("status", STATUS),
            "sortierung": q.auswahl("sortierung", buch.SORTIERUNGEN) or "datum",
            "seite": q.ganzzahl("seite", minimum=1),
            "pro_seite": q.ganzzahl("pro_seite", minimum=1, maximum=500),
        }
        if f["von"] and f["bis"] and f["von"] > f["bis"]:
            q.fehler_melden("von", "von darf nicht nach bis liegen.")
        if f["betrag_min"] is not None and f["betrag_max"] is not None and f["betrag_min"] > f["betrag_max"]:
            q.fehler_melden("betrag_min", "betrag_min darf nicht größer als betrag_max sein.")
        q.pruefen()
        f["seite"] = f["seite"] or 1
        f["pro_seite"] = f["pro_seite"] or 50
        return await lesen(buch.buchungsliste, f)

    @endpunkt("POST", "/api/buchungen", 201)
    async def buchung_anlegen(request: Request):
        d = await koerper(request, BUCHUNG_NEU)
        return await schreiben(buch.buchung_anlegen, d)

    @endpunkt("POST", "/api/buchungen/mehrfach/kategorie")
    async def mehrfach_kategorie(request: Request):
        d = await koerper(request, MEHRFACH_KATEGORIE)
        return await schreiben(buch.mehrfach_kategorie, d["buchung_ids"], d["kategorie_id"])

    @endpunkt("POST", "/api/buchungen/mehrfach/tags")
    async def mehrfach_tags(request: Request):
        d = await koerper(request, MEHRFACH_TAGS)
        return await schreiben(buch.mehrfach_tags, d["buchung_ids"], d.get("hinzufuegen") or [],
                               d.get("entfernen") or [])

    @endpunkt("GET", "/api/buchungen/{buchung_id:int}")
    async def buchung_lesen(request: Request):
        return await lesen(buch.buchung_lesen, pid(request, "buchung_id"))

    @endpunkt("PATCH", "/api/buchungen/{buchung_id:int}")
    async def buchung_aendern(request: Request):
        d = await koerper(request, BUCHUNG_AENDERUNG)
        return await schreiben(buch.buchung_aendern, pid(request, "buchung_id"), d)

    @endpunkt("DELETE", "/api/buchungen/{buchung_id:int}", 204)
    async def buchung_loeschen(request: Request):
        return await schreiben(buch.buchung_loeschen, pid(request, "buchung_id"))

    @endpunkt("PUT", "/api/buchungen/{buchung_id:int}/splits")
    async def splits_ersetzen(request: Request):
        d = await koerper(request, SPLITS_ERSETZEN)
        return await schreiben(buch.splits_ersetzen, pid(request, "buchung_id"), d["splits"])

    @endpunkt("PUT", "/api/buchungen/{buchung_id:int}/kategorie")
    async def kategorie_setzen(request: Request):
        d = await koerper(request, KATEGORIE)
        return await schreiben(buch.kategorie_setzen, pid(request, "buchung_id"), d["kategorie_id"])

    # -------------------------------------------------------------- Tags
    @endpunkt("GET", "/api/tags")
    async def tags_liste(request: Request):
        return await lesen(buch.tags_liste)

    @endpunkt("POST", "/api/tags", 201)
    async def tag_anlegen(request: Request):
        d = await koerper(request, TAG_EINGABE)
        return await schreiben(buch.tag_anlegen, d["name"])

    @endpunkt("PATCH", "/api/tags/{tag_id:int}")
    async def tag_umbenennen(request: Request):
        d = await koerper(request, TAG_EINGABE)
        return await schreiben(buch.tag_umbenennen, pid(request, "tag_id"), d["name"])

    @endpunkt("DELETE", "/api/tags/{tag_id:int}", 204)
    async def tag_loeschen(request: Request):
        return await schreiben(buch.tag_loeschen, pid(request, "tag_id"))

    # --------------------------------------------------------- Empfänger
    @endpunkt("GET", "/api/empfaenger")
    async def empfaenger_liste(request: Request):
        return await lesen(buch.empfaenger_liste)

    @endpunkt("POST", "/api/empfaenger", 201)
    async def empfaenger_anlegen(request: Request):
        d = await koerper(request, EMPFAENGER_NEU)
        return await schreiben(buch.empfaenger_anlegen, d["name"])

    @endpunkt("GET", "/api/empfaenger/{empfaenger_id:int}")
    async def empfaenger_lesen(request: Request):
        return await lesen(buch.empfaenger_lesen, pid(request, "empfaenger_id"))

    # ------------------------------------------------------------ Import
    @endpunkt("POST", "/api/import/kmymoney")
    async def import_kmymoney(request: Request):
        try:
            form = await request.form()
        except Exception:
            raise Validierungsfehler([fehler_eintrag(["body"], "multipart/form-data mit Feld 'datei' erwartet.")])
        datei = form.get("datei")
        if datei is None or isinstance(datei, str) or not hasattr(datei, "read"):
            raise Validierungsfehler([fehler_eintrag(["body", "datei"], "Die Datei fehlt (Feld 'datei').")])
        roh = await datei.read()
        dateiname = datei.filename or None

        def ausfuehren(con):
            return importiere_bytes(con, roh, dateiname)

        ergebnis = await lesen(ausfuehren)
        d = ergebnis.als_dict()
        if not ergebnis.erfolgreich:
            erster = ergebnis.fehler[0]
            return fehler_antwort(422, erster.code, erster.meldung, d)
        return d

    @endpunkt("GET", "/api/importe")
    async def importe(request: Request):
        return await lesen(buch.importe_liste)

    # --------------------------------------------------------- Dubletten
    @endpunkt("GET", "/api/dubletten")
    async def dubletten(request: Request):
        q = Query(request.query_params)
        status_ = q.auswahl("status", ("offen", "zusammengefuehrt", "keine_dublette"))
        q.pruefen()
        return await lesen(buch.dubletten_liste, status_)

    @endpunkt("POST", "/api/dubletten/{verdacht_id:int}/aufloesen")
    async def dublette_aufloesen(request: Request):
        d = await koerper(request, DUBLETTE_AUFLOESEN)
        return await schreiben(buch.verdacht_aufloesen, pid(request, "verdacht_id"), d["entscheidung"],
                               d.get("behalten_id"))

    # ---------------------------------------------------- Weboberfläche
    index = _index_html(config)

    @app.get("/", include_in_schema=False)
    async def startseite():
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest():
        return Response((WEB / "manifest.webmanifest").read_bytes(), media_type="application/manifest+json")

    app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")
    return app


__all__ = ["create_app", "BETRAG_MAX"]
