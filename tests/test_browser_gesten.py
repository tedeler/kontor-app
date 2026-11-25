"""Browser-Rauchtest (D-278, D-279): die fünf Gesten auf einer Buchungszeile im Handy-Format und die einzeilige
Kopfzeile. Nur Mock-Modus, synthetische Daten."""

from __future__ import annotations

import pytest

from .test_browser import HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-id]'


def _mitte(zeile):
    box = zeile.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _wischen(cdp, zeile, weg):
    x, y = _mitte(zeile)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    for i in range(1, 9):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + weg * i / 8, "y": y}]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def test_gesten_im_kontoblatt(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/konten/1")
        bereit(page, "konto")
        liste = tid(page, "buchungsliste")
        expect(tid(page, "buchung-erfassen")).to_be_hidden()          # D-283: mobil kein Knopf zum Erfassen
        erste, zweite = page.locator(ZEILEN).nth(1), page.locator(ZEILEN).nth(2)
        cdp = page.context.new_cdp_session(page)

        # Kopfzeile: eine Zeile, nichts ragt über den Rand (D-279)
        oben = page.evaluate("""() => [...document.querySelectorAll('[data-testid="app-kopf"] .kopf-knopf')]
            .filter((e) => e.offsetParent).map((e) => Math.round(e.getBoundingClientRect().top))""")
        assert len(oben) >= 8 and len(set(oben)) == 1, oben
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Kurz tippen: markiert genau diese Zeile – keine Auswahl, kein Fenster
        erste.tap()
        expect(erste).to_have_attribute("data-markiert", "")
        expect(erste).to_have_attribute("aria-selected", "false")
        expect(tid(page, "panel-details")).to_have_count(0)
        expect(tid(page, "mehrfach-leiste")).to_be_hidden()
        page.wait_for_timeout(450)                      # kein Doppeltipp mit dem nächsten Tippen
        zweite.tap()
        expect(zweite).to_have_attribute("data-markiert", "")
        assert erste.get_attribute("data-markiert") is None
        assert liste.get_attribute("data-auswahlmodus") != "ja"

        # Doppeltipp: Einzelheiten
        page.wait_for_timeout(450)
        erste.tap()
        erste.tap()
        expect(tid(page, "panel-details")).to_be_visible()
        tid(page, "details-schliessen").click()

        # D-281: kein Doppeltipp, solange die Liste gerade gerollt wurde (schnelles Rollen mit wiederholtem Ansetzen)
        # und keiner bei zwei Tipps an verschiedenen Stellen der Zeile
        page.wait_for_timeout(450)
        page.evaluate("() => document.dispatchEvent(new Event('scroll'))")
        erste.tap()
        erste.tap()
        page.wait_for_timeout(450)
        erste.tap(position={"x": 30, "y": 10})
        erste.tap(position={"x": 200, "y": 30})
        expect(tid(page, "panel-details")).to_have_count(0)
        page.wait_for_timeout(450)

        # D-282: lange Berührung auf der eben noch rollenden Liste (mit dem Finger angehalten) öffnet kein Menü
        x, y = _mitte(zweite)
        page.evaluate("() => document.dispatchEvent(new Event('scroll'))")
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        page.wait_for_timeout(700)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(tid(page, "kontextmenue")).to_have_count(0)
        page.wait_for_timeout(400)

        # Lang tippen: Kontextmenü als Blatt – Einzelheiten, Mehrfachauswahl, dann die Einträge des Desktops
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        expect(tid(page, "kontextmenue")).to_be_visible()
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        eintraege = tid(page, "kontextmenue").locator('[role="menuitem"]').evaluate_all("els => els.map((e) => e.dataset.testid)")
        assert eintraege[:3] == ["km-details", "km-auswahl", "km-kategorie"], eintraege
        assert "km-loeschen" in eintraege and "km-status" in eintraege
        assert liste.get_attribute("data-auswahlmodus") != "ja"          # das Menü allein wählt nichts aus
        tid(page, "km-auswahl").click()
        expect(liste).to_have_attribute("data-auswahlmodus", "ja")
        expect(zweite).to_have_attribute("aria-selected", "true")
        tid(page, "auswahl-beenden").click()
        expect(liste).not_to_have_attribute("data-auswahlmodus", "ja")

        # Nach rechts wischen: bestätigt sofort; die Zeile bietet kurz „Rückgängig“ an
        _wischen(cdp, erste, 160)
        rueck = tid(page, "wisch-rueckgaengig")
        expect(rueck).to_be_visible()
        expect(rueck).to_contain_text("Rückgängig")
        assert abs(rueck.bounding_box()["y"] - erste.bounding_box()["y"]) <= 1, "Rückgängig liegt über der Zeile"
        expect(erste).to_have_attribute("data-bestaetigt", "Torsten")
        expect(erste).to_have_attribute("data-status", "bestaetigt")
        rueck.click()
        expect(rueck).to_have_count(0)
        expect(erste).to_have_attribute("data-status", "importiert")
        assert erste.get_attribute("data-bestaetigt") is None
        # schon Bestätigtes bleibt beim Wisch unverändert (das Verschwinden nach drei Sekunden wird hier nicht
        # abgewartet: Zeitbudget des Browser-Jobs)
        _wischen(cdp, erste, 160)
        expect(rueck).to_be_visible()
        expect(erste).to_have_attribute("data-status", "bestaetigt")
        _wischen(cdp, erste, 160)
        expect(rueck).to_have_count(0)
        expect(erste).to_have_attribute("data-bestaetigt", "Torsten")

        # Nach links wischen: Kategorie-Auswahl mit Suche und „Neue Kategorie“
        _wischen(cdp, zweite, -160)
        expect(tid(page, "kategorie-auswahl")).to_be_visible()
        expect(tid(page, "kategorie-auswahl-suche")).to_be_visible()
        expect(tid(page, "kategorie-auswahl").get_by_text("Neue Kategorie")).to_be_visible()


def test_wischen_in_langer_liste_bleibt_an_der_zeile(tmp_path, browser):
    """D-283: In einer langen Liste (nur der sichtbare Ausschnitt ist gezeichnet) liegen Hinweis und „Rückgängig“
    über der gewischten Zeile, und die Ansicht steht nach dem Bestätigen an derselben Stelle."""
    from kontor.importer.kmymoney import importiere_kmy

    from .conftest import GIRO, kmy, transaktion

    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **HANDY) as page:
        # 130 Buchungen in einem Import (schneller als einzeln über REST; Zeitbudget des Browser-Jobs)
        transaktionen = "".join(transaktion(f"T{i}", f"2024-03-{i % 28 + 1:02d}", ("A1", f"-{i + 1}/100"), ("A2", f"{i + 1}/100"),
                                            memo=f"Massen {i}") for i in range(130))
        assert importiere_kmy(config, kmy(GIRO, transaktionen=transaktionen)).erfolgreich
        page.goto(url + "/konten/1")
        bereit(page, "konto")
        page.evaluate("() => { document.querySelector('.hauptbereich').scrollTop = 3000; }")
        page.wait_for_timeout(300)
        bid = page.evaluate("() => document.elementFromPoint(190, 450).closest('[role=row][data-id]').dataset.id")
        zeile = tid(page, f"buchung-{bid}")
        oben = zeile.bounding_box()["y"]
        cdp = page.context.new_cdp_session(page)
        x, y = _mitte(zeile)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        for i in range(1, 9):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + 20 * i, "y": y}]})
        hinweis = page.locator(".wisch-hinweis")
        expect(hinweis).to_be_visible()
        expect(hinweis).to_contain_text("Bestätigen")
        assert abs(hinweis.bounding_box()["y"] - oben) <= 1, "der Hinweis liegt über der gewischten Zeile"
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        rueck = tid(page, "wisch-rueckgaengig")
        expect(rueck).to_be_visible()
        assert abs(rueck.bounding_box()["y"] - oben) <= 1, "Rückgängig liegt über der Zeile"
        expect(zeile).to_have_attribute("data-status", "bestaetigt")
        assert abs(zeile.bounding_box()["y"] - oben) <= 1, "die Ansicht ist nicht gesprungen"
        assert page.evaluate("document.querySelector('.hauptbereich').scrollTop") == 3000
