"""Eigene Tests zur Umstellung des Bankabrufs auf FinTS/camt (Feature fints-camt, D-190 bis D-193): camt-Version,
Bankzugang über REST, Übergang alter Bank-Kennungen. Nur synthetische Daten, keine Verbindungen nach außen."""

from __future__ import annotations

import datetime as dt
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from kontor import db
from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.fehler import BankFehler
from kontor.plugins.fints import CAMT_FORMATE, FintsBankPlugin, camt_eintraege

CAMT = "urn:iso:std:iso:20022:tech:xsd:camt.052.001."


def _fints(tmp_path, **kw) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", bank_plugin="fints", **kw)))


def _mock(tmp_path) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30))))


# ---------------------------------------------------------------- camt (D-190)

CAMT_02 = (f'<Document xmlns="{CAMT}02"><BkToCstmrAcctRpt><Rpt>'
           '<Ntry><Amt Ccy="EUR">12.34</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>'
           "<BookgDt><Dt>2024-06-03</Dt></BookgDt><ValDt><Dt>2024-06-04</Dt></ValDt>"
           "<NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Bäckerei Beispiel</Nm></Cdtr>"
           "<CdtrAcct><Id><IBAN>DE57000000000532013000</IBAN></Id></CdtrAcct></RltdPties>"
           "<RmtInf><Ustrd>Rechnung 1</Ustrd><Ustrd> Teil 2</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"
           '<Ntry><Amt Ccy="EUR">100.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>PDNG</Sts>'
           "<BookgDt><Dt>2024-06-05</Dt></BookgDt><AcctSvcrRef>REF-1</AcctSvcrRef>"
           "<NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Arbeitgeber</Nm></Dbtr></RltdPties></TxDtls></NtryDtls></Ntry>"
           "</Rpt></BkToCstmrAcctRpt></Document>").encode()


def test_camt_052_001_02_wird_gelesen():
    a, b = camt_eintraege(CAMT_02)
    assert (a.buchungstag, a.valuta, a.betrag) == (dt.date(2024, 6, 3), dt.date(2024, 6, 4), -1234)
    assert (a.gegenpartei_name, a.gegenpartei_iban, a.verwendungszweck) == (
        "Bäckerei Beispiel", "DE57000000000532013000", "Rechnung 1 Teil 2")
    assert not a.vormerkung and a.referenz is None
    assert (b.betrag, b.gegenpartei_name, b.vormerkung, b.referenz) == (10000, "Arbeitgeber", True, "REF-1")


def _dialog(formate: list[str] | None):
    """Dialog-Stellvertreter, dessen Bankparameter die angegebenen camt-Formate anbieten (None: kein HKCAZ)."""
    hicazs = None if formate is None else SimpleNamespace(parameter=SimpleNamespace(supported_camt_formats=formate))

    class Bpd:
        def find_segment_first(self, name):
            return hicazs if name == "HICAZS" else None

    class Client:
        bpd = Bpd()

        def _find_highest_supported_command(self, *_klassen):
            raise RuntimeError("kein HKKAZ in den Bankparametern")

    return SimpleNamespace(client=Client())


@pytest.mark.parametrize("angeboten, erwartet", [
    ([CAMT + "02"], CAMT + "02"),
    ([CAMT + "02", CAMT + "08"], CAMT + "08"),
    ([CAMT + "02", CAMT + "04", "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"], CAMT + "04"),
])
def test_camt_format_aus_bankparametern(angeboten, erwartet):
    from fints.models import SEPAAccount
    konto = SEPAAccount("DE57000000000532013000", "TESTDEFFXXX", "0532013000", None, "00000000")
    seg, camt = FintsBankPlugin()._segment(_dialog(angeboten), konto, dt.date(2024, 1, 1), dt.date(2024, 1, 31), None)
    assert camt and [str(x) for x in seg.supported_camt_messages.expected_type] == [erwartet]
    # Kontoverbindung international: nur IBAN und BIC (keine Kontonummer, kein Unterkonto, keine BLZ)
    k = seg.account
    assert (str(k.iban), str(k.bic)) == ("DE57000000000532013000", "TESTDEFFXXX")
    assert k.account_number is None and k.subaccount_number is None
    assert k.bank_identifier.bank_code is None and k.bank_identifier.country_identifier is None
    from fints.parser import FinTS3Serializer
    assert b"DE57000000000532013000:TESTDEFFXXX+" in FinTS3Serializer().serialize_message(seg)


