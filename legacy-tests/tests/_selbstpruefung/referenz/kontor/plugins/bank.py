"""Bank-Schnittstelle laut plugins.md 1, 2, 7.1 (Wegwerf-Referenz)."""

from __future__ import annotations

import abc
import datetime
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class BankKonto:
    iban: str
    bic: str | None
    name: str
    art: str
    inhaber: str
    waehrung: str


@dataclass(frozen=True)
class BankUmsatz:
    umsatz_id: str
    iban: str
    buchungstag: datetime.date
    valuta: datetime.date | None
    betrag: int
    waehrung: str
    gegenpartei_name: str | None
    gegenpartei_iban: str | None
    verwendungszweck: str
    vormerkung: bool
    storno: bool


@dataclass(frozen=True)
class BankSaldo:
    """M11, kontostand.md 1: gebuchter Saldo, Sicht des Kontos."""
    iban: str
    betrag: int
    stichtag: datetime.date


class Umsatzliste(list):
    """M11, kontostand.md 1: Ergebnis von umsaetze() mit dem gebuchten Saldo der Bank."""
    saldo = None

    def __init__(self, umsaetze=(), saldo=None) -> None:
        super().__init__(umsaetze)
        self.saldo = saldo


@dataclass(frozen=True)
class TanAntwort:
    anforderung_id: str
    tan: str = field(repr=False)


class BankPlugin(abc.ABC):
    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def konten(self) -> list[BankKonto]: ...

    @abc.abstractmethod
    def umsaetze(self, iban: str, von: datetime.date, bis: datetime.date, *,
                 tan: TanAntwort | None = None) -> list[BankUmsatz]: ...

    def schliessen(self) -> None:
        return None
