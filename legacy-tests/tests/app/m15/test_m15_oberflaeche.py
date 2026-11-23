"""M15: Oberfläche – Rückgängig bis hierher, Löschen mit einer Anfrage, Verschieben-Dialog, Zuordnung unbekannter
Bankkonten, Kontoeinstellungen, gesperrter PIN-Dialog, Vorschläge je Zeile, Berichtsgrafiken (oberflaeche.md 25,
E-187). Playwright wie M8 (E-139); Daten über REST, Erwartungen im Test berechnet, gesendete Anfragen über
``m15.Mitschnitt``. Nicht kern (E-188).
"""

from __future__ import annotations

import json
import re

import pytest

from generator.iban import fiktive_iban
from tests.hilfen import m8
from tests.hilfen.m2 import SYNC_DATEN, SYNC_DATEN_PIN, lade_sync
from tests.hilfen.m3 import erfassen
from tests.hilfen.m8 import oeffnen, strg, tid, warte_bis, zeile
from tests.hilfen.m15 import Mitschnitt, prozent_text, text_normal
from tests.hilfen.pfade import KMY

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

GIRO_IBAN = fiktive_iban(7601)
ERFOLG = '[data-testid="meldung"][data-art="erfolg"]'
FEHLER = '[data-testid="meldung"][data-art="fehler"]'


def _meldung(seite, art=ERFOLG):
    return tid(seite, "meldungen").locator(art).last


def _daten(api) -> dict:
    k = {"giro": api.konto("Girokonto", "girokonto", iban=GIRO_IBAN)["id"],
         "spar": api.konto("Tagesgeld", "sparkonto")["id"],
         "karte": api.konto("Kreditkarte", "kreditkonto")["id"],
         "leb": api.konto("Lebensmittel", "aufwand")["id"]}
    k["b"] = [api.buchung(f"2024-03-0{i}", [(k["giro"], -100 * i, f"G{i}"), (k["leb"], 100 * i)],
                          verwendungszweck=f"Einkauf {i}")["id"] for i in range(1, 6)]
    return k


def _konto(starte_server, neue_seite, *, erfolgsmeldung: bool = False, **felder):
    server = starte_server(**felder)
    k = _daten(server.api)
    seite = neue_seite(server, erfolgsmeldung=erfolgsmeldung)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    m8.warte_liste(seite, m8.rest_liste(server.api, k["giro"]))
    return server, seite, mit, k


def _waehle(seite, *bids):
    zeile(seite, bids[0]).click()
    for bid in bids[1:]:
        zeile(seite, bid).click(modifiers=[strg()])
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", str(len(bids)))


def _werte(select) -> list[str]:
    return select.locator("option").evaluate_all("els => els.map(e => e.value)")


def _hat_klasse(locator, klasse: str) -> bool:
    return locator.evaluate(f"e => e.classList.contains({json.dumps(klasse)})")


# ------------------------------------------------------------------ 25.1 Rückgängig bis hierher


def test_protokoll_bis_hierher(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    ids = [api.tag(f"Tag {i}")["id"] for i in range(4)]
    alle = [a["id"] for a in api.get("/api/aenderungen", params={"pro_seite": 50}, erwartet=200).daten["eintraege"]]
    ziel = sorted(alle)[1]
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, "/protokoll", seitenname="protokoll")
    for a in alle:
        expect(tid(seite, f"aenderung-bis-{a}")).to_be_visible()
    tid(seite, f"aenderung-bis-{ziel}").hover()
    warte_bis(lambda: all(_hat_klasse(tid(seite, f"aenderung-{a}"), "bis-markiert") == (a >= ziel) for a in alle),
              text="bis-markiert genau an den Einträgen ≥ id")
    tid(seite, f"aenderung-bis-{ziel}").click()
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    tid(seite, "bestaetigen-nein").click()
    expect(tid(seite, "bestaetigen-dialog")).to_have_count(0)
    assert mit.schreibend() == []
    tid(seite, f"aenderung-bis-{ziel}").click()
    tid(seite, "bestaetigen-ja").click()
    u = warte_bis(lambda: (x := m8.letzte_aenderung(api)) and x["quelle"] == "rueckgaengig" and x, text="Rückgängig")
    assert mit.schreibend() == [("POST", "/api/aenderungen/rueckgaengig", {"bis_id": ziel})]
    assert u["rueckgaengig_von"] == [a for a in sorted(alle) if a >= ziel]
    expect(_meldung(seite)).to_contain_text(str(len(u["rueckgaengig_von"])))
    expect(tid(seite, f"aenderung-{u['id']}")).to_be_visible()
    expect(tid(seite, f"aenderung-{ziel}")).to_have_attribute("data-wirksam", "nein")
    assert len(api.get("/api/tags", erwartet=200).daten) == len(ids) - (len(u["rueckgaengig_von"]))


