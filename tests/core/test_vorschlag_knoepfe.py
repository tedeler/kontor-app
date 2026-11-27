"""Core-Tests zum Feature „vorschlag-knoepfe“ (D-305): Die Knöpfe ✓/✗ zum Annehmen und Ablehnen eines
Kategorievorschlags in der Buchungszeile entfallen. Die übrigen Wege bleiben: Tasten `a`/`A`, Kontextmenü,
Mehrfachleiste, Einzelheiten, Wischen auf dem Handy."""

from __future__ import annotations


def test_keine_knoepfe_in_der_zeile(auslieferung):
    js = auslieferung.get("/oeffentlich/app/konto.js").text
    assert "vorschlag-annehmen-${" not in js and "vorschlag-ablehnen-${" not in js
    assert "vorschlag-knoepfe" not in js
    assert "vorschlag-knoepfe" not in auslieferung.get("/oeffentlich/app.css").text


def test_die_anderen_wege_bleiben(auslieferung):
    js = auslieferung.get("/oeffentlich/app/konto.js").text
    for t in ('tid: "km-vorschlag-annehmen"', 'tid: "km-vorschlag-ablehnen"', '"mehrfach-vorschlag-annehmen"',
              '"mehrfach-vorschlag-ablehnen"', 'tid: "details-vorschlag-annehmen"', 'tid: "details-vorschlag-ablehnen"'):
        assert t in js, t
    tabelle = js[js.index("const KUERZEL = ["):js.index("const VORTASTEN")]
    assert '["", "a", "Vorschlag annehmen"' in tabelle and '["", "A", "Vorschlag ablehnen"' in tabelle
