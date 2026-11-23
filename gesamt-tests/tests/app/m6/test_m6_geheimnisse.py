"""M6: verschlüsselter Geheimnisspeicher (geheimnisse.md; K 3, T 16, T 18)."""

from __future__ import annotations

import base64
import logging
import secrets
import stat

import pytest

from tests.hilfen.api import Api, fehlercode, neue_config
from tests.hilfen.m2 import db_dateien
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m6 import geheimnis_setzen, geheimnisse, jetzt, zeit
from tests.hilfen.m9 import einspielen, enthaelt, sicherung

WERT = "SYNTH-NTFY-GEHEIMNIS-5c1e"
SECRET = "SYNTH-OAUTH-SECRET-9b2f"


def _schluesseldatei(api: Api):
    c = api.config
    return c.geheimnis_schluessel_datei or c.aktive_datenbank.with_suffix(".schluessel")


@pytest.mark.kern
def test_anfangs_leer_und_nichts_angelegt(api):
    g = geheimnisse(api)
    assert g == {"schluessel": {"quelle": "datei", "vorhanden": False, "gueltig": False}, "eintraege": []}
    assert not _schluesseldatei(api).exists(), "create_app legt keinen Schlüssel an"


@pytest.mark.kern
def test_setzen_legt_schluessel_an(api):
    vorher = jetzt()
    geheimnis_setzen(api, "ntfy_token", WERT)
    datei = _schluesseldatei(api)
    assert datei == api.config.aktive_datenbank.with_suffix(".schluessel") and datei.exists()
    assert stat.S_IMODE(datei.stat().st_mode) == 0o600
    roh = datei.read_bytes()
    assert len(base64.b64decode(roh.strip(), validate=True)) == 32
    g = geheimnisse(api)
    assert g["schluessel"] == {"quelle": "datei", "vorhanden": True, "gueltig": True}
    (e,) = g["eintraege"]
    assert e["name"] == "ntfy_token" and e["lesbar"] is True
    assert vorher <= zeit(e["gesetzt_am"]) <= jetzt()


@pytest.mark.kern
def test_ersetzen_loeschen_und_sortierung(api):
    geheimnis_setzen(api, "oauth_client_secret", SECRET)
    geheimnis_setzen(api, "ntfy_token", WERT)
    geheimnis_setzen(api, "ntfy_token", WERT + "-NEU")
    assert [e["name"] for e in geheimnisse(api)["eintraege"]] == ["ntfy_token", "oauth_client_secret"]
    api.delete("/api/geheimnisse/ntfy_token", erwartet=204)
    api.delete("/api/geheimnisse/ntfy_token", erwartet=204)
    assert [e["name"] for e in geheimnisse(api)["eintraege"]] == ["oauth_client_secret"]


