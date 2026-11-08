"""Weboberfläche: Auslieferung, Navigation, Mock-Hinweis, keine externen Ressourcen."""

from __future__ import annotations

import re
from pathlib import Path

import kontor

WEB = Path(kontor.__file__).parent / "web"
NAVIGATION = ["Finanzübersicht", "Konten", "Kategorien", "Wiederkehrende Buchungen", "Kredite", "Berichte",
              "Import", "Einstellungen"]


def test_startseite_echt(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "mock-hinweis" not in r.text
    for eintrag in NAVIGATION:
        assert eintrag in r.text
    assert r.text.count("später") == 3, "nicht umgesetzte Bereiche sind als später gekennzeichnet"


def test_startseite_mock(mock_client):
    r = mock_client.get("/")
    assert 'id="mock-hinweis"' in r.text and "Mock-Modus" in r.text


def test_assets(client):
    for pfad, typ in [("/static/app.js", "javascript"), ("/static/app.css", "text/css"),
                      ("/static/icon.svg", "image/svg+xml"), ("/manifest.webmanifest", "manifest")]:
        r = client.get(pfad)
        assert r.status_code == 200, pfad
        assert typ in r.headers["content-type"], (pfad, r.headers["content-type"])


def test_keine_externen_ressourcen():
    """Kein CDN, keine Laufzeit-Downloads: alle Ressourcen liegen im Paket."""
    for datei in WEB.rglob("*"):
        if datei.is_file():
            text = datei.read_text(encoding="utf-8")
            treffer = [u for u in re.findall(r"https?://[^\s\"')]+", text) if "www.w3.org/2000/svg" not in u]
            assert not treffer, f"{datei.name}: externe Adresse {treffer}"


def test_oberflaeche_nutzt_nur_spezifizierte_api():
    js = (WEB / "static" / "app.js").read_text(encoding="utf-8")
    pfade = set(re.findall(r"[\"`](/api/[a-z/]+)", js))
    erlaubt = {"/api/konten", "/api/tags", "/api/empfaenger", "/api/kontenuebersicht", "/api/status",
               "/api/dubletten", "/api/buchungen", "/api/buchungen/mehrfach/kategorie",
               "/api/buchungen/mehrfach/tags", "/api/import/kmymoney", "/api/importe", "/api/konten/",
               "/api/buchungen/", "/api/tags/", "/api/dubletten/"}
    assert pfade <= erlaubt, pfade - erlaubt
