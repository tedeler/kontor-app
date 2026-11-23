"""Unabhängige Umsetzung der Textvergleiche aus datenmodell.md Abschnitt 1."""

import re


def norm(s: str) -> str:
    return s.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def ekey(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"[^a-z0-9]", "", norm(s))


def passend(a: str | None, b: str | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    ka, kb = ekey(a), ekey(b)
    return bool(ka) and ka == kb


def eindeutiger_name(name: str, vergeben: set[str]) -> str:
    """M32 (sammel3.md 1, E-307): hängt bei Bedarf „ ~n“ an, damit ``name.strip().casefold()`` in ``vergeben`` neu
    ist (für Zufallsbücher, deren Kontonamen je Ebene eindeutig sein müssen); trägt den Schlüssel ein."""
    kandidat, n = name, 1
    while kandidat.strip().casefold() in vergeben:
        n += 1
        kandidat = f"{name} ~{n}"
    vergeben.add(kandidat.strip().casefold())
    return kandidat
