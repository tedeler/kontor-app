"""IMAP-Mail-Plugin (Platzhalter für Meilenstein 1).

Wählbar und erzeugbar, baut aber keine Verbindung auf; Abrufe melden
``PluginNichtVerfuegbar``. OAuth2/XOAUTH2 folgt in einem späteren Meilenstein.
"""

from __future__ import annotations

import datetime as dt

from ..fehler import PluginNichtVerfuegbar
from .mail import MailNachricht, MailPlugin


class ImapMailPlugin(MailPlugin):
    name = "imap"
    ist_mock = False

    def postfaecher(self) -> list[str]:
        raise PluginNichtVerfuegbar("Die IMAP-Anbindung ist in dieser Version noch nicht verfügbar.")

    def nachrichten(self, postfach: str, seit: dt.datetime) -> list[MailNachricht]:
        raise PluginNichtVerfuegbar("Die IMAP-Anbindung ist in dieser Version noch nicht verfügbar.")
