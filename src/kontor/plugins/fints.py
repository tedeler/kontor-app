"""FinTS-Bank-Plugin (Platzhalter für Meilenstein 1).

Wählbar und erzeugbar, baut aber keine Verbindung auf; Abrufe melden
``PluginNichtVerfuegbar``. Die echte Anbindung über python-fints folgt mit
der Bank-Synchronisation (Meilenstein 2).
"""

from __future__ import annotations

import datetime as dt

from ..fehler import PluginNichtVerfuegbar
from .bank import BankKonto, BankPlugin, BankUmsatz


class FintsBankPlugin(BankPlugin):
    name = "fints"
    ist_mock = False

    def konten(self) -> list[BankKonto]:
        raise PluginNichtVerfuegbar("Die FinTS-Anbindung ist in dieser Version noch nicht verfügbar.")

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date) -> list[BankUmsatz]:
        raise PluginNichtVerfuegbar("Die FinTS-Anbindung ist in dieser Version noch nicht verfügbar.")
