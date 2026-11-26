"""Eigene Browsertests zur Gestaltung des Änderungsprotokolls (D-294): Tage, Quellen-Marken, Filter nach Quelle,
zurückgenommene Änderungen, Handy ohne seitliches Rollen. Nur synthetische Daten."""
from __future__ import annotations

import datetime as dt

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _client(url):
    import httpx
    return httpx.Client(base_url=url, trust_env=False, timeout=60)


def _aenderungen(c):
    """Drei eigene Änderungen, die mittlere zurückgenommen."""
    a = c.post("/api/tags", json={"name": "Urlaub"}).json()
    b = c.post("/api/tags", json={"name": "Auto"}).json()
    c.post("/api/tags", json={"name": "Steuer"})
    neueste = c.get("/api/aenderungen", params={"pro_seite": 3}).json()["eintraege"]
    assert c.post(f"/api/aenderungen/{neueste[1]['id']}/rueckgaengig").status_code == 200
    return a, b, neueste


def test_tage_quellen_und_zurueckgenommenes(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        _, _, eigene = _aenderungen(c)
        alle = c.get("/api/aenderungen", params={"pro_seite": 50}).json()
        page.goto(url + "/protokoll")
        bereit(page, "protokoll")
        expect(tid(page, "protokoll-stand")).to_have_text(f"{alle['gesamt']} Änderungen")
        # nach Tagen gegliedert, neueste zuerst; jede Zeile mit Uhrzeit und Marke der Quelle
        tag = dt.datetime.fromisoformat(alle["eintraege"][0]["zeitpunkt"].replace("Z", "+00:00")).astimezone().date()
        erster = page.locator(".pr-tag").first
        expect(erster).to_have_attribute("data-tag", tag.isoformat())
        if tag != dt.date.today():       # der Testserver läuft mit simulierter Uhr
            expect(erster.locator(".pr-tag-titel")).to_contain_text(f"{tag.day}.")
        zeile = tid(page, f"aenderung-{eigene[0]['id']}")
        expect(zeile.locator(".pr-quelle")).to_have_text("Von Hand")
        expect(zeile.locator(".pr-titel")).to_have_text("Tag angelegt")      # ohne „(1 Objekt)“
        expect(zeile.locator(".pr-umfang")).to_have_text("Tag: Steuer")
        zurueck = tid(page, f"aenderung-{eigene[1]['id']}")
        expect(zurueck).to_have_attribute("data-wirksam", "nein")
        expect(zurueck).to_contain_text("zurückgenommen durch #")
        expect(tid(page, f"aenderung-rueckgaengig-{eigene[1]['id']}")).to_have_count(0)
        neueste = tid(page, f"aenderung-{alle['eintraege'][0]['id']}")
        expect(neueste.locator(".pr-quelle")).to_have_text("Rückgängig")
        expect(neueste).to_contain_text(f"nimmt Änderung #{eigene[1]['id']} zurück")
        # die Beschreibung öffnet die Einzelheiten
        tid(page, f"aenderung-einzelheiten-{eigene[0]['id']}").click()
        expect(tid(page, "aenderung-dialog")).to_be_visible()
        expect(tid(page, "ae-stand")).to_have_text("wirksam")
        tid(page, "ae-schliessen").click()


def test_filter_nach_quelle_ohne_bis_hierher(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        _, _, eigene = _aenderungen(c)
        page.goto(url + "/protokoll")
        bereit(page, "protokoll")
        expect(tid(page, f"aenderung-bis-{eigene[0]['id']}")).to_be_visible()
        anfragen = []
        page.on("request", lambda r: anfragen.append(r.url) if "/api/aenderungen?" in r.url else None)
        tid(page, "protokoll-filter-rueckgaengig").click()
        expect(tid(page, "protokoll-filter-rueckgaengig")).to_have_attribute("aria-pressed", "true")
        expect(page.locator("li.aenderung")).to_have_count(1)
        expect(page.locator("li.aenderung").first).to_have_attribute("data-quelle", "rueckgaengig")
        assert "quelle=rueckgaengig" in anfragen[-1]
        # mit Filter kein „Bis hierher“: es würde auch ausgeblendete Änderungen zurücknehmen
        expect(page.locator('[data-testid^="aenderung-bis-"]')).to_have_count(0)
        expect(tid(page, "protokoll-stand")).to_have_text("1 Änderung · Rückgängig")
        tid(page, "protokoll-filter-bank").click()
        expect(page.locator("li.aenderung")).to_have_count(0)
        expect(page.locator(".pr-leer")).to_have_text("Keine Änderungen in „Bankabruf“.")
        tid(page, "protokoll-filter-alle").click()
        expect(tid(page, f"aenderung-bis-{eigene[0]['id']}")).to_be_visible()


def test_handy_ohne_seitliches_rollen(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        c = _client(url)
        _aenderungen(c)
        page.goto(url + "/protokoll")
        bereit(page, "protokoll")
        zeile = page.locator("li.aenderung").first
        expect(zeile.locator(".pr-titel")).to_be_visible()
        breite = page.evaluate("() => [document.querySelector('.pr-liste').scrollWidth, document.querySelector('.pr-liste').clientWidth]")
        assert breite[0] <= breite[1], breite
        # Aktionen stehen in der ersten Zeile neben Uhrzeit und Quelle, die Beschreibung darunter
        oben = zeile.locator(".pr-aktionen").bounding_box()["y"]
        assert oben < zeile.locator(".pr-titel").bounding_box()["y"]
