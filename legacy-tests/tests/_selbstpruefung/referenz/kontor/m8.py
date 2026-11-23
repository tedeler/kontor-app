"""WEGWERF-REFERENZ M8 (E-149): Auslieferung einer kleinen Oberfläche – kein Anwendungscode.

Nur so viel, dass die ``kern``-Tests der Oberfläche (Auslieferung, Mehrfachauswahl, Kontextmenü,
Mehrfachbearbeitung, Befehlspalette, mobiles Menü, Mock-Hinweis) grün werden und die Mutanten rot.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from . import MUTANT, __version__, mutant

HIER = Path(__file__).parent / "oberflaeche"
ROUTEN = ["/konten", "/konten/{a}", "/kategorien", "/erwartet", "/mail", "/tags", "/konfiguration", "/kredite", "/kredite/{a}", "/berichte",
          "/import", "/einstellungen", "/protokoll", "/empfaenger", "/regeln", "/vorlagen", "/dubletten", "/sync",
          "/benachrichtigungen", "/suche", "/tan/{a}", "/mail/postfaecher/{a}"]


def _png(groesse: int) -> bytes:
    zeile = b"\x00" + b"\x20\x60\xa0" * groesse
    roh = zeile * groesse

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", groesse, groesse, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(roh)) + chunk(b"IEND", b""))


MANIFEST = {
    "id": "/", "name": "Kontor", "short_name": "Kontor", "lang": "de", "start_url": "/", "scope": "/",
    "display": "standalone", "background_color": "#ffffff", "theme_color": "#1f4e79",
    "icons": [{"src": "/oeffentlich/symbol-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
              {"src": "/oeffentlich/symbol-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
              {"src": "/oeffentlich/symbol-maskable-512.png", "sizes": "512x512", "type": "image/png",
               "purpose": "maskable"}],
}


def huelle(config) -> str:
    hinweis = ('<div id="mock-hinweis" data-testid="mock-hinweis" role="status">Mock-Modus: synthetische Daten'
               '</div>') if config.mock_modus else ""
    skript = "<script>window.x=1</script>" if mutant("m8_huelle_inline_skript") else ""
    knopf = "" if mutant("m13_huelle_ohne_version") else (
        '<button type="button" data-testid="version-knopf" aria-haspopup="dialog">Version ' + __version__ + '</button>')
    return ('<!DOCTYPE html><html lang="de" data-mutant="' + MUTANT + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="color-scheme" content="light dark"><title>Kontor</title>'
            '<link rel="manifest" href="/oeffentlich/manifest.webmanifest">'
            '<link rel="stylesheet" href="/oeffentlich/app.css">' + skript +
            '<script type="module" src="/oeffentlich/app.js"></script></head><body>'
            '<div data-testid="app" data-bereit="nein">' + hinweis + '<div id="wurzel">' + knopf + '</div></div>'
            '</body></html>')


def mit_cache(request, antwort: Response) -> Response:
    """M26 (oberflaeche.md 36.8): no-cache, ETag, 304 bei passendem If-None-Match."""
    import hashlib

    etag = '"' + hashlib.sha256(antwort.body).hexdigest()[:32] + '"'
    if not mutant("m26_ohne_304") and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    antwort.headers["Cache-Control"] = "max-age=3600" if mutant("m26_cache_frei") else "no-cache"
    if not mutant("m26_ohne_etag"):
        antwort.headers["ETag"] = etag
    return antwort


def statisch(name: str) -> Response | None:
    if name == "manifest.webmanifest":
        return Response(json.dumps(MANIFEST), media_type="application/manifest+json")
    if name in ("symbol-192.png", "symbol-512.png", "symbol-maskable-512.png"):
        return Response(_png(192 if "192" in name else 512), media_type="image/png")
    if name in ("app.js", "app.css"):
        return Response((HIER / name).read_bytes(), media_type="text/javascript" if name.endswith(".js")
                        else "text/css")
    return None


def m8_einbinden(app: FastAPI, config) -> None:
    def seite():
        return HTMLResponse(huelle(config))

    for r in ROUTEN:
        app.add_api_route(r, seite, methods=["GET"], response_class=HTMLResponse)

    @app.get("/sw.js")
    def sw():
        return Response((HIER / "sw.js").read_bytes(), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})
