"""Fehlerklassen laut python-api.md 2 und 8.1 (Wegwerf-Referenz)."""


class KontorFehler(Exception):
    code = "kontor_fehler"

    def __init__(self, meldung: str = "", **details: object) -> None:
        super().__init__(meldung)
        self.meldung = meldung
        self.details = dict(details)

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
    code = "tan_erforderlich"

    def __init__(self, meldung: str = "", *, anforderung_id: str, gueltig_bis, challenge: str,
                 bild: bytes | None = None, bild_mime_typ: str | None = None) -> None:
        super().__init__(meldung)
        self.anforderung_id, self.gueltig_bis = anforderung_id, gueltig_bis
        self.challenge, self.bild, self.bild_mime_typ = challenge, bild, bild_mime_typ


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


class KreditRateZuKlein(KontorFehler):
    code = "kredit_rate_zu_klein"


# ---------------------------------------------------------------- M6 (python-api.md 13.2)
class BankZugangGesperrt(BankFehler):
    code = "bank_zugang_gesperrt"


class MailVerbindungsFehler(MailFehler):
    code = "mail_verbindung"


class MailTokenAbgelaufen(MailFehler):
    code = "mail_token_abgelaufen"


class PostfachUnbekannt(MailFehler):
    code = "mail_postfach_unbekannt"


class MailTokenWiderrufen(MailFehler):
    code = "mail_token_widerrufen"


class MailAnmeldungFehlt(MailFehler):
    code = "mail_anmeldung_fehlt"


class MailAnmeldungAbgelehnt(MailFehler):
    code = "mail_anmeldung_abgelehnt"


class MailOAuthFehler(MailFehler):
    code = "mail_oauth_fehler"


class MailOrdnerUnbekannt(MailFehler):
    code = "mail_ordner_unbekannt"


class BenachrichtigungFehler(PluginFehler):
    code = "benachrichtigung_fehler"
