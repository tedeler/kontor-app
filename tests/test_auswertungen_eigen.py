"""Weitere Berichte (Feature berichte, D-217): Verträge, Jahr, Vorschau, Vermögen, Kategorien, Empfänger, Geldfluss,
Datenqualität, Tags. Synthetische Daten."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def _client(tmp_path, heute=dt.date(2024, 6, 15)) -> TestClient:
    return TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=heute)))


def _konto(c, name, art, eltern=None):
    r = c.post("/api/konten", json={"name": name, "art": art, **({"eltern_id": eltern} if eltern else {})})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _buchen(c, art, konto, datum, betrag, name, tags=None, **extra):
    r = c.post("/api/buchungen/erfassen", json={
        "art": art, "datum": datum, "konto_id": konto, "betrag": betrag, "empfaenger_name": name, **extra})
    assert r.status_code == 201, r.text
    if tags:
        assert c.patch(f"/api/buchungen/{r.json()['id']}", json={"tag_ids": tags}).status_code == 200
    return r.json()


def _b(c, name, **params):
    r = c.get(f"/api/berichte/{name}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def haus(tmp_path):
    """Januar bis Juni 2024 (heute 15.06.): Miete, Strom, Einkäufe, Gehalt, Sparrate; Anfangsbestand; Tags."""
    c = _client(tmp_path)
    k = {"giro": _konto(c, "Giro", "girokonto"), "spar": _konto(c, "Sparbuch", "sparkonto"),
         "wohnen": _konto(c, "Wohnen", "aufwand"), "leben": _konto(c, "Leben", "aufwand"),
         "lohn": _konto(c, "Lohn", "ertrag"), "anfang": _konto(c, "Anfangsbestand", "eigenkapital")}
    k["miete"] = _konto(c, "Miete", "aufwand", k["wohnen"])
    k["strom"] = _konto(c, "Strom", "aufwand", k["wohnen"])
    k["essen"] = _konto(c, "Essen", "aufwand", k["leben"])
    r = c.post("/api/buchungen", json={"datum": "2024-01-01", "verwendungszweck": "Anfangsbestand", "splits": [
        {"konto_id": k["giro"], "betrag": 100_000}, {"konto_id": k["anfang"], "betrag": -100_000}]})
    assert r.status_code == 201, r.text
    k["urlaub"] = c.post("/api/tags", json={"name": "Urlaub"}).json()["id"]
    k["auto"] = c.post("/api/tags", json={"name": "Auto"}).json()["id"]
    for m in range(1, 7):
        _buchen(c, "ausgabe", k["giro"], f"2024-{m:02d}-01", 80_000 if m < 6 else 85_000, "Vermieter", kategorie_id=k["miete"])
        _buchen(c, "einnahme", k["giro"], f"2024-{m:02d}-02", 250_000, "Arbeitgeber", kategorie_id=k["lohn"])
        _buchen(c, "umbuchung", k["giro"], f"2024-{m:02d}-03", 20_000, "Sparrate", gegenkonto_id=k["spar"])
        _buchen(c, "ausgabe", k["giro"], f"2024-{m:02d}-10", 5_000, "Stadtwerke", kategorie_id=k["strom"])
        for tag in (5, 12):
            _buchen(c, "ausgabe", k["giro"], f"2024-{m:02d}-{tag:02d}", 4_000 + m * 100, "Supermarkt", kategorie_id=k["essen"])
    _buchen(c, "ausgabe", k["giro"], "2024-05-18", 60_000, "Reisebüro", kategorie_id=k["leben"], tags=[k["urlaub"]])
    _buchen(c, "ausgabe", k["giro"], "2024-06-08", 7_000, "Tankstelle", tags=[k["auto"], k["urlaub"]])
    k["unkat"] = _buchen(c, "ausgabe", k["giro"], "2024-06-09", 1_500, "Kiosk")["id"]
    return c, k


def test_vertraege(haus):
    c, k = haus
    b = _b(c, "vertraege")
    namen = [v["empfaenger"]["name"] for v in b["ausgaben"]]
    assert namen == ["Vermieter", "Stadtwerke"]          # die Sparrate ist eine Umbuchung, der Supermarkt keine Serie
    miete = b["ausgaben"][0]
    assert miete["betrag"] == 85_000 and miete["jahreskosten"] == 1_020_000 and miete["monatlich"] == 85_000
    assert miete["aenderungen"] == [{"datum": "2024-06-01", "vorher": 80_000, "betrag": 85_000}]
    assert miete["erster_betrag"] == 80_000 and miete["anzahl"] == 6 and len(miete["zahlungen"]) == 6
    assert miete["summe_12"] == 485_000 and miete["naechste_faelligkeit"] == "2024-07-01" and miete["neu"] is False
    s = b["summen"]
    assert s["anzahl"] == 2 and s["jaehrlich"] == 1_020_000 + 60_000 and s["monatlich"] == s["jaehrlich"] // 12
    assert s["geaendert"] == 1 and s["einnahmen_monatlich"] == 250_000
    assert [v["empfaenger"]["name"] for v in b["einnahmen"]] == ["Arbeitgeber"]
    assert s["anteil_promille"] == s["jaehrlich"] * 1000 // s["ausgaben_12"]


def test_jahr(haus):
    c, k = haus
    b = _b(c, "jahr")
    assert b["jahr"] == 2024 and b["laufend"] is True and b["bis_monat"] == 6 and len(b["monate"]) == 12
    jan = b["monate"][0]
    assert jan["ausgaben"] == 80_000 + 5_000 + 2 * 4_100 and jan["einnahmen"] == 250_000      # ohne Anfangsbestand
    assert jan["fix"] == 85_000 and jan["variabel"] == 8_200
    s = b["summen"]
    assert s["ausgaben"] == sum(m["ausgaben"] for m in b["monate"]) and s["einnahmen"] == 6 * 250_000
    assert s["vorjahr"] is None and s["vorjahr_bis_monat"] is None
    assert b["top_buchungen"]["eintraege"][0]["betrag"] == 85_000
    assert b["top_empfaenger"][0]["empfaenger"]["name"] == "Vermieter" and b["top_empfaenger"][0]["vorjahr"] == 0
    assert b["ausgeschlossen"]["umbuchungen"] == 7 and b["erstes_jahr"] == 2024
    vor = _b(c, "jahr", jahr=2025)
    assert vor["zukunft"] is True and vor["summen"]["ausgaben"] == 0 and vor["summen"]["vorjahr"] == s["ausgaben"]


def test_vorschau(haus):
    c, k = haus
    b = _b(c, "vorschau", tage=30)
    assert [x["id"] for x in b["konten"]] == [k["giro"]] and b["tage"] == 30 and b["bis"] == "2024-07-15"
    start = b["start"]
    assert start == b["verlauf"]["fest"][0] == b["verlauf"]["erwartet"][0] and len(b["verlauf"]["tage"]) == 31
    ereignisse = {(e["datum"], e["empfaenger"]["name"]): e["betrag"] for e in b["ereignisse"]}
    assert ereignisse == {("2024-07-01", "Vermieter"): -85_000, ("2024-07-02", "Arbeitgeber"): 250_000,
                          ("2024-07-03", "Sparrate"): -20_000, ("2024-07-10", "Stadtwerke"): -5_000}
    assert b["verlauf"]["fest"][-1] == start + 250_000 - 110_000 == b["ende"]["fest"]
    assert b["ende"]["erwartet"] == b["ende"]["fest"] - 30 * b["variabel_pro_tag"] and b["variabel_pro_tag"] > 0
    assert b["naechster_eingang"]["datum"] == "2024-07-02"
    f = b["frei"]
    assert f["tage"] == 17 and f["feste_ausgaben"] == 85_000 and f["betrag"] == start - 85_000
    assert f["nach_variabel"] == f["betrag"] - 17 * b["variabel_pro_tag"]
    assert b["tiefststand_fest"] == {"datum": "2024-07-01", "betrag": start - 85_000}
    assert c.get("/api/berichte/vorschau", params={"tage": 45}).status_code == 422


def test_vermoegen(haus):
    c, k = haus
    b = _b(c, "vermoegen")
    assert b["monate"] == ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
    je = {z["name"]: z["werte"] for z in b["konten"]}
    assert je["Sparbuch"] == [20_000 * n for n in range(1, 7)]
    assert b["netto"][0] == 100_000 + 250_000 - 93_200 and b["schulden"] == [0] * 6
    assert b["netto"][-1] == je["Giro"][-1] + je["Sparbuch"][-1] == b["kennzahlen"]["netto"]
    assert b["kennzahlen"]["veraenderung"] == b["netto"][-1] - b["netto"][0]
    assert [s["saldo"] for s in b["sparen"]][0] == 250_000 - 93_200      # Anfangsbestand ist keine Einnahme
    assert b["kredite"] == []
    assert _b(c, "vermoegen", monate=12)["monate"] == b["monate"]


def test_kategorien(haus):
    c, k = haus
    b = _b(c, "kategorien")
    z = {x["name"]: x for x in b["ausgaben"]}
    assert [x["name"] for x in b["ausgaben"]] == ["Leben", "Essen", "Wohnen", "Miete", "Strom", "Unkategorisiert"]
    assert z["Wohnen"]["summe"] == 90_000 and z["Wohnen"]["eigen"] == 0 and z["Miete"]["ebene"] == 1
    assert z["Miete"]["schnitt"] == 80_000 and z["Miete"]["abweichung"] == 5_000 and b["vergleich_monate"] == 5
    assert z["Leben"]["summe"] == 2 * 4_600 and z["Leben"]["schnitt"] == (sum(2 * (4_000 + m * 100) for m in range(1, 6)) + 60_000) // 5
    assert z["Unkategorisiert"]["summe"] == 8_500 and z["Unkategorisiert"]["unkategorisiert"] is True
    assert len(z["Miete"]["verlauf"]) == 13 and z["Miete"]["verlauf"][-2:] == [80_000, 85_000]
    assert b["summen"] == {"ausgaben": 90_000 + 9_200 + 8_500, "einnahmen": 250_000, "unkategorisiert": 8_500}
    assert [x["name"] for x in b["einnahmen"]] == ["Lohn"]
    kiosk = [x for x in b["buchungen"] if x["id"] == k["unkat"]][0]
    assert kiosk["teile"] == [{"konto_id": z["Unkategorisiert"]["id"], "betrag": -1_500}]


def test_empfaenger(haus):
    c, k = haus
    liste = _b(c, "empfaenger")
    assert liste["empfaenger"] is None and liste["rangliste"][0]["empfaenger"]["name"] == "Arbeitgeber"
    eid = [e["empfaenger"]["id"] for e in liste["rangliste"] if e["empfaenger"]["name"] == "Supermarkt"][0]
    assert "Sparrate" not in [e["empfaenger"]["name"] for e in liste["rangliste"]]
    b = _b(c, "empfaenger", empfaenger_id=eid)
    kz = b["kennzahlen"]
    assert kz["anzahl"] == 12 and kz["ausgaben"] == sum(2 * (4_000 + m * 100) for m in range(1, 7))
    assert kz["median"] == 4_350 and kz["groesste"] == 4_600 and kz["erste"] == "2024-01-05" and kz["letzte"] == "2024-06-12"
    assert kz["abstand_tage"] in (7, 23, 24) and len(b["monate"]) == 24 and b["monate"][-1]["ausgaben"] == 9_200
    assert b["jahre"] == [{"jahr": 2024, "ausgaben": kz["ausgaben"], "einnahmen": 0, "saldo": -kz["ausgaben"],
                           "sparquote_promille": None, "anzahl": 12, "buchungen": 12}]
    assert b["kategorien"] == [{"konto_id": k["essen"], "name": "Essen", "summe": kz["ausgaben"]}]
    assert len(b["buchungen"]) == 12 and b["serien"] == []
    assert c.get("/api/berichte/empfaenger", params={"empfaenger_id": 99_999}).status_code == 404


def test_geldfluss(haus):
    c, k = haus
    b = _b(c, "geldfluss")
    assert b["zeitraum"] == "monat" and b["monat"] == "2024-06" and b["einnahmen"] == 250_000 and b["ausgaben"] == 107_700
    assert [(q["name"], q["betrag"]) for q in b["quellen"]] == [("Lohn", 250_000)]
    assert [(z["name"], z["betrag"]) for z in b["ziele"]] == [
        ("Wohnen", 90_000), ("Leben", 9_200), ("Unkategorisiert", 8_500), ("Übrig", 250_000 - 107_700)]
    assert b["summe"] == 250_000 and sum(z["betrag"] for z in b["ziele"]) == sum(q["betrag"] for q in b["quellen"])
    jahr = _b(c, "geldfluss", jahr=2024)
    assert jahr["zeitraum"] == "jahr" and jahr["einnahmen"] == 1_500_000 and jahr["von"] == "2024-01-01"
    assert c.get("/api/berichte/geldfluss", params={"jahr": 2024, "monat": "2024-06"}).status_code == 422
    # mehr Ausgaben als Einnahmen: die Lücke kommt aus dem Bestand
    c.post("/api/buchungen/erfassen", json={"art": "ausgabe", "datum": "2024-06-14", "konto_id": k["giro"], "betrag": 200_000,
                                            "empfaenger_name": "Autohaus", "kategorie_id": k["leben"]})
    b = _b(c, "geldfluss")
    assert b["quellen"][-1]["art"] == "bestand" and b["quellen"][-1]["betrag"] == 307_700 - 250_000
    assert b["ziele"][0]["name"] == "Leben"


def test_qualitaet(haus):
    c, k = haus
    b = _b(c, "qualitaet")
    kz = b["kennzahlen"]
    assert kz["buchungen"] == 6 * 5 + 3 and kz["unkategorisiert"] == 2 and kz["unkategorisiert_summe"] == 8_500
    assert kz["kategorisiert_promille"] == 31 * 1000 // 33 and kz["ohne_empfaenger"] == 0 and kz["mit_empfaenger_promille"] == 1000
    assert kz["verdacht_offen"] == 0 and kz["nicht_abgestimmt"] == 2 and kz["ohne_tag"] == 31
    assert [x["betrag"] for x in b["unkategorisiert"]] == [7_000, 1_500] and b["ohne_empfaenger"] == []
    assert b["monate"][-1] == {"monat": "2024-06", "anzahl": 7, "unkategorisiert": 2, "ohne_empfaenger": 0}
    giro = [x for x in b["konten"] if x["name"] == "Giro"][0]
    assert giro["letzte_abstimmung"] is None and giro["letzte_buchung"] == "2024-06-12" and giro["seit_abstimmung"] == giro["buchungen"]


def test_tags(haus):
    c, k = haus
    b = _b(c, "tags")
    je = {t["name"]: t for t in b["tags"]}
    assert je["Urlaub"]["ausgaben"] == 67_000 and je["Urlaub"]["anzahl"] == 2 and je["Auto"]["ausgaben"] == 7_000
    assert je["Urlaub"]["erste"] == "2024-05-18" and je["Urlaub"]["letzte"] == "2024-06-08" and b["einzeln"] == []
    assert b["ohne_tag"]["anzahl"] == 31 and b["ausgaben"] == b["ohne_tag"]["ausgaben"] + 67_000      # Tankstelle nur einmal
    eins = _b(c, "tags", tag_id=k["urlaub"])["einzeln"]
    assert len(eins) == 1 and eins[0]["ausgaben"] == 67_000 and eins[0]["buchungen_anzahl"] == 2
    assert [e["empfaenger"]["name"] for e in eins[0]["empfaenger"]] == ["Reisebüro", "Tankstelle"]
    assert [x["name"] for x in eins[0]["kategorien"]] == ["Leben", "Unkategorisiert"]
    assert [m["ausgaben"] for m in eins[0]["monate"]][-2:] == [60_000, 7_000]
    zwei = _b(c, "tags", tag_id=[k["urlaub"], k["auto"]])["einzeln"]
    assert [t["name"] for t in zwei] == ["Urlaub", "Auto"]
    # ein Tag am Empfänger zählt für alle seine Buchungen
    eid = [e["empfaenger"]["id"] for e in _b(c, "empfaenger")["rangliste"] if e["empfaenger"]["name"] == "Stadtwerke"][0]
    assert c.patch(f"/api/empfaenger/{eid}", json={"tag_ids": [k["auto"]]}).status_code == 200
    assert {t["name"]: t for t in _b(c, "tags")["tags"]}["Auto"]["anzahl"] == 7
    assert c.get("/api/berichte/tags", params={"tag_id": 99_999}).json()["fehler"]["code"] == "referenz_unbekannt"


def test_leer_und_unbekannte_parameter(tmp_path):
    c = _client(tmp_path)
    for name in ("vertraege", "jahr", "vorschau", "vermoegen", "kategorien", "empfaenger", "geldfluss", "qualitaet", "tags"):
        assert c.get(f"/api/berichte/{name}").status_code == 200, name
        assert c.get(f"/api/berichte/{name}", params={"unsinn": "1"}).status_code == 422, name
