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
import datetime as dt
import hashlib
import http.client
import logging
import re
import threading
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
from .bank import BankKonto, BankPlugin, BankUmsatz, TanAntwort

BERLIN = ZoneInfo("Europe/Berlin")
UTC = dt.timezone.utc
CAMT_052 = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"
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


def _cent_punkt(text: str) -> int:
    ganz, _, rest = text.strip().partition(".")
    return int(ganz or "0") * 100 + int((rest + "00")[:2])


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
        bt = _text(ntry, "BookgDt", "Dt") or _text(ntry, "ValDt", "Dt")
        if not bt:
            continue
        valuta = _text(ntry, "ValDt", "Dt")
        seite = ind if not storno else ("CRDT" if ind == "DBIT" else "DBIT")
        partei, konto = ("Cdtr", "CdtrAcct") if seite == "DBIT" else ("Dbtr", "DbtrAcct")
        tx = _kind(ntry, "NtryDtls", "TxDtls")
        pt = _kind(tx, "RltdPties")
        name = _text(pt, partei, "Pty", "Nm") or _text(pt, partei, "Nm") or None
        rmt = _kind(tx, "RmtInf")
        zweck = "".join((k.text or "") for k in (rmt if rmt is not None else []) if _lokal(k) == "Ustrd")
        ref = (_text(ntry, "AcctSvcrRef") or "").strip()
        aus.append(_Roh(dt.date.fromisoformat(bt.strip()), dt.date.fromisoformat(valuta.strip()) if valuta else None,
                        cent if ind == "CRDT" else -cent, name, _iban_oder_none(_text(pt, konto, "Id", "IBAN")),
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

    def __init__(self, config: KontorConfig) -> None:
        self._config = config
        self.letzte = None

    def __repr__(self) -> str:
        return "_Verbindung()"

    def send(self, msg):
        from fints.message import FinTSInstituteMessage
        c = self._config
        daten = base64.b64encode(msg.render_bytes())
        try:
            antwort = http_anfrage(c, "POST", c.fints_url, daten, {"Content-Type": "text/plain"},
                                   c.fints_timeout_sekunden)
        except TimeoutError:
            raise BankZeitueberschreitung("Die Bank hat nicht rechtzeitig geantwortet.") from None
        except (OSError, http.client.HTTPException):
            raise BankVerbindungsFehler("Die Verbindung zur Bank ist fehlgeschlagen.") from None
        if not 200 <= antwort.status <= 299:
            raise BankVerbindungsFehler(f"Die Bank hat mit HTTP-Status {antwort.status} geantwortet.",
                                        status=antwort.status)
        try:
            roh = base64.b64decode(antwort.koerper.decode("iso-8859-1"), validate=False)
            nachricht = FinTSInstituteMessage(segments=roh)
        except Exception:  # noqa: BLE001 - jede unlesbare Antwort
            raise BankVerbindungsFehler("Die Antwort der Bank ist unlesbar.") from None
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

    def __repr__(self) -> str:
        return f"_Offen(von={self.von}, bis={self.bis})"


# ================================================================ Plugin


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

    def __repr__(self) -> str:
        return "FintsBankPlugin()"

    __str__ = __repr__

    # ------------------------------------------------------------ Schnittstelle
    def konten(self) -> list[BankKonto]:
        with self._sperre:
            self._konfiguriert()
            d = self._dialog_beginnen()
            try:
                konten = self._konten_im_dialog(d)
            except BaseException:
                self._dialog_verwerfen(d)
                raise
            self._dialog_beenden(d)
            return [k for k, _ in konten]

    def umsaetze(self, iban: str, von: dt.date, bis: dt.date, *,
                 tan: TanAntwort | None = None) -> list[BankUmsatz]:
        with self._sperre:
            self._konfiguriert()
            if von > bis:
                raise ValueError("von darf nicht nach bis liegen.")
            n = iban_normalisieren(str(iban))
            if tan is not None:
                return self._mit_tan(n, tan)
            d = self._dialog_beginnen()
            try:
                konten = self._konten_im_dialog(d)
                konto = next((sepa for k, sepa in konten if k.iban == n), None)
                if konto is None:
                    raise BankKontoUnbekannt("Das Konto ist der Bank unbekannt.")
                return self._abruf(d, n, von, bis, konto)
            except TanErforderlich:
                raise
            except BaseException:
                self._dialog_verwerfen(d)
                raise

    def schliessen(self) -> None:
        with self._sperre:
            for o in list(self._offen.values()):
                self._dialog_verwerfen(o.d)
            self._offen.clear()

    # ------------------------------------------------------------ Prüfungen
    def _konfiguriert(self) -> None:
        c = self._config
        if c is None or not (c.fints_url and c.fints_blz and c.fints_benutzer and c.fints_produkt_id):
            raise PluginNichtVerfuegbar("Der FinTS-Zugang ist nicht konfiguriert (fints_url, fints_blz, "
                                        "fints_benutzer, fints_produkt_id).")

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
        verbindung = _Verbindung(c)
        try:
            client = FinTS3PinTanClient(c.fints_blz, c.fints_benutzer, pin, c.fints_url,
                                        customer_id=c.fints_kunden_id or c.fints_benutzer,
                                        product_id=c.fints_produkt_id, from_data=self._daten)
        except Exception:  # noqa: BLE001
            raise BankFehler("Der FinTS-Zugang konnte nicht vorbereitet werden.") from None
        del pin
        client.connection = verbindung
        if c.fints_tan_verfahren and not client.selected_security_function:
            client.selected_security_function = c.fints_tan_verfahren
        with self._bibliothek(verbindung):
            client._ensure_system_id()
            dialog = client._new_dialog()
            antwort = dialog.init()
        if client.init_tan_response is not None:
            # Starke Kundenauthentifizierung schon beim Dialogbeginn wird nicht unterstützt (D-071).
            d = _Dialog(client, dialog, verbindung)
            self._dialog_verwerfen(d)
            raise BankFehler("Die Bank verlangt schon beim Dialogbeginn eine Freigabe; das wird nicht unterstützt.")
        try:
            _fehler_aus_codes(_alle_codes(antwort))
        except KontorFehler:
            self._dialog_verwerfen(_Dialog(client, dialog, verbindung))
            raise
        return _Dialog(client, dialog, verbindung)

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
        aus = []
        gesehen = set()
        for u in d.client.upd.find_segments("HIUPD"):
            iban = getattr(u, "iban", None)
            if not iban:
                continue
            n = iban_normalisieren(str(iban))
            if n in gesehen or n not in sepa:
                continue
            if str(getattr(u, "account_currency", "") or "") != "EUR":
                continue
            try:
                art = _art(int(u.account_type) if u.account_type is not None else None)
            except (TypeError, ValueError):
                art = None
            if art is None:
                continue
            gesehen.add(n)
            inhaber = " ".join(str(x) for x in (u.name_account_owner_1, u.name_account_owner_2) if x)
            bic = str(sepa[n].bic) if sepa[n].bic else None
            aus.append((BankKonto(n, bic or None, str(u.account_product_name or ""), art, inhaber, "EUR"),
                        sepa[n].as_sepa_account()))
        aus.sort(key=lambda x: x[0].iban)
        return aus

    # ------------------------------------------------------------ Umsätze (3.3–3.5)
    def _segment(self, d: _Dialog, konto, von: dt.date, bis: dt.date, aufsetzpunkt: str | None):
        from fints.formals import SupportedMessageTypes
        from fints.segments.statement import HKCAZ1, HKKAZ5, HKKAZ6, HKKAZ7
        client = d.client
        hicazs = client.bpd.find_segment_first("HICAZS")
        if hicazs is not None and CAMT_052 in [str(x) for x in (hicazs.parameter.supported_camt_formats or [])]:
            seg = HKCAZ1(account=HKCAZ1._fields["account"].type.from_sepa_account(konto), all_accounts=False,
                         date_start=von, date_end=bis, touchdown_point=aufsetzpunkt,
                         supported_camt_messages=SupportedMessageTypes([CAMT_052]))
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
        self._dialog_beenden(d)
        return self._ergebnis(iban, von, bis, seiten)

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
        except (ET.ParseError, ValueError):
            raise BankFehler("Die Bank hat unlesbare Umsatzdaten geliefert.") from None
        aus = [u for u in kennungen_vergeben(iban, roh) if von <= u.buchungstag <= bis]
        aus.sort(key=lambda u: (u.buchungstag, u.umsatz_id))
        return aus

    # ------------------------------------------------------------ TAN (3.5)
    def _tan_anfordern(self, o: _Offen) -> TanErforderlich:
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
        return TanErforderlich("Die Bank verlangt für den Umsatzabruf eine TAN.", anforderung_id=aid,
                               gueltig_bis=gueltig, challenge=challenge, bild=bild, bild_mime_typ=mime)

    def _mit_tan(self, iban: str, tan: TanAntwort) -> list[BankUmsatz]:
        aid = str(getattr(tan, "anforderung_id", ""))
        o = self._offen.get(aid)
        if o is None or o.iban != iban or not isinstance(getattr(tan, "tan", None), str):
            raise TanUngueltig("Zu dieser Kennung gibt es keine offene TAN-Anforderung.")
        d = o.d
        try:
            tan_seg = d.client._get_tan_segment(o.segment, "2", o.hitan)
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
            _fehler_aus_codes(codes)
            aufsetzpunkt = self._seite_lesen(antwort, o.segment, o.camt, o.seiten)
            if aufsetzpunkt is None:
                self._dialog_beenden(d)
                return self._ergebnis(iban, o.von, o.bis, o.seiten)
            return self._abruf(d, iban, o.von, o.bis, o.konto, o.seiten, aufsetzpunkt)
        except TanErforderlich:
            raise
        except BaseException:
            self._dialog_verwerfen(d)
            raise


__all__ = ["FintsBankPlugin", "camt_eintraege", "mt940_eintraege", "kennungen_vergeben"]
