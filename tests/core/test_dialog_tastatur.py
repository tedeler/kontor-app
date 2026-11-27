"""Core-Test (D-298): Alle Dialoge lassen sich mit der Tastatur bedienen (oberflaeche.md 9).

Das Verhalten prüft `tests/test_browser_dialog_tastatur.py` an einer breiten Auswahl von Dialogen. Hier ist ohne
Browser gesichert, dass alle Dialoge über das gemeinsame Grundgerüst entstehen und das Grundgerüst Anfangsfokus und
Pfeiltasten regelt.
"""

from __future__ import annotations

import re

MODULE = ("kern", "ui", "baum", "konto", "seiten", "einstellungen", "haupt", "regeleditor", "ausdruck", "aenderung",
          "dokumente", "erwartet", "mail", "monatsbericht", "berichte", "berichte2", "berichtsteile", "tabs")


def _grundgeruest(client):
    js = client.get("/oeffentlich/app/ui.js").text
    teil = js[js.index("export function dialog("):]
    return js, teil[:teil.index("\n}\n")]


def test_alle_dialoge_ueber_das_grundgeruest(auslieferung):
    for m in MODULE:
        r = auslieferung.get(f"/oeffentlich/app/{m}.js")
        if r.status_code == 404:
            continue
        treffer = re.findall(r'role: "(?:alert)?dialog"', r.text)
        assert len(treffer) == (1 if m == "ui" else 0), f"{m}.js baut einen Dialog ohne dialog() aus ui.js"


def test_anfangsfokus_nur_auf_bedienbare_elemente(auslieferung):
    _js, teil = _grundgeruest(auslieferung)
    # der erste Kandidat für den Fokus kommt aus fokussierbare() (ohne deaktivierte und unsichtbare Elemente)
    assert "fokussierbare(box)" in teil, "Anfangsfokus übergeht deaktivierte Felder nicht"
    assert "box.contains(document.activeElement)" in teil, "kein Rückfall, wenn nichts den Fokus bekommt"


def test_pfeiltasten_im_dialog(auslieferung):
    js, teil = _grundgeruest(auslieferung)
    assert re.search(r'box\.addEventListener\("keydown", \(e\) => dialogPfeil\(box, e\)\)', teil)
    pfeil = js[js.index("export function dialogPfeil("):]
    pfeil = pfeil[:pfeil.index("\n}\n")]
    for taste in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"):
        assert taste in pfeil, f"{taste} fehlt"
    assert "knopf-leiste" in pfeil and "defaultPrevented" in pfeil
