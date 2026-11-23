"""M4: Lernmodell anwenden – vorhandene Buchungen, Synchronisation, Erfassen, Stufenfolge (lernmodell.md 5, 7; K 7; T 8).

Erwartete Vorschläge berechnet das Orakel ``tests/hilfen/lern_orakel.py`` aus
den Trainingsbeispielen, die der Test selbst angelegt hat, bzw. aus der
Wahrheit des Generators (``m4/lernen.erwartung.json``).
"""

from __future__ import annotations

import pytest

from generator.iban import fiktive_iban
from tests.hilfen.api import fehlercode
from tests.hilfen.lern_orakel import Modell, merkmale
from tests.hilfen.m3 import (UNKATEGORISIERT, aenderungen_seit, bestand, erfassen, konto_id, letzte_aenderung_id,
                             pruefe_eintraege, pruefe_rueckgaengig_rundreise)
from tests.hilfen.m4 import (LERN_MOCK, M4, Buch, bank_buchungen, lade, mock_api, mock_datei, sync, umsatz,
                             vorhersagen)
from tests.hilfen.pfade import KMY

GIRO = fiktive_iban(7601)
FREMD = fiktive_iban(7699)


def _training(b: Buch) -> None:
    for i in range(3):
        b.einfach("Supermarkt", f"Einkauf {i}", -1500, "Lebensmittel")
    b.einfach("Café Bohne", "Kartenzahlung", -340, "Café")
    b.einfach("Café Bohne", "Kartenzahlung", -360, "Café")


@pytest.mark.kern
def test_anwenden_auf_unkategorisierte(api):
    b = Buch(api)
    _training(b)
    m = b.modell()
    g = b.giro
    kandidaten = [erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=g, betrag=1700,
                           empfaenger_name="Supermarkt", verwendungszweck="Einkauf"),
                  erfassen(api, art="ausgabe", datum="2024-04-02", konto_id=g, betrag=300, empfaenger_name="Café Bohne"),
                  erfassen(api, art="ausgabe", datum="2024-04-03", konto_id=g, betrag=999, empfaenger_name="Unbekannt")]
    gesperrt = erfassen(api, art="ausgabe", datum="2024-04-04", konto_id=g, betrag=1500,
                        empfaenger_name="Supermarkt")
    api.patch(f"/api/buchungen/{gesperrt['id']}", json={"status": "abgeglichen"}, erwartet=200)
    unk = konto_id(api, UNKATEGORISIERT)
    soll = []
    for k in kandidaten:
        v = m.vorhersage(merkmale(k["empfaenger"]["name"], k["verwendungszweck"], -k["betrag"]))
        if v.kategorie_id is not None:
            soll.append({"buchung_id": k["id"], "kategorie_id": v.kategorie_id, "sicherheit": v.sicherheit})
    assert len(soll) == 2, "Supermarkt und Café werden vorgeschlagen, Unbekannt nicht"
    vorher = bestand(api)
    t = api.post("/api/lernmodell/anwenden", json={"trocken": True}, erwartet=200).daten
    assert t == {"geprueft": 3, "anzahl": 2, "trocken": True, "aenderungen": soll}
    assert bestand(api) == vorher
    a0 = letzte_aenderung_id(api)
    r = api.post("/api/lernmodell/anwenden", json={}, erwartet=200).daten
    assert r == {**t, "trocken": False}
    for s in soll:
        x = api.buchung_lesen(s["buchung_id"])
        assert x["vorschlag"] == {"kategorie_id": s["kategorie_id"], "regel_id": None, "quelle": "lernmodell",
                                  "vorher_konto_id": unk, "sicherheit": s["sicherheit"]}
        assert x["kategorie_id"] == s["kategorie_id"]
    assert api.buchung_lesen(gesperrt["id"])["vorschlag"] is None, "gesperrte Buchungen werden übergangen"
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("lernmodell", "lernmodell_anwenden", None)
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    pruefe_rueckgaengig_rundreise(api, a, vorher, nachher)


