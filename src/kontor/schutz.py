"""Meilenstein 7: ASGI-Hülle für Netzbeschränkung, Sitzungsprüfung, Herkunft/CSRF, Größengrenzen und
Sicherheitsköpfe (sicherheit.md 3, 4.6, 6, 8, 10).

Reihenfolge je Anfrage: Netz → (geschützter Pfad) Sitzung → Herkunft → CSRF-Token → Größe → App.
Jede Antwort – auch die dieser Hülle und 5xx – trägt die Sicherheitsköpfe.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import urllib.parse
from http.cookies import CookieError, SimpleCookie

from starlette.concurrency import run_in_threadpool

from . import anmeldung

log = logging.getLogger("kontor.schutz")

COOKIE = "kontor_sitzung"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
       "form-action 'self'")
KOEPFE = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
          (b"referrer-policy", b"no-referrer"), (b"content-security-policy", CSP.encode("ascii")),
          (b"cross-origin-opener-policy", b"same-origin")]
OEFFENTLICH = {("GET", "/api/anmeldung"), ("POST", "/api/anmeldung"), ("POST", "/api/anmeldung/einrichten"),
               ("GET", "/api/gesundheit"), ("GET", "/anmelden")}
UPLOADS = {"/api/import/kmymoney", "/api/import/gnucash", "/api/sicherung/einspielen", "/api/dokumente"}
# Antworten mit diesem Kopf (nur Dokumentinhalte, D-123) behalten ihre eigene, strengere Inhaltsrichtlinie und
# dürfen von der eigenen Seite eingebettet werden; der Kopf selbst geht nie nach außen.
EINBETTBAR = b"x-kontor-einbettbar"
SCHREIBEND = {"POST", "PUT", "PATCH", "DELETE"}
_STANDARDPORT = {"http": 80, "https": 443}


def ist_api(pfad: str) -> bool:
    return pfad == "/api" or pfad.startswith("/api/")


def ist_oeffentlich(methode: str, pfad: str) -> bool:
    m = "GET" if methode == "HEAD" else methode
    return (m, pfad) in OEFFENTLICH or (m == "GET" and pfad.startswith("/oeffentlich/"))


def cookie_token(scope) -> str | None:
    for k, v in scope.get("headers", []):
        if k == b"cookie":
            c = SimpleCookie()
            try:
                c.load(v.decode("latin-1"))
            except CookieError:
                continue
            if COOKIE in c and c[COOKIE].value:
                return c[COOKIE].value
    return None


def kopf(scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


def _ursprung(url: str) -> str | None:
    try:
        t = urllib.parse.urlsplit(url)
        port = t.port
    except ValueError:
        return None
    if t.scheme not in ("http", "https") or not t.hostname:
        return None
    host = t.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is None or port == _STANDARDPORT[t.scheme]:
        return f"{t.scheme}://{host}"
    return f"{t.scheme}://{host}:{port}"


def eigener_ursprung(scope) -> str | None:
    host = kopf(scope, b"host")
    if not host:
        return None
    return _ursprung(f"{scope.get('scheme', 'http')}://{host}")


def ist_https(scope) -> bool:
    return scope.get("scheme") == "https"


def json_antwort(status: int, code: str, meldung: str, details=None, extra: list | None = None):
    return status, [(b"content-type", b"application/json")] + (extra or []), json.dumps(
        {"fehler": {"code": code, "meldung": meldung, "details": details}}, ensure_ascii=False).encode("utf-8")


class Schutz:
    def __init__(self, app, config, modus: str) -> None:
        self.app = app
        self.config = config
        self.modus = modus.encode("ascii")
        self.dienst = anmeldung.Anmeldedienst(config)
        self.netze = ([ipaddress.ip_network(n) for n in config.erlaubte_netze]
                      if config.erlaubte_netze is not None else None)
        self.upload_grenze = config.upload_max_mib * 1024 * 1024
        self.anfrage_grenze = config.anfrage_max_kib * 1024
        eigene = config.oeffentliche_url
        self.oeffentlicher_ursprung = _ursprung(eigene) if eigene else None

    # ------------------------------------------------------------------ Hilfen
    def _netz_erlaubt(self, scope) -> bool:
        if self.netze is None:
            return True
        client = scope.get("client")
        try:
            adresse = ipaddress.ip_address(client[0]) if client else None
        except ValueError:
            return False
        if adresse is None:
            return False
        if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped is not None:
            adresse = adresse.ipv4_mapped
        return any(adresse.version == n.version and adresse in n for n in self.netze)

    def _herkunft_ok(self, scope) -> bool:
        if (kopf(scope, b"sec-fetch-site") or "").strip().lower() == "cross-site":
            return False
        origin = kopf(scope, b"origin")
        if origin is None:
            return True
        o = origin.strip()
        if o.lower() == "null":
            return False
        ursprung = _ursprung(o)
        return ursprung is not None and ursprung in (eigener_ursprung(scope), self.oeffentlicher_ursprung)

    async def _senden(self, send, scope, status: int, koepfe: list, koerper: bytes) -> None:
        await send({"type": "http.response.start", "status": status,
                    "headers": self._koepfe(scope, koepfe + [(b"content-length", str(len(koerper)).encode())])})
        await send({"type": "http.response.body", "body": koerper if scope.get("method") != "HEAD" else b""})

    def _koepfe(self, scope, koepfe: list) -> list:
        pfad = scope["path"]
        namen = {k.lower() for k, _ in koepfe}
        aus = [(k, v) for k, v in koepfe if k.lower() not in {n for n, _ in KOEPFE}]
        if EINBETTBAR in namen and ist_api(pfad):
            eigene = next((v for k, v in koepfe if k.lower() == b"content-security-policy"), None)
            aus = [(k, v) for k, v in aus if k.lower() != EINBETTBAR]
            aus += [(k, v) for k, v in KOEPFE if k not in (b"x-frame-options", b"content-security-policy")]
            aus += [(b"x-frame-options", b"SAMEORIGIN"), (b"content-security-policy", eigene or CSP.encode("ascii"))]
        else:
            aus = [(k, v) for k, v in aus if k.lower() != EINBETTBAR]
            aus += KOEPFE
        typ = next((v for k, v in koepfe if k.lower() == b"content-type"), b"")
        erzwingen = ist_api(pfad) or typ.lower().startswith(b"text/html")
        statisch = pfad.startswith(("/oeffentlich/", "/static/"))
        if erzwingen or (not statisch and b"cache-control" not in namen):
            aus = [(k, v) for k, v in aus if k.lower() != b"cache-control"] + [(b"cache-control", b"no-store")]
        if ist_api(pfad) and b"x-kontor-modus" not in namen:
            aus.append((b"x-kontor-modus", self.modus))
        return aus

    async def _fehler(self, send, scope, status: int, code: str, meldung: str, details=None, extra=None):
        if ist_api(scope["path"]):
            s, k, b = json_antwort(status, code, meldung, details, extra)
        else:
            s, k, b = status, [(b"content-type", b"text/plain; charset=utf-8")] + (extra or []), (
                meldung.encode("utf-8"))
        await self._senden(send, scope, s, k, b)

    # ------------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        gestartet = False

        async def senden(nachricht):
            nonlocal gestartet
            if nachricht["type"] == "http.response.start":
                gestartet = True
                nachricht = {**nachricht, "headers": self._koepfe(scope, list(nachricht.get("headers", [])))}
            await send(nachricht)

        try:
            await self._bearbeiten(scope, receive, senden)
        except Exception:  # letzte Absicherung: keine Details nach außen
            log.exception("Unbehandelter Fehler")
            if not gestartet:
                await self._fehler(send, scope, 500, "interner_fehler", "Interner Fehler.")

    async def _bearbeiten(self, scope, receive, send):
        pfad, methode = scope["path"], scope["method"].upper()
        # 1. Netz (sicherheit.md 10) – allererste Prüfung
        if not self._netz_erlaubt(scope):
            return await self._fehler(send, scope, 403, "netz_nicht_erlaubt",
                                      "Zugriff nur aus den erlaubten Netzen.", {})
        state = scope.setdefault("state", {})
        if self.config.anmeldung:
            oeffentlich = ist_oeffentlich(methode, pfad)
            if not oeffentlich:
                # 2. Sitzung (3.2)
                token = cookie_token(scope)
                sitzung = await run_in_threadpool(self.dienst.sitzung_pruefen, token) if token else None
                if sitzung is None:
                    if ist_api(pfad):
                        return await self._fehler(send, scope, 401, "nicht_angemeldet",
                                                  "Bitte zuerst anmelden.", {})
                    ziel = pfad
                    qs = scope.get("query_string", b"")
                    if qs:
                        ziel += "?" + urllib.parse.unquote(qs.decode("latin-1"))
                    ort = "/anmelden?weiter=" + urllib.parse.quote(ziel, safe="/-._~")
                    return await self._senden(send, scope, 303, [(b"location", ort.encode("ascii")),
                                                                 (b"content-type", b"text/plain; charset=utf-8")],
                                              b"Weiterleitung zur Anmeldung.")
                state["kontor_sitzung"] = token
                state["kontor_sitzung_zeiten"] = sitzung
            if methode in SCHREIBEND:
                # 3. Herkunft (4.6 Punkt 1), auch für öffentliche POST-Pfade
                if not self._herkunft_ok(scope):
                    return await self._fehler(send, scope, 403, "csrf_ungueltig",
                                              "Die Anfrage kommt nicht von dieser Seite.", {})
                # 4. Token (nur geschützte Pfade)
                if not oeffentlich:
                    gesendet = kopf(scope, b"x-kontor-csrf") or ""
                    if not hmac.compare_digest(gesendet.encode("utf-8", "replace"),
                                               anmeldung.csrf_token(state["kontor_sitzung"]).encode("ascii")):
                        return await self._fehler(send, scope, 403, "csrf_ungueltig",
                                                  "CSRF-Token fehlt oder ist ungültig.", {})
        # 5. Größe (8)
        if methode in SCHREIBEND or kopf(scope, b"content-length") or kopf(scope, b"transfer-encoding"):
            upload = pfad in UPLOADS
            grenze = self.upload_grenze if upload else self.anfrage_grenze
            code = "datei_zu_gross" if upload else "anfrage_zu_gross"
            meldung = ("Die Datei ist zu groß." if upload else "Der Anfragekörper ist zu groß.")
            laenge = kopf(scope, b"content-length")
            if laenge is not None and laenge.strip().isdigit() and int(laenge) > grenze:
                return await self._fehler(send, scope, 413, code, meldung, {"grenze_bytes": grenze})
            teile, gesamt = [], 0
            while True:
                n = await receive()
                if n["type"] == "http.disconnect":
                    return
                stueck = n.get("body", b"")
                gesamt += len(stueck)
                if gesamt > grenze:
                    return await self._fehler(send, scope, 413, code, meldung, {"grenze_bytes": grenze})
                teile.append(stueck)
                if not n.get("more_body", False):
                    break
            koerper = b"".join(teile)
            geliefert = False

            async def wiedergabe():
                nonlocal geliefert
                if not geliefert:
                    geliefert = True
                    return {"type": "http.request", "body": koerper, "more_body": False}
                return await receive()

            return await self.app(scope, wiedergabe, send)
        return await self.app(scope, receive, send)


__all__ = ["Schutz", "COOKIE", "ist_https", "cookie_token"]
