"""Browser-Rauchtest der M2-Oberfläche (Playwright, Chrome headless): Synchronisation, Regeln,
Vorschläge, TAN-Seite und Benachrichtigungen. Wird übersprungen, wenn kein Browser verfügbar ist.

Echte Server im Mock-Modus (eingebauter synthetischer Datensatz, simuliertes „heute“) auf freien
lokalen Ports; es wird nie eine Bank angesprochen.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import socket
import threading
import time

import pytest

from .test_browser import _chrome

playwright = pytest.importorskip("playwright.sync_api")


@contextlib.contextmanager
def _server(basis, szenario: str):
    import uvicorn

    from kontor.app import create_app
    from kontor.config import KontorConfig

    config = KontorConfig(datenbank=basis / "kontor.sqlite3", mock_modus=True, mock_szenario=szenario,
                          mock_heute=dt.date(2024, 6, 30))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.should_exit = True
        t.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    sp = playwright.sync_playwright().start()
    try:
        b = sp.chromium.launch(executable_path=_chrome(), headless=True, args=["--no-sandbox"])
    except Exception as e:  # noqa: BLE001
        sp.stop()
        pytest.skip(f"Kein Browser verfügbar: {e}")
    yield b
    b.close()
    sp.stop()


def _neue_seite(browser, **kw):
    page = browser.new_page(**kw)
    fehler: list[str] = []
    page.on("pageerror", lambda e: fehler.append(str(e)))
    return page, fehler


def test_regel_sync_und_vorschlaege(tmp_path, browser):
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport={"width": 1280, "height": 900})
        page.request.post(url + "/api/konten", data={"name": "Lebensmittel", "art": "aufwand"})
        # Regel über den Dialog anlegen
        page.goto(url + "/#/regeln")
        page.locator("button", has_text="+ Regel anlegen").click()
        page.fill(".dialog input[type=text]", "Supermarkt")
        page.select_option(".dialog select[required]", label="Lebensmittel (Aufwand)")
        page.locator(".dialog .bed-zeile input").fill("Frischekorb")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector("table.tabelle td:has-text('Supermarkt')")
        assert "Empfänger enthält „Frischekorb“" in page.locator("#inhalt").inner_text()
        # Synchronisation auslösen
        page.goto(url + "/#/sync")
        page.locator("button", has_text="Jetzt synchronisieren").click()
        page.wait_for_selector(".meldung:has-text('erfolgreich')")
        page.wait_for_selector("text=Girokonto (Mock)")
        assert page.locator(".lauf-erfolgreich").count() >= 1
        # Vorschläge in der Buchungsliste erkennen und bestätigen
        page.goto(url + "/#/buchungen?vorschlag=true")
        zeilen = page.locator("table.buchungen tbody tr[data-id]")
        zeilen.first.wait_for()
        vorher = zeilen.count()
        assert vorher > 2 and page.locator(".vorschlag").count() == vorher
        zeilen.first.locator("button[title='Vorschlag annehmen']").click()
        page.wait_for_selector(".meldung:has-text('angenommen')")
        page.wait_for_function(f"document.querySelectorAll('table.buchungen tbody tr[data-id]').length === {vorher - 1}")
        # Mehrfach ablehnen über Auswahl
        zeilen.nth(0).click()
        zeilen.nth(1).click(modifiers=["Shift"])
        page.locator("button", has_text="ablehnen").first.click()
        page.wait_for_selector(".meldung:has-text('2 Vorschläge abgelehnt')")
        assert not fehler, fehler
        page.close()


def test_tan_seite_und_benachrichtigung(tmp_path, browser):
    with _server(tmp_path, "tan_erforderlich") as url:
        page, fehler = _neue_seite(browser, viewport={"width": 390, "height": 840}, is_mobile=True, has_touch=True)
        page.goto(url + "/#/sync")
        page.locator("button", has_text="Jetzt synchronisieren").click()
        page.wait_for_selector("h1:has-text('TAN-Freigabe')")
        assert page.locator(".tan-bild img").evaluate("i => i.complete && i.naturalWidth > 0")
        speichern = page.locator("a", has_text="QR-Code speichern")
        assert speichern.get_attribute("download", timeout=2000).endswith(".png")
        assert page.locator("button", has_text="Teilen").count() == 1
        # Glocke zeigt die Benachrichtigung; Link /tan/<id> führt auf die TAN-Seite
        page.wait_for_function("document.querySelector('#glocke .zahl-marke').textContent === '1'", timeout=40000)
        tan_id = page.evaluate("location.hash").split("/")[-1]
        page.goto(url + f"/tan/{tan_id}")
        page.wait_for_selector("h1:has-text('TAN-Freigabe')")
        # falsche, dann richtige TAN
        page.fill(".tan-feld", "000000")
        page.locator("button", has_text="TAN senden").click()
        page.wait_for_selector(".meldung:has-text('nicht akzeptiert')")
        page.fill(".tan-feld", "123456")
        page.locator("button", has_text="TAN senden").click()
        page.wait_for_selector("h1:has-text('Synchronisation')")
        page.wait_for_selector(".lauf-erfolgreich")
        page.goto(url + "/#/benachrichtigungen")
        page.wait_for_selector("text=TAN erforderlich")
        page.locator("button", has_text="Als gelesen markieren").click()
        page.wait_for_selector("text=gelesen")
        assert not fehler, fehler
        page.close()
