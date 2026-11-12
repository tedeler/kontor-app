"""Erkennung von Bestell- und Zahlungsmails (Feature ``mail-abgleich``, D-128).

Reine Funktionen ohne Datenbank: aus Absender, Betreff und Klartext einer gespiegelten Mail wird – wenn sie zu
einem bekannten Anbieter gehört – eine ``Erkennung`` mit Kennung, Händler, Beträgen (ganze Cent) und
Guthabenanteil. Erkannt wird nur, was eindeutig ist; im Zweifel ``None`` (die Mail bleibt im Spiegel).

Anbieter und Mailarten:

- Amazon: Bestellbestätigung (``bestellung``), Stornierung (``storno``), Erstattung (``erstattung``)
- PayPal: Zahlung an einen Händler (``zahlung``), Rückzahlung eines Händlers (``erstattung``)

Das Muster richtet sich nach typischen deutschsprachigen Mails; Kennung und Betrag sind Pflicht.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

ANBIETER = ("amazon", "paypal")
ARTEN = ("bestellung", "storno", "erstattung", "zahlung")

# Betrag im deutschen Format: 1.234,56 / 1234,56 / 12 – optional mit €/EUR davor oder danach, optional Vorzeichen.
_BETRAG = r"(?P<vz>[-−–+]?)\s*(?:€|EUR)?\s*(?P<zahl>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<cent>\d{2}))?\s*(?:€|EUR)?"
_BETRAG_RE = re.compile(_BETRAG)
_AMAZON_NR = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")
_PAYPAL_CODE = re.compile(r"Transaktions(?:code|nummer|-ID)\s*:?\s*([0-9A-Z]{17})\b", re.I)
_PAYPAL_URSPRUNG = re.compile(r"(?:Ursprünglicher?|Original-?)\s*Transaktions(?:code|nummer|-ID)\s*:?\s*([0-9A-Z]{17})\b",
                              re.I)


@dataclass(frozen=True)
class Artikel:
    name: str
    betrag: int | None  # Cent, None wenn nicht angegeben


@dataclass(frozen=True)
class Erkennung:
    anbieter: str
    art: str
    kennung: str            # Amazon-Bestellnummer bzw. PayPal-Transaktionscode
    haendler: str
    gesamt: int             # Cent, immer >= 0
    guthaben: int = 0       # Anteil aus Guthaben/Gutschein (Cent, >= 0, <= gesamt)
    bezug: str | None = None  # PayPal-Rückzahlung: ursprünglicher Transaktionscode; Amazon: Bestellnummer
    artikel: tuple[Artikel, ...] = field(default_factory=tuple)

    @property
    def bankanteil(self) -> int:
        return max(0, self.gesamt - self.guthaben)


def betrag_lesen(text: str) -> int | None:
    """Erster Betrag in ``text`` als positive Cent (Vorzeichen wird ignoriert)."""
    m = _BETRAG_RE.search(text)
    if m is None or not (m.group("cent") or re.search(r"€|EUR", m.group(0))):
        return None
    euro = int(m.group("zahl").replace(".", ""))
    return euro * 100 + int(m.group("cent") or 0)


def _zeilen(text: str) -> list[str]:
    return [z.strip() for z in text.replace("\r", "").split("\n") if z.strip()]


def _wert_nach(zeilen: list[str], muster: str) -> int | None:
    """Betrag in der Zeile mit ``muster`` (Regex, ohne Groß/Klein), sonst in der folgenden Zeile."""
    rx = re.compile(muster, re.I)
    for i, z in enumerate(zeilen):
        m = rx.search(z)
        if not m:
            continue
        rest = z[m.end():]
        wert = betrag_lesen(rest) if rest.strip(" :\t") else None
        if wert is None and i + 1 < len(zeilen):
            wert = betrag_lesen(zeilen[i + 1])
        if wert is not None:
            return wert
    return None


def _anbieter(absender: str) -> str | None:
    a = absender.casefold()
    dom = a.rsplit("@", 1)[-1].rstrip(">").strip()
    for name in ANBIETER:
        if dom == f"{name}.de" or dom.startswith(f"{name}.") or f".{name}." in f".{dom}":
            return name
    return None


def _haendler_aus_betreff(betreff: str, muster: str) -> str:
    m = re.search(muster, betreff, re.I)
    if not m:
        return ""
    return m.group(1).strip().strip("\"'„“”»«").strip()[:200]


# ================================================================ Amazon


def _amazon_artikel(zeilen: list[str]) -> tuple[Artikel, ...]:
    aus = []
    for z in zeilen:
        m = re.match(r"^(?:\d+\s*x\s+)?(.{3,}?)\s+((?:€|EUR)\s*[\d.,]+|[\d.,]+\s*(?:€|EUR))$", z)
        if not m:
            continue
        name = m.group(1).strip(" .:-")
        if re.search(r"summe|betrag|zwischen|versand|verpackung|gutschein|guthaben|steuer|mwst|rabatt|erstattung"
                     r"|bestellnr|zahlung", name, re.I):
            continue
        aus.append(Artikel(name[:200], betrag_lesen(m.group(2))))
    return tuple(aus[:50])


def _amazon(betreff: str, text: str) -> Erkennung | None:
    nr = _AMAZON_NR.search(betreff) or _AMAZON_NR.search(text)
    if nr is None:
        return None
    zeilen = _zeilen(text)
    b = betreff.casefold()
    if re.search(r"storniert|stornierung", b):
        return Erkennung("amazon", "storno", nr.group(1), "Amazon", 0)
    if re.search(r"erstattung", b):
        wert = _wert_nach(zeilen, r"(Gesamt)?erstattung(sbetrag)?|Erstattete?r? Betrag")
        if wert is None:
            return None
        return Erkennung("amazon", "erstattung", nr.group(1), "Amazon", wert, bezug=nr.group(1))
    if not re.search(r"bestell|bestätig", b):
        return None
    gesamt = _wert_nach(zeilen, r"Gesamtsumme|Gesamtbetrag|Endbetrag|Summe der Bestellung|Bestellsumme")
    if gesamt is None:
        return None
    guthaben = _wert_nach(zeilen, r"Geschenkgutschein|Gutschein(e)?\s*(eingelöst)?|Amazon-Guthaben|Guthaben") or 0
    return Erkennung("amazon", "bestellung", nr.group(1), "Amazon", gesamt, min(guthaben, gesamt),
                     artikel=_amazon_artikel(zeilen))


# ================================================================ PayPal


def _paypal_guthaben(zeilen: list[str]) -> int:
    """Anteil aus dem PayPal-Guthaben im Abschnitt „Bezahlt mit“/„Zahlungsquelle“/„Finanziert über“."""
    summe = 0
    for z in zeilen:
        if re.search(r"PayPal-?Guthaben", z, re.I):
            wert = betrag_lesen(re.split(r"PayPal-?Guthaben", z, flags=re.I)[-1])
            if wert is not None:
                summe += wert
    return summe


def _paypal(betreff: str, text: str) -> Erkennung | None:
    zeilen = _zeilen(text)
    code = _PAYPAL_CODE.search(text)
    if code is None:
        return None
    b = betreff
    if re.search(r"Rückzahlung|Erstattung", b, re.I):
        haendler = _haendler_aus_betreff(b, r"(?:Rückzahlung|Erstattung)\s+(?:von|durch)\s+(.+?)(?:\s+erhalten)?$")
        wert = _wert_nach(zeilen, r"Rückzahlungsbetrag|Erstatteter Betrag|Betrag der Rückzahlung|Gesamt|Betrag")
        if wert is None:
            return None
        u = _PAYPAL_URSPRUNG.search(text)
        guthaben = wert if re.search(r"(gutgeschrieben|überwiesen)\s+(auf|an)\s+(Ihr\s+)?PayPal-?Guthaben", text,
                                     re.I) else 0
        return Erkennung("paypal", "erstattung", code.group(1), haendler or "PayPal", wert, guthaben,
                         bezug=u.group(1) if u else None)
    if not re.search(r"Zahlung", b, re.I):
        return None
    haendler = _haendler_aus_betreff(b, r"Zahlung\s+an\s+(.+?)(?:\s+gesendet)?$")
    gesamt = _wert_nach(zeilen, r"Gesendeter Betrag|Gesamtbetrag|Gesamt|Betrag")
    if gesamt is None:
        return None
    nr = _AMAZON_NR.search(text)
    bezug = None
    m = re.search(r"(?:Bestell|Rechnungs)(?:nummer|nr\.?)\s*:?\s*([A-Za-z0-9-]{3,40})", text)
    if m:
        bezug = m.group(1)
    elif nr:
        bezug = nr.group(1)
    return Erkennung("paypal", "zahlung", code.group(1), haendler or "PayPal", gesamt,
                     min(_paypal_guthaben(zeilen), gesamt), bezug=bezug)


def erkennen(absender: str, betreff: str, text: str) -> Erkennung | None:
    """Erkennt eine Mail eines bekannten Anbieters; ``None`` wenn nicht eindeutig."""
    anbieter = _anbieter(absender or "")
    if anbieter is None:
        return None
    try:
        if anbieter == "amazon":
            return _amazon(betreff or "", text or "")
        return _paypal(betreff or "", text or "")
    except (ValueError, IndexError):
        return None


def datum_aus(empfangen: str) -> dt.date:
    """Datum (UTC) eines Zeitstempels ``YYYY-MM-DDTHH:MM:SSZ``."""
    return dt.date.fromisoformat(empfangen[:10])
