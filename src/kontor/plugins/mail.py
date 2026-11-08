"""Schnittstelle der Mail-Plugins (plugins.md Abschnitte 1 und 2). Nur lesend."""

from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class MailNachricht:
    nachricht_id: str
    postfach: str
    empfangen: dt.datetime
    absender: str
    betreff: str
    text: str


class MailPlugin(abc.ABC):
    """Lesender Zugriff auf Postfächer. Kein Senden, Löschen oder Verschieben."""

    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def postfaecher(self) -> list[str]: ...

    @abc.abstractmethod
    def nachrichten(self, postfach: str, seit: dt.datetime) -> list[MailNachricht]: ...

    def schliessen(self) -> None:
        return None


__all__ = ["MailPlugin", "MailNachricht"]
