"""Browser-Rauchtests der Oberfläche (M8, Playwright mit Chrome headless). Werden übersprungen, wenn kein Browser
verfügbar ist. Jeder Test startet einen echten Server im Mock-Modus auf einem freien Loopback-Port (synthetische
Daten) und beendet ihn wieder. Ergänzen die Oberflächentests aus kontor-tests (tests/app/m8), ersetzen sie nicht.
"""

from __future__ import annotations

import contextlib
import re
import datetime as dt
import os
import shutil
import socket
import threading
import time

import pytest

from .conftest import GIRO, kmy, transaktion

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _chrome() -> str | None:
    for name in (os.environ.get("KONTOR_CHROME"), "google-chrome", "chromium", "chromium-browser"):
        if name and shutil.which(name):
            return shutil.which(name)
    return None


@contextlib.contextmanager
def server(basis, *, daten: bool = True, **kw):
    import uvicorn

    from kontor.app import create_app
    from kontor.config import KontorConfig
    from kontor.importer.kmymoney import importiere_kmy

    kw.setdefault("mock_modus", True)
    kw.setdefault("mock_heute", dt.date(2024, 6, 30))
    config = KontorConfig(datenbank=basis / "kontor.sqlite3", **kw)
    if daten:
        transaktionen = "".join(transaktion(f"T{i}", f"2024-01-{i:02d}", ("A1", f"-{i * 100}/100"), ("A2", f"{i * 100}/100"),
                                            memo=f"Einkauf {i}") for i in range(1, 21))
        assert importiere_kmy(config, kmy(GIRO, transaktionen=transaktionen)).erfolgreich
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", config
    finally:
        srv.should_exit = True
        t.join(timeout=30)


@pytest.fixture(scope="module")
def browser():
    sp = playwright.sync_playwright().start()
    try:
        b = sp.chromium.launch(executable_path=_chrome(), headless=True, args=["--no-sandbox", "--no-proxy-server"])
    except Exception as e:  # noqa: BLE001
        sp.stop()
        pytest.skip(f"Kein Browser verfügbar: {e}")
    yield b
    b.close()
    sp.stop()


HANDY = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True, "has_touch": True}
DESKTOP = {"viewport": {"width": 1280, "height": 800}}


@contextlib.contextmanager
def seite(browser, url, **kw):
    ctx = browser.new_context(locale="de-DE", timezone_id="Europe/Berlin", reduced_motion="reduce", **kw)
    ctx.set_default_timeout(10_000)
    page = ctx.new_page()
    fehler: list[str] = []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.on("console", lambda m: fehler.append(m.text) if "Content Security Policy" in m.text else None)
    page.on("request", lambda r: fehler.append("fremd: " + r.url) if not r.url.startswith((url, "data:", "blob:")) else None)
    try:
        yield page
    finally:
        ctx.close()
    assert not fehler, fehler


def tid(page, x):
    return page.get_by_test_id(x)


def bereit(page, name):
    expect(tid(page, "app")).to_have_attribute("data-bereit", "ja")
    expect(tid(page, f"seite-{name}")).to_have_attribute("data-geladen", "ja")


