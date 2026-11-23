"""M6: OAuth2-Anmeldung, Tokens, Ablauf im Testmodus und Abruf im Echtmodus (mail.md 4–6; K 13, T 16, E-120)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import logging
import time

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import fehlercode
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m6 import (
    CLIENT_SECRET, EINS, REDIRECT, ZWEI, abruf, anmelden, benachrichtigungen, echt_api, geheimnis_setzen, geheimnisse,
    geheimnisse_nirgends, jetzt, mail_erwartung, mail_felder, nachrichten, ntfy_felder, postfach, postfach_status,
    url_parameter, zeit,
)
from tests.hilfen.ntfy_attrappe import NtfyAttrappe
from tests.hilfen.oauth_attrappe import SCOPE, OAuthAttrappe
from tests.hilfen.m6 import CLIENT_ID


@pytest.fixture
def stubs(netz_nur_loopback):
    o = OAuthAttrappe(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT).starte()
    i = ImapAttrappe(pruefe_token=o.access_gueltig).starte()
    yield o, i
    i.stoppe()
    o.stoppe()


def _api(tmp_path, o, i, secret=True, **extra):
    api = echt_api(tmp_path, **mail_felder(i, o, mail_erstabruf_tage=3650, **extra))
    if secret:
        geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    return api


def _takt(api):
    return kontor.modul("kontor.sync").planer_takt(api.app)


def _arten(api, pid):
    return [b["schluessel"] for b in benachrichtigungen(api) if b["schluessel"].startswith("mail_")
            and f":{pid}:" in b["schluessel"]]


@pytest.mark.kern
def test_ohne_client_keine_anmeldung(tmp_path, stubs):
    o, i = stubs
    a = _api(tmp_path / "a", o, i, secret=False)
    p = postfach(a, EINS)
    assert fehlercode(a.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=409)) == "oauth_client_fehlt"
    b = echt_api(tmp_path / "b", **{**mail_felder(i, o), "oauth_client_id": None})
    geheimnis_setzen(b, "oauth_client_secret", CLIENT_SECRET)
    q = postfach(b, EINS)
    assert fehlercode(b.post(f"/api/mail/postfaecher/{q['id']}/anmeldung", erwartet=409)) == "oauth_client_fehlt"
    assert fehlercode(b.post("/api/mail/postfaecher/999/anmeldung", erwartet=404)) == "nicht_gefunden"


@pytest.mark.kern
def test_autorisierungs_url_mit_pkce(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    vorher = jetzt()
    s = api.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=200).daten
    assert s["autorisierung_url"].startswith(o.autorisierung_url + "?")
    q = url_parameter(s["autorisierung_url"])
    assert {k: q[k] for k in ("response_type", "client_id", "redirect_uri", "scope", "code_challenge_method",
                              "access_type", "prompt", "login_hint")} == {
        "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT, "scope": SCOPE,
        "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent", "login_hint": EINS}
    assert len(q["state"]) >= 22 and len(q["code_challenge"]) == 43 and "=" not in q["code_challenge"]
    assert vorher + dt.timedelta(minutes=10) <= zeit(s["gueltig_bis"]) <= jetzt() + dt.timedelta(minutes=10)
    s2 = api.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=200).daten
    assert url_parameter(s2["autorisierung_url"])["state"] != q["state"]


@pytest.mark.kern
def test_anmeldung_ueber_antwort_url(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    vorher = jetzt()
    s = anmelden(api, o, p["id"])
    assert s["anmeldung"] == "angemeldet" and s["anmeldung_nr"] == 1
    assert vorher <= zeit(s["angemeldet_am"]) <= jetzt()
    assert zeit(s["laeuft_ab_am"]) == zeit(s["angemeldet_am"]) + dt.timedelta(hours=168), "Vorgabe sieben Tage"
    (tausch,) = o.token_anfragen
    start = o.genehmigungen[-1].parameter
    assert tausch["grant_type"] == "authorization_code" and tausch["redirect_uri"] == REDIRECT
    assert (tausch["client_id"], tausch["client_secret"]) == (CLIENT_ID, CLIENT_SECRET)
    assert base64.urlsafe_b64encode(hashlib.sha256(tausch["code_verifier"].encode()).digest()).rstrip(
        b"=").decode() == start["code_challenge"]
    assert [e["name"] for e in geheimnisse(api)["eintraege"]] == [f"mail_token:{EINS.casefold()}",
                                                                  "oauth_client_secret"]


@pytest.mark.kern
def test_anmeldung_ueber_rueckruf(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, ZWEI)
    s = api.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=200).daten
    ziel = o.genehmige(s["autorisierung_url"])
    pfad = "/oauth2/rueckruf?" + ziel.split("?", 1)[1]
    r = api.client.get(pfad)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert postfach_status(api, p["id"])["anmeldung"] == "angemeldet"
    r2 = api.client.get(pfad)
    assert r2.status_code == 400, "jeder state höchstens einmal"


@pytest.mark.kern
@pytest.mark.parametrize("fall,status,code", [
    ("state_unbekannt", 422, "oauth_zustand_ungueltig"), ("abgelehnt", 422, "oauth_abgelehnt"),
    ("ohne_code", 422, "oauth_zustand_ungueltig"), ("scope", 422, "oauth_scope_fehlt"),
    ("ohne_refresh", 422, "oauth_kein_refresh_token"), ("server", 409, "oauth_fehler"),
    ("falsches_secret", 409, "oauth_fehler")])
def test_anmeldung_fehler(tmp_path, stubs, fall, status, code):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    s = api.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=200).daten
    if fall == "abgelehnt":
        ziel = o.genehmige(s["autorisierung_url"], ablehnen=True)
    else:
        ziel = o.genehmige(s["autorisierung_url"])
    if fall == "state_unbekannt":
        ziel = ziel.replace("state=", "state=X")
    elif fall == "ohne_code":
        q = url_parameter(ziel)
        ziel = f"{REDIRECT}?state={q['state']}"
    elif fall == "scope":
        o.scope_antwort = "https://www.googleapis.com/auth/gmail.readonly"
    elif fall == "ohne_refresh":
        o.ohne_refresh_token = True
    elif fall == "server":
        o.fehlerstatus = 500
    elif fall == "falsches_secret":
        geheimnis_setzen(api, "oauth_client_secret", "SYNTH-FALSCHES-SECRET")
    r = api.post("/api/mail/anmeldung/abschluss", json={"antwort_url": ziel}, erwartet=status)
    assert fehlercode(r) == code
    assert postfach_status(api, p["id"])["anmeldung"] == "fehlt"
    assert fehlercode(api.post("/api/mail/anmeldung/abschluss", json={"antwort_url": ziel}, erwartet=422)) == \
        "oauth_zustand_ungueltig", "die offene Anmeldung ist verbraucht"


@pytest.mark.kern
def test_abruf_beider_postfaecher_parallel(tmp_path, stubs):
    o, i = stubs
    erw = mail_erwartung()
    api = _api(tmp_path, o, i)
    p1 = postfach(api, EINS)
    p2 = postfach(api, ZWEI, ordner="Bestellungen/Bücher")
    anmelden(api, o, p1["id"])
    anmelden(api, o, p2["id"])
    i.parallel(2)
    e = abruf(api)
    assert [x["status"] for x in e["postfaecher"]] == ["erfolgreich", "erfolgreich"], e
    for p, ordner in ((p1, "INBOX"), (p2, "Bestellungen/Bücher")):
        soll = [{k: n[k] for k in ("nachricht_id", "empfangen", "absender", "betreff", "text")}
                for n in erw["postfaecher"][p["adresse"]][ordner]["nachrichten"]]
        ist = [{k: n[k] for k in ("nachricht_id", "empfangen", "absender", "betreff", "text")}
               for n in nachrichten(api, postfach_id=p["id"])]
        assert ist == soll
    assert i.verstoesse == [] and not i.interne_fehler


@pytest.mark.kern
def test_nicht_angemeldet_ohne_verbindung(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    x = abruf(api)["postfaecher"][0]
    assert (x["status"], x["nachrichten_gesamt"], x["fehler"]) == ("anmeldung_erforderlich", 0, None)
    assert i.sitzungen == [] and benachrichtigungen(api) == []
    assert postfach_status(api, p["id"])["letzter_abruf_am"] is None


@pytest.mark.kern
def test_ein_postfach_scheitert_das_andere_nicht(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p1 = postfach(api, EINS, ordner="Gibt/Es/Nicht")
    p2 = postfach(api, ZWEI)
    anmelden(api, o, p1["id"])
    anmelden(api, o, p2["id"])
    e = abruf(api)["postfaecher"]
    assert (e[0]["status"], e[0]["fehler"]["code"]) == ("fehlgeschlagen", "mail_ordner_unbekannt")
    assert e[1]["status"] == "erfolgreich" and e[1]["nachrichten_neu"] > 0
    assert _arten(api, p1["id"]) == [f"mail_fehler:{p1['id']}:mail_ordner_unbekannt"]


@pytest.mark.kern
def test_access_token_wird_erneuert(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    anmelden(api, o, p["id"])
    abruf(api)
    abruf(api)
    assert [t["grant_type"] for t in o.token_anfragen] == ["authorization_code"], "gültiges Access-Token weiter nutzen"
    o.access_lebensdauer = 30
    o.entwerte_access_tokens(EINS)
    assert abruf(api)["postfaecher"][0]["status"] == "erfolgreich", "IMAP lehnt ab → erneuern → Erfolg"
    assert [t["grant_type"] for t in o.token_anfragen][-1] == "refresh_token"
    n = len(o.token_anfragen)
    abruf(api)
    assert len(o.token_anfragen) == n + 1, "Access-Token mit weniger als 60 s Restlaufzeit wird erneuert"


@pytest.mark.kern
def test_vorwarnung_einmal_je_anmeldung(tmp_path, stubs):
    o, i = stubs
    o.refresh_lebensdauer = 3600
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    s = anmelden(api, o, p["id"])
    assert zeit(s["laeuft_ab_am"]) == zeit(s["angemeldet_am"]) + dt.timedelta(seconds=3600)
    for _ in range(3):
        _takt(api)
        for b in benachrichtigungen(api, gelesen=False):
            api.post(f"/api/benachrichtigungen/{b['id']}/gelesen", erwartet=200)
    assert _arten(api, p["id"]) == [f"mail_token_laeuft_ab:{p['id']}:1"], "einmal je Anmeldung, auch nach Lesen"
    assert abruf(api)["postfaecher"][0]["status"] == "erfolgreich"


@pytest.mark.kern
def test_vorwarnung_ueber_konfiguration(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i, oauth_refresh_gueltig_stunden=168, oauth_vorwarnung_stunden=168)
    p = postfach(api, EINS)
    anmelden(api, o, p["id"])
    _takt(api)
    assert _arten(api, p["id"]) == [f"mail_token_laeuft_ab:{p['id']}:1"]
    ohne = _api(tmp_path / "b", o, i, oauth_refresh_gueltig_stunden=0, oauth_vorwarnung_stunden=8760)
    q = postfach(ohne, ZWEI)
    assert anmelden(ohne, o, q["id"])["laeuft_ab_am"] is None
    _takt(ohne)
    assert _arten(ohne, q["id"]) == []


@pytest.mark.kern
def test_proaktiver_ablauf_ohne_anfrage(tmp_path, stubs):
    o, i = stubs
    with NtfyAttrappe() as n:
        o.refresh_lebensdauer = 2
        api = _api(tmp_path, o, i, **ntfy_felder(n))
        p1 = postfach(api, EINS)
        anmelden(api, o, p1["id"])
        o.refresh_lebensdauer = None
        p2 = postfach(api, ZWEI)
        anmelden(api, o, p2["id"])
        time.sleep(2.2)
        anfragen = len(o.token_anfragen)
        _takt(api)
        assert len(o.token_anfragen) == anfragen, "Ablauf ohne Anfrage beim Anbieter erkannt"
        s = postfach_status(api, p1["id"])
        assert (s["anmeldung"], s["laeuft_ab_am"]) == ("abgelaufen", None)
        assert f"mail_token_abgelaufen:{p1['id']}:1" in _arten(api, p1["id"])
        sitzungen = len(i.sitzungen)
        e = abruf(api)["postfaecher"]
        assert e[0]["status"] == "anmeldung_erforderlich" and e[1]["status"] == "erfolgreich"
        assert len(i.sitzungen) == sitzungen + 1, "nur das angemeldete Postfach verbindet sich"
        _takt(api)
        abruf(api)
        assert _arten(api, p1["id"]).count(f"mail_token_abgelaufen:{p1['id']}:1") == 1
        assert [k["tags"] for k in n.angenommen].count(["mail_token_abgelaufen"]) == 1
        assert [k for k in n.angenommen if k["tags"] == ["mail_token_abgelaufen"]][0]["priority"] == 4
        assert not any(e["name"] == f"mail_token:{EINS.casefold()}" for e in geheimnisse(api)["eintraege"])
        # erneute Anmeldung: neuer Zyklus, alte Meldungen gelesen
        s = anmelden(api, o, p1["id"])
        assert (s["anmeldung"], s["anmeldung_nr"]) == ("angemeldet", 2)
        assert all(b["gelesen"] for b in benachrichtigungen(api) if f":{p1['id']}:" in b["schluessel"])
        assert abruf(api)["postfaecher"][0]["status"] == "erfolgreich"


@pytest.mark.kern
@pytest.mark.parametrize("lebensdauer,art", [(7200, "mail_token_widerrufen"), (1800, "mail_token_abgelaufen")])
def test_reaktiv_invalid_grant(tmp_path, stubs, lebensdauer, art):
    o, i = stubs
    o.refresh_lebensdauer = lebensdauer
    o.access_lebensdauer = 30
    api = _api(tmp_path, o, i, oauth_vorwarnung_stunden=0)
    p = postfach(api, EINS)
    anmelden(api, o, p["id"])
    o.lasse_ablaufen(EINS)
    x = abruf(api)["postfaecher"][0]
    assert (x["status"], x["fehler"]["code"]) == ("fehlgeschlagen", art)
    assert postfach_status(api, p["id"])["anmeldung"] == art.rsplit("_", 1)[1]
    assert _arten(api, p["id"]) == [f"{art}:{p['id']}:1"]
    assert abruf(api)["postfaecher"][0]["status"] == "anmeldung_erforderlich"
    assert _arten(api, p["id"]) == [f"{art}:{p['id']}:1"]


@pytest.mark.kern
def test_abmelden_widerruft(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    anmelden(api, o, p["id"])
    refresh = next(t for t, r in o.refresh_tokens.items() if r.adresse == EINS)
    api.delete(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=204)
    assert o.widerrufe == [refresh]
    assert postfach_status(api, p["id"])["anmeldung"] == "fehlt"
    assert [e["name"] for e in geheimnisse(api)["eintraege"]] == ["oauth_client_secret"]
    api.delete(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=204)
    assert o.widerrufe == [refresh]


@pytest.mark.kern
def test_postfach_loeschen_entfernt_tokens(tmp_path, stubs):
    o, i = stubs
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    anmelden(api, o, p["id"])
    api.delete(f"/api/mail/postfaecher/{p['id']}", erwartet=204)
    assert [e["name"] for e in geheimnisse(api)["eintraege"]] == ["oauth_client_secret"]


@pytest.mark.kern
def test_tokens_nirgends_im_klartext(tmp_path, stubs, caplog, capfd):
    o, i = stubs
    caplog.set_level(logging.DEBUG)
    o.access_lebensdauer = 30
    api = _api(tmp_path, o, i)
    p = postfach(api, EINS)
    texte = [api.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=200).text]
    s = api.post(f"/api/mail/postfaecher/{p['id']}/anmeldung", erwartet=200).daten
    ziel = o.genehmige(s["autorisierung_url"])
    texte.append(api.post("/api/mail/anmeldung/abschluss", json={"antwort_url": ziel}, erwartet=200).text)
    abruf(api)
    abruf(api)
    werte = list(o.refresh_tokens) + list(o.access_tokens) + [url_parameter(ziel)["code"], CLIENT_SECRET,
                                                              o.token_anfragen[0]["code_verifier"]]
    geheimnisse_nirgends(api, werte, texte=texte, caplog=caplog, capfd=capfd)
