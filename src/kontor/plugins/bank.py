"""Schnittstelle der Bank-Plugins (plugins.md Abschnitte 1 und 2). Nur lesend."""

from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class TanAntwort:
    """Vom Benutzer eingegebene TAN zu einer TAN-Anforderung (plugins.md 7.1). repr() enthält die TAN nie."""

    anforderung_id: str
    tan: str = field(repr=False)


@dataclass(frozen=True)
class BankSaldo:
    """Gebuchter Saldo eines Kontos, wie die Bank ihn beim Umsatzabruf meldet (kontostand.md 1)."""

    iban: str
    betrag: int
    stichtag: dt.date


class Umsatzliste(list):  # type: ignore[type-arg]
    """Ergebnis von ``umsaetze()``: eine Liste von ``BankUmsatz`` mit dem Attribut ``saldo`` (kontostand.md 1).

    Vergleicht und verhält sich wie eine gewöhnliche Liste; ``saldo`` ist None, wenn die Bank keinen Saldo
    gemeldet hat.
    """

    saldo: BankSaldo | None = None

    def __init__(self, umsaetze: object = (), saldo: BankSaldo | None = None) -> None:
        super().__init__(umsaetze)  # type: ignore[call-overload]
        self.saldo = saldo


class BankPlugin(abc.ABC):
    """Lesender Zugriff auf Bankkonten. Es gibt bewusst keine schreibenden Methoden."""

    name: ClassVar[str]
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def konten(self) -> list[BankKonto]: ...

    @abc.abstractmethod
    def umsaetze(self, iban: str, von: dt.date, bis: dt.date, *,
                 tan: TanAntwort | None = None) -> list[BankUmsatz]: ...

    def schliessen(self) -> None:
        return None


__all__ = ["BankPlugin", "BankKonto", "BankUmsatz", "BankSaldo", "TanAntwort", "Umsatzliste"]