def test_desktop_ablauf(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        expect(tid(page, "mock-hinweis")).to_be_visible()
        expect(page).to_have_title("Finanzübersicht – Kontor")
        page.locator('[data-testid^="uebersicht-konto-"] [data-feld="name"]', has_text="Giro").click()
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        expect(zeilen).to_have_count(20)
        expect(zeilen.first.locator('[data-feld="betrag"]')).to_have_text("-20,00 €")
        # Auswahl wie im Dateimanager, Kontextmenü, Kategorie-Auswahl mit Suche
        zeilen.nth(0).locator('[data-feld="datum"]').click()
        zeilen.nth(3).locator('[data-feld="datum"]').click(modifiers=["Shift"])
        zeilen.nth(6).locator('[data-feld="datum"]').click(modifiers=["Control"])
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "5")
        zeilen.nth(6).click(button="right")
        expect(tid(page, "km-kategorie")).to_be_focused()
        page.keyboard.press("Enter")
        page.keyboard.type("lebens")
        page.keyboard.press("Enter")
        erfolg = page.locator('[data-testid="meldung"][data-art="erfolg"]')
        expect(erfolg.first).to_contain_text("Lebensmittel")
        page.wait_for_load_state("networkidle")   # Neuladen nach der Änderung abwarten (sonst schließt es den Editor)
        # Inline-Bearbeitung und Rückgängig über das Protokoll
        zweck = zeilen.nth(1).locator('[data-feld="verwendungszweck"]')
        alt = zweck.inner_text()
        zweck.dblclick()
        tid(page, "inline-editor").fill("Geändert <b>&</b>")
        page.keyboard.press("Enter")
        expect(zweck).to_have_text("Geändert <b>&</b>")
        page.evaluate("() => document.activeElement.blur()")
        page.keyboard.press("Control+z")
        expect(zweck).to_have_text(alt)
        expect(tid(page, "wiederholen-knopf")).to_be_enabled()
        # Befehlspalette mit Umlautfaltung
        page.keyboard.press("Control+k")
        page.keyboard.type("aenderungsprot")
        page.keyboard.press("Enter")
        bereit(page, "protokoll")
        expect(page.locator('[data-testid^="aenderung-"][data-wirksam]').first).to_be_visible()


def test_panels_und_layout(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/konten/1")
        bereit(page, "konto")
        griff = tid(page, "panel-groesse-kategorien")
        griff.focus()
        page.keyboard.press("ArrowRight")
        expect(griff).to_have_attribute("aria-valuenow", "256")
        tid(page, "panel-verschieben-details").click()
        expect(tid(page, "panel-details")).to_have_attribute("data-bereich", "links")
        page.reload()
        bereit(page, "konto")
        expect(tid(page, "panel-details")).to_have_attribute("data-bereich", "links")
        assert abs(tid(page, "panel-kategorien").bounding_box()["width"] - 256) <= 1


def test_mobil(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/konten/1")
        bereit(page, "konto")
        expect(tid(page, "app")).to_have_attribute("data-layout", "mobil")
        expect(tid(page, "buchungsliste")).to_have_attribute("data-kompakt", "ja")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        # D-141: lange Berührung startet den Auswahlmodus (kein Kontextmenü), sichtbar mit Häkchen und Kopfleiste
        zeile = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]').nth(1)
        box = zeile.bounding_box()
        cdp = page.context.new_cdp_session(page)
        x, y = box["x"] + 60, box["y"] + box["height"] / 2
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        page.wait_for_timeout(700)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(zeile).to_have_attribute("aria-selected", "true")
        expect(tid(page, "kontextmenue")).to_have_count(0)
        expect(tid(page, "panel-details")).to_have_count(0)
        expect(tid(page, "buchungsliste")).to_have_attribute("data-auswahlmodus", "ja")
        expect(tid(page, "auswahl-kopf")).to_be_visible()
        expect(tid(page, "auswahl-kopf-anzahl")).to_have_text("1 ausgewählt")
        # Rückgängig bleibt im Auswahlmodus erreichbar (Kopfleiste liegt darunter)
        kopf = tid(page, "app-kopf").bounding_box()
        assert tid(page, "auswahl-kopf").bounding_box()["y"] >= kopf["y"] + kopf["height"] - 1
        # Wischen nach rechts schaltet die Auswahl einer weiteren Zeile um
        zeile = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]').nth(3)
        box = zeile.bounding_box()
        y = box["y"] + box["height"] / 2
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": 20, "y": y}]})
        for i in range(1, 9):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": 20 + 20 * i, "y": y}]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(zeile).to_have_attribute("aria-selected", "true")
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
        expect(tid(page, "mehrfach-leiste")).to_be_visible()
        expect(tid(page, "auswahl-kopf-anzahl")).to_have_text("2 ausgewählt")
        expect(tid(page, "buchung-erfassen")).to_be_hidden()           # schwebender Knopf im Auswahlmodus weg
        # „Mehr“ öffnet das Kontextmenü der Auswahl als Blatt am unteren Rand
        tid(page, "mehrfach-mehr").click()
        m = tid(page, "kontextmenue")
        expect(m).to_be_visible()
        mb = m.bounding_box()
        assert abs(mb["y"] + mb["height"] - 844) <= 1 and mb["width"] >= 389
        page.keyboard.press("Escape")
        # „Alle“ und die Zurück-Taste beenden bzw. erweitern den Auswahlmodus
        tid(page, "auswahl-alle").click()
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "20")
        page.go_back()
        expect(tid(page, "auswahl-kopf")).to_be_hidden()
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "0")
        expect(tid(page, "buchungsliste")).to_have_attribute("data-auswahlmodus", "nein")
        assert page.url.endswith("/konten/1")
        # ohne Auswahl öffnet Tippen die Einzelheiten
        page.locator('[data-testid="buchungsliste"] [role="row"][data-id]').nth(2).tap()
        expect(tid(page, "panel-details")).to_be_visible()
        tid(page, "details-schliessen").click()
        # Suche als Lupe
        expect(tid(page, "suche-feld")).to_be_hidden()
        tid(page, "suche-knopf").click()
        expect(tid(page, "suche-feld")).to_be_visible()
        expect(tid(page, "suche-feld")).to_be_focused()
        # Menü
        tid(page, "menue-knopf").click()
        tid(page, "nav-einstellungen").click()
        bereit(page, "einstellungen")
        expect(tid(page, "navigation")).to_be_hidden()


