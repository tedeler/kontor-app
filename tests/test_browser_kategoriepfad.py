"""Entwicklungstest zum Fehler „Kategoriepfad im Baukasten“ (D-301): Der Filter-Baukasten schreibt eine
Unterkategorie als `kategorie == "Versicherungen:PKV"`, der Ausdruck ist gültig und filtert. Ein Ausdruck mit dem
Anzeigetrenner „›“ (alte Lesezeichen) gilt ebenso und erscheint im Baukasten.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import urllib.parse

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401

ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-id]'


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        giro = c.post(url + "/api/konten", json={"name": "Giro KP", "art": "girokonto"}).json()["id"]
        oben = c.post(url + "/api/konten", json={"name": "Versicherungen", "art": "aufwand"}).json()["id"]
        pkv = c.post(url + "/api/konten", json={"name": "PKV", "art": "aufwand", "eltern_id": oben}).json()["id"]
        sonst = c.post(url + "/api/konten", json={"name": "Sonstiges KP", "art": "aufwand"}).json()["id"]
        for i, kat in enumerate((pkv, sonst, sonst), start=1):
            assert c.post(url + "/api/buchungen", json={
                "datum": f"2024-02-0{i}", "verwendungszweck": f"Posten {i}",
                "splits": [{"konto_id": giro, "betrag": -1000 * i}, {"konto_id": kat, "betrag": 1000 * i}]}).status_code == 201
    return giro


def test_baukasten_mit_unterkategorie(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = _welt(url)
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        expect(page.locator(ZEILEN)).to_have_count(3)
        tid(page, "filter-baukasten-umschalten").click()
        tid(page, "bk-0-feld").select_option(label="Kategorie")
        tid(page, "bk-0-op").select_option(label="ist")
        tid(page, "bk-0-wert").select_option(label="Versicherungen › PKV")      # Anzeige bleibt mit „›“
        expect(tid(page, "filter-ausdruck")).to_have_value('kategorie == "Versicherungen:PKV"')
        expect(tid(page, "filter-ausdruck-status")).to_have_attribute("data-status", "ok")
        expect(page.locator(ZEILEN)).to_have_count(1)

        # altes Lesezeichen mit dem Anzeigetrenner
        page.goto(f"{url}/konten/{giro}?filter=" + urllib.parse.quote('kategorie == "Versicherungen › PKV"'))
        bereit(page, "konto")
        expect(page.locator(ZEILEN)).to_have_count(1)
        expect(tid(page, "filter-ausdruck-status")).to_have_attribute("data-status", "ok")
        tid(page, "filter-baukasten-umschalten").click()
        expect(tid(page, "bk-0-wert")).to_have_value("Versicherungen:PKV")
