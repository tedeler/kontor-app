"""Core-Tests zum Feature „konto-typ-inhaber“ (D-312): Kontotyp änderbar, Kontoinhaber, Kreditkonten mit
umgedrehtem Vorzeichen in der Anzeige.

- ``art`` ist bei Bestandskonten über ``PATCH /api/konten/{id}`` änderbar (``girokonto``, ``sparkonto``,
  ``kreditkonto``). Andere Werte sind ungültig (422 ``validierung``); Kategorien und technische Konten können den Typ
  nicht wechseln (422 ``art_ungueltig``). Ein Konto, auf das ein Kredit verweist, bleibt Kreditkonto (409
  ``konto_in_verwendung``).
- ``inhaber`` = ``{vorname, nachname}`` bei Bestandskonten, beide Teile dürfen leer bleiben. Sind beide leer,
  fehlt das Feld in der Antwort (wie in der Protokollform). ``null`` entfernt den Inhaber.
- Gespeichert wird unverändert (Soll positiv): das umgedrehte Vorzeichen ist reine Anzeige (Kontoblatt, Konten),
  der Saldo der Finanzübersicht bleibt negativ.
- Protokoll (Rückgängig) und Sicherung (Schemaversion 12, Tabelle ``konto_inhaber``) erfassen beides; ältere
  Sicherungen ohne die Tabelle lassen sich weiter einspielen.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest



@pytest.fixture
def c(client):
    return client


def _konto(c, name, art, **mehr):
    r = c.post("/api/konten", json={"name": name, "art": art, **mehr})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------------------------- Kontotyp


def test_art_von_bestandskonten_aenderbar_und_nur_innerhalb_der_bestandskonten(c):
    # ein Client für alle Fälle (Zeitbudget der Core-Tests)
    for i, (von, nach) in enumerate([("girokonto", "kreditkonto"), ("kreditkonto", "sparkonto"),
                                     ("sparkonto", "girokonto")]):
        k = _konto(c, f"Karte {i}", von)
        r = c.patch(f"/api/konten/{k['id']}", json={"art": nach})
        assert r.status_code == 200, r.text
        assert r.json()["art"] == nach
        assert c.get(f"/api/konten/{k['id']}").json()["art"] == nach
    kat = _konto(c, "Lebensmittel", "aufwand")
    giro = _konto(c, "Giro", "girokonto")
    r = c.patch(f"/api/konten/{kat['id']}", json={"art": "girokonto"})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "art_ungueltig"
    for art in ("aufwand", "ertrag", "eigenkapital", "giro"):
        r = c.patch(f"/api/konten/{giro['id']}", json={"art": art})
        assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung", art
    assert c.get(f"/api/konten/{kat['id']}").json()["art"] == "aufwand"
    assert c.get(f"/api/konten/{giro['id']}").json()["art"] == "girokonto"
    # gespeicherte Beträge bleiben beim Typwechsel, die Finanzübersicht zählt Schulden negativ
    karte = _konto(c, "Kreditkarte", "girokonto")
    c.post("/api/buchungen", json={"datum": "2026-11-02", "splits": [{"konto_id": karte["id"], "betrag": -4_990},
                                                                     {"konto_id": kat["id"], "betrag": 4_990}]})
    assert c.patch(f"/api/konten/{karte['id']}", json={"art": "kreditkonto"}).status_code == 200
    liste = c.get("/api/buchungen", params={"konto_id": karte["id"]}).json()
    assert [b["betrag"] for b in liste["eintraege"]] == [-4_990]
    u = c.get("/api/kontenuebersicht").json()
    saldo = {k["konto_id"]: k["saldo_gesamt"] for k in u["konten"]}
    assert saldo[karte["id"]] == -4_990
    assert u["summe_bestand"] == -4_990


# ---------------------------------------------------------------------------------------------- Inhaber


def test_inhaber_anlegen_lesen_aendern_entfernen(c):
    k = _konto(c, "Giro", "girokonto", inhaber={"vorname": "  Erika ", "nachname": "Mustermann"})
    assert k["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
    assert c.get(f"/api/konten/{k['id']}").json()["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
    r = c.patch(f"/api/konten/{k['id']}", json={"inhaber": {"vorname": "", "nachname": "Muster"}})
    assert r.status_code == 200 and r.json()["inhaber"] == {"vorname": "", "nachname": "Muster"}
    r = c.patch(f"/api/konten/{k['id']}", json={"inhaber": None})
    assert r.status_code == 200 and "inhaber" not in r.json()
    r = c.patch(f"/api/konten/{k['id']}", json={"inhaber": {"vorname": " ", "nachname": ""}})
    assert r.status_code == 200 and "inhaber" not in r.json()
    assert all("inhaber" not in x for x in c.get("/api/konten").json())
    # teilweise angeben; andere Felder lassen ihn stehen, ein Typwechsel auch
    k = _konto(c, "Giro 2", "girokonto", inhaber={"nachname": "Mustermann"})
    assert k["inhaber"] == {"vorname": "", "nachname": "Mustermann"}
    r = c.patch(f"/api/konten/{k['id']}", json={"name": "Giro neu"})
    assert r.json()["inhaber"] == {"vorname": "", "nachname": "Mustermann"}
    r = c.patch(f"/api/konten/{k['id']}", json={"art": "kreditkonto"})
    assert r.json()["inhaber"] == {"vorname": "", "nachname": "Mustermann"}
    # Löschen nimmt den Inhaber mit
    assert c.delete(f"/api/konten/{k['id']}").status_code == 204
    assert "inhaber" not in _konto(c, "Giro neu", "girokonto")
    # ungültige Angaben (ein Client für alle Fälle, Zeitbudget)
    kat = _konto(c, "Lebensmittel X", "aufwand")
    r = c.patch(f"/api/konten/{kat['id']}", json={"inhaber": {"vorname": "Erika", "nachname": ""}})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "inhaber_ungueltig"
    r = c.post("/api/konten", json={"name": "X", "art": "ertrag", "inhaber": {"vorname": "A"}})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "inhaber_ungueltig"
    giro = _konto(c, "Giro X", "girokonto")
    for falsch in ({"vorname": "x" * 201}, {"vorname": 1}, {"titel": "Dr."}, "Erika"):
        r = c.patch(f"/api/konten/{giro['id']}", json={"inhaber": falsch})
        assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung", falsch
    # leerer Inhaber an einer Kategorie stört nicht
    assert c.patch(f"/api/konten/{kat['id']}", json={"inhaber": None}).status_code == 200


# ---------------------------------------------------------------------------------------------- Sicherung


def _einspielen(c, datei: bytes):
    return c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                  files={"datei": ("s.zip", datei, "application/zip")})


def test_sicherung_erfasst_typ_und_inhaber(c):
    k = _konto(c, "Karte", "girokonto", inhaber={"vorname": "Erika", "nachname": "Mustermann"})
    _konto(c, "Spar", "sparkonto")
    c.patch(f"/api/konten/{k['id']}", json={"art": "kreditkonto"})
    datei = c.get("/api/sicherung").content
    with zipfile.ZipFile(io.BytesIO(datei)) as z:
        assert json.loads(z.read("manifest.json"))["schemaversion"] == 12
    c.patch(f"/api/konten/{k['id']}", json={"art": "girokonto", "inhaber": None})
    r = _einspielen(c, datei)
    assert r.status_code == 200, r.text
    nach = c.get(f"/api/konten/{k['id']}").json()
    assert nach["art"] == "kreditkonto"
    assert nach["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
    # Probelauf derselben Datei: gleicher Inhalt
    r = c.post("/api/sicherung/einspielen", params={"trocken": "true"},
               files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 200, r.text
    assert r.json()["geaendert"] is False, r.json()


# ---------------------------------------------------------------------------------------------- Oberfläche


def test_oberflaeche_kennt_typ_inhaber_und_vorzeichen(auslieferung):
    ui = auslieferung.get("/oeffentlich/app/ui.js").text
    for tid in ("einstellungen-art", "einstellungen-inhaber-vorname", "einstellungen-inhaber-nachname"):
        assert f'"{tid}"' in ui, tid
    kern = auslieferung.get("/oeffentlich/app/kern.js").text
    assert "export function vorzeichen" in kern
