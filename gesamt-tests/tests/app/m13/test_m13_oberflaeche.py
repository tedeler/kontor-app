"""M13: Versionsanzeige und About-Fenster in der Oberfläche (oberflaeche.md 24; E-179, E-180).

Playwright wie M8 (E-139). Erwartete Werte kommen aus ``GET /api/version`` derselben laufenden App; keine
Versionsnummer ist fest eingetragen (E-176). Beide Build-Zweige und der Fehlerfall entstehen über im Browser
ersetzte Antworten (E-180), der 401-Fall echt über eine beendete Sitzung.
"""

from __future__ import annotations

import json

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import oeffnen, tid
from tests.hilfen.m13 import ENTWICKLUNGSSTAND_TEXT, knopf_text_soll, leer

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

NAV_IDS = [t for t, _ in m8.NAV_LINKS]   # M28 (oberflaeche.md 37.2, E-254)

JS_LAGE = """btn => {
  const nav = document.querySelector('[data-testid="navigation"]');
  const eintraege = [...document.querySelectorAll('[data-testid="navigation"] a[data-testid]')];
  const r = (e) => { const b = e.getBoundingClientRect(); return {top: b.top, bottom: b.bottom, height: b.height}; };
  return {
    tag: btn.tagName.toLowerCase(),
    inNav: !!nav && nav.contains(btn),
    navIds: eintraege.map((e) => e.getAttribute('data-testid')),
    alleDavor: eintraege.every((e) => (e.compareDocumentPosition(btn) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0),
    knopf: r(btn), nav: nav ? r(nav) : null, navInhalt: nav ? nav.scrollHeight : 0, letzter: eintraege.length ? r(eintraege[eintraege.length - 1]) : null,
  };
}"""
JS_IM_DIALOG = """() => { const d = document.querySelector('[data-testid="ueber-dialog"]');
  return !!d && d.contains(document.activeElement) && document.activeElement !== d; }"""
JS_BREITE = "() => [document.documentElement.scrollWidth, window.innerWidth]"


def _angaben(server) -> dict:
    return dict(server.api.get("/api/version", erwartet=200).daten)


def _start(starte_server, neue_seite, geraet="desktop", pfad="/", seitenname="uebersicht", **server_kw):
    server = starte_server(**server_kw)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, pfad, seitenname=seitenname)
    return server, seite


def _knopf(seite):
    """version-knopf bedienbar machen (mobil: Menü öffnen, oberflaeche.md 16.2)."""
    k = tid(seite, "version-knopf")
    if m8.ist_mobil(seite):
        expect(k).to_be_hidden()
        tid(seite, "menue-knopf").click()
        expect(tid(seite, "menue-knopf")).to_have_attribute("aria-expanded", "true")
    expect(k).to_be_visible()
    return k


def _oeffnen(seite):
    _knopf(seite).click()
    d = tid(seite, "ueber-dialog")
    expect(d).to_be_visible()
    return d


def _ohne_waagerechtes_scrollen(seite):
    breite, innen = seite.evaluate(JS_BREITE)
    assert breite <= innen, f"waagerechtes Scrollen: scrollWidth {breite} > innerWidth {innen} (oberflaeche.md 16.2)"


def _antwort_ersetzen(seite, aenderung: dict):
    """GET /api/version mit der echten Antwort des Servers, geändert um ``aenderung`` (E-180)."""
    def handler(route):
        echt = route.fetch()
        daten = {**echt.json(), **aenderung}
        route.fulfill(status=200, headers={**echt.headers, "content-type": "application/json"},
                      body=json.dumps(daten))
    seite.route("**/api/version", handler)


# ------------------------------------------------------------------ 24.1 Versionsanzeige


