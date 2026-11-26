"""Entwicklungstests für das Feature „kategorie-tastatur“ (D-296): Kategorie-Auswahl im Kontoblatt nur mit der
Tastatur. Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _get

ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]'
GEWAEHLT = '[data-testid="kategorie-auswahl-liste"] [role="option"][aria-selected="true"]'


def _kategorien(url):
    with httpx.Client(trust_env=False) as c:
        for name in ("Wohnen", "Mobilität", "Freizeit", "Versicherungen"):
            assert c.post(url + "/api/konten", json={"name": name, "art": "aufwand"}).status_code == 201


def _start(page, url):
    giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
    page.goto(f"{url}/konten/{giro}")
    bereit(page, "konto")
    zeile = page.locator(ZEILEN).nth(2)
    zeile.locator('[data-feld="datum"]').click()
    return zeile


def _warte_kategorie(page, url, bid, soll):
    for _ in range(60):
        if _kategorie_von(url, bid) == soll:
            return
        page.wait_for_timeout(100)
    assert _kategorie_von(url, bid) == soll


def _kategorie_von(url, bid):
    with httpx.Client(trust_env=False) as c:
        return c.get(f"{url}/api/buchungen/{bid}").json()["kategorie_id"]


def test_waehlen_nur_mit_der_tastatur(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        _kategorien(url)
        zeile = _start(page, url)
        bid = int(zeile.get_attribute("data-id"))
        page.keyboard.press("k")
        expect(tid(page, "kategorie-auswahl-suche")).to_be_focused()
        expect(tid(page, "kategorie-auswahl-tasten")).to_contain_text("Strg+Enter anlegen")
        optionen = page.locator('[data-testid="kategorie-auswahl-liste"] [role="option"]:not([hidden])')
        n = optionen.count()
        assert n >= 5
        # ↑ ohne Markierung: letzte; ↓ danach umlaufend: erste
        page.keyboard.press("ArrowUp")
        expect(optionen.nth(n - 1)).to_have_attribute("aria-selected", "true")
        page.keyboard.press("ArrowDown")
        expect(optionen.first).to_have_attribute("aria-selected", "true")
        page.keyboard.press("Control+End")
        expect(optionen.nth(n - 1)).to_have_attribute("aria-selected", "true")
        page.keyboard.press("Control+Home")
        expect(optionen.first).to_have_attribute("aria-selected", "true")
        page.keyboard.press("PageDown")
        expect(page.locator(GEWAEHLT)).to_have_count(1)
        # Suchtext markiert den ersten Treffer; Enter übernimmt ihn (auch bei mehreren Treffern)
        page.keyboard.type("e")
        erster = optionen.first
        expect(erster).to_have_attribute("aria-selected", "true")
        assert optionen.count() > 1
        ziel = int(erster.get_attribute("data-testid").rsplit("-", 1)[1])
        page.keyboard.press("Enter")
        expect(tid(page, "kategorie-auswahl")).to_have_count(0)
        expect(page.locator(f'[data-testid="buchung-{bid}"]')).to_be_focused()
        _warte_kategorie(page, url, bid, ziel)


def test_neue_kategorie_nur_mit_der_tastatur(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        _kategorien(url)
        zeile = _start(page, url)
        bid = int(zeile.get_attribute("data-id"))
        page.keyboard.press("k")
        page.keyboard.type("Wohn")
        # Strg+Enter öffnet das Formular trotz Treffer, mit dem Suchtext als Name
        page.keyboard.press("Control+Enter")
        expect(tid(page, "kategorie-neu-name")).to_be_focused()
        expect(tid(page, "kategorie-neu-name")).to_have_value("Wohn")
        # Esc führt zurück zur Auswahl, das Fenster bleibt offen
        page.keyboard.press("Escape")
        expect(tid(page, "kategorie-auswahl")).to_be_visible()
        expect(tid(page, "kategorie-auswahl-suche")).to_be_focused()
        expect(tid(page, "kategorie-neu")).to_be_hidden()
        # wieder ins Formular, Name ändern, mit Tab zur übergeordneten Kategorie, Pfeil wählt, Enter legt an
        page.keyboard.press("Control+Enter")
        page.keyboard.press("Control+a")
        page.keyboard.type("Garten")
        page.keyboard.press("Tab")
        expect(tid(page, "kategorie-neu-art")).to_be_focused()
        page.keyboard.press("Tab")
        expect(tid(page, "kategorie-neu-eltern")).to_be_focused()
        page.keyboard.press("ArrowDown")
        eltern = int(tid(page, "kategorie-neu-eltern").input_value())
        page.keyboard.press("Enter")
        expect(tid(page, "kategorie-auswahl")).to_have_count(0)
        expect(page.locator(f'[data-testid="buchung-{bid}"]')).to_be_focused()
        konten = {k["name"]: k for k in _get(url + "/api/konten")}
        assert konten["Garten"]["eltern_id"] == eltern
        _warte_kategorie(page, url, bid, konten["Garten"]["id"])


def test_esc_bricht_ab_und_fokus_kehrt_zurueck(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        zeile = _start(page, url)
        bid = int(zeile.get_attribute("data-id"))
        vorher = _kategorie_von(url, bid)
        page.keyboard.press("k")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Escape")
        expect(tid(page, "kategorie-auswahl")).to_have_count(0)
        expect(page.locator(f'[data-testid="buchung-{bid}"]')).to_be_focused()
        assert _kategorie_von(url, bid) == vorher
