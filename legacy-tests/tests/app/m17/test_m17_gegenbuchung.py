"""M17: Kontextmenü „Gehe zur Gegenbuchung“ (oberflaeche.md 27.2 und 27.3, Definition `tabs-gegenbuchung`
Abschnitte 2 und 3, E-200, E-201).

Gegenseiten werden im Test aus den angelegten Splits bestimmt (``tests/hilfen/m17.daten``). Dass der Sprung
nichts ändert, prüfen der Mitschnitt der Anfragen (nur GET) und das Änderungsprotokoll. Nicht kern (E-202).
"""

from __future__ import annotations

from urllib.parse import parse_qs

import pytest

from tests.hilfen import m8, m17
from tests.hilfen.m8 import ausgewaehlt, oeffnen, strg, tid, warte_liste, zeile
from tests.hilfen.m15 import Mitschnitt
from tests.hilfen.m17 import aktive, text_normal, url, warte, warte_tabs, wechsle

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

FEHLER = '[data-testid="meldung"][data-art="fehler"]'
HINWEIS = '[data-testid="meldung"][data-art="hinweis"]'


def _start(starte_server, neue_seite, geraet="desktop", *, viele=False, konto="giro"):
    server = starte_server()
    d = m17.daten(server.api, viele=viele)
    seite = neue_seite(server, geraet)
    mit = Mitschnitt(seite)
    kid = d["k"][konto]
    oeffnen(seite, server, f"/konten/{kid}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(server.api, kid))
    return server, server.api, seite, mit, d["k"], d["b"]


def _menue(seite, bid):
    zeile(seite, bid).click(button="right")
    m = tid(seite, "kontextmenue")
    expect(m).to_be_visible()
    return m


def _eintrag(seite):
    return tid(seite, "kontextmenue").get_by_test_id("km-gegenbuchung")


def _ziel_ausgewaehlt(seite, api, konto_id, bid, **params):
    """Definition 2.2: Ziel-Tab aktiv, genau diese Buchung ausgewählt, mit Fokus und sichtbar."""
    m17.warte_konto(seite, konto_id)
    warte_liste(seite, m8.rest_liste(api, konto_id, **params))
    warte(seite, lambda: ausgewaehlt(seite) == {bid}, text=f"Buchung {bid} ausgewählt")
    expect(zeile(seite, bid)).to_have_attribute("aria-selected", "true")
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", "1")
    assert m17.fokuszeile(seite) == bid, "die Buchung hat den Fokus der Liste"
    expect(zeile(seite, bid)).to_be_in_viewport()


def _ohne_wirkung(seite, mit, api, a0):
    assert mit.schreibend() == [], "der Sprung sendet nur Lesezugriffe"
    assert m8.max_aenderung(api) == a0, "kein Eintrag im Änderungsprotokoll"
    expect(tid(seite, "rueckgaengig-knopf")).to_be_disabled()


# ------------------------------------------------------------------ 2.1 Eintrag


def test_eintrag_position_text_und_aktivierung(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    m = _menue(seite, b["einfach"])
    e = m17.menue_eintraege(seite)
    assert "km-gegenbuchung" in e and "km-mehrfach" in e
    assert e.index("km-gegenbuchung") == e.index("km-mehrfach") + 1, f"direkt nach „Bearbeiten…“: {e}"
    assert e[-1] == "km-loeschen", f"„Löschen…“ bleibt der letzte Eintrag: {e}"
    expect(_eintrag(seite)).to_have_attribute("role", "menuitem")
    expect(_eintrag(seite)).not_to_have_attribute("aria-disabled", "true")
    assert text_normal(_eintrag(seite).inner_text()) == "Gehe zur Gegenbuchung"
    seite.keyboard.press("Escape")
    expect(m).to_be_hidden()
    # zwei Splits auf derselben Kategorie: eine Gegenseite, kein „…“
    _menue(seite, b["doppelt"])
    assert text_normal(_eintrag(seite).inner_text()) == "Gehe zur Gegenbuchung"
    seite.keyboard.press("Escape")
    # zwei Gegenseiten: mit „…“
    _menue(seite, b["split"])
    expect(_eintrag(seite)).not_to_have_attribute("aria-disabled", "true")
    assert text_normal(_eintrag(seite).inner_text()) == "Gehe zur Gegenbuchung…"
    seite.keyboard.press("Escape")
    # ohne Gegenseite: vorhanden, deaktiviert
    _menue(seite, b["ohne"])
    expect(_eintrag(seite)).to_have_attribute("aria-disabled", "true")
    seite.keyboard.press("Escape")


def test_deaktiviert_bei_mehrfachauswahl(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    zeile(seite, b["einfach"]).click()
    zeile(seite, b["zweite"]).click(modifiers=[strg()])
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
    _menue(seite, b["einfach"])
    expect(_eintrag(seite)).to_have_attribute("aria-disabled", "true")
    _eintrag(seite).click(force=True)
    seite.wait_for_timeout(300)  # einem fälschlich ausgelösten Sprung Zeit geben (es darf nichts passieren)
    warte_tabs(seite, [g], g)
    assert ausgewaehlt(seite) == {b["einfach"], b["zweite"]}


def test_tastatur_oeffnet_menue_mit_eintrag(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    zeile(seite, b["einfach"]).click()
    seite.keyboard.press("Shift+F10")
    expect(tid(seite, "kontextmenue")).to_be_visible()
    _eintrag(seite).focus()
    seite.keyboard.press("Enter")
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"])


# ------------------------------------------------------------------ 2.2 eine Gegenseite


def test_konto_zu_kategorie_und_zurueck_ohne_wirkung(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    g, leb = f"/konten/{k['giro']}", f"/konten/{k['leb']}"
    a0 = m8.max_aenderung(api)
    expect(tid(seite, "rueckgaengig-knopf")).to_be_disabled()
    _menue(seite, b["einfach"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"])
    warte_tabs(seite, [g, leb], leb, {})
    assert m17.titel_text(seite, leb) == "Lebensmittel"
    # Kategorie → Konto: der offene Tab wird aktiv, kein neuer Tab
    _menue(seite, b["zweite"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["giro"], b["zweite"])
    warte_tabs(seite, [g, leb], g, {})
    expect(tid(seite, "filter-leiste")).to_be_hidden()
    # zwei Splits auf derselben Kategorie: direkter Sprung
    _menue(seite, b["doppelt"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["doppelt"])
    warte_tabs(seite, [g, leb], leb)
    _ohne_wirkung(seite, mit, api, a0)


def test_umbuchung_laedt_weitere_seiten(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite, viele=True)
    g, s = f"/konten/{k['giro']}", f"/konten/{k['spar']}"
    a0 = m8.max_aenderung(api)
    alle = m8.rest_liste(api, k["spar"])
    assert alle.index(b["umbuchung"]) >= 200, "Testdaten: die Umbuchung liegt nicht auf der ersten Seite"
    _menue(seite, b["umbuchung"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["spar"], b["umbuchung"])
    warte_tabs(seite, [g, s], s, {})
    _ohne_wirkung(seite, mit, api, a0)


# ------------------------------------------------------------------ 2.2 mehrere Gegenseiten


def test_untermenue_mehrere_gegenseiten(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    g, leb = f"/konten/{k['giro']}", f"/konten/{k['leb']}"
    a0 = m8.max_aenderung(api)
    _menue(seite, b["split"])
    _eintrag(seite).click()
    soll = [f"km-gegenbuchung-{k['cafe']}", f"km-gegenbuchung-{k['leb']}"]   # Split-Reihenfolge
    warte(seite, lambda: m17.untermenue_eintraege(seite) == soll, text=f"Untermenü {soll}")
    for testid, name in zip(soll, ["Café", "Lebensmittel"]):
        x = tid(seite, testid)
        expect(x).to_contain_text(name)
        assert x.evaluate("e => !!e.closest('[role=\"menu\"]')"), "Einträge liegen in einem role=menu"
    expect(tid(seite, soll[0])).to_be_focused()
    # Esc schließt ohne Wirkung
    seite.keyboard.press("Escape")
    expect(tid(seite, soll[0])).to_have_count(0)
    warte_tabs(seite, [g], g)
    # Pfeil ab + Enter wählt die zweite Gegenseite
    _menue(seite, b["split"])
    _eintrag(seite).click()
    expect(tid(seite, soll[0])).to_be_focused()
    seite.keyboard.press("ArrowDown")
    expect(tid(seite, soll[1])).to_be_focused()
    seite.keyboard.press("Enter")
    _ziel_ausgewaehlt(seite, api, k["leb"], b["split"])
    warte_tabs(seite, [g, leb], leb)
    # aus der Kategorie: Gegenseiten Café und Girokonto (ohne das eigene Konto), Klick auf Girokonto
    _menue(seite, b["split"])
    _eintrag(seite).click()
    soll2 = [f"km-gegenbuchung-{k['cafe']}", f"km-gegenbuchung-{k['giro']}"]
    warte(seite, lambda: m17.untermenue_eintraege(seite) == soll2, text=f"Untermenü {soll2}")
    expect(tid(seite, soll2[1])).to_contain_text("Girokonto")
    tid(seite, soll2[1]).click()
    _ziel_ausgewaehlt(seite, api, k["giro"], b["split"])
    warte_tabs(seite, [g, leb], g)
    _ohne_wirkung(seite, mit, api, a0)


# ------------------------------------------------------------------ 2.2 Filter des Ziel-Tabs


def test_filter_des_ziels_zurueckgesetzt_mit_hinweis(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    g, leb = f"/konten/{k['giro']}", f"/konten/{k['leb']}"
    _menue(seite, b["einfach"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"])
    # im Ziel-Tab filtern (blendet die Buchung aus) und aufsteigend nach Datum sortieren
    m17.filter_status_setzen(seite, "bestaetigt")   # ab M30 über das Ausdrucksfeld (E-271)
    tid(seite, "spalte-datum").click()
    warte(seite, lambda: url(seite)[1].get("sortierung") == ["datum"], text="sortierung=datum")
    gefiltert = m8.rest_liste(api, k["leb"], status="bestaetigt", sortierung="datum")
    assert b["einfach"] not in gefiltert
    warte_liste(seite, gefiltert)
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    a0 = m8.max_aenderung(api)
    mit.leeren()
    _menue(seite, b["einfach"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"], sortierung="datum")
    warte_tabs(seite, [g, leb], leb)
    expect(tid(seite, "filter-anzahl")).to_have_attribute("data-anzahl", "0")
    assert url(seite)[1] == {"sortierung": ["datum"]}, f"URL ohne Filter, Sortierung bleibt: {seite.url}"
    expect(tid(seite, "meldungen").locator(HINWEIS).last).to_contain_text(m17.HINWEIS_FILTER)
    _ohne_wirkung(seite, mit, api, a0)


def test_ziel_ohne_ausblendenden_filter_ohne_hinweis(starte_server, neue_seite):
    """Filter des Ziel-Tabs, die die Buchung nicht ausblenden, bleiben (Definition 1.3, 2.2)."""
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    g, leb = f"/konten/{k['giro']}", f"/konten/{k['leb']}"
    _menue(seite, b["einfach"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"])
    m17.filter_status_setzen(seite, "importiert")   # ab M30 über das Ausdrucksfeld (E-271)
    warte_liste(seite, m8.rest_liste(api, k["leb"], status="importiert"))
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    _menue(seite, b["einfach"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"], status="importiert")
    warte_tabs(seite, [g, leb], leb, m17.filter_abfrage("importiert"))
    m8.filter_aktiv(seite)
    expect(tid(seite, "filter-leiste")).to_be_hidden()
    expect(tid(seite, "meldungen").locator(HINWEIS)).to_have_count(0)


# ------------------------------------------------------------------ mobil


def test_mobil_lange_beruehrung(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite, "handy")
    g, leb = f"/konten/{k['giro']}", f"/konten/{k['leb']}"
    a0 = m8.max_aenderung(api)
    # M26 (36.2.3, 36.3, E-248): Leiste mobil verborgen, tabs-zahl zählt; Menü über mehrfach-mehr
    expect(m17.leiste(seite)).to_be_hidden()
    expect(tid(seite, "tabs-knopf")).to_be_visible()
    expect(tid(seite, "tabs-zahl")).to_have_text("1")
    m8.auswahlmenue_mobil(seite, zeile(seite, b["einfach"]))
    expect(_eintrag(seite)).to_be_visible()
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"])
    warte_tabs(seite, [g, leb], leb)
    expect(m17.leiste(seite)).to_be_hidden()
    expect(tid(seite, "tabs-zahl")).to_have_text("2")
    m17.tabs_aufklappen(seite)
    assert mit.schreibend() == [] and m8.max_aenderung(api) == a0


# ------------------------------------------------------------------ 3 Fehlerfälle


def test_gegenkonto_inzwischen_geloescht(starte_server, neue_seite):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    leb = f"/konten/{k['leb']}"
    _menue(seite, b["einfach"])
    api.post(f"/api/konten/{k['leb']}/loeschen", json={"buchungen": "unkategorisiert", "konflikte": "behalten"},
             erwartet=200)
    _eintrag(seite).click()
    m8.warte_geladen(seite, "nicht-gefunden")
    warte(seite, lambda: aktive(seite) == [leb], text="Ziel-Tab aktiv")
    assert url(seite)[0] == leb


@pytest.mark.parametrize("fall", ["geloescht", "umkategorisiert"])
def test_buchung_nicht_mehr_im_ziel(starte_server, neue_seite, fall):
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    leb = f"/konten/{k['leb']}"
    _menue(seite, b["einfach"])
    if fall == "geloescht":
        api.delete(f"/api/buchungen/{b['einfach']}", erwartet=(200, 204))
    else:
        api.put(f"/api/buchungen/{b['einfach']}/kategorie", json={"kategorie_id": k["cafe"]}, erwartet=200)
    _eintrag(seite).click()
    m17.warte_konto(seite, k["leb"])
    warte_liste(seite, m8.rest_liste(api, k["leb"]))
    warte(seite, lambda: aktive(seite) == [leb], text="Ziel-Tab aktiv")
    expect(tid(seite, "meldungen").locator(FEHLER).last).to_contain_text(m17.FEHLER_NICHT_ENTHALTEN)
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", "0")
    assert ausgewaehlt(seite) == set()


def test_abfrage_der_url_nach_sprung_ohne_filter(starte_server, neue_seite):
    """Neuer Ziel-Tab: Anfordern ohne Abfrageteil (Definition 1.3) – frischer Tab ohne Filter."""
    server, api, seite, mit, k, b = _start(starte_server, neue_seite)
    _menue(seite, b["einfach"])
    _eintrag(seite).click()
    _ziel_ausgewaehlt(seite, api, k["leb"], b["einfach"])
    assert parse_qs(seite.url.partition("?")[2]).keys() <= {"sortierung"}
    expect(tid(seite, "filter-anzahl")).to_have_attribute("data-anzahl", "0")
