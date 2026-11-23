"""M29: Bankzugang über REST (bankzugang.md 4, 6; E-262, E-265) – Echtmodus mit dem FinTS-Plugin gegen die lokale
FinTS-Attrappe, Mock-Modus ohne Netz."""

from __future__ import annotations

import base64
import logging

import pytest

from tests.hilfen import m9
from tests.hilfen.api import Api
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe
from tests.hilfen.m2 import mock_config
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m6 import (
    BIS, PRODUKT, VON, config, echt_api, fints_daten, fints_felder, geheimnisse_nirgends, giro, pin_setzen, sync,
)
from tests.hilfen.m7 import anmelden, m7_config
from tests.hilfen.m29 import (
    FELDER, ZUGANG, ZUSATZ_VERFAHREN, bild_bytes, code, diagnose, diagnose_schalten, konten_abrufen, konten_mit_tan,
    konten_waehlen, neustart, orte, soll_konten, verfahren, zugang, zugang_konten, zugang_setzen,
)

pytestmark = pytest.mark.kern
URL = "https://banking.example.invalid/fints"
VORBELEGUNG = {"bank_plugin": "fints", "fints_url": URL, "fints_blz": "00000000", "fints_benutzer": "SYNTH-NUTZER",
               "fints_produkt_id": PRODUKT}
ZEITRAUM = {"von": VON.isoformat(), "bis": BIS.isoformat()}


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


def _api(tmp_path, a, daten, pin: bool = True, **extra) -> Api:
    api = echt_api(tmp_path, **fints_felder(a, daten, **extra))
    if pin:
        pin_setzen(api, daten["pin"])
    return api


def _pin_vorhanden(api: Api) -> bool:
    return api.get("/api/sync/status", erwartet=200).daten["pin_vorhanden"]


# ------------------------------------------------------------------ 4.1 GET
def test_get_vorbelegung_aus_der_konfiguration(tmp_path, netz_gesperrt):
    api = echt_api(tmp_path, **VORBELEGUNG, fints_kunden_id="SYNTH-KUNDE", fints_tan_verfahren="913")
    assert zugang(api) == {"url": URL, "blz": "00000000", "benutzer": "SYNTH-NUTZER", "kunden_id": "SYNTH-KUNDE",
                           "produkt_id": PRODUKT, "tan_verfahren": "913", "plugin": "fints", "aenderbar": True,
                           "gespeichert": [], "vollstaendig": True, "konten": []}
    netz_gesperrt.pruefe()


def test_get_unkonfiguriert(tmp_path, netz_gesperrt):
    api = Api(config(tmp_path))
    assert zugang(api) == {**{f: None for f in FELDER}, "plugin": "fints", "aenderbar": True, "gespeichert": [],
                           "vollstaendig": False, "konten": []}
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("fehlt", ["fints_url", "fints_blz", "fints_benutzer", "fints_produkt_id"])
def test_vollstaendig_braucht_vier_felder(tmp_path, fehlt, netz_gesperrt):
    felder = {k: v for k, v in VORBELEGUNG.items() if k != fehlt}
    api = echt_api(tmp_path, **felder)
    z = zugang(api)
    assert z["vollstaendig"] is False and z[fehlt.removeprefix("fints_")] is None
    wert = {"fints_url": URL, "fints_blz": "00000000", "fints_benutzer": "SYNTH-N2", "fints_produkt_id": "SYNTH-P2"}
    z = zugang_setzen(api, **{fehlt.removeprefix("fints_"): wert[fehlt]})
    assert z["vollstaendig"] is True and z["gespeichert"] == [fehlt.removeprefix("fints_")]
    assert zugang(api) == z
    netz_gesperrt.pruefe()


