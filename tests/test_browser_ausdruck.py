"""Browser-Rauchtests Kontor-Ausdrücke (D-185): Filterausdruck im Kontoblatt, Regeleditor mit Baukasten und Test."""

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
        expect(tid(page, "regel-testmenge")).to_have_count(0)        # D-207: kein zweites Filterfeld
        expect(tid(page, "regel-in-testmenge")).to_have_count(0)
        expect(tid(page, "test-zeitraum-12m")).to_have_attribute("aria-pressed", "true")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "3")
        tid(page, "regel-modus-baukasten").click()
        expect(tid(page, "bk-0-op")).to_have_value("<=")
        expect(tid(page, "bk-1-wert")).to_have_value("ausgabe")
        tid(page, "bk-0-wert").fill("4")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "4")
        tid(page, "test-zeitraum-vorjahr").click()
        expect(tid(page, "test-zeitraum-vorjahr")).to_have_attribute("aria-pressed", "true")
        expect(tid(page, "test-zahlen")).to_contain_text("(Vorjahr)")
        expect(tid(page, "test-leer")).to_be_visible()               # Testdaten liegen in 2024
        tid(page, "test-alle").click()
        expect(tid(page, "test-zeitraum-alle")).to_have_attribute("aria-pressed", "true")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "4")
        tid(page, "regel-test-konto").select_option(label="Giro")
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


def test_regeleditor_ohne_bedingung_und_uebernahme(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        expect(tid(page, "test-zahlen")).to_contain_text("20 Buchungen (12 Monate)")
        page.locator('[data-testid^="test-zeile-"]').first.click()   # Einzelheiten aufklappen (D-193)
        page.locator('[data-testid^="test-uebernehmen-"]').first.click()
        expect(tid(page, "regel-ausdruck")).to_have_value('"Einkauf" in vwz and dir == "ausgabe"')
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "20")
        # D-207: leerer Name → Vorschlag aus Bedingung und Kategorie, statt „Die Anfrage ist ungültig.“
        expect(tid(page, "regel-name")).to_have_attribute("placeholder", re.compile(r"^Einkauf → .+"))
        tid(page, "regel-speichern").click()
        expect(tid(page, "regel-dialog")).to_be_hidden()
        expect(page.locator(".regel-zeile strong").first).to_have_text(re.compile(r"^Einkauf → .+"))


def test_regeleditor_ohne_kategorie(tmp_path, browser):  # noqa: F811
    """D-207: ohne Kategorie läuft der Test trotzdem; Speichern nennt den Grund am Feld."""
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        expect(tid(page, "regel-kategorie")).to_have_value("")
        tid(page, "regel-ausdruck").fill('"AMAZON" in empf')
        expect(tid(page, "test-zahlen")).to_have_text("0 Treffer in 0 Buchungen (12 Monate)")
        tid(page, "regel-speichern").click()
        expect(tid(page, "dialog-fehler")).to_contain_text("noch keine Kategorie")
        expect(tid(page, "regel-kategorie")).to_have_attribute("aria-invalid", "true")


def test_filter_baukasten_und_alte_adressen(tmp_path, browser):  # noqa: F811
    """D-194: Filter-Baukasten statt Einzelfelder; alte Parameter werden zum Ausdruck."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        page.locator('[data-testid^="uebersicht-konto-"] [data-feld="name"]', has_text="Giro").click()
        bereit(page, "konto")
        konto_url = page.url
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        expect(tid(page, "filter-leiste")).to_be_hidden()            # D-195: eingeklappt
        tid(page, "filter-baukasten-umschalten").click()
        expect(tid(page, "filter-baukasten-umschalten")).to_have_attribute("aria-expanded", "true")
        expect(tid(page, "filter-baukasten")).to_be_visible()
        tid(page, "bk-0-feld").select_option(label="Betrag")
        tid(page, "bk-0-op").select_option(label="mindestens")
        tid(page, "bk-0-wert").fill("18")
        expect(tid(page, "filter-ausdruck")).to_have_value("betrag >= 18")
        expect(zeilen).to_have_count(3)
        # Text oben → Baukasten folgt
        tid(page, "filter-ausdruck").fill("einkauf dt < 3.1.2024")
        expect(zeilen).to_have_count(2)
        expect(tid(page, "bk-1-op")).to_have_value("<")
        expect(tid(page, "bk-1-wert")).to_have_value("03.01.2024")
        tid(page, "filter-schnell-dieses_jahr").click()
        expect(tid(page, "filter-ausdruck")).to_have_value(re.compile(r"datum in dieses_jahr$"))
        tid(page, "filter-zuruecksetzen").click()
        expect(zeilen).to_have_count(20)
        page.goto(konto_url.split("?")[0] + "?von=2024-01-18&verwendungszweck=Einkauf")
        bereit(page, "konto")
        expect(tid(page, "filter-ausdruck")).to_have_value('datum >= 2024-01-18 and "Einkauf" in vwz')
        expect(zeilen).to_have_count(3)