def test_protokoll_bis_fehler_als_meldung(starte_server, neue_seite):
    server = starte_server()
    server.api.tag("Eins")
    a = m8.max_aenderung(server.api)
    seite = neue_seite(server)
    meldung = "Das Objekt wurde inzwischen verändert (Test)"
    seite.route("**/api/aenderungen/rueckgaengig", lambda route: route.fulfill(
        status=409, content_type="application/json", headers={"X-Kontor-Modus": "mock"},
        body=json.dumps({"fehler": {"code": "rueckgaengig_konflikt", "meldung": meldung, "details": None}})))
    oeffnen(seite, server, "/protokoll", seitenname="protokoll")
    tid(seite, f"aenderung-bis-{a}").click()
    tid(seite, "bestaetigen-ja").click()
    expect(_meldung(seite, FEHLER)).to_contain_text(meldung)
    assert m8.max_aenderung(server.api) == a


# ------------------------------------------------------------------ 25.2 Löschen


def _meldungen_schliessen(seite):
    knoepfe = tid(seite, "meldungen").get_by_test_id("meldung-schliessen")
    while knoepfe.count():
        knoepfe.first.click()
    expect(tid(seite, "meldungen").locator('[data-testid="meldung"]')).to_have_count(0)


def _verschieben_menue(seite, bid):
    """M28 (37.9, E-254): „Auf anderes Konto verschieben…“ nur mit gehaltener Alt-Taste. Offene Meldungen liegen
    über dem längeren Menü (M28 13 G, O3) und werden vorher geschlossen."""
    _meldungen_schliessen(seite)
    zeile(seite, bid).click(button="right", modifiers=["Alt"])
    expect(tid(seite, "km-verschieben")).to_be_visible()
    tid(seite, "km-verschieben").click()


def test_mehrfach_loeschen_eine_anfrage_und_ein_rueckgaengig(starte_server, neue_seite):
    server, seite, mit, k = _konto(starte_server, neue_seite)
    api = server.api
    wahl = [k["b"][3], k["b"][0], k["b"][2]]
    a0 = m8.max_aenderung(api)
    _waehle(seite, *wahl)
    tid(seite, "mehrfach-loeschen").click()
    tid(seite, "bestaetigen-ja").click()
    warte_bis(lambda: all(api.get(f"/api/buchungen/{b}").status_code == 404 for b in wahl), text="gelöscht")
    assert mit.schreibend() == [("POST", "/api/buchungen/mehrfach/loeschen", {"buchung_ids": sorted(wahl)})]
    neu = m8.aenderungen_seit(api, a0)
    assert [x["aktion"] for x in neu] == ["mehrfach_loeschen"]
    m8.warte_liste(seite, m8.rest_liste(api, k["giro"]))
    mit.leeren()
    tid(seite, "rueckgaengig-knopf").click()
    warte_bis(lambda: all(api.get(f"/api/buchungen/{b}").status_code == 200 for b in wahl), text="wiederhergestellt")
    assert mit.schreibend() == [("POST", f"/api/aenderungen/{neu[0]['id']}/rueckgaengig", None)]
    # eine Buchung über das Kontextmenü: weiter DELETE
    m8.warte_liste(seite, m8.rest_liste(api, k["giro"]))
    mit.leeren()
    _meldungen_schliessen(seite)   # M28 13 G (E-254): Meldungen liegen über dem längeren Menü
    zeile(seite, k["b"][4]).click(button="right")
    tid(seite, "km-loeschen").click()
    tid(seite, "bestaetigen-ja").click()
    warte_bis(lambda: api.get(f"/api/buchungen/{k['b'][4]}").status_code == 404, text="einzeln gelöscht")
    assert mit.schreibend() == [("DELETE", f"/api/buchungen/{k['b'][4]}", None)]


