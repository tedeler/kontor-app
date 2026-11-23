"""M2: Fehlerbehandlung, Wiederholung ohne Datenverlust, Benachrichtigungen mit Entprellung (synchronisation.md 5, 6, 11).

T 7: Fehler führen zu Benachrichtigung und Wiederholung, ohne Datenverlust.
T 17: gleiche Ereignisse lösen keine Nachrichtenflut aus.
"""

from __future__ import annotations

import pytest

from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import Api, fehlercode
from tests.hilfen.m2 import benachrichtigungen, laeufe, lade_sync, mock_api, mock_config, nach_kennung, sync

FEHLER = [("bankfehler", "bank_verbindung"), ("zeitueberschreitung", "bank_zeitueberschreitung")]


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.mark.kern
@pytest.mark.parametrize("szenario,code", FEHLER)
def test_fehlgeschlagener_lauf_aendert_nichts(tmp_path, szenario, code, netz_gesperrt):
    api = mock_api(tmp_path, szenario=szenario)
    g = api.konto("Vorhanden")
    a = api.konto("Lebensmittel", "aufwand")
    api.buchung("2024-01-01", [(g["id"], -100), (a["id"], 100)])
    vorher = api.zustand()
    lauf = sync(api, von="2024-01-01")
    assert lauf["status"] == "fehlgeschlagen" and lauf["konten"] == []
    assert lauf["fehler"]["code"] == code and lauf["fehler"]["meldung"].strip()
    assert lauf["beendet_am"] is not None
    assert api.zustand() == vorher
    assert api.get("/api/sync/konten", erwartet=200).daten == []


@pytest.mark.kern
@pytest.mark.parametrize("szenario,code", FEHLER)
def test_benachrichtigung_entprellt(tmp_path, szenario, code, netz_gesperrt):
    api = mock_api(tmp_path, szenario=szenario)
    assert benachrichtigungen(api) == []
    for _ in range(3):
        sync(api)
    bs = benachrichtigungen(api)
    assert len(bs) == 1, "gleiche Fehler dürfen keine Nachrichtenflut auslösen"
    b = bs[0]
    assert (b["art"], b["schluessel"], b["gelesen"], b["link"]) == ("sync_fehler", f"sync_fehler:{code}", False, None)
    assert b["titel"].strip() and b["text"].strip()
    gelesen = api.post(f"/api/benachrichtigungen/{b['id']}/gelesen", erwartet=200).daten
    assert gelesen == {**b, "gelesen": True}
    assert api.post(f"/api/benachrichtigungen/{b['id']}/gelesen", erwartet=200).daten == gelesen
    sync(api)
    bs = benachrichtigungen(api)
    assert len(bs) == 2 and bs[0]["gelesen"] is True and bs[1]["gelesen"] is False
    assert bs[1]["schluessel"] == f"sync_fehler:{code}" and bs[1]["id"] > bs[0]["id"]
    assert benachrichtigungen(api, gelesen=False) == [bs[1]]
    assert benachrichtigungen(api, gelesen=True) == [bs[0]]
    assert len(laeufe(api)) == 4


def test_benachrichtigung_404(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path)
    assert fehlercode(api.post("/api/benachrichtigungen/4711/gelesen", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.get("/api/benachrichtigungen", params={"gelesen": "vielleicht"},
                              erwartet=422)) == "validierung"


def test_erfolgreicher_lauf_ohne_benachrichtigung(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path)
    sync(api, von="2024-01-01")
    assert benachrichtigungen(api) == []


@pytest.mark.kern
def test_wiederholung_ohne_datenverlust(tmp_path, sd, netz_gesperrt):
    """Bank zeitweise nicht erreichbar: vorhandene Daten bleiben, der nächste Lauf holt alles nach."""
    daten, erw = sd
    s1, s2, s3 = erw["stufen"]
    a = Api(mock_config(tmp_path, heute=s1))
    sync(a, von="2024-01-01")
    vorher = a.zustand()
    b = Api(mock_config(tmp_path, heute=s2, szenario="zeitueberschreitung"))  # gleiche Datenbank
    assert sync(b)["status"] == "fehlgeschlagen"
    assert b.zustand() == vorher
    assert {z["letzter_abruf_bis"] for z in b.get("/api/sync/konten", erwartet=200).daten} == {s1}
    c = Api(mock_config(tmp_path, heute=s3))
    lauf = sync(c)
    assert lauf["status"] == "erfolgreich"
    soll = {orakel.kennung(u) for u in daten["bank"]["umsaetze"] if not u["vormerkung"] and u["buchungstag"] <= s3}
    assert set(nach_kennung(c.alle_buchungen())) == soll
    assert [x["status"] for x in laeufe(c)] == ["erfolgreich", "fehlgeschlagen", "erfolgreich"]


def test_fehler_beim_erzeugen_des_plugins(tmp_path, netz_gesperrt):
    """Unlesbare Mock-Datendatei: fehlgeschlagener Lauf mit konfiguration_ungueltig, nie 5xx (synchronisation.md 6)."""
    kaputt = tmp_path / "kaputt.json"
    kaputt.write_text("{ kein json", encoding="utf-8")
    api = mock_api(tmp_path / "db", daten=kaputt)
    lauf = sync(api)
    assert (lauf["status"], lauf["konten"], lauf["fehler"]["code"]) == ("fehlgeschlagen", [], "konfiguration_ungueltig")
    assert benachrichtigungen(api)[0]["schluessel"] == "sync_fehler:konfiguration_ungueltig"
