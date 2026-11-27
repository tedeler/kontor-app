"""Core-Test (D-296): Die Kategorie-Auswahl ist vollständig über die Tastatur bedienbar.

Das Verhalten prüft `tests/test_browser_kategorie_tastatur.py`. Hier ist ohne Browser gesichert, dass der Dialog die
Tasten kennt und sie im Fenster nennt.
"""

from __future__ import annotations

import re


def _auswahl(client):
    js = client.get("/oeffentlich/app/ui.js").text
    teil = js[js.index("export function kategorieAuswahl("):]
    return teil[:teil.index("\n}\n")]


def test_tasten_der_suche(auslieferung):
    teil = _auswahl(auslieferung)
    for taste in ("ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", "Enter"):
        assert re.search(rf"\b{taste}\b", teil), f"{taste} fehlt in der Kategorie-Auswahl"
    assert "ctrlKey" in teil, "Strg+Enter (neue Kategorie) fehlt"


def test_formular_neue_kategorie_mit_tastatur(auslieferung):
    teil = _auswahl(auslieferung)
    assert '"Escape"' in teil, "Esc im Formular führt nicht zurück zur Auswahl"
    assert "stopPropagation" in teil


def test_tasten_werden_im_fenster_genannt(auslieferung):
    assert '"kategorie-auswahl-tasten"' in _auswahl(auslieferung)
