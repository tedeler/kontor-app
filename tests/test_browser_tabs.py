"""Entwicklungstests für das Feature „tabs-gegenbuchung“ (Branch feature/tabs-gegenbuchung): Tabs der Ansichten
und „Gehe zur Gegenbuchung“ im Kontextmenü. Playwright mit Chrome headless gegen einen echten Server im Mock-Modus
(synthetische Daten). Ersetzen nicht die Abnahmetests aus kontor-tests.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from .conftest import kmy, transaktion
from .test_browser import DESKTOP, HANDY, bereit, browser, expect, seite, server, tid  # noqa: F401

KONTEN = ('<ACCOUNT id="A1" name="Giro" type="1" parentaccount="AStd::Asset" currency="EUR">'
          '<KEYVALUEPAIRS><PAIR key="iban" value="DE57 0000 0000 0532 0130 00"/></KEYVALUEPAIRS></ACCOUNT>'
          '<ACCOUNT id="A3" name="Sparkonto" type="1" parentaccount="AStd::Asset" currency="EUR"/>'
          '<ACCOUNT id="A2" name="Lebensmittel" type="13" parentaccount="AStd::Expense" currency="EUR"/>'
          '<ACCOUNT id="A4" name="Drogerie" type="13" parentaccount="AStd::Expense" currency="EUR"/>')


def _daten(basis):
    from kontor.config import KontorConfig
    from kontor.importer.kmymoney import importiere_kmy

    t = "".join(transaktion(f"T{i}", f"2024-01-{i:02d}", ("A1", f"-{i * 100}/100"), ("A2", f"{i * 100}/100"),
                            memo=f"Einkauf {i}") for i in range(1, 21))
    t += transaktion("TU", "2024-02-01", ("A1", "-5000/100"), ("A3", "5000/100"), memo="Sparen")
    t += transaktion("TS", "2024-02-02", ("A1", "-3000/100"), ("A2", "2000/100"), ("A4", "1000/100"), memo="Markt gemischt")
    config = KontorConfig(datenbank=basis / "kontor.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 30))
    assert importiere_kmy(config, kmy(KONTEN, transaktionen=t)).erfolgreich


@pytest.fixture
def umgebung(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        konten = {k["name"]: k["id"] for k in _get(url + "/api/konten")}
        buchungen = _get(url + "/api/buchungen", konto_id=konten["Giro"], pro_seite=200)["eintraege"]
        nach_zweck = {b["verwendungszweck"]: b["id"] for b in buchungen}
        yield url, page, konten, nach_zweck


def _get(adresse, **params):
    with httpx.Client(trust_env=False) as c:
        return c.get(adresse, params=params).json()


def _zeile(page, bid):
    return tid(page, f"buchung-{bid}")


def _tabs(page):
    return page.locator('[data-testid="tab-leiste"] [data-testid="tab"]')


def _tab(page, pfad):
    return page.locator(f'[data-testid="tab-leiste"] [data-testid="tab"][data-pfad="{pfad}"]')


def test_tab_behaelt_zustand_und_wird_wieder_geoeffnet(umgebung):
    url, page, konten, zweck = umgebung
    giro = f"/konten/{konten['Giro']}"
    page.goto(url + giro)
    bereit(page, "konto")
    expect(_tabs(page)).to_have_count(1)
    expect(_tab(page, giro)).to_have_attribute("aria-selected", "true")
    expect(_tab(page, giro)).to_contain_text("Giro")
    # Zustand: Auswahl und aufgeklappte Filterleiste
    _zeile(page, zweck["Einkauf 3"]).locator('[data-feld="datum"]').click()
    _zeile(page, zweck["Einkauf 5"]).locator('[data-feld="datum"]').click(modifiers=["Control"])
    tid(page, "filter-umschalten").click()
    expect(tid(page, "filter-leiste")).to_be_visible()
    expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
    # anderes Konto über die Navigation: neuer Tab, nur eine Kontoansicht im Dokument
    tid(page, "nav-konten").click()
    bereit(page, "konten")
    page.locator(f'a[href="/konten/{konten["Sparkonto"]}"]').first.click()
    bereit(page, "konto")
    expect(page.locator("h1")).to_have_text("Sparkonto")
    expect(_tabs(page)).to_have_count(3)
    expect(tid(page, "buchungsliste")).to_have_count(1)
    # zurück zum Giro-Tab: Auswahl und Filterleiste unverändert
    _tab(page, giro).get_by_test_id("tab-titel").click()
    expect(page).to_have_url(url + giro)
    expect(page.locator("h1")).to_have_text("Giro")
    expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
    expect(_zeile(page, zweck["Einkauf 5"])).to_have_attribute("aria-selected", "true")
    expect(tid(page, "filter-leiste")).to_be_visible()
    # Navigation zu einem offenen Konto aktiviert dessen Tab statt eines zweiten
    tid(page, "nav-konten").click()
    bereit(page, "konten")
    page.locator(f'a[href="{giro}"]').first.click()
    expect(page.locator("h1")).to_have_text("Giro")
    expect(_tabs(page)).to_have_count(3)
    expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
    # schließen: Nachbar wird aktiv; erneutes Anfordern öffnet den Tab wieder (frisch)
    _tab(page, giro).get_by_test_id("tab-schliessen").click()
    expect(_tabs(page)).to_have_count(2)
    expect(_tab(page, giro)).to_have_count(0)
    tid(page, "nav-konten").click()
    bereit(page, "konten")
    page.locator(f'a[href="{giro}"]').first.click()
    bereit(page, "konto")
    expect(_tab(page, giro)).to_have_count(1)
    expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "0")


def test_tabs_bleiben_ueber_neuladen_mit_filtern(umgebung):
    url, page, konten, _ = umgebung
    giro = f"/konten/{konten['Giro']}"
    page.goto(url + giro + "?verwendungszweck=Einkauf+1")
    bereit(page, "konto")
    tid(page, "nav-uebersicht").click()
    bereit(page, "uebersicht")
    page.reload()
    bereit(page, "uebersicht")
    expect(_tabs(page)).to_have_count(2)
    expect(_tab(page, "/")).to_have_attribute("aria-selected", "true")
    # der gespeicherte Tab lädt beim Aktivieren mit seinem Filter
    _tab(page, giro).get_by_test_id("tab-titel").click()
    bereit(page, "konto")
    expect(page).to_have_url(url + giro + "?verwendungszweck=Einkauf+1")
    expect(tid(page, "filter-anzahl")).to_have_attribute("data-anzahl", "1")
    # direkter Aufruf ohne Abfrageteil: die URL gilt
    page.goto(url + giro)
    bereit(page, "konto")
    expect(tid(page, "filter-anzahl")).to_have_attribute("data-anzahl", "0")


def test_aenderung_laedt_andere_tabs_neu(umgebung):
    url, page, konten, zweck = umgebung
    giro, leb = f"/konten/{konten['Giro']}", f"/konten/{konten['Lebensmittel']}"
    page.goto(url + leb)
    bereit(page, "konto")
    expect(tid(page, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", "21")
    page.goto(url + giro)
    bereit(page, "konto")
    _zeile(page, zweck["Einkauf 1"]).locator('[data-feld="datum"]').click()
    _zeile(page, zweck["Einkauf 1"]).click(button="right")
    tid(page, "km-kategorie").click()
    page.keyboard.type("droger")
    page.keyboard.press("Enter")
    expect(page.locator('[data-testid="meldung"][data-art="erfolg"]').first).to_contain_text("Drogerie")
    _tab(page, leb).get_by_test_id("tab-titel").click()
    expect(page.locator("h1")).to_have_text("Lebensmittel")
    expect(tid(page, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", "20")


def test_gegenbuchung_eine_gegenseite(umgebung):
    url, page, konten, zweck = umgebung
    page.goto(url + f"/konten/{konten['Giro']}")
    bereit(page, "konto")
    bid = zweck["Einkauf 7"]
    _zeile(page, bid).click(button="right")
    eintrag = tid(page, "km-gegenbuchung")
    expect(eintrag).to_have_text("Gehe zur Gegenbuchung")
    eintrag.click()
    expect(page).to_have_url(url + f"/konten/{konten['Lebensmittel']}")
    bereit(page, "konto")
    expect(page.locator("h1")).to_have_text("Lebensmittel")
    expect(_zeile(page, bid)).to_have_attribute("aria-selected", "true")
    expect(_zeile(page, bid)).to_be_focused()
    expect(_tabs(page)).to_have_count(2)
    # und zurück aus der Kategorie zum Bankkonto, in den offenen Tab
    _zeile(page, bid).click(button="right")
    tid(page, "km-gegenbuchung").click()
    expect(page.locator("h1")).to_have_text("Giro")
    expect(_zeile(page, bid)).to_have_attribute("aria-selected", "true")
    expect(_tabs(page)).to_have_count(2)
    # Umbuchung zwischen Bestandskonten
    _zeile(page, zweck["Sparen"]).click(button="right")
    tid(page, "km-gegenbuchung").click()
    expect(page.locator("h1")).to_have_text("Sparkonto")
    expect(_zeile(page, zweck["Sparen"])).to_have_attribute("aria-selected", "true")


def test_gegenbuchung_mehrere_gegenseiten_untermenue(umgebung):
    url, page, konten, zweck = umgebung
    page.goto(url + f"/konten/{konten['Giro']}")
    bereit(page, "konto")
    bid = zweck["Markt gemischt"]
    _zeile(page, bid).click(button="right")
    tid(page, "km-gegenbuchung").click()
    expect(tid(page, f"km-gegenbuchung-{konten['Lebensmittel']}")).to_be_visible()
    expect(tid(page, f"km-gegenbuchung-{konten['Drogerie']}")).to_have_text("Drogerie")
    expect(tid(page, f"km-gegenbuchung-{konten['Lebensmittel']}")).to_be_focused()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(page.locator("h1")).to_have_text("Drogerie")
    expect(_zeile(page, bid)).to_have_attribute("aria-selected", "true")


def test_gegenbuchung_setzt_verdeckende_filter_zurueck(umgebung):
    url, page, konten, zweck = umgebung
    leb = f"/konten/{konten['Lebensmittel']}"
    page.goto(url + leb + "?verwendungszweck=Einkauf+2")
    bereit(page, "konto")
    page.goto(url + f"/konten/{konten['Giro']}")
    bereit(page, "konto")
    bid = zweck["Einkauf 9"]
    _zeile(page, bid).click(button="right")
    tid(page, "km-gegenbuchung").click()
    expect(page.locator("h1")).to_have_text("Lebensmittel")
    expect(_zeile(page, bid)).to_have_attribute("aria-selected", "true")
    expect(page).to_have_url(url + leb)
    expect(tid(page, "filter-anzahl")).to_have_attribute("data-anzahl", "0")
    expect(page.locator('[data-testid="meldung"][data-art="hinweis"]').first).to_contain_text("Filter zurückgesetzt")


def test_mobil_tabs_und_gegenbuchung(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        konten = {k["name"]: k["id"] for k in _get(url + "/api/konten")}
        page.goto(url + f"/konten/{konten['Giro']}")
        bereit(page, "konto")
        expect(tid(page, "tab-leiste")).to_be_visible()
        zeile = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]', has_text="Einkauf 4").first
        zeile.click(button="right")
        tid(page, "km-gegenbuchung").click()
        bereit(page, "konto")
        expect(page.locator("h1")).to_have_text("Lebensmittel")
        expect(_tabs(page)).to_have_count(2)
