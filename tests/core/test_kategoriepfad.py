"""Core-Tests zum Fehler „Kategoriepfad im Baukasten“ (D-301).

Der Baukasten schrieb hierarchische Kategorien mit dem Anzeigetrenner „ › “ in den Ausdruck
(`kategorie == "Versicherungen › PKV"`); der Server kennt Pfade nur mit „:“ und meldete „gibt es nicht“.

- Der Server nimmt „›“ (mit oder ohne Leerzeichen) als gleichwertigen Trenner an; die kanonische Form schreibt „:“.
- Die Oberfläche schreibt Verweise im Ausdruck mit „:“ (`ausdruckPfad`), nicht mit dem Anzeigepfad.
"""

from __future__ import annotations

import re

import pytest


@pytest.fixture
def pkv(client):
    oben = client.post("/api/konten", json={"name": "Versicherungen", "art": "aufwand"}).json()["id"]
    r = client.post("/api/konten", json={"name": "PKV", "art": "aufwand", "eltern_id": oben})
    assert r.status_code == 201, r.text
    giro = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    unter = client.post("/api/konten", json={"name": "Unter", "art": "girokonto", "eltern_id": giro})
    assert unter.status_code == 201, unter.text
    return r.json()["id"]


def test_kategoriepfad_mit_beiden_trennern(client, pkv):
    # alle Fälle an einem Bestand (früher parametrisiert; Zeitbudget der Core-Tests, D-304)
    for pfad in ("Versicherungen:PKV", "Versicherungen › PKV", "Versicherungen›PKV", "versicherungen  ›  pkv", "PKV"):
        for kontext in ("filter", "regel"):
            r = client.post("/api/ausdruck/pruefen",
                            json={"ausdruck": f'kategorie == "{pfad}"', "kontext": kontext}).json()
            assert r["gueltig"], (pfad, kontext, r["fehler"])
            assert r["kanonisch"] == 'kategorie == "Versicherungen:PKV"', (pfad, kontext)


def test_kontopfad_mit_anzeigetrenner(client, pkv):
    r = client.post("/api/ausdruck/pruefen", json={"ausdruck": 'konto == "Giro › Unter"', "kontext": "filter"}).json()
    assert r["gueltig"], r["fehler"]
    assert r["kanonisch"] == 'konto == "Giro:Unter"'


def test_unbekannter_pfad_bleibt_ein_fehler(client, pkv):
    r = client.post("/api/ausdruck/pruefen", json={"ausdruck": 'kategorie == "Versicherungen › KFZ"',
                                                  "kontext": "filter"}).json()
    assert not r["gueltig"] and r["fehler"][0]["code"] == "referenz_unbekannt"


def test_regel_mit_anzeigepfad_speichern(client, pkv):
    r = client.post("/api/regeln", json={"name": "PKV", "kategorie_id": pkv,
                                         "ausdruck": '"Allianz" in empfänger and kategorie == "Versicherungen › PKV"'})
    assert r.status_code == 201, r.text
    assert 'kategorie == "Versicherungen:PKV"' in r.json()["ausdruck"]


def test_oberflaeche_schreibt_ausdruckspfade(auslieferung):
    kern = auslieferung.get("/oeffentlich/app/kern.js").text
    m = re.search(r"export function ausdruckPfad\(k\) \{.*?\n\}", kern, re.S)
    assert m and 'join(":")' in m.group(0), "ausdruckPfad fehlt oder trennt nicht mit „:“"
    editor = auslieferung.get("/oeffentlich/app/regeleditor.js").text
    # Werte der Auswahl für konto/kategorie und Rückweg aus dem Baum: Ausdruckspfad
    assert "[ausdruckPfad(konto), kontoPfad(konto)]" in editor
    assert ": ausdruckPfad(kontoNach(x.id))" in editor
    assert "[kontoPfad(konto), kontoPfad(konto)]" not in editor
    konto = auslieferung.get("/oeffentlich/app/konto.js").text
    assert "qText(kontoPfad(k))" not in konto and "qText(ausdruckPfad(k))" in konto
