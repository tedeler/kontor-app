"""Schnittstelle der Benachrichtigungs-Plugins (benachrichtigungen.md 2, python-api.md 13.3)."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class PushNachricht:
    benachrichtigung_id: int
    titel: str
    text: str
    link: str | None          # absolute URL oder None
    prioritaet: int           # 1–5 (ntfy: 1 min … 5 max)
    tags: tuple[str, ...]
    schluessel: str


class BenachrichtigungsPlugin(abc.ABC):
    """Stellt genau eine Push-Nachricht je Aufruf zu; wirft sonst ``BenachrichtigungFehler``."""

    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def senden(self, nachricht: PushNachricht) -> None: ...

    def schliessen(self) -> None:
        return None


__all__ = ["BenachrichtigungsPlugin", "PushNachricht"]
