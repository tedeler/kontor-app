"""Core-Test (D-297): Filter „unbestätigt“ – rote und gelbe Buchungen, bei denen die Bestätigung noch fehlt."""

from __future__ import annotations

import re

import pytest


@pytest.fixture
def welt(client):
    def konto(name, art):
        r = client.post("/api/konten", json={"name": name, "art": art})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    giro, alt = konto("Giro", "girokonto"), konto("Sonstiges", "aufwand")

    def neu(status):
        r = client.post("/api/buchungen", json={"datum": "2024-03-01", "status": status, "splits": [
            {"konto_id": giro, "betrag": -1250}, {"konto_id": alt, "betrag": 1250}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    b = {s: neu(s) for s in ("importiert", "vorlaeufig", "bestaetigt")}
    b["abgeglichen"] = neu("bestaetigt")
    r = client.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [b["abgeglichen"]], "status": "abgeglichen"})
    assert r.status_code == 200, r.text
    return client, b


def _ids(client, ausdruck):
    r = client.get("/api/buchungen", params={"filter": ausdruck})
    assert r.status_code == 200, r.text
    return {b["id"] for b in r.json()["eintraege"]}


def test_unbestaetigt_trifft_rot_und_gelb(welt):
    client, b = welt
    offen = {b["importiert"], b["vorlaeufig"]}
    fertig = {b["bestaetigt"], b["abgeglichen"]}
    assert _ids(client, "unbestätigt") == offen
    assert _ids(client, "unbestaetigt") == offen
    assert _ids(client, "unbestätigt == True") == offen
    assert _ids(client, "not unbestätigt") == fertig
    assert _ids(client, 'unbestätigt and status == "vorlaeufig"') == {b["vorlaeufig"]}
    # dieselbe Menge wie über den Status, also genau die rot und gelb getönten Zeilen
    assert _ids(client, 'status == "importiert" or status == "vorlaeufig"') == offen


def test_feld_steht_in_der_sprache_aber_nicht_in_regeln(welt):
    client, _ = welt
    felder = {f["name"]: f for f in client.get("/api/ausdruck/sprache", params={"kontext": "filter"}).json()["felder"]}
    assert felder["unbestätigt"]["typ"] == "bool" and felder["unbestätigt"]["nur_filter"] is True
    assert "unbestätigt" not in {f["name"] for f in
                                client.get("/api/ausdruck/sprache", params={"kontext": "regel"}).json()["felder"]}
    r = client.post("/api/ausdruck/pruefen", json={"ausdruck": "unbestätigt", "kontext": "filter"}).json()
    assert r["gueltig"] and r["kanonisch"] == "unbestätigt"


def test_kontoblatt_hat_schalter_und_kuerzel(auslieferung):
    js = auslieferung.get("/oeffentlich/app/konto.js").text
    assert "filter-unbestaetigt" in js, "der Schalter in der Filterzeile fehlt"
    assert re.search(r'\["f", "o", "[^"]*Bestätigung fehlt', js), "das Kürzel f o fehlt"
