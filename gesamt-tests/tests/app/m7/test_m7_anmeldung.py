"""M7: Anmeldung, Sitzungen, Bremse, CSRF, Ersteinrichtung (sicherheit.md 3–5)."""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import stat
import time
from urllib.parse import quote

import pytest
import yaml

from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode, neue_config
from tests.hilfen.m2 import zeit
from tests.hilfen.m7 import (COOKIE, CSRF, NEUES_PASSWORT, OEFFENTLICH, PASSWORT, alle_dateibytes, anmelden,
                             anmeldung, angemeldet, cookie_attribute, einrichtungsdatei, m7_api, m7_config,
                             set_cookie, set_cookie_roh, sitzungstoken, zweiter_client)
from tests.hilfen.pfade import KMY, OPENAPI


def _jetzt() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _operationen():
    dok = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    for pfad, ops in dok["paths"].items():
        for m in ops:
            if m in ("get", "post", "put", "patch", "delete"):
                yield m, pfad


def _konkret(pfad: str) -> str:
    return re.sub(r"\{([^}]+)\}", lambda m: "DE02120300000000202051" if m[1] == "iban" else (
        "ntfy_token" if m[1] == "name" else "1"), pfad)


# ------------------------------------------------------------------ Schutz aller Pfade
@pytest.mark.kern
def test_ohne_sitzung_nur_oeffentliche_pfade(tmp_path):
    api = m7_api(tmp_path)
    for m, pfad in _operationen():
        r = api.anfrage(m.upper(), _konkret(pfad), json={} if m in ("post", "put", "patch") else None)
        if (m, pfad) in OEFFENTLICH:
            assert r.status_code != 401 or pfad == "/api/anmeldung", (m, pfad, r.status_code)
            continue
        assert r.status_code == 401, f"{m.upper()} {pfad}: ohne Sitzung {r.status_code} statt 401"
        assert fehlercode(r) == "nicht_angemeldet" and r.json()["fehler"]["details"] == {}
    # auch unbekannte Pfade und unzulässige Methoden (kein Hinweis, ob ein Pfad existiert)
    for m, pfad in (("GET", "/api/gibt-es-nicht"), ("DELETE", "/api/status"), ("POST", "/api/konten/1/x")):
        r = api.anfrage(m, pfad)
        assert r.status_code == 401 and fehlercode(r) == "nicht_angemeldet", (m, pfad)
    # 401 vor 422 und vor der Größenprüfung
    r = api.post("/api/konten", content=b"{kein json", headers={"content-type": "application/json"})
    assert r.status_code == 401


@pytest.mark.kern
def test_oeffentliche_pfade(tmp_path):
    api = m7_api(tmp_path)
    s = api.get("/api/anmeldung", erwartet=200).daten
    assert s == {"aktiv": True, "eingerichtet": True, "angemeldet": False, "csrf_token": None,
                 "sitzung_ablauf": None, "gesperrt_bis": None,
                 # D-284: Passkeys und Bildschirmsperre (sicherheit.md 13)
                 "passkeys": False, "bildschirmsperre": {"minuten": None, "gesperrt": False}}
    g = api.get("/api/gesundheit", erwartet=200).daten
    assert g["status"] == "ok" and g["version"]
    r = api.get("/anmelden")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert api.get("/oeffentlich/gibt-es-nicht.js").status_code == 404
    assert set_cookie(r) is None and set_cookie(api.get("/api/anmeldung")) is None


