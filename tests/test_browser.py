"""Browser-Rauchtest der Weboberfläche (Playwright). Wird übersprungen, wenn kein Browser verfügbar ist.

Startet einen echten Server im Mock-Modus auf einem freien lokalen Port und
bedient Übersicht, Kontoansicht, Mehrfachauswahl, Kontextmenü und die mobile
Navigation.
"""

from __future__ import annotations

import os
import shutil
import socket
import threading
import time

import pytest

from .conftest import GIRO, kmy, transaktion

playwright = pytest.importorskip("playwright.sync_api")


def _chrome() -> str | None:
    for name in (os.environ.get("KONTOR_CHROME"), "google-chrome", "chromium", "chromium-browser"):
        if name and shutil.which(name):
            return shutil.which(name)
    return None


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn

    from kontor.app import create_app
    from kontor.config import KontorConfig
    from kontor.importer.kmymoney import importiere_kmy

    pfad = tmp_path_factory.mktemp("browser")
    config = KontorConfig(datenbank=pfad / "kontor.sqlite3", mock_modus=True)
    transaktionen = "".join(transaktion(f"T{i}", f"2024-01-{i:02d}", ("A1", f"-{i * 100}/100"), ("A2", f"{i * 100}/100"))
                            for i in range(1, 21))
    assert importiere_kmy(config, kmy(GIRO, transaktionen=transaktionen)).erfolgreich
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
    yield f"http://127.0.0.1:{port}/"
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


def test_desktop_ablauf(server, browser):
    fehler: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("pageerror", lambda e: fehler.append(str(e)))
    page.goto(server + "#/uebersicht")
    page.wait_for_selector("table")
    assert page.locator("#mock-hinweis").is_visible()
    assert "Giro" in page.locator("#inhalt").inner_text()
    page.locator("tbody tr", has_text="Giro").first.click()
    zeilen = page.locator("table.buchungen tbody tr[data-id]")
    zeilen.first.wait_for()
    assert zeilen.count() == 20
    zeilen.nth(0).click()
    zeilen.nth(3).click(modifiers=["Shift"])
    zeilen.nth(6).click(modifiers=["Control"])
    assert page.locator("tr.markiert").count() == 5
    zeilen.nth(6).click(button="right")
    assert page.locator("#kontextmenue").is_visible()
    page.locator("#kontextmenue button", has_text="Kategorie setzen").click()
    page.select_option(".dialog select", index=1)
    page.locator(".dialog button[type=submit]").click()
    page.wait_for_selector(".meldung")
    assert "gesetzt" in page.locator(".meldung").first.inner_text()
    assert not fehler, fehler


def test_mobil_menue_und_lange_beruehrung(server, browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 800}, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    page.goto(server + "#/konten")
    page.wait_for_selector("table")
    assert page.locator("#navigation").bounding_box()["x"] < 0, "Navigation ist eingeklappt"
    page.click("#menue-knopf")
    page.wait_for_timeout(400)
    assert page.locator("#navigation").bounding_box()["x"] >= 0
    page.locator("#navigation a", has_text="Finanzübersicht").click()
    page.wait_for_timeout(300)
    page.goto(server + "#/konto/1")
    page.wait_for_timeout(1000)
    zeile = page.locator("table.buchungen tbody tr[data-id]").nth(1)
    zeile.scroll_into_view_if_needed()
    box = zeile.bounding_box()
    cdp = ctx.new_cdp_session(page)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": box["x"] + 40, "y": box["y"] + 10}]})
    page.wait_for_timeout(800)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(200)
    assert page.locator("#kontextmenue").is_visible(), "lange Berührung öffnet das Kontextmenü"
    ctx.close()
