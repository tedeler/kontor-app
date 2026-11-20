"""Erkennung von Bestell- und Zahlungsmails (Feature ``mail-abgleich``, D-128).

Seit D-230 steht das Wissen über die Anbieter nicht mehr hier, sondern in den Beschreibungen des Pakets
``kontor.anbieter`` (``amazon.toml``, ``paypal.toml`` und Zusatzdateien); dieses Modul reicht die Erkennung nur
weiter. Reine Funktionen ohne Datenbank: aus Absender, Betreff und Klartext einer gespiegelten Mail wird – wenn sie
zu einem bekannten Anbieter gehört – eine ``Erkennung`` mit Kennung, Händler, Beträgen (ganze Cent) und
Guthabenanteil. Erkannt wird nur, was eindeutig ist; im Zweifel ``None`` (die Mail bleibt im Spiegel).
"""

from __future__ import annotations

import datetime as dt

from .anbieter import Anbieter, Artikel, Erkennung, betrag_lesen, eingebaute
from .anbieter import erkennen as _erkennen

__all__ = ["Artikel", "Erkennung", "betrag_lesen", "erkennen", "datum_aus", "ANBIETER"]

ANBIETER = tuple(a.name for a in eingebaute())


def erkennen(absender: str, betreff: str, text: str,
             anbieter: tuple[Anbieter, ...] | None = None) -> Erkennung | None:
    """Erkennt eine Mail eines bekannten Anbieters; ``None`` wenn nicht eindeutig."""
    return _erkennen(absender, betreff, text, anbieter)


def datum_aus(empfangen: str) -> dt.date:
    """Datum (UTC) eines Zeitstempels ``YYYY-MM-DDTHH:MM:SSZ``."""
    return dt.date.fromisoformat(empfangen[:10])
