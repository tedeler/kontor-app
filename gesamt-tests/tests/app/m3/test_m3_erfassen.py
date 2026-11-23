"""M3: Manuelle Buchungen über die Erfassungshilfe (buchhaltungspflege.md 3, T 14).

Splits werden im Test aus Art, Betrag und Konten unabhängig berechnet; manuell erfasste Buchungen
unterliegen denselben Invarianten wie importierte (Hypothesis).
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import KORREKTUR, UNKATEGORISIERT, erfassen, konto_id


@pytest.fixture
def k(api):
    return {
        "giro": api.konto("Giro"), "spar": api.konto("Spar", "sparkonto"), "kredit": api.konto("Karte", "kreditkonto"),
        "lm": api.konto("Lebensmittel", "aufwand"), "gehalt": api.konto("Gehalt", "ertrag"),
        "ek": api.konto("Anfang", "eigenkapital"), "tag": api.tag("Bar"),
    }


def _splits(b):
    return [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]]


@pytest.mark.kern
def test_ausgabe_einnahme_mit_kategorie(api, k):
    g, lm, gh = k["giro"]["id"], k["lm"]["id"], k["gehalt"]["id"]
    a = erfassen(api, art="ausgabe", datum="2024-03-01", konto_id=g, betrag=1234, kategorie_id=lm,
                 verwendungszweck="Markt", memo="bar", tag_ids=[k["tag"]["id"]])
    assert _splits(a) == [(g, -1234, "bar"), (lm, 1234, "bar")]
    assert (a["kategorie_id"], a["status"], a["extern_ids"], a["gegen_iban"], a["vorschlag"]) == (lm, "bestaetigt",
                                                                                                 [], None, None)
    assert (a["verwendungszweck"], [t["id"] for t in a["tags"]], a["ist_umbuchung"], a["abgestimmt"]) == (
        "Markt", [k["tag"]["id"]], False, False)
    e = erfassen(api, art="einnahme", datum="2024-03-28", konto_id=g, betrag=250000, kategorie_id=gh,
                 status="importiert")
    assert _splits(e) == [(g, 250000, ""), (gh, -250000, "")] and e["status"] == "importiert"
    assert api.buchung_lesen(a["id"]) == a
    assert api.salden()[g]["saldo"] == 250000 - 1234


@pytest.mark.kern
def test_ohne_kategorie_unkategorisiert(api, k):
    g = k["giro"]["id"]
    assert konto_id(api, UNKATEGORISIERT) is None
    a = erfassen(api, art="ausgabe", datum="2024-03-01", konto_id=g, betrag=500)
    unk = konto_id(api, UNKATEGORISIERT)
    assert unk is not None and _splits(a) == [(g, -500, ""), (unk, 500, "")]
    konto = api.get(f"/api/konten/{unk}", erwartet=200).daten
    assert (konto["name"], konto["art"], konto["eltern_id"], konto["iban"]) == ("Unkategorisiert", "eigenkapital",
                                                                                None, None)
    api.patch(f"/api/konten/{unk}", json={"name": "Offen"}, erwartet=200)
    b = erfassen(api, art="einnahme", datum="2024-03-02", konto_id=g, betrag=700, kategorie_id=None)
    assert _splits(b) == [(g, 700, ""), (unk, -700, "")], "über extern_id wiederverwendet, auch umbenannt"
    assert b["kategorie_id"] is None


@pytest.mark.kern
def test_umbuchung(api, k):
    g, s = k["giro"]["id"], k["spar"]["id"]
    u = erfassen(api, art="umbuchung", datum="2024-03-05", konto_id=g, gegenkonto_id=s, betrag=10000, memo="Rücklage")
    assert _splits(u) == [(g, -10000, "Rücklage"), (s, 10000, "Rücklage")]
    assert u["ist_umbuchung"] is True and u["kategorie_id"] is None
    vorher = {kid: v["saldo"] for kid, v in api.salden().items() if kid in (k["lm"]["id"], k["gehalt"]["id"])}
    assert vorher == {k["lm"]["id"]: 0, k["gehalt"]["id"]: 0}, "Umbuchung zählt weder als Einnahme noch als Ausgabe"


@pytest.mark.kern
def test_korrektur(api, k):
    g = k["giro"]["id"]
    a = erfassen(api, art="korrektur", datum="2024-03-31", konto_id=g, betrag=-37)
    kor = konto_id(api, KORREKTUR)
    assert kor is not None and _splits(a) == [(g, -37, ""), (kor, 37, "")]
    konto = api.get(f"/api/konten/{kor}", erwartet=200).daten
    assert (konto["name"], konto["art"]) == ("Korrekturen", "eigenkapital")
    b = erfassen(api, art="korrektur", datum="2024-03-31", konto_id=k["kredit"]["id"], betrag=500,
                 kategorie_id=k["gehalt"]["id"])
    assert _splits(b) == [(k["kredit"]["id"], 500, ""), (k["gehalt"]["id"], -500, "")]
    assert api.salden()[g]["saldo"] == -37


@pytest.mark.kern
def test_empfaenger_name(api, k):
    g = k["giro"]["id"]
    # ab M32 ohne Standardkategorie: ohne kategorie_id „Unkategorisiert“ ohne Vorschlag (sammel3.md 2.1, E-296)
    e = api.post("/api/empfaenger", json={"name": "Bäckerei Korn", "aliase": ["BAECKEREI KORN GMBH"]},
                 erwartet=201).daten
    a = erfassen(api, art="ausgabe", datum="2024-03-01", konto_id=g, betrag=300, empfaenger_name=" Bäckerei Korn ")
    b = erfassen(api, art="ausgabe", datum="2024-03-02", konto_id=g, betrag=301, empfaenger_name="baeckerei korn gmbh")
    assert a["empfaenger"]["id"] == b["empfaenger"]["id"] == e["id"]
    unk = konto_id(api, UNKATEGORISIERT)
    for x in (a, b):
        assert x["vorschlag"] is None
        assert unk in [s["konto_id"] for s in x["splits"]]
    c = erfassen(api, art="ausgabe", datum="2024-03-03", konto_id=g, betrag=302, empfaenger_name="Neuer Laden",
                 kategorie_id=k["lm"]["id"])
    assert c["vorschlag"] is None, "ausdrückliche Kategorie ist kein Vorschlag"
    neu = api.get(f"/api/empfaenger/{c['empfaenger']['id']}", erwartet=200).daten
    assert neu == {"id": neu["id"], "name": "Neuer Laden", "extern_id": None, "aliase": [], "standardkategorie_id": None}
    d = erfassen(api, art="ausgabe", datum="2024-03-04", konto_id=g, betrag=303, empfaenger_id=e["id"],
                 kategorie_id=k["gehalt"]["id"])
    assert d["kategorie_id"] == k["gehalt"]["id"] and d["empfaenger"]["id"] == e["id"]


@pytest.mark.kern
@pytest.mark.parametrize("fall,code", [
    ({"betrag": 0}, "validierung"), ({"betrag": -5}, "validierung"), ({"betrag": 1.5}, "validierung"),
    ({"betrag": "5"}, "validierung"), ({"art": "spende"}, "validierung"), ({"gegenkonto_id": "SPAR"}, "validierung"),
    ({"art": "umbuchung"}, "validierung"), ({"art": "umbuchung", "gegenkonto_id": "SPAR", "kategorie_id": "LM"},
                                            "validierung"),
    ({"art": "korrektur", "betrag": 0}, "validierung"), ({"empfaenger_id": "E", "empfaenger_name": "x"}, "validierung"),
    ({"empfaenger_name": "   "}, "validierung"), ({"unbekannt": 1}, "validierung"), ({"datum": "2024-02-30"}, "validierung"),
    ({"konto_id": 999999}, "referenz_unbekannt"), ({"empfaenger_id": 999999}, "referenz_unbekannt"),
    ({"tag_ids": [999999]}, "referenz_unbekannt"), ({"art": "umbuchung", "gegenkonto_id": 999999}, "referenz_unbekannt"),
    ({"konto_id": "LM"}, "konto_ungueltig"), ({"konto_id": "EK"}, "konto_ungueltig"),
    ({"art": "umbuchung", "gegenkonto_id": "GIRO"}, "konto_ungueltig"),
    ({"art": "umbuchung", "gegenkonto_id": "LM"}, "konto_ungueltig"),
    ({"kategorie_id": "SPAR"}, "kategorie_ungueltig"), ({"kategorie_id": "EK"}, "kategorie_ungueltig"),
    ({"kategorie_id": 999999}, "kategorie_ungueltig"),
], ids=lambda x: str(x) if isinstance(x, str) else "-".join(f"{a}={b}" for a, b in x.items()))
def test_fehler(api, k, fall, code):
    ref = {"GIRO": k["giro"]["id"], "SPAR": k["spar"]["id"], "LM": k["lm"]["id"], "EK": k["ek"]["id"],
           "E": api.empfaenger("Ein Empfänger")["id"]}
    body = {"art": "ausgabe", "datum": "2024-03-01", "konto_id": k["giro"]["id"], "betrag": 100}
    body.update({f: ref.get(v, v) if isinstance(v, str) and f not in ("empfaenger_name", "art", "datum") else v
                 for f, v in fall.items()})
    vorher = api.zustand()
    assert fehlercode(api.post("/api/buchungen/erfassen", json=body, erwartet=422)) == code
    assert api.zustand() == vorher


@pytest.mark.kern
@given(eintraege=st.lists(st.tuples(st.sampled_from(["ausgabe", "einnahme", "umbuchung", "korrektur"]),
                                    st.integers(1, 10 ** 9), st.booleans(), st.integers(0, 2), st.integers(0, 2)),
                          min_size=1, max_size=15))
def test_invarianten_wie_importierte(api_fabrik, eintraege):
    api = api_fabrik()
    bestand = [api.konto("Giro")["id"], api.konto("Spar", "sparkonto")["id"], api.konto("Karte", "kreditkonto")["id"]]
    kat = api.konto("Lebensmittel", "aufwand")["id"]
    modell = {b: 0 for b in bestand}
    for art, betrag, mit_kat, i, j in eintraege:
        body = {"art": art, "datum": "2024-04-01", "konto_id": bestand[i], "betrag": betrag}
        if art == "umbuchung":
            if i == j:
                continue
            body["gegenkonto_id"] = bestand[j]
            modell[bestand[j]] += betrag
            modell[bestand[i]] -= betrag
        else:
            if mit_kat:
                body["kategorie_id"] = kat
            if art == "korrektur" and j == 1:
                body["betrag"] = -betrag
            modell[bestand[i]] += {"ausgabe": -betrag, "einnahme": betrag, "korrektur": body["betrag"]}[art]
        b = erfassen(api, **body)
        assert sum(s["betrag"] for s in b["splits"]) == 0 and len(b["splits"]) == 2
        assert b["betrag"] == abs(body["betrag"]) and b["ist_umbuchung"] == (art == "umbuchung")
    s = api.uebersicht()
    assert s["summe_gesamt"] == 0
    for kid, wert in modell.items():
        assert next(x for x in s["konten"] if x["konto_id"] == kid)["saldo"] == wert
    # manuell erfasste Buchungen lassen sich wie alle anderen bearbeiten und löschen
    for b in api.alle_buchungen():
        api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    assert all(x["saldo"] == 0 for x in api.uebersicht()["konten"])
