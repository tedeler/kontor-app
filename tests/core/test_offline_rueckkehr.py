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


def test_offline_bleibt_die_geladene_seite_stehen(client):
    """D-277: Der Offline-Zustand leert die geladene Seite und die offenen Tabs nicht mehr; der Hinweis sagt, dass
    die Daten veraltet sein können."""
    js = client.get("/oeffentlich/app/haupt.js").text
    assert "alleVerwerfen" not in js, "der Offline-Zustand verwirft weiter die geladenen Tabs"
    huelle = client.get("/").text
    hinweis = re.search(r'(?s)data-testid="offline-hinweis"[^>]*>(.*?)</div>', huelle).group(1).lower()
    assert "offline" in hinweis and "veraltet" in hinweis
