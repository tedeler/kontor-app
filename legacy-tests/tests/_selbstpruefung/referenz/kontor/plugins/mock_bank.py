"""Mock-Bank-Plugin laut plugins.md 3 und 7.2 (Wegwerf-Referenz, nur Bankteil)."""

from __future__ import annotations

import datetime as dt
import json
import struct
import zlib

from .. import mutant
from ..config import SZENARIEN
from ..fehler import (BankKontoUnbekannt, BankPinFalsch, BankPinFehlt, BankVerbindungsFehler,
                      BankZeitueberschreitung, KonfigurationsFehler, TanErforderlich, TanUngueltig)
from .bank import BankKonto, BankPlugin, BankSaldo, BankUmsatz, Umsatzliste

_EINGEBAUT = {
    "konten": [{"iban": "DE02000000000000000001", "bic": None, "name": "Giro", "art": "girokonto",
                "inhaber": "Test (fiktiv)", "waehrung": "EUR"}],
    "umsaetze": [],
}


def _png(text: str) -> bytes:
    def chunk(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
            + chunk(b"tEXt", b"Kennung\x00" + text.encode()) + chunk(b"IDAT", zlib.compress(b"\x00\x00"))
            + chunk(b"IEND", b""))


class MockBankPlugin(BankPlugin):
    name = "mock"
    ist_mock = True

    def __init__(self, daten=None, szenario: str = "normal", heute=None, *, pin_quelle=None) -> None:
        if szenario not in SZENARIEN:
            raise KonfigurationsFehler("Unbekanntes Szenario")
        bank = _EINGEBAUT
        if daten is not None:
            try:
                d = json.loads(open(daten, encoding="utf-8").read())
                assert d["format"] == "kontor-mock-daten" and d["version"] == 1
                bank = d["bank"]
                assert isinstance(bank["konten"], list) and isinstance(bank["umsaetze"], list)
                for u in bank["umsaetze"]:
                    w = u.get("betrag_beitragsaenderung", 0)
                    assert type(w) is int
            except Exception as e:  # noqa: BLE001
                raise KonfigurationsFehler("Mock-Datendatei ungültig") from e
        self._konten = [BankKonto(**{k: x[k] for k in ("iban", "bic", "name", "art", "inhaber", "waehrung")})
                        for x in bank["konten"]]
        self._umsaetze = [BankUmsatz(**{**{k: u[k] for k in BankUmsatz.__dataclass_fields__},
                                        "buchungstag": dt.date.fromisoformat(u["buchungstag"]),
                                        "valuta": dt.date.fromisoformat(u["valuta"]) if u["valuta"] else None,
                                        **({"betrag": u["betrag_beitragsaenderung"]}
                                           if szenario == "beitragsaenderung" and "betrag_beitragsaenderung" in u
                                           and not mutant("beitragsaenderung_ignoriert") else {})})
                          for u in bank["umsaetze"]]
        self._anfang = bank.get("anfangssalden")  # M11, kontostand.md 1.1
        self._pin = bank.get("pin")
        self._tan = bank.get("tan", "123456")
        self._szenario, self._heute, self._pin_quelle = szenario, heute, pin_quelle
        self._freigabe: dt.date | None = None

    def __repr__(self) -> str:
        return f"MockBankPlugin(szenario={self._szenario!r})"

    def setze_heute(self, heute) -> None:
        self._heute = heute

    def _h(self) -> dt.date:
        return self._heute or dt.date.today()

    def _pruefe(self) -> None:
        if self._pin is not None:
            wert = self._pin_quelle() if self._pin_quelle else None
            if wert is None:
                raise BankPinFehlt("Für den Abruf wird die Banking-PIN benötigt")
            if wert != self._pin:
                raise BankPinFalsch("Die Bank hat die PIN abgelehnt" + (f" ({wert})" if mutant("pin_im_fehlertext")
                                                                         else ""))
        if self._szenario == "bankfehler":
            raise BankVerbindungsFehler("Bank nicht erreichbar (Mock)")
        if self._szenario == "zeitueberschreitung":
            raise BankZeitueberschreitung("Zeitüberschreitung (Mock)")

    def konten(self):
        self._pruefe()
        return list(self._konten)

    def umsaetze(self, iban, von, bis, *, tan=None):
        self._pruefe()
        if von > bis:
            raise ValueError("von > bis")
        iban = iban.replace(" ", "").upper()
        if iban not in {k.iban for k in self._konten}:
            raise BankKontoUnbekannt("Konto unbekannt")
        h = self._h()
        if self._szenario == "tan_erforderlich" and self._freigabe != h:
            aid = "MOCK-TAN-" + h.isoformat()
            if tan is None:
                raise TanErforderlich("Die Bank verlangt eine TAN", anforderung_id=aid,
                                      gueltig_bis=dt.datetime.combine(h, dt.time(23, 59, 59), dt.timezone.utc),
                                      challenge="Bitte den QR-Code mit der Banking-App scannen (Mock)",
                                      bild=_png(aid), bild_mime_typ="image/png")
            if tan.anforderung_id != aid or tan.tan != self._tan:
                raise TanUngueltig("TAN ungültig")
            self._freigabe = h
        aus = [u for u in self._umsaetze if u.iban == iban and von <= u.buchungstag <= bis and u.buchungstag <= h]
        saldo = None
        if isinstance(self._anfang, dict) and type(self._anfang.get(iban)) is int:
            betrag = self._anfang[iban] + sum(u.betrag for u in self._umsaetze if u.iban == iban
                                              and not u.vormerkung and u.buchungstag <= h)
            if mutant("saldo_mit_vormerkungen"):
                betrag += sum(u.betrag for u in self._umsaetze if u.iban == iban and u.vormerkung and u.buchungstag <= h)
            saldo = BankSaldo(iban, betrag, h)
        return Umsatzliste(sorted(aus, key=lambda u: (u.buchungstag, u.umsatz_id)), saldo=saldo)
