"""Browser-Rauchtest zu D-313: Im Konto- und im Kategorieblatt blendet der Schalter „mit Unterkonten“ bzw. „mit
Unterkategorien“ die Buchungen aller Unterkonten ein; jede Buchung eines Unterkontos zeigt, woher sie kommt.
Synthetische Daten, eigener Server auf einem freien Loopback-Port."""

from __future__ import annotations

import os

import httpx

from .test_browser import DESKTOP, HANDY, bereit, browser, expect, seite, server, tid  # noqa: F401


def _daten(url):
    c = httpx.Client(base_url=url)
    konto = lambda name, art, eltern=None: c.post("/api/konten", json={  # noqa: E731
        "name": name, "art": art, **({"eltern_id": eltern} if eltern else {})}).json()["id"]
    k = {"giro": konto("Giro", "girokonto")}
    k["ruecklage"] = konto("Rücklage", "sparkonto", k["giro"])
    k["urlaub"] = konto("Urlaub", "sparkonto", k["ruecklage"])
    k["leben"] = konto("Lebensmittel", "aufwand")
    k["baecker"] = konto("Bäcker", "aufwand", k["leben"])
    k["markt"] = konto("Markt", "aufwand", k["leben"])
    k["frei"] = konto("Freizeit", "aufwand")

    def buchung(datum, empfaenger, splits):
        e = c.post("/api/empfaenger", json={"name": empfaenger}).json()["id"]
        r = c.post("/api/buchungen", json={"datum": datum, "status": "bestaetigt", "empfaenger_id": e,
                                           "verwendungszweck": "fiktiv", "splits": splits})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    b = {
        "direkt": buchung("2026-11-02", "Laden A", [{"konto_id": k["giro"], "betrag": -500},
                                                    {"konto_id": k["leben"], "betrag": 500}]),
        "baecker": buchung("2026-11-03", "Bäckerei B", [{"konto_id": k["giro"], "betrag": -300},
                                                        {"konto_id": k["baecker"], "betrag": 300}]),
        "urlaub": buchung("2026-11-04", "Reise C", [{"konto_id": k["urlaub"], "betrag": -2000},
                                                    {"konto_id": k["frei"], "betrag": 2000}]),
        "split": buchung("2026-11-05", "Markt D", [{"konto_id": k["giro"], "betrag": -900},
                                                   {"konto_id": k["baecker"], "betrag": 400},
                                                   {"konto_id": k["markt"], "betrag": 500}]),
    }
    return k, b


def test_unterkonten_im_kontoblatt(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        k, b = _daten(url)
        page.goto(f"{url}/konten/{k['giro']}")
        bereit(page, "konto")
        schalter = tid(page, "unterkonten-schalter")
        expect(schalter).to_have_text("mit Unterkonten")
        expect(schalter).to_have_attribute("aria-pressed", "false")
        expect(tid(page, f"buchung-{b['urlaub']}")).to_have_count(0)
        expect(tid(page, "herkunft")).to_have_count(0)
        schalter.click()
        expect(schalter).to_have_attribute("aria-pressed", "true")
        expect(tid(page, f"buchung-{b['urlaub']}")).to_be_visible()
        assert "unterkonten=true" in page.url
        # Herkunft: Pfad ab dem Konto der Ansicht; Buchungen des Kontos selbst ohne Marke
        marke = tid(page, f"buchung-{b['urlaub']}").locator("[data-testid=herkunft]")
        expect(marke).to_have_text("Rücklage › Urlaub")
        expect(marke).to_have_attribute("data-konto-ids", str(k["urlaub"]))
        expect(tid(page, f"buchung-{b['direkt']}").locator("[data-testid=herkunft]")).to_have_count(0)
        expect(tid(page, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", "4")
        expect(tid(page, "buchungsliste-summe")).to_have_attribute("data-betrag", "-3700")
        # Kontrollkästchen im Filter-Baukasten zeigt denselben Zustand
        expect(tid(page, "filter-unterkonten")).to_be_checked()
        if os.environ.get("KONTOR_BILD"):
            page.screenshot(path=os.environ["KONTOR_BILD"] + "-konto.png")
        # Kürzel f u schaltet wieder aus
        tid(page, "buchungsliste").focus()
        page.keyboard.press("f")
        page.keyboard.press("u")
        expect(schalter).to_have_attribute("aria-pressed", "false")
        expect(tid(page, f"buchung-{b['urlaub']}")).to_have_count(0)


def test_unterkategorien_im_kategorieblatt(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        k, b = _daten(url)
        page.goto(f"{url}/konten/{k['leben']}?unterkonten=true")
        bereit(page, "konto")
        expect(tid(page, "unterkonten-schalter")).to_have_text("mit Unterkategorien")
        expect(tid(page, "unterkonten-schalter")).to_have_attribute("aria-pressed", "true")
        expect(tid(page, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", "3")
        expect(tid(page, f"buchung-{b['baecker']}").locator("[data-testid=herkunft]")).to_have_text("Bäcker")
        # Split über zwei Unterkategorien: beide
        marke = tid(page, f"buchung-{b['split']}").locator("[data-testid=herkunft]")
        expect(marke).to_have_text("Bäcker, Markt")
        expect(tid(page, f"buchung-{b['direkt']}").locator("[data-testid=herkunft]")).to_have_count(0)
        if os.environ.get("KONTOR_BILD"):
            page.screenshot(path=os.environ["KONTOR_BILD"] + "-kategorie.png")


def test_ohne_unterkonten_kein_schalter(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        k, _b = _daten(url)
        page.goto(f"{url}/konten/{k['frei']}")
        bereit(page, "konto")
        expect(tid(page, "unterkonten-schalter")).to_be_hidden()


def test_herkunft_mobil(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        k, b = _daten(url)
        page.goto(f"{url}/konten/{k['giro']}?unterkonten=true")
        bereit(page, "konto")
        expect(tid(page, f"buchung-{b['urlaub']}").locator("[data-testid=herkunft]")).to_be_visible()
        if os.environ.get("KONTOR_BILD"):
            page.screenshot(path=os.environ["KONTOR_BILD"] + "-mobil.png")
