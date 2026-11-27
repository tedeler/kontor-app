"""Entwicklungstests für das Feature „kategorien-uebersicht“ (D-311): neue Kategorienseite mit Kennzahlen, Beträgen,
Suche, Zeitraum, Sortierung und Knöpfen je Zeile. Playwright mit Chrome headless gegen einen echten Server im
Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import datetime as dt

import httpx

from .test_browser import (  # noqa: F401
    DESKTOP,
    HANDY,
    bereit,
    browser,
    expect,
    seite,
    server,
    tid,
)


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        def konto(name, art, eltern=None, iban=None):
            r = c.post(url + "/api/konten", json={"name": name, "art": art, "eltern_id": eltern, "iban": iban})
            assert r.status_code == 201, r.text
            return r.json()["id"]

        giro = konto("Giro KU", "girokonto", iban="DE57000000000004711009")
        k = {"wohnen": konto("Wohnen", "aufwand")}
        k["miete"] = konto("Miete", "aufwand", k["wohnen"])
        k["lebensmittel"] = konto("Lebensmittel", "aufwand")
        k["gehalt"] = konto("Gehalt", "ertrag")

        def buchen(datum, kat, betrag):
            r = c.post(url + "/api/buchungen", json={"datum": datum, "verwendungszweck": f"KU {datum}",
                                                     "splits": [{"konto_id": giro, "betrag": -betrag},
                                                                {"konto_id": k[kat], "betrag": betrag}]})
            assert r.status_code == 201, r.text

        for m in (4, 5, 6):
            buchen(f"2026-{m:02d}-03", "miete", 98_000)
            buchen(f"2026-{m:02d}-01", "gehalt", -285_000)
        buchen("2026-06-10", "lebensmittel", 150_000)   # im Juni größer als die Miete
    return giro, k


def test_kategorienseite(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2026, 6, 20)) as (url, _), \
            seite(browser, url, **DESKTOP) as page:
        giro, k = _welt(url)
        page.goto(f"{url}/kategorien")
        bereit(page, "kategorien")
        # Beträge (12 Monate), Unterkategorien zählen mit, Einnahmen positiv
        expect(tid(page, f"kategorie-summe-{k['miete']}")).to_have_attribute("data-betrag", "294000")
        expect(tid(page, f"kategorie-summe-{k['wohnen']}")).to_have_attribute("data-betrag", "294000")
        expect(tid(page, f"kategorie-summe-{k['gehalt']}")).to_have_attribute("data-betrag", "855000")
        expect(tid(page, "kategorien-summe-aufwand")).to_have_attribute("data-betrag", "444000")
        expect(tid(page, "kategorien-kachel-saldo").locator("[data-betrag]")).to_have_attribute("data-betrag", "411000")
        # Zeitraum: dieser Monat, in der Adresse vermerkt
        tid(page, "kategorien-zeitraum-monat").click()
        expect(tid(page, f"kategorie-summe-{k['miete']}")).to_have_attribute("data-betrag", "98000")
        expect(tid(page, "kategorien-zeitraum-monat")).to_have_attribute("aria-checked", "true")
        assert page.url.endswith("/kategorien?zeitraum=monat")
        # D-315: letzter Monat und 30 Tage (heute 20.06.: 22.05. bis 20.06.)
        tid(page, "kategorien-zeitraum-vormonat").click()
        expect(tid(page, f"kategorie-summe-{k['lebensmittel']}")).to_have_attribute("data-betrag", "0")
        expect(tid(page, f"kategorie-summe-{k['miete']}")).to_have_attribute("data-betrag", "98000")
        tid(page, "kategorien-zeitraum-30tage").click()
        expect(tid(page, f"kategorie-summe-{k['gehalt']}")).to_have_attribute("data-betrag", "285000")
        expect(tid(page, "kategorien-kachel-ausgaben")).to_contain_text("22.05. – 20.06.2026")
        assert page.url.endswith("/kategorien?zeitraum=30tage")
        tid(page, "kategorien-zeitraum-monat").click()
        expect(tid(page, f"kategorie-summe-{k['miete']}")).to_have_attribute("data-betrag", "98000")
        # Sortierung nach Betrag: Lebensmittel (1.500) vor Wohnen (980) – nach Name umgekehrt
        reihen = lambda: [x for x in page.locator('[data-testid="kategorienbaum"] [role="treeitem"][aria-level="1"]')
                          .evaluate_all("els => els.map(e => e.getAttribute('aria-label'))") if x != "Gehalt"]
        assert reihen() == ["Lebensmittel", "Wohnen"]
        tid(page, "kategorien-sortierung-betrag").click()
        expect(tid(page, "kategorien-sortierung-betrag")).to_have_attribute("aria-checked", "true")
        assert reihen() == ["Lebensmittel", "Wohnen"]
        tid(page, "kategorien-zeitraum-12monate").click()
        expect(tid(page, f"kategorie-summe-{k['miete']}")).to_have_attribute("data-betrag", "294000")
        assert reihen() == ["Wohnen", "Lebensmittel"]
        tid(page, "kategorien-sortierung-name").click()
        # Suche: Treffer mit Vorfahren, andere verschwinden; ohne Treffer anlegen
        tid(page, "kategorien-suche").fill("mie")
        expect(tid(page, f"kategorie-{k['miete']}")).to_be_visible()
        expect(tid(page, f"kategorie-{k['wohnen']}")).to_be_visible()
        expect(tid(page, f"kategorie-{k['lebensmittel']}")).to_have_count(0)
        expect(tid(page, f"kategorie-{k['miete']}").locator("mark")).to_have_text("Mie")
        tid(page, "kategorien-suche").fill("Spenden")
        tid(page, "kategorien-treffer-anlegen").click()
        expect(tid(page, "konto-name")).to_have_value("Spenden")
        page.keyboard.press("Escape")
        tid(page, "kategorien-suche").focus()
        page.keyboard.press("Escape")
        expect(tid(page, f"kategorie-{k['lebensmittel']}")).to_be_visible()
        # Zuklappen / Aufklappen
        tid(page, "kategorien-zuklappen").click()
        expect(tid(page, f"kategorie-{k['wohnen']}")).to_have_attribute("aria-expanded", "false")
        tid(page, "kategorien-aufklappen").click()
        expect(tid(page, f"kategorie-{k['wohnen']}")).to_have_attribute("aria-expanded", "true")
        # Knöpfe je Zeile: Menü und Öffnen
        tid(page, f"kategorie-{k['lebensmittel']}").hover()
        tid(page, f"kategorie-menue-{k['lebensmittel']}").click()
        expect(tid(page, "km-konto-umbenennen")).to_be_visible()
        page.keyboard.press("Escape")
        tid(page, f"kategorie-{k['lebensmittel']}").hover()
        tid(page, f"kategorie-oeffnen-{k['lebensmittel']}").click()
        bereit(page, "konto")
        assert page.url.endswith(f"/konten/{k['lebensmittel']}")


def test_handy_ohne_waagrechtes_scrollen(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2026, 6, 20)) as (url, _), \
            seite(browser, url, **HANDY) as page:
        _, k = _welt(url)
        page.goto(f"{url}/kategorien")
        bereit(page, "kategorien")
        expect(tid(page, f"kategorie-menue-{k['miete']}")).to_be_visible()
        breite = page.evaluate("() => [document.querySelector('[data-testid=kategorienbaum]').scrollWidth, window.innerWidth]")
        assert breite[0] <= breite[1], breite


def test_leerzustand(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2026, 6, 20)) as (url, _), \
            seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/kategorien")
        bereit(page, "kategorien")
        expect(tid(page, "kategorien-leer")).to_be_visible()
        tid(page, "kategorien-leer-anlegen").click()
        tid(page, "konto-name").fill("Haushalt")
        tid(page, "konto-speichern").click()
        expect(tid(page, "kategorienbaum")).to_be_visible()
        expect(tid(page, "kategorien-leer")).to_have_count(0)
