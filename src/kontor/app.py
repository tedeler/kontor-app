"""App-Fabrik und REST-Endpunkte (python-api.md 4, openapi.yaml).

Jede Anfrage öffnet eine eigene SQLite-Verbindung auf
``config.aktive_datenbank``; schreibende Operationen laufen in einer
Transaktion. Mehrere Apps im selben Prozess teilen keinen Zustand.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import functools
import html
import logging
import pathlib
import re
import urllib.parse
from collections.abc import Callable
from typing import Any

import fastapi
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from . import (__version__, berichte, buch, db, export, kredite, lernmodell, mail, pflege, protokoll, regeln,
               sicherung, vorlagen, wiederkehrend)
from .geheimnisse import REST_NAMEN
from .sync import SyncDienst
from .config import KontorConfig
from .importer.kmymoney import importiere_bytes
from .importer import gnucash as gnucash_import
from .validierung import (BETRAG_MAX, STATUS, ApiFehler, Feld, Query, Validierungsfehler, fehler_eintrag,
                          json_koerper, pruefe_koerper, pruefe_objekt)
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
ALIASE = S("str_liste", strip=True, min_len=1, max_len=200, max_items=100)
EMPFAENGER_NEU = {"name": S("str", pflicht=True, strip=True, min_len=1, max_len=200), "aliase": ALIASE,
                  "standardkategorie_id": S("int", nullbar=True)}
EMPFAENGER_AENDERUNG = {"name": S("str", strip=True, min_len=1, max_len=200), "aliase": ALIASE,
                        "standardkategorie_id": S("int", nullbar=True)}
EMPFAENGER_ZUSAMMEN = {"quelle_ids": S("int_liste", pflicht=True, min_items=1, max_items=100, eindeutig=True)}
BUCHUNG_ERFASSEN = {
    "art": S("enum", pflicht=True, werte=("ausgabe", "einnahme", "umbuchung", "korrektur")),
    "datum": S("datum", pflicht=True),
    "konto_id": S("int", pflicht=True),
    "betrag": S("betrag", pflicht=True),
    "kategorie_id": S("int", nullbar=True),
    "gegenkonto_id": S("int"),
    "empfaenger_id": S("int", nullbar=True),
    "empfaenger_name": S("str", strip=True, min_len=1, max_len=200),
    "verwendungszweck": S("str", max_len=10000),
    "memo": S("str", max_len=10000),
    "tag_ids": S("int_liste"),
    "status": S("enum", werte=("importiert", "vorlaeufig", "bestaetigt")),
}
UMBUCHUNGEN_ERKENNEN = {"trocken": S("bool")}
UMBUCHUNG_ZUSAMMEN = {"buchung_ids": S("int_liste", pflicht=True, min_items=2, max_items=2, eindeutig=True)}
ABSTIMMUNG_EINGABE = {"konto_id": S("int", pflicht=True), "stichtag": S("datum", pflicht=True),
                      "saldo": S("betrag", pflicht=True), "trocken": S("bool")}
KONTO_LOESCHEN = {
    "buchungen": S("enum", pflicht=True, werte=("loeschen", "elternkonto", "unkategorisiert")),
    "konflikte": S("enum", pflicht=True, werte=("loeschen", "behalten")),
    "gesperrte_einbeziehen": S("bool"),
    "trocken": S("bool"),
}
RUECKGAENGIG = {"aenderung_ids": S("int_liste", min_items=1, max_items=1000, eindeutig=True),
                "gruppe": S("str", min_len=1)}
VORSCHLAG_AKTION = {"aktion": S("enum", pflicht=True, werte=("annehmen", "ablehnen"))}
MEHRFACH_VORSCHLAG = {
    "buchung_ids": S("int_liste", pflicht=True, min_items=1, eindeutig=True),
    "aktion": S("enum", pflicht=True, werte=("annehmen", "ablehnen")),
}
REGELN_ANWENDEN = {
    "buchung_ids": S("int_liste", min_items=1, eindeutig=True),
    "regel_ids": S("int_liste", min_items=1, eindeutig=True),
    "nur_unkategorisiert": S("bool"),
    "trocken": S("bool"),
}
SYNC_ANFRAGE = {"von": S("datum"), "bis": S("datum")}
SYNC_ENTSCHEIDUNG = {"aktion": S("enum", pflicht=True, werte=("wiederherstellen", "ignorieren")),
                     "buchungen": S("enum", pflicht=True, werte=("alle", "nur_neue"))}
LERN_BUCHUNG = {"buchung_id": S("int", pflicht=True)}
LERN_MERKMALE = {"empfaenger": S("str", nullbar=True, max_len=200), "verwendungszweck": S("str", max_len=10000),
                 "betrag": S("betrag", pflicht=True)}
LERN_ANWENDEN = {"buchung_ids": S("int_liste", min_items=1, eindeutig=True), "trocken": S("bool")}
VORLAGEN_ANWENDEN = {
    "buchung_ids": S("int_liste", min_items=1, eindeutig=True),
    "vorlage_ids": S("int_liste", min_items=1, eindeutig=True),
    "nur_unkategorisiert": S("bool"),
    "trocken": S("bool"),
}
PIN_EINGABE = {"pin": S("str", pflicht=True, min_len=1, max_len=128)}
TAN_EINGABE = {"tan": S("str", pflicht=True, min_len=1, max_len=64)}
MOCK_ZEIT = {"jetzt": S("str", pflicht=True)}
GEHEIMNIS_EINGABE = {"wert": S("str", pflicht=True, min_len=1, max_len=4096)}
_ZEITSTEMPEL = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z$")
KREDIT_ZUORDNEN = {"buchung_ids": S("int_liste", max_items=10000, eindeutig=True), "trocken": S("bool")}
KREDIT_ABGLEICH = {"jahr": S("int", pflicht=True), "restschuld": S("int", pflicht=True),
                   "zinsen": S("int", pflicht=True), "trocken": S("bool")}
WIEDERKEHREND_PRUEFEN = {"buchung_ids": S("int_liste", max_items=10000, eindeutig=True)}
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


class _AbfrageSchwaerzen(logging.Filter):
    """Zugriffsprotokoll von uvicorn ohne Abfrageteil: ``/oauth2/rueckruf?state=…&code=…`` trägt Geheimnisse
    (geheimnisse.md 1 und 6)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = args[:2] + (args[2].split("?", 1)[0] + "?…",) + args[3:]
        return True


