"""Entwicklungstests für das Feature „sonderposten“ (D-300): Markieren im Kontoblatt, Vorschlag im Monatsbericht,
Schalter und Kasten in den Berichten. Playwright mit Chrome headless gegen einen echten Server im Mock-Modus
(synthetische Daten).
"""

from __future__ import annotations

import datetime as dt
import re

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401

GROSS = 2_499_000


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        giro = c.post(url + "/api/konten", json={"name": "Giro SP", "art": "girokonto"}).json()["id"]
        lm = c.post(url + "/api/konten", json={"name": "Lebensmittel SP", "art": "aufwand"}).json()["id"]
        auto = c.post(url + "/api/konten", json={"name": "Auto SP", "art": "aufwand"}).json()["id"]
        markt = c.post(url + "/api/empfaenger", json={"name": "Markt SP"}).json()["id"]
        haendler = c.post(url + "/api/empfaenger", json={"name": "Autohaus SP"}).json()["id"]
        for m in range(1, 7):
            for tag in (3, 17):
                assert c.post(url + "/api/buchungen", json={
                    "datum": f"2026-{m:02d}-{tag:02d}", "verwendungszweck": "Einkauf", "empfaenger_id": markt,
                    "splits": [{"konto_id": giro, "betrag": -15_000}, {"konto_id": lm, "betrag": 15_000}]}).status_code == 201
        r = c.post(url + "/api/buchungen", json={
            "datum": "2026-06-10", "verwendungszweck": "Autokauf", "empfaenger_id": haendler,
            "splits": [{"konto_id": giro, "betrag": -GROSS}, {"konto_id": auto, "betrag": GROSS}]})
        assert r.status_code == 201, r.text
    return giro, r.json()["id"]


def _tags(url, bid):
    with httpx.Client(trust_env=False) as c:
        return [t["name"] for t in c.get(f"{url}/api/buchungen/{bid}").json()["tags"]]


def _warte_tags(page, url, bid, soll):
    for _ in range(60):
        if _tags(url, bid) == soll:
            return
        page.wait_for_timeout(100)
    assert _tags(url, bid) == soll


def test_markieren_vorschlag_und_schalter(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2026, 6, 20)) as (url, _), \
            seite(browser, url, **DESKTOP) as page:
        giro, bid = _welt(url)
        # Monatsbericht: Vorschlag für den Autokauf, noch kein Schalter (es gibt den Tag nicht)
        page.goto(url + "/berichte?art=monat&monat=2026-06")
        bereit(page, "berichte")
        expect(tid(page, f"mb-sonderposten-vorschlag-{bid}")).to_be_visible()
        expect(tid(page, "bericht-sonderposten-schalter")).to_have_count(0)
        tid(page, f"mb-sonderposten-markieren-{bid}").click()
        _warte_tags(page, url, bid, ["Sonderposten"])
        kasten = tid(page, "bericht-sonderposten")
        expect(kasten).to_contain_text("nicht mitgezählt")
        expect(tid(page, f"bericht-sonderposten-{bid}")).to_contain_text("Autohaus SP")
        expect(tid(page, f"mb-sonderposten-vorschlag-{bid}")).to_have_count(0)
        expect(tid(page, "mb-kachel-ausgaben")).to_contain_text("300,00")
        # Schalter: mit Sonderposten
        schalter = tid(page, "bericht-sonderposten-schalter")
        expect(schalter).to_be_checked()
        schalter.click()
        expect(page).to_have_url(re.compile(r"sonderposten=mit"))
        expect(tid(page, "bericht-sonderposten")).to_contain_text("– mitgezählt")
        expect(tid(page, "mb-kachel-ausgaben")).to_contain_text("25.290,00")
        # Jahresbericht übernimmt den Schalter aus der Adresse, Vorgabe ohne
        page.goto(url + "/berichte?art=jahr&jahr=2026")
        bereit(page, "berichte")
        expect(tid(page, "bericht-sonderposten-schalter")).to_be_checked()
        expect(tid(page, "bericht-sonderposten")).to_be_visible()
        # Kontoblatt: p nimmt die Markierung zurück und setzt sie wieder
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        tid(page, f"buchung-{bid}").locator('[data-feld="datum"]').click()
        page.keyboard.press("p")
        _warte_tags(page, url, bid, [])
        expect(tid(page, "seite-konto")).to_have_attribute("data-ausstehend", "0")
        page.keyboard.press("p")
        _warte_tags(page, url, bid, ["Sonderposten"])
        tid(page, f"buchung-{bid}").click(button="right")
        expect(tid(page, "km-sonderposten")).to_have_text(re.compile("Sonderposten zurücknehmen"))
