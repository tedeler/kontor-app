"""Browser-Rauchtest der M9-Oberfläche (Playwright, Chrome headless): Sicherung herunterladen, nach
Änderungen hochladen, Probelauf mit Unterschied, deutliche Bestätigung, Einspielen, Ergebnis, Rückgängig;
fehlerhafte Datei; Handy-Ansicht.

Echte Server im Mock-Modus (eingebauter synthetischer Datensatz) auf freien lokalen Ports; nur
synthetische Daten, keine Verbindung nach außen.
"""

from __future__ import annotations

import pytest

from .test_browser_m2 import _neue_seite, _server, browser  # noqa: F401  (Fixture)

playwright = pytest.importorskip("playwright.sync_api")


def _namen(page, url) -> set[str]:
    return {k["name"] for k in page.request.get(url + "/api/konten").json()}


def _sicherung_herunterladen(page, tmp_path) -> bytes:
    with page.expect_download() as info:
        page.locator("#sicherung-herunterladen").click()
    d = info.value
    assert d.suggested_filename.startswith("kontor-sicherung-mock-") and d.suggested_filename.endswith(".zip")
    ziel = tmp_path / d.suggested_filename
    d.save_as(ziel)
    return ziel.read_bytes()


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}],
                         ids=["desktop", "handy"])
def test_m9_sicherung(tmp_path, browser, viewport):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport=viewport, accept_downloads=True)
        page.request.post(url + "/api/konten", data={"name": "Vor der Sicherung", "art": "aufwand"})
        page.goto(url + "/#/sicherung")
        page.wait_for_selector("h1:has-text('Datensicherung')")
        daten = _sicherung_herunterladen(page, tmp_path)
        assert daten[:2] == b"PK"

        # identische Sicherung: Probelauf meldet „identisch“
        page.set_input_files("#sicherung-datei", files=[{"name": "s.zip", "mimeType": "application/zip",
                                                          "buffer": daten}])
        page.locator("#sicherung-pruefen").click()
        page.wait_for_selector("#sicherung-identisch")

        # nach einer Änderung: Unterschied anzeigen, Bestätigung nötig
        page.request.post(url + "/api/konten", data={"name": "Nach der Sicherung", "art": "aufwand"})
        page.set_input_files("#sicherung-datei", files=[{"name": "s.zip", "mimeType": "application/zip",
                                                          "buffer": daten}])
        page.locator("#sicherung-pruefen").click()
        page.wait_for_selector("#sicherung-probelauf")
        zeile = page.locator("#sicherung-unterschied tr", has_text="Konten und Kategorien")
        assert zeile.locator("td").nth(4).inner_text() == "1"
        assert page.locator("#sicherung-einspielen").is_disabled()
        assert "Nach der Sicherung" in _namen(page, url), "Probelauf ändert nichts"
        page.locator("#sicherung-verstanden").check()
        page.locator("#sicherung-einspielen").click()
        page.wait_for_selector(".dialog:has-text('Gesamten Bestand ersetzen?')")
        page.locator(".dialog button", has_text="Ja, Bestand ersetzen").click()
        page.wait_for_selector("#sicherung-ergebnis:has-text('Sicherung eingespielt.')")
        assert "Nach der Sicherung" not in _namen(page, url) and "Vor der Sicherung" in _namen(page, url)
        aend = page.request.get(url + "/api/aenderungen?quelle=sicherung").json()
        assert aend["gesamt"] == 1 and aend["eintraege"][0]["aktion"] == "sicherung_einspielen"

        # Rückgängig aus der Ergebnisanzeige
        page.locator("#sicherung-rueckgaengig").click()
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('rückgängig gemacht')")
        assert "Nach der Sicherung" in _namen(page, url)

        # kaputte Datei: deutliche Fehlermeldung, nichts geändert
        page.set_input_files("#sicherung-datei", files=[{"name": "kaputt.zip", "mimeType": "application/zip",
                                                          "buffer": b"kein zip"}])
        page.locator("#sicherung-pruefen").click()
        page.wait_for_selector("#sicherung-ausgabe:has-text('keine lesbare ZIP-Datei')")
        assert "Nach der Sicherung" in _namen(page, url)

        # Navigation enthält den neuen Bereich; keine horizontale Überbreite auf dem Handy
        breite = page.evaluate("document.documentElement.scrollWidth")
        assert breite <= viewport["width"] + 1, breite
        assert not fehler, fehler
        page.close()
