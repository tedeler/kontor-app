"""Core-Test (D-273): Das Design steht vor dem ersten Zeichnen fest – kein helles Aufblitzen im dunklen Design."""

from __future__ import annotations


def test_thema_wird_vor_dem_stil_gesetzt(auslieferung):
    huelle = auslieferung.get("/").text
    skript = '<script src="/oeffentlich/thema.js"></script>'
    # blockierendes Skript im Kopf, vor dem Stylesheet und vor dem (verzögert laufenden) Modul der Anwendung
    assert skript in huelle
    assert huelle.index(skript) < huelle.index('<link rel="stylesheet"') < huelle.index('<script type="module"')
    assert huelle.index(skript) < huelle.index("</head>")

    r = auslieferung.get("/oeffentlich/thema.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    js = r.text
    # liest dieselbe Einstellung wie die Anwendung und folgt sonst dem System
    assert '"kontor.thema"' in js and "prefers-color-scheme: dark" in js and "dataset.thema" in js
    assert '"/oeffentlich/thema.js"' in auslieferung.get("/sw.js").text   # auch offline verfügbar
