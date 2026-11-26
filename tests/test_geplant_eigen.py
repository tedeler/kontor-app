"""Eigene Tests zu geplanten Zahlungen mit Wiederholung (D-238): von Hand angelegte erwartete Zahlungen, die sich
wiederholen, in die Vorschau einfließen und sich mit der passenden Bankbuchung erledigen. Nur synthetische Daten."""
from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from kontor import abgleich, db, erwartung
from kontor.app import create_app
from kontor.config import KontorConfig

HEUTE = "2024-06-30"      # Mock-Uhr


@pytest.fixture
def umgebung(tmp_path):
    config = KontorConfig(datenbank=tmp_path / "k.sqlite3", planer_starten=False, mail_abgleich=True)
    with TestClient(create_app(config)) as c:
        giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
        kat = c.post("/api/konten", json={"name": "Versicherung", "art": "aufwand"}).json()["id"]
        yield c, config, giro, kat


def ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json() if r.content else None


def _buchen(c, giro, kat, datum, betrag, zweck):
    return ok(c.post("/api/buchungen", json={"datum": datum, "verwendungszweck": zweck, "splits": [
        {"konto_id": giro, "betrag": betrag}, {"konto_id": kat, "betrag": -betrag}]}), 201)["id"]


def _offen(c):
    return ok(c.get("/api/erwartungen"))["eintraege"]


def test_naechstes_datum_haelt_den_tag_im_monat():
    assert erwartung.naechstes_datum("2024-01-31", "monatlich", 31) == "2024-02-29"
    assert erwartung.naechstes_datum("2024-02-29", "monatlich", 31) == "2024-03-31"
    assert erwartung.naechstes_datum("2024-11-15", "vierteljaehrlich", 15) == "2025-02-15"
    assert erwartung.naechstes_datum("2024-08-31", "halbjaehrlich", 31) == "2025-02-28"
    assert erwartung.naechstes_datum("2024-02-29", "jaehrlich", 29) == "2025-02-28"


def test_ohne_wiederholung_bleibt_die_form_unveraendert(umgebung):
    c, *_ = umgebung
    e = ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Handwerker Musterbau", "betrag": 320000,
                                            "datum": "2024-07-20"}), 201)
    assert "wiederholung" not in e and e["grund"] == "manuell" and e["datum"] == "2024-07-20"
    protokoll = ok(c.get("/api/aenderungen", params={"pro_seite": 1}))["eintraege"][0]
    assert "wiederholung" not in protokoll["eintraege"][0]["nachher"]


def test_wiederholung_anlegen_aendern_und_pruefen(umgebung):
    c, *_ = umgebung
    neu = {"richtung": "ausgabe", "haendler": "Musterschutz Versicherung", "betrag": 4800, "datum": "2024-07-31"}
    e = ok(c.post("/api/erwartungen", json={**neu, "wiederholung": "monatlich", "wiederholung_bis": "2024-12-31"}), 201)
    assert e["wiederholung"] == {"rhythmus": "monatlich", "bis": "2024-12-31"}
    e = ok(c.patch(f"/api/erwartungen/{e['id']}", json={"wiederholung": "jaehrlich", "wiederholung_bis": None}))
    assert e["wiederholung"] == {"rhythmus": "jaehrlich", "bis": None}
    e = ok(c.patch(f"/api/erwartungen/{e['id']}", json={"wiederholung": "keine"}))
    assert "wiederholung" not in e
    assert c.post("/api/erwartungen", json={**neu, "wiederholung": "taeglich"}).status_code == 422
    assert c.post("/api/erwartungen", json={**neu, "wiederholung_bis": "2024-12-31"}).status_code == 422


def test_erledigt_legt_die_naechste_an_und_rueckgaengig_nimmt_sie_zurueck(umgebung):
    c, *_ = umgebung
    e = ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Musterschutz", "betrag": 4800,
                                            "datum": "2024-07-31", "frist": "2024-08-10", "wiederholung": "monatlich",
                                            "wiederholung_bis": "2024-09-15"}), 201)
    ok(c.post(f"/api/erwartungen/{e['id']}/zustand", json={"zustand": "erledigt"}))
    (folge,) = _offen(c)
    assert (folge["datum"], folge["frist"], folge["betrag"], folge["haendler"]) == ("2024-08-31", "2024-09-10", 4800, "Musterschutz")
    assert folge["wiederholung"] == {"rhythmus": "monatlich", "bis": "2024-09-15"}
    aenderung = ok(c.get("/api/aenderungen", params={"pro_seite": 1}))["eintraege"][0]
    assert sorted((x["objekt"], x["art"]) for x in aenderung["eintraege"]) == [("erwartung", "angelegt"), ("erwartung", "geaendert")]
    # wieder offen: die unberührte Folge entfällt
    ok(c.post(f"/api/erwartungen/{e['id']}/zustand", json={"zustand": "offen"}))
    assert [x["id"] for x in _offen(c)] == [e["id"]]
    # Rückgängig stellt „erledigt“ samt Folge wieder her
    letzte = ok(c.get("/api/aenderungen", params={"pro_seite": 1}))["eintraege"][0]
    ok(c.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig"))
    assert [x["datum"] for x in _offen(c)] == ["2024-08-31"]
    # die Folge erledigt: Ende (15.09.) erreicht, keine weitere; storniert beendet ebenfalls
    ok(c.post(f"/api/erwartungen/{_offen(c)[0]['id']}/zustand", json={"zustand": "erledigt"}))
    assert _offen(c) == []
    f = ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Verein", "betrag": 1200, "datum": "2024-07-01",
                                            "wiederholung": "jaehrlich"}), 201)
    ok(c.post(f"/api/erwartungen/{f['id']}/zustand", json={"zustand": "storniert"}))
    assert _offen(c) == []


