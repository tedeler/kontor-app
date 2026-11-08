"""Fehlerklassen von Kontor (python-api.md Abschnitt 2).

Meldungen sind deutsche Texte und enthalten nie Geheimnisse (PIN, Tokens).
"""

from __future__ import annotations

import datetime as _dt


class KontorFehler(Exception):
    """Basisklasse aller fachlichen Fehler von Kontor."""

    code: str = "kontor_fehler"

    def __init__(self, meldung: str = "", **details: object) -> None:
        super().__init__(meldung)
        self.meldung: str = meldung
        self.details: dict[str, object] = dict(details)

    def __str__(self) -> str:
        return self.meldung


class KonfigurationsFehler(KontorFehler):
    code = "konfiguration_ungueltig"


class PluginFehler(KontorFehler):
    code = "plugin_fehler"


class PluginNichtVerfuegbar(PluginFehler):
    code = "plugin_nicht_verfuegbar"


class BankFehler(PluginFehler):
    code = "bank_fehler"


class BankVerbindungsFehler(BankFehler):
    code = "bank_verbindung"


class BankZeitueberschreitung(BankFehler):
    code = "bank_zeitueberschreitung"


class BankKontoUnbekannt(BankFehler):
    code = "bank_konto_unbekannt"


class TanErforderlich(BankFehler):
    """Die Bank verlangt eine TAN. Trägt Kennung und Gültigkeit der Anforderung."""

    code = "tan_erforderlich"

    def __init__(
        self,
        meldung: str = "",
        *,
        anforderung_id: str = "",
        gueltig_bis: _dt.datetime | None = None,
        challenge: str = "",
        bild: bytes | None = None,
        bild_mime_typ: str | None = None,
        **details: object,
    ) -> None:
        super().__init__(meldung, **details)
        self.anforderung_id: str = anforderung_id
        if gueltig_bis is None:
            gueltig_bis = _dt.datetime.now(_dt.timezone.utc)
        self.gueltig_bis: _dt.datetime = gueltig_bis
        self.challenge: str = challenge or meldung or "Bitte die TAN-Anforderung in der Banking-App freigeben."
        self.bild: bytes | None = bild
        self.bild_mime_typ: str | None = bild_mime_typ if bild is not None else None

    def __repr__(self) -> str:
        # Die interne Kennung und das Bild gehören nicht in Darstellungen.
        return f"{type(self).__name__}({self.meldung!r})"


class BankPinFehlt(BankFehler):
    code = "bank_pin_fehlt"


class BankPinFalsch(BankFehler):
    code = "bank_pin_falsch"


class TanUngueltig(BankFehler):
    code = "tan_ungueltig"


class TanAbgelaufen(BankFehler):
    code = "tan_abgelaufen"


class MailFehler(PluginFehler):
    code = "mail_fehler"


class MailVerbindungsFehler(MailFehler):
    code = "mail_verbindung"


class MailTokenAbgelaufen(MailFehler):
    code = "mail_token_abgelaufen"


class PostfachUnbekannt(MailFehler):
    code = "mail_postfach_unbekannt"


__all__ = [
    "KontorFehler",
    "KonfigurationsFehler",
    "PluginFehler",
    "PluginNichtVerfuegbar",
    "BankFehler",
    "BankVerbindungsFehler",
    "BankZeitueberschreitung",
    "BankKontoUnbekannt",
    "TanErforderlich",
    "BankPinFehlt",
    "BankPinFalsch",
    "TanUngueltig",
    "TanAbgelaufen",
    "MailFehler",
    "MailVerbindungsFehler",
    "MailTokenAbgelaufen",
    "PostfachUnbekannt",
]
