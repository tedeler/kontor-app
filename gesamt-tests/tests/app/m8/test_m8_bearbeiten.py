"""M8: Inline-Bearbeitung, Rückgängig per Strg+Z und Wiederholen über das Änderungsprotokoll
(oberflaeche.md 7.6, 11, 13.9; K 5, K 14; E-142; T 3.6).

Ab M28 öffnet kein Doppelklick mehr einen Editor (oberflaeche.md 37.8): der Verwendungszweck mit F2, das Datum
über ``stift-datum`` der Einzelheiten, die Kategorie über die Kategorie-Auswahl (E-254)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import oeffnen, tid, zeile

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


@pytest.fixture
def konto(starte_server, neue_seite):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    reihen = m8.rest_liste(server.api, giro)
    m8.warte_liste(seite, reihen)
    return server, seite, erw, ids, giro, reihen


def _zelle(seite, bid, feld):
    return zeile(seite, bid).locator(f'[data-feld="{feld}"]')


def _editor(seite, bid, feld):
    e = zeile(seite, bid).get_by_test_id("inline-editor")
    expect(e).to_be_visible()
    expect(e).to_have_attribute("data-feld", feld)
    expect(e).to_be_focused()
    return e


def _zweck_bearbeiten(seite, bid, text, taste="Enter"):
    m8.zweck_editor(seite, bid)
    e = _editor(seite, bid, "verwendungszweck")
    e.fill(text)
    e.press(taste)
    return e


def _fokus_raus(seite):
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")


def _neue(server, a0):
    return m8.warte_bis(lambda: m8.aenderungen_seit(server.api, a0), text="neue Änderung")


# ------------------------------------------------------------------ Inline-Bearbeitung (7.6)
def test_verwendungszweck_mit_enter(konto):
    server, seite, erw, ids, giro, r = konto
    a0 = m8.max_aenderung(server.api)
    _zweck_bearbeiten(seite, r[0], "Geänderter Zweck <i>ä</i>")
    neu = _neue(server, a0)
    assert [(a["quelle"], a["aktion"]) for a in neu] == [("manuell", "buchung_aendern")]
    assert server.api.buchung_lesen(r[0])["verwendungszweck"] == "Geänderter Zweck <i>ä</i>"
    expect(_zelle(seite, r[0], "verwendungszweck")).to_have_text("Geänderter Zweck <i>ä</i>")
    expect(zeile(seite, r[0]).get_by_test_id("inline-editor")).to_have_count(0)
    expect(tid(seite, "rueckgaengig-knopf")).to_be_enabled()


def test_esc_bricht_ab_und_unveraendert_ohne_anfrage(konto):
    server, seite, erw, ids, giro, r = konto
    alt = server.api.buchung_lesen(r[1])["verwendungszweck"]
    a0 = m8.max_aenderung(server.api)
    _zweck_bearbeiten(seite, r[1], "verworfen", "Escape")
    expect(_zelle(seite, r[1], "verwendungszweck")).to_have_text(alt)
    m8.zweck_editor(seite, r[1])
    _editor(seite, r[1], "verwendungszweck").press("Enter")      # unverändert
    expect(zeile(seite, r[1]).get_by_test_id("inline-editor")).to_have_count(0)
    assert m8.max_aenderung(server.api) == a0
    assert server.api.buchung_lesen(r[1])["verwendungszweck"] == alt


def test_f2_und_verlassen_uebernimmt(konto):
    server, seite, erw, ids, giro, r = konto
    _zelle(seite, r[2], "betrag").click()
    seite.keyboard.press("F2")
    e = _editor(seite, r[2], "verwendungszweck")
    assert e.evaluate("el => el.selectionStart === 0 && el.selectionEnd === el.value.length"), "Text markiert"
    seite.keyboard.type("Per F2")
    tid(seite, "buchungsliste-anzahl").click()                    # Fokus verlässt den Editor
    m8.warte_bis(lambda: server.api.buchung_lesen(r[2])["verwendungszweck"] == "Per F2")


def test_datum_und_kategorie(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    (bid,) = m8.kategorisierbare(erw, ids, r, ohne=(kino,))   # nach der bekannten Wahrheit (W-007)
    e = m8.stift(seite, bid, "datum")
    expect(e).to_be_focused()
    expect(e).to_have_attribute("type", "date")
    e.fill("2024-02-29")
    e.press("Enter")
    m8.warte_bis(lambda: api.buchung_lesen(bid)["datum"] == "2024-02-29")
    expect(_zelle(seite, bid, "datum")).to_have_attribute("data-datum", "2024-02-29")
    expect(_zelle(seite, bid, "datum")).to_have_text("29.02.2024")
    a0 = m8.max_aenderung(api)
    _zelle(seite, bid, "kategorie").dblclick()
    expect(zeile(seite, bid).get_by_test_id("inline-editor")).to_have_count(0)   # 37.8: kein Editor
    _zelle(seite, bid, "kategorie").click(button="right")
    tid(seite, "km-kategorie").click()
    expect(tid(seite, "kategorie-auswahl")).to_be_visible()
    expect(tid(seite, f"kategorie-option-{kino}")).to_have_text("Freizeit › Kino")
    tid(seite, f"kategorie-option-{kino}").click()
    neu = _neue(server, a0)
    assert [a["aktion"] for a in neu] == ["kategorie_setzen"]
    assert api.buchung_lesen(bid)["kategorie_id"] == kino


def test_fehler_zeigt_stand_des_servers(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    alt = api.buchung_lesen(r[0])["verwendungszweck"]
    _zweck_bearbeiten(seite, r[0], "x" * 10001)                  # länger als erlaubt → 422
    fehler = tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="fehler"]')
    expect(fehler).to_be_visible()
    expect(_zelle(seite, r[0], "verwendungszweck")).to_have_text(alt)
    assert api.buchung_lesen(r[0])["verwendungszweck"] == alt


def test_gesperrte_buchung_bleibt_unveraendert(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    alt_b = api.buchung_lesen(r[-1])
    saldo = sum(s["betrag"] for x in api.alle_buchungen(konto_id=giro, bis=alt_b["datum"])
                for s in x["splits"] if s["konto_id"] == giro)
    api.post("/api/abstimmungen", json={"konto_id": giro, "stichtag": alt_b["datum"], "saldo": saldo}, erwartet=200)
    seite.reload()
    m8.warte_liste(seite, r)
    a0 = m8.max_aenderung(api)
    _zelle(seite, r[-1], "betrag").click()
    seite.keyboard.press("F2")
    editor = zeile(seite, r[-1]).get_by_test_id("inline-editor")
    if editor.count():
        editor.fill("darf nicht")
        editor.press("Enter")
        expect(tid(seite, "meldungen").locator('[data-art="fehler"]')).to_be_visible()
    assert api.buchung_lesen(r[-1])["verwendungszweck"] == alt_b["verwendungszweck"]
    assert m8.max_aenderung(api) == a0


# ------------------------------------------------------------------ Rückgängig und Wiederholen (11)
def test_strg_z_und_wiederholen(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    alt = api.buchung_lesen(r[0])
    a0 = m8.max_aenderung(api)
    _zweck_bearbeiten(seite, r[0], "Neu für Undo")
    bearbeitung = _neue(server, a0)[0]
    _fokus_raus(seite)
    seite.keyboard.press("Control+z")
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == alt["verwendungszweck"])
    u = m8.letzte_aenderung(api)
    assert (u["quelle"], u["rueckgaengig_von"]) == ("rueckgaengig", [bearbeitung["id"]])
    assert api.buchung_lesen(r[0]) == alt, "exakt der vorherige Zustand (T 3.6)"
    expect(_zelle(seite, r[0], "verwendungszweck")).to_have_text(alt["verwendungszweck"])
    expect(tid(seite, "wiederholen-knopf")).to_be_enabled()
    expect(tid(seite, "rueckgaengig-knopf")).to_be_disabled()
    seite.keyboard.press("Control+Shift+z")
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == "Neu für Undo")
    w = m8.letzte_aenderung(api)
    assert w["rueckgaengig_von"] == [u["id"]], "Wiederholen = Rückgängig der Rückgängig-Änderung (protokoll.md 6.3)"
    expect(_zelle(seite, r[0], "verwendungszweck")).to_have_text("Neu für Undo")
    seite.keyboard.press("Control+z")
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == alt["verwendungszweck"])
    seite.keyboard.press("Control+y")
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == "Neu für Undo")
    tid(seite, "rueckgaengig-knopf").click()
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == alt["verwendungszweck"])
    tid(seite, "wiederholen-knopf").click()
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == "Neu für Undo")


def test_mehrere_aenderungen_ein_schritt(konto):
    """Tag anlegen und zuordnen sind zwei Änderungen, aber ein Rückgängig (11, E-142)."""
    server, seite, erw, ids, giro, r = konto
    api = server.api
    vorher = {b: api.buchung_lesen(b) for b in r[:2]}
    tags_vorher = api.get("/api/tags", erwartet=200).daten
    m8.zeile(seite, r[0]).locator('[data-feld="betrag"]').click()
    m8.zeile(seite, r[1]).locator('[data-feld="betrag"]').click(modifiers=["Shift"])
    a0 = m8.max_aenderung(api)
    tid(seite, "mehrfach-tags").click()
    tid(seite, "tag-auswahl-name").fill("Einmalig")
    tid(seite, "tag-auswahl-hinzufuegen").click()
    neu = m8.warte_bis(lambda: len(m8.aenderungen_seit(api, a0)) == 2 and m8.aenderungen_seit(api, a0))
    _fokus_raus(seite)
    seite.keyboard.press("Control+z")
    m8.warte_bis(lambda: api.get("/api/tags", erwartet=200).daten == tags_vorher)
    u = m8.letzte_aenderung(api)
    assert u["rueckgaengig_von"] == sorted(a["id"] for a in neu)
    assert m8.aenderungen_seit(api, a0)[-1]["id"] == u["id"] and len(m8.aenderungen_seit(api, a0)) == 3
    assert {b: api.buchung_lesen(b) for b in r[:2]} == vorher


def test_strg_z_im_textfeld_und_leerer_stapel(konto):
    server, seite, erw, ids, giro, r = konto
    a0 = m8.max_aenderung(server.api)
    expect(tid(seite, "rueckgaengig-knopf")).to_be_disabled()
    _fokus_raus(seite)
    seite.keyboard.press("Control+z")
    expect(tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="hinweis"]')).to_be_visible()
    _zweck_bearbeiten(seite, r[3], "Bleibt bestehen")
    m8.warte_bis(lambda: m8.max_aenderung(server.api) > a0)
    a1 = m8.max_aenderung(server.api)
    tid(seite, "suche-feld").fill("abc")
    tid(seite, "suche-feld").press("Control+z")                    # Text-Undo des Browsers, kein Protokoll
    tid(seite, "befehlspalette-knopf").click()
    expect(tid(seite, "befehlspalette")).to_be_visible()
    seite.keyboard.press("Control+z")                              # bei offenem Dialog wirkungslos
    seite.keyboard.press("Escape")
    assert m8.max_aenderung(server.api) == a1
    assert server.api.buchung_lesen(r[3])["verwendungszweck"] == "Bleibt bestehen"


def test_konflikt_wird_gemeldet(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    _zweck_bearbeiten(seite, r[0], "Erste Fassung")
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == "Erste Fassung")
    api.patch(f"/api/buchungen/{r[0]}", json={"verwendungszweck": "Anderes Gerät"}, erwartet=200)
    a1 = m8.max_aenderung(api)
    _fokus_raus(seite)
    seite.keyboard.press("Control+z")
    fehler = tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="fehler"]')
    expect(fehler).to_be_visible()
    assert m8.max_aenderung(api) == a1
    assert api.buchung_lesen(r[0])["verwendungszweck"] == "Anderes Gerät"
    expect(tid(seite, "rueckgaengig-knopf")).to_be_disabled()          # Eintrag verworfen


def test_neue_aktion_leert_wiederholen(konto):
    server, seite, erw, ids, giro, r = konto
    _zweck_bearbeiten(seite, r[0], "A")
    m8.warte_bis(lambda: server.api.buchung_lesen(r[0])["verwendungszweck"] == "A")
    _fokus_raus(seite)
    seite.keyboard.press("Control+z")
    expect(tid(seite, "wiederholen-knopf")).to_be_enabled()
    m8.warte_bis(lambda: server.api.buchung_lesen(r[0])["verwendungszweck"] != "A")
    _zweck_bearbeiten(seite, r[1], "B")
    m8.warte_bis(lambda: server.api.buchung_lesen(r[1])["verwendungszweck"] == "B")
    expect(tid(seite, "wiederholen-knopf")).to_be_disabled()


def test_rueckgaengig_ueber_meldung(starte_server, neue_seite):
    """Ab M32 erscheint die Meldung mit „Rückgängig“ nur mit der Einstellung (oberflaeche.md 41.9, E-307)."""
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server, erfolgsmeldung=True)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    r = m8.rest_liste(server.api, giro)
    m8.warte_liste(seite, r)
    alt = server.api.buchung_lesen(r[4])["verwendungszweck"]
    _zweck_bearbeiten(seite, r[4], "Über Meldung zurück")
    m = tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="erfolg"]').last
    expect(m).to_be_visible()
    m.get_by_test_id("meldung-rueckgaengig").click()
    m8.warte_bis(lambda: server.api.buchung_lesen(r[4])["verwendungszweck"] == alt)


def test_protokollseite(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    alt = api.buchung_lesen(r[0])["verwendungszweck"]
    a0 = m8.max_aenderung(api)
    _zweck_bearbeiten(seite, r[0], "Fürs Protokoll")
    a = _neue(server, a0)[0]
    m8.navigiere(seite, "protokoll")
    z = tid(seite, f"aenderung-{a['id']}")
    expect(z).to_have_attribute("data-quelle", "manuell")
    expect(z).to_have_attribute("data-wirksam", "ja")
    # W-008: die ID ist genau der Teil nach dem Präfix "aenderung-" (nur Ziffern, kein Vorzeichen)
    ids_angezeigt = [int(x) for x in seite.locator(
        '[data-testid="protokoll-liste"] [data-testid^="aenderung-"][data-wirksam]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))"
        ".map(t => /^aenderung-([0-9]+)$/.exec(t)).filter(m => m).map(m => m[1])")]
    assert ids_angezeigt and all(x > 0 for x in ids_angezeigt)
    rest = [x["id"] for x in api.get("/api/aenderungen", params={"pro_seite": 50}, erwartet=200).daten["eintraege"]]
    assert ids_angezeigt == rest, "neueste zuerst, wie GET /api/aenderungen"
    tid(seite, f"aenderung-rueckgaengig-{a['id']}").click()
    m8.warte_bis(lambda: api.buchung_lesen(r[0])["verwendungszweck"] == alt)
    expect(tid(seite, f"aenderung-{a['id']}")).to_have_attribute("data-wirksam", "nein")
    expect(tid(seite, f"aenderung-rueckgaengig-{a['id']}")).to_have_count(0)


def test_konto_loeschen_rueckgaengig(konto):
    """Auch strukturelle Operationen (Konto mit Buchungen löschen) sind ein Strg+Z (loeschen.md 5)."""
    server, seite, erw, ids, giro, r = konto
    api = server.api
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    vorher = (api.konten(), api.alle_buchungen())
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    tid(seite, f"kategorie-{kino}").click(button="right")
    tid(seite, "km-konto-loeschen").click()
    d = tid(seite, "loeschen-dialog")
    d.get_by_test_id("loeschen-wahl-elternkonto").check()
    d.get_by_test_id("loeschen-ausfuehren").click()
    m8.warte_bis(lambda: api.get(f"/api/konten/{kino}").status_code == 404)
    _fokus_raus(seite)
    seite.keyboard.press("Control+z")
    m8.warte_bis(lambda: api.get(f"/api/konten/{kino}").status_code == 200)
    assert (api.konten(), api.alle_buchungen()) == vorher
    expect(tid(seite, f"kategorie-{kino}")).to_be_visible()
