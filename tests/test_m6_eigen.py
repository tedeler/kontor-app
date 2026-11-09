"""Eigene Tests zu Meilenstein 6 (ergänzend zu kontor-tests): Migration, ältere Sicherungen, Protokollschutz,
Abbildung von MT940/camt, Test-Benachrichtigung. Nur synthetische Daten, keine Verbindungen nach außen."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import logging
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from kontor import db, sicherung
from kontor.app import _AbfrageSchwaerzen, create_app
from kontor.config import KontorConfig
from kontor.plugins.fints import camt_eintraege, kennungen_vergeben, mt940_eintraege


def _mock(tmp_path, name="k", **kw) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / f"{name}.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30), **kw)))


def test_migration_von_schemaversion_6(tmp_path):
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    con.execute("DROP TRIGGER benachrichtigung_zustellung_neu")
    con.execute("DROP INDEX benachrichtigung_zustellung")
    for t in ("geheimnis", "postfach", "postfach_zustand", "mail_nachricht"):
        con.execute(f"DROP TABLE {t}")
    for spalte in ("zustellung", "zustellversuche", "zugestellt_am", "naechster_versuch"):
        con.execute(f"ALTER TABLE benachrichtigung DROP COLUMN {spalte}")
    con.execute("ALTER TABLE tan_anforderung DROP COLUMN erinnerung_nr")
    con.execute("INSERT INTO benachrichtigung (art, schluessel, titel, text, link, erstellt_am, gelesen)"
                " VALUES ('sync_fehler', 'sync_fehler:x', 'Alt', 'Vor M6 entstanden', NULL, '2024-01-01T00:00:00Z', 0)")
    con.execute("INSERT INTO konto (name, art) VALUES ('Giro', 'girokonto')")
    con.execute("UPDATE meta SET wert = '6' WHERE schluessel = 'schema_version'")
    con.commit()
    con.close()
    c = TestClient(create_app(KontorConfig(datenbank=pfad)))
    assert [k["name"] for k in c.get("/api/konten").json()] == ["Giro"]
    (b,) = c.get("/api/benachrichtigungen").json()
    assert (b["zustellung"], b["zustellversuche"], b["zugestellt_am"]) == ("keine", 0, None)
    assert c.get("/api/mail/postfaecher").json() == []
    assert c.get("/api/geheimnisse").json()["eintraege"] == []


def _als_version_2(roh: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        m = json.loads(z.read("manifest.json"))
        daten = z.read("kontor.sqlite")
    con = sqlite3.connect(":memory:")
    con.deserialize(daten)
    con.execute("DROP TABLE postfach")
    con.execute("DELETE FROM id_zaehler WHERE objekt = 'postfach'")
    con.commit()
    con.execute("VACUUM")
    daten = con.serialize()
    m.update(schemaversion=2, datenbank_sha256=hashlib.sha256(daten).hexdigest())
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr("kontor.sqlite", daten)
    return puffer.getvalue()


def test_sicherung_der_schemaversion_2_einspielbar_und_postfach_bleibt_erhalten(tmp_path):
    q = _mock(tmp_path, "q")
    q.post("/api/konten", json={"name": "Giro", "art": "girokonto"})
    alt = _als_version_2(q.get("/api/sicherung").content)
    z = _mock(tmp_path, "z")
    z.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"})
    r = z.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", alt, "application/zip")})
    assert r.status_code == 200, r.json()
    assert r.json()["unterschied"]["postfach"] == {"angelegt": 0, "geaendert": 0, "geloescht": 1}
    assert z.get("/api/mail/postfaecher").json() == []
    assert sicherung.SCHEMAVERSION == 3


def test_spiegel_bleibt_bei_gleicher_adresse(tmp_path):
    q = _mock(tmp_path, "q")
    q.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"})
    daten = q.get("/api/sicherung").content
    assert q.post("/api/mail/abruf").json()["postfaecher"][0]["status"] == "erfolgreich"
    vorher = q.get("/api/mail/nachrichten").json()["gesamt"]
    assert vorher > 0
    q.post("/api/konten", json={"name": "Giro", "art": "girokonto"})
    r = q.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", daten, "application/zip")})
    assert r.status_code == 200 and r.json()["geaendert"] is True
    assert q.get("/api/mail/nachrichten").json()["gesamt"] == vorher, "mail.md 6.5"


def test_zugriffsprotokoll_ohne_abfrageteil():
    r = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                          ("127.0.0.1:1", "GET", "/oauth2/rueckruf?state=SYNTH-S&code=SYNTH-C", "1.1", 200), None)
    assert _AbfrageSchwaerzen().filter(r)
    assert "SYNTH" not in r.getMessage() and "/oauth2/rueckruf?…" in r.getMessage()


def test_fints_logger_gibt_nichts_weiter():
    create_app  # noqa: B018 - Import genügt, das Plugin-Modul legt den Logger still
    import kontor.plugins.fints  # noqa: F401
    assert logging.getLogger("fints").propagate is False


def test_mt940_storno_und_buchungsjahr():
    text = ("\r\n:20:STARTUMS\r\n:25:00000000/1\r\n:28C:0\r\n:60F:C231229EUR0,00\r\n"
            ":61:2401020101D12,34NMSCNONREF\r\n:86:105?20EINKAUF ?21FIKTIV?32FIKTIV MARKT?31DE02000000000000000000\r\n"
            ":61:2312291229RC5,00NMSCNONREF\r\n:86:166?20STORNO\r\n"
            ":61:240103RD1,50NMSCNONREF\r\n:86:166?20RUECK\r\n-\r\n")
    a, b, c = mt940_eintraege(text)
    assert (a.buchungstag, a.valuta, a.betrag, a.verwendungszweck, a.gegenpartei_name) == (
        dt.date(2024, 1, 1), dt.date(2024, 1, 2), -1234, "EINKAUF FIKTIV", "FIKTIV MARKT")
    assert (b.betrag, b.storno, c.betrag, c.storno) == (-500, True, 150, True)
    u = kennungen_vergeben("DE02000000000000000000", [a, a])
    assert [x.umsatz_id.rsplit(":", 1)[1] for x in u] == ["1", "2"] and u[0].umsatz_id.startswith("h:")


def test_camt_vormerkung_und_referenz():
    doc = ('<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"><BkToCstmrAcctRpt><Rpt>'
           '<Ntry><Amt Ccy="EUR">10.5</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>PDNG</Cd></Sts>'
           '<BookgDt><Dt>2024-06-30</Dt></BookgDt><AcctSvcrRef> R1 </AcctSvcrRef><NtryDtls><TxDtls><RltdPties>'
           '<Cdtr><Pty><Nm>Fiktiv GmbH</Nm></Pty></Cdtr></RltdPties><RmtInf><Ustrd>A</Ustrd><Ustrd>B</Ustrd>'
           '</RmtInf></TxDtls></NtryDtls></Ntry>'
           '<Ntry><Amt Ccy="USD">1.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts></Ntry>'
           '</Rpt></BkToCstmrAcctRpt></Document>').encode()
    (e,) = camt_eintraege(doc)
    assert (e.betrag, e.vormerkung, e.referenz, e.gegenpartei_name, e.verwendungszweck) == (
        -1050, True, "R1", "Fiktiv GmbH", "AB")


def test_test_benachrichtigung(tmp_path):
    m = _mock(tmp_path, "m")
    assert m.post("/api/benachrichtigungen/test").json() == {"gesendet": True, "plugin": "mock"}
    assert m.get("/api/mock/zustellungen").json() == [], "nicht in der Liste der Benachrichtigungen"
    e = TestClient(create_app(KontorConfig(datenbank=tmp_path / "e.sqlite3")))
    assert e.post("/api/benachrichtigungen/test").status_code == 409
