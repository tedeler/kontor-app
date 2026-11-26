"""Core-Test (D-293): Spalten brechen nicht mitten im Wort um.

Das Verhalten im Browser prüft `tests/test_browser_tabellenbreite.py`. Hier ist ohne Browser gesichert, dass
Tabellenzellen und Karten Wörter nicht zerbrechen, Tabellen in einem rollenden Rahmen liegen und die Überschrift
einer Tabelle als Karten (Finanzübersicht) die volle Breite bekommt.
"""

from __future__ import annotations

import re


def _regel(css, selektor):
    m = re.search(re.escape(selektor) + r"\s*\{([^}]*)\}", css)
    assert m, f"Regel für {selektor} fehlt"
    return m.group(1)


def test_zellen_und_karten_zerbrechen_keine_woerter(client):
    css = client.get("/oeffentlich/app.css").text
    assert "overflow-wrap: break-word" in _regel(css, ".tabelle th, .tabelle td")
    assert "overflow-wrap: break-word" in _regel(css, ".karte")
    assert "display: block" in _regel(css, '[data-layout="mobil"] .tabelle.mobil-karten > caption')
    assert "overflow-x: auto" in _regel(css, ".tabelle-rahmen")


def test_tabellen_bekommen_einen_rahmen(client):
    js = client.get("/oeffentlich/app/haupt.js").text
    teil = js[js.index("function tabelleRahmen("):]
    assert "tabelle-rahmen" in teil[:600]
    assert "new MutationObserver" in js[js.index("function tabelleRahmen("):][:1500]
