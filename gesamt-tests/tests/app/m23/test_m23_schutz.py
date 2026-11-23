"""M23: Schutz der Geheimnisse mit dem Login-Passwort – Zustände, Endpunkte, Bremse, Login und Passwort
(geheimnisschutz.md 1, 2; E-229)."""

from __future__ import annotations

import logging

import pytest

from tests.hilfen.api import Api
from tests.hilfen.m2 import db_dateien
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m6 import CLIENT_SECRET, NTFY_TOKEN, geheimnis_setzen
from tests.hilfen.m7 import COOKIE, NEUES_PASSWORT, PASSWORT, anmelden, m7_config, sitzungstoken, zweiter_client
from tests.hilfen.m23 import (
    AUS, ENDPUNKTE, FALSCH, PIN, ausschalten, code, einschalten, eintraege, entsperren, lauf, m23_mock_api,
    m23_mock_config, merken, neustart, pin_vorhanden, schluessel_tauschen, schutz, sperren,
)

pytestmark = pytest.mark.kern

EIN_OFFEN = {"aktiv": True, "entsperrt": True, "gesperrt": False}
EIN_ZU = {"aktiv": True, "entsperrt": False, "gesperrt": True}


def _teil(s: dict, soll: dict) -> None:
    assert {k: s[k] for k in soll} == soll, s


