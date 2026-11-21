"""Eigener Browsertest zu geplanten Zahlungen mit Wiederholung (D-238). Nur synthetische Daten."""
from __future__ import annotations

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _client(url):
    import httpx
    return httpx.Client(base_url=url, trust_env=False, timeout=60)


def test_geplante_zahlung_mit_wiederholung_anlegen_und_in_der_vorschau_sehen(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        page.goto(url + "/erwartet")
        bereit(page, "erwartet")
        tid(page, "erwartet-neu").click()
        tid(page, "erwartung-haendler").fill("Musterschutz Versicherung")
        tid(page, "erwartung-betrag").fill("48,00")
        tid(page, "erwartung-datum").fill("2024-07-15")       # Mock-Uhr: 30.06.2024
        expect(tid(page, "erwartung-wiederholung-bis")).to_be_hidden()
        tid(page, "erwartung-wiederholung").select_option("monatlich")
        expect(tid(page, "erwartung-wiederholung-bis")).to_be_visible()
        tid(page, "erwartung-wiederholung-bis").fill("2024-08-31")
        tid(page, "erwartung-ok").click()
        expect(tid(page, "erwartet-tabelle")).to_contain_text("Musterschutz Versicherung")
        (e,) = c.get("/api/erwartungen").json()["eintraege"]
        assert e["wiederholung"] == {"rhythmus": "monatlich", "bis": "2024-08-31"} and e["betrag"] == 4800
        marke = tid(page, f"erwartung-wiederholung-{e['id']}")
        expect(marke).to_have_text("↻ monatlich")
        expect(tid(page, f"erwartung-{e['id']}")).to_have_attribute("data-grund", "manuell")
        # Vorschau: beide Fälligkeiten stehen als „Geplant“ in den erwarteten Zahlungen
        page.goto(url + "/berichte?art=vorschau")
        bereit(page, "berichte")
        expect(page.locator("[data-testid^=mb-ereignis-geplant-]")).to_have_count(2)
        expect(tid(page, "mb-ereignisse-tabelle")).to_contain_text("Musterschutz Versicherung")
        # Wiederholung im Dialog wieder zurücknehmen
        page.goto(url + "/erwartet")
        bereit(page, "erwartet")
        tid(page, f"erwartung-menue-{e['id']}").click()
        tid(page, "km-erwartung-bearbeiten").click()
        expect(tid(page, "erwartung-wiederholung")).to_have_value("monatlich")
        tid(page, "erwartung-wiederholung").select_option("keine")
        tid(page, "erwartung-ok").click()
        expect(tid(page, f"erwartung-wiederholung-{e['id']}")).to_have_count(0)
        assert "wiederholung" not in c.get(f"/api/erwartungen/{e['id']}").json()
