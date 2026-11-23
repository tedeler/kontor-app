"""Fiktive, prüfziffergültige Test-IBANs.

Alle IBANs verwenden die Bankleitzahl 00000000, die in Deutschland nicht
vergeben ist. Damit sind sie offensichtlich synthetisch, bestehen aber die
Prüfung nach ISO 13616 (mod 97).
"""

from __future__ import annotations

import re

FIKTIVE_BLZ = "00000000"

_MUSTER = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def _als_zahl(text: str) -> int:
    return int("".join(str(int(z, 36)) for z in text))


def normalisiere(iban: str) -> str:
    return iban.replace(" ", "").upper()


def ist_gueltig(iban: str) -> bool:
    iban = normalisiere(iban)
    if not _MUSTER.match(iban):
        return False
    return _als_zahl(iban[4:] + iban[:4]) % 97 == 1


def fiktive_iban(kontonummer: int, land: str = "DE", blz: str = FIKTIVE_BLZ) -> str:
    """Erzeugt eine gültige deutsche IBAN mit fiktiver BLZ."""
    bban = blz + f"{kontonummer:010d}"
    pruef = 98 - _als_zahl(bban + land + "00") % 97
    iban = f"{land}{pruef:02d}{bban}"
    assert ist_gueltig(iban)
    return iban


def ungueltige_iban(kontonummer: int) -> str:
    """Gleiche Form wie fiktive_iban, aber mit falscher Prüfziffer."""
    gut = fiktive_iban(kontonummer)
    falsch = (int(gut[2:4]) + 1) % 100
    if falsch < 2:
        falsch = 2
    kandidat = gut[:2] + f"{falsch:02d}" + gut[4:]
    assert not ist_gueltig(kandidat)
    return kandidat
