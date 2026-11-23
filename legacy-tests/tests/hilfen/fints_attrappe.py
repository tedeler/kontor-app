"""Lokale FinTS-Attrappe (FinTS 3.0 PIN/TAN über HTTP) für Meilenstein 6 – nur 127.0.0.1.

Die Attrappe spielt eine Bank auf Protokollebene (E-028, ``fints.md`` 6): Sie
nimmt base64-kodierte FinTS-Nachrichten per HTTP-POST an, prüft PIN und TAN
und antwortet mit Bankparameterdaten, Kontenliste und Umsätzen aus den
synthetischen Daten des Generators (``fixtures/m6/fints_bank.json``). Zum
Zerlegen und Bauen der Segmente verwendet sie die Klassen von python-fints;
sie ist keine Implementierung und kein Vorbild für das Plugin.

Verhalten (verbindlich beschrieben in ``spec/api/fints.md`` 6):

- Profil ``camt`` (Vorgabe): BPD bieten nur HKCAZ (camt.052.001.08) an;
  Profil ``mt940``: nur HKKAZ Version 7.
- Zwei-Schritt-Verfahren mit QR-Bild (Sicherheitsfunktion ``tan_verfahren``),
  HKSPA ohne, HKKAZ/HKCAZ mit TAN-Pflicht laut HIPINS. ``tan_pflicht``:
  ``"einmal"`` (bis zur ersten erfolgreichen TAN, danach Freigabe wie nach
  PSD2 für 90 Tage), ``"immer"``, ``"nie"``.
- Rückmeldungen: 0010/0020 Erfolg, 3920 zugelassene TAN-Verfahren, 3076
  keine starke Kundenauthentifizierung nötig, 0030 TAN erforderlich (HITAN
  Version 6 mit Challenge, QR-Bild als Matrix-Code und Gültigkeit), 3040
  Aufsetzpunkt, 9931 PIN falsch, 3938 Zugang gesperrt, 9941 TAN ungültig
  (Auftrag bleibt offen), 9955 TAN-Auftrag abgelaufen, 9380 Auftrag
  abgelehnt (für Konten in ``fehler_iban``), 9210 unbekanntes Konto.
- Schreibende Geschäftsvorfälle werden nie ausgeführt; jede empfangene
  Segmentart steht in ``segmentarten``.

Betriebsarten ab Meilenstein 29 (``fints.md`` 6, E-263; die Vorgaben lassen das
Verhalten von M6/M11 unverändert): Profil ``beide``, ``camt_formate``,
``tan_anmeldung``/``anmeldung_entkoppelt``, ``erlaubte_verfahren``/
``verfahren_zusatz``, ``upd_ohne_kontoart``/``upd_ohne_iban``/``upd_ohne_konten``,
``hispa_mit_nicht_sepa``/``hispa_ohne_bic``, ``datum_form``/``datum_kaputt``/
``betrag_kaputt`` und ``rueckmeldung_zusatz``.
"""

from __future__ import annotations

import base64
import datetime as dt
import http.server
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")

#: Segmentarten, die ein nur lesender Client senden darf (fints.md 3.6)
LESEND = frozenset({"HNHBK", "HNHBS", "HNVSK", "HNVSD", "HNSHK", "HNSHA", "HKIDN", "HKVVB", "HKSYN", "HKTAN",
                    "HKEND", "HKSPA", "HKKAZ", "HKCAZ", "HKSAL", "HKTAB"})
CAMT_052 = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"


def camt_format(n: int) -> str:
    """Formatbezeichner ``camt.052.001.0n`` (M29, fints.md 3.3)."""
    return f"urn:iso:std:iso:20022:tech:xsd:camt.052.001.{n:02d}"


def _fints():
    """python-fints erst bei Bedarf laden (nur M6-Tests brauchen es)."""
    import fints.formals as formals  # noqa: PLC0415
    import fints.segments.accounts as accounts  # noqa: PLC0415
    import fints.segments.auth as auth  # noqa: PLC0415
    import fints.segments.bank as bank  # noqa: PLC0415
    import fints.segments.dialog as dialog  # noqa: PLC0415
    import fints.segments.message as message  # noqa: PLC0415
    import fints.segments.statement as statement  # noqa: PLC0415
    import fints.types as types  # noqa: PLC0415
    return formals, accounts, auth, bank, dialog, message, statement, types


@dataclass
class _Auftrag:
    """Offene TAN-Anforderung (Auftragsreferenz) mit dem ursprünglichen Abruf."""
    referenz: str
    art: str                 # "HKCAZ" | "HKKAZ" | "HKIDN" (TAN bei der Anmeldung, M29)
    segmentnummer: int
    iban: str
    von: dt.date | None
    bis: dt.date | None
    aufsetzpunkt: str | None
    version: int
    abgelaufen: bool = False
    camt: str = CAMT_052     # verlangtes camt-Format (M29)


@dataclass
class _Dialog:
    dialog_id: str
    nachrichten: int = 0
    pin_geprueft: bool = False
    sca_erfolgt: bool = False
    anmeldung_ok: bool = True     # M29: False, solange die Anmeldung noch eine TAN braucht


