"""Benachrichtigungs-Schnittstelle (benachrichtigungen.md 2) – Wegwerf-Referenz."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class PushNachricht:
    benachrichtigung_id: int
    titel: str
    text: str
    link: str | None
    prioritaet: int
    tags: tuple[str, ...]
    schluessel: str


class BenachrichtigungsPlugin(abc.ABC):
    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def senden(self, nachricht: PushNachricht) -> None: ...

    def schliessen(self) -> None:
        return None