@pytest.mark.kern
@pytest.mark.parametrize("name", ["pin", "bank_pin", "mail_token:haushalt.eins@example.invalid", "NTFY_TOKEN"])
def test_unbekannte_namen(api, name):
    assert fehlercode(api.put(f"/api/geheimnisse/{name}", json={"wert": "SYNTH-X"}, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.delete(f"/api/geheimnisse/{name}", erwartet=404)) == "nicht_gefunden"


@pytest.mark.kern
@pytest.mark.parametrize("koerper,geheim", [
    ({}, None), ({"wert": ""}, None), ({"wert": "SYNTH-LANG-" + "z" * 4090}, "z" * 4090),
    ({"wert": 4711815}, "4711815"), ({"wert": "SYNTH-EXTRA-FELD", "x": 1}, "SYNTH-EXTRA-FELD"),
    ({"wert": ["SYNTH-IN-LISTE"]}, "SYNTH-IN-LISTE"),
], ids=["fehlt", "leer", "zu_lang", "zahl", "feld_unbekannt", "liste"])
def test_validierung_ohne_echo(api, koerper, geheim):
    r = api.put("/api/geheimnisse/ntfy_token", json=koerper, erwartet=422)
    assert fehlercode(r) == "validierung"
    if geheim:
        assert geheim not in r.text
    assert geheimnisse(api)["eintraege"] == []


@pytest.mark.kern
def test_nie_im_klartext(api, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    geheimnis_setzen(api, "ntfy_token", WERT)
    geheimnis_setzen(api, "oauth_client_secret", SECRET)
    texte = [api.get("/api/geheimnisse", erwartet=200).text, api.get("/api/aenderungen", erwartet=200).text,
             api.get("/api/benachrichtigungen", erwartet=200).text]
    raus, err = capfd.readouterr()
    texte += [caplog.text, raus, err]
    for w in (WERT, SECRET):
        assert all(w not in t for t in texte)
        for d in db_dateien(api):
            assert w.encode() not in d.read_bytes(), d.name
        assert w.encode() not in _schluesseldatei(api).read_bytes()


@pytest.mark.kern
def test_anderer_schluessel_unlesbar(tmp_path):
    config = neue_config(tmp_path)
    a = Api(config)
    geheimnis_setzen(a, "ntfy_token", WERT)
    datei = _schluesseldatei(a)
    datei.write_bytes(base64.b64encode(secrets.token_bytes(32)) + b"\n")
    b = Api(config)
    g = geheimnisse(b)
    assert g["schluessel"]["gueltig"] is True and g["eintraege"][0]["lesbar"] is False
    geheimnis_setzen(b, "ntfy_token", WERT)
    assert geheimnisse(b)["eintraege"][0]["lesbar"] is True


@pytest.mark.kern
@pytest.mark.parametrize("inhalt", [b"kein-base64!!", base64.b64encode(b"x" * 16) + b"\n", b""])
def test_ungueltiger_schluessel(tmp_path, inhalt):
    config = neue_config(tmp_path, geheimnis_schluessel_datei=tmp_path / "eigen.key")
    (tmp_path / "eigen.key").write_bytes(inhalt)
    a = Api(config)
    assert geheimnisse(a)["schluessel"] == {"quelle": "datei", "vorhanden": True, "gueltig": False}
    r = a.put("/api/geheimnisse/ntfy_token", json={"wert": WERT}, erwartet=409)
    assert fehlercode(r) == "geheimnis_schluessel_ungueltig" and WERT not in r.text
    assert (tmp_path / "eigen.key").read_bytes() == inhalt


@pytest.mark.kern
def test_schluessel_aus_systemd_creds(tmp_path):
    creds = tmp_path / "creds"
    creds.mkdir()
    (creds / "kontor-geheimnisschluessel").write_bytes(base64.b64encode(secrets.token_bytes(32)) + b"\n")
    config = neue_config(tmp_path, credentials_verzeichnis=creds)
    a = Api(config)
    geheimnis_setzen(a, "ntfy_token", WERT)
    assert geheimnisse(a)["schluessel"] == {"quelle": "systemd-creds", "vorhanden": True, "gueltig": True}
    assert not config.aktive_datenbank.with_suffix(".schluessel").exists(), "keine Schlüsseldatei bei systemd-creds"
    assert geheimnisse(Api(config))["eintraege"][0]["lesbar"] is True
    ohne = neue_config(tmp_path, credentials_verzeichnis=tmp_path / "leer")
    g = geheimnisse(Api(ohne))
    assert g["schluessel"]["quelle"] == "datei" and g["eintraege"][0]["lesbar"] is False


@pytest.mark.kern
def test_kein_protokoll(api):
    a0 = letzte_aenderung_id(api)
    geheimnis_setzen(api, "ntfy_token", WERT)
    api.delete("/api/geheimnisse/ntfy_token", erwartet=204)
    assert letzte_aenderung_id(api) == a0


@pytest.mark.kern
def test_nie_in_der_sicherung(tmp_path):
    """sicherung.md 2.6, E-090: weder Klartext noch Chiffretext; Einspielen lässt Geheimnisse unverändert."""
    quelle = Api(neue_config(tmp_path / "a", geheimnis_schluessel_datei=tmp_path / "gemeinsam.key"))
    quelle.konto("Girokonto")
    geheimnis_setzen(quelle, "ntfy_token", WERT)
    geheimnis_setzen(quelle, "oauth_client_secret", SECRET)
    daten = sicherung(quelle)
    assert not enthaelt(daten, WERT) and not enthaelt(daten, SECRET)
    ziel = Api(neue_config(tmp_path / "b", geheimnis_schluessel_datei=tmp_path / "gemeinsam.key"))
    einspielen(ziel, daten)
    assert geheimnisse(ziel)["eintraege"] == [], "Geheimnisse kommen nicht mit der Sicherung"
    geheimnis_setzen(ziel, "ntfy_token", "SYNTH-ZIEL-TOKEN")
    zweite = Api(neue_config(tmp_path / "c"))
    zweite.konto("Sparkonto", "sparkonto")
    einspielen(ziel, sicherung(zweite))
    assert [(e["name"], e["lesbar"]) for e in geheimnisse(ziel)["eintraege"]] == [("ntfy_token", True)]


@pytest.mark.kern
def test_mock_und_echt_getrennt(tmp_path):
    echt = Api(neue_config(tmp_path))
    geheimnis_setzen(echt, "ntfy_token", WERT)
    mock = Api(neue_config(tmp_path, mock_modus=True))
    assert geheimnisse(mock)["eintraege"] == []
    geheimnis_setzen(mock, "ntfy_token", "SYNTH-MOCK-TOKEN")
    assert mock.config.aktive_datenbank.with_suffix(".schluessel").exists()
    assert mock.config.aktive_datenbank.with_suffix(".schluessel") != echt.config.aktive_datenbank.with_suffix(
        ".schluessel")