def test_anwenden_ohne_wirkung_und_auswahl(api):
    b = Buch(api)
    _training(b)
    x = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1700, empfaenger_name="Supermarkt",
                 verwendungszweck="Einkauf")
    y = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1700, empfaenger_name="Supermarkt",
                 verwendungszweck="Einkauf")
    a0 = letzte_aenderung_id(api)
    r = api.post("/api/lernmodell/anwenden", json={"buchung_ids": [y["id"], b.buchungen[0]["id"]]}, erwartet=200).daten
    assert (r["geprueft"], [c["buchung_id"] for c in r["aenderungen"]]) == (1, [y["id"]])
    assert api.buchung_lesen(x["id"])["vorschlag"] is None
    r2 = api.post("/api/lernmodell/anwenden", json={"buchung_ids": [y["id"]]}, erwartet=200).daten
    assert (r2["geprueft"], r2["anzahl"]) == (0, 0), "mit offenem Vorschlag nicht mehr unkategorisiert"
    assert len(aenderungen_seit(api, a0)) == 1


@pytest.mark.parametrize("koerper,code", [
    ({"buchung_ids": [999, 998]}, "referenz_unbekannt"), ({"buchung_ids": [1, 1]}, "validierung"),
    ({"buchung_ids": []}, "validierung"), ({"trocken": "ja"}, "validierung"), ({"regel_ids": [1]}, "validierung")])
def test_anwenden_fehler(api, koerper, code):
    Buch(api).einfach("A", "", -1, "Café")
    r = api.post("/api/lernmodell/anwenden", json=koerper, erwartet=422)
    assert fehlercode(r) == code
    if code == "referenz_unbekannt":
        assert r.json()["fehler"]["details"]["buchung_ids"] == [998, 999]


@pytest.mark.kern
def test_annehmen_ablehnen_und_trainingsmenge(api):
    b = Buch(api)
    _training(b)
    x = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1700, empfaenger_name="Supermarkt",
                 verwendungszweck="Einkauf")
    y = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1600, empfaenger_name="Supermarkt",
                 verwendungszweck="Einkauf")
    api.post("/api/lernmodell/anwenden", json={}, erwartet=200)
    n = api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"]
    api.post(f"/api/buchungen/{x['id']}/vorschlag", json={"aktion": "annehmen"}, erwartet=200)
    api.post(f"/api/buchungen/{y['id']}/vorschlag", json={"aktion": "ablehnen"}, erwartet=200)
    assert api.buchung_lesen(y["id"])["kategorie_id"] is None
    assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] == n + 1
    b.beispiele.append((merkmale("Supermarkt", "Einkauf", -1700), b.kats["Lebensmittel"]))
    v = vorhersagen(api, [{"empfaenger": "Supermarkt", "verwendungszweck": "", "betrag": -10}])[0]
    assert v == b.modell().vorhersage(merkmale("Supermarkt", "", -10)).als_json()


# ------------------------------------------------------------ Synchronisation
@pytest.fixture(scope="module")
def lern():
    return lade(M4 / "lernen.erwartung.json")


def _lern_sync(tmp_path, lern, automatisch: bool):
    pruef = [w for w in lern["buchungen"] if w["teil"] == "pruefung"]
    api = mock_api(tmp_path, LERN_MOCK, pruef[-1]["datum"], lernmodell_automatisch=automatisch)
    api.import_kmy(KMY / "m4_lernen_training.kmy", erwartet=200)
    lauf = sync(api, von=lern["erstes_pruefdatum"])
    assert lauf["status"] == "erfolgreich"
    return api, lauf, pruef


