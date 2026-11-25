"""Core-Test (D-287): Bereichswechsel mit der Vortaste „w“ und F6.

Das Verhalten selbst prüft `tests/test_browser_tastatur.py`. Hier ist ohne Browser gesichert, dass die Bausteine
ausgeliefert werden: die globale Vortaste mit ihren Zielen, die Ziele des Kontoblatts, Hilfe und Hervorhebung.
"""

from __future__ import annotations

import re


def _js(client, name):
    return client.get(f"/oeffentlich/app/{name}.js").text


def test_vortaste_w_ist_global_und_kennt_die_ziele_jeder_seite(client):
    js = _js(client, "haupt")
    assert re.search(r'BEREICH_VORTASTE\s*=\s*"w"', js), "die Vortaste w fehlt"
    ziele = js[js.index("const BEREICH_ZIELE"):]
    ziele = ziele[:ziele.index("];")]
    for taste in ("b", "t", "n", "s", "z", "x", "ArrowLeft", "ArrowRight"):
        assert f'["{taste}"' in ziele, f"w {taste} fehlt"
    assert "Digit" in js[js.index("function bereichTaste"):][:3000], "w 1 … w 9 fehlen"
    assert '"F6"' in js, "F6 wechselt die Bereiche nicht"


def test_kontoblatt_meldet_buchungsblatt_einzelheiten_und_filter(client):
    js = _js(client, "konto")
    teil = js[js.index("  bereiche() {"):]
    teil = teil[:teil.index("\n  }\n")]
    for taste, text in (("b", "Buchungsblatt"), ("e", "Einzelheiten"), ("f", "Filter")):
        assert re.search(rf'taste:\s*"{taste}",\s*text:\s*"{text}"', teil), f"w {taste} ({text}) fehlt im Kontoblatt"
    # w darf weder ein Kürzel ohne Vortaste noch eine Vortaste des Kontoblatts sein
    tabelle = js[js.index("const KUERZEL = ["):js.index("const VORTASTEN")]
    assert '["", "w"' not in tabelle
    assert not re.search(r"const VORTASTEN = \{[^}]*\bw:", js)


def test_tabs_kennen_nachbar_nummer_und_den_zuletzt_aktiven(client):
    js = _js(client, "tabs")
    for name in ("nachbar(", "nummer(", "vorher"):
        assert name in js, f"{name} fehlt in den Tabs"


def test_hilfe_und_hinweis_zeigen_die_bereiche(client):
    js = _js(client, "haupt")
    assert "tastatur-hilfe-bereiche" in js, "die Tastaturhilfe nennt die Bereiche nicht"
    assert re.search(r'vortaste\s*=\s*BEREICH_VORTASTE', js), "der Hinweis nach w fehlt"


def test_aktiver_bereich_ist_sichtbar(client):
    css = client.get("/oeffentlich/app.css").text
    assert re.search(r"\.bereich-aktiv\b", css), "der aktive Bereich ist nicht hervorgehoben"


def test_fokuszeile_haelt_unter_dem_klebenden_spaltenkopf(client):
    """D-288: Beim Nachführen der Liste zählt die Höhe des Spaltenkopfs mit (kurze Liste und Fenstertechnik)."""
    js = _js(client, "konto")
    assert "kopfUeberstand()" in js
    slot = js[js.index("  slotZeigen(slotId"):]
    assert "kopfUeberstand" in slot[:slot.index("\n  }\n")], "die Fenstertechnik beachtet den Spaltenkopf nicht"
    fokus = js[js.index("  fokussieren(id, mitDom"):]
    assert "scrollPaddingTop" in fokus[:fokus.index("\n  }\n")], "die kurze Liste beachtet den Spaltenkopf nicht"
