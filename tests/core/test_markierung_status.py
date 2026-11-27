"""Core-Test (D-309): Die mobil markierte (getippte) Buchung behält die Farbe ihres Status.

Vorher färbte die Markierung die ganze Zeile in der Auswahlfarbe (blau); ob die Buchung importiert (rot), vorläufig
(gelb) oder bestätigt (weiß/schwarz) ist, war nicht mehr zu sehen. Jetzt gilt mobil dasselbe Prinzip wie für die
Auswahl am Desktop (D-269/D-270): Grundton und Streifen des Status bleiben, die Markierung legt nur einen neutralen
Schleier und einen Rahmen in der Akzentfarbe darüber. Das sichtbare Ergebnis prüft
`tests/test_browser_markierung_status.py`.
"""

from __future__ import annotations

import re

MARKIERT = r'\[data-layout="mobil"\] \.buchungsliste:not\(\[data-auswahlmodus="ja"\]\) \.zeile\[data-markiert\]'


def _regeln(css: str, auswahl: str) -> list[str]:
    return re.findall(auswahl + r"[^{,]*\{([^}]*)\}", css)


def test_markierung_faerbt_die_zeile_nicht_um(client):
    css = client.get("/oeffentlich/app.css").text
    regeln = _regeln(css, MARKIERT)
    assert regeln, "keine Regel für die mobil markierte Zeile"
    for r in regeln:
        assert "var(--auswahl)" not in r, "die Markierung überdeckt die Statusfarbe mit der Auswahlfarbe"
        m = re.search(r"background-color:\s*([^;]+)", r)
        assert m is None or "var(--toenung)" in m.group(1), "der Grundton der Zeile ist nicht mehr der des Status"


def test_markierung_hat_rahmen_und_schleier(client):
    css = client.get("/oeffentlich/app.css").text
    alles = " ".join(_regeln(css, MARKIERT))
    assert "--schleier" in alles, "die Markierung legt keinen Schleier über die Zeile"
    rahmen = " ".join(_regeln(css, MARKIERT + r"::after"))
    assert re.search(r"border:\s*\d+px solid var\(--wahl-linie\)", rahmen), "die Markierung hat keinen Rahmen"
    # der Statusstreifen liegt innerhalb des Rahmens und bleibt sichtbar
    assert re.search(r"background-position:\s*\d+px 0", alles)
