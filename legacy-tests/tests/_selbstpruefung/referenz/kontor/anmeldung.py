"""WEGWERF-REFERENZ: Haushaltskonto (sicherheit.md 2, 5; python-api.md 14.2) – KEIN Anwendungscode.

Anmeldedaten liegen wie das Buch der Referenz im Arbeitsspeicher, je Datenbankpfad.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import sys
import unicodedata
from pathlib import Path

from . import mutant

N, R, P = 2 ** 15, 8, 1
ZUSTAND: dict[str, dict] = {}


def _nfc(passwort: str) -> str:
    if not isinstance(passwort, str):
        raise TypeError("Passwort muss str sein")
    return passwort if mutant("m7_hash_ohne_nfc") else unicodedata.normalize("NFC", passwort)


def pruefe_regeln(passwort: str) -> str:
    p = _nfc(passwort)
    laenge = len(passwort) if mutant("m7_passwortlaenge_roh") else len(p)
    if not 12 <= laenge <= 1024:
        raise ValueError("Das Passwort muss 12 bis 1024 Zeichen lang sein")
    return p


def _scrypt(p: str, salz: bytes, n: int, r: int, pp: int) -> bytes:
    return hashlib.scrypt(p.encode("utf-8"), salt=salz, n=n, r=r, p=pp, maxmem=64 * 1024 * 1024, dklen=32)


def passwort_hash(passwort: str) -> str:
    p = pruefe_regeln(passwort)
    salz = secrets.token_bytes(16)
    k = _scrypt(p, salz, N, R, P)
    return f"scrypt${N}${R}${P}${base64.b64encode(salz).decode()}${base64.b64encode(k).decode()}"


def _zahl(t: str) -> int | None:
    if not t.isdigit() or (len(t) > 1 and t[0] == "0"):
        return None
    return int(t)


def passwort_pruefen(passwort: str, hash_text: str) -> bool:
    if not isinstance(hash_text, str):
        raise TypeError("hash_text muss str sein")
    p = _nfc(passwort)
    teile = hash_text.split("$")
    if len(teile) != 6 or teile[0] != "scrypt":
        return False
    n, r, pp = (_zahl(t) for t in teile[1:4])
    if mutant("m7_hash_parameter_fest"):
        n, r, pp = N, R, P
    if None in (n, r, pp) or n < 2 or n & (n - 1) or n > 2 ** 20 or not 1 <= r <= 64 or not 1 <= pp <= 64:
        return False
    try:
        salz = base64.b64decode(teile[4], validate=True)
        schluessel = base64.b64decode(teile[5], validate=True)
    except (binascii.Error, ValueError):
        return False
    if len(schluessel) != 32:
        return False
    try:
        ist = _scrypt(p, salz, n, r, pp)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(ist, schluessel)


def schluessel(config) -> str:
    return str(Path(config.aktive_datenbank).resolve())


def zustand(config) -> dict:
    return ZUSTAND.setdefault(schluessel(config), {"hash": None, "sitzungen": {}, "fehlversuche": 0,
                                                   "gesperrt_bis": None})


def einrichtungsdatei(config) -> Path:
    db = Path(config.aktive_datenbank)
    return db.with_name(db.name + ".einrichtung")


def setze_hash(config, hash_text: str) -> None:
    z = zustand(config)
    z["hash"] = hash_text
    z["sitzungen"].clear()
    z["fehlversuche"] = 0
    z["gesperrt_bis"] = None
    einrichtungsdatei(config).unlink(missing_ok=True)


def passwort_setzen(config, passwort: str) -> None:
    from .buch import buch_fuer

    h = passwort_hash(passwort)
    buch_fuer(config.aktive_datenbank)
    setze_hash(config, h)


def ist_eingerichtet(config) -> bool:
    if not Path(config.aktive_datenbank).exists():
        return False
    return ZUSTAND.get(schluessel(config), {}).get("hash") is not None


def main(argv: list[str]) -> int:
    from .config import KontorConfig
    from .fehler import KonfigurationsFehler

    if argv != ["passwort-setzen"]:
        print("Aufruf: python -m kontor.anmeldung passwort-setzen", file=sys.stderr)
        return 2
    try:
        config = KontorConfig.from_env()
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    zeile = sys.stdin.readline().rstrip("\r\n")
    try:
        passwort_setzen(config, zeile)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("Passwort gesetzt.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
