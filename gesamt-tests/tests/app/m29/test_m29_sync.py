"""M29: Synchronisation mit dem Bankzugang – ausgewählte Konten, TAN bei der Anmeldung im Lauf, Bankzugang ohne
Neustart wirksam (synchronisation.md 21.1, bankzugang.md 4; E-265). Echtmodus gegen die lokale FinTS-Attrappe."""

from __future__ import annotations

import base64

import pytest

from tests.hilfen import m6_orakel as orakel
from tests.hilfen.api import Api, fehlercode
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe, camt_format
from tests.hilfen.m6 import (
    BIS, PRODUKT, VON, config, echt_api, fints_daten, fints_felder, giro, pin_setzen, sync, tan_antwort,
)
from tests.hilfen.m29 import konten_abrufen, konten_mit_tan, konten_waehlen, soll_konten, zugang, zugang_setzen

pytestmark = pytest.mark.kern
ZEITRAUM = {"von": VON.isoformat(), "bis": BIS.isoformat()}


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


def _api(tmp_path, a, daten, **extra) -> Api:
    api = echt_api(tmp_path, **fints_felder(a, daten, **extra))
    pin_setzen(api, daten["pin"])
    return api


def _ibans_mit_buchungen(api: Api) -> set[str]:
    konten = {k["id"]: k["iban"] for k in api.konten() if k["iban"]}
    return {konten[s["konto_id"]] for b in api.alle_buchungen() for s in b["splits"] if s["konto_id"] in konten}


def _gebucht(api: Api, iban: str) -> list[tuple]:
    konto = next(k["id"] for k in api.konten() if k["iban"] == iban)
    return sorted((b["datum"], s["betrag"], b["extern_ids"][0]) for b in api.alle_buchungen() for s in b["splits"]
                  if s["konto_id"] == konto)


def _soll_gebucht(erw, iban: str) -> list[tuple]:
    return sorted((u["buchungstag"], u["betrag"], f"bank:{iban}:{u['umsatz_id']}")
                  for u in orakel.erwartete_umsaetze(erw, "camt", iban, VON, BIS) if not u["vormerkung"])


def _offene_tans(api: Api) -> list[dict]:
    return [t for t in api.get("/api/tan-anforderungen", erwartet=200).daten if t["status"] == "offen"]


