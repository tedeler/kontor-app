"""Datenbankschema (nur ganze Cent) und eingebauter Mock-Datensatz."""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from kontor import db
from kontor.plugins.mock_bank import MockBankPlugin
from kontor.plugins.mock_mail import MockMailPlugin
from kontor.text import iban_gueltig


def test_schema_lehnt_gleitkomma_ab(tmp_path):
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = db.verbinde(pfad)
    con.execute("INSERT INTO konto (name, art) VALUES ('A', 'girokonto')")
    con.execute("INSERT INTO buchung (datum, status) VALUES ('2024-01-01', 'bestaetigt')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO split (buchung_id, position, konto_id, betrag) VALUES (1, 0, 1, 12.5)")
    spalten = {r["name"]: r["type"] for r in con.execute("PRAGMA table_info(split)")}
    assert spalten["betrag"] == "INTEGER"
    con.close()


def test_eingebauter_datensatz_fortlaufend():
    heute = dt.date(2025, 3, 15)
    p = MockBankPlugin(heute=heute)
    konten = p.konten()
    assert all(iban_gueltig(k.iban) and k.iban[4:12] == "00000000" for k in konten)
    giro = konten[0].iban
    frueh = p.umsaetze(giro, dt.date(2025, 1, 1), dt.date(2025, 12, 31))
    assert frueh and max(u.buchungstag for u in frueh) <= heute
    p.setze_heute(dt.date(2025, 6, 30))
    spaeter = p.umsaetze(giro, dt.date(2025, 1, 1), dt.date(2025, 12, 31))
    assert spaeter[:len(frueh)] == frueh and len(spaeter) > len(frueh)
    m = MockMailPlugin(heute=heute)
    assert len(m.postfaecher()) == 2
    assert m.nachrichten(m.postfaecher()[0], dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc))