@pytest.mark.kern
def test_versionsknopf_als_letztes_element_der_navigation(starte_server, neue_seite, geraet):
    server, seite = _start(starte_server, neue_seite, geraet)
    v = _angaben(server)["version"]
    k = _knopf(seite)
    expect(k).to_have_text(knopf_text_soll(server.api.get("/").text, v))   # M31 (E-285)
    expect(k).to_have_attribute("aria-haspopup", "dialog")
    lage = k.evaluate(JS_LAGE)
    assert lage["tag"] == "button"
    assert lage["inNav"], "version-knopf steht nicht in der Hauptnavigation"
    assert m8.ohne_lose_links(lage["navIds"]) == NAV_IDS, "die Liste der Navigationseinträge (oberflaeche.md 3) ist unverändert"
    assert lage["alleDavor"], "version-knopf ist das letzte Element: nach allen nav-Einträgen"
    assert lage["knopf"]["top"] >= lage["letzter"]["bottom"] - 1, "unterhalb des letzten Navigationseintrags"
    # M28 (37.2, E-254): die längere Navigation darf in sich rollen; maßgeblich ist ihr Inhalt
    unten = max(lage["nav"]["bottom"], lage["nav"]["top"] + lage["navInhalt"])
    assert lage["nav"]["top"] - 1 <= lage["knopf"]["top"] and lage["knopf"]["bottom"] <= unten + 1, \
        "innerhalb der Navigationsleiste"
    if m8.ist_mobil(seite):
        assert lage["knopf"]["height"] >= 44, f"Trefferfläche {lage['knopf']['height']} px < 44 px"
        _ohne_waagerechtes_scrollen(seite)


# ------------------------------------------------------------------ 24.2 About-Fenster


@pytest.mark.kern
def test_ueber_dialog_zeigt_die_versionsangaben(starte_server, neue_seite, geraet):
    server, seite = _start(starte_server, neue_seite, geraet, pfad="/kategorien", seitenname="kategorien")
    d = _oeffnen(seite)
    a = _angaben(server)
    expect(d).to_have_attribute("role", "dialog")
    expect(d).to_have_attribute("aria-modal", "true")
    expect(seite.get_by_role("dialog", name="Über Kontor")).to_be_visible()
    expect(tid(seite, "ueber-schliessen")).to_be_focused()
    if m8.ist_mobil(seite):
        expect(tid(seite, "menue-knopf")).to_have_attribute("aria-expanded", "false")
        expect(tid(seite, "version-knopf")).to_be_hidden()
    assert leer(tid(d, "ueber-version").inner_text()) == f"Version {a['version']}"
    assert leer(tid(d, "ueber-modus").inner_text()) == "Mock-Modus"
    assert a["python"] in tid(d, "ueber-python").inner_text()
    assert a["datenbank"] in tid(d, "ueber-datenbank").inner_text()
    assert leer(tid(d, "ueber-schema").inner_text()) == \
        f"Datenbank {a['datenbank_schema']} · Sicherung {a['sicherung_schema']}"
    build = tid(d, "ueber-build").inner_text()
    if a["entwicklungsstand"]:
        assert ENTWICKLUNGSSTAND_TEXT in leer(build)
    else:
        assert a["commit"] in build
    link = tid(d, "ueber-repository")
    assert link.evaluate("e => e.tagName.toLowerCase()") == "a"
    assert link.get_attribute("href") == a["repository"]
    assert link.get_attribute("target") == "_blank"
    assert "noopener" in (link.get_attribute("rel") or "").split()
    if m8.ist_mobil(seite):
        _ohne_waagerechtes_scrollen(seite)


@pytest.mark.kern
def test_ueber_dialog_im_echtbetrieb(starte_server, neue_seite):
    server, seite = _start(starte_server, neue_seite, mock=False)
    d = _oeffnen(seite)
    a = _angaben(server)
    assert a["modus"] == "echt"
    assert leer(tid(d, "ueber-modus").inner_text()) == "Echtbetrieb"
    assert a["datenbank"] in tid(d, "ueber-datenbank").inner_text()
    assert leer(tid(d, "ueber-version").inner_text()) == f"Version {a['version']}"


