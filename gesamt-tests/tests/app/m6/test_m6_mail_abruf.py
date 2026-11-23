"""M6: Mail-Abruf im Mock-Modus, Spiegel, Absenderfilter, Fehler, Planer (mail.md 6, 7)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode
from tests.hilfen.m2 import mock_config, setze_zeit
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m6 import (
    EINS, MAIL_VERGLEICH, ZWEI, abruf, benachrichtigungen, lade, nachrichten, postfach, postfach_status, zeit, zs,
)


@pytest.fixture(scope="module")
def mock_daten():
    return lade(MAIL_VERGLEICH)["mail"]["nachrichten"]


def _app(tmp_path, **felder):
    f = {"daten": MAIL_VERGLEICH, "heute": "2024-06-30", "mail_erstabruf_tage": 365, **felder}
    return Api(mock_config(tmp_path, **f))


def _soll(daten, adresse, seit=None, bis=None):
    return [n for n in daten if n["postfach"] == adresse and (seit is None or zeit(n["empfangen"]) >= seit)
            and (bis is None or zeit(n["empfangen"]).date() <= bis)]


def _spiegel(api, pid):
    return [{k: n[k] for k in ("nachricht_id", "empfangen", "absender", "betreff", "text")}
            for n in nachrichten(api, postfach_id=pid)]


def _ohne_postfach(liste):
    return [{k: v for k, v in n.items() if k != "postfach"} for n in liste]


@pytest.mark.kern
def test_erster_abruf_beide_postfaecher(tmp_path, mock_daten, netz_gesperrt):
    api = _app(tmp_path)
    p1, p2 = postfach(api, EINS), postfach(api, ZWEI)
    a0 = letzte_aenderung_id(api)
    e = abruf(api)
    jetzt = zeit(api.get("/api/mock/zeit", erwartet=200).daten["jetzt"])
    assert zeit(e["gestartet_am"]) == jetzt and [x["postfach_id"] for x in e["postfaecher"]] == [p1["id"], p2["id"]]
    for p, x in zip((p1, p2), e["postfaecher"]):
        soll = _soll(mock_daten, p["adresse"], bis=jetzt.date())
        assert x == {"postfach_id": p["id"], "adresse": p["adresse"], "status": "erfolgreich",
                     "seit": zs(jetzt - dt.timedelta(days=365)), "nachrichten_gesamt": len(soll),
                     "nachrichten_neu": len(soll), "nachrichten_vorhanden": 0, "nachrichten_gefiltert": 0,
                     "fehler": None}
        assert _spiegel(api, p["id"]) == _ohne_postfach(soll)
        s = postfach_status(api, p["id"])
        assert (s["letzter_abruf_am"], s["letzter_erfolg_am"], s["nachrichten"]) == (zs(jetzt), zs(jetzt), len(soll))
    alle = nachrichten(api)
    assert alle == sorted(alle, key=lambda n: (n["empfangen"], n["postfach_id"], n["nachricht_id"]))
    assert len({n["id"] for n in alle}) == len(alle)
    assert letzte_aenderung_id(api) == a0, "Abruf und Spiegel sind kein Buchbestand"


@pytest.mark.kern
def test_folgeabruf_mit_ueberlappung(tmp_path, mock_daten, netz_gesperrt):
    api = _app(tmp_path, heute="2024-03-31", mail_ueberlappung_stunden=48)
    p = postfach(api, EINS)
    erst = abruf(api)["postfaecher"][0]
    setze_zeit(api, "2024-06-30T08:00:00Z")
    x = abruf(api)["postfaecher"][0]
    assert zeit(erst["seit"]) == zeit("2024-03-31T12:00:00Z") - dt.timedelta(days=365)
    assert zeit(x["seit"]) == zeit("2024-03-31T12:00:00Z") - dt.timedelta(hours=48), "letzter Erfolg − Überlappung"
    neu = _soll(mock_daten, EINS, seit=zeit(x["seit"]), bis=dt.date(2024, 6, 30))
    vorhanden = [n for n in neu if zeit(n["empfangen"]).date() <= dt.date(2024, 3, 31)]
    assert (x["nachrichten_gesamt"], x["nachrichten_vorhanden"], x["nachrichten_neu"]) == (
        len(neu), len(vorhanden), len(neu) - len(vorhanden))
    assert _spiegel(api, p["id"]) == _ohne_postfach(_soll(mock_daten, EINS, bis=dt.date(2024, 6, 30)))
    assert abruf(api)["postfaecher"][0]["nachrichten_neu"] == 0


@pytest.mark.kern
def test_absenderfilter(tmp_path, mock_daten, netz_gesperrt):
    api = _app(tmp_path)
    p = postfach(api, EINS, absender_filter=["BUECHERSTUBE", "bezahldienst.example"])
    x = abruf(api)["postfaecher"][0]
    soll = _soll(mock_daten, EINS)
    behalten = [n for n in soll if "buecherstube" in n["absender"] or "bezahldienst.example" in n["absender"]]
    assert 0 < len(behalten) < len(soll)
    assert (x["nachrichten_neu"], x["nachrichten_gefiltert"]) == (len(behalten), len(soll) - len(behalten))
    assert _spiegel(api, p["id"]) == _ohne_postfach(behalten)


@pytest.mark.kern
def test_inaktive_und_loeschen(tmp_path, netz_gesperrt):
    api = _app(tmp_path)
    p1, p2 = postfach(api, EINS), postfach(api, ZWEI, aktiv=False)
    assert [x["postfach_id"] for x in abruf(api)["postfaecher"]] == [p1["id"]]
    assert nachrichten(api, postfach_id=p2["id"]) == [] and nachrichten(api)
    api.delete(f"/api/mail/postfaecher/{p1['id']}", erwartet=204)
    assert nachrichten(api) == []
    seite = api.get("/api/mail/nachrichten", params={"pro_seite": 501}, erwartet=422)
    assert fehlercode(seite) == "validierung"


@pytest.mark.kern
def test_token_ablauf_im_mock_einmal(tmp_path, netz_gesperrt):
    api = _app(tmp_path, szenario="token_ablauf")
    p = postfach(api, EINS)
    for _ in range(3):
        x = abruf(api)["postfaecher"][0]
        assert (x["status"], x["fehler"]["code"], x["nachrichten_gesamt"]) == ("fehlgeschlagen",
                                                                              "mail_token_abgelaufen", 0)
    b = [y for y in benachrichtigungen(api) if y["art"] == "mail_token_abgelaufen"]
    assert [y["schluessel"] for y in b] == [f"mail_token_abgelaufen:{p['id']}:0"]
    assert b[0]["link"] == f"/mail/postfaecher/{p['id']}"
    s = postfach_status(api, p["id"])
    assert s["letzter_fehler"]["code"] == "mail_token_abgelaufen" and s["letzter_erfolg_am"] is None


@pytest.mark.kern
def test_unbekanntes_postfach_entprellt(tmp_path, netz_gesperrt):
    api = _app(tmp_path)
    p = postfach(api, "drei@example.invalid")
    ok = postfach(api, EINS)
    for _ in range(2):
        e = abruf(api)["postfaecher"]
        assert e[0]["status"] == "fehlgeschlagen" and e[0]["fehler"]["code"] == "mail_postfach_unbekannt"
        assert e[1]["status"] == "erfolgreich", "das andere Postfach ist unberührt"
    schl = f"mail_fehler:{p['id']}:mail_postfach_unbekannt"
    b = [y for y in benachrichtigungen(api) if y["art"] == "mail_fehler"]
    assert [y["schluessel"] for y in b] == [schl]
    api.post(f"/api/benachrichtigungen/{b[0]['id']}/gelesen", erwartet=200)
    abruf(api)
    assert [y["schluessel"] for y in benachrichtigungen(api) if y["art"] == "mail_fehler"] == [schl, schl]
    assert ok


@pytest.mark.kern
def test_planer_ruft_ab(tmp_path, netz_gesperrt):
    planer = kontor.modul("kontor.sync")
    api = _app(tmp_path, mail_intervall_minuten=60)
    p = postfach(api, EINS)
    setze_zeit(api, "2024-06-30T12:00:00Z")
    assert planer.planer_takt(api.app) is None
    assert postfach_status(api, p["id"])["letzter_abruf_am"] == "2024-06-30T12:00:00Z"
    setze_zeit(api, "2024-06-30T12:59:00Z")
    planer.planer_takt(api.app)
    assert postfach_status(api, p["id"])["letzter_abruf_am"] == "2024-06-30T12:00:00Z"
    setze_zeit(api, "2024-06-30T13:00:00Z")
    planer.planer_takt(api.app)
    assert postfach_status(api, p["id"])["letzter_abruf_am"] == "2024-06-30T13:00:00Z"


def test_ohne_intervall_kein_automatischer_abruf(tmp_path, netz_gesperrt):
    api = _app(tmp_path)
    p = postfach(api, EINS)
    kontor.modul("kontor.sync").planer_takt(api.app)
    assert postfach_status(api, p["id"])["letzter_abruf_am"] is None
