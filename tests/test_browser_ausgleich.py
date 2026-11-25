"""Browser-Rauchtest (D-280): Zwei Ausgleichsbuchungen mit unterschiedlichem Betrag innerhalb einer Woche – Kontor
fragt in einem Fenster, ob sie zusammengeführt werden sollen. Nur Mock-Modus, synthetische Daten."""

from __future__ import annotations

import datetime as dt

import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
IBAN = "DE02000000000000000001"


def _bank_meldet(config, konto_id: int, betrag: int, tag: str) -> None:
    """Saldoabgleich wie nach einem Abruf: Die Bank meldet am Stichtag diesen Kontostand."""
    from kontor import db
    from kontor.plugins.bank import BankSaldo, Umsatzliste
    from kontor.sync import SyncDienst

    con = db.verbinde(config.aktive_datenbank)
    try:
        with db.transaktion(con):
            lid = con.execute("INSERT INTO sync_lauf (ausloeser, status, gestartet_am) VALUES ('manuell', 'erfolgreich', ?)",
                              (tag,)).lastrowid
            con.execute("INSERT INTO sync_lauf_konto (lauf_id, iban, konto_id, konto_neu, status) VALUES (?, ?, ?, 0,"
                        " 'erfolgreich')", (lid, IBAN, konto_id))
        SyncDienst(config)._saldo_abgleichen(con, lid, IBAN, konto_id,
                                             Umsatzliste(saldo=BankSaldo(IBAN, betrag, dt.date.fromisoformat(tag))))
    finally:
        con.close()


def test_fenster_fragt_nach_dem_zusammenfuehren(tmp_path, browser):
    with server(tmp_path) as (url, config), seite(browser, url, **DESKTOP) as page:
        _bank_meldet(config, 1, -16000, "2024-06-01")     # Buch: −210,00 € → Ausgleich +50,00 €
        _bank_meldet(config, 1, -19000, "2024-06-03")     # → Ausgleich −30,00 €
        page.goto(url + "/konten/1")
        bereit(page, "konto")
        d = tid(page, "ausgleich-dialog")
        expect(d).to_be_visible()
        expect(d).to_contain_text("Giro")
        expect(tid(page, "ausgleich-summe")).to_have_attribute("data-betrag", "2000")
        # „Später“ lässt alles stehen und fragt in dieser Sitzung nicht noch einmal
        tid(page, "ausgleich-spaeter").click()
        expect(d).to_have_count(0)
        assert len(page.request.get(url + "/api/saldoausgleich/paare").json()) == 1
        # nach dem Neuladen kommt die Frage wieder; Zusammenführen lässt eine Buchung über 20,00 € übrig
        page.reload()
        bereit(page, "konto")
        tid(page, "ausgleich-zusammenfuehren").click()
        expect(d).to_have_count(0)
        zeilen = page.locator('[data-testid="buchungsliste"] [role="row"][data-id]', has_text="Saldoausgleich Bank")
        expect(zeilen).to_have_count(1)
        expect(zeilen.locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", "2000")
        assert page.request.get(url + "/api/saldoausgleich/paare").json() == []