# ------------------------------------------------------------------ ausgewählte Konten
def test_lauf_verarbeitet_genau_die_ausgewaehlten_konten(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    alle = [k["iban"] for k in soll_konten(daten)]
    auswahl = [giro(erw), next(k["iban"] for k in erw["konten"] if k["art"] == "sparkonto")]
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        assert [k["iban"] for k in konten_abrufen(api)["konten"]] == alle
        konten_waehlen(api, auswahl)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "erfolgreich", lauf
        assert sorted(k["iban"] for k in lauf["konten"]) == sorted(auswahl)
        assert _ibans_mit_buchungen(api) == set(auswahl)
        for iban in auswahl:
            assert _gebucht(api, iban) == _soll_gebucht(erw, iban), iban
        # Auswahl ändern: gilt ab dem nächsten Lauf
        konten_waehlen(api, alle)
        lauf = sync(api, **ZEITRAUM)
        assert sorted(k["iban"] for k in lauf["konten"]) == alle
        assert _ibans_mit_buchungen(api) == set(alle)
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_gespeicherte_konten_statt_kontenliste_der_bank(tmp_path, bank, netz_nur_loopback):
    """Mit gespeicherten Konten zählt deren Liste, nicht was die Bank inzwischen liefern würde."""
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        gespeichert = [k["iban"] for k in konten_abrufen(api)["konten"]]
        a.upd_ohne_konten = True       # die Bank würde jetzt fünf Konten liefern (ohne Benutzerparameter)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "erfolgreich", lauf
        assert sorted(k["iban"] for k in lauf["konten"]) == gespeichert
        assert _ibans_mit_buchungen(api) <= set(gespeichert)
        assert [k["iban"] for k in zugang(api)["konten"]] == gespeichert, "ein Lauf ändert die gespeicherten Konten nicht"
    assert not a.interne_fehler


def test_kein_konto_ausgewaehlt_kein_konto_verarbeitet(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        konten_abrufen(api)
        konten_waehlen(api, [])
        vorher = len(a.anfragen)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["konten"] == [] and lauf["tan_anforderung_id"] is None
        assert api.alle_buchungen() == [] and not [k for k in api.konten() if k["iban"]]
        assert "HKCAZ" not in {s for x in a.anfragen[vorher:] for s in x.segmente}, "kein Umsatzabruf"
    assert not a.interne_fehler


def test_ohne_gespeicherte_konten_wie_bisher(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        assert zugang(api)["konten"] == []
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "erfolgreich"
        assert sorted(k["iban"] for k in lauf["konten"]) == [k["iban"] for k in soll_konten(daten)]
        assert zugang(api)["konten"] == [], "ein Lauf speichert keine Konten im Bankzugang"
        for k in erw["konten"]:
            assert _gebucht(api, k["iban"]) == _soll_gebucht(erw, k["iban"])


# ------------------------------------------------------------------ TAN bei der Anmeldung
def test_ohne_gespeicherte_konten_scheitert_der_lauf_bei_tan_zur_anmeldung(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "fehlgeschlagen", lauf
        assert lauf["tan_anforderung_id"] is None and _offene_tans(api) == []
        assert "Einstellungen" in lauf["fehler"]["meldung"], \
            "die Meldung nennt den Weg, die Konten einmal in den Einstellungen abzurufen"
        assert api.alle_buchungen() == []
        assert a.tans_empfangen == 0


def test_lauf_wartet_auf_tan_zur_anmeldung(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"                       # jede Anmeldung verlangt eine TAN
        api = _api(tmp_path, a, daten)
        konten_mit_tan(api, daten["tan"])               # Konten einmal in den Einstellungen abrufen (mit TAN)
        konten_waehlen(api, [giro(erw)])
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "wartet_auf_tan", lauf
        tid = lauf["tan_anforderung_id"]
        t = api.get(f"/api/tan-anforderungen/{tid}", erwartet=200).daten
        assert (t["status"], t["challenge"], t["hat_bild"], t["iban"]) == ("offen", daten["challenge"], True,
                                                                          giro(erw)), "TAN-Anforderung an diesem Konto"
        bild = api.get(f"/api/tan-anforderungen/{tid}/bild", erwartet=200)
        assert bild.content == base64.b64decode(daten["qr_png"])
        assert len(_offene_tans(api)) == 1
        assert fehlercode(tan_antwort(api, tid, "000000", erwartet=422)) == "tan_ungueltig"
        lauf = tan_antwort(api, tid, daten["tan"]).daten
        for _ in range(4):                              # weitere Dialoge desselben Kontos dürfen erneut fragen
            if lauf["status"] != "wartet_auf_tan":
                break
            lauf = tan_antwort(api, lauf["tan_anforderung_id"], daten["tan"]).daten
        assert lauf["status"] == "erfolgreich", lauf
        assert [k["iban"] for k in lauf["konten"]] == [giro(erw)]
        assert _gebucht(api, giro(erw)) == _soll_gebucht(erw, giro(erw))
        assert _offene_tans(api) == []
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_lauf_mit_tan_in_jedem_dialog_und_fuer_den_abruf(tmp_path, bank, netz_nur_loopback):
    """TAN bei jeder Anmeldung und zusätzlich für den Abruf: der Lauf fragt nacheinander und endet erfolgreich."""
    daten, erw = bank
    auswahl = [giro(erw), next(k["iban"] for k in erw["konten"] if k["art"] == "kreditkonto")]
    with FintsAttrappe(daten, tan_pflicht="immer") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        konten_mit_tan(api, daten["tan"])
        konten_waehlen(api, auswahl)
        lauf = sync(api, **ZEITRAUM)
        gesehen = []
        for _ in range(12):
            if lauf["status"] != "wartet_auf_tan":
                break
            tid = lauf["tan_anforderung_id"]
            assert tid not in gesehen, "jede TAN-Anforderung ist neu"
            gesehen.append(tid)
            t = api.get(f"/api/tan-anforderungen/{tid}", erwartet=200).daten
            assert t["iban"] in auswahl and t["lauf_id"] == lauf["id"]
            lauf = tan_antwort(api, tid, daten["tan"]).daten
        assert lauf["status"] == "erfolgreich", lauf
        assert len(gesehen) >= 2, "mindestens eine TAN zur Anmeldung und eine für den Abruf"
        for iban in auswahl:
            assert _gebucht(api, iban) == _soll_gebucht(erw, iban), iban
        assert _ibans_mit_buchungen(api) == set(auswahl)
    assert not a.interne_fehler


def test_tan_zur_anmeldung_abbrechen(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        konten_mit_tan(api, daten["tan"])
        konten_waehlen(api, [giro(erw)])
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "wartet_auf_tan"
        api.post(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}/abbrechen", erwartet=200)
        assert api.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten["status"] == "abgebrochen"
        assert api.alle_buchungen() == [] and _offene_tans(api) == []


# ------------------------------------------------------------------ Bankzugang gilt ab dem nächsten Lauf
def test_bankzugang_gilt_ohne_neustart(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = Api(config(tmp_path))                    # nichts vorbelegt
        pin_setzen(api, daten["pin"])
        lauf = sync(api, **ZEITRAUM)
        assert (lauf["status"], lauf["fehler"]["code"]) == ("fehlgeschlagen", "plugin_nicht_verfuegbar")
        assert a.anfragen == [], "ohne vollständigen Zugang keine Verbindung"
        zugang_setzen(api, url=a.url, blz=daten["blz"], benutzer=daten["benutzer"], produkt_id=PRODUKT)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "erfolgreich", lauf
        assert {x.produkt_id for x in a.anfragen if x.produkt_id} == {PRODUKT}
        assert _gebucht(api, giro(erw)) == _soll_gebucht(erw, giro(erw))
        # geänderte Produkt-ID: der nächste Lauf verwendet sie
        vorher = len(a.anfragen)
        zugang_setzen(api, produkt_id="SYNTH-PRODUKT-NEU")
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich"
        assert {x.produkt_id for x in a.anfragen[vorher:] if x.produkt_id} == {"SYNTH-PRODUKT-NEU"}
        # Zugang entfernt: wieder unvollständig
        zugang_setzen(api, url=None)
        vorher = len(a.anfragen)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["fehler"]["code"] == "plugin_nicht_verfuegbar" and len(a.anfragen) == vorher


def test_gespeicherter_zugang_hat_vorrang_vor_der_vorbelegung(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as alt, FintsAttrappe(daten, tan_pflicht="nie") as neu:
        api = _api(tmp_path, alt, daten)               # Vorbelegung zeigt auf die erste Bank
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich"
        assert alt.anfragen and not neu.anfragen
        vorher = len(alt.anfragen)
        zugang_setzen(api, url=neu.url)
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich"
        assert neu.anfragen and len(alt.anfragen) == vorher, "der gespeicherte Wert gilt ab dem nächsten Lauf"
        zugang_setzen(api, url=None)
        vorher_neu = len(neu.anfragen)
        assert sync(api, **ZEITRAUM)["status"] == "erfolgreich"
        assert len(neu.anfragen) == vorher_neu and len(alt.anfragen) > vorher, "ohne gespeicherten Wert die Vorbelegung"


def test_lauf_mit_camt_version_der_bank(tmp_path, bank, netz_nur_loopback):
    """Lauf im Echtmodus mit camt in der Version der Bank und dem im Bankzugang gespeicherten Zugang."""
    daten, erw = bank
    with FintsAttrappe(daten, profil="beide", tan_pflicht="nie") as a:
        a.camt_formate = [camt_format(2), camt_format(5)]
        api = _api(tmp_path, a, daten)
        zugang_setzen(api, tan_verfahren=daten["tan_verfahren"]["funktion"])
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "erfolgreich", lauf
        assert a.camt_angefordert and all(x == [camt_format(5)] for x in a.camt_angefordert)
        assert "HKKAZ" not in a.segmentarten
        for k in erw["konten"]:
            assert _gebucht(api, k["iban"]) == _soll_gebucht(erw, k["iban"])
    assert not a.interne_fehler
