"""M23: Sperrleiste, Entsperren-Dialog, Einstellungen „Schutz der Geheimnisse“, PIN merken, App-Passwort auf der
Postfachseite (oberflaeche.md 33, E-231) – Playwright wie M8; nicht kern."""

from __future__ import annotations

import re

import pytest

from tests.hilfen import kontor, m8
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m2 import SYNC_DATEN_PIN
from tests.hilfen.m6 import EINS, mail_felder, postfach
from tests.hilfen.m8 import oeffnen, tid
from tests.hilfen.m15 import Mitschnitt
from tests.hilfen.m23 import APP_PASSWORT, APP_ROH, PIN
from tests.hilfen.m31 import einstellung_oeffnen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

PW = m8.PASSWORT
ERFOLG = '[data-testid="meldung"][data-art="erfolg"]'


def _server(starte_server, **felder):
    felder.setdefault("heute", "2024-06-30")
    if felder.get("mock", True):
        felder.setdefault("mock_daten", SYNC_DATEN_PIN)
    server = starte_server(**felder)
    anm = kontor.modul("kontor.anmeldung")
    if not anm.ist_eingerichtet(server.config):
        anm.passwort_setzen(server.config, PW)
    return server


def _schutz(server) -> dict:
    return server.api.get("/api/geheimnisse/schutz", erwartet=200).daten


def _ein(server):
    server.api.post("/api/geheimnisse/schutz", json={"passwort": PW}, erwartet=200)


def _sperren(server):
    server.api.post("/api/geheimnisse/sperren", erwartet=200)


def _leiste_weg(seite):
    leiste = tid(seite, "sperr-leiste")
    expect(leiste).to_be_hidden()


