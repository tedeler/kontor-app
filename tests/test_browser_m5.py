"""Browser-Rauchtest der M5-Oberfläche (Playwright, Chrome headless): wiederkehrende Buchungen, Kredit anlegen
mit Tilgungsplan, Raten zuordnen, Jahresabgleich-Dialog mit Probelauf, Bericht Kontostandsverlauf als
SVG-Liniendiagramm, Export-Knöpfe; Handy-Ansicht ohne waagerechtes Scrollen der Seite.

Echter Server im Mock-Modus auf einem freien lokalen Port; nur synthetische Daten, keine Verbindung nach außen.
"""

from __future__ import annotations

import pytest

from .test_browser_m2 import _neue_seite, _server, browser  # noqa: F401  (Fixture)

playwright = pytest.importorskip("playwright.sync_api")


def _aufbau(page, url) -> dict:
    post = lambda pfad, d: page.request.post(url + pfad, data=d).json()  # noqa: E731
    k = {"giro": post("/api/konten", {"name": "Giro Fiktiv", "art": "girokonto"})["id"],
         "darlehen": post("/api/konten", {"name": "Darlehen Fiktivbank", "art": "kreditkonto"})["id"],
         "zinsen": post("/api/konten", {"name": "Zinsen", "art": "aufwand"})["id"],
         "abo": post("/api/konten", {"name": "Abos", "art": "aufwand"})["id"]}
    abo = post("/api/empfaenger", {"name": "Streamingdienst Fiktiv"})["id"]
    k["bank"] = post("/api/empfaenger", {"name": "Fiktivbank AG"})["id"]
    for monat in range(1, 7):
        post("/api/buchungen", {"datum": f"2024-{monat:02d}-15", "empfaenger_id": abo,
                                "splits": [{"konto_id": k["giro"], "betrag": -1299}, {"konto_id": k["abo"], "betrag": 1299}]})
    return k


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 900}, {"width": 390, "height": 844}],
                         ids=["desktop", "handy"])
def test_m5_oberflaeche(tmp_path, browser, viewport):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport=viewport)
        k = _aufbau(page, url)

        # Wiederkehrende Buchungen
        page.goto(url + "/#/wiederkehrend")
        page.wait_for_selector("#wiederkehrend-tabelle td:has-text('Streamingdienst Fiktiv')")
        assert "155,88" in page.locator("#wiederkehrend-summe").inner_text()  # 12 × 12,99 €
        page.locator("#wiederkehrend-pruefen").click()
        page.wait_for_selector("#wiederkehrend-ergebnis .karte")

        # Kredit über den Dialog anlegen
        page.goto(url + "/#/kredite")
        page.locator("#kredit-neu").click()
        page.fill("#kredit-name", "Baufinanzierung Fiktiv")
        page.select_option("#kredit-konto", label="Darlehen Fiktivbank")
        page.select_option("#kredit-zahlungskonto", label="Giro Fiktiv")
        page.select_option("#kredit-zinskonto", label="Zinsen")
        page.fill("#kredit-restschuld", "10.000,00")
        page.fill("#kredit-stand", "2024-01-15")
        page.fill("#kredit-sollzins", "3,6")
        page.fill("#kredit-rate", "500")
        page.fill("#kredit-erste", "2024-02-01")
        page.locator(".kredit-bedingung").fill("Fiktivbank")
        page.locator(".dialog button", has_text="Plan berechnen").click()
        page.wait_for_selector("#kredit-vorschau p:has-text('Raten')")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector("#tilgungsplan tbody tr")
        kredit = page.request.get(url + "/api/kredite").json()[0]
        assert (kredit["sollzins"], kredit["restschuld"], kredit["rate"]) == (36_000, 1_000_000, 50_000)
        plan = page.request.get(url + f"/api/kredite/{kredit['id']}/plan").json()
        assert page.locator("#tilgungsplan tbody tr").count() == plan["anzahl_raten"]

        # Raten buchen und über die Oberfläche zuordnen
        for z in plan["zeilen"][:3]:
            page.request.post(url + "/api/buchungen", data={
                "datum": z["faelligkeit"], "empfaenger_id": k["bank"], "status": "importiert",
                "splits": [{"konto_id": k["giro"], "betrag": -z["rate"]}, {"konto_id": k["abo"], "betrag": z["rate"]}]})
        page.reload()
        page.wait_for_selector("#tilgungsplan")
        page.locator("button", has_text="Raten in vorhandenen Buchungen suchen").click()
        page.locator("#zuordnen-ergebnis button", has_text="Jetzt aufteilen").click()
        page.wait_for_selector("#zuordnen-ergebnis:has-text('wurden')")
        assert len(page.request.get(url + f"/api/kredite/{kredit['id']}").json()["zuordnungen"]) == 3

        # Jahresabgleich: erst Vorschlag (Probelauf), dann bestätigen
        page.reload()
        page.wait_for_selector("#jahresabgleich-knopf")
        page.locator("#jahresabgleich-knopf").click()
        page.fill("#abgleich-jahr", "2024")
        page.fill("#abgleich-restschuld", "8.600,00")
        page.fill("#abgleich-zinsen", "80,00")
        page.locator("#abgleich-vorschlag").click()
        page.wait_for_selector("#abgleich-probelauf")
        assert page.request.get(url + f"/api/kredite/{kredit['id']}").json()["abgleiche"] == [], "Probelauf ändert nichts"
        page.locator(".dialog button", has_text="Korrektur bestätigen").click()
        page.wait_for_selector(".karte:has-text('Jahresabgleiche')")
        a = page.request.get(url + f"/api/kredite/{kredit['id']}").json()["abgleiche"]
        assert [(x["jahr"], x["restschuld"], x["zinsen"]) for x in a] == [(2024, 860_000, 8_000)]

        # Bericht Kontostandsverlauf als selbst gezeichnetes SVG, Export-Knöpfe
        page.goto(url + f"/#/berichte?konto_id={k['giro']}&konto_id={k['darlehen']}&von=2024-01-01&bis=2024-06-30")
        page.wait_for_selector("#kontostand-diagramm polyline")
        assert page.locator("#kontostand-diagramm polyline").count() == 2
        assert page.locator("#kontostand-legende").inner_text().count("Darlehen Fiktivbank") == 1
        box = page.locator("#kontostand-diagramm").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] / 2)
        page.wait_for_selector(".diagramm-tip:not([hidden])")
        csv_link = page.locator("#bericht-export a", has_text="CSV").get_attribute("href")
        r = page.request.get(url + csv_link)
        assert r.ok and r.body().startswith(b"\xef\xbb\xbfbuchung_id;")
        pdf_link = page.locator("#bericht-export a", has_text="PDF").get_attribute("href")
        assert page.request.get(url + pdf_link).body().startswith(b"%PDF-1.")
        page.goto(url + "/#/buchungen")
        page.wait_for_selector("h1:has-text('Alle Buchungen')")
        link = page.locator(".werkzeug a", has_text="CSV")
        link.wait_for()
        assert link.get_attribute("href").startswith("/api/export/buchungen.csv?")

        # responsiv: die Seite selbst scrollt nicht waagerecht (Tabellen scrollen in ihrer Hülle)
        for ziel in ("#/kredite", f"#/kredit/{kredit['id']}", "#/berichte", "#/wiederkehrend"):
            page.goto(url + "/" + ziel)
            page.wait_for_selector("h1")
            page.wait_for_timeout(150)
            breite = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
            assert breite[0] <= breite[1] + 1, (ziel, breite)
        assert fehler == [], fehler
        page.close()
