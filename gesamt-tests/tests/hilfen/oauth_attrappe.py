"""Lokale OAuth2-Attrappe nach dem Vorbild von Google (mail.md 8) – nur 127.0.0.1, synthetische Tokens.

- ``genehmige(autorisierung_url)`` spielt die Zustimmung des Anwenders im Browser: prüft die Parameter
  (Client-ID, Umleitungsadresse, Scope, PKCE S256, ``access_type=offline``, ``prompt=consent``) und liefert
  die Umleitungs-URL mit ``state`` und ``code`` (bzw. ``error=access_denied``).
- ``POST /token``: ``authorization_code`` (Secret, Code einmalig, ``redirect_uri``, ``code_verifier``) und
  ``refresh_token``; Fehler wie Google (400 ``invalid_grant`` „Token has been expired or revoked.“, 401
  ``invalid_client``).
- ``POST /revoke``: widerruft den Token.
- ``access_gueltig(adresse, token)``: für die IMAP-Attrappe (XOAUTH2).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit

from .http_attrappe import HttpAnfrage, HttpAttrappe, json_antwort

SCOPE = "https://mail.google.com/"


@dataclass
class _Refresh:
    adresse: str
    ausgestellt: float
    lebensdauer: int | None          # Sekunden oder None (unbegrenzt)
    widerrufen: bool = False
    abgelaufen: bool = False

    def gueltig(self) -> bool:
        if self.widerrufen or self.abgelaufen:
            return False
        return self.lebensdauer is None or time.time() < self.ausgestellt + self.lebensdauer


@dataclass
class _Access:
    adresse: str
    refresh: str
    bis: float


@dataclass
class _Code:
    adresse: str
    challenge: str
    redirect_uri: str
    scope: str
    benutzt: bool = False


@dataclass
class Genehmigung:
    """Parameter einer Autorisierungs-URL, wie die Attrappe sie gesehen hat."""
    parameter: dict[str, str]
    fehler: list[str] = field(default_factory=list)


class OAuthAttrappe(HttpAttrappe):
    name = "oauth-attrappe"

    def __init__(self, *, client_id: str, client_secret: str, redirect_uri: str, **kw) -> None:
        super().__init__(**kw)
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_lebensdauer = 3600
        self.refresh_lebensdauer: int | None = None       # None: Feld refresh_token_expires_in fehlt
        self.scope_antwort: str | None = None             # None: angefragter Scope
        self.ohne_refresh_token = False
        self.fehlerstatus: int | None = None              # z. B. 500 für einen Ausfall
        self.genehmigungen: list[Genehmigung] = []
        self._codes: dict[str, _Code] = {}
        self.refresh_tokens: dict[str, _Refresh] = {}
        self.access_tokens: dict[str, _Access] = {}
        self.widerrufe: list[str] = []

    # ------------------------------------------------------------ URLs
    @property
    def autorisierung_url(self) -> str:
        return self.basis + "/auth"

    @property
    def token_url(self) -> str:
        return self.basis + "/token"

    @property
    def widerruf_url(self) -> str:
        return self.basis + "/revoke"

    # ------------------------------------------------------------ Zustimmung im „Browser“
    def genehmige(self, url: str, *, ablehnen: bool = False, adresse: str | None = None) -> str:
        teile = urlsplit(url)
        assert f"{teile.scheme}://{teile.netloc}{teile.path}" == self.autorisierung_url, url
        roh = parse_qs(teile.query, keep_blank_values=True)
        p = {k: v[0] for k, v in roh.items()}
        g = Genehmigung(p)
        for k, v in roh.items():
            if len(v) != 1:
                g.fehler.append(f"Parameter {k} mehrfach")
        soll = {"response_type": "code", "client_id": self.client_id, "redirect_uri": self.redirect_uri,
                "scope": SCOPE, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"}
        for k, v in soll.items():
            if p.get(k) != v:
                g.fehler.append(f"{k}={p.get(k)!r}, erwartet {v!r}")
        for k in ("state", "code_challenge", "login_hint"):
            if not p.get(k):
                g.fehler.append(f"{k} fehlt")
        self.genehmigungen.append(g)
        assert not g.fehler, g.fehler
        ziel = p["redirect_uri"]
        trenner = "&" if "?" in ziel else "?"
        if ablehnen:
            return ziel + trenner + urlencode({"state": p["state"], "error": "access_denied"})
        code = "SYNTH-CODE-" + secrets.token_urlsafe(12)
        self._codes[code] = _Code(adresse or p["login_hint"], p["code_challenge"], p["redirect_uri"], p["scope"])
        return ziel + trenner + urlencode({"state": p["state"], "code": code, "scope": SCOPE})

    # ------------------------------------------------------------ Steuerung
    def _refresh_von(self, adresse: str) -> list[_Refresh]:
        return [r for r in self.refresh_tokens.values() if r.adresse == adresse]

    def widerrufe_alle(self, adresse: str) -> None:
        for r in self._refresh_von(adresse):
            r.widerrufen = True

    def lasse_ablaufen(self, adresse: str) -> None:
        for r in self._refresh_von(adresse):
            r.abgelaufen = True

    def access_gueltig(self, adresse: str, token: str) -> bool:
        a = self.access_tokens.get(token)
        if a is None or a.adresse.casefold() != adresse.casefold() or time.time() >= a.bis:
            return False
        r = self.refresh_tokens.get(a.refresh)
        return r is not None and not r.widerrufen

    def entwerte_access_tokens(self, adresse: str) -> None:
        for a in self.access_tokens.values():
            if a.adresse == adresse:
                a.bis = 0

    @property
    def token_anfragen(self) -> list[dict[str, str]]:
        return [a.formular for a in self.anfragen if urlsplit(a.pfad).path == "/token"]

    # ------------------------------------------------------------ HTTP
    def antworte(self, a: HttpAnfrage):
        pfad = urlsplit(a.pfad).path
        if self.fehlerstatus is not None:
            return json_antwort(self.fehlerstatus, {"error": "server_error"})
        if a.methode == "POST" and pfad == "/token":
            return self._token(a.formular)
        if a.methode == "POST" and pfad == "/revoke":
            t = a.formular.get("token", "")
            self.widerrufe.append(t)
            if t in self.refresh_tokens:
                self.refresh_tokens[t].widerrufen = True
            return json_antwort(200, {})
        return json_antwort(404, {"error": "not_found"})

    def _neues_access(self, adresse: str, refresh: str) -> str:
        t = "SYNTH-ACCESS-" + secrets.token_urlsafe(16)
        self.access_tokens[t] = _Access(adresse, refresh, time.time() + self.access_lebensdauer)
        return t

    def _token(self, f: dict[str, str]):
        if f.get("client_id") != self.client_id or f.get("client_secret") != self.client_secret:
            return json_antwort(401, {"error": "invalid_client", "error_description": "The OAuth client was not found."})
        art = f.get("grant_type")
        if art == "authorization_code":
            c = self._codes.get(f.get("code", ""))
            verifier = f.get("code_verifier", "")
            erwartet = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            if (c is None or c.benutzt or f.get("redirect_uri") != c.redirect_uri or erwartet != c.challenge
                    or not (43 <= len(verifier) <= 128)):
                return json_antwort(400, {"error": "invalid_grant", "error_description": "Bad Request"})
            c.benutzt = True
            refresh = "SYNTH-REFRESH-" + secrets.token_urlsafe(16)
            self.refresh_tokens[refresh] = _Refresh(c.adresse, time.time(), self.refresh_lebensdauer)
            antwort = {"access_token": self._neues_access(c.adresse, refresh), "expires_in": self.access_lebensdauer,
                       "scope": self.scope_antwort or c.scope, "token_type": "Bearer"}
            if not self.ohne_refresh_token:
                antwort["refresh_token"] = refresh
            if self.refresh_lebensdauer is not None:
                antwort["refresh_token_expires_in"] = self.refresh_lebensdauer
            return json_antwort(200, antwort)
        if art == "refresh_token":
            r = self.refresh_tokens.get(f.get("refresh_token", ""))
            if r is None or not r.gueltig():
                return json_antwort(400, {"error": "invalid_grant",
                                          "error_description": "Token has been expired or revoked."})
            return json_antwort(200, {"access_token": self._neues_access(r.adresse, f["refresh_token"]),
                                      "expires_in": self.access_lebensdauer, "scope": SCOPE, "token_type": "Bearer"})
        return json_antwort(400, {"error": "unsupported_grant_type"})
