"""M9: Sicherung erstellen (sicherung.md 2–4, E-085 bis E-091).

Aufbau der ZIP-Datei, Manifest, Prüfsummen (unabhängig aus REST berechnet), SQLite-Eigenschaften, und
dass weder Änderungsprotokoll noch Geheimnisse noch Reste gelöschter Daten in der Datei stehen.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from tests.hilfen import kontor
from tests.hilfen.m2 import mock_api
from tests.hilfen.m3 import zeitstempel_ok
from tests.hilfen.m9 import (aenderungsanzahl, anzahl, bestand, dateiname, db_objekte, enthaelt, inhalt,
                             inhalt_sha256, kleiner_bestand, oeffne, reicher_bestand, sicherung)

pytestmark = pytest.mark.kern


def test_leere_instanz(api):
    """Auch eine leere Instanz lässt sich sichern; Manifest nach 3.2."""
    m, db = oeffne(sicherung(api))
    i = inhalt(api, vorlagen=False)
    assert (m["format"], m["formatversion"], m["modus"]) == ("kontor-sicherung", 1, "echt")
    assert m["app_version"] == kontor.modul("kontor").__version__
    assert isinstance(m["schemaversion"], int) and m["schemaversion"] >= 1
    assert zeitstempel_ok(m["erstellt"]), m["erstellt"]
    assert m["anzahl"] == anzahl(i)
    assert m["inhalt_sha256"] == inhalt_sha256(i)
    assert m["datenbank_sha256"] == hashlib.sha256(db).hexdigest()


def test_reicher_bestand_pruefsummen(api):
    """3.2/3.3: Anzahlen und Inhaltsprüfsumme stimmen mit der unabhängigen Berechnung aus REST überein."""
    reicher_bestand(api)
    i = inhalt(api, vorlagen=False)
    assert all(i[o] for o in ("konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung")), (
        "Testbestand soll jede M3-Objektart enthalten: " + str(anzahl(i)))
    m, db = oeffne(sicherung(api))
    assert m["anzahl"] == anzahl(i)
    assert m["inhalt_sha256"] == inhalt_sha256(i), "inhalt_sha256 weicht von sicherung.md 3.3 ab"
    assert m["datenbank_sha256"] == hashlib.sha256(db).hexdigest()


def test_sqlite_eigenstaendig_ohne_views_und_trigger(api):
    """3.1: integrity_check ok, nur table/index, kein WAL-Modus im Dateikopf."""
    kleiner_bestand(api)
    _, db = oeffne(sicherung(api))
    assert db[:16] == b"SQLite format 3\x00", "kontor.sqlite ist keine SQLite-3-Datei"
    assert (db[18], db[19]) == (1, 1), "Dateikopf verlangt WAL (Bytes 18/19 müssen 1 sein)"
    typen = {t for t, _ in db_objekte(db)}
    assert typen <= {"table", "index"}, f"unerlaubte Objekte in sqlite_master: {typen - {'table', 'index'}}"


def test_dateiname_und_zeitpunkt(api):
    """3.1: kontor-sicherung-<modus>-<JJJJMMTT>T<HHMMSS>Z.zip passend zu erstellt."""
    name = dateiname(api)
    m, _ = oeffne(api.get("/api/sicherung", erwartet=200).content)
    assert name.startswith("kontor-sicherung-echt-")
    erstellt = dt.datetime.strptime(m["erstellt"], "%Y-%m-%dT%H:%M:%SZ")
    aus_name = dt.datetime.strptime(name[len("kontor-sicherung-echt-"):-len(".zip")], "%Y%m%dT%H%M%SZ")
    assert abs((erstellt - aus_name).total_seconds()) <= 2, (name, m["erstellt"])


def test_mock_modus_und_simulierte_uhr(tmp_path, netz_gesperrt):
    """3.1/3.2: Modus mock, erstellt = App-Uhr (simulierte Zeit)."""
    api = mock_api(tmp_path, heute="2024-03-31")
    api.put("/api/mock/zeit", json={"jetzt": "2024-04-02T08:15:30Z"}, erwartet=200)
    m, _ = oeffne(sicherung(api))
    assert (m["modus"], m["erstellt"]) == ("mock", "2024-04-02T08:15:30Z")
    assert dateiname(api) == "kontor-sicherung-mock-20240402T081530Z.zip"


def test_erstellen_aendert_nichts(api):
    """4: keine Änderung, gleicher Bestand; zweimal erstellt → gleiche Inhaltsprüfsumme."""
    reicher_bestand(api)
    vorher, n = bestand(api, vorlagen=False), aenderungsanzahl(api)
    m1, _ = oeffne(sicherung(api))
    m2, _ = oeffne(sicherung(api))
    assert bestand(api, vorlagen=False) == vorher
    assert aenderungsanzahl(api) == n, "GET /api/sicherung darf keine Änderung erzeugen"
    assert m1["inhalt_sha256"] == m2["inhalt_sha256"]
    assert api.get("/api/benachrichtigungen", erwartet=200).daten == []


def test_kein_protokoll_und_keine_reste(api):
    """2.2/E-086: Texte, die nur noch im Protokoll stehen, kommen in der Datei nicht vor."""
    k = kleiner_bestand(api)
    marken = {
        "tag": "MarkeTagQ7xZ1",
        "zweck": "MarkeZweckQ7xZ2",
        "konto": "MarkeKontoQ7xZ3",
        "notiz": "MarkeNotizQ7xZ4",
    }
    t = api.tag(marken["tag"])
    api.patch(f"/api/tags/{t['id']}", json={"name": "Neuer Name"}, erwartet=200)
    b = api.buchung("2024-02-02", [(k["giro"]["id"], -500), (k["kat"]["id"], 500)], verwendungszweck=marken["zweck"])
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    weg = api.konto(marken["konto"], "aufwand", notiz=marken["notiz"])
    api.delete(f"/api/konten/{weg['id']}", erwartet=204)
    api.patch(f"/api/konten/{k['giro']['id']}", json={"notiz": "MarkeNotizQ7xZ5"}, erwartet=200)
    api.patch(f"/api/konten/{k['giro']['id']}", json={"notiz": "aktuell"}, erwartet=200)
    daten = sicherung(api)
    for name, marke in {**marken, "notiz_alt": "MarkeNotizQ7xZ5"}.items():
        assert not enthaelt(daten, marke), f"Rest im Protokoll bzw. gelöschtes Objekt in der Sicherung: {name}"
    # Gegenprobe: aktuelle Texte sind enthalten
    assert enthaelt(daten, "Neuer Name") and enthaelt(daten, "A Einkauf") and enthaelt(daten, "aktuell")


def test_keine_pin(tmp_path, netz_gesperrt):
    """2.2/E-090: Eine gesetzte PIN steht in keinem Byte der Sicherung."""
    api = mock_api(tmp_path)
    pin = "PinMarke-80417"
    api.put("/api/sync/pin", json={"pin": pin}, erwartet=204)
    api.post("/api/sync", json={"von": "2024-01-01"}, erwartet=200)
    daten = sicherung(api)
    assert not enthaelt(daten, pin), "PIN in der Sicherung"


def test_python_erstelle_sicherung(tmp_path):
    """python-api.md 11.1: gleicher Inhalt wie REST, liest nur, Modus aus der Konfiguration."""
    from tests.hilfen.api import Api, neue_config

    config = neue_config(tmp_path)
    api = Api(config)
    kleiner_bestand(api)
    n = aenderungsanzahl(api)
    roh = kontor.modul("kontor.sicherung").erstelle_sicherung(config)
    assert isinstance(roh, bytes)
    m, db = oeffne(roh)
    assert m["modus"] == "echt" and m["inhalt_sha256"] == inhalt_sha256(inhalt(api, vorlagen=False))
    assert m["datenbank_sha256"] == hashlib.sha256(db).hexdigest()
    assert aenderungsanzahl(api) == n


def test_python_erstelle_sicherung_mock_heute(tmp_path):
    """python-api.md 11.1: im Mock-Modus mit mock_heute ist erstellt dessen 12:00:00Z; leere neue Datenbank."""
    from tests.hilfen.api import neue_config

    config = neue_config(tmp_path, mock_modus=True, mock_heute=dt.date(2024, 5, 6))
    m, _ = oeffne(kontor.modul("kontor.sicherung").erstelle_sicherung(config))
    assert (m["modus"], m["erstellt"]) == ("mock", "2024-05-06T12:00:00Z")
    assert set(m["anzahl"]) == {"konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung",
                                "vorlage"}