@pytest.mark.kern
def test_synchronisation_mit_lernmodell(tmp_path, lern):
    """lernmodell.md 5.1: Prüfumsätze erhalten genau die Vorschläge des Orakels (Trainingsmenge = Altdaten)."""
    api, lauf, pruef = _lern_sync(tmp_path, lern, True)
    kat = {k["name"]: k["id"] for k in api.konten() if k["art"] in ("aufwand", "ertrag")}
    modell = Modell([(merkmale(w["empfaenger"], w["verwendungszweck"], w["betrag"]), kat[w["kategorie"]])
                     for w in lern["buchungen"] if w["teil"] == "training"])
    unk = konto_id(api, UNKATEGORISIERT)
    bank = bank_buchungen(api)
    neu = vorgeschlagen = 0
    for w in pruef:
        b = bank[w["umsatz_id"]]
        if any(e.startswith("kmy:") for e in b["extern_ids"]):
            continue  # mit Altbestand zusammengeführt
        neu += 1
        v = modell.vorhersage(merkmale(w["empfaenger"], w["verwendungszweck"], w["betrag"]))
        if v.kategorie_id is None:
            assert b["vorschlag"] is None and b["kategorie_id"] is None, w
        else:
            vorgeschlagen += 1
            assert b["vorschlag"] == {"kategorie_id": v.kategorie_id, "regel_id": None, "quelle": "lernmodell",
                                      "vorher_konto_id": unk, "sicherheit": v.sicherheit}, w
            assert b["kategorie_id"] == v.kategorie_id
    assert vorgeschlagen >= 0.7 * len(pruef) - 5
    assert sum(k["buchungen_kategorisiert"] for k in lauf["konten"]) == vorgeschlagen
    assert sum(k["buchungen_neu"] for k in lauf["konten"]) == neu
    assert api.get("/api/lernmodell", erwartet=200).daten["automatisch"] is True


def test_synchronisation_ohne_lernmodell_wie_m3(tmp_path, lern):
    """E-072: Vorgabe aus – die Synchronisation verhält sich wie in M3."""
    api, lauf, _ = _lern_sync(tmp_path, lern, False)
    assert all(b["vorschlag"] is None for b in bank_buchungen(api).values())
    assert sum(k["buchungen_kategorisiert"] for k in lauf["konten"]) == 0
    assert api.get("/api/lernmodell", erwartet=200).daten["automatisch"] is False


def _klein(tmp_path, umsaetze, **felder):
    p = mock_datei(tmp_path / "bank.json", [(GIRO, "Giro", "girokonto")], umsaetze)
    api = mock_api(tmp_path, p, "2024-06-30", lernmodell_automatisch=True, **felder)
    b = Buch(api)
    api.patch(f"/api/konten/{b.giro}", json={"iban": GIRO}, erwartet=200)
    return api, b


