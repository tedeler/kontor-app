"""Browser-Rauchtest zu D-208: Gruppierung nach Datum mit vier festen Abschnitten je Monat (1.–7., 8.–14., 15.–21.,
22.–Monatsende) zwischen Monat und Tag. Synthetische Daten, eigener Server auf einem freien Loopback-Port."""

from __future__ import annotations

import os

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401

# Tag → Betrag in Cent; Grenztage der Abschnitte und ein Schaltjahr-Februar
BUCHUNGEN = {"2024-11-01": 100, "2024-11-07": 200, "2024-11-08": 400, "2024-11-21": 800, "2024-11-22": 1600,
             "2024-11-30": 3200, "2024-02-29": 500}


def _daten(url):
    c = httpx.Client(base_url=url)
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    ids = {}
    for datum, cent in BUCHUNGEN.items():
        r = c.post("/api/buchungen", json={"datum": datum, "status": "bestaetigt", "verwendungszweck": "fiktiv", "splits": [
            {"konto_id": g, "betrag": -cent}, {"konto_id": kat, "betrag": cent}]})
        assert r.status_code == 201, r.text
        ids[datum] = r.json()["id"]
    return g, ids


def test_vier_abschnitte_je_monat(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        g, ids = _daten(url)
        page.goto(f"{url}/konten/{g}?gruppierung=datum")
        bereit(page, "konto")
        liste = tid(page, "buchungsliste")
        ebenen = [(e.get_attribute("data-periode"), e.get_attribute("data-ebene"))
                  for e in liste.locator(".perioden-balken").all()]
        # absteigend nach Datum: Jahr, Monat, Abschnitt, Tag, jeweils ineinander
        assert ebenen[:5] == [("2024", "jahr"), ("2024-11", "monat"), ("2024-11-a4", "abschnitt"),
                              ("2024-11-30", "tag"), ("2024-11-22", "tag")]
        assert [p for p, e in ebenen if e == "abschnitt"] == ["2024-11-a4", "2024-11-a3", "2024-11-a2", "2024-11-a1",
                                                              "2024-02-a4"]
        # Beschriftung ist der Datumsbereich; der letzte Abschnitt reicht bis zum Monatsende
        for schluessel, text in (("2024-11-a1", "01.–07.11."), ("2024-11-a2", "08.–14.11."), ("2024-11-a3", "15.–21.11."),
                                 ("2024-11-a4", "22.–30.11."), ("2024-02-a4", "22.–29.02.")):
            expect(tid(page, f"periode-{schluessel}")).to_contain_text(text)
        # Summen: die Abschnitte ergeben zusammen den Monat
        summe = lambda k: int(tid(page, f"periode-summe-{k}").get_attribute("data-betrag"))  # noqa: E731
        assert [summe(f"2024-11-a{n}") for n in (1, 2, 3, 4)] == [-300, -400, -800, -4800]
        assert summe("2024-11") == -6300
        expect(tid(page, "periode-anzahl-2024-11-a1")).to_have_attribute("data-anzahl", "2")
        if os.environ.get("KONTOR_BILD"):
            page.screenshot(path=os.environ["KONTOR_BILD"])
        # Abschnitt zuklappen verbirgt seine Tage und Buchungen, die übrigen bleiben
        tid(page, "periode-2024-11-a1").click()
        expect(tid(page, "periode-2024-11-a1")).to_have_attribute("aria-expanded", "false")
        expect(tid(page, "periode-2024-11-01")).to_have_count(0)
        expect(tid(page, f"buchung-{ids['2024-11-07']}")).to_have_count(0)
        expect(tid(page, f"buchung-{ids['2024-11-08']}")).to_be_visible()
        # „Alles zusammenklappen“ gilt auch für die Abschnitte
        tid(page, "gruppierung-zu").click()
        expect(liste.locator(".perioden-balken")).to_have_count(1)
        tid(page, "gruppierung-auf").click()
        expect(tid(page, f"buchung-{ids['2024-11-07']}")).to_be_visible()


def test_tiefe_der_gruppierung(tmp_path, browser):  # noqa: F811
    """D-209: Die gewählte Ebene ist die tiefste; sie steht in der Adresse, die volle Tiefe ist die Vorgabe."""
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        g, ids = _daten(url)
        page.goto(f"{url}/konten/{g}?gruppierung=datum&tiefe=abschnitt")
        bereit(page, "konto")
        liste = tid(page, "buchungsliste")
        ebenen = lambda: {e.get_attribute("data-ebene") for e in liste.locator(".perioden-balken").all()}  # noqa: E731
        gedrueckt = lambda: [k for k in ("keine", "jahr", "monat", "abschnitt", "datum")  # noqa: E731
                             if tid(page, f"gruppierung-{k}").get_attribute("aria-pressed") == "true"]
        # aus der Adresse: bis Abschnitt, die Buchungen stehen direkt unter dem Abschnitt
        expect(tid(page, "gruppierung-abschnitt")).to_have_attribute("aria-pressed", "true")
        assert ebenen() == {"jahr", "monat", "abschnitt"} and gedrueckt() == ["abschnitt"]
        expect(tid(page, f"buchung-{ids['2024-11-07']}")).to_be_visible()
        assert int(tid(page, "periode-summe-2024-11-a1").get_attribute("data-betrag")) == -300
        if os.environ.get("KONTOR_BILD"):
            page.screenshot(path=os.environ["KONTOR_BILD"].replace(".png", "-tiefe.png"))
        # Monat: Jahr → Monat → Buchungen
        tid(page, "gruppierung-monat").click()
        expect(liste.locator('.perioden-balken[data-ebene="abschnitt"]')).to_have_count(0)
        assert ebenen() == {"jahr", "monat"} and gedrueckt() == ["monat"]
        assert "tiefe=monat" in page.url and "gruppierung=datum" in page.url
        tid(page, "periode-2024-11").click()   # Monat zuklappen verbirgt seine Buchungen
        expect(tid(page, f"buchung-{ids['2024-11-07']}")).to_have_count(0)
        expect(tid(page, f"buchung-{ids['2024-02-29']}")).to_be_visible()
        # Jahr
        tid(page, "gruppierung-jahr").click()
        expect(liste.locator(".perioden-balken")).to_have_count(1)
        expect(tid(page, f"buchung-{ids['2024-11-07']}")).to_be_visible()
        # Tag ist die volle Tiefe und steht nicht in der Adresse
        tid(page, "gruppierung-datum").click()
        expect(tid(page, "periode-2024-02-29")).to_be_visible()
        assert ebenen() == {"jahr", "monat", "abschnitt", "tag"} and gedrueckt() == ["datum"]
        assert "tiefe=" not in page.url and "gruppierung=datum" in page.url
        # Kürzel v g schaltet weiter: Tag → keine → Jahr
        page.keyboard.press("Escape")
        liste.locator(".perioden-knopf").first.focus()
        page.keyboard.press("v")
        page.keyboard.press("g")
        expect(tid(page, "gruppierung-keine")).to_have_attribute("aria-pressed", "true")
        expect(liste.locator(".perioden-balken")).to_have_count(0)
        assert "gruppierung" not in page.url and "tiefe" not in page.url
        page.keyboard.press("v")
        page.keyboard.press("g")
        expect(tid(page, "gruppierung-jahr")).to_have_attribute("aria-pressed", "true")
        # unbekannte Tiefe in der Adresse gilt wie ohne Angabe
        page.goto(f"{url}/konten/{g}?gruppierung=datum&tiefe=woche")
        bereit(page, "konto")
        expect(tid(page, "gruppierung-datum")).to_have_attribute("aria-pressed", "true")
