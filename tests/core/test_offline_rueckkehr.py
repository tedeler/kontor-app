"""Core-Test (D-276): Die Oberfläche findet nach einem Verbindungsabbruch von selbst zurück.

Am Handy friert der Browser die Seite im Hintergrund ein; beim Zurückholen schlägt eine Anfrage fehl und der
Offline-Hinweis erscheint. Das Ereignis `online` kommt danach nie, weil das Gerät nie offline war. Das Verhalten
selbst prüft `tests/test_browser_offline.py`; hier ist gesichert, dass die Anlässe für die erneute Prüfung bleiben.
"""

from __future__ import annotations

import re


def test_oberflaeche_prueft_die_verbindung_bei_rueckkehr(client):
    js = client.get("/oeffentlich/app/haupt.js").text
    for ereignis in ("visibilitychange", "pageshow", "online"):
        assert re.search(rf'addEventListener\("{ereignis}"', js), f"haupt.js reagiert nicht auf {ereignis}"
    assert "verbindungPruefen" in js, "die erneute Prüfung der Verbindung fehlt"
