"""Hilfen für Meilenstein-17-Tests (Tabs der Ansichten, „Gehe zur Gegenbuchung“, ``oberflaeche.md`` 27).

Nur über die Spezifikation: ``data-testid``, ARIA-Rollen und -Attribute, ``data-pfad``, Routen und Tastatur.

- ``daten``: synthetische Konten und Buchungen über REST (einfache Buchung, Umbuchung, Splitbuchung mit zwei
  Gegenseiten, Buchung mit zwei Splits auf derselben Kategorie, Buchung ohne Gegenseite; optional viele
  Buchungen auf dem Tagesgeld für das Nachladen von Seiten).
- Tab-Leiste: Pfade, aktiver Tab, Warten auf einen Zustand, Wechsel über ``tab-titel``, Anfordern über die
  Befehlspalette (Navigation nach ``oberflaeche.md`` 12.3).
- ``Anfragen``: vollständige URLs aller Anfragen an ``/api/`` (für „lädt erst, wenn aktiv“).
"""

from __future__ import annotations

import datetime as dt
import time
from urllib.parse import parse_qs, urlsplit

from .api import Api
from .m8 import WARTEN_MS, tid, warte_geladen

#: Zahl der zusätzlichen Buchungen auf dem Tagesgeld (mehr als eine Seite zu 200, oberflaeche.md 7.2)
VIELE = 205
HINWEIS_FILTER = "Filter zurückgesetzt, damit die Buchung sichtbar ist."
FEHLER_NICHT_ENTHALTEN = "Die Buchung ist in dieser Ansicht nicht enthalten."


# ------------------------------------------------------------------ Daten
def daten(api: Api, *, viele: bool = False) -> dict:
    """Konten und Buchungen; Schlüssel siehe unten. Gegenseiten in der Ansicht von K = Konten aller Splits mit
    ``konto_id`` ≠ K in Split-Reihenfolge, jedes einmal (Definition 2.1) – hier im Test selbst festgelegt."""
    k = {"giro": api.konto("Girokonto", "girokonto")["id"],
         "spar": api.konto("Tagesgeld", "sparkonto")["id"],
         "leb": api.konto("Lebensmittel", "aufwand")["id"],
         "cafe": api.konto("Café", "aufwand")["id"],
         "zins": api.konto("Zinsen", "ertrag")["id"]}
    g, s, leb, cafe = k["giro"], k["spar"], k["leb"], k["cafe"]
    b = {
        # genau eine Gegenseite (Kategorie), Status importiert
        "einfach": api.buchung("2024-03-06", [(g, -1250, "Markt"), (leb, 1250)], status="importiert",
                               verwendungszweck="Wocheneinkauf")["id"],
        "zweite": api.buchung("2024-03-05", [(leb, 800), (g, -800)], status="bestaetigt",
                              verwendungszweck="Bäcker")["id"],
        # Umbuchung zwischen zwei Bestandskonten (älteste Buchung des Tagesgelds)
        "umbuchung": api.buchung("2024-03-04", [(g, -50000), (s, 50000)], status="bestaetigt",
                                 verwendungszweck="Sparen")["id"],
        # zwei Gegenseiten; Reihenfolge der Splits: Café, Girokonto, Lebensmittel
        "split": api.buchung("2024-03-03", [(cafe, 1000, "Kaffee"), (g, -3000), (leb, 2000, "Brot")],
                             status="importiert", verwendungszweck="Markt und Café")["id"],
        # zwei Splits auf derselben Kategorie: eine Gegenseite
        "doppelt": api.buchung("2024-03-02", [(g, -300), (leb, 100, "a"), (leb, 200, "b")], status="importiert",
                               verwendungszweck="Zwei Posten")["id"],
        # ohne Gegenseite (alle Splits auf dem Girokonto)
        "ohne": api.buchung("2024-03-01", [(g, 500), (g, -500)], status="bestaetigt",
                            verwendungszweck="Nullsumme")["id"],
    }
    if viele:
        start = dt.date(2024, 4, 1)
        for i in range(VIELE):
            api.buchung((start + dt.timedelta(days=i)).isoformat(), [(s, 100 + i), (k["zins"], -(100 + i))],
                        verwendungszweck=f"Zins {i}")
    return {"k": k, "b": b}


# ------------------------------------------------------------------ Tab-Leiste
def leiste(seite):
    return tid(seite, "tab-leiste")


def tabs_aufklappen(seite) -> None:
    """Mobil (M26, oberflaeche.md 36.2.3): ``tab-leiste`` ist verborgen, bis ``tabs-knopf`` sie aufklappt."""
    from playwright.sync_api import expect

    knopf = tid(seite, "tabs-knopf")
    if knopf.get_attribute("aria-expanded") != "true":
        knopf.click()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    expect(leiste(seite)).to_be_visible()


