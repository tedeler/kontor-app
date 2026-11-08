"""Mock-Bank-Plugin: synthetische Daten aus Datendatei oder eingebautem Datensatz (plugins.md 3).

Baut nie eine Netzwerkverbindung auf. Zeitlich fortlaufend über ein
simuliertes „heute“.
"""

from __future__ import annotations

import datetime as dt
import pathlib

from ..fehler import BankKontoUnbekannt, BankVerbindungsFehler, BankZeitueberschreitung, TanErforderlich
from . import mock_daten as md
from .bank import BankKonto, BankPlugin, BankUmsatz


class MockBankPlugin(BankPlugin):
    name = "mock"
    ist_mock = True

    def __init__(self, daten: pathlib.Path | None = None, szenario: str = "normal",
                 heute: dt.date | None = None) -> None:
        self._szenario = md.szenario_pruefen(szenario)
        self._daten = md.lade_datei(pathlib.Path(daten)) if daten is not None else None
        self._heute = heute

    def setze_heute(self, heute: dt.date | None) -> None:
        self._heute = heute

    def _jetzt(self) -> dt.date:
        return self._heute if self._heute is not None else dt.date.today()

    def _stoerung(self) -> None:
        if self._szenario == "bankfehler":
            raise BankVerbindungsFehler("Die Bank ist nicht erreichbar (Mock-Szenario „bankfehler“).")
        if self._szenario == "zeitueberschreitung":
            raise BankZeitueberschreitung("Die Bank antwortet nicht rechtzeitig (Mock-Szenario "
                                          "„zeitueberschreitung“).")

    def _konten(self) -> tuple[BankKonto, ...]:
        return self._daten.konten if self._daten is not None else md.EINGEBAUTE_KONTEN

    def konten(self) -> list[BankKonto]:
        self._stoerung()
        return list(self._konten())

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date) -> list[BankUmsatz]:
        if von > bis:
            raise ValueError("von darf nicht nach bis liegen.")
        self._stoerung()
        heute = self._jetzt()
        if self._szenario == "tan_erforderlich":
            raise TanErforderlich(
                "Die Bank verlangt eine TAN-Freigabe (Mock-Szenario „tan_erforderlich“).",
                anforderung_id=f"mock-tan-{heute.isoformat()}",
                gueltig_bis=dt.datetime(heute.year, heute.month, heute.day, 23, 59, 59, tzinfo=dt.timezone.utc))
        n = md.normalisiere_iban(iban)
        if n not in {k.iban for k in self._konten()}:
            raise BankKontoUnbekannt("Das Konto ist bei der (Mock-)Bank unbekannt.")
        obergrenze = min(bis, heute)
        if self._daten is not None:
            aus = [u for u in self._daten.umsaetze if u.iban == n and von <= u.buchungstag <= obergrenze]
        elif von <= obergrenze:
            aus = md.eingebaute_umsaetze(n, von, obergrenze)
        else:
            aus = []
        aus.sort(key=lambda u: (u.buchungstag, u.umsatz_id))
        return aus


__all__ = ["MockBankPlugin"]
