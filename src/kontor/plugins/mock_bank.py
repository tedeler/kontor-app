"""Mock-Bank-Plugin: synthetische Daten aus Datendatei oder eingebautem Datensatz (plugins.md 3, 7.2).

Baut nie eine Netzwerkverbindung auf. Zeitlich fortlaufend über ein
simuliertes „heute“. Im Szenario ``tan_erforderlich`` verlangt es je Instanz
und Tag eine TAN-Freigabe; enthält die Datendatei ``bank.pin``, verlangt es
bei jedem Abruf diese PIN über ``pin_quelle``. PIN und TAN erscheinen nie in
Meldungen, Details oder ``repr()``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import hmac
import pathlib
import struct
import zlib
from collections.abc import Callable

from ..fehler import (BankKontoUnbekannt, BankPinFalsch, BankPinFehlt, BankVerbindungsFehler,
                      BankZeitueberschreitung, TanErforderlich, TanUngueltig)
from . import mock_daten as md
from .bank import BankKonto, BankPlugin, BankUmsatz, TanAntwort

VORGABE_TAN = "123456"
CHALLENGE = ("Bitte scannen Sie den QR-Code mit Ihrer (Mock-)Banking-App und geben Sie die angezeigte TAN ein. "
             "Freigabe für den Kontoabruf.")


class MockBankPlugin(BankPlugin):
    name = "mock"
    ist_mock = True

    def __init__(self, daten: pathlib.Path | None = None, szenario: str = "normal",
                 heute: dt.date | None = None, *,
                 pin_quelle: Callable[[], str | None] | None = None, verzoegerung_ms: int = 0) -> None:
        self._verzoegerung = verzoegerung_ms / 1000  # betrieb.md 5.4 (Testhilfe)
        self._szenario = md.szenario_pruefen(szenario)
        self._daten = md.lade_datei(pathlib.Path(daten)) if daten is not None else None
        self._heute = heute
        self._pin_quelle = pin_quelle
        self._freigabe: dt.date | None = None  # Tag, für den die Instanz per TAN freigegeben ist

    def __repr__(self) -> str:
        return f"MockBankPlugin(szenario={self._szenario!r})"

    __str__ = __repr__

    def setze_heute(self, heute: dt.date | None) -> None:
        self._heute = heute

    def _jetzt(self) -> dt.date:
        return self._heute if self._heute is not None else dt.date.today()

    def _pin_pruefen(self) -> None:
        soll = self._daten.pin if self._daten is not None else None
        if soll is None:
            return
        ist = self._pin_quelle() if self._pin_quelle is not None else None
        if ist is None:
            raise BankPinFehlt("Für den Bankzugang wird eine PIN benötigt; es ist keine hinterlegt.")
        if not hmac.compare_digest(str(ist).encode("utf-8"), soll.encode("utf-8")):
            raise BankPinFalsch("Die Bank hat die PIN abgelehnt.")

    def _stoerung(self) -> None:
        if self._szenario == "bankfehler":
            raise BankVerbindungsFehler("Die Bank ist nicht erreichbar (Mock-Szenario „bankfehler“).")
        if self._szenario == "zeitueberschreitung":
            raise BankZeitueberschreitung("Die Bank antwortet nicht rechtzeitig (Mock-Szenario "
                                          "„zeitueberschreitung“).")

    def _konten(self) -> tuple[BankKonto, ...]:
        return self._daten.konten if self._daten is not None else md.EINGEBAUTE_KONTEN

    def konten(self) -> list[BankKonto]:
        self._pin_pruefen()
        self._stoerung()
        return list(self._konten())

    def _tan_pruefen(self, heute: dt.date, tan: TanAntwort | None) -> None:
        if self._szenario != "tan_erforderlich" or self._freigabe == heute:
            return
        anforderung_id = "MOCK-TAN-" + heute.isoformat()
        if tan is None:
            raise TanErforderlich(
                "Die Bank verlangt eine TAN-Freigabe (Mock-Szenario „tan_erforderlich“).",
                anforderung_id=anforderung_id,
                gueltig_bis=dt.datetime(heute.year, heute.month, heute.day, 23, 59, 59, tzinfo=dt.timezone.utc),
                challenge=CHALLENGE, bild=qr_bild(anforderung_id), bild_mime_typ="image/png")
        richtig = (self._daten.tan if self._daten is not None and self._daten.tan is not None else VORGABE_TAN)
        if not (isinstance(tan, TanAntwort) and isinstance(tan.tan, str)
                and hmac.compare_digest(str(tan.anforderung_id).encode("utf-8"), anforderung_id.encode("utf-8"))
                and hmac.compare_digest(tan.tan.encode("utf-8"), richtig.encode("utf-8"))):
            raise TanUngueltig("Die TAN wurde nicht akzeptiert.")
        self._freigabe = heute

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date, *,
                 tan: TanAntwort | None = None) -> list[BankUmsatz]:
        if self._verzoegerung > 0:
            import time
            time.sleep(self._verzoegerung)
        self._pin_pruefen()
        self._stoerung()
        if von > bis:
            raise ValueError("von darf nicht nach bis liegen.")
        n = md.normalisiere_iban(iban)
        if n not in {k.iban for k in self._konten()}:
            raise BankKontoUnbekannt("Das Konto ist bei der (Mock-)Bank unbekannt.")
        heute = self._jetzt()
        self._tan_pruefen(heute, tan)
        obergrenze = min(bis, heute)
        if self._daten is not None:
            aus = []
            for i, u in enumerate(self._daten.umsaetze):
                if u.iban == n and von <= u.buchungstag <= obergrenze:
                    neu = self._daten.beitraege[i] if i < len(self._daten.beitraege) else None
                    if self._szenario == "beitragsaenderung" and neu is not None:
                        u = dataclasses.replace(u, betrag=neu)  # plugins.md 8
                    aus.append(u)
        elif von <= obergrenze:
            aus = md.eingebaute_umsaetze(n, von, obergrenze)
        else:
            aus = []
        aus.sort(key=lambda u: (u.buchungstag, u.umsatz_id))
        return aus


# ------------------------------------------------------------- QR-Bild


def _chunk(art: bytes, daten: bytes) -> bytes:
    return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)


def qr_bild(anforderung_id: str, module: int = 25, skala: int = 8, rand: int = 4) -> bytes:
    """Deterministisches PNG im Stil eines QR-Codes (nur von ``anforderung_id`` abhängig).

    Es ist kein lesbarer QR-Code, sondern ein synthetisches Bild für den Mock;
    die Kennung selbst ist darin nicht enthalten (nur ein Hash davon).
    """
    bits: list[int] = []
    zaehler = 0
    while len(bits) < module * module:
        h = hashlib.sha256(f"{zaehler}|{anforderung_id}".encode("utf-8")).digest()
        for byte in h:
            bits.extend((byte >> i) & 1 for i in range(8))
        zaehler += 1

    def finder(x: int, y: int) -> int | None:
        for ox, oy in ((0, 0), (module - 7, 0), (0, module - 7)):
            dx, dy = x - ox, y - oy
            if -1 <= dx <= 7 and -1 <= dy <= 7:
                if dx in (-1, 7) or dy in (-1, 7):
                    return 0
                if dx in (0, 6) or dy in (0, 6) or (2 <= dx <= 4 and 2 <= dy <= 4):
                    return 1
                return 0
        return None

    breite = (module + 2 * rand) * skala
    zeilen = bytearray()
    for py in range(breite):
        my = py // skala - rand
        zeilen.append(0)  # Filter „None“
        for px in range(breite):
            mx = px // skala - rand
            if 0 <= mx < module and 0 <= my < module:
                f = finder(mx, my)
                dunkel = f if f is not None else bits[my * module + mx]
            else:
                dunkel = 0
            zeilen.append(0 if dunkel else 255)
    ihdr = struct.pack(">IIBBBBB", breite, breite, 8, 0, 0, 0, 0)  # 8 Bit Graustufen
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(zeilen), 9))
            + _chunk(b"IEND", b""))


__all__ = ["MockBankPlugin"]
