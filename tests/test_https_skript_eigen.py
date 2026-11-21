"""Eigene Tests zum Skript `kontor-https` (D-239): stellt Kontor und die Testinstanz auf HTTPS über Tailscale Serve
um und wieder zurück. Ohne Tailscale und ohne systemd: beide sind Attrappen, die ihre Aufrufe mitschreiben; die
Umgebungsdateien liegen in einem temporären Verzeichnis, der Port ist ein lokaler Lauscher."""

from __future__ import annotations

import os
import pathlib
import shutil
import socket
import subprocess
import sys
from importlib import resources

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash fehlt")
ROOT = pytest.mark.skipif(os.geteuid() != 0, reason="das Skript verlangt root")
NAME = "kontor.example.invalid"


def _skript(name: str = "kontor-https.sh") -> str:
    return str(resources.files("kontor.betrieb").joinpath(name))


def _attrappe(pfad: pathlib.Path, inhalt: str) -> None:
    pfad.write_text("#!/bin/sh\n" + inhalt, encoding="utf-8")
    pfad.chmod(0o755)


@pytest.fixture
def umgebung(tmp_path: pathlib.Path):
    lauscher = socket.socket()
    lauscher.bind(("127.0.0.1", 0))
    lauscher.listen()
    port = lauscher.getsockname()[1]
    aufrufe = tmp_path / "aufrufe"
    werkzeuge = tmp_path / "bin"
    werkzeuge.mkdir()
    # Tailscale: meldet einen verbundenen Knoten; „serve“ scheitert, wenn die Datei „serve-kaputt“ existiert
    _attrappe(werkzeuge / "tailscale", f'''echo "tailscale $*" >> "{aufrufe}"
if [ "$1" = status ]; then
  if [ -e "{tmp_path}/getrennt" ]; then echo '{{"BackendState": "NeedsLogin", "Self": {{"DNSName": ""}}}}'
  else echo '{{"BackendState": "Running", "Self": {{"DNSName": "{NAME}."}}}}'; fi
  exit 0
fi
if [ "$1" = serve ] && [ -e "{tmp_path}/serve-kaputt" ]; then echo "serve: HTTPS nicht eingeschaltet" >&2; exit 1; fi
exit 0
''')
    # systemctl: schreibt mit; „is-active“ nur für die Testinstanz wahr, wenn die Datei „test-laeuft“ existiert
    _attrappe(werkzeuge / "systemctl", f'''echo "systemctl $*" >> "{aufrufe}"
if [ "$1" = is-active ]; then [ -e "{tmp_path}/test-laeuft" ]; exit $?; fi
exit 0
''')
    haupt = tmp_path / "kontor.env"
    haupt.write_text("# Kontor\nKONTOR_DATENBANK=/var/lib/kontor/kontor.sqlite3\nKONTOR_HOST=0.0.0.0\n"
                     f"KONTOR_PORT={port}\n#KONTOR_SITZUNG_COOKIE_SECURE=1\nKONTOR_ANMELDUNG=1\n", encoding="utf-8")
    haupt.chmod(0o640)
    test = tmp_path / "kontor-test.env"
    umg = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    umg.update(PATH=f"{werkzeuge}:{umg['PATH']}", KONTOR_PYTHON=sys.executable, KONTOR_HAUPT_ENV=str(haupt),
               KONTOR_TEST_ENV=str(test), KONTOR_TEST_MERKDATEI=str(tmp_path / "branch"))
    yield umg, tmp_path, haupt, test, aufrufe, port
    lauscher.close()


def _lauf(umg, *args, skript="kontor-https.sh"):
    return subprocess.run(["bash", _skript(skript), *args], env=umg, capture_output=True, text=True, timeout=120)


def _werte(datei: pathlib.Path) -> dict[str, str]:
    return dict(z.split("=", 1) for z in datei.read_text(encoding="utf-8").splitlines() if z and not z.startswith("#"))


