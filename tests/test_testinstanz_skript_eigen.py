"""Eigene Tests zum Bedienskript der Testinstanz (D-213): ausgeliefert im Paket `kontor.betrieb`, ruft das Programm
`python -m kontor.testinstanz` mit den richtigen Argumenten auf. Ohne root, ohne systemd; das Programm ist eine
Attrappe, der Port ein lokaler Lauscher."""

from __future__ import annotations

import os
import pathlib
import shutil
import socket
import subprocess
from importlib import resources

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash fehlt")


def _skript() -> str:
    return str(resources.files("kontor.betrieb").joinpath("kontor-test.sh"))


@pytest.fixture
def umgebung(tmp_path: pathlib.Path):
    """Attrappe für das Programm (schreibt seine Argumente mit), Umgebungsdatei mit einem belegten lokalen Port."""
    lauscher = socket.socket()
    lauscher.bind(("127.0.0.1", 0))
    lauscher.listen()
    aufrufe = tmp_path / "aufrufe"
    programm = tmp_path / "python"
    programm.write_text(f'#!/bin/sh\necho "$*" >> "{aufrufe}"\n', encoding="utf-8")
    programm.chmod(0o755)
    env_datei = tmp_path / "kontor-test.env"
    env_datei.write_text(f"KONTOR_MOCK_MODUS=1\nKONTOR_PORT={lauscher.getsockname()[1]}\n", encoding="utf-8")
    umg = {**os.environ, "KONTOR_PYTHON": str(programm), "KONTOR_TEST_ENV": str(env_datei),
           "KONTOR_TEST_MERKDATEI": str(tmp_path / "branch")}
    yield umg, aufrufe, lauscher.getsockname()[1]
    lauscher.close()


def _lauf(umg: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", _skript(), *args], env=umg, capture_output=True, text=True, timeout=60)


def test_skript_ist_ausgeliefert_und_fehlerfrei():
    assert subprocess.run(["bash", "-n", _skript()], capture_output=True).returncode == 0
    hilfe = subprocess.run(["bash", _skript(), "hilfe"], capture_output=True, text=True)
    assert hilfe.returncode == 0 and "kontor-test start <branch>" in hilfe.stdout
    assert subprocess.run(["bash", _skript(), "unbekannt"], capture_output=True).returncode == 2


@pytest.mark.skipif(os.geteuid() != 0, reason="das Skript verlangt root")
def test_start_neu_stop_loeschen(umgebung):
    umg, aufrufe, port = umgebung
    e = _lauf(umg, "start", "monatsbericht")
    assert e.returncode == 0, e.stderr
    assert f":{port}" in e.stdout  # Port aus der Umgebungsdatei, nicht fest 8081
    assert _lauf(umg, "start", "main").returncode == 0
    assert _lauf(umg, "start", "feature/x-y").returncode == 0
    assert _lauf(umg, "neu").returncode == 0
    assert _lauf(umg, "stop").returncode == 0
    assert _lauf(umg, "loeschen").returncode == 0
    assert aufrufe.read_text(encoding="utf-8").splitlines() == [
        "-m kontor.testinstanz einrichten feature/monatsbericht",
        "-m kontor.testinstanz einrichten main",
        "-m kontor.testinstanz einrichten feature/x-y",
        "-m kontor.testinstanz einrichten feature/x-y",
        "-m kontor.testinstanz stoppen",
        "-m kontor.testinstanz stoppen --loeschen",
    ]


@pytest.mark.skipif(os.geteuid() != 0, reason="das Skript verlangt root")
def test_demo_und_neu_merken_die_art(umgebung):
    """Feature demodaten: ``demo [branch]`` baut Demodaten statt einer Kopie; ``neu`` wiederholt, was zuletzt lief."""
    umg, aufrufe, _ = umgebung
    e = _lauf(umg, "demo")
    assert e.returncode == 0, e.stderr
    assert "ohne Anmeldung" in e.stdout and "Haushaltspasswort" not in e.stdout
    assert _lauf(umg, "neu").returncode == 0
    status = _lauf(umg, "status").stdout
    assert "main" in status and "Demodaten" in status
    assert _lauf(umg, "demo", "berichte").returncode == 0
    e = _lauf(umg, "start", "berichte")
    assert e.returncode == 0 and "Haushaltspasswort" in e.stdout
    assert _lauf(umg, "neu").returncode == 0
    assert "Kopie" in _lauf(umg, "status").stdout
    assert aufrufe.read_text(encoding="utf-8").splitlines() == [
        "-m kontor.testinstanz demo main",
        "-m kontor.testinstanz demo main",
        "-m kontor.testinstanz demo feature/berichte",
        "-m kontor.testinstanz einrichten feature/berichte",
        "-m kontor.testinstanz einrichten feature/berichte",
    ]


@pytest.mark.skipif(os.geteuid() != 0, reason="das Skript verlangt root")
def test_fehlerfaelle(umgebung, tmp_path):
    umg, aufrufe, _ = umgebung
    assert _lauf(umg, "start").returncode == 1          # Branch fehlt
    assert _lauf(umg, "neu").returncode == 1            # noch kein Branch gemerkt
    assert not aufrufe.exists()
    # Scheitert das Programm, merkt sich das Skript den Branch nicht
    kaputt = tmp_path / "kaputt"
    kaputt.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    kaputt.chmod(0o755)
    assert _lauf({**umg, "KONTOR_PYTHON": str(kaputt)}, "start", "x").returncode == 1
    assert not pathlib.Path(umg["KONTOR_TEST_MERKDATEI"]).exists()
