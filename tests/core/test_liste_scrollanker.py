"""Core-Test (D-275): Die Buchungsliste nimmt nicht am Scroll-Anker des Browsers teil.

Die Liste zeichnet nur einen Ausschnitt und tauscht beim Rollen ihre Zeilen aus. Mit Scroll-Anker schob der Browser
die Rollposition bei jedem Austausch nach; der Schwung nach dem Loslassen lief dann ungebremst bis ans Ende der Liste.
Das Verhalten selbst lässt sich nur im Browser messen (Messung in D-275); hier ist gesichert, dass die Angabe bleibt.
"""

from __future__ import annotations

import re


def test_buchungsliste_ohne_scrollanker(auslieferung):
    css = auslieferung.get("/oeffentlich/app.css").text
    regeln = re.findall(r"(?m)^\.buchungsliste\s*\{([^}]*)\}", css)
    assert any(re.search(r"overflow-anchor:\s*none", r) for r in regeln), "overflow-anchor: none fehlt an .buchungsliste"
