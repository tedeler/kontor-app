"""M6: Synchronisation im Echtmodus über das FinTS-Plugin und die FinTS-Attrappe (fints.md 4, 7; T 6, T 7, T 21)."""

from __future__ import annotations

import base64
import datetime as dt
import logging

import pytest

from tests.hilfen import m6_orakel as orakel
from tests.hilfen.api import Api, fehlercode
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe
from tests.hilfen.m2 import mock_config
from tests.hilfen.m6 import (
    BIS, FINTS_VERGLEICH, VON, benachrichtigungen, config, echt_api, fints_daten, fints_felder, geheimnisse_nirgends,
    giro, pin_setzen, sync, tan_antwort,
)

SPAETER = dt.date(2024, 7, 5)
ZEITRAUM = {"von": VON.isoformat(), "bis": BIS.isoformat()}


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


def _api(tmp_path, a, daten, **extra):
    api = echt_api(tmp_path, **fints_felder(a, daten, **extra))
    return api


def _buchungen_je_konto(api):
    konten = {k["id"]: k["iban"] for k in api.konten() if k["iban"]}
    aus: dict[str, list[dict]] = {}
    for b in api.alle_buchungen():
        for s in b["splits"]:
            if s["konto_id"] in konten:
                aus.setdefault(konten[s["konto_id"]], []).append({"betrag": s["betrag"], "datum": b["datum"],
                                                                   "extern_ids": b["extern_ids"]})
    return aus


@pytest.mark.kern
def test_lauf_mit_tan_und_qr_bild(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, seitengroesse=30) as a:
        api = _api(tmp_path, a, daten)
        pin_setzen(api, daten["pin"])
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "wartet_auf_tan"
        tid = lauf["tan_anforderung_id"]
        t = api.get(f"/api/tan-anforderungen/{tid}", erwartet=200).daten
        assert (t["status"], t["challenge"], t["hat_bild"]) == ("offen", daten["challenge"], True)
        assert t["iban"] == giro(erw) or t["iban"] in {k["iban"] for k in erw["konten"]}
        r = api.get(f"/api/tan-anforderungen/{tid}/bild", erwartet=200)
        assert r.headers["content-type"].split(";")[0] == "image/png"
        assert r.content == base64.b64decode(daten["qr_png"]), "Bild unverändert aus HITAN"
        b = [x for x in benachrichtigungen(api) if x["art"] == "tan_erforderlich"]
        assert len(b) == 1 and b[0]["link"] == f"/tan/{tid}"
        assert fehlercode(tan_antwort(api, tid, "000000", erwartet=422)) == "tan_ungueltig"
        lauf = tan_antwort(api, tid, daten["tan"]).daten
        assert lauf["status"] == "erfolgreich", lauf
    assert a.segmentarten <= LESEND
    konten = {k["iban"]: k for k in api.konten() if k["iban"]}
    assert set(konten) == {k["iban"] for k in erw["konten"]}
    for k in erw["konten"]:
        assert (konten[k["iban"]]["name"], konten[k["iban"]]["art"]) == (k["name"], k["art"])
    ist = _buchungen_je_konto(api)
    for k in erw["konten"]:
        soll = [u for u in orakel.erwartete_umsaetze(erw, "camt", k["iban"], VON, BIS) if not u["vormerkung"]]
        assert sorted((x["datum"], x["betrag"], x["extern_ids"][0]) for x in ist.get(k["iban"], [])) == sorted(
            (u["buchungstag"], u["betrag"], f"bank:{k['iban']}:{u['umsatz_id']}") for u in soll), k["iban"]
    sk = {x["iban"]: x for x in lauf["konten"]}
    vorgemerkt = [u for u in orakel.erwartete_umsaetze(erw, "camt", giro(erw), VON, BIS) if u["vormerkung"]]
    assert sk[giro(erw)]["vormerkungen_ignoriert"] == len(vorgemerkt) > 0


