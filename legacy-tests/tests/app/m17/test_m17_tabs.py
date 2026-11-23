"""M17: Tabs der Ansichten (oberflaeche.md 27.1, Definition `tabs-gegenbuchung` Abschnitt 1, E-199 bis E-202).

Playwright wie M8 (E-139); Daten über REST (``tests/hilfen/m17.daten``), erwartete Listen aus REST-Abfragen,
die der Test selbst stellt. Nicht kern (E-202).
"""

from __future__ import annotations

from urllib.parse import urlencode

import pytest

from tests.hilfen import m8, m17
from tests.hilfen.m8 import ausgewaehlt, filter_aufklappen, navigiere, oeffnen, strg, tid, warte_geladen, \
    warte_liste, zeile
from tests.hilfen.m17 import aktive, oeffne_konto, pfade, tab, titel, titel_text, url, warte, warte_tabs, wechsle

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


def _start(starte_server, neue_seite, geraet="desktop", *, viele=False, pfad=None):
    server = starte_server()
    d = m17.daten(server.api, viele=viele)
    seite = neue_seite(server, geraet)
    ziel = pfad or f"/konten/{d['k']['giro']}"
    oeffnen(seite, server, ziel)
    return server, server.api, seite, d["k"], d["b"]


def _liste(api, konto_id, **params):
    return m8.rest_liste(api, konto_id, **params)


def _filter_importiert(seite, api, konto_id):
    """Filter Status „importiert“ über das Ausdrucksfeld setzen (oberflaeche.md 39.2, E-271); der Baukasten wird
    dazu aufgeklappt, damit die Tests den Zustand der Leiste je Tab weiter prüfen."""
    filter_aufklappen(seite)
    m17.filter_status_setzen(seite, "importiert")
    warte_liste(seite, _liste(api, konto_id, status="importiert"))


def _waehle(seite, *bids):
    zeile(seite, bids[0]).click()
    for bid in bids[1:]:
        zeile(seite, bid).click(modifiers=[strg()])
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", str(len(bids)))


# ------------------------------------------------------------------ 1.1/1.2 Leiste, Attribute, ein Tab je Pfad


@pytest.mark.parametrize("geraet", ["desktop", "handy"])
def test_tab_leiste_und_attribute(starte_server, neue_seite, geraet):
    server, api, seite, k, b = _start(starte_server, neue_seite, geraet)
    g = f"/konten/{k['giro']}"
    warte_geladen(seite, "konto")
    lst = m17.leiste(seite)
    m17.leiste_sichtbar(seite, geraet)   # mobil erst nach tabs-knopf (M26 36.2.3, E-248)
    expect(lst).to_have_attribute("role", "tablist")
    assert (lst.get_attribute("aria-label") or "").strip(), "tab-leiste braucht ein aria-label"
    assert lst.evaluate("e => !e.closest('[data-testid=\"hauptbereich\"]') && !e.closest('main')"), \
        "tab-leiste liegt außerhalb von hauptbereich"
    warte_tabs(seite, [g], g, {})
    t = tab(seite, g)
    expect(t).to_have_attribute("role", "tab")
    expect(t).to_have_attribute("aria-selected", "true")
    assert titel_text(seite, g) == "Girokonto"
    assert titel(seite, g).evaluate("e => e.tagName") == "A"
    assert titel(seite, g).evaluate("e => new URL(e.href, location.href).pathname + new URL(e.href, location.href)"
                                    ".search") == g
    assert "Girokonto" in (m17.schliessen(seite, g).get_attribute("aria-label") or "")
    # Navigation: neuer Tab rechts, aktiv; der inaktive hängt nicht im Dokument
    navigiere(seite, "uebersicht")
    warte_tabs(seite, [g, "/"], "/", {})
    assert titel_text(seite, "/") == "Finanzübersicht"
    expect(tab(seite, g)).to_have_attribute("aria-selected", "false")
    expect(tid(seite, "seite-konto")).to_have_count(0)
    expect(tid(seite, "buchungsliste")).to_have_count(0)
    expect(tid(seite, "seite-uebersicht")).to_have_count(1)
    expect(tid(seite, "hauptbereich")).to_have_count(1)
    m17.leiste_sichtbar(seite, geraet)
    # Kategorie-Ansicht und „Nicht gefunden“ bekommen ebenfalls einen Tab (direkter Aufruf)
    oeffnen(seite, server, f"/konten/{k['leb']}", seitenname="konto")
    leb = f"/konten/{k['leb']}"
    warte(seite, lambda: aktive(seite) == [leb], text="Kategorie-Tab aktiv")
    assert titel_text(seite, leb) == "Lebensmittel"
    oeffnen(seite, server, "/konten/999999", seitenname="nicht-gefunden")
    warte(seite, lambda: aktive(seite) == ["/konten/999999"], text="Tab für „Nicht gefunden“ aktiv")
    assert titel_text(seite, "/konten/999999") == "Nicht gefunden"
    assert len(pfade(seite)) == len(set(pfade(seite))), "höchstens ein Tab je Pfad"
    expect(tid(seite, "seite-konto")).to_have_count(0)


