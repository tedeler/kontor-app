"""M23: gemerkte Bank-PIN unter dem Schutz der Geheimnisse (geheimnisschutz.md 4, 5; E-229)."""

from __future__ import annotations

import logging

import pytest

from tests.hilfen.m2 import db_dateien
from tests.hilfen.m9 import enthaelt, sicherung
from tests.hilfen.m23 import (
    FALSCHE_PIN, PASSWORT, PIN, ausschalten, code, einschalten, eintraege, entsperren, lauf, m23_mock_api, merken,
    neustart, pin_vorhanden, schutz, sperren,
)

pytestmark = pytest.mark.kern


def _ein(tmp_path, **kw):
    api = m23_mock_api(tmp_path, **kw)
    einschalten(api)
    return api


def _pin(api, pin=PIN):
    api.put("/api/sync/pin", json={"pin": pin}, erwartet=204)


def test_merken_pruefreihenfolge(tmp_path, netz_gesperrt):
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "kontor-bank-pin").write_text(PIN, encoding="utf-8")
    sd = m23_mock_api(tmp_path / "s", bank_pin_quelle="systemd-creds", credentials_verzeichnis=creds)
    einschalten(sd)
    for koerper in ({"pin": PIN}, {}, {"pin": ""}):
        r = sd.put("/api/sync/pin/gemerkt", json=koerper, erwartet=409)
        assert code(r) == "pin_quelle_systemd", "systemd-creds vor der Körperprüfung"
    api = m23_mock_api(tmp_path / "e")
    for koerper, geheim in (({}, None), ({"pin": ""}, None), ({"pin": "GEHEIM-" + "7" * 130}, "7" * 130),
                            ({"pin": 98765432323}, "98765432323"), ({"pin": "GEHEIM-PIN-FELD", "x": 1}, "GEHEIM-PIN-FELD"),
                            ({"pin": ["GEHEIM-PIN-LISTE"]}, "GEHEIM-PIN-LISTE")):
        r = api.put("/api/sync/pin/gemerkt", json=koerper, erwartet=422)
        assert code(r) == "validierung", "Körper vor „Schutz nicht aktiv“"
        if geheim:
            assert geheim not in r.text
    assert code(merken(api, erwartet=409)) == "schutz_nicht_aktiv"
    einschalten(api)
    sperren(api)
    assert code(api.put("/api/sync/pin/gemerkt", json={}, erwartet=422)) == "validierung"
    r = merken(api, erwartet=409)
    assert code(r) == "geheimnisse_gesperrt" and PIN not in r.text
    assert schutz(api)["pin_gemerkt"] is False and "bank_pin" not in eintraege(api)
    assert pin_vorhanden(api) is False


def test_gemerkte_pin_ueber_neustart(tmp_path, netz_gesperrt):
    a = _ein(tmp_path)
    merken(a)
    assert schutz(a) == {"aktiv": True, "entsperrt": True, "gesperrt": False, "geschuetzt": 1, "pin_gemerkt": True}
    assert eintraege(a) == {"bank_pin": True}
    assert pin_vorhanden(a) is True, "auch in den Arbeitsspeicher übernommen"
    b = neustart(a)
    assert pin_vorhanden(b) is False and eintraege(b) == {"bank_pin": False}
    x = lauf(b)
    assert (x["status"], x["fehler"]["code"]) == ("fehlgeschlagen", "bank_pin_fehlt"), "gesperrt wie ohne PIN"
    entsperren(b)
    assert pin_vorhanden(b) is True
    assert lauf(b)["status"] == "erfolgreich", "der Lauf verwendet die gemerkte PIN ohne Eingabe"


def test_gesperrt_mit_eingegebener_pin(tmp_path, netz_gesperrt):
    a = _ein(tmp_path)
    merken(a)
    b = neustart(a)
    _pin(b)
    assert pin_vorhanden(b) is True
    assert lauf(b)["status"] == "erfolgreich"


