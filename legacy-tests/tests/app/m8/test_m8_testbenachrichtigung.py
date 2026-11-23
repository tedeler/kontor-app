"""M8/W-005: Test-Benachrichtigung aus den Einstellungen (benachrichtigungen.md 8, E-138) – ohne Browser."""

from __future__ import annotations

import pytest

from tests.hilfen.api import Api, fehlercode, neue_api
from tests.hilfen.m2 import mock_config
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m6 import NTFY_TOKEN, THEMA, benachrichtigungen, geheimnis_setzen, ntfy_felder, zustellung
from tests.hilfen.m7 import CSRF, anmelden, m7_api
from tests.hilfen.ntfy_attrappe import NtfyAttrappe

PFAD = "/api/benachrichtigungen/test"
TITEL = "Kontor: Test-Benachrichtigung"
OEFFENTLICH = "https://kontor.heim.example.invalid:8443/"


def _spuren(api: Api) -> dict:
    """Alles, was die Test-Benachrichtigung nicht verändern darf (benachrichtigungen.md 8)."""
    aus = {
        "benachrichtigungen": benachrichtigungen(api),
        "zustellung": zustellung(api),
        "aenderung": letzte_aenderung_id(api),
        "aenderungen_gesamt": api.get("/api/aenderungen", erwartet=200).daten["gesamt"],
    }
    if api.config.mock_modus:
        aus["mock_zustellungen"] = api.get("/api/mock/zustellungen", erwartet=200).daten
    return aus


def _senden(api: Api, erwartet: int = 200):
    return api.post(PFAD, erwartet=erwartet)


@pytest.mark.kern
def test_mock_plugin_bestaetigt_ohne_zu_senden(tmp_path):
    api = neue_api(tmp_path, mock_modus=True)
    vorher = _spuren(api)
    for _ in range(2):
        r = _senden(api)
        assert r.daten == {"plugin": "mock", "zugestellt": True, "gesendet": False, "fehler": None}
    assert _spuren(api) == vorher
    assert vorher["mock_zustellungen"] == [], "keine Nachricht in /api/mock/zustellungen"


@pytest.mark.kern
@pytest.mark.parametrize("modus", ["echt", "mock"])
def test_plugin_keins_409(tmp_path, modus):
    felder = {"mock_modus": True, "benachrichtigung_plugin": "keins"} if modus == "mock" else {}
    api = neue_api(tmp_path, **felder)  # Echtmodus: Vorgabe keins (benachrichtigungen.md 2)
    vorher = _spuren(api)
    r = _senden(api, erwartet=409)
    assert fehlercode(r) == "kein_benachrichtigungs_plugin"
    assert r.json()["fehler"]["details"] == {}
    assert _spuren(api) == vorher


@pytest.mark.kern
def test_ntfy_genau_eine_nachricht_echtmodus(tmp_path, netz_nur_loopback):
    with NtfyAttrappe() as n:
        api = neue_api(tmp_path, **ntfy_felder(n))
        vorher = _spuren(api)
        r = _senden(api)
        assert r.daten == {"plugin": "ntfy", "zugestellt": True, "gesendet": True, "fehler": None}
        assert len(n.versuche) == 1
        a = n.versuche[0].anfrage
        assert (a.methode, a.pfad) == ("POST", "/")
        assert a.koepfe["content-type"].split(";")[0] == "application/json"
        assert "authorization" not in a.koepfe
        k = n.versuche[0].koerper
        assert set(k) == {"topic", "title", "message", "priority", "tags"}, "ohne oeffentliche_url kein click"
        assert (k["topic"], k["title"], k["priority"], k["tags"]) == (THEMA, TITEL, 3, ["test"])
        assert isinstance(k["message"], str) and k["message"].strip()
        assert _spuren(api) == vorher
        # die Zustellung ausstehender Benachrichtigungen sendet sie nicht noch einmal
        api.post("/api/benachrichtigungen/zustellen", erwartet=200)
        assert len(n.versuche) == 1


@pytest.mark.kern
def test_ntfy_mock_modus_praefix_und_link(tmp_path, netz_nur_loopback):
    with NtfyAttrappe() as n:
        api = neue_api(tmp_path, mock_modus=True, oeffentliche_url=OEFFENTLICH, **ntfy_felder(n))
        vorher = _spuren(api)
        assert _senden(api).daten == {"plugin": "ntfy", "zugestellt": True, "gesendet": True, "fehler": None}
        k = n.versuche[0].koerper
        assert k["title"] == "[Mock] " + TITEL
        assert k["click"] == "https://kontor.heim.example.invalid:8443/einstellungen"
        assert set(k) == {"topic", "title", "message", "priority", "tags", "click"}
        assert _spuren(api) == vorher
        assert vorher["mock_zustellungen"] == []


