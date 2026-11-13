"""Browser-Rauchtest zum Betragsfilter wiederkehrender Buchungen (D-137): Vorgabe und Einstellung je Empfänger in den
Einstellungen, Dialog aus der Begründung. Synthetische Daten, eigener Server auf einem freien Loopback-Port."""

from __future__ import annotations

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401


def _daten(url):
    c = httpx.Client(base_url=url)
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Lohn", "art": "ertrag"}).json()["id"]
    e = c.post("/api/empfaenger", json={"name": "Beispiel GmbH (fiktiv)"}).json()["id"]
    ids = []
    for t, b in (("2024-01-30", 312_345), ("2024-02-12", 4_250), ("2024-02-29", 312_345), ("2024-03-15", 18_990),
                 ("2024-03-28", 312_345), ("2024-04-30", 312_345), ("2024-05-10", 2_300)):
        r = c.post("/api/buchungen", json={"datum": t, "empfaenger_id": e, "splits": [
            {"konto_id": g, "betrag": b}, {"konto_id": kat, "betrag": -b}]})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return c, g, e, ids


def test_einstellungen_und_dialog(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        c, g, e, ids = _daten(url)
        page.goto(f"{url}/einstellungen")
        bereit(page, "einstellungen")
        expect(tid(page, "wk-vorgabe-modus")).to_have_value("toleranz")
        expect(tid(page, "wk-vorgabe-toleranz")).to_have_value("10")
        tid(page, "wk-vorgabe-toleranz").fill("15")
        tid(page, "wk-vorgabe-speichern").click()
        expect(tid(page, "wk-vorgabe-toleranz")).to_have_value("15")
        assert c.get("/api/wiederkehrend/einstellungen").json()["vorgabe"]["toleranz_prozent"] == 15
        # Empfänger hinzufügen: Mindestschwelle
        tid(page, "wk-filter-neu").click()
        d = tid(page, "wk-filter-dialog")
        expect(d).to_be_visible()
        tid(page, "wk-filter-modus").select_option("mindestschwelle")
        tid(page, "wk-filter-betrag").fill("2.500,00")
        tid(page, "wk-filter-speichern").click()
        expect(tid(page, f"wk-filter-{e}")).to_have_attribute("data-modus", "mindestschwelle")
        assert c.get("/api/wiederkehrend/einstellungen").json()["empfaenger"][0]["mindestbetrag"] == 250_000
        # Begründung der jüngsten Buchung (Auslage) zeigt anderen Betrag und öffnet den Filterdialog
        page.goto(f"{url}/konten/{g}")
        bereit(page, "konto")
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]')
        zeilen.locator('[data-feld="datum"]', has_text="10.05.2024").click(button="right", modifiers=["Alt"])
        tid(page, "km-wiederkehrend").click()
        expect(tid(page, "wk-eintrag")).to_have_attribute("data-urteil", "anderer_betrag")
        expect(tid(page, "wk-betragsfilter")).to_have_attribute("data-quelle", "empfaenger")
        tid(page, "wk-filter-oeffnen").click()
        expect(tid(page, "wk-filter-modus")).to_have_value("mindestschwelle")
        expect(tid(page, "wk-filter-betrag")).to_have_value("2500,00")
        tid(page, "wk-filter-modus").select_option("vorgabe")
        tid(page, "wk-filter-speichern").click()
        expect(tid(page, "wk-filter-dialog")).to_have_count(0)
        assert c.get("/api/wiederkehrend/einstellungen").json()["empfaenger"] == []