def test_ein_tab_je_pfad_neuer_rechts_vom_aktiven(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g, s = f"/konten/{k['giro']}", f"/konten/{k['spar']}"
    warte_tabs(seite, [g], g)
    navigiere(seite, "uebersicht")
    warte_tabs(seite, [g, "/"], "/")
    wechsle(seite, g)
    warte_tabs(seite, [g, "/"], g)
    navigiere(seite, "konten")
    warte_tabs(seite, [g, "/konten", "/"], "/konten")
    assert titel_text(seite, "/konten") == "Konten"
    navigiere(seite, "uebersicht")
    warte_tabs(seite, [g, "/konten", "/"], "/")
    oeffne_konto(seite, k["spar"])
    m17.warte_konto(seite, k["spar"])
    warte_tabs(seite, [g, "/konten", "/", s], s)
    assert titel_text(seite, s) == "Tagesgeld"
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    oeffne_konto(seite, k["spar"])
    m17.warte_konto(seite, k["spar"])
    warte_tabs(seite, [g, "/konten", "/", s], s)
    # derselbe Pfad mit Abfrageteil ist derselbe Tab
    oeffnen(seite, server, f"{s}?{urlencode({'filter': m17.filter_status_ausdruck('bestaetigt')})}",
            seitenname="konto")
    warte_tabs(seite, [g, "/konten", "/", s], s, m17.filter_abfrage("bestaetigt"))


# ------------------------------------------------------------------ 1.3 Zustand beim Wechsel


def test_zustand_beim_wechsel_ueber_tab_und_zurueck(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    _filter_importiert(seite, api, k["giro"])
    tid(seite, "spalte-betrag").click()
    warte(seite, lambda: url(seite)[1].get("sortierung") == ["betrag"], text="sortierung=betrag in der URL")
    liste = _liste(api, k["giro"], status="importiert", sortierung="betrag")
    warte_liste(seite, liste)
    _waehle(seite, b["einfach"], b["doppelt"])
    abfrage = url(seite)[1]

    def pruefe():
        m17.warte_konto(seite, k["giro"])
        warte_tabs(seite, [g, "/"], g, abfrage)
        warte_liste(seite, liste)
        expect(tid(seite, "filter-leiste")).to_be_visible()
        expect(tid(seite, m8.FILTER_UMSCHALTER)).to_have_attribute("aria-expanded", "true")
        assert "importiert" in m8.filter_ausdruck_wert(seite)
        m8.filter_aktiv(seite)
        expect(seite.locator('[data-testid="spalte-betrag"]').locator(
            "xpath=ancestor-or-self::*[@role='columnheader'][1]")).to_have_attribute("aria-sort", "ascending")
        assert ausgewaehlt(seite) == {b["einfach"], b["doppelt"]}
        expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", "2")
        assert m17.fokuszeile(seite) == b["doppelt"]

    navigiere(seite, "uebersicht")
    warte_tabs(seite, [g, "/"], "/", {})
    wechsle(seite, g)
    pruefe()
    navigiere(seite, "uebersicht")
    warte_tabs(seite, [g, "/"], "/", {})
    seite.go_back()
    pruefe()
    seite.go_forward()
    warte_tabs(seite, [g, "/"], "/", {})
    warte_geladen(seite, "uebersicht")


def test_nachgeladene_seiten_bleiben_beim_wechsel(starte_server, neue_seite):
    server = starte_server()
    d = m17.daten(server.api, viele=True)
    k = d["k"]
    seite = neue_seite(server)
    s = f"/konten/{k['spar']}"
    oeffnen(seite, server, s, seitenname="konto")
    alle = _liste(server.api, k["spar"])
    assert len(alle) > 200
    warte_liste(seite, alle[:200])
    tid(seite, "buchungsliste-mehr").click()
    warte_liste(seite, alle)
    navigiere(seite, "uebersicht")
    warte_tabs(seite, [s, "/"], "/")
    wechsle(seite, s)
    m17.warte_konto(seite, k["spar"])
    warte_liste(seite, alle)
    expect(tid(seite, "buchungsliste-mehr")).to_be_hidden()


def test_anfordern_ueber_navigation_klappt_filterleiste_ein(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g, s = f"/konten/{k['giro']}", f"/konten/{k['spar']}"
    _filter_importiert(seite, api, k["giro"])
    liste = _liste(api, k["giro"], status="importiert")
    _waehle(seite, b["einfach"])
    oeffne_konto(seite, k["spar"])
    m17.warte_konto(seite, k["spar"])
    warte_tabs(seite, [g, s], s, {})
    expect(tid(seite, "filter-leiste")).to_be_hidden()   # neuer Tab: frisch, eingeklappt

    def pruefe():
        m17.warte_konto(seite, k["giro"])
        warte_tabs(seite, [g, s], g, m17.filter_abfrage("importiert"))
        warte_liste(seite, liste)
        expect(tid(seite, "filter-leiste")).to_be_hidden()
        expect(tid(seite, m8.FILTER_UMSCHALTER)).to_have_attribute("aria-expanded", "false")
        m8.filter_aktiv(seite)
        assert ausgewaehlt(seite) == {b["einfach"]}

    oeffne_konto(seite, k["giro"])
    pruefe()
    # auch wenn der angeforderte Tab schon aktiv ist und eigene Filter hat
    filter_aufklappen(seite)
    oeffne_konto(seite, k["giro"])
    pruefe()


def test_direkter_aufruf_zeigt_abfrage_der_url(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    _filter_importiert(seite, api, k["giro"])
    navigiere(seite, "uebersicht")
    warte_tabs(seite, [g, "/"], "/")
    oeffnen(seite, server, f"{g}?{urlencode({'filter': m17.filter_status_ausdruck('bestaetigt')})}",
            seitenname="konto")
    warte_tabs(seite, [g, "/"], g, m17.filter_abfrage("bestaetigt"))
    warte_liste(seite, _liste(api, k["giro"], status="bestaetigt"))
    m8.filter_aktiv(seite)
    wert = m8.filter_ausdruck_wert(seite)
    assert "bestaetigt" in wert and "importiert" not in wert
    oeffnen(seite, server, g, seitenname="konto")
    warte_tabs(seite, [g, "/"], g, {})
    warte_liste(seite, _liste(api, k["giro"]))
    expect(tid(seite, "filter-anzahl")).to_have_attribute("data-anzahl", "0")


# ------------------------------------------------------------------ 1.5 Schließen und Wiederöffnen


def test_schliessen_nachbarn_und_wiederoeffnen(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    seite.context.on("page", lambda p: p.close())   # Mittelklick darf kein Browserfenster stehen lassen
    _filter_importiert(seite, api, k["giro"])
    _waehle(seite, b["einfach"])
    navigiere(seite, "uebersicht")
    navigiere(seite, "konten")
    warte_tabs(seite, [g, "/", "/konten"], "/konten")
    # inaktiven Tab schließen: aktiver bleibt
    m17.schliessen(seite, g).click()
    warte_tabs(seite, ["/", "/konten"], "/konten", {})
    warte_geladen(seite, "konten")
    # Wiederöffnen: neuer Tab rechts vom aktiven, frischer Zustand
    oeffne_konto(seite, k["giro"])
    m17.warte_konto(seite, k["giro"])
    warte_tabs(seite, ["/", "/konten", g], g, {})
    warte_liste(seite, _liste(api, k["giro"]))
    expect(tid(seite, "filter-anzahl")).to_have_attribute("data-anzahl", "0")
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", "0")
    assert ausgewaehlt(seite) == set()
    # aktiven Tab schließen: rechter Nachbar
    wechsle(seite, "/")
    warte_tabs(seite, ["/", "/konten", g], "/")
    m17.schliessen(seite, "/").click()
    warte_tabs(seite, ["/konten", g], "/konten")
    warte_geladen(seite, "konten")
    # aktiven Tab ohne rechten Nachbarn schließen (Mittelklick): linker Nachbar
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    titel(seite, g).click(button="middle")
    warte_tabs(seite, ["/konten"], "/konten")
    warte_geladen(seite, "konten")
    # letzten Tab schließen (Entf auf dem fokussierten Tab): Finanzübersicht in neuem Tab
    m17.fokus_auf_tab(seite, "/konten")
    seite.keyboard.press("Delete")
    warte_tabs(seite, ["/"], "/", {})
    warte_geladen(seite, "uebersicht")


def test_mittelklick_auf_inaktiven_tab_schliesst_ohne_wechsel(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    seite.context.on("page", lambda p: p.close())
    navigiere(seite, "uebersicht")
    navigiere(seite, "konten")
    warte_tabs(seite, [g, "/", "/konten"], "/konten")
    titel(seite, g).click(button="middle")
    warte_tabs(seite, ["/", "/konten"], "/konten", {})


# ------------------------------------------------------------------ 1.6 Speicherung


def test_speicherung_ueber_neuladen_und_lazy(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    _filter_importiert(seite, api, k["giro"])
    _waehle(seite, b["einfach"])
    navigiere(seite, "uebersicht")
    navigiere(seite, "konten")
    warte_tabs(seite, [g, "/", "/konten"], "/konten")
    titel_vorher = {p: titel_text(seite, p) for p in pfade(seite)}
    anfragen = m17.Anfragen(seite)
    seite.reload()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    warte_geladen(seite, "konten")
    warte_tabs(seite, [g, "/", "/konten"], "/konten", {})
    assert {p: titel_text(seite, p) for p in pfade(seite)} == titel_vorher
    # die übrigen Tabs laden erst, wenn sie aktiv werden
    assert anfragen.buchungen_von(k["giro"]) == [], "inaktiver Tab hat seine Buchungsliste schon geladen"
    assert f"/api/konten/{k['giro']}" not in anfragen.pfade()
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    warte_tabs(seite, [g, "/", "/konten"], g, m17.filter_abfrage("importiert"))
    warte_liste(seite, _liste(api, k["giro"], status="importiert"))
    m8.filter_aktiv(seite)
    assert ausgewaehlt(seite) == set(), "Auswahl wird nicht gespeichert"
    assert any(q.get("filter") == [m17.filter_status_ausdruck("importiert")]
               for q in anfragen.buchungen_von(k["giro"]))
    # neuer Aufruf der Anwendung im selben Browser
    neu = seite.context.new_page()
    try:
        oeffnen(neu, server, "/", seitenname="uebersicht")
        warte_tabs(neu, [g, "/", "/konten"], "/", {})
    finally:
        neu.close()


def test_hoechstens_40_tabs_gespeichert(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    ids = [api.konto(f"Konto {i:02d}", "girokonto")["id"] for i in range(1, 42)]
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    for kid in ids:
        oeffne_konto(seite, kid)
        m17.warte_konto(seite, kid)
    letzter = f"/konten/{ids[-1]}"
    warte(seite, lambda: len(pfade(seite)) == 42, text="42 offene Tabs (keine Begrenzung in der laufenden Seite)")
    assert aktive(seite) == [letzter]
    seite.reload()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    m17.warte_konto(seite, ids[-1])
    p = pfade(seite)
    assert 1 <= len(p) <= 40, f"nach dem Neuladen {len(p)} Tabs, gespeichert werden höchstens 40"
    assert aktive(seite) == [letzter] and letzter in p
    assert len(p) == len(set(p))
    assert all(titel_text(seite, x) for x in p), "Titel nie leer"


GESPERRT = {
    # wie in Chromium bei gesperrtem Website-Speicher: schon der Zugriff auf window.localStorage wirft
    "nicht_verfuegbar": """(() => { const f = () => { throw new DOMException('gesperrt', 'SecurityError'); };
      for (const n of ['localStorage']) Object.defineProperty(window, n, { get: f }); })()""",
    # nur Schlüssel außer kontor.layout/kontor.thema (M8) gesperrt: trennt die Tabs von Layout und Design
    "nur_tabs_gesperrt": """(() => { const frei = new Set(['kontor.layout', 'kontor.thema']);
      for (const m of ['getItem', 'setItem', 'removeItem']) { const o = Storage.prototype[m];
        Storage.prototype[m] = function (k, ...r) {
          if (!frei.has(String(k))) throw new DOMException('gesperrt', 'QuotaExceededError');
          return o.call(this, k, ...r); }; } })()""",
}


@pytest.mark.parametrize("inhalt", ["{kaputt", "[]", "null", '{"tabs": 7}', "nicht_verfuegbar", "nur_tabs_gesperrt"])
def test_ungueltiger_oder_fehlender_speicher(starte_server, neue_seite, inhalt):
    server = starte_server()
    d = m17.daten(server.api)
    k = d["k"]
    g = f"/konten/{k['giro']}"
    seite = neue_seite(server)
    if inhalt in GESPERRT:
        seite.add_init_script(GESPERRT[inhalt])
        # M28 (37.1, E-253): ohne Speicher erscheint der Pflichtdialog bei jedem Laden; er wird beantwortet
        oeffnen(seite, server, "/")
        m8.person_waehlen(seite)
        warte_geladen(seite, "uebersicht")
        navigiere(seite, "konten")
        seite.reload()
        expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
        m8.person_waehlen(seite)
        warte_geladen(seite, "konten")
        warte_tabs(seite, ["/konten"], "/konten")
    else:
        oeffnen(seite, server, "/", seitenname="uebersicht")
        navigiere(seite, "konten")
        warte_tabs(seite, ["/", "/konten"], "/konten")
        schluessel = seite.evaluate("() => Object.keys(localStorage)")
        # kontor.person (M28 37.1) ist kein Tab-Zustand (E-253)
        fremd = [x for x in schluessel if x not in ("kontor.layout", "kontor.thema", "kontor.person")]
        if not fremd:
            pytest.skip("Tabs liegen nicht im localStorage; ungültiger Inhalt dort nicht prüfbar (E-201)")
        seite.evaluate("([ks, v]) => ks.forEach(k => localStorage.setItem(k, v))", [fremd, inhalt])
        oeffnen(seite, server, g, seitenname="konto")
        warte_tabs(seite, [g], g, {})
    # sonst unverändert: Ansicht, Navigation und Tabs funktionieren
    oeffnen(seite, server, g)
    if inhalt in GESPERRT:
        m8.person_waehlen(seite)
    warte_geladen(seite, "konto")
    warte_liste(seite, _liste(server.api, k["giro"]))
    navigiere(seite, "uebersicht")
    assert pfade(seite)[-2:] == [g, "/"] and aktive(seite) == ["/"]


# ------------------------------------------------------------------ 1.4 Aktualität


def test_aenderung_in_anderem_tab_beim_naechsten_zeigen(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g, leb = f"/konten/{k['giro']}", f"/konten/{k['leb']}"
    tid(seite, "spalte-betrag").click()
    warte(seite, lambda: url(seite)[1].get("sortierung") == ["betrag"], text="sortierung=betrag")
    warte_liste(seite, _liste(api, k["giro"], sortierung="betrag"))
    zeile(seite, b["einfach"]).click(button="right")
    tid(seite, "km-gegenbuchung").click()
    m17.warte_konto(seite, k["leb"])
    warte_tabs(seite, [g, leb], leb)
    warte_liste(seite, _liste(api, k["leb"]))
    # Betrag im Kategorie-Tab ändern (23.2) und eine andere Buchung löschen (8.2)
    # M28 (37.8, E-254): Betrag über den Split-Dialog statt inline
    m8.stift(seite, b["einfach"], "splits")
    d = tid(seite, "split-dialog")
    expect(d).to_be_visible()
    for i, s_ in enumerate(api.buchung_lesen(b["einfach"])["splits"]):
        d.get_by_test_id(f"split-betrag-{i}").fill(m8.eingabe_betrag(1500 if s_["betrag"] > 0 else -1500))
    d.get_by_test_id("split-betrag-1").press("Tab")
    d.get_by_test_id("split-speichern").click()
    expect(d).to_be_hidden()
    m8.warte_bis(lambda: sorted(x["betrag"] for x in api.buchung_lesen(b["einfach"])["splits"]) == [-1500, 1500],
                 text="Betrag geändert")
    warte_liste(seite, _liste(api, k["leb"]))
    zeile(seite, b["zweite"]).click(button="right")
    tid(seite, "km-loeschen").click()
    tid(seite, "bestaetigen-ja").click()
    m8.warte_bis(lambda: api.get(f"/api/buchungen/{b['zweite']}").status_code == 404, text="gelöscht")
    warte_liste(seite, _liste(api, k["leb"]))
    # zurück zum Girokonto: Stand des Servers, Sortierung und Auswahl bleiben
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    warte_tabs(seite, [g, leb], g, {"sortierung": ["betrag"]})
    soll = api.seite(konto_id=k["giro"], sortierung="betrag", pro_seite=200)
    warte_liste(seite, [x["id"] for x in soll["eintraege"]])
    expect(zeile(seite, b["einfach"]).locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", "-1500")
    expect(tid(seite, "buchungsliste-summe")).to_have_attribute("data-betrag", str(soll["summe"]))
    expect(tid(seite, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", str(soll["gesamt"]))
    assert ausgewaehlt(seite) == {b["einfach"]}


# ------------------------------------------------------------------ 1.7 Tastatur und Zugänglichkeit


def test_tastatur_in_der_tab_leiste(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    navigiere(seite, "uebersicht")
    navigiere(seite, "konten")
    warte_tabs(seite, [g, "/", "/konten"], "/konten")
    assert m17.per_tab_erreichbar(seite) == {g: False, "/": False, "/konten": True}, \
        "nur der aktive Tab ist per Tabulatortaste erreichbar"
    m17.fokus_auf_tab(seite, "/konten")

    def taste(t, soll):
        seite.keyboard.press(t)
        warte(seite, lambda: m17.fokus_tab(seite) == soll, text=f"{t} → Fokus auf {soll}")

    taste("ArrowRight", g)          # umlaufend
    taste("ArrowRight", "/")
    taste("ArrowLeft", g)
    taste("ArrowLeft", "/konten")   # umlaufend
    taste("Home", g)
    taste("End", "/konten")
    assert aktive(seite) == ["/konten"], "Pfeiltasten bewegen nur den Fokus"
    taste("ArrowLeft", "/")
    seite.keyboard.press("Space")
    warte_tabs(seite, [g, "/", "/konten"], "/")
    warte_geladen(seite, "uebersicht")
    assert m17.per_tab_erreichbar(seite) == {g: False, "/": True, "/konten": False}
    m17.fokus_auf_tab(seite, "/")
    taste("Home", g)
    seite.keyboard.press("Enter")
    warte_tabs(seite, [g, "/", "/konten"], g)
    m17.warte_konto(seite, k["giro"])
    m17.fokus_auf_tab(seite, g)
    taste("End", "/konten")
    seite.keyboard.press("Delete")
    warte_tabs(seite, [g, "/"], g)


@pytest.mark.parametrize("taste", ["Strg", "Umschalt"])
def test_strg_und_umschaltklick_auf_tab_titel(starte_server, neue_seite, taste):
    """Definition 1.7: Der Klick bleibt dem Browser überlassen (Standardaktion nicht verhindert, der Browser
    öffnet den Link in einem neuen Fenster bzw. Browser-Tab), der Tab wechselt nicht. Ob headless Chromium
    tatsächlich ein Fenster öffnet, ist nicht zuverlässig beobachtbar; geprüft wird ``defaultPrevented`` (E-201)."""
    server, api, seite, k, b = _start(starte_server, neue_seite)
    g = f"/konten/{k['giro']}"
    seite.context.on("page", lambda p: p.close())
    navigiere(seite, "uebersicht")
    wechsle(seite, g)
    m17.warte_konto(seite, k["giro"])
    warte_tabs(seite, [g, "/"], g)
    warte_liste(seite, _liste(api, k["giro"]))
    seite.evaluate("""() => { window.__m17_klicks = [];
      window.addEventListener('click', e => {
        const t = e.target.closest && e.target.closest('[data-testid="tab-titel"]');
        if (t) setTimeout(() => window.__m17_klicks.push(e.defaultPrevented), 0); }); }""")
    titel(seite, "/").click(modifiers=[strg() if taste == "Strg" else "Shift"])
    klicks = warte(seite, lambda: seite.evaluate("() => window.__m17_klicks"), text="Klick auf tab-titel")
    assert klicks == [False], "Strg-/Umschaltklick: die Standardaktion des Browsers darf nicht verhindert werden"
    warte_tabs(seite, [g, "/"], g)
    m17.warte_konto(seite, k["giro"])
    expect(tid(seite, "seite-uebersicht")).to_have_count(0)


# ------------------------------------------------------------------ mobil


def test_mobil_viele_tabs_aktiver_sichtbar(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    ids = [api.konto(f"Gemeinschaftskonto Nummer {i}", "girokonto")["id"] for i in range(1, 9)]
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, "/", seitenname="uebersicht")
    for kid in ids:
        oeffne_konto(seite, kid)
        m17.warte_konto(seite, kid)

    def aktiver_im_blick():
        """M26 (36.2.3, E-248): senkrechte Liste; aktiver Tab vollständig innerhalb (oben/unten)."""
        return m17.leiste(seite).evaluate("""l => { const t = l.querySelector('[role="tab"][aria-selected="true"]');
          const a = l.getBoundingClientRect(), r = t.getBoundingClientRect();
          return r.height > 0 && r.top >= a.top - 1 && r.bottom <= a.bottom + 1; }""")

    def senkrecht():
        return m17.leiste(seite).evaluate("""l => { const t = [...l.querySelectorAll('[role="tab"]')]
          .map(e => e.getBoundingClientRect()).filter(r => r.height > 0);
          return t.length > 1 && t.every((r, i) => i === 0 || r.top >= t[i - 1].bottom - 1); }""")

    expect(m17.leiste(seite)).to_be_hidden()
    m17.tabs_aufklappen(seite)
    assert senkrecht(), "Tab-Liste ist mobil senkrecht"
    warte(seite, aktiver_im_blick, text="aktiver Tab im sichtbaren Bereich der Liste")
    assert seite.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), \
        "kein waagerechtes Scrollen der Seite (oberflaeche.md 16.2)"
    assert len(pfade(seite)) == 9
    m17.tabs_zuklappen(seite)
    seite.go_back()
    m17.warte_konto(seite, ids[-2])
    m17.tabs_aufklappen(seite)
    warte(seite, aktiver_im_blick, text="aktiver Tab nach Zurück im sichtbaren Bereich")
    titel(seite, "/").click()
    warte(seite, lambda: aktive(seite) == ["/"], text="Finanzübersicht aktiv")
    expect(tid(seite, "tabs-knopf")).to_have_attribute("aria-expanded", "false")
    expect(m17.leiste(seite)).to_be_hidden()
    m17.tabs_aufklappen(seite)
    warte(seite, aktiver_im_blick, text="erster Tab im sichtbaren Bereich")
