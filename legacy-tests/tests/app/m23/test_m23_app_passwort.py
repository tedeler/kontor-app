"""M23: Postfach mit App-Passwort (Gmail ohne Google-Cloud-Projekt) gegen die lokale IMAP-Attrappe; Mail-Abruf
im gesperrten Zustand (geheimnisschutz.md 1, 6; E-229, E-230)."""

from __future__ import annotations

import socket

import pytest

from tests.hilfen import kontor
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m2 import db_dateien
from tests.hilfen.m6 import (
    CLIENT_ID, CLIENT_SECRET, EINS, MAIL_VERGLEICH, REDIRECT, ZWEI, abruf, alles_protokollieren, anmelden,
    geheimnis_setzen, jetzt, mail_erwartung, nachrichten, postfach, postfach_status, zeit,
)
from tests.hilfen.m9 import enthaelt, sicherung
from tests.hilfen.m23 import (
    APP_PASSWORT, APP_ROH, PASSWORT, app_passwort, ausschalten, code, einschalten, eintraege, entsperren,
    m23_echt_api, m23_mock_api, neustart, schluessel_tauschen, schutz,
)
from tests.hilfen.oauth_attrappe import OAuthAttrappe

pytestmark = pytest.mark.kern

ZWEITES = "zwei abcd efgh m23y"
GROSS = "Haushalt.Eins@example.invalid"
FELDER = ("nachricht_id", "empfangen", "absender", "betreff", "text")


@pytest.fixture
def imap(netz_nur_loopback):
    i = ImapAttrappe(passwoerter={EINS: APP_ROH}).starte()
    yield i
    i.stoppe()


@pytest.fixture
def stubs(netz_nur_loopback):
    o = OAuthAttrappe(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT).starte()
    i = ImapAttrappe(pruefe_token=o.access_gueltig, passwoerter={EINS: APP_ROH}).starte()
    yield o, i
    i.stoppe()
    o.stoppe()


def _befehle(i: ImapAttrappe, nr: int = -1) -> list[str]:
    return [b for b in i.sitzungen[nr].befehle if b not in ("CAPABILITY", "ID", "NOOP")]


def _soll(adresse: str, ordner: str = "INBOX") -> list[dict]:
    return [{k: n[k] for k in FELDER} for n in mail_erwartung()["postfaecher"][adresse][ordner]["nachrichten"]]


def _spiegel(api, pid) -> list[dict]:
    return [{k: n[k] for k in FELDER} for n in nachrichten(api, postfach_id=pid)]


# ------------------------------------------------------------------ PUT app-passwort
def test_setzen_prueft_und_speichert(tmp_path, imap):
    api = m23_echt_api(tmp_path, imap)
    p = postfach(api, GROSS)
    assert postfach_status(api, p["id"])["anmeldung"] == "fehlt"
    vorher = jetzt()
    r = app_passwort(api, p["id"])
    n = len(imap.postfaecher[EINS]["INBOX"].nachrichten)
    assert r.daten == {"postfach_id": p["id"], "ordner": "INBOX", "nachrichten_im_ordner": n}
    assert APP_PASSWORT not in r.text and APP_ROH not in r.text
    assert imap.logins == [(GROSS, True)], "Leerraum entfernt, Adresse des Postfachs"
    assert _befehle(imap) == ["LOGIN", "EXAMINE", "LOGOUT"]
    assert imap.verstoesse == [] and not imap.interne_fehler
    s = postfach_status(api, p["id"])
    assert (s["anmeldung"], s["laeuft_ab_am"], s["letzter_fehler"]) == ("angemeldet", None, None)
    assert vorher <= zeit(s["angemeldet_am"]) <= jetzt()
    assert eintraege(api) == {f"mail_passwort:{EINS}": True}
    for name in (f"mail_passwort:{EINS}", "mail_passwort:" + GROSS):
        assert code(api.put(f"/api/geheimnisse/{name}", json={"wert": "SYNTH-X"}, erwartet=404)) == "nicht_gefunden"
        assert code(api.delete(f"/api/geheimnisse/{name}", erwartet=404)) == "nicht_gefunden"
    assert eintraege(api) == {f"mail_passwort:{EINS}": True}


