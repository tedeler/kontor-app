"""M8: Helles und dunkles Design (oberflaeche.md 17) und installierbare Web-App mit Offline-Hülle
(oberflaeche.md 18; K 5; E-146)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import JS_HINTERGRUND, JS_TEXTFARBE, kontrast, leuchtdichte, oeffnen, tid

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


@pytest.fixture
def server(starte_server):
    s = starte_server()
    m8.importiere(s.api)
    return s


def _farben(seite):
    h1 = tid(seite, "hauptbereich").locator("h1")
    hinter = h1.evaluate(JS_HINTERGRUND)
    text = h1.evaluate(JS_TEXTFARBE)
    return hinter, text


def _pruefe_thema(seite, thema):
    expect(seite.locator("html")).to_have_attribute("data-thema", thema)
    hinter, text = _farben(seite)
    l = leuchtdichte(hinter)
    if thema == "dunkel":
        assert l < 0.2, f"dunkler Hintergrund erwartet, Leuchtdichte {l:.3f} ({hinter})"
    else:
        assert l > 0.7, f"heller Hintergrund erwartet, Leuchtdichte {l:.3f} ({hinter})"
    assert kontrast(hinter, text) >= 4.5, f"Kontrast {kontrast(hinter, text):.2f} < 4,5 ({text} auf {hinter})"


@pytest.mark.parametrize("schema,thema", [("light", "hell"), ("dark", "dunkel")])
def test_folgt_der_systemeinstellung(server, neue_seite, geraet, schema, thema):
    seite = neue_seite(server, geraet, color_scheme=schema)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    _pruefe_thema(seite, thema)


def test_wechsel_ohne_neuladen_und_einstellung(server, neue_seite):
    seite = neue_seite(server)
    oeffnen(seite, server, "/einstellungen", seitenname="einstellungen")
    marke = seite.evaluate("() => (window.__m8marke = 7)")
    _pruefe_thema(seite, "hell")
    seite.emulate_media(color_scheme="dark")
    _pruefe_thema(seite, "dunkel")
    seite.emulate_media(color_scheme="light")
    _pruefe_thema(seite, "hell")
    assert seite.evaluate("() => window.__m8marke") == marke
    expect(tid(seite, "einstellung-thema")).to_have_value("system")
    tid(seite, "einstellung-thema").select_option("dunkel")
    _pruefe_thema(seite, "dunkel")
    assert seite.evaluate("() => localStorage.getItem('kontor.thema')") == "dunkel"
    seite.reload()
    m8.warte_geladen(seite, "einstellungen")
    _pruefe_thema(seite, "dunkel")                       # trotz hellem System
    tid(seite, "einstellung-thema").select_option("system")
    _pruefe_thema(seite, "hell")
    seite.keyboard.press("Control+k")
    seite.keyboard.type("design dunkel")
    seite.keyboard.press("Enter")
    _pruefe_thema(seite, "dunkel")


# ------------------------------------------------------------------ PWA (18)
def test_installierbar_und_service_worker(server, neue_seite):
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    seite.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    reg = seite.evaluate("() => navigator.serviceWorker.getRegistration('/').then(r => r && r.scope)")
    assert reg == server.url + "/"
    cdp = seite.context.new_cdp_session(seite)
    fehler = cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]
    assert fehler == [], f"nicht installierbar: {fehler}"
    m = cdp.send("Page.getAppManifest")
    assert m.get("url", "").endswith("/oeffentlich/manifest.webmanifest") and not m.get("errors"), m
    seite.reload()
    m8.warte_geladen(seite, "uebersicht")
    assert seite.evaluate("() => !!navigator.serviceWorker.controller"), "Service Worker steuert die Seite"


def test_offline_huelle_und_keine_daten(server, neue_seite):
    seite = neue_seite(server)
    giro = next(k["id"] for k in server.api.konten() if k["name"] == "Girokonto")
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    seite.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
    seite.reload()
    m8.warte_geladen(seite, "konto")
    assert seite.evaluate("() => !!navigator.serviceWorker.controller")
    seite.context.set_offline(True)
    try:
        seite.goto(server.url + "/kategorien")
        hinweis = tid(seite, "offline-hinweis")
        expect(hinweis).to_be_visible()
        expect(hinweis).to_have_attribute("role", "status")
        assert "offline" in hinweis.inner_text().lower()
        expect(seite.locator('[data-testid^="kategorie-"][role="treeitem"]')).to_have_count(0)
        expect(tid(seite, "mock-hinweis")).to_be_visible()
    finally:
        seite.context.set_offline(False)
    seite.evaluate("() => window.dispatchEvent(new Event('online'))")
    expect(tid(seite, "offline-hinweis")).to_be_hidden()
    m8.warte_geladen(seite, "kategorien")
    # keine Daten im Browser (18): Caches ohne /api/, Speicher nur kontor.* ohne Buchbestand
    caches = seite.evaluate("""async () => {
        const aus = [];
        for (const n of await caches.keys()) {
          const c = await caches.open(n);
          for (const r of await c.keys()) { const a = await c.match(r); aus.push([n, r.url, await a.clone().text()]); }
        }
        return aus; }""")
    assert caches, "Hülle im Cache"
    texte = ["Supermarkt Frischekorb", "Bäckerei Körnchen", "Wocheneinkauf", "Abschlag Strom"]
    for name, url, inhalt in caches:
        assert name.startswith("kontor-"), name
        assert "/api/" not in url, url
        for t in texte:
            assert t not in inhalt, f"Buchbestand im Cache {url}: {t}"
    speicher = seite.evaluate("() => [Object.entries(localStorage), Object.entries(sessionStorage)]")
    for k, v in speicher[0] + speicher[1]:
        assert k.startswith("kontor."), k
        for t in texte:
            assert t not in v, (k, t)
