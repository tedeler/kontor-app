"""Eigene Tests zur Umstellung des Bankabrufs auf FinTS/camt (Feature fints-camt, D-197 bis D-200): camt-Version,
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


# ---------------------------------------------------------------- camt (D-197)

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


# ---------------------------------------------------------------- Bankzugang (D-199)

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


# ---------------------------------------------------------------- Übergang alter Kennungen (D-200)


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


# ---------------------------------------------------------------- Kontenliste (D-202)


def _konten(monkeypatch, sepa_konten, hiupd):
    from kontor.plugins import fints as modul
    antwort = SimpleNamespace(response_segments=lambda *_a: [SimpleNamespace(accounts=sepa_konten)],
                              find_segments=lambda *_a: [])
    monkeypatch.setattr(modul, "_codes", lambda *_a: [])
    plugin = FintsBankPlugin()
    monkeypatch.setattr(plugin, "_senden", lambda *_a: antwort)
    d = SimpleNamespace(client=SimpleNamespace(upd=SimpleNamespace(find_segments=lambda _n: hiupd)))
    return [k for k, _ in plugin._konten_im_dialog(d)]


def _sepa(iban, nummer):
    from fints.formals import KTZ1, BankIdentifier
    return KTZ1(is_sepa=True, iban=iban, bic="TESTDEFFXXX", account_number=nummer,
                bank_identifier=BankIdentifier(country_identifier="280", bank_code="00000000"))


def _upd(nummer, iban=None, art=None, waehrung="EUR", name="Produkt"):
    return SimpleNamespace(iban=iban, account_information=SimpleNamespace(account_number=nummer),
                           account_currency=waehrung, account_type=art, account_product_name=name,
                           name_account_owner_1="Erika Mustermann", name_account_owner_2=None)


def test_konten_ohne_iban_oder_kontoart_in_den_benutzerparametern(monkeypatch):
    a, b, c, e = ("DE57000000000532013000", "DE95000000000000006601", "DE68000000000000006602",
                  "DE41000000000000006603")
    sepa = [_sepa(a, "0532013000"), _sepa(b, "6601"), _sepa(c, "6602"), _sepa(e, "6603")]
    # Benutzerparameter ganz ohne Konten: alle SEPA-Konten als Girokonto
    assert [(k.iban, k.art, k.name) for k in _konten(monkeypatch, sepa, [])] == [
        (i, "girokonto", "") for i in sorted((a, b, c, e))]
    # ohne IBAN (Zuordnung über die Kontonummer) und ohne Kontoart; Depot und Fremdwährung bleiben draußen
    konten = _konten(monkeypatch, sepa, [_upd("532013000"), _upd("6601", art=10, name="Tagesgeld"),
                                         _upd("6602", art=30), _upd("6603", iban=e, art=1, waehrung="USD")])
    assert sorted((k.iban, k.art, k.name, k.bic, k.inhaber) for k in konten) == sorted([
        (a, "girokonto", "Produkt", "TESTDEFFXXX", "Erika Mustermann"),
        (b, "sparkonto", "Tagesgeld", "TESTDEFFXXX", "Erika Mustermann")])


# ---------------------------------------------------------------- Diagnoseprotokoll (D-203)

GEHEIM = {"pin": "PIN-GEHEIM-9431", "tan": "847261", "benutzer": "ZUGANG-55123377", "kunde": "KUNDE-88442211",
          "system": "SYSTEMID-7781234", "iban": "DE57000000000532013000", "nummer": "0532013000",
          "inhaber": "Erika Mustermann", "produkt": "Urlaubskasse Erika", "referenz": "AUFTRAG-REF-66120",
          "challenge": "Bitte TAN für Konto 0532013000 eingeben"}


def _nachrichten():
    """Eine ausgehende und eine eingehende Nachricht, die an allen denkbaren Stellen persönliche Daten tragen."""
    from fints.formals import KTI1, KTZ1, BankIdentifier, Response, SupportedMessageTypes
    from fints.message import FinTSCustomerMessage, FinTSInstituteMessage
    from fints.segments.accounts import HISPA1
    from fints.segments.auth import HITAN6, HKIDN2, HKTAN6
    from fints.segments.dialog import HIRMS2, HISYN4
    from fints.segments.statement import HKCAZ1
    blz = BankIdentifier(country_identifier="280", bank_code="00000000")
    aus = FinTSCustomerMessage()
    aus += HKIDN2(bank_identifier=blz, customer_id=GEHEIM["kunde"], system_id=GEHEIM["system"], system_id_status="1")
    aus += HKCAZ1(account=KTI1(iban=GEHEIM["iban"], bic="TESTDEFFXXX"), all_accounts=False,
                  date_start=dt.date(2024, 1, 1), date_end=dt.date(2024, 1, 31),
                  supported_camt_messages=SupportedMessageTypes([CAMT + "02"]))
    aus += HKTAN6(tan_process="2", task_reference=GEHEIM["referenz"], further_tan_follows=False)
    ein = FinTSInstituteMessage()
    ein += HIRMS2(responses=[
        Response(code="9010", reference_element="3", text=f"Konto {GEHEIM['nummer']} von {GEHEIM['benutzer']} "
                 f"({GEHEIM['iban']}) unbekannt", parameters=[GEHEIM["nummer"], GEHEIM["inhaber"]]),
        Response(code="3920", reference_element="3", text="Zugelassene Verfahren", parameters=["902", "913"])])
    ein += HISPA1(accounts=[KTZ1(is_sepa=True, iban=GEHEIM["iban"], bic="TESTDEFFXXX",
                                 account_number=GEHEIM["nummer"], bank_identifier=blz)])
    ein += HITAN6(tan_process="4", task_reference=GEHEIM["referenz"], challenge=GEHEIM["challenge"],
                  challenge_hhduc=b"\x00\x09image/png\x00\x04BILD")
    ein += HISYN4(system_id=GEHEIM["system"])
    return aus, ein


def test_diagnose_enthaelt_keine_persoenlichen_daten():
    from kontor.plugins.fints_diagnose import Diagnose
    d = Diagnose()
    aus, ein = _nachrichten()
    d.nachricht("→ Bank", aus)
    assert d.zeilen() == []                      # ausgeschaltet: nichts
    d.einschalten(True)
    d.geheim = (GEHEIM["benutzer"], GEHEIM["kunde"])
    d.nachricht("→ Bank", aus)
    d.nachricht("← Bank", ein)
    text = "\n".join(d.zeilen())
    for name, wert in GEHEIM.items():
        assert wert not in text, name
    assert "0532013" not in text and "Mustermann" not in text
    # das Nützliche steht drin
    for erwartet in ("HKIDN2 HKCAZ1 HKTAN6", "Kontoverbindung mit IBAN+BIC", "camt.052.001.02", "9010",
                     "Verfahren: 902,913", "HISPA 1 Kontoverbindungen", "Konto 1: SEPA ja", "Grafik/HHD: 17 Bytes",
                     "Kundensystem-ID erhalten: ja", "HKTAN Prozess 2"):
        assert erwartet in text, erwartet
    assert "(2 Parameter)" in text               # Parameter anderer Rückmeldungen nur als Anzahl


def test_diagnose_bereinigt_freitext():
    from kontor.plugins.fints_diagnose import MAX_TEXT, bereinigen
    t = bereinigen("Benutzer zugang-55123377: Konto 12345 / DE57000000000532013000 gesperrt\x07 seit 2024",
                   ("ZUGANG-55123377",))
    assert t == "Benutzer ‹entfernt›: Konto ‹Ziffern› / ‹IBAN› gesperrt  seit 2024"
    assert len(bereinigen("x" * 1000)) == MAX_TEXT


def test_diagnose_ueber_rest_schaltbar(tmp_path):
    c = _fints(tmp_path)
    assert c.get("/api/bank/zugang/diagnose").json() == {"aktiv": False, "zeilen": []}
    assert c.put("/api/bank/zugang/diagnose", json={"aktiv": True}).json()["aktiv"] is True
    c.put("/api/bank/zugang", json=ZUGANG)
    c.put("/api/sync/pin", json={"pin": "SYNTH-PIN-4711"})
    c.post("/api/bank/zugang/konten/abrufen")    # example.invalid: keine Verbindung, aber ein Protokoll
    zeilen = c.get("/api/bank/zugang/diagnose").json()["zeilen"]
    text = "\n".join(zeilen)
    assert "Kontenabruf" in text and "Verbindung fehlgeschlagen" in text
    assert "SYNTH-PIN-4711" not in text and ZUGANG["benutzer"] not in text and "example.invalid" not in text
    # die Einstellung übersteht einen Neustart, das Protokoll (Arbeitsspeicher) nicht
    neu = _fints(tmp_path)
    neu.put("/api/sync/pin", json={"pin": "SYNTH-PIN-4711"})
    neu.post("/api/bank/zugang/konten/abrufen")
    assert neu.get("/api/bank/zugang/diagnose").json()["aktiv"] is True
    assert c.put("/api/bank/zugang/diagnose", json={"aktiv": False}).json()["aktiv"] is False
    assert _mock(tmp_path).put("/api/bank/zugang/diagnose", json={"aktiv": True}).status_code == 409
