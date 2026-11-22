"""Echtes FinTS-Bank-Plugin über python-fints (fints.md, Meilenstein 6). Nur lesend.

Ablauf je Aufruf von ``konten``/``umsaetze``: Prüfungen ohne Verbindung (Konfiguration, Argumente, Freigabe,
PIN), dann ein FinTS-Dialog (Synchronisierung beim ersten Mal, Dialoginitialisierung, HKSPA, Umsatzabruf mit
Aufsetzpunkten, Dialogende). Verlangt die Bank eine TAN (0030), bleibt der Dialog in dieser Plugin-Instanz
offen; ``umsaetze(..., tan=TanAntwort(...))`` sendet die TAN im selben Dialog (HKTAN Prozess 2).

Das Plugin sendet ausschließlich lesende Segmentarten (fints.md 3.7); Aufträge wie Überweisungen gibt es hier
nicht. PIN, TAN und Benutzerkennung erscheinen nie in Meldungen, ``details``, ``repr()`` oder Protokollen: Die
Verbindung protokolliert nichts, der Logger ``fints`` wird beim Laden dieses Moduls stillgelegt (3.8).
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import hashlib
import http.client
import logging
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from ..config import KontorConfig
from ..fehler import (BankFehler, BankKontoUnbekannt, BankPinFalsch, BankPinFehlt, BankVerbindungsFehler,
                      BankZeitueberschreitung, BankZugangGesperrt, KontorFehler, PluginNichtVerfuegbar,
                      TanAbgelaufen, TanErforderlich, TanUngueltig)
from ..netz import http_anfrage
from ..text import iban_gueltig, iban_normalisieren
from .bank import BankKonto, BankPlugin, BankSaldo, BankUmsatz, TanAntwort, Umsatzliste

BERLIN = ZoneInfo("Europe/Berlin")
UTC = dt.timezone.utc
CAMT_052 = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"
# D-197: lesbare camt.052-Versionen in der Reihenfolge der Bevorzugung (zuerst .08 nach fints.md 3.3, sonst die
# höchste von der Bank angebotene; die comdirect bietet z. B. nur camt.052.001.02 an).
CAMT_FORMATE = tuple(f"urn:iso:std:iso:20022:tech:xsd:camt.052.001.{n:02d}" for n in (8, 7, 6, 5, 4, 3, 2))
PIN_CODES = ("9931", "9340", "9910", "9930", "9942")


def bibliothek_stilllegen() -> None:
    """fints.md 3.8: python-fints schreibt auf DEBUG ganze Nachrichten (mit TAN) – nie weitergeben.

    Der Logger ``fints`` (und damit alle ``fints.*``) gibt keine Einträge an die Wurzel weiter und hat nur einen
    ``NullHandler``; das gilt unabhängig von der eingestellten Stufe."""
    lg = logging.getLogger("fints")
    lg.propagate = False
    if not any(isinstance(h, logging.NullHandler) for h in lg.handlers):
        lg.addHandler(logging.NullHandler())


bibliothek_stilllegen()


def _art(kontoart: int | None) -> str | None:
    if kontoart is None:
        return None
    if 1 <= kontoart <= 9:
        return "girokonto"
    if 10 <= kontoart <= 29:
        return "sparkonto"
    if 40 <= kontoart <= 59:
        return "kreditkonto"
    return None


# ================================================================ Formate (fints.md 3.4)


class _Unlesbar(ValueError):
    """Ein Feld der Umsatzdaten hat eine unerwartete Form. ``form`` beschreibt sie ohne den Wert (Ziffern als
    ``9``, Buchstaben als ``a``), damit das Diagnoseprotokoll die Ursache nennen kann (D-203)."""

    def __init__(self, feld: str, text: str | None) -> None:
        super().__init__(feld)
        self.feld = feld
        self.form = "".join("9" if ch.isdigit() else "a" if ch.isalpha() else ch if ch in "-+.:,TZ /" else "?"
                            for ch in (text or "").strip()[:32])


_BETRAG = re.compile(r"^\s*([0-9]*)(?:\.([0-9]*))?\s*$")
_DATUM = re.compile(r"^\s*([0-9]{4})-([0-9]{2})-([0-9]{2})(?:$|[T+\-Z\s])")


def _cent_punkt(text: str) -> int:
    m = _BETRAG.match(text or "")
    if m is None or not (m[1] or m[2]):
        raise _Unlesbar("Amt", text)
    return int(m[1] or "0") * 100 + int(((m[2] or "") + "00")[:2])


def _camt_datum(e: ET.Element | None, feld: str) -> dt.date | None:
    """Datum aus ``Dt`` oder ``DtTm``; Zeitzonen- und Zeitanteile (``2024-06-03+02:00``, wie sie z. B. die
    comdirect liefert) werden nicht ausgewertet (D-204)."""
    text = _text(e, feld, "Dt") or _text(e, feld, "DtTm")
    if not text or not text.strip():
        return None
    m = _DATUM.match(text)
    try:
        if m is None:
            raise ValueError
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        raise _Unlesbar(feld, text) from None


def _cent_komma(text: str) -> int:
    ganz, _, rest = text.partition(",")
    return int(ganz or "0") * 100 + int((rest + "00")[:2])


def _iban_oder_none(text: str | None) -> str | None:
    if not text:
        return None
    n = iban_normalisieren(text)
    return n if iban_gueltig(n) else None


def _lokal(e: ET.Element) -> str:
    return e.tag.rsplit("}", 1)[-1]


def _kind(e: ET.Element | None, *pfad: str) -> ET.Element | None:
    for name in pfad:
        if e is None:
            return None
        e = next((k for k in e if _lokal(k) == name), None)
    return e


def _text(e: ET.Element | None, *pfad: str) -> str | None:
    k = _kind(e, *pfad)
    return k.text if k is not None else None


@dataclass
class _Roh:
    """Abgebildeter Umsatz vor der Vergabe der Hash-Kennung."""
    buchungstag: dt.date
    valuta: dt.date | None
    betrag: int
    gegenpartei_name: str | None
    gegenpartei_iban: str | None
    verwendungszweck: str
    vormerkung: bool
    storno: bool
    referenz: str | None = None


def camt_eintraege(dokument: bytes) -> list[_Roh]:
    aus: list[_Roh] = []
    wurzel = ET.fromstring(dokument)
    for ntry in wurzel.iter():
        if _lokal(ntry) != "Ntry":
            continue
        amt = _kind(ntry, "Amt")
        if amt is None or amt.get("Ccy") != "EUR" or not (amt.text or "").strip():
            continue
        cent = _cent_punkt(amt.text)
        ind = (_text(ntry, "CdtDbtInd") or "").strip()
        if ind not in ("CRDT", "DBIT"):
            continue
        storno = (_text(ntry, "RvslInd") or "").strip() == "true"
        sts = (_text(ntry, "Sts", "Cd") or _text(ntry, "Sts") or "").strip()
        if sts not in ("BOOK", "PDNG"):
            continue
        valuta = _camt_datum(ntry, "ValDt")
        bt = _camt_datum(ntry, "BookgDt") or valuta
        if bt is None:
            continue
        seite = ind if not storno else ("CRDT" if ind == "DBIT" else "DBIT")
        partei, konto = ("Cdtr", "CdtrAcct") if seite == "DBIT" else ("Dbtr", "DbtrAcct")
        tx = _kind(ntry, "NtryDtls", "TxDtls")
        pt = _kind(tx, "RltdPties")
        name = _text(pt, partei, "Pty", "Nm") or _text(pt, partei, "Nm") or None
        rmt = _kind(tx, "RmtInf")
        zweck = "".join((k.text or "") for k in (rmt if rmt is not None else []) if _lokal(k) == "Ustrd")
        ref = (_text(ntry, "AcctSvcrRef") or "").strip()
        aus.append(_Roh(bt, valuta, cent if ind == "CRDT" else -cent, name, _iban_oder_none(_text(pt, konto, "Id", "IBAN")),
                        zweck, sts == "PDNG", storno, ref or None))
    return aus


_FELD = re.compile(r"^:([0-9]{2}[A-Z]?):(.*)$")
_ZEILE61 = re.compile(r"^([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{4})?(RC|RD|C|D)[A-Z]?([0-9]+,[0-9]{0,2})")


def mt940_eintraege(text: str) -> list[_Roh]:
    felder: list[list[str]] = []
    for zeile in text.replace("\r\n", "\n").split("\n"):
        m = _FELD.match(zeile)
        if m:
            felder.append([m[1], m[2]])
        elif zeile in ("-", ""):
            continue
        elif felder:
            felder[-1][1] += zeile  # Zeilenumbrüche innerhalb eines Feldes gehören nicht zum Inhalt
    aus: list[_Roh] = []
    i = 0
    while i < len(felder):
        tag, wert = felder[i]
        if tag != "61":
            i += 1
            continue
        m = _ZEILE61.match(wert)
        if m is None:
            raise BankFehler("Die Bank hat einen unlesbaren MT940-Umsatz geliefert.")
        valuta = dt.date(2000 + int(m[1]), int(m[2]), int(m[3]))
        if m[4]:
            bt = dt.date(valuta.year, int(m[4][:2]), int(m[4][2:]))
            if (bt - valuta).days > 180:
                bt = bt.replace(year=bt.year - 1)
            elif (valuta - bt).days > 180:
                bt = bt.replace(year=bt.year + 1)
        else:
            bt = valuta
        cent = _cent_komma(m[6])
        vorzeichen = {"C": 1, "D": -1, "RC": -1, "RD": 1}[m[5]]
        unter: list[tuple[str, str]] = []
        if i + 1 < len(felder) and felder[i + 1][0] == "86":
            unter = re.findall(r"\?([0-9]{2})([^?]*)", felder[i + 1][1])
            i += 1
        zweck = "".join(v for k, v in unter if 20 <= int(k) <= 29 or 60 <= int(k) <= 63)
        name = "".join(v for k, v in unter if k in ("32", "33")) or None
        konto = next((v for k, v in unter if k == "31"), None)
        aus.append(_Roh(bt, valuta, vorzeichen * cent, name, _iban_oder_none(konto), zweck, False,
                        m[5] in ("RC", "RD")))
        i += 1
    return aus


def kennungen_vergeben(iban: str, eintraege: list[_Roh]) -> list[BankUmsatz]:
    """``ref:<AcctSvcrRef>`` oder Hash-Kennung mit laufender Nummer je Abruf (fints.md 3.4, E-114)."""
    gesehen: dict[str, int] = {}
    aus = []
    for r in eintraege:
        if r.referenz:
            uid = "ref:" + r.referenz
        else:
            teile = [r.buchungstag.isoformat(), r.valuta.isoformat() if r.valuta else "", str(r.betrag),
                     r.gegenpartei_iban or "", r.gegenpartei_name or "", r.verwendungszweck, "S" if r.storno else ""]
            h = hashlib.sha256("|".join(teile).encode("utf-8")).hexdigest()[:16]
            gesehen[h] = gesehen.get(h, 0) + 1
            uid = f"h:{h}:{gesehen[h]}"
        aus.append(BankUmsatz(uid, iban, r.buchungstag, r.valuta, r.betrag, "EUR", r.gegenpartei_name,
                              r.gegenpartei_iban, r.verwendungszweck, r.vormerkung, r.storno))
    return aus


# ================================================================ Verbindung


class _Verbindung:
    """Ersatz für ``FinTSHTTPSConnection``: Zeitgrenze je Anfrage, eigene Vertrauensanker, keine Umleitungen,
    keine Proxys, kein Protokoll der Nachrichten."""

    def __init__(self, config: KontorConfig, diagnose=None) -> None:
        self._config = config
        self._diagnose = diagnose
        self.letzte = None

    def _diag(self, text: str) -> None:
        if self._diagnose is not None:
            self._diagnose.eintrag(text)

    def __repr__(self) -> str:
        return "_Verbindung()"

    def send(self, msg):
        from fints.message import FinTSInstituteMessage
        c = self._config
        daten = base64.b64encode(msg.render_bytes())
        if self._diagnose is not None:   # D-203: nur Strukturangaben, nie die Nachricht selbst
            self._diagnose.nachricht("→ Bank", msg)
        beginn = time.monotonic()
        try:
            antwort = http_anfrage(c, "POST", c.fints_url, daten, {"Content-Type": "text/plain"},
                                   c.fints_timeout_sekunden)
        except TimeoutError:
            self._diag(f"✗ keine Antwort innerhalb von {c.fints_timeout_sekunden} s")
            raise BankZeitueberschreitung("Die Bank hat nicht rechtzeitig geantwortet.") from None
        except (OSError, http.client.HTTPException) as e:
            self._diag(f"✗ Verbindung fehlgeschlagen ({type(e).__name__})")
            raise BankVerbindungsFehler("Die Verbindung zur Bank ist fehlgeschlagen.") from None
        self._diag(f"← HTTP {antwort.status}, {len(antwort.koerper)} Bytes nach "
                   f"{int((time.monotonic() - beginn) * 1000)} ms")
        if not 200 <= antwort.status <= 299:
            raise BankVerbindungsFehler(f"Die Bank hat mit HTTP-Status {antwort.status} geantwortet.",
                                        status=antwort.status)
        try:
            roh = base64.b64decode(antwort.koerper.decode("iso-8859-1"), validate=False)
            nachricht = FinTSInstituteMessage(segments=roh)
        except Exception:  # noqa: BLE001 - jede unlesbare Antwort
            self._diag("✗ Antwort der Bank ist unlesbar (kein FinTS)")
            raise BankVerbindungsFehler("Die Antwort der Bank ist unlesbar.") from None
        if self._diagnose is not None:
            self._diagnose.nachricht("← Bank", nachricht)
        self.letzte = nachricht
        return nachricht


def _codes(nachricht, segment=None) -> list[str]:
    """Rückmeldecodes zur Nachricht (HIRMG) bzw. zu einem Segment (HIRMS)."""
    from fints.segments.dialog import HIRMG2
    if nachricht is None:
        return []
    if segment is None:
        return [str(r.code) for s in nachricht.find_segments(HIRMG2) for r in s.responses]
    return [str(r.code) for r in nachricht.responses(segment)]


def _alle_codes(nachricht) -> list[str]:
    from fints.segments.dialog import HIRMG2, HIRMS2
    if nachricht is None:
        return []
    return [str(r.code) for s in list(nachricht.find_segments(HIRMG2)) + list(nachricht.find_segments(HIRMS2))
            for r in s.responses]


def _fehler_aus_codes(codes: list[str]) -> None:
    """fints.md 3.6 für eine Liste von Rückmeldungen (Reihenfolge der Bank)."""
    for c in codes:
        if c in PIN_CODES:
            raise BankPinFalsch("Die Bank hat die PIN abgelehnt.")
        if c == "3938":
            raise BankZugangGesperrt("Der Bankzugang ist gesperrt. Bitte bei der Bank entsperren lassen.")
    for c in codes:
        if c == "9210":
            raise BankKontoUnbekannt("Das Konto ist der Bank unbekannt.")
    for c in codes:
        if c.startswith("9") and c != "9050":
            raise BankFehler(f"Die Bank hat den Auftrag abgelehnt (Rückmeldung {c}).", rueckmeldung=c)
    for c in codes:
        if c.startswith("9"):
            raise BankFehler(f"Die Bank hat den Auftrag abgelehnt (Rückmeldung {c}).", rueckmeldung=c)


@dataclass
class _Dialog:
    client: object
    dialog: object
    verbindung: _Verbindung
    beginn: object = None   # HITAN der Dialoginitialisierung, solange deren TAN aussteht (D-198)

    def __repr__(self) -> str:
        return "_Dialog()"


@dataclass
class _Offen:
    """Offene TAN-Anforderung: Dialog, ursprünglicher Auftrag und schon gelieferte Seiten (nur Arbeitsspeicher)."""
    d: _Dialog
    iban: str
    von: dt.date
    bis: dt.date
    konto: object
    segment: object
    hitan: object
    camt: bool
    seiten: list = field(default_factory=list)
    beginn: bool = False    # TAN zur Dialoginitialisierung: der eigentliche Auftrag folgt erst danach (D-198)

    def __repr__(self) -> str:
        return f"_Offen(von={self.von}, bis={self.bis})"


# ================================================================ Plugin

_KONTEN = ""  # „Konto“ einer offenen TAN-Anforderung, die zum Kontenabruf gehört


def _verfahren_der_bankparameter(client) -> dict:
    """Alle Zwei-Schritt-Verfahren aus den Bankparametern (HITANS), unabhängig von der Liste der erlaubten."""
    from fints.client import IMPLEMENTED_HKTAN_VERSIONS
    aus: dict = {}
    for version in sorted(IMPLEMENTED_HKTAN_VERSIONS.keys()):
        for seg in client.bpd.find_segments("HITANS", version):
            for parameter in seg.parameter.twostep_parameters:
                aus[parameter.security_function] = parameter
    return aus


class FintsBankPlugin(BankPlugin):
    name = "fints"
    ist_mock = False

    def __init__(self, config: KontorConfig | None = None, *,
                 pin_quelle: Callable[[], str | None] | None = None) -> None:
        # Das Erzeugen baut keine Verbindung auf und ruft pin_quelle nicht auf (fints.md 3).
        self._config = config
        self._pin_quelle = pin_quelle
        self._daten: bytes | None = None      # BPD, UPD, System-ID (kein Geheimnis, nur Arbeitsspeicher)
        self._offen: dict[str, _Offen] = {}
        self._sperre = threading.RLock()
        self.diagnose = None   # D-203: Diagnoseprotokoll ohne persönliche Daten (plugins/fints_diagnose.py)

    def __repr__(self) -> str:
        return "FintsBankPlugin()"

    def _diag(self, text: str) -> None:
        if self.diagnose is not None:
            self.diagnose.eintrag(text)

    @contextlib.contextmanager
    def _vorgang(self, name: str):
        """Rahmen eines Aufrufs im Diagnoseprotokoll: Beginn und – ohne Texte fremder Ausnahmen – der Ausgang."""
        self._diag(f"── {name}")
        try:
            yield
        except TanErforderlich:
            raise
        except KontorFehler as e:
            self._diag(f"✗ {name} gescheitert: {type(e).__name__} ({getattr(e, 'code', '?')})")
            raise
        except Exception as e:
            self._diag(f"✗ {name} gescheitert: unerwarteter Fehler {type(e).__name__}")
            raise
        else:
            self._diag(f"✓ {name} abgeschlossen")

    __str__ = __repr__

    # ------------------------------------------------------------ Schnittstelle
    def konten(self, *, tan: TanAntwort | None = None) -> list[BankKonto]:
        """Konten der Bank. Verlangt die Bank schon beim Dialogbeginn eine TAN, kommt ``TanErforderlich``;
        ``konten(tan=TanAntwort(...))`` setzt denselben Dialog fort (D-198)."""
        with self._sperre, self._vorgang("Kontenabruf" + (" (Fortsetzung mit TAN)" if tan is not None else "")):
            self._konfiguriert()
            if tan is not None:
                return self._mit_tan(_KONTEN, tan)
            d = self._dialog_beginnen()
            try:
                if d.beginn is not None:
                    raise self._beginn_tan(d, _KONTEN, dt.date.min, dt.date.min)
                return self._konten_abschluss(d)
            except TanErforderlich:
                raise
            except BaseException:
                self._dialog_verwerfen(d)
                raise

    def _konten_abschluss(self, d: _Dialog) -> list[BankKonto]:
        konten = self._konten_im_dialog(d)
        self._dialog_beenden(d)
        return [k for k, _ in konten]

    def tan_verfahren(self) -> list[tuple[str, str]]:
        """Zwei-Schritt-Verfahren, die die Bank diesem Zugang erlaubt: ``(Sicherheitsfunktion, Name)``.

        Braucht nur den Synchronisierungsdialog (PIN, keine TAN). Kein Geschäftsvorfall wird gesendet."""
        from fints.client import FinTS3PinTanClient
        with self._sperre, self._vorgang("Abruf der TAN-Verfahren"):
            self._konfiguriert()
            c = self._config
            pin = self._pin()
            verbindung = _Verbindung(c, self.diagnose)
            try:
                client = FinTS3PinTanClient(c.fints_blz, c.fints_benutzer, pin, c.fints_url,
                                            customer_id=c.fints_kunden_id or c.fints_benutzer,
                                            product_id=c.fints_produkt_id)
            except Exception:  # noqa: BLE001 - Texte der Bibliothek nie weitergeben
                raise BankFehler("Der FinTS-Zugang konnte nicht vorbereitet werden.") from None
            del pin
            client.connection = verbindung
            with self._bibliothek(verbindung):
                client._ensure_system_id()
                verfahren = client.get_tan_mechanisms()
            _fehler_aus_codes(_alle_codes(verbindung.letzte))
            erlaubt = [str(x) for x in (client.allowed_security_functions or [])]
            self._diag(f"TAN-Verfahren: Bank kennt {','.join(str(k) for k in verfahren) or '-'}; "
                       f"für diesen Zugang erlaubt: {','.join(erlaubt) or 'keine Angabe (3920 fehlt)'}")
            if not erlaubt:
                # Nennt die Bank keine erlaubten Verfahren, gelten alle Zwei-Schritt-Verfahren der Bankparameter
                # (bankzugang.md 2.1). Die Bibliothek liefert in diesem Fall nichts, weil sie nach „erlaubt“ filtert.
                verfahren = _verfahren_der_bankparameter(client)
            aus = []
            for code, p in verfahren.items():
                code = str(code)
                if code == "999" or (erlaubt and code not in erlaubt):
                    continue
                aus.append((code, str(getattr(p, "name", "") or code)))
            return aus

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date, *,
                 tan: TanAntwort | None = None) -> Umsatzliste:
        with self._sperre, self._vorgang(f"Umsatzabruf {von} bis {bis}"
                                         + (" (Fortsetzung mit TAN)" if tan is not None else "")):
            self._konfiguriert()
            if von > bis:
                raise ValueError("von darf nicht nach bis liegen.")
            n = iban_normalisieren(str(iban))
            if tan is not None:
                return self._mit_tan(n, tan)
            d = self._dialog_beginnen()
            try:
                if d.beginn is not None:
                    raise self._beginn_tan(d, n, von, bis)
                return self._umsaetze_im_dialog(d, n, von, bis)
            except TanErforderlich:
                raise
            except BaseException:
                self._dialog_verwerfen(d)
                raise

    def _umsaetze_im_dialog(self, d: _Dialog, iban: str, von: dt.date, bis: dt.date) -> Umsatzliste:
        konten = self._konten_im_dialog(d)
        konto = next((sepa for k, sepa in konten if k.iban == iban), None)
        if konto is None:
            self._diag("✗ Das abzurufende Konto ist nicht in der Kontenliste der Bank")
            raise BankKontoUnbekannt("Das Konto ist der Bank unbekannt.")
        return self._abruf(d, iban, von, bis, konto)

    def _beginn_tan(self, d: _Dialog, iban: str, von: dt.date, bis: dt.date) -> TanErforderlich:
        """TAN-Anforderung der Dialoginitialisierung (starke Kundenauthentifizierung, D-198)."""
        hitan = d.beginn
        if getattr(hitan, "task_reference", None) is None:
            raise BankFehler("Die Bank verlangt eine TAN, hat aber keine TAN-Anforderung geliefert.")
        return self._tan_anfordern(_Offen(d, iban, von, bis, None, None, hitan, False, beginn=True),
                                   "Die Bank verlangt für die Anmeldung eine TAN.")

    def schliessen(self) -> None:
        with self._sperre:
            for o in list(self._offen.values()):
                self._dialog_verwerfen(o.d)
            self._offen.clear()

    # ------------------------------------------------------------ Prüfungen
    def _konfiguriert(self) -> None:
        c = self._config
        if c is None or not (c.fints_url and c.fints_blz and c.fints_benutzer and c.fints_produkt_id):
            raise PluginNichtVerfuegbar("Der Bankzugang ist noch nicht eingerichtet. Bitte unter Einstellungen → "
                                        "Bankzugang (FinTS) Server-Adresse, Bankleitzahl, Benutzerkennung und "
                                        "Produkt-ID eintragen und speichern.")

    def _pin(self) -> str:
        pin = self._pin_quelle() if self._pin_quelle is not None else None
        if pin is None or pin == "":
            raise BankPinFehlt("Für den Bankzugang wird eine PIN benötigt; es ist keine hinterlegt.")
        return str(pin)

    # ------------------------------------------------------------ Dialog
    def _dialog_beginnen(self) -> _Dialog:
        from fints.client import FinTS3PinTanClient
        c = self._config
        pin = self._pin()  # höchstens einmal je Dialog, unmittelbar vor dessen Beginn
        verbindung = _Verbindung(c, self.diagnose)
        client = None
        if self._daten is not None:
            try:
                client = FinTS3PinTanClient(c.fints_blz, c.fints_benutzer, pin, c.fints_url,
                                            customer_id=c.fints_kunden_id or c.fints_benutzer,
                                            product_id=c.fints_produkt_id, from_data=self._daten)
            except Exception:  # noqa: BLE001 - D-247: gespeicherte Parameter unlesbar (z. B. UPD ohne Konten)
                self._diag("Gespeicherte Bank- und Benutzerparameter nicht lesbar; neuer Abruf")
                self._daten = None
        if client is None:
            try:
                client = FinTS3PinTanClient(c.fints_blz, c.fints_benutzer, pin, c.fints_url,
                                            customer_id=c.fints_kunden_id or c.fints_benutzer,
                                            product_id=c.fints_produkt_id)
            except Exception:  # noqa: BLE001 - Texte der Bibliothek nie weitergeben
                raise BankFehler("Der FinTS-Zugang konnte nicht vorbereitet werden.") from None
        del pin
        client.connection = verbindung
        if c.fints_tan_verfahren and not client.selected_security_function:
            client.selected_security_function = c.fints_tan_verfahren
        with self._bibliothek(verbindung):
            client._ensure_system_id()
            dialog = client._new_dialog()
            antwort = dialog.init()
        beginn = client.init_tan_response
        client.init_tan_response = None
        self._diag(f"Dialog eröffnet: TAN-Verfahren {client.selected_security_function or '-'} (eingestellt: "
                   f"{c.fints_tan_verfahren or 'automatisch'}), TAN zur Anmeldung verlangt: "
                   f"{'ja' if beginn is not None else 'nein'}")
        if beginn is not None and getattr(beginn, "decoupled", False):
            # Entkoppelte Freigabe (3955) wird nicht unterstützt (D-070 gilt weiter, D-198).
            self._dialog_verwerfen(_Dialog(client, dialog, verbindung))
            raise BankFehler("Die Bank verlangt eine Freigabe in einer App; unterstützt wird nur die Eingabe "
                             "einer TAN (z. B. photoTAN). Bitte ein anderes TAN-Verfahren wählen.")
        try:
            _fehler_aus_codes(_alle_codes(antwort))
        except KontorFehler:
            self._dialog_verwerfen(_Dialog(client, dialog, verbindung))
            raise
        return _Dialog(client, dialog, verbindung, beginn.tan_request if beginn is not None else None)

    def _bibliothek(self, verbindung: _Verbindung):
        """Übersetzt Ausnahmen von python-fints in Fehlerklassen von Kontor (ohne Texte der Bibliothek)."""
        plugin = self

        class _Rahmen:
            def __enter__(self):
                return self

            def __exit__(self, typ, wert, tb):
                if wert is None:
                    return False
                plugin._uebersetzen(wert, verbindung)
                return False

        return _Rahmen()

    @staticmethod
    def _uebersetzen(wert: BaseException, verbindung: _Verbindung) -> None:
        from fints.exceptions import FinTSClientPINError, FinTSClientTemporaryAuthError, FinTSError
        ursache = wert
        while ursache is not None and not isinstance(ursache, KontorFehler):
            ursache = ursache.__cause__ or ursache.__context__
        if isinstance(ursache, KontorFehler):
            raise ursache.with_traceback(None) from None
        if isinstance(wert, FinTSClientPINError):
            raise BankPinFalsch("Die Bank hat die PIN abgelehnt.") from None
        if isinstance(wert, FinTSClientTemporaryAuthError):
            raise BankZugangGesperrt("Der Bankzugang ist gesperrt. Bitte bei der Bank entsperren lassen.") from None
        if isinstance(wert, (FinTSError, Exception)):
            codes = _alle_codes(verbindung.letzte)
            _fehler_aus_codes(codes)
            raise BankFehler("Die Kommunikation mit der Bank ist fehlgeschlagen.") from None

    def _senden(self, d: _Dialog, *segmente):
        with self._bibliothek(d.verbindung):
            return d.dialog.send(*segmente)

    def _dialog_beenden(self, d: _Dialog) -> None:
        try:
            with self._bibliothek(d.verbindung):
                d.dialog.end()
        except KontorFehler:
            pass  # Daten liegen schon vor; ein gescheitertes Dialogende ändert daran nichts
        self._merken(d)

    def _dialog_verwerfen(self, d: _Dialog) -> None:
        try:
            if getattr(d.dialog, "open", False):
                with self._bibliothek(d.verbindung):
                    d.dialog.end()
        except Exception:  # noqa: BLE001
            pass
        self._merken(d)

    def _merken(self, d: _Dialog) -> None:
        try:
            if d.client.bpd_version:
                self._daten = d.client.deconstruct(including_private=True)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ Konten (3.2)
    def _konten_im_dialog(self, d: _Dialog) -> list[tuple[BankKonto, object]]:
        from fints.segments.accounts import HISPA1, HKSPA1
        seg = HKSPA1()
        antwort = self._senden(d, seg)
        _fehler_aus_codes(_codes(antwort, seg) + _codes(antwort))
        sepa = {}
        segmente = list(antwort.response_segments(seg, HISPA1)) or [
            s for s in antwort.find_segments(HISPA1) if s.header.reference is None]
        for s in segmente:
            for k in s.accounts or []:
                if k.iban:
                    sepa.setdefault(iban_normalisieren(str(k.iban)), k)
        # Benutzerparameter je Konto: über die IBAN, ersatzweise über die Kontonummer. D-202: Manche Banken
        # (z. B. comdirect) liefern in HIUPD keine IBAN oder keine Kontoart; maßgeblich ist dann die
        # SEPA-Kontoverbindung aus HISPA.
        nach_iban: dict[str, object] = {}
        nach_nummer: dict[str, object] = {}
        for u in d.client.upd.find_segments("HIUPD"):
            if getattr(u, "iban", None):
                nach_iban.setdefault(iban_normalisieren(str(u.iban)), u)
            nummer = getattr(getattr(u, "account_information", None), "account_number", None)
            if nummer:
                nach_nummer.setdefault(str(nummer).lstrip("0"), u)
        aus = []
        self._diag(f"Kontenliste: {len(sepa)} Kontoverbindungen mit IBAN aus HISPA, {len(nach_iban)} HIUPD mit IBAN, "
                   f"{len(nach_nummer)} HIUPD mit Kontonummer")
        for nr, (n, k) in enumerate(sepa.items(), 1):
            u = nach_iban.get(n)
            wie = "IBAN"
            if u is None and getattr(k, "account_number", None):
                u = nach_nummer.get(str(k.account_number).lstrip("0"))
                wie = "Kontonummer"
            art, name, inhaber = "girokonto", "", ""
            if u is not None:
                if str(getattr(u, "account_currency", "") or "EUR") != "EUR":
                    self._diag(f"  Konto {nr}: ausgelassen, Währung {u.account_currency} (HIUPD über {wie})")
                    continue
                if getattr(u, "account_type", None) is not None:
                    try:
                        art = _art(int(u.account_type))
                    except (TypeError, ValueError):
                        art = None
                    if art is None:
                        self._diag(f"  Konto {nr}: ausgelassen, Kontoart {u.account_type} wird nicht abgerufen "
                                   f"(HIUPD über {wie})")
                        continue   # Depot, Fonds, Bausparen … (K 15)
                name = str(u.account_product_name or "")
                inhaber = " ".join(str(x) for x in (u.name_account_owner_1, u.name_account_owner_2) if x)
            konto = k.as_sepa_account()
            if konto is None:   # von der Bank nicht als SEPA-Konto geführt
                self._diag(f"  Konto {nr}: ausgelassen, von der Bank nicht als SEPA-Konto gekennzeichnet")
                continue
            self._diag(f"  Konto {nr}: übernommen als {art} ("
                       + (f"HIUPD über {wie}" if u is not None else "kein HIUPD-Eintrag") + ")")
            bic = str(k.bic) if k.bic else None
            aus.append((BankKonto(n, bic or None, name, art, inhaber, "EUR"), konto))
        aus.sort(key=lambda x: x[0].iban)
        return aus

    # ------------------------------------------------------------ Umsätze (3.3–3.5)
    def _segment(self, d: _Dialog, konto, von: dt.date, bis: dt.date, aufsetzpunkt: str | None):
        from fints.formals import SupportedMessageTypes
        from fints.segments.statement import HKCAZ1, HKKAZ5, HKKAZ6, HKKAZ7
        client = d.client
        hicazs = client.bpd.find_segment_first("HICAZS")
        if hicazs is not None:
            # D-197: bietet die Bank camt an, wird nie auf MT940 ausgewichen (HKKAZ ist bei manchen Banken
            # abgekündigt oder gestört); KTI1 trägt dabei nur IBAN und BIC.
            angeboten = [str(x) for x in (hicazs.parameter.supported_camt_formats or [])]
            fmt = next((f for f in CAMT_FORMATE if f in angeboten), None)
            self._diag("Umsatzabruf über HKCAZ, Format: " + (fmt.rsplit(":", 1)[-1] if fmt else "keines lesbar"))
            if fmt is None:
                raise BankFehler("Die Bank bietet kein unterstütztes camt-Format an (camt.052.001.02 bis .08).")
            seg = HKCAZ1(account=HKCAZ1._fields["account"].type.from_sepa_account(konto), all_accounts=False,
                         date_start=von, date_end=bis, touchdown_point=aufsetzpunkt,
                         supported_camt_messages=SupportedMessageTypes([fmt]))
            return seg, True
        try:
            klasse = client._find_highest_supported_command(HKKAZ5, HKKAZ6, HKKAZ7)
        except Exception:  # noqa: BLE001 - FinTSUnsupportedOperation
            raise BankFehler("Die Bank bietet keinen unterstützten Umsatzabruf an (camt.052.001.08 oder MT940).") \
                from None
        seg = klasse(account=klasse._fields["account"].type.from_sepa_account(konto), all_accounts=False,
                     date_start=von, date_end=bis, touchdown_point=aufsetzpunkt)
        return seg, False

    def _tan_noetig(self, d: _Dialog, seg) -> bool:
        try:
            return bool(d.client._need_twostep_tan_for_segment(seg))
        except Exception:  # noqa: BLE001
            return False

    def _abruf(self, d: _Dialog, iban: str, von: dt.date, bis: dt.date, konto, seiten=None,
               aufsetzpunkt: str | None = None) -> list[BankUmsatz]:
        seiten = [] if seiten is None else seiten
        while True:
            seg, camt = self._segment(d, konto, von, bis, aufsetzpunkt)
            if self._tan_noetig(d, seg):
                tan_seg = d.client._get_tan_segment(seg, "4")
                antwort = self._senden(d, seg, tan_seg)
                tan_codes = _codes(antwort, tan_seg)
                if "3955" in tan_codes:
                    raise BankFehler("Die Bank verlangt eine Freigabe in einer App; nur QR-TAN wird unterstützt.")
                if "0030" in tan_codes:
                    hitan = antwort.find_segment_first("HITAN")
                    if hitan is None:
                        raise BankFehler("Die Bank verlangt eine TAN, hat aber keine TAN-Anforderung geliefert.")
                    raise self._tan_anfordern(_Offen(d, iban, von, bis, konto, seg, hitan, camt, seiten))
                _fehler_aus_codes(tan_codes)
            else:
                antwort = self._senden(d, seg)
            aufsetzpunkt = self._seite_lesen(antwort, seg, camt, seiten)
            if aufsetzpunkt is None:
                break
        return self._abschluss(d, iban, von, bis, konto, seiten)

    def _abschluss(self, d: _Dialog, iban: str, von: dt.date, bis: dt.date, konto, seiten: list) -> Umsatzliste:
        """Nach dem letzten Abrufteil: Umsätze auswerten, im selben Dialog den Saldo abfragen, Dialog beenden."""
        umsaetze = self._ergebnis(iban, von, bis, seiten)
        saldo = self._saldo(d, iban, konto)
        self._dialog_beenden(d)
        return Umsatzliste(umsaetze, saldo=saldo)

    # ------------------------------------------------------------ Saldo (kontostand.md 1.2)
    def _saldo_angeboten(self, d: _Dialog, iban: str) -> bool:
        """HISALS in der BPD und HKSAL unter den erlaubten Geschäftsvorfällen des Kontos in der UPD."""
        if d.client.bpd.find_segment_first("HISALS") is None:
            return False
        for u in d.client.upd.find_segments("HIUPD"):
            u_iban = getattr(u, "iban", None)
            if u_iban and iban_normalisieren(str(u_iban)) == iban:
                return any(str(getattr(t, "transaction", "") or "") == "HKSAL"
                           for t in (getattr(u, "allowed_transactions", None) or []))
        return False

    def _saldo(self, d: _Dialog, iban: str, konto) -> BankSaldo | None:
        """Genau ein HKSAL im Dialog des Umsatzabrufs; scheitert nur die Saldenabfrage, ist der Saldo None.

        Kennzeichnet die Bank HKSAL als zweischrittig, geht HKTAN Prozess 4 mit (wie beim Umsatzabruf, D-240).
        Viele Banken antworten darauf mit 3076 (keine starke Authentifizierung nötig) und liefern den Saldo.
        Verlangen sie tatsächlich eine TAN (0030) oder eine App-Freigabe (3955), bleibt der Saldo None: für den
        Saldo nie eine TAN (kontostand.md 1)."""
        from fints.segments.saldo import HKSAL5, HKSAL6, HKSAL7
        if not self._saldo_angeboten(d, iban):
            self._diag("Saldo: nicht abgefragt, HKSAL ist für dieses Konto laut Benutzerparametern nicht erlaubt")
            return None
        try:
            klasse = d.client._find_highest_supported_command(HKSAL5, HKSAL6, HKSAL7)
            seg = klasse(account=klasse._fields["account"].type.from_sepa_account(konto), all_accounts=False)
        except Exception as e:  # noqa: BLE001 - FinTSUnsupportedOperation o. ä.: keine passende Version
            self._diag(f"Saldo: nicht abgefragt, keine passende HKSAL-Version ({type(e).__name__})")
            return None
        try:
            if self._tan_noetig(d, seg):
                tan_seg = d.client._get_tan_segment(seg, "4")
                antwort = self._senden(d, seg, tan_seg)
                tan_codes = _codes(antwort, tan_seg)
                if "0030" in tan_codes or "3955" in tan_codes:
                    self._diag("Saldo: nicht übernommen, die Bank verlangt dafür eine TAN-Freigabe")
                    return None
            else:
                antwort = self._senden(d, seg)
        except KontorFehler as e:
            self._diag(f"Saldo: Abfrage gescheitert ({type(e).__name__})")
            return None
        fehler = [c for c in _codes(antwort, seg) if c.startswith("9")]
        if fehler:
            self._diag(f"Saldo: von der Bank abgelehnt ({','.join(fehler)})")
            return None
        for h in list(antwort.response_segments(seg, "HISAL")) or [
                h for h in antwort.find_segments("HISAL") if h.header.reference is None]:
            saldo = _saldo_aus_hisal(iban, h)
            self._diag("Saldo: übernommen" if saldo is not None
                       else "Saldo: Antwort ohne verwertbaren gebuchten Saldo in EUR")
            return saldo
        self._diag("Saldo: die Antwort enthält kein HISAL")
        return None

    def _seite_lesen(self, antwort, seg, camt: bool, seiten: list) -> str | None:
        """Prüft die Rückmeldungen zum Abruf, sammelt die Daten und liefert den Aufsetzpunkt (3040) oder None."""
        codes = _codes(antwort, seg)
        _fehler_aus_codes(codes + [c for c in _codes(antwort) if c != "9050" or not codes])
        art = "HICAZ" if camt else "HIKAZ"
        for s in list(antwort.response_segments(seg, art)) or [
                s for s in antwort.find_segments(art) if s.header.reference is None]:
            if camt:
                for doc in (s.statement_booked.camt_statements if s.statement_booked else None) or []:
                    seiten.append(("camt", bytes(doc)))
                if s.statement_pending:
                    seiten.append(("camt", bytes(s.statement_pending)))
            else:
                seiten.append(("mt940", bytes(s.statement_booked or b"")))
        for r in antwort.responses(seg, "3040"):
            if r.parameters:
                return str(r.parameters[0])
        return None

    def _ergebnis(self, iban: str, von: dt.date, bis: dt.date, seiten: list) -> list[BankUmsatz]:
        roh: list[_Roh] = []
        try:
            mt940 = "".join(b.decode("iso-8859-1") for art, b in seiten if art == "mt940")
            for art, b in seiten:
                if art == "camt":
                    roh.extend(camt_eintraege(b))
            if mt940:
                roh.extend(mt940_eintraege(mt940))
        except (ET.ParseError, ValueError) as e:
            if isinstance(e, _Unlesbar):   # Form des Felds ohne den Wert
                self._diag(f"✗ Umsatzdaten unlesbar: Feld {e.feld} hat die Form „{e.form}“")
            else:
                self._diag(f"✗ Umsatzdaten unlesbar ({type(e).__name__})")
            raise BankFehler("Die Bank hat unlesbare Umsatzdaten geliefert.") from None
        aus = [u for u in kennungen_vergeben(iban, roh) if von <= u.buchungstag <= bis]
        aus.sort(key=lambda u: (u.buchungstag, u.umsatz_id))
        self._diag(f"Umsätze: {sum(1 for a, _ in seiten if a == 'camt')} camt-Dokumente, "
                   f"{sum(1 for a, _ in seiten if a == 'mt940')} MT940-Blöcke, {len(roh)} Einträge gelesen "
                   f"({sum(1 for r in roh if r.vormerkung)} vorgemerkt, {sum(1 for r in roh if r.referenz)} mit "
                   f"Bankreferenz), {len(aus)} im Zeitraum {von} bis {bis}")
        return aus

    # ------------------------------------------------------------ TAN (3.5)
    def _tan_anfordern(self, o: _Offen,
                       meldung: str = "Die Bank verlangt für den Umsatzabruf eine TAN.") -> TanErforderlich:
        self._diag("TAN erforderlich: " + ("zur Anmeldung (Dialogbeginn)" if o.beginn else "zum Umsatzabruf")
                   + "; der Dialog bleibt offen")
        h = o.hitan
        referenz = str(getattr(h, "task_reference", "") or "").strip()
        aid = referenz or ("TAN-" + uuid.uuid4().hex)
        while aid in self._offen:
            aid = f"{referenz}-{uuid.uuid4().hex[:8]}"
        alt = [k for k, v in self._offen.items() if v.iban == o.iban]
        for k in alt:  # eine frühere Anforderung desselben Kontos verfällt
            self._dialog_verwerfen(self._offen.pop(k).d)
        self._offen[aid] = o
        challenge = str(getattr(h, "challenge", "") or "").strip() or "Bitte TAN eingeben"
        bild = mime = None
        roh = getattr(h, "challenge_hhduc", None)
        if roh:
            roh = bytes(roh)
            if len(roh) >= 4:
                n = int.from_bytes(roh[:2], "big")
                typ = roh[2:2 + n]
                rest = roh[2 + n:]
                if len(typ) == n and len(rest) >= 2:
                    m = int.from_bytes(rest[:2], "big")
                    inhalt = rest[2:2 + m]
                    if len(inhalt) == m and m > 0 and typ:
                        try:
                            mime, bild = typ.decode("ascii"), inhalt
                        except UnicodeDecodeError:
                            mime = bild = None
        gueltig = None
        gv = getattr(h, "challenge_valid_until", None)
        if gv is not None and getattr(gv, "date", None) is not None:
            try:
                zeit = gv.time if gv.time is not None else dt.time(23, 59, 59)
                gueltig = dt.datetime.combine(gv.date, zeit).replace(tzinfo=BERLIN).astimezone(UTC)
            except (TypeError, ValueError):
                gueltig = None
        if gueltig is None:
            gueltig = dt.datetime.now(UTC) + dt.timedelta(minutes=5)
        return TanErforderlich(meldung, anforderung_id=aid,
                               gueltig_bis=gueltig, challenge=challenge, bild=bild, bild_mime_typ=mime)

    def _mit_tan(self, iban: str, tan: TanAntwort):
        aid = str(getattr(tan, "anforderung_id", ""))
        o = self._offen.get(aid)
        if o is None or o.iban != iban or not isinstance(getattr(tan, "tan", None), str):
            raise TanUngueltig("Zu dieser Kennung gibt es keine offene TAN-Anforderung.")
        d = o.d
        try:
            tan_seg = d.client._get_tan_segment(o.segment, "2", o.hitan)  # Prozess 2 braucht nur die Referenz
            d.client._pending_tan = tan.tan
            try:
                antwort = self._senden(d, tan_seg)
            finally:
                d.client._pending_tan = None
        except (BankVerbindungsFehler, BankZeitueberschreitung):
            raise
        except KontorFehler:
            self._offen.pop(aid, None)
            self._dialog_verwerfen(d)
            raise
        codes = _codes(antwort, tan_seg)
        if "9941" in codes:
            raise TanUngueltig("Die Bank hat die TAN nicht akzeptiert.")
        if "9955" in codes or not getattr(d.dialog, "open", True):
            self._offen.pop(aid, None)
            self._dialog_verwerfen(d)
            raise TanAbgelaufen("Die TAN-Anforderung ist bei der Bank abgelaufen.")
        self._offen.pop(aid, None)
        try:
            if o.beginn:
                # Die Antwort auf die TAN vervollständigt die Dialoginitialisierung (BPD/UPD sind verarbeitet).
                _fehler_aus_codes(_alle_codes(antwort))
                if iban == _KONTEN:
                    return self._konten_abschluss(d)
                return self._umsaetze_im_dialog(d, iban, o.von, o.bis)
            _fehler_aus_codes(codes)
            aufsetzpunkt = self._seite_lesen(antwort, o.segment, o.camt, o.seiten)
            if aufsetzpunkt is None:
                return self._abschluss(d, iban, o.von, o.bis, o.konto, o.seiten)
            return self._abruf(d, iban, o.von, o.bis, o.konto, o.seiten, aufsetzpunkt)
        except TanErforderlich:
            raise
        except BaseException:
            self._dialog_verwerfen(d)
            raise


def _saldo_aus_hisal(iban: str, h) -> BankSaldo | None:
    """HISAL (Version 5: Balance1, 6/7: Balance2) → BankSaldo in Cent; Haben positiv, Soll negativ, nur EUR."""
    import decimal
    b = getattr(h, "balance_booked", None)
    if b is None or getattr(b, "date", None) is None:
        return None
    betrag = getattr(b, "amount", None)
    waehrung = getattr(b, "currency", None)
    if betrag is not None and hasattr(betrag, "amount"):  # Balance2 mit Amount1
        betrag, waehrung = betrag.amount, betrag.currency
    if betrag is None or str(waehrung or "") != "EUR":
        return None
    try:
        cent_dez = decimal.Decimal(betrag) * 100
    except (decimal.InvalidOperation, TypeError, ValueError):
        return None
    if cent_dez != cent_dez.to_integral_value():
        return None
    cent = abs(int(cent_dez))
    kennzeichen = str(getattr(getattr(b, "credit_debit", None), "value", getattr(b, "credit_debit", "")) or "")
    if kennzeichen == "D":
        cent = -cent
    elif kennzeichen != "C":
        return None
    datum = b.date
    if isinstance(datum, dt.datetime):
        datum = datum.date()
    if not isinstance(datum, dt.date):
        return None
    return BankSaldo(iban=iban, betrag=cent, stichtag=datum)


__all__ = ["FintsBankPlugin", "camt_eintraege", "mt940_eintraege", "kennungen_vergeben"]
