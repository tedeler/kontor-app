"""M26: Bedienung auf dem Handy (oberflaeche.md 36, Definition M26, E-246, E-247).

Playwright wie M8 (E-139); Daten über REST (``tests/hilfen/m17.daten``). Nicht kern (Definition: nur 36.8).
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from tests.hilfen import m8, m17, m26
from tests.hilfen.m8 import ausgewaehlt, lange_beruehrung, oeffnen, tid, warte_liste, zeile
from tests.hilfen.m17 import aktive, fokus_tab, pfade, tab, titel, warte
from tests.hilfen.m26 import box, kein_waagerechtes_scrollen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


def _start(starte_server, neue_seite, geraet="handy", *, pfad=None, **kontext):
    server = starte_server()
    d = m17.daten(server.api)
    seite = neue_seite(server, geraet, **kontext)
    ziel = pfad or f"/konten/{d['k']['giro']}"
    oeffnen(seite, server, ziel)
    if ziel.startswith("/konten/"):
        m8.warte_geladen(seite, "konto")
        warte_liste(seite, m8.rest_liste(server.api, d["k"]["giro"]))
    return server, server.api, seite, d["k"], d["b"]


def _liste(api, konto_id):
    return m8.rest_liste(api, konto_id)


def _url(seite):
    t = urlsplit(seite.url)
    return t.path, t.query


# ------------------------------------------------------------------ 36.1, 36.2 Kopfzeile


def test_kopfzeile_eine_zeile_reihenfolge_und_groesse(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    expect(tid(seite, "app")).to_have_attribute("data-layout", "mobil")
    kopf = box(tid(seite, "app-kopf"))
    boxen = []
    for t in m26.KOPF:
        el = tid(seite, t)
        expect(el).to_be_visible()
        bx = box(el)
        assert bx["width"] >= 44 - 0.5 and bx["height"] >= 44 - 0.5, f"{t}: mindestens 44 × 44 px ({bx})"
        boxen.append((t, bx))
    # Reihenfolge in Lesefolge. Seit D-279 stehen alle Knöpfe wieder in einer Zeile (ohne „Wiederholen“ unter 403 px).
    expect(tid(seite, "wiederholen-knopf")).to_be_hidden()
    assert max(bx["y"] for _, bx in boxen) - min(bx["y"] for _, bx in boxen) <= 1, "eine Zeile (36.2.1, D-279)"
    def lesefolge(item):
        t, bx = item
        return (round((bx["y"] + bx["height"] / 2) / 22), bx["x"])
    assert [t for t, _ in sorted(boxen, key=lesefolge)] == m26.KOPF, \
        f"Reihenfolge der Kopfzeile (36.2.1): {[(t, round(bx['x']), round(bx['y'])) for t, bx in boxen]}"
    for t, bx in boxen:
        assert bx["x"] >= kopf["x"] - 1 and bx["x"] + bx["width"] <= kopf["x"] + kopf["width"] + 1, t
        assert bx["y"] >= kopf["y"] - 1 and bx["y"] + bx["height"] <= kopf["y"] + kopf["height"] + 1, t
    assert kein_waagerechtes_scrollen(seite)


def test_suche_ein_und_ausblenden(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/")
    m8.warte_geladen(seite, "uebersicht")
    knopf, feld = tid(seite, "suche-knopf"), tid(seite, "suche-feld")
    expect(feld).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(knopf).to_have_attribute("aria-label", "Suche einblenden")
    ziel = knopf.get_attribute("aria-controls")
    assert ziel and seite.evaluate("([z]) => !!document.getElementById(z)", [ziel]), "aria-controls verweist"
    knopf.click()
    expect(feld).to_be_visible()
    expect(feld).to_be_focused()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    expect(knopf).to_have_attribute("aria-label", "Suche ausblenden")
    assert box(feld)["y"] >= box(knopf)["y"] + box(knopf)["height"] - 1, "Suchfeld als zweite Zeile"
    knopf.click()
    expect(feld).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    # leeres Feld verliert den Fokus → ausgeblendet
    knopf.click()
    expect(feld).to_be_focused()
    feld.evaluate("e => e.blur()")
    expect(feld).to_be_hidden()
    # mit Inhalt bleibt es sichtbar; Absenden wie bisher
    knopf.click()
    feld.fill("Markt")
    feld.evaluate("e => e.blur()")
    expect(feld).to_be_visible()
    feld.focus()
    feld.press("Enter")
    m8.warte_geladen(seite, "suche")
    assert urlsplit(seite.url).path == "/suche"


def test_mock_hinweis_gekuerzt_und_aufklappbar(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/")
    h = tid(seite, "mock-hinweis")
    expect(h).to_be_visible()
    expect(h).to_be_in_viewport()
    zeile_hoehe = h.evaluate("e => parseFloat(getComputedStyle(e).lineHeight) || 20")
    vorher = box(h)["height"]
    voll = h.evaluate("e => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1")
    assert voll or vorher <= 2 * zeile_hoehe + 16, "Mock-Hinweis einzeilig gekürzt (36.2.4)"
    m8.tippen(seite, h)
    warte(seite, lambda: box(h)["height"] > vorher + 1, text="ganzer Text nach Tippen")
    m8.tippen(seite, h)
    warte(seite, lambda: abs(box(h)["height"] - vorher) <= 1, text="wieder gekürzt")
    expect(h).to_be_in_viewport()


# ------------------------------------------------------------------ 36.2.3 Tab-Liste


def _knopf(seite):
    return tid(seite, "tabs-knopf")


def test_tab_liste_oeffnen_waehlen_schliessen(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g, s = f"/konten/{k['giro']}", f"/konten/{k['spar']}"
    m17.oeffne_konto(seite, k["spar"])
    m17.warte_konto(seite, k["spar"])
    leb = f"/konten/{k['leb']}"
    oeffnen(seite, server, leb, seitenname="konto")
    warte(seite, lambda: aktive(seite) == [leb], text="Kategorie-Tab aktiv")
    knopf = _knopf(seite)
    expect(m17.leiste(seite)).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(tid(seite, "tabs-zahl")).to_have_text("3")
    expect(knopf).to_have_attribute("aria-label", "Geöffnete Ansichten (3)")
    ac = knopf.get_attribute("aria-controls")
    assert ac and m17.leiste(seite).evaluate("(l, ac) => l.id === ac", ac), "aria-controls → tab-leiste"
    assert pfade(seite) == [g, s, leb], "Tabs bleiben mit allen Attributen im Dokument"
    knopf.click()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    expect(m17.leiste(seite)).to_be_visible()
    warte(seite, lambda: fokus_tab(seite) == leb, text="aktiver Tab hat den Fokus")
    # Schließen (×) lässt die Liste offen
    m17.schliessen(seite, s).click()
    warte(seite, lambda: pfade(seite) == [g, leb], text="Tab geschlossen")
    expect(knopf).to_have_attribute("aria-expanded", "true")
    expect(tid(seite, "tabs-zahl")).to_have_text("2")
    # Wahl eines Tabs wechselt und klappt zu
    titel(seite, g).click()
    m17.warte_konto(seite, k["giro"])
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(m17.leiste(seite)).to_be_hidden()
    # erneutes Betätigen klappt zu
    knopf.click()
    expect(m17.leiste(seite)).to_be_visible()
    knopf.click()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(m17.leiste(seite)).to_be_hidden()
    # Esc klappt zu
    knopf.click()
    expect(m17.leiste(seite)).to_be_visible()
    seite.keyboard.press("Escape")
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(m17.leiste(seite)).to_be_hidden()
    assert aktive(seite) == [g]


def test_tab_liste_tippen_daneben_und_layoutwechsel(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/einstellungen")
    m8.warte_geladen(seite, "einstellungen")
    knopf = _knopf(seite)
    knopf.click()
    lst = box(m17.leiste(seite))
    vp = seite.viewport_size
    # ein Punkt außerhalb von Liste und Knopf: unten links im Inhalt
    x, y = 8, vp["height"] - 8
    assert not (lst["x"] <= x <= lst["x"] + lst["width"] and lst["y"] <= y <= lst["y"] + lst["height"])
    m26.tippen_bei(seite, x, y)
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(m17.leiste(seite)).to_be_hidden()
    expect(tid(seite, "seite-einstellungen")).to_be_visible()
    # Layoutwechsel zu Desktop: Liste zu, Leiste dauerhaft sichtbar
    knopf.click()
    expect(m17.leiste(seite)).to_be_visible()
    seite.set_viewport_size({"width": 1280, "height": 800})
    expect(tid(seite, "app")).to_have_attribute("data-layout", "desktop")
    expect(m17.leiste(seite)).to_be_visible()
    expect(knopf).to_be_hidden()
    seite.set_viewport_size({"width": 390, "height": 844})
    expect(tid(seite, "app")).to_have_attribute("data-layout", "mobil")
    expect(m17.leiste(seite)).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")


# ------------------------------------------------------------------ 36.3 Auswahlmodus


def test_lange_beruehrung_beginnt_auswahlmodus(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    r = _liste(api, k["giro"])
    liste = tid(seite, "buchungsliste")
    assert liste.get_attribute("data-auswahlmodus") in (None, "nein")
    expect(tid(seite, "auswahl-kopf")).to_be_hidden()
    expect(tid(seite, "buchung-erfassen")).to_be_visible()
    lange_beruehrung(seite, zeile(seite, r[1]))
    expect(liste).to_have_attribute("data-auswahlmodus", "ja")
    assert ausgewaehlt(seite) == {r[1]}
    expect(tid(seite, "kontextmenue")).to_be_hidden()
    expect(tid(seite, "panel-details")).to_be_hidden()
    kopf = tid(seite, "auswahl-kopf")
    expect(kopf).to_be_visible()
    expect(kopf).to_have_attribute("role", "toolbar")
    expect(kopf).to_have_attribute("aria-label", "Auswahlmodus")
    assert box(kopf)["y"] >= box(tid(seite, "app-kopf"))["y"] + box(tid(seite, "app-kopf"))["height"] - 1
    expect(tid(seite, "rueckgaengig-knopf")).to_be_visible()
    expect(kopf.get_by_test_id("auswahl-beenden")).to_have_attribute("aria-label", "Auswahl beenden")
    anzahl = kopf.get_by_test_id("auswahl-kopf-anzahl")
    expect(anzahl).to_have_text("1 ausgewählt")
    expect(anzahl).to_have_attribute("aria-live", "polite")
    expect(tid(seite, "buchung-erfassen")).to_be_hidden()
    # zweite lange Berührung nimmt hinzu
    lange_beruehrung(seite, zeile(seite, r[3]))
    warte(seite, lambda: ausgewaehlt(seite) == {r[1], r[3]}, text="zwei ausgewählt")
    expect(anzahl).to_have_text("2 ausgewählt")
    # Tippen schaltet um, Einzelheiten öffnen sich nicht
    m8.tippen(seite, zeile(seite, r[0]))
    warte(seite, lambda: ausgewaehlt(seite) == {r[0], r[1], r[3]}, text="drei ausgewählt")
    m8.tippen(seite, zeile(seite, r[3]))
    warte(seite, lambda: ausgewaehlt(seite) == {r[0], r[1]}, text="umgeschaltet")
    expect(tid(seite, "panel-details")).to_be_hidden()
    # auswahl-alle wählt alle geladenen
    kopf.get_by_test_id("auswahl-alle").click()
    warte(seite, lambda: ausgewaehlt(seite) == set(r), text="alle ausgewählt")
    expect(anzahl).to_have_text(f"{len(r)} ausgewählt")
    # Auswahl beenden
    kopf.get_by_test_id("auswahl-beenden").click()
    warte(seite, lambda: ausgewaehlt(seite) == set(), text="Auswahl aufgehoben")
    assert liste.get_attribute("data-auswahlmodus") in (None, "nein")
    expect(kopf).to_be_hidden()
    expect(tid(seite, "buchung-erfassen")).to_be_visible()


def test_abwaehlen_der_letzten_beendet(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    r = _liste(api, k["giro"])
    lange_beruehrung(seite, zeile(seite, r[0]))
    expect(tid(seite, "auswahl-kopf")).to_be_visible()
    m8.tippen(seite, zeile(seite, r[0]))
    warte(seite, lambda: ausgewaehlt(seite) == set(), text="letzte abgewählt")
    expect(tid(seite, "auswahl-kopf")).to_be_hidden()
    assert tid(seite, "buchungsliste").get_attribute("data-auswahlmodus") in (None, "nein")
    # danach öffnet Tippen wieder die Einzelheiten (36.3.1)
    m8.tippen(seite, zeile(seite, r[0]))
    expect(tid(seite, "panel-details")).to_be_visible()


def test_zurueck_beendet_auswahl_ohne_ansicht_zu_verlassen(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/konten")
    m8.warte_geladen(seite, "konten")
    m17.oeffne_konto(seite, k["giro"])
    m17.warte_konto(seite, k["giro"])
    r = _liste(api, k["giro"])
    warte_liste(seite, r)
    vorher_url, vorher_tabs = _url(seite), pfade(seite)
    m8.auswahl_starten_mobil(seite, zeile(seite, r[0]))
    expect(tid(seite, "auswahl-kopf")).to_be_visible()
    seite.go_back()
    warte(seite, lambda: ausgewaehlt(seite) == set(), text="Zurück hebt die Auswahl auf")
    expect(tid(seite, "auswahl-kopf")).to_be_hidden()
    assert _url(seite) == vorher_url, "Pfad und Abfrageteil bleiben"
    assert pfade(seite) == vorher_tabs and aktive(seite) == [f"/konten/{k['giro']}"], "kein Tab-Wechsel"
    expect(tid(seite, "seite-konto")).to_be_visible()
    # anders beendet: das spätere Zurück führt zur vorigen Ansicht (kein leerer Schritt)
    m8.auswahl_starten_mobil(seite, zeile(seite, r[1]))
    expect(tid(seite, "auswahl-kopf")).to_be_visible()
    tid(seite, "auswahl-beenden").click()
    expect(tid(seite, "auswahl-kopf")).to_be_hidden()
    seite.go_back()
    m8.warte_geladen(seite, "konten")
    assert urlsplit(seite.url).path == "/konten"


def test_mehrfach_leiste_und_mehr_wie_rechtsklick(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    r = _liste(api, k["giro"])
    m = m8.auswahlmenue_mobil(seite, zeile(seite, b["einfach"]))
    seite.keyboard.press("Escape")
    expect(m).to_be_hidden()
    leiste = tid(seite, "mehrfach-leiste")
    expect(leiste).to_be_visible()
    for t in m26.LEISTE_SICHTBAR:
        expect(leiste.get_by_test_id(t)).to_be_visible()
    for t in m26.LEISTE_VERBORGEN:
        el = leiste.get_by_test_id(t)
        if el.count():
            expect(el).to_be_hidden()
    mehr = tid(seite, "mehrfach-mehr")
    expect(mehr).to_have_text("Mehr")
    expect(mehr).to_have_attribute("aria-haspopup", "menu")
    mehr.click()
    expect(tid(seite, "kontextmenue")).to_be_visible()
    mobil = m26.kontextmenue_eintraege(seite)
    for e in ("km-status", "km-splitten", "km-gegenbuchung", "km-kategorie", "km-tags", "km-loeschen"):
        assert e in mobil, e
    expect(tid(seite, "km-splitten")).not_to_have_attribute("aria-disabled", "true")
    # dieselben Einträge wie ein Rechtsklick auf Desktop (ohne die mobilen Zusätze aus M28 9, E-247)
    d = neue_seite(server, "desktop")
    oeffnen(d, server, f"/konten/{k['giro']}", seitenname="konto")
    warte_liste(d, r)
    zeile(d, b["einfach"]).locator('[data-feld="verwendungszweck"]').click(button="right")
    expect(tid(d, "kontextmenue")).to_be_visible()
    desktop = m26.kontextmenue_eintraege(d)
    nur_mobil = {"km-dokument-foto", "km-verschieben"}
    assert [e for e in mobil if e not in nur_mobil] == [e for e in desktop if e not in nur_mobil]


def test_erfassen_schwebend_und_titelzeile(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    knopf = tid(seite, "buchung-erfassen")
    expect(knopf).to_be_visible()
    pos = knopf.evaluate("e => getComputedStyle(e).position")
    assert pos in ("fixed", "sticky", "absolute"), f"schwebend, nicht im Seitenfluss ({pos})"
    bx, vp = box(knopf), seite.viewport_size
    assert bx["x"] + bx["width"] / 2 > vp["width"] / 2 and bx["y"] + bx["height"] / 2 > vp["height"] / 2, \
        "unten rechts"
    # ab M30 ohne die Zeile mit `filter-umschalten` (oberflaeche.md 39.8, E-271)

# ------------------------------------------------------------------ 36.1.2 Desktop unverändert


def test_desktop_neue_elemente_unsichtbar_und_touch_menue(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, "desktop", has_touch=True)
    expect(tid(seite, "app")).to_have_attribute("data-layout", "desktop")
    for t in ("suche-knopf", "tabs-knopf", "tabs-zahl"):
        expect(tid(seite, t)).to_be_attached()
        expect(tid(seite, t)).to_be_hidden()
    expect(tid(seite, "suche-feld")).to_be_visible()
    expect(m17.leiste(seite)).to_be_visible()
    r = _liste(api, k["giro"])
    lange_beruehrung(seite, zeile(seite, r[2]))
    expect(tid(seite, "kontextmenue")).to_be_visible()
    assert ausgewaehlt(seite) == {r[2]}
    for t in ("auswahl-kopf", "mehrfach-mehr"):
        el = tid(seite, t)
        expect(el).to_be_attached()
        expect(el).to_be_hidden()


# ------------------------------------------------------------------ 36.4 Wischgesten


def test_wischhinweis_rechts(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    r = _liste(api, k["giro"])
    z = zeile(seite, r[1])
    x0 = box(z)["x"]
    w = m26.Wisch(seite, z, start_dx=-120)
    w.nach(50)
    h = warte(seite, lambda: m26.sichtbarer_hinweis(seite), text="Wischhinweis sichtbar")
    expect(h).to_have_attribute("aria-hidden", "true")
    expect(h).to_have_attribute("data-richtung", "rechts")
    expect(h).to_have_attribute("data-bereit", "nein")
    expect(h).to_contain_text("✓ Auswählen")
    warte(seite, lambda: box(z)["x"] > x0 + 10, text="Zeile folgt dem Finger")
    w.nach(110)
    expect(h).to_have_attribute("data-bereit", "ja")
    w.nach(240)
    warte(seite, lambda: box(z)["x"] - x0 <= 160 + 1 and box(z)["x"] - x0 > 80, text="höchstens 160 px")
    w.loslassen()
    warte(seite, lambda: m26.sichtbarer_hinweis(seite) is None, text="Hinweis nach Loslassen verborgen")
    warte(seite, lambda: abs(box(z)["x"] - x0) <= 1, text="Zeile wieder an ihrem Platz")
    warte(seite, lambda: ausgewaehlt(seite) == {r[1]}, text="Wischen nach rechts wählt aus")
    # ausgewählte Zeile: „✕ Abwählen“
    w = m26.Wisch(seite, z, start_dx=-120)
    w.nach(60)
    h = warte(seite, lambda: m26.sichtbarer_hinweis(seite), text="Wischhinweis sichtbar")
    expect(h).to_contain_text("✕ Abwählen")
    w.loslassen()


def test_wischhinweis_links_und_senkrecht_abbruch(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    r = _liste(api, k["giro"])
    z = zeile(seite, r[2])
    x0 = box(z)["x"]
    w = m26.Wisch(seite, z, start_dx=120)
    w.nach(-100)
    h = warte(seite, lambda: m26.sichtbarer_hinweis(seite), text="Wischhinweis sichtbar")
    expect(h).to_have_attribute("data-richtung", "links")
    expect(h).to_have_attribute("data-bereit", "ja")
    expect(h).to_contain_text("Kategorie")
    w.nach(-100, 60)
    warte(seite, lambda: m26.sichtbarer_hinweis(seite) is None, text="Hinweis verschwindet bei > 40 px senkrecht")
    w.loslassen()
    warte(seite, lambda: abs(box(z)["x"] - x0) <= 1, text="Zeile wieder an ihrem Platz")
    seite.wait_for_timeout(200)  # Zeitraum, in dem ein Dialog erschiene
    expect(tid(seite, "kategorie-auswahl")).to_be_hidden()


def test_langsames_wischen_loest_mobil_aus(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    r = _liste(api, k["giro"])
    m26.langsam_wischen(seite, zeile(seite, r[3]), "rechts")
    warte(seite, lambda: ausgewaehlt(seite) == {r[3]}, text="langsames Wischen (> 1 s) schaltet die Auswahl um")
    m26.langsam_wischen(seite, zeile(seite, r[0]), "links")
    expect(tid(seite, "kategorie-auswahl")).to_be_visible()


# ------------------------------------------------------------------ 36.5 Blätter


def _unten_volle_breite(seite, el, *, toleranz=2):
    bx, vp = box(el), seite.viewport_size
    assert abs(bx["x"]) <= toleranz, f"linker Rand 0 ({bx})"
    assert abs(bx["x"] + bx["width"] - vp["width"]) <= toleranz, f"rechter Rand = Breite ({bx}, {vp})"
    assert abs(bx["y"] + bx["height"] - vp["height"]) <= toleranz, f"Unterkante unten ({bx}, {vp})"
    return bx


def test_kontextmenue_als_blatt(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    m = m8.auswahlmenue_mobil(seite, zeile(seite, b["einfach"]))
    _unten_volle_breite(seite, m)
    eintraege = m.locator('[role="menuitem"]')
    for i in range(eintraege.count()):
        e = eintraege.nth(i)
        if e.get_attribute("aria-disabled") == "true":
            expect(e).to_be_hidden()
        else:
            expect(e).to_be_visible()
            assert box(e)["height"] >= 48 - 0.5, f"{e.get_attribute('data-testid')}: mindestens 48 px"
    assert any(eintraege.nth(i).get_attribute("aria-disabled") == "true" for i in range(eintraege.count())), \
        "Testdaten: mindestens ein nicht verfügbarer Eintrag (z. B. km-dublette ohne Verdacht)"
    seite.keyboard.press("Escape")
    expect(m).to_be_hidden()
    # auch andere Menüs: Konto in der Finanzübersicht (lange Berührung, 36.3.5)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    lange_beruehrung(seite, tid(seite, f"uebersicht-konto-{k['giro']}"))
    m = tid(seite, "kontextmenue")
    expect(m).to_be_visible()
    expect(m.get_by_test_id("km-konto-oeffnen")).to_be_visible()
    _unten_volle_breite(seite, m)


def test_dialog_als_blatt_fokus_und_hintergrund(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    tid(seite, "buchung-erfassen").click()
    d = tid(seite, "erfassen-dialog")
    expect(d).to_be_visible()
    expect(d).to_have_attribute("role", "dialog")
    bx = _unten_volle_breite(seite, d)
    assert bx["height"] <= 0.92 * seite.viewport_size["height"] + 1, "höchstens 92 % der Höhe"
    art = seite.evaluate("""() => { const e = document.activeElement; if (!e) return null;
      return [e.tagName, (e.getAttribute('type') || '').toLowerCase()]; }""")
    assert art and not (art[0] == "TEXTAREA" or (art[0] == "INPUT" and art[1] in ("", "text", "search", "number",
                                                                                  "email", "tel", "url",
                                                                                  "password"))), \
        f"Fokus nicht in einem Textfeld (36.5.3): {art}"
    assert d.evaluate("d => d.contains(document.activeElement)"), "Fokus im Dialog"
    # Tippen auf den abgedunkelten Bereich wirkt wie Esc
    m26.tippen_bei(seite, seite.viewport_size["width"] / 2, max(bx["y"] / 2, 2))
    expect(d).to_be_hidden()


def test_befehlspalette_oben_volle_breite(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    tid(seite, "befehlspalette-knopf").click()
    p = tid(seite, "befehlspalette")
    expect(p).to_be_visible()
    bx, vp = box(p), seite.viewport_size
    assert abs(bx["x"]) <= 2 and abs(bx["x"] + bx["width"] - vp["width"]) <= 2, f"volle Breite ({bx})"
    kopf = box(tid(seite, "app-kopf"))
    assert bx["y"] <= kopf["y"] + kopf["height"] + 2, f"oben (36.5.2): {bx}"
    expect(tid(seite, "befehlspalette-eingabe")).to_be_focused()


def test_viewport_meta(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/")
    inhalt = seite.locator('meta[name="viewport"]').get_attribute("content") or ""
    assert "interactive-widget=resizes-content" in inhalt.replace(" ", ""), inhalt


# ------------------------------------------------------------------ 36.6 Karten


def _karte_pruefen(seite, zeile_el, name_sel, betrag_sel):
    z, n, bt = box(zeile_el), box(zeile_el.locator(name_sel).first), box(zeile_el.locator(betrag_sel).first)
    assert abs(n["y"] - bt["y"]) <= 8, f"Bezeichnung und Betrag in derselben Zeile ({n}, {bt})"
    assert bt["x"] > n["x"], "Betrag rechts der Bezeichnung"
    assert z["x"] + z["width"] - (bt["x"] + bt["width"]) <= 32, f"Betrag am rechten Rand ({z}, {bt})"
    assert zeile_el.evaluate("e => getComputedStyle(e).display") != "table-row", "Karte statt Tabellenzeile"


def test_karten_uebersicht_und_konten(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/")
    m8.warte_geladen(seite, "uebersicht")
    t = tid(seite, "uebersicht-tabelle")
    kopf = t.locator("thead")
    if kopf.count():
        expect(kopf.first).to_be_hidden()
    _karte_pruefen(seite, tid(seite, f"uebersicht-konto-{k['giro']}"), '[data-feld="name"]', '[data-feld="saldo"]')
    expect(tid(seite, f"uebersicht-konto-{k['giro']}").locator('[data-feld="saldo"]')).to_have_attribute(
        "data-betrag", str(api.salden()[k["giro"]]["saldo_gesamt"]))
    assert kein_waagerechtes_scrollen(seite)
    m8.navigiere(seite, "konten")
    baum = tid(seite, "kontenbaum")
    if baum.locator("thead").count():
        expect(baum.locator("thead").first).to_be_hidden()
    z = tid(seite, f"kontenbaum-konto-{k['giro']}")
    expect(z).to_be_visible()
    assert z.evaluate("e => getComputedStyle(e).display") != "table-row"
    assert kein_waagerechtes_scrollen(seite)


def test_desktop_tabellen_unveraendert(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, "desktop", pfad="/")
    m8.warte_geladen(seite, "uebersicht")
    z = tid(seite, f"uebersicht-konto-{k['giro']}")
    assert z.evaluate("e => getComputedStyle(e).display") == "table-row"
    kopf = tid(seite, "uebersicht-tabelle").locator("thead")
    if kopf.count():
        expect(kopf.first).to_be_visible()


def test_suchtreffer_kompakt_und_tippen_springt(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/suche?q=Wocheneinkauf")
    m8.warte_geladen(seite, "suche")
    t = tid(seite, f"buchung-{b['einfach']}")
    expect(t).to_be_visible()
    assert kein_waagerechtes_scrollen(seite)
    m8.tippen(seite, t)
    m17.warte_konto(seite, k["giro"])
    # D-281: mobil ist das Sprungziel markiert, nicht ausgewählt (Auswahlmodus nur über das Kontextmenü)
    expect(zeile(seite, b["einfach"])).to_have_attribute("data-markiert", "")
    assert ausgewaehlt(seite) == set(), "kein Auswahlmodus nach dem Sprung"
    assert m17.fokuszeile(seite) == b["einfach"], "Buchung fokussiert"


# ------------------------------------------------------------------ 36.1.3 kein waagerechtes Scrollen

SEITEN = ["/", "/konten", "/kategorien", "/kredite", "/berichte", "/import", "/einstellungen", "/protokoll",
          "/empfaenger", "/regeln", "/vorlagen", "/dubletten", "/sync", "/erwartet", "/benachrichtigungen",
          "/suche?q=Markt", "{giro}", "{leb}"]


def test_kein_waagerechtes_scrollen_auf_allen_seiten(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, pfad="/")
    for p in SEITEN:
        pfad = p.format(giro=f"/konten/{k['giro']}", leb=f"/konten/{k['leb']}")
        oeffnen(seite, server, pfad)
        warte(seite, lambda: seite.locator('[data-testid^="seite-"][data-geladen="ja"]').count() >= 1,
              text=f"{pfad} geladen")
        assert kein_waagerechtes_scrollen(seite), pfad
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    tab(seite, f"/konten/{k['giro']}")
    m17.tabs_aufklappen(seite)
    assert kein_waagerechtes_scrollen(seite), "Tab-Liste"
