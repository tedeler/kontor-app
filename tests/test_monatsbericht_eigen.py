"""Monatsbericht (Feature monatsbericht, D-205): Ausgaben eines Monats rein statistisch."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def _client(tmp_path, heute=dt.date(2024, 6, 15)) -> TestClient:
    return TestClient(create_app(KontorConfig(
        datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=heute)))


def _konto(c, name, art):
    r = c.post("/api/konten", json={"name": name, "art": art})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _buchen(c, art, konto, datum, betrag, name, **extra):
    r = c.post("/api/buchungen/erfassen", json={
        "art": art, "datum": datum, "konto_id": konto, "betrag": betrag, "empfaenger_name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _bericht(c, **params):
    r = c.get("/api/berichte/monat", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _haushalt(c):
    """Sechs Monate Miete und Einkäufe, dazu Gehalt; Juni 2024 läuft (heute 15.06.)."""
    giro = _konto(c, "Giro", "girokonto")
    spar = _konto(c, "Sparbuch", "sparkonto")
    wohnen = _konto(c, "Wohnen", "aufwand")
    essen = _konto(c, "Essen", "aufwand")
    lohn = _konto(c, "Lohn", "ertrag")
    for monat in range(1, 7):
        _buchen(c, "ausgabe", giro, f"2024-{monat:02d}-01", 80_000, "Vermieter", kategorie_id=wohnen)
        _buchen(c, "einnahme", giro, f"2024-{monat:02d}-02", 250_000, "Arbeitgeber", kategorie_id=lohn)
        for tag in (5, 12):
            _buchen(c, "ausgabe", giro, f"2024-{monat:02d}-{tag:02d}", 4_000 + monat * 100, "Supermarkt",
                    kategorie_id=essen)
    return {"giro": giro, "spar": spar, "wohnen": wohnen, "essen": essen, "lohn": lohn}


def test_kennzahlen_und_umbuchung(tmp_path):
    c = _client(tmp_path)
    k = _haushalt(c)
    _buchen(c, "umbuchung", k["giro"], "2024-06-03", 50_000, "Sparrate", gegenkonto_id=k["spar"])
    b = _bericht(c)
    assert b["monat"] == "2024-06" and b["laufend"] is True and b["stichtag"] == "2024-06-15"
    kz = b["kennzahlen"]
    assert kz["ausgaben"] == 80_000 + 2 * 4_600
    assert kz["einnahmen"] == 250_000
    assert kz["saldo"] == 250_000 - kz["ausgaben"]
    assert kz["sparquote_promille"] == kz["saldo"] * 1000 // 250_000
    assert kz["anzahl"] == 3 and kz["median"] == 4_600
    assert kz["pro_tag"] == kz["ausgaben"] // 15
    assert kz["vormonat"] == 80_000 + 2 * 4_500
    assert b["ausgeschlossen"]["umbuchungen"] == 1
    assert {x["id"] for x in b["konten"]} == {k["giro"], k["spar"]}
    assert b["erster_monat"] == "2024-01" and b["letzter_monat"] == "2024-06"


def test_verlauf_und_monatsvergleich(tmp_path):
    c = _client(tmp_path)
    _haushalt(c)
    b = _bericht(c)
    v = b["verlauf"]
    assert v["tage"] == 30 and v["bis_tag"] == 15 and len(v["kumuliert"]) == 15
    assert v["kumuliert"][0] == 80_000 and v["kumuliert"][4] == 84_600 and v["kumuliert"][-1] == 89_200
    assert len(v["vormonat"]) == 30 and v["vormonat"][-1] == 89_000
    assert v["durchschnitt_monate"] == 5 and len(v["durchschnitt"]) == 30
    assert v["durchschnitt"][-1] == sum(80_000 + 2 * (4_000 + m * 100) for m in range(1, 6)) // 5
    assert [m["monat"] for m in b["monate"]][-1] == "2024-06" and len(b["monate"]) == 13
    assert b["monate"][-2]["ausgaben"] == 89_000
    assert b["monate"][0]["anzahl"] == 0


def test_fix_variabel_und_prognose(tmp_path):
    c = _client(tmp_path)
    _haushalt(c)
    b = _bericht(c)
    fv = b["fix_variabel"]
    assert fv["fix"] == 80_000 and fv["fix_anzahl"] == 1
    assert fv["variabel"] == 2 * 4_600 and fv["variabel_anzahl"] == 2
    fix = [x for x in b["buchungen"] if x["fix"]]
    assert [x["empfaenger"]["name"] for x in fix] == ["Vermieter"]
    p = b["prognose"]
    assert p["resttage"] == 15 and p["grundlage"] == "letzte_90_tage"
    assert p["summe"] == b["kennzahlen"]["ausgaben"] + p["fix_offen"] + p["variabel_pro_tag"] * 15
    # abgeschlossener Monat: keine Hochrechnung, Verlauf bis zum Monatsende
    mai = _bericht(c, monat="2024-05")
    assert mai["prognose"] is None and mai["laufend"] is False and mai["verlauf"]["bis_tag"] == 31
    assert mai["fix_variabel"]["erwartet"] == []


def test_erwartete_feste_zahlung(tmp_path):
    c = _client(tmp_path, heute=dt.date(2024, 7, 10))
    k = _haushalt(c)
    for monat in range(1, 7):
        _buchen(c, "ausgabe", k["giro"], f"2024-{monat:02d}-20", 3_000, "Stadtwerke", kategorie_id=k["wohnen"])
    b = _bericht(c)
    namen = {e["empfaenger"]["name"]: e for e in b["fix_variabel"]["erwartet"]}
    assert namen["Stadtwerke"]["faellig"] == "2024-07-20" and namen["Stadtwerke"]["betrag"] == 3_000
    assert b["prognose"]["fix_offen"] == sum(e["betrag"] for e in b["fix_variabel"]["erwartet"])
    ausgeblieben = [s for s in b["auffaellig"]["serien"] if s["art"] == "ausgeblieben"]
    assert [s["empfaenger"]["name"] for s in ausgeblieben] == ["Vermieter"]


def test_groessenklassen_top_und_empfaenger(tmp_path):
    c = _client(tmp_path)
    k = _haushalt(c)
    _buchen(c, "ausgabe", k["giro"], "2024-06-10", 500, "Bäcker", kategorie_id=k["essen"])
    _buchen(c, "ausgabe", k["giro"], "2024-06-11", 120_000, "Möbelhaus", kategorie_id=k["wohnen"])
    b = _bericht(c)
    kl = b["groessenklassen"]
    assert [x["anzahl"] for x in kl] == [1, 2, 0, 1, 1]
    assert [x["summe"] for x in kl] == [500, 9_200, 0, 80_000, 120_000]
    assert kl[0]["ab"] == 0 and kl[0]["unter"] == 1_000 and kl[-1]["unter"] is None
    top = b["top_buchungen"]
    assert [x["betrag"] for x in top["eintraege"]] == [120_000, 80_000, 4_600, 4_600, 500]
    assert top["gesamt"] == top["summe"] == 209_700
    emp = b["top_empfaenger"]
    assert [e["empfaenger"]["name"] for e in emp] == ["Möbelhaus", "Vermieter", "Supermarkt", "Bäcker"]
    assert emp[2]["anzahl"] == 2 and emp[2]["summe"] == 9_200
    assert emp[1]["ueblich"] == 80_000 and emp[0]["ueblich"] == 0
    neue = b["auffaellig"]["neue_empfaenger"]
    assert [e["empfaenger"]["name"] for e in neue] == ["Möbelhaus", "Bäcker"]


def test_ausreisser_und_geaenderte_serie(tmp_path):
    c = _client(tmp_path)
    k = _haushalt(c)
    _buchen(c, "ausgabe", k["giro"], "2024-06-14", 30_000, "Supermarkt", kategorie_id=k["essen"])
    b = _bericht(c)
    aus = b["auffaellig"]["ausreisser"]
    assert len(aus) == 1 and aus[0]["buchung"]["betrag"] == 30_000
    assert aus[0]["ueblich"] == 4_300 and aus[0]["basis_anzahl"] == 10
    # Miete steigt im Juli
    c2 = _client(tmp_path / "zwei", heute=dt.date(2024, 7, 20))
    k2 = _haushalt(c2)
    _buchen(c2, "ausgabe", k2["giro"], "2024-07-01", 85_000, "Vermieter", kategorie_id=k2["wohnen"])
    serien = _bericht(c2)["auffaellig"]["serien"]
    geaendert = [s for s in serien if s["art"] == "betrag_geaendert"]
    assert len(geaendert) == 1 and geaendert[0]["betrag"] == 85_000 and geaendert[0]["vorher"] == 80_000


def test_erstattung_mindert_ausgaben(tmp_path):
    c = _client(tmp_path)
    k = _haushalt(c)
    _buchen(c, "einnahme", k["giro"], "2024-06-08", 2_000, "Supermarkt", kategorie_id=k["essen"])
    b = _bericht(c)
    kz = b["kennzahlen"]
    assert kz["erstattungen"] == 2_000 and kz["ausgaben_brutto"] == 89_200 and kz["ausgaben"] == 87_200
    assert kz["einnahmen"] == 250_000
    assert b["verlauf"]["kumuliert"][7] == 84_600 - 2_000
    assert [x["art"] for x in b["buchungen"] if x["datum"] == "2024-06-08"] == ["erstattung"]


def test_kalender_wochentage_kontostand(tmp_path):
    c = _client(tmp_path)
    k = _haushalt(c)
    b = _bericht(c, konto_id=k["giro"])
    kal = b["kalender"]
    assert len(kal) == 30 and kal[0] == {"datum": "2024-06-01", "wochentag": 5, "summe": 80_000, "anzahl": 1}
    assert sum(x["summe"] for x in kal) == b["kennzahlen"]["ausgaben_brutto"]
    wt = {w["name"]: w for w in b["wochentage"]}
    assert wt["Sa"]["summe"] == 80_000 and wt["Sa"]["tage"] == 3 and wt["Mi"]["summe"] == 9_200
    ks = b["kontostand"]
    vorher = 5 * (250_000 - 80_000) - sum(2 * (4_000 + m * 100) for m in range(1, 6))
    assert ks["anfang"] == vorher and len(ks["werte"]) == 15
    assert ks["werte"][0] == vorher - 80_000 and ks["tiefststand"] == {"datum": "2024-06-01", "betrag": vorher - 80_000}
    assert ks["ende"] == vorher - 80_000 + 250_000 - 9_200
    assert [x["id"] for x in b["konten"]] == [k["giro"]]


def test_leer_zukunft_und_fehler(tmp_path):
    c = _client(tmp_path)
    leer = _bericht(c)
    assert leer["kennzahlen"]["ausgaben"] == 0 and leer["buchungen"] == [] and leer["erster_monat"] is None
    assert leer["verlauf"]["vormonat"] is None and leer["verlauf"]["durchschnitt"] is None
    k = _haushalt(c)
    zukunft = _bericht(c, monat="2024-08")
    assert zukunft["zukunft"] is True and zukunft["verlauf"]["kumuliert"] == [] and zukunft["prognose"] is None
    for falsch in ("2024-13", "2024", "24-06", "2024-6", "abcd-ef"):
        r = c.get("/api/berichte/monat", params={"monat": falsch})
        assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung", falsch
    assert c.get("/api/berichte/monat", params={"konto_id": 99_999}).json()["fehler"]["code"] == "referenz_unbekannt"
    assert c.get("/api/berichte/monat", params={"konto_id": k["essen"]}).json()["fehler"]["code"] == "konto_ungueltig"
    assert c.get("/api/berichte/monat", params={"jahr": "2024"}).status_code == 422
