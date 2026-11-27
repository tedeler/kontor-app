"""Eigene Tests zum Feature „demodaten“: voller Umfang des erfundenen Haushalts (drei Jahre) und Randfälle des
Kalenders. Die schnellen Tests an einem kleinen Zeitraum stehen in ``tests/core/test_demodaten.py``."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from kontor import demodaten as D
from kontor import demowelt
from kontor.app import create_app

HEUTE = dt.date(2026, 11, 25)


@pytest.fixture(scope="module")
def voll(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("demo-voll")
    datenbank, mockdatei = ordner / "demo.sqlite3", ordner / "mock.json"
    bericht = D.aufbauen(datenbank, mockdatei, heute=HEUTE)
    client = TestClient(create_app(D.konfiguration(datenbank, mockdatei, mock_heute=HEUTE)))
    return bericht, client, datenbank, mockdatei


def test_umfang_wie_bestellt(voll):
    """Auftrag: ein Girokonto, ein Sparbuch, rund zehn teils hierarchische Kategorien, Kredite, mindestens
    2000 Buchungen und mindestens 100 Mails."""
    bericht, c, _, _ = voll
    assert bericht["buchungen"] >= 2000 and bericht["mails"] >= 100
    konten = c.get("/api/konten").json()
    assert sorted(k["name"] for k in konten if k["art"] in ("girokonto", "sparkonto")) == ["Girokonto", "Sparbuch"]
    kategorien = [k for k in konten if k["art"] in ("aufwand", "ertrag") and not k["extern_id"]]
    assert 10 <= len(kategorien) <= 16 and bericht["kategorien"] == len(kategorien)
    assert 4 <= sum(1 for k in kategorien if k["eltern_id"] is not None) < len(kategorien)
    assert bericht["kredite"] == 2 and bericht["belege"] >= 10


def test_fast_alles_ist_zugeordnet_ein_rest_bleibt_zum_vorfuehren(voll):
    _, c, _, _ = voll
    gesamt = c.get("/api/buchungen?pro_seite=1").json()["gesamt"]
    offen = c.get("/api/buchungen?status=importiert&status=vorlaeufig&pro_seite=1").json()["gesamt"]
    assert 15 <= offen <= gesamt // 20
    assert c.get("/api/buchungen?vorschlag=true&pro_seite=1").json()["gesamt"] >= 10
    unkategorisiert = next(k for k in c.get("/api/konten").json() if k["extern_id"] == "kontor:unkategorisiert")
    liste = c.get(f"/api/buchungen?konto_id={unkategorisiert['id']}&pro_seite=100").json()
    assert 2 <= liste["gesamt"] <= 12
    # Bearbeitet wurde nur bis kurz vor dem Bezugstag: Alles Offene stammt aus den letzten Wochen
    aeltestes = min(b["datum"] for b in c.get("/api/buchungen?status=importiert&status=vorlaeufig&pro_seite=500")
                    .json()["eintraege"])
    assert aeltestes >= (HEUTE - dt.timedelta(days=60)).isoformat()


def test_kredite_laufen_mit_plan_sondertilgung_und_jahresabgleich(voll):
    _, c, _, _ = voll
    wohnung, auto = sorted(c.get("/api/kredite").json(), key=lambda k: -k["restschuld"])
    assert len(wohnung["zuordnungen"]) >= 35 and len(auto["zuordnungen"]) >= 35
    assert [s["betrag"] for s in wohnung["sondertilgungen"]] == [demowelt.SONDERTILGUNG]
    assert [a["jahr"] for a in wohnung["abgleiche"]] == [2023, 2024, 2025]
    assert all(a["buchung_id"] is not None for a in wohnung["abgleiche"]), "Korrekturbuchung je Jahresauszug"
    assert all(a["buchung_id"] is None for a in auto["abgleiche"]), "der Autokredit stimmt ohne Korrektur"
    stand = {k["name"]: k["saldo"] for k in c.get("/api/kontenuebersicht").json()["konten"]}
    assert -demowelt.WOHNUNG["restschuld"] < stand["Wohnungsdarlehen"] < 0
    assert -demowelt.AUTO["restschuld"] < stand["Autokredit"] < 0
    assert stand["Girokonto"] > 0 and stand["Sparbuch"] > 0


def test_weitere_funktionen_haben_stoff(voll):
    _, c, _, _ = voll
    serien = c.get("/api/wiederkehrend").json()["serien"]
    assert len(serien) >= 12 and {"aktiv", "beendet"} <= {s["status"] for s in serien}
    assert len(c.get("/api/abstimmungen").json()) == 6
    regeln = c.get("/api/regeln").json()
    assert any(r.get("automatisch") for r in regeln) and sum(1 for r in regeln if not r.get("automatisch")) == 8
    erwartungen = c.get("/api/erwartungen").json()
    assert erwartungen["anzahl"] == 4 and erwartungen["ueberfaellig"] == 1
    arten = {n["art"] for n in c.get("/api/benachrichtigungen").json() if not n["gelesen"]}
    assert {"split_abweichung", "saldo_ausgeglichen"} <= arten
    tags = {t["name"]: t["anzahl_buchungen"] for t in c.get("/api/tags").json()}
    assert tags["Auto"] > 50 and tags["Urlaub 2025"] > 5 and tags["Große Ausgabe"] > 10
    for bericht in ("monat", "kategorien", "vermoegen", "geldfluss"):
        assert c.get(f"/api/berichte/{bericht}").status_code == 200
    laeufe = c.get("/api/sync/laeufe").json()
    assert len(laeufe) >= 12 and all(lauf["status"] == "erfolgreich" for lauf in laeufe)


def test_nur_erfundene_daten_und_keine_geheimnisse(voll):
    _, _, datenbank, mockdatei = voll
    con = sqlite3.connect(datenbank)
    try:
        assert con.execute("SELECT count(*) FROM geheimnis").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM anmeldung_konto WHERE passwort_hash IS NOT NULL").fetchone() == (0,)
        ibans = [r[0] for r in con.execute("SELECT iban FROM konto WHERE iban IS NOT NULL")]
        adressen = [r[0] for r in con.execute("SELECT adresse FROM postfach")]
        absender = {r[0].rpartition("@")[2] for r in con.execute("SELECT absender FROM mail_nachricht")}
    finally:
        con.close()
    assert sorted(ibans) == sorted([demowelt.GIRO, demowelt.SPARBUCH]) and all(i[4:12] == "00000000" for i in ibans)
    assert all(a.endswith("@example.invalid") for a in adressen)
    assert all(a.endswith("example.invalid") for a in absender)
    welt = json.loads(mockdatei.read_text(encoding="utf-8"))
    assert "pin" not in welt["bank"] and "tan" not in welt["bank"]


@pytest.mark.parametrize("heute, monate", [(dt.date(2026, 1, 1), 3), (dt.date(2024, 2, 29), 5),
                                           (dt.date(2027, 3, 31), 2), (dt.date(2026, 1, 21), 1)])
def test_aufbau_gelingt_an_kalenderraendern(tmp_path, heute, monate):
    bericht = D.aufbauen(tmp_path / "demo.sqlite3", tmp_path / "mock.json", heute=heute, monate=monate)
    assert bericht["buchungen"] > 50 and bericht["mails"] > 5 and bericht["kredite"] == 2


def test_kommandozeile(tmp_path, capsys):
    assert D.main([str(tmp_path / "demo.sqlite3"), str(tmp_path / "mock.json"), "--heute", "2026-11-25",
                   "--monate", "1"]) == 0
    assert "Buchungen" in capsys.readouterr().out
    assert D.main([str(tmp_path / "demo.sqlite3"), str(tmp_path / "mock.json"), "--monate", "0"]) == 1
    assert "nicht aufbauen" in capsys.readouterr().err


def test_umgebung_der_demo_instanz(voll, tmp_path):
    """Ausgelieferte Umgebungsdatei der Testinstanz und darüber der Zusatz der Demo: ohne Anmeldung, die erfundene
    Welt als Mock-Bank; die Instanz startet damit auf den aufgebauten Daten und verhält sich wie beim Aufbau."""
    from importlib import resources

    from kontor import testinstanz as T
    from kontor.config import KontorConfig

    _, _, datenbank, mockdatei = voll
    texte = (resources.files("kontor.betrieb").joinpath("kontor-test.env").read_text(encoding="utf-8"),
             T.DEMO_ENV.format(mockdaten=mockdatei))
    env: dict[str, str] = {}
    for text in texte:      # spätere Angaben gelten, wie bei systemd
        for zeile in text.splitlines():
            if zeile.strip() and not zeile.startswith("#"):
                name, _, wert = zeile.partition("=")
                env[name.strip()] = wert.strip()
    env["KONTOR_MOCK_DATENBANK"] = str(datenbank)
    env["KONTOR_DATENBANK"] = str(tmp_path / "unbenutzt.sqlite3")
    config = KontorConfig.from_env(env)
    assert config.anmeldung is False and config.mock_modus is True and config.mock_daten == mockdatei
    aufbau = D.konfiguration(datenbank, mockdatei)
    for feld in ("umbuchung_automatisch", "lernmodell_automatisch", "regeln_automatisch", "wiederkehrend_automatisch",
                 "sync_konten_anlegen", "mail_bestellnummer", "mail_nur_koepfe", "mail_abgleich"):
        assert getattr(config, feld) == getattr(aufbau, feld), feld
    c = TestClient(create_app(config), client=("192.168.1.20", 50000))     # aus dem erlaubten Heimnetz
    assert c.get("/api/buchungen?pro_seite=1").status_code == 200, "ohne Anmeldung erreichbar"
    assert c.get("/", follow_redirects=False).status_code == 200, "keine Umleitung zur Anmeldeseite"


def test_aufbau_ersetzt_einen_frueheren_bestand(tmp_path):
    """Aus tests/core verschoben (Zeitbudget der Core-Tests, D-304)."""
    datenbank, mockdatei = tmp_path / "demo.sqlite3", tmp_path / "mock.json"
    datenbank.write_bytes(b"kein SQLite")
    D.aufbauen(datenbank, mockdatei, heute=dt.date(2026, 3, 10), monate=1)
    c = TestClient(create_app(D.konfiguration(datenbank, mockdatei, mock_heute=dt.date(2026, 3, 10))))
    assert c.get("/api/buchungen?pro_seite=1").json()["gesamt"] > 0
