"""Core-Tests zum Feature ausgleich-aufraeumen (D-280, kontostand.md 5): Ausgleichsbuchungen des Saldoabgleichs, die
sich innerhalb einer Woche ganz oder teilweise aufheben.

Die Ausgleichsbuchungen entstehen hier über die öffentliche Funktion des Abgleichs (`SyncDienst._saldo_abgleichen`
mit einem Banksaldo), ohne Bankabruf und ohne Netz."""

from __future__ import annotations

import datetime as dt

import pytest

from kontor import db
from kontor.plugins.bank import BankSaldo, Umsatzliste
from kontor.sync import SyncDienst

IBAN = "DE02000000000000000001"


@pytest.fixture
def bank(client, config):
    r = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"})
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    dienst = SyncDienst(config)

    def saldo(betrag: int, tag: str, konto: int = kid) -> dict:
        """Die Bank meldet am Stichtag diesen Kontostand; Ergebnis ist der Saldoabgleich des Laufs."""
        con = db.verbinde(config.aktive_datenbank)
        try:
            with db.transaktion(con):
                lid = con.execute("INSERT INTO sync_lauf (ausloeser, status, gestartet_am) VALUES ('manuell', 'laeuft', ?)",
                                  (tag,)).lastrowid
                con.execute("INSERT INTO sync_lauf_konto (lauf_id, iban, konto_id, konto_neu, status) VALUES (?, ?, ?, 0,"
                            " 'erfolgreich')", (lid, IBAN, konto))
            dienst._saldo_abgleichen(con, lid, IBAN, konto, Umsatzliste(saldo=BankSaldo(IBAN, betrag, dt.date.fromisoformat(tag))))
            import json
            return json.loads(con.execute("SELECT saldo_abgleich FROM sync_lauf_konto WHERE lauf_id = ?", (lid,)).fetchone()[0])
        finally:
            con.close()

    def ausgleiche() -> list[tuple[str, int]]:
        liste = client.get(f"/api/buchungen?konto_id={kid}&limit=500").json()["eintraege"]
        return sorted((b["datum"], b["betrag"]) for b in liste if b["verwendungszweck"] == "Saldoausgleich Bank")

    return client, kid, saldo, ausgleiche


def test_gegenlaeufiger_ausgleich_hebt_den_frueheren_auf(bank):
    client, kid, saldo, ausgleiche = bank
    erster = saldo(5000, "2026-11-10")
    assert erster["status"] == "ausgeglichen" and erster["buchung_id"]
    assert ausgleiche() == [("2026-11-10", 5000)]
    # einen Tag später meldet die Bank wieder den alten Stand: statt −50,00 € zu buchen, entfällt die erste
    zweiter = saldo(0, "2026-11-11")
    assert zweiter["status"] == "ausgeglichen" and zweiter["differenz"] == -5000
    assert zweiter["buchung_id"] is None and zweiter["aufgehoben_buchung_id"] == erster["buchung_id"]
    assert ausgleiche() == []
    assert client.get("/api/saldoausgleich/paare").json() == []
    # das Entfernen steht im Protokoll und lässt sich rückgängig machen
    letzte = client.get("/api/aenderungen?limit=1").json()["eintraege"][0]
    assert letzte["aktion"] == "sync_saldoausgleich"
    assert client.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    assert ausgleiche() == [("2026-11-10", 5000)]


def test_nach_der_wochenfrist_bleibt_beides_stehen(bank):
    client, kid, saldo, ausgleiche = bank
    saldo(5000, "2026-11-01")
    spaet = saldo(0, "2026-11-09")                       # acht Tage später
    assert spaet["buchung_id"] and "aufgehoben_buchung_id" not in spaet
    assert ausgleiche() == [("2026-11-01", 5000), ("2026-11-09", -5000)]
    assert client.get("/api/saldoausgleich/paare").json() == []


