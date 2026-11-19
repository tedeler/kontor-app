"""D-218: Kontonamen sind je Hierarchieebene eindeutig (ohne Groß-/Kleinschreibung)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kontor import db
from kontor.app import create_app
from kontor.importer.kmymoney import importiere_kmy

from .conftest import kmy, transaktion


def _konto(c, name, art="aufwand", eltern=None, status=201):
    r = c.post("/api/konten", json={"name": name, "art": art, "eltern_id": eltern})
    assert r.status_code == status, r.text
    return r.json()


def _namen(c):
    return sorted((k["name"], k["eltern_id"]) for k in c.get("/api/konten").json())


def test_anlegen_gleicher_name_auf_einer_ebene(client):
    auto = _konto(client, "Auto")
    f = _konto(client, " auto ", status=409)
    assert f["fehler"]["code"] == "konto_existiert" and auto["id"] in f["fehler"]["details"]["konto_ids"]
    # andere Ebene, andere Klasse: erlaubt
    _konto(client, "Auto", eltern=auto["id"])
    _konto(client, "Auto", art="ertrag")
    _konto(client, "Auto", art="girokonto")
    _konto(client, "AUTO", art="sparkonto", status=409)   # Bestandskonten bilden eine Klasse


def test_umbenennen_und_verschieben(client):
    a, b = _konto(client, "Auto"), _konto(client, "Haus")
    unter = _konto(client, "Versicherung", eltern=a["id"])
    andere = _konto(client, "Versicherung", eltern=b["id"])
    assert client.patch(f"/api/konten/{b['id']}", json={"name": "AUTO"}).status_code == 409
    assert client.patch(f"/api/konten/{andere['id']}", json={"eltern_id": a["id"]}).status_code == 409
    assert client.patch(f"/api/konten/{a['id']}", json={"name": "AUTO"}).status_code == 200   # eigener Name
    assert client.get(f"/api/konten/{unter['id']}").json()["eltern_id"] == a["id"]


def test_loeschen_laesst_unterkonten_nicht_kollidieren(client):
    a = _konto(client, "Auto")
    _konto(client, "Sprit")
    _konto(client, "sprit", eltern=a["id"])
    for trocken in (True, False):
        r = client.post(f"/api/konten/{a['id']}/loeschen",
                        json={"buchungen": "unkategorisiert", "konflikte": "behalten", "trocken": trocken})
        assert r.status_code == 409 and r.json()["fehler"]["code"] == "konto_existiert", r.text
    assert len(client.get("/api/konten").json()) == 3


def test_rueckgaengig_wird_abgelehnt(client):
    a = _konto(client, "Auto")
    assert client.delete(f"/api/konten/{a['id']}").status_code == 204
    loeschung = client.get("/api/aenderungen").json()["eintraege"][0]["id"]
    _konto(client, "auto")
    r = client.post(f"/api/aenderungen/{loeschung}/rueckgaengig")
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "konto_existiert", r.text


def _doppelte_einfuegen(config):
    """Altbestand einer früheren Version: gleichnamige Geschwister direkt in der Datenbank."""
    con = db.verbinde(config.aktive_datenbank)
    with db.transaktion(con):
        def k(name, art, eltern=None, iban=None):
            return con.execute("INSERT INTO konto (name, art, eltern_id, iban) VALUES (?, ?, ?, ?)",
                               (name, art, eltern, iban)).lastrowid
        giro = k("Giro", "girokonto", iban="DE57000000000532013000")
        giro2 = k("giro", "girokonto")
        a1, a2 = k("Auto", "aufwand"), k("AUTO", "aufwand")
        s1, s2 = k("Sprit", "aufwand", a1), k("Sprit", "aufwand", a2)
        for datum, kat in (("2026-01-02", s1), ("2026-01-03", s2), ("2026-01-04", a2)):
            b = con.execute("INSERT INTO buchung (datum, verwendungszweck, status) VALUES (?, '', 'bestaetigt')",
                            (datum,)).lastrowid
            con.executemany("INSERT INTO split (buchung_id, konto_id, betrag, position) VALUES (?, ?, ?, ?)",
                            [(b, giro, -500, 0), (b, kat, 500, 1)])
    con.close()
    return giro, giro2, a1, s1


def test_altbestand_wird_beim_start_bereinigt(config):
    create_app(config)
    giro, giro2, a1, s1 = _doppelte_einfuegen(config)
    c = TestClient(create_app(config))
    assert _namen(c) == [("Auto", None), ("Giro", None), ("Sprit", a1), ("giro (2)", None)]
    je_konto = {}
    for b in c.get("/api/buchungen", params={"pro_seite": 50}).json()["eintraege"]:
        for s in b["splits"]:
            je_konto[s["konto_id"]] = je_konto.get(s["konto_id"], 0) + s["betrag"]
    assert je_konto == {giro: -1500, s1: 1000, a1: 500}
    eintraege = c.get("/api/aenderungen").json()["eintraege"]
    assert len(eintraege) == 1 and eintraege[0]["beschreibung"].startswith("Gleichnamige Konten bereinigt")
    # zweiter Start: nichts mehr zu tun
    c = TestClient(create_app(config))
    assert len(c.get("/api/aenderungen").json()["eintraege"]) == 1


def test_import_fuehrt_gleichnamige_kategorien_zusammen(config):
    konten = ('<ACCOUNT id="A1" name="Giro" type="1" parentaccount="AStd::Asset" currency="EUR"/>'
              '<ACCOUNT id="A2" name="Essen" type="13" parentaccount="AStd::Expense" currency="EUR"/>'
              '<ACCOUNT id="A3" name="essen" type="13" parentaccount="AStd::Expense" currency="EUR"/>')
    datei = kmy(konten, transaktionen=transaktion("T1", "2026-01-02", ("A1", "-5/1"), ("A2", "5/1"))
                + transaktion("T2", "2026-01-03", ("A1", "-7/1"), ("A3", "7/1")))
    for _ in range(2):   # auch der erneute Import bleibt eindeutig
        erg = importiere_kmy(config, datei)
        assert erg.erfolgreich and [w.code for w in erg.warnungen] == ["konto_zusammengefasst"]
        c = TestClient(create_app(config))
        essen = [k for k in c.get("/api/konten").json() if k["name"].casefold() == "essen"]
        assert len(essen) == 1
        b = c.get("/api/buchungen", params={"konto_id": essen[0]["id"]}).json()
        assert b["gesamt"] == 2


def test_technisches_konto_uebernimmt_gleichnamiges(client):
    eigen = _konto(client, "unkategorisiert", art="eigenkapital")
    giro = _konto(client, "Giro", art="girokonto")
    aufwand = _konto(client, "Auto")
    r = client.post(f"/api/konten/{aufwand['id']}/loeschen",
                    json={"buchungen": "unkategorisiert", "konflikte": "behalten"})
    assert r.status_code == 200, r.text
    assert [k["id"] for k in client.get("/api/konten").json() if k["art"] == "eigenkapital"] == [eigen["id"]]
    assert giro
