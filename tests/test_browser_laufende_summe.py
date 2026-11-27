"""Browser-Rauchtest (D-322): Spalte „Summe“ im Kontoblatt – Stand nach jeder Buchung über alle Buchungen bis zu
dieser, unabhängig von Filtern; beim Kreditkonto mit umgedrehtem Vorzeichen wie der Betrag; mobil ausgeblendet.
Nur Mock-Modus, synthetische Daten."""

from __future__ import annotations

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)
from .test_browser_kredit_spalten import _daten
from .test_browser_tabs import _get

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-id]'


def _spalten(page):
    return page.locator(ZEILEN).evaluate_all("""els => els.map((z) => [Number(z.dataset.id),
      Number(z.querySelector('[data-feld="betrag"]').dataset.betrag),
      z.querySelector('[data-feld="saldo"]').dataset.betrag === undefined ? null
        : Number(z.querySelector('[data-feld="saldo"]').dataset.betrag)])""")


def test_spalte_summe(tmp_path, browser):
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro['id']}")
        bereit(page, "konto")
        expect(page.locator('[data-testid="buchungsliste"] .liste-kopf [data-feld="saldo"]')).to_have_text("Summe")
        zeilen = _spalten(page)
        # absteigend nach Datum: oberste Zeile = Kontostand, darunter je Zeile um den Betrag der Zeile darüber weniger
        stand = sum(b["betrag"] for b in _get(url + "/api/buchungen", konto_id=giro["id"], pro_seite=500)["eintraege"])
        assert zeilen[0][2] == stand
        for (_, betrag, saldo), (_, _, naechster) in zip(zeilen, zeilen[1:]):
            assert saldo - betrag == naechster
        voll = {i: s for i, _, s in zeilen}
        # Filter ändern die Summe nicht
        page.goto(f"{url}/konten/{giro['id']}?verwendungszweck=Einkauf%203")
        bereit(page, "konto")
        gefiltert = _spalten(page)
        assert len(gefiltert) == 1 and gefiltert[0][2] == voll[gefiltert[0][0]]
        # Kreditkonto: Summe wie der Betrag umgedreht
        tid(page, "konto-einstellungen-oeffnen").click()
        tid(page, "einstellungen-art").select_option("kreditkonto")
        tid(page, "einstellungen-speichern").click()
        expect(tid(page, "konto-einstellungen")).to_have_count(0)
        page.goto(f"{url}/konten/{giro['id']}")
        bereit(page, "konto")
        assert {i: s for i, _, s in _spalten(page)} == {i: -s for i, s in voll.items()}


def test_mobil_ohne_summe(tmp_path, browser):
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        giro = next(k for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro['id']}")
        bereit(page, "konto")
        expect(page.locator(ZEILEN).first.locator('[data-feld="saldo"]')).to_be_hidden()