def test_mehrfach_loeschen_gesperrt_meldet_fehler(starte_server, neue_seite):
    server, seite, mit, k = _konto(starte_server, neue_seite)
    api = server.api
    api.patch(f"/api/buchungen/{k['b'][1]}", json={"status": "abgeglichen"}, erwartet=200)
    seite.reload()
    m8.warte_liste(seite, m8.rest_liste(api, k["giro"]))
    a0 = m8.max_aenderung(api)
    _waehle(seite, k["b"][0], k["b"][1])
    tid(seite, "mehrfach-loeschen").click()
    tid(seite, "bestaetigen-ja").click()
    expect(_meldung(seite, FEHLER)).to_be_visible()
    assert m8.max_aenderung(api) == a0
    assert all(api.get(f"/api/buchungen/{b}").status_code == 200 for b in k["b"])


# ------------------------------------------------------------------ 25.3 Verschieben


def test_verschieben_auswahl(starte_server, neue_seite):
    server, seite, mit, k = _konto(starte_server, neue_seite, erfolgsmeldung=True)   # Meldung ab M32: E-307
    api = server.api
    wahl = [k["b"][2], k["b"][0]]
    _waehle(seite, *wahl)
    expect(tid(seite, "mehrfach-verschieben")).to_be_hidden()   # Desktop: nur über das Menü mit Alt
    _verschieben_menue(seite, wahl[0])
    d = tid(seite, "verschieben-dialog")
    expect(d).to_be_visible()
    ziel = tid(seite, "verschieben-ziel")
    assert _werte(ziel) == ["", str(k["karte"]), str(k["spar"])], "andere Bestandskonten in Baumfolge (Name)"
    expect(ziel).to_have_value("")
    expect(tid(seite, "verschieben-ok")).to_be_disabled()
    ziel.select_option(str(k["spar"]))
    tid(seite, "verschieben-auswahl").check()
    expect(tid(seite, "verschieben-ok")).to_be_enabled()
    tid(seite, "verschieben-ok").click()
    expect(d).to_have_count(0)
    expect(_meldung(seite)).to_be_visible()
    assert mit.schreibend() == [("POST", "/api/buchungen/mehrfach/verschieben",
                                 {"von_konto_id": k["giro"], "nach_konto_id": k["spar"], "buchung_ids": sorted(wahl)})]
    for b in wahl:
        assert k["spar"] in [s["konto_id"] for s in api.buchung_lesen(b)["splits"]]
    m8.warte_liste(seite, m8.rest_liste(api, k["giro"]))
    # ohne Alt kein Eintrag; mit Alt derselbe Dialog
    zeile(seite, k["b"][1]).click(button="right")
    expect(tid(seite, "kontextmenue")).to_be_visible()
    expect(tid(seite, "km-verschieben")).to_have_count(0)
    seite.keyboard.press("Escape")
    _verschieben_menue(seite, k["b"][1])
    expect(tid(seite, "verschieben-dialog")).to_be_visible()
    seite.keyboard.press("Escape")
    expect(tid(seite, "verschieben-dialog")).to_have_count(0)