def test_mobil_karten_und_wischhinweis(tmp_path, browser):
    """D-141: Tabellen mobil als Karten, Desktop unverändert; beim Wischen zeigt die Zeile die Wirkung an."""
    with server(tmp_path) as (url, _):
        with seite(browser, url, **DESKTOP) as page:
            page.goto(url + "/konten")
            bereit(page, "konten")
            t = tid(page, "kontenbaum")
            expect(t.locator("thead")).to_be_visible()
            assert t.locator("tbody tr").first.evaluate("e => getComputedStyle(e).display") == "table-row"
            expect(tid(page, "tabs-knopf")).to_be_hidden()
            expect(tid(page, "suche-knopf")).to_be_hidden()
        with seite(browser, url, **HANDY) as page:
            page.goto(url + "/konten")
            bereit(page, "konten")
            t = tid(page, "kontenbaum")
            expect(t.locator("thead")).to_be_hidden()
            tr = t.locator("tbody tr").first
            assert tr.evaluate("e => getComputedStyle(e).display") == "flex"
            expect(tr.locator('[data-mk="titel"]')).to_have_count(1)
            expect(tr.locator('[data-mk="betrag"]')).to_have_count(1)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.goto(url + "/konten/1")
            bereit(page, "konto")
            zeile = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]').nth(2)
            box = zeile.bounding_box()
            cdp = page.context.new_cdp_session(page)
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
            for i in range(1, 6):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x - 10 * i, "y": y}]})
            h = page.locator(".wisch-hinweis")
            expect(h).to_be_visible()
            expect(h).to_have_attribute("data-richtung", "links")
            expect(h).to_have_attribute("data-bereit", "nein")
            for i in range(6, 11):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x - 10 * i, "y": y}]})
            expect(h).to_have_attribute("data-bereit", "ja")
            expect(zeile).to_have_class(re.compile(r"\bwischt\b"))
            # langsam (> 1 s) gewischt wirkt mobil trotzdem, weil die Zeile den Zustand angezeigt hat
            page.wait_for_timeout(1100)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            expect(tid(page, "kategorie-auswahl")).to_be_visible()
            expect(h).to_be_hidden()
            expect(zeile).not_to_have_class(re.compile(r"\bwischt\b"))
            # mobil kein Fokus im Textfeld des Blatts (Tastatur erst auf Tippen)
            expect(tid(page, "kategorie-auswahl-suche")).not_to_be_focused()


