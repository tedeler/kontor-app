"""M2: TAN-Ablauf – speichern, anzeigen, beantworten, abbrechen, Ablauf, Neustart (synchronisation.md 7, 10; K 6)."""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import Api, fehlercode
from tests.hilfen.m2 import (
    alle_antworten, benachrichtigungen, db_dateien, laeufe, lade_sync, mock_bank, mock_config, nach_kennung,
    setze_zeit, status, sync, tans, zeit,
)

VON = "2024-01-01"


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def tapi(tmp_path):
    return Api(mock_config(tmp_path, szenario="tan_erforderlich"))


def _starte(api) -> tuple[dict, dict]:
    lauf = sync(api, von=VON)
    assert lauf["status"] == "wartet_auf_tan", lauf
    t = api.get(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}", erwartet=200).daten
    return lauf, t


def _antwort(api, tid, tan, erwartet=200):
    return api.post(f"/api/tan-anforderungen/{tid}/antwort", json={"tan": tan}, erwartet=erwartet)


@pytest.mark.kern
def test_tan_anforderung_entsteht(tapi, sd, netz_gesperrt):
    daten, erw = sd
    lauf, t = _starte(tapi)
    ibans = sorted(k["iban"] for k in daten["bank"]["konten"])
    assert lauf["beendet_am"] is None and lauf["fehler"] is None
    assert [k["iban"] for k in lauf["konten"]] == ibans
    erstes, *rest = lauf["konten"]
    assert erstes["status"] == "wartet_auf_tan" and (erstes["von"], erstes["bis"]) == (VON, "2024-06-30")
    assert all(k["status"] == "ausstehend" and k["von"] is None and k["bis"] is None for k in rest)
    assert all(k["konto_neu"] for k in lauf["konten"]), "Zuordnung geschieht vor dem ersten Abruf"
    assert all(k["buchungen_neu"] == k["umsaetze_gesamt"] == 0 for k in lauf["konten"])
    assert (t["status"], t["lauf_id"], t["iban"], t["konto_id"], t["hat_bild"], t["beendet_am"]) == (
        "offen", lauf["id"], ibans[0], erstes["konto_id"], True, None)
    assert zeit(t["gueltig_bis"]) == zeit("2024-06-30T23:59:59Z")
    assert zeit(t["erstellt_am"]) == zeit("2024-06-30T12:00:00Z")
    assert t["challenge"].strip()
    assert tans(tapi) == [t]
    assert tapi.alle_buchungen() == []
    st = status(tapi)
    assert st["offene_tan_anforderung"] == t and st["letzter_lauf"]["id"] == lauf["id"]
    b = benachrichtigungen(tapi)
    assert [(x["art"], x["schluessel"], x["link"]) for x in b] == [
        ("tan_erforderlich", f"tan:{t['id']}", f"/tan/{t['id']}")]


def test_tan_bild(tapi, sd, netz_gesperrt):
    daten, _ = sd
    _, t = _starte(tapi)
    r = tapi.get(f"/api/tan-anforderungen/{t['id']}/bild", erwartet=200)
    assert r.headers["content-type"].split(";")[0].strip() == "image/png"
    with pytest.raises(kontor.fehler().TanErforderlich) as info:
        mock_bank(szenario="tan_erforderlich").umsaetze(t["iban"], dt.date(2024, 1, 1), dt.date(2024, 6, 30))
    assert r.content == info.value.bild, "Bild muss genau die Bytes des Plugins enthalten"


def test_interne_kennung_nie_sichtbar(tapi, netz_gesperrt):
    _starte(tapi)
    assert "MOCK-TAN-2024-06-30" not in alle_antworten(tapi)


@pytest.mark.kern
def test_waehrend_offener_tan_kein_neuer_lauf(tapi, netz_gesperrt):
    _starte(tapi)
    r = tapi.post("/api/sync", json={}, erwartet=409)
    assert fehlercode(r) == "tan_ausstehend"
    assert len(laeufe(tapi)) == 1 and status(tapi)["naechster_lauf"] is None


