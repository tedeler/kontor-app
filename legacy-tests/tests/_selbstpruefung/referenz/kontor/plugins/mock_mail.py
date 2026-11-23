"""Mock-Mail-Plugin (plugins.md 3) – Wegwerf-Referenz, nur Dateidaten."""

from __future__ import annotations

import datetime as dt
import json

from ..config import SZENARIEN
from ..fehler import KonfigurationsFehler, MailTokenAbgelaufen, PostfachUnbekannt
from .mail import MailNachricht, MailPlugin

UTC = dt.timezone.utc


class MockMailPlugin(MailPlugin):
    name = "mock"
    ist_mock = True

    def __init__(self, daten=None, szenario: str = "normal", heute=None) -> None:
        if szenario not in SZENARIEN:
            raise KonfigurationsFehler("Unbekanntes Szenario")
        mail = {"postfaecher": ["haushalt.eins@example.invalid", "haushalt.zwei@example.invalid"],
                "nachrichten": []}
        if daten is not None:
            try:
                mail = json.loads(open(daten, encoding="utf-8").read())["mail"]
            except (OSError, ValueError, KeyError) as e:
                raise KonfigurationsFehler("Mock-Daten ungültig") from e
        self._postfaecher = list(mail["postfaecher"])
        self._n = [MailNachricht(n["nachricht_id"], n["postfach"],
                                 dt.datetime.fromisoformat(n["empfangen"].replace("Z", "+00:00")), n["absender"],
                                 n["betreff"], n["text"]) for n in mail["nachrichten"]]
        self._szenario, self._heute = szenario, heute

    def setze_heute(self, heute) -> None:
        self._heute = heute

    def postfaecher(self) -> list[str]:
        if self._szenario == "token_ablauf":
            raise MailTokenAbgelaufen("Token abgelaufen (Mock)")
        return list(self._postfaecher)

    def nachrichten(self, postfach, seit):
        if seit.tzinfo is None:
            raise ValueError("seit ohne Zeitzone")
        if self._szenario == "token_ablauf":
            raise MailTokenAbgelaufen("Token abgelaufen (Mock)")
        if postfach not in self._postfaecher:
            raise PostfachUnbekannt("Postfach unbekannt")
        heute = self._heute or dt.date.today()
        aus = [n for n in self._n if n.postfach == postfach and n.empfangen >= seit
               and n.empfangen.astimezone(UTC).date() <= heute]
        return sorted(aus, key=lambda n: (n.empfangen, n.nachricht_id))
