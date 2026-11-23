"""M8: Panels mit gespeichertem Layout (oberflaeche.md 15; K 5; E-141) und mobile Bedienung mit Gesten
(oberflaeche.md 16; K 5, K 14; E-145; T 19: lange Berührung und Wischgesten)."""

from __future__ import annotations

import json

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import (ausgewaehlt, lange_beruehrung, maus_ziehen, maus_ziehen_um, oeffnen, tid, tippen,
                             wischen, zeile)

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


@pytest.fixture
def daten(starte_server):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    return server, erw, ids


def _konto(seite, server, kid):
    oeffnen(seite, server, f"/konten/{kid}", seitenname="konto")
    reihen = m8.rest_liste(server.api, kid)
    m8.warte_liste(seite, reihen)
    return reihen


def _breite(seite, p) -> float:
    return tid(seite, f"panel-{p}").bounding_box()["width"]


def _layout(seite):
    roh = seite.evaluate("() => localStorage.getItem('kontor.layout')")
    return json.loads(roh) if roh else None


def _pruefe_trenner(seite, p):
    g = tid(seite, f"panel-groesse-{p}")
    expect(g).to_have_attribute("role", "separator")
    expect(g).to_have_attribute("aria-orientation", "vertical")
    expect(g).to_have_attribute("aria-valuemin", "160")
    expect(g).to_have_attribute("aria-valuemax", "600")
    wert = int(g.get_attribute("aria-valuenow"))
    assert abs(wert - _breite(seite, p)) <= 1, (wert, _breite(seite, p))
    return wert