def test_verschieben_herkunft_und_kategorieansicht(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    (imp,) = api.get("/api/importe", erwartet=200).daten
    giro = next(x["id"] for x in api.konten() if x["extern_id"] == "kmy:A000001")
    leb = next(x["id"] for x in api.konten() if x["extern_id"] == "kmy:A000002")
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    expect(tid(seite, "konto-verschieben")).to_have_count(0)   # M28 (37.9, E-254): Knopf entfällt
    m8.warte_liste(seite, m8.rest_liste(api, giro))
    _verschieben_menue(seite, m8.rest_liste(api, giro)[0])
    expect(tid(seite, "verschieben-dialog")).to_be_visible()
    wahl = tid(seite, "verschieben-herkunft-wahl")
    assert [w for w in _werte(wahl) if w] == [f"import:{imp['id']}"]
    tid(seite, "verschieben-ziel").select_option(str(spar))
    tid(seite, "verschieben-herkunft").check()
    wahl.select_option(f"import:{imp['id']}")
    tid(seite, "verschieben-ok").click()
    expect(tid(seite, "verschieben-dialog")).to_have_count(0)
    assert mit.schreibend() == [("POST", "/api/buchungen/mehrfach/verschieben",
                                 {"von_konto_id": giro, "nach_konto_id": spar, "gruppe": f"import:{imp['id']}"})]
    assert api.get(f"/api/konten/{giro}/herkunft", erwartet=200).daten == []
    # Kategorie: kein Verschieben, auch nicht mit Alt
    oeffnen(seite, server, f"/konten/{leb}", seitenname="konto")
    expect(tid(seite, "konto-verschieben")).to_have_count(0)
    rl = m8.rest_liste(api, leb)
    m8.warte_liste(seite, rl)
    zeile(seite, rl[0]).click(button="right", modifiers=["Alt"])
    expect(tid(seite, "kontextmenue")).to_be_visible()
    expect(tid(seite, "km-verschieben")).to_have_count(0)
    seite.keyboard.press("Escape")
    # ohne Herkunft: Auswahl der Herkunft inaktiv (Konto mit einer manuellen Buchung, ohne Import)
    neu = api.konto("Leer", "girokonto")["id"]
    nb = api.buchung("2024-01-05", [(neu, -100), (leb, 100)])["id"]
    oeffnen(seite, server, f"/konten/{neu}", seitenname="konto")
    m8.warte_liste(seite, [nb])
    _verschieben_menue(seite, nb)
    expect(tid(seite, "verschieben-herkunft-wahl")).to_be_disabled()


# ------------------------------------------------------------------ 25.4 Zuordnung und Kontoeinstellungen


def _ibans():
    daten, erw = lade_sync()
    return daten, erw["ibans"]


def test_zuordnung_nach_lauf_und_folgelauf(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN, sync_konten_anlegen=False)
    api = server.api
    _, i = _ibans()
    giro = api.konto("Girokonto", "girokonto")["id"]
    kasse = api.konto("Haushaltskasse", "sparkonto")["id"]
    api.konto("Fremdkonto", "girokonto", iban=fiktive_iban(7602))
    api.konto("Essen", "aufwand")
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, "sync-starten").click()
    d = tid(seite, "zuordnung-dialog")
    expect(d).to_be_visible()
    warte_bis(lambda: i["giro"] in d.inner_text().replace(" ", ""), text="Dialog für das Girokonto")
    expect(d).to_contain_text("Girokonto")
    expect(tid(seite, "zuordnung-vorhanden")).to_be_checked()
    assert sorted(w for w in _werte(tid(seite, "zuordnung-konto")) if w) == sorted([str(giro), str(kasse)])
    expect(tid(seite, "zuordnung-konto")).to_have_value(str(giro))
    tid(seite, "zuordnung-ok").click()
    warte_bis(lambda: i["kredit"] in d.inner_text().replace(" ", ""), text="Dialog für die Kreditkarte")
    zweite_optionen = [w for w in _werte(tid(seite, "zuordnung-konto")) if w]   # geprüft am Ende
    tid(seite, "zuordnung-spaeter").click()
    warte_bis(lambda: i["spar"] in d.inner_text().replace(" ", ""), text="Dialog für das Tagesgeld")
    tid(seite, "zuordnung-neu").check()
    expect(tid(seite, "zuordnung-name")).to_have_value("Tagesgeld")
    expect(tid(seite, "zuordnung-art")).to_have_value("sparkonto")
    tid(seite, "zuordnung-ok").click()
    # Folgelauf: die Kreditkarte wird erneut gefragt, Esc bricht ab
    warte_bis(lambda: len(api.get("/api/sync/laeufe", erwartet=200).daten) == 2, text="Folgelauf")
    expect(tid(seite, "zuordnung-dialog")).to_be_visible()
    warte_bis(lambda: i["kredit"] in tid(seite, "zuordnung-dialog").inner_text().replace(" ", ""), text="erneut")
    seite.keyboard.press("Escape")
    expect(tid(seite, "zuordnung-dialog")).to_have_count(0)
    schreibend = mit.schreibend()
    assert ("PATCH", f"/api/konten/{giro}", {"iban": i["giro"]}) in schreibend
    assert ("POST", "/api/konten", {"name": "Tagesgeld", "art": "sparkonto", "iban": i["spar"]}) in schreibend
    assert [a for a in schreibend if a[1] == "/api/sync"] == [("POST", "/api/sync", {})] * 2
    laeufe = api.get("/api/sync/laeufe", erwartet=200).daten
    assert len(laeufe) == 2
    assert sorted(x["iban"] for x in laeufe[-1]["konten"]) == sorted([i["giro"], i["spar"]])
    assert zweite_optionen == [str(kasse)], "zweiter Dialog: nur Bestandskonten ohne IBAN (Girokonto trägt jetzt eine)"


