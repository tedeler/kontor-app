"""Eigene Tests zu Meilenstein 11 (ergänzend zu kontor-tests): Abbildung des Saldos aus FinTS (HISAL) und
AqBanking (Kontextdatei), Migration von Schemaversion 8. Ohne Netz; nur synthetische Daten (BLZ 00000000)."""

from __future__ import annotations

import datetime as dt
import decimal
import sqlite3

from fastapi.testclient import TestClient
from fints import formals
from fints.segments.saldo import HISAL5, HISAL7

from kontor import db
from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.plugins.aqbanking import saldo_aus_kontext
from kontor.plugins.bank import BankSaldo, Umsatzliste
from kontor.plugins.fints import _saldo_aus_hisal

IBAN = "DE02000000000000004711"
TAG = dt.date(2024, 6, 30)


def _hisal7(betrag: str, kennz: formals.CreditDebit2, waehrung: str = "EUR") -> HISAL7:
    bal = formals.Balance2(credit_debit=kennz, amount=formals.Amount1(amount=decimal.Decimal(betrag),
                                                                      currency=waehrung), date=TAG)
    return HISAL7(account_product="Giro", currency=waehrung, balance_booked=bal)


def test_hisal_haben_soll_waehrung_und_bruchteile():
    assert _saldo_aus_hisal(IBAN, _hisal7("1234.56", formals.CreditDebit2.CREDIT)) == BankSaldo(IBAN, 123456, TAG)
    assert _saldo_aus_hisal(IBAN, _hisal7("0.07", formals.CreditDebit2.DEBIT)) == BankSaldo(IBAN, -7, TAG)
    assert _saldo_aus_hisal(IBAN, _hisal7("0", formals.CreditDebit2.CREDIT)) == BankSaldo(IBAN, 0, TAG)
    assert _saldo_aus_hisal(IBAN, _hisal7("10.00", formals.CreditDebit2.CREDIT, "USD")) is None
    assert _saldo_aus_hisal(IBAN, _hisal7("1.005", formals.CreditDebit2.CREDIT)) is None, "keine Bruchteile von Cent"


def test_hisal_version_5():
    bal = formals.Balance1(credit_debit=formals.CreditDebit2.DEBIT, amount=decimal.Decimal("99.90"), currency="EUR",
                           date=TAG)
    h = HISAL5(account_product="Giro", currency="EUR", balance_booked=bal)
    assert _saldo_aus_hisal(IBAN, h) == BankSaldo(IBAN, -9990, TAG)


KONTEXT = """
accountInfoList {
  accountInfo {
    char iban="{iban}"
    balanceList {
      balance {
        char type="noted"
        char date="20240630"
        char value="999%2F1%3AEUR"
      }
      balance {
        char type="booked"
        char date="20240629"
        char value="-150%2F100%3AEUR"
      }
      balance {
        char type="booked"
        char date="20240630"
        char value="12345%2F100%3AEUR"
      }
    }
  }
}
"""


def test_aqbanking_saldo_aus_kontext():
    text = KONTEXT.replace("{iban}", IBAN)
    assert saldo_aus_kontext(text, IBAN) == BankSaldo(IBAN, 12345, TAG), "spätester Eintrag vom Typ booked"
    assert saldo_aus_kontext(text.replace('"booked"', '"noted"'), IBAN) is None, "noted zählt nicht"
    assert saldo_aus_kontext(text.replace("%3AEUR", "%3AUSD"), IBAN) is None
    assert saldo_aus_kontext(text, "DE68000000000000004712") is None, "anderes Konto"


def test_umsatzliste_wie_liste():
    u = Umsatzliste([1, 2], saldo=BankSaldo(IBAN, 1, TAG))
    assert u == [1, 2] and u.saldo.betrag == 1
    assert Umsatzliste().saldo is None


def test_migration_von_schemaversion_8(tmp_path):
    """Ältere Datenbank ohne sync_lauf_konto.saldo_abgleich: Spalte wird ergänzt, Läufe bleiben lesbar."""
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    con.execute("INSERT INTO konto (name, art) VALUES ('Alt', 'girokonto')")
    con.execute("ALTER TABLE sync_lauf_konto DROP COLUMN saldo_abgleich")
    con.execute("UPDATE meta SET wert = '8' WHERE schluessel = 'schema_version'")
    con.commit()
    con.close()
    client = TestClient(create_app(KontorConfig(datenbank=pfad)))
    assert [k["name"] for k in client.get("/api/konten").json()] == ["Alt"]
    con = sqlite3.connect(pfad)
    spalten = {r[1] for r in con.execute("PRAGMA table_info(sync_lauf_konto)")}
    assert "saldo_abgleich" in spalten
    assert con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()[0] == str(db.SCHEMA_VERSION)
    con.close()