def test_bankbuchung_erfuellt_die_geplante_zahlung_und_die_naechste_entsteht(umgebung):
    c, config, giro, kat = umgebung
    e = ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Musterschutz Versicherung AG", "betrag": 4800,
                                            "datum": "2024-06-28", "wiederholung": "vierteljaehrlich"}), 201)
    # zwei Tage früher gebucht, die Bank kürzt den Namen: ein aussagekräftiges Wort genügt
    b = _buchen(c, giro, kat, "2024-06-26", -4800, "MUSTERSCHUTZ VERS. Beitrag 3. Quartal")
    _buchen(c, giro, kat, "2024-06-24", -4800, "Baumarkt Einkauf")      # gleicher Betrag, anderer Name
    erg = abgleich.laufen(config, dt.datetime(2024, 6, 30, 12, tzinfo=dt.timezone.utc))
    assert erg["zugeordnet"] == 1
    alt = ok(c.get(f"/api/erwartungen/{e['id']}"))
    assert alt["zustand"] == "erfuellt" and alt["buchung_ids"] == [b]
    (folge,) = _offen(c)
    assert folge["datum"] == "2024-09-28" and folge["buchung_ids"] == []
    # Zuordnung lösen: die alte ist wieder offen, die Folge entfällt
    ok(c.delete(f"/api/erwartungen/{e['id']}/buchungen/{b}"))
    assert [x["id"] for x in _offen(c)] == [e["id"]]
    # Buchung löschen nach erneutem Zuordnen: ebenso
    ok(c.post(f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [b]}))
    assert len(_offen(c)) == 1 and _offen(c)[0]["datum"] == "2024-09-28"
    assert c.delete(f"/api/buchungen/{b}").status_code == 204
    assert [x["id"] for x in _offen(c)] == [e["id"]]


def test_vorschau_enthaelt_geplante_zahlungen_mit_wiederholungen(umgebung):
    c, _config, giro, kat = umgebung
    heute = dt.date.today()
    tag = lambda n: (heute + dt.timedelta(days=n)).isoformat()  # noqa: E731
    _buchen(c, giro, kat, tag(-5), 500000, "Anfang")
    ohne = ok(c.get("/api/berichte/vorschau", params={"tage": 90}))
    ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Handwerker Musterbau", "betrag": 320000,
                                        "datum": tag(20)}), 201)
    zweite = erwartung.naechstes_datum(tag(10), "monatlich", int(tag(10)[8:10]))
    ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Musterschutz", "betrag": 4800,
                                        "datum": tag(10), "wiederholung": "monatlich", "wiederholung_bis": zweite}), 201)
    ok(c.post("/api/erwartungen", json={"richtung": "eingang", "haendler": "Finanzamt", "betrag": 15000, "datum": tag(-20)}), 201)
    mit = ok(c.get("/api/berichte/vorschau", params={"tage": 90}))
    geplant = sorted((e["datum"], e["betrag"], e["rhythmus"], e["empfaenger"]["name"]) for e in mit["ereignisse"] if e["quelle"] == "geplant")
    assert geplant == sorted([(tag(1), 15000, "einmalig", "Finanzamt"),          # schon fällig: am Folgetag erwartet
                              (tag(20), -320000, "einmalig", "Handwerker Musterbau"),
                              (tag(10), -4800, "monatlich", "Musterschutz"), (zweite, -4800, "monatlich", "Musterschutz")])
    assert mit["ende"]["fest"] == ohne["ende"]["fest"] + 15000 - 320000 - 2 * 4800
    assert mit["summen"]["feste_ausgaben"] == ohne["summen"]["feste_ausgaben"] + 320000 + 2 * 4800


def test_sicherung_und_altbestand(umgebung, tmp_path):
    """Die Wiederholung steht in der Sicherung (Schemaversion 10) und kommt beim Einspielen zurück."""
    c, config, *_ = umgebung
    e = ok(c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Musterschutz", "betrag": 4800,
                                            "datum": "2024-07-31", "wiederholung": "halbjaehrlich"}), 201)
    r = c.get("/api/sicherung")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        manifest = json.loads(z.read("manifest.json"))
        (tmp_path / "s.sqlite").write_bytes(z.read("kontor.sqlite"))
    assert manifest["schemaversion"] >= 10   # D-302: ab 11 mit Einstellungen
    con = sqlite3.connect(tmp_path / "s.sqlite")
    assert con.execute("SELECT erwartung_id, rhythmus, tag, bis, vorgaenger_id FROM erwartung_wiederholung").fetchall() == [
        (e["id"], "halbjaehrlich", 31, None, None)]
    con.close()
    ok(c.patch(f"/api/erwartungen/{e['id']}", json={"wiederholung": "keine"}))
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"}, files={"datei": ("s.zip", r.content, "application/zip")})
    assert r.status_code == 200, r.text
    assert ok(c.get(f"/api/erwartungen/{e['id']}"))["wiederholung"] == {"rhythmus": "halbjaehrlich", "bis": None}
    assert db.SCHEMA_VERSION >= 16   # D-238; ab D-243 Schema 17
