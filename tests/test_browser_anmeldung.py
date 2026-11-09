"""Browser-Rauchtest der Anmeldung (M7/M8): Ersteinrichtung, falsches Passwort, Weiterleitung, CSRF beim
Schreiben, Abmelden über die Einstellungen; Desktop- und Handybreite. Synthetisches Passwort, kein Geheimnis."""

from __future__ import annotations

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
PASSWORT = "Synthetisch-Haushalt-2026"


@pytest.mark.parametrize("geraet", [DESKTOP, HANDY], ids=["desktop", "handy"])
def test_anmeldung(tmp_path, browser, geraet):  # noqa: F811
    from kontor.anmeldung import einrichtungsdatei

    with server(tmp_path, anmeldung=True, anmeldung_fehlversuche=3, anmeldung_sperre_sekunden=2) as (url, config), \
            seite(browser, url, **geraet) as page:
        page.goto(url + "/einstellungen")
        expect(tid(page, "anmeldung-formular")).to_be_visible()
        assert "/anmelden?weiter=" in page.url
        expect(tid(page, "anmeldung-fehler")).to_be_hidden()
        code = einrichtungsdatei(config).read_text(encoding="ascii").strip()
        tid(page, "anmeldung-einrichtungscode").fill("0" * 32)
        tid(page, "anmeldung-passwort").fill(PASSWORT)
        tid(page, "anmeldung-passwort").press("Enter")
        expect(tid(page, "anmeldung-fehler")).to_contain_text("Einrichtungscode ist falsch")
        expect(tid(page, "anmeldung-passwort")).to_have_value("")
        tid(page, "anmeldung-einrichtungscode").fill(code)
        tid(page, "anmeldung-passwort").fill(PASSWORT)
        tid(page, "anmeldung-passwort").press("Enter")
        bereit(page, "einstellungen")
        # schreibende Anfrage der Oberfläche mit CSRF-Kopf
        page.goto(url + "/kategorien")
        bereit(page, "kategorien")
        tid(page, "kategorie-anlegen").click()
        tid(page, "konto-name").fill("Spenden")
        tid(page, "konto-speichern").click()
        expect(page.locator('[role="treeitem"][aria-label="Spenden"]')).to_be_visible()
        # Abmelden
        page.goto(url + "/einstellungen")
        bereit(page, "einstellungen")
        tid(page, "abmelden").click()
        expect(tid(page, "anmeldung-formular")).to_be_visible()
        assert page.request.get(url + "/api/konten").status == 401
        tid(page, "anmeldung-passwort").fill("Ganz-falsches-Passwort")
        tid(page, "anmeldung-passwort").press("Enter")
        expect(tid(page, "anmeldung-fehler")).to_contain_text("Passwort ist falsch")
        tid(page, "anmeldung-passwort").fill(PASSWORT)
        tid(page, "anmeldung-passwort").press("Enter")
        bereit(page, "uebersicht")
