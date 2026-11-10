"""Eigene Tests zu Meilenstein 12 (ergänzend zu kontor-tests): POST /api/buchungen/mehrfach/aendern über viele
Buchungen (stückweise SQL), Rückgängig in einem Schritt, Auslieferung der neuen Oberflächenteile. Nur synthetische
Daten."""

from __future__ import annotations

PFAD = "/api/buchungen/mehrfach/aendern"


def _konten(client) -> tuple[int, int]:
    giro = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    leb = client.post("/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()["id"]
    return giro, leb


def _buchung(client, giro, leb, status="importiert") -> int:
    r = client.post("/api/buchungen", json={"datum": "2024-03-01", "status": status, "splits": [
        {"konto_id": giro, "betrag": -100}, {"konto_id": leb, "betrag": 100}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_viele_buchungen_eine_aenderung_und_rueckgaengig(client):
    giro, leb = _konten(client)
    ids = [_buchung(client, giro, leb) for _ in range(620)]          # mehr als ein Stück (500)
    vor = client.get("/api/aenderungen").json()
    r = client.post(PFAD, json={"buchung_ids": ids[::-1], "status": "bestaetigt", "verwendungszweck": "Sammel"})
    assert r.status_code == 200, r.text
    assert r.json() == {"geaendert": ids, "anzahl": len(ids)}
    alle = client.get("/api/buchungen", params={"pro_seite": 500}).json()["gesamt"]
    assert alle == len(ids)
    neu = [a for a in client.get("/api/aenderungen").json()["eintraege"]
           if a["id"] not in {x["id"] for x in vor["eintraege"]}]
    assert [a["aktion"] for a in neu] == ["mehrfach_aendern"]
    assert client.post(f"/api/aenderungen/{neu[0]['id']}/rueckgaengig").status_code == 200
    for bid in (ids[0], ids[-1]):
        b = client.get(f"/api/buchungen/{bid}").json()
        assert (b["status"], b["verwendungszweck"]) == ("importiert", "")


def test_nur_entsperren_ist_ungueltig(client):
    giro, leb = _konten(client)
    bid = _buchung(client, giro, leb)
    r = client.post(PFAD, json={"buchung_ids": [bid], "entsperren": True})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung"


def test_oberflaeche_kennt_die_neuen_elemente(client):
    js = client.get("/oeffentlich/app/konto.js")
    assert js.status_code == 200
    for testid in ("mehrfach-status", "mehrfach-bearbeiten", "km-status", "km-mehrfach", "status-auswahl",
                   "mehrfach-dialog", "mehrfach-entsperren"):
        assert testid in js.text