# ------------------------------------------------------------------ Sperrleiste und Dialog
def test_ohne_schutz_keine_sperrleiste(starte_server, neue_seite):
    server = _server(starte_server)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    _leiste_weg(seite)
    _ein(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    _leiste_weg(seite)


def test_sperrleiste_und_entsperren(starte_server, neue_seite):
    server = _server(starte_server)
    _ein(server)
    seite = neue_seite(server)
    _sperren(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    leiste = tid(seite, "sperr-leiste")
    expect(leiste).to_be_visible()
    expect(leiste).to_have_attribute("role", "status")
    expect(leiste).to_contain_text("Kontor ist gesperrt")
    vor = leiste.evaluate("""l => { const t = document.querySelector('[data-testid="tab-leiste"]');
        return !t || !!(l.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING); }""")
    assert vor, "Sperrleiste steht über der Tab-Leiste"
    tid(seite, "sperr-entsperren").click()
    dialog = tid(seite, "entsperren-dialog")
    expect(dialog).to_be_visible()
    feld = tid(seite, "entsperren-passwort")
    expect(feld).to_have_attribute("type", "password")
    mit = Mitschnitt(seite)
    tid(seite, "entsperren-ok").click()
    expect(dialog).to_be_visible()
    assert mit.schreibend(r"/api/geheimnisse/entsperren") == [], "leer: keine Anfrage"
    expect(dialog).to_contain_text(re.compile(r"\S"))
    feld.fill("Falsches-Testpasswort-0000")
    tid(seite, "entsperren-ok").click()
    expect(feld).to_have_value("")
    expect(dialog).to_be_visible()
    assert len(mit.schreibend(r"/api/geheimnisse/entsperren")) == 1
    assert _schutz(server)["gesperrt"] is True
    feld.fill(PW)
    feld.press("Enter")
    expect(dialog).to_be_hidden()
    expect(tid(seite, "meldungen").locator(ERFOLG).filter(has_text="Entsperrt.")).to_be_visible()
    _leiste_weg(seite)
    assert _schutz(server)["entsperrt"] is True


# ------------------------------------------------------------------ Einstellungen
def _status(seite, aktiv: str, gesperrt: str):
    s = tid(seite, "schutz-status")
    expect(s).to_have_attribute("data-aktiv", aktiv)
    expect(s).to_have_attribute("data-gesperrt", gesperrt)


def _knoepfe(seite, sichtbar: set[str]):
    for k in ("schutz-einschalten", "schutz-sperren", "schutz-ausschalten", "schutz-pin-vergessen",
              "schutz-entsperren"):
        if k in sichtbar:
            expect(tid(seite, k)).to_be_visible()
        else:
            expect(tid(seite, k)).to_be_hidden()


def test_einstellungen_schutz(starte_server, neue_seite):
    server = _server(starte_server)
    seite = neue_seite(server)
    einstellung_oeffnen(seite, server, "schutz-status")          # M31: Bereich sicherheit (E-291)
    _status(seite, "nein", "nein")
    _knoepfe(seite, {"schutz-einschalten"})
    expect(tid(seite, "schutz-passwort")).to_have_attribute("type", "password")
    tid(seite, "schutz-passwort").fill(PW)
    tid(seite, "schutz-einschalten").click()
    _status(seite, "ja", "nein")
    _knoepfe(seite, {"schutz-sperren", "schutz-ausschalten"})
    assert _schutz(server)["aktiv"] is True
    tid(seite, "schutz-sperren").click()
    _status(seite, "ja", "ja")
    _knoepfe(seite, {"schutz-entsperren", "schutz-ausschalten"})
    expect(tid(seite, "sperr-leiste")).to_be_visible()
    tid(seite, "schutz-passwort").fill(PW)
    tid(seite, "schutz-entsperren").click()
    _status(seite, "ja", "nein")
    _leiste_weg(seite)
    server.api.put("/api/sync/pin/gemerkt", json={"pin": PIN}, erwartet=204)
    einstellung_oeffnen(seite, server, "schutz-status")          # M31: Bereich sicherheit (E-291)
    _knoepfe(seite, {"schutz-sperren", "schutz-ausschalten", "schutz-pin-vergessen"})
    tid(seite, "schutz-pin-vergessen").click()
    _knoepfe(seite, {"schutz-sperren", "schutz-ausschalten"})
    assert _schutz(server)["pin_gemerkt"] is False
    tid(seite, "schutz-passwort").fill(PW)
    tid(seite, "schutz-ausschalten").click()
    _status(seite, "nein", "nein")
    _knoepfe(seite, {"schutz-einschalten"})
    assert _schutz(server)["aktiv"] is False


def test_einstellungen_reihenfolge(starte_server, neue_seite):
    server = _server(starte_server)
    seite = neue_seite(server)
    einstellung_oeffnen(seite, server, "schutz-status")          # M31: Bereich sicherheit (E-291)
    # M31 (E-291): PIN und Schutz liegen in verschiedenen Bereichen; die Reihenfolge gilt nur für einen
    # PIN-Abschnitt, der im selben (sichtbaren) Bereich steht.
    nach = tid(seite, "schutz-status").evaluate("""s => {
        const p = [...document.querySelectorAll('[data-testid="seite-einstellungen"] [data-testid^="pin-"],'
            + '[data-testid="seite-einstellungen"] [data-testid*="-pin"]')].find(e => e.checkVisibility());
        return !p || !!(p.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING); }""")
    assert nach, "Abschnitt nach dem PIN-Abschnitt"


# ------------------------------------------------------------------ PIN-Dialog
def _pin_dialog(seite, server):
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, "sync-starten").click()
    d = tid(seite, "pin-dialog")
    expect(d).to_be_visible()
    return d


def test_pin_dialog_ohne_schutz_ohne_merken(starte_server, neue_seite):
    server = _server(starte_server)
    seite = neue_seite(server)
    _pin_dialog(seite, server)
    expect(tid(seite, "pin-merken")).to_be_hidden()


def test_pin_dialog_merken(starte_server, neue_seite):
    server = _server(starte_server)
    _ein(server)
    seite = neue_seite(server)
    _pin_dialog(seite, server)
    merken = tid(seite, "pin-merken")
    expect(merken).to_be_visible()
    mit = Mitschnitt(seite)
    merken.check()
    tid(seite, "pin-eingabe").fill(PIN)
    tid(seite, "pin-senden").click()
    expect(tid(seite, "pin-dialog")).to_have_count(0, timeout=15_000)
    assert ("PUT", "/api/sync/pin/gemerkt", {"pin": PIN}) in mit.schreibend()
    assert not [a for a in mit.schreibend() if a[1] == "/api/sync/pin"]
    assert _schutz(server)["pin_gemerkt"] is True


def test_pin_dialog_gesperrt_ohne_merken(starte_server, neue_seite):
    server = _server(starte_server)
    _ein(server)
    seite = neue_seite(server)
    _sperren(server)
    _pin_dialog(seite, server)
    expect(tid(seite, "pin-merken")).to_be_hidden()
    mit = Mitschnitt(seite)
    tid(seite, "pin-eingabe").fill(PIN)
    tid(seite, "pin-senden").click()
    expect(tid(seite, "pin-dialog")).to_have_count(0, timeout=15_000)
    assert ("PUT", "/api/sync/pin", {"pin": PIN}) in mit.schreibend()
    assert _schutz(server)["pin_gemerkt"] is False


# ------------------------------------------------------------------ Postfachseite
def _postfachseite(starte_server, neue_seite, imap, ordner):
    server = _server(starte_server, mock=False, **mail_felder(imap), mail_erstabruf_tage=3650)
    p = postfach(server.api, EINS, ordner=ordner)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/mail/postfaecher/{p['id']}", seitenname="postfach")
    return server, p, seite


def _speichern_mit_fehler(seite, feld):
    feld.fill(APP_PASSWORT)
    with seite.expect_response(lambda r: r.url.endswith("/app-passwort"), timeout=15_000) as antwort:
        tid(seite, "postfach-app-speichern").click()
    assert antwort.value.status == 422
    erg = tid(seite, "postfach-app-ergebnis")
    expect(erg).to_have_attribute("role", "status")
    expect(erg).to_contain_text(re.compile(r"\S"))
    expect(feld).to_have_value("")


def test_postfach_app_passwort(starte_server, neue_seite, netz_nur_loopback):
    with ImapAttrappe(passwoerter={EINS: APP_ROH}) as imap:
        server, p, seite = _postfachseite(starte_server, neue_seite, imap, "Falsch")
        api = server.api
        ordner = tid(seite, "postfach-ordner")
        expect(ordner).to_have_value("Falsch")
        feld = tid(seite, "postfach-app-passwort")
        expect(feld).to_have_attribute("type", "password")
        vor = feld.evaluate("""f => { const o = document.querySelector('[data-testid="postfach-anmelden"]');
            return !o || !!(f.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING); }""")
        assert vor, "Abschnitt vor dem OAuth2-Abschnitt"
        mit = Mitschnitt(seite)
        ordner.fill("INBOX")
        feld.fill(APP_PASSWORT)
        tid(seite, "postfach-app-speichern").click()
        n = len(imap.postfaecher[EINS]["INBOX"].nachrichten)
        expect(tid(seite, "meldungen").locator(ERFOLG).filter(has_text=str(n))).to_be_visible()
        expect(tid(seite, "postfach-status")).to_have_attribute("data-anmeldung", "angemeldet")
        schreibend = [(m, pf) for m, pf, _ in mit.schreibend()]
        assert schreibend[:2] == [("PATCH", f"/api/mail/postfaecher/{p['id']}"),
                                  ("PUT", f"/api/mail/postfaecher/{p['id']}/app-passwort")]
        assert api.get(f"/api/mail/postfaecher/{p['id']}", erwartet=200).daten["ordner"] == "INBOX"
        expect(tid(seite, "postfach-app-passwort")).to_have_value("")
        tid(seite, "postfach-app-entfernen").click()
        expect(tid(seite, "postfach-status")).to_have_attribute("data-anmeldung", "fehlt")
        assert api.get(f"/api/mail/postfaecher/{p['id']}/status", erwartet=200).daten["anmeldung"] == "fehlt"
        assert imap.verstoesse == []


def test_postfach_app_passwort_fehler(starte_server, neue_seite, netz_nur_loopback):
    with ImapAttrappe(passwoerter={EINS: APP_ROH}) as imap:
        server, p, seite = _postfachseite(starte_server, neue_seite, imap, "Falsch")
        feld = tid(seite, "postfach-app-passwort")
        _speichern_mit_fehler(seite, feld)
        assert server.api.get(f"/api/mail/postfaecher/{p['id']}/status", erwartet=200).daten["anmeldung"] == "fehlt"
        expect(tid(seite, "postfach-status")).not_to_have_attribute("data-anmeldung", "angemeldet")


def test_postfach_app_passwort_erneut_nach_fehler(starte_server, neue_seite, netz_nur_loopback):
    """Nach einem Fehler lässt sich mit korrigierten Angaben erneut speichern (Feld geleert zur neuen Eingabe)."""
    with ImapAttrappe(passwoerter={EINS: APP_ROH}) as imap:
        server, p, seite = _postfachseite(starte_server, neue_seite, imap, "Falsch")
        feld = tid(seite, "postfach-app-passwort")
        _speichern_mit_fehler(seite, feld)
        tid(seite, "postfach-ordner").fill("INBOX")
        feld.fill(APP_PASSWORT)
        tid(seite, "postfach-app-speichern").click()
        expect(tid(seite, "postfach-status")).to_have_attribute("data-anmeldung", "angemeldet")