def test_ordner_utf7_und_ersetzen(tmp_path, netz_nur_loopback):
    with ImapAttrappe(passwoerter={ZWEI: APP_ROH}) as i:
        api = m23_echt_api(tmp_path, i)
        p = postfach(api, ZWEI, ordner="Bestellungen/Bücher")
        r = app_passwort(api, p["id"]).daten
        assert r == {"postfach_id": p["id"], "ordner": "Bestellungen/Bücher",
                     "nachrichten_im_ordner": len(i.postfaecher[ZWEI]["Bestellungen/Bücher"].nachrichten)}
        i.passwoerter[ZWEI] = ZWEITES.replace(" ", "")
        app_passwort(api, p["id"], ZWEITES)
        assert [ok for _, ok in i.logins] == [True, True]
        assert abruf(api)["postfaecher"][0]["status"] == "erfolgreich", "erneutes Setzen ersetzt den Wert"
        assert _spiegel(api, p["id"]) == _soll(ZWEI, "Bestellungen/Bücher")


@pytest.mark.parametrize("koerper,geheim", [
    ({}, None), ({"passwort": ""}, None), ({"passwort": "GEHEIM-" + "w" * 250}, "w" * 250),
    ({"passwort": 4711232323}, "4711232323"), ({"passwort": "GEHEIM-APP-FELD", "x": 1}, "GEHEIM-APP-FELD"),
    (["GEHEIM-APP-LISTE"], "GEHEIM-APP-LISTE"),
], ids=["fehlt", "leer", "zu_lang", "zahl", "feld_unbekannt", "kein_objekt"])
def test_validierung_ohne_echo(tmp_path, koerper, geheim, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    p = postfach(api, EINS)
    r = api.put(f"/api/mail/postfaecher/{p['id']}/app-passwort", json=koerper, erwartet=422)
    assert code(r) == "validierung", "Körper vor Mock-Modus"
    if geheim:
        assert geheim not in r.text


def test_pruefreihenfolge_mock(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    p = postfach(api, EINS)
    for pid, wert in ((p["id"], APP_PASSWORT), (p["id"], "  \t "), (9999, APP_PASSWORT)):
        assert code(app_passwort(api, pid, wert, erwartet=409)) == "nur_echtmodus"
    einschalten(api)
    neu = neustart(api)
    assert code(app_passwort(neu, p["id"], erwartet=409)) == "nur_echtmodus", "Mock vor gesperrt"


def test_pruefreihenfolge_echt(tmp_path, imap):
    api = m23_echt_api(tmp_path, imap)
    p = postfach(api, EINS)
    for wert in (" ", "    \t\n "):
        assert code(app_passwort(api, p["id"], wert, erwartet=422)) == "validierung", "nur Leerraum"
    assert code(app_passwort(api, 9999, "   ", erwartet=422)) == "validierung", "Leerraum vor unbekanntem Postfach"
    assert code(app_passwort(api, 9999, erwartet=404)) == "nicht_gefunden"
    einschalten(api)
    b = neustart(api)
    assert code(app_passwort(b, 9999, erwartet=404)) == "nicht_gefunden", "unbekannt vor gesperrt"
    r = app_passwort(b, p["id"], erwartet=409)
    assert code(r) == "geheimnisse_gesperrt" and APP_ROH not in r.text
    assert imap.sitzungen == [], "gesperrt: kein Verbindungstest"
    assert eintraege(b) == {} and postfach_status(b, p["id"])["anmeldung"] == "fehlt"


@pytest.mark.parametrize("fall,soll", [
    ("falsch", "mail_anmeldung_abgelehnt"), ("logindisabled", "mail_fehler"), ("ordner", "mail_ordner_unbekannt"),
    ("abbruch", "mail_verbindung"), ("kein_server", "mail_verbindung"),
])
def test_verbindungstest_fehler(tmp_path, imap, fall, soll):
    port = imap.port
    if fall == "kein_server":
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    api = m23_echt_api(tmp_path, imap, imap_port=port)
    p = postfach(api, EINS, ordner="Gibt/Es/Nicht" if fall == "ordner" else "INBOX")
    imap.login_deaktiviert = fall == "logindisabled"
    imap.abbruch_nach_gruss = fall == "abbruch"
    wert = "falsch passwort xyz" if fall == "falsch" else APP_PASSWORT
    r = app_passwort(api, p["id"], wert, erwartet=422)
    assert code(r) == soll
    for w in (wert, wert.replace(" ", "")):
        assert w not in r.text
    assert eintraege(api) == {}, "nichts gespeichert"
    s = postfach_status(api, p["id"])
    assert (s["anmeldung"], s["angemeldet_am"], s["letzter_fehler"]) == ("fehlt", None, None), "Status unverändert"
    if fall == "logindisabled":
        assert imap.verstoesse == [] and "LOGIN" not in imap.alle_befehle, "kein LOGIN gesendet"
    assert not imap.interne_fehler


# ------------------------------------------------------------------ DELETE, Abmelden, Postfach löschen
def test_entfernen(tmp_path, imap):
    api = m23_echt_api(tmp_path, imap)
    p = postfach(api, EINS)
    api.delete(f"/api/mail/postfaecher/{p['id']}/app-passwort", erwartet=204)
    app_passwort(api, p["id"])
    api.delete(f"/api/mail/postfaecher/{p['id']}/app-passwort", erwartet=204)
    s = postfach_status(api, p["id"])
    assert (s["anmeldung"], s["laeuft_ab_am"]) == ("fehlt", None) and eintraege(api) == {}
    api.delete(f"/api/mail/postfaecher/{p['id']}/app-passwort", erwartet=204)
    assert code(api.delete("/api/mail/postfaecher/9999/app-passwort", erwartet=404)) == "nicht_gefunden"
    x = abruf(api)["postfaecher"][0]
    assert x["status"] == "anmeldung_erforderlich"
    app_passwort(api, p["id"])
    api.delete(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=204)
    assert eintraege(api) == {} and postfach_status(api, p["id"])["anmeldung"] == "fehlt"
    app_passwort(api, p["id"])
    api.delete(f"/api/mail/postfaecher/{p['id']}", erwartet=204)
    assert eintraege(api) == {}, "mail_passwort entfällt mit dem Postfach"


def test_entfernen_im_mock_modus(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path)
    p = postfach(api, EINS)
    api.delete(f"/api/mail/postfaecher/{p['id']}/app-passwort", erwartet=204)
    assert code(api.delete("/api/mail/postfaecher/9999/app-passwort", erwartet=404)) == "nicht_gefunden"


def test_oauth_token_und_vorrang(tmp_path, stubs):
    o, i = stubs
    api = m23_echt_api(tmp_path, i, oauth=o)
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    p = postfach(api, EINS)
    anmelden(api, o, p["id"])
    assert f"mail_token:{EINS}" in eintraege(api)
    app_passwort(api, p["id"])
    assert set(eintraege(api)) == {"oauth_client_secret", f"mail_passwort:{EINS}"}, "Token gelöscht"
    s = postfach_status(api, p["id"])
    assert (s["anmeldung"], s["laeuft_ab_am"]) == ("angemeldet", None)
    anmelden(api, o, p["id"])
    assert set(eintraege(api)) == {"oauth_client_secret", f"mail_passwort:{EINS}", f"mail_token:{EINS}"}
    xoauth = len(i.anmeldungen)
    assert abruf(api)["postfaecher"][0]["status"] == "erfolgreich"
    assert len(i.anmeldungen) == xoauth and i.logins[-1] == (EINS, True), "App-Passwort hat Vorrang"
    api.delete(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=204)
    assert set(eintraege(api)) == {"oauth_client_secret", f"mail_token:{EINS}"}, "Abmelden entfernt nur das Passwort"
    assert i.verstoesse == []


# ------------------------------------------------------------------ Abruf
def test_abruf_mit_login_parallel_zu_xoauth2(tmp_path, stubs):
    o, i = stubs
    api = m23_echt_api(tmp_path, i, oauth=o)
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    p1 = postfach(api, EINS)
    p2 = postfach(api, ZWEI, ordner="Bestellungen/Bücher")
    app_passwort(api, p1["id"])
    anmelden(api, o, p2["id"])
    vorher = len(i.sitzungen)
    i.parallel(2)
    e = abruf(api)
    assert [x["status"] for x in e["postfaecher"]] == ["erfolgreich", "erfolgreich"], e
    assert _spiegel(api, p1["id"]) == _soll(EINS) and _spiegel(api, p2["id"]) == _soll(ZWEI, "Bestellungen/Bücher")
    neu = i.sitzungen[vorher:]
    login = [s for s in neu if "LOGIN" in s.befehle]
    assert len(neu) == 2 and len(login) == 1
    befehle = [b for b in login[0].befehle if b not in ("CAPABILITY", "ID", "NOOP")]
    assert befehle[:2] == ["LOGIN", "EXAMINE"] and "UID FETCH" in befehle and befehle[-1] == "LOGOUT"
    assert not any(b.startswith("AUTHENTICATE") for b in login[0].befehle)
    assert i.verstoesse == [] and not i.interne_fehler


def test_abruf_abgelehnt_und_unlesbar(tmp_path, imap):
    api = m23_echt_api(tmp_path, imap)
    p = postfach(api, EINS)
    app_passwort(api, p["id"])
    imap.passwoerter[EINS] = "anderes"
    x = abruf(api)["postfaecher"][0]
    assert (x["status"], x["fehler"]["code"]) == ("fehlgeschlagen", "mail_anmeldung_abgelehnt")
    assert postfach_status(api, p["id"])["letzter_fehler"]["code"] == "mail_anmeldung_abgelehnt"
    imap.passwoerter[EINS] = APP_ROH
    schluessel_tauschen(api)
    b = neustart(api)
    logins = len(imap.logins)
    x = abruf(b)["postfaecher"][0]
    assert x["status"] != "erfolgreich" and len(imap.logins) == logins, "nicht lesbar: keine Anmeldung"
    fehler = x["fehler"] or postfach_status(b, p["id"])["letzter_fehler"]
    assert fehler is None or fehler["code"] == "mail_anmeldung_fehlt"
    assert x["fehler"] is None or x["fehler"]["code"] == "mail_anmeldung_fehlt"


def test_geschuetztes_app_passwort(tmp_path, imap):
    api = m23_echt_api(tmp_path, imap)
    p = postfach(api, EINS)
    einschalten(api)
    app_passwort(api, p["id"])
    assert schutz(api)["geschuetzt"] == 1
    b = neustart(api)
    assert eintraege(b) == {f"mail_passwort:{EINS}": False}
    sitzungen = len(imap.sitzungen)
    assert code(b.post("/api/mail/abruf", erwartet=409)) == "geheimnisse_gesperrt"
    assert len(imap.sitzungen) == sitzungen
    entsperren(b)
    assert abruf(b)["postfaecher"][0]["status"] == "erfolgreich"
    c = neustart(b)
    ausschalten(c)
    d = neustart(c)
    assert schutz(d)["aktiv"] is False
    assert abruf(d)["postfaecher"][0]["status"] == "erfolgreich", "Wert erhalten, nach Neustart sofort lesbar"


# ------------------------------------------------------------------ Mail-Abruf gesperrt (1)
def test_abruf_gesperrt_auch_im_mock(tmp_path, netz_gesperrt):
    api = m23_mock_api(tmp_path, daten=MAIL_VERGLEICH, mail_intervall_minuten=60, mail_erstabruf_tage=365)
    p = postfach(api, EINS)
    einschalten(api)
    b = neustart(api)
    assert code(b.post("/api/mail/abruf", erwartet=409)) == "geheimnisse_gesperrt"
    planer = kontor.modul("kontor.sync")
    planer.planer_takt(b.app)
    s = postfach_status(b, p["id"])
    assert (s["letzter_abruf_am"], s["letzter_fehler"], s["nachrichten"]) == (None, None, 0), "Planer ruft nicht ab"
    entsperren(b)
    planer.planer_takt(b.app)
    assert postfach_status(b, p["id"])["letzter_abruf_am"] is not None
    assert abruf(b)["postfaecher"][0]["status"] == "erfolgreich"


# ------------------------------------------------------------------ nirgends
def test_app_passwort_nirgends(tmp_path, imap, caplog, capfd):
    alles_protokollieren(caplog)
    api = m23_echt_api(tmp_path, imap)
    p = postfach(api, EINS)
    texte = [app_passwort(api, p["id"]).text, app_passwort(api, p["id"], "falsch passwort xyz", erwartet=422).text]
    abruf(api)
    einschalten(api)
    app_passwort(api, p["id"])
    abruf(api)
    daten = sicherung(api)
    for pfad in ("/api/geheimnisse", "/api/mail/postfaecher", f"/api/mail/postfaecher/{p['id']}/status",
                 "/api/benachrichtigungen", "/api/aenderungen", "/api/status"):
        texte.append(api.get(pfad, erwartet=200).text)
    raus, err = capfd.readouterr()
    texte += [caplog.text, raus, err, repr(api.config)] + [r.getMessage() for r in caplog.records]
    texte += [repr(r.args) for r in caplog.records]
    for w in (APP_PASSWORT, APP_ROH, "falschpasswortxyz", PASSWORT):
        assert all(w not in t for t in texte), w
        assert not enthaelt(daten, w)
        for d in db_dateien(api):
            for k in ("utf-8", "utf-16-le"):
                assert w.encode(k) not in d.read_bytes(), (w, d.name)
