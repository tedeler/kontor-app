"""Lokale ntfy-Attrappe (benachrichtigungen.md 7): zeichnet Veröffentlichungen auf, antwortet nach Statusfolge."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .http_attrappe import HttpAnfrage, HttpAttrappe, json_antwort


@dataclass
class Zustellversuch:
    anfrage: HttpAnfrage
    status: int

    @property
    def koerper(self) -> dict | None:
        try:
            return json.loads(self.anfrage.koerper.decode("utf-8"))
        except ValueError:
            return None


class NtfyAttrappe(HttpAttrappe):
    name = "ntfy-attrappe"

    def __init__(self, *, erwartetes_token: str | None = None, **kw) -> None:
        super().__init__(**kw)
        self.erwartetes_token = erwartetes_token
        self.statusfolge: list[int] = []      # von vorn verbraucht; leer → 200
        self.versuche: list[Zustellversuch] = []

    @property
    def url(self) -> str:
        return self.basis

    def antworte(self, a: HttpAnfrage):
        if self.erwartetes_token is not None and a.koepfe.get("authorization") != f"Bearer {self.erwartetes_token}":
            self.versuche.append(Zustellversuch(a, 401))
            return json_antwort(401, {"code": 40101, "http": 401, "error": "unauthorized"})
        status = self.statusfolge.pop(0) if self.statusfolge else 200
        if status == 200:
            try:
                json.loads(a.koerper.decode("utf-8"))
            except ValueError:
                status = 400
        self.versuche.append(Zustellversuch(a, status))
        if status != 200:
            return json_antwort(status, {"http": status, "error": "Fehler der Attrappe"})
        return json_antwort(200, {"id": f"N{len(self.versuche):06d}", "event": "message"})

    @property
    def angenommen(self) -> list[dict]:
        """JSON-Körper aller mit 200 beantworteten Veröffentlichungen, in Reihenfolge."""
        return [v.koerper for v in self.versuche if v.status == 200]
