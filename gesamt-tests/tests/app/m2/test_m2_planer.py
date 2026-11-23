"""M2: Planer – abschaltbar, deterministischer Takt, Intervall, Wiederholung, TAN-Ablauf (synchronisation.md 9)."""

from __future__ import annotations

import time

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api
from tests.hilfen.m2 import laeufe, mock_config, setze_zeit, status, sync, tans, zeit


def takt(api):
    return kontor.modul("kontor.sync").planer_takt(api.app)


def _api(tmp_path, **kw):
    kw.setdefault("planer_starten", False)
    return Api(mock_config(tmp_path, **kw))


@pytest.mark.kern
def test_ohne_intervall_kein_automatischer_abruf(tmp_path, netz_gesperrt):
    api = _api(tmp_path, planer_starten=True)
    assert takt(api) is None and takt(api) is None
    st = status(api)
    assert (st["automatisch"], st["intervall_minuten"], st["naechster_lauf"]) == (False, 0, None)
    assert laeufe(api) == []


@pytest.mark.kern
def test_intervall(tmp_path, netz_gesperrt):
    api = _api(tmp_path, sync_intervall_minuten=60)
    st = status(api)
    assert st["automatisch"] is True and st["intervall_minuten"] == 60
    assert zeit(st["naechster_lauf"]) == zeit("2024-06-30T12:00:00Z"), "ohne vorherigen Lauf sofort fällig"
    lauf = takt(api)
    assert isinstance(lauf, dict) and lauf["ausloeser"] == "planer" and lauf["status"] == "erfolgreich"
    assert (lauf["von"], lauf["bis"]) == (None, None)
    assert laeufe(api) == [lauf] and api.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten == lauf
    assert takt(api) is None
    assert zeit(status(api)["naechster_lauf"]) == zeit("2024-06-30T13:00:00Z")
    setze_zeit(api, "2024-06-30T12:59:59Z")
    assert takt(api) is None
    setze_zeit(api, "2024-06-30T13:00:00Z")
    zweiter = takt(api)
    assert zweiter["ausloeser"] == "planer" and len(laeufe(api)) == 2
    assert all(k["buchungen_neu"] == 0 for k in zweiter["konten"])
    assert {k["von"] for k in zweiter["konten"]} == {"2024-06-16"}  # 30.06. − 14 Tage Überlappung


def test_manueller_lauf_zaehlt(tmp_path, netz_gesperrt):
    api = _api(tmp_path, sync_intervall_minuten=30)
    sync(api)
    assert zeit(status(api)["naechster_lauf"]) == zeit("2024-06-30T12:30:00Z")
    assert takt(api) is None


@pytest.mark.kern
def test_wiederholung_nach_fehler(tmp_path, netz_gesperrt):
    api = _api(tmp_path, szenario="bankfehler", sync_intervall_minuten=360, sync_wiederholung_minuten=15)
    assert takt(api)["status"] == "fehlgeschlagen"
    assert zeit(status(api)["naechster_lauf"]) == zeit("2024-06-30T12:15:00Z")
    setze_zeit(api, "2024-06-30T12:14:00Z")
    assert takt(api) is None
    setze_zeit(api, "2024-06-30T12:15:00Z")
    assert takt(api)["status"] == "fehlgeschlagen"
    assert len(laeufe(api)) == 2


@pytest.mark.kern
def test_planer_und_tan(tmp_path, netz_gesperrt):
    api = _api(tmp_path, szenario="tan_erforderlich", sync_intervall_minuten=60)
    lauf = takt(api)
    assert lauf["status"] == "wartet_auf_tan"
    assert status(api)["naechster_lauf"] is None
    setze_zeit(api, "2024-06-30T18:00:00Z")
    assert takt(api) is None, "während einer offenen TAN-Anforderung startet der Planer nichts"
    setze_zeit(api, "2024-07-01T00:00:00Z")
    assert takt(api) is None  # Takt erkennt den Ablauf; nächster Lauf erst eine Stunde nach dem Abbruch
    assert tans(api)[0]["status"] == "abgelaufen"
    assert api.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten["status"] == "abgebrochen"
    assert zeit(status(api)["naechster_lauf"]) == zeit("2024-07-01T01:00:00Z")
    setze_zeit(api, "2024-07-01T01:00:00Z")
    neu = takt(api)
    assert neu["status"] == "wartet_auf_tan" and len(tans(api)) == 2


def test_kein_planer_ohne_lifespan(tmp_path, netz_gesperrt):
    api = Api(mock_config(tmp_path, sync_intervall_minuten=1, planer_starten=True))
    time.sleep(1.5)
    assert laeufe(api) == [], "create_app darf keinen Planer starten"


def test_planer_starten_falsch(tmp_path, netz_gesperrt):
    from fastapi.testclient import TestClient

    app = kontor.create_app(mock_config(tmp_path, sync_intervall_minuten=1, planer_starten=False))
    with TestClient(app) as c:
        time.sleep(2)
        assert c.get("/api/sync/laeufe").json() == []


def test_hintergrund_thread(tmp_path, netz_gesperrt):
    """Mit Lifespan, Intervall und planer_starten führt der Thread den ersten Takt binnen 5 s aus."""
    from fastapi.testclient import TestClient

    app = kontor.create_app(mock_config(tmp_path, sync_intervall_minuten=1, planer_starten=True))
    with TestClient(app) as c:
        frist = time.monotonic() + 15
        ls = []
        while time.monotonic() < frist:
            ls = c.get("/api/sync/laeufe").json()
            if ls:
                break
            time.sleep(0.25)
        assert ls and ls[0]["ausloeser"] == "planer"
