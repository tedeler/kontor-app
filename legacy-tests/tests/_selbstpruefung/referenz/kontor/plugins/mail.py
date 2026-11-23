"""Mail-Schnittstelle (plugins.md 1, 2) – Wegwerf-Referenz."""

from __future__ import annotations

import abc
import datetime
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class MailNachricht:
    nachricht_id: str
    postfach: str
    empfangen: datetime.datetime
    absender: str
    betreff: str
    text: str


class MailPlugin(abc.ABC):
    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def postfaecher(self) -> list[str]: ...

    @abc.abstractmethod
    def nachrichten(self, postfach: str, seit: datetime.datetime) -> list[MailNachricht]: ...

    def schliessen(self) -> None:
        return None
