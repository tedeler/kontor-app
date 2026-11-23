"""IBAN-Hilfen der Wegwerf-Referenz."""

import re


def norm(t: str) -> str:
    return t.replace(" ", "").upper()


def gueltig(t: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", t):
        return False
    return int("".join(str(int(z, 36)) for z in t[4:] + t[:4])) % 97 == 1
