"""Browser-Rauchtest der M7-Oberfläche (Playwright, Chrome headless): Ersteinrichtung mit Einrichtungscode,
Anmeldung, falsches Passwort und Sperrhinweis, Weiterleitung über ``weiter``, Passwort ändern, Abmelden; auf
Desktop- und Handybreite. Echter Server im Mock-Modus auf einem freien Loopback-Port, synthetisches Passwort.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import socket
import threading
import time

import pytest

from .test_browser_m2 import _neue_seite, browser  # noqa: F401  (Fixture)

playwright = pytest.importorskip("playwright.sync_api")

PASSWORT = "Synthetisch-Haushalt-2026"  # kein Geheimnis, nur für diesen Test
NEU = "Synthetisch-Neu-2026-xyz"


@contextlib.contextmanager
def _server(basis, **kw):
    import uvicorn

    from kontor.app import create_app
    from kontor.config import KontorConfig

    config = KontorConfig(datenbank=basis / "kontor.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 30),
                          anmeldung=True, **kw)
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
        yield f"http://127.0.0.1:{port}", config
    finally:
        srv.should_exit = True
        t.join(timeout=30)


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}],
                         ids=["desktop", "handy"])
def test_m7_anmeldung(tmp_path, browser, viewport):  # noqa: F811
    from kontor.anmeldung import einrichtungsdatei

    with _server(tmp_path, anmeldung_fehlversuche=3, anmeldung_sperre_sekunden=2) as (url, config):
        page, fehler = _neue_seite(browser, viewport=viewport)
        # ohne Sitzung: Weiterleitung zur Anmeldeseite mit Rücksprungziel
        page.goto(url + "/einstellungen")
        page.wait_for_selector("[data-testid=anmeldung-formular]")
        assert "/anmelden?weiter=" in page.url
        assert page.locator("#mock-hinweis").is_visible()
        # Ersteinrichtung mit dem Code aus der Datei auf dem Server
        code = einrichtungsdatei(config).read_text(encoding="ascii").strip()
        page.fill("[data-testid=anmeldung-einrichtungscode]", "0" * 32)
        page.fill("[data-testid=anmeldung-passwort]", PASSWORT)
        page.click("[data-testid=anmeldung-knopf]")
        page.wait_for_selector("[data-testid=anmeldung-meldung]:has-text('Einrichtungscode ist falsch')")
        page.fill("[data-testid=anmeldung-einrichtungscode]", code)
        page.click("[data-testid=anmeldung-knopf]")
        page.wait_for_selector("[data-testid=anmeldung-karte]")  # weiter=/einstellungen → Einstellungen
        assert not einrichtungsdatei(config).exists()
        breite = page.evaluate("document.documentElement.scrollWidth")
        assert breite <= viewport["width"] + 1, "kein waagerechtes Scrollen"
        # schreibende Anfrage der Oberfläche mit CSRF-Token
        page.goto(url + "/#/einstellungen")
        page.wait_for_selector("[data-testid=passwort-formular]")
        page.fill("[data-testid=passwort-alt]", "Falsch-falsch-falsch")
        page.fill("[data-testid=passwort-neu]", NEU)
        page.fill("[data-testid=passwort-wiederholen]", NEU)
        page.locator("[data-testid=passwort-formular] button[type=submit]").click()
        page.wait_for_selector("[data-testid=passwort-hinweis]:has-text('bisherige Passwort ist falsch')")
        page.fill("[data-testid=passwort-alt]", PASSWORT)
        page.locator("[data-testid=passwort-formular] button[type=submit]").click()
        page.wait_for_selector("[data-testid=passwort-hinweis]:has-text('Passwort geändert')")
        # Abmelden über den Kopf
        page.click("[data-testid=abmelden]")
        page.wait_for_selector("[data-testid=anmeldung-formular]")
        assert page.locator("[data-testid=anmeldung-einrichtungscode]").count() == 0
        r = page.request.get(url + "/api/konten")
        assert r.status == 401
        # falsche Passwörter bis zur Sperre: Hinweis mit Restzeit
        for _ in range(3):
            page.fill("[data-testid=anmeldung-passwort]", "Ganz-falsches-Passwort")
            page.click("[data-testid=anmeldung-knopf]")
            page.wait_for_selector("[data-testid=anmeldung-meldung]:has-text('Passwort ist falsch')")
            page.evaluate("document.getElementById('anmeldung-meldung').textContent = ''")
        page.fill("[data-testid=anmeldung-passwort]", NEU)
        page.click("[data-testid=anmeldung-knopf]")
        page.wait_for_selector("[data-testid=anmeldung-meldung]:has-text('gesperrt')")
        page.wait_for_selector("[data-testid=anmeldung-meldung]:has-text('Sperre ist abgelaufen')", timeout=8000)
        page.click("[data-testid=anmeldung-knopf]")
        page.wait_for_selector("#inhalt h1")
        assert page.request.get(url + "/api/konten").status == 200
        assert not fehler, fehler
