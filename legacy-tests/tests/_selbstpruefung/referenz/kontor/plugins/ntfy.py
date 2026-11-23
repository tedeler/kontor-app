"""ntfy-Plugin (benachrichtigungen.md 3) – Wegwerf-Referenz."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from .. import mutant
from ..fehler import BenachrichtigungFehler
from .benachrichtigung import BenachrichtigungsPlugin, PushNachricht


class _OhneUmleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


class NtfyPlugin(BenachrichtigungsPlugin):
    name = "ntfy"
    ist_mock = False

    def __init__(self, config, *, token_quelle=None) -> None:
        self._c, self._token = config, token_quelle

    def __repr__(self) -> str:
        return "<NtfyPlugin>"

    def senden(self, n: PushNachricht) -> None:
        k = {"topic": self._c.ntfy_topic, "title": n.titel, "message": n.text, "priority": n.prioritaet,
             "tags": list(n.tags)}
        if n.link is not None:
            k["click"] = n.link
        koepfe = {"Content-Type": "application/json"}
        token = self._token() if self._token else None
        if token:
            koepfe["Authorization"] = f"Bearer {token}"
        url = self._c.ntfy_url.rstrip("/") + "/"
        kontext = ssl.create_default_context(cafile=str(self._c.tls_ca_datei) if self._c.tls_ca_datei else None)
        oeffner = urllib.request.build_opener(_OhneUmleitung, urllib.request.HTTPSHandler(context=kontext),
                                              urllib.request.ProxyHandler({}))
        req = urllib.request.Request(url, data=json.dumps(k).encode(), headers=koepfe, method="POST")
        try:
            with oeffner.open(req, timeout=self._c.ntfy_timeout_sekunden) as r:
                if not 200 <= r.status <= 299:
                    raise BenachrichtigungFehler("ntfy lehnt ab", status=r.status)
        except urllib.error.HTTPError as e:
            raise BenachrichtigungFehler("ntfy lehnt ab", status=e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise BenachrichtigungFehler("ntfy nicht erreichbar", status=None) from None