def protokolle_absichern() -> None:
    """Bibliotheks-Logger so einstellen, dass sie keine Geheimnisse ausgeben (geheimnisse.md 6 Punkt 2)."""
    from .plugins.fints import bibliothek_stilllegen
    bibliothek_stilllegen()
    zugriff = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _AbfrageSchwaerzen) for f in zugriff.filters):
        zugriff.addFilter(_AbfrageSchwaerzen())


def _rueckruf_html(ok: bool, meldung: str) -> str:
    """Antwortseite für GET /oauth2/rueckruf (mail.md 4.3) – ohne Codes, Tokens oder state."""
    titel = "Anmeldung erfolgreich" if ok else "Anmeldung fehlgeschlagen"
    return ("<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>Kontor – " + titel
            + "</title></head><body><h1>" + titel + "</h1><p>" + html.escape(meldung)
            + "</p><p><a href=\"/#einstellungen\">Zurück zu Kontor</a></p></body></html>")


def create_app(config: KontorConfig | None = None) -> fastapi.FastAPI:
    if config is None:
        config = KontorConfig.from_env()
    pfad = config.aktive_datenbank
    protokolle_absichern()
    db.schema_anlegen(pfad)  # vor der Rückkehr: Datei und Schema existieren
    modus = "mock" if config.mock_modus else "echt"
    sync = SyncDienst(config)
    sync.neustart_aufraeumen()  # synchronisation.md 10
    sync.zustellung.vorbereiten()  # M6: neue Benachrichtigungen ausstehend oder „keine“ (benachrichtigungen.md 4.1)
    zustellung = sync.zustellung
    maildienst = sync.mail

    @contextlib.asynccontextmanager
    async def lebensdauer(_app):
        # Der Planer-Thread startet nur im ASGI-Lifespan, nie in create_app (synchronisation.md 9).
        sync.planer_starten()
        try:
            yield
        finally:
            await run_in_threadpool(sync.planer_stoppen)

    app = fastapi.FastAPI(title="Kontor", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                          lifespan=lebensdauer)
    app.state.config = config
    app.state.sync = sync
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
                finally:
                    await neue_zustellen()
                if isinstance(ergebnis, Response):
                    return ergebnis
                if status == 204:
                    return Response(status_code=204)
                return JSONResponse(ergebnis, status_code=status)
            app.add_api_route(pfad_vorlage, wrapper, methods=[methode], include_in_schema=False)
            return wrapper
        return deko

    async def neue_zustellen():
        """benachrichtigungen.md 4.3 Schritt 1: erster Versuch noch in derselben Anfrage, vor der Antwort."""
        if zustellung.plugin is not None:
            try:
                await run_in_threadpool(zustellung.neue)
            except Exception:  # noqa: BLE001 - die Zustellung ändert nie die auslösende Operation
                log.exception("Fehler bei der Zustellung")

    async def lesen(f: Callable, *args):
        return await run_in_threadpool(mit_db(f), *args)

    async def schreiben(f: Callable, *args):
        return await run_in_threadpool(mit_db(f, schreibend=True), *args)

    def _protokolliert(aktion: str, f: Callable, quelle: str):
        def ausfuehren(*args):
            con = db.verbinde(pfad)
            try:
                return protokoll.ausfuehren(con, quelle, aktion, sync.jetzt_text(), f, *args)
            finally:
                con.close()
        return ausfuehren

    async def aendern(aktion: str, f: Callable, *args, quelle: str = "manuell"):
        """Schreibende Operation auf dem Buchbestand: eine Transaktion, eine Änderung im Protokoll."""
        return await run_in_threadpool(_protokolliert(aktion, f, quelle), *args)

    def mit_uhr(f: Callable):
        def g(con, *args):
            return f(con, *args, sync.jetzt_text())
        return g

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
        return await aendern("konto_anlegen", buch.konto_anlegen, d)

    @endpunkt("GET", "/api/konten/{konto_id:int}")
    async def konto_lesen(request: Request):
        return await lesen(buch.konto_lesen, pid(request, "konto_id"))

    @endpunkt("PATCH", "/api/konten/{konto_id:int}")
    async def konto_aendern(request: Request):
        d = await koerper(request, KONTO_AENDERUNG)
        return await aendern("konto_aendern", buch.konto_aendern, pid(request, "konto_id"), d)

    @endpunkt("DELETE", "/api/konten/{konto_id:int}", 204)
    async def konto_loeschen(request: Request):
        return await aendern("konto_loeschen", buch.konto_loeschen, pid(request, "konto_id"))

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
    def buchungsfilter(request: Request, seiten: bool = True) -> dict:
        """Filter- und Sortierparameter von GET /api/buchungen (auch für den Export, berichte.md 4)."""
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
            "vorschlag": q.wahrheitswert("vorschlag"),
            "abgestimmt": q.wahrheitswert("abgestimmt"),
            "sortierung": q.auswahl("sortierung", buch.SORTIERUNGEN) or "datum",
        }
        if seiten:
            f["seite"] = q.ganzzahl("seite", minimum=1)
            f["pro_seite"] = q.ganzzahl("pro_seite", minimum=1, maximum=500)
        if f["von"] and f["bis"] and f["von"] > f["bis"]:
            q.fehler_melden("von", "von darf nicht nach bis liegen.")
        if f["betrag_min"] is not None and f["betrag_max"] is not None and f["betrag_min"] > f["betrag_max"]:
            q.fehler_melden("betrag_min", "betrag_min darf nicht größer als betrag_max sein.")
        q.pruefen()
        if seiten:
            f["seite"] = f["seite"] or 1
            f["pro_seite"] = f["pro_seite"] or 50
        return f

    @endpunkt("GET", "/api/buchungen")
    async def buchungen_liste(request: Request):
        return await lesen(buch.buchungsliste, buchungsfilter(request))

    @endpunkt("POST", "/api/buchungen", 201)
    async def buchung_anlegen(request: Request):
        d = await koerper(request, BUCHUNG_NEU)
        return await aendern("buchung_anlegen", buch.buchung_anlegen, d)

    @endpunkt("POST", "/api/buchungen/mehrfach/kategorie")
    async def mehrfach_kategorie(request: Request):
        d = await koerper(request, MEHRFACH_KATEGORIE)
        return await aendern("mehrfach_kategorie", buch.mehrfach_kategorie, d["buchung_ids"], d["kategorie_id"])

    @endpunkt("POST", "/api/buchungen/mehrfach/tags")
    async def mehrfach_tags(request: Request):
        d = await koerper(request, MEHRFACH_TAGS)
        return await aendern("mehrfach_tags", buch.mehrfach_tags, d["buchung_ids"], d.get("hinzufuegen") or [],
                               d.get("entfernen") or [])

    @endpunkt("GET", "/api/buchungen/{buchung_id:int}")
    async def buchung_lesen(request: Request):
        return await lesen(buch.buchung_lesen, pid(request, "buchung_id"))

    @endpunkt("PATCH", "/api/buchungen/{buchung_id:int}")
    async def buchung_aendern(request: Request):
        d = await koerper(request, BUCHUNG_AENDERUNG)
        return await aendern("buchung_aendern", buch.buchung_aendern, pid(request, "buchung_id"), d)

    @endpunkt("DELETE", "/api/buchungen/{buchung_id:int}", 204)
    async def buchung_loeschen(request: Request):
        return await aendern("buchung_loeschen", buch.buchung_loeschen, pid(request, "buchung_id"))

    @endpunkt("PUT", "/api/buchungen/{buchung_id:int}/splits")
    async def splits_ersetzen(request: Request):
        d = await koerper(request, SPLITS_ERSETZEN)
        return await aendern("splits_ersetzen", buch.splits_ersetzen, pid(request, "buchung_id"), d["splits"])

    @endpunkt("PUT", "/api/buchungen/{buchung_id:int}/kategorie")
    async def kategorie_setzen(request: Request):
        d = await koerper(request, KATEGORIE)
        return await aendern("kategorie_setzen", buch.kategorie_setzen, pid(request, "buchung_id"), d["kategorie_id"])

    # ------------------------------------------------- Vorschläge (M2)
    @endpunkt("POST", "/api/buchungen/{buchung_id:int}/vorschlag")
    async def vorschlag_entscheiden(request: Request):
        d = await koerper(request, VORSCHLAG_AKTION)
        return await aendern("vorschlag_entscheiden", regeln.vorschlag_entscheiden, pid(request, "buchung_id"), d["aktion"])

    @endpunkt("POST", "/api/buchungen/mehrfach/vorschlag")
    async def mehrfach_vorschlag(request: Request):
        d = await koerper(request, MEHRFACH_VORSCHLAG)
        return await aendern("mehrfach_vorschlag", regeln.mehrfach_vorschlag, d["buchung_ids"], d["aktion"])

    # ------------------------------------------------------ Regeln (M2)
    @endpunkt("GET", "/api/regeln")
    async def regeln_liste(request: Request):
        return await lesen(regeln.regeln_liste)

    @endpunkt("POST", "/api/regeln", 201)
    async def regel_anlegen(request: Request):
        d = regeln.regel_koerper(await request.body(), neu=True)
        return await aendern("regel_anlegen", regeln.regel_anlegen, d)

    @endpunkt("POST", "/api/regeln/anwenden")
    async def regeln_anwenden(request: Request):
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", REGELN_ANWENDEN)
        return await aendern("regeln_anwenden", regeln.anwenden, d.get("buchung_ids"), d.get("regel_ids"),
                             d.get("nur_unkategorisiert", True), d.get("trocken", False), quelle="regeln")

    @endpunkt("GET", "/api/regeln/{regel_id:int}")
    async def regel_lesen(request: Request):
        return await lesen(regeln.regel_lesen, pid(request, "regel_id"))

    @endpunkt("PATCH", "/api/regeln/{regel_id:int}")
    async def regel_aendern(request: Request):
        d = regeln.regel_koerper(await request.body(), neu=False)
        return await aendern("regel_aendern", regeln.regel_aendern, pid(request, "regel_id"), d)

    @endpunkt("DELETE", "/api/regeln/{regel_id:int}", 204)
    async def regel_loeschen(request: Request):
        return await aendern("regel_loeschen", regeln.regel_loeschen, pid(request, "regel_id"))

    # ------------------------------------------------- Synchronisation (M2)
    async def mit_ablauf(f: Callable, *args):
        """Prüft vor jedem Zugriff auf /api/sync… und /api/tan-anforderungen… die TAN-Abläufe (7.4)."""
        def ausfuehren():
            sync.ablauf_pruefen()
            con = db.verbinde(pfad)
            try:
                return f(con, *args)
            finally:
                con.close()
        return await run_in_threadpool(ausfuehren)

    @endpunkt("POST", "/api/sync")
    async def sync_starten(request: Request):
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", SYNC_ANFRAGE)
        if d.get("von") and d.get("bis") and d["von"] > d["bis"]:
            raise Validierungsfehler([fehler_eintrag(["body", "von"], "von darf nicht nach bis liegen.")])

        def ausfuehren():
            sync.ablauf_pruefen()
            return sync.starten("manuell", d.get("von"), d.get("bis"))
        return await run_in_threadpool(ausfuehren)

    @endpunkt("GET", "/api/sync/status")
    async def sync_status(request: Request):
        return await mit_ablauf(sync.status)

    @endpunkt("GET", "/api/sync/laeufe")
    async def sync_laeufe(request: Request):
        return await mit_ablauf(sync.laeufe)

    @endpunkt("GET", "/api/sync/laeufe/{lauf_id:int}")
    async def sync_lauf(request: Request):
        return await mit_ablauf(sync.lauf_lesen, pid(request, "lauf_id"))

    @endpunkt("GET", "/api/sync/konten")
    async def sync_konten(request: Request):
        return await mit_ablauf(sync.konten_zustand)

    @endpunkt("POST", "/api/sync/konten/{iban}/entscheidung")
    async def sync_konto_entscheidung(request: Request):
        d = await koerper(request, SYNC_ENTSCHEIDUNG)  # 422 vor 404 vor 409 (synchronisation.md 16.3)
        iban = request.path_params["iban"]
        return await run_in_threadpool(sync.entscheidung, iban, d)

    @endpunkt("PUT", "/api/sync/pin", 204)
    async def pin_setzen(request: Request):
        sync.pin_eingabe_pruefen()  # M6: 409 pin_quelle_systemd, ohne den Körper auszuwerten
        d = await koerper(request, PIN_EINGABE)  # Fehlermeldungen enthalten den Wert nie
        sync.pin_setzen(d["pin"])

    @endpunkt("DELETE", "/api/sync/pin", 204)
    async def pin_verwerfen(request: Request):
        sync.pin_verwerfen()

    @endpunkt("GET", "/api/tan-anforderungen")
    async def tan_liste(request: Request):
        return await mit_ablauf(sync.tans)

    @endpunkt("GET", "/api/tan-anforderungen/{tan_id:int}")
    async def tan_lesen(request: Request):
        return await mit_ablauf(sync.tan_lesen, pid(request, "tan_id"))

    @endpunkt("GET", "/api/tan-anforderungen/{tan_id:int}/bild")
    async def tan_bild(request: Request):
        bild, typ = await mit_ablauf(sync.tan_bild, pid(request, "tan_id"))
        return Response(bild, media_type=typ, headers={"Cache-Control": "no-store"})

    @endpunkt("POST", "/api/tan-anforderungen/{tan_id:int}/antwort")
    async def tan_antworten(request: Request):
        tid = pid(request, "tan_id")
        await mit_ablauf(sync.tan_lesen, tid)  # 404 vor 422
        d = await koerper(request, TAN_EINGABE)
        return await run_in_threadpool(sync.tan_antworten, tid, d["tan"])

    @endpunkt("POST", "/api/tan-anforderungen/{tan_id:int}/abbrechen")
    async def tan_abbrechen(request: Request):
        return await run_in_threadpool(sync.tan_abbrechen, pid(request, "tan_id"))

    @endpunkt("GET", "/api/benachrichtigungen")
    async def benachrichtigungen(request: Request):
        q = Query(request.query_params)
        gelesen = q.wahrheitswert("gelesen")
        q.pruefen()
        return await lesen(buch.benachrichtigungen_liste, gelesen)

    @endpunkt("POST", "/api/benachrichtigungen/{benachrichtigung_id:int}/gelesen")
    async def benachrichtigung_gelesen(request: Request):
        return await schreiben(buch.benachrichtigung_gelesen, pid(request, "benachrichtigung_id"))

    # ------------------------------------- M6: Zustellung der Benachrichtigungen
    @endpunkt("GET", "/api/benachrichtigungen/zustellung")
    async def zustellung_status(request: Request):
        return await lesen(zustellung.status)

    @endpunkt("POST", "/api/benachrichtigungen/zustellen")
    async def zustellen(request: Request):
        return await run_in_threadpool(zustellung.alle)

    @endpunkt("POST", "/api/benachrichtigungen/test")
    async def test_benachrichtigung(request: Request):
        # App-Erweiterung (D-076): eine Push-Nachricht direkt über das Plugin, ohne Eintrag in der internen Liste.
        return await run_in_threadpool(zustellung.testnachricht)

    @endpunkt("GET", "/api/mock/zustellungen")
    async def mock_zustellungen(request: Request):
        if not config.mock_modus:
            raise ApiFehler(409, "nur_mock_modus", "Die Liste der Mock-Zustellungen gibt es nur im Mock-Modus.")
        return zustellung.mock_gesendet()

    # ------------------------------------------------ M6: Geheimnisspeicher
    def geheimnis_name(request: Request) -> str:
        name = request.path_params["name"]
        if name not in REST_NAMEN:
            raise buch.nicht_gefunden("Das Geheimnis")
        return name

    @endpunkt("GET", "/api/geheimnisse")
    async def geheimnisse_liste(request: Request):
        return await lesen(sync.geheimnisse.uebersicht)

    @endpunkt("PUT", "/api/geheimnisse/{name}", 204)
    async def geheimnis_setzen(request: Request):
        name = geheimnis_name(request)
        d = await koerper(request, GEHEIMNIS_EINGABE)  # Fehlermeldungen enthalten den Wert nie
        await schreiben(lambda con: sync.geheimnisse.setzen(con, name, d["wert"]))

    @endpunkt("DELETE", "/api/geheimnisse/{name}", 204)
    async def geheimnis_loeschen(request: Request):
        name = geheimnis_name(request)
        await schreiben(lambda con: sync.geheimnisse.loeschen(con, name))

    # ------------------------------------------------------- M6: Postfächer
    @endpunkt("GET", "/api/mail/postfaecher")
    async def postfaecher(request: Request):
        return await lesen(mail.postfaecher_liste)

    @endpunkt("POST", "/api/mail/postfaecher", 201)
    async def postfach_anlegen(request: Request):
        d = mail.postfach_koerper(await request.body(), True)
        return await aendern("postfach_anlegen", mail.postfach_anlegen, d)

    @endpunkt("GET", "/api/mail/postfaecher/{postfach_id:int}")
    async def postfach_lesen(request: Request):
        return await lesen(mail.postfach_lesen, pid(request, "postfach_id"))

    @endpunkt("PATCH", "/api/mail/postfaecher/{postfach_id:int}")
    async def postfach_aendern(request: Request):
        await lesen(mail.postfach_lesen, pid(request, "postfach_id"))  # 404 vor 422
        d = mail.postfach_koerper(await request.body(), False)
        return await aendern("postfach_aendern", mail.postfach_aendern, pid(request, "postfach_id"), d)

    @endpunkt("DELETE", "/api/mail/postfaecher/{postfach_id:int}", 204)
    async def postfach_loeschen(request: Request):
        await aendern("postfach_loeschen", mail.postfach_loeschen, pid(request, "postfach_id"))

    @endpunkt("GET", "/api/mail/postfaecher/{postfach_id:int}/status")
    async def postfach_status(request: Request):
        return await lesen(maildienst.status, pid(request, "postfach_id"))

    @endpunkt("POST", "/api/mail/postfaecher/{postfach_id:int}/anmeldung")
    async def anmeldung_starten(request: Request):
        return await run_in_threadpool(maildienst.anmeldung_starten, pid(request, "postfach_id"))

    @endpunkt("DELETE", "/api/mail/postfaecher/{postfach_id:int}/anmeldung", 204)
    async def abmelden(request: Request):
        await run_in_threadpool(maildienst.abmelden, pid(request, "postfach_id"))

    @endpunkt("POST", "/api/mail/anmeldung/abschluss")
    async def anmeldung_abschluss(request: Request):
        d = await koerper(request, mail.ABSCHLUSS)
        try:
            abfrage = urllib.parse.urlsplit(d["antwort_url"]).query
        except ValueError:
            abfrage = ""
        parameter = dict(urllib.parse.parse_qsl(abfrage, keep_blank_values=True))
        return await run_in_threadpool(maildienst.anmeldung_abschliessen, parameter)

    @endpunkt("POST", "/api/mail/abruf")
    async def mail_abruf(request: Request):
        return await run_in_threadpool(maildienst.abruf)

    @endpunkt("GET", "/api/mail/nachrichten")
    async def mail_nachrichten(request: Request):
        q = Query(request.query_params)
        postfach_id = q.ganzzahl("postfach_id")
        seite = q.ganzzahl("seite", minimum=1)
        pro_seite = q.ganzzahl("pro_seite", minimum=1, maximum=500)
        q.pruefen()
        return await lesen(maildienst.nachrichten_liste, postfach_id, seite or 1, pro_seite or 50)

    @app.get("/oauth2/rueckruf", include_in_schema=False)
    async def oauth_rueckruf(request: Request):
        parameter = {k: v for k, v in request.query_params.items()}
        try:
            await run_in_threadpool(maildienst.anmeldung_abschliessen, parameter)
        except ApiFehler as e:
            return HTMLResponse(_rueckruf_html(False, e.meldung), status_code=400,
                                headers={"Cache-Control": "no-store"})
        except Exception:  # noqa: BLE001
            log.exception("Fehler beim OAuth-Rückruf")
            return HTMLResponse(_rueckruf_html(False, "Interner Fehler."), status_code=400,
                                headers={"Cache-Control": "no-store"})
        finally:
            await neue_zustellen()
        return HTMLResponse(_rueckruf_html(True, "Das Postfach ist angemeldet. Dieses Fenster kann geschlossen "
                                                 "werden."), headers={"Cache-Control": "no-store"})

    @endpunkt("GET", "/api/mock/zeit")
    async def mock_zeit(request: Request):
        return sync.mock_zeit()

    @endpunkt("PUT", "/api/mock/zeit")
    async def mock_zeit_setzen(request: Request):
        sync.mock_zeit()  # 409 nur_mock_modus vor der Körperprüfung
        d = await koerper(request, MOCK_ZEIT)
        m = _ZEITSTEMPEL.match(d["jetzt"])
        zeitpunkt = None
        if m:
            try:
                zeitpunkt = dt.datetime.fromisoformat(f"{m[1]}T{m[2]}:{m[3]}:{m[4]}").replace(tzinfo=dt.timezone.utc)
            except ValueError:
                zeitpunkt = None
        if zeitpunkt is None:
            raise Validierungsfehler([fehler_eintrag(["body", "jetzt"], "Zeitstempel in UTC mit Z erwartet.")])
        return sync.mock_zeit_setzen(zeitpunkt)

    # -------------------------------------------------------------- Tags
    @endpunkt("GET", "/api/tags")
    async def tags_liste(request: Request):
        return await lesen(buch.tags_liste)

    @endpunkt("POST", "/api/tags", 201)
    async def tag_anlegen(request: Request):
        d = await koerper(request, TAG_EINGABE)
        return await aendern("tag_anlegen", buch.tag_anlegen, d["name"])

    @endpunkt("PATCH", "/api/tags/{tag_id:int}")
    async def tag_umbenennen(request: Request):
        d = await koerper(request, TAG_EINGABE)
        return await aendern("tag_umbenennen", buch.tag_umbenennen, pid(request, "tag_id"), d["name"])

    @endpunkt("DELETE", "/api/tags/{tag_id:int}", 204)
    async def tag_loeschen(request: Request):
        return await aendern("tag_loeschen", buch.tag_loeschen, pid(request, "tag_id"))

    # --------------------------------------------------------- Empfänger
    @endpunkt("GET", "/api/empfaenger")
    async def empfaenger_liste(request: Request):
        return await lesen(buch.empfaenger_liste)

    @endpunkt("POST", "/api/empfaenger", 201)
    async def empfaenger_anlegen(request: Request):
        d = await koerper(request, EMPFAENGER_NEU)
        return await aendern("empfaenger_anlegen", pflege.empfaenger_anlegen, d)

    @endpunkt("GET", "/api/empfaenger/{empfaenger_id:int}")
    async def empfaenger_lesen(request: Request):
        return await lesen(buch.empfaenger_lesen, pid(request, "empfaenger_id"))

    @endpunkt("PATCH", "/api/empfaenger/{empfaenger_id:int}")
    async def empfaenger_aendern(request: Request):
        d = await koerper(request, EMPFAENGER_AENDERUNG)
        return await aendern("empfaenger_aendern", pflege.empfaenger_aendern, pid(request, "empfaenger_id"), d)

    @endpunkt("DELETE", "/api/empfaenger/{empfaenger_id:int}", 204)
    async def empfaenger_loeschen(request: Request):
        return await aendern("empfaenger_loeschen", pflege.empfaenger_loeschen, pid(request, "empfaenger_id"))

    @endpunkt("POST", "/api/empfaenger/{empfaenger_id:int}/zusammenfuehren")
    async def empfaenger_zusammenfuehren(request: Request):
        d = await koerper(request, EMPFAENGER_ZUSAMMEN)
        return await aendern("empfaenger_zusammenfuehren", pflege.empfaenger_zusammenfuehren,
                             pid(request, "empfaenger_id"), d["quelle_ids"])

    # ----------------------------------------------------- M3: Pflege
    @endpunkt("POST", "/api/konten/{konto_id:int}/loeschen")
    async def konto_loeschen_mit_buchungen(request: Request):
        d = await koerper(request, KONTO_LOESCHEN)

        def f(con, kid, d):
            return protokoll.mit_aenderung_id(pflege.konto_loeschen_mit_buchungen(con, kid, d))
        return await aendern("konto_loeschen_mit_buchungen", f, pid(request, "konto_id"), d)

    @endpunkt("POST", "/api/buchungen/erfassen", 201)
    async def buchung_erfassen(request: Request):
        d = await koerper(request, BUCHUNG_ERFASSEN)
        def f(con, d):
            return pflege.erfassen(con, d, config.lernmodell_automatisch)
        return await aendern("buchung_erfassen", f, d)

    @endpunkt("POST", "/api/umbuchungen/erkennen")
    async def umbuchungen_erkennen(request: Request):
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", UMBUCHUNGEN_ERKENNEN)
        return await aendern("umbuchung_erkennen", pflege.umbuchungen_erkennen, d.get("trocken", False),
                             config.umbuchung_fenster_tage, quelle="umbuchung")

    @endpunkt("POST", "/api/umbuchungen/zusammenfuehren")
    async def umbuchung_zusammenfuehren(request: Request):
        d = await koerper(request, UMBUCHUNG_ZUSAMMEN)
        return await aendern("umbuchung_zusammenfuehren", pflege.umbuchung_von_hand, d["buchung_ids"])

    @endpunkt("GET", "/api/abstimmungen")
    async def abstimmungen_liste(request: Request):
        q = Query(request.query_params)
        kid = q.ganzzahl("konto_id")
        q.pruefen()
        return await lesen(pflege.abstimmungen_liste, kid)

    @endpunkt("POST", "/api/abstimmungen")
    async def abstimmen(request: Request):
        d = await koerper(request, ABSTIMMUNG_EINGABE)
        return await aendern("abstimmung_anlegen", mit_uhr(pflege.abstimmen), d)

    @endpunkt("GET", "/api/abstimmungen/{abstimmung_id:int}")
    async def abstimmung_lesen(request: Request):
        return await lesen(pflege.abstimmung_lesen, pid(request, "abstimmung_id"))

    @endpunkt("DELETE", "/api/abstimmungen/{abstimmung_id:int}", 204)
    async def abstimmung_aufheben(request: Request):
        return await aendern("abstimmung_aufheben", pflege.abstimmung_aufheben, pid(request, "abstimmung_id"))

    @endpunkt("GET", "/api/suche")
    async def volltextsuche(request: Request):
        q = Query(request.query_params)
        text = q.text("q", 1)
        limit = q.ganzzahl("limit", minimum=1, maximum=500)
        if "q" not in request.query_params:
            q.fehler_melden("q", "Pflichtparameter fehlt.")
        elif text is not None and (len(text) > 200 or not text.split()):
            q.fehler_melden("q", "1–200 Zeichen mit mindestens einem Wort.")
        q.pruefen()
        return await lesen(pflege.suche, text, limit or 50)

    # ------------------------------------------------- M4: Lernmodell
    @endpunkt("GET", "/api/lernmodell")
    async def lernmodell_zustand(request: Request):
        return await lesen(lernmodell.zustand, config.lernmodell_automatisch)

    @endpunkt("POST", "/api/lernmodell/vorhersage")
    async def lernmodell_vorhersage(request: Request):
        roh = json_koerper(await request.body())
        fehler: list[dict] = []
        if not isinstance(roh, dict):
            raise Validierungsfehler([fehler_eintrag(["body"], "JSON-Objekt erwartet.")])
        for k in roh:
            if k != "eintraege":
                fehler.append(fehler_eintrag(["body", k], "Unbekanntes Feld."))
        liste = roh.get("eintraege")
        eintraege = []
        if not isinstance(liste, list) or not 1 <= len(liste) <= 1000:
            fehler.append(fehler_eintrag(["body", "eintraege"], "Liste mit 1 bis 1000 Einträgen erwartet."))
        else:
            for i, e in enumerate(liste):
                ort = ["body", "eintraege", i]
                if not isinstance(e, dict):
                    fehler.append(fehler_eintrag(ort, "Objekt erwartet."))
                    continue
                schema = LERN_BUCHUNG if "buchung_id" in e else LERN_MERKMALE
                eintraege.append(pruefe_objekt(e, schema, ort, fehler))
        if fehler:
            raise Validierungsfehler(fehler)
        return await lesen(lernmodell.vorhersagen, eintraege)

    @endpunkt("POST", "/api/lernmodell/anwenden")
    async def lernmodell_anwenden(request: Request):
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", LERN_ANWENDEN)
        return await aendern("lernmodell_anwenden", lernmodell.anwenden, d.get("buchung_ids"),
                             d.get("trocken", False), quelle="lernmodell")

    # --------------------------------------------------- M4: Vorlagen
    @endpunkt("GET", "/api/vorlagen")
    async def vorlagen_liste(request: Request):
        return await lesen(vorlagen.vorlagen_liste)

    @endpunkt("POST", "/api/vorlagen", 201)
    async def vorlage_anlegen(request: Request):
        d = vorlagen.vorlage_koerper(await request.body(), neu=True)
        return await aendern("vorlage_anlegen", vorlagen.vorlage_anlegen, d)

    @endpunkt("POST", "/api/vorlagen/anwenden")
    async def vorlagen_anwenden(request: Request):
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", VORLAGEN_ANWENDEN)
        return await aendern("vorlagen_anwenden", vorlagen.anwenden, d.get("buchung_ids"), d.get("vorlage_ids"),
                             d.get("nur_unkategorisiert", True), d.get("trocken", False), quelle="vorlage")

    @endpunkt("GET", "/api/vorlagen/{vorlage_id:int}")
    async def vorlage_lesen(request: Request):
        return await lesen(vorlagen.vorlage_lesen, pid(request, "vorlage_id"))

    @endpunkt("PATCH", "/api/vorlagen/{vorlage_id:int}")
    async def vorlage_aendern(request: Request):
        vid = pid(request, "vorlage_id")
        await lesen(vorlagen.vorlage_lesen, vid)  # 404 vor 422
        d = vorlagen.vorlage_koerper(await request.body(), neu=False)
        return await aendern("vorlage_aendern", vorlagen.vorlage_aendern, vid, d)

    @endpunkt("DELETE", "/api/vorlagen/{vorlage_id:int}", 204)
    async def vorlage_loeschen(request: Request):
        return await aendern("vorlage_loeschen", vorlagen.vorlage_loeschen, pid(request, "vorlage_id"))

    # --------------------------------------------------- M5: Kredite
    @endpunkt("GET", "/api/kredite")
    async def kredite_liste(request: Request):
        return await lesen(kredite.kredite_liste)

    @endpunkt("POST", "/api/kredite", 201)
    async def kredit_anlegen(request: Request):
        d = kredite.kredit_koerper(await request.body(), neu=True)
        return await aendern("kredit_anlegen", kredite.kredit_anlegen, d)

    @endpunkt("POST", "/api/kredite/tilgungsplan")
    async def tilgungsplan(request: Request):
        return kredite.plan_rest(kredite.plan_koerper(await request.body()))

    @endpunkt("GET", "/api/kredite/{kredit_id:int}")
    async def kredit_lesen(request: Request):
        return await lesen(kredite.kredit_lesen, pid(request, "kredit_id"))

    @endpunkt("PATCH", "/api/kredite/{kredit_id:int}")
    async def kredit_aendern(request: Request):
        kid = pid(request, "kredit_id")
        await lesen(kredite.kredit_lesen, kid)  # 404 vor allem anderen
        d = kredite.kredit_koerper(await request.body(), neu=False)
        return await aendern("kredit_aendern", kredite.kredit_aendern, kid, d)

    @endpunkt("DELETE", "/api/kredite/{kredit_id:int}", 204)
    async def kredit_loeschen(request: Request):
        return await aendern("kredit_loeschen", kredite.kredit_loeschen, pid(request, "kredit_id"))

    @endpunkt("GET", "/api/kredite/{kredit_id:int}/plan")
    async def kredit_plan(request: Request):
        return await lesen(kredite.plan_des_kredits, pid(request, "kredit_id"))

    @endpunkt("POST", "/api/kredite/{kredit_id:int}/zuordnen")
    async def kredit_zuordnen(request: Request):
        kid = pid(request, "kredit_id")
        await lesen(kredite.kredit_lesen, kid)  # 404 vor 422
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", KREDIT_ZUORDNEN)
        return await aendern("kredit_zuordnen", kredite.zuordnen, kid, d.get("buchung_ids"), d.get("trocken", False),
                             quelle="kredit")

    @endpunkt("POST", "/api/kredite/{kredit_id:int}/jahresabgleich")
    async def kredit_jahresabgleich(request: Request):
        kid = pid(request, "kredit_id")
        await lesen(kredite.kredit_lesen, kid)  # 404 vor 422
        d = await koerper(request, KREDIT_ABGLEICH)
        fehler = [fehler_eintrag(["body", k], f"Ganzzahl von {a} bis {b} erwartet.")
                  for k, a, b in (("jahr", 1900, 9999), ("restschuld", 0, BETRAG_MAX), ("zinsen", 0, BETRAG_MAX))
                  if not a <= d[k] <= b]
        if fehler:
            raise Validierungsfehler(fehler)
        return await aendern("kredit_jahresabgleich", kredite.jahresabgleich, kid, d)

    # ---------------------------------------- M5: Wiederkehrende Buchungen
    @endpunkt("GET", "/api/wiederkehrend")
    async def wiederkehrend_uebersicht(request: Request):
        q = Query(request.query_params)
        stichtag = q.datum("stichtag")
        q.pruefen()
        return await lesen(wiederkehrend.uebersicht, stichtag or sync.heute().isoformat())

    @endpunkt("POST", "/api/wiederkehrend/pruefen")
    async def wiederkehrend_pruefen(request: Request):
        roh = await request.body()
        d = pruefe_koerper(roh if roh.strip() else b"{}", WIEDERKEHREND_PRUEFEN)
        erg = await schreiben(wiederkehrend.pruefen_rest, d.get("buchung_ids") or [], sync.heute().isoformat(),
                              sync.jetzt_text())
        if erg["benachrichtigungen"] and zustellung.plugin is not None:
            # M6: erst zustellen, dann antworten – die Antwort zeigt den Stand der Zustellung (4.3 Schritt 1)
            await neue_zustellen()

            def neu_lesen(con):
                ids = [b["id"] for b in erg["benachrichtigungen"]]
                return [b for b in buch.benachrichtigungen_liste(con, None) if b["id"] in ids]
            erg = {**erg, "benachrichtigungen": await lesen(neu_lesen)}
        return erg

    # -------------------------------------------- M5: Berichte und Export
    def berichtsfilter(request: Request) -> dict:
        q = Query(request.query_params)
        f = {"konto_id": q.ganzzahlen("konto_id"), "von": q.datum("von"), "bis": q.datum("bis"),
             "intervall": q.auswahl("intervall", berichte.INTERVALLE) or "monat",
             "unterkonten": q.wahrheitswert("unterkonten") or False}
        if f["von"] and f["bis"] and f["von"] > f["bis"]:
            q.fehler_melden("von", "von darf nicht nach bis liegen.")
        q.pruefen()
        return f

    @endpunkt("GET", "/api/berichte/kontostand")
    async def bericht_kontostand(request: Request):
        return await lesen(berichte.kontostand, berichtsfilter(request), sync.heute().isoformat())

    @endpunkt("GET", "/api/berichte/einnahmen-ausgaben")
    async def bericht_einnahmen_ausgaben(request: Request):
        f = berichtsfilter(request)
        return await lesen(berichte.einnahmen_ausgaben, f, sync.heute().isoformat())

    def _exportname(endung: str) -> str:
        return f"kontor-buchungen-{sync.heute().strftime('%Y%m%d')}.{endung}"

    @endpunkt("GET", "/api/export/buchungen.csv")
    async def export_csv(request: Request):
        f = buchungsfilter(request, seiten=False)
        daten = await lesen(export.csv_bytes, f)
        return Response(daten, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{_exportname("csv")}"',
                                 "Cache-Control": "no-store"})

    @endpunkt("GET", "/api/export/buchungen.pdf")
    async def export_pdf(request: Request):
        f = buchungsfilter(request, seiten=False)
        teile = [f"{k}={v}" for k, v in request.query_params.multi_items()]
        beschreibung = ("Filter: " + ", ".join(teile)) if teile else "Alle Buchungen"
        daten = await lesen(export.pdf_bytes, f, sync.heute().isoformat(), beschreibung)
        return Response(daten, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{_exportname("pdf")}"',
                                 "Cache-Control": "no-store"})

    # ------------------------------------------- M3: Änderungsprotokoll
    @endpunkt("GET", "/api/aenderungen")
    async def aenderungen_liste(request: Request):
        q = Query(request.query_params)
        f = {
            "quelle": q.auswahlen("quelle", protokoll.QUELLEN),
            "aktion": q.text("aktion", 1),
            "gruppe": q.text("gruppe", 1),
            "objekt": q.auswahl("objekt", protokoll.OBJEKTE),
            "objekt_id": q.ganzzahl("objekt_id"),
            "wirksam": q.wahrheitswert("wirksam"),
            "seite": q.ganzzahl("seite", minimum=1),
            "pro_seite": q.ganzzahl("pro_seite", minimum=1, maximum=500),
        }
        if "objekt_id" in request.query_params and "objekt" not in request.query_params:
            q.fehler_melden("objekt_id", "objekt_id nur zusammen mit objekt.")
        q.pruefen()
        return await lesen(protokoll.aenderungen_liste, f)

    @endpunkt("POST", "/api/aenderungen/rueckgaengig")
    async def aenderungen_rueckgaengig(request: Request):
        d = await koerper(request, RUECKGAENGIG)
        if ("aenderung_ids" in d) == ("gruppe" in d):
            raise Validierungsfehler([fehler_eintrag(["body"], "Genau eines der Felder aenderung_ids oder gruppe.")])
        return await lesen(mit_uhr(protokoll.mehrere_rueckgaengig), d)

    @endpunkt("GET", "/api/aenderungen/{aenderung_id:int}")
    async def aenderung_lesen(request: Request):
        return await lesen(protokoll.aenderung_lesen, pid(request, "aenderung_id"))

    @endpunkt("POST", "/api/aenderungen/{aenderung_id:int}/rueckgaengig")
    async def aenderung_rueckgaengig(request: Request):
        return await lesen(mit_uhr(protokoll.einzeln_rueckgaengig), pid(request, "aenderung_id"))

    # ------------------------------------------------------------ Import
    async def datei_importieren(request: Request, importieren: Callable):
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
            return importieren(con, roh, dateiname, zeitpunkt=sync.jetzt_text())

        ergebnis = await lesen(ausfuehren)
        d = ergebnis.als_dict()
        if not ergebnis.erfolgreich:
            erster = ergebnis.fehler[0]
            return fehler_antwort(422, erster.code, erster.meldung, d)
        return d

    @endpunkt("POST", "/api/import/kmymoney")
    async def import_kmymoney(request: Request):
        return await datei_importieren(request, importiere_bytes)

    @endpunkt("POST", "/api/import/gnucash")
    async def import_gnucash(request: Request):
        return await datei_importieren(request, gnucash_import.importiere_bytes)

    @endpunkt("GET", "/api/importe")
    async def importe(request: Request):
        return await lesen(buch.importe_liste)

    # ------------------------------------------------- M9: Datensicherung
    @endpunkt("GET", "/api/sicherung")
    async def sicherung_erstellen(request: Request):
        daten, name = await run_in_threadpool(sicherung.erstellen, pfad, modus, sync.jetzt())
        return Response(daten, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"',
                                 "Cache-Control": "no-store"})

    @endpunkt("POST", "/api/sicherung/einspielen")
    async def sicherung_einspielen(request: Request):
        q = Query(request.query_params)
        trocken = bool(q.wahrheitswert("trocken"))
        bestaetigt = bool(q.wahrheitswert("bestaetigt"))
        q.pruefen()
        try:
            form = await request.form()
        except Exception:
            raise Validierungsfehler([fehler_eintrag(["body"], "multipart/form-data mit Feld 'datei' erwartet.")])
        datei = form.get("datei")
        if datei is None or isinstance(datei, str) or not hasattr(datei, "read"):
            raise Validierungsfehler([fehler_eintrag(["body", "datei"], "Die Datei fehlt (Feld 'datei').")])
        roh = await datei.read()

        def ausfuehren():
            s = sicherung.pruefen(roh)
            if s.manifest["modus"] != modus:
                raise ApiFehler(409, "sicherung_modus",
                                "Die Sicherung stammt aus dem " + ("Mock-Modus" if s.manifest["modus"] == "mock"
                                                                   else "Echtbetrieb")
                                + " und passt nicht zu dieser Instanz.")
            con = db.verbinde(pfad)
            try:
                if trocken:
                    return sicherung.probelauf(con, s)
                if not bestaetigt:
                    raise ApiFehler(409, "bestaetigung_erforderlich",
                                    "Das Einspielen ersetzt den gesamten Bestand; bitte ausdrücklich bestätigen.")
                with sync.ohne_lauf():
                    return sicherung.einspielen(con, s, sync.jetzt_text())
            finally:
                con.close()

        return await run_in_threadpool(ausfuehren)

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
        return await aendern("dublette_aufloesen", buch.verdacht_aufloesen, pid(request, "verdacht_id"), d["entscheidung"],
                               d.get("behalten_id"))

    # ---------------------------------------------------- Weboberfläche
    index = _index_html(config)

    @app.get("/", include_in_schema=False)
    async def startseite():
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/tan/{tan_id}", include_in_schema=False)
    async def tan_seite(tan_id: str):
        # Link aus der Benachrichtigung (synchronisation.md 7.2) öffnet die TAN-Seite der Oberfläche.
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/buchungen/{buchung_id}", include_in_schema=False)
    async def buchung_seite(buchung_id: str):
        # Link aus der Benachrichtigung split_abweichung (vorlagen.md 6) öffnet die Buchung in der Oberfläche.
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/sync/konten", include_in_schema=False)
    async def sync_konten_seite():
        # Link aus der Benachrichtigung konto_fehlt (synchronisation.md 16.5).
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/wiederkehrend", include_in_schema=False)
    async def wiederkehrend_seite():
        # Link aus den Benachrichtigungen wiederkehrend_ausbleibend (wiederkehrend.md 6).
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/mail/postfaecher/{postfach_id}", include_in_schema=False)
    async def postfach_seite(postfach_id: str):
        # Link aus den Mail-Benachrichtigungen (benachrichtigungen.md 6) öffnet die Postfach-Einstellungen.
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/einstellungen", include_in_schema=False)
    async def einstellungen_seite():
        return HTMLResponse(index, headers={"Cache-Control": "no-store"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest():
        return Response((WEB / "manifest.webmanifest").read_bytes(), media_type="application/manifest+json")

    app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")
    return app


__all__ = ["create_app", "BETRAG_MAX"]