def _aufrufe(datei: pathlib.Path) -> list[str]:
    return datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []


def test_skript_ist_ausgeliefert_und_fehlerfrei():
    assert os.access(_skript(), os.X_OK)
    assert subprocess.run(["bash", "-n", _skript()], capture_output=True).returncode == 0
    hilfe = subprocess.run(["bash", _skript(), "hilfe"], capture_output=True, text=True)
    assert hilfe.returncode == 0 and "kontor-https einrichten" in hilfe.stdout and "kontor-https zurueck" in hilfe.stdout
    assert subprocess.run(["bash", _skript(), "unbekannt"], capture_output=True).returncode == 2


@ROOT
def test_einrichten_stellt_beide_instanzen_um_und_ist_wiederholbar(umgebung):
    umg, tmp, haupt, test, aufrufe, port = umgebung
    vorher = haupt.read_text(encoding="utf-8")
    e = _lauf(umg, "einrichten")
    assert e.returncode == 0, e.stderr + e.stdout
    w = _werte(haupt)
    assert (w["KONTOR_HOST"], w["KONTOR_SITZUNG_COOKIE_SECURE"], w["KONTOR_OEFFENTLICHE_URL"]) == (
        "127.0.0.1", "1", f"https://{NAME}")
    assert w["KONTOR_PORT"] == str(port) and w["KONTOR_ANMELDUNG"] == "1"          # Übriges unberührt
    assert "#KONTOR_SITZUNG_COOKIE_SECURE=1" in haupt.read_text(encoding="utf-8")   # Kommentare bleiben
    assert oct(haupt.stat().st_mode & 0o777) == "0o640"
    assert (tmp / "kontor.env.vor-https").read_text(encoding="utf-8") == vorher
    # Testinstanz: aus der Vorlage angelegt, eigener HTTPS-Port, Mock-Modus unverändert
    t = _werte(test)
    assert (t["KONTOR_HOST"], t["KONTOR_SITZUNG_COOKIE_SECURE"], t["KONTOR_OEFFENTLICHE_URL"]) == (
        "127.0.0.1", "1", f"https://{NAME}:8443")
    assert t["KONTOR_MOCK_MODUS"] == "1" and t["KONTOR_PORT"] == "8081"
    a = _aufrufe(aufrufe)
    assert f"tailscale serve --bg --https=443 http://127.0.0.1:{port}" in a
    assert "systemctl restart kontor.service" in a
    assert a.index(f"tailscale serve --bg --https=443 http://127.0.0.1:{port}") < a.index("systemctl restart kontor.service")
    assert not any("8443" in x for x in a), "die Testinstanz läuft nicht: keine Freigabe"
    assert f"https://{NAME}:8443" in e.stdout
    # zweiter Lauf: gleiche Werte, keine doppelten Zeilen, die erste Sicherung bleibt
    assert _lauf(umg, "einrichten", "--test-port", "9443").returncode == 0
    text = haupt.read_text(encoding="utf-8")
    assert text.count("KONTOR_OEFFENTLICHE_URL=") == 1 and text.count("\nKONTOR_HOST=") == 1
    assert _werte(test)["KONTOR_OEFFENTLICHE_URL"] == f"https://{NAME}:9443"
    assert (tmp / "kontor.env.vor-https").read_text(encoding="utf-8") == vorher


@ROOT
def test_laufende_testinstanz_wird_mit_umgestellt(umgebung):
    umg, tmp, haupt, test, aufrufe, port = umgebung
    test.write_text(f"KONTOR_MOCK_MODUS=1\nKONTOR_HOST=0.0.0.0\nKONTOR_PORT={port}\n", encoding="utf-8")
    (tmp / "test-laeuft").touch()
    e = _lauf(umg, "einrichten", "--name", "anders.example.invalid")
    assert e.returncode == 0, e.stderr
    a = _aufrufe(aufrufe)
    assert "systemctl restart kontor-test.service" in a
    assert f"tailscale serve --bg --https=8443 http://127.0.0.1:{port}" in a
    assert _werte(haupt)["KONTOR_OEFFENTLICHE_URL"] == "https://anders.example.invalid"
    assert (tmp / "kontor-test.env.vor-https").read_text(encoding="utf-8").count("KONTOR_HOST=0.0.0.0") == 1