def test_mobil_wiederkehrend_karten(tmp_path, browser):
    """D-142: wiederkehrende Buchungen mobil als feste Karte; Tippen auf die Karte öffnet die Aktionen."""
    import httpx

    with server(tmp_path, daten=False) as (url, _):
        with httpx.Client(base_url=url, trust_env=False) as c:
            giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
            kat = c.post("/api/konten", json={"name": "Telefon", "art": "aufwand"}).json()["id"]
            e = c.post("/api/empfaenger", json={"name": "Netzfunk Internet und Telefon GmbH (fiktiv)"}).json()["id"]
            for monat in range(1, 7):
                r = c.post("/api/buchungen", json={"datum": f"2024-{monat:02d}-15", "empfaenger_id": e, "splits": [
                    {"konto_id": giro, "betrag": -4539}, {"konto_id": kat, "betrag": 4539}]})
                assert r.status_code == 201, r.text
        with seite(browser, url, **DESKTOP) as page:      # Desktop bleibt eine Tabelle
            page.goto(url + "/wiederkehrend")
            bereit(page, "wiederkehrend")
            t = tid(page, "wiederkehrend-tabelle")
            expect(t.locator("thead")).to_be_visible()
            assert t.locator("tbody tr").first.evaluate("e => getComputedStyle(e).display") == "table-row"
        with seite(browser, url, **HANDY) as page:
            page.goto(url + "/wiederkehrend")
            bereit(page, "wiederkehrend")
            t = tid(page, "wiederkehrend-tabelle")
            expect(t.locator("thead")).to_be_hidden()
            tr = t.locator("tbody tr").first
            titel, betrag, jahr = (tr.locator(f'[data-mk="{m}"]').bounding_box() for m in ("titel", "betrag", "wk-jahr"))
            karte = tr.bounding_box()
            assert abs(titel["y"] - betrag["y"]) < 8, "Empfänger und Betrag in einer Zeile"
            assert jahr["y"] > betrag["y"] + 10, "Jahreskosten darunter"
            assert abs((betrag["x"] + betrag["width"]) - (jahr["x"] + jahr["width"])) < 2, "Beträge rechtsbündig untereinander"
            assert karte["x"] + karte["width"] - (betrag["x"] + betrag["width"]) < 24, "Betrag am rechten Rand"
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            tr.locator('[data-mk="titel"]').tap()
            expect(tid(page, "km-serie-begruendung")).to_be_visible()


