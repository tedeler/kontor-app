"""Mock-Benachrichtigungen (benachrichtigungen.md 2) – Wegwerf-Referenz."""

from __future__ import annotations

from .benachrichtigung import BenachrichtigungsPlugin, PushNachricht


class MockBenachrichtigungsPlugin(BenachrichtigungsPlugin):
    name = "mock"
    ist_mock = True

    def __init__(self) -> None:
        self.gesendet: list[PushNachricht] = []

    def senden(self, nachricht: PushNachricht) -> None:
        self.gesendet.append(nachricht)
