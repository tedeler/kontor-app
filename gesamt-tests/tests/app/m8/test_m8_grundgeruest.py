"""M8: Routen, Navigation, Grundgerüst, Mock-Hinweis und mobiles Menü (oberflaeche.md 1–4, 16.1, 16.2; K 3, K 5, K 14)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import NAV, navigiere, oeffnen, tid, warte_geladen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

SEITEN = [(z, p, t) for z, p, t in NAV] + [("benachrichtigungen", "/benachrichtigungen", "Benachrichtigungen")]


@pytest.fixture
def server(starte_server):
    s = starte_server()
    m8.importiere(s.api)
    return s


def _pruefe_seite(seite, server, name, pfad, titel, nav=True):
    s = warte_geladen(seite, name)
    expect(s.locator("h1")).to_have_text(titel)
    expect(seite.locator("h1")).to_have_count(1)
    assert seite.title() == f"{titel} – Kontor", seite.title()
    if nav:
        expect(tid(seite, f"nav-{name}")).to_have_attribute("aria-current", "page")
        assert seite.locator('[data-testid="navigation"] a[aria-current="page"]').count() == 1


@pytest.mark.kern
@pytest.mark.parametrize("name,pfad,titel", SEITEN, ids=[s[0] for s in SEITEN])
def test_direkter_aufruf(server, neue_seite, geraet, name, pfad, titel):
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, pfad)
    _pruefe_seite(seite, server, name, pfad, titel, nav=name != "benachrichtigungen")
    expect(tid(seite, "app")).to_have_attribute("data-layout", "mobil" if geraet == "handy" else "desktop")


@pytest.mark.kern
def test_navigation_ohne_neuladen_und_zurueck(server, neue_seite, geraet):
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    eintraege = seite.locator('[data-testid="navigation"] a[data-testid]').evaluate_all(
        "els => els.map(e => [e.getAttribute('data-testid'), e.tagName, e.getAttribute('href')])")
    # M28 (oberflaeche.md 37.2, E-254): Links in Themengruppen, nav-wiederkehrend entfällt; ab M32 (41.1, E-307) mit
    # navlink-tags, ohne navlink-statistik; navlink-konfiguration steht frei in „Betrieb“ (eigener Test in M32)
    assert m8.ohne_lose_links(eintraege) == [[t, "A", p] for t, p in m8.NAV_LINKS], "Einträge, Reihenfolge, Links"
    expect(tid(seite, "navigation")).to_have_attribute("aria-label", "Hauptnavigation")
    marke = seite.evaluate("() => (window.__m8marke = Math.random())")
    for z, p, t in NAV:
        navigiere(seite, z)
        _pruefe_seite(seite, server, z, p, t)
        assert seite.url == server.url + p
    assert seite.evaluate("() => window.__m8marke") == marke, "keine Seite neu geladen"
    seite.go_back()
    _pruefe_seite(seite, server, NAV[-2][0], NAV[-2][1], NAV[-2][2])
    seite.go_forward()
    _pruefe_seite(seite, server, NAV[-1][0], NAV[-1][1], NAV[-1][2])
    assert seite.evaluate("() => window.__m8marke") == marke


def test_wiederkehrend_entfallen(server, neue_seite, geraet):
    """M28 (37.3, E-254): /wiederkehrend direkt → 404 ohne Hülle; in der Oberfläche „Nicht gefunden“."""
    import httpx
    r = httpx.get(server.url + "/wiederkehrend", follow_redirects=False, trust_env=False)
    assert r.status_code == 404
    assert 'data-testid="app"' not in r.text
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(tid(seite, "nav-wiederkehrend")).to_have_count(0)
    # Navigation innerhalb der Oberfläche: ein Link der Seite auf /wiederkehrend
    seite.evaluate("""() => { const a = document.createElement('a'); a.href = '/wiederkehrend';
      a.textContent = 'alt'; a.setAttribute('data-testid', 'm28-alter-link');
      document.querySelector('[data-testid="hauptbereich"]').prepend(a); }""")
    marke = seite.evaluate("() => (window.__m28marke = 1)")
    tid(seite, "m28-alter-link").click()
    warte_geladen(seite, "nicht-gefunden")
    assert seite.evaluate("() => window.__m28marke") == marke, "ohne Neuladen"


@pytest.mark.kern
def test_landmarken(server, neue_seite):
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(seite.get_by_role("banner")).to_have_count(1)
    expect(seite.get_by_role("main")).to_have_count(1)
    expect(tid(seite, "hauptbereich")).to_have_js_property("tagName", "MAIN")
    expect(tid(seite, "app-kopf")).to_have_js_property("tagName", "HEADER")
    expect(tid(seite, "navigation")).to_have_js_property("tagName", "NAV")
    expect(tid(seite, "meldungen")).to_have_attribute("role", "status")
    expect(tid(seite, "meldungen")).to_have_attribute("aria-live", "polite")


def test_konto_und_unbekannt(server, neue_seite):
    seite = neue_seite(server)
    giro = next(k for k in server.api.konten() if k["name"] == "Girokonto")
    oeffnen(seite, server, f"/konten/{giro['id']}")
    _pruefe_seite(seite, server, "konto", "", "Girokonto", nav=False)
    expect(tid(seite, "nav-konten")).to_have_attribute("aria-current", "page")
    oeffnen(seite, server, "/konten/999999")
    s = warte_geladen(seite, "nicht-gefunden")
    expect(s.locator("h1")).to_have_text("Nicht gefunden")


@pytest.mark.kern
@pytest.mark.parametrize("pfad", ["/", "/konten", "/kategorien", "/einstellungen", "/kredite"])
def test_mock_hinweis_immer_sichtbar(server, neue_seite, geraet, pfad):
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, pfad)
    h = tid(seite, "mock-hinweis")
    expect(h).to_be_visible()
    expect(h).to_contain_text("Mock-Modus")
    seite.mouse.wheel(0, 3000)          # auch nach dem Scrollen oben sichtbar
    seite.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    box = h.bounding_box()
    vp = seite.viewport_size
    assert box and box["y"] >= -1 and box["y"] + box["height"] <= vp["height"] and box["width"] > 0, box
    oben = seite.evaluate("""() => { const r = document.querySelector('[data-testid="mock-hinweis"]')
        .getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!e && !!e.closest('[data-testid="mock-hinweis"]'); }""")
    assert oben, "Mock-Hinweis ist verdeckt"


def test_kein_mock_hinweis_im_echtmodus(starte_server, neue_seite, geraet):
    server = starte_server(mock=False)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(seite.locator("#mock-hinweis")).to_have_count(0)
    expect(tid(seite, "mock-hinweis")).to_have_count(0)


@pytest.mark.kern
def test_mobiles_menue(server, neue_seite):
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, "/", seitenname="uebersicht")
    knopf = tid(seite, "menue-knopf")
    expect(knopf).to_be_visible()
    expect(tid(seite, "navigation")).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    assert knopf.get_attribute("aria-controls")
    knopf.click()
    expect(tid(seite, "navigation")).to_be_visible()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    expect(tid(seite, "nav-uebersicht")).to_be_focused()
    for z, _, _ in NAV:
        box = tid(seite, f"nav-{z}").bounding_box()
        assert box["height"] >= 44 - 0.5 and box["width"] >= 44 - 0.5, (z, box)
    seite.keyboard.press("Escape")
    expect(tid(seite, "navigation")).to_be_hidden()
    expect(knopf).to_be_focused()
    knopf.click()
    tid(seite, "menue-hintergrund").click(position={"x": 370, "y": 600})
    expect(tid(seite, "navigation")).to_be_hidden()
    knopf.click()
    tid(seite, "nav-kredite").click()
    warte_geladen(seite, "kredite")
    expect(tid(seite, "navigation")).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")


@pytest.mark.kern
def test_desktop_ohne_menueknopf(server, neue_seite):
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(tid(seite, "navigation")).to_be_visible()
    expect(tid(seite, "menue-knopf")).to_be_hidden()


@pytest.mark.kern
def test_layout_wechsel_ohne_neuladen(server, neue_seite):
    seite = neue_seite(server)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    marke = seite.evaluate("() => (window.__m8marke = 1)")
    seite.set_viewport_size({"width": 600, "height": 800})
    expect(tid(seite, "app")).to_have_attribute("data-layout", "mobil")
    expect(tid(seite, "navigation")).to_be_hidden()
    seite.set_viewport_size({"width": 1024, "height": 800})
    expect(tid(seite, "app")).to_have_attribute("data-layout", "desktop")
    expect(tid(seite, "navigation")).to_be_visible()
    assert seite.evaluate("() => window.__m8marke") == marke


@pytest.mark.parametrize("pfad", ["/", "/konten", "/kategorien", "/kredite", "/berichte",
                                  "/import", "/einstellungen", "/protokoll", "/empfaenger", "/konto"])
def test_kein_waagerechtes_scrollen_mobil(server, neue_seite, pfad):
    seite = neue_seite(server, "handy")
    if pfad == "/konto":
        pfad = f"/konten/{next(k['id'] for k in server.api.konten() if k['name'] == 'Girokonto')}"
    oeffnen(seite, server, pfad)
    seite.wait_for_selector('[data-testid^="seite-"][data-geladen="ja"]')
    breite = seite.evaluate("() => [document.documentElement.scrollWidth, window.innerWidth]")
    assert breite[0] <= breite[1], f"waagerechtes Scrollen auf {pfad}: {breite}"