def test_sync_seite_nicht_zugeordnet(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN, sync_konten_anlegen=False)
    api = server.api
    _, i = _ibans()
    api.post("/api/sync", json={}, erwartet=200)
    api.konto("Giro", "girokonto", iban=i["giro"])
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, "/sync", seitenname="sync")
    bereich = tid(seite, "sync-nicht-zugeordnet")
    expect(bereich.get_by_test_id(f"nicht-zugeordnet-{i['kredit']}")).to_be_visible()
    expect(bereich.get_by_test_id(f"nicht-zugeordnet-{i['spar']}")).to_be_visible()
    expect(tid(seite, f"nicht-zugeordnet-{i['giro']}")).to_have_count(0)
    tid(seite, f"zuordnen-{i['kredit']}").click()
    d = tid(seite, "zuordnung-dialog")
    expect(d).to_be_visible()
    assert i["kredit"] in d.inner_text().replace(" ", "")
    tid(seite, "zuordnung-neu").check()
    expect(tid(seite, "zuordnung-art")).to_have_value("kreditkonto")
    tid(seite, "zuordnung-ok").click()
    warte_bis(lambda: any(x["iban"] == i["kredit"] for x in api.konten()), text="Konto angelegt")
    assert ("POST", "/api/konten", {"name": "Kreditkarte", "art": "kreditkonto", "iban": i["kredit"]}) in \
        mit.schreibend()
    expect(tid(seite, f"nicht-zugeordnet-{i['kredit']}")).to_have_count(0)


def test_kontoeinstellungen(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN, sync_konten_anlegen=False)
    api = server.api
    _, i = _ibans()
    api.post("/api/sync", json={}, erwartet=200)
    a = api.konto("Giro alt", "girokonto")
    api.konto("Spar", "sparkonto", iban=i["spar"])
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, f"/konten/{a['id']}", seitenname="konto")

    def oeffne():
        tid(seite, "konto-einstellungen-oeffnen").click()
        d = tid(seite, "konto-einstellungen")
        expect(d).to_be_visible()
        return d
    d = oeffne()
    expect(tid(seite, "einstellungen-name")).to_have_value("Giro alt")
    sel = tid(seite, "einstellungen-sync")
    werte = _werte(sel)
    assert werte[0] == "" and "*" in werte and {i["giro"], i["kredit"], i["spar"]} <= set(werte)
    expect(sel).to_have_value("")
    expect(sel.locator(f'option[value="{i["spar"]}"]')).to_be_disabled()
    expect(sel.locator(f'option[value="{i["giro"]}"]')).to_be_enabled()
    expect(tid(seite, "einstellungen-iban")).to_be_hidden()
    mit.leeren()
    tid(seite, "einstellungen-speichern").click()
    expect(d).to_have_count(0)
    assert mit.schreibend() == [], "ohne Änderung keine Anfrage"
    oeffne()
    tid(seite, "einstellungen-name").fill("Giro neu")
    tid(seite, "einstellungen-sync").select_option(i["giro"])
    tid(seite, "einstellungen-speichern").click()
    expect(tid(seite, "konto-einstellungen")).to_have_count(0)
    assert mit.schreibend() == [("PATCH", f"/api/konten/{a['id']}", {"name": "Giro neu", "iban": i["giro"]})]
    assert api.get(f"/api/konten/{a['id']}", erwartet=200).daten == {**a, "name": "Giro neu", "iban": i["giro"]}
    # Kontomenü der Übersicht; andere IBAN mit Fehler, dann nur die Notiz
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, f"uebersicht-konto-{a['id']}").click(button="right")
    tid(seite, "km-konto-einstellungen").click()
    expect(tid(seite, "konto-einstellungen")).to_be_visible()
    tid(seite, "einstellungen-sync").select_option("*")
    expect(tid(seite, "einstellungen-iban")).to_be_visible()
    tid(seite, "einstellungen-iban").fill("DE00 1234")
    tid(seite, "einstellungen-speichern").click()
    expect(tid(seite, "konto-einstellungen").get_by_test_id("dialog-fehler")).to_be_visible()
    expect(tid(seite, "konto-einstellungen")).to_be_visible()
    seite.keyboard.press("Escape")
    expect(tid(seite, "konto-einstellungen")).to_have_count(0)
    mit.leeren()
    tid(seite, f"uebersicht-konto-{a['id']}").click(button="right")
    tid(seite, "km-konto-einstellungen").click()
    tid(seite, "einstellungen-notiz").fill("Notiz neu")
    tid(seite, "einstellungen-speichern").click()
    expect(tid(seite, "konto-einstellungen")).to_have_count(0)
    assert mit.schreibend() == [("PATCH", f"/api/konten/{a['id']}", {"notiz": "Notiz neu"})]