@pytest.mark.kern
@pytest.mark.parametrize("zweig", ["release", "entwicklung"])
def test_build_angaben_beider_zweige(starte_server, neue_seite, zweig):
    """24.2 ueber-build: Release-Build mit Datum und Commit, sonst Entwicklungsstand (E-180)."""
    server = starte_server()
    seite = neue_seite(server)
    if zweig == "release":
        _antwort_ersetzen(seite, {"commit": "0a1b2c3d", "build_datum": "2026-11-10T08:15:00Z",
                                  "entwicklungsstand": False})
    else:
        _antwort_ersetzen(seite, {"commit": None, "build_datum": None, "entwicklungsstand": True})
    oeffnen(seite, server, "/", seitenname="uebersicht")
    d = _oeffnen(seite)
    build = leer(tid(d, "ueber-build").inner_text())
    if zweig == "release":
        assert "0a1b2c3d" in build
        assert "Entwicklungsstand" not in build
    else:
        assert ENTWICKLUNGSSTAND_TEXT in build
        assert "0a1b2c3d" not in build
    assert leer(tid(d, "ueber-version").inner_text()) == f"Version {_angaben(server)['version']}"


# ------------------------------------------------------------------ 24.3 Bedienung


@pytest.mark.kern
@pytest.mark.parametrize("weg", ["schliessen", "x", "esc"])
def test_schliessen_und_fokus_zurueck(starte_server, neue_seite, geraet, weg):
    server, seite = _start(starte_server, neue_seite, geraet)
    d = _oeffnen(seite)
    if weg == "esc":
        seite.keyboard.press("Escape")
    else:
        tid(d, f"ueber-{weg}").click()
    expect(tid(seite, "ueber-dialog")).to_have_count(0)
    if m8.ist_mobil(seite):
        expect(tid(seite, "menue-knopf")).to_be_focused()
        expect(tid(seite, "menue-knopf")).to_have_attribute("aria-expanded", "false")
        expect(tid(seite, "version-knopf")).to_be_hidden()
        _ohne_waagerechtes_scrollen(seite)
    else:
        expect(tid(seite, "version-knopf")).to_be_focused()
    # erneutes Öffnen geht
    _oeffnen(seite)


@pytest.mark.kern
def test_tastatur_enter_leertaste_und_tab(starte_server, neue_seite):
    server, seite = _start(starte_server, neue_seite)
    k = _knopf(seite)
    for taste in ("Enter", " "):
        k.focus()
        seite.keyboard.press(taste)
        expect(tid(seite, "ueber-dialog")).to_be_visible()
        expect(tid(seite, "ueber-schliessen")).to_be_focused()
        for kuerzel in ["Tab"] * 8 + ["Shift+Tab"] * 8:
            seite.keyboard.press(kuerzel)
            assert seite.evaluate(JS_IM_DIALOG), f"Fokus verlässt den Dialog nach {kuerzel} (oberflaeche.md 9)"
        seite.keyboard.press("Escape")
        expect(tid(seite, "ueber-dialog")).to_have_count(0)
        expect(k).to_be_focused()


# ------------------------------------------------------------------ 24.4 Fehlerfall


@pytest.mark.kern
@pytest.mark.parametrize("status", [404, 500])
def test_fehler_oeffnet_keinen_dialog(starte_server, neue_seite, status):
    server, seite = _start(starte_server, neue_seite)
    text = "Versionsangaben im Test nicht verfügbar"
    koerper = {"fehler": {"code": "nicht_gefunden" if status == 404 else "interner_fehler", "meldung": text,
                          "details": None}}
    seite.route("**/api/version", lambda route: route.fulfill(status=status, content_type="application/json",
                                                              body=json.dumps(koerper)))
    _knopf(seite).click()
    fehler = seite.locator('[data-testid="meldung"][data-art="fehler"]')
    expect(fehler.first).to_be_visible()
    if status == 404:
        expect(fehler.filter(has_text=text)).to_have_count(1)
    expect(tid(seite, "ueber-dialog")).to_have_count(0)


@pytest.mark.kern
def test_fehler_401_fuehrt_zur_anmeldung(starte_server, neue_seite):
    server = starte_server(anmeldung=True)
    seite = neue_seite(server)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    status = seite.context.request.get(server.url + "/api/anmeldung").json()
    r = seite.context.request.post(server.url + "/api/anmeldung/abmelden",
                                   headers={"X-Kontor-CSRF": status["csrf_token"]})
    assert r.status == 204
    _knopf(seite).click()
    expect(tid(seite, "anmeldung-formular")).to_be_visible()
    assert seite.url == server.url + "/anmelden?weiter=/kategorien"
