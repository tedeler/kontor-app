"""Entwicklungstest für D-297: Schalter „Bestätigung fehlt“ im Kontoblatt (rote und gelbe Buchungen)."""

from __future__ import annotations

import re

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _daten, _get

ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]'


def _farben(page):
    return {z.get_attribute("data-markierung") for z in page.locator(ZEILEN).all()}


def test_schalter_und_kuerzel_zeigen_nur_rote_und_gelbe_buchungen(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        alle = _get(url + "/api/buchungen", konto_id=giro, pro_seite=200)["eintraege"]
        with httpx.Client(trust_env=False, base_url=url) as c:
            for status, teil in (("bestaetigt", alle[:8]), ("vorlaeufig", alle[8:12])):
                r = c.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [b["id"] for b in teil], "status": status})
                assert r.status_code == 200, r.text
        offen = len(alle) - 8
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        assert _farben(page) == {"importiert", "vorlaeufig", "bestaetigt"}
        schalter = tid(page, "filter-unbestaetigt")
        expect(schalter).to_have_attribute("aria-pressed", "false")
        # Schalter: nur Rot und Gelb
        schalter.click()
        expect(schalter).to_have_attribute("aria-pressed", "true")
        expect(page.locator(ZEILEN)).to_have_count(offen)
        assert _farben(page) == {"importiert", "vorlaeufig"}
        expect(tid(page, "filter-ausdruck")).to_have_value("unbestätigt")
        expect(tid(page, "filter-zusammenfassung")).to_contain_text(f"{offen} Buchungen")
        # ein Zeitraum kommt dazu, der Teil bleibt
        tid(page, "filter-schnell-dieses_jahr").click()
        expect(tid(page, "filter-ausdruck")).to_have_value(re.compile(r"^unbestätigt and datum in dieses_jahr$"))
        expect(schalter).to_have_attribute("aria-pressed", "true")
        # f o schaltet aus, der Zeitraum bleibt
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        page.keyboard.press("f")
        page.keyboard.press("o")
        expect(tid(page, "filter-ausdruck")).to_have_value("datum in dieses_jahr")
        expect(schalter).to_have_attribute("aria-pressed", "false")
        # von Hand eingegeben gilt der Schalter ebenfalls als ein
        feld = tid(page, "filter-ausdruck")
        feld.fill('status == "bestaetigt" or status == "vorlaeufig"')
        feld.press("Enter")
        expect(page.locator(ZEILEN)).to_have_count(12)
        expect(schalter).to_have_attribute("aria-pressed", "false")
        # Ausdruck mit „oder“: der Schalter klammert und nimmt seinen Teil auch wieder heraus
        schalter.click()
        expect(feld).to_have_value('(status == "bestaetigt" or status == "vorlaeufig") and unbestätigt')
        expect(page.locator(ZEILEN)).to_have_count(4)
        assert _farben(page) == {"vorlaeufig"}
        expect(schalter).to_have_attribute("aria-pressed", "true")
        schalter.click()
        expect(feld).to_have_value('status == "bestaetigt" or status == "vorlaeufig"')
        expect(page.locator(ZEILEN)).to_have_count(12)
        # die Tastaturhilfe nennt das Kürzel
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        page.keyboard.press("h")
        expect(tid(page, "tastatur-hilfe")).to_contain_text("Bestätigung fehlt")
