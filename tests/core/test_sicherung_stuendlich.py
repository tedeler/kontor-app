"""Core-Tests zum Feature „sicherung-stuendlich“ (spec/api/sicherungspunkte.md, D-302).

- Ein stündlicher Lauf legt nur bei tatsächlicher Änderung einen Punkt an; der erste ist ein Anker, die weiteren
  sind kleine Differenzen.
- Jeder Punkt ist herstellbar und als eigenständige Sicherungsdatei herunterladbar; Zurück und Vorwärts über
  Wechsel; vor jedem Einspielen wird der bestehende Stand gesichert.
- Ausdünnen behält Stunden-, Tages-, Wochen- und Monatspunkte; alle behaltenen bleiben herstellbar.
- Das Änderungsprotokoll wird nach einem gesicherten Lauf auf die letzte Stunde gekürzt.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from kontor import sicherungspunkte as sp
from kontor.app import create_app
from kontor.config import KontorConfig

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


@pytest.fixture
def umgebung(tmp_path):
    config = KontorConfig(datenbank=tmp_path / "kontor.sqlite3", sicherung_verzeichnis=tmp_path / "sicherungen")
    c = TestClient(create_app(config))
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()["id"]

    def buchen(betrag=1234, zweck="Einkauf"):
        r = c.post("/api/buchungen", json={"datum": "2026-11-01", "verwendungszweck": zweck, "splits": [
            {"konto_id": giro, "betrag": -betrag}, {"konto_id": kat, "betrag": betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return config, c, buchen


def inhalt(c) -> str:
    """Inhaltsprüfsumme des aktuellen Bestands (sicherung.md 3.3)."""
    r = c.get("/api/sicherung")
    assert r.status_code == 200
    import json
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return json.loads(z.read("manifest.json"))["inhalt_sha256"]


def punkte(c) -> dict:
    r = c.get("/api/sicherung/punkte")
    assert r.status_code == 200, r.text
    return r.json()


def test_nur_bei_aenderung_ein_punkt_erster_ist_anker(umgebung):
    config, c, buchen = umgebung
    buchen()
    a = sp.stunde(config, jetzt=T0)
    assert a["neu"] is True and a["punkt"]["anker"] is True and a["punkt"]["marken"] == ["stuendlich"]
    assert sp.stunde(config, jetzt=T0 + dt.timedelta(hours=1))["neu"] is False
    # angelegt und wieder gelöscht: kein neuer Punkt (nur Begleitzustand geändert)
    bid = buchen(999)
    assert c.delete(f"/api/buchungen/{bid}").status_code in (200, 204)
    assert sp.stunde(config, jetzt=T0 + dt.timedelta(hours=2))["neu"] is False
    buchen(500)
    b = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=3))
    assert b["neu"] is True and b["punkt"]["anker"] is False and b["punkt"]["basis"] == a["punkt"]["kennung"]
    assert b["punkt"]["aenderungen"]["buchung"]["neu"] == 1
    assert b["punkt"]["groesse"] < a["punkt"]["groesse"]
    p = punkte(c)
    assert [x["kennung"] for x in p["punkte"]] == [b["punkt"]["kennung"], a["punkt"]["kennung"]]
    assert p["gesamt"]["anzahl"] == 2
    assert p["gesamt"]["groesse"] == a["punkt"]["groesse"] + b["punkt"]["groesse"]
    assert p["bezugspunkt"] == b["punkt"]["kennung"] and p["unveraendert"] is True
    assert p["punkte"][0]["groesse_herstellen"] == p["gesamt"]["groesse"]
    assert p["zuletzt_geprueft"] is not None


def test_punkt_von_hand_und_bestehender_stand(umgebung):
    config, c, buchen = umgebung
    buchen()
    r = c.post("/api/sicherung/punkte", json={"name": "Vor dem Aufräumen"})
    assert r.status_code == 201, r.text
    k = r.json()["kennung"]
    assert r.json()["name"] == "Vor dem Aufräumen" and r.json()["marken"] == ["von_hand"]
    r = c.post("/api/sicherung/punkte", json={})
    assert r.status_code == 200 and r.json()["neu"] is False and r.json()["kennung"] == k
    r = c.patch(f"/api/sicherung/punkte/{k}", json={"angeheftet": True, "name": None})
    assert r.status_code == 200 and r.json()["angeheftet"] is True and r.json()["name"] is None
    assert c.patch(f"/api/sicherung/punkte/{k}", json={"farbe": 1}).status_code == 422


def test_beschaedigter_punkt_wird_erkannt_und_neuer_anker(umgebung):
    config, c, buchen = umgebung
    buchen(1)
    a = sp.stunde(config, jetzt=T0)["punkt"]
    buchen(2)
    b = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=1))["punkt"]
    sp.datei_pfad(config, a["kennung"]).write_bytes(b"kaputt")
    r = c.post(f"/api/sicherung/punkte/{b['kennung']}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "punkt_nicht_herstellbar"
    assert c.get(f"/api/sicherung/punkte/{b['kennung']}/datei").status_code == 409
    buchen(3)
    neu = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=2))["punkt"]
    assert neu["anker"] is True


def test_protokoll_wird_nach_gesichertem_lauf_gekuerzt(umgebung):
    config, c, buchen = umgebung
    buchen(1)
    jetzt = dt.datetime.now(UTC)
    sp.stunde(config, jetzt=jetzt + dt.timedelta(hours=2))
    r = c.get("/api/aenderungen").json()
    assert r["eintraege"] == [] and r["gekuerzt_bis"] is not None
    # ohne gesicherten Stand wird nicht gekürzt
    buchen(2)
    c2 = KontorConfig(datenbank=config.datenbank, sicherung_verzeichnis=config.sicherung_verzeichnis,
                      protokoll_stunden=0)
    sp.stunde(c2, jetzt=jetzt + dt.timedelta(hours=4))
    assert len(c.get("/api/aenderungen").json()["eintraege"]) == 1


def test_einstellungen_sind_teil_der_sicherung(umgebung):
    config, c, buchen = umgebung
    assert c.put("/api/lernmodell/einstellungen", json={"schwelle_promille": 700}).status_code == 200
    datei = c.get("/api/sicherung").content
    assert c.put("/api/lernmodell/einstellungen", json={"schwelle_promille": 900}).status_code == 200
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 200, r.text
    assert c.get("/api/lernmodell/einstellungen").json()["schwelle_promille"] == 700
    import json
    with zipfile.ZipFile(io.BytesIO(datei)) as z:
        assert json.loads(z.read("manifest.json"))["schemaversion"] == 11
