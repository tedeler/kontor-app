"""Core-Test (D-289): Vorschlag annehmen und ablehnen wirken im Kontoblatt sofort.

Das Verhalten prüft `tests/test_browser_vorschlag_sofort.py` mit verzögertem Server. Hier ist ohne Browser gesichert,
dass die Bausteine ausgeliefert werden und dass die Antwort der REST-Schnittstelle dem entspricht, was das Blatt
vorwegnimmt.
"""

from __future__ import annotations


def _vorschlag(js):
    teil = js[js.index("  vorschlag(e, ids, was) {"):]
    return teil[:teil.index("\n  }\n")]


def test_blatt_nimmt_die_wirkung_vorweg_und_reiht_die_anfragen(client):
    js = client.get("/oeffentlich/app/konto.js").text
    teil = _vorschlag(js)
    assert "vorschlagVorweg" in teil, "die Zeile wird nicht vor der Anfrage geändert"
    assert teil.index("listeZeichnen()") < teil.index("aktion("), "gezeichnet wird erst nach der Anfrage"
    assert "vorschlagKette" in teil, "mehrere Entscheidungen laufen nicht nacheinander"
    assert "ohneNeuLaden" in teil, "zwischen eingereihten Entscheidungen wird neu geladen"


def test_vorweggenommene_wirkung_stimmt_mit_dem_server(mock_client):
    """Annehmen: Kategorie bleibt, Vorschlag weg, bestätigt. Ablehnen: vorherige Kategorie, Vorschlag weg, importiert."""
    c = mock_client

    def konto(name, art):
        r = c.post("/api/konten", json={"name": name, "art": art})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    giro, alt, ziel = konto("Giro V", "girokonto"), konto("Sonstiges V", "aufwand"), konto("Haushalt V", "aufwand")
    ids = []
    for i in (1, 2):
        b = c.post("/api/buchungen", json={"datum": f"2024-05-0{i}", "verwendungszweck": f"Tankstelle {i}", "splits": [
            {"konto_id": giro, "betrag": -1000 * i}, {"konto_id": alt, "betrag": 1000 * i}]})
        assert b.status_code == 201, b.text
        ids.append(b.json()["id"])
    regel = c.post("/api/regeln", json={"name": "Tanken", "kategorie_id": ziel, "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Tankstelle"}]})
    assert regel.status_code == 201, regel.text
    r = c.post("/api/regeln/anwenden", json={"regel_ids": [regel.json()["id"]], "nur_unkategorisiert": False})
    assert r.status_code == 200, r.text
    vorher = {i: c.get(f"/api/buchungen/{i}").json() for i in ids}
    assert all(v["vorschlag"] and v["kategorie_id"] == ziel for v in vorher.values()), vorher
    assert vorher[ids[1]]["vorschlag"]["vorher_konto_id"] == alt
    a = c.post(f"/api/buchungen/{ids[0]}/vorschlag", json={"aktion": "annehmen"}).json()
    erwartet = "bestaetigt" if vorher[ids[0]]["status"] in ("importiert", "vorlaeufig") else vorher[ids[0]]["status"]
    assert (a["vorschlag"], a["kategorie_id"], a["status"]) == (None, ziel, erwartet)
    b = c.post(f"/api/buchungen/{ids[1]}/vorschlag", json={"aktion": "ablehnen"}).json()
    erwartet = "importiert" if vorher[ids[1]]["status"] == "vorlaeufig" else vorher[ids[1]]["status"]
    assert (b["vorschlag"], b["kategorie_id"], b["status"]) == (None, alt, erwartet)