@pytest.mark.kern
def test_oberflaeche_leitet_zur_anmeldung(tmp_path):
    api = m7_api(tmp_path)
    for pfad in ("/", "/konten?x=1&y=ä", "/tan/7"):
        r = api.client.get(pfad, follow_redirects=False)
        assert r.status_code == 303, pfad
        assert r.headers["location"] == "/anmelden?weiter=" + quote(pfad, safe="/-._~"), r.headers["location"]
        assert "Kontor" not in r.text or len(r.text) < 200
    anmelden(api)
    assert api.client.get("/", follow_redirects=False).status_code == 200
    r = api.client.get("/anmelden", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


# ------------------------------------------------------------------ Anmelden
@pytest.mark.kern
def test_anmelden_cookie_und_status(tmp_path):
    api = m7_api(tmp_path, sitzung_leerlauf_sekunden=3600, sitzung_hoechstdauer_sekunden=7200)
    vorher = _jetzt()
    r = anmelden(api)
    st = r.daten
    assert st["aktiv"] and st["eingerichtet"] and st["angemeldet"] and st["gesperrt_bis"] is None
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", st["csrf_token"])
    ablauf = zeit(st["sitzung_ablauf"])
    assert vorher + dt.timedelta(seconds=3590) <= ablauf <= _jetzt() + dt.timedelta(seconds=3601)
    roh = set_cookie_roh(r)
    assert roh, "Set-Cookie kontor_sitzung fehlt"
    attr = cookie_attribute(roh)
    wert = roh.split(";", 1)[0].split("=", 1)[1]
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", wert)
    assert attr.get("httponly") is True and str(attr.get("samesite")).lower() == "strict"
    assert attr.get("path") == "/" and attr.get("max-age") == "7200"
    assert "secure" not in attr and "domain" not in attr, "über http kein Secure, nie Domain"
    assert api.get("/api/konten", erwartet=200).daten == []
    s2 = api.get("/api/anmeldung", erwartet=200).daten
    assert s2["angemeldet"] and s2["csrf_token"] == st["csrf_token"]


@pytest.mark.kern
@pytest.mark.parametrize("basis,einstellung,secure", [("https://testserver", None, True),
                                                      ("http://testserver", True, True),
                                                      ("https://testserver", False, False)])
def test_secure_attribut(tmp_path, basis, einstellung, secure):
    api = m7_api(tmp_path, sitzung_cookie_secure=einstellung, client_kw={"base_url": basis})
    attr = cookie_attribute(set_cookie_roh(anmelden(api)))
    assert ("secure" in attr) is secure
    if basis.startswith("https") or not secure:  # über http sendet der Client ein Secure-Cookie nicht zurück
        assert api.get("/api/konten", erwartet=200).daten == []


@pytest.mark.kern
def test_falsches_passwort(tmp_path):
    api = m7_api(tmp_path)
    r = anmelden(api, "Falsches-Passwort-123", erwartet=401)
    assert fehlercode(r) == "anmeldung_fehlgeschlagen" and r.json()["fehler"]["details"] == {}
    assert "Falsches-Passwort-123" not in r.text and set_cookie(r) is None
    assert api.get("/api/konten", erwartet=401)
    assert anmelden(api, PASSWORT.lower(), erwartet=401)


def _token(r) -> str:
    return set_cookie(r)[COOKIE].value


def test_keine_sitzungsfixierung(tmp_path):
    api = m7_api(tmp_path)
    vorgabe = "A" * 43
    r = api.client.post("/api/anmeldung", json={"passwort": PASSWORT}, headers={"cookie": f"{COOKIE}={vorgabe}"})
    erstes = _token(r)
    assert r.status_code == 200 and erstes != vorgabe
    r = api.client.post("/api/anmeldung", json={"passwort": PASSWORT}, headers={"cookie": f"{COOKIE}={erstes}"})
    zweites = _token(r)
    assert r.status_code == 200 and zweites != erstes
    for token in (erstes, zweites):
        alt = zweiter_client(api)
        alt.client.cookies.set(COOKIE, token)
        alt.get("/api/konten", erwartet=200)  # beide Sitzungen gültig, die vorgegebene nie
    alt = zweiter_client(api)
    alt.client.cookies.set(COOKIE, vorgabe)
    alt.get("/api/konten", erwartet=401)


def test_sitzung_uebersteht_neustart(tmp_path):
    api = angemeldet(tmp_path)
    token, csrf = sitzungstoken(api), api.csrf
    neu = Api(api.config)
    neu.client.cookies.set(COOKIE, token)
    neu.csrf = csrf
    assert neu.get("/api/konten", erwartet=200).daten == []
    assert neu.konto("Nach Neustart")["name"] == "Nach Neustart"


def test_token_nie_in_dateien(tmp_path):
    api = angemeldet(tmp_path / "db")
    api.konto("Giro")
    token = sitzungstoken(api)
    inhalt = alle_dateibytes(tmp_path / "db")
    assert token.encode() not in inhalt, "Sitzungstoken im Klartext in der Datenbank"
    assert PASSWORT.encode() not in inhalt


# ------------------------------------------------------------------ Bremse
@pytest.mark.kern
def test_bremse_mit_verdopplung(tmp_path):
    api = m7_api(tmp_path, anmeldung_fehlversuche=3, anmeldung_sperre_sekunden=1)
    falsch = "Falsches-Passwort-999"
    anmelden(api, falsch, erwartet=401)
    anmelden(api, falsch, erwartet=401)
    anmelden(api, falsch, erwartet=401)  # dritter Fehlversuch: noch 401, Sperre beginnt
    r = anmelden(api, PASSWORT, erwartet=429)  # auch das richtige Passwort wird nicht geprüft
    assert fehlercode(r) == "anmeldung_gesperrt" and 1 <= int(r.headers["retry-after"]) <= 1
    bis = zeit(r.json()["fehler"]["details"]["gesperrt_bis"])
    assert _jetzt() < bis <= _jetzt() + dt.timedelta(seconds=1.5)
    assert api.get("/api/anmeldung", erwartet=200).daten["gesperrt_bis"] is not None
    time.sleep(1.2)
    anmelden(api, falsch, erwartet=401)  # vierter: Sperre 2 s
    r = anmelden(api, falsch, erwartet=429)
    assert 1 <= int(r.headers["retry-after"]) <= 2
    bis = zeit(r.json()["fehler"]["details"]["gesperrt_bis"])
    assert _jetzt() + dt.timedelta(seconds=1) < bis <= _jetzt() + dt.timedelta(seconds=2.5)
    time.sleep(2.2)
    anmelden(api, PASSWORT)  # Erfolg setzt zurück
    assert api.get("/api/anmeldung", erwartet=200).daten["gesperrt_bis"] is None
    anmelden(api, falsch, erwartet=401)
    anmelden(api, falsch, erwartet=401)
    anmelden(api, PASSWORT)  # nach Zurücksetzen erst ab dem dritten Fehlversuch gesperrt


def test_bremse_uebersteht_neustart_und_protokolliert(tmp_path, caplog):
    api = m7_api(tmp_path, anmeldung_fehlversuche=2, anmeldung_sperre_sekunden=30)
    falsch = "Ganz-falsches-Passwort-42"
    with caplog.at_level(logging.DEBUG):
        anmelden(api, falsch, erwartet=401)
        anmelden(api, falsch, erwartet=401)
        anmelden(Api(api.config), PASSWORT, erwartet=429)
    warnungen = [r for r in caplog.records if r.name.startswith("kontor.anmeldung") and r.levelno == logging.WARNING]
    assert len(warnungen) >= 2, "Fehlversuche und Sperre werden mit WARNING protokolliert"
    assert falsch not in caplog.text and PASSWORT not in caplog.text


# ------------------------------------------------------------------ Ablauf
@pytest.mark.kern
def test_leerlauf(tmp_path):
    api = angemeldet(tmp_path, sitzung_leerlauf_sekunden=3)
    time.sleep(1.8)
    api.get("/api/konten", erwartet=200)
    time.sleep(1.8)
    api.get("/api/konten", erwartet=200)  # Aktivität verlängert (3,6 s nach der Anmeldung)
    time.sleep(3.8)
    r = api.get("/api/konten", erwartet=401)
    assert fehlercode(r) == "nicht_angemeldet"
    assert api.get("/api/anmeldung", erwartet=200).daten["angemeldet"] is False


@pytest.mark.kern
def test_hoechstdauer(tmp_path):
    api = angemeldet(tmp_path, sitzung_hoechstdauer_sekunden=5)
    token = sitzungstoken(api)
    for _ in range(3):
        time.sleep(1.0)
        api.get("/api/konten", erwartet=200)
    time.sleep(2.8)
    # Cookie selbst senden: Max-Age=5 ließe es sonst schon im Client verfallen (Prüfung des Servers)
    alt = zweiter_client(api)
    alt.client.cookies.set(COOKIE, token)
    assert fehlercode(alt.get("/api/konten", erwartet=401)) == "nicht_angemeldet"


def test_mock_uhr_wirkt_nicht(tmp_path):
    api = angemeldet(tmp_path, mock_modus=True, mock_heute=dt.date(2024, 6, 30), sitzung_leerlauf_sekunden=60,
                     anmeldung_fehlversuche=1, anmeldung_sperre_sekunden=60)
    api.put("/api/mock/zeit", json={"jetzt": "2034-06-30T12:00:00Z"}, erwartet=200)
    api.get("/api/konten", erwartet=200)
    zweiter = zweiter_client(api)
    anmelden(zweiter, "Falsches-Passwort-777", erwartet=401)
    api.put("/api/mock/zeit", json={"jetzt": "2044-06-30T12:00:00Z"}, erwartet=200)
    anmelden(zweiter, PASSWORT, erwartet=429)


# ------------------------------------------------------------------ Abmelden, Passwort
@pytest.mark.kern
def test_abmelden(tmp_path):
    api = angemeldet(tmp_path)
    andere = zweiter_client(api)
    anmelden(andere)
    token = sitzungstoken(api)
    r = api.post("/api/anmeldung/abmelden", erwartet=204)
    attr = cookie_attribute(set_cookie_roh(r))
    assert attr.get("max-age") == "0"
    alt = zweiter_client(api)
    alt.client.cookies.set(COOKIE, token)
    assert fehlercode(alt.get("/api/konten", erwartet=401)) == "nicht_angemeldet", "serverseitig beendet"
    andere.get("/api/konten", erwartet=200)


@pytest.mark.kern
def test_passwort_aendern(tmp_path):
    a = angemeldet(tmp_path)
    b = zweiter_client(a)
    anmelden(b)
    csrf = a.csrf
    r = a.put("/api/anmeldung/passwort", json={"altes_passwort": "Falsch-Falsch-Falsch", "neues_passwort": NEUES_PASSWORT},
              erwartet=403)
    assert fehlercode(r) == "anmeldung_fehlgeschlagen"
    r = a.put("/api/anmeldung/passwort", json={"altes_passwort": PASSWORT, "neues_passwort": "zu-kurz"}, erwartet=422)
    assert "zu-kurz" not in r.text and PASSWORT not in r.text
    st = a.put("/api/anmeldung/passwort", json={"altes_passwort": PASSWORT, "neues_passwort": NEUES_PASSWORT},
               erwartet=200).daten
    assert st["angemeldet"] and st["csrf_token"] == csrf
    a.get("/api/konten", erwartet=200)
    a.konto("Nach Änderung")
    b.get("/api/konten", erwartet=401)
    c = zweiter_client(a)
    anmelden(c, PASSWORT, erwartet=401)
    anmelden(c, NEUES_PASSWORT)


def test_passwort_setzen_beendet_sitzungen(tmp_path):
    api = angemeldet(tmp_path)
    anmeldung().passwort_setzen(api.config, NEUES_PASSWORT)
    api.get("/api/konten", erwartet=401)
    anmelden(api, NEUES_PASSWORT)


# ------------------------------------------------------------------ CSRF und Herkunft
@pytest.mark.kern
def test_csrf_token_pflicht(tmp_path):
    api = angemeldet(tmp_path)
    k = api.konto("Giro")
    anzahl = api.get("/api/aenderungen", erwartet=200).daten["gesamt"]
    csrf, api.csrf = api.csrf, None
    for m, pfad, body in (("POST", "/api/konten", {"name": "Ohne Token", "art": "girokonto"}),
                          ("PATCH", f"/api/konten/{k['id']}", {"name": "Geändert"}),
                          ("DELETE", f"/api/konten/{k['id']}", None), ("POST", "/api/anmeldung/abmelden", None)):
        for kopf in ({}, {CSRF: "x" * 43}, {CSRF: csrf[:-1] + ("A" if csrf[-1] != "A" else "B")}):
            r = api.anfrage(m, pfad, json=body, headers=kopf)
            assert r.status_code == 403 and fehlercode(r) == "csrf_ungueltig", (m, pfad, kopf, r.status_code)
    api.csrf = csrf
    assert [x["name"] for x in api.konten()] == ["Giro"], "abgelehnte Anfragen ohne Wirkung"
    assert api.get("/api/aenderungen", erwartet=200).daten["gesamt"] == anzahl, "keine Änderung im Protokoll"
    api.get("/api/konten", headers={}, erwartet=200)  # GET ohne Token
    r = api.import_kmy(KMY / "minimal.kmy", erwartet=200)  # Multipart mit Token
    assert r.daten["erfolgreich"]


@pytest.mark.kern
@pytest.mark.parametrize("koepfe,ok", [
    ({"origin": "http://testserver"}, True), ({"origin": "http://evil.example.invalid"}, False),
    ({"origin": "null"}, False), ({"origin": "https://testserver"}, False),
    ({"sec-fetch-site": "cross-site"}, False), ({"sec-fetch-site": "same-origin"}, True),
    ({"origin": "http://testserver:8080"}, False)])
def test_herkunft(tmp_path, koepfe, ok):
    api = angemeldet(tmp_path)
    r = api.post("/api/konten", json={"name": "Herkunft", "art": "girokonto"}, headers=koepfe)
    assert r.status_code == (201 if ok else 403), (koepfe, r.status_code)
    if not ok:
        assert fehlercode(r) == "csrf_ungueltig" and api.konten() == []
    neu = m7_api(tmp_path / "b")
    r = neu.post("/api/anmeldung", json={"passwort": PASSWORT}, headers=koepfe)
    assert r.status_code == (200 if ok else 403)
    if not ok:
        assert set_cookie(r) is None


def test_herkunft_oeffentliche_url(tmp_path):
    api = angemeldet(tmp_path, oeffentliche_url="http://kontor.example.invalid:8000")
    api.post("/api/konten", json={"name": "A", "art": "girokonto"}, headers={"origin": "http://kontor.example.invalid:8000"},
             erwartet=201)
    api.post("/api/konten", json={"name": "B", "art": "girokonto"}, headers={"origin": "http://kontor.example.invalid"},
             erwartet=403)


# ------------------------------------------------------------------ abgeschaltet
@pytest.mark.kern
def test_abgeschaltet_wie_m6(tmp_path):
    api = Api(neue_config(tmp_path))
    s = api.get("/api/anmeldung", erwartet=200).daten
    assert s["aktiv"] is False and s["angemeldet"] is False and s["csrf_token"] is None
    for m, pfad, body in (("POST", "/api/anmeldung", {"passwort": PASSWORT}),
                          ("POST", "/api/anmeldung/einrichten", {"einrichtungscode": "0" * 32, "passwort": PASSWORT}),
                          ("POST", "/api/anmeldung/abmelden", None),
                          ("PUT", "/api/anmeldung/passwort", {"altes_passwort": PASSWORT, "neues_passwort": PASSWORT})):
        r = api.anfrage(m, pfad, json=body)
        assert r.status_code == 409 and fehlercode(r) == "anmeldung_abgeschaltet", pfad
    r = api.client.get("/anmelden", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert api.get("/api/gibt-es-nicht").status_code == 404
    r = api.post("/api/konten", json={"name": "Offen", "art": "girokonto"}, erwartet=201)
    assert set_cookie(r) is None and api.get("/", erwartet=200)


def test_warnung_ohne_anmeldung_im_echtmodus(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        kontor.create_app(neue_config(tmp_path / "e"))
    assert any(r.levelno >= logging.WARNING and r.name.startswith("kontor") for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        kontor.create_app(m7_config(tmp_path / "a"))
    assert not [r for r in caplog.records if r.name.startswith("kontor") and "anmeldung" in r.getMessage().lower()
                and r.levelno >= logging.WARNING]


# ------------------------------------------------------------------ Ersteinrichtung
def test_einrichtung_mit_code(tmp_path, caplog):
    c = m7_config(tmp_path, passwort=None, anmeldung_fehlversuche=5)
    with caplog.at_level(logging.DEBUG):
        api = Api(c)
    datei = einrichtungsdatei(c)
    inhalt = datei.read_text(encoding="ascii")
    assert re.fullmatch(r"[0-9a-f]{32}\n", inhalt), inhalt
    assert stat.S_IMODE(os.stat(datei).st_mode) == 0o600
    code = inhalt.strip()
    assert code not in caplog.text and datei.name in caplog.text, "Pfad der Datei, nie der Code im Log"
    Api(c)
    assert datei.read_text(encoding="ascii") == inhalt, "vorhandene Datei wird weiterverwendet"
    s = api.get("/api/anmeldung", erwartet=200).daten
    assert s["eingerichtet"] is False
    assert fehlercode(anmelden(api, PASSWORT, erwartet=409)) == "nicht_eingerichtet"
    assert api.get("/api/konten", erwartet=401)
    r = api.post("/api/anmeldung/einrichten", json={"einrichtungscode": code, "passwort": "kurz"}, erwartet=422)
    assert "kurz" not in r.text and code not in r.text
    r = api.post("/api/anmeldung/einrichten", json={"einrichtungscode": "f" * 32, "passwort": PASSWORT}, erwartet=403)
    assert fehlercode(r) == "einrichtungscode_ungueltig" and code not in r.text
    r = api.post("/api/anmeldung/einrichten", json={"einrichtungscode": code, "passwort": PASSWORT}, erwartet=200)
    assert r.daten["angemeldet"] and r.daten["eingerichtet"] and set_cookie(r) is not None
    api.csrf = r.daten["csrf_token"]
    assert not datei.exists()
    api.get("/api/konten", erwartet=200)
    assert anmeldung().ist_eingerichtet(c)
    r = api.post("/api/anmeldung/einrichten", json={"einrichtungscode": code, "passwort": PASSWORT}, erwartet=409)
    assert fehlercode(r) == "bereits_eingerichtet"
    anmelden(zweiter_client(api), PASSWORT)


def test_einrichtungscode_bremse(tmp_path):
    c = m7_config(tmp_path, passwort=None, anmeldung_fehlversuche=2, anmeldung_sperre_sekunden=60)
    api = Api(c)
    code = einrichtungsdatei(c).read_text(encoding="ascii").strip()
    for _ in range(2):
        api.post("/api/anmeldung/einrichten", json={"einrichtungscode": "0" * 32, "passwort": PASSWORT}, erwartet=403)
    api.post("/api/anmeldung/einrichten", json={"einrichtungscode": code, "passwort": PASSWORT}, erwartet=429)


def test_kein_einrichtungscode_wenn_eingerichtet_oder_aus(tmp_path):
    c = m7_config(tmp_path / "a")
    Api(c)
    assert not einrichtungsdatei(c).exists()
    c2 = neue_config(tmp_path / "b")
    Api(c2)
    assert not einrichtungsdatei(c2).exists()


# ------------------------------------------------------------------ Anmeldeseite
def test_anmeldeseite(tmp_path):
    from tests.app.test_mock_modus import pruefe_mock_hinweis

    api = m7_api(tmp_path, passwort=None)
    html = api.get("/anmelden").text
    for testid in ("anmeldung-formular", "anmeldung-passwort", "anmeldung-einrichtungscode"):
        assert f'data-testid="{testid}"' in html, testid
    assert re.search(r'<input[^>]*type="password"[^>]*data-testid="anmeldung-passwort"|'
                     r'<input[^>]*data-testid="anmeldung-passwort"[^>]*type="password"', html)
    assert "mock-hinweis" not in html
    anmeldung().passwort_setzen(api.config, PASSWORT)
    assert 'data-testid="anmeldung-einrichtungscode"' not in api.get("/anmelden").text
    mock = m7_api(tmp_path / "m", mock_modus=True)
    pruefe_mock_hinweis(mock.get("/anmelden").text)


@pytest.mark.parametrize("weiter", ['<script>alert("x")</script>', '"><img src=x onerror=alert(1)>',
                                    "javascript:alert(1)", "//evil.example.invalid/"])
def test_weiter_nicht_gespiegelt(tmp_path, weiter):
    api = m7_api(tmp_path)
    r = api.client.get("/anmelden", params={"weiter": weiter})
    assert r.status_code == 200
    for teil in ("<script>alert", "onerror=alert", "<img src=x"):
        assert teil not in r.text


@pytest.mark.parametrize("pfad,body", [
    ("/api/anmeldung", {"passwort": "Marker-Passwort-31337", "x": 1}),
    ("/api/anmeldung", {"passwort": "Marker-Passwort-31337" * 300}),
    ("/api/anmeldung/einrichten", {"einrichtungscode": "Marker-Passwort-31337", "passwort": 5}),
    ("/api/anmeldung/einrichten", {"einrichtungscode": "0" * 32, "passwort": "Marker-Passwort-31337", "y": None}),
])
def test_422_ohne_echo(tmp_path, pfad, body):
    api = m7_api(tmp_path, passwort=None if "einrichten" in pfad else PASSWORT)
    r = api.post(pfad, json=body, erwartet=422)
    assert fehlercode(r) == "validierung" and "Marker-Passwort-31337" not in r.text