# ------------------------------------------------------------------ 25.5 PIN-Dialog


def _pin():
    return json.loads(SYNC_DATEN_PIN.read_text(encoding="utf-8"))["bank"]["pin"]


def _pin_dialog(seite, server):
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, "sync-starten").click()
    d = tid(seite, "pin-dialog")
    expect(d).to_be_visible()
    return d


def test_pin_dialog_gesperrt_mit_phasen(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN_PIN, mock_verzoegerung_ms=2500)
    seite = neue_seite(server)
    d = _pin_dialog(seite, server)
    tid(seite, "pin-eingabe").fill(_pin())
    tid(seite, "pin-eingabe").press("Enter")
    expect(d).to_have_attribute("data-gesperrt", "ja")
    expect(d).to_have_attribute("aria-busy", "true")
    for x in ("pin-eingabe", "pin-senden", "pin-abbrechen"):
        expect(tid(seite, x)).to_be_disabled()
    seite.keyboard.press("Escape")
    expect(d).to_be_visible()
    status = tid(seite, "pin-dialog-status")
    expect(status).to_have_attribute("role", "status")
    expect(status).to_have_attribute("data-phase", "abruf")
    expect(status).to_contain_text("Rufe Umsätze ab")
    expect(status).to_have_attribute("data-phase", "fertig", timeout=15_000)
    expect(tid(seite, "pin-dialog")).to_have_count(0)
    assert server.api.get("/api/sync/laeufe", erwartet=200).daten[-1]["status"] == "erfolgreich"


def test_pin_dialog_falsche_pin_entsperrt(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN_PIN)
    seite = neue_seite(server)
    d = _pin_dialog(seite, server)
    tid(seite, "pin-eingabe").fill("FALSCHE-PIN-0000")
    tid(seite, "pin-senden").click()
    expect(d.get_by_test_id("dialog-fehler")).to_contain_text("Die Bank hat die PIN abgelehnt. Bitte erneut eingeben.")
    expect(d).to_have_attribute("data-gesperrt", "nein")
    expect(tid(seite, "pin-eingabe")).to_be_focused()
    expect(tid(seite, "pin-eingabe")).to_be_enabled()


def test_pin_dialog_tan(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN_PIN, mock_szenario="tan_erforderlich")
    seite = neue_seite(server)
    _pin_dialog(seite, server)
    tid(seite, "pin-eingabe").fill(_pin())
    tid(seite, "pin-senden").click()
    expect(tid(seite, "pin-dialog-status")).to_have_attribute("data-phase", "tan")
    expect(tid(seite, "pin-dialog")).to_have_count(0)
    expect(tid(seite, "sync-tan-link")).to_be_visible()


