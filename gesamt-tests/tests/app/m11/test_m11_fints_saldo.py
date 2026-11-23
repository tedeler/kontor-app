"""M11: Saldo über das FinTS-Plugin gegen die FinTS-Attrappe (kontostand.md 1.2, fints.md 6; E-159).

Die Attrappe bietet HKSAL nur mit ``saldo_anbieten = True`` an; ohne bleibt alles wie in M6.
Erwartete Salden kommen aus ``FintsAttrappe.saldo_von`` (Generatordaten) bzw. dem M6-Orakel.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen import m6_orakel as orakel
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe
from tests.hilfen.m6 import BIS, VON, config, echt_api, fints_daten, fints_felder, giro, pin_setzen, sync

HEUTE = dt.date(2024, 6, 30)


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


class Pin:
    def __init__(self, wert):
        self.wert, self.aufrufe = wert, 0

    def __call__(self):
        self.aufrufe += 1
        return self.wert


def _plugin(tmp_path, a, daten):
    c = config(tmp_path, **fints_felder(a, daten))
    p = Pin(daten["pin"])
    return kontor.modul("kontor.plugins.fints").FintsBankPlugin(c, pin_quelle=p), p


def _konto(daten, iban):
    return next(k for k in daten["konten"] if k["iban"] == iban)


@pytest.fixture(params=["camt", "mt940"])
def profil(request):
    return request.param


@pytest.mark.kern
def test_ohne_angebot_kein_hksal(tmp_path, bank, profil, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, profil=profil, tan_pflicht="nie") as a:
        p, pin = _plugin(tmp_path, a, daten)
        assert getattr(p.umsaetze(giro(erw), VON, BIS), "saldo", None) is None
        assert "HKSAL" not in a.segmentarten and a.saldo_abfragen == []
        assert pin.aufrufe == 1


@pytest.mark.kern
def test_saldo_im_selben_dialog(tmp_path, bank, profil, netz_nur_loopback):
    daten, erw = bank
    BankSaldo = kontor.modul("kontor.plugins.bank").BankSaldo
    iban = giro(erw)
    with FintsAttrappe(daten, profil=profil, tan_pflicht="nie") as a:
        a.saldo_anbieten = True
        p, pin = _plugin(tmp_path, a, daten)
        r = p.umsaetze(iban, VON, BIS)
        soll = a.saldo_von(_konto(daten, iban))
        assert r.saldo == BankSaldo(iban, soll, HEUTE)
        assert [u.umsatz_id for u in r] == [u["umsatz_id"] for u in orakel.erwartete_umsaetze(
            erw, profil, iban, VON, BIS) if profil == "camt" or not u["vormerkung"]], "Umsätze unverändert"
        assert pin.aufrufe == 1, "kein zusätzlicher Dialog für den Saldo"
        assert [x[1] for x in a.saldo_abfragen] in ([iban], [_konto(daten, iban)["kontonummer"]])
        assert a.segmentarten <= LESEND
        # Soll-Saldo (negativ)
        a.saldo_versatz = -10_000_000
        assert p.umsaetze(iban, VON, BIS).saldo.betrag == soll - 10_000_000 < 0
        andere = next(k["iban"] for k in erw["konten"] if k["iban"] != iban)
        assert p.umsaetze(andere, VON, BIS).saldo == BankSaldo(andere, a.saldo_von(_konto(daten, andere)) , HEUTE)


def test_saldo_nach_tan_freigabe(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="einmal") as a:
        a.saldo_anbieten = True
        p, _ = _plugin(tmp_path, a, daten)
        with pytest.raises(kontor.fehler().TanErforderlich) as e:
            p.umsaetze(iban, VON, BIS)
        tan = kontor.modul("kontor.plugins.bank").TanAntwort(e.value.anforderung_id, daten["tan"])
        assert p.umsaetze(iban, VON, BIS, tan=tan).saldo.betrag == a.saldo_von(_konto(daten, iban))


def test_abgelehnte_saldenabfrage(tmp_path, bank, netz_nur_loopback):
    """Nur HKSAL scheitert → Umsätze unverändert, saldo() None (kontostand.md 1.2)."""
    daten, erw = bank
    iban = giro(erw)
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.saldo_anbieten = True
        a.saldo_fehler_iban = {iban}
        p, _ = _plugin(tmp_path, a, daten)
        r = p.umsaetze(iban, VON, BIS)
        ohne = [u.umsatz_id for u in r]
        assert getattr(r, "saldo", None) is None
        assert ohne == [u["umsatz_id"] for u in orakel.erwartete_umsaetze(erw, "camt", iban, VON, BIS)]


@pytest.mark.kern
def test_lauf_gleicht_anfangssaldo_aus(tmp_path, bank, netz_nur_loopback):
    """Synchronisation im Echtmodus: Differenz = Anfangssaldo der Bank (alle Umsätze im Zeitraum)."""
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.saldo_anbieten = True
        api = echt_api(tmp_path, **fints_felder(a, daten))
        pin_setzen(api, daten["pin"])
        lauf = sync(api, von=VON.isoformat(), bis=BIS.isoformat())
        assert lauf["status"] == "erfolgreich", lauf
        sk = {k["iban"]: k for k in lauf["konten"]}
        for k in erw["konten"]:
            konto = _konto(daten, k["iban"])
            bank_saldo = a.saldo_von(konto)
            kontor_saldo = sum(u["betrag"] for u in orakel.erwartete_umsaetze(erw, "camt", k["iban"], VON, BIS)
                               if not u["vormerkung"])
            sa = sk[k["iban"]]["saldo_abgleich"]
            assert (sa["bank_saldo"], sa["kontor_saldo"], sa["stichtag"]) == (bank_saldo, kontor_saldo,
                                                                               HEUTE.isoformat()), k["iban"]
            assert sa["differenz"] == bank_saldo - kontor_saldo
            assert sa["status"] == ("stimmt" if sa["differenz"] == 0 else "ausgeglichen")
            if konto.get("anfangssaldo"):
                assert sa["status"] == "ausgeglichen" and sa["buchung_id"] is not None
        lauf2 = sync(api, von=VON.isoformat(), bis=BIS.isoformat())
        assert {k["saldo_abgleich"]["status"] for k in lauf2["konten"]} == {"stimmt"}
    assert a.segmentarten <= LESEND