def test_get_im_mock_modus(tmp_path, netz_gesperrt):
    api = Api(mock_config(tmp_path))
    z = zugang(api)
    assert (z["plugin"], z["aenderbar"], z["gespeichert"], z["konten"]) == ("mock", False, [], [])
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ 4.2 PUT
def test_put_speichert_entfernt_und_laesst_ungenanntes(tmp_path, netz_gesperrt):
    api = echt_api(tmp_path, **VORBELEGUNG)
    vorher = zugang(api)
    assert zugang_setzen(api) == vorher, "{} ändert nichts"
    z = zugang_setzen(api, benutzer="SYNTH-ANDERER")
    assert z == {**vorher, "benutzer": "SYNTH-ANDERER", "gespeichert": ["benutzer"]}
    z = zugang_setzen(api, url="http://127.0.0.1:8123/fints", tan_verfahren="921", kunden_id="SYNTH-K")
    assert z == {**vorher, "benutzer": "SYNTH-ANDERER", "url": "http://127.0.0.1:8123/fints", "tan_verfahren": "921",
                 "kunden_id": "SYNTH-K", "gespeichert": ["benutzer", "kunden_id", "tan_verfahren", "url"]}
    assert zugang(api) == z
    z = zugang_setzen(api, benutzer=None, url="")
    assert (z["benutzer"], z["url"]) == ("SYNTH-NUTZER", URL), "ohne gespeicherten Wert gilt wieder die Vorbelegung"
    assert z["gespeichert"] == ["kunden_id", "tan_verfahren"]
    z = zugang_setzen(api, kunden_id="", tan_verfahren=None, produkt_id=None)
    assert z == vorher
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("feld,wert", [
    ("url", "https://banking.example.invalid/fints"), ("url", "http://127.0.0.1:8080/fints"),
    ("url", "http://localhost/fints"), ("url", "http://[::1]:8080/fints"), ("blz", "12345678"),
    ("benutzer", "x"), ("benutzer", "y" * 64), ("kunden_id", "k" * 64), ("produkt_id", "p" * 25),
    ("tan_verfahren", "000"), ("tan_verfahren", "913")])
def test_put_gueltige_werte(tmp_path, feld, wert, netz_gesperrt):
    api = Api(config(tmp_path))
    z = zugang_setzen(api, **{feld: wert})
    assert z[feld] == wert and z["gespeichert"] == [feld]
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("feld,wert", [
    ("url", "http://banking.example.invalid/fints"), ("url", "ftp://127.0.0.1/fints-geheim"),
    ("url", "banking.example.invalid"), ("url", "https:///ohne-host"),
    ("blz", "1234567"), ("blz", "123456789"), ("blz", "1234567X"),
    ("benutzer", "b" * 65), ("kunden_id", "k" * 65), ("produkt_id", "p" * 26),
    ("tan_verfahren", "91"), ("tan_verfahren", "9130"), ("tan_verfahren", "9a3")])
def test_put_validierung_nichts_gespeichert(tmp_path, feld, wert, netz_gesperrt):
    api = echt_api(tmp_path, **VORBELEGUNG)
    vorher = zugang(api)
    anderes = "produkt_id" if feld != "produkt_id" else "benutzer"
    r = zugang_setzen(api, 422, **{anderes: "SYNTH-GUELTIG", feld: wert})
    assert code(r) == "validierung"
    assert ["body", feld] in orte(r), f"Ort body, {feld} erwartet: {orte(r)}"
    assert wert not in r.text, "die Meldung nennt nie den übergebenen Wert"
    assert zugang(api) == vorher, "bei einem Fehler wird nichts gespeichert"
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("koerper", [{"pin": "SYNTH-PIN-IM-ZUGANG"}, {"tan": "123456"}, {"timeout": "30"},
                                     {"benutzer": "SYNTH-OK", "pin": "SYNTH-PIN-IM-ZUGANG"}, {"blz": 12345678},
                                     {"benutzer": ["SYNTH-LISTE"]}, {"konten": []}])
def test_put_unbekannte_felder_und_typen(tmp_path, koerper, netz_gesperrt):
    api = echt_api(tmp_path, **VORBELEGUNG)
    vorher = zugang(api)
    r = api.put(ZUGANG, json=koerper, erwartet=422)
    assert code(r) == "validierung"
    assert "SYNTH-PIN-IM-ZUGANG" not in r.text
    assert zugang(api) == vorher
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("feld,wert,entfallen", [
    ("url", "https://andere.example.invalid/fints", True), ("blz", "00000001", True),
    ("benutzer", "SYNTH-ANDERER", True), ("kunden_id", "SYNTH-KUNDE-2", True),
    ("produkt_id", "SYNTH-PRODUKT-2", False), ("tan_verfahren", "913", False)])
