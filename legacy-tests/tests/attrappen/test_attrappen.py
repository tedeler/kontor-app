"""Selbsttests der lokalen Attrappen (ohne App): Sie sprechen das jeweilige Protokoll so, wie es die
echten Bibliotheken erwarten (python-fints, imaplib, HTTP). Nur 127.0.0.1, synthetische Daten (E-028).

Diese Tests zeigen der Implementierung, dass die Attrappen ein verlässlicher Gegenüber sind; Fehler hier
sind Fehler der Tests, nicht der Anwendung.
"""

from __future__ import annotations

import base64
import re
import datetime as dt
import hashlib
import imaplib
import json
import secrets
import ssl
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from tests.hilfen import m6_orakel as orakel
from tests.hilfen.fints_attrappe import LESEND, FintsAttrappe, _camt, _mt940, camt_format
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.ntfy_attrappe import NtfyAttrappe
from tests.hilfen.oauth_attrappe import SCOPE, OAuthAttrappe
from tests.hilfen.pfade import FIXTURES
from tests.hilfen.tls import erzeuge_zertifikat

fints_client = pytest.importorskip("fints.client", reason="python-fints fehlt (requirements-tests.txt)")
UTC = dt.timezone.utc
VON, BIS = dt.date(2023, 12, 1), dt.date(2024, 7, 31)