def test_unterschiedliche_betraege_werden_zum_zusammenfuehren_angeboten(bank):
    client, kid, saldo, ausgleiche = bank
    a = saldo(5000, "2026-11-10")["buchung_id"]
    b = saldo(2000, "2026-11-12")["buchung_id"]          # −30,00 €
    assert ausgleiche() == [("2026-11-10", 5000), ("2026-11-12", -3000)]
    (paar,) = client.get("/api/saldoausgleich/paare").json()
    assert paar["konto_id"] == kid and paar["konto_name"] == "Giro" and paar["summe"] == 2000
    assert [x["id"] for x in paar["buchungen"]] == [a, b]
    assert [x["betrag"] for x in paar["buchungen"]] == [5000, -3000]

    r = client.post("/api/saldoausgleich/paare/zusammenfuehren", json={"buchung_ids": [a, b]})
    assert r.status_code == 200, r.text
    assert r.json()["buchung_id"] == b and r.json()["summe"] == 2000
    assert ausgleiche() == [("2026-11-12", 2000)]        # eine Buchung mit dem Restbetrag, am späteren Tag
    assert client.get("/api/saldoausgleich/paare").json() == []
    # eine Änderung im Protokoll; Rückgängig stellt beide wieder her
    letzte = client.get("/api/aenderungen?limit=1").json()["eintraege"][0]
    assert letzte["aktion"] == "saldoausgleich_zusammenfuehren"
    assert client.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    assert ausgleiche() == [("2026-11-10", 5000), ("2026-11-12", -3000)]


def test_getrennt_lassen_fragt_nicht_wieder(bank):
    client, kid, saldo, ausgleiche = bank
    a = saldo(5000, "2026-11-10")["buchung_id"]
    b = saldo(2000, "2026-11-12")["buchung_id"]
    assert client.post("/api/saldoausgleich/paare/getrennt", json={"buchung_ids": [b, a]}).status_code == 204
    assert client.get("/api/saldoausgleich/paare").json() == []
    assert ausgleiche() == [("2026-11-10", 5000), ("2026-11-12", -3000)]


def test_von_hand_geaenderte_buchung_ist_kein_ausgleich_mehr(bank):
    client, kid, saldo, ausgleiche = bank
    a = saldo(5000, "2026-11-10")["buchung_id"]
    kat = client.post("/api/konten", json={"name": "Zinsen", "art": "ertrag"}).json()["id"]
    assert client.put(f"/api/buchungen/{a}/kategorie", json={"kategorie_id": kat}).status_code == 200
    zweiter = saldo(0, "2026-11-11")
    assert zweiter["buchung_id"] and "aufgehoben_buchung_id" not in zweiter     # die umgebuchte bleibt unberührt
    assert client.get("/api/saldoausgleich/paare").json() == []
    r = client.post("/api/saldoausgleich/paare/zusammenfuehren", json={"buchung_ids": [a, zweiter["buchung_id"]]})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "kein_ausgleichspaar"


def test_altbestand_wird_beim_start_einmalig_aufgeraeumt(bank, config):
    from fastapi.testclient import TestClient

    from kontor import ausgleich
    from kontor.app import create_app

    client, kid, saldo, ausgleiche = bank
    # Bestand aus der Zeit vor D-280: ein Paar, das sich aufhebt, und ein einzelner Ausgleich
    con = db.verbinde(config.aktive_datenbank)
    try:
        saldo(5000, "2026-10-01")
        with db.transaktion(con):
            con.execute("DELETE FROM meta WHERE schluessel = 'saldo_altbestand_aufgeraeumt'")
        from kontor import buch, pflege, protokoll
        with protokoll.protokolliert(con, "sync", "sync_saldoausgleich", "2026-10-02T08:00:00Z"):
            buch.buchung_einfuegen(con, "2026-10-02", None, "Saldoausgleich Bank", "importiert",
                                   [{"konto_id": kid, "betrag": -5000, "memo": ""},
                                    {"konto_id": pflege.korrektur_id(con), "betrag": 5000, "memo": ""}], (),
                                   [f"saldo:{IBAN}:2026-10-02"])
    finally:
        con.close()
    saldo(700, "2026-10-20")
    assert ausgleiche() == [("2026-10-01", 5000), ("2026-10-02", -5000), ("2026-10-20", 700)]

    neu = TestClient(create_app(config))                 # Neustart räumt auf
    liste = neu.get(f"/api/buchungen?konto_id={kid}&limit=500").json()["eintraege"]
    assert sorted((b["datum"], b["betrag"]) for b in liste) == [("2026-10-20", 700)]
    letzte = neu.get("/api/aenderungen?limit=1").json()["eintraege"][0]
    assert letzte["aktion"] == "saldoausgleich_aufraeumen"
    assert ausgleich.altbestand_aufraeumen(config.aktive_datenbank) == []       # nur einmal
