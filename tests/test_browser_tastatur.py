"""Entwicklungstests für das Feature „tastatur“ (D-287): Bereichswechsel mit der Vortaste „w“ und F6.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import re

import pytest

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _get, _tab, _tabs

def _im(page, sel):
    """Der Fokus liegt in diesem Bereich (oder auf ihm selbst)."""
    expect(page.locator(f"{sel}:focus, {sel} :focus")).to_have_count(1)



def test_w_wechselt_die_bereiche_im_kontoblatt(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]')
        zeilen.nth(2).locator('[data-feld="datum"]').click()
        # w zeigt den Hinweis mit den Zielen; Esc bricht ab
        page.keyboard.press("w")
        hinweis = tid(page, "kuerzel-hinweis")
        expect(hinweis).to_have_attribute("data-vortaste", "w")
        expect(hinweis).to_contain_text("Buchungsblatt")
        expect(hinweis).to_contain_text("Einzelheiten")
        page.keyboard.press("Escape")
        expect(hinweis).to_have_count(0)
        # w e: Einzelheiten; das Panel ist als aktiver Bereich markiert
        page.keyboard.press("w")
        page.keyboard.press("e")
        _im(page, '[data-testid="panel-details"]')
        expect(tid(page, "panel-details")).to_have_class("panel bereich-aktiv")
        # w b: zurück auf dieselbe Buchung
        page.keyboard.press("w")
        page.keyboard.press("b")
        expect(zeilen.nth(2)).to_be_focused()
        expect(tid(page, "panel-details")).not_to_have_class("panel bereich-aktiv")
        # Esc in den Einzelheiten führt ebenfalls zurück
        page.keyboard.press("w")
        page.keyboard.press("e")
        _im(page, '[data-testid="panel-details"]')
        page.keyboard.press("Escape")
        expect(zeilen.nth(2)).to_be_focused()
        # eingeklapptes Panel klappt auf (D-292: ohne Kürzel, über den Knopf im Panelkopf)
        tid(page, "panel-einklappen-details").click()
        expect(tid(page, "panel-details")).to_have_attribute("data-eingeklappt", "ja")
        page.keyboard.press("w")
        page.keyboard.press("e")
        expect(tid(page, "panel-details")).to_have_attribute("data-eingeklappt", "nein")
        _im(page, '[data-testid="panel-details"]')
        # w f: Filterausdruck; im Textfeld tippt w ein w; Esc führt zurück in die Liste
        page.keyboard.press("w")
        page.keyboard.press("f")
        _im(page, '[data-testid="ausdruck-filter"]')
        page.keyboard.press("w")
        expect(hinweis).to_have_count(0)
        page.keyboard.press("Backspace")
        page.keyboard.press("Escape")
        expect(zeilen.nth(2)).to_be_focused()
        # die Vortaste f des Kontoblatts behält „f w“ (D-292: diese Woche)
        zeilen.nth(2).locator('[data-feld="datum"]').click()
        page.keyboard.press("f")
        page.keyboard.press("w")
        expect(hinweis).to_have_count(0)
        expect(page).to_have_url(re.compile("diese_woche"))
        # unbelegte zweite Taste wird gemeldet
        page.keyboard.press("w")
        page.keyboard.press("q")
        expect(tid(page, "meldungen")).to_contain_text("„w q“ ist nicht belegt")


def test_w_navigation_tabs_und_f6(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        pfad = f"/konten/{giro}"
        page.goto(url + "/konten")
        bereit(page, "konten")
        page.goto(url + pfad)
        bereit(page, "konto")
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        expect(_tabs(page)).to_have_count(3)
        # w n: Navigation, Pfeile bewegen den Fokus, Enter öffnet
        page.keyboard.press("w")
        page.keyboard.press("n")
        expect(tid(page, "nav-regeln")).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(tid(page, "nav-vorlagen")).to_be_focused()
        page.keyboard.press("Escape")
        _im(page, '[data-testid="hauptbereich"]')
        # w 2: zweiter Tab (Giro), Fokus im Buchungsblatt
        page.keyboard.press("w")
        page.keyboard.press("2")
        expect(_tab(page, pfad)).to_have_attribute("aria-selected", "true")
        _im(page, '[data-testid="buchungsliste"]')
        # w ←, w →, w z
        page.keyboard.press("w")
        page.keyboard.press("ArrowLeft")
        expect(_tab(page, "/konten")).to_have_attribute("aria-selected", "true")
        _im(page, '[data-testid="hauptbereich"]')
        page.keyboard.press("w")
        page.keyboard.press("z")
        expect(_tab(page, pfad)).to_have_attribute("aria-selected", "true")
        _im(page, '[data-testid="hauptbereich"]')
        page.keyboard.press("w")
        page.keyboard.press("ArrowRight")
        expect(_tab(page, "/regeln")).to_have_attribute("aria-selected", "true")
        _im(page, '[data-testid="hauptbereich"]')
        # w t: Tab-Leiste; Pfeil und Enter wechseln
        page.keyboard.press("w")
        page.keyboard.press("t")
        _im(page, '[data-testid="tab-leiste"]')
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("Enter")
        expect(_tab(page, pfad)).to_have_attribute("aria-selected", "true")
        # F6 reihum: Tab-Leiste → Filter → Aktionen (D-292) → Buchungsblatt → Einzelheiten → Navigation; Umschalt+F6 zurück
        _im(page, '[data-testid="tab-leiste"]')
        for ziel in ("ausdruck-filter", "konto-kopf", "buchungsliste", "panel-details", "navigation"):
            page.keyboard.press("F6")
            _im(page, f'[data-testid="{ziel}"]')
        page.keyboard.press("Shift+F6")
        _im(page, '[data-testid="panel-details"]')
        # F6 wirkt auch aus einem Textfeld
        page.keyboard.press("w")
        page.keyboard.press("f")
        _im(page, '[data-testid="ausdruck-filter"]')
        page.keyboard.press("F6")
        _im(page, '[data-testid="konto-kopf"]')
        # w x schließt den Tab
        page.keyboard.press("w")
        page.keyboard.press("x")
        expect(_tabs(page)).to_have_count(2)
        expect(_tab(page, pfad)).to_have_count(0)


def test_hilfe_und_befehlspalette_nennen_die_bereiche(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        page.locator('[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]').first.locator('[data-feld="datum"]').click()
        page.keyboard.press("h")   # D-292: h statt ?
        hilfe = tid(page, "tastatur-hilfe-bereiche")
        expect(hilfe).to_contain_text("w b")
        expect(hilfe).to_contain_text("Buchungsblatt")
        expect(hilfe).to_contain_text("w 1 … 9")
        page.keyboard.press("Escape")
        page.keyboard.press("Control+k")
        tid(page, "befehlspalette-eingabe").fill("Bereich: Einzel")
        page.keyboard.press("Enter")
        _im(page, '[data-testid="panel-details"]')


def _viele(basis, anzahl):
    import datetime as dt

    from kontor.config import KontorConfig
    from kontor.importer.kmymoney import importiere_kmy

    from .conftest import GIRO, kmy, transaktion

    start = dt.date(2023, 1, 1)
    t = "".join(transaktion(f"T{i}", (start + dt.timedelta(days=i)).isoformat(), ("A1", f"-{i + 1}00/100"),
                            ("A2", f"{i + 1}00/100"), memo=f"Einkauf {i}") for i in range(anzahl))
    config = KontorConfig(datenbank=basis / "kontor.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 30))
    assert importiere_kmy(config, kmy(GIRO, transaktionen=t)).erfolgreich


def _erste_sichtbar(page):
    """Die fokussierte Zeile liegt ganz unter dem klebenden Spaltenkopf und im sichtbaren Teil der Liste."""
    page.wait_for_timeout(150)
    zeile = page.locator('[data-testid="buchungsliste"] [role="row"]:focus').bounding_box()
    kopf = page.locator('[data-testid="buchungsliste"] .liste-kopf').bounding_box()
    spalte = page.locator(".listen-spalte").bounding_box()
    assert zeile["y"] >= kopf["y"] + kopf["height"] - 1, (zeile, kopf)
    assert zeile["y"] + zeile["height"] <= spalte["y"] + spalte["height"] + 1, (zeile, spalte)


@pytest.mark.parametrize("anzahl", [40, 700])
def test_pfeil_nach_oben_zeigt_die_erste_buchung_unter_dem_spaltenkopf(tmp_path, browser, anzahl):  # noqa: F811
    """Mit den Pfeiltasten bis zur ersten Buchung: sie verschwindet nicht hinter dem Spaltenkopf (kurze Liste und
    Liste mit Fenstertechnik)."""
    _viele(tmp_path, anzahl)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, viewport={"width": 1280, "height": 600}) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]')
        zeilen.nth(1).locator('[data-feld="datum"]').click()
        for _i in range(25):
            page.keyboard.press("ArrowDown")
        for _i in range(26):
            page.keyboard.press("ArrowUp")
            if _i % 5 == 0:
                _erste_sichtbar(page)
        _erste_sichtbar(page)
        expect(zeilen.first).to_be_focused()
        # auch mit Bild↑ und Pos1
        page.keyboard.press("End")
        page.keyboard.press("PageUp")
        _erste_sichtbar(page)
        page.keyboard.press("Home")
        _erste_sichtbar(page)
        expect(zeilen.first).to_be_focused()


def test_rollen_in_der_befehlspalette_sperrt_die_lange_beruehrung_nicht(tmp_path, browser):  # noqa: F811
    """D-291: Wer ein Konto über die Befehlspalette öffnet (deren Trefferliste rollt) und gleich danach lange auf
    eine Buchung drückt, bekommt das Kontextmenü."""
    from .test_browser import HANDY

    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        tid(page, "befehlspalette-knopf").click()
        for _i in range(18):
            page.keyboard.press("ArrowDown")           # die Trefferliste rollt
        page.keyboard.press("Escape")
        expect(tid(page, "befehlspalette")).to_have_count(0)
        zeile = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]').nth(1)
        box = zeile.bounding_box()
        cdp = page.context.new_cdp_session(page)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [
            {"x": box["x"] + 60, "y": box["y"] + box["height"] / 2}]})
        page.wait_for_timeout(700)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(tid(page, "km-auswahl")).to_be_visible()
