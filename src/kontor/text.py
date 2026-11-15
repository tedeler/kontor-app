"""Textvergleiche (datenmodell.md Abschnitt 1) und IBAN-Regeln (Abschnitt 2)."""

from __future__ import annotations

import re

_NICHT_ALNUM = re.compile(r"[^a-z0-9]")
_IBAN_MUSTER = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def norm(s: str | None) -> str:
    """casefold, danach ä→ae, ö→oe, ü→ue (ß wird durch casefold zu ss)."""
    if s is None:
        return ""
    return s.casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def ekey(s: str | None) -> str | None:
    if s is None:
        return None
    return _NICHT_ALNUM.sub("", norm(s))


def woerter(s: str | None, mindest: int = 4) -> list[str]:
    """Normierte Wörter ab ``mindest`` Buchstaben, reine Ziffernfolgen ausgelassen, ohne Doppelte."""
    aus: list[str] = []
    for w in _NICHT_ALNUM.split(norm(s)):
        if len(w) < mindest or w.isdigit() or w in aus:
            continue
        aus.append(w)
    return aus


def namen_aehnlich(a: str | None, b: str | None) -> bool:
    """Empfängernamen gelten als ähnlich, wenn ihr Vergleichsschlüssel gleich ist oder der gemeinsame
    Anfang mindestens vier Zeichen lang ist (D-158)."""
    ka, kb = ekey(a) or "", ekey(b) or ""
    if not ka or not kb:
        return False
    n = 0
    for x, y in zip(ka, kb):
        if x != y:
            break
        n += 1
    return n >= 4


def passend(a: str | None, b: str | None) -> bool:
    """Zwei Empfänger sind passend, wenn beide fehlen oder ekey gleich und nicht leer ist."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    ka, kb = ekey(a), ekey(b)
    return bool(ka) and ka == kb


def iban_normalisieren(s: str) -> str:
    return "".join(s.split()).upper()


def iban_gueltig(n: str) -> bool:
    """n muss bereits normalisiert sein."""
    if not _IBAN_MUSTER.match(n):
        return False
    umgestellt = n[4:] + n[:4]
    ziffern = "".join(str(int(c, 36)) for c in umgestellt)
    return int(ziffern) % 97 == 1


def euro(cent: int) -> str:
    """Betrag in Cent als deutscher Eurotext (nur Ganzzahlarithmetik)."""
    vz = "−" if cent < 0 else ""
    e, c = divmod(abs(cent), 100)
    return f"{vz}{e:,}".replace(",", ".") + f",{c:02d} €"
