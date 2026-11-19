"""Browser-Rauchtest der Berichte (D-217): Wahl der Berichtsart, jede Art lädt und zeichnet, Sortieren, Einzelbuchungen,
Empfänger- und Tag-Auswertung, Handy ohne waagerechtes Rollen. Eigener Server auf einem freien Loopback-Port."""

from __future__ import annotations

import datetime as dt

import httpx

from .test_browser import DESKTOP, HANDY, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_monatsbericht import _daten

ARTEN = ("uebersicht", "monat", "jahr", "kategorien", "empfaenger", "tags", "vertraege", "geldfluss", "vorschau",
         "vermoegen", "qualitaet")
DIAGRAMME = {"jahr": ("mb-jahr-diagramm", "mb-jahr-lauf-diagramm"), "vorschau": ("mb-vorschau-diagramm",),
             "vermoegen": ("mb-vermoegen-diagramm", "mb-sparen-diagramm"), "qualitaet": ("mb-qualitaet-diagramm",),
             "geldfluss": ("mb-fluss",)}


def _tags(url):
    c = httpx.Client(base_url=url)
    ids = [c.post("/api/tags", json={"name": n}).json()["id"] for n in ("Urlaub (fiktiv)", "Auto (fiktiv)")]
    liste = c.get("/api/buchungen", params={"von": "2024-05-01", "bis": "2024-06-30", "pro_seite": 200}).json()
    buchungen = liste["eintraege"]
    markt = [b for b in buchungen if b["empfaenger"] and b["empfaenger"]["name"].startswith("Supermarkt")]
    assert len(markt) == 4
    for b, t in zip(markt, (ids[0], ids[0], ids[1], ids[1])):
        assert c.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": [t]}).status_code == 200
    return ids


def _art(page, name):
    tid(page, f"bericht-art-{name}").click()
    expect(tid(page, "seite-berichte")).to_have_attribute("data-art", name)
    bereit(page, "berichte")
    expect(tid(page, f"bericht-art-{name}")).to_have_attribute("aria-current", "page")


def test_berichtswahl_und_alle_arten(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2024, 6, 15)) as (url, _), seite(browser, url, **DESKTOP) as page:
        _daten(url)
        _tags(url)
        fehler = []
        page.on("pageerror", lambda e: fehler.append(str(e)))
        page.goto(f"{url}/berichte")
        bereit(page, "berichte")
        expect(tid(page, "seite-berichte")).to_have_attribute("data-art", "uebersicht")
        expect(tid(page, "bericht-wahl").locator("a")).to_have_count(len(ARTEN))
        expect(tid(page, "bericht-konten")).to_be_visible()          # die bisherige Seite bleibt die Vorgabe
        for name in ARTEN[1:]:
            _art(page, name)
            assert page.url.endswith(f"/berichte?art={name}"), page.url
            for d in DIAGRAMME.get(name, ()):
                expect(tid(page, d)).to_have_attribute("data-gezeichnet", "ja")
            if name not in ("empfaenger",):
                expect(tid(page, "mb-kacheln")).to_be_visible()
        expect(tid(page, "tab-leiste").locator("[role=tab]")).to_have_count(1)      # ein Tab für alle Arten
        _art(page, "uebersicht")
        assert page.url.endswith("/berichte?art=uebersicht")
        assert not fehler, fehler


def test_vertraege_jahr_und_kategorien(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2024, 6, 15)) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro, spar, ids = _daten(url)
        page.goto(f"{url}/berichte?art=vertraege")
        bereit(page, "berichte")
        zeilen = tid(page, "mb-vertraege-tabelle").locator("tbody tr")
        expect(zeilen).to_have_count(1)                                   # Miete; die Sparrate ist eine Umbuchung
        expect(tid(page, "mb-kachel-monatlich").locator("[data-betrag]")).to_have_attribute("data-betrag", "80000")
        expect(tid(page, "mb-einnahmen-tabelle").locator("tbody tr")).to_have_count(1)
        zeilen.first.click()
        expect(tid(page, "mb-buchungen-dialog").locator("tbody tr")).to_have_count(6)
        page.keyboard.press("Escape")
        # Sortieren über den Spaltenkopf
        kopf = tid(page, "mb-vertraege-tabelle").locator("th").nth(3)
        expect(kopf).to_have_attribute("aria-sort", "descending")
        tid(page, "mb-vertraege-tabelle-sort-3").click()
        expect(kopf).to_have_attribute("aria-sort", "ascending")
        # Jahr: Monatskachel öffnet den Monatsbericht im selben Tab
        _art(page, "jahr")
        expect(tid(page, "mb-jahr")).to_have_value("2024")
        expect(tid(page, "mb-jahr-monat-2024-07")).to_be_disabled()
        tid(page, "mb-jahr-monat-2024-03").click()
        expect(tid(page, "seite-berichte")).to_have_attribute("data-monat", "2024-03")
        bereit(page, "berichte")
        assert "art=monat" in page.url and "monat=2024-03" in page.url
        # Kategorien: Baum, Einzelbuchungen einer Hauptkategorie
        _art(page, "kategorien")
        tabelle = tid(page, "mb-kategorien-ausgaben")
        expect(tabelle.locator("tbody tr")).to_have_count(2)
        tabelle.locator("tbody tr", has_text="Essen").click()
        expect(tid(page, "mb-buchungen-dialog").locator("tbody tr")).to_have_count(3)
        tid(page, "mb-dialog-schliessen").click()
        tid(page, "mb-monat-zurueck").click()
        bereit(page, "berichte")
        assert page.url.endswith("/berichte?art=kategorien&monat=2024-05")


