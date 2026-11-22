"""Browser-Rauchtest zu D-240 (sammel4): unter „Kategorie“ ein Konto wählen – die Buchung wird zur Umbuchung."""

from __future__ import annotations

import sqlite3

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)
from .test_browser_sammel3 import _daten

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _ids(config):
    con = sqlite3.connect(config.aktive_datenbank)
    konten = dict(con.execute("SELECT name, id FROM konto"))
    erste, = con.execute("SELECT b.id FROM buchung b JOIN split s ON s.buchung_id = b.id WHERE s.konto_id = ?"
                         " ORDER BY b.datum LIMIT 1", (konten["Giro"],)).fetchone()
    con.close()
    return konten, erste


def test_konto_in_der_kategorieauswahl_macht_eine_umbuchung(tmp_path, browser):
    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **DESKTOP) as page:
        _daten(config)
        konten, bid = _ids(config)
        page.goto(f"{url}/konten/{konten['Giro']}")
        bereit(page, "konto")
        zeile = page.locator(f'[role=row][data-id="{bid}"]')
        zeile.click(button="right", position={"x": 200, "y": 8})
        tid(page, "km-kategorie").click()
        expect(tid(page, "kategorie-auswahl-konten")).to_be_visible()
        expect(tid(page, f"kategorie-option-{konten['Lebensmittel']}")).to_be_visible()
        expect(tid(page, f"kategorie-option-{konten['Giro']}")).to_have_count(0)      # das eigene Konto fehlt
        # die Suche filtert auch die Konten; ohne Treffer verschwindet die Überschrift
        tid(page, "kategorie-auswahl-suche").fill("Lebens")
        expect(tid(page, "kategorie-auswahl-konten")).to_be_hidden()
        tid(page, "kategorie-auswahl-suche").fill("Spar")
        ziel = tid(page, f"kategorie-option-{konten['Spar']}")
        expect(ziel).to_have_attribute("data-umbuchung", "ja")
        ziel.click()
        expect(zeile.locator(".zelle-kategorie")).to_have_text("Umbuchung → Spar")
        # im Blatt des Zielkontos steht dieselbe Buchung mit der Gegenrichtung
        page.goto(f"{url}/konten/{konten['Spar']}")
        bereit(page, "konto")
        drueben = page.locator(f'[role=row][data-id="{bid}"]')
        expect(drueben.locator(".zelle-kategorie")).to_have_text("Umbuchung ← Giro")
        # umhängen: zurück auf eine Kategorie (das Konto des Blatts bleibt)
        page.goto(f"{url}/konten/{konten['Giro']}")
        bereit(page, "konto")
        zeile = page.locator(f'[role=row][data-id="{bid}"]')
        zeile.click(button="right", position={"x": 200, "y": 8})
        tid(page, "km-kategorie").click()
        tid(page, f"kategorie-option-{konten['Lebensmittel']}").click()
        expect(zeile.locator(".zelle-kategorie")).to_have_text("Lebensmittel")
        con = sqlite3.connect(config.aktive_datenbank)
        assert {r[0] for r in con.execute("SELECT konto_id FROM split WHERE buchung_id = ?", (bid,))} == {
            konten["Giro"], konten["Lebensmittel"]}
        con.close()
