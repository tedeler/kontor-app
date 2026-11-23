"""Plugins (Wegwerf-Referenz): Bank (Mock, FinTS), Mail (Mock, IMAP), Benachrichtigung (Mock, ntfy)."""

from __future__ import annotations

from .bank import BankPlugin
from .fints import FintsBankPlugin
from .mock_bank import MockBankPlugin


def erzeuge_bank_plugin(config, *, pin_quelle=None) -> BankPlugin:
    if config.bank_plugin == "mock":
        return MockBankPlugin(config.mock_daten, config.mock_szenario, config.mock_heute, pin_quelle=pin_quelle)
    return FintsBankPlugin(config, pin_quelle=pin_quelle)


def erzeuge_mail_plugin(config, *, postfaecher=(), zugang=None):
    if config.mail_plugin == "mock":
        from .mock_mail import MockMailPlugin  # noqa: PLC0415
        return MockMailPlugin(config.mock_daten, config.mock_szenario, config.mock_heute)
    from .imap import ImapMailPlugin  # noqa: PLC0415
    return ImapMailPlugin(config, postfaecher=postfaecher, zugang=zugang)


def erzeuge_benachrichtigungs_plugin(config, *, token_quelle=None):
    if config.benachrichtigung_plugin == "keins":
        return None
    if config.benachrichtigung_plugin == "mock":
        from .mock_benachrichtigung import MockBenachrichtigungsPlugin  # noqa: PLC0415
        return MockBenachrichtigungsPlugin()
    from .ntfy import NtfyPlugin  # noqa: PLC0415
    return NtfyPlugin(config, token_quelle=token_quelle)
