"""Schnittstelle der Bank-Plugins (plugins.md Abschnitte 1 und 2). Nur lesend."""

from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class BankKonto:
    iban: str
    bic: str | None
    name: str
    art: str
    inhaber: str
    waehrung: str = "EUR"


@dataclass(frozen=True)
class BankUmsatz:
    umsatz_id: str
    iban: str
    buchungstag: dt.date
    valuta: dt.date | None
    betrag: int
    waehrung: str
    gegenpartei_name: str | None
    gegenpartei_iban: str | None
    verwendungszweck: str
    vormerkung: bool
    storno: bool


class BankPlugin(abc.ABC):
    """Lesender Zugriff auf Bankkonten. Es gibt bewusst keine schreibenden Methoden."""

    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def konten(self) -> list[BankKonto]: ...

    @abc.abstractmethod
    def umsaetze(self, iban: str, von: dt.date, bis: dt.date) -> list[BankUmsatz]: ...

    def schliessen(self) -> None:
        return None


__all__ = ["BankPlugin", "BankKonto", "BankUmsatz"]
