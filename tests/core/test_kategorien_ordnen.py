"""Core-Tests zum Feature „kategorien-ordnen“ (D-326): Kategorien hierarchisch neu ordnen.

- ``POST /api/kategorien/verschieben`` mit ``{"konto_ids": [...], "eltern_id": <id> | null}`` hängt eine oder mehrere
  Kategorien unter dieselbe Oberkategorie (``null`` = oberste Ebene). Genau eine Änderung im Protokoll
  (``kategorien_verschieben``), mit einem Rückgängig vollständig zurückzunehmen. Ist eine markierte Kategorie
  Nachfahre einer anderen markierten, wandert sie mit ihr und wird nicht einzeln verschoben. Nichts zu tun → keine
  Änderung (``aenderung_id`` null).
- Fehler: Ziel ist eine der Kategorien oder ein Nachfahre (422 ``hierarchie_ungueltig``), andere Kontoklasse
  (422 ``hierarchie_ungueltig``), Bestandskonto als Quelle (422 ``hierarchie_ungueltig``), unbekannte ID
  (404/422), gleichnamige Geschwister (409 ``konto_existiert``). Bei einem Fehler ändert sich nichts.
- Die Oberfläche kennt Suche, „Zuletzt gewählt“, Ablegen zwischen Zeilen, Aufklappen beim Verweilen, Esc beim Ziehen
  und das Tastenkürzel ``v`` (geprüft an der Auslieferung; Verhalten in ``tests/test_browser_kategorien_ordnen.py``).
"""

from __future__ import annotations

import pytest


def _kat(c, name, art="aufwand", eltern=None):
    r = c.post("/api/konten", json={"name": name, "art": art, "eltern_id": eltern})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _eltern(c, kid):
    return c.get(f"/api/konten/{kid}").json()["eltern_id"]


def _letzte(c):
    return c.get("/api/aenderungen?limit=1").json()["eintraege"][0]


@pytest.fixture
def baum(client):
    k = {"wohnen": _kat(client, "Wohnen"), "freizeit": _kat(client, "Freizeit")}
    k["miete"] = _kat(client, "Miete", eltern=k["wohnen"])
    k["strom"] = _kat(client, "Strom", eltern=k["wohnen"])
    k["oeko"] = _kat(client, "Ökostrom", eltern=k["strom"])
    k["kino"] = _kat(client, "Kino")
    k["gehalt"] = _kat(client, "Gehalt", "ertrag")
    return client, k


def test_eine_kategorie_unterordnen(baum):
    c, k = baum
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["kino"]], "eltern_id": k["freizeit"]})
    assert r.status_code == 200, r.text
    assert r.json()["aenderung_id"] is not None
    assert [x["id"] for x in r.json()["verschoben"]] == [k["kino"]]
    assert _eltern(c, k["kino"]) == k["freizeit"]
    assert _letzte(c)["aktion"] == "kategorien_verschieben"


def test_mehrere_eine_aenderung_und_rueckgaengig(baum):
    c, k = baum
    vorher = c.get("/api/aenderungen?limit=1").json()["eintraege"][0]["id"]
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["miete"], k["kino"]], "eltern_id": k["freizeit"]})
    assert r.status_code == 200, r.text
    assert _eltern(c, k["miete"]) == k["freizeit"] and _eltern(c, k["kino"]) == k["freizeit"]
    neu = c.get("/api/aenderungen?limit=5").json()["eintraege"]
    assert [e["id"] for e in neu if e["id"] > vorher] == [r.json()["aenderung_id"]]
    assert c.post(f"/api/aenderungen/{r.json()['aenderung_id']}/rueckgaengig").status_code == 200
    assert _eltern(c, k["miete"]) == k["wohnen"] and _eltern(c, k["kino"]) is None


def test_nachfahre_wandert_mit(baum):
    c, k = baum
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["strom"], k["oeko"]], "eltern_id": k["freizeit"]})
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()["verschoben"]] == [k["strom"]]
    assert _eltern(c, k["strom"]) == k["freizeit"]
    assert _eltern(c, k["oeko"]) == k["strom"]


def test_zur_obersten_ebene(baum):
    c, k = baum
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["oeko"]], "eltern_id": None})
    assert r.status_code == 200, r.text
    assert _eltern(c, k["oeko"]) is None


