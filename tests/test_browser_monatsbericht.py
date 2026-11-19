"""Browser-Rauchtest zum Monatsbericht (D-206): Kacheln, Diagramme, Monatswechsel, Einzelbuchungen, Kontenwahl,
Handy-Layout. Synthetische Daten, eigener Server auf einem freien Loopback-Port."""

from __future__ import annotations

import datetime as dt

import httpx

from .test_browser import DESKTOP, HANDY, bereit, browser, expect, seite, server, tid  # noqa: F401


def _daten(url):
    c = httpx.Client(base_url=url)

    def konto(name, art):
        return c.post("/api/konten", json={"name": name, "art": art}).json()["id"]

    giro, spar = konto("Giro", "girokonto"), konto("Sparbuch", "sparkonto")
    wohnen, essen, lohn = konto("Wohnen", "aufwand"), konto("Essen", "aufwand"), konto("Lohn", "ertrag")

    def buchen(art, datum, betrag, name, konto_id=giro, **extra):
        r = c.post("/api/buchungen/erfassen", json={"art": art, "datum": datum, "konto_id": konto_id, "betrag": betrag,
                                                     "empfaenger_name": name, **extra})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    ids = {}
    for monat in range(1, 7):
        ids[f"miete-{monat}"] = buchen("ausgabe", f"2024-{monat:02d}-01", 80_000, "Vermieter (fiktiv)", kategorie_id=wohnen)
        buchen("einnahme", f"2024-{monat:02d}-02", 250_000, "Arbeitgeber (fiktiv)", kategorie_id=lohn)
        for tag in (5, 12):
            buchen("ausgabe", f"2024-{monat:02d}-{tag:02d}", 4_000 + monat * 100, "Supermarkt (fiktiv)", kategorie_id=essen)
    buchen("ausgabe", "2024-06-12", 900, "Bäcker (fiktiv)", kategorie_id=essen)
    buchen("ausgabe", "2024-06-10", 2_500, "Bank (fiktiv)", konto_id=spar, kategorie_id=wohnen)
    buchen("umbuchung", "2024-06-03", 50_000, "Sparrate", gegenkonto_id=spar)
    return giro, spar, ids


def test_monatsbericht_desktop(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2024, 6, 15)) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro, spar, ids = _daten(url)
        page.goto(f"{url}/berichte")
        bereit(page, "berichte")
        tid(page, "bericht-art-monat").click()
        expect(tid(page, "seite-berichte")).to_have_attribute("data-art", "monat")
        bereit(page, "berichte")
        s = tid(page, "seite-berichte")
        expect(s).to_have_attribute("data-monat", "2024-06")
        expect(tid(page, "mb-monat")).to_have_value("2024-06")
        expect(tid(page, "mb-stand")).to_contain_text("Stand 15.06.2024")
        expect(tid(page, "mb-stand")).to_contain_text("1 Umbuchung")
        expect(tid(page, "mb-kachel-ausgaben").locator("[data-betrag]")).to_have_attribute("data-betrag", "92600")
        expect(tid(page, "mb-kachel-prognose")).to_be_visible()
        for name in ("verlauf", "monate", "kontostand"):
            expect(tid(page, f"mb-{name}-diagramm")).to_have_attribute("data-gezeichnet", "ja")
        expect(tid(page, "mb-teil-fix")).to_contain_text("800,00")
        expect(tid(page, "mb-heute")).to_be_disabled()
        expect(tid(page, "mb-monat-vor")).to_be_disabled()
        # Einzelbuchungen eines Tages; von dort zur Buchung im Konto
        tid(page, "mb-tag-2024-06-12").click()
        d = tid(page, "mb-buchungen-dialog")
        expect(d.locator("tbody tr")).to_have_count(2)
        expect(tid(page, "mb-dialog-summe")).to_contain_text("55,00")
        page.keyboard.press("Escape")
        expect(d).to_have_count(0)
        expect(tid(page, "mb-tag-2024-06-12")).to_be_focused()
        expect(tid(page, "mb-tag-2024-06-13")).to_be_disabled()
        # Empfänger und Größenklasse öffnen dieselbe Liste; Zeilen sind mit der Tastatur bedienbar
        tid(page, "mb-klasse-0").focus()
        page.keyboard.press("Enter")
        expect(d.locator("tbody tr")).to_have_count(1)
        tid(page, "mb-dialog-schliessen").click()
        tid(page, "mb-empfaenger-1").click()
        expect(d.locator("h2")).to_have_text("Ausgaben an Supermarkt (fiktiv)")
        expect(d.locator("tbody tr")).to_have_count(2)
        tid(page, "mb-dialog-schliessen").click()
        # Monat wechseln: Knopf, Auswahl, zurück zum laufenden Monat; die Adresse merkt sich die Wahl
        tid(page, "mb-monat-zurueck").click()
        expect(s).to_have_attribute("data-monat", "2024-05")
        bereit(page, "berichte")
        assert page.url.endswith("/berichte?art=monat&monat=2024-05")
        expect(tid(page, "mb-kachel-prognose")).to_have_count(0)
        expect(tid(page, "mb-kachel-protag")).to_be_visible()
        expect(tid(page, "mb-stand")).to_contain_text("Abgeschlossener Monat")
        tid(page, "mb-monat").select_option("2024-02")
        expect(s).to_have_attribute("data-monat", "2024-02")
        bereit(page, "berichte")
        tid(page, "mb-heute").click()
        expect(s).to_have_attribute("data-monat", "2024-06")
        bereit(page, "berichte")
        assert page.url.endswith("/berichte?art=monat")
        # Konten einschränken
        tid(page, "mb-konten").locator("summary").click()
        tid(page, f"mb-konto-{spar}").uncheck()
        expect(tid(page, "mb-kachel-ausgaben").locator("[data-betrag]")).to_have_attribute("data-betrag", "90100")
        bereit(page, "berichte")
        assert page.url.endswith(f"/berichte?art=monat&konto={giro}")
        expect(tid(page, "mb-konten")).to_have_attribute("open", "")
        tid(page, "mb-konten-alle").click()
        expect(tid(page, "mb-kachel-ausgaben").locator("[data-betrag]")).to_have_attribute("data-betrag", "92600")
        bereit(page, "berichte")
        # größte Buchung führt ins Konto
        tid(page, f"mb-top-buchung-{ids['miete-6']}").click()
        bereit(page, "konto")
        expect(tid(page, f"buchung-{ids['miete-6']}")).to_be_visible()


def test_monatsbericht_handy_und_leer(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2024, 6, 15)) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(f"{url}/berichte/monat")
        bereit(page, "berichte")
        expect(tid(page, "mb-leer")).to_be_visible()
        expect(tid(page, "mb-kalender")).to_have_count(0)
        _daten(url)
        page.goto(f"{url}/berichte?art=monat&monat=2024-05")
        bereit(page, "berichte")
        expect(tid(page, "mb-kalender")).to_be_visible()
        breite = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert breite, "kein waagerechtes Rollen auf dem Handy"
        for karte in ("mb-klassen", "mb-empfaenger", "mb-top-buchungen", "mb-kalender-karte"):
            passt = tid(page, karte).evaluate("el => el.scrollWidth <= el.clientWidth + 1")
            assert passt, f"{karte} läuft über"
        tid(page, "mb-tag-2024-05-05").click()
        expect(tid(page, "mb-buchungen-dialog").locator("tbody tr")).to_have_count(1)
