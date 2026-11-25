"""Core-Test (D-278, D-279): Gesten im mobilen Kontoblatt und einzeilige Kopfzeile.

Das Verhalten selbst prüft `tests/test_browser_gesten.py` im Handy-Format. Hier ist ohne Browser gesichert, dass die
Bausteine ausgeliefert werden: Einträge des mobilen Kontextmenüs, das Rückgängig-Angebot nach dem Wisch und die
Regeln der Kopfzeile.
"""

from __future__ import annotations

import re


def test_kontoblatt_liefert_die_bausteine_der_gesten(client):
    js = client.get("/oeffentlich/app/konto.js").text
    for kennung in ("km-details", "km-auswahl", "wisch-rueckgaengig"):
        assert f'"{kennung}"' in js, f"{kennung} fehlt im Kontoblatt"
    assert "wischBestaetigen" in js, "Wisch nach rechts bestätigt nicht"
    assert re.search(r"DOPPELTIPP_MS\s*=\s*\d+", js), "Doppeltipp fehlt"
    assert "stapelStand" in client.get("/oeffentlich/app/kern.js").text


def test_markierung_und_rueckgaengig_haben_stile(client):
    css = client.get("/oeffentlich/app.css").text
    assert ".zeile[data-markiert]" in css, "die getippte Zeile ist mobil nicht hervorgehoben"
    assert re.search(r"(?m)^\.wisch-rueck\s*\{", css)
    # Doppeltipp zoomt nicht: die Zeile lässt dem Browser nur das senkrechte Rollen
    assert re.search(r"(?m)^\.zeile\s*\{[^}]*touch-action:\s*pan-y", css)


def test_kopfzeile_mobil_bricht_nicht_um(client):
    css = client.get("/oeffentlich/app.css").text
    assert re.search(r'\[data-layout="mobil"\]:not\(\.suche-offen\) \.kopf\s*\{[^}]*flex-wrap:\s*nowrap', css)
    assert re.search(r"max-width:\s*402\.98px\)\s*\{[^}]*#wiederholen-knopf\s*\{\s*display:\s*none", css)


def test_doppeltipp_nur_bei_ruhender_liste_und_auswahl_nur_ausdruecklich(client):
    """D-281: Ein Tipp zählt für den Doppeltipp nur, wenn die Liste nicht gerade rollt und beide Tipps an derselben
    Stelle liegen; Sprünge (Gegenbuchung, Berichte) wählen mobil nichts aus."""
    js = client.get("/oeffentlich/app/konto.js").text
    assert re.search(r"TIPP_RUHE_MS\s*=\s*\d+", js) and re.search(r"TIPP_ABSTAND\s*=\s*\d+", js)
    assert re.search(r'addEventListener\("scroll"', js), "das Rollen wird nicht beobachtet"
    sprung = js[js.index("  sprungMarkieren(id) {"):]
    sprung = sprung[:sprung.index("\n  }\n")]
    assert "istMobil()" in sprung, "der Sprung zu einer Buchung wählt mobil weiter aus"