def test_nichts_zu_tun_ohne_aenderung(baum):
    c, k = baum
    vorher = _letzte(c)["id"]
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["miete"]], "eltern_id": k["wohnen"]})
    assert r.status_code == 200, r.text
    assert r.json()["aenderung_id"] is None and r.json()["verschoben"] == []
    assert _letzte(c)["id"] == vorher


@pytest.mark.parametrize("fall", ["selbst", "nachfahre", "klasse", "bestand"])
def test_ungueltige_ziele_aendern_nichts(baum, fall):
    c, k = baum
    if fall == "bestand":
        giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
        body = {"konto_ids": [giro, k["kino"]], "eltern_id": k["freizeit"]}
    else:
        ziel = {"selbst": k["wohnen"], "nachfahre": k["oeko"], "klasse": k["gehalt"]}[fall]
        body = {"konto_ids": [k["kino"], k["wohnen"]], "eltern_id": ziel}
    vorher = _letzte(c)["id"]
    r = c.post("/api/kategorien/verschieben", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["fehler"]["code"] == "hierarchie_ungueltig"
    assert _eltern(c, k["kino"]) is None and _eltern(c, k["wohnen"]) is None
    assert _letzte(c)["id"] == vorher


def test_unbekannte_id(baum):
    c, k = baum
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["kino"], 999999], "eltern_id": None})
    assert r.status_code in (404, 422), r.text
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["kino"]], "eltern_id": 999999})
    assert r.status_code == 422, r.text
    assert _eltern(c, k["kino"]) is None


def test_gleichnamige_geschwister(baum):
    c, k = baum
    _kat(c, "Kino", eltern=k["freizeit"])
    r = c.post("/api/kategorien/verschieben", json={"konto_ids": [k["kino"]], "eltern_id": k["freizeit"]})
    assert r.status_code == 409, r.text
    assert _eltern(c, k["kino"]) is None


def test_koerper_wird_geprueft(baum):
    c, _ = baum
    for body in ({"eltern_id": None}, {"konto_ids": [], "eltern_id": None}, {"konto_ids": [1]},
                 {"konto_ids": [1], "eltern_id": None, "x": 1}):
        assert c.post("/api/kategorien/verschieben", json=body).status_code == 422, body


def test_protokoll_nennt_die_aktion():
    from kontor import protokoll
    assert protokoll.BESCHREIBUNG["kategorien_verschieben"] == "Kategorien verschoben"


# ------------------------------------------------------------------ Oberfläche (Auslieferung)
def _js(c, datei):
    return c.get(f"/oeffentlich/app/{datei}").text


def _funktion(js, kopf):
    teil = js[js.index(kopf):]
    return teil[:teil.index("\n}\n")]


def test_auswahl_mit_suche_und_zuletzt(auslieferung):
    teil = _funktion(_js(auslieferung, "ui.js"), "export function zielAuswahl(")
    assert '"ziel-suche"' in teil, "Suchfeld der Oberkategorie-Auswahl fehlt"
    assert '"ziel-zuletzt"' in teil, "Abschnitt „Zuletzt gewählt“ fehlt"
    for taste in ("ArrowDown", "ArrowUp", "Enter", "Escape"):
        assert f'"{taste}"' in teil, taste


def test_baum_ablegen_zwischen_zeilen_verweilen_esc(auslieferung):
    js = _js(auslieferung, "baum.js")
    assert "data-ablage-ort" in js or "ablageOrt" in js, "Ablegen zwischen zwei Zeilen fehlt"
    assert "700" in js, "Aufklappen nach Verweilen fehlt"
    teil = _funktion(js, "export function ziehbar(")
    assert '"Escape"' in teil, "Esc bricht das Ziehen nicht ab"
    assert "/api/kategorien/verschieben" in js


def test_tastenkuerzel_verschieben(auslieferung):
    js = _js(auslieferung, "baum.js")
    assert 'e.key === "v"' in js, "Kürzel v für „Verschieben…“ fehlt im Kategorienbaum"
    assert '"kategorien-status"' in _js(auslieferung, "kategorien.js"), "Statusmeldung (aria-live) fehlt"
