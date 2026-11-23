"""M28: Person, Navigation in Gruppen, Tabs-Kontextmenü, wiederkehrende Buchungen entfernt
(oberflaeche.md 37.1–37.5; E-252 bis E-255). Browsertests, nicht kern."""

from __future__ import annotations

import pytest

from tests.hilfen import m8, m17, m28
from tests.hilfen.m8 import oeffnen, tid, warte_geladen, warte_liste, zeile
from tests.hilfen.m17 import aktive, pfade, tab, warte, warte_tabs

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


def _server(starte_server, **kw):
    server = starte_server(**kw)
    d = m17.daten(server.api)
    return server, d["k"], d["b"]


# ------------------------------------------------------------------ 37.1 Person


def test_pflichtdialog_ohne_person(starte_server, neue_seite, geraet):
    server, k, b = _server(starte_server)
    seite = neue_seite(server, geraet, person=None)
    oeffnen(seite, server, "/konten")
    d = tid(seite, "person-dialog")
    expect(d).to_be_visible()
    expect(d).to_have_attribute("role", "dialog")
    expect(d).to_contain_text("Wer bist du?")
    assert "null" not in d.inner_text()
    expect(d.get_by_test_id("person-torsten")).to_be_visible()
    expect(d.get_by_test_id("person-tina")).to_be_visible()
    expect(d.get_by_test_id("person-abbrechen")).to_have_count(0)
    seite.keyboard.press("Escape")
    expect(d).to_be_visible()
    knopf = tid(seite, "person-knopf")
    expect(knopf).to_have_attribute("data-person", "")
    expect(knopf).to_have_attribute("data-kurz", "?")
    expect(knopf).to_have_attribute("aria-label", "Wer bist du?")
    d.get_by_test_id("person-tina").click()
    expect(tid(seite, "person-dialog")).to_be_hidden()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    warte_geladen(seite, "konten")
    assert seite.evaluate("() => localStorage.getItem('kontor.person')") == "Tina"
    knopf = tid(seite, "person-knopf")
    expect(knopf).to_have_attribute("data-person", "Tina")
    expect(knopf).to_have_attribute("data-kurz", "T")
    expect(knopf).to_have_attribute("aria-label", "Angemeldet als Tina. Benutzer wechseln.")
    if geraet == "desktop":
        expect(knopf).to_have_text("Tina")
    else:
        assert seite.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    seite.reload()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    warte_geladen(seite, "konten")
    expect(tid(seite, "person-dialog")).to_be_hidden()


@pytest.mark.parametrize("wert", ["Toni", "", "torsten"])
def test_ungueltige_person_gilt_als_keine(starte_server, neue_seite, wert):
    server, k, b = _server(starte_server)
    seite = neue_seite(server, person=None)
    seite.add_init_script(f"localStorage.setItem('kontor.person', {wert!r});")
    oeffnen(seite, server, "/")
    expect(tid(seite, "person-dialog")).to_be_visible()
    expect(tid(seite, "person-knopf")).to_have_attribute("data-kurz", "?")


def test_benutzer_wechseln(starte_server, neue_seite):
    server, k, b = _server(starte_server)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    knopf = tid(seite, "person-knopf")
    expect(knopf).to_have_attribute("data-person", "Torsten")
    expect(knopf).to_have_text("Torsten")
    kopf = [b_["x"] for b_ in (tid(seite, t).bounding_box() for t in ("befehlspalette-knopf", "person-knopf"))]
    assert kopf[0] < kopf[1], "Personenknopf rechts nach den übrigen Kopfknöpfen"
    knopf.click()
    d = tid(seite, "person-dialog")
    expect(d).to_be_visible()
    expect(d).to_contain_text("Benutzer wechseln")
    d.get_by_test_id("person-abbrechen").click()
    expect(d).to_be_hidden()
    knopf.click()
    seite.keyboard.press("Escape")
    expect(tid(seite, "person-dialog")).to_be_hidden()
    assert seite.evaluate("() => localStorage.getItem('kontor.person')") == "Torsten"
    knopf.click()
    tid(seite, "person-tina").click()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    expect(tid(seite, "person-knopf")).to_have_attribute("data-person", "Tina")
    assert seite.evaluate("() => localStorage.getItem('kontor.person')") == "Tina"


def test_abmelden_vergisst_person(starte_server, neue_seite):
    server, k, b = _server(starte_server, anmeldung=True)
    seite = neue_seite(server, person=None)
    oeffnen(seite, server, "/einstellungen?bereich=sicherheit")   # M31: Bereich der Anmeldung (E-286, E-291)
    m8.person_waehlen(seite, "Tina")
    warte_geladen(seite, "einstellungen")
    tid(seite, "abmelden").click()
    expect(tid(seite, "anmeldung-formular")).to_be_visible()
    assert seite.evaluate("() => localStorage.getItem('kontor.person')") is None


