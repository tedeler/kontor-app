"""Mock-Benachrichtigungs-Plugin: sammelt Push-Nachrichten im Arbeitsspeicher, nie eine Verbindung."""

from __future__ import annotations

from .benachrichtigung import BenachrichtigungsPlugin, PushNachricht


class MockBenachrichtigungsPlugin(BenachrichtigungsPlugin):
    name = "mock"
    ist_mock = True

    def __init__(self) -> None:
        self.gesendet: list[PushNachricht] = []

    def __repr__(self) -> str:
        return f"MockBenachrichtigungsPlugin(gesendet={len(self.gesendet)})"

    def senden(self, nachricht: PushNachricht) -> None:
        self.gesendet.append(nachricht)


__all__ = ["MockBenachrichtigungsPlugin"]
