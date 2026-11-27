"""Core-Tests zum Feature „laufende-summe“ (D-322): Spalte „Summe“ im Kontoblatt.

- ``GET /api/buchungen`` mit ``konto_id`` liefert zusätzlich ``salden``: je Eintrag (gleiche Reihenfolge wie
  ``eintraege``) die Summe der Splits auf der Kontenmenge der Liste (``konto_id``, mit ``unterkonten`` samt
  Unterkonten) über **alle** Buchungen bis einschließlich dieser – unabhängig von allen anderen Filtern, Seite und
  Sortierung. Gespeichertes Vorzeichen (die Anzeige dreht wie beim Betrag).
- Reihenfolge: nach Datum; innerhalb eines Tages wie die Liste bei Sortierung nach Datum (aufsteigend: ``id``
  aufsteigend; bei ``-datum`` von unten nach oben gelesen, also ``id`` absteigend), damit die Spalte in der nach Datum
  sortierten Liste von Zeile zu Zeile genau um den Betrag springt. Der Stand am Ende eines Tages hängt davon nicht ab.
- Ohne ``konto_id`` fehlt das Feld.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def welt(client):
    c = client

    def konto(name, art, eltern=None):
        r = c.post("/api/konten", json={"name": name, "art": art, "eltern_id": eltern})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    giro = konto("Giro", "girokonto")
    unter = konto("Giro Rücklage", "girokonto", giro)
    lm = konto("Lebensmittel", "aufwand")
    gehalt = konto("Gehalt", "ertrag")

    def buchen(datum, konto_id, betrag, gegen, zweck):
        r = c.post("/api/buchungen", json={"datum": datum, "verwendungszweck": zweck, "splits": [
            {"konto_id": konto_id, "betrag": betrag}, {"konto_id": gegen, "betrag": -betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    ids = [buchen("2026-01-01", giro, 300_000, gehalt, "Gehalt"),
           buchen("2026-01-05", giro, -4_000, lm, "Markt A"),
           buchen("2026-01-05", giro, -6_000, lm, "Markt B"),
           buchen("2026-01-03", unter, 10_000, gehalt, "Rücklage"),
           buchen("2026-01-09", giro, -1_500, lm, "Bäcker")]
    return c, {"giro": giro, "unter": unter, "lm": lm}, ids


def _liste(c, **p):
    r = c.get("/api/buchungen", params=p)
    assert r.status_code == 200, r.text
    return r.json()


def _salden(d):
    assert len(d["salden"]) == len(d["eintraege"])
    return {e["id"]: s for e, s in zip(d["eintraege"], d["salden"])}


def test_summe_aller_buchungen_bis_zu_dieser(welt):
    c, k, (g, a, b, r, bae) = welt
    d = _liste(c, konto_id=k["giro"], sortierung="datum")
    assert [e["id"] for e in d["eintraege"]] == [g, a, b, bae]
    assert d["salden"] == [300_000, 296_000, 290_000, 288_500]
    # absteigend nach Datum (Vorgabe des Kontoblatts): von oben nach unten springt die Summe um den Betrag der Zeile
    d = _liste(c, konto_id=k["giro"], sortierung="-datum")
    assert [e["id"] for e in d["eintraege"]] == [bae, a, b, g]          # Gleichstand: id aufsteigend
    assert d["salden"] == [288_500, 290_000, 294_000, 300_000]
    for i in range(len(d["salden"]) - 1):
        assert d["salden"][i] - d["eintraege"][i]["betrag"] == d["salden"][i + 1]
    # Kategorie: Summe der Splits der Kategorie
    assert _liste(c, konto_id=k["lm"], sortierung="datum")["salden"] == [4_000, 10_000, 11_500]


def test_unabhaengig_von_filtern_seite_und_sortierung(welt):
    c, k, (g, a, b, r, bae) = welt
    voll = _salden(_liste(c, konto_id=k["giro"], sortierung="datum"))
    for p in ({"verwendungszweck": "Markt B"}, {"von": "2026-01-05"}, {"betrag_max": -5_000},
              {"filter": "betrag >= 15"}, {"sortierung": "betrag"}, {"sortierung": "-empfaenger"},
              {"pro_seite": 1, "seite": 2, "sortierung": "datum"}):
        d = _liste(c, konto_id=k["giro"], **p)
        assert d["eintraege"], p
        assert _salden(d) == {i: voll[i] for i in _salden(d)}, p
    # mit Unterkonten: Kontenmenge der Liste einschließlich Unterkonto
    d = _liste(c, konto_id=k["giro"], unterkonten="true", sortierung="datum")
    assert [e["id"] for e in d["eintraege"]] == [g, r, a, b, bae]
    assert d["salden"] == [300_000, 310_000, 306_000, 300_000, 298_500]


def test_ohne_konto_kein_feld_und_leere_liste(welt):
    c, k, ids = welt
    assert "salden" not in _liste(c)
    d = _liste(c, konto_id=k["giro"], verwendungszweck="gibt es nicht")
    assert d["eintraege"] == [] and d["salden"] == []