def test_service_worker_und_offline(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/kategorien")
        bereit(page, "kategorien")
        page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
        page.reload()
        bereit(page, "kategorien")
        page.context.set_offline(True)
        page.goto(url + "/konten")
        expect(tid(page, "offline-hinweis")).to_be_visible()
        page.context.set_offline(False)
        page.evaluate("() => window.dispatchEvent(new Event('online'))")
        bereit(page, "konten")
        expect(tid(page, "offline-hinweis")).to_be_hidden()


def test_ueber_fenster(tmp_path, browser):
    """D-105: Klick auf die Versionsnummer öffnet das About-Fenster (Desktop und mobil über das Menü)."""
    import kontor
    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        knopf = tid(page, "version-knopf")
        expect(knopf).to_have_text(f"Version {kontor.__version__}")
        knopf.click()
        expect(tid(page, "ueber-dialog")).to_be_visible()
        expect(tid(page, "ueber-version")).to_have_text(f"Version {kontor.__version__}")
        expect(tid(page, "ueber-modus")).to_have_text("Mock-Modus")
        expect(tid(page, "ueber-datenbank")).to_have_text(str(config.aktive_datenbank.resolve()))
        expect(tid(page, "ueber-schliessen")).to_be_focused()
        page.keyboard.press("Escape")
        expect(tid(page, "ueber-dialog")).to_have_count(0)
        expect(knopf).to_be_focused()
    with server(tmp_path / "m", daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        tid(page, "menue-knopf").click()
        tid(page, "version-knopf").click()
        expect(tid(page, "ueber-dialog")).to_be_visible()
        expect(tid(page, "navigation")).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        tid(page, "ueber-schliessen").click()
        expect(tid(page, "ueber-dialog")).to_have_count(0)
        expect(tid(page, "menue-knopf")).to_be_focused()


# ------------------------------------------------------------------ Sammelpaket (D-108 bis D-113)
def test_sammelpaket_loeschen_verschieben_bis(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        page.evaluate("""() => fetch('/api/konten', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'Zweitkonto', art: 'sparkonto'})})""")
        page.locator('[data-testid^="uebersicht-konto-"] [data-feld="name"]', has_text="Giro").click()
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        # drei Buchungen verschieben: eine Änderung
        zeilen.nth(0).locator('[data-feld="datum"]').click()
        zeilen.nth(2).locator('[data-feld="datum"]').click(modifiers=["Shift"])
        tid(page, "mehrfach-verschieben").click()
        tid(page, "verschieben-ziel").select_option(label="Zweitkonto")
        tid(page, "verschieben-ok").click()
        expect(zeilen).to_have_count(17)
        # zwei Buchungen löschen: eine Änderung
        zeilen.nth(0).locator('[data-feld="datum"]').click()
        zeilen.nth(1).locator('[data-feld="datum"]').click(modifiers=["Shift"])
        tid(page, "mehrfach-loeschen").dispatch_event("click")   # Erfolgsmeldung liegt über der Leiste
        tid(page, "bestaetigen-ja").click()
        expect(zeilen).to_have_count(15)
        page.goto(url + "/protokoll")
        bereit(page, "protokoll")
        eintraege = tid(page, "protokoll-liste").locator("li")
        expect(eintraege.nth(0)).to_contain_text("Mehrere Buchungen gelöscht")
        expect(eintraege.nth(1)).to_contain_text("auf anderes Konto verschoben")
        # Rückgängig bis einschließlich „verschieben“
        eintraege.nth(1).locator('[data-testid^="aenderung-bis-"]').click()
        tid(page, "bestaetigen-ja").click()
        expect(eintraege.nth(0)).to_contain_text("Rückgängig")
        page.goto(url + "/")
        bereit(page, "uebersicht")
        page.locator('[data-testid^="uebersicht-konto-"] [data-feld="name"]', has_text="Giro").click()
        bereit(page, "konto")
        expect(zeilen).to_have_count(20)


def test_sammelpaket_berichte_plotly(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/berichte")
        bereit(page, "berichte")
        tid(page, "bericht-konten").select_option(label="Giro")
        tid(page, "bericht-von").fill("2024-01-01")
        tid(page, "bericht-von").dispatch_event("change")
        diagramm = tid(page, "bericht-diagramm")
        expect(diagramm).to_have_attribute("role", "img")
        expect(diagramm.locator(".main-svg").first).to_be_visible()
        expect(diagramm).to_have_attribute("data-reihen", "1")


def test_plotly_tooltip_im_dunklen_thema(tmp_path, browser):
    """Tooltip-Hintergrund und -Schrift folgen dem Thema (sonst helle Schrift auf hellem Grund)."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/berichte")
        page.evaluate("localStorage.setItem('kontor.thema', 'dunkel')")
        page.reload()
        bereit(page, "berichte")
        assert page.evaluate("document.documentElement.dataset.thema") == "dunkel"
        tid(page, "bericht-konten").select_option(label="Giro")
        tid(page, "bericht-von").fill("2024-01-01")
        tid(page, "bericht-von").dispatch_event("change")
        diagramm = tid(page, "bericht-diagramm")
        expect(diagramm.locator(".main-svg").first).to_be_visible()
        farben = diagramm.evaluate("""(el) => {
            const p = el.querySelector('.js-plotly-plot') || el;
            const cs = getComputedStyle(document.documentElement);
            const h = p._fullLayout.hoverlabel;
            return { bg: h.bgcolor, schrift: h.font.color,
                     hg: cs.getPropertyValue('--hg').trim(), text: cs.getPropertyValue('--text').trim() };
        }""")
        assert farben["bg"].lower() == farben["hg"].lower() == "#15181c"
        assert farben["schrift"].lower() == farben["text"].lower()


def _bericht_giro(page, url):
    page.goto(url + "/berichte")
    bereit(page, "berichte")
    tid(page, "bericht-konten").select_option(label="Giro")
    tid(page, "bericht-von").fill("2024-01-01")
    tid(page, "bericht-von").dispatch_event("change")
    expect(tid(page, "bericht-diagramm").locator(".main-svg").first).to_be_visible()
    # monatlich bis zum Mock-Heute 30.06.2024: 01.01., 31.01., 29.02., …, 30.06.
    expect(tid(page, "bericht-tabelle").locator("tbody tr")).to_have_count(7)


def test_bericht_tabelle_folgt_dem_zoom(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        _bericht_giro(page, url)
        zeilen = tid(page, "bericht-tabelle").locator("tbody tr")
        hinweis = tid(page, "bericht-zoom-hinweis")
        expect(hinweis).to_be_hidden()
        tid(page, "bericht-diagramm").evaluate(
            "(el) => Plotly.relayout(el, {'xaxis.range': ['2024-02-15', '2024-04-15']})")
        expect(zeilen.locator("visible=true")).to_have_count(2)
        expect(tid(page, "bericht-zeile-2024-02-29")).to_be_visible()
        expect(tid(page, "bericht-zeile-2024-03-31")).to_be_visible()
        expect(tid(page, "bericht-zeile-2024-01-31")).to_be_hidden()
        expect(hinweis).to_be_visible()
        expect(hinweis).to_contain_text("15.02.2024 – 15.04.2024 (2 von 7 Zeilen)")
        # Doppelklick ins Diagramm = Autorange: wieder alles
        tid(page, "bericht-diagramm").evaluate("(el) => Plotly.relayout(el, {'xaxis.autorange': true})")
        expect(zeilen.locator("visible=true")).to_have_count(7)
        expect(hinweis).to_be_hidden()


def test_bericht_zeile_aufklappen_und_zur_buchung_springen(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        _bericht_giro(page, url)
        zeile = tid(page, "bericht-zeile-2024-01-31")
        expect(zeile.locator("th")).to_have_text("31.01.2024")          # Text der Zelle unverändert
        knopf = tid(page, "bericht-aufklappen-1")
        expect(knopf).to_have_attribute("aria-expanded", "false")
        knopf.click()
        expect(knopf).to_have_attribute("aria-expanded", "true")
        details = tid(page, "bericht-details-1")
        buchungen = details.locator('[data-testid^="bericht-buchung-"][data-id]')
        expect(buchungen).to_have_count(19)                              # 02.01. bis 20.01.; 01.01. gehört zu Zeile 0
        erste = buchungen.first
        expect(erste).to_contain_text("02.01.2024")
        expect(erste).to_contain_text("-2,00 €")
        bid = erste.get_attribute("data-id")
        sprung = erste.locator('a[data-testid^="bericht-buchung-"]').first
        expect(sprung).to_have_text("Giro")                              # gewähltes Konto zuerst
        # Zuklappen und wieder aufklappen ohne neue Anfrage
        knopf.click()
        expect(details).to_be_hidden()
        knopf.click()
        expect(details).to_be_visible()
        sprung.click()
        bereit(page, "konto")
        markiert = page.locator('[data-testid="buchungsliste"] [role="row"][aria-selected="true"]')
        expect(markiert).to_have_count(1)
        expect(markiert).to_have_attribute("data-id", bid)


def test_bericht_ea_zeile_aufklappen(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        _bericht_giro(page, url)
        page.get_by_role("button", name="Einnahmen und Ausgaben berechnen").click()
        expect(tid(page, "bericht-ea-diagramm")).to_be_visible()
        tid(page, "bericht-ea-aufklappen-0").click()
        details = tid(page, "bericht-ea-details-0")
        expect(details.locator('[data-testid^="bericht-ea-buchung-"][data-id]')).to_have_count(20)


def test_bericht_sprung_in_schon_offenen_kontotab(tmp_path, browser):
    """Ist das Konto schon als Tab offen (mit anderer Auswahl), steht der Cursor danach auf der Berichtsbuchung."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/konten/1")
        bereit(page, "konto")
        liste = tid(page, "buchungsliste")
        andere = liste.locator('[role="row"][data-id]').first
        andere.click()
        expect(andere).to_have_attribute("aria-selected", "true")
        andere_id = andere.get_attribute("data-id")
        page.get_by_role("link", name="Berichte").first.click()
        bereit(page, "berichte")
        tid(page, "bericht-konten").select_option(label="Giro")
        tid(page, "bericht-von").fill("2024-01-01")
        tid(page, "bericht-von").dispatch_event("change")
        tid(page, "bericht-aufklappen-1").click()
        ziel = tid(page, "bericht-details-1").locator('[data-testid^="bericht-buchung-"][data-id]').nth(5)
        bid = ziel.get_attribute("data-id")
        assert bid != andere_id
        ziel.locator('a[data-testid$="-konto-1"]').click()
        bereit(page, "konto")
        markiert = liste.locator('[role="row"][aria-selected="true"]')
        expect(markiert).to_have_count(1)
        expect(markiert).to_have_attribute("data-id", bid)
        expect(markiert).to_be_focused()
        assert page.evaluate("location.pathname") == "/konten/1"


def test_bericht_sprung_mobil_mit_nachladen_nicht_verdeckt(tmp_path, browser):
    """Mobil, Ziel erst nach dem Nachladen in der Liste: Zeile gewählt, fokussiert und nicht von der Mehrfachleiste
    verdeckt (D-129)."""
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        import httpx
        with httpx.Client(base_url=url) as c:
            for i in range(450):   # neuere Buchungen davor, damit die Kontoansicht nachladen muss
                d = dt.date(2024, 3, 1) + dt.timedelta(days=i % 28)
                r = c.post("/api/buchungen", json={"datum": d.isoformat(), "verwendungszweck": f"Massen {i}",
                                                   "splits": [{"konto_id": 1, "betrag": -(i + 1)}, {"konto_id": 2, "betrag": i + 1}]})
                assert r.status_code in (200, 201), r.text
        page.goto(url + "/berichte")
        bereit(page, "berichte")
        tid(page, "bericht-konten").select_option(label="Giro")
        tid(page, "bericht-von").fill("2024-01-01")
        tid(page, "bericht-von").dispatch_event("change")
        tid(page, "bericht-aufklappen-1").click()
        ziel = tid(page, "bericht-details-1").locator('[data-testid^="bericht-buchung-"][data-id]').nth(12)
        bid = ziel.get_attribute("data-id")
        ziel.locator('a[data-testid$="-konto-1"]').click()
        bereit(page, "konto")
        markiert = tid(page, "buchungsliste").locator('[role="row"][aria-selected="true"]')
        expect(markiert).to_have_attribute("data-id", bid)
        expect(markiert).to_be_focused()
        page.wait_for_timeout(300)
        assert markiert.evaluate("""(r) => {
            const b = r.getBoundingClientRect();
            const m = document.querySelector('[data-testid=mehrfach-leiste]');
            const unten = m && !m.hidden ? m.getBoundingClientRect().top : innerHeight;
            const oben = document.elementFromPoint(b.left + 5, b.top + b.height / 2);
            return b.top >= 0 && b.bottom <= unten && !!oben && oben.closest('[data-id]') === r;
        }""")
