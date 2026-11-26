"""Core-Test (D-299): Fällt die markierte Buchung durch eine Änderung aus der gefilterten Liste, rückt die Buchung
direkt darunter nach (am Ende die darüber). Bei einem Wechsel von Filter, Sortierung oder Gruppierung bleibt D-271.

Das Verhalten prüft `tests/test_browser_markierung_nachruecken.py`. Hier ist ohne Browser gesichert, dass das
Kontoblatt den Nachfolger beim Neuladen bestimmt und dafür die Abfrage vergleicht.
"""

from __future__ import annotations


def _laden(client):
    js = client.get("/oeffentlich/app/konto.js").text
    teil = js[js.index("  async laden(o) {"):]
    return js, teil[:teil.index("\n  }\n")]


def test_laden_bestimmt_den_nachfolger(client):
    js, teil = _laden(client)
    assert "nachruecken(" in teil, "laden() lässt keinen Nachfolger nachrücken"
    n = js[js.index("  nachruecken("):]
    n = n[:n.index("\n  }\n")]
    assert "gleicheAbfrage" in teil, "Nachrücken hängt nicht an einer unveränderten Abfrage"
    for teilstueck in ("this.auswahl", "this.fokusId", "this.anker"):
        assert teilstueck in n, f"{teilstueck} wird beim Nachrücken nicht gesetzt"
