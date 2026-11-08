"""Mock-Datenquellen: Datendatei (``kontor-mock-daten`` Version 1) und eingebauter Datensatz.

Der eingebaute Datensatz ist rein synthetisch (fiktive Empfänger, Test-IBANs
mit Bankleitzahl 00000000, Adressen unter ``example.invalid``) und wird
deterministisch Monat für Monat erzeugt, sodass er für jedes simulierte
„heute“ zeitlich fortlaufend Daten liefert.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
from dataclasses import dataclass

from ..config import SZENARIEN
from ..fehler import KonfigurationsFehler
from ..text import iban_normalisieren
from .bank import BankKonto, BankUmsatz
from .mail import MailNachricht

UTC = dt.timezone.utc


def szenario_pruefen(szenario: str) -> str:
    if szenario not in SZENARIEN:
        raise KonfigurationsFehler(f"Unbekanntes Mock-Szenario {szenario!r}.")
    return szenario


# ------------------------------------------------------------- Datendatei


def _fehler(text: str) -> KonfigurationsFehler:
    return KonfigurationsFehler(f"Mock-Datendatei ungültig: {text}")


def _datum(wert, feld: str, nullbar: bool = False) -> dt.date | None:
    if wert is None and nullbar:
        return None
    if not isinstance(wert, str) or len(wert) != 10:
        raise _fehler(f"{feld} muss ein Datum YYYY-MM-DD sein.")
    try:
        return dt.date.fromisoformat(wert)
    except ValueError:
        raise _fehler(f"{feld} muss ein Datum YYYY-MM-DD sein.") from None


def _zeit(wert, feld: str) -> dt.datetime:
    if not isinstance(wert, str) or not wert.endswith("Z"):
        raise _fehler(f"{feld} muss ein Zeitstempel in UTC mit Z sein.")
    try:
        z = dt.datetime.fromisoformat(wert[:-1])
    except ValueError:
        raise _fehler(f"{feld} muss ein Zeitstempel in UTC mit Z sein.") from None
    if z.tzinfo is not None:
        raise _fehler(f"{feld} muss ein Zeitstempel in UTC mit Z sein.")
    return z.replace(tzinfo=UTC)


def _text(wert, feld: str, nullbar: bool = False) -> str | None:
    if wert is None and nullbar:
        return None
    if not isinstance(wert, str):
        raise _fehler(f"{feld} muss eine Zeichenkette sein.")
    return wert


def _bool(wert, feld: str) -> bool:
    if not isinstance(wert, bool):
        raise _fehler(f"{feld} muss true oder false sein.")
    return wert


def _objekt(wert, feld: str, schluessel: tuple[str, ...]) -> dict:
    if not isinstance(wert, dict):
        raise _fehler(f"{feld} muss ein Objekt sein.")
    fehlend = [s for s in schluessel if s not in wert]
    if fehlend:
        raise _fehler(f"{feld}: Pflichtschlüssel fehlen: {', '.join(fehlend)}.")
    return wert


def _liste(wert, feld: str) -> list:
    if not isinstance(wert, list):
        raise _fehler(f"{feld} muss eine Liste sein.")
    return wert


@dataclass(frozen=True)
class MockDaten:
    konten: tuple[BankKonto, ...]
    umsaetze: tuple[BankUmsatz, ...]
    postfaecher: tuple[str, ...]
    nachrichten: tuple[MailNachricht, ...]
    pin: str | None = None   # optional bank.pin (plugins.md 7.2)
    tan: str | None = None   # optional bank.tan

    def __repr__(self) -> str:  # nie PIN oder TAN ausgeben
        return f"MockDaten(konten={len(self.konten)}, umsaetze={len(self.umsaetze)})"


def lade_datei(pfad: pathlib.Path) -> MockDaten:
    try:
        text = pathlib.Path(pfad).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise KonfigurationsFehler(f"Mock-Datendatei nicht lesbar: {pfad}") from None
    try:
        d = json.loads(text)
    except ValueError:
        raise _fehler("kein gültiges JSON.") from None
    d = _objekt(d, "Wurzel", ("format", "version", "bank", "mail"))
    if d["format"] != "kontor-mock-daten":
        raise _fehler("format muss 'kontor-mock-daten' sein.")
    if type(d["version"]) is not int or d["version"] != 1:
        raise _fehler("nur version 1 wird unterstützt.")
    bank = _objekt(d["bank"], "bank", ("konten", "umsaetze"))
    mail = _objekt(d["mail"], "mail", ("postfaecher", "nachrichten"))
    konten = []
    for i, k in enumerate(_liste(bank["konten"], "bank.konten")):
        f = f"bank.konten[{i}]"
        k = _objekt(k, f, ("iban", "bic", "name", "art", "inhaber", "waehrung"))
        konten.append(BankKonto(iban=_text(k["iban"], f + ".iban"), bic=_text(k["bic"], f + ".bic", True),
                                name=_text(k["name"], f + ".name"), art=_text(k["art"], f + ".art"),
                                inhaber=_text(k["inhaber"], f + ".inhaber"),
                                waehrung=_text(k["waehrung"], f + ".waehrung")))
    umsaetze = []
    for i, u in enumerate(_liste(bank["umsaetze"], "bank.umsaetze")):
        f = f"bank.umsaetze[{i}]"
        u = _objekt(u, f, ("umsatz_id", "iban", "buchungstag", "valuta", "betrag", "waehrung", "gegenpartei_name",
                           "gegenpartei_iban", "verwendungszweck", "vormerkung", "storno"))
        if type(u["betrag"]) is not int:
            raise _fehler(f"{f}.betrag muss eine Ganzzahl in Cent sein.")
        umsaetze.append(BankUmsatz(
            umsatz_id=_text(u["umsatz_id"], f + ".umsatz_id"), iban=_text(u["iban"], f + ".iban"),
            buchungstag=_datum(u["buchungstag"], f + ".buchungstag"),
            valuta=_datum(u["valuta"], f + ".valuta", True), betrag=u["betrag"],
            waehrung=_text(u["waehrung"], f + ".waehrung"),
            gegenpartei_name=_text(u["gegenpartei_name"], f + ".gegenpartei_name", True),
            gegenpartei_iban=_text(u["gegenpartei_iban"], f + ".gegenpartei_iban", True),
            verwendungszweck=_text(u["verwendungszweck"], f + ".verwendungszweck"),
            vormerkung=_bool(u["vormerkung"], f + ".vormerkung"), storno=_bool(u["storno"], f + ".storno")))
    postfaecher = [_text(p, f"mail.postfaecher[{i}]") for i, p in enumerate(_liste(mail["postfaecher"],
                                                                                    "mail.postfaecher"))]
    nachrichten = []
    for i, m in enumerate(_liste(mail["nachrichten"], "mail.nachrichten")):
        f = f"mail.nachrichten[{i}]"
        m = _objekt(m, f, ("nachricht_id", "postfach", "empfangen", "absender", "betreff", "text"))
        nachrichten.append(MailNachricht(
            nachricht_id=_text(m["nachricht_id"], f + ".nachricht_id"), postfach=_text(m["postfach"], f + ".postfach"),
            empfangen=_zeit(m["empfangen"], f + ".empfangen"), absender=_text(m["absender"], f + ".absender"),
            betreff=_text(m["betreff"], f + ".betreff"), text=_text(m["text"], f + ".text")))
    pin = _text(bank["pin"], "bank.pin") if "pin" in bank else None
    tan = _text(bank["tan"], "bank.tan") if "tan" in bank else None
    return MockDaten(tuple(konten), tuple(umsaetze), tuple(postfaecher), tuple(nachrichten), pin, tan)


# ----------------------------------------------------- eingebauter Datensatz

START = dt.date(2015, 1, 1)
INHABER = "Erika Mustermann (fiktiv)"


def test_iban(kontonummer: int) -> str:
    """Prüfziffergültige deutsche Test-IBAN mit Bankleitzahl 00000000."""
    bban = "00000000" + f"{kontonummer:010d}"
    zahl = int(bban + "131400")  # D=13, E=14, Prüfziffer 00
    pruef = 98 - zahl % 97
    return f"DE{pruef:02d}{bban}"


GIRO = test_iban(4711001)
TAGESGELD = test_iban(4711002)
FREMD_VERMIETER = test_iban(4711901)
POSTFAECHER = ("haushalt.eins@example.invalid", "haushalt.zwei@example.invalid")

EINGEBAUTE_KONTEN = (
    BankKonto(iban=GIRO, bic="TESTDEFFXXX", name="Girokonto (Mock)", art="girokonto", inhaber=INHABER),
    BankKonto(iban=TAGESGELD, bic=None, name="Tagesgeld (Mock)", art="sparkonto", inhaber=INHABER),
)


def _zufall(*teile: object) -> int:
    h = hashlib.sha256("|".join(map(str, teile)).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _monate(von: dt.date, bis: dt.date):
    j, m = max(von, START).year, max(von, START).month
    while (j, m) <= (bis.year, bis.month):
        yield j, m
        m += 1
        if m == 13:
            j, m = j + 1, 1


def _tag(j: int, m: int, d: int) -> dt.date:
    while True:
        try:
            return dt.date(j, m, d)
        except ValueError:
            d -= 1


def _monatsumsaetze(j: int, m: int) -> list[BankUmsatz]:
    k = f"{j:04d}{m:02d}"
    aus: list[BankUmsatz] = []

    def u(nr, iban, tag, betrag, name, gegen_iban, zweck):
        d = _tag(j, m, tag)
        aus.append(BankUmsatz(umsatz_id=f"E-{k}-{nr:02d}", iban=iban, buchungstag=d, valuta=d, betrag=betrag,
                              waehrung="EUR", gegenpartei_name=name, gegenpartei_iban=gegen_iban,
                              verwendungszweck=zweck, vormerkung=False, storno=False))

    u(1, GIRO, 1, 285000, "Arbeitgeber Beispiel GmbH (fiktiv)", None, f"Gehalt {m:02d}/{j}")
    u(2, GIRO, 3, -98000, "Wohnbau Beispiel eG (fiktiv)", FREMD_VERMIETER, f"Miete {m:02d}/{j}")
    for n, tag in enumerate((5, 12, 19, 26), start=3):
        betrag = -(1500 + _zufall("einkauf", k, n) % 9000)
        u(n, GIRO, tag, betrag, "Supermarkt Frischekorb (fiktiv)", None, f"Kartenzahlung {k}-{n}")
    u(7, GIRO, 15, -(7000 + _zufall("strom", j) % 3000), "Stadtwerke Musterstadt (fiktiv)", None,
      f"Abschlag Strom {m:02d}/{j}")
    u(8, GIRO, 28, -20000, "Erika Mustermann (fiktiv)", TAGESGELD, "Sparen")
    u(9, TAGESGELD, 28, 20000, "Erika Mustermann (fiktiv)", GIRO, "Sparen")
    if m in (3, 6, 9, 12):
        u(10, TAGESGELD, _tag(j, m, 31).day, 100 + _zufall("zins", k) % 900, "Testbank (fiktiv)", None,
          "Zinsen")
    return aus


def eingebaute_umsaetze(iban: str, von: dt.date, bis: dt.date) -> list[BankUmsatz]:
    aus = []
    for j, m in _monate(von, bis):
        aus.extend(u for u in _monatsumsaetze(j, m) if u.iban == iban and von <= u.buchungstag <= bis)
    return aus


def eingebaute_nachrichten(postfach: str, seit_datum: dt.date, bis: dt.date) -> list[MailNachricht]:
    aus = []
    nr = POSTFAECHER.index(postfach) + 1
    for j, m in _monate(seit_datum, bis):
        tag = 8 + nr * 5
        stunde = 7 + _zufall("mail", postfach, j, m) % 12
        bestellnr = 1000 + _zufall("bestellung", postfach, j, m) % 9000
        cent = 1000 + _zufall("summe", postfach, j, m) % 20000
        aus.append(MailNachricht(
            nachricht_id=f"E-{j:04d}{m:02d}-{nr}",
            postfach=postfach,
            empfangen=dt.datetime(j, m, tag, stunde, 15, tzinfo=UTC),
            absender="shop@example.invalid",
            betreff=f"Ihre Bestellung Nr. {bestellnr} – Bestätigung (Testdaten)",
            text=(f"Hallo Erika,\nvielen Dank für Ihre Bestellung Nr. {bestellnr}.\n"
                  f"Gesamtbetrag: {cent // 100},{cent % 100:02d} EUR\nIhr fiktiver Shop (Testdaten)"),
        ))
    return aus


def normalisiere_iban(iban: str) -> str:
    return iban_normalisieren(iban)
