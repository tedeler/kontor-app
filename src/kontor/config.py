"""Konfiguration von Kontor (python-api.md Abschnitt 3)."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import pathlib
import re
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .fehler import KonfigurationsFehler

BANK_PLUGINS = ("mock", "fints", "aqbanking")
MAIL_PLUGINS = ("mock", "imap")
SZENARIEN = ("normal", "bankfehler", "zeitueberschreitung", "tan_erforderlich", "token_ablauf", "beitragsaenderung")

BENACHRICHTIGUNG_PLUGINS = ("keins", "mock", "ntfy")
PIN_QUELLEN = ("eingabe", "systemd-creds")
LOOPBACK = ("127.0.0.1", "::1", "localhost")
LOG_STUFEN = ("DEBUG", "INFO", "WARNING", "ERROR")
# M7 (python-api.md 14.1): Ganzzahlfelder mit Bereich
M7_GANZ = {
    "sitzung_leerlauf_sekunden": (1, 31_536_000), "sitzung_hoechstdauer_sekunden": (1, 31_536_000),
    "anmeldung_fehlversuche": (1, 100), "anmeldung_sperre_sekunden": (1, 86_400), "upload_max_mib": (1, 4096),
    "anfrage_max_kib": (16, 1_048_576), "port": (1, 65535), "beenden_frist_sekunden": (1, 600),
    "mock_verzoegerung_ms": (0, 60_000),
}
# M10 (python-api.md 16.1): Bereich der Zeitgrenze je AqBanking-Programmaufruf
AQBANKING_TIMEOUT = (1, 3600)
_THEMA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# M6 (python-api.md 13.1): Ganzzahlfelder mit Bereich (None = ohne Obergrenze)
_M6_GANZ = {
    "fints_timeout_sekunden": (1, 600), "imap_port": (1, 65535), "imap_timeout_sekunden": (1, 600),
    "oauth_timeout_sekunden": (1, 600), "oauth_refresh_gueltig_stunden": (0, 87600),
    "oauth_vorwarnung_stunden": (0, 8760), "mail_intervall_minuten": (0, None), "mail_erstabruf_tage": (0, 3650),
    "mail_ueberlappung_stunden": (0, 8760), "ntfy_timeout_sekunden": (1, 600), "zustellung_max_versuche": (1, 1000),
    "zustellung_wiederholung_minuten": (1, 1440), "tan_erinnerung_minuten": (0, 1440),
    "tan_erinnerung_anzahl": (0, 100),
}
# Zeichenkettenfelder (None erlaubt) mit Länge
_M6_TEXT = {"fints_benutzer": (1, 64), "fints_kunden_id": (1, 64), "fints_produkt_id": (1, 25),
            "oauth_client_id": (1, 256)}
# URL-Felder: (darf None sein, beliebiger http-Host erlaubt) – geheimnisse.md 7
_M6_URL = {"fints_url": (True, False), "oauth_autorisierung_url": (False, False), "oauth_token_url": (False, False),
           "oauth_widerruf_url": (False, False), "oauth_redirect_uri": (False, True), "ntfy_url": (False, False),
           "oeffentliche_url": (True, True)}


def ist_loopback(host: str | None) -> bool:
    return (host or "").lower() in LOOPBACK


def url_pruefen(wert: object, feld: str, http_ueberall: bool) -> None:
    """geheimnisse.md 7: absolute http(s)-URL mit Host; http nur auf Loopback (außer ``http_ueberall``)."""
    if not isinstance(wert, str) or not wert or any(c.isspace() for c in wert):
        raise KonfigurationsFehler(f"{feld} muss eine absolute http- oder https-URL sein.", feld=feld)
    try:
        teile = urllib.parse.urlsplit(wert)
        host = teile.hostname
        teile.port  # noqa: B018 - ungültiger Port wirft ValueError
    except ValueError:
        raise KonfigurationsFehler(f"{feld} ist keine gültige URL.", feld=feld) from None
    if teile.scheme not in ("http", "https") or not host:
        raise KonfigurationsFehler(f"{feld} muss eine absolute http- oder https-URL mit Host sein.", feld=feld)
    if teile.scheme == "http" and not http_ueberall and not ist_loopback(host):
        raise KonfigurationsFehler(f"{feld}: unverschlüsseltes http ist nur für 127.0.0.1, ::1 und localhost "
                                   "erlaubt.", feld=feld)


_WAHR = {"1", "true", "ja", "yes", "on"}
_FALSCH = {"0", "false", "nein", "no", "off", ""}


def _als_pfad(wert: object, feld: str) -> pathlib.Path:
    if isinstance(wert, pathlib.Path):
        return wert
    if isinstance(wert, (str, os.PathLike)):
        return pathlib.Path(wert)
    raise KonfigurationsFehler(f"{feld} muss ein Pfad sein.", feld=feld)


@dataclass(frozen=True)
class KontorConfig:
    datenbank: pathlib.Path
    mock_modus: bool = False
    mock_datenbank: pathlib.Path | None = None
    bank_plugin: str | None = None
    mail_plugin: str | None = None
    mock_szenario: str = "normal"
    mock_daten: pathlib.Path | None = None
    mock_heute: dt.date | None = None
    # Meilenstein 2: Synchronisation und Planer (python-api.md 8.2)
    sync_intervall_minuten: int = 0
    sync_wiederholung_minuten: int = 30
    sync_erstabruf_tage: int = 90
    sync_ueberlappung_tage: int = 14
    planer_starten: bool = True
    # Meilenstein 3: Umbuchungserkennung (python-api.md 9.1)
    umbuchung_automatisch: bool = False
    umbuchung_fenster_tage: int = 3
    # Meilenstein 4: Lernmodell bei neuen Buchungen (python-api.md 10.1)
    lernmodell_automatisch: bool = False
    # Meilenstein 5: Prüfung auf unerwartete Buchungen nach jedem Lauf (python-api.md 12.1)
    wiederkehrend_automatisch: bool = False
    # Sammelpaket (D-111): unbekannte Bankkonten automatisch als Konto anlegen (synchronisation.md 3) oder
    # überspringen und den Anwender zuordnen lassen. Vorgabe wie bisher; die ausgelieferte Umgebungsdatei schaltet ab.
    sync_konten_anlegen: bool = True
    # Meilenstein 6: echte Anbindungen und Benachrichtigungen (python-api.md 13.1). Keine Geheimnisse.
    bank_pin_quelle: str = "eingabe"
    credentials_verzeichnis: pathlib.Path | None = None
    fints_url: str | None = None
    fints_blz: str | None = None
    fints_benutzer: str | None = None
    fints_kunden_id: str | None = None
    fints_produkt_id: str | None = None
    fints_tan_verfahren: str | None = None
    fints_timeout_sekunden: int = 30
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_tls: bool = True
    imap_timeout_sekunden: int = 30
    oauth_client_id: str | None = None
    oauth_autorisierung_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_url: str = "https://oauth2.googleapis.com/token"
    oauth_widerruf_url: str = "https://oauth2.googleapis.com/revoke"
    oauth_redirect_uri: str = "http://127.0.0.1/oauth2/rueckruf"
    oauth_timeout_sekunden: int = 30
    oauth_refresh_gueltig_stunden: int = 168
    oauth_vorwarnung_stunden: int = 24
    mail_intervall_minuten: int = 0
    mail_erstabruf_tage: int = 30
    mail_ueberlappung_stunden: int = 24
    benachrichtigung_plugin: str | None = None
    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str | None = None
    ntfy_timeout_sekunden: int = 10
    zustellung_max_versuche: int = 10
    zustellung_wiederholung_minuten: int = 5
    tan_erinnerung_minuten: int = 5
    tan_erinnerung_anzahl: int = 3
    oeffentliche_url: str | None = None
    geheimnis_schluessel_datei: pathlib.Path | None = None
    tls_ca_datei: pathlib.Path | None = None
    # Meilenstein 7: Anmeldung, Härtung, Betrieb (python-api.md 14.1)
    anmeldung: bool = False
    sitzung_leerlauf_sekunden: int = 86400
    sitzung_hoechstdauer_sekunden: int = 2592000
    sitzung_cookie_secure: bool | None = None
    anmeldung_fehlversuche: int = 5
    anmeldung_sperre_sekunden: int = 60
    erlaubte_netze: tuple[str, ...] | None = None
    upload_max_mib: int = 200
    anfrage_max_kib: int = 4096
    host: str = "127.0.0.1"
    port: int = 8000
    log_stufe: str = "INFO"
    beenden_frist_sekunden: int = 20
    mock_verzoegerung_ms: int = 0
    # Meilenstein 10: AqBanking-Plugin (python-api.md 16.1). Nur Pfade und Zeitgrenze, keine Geheimnisse.
    aqbanking_verzeichnis: pathlib.Path | None = None
    aqbanking_programme: pathlib.Path | None = None
    aqbanking_timeout_sekunden: int = 120
    # Meilenstein 11: Kontostand bei der Synchronisation (python-api.md 17.1, kontostand.md)
    aqbanking_saldo: bool = False
    sync_saldo_angleichen: bool = True
    # Feature update (D-107): Suche nach neuen Releases auf GitHub, Update-Dienst
    update_pruefen: bool = False
    update_url: str = "https://api.github.com/repos/tedeler/kontor-app/releases/latest"
    update_intervall_stunden: int = 24
    update_verzeichnis: pathlib.Path | None = None

    def __post_init__(self) -> None:
        setze = object.__setattr__
        self._m6_pruefen()
        self._m7_pruefen()
        self._m10_pruefen()
        self._aktualisierung_pruefen()
        if not isinstance(self.wiederkehrend_automatisch, bool):
            raise KonfigurationsFehler("wiederkehrend_automatisch muss wahr oder falsch sein.",
                                       feld="wiederkehrend_automatisch")
        if not isinstance(self.sync_konten_anlegen, bool):
            raise KonfigurationsFehler("sync_konten_anlegen muss wahr oder falsch sein.", feld="sync_konten_anlegen")
        if not isinstance(self.lernmodell_automatisch, bool):
            raise KonfigurationsFehler("lernmodell_automatisch muss wahr oder falsch sein.",
                                       feld="lernmodell_automatisch")
        if not isinstance(self.umbuchung_automatisch, bool):
            raise KonfigurationsFehler("umbuchung_automatisch muss wahr oder falsch sein.",
                                       feld="umbuchung_automatisch")
        f = self.umbuchung_fenster_tage
        if type(f) is not int or not 0 <= f <= 366:
            raise KonfigurationsFehler("umbuchung_fenster_tage muss eine Ganzzahl von 0 bis 366 sein.",
                                       feld="umbuchung_fenster_tage")
        for feld, minimum in (("sync_intervall_minuten", 0), ("sync_wiederholung_minuten", 1),
                              ("sync_erstabruf_tage", 0), ("sync_ueberlappung_tage", 0)):
            wert = getattr(self, feld)
            if type(wert) is not int or wert < minimum:
                raise KonfigurationsFehler(f"{feld} muss eine Ganzzahl ≥ {minimum} sein.", feld=feld)
        if not isinstance(self.planer_starten, bool):
            raise KonfigurationsFehler("planer_starten muss wahr oder falsch sein.", feld="planer_starten")
        setze(self, "datenbank", _als_pfad(self.datenbank, "datenbank"))
        if self.mock_datenbank is not None:
            setze(self, "mock_datenbank", _als_pfad(self.mock_datenbank, "mock_datenbank"))
        if self.mock_daten is not None:
            setze(self, "mock_daten", _als_pfad(self.mock_daten, "mock_daten"))
        if not isinstance(self.mock_modus, bool):
            raise KonfigurationsFehler("mock_modus muss wahr oder falsch sein.", feld="mock_modus")
        if self.mock_heute is not None and (
            not isinstance(self.mock_heute, dt.date) or isinstance(self.mock_heute, dt.datetime)
        ):
            raise KonfigurationsFehler("mock_heute muss ein Datum sein.", feld="mock_heute")

        standard = "mock" if self.mock_modus else None
        bank = self.bank_plugin if self.bank_plugin is not None else (standard or "fints")
        mail = self.mail_plugin if self.mail_plugin is not None else (standard or "imap")
        if bank not in BANK_PLUGINS:
            raise KonfigurationsFehler(f"Unbekanntes Bank-Plugin {bank!r} (erlaubt: mock, fints, aqbanking).",
                                       feld="bank_plugin")
        if mail not in MAIL_PLUGINS:
            raise KonfigurationsFehler(f"Unbekanntes Mail-Plugin {mail!r} (erlaubt: mock, imap).",
                                       feld="mail_plugin")
        if self.mock_modus and (bank != "mock" or mail != "mock"):
            raise KonfigurationsFehler("Im Mock-Modus sind nur Mock-Plugins erlaubt.", feld="mock_modus")
        if not self.mock_modus and (bank == "mock" or mail == "mock"):
            raise KonfigurationsFehler(
                "Mock-Plugins sind nur im Mock-Modus erlaubt (Mock-Daten dürfen nie in die Echt-Datenbank).",
                feld="mock_modus")
        if self.mock_szenario not in SZENARIEN:
            raise KonfigurationsFehler(f"Unbekanntes Mock-Szenario {self.mock_szenario!r}.",
                                       feld="mock_szenario")
        setze(self, "bank_plugin", bank)
        setze(self, "mail_plugin", mail)
        if self.mock_modus and self.aktive_datenbank.resolve() == self.datenbank.resolve():
            raise KonfigurationsFehler("Die Mock-Datenbank darf nicht die Echt-Datenbank sein.",
                                       feld="mock_datenbank")

    def _m6_pruefen(self) -> None:
        """python-api.md 13.1: Felder von Meilenstein 6 prüfen (ohne Dateien zu lesen oder anzulegen)."""
        setze = object.__setattr__
        if self.bank_pin_quelle not in PIN_QUELLEN:
            raise KonfigurationsFehler("bank_pin_quelle muss „eingabe“ oder „systemd-creds“ sein.",
                                       feld="bank_pin_quelle")
        for feld in ("credentials_verzeichnis", "geheimnis_schluessel_datei", "tls_ca_datei"):
            wert = getattr(self, feld)
            if wert is not None:
                if isinstance(wert, str) and not wert:
                    raise KonfigurationsFehler(f"{feld} darf nicht leer sein.", feld=feld)
                setze(self, feld, _als_pfad(wert, feld))
        if self.bank_pin_quelle == "systemd-creds" and self.credentials_verzeichnis is None:
            raise KonfigurationsFehler("Für bank_pin_quelle „systemd-creds“ muss credentials_verzeichnis "
                                       "($CREDENTIALS_DIRECTORY) gesetzt sein.", feld="credentials_verzeichnis")
        for feld, (minimum, maximum) in _M6_GANZ.items():
            wert = getattr(self, feld)
            if type(wert) is not int or wert < minimum or (maximum is not None and wert > maximum):
                bereich = f"{minimum} bis {maximum}" if maximum is not None else f"≥ {minimum}"
                raise KonfigurationsFehler(f"{feld} muss eine Ganzzahl {bereich} sein.", feld=feld)
        for feld, (minimum, maximum) in _M6_TEXT.items():
            wert = getattr(self, feld)
            if wert is not None and (not isinstance(wert, str) or not minimum <= len(wert) <= maximum):
                raise KonfigurationsFehler(f"{feld} muss {minimum} bis {maximum} Zeichen lang sein.", feld=feld)
        blz = self.fints_blz
        if blz is not None and not (isinstance(blz, str) and len(blz) == 8 and blz.isascii() and blz.isdigit()):
            raise KonfigurationsFehler("fints_blz muss aus genau 8 Ziffern bestehen.", feld="fints_blz")
        tv = self.fints_tan_verfahren
        if tv is not None and not (isinstance(tv, str) and len(tv) == 3 and tv.isascii() and tv.isdigit()):
            raise KonfigurationsFehler("fints_tan_verfahren muss aus genau 3 Ziffern bestehen.",
                                       feld="fints_tan_verfahren")
        if not isinstance(self.imap_host, str) or not self.imap_host or len(self.imap_host) > 253 or any(
                c.isspace() for c in self.imap_host):
            raise KonfigurationsFehler("imap_host darf nicht leer sein.", feld="imap_host")
        if not isinstance(self.imap_tls, bool):
            raise KonfigurationsFehler("imap_tls muss wahr oder falsch sein.", feld="imap_tls")
        if not self.imap_tls and not ist_loopback(self.imap_host):
            raise KonfigurationsFehler("IMAP ohne TLS ist nur für 127.0.0.1, ::1 und localhost erlaubt.",
                                       feld="imap_tls")
        for feld, (nullbar, http_ueberall) in _M6_URL.items():
            wert = getattr(self, feld)
            if wert is None and nullbar:
                continue
            url_pruefen(wert, feld, http_ueberall)
        if self.ntfy_topic is not None and not (isinstance(self.ntfy_topic, str) and _THEMA.match(self.ntfy_topic)):
            raise KonfigurationsFehler("ntfy_topic darf nur aus 1 bis 64 Zeichen A–Z, a–z, 0–9, _ und - bestehen.",
                                       feld="ntfy_topic")
        plugin = self.benachrichtigung_plugin
        if plugin is None:
            plugin = "mock" if self.mock_modus is True else "keins"
        if plugin not in BENACHRICHTIGUNG_PLUGINS:
            raise KonfigurationsFehler("benachrichtigung_plugin muss „keins“, „mock“ oder „ntfy“ sein.",
                                       feld="benachrichtigung_plugin")
        if plugin == "mock" and self.mock_modus is not True:
            raise KonfigurationsFehler("Das Mock-Benachrichtigungs-Plugin ist nur im Mock-Modus erlaubt.",
                                       feld="benachrichtigung_plugin")
        if plugin == "ntfy" and self.ntfy_topic is None:
            raise KonfigurationsFehler("Für das Benachrichtigungs-Plugin ntfy muss ntfy_topic gesetzt sein.",
                                       feld="ntfy_topic")
        setze(self, "benachrichtigung_plugin", plugin)

    def _m7_pruefen(self) -> None:
        """python-api.md 14.1: Felder von Meilenstein 7 prüfen."""
        setze = object.__setattr__
        if not isinstance(self.anmeldung, bool):
            raise KonfigurationsFehler("anmeldung muss wahr oder falsch sein.", feld="anmeldung")
        if self.sitzung_cookie_secure is not None and not isinstance(self.sitzung_cookie_secure, bool):
            raise KonfigurationsFehler("sitzung_cookie_secure muss wahr, falsch oder None sein.",
                                       feld="sitzung_cookie_secure")
        for feld, (minimum, maximum) in M7_GANZ.items():
            wert = getattr(self, feld)
            if type(wert) is not int or not minimum <= wert <= maximum:
                raise KonfigurationsFehler(f"{feld} muss eine Ganzzahl von {minimum} bis {maximum} sein.", feld=feld)
        if not isinstance(self.host, str) or not self.host.strip() or any(c.isspace() for c in self.host):
            raise KonfigurationsFehler("host darf nicht leer sein.", feld="host")
        if not isinstance(self.log_stufe, str) or self.log_stufe not in LOG_STUFEN:
            raise KonfigurationsFehler("log_stufe muss DEBUG, INFO, WARNING oder ERROR sein.", feld="log_stufe")
        netze = self.erlaubte_netze
        if netze is not None:
            if not isinstance(netze, (list, tuple)) or not netze:
                raise KonfigurationsFehler("erlaubte_netze muss eine nicht leere Liste von CIDR-Netzen sein.",
                                           feld="erlaubte_netze")
            kanonisch = []
            for eintrag in netze:
                if not isinstance(eintrag, str):
                    raise KonfigurationsFehler("erlaubte_netze darf nur Zeichenketten enthalten.",
                                               feld="erlaubte_netze")
                try:
                    kanonisch.append(str(ipaddress.ip_network(eintrag, strict=False)))
                except ValueError:
                    raise KonfigurationsFehler("erlaubte_netze enthält ein ungültiges Netz.",
                                               feld="erlaubte_netze") from None
            setze(self, "erlaubte_netze", tuple(kanonisch))

    def _m10_pruefen(self) -> None:
        """python-api.md 16.1: Felder von Meilenstein 10 prüfen (ohne Verzeichnisse oder Programme anzusehen)."""
        setze = object.__setattr__
        for feld in ("aqbanking_verzeichnis", "aqbanking_programme"):
            wert = getattr(self, feld)
            if isinstance(wert, str) and not wert.strip():
                wert = None  # leer → None (wie in der Umgebung)
            setze(self, feld, None if wert is None else _als_pfad(wert, feld))
        for feld in ("aqbanking_saldo", "sync_saldo_angleichen"):  # M11, python-api.md 17.1
            if not isinstance(getattr(self, feld), bool):
                raise KonfigurationsFehler(f"{feld} muss wahr oder falsch sein.", feld=feld)
        t = self.aqbanking_timeout_sekunden
        if type(t) is not int or not AQBANKING_TIMEOUT[0] <= t <= AQBANKING_TIMEOUT[1]:
            raise KonfigurationsFehler("aqbanking_timeout_sekunden muss eine Ganzzahl von 1 bis 3600 sein.",
                                       feld="aqbanking_timeout_sekunden")

    def _aktualisierung_pruefen(self) -> None:
        if not isinstance(self.update_pruefen, bool):
            raise KonfigurationsFehler("update_pruefen muss wahr oder falsch sein.", feld="update_pruefen")
        if (not isinstance(self.update_intervall_stunden, int) or isinstance(self.update_intervall_stunden, bool)
                or not 1 <= self.update_intervall_stunden <= 720):
            raise KonfigurationsFehler("update_intervall_stunden muss eine Ganzzahl von 1 bis 720 sein.",
                                       feld="update_intervall_stunden")
        if not isinstance(self.update_url, str) or not self.update_url.startswith(("https://", "http://127.0.0.1")):
            raise KonfigurationsFehler("update_url muss eine HTTPS-Adresse sein.", feld="update_url")

    @property
    def standard_mock_datenbank(self) -> pathlib.Path:
        d = self.datenbank
        return d.with_name(d.stem + "-mock" + d.suffix)

    @property
    def aktive_datenbank(self) -> pathlib.Path:
        if not self.mock_modus:
            return self.datenbank
        return self.mock_datenbank if self.mock_datenbank is not None else self.standard_mock_datenbank

    @classmethod
    def from_env(cls, umgebung: Mapping[str, str] | None = None) -> "KontorConfig":
        env = os.environ if umgebung is None else umgebung

        def wert(name: str) -> str:
            return (env.get(name) or "").strip()

        datenbank = wert("KONTOR_DATENBANK")
        if not datenbank:
            raise KonfigurationsFehler("KONTOR_DATENBANK ist nicht gesetzt.", variable="KONTOR_DATENBANK")
        mock_modus = _wahrheitswert(wert("KONTOR_MOCK_MODUS"), "KONTOR_MOCK_MODUS", False)
        planer_starten = _wahrheitswert(wert("KONTOR_PLANER_STARTEN"), "KONTOR_PLANER_STARTEN", True)
        ganz = {}
        for feld in ("sync_intervall_minuten", "sync_wiederholung_minuten", "sync_erstabruf_tage",
                     "sync_ueberlappung_tage"):
            variable = "KONTOR_" + feld.upper()
            text = wert(variable)
            if text:
                if not text.isascii() or not text.isdigit():
                    raise KonfigurationsFehler(f"{variable} muss eine nicht negative Ganzzahl sein.",
                                               variable=variable)
                ganz[feld] = int(text)
        umbuchung_automatisch = _wahrheitswert(wert("KONTOR_UMBUCHUNG_AUTOMATISCH"),
                                               "KONTOR_UMBUCHUNG_AUTOMATISCH", False)
        lernmodell_automatisch = _wahrheitswert(wert("KONTOR_LERNMODELL_AUTOMATISCH"),
                                                "KONTOR_LERNMODELL_AUTOMATISCH", False)
        sync_konten_anlegen = _wahrheitswert(wert("KONTOR_SYNC_KONTEN_ANLEGEN"), "KONTOR_SYNC_KONTEN_ANLEGEN", True)
        wiederkehrend_automatisch = _wahrheitswert(wert("KONTOR_WIEDERKEHREND_AUTOMATISCH"),
                                                   "KONTOR_WIEDERKEHREND_AUTOMATISCH", False)
        text = wert("KONTOR_UMBUCHUNG_FENSTER_TAGE")
        if text:
            if not text.isascii() or not text.isdigit() or int(text) > 366:
                raise KonfigurationsFehler("KONTOR_UMBUCHUNG_FENSTER_TAGE muss eine Ganzzahl von 0 bis 366 sein.",
                                           variable="KONTOR_UMBUCHUNG_FENSTER_TAGE")
            ganz["umbuchung_fenster_tage"] = int(text)
        m6 = _m6_aus_umgebung(wert)
        m7 = _m7_aus_umgebung(wert)
        m10 = _m10_aus_umgebung(wert)
        upd = _update_aus_umgebung(wert)
        heute_text = wert("KONTOR_MOCK_HEUTE")
        mock_heute = None
        if heute_text:
            try:
                if len(heute_text) != 10:
                    raise ValueError(heute_text)
                mock_heute = dt.date.fromisoformat(heute_text)
            except ValueError:
                raise KonfigurationsFehler("KONTOR_MOCK_HEUTE muss das Format YYYY-MM-DD haben.",
                                           variable="KONTOR_MOCK_HEUTE") from None
        return cls(
            datenbank=pathlib.Path(datenbank),
            mock_modus=mock_modus,
            mock_datenbank=pathlib.Path(wert("KONTOR_MOCK_DATENBANK")) if wert("KONTOR_MOCK_DATENBANK") else None,
            bank_plugin=wert("KONTOR_BANK_PLUGIN") or None,
            mail_plugin=wert("KONTOR_MAIL_PLUGIN") or None,
            mock_szenario=wert("KONTOR_MOCK_SZENARIO") or "normal",
            mock_daten=pathlib.Path(wert("KONTOR_MOCK_DATEN")) if wert("KONTOR_MOCK_DATEN") else None,
            mock_heute=mock_heute,
            planer_starten=planer_starten,
            umbuchung_automatisch=umbuchung_automatisch,
            lernmodell_automatisch=lernmodell_automatisch,
            wiederkehrend_automatisch=wiederkehrend_automatisch,
            sync_konten_anlegen=sync_konten_anlegen,
            **ganz,
            **m6,
            **m7,
            **m10,
            **upd,
        )


def _m6_aus_umgebung(wert) -> dict:
    """python-api.md 13.1: Umgebungsvariablen von Meilenstein 6 (leer/fehlend → Vorgabe bzw. None)."""
    aus: dict = {}
    for feld in _M6_GANZ:
        variable = "KONTOR_" + feld.upper()
        text = wert(variable)
        if text:
            if not text.isascii() or not text.isdigit():
                raise KonfigurationsFehler(f"{variable} muss eine nicht negative Ganzzahl sein.", variable=variable)
            aus[feld] = int(text)
    for feld in ("bank_pin_quelle", "fints_url", "fints_blz", "fints_benutzer", "fints_kunden_id",
                 "fints_produkt_id", "fints_tan_verfahren", "imap_host", "oauth_client_id", "oauth_autorisierung_url",
                 "oauth_token_url", "oauth_widerruf_url", "oauth_redirect_uri", "benachrichtigung_plugin", "ntfy_url",
                 "ntfy_topic", "oeffentliche_url"):
        text = wert("KONTOR_" + feld.upper())
        if text:
            aus[feld] = text
    for feld, variable in (("credentials_verzeichnis", "CREDENTIALS_DIRECTORY"),
                           ("geheimnis_schluessel_datei", "KONTOR_GEHEIMNIS_SCHLUESSEL_DATEI"),
                           ("tls_ca_datei", "KONTOR_TLS_CA_DATEI")):
        text = wert(variable)
        if text:
            aus[feld] = pathlib.Path(text)
    aus["imap_tls"] = _wahrheitswert(wert("KONTOR_IMAP_TLS"), "KONTOR_IMAP_TLS", True)
    return aus


def _m10_aus_umgebung(wert: Callable[[str], str]) -> dict:
    """python-api.md 16.1: Umgebungsvariablen von Meilenstein 10 (leer/fehlend → Vorgabe bzw. None)."""
    aus: dict = {}
    for feld in ("aqbanking_verzeichnis", "aqbanking_programme"):
        text = wert("KONTOR_" + feld.upper())
        if text:
            aus[feld] = pathlib.Path(text)
    variable = "KONTOR_AQBANKING_TIMEOUT_SEKUNDEN"
    text = wert(variable)
    if text:
        if not text.isascii() or not text.isdigit():
            raise KonfigurationsFehler(f"{variable} muss eine Ganzzahl von 1 bis 3600 sein.", variable=variable)
        aus["aqbanking_timeout_sekunden"] = int(text)
    # M11 (python-api.md 17.1)
    aus["aqbanking_saldo"] = _wahrheitswert(wert("KONTOR_AQBANKING_SALDO"), "KONTOR_AQBANKING_SALDO", False)
    aus["sync_saldo_angleichen"] = _wahrheitswert(wert("KONTOR_SYNC_SALDO_ANGLEICHEN"),
                                                  "KONTOR_SYNC_SALDO_ANGLEICHEN", True)
    return aus


def _update_aus_umgebung(wert: Callable[[str], str]) -> dict:
    """Feature update (D-107): KONTOR_UPDATE_PRUEFEN, _URL, _INTERVALL_STUNDEN, _VERZEICHNIS."""
    aus: dict = {"update_pruefen": _wahrheitswert(wert("KONTOR_UPDATE_PRUEFEN"), "KONTOR_UPDATE_PRUEFEN", False)}
    if wert("KONTOR_UPDATE_URL"):
        aus["update_url"] = wert("KONTOR_UPDATE_URL")
    variable = "KONTOR_UPDATE_INTERVALL_STUNDEN"
    text = wert(variable)
    if text:
        if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 720:
            raise KonfigurationsFehler(f"{variable} muss eine Ganzzahl von 1 bis 720 sein.", variable=variable)
        aus["update_intervall_stunden"] = int(text)
    if wert("KONTOR_UPDATE_VERZEICHNIS"):
        aus["update_verzeichnis"] = pathlib.Path(wert("KONTOR_UPDATE_VERZEICHNIS"))
    return aus


def _m7_aus_umgebung(wert) -> dict:
    """python-api.md 14.1: Umgebungsvariablen von Meilenstein 7 (leer/fehlend → Vorgabe)."""
    aus: dict = {"anmeldung": _wahrheitswert(wert("KONTOR_ANMELDUNG"), "KONTOR_ANMELDUNG", False)}
    text = wert("KONTOR_SITZUNG_COOKIE_SECURE")
    if text:
        aus["sitzung_cookie_secure"] = _wahrheitswert(text, "KONTOR_SITZUNG_COOKIE_SECURE", False)
    for feld in M7_GANZ:
        variable = "KONTOR_" + feld.upper()
        text = wert(variable)
        if text:
            if not text.isascii() or not text.isdigit():
                raise KonfigurationsFehler(f"{variable} muss eine nicht negative Ganzzahl sein.", variable=variable)
            aus[feld] = int(text)
    text = wert("KONTOR_ERLAUBTE_NETZE")
    if text:
        aus["erlaubte_netze"] = tuple(t.strip() for t in text.split(","))
    text = wert("KONTOR_HOST")
    if text:
        aus["host"] = text
    text = wert("KONTOR_LOG_STUFE")
    if text:
        aus["log_stufe"] = text.upper()
    return aus


def _wahrheitswert(text: str, variable: str, leer: bool) -> bool:
    t = text.lower()
    if not t:
        return leer
    if t in _WAHR:
        return True
    if t in _FALSCH:
        return False
    raise KonfigurationsFehler(f"{variable} hat einen ungültigen Wert.", variable=variable)


__all__ = ["KontorConfig"]
