"""M8: Kontextmenüs per Rechtsklick, Tastatur und langer Berührung (oberflaeche.md 8, 9.4, 9.7; K 5)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import ausgewaehlt, lange_beruehrung, oeffnen, tid, zeile

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

BUCHUNG_EINTRAEGE = ["km-kategorie", "km-tags", "km-splitten", "km-dublette", "km-vorschlag-annehmen",
                     "km-vorschlag-ablehnen", "km-bearbeiten", "km-loeschen"]


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


def _zweck(seite, bid):
    return zeile(seite, bid).locator('[data-feld="verwendungszweck"]')


def _menue(seite):
    m = tid(seite, "kontextmenue")
    expect(m).to_be_visible()
    expect(m).to_have_attribute("role", "menu")
    return m


def _im_sichtbaren_bereich(seite, locator):
    box = locator.bounding_box()
    vp = seite.viewport_size
    assert box and box["x"] >= 0 and box["y"] >= 0, box
    assert box["x"] + box["width"] <= vp["width"] + 1 and box["y"] + box["height"] <= vp["height"] + 1, (box, vp)


@pytest.mark.kern
def test_rechtsklick_setzt_auswahl_und_zeigt_eintraege(konto):
    server, seite, erw, ids, giro, r = konto
    _zweck(seite, r[0]).click()
    _zweck(seite, r[1]).click(modifiers=["Control"])
    _zweck(seite, r[5]).click(button="right")           # außerhalb der Auswahl → Auswahl = {r[5]}
    m = _menue(seite)
    assert ausgewaehlt(seite) == {r[5]}
    for e in BUCHUNG_EINTRAEGE:
        expect(m.get_by_test_id(e)).to_have_attribute("role", "menuitem")
    expect(m.get_by_test_id("km-splitten")).not_to_have_attribute("aria-disabled", "true")
    expect(m.get_by_test_id("km-kategorie")).to_be_focused()
    expect(m.get_by_test_id("km-dublette")).to_have_attribute("aria-disabled", "true")  # kein Verdacht (E-143)
    _im_sichtbaren_bereich(seite, m)
    seite.keyboard.press("Escape")
    expect(m).to_be_hidden()
    expect(zeile(seite, r[5])).to_be_focused()


@pytest.mark.kern
def test_rechtsklick_in_der_auswahl_behaelt_sie(konto):
    server, seite, erw, ids, giro, r = konto
    _zweck(seite, r[2]).click()
    _zweck(seite, r[4]).click(modifiers=["Shift"])
    _zweck(seite, r[3]).click(button="right")
    m = _menue(seite)
    assert ausgewaehlt(seite) == {r[2], r[3], r[4]}
    expect(m.get_by_test_id("km-splitten")).to_have_attribute("aria-disabled", "true")   # nur bei genau einer
    expect(m.get_by_test_id("km-bearbeiten")).to_have_attribute("aria-disabled", "true")
    # deaktivierte Einträge lösen nichts aus
    a0 = m8.max_aenderung(server.api)
    m.get_by_test_id("km-splitten").click(force=True)
    expect(tid(seite, "split-dialog")).to_have_count(0)
    assert m8.max_aenderung(server.api) == a0


@pytest.mark.kern
def test_menue_tastatur_und_klick_ausserhalb(konto):
    server, seite, erw, ids, giro, r = konto
    _zweck(seite, r[0]).click(button="right")
    m = _menue(seite)
    seite.keyboard.press("ArrowDown")
    expect(m.get_by_test_id("km-tags")).to_be_focused()
    seite.keyboard.press("ArrowUp")
    seite.keyboard.press("ArrowUp")                     # umlaufend, deaktivierte werden übersprungen
    expect(m.get_by_test_id("km-loeschen")).to_be_focused()
    seite.mouse.click(5, seite.viewport_size["height"] - 5)
    expect(m).to_be_hidden()
    # Umschalt+F10 auf der fokussierten Zeile
    zeile(seite, r[1]).focus()
    seite.keyboard.press("Shift+F10")
    expect(_menue(seite)).to_be_visible()
    seite.keyboard.press("Escape")
    expect(tid(seite, "kontextmenue")).to_be_hidden()


@pytest.mark.kern
def test_kategorie_setzen_ueber_menue(konto):
    server, seite, erw, ids, giro, r = konto
    miete = ids.konto[erw["m8"]["konten"]["miete"]]
    wahl = m8.kategorisierbare(erw, ids, r, 2, ohne=(miete,), ab=6)   # bekannte Wahrheit (W-007)
    _zweck(seite, wahl[0]).click()
    _zweck(seite, wahl[1]).click(modifiers=["Control"])
    _zweck(seite, wahl[1]).click(button="right")
    a0 = m8.max_aenderung(server.api)
    _menue(seite).get_by_test_id("km-kategorie").click()
    expect(tid(seite, "kontextmenue")).to_be_hidden()
    tid(seite, "kategorie-auswahl-suche").fill("miete")
    tid(seite, f"kategorie-option-{miete}").click()
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(server.api, a0))
    assert [a["aktion"] for a in neu] == ["mehrfach_kategorie"]
    ein = {e["objekt_id"] for e in neu[0]["eintraege"] if e["objekt"] == "buchung"}
    assert set(wahl) >= ein and all(server.api.buchung_lesen(b)["kategorie_id"] == miete for b in wahl)


@pytest.mark.kern
def test_kategorie_setzen_umbuchung_meldet_ablehnung(konto):
    """W-007, E-151: „Kategorie setzen…“ ist auch bei einer Umbuchung aktiv (8.2); der Server lehnt mit 422
    `nicht_kategorisierbar` ab (datenmodell.md 3.2), die Oberfläche zeigt dessen `meldung` als Fehlermeldung
    (1 Nr. 8, 4.3) und weiter den Stand des Servers."""
    from tests.hilfen.api import fehlercode

    server, seite, erw, ids, giro, r = konto
    api = server.api
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    umb = m8.umbuchung_zeile(erw, ids, r)
    vorher = api.buchung_lesen(umb)
    zelle = zeile(seite, umb).locator('[data-feld="kategorie"]')
    expect(zelle).to_have_text("Umbuchung")
    a0 = m8.max_aenderung(api)
    _zweck(seite, umb).click(button="right")
    m = _menue(seite)
    expect(m.get_by_test_id("km-kategorie")).not_to_have_attribute("aria-disabled", "true")
    m.get_by_test_id("km-kategorie").click()
    tid(seite, f"kategorie-option-{kino}").click()
    fehler = tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="fehler"]')
    expect(fehler).to_be_visible()
    expect(fehler).to_have_attribute("role", "alert")
    assert m8.max_aenderung(api) == a0
    assert api.buchung_lesen(umb) == vorher
    expect(zelle).to_have_attribute("data-kategorie-id", "")
    expect(zelle).to_have_text("Umbuchung")
    # dieselbe Anfrage direkt: Ablehnung laut Vertrag, ihre meldung steht in der Fehlermeldung (4.3)
    antwort = api.put(f"/api/buchungen/{umb}/kategorie", json={"kategorie_id": kino}, erwartet=422)
    assert fehlercode(antwort) == "nicht_kategorisierbar"
    expect(fehler).to_contain_text(antwort.json()["fehler"]["meldung"])
    assert api.buchung_lesen(umb) == vorher


def test_dublette_markieren(starte_server, neue_seite):
    """km-dublette ist aktiv bei einer Buchung in einem offenen Verdacht und öffnet den Dialog (E-143)."""
    from tests.hilfen.pfade import KMY

    from tests.app.test_dubletten import lege_vorbestand_an
    from tests.hilfen.erwartung import lade

    server = starte_server()
    api = server.api
    ref = lege_vorbestand_an(api, lade("dubletten")["vorbestand"])
    giro_ref = next(k for k in lade("dubletten")["vorbestand"]["konten"] if k["art"] == "girokonto")["ref"]
    api.import_kmy(KMY / "dubletten.kmy", erwartet=200)
    offen = api.get("/api/dubletten", params={"status": "offen"}, erwartet=200).daten
    assert offen, "Der Dubletten-Datensatz erzeugt offene Verdachte"
    v = offen[0]
    konto_id = ref[giro_ref]["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{konto_id}", seitenname="konto")
    _zweck(seite, v["buchung_id"]).click(button="right")
    m = _menue(seite)
    expect(m.get_by_test_id("km-dublette")).not_to_have_attribute("aria-disabled", "true")
    m.get_by_test_id("km-dublette").click()
    d = tid(seite, "dublette-dialog")
    expect(d).to_be_visible()
    k = v["kandidat_ids"][0]
    expect(d.get_by_test_id(f"dublette-kandidat-{k}")).to_be_visible()
    d.get_by_test_id("dublette-keine").click()
    m8.warte_bis(lambda: api.get("/api/dubletten", erwartet=200).daten and next(
        x for x in api.get("/api/dubletten", erwartet=200).daten if x["id"] == v["id"])["status"] == "keine_dublette")


@pytest.mark.parametrize("ort", ["uebersicht", "kategorien"])
def test_konto_umbenennen_und_unterkonto(konto, ort):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    if ort == "uebersicht":
        oeffnen(seite, server, "/", seitenname="uebersicht")
        ziel_id = ids.konto[erw["m8"]["konten"]["tagesgeld"]]
        element = tid(seite, f"uebersicht-konto-{ziel_id}")
    else:
        oeffnen(seite, server, "/kategorien", seitenname="kategorien")
        ziel_id = ids.konto[erw["m8"]["konten"]["freizeit"]]
        element = tid(seite, f"kategorie-{ziel_id}")
    alt = next(k for k in api.konten() if k["id"] == ziel_id)
    element.click(button="right")
    _menue(seite).get_by_test_id("km-konto-umbenennen").click()
    feld = tid(seite, "umbenennen-eingabe")
    expect(feld).to_be_focused()
    feld.fill(alt["name"] + " Ä")
    feld.press("Enter")
    m8.warte_bis(lambda: next(k for k in api.konten() if k["id"] == ziel_id)["name"] == alt["name"] + " Ä")
    element.click(button="right")
    _menue(seite).get_by_test_id("km-konto-unterkonto").click()
    tid(seite, "konto-name").fill("Neues Unterkonto")
    tid(seite, "konto-speichern").click()
    neu = m8.warte_bis(lambda: next((k for k in api.konten() if k["name"] == "Neues Unterkonto"), None))
    assert (neu["eltern_id"], neu["art"]) == (ziel_id, alt["art"])


def test_konto_verschieben_ueber_menue(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    wohnen = ids.konto[erw["m8"]["konten"]["wohnen"]]
    kino_3d = ids.konto[erw["m8"]["konten"]["kino_3d"]]
    gehalt = ids.konto[erw["m8"]["konten"]["gehalt"]]
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    tid(seite, f"kategorie-{kino}").click(button="right")
    _menue(seite).get_by_test_id("km-konto-verschieben").click()
    d = tid(seite, "ziel-auswahl")
    expect(d).to_be_visible()
    expect(d.get_by_test_id("ziel-option-wurzel")).to_be_visible()
    expect(d.get_by_test_id(f"ziel-option-{kino}")).to_have_count(0)      # nicht sich selbst
    expect(d.get_by_test_id(f"ziel-option-{kino_3d}")).to_have_count(0)   # nicht der eigene Nachfahre
    expect(d.get_by_test_id(f"ziel-option-{gehalt}")).to_have_count(0)   # nicht andere Klasse
    d.get_by_test_id(f"ziel-option-{wohnen}").click()
    m8.warte_bis(lambda: next(k for k in api.konten() if k["id"] == kino)["eltern_id"] == wohnen)
    eintrag = tid(seite, f"kategorie-{wohnen}")
    expect(eintrag.get_by_test_id(f"kategorie-{kino}")).to_be_visible()   # im Baum unter Wohnen


def test_konto_loeschen_unbenutzt_und_benutzt(konto):
    server, seite, erw, ids, giro, r = konto
    api = server.api
    leer = api.konto("Leeres Testkonto", "aufwand")["id"]
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    tid(seite, f"kategorie-{leer}").click(button="right")
    _menue(seite).get_by_test_id("km-konto-loeschen").click()
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    tid(seite, "bestaetigen-ja").click()
    m8.warte_bis(lambda: api.get(f"/api/konten/{leer}").status_code == 404)
    # benutzte Kategorie: Dialog mit Zahlen aus dem Probelauf, ohne Vorauswahl
    strom = ids.konto[erw["m8"]["konten"]["strom"]]
    wohnen = ids.konto[erw["m8"]["konten"]["wohnen"]]
    anzahl = len(api.alle_buchungen(kategorie_id=strom))
    tid(seite, f"kategorie-{strom}").click(button="right")
    _menue(seite).get_by_test_id("km-konto-loeschen").click()
    d = tid(seite, "loeschen-dialog")
    expect(d).to_be_visible()
    expect(d.get_by_test_id("loeschen-anzahl-buchungen")).to_have_attribute("data-anzahl", str(anzahl))
    expect(d.get_by_test_id("loeschen-anzahl-unterkonten")).to_have_attribute("data-anzahl", "0")
    expect(d.get_by_test_id("loeschen-anzahl-regeln")).to_have_attribute("data-anzahl", "0")
    for w in ("loeschen", "elternkonto", "unkategorisiert"):
        expect(d.get_by_test_id(f"loeschen-wahl-{w}")).not_to_be_checked()
    expect(d.get_by_test_id("loeschen-ausfuehren")).to_be_disabled()
    d.get_by_test_id("loeschen-wahl-elternkonto").check()
    expect(d.get_by_test_id("loeschen-ausfuehren")).to_be_enabled()
    saldo_vorher = api.salden()[wohnen]["saldo_gesamt"]
    d.get_by_test_id("loeschen-ausfuehren").click()
    m8.warte_bis(lambda: api.get(f"/api/konten/{strom}").status_code == 404)
    assert api.salden()[wohnen]["saldo_gesamt"] == saldo_vorher  # loeschen.md 3.9
    letzte = m8.letzte_aenderung(api)
    assert letzte["aktion"] == "konto_loeschen_mit_buchungen"


def test_konto_loeschen_wurzel_ohne_elternkonto(konto):
    server, seite, erw, ids, giro, r = konto
    mobil = ids.konto[erw["m8"]["konten"]["mobilitaet"]]
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    tid(seite, f"kategorie-{mobil}").click(button="right")
    _menue(seite).get_by_test_id("km-konto-loeschen").click()
    d = tid(seite, "loeschen-dialog")
    expect(d.get_by_test_id("loeschen-wahl-elternkonto")).to_be_disabled()
    d.get_by_test_id("loeschen-abbrechen").click()
    expect(d).to_be_hidden()
    assert server.api.get(f"/api/konten/{mobil}").status_code == 200


def test_lange_beruehrung_oeffnet_menue(starte_server, neue_seite):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    r = m8.rest_liste(server.api, giro)
    m8.warte_liste(seite, r)
    # M26 (oberflaeche.md 36.3, E-248): lange Berührung wählt aus statt das Menü zu öffnen
    lange_beruehrung(seite, zeile(seite, r[3]))
    expect(tid(seite, "buchungsliste")).to_have_attribute("data-auswahlmodus", "ja")
    assert ausgewaehlt(seite) == {r[3]}
    expect(tid(seite, "auswahl-kopf")).to_be_visible()
    expect(tid(seite, "auswahl-kopf-anzahl")).to_have_text("1 ausgewählt")
    expect(tid(seite, "kontextmenue")).to_be_hidden()    # kein Menü (fehlt oder verborgen)
    expect(tid(seite, "panel-details")).to_be_hidden()   # kein Tippen nach der langen Berührung
    tid(seite, "mehrfach-mehr").click()
    m = _menue(seite)
    _im_sichtbaren_bereich(seite, m)
    for e in BUCHUNG_EINTRAEGE:
        expect(m.get_by_test_id(e)).to_be_attached()
