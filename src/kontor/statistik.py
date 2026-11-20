"""Robuste Kennzahlen (Median, MAD, robustes z) für Monatsbericht, Berichte und Verdachtsprüfung.

Die experimentelle Seite „Statistische Analyse“ (D-145) und ``GET /api/statistik`` sind entfallen (D-221); ihre
Aussagen stehen in den Berichten. Ganze Cent, keine Gleitkommazahlen.
"""

from __future__ import annotations

AUSREISSER_HUNDERTSTEL = 350  # robustes z von 3,50
_ROBUST_Z = 14826  # 1,4826 · 10000
_ROBUST_N = 10000


def _median(werte: list[int]) -> int:
    s = sorted(werte)
    n = len(s)
    if n == 0:
        return 0
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) // 2


def _mad(werte: list[int], mitte: int) -> int:
    return _median([abs(v - mitte) for v in werte]) if werte else 0


def _z_hundertstel(wert: int, mitte: int, mad: int) -> int | None:
    """Robustes z in Hundertsteln. ``None``, wenn die MAD 0 ist und der Wert abweicht."""
    if mad == 0:
        return 0 if wert == mitte else None
    skala = mad * _ROBUST_Z // _ROBUST_N
    if skala == 0:
        return 0 if wert == mitte else None
    return abs(wert - mitte) * 100 // skala
