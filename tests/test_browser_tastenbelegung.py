"""Entwicklungstests für das Feature „tastenbelegung“ (D-292): systematische Tastenbelegung.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _daten, _get

ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]'


def _giro(url):
    return next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")


def _filter(page):
    return parse_qs(urlparse(page.url).query).get("filter", [""])[0]


def _warte_filter(page, soll):
    for _ in range(100):
        if _filter(page) == soll:
            return
        page.wait_for_timeout(50)
    assert _filter(page) == soll


def _taste(page, *tasten):
    for t in tasten:
        page.keyboard.press(t)


def test_u_und_d_bewegen_die_markierung_im_kontoblatt(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(url)}")
        bereit(page, "konto")
        zeilen = page.locator(ZEILEN)
        zeilen.nth(2).locator('[data-feld="datum"]').click()
        page.keyboard.press("d")
        expect(zeilen.nth(3)).to_be_focused()
        expect(zeilen.nth(3)).to_have_attribute("aria-selected", "true")
        expect(zeilen.nth(2)).to_have_attribute("aria-selected", "false")
        _taste(page, "u", "u")
        expect(zeilen.nth(1)).to_be_focused()
        # U/D markieren einen Bereich
        _taste(page, "D", "D")
        expect(zeilen.nth(3)).to_be_focused()
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "3")
        # d ist keine Dublette mehr: kein Dialog
        expect(tid(page, "dublette-dialog")).to_have_count(0)
        # Fokus außerhalb der Liste: der erste Druck führt in die Liste
        _taste(page, "w", "a")
        expect(tid(page, "buchung-erfassen")).to_be_focused()
        page.keyboard.press("d")
        expect(page.locator(f"{ZEILEN}:focus")).to_have_count(1)


def test_dublette_auf_X_und_alte_folgen_sind_nicht_belegt(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(url)}")
        bereit(page, "konto")
        zeilen = page.locator(ZEILEN)
        zeilen.nth(1).locator('[data-feld="datum"]').click()
        zeilen.nth(2).locator('[data-feld="datum"]').click(modifiers=["Control"])
        page.keyboard.press("X")
        expect(tid(page, "dublette-dialog")).to_be_visible()
        page.keyboard.press("Escape")
        expect(tid(page, "dublette-dialog")).to_have_count(0)
        meldungen = tid(page, "meldungen")
        for vor, taste in (("f", "j"), ("f", "l"), ("f", "h"), ("f", "."), ("v", "d"), ("v", ","), ("v", "+")):
            zeilen.nth(1).locator('[data-feld="datum"]').click()
            _taste(page, vor, taste)
            expect(meldungen).to_contain_text(f"„{vor} {taste}“ ist nicht belegt")


def test_zeitraeume_klein_dieser_gross_letzter(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(url)}")
        bereit(page, "konto")
        erste = page.locator(ZEILEN).first.locator('[data-feld="datum"]')
        for taste, teil in (("t", "datum == heute"), ("T", "datum == gestern"), ("w", "datum in diese_woche"),
                            ("W", "datum in letzte_woche"), ("m", "datum in dieser_monat"), ("M", "datum in letzter_monat"),
                            ("q", "datum in dieses_quartal"), ("Q", "datum in letztes_quartal"),
                            ("y", "datum in dieses_jahr"), ("Y", "datum in letztes_jahr")):
            page.evaluate("() => document.activeElement && document.activeElement.blur()")
            _taste(page, "f", taste)
            _warte_filter(page, teil)
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _taste(page, "f", "x")
        _warte_filter(page, "")
        erste.click()


def test_filter_wie_die_markierte_buchung(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(url)}")
        bereit(page, "konto")
        zeile = page.locator(ZEILEN).nth(4)
        betrag = int(zeile.locator('[data-feld="betrag"] [data-betrag], [data-feld="betrag"][data-betrag]').first
                     .get_attribute("data-betrag"))
        euro = f"{abs(betrag) // 100}.{abs(betrag) % 100:02d}"
        richtung = "ausgabe" if betrag < 0 else "einnahme"
        zeile.locator('[data-feld="datum"]').click()
        _taste(page, "f", "b")
        _warte_filter(page, f'bet == {euro} and dir == "{richtung}"')
        expect(page.locator(ZEILEN)).to_have_count(1)
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        _taste(page, "f", "B")
        _warte_filter(page, f"bet == {euro}")
        # Kontextmenü „Filter“ mit denselben Einträgen
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click(button="right")
        tid(page, "km-filter").click()
        for k in ("km-filter-empfaenger", "km-filter-zweck", "km-filter-zweck-aehnlich", "km-filter-empfaenger-aehnlich",
                  "km-filter-betrag", "km-filter-betrag-absolut"):
            expect(tid(page, k)).to_be_visible()
        tid(page, "km-filter-betrag").click()
        _warte_filter(page, f'bet == {euro} and dir == "{richtung}"')
        # ohne markierte Buchung: Hinweis
        page.keyboard.press("Escape")
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        page.keyboard.press("Escape")


def test_ansicht_ohne_satzzeichen(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(url)}?gruppierung=datum&tiefe=monat")
        bereit(page, "konto")
        liste = tid(page, "buchungsliste")
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        _taste(page, "v", "K")
        expect(page.locator(ZEILEN)).to_have_count(0)
        expect(liste.locator(".perioden-knopf[aria-expanded='false']").first).to_be_visible()
        liste.locator(".perioden-knopf").first.focus()
        _taste(page, "v", "k")
        expect(page.locator(ZEILEN).first).to_be_visible()
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        _taste(page, "v", "e")
        expect(tid(page, "konto-einstellungen")).to_be_visible()


def test_tastaturhilfe_je_blatt(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(url)}")
        bereit(page, "konto")
        page.locator(ZEILEN).first.locator('[data-feld="datum"]').click()
        # ? öffnet die Hilfe nicht mehr, / nicht die Suche
        page.keyboard.press("?")
        page.keyboard.press("/")
        expect(tid(page, "tastatur-hilfe")).to_have_count(0)
        expect(tid(page, "suche-feld")).not_to_be_focused()
        page.keyboard.press("h")
        hilfe = tid(page, "tastatur-hilfe")
        expect(hilfe).to_be_visible()
        expect(tid(page, "tastatur-hilfe-blatt")).to_have_attribute("data-blatt", "konto")
        for t in ("tastatur-hilfe-ueberall", "tastatur-hilfe-bereiche", "tastatur-hilfe-liste", "tastatur-hilfe-aktionen",
                  "tastatur-hilfe-filter", "tastatur-hilfe-ansicht"):
            expect(tid(page, t)).to_be_visible()
        expect(tid(page, "tastatur-hilfe-liste")).to_contain_text("u d")
        expect(tid(page, "tastatur-hilfe-bereiche")).to_contain_text("Aktionen")
        # eine Buchung markiert: „f e“ wirkt; ohne Person grau wäre b (Person ist gesetzt)
        filter = tid(page, "tastatur-hilfe-filter")
        expect(filter.locator("tr", has_text=re.compile("^f e"))).not_to_have_class("inaktiv")
        expect(tid(page, "tastatur-hilfe-aktionen").locator("tr.inaktiv")).to_have_count(0)
        assert "?" not in tid(page, "tastatur-hilfe-ueberall").inner_text()
        page.keyboard.press("Escape")
        # zwei Buchungen markiert: die Kürzel für genau eine sind grau
        page.locator(ZEILEN).nth(1).locator('[data-feld="datum"]').click(modifiers=["Control"])
        page.keyboard.press("h")
        expect(filter.locator("tr.inaktiv", has_text=re.compile("^f e"))).to_have_count(1)
        expect(tid(page, "tastatur-hilfe-aktionen").locator("tr.inaktiv", has_text="Splitten")).to_have_count(1)
        page.keyboard.press("Escape")
        # Kategorienbaum: keine Kürzel des Kontoblatts, dafür die Tasten des Baums
        page.goto(url + "/kategorien")
        bereit(page, "kategorien")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("h")
        expect(tid(page, "tastatur-hilfe-blatt")).to_have_attribute("data-blatt", "kategorien")
        expect(tid(page, "tastatur-hilfe-liste")).to_contain_text("zu- / aufklappen")
        expect(tid(page, "tastatur-hilfe-aktionen")).to_have_count(0)
        expect(tid(page, "tastatur-hilfe-weitere")).to_be_hidden()
        tid(page, "tastatur-hilfe-alle").check()
        expect(tid(page, "tastatur-hilfe-weitere")).to_be_visible()
        expect(tid(page, "tastatur-hilfe-alle-filter")).to_be_visible()


def test_w_je_blatt_und_u_d_in_anderen_listen(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)   # mehrere Bestandskonten
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("w")
        hinweis = tid(page, "kuerzel-hinweis")
        expect(hinweis).to_contain_text("Kontentabelle")
        expect(hinweis).to_contain_text("Kategorientabellen")
        expect(hinweis).not_to_contain_text("Aktionen")   # die Finanzübersicht hat keine Knöpfe im Kopf
        page.keyboard.press("b")
        tabelle = tid(page, "uebersicht-tabelle")
        zeilen = tabelle.locator("tr[tabindex]")
        expect(zeilen.first).to_be_focused()
        page.keyboard.press("d")
        expect(zeilen.nth(1)).to_be_focused()
        page.keyboard.press("u")
        expect(zeilen.first).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(zeilen.nth(1)).to_be_focused()
        # Einstellungen: w f führt in die Suche, w b in die Liste der Bereiche
        page.goto(url + "/einstellungen")
        bereit(page, "einstellungen")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _taste(page, "w", "f")
        expect(tid(page, "einstellungen-suche")).to_be_focused()
        page.keyboard.press("Escape")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _taste(page, "w", "b")
        expect(tid(page, "einstellungen-nav").locator(":focus")).to_have_count(1)
        # Konten: d führt zuerst in den Baum, danach bewegt es
        page.goto(url + "/konten")
        bereit(page, "konten")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        _taste(page, "w", "a")
        expect(tid(page, "konto-anlegen")).to_be_focused()
        page.keyboard.press("d")
        baum = tid(page, "kontenbaum")
        expect(baum.locator(":focus")).to_have_count(1)
        vorher = page.evaluate("() => document.activeElement.textContent")
        page.keyboard.press("d")
        assert page.evaluate("() => document.activeElement.textContent") != vorher


def test_u_d_im_kategorienbaum(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/kategorien")
        bereit(page, "kategorien")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("d")                       # erst in den Baum
        eintraege = tid(page, "kategorienbaum").locator('[role="treeitem"]')
        expect(eintraege.first).to_be_focused()
        page.keyboard.press("d")
        expect(eintraege.nth(1)).to_be_focused()
        page.keyboard.press("u")
        expect(eintraege.first).to_be_focused()


def test_u_d_in_der_empfaengerliste(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        import httpx
        with httpx.Client(trust_env=False) as c:
            for name in ("Laden A (fiktiv)", "Laden B (fiktiv)", "Laden C (fiktiv)"):
                assert c.post(url + "/api/empfaenger", json={"name": name}).status_code == 201
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.keyboard.press("d")
        zeilen = tid(page, "empfaenger-liste").locator("tr[data-id]")
        expect(zeilen.first).to_be_focused()
        _taste(page, "d", "D")
        expect(zeilen.nth(2)).to_be_focused()
        expect(tid(page, "empfaenger-auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
        _taste(page, "w", "f")
        expect(tid(page, "empfaenger-suche")).to_be_focused()
