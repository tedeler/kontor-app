"""Browser-Rauchtest (D-312): Kontotyp und Kontoinhaber in den Kontoeinstellungen; ein Kreditkonto zeigt Beträge
im Kontoblatt und den Kontostand in der Kontenliste umgedreht, die Finanzübersicht zählt ihn negativ. Nur
Mock-Modus, synthetische Daten."""

from __future__ import annotations

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)
from .test_browser_tabs import _daten, _get

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-id]'


def test_kreditkonto_und_inhaber(tmp_path, browser):
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        giro = next(k for k in _get(url + "/api/konten") if k["name"] == "Giro")
        saldo = next(k for k in _get(url + "/api/kontenuebersicht")["konten"] if k["konto_id"] == giro["id"])["saldo_gesamt"]
        assert saldo < 0
        page.goto(f"{url}/konten/{giro['id']}")
        bereit(page, "konto")
        erste = page.locator(ZEILEN).first
        roh = int(erste.locator('[data-feld="betrag"]').get_attribute("data-betrag"))
        assert roh < 0                                    # Girokonto: Abbuchung negativ
        tid(page, "konto-einstellungen-oeffnen").click()
        d = tid(page, "konto-einstellungen")
        expect(tid(page, "einstellungen-art")).to_have_value("girokonto")
        tid(page, "einstellungen-art").select_option("kreditkonto")
        tid(page, "einstellungen-inhaber-vorname").fill("Erika")
        tid(page, "einstellungen-inhaber-nachname").fill("Mustermann")
        tid(page, "einstellungen-speichern").click()
        expect(d).to_have_count(0)
        k = next(k for k in _get(url + "/api/konten") if k["id"] == giro["id"])
        assert k["art"] == "kreditkonto" and k["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
        # Kontoblatt: dieselbe Abbuchung jetzt positiv, gespeichert unverändert
        expect(page.locator(ZEILEN).first.locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", str(-roh))
        assert _get(url + "/api/buchungen", konto_id=giro["id"], pro_seite=1, sortierung="-datum")["eintraege"][0]["betrag"] == roh
        # Sortierung nach Betrag folgt der Anzeige (aufsteigend: kleinste angezeigte Abbuchung zuerst)
        page.goto(f"{url}/konten/{giro['id']}?sortierung=betrag")
        bereit(page, "konto")
        werte = [int(x) for x in page.locator(ZEILEN + ' [data-feld="betrag"]').evaluate_all(
            "els => els.map((e) => e.dataset.betrag)")]
        assert werte == sorted(werte) and werte[0] > 0, werte
        # die Einstellungen zeigen den neuen Stand
        tid(page, "konto-einstellungen-oeffnen").click()
        expect(tid(page, "einstellungen-art")).to_have_value("kreditkonto")
        expect(tid(page, "einstellungen-inhaber-vorname")).to_have_value("Erika")
        tid(page, "einstellungen-inhaber-vorname").fill("")
        tid(page, "einstellungen-inhaber-nachname").fill("")
        tid(page, "einstellungen-speichern").click()
        expect(tid(page, "konto-einstellungen")).to_have_count(0)
        assert "inhaber" not in next(k for k in _get(url + "/api/konten") if k["id"] == giro["id"])
        # Kontenliste: Kontostand als Schulden positiv, data-betrag gespeichert
        page.goto(f"{url}/konten")
        bereit(page, "konten")
        zelle = tid(page, f"kontenbaum-konto-{giro['id']}").locator('[data-feld="saldo"]')
        expect(zelle).to_have_attribute("data-betrag", str(saldo))
        expect(zelle).not_to_contain_text("-")
        # Finanzübersicht: negativ
        page.goto(f"{url}/")
        bereit(page, "uebersicht")
        z = tid(page, f"uebersicht-konto-{giro['id']}").locator('[data-feld="saldo"]')
        expect(z).to_have_attribute("data-betrag", str(saldo))
        expect(z).to_contain_text("-")
