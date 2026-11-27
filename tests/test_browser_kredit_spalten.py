"""Browser-Rauchtest (D-318): Das Kontoblatt eines Kreditkontos zeigt Beträge wie GnuCash in zwei Spalten
„Zahlung“ (Gutschrift, mindert die Schulden) und „Belastung“ (Abbuchung), beide ohne Vorzeichen. Girokonten und die
mobile Liste bleiben bei einer Spalte. Nur Mock-Modus, synthetische Daten."""

from __future__ import annotations

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)
from .test_browser_tabs import _daten, _get

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-id]'


def _text(cent: int) -> str:
    euro, rest = divmod(abs(cent), 100)
    gruppen = f"{euro:,}".replace(",", ".")
    return f"{gruppen},{rest:02d}\u00a0€"


def _zellen(page):
    return page.locator(ZEILEN).evaluate_all("""els => els.map((z) => {
      const c = z.querySelector('[data-feld="betrag"]');
      const t = (s) => { const e = c.querySelector(s); return e ? e.textContent.trim() : null; };
      return { betrag: Number(c.dataset.betrag), zahlung: t('[data-teil="zahlung"]'), belastung: t('[data-teil="belastung"]') };
    })""")


def test_kreditkonto_mit_zahlung_und_belastung(tmp_path, browser):
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k for k in _get(url + "/api/konten") if k["name"] == "Giro")
        page.goto(f"{url}/konten/{giro['id']}")
        bereit(page, "konto")
        # Girokonto: eine Spalte „Betrag“, ohne Teile
        expect(tid(page, "spalte-betrag")).to_have_text("Betrag")
        assert all(z["zahlung"] is None and z["belastung"] is None for z in _zellen(page))
        tid(page, "konto-einstellungen-oeffnen").click()
        tid(page, "einstellungen-art").select_option("kreditkonto")
        tid(page, "einstellungen-speichern").click()
        expect(tid(page, "konto-einstellungen")).to_have_count(0)
        expect(page.locator('[data-testid="buchungsliste"]')).to_have_attribute("data-zwei-betraege", "ja")
        expect(tid(page, "spalte-betrag")).to_contain_text("Zahlung")
        expect(tid(page, "spalte-betrag")).to_contain_text("Belastung")
        zellen = _zellen(page)
        assert any(z["betrag"] > 0 for z in zellen) and any(z["betrag"] < 0 for z in zellen), zellen
        for z in zellen:
            # angezeigter Betrag (D-312): Abbuchung positiv = Belastung, Gutschrift negativ = Zahlung
            if z["betrag"] > 0:
                assert z == {"betrag": z["betrag"], "zahlung": "", "belastung": _text(z["betrag"])}, z
            elif z["betrag"] < 0:
                assert z == {"betrag": z["betrag"], "zahlung": _text(z["betrag"]), "belastung": ""}, z
        # Sortierung über den gemeinsamen Spaltenkopf bleibt die nach Betrag
        tid(page, "spalte-betrag").click()
        expect(page).to_have_url(f"{url}/konten/{giro['id']}?sortierung=betrag")
        # mobile Liste: weiter ein Betrag mit Vorzeichen
        page.set_viewport_size({"width": 390, "height": 800})
        expect(page.locator('[data-testid="buchungsliste"]')).to_have_attribute("data-zwei-betraege", "nein")
        assert all(z["zahlung"] is None for z in _zellen(page))
