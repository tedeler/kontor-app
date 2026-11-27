"""Browser-Rauchtest zu D-314: Das Fenster eines Sicherungspunkts öffnet sofort; der Unterschied zum aktuellen Stand
und die Chronik kommen nach. Solange der Unterschied fehlt, ist „Auf diesen Stand wechseln“ gesperrt."""
from __future__ import annotations

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)
from .test_browser_sicherung_stuendlich import _client, _zwei_punkte

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def test_fenster_oeffnet_vor_dem_vergleich(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        a, _b = _zwei_punkte(_client(url))
        gehalten = []
        page.route("**/vergleich", lambda route: gehalten.append(route))
        page.goto(url + "/sicherung")
        bereit(page, "sicherung")
        tid(page, f"punkt-oeffnen-{a['kennung']}").click()
        # ohne Antwort des Vergleichs: Fenster mit Angaben, Hinweis, Wechseln gesperrt, Chronik geladen
        expect(tid(page, "punkt-dialog")).to_be_visible()
        expect(tid(page, "punkt-angaben")).to_be_visible()
        expect(tid(page, "punkt-wirkung")).to_have_attribute("data-geladen", "nein")
        expect(tid(page, "punkt-wirkung")).to_contain_text("wird ermittelt")
        expect(tid(page, "punkt-wechseln")).to_be_disabled()
        expect(tid(page, "punkt-chronik")).to_have_attribute("data-geladen", "ja")
        for _ in range(100):   # die gehaltene Anfrage abholen (Ereignisse von Playwright abarbeiten)
            if gehalten:
                break
            page.wait_for_timeout(20)
        assert len(gehalten) == 1
        gehalten[0].continue_()
        expect(tid(page, "punkt-wirkung")).to_have_attribute("data-geladen", "ja")
        expect(tid(page, "punkt-wirkung")).to_contain_text("1 Tag entfällt")
        expect(tid(page, "punkt-wechseln")).to_be_enabled()
