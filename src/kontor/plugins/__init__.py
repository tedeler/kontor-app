"""Bank-, Mail- und Benachrichtigungs-Plugins: Auswahl per Konfiguration (plugins.md 5, 9; python-api.md 13.3)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..config import KontorConfig
from ..fehler import KonfigurationsFehler
from .bank import BankPlugin
from .mail import MailPlugin


def erzeuge_bank_plugin(config: KontorConfig, *,
                        pin_quelle: Callable[[], str | None] | None = None) -> BankPlugin:
    if config.bank_plugin == "mock":
        from .mock_bank import MockBankPlugin
        return MockBankPlugin(config.mock_daten, config.mock_szenario, config.mock_heute, pin_quelle=pin_quelle)
    if config.bank_plugin == "fints":
        from .fints import FintsBankPlugin
        return FintsBankPlugin(config, pin_quelle=pin_quelle)
    raise KonfigurationsFehler(f"Unbekanntes Bank-Plugin {config.bank_plugin!r}.")


def erzeuge_mail_plugin(config: KontorConfig, *, postfaecher: Sequence = (),
                        zugang: Callable[[str, bool], str] | None = None) -> MailPlugin:
    if config.mail_plugin == "mock":
        from .mock_mail import MockMailPlugin
        return MockMailPlugin(config.mock_daten, config.mock_szenario, config.mock_heute)
    if config.mail_plugin == "imap":
        from .imap import ImapMailPlugin
        return ImapMailPlugin(config, postfaecher=postfaecher, zugang=zugang)
    raise KonfigurationsFehler(f"Unbekanntes Mail-Plugin {config.mail_plugin!r}.")


def erzeuge_benachrichtigungs_plugin(config: KontorConfig, *, token_quelle: Callable[[], str | None] | None = None):
    """benachrichtigungen.md 2: Plugin nach ``benachrichtigung_plugin`` oder None bei ``keins``."""
    if config.benachrichtigung_plugin == "mock":
        from .mock_benachrichtigung import MockBenachrichtigungsPlugin
        return MockBenachrichtigungsPlugin()
    if config.benachrichtigung_plugin == "ntfy":
        from .ntfy import NtfyPlugin
        return NtfyPlugin(config, token_quelle=token_quelle)
    return None


__all__ = ["erzeuge_bank_plugin", "erzeuge_mail_plugin", "erzeuge_benachrichtigungs_plugin"]