def test_arbeitsspeicher_vor_gemerkter_pin(tmp_path, netz_gesperrt):
    a = _ein(tmp_path)
    merken(a, FALSCHE_PIN)
    b = neustart(a)
    entsperren(b)
    _pin(b)
    assert lauf(b)["status"] == "erfolgreich", "PIN im Arbeitsspeicher hat Vorrang"
    assert schutz(b)["pin_gemerkt"] is True
    b.delete("/api/sync/pin", erwartet=204)
    assert schutz(b)["pin_gemerkt"] is False and "bank_pin" not in eintraege(b), "verwerfen löscht auch die gemerkte"
    assert pin_vorhanden(b) is False
    assert pin_vorhanden(neustart(b)) is False


def test_gemerkte_pin_loeschen(tmp_path, netz_gesperrt):
    a = _ein(tmp_path)
    merken(a)
    a.delete("/api/sync/pin/gemerkt", erwartet=204)
    a.delete("/api/sync/pin/gemerkt", erwartet=204)
    assert schutz(a)["pin_gemerkt"] is False and eintraege(a) == {} and schutz(a)["geschuetzt"] == 0
    assert pin_vorhanden(a) is True, "die PIN im Arbeitsspeicher bleibt"
    assert lauf(a)["status"] == "erfolgreich"
    merken(a)
    b = neustart(a)
    b.delete("/api/sync/pin/gemerkt", erwartet=204)
    assert "bank_pin" not in eintraege(b), "auch gesperrt"
    entsperren(b)
    assert pin_vorhanden(b) is False
    ohne = m23_mock_api(tmp_path / "ohne")
    ohne.delete("/api/sync/pin/gemerkt", erwartet=204)


def test_falsche_gemerkte_pin_wird_geloescht(tmp_path, netz_gesperrt):
    a = _ein(tmp_path)
    merken(a, FALSCHE_PIN)
    x = lauf(a)
    assert (x["status"], x["fehler"]["code"]) == ("fehlgeschlagen", "bank_pin_falsch")
    assert schutz(a)["pin_gemerkt"] is False and "bank_pin" not in eintraege(a)
    assert pin_vorhanden(a) is False
    assert lauf(a)["fehler"]["code"] == "bank_pin_fehlt", "kein zweiter Versuch mit ihr"


def test_ausschalten_loescht_gemerkte_pin(tmp_path, netz_gesperrt):
    a = _ein(tmp_path)
    merken(a)
    b = neustart(a)
    ausschalten(b)
    assert schutz(b)["pin_gemerkt"] is False and "bank_pin" not in eintraege(b)
    c = neustart(b)
    assert pin_vorhanden(c) is False
    assert lauf(c)["fehler"]["code"] == "bank_pin_fehlt"
    d = _ein(tmp_path / "d")
    merken(d)
    ausschalten(d)
    assert "bank_pin" not in eintraege(d) and schutz(d)["pin_gemerkt"] is False


def test_pin_nirgends(tmp_path, caplog, capfd, netz_gesperrt):
    caplog.set_level(logging.DEBUG)
    a = _ein(tmp_path)
    merken(a, FALSCHE_PIN)
    lauf(a)
    merken(a)
    lauf(a)
    daten = sicherung(a)
    b = neustart(a)
    entsperren(b)
    lauf(b)
    raus, err = capfd.readouterr()
    texte = [caplog.text, raus, err] + [r.getMessage() for r in caplog.records]
    for pfad in ("/api/sync/status", "/api/sync/laeufe", "/api/geheimnisse", "/api/benachrichtigungen",
                 "/api/aenderungen"):
        texte.append(b.get(pfad, erwartet=200).text)
    for w in (PIN, FALSCHE_PIN, PASSWORT):
        assert all(w not in t for t in texte), w
        assert not enthaelt(daten, w), "nicht in der Sicherung"
        for d in db_dateien(b):
            assert w.encode() not in d.read_bytes(), d.name
