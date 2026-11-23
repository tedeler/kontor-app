"""M2: Mock-Bank-Plugin mit TAN-Freigabe und PIN (plugins.md 7.2). Netzwerk gesperrt."""

from __future__ import annotations

import datetime as dt
import struct

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import neue_config
from tests.hilfen.m2 import SYNC_DATEN, SYNC_DATEN_PIN, lade_sync, mock_bank
from tests.hilfen.pfade import MOCK

UTC = dt.timezone.utc
VON, BIS = dt.date(2024, 1, 1), dt.date(2024, 6, 30)


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


def F():  # noqa: N802
    return kontor.fehler()


def TanAntwort(*a):  # noqa: N802
    return kontor.modul("kontor.plugins.bank").TanAntwort(*a)


def _ibans(daten):
    return sorted(k["iban"] for k in daten["bank"]["konten"])


def _tan_anfordern(p, iban):
    with pytest.raises(F().TanErforderlich) as info:
        p.umsaetze(iban, VON, BIS)
    return info.value


def pruefe_png(bild: bytes) -> None:
    assert isinstance(bild, bytes) and bild[:8] == b"\x89PNG\r\n\x1a\n", "kein PNG"
    laenge, art = struct.unpack(">I4s", bild[8:16])
    assert art == b"IHDR" and laenge == 13


def test_tan_szenario_bleibt_wie_m1(sd, netz_gesperrt):
    daten, _ = sd
    p = mock_bank(szenario="tan_erforderlich")
    assert len(p.konten()) == 3
    e = _tan_anfordern(p, _ibans(daten)[0])
    assert e.anforderung_id == "MOCK-TAN-2024-06-30"
    assert e.gueltig_bis == dt.datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)
    assert isinstance(e.challenge, str) and e.challenge.strip()
    pruefe_png(e.bild)
    assert e.bild_mime_typ == "image/png"
    assert e.code == "tan_erforderlich"


@pytest.mark.kern
def test_tan_freigabe(sd, netz_gesperrt):
    daten, erw = sd
    i0, i1, i2 = _ibans(daten)
    normal = mock_bank()
    p = mock_bank(szenario="tan_erforderlich")
    e = _tan_anfordern(p, i0)
    with pytest.raises(F().TanUngueltig):
        p.umsaetze(i0, VON, BIS, tan=TanAntwort(e.anforderung_id, "FALSCH-0000"))
    with pytest.raises(F().TanUngueltig):
        p.umsaetze(i0, VON, BIS, tan=TanAntwort("MOCK-TAN-1999-01-01", erw["tan"]))
    # nach falschen Versuchen bleibt die Anforderung gültig
    assert p.umsaetze(i0, VON, BIS, tan=TanAntwort(e.anforderung_id, erw["tan"])) == normal.umsaetze(i0, VON, BIS)
    # Sitzung freigegeben: weitere Abrufe ohne TAN, auch andere Konten
    for i in (i0, i1, i2):
        assert p.umsaetze(i, VON, BIS) == normal.umsaetze(i, VON, BIS)
    # eine neue Instanz ist nicht freigegeben
    _tan_anfordern(mock_bank(szenario="tan_erforderlich"), i0)
    # neuer Tag: Freigabe erloschen, neue Anforderung
    p.setze_heute(dt.date(2024, 7, 1))
    e2 = _tan_anfordern(p, i1)
    assert e2.anforderung_id == "MOCK-TAN-2024-07-01"
    assert e2.gueltig_bis == dt.datetime(2024, 7, 1, 23, 59, 59, tzinfo=UTC)
    with pytest.raises(F().TanUngueltig):
        p.umsaetze(i1, VON, BIS, tan=TanAntwort(e.anforderung_id, erw["tan"]))


def test_tan_bild_deterministisch(netz_gesperrt):
    a = _tan_anfordern(mock_bank(szenario="tan_erforderlich"), lade_sync()[1]["ibans"]["giro"])
    b = _tan_anfordern(mock_bank(szenario="tan_erforderlich"), lade_sync()[1]["ibans"]["spar"])
    assert a.bild == b.bild and a.challenge == b.challenge


def test_vorgabe_tan_ohne_schluessel(netz_gesperrt):
    """Mock-Datei ohne ``bank.tan`` (M1-Fixture): richtige TAN ist 123456."""
    import json
    daten = json.loads((MOCK / "mock_daten.json").read_text(encoding="utf-8"))
    iban = daten["bank"]["konten"][0]["iban"]
    p = mock_bank(MOCK / "mock_daten.json", "tan_erforderlich", "2024-12-31")
    e = _tan_anfordern(p, iban)
    with pytest.raises(F().TanUngueltig):
        p.umsaetze(iban, VON, BIS, tan=TanAntwort(e.anforderung_id, "654321"))
    assert p.umsaetze(iban, VON, BIS, tan=TanAntwort(e.anforderung_id, "123456")) == \
        mock_bank(MOCK / "mock_daten.json", "normal", "2024-12-31").umsaetze(iban, VON, BIS)