def tabs_zuklappen(seite) -> None:
    """Klappt die mobile Tab-Liste mit Esc zu (36.2.3)."""
    from playwright.sync_api import expect

    if tid(seite, "tabs-knopf").get_attribute("aria-expanded") == "true":
        seite.keyboard.press("Escape")
    expect(tid(seite, "tabs-knopf")).to_have_attribute("aria-expanded", "false")
    expect(leiste(seite)).to_be_hidden()


def leiste_sichtbar(seite, geraet: str) -> None:
    """Desktop: Leiste dauerhaft sichtbar (27.1.2). Mobil (36.2.3, E-248): ohne Aufklappen verborgen, nach
    ``tabs-knopf`` sichtbar; danach wieder zugeklappt."""
    from playwright.sync_api import expect

    if geraet != "handy":
        expect(leiste(seite)).to_be_visible()
        return
    expect(leiste(seite)).to_be_hidden()
    expect(tid(seite, "tabs-knopf")).to_be_visible()
    tabs_aufklappen(seite)
    tabs_zuklappen(seite)


def tab(seite, pfad: str):
    return leiste(seite).locator(f'[data-testid="tab"][data-pfad="{pfad}"]')


def titel(seite, pfad: str):
    return tab(seite, pfad).get_by_test_id("tab-titel")


def schliessen(seite, pfad: str):
    return tab(seite, pfad).get_by_test_id("tab-schliessen")


def pfade(seite) -> list[str]:
    return leiste(seite).locator('[data-testid="tab"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-pfad'))")


def aktive(seite) -> list[str]:
    return leiste(seite).locator('[data-testid="tab"][aria-selected="true"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-pfad'))")


def url(seite) -> tuple[str, dict[str, list[str]]]:
    t = urlsplit(seite.url)
    return t.path, parse_qs(t.query)


def warte(seite, bedingung, text: str):
    """Wartet (ohne feste Zeit) auf eine Bedingung im Browser; gibt den letzten Wert aus."""
    ende = time.monotonic() + WARTEN_MS / 1000
    letzter = None
    while time.monotonic() < ende:
        letzter = bedingung()
        if letzter:
            return letzter
        seite.wait_for_timeout(50)
    raise AssertionError(f"{text} nicht erreicht (zuletzt: {letzter!r})")


def warte_tabs(seite, erwartet: list[str], aktiv: str, abfrage: dict[str, list[str]] | None = None) -> None:
    """Tabs genau ``erwartet`` in dieser Reihenfolge, genau ``aktiv`` mit aria-selected="true", alle anderen
    "false"; URL-Pfad = ``aktiv`` (Definition 1.1, 1.2); optional Abfrage der URL genau ``abfrage``."""
    def ist():
        p = pfade(seite)
        sel = leiste(seite).locator('[data-testid="tab"]').evaluate_all(
            "els => els.map(e => e.getAttribute('aria-selected'))")
        u = url(seite)
        return (p, sel, u[0], u[1] if abfrage is not None else None)
    soll = (erwartet, ["true" if x == aktiv else "false" for x in erwartet], aktiv, abfrage)
    ende = time.monotonic() + WARTEN_MS / 1000
    letzter = None
    while time.monotonic() < ende:
        letzter = ist()
        if letzter == soll:
            return
        seite.wait_for_timeout(50)
    raise AssertionError(f"Tabs/URL (Pfade, aria-selected, URL-Pfad, Abfrage) = {letzter}, erwartet {soll}")


def titel_text(seite, pfad: str) -> str:
    return " ".join(titel(seite, pfad).inner_text().split())


def wechsle(seite, pfad: str) -> None:
    """Wechsel über den Tab (Klick auf ``tab-titel``, Definition 1.3)."""
    titel(seite, pfad).click()


def oeffne_konto(seite, konto_id: int) -> None:
    """Anfordern über die Befehlspalette („Konto öffnen: <Name>“, ``oberflaeche.md`` 12.3) ohne Abfrageteil."""
    from playwright.sync_api import expect

    tid(seite, "befehlspalette-knopf").click()
    expect(tid(seite, "befehlspalette")).to_be_visible()
    tid(seite, f"befehl-konto-{konto_id}").click()
    expect(tid(seite, "befehlspalette")).to_have_count(0)


def warte_konto(seite, konto_id: int):
    """Kontoansicht des Kontos aktiv und geladen."""
    warte(seite, lambda: konto_id_aktiv(seite) == konto_id, text=f"Tab /konten/{konto_id} aktiv")
    return warte_geladen(seite, "konto")


