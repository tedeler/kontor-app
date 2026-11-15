"""Experimentelle statistische Analyse (D-145)."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(KontorConfig(
        datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2024, 6, 15))))


def _konto(c, name, art):
    r = c.post("/api/konten", json={"name": name, "art": art})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ausgabe(c, giro, kat, datum, betrag, name):
    r = c.post("/api/buchungen/erfassen", json={
        "art": "ausgabe", "datum": datum, "konto_id": giro, "betrag": betrag,
        "kategorie_id": kat, "empfaenger_name": name})
    assert r.status_code == 201, r.text


def _umbuchung(c, von, nach, datum, betrag):
    r = c.post("/api/buchungen/erfassen", json={
        "art": "umbuchung", "datum": datum, "konto_id": von, "gegenkonto_id": nach, "betrag": betrag,
        "empfaenger_name": "Sparrate"})
    assert r.status_code == 201, r.text


def test_regelmaessige_miete_und_moeglicher_strom(tmp_path):
    c = _client(tmp_path)
    giro = _konto(c, "Giro", "girokonto")
    miete = _konto(c, "Miete", "aufwand")
    strom = _konto(c, "Strom", "aufwand")
    for monat in range(1, 7):
        _ausgabe(c, giro, miete, f"2024-{monat:02d}-01", 80_000, "Vermieter")
    for monat in range(1, 4):
        _ausgabe(c, giro, strom, f"2024-{monat:02d}-05", 4_000, "Stadtwerke")
    a = c.get("/api/statistik", params={"konto_id": giro, "stichtag": "2024-06-15"})
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["experimentell"] is True
    reihen = {r["bezeichnung"]: r for r in body["reihen"]}
    assert reihen["Vermieter"]["status"] == "regelmaessig"
    assert reihen["Vermieter"]["rhythmus"] == "monatlich"
    assert reihen["Vermieter"]["jahresrate"] == 80_000 * 365 // reihen["Vermieter"]["abstand_median_tage"]
    assert reihen["Vermieter"]["kategorie"]["name"] == "Miete"
    assert reihen["Stadtwerke"]["status"] == "moeglich"
    assert reihen["Stadtwerke"]["grund"] == "zu_wenige"
    assert body["fixkosten"]["summe_jahresrate"] == reihen["Vermieter"]["jahresrate"]
    assert body["fixkosten"]["kategorien"][0]["kategorie"]["name"] == "Miete"
    assert body["fixkosten"]["summe_letzte_zwoelf_monate"] == 6 * 80_000


def test_zwei_betraege_derselben_gegenpartei(tmp_path):
    c = _client(tmp_path)
    giro = _konto(c, "Giro", "girokonto")
    kat = _konto(c, "Abos", "aufwand")
    for monat in range(1, 5):
        _ausgabe(c, giro, kat, f"2024-{monat:02d}-10", 999, "PayPal")
        _ausgabe(c, giro, kat, f"2024-{monat:02d}-11", 4_999, "PayPal")
    reihen = c.get("/api/statistik", params={"konto_id": giro, "stichtag": "2024-06-15"}).json()["reihen"]
    paypal = [r for r in reihen if r["bezeichnung"] == "PayPal"]
    assert len(paypal) == 2
    assert {r["betrag_median"] for r in paypal} == {-999, -4_999}
    assert all(r["status"] == "regelmaessig" for r in paypal)


def test_umbuchung_zaehlt_nicht_als_fixkosten(tmp_path):
    c = _client(tmp_path)
    giro = _konto(c, "Giro", "girokonto")
    tag = _konto(c, "Tagesgeld", "sparkonto")
    for monat in range(1, 5):
        _umbuchung(c, giro, tag, f"2024-{monat:02d}-03", 20_000)
    body = c.get("/api/statistik", params={"konto_id": giro, "stichtag": "2024-06-15"}).json()
    assert body["ausgeschlossen"]["umbuchungen"] == 4
    assert body["reihen"] == []
    assert body["fixkosten"]["summe_jahresrate"] == 0


def test_rauschen_und_ausreisser(tmp_path):
    c = _client(tmp_path)
    giro = _konto(c, "Giro", "girokonto")
    kat = _konto(c, "Lebensmittel", "aufwand")
    klein = [(1, 3, 1200), (1, 8, 1800), (1, 21, 900), (2, 4, 2500), (2, 18, 1400), (3, 2, 2200)]
    for monat, tag, betrag in klein:
        _ausgabe(c, giro, kat, f"2024-{monat:02d}-{tag:02d}", betrag, "Markt")
    _ausgabe(c, giro, kat, "2024-03-20", 80_000, "Werkstatt")
    body = c.get("/api/statistik", params={"konto_id": giro, "stichtag": "2024-06-15"}).json()
    assert body["reihen"] == []
    assert body["rauschen"][0]["kategorie"]["name"] == "Lebensmittel"
    treffer = [u for u in body["ungewoehnlich"] if u["grund"] == "rauschen" and u["betrag"] == -80_000]
    assert len(treffer) == 1
    assert treffer[0]["z_hundertstel"] >= 350


def test_aufwandskonto_und_unbekannt(tmp_path):
    c = _client(tmp_path)
    kat = _konto(c, "Miete", "aufwand")
    assert c.get("/api/statistik", params={"konto_id": kat}).status_code == 422
    assert c.get("/api/statistik", params={"konto_id": 99999}).status_code == 404
    assert c.get("/api/statistik").status_code == 422
    assert c.get("/api/statistik", params={"konto_id": 1, "sonst": "x"}).status_code == 422