@pytest.mark.kern
def test_falsche_tan_dann_richtige(tapi, sd, netz_gesperrt):
    daten, erw = sd
    lauf, t = _starte(tapi)
    r = _antwort(tapi, t["id"], "FALSCHE-TAN-4711", erwartet=422)
    assert fehlercode(r) == "tan_ungueltig"
    assert tapi.get(f"/api/tan-anforderungen/{t['id']}", erwartet=200).daten["status"] == "offen"
    assert tapi.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten == lauf
    assert tapi.alle_buchungen() == []
    fertig = _antwort(tapi, t["id"], erw["tan"]).daten
    assert fertig["id"] == lauf["id"] and fertig["status"] == "erfolgreich" and fertig["beendet_am"]
    assert all(k["status"] == "erfolgreich" and (k["von"], k["bis"]) == (VON, "2024-06-30") for k in fertig["konten"])
    t2 = tapi.get(f"/api/tan-anforderungen/{t['id']}", erwartet=200).daten
    assert t2["status"] == "beantwortet" and zeit(t2["beendet_am"]) == zeit("2024-06-30T12:00:00Z")
    soll = {orakel.kennung(u) for u in daten["bank"]["umsaetze"] if not u["vormerkung"]}
    assert set(nach_kennung(tapi.alle_buchungen())) == soll
    assert fehlercode(tapi.get(f"/api/tan-anforderungen/{t['id']}/bild", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(_antwort(tapi, t["id"], erw["tan"], erwartet=409)) == "tan_nicht_offen"
    assert fehlercode(tapi.post(f"/api/tan-anforderungen/{t['id']}/abbrechen", erwartet=409)) == "tan_nicht_offen"
    assert status(tapi)["offene_tan_anforderung"] is None


def test_freigabe_gilt_fuer_weitere_laeufe_am_selben_tag(tapi, sd, netz_gesperrt):
    _, erw = sd
    _, t = _starte(tapi)
    _antwort(tapi, t["id"], erw["tan"])
    lauf = sync(tapi, von=VON)
    assert lauf["status"] == "erfolgreich" and len(tans(tapi)) == 1
    setze_zeit(tapi, "2024-07-01T08:00:00Z")
    lauf = sync(tapi)
    assert lauf["status"] == "wartet_auf_tan" and len(tans(tapi)) == 2


@pytest.mark.parametrize("koerper", [{}, {"tan": ""}, {"tan": 123456}, {"tan": "1" * 65}, {"tan": "1", "x": 1}],
                         ids=["leer", "leere_tan", "zahl", "zu_lang", "feld_unbekannt"])
def test_antwort_validierung(tapi, koerper, netz_gesperrt):
    _, t = _starte(tapi)
    r = tapi.post(f"/api/tan-anforderungen/{t['id']}/antwort", json=koerper, erwartet=422)
    assert fehlercode(r) == "validierung"
    assert tapi.get(f"/api/tan-anforderungen/{t['id']}", erwartet=200).daten["status"] == "offen"


def test_unbekannte_anforderung_404(tapi, netz_gesperrt):
    for r in (tapi.get("/api/tan-anforderungen/4711", erwartet=404),
              tapi.get("/api/tan-anforderungen/4711/bild", erwartet=404),
              tapi.post("/api/tan-anforderungen/4711/antwort", json={"tan": "1"}, erwartet=404),
              tapi.post("/api/tan-anforderungen/4711/abbrechen", erwartet=404)):
        assert fehlercode(r) == "nicht_gefunden"


@pytest.mark.kern
def test_ablauf(tapi, sd, netz_gesperrt):
    _, erw = sd
    lauf, t = _starte(tapi)
    setze_zeit(tapi, "2024-06-30T23:59:59Z")  # noch gültig (jetzt > gueltig_bis erst danach)
    assert tapi.get(f"/api/tan-anforderungen/{t['id']}", erwartet=200).daten["status"] == "offen"
    setze_zeit(tapi, "2024-07-01T00:00:00Z")
    t2 = tapi.get(f"/api/tan-anforderungen/{t['id']}", erwartet=200).daten
    assert t2["status"] == "abgelaufen" and zeit(t2["beendet_am"]) == zeit("2024-07-01T00:00:00Z")
    l2 = tapi.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten
    assert l2["status"] == "abgebrochen" and zeit(l2["beendet_am"]) == zeit("2024-07-01T00:00:00Z")
    assert {k["status"] for k in l2["konten"]} == {"abgebrochen"}
    assert fehlercode(_antwort(tapi, t["id"], erw["tan"], erwartet=409)) == "tan_abgelaufen"
    assert fehlercode(tapi.post(f"/api/tan-anforderungen/{t['id']}/abbrechen", erwartet=409)) == "tan_abgelaufen"
    assert fehlercode(tapi.get(f"/api/tan-anforderungen/{t['id']}/bild", erwartet=404)) == "nicht_gefunden"
    arten = [(b["art"], b["schluessel"]) for b in benachrichtigungen(tapi)]
    assert arten == [("tan_erforderlich", f"tan:{t['id']}"), ("tan_abgelaufen", f"tan_abgelaufen:{t['id']}")]
    assert tapi.alle_buchungen() == []
    # danach ist ein neuer Lauf möglich und verlangt eine neue TAN
    neu = sync(tapi)
    assert neu["status"] == "wartet_auf_tan" and neu["tan_anforderung_id"] != t["id"]


def test_ablauf_beim_antworten_erkannt(tapi, sd, netz_gesperrt):
    _, erw = sd
    _, t = _starte(tapi)
    setze_zeit(tapi, "2024-07-02T09:00:00Z")
    assert fehlercode(_antwort(tapi, t["id"], erw["tan"], erwartet=409)) == "tan_abgelaufen"
    assert tans(tapi)[0]["status"] == "abgelaufen"


def test_abbrechen(tapi, netz_gesperrt):
    lauf, t = _starte(tapi)
    a = tapi.post(f"/api/tan-anforderungen/{t['id']}/abbrechen", erwartet=200).daten
    assert a["status"] == "abgebrochen" and a["beendet_am"] is not None
    l2 = tapi.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten
    assert l2["status"] == "abgebrochen" and {k["status"] for k in l2["konten"]} == {"abgebrochen"}
    assert status(tapi)["offene_tan_anforderung"] is None
    assert sync(tapi)["status"] == "wartet_auf_tan"


@pytest.mark.kern
def test_neustart_bricht_sauber_ab(tmp_path, sd, netz_gesperrt):
    """T 20: Neustart während einer wartenden Synchronisation führt zu keinem inkonsistenten Zustand."""
    _, erw = sd
    config = mock_config(tmp_path, szenario="tan_erforderlich")
    a = Api(config)
    lauf, t = _starte(a)
    konten_vorher = a.konten()
    b = Api(config)  # Neustart: neue App auf derselben Datenbank
    assert b.get(f"/api/tan-anforderungen/{t['id']}", erwartet=200).daten["status"] == "abgebrochen"
    l2 = b.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten
    assert l2["status"] == "abgebrochen" and l2["beendet_am"] is not None
    assert {k["status"] for k in l2["konten"]} == {"abgebrochen"}
    assert b.konten() == konten_vorher, "Kontozuordnung bleibt erhalten"
    neu = sync(b, von=VON)
    assert neu["status"] == "wartet_auf_tan"
    fertig = _antwort(b, neu["tan_anforderung_id"], erw["tan"]).daten
    assert fertig["status"] == "erfolgreich"


@pytest.mark.kern
def test_tan_nie_gespeichert_oder_ausgegeben(tapi, sd, caplog, capfd, netz_gesperrt):
    import logging
    caplog.set_level(logging.DEBUG)
    _, erw = sd
    _, t = _starte(tapi)
    _antwort(tapi, t["id"], "FALSCHE-TAN-4711", erwartet=422)
    _antwort(tapi, t["id"], erw["tan"])
    texte = [alle_antworten(tapi), caplog.text, *capfd.readouterr()]
    for geheim in (erw["tan"], "FALSCHE-TAN-4711"):
        for text in texte:
            assert geheim not in text
        for datei in db_dateien(tapi):
            assert geheim.encode() not in datei.read_bytes(), f"TAN in {datei.name}"