def test_put_gespeicherte_konten_entfallen_nur_bei_anderem_zugang(tmp_path, bank, feld, wert, entfallen,
                                                                  netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        konten = konten_abrufen(api)["konten"]
        assert konten and zugang(api)["konten"] == konten
        anfragen = len(a.anfragen)
        # derselbe wirksame Wert noch einmal gespeichert: nichts ändert sich an den Konten
        z = zugang_setzen(api, benutzer=daten["benutzer"], blz=daten["blz"])
        assert z["konten"] == konten and z["gespeichert"] == ["benutzer", "blz"]
        z = zugang_setzen(api, **{feld: wert})
        assert z["konten"] == ([] if entfallen else konten), feld
        assert zugang(api)["konten"] == z["konten"]
        assert len(a.anfragen) == anfragen, "Speichern spricht die Bank nicht an"


# ------------------------------------------------------------------ Mock-Modus
def test_mock_modus_nicht_aenderbar(tmp_path, netz_gesperrt):
    api = Api(mock_config(tmp_path))
    vorher = zugang(api)
    assert code(zugang_setzen(api, 409, benutzer="SYNTH-NUTZER")) == "bankzugang_nicht_aenderbar"
    assert code(verfahren(api, 409)) == "bankzugang_nicht_aenderbar"
    assert code(konten_abrufen(api, 409)) == "bankzugang_nicht_aenderbar"
    assert code(konten_waehlen(api, [], 409)) == "bankzugang_nicht_aenderbar"
    assert code(diagnose_schalten(api, True, 409)) == "bankzugang_nicht_aenderbar"
    assert diagnose(api)["aktiv"] is False
    assert zugang(api) == vorher
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ 4.3 TAN-Verfahren
def test_tan_verfahren_abrufen_speichert_nichts(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        a.verfahren_zusatz = [ZUSATZ_VERFAHREN]
        a.erlaubte_verfahren = [daten["tan_verfahren"]["funktion"], ZUSATZ_VERFAHREN["funktion"]]
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        vorher = zugang(api)
        v = verfahren(api)
        assert sorted((x["code"], x["name"]) for x in v) == sorted([
            (daten["tan_verfahren"]["funktion"], daten["tan_verfahren"]["name"]),
            (ZUSATZ_VERFAHREN["funktion"], ZUSATZ_VERFAHREN["name"])])
        assert zugang(api) == vorher, "gespeichert wird dabei nichts"
    assert a.tans_empfangen == 0 and a.anmeldungs_tans == 0 and a.segmentarten <= LESEND and not a.interne_fehler


@pytest.mark.parametrize("abruf", [verfahren, konten_abrufen])
def test_abruf_unvollstaendig_vor_allem_anderen(tmp_path, abruf, netz_gesperrt):
    """bankzugang_unvollstaendig kommt vor jeder anderen Prüfung des Zugangs (auch ohne PIN) und ohne Verbindung."""
    api = echt_api(tmp_path, **{k: v for k, v in VORBELEGUNG.items() if k != "fints_produkt_id"})
    assert code(abruf(api, 409)) == "bankzugang_unvollstaendig"
    pin_setzen(api, "SYNTH-PIN")
    assert code(abruf(api, 409)) == "bankzugang_unvollstaendig"
    assert _pin_vorhanden(api) is True
    netz_gesperrt.pruefe()


@pytest.mark.parametrize("abruf", [verfahren, konten_abrufen])
def test_abruf_ohne_pin_ohne_verbindung(tmp_path, bank, abruf, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten) as a:
        api = _api(tmp_path, a, daten, pin=False)
        assert code(abruf(api, 409)) == "bank_pin_fehlt"
        assert a.anfragen == [], "ohne PIN wird keine Verbindung aufgebaut"


@pytest.mark.parametrize("abruf", [verfahren, konten_abrufen])
def test_abruf_falsche_pin_wird_verworfen(tmp_path, bank, abruf, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten, pin=False)
        pin_setzen(api, "SYNTH-FALSCHE-PIN-29")
        r = abruf(api, 409)
        assert code(r) == "bank_pin_falsch" and "SYNTH-FALSCHE-PIN-29" not in r.text
        assert _pin_vorhanden(api) is False, "eine abgelehnte PIN wird wie bei der Synchronisation verworfen"
        versuche = a.pins_falsch
        assert 1 <= versuche <= 2
        assert code(abruf(api, 409)) == "bank_pin_fehlt"
        assert a.pins_falsch == versuche, "kein weiterer Versuch mit der abgelehnten PIN"
        assert zugang(api)["konten"] == []


@pytest.mark.parametrize("abruf", [verfahren, konten_abrufen])
def test_abruf_fehler_des_plugins_mit_seinem_code(tmp_path, bank, abruf, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path / "a", a, daten)
        a.http_status = 503
        assert code(abruf(api, 409)) == "bank_verbindung"
        a.http_status = 200
        a.gesperrt = True
        assert code(abruf(api, 409)) == "bank_zugang_gesperrt"
        a.gesperrt = False
        langsam = _api(tmp_path / "b", a, daten, fints_timeout_sekunden=1)
        a.verzoegerung = 2.5
        assert code(abruf(langsam, 409)) == "bank_zeitueberschreitung"
        a.verzoegerung = 0


def test_konten_abrufen_entkoppelt_ist_bankfehler(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung, a.anmeldung_entkoppelt = "immer", True
        api = _api(tmp_path, a, daten)
        assert code(konten_abrufen(api, 409)) == "bank_fehler"
        assert zugang(api)["konten"] == []


# ------------------------------------------------------------------ 4.4 Konten abrufen
@pytest.mark.parametrize("koerper", [None, {}])
def test_konten_abrufen_speichert(tmp_path, bank, koerper, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        r = api.post(ZUGANG + "/konten/abrufen", erwartet=200, **({} if koerper is None else {"json": koerper}))
        soll = zugang_konten(soll_konten(daten))
        assert r.daten == {"konten": soll, "tan_erforderlich": None}
        assert soll == sorted(soll, key=lambda k: k["iban"]) and all(k["aktiv"] for k in soll)
        assert zugang(api)["konten"] == soll
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_konten_abrufen_behaelt_auswahl_und_ersetzt_die_liste(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        konten_abrufen(api)
        z = konten_waehlen(api, [giro(erw)])
        aktiv = {k["iban"]: k["aktiv"] for k in z["konten"]}
        assert aktiv == {k["iban"]: k["iban"] == giro(erw) for k in soll_konten(daten)}
        a.upd_ohne_konten = True            # die Bank liefert jetzt mehr Konten, ohne Namen und Inhaber
        neu = konten_abrufen(api)["konten"]
        soll = zugang_konten(soll_konten(daten, upd="ohne_konten"), aktiv)
        assert neu == soll, "bekannte Konten behalten ihre Auswahl, neue sind ausgewählt, die Liste wird ersetzt"
        assert len(neu) == 5 and zugang(api)["konten"] == soll
        a.upd_ohne_konten = False           # zwei Konten fallen wieder weg
        wieder = konten_abrufen(api)["konten"]
        assert wieder == zugang_konten(soll_konten(daten), aktiv)


def test_konten_abrufen_null_konten(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    leer = {**daten, "konten": []}
    with FintsAttrappe(leer, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        assert konten_abrufen(api) == {"konten": [], "tan_erforderlich": None}
        assert zugang(api)["konten"] == []
    assert not a.interne_fehler


def test_konten_abrufen_mit_tan(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        r = api.post(ZUGANG + "/konten/abrufen", erwartet=200)
        erg = r.daten
        assert erg["konten"] is None
        t = erg["tan_erforderlich"]
        assert set(t) == {"vorgang", "challenge", "bild"} and t["vorgang"]
        assert t["challenge"] == daten["challenge"]
        assert bild_bytes(t["bild"]) == ("image/png", base64.b64decode(daten["qr_png"])), "Grafik unverändert"
        assert "ANM-" not in r.text, "die Auftragsreferenz der Bank verlässt den Arbeitsspeicher nie"
        assert zugang(api)["konten"] == [], "vor der TAN ist nichts gespeichert"
        # nur eines von beiden ist ein Validierungsfehler
        assert code(konten_abrufen(api, 422, vorgang=t["vorgang"])) == "validierung"
        assert code(konten_abrufen(api, 422, tan=daten["tan"])) == "validierung"
        # falsche TAN: der Vorgang bleibt offen
        f = konten_abrufen(api, 422, vorgang=t["vorgang"], tan="000000")
        assert code(f) == "tan_ungueltig" and "000000" not in f.text
        assert code(konten_abrufen(api, 409, vorgang=t["vorgang"] + "x", tan=daten["tan"])) == "tan_nicht_offen"
        ok = konten_abrufen(api, vorgang=t["vorgang"], tan=daten["tan"])
        soll = zugang_konten(soll_konten(daten))
        assert ok == {"konten": soll, "tan_erforderlich": None} and zugang(api)["konten"] == soll
        assert code(konten_abrufen(api, 409, vorgang=t["vorgang"], tan=daten["tan"])) == "tan_nicht_offen", \
            "der Vorgang ist beendet"
        assert a.anmeldungs_tans == 1, "die TAN setzt denselben Dialog fort"
    assert a.segmentarten <= LESEND and not a.interne_fehler


def test_konten_abrufen_tan_ohne_grafik(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    ohne = {**daten, "qr_png": ""}
    with FintsAttrappe(ohne, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        a._hitan = _hitan_ohne_bild(a)
        api = _api(tmp_path, a, daten)
        t = konten_abrufen(api)["tan_erforderlich"]
        assert t["bild"] is None and t["challenge"] == daten["challenge"]
        assert konten_abrufen(api, vorgang=t["vorgang"], tan=daten["tan"])["konten"] == zugang_konten(
            soll_konten(daten))


def _hitan_ohne_bild(attrappe):
    """HITAN ohne Matrix-Code (nur Text), wie ihn eine Bank ohne Grafik liefert."""
    original = attrappe._hitan

    def hitan(referenz):
        seg = original(referenz)
        seg.challenge_hhduc = None
        return seg
    return hitan


def test_konten_abrufen_tan_abgelaufen(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        t = konten_abrufen(api)["tan_erforderlich"]
        a.lasse_tan_ablaufen()
        assert code(konten_abrufen(api, 409, vorgang=t["vorgang"], tan=daten["tan"])) == "tan_abgelaufen"
        assert code(konten_abrufen(api, 409, vorgang=t["vorgang"], tan=daten["tan"])) == "tan_nicht_offen", \
            "nach dem Ablauf ist der Vorgang beendet"
        assert zugang(api)["konten"] == []
        assert konten_mit_tan(api, daten["tan"]) == zugang_konten(soll_konten(daten))


def test_neuer_abruf_ersetzt_offenen_vorgang(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        v1 = konten_abrufen(api)["tan_erforderlich"]["vorgang"]
        v2 = konten_abrufen(api)["tan_erforderlich"]["vorgang"]
        assert v1 != v2
        assert code(konten_abrufen(api, 409, vorgang=v1, tan=daten["tan"])) == "tan_nicht_offen"
        assert konten_abrufen(api, vorgang=v2, tan=daten["tan"])["konten"] == zugang_konten(soll_konten(daten))


def test_vorgang_lebt_nur_im_arbeitsspeicher(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = _api(tmp_path, a, daten)
        v = konten_abrufen(api)["tan_erforderlich"]["vorgang"]
        for datei in api.config.aktive_datenbank.parent.iterdir():
            if datei.is_file():
                assert v.encode() not in datei.read_bytes(), f"vorgang steht in {datei.name}"
        neu = neustart(api)
        pin_setzen(neu, daten["pin"])
        assert code(konten_abrufen(neu, 409, vorgang=v, tan=daten["tan"])) == "tan_nicht_offen"


# ------------------------------------------------------------------ 4.5 Auswahl
def test_konten_auswaehlen(tmp_path, bank, netz_nur_loopback):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        alle = [k["iban"] for k in konten_abrufen(api)["konten"]]
        anfragen = len(a.anfragen)
        z = konten_waehlen(api, [alle[1]])
        assert set(z) == set(zugang(api)) and z == zugang(api)
        assert {k["iban"]: k["aktiv"] for k in z["konten"]} == {i: i == alle[1] for i in alle}
        z = konten_waehlen(api, [])
        assert not any(k["aktiv"] for k in z["konten"]) and [k["iban"] for k in z["konten"]] == alle
        z = konten_waehlen(api, list(reversed(alle)))
        assert all(k["aktiv"] for k in z["konten"]) and [k["iban"] for k in z["konten"]] == alle
        vorher = zugang(api)
        r = konten_waehlen(api, [alle[0], "DE02000000000000009999"], 422)
        assert code(r) == "validierung" and ["body", "ibans", 1] in orte(r)
        r = konten_waehlen(api, [erw["nicht_geliefert"][0]], 422)
        assert code(r) == "validierung" and ["body", "ibans", 0] in orte(r)
        assert code(api.put(ZUGANG + "/konten", json={}, erwartet=422)) == "validierung"
        assert code(api.put(ZUGANG + "/konten", json={"ibans": alle[0]}, erwartet=422)) == "validierung"
        assert code(api.put(ZUGANG + "/konten", json={"ibans": alle, "aktiv": True}, erwartet=422)) == "validierung"
        assert zugang(api) == vorher, "bei einem Fehler ändert sich nichts"
        assert len(a.anfragen) == anfragen, "die Auswahl spricht die Bank nicht an"


def test_konten_auswaehlen_ohne_gespeicherte_konten(tmp_path, netz_gesperrt):
    api = echt_api(tmp_path, **VORBELEGUNG)
    assert konten_waehlen(api, [])["konten"] == []
    r = konten_waehlen(api, ["DE95000000000000006601"], 422)
    assert code(r) == "validierung" and ["body", "ibans", 0] in orte(r)
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ 409 tan_offen
def test_aendern_waehrend_ein_lauf_auf_tan_wartet(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="einmal") as a:
        api = _api(tmp_path, a, daten)
        lauf = sync(api, **ZEITRAUM)
        assert lauf["status"] == "wartet_auf_tan"
        vorher = zugang(api)
        assert code(zugang_setzen(api, 409, produkt_id="SYNTH-P2")) == "tan_offen"
        assert code(verfahren(api, 409)) == "tan_offen"
        assert code(konten_abrufen(api, 409)) == "tan_offen"
        assert code(konten_waehlen(api, [], 409)) == "tan_offen"
        assert zugang(api) == vorher and diagnose(api)["aktiv"] is False
        api.post(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}/abbrechen", erwartet=200)
        assert zugang_setzen(api, produkt_id="SYNTH-P2")["produkt_id"] == "SYNTH-P2"


# ------------------------------------------------------------------ Betriebszustand
def test_kein_protokoll_und_nicht_in_der_sicherung(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = echt_api(tmp_path, bank_plugin="fints")
        pin_setzen(api, daten["pin"])
        a0 = letzte_aenderung_id(api)
        m0, _ = m9.oeffne(m9.sicherung(api))
        zugang_setzen(api, url=a.url, blz=daten["blz"], benutzer=daten["benutzer"], produkt_id="SYNTH-PRODUKT-SICHER",
                      kunden_id=daten["benutzer"], tan_verfahren="913")
        konten = konten_abrufen(api)["konten"]
        konten_waehlen(api, [konten[0]["iban"]])
        diagnose_schalten(api, True)
        verfahren(api)
        assert letzte_aenderung_id(api) == a0, "der Bankzugang ist Betriebszustand: kein Eintrag im Änderungsprotokoll"
        roh = m9.sicherung(api)
        m1, _ = m9.oeffne(roh)
        assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])
        for wert in (a.url, daten["benutzer"], "SYNTH-PRODUKT-SICHER", konten[0]["iban"], konten[0]["inhaber"]):
            assert not m9.enthaelt(roh, wert), f"Bankzugang in der Sicherung: {wert!r}"
        assert not m9.enthaelt(roh, daten["pin"])


def test_einspielen_laesst_den_bankzugang_stehen(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        roh = m9.sicherung(api)                      # Sicherung vor jeder Einstellung
        zugang_setzen(api, produkt_id="SYNTH-P3", tan_verfahren="913")
        konten_abrufen(api)
        vorher = zugang(api)
        api.konto("Bargeld", "girokonto")            # Unterschied zum Stand der Sicherung
        m9.einspielen(api, roh)
        assert zugang(api) == vorher, "Einspielen ändert den Bankzugang nicht"


def test_zugang_und_diagnoseschalter_ueberstehen_neustart(tmp_path, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        api = _api(tmp_path, a, daten)
        zugang_setzen(api, produkt_id="SYNTH-P4", tan_verfahren="913")
        konten = konten_abrufen(api)["konten"]
        konten_waehlen(api, [konten[-1]["iban"]])
        d = diagnose_schalten(api, True)
        assert d == {"aktiv": True, "zeilen": []}, "Einschalten leert das Protokoll"
        konten_abrufen(api)
        assert diagnose(api)["zeilen"]
        vorher = zugang(api)
        neu = neustart(api)
        assert zugang(neu) == vorher, "der Bankzugang ist dauerhaft gespeichert"
        assert diagnose(neu) == {"aktiv": True, "zeilen": []}, "die Einstellung übersteht den Neustart, die Zeilen nicht"
        assert _pin_vorhanden(neu) is False, "die PIN gehört nicht zum Bankzugang"


# ------------------------------------------------------------------ Schutz und Geheimnisse
def test_endpunkte_geschuetzt(tmp_path, netz_gesperrt):
    api = Api(m7_config(tmp_path, **VORBELEGUNG))
    for methode, pfad, koerper in (("GET", ZUGANG, None), ("PUT", ZUGANG, {"benutzer": "SYNTH-X"}),
                                   ("POST", ZUGANG + "/tan-verfahren", None),
                                   ("POST", ZUGANG + "/konten/abrufen", None),
                                   ("PUT", ZUGANG + "/konten", {"ibans": []}),
                                   ("GET", ZUGANG + "/diagnose", None),
                                   ("PUT", ZUGANG + "/diagnose", {"aktiv": True})):
        kw = {"json": koerper} if koerper is not None else {}
        assert code(api.anfrage(methode, pfad, erwartet=401, **kw)) == "nicht_angemeldet", (methode, pfad)
    anmelden(api)
    csrf, api.csrf = api.csrf, None
    assert code(api.put(ZUGANG, json={"benutzer": "SYNTH-X"}, erwartet=403)) == "csrf_ungueltig"
    api.csrf = csrf
    z = zugang(api)
    assert z["benutzer"] == "SYNTH-NUTZER" and z["gespeichert"] == []
    netz_gesperrt.pruefe()


def test_pin_und_tan_nirgends(tmp_path, bank, caplog, capfd, netz_nur_loopback):
    daten, _ = bank
    caplog.set_level(logging.DEBUG)
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        api = echt_api(tmp_path, **fints_felder(a, daten))
        texte = [api.put("/api/sync/pin", json={"pin": daten["pin"]}, erwartet=204).text]
        diagnose_schalten(api, True)
        r = api.post(ZUGANG + "/konten/abrufen", erwartet=200)
        v = r.daten["tan_erforderlich"]["vorgang"]
        texte.append(r.text)
        texte.append(konten_abrufen(api, 422, vorgang=v, tan="918273").text)
        r = api.post(ZUGANG + "/konten/abrufen", json={"vorgang": v, "tan": daten["tan"]}, erwartet=200)
        texte.append(r.text)
        texte.append(api.post(ZUGANG + "/tan-verfahren", erwartet=200).text)
        texte.append(api.get(ZUGANG, erwartet=200).text)
        texte.append(api.get(ZUGANG + "/diagnose", erwartet=200).text)
    geheimnisse_nirgends(api, [daten["pin"], daten["tan"], "918273"], texte=texte, caplog=caplog, capfd=capfd)
