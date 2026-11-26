"""Entwicklungstests für das Feature „markierung-nachruecken“ (D-299): Fällt die markierte Buchung durch eine
Änderung aus der gefilterten Liste, ist danach die Buchung direkt darunter markiert (am Ende die darüber).
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import urllib.parse

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401

ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]'
GEWAEHLT = '[data-testid="buchungsliste"] [role="row"][aria-selected="true"]'


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        giro = c.post(url + "/api/konten", json={"name": "Giro NR", "art": "girokonto"}).json()["id"]
        unklar = c.post(url + "/api/konten", json={"name": "Unklar NR", "art": "aufwand"}).json()["id"]
        assert c.post(url + "/api/konten", json={"name": "Erledigt NR", "art": "aufwand"}).status_code == 201
        ids = []
        for i in range(1, 6):
            r = c.post(url + "/api/buchungen", json={"datum": f"2024-03-{i:02d}", "verwendungszweck": f"Posten {i}",
                                                    "splits": [{"konto_id": giro, "betrag": -100 * i},
                                                               {"konto_id": unklar, "betrag": 100 * i}]})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
    return giro, ids


def _oeffnen(page, url, giro):
    page.goto(f"{url}/konten/{giro}?filter=" + urllib.parse.quote('kategorie == "Unklar NR"'))
    bereit(page, "konto")
    expect(page.locator(ZEILEN)).to_have_count(5)


def _wegsortieren(page, bid):
    """Kategorie der Buchung mit der Tastatur auf „Erledigt NR“ setzen: Sie fällt aus dem Filter."""
    tid(page, f"buchung-{bid}").locator('[data-feld="datum"]').click()
    page.keyboard.press("k")
    tid(page, "kategorie-auswahl-suche").fill("Erledigt NR")
    page.keyboard.press("Enter")
    expect(tid(page, f"buchung-{bid}")).to_have_count(0)
    expect(tid(page, "seite-konto")).to_have_attribute("data-ausstehend", "0")


def _reihenfolge(page):
    return [int(z.get_attribute("data-id")) for z in page.locator(ZEILEN).all()]


def test_naechste_buchung_rueckt_nach(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro, _ids = _welt(url)
        _oeffnen(page, url, giro)
        vorher = _reihenfolge(page)
        _wegsortieren(page, vorher[1])
        darunter = vorher[2]
        expect(page.locator(GEWAEHLT)).to_have_count(1)
        expect(tid(page, f"buchung-{darunter}")).to_have_attribute("aria-selected", "true")
        expect(tid(page, f"buchung-{darunter}")).to_be_focused()
        # gleich weiter mit der Tastatur: die nachgerückte Buchung ist das Ziel
        page.keyboard.press("k")
        tid(page, "kategorie-auswahl-suche").fill("Erledigt NR")
        page.keyboard.press("Enter")
        expect(tid(page, f"buchung-{darunter}")).to_have_count(0)
        expect(tid(page, f"buchung-{vorher[3]}")).to_have_attribute("aria-selected", "true")


def test_am_ende_rueckt_die_buchung_darueber_nach(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro, _ids = _welt(url)
        _oeffnen(page, url, giro)
        vorher = _reihenfolge(page)
        _wegsortieren(page, vorher[-1])
        expect(tid(page, f"buchung-{vorher[-2]}")).to_have_attribute("aria-selected", "true")
        expect(page.locator(GEWAEHLT)).to_have_count(1)


def test_mehrere_markierte_buchungen(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro, _ids = _welt(url)
        _oeffnen(page, url, giro)
        vorher = _reihenfolge(page)
        tid(page, f"buchung-{vorher[0]}").locator('[data-feld="datum"]').click()
        page.keyboard.press("Shift+ArrowDown")
        expect(page.locator(GEWAEHLT)).to_have_count(2)
        page.keyboard.press("k")
        tid(page, "kategorie-auswahl-suche").fill("Erledigt NR")
        page.keyboard.press("Enter")
        expect(page.locator(ZEILEN)).to_have_count(3)
        expect(tid(page, "seite-konto")).to_have_attribute("data-ausstehend", "0")
        # die Buchung unter der untersten markierten
        expect(page.locator(GEWAEHLT)).to_have_count(1)
        expect(tid(page, f"buchung-{vorher[2]}")).to_have_attribute("aria-selected", "true")

