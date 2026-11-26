"""M8: Tastaturkürzel und Befehlspalette (oberflaeche.md 12; K 5)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import oeffnen, tid, warte_geladen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


@pytest.fixture
def bereit(starte_server, neue_seite):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    seite = neue_seite(server)
    oeffnen(seite, server, "/einstellungen", seitenname="einstellungen")
    return server, seite, erw, ids


def _treffer(seite) -> list[str]:
    return seite.locator('[data-testid="befehlspalette-liste"] [role="option"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")


def _palette(seite, kuerzel="Control+k"):
    seite.keyboard.press(kuerzel)
    p = tid(seite, "befehlspalette")
    expect(p).to_be_visible()
    expect(p).to_have_attribute("role", "dialog")
    e = tid(seite, "befehlspalette-eingabe")
    expect(e).to_be_focused()
    expect(e).to_have_attribute("role", "combobox")
    expect(tid(seite, "befehlspalette-liste")).to_have_attribute("role", "listbox")
    return p, e


@pytest.mark.kern
def test_palette_umlaute_und_navigation(bereit):
    server, seite, erw, ids = bereit
    marke = seite.evaluate("() => (window.__m8marke = Math.random())")
    p, e = _palette(seite)
    seite.keyboard.type("finanzueb")
    expect(seite.locator('[data-testid="befehlspalette-liste"] [role="option"]')).to_have_count(1)
    assert _treffer(seite) == ["befehl-gehe-uebersicht"]
    expect(tid(seite, "befehl-gehe-uebersicht")).to_have_text("Gehe zu: Finanzübersicht")
    expect(tid(seite, "befehl-gehe-uebersicht")).to_have_attribute("aria-selected", "true")
    e.fill("ÜBERSICHT")                                   # Groß-/Kleinschreibung und Umlaut egal
    expect(tid(seite, "befehl-gehe-uebersicht")).to_be_visible()
    seite.keyboard.press("Enter")
    expect(p).to_be_hidden()
    warte_geladen(seite, "uebersicht")
    assert seite.evaluate("() => window.__m8marke") == marke, "Navigation ohne Neuladen (oberflaeche.md 1)"
    assert seite.url == server.url + "/"


@pytest.mark.kern
def test_palette_woerter_pfeile_und_konten(bereit):
    server, seite, erw, ids = bereit
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    p, e = _palette(seite)
    seite.keyboard.type("gehe kred")
    assert _treffer(seite) == ["befehl-gehe-kredite"]
    e.fill("gehe zu")
    alle = _treffer(seite)
    # M28 (oberflaeche.md 37.2, E-254): „Gehe zu“ in der neuen Reihenfolge, ohne gehe-wiederkehrend
    gehe = [x for x in alle if x.startswith("befehl-gehe-")]
    # ab M32 (41.1, E-307): Tags und Konfiguration mit freier Stelle, ohne Statistik
    assert m8.gehe_geordnet(gehe) == [f"befehl-gehe-{z}" for z in m8.PALETTE_GEHE], "feste Reihenfolge der Tabelle"
    assert alle[:len(gehe)] == gehe
    seite.keyboard.press("ArrowDown")
    seite.keyboard.press("ArrowDown")
    expect(tid(seite, alle[2])).to_have_attribute("aria-selected", "true")
    aktiv = tid(seite, alle[2]).get_attribute("id")
    assert aktiv and e.get_attribute("aria-activedescendant") == aktiv
    seite.keyboard.press("ArrowUp")
    expect(tid(seite, alle[1])).to_have_attribute("aria-selected", "true")
    e.fill("konto öffnen giro")
    assert _treffer(seite) == [f"befehl-konto-{giro}"]
    expect(tid(seite, f"befehl-konto-{giro}")).to_have_text("Konto öffnen: Girokonto")
    tid(seite, f"befehl-konto-{giro}").click()
    warte_geladen(seite, "konto")
    assert seite.url == f"{server.url}/konten/{giro}"


@pytest.mark.kern
def test_palette_konten_nur_offene_bestandskonten(bereit):
    server, seite, erw, ids = bereit
    _palette(seite)
    seite.keyboard.type("konto öffnen")
    namen = sorted(k["name"] for k in server.api.konten()
                   if k["art"] in ("girokonto", "sparkonto", "kreditkonto") and not k["geschlossen"])
    erwartet = [f"befehl-konto-{next(k['id'] for k in server.api.konten() if k['name'] == n)}"
                for n in sorted(namen, key=lambda n: n.casefold())]
    assert _treffer(seite) == erwartet
    assert f"befehl-konto-{ids.konto[erw['m8']['konten']['sparbuch_geschlossen']]}" not in _treffer(seite)


@pytest.mark.kern
def test_palette_esc_und_fokus_zurueck(bereit):
    server, seite, erw, ids = bereit
    tid(seite, "befehlspalette-knopf").click()
    expect(tid(seite, "befehlspalette")).to_be_visible()
    seite.keyboard.press("Escape")
    expect(tid(seite, "befehlspalette")).to_be_hidden()
    expect(tid(seite, "befehlspalette-knopf")).to_be_focused()
    _palette(seite, "Control+Shift+P")
    seite.keyboard.press("Escape")
    expect(tid(seite, "befehlspalette")).to_be_hidden()
    assert seite.url.endswith("/einstellungen")


@pytest.mark.kern
def test_alt_ziffern_und_schraegstrich(bereit):
    server, seite, erw, ids = bereit
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    for n, (ziel, pfad) in enumerate(m8.ALT_ZIELE, start=1):   # M28 (37.2, E-254): Alt+1 … Alt+7
        seite.keyboard.press(f"Alt+{n}")
        warte_geladen(seite, ziel)
        assert seite.url == server.url + pfad, (n, seite.url)
    seite.keyboard.press("Alt+8")   # ohne Wirkung
    seite.wait_for_timeout(300)     # Zeitraum, in dem eine Navigation einträte
    assert seite.url == server.url + "/einstellungen"
    seite.keyboard.press("w")   # D-292: w s statt /
    seite.keyboard.press("s")
    expect(tid(seite, "suche-feld")).to_be_focused()
    # im Suchfeld wirken Einbuchstaben- und Alt-Kürzel nicht
    seite.keyboard.press("Alt+1")
    seite.keyboard.type("/")
    expect(tid(seite, "suche-feld")).to_have_value("/")
    assert seite.url.endswith("/einstellungen")


def test_suche_und_tastaturhilfe(bereit):
    server, seite, erw, ids = bereit
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.keyboard.press("h")   # D-292: h statt ?
    hilfe = tid(seite, "tastatur-hilfe")
    expect(hilfe).to_be_visible()
    expect(hilfe).to_have_attribute("role", "dialog")
    expect(hilfe).to_contain_text("Strg+K")
    seite.keyboard.press("Escape")
    expect(hilfe).to_be_hidden()
    tid(seite, "suche-feld").fill("Bäckerei")
    tid(seite, "suche-feld").press("Enter")
    warte_geladen(seite, "suche")
    assert "/suche?q=" in seite.url
    erg = server.api.get("/api/suche", params={"q": "Bäckerei"}, erwartet=200).daten
    expect(tid(seite, "suche-anzahl")).to_have_attribute("data-anzahl", str(erg["buchungen_gesamt"]))
    for b in erg["buchungen"][:5]:
        expect(tid(seite, f"buchung-{b['id']}")).to_be_visible()
    for e in erg["empfaenger"]:
        expect(tid(seite, f"treffer-empfaenger-{e['id']}")).to_be_visible()


def test_entf_loescht_auswahl_nach_rueckfrage(starte_server, neue_seite):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    r = m8.rest_liste(server.api, giro)
    m8.warte_liste(seite, r)
    m8.zeile(seite, r[0]).locator('[data-feld="betrag"]').click()
    seite.keyboard.press("Shift+ArrowDown")
    seite.keyboard.press("Delete")
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    seite.keyboard.press("Escape")
    expect(tid(seite, "bestaetigen-dialog")).to_be_hidden()
    assert server.api.get(f"/api/buchungen/{r[0]}").status_code == 200
    seite.keyboard.press("Delete")
    tid(seite, "bestaetigen-ja").click()
    m8.warte_bis(lambda: all(server.api.get(f"/api/buchungen/{b}").status_code == 404 for b in r[:2]))


def test_enter_zeigt_details(starte_server, neue_seite):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    split_id = ids.buchung[erw["m8"]["split_buchung"]]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    m8.zeile(seite, split_id).locator('[data-feld="datum"]').click()
    seite.keyboard.press("Enter")
    details = tid(seite, "panel-details")
    for s in server.api.buchung_lesen(split_id)["splits"]:
        el = details.get_by_test_id(f"details-split-{s['id']}")
        expect(el).to_be_visible()
        wert = el.evaluate("e => e.matches('[data-betrag]') ? e.dataset.betrag "
                           ": e.querySelector('[data-betrag]')?.dataset.betrag")
        assert wert == str(s["betrag"]), (s, wert)