# ------------------------------------------------------------------ 25.6 Vorschläge


def _vorschlaege(api) -> dict:
    k = {"giro": api.konto("Girokonto", "girokonto")["id"]}
    k["haus"] = api.konto("Haushalt", "aufwand")["id"]
    k["leb"] = api.konto("Lebensmittel", "aufwand", eltern_id=k["haus"])["id"]
    k["cafe"] = api.konto("Café", "aufwand")["id"]
    baecker = api.empfaenger("Bäckerei Korn")["id"]
    for i in range(8):
        api.buchung(f"2024-01-{i + 1:02d}", [(k["giro"], -500), (k["leb"], 500)], empfaenger_id=baecker)
    api.buchung("2024-01-20", [(k["giro"], -500), (k["cafe"], 500)], empfaenger_id=baecker)
    k["lern"] = erfassen(api, art="ausgabe", datum="2024-02-01", konto_id=k["giro"], betrag=500,
                         empfaenger_id=baecker)["id"]
    api.post("/api/lernmodell/anwenden", json={"buchung_ids": [k["lern"]]}, erwartet=200)
    tank = api.empfaenger("Tankstelle Nord")["id"]
    k["regel"] = erfassen(api, art="ausgabe", datum="2024-02-02", konto_id=k["giro"], betrag=4000,
                          empfaenger_id=tank, status="importiert")["id"]
    regel = api.post("/api/regeln", json={"name": "Tanken", "kategorie_id": k["cafe"], "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "tankstelle"}]}, erwartet=201).daten
    k["regel_name"] = regel["name"]
    api.post("/api/regeln/anwenden", json={"regel_ids": [regel["id"]]}, erwartet=200)
    # ab M32 keine Standardkategorie mehr (sammel3.md 2.1, E-307): kein Fall „Empf.“
    for x, q in (("lern", "lernmodell"), ("regel", "regel")):
        v = api.buchung_lesen(k[x])["vorschlag"]
        assert v and v["quelle"] == q, f"Testvoraussetzung: Vorschlag {q}: {v}"
    return k


def _vorschlag_seite(starte_server, neue_seite, geraet="desktop"):
    server = starte_server()
    k = _vorschlaege(server.api)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    m8.warte_liste(seite, m8.rest_liste(server.api, k["giro"]))
    return server, seite, k


@pytest.mark.parametrize("geraet", ["desktop", "handy"])
def test_vorschlag_marken(starte_server, neue_seite, geraet):
    server, seite, k = _vorschlag_seite(starte_server, neue_seite, geraet)
    api = server.api
    p = api.buchung_lesen(k["lern"])["vorschlag"]["sicherheit"]
    erwartet = {
        "lern": ("lernmodell", str(p), prozent_text(p), ["Lernmodell", prozent_text(p)], "Haushalt › Lebensmittel"),
        "regel": ("regel", "", "Regel", ["Regel", k["regel_name"]], "Café"),
    }
    for x, (quelle, sicherheit, text, titel, pfad) in erwartet.items():
        z = zeile(seite, k[x])
        expect(z).to_have_attribute("data-vorschlag", "ja")
        marke = z.get_by_test_id("vorschlag-marke")
        expect(marke).to_have_attribute("data-quelle", quelle)
        assert (marke.get_attribute("data-sicherheit") or "") == sicherheit
        assert text_normal(marke.inner_text()) == text, (x, marke.inner_text())
        lang = text_normal((marke.get_attribute("title") or "") + " " + (marke.get_attribute("aria-label") or ""))
        assert all(t in lang for t in titel), (x, lang)
        kat = z.locator('[data-feld="kategorie"] .vorschlag-kategorie')
        expect(kat).to_have_count(1)
        assert text_normal(kat.inner_text()) == pfad
        if geraet == "handy":
            expect(tid(seite, f"vorschlag-annehmen-{k[x]}")).to_be_visible()
            expect(tid(seite, f"vorschlag-ablehnen-{k[x]}")).to_be_visible()


def test_details_vorschlag_und_kandidaten(starte_server, neue_seite):
    server, seite, k = _vorschlag_seite(starte_server, neue_seite)
    api = server.api
    vorh = api.post("/api/lernmodell/vorhersage", json={"eintraege": [{"buchung_id": k["lern"]}]},
                    erwartet=200).daten["ergebnisse"][0]
    vorschlag = api.buchung_lesen(k["lern"])["vorschlag"]
    kandidaten = {c["kategorie_id"] for c in vorh["kandidaten"] if c["sicherheit"] >= 10} - {vorschlag["kategorie_id"]}
    assert k["cafe"] in kandidaten, "Testvoraussetzung: Café als Kandidat ab 1 %"
    zeile(seite, k["lern"]).click()
    d = tid(seite, "details-vorschlag")
    expect(d).to_be_visible()
    expect(d).to_have_attribute("data-quelle", "lernmodell")
    expect(d.get_by_test_id("details-vorschlag-annehmen")).to_be_visible()
    expect(d.get_by_test_id("details-vorschlag-ablehnen")).to_be_visible()
    expect(tid(seite, "details-vorschlag-kandidaten")).to_be_visible()
    knoepfe = {int(x.split("-")[-1]) for x in seite.locator('[data-testid^="details-kandidat-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))") if re.fullmatch(r"details-kandidat-\d+", x)}
    assert knoepfe == kandidaten
    tid(seite, f"details-kandidat-{k['cafe']}").click()
    warte_bis(lambda: api.buchung_lesen(k["lern"])["kategorie_id"] == k["cafe"], text="Kandidat übernommen")


# ------------------------------------------------------------------ 25.7 Berichte


def _bericht(starte_server, neue_seite, route=None):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    konten = [ids.konto[erw["m8"]["konten"]["giro"]],
              next(k["id"] for k in server.api.konten() if k["art"] in ("sparkonto", "kreditkonto"))]
    seite = neue_seite(server)
    if route:
        seite.route(re.compile(r".*plotly.*", re.I), lambda r: r.abort())
    oeffnen(seite, server, "/berichte", seitenname="berichte")
    return server, seite, konten


def test_bericht_diagramm_reihen(starte_server, neue_seite):
    server, seite, konten = _bericht(starte_server, neue_seite)
    diagramm = tid(seite, "bericht-diagramm")
    expect(diagramm).to_have_attribute("role", "img")
    assert text_normal(diagramm.inner_text()), "ohne Konten ein Hinweistext"
    tid(seite, "bericht-von").fill("2024-01-01")
    tid(seite, "bericht-bis").fill("2024-12-31")
    tid(seite, "bericht-konten").select_option([str(konten[0])])
    expect(diagramm).to_have_attribute("data-reihen", "1")
    tid(seite, "bericht-konten").select_option([str(x) for x in konten])
    expect(diagramm).to_have_attribute("data-reihen", "2")
    expect(diagramm).to_have_attribute("role", "img")
    assert (diagramm.get_attribute("aria-label") or "").strip()
    quellen = seite.evaluate("() => [...document.scripts].map(s => s.src).filter(Boolean)")
    assert all(m8.gleiche_herkunft(q, server.herkunft) for q in quellen)


def test_bericht_einnahmen_ausgaben_diagramm(starte_server, neue_seite):
    server, seite, konten = _bericht(starte_server, neue_seite)
    seite.get_by_role("button", name=re.compile("berechnen", re.I)).first.click()
    ea = tid(seite, "bericht-ea-diagramm")
    expect(ea).to_be_visible()
    expect(ea).to_have_attribute("role", "img")
    assert (ea.get_attribute("aria-label") or "").strip()


def test_bericht_ohne_grafikbibliothek(starte_server, neue_seite):
    server, seite, konten = _bericht(starte_server, neue_seite, route=True)
    tid(seite, "bericht-von").fill("2024-01-01")
    tid(seite, "bericht-bis").fill("2024-12-31")
    tid(seite, "bericht-konten").select_option([str(konten[0])])
    diagramm = tid(seite, "bericht-diagramm")
    expect(diagramm).to_be_visible()
    expect(diagramm).to_have_attribute("role", "img")
    assert (diagramm.get_attribute("aria-label") or "").strip()
