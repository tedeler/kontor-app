"""Eigene Tests zum Feature `update` (D-107): Auswertung der Release-Antwort, Prüfdienst, Auftrag, Endpunkte und das
Update-Programm mit untergeschobenem Download und Befehlen. Ohne Netz; nur synthetische Daten."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from kontor import aktualisierung as A
from kontor import version as versionsinfo
from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.fehler import KonfigurationsFehler

WHEEL = b"kein echtes Wheel, nur Testbytes"


def _naechste() -> str:
    return versionsinfo.naechste(versionsinfo.VERSION)


def _release(version: str, daten: bytes = WHEEL, **extra) -> dict:
    ma, mi = versionsinfo.zerlegen(version)
    name = f"kontor-{ma}.{mi}-py3-none-any.whl"
    return {"tag_name": f"v{version}", "draft": False, "prerelease": False,
            "html_url": f"https://github.com/tedeler/kontor-app/releases/tag/v{version}",
            "assets": [{"name": name, "digest": "sha256:" + hashlib.sha256(daten).hexdigest(),
                        "browser_download_url": f"https://github.com/tedeler/kontor-app/releases/download/v{version}/{name}"},
                       {"name": f"kontor-{ma}.{mi}.tar.gz", "digest": None, "browser_download_url": "https://x.invalid/q"}],
            **extra}


# ------------------------------------------------------------------ Auswertung


def test_release_auswerten():
    r = A.release_auswerten(_release("1.07"))
    assert r["version"] == "1.07" and r["sha256"] == hashlib.sha256(WHEEL).hexdigest()
    assert r["wheel_url"].endswith("/kontor-1.7-py3-none-any.whl")


@pytest.mark.parametrize("aenderung", [
    {"tag_name": "1.07"}, {"tag_name": "v1.7"}, {"draft": True}, {"prerelease": True}, {"assets": []},
])
def test_release_auswerten_lehnt_ab(aenderung):
    with pytest.raises(ValueError):
        A.release_auswerten({**_release("1.07"), **aenderung})


def test_release_ohne_digest():
    d = _release("1.07")
    d["assets"][0]["digest"] = None
    with pytest.raises(ValueError):
        A.release_auswerten(d)


def test_neuer():
    assert A.neuer("0.10", "0.09") and A.neuer("1.00", "0.99") and not A.neuer("0.03", "0.03")


# ------------------------------------------------------------------ Prüfdienst und Endpunkte


def _client(tmp_path, abrufen=None, **cfg) -> TestClient:
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", **cfg)))
    if abrufen is not None:
        c.app.state.updates._abrufen = abrufen
    return c


def test_status_ohne_pruefung(tmp_path):
    st = _client(tmp_path).get("/api/update").json()
    assert st["version"] == versionsinfo.VERSION
    assert (st["automatisch"], st["verfuegbar"], st["eingerichtet"], st["installierbar"]) == (False, False, False, False)


def test_pruefen_und_auftrag(tmp_path):
    ziel = _naechste()
    verz = tmp_path / "update"
    c = _client(tmp_path, lambda url: _release(ziel), update_verzeichnis=verz)
    st = c.post("/api/update/pruefen").json()
    assert (st["neueste_version"], st["verfuegbar"], st["installierbar"]) == (ziel, True, True)
    assert c.post("/api/update/installieren", json={"version": "0.01"}).json()["fehler"]["code"] \
        == "update_nicht_verfuegbar"
    r = c.post("/api/update/installieren", json={"version": ziel})
    assert r.status_code == 202 and r.json()["laeuft"] is True and r.json()["installierbar"] is False
    assert json.loads((verz / A.AUFTRAG).read_text())["version"] == ziel
    assert c.post("/api/update/installieren", json={"version": ziel}).json()["fehler"]["code"] == "update_laeuft"


def test_kein_update_bei_gleicher_version(tmp_path):
    c = _client(tmp_path, lambda url: _release(versionsinfo.VERSION), update_verzeichnis=tmp_path / "u")
    st = c.post("/api/update/pruefen").json()
    assert st["neueste_version"] == versionsinfo.VERSION and st["verfuegbar"] is False


def test_fehler_der_gegenstelle_ohne_fremdtext(tmp_path):
    def kaputt(url):
        raise OSError("geheimer Fremdtext")
    st = _client(tmp_path, kaputt).post("/api/update/pruefen").json()
    assert st["fehler"] and "geheimer" not in st["fehler"] and st["verfuegbar"] is False


def test_ohne_verzeichnis_nicht_eingerichtet(tmp_path):
    ziel = _naechste()
    c = _client(tmp_path, lambda url: _release(ziel))
    st = c.post("/api/update/pruefen").json()
    assert st["verfuegbar"] is True and st["installierbar"] is False
    assert c.post("/api/update/installieren", json={"version": ziel}).json()["fehler"]["code"] \
        == "update_nicht_eingerichtet"


def test_mock_modus_ohne_netz(tmp_path):
    def verboten(url):
        raise AssertionError("im Mock-Modus kein Abruf")
    c = _client(tmp_path, verboten, mock_modus=True, update_pruefen=True, update_verzeichnis=tmp_path / "u")
    assert c.get("/api/update").json()["automatisch"] is False
    assert c.post("/api/update/pruefen").json()["fehler"]["code"] == "update_mock"


def test_validierung(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/update/installieren", json={}).status_code == 422
    assert c.post("/api/update/pruefen", json={"x": 1}).status_code == 422


def test_konfiguration_aus_umgebung(tmp_path):
    c = KontorConfig.from_env({"KONTOR_DATENBANK": str(tmp_path / "k"), "KONTOR_UPDATE_PRUEFEN": "1",
                               "KONTOR_UPDATE_INTERVALL_STUNDEN": "6", "KONTOR_UPDATE_VERZEICHNIS": str(tmp_path)})
    assert (c.update_pruefen, c.update_intervall_stunden, c.update_verzeichnis) == (True, 6, tmp_path)
    with pytest.raises(KonfigurationsFehler):
        KontorConfig.from_env({"KONTOR_DATENBANK": "x", "KONTOR_UPDATE_INTERVALL_STUNDEN": "0"})
    with pytest.raises(KonfigurationsFehler):
        KontorConfig(datenbank=tmp_path / "k", update_url="http://example.invalid/")


# ------------------------------------------------------------------ Update-Programm


def _programm(tmp_path, release, daten=WHEEL, version=None, befehl_fehler=None):
    verz = tmp_path / "update"
    verz.mkdir()
    ziel = version or _naechste()
    (verz / A.AUFTRAG).write_text(json.dumps({"version": ziel}))
    befehle: list[list[str]] = []

    def laden(url):
        return json.dumps(release).encode() if url == "https://api.invalid/latest" else daten

    def befehl(args):
        befehle.append(args)
        if befehl_fehler and befehl_fehler in args:
            raise A.UpdateFehler("Befehl fehlgeschlagen")
    erg = A.ausfuehren(verz, tmp_path / "venv", "https://api.invalid/latest", laden=laden, befehl=befehl)
    assert not (verz / A.AUFTRAG).exists() and not (verz / A.LAEUFT).exists()
    assert json.loads((verz / A.ERGEBNIS).read_text()) == erg
    return erg, befehle


def test_programm_erfolg(tmp_path):
    erg, befehle = _programm(tmp_path, _release(_naechste()))
    assert erg["erfolg"] is True
    assert befehle[0] == ["systemctl", "start", "kontor-sicherung.service"]
    assert befehle[1][0] == str(tmp_path / "venv" / "bin" / "pip") and befehle[1][-1].endswith("-py3-none-any.whl")
    assert befehle[2] == ["systemctl", "restart", "kontor.service"]


def test_programm_pruefsumme_falsch(tmp_path):
    erg, befehle = _programm(tmp_path, _release(_naechste()), daten=b"manipuliert")
    assert erg["erfolg"] is False and "Prüfsumme" in erg["meldung"] and befehle == []


def test_programm_andere_version_als_angefordert(tmp_path):
    erg, befehle = _programm(tmp_path, _release(versionsinfo.naechste(_naechste())))
    assert erg["erfolg"] is False and befehle == []


def test_programm_nicht_neuer(tmp_path):
    erg, befehle = _programm(tmp_path, _release(versionsinfo.VERSION), version=versionsinfo.VERSION)
    assert erg["erfolg"] is False and befehle == []


def test_programm_ohne_sicherung_kein_update(tmp_path):
    erg, befehle = _programm(tmp_path, _release(_naechste()), befehl_fehler="kontor-sicherung.service")
    assert erg["erfolg"] is False and len(befehle) == 1, "nach fehlgeschlagener Sicherung nichts installieren"


def test_ausgelieferte_units():
    from importlib import resources
    b = resources.files("kontor.betrieb")
    pfad = b.joinpath("kontor-update.path").read_text()
    dienst = b.joinpath("kontor-update.service").read_text()
    assert "PathExists=/var/lib/kontor/update/auftrag.json" in pfad
    assert "-m kontor.aktualisierung ausfuehren --verzeichnis /var/lib/kontor/update" in dienst
    env = b.joinpath("kontor.env").read_text()
    assert "KONTOR_UPDATE_PRUEFEN=1" in env and "KONTOR_UPDATE_VERZEICHNIS=/var/lib/kontor/update" in env
