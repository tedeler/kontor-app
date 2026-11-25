"""Browser-Rauchtest (D-276): Nach einem Verbindungsabbruch findet die Oberfläche von selbst zurück.

Nachgestellt wird das Handy, dessen Browser im Hintergrund war: Anfragen an den Server scheitern, das Gerät selbst
bleibt „online“ (`navigator.onLine`), das Ereignis `online` kommt also nie. Nur Mock-Modus, synthetische Daten."""

from __future__ import annotations

import pytest

from .test_browser import HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def test_rueckkehr_ohne_online_ereignis(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/konten")
        bereit(page, "konten")
        abbruch = lambda route: route.abort("failed")  # noqa: E731
        # 1. Sichtbare Seite: eine Anfrage scheitert, danach ist der Server wieder da – die Seite lädt ohne Zutun.
        page.route("**/api/**", abbruch)
        page.goto(url + "/kategorien")
        expect(tid(page, "offline-hinweis")).to_be_visible()
        assert page.evaluate("navigator.onLine")
        page.unroute("**/api/**", abbruch)
        expect(tid(page, "offline-hinweis")).to_be_hidden()
        bereit(page, "kategorien")
        # 2. Rückkehr aus dem Hintergrund: Die Prüfung läuft sofort, nicht erst nach der gewachsenen Wartezeit.
        page.route("**/api/**", abbruch)
        page.reload()
        expect(tid(page, "offline-hinweis")).to_be_visible()
        page.wait_for_timeout(3500)          # Wartezeit ist auf mehrere Sekunden gewachsen
        page.unroute("**/api/**", abbruch)
        page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
        expect(tid(page, "offline-hinweis")).to_be_hidden(timeout=1500)
        bereit(page, "kategorien")
