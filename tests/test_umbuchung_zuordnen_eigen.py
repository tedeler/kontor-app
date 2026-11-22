"""Sammelbranch sammel4 (D-240): unter „Kategorie“ ein Bestandskonto wählen – die Zuordnung wird zur Umbuchung."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor import db
from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.plugins.bank import BankUmsatz


def _konto(c, name, art, **kw):
    r = c.post("/api/konten", json={"name": name, "art": art, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _buchung(c, datum, konto, gegen, betrag):
    r = c.post("/api/buchungen", json={"datum": datum, "splits": [
        {"konto_id": konto, "betrag": betrag}, {"konto_id": gegen, "betrag": -betrag}]})
    assert r.status_code == 201, r.text
    return r.json()


def _setzen(c, bid, ziel, **kw):
    return c.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": ziel, **kw})


@pytest.fixture
def bestand(client):
    c = client
    return c, {"giro": _konto(c, "Giro", "girokonto"), "spar": _konto(c, "Tagesgeld", "sparkonto"),
               "bar": _konto(c, "Bargeld", "girokonto"), "kat": _konto(c, "Lebensmittel", "aufwand"),
               "kat2": _konto(c, "Sparen", "aufwand")}


def _konten(b):
    return sorted((s["konto_id"], s["betrag"]) for s in b["splits"])


def test_konto_als_ziel_macht_die_buchung_zur_umbuchung(bestand):
    c, k = bestand
    b = _buchung(c, "2024-06-03", k["giro"], k["kat"], -50_000)
    r = _setzen(c, b["id"], k["spar"])
    assert r.status_code == 200, r.text
    neu = r.json()
    assert neu["ist_umbuchung"] is True and neu["kategorie_id"] is None
    assert _konten(neu) == sorted([(k["giro"], -50_000), (k["spar"], 50_000)])
    # eine Änderung im Protokoll, und sie lässt sich zurücknehmen
    letzte = c.get("/api/aenderungen").json()["eintraege"][0]
    assert letzte["aktion"] == "kategorie_setzen"
    assert c.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    assert c.get(f"/api/buchungen/{b['id']}").json()["kategorie_id"] == k["kat"]


def test_umbuchung_zaehlt_nicht_als_ausgabe(bestand):
    c, k = bestand
    b = _buchung(c, "2024-06-03", k["giro"], k["kat"], -50_000)
    vorher = c.get("/api/berichte/monat?monat=2024-06").json()
    assert _setzen(c, b["id"], k["spar"]).status_code == 200
    nachher = c.get("/api/berichte/monat?monat=2024-06").json()
    assert nachher["ausgeschlossen"]["umbuchungen"] == vorher["ausgeschlossen"]["umbuchungen"] + 1


def test_ziel_zurueck_auf_kategorie_und_auf_anderes_konto(bestand):
    c, k = bestand
    b = _buchung(c, "2024-06-03", k["giro"], k["kat"], -50_000)
    assert _setzen(c, b["id"], k["spar"]).status_code == 200
    # keine Seite trägt einen Bankumsatz: ohne Angabe des Blatts ist nicht klar, welche Seite bleibt
    assert _setzen(c, b["id"], k["kat2"]).json()["fehler"]["code"] == "nicht_kategorisierbar"
    r = _setzen(c, b["id"], k["bar"], konto_id=k["giro"])
    assert r.status_code == 200, r.text
    assert _konten(r.json()) == sorted([(k["giro"], -50_000), (k["bar"], 50_000)])
    r = _setzen(c, b["id"], k["kat2"], konto_id=k["giro"])
    assert r.status_code == 200, r.text
    assert r.json()["kategorie_id"] == k["kat2"] and r.json()["ist_umbuchung"] is False


def test_fehlerfaelle(bestand):
    c, k = bestand
    b = _buchung(c, "2024-06-03", k["giro"], k["kat"], -50_000)
    assert _setzen(c, b["id"], k["giro"]).json()["fehler"]["code"] == "konto_ungueltig"   # dasselbe Konto
    eigen = c.post("/api/konten", json={"name": "Anfang", "art": "eigenkapital"}).json()["id"]
    assert _setzen(c, b["id"], eigen).json()["fehler"]["code"] == "kategorie_ungueltig"
    assert _setzen(c, b["id"], 999_999).json()["fehler"]["code"] == "kategorie_ungueltig"
    assert _setzen(c, b["id"], k["kat2"], gegenbuchung_id=b["id"]).json()["fehler"]["code"] == "keine_umbuchung"
    assert _setzen(c, b["id"], k["spar"], gegenbuchung_id=999).json()["fehler"]["code"] == "keine_umbuchung"
    split = c.post("/api/buchungen", json={"datum": "2024-06-03", "splits": [
        {"konto_id": k["giro"], "betrag": -300}, {"konto_id": k["kat"], "betrag": 100},
        {"konto_id": k["kat2"], "betrag": 200}]}).json()
    assert _setzen(c, split["id"], k["spar"]).json()["fehler"]["code"] == "nicht_kategorisierbar"
    assert c.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}).status_code == 200
    assert _setzen(c, b["id"], k["spar"]).json()["fehler"]["code"] == "buchung_gesperrt"
    assert c.get(f"/api/buchungen/{b['id']}/gegenbuchungen").status_code == 422


def test_mehrfach_auf_ein_konto(bestand):
    c, k = bestand
    a = _buchung(c, "2024-06-03", k["giro"], k["kat"], -10_000)
    b = _buchung(c, "2024-06-04", k["giro"], k["kat"], -20_000)
    r = c.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [a["id"], b["id"]], "kategorie_id": k["spar"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"geaendert": [a["id"], b["id"]], "anzahl": 2}
    assert all(c.get(f"/api/buchungen/{x['id']}").json()["ist_umbuchung"] for x in (a, b))
    assert len(c.get("/api/aenderungen").json()["eintraege"]) >= 1
    # Kategorie als Ziel wie bisher
    r = c.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [a["id"]], "kategorie_id": k["kat2"],
                                                          "konto_id": k["giro"]})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/buchungen/{a['id']}").json()["kategorie_id"] == k["kat2"]


# ------------------------------------------------------------------ mit Bankumsätzen auf beiden Seiten


class Bank:
    """Zwei Bankkonten des Mock-Modus; Umsätze werden wie von der Synchronisation übernommen."""

    def __init__(self, tmp_path):
        self.c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                                    mock_heute=dt.date(2024, 6, 30))))
        assert self.c.post("/api/sync", json={}).status_code in (200, 201, 202)
        self.sync = self.c.app.state.sync
        con = db.verbinde(self.sync.pfad)
        zeilen = con.execute("SELECT iban, konto_id FROM sync_konto_zustand WHERE konto_id IS NOT NULL"
                             " ORDER BY iban LIMIT 2").fetchall()
        assert len(zeilen) == 2
        self.a, self.b = ({"iban": z["iban"], "konto_id": z["konto_id"]} for z in zeilen)
        self.lid = con.execute("SELECT max(id) FROM sync_lauf").fetchone()[0]
        con.close()
        self.nr = 0

    def umsatz(self, konto, tag, betrag, gegen_iban=None, name="Eigener Name"):
        self.nr += 1
        u = BankUmsatz(f"t:{self.nr}", konto["iban"], tag, tag, betrag, "EUR", name, gegen_iban, "Übertrag", False,
                       False)
        con = db.verbinde(self.sync.pfad)
        vorher = {r[0] for r in con.execute("SELECT id FROM buchung")}
        self.sync._konto_uebernehmen(con, self.lid, konto, tag, tag, [u])
        con.commit()
        neu = {r[0] for r in con.execute("SELECT id FROM buchung")} - vorher
        con.close()
        return neu

    def anzahl(self, konto):
        return self.c.get(f"/api/buchungen?konto_id={konto['konto_id']}&limit=1").json()["gesamt"]


@pytest.fixture
def bank(tmp_path):
    return Bank(tmp_path)


def test_gegenseite_schon_da_wird_zusammengefuehrt(bank):
    c = bank.c
    tag = dt.date(2024, 6, 20)
    (x,) = bank.umsatz(bank.a, tag, -123_456)
    (y,) = bank.umsatz(bank.b, tag + dt.timedelta(days=1), 123_456)
    kand = c.get(f"/api/buchungen/{x}/gegenbuchungen?konto_id={bank.b['konto_id']}").json()["kandidaten"]
    assert [k["id"] for k in kand] == [y]
    r = _setzen(c, x, bank.b["konto_id"])
    assert r.status_code == 200, r.text
    neu = r.json()
    assert neu["ist_umbuchung"] is True
    assert _konten(neu) == sorted([(bank.a["konto_id"], -123_456), (bank.b["konto_id"], 123_456)])
    assert len(neu["extern_ids"]) == 2, "beide Bankkennungen hängen an der einen Buchung"
    assert c.get(f"/api/buchungen/{y}").status_code == 404
    letzte = c.get("/api/aenderungen").json()["eintraege"][0]
    assert c.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    assert c.get(f"/api/buchungen/{y}").status_code == 200
    assert c.get(f"/api/buchungen/{x}").json()["ist_umbuchung"] is False


def test_gegenseite_ausdruecklich_nicht_zusammenfuehren(bank):
    c = bank.c
    tag = dt.date(2024, 6, 20)
    (x,) = bank.umsatz(bank.a, tag, -123_456)
    (y,) = bank.umsatz(bank.b, tag, 123_456)
    r = _setzen(c, x, bank.b["konto_id"], gegenbuchung_id=None)
    assert r.status_code == 200, r.text
    assert c.get(f"/api/buchungen/{y}").status_code == 200


def test_mehrere_gegenseiten_fragen_nach(bank):
    c = bank.c
    tag = dt.date(2024, 6, 20)
    (x,) = bank.umsatz(bank.a, tag, -123_456)
    (y1,) = bank.umsatz(bank.b, tag, 123_456)
    (y2,) = bank.umsatz(bank.b, tag + dt.timedelta(days=2), 123_456)
    bank.umsatz(bank.b, tag + dt.timedelta(days=9), 123_456)          # außerhalb des Fensters
    r = _setzen(c, x, bank.b["konto_id"])
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "gegenbuchung_mehrdeutig"
    assert r.json()["fehler"]["details"]["kandidaten"] == [y1, y2]
    r = c.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [x], "kategorie_id": bank.b["konto_id"]})
    assert r.status_code == 409 and r.json()["fehler"]["details"]["buchung_ids"] == [x]
    r = _setzen(c, x, bank.b["konto_id"], gegenbuchung_id=y2)
    assert r.status_code == 200, r.text
    assert c.get(f"/api/buchungen/{y2}").status_code == 404 and c.get(f"/api/buchungen/{y1}").status_code == 200


def test_gegen_iban_eines_fremden_kontos_passt_nicht(bank):
    c = bank.c
    tag = dt.date(2024, 6, 20)
    (x,) = bank.umsatz(bank.a, tag, -123_456)
    (y,) = bank.umsatz(bank.b, tag, 123_456, gegen_iban="DE52000000000000000100")
    assert c.get(f"/api/buchungen/{x}/gegenbuchungen?konto_id={bank.b['konto_id']}").json()["kandidaten"] == []
    assert _setzen(c, x, bank.b["konto_id"]).status_code == 200
    assert c.get(f"/api/buchungen/{y}").status_code == 200


def test_gegenseite_kommt_spaeter_von_der_bank(bank):
    c = bank.c
    tag = dt.date(2024, 6, 20)
    (x,) = bank.umsatz(bank.a, tag, -123_456)
    assert _setzen(c, x, bank.b["konto_id"]).status_code == 200
    vorher = bank.anzahl(bank.b)
    # zwei Tage später, anderer Name: trotzdem dieselbe Umbuchung, keine zweite Buchung, kein Verdacht
    assert bank.umsatz(bank.b, tag + dt.timedelta(days=2), 123_456, name="Anders Lautend") == set()
    assert bank.anzahl(bank.b) == vorher
    b = c.get(f"/api/buchungen/{x}").json()
    assert len(b["extern_ids"]) == 2
    assert not [v for v in c.get("/api/dubletten?status=offen").json() if x in (v["buchung_id"], *v["kandidat_ids"])]
    # jetzt tragen beide Seiten einen Bankumsatz: die Zuordnung lässt sich nicht mehr umhängen
    kat = _konto(c, "Sonstiges Test", "aufwand")
    assert _setzen(c, x, kat, konto_id=bank.a["konto_id"]).json()["fehler"]["code"] == "nicht_kategorisierbar"
    # ein weiterer gleicher Umsatz ist eine neue Buchung
    assert len(bank.umsatz(bank.b, tag + dt.timedelta(days=2), 123_456)) == 1


def test_seite_mit_bankumsatz_bleibt_beim_umhaengen(bank):
    c = bank.c
    tag = dt.date(2024, 6, 20)
    (x,) = bank.umsatz(bank.a, tag, -123_456)
    assert _setzen(c, x, bank.b["konto_id"]).status_code == 200
    kat = _konto(c, "Sonstiges Test", "aufwand")
    # ohne Angabe des Blatts: die Seite ohne Bankumsatz (Konto b) wird ersetzt
    r = _setzen(c, x, kat)
    assert r.status_code == 200, r.text
    assert _konten(r.json()) == sorted([(bank.a["konto_id"], -123_456), (kat, 123_456)])
