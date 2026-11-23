"""Allgemeine REST-Regeln aus openapi.yaml: Status, Fehlerformat, Validierung, Beträge.

Jede Antwort wird zusätzlich vom Testclient gegen openapi.yaml geprüft
(tests/hilfen/api.py), inklusive Header ``X-Kontor-Modus``.
"""

from __future__ import annotations

import json

import pytest

from tests.hilfen.api import fehlercode

MAX = 999_999_999_999


def test_status_echtmodus(api):
    d = api.get("/api/status", erwartet=200).daten
    assert d["modus"] == "echt" and d["mock"] is False
    assert d["hinweis"] is None and d["mock_szenario"] is None
    assert d["plugins"] == {"bank": {"name": "fints", "mock": False}, "mail": {"name": "imap", "mock": False}}
    assert d["version"].strip()


def test_unbekannter_pfad_404(api):
    r = api.get("/api/gibtsnicht", erwartet=404)
    assert fehlercode(r) == "nicht_gefunden"
    r = api.post("/api/konten/1/unsinn", json={}, erwartet=404)
    assert fehlercode(r) == "nicht_gefunden"


@pytest.mark.parametrize("methode,pfad", [
    ("DELETE", "/api/status"), ("PUT", "/api/konten"), ("DELETE", "/api/kontenuebersicht"),
    ("PATCH", "/api/importe"), ("GET", "/api/buchungen/mehrfach/kategorie"),
])
def test_falsche_methode_405(api, methode, pfad):
    r = api.anfrage(methode, pfad, erwartet=405)
    assert fehlercode(r) == "methode_nicht_erlaubt"


@pytest.mark.parametrize("pfad", ["/api/konten/4711", "/api/buchungen/4711", "/api/empfaenger/4711"])
def test_unbekannte_id_404(api, pfad):
    r = api.get(pfad, erwartet=404)
    assert fehlercode(r) == "nicht_gefunden"
    assert r.json()["fehler"]["meldung"].strip()