@pytest.mark.kern
def test_stufenfolge_regel_lernmodell(tmp_path):
    """K 7, T 8: Regeln greifen vor dem Lernmodell (lernmodell.md 5.1). Ab M32 gibt es keine Standardkategorie; an
    ihrer Stelle steht die umgewandelte Regel „Empfänger ist <Name>“ am Ende der Regelliste (sammel3.md 2.1, E-307)."""
    us = [umsatz("U1", GIRO, "2024-06-01", -1500, "Supermarkt", "Einkauf Sonderposten"),
          umsatz("U2", GIRO, "2024-06-02", -1500, "Supermarkt", "Einkauf"),
          umsatz("U3", GIRO, "2024-06-03", -1500, "Supermarkt Zwei", "Einkauf"),
          umsatz("U4", GIRO, "2024-06-04", -1500, "Supermarkt", "Einkauf", gegenpartei_iban=FREMD),
          umsatz("U5", GIRO, "2024-06-05", -1500, "Supermarkt", "Einkauf", gegenpartei_iban="DE00 kaputt")]
    api, b = _klein(tmp_path, us)
    _training(b)
    regel = api.post("/api/regeln", json={"name": "Sonder", "kategorie_id": b.kats["Tanken"], "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "sonderposten"}]}, erwartet=201).daten
    std = api.post("/api/regeln", json={"name": "Empfänger ist Supermarkt Zwei", "kategorie_id": b.kats["Café"],
                                        "bedingungen": [{"feld": "empfaenger", "operator": "gleich",
                                                         "wert": "Supermarkt Zwei"}]}, erwartet=201).daten
    sync(api, von="2024-06-01")
    x = bank_buchungen(api)
    assert x["U1"]["vorschlag"]["quelle"] == "regel" and x["U1"]["vorschlag"]["regel_id"] == regel["id"]
    assert x["U2"]["vorschlag"]["quelle"] == "lernmodell" and x["U2"]["kategorie_id"] == b.kats["Lebensmittel"]
    assert x["U3"]["vorschlag"]["quelle"] == "regel" and x["U3"]["vorschlag"]["regel_id"] == std["id"]
    assert x["U3"]["kategorie_id"] == b.kats["Café"]
    assert x["U4"]["vorschlag"]["quelle"] == "lernmodell", "fremde Gegen-IBAN: Lernmodell wird befragt"
    assert x["U5"]["vorschlag"]["quelle"] == "lernmodell", "ungültige Gegen-IBAN zählt nicht"


@pytest.mark.kern
def test_eigene_gegen_iban_kein_lernmodell(tmp_path):
    """lernmodell.md 5.1 Ausnahme: mögliche Umbuchung bleibt unkategorisiert."""
    spar = fiktive_iban(7602)
    us = [umsatz("U1", GIRO, "2024-06-01", -1500, "Supermarkt", "Einkauf", gegenpartei_iban=spar)]
    api, b = _klein(tmp_path, us)
    _training(b)
    api.konto("Tagesgeld", "sparkonto", iban=spar)
    sync(api, von="2024-06-01")
    x = bank_buchungen(api)["U1"]
    assert x["vorschlag"] is None and x["kategorie_id"] is None and x["gegen_iban"] == spar


def test_trainingsmenge_zu_beginn_des_kontos(tmp_path):
    """Neue Buchungen desselben Abrufs beeinflussen sich nicht (Trainingsmenge zu Beginn des Kontos)."""
    us = [umsatz(f"U{i}", GIRO, f"2024-06-0{i + 1}", -1500, "Neuer Laden", "Einkauf") for i in range(3)]
    api, b = _klein(tmp_path, us)
    _training(b)
    sync(api, von="2024-06-01")
    m = b.modell()
    soll = m.vorhersage(merkmale("Neuer Laden", "Einkauf", -1500))
    for x in bank_buchungen(api).values():
        assert (x["vorschlag"] or {}).get("kategorie_id") == soll.kategorie_id


# ------------------------------------------------------------------ Erfassen
@pytest.mark.kern
def test_erfassen_mit_lernmodell(tmp_path):
    api, b = _klein(tmp_path, [])
    _training(b)
    a = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1500, empfaenger_name="Supermarkt",
                 verwendungszweck="Einkauf")
    v = b.modell().vorhersage(merkmale("Supermarkt", "Einkauf", -1500))
    unk = konto_id(api, UNKATEGORISIERT)
    assert a["vorschlag"] == {"kategorie_id": v.kategorie_id, "regel_id": None, "quelle": "lernmodell",
                              "vorher_konto_id": unk, "sicherheit": v.sicherheit}
    e = erfassen(api, art="einnahme", datum="2024-04-01", konto_id=b.giro, betrag=1500, empfaenger_name="Supermarkt")
    assert e["vorschlag"] is None or e["vorschlag"]["quelle"] == "lernmodell"
    assert e["vorschlag"] == ({"kategorie_id": w.kategorie_id, "regel_id": None, "quelle": "lernmodell",
                               "vorher_konto_id": unk, "sicherheit": w.sicherheit}
                              if (w := b.modell().vorhersage(merkmale("Supermarkt", "", 1500))).kategorie_id
                              else None), "Regelbetrag bei Einnahme positiv"
    mit = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1500, empfaenger_name="Supermarkt",
                   kategorie_id=b.kats["Tanken"])
    assert mit["vorschlag"] is None and mit["kategorie_id"] == b.kats["Tanken"]
    k = erfassen(api, art="korrektur", datum="2024-04-01", konto_id=b.giro, betrag=1500, empfaenger_name="Supermarkt")
    assert k["vorschlag"] is None, "Korrekturen werden nicht vom Lernmodell kategorisiert"


def test_erfassen_ohne_lernmodell(api):
    b = Buch(api)
    _training(b)
    a = erfassen(api, art="ausgabe", datum="2024-04-01", konto_id=b.giro, betrag=1500, empfaenger_name="Supermarkt",
                 verwendungszweck="Einkauf")
    assert a["vorschlag"] is None and a["kategorie_id"] is None
