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


def test_jeder_punkt_als_eigenstaendige_datei(umgebung, tmp_path):
    config, c, buchen = umgebung
    staende = []
    for i in range(3):
        buchen(100 + i)
        k = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=i))["punkt"]["kennung"]
        staende.append((k, inhalt(c)))
    for k, soll in staende:
        r = c.get(f"/api/sicherung/punkte/{k}/datei")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        # in einer frischen Instanz einspielbar und gleich dem damaligen Stand
        frisch = TestClient(create_app(KontorConfig(datenbank=tmp_path / f"neu-{k}.sqlite3",
                                                    sicherung_verzeichnis=tmp_path / f"s-{k}")))
        e = frisch.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                        files={"datei": ("s.zip", r.content, "application/zip")})
        assert e.status_code == 200, e.text
        assert inhalt(frisch) == soll
    assert c.get("/api/sicherung/punkte/unbekannt/datei").status_code == 404


def test_zurueck_und_vorwaerts(umgebung):
    config, c, buchen = umgebung
    buchen(1)
    a = sp.stunde(config, jetzt=T0)["punkt"]["kennung"]
    stand_a = inhalt(c)
    buchen(2)
    b = sp.stunde(config, jetzt=T0 + dt.timedelta(hours=1))["punkt"]["kennung"]
    buchen(3)   # noch nicht gesichert
    stand_jetzt = inhalt(c)
    assert c.post(f"/api/sicherung/punkte/{a}/wechseln").status_code == 409   # Bestätigung fehlt
    r = c.post(f"/api/sicherung/punkte/{a}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 200, r.text
    vorher = r.json()["vorher"]
    assert vorher not in (a, b) and r.json()["ziel"] == a
    assert inhalt(c) == stand_a
    p = punkte(c)
    assert p["bezugspunkt"] == a and p["unveraendert"] is True
    vp = next(x for x in p["punkte"] if x["kennung"] == vorher)
    assert "vor_wiederherstellung" in vp["marken"]
    # Vorwärts auf den ungesicherten Stand vor dem Wechsel
    r = c.post(f"/api/sicherung/punkte/{vorher}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 200, r.text
    assert inhalt(c) == stand_jetzt
    # derselbe Stand: nichts zu tun; Stand vor dem Wechsel war schon gesichert (Marke am bestehenden Punkt)
    r = c.post(f"/api/sicherung/punkte/{vorher}/wechseln", params={"bestaetigt": "true"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "stand_unveraendert"
    p = punkte(c)["punkte"]
    assert len(p) == 3   # a, b, vorher; beim Vorwärts entsprach der Stand a, a erhielt nur die Marke
    assert "vor_wiederherstellung" in next(x for x in p if x["kennung"] == a)["marken"]
    assert c.post("/api/sicherung/punkte/xyz/wechseln", params={"bestaetigt": "true"}).status_code == 404


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


def test_einspielen_sichert_vorher_und_scheitert_ohne_sicherung(umgebung, tmp_path):
    config, c, buchen = umgebung
    buchen(1)
    datei = c.get("/api/sicherung").content
    buchen(2)
    stand = inhalt(c)
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 200, r.text
    p = punkte(c)
    marken = {m for x in p["punkte"] for m in x["marken"]}
    assert {"vor_wiederherstellung", "aus_datei"} <= marken
    vor = next(x for x in p["punkte"] if "vor_wiederherstellung" in x["marken"])
    assert c.post(f"/api/sicherung/punkte/{vor['kennung']}/wechseln", params={"bestaetigt": "true"}).status_code == 200
    assert inhalt(c) == stand
    # Ablage nicht beschreibbar: nichts wird gelöscht
    kaputt = tmp_path / "blockiert"
    kaputt.write_text("keine Ablage")
    c2 = TestClient(create_app(KontorConfig(datenbank=config.datenbank, sicherung_verzeichnis=kaputt)))
    r = c2.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "sicherung_vorher_fehlgeschlagen"
    assert inhalt(c2) == stand


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


def test_ausduennen_behaelt_stufen_und_alles_bleibt_herstellbar(umgebung):
    config, c, buchen = umgebung
    import dataclasses
    config = dataclasses.replace(config, sicherung_tage=8)   # kleine Stufen halten den Test schnell
    t = dt.datetime(2026, 10, 10, 20, 0, tzinfo=UTC)
    zeiten = [t + dt.timedelta(days=tag) for tag in range(20)]          # ein Punkt je Tag
    zeiten += [zeiten[-1] + dt.timedelta(hours=h) for h in (2, 4, 6)]   # und drei in den letzten Stunden
    for i, zeit in enumerate(zeiten):
        buchen(100 + i)
        sp.stunde(config, jetzt=zeit, ausduennen=False)
    jetzt = zeiten[-1]
    sp.ausduennen(config, jetzt=jetzt)
    p = punkte(c)["punkte"]
    behalten = sorted(dt.datetime.fromisoformat(x["zeitpunkt"].replace("Z", "+00:00")) for x in p)
    stunden = [z for z in zeiten if jetzt - z <= dt.timedelta(hours=48)]
    tage = [z for z in zeiten if dt.timedelta(hours=48) < jetzt - z <= dt.timedelta(days=8)]
    alt = [z for z in zeiten if jetzt - z > dt.timedelta(days=8)]
    assert all(z in behalten for z in stunden + tage)
    wochen = {tuple(z.isocalendar())[:2] for z in alt}
    assert sorted(z for z in behalten if z in alt) == sorted(max(z for z in alt if tuple(z.isocalendar())[:2] == w)
                                                           for w in wochen)
    for x in p:
        assert sp.herstellen_pruefen(config, x["kennung"]) is True
    # Ketten bleiben kurz: höchstens Anker → Tages-/Wochenpunkt → Stundenpunkte
    assert max(sp.kettenlaenge(config, x["kennung"]) for x in p) <= 2 + len(stunden)
    assert sum(1 for x in p if x["anker"]) <= 2   # je Monat höchstens ein Anker
    # angeheftete Punkte bleiben auch nach Ablauf aller Stufen
    k = p[-1]["kennung"]
    assert c.patch(f"/api/sicherung/punkte/{k}", json={"angeheftet": True}).status_code == 200
    sp.ausduennen(dataclasses.replace(config, sicherung_wochen=0, sicherung_monate=0), jetzt=jetzt)
    assert k in {x["kennung"] for x in punkte(c)["punkte"]}
    assert sp.herstellen_pruefen(config, k) is True


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