def test_speicher_gesperrt_person_fuer_die_seite(starte_server, neue_seite):
    """37.1/37.14 C1: ohne Speicher gilt die gewählte Person für die geladene Seite."""
    server, k, b = _server(starte_server)
    seite = neue_seite(server, person=None)
    seite.add_init_script("""(() => { const f = () => { throw new DOMException('gesperrt', 'SecurityError'); };
      Object.defineProperty(window, 'localStorage', { get: f }); })()""")
    oeffnen(seite, server, f"/konten/{k['giro']}")
    m8.person_waehlen(seite)
    warte_geladen(seite, "konto")
    expect(tid(seite, "person-knopf")).to_have_attribute("data-person", "Torsten")
    seite.reload()
    expect(tid(seite, "person-dialog")).to_be_visible()


# ------------------------------------------------------------------ 37.2 Navigation


def test_navigation_in_gruppen(starte_server, neue_seite, geraet):
    server, k, b = _server(starte_server)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    if m8.ist_mobil(seite):
        tid(seite, "menue-knopf").click()
    nav = tid(seite, "navigation")
    gruppen = nav.locator("h2[data-testid^='nav-gruppe-']").evaluate_all(
        "els => els.map(e => [e.getAttribute('data-testid'), e.id, e.textContent.trim()])")
    assert [g[0] for g in gruppen] == [f"nav-gruppe-{g}" for g in m8.NAV_GRUPPEN]
    assert [g[2] for g in gruppen] == ["Buchhaltung", "Zahlungen", "Auswertung", "Regeln", "Betrieb"]
    links_je_gruppe = nav.evaluate("""n => [...n.querySelectorAll('h2[data-testid^="nav-gruppe-"]')].map(h => {
      const a = document.querySelector('[aria-labelledby="' + h.id + '"]');
      return a ? [...a.querySelectorAll('a[data-testid]')].map(x => x.getAttribute('data-testid')) : null; })""")
    t = [x for x, _ in m8.NAV_LINKS]
    # ab M32 (41.1, E-307): Tags in „Buchhaltung“, „Auswertung“ ohne Statistik, Konfiguration frei in „Betrieb“
    assert [m8.ohne_lose_links(g) for g in links_je_gruppe] == [t[a:b] for a, b in m8.NAV_GRUPPEN_SCHNITTE], (
        "Abschnitte mit aria-labelledby")
    expect(tid(seite, "nav-wiederkehrend")).to_have_count(0)
    # navlink-erwartet bleibt mobil ausgeblendet (oberflaeche.md 30, von M28 nicht aufgehoben; W-013, E-257)
    mobil_aus = {"navlink-erwartet"} if m8.ist_mobil(seite) else set()
    for testid, _ in m8.NAV_LINKS:
        if testid in mobil_aus:
            expect(tid(seite, testid)).to_be_hidden()
        else:
            expect(tid(seite, testid)).to_be_visible()
    ziele = [("navlink-mail", "mail"), ("navlink-tags", "tags"), ("navlink-erwartet", "erwartet")]
    for testid, ziel in [z for z in ziele if z[0] not in mobil_aus]:
        if m8.ist_mobil(seite) and tid(seite, "menue-knopf").get_attribute("aria-expanded") != "true":
            tid(seite, "menue-knopf").click()
        tid(seite, testid).click()
        warte_geladen(seite, ziel)
        expect(tid(seite, testid)).to_have_attribute("aria-current", "page")


