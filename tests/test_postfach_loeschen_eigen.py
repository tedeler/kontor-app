"""Entwicklungstests für das Feature „postfach-loeschen“ (D-244): Postfach löschen hinterlässt einen stimmigen
Bestand. Synthetische Daten; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor import db
from kontor.app import create_app
from kontor.config import KontorConfig

PF = "erika@example.invalid"
ANDERES = "max@example.invalid"
NR = "302-1234567-7654321"


@pytest.fixture
def umgebung(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 30),
                       planer_starten=False, mail_bestellnummer=True)
    c = TestClient(create_app(cfg))
    ids = [c.post("/api/mail/postfaecher", json={"adresse": a}).json()["id"] for a in (PF, ANDERES)]
    return c, cfg, ids


def sql(cfg, abfrage, *par):
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        with db.transaktion(con):
            return [tuple(r) for r in con.execute(abfrage, par)]
    finally:
        con.close()


def test_loeschen_raeumt_auf_und_laesst_den_rest_stehen(umgebung):
    c, cfg, (pid, anderes) = umgebung
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    b = c.post("/api/buchungen", json={"datum": "2024-03-03", "verwendungszweck": f"{NR} AMZN fiktiv", "splits": [
        {"konto_id": giro, "betrag": -999}, {"konto_id": kat, "betrag": 999}]}).json()["id"]
    for cf, nid in ((PF, "<a@x.invalid>"), (ANDERES, "<b@x.invalid>")):
        sql(cfg, "INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text)"
                 " VALUES (?, ?, '2024-03-01T10:00:00Z', 'versand@amazon.example.invalid', ?, 'Text')",
            cf, nid, f"Bestellt {NR}")
        sql(cfg, "INSERT INTO postfach_zustand (adresse_cf, anmeldung) VALUES (?, 'angemeldet')", cf)
    # Mail von Hand an die Buchung: Dokument und Vermerk entstehen
    spiegel_id = sql(cfg, "SELECT id FROM mail_nachricht WHERE adresse_cf = ?", PF)[0][0]
    assert c.post(f"/api/mail/nachrichten/{spiegel_id}/buchung", json={"buchung_id": b}).status_code == 201
    sql(cfg, "INSERT INTO bestellmail_nummer (spiegel_id, nummer) VALUES (?, ?)", spiegel_id, NR)
    for p in (pid, anderes):
        sql(cfg, "INSERT INTO benachrichtigung (art, schluessel, titel, text, link, erstellt_am)"
                 " VALUES ('mail_fehler', ?, 't', 't', ?, '2024-06-01T00:00:00Z')", f"mail_fehler:{p}:x",
            f"/mail/postfaecher/{p}")

    assert c.delete(f"/api/mail/postfaecher/{pid}").status_code == 204

    assert c.get(f"/api/mail/postfaecher/{pid}").status_code == 404
    assert sql(cfg, "SELECT adresse_cf FROM mail_nachricht") == [(ANDERES,)]
    assert sql(cfg, "SELECT adresse_cf FROM postfach_zustand") == [(ANDERES,)]
    assert sql(cfg, "SELECT link FROM benachrichtigung WHERE art = 'mail_fehler'") == [(f"/mail/postfaecher/{anderes}",)]
    assert sql(cfg, "SELECT count(*) FROM bestellmail_nummer WHERE spiegel_id = ?", spiegel_id) == [(0,)]
    # bleibt: Dokument an der Buchung und der Vermerk (kein doppeltes Anhängen nach dem Neuanlegen)
    assert len(c.get(f"/api/buchungen/{b}").json()["belege"]) == 1
    assert sql(cfg, "SELECT count(*) FROM bestellmail WHERE buchung_id = ?", b) == [(1,)]
    # Rückgängig stellt das Postfach wieder her (ohne Spiegel und Anmeldung)
    letzte = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert letzte["aktion"] == "postfach_loeschen"
    assert c.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [letzte["id"]]}).status_code == 200
    assert c.get(f"/api/mail/postfaecher/{pid}").json()["adresse"] == PF
    assert c.get(f"/api/mail/postfaecher/{pid}/status").json()["nachrichten"] == 0


def test_nicht_waehrend_eines_abrufs(umgebung):
    c, cfg, (pid, _) = umgebung
    dienst = c.app.state.sync.mail
    assert dienst._abruf.acquire(blocking=False)
    try:
        r = c.delete(f"/api/mail/postfaecher/{pid}")
        assert r.status_code == 409 and r.json()["fehler"]["code"] == "mail_abruf_laeuft"
    finally:
        dienst._abruf.release()
    assert c.get(f"/api/mail/postfaecher/{pid}").status_code == 200
    assert c.delete(f"/api/mail/postfaecher/{pid}").status_code == 204
    # die Sperre ist wieder frei: ein Abruf läuft
    assert c.post("/api/mail/abruf").status_code == 200


def test_unbekanntes_postfach(umgebung):
    c, _, _ = umgebung
    assert c.delete("/api/mail/postfaecher/999999").status_code == 404
    assert c.post("/api/mail/abruf").status_code == 200