def test_empfaenger_tags_und_vorschau(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2024, 6, 15)) as (url, _), seite(browser, url, **DESKTOP) as page:
        _daten(url)
        urlaub, auto = _tags(url)
        page.goto(f"{url}/berichte?art=empfaenger")
        bereit(page, "berichte")
        tid(page, "mb-rangliste-tabelle").locator("tbody tr", has_text="Supermarkt").click()
        expect(tid(page, "mb-kachel-typisch")).to_be_visible()
        bereit(page, "berichte")
        assert "empfaenger=" in page.url
        expect(tid(page, "mb-empfaenger-diagramm")).to_have_attribute("data-gezeichnet", "ja")
        expect(tid(page, "mb-empfaenger-punkte")).to_have_attribute("data-gezeichnet", "ja")
        tid(page, "mb-empfaenger-alle").click()
        expect(tid(page, "mb-buchungen-dialog").locator("tbody tr")).to_have_count(12)
        page.keyboard.press("Escape")
        tid(page, "mb-empfaenger-suche").fill("Vermieter (fiktiv)")
        tid(page, "mb-empfaenger-suche").press("Enter")
        expect(tid(page, "mb-stand")).to_contain_text("Vermieter (fiktiv)")
        bereit(page, "berichte")
        tid(page, "mb-empfaenger-zurueck").click()
        expect(tid(page, "mb-rangliste-tabelle")).to_be_visible()
        # Tags: Einzelauswertung und Vergleich
        _art(page, "tags")
        expect(tid(page, f"mb-tag-{urlaub}")).to_contain_text("2")
        tid(page, f"mb-tag-{urlaub}").click()
        expect(tid(page, "mb-tag-diagramm")).to_have_attribute("data-gezeichnet", "ja")
        expect(tid(page, "mb-kachel-buchungen")).to_contain_text("2")
        assert page.url.endswith(f"/berichte?art=tags&tag={urlaub}")
        tid(page, "mb-tags-zurueck").click()
        expect(tid(page, "mb-tags-vergleichen")).to_be_disabled()
        tid(page, f"mb-tag-wahl-{urlaub}").check()
        tid(page, f"mb-tag-wahl-{auto}").check()
        tid(page, "mb-tags-vergleichen").click()
        expect(tid(page, f"mb-kachel-tag-{auto}")).to_be_visible()
        expect(tid(page, f"mb-kachel-tag-{urlaub}")).to_be_visible()
        bereit(page, "berichte")
        tid(page, "mb-zeitraum-24").click()
        bereit(page, "berichte")
        assert "monate=24" in page.url
        # Vorschau: Zeitraum wechseln, erwartete Zahlungen
        _art(page, "vorschau")
        expect(tid(page, "mb-ereignisse-tabelle").locator("tbody tr")).to_have_count(4)   # Miete, Gehalt, Sparrate je 1 … 2
        tid(page, "mb-tage-30").click()
        expect(tid(page, "mb-tage-30")).to_have_attribute("aria-pressed", "true")
        bereit(page, "berichte")
        assert page.url.endswith("/berichte?art=vorschau&tage=30")


def test_berichte_handy(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2024, 6, 15)) as (url, _), seite(browser, url, **HANDY) as page:
        _daten(url)
        _tags(url)
        for name in ARTEN[1:]:
            page.goto(f"{url}/berichte?art={name}")
            bereit(page, "berichte")
            passt = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert passt, f"{name}: waagerechtes Rollen auf dem Handy"
            ueber = page.evaluate(
                "[...document.querySelectorAll('.mb-karte')].filter(el => el.scrollWidth > el.clientWidth + 1)"
                ".map(el => el.dataset.testid)")
            assert not ueber, f"{name}: {ueber} läuft über"
        expect(tid(page, "bericht-art-qualitaet")).to_be_in_viewport()
