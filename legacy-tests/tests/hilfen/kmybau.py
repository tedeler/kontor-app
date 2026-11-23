"""Bausteine für KMyMoney-Testdateien, die Tests selbst erzeugen.

Nutzt das Modell und den Schreiber des Testdatengenerators (``generator.kmy``)
und erlaubt gezielte Eingriffe in das XML (Attribute entfernen, Werte
verfälschen), um Sonder- und Fehlerfälle unabhängig von den eingecheckten
Fixtures zu prüfen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable

from generator.kmy import KBuch, KBuchung, KKonto, KSplit, als_xml, packe_gzip  # noqa: F401 (Re-Export)
from generator.szenarien import minimal_buch

KOPF = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE KMYMONEY-FILE>\n'


def baum(xml: bytes) -> ET.Element:
    return ET.fromstring(xml)


def als_bytes(wurzel: ET.Element, kopf: str = KOPF) -> bytes:
    return (kopf + ET.tostring(wurzel, encoding="unicode") + "\n").encode("utf-8")


def minimal_baum() -> ET.Element:
    return baum(als_xml(minimal_buch()))


def veraendert(eingriff: Callable[[ET.Element], None], *, gz: bool = True) -> bytes:
    """minimal.kmy nach einem Eingriff in den XML-Baum, gzip-komprimiert."""
    w = minimal_baum()
    eingriff(w)
    roh = als_bytes(w)
    return packe_gzip(roh) if gz else roh


def konto(w: ET.Element, kid: str) -> ET.Element:
    return next(a for a in w.iter("ACCOUNT") if a.get("id") == kid)


def transaktion(w: ET.Element, n: int = 0) -> ET.Element:
    return w.findall("TRANSACTIONS/TRANSACTION")[n]


def split(w: ET.Element, t: int = 0, s: int = 0) -> ET.Element:
    return transaktion(w, t).findall("SPLITS/SPLIT")[s]


def gzip_bytes(buch: KBuch) -> bytes:
    return packe_gzip(als_xml(buch))
