"""Browser-Rauchtest zur Begründung „wiederkehrend“ (D-109): versteckter Kontextmenüeintrag mit Alt und Eintrag in
der Befehlspalette. Synthetische Daten, eigener Server auf einem freien Loopback-Port."""

from __future__ import annotations

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401


def _daten(url):
    c = httpx.Client(base_url=url)
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Abo", "art": "aufwand"}).json()["id"]
    e = c.post("/api/empfaenger", json={"name": "Abo AG (fiktiv)"}).json()["id"]
    for t in ("2024-03-15", "2024-04-15", "2024-05-13", "2024-05-15", "2024-06-15"):
        r = c.post("/api/buchungen", json={"datum": t, "empfaenger_id": e, "splits": [
            {"konto_id": g, "betrag": -999}, {"konto_id": kat, "betrag": 999}]})
        assert r.status_code == 201, r.text
    return g


def test_begruendung_ueber_alt_kontextmenue_und_palette(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        g = _daten(url)
        page.goto(f"{url}/konten/{g}")
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        expect(zeilen).to_have_count(5)
        # ohne Alt kein Eintrag
        zeilen.nth(0).click(button="right")
        expect(tid(page, "km-kategorie")).to_be_visible()
        expect(tid(page, "km-wiederkehrend")).to_have_count(0)
        page.keyboard.press("Escape")
        # mit Alt: Glied der Serie (jüngste Buchung)
        zeilen.nth(0).click(button="right", modifiers=["Alt"])
        tid(page, "km-wiederkehrend").click()
        d = tid(page, "wiederkehrend-begruendung")
        expect(d).to_be_visible()
        expect(tid(page, "wk-urteil")).to_have_attribute("data-urteil", "wiederkehrend")
        expect(d.locator('[data-testid="wk-schritt"][data-ergebnis="verbunden"]')).to_have_count(3)
        tid(page, "wk-schliessen").click()
        # zusätzliche Zahlung am 13.05. über die Befehlspalette
        zeilen.locator('[data-feld="datum"]', has_text="13.05.2024").click()
        page.keyboard.press("Control+k")
        page.keyboard.type("warum")
        page.keyboard.press("Enter")
        expect(tid(page, "wk-urteil")).to_have_attribute("data-urteil", "nicht_wiederkehrend")
        expect(tid(page, "wk-eintrag")).to_have_attribute("data-urteil", "zusaetzlich")
        expect(page.locator(".wk-betroffen")).to_have_count(1)