def konto_id_aktiv(seite) -> int | None:
    a = aktive(seite)
    if len(a) == 1 and a[0].startswith("/konten/"):
        try:
            return int(a[0].rsplit("/", 1)[1])
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ Tastatur
def fokus_auf_tab(seite, pfad: str) -> None:
    """Setzt den Tastaturfokus auf den Tab (das Element ``role=tab`` oder sein fokussierbares Element)."""
    tab(seite, pfad).evaluate("""t => {
      const k = [t, ...t.querySelectorAll('a[href], button, [tabindex]')]
        .filter(e => e.tabIndex >= 0 && e.getAttribute('data-testid') !== 'tab-schliessen');
      (k[0] || t).focus();
    }""")


def fokus_tab(seite) -> str | None:
    """``data-pfad`` des Tabs, in dem der Tastaturfokus liegt."""
    return seite.evaluate("""() => { const e = document.activeElement;
      const t = e && e.closest('[data-testid="tab-leiste"] [role="tab"]');
      return t ? t.getAttribute('data-pfad') : null; }""")


def per_tab_erreichbar(seite) -> dict[str, bool]:
    """Je Tab: enthält er (oder ist er) ein per Tabulatortaste erreichbares Element?"""
    return dict(leiste(seite).locator('[data-testid="tab"]').evaluate_all("""els => els.map(t => [
      t.getAttribute('data-pfad'),
      [t, ...t.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')]
        .some(e => e.tabIndex >= 0 && !e.disabled)])"""))


# ------------------------------------------------------------------ Liste
def fokuszeile(seite) -> int | None:
    ids = seite.locator('[data-testid="buchungsliste"] [role="row"][tabindex="0"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    ids = [x for x in ids if x and x.startswith("buchung-")]
    return int(ids[0][8:]) if len(ids) == 1 else None


def menue_eintraege(seite) -> list[str]:
    """``data-testid`` der Einträge des offenen Kontextmenüs in Reihenfolge."""
    return tid(seite, "kontextmenue").locator('[role="menuitem"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")


def untermenue_eintraege(seite) -> list[str]:
    return seite.locator('[role="menu"] [data-testid^="km-gegenbuchung-"]').evaluate_all(
        "els => els.filter(e => e.offsetParent !== null || e.getClientRects().length)"
        ".map(e => e.getAttribute('data-testid'))")


def text_normal(s: str | None) -> str:
    return " ".join((s or "").replace(" ", " ").replace(" ", " ").split())


# ------------------------------------------------------------------ Anfragen
class Anfragen:
    """Vollständige URLs (Methode, Pfad, Abfrage) aller Anfragen der Seite an ``/api/``."""

    def __init__(self, seite) -> None:
        self.seite = seite
        self.liste: list[tuple[str, str, dict[str, list[str]]]] = []
        seite.on("request", self._neu)

    def _neu(self, req) -> None:
        t = urlsplit(req.url)
        if t.path.startswith("/api/"):
            self.liste.append((req.method, t.path, parse_qs(t.query)))

    def leeren(self) -> None:
        self.seite.wait_for_timeout(100)
        self.liste.clear()

    def buchungen_von(self, konto_id: int) -> list[dict[str, list[str]]]:
        """Abfragen aller ``GET /api/buchungen`` mit ``konto_id`` = ``konto_id``."""
        self.seite.wait_for_timeout(100)
        return [q for m, p, q in self.liste if m == "GET" and p == "/api/buchungen"
                and q.get("konto_id") == [str(konto_id)]]

    def pfade(self) -> list[str]:
        self.seite.wait_for_timeout(100)
        return [p for _, p, _ in self.liste]


# ---------------------------------------------------------------- Filter ab M30 (oberflaeche.md 39.2, E-271)
def filter_status_ausdruck(status: str) -> str:
    """Filter „Status = …“ als Kontor-Ausdruck in kanonischer Schreibweise (ausdruecke.md 2.6)."""
    return f'status == "{status}"'


def filter_abfrage(status: str) -> dict[str, list[str]]:
    """Abfrageteil der Adresse mit diesem Filter (``filter=…``)."""
    return {"filter": [filter_status_ausdruck(status)]}


def filter_status_setzen(seite, status: str) -> None:
    """Ersetzt das frühere Ankreuzen von ``filter-status-<status>``: Ausdruck in ``filter-ausdruck`` (E-271)."""
    from . import m8

    m8.filter_ausdruck_setzen(seite, filter_status_ausdruck(status))
    warte(seite, lambda: url(seite)[1].get("filter") == [filter_status_ausdruck(status)],
          text=f"filter=status == {status} in der Adresse")
