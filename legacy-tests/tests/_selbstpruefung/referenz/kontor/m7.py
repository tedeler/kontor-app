"""WEGWERF-REFERENZ: Anmeldung, Härtung, Gesundheit (sicherheit.md, betrieb.md 6) – KEIN Anwendungscode."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import secrets
from http.cookies import SimpleCookie
from urllib.parse import quote, unquote, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.datastructures import MutableHeaders

from . import __version__, anmeldung, mutant

LOG = logging.getLogger("kontor.anmeldung")
UNSICHER = {"POST", "PUT", "PATCH", "DELETE"}
UPLOADS = {"/api/import/kmymoney", "/api/import/gnucash", "/api/sicherung/einspielen"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
SKRIPT = "document.querySelector('[data-testid=anmeldung-formular]')?.addEventListener('submit', e => {});\n"


def _jetzt() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ts(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fehler(status: int, code: str, meldung: str, details=None, koepfe=None) -> JSONResponse:
    return JSONResponse({"fehler": {"code": code, "meldung": meldung, "details": {} if details is None else details}},
                        status, headers=koepfe)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Anmeldung:
    """Sitzungen, Bremse und Einrichtung einer App."""

    def __init__(self, config) -> None:
        self.config = config

    @property
    def z(self) -> dict:
        return anmeldung.zustand(self.config)

    def sitzung(self, token: str | None) -> dict | None:
        if not token:
            return None
        s = self.z["sitzungen"].get(_hash(token))
        if s is None:
            return None
        jetzt = _jetzt()
        leer = (jetzt - s["letzte"]).total_seconds() > self.config.sitzung_leerlauf_sekunden
        hoch = (jetzt - s["erstellt"]).total_seconds() > self.config.sitzung_hoechstdauer_sekunden
        if (leer and not mutant("m7_leerlauf_ignoriert")) or (hoch and not mutant("m7_hoechstdauer_ignoriert")):
            self.z["sitzungen"].pop(_hash(token), None)
            return None
        s["letzte"] = jetzt
        return s

    def ablauf(self, s: dict) -> str:
        return _ts(min(s["letzte"] + dt.timedelta(seconds=self.config.sitzung_leerlauf_sekunden),
                       s["erstellt"] + dt.timedelta(seconds=self.config.sitzung_hoechstdauer_sekunden)))

    def neue_sitzung(self) -> tuple[str, dict]:
        token = secrets.token_urlsafe(32)
        jetzt = _jetzt()
        s = {"erstellt": jetzt, "letzte": jetzt, "csrf": secrets.token_urlsafe(32), "hash": _hash(token)}
        self.z["sitzungen"][s["hash"]] = s
        return token, s

    def gesperrt_bis(self) -> dt.datetime | None:
        b = self.z["gesperrt_bis"]
        return b if b is not None and b > _jetzt() else None

    def fehlversuch(self, client: str) -> None:
        z = self.z
        z["fehlversuche"] += 1
        LOG.warning("Fehlgeschlagene Anmeldung von %s (%d in Folge)", client, z["fehlversuche"])
        n, s = self.config.anmeldung_fehlversuche, self.config.anmeldung_sperre_sekunden
        if z["fehlversuche"] >= n:
            k = 0 if mutant("m7_sperre_ohne_verdopplung") else z["fehlversuche"] - n
            dauer = min(s * 2 ** k, 86400)
            z["gesperrt_bis"] = _jetzt() + dt.timedelta(seconds=dauer)
            LOG.warning("Anmeldung für %d s gesperrt", dauer)

    def erfolg(self) -> None:
        self.z["fehlversuche"] = 0
        self.z["gesperrt_bis"] = None

    def status(self, s: dict | None) -> dict:
        bis = self.gesperrt_bis()
        return {"aktiv": self.config.anmeldung, "eingerichtet": anmeldung.ist_eingerichtet(self.config),
                "angemeldet": s is not None and self.config.anmeldung, "csrf_token": s["csrf"] if s else None,
                "sitzung_ablauf": self.ablauf(s) if s else None, "gesperrt_bis": _ts(bis) if bis else None}

    def cookie(self, token: str, request: Request) -> str:
        secure = self.config.sitzung_cookie_secure
        if secure is None:
            secure = request.url.scheme == "https"
        teile = [f"kontor_sitzung={token}", "Path=/", f"Max-Age={self.config.sitzung_hoechstdauer_sekunden}"]
        if not mutant("m7_cookie_ohne_httponly"):
            teile.append("HttpOnly")
        teile.append("SameSite=Strict")
        if secure:
            teile.append("Secure")
        return "; ".join(teile)

    def einrichtungscode(self) -> str | None:
        datei = anmeldung.einrichtungsdatei(self.config)
        try:
            t = datei.read_text(encoding="ascii")
        except OSError:
            return None
        return t[:-1] if len(t) == 33 and t.endswith("\n") else None

    def einrichtungsdatei_anlegen(self) -> None:
        if self.einrichtungscode():
            return
        datei = anmeldung.einrichtungsdatei(self.config)
        datei.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(datei, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(secrets.token_hex(16) + "\n")
        os.chmod(datei, 0o600)
        logging.getLogger("kontor.anmeldung").warning("Einrichtungscode liegt in %s", datei)


def _oeffentlich(methode: str, pfad: str) -> bool:
    if methode in ("GET", "HEAD") and (pfad in ("/api/anmeldung", "/api/gesundheit", "/anmelden")
                                       or pfad.startswith("/oeffentlich/")):
        return True
    if mutant("m7_oeffentlich_konten") and pfad == "/api/konten":
        return True
    if mutant("m13_version_oeffentlich") and pfad == "/api/version":
        return True
    return methode == "POST" and pfad in ("/api/anmeldung", "/api/anmeldung/einrichten")


def _herkunft_ok(koepfe: dict, scope: dict, config) -> bool:
    if mutant("m7_herkunft_ungeprueft"):
        return True
    if koepfe.get("sec-fetch-site", "").lower() == "cross-site":
        return False
    origin = koepfe.get("origin")
    if origin is None:
        return True
    if origin == "null":
        return False

    def ursprung(url: str) -> str | None:
        u = urlsplit(url)
        if not u.scheme or not u.hostname:
            return None
        port = u.port
        standard = {"http": 80, "https": 443}.get(u.scheme)
        return f"{u.scheme}://{u.hostname}" + (f":{port}" if port and port != standard else "")

    erlaubt = {ursprung(f"{scope.get('scheme', 'http')}://{koepfe.get('host', '')}")}
    if config.oeffentliche_url:
        erlaubt.add(ursprung(config.oeffentliche_url))
    return ursprung(origin) in erlaubt - {None}


def _netz_ok(scope: dict, netze) -> bool:
    if mutant("m7_netz_ignoriert"):
        return True
    adresse = (scope.get("client") or ("",))[0]
    if mutant("m7_netz_xff"):
        for k, v in scope.get("headers", []):
            if k.decode().lower() == "x-forwarded-for":
                adresse = v.decode().split(",")[0].strip()
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in ipaddress.ip_network(n) for n in netze)


class Sicherheit:
    """ASGI-Hülle: Netz, Anmeldung, Herkunft, CSRF, Größengrenzen, Sicherheitsköpfe (sicherheit.md 3–10)."""

    def __init__(self, app, config, anm: Anmeldung, modus: str) -> None:
        self.app, self.config, self.anm, self.modus = app, config, anm, modus

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        pfad, methode = scope["path"], scope["method"]
        koepfe = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        async def senden(msg):
            if msg["type"] == "http.response.start":
                h = MutableHeaders(scope=msg)
                if not mutant("m7_ohne_nosniff"):
                    h["X-Content-Type-Options"] = "nosniff"
                h["X-Frame-Options"] = "DENY"
                h["Referrer-Policy"] = "no-referrer"
                h["Cross-Origin-Opener-Policy"] = "same-origin"
                h["Content-Security-Policy"] = CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'") \
                    if mutant("m7_csp_inline") else CSP
                art = h.get("content-type", "")
                if pfad.startswith("/api") or art.startswith("text/html") or (
                        not pfad.startswith("/oeffentlich/") and msg["status"] in (303, 401, 403)):
                    h["Cache-Control"] = "no-store"
                if pfad.startswith("/api"):
                    h["X-Kontor-Modus"] = self.modus
            await send(msg)

        async def antworte(r: Response):
            await r(scope, receive, senden)

        if self.config.erlaubte_netze and not _netz_ok(scope, self.config.erlaubte_netze):
            if pfad.startswith("/api"):
                return await antworte(_fehler(403, "netz_nicht_erlaubt", "Zugriff nur aus dem Heimnetz"))
            return await antworte(Response("Zugriff nur aus dem Heimnetz", 403, media_type="text/plain"))
        sitzung = None
        if self.config.anmeldung:
            c = SimpleCookie()
            try:
                c.load(koepfe.get("cookie", ""))
            except Exception:  # noqa: BLE001
                pass
            sitzung = self.anm.sitzung(c["kontor_sitzung"].value if "kontor_sitzung" in c else None)
            scope.setdefault("state", {})["kontor_sitzung"] = sitzung
            oeffentlich = _oeffentlich(methode, pfad)
            if sitzung is None and not oeffentlich:
                if pfad.startswith("/api"):
                    if mutant("m7_401_nach_404") and pfad == "/api/gibt-es-nicht":
                        return await antworte(_fehler(404, "nicht_gefunden", "Nicht gefunden"))
                    return await antworte(_fehler(401, "nicht_angemeldet", "Bitte anmelden"))
                ziel = pfad + ("?" + unquote(scope["query_string"].decode("latin-1")) if scope["query_string"] else "")
                return await antworte(Response(b"", 303, headers={"Location": "/anmelden?weiter=" + quote(
                    ziel, safe="/-._~")}))
            if methode in UNSICHER:
                if not _herkunft_ok(koepfe, scope, self.config):
                    return await antworte(_fehler(403, "csrf_ungueltig", "Herkunft ungültig"))
                if not oeffentlich and not mutant("m7_csrf_ungeprueft") and not hmac.compare_digest(
                        koepfe.get("x-kontor-csrf", "").encode(), sitzung["csrf"].encode()):
                    return await antworte(_fehler(403, "csrf_ungueltig", "CSRF-Token fehlt oder ist falsch"))
        upload = pfad in UPLOADS
        grenze = (self.config.upload_max_mib * 1024 * 1024) if upload else self.config.anfrage_max_kib * 1024
        if mutant("m7_upload_grenze_exklusiv") and upload:
            grenze -= 1
        code = "datei_zu_gross" if upload else "anfrage_zu_gross"
        zu_gross = _fehler(413, code, "Anfrage zu groß", {"grenze_bytes": grenze})
        laenge = koepfe.get("content-length")
        if laenge and laenge.isdigit() and int(laenge) > grenze and not (mutant("m7_anfrage_grenze_ignoriert")
                                                                         and not upload):
            return await antworte(zu_gross)
        teile, gesamt = [], 0
        while True:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            teile.append(msg.get("body", b""))
            gesamt += len(teile[-1])
            if gesamt > grenze and not (mutant("m7_anfrage_grenze_ignoriert") and not upload):
                return await antworte(zu_gross)
            if not msg.get("more_body"):
                break
        body = b"".join(teile)
        art = koepfe.get("content-type", "")
        if body and pfad.startswith("/api") and "json" in art:
            try:
                json.loads(body)
            except RecursionError:
                return await antworte(_fehler(422, "validierung", "Anfrage zu tief verschachtelt", []))
            except UnicodeDecodeError:
                return await antworte(_fehler(422, "validierung", "Körper ist kein UTF-8", []))
            except ValueError:
                pass
        elif body and pfad.startswith("/api") and not art.startswith("multipart/"):
            return await antworte(_fehler(422, "validierung", "Content-Type nicht unterstützt", []))
        gesendet = False

        async def wiedergabe():
            nonlocal gesendet
            if not gesendet:
                gesendet = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, wiedergabe, senden)


def _anmelde_html(config, eingerichtet: bool) -> str:
    hinweis = '<div id="mock-hinweis">Mock-Modus: synthetische Daten</div>' if config.mock_modus else ""
    code = "" if eingerichtet else ('<input type="text" name="einrichtungscode" '
                                    'data-testid="anmeldung-einrichtungscode">')
    return ('<!DOCTYPE html><html><head><title>Kontor – Anmeldung</title>'
            '<link rel="manifest" href="/oeffentlich/manifest.webmanifest">'
            '<script src="/oeffentlich/anmeldung.js" defer></script></head><body>' + hinweis +
            '<form data-testid="anmeldung-formular">' + code +
            '<input type="password" name="passwort" data-testid="anmeldung-passwort">'
            '<button type="submit">Anmelden</button></form></body></html>')


def m7_einbinden(app: FastAPI, config, modus: str) -> Anmeldung:
    anm = Anmeldung(config)
    if config.anmeldung and not anmeldung.ist_eingerichtet(config):
        anm.einrichtungsdatei_anlegen()
    if not config.anmeldung and not config.mock_modus:
        logging.getLogger("kontor").warning("Anmeldung abgeschaltet: im Betrieb KONTOR_ANMELDUNG=1 setzen")

    def sitzung_von(request: Request):
        return request.scope.get("state", {}).get("kontor_sitzung")

    async def koerper(request: Request, felder: dict[str, int]) -> dict | JSONResponse:
        try:
            d = json.loads(await request.body())
        except (ValueError, RecursionError):
            d = None
        if not isinstance(d, dict) or set(d) != set(felder) or not all(
                isinstance(d[k], str) and 1 <= len(d[k]) <= m for k, m in felder.items()):
            return _fehler(422, "validierung", "Ungültige Anfrage", [{"ort": ["body"], "meldung": "ungültig"}])
        return d

    def regel_ok(pw: str) -> bool:
        try:
            anmeldung.pruefe_regeln(pw)
            return True
        except ValueError:
            return False

    def gesperrt() -> JSONResponse | None:
        bis = anm.gesperrt_bis()
        if bis is None:
            return None
        rest = max(1, math.ceil((bis - _jetzt()).total_seconds()))
        return _fehler(429, "anmeldung_gesperrt", "Zu viele Fehlversuche", {"gesperrt_bis": _ts(bis)},
                       {"Retry-After": str(rest)})

    def angemeldet(request: Request, s: dict, token: str) -> JSONResponse:
        r = JSONResponse(anm.status(s))
        r.headers.append("set-cookie", anm.cookie(token, request))
        return r

    def aus() -> JSONResponse:
        return _fehler(409, "anmeldung_abgeschaltet", "Anmeldung ist abgeschaltet")

    @app.get("/api/anmeldung")
    def status(request: Request):
        return anm.status(sitzung_von(request))

    @app.post("/api/anmeldung")
    async def anmelden(request: Request):
        if not config.anmeldung:
            return aus()
        d = await koerper(request, {"passwort": 4096})
        if isinstance(d, JSONResponse):
            return d
        if not anmeldung.ist_eingerichtet(config):
            return _fehler(409, "nicht_eingerichtet", "Noch kein Passwort eingerichtet")
        g = gesperrt()
        if g is not None and not mutant("m7_sperre_prueft_passwort"):
            return g
        if not anmeldung.passwort_pruefen(d["passwort"], anm.z["hash"]):
            anm.fehlversuch(request.client.host if request.client else "?")
            return _fehler(401, "anmeldung_fehlgeschlagen", "Passwort falsch")
        anm.erfolg()
        token, s = anm.neue_sitzung()
        LOG.info("Anmeldung erfolgreich")
        return angemeldet(request, s, token)

    @app.post("/api/anmeldung/einrichten")
    async def einrichten(request: Request):
        if not config.anmeldung:
            return aus()
        d = await koerper(request, {"einrichtungscode": 64, "passwort": 4096})
        if isinstance(d, JSONResponse):
            return d
        if not regel_ok(d["passwort"]):
            return _fehler(422, "validierung", "Passwort muss 12 bis 1024 Zeichen haben", [])
        if anmeldung.ist_eingerichtet(config):
            return _fehler(409, "bereits_eingerichtet", "Bereits eingerichtet")
        g = gesperrt()
        if g is not None:
            return g
        code = anm.einrichtungscode()
        if code is None or not hmac.compare_digest(code.encode(), d["einrichtungscode"].encode()):
            anm.fehlversuch(request.client.host if request.client else "?")
            return _fehler(403, "einrichtungscode_ungueltig", "Einrichtungscode falsch")
        anmeldung.passwort_setzen(config, d["passwort"])
        token, s = anm.neue_sitzung()
        return angemeldet(request, s, token)

    @app.post("/api/anmeldung/abmelden", status_code=204)
    def abmelden(request: Request):
        if not config.anmeldung:
            return aus()
        s = sitzung_von(request)
        if s and not mutant("m7_abmelden_nur_cookie"):
            anm.z["sitzungen"].pop(s["hash"], None)
        r = Response(status_code=204)
        r.headers.append("set-cookie", "kontor_sitzung=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict")
        return r

    @app.put("/api/anmeldung/passwort")
    async def passwort(request: Request):
        if not config.anmeldung:
            return aus()
        d = await koerper(request, {"altes_passwort": 4096, "neues_passwort": 4096})
        if isinstance(d, JSONResponse):
            return d
        if not regel_ok(d["neues_passwort"]):
            return _fehler(422, "validierung", "Passwort muss 12 bis 1024 Zeichen haben", [])
        g = gesperrt()
        if g is not None:
            return g
        if not anmeldung.passwort_pruefen(d["altes_passwort"], anm.z["hash"]):
            anm.fehlversuch(request.client.host if request.client else "?")
            return _fehler(403, "anmeldung_fehlgeschlagen", "Passwort falsch")
        eigene = sitzung_von(request)
        anm.z["hash"] = anmeldung.passwort_hash(d["neues_passwort"])
        anm.erfolg()
        if not mutant("m7_passwortaenderung_sitzungen_bleiben"):
            anm.z["sitzungen"] = {eigene["hash"]: eigene}
        return anm.status(eigene)

    @app.get("/api/gesundheit")
    def gesundheit():
        return {"status": "ok", "version": __version__}

    @app.get("/anmelden")
    def anmeldeseite(request: Request):
        if not config.anmeldung or sitzung_von(request) is not None:
            return Response(b"", 303, headers={"Location": "/"})
        return HTMLResponse(_anmelde_html(config, anmeldung.ist_eingerichtet(config)))

    @app.get("/oeffentlich/{name}")
    def oeffentlich(name: str, request: Request):
        from .m8 import mit_cache, statisch
        if name != "anmeldung.js":
            r = statisch(name)
            return mit_cache(request, r) if r else Response("Nicht gefunden", 404, media_type="text/plain")
        return mit_cache(request, Response(SKRIPT, media_type="text/javascript"))

    return anm


def sicherheit_einbinden(app: FastAPI, config, anm: Anmeldung, modus: str) -> None:
    app.add_middleware(Sicherheit, config=config, anm=anm, modus=modus)

