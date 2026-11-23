"""M8: Split bearbeiten (oberflaeche.md 9.3; T 19) und Drag and Drop (oberflaeche.md 10; K 5; E-144)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import maus_ziehen, oeffnen, tid, zeile

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


# ------------------------------------------------------------------ Split (9.3)
def _split_oeffnen(seite, geraet, bid):
    if geraet == "handy":   # M26 (36.3, E-248): lange Berührung → mehrfach-mehr → km-splitten
        m8.auswahlmenue_mobil(seite, zeile(seite, bid))
    else:
        zeile(seite, bid).locator('[data-feld="betrag"]').click(button="right")
    tid(seite, "km-splitten").click()
    d = tid(seite, "split-dialog")
    expect(d).to_be_visible()
    expect(d).to_have_attribute("role", "dialog")
    expect(d).to_have_attribute("aria-modal", "true")
    return d


def test_split_bearbeiten(daten, neue_seite, geraet):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    lebensmittel = ids.konto[erw["m8"]["konten"]["lebensmittel"]]
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    seite = neue_seite(server, geraet)
    r = _konto(seite, server, giro)
    bid = next(b["id"] for b in api.alle_buchungen(konto_id=giro, kategorie_id=lebensmittel)
               if len(b["splits"]) == 2 and b["empfaenger"] and b["empfaenger"]["name"] == "Supermarkt Frischekorb")
    b = api.buchung_lesen(bid)
    giro_split = next(s for s in b["splits"] if s["konto_id"] == giro)
    gegen = next(s for s in b["splits"] if s["konto_id"] != giro)
    gesamt = gegen["betrag"]
    assert gesamt > 600
    d = _split_oeffnen(seite, geraet, bid)
    for i, s in enumerate(b["splits"]):
        expect(d.get_by_test_id(f"split-konto-{i}")).to_have_value(str(s["konto_id"]))
        assert m8.lies_betrag(d.get_by_test_id(f"split-betrag-{i}").input_value()) == s["betrag"]
    expect(d.get_by_test_id("split-rest")).to_have_attribute("data-betrag", "0")
    i_gegen = [s["id"] for s in b["splits"]].index(gegen["id"])
    teil = 500
    d.get_by_test_id(f"split-betrag-{i_gegen}").fill(m8.eingabe_betrag(gesamt - teil))
    d.get_by_test_id(f"split-betrag-{i_gegen}").press("Tab")
    expect(d.get_by_test_id("split-rest")).to_have_attribute("data-betrag", str(-teil))
    expect(d.get_by_test_id("split-speichern")).to_be_disabled()
    d.get_by_test_id("split-hinzufuegen").click()
    d.get_by_test_id("split-konto-2").select_option(str(haushalt))
    d.get_by_test_id("split-betrag-2").fill(m8.eingabe_betrag(teil))
    d.get_by_test_id("split-memo-2").fill("Spülmittel")
    d.get_by_test_id("split-betrag-2").press("Tab")
    expect(d.get_by_test_id("split-rest")).to_have_attribute("data-betrag", "0")
    expect(d.get_by_test_id("split-speichern")).to_be_enabled()
    a0 = m8.max_aenderung(api)
    d.get_by_test_id("split-speichern").click()
    expect(d).to_be_hidden()
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(api, a0))
    assert [a["aktion"] for a in neu] == ["splits_ersetzen"]
    splits = [(s["konto_id"], s["betrag"], s["memo"]) for s in api.buchung_lesen(bid)["splits"]]
    erwartet = [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]]
    erwartet[i_gegen] = (gegen["konto_id"], gesamt - teil, gegen["memo"])
    erwartet.append((haushalt, teil, "Spülmittel"))
    assert splits == erwartet
    assert giro_split["betrag"] == -gesamt
    k = zeile(seite, bid).locator('[data-feld="kategorie"]')
    expect(k).to_have_attribute("data-kategorie-id", "")


def test_split_abbrechen_und_entfernen(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    split = ids.buchung[erw["m8"]["split_buchung"]]
    seite = neue_seite(server)
    _konto(seite, server, giro)
    vorher = api.buchung_lesen(split)
    d = _split_oeffnen(seite, "desktop", split)
    expect(d.get_by_test_id("split-zeile-2")).to_be_visible()
    d.get_by_test_id("split-abbrechen").click()
    expect(d).to_be_hidden()
    assert api.buchung_lesen(split) == vorher
    # Split entfernen und Rest auf den verbleibenden Gegensplit legen: Zusammenführen (datenmodell.md 4)
    d = _split_oeffnen(seite, "desktop", split)
    b1, b2 = vorher["splits"][1]["betrag"], vorher["splits"][2]["betrag"]
    d.get_by_test_id("split-entfernen-2").click()
    expect(d.get_by_test_id("split-zeile-2")).to_have_count(0)
    expect(d.get_by_test_id("split-rest")).to_have_attribute("data-betrag", str(-b2))
    d.get_by_test_id("split-betrag-1").fill(m8.eingabe_betrag(b1 + b2))
    d.get_by_test_id("split-betrag-1").press("Tab")
    d.get_by_test_id("split-speichern").click()
    m8.warte_bis(lambda: len(api.buchung_lesen(split)["splits"]) == 2)
    assert [s["betrag"] for s in api.buchung_lesen(split)["splits"]] == [vorher["splits"][0]["betrag"], b1 + b2]


def test_split_ein_split_nicht_speicherbar(daten, neue_seite):
    """Mit nur einem Split ist Speichern deaktiviert (9.3)."""
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    split = ids.buchung[erw["m8"]["split_buchung"]]
    seite = neue_seite(server)
    _konto(seite, server, giro)
    d = _split_oeffnen(seite, "desktop", split)
    d.get_by_test_id("split-entfernen-2").click()
    d.get_by_test_id("split-entfernen-1").click()
    expect(d.get_by_test_id("split-speichern")).to_be_disabled()


# ------------------------------------------------------------------ Drag and Drop (10)
def test_buchung_auf_kategorie_ziehen(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    seite = neue_seite(server)
    r = _konto(seite, server, giro)
    # Zeilen nach der bekannten Wahrheit wählen, nicht nach Listenposition (W-007: Umbuchungen sind nicht
    # kategorisierbar, datenmodell.md 3.2)
    (einzeln,) = m8.kategorisierbare(erw, ids, r, ohne=(kino,))
    block = m8.kategorisierbare(erw, ids, r, 3, ohne=(haushalt,), ab=r.index(einzeln) + 1, folge=True)
    panel = tid(seite, "panel-kategorien")
    expect(panel).to_be_visible()
    ziel = panel.get_by_test_id(f"kategorie-{kino}")
    a0 = m8.max_aenderung(api)
    maus_ziehen(seite, zeile(seite, einzeln).locator('[data-feld="datum"]'), ziel)
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(api, a0))
    assert [a["aktion"] for a in neu] == ["kategorie_setzen"]
    assert api.buchung_lesen(einzeln)["kategorie_id"] == kino
    assert m8.ausgewaehlt(seite) == {einzeln}, "nicht ausgewählte Zeile wird vor dem Ziehen ausgewählt"
    # Auswahl ziehen
    zeile(seite, block[0]).locator('[data-feld="datum"]').click()
    zeile(seite, block[2]).locator('[data-feld="datum"]').click(modifiers=["Shift"])
    a1 = m8.max_aenderung(api)
    maus_ziehen(seite, zeile(seite, block[1]).locator('[data-feld="betrag"]'),
                panel.get_by_test_id(f"kategorie-{haushalt}"))
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(api, a1))
    assert [a["aktion"] for a in neu] == ["mehrfach_kategorie"]
    assert all(api.buchung_lesen(b)["kategorie_id"] == haushalt for b in block)
    expect(zeile(seite, block[1]).locator('[data-feld="kategorie"]')).to_have_attribute("data-kategorie-id",
                                                                                         str(haushalt))
    # Drag and Drop ist wie jede eigene Änderung rückgängig zu machen
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.keyboard.press("Control+z")
    m8.warte_bis(lambda: all(api.buchung_lesen(b)["kategorie_id"] != haushalt for b in block))


@pytest.mark.parametrize("ort", ["panel", "seite"])
def test_kategorien_umsortieren(daten, neue_seite, ort):
    server, erw, ids = daten
    api = server.api
    k = erw["m8"]["konten"]
    kino, wohnen, freizeit, kino_3d, gehalt = (ids.konto[k[x]] for x in ("kino", "wohnen", "freizeit", "kino_3d",
                                                                        "gehalt"))
    seite = neue_seite(server)
    if ort == "panel":
        _konto(seite, server, ids.konto[k["giro"]])
        baum = tid(seite, "panel-kategorien")
    else:
        oeffnen(seite, server, "/kategorien", seitenname="kategorien")
        baum = tid(seite, "kategorienbaum")
        expect(baum).to_have_attribute("role", "tree")

    def eltern(kid):
        return next(x for x in api.konten() if x["id"] == kid)["eltern_id"]

    def kopf(kid):
        # der Eintrag selbst ohne seine Unterkategorien: oberer Rand der Zeile
        return baum.get_by_test_id(f"kategorie-{kid}")

    def ziel_oben(kid):
        def f():
            box = kopf(kid).bounding_box()
            return box["x"] + min(40, box["width"] / 2), box["y"] + 8
        return f

    expect(kopf(kino)).to_have_attribute("aria-level", "2")
    maus_ziehen(seite, kopf(kino), ziel_oben(wohnen))
    m8.warte_bis(lambda: eltern(kino) == wohnen, text="Kino unter Wohnen")
    expect(kopf(wohnen).get_by_test_id(f"kategorie-{kino}")).to_be_visible()
    expect(kopf(kino)).to_have_attribute("aria-level", "2")
    expect(kopf(kino_3d)).to_have_attribute("aria-level", "3")
    assert eltern(kino_3d) == kino
    # auf die Gruppenüberschrift: Wurzelkategorie
    maus_ziehen(seite, kopf(kino), baum.get_by_test_id("kategorien-gruppe-aufwand"))
    m8.warte_bis(lambda: eltern(kino) is None, text="Kino als Wurzel")
    expect(kopf(kino)).to_have_attribute("aria-level", "1")
    # ungültig: auf den eigenen Nachfahren und in die andere Klasse
    a0 = m8.max_aenderung(api)
    maus_ziehen(seite, kopf(kino), ziel_oben(kino_3d))
    maus_ziehen(seite, kopf(kino), ziel_oben(gehalt))
    seite.wait_for_timeout(300)  # keine Anfrage erwartet: kurzer Puffer, danach Zustand prüfen
    assert eltern(kino) is None and eltern(kino_3d) == kino
    assert m8.max_aenderung(api) == a0
    assert eltern(freizeit) is None


def test_kein_ziehen_auf_dem_handy(daten, neue_seite):
    """Mobil kein Kategorien-Panel (16.3); Drag and Drop wird durch Wischen ersetzt (test_m8_mobil)."""
    server, erw, ids = daten
    seite = neue_seite(server, "handy")
    _konto(seite, server, ids.konto[erw["m8"]["konten"]["giro"]])
    expect(tid(seite, "panel-kategorien")).to_be_hidden()
