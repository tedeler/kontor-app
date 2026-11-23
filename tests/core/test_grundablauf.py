"""Core-Test des Grundablaufs: Konten anlegen, buchen, Salden, Rückgängig. Zugleich Muster für neue Core-Tests."""

from __future__ import annotations


def _konto(client, name: str, art: str) -> int:
    r = client.post("/api/konten", json={"name": name, "art": art})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _salden(client) -> dict[int, int]:
    return {k["konto_id"]: k["saldo"] for k in client.get("/api/kontenuebersicht").json()["konten"]}


def test_buchen_saldo_und_rueckgaengig(client):
    assert client.get("/api/status").status_code == 200
    giro, leb = _konto(client, "Giro", "girokonto"), _konto(client, "Lebensmittel", "aufwand")
    r = client.post("/api/buchungen", json={"datum": "2024-03-01", "splits": [
        {"konto_id": giro, "betrag": -1250}, {"konto_id": leb, "betrag": 1250}]})
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    salden = _salden(client)
    assert (salden[giro], salden[leb]) == (-1250, 1250)

    letzte = client.get("/api/aenderungen").json()["eintraege"][0]
    assert client.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    assert client.get(f"/api/buchungen/{bid}").status_code == 404
    assert _salden(client)[giro] == 0


def test_unausgeglichene_buchung_wird_abgelehnt(client):
    giro, leb = _konto(client, "Giro", "girokonto"), _konto(client, "Lebensmittel", "aufwand")
    r = client.post("/api/buchungen", json={"datum": "2024-03-01", "splits": [
        {"konto_id": giro, "betrag": -100}, {"konto_id": leb, "betrag": 90}]})
    assert r.status_code == 422, r.text
    assert client.get("/api/buchungen").json()["gesamt"] == 0
