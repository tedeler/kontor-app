"""M6: TAN-Push und Erinnerungen in Abständen (benachrichtigungen.md 5, K 6 Schritte 2 und 4, E-121)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen import m6_orakel as orakel
from tests.hilfen.api import Api
from tests.hilfen.m2 import SYNC_DATEN_PIN, lade_sync, mock_config, setze_zeit
from tests.hilfen.m6 import benachrichtigungen, lade, ntfy_felder, zeit, zs
from tests.hilfen.ntfy_attrappe import NtfyAttrappe
from tests.hilfen.pfade import FIXTURES

START = dt.datetime(2024, 6, 30, 9, 0, 0, tzinfo=dt.timezone.utc)


def _takt(api):
    return kontor.modul("kontor.sync").planer_takt(api.app)


def _tan_app(tmp_path, n=None, **felder):
    f = dict(felder)
    if n is not None:
        f.update(ntfy_felder(n))
    api = Api(mock_config(tmp_path, daten=SYNC_DATEN_PIN, szenario="tan_erforderlich", **f))
    _, erw = lade_sync()
    api.put("/api/sync/pin", json={"pin": erw["pin"]}, erwartet=204)
    setze_zeit(api, zs(START))
    lauf = api.post("/api/sync", json={"von": "2024-01-01"}, erwartet=200).daten
    t = api.get(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}", erwartet=200).daten
    return api, t, erw


def _erinnerungen(api, tid):
    return [b for b in benachrichtigungen(api) if b["art"] == "tan_erinnerung" and
            b["schluessel"].startswith(f"tan_erinnerung:{tid}:")]


@pytest.mark.kern
def test_fester_fall_mit_ntfy(tmp_path, netz_nur_loopback):
    with NtfyAttrappe() as n:
        api, t, _ = _tan_app(tmp_path, n, tan_erinnerung_minuten=5, tan_erinnerung_anzahl=3,
                             oeffentliche_url="http://kontor.lan.example.invalid")
        assert zeit(t["erstellt_am"]) == START
        for minuten, soll in ((4, []), (5, [1]), (6, []), (16, [3]), (21, []), (40, [])):
            vorher = len(_erinnerungen(api, t["id"]))
            setze_zeit(api, zs(START + dt.timedelta(minutes=minuten)))
            assert _takt(api) is None
            neu = _erinnerungen(api, t["id"])[vorher:]
            assert [int(b["schluessel"].rsplit(":", 1)[1]) for b in neu] == soll, minuten
            for b in neu:
                assert b["link"] == f"/tan/{t['id']}" and b["zustellung"] == "zugestellt"
    erinnert = [k for k in n.angenommen if k["tags"] == ["tan_erinnerung"]]
    assert len(erinnert) == 2 and all(k["priority"] == 4 for k in erinnert)
    assert all(k["click"] == f"http://kontor.lan.example.invalid/tan/{t['id']}" for k in erinnert)
    assert [k["tags"] for k in n.angenommen][0] == ["tan_erforderlich"]


@pytest.mark.kern
@pytest.mark.parametrize("nr", range(8))
def test_faelle_des_generators(tmp_path, nr, netz_gesperrt):
    f = lade(FIXTURES / "m6" / "benachrichtigungen.erwartung.json")["erinnerungen"][nr]
    api, t, _ = _tan_app(tmp_path, tan_erinnerung_minuten=f["intervall"], tan_erinnerung_anzahl=f["anzahl"])
    erstellt = zeit(f["erstellt"])
    takte = [START + (zeit(x) - erstellt) for x in f["takte"]]
    soll = orakel.erinnerungen(START, zeit(t["gueltig_bis"]), f["intervall"], f["anzahl"], takte)
    ist = []
    for x in takte:
        vorher = len(_erinnerungen(api, t["id"]))
        setze_zeit(api, zs(x))
        _takt(api)
        ist.append([int(b["schluessel"].rsplit(":", 1)[1]) for b in _erinnerungen(api, t["id"])[vorher:]])
    assert ist == soll


@pytest.mark.kern
@pytest.mark.parametrize("ende", ["antwort", "abbruch", "ablauf"])
def test_keine_erinnerung_nach_ende(tmp_path, ende, netz_gesperrt):
    api, t, erw = _tan_app(tmp_path, tan_erinnerung_minuten=1, tan_erinnerung_anzahl=10)
    setze_zeit(api, zs(START + dt.timedelta(minutes=1)))
    _takt(api)
    assert len(_erinnerungen(api, t["id"])) == 1
    if ende == "antwort":
        api.post(f"/api/tan-anforderungen/{t['id']}/antwort", json={"tan": erw["tan"]}, erwartet=200)
    elif ende == "abbruch":
        api.post(f"/api/tan-anforderungen/{t['id']}/abbrechen", erwartet=200)
    else:
        setze_zeit(api, zs(zeit(t["gueltig_bis"]) + dt.timedelta(seconds=1)))
        _takt(api)
        assert [b["art"] for b in benachrichtigungen(api)].count("tan_abgelaufen") == 1
    for minuten in (3, 9, 30):
        setze_zeit(api, zs(max(START + dt.timedelta(minutes=minuten),
                               zeit(t["gueltig_bis"]) + dt.timedelta(minutes=minuten) if ende == "ablauf" else START)))
        _takt(api)
    assert len(_erinnerungen(api, t["id"])) == 1


@pytest.mark.kern
def test_abgeschaltet(tmp_path, netz_gesperrt):
    api, t, _ = _tan_app(tmp_path, tan_erinnerung_minuten=0)
    for minuten in (5, 10, 60):
        setze_zeit(api, zs(START + dt.timedelta(minutes=minuten)))
        _takt(api)
    assert _erinnerungen(api, t["id"]) == []
    mock = api.get("/api/mock/zustellungen", erwartet=200).daten
    assert [p["tags"] for p in mock] == [["tan_erforderlich"]] and mock[0]["link"] is None


@pytest.mark.kern
def test_vorgaben_fuenf_minuten_drei_mal(tmp_path, netz_gesperrt):
    api, t, _ = _tan_app(tmp_path)
    for minuten in range(1, 40):
        setze_zeit(api, zs(START + dt.timedelta(minutes=minuten)))
        _takt(api)
    assert [b["schluessel"] for b in _erinnerungen(api, t["id"])] == [
        f"tan_erinnerung:{t['id']}:{i}" for i in (1, 2, 3)]
