"""Browser-Rauchtests des Sammelpakets `feature/sammel3` (D-218 ff.)."""

from __future__ import annotations

import sqlite3

import pytest

from .conftest import kmy, transaktion
from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

KONTEN = ('<ACCOUNT id="A1" name="Giro" type="1" parentaccount="AStd::Asset" currency="EUR"/>'
          '<ACCOUNT id="A3" name="Spar" type="1" parentaccount="AStd::Asset" currency="EUR"/>'
          '<ACCOUNT id="A2" name="Lebensmittel" type="13" parentaccount="AStd::Expense" currency="EUR"/>')
PAYEES = '<PAYEE id="P1" name="Markt"/><PAYEE id="P2" name="Bäcker"/>'


def _daten(config):
    from kontor.importer.kmymoney import importiere_kmy
    t = "".join(transaktion(f"T{i}", f"2024-01-{i:02d}", ("A1" if i < 4 else "A3", "-5/1"), ("A2", "5/1"))
                .replace("<TRANSACTION", "<TRANSACTION").replace('<SPLIT account="A', '<SPLIT payee="P1" account="A', 1)
                for i in range(1, 6))
    assert importiere_kmy(config, kmy(KONTEN, payees=PAYEES, transaktionen=t)).erfolgreich


def test_empfaenger_menue_regel_und_konto(tmp_path, browser):
    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **DESKTOP) as page:
        _daten(config)
        con = sqlite3.connect(config.aktive_datenbank)
        markt, = con.execute("SELECT id FROM empfaenger WHERE name = 'Markt'").fetchone()
        con.execute("INSERT INTO empfaenger_alias (empfaenger_id, alias, ekey) VALUES (?, 'MARKT \"GMBH\"', 'marktgmbh')", (markt,))
        con.commit()
        con.close()
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        expect(tid(page, "empfaenger-liste")).not_to_contain_text("Standardkategorie")
        tid(page, f"empfaenger-{markt}").click(button="right")
        expect(tid(page, "em-regel")).to_be_visible()
        # zwei Konten mit Buchungen: Untermenü, das meistbenutzte zuerst
        tid(page, "em-im-konto").hover()
        eintraege = page.locator("[data-testid^=em-im-konto-]")
        expect(eintraege).to_have_count(2)
        expect(eintraege.first).to_have_text("Giro (3)")
        eintraege.first.click()
        bereit(page, "konto")
        assert "/konten/" in page.url
        expect(page.locator("[data-testid^=buchung-zeile-], [role=row][data-id]")).to_have_count(3)
        # Regel erstellen: Editor mit Empfänger und Alias vorbelegt
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        tid(page, f"empfaenger-{markt}").click(button="right")
        tid(page, "em-regel").click()
        expect(tid(page, "regel-dialog")).to_be_visible()
        expect(tid(page, "regel-name")).to_have_value("Markt")