@pytest.mark.kern
def test_zweiter_lauf_ohne_tan_und_ohne_dubletten(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        api = _api(tmp_path, a, daten)
        pin_setzen(api, daten["pin"])
        lauf = sync(api, **ZEITRAUM)
        tan_antwort(api, lauf["tan_anforderung_id"], daten["tan"])
        anzahl = len(api.alle_buchungen())
        zweiter = sync(api, **ZEITRAUM)
        assert zweiter["status"] == "erfolgreich" and zweiter["tan_anforderung_id"] is None
        assert sum(k["buchungen_neu"] for k in zweiter["konten"]) == 0
        assert len(api.alle_buchungen()) == anzahl
    assert a.tans_empfangen == 1


@pytest.mark.kern
def test_vertrag_echt_gleich_mock(tmp_path, bank, netz_nur_loopback):
    """T 21: gleicher Buchbestand nach einem Lauf mit FinTS (Attrappe) und mit dem Mock-Plugin."""
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie", heute=SPAETER) as a:
        echt = _api(tmp_path / "echt", a, daten)
        pin_setzen(echt, daten["pin"])
        assert sync(echt, **ZEITRAUM)["status"] == "erfolgreich"
    mock = Api(mock_config(tmp_path / "mock", daten=FINTS_VERGLEICH, heute=SPAETER.isoformat()))
    pin_setzen(mock, daten["pin"])
    assert sync(mock, **ZEITRAUM)["status"] == "erfolgreich"
    assert echt.konten() == mock.konten()
    assert echt.alle_buchungen() == mock.alle_buchungen()
    assert echt.get("/api/empfaenger", erwartet=200).daten == mock.get("/api/empfaenger", erwartet=200).daten


@pytest.mark.kern
def test_bank_nicht_erreichbar_ohne_datenverlust(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        pin_setzen(api, daten["pin"])
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich"
        vorher = api.alle_buchungen()
        a.http_status = 503
        for _ in range(2):
            lauf = sync(api, **ZEITRAUM)
            assert (lauf["status"], lauf["fehler"]["code"]) == ("fehlgeschlagen", "bank_verbindung")
        assert api.alle_buchungen() == vorher
        assert [b["schluessel"] for b in benachrichtigungen(api)] == ["sync_fehler:bank_verbindung"]
        a.http_status = 200
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich" and api.alle_buchungen() == vorher


@pytest.mark.kern
def test_zeitueberschreitung(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.verzoegerung = 2.5
        api = _api(tmp_path, a, daten, fints_timeout_sekunden=1)
        pin_setzen(api, daten["pin"])
        lauf = sync(api, **ZEITRAUM)
        assert lauf["fehler"]["code"] == "bank_zeitueberschreitung" and api.alle_buchungen() == []
        a.verzoegerung = 0


@pytest.mark.kern
def test_ein_konto_abgelehnt_die_anderen_laufen(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    karte = next(k["iban"] for k in erw["konten"] if k["art"] == "kreditkonto")
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.fehler_iban.add(karte)
        api = _api(tmp_path, a, daten)
        pin_setzen(api, daten["pin"])
        lauf = sync(api, **ZEITRAUM)
    sk = {k["iban"]: k for k in lauf["konten"]}
    assert lauf["status"] == "fehlgeschlagen" and sk[karte]["status"] == "fehlgeschlagen"
    assert sk[karte]["fehler"]["code"] == "bank_fehler"
    assert all(k["status"] == "erfolgreich" for i, k in sk.items() if i != karte)
    assert karte not in _buchungen_je_konto(api) and giro(erw) in _buchungen_je_konto(api)


@pytest.mark.kern
@pytest.mark.parametrize("fall,code", [("falsch", "bank_pin_falsch"), ("gesperrt", "bank_zugang_gesperrt")])
def test_pin_falsch_oder_gesperrt_verwirft_pin(tmp_path, bank, fall, code, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        api = _api(tmp_path, a, daten)
        if fall == "gesperrt":
            a.gesperrt = True
            pin_setzen(api, daten["pin"])
        else:
            pin_setzen(api, "SYNTH-FALSCH-77")
        lauf = sync(api, **ZEITRAUM)
        assert (lauf["status"], lauf["fehler"]["code"]) == ("fehlgeschlagen", code)
        assert api.get("/api/sync/status", erwartet=200).daten["pin_vorhanden"] is False
        assert sync(api, **ZEITRAUM)["fehler"]["code"] == "bank_pin_fehlt"


@pytest.mark.kern
def test_tan_bei_der_bank_abgelaufen(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        api = _api(tmp_path, a, daten)
        pin_setzen(api, daten["pin"])
        lauf = sync(api, **ZEITRAUM)
        a.lasse_tan_ablaufen()
        r = tan_antwort(api, lauf["tan_anforderung_id"], daten["tan"], erwartet=409)
        assert fehlercode(r) == "tan_abgelaufen"
        assert api.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten["status"] == "abgebrochen"
        neu = sync(api, **ZEITRAUM)
        assert neu["status"] == "wartet_auf_tan" and neu["tan_anforderung_id"] != lauf["tan_anforderung_id"]


@pytest.mark.kern
def test_pin_und_tan_nirgends(tmp_path, bank, caplog, capfd, netz_nur_loopback):
    daten, _ = bank
    caplog.set_level(logging.DEBUG)
    with FintsAttrappe(daten) as a:
        api = _api(tmp_path, a, daten)
        texte = [api.put("/api/sync/pin", json={"pin": daten["pin"]}, erwartet=204).text]
        lauf = sync(api, **ZEITRAUM)
        texte.append(tan_antwort(api, lauf["tan_anforderung_id"], "918273", erwartet=422).text)
        texte.append(tan_antwort(api, lauf["tan_anforderung_id"], daten["tan"]).text)
    geheimnisse_nirgends(api, [daten["pin"], daten["tan"], "918273"], texte=texte, caplog=caplog, capfd=capfd)


@pytest.mark.kern
def test_tls_der_bank(tmp_path, bank, netz_nur_loopback):
    from tests.hilfen.tls import erzeuge_zertifikat
    daten, _ = bank
    z = erzeuge_zertifikat(tmp_path / "tls")
    with FintsAttrappe(daten, tan_pflicht="nie", tls=z) as a:
        ok = _api(tmp_path / "a", a, daten, tls_ca_datei=z.zertifikat)
        pin_setzen(ok, daten["pin"])
        assert sync(ok, **ZEITRAUM)["status"] == "erfolgreich"
        fremd = _api(tmp_path / "b", a, daten)
        pin_setzen(fremd, daten["pin"])
        assert sync(fremd, **ZEITRAUM)["fehler"]["code"] == "bank_verbindung"


def test_unkonfiguriert_ohne_verbindung(tmp_path, netz_gesperrt):
    api = Api(config(tmp_path))
    pin_setzen(api, "SYNTH-PIN")
    lauf = sync(api)
    assert (lauf["status"], lauf["fehler"]["code"]) == ("fehlgeschlagen", "plugin_nicht_verfuegbar")
    netz_gesperrt.pruefe()
