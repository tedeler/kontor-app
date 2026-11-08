"""Bank- und Mail-Plugins: Auswahl per Konfiguration (plugins.md Abschnitt 5)."""

from __future__ import annotations

from ..config import KontorConfig
from ..fehler import KonfigurationsFehler
from .bank import BankPlugin
from .mail import MailPlugin


def erzeuge_bank_plugin(config: KontorConfig) -> BankPlugin:
    if config.bank_plugin == "mock":
        from .mock_bank import MockBankPlugin
        return MockBankPlugin(config.mock_daten, config.mock_szenario, config.mock_heute)
    if config.bank_plugin == "fints":
        from .fints import FintsBankPlugin
        return FintsBankPlugin()
    raise KonfigurationsFehler(f"Unbekanntes Bank-Plugin {config.bank_plugin!r}.")


def erzeuge_mail_plugin(config: KontorConfig) -> MailPlugin:
    if config.mail_plugin == "mock":
        from .mock_mail import MockMailPlugin
        return MockMailPlugin(config.mock_daten, config.mock_szenario, config.mock_heute)
    if config.mail_plugin == "imap":
        from .imap import ImapMailPlugin
        return ImapMailPlugin()
    raise KonfigurationsFehler(f"Unbekanntes Mail-Plugin {config.mail_plugin!r}.")


__all__ = ["erzeuge_bank_plugin", "erzeuge_mail_plugin"]
