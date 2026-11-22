"""Entwicklungstests zu D-251: Sicherung und ``passwort-setzen`` laufen ohne Credentials, auch wenn die
Hauptinstanz die PIN über systemd-creds bekommt. Synthetische Daten."""

from __future__ import annotations

import pytest

from kontor import sicherung
from kontor.config import KontorConfig, KonfigurationsFehler


def test_werkzeug_konfiguration(tmp_path):
    env = {"KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"), "KONTOR_BANK_PIN_QUELLE": "systemd-creds"}
    with pytest.raises(KonfigurationsFehler):
        KontorConfig.from_env(env)                     # der Dienst prüft weiter streng
    assert KontorConfig.fuer_werkzeug(env).bank_pin_quelle == "eingabe"
    mit = {**env, "CREDENTIALS_DIRECTORY": str(tmp_path)}
    assert KontorConfig.fuer_werkzeug(mit).bank_pin_quelle == "systemd-creds"
    with pytest.raises(KonfigurationsFehler):          # andere Fehler bleiben Fehler
        KontorConfig.fuer_werkzeug({**env, "KONTOR_MAIL_ERSTABRUF_TAGE": "5000"})


def test_sicherung_ohne_credentials(tmp_path, monkeypatch, capsys):
    for k in list(__import__("os").environ):
        if k.startswith("KONTOR_") or k == "CREDENTIALS_DIRECTORY":
            monkeypatch.delenv(k)
    monkeypatch.setenv("KONTOR_DATENBANK", str(tmp_path / "k.sqlite3"))
    monkeypatch.setenv("KONTOR_BANK_PIN_QUELLE", "systemd-creds")
    assert sicherung.main(["--verzeichnis", str(tmp_path / "s")]) == 0
    assert list((tmp_path / "s").glob("kontor-sicherung-echt-*.zip"))
