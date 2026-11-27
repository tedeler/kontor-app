"""Core-Test (D-290): Kategorie setzen, Status setzen, Bestätigen und Tags wirken im Kontoblatt sofort.

Das Verhalten prüft `tests/test_browser_aktionen_sofort.py` mit verzögertem Server. Hier ist ohne Browser gesichert,
dass die Aktionen den gemeinsamen Weg `sofort` nehmen und dass die REST-Schnittstelle tut, was das Blatt vorwegnimmt.
"""

from __future__ import annotations


def _methode(js, kopf):
    teil = js[js.index(kopf):]
    return teil[:teil.index("\n  }\n")]


def test_aktionen_nehmen_den_gemeinsamen_weg(auslieferung):
    js = auslieferung.get("/oeffentlich/app/konto.js").text
    sofort = _methode(js, "  sofort(ids, patch, ausfuehren, optionen) {")
    assert sofort.index("listeZeichnen()") < sofort.index("aktion("), "gezeichnet wird erst nach der Anfrage"
    assert "ohneNeuLaden" in sofort and "this.kette" in sofort
    for kopf in ("  vorschlag(e, ids, was) {", "  async kategorieSetzen(ids, kategorieId) {",
                 "  async statusSetzen(ids, status, ausloeser) {", "  async personMarkieren(ids, hinzu) {",
                 "  tagsDialog(ids, ausloeser) {"):
        assert "this.sofort(" in _methode(js, kopf), f"{kopf.strip()} wartet auf den Server"
    ui = auslieferung.get("/oeffentlich/app/ui.js").text
    assert "export function tagAuswahl(ids, ausloeser, tagsVon, sofort)" in ui


def _welt(c):
    def konto(name, art):
        r = c.post("/api/konten", json={"name": name, "art": art})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    giro, alt, ziel = konto("Giro S", "girokonto"), konto("Sonstiges S", "aufwand"), konto("Haushalt S", "aufwand")
    ids = []
    for i in (1, 2, 3):
        b = c.post("/api/buchungen", json={"datum": f"2024-05-0{i}", "verwendungszweck": f"Tankstelle {i}", "splits": [
            {"konto_id": giro, "betrag": -1000 * i}, {"konto_id": alt, "betrag": 1000 * i}]})
        assert b.status_code == 201, b.text
        ids.append(b.json()["id"])
    regel = c.post("/api/regeln", json={"name": "Tanken", "kategorie_id": ziel, "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Tankstelle"}]})
    assert regel.status_code == 201, regel.text
    r = c.post("/api/regeln/anwenden", json={"regel_ids": [regel.json()["id"]], "nur_unkategorisiert": False})
    assert r.status_code == 200, r.text
    return giro, alt, ziel, ids


def test_kategorie_setzen_erledigt_den_vorschlag_und_bestaetigt(mock_client):
    c = mock_client
    giro, alt, ziel, ids = _welt(c)
    vorher = c.get(f"/api/buchungen/{ids[0]}").json()
    assert vorher["vorschlag"]
    r = c.put(f"/api/buchungen/{ids[0]}/kategorie", json={"kategorie_id": alt, "konto_id": giro})
    assert r.status_code == 200, r.text
    b = c.get(f"/api/buchungen/{ids[0]}").json()
    erwartet = "bestaetigt" if vorher["status"] in ("importiert", "vorlaeufig") else vorher["status"]
    assert (b["vorschlag"], b["kategorie_id"], b["status"]) == (None, alt, erwartet)
    r = c.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": ids[1:], "kategorie_id": alt, "konto_id": giro})
    assert r.status_code == 200, r.text
    for i in ids[1:]:
        b = c.get(f"/api/buchungen/{i}").json()
        assert (b["vorschlag"], b["kategorie_id"]) == (None, alt)


def test_status_bestaetigt_erledigt_den_vorschlag_und_tags_aendern_nur_tags(mock_client):
    c = mock_client
    giro, alt, ziel, ids = _welt(c)
    vorher = c.get(f"/api/buchungen/{ids[0]}").json()
    if vorher["status"] != "bestaetigt":
        r = c.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [ids[0]], "status": "bestaetigt"})
        assert r.status_code == 200, r.text
        b = c.get(f"/api/buchungen/{ids[0]}").json()
        assert (b["status"], b["vorschlag"], b["kategorie_id"]) == ("bestaetigt", None, ziel)
    tag = c.post("/api/tags", json={"name": "B-Torsten"}).json()
    davor = c.get(f"/api/buchungen/{ids[1]}").json()
    r = c.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [ids[1]], "hinzufuegen": [tag["id"]], "entfernen": []})
    assert r.status_code == 200, r.text
    b = c.get(f"/api/buchungen/{ids[1]}").json()
    assert [t["name"] for t in b["tags"]] == ["B-Torsten"]
    assert (b["status"], b["vorschlag"], b["kategorie_id"]) == (davor["status"], davor["vorschlag"], davor["kategorie_id"])
