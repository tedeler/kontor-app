"""M8: Auslieferung der Oberfläche durch den Server (oberflaeche.md 2, 3, 18; sicherheit.md 3, 6, 7) – ohne Browser."""

from __future__ import annotations

import json
import re
import struct
from html.parser import HTMLParser

import pytest

from tests.hilfen.api import neue_api
from tests.hilfen.m7 import csp, m7_api
from tests.hilfen.m8 import OBERFLAECHE, lade_erwartung

# M28 (oberflaeche.md 37.3, E-254): /wiederkehrend entfällt (404, tests/app/m28/test_m28_routen.py)
ROUTEN = ["/", "/konten", "/kategorien", "/kredite", "/berichte", "/import", "/einstellungen",
          "/protokoll", "/empfaenger", "/regeln", "/vorlagen", "/dubletten", "/sync", "/benachrichtigungen",
          "/suche?q=B%C3%A4ckerei", "/konten/{giro}?von=2024-03-01&status=bestaetigt&sortierung=betrag",
          "/konten/{giro}", "/kredite/1", "/tan/1", "/mail/postfaecher/1"]


class _Html(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.skripte: list[tuple[dict, str]] = []
        self._im_skript: dict | None = None
        self._skript_text = ""

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append((tag, a))
        if tag == "script":
            self._im_skript, self._skript_text = a, ""

    def handle_data(self, data):
        if self._im_skript is not None:
            self._skript_text += data

    def handle_endtag(self, tag):
        if tag == "script" and self._im_skript is not None:
            self.skripte.append((self._im_skript, self._skript_text))
            self._im_skript = None


def _html(text: str) -> _Html:
    p = _Html()
    p.feed(text)
    return p


@pytest.fixture(scope="module")
def m8_api(tmp_path_factory):
    api = neue_api(tmp_path_factory.mktemp("m8"), mock_modus=True)
    api.import_kmy(OBERFLAECHE, erwartet=200)
    return api


def _giro(api) -> int:
    return next(k["id"] for k in api.konten() if k["extern_id"] == lade_erwartung()["m8"]["konten"]["giro"])


@pytest.mark.kern
@pytest.mark.parametrize("route", ROUTEN)
def test_jede_route_liefert_die_huelle(m8_api, route):
    pfad = route.format(giro=_giro(m8_api))
    r = m8_api.get(pfad)
    assert r.status_code == 200, f"{pfad}: {r.status_code}"
    assert r.headers["content-type"].split(";")[0].strip() == "text/html"
    assert "no-store" in r.headers.get("cache-control", "")
    start = m8_api.get("/").text
    assert r.text == start, "jede Route liefert dieselbe Hülle (oberflaeche.md 2)"


@pytest.mark.kern
def test_huelle_kopf_und_skripte(m8_api):
    text = m8_api.get("/").text
    h = _html(text)
    html = next(a for t, a in h.tags if t == "html")
    assert html.get("lang") == "de"
    metas = {a.get("name"): a.get("content", "") for t, a in h.tags if t == "meta" and a.get("name")}
    vp = metas.get("viewport", "").replace(" ", "")
    assert "width=device-width" in vp and "initial-scale=1" in vp
    assert "maximum-scale" not in vp and "user-scalable=no" not in vp, "Vergrößerung nicht sperren"
    assert set(metas.get("color-scheme", "").split()) == {"light", "dark"}
    links = [(a.get("rel"), a.get("href")) for t, a in h.tags if t == "link"]
    assert ("manifest", "/oeffentlich/manifest.webmanifest") in links
    assert h.skripte, "Die Oberfläche braucht ein Skript"
    for a, inhalt in h.skripte:
        src = a.get("src", "")
        assert src.startswith("/") and not src.startswith("//"), f"Skript nicht von derselben Herkunft: {src!r}"
        assert not inhalt.strip(), "kein Inline-Skript"
    for t, a in h.tags:
        assert not any(k.lower().startswith("on") for k in a), f"on…-Attribut an <{t}>"
        for k in ("href", "src"):
            assert not a.get(k, "").strip().lower().startswith("javascript:")
            v = a.get(k, "")
            assert not re.match(r"^(https?:)?//", v), f"fremde Quelle {v!r} (oberflaeche.md 1 Nr. 3)"


@pytest.mark.kern
def test_mock_hinweis_in_der_huelle(m8_api, tmp_path):
    h = _html(m8_api.get("/").text)
    hinweis = [a for t, a in h.tags if a.get("id") == "mock-hinweis"]
    assert len(hinweis) == 1 and hinweis[0].get("data-testid") == "mock-hinweis"
    assert "hidden" not in hinweis[0] and "display:none" not in hinweis[0].get("style", "").replace(" ", "")
    echt = neue_api(tmp_path / "echt")
    for pfad in ("/", "/konten", "/einstellungen"):
        assert "mock-hinweis" not in echt.get(pfad, erwartet=200).text


@pytest.mark.kern
def test_huelle_ohne_buchbestand(m8_api):
    """sicherheit.md 7.2: serverseitiges HTML enthält keine Texte aus dem Buchbestand."""
    erw = lade_erwartung()
    texte = [e["name"] for e in erw["empfaenger"]] + [erw["m8"]["umlaut_zweck"], "Wocheneinkauf", "Tankstelle"]
    giro = _giro(m8_api)
    for pfad in ("/", f"/konten/{giro}", "/suche?q=Tankstelle"):
        text = m8_api.get(pfad, erwartet=200).text
        for t in texte:
            assert t not in text, f"{pfad} enthält {t!r}"


def _png_groesse(roh: bytes) -> tuple[int, int]:
    assert roh[:8] == b"\x89PNG\r\n\x1a\n" and roh[12:16] == b"IHDR", "kein PNG"
    return struct.unpack(">II", roh[16:24])


@pytest.mark.kern
def test_manifest(m8_api, tmp_path):
    for api in (m8_api, m7_api(tmp_path / "m7", passwort=None, mock_modus=True)):
        r = api.get("/oeffentlich/manifest.webmanifest")
        assert r.status_code == 200, "Manifest ist öffentlich (sicherheit.md 3.1)"
        assert r.headers["content-type"].split(";")[0].strip() == "application/manifest+json"
        m = json.loads(r.content)
        assert (m["id"], m["name"], m["short_name"], m["lang"], m["start_url"], m["scope"], m["display"]) == (
            "/", "Kontor", "Kontor", "de", "/", "/", "standalone")
        for feld in ("background_color", "theme_color"):
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", m[feld]), feld
        groessen_any, maskable = set(), False
        for icon in m["icons"]:
            assert icon["src"].startswith("/oeffentlich/"), icon
            roh = api.get(icon["src"])
            assert roh.status_code == 200, icon
            breite, hoehe = _png_groesse(roh.content)
            assert icon["sizes"] == f"{breite}x{hoehe}", icon
            zwecke = icon.get("purpose", "any").split()
            if "any" in zwecke and icon.get("type", "image/png") == "image/png":
                groessen_any.add((breite, hoehe))
            maskable |= "maskable" in zwecke
        assert {(192, 192), (512, 512)} <= groessen_any
        assert maskable


@pytest.mark.kern
def test_service_worker_ausgeliefert(m8_api):
    r = m8_api.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].split(";")[0].strip() in ("text/javascript", "application/javascript")
    cc = r.headers.get("cache-control", "")
    assert "no-cache" in cc or "no-store" in cc
    assert r.content.strip()


