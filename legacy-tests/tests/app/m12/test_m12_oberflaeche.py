"""M12: Oberfläche – Filterleiste anfangs eingeklappt (oberflaeche.md 23.1), Inline-Bearbeitung von Status,
Empfänger und Betrag (23.2), Status-Auswahl, Bearbeiten-Dialog und Kontextmenü (23.3 bis 23.5).
Playwright wie M8 (E-139). Die Daten entstehen über REST; Erwartungen werden im Test berechnet.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import aenderungen_seit, eingabe_betrag, max_aenderung, oeffnen, strg, tid, warte_bis, \
    warte_liste, zeile

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

STATUS = ["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"]


def _daten(api) -> dict:
    k = {"giro": api.konto("Girokonto", "girokonto")["id"],
         "leb": api.konto("Lebensmittel", "aufwand")["id"],
         "cafe": api.konto("Café", "aufwand")["id"],
         "e1": api.empfaenger("Bäckerei Eins")["id"],
         "e2": api.empfaenger("Markt Zwei")["id"]}
    k["unter"] = api.konto("Rücklage", "girokonto", eltern_id=k["giro"])["id"]
    g = k["giro"]
    b = {
        "b1": api.buchung("2024-03-01", [(g, -1000, "G1"), (k["leb"], 1000, "K1")], status="importiert",
                          empfaenger_id=k["e1"], verwendungszweck="Brot")["id"],
        "b2": api.buchung("2024-03-02", [(k["leb"], 2000, "K2"), (g, -2000, "G2")], status="bestaetigt",
                          verwendungszweck="Einkauf")["id"],
        "b3": api.buchung("2024-03-03", [(g, -3000), (k["leb"], 3000)], status="bestaetigt",
                          empfaenger_id=k["e2"])["id"],
        "b4": api.buchung("2024-03-04", [(g, -3000), (k["leb"], 2000), (k["cafe"], 1000)], status="importiert")["id"],
        "b5": api.buchung("2024-03-05", [(k["unter"], -500), (k["cafe"], 500)], status="importiert")["id"],
    }
    api.patch(f"/api/buchungen/{b['b3']}", json={"status": "abgeglichen"}, erwartet=200)
    return {"k": k, "b": b}


def _start(starte_server, neue_seite, geraet="desktop", abfrage=""):
    server = starte_server()
    d = _daten(server.api)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, f"/konten/{d['k']['giro']}{abfrage}", seitenname="konto")
    return server, server.api, seite, d["k"], d["b"]


def _liste(api, konto_id, **params) -> list[int]:
    return m8.rest_liste(api, konto_id, **params)


def _status(api, bid) -> str:
    return api.buchung_lesen(bid)["status"]


def _editor(seite, bid, feld):
    """Ab M28 über den Stift der Einzelheiten statt Doppelklick (oberflaeche.md 37.8, E-254)."""
    return m8.stift(seite, bid, feld)


def _optionen(locator) -> list[str]:
    return locator.locator("option").evaluate_all("els => els.map(e => e.value)")


def _waehle(seite, *bids):
    zeile(seite, bids[0]).click()
    for bid in bids[1:]:
        zeile(seite, bid).click(modifiers=[strg()])
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", str(len(bids)))


# ------------------------------------------------------------------ 23.1 Filterleiste


@pytest.mark.kern
@pytest.mark.parametrize("geraet", ["desktop", "handy"])
def test_filterleiste_anfangs_eingeklappt(starte_server, neue_seite, geraet):
    server, api, seite, k, b = _start(starte_server, neue_seite, geraet)
    leiste, knopf, anzahl = tid(seite, "filter-leiste"), tid(seite, m8.FILTER_UMSCHALTER), tid(seite, "filter-anzahl")
    expect(leiste).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    kennung = leiste.get_attribute("id")
    assert kennung, "filter-leiste braucht eine id für aria-controls"
    expect(knopf).to_have_attribute("aria-controls", kennung)
    expect(anzahl).to_have_attribute("data-anzahl", "0")
    warte_liste(seite, _liste(api, k["giro"]))
    knopf.click()
    expect(leiste).to_be_visible()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    knopf.click()
    expect(leiste).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    # Filter setzen lässt die Leiste offen
    knopf.click()
    tid(seite, "filter-unterkonten").check()
    mit = _liste(api, k["giro"], unterkonten="true")
    assert b["b5"] in mit
    warte_liste(seite, mit)
    expect(leiste).to_be_visible()
    m8.filter_aktiv(seite)   # ab M30 nur noch „ungleich 0“ (E-271)
    # Neuladen: wieder eingeklappt, Filter aus der URL wirkt, Zahl am Umschalter sichtbar
    seite.reload()
    m8.warte_geladen(seite, "konto")
    expect(tid(seite, "filter-leiste")).to_be_hidden()
    expect(tid(seite, m8.FILTER_UMSCHALTER)).to_have_attribute("aria-expanded", "false")
    warte_liste(seite, mit)
    expect(tid(seite, "filter-anzahl")).to_be_visible()
    m8.filter_aktiv(seite)
    # Neuladen der Liste nach einer Änderung klappt nicht ein (mobil darf die Statusspalte fehlen, 16.3)
    tid(seite, m8.FILTER_UMSCHALTER).click()
    if geraet == "handy":
        return
    _editor(seite, b["b1"], "status").select_option("bestaetigt")
    warte_bis(lambda: _status(api, b["b1"]) == "bestaetigt", text="Status gesetzt")
    expect(zeile(seite, b["b1"])).to_have_attribute("data-status", "bestaetigt")
    expect(tid(seite, "filter-leiste")).to_be_visible()


def test_filterleiste_eingeklappt_mit_filtern_aus_der_url(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, abfrage="?status=importiert&von=2024-03-02")
    expect(tid(seite, "filter-leiste")).to_be_hidden()
    soll = _liste(api, k["giro"], status=["importiert"], von="2024-03-02")
    assert soll == [b["b4"]]
    warte_liste(seite, soll)
    m8.filter_aktiv(seite)
    # ab M30 stehen alte Adressparameter im Ausdruck statt in Einzelfeldern (oberflaeche.md 39.2, E-271)
    m8.warte_bis(lambda: "importiert" in m8.filter_ausdruck_wert(seite), text="Status im Ausdruck")
    m8.filter_aufklappen(seite)
    m8.filter_zuruecksetzen(seite)
    warte_liste(seite, _liste(api, k["giro"]))
    expect(tid(seite, "filter-leiste")).to_be_visible()


def test_filterleiste_nach_navigation_wieder_eingeklappt(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    tid(seite, m8.FILTER_UMSCHALTER).click()
    expect(tid(seite, "filter-leiste")).to_be_visible()
    m8.navigiere(seite, "uebersicht")
    tid(seite, f"uebersicht-konto-{k['giro']}").locator('[data-feld="name"]').click()
    m8.warte_geladen(seite, "konto")
    expect(tid(seite, "filter-leiste")).to_be_hidden()


# ------------------------------------------------------------------ 23.2 Inline: Status


@pytest.mark.kern
def test_status_inline(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vor = max_aenderung(api)
    # Esc bricht ab
    e = _editor(seite, b["b2"], "status")
    assert _optionen(e) == STATUS
    expect(e).to_have_value("bestaetigt")
    e.press("Escape")
    expect(tid(seite, "panel-details").get_by_test_id("inline-editor")).to_have_count(0)
    # Rückwärts: bestaetigt → importiert (über PATCH unzulässig, hier frei)
    _editor(seite, b["b2"], "status").select_option("importiert")
    warte_bis(lambda: _status(api, b["b2"]) == "importiert", text="Status importiert")
    expect(zeile(seite, b["b2"])).to_have_attribute("data-status", "importiert")
    expect(zeile(seite, b["b2"]).locator('[data-feld="status"]')).to_have_text("Importiert")
    (a,) = aenderungen_seit(api, vor)
    assert a["aktion"] == "mehrfach_aendern"
    assert [x["objekt_id"] for x in a["eintraege"]] == [b["b2"]]


@pytest.mark.kern
def test_status_inline_abgeglichen_mit_rueckfrage(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vor = max_aenderung(api)
    _editor(seite, b["b3"], "status").select_option("importiert")
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    tid(seite, "bestaetigen-nein").click()
    expect(tid(seite, "bestaetigen-dialog")).to_have_count(0)
    expect(zeile(seite, b["b3"])).to_have_attribute("data-status", "abgeglichen")
    assert _status(api, b["b3"]) == "abgeglichen" and aenderungen_seit(api, vor) == []
    _editor(seite, b["b3"], "status").select_option("bestaetigt")
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    tid(seite, "bestaetigen-ja").click()
    warte_bis(lambda: _status(api, b["b3"]) == "bestaetigt", text="entsperrt")
    expect(zeile(seite, b["b3"])).to_have_attribute("data-status", "bestaetigt")
    assert [a["aktion"] for a in aenderungen_seit(api, vor)] == ["mehrfach_aendern"]


# ------------------------------------------------------------------ 23.3/23.4 Mehrfach und Kontextmenü


@pytest.mark.kern
def test_mehrfach_status(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vor = max_aenderung(api)
    _waehle(seite, b["b1"], b["b4"], b["b2"])
    tid(seite, "mehrfach-status").click()
    dlg = tid(seite, "status-auswahl")
    expect(dlg).to_be_visible()
    expect(dlg).to_have_attribute("role", "dialog")
    knoepfe = dlg.locator('[data-testid^="status-waehlen-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    assert knoepfe == [f"status-waehlen-{s}" for s in STATUS]
    tid(seite, "status-waehlen-vorlaeufig").click()
    warte_bis(lambda: all(_status(api, x) == "vorlaeufig" for x in (b["b1"], b["b2"], b["b4"])), text="vorläufig")
    (a,) = aenderungen_seit(api, vor)
    assert a["aktion"] == "mehrfach_aendern"
    assert sorted(x["objekt_id"] for x in a["eintraege"]) == sorted([b["b1"], b["b2"], b["b4"]])
    assert _status(api, b["b3"]) == "abgeglichen"
    for x in (b["b1"], b["b2"], b["b4"]):
        expect(zeile(seite, x)).to_have_attribute("data-status", "vorlaeufig")


@pytest.mark.kern
def test_mehrfach_status_mit_abgeglichen_rueckfrage(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vor = max_aenderung(api)
    _waehle(seite, b["b2"], b["b3"])
    tid(seite, "mehrfach-status").click()
    tid(seite, "status-waehlen-importiert").click()
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    tid(seite, "bestaetigen-nein").click()
    expect(tid(seite, "bestaetigen-dialog")).to_have_count(0)
    assert aenderungen_seit(api, vor) == []
    tid(seite, "mehrfach-status").click()
    tid(seite, "status-waehlen-importiert").click()
    tid(seite, "bestaetigen-ja").click()
    warte_bis(lambda: _status(api, b["b2"]) == _status(api, b["b3"]) == "importiert", text="beide importiert")
    assert len(aenderungen_seit(api, vor)) == 1


@pytest.mark.kern
def test_kontextmenue_status(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["b1"]).click(button="right")
    menue = tid(seite, "kontextmenue")
    expect(menue.get_by_test_id("km-status")).not_to_have_attribute("aria-disabled", "true")
    expect(menue.get_by_test_id("km-mehrfach")).not_to_have_attribute("aria-disabled", "true")
    menue.get_by_test_id("km-status").click()
    tid(seite, "status-waehlen-abgeglichen").click()
    warte_bis(lambda: _status(api, b["b1"]) == "abgeglichen", text="abgeglichen")
    expect(tid(seite, "bestaetigen-dialog")).to_have_count(0)


# ------------------------------------------------------------------ 23.5 Bearbeiten-Dialog


def test_bearbeiten_dialog(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vorher = {x: api.buchung_lesen(b[x]) for x in ("b1", "b2")}
    vor = max_aenderung(api)
    _waehle(seite, b["b1"], b["b2"])
    tid(seite, "mehrfach-bearbeiten").click()
    dlg = tid(seite, "mehrfach-dialog")
    expect(dlg).to_be_visible()
    expect(tid(seite, "mehrfach-dialog-anzahl")).to_have_attribute("data-anzahl", "2")
    expect(tid(seite, "mehrfach-uebernehmen")).to_be_disabled()
    for f in ("status", "datum", "empfaenger", "verwendungszweck"):
        expect(tid(seite, f"mehrfach-an-{f}")).not_to_be_checked()
    tid(seite, "mehrfach-wert-verwendungszweck").fill("Sammelkorrektur")
    expect(tid(seite, "mehrfach-an-verwendungszweck")).to_be_checked()
    assert _optionen(tid(seite, "mehrfach-wert-empfaenger")) == ["", str(k["e1"]), str(k["e2"])]
    tid(seite, "mehrfach-wert-empfaenger").select_option(str(k["e2"]))
    expect(tid(seite, "mehrfach-an-empfaenger")).to_be_checked()
    expect(tid(seite, "mehrfach-entsperren")).to_be_hidden()
    tid(seite, "mehrfach-uebernehmen").click()
    expect(dlg).to_have_count(0)
    warte_bis(lambda: aenderungen_seit(api, vor), text="Änderung")
    e2 = {"id": k["e2"], "name": "Markt Zwei"}
    for x in ("b1", "b2"):
        assert api.buchung_lesen(b[x]) == {**vorher[x], "verwendungszweck": "Sammelkorrektur", "empfaenger": e2}
    (a,) = aenderungen_seit(api, vor)
    assert a["aktion"] == "mehrfach_aendern"


def test_bearbeiten_dialog_ohne_empfaenger_und_datum(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    _waehle(seite, b["b1"], b["b4"])
    tid(seite, "mehrfach-bearbeiten").click()
    tid(seite, "mehrfach-an-empfaenger").check()
    tid(seite, "mehrfach-wert-empfaenger").select_option("")
    tid(seite, "mehrfach-an-datum").check()
    expect(tid(seite, "mehrfach-uebernehmen")).to_be_disabled()   # Datum angehakt, aber leer
    tid(seite, "mehrfach-wert-datum").fill("2024-02-29")
    tid(seite, "mehrfach-uebernehmen").click()
    warte_bis(lambda: all(api.buchung_lesen(b[x])["datum"] == "2024-02-29" for x in ("b1", "b4")), text="Datum")
    assert all(api.buchung_lesen(b[x])["empfaenger"] is None for x in ("b1", "b4"))


def test_bearbeiten_dialog_entsperren(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    _waehle(seite, b["b1"], b["b3"])
    tid(seite, "mehrfach-bearbeiten").click()
    tid(seite, "mehrfach-an-status").check()
    tid(seite, "mehrfach-wert-status").select_option("abgeglichen")
    expect(tid(seite, "mehrfach-entsperren")).to_be_hidden()
    tid(seite, "mehrfach-wert-status").select_option("vorlaeufig")
    expect(tid(seite, "mehrfach-entsperren")).to_be_visible()
    expect(tid(seite, "mehrfach-uebernehmen")).to_be_disabled()
    tid(seite, "mehrfach-entsperren").check()
    tid(seite, "mehrfach-uebernehmen").click()
    warte_bis(lambda: _status(api, b["b1"]) == _status(api, b["b3"]) == "vorlaeufig", text="vorläufig")


def test_bearbeiten_dialog_fehler_bleibt_offen(starte_server, neue_seite):
    """Datum einer abgeglichenen Buchung → 409 buchung_gesperrt im Dialog; atomar, nichts geändert."""
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vorher = api.alle_buchungen()
    vor = max_aenderung(api)
    _waehle(seite, b["b2"], b["b3"])
    tid(seite, "mehrfach-bearbeiten").click()
    tid(seite, "mehrfach-wert-datum").fill("2024-01-01")
    tid(seite, "mehrfach-uebernehmen").click()
    expect(tid(seite, "dialog-fehler")).to_be_visible()
    expect(tid(seite, "mehrfach-dialog")).to_be_visible()
    assert api.alle_buchungen() == vorher and aenderungen_seit(api, vor) == []
    seite.keyboard.press("Escape")
    expect(tid(seite, "mehrfach-dialog")).to_have_count(0)


def test_kontextmenue_bearbeiten(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    _waehle(seite, b["b1"], b["b2"])
    zeile(seite, b["b2"]).click(button="right")
    tid(seite, "km-mehrfach").click()
    expect(tid(seite, "mehrfach-dialog-anzahl")).to_have_attribute("data-anzahl", "2")
    tid(seite, "mehrfach-abbrechen").click()
    expect(tid(seite, "mehrfach-dialog")).to_have_count(0)


# ------------------------------------------------------------------ 23.2 Inline: Empfänger und Betrag


def test_empfaenger_inline(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    e = _editor(seite, b["b1"], "empfaenger")
    assert _optionen(e) == ["", str(k["e1"]), str(k["e2"])]
    expect(e).to_have_value(str(k["e1"]))
    e.select_option(str(k["e2"]))
    warte_bis(lambda: (api.buchung_lesen(b["b1"])["empfaenger"] or {}).get("id") == k["e2"], text="Empfänger")
    expect(zeile(seite, b["b1"]).locator('[data-feld="empfaenger"]')).to_have_attribute(
        "data-empfaenger-id", str(k["e2"]))
    _editor(seite, b["b1"], "empfaenger").select_option("")
    warte_bis(lambda: api.buchung_lesen(b["b1"])["empfaenger"] is None, text="ohne Empfänger")
    # gesperrte Buchung: Stift deaktiviert (37.8), keine Änderung
    vorher = api.buchung_lesen(b["b3"])
    zeile(seite, b["b3"]).locator('[data-feld="betrag"]').click()
    expect(tid(seite, "panel-details").get_by_test_id("stift-empfaenger")).to_be_disabled()
    assert api.buchung_lesen(b["b3"]) == vorher


def test_betrag_inline(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    vorher = api.buchung_lesen(b["b2"])            # Splits in der Reihenfolge Kategorie, Giro
    vor = max_aenderung(api)
    # M28 (37.8, E-254): Betrag über den Split-Dialog (stift-splits)
    m8.stift(seite, b["b2"], "splits")
    d = tid(seite, "split-dialog")
    expect(d).to_be_visible()
    assert m8.lies_betrag(d.get_by_test_id("split-betrag-1").input_value()) == -2000
    d.get_by_test_id("split-abbrechen").click()
    expect(d).to_be_hidden()
    assert aenderungen_seit(api, vor) == []
    m8.stift(seite, b["b2"], "splits")
    d.get_by_test_id("split-betrag-0").fill(eingabe_betrag(12345))
    d.get_by_test_id("split-betrag-1").fill(eingabe_betrag(-12345))
    d.get_by_test_id("split-betrag-1").press("Tab")
    expect(d.get_by_test_id("split-rest")).to_have_attribute("data-betrag", "0")
    d.get_by_test_id("split-speichern").click()
    expect(d).to_be_hidden()
    warte_bis(lambda: api.buchung_lesen(b["b2"])["splits"][1]["betrag"] == -12345, text="Betrag")
    neu = api.buchung_lesen(b["b2"])
    assert [(s["konto_id"], s["betrag"], s["memo"]) for s in neu["splits"]] == [
        (k["leb"], 12345, "K2"), (k["giro"], -12345, "G2")]
    assert {f: neu[f] for f in ("datum", "status", "verwendungszweck", "empfaenger")} == {
        f: vorher[f] for f in ("datum", "status", "verwendungszweck", "empfaenger")}
    expect(zeile(seite, b["b2"]).locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", "-12345")
    (a,) = aenderungen_seit(api, vor)
    assert a["aktion"] == "splits_ersetzen"
    # drei Splits und gesperrte Buchung: kein Betrags-Editor
    for x in ("b4", "b3"):
        zelle = zeile(seite, b[x]).locator('[data-feld="betrag"]')
        zelle.dblclick()
        expect(zelle.get_by_test_id("inline-editor")).to_have_count(0)


def test_status_inline_mobil_ueber_kontextmenue(starte_server, neue_seite):
    """Mobil: Status über lange Berührung → mehrfach-mehr → km-status (16.4, 23.3; M26 36.3, E-248)."""
    server, api, seite, k, b = _start(starte_server, neue_seite, "handy")
    warte_liste(seite, _liste(api, k["giro"]))
    m8.auswahlmenue_mobil(seite, zeile(seite, b["b1"]))
    tid(seite, "km-status").click()
    tid(seite, "status-waehlen-bestaetigt").click()
    warte_bis(lambda: _status(api, b["b1"]) == "bestaetigt", text="bestätigt")


def test_url_ohne_filterleisten_zustand(starte_server, neue_seite):
    """E-172: Der Zustand der Leiste steht nicht in der URL."""
    server, api, seite, k, b = _start(starte_server, neue_seite)
    tid(seite, m8.FILTER_UMSCHALTER).click()
    assert parse_qs(urlsplit(seite.url).query) == {}
