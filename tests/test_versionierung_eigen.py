"""Eigene Tests: Versionsnummer, /api/version, About-Fenster in der Hülle (D-105)."""

from __future__ import annotations

import json
import re

import pytest

import kontor
from kontor import release, version as v


def test_versionsdatei_hat_schema_major_minor():
    assert re.fullmatch(r"(0|[1-9][0-9]*)\.[0-9]{2,}", kontor.__version__)
    assert kontor.__version__ == v.VERSION


@pytest.mark.parametrize(("alt", "major", "neu"), [
    ("0.00", False, "0.01"), ("0.07", False, "0.08"), ("0.09", False, "0.10"), ("0.99", False, "0.100"),
    ("1.00", False, "1.01"), ("0.07", True, "1.00"), ("1.42", True, "2.00"),
])
def test_naechste(alt, major, neu):
    assert v.naechste(alt, major=major) == neu


@pytest.mark.parametrize("falsch", ["1", "1.0", "1.0.0", "01.00", "a.00", "1.00-dev", ""])
def test_zerlegen_lehnt_ab(falsch):
    with pytest.raises(ValueError):
        v.zerlegen(falsch)


def test_kommandozeile(tmp_path, capsys):
    datei = tmp_path / "VERSION"
    datei.write_text("0.07\n")
    assert release.main(["hochzaehlen", str(datei)]) == 0
    assert datei.read_text() == "0.08\n" and capsys.readouterr().out.strip() == "0.08"
    release.main(["hochzaehlen", "--major", str(datei)])
    assert datei.read_text() == "1.00\n"
    b = tmp_path / "build.json"
    release.main(["build", str(b), "--commit", "0123456789abcdef", "--datum", "2026-11-10"])
    assert json.loads(b.read_text()) == {"commit": "0123456789abcdef", "build_datum": "2026-11-10"}


def test_build_ohne_datei_ist_entwicklungsstand(monkeypatch):
    monkeypatch.setattr(v, "_paketdatei", lambda name: None)
    assert v.build() == {"commit": None, "build_datum": None, "entwicklungsstand": True}


def test_build_aus_datei(monkeypatch):
    monkeypatch.setattr(v, "_paketdatei",
                        lambda name: '{"commit": "0123456789abcdef", "build_datum": "2026-11-10"}')
    assert v.build() == {"commit": "0123456789ab", "build_datum": "2026-11-10", "entwicklungsstand": False}


def test_api_version(client, config):
    r = client.get("/api/version")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "Kontor" and d["version"] == kontor.__version__
    assert d["modus"] == "echt" and d["datenbank"] == str(config.aktive_datenbank)
    assert isinstance(d["datenbank_schema"], int) and isinstance(d["sicherung_schema"], int)
    assert d["repository"].startswith("https://github.com/")
    assert set(d) == {"name", "version", "commit", "build_datum", "entwicklungsstand", "python", "repository",
                      "modus", "datenbank", "datenbank_schema", "sicherung_schema"}


def test_status_und_gesundheit_nennen_dieselbe_version(client):
    assert client.get("/api/status").json()["version"] == kontor.__version__


def test_huelle_zeigt_version_in_der_navigation(client):
    html = client.get("/").text
    knopf = re.search(r'<button[^>]*data-testid="version-knopf"[^>]*>([^<]*)</button>', html, re.S)
    assert knopf and knopf.group(1).strip() == f"Version {kontor.__version__}"
    assert "{{VERSION}}" not in html
