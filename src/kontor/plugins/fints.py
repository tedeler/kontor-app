"""FinTS-Bank-Plugin (Platzhalter für Meilenstein 1 und 2, echte Anbindung in M6).

Wählbar und erzeugbar, baut aber keine Verbindung auf; Abrufe melden
``PluginNichtVerfuegbar``. Die echte Anbindung über python-fints folgt mit
der Bank-Synchronisation (Meilenstein 2).
"""

from __future__ import annotations

import datetime as dt

from ..fehler import PluginNichtVerfuegbar
from .bank import BankKonto, BankPlugin, BankUmsatz, TanAntwort


class FintsBankPlugin(BankPlugin):
    name = "fints"
    ist_mock = False

    def __init__(self, *, pin_quelle=None) -> None:
        # Die PIN-Quelle wird erst bei einem echten Abruf benötigt (M6); hier nie aufgerufen.
        self._pin_quelle = pin_quelle

    def __repr__(self) -> str:
        return "FintsBankPlugin()"

    def konten(self) -> list[BankKonto]:
        raise PluginNichtVerfuegbar("Die FinTS-Anbindung ist in dieser Version noch nicht verfügbar.")

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date, *,
                 tan: TanAntwort | None = None) -> list[BankUmsatz]:
        raise PluginNichtVerfuegbar("Die FinTS-Anbindung ist in dieser Version noch nicht verfügbar.")
