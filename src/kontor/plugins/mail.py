"""Schnittstelle der Mail-Plugins (plugins.md Abschnitte 1 und 2). Nur lesend."""

from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from collections.abc import Callable
from typing import ClassVar

Fortschritt = Callable[[int, int], None]


@dataclass(frozen=True)
class MailNachricht:
    nachricht_id: str
    postfach: str
    empfangen: dt.datetime
    absender: str
    betreff: str
    text: str


@dataclass(frozen=True)
class MailKopf:
    """D-243: nur die Kopfzeilen einer Nachricht (Kennung, Zeit, Absender, Betreff). ``ort`` ist die Fundstelle
    des Plugins zum Nachladen des Inhalts (IMAP: ``<UIDVALIDITY>:<UID>``); für Kontor ohne Bedeutung."""
    nachricht_id: str
    postfach: str
    empfangen: dt.datetime
    absender: str
    betreff: str
    ort: str = ""


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

    # D-243: zweistufiger Abruf – erst die Kopfzeilen, den Inhalt nur bei Bedarf. Freiwillig; ein Plugin ohne diese
    # Fähigkeit wird wie bisher über ``nachrichten`` vollständig abgerufen.
    kann_koepfe: ClassVar[bool] = False

    def koepfe(self, postfach: str, seit: dt.datetime, fortschritt: Fortschritt | None = None) -> list[MailKopf]:
        """Kopfzeilen aller Nachrichten ab ``seit`` (gleiche Auswahl, Reihenfolge und Kennungen wie ``nachrichten``).
        ``fortschritt(erledigt, gesamt)`` meldet unterwegs, wie viele Kopfzeilen schon da sind (D-252)."""
        raise NotImplementedError

    def inhalte(self, postfach: str, koepfe: list[MailKopf],
                fortschritt: Fortschritt | None = None) -> dict[str, MailNachricht]:
        """Vollständige Nachrichten zu ``koepfe``, nach ``nachricht_id``; nicht mehr vorhandene fehlen im Ergebnis."""
        raise NotImplementedError

    def schliessen(self) -> None:
        return None


__all__ = ["MailPlugin", "MailNachricht", "MailKopf", "mit_roh"]
