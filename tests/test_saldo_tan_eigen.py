"""Eigene Tests zum Feature saldo-tan (D-240, D-241): Saldenabfrage mit HKTAN Prozess 4, Diagnosezeilen,
Startwarnung bei fehlender PIN-Datei. Nur synthetische Daten, keine Verbindungen nach außen."""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kontor.plugins import fints as modul
from kontor.plugins.fints import FintsBankPlugin

IBAN = "DE57000000000532013000"


class _Diag:
    def __init__(self) -> None:
        self.zeilen: list[str] = []

    def eintrag(self, text: str) -> None:
        self.zeilen.append(text)


def _hisal(betrag="1234.56", kz="C"):
    return SimpleNamespace(balance_booked=SimpleNamespace(amount=Decimal(betrag), currency="EUR",
                                                          credit_debit=kz, date=dt.date(2026, 11, 22)),
                           header=SimpleNamespace(reference=None))


class _Antwort:
    """Antwort der Bank: Rückmeldecodes je Segment (über die Rolle ``hksal``/``hktan``) und HISAL-Segmente."""

    def __init__(self, codes: dict[str, list[str]], hisal: list) -> None:
        self.codes, self.hisal = codes, hisal

    def response_segments(self, _seg, art):
        return list(self.hisal) if art == "HISAL" else []

    def find_segments(self, _art):
        return []


def _plugin(monkeypatch, *, tan_noetig: bool, antwort: _Antwort, versionen_ok: bool = True):
    plugin = FintsBankPlugin()
    plugin.diagnose = _Diag()
    gesendet: list[tuple] = []
    hksal, hktan = SimpleNamespace(rolle="hksal"), SimpleNamespace(rolle="hktan")

    class _Klasse:
        _fields = {"account": SimpleNamespace(type=SimpleNamespace(from_sepa_account=lambda k: k))}

        def __new__(cls, **_kw):
            return hksal

    def finden(*_k):
        if not versionen_ok:
            raise RuntimeError("keine Version")
        return _Klasse

    client = SimpleNamespace(_find_highest_supported_command=finden,
                             _get_tan_segment=lambda seg, prozess: (gesendet.append(("tan", prozess)), hktan)[1])
    d = SimpleNamespace(client=client)
    monkeypatch.setattr(plugin, "_saldo_angeboten", lambda *_a: True)
    monkeypatch.setattr(plugin, "_tan_noetig", lambda *_a: tan_noetig)
    monkeypatch.setattr(plugin, "_senden", lambda _d, *segs: (gesendet.append(tuple(s.rolle for s in segs)), antwort)[1])
    monkeypatch.setattr(modul, "_codes", lambda a, seg=None: a.codes.get(getattr(seg, "rolle", ""), []))
    return plugin, d, gesendet


def test_saldo_mit_hktan_prozess_4_bei_3076(monkeypatch):
    antwort = _Antwort({"hksal": ["0020"], "hktan": ["3076"]}, [_hisal()])
    plugin, d, gesendet = _plugin(monkeypatch, tan_noetig=True, antwort=antwort)
    saldo = plugin._saldo(d, IBAN, object())
    assert saldo is not None and (saldo.betrag, saldo.stichtag) == (123456, dt.date(2026, 11, 22))
    assert gesendet == [("tan", "4"), ("hksal", "hktan")]
    assert plugin.diagnose.zeilen == ["Saldo: übernommen"]


@pytest.mark.parametrize("code", ["0030", "3955"])
def test_saldo_ohne_tan_wenn_die_bank_eine_freigabe_verlangt(monkeypatch, code):
    antwort = _Antwort({"hksal": [], "hktan": [code]}, [_hisal()])
    plugin, d, gesendet = _plugin(monkeypatch, tan_noetig=True, antwort=antwort)
    assert plugin._saldo(d, IBAN, object()) is None
    assert gesendet == [("tan", "4"), ("hksal", "hktan")]      # genau ein HKSAL, keine TAN (kein Prozess 2)
    assert "verlangt dafür eine TAN-Freigabe" in plugin.diagnose.zeilen[-1]


def test_saldo_ohne_tan_segment_wie_bisher(monkeypatch):
    antwort = _Antwort({"hksal": ["0020"]}, [_hisal("10.00", "D")])
    plugin, d, gesendet = _plugin(monkeypatch, tan_noetig=False, antwort=antwort)
    assert plugin._saldo(d, IBAN, object()).betrag == -1000
    assert gesendet == [("hksal",)]


@pytest.mark.parametrize("antwort, versionen_ok, text", [
    (_Antwort({"hksal": ["9380"]}, []), True, "Saldo: von der Bank abgelehnt (9380)"),
    (_Antwort({"hksal": ["0020"]}, []), True, "Saldo: die Antwort enthält kein HISAL"),
    (_Antwort({"hksal": ["0020"]}, [_hisal("1.005")]), True, "Saldo: Antwort ohne verwertbaren gebuchten Saldo in EUR"),
    (_Antwort({}, []), False, "Saldo: nicht abgefragt, keine passende HKSAL-Version (RuntimeError)"),
])
def test_jeder_fall_ohne_saldo_steht_im_diagnoseprotokoll(monkeypatch, antwort, versionen_ok, text):
    plugin, d, _ = _plugin(monkeypatch, tan_noetig=False, antwort=antwort, versionen_ok=versionen_ok)
    assert plugin._saldo(d, IBAN, object()) is None
    assert plugin.diagnose.zeilen == [text]


def test_diagnosezeilen_ohne_persoenliche_daten(monkeypatch):
    antwort = _Antwort({"hksal": ["0020"], "hktan": ["3076"]}, [_hisal("98765.43")])
    plugin, d, _ = _plugin(monkeypatch, tan_noetig=True, antwort=antwort)
    plugin._saldo(d, IBAN, object())
    text = " ".join(plugin.diagnose.zeilen)
    assert IBAN not in text and "98765" not in text


# ---------------------------------------------------------------- Startwarnung (D-241)

def _app(tmp_path, creds: bool):
    from kontor.app import create_app
    from kontor.config import KontorConfig
    verzeichnis = tmp_path / "creds"
    verzeichnis.mkdir()
    if creds:
        (verzeichnis / "kontor-bank-pin").write_text("12345\n")
    return create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", bank_plugin="fints",
                                   bank_pin_quelle="systemd-creds", credentials_verzeichnis=verzeichnis))


@pytest.mark.parametrize("creds", [False, True])
def test_warnung_wenn_die_pin_datei_fehlt(tmp_path, caplog, creds):
    with caplog.at_level(logging.WARNING):
        _app(tmp_path, creds)
    gewarnt = any("keine Datei kontor-bank-pin" in r.getMessage() for r in caplog.records)
    assert gewarnt is (not creds)
    assert "12345" not in caplog.text
