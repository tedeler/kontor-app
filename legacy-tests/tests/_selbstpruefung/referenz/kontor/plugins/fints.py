"""FinTS-Plugin über python-fints (fints.md 3) – Wegwerf-Referenz, KEIN Anwendungscode."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from .. import mutant
from ..fehler import (BankFehler, BankKontoUnbekannt, BankPinFalsch, BankPinFehlt, BankVerbindungsFehler,
                      BankZeitueberschreitung, BankZugangGesperrt, PluginNichtVerfuegbar, TanAbgelaufen,
                      TanErforderlich, TanUngueltig)
from .bank import BankKonto, BankPlugin, BankSaldo, BankUmsatz, Umsatzliste
from .iban import gueltig, norm

CAMT = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"
BERLIN = ZoneInfo("Europe/Berlin")
UTC = dt.timezone.utc
PIN_CODES = {"9931", "9340", "9910", "9930", "9942"}

# python-fints schreibt auf DEBUG ganze Nachrichten (mit TAN) – nie ausgeben (fints.md 3.8)
logging.getLogger("fints.connection").disabled = not mutant("fints_tan_im_log")


def _art(kontoart: int) -> str | None:
    if 1 <= kontoart <= 9:
        return "girokonto"
    if 10 <= kontoart <= 29:
        return "sparkonto"
    if 40 <= kontoart <= 59:
        return "kreditkonto"
    return None


def _hash(u: dict, n: int) -> str:
    teile = [u["buchungstag"].isoformat(), u["valuta"].isoformat() if u["valuta"] else "", str(u["betrag"]),
             u["gegenpartei_iban"] or "", u["gegenpartei_name"] or "", u["verwendungszweck"], "S" if u["storno"] else ""]
    return "h:" + hashlib.sha256("|".join(teile).encode()).hexdigest()[:16] + f":{n}"


def _iban(t):
    if not t:
        return None
    t = norm(t)
    return t if gueltig(t) else None


def mt940(iban: str, text: str) -> list[dict]:
    felder: list[list[str]] = []
    for z in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^:([0-9]{2}[A-Z]?):(.*)$", z)
        if m:
            felder.append([m[1], m[2]])
        elif z not in ("", "-") and felder:
            felder[-1][1] += z
    aus, i = [], 0
    while i < len(felder):
        if felder[i][0] != "61":
            i += 1
            continue
        m = re.match(r"^(\d\d)(\d\d)(\d\d)(\d{4})?(RC|RD|C|D)[A-Z]?(\d+),(\d{0,2})N", felder[i][1])
        valuta = dt.date(2000 + int(m[1]), int(m[2]), int(m[3]))
        bt = valuta
        if m[4]:
            bt = dt.date(valuta.year, int(m[4][:2]), int(m[4][2:]))
            if not mutant("mt940_jahr_ohne_korrektur"):
                if (bt - valuta).days > 180:
                    bt = bt.replace(year=bt.year - 1)
                elif (valuta - bt).days > 180:
                    bt = bt.replace(year=bt.year + 1)
        cent = int(m[6]) * 100 + int((m[7] + "00")[:2])
        zeichen = {"C": 1, "D": -1, "RC": 1 if mutant("mt940_storno_vorzeichen") else -1, "RD": 1}[m[5]]
        unter = []
        if i + 1 < len(felder) and felder[i + 1][0] == "86":
            unter = re.findall(r"\?(\d\d)([^?]*)", felder[i + 1][1])
            i += 1
        aus.append({"buchungstag": bt, "valuta": valuta, "betrag": zeichen * cent,
                    "verwendungszweck": "".join(v for k, v in unter if 20 <= int(k) <= 29 or 60 <= int(k) <= 63),
                    "gegenpartei_name": "".join(v for k, v in unter if k in ("32", "33")) or None,
                    "gegenpartei_iban": _iban(next((v for k, v in unter if k == "31"), None)),
                    "vormerkung": False, "storno": m[5] in ("RC", "RD"), "ref": None})
        i += 1
    return aus


def _l(e):
    return e.tag.rsplit("}", 1)[-1]


def _k(e, *pfad):
    for n in pfad:
        if e is None:
            return None
        e = next((x for x in e if _l(x) == n), None)
    return e


def _t(e, *pfad):
    k = _k(e, *pfad)
    return k.text if k is not None else None


def _zweck(rmt) -> str:
    teile = [(x.text or "") for x in (rmt if rmt is not None else []) if _l(x) == "Ustrd"]
    if mutant("camt_nur_erster_ustrd"):
        return teile[0] if teile else ""
    return "".join(teile)


def camt(dokumente: list[bytes]) -> list[dict]:
    aus = []
    for d in dokumente:
        for n in ET.fromstring(d).iter():
            if _l(n) != "Ntry":
                continue
            amt = _k(n, "Amt")
            if amt is None or amt.get("Ccy") != "EUR":
                continue
            g, _, r = amt.text.strip().partition(".")
            cent = int(g) * 100 + int((r + "00")[:2])
            ind = _t(n, "CdtDbtInd")
            storno = (_t(n, "RvslInd") or "") == "true"
            sts = _t(n, "Sts", "Cd") or _t(n, "Sts")
            if sts not in ("BOOK", "PDNG"):
                continue
            seite = ind if (not storno or mutant("camt_gegenpartei_ohne_storno")) else (
                "CRDT" if ind == "DBIT" else "DBIT")
            partei, konto = ("Cdtr", "CdtrAcct") if seite == "DBIT" else ("Dbtr", "DbtrAcct")
            tx = _k(n, "NtryDtls", "TxDtls")
            pt = _k(tx, "RltdPties")
            rmt = _k(tx, "RmtInf")
            bt = _t(n, "BookgDt", "Dt") or _t(n, "ValDt", "Dt")
            val = _t(n, "ValDt", "Dt")
            aus.append({"buchungstag": dt.date.fromisoformat(bt), "valuta": dt.date.fromisoformat(val) if val else None,
                        "betrag": cent if ind == "CRDT" else -cent,
                        "verwendungszweck": _zweck(rmt),
                        "gegenpartei_name": _t(pt, partei, "Pty", "Nm") or _t(pt, partei, "Nm") or None,
                        "gegenpartei_iban": _iban(_t(pt, konto, "Id", "IBAN")), "vormerkung": sts == "PDNG",
                        "storno": storno, "ref": (_t(n, "AcctSvcrRef") or "").strip() or None})
    return aus


class FintsBankPlugin(BankPlugin):
    name = "fints"
    ist_mock = False

    def __init__(self, config, *, pin_quelle=None) -> None:
        self._c = config
        self._pin_quelle = pin_quelle
        self._daten: bytes | None = None
        self._offen: dict[str, dict] = {}

    def __repr__(self) -> str:
        return "<FintsBankPlugin>"

    # ------------------------------------------------------------ Verbindung
    def _konfiguriert(self) -> None:
        c = self._c
        if not (c.fints_url and c.fints_blz and c.fints_benutzer and c.fints_produkt_id):
            raise PluginNichtVerfuegbar("FinTS ist nicht konfiguriert")

    def _client(self):
        # erneut bei jedem Dialog: logging.config.dictConfig (z. B. uvicorn) schaltet Logger wieder ein
        logging.getLogger("fints.connection").disabled = not mutant("fints_tan_im_log")
        pin = self._pin_quelle() if self._pin_quelle else None
        if not pin:
            raise BankPinFehlt("Keine PIN vorhanden")
        from fints.client import FinTS3PinTanClient  # noqa: PLC0415
        c = self._c
        k = FinTS3PinTanClient(c.fints_blz, c.fints_benutzer, pin, c.fints_url, customer_id=c.fints_kunden_id,
                               product_id=c.fints_produkt_id, from_data=self._daten)
        s = k.connection.session
        roh = s.post
        verify = str(c.tls_ca_datei) if c.tls_ca_datei else True
        s.post = lambda url, **kw: roh(url, timeout=c.fints_timeout_sekunden, verify=verify, allow_redirects=False,
                                       **kw)
        if c.fints_tan_verfahren:
            k.selected_security_function = c.fints_tan_verfahren
        k._kontor_codes = []
        k.add_response_callback(lambda seg, resp: k._kontor_codes.append(str(resp.code)))
        return k

    @staticmethod
    def _uebersetze(e: BaseException) -> Exception:
        from fints import exceptions as fx  # noqa: PLC0415
        import requests  # noqa: PLC0415
        kette, x = [], e
        while x is not None:
            kette.append(x)
            x = x.__cause__ or x.__context__
        if any(isinstance(x, (requests.exceptions.Timeout, TimeoutError)) for x in kette):
            return BankZeitueberschreitung("Zeitüberschreitung bei der Bank")
        if any(isinstance(x, fx.FinTSClientTemporaryAuthError) for x in kette):
            return BankZugangGesperrt("Der Bankzugang ist gesperrt")
        if any(isinstance(x, fx.FinTSClientPINError) for x in kette):
            return BankPinFalsch("Die Bank hat die PIN abgelehnt")
        if any(isinstance(x, (fx.FinTSConnectionError, requests.exceptions.RequestException, OSError)) for x in kette):
            return BankVerbindungsFehler("Die Bank ist nicht erreichbar")
        return BankFehler("Fehler der Bank")

    def _schliessen(self, k) -> None:
        try:
            k.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass

    def _sitzung(self, k) -> None:
        try:
            k.__enter__()
        except Exception as e:  # noqa: BLE001
            raise self._uebersetze(e) from None

    def _kontenliste(self, k) -> tuple[list[BankKonto], dict]:
        sepa = {norm(a.iban): a for a in k.get_sepa_accounts() if a.iban}
        info = k.get_information()
        aus = []
        for a in info["accounts"]:
            iban = norm(a["iban"] or "")
            art = _art(int(a["type"] or 0))
            if iban not in sepa or art is None or a["currency"] != "EUR":
                continue
            bic = sepa[iban].bic or None
            aus.append(BankKonto(iban, bic, (a["product_name"] or ""), art, " ".join(a["owner_name"]), "EUR"))
        aus.sort(key=lambda b: b.iban)
        return aus, sepa

    # ------------------------------------------------------------ Schnittstelle
    def konten(self) -> list[BankKonto]:
        self._konfiguriert()
        k = self._client()
        self._sitzung(k)
        try:
            return self._kontenliste(k)[0]
        except Exception as e:  # noqa: BLE001
            raise self._uebersetze(e) from None
        finally:
            self._daten = k.deconstruct(including_private=True)
            self._schliessen(k)

    def tan_verfahren(self) -> list[tuple[str, str]]:
        """M29 (fints.md 3.0), kleinste Fassung: erlaubte Zwei-Schritt-Verfahren ohne Geschäftsvorfall."""
        self._konfiguriert()
        k = self._client()
        try:
            k.fetch_tan_mechanisms()
            return [(str(f), str(p.name)) for f, p in k.get_tan_mechanisms().items() if str(f) != "999"]
        except Exception as e:  # noqa: BLE001
            raise self._uebersetze(e) from None

    def umsaetze(self, iban, von, bis, *, tan=None) -> list[BankUmsatz]:
        self._konfiguriert()
        if von > bis:
            raise ValueError("von > bis")
        iban = norm(iban)
        if tan is not None:
            return self._mit_tan(iban, von, bis, tan)
        k = self._client()
        self._sitzung(k)
        offen_lassen = False
        try:
            konten, sepa = self._kontenliste(k)
            if iban not in {b.iban for b in konten}:
                raise BankKontoUnbekannt("Konto unbekannt")
            konto = sepa[iban]
            camt_ok = any(CAMT in list(getattr(s.parameter, "supported_camt_formats", []) or [])
                          for s in k.bpd.find_segments("HICAZS"))
            if camt_ok:
                r = k.get_transactions_xml(konto, von, bis, supported_camt_messages=[CAMT])
            else:
                r = self._mt940_roh(k, konto, von, bis)
            from fints.client import NeedTANResponse  # noqa: PLC0415
            if isinstance(r, NeedTANResponse):
                aid = str(r.tan_request.task_reference or uuid.uuid4().hex)
                self._offen[aid] = {"k": k, "r": r, "camt": camt_ok, "iban": iban, "konto": konto}
                offen_lassen = True
                raise self._tan_erforderlich(aid, r)
            aus = self._ergebnis(k, iban, von, bis, r, camt_ok)
            return Umsatzliste(aus, saldo=self._saldo_holen(k, konto, iban))
        except (TanErforderlich, BankKontoUnbekannt, BankFehler, PluginNichtVerfuegbar):
            raise
        except Exception as e:  # noqa: BLE001
            raise self._uebersetze(e) from None
        finally:
            self._daten = k.deconstruct(including_private=True)
            if not offen_lassen:
                self._schliessen(k)

    def _mt940_roh(self, k, konto, von, bis):
        from fints.segments.statement import HKKAZ5, HKKAZ6, HKKAZ7  # noqa: PLC0415
        hkkaz = k._find_highest_supported_command(HKKAZ5, HKKAZ6, HKKAZ7)
        return k._fetch_with_touchdowns(
            k._standing_dialog,
            lambda td: hkkaz(account=hkkaz._fields["account"].type.from_sepa_account(konto), all_accounts=False,
                             date_start=von, date_end=bis, touchdown_point=td),
            lambda segs: b"".join(s.statement_booked for s in segs), "HIKAZ")

    @staticmethod
    def _tan_erforderlich(aid, r) -> TanErforderlich:
        bis = dt.datetime.now(UTC).replace(microsecond=0) + dt.timedelta(minutes=5)
        g = getattr(r.tan_request, "challenge_valid_until", None)
        if g is not None and g.date and g.time:
            bis = dt.datetime.combine(g.date, g.time, BERLIN).astimezone(UTC)
        bild, mime = None, None
        if r.challenge_matrix:
            mime, bild = r.challenge_matrix
        return TanErforderlich("TAN erforderlich", anforderung_id=aid, gueltig_bis=bis,
                               challenge=r.challenge or "Bitte TAN eingeben", bild=bild, bild_mime_typ=mime)

    def _mit_tan(self, iban, von, bis, tan) -> list[BankUmsatz]:
        o = self._offen.get(tan.anforderung_id)
        if o is None:
            raise TanUngueltig("TAN-Anforderung unbekannt")
        k = o["k"]
        k._kontor_codes.clear()
        try:
            r = k.send_tan(o["r"], tan.tan)
        except Exception as e:  # noqa: BLE001
            self._offen.pop(tan.anforderung_id, None)
            self._schliessen(k)
            raise self._uebersetze(e) from None
        codes = set(k._kontor_codes)
        if "9941" in codes and not mutant("fints_tan_ungueltig_leer"):
            raise TanUngueltig("Die Bank hat die TAN abgelehnt")
        self._offen.pop(tan.anforderung_id, None)
        try:
            if "9955" in codes:
                raise TanAbgelaufen("TAN-Anforderung abgelaufen")
            aus = self._ergebnis(k, iban, von, bis, r, o["camt"])
            return Umsatzliste(aus, saldo=self._saldo_holen(k, o["konto"], iban))
        finally:
            self._daten = k.deconstruct(including_private=True)
            self._schliessen(k)

    def _ergebnis(self, k, iban, von, bis, r, camt_ok) -> list[BankUmsatz]:
        codes = set(k._kontor_codes)
        if "9210" in codes:
            raise BankKontoUnbekannt("Konto unbekannt")
        fehler = sorted(c for c in codes if c.startswith("9") and c != "9050")
        if fehler:
            raise BankFehler("Auftrag abgelehnt", rueckmeldung=fehler[0])
        if camt_ok:
            gebucht, vorgemerkt = r
            roh = camt(list(gebucht) + [x for x in vorgemerkt if x])
        else:
            roh = mt940(iban, r.decode("iso-8859-1"))
        gezaehlt: dict[str, int] = {}
        aus = []
        for u in roh:
            if u["ref"] and not mutant("fints_ohne_referenz"):
                uid = "ref:" + u["ref"]
            else:
                h = _hash(u, 0)
                gezaehlt[h] = gezaehlt.get(h, 0) + 1
                uid = _hash(u, 1 if mutant("fints_hash_ohne_nummer") else gezaehlt[h])
            if not von <= u["buchungstag"] <= bis:
                continue
            aus.append(BankUmsatz(uid, iban, u["buchungstag"], u["valuta"], u["betrag"], "EUR", u["gegenpartei_name"],
                                  u["gegenpartei_iban"], u["verwendungszweck"], u["vormerkung"], u["storno"]))
        aus.sort(key=lambda u: (u.buchungstag, u.umsatz_id))
        return aus

    def _saldo_holen(self, k, konto, iban):
        """M11: HKSAL im selben Dialog, nur wenn die BPD es anbieten (kontostand.md 1.2)."""
        try:
            if not list(k.bpd.find_segments("HISALS")):
                return None
            k._kontor_codes.clear()
            bal = k.get_balance(konto)
            if any(c.startswith("9") for c in k._kontor_codes) or bal is None:
                return None
            if str(bal.amount.currency) != "EUR":
                return None
            cent = int((bal.amount.amount * 100).to_integral_value())
            if mutant("fints_saldo_ohne_vorzeichen"):
                cent = abs(cent)
            return BankSaldo(iban, cent, bal.date)
        except Exception:  # noqa: BLE001
            return None

    def schliessen(self) -> None:
        for o in self._offen.values():
            self._schliessen(o["k"])
        self._offen.clear()