# ------------------------------------------------------------------ Panels (15)
def test_vorgaben(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    for p, bereich, breite in (("kategorien", "links", 240), ("details", "rechts", 320)):
        panel = tid(seite, f"panel-{p}")
        expect(panel).to_have_attribute("data-bereich", bereich)
        expect(panel).to_have_attribute("data-eingeklappt", "nein")
        assert abs(_breite(seite, p) - breite) <= 1, (p, _breite(seite, p))
        assert _pruefe_trenner(seite, p) == breite
        expect(tid(seite, f"bereich-{bereich}").get_by_test_id(f"panel-{p}")).to_be_visible()
    liste = tid(seite, "buchungsliste").bounding_box()
    assert tid(seite, "panel-kategorien").bounding_box()["x"] < liste["x"] < tid(seite, "panel-details").bounding_box()["x"]


def test_groesse_aendern_und_speichern(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    maus_ziehen_um(seite, tid(seite, "panel-groesse-kategorien"), 100)
    m8.warte_bis(lambda: abs(_breite(seite, "kategorien") - 340) <= 2, text="linkes Panel 340 px")
    maus_ziehen_um(seite, tid(seite, "panel-groesse-details"), -80)        # rechts: nach links = breiter
    m8.warte_bis(lambda: abs(_breite(seite, "details") - 400) <= 2, text="rechtes Panel 400 px")
    maus_ziehen_um(seite, tid(seite, "panel-groesse-kategorien"), 1000)     # Obergrenze
    m8.warte_bis(lambda: abs(_breite(seite, "kategorien") - 600) <= 2)
    k, d = _pruefe_trenner(seite, "kategorien"), _pruefe_trenner(seite, "details")
    lay = _layout(seite)
    assert lay["version"] == 1
    assert lay["panels"]["kategorien"]["breite"] == k and lay["panels"]["details"]["breite"] == d
    seite.reload()
    m8.warte_geladen(seite, "konto")
    assert abs(_breite(seite, "kategorien") - k) <= 1 and abs(_breite(seite, "details") - d) <= 1


def test_groesse_per_tastatur(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    g = tid(seite, "panel-groesse-kategorien")
    g.focus()
    seite.keyboard.press("ArrowRight")
    seite.keyboard.press("ArrowRight")
    expect(g).to_have_attribute("aria-valuenow", "272")
    seite.keyboard.press("ArrowLeft")
    expect(g).to_have_attribute("aria-valuenow", "256")
    seite.keyboard.press("Home")
    expect(g).to_have_attribute("aria-valuenow", "160")
    seite.keyboard.press("ArrowLeft")
    expect(g).to_have_attribute("aria-valuenow", "160")
    seite.keyboard.press("End")
    expect(g).to_have_attribute("aria-valuenow", "600")
    rechts = tid(seite, "panel-groesse-details")
    rechts.focus()
    seite.keyboard.press("ArrowLeft")
    expect(rechts).to_have_attribute("aria-valuenow", "336")


def test_einklappen_und_speichern(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    knopf = tid(seite, "panel-einklappen-details")
    expect(knopf).to_have_attribute("aria-expanded", "true")
    knopf.click()
    expect(tid(seite, "panel-details")).to_have_attribute("data-eingeklappt", "ja")
    expect(knopf).to_have_attribute("aria-expanded", "false")
    assert _breite(seite, "details") <= 48
    assert _layout(seite)["panels"]["details"]["eingeklappt"] is True
    seite.reload()
    m8.warte_geladen(seite, "konto")
    expect(tid(seite, "panel-details")).to_have_attribute("data-eingeklappt", "ja")
    tid(seite, "panel-einklappen-details").click()
    expect(tid(seite, "panel-details")).to_have_attribute("data-eingeklappt", "nein")
    assert abs(_breite(seite, "details") - 320) <= 1, "Breite bleibt beim Einklappen erhalten"


def test_verschieben_per_drag_und_knopf(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])

    def ablage_rechts():
        box = tid(seite, "ablage-rechts").bounding_box()
        assert box and box["width"] >= 48, f"Ablage rechts während des Ziehens: {box}"
        return box["x"] + box["width"] / 2, box["y"] + min(box["height"] / 2, 200)

    maus_ziehen(seite, tid(seite, "panel-kopf-kategorien"), ablage_rechts)
    expect(tid(seite, "panel-kategorien")).to_have_attribute("data-bereich", "rechts")
    liste = tid(seite, "buchungsliste").bounding_box()
    kat, det = tid(seite, "panel-kategorien").bounding_box(), tid(seite, "panel-details").bounding_box()
    assert liste["x"] < kat["x"] < det["x"], "das verschobene Panel kommt nach innen, neben die Liste (15.2)"
    lay = _layout(seite)["panels"]
    assert lay["kategorien"]["bereich"] == "rechts" and lay["kategorien"]["position"] > lay["details"]["position"]
    seite.reload()
    m8.warte_geladen(seite, "konto")
    expect(tid(seite, "panel-kategorien")).to_have_attribute("data-bereich", "rechts")
    tid(seite, "panel-verschieben-details").click()
    expect(tid(seite, "panel-details")).to_have_attribute("data-bereich", "links")
    seite.reload()
    m8.warte_geladen(seite, "konto")
    expect(tid(seite, "panel-details")).to_have_attribute("data-bereich", "links")


def test_falsch_gespeichertes_layout_und_zuruecksetzen(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    _konto(seite, server, giro)
    seite.evaluate("() => localStorage.setItem('kontor.layout', '{kaputt')")
    seite.reload()
    m8.warte_geladen(seite, "konto")
    expect(tid(seite, "panel-kategorien")).to_have_attribute("data-bereich", "links")
    tid(seite, "panel-verschieben-kategorien").click()
    tid(seite, "panel-einklappen-details").click()
    oeffnen(seite, server, "/einstellungen", seitenname="einstellungen")
    tid(seite, "layout-zuruecksetzen").click()
    m8.warte_bis(lambda: _layout(seite) is None or _layout(seite)["panels"]["kategorien"]["bereich"] == "links")
    _konto(seite, server, giro)
    expect(tid(seite, "panel-kategorien")).to_have_attribute("data-bereich", "links")
    expect(tid(seite, "panel-details")).to_have_attribute("data-eingeklappt", "nein")


def test_mobil_kein_andocken_layout_bleibt(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    _konto(seite, server, giro)
    tid(seite, "panel-verschieben-kategorien").click()
    gespeichert = _layout(seite)
    seite.set_viewport_size({"width": 390, "height": 844})
    expect(tid(seite, "app")).to_have_attribute("data-layout", "mobil")
    expect(tid(seite, "panel-kategorien")).to_be_hidden()
    assert _layout(seite) == gespeichert


# ------------------------------------------------------------------ mobil (16)
def test_kompakte_liste_und_details(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    seite = neue_seite(server, "handy")
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    r = _konto(seite, server, giro)
    expect(tid(seite, "buchungsliste")).to_have_attribute("data-kompakt", "ja")
    for bid in r[:10]:
        z = zeile(seite, bid)
        assert z.bounding_box()["height"] >= 44 - 0.5
        for feld in ("datum", "betrag", "kategorie"):
            expect(z.locator(f'[data-feld="{feld}"]')).to_be_visible()
        b = api.buchung_lesen(bid)
        if b["empfaenger"]:
            expect(z.locator('[data-feld="empfaenger"]')).to_be_visible()
    tippen(seite, zeile(seite, r[0]).locator('[data-feld="betrag"]'))
    d = tid(seite, "panel-details")
    expect(d).to_be_visible()
    expect(d).to_have_attribute("role", "dialog")
    for s in api.buchung_lesen(r[0])["splits"]:
        expect(d.get_by_test_id(f"details-split-{s['id']}")).to_be_visible()
    tid(seite, "details-schliessen").click()
    expect(d).to_be_hidden()


def test_wischen_rechts_waehlt_aus(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server, "handy")
    r = _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    wischen(seite, zeile(seite, r[1]), "rechts")
    expect(zeile(seite, r[1])).to_have_attribute("aria-selected", "true")
    expect(tid(seite, "mehrfach-leiste")).to_be_visible()
    wischen(seite, zeile(seite, r[3]), "rechts")
    assert ausgewaehlt(seite) == {r[1], r[3]}
    # im Auswahlmodus schaltet Tippen um
    tippen(seite, zeile(seite, r[5]).locator('[data-feld="datum"]'))
    expect(zeile(seite, r[5])).to_have_attribute("aria-selected", "true")
    tippen(seite, zeile(seite, r[1]).locator('[data-feld="datum"]'))
    expect(zeile(seite, r[1])).to_have_attribute("aria-selected", "false")
    wischen(seite, zeile(seite, r[3]), "rechts")
    assert ausgewaehlt(seite) == {r[5]}
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", "1")
    leiste = tid(seite, "mehrfach-leiste").bounding_box()
    assert leiste["y"] + leiste["height"] >= seite.viewport_size["height"] - 2, "Leiste am unteren Rand"


def test_wischen_links_setzt_kategorie_und_rueckgaengig(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    seite = neue_seite(server, "handy")
    r = _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    mobil = ids.konto[erw["m8"]["konten"]["mobilitaet"]]
    # nach der bekannten Wahrheit kategorisierbare Zeilen, nicht nach Listenposition (W-007, datenmodell.md 3.2)
    (einzeln,) = m8.kategorisierbare(erw, ids, r, ohne=(mobil,))
    paar = m8.kategorisierbare(erw, ids, r, 2, ohne=(mobil,), ab=r.index(einzeln) + 1)
    vorher = api.buchung_lesen(einzeln)
    wischen(seite, zeile(seite, einzeln), "links")
    expect(tid(seite, "kategorie-auswahl")).to_be_visible()
    tippen(seite, tid(seite, f"kategorie-option-{mobil}"))
    m8.warte_bis(lambda: api.buchung_lesen(einzeln)["kategorie_id"] == mobil)
    expect(zeile(seite, einzeln).locator('[data-feld="kategorie"]')).to_have_attribute("data-kategorie-id",
                                                                                        str(mobil))
    # Auswahl per Wischen, dann Wischen nach links auf eine ausgewählte Zeile: wirkt auf die Auswahl
    wischen(seite, zeile(seite, paar[0]), "rechts")
    wischen(seite, zeile(seite, paar[1]), "rechts")
    wischen(seite, zeile(seite, paar[1]), "links")
    tippen(seite, tid(seite, f"kategorie-option-{mobil}"))
    m8.warte_bis(lambda: all(api.buchung_lesen(b)["kategorie_id"] == mobil for b in paar))
    # Rückgängig ohne Tastatur: Kopfzeile
    tippen(seite, tid(seite, "rueckgaengig-knopf"))
    m8.warte_bis(lambda: all(api.buchung_lesen(b)["kategorie_id"] != mobil for b in paar))
    assert api.buchung_lesen(einzeln)["kategorie_id"] == mobil
    assert vorher["kategorie_id"] != mobil


def test_mehrfachbearbeitung_mobil(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    seite = neue_seite(server, "handy")
    r = _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    for bid in r[:3]:
        wischen(seite, zeile(seite, bid), "rechts")
    tippen(seite, tid(seite, "mehrfach-tags"))
    tid(seite, "tag-auswahl-name").fill("Urlaub")
    tippen(seite, tid(seite, "tag-auswahl-hinzufuegen"))
    urlaub = ids.tag["kmy:G000001"]
    m8.warte_bis(lambda: all(urlaub in [t["id"] for t in api.buchung_lesen(b)["tags"]] for b in r[:3]))


def test_kategorie_verschieben_mobil(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    lange_beruehrung(seite, tid(seite, f"kategorie-{kino}"))
    tippen(seite, tid(seite, "km-konto-verschieben"))
    tippen(seite, tid(seite, "ziel-option-wurzel"))
    m8.warte_bis(lambda: next(k for k in api.konten() if k["id"] == kino)["eltern_id"] is None)
    expect(tid(seite, f"kategorie-{kino}")).to_have_attribute("aria-level", "1")


def test_kurzes_wischen_und_scrollen_ohne_wirkung(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server, "handy")
    r = _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    wischen(seite, zeile(seite, r[1]), "rechts", weite=40)        # unter 80 px: keine Geste
    expect(tid(seite, "kategorie-auswahl")).to_have_count(0)
    assert ausgewaehlt(seite) == set()
