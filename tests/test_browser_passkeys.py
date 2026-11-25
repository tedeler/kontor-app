"""Browser-Rauchtest (D-284): Passkey einrichten, Bildschirmsperre mit Passkey und Passwort aufheben, Anmeldung mit
Passkey. Der Authentikator ist der virtuelle des Browsers (CDP `WebAuthn`); die Seite läuft unter `localhost`, weil
Passkeys einen Namen statt einer IP-Adresse brauchen. Synthetisches Passwort, kein Geheimnis."""

from __future__ import annotations

import pytest

from .test_browser import HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
PASSWORT = "Synthetisch-Passkey-2026"


def _sperren(page, url):
    """Die Sitzung des Browsers serverseitig sperren (wie nach der eingestellten Zeit im Hintergrund)."""
    csrf = page.request.get(url + "/api/anmeldung").json()["csrf_token"]
    assert page.request.post(url + "/api/anmeldung/sperren", headers={"X-Kontor-CSRF": csrf, "Origin": url}).status == 204


def test_passkey_und_bildschirmsperre(tmp_path, browser):  # noqa: F811
    from kontor import anmeldung

    with server(tmp_path, anmeldung=True) as (url, config):
        url = url.replace("127.0.0.1", "localhost")
        anmeldung.passwort_setzen(config, PASSWORT)
        with seite(browser, url, **HANDY) as page:
            cdp = page.context.new_cdp_session(page)
            cdp.send("WebAuthn.enable")
            geraet = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
                "protocol": "ctap2", "transport": "internal", "hasResidentKey": True, "hasUserVerification": True,
                "isUserVerified": True, "automaticPresenceSimulation": True}})["authenticatorId"]

            # ohne Passkey bietet die Anmeldeseite keinen an
            page.goto(url + "/einstellungen?bereich=sicherheit")
            expect(tid(page, "anmeldung-formular")).to_be_visible()
            expect(tid(page, "anmeldung-passkey")).to_be_hidden()
            tid(page, "anmeldung-passwort").fill(PASSWORT)
            tid(page, "anmeldung-passwort").press("Enter")
            bereit(page, "einstellungen")

            # Passkey auf diesem Gerät einrichten
            expect(tid(page, "passkey-liste")).to_contain_text("Noch kein Passkey")
            tid(page, "passkey-name").fill("Testhandy")
            tid(page, "passkey-anlegen").click()
            expect(tid(page, "passkey-liste")).to_contain_text("Testhandy")
            assert len(cdp.send("WebAuthn.getCredentials", {"authenticatorId": geraet})["credentials"]) == 1

            # Bildschirmsperre einstellen; gesperrt zeigt die Oberfläche nur das Sperrblatt und der Server keine Daten
            tid(page, "bildschirmsperre-wahl").select_option("5")
            expect(tid(page, "meldung").last).to_contain_text("Bildschirmsperre eingestellt")
            cdp.send("WebAuthn.setUserVerified", {"authenticatorId": geraet, "isUserVerified": False})   # Finger passt nicht
            _sperren(page, url)
            page.goto(url + "/konten/1")
            blatt = tid(page, "bildschirmsperre")
            expect(blatt).to_be_visible()
            expect(tid(page, "buchungsliste")).to_have_count(0)
            assert page.request.get(url + "/api/konten").status == 423
            # mit dem Passwort als Rückfallweg: erst falsch, dann richtig
            tid(page, "sperre-passwort-zeigen").click()
            tid(page, "sperre-passwort").fill("Falsches-Passwort-2026")
            tid(page, "sperre-passwort-knopf").click()
            expect(tid(page, "sperre-fehler")).to_contain_text("Passwort ist falsch")
            tid(page, "sperre-passwort").fill(PASSWORT)
            tid(page, "sperre-passwort-knopf").click()
            expect(blatt).to_have_count(0)
            bereit(page, "konto")

            # gesperrt, während die Seite offen ist: die nächste Anfrage zeigt das Blatt; der Passkey hebt es auf
            cdp.send("WebAuthn.setUserVerified", {"authenticatorId": geraet, "isUserVerified": True})
            _sperren(page, url)
            page.evaluate("() => window.dispatchEvent(new Event('kontor-sperre'))")      # irgendeine Anfrage der Oberfläche
            for _ in range(100):                                                         # Blatt erscheint, Passkey entsperrt
                if page.request.get(url + "/api/konten").status == 200:
                    break
                page.wait_for_timeout(50)
            else:
                raise AssertionError("die gesperrte Sitzung wurde nicht mit dem Passkey entsperrt")
            expect(blatt).to_have_count(0)
            expect(tid(page, "buchungsliste")).to_be_visible()

            # Abmelden und mit dem Passkey wieder anmelden
            page.goto(url + "/einstellungen?bereich=sicherheit")
            bereit(page, "einstellungen")
            tid(page, "abmelden").click()
            expect(tid(page, "anmeldung-passkey")).to_be_visible()
            tid(page, "anmeldung-passkey").click()
            bereit(page, "uebersicht")