def test_anmeldeseite_verlinkt_manifest(tmp_path):
    api = m7_api(tmp_path, passwort=None, mock_modus=True)
    h = _html(api.get("/anmelden", erwartet=200).text)
    assert ("manifest", "/oeffentlich/manifest.webmanifest") in [(a.get("rel"), a.get("href"))
                                                                 for t, a in h.tags if t == "link"]


def test_routen_geschuetzt_mit_anmeldung(tmp_path):
    """oberflaeche.md 2, sicherheit.md 3.2: ohne Sitzung 303 zur Anmeldung, /sw.js eingeschlossen."""
    api = m7_api(tmp_path, mock_modus=True)
    for pfad in ("/", "/konten/3?von=2024-01-01", "/tan/1", "/sw.js"):
        r = api.get(pfad, follow_redirects=False)
        assert r.status_code == 303, pfad
        assert r.headers["location"].startswith("/anmelden?weiter=")
    r = api.get("/oeffentlich/manifest.webmanifest")
    assert r.status_code == 200


def test_csp_der_huelle(m8_api):
    k = csp(m8_api.get("/").headers["content-security-policy"])
    assert k["script-src"] == ["'self'"]
    for direktive, werte in k.items():
        for w in werte:
            assert "://" not in w and w != "*", f"{direktive}: fremde Quelle {w}"
