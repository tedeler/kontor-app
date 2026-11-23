"""M7-Felder der Konfiguration (python-api.md 14.1) – Wegwerf-Referenz, KEIN Anwendungscode."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from .fehler import KonfigurationsFehler


@dataclass(frozen=True, kw_only=True)
class M7Felder:
    anmeldung: bool = False
    sitzung_leerlauf_sekunden: int = 86400
    sitzung_hoechstdauer_sekunden: int = 2592000
    sitzung_cookie_secure: bool | None = None
    anmeldung_fehlversuche: int = 5
    anmeldung_sperre_sekunden: int = 60
    erlaubte_netze: tuple | None = None
    upload_max_mib: int = 200
    anfrage_max_kib: int = 4096
    host: str = "127.0.0.1"
    port: int = 8000
    log_stufe: str = "INFO"
    beenden_frist_sekunden: int = 20
    mock_verzoegerung_ms: int = 0


BEREICHE = {"sitzung_leerlauf_sekunden": (1, 31_536_000), "sitzung_hoechstdauer_sekunden": (1, 31_536_000),
            "anmeldung_fehlversuche": (1, 100), "anmeldung_sperre_sekunden": (1, 86_400),
            "upload_max_mib": (1, 4096), "anfrage_max_kib": (16, 1_048_576), "port": (1, 65535),
            "beenden_frist_sekunden": (1, 600), "mock_verzoegerung_ms": (0, 60_000)}
STUFEN = ("DEBUG", "INFO", "WARNING", "ERROR")


def m7_pruefen(c) -> None:
    if type(c.anmeldung) is not bool:
        raise KonfigurationsFehler("anmeldung ungültig")
    if c.sitzung_cookie_secure is not None and type(c.sitzung_cookie_secure) is not bool:
        raise KonfigurationsFehler("sitzung_cookie_secure ungültig")
    for feld, (lo, hi) in BEREICHE.items():
        w = getattr(c, feld)
        if type(w) is not int or not lo <= w <= hi:
            raise KonfigurationsFehler(f"{feld} ungültig")
    if type(c.host) is not str or not c.host:
        raise KonfigurationsFehler("host ungültig")
    if type(c.log_stufe) is not str or c.log_stufe not in STUFEN:
        raise KonfigurationsFehler("log_stufe ungültig")
    if c.erlaubte_netze is not None:
        if not isinstance(c.erlaubte_netze, (list, tuple)) or not c.erlaubte_netze:
            raise KonfigurationsFehler("erlaubte_netze ungültig")
        aus = []
        for n in c.erlaubte_netze:
            if not isinstance(n, str):
                raise KonfigurationsFehler("erlaubte_netze ungültig")
            try:
                aus.append(str(ipaddress.ip_network(n.strip(), strict=False)))
            except ValueError as e:
                raise KonfigurationsFehler("erlaubte_netze ungültig") from e
        object.__setattr__(c, "erlaubte_netze", tuple(aus))


def m7_env(text, wahr, zahl) -> dict:
    secure = text("KONTOR_SITZUNG_COOKIE_SECURE")
    netze = text("KONTOR_ERLAUBTE_NETZE")
    return dict(
        anmeldung=wahr("KONTOR_ANMELDUNG", False),
        sitzung_leerlauf_sekunden=zahl("KONTOR_SITZUNG_LEERLAUF_SEKUNDEN", 86400),
        sitzung_hoechstdauer_sekunden=zahl("KONTOR_SITZUNG_HOECHSTDAUER_SEKUNDEN", 2592000),
        sitzung_cookie_secure=wahr("KONTOR_SITZUNG_COOKIE_SECURE", None) if secure else None,
        anmeldung_fehlversuche=zahl("KONTOR_ANMELDUNG_FEHLVERSUCHE", 5),
        anmeldung_sperre_sekunden=zahl("KONTOR_ANMELDUNG_SPERRE_SEKUNDEN", 60),
        erlaubte_netze=tuple(t.strip() for t in netze.split(",")) if netze else None,
        upload_max_mib=zahl("KONTOR_UPLOAD_MAX_MIB", 200),
        anfrage_max_kib=zahl("KONTOR_ANFRAGE_MAX_KIB", 4096),
        host=text("KONTOR_HOST") or "127.0.0.1",
        port=zahl("KONTOR_PORT", 8000),
        log_stufe=(text("KONTOR_LOG_STUFE") or "INFO").upper(),
        beenden_frist_sekunden=zahl("KONTOR_BEENDEN_FRIST_SEKUNDEN", 20),
        mock_verzoegerung_ms=zahl("KONTOR_MOCK_VERZOEGERUNG_MS", 0),
    )
