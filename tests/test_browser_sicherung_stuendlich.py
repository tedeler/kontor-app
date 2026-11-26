"""Eigene Browsertests zu den Sicherungspunkten (D-302): Seite /sicherung mit Stand, Speicher und Zeitleiste, Fenster
eines Punkts, Wechsel zurück und vorwärts, Handy ohne seitliches Rollen. Nur synthetische Daten."""
from __future__ import annotations

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _client(url):
    import httpx
    return httpx.Client(base_url=url, trust_env=False, timeout=60)


def _zwei_punkte(c):
    a = c.post("/api/sicherung/punkte", json={"name": "Ausgangsstand"}).json()
    assert c.post("/api/tags", json={"name": "Urlaub"}).status_code == 201
    b = c.post("/api/sicherung/punkte", json={}).json()
    assert b["neu"] is True
    return a, b


def test_seite_zeigt_punkte_und_wechselt_zurueck_und_vorwaerts(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        a, b = _zwei_punkte(c)
        page.goto(url + "/sicherung")
        bereit(page, "sicherung")
        expect(tid(page, "sicherung-stand")).to_have_attribute("data-zustand", "ok")
        expect(tid(page, "sicherung-stand")).to_contain_text("unverändert seit")
        gesamt = c.get("/api/sicherung/punkte").json()["gesamt"]["groesse"]
        expect(tid(page, "sicherung-gesamt")).to_have_attribute("data-bytes", str(gesamt))
        expect(tid(page, f"punkt-{a['kennung']}")).to_contain_text("Ausgangsstand")
        expect(tid(page, f"punkt-{b['kennung']}")).to_contain_text("entspricht dem aktuellen Stand")
        expect(tid(page, f"punkt-groesse-{b['kennung']}")).to_be_visible()
        # Fenster des älteren Punkts: Wirkung gegenüber dem aktuellen Stand, dann wechseln
        tid(page, f"punkt-oeffnen-{a['kennung']}").click()
        expect(tid(page, "punkt-dialog")).to_be_visible()
        expect(tid(page, "punkt-wirkung")).to_contain_text("1 Tag entfällt")
        tid(page, "punkt-wechseln").click()
        tid(page, "bestaetigen-ja").click()
        expect(tid(page, "punkt-dialog")).to_have_count(0)
        expect(page.locator('[data-testid="meldung"][data-art="erfolg"]').last).to_contain_text("hergestellt")
        assert c.get("/api/tags").json() == []
        # vorwärts: der neuere Punkt ist noch da und stellt den Tag wieder her
        expect(tid(page, f"punkt-{b['kennung']}")).to_contain_text("vorwärts")
        tid(page, f"punkt-oeffnen-{b['kennung']}").click()
        expect(tid(page, "punkt-wirkung")).to_contain_text("1 Tag kommt zurück")
        tid(page, "punkt-wechseln").click()
        tid(page, "bestaetigen-ja").click()
        expect(tid(page, "punkt-dialog")).to_have_count(0)
        assert [t["name"] for t in c.get("/api/tags").json()] == ["Urlaub"]
        # derselbe Stand: Wechsel nicht möglich
        tid(page, f"punkt-oeffnen-{b['kennung']}").click()
        expect(tid(page, "punkt-wirkung")).to_have_attribute("data-gleich", "ja")
        expect(tid(page, "punkt-wechseln")).to_be_disabled()


def test_punkt_von_hand_und_handy(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        c = _client(url)
        _zwei_punkte(c)
        page.goto(url + "/sicherung")
        bereit(page, "sicherung")
        tid(page, "sicherung-anlegen").click()
        tid(page, "punkt-anlegen-ok").click()
        expect(page.locator('[data-testid="meldung"]').last).to_contain_text("bereits gesichert")
        breite = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert breite <= 1, "kein seitliches Rollen am Handy"
