"""Mock-Mail-Plugin: synthetische Nachrichten aus Datendatei oder eingebautem Datensatz (plugins.md 3)."""

from __future__ import annotations

import datetime as dt
import pathlib

from ..fehler import MailTokenAbgelaufen, PostfachUnbekannt
from . import mock_daten as md
from .mail import MailNachricht, MailPlugin


class MockMailPlugin(MailPlugin):
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
        if self._szenario == "token_ablauf":
            raise MailTokenAbgelaufen("Der Zugriffstoken für das Postfach ist abgelaufen (Mock-Szenario "
                                      "„token_ablauf“).")

    def _postfaecher(self) -> tuple[str, ...]:
        return self._daten.postfaecher if self._daten is not None else md.POSTFAECHER

    def postfaecher(self) -> list[str]:
        self._stoerung()
        return list(self._postfaecher())

    def nachrichten(self, postfach: str, seit: dt.datetime) -> list[MailNachricht]:
        if not isinstance(seit, dt.datetime) or seit.tzinfo is None or seit.utcoffset() is None:
            raise ValueError("seit muss ein zeitzonenbehafteter Zeitpunkt sein.")
        self._stoerung()
        if postfach not in self._postfaecher():
            raise PostfachUnbekannt("Das Postfach ist unbekannt.")
        heute = self._jetzt()
        if self._daten is not None:
            quelle = [m for m in self._daten.nachrichten if m.postfach == postfach]
        else:
            seit_utc = seit.astimezone(dt.timezone.utc).date()
            quelle = md.eingebaute_nachrichten(postfach, seit_utc, heute) if seit_utc <= heute else []
        aus = [m for m in quelle if m.empfangen >= seit and m.empfangen.astimezone(dt.timezone.utc).date() <= heute]
        aus.sort(key=lambda m: (m.empfangen, m.nachricht_id))
        return aus


__all__ = ["MockMailPlugin"]