def test_unbekannte_id_404_bei_aenderungen(api):
    assert fehlercode(api.patch("/api/konten/4711", json={"name": "x"}, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.delete("/api/konten/4711", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.patch("/api/buchungen/4711", json={}, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.delete("/api/buchungen/4711", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.put("/api/buchungen/4711/kategorie", json={"kategorie_id": 1},
                              erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.put("/api/buchungen/4711/splits", json={"splits": []},
                              erwartet=(404, 422))) in ("nicht_gefunden", "validierung", "zu_wenige_splits")
    assert fehlercode(api.patch("/api/tags/4711", json={"name": "x"}, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.delete("/api/tags/4711", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.post("/api/dubletten/4711/aufloesen", json={"entscheidung": "keine_dublette"},
                               erwartet=404)) == "nicht_gefunden"


def _validierung(r) -> None:
    f = r.json()["fehler"]
    assert f["code"] == "validierung", f
    assert isinstance(f["details"], list) and f["details"], "details muss eine nicht leere Liste sein"
    for d in f["details"]:
        assert isinstance(d, dict) and set(d) >= {"ort", "meldung"}, d
        assert isinstance(d["ort"], list) and all(isinstance(x, (str, int)) for x in d["ort"]), d
        assert isinstance(d["meldung"], str)


def test_kaputtes_json_422(api):
    r = api.post("/api/konten", content=b'{"name": "Giro", "art": ', headers={"content-type": "application/json"},
                 erwartet=422)
    assert fehlercode(r) == "validierung"


@pytest.mark.parametrize("koerper", [
    {"name": "Giro"},
    {"art": "girokonto"},
    {"name": "Giro", "art": "bargeld"},
    {"name": "Giro", "art": "girokonto", "unbekannt": 1},
    {"name": "Giro", "art": "girokonto", "waehrung": "EUR"},
    {"name": "Giro", "art": "girokonto", "geschlossen": "ja"},
    {"name": "", "art": "girokonto"},
    {"name": "x" * 201, "art": "girokonto"},
    {"name": "Giro", "art": "girokonto", "eroeffnet_am": "01.02.2024"},
    {"name": "Giro", "art": "girokonto", "notiz": "n" * 10001},
], ids=["ohne_art", "ohne_name", "art_unbekannt", "feld_unbekannt", "waehrung_nur_lesbar",
        "bool_als_text", "name_leer", "name_zu_lang", "datum_format", "notiz_zu_lang"])
def test_konto_validierung(api, koerper):
    _validierung(api.post("/api/konten", json=koerper, erwartet=422))
    assert api.konten() == []


def test_koerper_kein_objekt(api):
    for koerper in ([], "Giro", 17, None):
        r = api.post("/api/konten", json=koerper, erwartet=422)
        assert fehlercode(r) == "validierung"


@pytest.mark.kern
@pytest.mark.parametrize("betrag", [12.0, 12.5, "1200", True, False, None, MAX + 1, -MAX - 1, 10**20],
                         ids=["float_ganz", "float", "text", "true", "false", "null", "max+1", "min-1", "riesig"])
def test_betrag_nur_ganze_cent(api, betrag):
    """Invariante 2 an der Schnittstelle: keine Gleitkommazahlen, keine Texte, Bereich (E-004)."""
    g = api.konto()
    a = api.konto("Lebensmittel", "aufwand")
    gegen = -betrag if isinstance(betrag, (int, float)) and not isinstance(betrag, bool) else 0
    r = api.post("/api/buchungen", json={"datum": "2024-01-01", "splits": [
        {"konto_id": g["id"], "betrag": betrag}, {"konto_id": a["id"], "betrag": gegen}]}, erwartet=422)
    assert fehlercode(r) == "validierung"
    assert api.alle_buchungen() == []


def test_betrag_grenzen_zulaessig(api):
    g = api.konto()
    a = api.konto("Lebensmittel", "aufwand")
    b = api.buchung("2024-01-01", [(g["id"], MAX), (a["id"], -MAX)])
    assert [s["betrag"] for s in b["splits"]] == [MAX, -MAX]
    assert api.salden()[g["id"]]["saldo"] == MAX


def test_betraege_in_json_sind_ganzzahlen(api):
    """Die Rohantwort enthält Beträge als JSON-Ganzzahlen (kein ``12.0``)."""
    g = api.konto()
    a = api.konto("Lebensmittel", "aufwand")
    b = api.buchung("2024-01-01", [(g["id"], -1234), (a["id"], 1234)])
    roh = api.get(f"/api/buchungen/{b['id']}", erwartet=200).text

    def pruefe(obj):
        if isinstance(obj, float):
            raise AssertionError(f"Gleitkommazahl in Antwort: {roh}")
        if isinstance(obj, dict):
            for v in obj.values():
                pruefe(v)
        if isinstance(obj, list):
            for v in obj:
                pruefe(v)
    pruefe(json.loads(roh))
    pruefe(api.get("/api/kontenuebersicht", erwartet=200).json())
    pruefe(api.get("/api/buchungen", erwartet=200).json())


@pytest.mark.parametrize("params", [
    {"stichtag": "2024-13-01"}, {"stichtag": "heute"},
])
def test_uebersicht_stichtag_ungueltig(api, params):
    assert fehlercode(api.get("/api/kontenuebersicht", params=params, erwartet=422)) == "validierung"


def test_header_auch_bei_fehlern(api):
    # Der Testclient prüft den Header bei jeder /api/-Antwort; hier ausdrücklich.
    for r in (api.get("/api/gibtsnicht"), api.delete("/api/status"), api.post("/api/konten", json={})):
        assert r.headers["x-kontor-modus"] == "echt"


def test_weboberflaeche_echtmodus(api):
    r = api.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0].strip() == "text/html"
    assert "mock-hinweis" not in r.text
