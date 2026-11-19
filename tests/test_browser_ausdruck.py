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
        expect(tid(page, "regel-testmenge")).to_have_count(0)        # D-214: kein zweites Filterfeld
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
        # D-214: leerer Name → Vorschlag aus Bedingung und Kategorie, statt „Die Anfrage ist ungültig.“
        expect(tid(page, "regel-name")).to_have_attribute("placeholder", re.compile(r"^Einkauf → .+"))
        tid(page, "regel-speichern").click()
        expect(tid(page, "regel-dialog")).to_be_hidden()
        expect(page.locator(".regel-zeile strong").first).to_have_text(re.compile(r"^Einkauf → .+"))


def test_regeleditor_ohne_kategorie(tmp_path, browser):  # noqa: F811
    """D-214: ohne Kategorie läuft der Test trotzdem; Speichern nennt den Grund am Feld."""
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        expect(tid(page, "regel-kategorie")).to_have_value("")
        tid(page, "regel-ausdruck").fill('"AMAZON" in empf')
        expect(tid(page, "test-zahlen")).to_have_text("0 Treffer in 0 Buchungen (12 Monate)")
        tid(page, "regel-speichern").click()
        expect(tid(page, "dialog-fehler")).to_contain_text("Kategorie oder mindestens einen Tag")
        expect(tid(page, "regel-kategorie")).to_have_attribute("aria-invalid", "true")


def test_regeleditor_tags(tmp_path, browser):  # noqa: F811
    """D-215: Regel vergibt Tags (auch ohne Kategorie); neue Tags entstehen beim Speichern."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        expect(tid(page, "regel-kategorie")).not_to_have_value("")   # Vorgabe bleibt die erste Kategorie
        tid(page, "regel-ausdruck").fill('"Einkauf" in vwz and bet <= 3')
        tid(page, "regel-tag-eingabe").fill("Urlaub")
        tid(page, "regel-tag-eingabe").press("Enter")
        tid(page, "regel-tag-eingabe").fill("Privat")
        tid(page, "regel-tag-hinzufuegen").click()
        tid(page, "regel-tag-eingabe").fill("urlaub")                 # doppelt: bleibt bei zwei
        tid(page, "regel-tag-eingabe").press("Enter")
        expect(tid(page, "regel-tags").locator('[role="listitem"]')).to_have_count(2)
        tid(page, "regel-tag-entfernen-Privat").click()
        expect(tid(page, "regel-tags")).to_have_text(re.compile(r"^Urlaub \(neu\)×$"))
        tid(page, "regel-kategorie").select_option("")
        expect(tid(page, "regel-name")).to_have_attribute("placeholder", "Einkauf → #Urlaub")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-tags", "3")
        expect(tid(page, "regel-test-anwenden")).to_have_text("Tags an 3 Buchung(en) vergeben…")
        tid(page, "regel-test-anwenden").click()                      # speichert und fragt nach
        expect(tid(page, "regel-anwenden-tags")).to_contain_text("+ Urlaub")
        tid(page, "regel-anwenden-ok").click()
        expect(page.get_by_text("3 Buchung(en) geändert")).to_be_visible()
        ziel = page.locator('[data-testid^="regel-ziel-"]').first
        expect(ziel).to_contain_text("+ Urlaub")
        expect(page.locator(".regel-zeile strong").first).to_have_text("Einkauf → #Urlaub")
        # erneut öffnen: Tag ist jetzt vorhanden, Kategorie bleibt leer, nichts mehr zu vergeben
        page.get_by_role("button", name="Regel Einkauf → #Urlaub bearbeiten").click()
        expect(tid(page, "regel-kategorie")).to_have_value("")
        expect(tid(page, "regel-tags")).to_have_text("Urlaub×")
        expect(tid(page, "test-zahlen")).to_have_attribute("data-tags", "0")
        expect(tid(page, "regel-test-anwenden")).to_be_disabled()


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


def test_anwenden_fenster_ohne_unsinn(tmp_path, browser):  # noqa: F811
    """D-216: Das Fenster nach „Speichern und anwenden“ nennt Umfang und Wirkung in Worten, nie „null“."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        tid(page, "regel-anlegen").click()
        tid(page, "regel-ausdruck").fill('"Einkauf" in vwz and bet <= 3')
        expect(tid(page, "test-zahlen")).to_have_attribute("data-anzahl", "3")
        tid(page, "regel-speichern-anwenden").click()
        fenster = tid(page, "regel-anwenden-dialog")
        expect(fenster).to_be_visible()
        expect(fenster).not_to_contain_text("null")
        expect(fenster).not_to_contain_text("datum in")
        expect(tid(page, "regel-anwenden-umfang")).to_have_text("Zeitraum: 12 Monate")
        expect(tid(page, "regel-anwenden-nichts")).to_be_visible()     # alle drei haben die Kategorie schon
        expect(tid(page, "regel-anwenden-ok")).to_be_hidden()


def test_tags_im_kontoblatt_bearbeiten(tmp_path, browser):  # noqa: F811
    """D-216: Der Tag-Dialog zeigt die vorhandenen Tags; entfernen per ×, auch für mehrere Buchungen."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        page.locator('[data-testid^="uebersicht-konto-"] [data-feld="name"]', has_text="Giro").click()
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        zeilen.nth(0).locator('[data-feld="datum"]').click()
        zeilen.nth(1).locator('[data-feld="datum"]').click(modifiers=["Control"])
        zeilen.nth(2).locator('[data-feld="datum"]').click(modifiers=["Control"])
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "3")
        tid(page, "mehrfach-tags").click()
        expect(tid(page, "tag-auswahl-vorhanden")).to_have_text("Noch keine Tags.")
        tid(page, "tag-auswahl-name").fill("Urlaub")
        tid(page, "tag-auswahl-hinzufuegen").click()
        expect(tid(page, "tag-auswahl")).to_be_hidden()
        # eine der drei bekommt zusätzlich „Privat“
        zeilen.nth(0).locator('[data-feld="datum"]').click()
        page.keyboard.press("t")
        expect(tid(page, "tag-auswahl-vorhanden")).to_have_text("Urlaub×")
        tid(page, "tag-auswahl-name").fill("Privat")
        tid(page, "tag-auswahl-name").press("Enter")
        expect(tid(page, "tag-auswahl")).to_be_hidden()
        # Mehrfachauswahl: beide Tags mit Anzahl, × entfernt von allen, der Dialog bleibt offen
        zeilen.nth(1).locator('[data-feld="datum"]').click(modifiers=["Control"])
        zeilen.nth(2).locator('[data-feld="datum"]').click(modifiers=["Control"])
        tid(page, "mehrfach-tags").click()
        vorhanden = tid(page, "tag-auswahl-vorhanden")
        expect(vorhanden).to_contain_text("Urlaub (alle)")
        expect(vorhanden).to_contain_text("Privat (1 von 3)")
        vorhanden.locator('[role="listitem"]', has_text="Urlaub").get_by_role("button").click()
        expect(vorhanden.locator('[role="listitem"]')).to_have_count(1)
        expect(tid(page, "tag-auswahl")).to_be_visible()
        vorhanden.locator('[role="listitem"]', has_text="Privat").get_by_role("button").click()
        expect(vorhanden).to_have_text("Noch keine Tags.")
        page.keyboard.press("Escape")
        expect(page.locator('[data-testid="buchungsliste"] .tag', has_text="Urlaub")).to_have_count(0)
        page.keyboard.press("Control+z")                              # letzter Schritt zurück: „Privat“ wieder da
        expect(page.locator('[data-testid="buchungsliste"] .tag', has_text="Privat")).to_have_count(1)
