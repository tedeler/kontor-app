"""Browser-Rauchtests Kontor-Ausdrücke (D-175): Filterausdruck im Kontoblatt, Regeleditor mit Baukasten und Test."""

from __future__ import annotations

import re

from .test_browser import DESKTOP, HANDY, bereit, browser, expect, seite, server, tid  # noqa: F401


def test_filterausdruck_im_kontoblatt(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        page.locator('[data-testid^="uebersicht-konto-"] [data-feld="name"]', has_text="Giro").click()
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        expect(zeilen).to_have_count(20)
        feld = tid(page, "filter-ausdruck")
        feld.fill("bet >= 15 and bet < 18")
        expect(zeilen).to_have_count(3)
        expect(page).to_have_url(re.compile(r"filter=bet"))
        expect(tid(page, "filter-zusammenfassung")).to_contain_text("3 Buchungen")
        feld.fill("bet = 5")
        expect(tid(page, "filter-ausdruck-fehler")).to_contain_text("==")
        expect(zeilen).to_have_count(3)   # die letzte gültige Liste bleibt stehen
        feld.fill("datum < 5.1.2024")
        expect(zeilen).to_have_count(4)
        tid(page, "filter-ausdruck-leeren").click()
        expect(zeilen).to_have_count(20)


def test_regeleditor_baukasten_und_test(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        dialog = tid(page, "regel-dialog")
        expect(dialog).to_be_visible()
        tid(page, "regel-name").fill("Kleinbeträge")
        tid(page, "regel-ausdruck").fill('bet <= 3 and dir == "ausgabe"')
        expect(tid(page, "regel-ausdruck-status")).to_have_attribute("data-status", "ok")
        tid(page, "regel-testmenge").fill("")
        tid(page, "regel-testmenge").press("Enter")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "3")
        tid(page, "regel-modus-baukasten").click()
        expect(tid(page, "bk-0-op")).to_have_value("<=")
        expect(tid(page, "bk-1-wert")).to_have_value("ausgabe")
        tid(page, "bk-0-wert").fill("4")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "4")
        tid(page, "regel-speichern").click()
        expect(dialog).to_be_hidden()
        expect(page.locator('[data-testid^="regel-ausdruck-"]').first).to_have_text('betrag <= 4 and richtung == "ausgabe"')


def test_regelliste_handy(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        expect(tid(page, "regel-dialog")).to_be_visible()
        tid(page, "regel-ausdruck").fill('datum in -5d')
        expect(tid(page, "regel-ausdruck-fehler")).to_contain_text("nur im Filter")
