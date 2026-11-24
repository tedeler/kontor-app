"""Verlustfreie Kompression gespeicherter Mails (Feature „mail-schlank“, D-255).

Mail-Dokumente (``dokument_inhalt``) und die Rohfassung im Mail-Spiegel (``mail_nachricht.roh``) liegen mit zlib
komprimiert in der Datenbank. Die Spalte des Verfahrens sagt, wie die Bytes zu lesen sind:

- ``'zlib'``: komprimiert,
- ``''``: bewusst unkomprimiert (PDF und Bilder sind schon komprimiert),
- ``NULL``: Bestand aus der Zeit vor diesem Feature (unkomprimiert, beim nächsten Start umgestellt).

Prüfsummen (``sha256``), Größen und alles, was die Schnittstelle liefert, beziehen sich immer auf die
Originalbytes. Das Modul hat keine Abhängigkeiten innerhalb von Kontor (``db`` benutzt es bei der Migration).
"""

from __future__ import annotations

import zlib

ZLIB = "zlib"
VERFAHREN = ("", ZLIB)
_STUFE = 6


def packen(roh: bytes) -> tuple[bytes, str]:
    """Komprimiert, wenn es sich lohnt; sonst die Bytes unverändert mit Verfahren ``''``."""
    gepackt = zlib.compress(roh, _STUFE)
    if len(gepackt) < len(roh):
        return gepackt, ZLIB
    return bytes(roh), ""


def entpacken(inhalt: bytes, verfahren: str | None) -> bytes:
    """Originalbytes aus der gespeicherten Form (``NULL`` und ``''``: unverändert)."""
    if verfahren == ZLIB:
        return zlib.decompress(inhalt)
    if verfahren in (None, ""):
        return bytes(inhalt)
    raise ValueError("unbekanntes Kompressionsverfahren")
