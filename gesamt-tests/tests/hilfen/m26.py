"""Hilfen für Meilenstein-26-Tests (Bedienung auf dem Handy, ``oberflaeche.md`` 36, E-246, E-247).

Nur über die Spezifikation: ``data-testid``, ARIA-Attribute, Lage der Elemente und echte Touch-Ereignisse über
CDP (wie ``tests/hilfen/m8.lange_beruehrung``/``wischen``).
"""

from __future__ import annotations

from .m8 import _cdp, _mitte, tid

#: Reihenfolge der Kopfzeile mobil (36.2.1)
#: bei 390 px Breite; „Wiederholen“ entfällt unter 403 px (D-279), damit alle Knöpfe in eine Zeile passen
KOPF = ["menue-knopf", "suche-knopf", "sync-starten", "rueckgaengig-knopf",
        "befehlspalette-knopf", "benachrichtigungen-knopf", "tabs-knopf"]
#: Knöpfe der Auswahlleiste, die im Auswahlmodus mobil sichtbar sind (36.3.3)
LEISTE_SICHTBAR = ["mehrfach-kategorie", "mehrfach-tags", "mehrfach-loeschen", "mehrfach-mehr"]
#: Knöpfe der Auswahlleiste, die mobil verborgen sind (übrige aus 7.5, 23.3)
LEISTE_VERBORGEN = ["mehrfach-vorschlag-annehmen", "mehrfach-vorschlag-ablehnen", "mehrfach-status",
                    "mehrfach-bearbeiten", "auswahl-aufheben"]


def box(locator) -> dict:
    b = locator.bounding_box()
    assert b, "Element ohne Lage (nicht sichtbar)"
    return b


def kein_waagerechtes_scrollen(seite) -> bool:
    return seite.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")


class Wisch:
    """Waagerechte Wischgeste in Schritten, zwischen denen der Test den Zustand prüft (36.4.3)."""

    def __init__(self, seite, locator, *, start_dx: float = 0) -> None:
        self.seite = seite
        x, y = _mitte(locator)
        self.x0 = min(max(x + start_dx, 5), seite.viewport_size["width"] - 5)
        self.y0 = y
        self.cdp = _cdp(seite)
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchStart",
                                                    "touchPoints": [{"x": self.x0, "y": self.y0}]})

    def nach(self, dx: float, dy: float = 0, *, schritte: int = 6, pause_ms: int = 20) -> None:
        """Bewegt den Finger in ``schritte`` Schritten auf (x0 + dx, y0 + dy)."""
        aktuell = getattr(self, "_pos", (0.0, 0.0))
        for i in range(1, schritte + 1):
            px = aktuell[0] + (dx - aktuell[0]) * i / schritte
            py = aktuell[1] + (dy - aktuell[1]) * i / schritte
            self.seite.wait_for_timeout(pause_ms)  # Geschwindigkeit der Geste, keine Wartezeit auf einen Zustand
            self.cdp.send("Input.dispatchTouchEvent", {"type": "touchMove",
                                                        "touchPoints": [{"x": self.x0 + px, "y": self.y0 + py}]})
        self._pos = (dx, dy)

    def loslassen(self) -> None:
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def langsam_wischen(seite, locator, richtung: str, *, weite: int = 140, dauer_ms: int = 1500) -> None:
    """Wischen über mehr als 1 s (36.4.2: mobil ohne Dauergrenze)."""
    dx = weite if richtung == "rechts" else -weite
    w = Wisch(seite, locator, start_dx=-dx / 2)
    w.nach(dx, schritte=15, pause_ms=dauer_ms // 15)
    w.loslassen()


def wisch_hinweis(seite):
    return seite.locator(".wisch-hinweis")


def sichtbarer_hinweis(seite):
    """Der sichtbare ``wisch-hinweis`` (oder ``None``)."""
    h = wisch_hinweis(seite)
    for i in range(h.count()):
        if h.nth(i).is_visible():
            return h.nth(i)
    return None


def tippen_bei(seite, x: float, y: float) -> None:
    seite.touchscreen.tap(x, y)


def kontextmenue_eintraege(seite) -> list[str]:
    """Alle Einträge des offenen Kontextmenüs (auch verborgene deaktivierte) in Reihenfolge."""
    return tid(seite, "kontextmenue").locator('[role="menuitem"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
