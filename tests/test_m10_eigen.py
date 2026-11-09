"""Eigene Tests zu Meilenstein 10 (ergänzend zu kontor-tests): Auswertung der AqBanking-Ausgabe, Kontextdatei,
Kontoliste, PIN-Datei. Ohne AqBanking, ohne Verbindungen; nur synthetische Daten (BLZ 00000000)."""

from __future__ import annotations

import datetime as dt

import pytest

from kontor.fehler import (BankFehler, BankKontoUnbekannt, BankPinFalsch, BankTanNichtUnterstuetzt,
                           BankVerbindungsFehler, BankZugangGesperrt)
from kontor.plugins.aqbanking import (benutzer_aus_liste, fehler_aus_ausgabe, konten_aus_liste, pin_datei,
                                      umsaetze_aus_kontext)

KOPF = "6:2026/11/09 12-00-00:aqhbci(4711):jobqueue_dispatch.c:  173: "
JOB = '6:2026/11/09 12-00-00:aqhbci(4711):job.c:  644: Changing status of job "JobGetTransactions" from "{a}" (4) to "{b}" (5)'


def _aus(*zeilen: str) -> str:
    return "\n".join(zeilen) + "\n"


def test_erfolg_nur_mit_status_answered():
    fehler_aus_ausgabe(0, _aus(KOPF + "Result: Warning (3076: SCA nicht notwendig)", JOB.format(a="sent", b="answered")))
    with pytest.raises(BankVerbindungsFehler):
        fehler_aus_ausgabe(0, _aus(JOB.format(a="enqueued", b="error")))
    with pytest.raises(BankVerbindungsFehler):
        fehler_aus_ausgabe(1, _aus(JOB.format(a="sent", b="answered")))
    with pytest.raises(BankVerbindungsFehler):
        fehler_aus_ausgabe(0, "")


@pytest.mark.parametrize("codes,klasse,rueckmeldung", [
    (["9800", "9931"], BankPinFalsch, None),
    (["9800", "3938"], BankZugangGesperrt, None),
    (["9210"], BankKontoUnbekannt, None),
    (["0030"], BankTanNichtUnterstuetzt, None),
    (["9050", "9380"], BankFehler, "9380"),
    (["9800"], BankFehler, "9800"),
])
def test_zuordnung_der_rueckmeldungen(codes, klasse, rueckmeldung):
    text = _aus(*(KOPF + f"Result: Error ({c}: synthetisch)" for c in codes), JOB.format(a="sent", b="answered"))
    with pytest.raises(BankFehler) as e:
        fehler_aus_ausgabe(0, text)
    assert type(e.value) is klasse
    assert e.value.details.get("rueckmeldung") == rueckmeldung
    assert "synthetisch" not in str(e.value)


def test_tan_ohne_eingabe_und_hexdump_ignoriert():
    text = _aus("  0000: 52 65 73 75 6c 74 Result: Error (9931: x)",
                "3:2026/11/09 12-00-00:gwen(4711):cgui.c:  474: No TAN input in non-interactive mode")
    with pytest.raises(BankTanNichtUnterstuetzt):
        fehler_aus_ausgabe(0, text)


KONTEXT = """accountInfoList {
  accountInfo {
    char iban="DE95000000000000006601"
    transactionList {
      transaction {
        char type="statement"
        char remoteName="B%C3%A4ckerei M%C3%BCller ", "%26 S%C3%B6hne"
        char remoteIban="de20 0000 0000 0000 0066 90"
        char date="20231229"
        char valutaDate="20240102"
        char value="-2390%2F100%3AEUR"
        char purpose="Kartenzahlung%0D%0A Jahresende"
      } #transaction
      transaction {
        char type="statement"
        char status="pending"
        char date="20231230"
        char value="-100%2F100%3AEUR"
      } #transaction
      transaction {
        char type="statement"
        char date="20231230"
        char value="-100%2F100%3AUSD"
      } #transaction
      transaction {
        char type="notedStatement"
        char date="20231230"
        char value="-100%2F100%3AEUR"
      } #transaction
      transaction {
        char type="statement"
        char valutaDate="20240103"
        char value="5%2F1"
        char remoteIban="DE00000000000000000000"
      } #transaction
    } #transactionList
  } #accountInfo
} #accountInfoList
"""


def test_kontext_abbildung():
    roh = umsaetze_aus_kontext(KONTEXT, "DE95000000000000006601")
    assert [(r.buchungstag, r.valuta, r.betrag, r.gegenpartei_name, r.gegenpartei_iban, r.verwendungszweck)
            for r in roh] == [
        (dt.date(2023, 12, 29), dt.date(2024, 1, 2), -2390, "Bäckerei Müller & Söhne", "DE20000000000000006690",
         "Kartenzahlung Jahresende"),
        (dt.date(2024, 1, 3), dt.date(2024, 1, 3), 500, None, None, ""),
    ]
    assert all(r.storno is False and r.vormerkung is False for r in roh)
    assert umsaetze_aus_kontext(KONTEXT, "DE68000000000000006602") == []


def test_kontext_unlesbar():
    with pytest.raises(ValueError):
        umsaetze_aus_kontext("accountInfo {\n char iban=\"DE95", "DE95000000000000006601")
    with pytest.raises(ValueError):
        umsaetze_aus_kontext(KONTEXT.replace("-2390%2F100", "-2391%2F1000"), "DE95000000000000006601")


def test_kontoliste():
    s, f = "\x1e", "\x1f"
    ausgabe = ("       \tBankcode\tAccountnumber\tBic\tIban\tUniqueId\tType\n"
               f"{s}DE68000000000000006602{f}{f}savings{f}Tagesgeld{f}Erika\n"
               f"{s}DE95000000000000006601{f}TESTDEFFXXX{f}bank{f}Giro{f}Erika\n"
               f"{s}DE14000000000000006604{f}{f}investment{f}Depot{f}Erika\n"
               f"{s}DE95000000000000006601{f}{f}checking{f}Doppelt{f}Max\n"
               f"{s}DE00000000000000000000{f}{f}bank{f}Ungültig{f}Erika\n"
               f"{s}DE41000000000000006603{f}{f}creditcard{f}{f}\n")
    konten = konten_aus_liste(ausgabe)
    assert [(k.iban, k.bic, k.name, k.art, k.inhaber, k.waehrung) for k, _ in konten] == [
        ("DE41000000000000006603", None, "", "kreditkonto", "", "EUR"),
        ("DE68000000000000006602", None, "Tagesgeld", "sparkonto", "Erika", "EUR"),
        ("DE95000000000000006601", "TESTDEFFXXX", "Giro", "girokonto", "Erika", "EUR"),
    ]


def test_benutzer_und_pin_datei():
    xml = ("<?xml version=\"1.0\"?>\n<users>\n  <user>\n    <UserId>KONTOR-TEST-01</UserId>\n"
           "    <BankCode>00000000</BankCode>\n  </user>\n  <user>\n    <UserId><![CDATA[B&2]]></UserId>\n"
           "    <BankCode>00000000</BankCode>\n  </user>\n</users>\n")
    benutzer = benutzer_aus_liste(xml)
    assert benutzer == [("00000000", "KONTOR-TEST-01"), ("00000000", "B&2")]
    assert pin_datei(benutzer, 'SYN"TH\\1') == (b'PIN_00000000_KONTOR-TEST-01 = "SYN\\"TH\\\\1"\n'
                                                b'PIN_00000000_B&2 = "SYN\\"TH\\\\1"\n')
