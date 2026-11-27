"""Browsertest des Features „mail-aktuell“ (D-284): Ein offenes Kontoblatt zeigt die Zuordnungen eines Mail-Abrufs,
ohne dass man es schließen und wieder öffnen muss."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from kontor import abgleich, db

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

NR = "302-1234567-7654321"
ADRESSE = "haushalt.eins@example.invalid"


def _vorbereiten(url, config):
    """Buchung mit Amazon-Bestellnummer und eine passende Mail im Spiegel, noch nicht zugeordnet."""
    c = httpx.Client(base_url=url, trust_env=False, timeout=60)
    assert c.post("/api/mail/postfaecher", json={"adresse": ADRESSE}).status_code == 201
    konten = {k["name"]: k["id"] for k in c.get("/api/konten").json()}
    r = c.post("/api/buchungen", json={"datum": "2024-03-03", "verwendungszweck": f"{NR} AMZN Mktp DE fiktiv", "splits": [
        {"konto_id": konten["Giro"], "betrag": -4990}, {"konto_id": konten["Lebensmittel"], "betrag": 4990}]})
    assert r.status_code == 201, r.text
    con = db.verbinde(config.aktive_datenbank)
    try:
        with db.transaktion(con):
            con.execute("INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text, roh)"
                        " VALUES (?, '<a1@example.invalid>', '2024-03-01T10:00:00Z', 'versand@amazon.example.invalid',"
                        " ?, 'ohne Summe', NULL)", (ADRESSE, f"Bestellt: Kabel (fiktiv) {NR}"))
    finally:
        con.close()
    return c, konten["Giro"], r.json()["id"]


def test_abruf_im_mail_blatt_aktualisiert_das_offene_kontoblatt(tmp_path, browser):
    with server(tmp_path, mail_bestellnummer=True) as (url, config), seite(browser, url, **DESKTOP) as page:
        _, giro, bid = _vorbereiten(url, config)
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        expect(tid(page, f"buchung-{bid}")).to_be_visible()
        expect(tid(page, f"beleg-marke-{bid}")).to_have_count(0)
        page.locator('nav a[href="/mail"]').first.click()
        bereit(page, "mail")
        tid(page, "mail-abrufen").click()
        expect(tid(page, "mail-stand")).to_contain_text("Abruf beendet", timeout=20000)
        page.locator(f'[data-testid="tab-leiste"] [data-testid="tab"][data-pfad="/konten/{giro}"]').click()
        expect(tid(page, f"beleg-marke-{bid}")).to_be_visible()


def test_abruf_im_hintergrund_aktualisiert_das_sichtbare_kontoblatt(tmp_path, browser):
    """Planer oder anderes Gerät: Die sichtbare Ansicht lädt beim nächsten Anlass von selbst neu."""
    with server(tmp_path, mail_bestellnummer=True, mail_intervall_minuten=120) as (url, config), \
            seite(browser, url, **DESKTOP) as page:
        c, giro, bid = _vorbereiten(url, config)
        # erst ändern, wenn die Oberfläche den Stand beim Start gemerkt hat (sonst merkt sie schon den neuen)
        with page.expect_response(lambda r: r.url.endswith("/api/bestand/stand")):
            page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        expect(tid(page, f"beleg-marke-{bid}")).to_have_count(0)
        tid(page, f"buchung-{bid}").click()                       # die Auswahl bleibt beim Neuladen
        abgleich.nach_ereignis(config, dt.datetime.now().astimezone())
        assert len(c.get(f"/api/buchungen/{bid}").json()["belege"]) == 1
        page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
        expect(tid(page, f"beleg-marke-{bid}")).to_be_visible()
        expect(tid(page, f"buchung-{bid}")).to_have_attribute("aria-selected", "true")
        page.locator('nav a[href="/mail"]').first.click()
        bereit(page, "mail")
        expect(tid(page, "mail-automatik")).to_contain_text("alle 2 Stunden")
