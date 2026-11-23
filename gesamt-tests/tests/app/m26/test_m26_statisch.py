"""M26: Auslieferung statischer Dateien (oberflaeche.md 36.8, sicherheit.md 6; E-246, E-247) – REST ohne Browser."""

from __future__ import annotations

from html.parser import HTMLParser

import pytest

from tests.hilfen.api import neue_api


class _Verweise(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pfade: list[str] = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("src", "href") and v and v.startswith(("/oeffentlich/", "/static/")):
                self.pfade.append(v.split("#")[0])


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    return neue_api(tmp_path_factory.mktemp("m26"), mock_modus=True)


def _statische_pfade(api) -> list[str]:
    p = _Verweise()
    p.feed(api.get("/", erwartet=200).text)
    pfade = list(dict.fromkeys(p.pfade + ["/oeffentlich/manifest.webmanifest"]))
    assert any(x.endswith(".js") for x in pfade), f"die Hülle lädt Skripte unter /oeffentlich/: {pfade}"
    return pfade


@pytest.mark.kern
def test_no_cache_und_etag(api):
    for pfad in _statische_pfade(api):
        r = api.get(pfad)
        assert r.status_code == 200, pfad
        cc = [t.strip().lower() for t in r.headers.get("cache-control", "").split(",")]
        assert "no-cache" in cc, f"{pfad}: Cache-Control {r.headers.get('cache-control')!r} (36.8.1)"
        assert r.headers.get("etag"), f"{pfad}: ETag fehlt (36.8.1)"


@pytest.mark.kern
def test_bedingte_anfrage_304_ohne_koerper(api):
    for pfad in _statische_pfade(api):
        etag = api.get(pfad, erwartet=200).headers.get("etag")
        assert etag, f"{pfad}: ETag fehlt (36.8.1)"
        r = api.get(pfad, headers={"If-None-Match": etag})
        assert r.status_code == 304, f"{pfad}: passendes If-None-Match → 304, erhalten {r.status_code}"
        assert r.content == b"", f"{pfad}: 304 ohne Körper"
        r = api.get(pfad, headers={"If-None-Match": '"nicht-passend-4711"'})
        assert r.status_code == 200 and r.content, f"{pfad}: unpassendes If-None-Match → 200 mit Inhalt"


@pytest.mark.kern
def test_huelle_sw_und_api_unveraendert(api):
    """36.8.2: Hülle und /api/ behalten no-store, /sw.js no-cache oder no-store."""
    assert "no-store" in api.get("/", erwartet=200).headers.get("cache-control", "")
    assert "no-store" in api.get("/api/status", erwartet=200).headers.get("cache-control", "")
    cc = api.get("/sw.js", erwartet=200).headers.get("cache-control", "")
    assert "no-cache" in cc or "no-store" in cc
