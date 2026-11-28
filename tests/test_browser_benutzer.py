"""Browser-Rauchtests zum Feature benutzer (D-324): Personen aus ``KONTOR_BENUTZER``."""

from __future__ import annotations

import sqlite3

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _giro(config) -> int:
    con = sqlite3.connect(config.aktive_datenbank)
    try:
        return con.execute("SELECT id FROM konto WHERE art = 'girokonto' ORDER BY id LIMIT 1").fetchone()[0]
    finally:
        con.close()


def test_drei_benutzer_im_dialog_in_ihrer_reihenfolge(tmp_path, browser):
    namen = ("Jörg", "Anna-Lena", "Ole")
    with server(tmp_path, benutzer=namen) as (url, config), seite(browser, url, person=None, **DESKTOP) as page:
        page.goto(url + "/")
        d = tid(page, "person-dialog")
        expect(d).to_be_visible()
        expect(d.locator(".knopf-leiste button")).to_have_text(list(namen))
        tid(page, "person-ole").click()
        expect(d).to_have_count(0)
        k = tid(page, "person-knopf")
        expect(k).to_have_text("Ole")
        expect(k).to_have_attribute("data-farbe", "2")
        assert page.evaluate("() => localStorage.getItem('kontor.person')") == "Ole"
        # Bestätigen setzt „Ole-Bestätigt“ mit der Farbe seines Platzes
        page.goto(f"{url}/konten/{_giro(config)}")
        bereit(page, "konto")
        page.locator(".zeile").first.click(button="right", position={"x": 20, "y": 8})
        expect(tid(page, "km-bestaetigen")).to_have_text("Als Ole bestätigen")
        tid(page, "km-bestaetigen").click()
        tag = page.locator(".zeile[data-bestaetigt=Ole] .tag-person").first
        expect(tag).to_have_text("Ole-Bestätigt")
        expect(tag).to_have_attribute("data-farbe", "2")


def test_gemerkter_name_ausserhalb_der_liste_gilt_nicht(tmp_path, browser):
    with server(tmp_path, daten=False, benutzer=("Anna", "Ben")) as (url, _), \
            seite(browser, url, person="Torsten", **DESKTOP) as page:
        page.goto(url + "/")
        expect(tid(page, "person-dialog")).to_be_visible()
        expect(tid(page, "person-anna")).to_be_visible()
        expect(tid(page, "person-torsten")).to_have_count(0)


def test_ein_benutzer_ohne_rueckfrage(tmp_path, browser):
    with server(tmp_path, benutzer=("Anna",)) as (url, config), seite(browser, url, person=None, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(config)}")
        bereit(page, "konto")
        expect(tid(page, "person-dialog")).to_have_count(0)
        k = tid(page, "person-knopf")
        expect(k).to_have_text("Anna")
        expect(k).to_be_disabled()
        expect(k).to_have_attribute("aria-label", "Angemeldet als Anna.")
        page.locator(".zeile").first.click(button="right", position={"x": 20, "y": 8})
        expect(tid(page, "km-bestaetigen")).to_have_text("Als Anna bestätigen")


def test_ohne_benutzer_kein_dialog_und_kein_bestaetigen(tmp_path, browser):
    with server(tmp_path, benutzer=()) as (url, config), seite(browser, url, person=None, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(config)}")
        bereit(page, "konto")
        expect(tid(page, "person-dialog")).to_have_count(0)
        expect(tid(page, "person-knopf")).to_have_count(0)
        page.locator(".zeile").first.click(button="right", position={"x": 20, "y": 8})
        expect(tid(page, "km-bearbeiten")).to_be_visible()
        expect(tid(page, "km-bestaetigen")).to_have_count(0)
        page.keyboard.press("Escape")
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        expect(tid(page, "empfaenger-bestaetigen")).to_be_hidden()
        expect(page.locator("[data-testid^=empfaenger-bestaetigen-]:visible")).to_have_count(0)
        expect(page.locator(".empfaenger-liste th", has_text="Bestätigt")).to_be_hidden()
