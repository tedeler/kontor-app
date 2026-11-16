"""Eigene Tests zu Kontor-Ausdrücken (D-185): Sprache, Datum, Regeln mit Ausdruck, Testbereich, Filter."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor import ausdruck as A
from kontor.app import create_app
from kontor.config import KontorConfig

HEUTE = dt.date(2026, 11, 16)
BEZ = A.Bezuege(konto_pfad={1: "Girokonto"}, kategorie_pfad={10: "Lebensmittel", 11: "Lebensmittel:Supermarkt"},
                tag_name={5: "Urlaub"})


def _baum(text: str, kontext: str = "filter") -> dict:
    return A.uebersetzen(text, kontext, BEZ).baum


def _fehler(text: str, kontext: str = "filter") -> list[dict]:
    with pytest.raises(A.AusdruckFehler) as e:
        A.uebersetzen(text, kontext, BEZ)
    return e.value.fehler


# ------------------------------------------------------------- Sprache


@pytest.mark.parametrize("text, kanonisch", [
    ('"REWE" in empf and dir == "ausgabe" and bet > 5', '"REWE" in empfänger and richtung == "ausgabe" and betrag > 5'),
    ('("A" in empf || "B" in vwz) && !("C" in vwz)', '("A" in empfänger or "B" in verwendungszweck) and not "C" in verwendungszweck'),
    ("30 <= bet <= 40.5 and kategorie is None", "30 <= betrag <= 40.50 and kategorie is None"),
    ('empfaenger.search(r"^rewe\\b", case=True)', 'empfänger.search(r"^rewe\\b", case=True)'),
    ('wochentag in ("sa", "so")', 'wochentag in ["sa", "so"]'),
    ('kategorie == "Supermarkt"', 'kategorie == "Lebensmittel:Supermarkt"'),
])
def test_kanonische_form_und_rundreise(text, kanonisch):
    b = _baum(text, "regel")
    assert A.drucken(b, BEZ) == kanonisch
    assert _baum(kanonisch, "regel") == b


@pytest.mark.parametrize("text, code", [
    ('empf = "x"', "syntax"),
    ("bet > 12.505", "wert_ungueltig"),
    ('empf > "R"', "operator_unpassend"),
    ('vwz.search(r"(a)\\1")', "regex_nicht_unterstuetzt"),
    ('vwz.search(r"(?=a)")', "regex_nicht_unterstuetzt"),
    ('vwz.search(r"(a")', "regex_ungueltig"),
    ("empfnger", "feld_unbekannt"),
    ('kategorie == "Gibtsnicht"', "referenz_unbekannt"),
    ("datum >= 5.2.", "nur_im_filter"),
    ("jahr == 2020", "nur_im_filter"),
])
def test_fehler_in_regeln(text, code):
    assert _fehler(text, "regel")[0]["code"] == code


def test_fehlerposition():
    f = _fehler('empf == "x" and\nbet >> 5', "regel")[0]
    assert (f["zeile"], f["spalte"]) == (2, 6)


# --------------------------------------------------------------- Datum


@pytest.mark.parametrize("text, von, bis", [
    ("5.2.", "2026-02-05", "2026-02-05"),
    ("5.2.26", "2026-02-05", "2026-02-05"),
    ("2026-02-05", "2026-02-05", "2026-02-05"),
    ("-5d", "2026-11-12", "2026-11-16"),
    ("-1m", "2026-10-17", "2026-11-16"),
    ("+3d", "2026-11-16", "2026-11-18"),
    ("heute - 30d", "2026-10-18", "2026-11-16"),
    ("1.1.2017 + 1y", "2017-01-01", "2017-12-31"),
    ("1.1.2017 + 18m", "2017-01-01", "2018-06-30"),
    ("2017", "2017-01-01", "2017-12-31"),
    ("feb", "2026-02-01", "2026-02-28"),
    ("2/2025", "2025-02-01", "2025-02-28"),
    ("q3", "2026-07-01", "2026-09-30"),
    ("letzter_monat", "2026-10-01", "2026-10-31"),
    ("letzte_woche", "2026-11-09", "2026-11-15"),
    ("vorjahr", "2025-01-01", "2025-12-31"),
    ("5.2...10.3.", "2026-02-05", "2026-03-10"),
    ("-3m .. letzter_monat", "2026-08-17", "2026-10-31"),
    ("31.12.2025 - 1q", "2025-10-01", "2025-12-31"),
])
def test_zeitraeume(text, von, bis):
    z = _baum(f"datum in {text}")["terme"][1]["z"]
    assert A.zeitraum(z, HEUTE) == (dt.date.fromisoformat(von), dt.date.fromisoformat(bis))


@pytest.mark.parametrize("text, code", [
    ("datum == 5.2", "datum_ungueltig"),
    ("datum == 30.2.2026", "datum_ungueltig"),
    ("datum == 29.2.2026", "datum_ungueltig"),
    ("datum in 5d", "dauer_ohne_vorzeichen"),
    ("datum in 2018 .. 2017", "zeitraum_leer"),
])
def test_datumsfehler(text, code):
    assert _fehler(text)[0]["code"] == code


def test_vergleiche_mit_zeitraeumen():
    s = A.Sicht("X", "", -100, datum="2018-01-01")
    aw = A.Auswerter(HEUTE)
    assert aw.wahr(_baum("datum > 2017"), s) and not aw.wahr(_baum("datum <= 2017"), s)
    assert aw.wahr(_baum("2017 <= datum <= 2018"), s) and aw.wahr(_baum("datum in [dez/2017, 1/2018]"), s)


# ----------------------------------------------------- Freitext, Auswertung


def test_freitext_und_markierungen():
    assert A.drucken(_baum("rewe bet > 20"), BEZ) == '"rewe" and betrag > 20'
    assert _baum("rewe pfand") == {"t": "und", "teile": [{"t": "freitext", "wert": "rewe"},
                                                            {"t": "freitext", "wert": "pfand"}]}
    s = A.Sicht("REWE Markt", "Pfand Rückgabe", -2340, tag_namen=("Urlaub",))
    assert A.auswerten(_baum("rewe urlaub"), s, HEUTE)
    m = A.markierungen(_baum('empf.search(r"markt")'), s, HEUTE)
    assert m == [{"feld": "empfänger", "start": 5, "ende": 10}]
    assert _fehler("rewe", "regel")[0]["code"] == "feld_unbekannt"


def test_umlaute_und_gross_klein():
    s = A.Sicht("Bäckerei MÜLLER", "", -300)
    assert A.auswerten(_baum('"mueller" in empf', "regel"), s, HEUTE)
    assert not A.auswerten(_baum('empf.search(r"müller", case=True)', "regel"), s, HEUTE)


def test_alte_bedingungen_gleichbedeutend():
    from kontor.regeln import _trifft, bedingungen_als_baum
    for op in ("gleich", "mindestens", "hoechstens"):
        for w in (-500, 0, 500):
            bed = [{"feld": "betrag", "operator": op, "wert": w}]
            b = bedingungen_als_baum(bed)
            for rb in (-700, -500, -1, 0, 1, 500, 700):
                s = A.Sicht(None, "", rb)
                assert A.auswerten(b, s, HEUTE) == _trifft(bed[0], s), (op, w, rb)


# --------------------------------------------------------------- API


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30))))


def _empf(c: TestClient, name: str) -> int:
    for e in c.get("/api/empfaenger").json():
        if e["name"] == name:
            return e["id"]
    r = c.post("/api/empfaenger", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _buchung(c: TestClient, datum: str, empf: str, zweck: str, konto: int, betrag: int, gegen: int) -> int:
    r = c.post("/api/buchungen", json={"datum": datum, "empfaenger_id": _empf(c, empf), "verwendungszweck": zweck,
                                        "splits": [{"konto_id": konto, "betrag": betrag},
                                                   {"konto_id": gegen, "betrag": -betrag}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _aufbau(c: TestClient) -> dict:
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    lm = c.post("/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()["id"]
    cafe = c.post("/api/konten", json={"name": "Café", "art": "aufwand"}).json()["id"]
    ids = []
    for datum, empf, zweck, betrag, kat in [("2024-06-10", "REWE Markt", "Einkauf", -2340, None),
                                            ("2024-06-11", "REWE To Go", "Kaffee", -410, cafe),
                                            ("2024-06-12", "EDEKA", "Einkauf", -1500, lm),
                                            ("2023-01-05", "REWE Markt", "alt", -999, None)]:
        ids.append(_buchung(c, datum, empf, zweck, giro, betrag, kat or lm))
    return {"giro": giro, "lm": lm, "cafe": cafe, "ids": ids}


def test_pruefen_endpunkt(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/ausdruck/pruefen", json={"ausdruck": "rewe dt in -5d", "kontext": "filter",
                                              "stichtag": "2026-11-16"}).json()
    assert r["gueltig"] and r["kanonisch"] == '"rewe" and datum in -5d'
    assert r["datumsangaben"] == [{"text": "-5d", "von": "2026-11-12", "bis": "2026-11-16", "tage": 5,
                                   "relativ": True}]
    r = c.post("/api/ausdruck/pruefen", json={"ausdruck": "dt in -5d", "kontext": "regel"}).json()
    assert not r["gueltig"] and r["fehler"][0]["code"] == "nur_im_filter"
    assert any(f["name"] == "datum" for f in c.get("/api/ausdruck/sprache?kontext=filter").json()["felder"])
    assert not any(f["name"] == "datum" for f in c.get("/api/ausdruck/sprache?kontext=regel").json()["felder"])


def test_regel_mit_ausdruck_crud_und_alte_form(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    r = c.post("/api/regeln", json={"name": "REWE", "kategorie_id": k["lm"],
                                    "ausdruck": '"rewe" in empf and bet > 5'})
    assert r.status_code == 201, r.text
    regel = r.json()
    assert regel["ausdruck"] == '"rewe" in empfänger and betrag > 5' and regel["ausdruck_form"] == "ausdruck"
    r = c.post("/api/regeln", json={"name": "x", "kategorie_id": k["lm"], "ausdruck": "dt in -5d"})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "ausdruck_ungueltig"
    alt = c.post("/api/regeln", json={"name": "alt", "kategorie_id": k["cafe"], "bedingungen": [
        {"feld": "empfaenger", "operator": "beginnt_mit", "wert": "REWE"},
        {"feld": "betrag", "operator": "mindestens", "wert": -500}]}).json()
    assert alt["ausdruck"] == ('empfänger.startswith("REWE") and (richtung != "ausgabe" or betrag <= 5)')
    # Reihenfolge (eine Änderung im Protokoll)
    neu = c.post("/api/regeln/reihenfolge", json={"regel_ids": [alt["id"], regel["id"]]})
    assert [x["id"] for x in neu.json()] == [alt["id"], regel["id"]]
    assert c.post("/api/regeln/reihenfolge", json={"regel_ids": [alt["id"]]}).status_code == 422
    # Umbenennen der Kategorie ändert den gedruckten Ausdruck, nicht den Verweis
    c.post("/api/regeln", json={"name": "k", "kategorie_id": k["lm"], "ausdruck": 'kategorie == "Café"'})
    c.patch(f"/api/konten/{k['cafe']}", json={"name": "Kaffee"})
    assert any(x["ausdruck"] == 'kategorie == "Kaffee"' for x in c.get("/api/regeln").json())
    # Konto mit Verweis im Ausdruck ist nicht löschbar
    assert c.delete(f"/api/konten/{k['cafe']}").status_code == 409


def test_testbereich_erklaeren_anwenden(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    unk = _buchung(c, "2024-06-13", "REWE City", "", k["giro"], -100, k["cafe"])
    c.post("/api/regeln", json={"name": "Café", "kategorie_id": k["cafe"], "ausdruck": '"to go" in empf'})
    test = c.post("/api/regeln/test", json={"ausdruck": '"rewe" in empf', "kategorie_id": k["lm"],
                                            "testmenge": "datum in 2024"}).json()
    wirkung = {z["buchung_id"]: z["wirkung"] for z in test["treffer"]}
    assert wirkung == {k["ids"][0]: "bereits_so", k["ids"][1]: "verdeckt", unk: "abweichend"}
    assert test["nicht_erfasst"]["buchung_ids"] == [k["ids"][2]]   # EDEKA hat die Kategorie, trifft nicht
    assert test["treffer"][0]["markierungen"][0]["feld"] == "empfänger"
    # Quellkonto: nur Buchungen mit Split auf diesem Konto; kein Bestandskonto → 422
    leer = c.post("/api/konten", json={"name": "Spar", "art": "sparkonto"}).json()["id"]
    assert c.post("/api/regeln/test", json={"ausdruck": '"rewe" in empf', "konto_id": leer, "testmenge": ""}).json()["testmenge_anzahl"] == 0
    assert c.post("/api/regeln/test", json={"ausdruck": '"rewe" in empf', "konto_id": k["giro"], "testmenge": ""}).json()["anzahl"] == 4
    r = c.post("/api/regeln/test", json={"ausdruck": '"rewe" in empf', "konto_id": k["lm"]})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "konto_ungueltig"
    e = c.post("/api/regeln/erklaeren", json={"ausdruck": '"rewe" in empf and bet > 50',
                                              "buchung_id": k["ids"][1]}).json()
    assert e["ergebnis"] == "falsch"
    assert [x["ergebnis"] for x in e["baum"]["kinder"]] == ["wahr", "falsch"]
    rid = c.post("/api/regeln", json={"name": "REWE", "kategorie_id": k["lm"], "ausdruck": '"rewe" in empf'}).json()["id"]
    r = c.post(f"/api/regeln/{rid}/anwenden", json={"testmenge": "datum in 2024", "abweichende_ueberschreiben": True})
    assert r.json() == {"geaendert": [unk], "anzahl": 1}
    b = c.get(f"/api/buchungen/{unk}").json()
    assert b["kategorie_id"] == k["lm"] and b["vorschlag"]["quelle"] == "regel"
    aenderung = c.get("/api/aenderungen").json()["eintraege"][0]
    assert aenderung["aktion"] == "regeln_anwenden"
    c.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [aenderung["id"]]})
    assert c.get(f"/api/buchungen/{unk}").json()["kategorie_id"] == k["cafe"]


def test_filter_in_buchungsliste(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)

    def ids(f: str) -> list[int]:
        r = c.get("/api/buchungen", params={"konto_id": k["giro"], "filter": f, "stichtag": "2024-06-30"})
        assert r.status_code == 200, r.text
        return sorted(e["id"] for e in r.json()["eintraege"])

    assert ids("rewe") == sorted([k["ids"][0], k["ids"][1], k["ids"][3]])
    assert ids("rewe dt in 2024") == sorted(k["ids"][:2])
    assert ids("dt in -30d and bet > 10") == [k["ids"][0], k["ids"][2]]
    assert ids('kategorie == "Café" or dir == "einnahme"') == [k["ids"][1]]
    r = c.get("/api/buchungen", params={"konto_id": k["giro"], "filter": "rewe", "betrag_max": -1000})
    assert [e["id"] for e in r.json()["eintraege"]] == [k["ids"][0]]
    assert r.json()["eintraege"][0]["markierungen"] == [{"feld": "empfänger", "start": 0, "ende": 4}]
    r = c.get("/api/buchungen", params={"filter": "datum == 5.2"})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "ausdruck_ungueltig"
