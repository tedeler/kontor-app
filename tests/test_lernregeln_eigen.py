"""Eigene Entwicklungstests zum Feature „lernmodell-transparenz“: automatisch angelegte Regeln (D-179)."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig


@pytest.fixture
def auto(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "kontor.sqlite3", regeln_automatisch=True)))
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = {n: c.post("/api/konten", json={"name": n, "art": "aufwand"}).json()["id"]
           for n in ("Lebensmittel", "Drogerie", "Unklar")}
    emp = {n: c.post("/api/empfaenger", json={"name": n}).json()["id"] for n in ("Frischekorb", "Glanz")}
    heute = dt.date.today()

    def buchen(empf, kategorie, tage_her=10, betrag=-1234):
        r = c.post("/api/buchungen", json={
            "datum": (heute - dt.timedelta(days=tage_her)).isoformat(), "empfaenger_id": emp[empf],
            "verwendungszweck": "Kartenzahlung",
            "splits": [{"konto_id": g, "betrag": betrag}, {"konto_id": kat[kategorie], "betrag": -betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return c, buchen, kat, emp


def automatische(c):
    return [r for r in c.get("/api/regeln").json() if r.get("automatisch")]


def test_fuenfte_gleiche_zuordnung_legt_regel_an(auto):
    c, buchen, kat, emp = auto
    for i in range(4):
        buchen("Frischekorb", "Lebensmittel", 30 + i)
    assert automatische(c) == []
    buchen("Frischekorb", "Lebensmittel", 5)
    (r,) = automatische(c)
    assert r["kategorie_id"] == kat["Lebensmittel"] and r["empfaenger_id"] == emp["Frischekorb"]
    assert r["bedingungen"] == [{"feld": "empfaenger", "operator": "gleich", "wert": "Frischekorb"}]
    assert r["name"] == "Frischekorb" and r["aktiv"]
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["quelle"] == "lernmodell" and a["aktion"] == "regel_automatisch"
    assert "Frischekorb → Lebensmittel" in a["beschreibung"]


def test_abweichung_im_letzten_jahr_verhindert_regel(auto):
    c, buchen, _kat, _emp = auto
    buchen("Glanz", "Lebensmittel", 100)
    for i in range(6):
        buchen("Glanz", "Drogerie", 20 + i)
    assert automatische(c) == []


def test_alte_abweichung_stoert_nicht(auto):
    c, buchen, kat, _emp = auto
    buchen("Glanz", "Lebensmittel", 500)  # alter Fehlgriff: 1 von 21, Anteil Drogerie über 95 %
    for i in range(20):
        buchen("Glanz", "Drogerie", 20 + i)
    (r,) = automatische(c)
    assert r["kategorie_id"] == kat["Drogerie"]


def test_loeschen_ohne_sperre_rueckgaengig_bringt_regel_zurueck(auto):
    """D-308: Das Löschen sperrt den Empfänger nicht mehr (vorher D-179: Sperre)."""
    c, buchen, _kat, emp = auto
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    (r,) = automatische(c)
    assert c.delete(f"/api/regeln/{r['id']}").status_code in (200, 204)
    assert automatische(c) == []
    assert "lernregel_gesperrt" not in c.get(f"/api/empfaenger/{emp['Frischekorb']}").json()
    # Rückgängig des Löschens bringt Regel und Vermerk zurück
    loeschung = [a for a in c.get("/api/aenderungen").json()["eintraege"] if a["aktion"] == "regel_loeschen"][0]
    assert c.post(f"/api/aenderungen/{loeschung['id']}/rueckgaengig").status_code == 200
    (r2,) = automatische(c)
    assert r2["id"] == r["id"] and r2["empfaenger_id"] == emp["Frischekorb"]


def test_rueckgaengig_entfernt_automatische_regel(auto):
    c, buchen, _kat, _emp = auto
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["aktion"] == "regel_automatisch"
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    assert automatische(c) == []


def test_keine_regel_bei_vorhandener_regel(auto):
    c, buchen, kat, emp = auto
    c.post("/api/regeln", json={"name": "Frisch", "kategorie_id": kat["Lebensmittel"],
                                "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "frisch"}]})
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
    assert automatische(c) == []


def test_ohne_einstellung_keine_automatischen_regeln(client):
    g = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    k = client.post("/api/konten", json={"name": "L", "art": "aufwand"}).json()["id"]
    e = client.post("/api/empfaenger", json={"name": "X"}).json()["id"]
    for i in range(6):
        client.post("/api/buchungen", json={"datum": dt.date.today().isoformat(), "empfaenger_id": e,
                                            "splits": [{"konto_id": g, "betrag": -100}, {"konto_id": k, "betrag": 100}]})
    assert client.get("/api/regeln").json() == []


def test_sicherung_enthaelt_vermerk_und_deaktivierte_regel(auto, tmp_path):
    c, buchen, _kat, emp = auto
    for i in range(5):
        buchen("Frischekorb", "Lebensmittel", 10 + i)
        buchen("Glanz", "Drogerie", 10 + i)
    regeln_vorher = automatische(c)
    glanz = [r for r in regeln_vorher if r["empfaenger_id"] == emp["Glanz"]][0]
    c.patch(f"/api/regeln/{glanz['id']}", json={"aktiv": False})
    datei = c.get("/api/sicherung")
    assert datei.status_code == 200, datei.text
    z = TestClient(create_app(KontorConfig(datenbank=tmp_path / "ziel.sqlite3", regeln_automatisch=True)))
    r = z.post("/api/sicherung/einspielen?bestaetigt=true", files={"datei": ("s.zip", datei.content, "application/zip")})
    assert r.status_code == 200, r.text
    assert sorted((x["empfaenger_id"], x["aktiv"]) for x in automatische(z)) == sorted(
        [(emp["Frischekorb"], True), (emp["Glanz"], False)])
    # Die deaktivierte Regel ist mitgekommen: weitere Drogerie-Buchungen legen keine neue Regel an (D-308)
    gid = [k["id"] for k in z.get("/api/konten").json() if k["name"] == "Giro"][0]
    did = [k["id"] for k in z.get("/api/konten").json() if k["name"] == "Drogerie"][0]
    z.post("/api/buchungen", json={"datum": dt.date.today().isoformat(), "empfaenger_id": emp["Glanz"],
                                   "splits": [{"konto_id": gid, "betrag": -5}, {"konto_id": did, "betrag": 5}]})
    assert len(automatische(z)) == 2


def test_empfaenger_mit_zwei_kategorien_bekommt_keine_regel(auto):
    c, buchen, _kat, _emp = auto
    buchen("Glanz", "Lebensmittel", 500)  # 1 von 16: Anteil Drogerie bleibt unter 95 %
    for i in range(12):
        buchen("Glanz", "Drogerie", 400 + 7 * i)
    for i in range(3):
        buchen("Glanz", "Drogerie", 10 + i)
    assert automatische(c) == []
