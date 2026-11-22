"""Browser-Rauchtest des Features „postfach-loeschen“ (D-244): Knopf mit Rückfrage auf der Postfach-Seite."""

from __future__ import annotations

import httpx
import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def test_postfach_loeschen_mit_rueckfrage(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        pid = c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).json()["id"]
        assert c.post("/api/mail/abruf").status_code == 200
        page.goto(url + f"/mail/postfaecher/{pid}")
        tid(page, "postfach-loeschen").click()
        expect(tid(page, "bestaetigen-dialog")).to_be_visible()
        expect(tid(page, "bestaetigen-dialog")).to_contain_text("gespeicherte Mail")
        tid(page, "bestaetigen-nein").click()
        assert c.get(f"/api/mail/postfaecher/{pid}").status_code == 200
        tid(page, "postfach-loeschen").click()
        tid(page, "bestaetigen-ja").click()
        page.wait_for_url("**/einstellungen?bereich=mail")
        bereit(page, "einstellungen")
        expect(tid(page, "postfaecher")).not_to_contain_text("haushalt.eins@example.invalid")
        assert c.get(f"/api/mail/postfaecher/{pid}").status_code == 404
