"""Dublettenvorschläge: gleicher Betrag (Cent), gleiches Datum, gleiche Empfänger-Id."""

from __future__ import annotations


def _konto(c, name, art):
    r = c.post("/api/konten", json={"name": name, "art": art})
    assert r.status_code == 201, r.text
    return r.json()


def _empfaenger(c, name):
    r = c.post("/api/empfaenger", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _buchung(c, datum, splits, empf=None):
    body = {"datum": datum, "splits": splits}
    if empf is not None:
        body["empfaenger_id"] = empf
    r = c.post("/api/buchungen", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _paar(giro, kat, betrag):
    return [{"konto_id": giro, "betrag": betrag}, {"konto_id": kat, "betrag": -betrag}]


def _ids(v):
    return {v["buchung_id"], *v["kandidat_ids"]}


def test_vorschlag_betrag_datum_empfaenger(client):
    giro = _konto(client, "Giro", "girokonto")["id"]
    giro2 = _konto(client, "Zweites Giro", "girokonto")["id"]
    spar = _konto(client, "Spar", "sparkonto")["id"]
    kat = _konto(client, "Miete", "aufwand")["id"]
    vermieter = _empfaenger(client, "Vermieter")["id"]
    andere = _empfaenger(client, "Andere")["id"]

    a = _buchung(client, "2024-06-01", _paar(giro, kat, -10_000), vermieter)
    b = _buchung(client, "2024-06-01", _paar(giro2, kat, -10_000), vermieter)  # anderes Konto, gleiche Schlüssel
    # zwei Splits derselben Buchung: ein Betrag, keine zweite Buchung
    doppelt = _buchung(client, "2024-06-01", [
        {"konto_id": giro, "betrag": -4_000}, {"konto_id": giro, "betrag": -6_000},
        {"konto_id": kat, "betrag": 10_000}], vermieter)
    anderes_datum = _buchung(client, "2024-06-02", _paar(giro, kat, -10_000), vermieter)
    _buchung(client, "2024-06-01", _paar(giro, kat, -10_001), vermieter)  # anderer Betrag
    _buchung(client, "2024-06-01", _paar(giro, kat, 10_000), vermieter)  # anderes Vorzeichen
    _buchung(client, "2024-06-01", _paar(giro, kat, -10_000), andere)  # anderer Empfänger
    _buchung(client, "2024-06-01", _paar(giro, kat, -10_000))  # ohne Empfänger
    _buchung(client, "2024-06-01", _paar(giro, kat, -10_000))
    # Umbuchung: zwei Bestandskonten, kein vergleichbarer Zahlungsbetrag
    umbuchung = _buchung(client, "2024-06-01", [
        {"konto_id": giro, "betrag": -10_000}, {"konto_id": spar, "betrag": 10_000}], vermieter)

    liste = client.get("/api/dubletten?status=offen&vorschlaege=ja").json()
    vorschlaege = [v for v in liste if v.get("vorschlag")]
    assert len(vorschlaege) == 1
    assert vorschlaege[0]["grund"] == "gleich"
    assert vorschlaege[0]["id"] is None
    assert _ids(vorschlaege[0]) == {a["id"], b["id"], doppelt["id"]}
    assert umbuchung["id"] not in _ids(vorschlaege[0])
    assert anderes_datum["id"] not in _ids(vorschlaege[0])
    # D-169: ohne ausdrückliche Anfrage keine Vorschläge (bestehender Vertrag von GET /api/dubletten)
    assert not [v for v in client.get("/api/dubletten?status=offen").json() if v.get("vorschlag")]
    assert not [v for v in client.get("/api/dubletten").json() if v.get("vorschlag")]
    assert client.get("/api/dubletten?vorschlaege=vielleicht").status_code == 422
    assert all(type(x) is int for x in _ids(vorschlaege[0]))

    # Manuelles Paar ohne die drei Schlüssel; der Vorschlag bleibt daneben stehen.
    assert client.post("/api/dubletten", json={"buchung_ids": [a["id"]]}).status_code == 422
    fremd = client.post("/api/dubletten", json={"buchung_ids": [a["id"], anderes_datum["id"]]})
    assert fremd.status_code == 201
    assert set(_ids(fremd.json())) == {a["id"], anderes_datum["id"]}
    assert fremd.json().get("vorschlag") is not True
    offen = client.get("/api/dubletten?status=offen&vorschlaege=ja").json()
    assert [set(_ids(v)) for v in offen if v.get("vorschlag")] == [{a["id"], b["id"], doppelt["id"]}]
    assert [v["id"] for v in offen if not v.get("vorschlag")] == [fremd.json()["id"]]

    # „Keine Dublette“ für die Gruppe verdeckt den Vorschlag und ändert keine Buchung.
    gruppe = client.post("/api/dubletten", json={"buchung_ids": [a["id"], b["id"], doppelt["id"]]})
    assert gruppe.status_code == 201
    weg = client.post(f"/api/dubletten/{gruppe.json()['id']}/aufloesen",
                      json={"entscheidung": "keine_dublette"})
    assert weg.status_code == 200 and weg.json()["status"] == "keine_dublette"
    rest = client.get("/api/dubletten?status=offen&vorschlaege=ja").json()
    assert rest == [fremd.json()] or [v["id"] for v in rest] == [fremd.json()["id"]]
    assert client.get(f"/api/buchungen/{a['id']}").status_code == 200
    assert client.get(f"/api/buchungen/{doppelt['id']}").status_code == 200
