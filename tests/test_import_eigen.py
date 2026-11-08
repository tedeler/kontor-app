"""Ergänzende Import-Tests mit eigenen, synthetischen Kleinstdateien."""

from __future__ import annotations

import pytest

from kontor.importer.kmymoney import datum_aus_postdate, importiere_kmy, wert_in_cent

from .conftest import GIRO, kmy, transaktion


@pytest.mark.parametrize("text,cent", [("0", 0), ("-0", 0), ("12", 1200), ("-617/50", -1234), ("1/100", 1),
                                       ("10/1000", 1), ("999999999999/100", 999_999_999_999)])
def test_wert_in_cent(text, cent):
    assert wert_in_cent(text) == cent


@pytest.mark.parametrize("text", ["1/3", "1/0", "1.5", "+1", "", "1e3", "1000000000000/100", "1/1000"])
def test_wert_ungueltig(text):
    assert wert_in_cent(text) is None


def test_postdate():
    assert datum_aus_postdate("2024-02-29") == "2024-02-29"
    assert datum_aus_postdate("2024-02-29T10:00:00") == "2024-02-29"
    assert datum_aus_postdate("2023-02-29") is None
    assert datum_aus_postdate("2024-02-29 10:00") is None


def test_import_idempotent_und_ausgleich(config, client):
    roh = kmy(GIRO, transaktionen=transaktion("T1", "2024-01-02", ("A1", "-500/100"), ("A2", "500/100"))
              + transaktion("T2", "2024-01-03", ("A1", "-77/100")))
    e1 = importiere_kmy(config, roh, dateiname="klein.kmy")
    assert e1.erfolgreich and e1.buchungen_neu == 2 and e1.splits_neu == 4
    assert [w.code for w in e1.warnungen] == ["buchung_ausgeglichen"]
    e2 = importiere_kmy(config, roh)
    assert e2.buchungen_vorhanden == 2 and e2.buchungen_neu == 0 and e2.konten_vorhanden == 1 and e2.kategorien_vorhanden == 1
    giro = next(k for k in client.get("/api/konten").json() if k["extern_id"] == "kmy:A1")
    assert giro["iban"] == "DE89370400440532013000"
    u = client.get("/api/kontenuebersicht").json()
    assert u["summe_gesamt"] == 0 and u["summe_bestand"] == -577


def test_fehler_ohne_teilimport(config, client):
    roh = kmy(GIRO, transaktionen=transaktion("T1", "2024-01-02", ("A1", "-500/100"), ("A2", "500/100"))
              + transaktion("T2", "2024-01-03", ("A1", "-1/3"), ("A2", "1/3")))
    e = importiere_kmy(config, roh)
    assert not e.erfolgreich and e.fehler[0].code == "import_inhalt_ungueltig" and e.fehler[0].referenz == "T2"
    assert client.get("/api/konten").json() == []


def test_rest_import_fehlercode(client):
    r = client.post("/api/import/kmymoney", files={"datei": ("x.kmy", b"kein xml", "text/plain")})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "import_format_ungueltig"
    assert r.json()["fehler"]["details"]["erfolgreich"] is False


def test_dublette_wird_zusammengefuehrt(client):
    giro = client.post("/api/konten", json={"name": "Hand", "art": "girokonto",
                                           "iban": "DE89370400440532013000"}).json()
    kat = client.post("/api/konten", json={"name": "Diverses", "art": "aufwand"}).json()
    hand = client.post("/api/buchungen", json={"datum": "2024-01-02", "splits": [
        {"konto_id": giro["id"], "betrag": -500}, {"konto_id": kat["id"], "betrag": 500}]}).json()
    roh = kmy(GIRO, transaktionen=transaktion("T1", "2024-01-02", ("A1", "-500/100"), ("A2", "500/100")))
    r = client.post("/api/import/kmymoney", files={"datei": ("d.kmy", roh, "application/gzip")}).json()
    assert r["buchungen_zusammengefuehrt"] == 1 and r["konten_vorhanden"] == 1
    assert client.get(f"/api/buchungen/{hand['id']}").json()["extern_ids"] == ["kmy:T1"]
