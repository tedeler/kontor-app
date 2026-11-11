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


def mit_roh(n: MailNachricht, roh: bytes) -> MailNachricht:
    """Rohfassung (RFC 5322) als Zusatzattribut ``roh`` – kein Feld der Datenklasse (plugins.md legt die Felder
    fest); Vergleich und Darstellung bleiben unverändert. Genutzt für Dokumente aus Mails (D-123)."""
    object.__setattr__(n, "roh", roh)
    return n


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


__all__ = ["MailPlugin", "MailNachricht", "mit_roh"]
