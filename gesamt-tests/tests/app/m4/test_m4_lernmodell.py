"""M4: Lernmodell – Verfahren, Trainingsmenge, Schwelle, Korrekturen, Mindestgenauigkeit (lernmodell.md, K 7, T 8, T 21).

Jede Vorhersage wird gegen die unabhängige Umsetzung ``tests/hilfen/lern_orakel.py``
geprüft; die Trainingsbeispiele des Orakels stammen aus dem, was der Test
selbst angelegt hat, bzw. aus der Wahrheit des Generators – nie aus einer
Antwort der Anwendung.
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode
from tests.hilfen.lern_orakel import KEINE, Modell, bewerte, merkmale
from tests.hilfen.m3 import alle_aenderungen, bestand
from tests.hilfen.m4 import GNC, M4, Buch, import_gnc, lade, vorhersagen
from tests.hilfen.pfade import KMY


def _anfrage(name, zweck, betrag) -> dict:
    return {"empfaenger": name, "verwendungszweck": zweck, "betrag": betrag}


def _gleich(ist: dict, soll) -> None:
    assert ist == soll.als_json(), f"Vorhersage {ist} statt {soll.als_json()}"


@pytest.mark.kern
def test_ohne_trainingsdaten_keine_kategorie(api):
    """T 8: Ohne Trainingsdaten wird keine Kategorie geraten."""
    assert api.get("/api/lernmodell", erwartet=200).daten == {
        "trainingsbuchungen": 0, "kategorien": 0, "merkmale": 0, "automatisch": False, "schwelle_promille": 700}
    (v,) = vorhersagen(api, [_anfrage("Supermarkt", "Einkauf", -1234)])
    assert v == {"kategorie_id": None, "sicherheit": None, "kandidaten": []}
    b = Buch(api)
    b.einfach("Supermarkt", "Einkauf", -1234, None)  # Gegenkonto Eigenkapital: kein Trainingsbeispiel
    assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] == 0
    (v,) = vorhersagen(api, [_anfrage("Supermarkt", "Einkauf", -1234)])
    assert v["kategorie_id"] is None and v["kandidaten"] == []


@pytest.mark.kern
def test_einfaches_beispiel_exakt(api):
    b = Buch(api)
    for i in range(4):
        b.einfach("Supermarkt Frischekorb", f"Einkauf Filiale {i}", -1500 - i, "Lebensmittel")
    b.einfach("Café Bohne", "Kartenzahlung Café", -340, "Café")
    b.einfach("Arbeitgeber", "LOHN/GEHALT 03/2024", 300000, "Gehalt")
    m = b.modell()
    fragen = [("Supermarkt Frischekorb", "Einkauf", -2000), ("Café Bohne", "", -500), ("Unbekannt", "Einkauf", -10),
              ("Unbekannt", "", -1500), (None, "LOHN", 310000), ("supermarkt-frischekorb", "", 5)]
    ist = vorhersagen(api, [_anfrage(*f) for f in fragen])
    for f, v in zip(fragen, ist):
        _gleich(v, m.vorhersage(merkmale(*f)))
    assert ist[0]["kategorie_id"] == b.kats["Lebensmittel"] and ist[0]["sicherheit"] >= 700
    assert ist[3] == {"kategorie_id": None, "sicherheit": None, "kandidaten": []}, "nur Betrag bekannt → nichts"
    z = api.get("/api/lernmodell", erwartet=200).daten
    assert (z["trainingsbuchungen"], z["kategorien"], z["merkmale"]) == (m.n, len(m.nk), len(m.nf))


@pytest.mark.kern
def test_trainingsmenge_nur_kategorisierte_ohne_vorschlag(api):
    """lernmodell.md 3: Umbuchungen, Splitbuchungen, Eigenkapital-Gegenkonto und offene Vorschläge zählen nicht."""
    b = Buch(api)
    b.einfach("Markt", "Einkauf", -100, "Lebensmittel")
    b.einfach("Markt", "Einkauf", -100, "Lebensmittel", konto=b.karte, status="importiert")
    api.buchung("2024-03-02", [(b.giro, -500), (b.karte, 500)], empfaenger_id=b.empfaenger("Markt"))
    api.buchung("2024-03-02", [(b.giro, -500), (b.kats["Lebensmittel"], 200), (b.kats["Café"], 300)],
                empfaenger_id=b.empfaenger("Markt"))
    b.einfach("Markt", "Einkauf", -100, None)
    abg = b.einfach("Markt", "Einkauf", -100, "Café")
    api.patch(f"/api/buchungen/{abg['id']}", json={"status": "abgeglichen"}, erwartet=200)  # Status egal
    assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] == 3
    # offener Vorschlag über das Lernmodell selbst: die Buchung fällt aus der Trainingsmenge
    offen = b.einfach("Markt", "Einkauf", -100, None)
    r = api.post("/api/lernmodell/anwenden", json={"buchung_ids": [offen["id"]]}, erwartet=200).daten
    if r["anzahl"]:
        assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] == 3
        api.post(f"/api/buchungen/{offen['id']}/vorschlag", json={"aktion": "annehmen"}, erwartet=200)
        assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] == 4
    _gleich(vorhersagen(api, [_anfrage("Markt", "Einkauf", -100)])[0],
            Modell(b.beispiele + ([(merkmale("Markt", "Einkauf", -100), r["aenderungen"][0]["kategorie_id"])]
                                  if r["anzahl"] else [])).vorhersage(merkmale("Markt", "Einkauf", -100)))


@pytest.mark.kern
def test_korrektur_fliesst_ein(api):
    """K 7, T 8: Eine Korrektur verändert nachweisbar künftige Vorschläge."""
    b = Buch(api)
    x = [b.einfach("Tankstelle Blitz", "", -4500, "Tanken") for _ in range(2)]
    b.einfach("Tankstelle Blitz", "", -4600, "Lebensmittel")
    frage = _anfrage("Tankstelle Blitz", "", -4700)
    vor = vorhersagen(api, [frage])[0]
    _gleich(vor, b.modell().vorhersage(merkmale("Tankstelle Blitz", "", -4700)))
    assert vor["kategorie_id"] == b.kats["Tanken"]
    api.put(f"/api/buchungen/{x[0]['id']}/kategorie", json={"kategorie_id": b.kats["Lebensmittel"]}, erwartet=200)
    b.beispiele[0] = (b.beispiele[0][0], b.kats["Lebensmittel"])
    nach = vorhersagen(api, [frage])[0]
    _gleich(nach, b.modell().vorhersage(merkmale("Tankstelle Blitz", "", -4700)))
    assert nach["kategorie_id"] == b.kats["Lebensmittel"], "die Korrektur dreht den Vorschlag"


def _p_fuer(k_a: int, k_b: int) -> Fraction:
    m = Modell([(["e:x", "b:-4"], 1)] * k_a + [(["e:x", "b:-4"], 2)] * k_b)
    s = {c: Fraction(m.nk[c], m.n) * Fraction(m.nkf["e:x"][c] + 1, m.nk[c] + 2) ** 2 for c in (1, 2)}
    return s[1] / sum(s.values())


@pytest.mark.kern
def test_schwelle_sieben_zehntel(api_fabrik):
    """lernmodell.md 4 Schritt 6: knapp unter 7/10 kein Vorschlag, ab 7/10 Vorschlag (exakt gerechnet)."""
    paare = [(a, b) for a in range(1, 9) for b in range(1, 9)]
    unter = next(p for p in paare if Fraction(6, 10) < _p_fuer(*p) < Fraction(7, 10))
    ueber = next(p for p in paare if _p_fuer(*p) >= Fraction(7, 10))
    for (ka, kb), vorschlag in ((unter, False), (ueber, True)):
        api = api_fabrik()
        b = Buch(api)
        for _ in range(ka):
            b.einfach("X", "", -1000, "Lebensmittel")
        for _ in range(kb):
            b.einfach("X", "", -2000, "Café")
        v = vorhersagen(api, [_anfrage("X", "", -3000)])[0]
        soll = b.modell().vorhersage(merkmale("X", "", -3000))
        _gleich(v, soll)
        assert (v["kategorie_id"] is not None) is vorschlag, (ka, kb, v)
        assert [k["kategorie_id"] for k in v["kandidaten"]] == [b.kats["Lebensmittel"], b.kats["Café"]]


def test_gleichstand_kleinere_id(api):
    b = Buch(api)
    b.einfach("Y", "", -100, "Café")
    b.einfach("Y", "", -100, "Lebensmittel")
    v = vorhersagen(api, [_anfrage("Y", "", -100)])[0]
    assert v["kategorie_id"] is None
    assert [k["kategorie_id"] for k in v["kandidaten"]] == sorted([b.kats["Café"], b.kats["Lebensmittel"]])
    assert v["kandidaten"][0]["sicherheit"] == v["kandidaten"][1]["sicherheit"] == 500


def test_vorhersage_ueber_buchung_id(api):
    b = Buch(api)
    for i in range(3):
        b.einfach("Markt", f"Einkauf {i}", -1000 * (i + 1), "Lebensmittel")
    neu = b.einfach("Markt", "Einkauf Filiale", -1200, None)
    via_id, via_merkmale = vorhersagen(api, [{"buchung_id": neu["id"]}, _anfrage("Markt", "Einkauf Filiale", -1200)])
    assert via_id == via_merkmale
    _gleich(via_id, b.modell().vorhersage(merkmale("Markt", "Einkauf Filiale", -1200)))
    # eine Trainingsbuchung bleibt bei der Abfrage über ihre ID Teil der Trainingsmenge
    t = vorhersagen(api, [{"buchung_id": b.buchungen[0]["id"]}])[0]
    _gleich(t, b.modell().vorhersage(merkmale("Markt", "Einkauf 0", -1000)))


def test_umbenennen_aendert_merkmale(api):
    """lernmodell.md 2: Merkmale nutzen den aktuellen Empfängernamen."""
    b = Buch(api)
    for _ in range(3):
        b.einfach("Altname", "", -100, "Café")
    api.patch(f"/api/empfaenger/{b.empf['Altname']}", json={"name": "Neuname"}, erwartet=200)
    alt, neu = vorhersagen(api, [_anfrage("Altname", "", -100), _anfrage("Neuname", "", -100)])
    assert alt["kategorie_id"] is None and neu["kategorie_id"] == b.kats["Café"]


@pytest.mark.kern
def test_vorhersage_aendert_nichts(api):
    b = Buch(api)
    b.einfach("Markt", "Einkauf", -100, "Lebensmittel")
    vorher, n = bestand(api), len(alle_aenderungen(api))
    vorhersagen(api, [_anfrage("Markt", "Einkauf", -100), {"buchung_id": b.buchungen[0]["id"]}])
    assert bestand(api) == vorher and len(alle_aenderungen(api)) == n


@pytest.mark.parametrize("koerper", [
    {}, {"eintraege": []}, {"eintraege": [{"betrag": 1.5}]}, {"eintraege": [{"betrag": "1"}]},
    {"eintraege": [{"verwendungszweck": "x"}]}, {"eintraege": [{"buchung_id": 1, "betrag": 5}]},
    {"eintraege": [{"betrag": 5, "farbe": "rot"}]}, {"eintraege": [{"betrag": 10 ** 12}]},
    {"eintraege": [{"betrag": 1, "empfaenger": "x" * 201}]}, {"eintraege": [{"betrag": 1}] * 1001},
], ids=["leer", "keine", "float", "text", "ohne_betrag", "beides", "unbekannt", "zu_gross", "name_lang", "zu_viele"])
def test_vorhersage_validierung(api, koerper):
    assert fehlercode(api.post("/api/lernmodell/vorhersage", json=koerper, erwartet=422)) == "validierung"


def test_vorhersage_unbekannte_buchung(api):
    r = api.post("/api/lernmodell/vorhersage", json={"eintraege": [{"buchung_id": 99}, {"buchung_id": 7}]},
                 erwartet=422)
    assert fehlercode(r) == "referenz_unbekannt" and r.json()["fehler"]["details"]["buchung_ids"] == [7, 99]


# ------------------------------------------------------------- Hypothesis
NAMEN = st.sampled_from(["Markt", "MARKT", "Café Bohne", "Tankstelle", "Bäckerei Müller", None])
WOERTER = st.lists(st.sampled_from(["Einkauf", "Filiale", "Café", "Kartenzahlung", "Diesel", "Brötchen", "12/2024",
                                    "ab", "Lohn", "Straße"]), max_size=4).map(" ".join)
BETRAG = st.sampled_from([-5, -340, -1234, -4500, -98000, 0, 250000, 1200])


@pytest.mark.kern
@given(st.lists(st.tuples(NAMEN, WOERTER, BETRAG, st.sampled_from(["Lebensmittel", "Café", "Tanken", "Gehalt", None])),
                max_size=25),
       st.lists(st.tuples(NAMEN, WOERTER, BETRAG), min_size=1, max_size=6))
def test_vorhersagen_gegen_orakel(api_fabrik, training, fragen):
    """Für zufällige Trainingsmengen stimmt jede Vorhersage exakt mit dem Orakel überein (lernmodell.md 2–4)."""
    api = api_fabrik()
    b = Buch(api)
    for name, zweck, betrag, kat in training:
        b.einfach(name, zweck, betrag, kat)
    ist = vorhersagen(api, [_anfrage(*f) for f in fragen])
    m = b.modell()
    for f, v in zip(fragen, ist):
        _gleich(v, m.vorhersage(merkmale(*f)) if b.beispiele else KEINE)
    z = api.get("/api/lernmodell", erwartet=200).daten
    assert (z["trainingsbuchungen"], z["kategorien"], z["merkmale"]) == (m.n, len(m.nk), len(m.nf))


# ---------------------------------------------- Mindestgenauigkeit (T 8, T 21)
@pytest.fixture(scope="module")
def lern():
    return lade(M4 / "lernen.erwartung.json")


def _pruefung_gegen_wahrheit(api, lern) -> dict:
    kat = {k["name"]: k["id"] for k in api.konten() if k["art"] in ("aufwand", "ertrag")}
    pruef = [w for w in lern["buchungen"] if w["teil"] == "pruefung"]
    ist = vorhersagen(api, [_anfrage(w["empfaenger"], w["verwendungszweck"], w["betrag"]) for w in pruef])
    soll = bewerte(lern["buchungen"], kat_id=lambda n: kat[n])
    for w, v, s in zip(pruef, ist, soll["vorhersagen"]):
        _gleich(v, s)
    vorgeschlagen = [(v, w) for v, w in zip(ist, pruef) if v["kategorie_id"] is not None]
    richtig = sum(v["kategorie_id"] == kat[w["wahr"]] for v, w in vorgeschlagen)
    return {"genauigkeit": Fraction(richtig, len(vorgeschlagen)), "abdeckung": Fraction(len(vorgeschlagen), len(pruef)),
            "n_train": soll["modell"].n}


@pytest.mark.kern
def test_mindestgenauigkeit_kmymoney_altdaten(api, lern):
    """T 21: ältere 80 % als KMyMoney-Altdaten, neueste 20 % geprüft: Genauigkeit ≥ 85 %, Abdeckung ≥ 70 %."""
    api.import_kmy(KMY / "m4_lernen_training.kmy", erwartet=200)
    r = _pruefung_gegen_wahrheit(api, lern)
    assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] == r["n_train"]
    assert r["genauigkeit"] >= Fraction(85, 100), f"Genauigkeit {float(r['genauigkeit']):.3f}"
    assert r["abdeckung"] >= Fraction(70, 100), f"Abdeckung {float(r['abdeckung']):.3f}"


def test_mindestgenauigkeit_gnucash_altdaten(api, lern):
    """Trainingsdaten aus GnuCash (K 7) liefern dieselben Vorhersagen."""
    import_gnc(api, GNC / "m4_lernen_training.gnucash")
    r = _pruefung_gegen_wahrheit(api, lern)
    assert r["genauigkeit"] >= Fraction(85, 100) and r["abdeckung"] >= Fraction(70, 100)