@dataclass
class Anfrage:
    """Aufzeichnung einer empfangenen Nachricht (ohne PIN/TAN-Werte)."""
    dialog_id: str
    segmente: list[str]
    pin_vorhanden: bool
    tan_vorhanden: bool
    produkt_id: str | None


class FintsAttrappe:
    def __init__(self, daten: dict, *, profil: str = "camt", tan_pflicht: str = "einmal",
                 seitengroesse: int = 40, heute: dt.date | None = None, tls=None) -> None:
        assert profil in ("camt", "mt940", "beide") and tan_pflicht in ("einmal", "immer", "nie")
        self.daten = daten
        self.tls = tls                    # tests/hilfen/tls.TestZertifikat oder None
        self.profil = profil
        self.tan_pflicht = tan_pflicht
        self.seitengroesse = seitengroesse
        self.heute = heute
        self.freigegeben = False
        self.gesperrt = False
        self.verzoegerung = 0.0           # Sekunden vor jeder Antwort
        self.http_status = 200            # ≠ 200: Antwort ohne FinTS-Inhalt
        self.fehler_iban: set[str] = set()
        # M11 (fints.md 6, kontostand.md 1.2): Saldenabfrage HKSAL nur auf Wunsch
        self.saldo_anbieten = False
        self.saldo_versatz = 0             # Cent, auf den gebuchten Saldo aufgeschlagen
        self.saldo_fehler_iban: set[str] = set()
        self.saldo_abfragen: list[tuple[int, str]] = []   # (Version, IBAN bzw. Kontonummer)
        self.tan_gueltig_minuten = 10
        # ---- M29 (fints.md 6, E-263); Vorgaben = Verhalten von M6/M11
        self.camt_formate: list[str] = [CAMT_052]           # Angebot in HICAZS
        self.camt_angefordert: list[list[str]] = []         # je HKCAZ die verlangten Formate
        self.camt_kontoverbindungen: list[dict] = []        # je HKCAZ die gefüllten Felder der Kontoverbindung
        self.tan_anmeldung = "nie"                          # "nie" | "einmal" | "immer"
        self.anmeldung_entkoppelt = False                   # 3955 statt 0030 bei der Anmeldung
        self.anmeldung_freigegeben = False
        self.anmeldungs_tans = 0                            # verlangte TANs zur Anmeldung
        self.erlaubte_verfahren: list[str] | None = [daten["tan_verfahren"]["funktion"]]   # None: kein 3920
        self.verfahren_zusatz: list[dict] = []              # weitere Zwei-Schritt-Verfahren in HITANS
        self.upd_ohne_kontoart = False
        self.upd_ohne_iban = False                          # HIUPD nur mit Kontonummer (ohne führende Nullen)
        self.upd_ohne_konten = False                        # kein HIUPD
        self.hispa_mit_nicht_sepa = False                   # Konten mit sepa=False als Nicht-SEPA-Konto in HISPA
        self.hispa_ohne_bic = False
        self.datum_form: str | None = None                  # "zone" | "z" | "zeitpunkt" | "zeitpunkt_dt"
        self.datum_kaputt: str | None = None                # ersetzt das Buchungsdatum des ersten Eintrags
        self.betrag_kaputt: str | None = None               # ersetzt den Betrag des ersten Eintrags
        self.rueckmeldung_zusatz: str | None = None         # jedem Rückmeldungstext vorangestellt
        self.referenzen: list[str] = []                     # alle ausgegebenen Auftragsreferenzen
        self.system_ids: list[str] = []                     # alle ausgegebenen Kundensystem-IDs
        self.letzte_url: str | None = None
        self.anfragen: list[Anfrage] = []
        self.interne_fehler: list[str] = []
        self.pins_falsch = 0
        self.tans_empfangen = 0
        self._dialoge: dict[str, _Dialog] = {}
        self._auftraege: dict[str, _Auftrag] = {}
        self._sperre = threading.Lock()
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ Betrieb
    @classmethod
    def aus_datei(cls, pfad: Path, **kw) -> "FintsAttrappe":
        return cls(json.loads(Path(pfad).read_text(encoding="utf-8")), **kw)

    def starte(self) -> "FintsAttrappe":
        attrappe = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):  # keine Ausgabe
                pass

            def do_POST(self):  # noqa: N802
                laenge = int(self.headers.get("Content-Length") or 0)
                roh = self.rfile.read(laenge)
                if attrappe.verzoegerung:
                    time.sleep(attrappe.verzoegerung)
                if attrappe.http_status != 200:
                    self.send_response(attrappe.http_status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                try:
                    antwort = attrappe.verarbeite(base64.b64decode(roh))
                except Exception:  # noqa: BLE001 - Fehler der Attrappe sichtbar machen
                    import traceback  # noqa: PLC0415
                    attrappe.interne_fehler.append(traceback.format_exc())
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                inhalt = base64.b64encode(antwort)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(inhalt)))
                self.end_headers()
                self.wfile.write(inhalt)

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        if self.tls is not None:
            self._server.socket = self.tls.server_kontext().wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, name="fints-attrappe", daemon=True)
        self._thread.start()
        self.letzte_url = self.url          # bleibt nach dem Stoppen lesbar (M29: Verbotsliste des Diagnoseprotokolls)
        return self

    def stoppe(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "FintsAttrappe":
        return self.starte()

    def __exit__(self, *a) -> None:
        self.stoppe()

    @property
    def url(self) -> str:
        assert self._server is not None, "Attrappe nicht gestartet"
        host, port = self._server.server_address[:2]
        return f"{'https' if self.tls else 'http'}://{host}:{port}/fints"

    # ------------------------------------------------------------ Steuerung
    def lasse_tan_ablaufen(self) -> None:
        with self._sperre:
            for a in self._auftraege.values():
                a.abgelaufen = True

    @property
    def segmentarten(self) -> set[str]:
        return {s for a in self.anfragen for s in a.segmente}

    @property
    def offene_auftraege(self) -> int:
        return len(self._auftraege)

    # ------------------------------------------------------------ Protokoll
    def verarbeite(self, nachricht: bytes) -> bytes:
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        seq = types.SegmentSequence(nachricht)
        alle = list(seq.find_segments())
        hnhbk = seq.find_segment_first("HNHBK")
        bezug = (str(hnhbk.dialog_id), int(hnhbk.message_number))
        with self._sperre:
            did = str(hnhbk.dialog_id)
            if did == "0":
                did = "D" + uuid.uuid4().hex[:12]
                self._dialoge[did] = _Dialog(did)
            d = self._dialoge.setdefault(did, _Dialog(did))
            d.nachrichten += 1
            nummer = d.nachrichten
            sig = seq.find_segment_first("HNSHA")
            uds = getattr(sig, "user_defined_signature", None) if sig else None
            pin = str(uds.pin) if uds is not None and uds.pin is not None else None
            tan = str(uds.tan) if uds is not None and uds.tan is not None else None
            hkvvb = seq.find_segment_first("HKVVB")
            self.anfragen.append(Anfrage(did, [s.header.type for s in alle], pin is not None, tan is not None,
                                         str(hkvvb.product_name) if hkvvb else None))
            innen = self._antwort(seq, d, pin, tan)
        return self._umschlag(did, nummer, innen, bezug)

    def _umschlag(self, did: str, nummer: int, innen: list, bezug: tuple[str, int] | None = None) -> bytes:
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        jetzt = dt.datetime.now(BERLIN)
        segs = [
            message.HNHBK3(message_size=0, hbci_version=300, dialog_id=did, message_number=nummer,
                           reference_message=formals.ReferenceMessage(*bezug) if bezug else None),
            message.HNVSK3(
                security_profile=formals.SecurityProfile("PIN", 2), security_function="998",
                security_role="1",
                security_identification_details=formals.SecurityIdentificationDetails("2", None, "0"),
                security_datetime=formals.SecurityDateTime("1", jetzt.date(), jetzt.time().replace(microsecond=0)),
                encryption_algorithm=formals.EncryptionAlgorithm("2", "2", "13", b"\x00" * 8, "5", "1"),
                key_name=formals.KeyName(formals.BankIdentifier("280", self.daten["blz"]), "0", "V", 0, 0),
                compression_function="0",
            ),
            None,
            message.HNHBS1(message_number=nummer),
        ]
        segs[1].header.number = 998
        nr = 1
        for s in [segs[0]] + list(innen) + [segs[3]]:
            s.header.number = nr
            nr += 1

        def roh(seg) -> bytes:
            # Leere Datenelemente am Segmentende weglassen (FinTS-Formals 3.0 B.1); python-fints füllt
            # wiederholbare Gruppen wie in HIUPD bis zur Höchstzahl auf, das lehnen strengere Clients ab.
            b = types.SegmentSequence([seg]).render_bytes()
            if b.endswith(b"'") and not re.search(rb"@\d+@", b):
                b = b[:-1].rstrip(b"+") + b"'"
            return b

        inhalt = b"".join(roh(x) for x in innen)
        hnvsd = b"HNVSD:999:1+@%d@" % len(inhalt) + inhalt + b"'"
        teile = [roh(segs[1]), hnvsd, roh(segs[3])]
        laenge = len(roh(segs[0])) + sum(len(t) for t in teile)
        segs[0].message_size = laenge
        return roh(segs[0]) + b"".join(teile)

    # ------------------------------------------------------------ Antworten
    def _antwort(self, seq, d: _Dialog, pin: str | None, tan: str | None) -> list:
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        R = formals.Response
        aus: list = []
        rueck: list = []          # (bezugssegmentnummer, [Response])

        def rms(seg, *antworten):
            rueck.append((seg.header.number, list(antworten)))

        if pin is None:
            return [dialog.HIRMG2(responses=[R("9800", None, "Dialog abgebrochen"),
                                             R("9110", None, "PIN fehlt")])]
        if self.gesperrt:
            return [dialog.HIRMG2(responses=[R("9800", None, "Dialog abgebrochen"),
                                             R("3938", None, "Zugang vorläufig gesperrt")])]
        if pin != self.daten["pin"]:
            self.pins_falsch += 1
            if self.pins_falsch >= 3:
                self.gesperrt = True
            return [dialog.HIRMG2(responses=[R("9800", None, "Dialog abgebrochen"),
                                             R("9931", None, "PIN ungültig")])]
        self.pins_falsch = 0
        d.pin_geprueft = True

        hkidn = seq.find_segment_first("HKIDN")
        if hkidn is not None:
            if str(hkidn.bank_identifier.bank_code) != self.daten["blz"] or str(hkidn.customer_id) != self._kunde():
                return [dialog.HIRMG2(responses=[R("9800", None, "Dialog abgebrochen"),
                                                 R("9010", None, "Kunde unbekannt")])]
            hkvvb = seq.find_segment_first("HKVVB")
            antworten = []
            if hkvvb is None or int(hkvvb.bpd_version) != self._bpd_version():
                antworten.append(R("3050", None, "BPD nicht mehr aktuell, aktuelle Version enthalten."))
                aus.extend(self._bpd())
            if hkvvb is None or int(hkvvb.upd_version) != self._upd_version():
                antworten.append(R("3050", None, "UPD nicht mehr aktuell, aktuelle Version enthalten."))
                aus.extend(self._upd())
            if self.erlaubte_verfahren is not None:
                antworten.append(R("3920", None, "Zugelassene TAN-Verfahren", list(self.erlaubte_verfahren)))
            antworten.append(R("0020", None, "Dialoginitialisierung erfolgreich"))
            rms(hkidn, *antworten)
        hksyn = seq.find_segment_first("HKSYN")
        if hksyn is not None:
            self.system_ids.append("SYS" + uuid.uuid4().hex[:10])
            hisyn = dialog.HISYN4(system_id=self.system_ids[-1])
            hisyn.header.reference = hksyn.header.number
            aus.append(hisyn)
            rms(hksyn, R("0020", None, "Kundensystem-ID zurückgemeldet"))
        # M29: TAN bei der Anmeldung (fints.md 3.5a, 6)
        hktan = seq.find_segment_first("HKTAN")
        abruf = seq.find_segment_first("HKCAZ") or seq.find_segment_first("HKKAZ")
        anmeldung_tan = False
        if hkidn is not None and (self.tan_anmeldung == "immer" or (
                self.tan_anmeldung == "einmal" and not self.anmeldung_freigegeben)):
            d.anmeldung_ok = False
            if hktan is not None and str(hktan.tan_process) == "4" and hksyn is None and abruf is None:
                anmeldung_tan = True
                ref = "ANM-" + uuid.uuid4().hex[:16]
                self.referenzen.append(ref)
                self._auftraege[ref] = _Auftrag(referenz=ref, art="HKIDN", segmentnummer=hkidn.header.number,
                                                iban="", von=None, bis=None, aufsetzpunkt=None, version=0)
                self.anmeldungs_tans += 1
                hitan = self._hitan(ref)
                hitan.header.reference = hktan.header.number
                aus.append(hitan)
                if self.anmeldung_entkoppelt:
                    rms(hktan, R("3955", None, "Sicherheitsfreigabe erfolgt über anderen Kanal"))
                else:
                    rms(hktan, R("0030", None, "Auftrag empfangen, Sicherheitsfreigabe erforderlich"))
        if not d.anmeldung_ok:
            # ohne starke Kundenauthentifizierung keine Geschäftsvorfälle in diesem Dialog
            for art_ in ("HKSPA", "HKCAZ", "HKKAZ", "HKSAL"):
                seg_ = seq.find_segment_first(art_)
                if seg_ is not None:
                    rms(seg_, R("9075", None, "Starke Kundenauthentifizierung notwendig"))
        hkspa = seq.find_segment_first("HKSPA") if d.anmeldung_ok else None
        if hkspa is not None:
            hispa = self._hispa()
            hispa.header.reference = hkspa.header.number
            aus.append(hispa)
            rms(hkspa, R("0020", None, "Auftrag ausgeführt"))

        if hktan is not None and str(hktan.tan_process) == "4" and abruf is None and not anmeldung_tan:
            # Dialogbeginn (HKIDN) – keine starke Kundenauthentifizierung nötig
            rms(hktan, R("3076", None, "Starke Kundenauthentifizierung nicht notwendig"))
        if abruf is not None and d.anmeldung_ok:
            self._abruf_annehmen(abruf, hktan, d, aus, rms)
        if hktan is not None and str(hktan.tan_process) == "2":
            self._tan_pruefen(hktan, tan, d, aus, rms)
        hksal = seq.find_segment_first("HKSAL")
        if hksal is not None and d.anmeldung_ok:
            self._saldo(hksal, aus, rms)
        hkend = seq.find_segment_first("HKEND")
        if hkend is not None:
            rms(hkend, R("0100", None, "Dialog beendet"))

        if self.rueckmeldung_zusatz:
            for _, antworten_ in rueck:
                for r_ in antworten_:
                    r_.text = (self.rueckmeldung_zusatz + " " + str(r_.text))[:80]
        hirms = [dialog.HIRMS2(responses=a) for _, a in rueck]
        for h, (bezug, _) in zip(hirms, rueck):
            h.header.reference = bezug
        fehler = any(r.code.startswith("9") for _, a in rueck for r in a)
        kopf = dialog.HIRMG2(responses=[R("9050", None, "Teilweise fehlerhaft") if fehler
                                        else R("0010", None, "Nachricht entgegengenommen")])
        return [kopf, *hirms, *aus]

    def _kunde(self) -> str:
        return self.daten.get("kunden_id") or self.daten["benutzer"]

    def _upd_version(self) -> int:
        # W-016 (E-290): andere Benutzerparameter → andere Version, wie bei einer Bank (fints.md 6);
        # Vorgaben unverändert 1 bzw. 2 (mit Saldo).
        return ((2 if self.saldo_anbieten else 1) + 10 * self.upd_ohne_kontoart + 20 * self.upd_ohne_iban
                + 40 * self.upd_ohne_konten)

    def _bpd_version(self) -> int:
        if self.saldo_anbieten:
            return (7 if self.profil == "camt" else 8) + 100
        return 7 if self.profil == "camt" else 8

    def _bpd(self) -> list:
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        t = self.daten["tan_verfahren"]
        bpa = bank.HIBPA3(bpd_version=self._bpd_version(),
                          bank_identifier=formals.BankIdentifier("280", self.daten["blz"]),
                          bank_name=self.daten["bank_name"], number_tasks=3,
                          supported_languages=formals.SupportedLanguages2(["1"]),
                          supported_hbci_version=formals.SupportedHBCIVersions2(["300"]),
                          max_message_length=0)
        def zweischritt_(v: dict):
            return formals.TwoStepParameters6(
                security_function=v["funktion"], tan_process="2", tech_id=v["technische_id"],
                zka_id=None, zka_version=None, name=v["name"], max_length_input=6, allowed_format="1",
                text_return_value="TAN", max_length_return_value=2048, multiple_tans_allowed=False,
                tan_time_dialog_association="1", cancel_allowed=False, sms_charge_account_required="0",
                principal_account_required="0", challenge_class_required=False, challenge_structured=False,
                initialization_mode="00", description_required="0", response_hhd_uc_required=False,
                supported_media_number=None)
        tans = auth.HITANS6(max_number_tasks=1, min_number_signatures=1, security_class=1,
                            parameter=formals.ParameterTwostepTAN6(onestep_method_allowed=False,
                                                                    multiple_tasks_allowed=False,
                                                                    task_hash_algorithm="0",
                                                                    twostep_parameters=[
                                                                        zweischritt_(v)
                                                                        for v in [t, *self.verfahren_zusatz]]))
        abrufe = {"camt": ["HKCAZ"], "mt940": ["HKKAZ"], "beide": ["HKCAZ", "HKKAZ"]}[self.profil]
        pins = auth.HIPINS1(max_number_tasks=1, min_number_signatures=1, security_class=1,
                            parameter=formals.ParameterPinTan(
                                min_pin_length=4, max_pin_length=40, max_tan_length=6,
                                user_id_field_text="Anmeldename", customer_id_field_text="Kunden-ID",
                                transaction_tans_required=[
                                    formals.TransactionTanRequired("HKSPA", False),
                                    *[formals.TransactionTanRequired(x, True) for x in abrufe],
                                    formals.TransactionTanRequired("HKSAL", False),
                                    formals.TransactionTanRequired("HKCCS", True),
                                    formals.TransactionTanRequired("HKTAN", False)]))
        spas = accounts.HISPAS1(max_number_tasks=1, min_number_signatures=1, security_class=0,
                                parameter=formals.GetSEPAAccountParameter1(
                                    single_account_query_allowed=True, national_account_allowed=False,
                                    structured_purpose_allowed=False,
                                    supported_sepa_formats=["urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"]))
        umsatz = []
        if self.profil in ("camt", "beide"):
            umsatz.append(statement.HICAZS1(max_number_tasks=1, min_number_signatures=1, security_class=1,
                                            parameter=formals.TransactionsTimeParameter1(
                                                storage_duration=360, entry_number_entries_allowed=True,
                                                all_accounts_allowed=False,
                                                supported_camt_formats=list(self.camt_formate))))
        if self.profil in ("mt940", "beide"):
            umsatz.append(types.SegmentSequence(b"HIKAZS:1:7:4+1+1+1+360:J:N'").segments[0])
        # Schreibende Geschäftsvorfälle werden angeboten, aber nie ausgeführt (Nachweis „nur lesend“)
        ueberweisung = types.SegmentSequence(b"HICCSS:1:1:4+1+1+1'").segments[0]
        saldo = ([types.SegmentSequence(b"HISALS:1:5:4+1+1+0'").segments[0],
                  types.SegmentSequence(b"HISALS:1:7:4+1+1+0'").segments[0]] if self.saldo_anbieten else [])
        return [bpa, tans, pins, spas, *umsatz, *saldo, ueberweisung]

    def _upd(self) -> list:
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        aus = [bank.HIUPA4(user_identifier=self.daten["benutzer"], upd_version=self._upd_version(), upd_usage="0")]
        abrufe = {"camt": ["HKCAZ"], "mt940": ["HKKAZ"], "beide": ["HKCAZ", "HKKAZ"]}[self.profil]
        for k in ([] if self.upd_ohne_konten else self.daten["konten"]):
            nummer = k["kontonummer"].lstrip("0") if self.upd_ohne_iban else k["kontonummer"]
            aus.append(bank.HIUPD6(
                account_information=formals.AccountInformation(nummer, None,
                                                               formals.BankIdentifier("280", self.daten["blz"])),
                iban=None if self.upd_ohne_iban else k["iban"], customer_id=self._kunde(),
                account_type=None if self.upd_ohne_kontoart else k["kontoart"],
                account_currency=k["waehrung"], name_account_owner_1=k["inhaber"],
                name_account_owner_2=k.get("inhaber2"), account_product_name=k["produkt"],
                allowed_transactions=[formals.AllowedTransaction("HKSPA", 1),
                                      *[formals.AllowedTransaction(x, 1) for x in abrufe],
                                      *([formals.AllowedTransaction("HKSAL", 1)] if self.saldo_anbieten else []),
                                      formals.AllowedTransaction("HKCCS", 1)]))
        return aus

    def _hispa(self):
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        return accounts.HISPA1(accounts=[
            formals.KTZ1(is_sepa=k.get("sepa", True), iban=k["iban"], bic=None if self.hispa_ohne_bic else k["bic"],
                         account_number=k["kontonummer"],
                         subaccount_number=None, bank_identifier=formals.BankIdentifier("280", self.daten["blz"]))
            for k in self.daten["konten"] if k.get("sepa", True) or self.hispa_mit_nicht_sepa])

    # ------------------------------------------------------------ Umsatzabruf
    def _abruf_annehmen(self, abruf, hktan, d: _Dialog, aus: list, rms) -> None:
        formals = _fints()[0]
        R = formals.Response
        art = abruf.header.type
        erlaubt = {"camt": ["HKCAZ"], "mt940": ["HKKAZ"], "beide": ["HKCAZ", "HKKAZ"]}[self.profil]
        if art not in erlaubt:
            rms(abruf, R("9120", None, "Geschäftsvorfall nicht unterstützt"))
            return
        verlangt = CAMT_052
        if art == "HKCAZ":
            # M29: verlangte Formate und gefüllte Felder der Kontoverbindung aufzeichnen (fints.md 3.3)
            formate = [str(x) for x in (abruf.supported_camt_messages.expected_type or []) if x]
            self.camt_angefordert.append(formate)
            kv = abruf.account
            bk = kv.bank_identifier
            self.camt_kontoverbindungen.append({
                "iban": bool(kv.iban), "bic": bool(kv.bic), "kontonummer": bool(kv.account_number),
                "unterkonto": bool(kv.subaccount_number),
                "bankleitzahl": bool(bk is not None and (bk.bank_code or bk.country_identifier))})
            if len(formate) != 1 or formate[0] not in self.camt_formate:
                rms(abruf, R("9930", None, "camt-Format nicht unterstützt"))
                return
            verlangt = formate[0]
        iban = str(abruf.account.iban or "")
        auftrag = _Auftrag(referenz="", art=art, segmentnummer=abruf.header.number, iban=iban,
                           von=abruf.date_start, bis=abruf.date_end,
                           aufsetzpunkt=str(abruf.touchdown_point) if abruf.touchdown_point else None,
                           version=abruf.header.version, camt=verlangt)
        sca_noetig = (self.tan_pflicht == "immer" and not d.sca_erfolgt) or (
            self.tan_pflicht == "einmal" and not self.freigegeben and not d.sca_erfolgt)
        if sca_noetig:
            if hktan is None or str(hktan.tan_process) != "4":
                rms(abruf, R("9075", None, "Starke Kundenauthentifizierung notwendig"))
                return
            auftrag.referenz = "AUF-" + uuid.uuid4().hex[:16]
            self.referenzen.append(auftrag.referenz)
            self._auftraege[auftrag.referenz] = auftrag
            hitan = self._hitan(auftrag.referenz)
            hitan.header.reference = hktan.header.number
            aus.append(hitan)
            rms(hktan, R("0030", None, "Auftrag empfangen, Sicherheitsfreigabe erforderlich"))
            return
        if hktan is not None:
            rms(hktan, R("3076", None, "Starke Kundenauthentifizierung nicht notwendig"))
        self._liefere(auftrag, aus, rms, bezug=abruf.header.number)

    def saldo_von(self, konto: dict) -> int:
        """Gebuchter Saldo laut Attrappe: anfangssaldo + saldo_versatz + gebuchte EUR-Umsätze bis heute."""
        heute = self.heute or dt.date.fromisoformat(self.daten.get("heute") or "9999-12-31")
        return konto.get("anfangssaldo", 0) + self.saldo_versatz + sum(
            u["betrag"] for u in self.daten["umsaetze"] if u["iban"] == konto["iban"] and not u["vormerkung"]
            and u["mt940"] and u["buchungstag"] <= heute.isoformat())

    def _saldo(self, hksal, aus: list, rms) -> None:
        import decimal  # noqa: PLC0415
        import fints.segments.saldo as saldo  # noqa: PLC0415
        formals = _fints()[0]
        R = formals.Response
        v = int(hksal.header.version)
        if not self.saldo_anbieten or v not in (5, 7):
            rms(hksal, R("9120", None, "Geschäftsvorfall nicht unterstützt"))
            return
        konto_ref = hksal.account
        if v == 7:
            schluessel = str(konto_ref.iban or "")
            konto = next((k for k in self.daten["konten"] if k["iban"] == schluessel), None)
        else:
            schluessel = str(konto_ref.account_number or "")
            konto = next((k for k in self.daten["konten"] if k["kontonummer"] == schluessel), None)
        self.saldo_abfragen.append((v, schluessel))
        if konto is None:
            rms(hksal, R("9210", None, "Konto unbekannt"))
            return
        if konto["iban"] in self.saldo_fehler_iban:
            rms(hksal, R("9380", None, "Saldenabfrage abgelehnt"))
            return
        heute = self.heute or dt.date.fromisoformat(self.daten.get("heute") or "9999-12-31")
        cent = self.saldo_von(konto)
        waehrung = konto.get("waehrung") or "EUR"
        kennz = formals.CreditDebit2.CREDIT if cent >= 0 else formals.CreditDebit2.DEBIT
        wert = (decimal.Decimal(abs(cent)) / 100).quantize(decimal.Decimal("0.01"))  # 0 → "0,"
        if v == 7:
            bal = formals.Balance2(credit_debit=kennz, amount=formals.Amount1(amount=wert, currency=waehrung),
                                   date=heute)
            seg = saldo.HISAL7(account=konto_ref, account_product=konto["produkt"][:30], currency=waehrung,
                               balance_booked=bal)
        else:
            bal = formals.Balance1(credit_debit=kennz, amount=wert, currency=waehrung, date=heute)
            seg = saldo.HISAL5(account=konto_ref, account_product=konto["produkt"][:30], currency=waehrung,
                               balance_booked=bal)
        seg.header.reference = hksal.header.number
        aus.append(seg)
        rms(hksal, R("0020", None, "Auftrag ausgeführt"))

    def _hitan(self, referenz: str):
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        png = base64.b64decode(self.daten["qr_png"])
        mime = b"image/png"
        matrix = len(mime).to_bytes(2, "big") + mime + len(png).to_bytes(2, "big") + png
        bis = dt.datetime.now(BERLIN) + dt.timedelta(minutes=self.tan_gueltig_minuten)
        return auth.HITAN6(tan_process="4", task_reference=referenz, challenge=self.daten["challenge"],
                           challenge_hhduc=matrix,
                           challenge_valid_until=formals.ChallengeValidUntil(bis.date(),
                                                                             bis.time().replace(microsecond=0)))

    def _tan_pruefen(self, hktan, tan: str | None, d: _Dialog, aus: list, rms) -> None:
        R = _fints()[0].Response
        ref = str(hktan.task_reference or "")
        auftrag = self._auftraege.get(ref)
        if auftrag is None:
            rms(hktan, R("9955", None, "Auftragsreferenz unbekannt oder abgelaufen"))
            return
        if tan is not None:
            self.tans_empfangen += 1
        if auftrag.abgelaufen:
            del self._auftraege[ref]
            rms(hktan, R("9955", None, "TAN-Auftrag abgelaufen"))
            return
        if tan != self.daten["tan"]:
            rms(hktan, R("9941", None, "TAN ungültig"))
            return
        del self._auftraege[ref]
        if auftrag.art == "HKIDN":
            # M29: TAN zur Anmeldung – der Dialog ist danach stark authentifiziert
            d.anmeldung_ok = True
            self.anmeldung_freigegeben = True
            rms(hktan, R("0020", None, "Sicherheitsfreigabe erfolgt"))
            return
        d.sca_erfolgt = True
        self.freigegeben = True
        rms(hktan, R("0020", None, "Sicherheitsfreigabe erfolgt"))
        self._liefere(auftrag, aus, rms, bezug=auftrag.segmentnummer)

    def _liefere(self, auftrag: _Auftrag, aus: list, rms, *, bezug: int) -> None:
        formals, accounts, auth, bank, dialog, message, statement, types = _fints()
        R = formals.Response

        class _Bezug:  # rms erwartet ein Objekt mit header.number
            class header:  # noqa: N801
                number = bezug

        konto = next((k for k in self.daten["konten"] if k["iban"] == auftrag.iban), None)
        if konto is None:
            rms(_Bezug, R("9210", None, "Konto unbekannt"))
            return
        if auftrag.iban in self.fehler_iban:
            rms(_Bezug, R("9380", None, "Auftrag abgelehnt"))
            return
        heute = self.heute or dt.date.fromisoformat(self.daten.get("heute") or "9999-12-31")
        gebucht = [u for u in self.daten["umsaetze"] if u["iban"] == auftrag.iban and not u["vormerkung"]
                   and (auftrag.art == "HKCAZ" or u["mt940"])
                   and (auftrag.von is None or u["buchungstag"] >= auftrag.von.isoformat())
                   and (auftrag.bis is None or u["buchungstag"] <= auftrag.bis.isoformat())
                   and u["buchungstag"] <= heute.isoformat()]
        vorgemerkt = [u for u in self.daten["umsaetze"] if u["iban"] == auftrag.iban and u["vormerkung"]
                      and (auftrag.von is None or u["buchungstag"] >= auftrag.von.isoformat())
                      and (auftrag.bis is None or u["buchungstag"] <= auftrag.bis.isoformat())
                      and u["sichtbar_ab"] <= heute.isoformat() and heute.isoformat() < u["sichtbar_bis"]]
        start = int(auftrag.aufsetzpunkt or 0)
        seite = gebucht[start:start + self.seitengroesse]
        weiter = start + self.seitengroesse < len(gebucht)
        antworten = [R("0020", None, "Auftrag ausgeführt")]
        if weiter:
            antworten.insert(0, R("3040", None, "Es liegen weitere Informationen vor",
                                  [str(start + self.seitengroesse)]))
        letzte = not weiter
        if auftrag.art == "HKCAZ":
            kti = formals.KTI1(iban=konto["iban"], bic=konto["bic"])
            um = self._umformen
            gebucht_xml = _camt(konto, seite, gebucht=True, format=auftrag.camt, umformen=um, erster=(start == 0))
            seg = statement.HICAZ1(account=kti, camt_descriptor=auftrag.camt,
                                   statement_booked=formals.BookedCamtStatements1(camt_statements=[gebucht_xml]),
                                   statement_pending=_camt(konto, vorgemerkt, gebucht=False, format=auftrag.camt,
                                                           umformen=um)
                                   if (letzte and vorgemerkt) else None)
        else:
            text = _mt940(konto, seite, self.daten["blz"])
            seg = types.SegmentSequence(b"HIKAZ:1:7:1+@" + str(len(text)).encode() + b"@" + text + b"'").segments[0]
        seg.header.reference = bezug
        aus.append(seg)
        rms(_Bezug, *antworten)


    # ------------------------------------------------------------ M29: Datumsformen und unlesbare Werte
    def _umformen(self, ntry: str, erster: bool) -> str:
        """Ein camt-Eintrag in der eingestellten Datumsform; beim ersten Eintrag ggf. unlesbare Werte."""
        if self.datum_form:
            ntry = re.sub(r"<Dt>(\d{4}-\d{2}-\d{2})</Dt>", lambda m: datum_in_form(m[1], self.datum_form), ntry)
        if erster and self.datum_kaputt is not None:
            ntry = re.sub(r"<BookgDt>.*?</BookgDt>", f"<BookgDt><Dt>{self.datum_kaputt}</Dt></BookgDt>", ntry, count=1)
        if erster and self.betrag_kaputt is not None:
            ntry = re.sub(r"(<Amt[^>]*>)[^<]*(</Amt>)", lambda m: m[1] + self.betrag_kaputt + m[2], ntry, count=1)
        return ntry


def datum_in_form(tag: str, form: str) -> str:
    """Datumsangabe eines camt-Eintrags in einer der Formen aus fints.md 3.4 (M29)."""
    if form == "zone":
        return f"<Dt>{tag}+02:00</Dt>"
    if form == "z":
        return f"<Dt>{tag}Z</Dt>"
    if form == "zeitpunkt":
        return f"<DtTm>{tag}T10:11:12+02:00</DtTm>"
    if form == "zeitpunkt_dt":
        return f"<Dt>{tag}T10:11:12+02:00</Dt>"
    raise ValueError(form)


# ================================================================ Formate

def _betrag_text(cent: int) -> str:
    return f"{abs(cent) // 100},{abs(cent) % 100:02d}"


def _mt940(konto: dict, umsaetze: list[dict], blz: str) -> bytes:
    zeilen = ["", ":20:STARTUMS", f":25:{blz}/{konto['kontonummer']}", ":28C:0"]
    saldo = konto.get("anfangssaldo", 0)
    tag = (umsaetze[0]["buchungstag"] if umsaetze else "2024-01-01").replace("-", "")[2:]
    zeilen.append(f":60F:{'C' if saldo >= 0 else 'D'}{tag}EUR{_betrag_text(saldo)}")
    for u in umsaetze:
        if not u["mt940"]:
            continue          # Fremdwährung: in MT940 nicht darstellbar (fints.md 3.3)
        zeilen.extend(u["mt940"].split("\n"))
        saldo += u["betrag"]
    ende = (umsaetze[-1]["buchungstag"] if umsaetze else "2024-01-01").replace("-", "")[2:]
    zeilen.append(f":62F:{'C' if saldo >= 0 else 'D'}{ende}EUR{_betrag_text(saldo)}")
    zeilen.append("-")
    return "\r\n".join(zeilen + [""]).encode("iso-8859-1")


def _camt(konto: dict, umsaetze: list[dict], *, gebucht: bool, format: str = CAMT_052, umformen=None,
          erster: bool = False) -> bytes:
    teile = [u["camt"] for u in umsaetze]
    if umformen is not None:
        teile = [umformen(x, erster and i == 0) for i, x in enumerate(teile)]
    ntry = "".join(teile)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           f'<Document xmlns="{format}">'
           '<BkToCstmrAcctRpt><GrpHdr><MsgId>KONTOR-ATTRAPPE</MsgId>'
           '<CreDtTm>2024-01-01T00:00:00</CreDtTm></GrpHdr>'
           f'<Rpt><Id>{"GEBUCHT" if gebucht else "VORGEMERKT"}</Id>'
           f'<Acct><Id><IBAN>{konto["iban"]}</IBAN></Id><Ccy>EUR</Ccy></Acct>'
           f'{ntry}</Rpt></BkToCstmrAcctRpt></Document>')
    return xml.encode("utf-8")


def fints_auftrag_nur_lesend(attrappe: FintsAttrappe) -> set[str]:
    """Segmentarten außerhalb der Leseliste (fints.md 3.6); leer bei korrektem Plugin."""
    return attrappe.segmentarten - LESEND