@ROOT
def test_zurueck_stellt_den_stand_vorher_her(umgebung):
    umg, tmp, haupt, test, aufrufe, port = umgebung
    vorher = _werte(haupt)
    assert _lauf(umg, "einrichten").returncode == 0
    aufrufe.unlink()
    e = _lauf(umg, "zurueck")
    assert e.returncode == 0, e.stderr
    assert _werte(haupt) == vorher                                  # Host wieder 0.0.0.0, die beiden anderen entfallen
    t = _werte(test)
    assert t["KONTOR_HOST"] == "0.0.0.0" and "KONTOR_OEFFENTLICHE_URL" not in t and "KONTOR_SITZUNG_COOKIE_SECURE" not in t
    a = _aufrufe(aufrufe)
    assert "tailscale serve --https=443 off" in a and "tailscale serve --https=8443 off" in a
    assert "systemctl restart kontor.service" in a
    assert "http" in e.stdout and "0.0.0.0" in e.stdout


@ROOT
def test_fehler_lassen_kontor_unveraendert(umgebung):
    umg, tmp, haupt, test, aufrufe, _ = umgebung
    vorher = haupt.read_text(encoding="utf-8")
    # Tailscale nicht verbunden
    (tmp / "getrennt").touch()
    e = _lauf(umg, "einrichten")
    assert e.returncode == 1 and "tailscale up" in e.stderr
    (tmp / "getrennt").unlink()
    # Freigabe scheitert (HTTPS-Zertifikate nicht eingeschaltet): nichts geändert, kein Neustart
    (tmp / "serve-kaputt").touch()
    e = _lauf(umg, "einrichten")
    assert e.returncode == 1 and "nichts geaendert" in e.stderr and "HTTPS-Zertifikate" in e.stderr
    assert haupt.read_text(encoding="utf-8") == vorher and not test.exists()
    assert not any(x.startswith("systemctl restart") for x in _aufrufe(aufrufe))
    (tmp / "serve-kaputt").unlink()
    # Tailscale fehlt ganz
    ohne = {**umg, "KONTOR_TAILSCALE": str(tmp / "gibt-es-nicht")}
    e = _lauf(ohne, "einrichten")
    assert e.returncode == 1 and "--tailscale-installieren" in e.stderr
    # falsche Optionen
    assert _lauf(umg, "einrichten", "--test-port", "443").returncode == 1
    assert _lauf(umg, "einrichten", "--test-port", "abc").returncode == 1
    assert _lauf(umg, "einrichten", "--name", "böse name").returncode == 1
    assert _lauf(umg, "einrichten", "--unbekannt").returncode == 1
    assert haupt.read_text(encoding="utf-8") == vorher


@ROOT
def test_status_zeigt_einstellungen(umgebung):
    umg, *_ = umgebung
    e = _lauf(umg, "status")
    assert e.returncode == 0 and "HTTPS ist nicht eingerichtet." in e.stdout
    assert _lauf(umg, "einrichten").returncode == 0
    e = _lauf(umg, "status")
    assert e.returncode == 0 and f"KONTOR_OEFFENTLICHE_URL=https://{NAME}" in e.stdout
    assert f"https://{NAME}:8443" in e.stdout and "tailscale serve status" in e.stdout