def test_kein_stiller_rueckfall_auf_mt940():
    from fints.models import SEPAAccount
    konto = SEPAAccount("DE57000000000532013000", "TESTDEFFXXX", "0532013000", None, "00000000")
    with pytest.raises(BankFehler) as e:   # camt angeboten, aber keine lesbare Version: nie HKKAZ
        FintsBankPlugin()._segment(_dialog([CAMT + "01"]), konto, dt.date(2024, 1, 1), dt.date(2024, 1, 31), None)
    assert "camt" in e.value.meldung
    assert CAMT_FORMATE[0].endswith(".08") and CAMT_FORMATE[-1].endswith(".02")


# ---------------------------------------------------------------- Bankzugang (D-192)

ZUGANG = {"url": "https://fints.example.invalid/fints", "blz": "00000000", "benutzer": "KONTOR-TEST-01",
          "produkt_id": "SYNTHETISCH"}


def test_bankzugang_speichern_und_wieder_lesen(tmp_path):
    c = _fints(tmp_path)
    z = c.get("/api/bank/zugang").json()
    assert z["aenderbar"] and not z["vollstaendig"] and z["konten"] == [] and z["gespeichert"] == []
    z = c.put("/api/bank/zugang", json={**ZUGANG, "tan_verfahren": "913"}).json()
    assert z["vollstaendig"] and {k: z[k] for k in ZUGANG} == ZUGANG and z["tan_verfahren"] == "913"
    # neue App-Instanz auf derselben Datenbank: die Angaben sind dauerhaft
    z = _fints(tmp_path).get("/api/bank/zugang").json()
    assert {k: z[k] for k in ZUGANG} == ZUGANG and z["kunden_id"] is None
    # null entfernt den gespeicherten Wert
    assert c.put("/api/bank/zugang", json={"tan_verfahren": None}).json()["tan_verfahren"] is None


def test_bankzugang_vorbelegung_aus_konfiguration(tmp_path):
    c = _fints(tmp_path, fints_url=ZUGANG["url"], fints_blz="00000000", fints_benutzer="AUS-ENV",
               fints_produkt_id="SYNTHETISCH")
    z = c.get("/api/bank/zugang").json()
    assert z["vollstaendig"] and z["benutzer"] == "AUS-ENV" and z["gespeichert"] == []
    z = c.put("/api/bank/zugang", json={"benutzer": "AUS-UI"}).json()
    assert z["benutzer"] == "AUS-UI" and z["gespeichert"] == ["benutzer"] and z["blz"] == "00000000"
    assert c.put("/api/bank/zugang", json={"benutzer": ""}).json()["benutzer"] == "AUS-ENV"


def test_bankzugang_validierung_nennt_feld_nie_den_wert(tmp_path):
    c = _fints(tmp_path)
    r = c.put("/api/bank/zugang", json={"url": "http://bank.example.invalid/x", "blz": "GEHEIM12", "tan_verfahren": "9x"})
    assert r.status_code == 422
    assert sorted(d["ort"][-1] for d in r.json()["fehler"]["details"]) == ["blz", "tan_verfahren", "url"]
    assert "GEHEIM12" not in r.text and "bank.example" not in r.text
    assert c.get("/api/bank/zugang").json()["gespeichert"] == []
    assert c.put("/api/bank/zugang", json={"pin": "1234"}).status_code == 422   # die PIN ist kein Feld des Zugangs


def test_bankzugang_ohne_verbindung_und_ohne_pin_in_der_datenbank(tmp_path):
    c = _fints(tmp_path)
    assert c.post("/api/bank/zugang/konten/abrufen").json()["fehler"]["code"] == "bankzugang_unvollstaendig"
    c.put("/api/bank/zugang", json=ZUGANG)
    # ohne PIN wird keine Verbindung aufgebaut (example.invalid wäre ohnehin nicht erreichbar)
    for pfad in ("/api/bank/zugang/tan-verfahren", "/api/bank/zugang/konten/abrufen"):
        r = c.post(pfad)
        assert (r.status_code, r.json()["fehler"]["code"]) == (409, "bank_pin_fehlt")
    assert c.put("/api/sync/pin", json={"pin": "SYNTH-PIN-4711"}).status_code == 204
    c.put("/api/bank/zugang", json={"kunden_id": "K1"})
    con = sqlite3.connect(tmp_path / "k.sqlite3")
    inhalt = " ".join(f"{k}={w}" for k, w in con.execute("SELECT schluessel, wert FROM meta"))
    assert "SYNTH-PIN-4711" not in inhalt and "bank_fints_kunden_id=K1" in inhalt
    assert c.post("/api/bank/zugang/konten/abrufen", json={"vorgang": "x"}).status_code == 422
    r = c.post("/api/bank/zugang/konten/abrufen", json={"vorgang": "unbekannt", "tan": "123456"})
    assert (r.status_code, r.json()["fehler"]["code"]) == (409, "tan_nicht_offen")


