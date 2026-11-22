"""Browser-Rauchtest des Features „mail-fortschritt“ (D-252): Abruf mit Fortschritt, alle Kopfzeilen neu abrufen."""

from __future__ import annotations

import httpx
import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def test_abruf_und_alle_koepfe(tmp_path, browser):
    with server(tmp_path, mail_nur_koepfe=True) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        assert c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
        page.goto(url + "/mail")
        bereit(page, "mail")
        expect(tid(page, "mail-alle-koepfe")).to_be_visible()
        tid(page, "mail-abrufen").click()
        expect(tid(page, "mail-stand")).to_contain_text("Abruf beendet", timeout=20000)
        expect(tid(page, "mail-abrufen")).to_be_enabled()
        expect(tid(page, "mail-fortschritt")).to_be_hidden()
        tid(page, "mail-alle-koepfe").click()
        expect(tid(page, "bestaetigen-dialog")).to_contain_text("Kopfzeilen aller Mails")
        tid(page, "bestaetigen-ja").click()
        expect(tid(page, "mail-stand")).to_contain_text("Abruf beendet", timeout=20000)
        st = c.get("/api/mail/abruf/stand").json()
        assert st["alle_koepfe"] is True and st["fehler"] is None


def test_ohne_kopfabruf_kein_knopf(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/mail")
        bereit(page, "mail")
        expect(tid(page, "mail-abrufen")).to_be_visible()
        expect(tid(page, "mail-alle-koepfe")).to_be_hidden()