@ROOT
def test_testinstanz_skript_schaltet_die_freigabe_ein_und_aus(umgebung, tmp_path):
    """`kontor-test start` gibt die Testinstanz über HTTPS frei und nennt die https-Adresse; ohne HTTPS bleibt http."""
    umg, tmp, haupt, test, aufrufe, port = umgebung
    programm = tmp / "python-attrappe"
    _attrappe(programm, f'echo "python $*" >> "{aufrufe}"\n')
    test.write_text(f"KONTOR_MOCK_MODUS=1\nKONTOR_PORT={port}\n", encoding="utf-8")
    ohne = {**umg, "KONTOR_PYTHON": str(programm)}
    e = _lauf(ohne, "start", "sammel3", skript="kontor-test.sh")
    assert e.returncode == 0, e.stderr
    assert f"http://" in e.stdout and f":{port}" in e.stdout and "https://" not in e.stdout
    assert not any(x.startswith("tailscale") for x in _aufrufe(aufrufe))
    # mit HTTPS
    test.write_text(f"KONTOR_MOCK_MODUS=1\nKONTOR_PORT={port}\nKONTOR_OEFFENTLICHE_URL=https://{NAME}:8443\n", encoding="utf-8")
    aufrufe.unlink()
    e = _lauf(ohne, "start", "sammel3", skript="kontor-test.sh")
    assert e.returncode == 0, e.stderr
    assert f"Testinstanz laeuft: https://{NAME}:8443" in e.stdout
    assert _aufrufe(aufrufe) == ["python -m kontor.testinstanz einrichten feature/sammel3",
                                 f"tailscale serve --bg --https=8443 http://127.0.0.1:{port}"]
    status = _lauf(ohne, "status", skript="kontor-test.sh")
    assert status.returncode == 0
    aufrufe.unlink()
    assert _lauf(ohne, "stop", skript="kontor-test.sh").returncode == 0
    assert _aufrufe(aufrufe) == ["tailscale serve --https=8443 off", "python -m kontor.testinstanz stoppen"]
    # Freigabe scheitert: deutliche Meldung, Rückgabecode 1
    (tmp / "serve-kaputt").touch()
    e = _lauf(ohne, "neu", skript="kontor-test.sh")
    assert e.returncode == 1 and "HTTPS-Freigabe ist fehlgeschlagen" in e.stderr


def test_start_warnt_bei_secure_cookie_ohne_https_adresse(tmp_path, caplog):
    from kontor.app import create_app
    from kontor.config import KontorConfig
    import logging
    with caplog.at_level(logging.WARNING, logger="kontor"):
        create_app(KontorConfig(datenbank=tmp_path / "a.sqlite3", planer_starten=False, sitzung_cookie_secure=True))
    assert any("KONTOR_OEFFENTLICHE_URL" in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="kontor"):
        create_app(KontorConfig(datenbank=tmp_path / "b.sqlite3", planer_starten=False, sitzung_cookie_secure=True,
                                oeffentliche_url="https://kontor.example.invalid"))
    assert not any("KONTOR_OEFFENTLICHE_URL" in r.getMessage() for r in caplog.records)


def test_herkunftspruefung_hinter_https_proxy_braucht_die_oeffentliche_adresse(tmp_path):
    """Hinter dem Proxy kommt die Anfrage per http an, der Browser meldet die https-Herkunft: ohne
    KONTOR_OEFFENTLICHE_URL wird sie abgelehnt (403), mit ihr angenommen."""
    from fastapi.testclient import TestClient

    from kontor.app import create_app
    from kontor.config import KontorConfig
    herkunft = {"Origin": f"https://{NAME}"}
    for url, erwartet in ((None, 403), (f"https://{NAME}", 409), (f"https://{NAME}:8443", 403)):
        config = KontorConfig(datenbank=tmp_path / f"{erwartet}-{bool(url)}-{len(url or '')}.sqlite3", planer_starten=False,
                              anmeldung=True, sitzung_cookie_secure=True, oeffentliche_url=url)
        with TestClient(create_app(config), base_url=f"http://{NAME}") as c:
            r = c.post("/api/anmeldung", json={"passwort": "synthetisch-falsch"}, headers=herkunft)
            assert r.status_code == erwartet, (url, r.text)      # 409: Herkunft angenommen, nur noch nicht eingerichtet