def test_bankzugang_kontenauswahl(tmp_path):
    from kontor import bankzugang
    from kontor.plugins.bank import BankKonto
    c = _fints(tmp_path)
    c.put("/api/bank/zugang", json=ZUGANG)
    a, b = "DE57000000000532013000", "DE95000000000000006601"
    con = db.verbinde(tmp_path / "k.sqlite3")
    with db.transaktion(con):
        bankzugang.konten_uebernehmen(con, [BankKonto(b, "TESTDEFFXXX", "Giro", "girokonto", "Erika Mustermann"),
                                            BankKonto(a, None, "Tagesgeld", "sparkonto", "Erika Mustermann")])
    assert [k.iban for k in bankzugang.aktive_bankkonten(con)] == [a, b]
    z = c.put("/api/bank/zugang/konten", json={"ibans": [b]}).json()
    assert [(k["iban"], k["aktiv"]) for k in z["konten"]] == [(a, False), (b, True)]
    assert [k.iban for k in bankzugang.aktive_bankkonten(con)] == [b]
    assert c.put("/api/bank/zugang/konten", json={"ibans": ["DE02120300000000202051"]}).status_code == 422
    # ein erneuter Abruf behält die Auswahl; ein anderer Zugang (BLZ, Benutzer, URL) verwirft die Konten
    with db.transaktion(con):
        neu = bankzugang.konten_uebernehmen(con, [BankKonto(a, None, "Tagesgeld", "sparkonto", ""),
                                                  BankKonto(b, None, "Giro", "girokonto", "")])
    assert [k["aktiv"] for k in neu] == [False, True]
    assert c.put("/api/bank/zugang", json={"produkt_id": "ANDERE"}).json()["konten"] != []
    assert c.put("/api/bank/zugang", json={"benutzer": "ANDERER"}).json()["konten"] == []
    assert bankzugang.aktive_bankkonten(con) is None
    con.close()


def test_bankzugang_im_mock_modus_nicht_aenderbar(tmp_path):
    c = _mock(tmp_path)
    z = c.get("/api/bank/zugang").json()
    assert (z["plugin"], z["aenderbar"]) == ("mock", False)
    r = c.put("/api/bank/zugang", json=ZUGANG)
    assert (r.status_code, r.json()["fehler"]["code"]) == (409, "bankzugang_nicht_aenderbar")


# ---------------------------------------------------------------- Übergang alter Kennungen (D-193)


def _kennungen_altern(pfad) -> int:
    """Stellt den Zustand vor der Umstellung nach: Dieselben Buchungen tragen Kennungen, die die Bank so nicht mehr
    liefert (wie nach einem Abruf über AqBanking)."""
    con = sqlite3.connect(pfad)
    zeilen = con.execute("SELECT buchung_id, extern_id FROM buchung_extern WHERE extern_id LIKE 'bank:%'").fetchall()
    con.execute("DELETE FROM sync_kennung")
    for i, (bid, alt) in enumerate(zeilen):
        neu = ":".join(alt.split(":")[:2]) + f":h:{i:016x}:1"
        con.execute("UPDATE buchung_extern SET extern_id = ? WHERE buchung_id = ? AND extern_id = ?", (neu, bid, alt))
        con.execute("INSERT INTO sync_kennung (kennung) VALUES (?)", (neu,))
        con.execute("INSERT INTO sync_kennung_alt (kennung) VALUES (?)", (neu,))
    con.commit()
    con.close()
    return len(zeilen)


