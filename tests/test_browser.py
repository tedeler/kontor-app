"""Browser-Rauchtests der Oberfläche (M8, Playwright mit Chrome headless). Werden übersprungen, wenn kein Browser
verfügbar ist. Jeder Test startet einen echten Server im Mock-Modus auf einem freien Loopback-Port (synthetische
Daten) und beendet ihn wieder. Ergänzen die Oberflächentests aus kontor-tests (tests/app/m8), ersetzen sie nicht.
"""

from __future__ import annotations

import contextlib
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
        # lange Berührung öffnet das Kontextmenü
        zeile = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]').nth(1)
        box = zeile.bounding_box()
        cdp = page.context.new_cdp_session(page)
        x, y = box["x"] + 60, box["y"] + box["height"] / 2
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        page.wait_for_timeout(700)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        expect(tid(page, "kontextmenue")).to_be_visible()
        page.keyboard.press("Escape")
        expect(zeile).to_have_attribute("aria-selected", "true")      # wie Rechtsklick: Auswahl = diese Zeile
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
        # Menü
        tid(page, "menue-knopf").click()
        tid(page, "nav-einstellungen").click()
        bereit(page, "einstellungen")
        expect(tid(page, "navigation")).to_be_hidden()


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