@pytest.mark.parametrize("szenario", ["normal", "token_ablauf"])
def test_tan_in_anderen_szenarien_ignoriert(sd, szenario, netz_gesperrt):
    daten, _ = sd
    i = _ibans(daten)[0]
    p = mock_bank(szenario=szenario)
    assert p.umsaetze(i, VON, BIS, tan=TanAntwort("egal", "egal")) == p.umsaetze(i, VON, BIS)


# ------------------------------------------------------------------ PIN


class Quelle:
    def __init__(self, wert):
        self.wert, self.aufrufe = wert, 0

    def __call__(self):
        self.aufrufe += 1
        return self.wert


@pytest.mark.kern
def test_pin_verlangt(sd, netz_gesperrt):
    daten, erw = sd
    i = _ibans(daten)[0]
    for quelle in (None, Quelle(None)):
        kw = {} if quelle is None else {"pin_quelle": quelle}
        p = mock_bank(SYNC_DATEN_PIN, **kw)
        with pytest.raises(F().BankPinFehlt):
            p.konten()
        with pytest.raises(F().BankPinFehlt):
            p.umsaetze(i, VON, BIS)
    falsch = mock_bank(SYNC_DATEN_PIN, pin_quelle=Quelle("FALSCH-PIN-0000"))
    with pytest.raises(F().BankPinFalsch):
        falsch.konten()
    with pytest.raises(F().BankPinFalsch):
        falsch.umsaetze(i, VON, BIS)
    richtig = mock_bank(SYNC_DATEN_PIN, pin_quelle=Quelle(erw["pin"]))
    assert richtig.konten() == mock_bank().konten()
    assert richtig.umsaetze(i, VON, BIS) == mock_bank().umsaetze(i, VON, BIS)


def test_pin_quelle_erst_bei_bedarf_und_jedes_mal(sd, netz_gesperrt):
    daten, erw = sd
    q = Quelle(erw["pin"])
    p = mock_bank(SYNC_DATEN_PIN, pin_quelle=q)
    assert q.aufrufe == 0, "pin_quelle darf beim Erzeugen nicht aufgerufen werden"
    p.konten()
    n = q.aufrufe
    assert n >= 1
    q.wert = None
    with pytest.raises(F().BankPinFehlt):
        p.umsaetze(_ibans(daten)[0], VON, BIS)
    assert q.aufrufe > n


def test_ohne_pin_schluessel_keine_pin(sd, netz_gesperrt):
    p = mock_bank(SYNC_DATEN, pin_quelle=Quelle(None))
    assert len(p.konten()) == 3
    assert mock_bank(None).konten()


def test_pin_vor_szenariofehler(sd, netz_gesperrt):
    p = mock_bank(SYNC_DATEN_PIN, szenario="bankfehler")
    with pytest.raises(F().BankPinFehlt):
        p.konten()
    p = mock_bank(SYNC_DATEN_PIN, szenario="bankfehler", pin_quelle=Quelle(lade_sync()[1]["pin"]))
    with pytest.raises(F().BankVerbindungsFehler):
        p.konten()


@pytest.mark.kern
def test_pin_nie_in_fehlern_oder_repr(sd, netz_gesperrt):
    daten, erw = sd
    i = _ibans(daten)[0]
    for wert in (erw["pin"], "FALSCH-PIN-0000-GEHEIM"):
        p = mock_bank(SYNC_DATEN_PIN, "tan_erforderlich", pin_quelle=Quelle(wert))
        texte = [repr(p), str(p)]
        for aufruf in (p.konten, lambda: p.umsaetze(i, VON, BIS)):
            try:
                aufruf()
            except F().PluginFehler as e:
                texte += [str(e), e.meldung, repr(e), repr(e.details), repr(e.args)]
                assert e.meldung.strip()
        for t in texte:
            assert wert not in t, f"PIN in {t!r}"
        assert erw["tan"] not in " ".join(texte)


def test_erzeuge_bank_plugin_reicht_pin_quelle(tmp_path, sd, netz_gesperrt):
    _, erw = sd
    c = neue_config(tmp_path, mock_modus=True, mock_daten=SYNC_DATEN_PIN, mock_heute=dt.date(2024, 6, 30))
    p = kontor.plugins()
    with pytest.raises(F().BankPinFehlt):
        p.erzeuge_bank_plugin(c).konten()
    assert len(p.erzeuge_bank_plugin(c, pin_quelle=lambda: erw["pin"]).konten()) == 3
