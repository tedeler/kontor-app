"""Browser-Rauchtest der M3-Oberfläche (Playwright, Chrome headless): Erfassen, Umbuchungsvorschläge,
Kontenabstimmung, globale Suche, Empfängerverwaltung, Konto löschen mit Auswahl, Änderungsprotokoll mit
Rückgängig-Knopf und Strg+Z. Wird übersprungen, wenn kein Browser verfügbar ist.

Echte Server im Mock-Modus (eingebauter synthetischer Datensatz) auf freien lokalen Ports.
"""

from __future__ import annotations

import pytest

from .test_browser_m2 import _neue_seite, _server, browser  # noqa: F401  (Fixture)

playwright = pytest.importorskip("playwright.sync_api")


def _konten(page, url) -> dict[str, dict]:
    return {k["name"]: k for k in page.request.get(url + "/api/konten").json()}


def test_m3_desktop(tmp_path, browser):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport={"width": 1280, "height": 900})
        page.request.post(url + "/api/sync", data={})
        # Umbuchungsvorschläge: Giro → Tagesgeld je Monat
        page.goto(url + "/#/umbuchungen")
        page.wait_for_selector("h1:has-text('Umbuchungen')")
        paare = page.locator(".paar").count()
        assert paare >= 1
        page.locator(".paar button", has_text="Zusammenführen").first.click()
        page.wait_for_selector(".meldung:has-text('Umbuchung zusammengeführt')")
        page.wait_for_function(f"document.querySelectorAll('.paar').length === {paare - 1}")
        # Strg+Z nimmt die letzte Änderung (das Zusammenführen) zurück
        page.locator("h1").click()
        page.keyboard.press("Control+z")
        page.wait_for_selector(".meldung:has-text('Rückgängig gemacht')")
        page.goto(url + "/#/umbuchungen")
        page.wait_for_function(f"document.querySelectorAll('.paar').length === {paare}")
        page.locator("button", has_text="zusammenführen").first.click()
        page.wait_for_selector(".meldung:has-text('zusammengeführt')")
        # Buchung erfassen
        konten = _konten(page, url)
        giro = konten["Girokonto (Mock)"]
        page.goto(url + f"/#/konto/{giro['id']}")
        page.locator("button", has_text="+ Buchung erfassen").click()
        page.locator(".dialog input[inputmode=decimal]").fill("12,34")
        page.locator(".dialog label:has-text('Verwendungszweck') input").fill("Bäckerei am Markt")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Buchung erfasst')")
        # Globale Suche (umlaut-unabhängig)
        page.fill("#suche-global", "BAECKEREI")
        page.press("#suche-global", "Enter")
        page.wait_for_selector("h1:has-text('Suche: BAECKEREI')")
        assert "Bäckerei am Markt" in page.locator("#inhalt").inner_text()
        # Kontenabstimmung mit Differenz und mit passendem Saldo
        saldo = next(k for k in page.request.get(url + "/api/kontenuebersicht").json()["konten"]
                     if k["konto_id"] == giro["id"])["saldo"]
        page.goto(url + "/#/abstimmung")
        page.locator("tr:has-text('Girokonto (Mock)') button", has_text="Abstimmen").click()
        page.fill(".dialog input[type=date]", "2099-12-31")
        page.fill(".dialog input[inputmode=decimal]", "1,00")
        page.locator(".dialog button", has_text="Prüfen").click()
        page.wait_for_selector(".dialog .warnung:has-text('stimmt nicht')")
        euro = f"{saldo // 100 if saldo >= 0 else -((-saldo) // 100)},{abs(saldo) % 100:02d}"
        page.fill(".dialog input[inputmode=decimal]", euro if saldo >= 0 else "-" + euro.lstrip("-"))
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Abgestimmt')")
        assert page.request.get(url + "/api/buchungen?abgestimmt=false&konto_id=%d" % giro["id"]).json()["gesamt"] == 0
        # Änderungsprotokoll: Rückgängig-Knopf hebt die Abstimmung auf
        page.goto(url + "/#/protokoll")
        zeile = page.locator("tr.aenderung").first
        assert "Konto abgestimmt" in zeile.inner_text()
        zeile.locator("button", has_text="Rückgängig").click()
        # Auf den Zustand warten, nicht auf die Meldung (eine ältere „Rückgängig gemacht“ kann noch sichtbar sein)
        for _ in range(100):
            if page.request.get(url + "/api/abstimmungen").json() == []:
                break
            page.wait_for_timeout(100)
        assert page.request.get(url + "/api/abstimmungen").json() == []
        assert not fehler, fehler
        page.close()


def test_m3_handy_empfaenger_und_loeschen(tmp_path, browser):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport={"width": 390, "height": 840}, is_mobile=True, has_touch=True)
        page.request.post(url + "/api/sync", data={})
        kat = page.request.post(url + "/api/konten", data={"name": "Strom", "art": "aufwand"}).json()
        # Empfänger: Standardkategorie und Alias im Dialog
        page.goto(url + "/#/empfaenger")
        page.locator("tr:has-text('Stadtwerke Musterstadt') button", has_text="Bearbeiten").click()
        page.locator(".dialog textarea").fill("SWM ENERGIE")
        page.select_option(".dialog select", value=str(kat["id"]))
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Empfänger gespeichert')")
        e = next(x for x in page.request.get(url + "/api/empfaenger").json() if x["name"].startswith("Stadtwerke"))
        assert e["aliase"] == ["SWM ENERGIE"] and e["standardkategorie_id"] == kat["id"]
        # Kategorie mit Buchungen löschen: erst Variante wählen, dann bestätigen
        b = page.request.get(url + "/api/buchungen?empfaenger_id=%d" % e["id"]).json()["eintraege"][0]
        page.request.put(url + f"/api/buchungen/{b['id']}/kategorie", data={"kategorie_id": kat["id"]})
        page.goto(url + f"/#/kategorie/{kat['id']}")
        page.locator("a", has_text="löschen …").click()
        page.wait_for_selector(".dialog:has-text('Wie soll mit den Buchungen umgegangen werden')")
        assert page.locator(".dialog input[name=variante]:checked").count() == 0, "keine Vorauswahl"
        assert page.locator(".dialog input[value=elternkonto]").is_disabled(), "Wurzelkategorie hat kein Elternkonto"
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Bitte wählen')")
        page.locator(".dialog input[value=unkategorisiert]").check()
        page.wait_for_selector(".dialog .zahlen")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('gelöscht')")
        assert all(k["id"] != kat["id"] for k in page.request.get(url + "/api/konten").json())
        # Rückgängig über den Knopf im Kopf (Touch-Bedienung)
        page.locator("#rueckgaengig-knopf").click()
        page.wait_for_selector(".meldung:has-text('Rückgängig gemacht')")
        assert any(k["id"] == kat["id"] for k in page.request.get(url + "/api/konten").json())
        assert page.request.get(url + f"/api/empfaenger/{e['id']}").json()["standardkategorie_id"] == kat["id"]
        # Suche auf dem Handy
        page.fill("#suche-global", "swm")
        page.press("#suche-global", "Enter")
        page.wait_for_selector("h2:has-text('Empfänger (1)')")
        assert not fehler, fehler
        page.close()
