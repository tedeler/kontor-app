"""Browser-Rauchtest der gegliederten Einstellungen (Feature „einstellungen“, D-207): Bereiche mit Navigation und
Stand, Suche mit Sprung zur Einstellung, „Erweitert“, ein Tab für alle Bereiche; Desktop und Handy. Nur Mock-Modus
bzw. FinTS ohne Zugangsdaten (keine Verbindung), keine Geheimnisse."""

from __future__ import annotations

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
BEREICHE = ["allgemein", "bank", "mail", "benachrichtigungen", "sicherheit", "daten"]


def test_bereiche_desktop(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/einstellungen")
        bereit(page, "einstellungen")
        # ohne gewählten Bereich zeigt der Desktop „Allgemein“; die übrigen Bereiche sind nicht sichtbar
        expect(tid(page, "einstellungen-nav").locator("a")).to_have_count(len(BEREICHE))
        expect(tid(page, "einstellungen-nav-allgemein")).to_have_attribute("aria-current", "page")
        expect(tid(page, "einstellung-thema")).to_be_visible()
        expect(tid(page, "sicherung-herunterladen")).to_be_hidden()
        expect(tid(page, "einstellungen-zurueck")).to_be_hidden()
        # jeder Eintrag der Navigation nennt den Stand seines Bereichs
        for b in BEREICHE:
            expect(tid(page, f"einstellungen-status-{b}")).not_to_be_empty()
        expect(tid(page, "einstellungen-status-bank")).to_contain_text("Mock-Modus")
        expect(tid(page, "einstellungen-status-benachrichtigungen")).to_have_attribute("data-zustand", "ok")
        # Wechsel des Bereichs: Adresse mit Abfrageteil, weiter genau ein Tab
        tid(page, "einstellungen-nav-daten").click()
        expect(tid(page, "einstellungen-bereich-titel")).to_have_text("Daten und Sicherung")
        expect(tid(page, "sicherung-herunterladen")).to_be_visible()
        expect(tid(page, "einstellung-thema")).to_be_hidden()
        assert page.url.endswith("/einstellungen?bereich=daten")
        expect(tid(page, "tab")).to_have_count(1)
        # Zurück im Browser und direkter Aufruf
        page.go_back()
        expect(tid(page, "einstellung-thema")).to_be_visible()
        page.goto(url + "/einstellungen?bereich=sicherheit")
        bereit(page, "einstellungen")
        expect(tid(page, "schutz-status")).to_be_visible()
        expect(tid(page, "einstellungen-nav-sicherheit")).to_have_attribute("aria-current", "page")
        # unbekannter Bereich: wie ohne Angabe
        page.goto(url + "/einstellungen?bereich=gibtsnicht")
        bereit(page, "einstellungen")
        expect(tid(page, "einstellung-thema")).to_be_visible()
        # der Stand folgt einer Änderung ohne Neuladen
        tid(page, "einstellung-thema").select_option("dunkel")
        expect(tid(page, "einstellungen-status-allgemein")).to_have_text("Design: Dunkel")
        # im Mock-Modus steht die PIN in einer eigenen Karte des Bereichs „Bank“
        tid(page, "einstellungen-nav-bank").click()
        expect(tid(page, "bankzugang-hinweis")).to_be_visible()
        expect(tid(page, "pin-status")).to_be_visible()


def test_suche_und_erweitert(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/einstellungen")
        bereit(page, "einstellungen")
        suche = tid(page, "einstellungen-suche")
        # Synonym: „backup“ findet die Datensicherung
        suche.fill("backup")
        expect(tid(page, "einstellungen-nav")).to_be_hidden()
        expect(tid(page, "einstellungen-treffer-eintrag")).to_have_count(3)   # D-302: dazu die Sicherungspunkte
        expect(tid(page, "einstellungen-treffer-stand")).to_have_text("3 Einstellungen gefunden.")
        suche.fill("gibtesnicht")
        expect(tid(page, "einstellungen-treffer-stand")).to_have_text("Keine passende Einstellung.")
        # Treffer unter „Erweitert“: Enter springt hin und klappt auf
        suche.fill("oauth")
        expect(tid(page, "einstellungen-treffer-eintrag")).to_contain_text("Mail › Erweitert")
        erw = tid(page, "einstellungen-erweitert-mail")
        suche.press("Enter")
        expect(suche).to_have_value("")
        expect(tid(page, "einstellungen-nav")).to_be_visible()
        expect(erw).to_have_attribute("open", "")
        expect(tid(page, "geheimnis-wert-oauth_client_secret")).to_be_focused()
        assert page.url.endswith("/einstellungen?bereich=mail")
        # Aufgeklapptes bleibt über das Neuladen nach einer Aktion offen
        tid(page, "geheimnis-wert-oauth_client_secret").fill("synthetisch")
        tid(page, "geheimnis-speichern-oauth_client_secret").click()
        expect(tid(page, "geheimnis-oauth_client_secret")).to_have_attribute("data-gesetzt", "ja")
        expect(tid(page, "einstellungen-erweitert-mail")).to_have_attribute("open", "")
        expect(tid(page, "geheimnis-wert-oauth_client_secret")).to_be_visible()
        # Esc leert die Suche
        suche.fill("pin")
        suche.press("Escape")
        expect(suche).to_have_value("")
        expect(tid(page, "einstellungen-treffer")).to_be_hidden()


def test_bankzugang_schritte(tmp_path, browser):
    """FinTS ohne Zugangsdaten: vier Schritte, Pflichtfeld Produkt-ID fehlt → „Erweitert“ offen; keine Verbindung."""
    with server(tmp_path, mock_modus=False, bank_plugin="fints") as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/einstellungen?bereich=bank")
        bereit(page, "einstellungen")
        expect(tid(page, "einstellungen-status-bank")).to_have_text("Bankzugang unvollständig")
        expect(tid(page, "einstellungen-status-bank")).to_have_attribute("data-zustand", "offen")
        karte = tid(page, "bankzugang")
        expect(karte.locator(".einst-gruppe > h4")).to_have_text(["1 · Zugangsdaten", "2 · Bank-PIN", "3 · TAN-Verfahren", "4 · Konten"])
        expect(tid(page, "einstellungen-erweitert-bank-kennungen")).to_have_attribute("open", "")
        expect(tid(page, "bankzugang-produkt_id")).to_be_visible()
        expect(tid(page, "bankzugang-diagnose-aktiv")).to_be_hidden()
        expect(tid(page, "pin-status")).to_have_attribute("data-vorhanden", "nein")
        expect(tid(page, "pin-verwerfen")).to_be_disabled()
        # PIN übergeben: Stand der PIN und Verwerfen folgen ohne Neuladen; die Meldung steht im Schritt
        tid(page, "bankzugang-pin").fill("00000")
        tid(page, "bankzugang-pin-senden").click()
        expect(tid(page, "pin-status")).to_have_attribute("data-vorhanden", "ja")
        expect(tid(page, "pin-verwerfen")).to_be_enabled()
        expect(page.locator('[data-einstellung="pin"]').get_by_test_id("bankzugang-meldung")).to_have_text("PIN übergeben.")
        tid(page, "pin-verwerfen").click()
        expect(tid(page, "pin-status")).to_have_attribute("data-vorhanden", "nein")
        # Suche führt ins Diagnoseprotokoll
        tid(page, "einstellungen-suche").fill("diagnose")
        tid(page, "einstellungen-suche").press("Enter")
        expect(tid(page, "bankzugang-diagnose-aktiv")).to_be_visible()


def test_handy_liste_und_bereich(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/einstellungen")
        bereit(page, "einstellungen")
        # zuerst nur die Liste der Bereiche
        expect(tid(page, "einstellungen-nav")).to_be_visible()
        expect(tid(page, "einstellung-thema")).to_be_hidden()
        tid(page, "einstellungen-nav-daten").click()
        expect(tid(page, "einstellungen-nav")).to_be_hidden()
        expect(tid(page, "einstellungen-suche")).to_be_hidden()
        expect(tid(page, "sicherung-herunterladen")).to_be_visible()
        expect(tid(page, "einstellungen-bereich-titel")).to_be_focused()
        tid(page, "einstellungen-zurueck").click()
        expect(tid(page, "einstellungen-nav")).to_be_visible()
        assert page.url.endswith("/einstellungen")
        # Suche führt direkt in den Bereich
        tid(page, "einstellungen-suche").fill("design")
        tid(page, "einstellungen-treffer-eintrag").first.click()
        expect(tid(page, "einstellung-thema")).to_be_visible()
        # „Einstellungen“ im Menü führt vom Bereich zurück zur Liste
        tid(page, "menue-knopf").click()
        tid(page, "nav-einstellungen").click()
        expect(tid(page, "einstellungen-nav")).to_be_visible()
        expect(tid(page, "einstellung-thema")).to_be_hidden()
        # kein waagerechtes Scrollen
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