def test_ntfy_mit_token(tmp_path, netz_nur_loopback):
    with NtfyAttrappe(erwartetes_token=NTFY_TOKEN) as n:
        api = neue_api(tmp_path, **ntfy_felder(n))
        r = _senden(api)
        assert r.daten["zugestellt"] is False and r.daten["fehler"]["status"] == 401, "ohne Token abgelehnt"
        geheimnis_setzen(api, "ntfy_token", NTFY_TOKEN)
        r = _senden(api)
        assert r.daten == {"plugin": "ntfy", "zugestellt": True, "gesendet": True, "fehler": None}
        assert n.versuche[-1].anfrage.koepfe["authorization"] == f"Bearer {NTFY_TOKEN}"
        assert NTFY_TOKEN not in r.text
        assert len(n.versuche) == 2


@pytest.mark.kern
def test_ntfy_fehlschlag_ohne_wiederholung(tmp_path, netz_nur_loopback):
    with NtfyAttrappe() as n:
        api = neue_api(tmp_path, **ntfy_felder(n, ntfy_timeout_sekunden=1))
        vorher = _spuren(api)
        n.statusfolge = [500]
        r = _senden(api)
        assert r.status_code == 200
        d = r.daten
        assert (d["plugin"], d["zugestellt"], d["gesendet"]) == ("ntfy", False, True)
        assert d["fehler"]["code"] == "benachrichtigung_fehler" and d["fehler"]["status"] == 500
        assert d["fehler"]["meldung"].strip()
        assert len(n.versuche) == 1
        api.post("/api/benachrichtigungen/zustellen", erwartet=200)
        assert len(n.versuche) == 1, "keine Wiederholung"
        assert _spuren(api) == vorher, "kein letzter_fehler, keine Benachrichtigung"
        n.verzoegerung = 2.5
        d = _senden(api).daten
        assert (d["zugestellt"], d["fehler"]["code"], d["fehler"]["status"]) == (False, "benachrichtigung_fehler",
                                                                                  None)
        assert _spuren(api) == vorher


def test_vorhandene_zustellungen_unberuehrt(tmp_path):
    """Eine echte Benachrichtigung (Bankfehler) bleibt die einzige Zustellung; der Test ändert nichts daran."""
    api = Api(mock_config(tmp_path, szenario="bankfehler"))
    api.post("/api/sync", json={}, erwartet=200)
    vorher = _spuren(api)
    assert len(vorher["benachrichtigungen"]) == 1 and len(vorher["mock_zustellungen"]) == 1
    assert _senden(api).daten["gesendet"] is False
    assert _spuren(api) == vorher


def test_nicht_in_der_sicherung(tmp_path):
    api = neue_api(tmp_path, mock_modus=True)
    api.konto("Girokonto", "girokonto")
    vorher = api.get("/api/sicherung", erwartet=200).content
    _senden(api)
    nachher = api.get("/api/sicherung", erwartet=200).content
    import io
    import json
    import zipfile

    def manifest(roh: bytes) -> dict:
        with zipfile.ZipFile(io.BytesIO(roh)) as z:
            m = json.loads(z.read("manifest.json"))
        return {k: m[k] for k in ("anzahl", "inhalt_sha256")}
    assert manifest(vorher) == manifest(nachher)


def test_methode_und_anmeldung(tmp_path):
    api = neue_api(tmp_path, mock_modus=True)
    assert fehlercode(api.get(PFAD, erwartet=405)) == "methode_nicht_erlaubt"
    geschuetzt = m7_api(tmp_path / "m7", mock_modus=True)
    assert fehlercode(geschuetzt.post(PFAD, erwartet=401)) == "nicht_angemeldet"
    anmelden(geschuetzt)
    token, geschuetzt.csrf = geschuetzt.csrf, None
    assert fehlercode(geschuetzt.post(PFAD, erwartet=403)) == "csrf_ungueltig"
    r = geschuetzt.post(PFAD, headers={CSRF: token}, erwartet=200)
    assert r.daten["plugin"] == "mock"
