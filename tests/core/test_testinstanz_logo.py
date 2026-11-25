"""Core-Tests zum Feature „testinstanz-logo“ (D-286): Im Mock-Modus – also in der Testinstanz – trägt Kontor ein
eigenes Logo und einen eigenen Namen, auch als installierte Anwendung auf dem Handy. So lassen sich Haupt- und
Testinstanz auf dem Startbildschirm und in der Tab-Leiste unterscheiden. Die Adressen bleiben dieselben."""

from __future__ import annotations

import json
import re
import struct

from kontor.app import WEB

SYMBOLE = ("icon.svg", "icon-192.png", "icon-512.png", "icon-maskable-512.png")


def _manifest(c) -> dict:
    r = c.get("/oeffentlich/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    return json.loads(r.content)


def _png_groesse(roh: bytes) -> tuple[int, int]:
    assert roh[:8] == b"\x89PNG\r\n\x1a\n" and roh[12:16] == b"IHDR", "kein PNG"
    return struct.unpack(">II", roh[16:24])


def _themenfarbe(seite: str) -> str:
    return re.search(r'<meta name="theme-color" content="(#[0-9a-fA-F]{6})">', seite)[1]


def test_echtbetrieb_bleibt_wie_bisher(client):
    m = _manifest(client)
    assert (m["name"], m["short_name"]) == ("Kontor", "Kontor")
    for name in SYMBOLE:
        assert client.get(f"/oeffentlich/{name}").content == (WEB / "oeffentlich" / name).read_bytes(), name
    seite = client.get("/").text
    assert "<title>Kontor</title>" in seite and _themenfarbe(seite) == m["theme_color"]


def test_mock_modus_hat_eigenen_namen_und_eigene_farbe(client, mock_client):
    echt, test = _manifest(client), _manifest(mock_client)
    assert (test["name"], test["short_name"]) == ("Kontor Test", "Kontor Test")
    assert test["theme_color"] != echt["theme_color"] and re.fullmatch(r"#[0-9a-fA-F]{6}", test["theme_color"])
    # alles Übrige wie im Echtbetrieb: dieselben Adressen, dieselbe Art der Installation
    for feld in ("id", "start_url", "scope", "display", "lang", "background_color"):
        assert test[feld] == echt[feld], feld
    assert [(i["src"], i["sizes"], i["purpose"]) for i in test["icons"]] == [
        (i["src"], i["sizes"], i["purpose"]) for i in echt["icons"]]
    seite = mock_client.get("/").text
    assert "<title>Kontor Test</title>" in seite and _themenfarbe(seite) == test["theme_color"]
    # iOS nimmt Namen und Symbol der installierten Anwendung aus der Seite, nicht aus dem Manifest
    assert '<meta name="apple-mobile-web-app-title" content="Kontor Test">' in seite
    assert '<link rel="apple-touch-icon" href="/oeffentlich/icon-192.png">' in seite


def test_mock_modus_liefert_eigene_symbole_unter_denselben_adressen(client, mock_client):
    for icon in _manifest(mock_client)["icons"]:
        r = mock_client.get(icon["src"])
        assert r.status_code == 200 and r.headers["content-type"] == icon["type"] == "image/png", icon
        assert "x".join(map(str, _png_groesse(r.content))) == icon["sizes"], icon
        assert r.content != client.get(icon["src"]).content, f"{icon['src']} ist das Symbol der Hauptinstanz"
    svg = mock_client.get("/oeffentlich/icon.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")
    assert svg.content != client.get("/oeffentlich/icon.svg").content and b"<svg" in svg.content
    assert b"<script" not in svg.content and b"href" not in svg.content, "ohne Skript und ohne fremde Ressourcen"


def test_symbole_im_mock_modus_mit_etag_wie_alle_statischen_dateien(mock_client):
    for name in SYMBOLE + ("manifest.webmanifest",):
        r = mock_client.get(f"/oeffentlich/{name}")
        assert r.headers["cache-control"] == "no-cache" and r.headers["etag"], name
        zweite = mock_client.get(f"/oeffentlich/{name}", headers={"If-None-Match": r.headers["etag"]})
        assert zweite.status_code == 304 and not zweite.content, name


def test_anmeldeseite_im_mock_modus(tmp_path):
    from fastapi.testclient import TestClient

    from kontor.app import create_app
    from kontor.config import KontorConfig

    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, anmeldung=True)))
    seite = c.get("/anmelden").text
    assert _themenfarbe(seite) == _manifest(c)["theme_color"] and "Kontor Test" in seite
    # Manifest und Symbole sind öffentlich wie bisher (sicherheit.md 3.1): die Anmeldeseite braucht sie
    assert c.get("/oeffentlich/icon.svg").status_code == 200
    assert c.get("/oeffentlich/icon-192.png").status_code == 200