def test_palette_ohne_wiederkehrend(starte_server, neue_seite):
    server, k, b = _server(starte_server)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    zeile(seite, b["einfach"]).click()
    seite.keyboard.press("Control+k")
    expect(tid(seite, "befehlspalette")).to_be_visible()
    ids = tid(seite, "befehlspalette-liste").locator('[role="option"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    gehe = [x for x in ids if x.startswith("befehl-gehe-")]
    assert m8.gehe_geordnet(gehe) == [f"befehl-gehe-{z}" for z in m8.PALETTE_GEHE]   # ab M32: E-307
    i = ids.index("befehl-gehe-benachrichtigungen")
    assert ids[i + 1:i + 3] == ["befehl-rueckgaengig", "befehl-wiederholen"]
    assert "befehl-gehe-statistik" not in ids
    assert "befehl-gehe-wiederkehrend" not in ids and "befehl-wiederkehrend-warum" not in ids
    texte = tid(seite, "befehlspalette-liste").locator('[role="option"]').evaluate_all(
        "els => els.map(e => e.textContent.trim())")
    assert any(t.startswith("Kontoblatt (") and t.endswith("]") for t in texte), "Kürzel-Einträge im Kontoblatt"
    seite.keyboard.press("Escape")
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    seite.keyboard.press("Control+k")
    texte = tid(seite, "befehlspalette-liste").locator('[role="option"]').evaluate_all(
        "els => els.map(e => e.textContent.trim())")
    assert not any(t.startswith("Kontoblatt (") for t in texte), "außerhalb des Kontoblatts keine Kürzel-Einträge"


# ------------------------------------------------------------------ 37.4 wiederkehrende Buchungen entfernt


def test_wiederkehrendes_aus_der_oberflaeche_entfernt(starte_server, neue_seite):
    server, k, b = _server(starte_server)
    seite = neue_seite(server)
    anfragen: list[str] = []
    seite.on("request", lambda r: anfragen.append(r.url))
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(server.api, k["giro"]))
    zeile(seite, b["einfach"]).click(button="right", modifiers=["Alt"])
    expect(tid(seite, "kontextmenue")).to_be_visible()
    expect(tid(seite, "km-wiederkehrend")).to_have_count(0)
    seite.keyboard.press("Escape")
    assert seite.locator("[data-wiederkehrend]").count() == 0
    oeffnen(seite, server, "/einstellungen", seitenname="einstellungen")
    assert seite.locator('[data-testid^="wk-vorgabe-"], [data-testid^="wk-filter-"]').count() == 0
    anfragen.clear()
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    expect(tid(seite, "erwartet-grund-serie")).to_have_count(0)
    assert not [u for u in anfragen if "serien=ja" in u], "die Seite fragt keine Serien ab"


# ------------------------------------------------------------------ 37.5 Tabs: Kontextmenü


def test_tab_kontextmenue(starte_server, neue_seite):
    server, k, b = _server(starte_server)
    seite = neue_seite(server)
    g, s, leb = (f"/konten/{k[x]}" for x in ("giro", "spar", "leb"))
    oeffnen(seite, server, g, seitenname="konto")
    tab(seite, g).click(button="right")
    m = tid(seite, "kontextmenue")
    expect(m).to_be_visible()
    expect(m).to_have_attribute("aria-label", "Tab „Girokonto“")
    assert m28.menue(seite) == ["km-tab-schliessen", "km-tab-andere", "km-tab-alle"]
    expect(tid(seite, "km-tab-schliessen")).to_have_text("Schließen")
    expect(tid(seite, "km-tab-andere")).to_have_text("Andere Tabs schließen")
    expect(tid(seite, "km-tab-alle")).to_have_text("Alle Tabs schließen")
    expect(tid(seite, "km-tab-andere")).to_have_attribute("aria-disabled", "true")
    seite.keyboard.press("Escape")
    m17.oeffne_konto(seite, k["spar"])
    oeffnen(seite, server, leb, seitenname="konto")
    warte_tabs(seite, [g, s, leb], leb)
    # Schließen wirkt wie ×
    tab(seite, s).click(button="right")
    tid(seite, "km-tab-schliessen").click()
    warte_tabs(seite, [g, leb], leb)
    # Andere: der angeklickte (inaktive) wird aktiv und gezeigt
    m17.fokus_auf_tab(seite, leb)
    seite.keyboard.press("ArrowLeft")          # Tastatur der Tab-Leiste (27.1): Fokus auf den vorigen Tab
    warte(seite, lambda: m17.fokus_tab(seite) == g, text="Fokus auf dem Tab des Girokontos")
    seite.keyboard.press("Shift+F10")
    expect(tid(seite, "kontextmenue")).to_be_visible()
    expect(tid(seite, "kontextmenue")).to_have_attribute("aria-label", "Tab „Girokonto“")
    tid(seite, "km-tab-andere").click()
    warte_tabs(seite, [g], g)
    m17.warte_konto(seite, k["giro"])
    # Alle: Leiste leer, danach die Finanzübersicht
    m17.oeffne_konto(seite, k["spar"])
    tab(seite, s).click(button="right")
    tid(seite, "km-tab-alle").click()
    warte_geladen(seite, "uebersicht")
    warte(seite, lambda: set(pfade(seite)) <= {"/"}, text="alle Tabs geschlossen")
    assert aktive(seite) in ([], ["/"])
    seite.reload()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    warte(seite, lambda: set(pfade(seite)) <= {"/"}, text="gespeicherter Zustand folgt")


def test_tab_kontextmenue_mobil_lange_beruehrung(starte_server, neue_seite):
    server, k, b = _server(starte_server)
    seite = neue_seite(server, "handy")
    g = f"/konten/{k['giro']}"
    oeffnen(seite, server, g, seitenname="konto")
    m17.tabs_aufklappen(seite)
    m8.lange_beruehrung(seite, tab(seite, g))
    expect(tid(seite, "kontextmenue")).to_be_visible()
    expect(tid(seite, "km-tab-schliessen")).to_be_visible()