def test_uebergang_bucht_nichts_doppelt(tmp_path):
    c = _mock(tmp_path)
    zeitraum = {"von": "2024-01-01", "bis": "2024-06-30"}
    erster = c.post("/api/sync", json=zeitraum).json()
    neu = sum(k["buchungen_neu"] for k in erster["konten"])
    pfad = c.app.state.sync.pfad   # im Mock-Modus eine eigene Datenbank
    anzahl = sqlite3.connect(pfad).execute("SELECT count(*) FROM buchung").fetchone()[0]
    assert neu > 0 and _kennungen_altern(pfad) == neu
    zweiter = c.post("/api/sync", json=zeitraum).json()
    assert zweiter["status"] == "erfolgreich"
    assert sum(k["buchungen_neu"] for k in zweiter["konten"]) == 0
    assert sum(k["buchungen_zusammengefuehrt"] for k in zweiter["konten"]) == neu
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT count(*) FROM buchung").fetchone()[0] == anzahl
    # jede Buchung trägt jetzt alte und neue Kennung; der nächste Abruf erkennt alles an der Kennung
    assert con.execute("SELECT count(*) FROM buchung_extern WHERE extern_id LIKE 'bank:%'").fetchone()[0] == 2 * neu
    dritter = c.post("/api/sync", json=zeitraum).json()
    assert sum(k["buchungen_vorhanden"] for k in dritter["konten"]) == neu
    assert sum(k["buchungen_neu"] + k["buchungen_zusammengefuehrt"] for k in dritter["konten"]) == 0
    con.close()


def test_uebergang_gleiche_betraege_am_selben_tag(tmp_path):
    """Zwei gleiche Umsätze am selben Tag, vor der Umstellung war erst einer gebucht: genau einer kommt dazu."""
    from kontor.plugins.bank import BankUmsatz
    c = _mock(tmp_path)
    c.post("/api/sync", json={})
    sync = c.app.state.sync
    con = db.verbinde(sync.pfad)
    k = con.execute("SELECT iban, konto_id FROM sync_konto_zustand ORDER BY iban LIMIT 1").fetchone()
    iban, kid = k["iban"], k["konto_id"]
    tag = dt.date(2024, 6, 20)

    def umsatz(uid, name):
        return BankUmsatz(uid, iban, tag, tag, -4711, "EUR", name, None, "Übergangstest", False, False)

    lid = con.execute("SELECT max(id) FROM sync_lauf").fetchone()[0]
    zeile = {"iban": iban, "konto_id": kid}
    sync._konto_uebernehmen(con, lid, zeile, tag, tag, [umsatz("h:alt:1", "Laden A")])
    con.execute("INSERT INTO sync_kennung_alt (kennung) VALUES (?)", (f"bank:{iban}:h:alt:1",))
    con.commit()
    vorher = con.execute("SELECT count(*) FROM buchung").fetchone()[0]
    sync._konto_uebernehmen(con, lid, zeile, tag, tag, [umsatz("ref:N1", "Laden B"), umsatz("ref:N2", "Laden A")])
    assert con.execute("SELECT count(*) FROM buchung").fetchone()[0] == vorher + 1
    # zugeordnet wurde nach dem Empfängernamen: „Laden A“ gehört zur alten Buchung, „Laden B“ ist neu
    alt = con.execute("SELECT buchung_id FROM buchung_extern WHERE extern_id = ?", (f"bank:{iban}:h:alt:1",)).fetchone()[0]
    assert con.execute("SELECT buchung_id FROM buchung_extern WHERE extern_id = ?",
                       (f"bank:{iban}:ref:N2",)).fetchone()[0] == alt
    assert con.execute("SELECT buchung_id FROM buchung_extern WHERE extern_id = ?",
                       (f"bank:{iban}:ref:N1",)).fetchone()[0] != alt
    # liefert die Bank die alte Kennung weiter, ist ein gleicher neuer Umsatz eine eigene Buchung
    sync._konto_uebernehmen(con, lid, zeile, tag, tag, [umsatz("h:alt:1", "Laden A"), umsatz("ref:N3", "Laden A")])
    assert con.execute("SELECT count(*) FROM buchung").fetchone()[0] == vorher + 2
    con.close()


def test_alte_kennungen_werden_einmal_beim_ersten_start_vermerkt(tmp_path):
    c = _mock(tmp_path)
    c.post("/api/sync", json={})
    pfad = c.app.state.sync.pfad
    con = sqlite3.connect(pfad)
    n = con.execute("SELECT count(*) FROM buchung_extern WHERE extern_id LIKE 'bank:%'").fetchone()[0]
    assert n > 0 and con.execute("SELECT count(*) FROM sync_kennung_alt").fetchone()[0] == 0
    con.execute("DELETE FROM meta WHERE schluessel = 'bank_uebergang'")   # Datenbank aus einer früheren Fassung
    con.commit()
    db.schema_anlegen(pfad)
    assert con.execute("SELECT count(*) FROM sync_kennung_alt").fetchone()[0] == n
    con.execute("DELETE FROM sync_kennung_alt")
    con.commit()
    db.schema_anlegen(pfad)   # nur einmal
    assert con.execute("SELECT count(*) FROM sync_kennung_alt").fetchone()[0] == 0
    con.close()