def _json(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bank():
    return _json("m6/fints_bank.json"), _json("m6/fints_bank.erwartung.json")


def _client(url, daten, pin=None, from_data=None):
    return fints_client.FinTS3PinTanClient(daten["blz"], daten["benutzer"], pin or daten["pin"], url,
                                           product_id="KONTOR-TEST-PRODUKT", from_data=from_data)


def _iban(sepa) -> str:
    return sepa.iban


# ---------------------------------------------------------------- FinTS
@pytest.mark.parametrize("profil", ["camt", "mt940"])
def test_fints_mit_python_fints(bank, profil):
    daten, erw = bank
    giro = next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")
    with FintsAttrappe(daten, profil=profil, seitengroesse=15) as a:
        c = _client(a.url, daten)
        with c:
            konten = c.get_sepa_accounts()
            info = c.get_information()
            konto = next(k for k in konten if k.iban == giro)
            r = (c.get_transactions_xml if profil == "camt" else c.get_transactions)(konto, VON, BIS)
            assert isinstance(r, fints_client.NeedTANResponse)
            assert r.challenge == daten["challenge"]
            mime, bild = r.challenge_matrix
            assert mime == "image/png" and bild == base64.b64decode(daten["qr_png"])
            codes = []
            c.add_response_callback(lambda seg, resp: codes.append(resp.code))
            falsch = c.send_tan(r, "000000")
            assert "9941" in codes and (falsch == ([], []) or falsch == [])
            ok = c.send_tan(r, daten["tan"])
            if profil == "camt":
                ist = orakel.camt_umsaetze(giro, ok[0] + [x for x in ok[1] if x])
            else:
                ist = [u for u in ok]
            # zweiter Abruf ohne TAN (Freigabe), Aufsetzpunkte werden verfolgt
            r2 = (c.get_transactions_xml if profil == "camt" else c.get_transactions)(konto, VON, BIS)
            assert not isinstance(r2, fints_client.NeedTANResponse)
    soll = orakel.erwartete_umsaetze(erw, profil, giro, VON, BIS)
    if profil == "camt":
        assert orakel.sortiert(ist) == soll
    else:
        assert len(ist) == len(soll)
        assert sorted(abs(int(t.data["amount"].amount * 100)) for t in ist) == sorted(abs(u["betrag"]) for u in soll)
    assert {k.iban for k in konten} >= {k["iban"] for k in erw["konten"]}
    assert {x["iban"]: x["type"] for x in info["accounts"]}[giro] == 1
    assert a.segmentarten <= LESEND and "HKCCS" not in a.segmentarten
    assert not a.interne_fehler
    assert {x.produkt_id for x in a.anfragen if x.produkt_id} == {"KONTOR-TEST-PRODUKT"}


def test_fints_mt940_zusammenbau_gleich_wahrheit(bank):
    daten, erw = bank
    for konto in daten["konten"]:
        liste = [u for u in daten["umsaetze"] if u["iban"] == konto["iban"] and u["mt940"]]
        text = _mt940(konto, liste, daten["blz"]).decode("iso-8859-1")
        ist = orakel.mt940_umsaetze(konto["iban"], text)
        soll = [w["mt940"] for w in erw["umsaetze"] if w["iban"] == konto["iban"] and w["mt940"]]
        assert ist == soll


def test_fints_camt_zusammenbau_gleich_wahrheit(bank):
    daten, erw = bank
    for konto in daten["konten"]:
        liste = [u for u in daten["umsaetze"] if u["iban"] == konto["iban"]]
        ist = orakel.camt_umsaetze(konto["iban"], [_camt(konto, liste, gebucht=True)])
        soll = [w["camt"] for w in erw["umsaetze"] if w["iban"] == konto["iban"] and w["camt"]]
        assert ist == soll


# ---------------------------------------------------------------- FinTS: Betriebsarten ab M29 (fints.md 6, E-263)
def test_fints_m29_tan_bei_der_anmeldung(bank):
    daten, erw = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        c = _client(a.url, daten)
        codes = []
        c.add_response_callback(lambda seg, resp: codes.append(resp.code))
        with c:
            r = c.init_tan_response
            assert isinstance(r, fints_client.NeedTANResponse) and not r.decoupled
            assert r.challenge == daten["challenge"]
            assert r.challenge_matrix == ("image/png", base64.b64decode(daten["qr_png"]))
            c.send_tan(r, "000000")
            assert "9941" in codes, "falsche TAN: Auftrag bleibt offen"
            c.send_tan(r, daten["tan"])
            konten = c.get_sepa_accounts()
            assert {k.iban for k in konten} >= {k["iban"] for k in erw["konten"]}
        assert a.anmeldungs_tans == 1 and a.offene_auftraege == 0
        # zweiter Dialog: wieder eine TAN ("immer")
        c2 = _client(a.url, daten)
        with c2:
            assert isinstance(c2.init_tan_response, fints_client.NeedTANResponse)
        assert a.anmeldungs_tans == 2
    assert not a.interne_fehler and a.segmentarten <= LESEND


def test_fints_m29_anmeldung_einmal_und_entkoppelt(bank):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "einmal"
        c = _client(a.url, daten)
        with c:
            c.send_tan(c.init_tan_response, daten["tan"])
            assert c.get_sepa_accounts()
        c2 = _client(a.url, daten)
        with c2:
            assert c2.init_tan_response is None, "nach der ersten richtigen TAN keine weitere"
            assert c2.get_sepa_accounts()
    with FintsAttrappe(daten, tan_pflicht="nie") as b:
        b.tan_anmeldung, b.anmeldung_entkoppelt = "immer", True
        c = _client(b.url, daten)
        with c:
            assert c.init_tan_response.decoupled is True
    assert not a.interne_fehler and not b.interne_fehler


def test_fints_m29_tan_verfahren_ohne_tan(bank):
    """Der Ein-Schritt-/Synchronisierungsdialog braucht auch bei TAN zur Anmeldung keine TAN."""
    daten, _ = bank
    zusatz = {"funktion": "921", "name": "pushTAN synthetisch", "technische_id": "PUSH"}
    with FintsAttrappe(daten) as a:
        a.tan_anmeldung = "immer"
        a.verfahren_zusatz = [zusatz]
        a.erlaubte_verfahren = ["913", "921"]
        c = _client(a.url, daten)
        c.fetch_tan_mechanisms()
        assert {k: v.name for k, v in c.get_tan_mechanisms().items()} == {"913": daten["tan_verfahren"]["name"],
                                                                         "921": "pushTAN synthetisch"}
        assert a.anmeldungs_tans == 0 and not a.interne_fehler
    with FintsAttrappe(daten) as b:
        b.verfahren_zusatz = [zusatz]
        b.erlaubte_verfahren = None
        c = _client(b.url, daten)
        c.fetch_tan_mechanisms()
        assert c.allowed_security_functions == [], "kein 3920"
        assert {str(p.security_function) for s in c.bpd.find_segments("HITANS")
                for p in s.parameter.twostep_parameters} == {"913", "921"}
        assert not b.interne_fehler


def test_fints_m29_camt_formate(bank):
    daten, erw = bank
    giro = next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")
    with FintsAttrappe(daten, profil="beide", tan_pflicht="nie") as a:
        a.camt_formate = [camt_format(2), camt_format(4)]
        c = _client(a.url, daten)
        with c:
            konto = next(k for k in c.get_sepa_accounts() if k.iban == giro)
            gebucht, vorgemerkt = c.get_transactions_xml(konto, VON, BIS, supported_camt_messages=[camt_format(4)])
            assert all(camt_format(4).encode() in x for x in gebucht) and gebucht
            ist = orakel.camt_umsaetze(giro, gebucht + [x for x in vorgemerkt if x])
            assert orakel.sortiert(ist) == orakel.erwartete_umsaetze(erw, "camt", giro, VON, BIS)
            assert c.get_transactions(konto, VON, BIS), "Profil beide: HKKAZ wird ebenfalls bedient"
        assert a.camt_angefordert[0] == [camt_format(4)]
        assert a.camt_kontoverbindungen[0] == {"iban": True, "bic": True, "kontonummer": False, "unterkonto": False,
                                               "bankleitzahl": False}
        assert {"HKCAZ", "HKKAZ"} <= a.segmentarten and not a.interne_fehler


@pytest.mark.parametrize("form", ["zone", "z", "zeitpunkt", "zeitpunkt_dt"])
def test_fints_m29_datumsformen(bank, form):
    daten, erw = bank
    giro = next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.datum_form = form
        c = _client(a.url, daten)
        with c:
            konto = next(k for k in c.get_sepa_accounts() if k.iban == giro)
            gebucht, _ = c.get_transactions_xml(konto, VON, BIS)
    text = b"".join(gebucht).decode("utf-8")
    assert not re.search(r"<Dt>\d{4}-\d{2}-\d{2}</Dt>", text), "kein Datum in der Grundform"
    muster = {"zone": r"<Dt>\d{4}-\d{2}-\d{2}\+02:00</Dt>", "z": r"<Dt>\d{4}-\d{2}-\d{2}Z</Dt>",
              "zeitpunkt": r"<DtTm>\d{4}-\d{2}-\d{2}T10:11:12\+02:00</DtTm>",
              "zeitpunkt_dt": r"<Dt>\d{4}-\d{2}-\d{2}T10:11:12\+02:00</Dt>"}[form]
    assert re.search(muster, text) and not a.interne_fehler


def test_fints_m29_unlesbare_werte_und_rueckmeldungstext(bank):
    daten, erw = bank
    giro = next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.datum_kaputt, a.betrag_kaputt = "03.06.2024", "12,5a"
        a.rueckmeldung_zusatz = "Kennung 4711998877"
        c = _client(a.url, daten)
        texte = []
        c.add_response_callback(lambda seg, resp: texte.append(resp.text))
        with c:
            konto = next(k for k in c.get_sepa_accounts() if k.iban == giro)
            gebucht, _ = c.get_transactions_xml(konto, VON, BIS)
    text = b"".join(gebucht).decode("utf-8")
    assert text.count("<Dt>03.06.2024</Dt>") == 1 and text.count(">12,5a</Amt>") == 1, "nur der erste Eintrag"
    assert any("4711998877" in x for x in texte) and not a.interne_fehler


@pytest.mark.parametrize("art", ["upd_ohne_kontoart", "upd_ohne_iban", "upd_ohne_konten"])
def test_fints_m29_benutzerparameter(bank, art):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        setattr(a, art, True)
        a.hispa_mit_nicht_sepa = a.hispa_ohne_bic = True
        c = _client(a.url, daten)
        with c:
            sepa = c.get_sepa_accounts()
            upd = list(c.upd.find_segments("HIUPD"))
        assert len(c.accounts) == len(daten["konten"]), "auch das Nicht-SEPA-Konto steht in HISPA"
        assert {k.iban for k in sepa} == {k["iban"] for k in daten["konten"] if k.get("sepa", True)}
        assert all(not k.bic for k in sepa)
    if art == "upd_ohne_konten":
        assert upd == []
    else:
        assert len(upd) == len(daten["konten"])
        if art == "upd_ohne_kontoart":
            assert all(u.account_type is None and u.iban for u in upd)
        else:
            assert all(u.iban is None for u in upd)
            assert {str(u.account_information.account_number) for u in upd} == {
                k["kontonummer"].lstrip("0") for k in daten["konten"]}
    assert not a.interne_fehler


def test_fints_m29_benutzerparameter_neue_version_beim_umschalten(bank):
    """W-016 (E-290): Ein Kunde, der die UPD-Version kennt, bekommt nach dem Umschalten neue UPD."""
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        c = _client(a.url, daten)
        with c:
            vorher = len(list(c.upd.find_segments("HIUPD")))
        zustand = c.deconstruct(including_private=True)
        a.upd_ohne_konten = True
        c2 = _client(a.url, daten, from_data=zustand)
        with c2:
            nachher = len(list(c2.upd.find_segments("HIUPD")))
    assert vorher == len(daten["konten"]) and nachher == 0, "die neue Version bringt die geänderten UPD"
    assert not a.interne_fehler


def test_fints_pin_falsch_und_sperre(bank):
    daten, _ = bank
    fehler = pytest.importorskip("fints.exceptions")
    with FintsAttrappe(daten) as a:
        for _ in range(3):
            with pytest.raises(fehler.FinTSClientPINError):
                with _client(a.url, daten, pin="SYNTH-FALSCH-0"):
                    pass
        assert a.gesperrt
        with pytest.raises((fehler.FinTSClientTemporaryAuthError, fehler.FinTSClientPINError)):
            with _client(a.url, daten):
                pass


def test_fints_tan_abgelaufen_und_ohne_pflicht(bank):
    daten, erw = bank
    giro = next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")
    with FintsAttrappe(daten) as a:
        c = _client(a.url, daten)
        with c:
            konto = next(k for k in c.get_sepa_accounts() if k.iban == giro)
            r = c.get_transactions_xml(konto, VON, BIS)
            a.lasse_tan_ablaufen()
            codes = []
            c.add_response_callback(lambda seg, resp: codes.append(resp.code))
            c.send_tan(r, daten["tan"])
            assert "9955" in codes and a.offene_auftraege == 0
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        c = _client(a.url, daten)
        with c:
            konto = next(k for k in c.get_sepa_accounts() if k.iban == giro)
            r = c.get_transactions_xml(konto, VON, BIS)
            assert not isinstance(r, fints_client.NeedTANResponse) and a.tans_empfangen == 0


def test_fints_fehler_iban_und_http(bank):
    daten, erw = bank
    giro = next(k["iban"] for k in erw["konten"] if k["art"] == "girokonto")
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.fehler_iban.add(giro)
        c = _client(a.url, daten)
        codes = []
        c.add_response_callback(lambda seg, resp: codes.append(resp.code))
        with c:
            konto = next(k for k in c.get_sepa_accounts() if k.iban == giro)
            c.get_transactions_xml(konto, VON, BIS)
        assert "9380" in codes
        a.http_status = 503
        with pytest.raises(Exception, match="status code 503"):
            with _client(a.url, daten):
                pass


# ---------------------------------------------------------------- IMAP
@pytest.fixture(scope="module")
def mail():
    return _json("m6/mail.erwartung.json")


def _xoauth2(adresse, token):
    return f"user={adresse}\x01auth=Bearer {token}\x01\x01".encode()


def _abruf(port, adresse, token, ordner="INBOX", seit=dt.datetime(2024, 1, 1, tzinfo=UTC), kontext=None):
    m = imaplib.IMAP4_SSL("127.0.0.1", port, ssl_context=kontext) if kontext else imaplib.IMAP4("127.0.0.1", port)
    try:
        m.authenticate("XOAUTH2", lambda _: _xoauth2(adresse, token))
        typ, daten = m.select(f'"{orakel.utf7_imap(ordner)}"', readonly=True)
        assert typ == "OK"
        uidvalidity = int(m.response("UIDVALIDITY")[1][0])
        typ, treffer = m.uid("SEARCH", None, "SINCE", seit.strftime("%d-%b-%Y"))
        uids = treffer[0].split()
        aus = []
        if uids:
            typ, teile = m.uid("FETCH", b",".join(uids).decode(), "(UID INTERNALDATE BODY.PEEK[])")
            for t in teile:
                if isinstance(t, tuple):
                    kopf = t[0].decode()
                    uid = int(kopf.split("UID ")[1].split()[0])
                    intern = imaplib.Internaldate2tuple(t[0])
                    zeit = dt.datetime(*intern[:6], tzinfo=UTC) if False else dt.datetime.fromtimestamp(
                        __import__("time").mktime(intern), tz=UTC)
                    aus.append(orakel.mail_nachricht(t[1], adresse, zeit, uidvalidity, uid))
        m.logout()
        return aus
    finally:
        try:
            m.shutdown()
        except OSError:
            pass


def test_imap_mit_imaplib(mail):
    adresse = "haushalt.eins@example.invalid"
    with ImapAttrappe(tokens={adresse: "SYNTH-ACCESS-1"}) as a:
        ist = _abruf(a.port, adresse, "SYNTH-ACCESS-1")
        soll = mail["postfaecher"][adresse]["INBOX"]["nachrichten"]
        gesehen, eindeutig = set(), []
        for n in ist:
            if n["nachricht_id"] not in gesehen:
                gesehen.add(n["nachricht_id"])
                eindeutig.append(n)
        eindeutig.sort(key=lambda n: (n["empfangen"], n["nachricht_id"]))
        assert eindeutig == [{k: v for k, v in n.items() if k != "uid"} for n in soll]
        assert not a.verstoesse and not a.interne_fehler
        assert a.alle_befehle[:2] == ["AUTHENTICATE XOAUTH2", "EXAMINE"]


def test_imap_utf7_ordner_und_tls(mail, tmp_path):
    adresse = "haushalt.zwei@example.invalid"
    z = erzeuge_zertifikat(tmp_path)
    kontext = ssl.create_default_context(cafile=str(z.zertifikat))
    with ImapAttrappe(tokens={adresse: "SYNTH-ACCESS-2"}, tls=z) as a:
        ist = _abruf(a.port, adresse, "SYNTH-ACCESS-2", ordner="Bestellungen/Bücher", kontext=kontext)
        assert len(ist) == len(mail["postfaecher"][adresse]["Bestellungen/Bücher"]["nachrichten"])
        with pytest.raises(ssl.SSLError):
            imaplib.IMAP4_SSL("127.0.0.1", a.port, ssl_context=ssl.create_default_context())


def test_imap_verbote_und_falsches_token():
    adresse = "haushalt.eins@example.invalid"
    with ImapAttrappe(tokens={adresse: "SYNTH-ACCESS-1"}) as a:
        m = imaplib.IMAP4("127.0.0.1", a.port)
        with pytest.raises(imaplib.IMAP4.error):
            m.login(adresse, "SYNTH-PASSWORT")
        with pytest.raises(imaplib.IMAP4.error):
            m.authenticate("XOAUTH2", lambda ch: b"" if ch else _xoauth2(adresse, "SYNTH-FALSCH"))
        m.authenticate("XOAUTH2", lambda _: _xoauth2(adresse, "SYNTH-ACCESS-1"))
        assert m.select("INBOX")[0] == "NO"
        m.select("INBOX", readonly=True)
        assert m.store("1", "+FLAGS", "\\Seen")[0] == "NO"
        m.fetch("1", "(BODY[])")
        m.logout()
        assert a.verstoesse == ["LOGIN (Passwort)", "SELECT statt EXAMINE", "schreibender Befehl STORE",
                                "BODY[] ohne PEEK"]
        assert a.anmeldungen == [(adresse, False), (adresse, True)]


def test_imap_app_passwoerter():
    """M23 (geheimnisschutz.md 6.5, E-230): LOGIN je Adresse; andere Adressen und LOGINDISABLED bleiben Verstöße."""
    eins, zwei = "haushalt.eins@example.invalid", "haushalt.zwei@example.invalid"
    with ImapAttrappe(passwoerter={eins: "abcdefghijklmnop"}) as a:
        m = imaplib.IMAP4("127.0.0.1", a.port)
        with pytest.raises(imaplib.IMAP4.error):
            m.login(eins, "falsch")
        m.login(eins.upper(), "abcdefghijklmnop")
        typ, daten = m.select('"INBOX"', readonly=True)
        assert typ == "OK" and int(daten[0]) > 0
        m.logout()
        assert not a.verstoesse and a.logins == [(eins, False), (eins.upper(), True)]
        m = imaplib.IMAP4("127.0.0.1", a.port)
        with pytest.raises(imaplib.IMAP4.error):
            m.login(zwei, "abcdefghijklmnop")
        m.logout()
        assert a.verstoesse == ["LOGIN (Passwort)"]
        a.login_deaktiviert = True
        m = imaplib.IMAP4("127.0.0.1", a.port)
        assert "LOGINDISABLED" in m.capabilities
        m.logout()


# ---------------------------------------------------------------- OAuth2 und ntfy
def _post(url, felder):
    req = urllib.request.Request(url, data=urlencode(felder).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_oauth_ablauf():
    with OAuthAttrappe(client_id="SYNTH-CLIENT.apps.example.invalid", client_secret="SYNTH-SECRET",
                       redirect_uri="http://127.0.0.1/oauth2/rueckruf") as o:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        url = o.autorisierung_url + "?" + urlencode({
            "response_type": "code", "client_id": o.client_id, "redirect_uri": o.redirect_uri, "scope": SCOPE,
            "state": "SYNTH-STATE-123456789012", "code_challenge": challenge, "code_challenge_method": "S256",
            "access_type": "offline", "prompt": "consent", "login_hint": "haushalt.eins@example.invalid"})
        zurueck = parse_qs(urlsplit(o.genehmige(url)).query)
        felder = {"grant_type": "authorization_code", "code": zurueck["code"][0], "redirect_uri": o.redirect_uri,
                  "client_id": o.client_id, "client_secret": o.client_secret, "code_verifier": verifier}
        status, t = _post(o.token_url, felder)
        assert status == 200 and t["refresh_token"].startswith("SYNTH-") and SCOPE in t["scope"]
        assert _post(o.token_url, felder)[1]["error"] == "invalid_grant"          # Code nur einmal
        assert o.access_gueltig("haushalt.eins@example.invalid", t["access_token"])
        status, t2 = _post(o.token_url, {"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                         "client_id": o.client_id, "client_secret": o.client_secret})
        assert status == 200 and t2["access_token"] != t["access_token"] and "refresh_token" not in t2
        assert _post(o.token_url, {"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                   "client_id": o.client_id, "client_secret": "SYNTH-FALSCH"})[0] == 401
        o.lasse_ablaufen("haushalt.eins@example.invalid")
        status, f = _post(o.token_url, {"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                        "client_id": o.client_id, "client_secret": o.client_secret})
        assert (status, f["error"], f["error_description"]) == (400, "invalid_grant",
                                                                "Token has been expired or revoked.")


def test_ntfy_attrappe(tmp_path):
    z = erzeuge_zertifikat(tmp_path)
    with NtfyAttrappe(erwartetes_token="SYNTH-NTFY", tls=z) as n:
        n.statusfolge = [500]
        kontext = ssl.create_default_context(cafile=str(z.zertifikat))
        def senden(token):
            req = urllib.request.Request(n.url + "/", data=json.dumps({"topic": "t", "message": "ä"}).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {token}"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5, context=kontext) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        assert [senden("SYNTH-NTFY"), senden("SYNTH-FALSCH"), senden("SYNTH-NTFY")] == [500, 401, 200]
        assert n.angenommen == [{"topic": "t", "message": "ä"}]
