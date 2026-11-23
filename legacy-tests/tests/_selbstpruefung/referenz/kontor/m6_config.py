"""M6-Felder der Konfiguration (python-api.md 13.1) – Wegwerf-Referenz, KEIN Anwendungscode."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .fehler import KonfigurationsFehler

LOOPBACK = ("127.0.0.1", "::1", "localhost")


@dataclass(frozen=True, kw_only=True)
class M6Felder:
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


BEREICHE = {"fints_timeout_sekunden": (1, 600), "imap_port": (1, 65535), "imap_timeout_sekunden": (1, 600),
            "oauth_timeout_sekunden": (1, 600), "oauth_refresh_gueltig_stunden": (0, 87600),
            "oauth_vorwarnung_stunden": (0, 8760), "mail_intervall_minuten": (0, 10 ** 9),
            "mail_erstabruf_tage": (0, 3650), "mail_ueberlappung_stunden": (0, 8760), "ntfy_timeout_sekunden": (1, 600),
            "zustellung_max_versuche": (1, 1000), "zustellung_wiederholung_minuten": (1, 1440),
            "tan_erinnerung_minuten": (0, 1440), "tan_erinnerung_anzahl": (0, 100)}
TEXTE = {"fints_benutzer": 64, "fints_kunden_id": 64, "fints_produkt_id": 25, "oauth_client_id": 256, "imap_host": 255}
URLS = ("fints_url", "oauth_autorisierung_url", "oauth_token_url", "oauth_widerruf_url", "oauth_redirect_uri",
        "ntfy_url", "oeffentliche_url")


def m6_pruefen(c) -> None:
    setze = object.__setattr__
    for feld in ("credentials_verzeichnis", "geheimnis_schluessel_datei", "tls_ca_datei"):
        if getattr(c, feld) is not None:
            setze(c, feld, pathlib.Path(getattr(c, feld)))
    if c.benachrichtigung_plugin is None:
        setze(c, "benachrichtigung_plugin", "mock" if c.mock_modus else "keins")
    if c.benachrichtigung_plugin not in ("keins", "mock", "ntfy"):
        raise KonfigurationsFehler("benachrichtigung_plugin ungültig")
    if c.benachrichtigung_plugin == "mock" and not c.mock_modus:
        raise KonfigurationsFehler("Mock-Benachrichtigungen nur im Mock-Modus")
    if c.benachrichtigung_plugin == "ntfy" and c.ntfy_topic is None:
        raise KonfigurationsFehler("ntfy_topic fehlt")
    if c.bank_pin_quelle not in ("eingabe", "systemd-creds"):
        raise KonfigurationsFehler("bank_pin_quelle ungültig")
    if c.bank_pin_quelle == "systemd-creds" and c.credentials_verzeichnis is None:
        raise KonfigurationsFehler("credentials_verzeichnis fehlt")
    for feld, (lo, hi) in BEREICHE.items():
        w = getattr(c, feld)
        if type(w) is not int or not lo <= w <= hi:
            raise KonfigurationsFehler(f"{feld} ungültig")
    if type(c.imap_tls) is not bool:
        raise KonfigurationsFehler("imap_tls ungültig")
    for feld, laenge in TEXTE.items():
        w = getattr(c, feld)
        if w is not None and (type(w) is not str or not 1 <= len(w) <= laenge):
            raise KonfigurationsFehler(f"{feld} ungültig")
    if c.fints_blz is not None and not re.fullmatch(r"[0-9]{8}", str(c.fints_blz)):
        raise KonfigurationsFehler("fints_blz ungültig")
    if c.fints_tan_verfahren is not None and not re.fullmatch(r"[0-9]{3}", str(c.fints_tan_verfahren)):
        raise KonfigurationsFehler("fints_tan_verfahren ungültig")
    if c.ntfy_topic is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(c.ntfy_topic)):
        raise KonfigurationsFehler("ntfy_topic ungültig")
    for feld in URLS:
        w = getattr(c, feld)
        if w is None:
            continue
        if type(w) is not str:
            raise KonfigurationsFehler(f"{feld} ungültig")
        t = urlsplit(w)
        if t.scheme not in ("http", "https") or not t.hostname:
            raise KonfigurationsFehler(f"{feld} ungültig")
        if t.scheme == "http" and feld not in ("oeffentliche_url", "oauth_redirect_uri") and t.hostname not in LOOPBACK:
            raise KonfigurationsFehler(f"{feld}: Klartext nur auf Loopback")
    if not c.imap_tls and c.imap_host not in LOOPBACK:
        raise KonfigurationsFehler("imap_tls=False nur auf Loopback")


def m6_env(text, wahr, zahl) -> dict:
    def opt(n):
        return text(n) or None

    def pfad(n):
        return pathlib.Path(text(n)) if text(n) else None
    aus = {"bank_pin_quelle": text("KONTOR_BANK_PIN_QUELLE") or "eingabe",
           "credentials_verzeichnis": pfad("CREDENTIALS_DIRECTORY"), "imap_tls": wahr("KONTOR_IMAP_TLS", True),
           "benachrichtigung_plugin": opt("KONTOR_BENACHRICHTIGUNG_PLUGIN"),
           "geheimnis_schluessel_datei": pfad("KONTOR_GEHEIMNIS_SCHLUESSEL_DATEI"),
           "tls_ca_datei": pfad("KONTOR_TLS_CA_DATEI")}
    for feld in ("fints_url", "fints_blz", "fints_benutzer", "fints_kunden_id", "fints_produkt_id",
                 "fints_tan_verfahren", "oauth_client_id", "ntfy_topic", "oeffentliche_url"):
        aus[feld] = opt("KONTOR_" + feld.upper())
    for feld in ("imap_host", "oauth_autorisierung_url", "oauth_token_url", "oauth_widerruf_url",
                 "oauth_redirect_uri", "ntfy_url"):
        aus[feld] = text("KONTOR_" + feld.upper()) or getattr(M6Felder, feld)
    for feld in BEREICHE:
        aus[feld] = zahl("KONTOR_" + feld.upper(), getattr(M6Felder, feld))
    return aus
