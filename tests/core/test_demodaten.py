"""Core-Tests zum Feature „demodaten“: Die Testinstanz lässt sich statt mit einer Kopie der echten Daten mit einem
erfundenen Haushalt füllen (Vorführung). Geprüft wird hier ein kleiner Zeitraum; der volle Umfang (mindestens
2000 Buchungen, mindestens 100 Mails) steht in ``tests/test_demodaten_eigen.py``."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from kontor import demodaten as D
from kontor import demowelt
from kontor import testinstanz as T
from kontor.app import create_app
from kontor.plugins import mock_daten

HEUTE = dt.date(2026, 3, 10)    # vier Monate zurück liegt ein Jahreswechsel: Jahresabgleich und Abstimmung
MONATE = 4


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """Ein kleiner Demobestand (vier Monate), einmal für alle Tests dieser Datei aufgebaut."""
    ordner = tmp_path_factory.mktemp("demo")
    datenbank, mockdatei = ordner / "demo.sqlite3", ordner / "demo-mockdaten.json"
    bericht = D.aufbauen(datenbank, mockdatei, heute=HEUTE, monate=MONATE)
    client = TestClient(create_app(D.konfiguration(datenbank, mockdatei, mock_heute=HEUTE)))
    return {"bericht": bericht, "client": client, "datenbank": datenbank, "mockdatei": mockdatei}


def test_welt_ist_reproduzierbar_und_rein_synthetisch():
    a, b = D.welt(HEUTE, monate=MONATE).mock_daten(), D.welt(HEUTE, monate=MONATE).mock_daten()
    assert a == b
    text = json.dumps(a, ensure_ascii=False)
    ibans = set(re.findall(r"DE\d{20}", text))
    assert ibans and all(i[4:12] == "00000000" for i in ibans)
    adressen = set(re.findall(r"[\w.+-]+@[\w.-]+", text))
    assert adressen and all(x.endswith("example.invalid") for x in adressen)
    assert len(a["bank"]["konten"]) == 2 and {k["art"] for k in a["bank"]["konten"]} == {"girokonto", "sparkonto"}


def test_mockdatei_ist_fuer_die_mock_plugins_lesbar(demo):
    daten = mock_daten.lade_datei(demo["mockdatei"])
    assert len(daten.konten) == 2 and len(daten.postfaecher) == 2
    # Es liegt schon Stoff für spätere Abrufe bereit (Umsätze und Mails nach dem Tag des Aufbaus)
    assert any(u.buchungstag > HEUTE for u in daten.umsaetze)
    assert any(m.empfangen.date() > HEUTE for m in daten.nachrichten)


def test_konten_kategorien_und_kredite(demo):
    c = demo["client"]
    konten = c.get("/api/konten").json()
    arten = [k["art"] for k in konten]
    assert arten.count("girokonto") == 1 and arten.count("sparkonto") == 1
    kategorien = [k for k in konten if k["art"] in ("aufwand", "ertrag")]
    ober = {k["id"] for k in kategorien if k["eltern_id"] is None}
    unter = [k for k in kategorien if k["eltern_id"] in ober]
    assert len(unter) >= 4, "ein Teil der Kategorien ist hierarchisch"
    kredite = c.get("/api/kredite").json()
    assert len(kredite) >= 2
    assert all(k["zuordnungen"] for k in kredite), "Raten sind erkannt und zugeordnet"


def test_buchbestand_zeigt_die_funktionen(demo):
    c = demo["client"]
    assert demo["bericht"]["buchungen"] == c.get("/api/buchungen?pro_seite=1").json()["gesamt"] > 150
    assert c.get("/api/regeln").json()
    assert c.get("/api/vorlagen").json()
    assert c.get("/api/tags").json()
    assert c.get("/api/erwartungen").json()["eintraege"]
    assert c.get("/api/wiederkehrend").json()["serien"]
    assert c.get("/api/abstimmungen").json()
    stati = {s for s in ("importiert", "vorlaeufig", "bestaetigt", "abgeglichen")
             if c.get(f"/api/buchungen?status={s}&pro_seite=1").json()["gesamt"]}
    assert {"vorlaeufig", "bestaetigt", "abgeglichen"} <= stati
    mails = c.get("/api/mail/nachrichten?pro_seite=1").json()
    assert mails["gesamt"] == demo["bericht"]["mails"] > 10
    assert mails["stand"]["zugeordnet"] > 0, "ein Teil der Mails hängt als Dokument an Buchungen"
    assert len(mails["stand"]["postfaecher"]) == 2


def test_kontostaende_passen_zur_mock_bank(demo):
    c = demo["client"]
    lauf = c.get("/api/sync/laeufe").json()[-1]
    assert lauf["status"] == "erfolgreich"
    nach_iban = {k["iban"]: k for k in lauf["konten"]}
    giro, sparbuch = nach_iban[demowelt.GIRO], nach_iban[demowelt.SPARBUCH]
    assert sparbuch["saldo_abgleich"]["status"] == "stimmt"
    # Im Girokonto steht eine von Hand notierte Ausgabe, die die Bank noch einmal geliefert hat (Dublettenverdacht):
    # Genau um diesen Betrag hat der Abruf den Kontostand an die Bank angeglichen.
    verdacht = c.get("/api/dubletten").json()
    assert len(verdacht) == 1 and verdacht[0]["status"] == "offen"
    doppelt = c.get(f"/api/buchungen/{verdacht[0]['buchung_id']}").json()
    assert giro["saldo_abgleich"]["status"] == "ausgeglichen"
    assert giro["saldo_abgleich"]["differenz"] == abs(doppelt["betrag"]) > 0
    stand = {k["name"]: k["saldo"] for k in c.get("/api/kontenuebersicht").json()["konten"]}
    assert stand["Girokonto"] == giro["saldo_abgleich"]["bank_saldo"]
    assert stand["Sparbuch"] == sparbuch["saldo_abgleich"]["bank_saldo"]


def test_abruf_in_der_vorfuehrung_bringt_neues(demo):
    """Der Aufbau endet einige Tage vor ``heute``: Die ersten Abrufe in der Vorführung liefern neue Einträge."""
    c = demo["client"]
    lauf = c.post("/api/sync").json()
    assert lauf["status"] == "erfolgreich" and sum(k["buchungen_neu"] for k in lauf["konten"]) > 0
    abruf = c.post("/api/mail/abruf").json()
    assert sum(p["nachrichten_neu"] for p in abruf["postfaecher"]) > 0


def test_aufbau_ersetzt_einen_frueheren_bestand(tmp_path):
    datenbank, mockdatei = tmp_path / "demo.sqlite3", tmp_path / "mock.json"
    datenbank.write_bytes(b"kein SQLite")
    D.aufbauen(datenbank, mockdatei, heute=HEUTE, monate=1)
    c = TestClient(create_app(D.konfiguration(datenbank, mockdatei, mock_heute=HEUTE)))
    assert c.get("/api/buchungen?pro_seite=1").json()["gesamt"] > 0


# ------------------------------------------------------------------------------------------------ Testinstanz

class _Befehle:
    def __init__(self) -> None:
        self.liste: list[list[str]] = []

    def __call__(self, args: list[str]) -> None:
        self.liste.append(args)
        if args[:2] == ["git", "clone"]:
            pathlib.Path(args[-1]).mkdir(parents=True)


def _orte(tmp_path: pathlib.Path) -> T.Orte:
    # Die Hauptinstanz fehlt hier ganz: Für die Demo wird sie nicht gebraucht und nicht gelesen.
    return T.Orte(haupt_env=tmp_path / "etc" / "kontor.env", programm=tmp_path / "opt", daten=tmp_path / "var",
                  env=tmp_path / "etc" / "kontor-test.env", unit=tmp_path / "systemd" / T.DIENST, benutzer=None)


def test_testinstanz_demo_baut_demodaten_statt_einer_kopie(tmp_path):
    orte, befehle = _orte(tmp_path), _Befehle()
    meldung = T.demo("main", orte, befehle)
    assert "Demodaten" in meldung
    aufruf = next(a for a in befehle.liste if "kontor.demodaten" in a)
    assert aufruf[0] == str(orte.venv / "bin" / "python"), "der Generator des Branches baut die Daten"
    assert str(orte.datenbank) in aufruf and str(orte.demo_mockdaten) in aufruf
    reihenfolge = [" ".join(a[:3]) for a in befehle.liste]
    assert reihenfolge.index(f"systemctl stop {T.DIENST}") < befehle.liste.index(aufruf) \
        < reihenfolge.index(f"systemctl start {T.DIENST}")
    zusatz = orte.demo_env.read_text(encoding="utf-8")
    assert "KONTOR_ANMELDUNG=0" in zusatz and f"KONTOR_MOCK_DATEN={orte.demo_mockdaten}" in zusatz
    # Ein Drop-in lässt die Unit die Zusatzdatei nach der gewöhnlichen Umgebungsdatei lesen (spätere Angaben
    # gelten); die ausgelieferte Unit selbst bleibt, wie betrieb.md 9 sie festlegt.
    assert orte.demo_dropin.parent == orte.unit.with_name(T.DIENST + ".d")
    assert f"EnvironmentFile=-{orte.demo_env}" in orte.demo_dropin.read_text(encoding="utf-8")
    assert "demo" not in orte.unit.read_text(encoding="utf-8")
    assert reihenfolge.index("systemctl daemon-reload", befehle.liste.index(aufruf)) \
        < reihenfolge.index(f"systemctl start {T.DIENST}"), "systemd liest das Drop-in vor dem Start"


def test_einrichten_mit_datenkopie_nimmt_die_demo_einstellungen_zurueck(tmp_path):
    orte, befehle = _orte(tmp_path), _Befehle()
    T.demo("main", orte, befehle)
    orte.demo_mockdaten.write_text("{}", encoding="utf-8")
    from kontor import db
    haupt = tmp_path / "haupt.sqlite3"
    db.schema_anlegen(haupt)
    orte.haupt_env.write_text(f"KONTOR_DATENBANK={haupt}\n", encoding="utf-8")
    T.einrichten("feature/x", orte, _Befehle())
    assert not orte.demo_env.exists() and not orte.demo_mockdaten.exists() and not orte.demo_dropin.exists()


def test_stoppen_mit_loeschen_entfernt_auch_die_demodaten(tmp_path):
    orte = _orte(tmp_path)
    T.demo("main", orte, _Befehle())
    orte.daten.mkdir(parents=True, exist_ok=True)
    orte.datenbank.write_bytes(b"x")
    orte.demo_mockdaten.write_text("{}", encoding="utf-8")
    T.stoppen(orte, _Befehle(), loeschen=True)
    assert not orte.datenbank.exists() and not orte.demo_mockdaten.exists()
