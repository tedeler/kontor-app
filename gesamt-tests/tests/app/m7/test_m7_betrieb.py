"""M7: ausgelieferte Betriebsdateien, zeitgesteuerte Sicherung, Kommandozeilen, Beenden und Neustart
(betrieb.md)."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_config
from tests.hilfen.m2 import laeufe, mock_config, status, sync
from tests.hilfen.m7 import PASSWORT, anmeldung, betriebsdatei
from tests.hilfen.m9 import aenderungsanzahl, oeffne
from tests.hilfen.pfade import KMY
from tests.hilfen.systemd import Unit, geheimer_name, umgebungsdatei

REPO = Path(__file__).resolve().parents[3]
PY = "/opt/kontor/venv/bin/python"
HAERTUNG_JA = ["NoNewPrivileges", "PrivateTmp", "PrivateDevices", "ProtectHome", "ProtectKernelTunables",
               "ProtectKernelModules", "ProtectKernelLogs", "ProtectControlGroups", "ProtectClock", "ProtectHostname",
               "RestrictSUIDSGID", "RestrictRealtime", "RestrictNamespaces", "LockPersonality", "RemoveIPC"]
HAERTUNG_GENAU = {"ProtectSystem": "strict", "ProtectProc": "invisible", "ProcSubset": "pid",
                  "SystemCallArchitectures": "native", "SystemCallFilter": "@system-service",
                  "CapabilityBoundingSet": "", "AmbientCapabilities": ""}
GEHEIM_WORTE = ("pin", "passwort", "password", "token", "secret", "kontor_", "--")


def _haertung(u: Unit) -> None:
    for k in HAERTUNG_JA:
        assert u.wert("Service", k) == "yes", k
    for k, v in HAERTUNG_GENAU.items():
        assert u.wert("Service", k) == v, (k, u.wert("Service", k))
    assert set(u.wert("Service", "RestrictAddressFamilies").split()) == {"AF_UNIX", "AF_INET", "AF_INET6"}
    for verboten in ("DynamicUser", "LoadCredential", "SetCredential", "PermissionsStartOnly"):
        assert verboten not in u.schluessel("Service"), verboten
    assert u.wert("Service", "User") == u.wert("Service", "Group") == "kontor"
    assert u.wert("Service", "UMask") == "0077"
    for zuweisung in u.werte("Service", "Environment"):
        for teil in zuweisung.split():
            assert not geheimer_name(teil.split("=", 1)[0]), zuweisung
    for k in ("ExecStartPre", "ExecStartPost"):
        assert not any("systemd-creds" in v for v in u.werte("Service", k))


# ------------------------------------------------------------------ Unit-Dateien (statisch)
@pytest.mark.kern
def test_kontor_service():
    u = Unit(betriebsdatei("kontor.service"))
    assert u.wert("Unit", "Description")
    for k in ("After", "Wants"):
        assert "network-online.target" in " ".join(u.werte("Unit", k)).split(), k
    s = "Service"
    assert u.wert(s, "Type") == "exec"
    assert u.wert(s, "EnvironmentFile") == "/etc/kontor/kontor.env"
    assert u.werte(s, "ExecStart") == [f"{PY} -m kontor"]
    teile = u.wert(s, "ExecStart").split()
    assert teile[0].startswith("/") and not any(w in t.lower() for t in teile[1:] for w in GEHEIM_WORTE)
    assert sorted(u.werte(s, "LoadCredentialEncrypted")) == [
        "kontor-bank-pin:/etc/kontor/kontor-bank-pin.cred",
        "kontor-geheimnisschluessel:/etc/kontor/kontor-geheimnisschluessel.cred"]
    assert (u.wert(s, "StateDirectory"), u.wert(s, "StateDirectoryMode")) == ("kontor", "0700")
    assert u.wert(s, "Restart") == "on-failure" and int(u.wert(s, "RestartSec")) >= 1
    assert "2" in u.wert(s, "RestartPreventExitStatus").split()
    assert int(u.wert(s, "TimeoutStopSec")) >= 30
    _haertung(u)
    assert u.werte("Install", "WantedBy") == ["multi-user.target"]


@pytest.mark.kern
def test_sicherung_service_und_timer():
    u = Unit(betriebsdatei("kontor-sicherung.service"))
    s = "Service"
    assert u.wert(s, "Type") == "oneshot" and u.wert(s, "EnvironmentFile") == "/etc/kontor/kontor.env"
    assert u.werte(s, "ExecStart") == [
        f"{PY} -m kontor.sicherung --verzeichnis /var/lib/kontor/sicherungen --behalten 14"]
    assert u.wert(s, "StateDirectory") == "kontor"
    assert "LoadCredentialEncrypted" not in u.schluessel(s) and "Install" not in u.abschnitte
    _haertung(u)
    t = Unit(betriebsdatei("kontor-sicherung.timer"))
    kal = t.wert("Timer", "OnCalendar")
    assert kal == "daily" or kal.startswith("*-*-* ")
    assert t.wert("Timer", "Persistent") == "yes"
    assert t.wert("Timer", "Unit") in (None, "kontor-sicherung.service")
    assert t.werte("Install", "WantedBy") == ["timers.target"]


@pytest.mark.kern
def test_sysusers_und_dropin():
    zeilen = [z for z in betriebsdatei("kontor.sysusers").splitlines() if z.strip() and not z.startswith("#")]
    assert zeilen == ['u kontor - "Kontor" /var/lib/kontor']
    d = Unit(betriebsdatei("pin-eingabe.conf"))
    assert list(d.abschnitte) == ["Service"]
    zeilen = d.abschnitte["Service"]
    assert zeilen[0] == ("LoadCredentialEncrypted", ""), "erst die Liste zurücksetzen"
    assert sorted(zeilen[1:]) == [
        ("Environment", "KONTOR_BANK_PIN_QUELLE=eingabe"),
        ("LoadCredentialEncrypted", "kontor-geheimnisschluessel:/etc/kontor/kontor-geheimnisschluessel.cred")]


@pytest.mark.kern
def test_umgebungsdatei(tmp_path):
    werte, kommentare = umgebungsdatei(betriebsdatei("kontor.env"))
    pflicht = {"KONTOR_DATENBANK": "/var/lib/kontor/kontor.sqlite3", "KONTOR_ANMELDUNG": "1", "KONTOR_HOST": "0.0.0.0",
               "KONTOR_PORT": "8000", "KONTOR_BANK_PIN_QUELLE": "systemd-creds", "KONTOR_UMBUCHUNG_AUTOMATISCH": "1",
               "KONTOR_LERNMODELL_AUTOMATISCH": "1", "KONTOR_WIEDERKEHREND_AUTOMATISCH": "1",
               "KONTOR_ERLAUBTE_NETZE": "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7,fe80::/10"}
    for k, v in pflicht.items():
        assert werte.get(k) == v, (k, werte.get(k))
    assert int(werte["KONTOR_SYNC_INTERVALL_MINUTEN"]) >= 60
    assert "CREDENTIALS_DIRECTORY" not in werte
    for k in werte:
        assert not geheimer_name(k), k
    for z in kommentare:
        m = re.match(r"#\s*([A-Z_][A-Z0-9_]*)=(.*)", z)
        if m:
            assert not geheimer_name(m[1]) or not m[2].strip(), z
    c = kontor.KontorConfig().from_env({**werte, "KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"),
                                        "CREDENTIALS_DIRECTORY": str(tmp_path)})
    assert c.anmeldung is True and c.bank_pin_quelle == "systemd-creds" and c.host == "0.0.0.0" and c.port == 8000
    assert len(c.erlaubte_netze) == 7


# ------------------------------------------------------------------ zeitgesteuerte Sicherung
NAME = re.compile(r"^kontor-sicherung-(echt|mock)-([0-9]{8})T([0-9]{6})Z\.zip$")


@pytest.mark.kern
def test_sichere_in_verzeichnis(tmp_path):
    api = Api(neue_config(tmp_path / "db"))
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    vorher = aenderungsanzahl(api)
    ziel = tmp_path / "sicherungen" / "tief"
    pfad = kontor.modul("kontor.sicherung").sichere_in_verzeichnis(api.config, ziel)
    assert pfad.parent == ziel and NAME.match(pfad.name) and NAME.match(pfad.name)[1] == "echt"
    assert stat.S_IMODE(os.stat(ziel).st_mode) == 0o700 and stat.S_IMODE(os.stat(pfad).st_mode) == 0o600
    m, _ = oeffne(pfad.read_bytes())
    erstellt = dt.datetime.fromisoformat(m["erstellt"].replace("Z", "+00:00"))
    assert pfad.name == f"kontor-sicherung-echt-{erstellt:%Y%m%dT%H%M%S}Z.zip"
    direkt, _ = oeffne(kontor.modul("kontor.sicherung").erstelle_sicherung(api.config))
    assert m["inhalt_sha256"] == direkt["inhalt_sha256"] and m["anzahl"] == direkt["anzahl"]
    assert aenderungsanzahl(api) == vorher
    assert [p.name for p in ziel.iterdir()] == [pfad.name], "keine temporären Reste"


@pytest.mark.kern
def test_aufbewahrung(tmp_path):
    config = neue_config(tmp_path / "db")
    Api(config).import_kmy(KMY / "minimal.kmy", erwartet=200)
    ziel = tmp_path / "s"
    ziel.mkdir()
    alt = [f"kontor-sicherung-echt-2020010{i}T000000Z.zip" for i in range(1, 6)]
    fremd = ["kontor-sicherung-mock-20200101T000000Z.zip", "notizen.txt", "kontor-sicherung-echt-kaputt.zip"]
    for n in alt + fremd:
        (ziel / n).write_bytes(b"alt")
    s = kontor.modul("kontor.sicherung")
    neu = s.sichere_in_verzeichnis(config, ziel, behalten=3)
    namen = sorted(p.name for p in ziel.iterdir())
    assert namen == sorted([neu.name, alt[4], alt[3]] + fremd), namen
    with pytest.raises(ValueError):
        s.sichere_in_verzeichnis(config, ziel, behalten=0)
    with pytest.raises(ValueError):
        s.sichere_in_verzeichnis(config, ziel, behalten=True)
    assert sorted(p.name for p in ziel.iterdir()) == namen, "ValueError vor jeder Wirkung"
    neu2 = s.sichere_in_verzeichnis(config, ziel, behalten=1)
    assert sorted(p.name for p in ziel.iterdir()) == sorted([neu2.name] + fremd)


def test_aufbewahrung_je_modus(tmp_path):
    mock = neue_config(tmp_path / "db", mock_modus=True, mock_heute=dt.date(2024, 6, 30))
    Api(mock)
    ziel = tmp_path / "s"
    ziel.mkdir()
    (ziel / "kontor-sicherung-echt-20200101T000000Z.zip").write_bytes(b"alt")
    neu = kontor.modul("kontor.sicherung").sichere_in_verzeichnis(mock, ziel, behalten=1)
    assert neu.name == "kontor-sicherung-mock-20240630T120000Z.zip"
    assert (ziel / "kontor-sicherung-echt-20200101T000000Z.zip").exists()


def _umgebung(tmp_path: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("KONTOR_") or k.startswith("KONTOR_TESTS_")
           or k == "KONTOR_MUTANT"}
    env.pop("CREDENTIALS_DIRECTORY", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.environ.get("PYTHONPATH", ""), str(REPO)]))
    env["KONTOR_DATENBANK"] = str(tmp_path / "kontor.sqlite3")
    env.update(extra)
    return env


def test_kommandozeile_sicherung(tmp_path):
    env = _umgebung(tmp_path)
    Api(neue_config(tmp_path)).import_kmy(KMY / "minimal.kmy", erwartet=200)
    r = subprocess.run([sys.executable, "-m", "kontor.sicherung", "--verzeichnis", str(tmp_path / "s"),
                        "--behalten", "2"], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    zeilen = r.stdout.strip().splitlines()
    assert len(zeilen) == 1 and Path(zeilen[0]).exists() and NAME.match(Path(zeilen[0]).name)
    ohne = {k: v for k, v in env.items() if k != "KONTOR_DATENBANK"}
    r = subprocess.run([sys.executable, "-m", "kontor.sicherung", "--verzeichnis", str(tmp_path / "s")], env=ohne,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "Traceback" not in r.stderr
    (tmp_path / "datei").write_text("kein Verzeichnis")
    r = subprocess.run([sys.executable, "-m", "kontor.sicherung", "--verzeichnis", str(tmp_path / "datei")], env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 1 and "Traceback" not in r.stderr


def test_kommandozeile_passwort(tmp_path):
    env = _umgebung(tmp_path)
    r = subprocess.run([sys.executable, "-m", "kontor.anmeldung", "passwort-setzen"], env=env, input=PASSWORT + "\n",
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert PASSWORT not in r.stdout + r.stderr and r.stdout.strip()
    assert anmeldung().ist_eingerichtet(neue_config(tmp_path))
    r = subprocess.run([sys.executable, "-m", "kontor.anmeldung", "passwort-setzen"], env=env, input="kurz\n",
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 1 and "kurz" not in r.stdout + r.stderr
    ohne = {k: v for k, v in env.items() if k != "KONTOR_DATENBANK"}
    r = subprocess.run([sys.executable, "-m", "kontor.anmeldung", "passwort-setzen"], env=ohne, input=PASSWORT + "\n",
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and PASSWORT not in r.stdout + r.stderr


# ------------------------------------------------------------------ Datenbank, Beenden, Neustart
def _wal(config) -> Path:
    db = Path(config.aktive_datenbank)
    return db.with_name(db.name + "-wal")


def test_wal_modus_und_checkpoint(tmp_path):
    from fastapi.testclient import TestClient

    config = neue_config(tmp_path / "db")
    app = kontor.create_app(config)
    with TestClient(app) as c:
        assert c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).status_code == 201
        for i in range(30):
            c.post("/api/konten", json={"name": f"Konto {i}", "art": "aufwand"})
    wal = _wal(config)
    assert not wal.exists() or wal.stat().st_size == 0, "nach dem Beenden ist das WAL geleert"
    with sqlite3.connect(f"file:{config.aktive_datenbank}?mode=ro", uri=True) as v:
        assert v.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    kopie = tmp_path / "kopie"
    kopie.mkdir()
    shutil.copy(config.aktive_datenbank, kopie / "kontor.sqlite3")
    neu = Api(neue_config(kopie))
    assert {k["name"] for k in neu.konten()} == {"Giro"} | {f"Konto {i}" for i in range(30)}


def _warte(bedingung, frist: float = 20.0) -> None:
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        if bedingung():
            return
        time.sleep(0.1)
    raise AssertionError("Zeitüberschreitung beim Warten")


def _buchungsbild(api: Api) -> list[tuple]:
    return sorted((b["datum"], b["betrag"], b["verwendungszweck"], tuple(sorted(b["extern_ids"])))
                  for b in api.alle_buchungen())


def test_beenden_waehrend_lauf(tmp_path, netz_gesperrt):
    from fastapi.testclient import TestClient

    config = mock_config(tmp_path / "a", sync_intervall_minuten=60, planer_starten=True, mock_verzoegerung_ms=1500,
                         beenden_frist_sekunden=20)
    app = kontor.create_app(config)
    with TestClient(app) as c:
        _warte(lambda: c.get("/api/sync/status").json()["laeuft"])
        beginn = time.monotonic()
    dauer = time.monotonic() - beginn
    assert dauer <= 25, f"Lifespan-Ende dauerte {dauer:.1f} s"
    wal = _wal(config)
    assert not wal.exists() or wal.stat().st_size == 0
    neu = Api(config)
    ls = laeufe(neu)
    assert len(ls) == 1 and ls[0]["beendet_am"] is not None
    lauf = ls[0]
    if lauf["status"] == "abgebrochen":
        assert any(k["status"] == "abgebrochen" for k in lauf["konten"])
    else:
        assert lauf["status"] == "erfolgreich"
    assert not status(neu)["laeuft"]
    erledigt = [k for k in lauf["konten"] if k["status"] == "erfolgreich"]
    assert all(k["status"] in ("erfolgreich", "abgebrochen") for k in lauf["konten"])
    for b in neu.alle_buchungen():
        assert sum(s["betrag"] for s in b["splits"]) == 0
    # ein vollständiger Lauf ohne Unterbrechung als Vergleich
    vergleich = Api(mock_config(tmp_path / "b"))
    sync(vergleich)
    bild_teil = _buchungsbild(neu)
    assert set(bild_teil) <= set(_buchungsbild(vergleich))
    if not erledigt:
        assert bild_teil == []
    sync(neu)
    assert _buchungsbild(neu) == _buchungsbild(vergleich), "nach erneutem Abruf vollständig, ohne Dubletten"


def test_frist_ueberschritten_schreibt_nichts(tmp_path, netz_gesperrt):
    from fastapi.testclient import TestClient

    config = mock_config(tmp_path, sync_intervall_minuten=60, planer_starten=True, mock_verzoegerung_ms=8000,
                         beenden_frist_sekunden=1)
    app = kontor.create_app(config)
    with TestClient(app) as c:
        _warte(lambda: c.get("/api/sync/status").json()["laeuft"])
        beginn = time.monotonic()
    assert time.monotonic() - beginn <= 6.5
    time.sleep(8)  # ein noch schlafender Abruf darf danach nichts mehr schreiben
    neu = Api(config)
    lauf = laeufe(neu)[0]
    assert lauf["status"] == "abgebrochen" and all(k["status"] == "abgebrochen" for k in lauf["konten"])
    assert neu.alle_buchungen() == []


def test_neustart_ohne_beenden(tmp_path, netz_gesperrt):
    """Harter Abbruch (zweite App ohne Lifespan-Ende der ersten): M2-Regel, Datenbank konsistent."""
    erste = Api(mock_config(tmp_path))
    sync(erste)
    erste.konto("Nach dem Abruf")
    zweite = Api(erste.config)
    assert {k["name"] for k in zweite.konten()} >= {"Nach dem Abruf"}
    with sqlite3.connect(f"file:{erste.config.aktive_datenbank}?mode=ro", uri=True) as v:
        assert v.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_gesundheit(tmp_path):
    api = Api(neue_config(tmp_path))
    g = api.get("/api/gesundheit", erwartet=200)
    assert g.daten == {"status": "ok", "version": api.get("/api/status", erwartet=200).daten["version"]}
    assert "set-cookie" not in g.headers


# ------------------------------------------------------------------ Startmodul
def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_startmodul_und_sigterm(tmp_path, netz_nur_loopback):
    port = _freier_port()
    env = _umgebung(tmp_path, KONTOR_HOST="127.0.0.1", KONTOR_PORT=str(port), KONTOR_ANMELDUNG="1")
    anmeldung().passwort_setzen(neue_config(tmp_path), PASSWORT)
    p = subprocess.Popen([sys.executable, "-m", "kontor"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
    try:
        def bereit():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/gesundheit", timeout=1) as r:
                    return r.status == 200 and json.load(r)["status"] == "ok"
            except (OSError, urllib.error.URLError):
                return False
        _warte(bereit, 30)
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/konten", timeout=5)
        assert e.value.code == 401 and e.value.headers.get("x-content-type-options") == "nosniff"
        assert "uvicorn" not in (e.value.headers.get("server") or "").lower(), "server_header=False"
        p.send_signal(signal.SIGTERM)
        aus, fehler = p.communicate(timeout=30)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode in (0, -signal.SIGTERM), fehler[-2000:]
    assert "Traceback" not in fehler and PASSWORT not in aus + fehler
    assert re.search(r"^INFO kontor", fehler, re.M), "Startmeldung im Format <STUFE> <logger>: …"
    wal = tmp_path / "kontor.sqlite3-wal"
    assert not wal.exists() or wal.stat().st_size == 0


@pytest.mark.parametrize("extra,args", [({"KONTOR_PORT": "acht"}, []), ({}, ["--irgendwas"]),
                                        ({"KONTOR_ANMELDUNG": "vielleicht"}, [])])
def test_startmodul_konfigurationsfehler(tmp_path, extra, args):
    env = _umgebung(tmp_path, **extra)
    r = subprocess.run([sys.executable, "-m", "kontor", *args], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2, (r.returncode, r.stderr[-500:])
    assert "Traceback" not in r.stderr
    if extra:
        assert r.stderr.strip().splitlines()[-1].startswith("Konfigurationsfehler: ")