# ------------------------------------------------------------------ Zustände
def test_anfangs_aus_und_sperren_ohne_wirkung(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    assert schutz(api) == AUS
    assert sperren(api) == AUS
    assert schutz(api) == AUS
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    assert schutz(api) == AUS, "ohne Schutz ist geschuetzt immer 0"
    assert eintraege(api) == {"oauth_client_secret": True}


def test_einschalten_zaehlt_und_entsperrt(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    geheimnis_setzen(api, "ntfy_token", NTFY_TOKEN)
    s = einschalten(api).daten
    assert s == {**EIN_OFFEN, "geschuetzt": 1, "pin_gemerkt": False}, "ntfy_token zählt nicht"
    assert schutz(api) == s
    assert eintraege(api) == {"ntfy_token": True, "oauth_client_secret": True}
    r = einschalten(api, erwartet=409)
    assert code(r) == "schutz_bereits_aktiv"
    assert schutz(api) == s


def test_sperren_entsperren_und_schreiben(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    geheimnis_setzen(api, "ntfy_token", NTFY_TOKEN)
    einschalten(api)
    gesetzt = {e["name"]: e["gesetzt_am"] for e in api.get("/api/geheimnisse", erwartet=200).daten["eintraege"]}
    s = sperren(api)
    assert s == {**EIN_ZU, "geschuetzt": 1, "pin_gemerkt": False}
    assert eintraege(api) == {"ntfy_token": True, "oauth_client_secret": False}
    r = api.put("/api/geheimnisse/oauth_client_secret", json={"wert": "SYNTH-NEUES-SECRET-23"}, erwartet=409)
    assert code(r) == "geheimnisse_gesperrt" and "SYNTH-NEUES-SECRET-23" not in r.text
    nach = {e["name"]: e["gesetzt_am"] for e in api.get("/api/geheimnisse", erwartet=200).daten["eintraege"]}
    assert nach["oauth_client_secret"] == gesetzt["oauth_client_secret"], "es wird nichts gespeichert"
    api.put("/api/geheimnisse/ntfy_token", json={"wert": NTFY_TOKEN + "-NEU"}, erwartet=204)
    e = entsperren(api).daten
    assert e == {**EIN_OFFEN, "geschuetzt": 1, "pin_gemerkt": False}
    assert entsperren(api).daten == e, "idempotent"
    assert eintraege(api) == {"ntfy_token": True, "oauth_client_secret": True}
    sperren(api)
    api.delete("/api/geheimnisse/oauth_client_secret", erwartet=204)
    assert eintraege(api) == {"ntfy_token": True}
    assert schutz(api)["geschuetzt"] == 0


def test_neustart_ist_gesperrt_je_instanz(tmp_path, netz_gesperrt):
    a = m23_mock_api(tmp_path)
    geheimnis_setzen(a, "oauth_client_secret", CLIENT_SECRET)
    einschalten(a)
    b = neustart(a)
    assert schutz(b) == {**EIN_ZU, "geschuetzt": 1, "pin_gemerkt": False}
    assert eintraege(b) == {"oauth_client_secret": False}
    _teil(schutz(a), EIN_OFFEN)
    assert eintraege(a) == {"oauth_client_secret": True}, "jede App-Instanz hat ihren eigenen Sperrzustand"
    entsperren(b)
    assert eintraege(b) == {"oauth_client_secret": True}
    sperren(a)
    _teil(schutz(b), EIN_OFFEN)


def test_entsperren_ohne_schutz(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    assert code(entsperren(api, erwartet=409)) == "schutz_nicht_aktiv"
    assert schutz(api) == AUS


def test_ausschalten(tmp_path, netz_gesperrt):
    a = m23_mock_api(tmp_path)
    assert ausschalten(a).daten == AUS, "Schutz nicht aktiv → 200 unverändert"
    geheimnis_setzen(a, "oauth_client_secret", CLIENT_SECRET)
    einschalten(a)
    b = neustart(a)
    _teil(schutz(b), EIN_ZU)
    assert ausschalten(b).daten == AUS, "auch gesperrt; das Passwort entsperrt dafür"
    assert schutz(b) == AUS
    c = neustart(b)
    assert schutz(c) == AUS
    assert eintraege(c) == {"oauth_client_secret": True}, "nach einem Neustart sofort lesbar"


def test_nicht_lesbare_werden_beim_einschalten_geloescht(tmp_path, netz_gesperrt):
    a = m23_mock_api(tmp_path)
    geheimnis_setzen(a, "oauth_client_secret", CLIENT_SECRET)
    schluessel_tauschen(a)
    b = neustart(a)
    assert eintraege(b) == {"oauth_client_secret": False}
    assert einschalten(b).daten == {**EIN_OFFEN, "geschuetzt": 0, "pin_gemerkt": False}
    assert eintraege(b) == {}


# ------------------------------------------------------------------ Prüfreihenfolge
@pytest.mark.parametrize("pfad", ENDPUNKTE)
@pytest.mark.parametrize("koerper,geheim", [
    ({}, None), ({"passwort": ""}, None), ({"passwort": "GEHEIM-LANG-" + "q" * 4090}, "q" * 4090),
    ({"passwort": 4711232323}, "4711232323"), ({"passwort": "GEHEIM-FELD-23", "x": 1}, "GEHEIM-FELD-23"),
    (["GEHEIM-LISTE-23"], "GEHEIM-LISTE-23"), ({"passwort": ["GEHEIM-IN-LISTE-23"]}, "GEHEIM-IN-LISTE-23"),
], ids=["fehlt", "leer", "zu_lang", "zahl", "feld_unbekannt", "kein_objekt", "liste"])
def test_validierung_ohne_echo(tmp_path, pfad, koerper, geheim, netz_gesperrt):
    api = m23_mock_api(tmp_path, passwort=None)
    r = api.post(pfad, json=koerper, erwartet=422)
    assert code(r) == "validierung", "Körper ungültig vor „nicht eingerichtet“"
    if geheim:
        assert geheim not in r.text
    r = api.post(pfad, erwartet=422)
    assert code(r) == "validierung", "ohne Körper"
    assert schutz(api) == AUS


@pytest.mark.parametrize("pfad", ENDPUNKTE)
def test_nicht_eingerichtet(tmp_path, pfad, netz_gesperrt):
    api = m23_mock_api(tmp_path, passwort=None)
    assert code(api.post(pfad, json={"passwort": PASSWORT}, erwartet=409)) == "nicht_eingerichtet"
    assert schutz(api) == AUS


def test_falsches_passwort_vor_endpunktregeln(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    for f in (entsperren, ausschalten):
        r = f(api, FALSCH, erwartet=403)
        assert code(r) == "anmeldung_fehlgeschlagen" and FALSCH not in r.text, "falsch vor schutz_nicht_aktiv"
    assert schutz(api) == AUS
    einschalten(api)
    r = einschalten(api, FALSCH, erwartet=403)
    assert code(r) == "anmeldung_fehlgeschlagen", "falsch vor schutz_bereits_aktiv"
    sperren(api)
    assert code(entsperren(api, FALSCH, erwartet=403)) == "anmeldung_fehlgeschlagen"
    _teil(schutz(api), EIN_ZU)
    assert code(ausschalten(api, FALSCH, erwartet=403)) == "anmeldung_fehlgeschlagen"
    _teil(schutz(api), EIN_ZU)


# ------------------------------------------------------------------ Bremse (sicherheit.md 4.5)
def _gesperrt(r) -> None:
    assert code(r) == "anmeldung_gesperrt"
    assert int(r.headers["retry-after"]) >= 1


def test_bremse_zaehlt_und_sperrt(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path, anmeldung_fehlversuche=2, anmeldung_sperre_sekunden=600)
    einschalten(api, FALSCH, erwartet=403)
    einschalten(api, erwartet=200)
    entsperren(api, FALSCH, erwartet=403)
    assert schutz(api)["aktiv"] is True, "ein richtiges Passwort setzt die Fehlversuche zurück"
    entsperren(api, FALSCH, erwartet=403)
    for pfad in ENDPUNKTE:
        _gesperrt(api.post(pfad, json={"passwort": PASSWORT}, erwartet=429))
    assert api.post(ENDPUNKTE[0], json={}, erwartet=422), "Körper ungültig vor der Bremse"
    assert api.get("/api/anmeldung", erwartet=200).daten["gesperrt_bis"] is not None, "gemeinsame Bremse"


def test_bremse_gemeinsam_mit_der_anmeldung(tmp_path, netz_gesperrt):
    config = m7_config(tmp_path, anmeldung_fehlversuche=2, anmeldung_sperre_sekunden=600)
    api = Api(config)
    anmelden(api)
    anmelden(zweiter_client(api), FALSCH, erwartet=401)
    r = einschalten(api, FALSCH, erwartet=403)
    assert code(r) == "anmeldung_fehlgeschlagen"
    _gesperrt(anmelden(zweiter_client(api), PASSWORT, erwartet=429))
    _gesperrt(einschalten(api, erwartet=429))


def test_nicht_eingerichtet_vor_bremse(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path, passwort=None)
    assert code(api.post(ENDPUNKTE[2], json={"passwort": FALSCH}, erwartet=409)) == "nicht_eingerichtet"


# ------------------------------------------------------------------ Login und Passwort (2.4)
def test_login_entsperrt(tmp_path, netz_gesperrt):
    config = m7_config(tmp_path)
    a = Api(config)
    anmelden(a)
    einschalten(a)
    b = Api(config)
    anmelden(b)
    _teil(schutz(b), EIN_OFFEN)
    sperren(b)
    _teil(schutz(b), EIN_ZU)
    b2 = zweiter_client(b)
    anmelden(b2)
    _teil(schutz(b), EIN_OFFEN)
    # Neustart mit gültiger Sitzung: gesperrt, bis jemand sich anmeldet oder entsperrt
    c = Api(config)
    c.client.cookies.set(COOKIE, sitzungstoken(b))
    c.csrf = b.csrf
    _teil(schutz(c), EIN_ZU)
    entsperren(c)
    _teil(schutz(c), EIN_OFFEN)


def test_endpunkte_geschuetzt(tmp_path, netz_gesperrt):
    api = Api(m7_config(tmp_path))
    for pfad in ENDPUNKTE + ("/api/geheimnisse/sperren",):
        assert code(api.post(pfad, json={"passwort": PASSWORT}, erwartet=401)) == "nicht_angemeldet"
    assert code(api.get("/api/geheimnisse/schutz", erwartet=401)) == "nicht_angemeldet"
    anmelden(api)
    csrf, api.csrf = api.csrf, None
    assert code(einschalten(api, erwartet=403)) == "csrf_ungueltig"
    api.csrf = csrf
    assert schutz(api) == AUS


def test_passwort_aendern_haelt_den_schutz(tmp_path, netz_gesperrt):
    config = m23_mock_config(tmp_path, anmeldung=True)
    api = Api(config)
    anmelden(api)
    einschalten(api)
    merken(api)
    sperren(api)
    r = api.put("/api/anmeldung/passwort", json={"altes_passwort": PASSWORT, "neues_passwort": NEUES_PASSWORT},
                erwartet=200)
    assert NEUES_PASSWORT not in r.text
    assert schutz(api) == {**EIN_OFFEN, "geschuetzt": 1, "pin_gemerkt": True}, "danach entsperrt"
    sperren(api)
    assert code(entsperren(api, PASSWORT, erwartet=403)) == "anmeldung_fehlgeschlagen"
    entsperren(api, NEUES_PASSWORT)
    b = Api(config)
    anmelden(b, NEUES_PASSWORT)
    assert pin_vorhanden(b) is True, "Wert erhalten: gemerkte PIN nach Neustart lesbar"
    assert lauf(b)["status"] == "erfolgreich"


# ------------------------------------------------------------------ Betriebszustand, Klartext
def test_kein_protokoll_und_kein_klartext(tmp_path, caplog, capfd, netz_gesperrt):
    caplog.set_level(logging.DEBUG)
    api = m23_mock_api(tmp_path)
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    a0 = letzte_aenderung_id(api)
    texte = [einschalten(api).text]
    merken(api)
    sperren(api)
    texte += [entsperren(api).text, ausschalten(api).text, einschalten(api).text]
    merken(api)
    texte.append(entsperren(api, FALSCH, erwartet=403).text)
    api.delete("/api/sync/pin/gemerkt", erwartet=204)
    merken(api)
    assert letzte_aenderung_id(api) == a0, "Betriebszustand: keine Änderung im Protokoll"
    assert lauf(api)["status"] == "erfolgreich"
    for pfad in ("/api/geheimnisse", "/api/geheimnisse/schutz", "/api/sync/status", "/api/sync/laeufe",
                 "/api/aenderungen", "/api/benachrichtigungen", "/api/status"):
        texte.append(api.get(pfad, erwartet=200).text)
    raus, err = capfd.readouterr()
    texte += [caplog.text, raus, err, repr(api.config)]
    texte += [r.getMessage() for r in caplog.records]
    for w in (PASSWORT, FALSCH, PIN, CLIENT_SECRET):
        for t in texte:
            assert w not in t, w
        for d in db_dateien(api):
            for k in ("utf-8", "utf-16-le"):
                assert w.encode(k) not in d.read_bytes(), (w, d.name)
