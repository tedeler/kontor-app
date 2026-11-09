"""Browser-Rauchtest der M6-Oberfläche (Playwright, Chrome headless): Anbindungen (Bankzugang, Geheimnisspeicher,
ntfy-Zustellung mit Test-Benachrichtigung, Postfächer mit Status und Anmeldestart), Mail-Übersicht mit Abruf;
Handy-Ansicht ohne waagerechtes Scrollen der Seite. Geheimnisse erscheinen nie im Seiteninhalt.

Echte Server auf freien lokalen Ports: Mock-Modus mit eingebauten synthetischen Postfächern; Echtmodus ohne
Netzverbindung (die Autorisierungs-URL wird nur angezeigt, nie geöffnet).
"""

from __future__ import annotations

import contextlib
import socket
import threading
import time

import pytest

from .test_browser_m2 import _neue_seite, _server, browser  # noqa: F401  (Fixture)

playwright = pytest.importorskip("playwright.sync_api")

GEHEIM = "SYNTH-NTFY-TOKEN-OBERFLAECHE-1"
SECRET = "SYNTH-CLIENT-SECRET-OBERFLAECHE-2"


@contextlib.contextmanager
def _echt_server(basis):
    import uvicorn

    from kontor.app import create_app
    from kontor.config import KontorConfig

    config = KontorConfig(datenbank=basis / "kontor.sqlite3", oauth_client_id="SYNTH-ID.apps.example.invalid",
                          oauth_autorisierung_url="https://auth.example.invalid/o/oauth2/auth")
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


def _kein_waagerechtes_scrollen(page):
    breite = page.evaluate("document.documentElement.scrollWidth")
    sichtbar = page.evaluate("document.documentElement.clientWidth")
    assert breite <= sichtbar + 1, (breite, sichtbar)


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}],
                         ids=["desktop", "handy"])
def test_m6_mock_modus(tmp_path, browser, viewport):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport=viewport)
        page.goto(url + "/#/anbindungen")
        page.wait_for_selector("#anbindung-bank")
        assert "Eingabe" in page.locator("#pin-quelle").inner_text()
        assert page.locator("#zustell-plugin").inner_text() == "mock"

        # Geheimnis setzen: Feld wird geleert, Wert erscheint nie
        page.fill("#geheimnis-ntfy_token", GEHEIM)
        page.locator("#geheimnis-ntfy_token").press("Enter")
        page.wait_for_selector("#anbindung-geheimnisse :text('gesetzt')")
        assert GEHEIM not in page.content()
        assert page.locator("#geheimnis-ntfy_token").input_value() == ""

        # Test-Benachrichtigung
        page.locator("#ntfy-test").click()
        page.wait_for_selector("#ntfy-ergebnis :text('gesendet')")

        # Postfach anlegen (eingebaute Mock-Adresse) und abrufen
        page.locator("#postfach-neu").click()
        page.fill("#postfach-adresse", "haushalt.eins@example.invalid")
        page.fill("#postfach-bezeichnung", "Haushalt (fiktiv)")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector("#postfach-tabelle td:has-text('haushalt.eins@example.invalid')")
        assert "nicht erforderlich" in page.locator("#postfach-tabelle").inner_text()
        _kein_waagerechtes_scrollen(page)

        page.goto(url + "/#/mail")
        page.locator("#mail-abruf").click()
        page.wait_for_selector("#abruf-ergebnis :text('erfolgreich')")
        page.wait_for_selector("#mail-tabelle tbody tr")
        assert page.locator("#mail-tabelle tbody tr").count() > 0
        _kein_waagerechtes_scrollen(page)

        # Link aus einer Benachrichtigung öffnet die Postfach-Einstellungen
        pid = page.request.get(url + "/api/mail/postfaecher").json()[0]["id"]
        page.goto(url + f"/mail/postfaecher/{pid}")
        page.wait_for_selector(f"#postfach-{pid}.markiert")
        assert fehler == [], fehler


def test_m6_echtmodus_anmeldung_starten(tmp_path, browser):  # noqa: F811
    with _echt_server(tmp_path) as url:
        page, fehler = _neue_seite(browser, viewport={"width": 1280, "height": 900})
        page.request.put(url + "/api/geheimnisse/oauth_client_secret", data={"wert": SECRET})
        page.request.post(url + "/api/mail/postfaecher", data={"adresse": "haushalt.zwei@example.invalid"})
        page.goto(url + "/#/anbindungen")
        page.wait_for_selector("#postfach-tabelle")
        assert "nicht angemeldet" in page.locator("#postfach-tabelle").inner_text()
        assert page.locator("#zustell-plugin").inner_text().startswith("keins")
        assert page.locator("#ntfy-test").is_disabled()
        page.locator("#postfach-tabelle button", has_text="Anmelden").click()
        link = page.locator("#anmeldung-link")
        link.wait_for()
        assert link.get_attribute("href").startswith("https://auth.example.invalid/o/oauth2/auth?")
        # ungültige Umleitungs-URL: Fehlermeldung, kein Absturz
        page.fill("#anmeldung-antwort", "http://127.0.0.1/oauth2/rueckruf?state=unbekannt&code=SYNTH")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung.fehler")
        assert SECRET not in page.content()
        assert fehler == [], fehler
