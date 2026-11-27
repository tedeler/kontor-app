"""Browser-Rauchtest (D-309): mobil behält die getippte Buchung Grundton und Streifen ihres Status; die Markierung ist
ein Rahmen in der Akzentfarbe. Nur Mock-Modus, synthetische Daten."""

from __future__ import annotations

import pytest

import httpx

from .test_browser import HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)
from .test_browser_tabs import _daten, _get

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-id]'

STIL = """(z) => { const s = getComputedStyle(z), a = getComputedStyle(z, '::after');
  return { hg: s.backgroundColor, bild: s.backgroundImage, rahmen: a.borderTopWidth,
           streifen: s.getPropertyValue('--streifen').trim() }; }"""


def test_markierte_zeile_zeigt_ihren_status(tmp_path, browser):
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
        alle = _get(url + "/api/buchungen", konto_id=giro, pro_seite=200)["eintraege"]
        with httpx.Client(trust_env=False, base_url=url) as c:      # oben in der Liste: je eine Farbe
            for status, teil in (("bestaetigt", alle[0:1]), ("vorlaeufig", alle[1:2])):
                r = c.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [b["id"] for b in teil], "status": status})
                assert r.status_code == 200, r.text
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        zeilen = page.locator(ZEILEN)
        gesehen = {}
        for i in range(zeilen.count()):
            m = zeilen.nth(i).get_attribute("data-markierung")
            gesehen.setdefault("bestaetigt" if m == "abgeglichen" else m, i)   # beide weiß
        assert {"importiert", "vorlaeufig", "bestaetigt"} <= set(gesehen), gesehen
        toene = {}
        for markierung, i in gesehen.items():
            z = zeilen.nth(i)
            z.scroll_into_view_if_needed()
            vorher = z.evaluate(STIL)
            page.wait_for_timeout(450)                      # kein Doppeltipp mit dem vorigen Tippen
            z.tap()
            expect(z).to_have_attribute("data-markiert", "")
            nachher = z.evaluate(STIL)
            assert nachher["hg"] == vorher["hg"], (markierung, vorher, nachher)       # Grundton des Status bleibt
            assert float(nachher["rahmen"].rstrip("px")) >= 3, nachher                # deutlicher Rahmen
            if vorher["streifen"] not in ("", "transparent"):
                assert nachher["streifen"] == vorher["streifen"], (markierung, nachher)
            toene[markierung] = nachher["hg"]
        # verschiedene Status bleiben auch markiert unterscheidbar
        assert len(set(toene.values())) == len(toene), toene
