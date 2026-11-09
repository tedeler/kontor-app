"""ntfy-Plugin (benachrichtigungen.md 3): JSON-Veröffentlichung an der Wurzel des ntfy-Servers.

Genau eine HTTP-Anfrage je Nachricht, keine Umleitungen; ``Authorization: Bearer`` nur mit einem Token aus
``token_quelle`` (Geheimnis ``ntfy_token``). Das Token erscheint nie in Meldungen, ``details`` oder ``repr()``.
"""

from __future__ import annotations

import http.client
import json
from collections.abc import Callable

from ..config import KontorConfig
from ..fehler import BenachrichtigungFehler
from ..netz import http_anfrage
from .benachrichtigung import BenachrichtigungsPlugin, PushNachricht


class NtfyPlugin(BenachrichtigungsPlugin):
    name = "ntfy"
    ist_mock = False

    def __init__(self, config: KontorConfig, *, token_quelle: Callable[[], str | None] | None = None) -> None:
        self._config = config
        self._token_quelle = token_quelle

    def __repr__(self) -> str:
        return "NtfyPlugin()"

    def senden(self, nachricht: PushNachricht) -> None:
        c = self._config
        koerper = {"topic": c.ntfy_topic, "title": nachricht.titel, "message": nachricht.text,
                   "priority": nachricht.prioritaet, "tags": list(nachricht.tags)}
        if nachricht.link is not None:
            koerper["click"] = nachricht.link
        koepfe = {"Content-Type": "application/json"}
        token = self._token_quelle() if self._token_quelle is not None else None
        if token:
            koepfe["Authorization"] = f"Bearer {token}"
        url = c.ntfy_url.rstrip("/") + "/"
        try:
            antwort = http_anfrage(c, "POST", url, json.dumps(koerper, ensure_ascii=False).encode("utf-8"), koepfe,
                                   c.ntfy_timeout_sekunden)
        except TimeoutError:
            raise BenachrichtigungFehler("Der ntfy-Server hat nicht rechtzeitig geantwortet.", status=None) from None
        except (OSError, http.client.HTTPException):
            raise BenachrichtigungFehler("Der ntfy-Server ist nicht erreichbar.", status=None) from None
        if not 200 <= antwort.status <= 299:
            raise BenachrichtigungFehler(f"Der ntfy-Server hat die Nachricht abgelehnt (HTTP {antwort.status}).",
                                         status=antwort.status)


__all__ = ["NtfyPlugin"]
