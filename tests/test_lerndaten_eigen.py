"""Mock-Lerndaten (D-181, D-184): 3000 Buchungen nach echten Kontoauszugsmustern, Lernmodell und automatische Regeln."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kontor import mock_lerndaten
from kontor.app import create_app
from kontor.config import KontorConfig


def test_eingecheckte_datei_entspricht_dem_generator():
    assert mock_lerndaten.DATEI.read_text(encoding="utf-8") == mock_lerndaten.als_csv(mock_lerndaten.erzeugen())
    b = mock_lerndaten.lesen()
    assert len(b) == mock_lerndaten.ANZAHL
    assert sum(x["teil"] == "pruefung" for x in b) == mock_lerndaten.ANZAHL // 5


def test_nur_im_mock_modus_und_nur_in_leeren_bestand(client, tmp_path):
    assert client.post("/api/mock/lerndaten").json()["fehler"]["code"] == "nur_mock_modus"
    m = TestClient(create_app(KontorConfig(datenbank=tmp_path / "m.sqlite3", mock_modus=True)))
    r = m.post("/api/mock/lerndaten")
    assert r.status_code == 200, r.text
    assert r.json()["buchungen"] == 3001 and r.json()["pruefbuchungen"] == 600
    assert m.post("/api/mock/lerndaten").json()["fehler"]["code"] == "bestand_nicht_leer"
    a = m.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["aktion"] == "mock_lerndaten" and a["quelle"] == "import"
    assert m.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    assert m.get("/api/buchungen").json()["gesamt"] == 0


def test_genauigkeit_mit_automatischen_regeln(tmp_path):
    b = mock_lerndaten.lesen()
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, regeln_automatisch=True)))
    assert c.post("/api/mock/lerndaten").status_code == 200
    kat = {k["id"]: k["name"] for k in c.get("/api/konten").json()}
    ids = {x["nr"]: x["nr"] + 1 for x in b}  # frischer Bestand: Anfangsbestand hat ID 1
    assert c.get(f"/api/buchungen/{ids[1]}").json()["verwendungszweck"] == b[0]["verwendungszweck"]
    pruef = [x for x in b if x["teil"] == "pruefung" and x["wahr"] in mock_lerndaten.KATEGORIEN]
    auto = {r["name"] for r in c.get("/api/regeln").json() if r.get("automatisch")}
    assert "REWE Markt GmbH" in auto
    assert not auto & {"Shell Station Hauptstr. 12", "Amazon Payments Europe S.C.A.", "PayPal Europe S.a.r.l. et Cie S.C.A"}
    c.post("/api/regeln/anwenden", json={"nur_unkategorisiert": True})
    c.post("/api/lernmodell/anwenden", json={})
    vorschlaege = richtig = 0
    for x in pruef:
        v = c.get(f"/api/buchungen/{ids[x['nr']]}").json()["vorschlag"]
        if v:
            vorschlaege += 1
            richtig += kat[v["kategorie_id"]] == x["wahr"]
    # Messung 2026-11-16: nur Lernmodell 99,2 % bei 89,0 % Abdeckung; mit Regeln 99,2 % bei 89,5 %
    assert richtig * 1000 >= vorschlaege * 990
    assert vorschlaege * 1000 >= len(pruef) * 890
