"""M8: Mehrfachauswahl wie im Dateimanager und Mehrfachbearbeitung (oberflaeche.md 7.4, 7.5; K 5; T 19)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import ausgewaehlt, oeffnen, tid, zeile

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


def _klick(seite, bid, modifiers=None):
    zeile(seite, bid).locator('[data-feld="verwendungszweck"]').click(modifiers=modifiers or [])


def _warte_auswahl(seite, erwartet: set[int]):
    ende = 100
    for _ in range(ende):
        if ausgewaehlt(seite) == erwartet:
            break
        seite.wait_for_timeout(50)
    assert ausgewaehlt(seite) == erwartet
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", str(len(erwartet)))


@pytest.mark.kern
def test_klick_strg_umschalt(konto):
    server, seite, erw, ids, giro, r = konto
    expect(tid(seite, "buchungsliste")).to_have_attribute("role", "grid")
    expect(tid(seite, "buchungsliste")).to_have_attribute("aria-multiselectable", "true")
    expect(tid(seite, "mehrfach-leiste")).to_be_hidden()
    _klick(seite, r[2])
    _warte_auswahl(seite, {r[2]})
    expect(tid(seite, "mehrfach-leiste")).to_be_visible()
    _klick(seite, r[5], ["Control"])
    _warte_auswahl(seite, {r[2], r[5]})
    _klick(seite, r[2], ["Control"])           # umschalten: wieder weg
    _warte_auswahl(seite, {r[5]})
    _klick(seite, r[8], ["Shift"])             # Bereich vom Anker (r[2], letzter Strg-Klick) bis r[8]
    _warte_auswahl(seite, set(r[2:9]))
    _klick(seite, r[4], ["Shift"])             # Anker unverändert: Bereich r[2]..r[4]
    _warte_auswahl(seite, set(r[2:5]))
    _klick(seite, r[11])                       # einfacher Klick: nur diese Zeile, neuer Anker
    _warte_auswahl(seite, {r[11]})
    _klick(seite, r[13], ["Shift"])
    _warte_auswahl(seite, set(r[11:14]))
    _klick(seite, r[0], ["Control"])
    _klick(seite, r[1], ["Control", "Shift"])  # Strg+Umschalt: Bereich Anker r[0]..r[1] hinzu
    _warte_auswahl(seite, set(r[11:14]) | {r[0], r[1]})
    for bid in r[:15]:
        expect(zeile(seite, bid)).to_have_attribute("aria-selected", "true" if bid in ausgewaehlt(seite) else "false")


@pytest.mark.kern
def test_umschalt_ohne_anker_wie_klick(konto):
    server, seite, erw, ids, giro, r = konto
    _klick(seite, r[6], ["Shift"])
    _warte_auswahl(seite, {r[6]})


@pytest.mark.kern
def test_tastatur(konto):
    server, seite, erw, ids, giro, r = konto
    _klick(seite, r[3])
    seite.keyboard.press("ArrowDown")
    _warte_auswahl(seite, {r[4]})
    expect(zeile(seite, r[4])).to_have_attribute("tabindex", "0")
    expect(zeile(seite, r[4])).to_be_focused()
    seite.keyboard.press("Shift+ArrowDown")
    seite.keyboard.press("Shift+ArrowDown")
    _warte_auswahl(seite, set(r[4:7]))
    seite.keyboard.press("Control+ArrowDown")  # nur Fokus
    _warte_auswahl(seite, set(r[4:7]))
    expect(zeile(seite, r[7])).to_be_focused()
    seite.keyboard.press(" ")
    _warte_auswahl(seite, set(r[4:8]))
    seite.keyboard.press("Home")
    _warte_auswahl(seite, {r[0]})
    seite.keyboard.press("End")
    _warte_auswahl(seite, {r[-1]})
    seite.keyboard.press("Control+a")
    _warte_auswahl(seite, set(r))
    seite.keyboard.press("Escape")
    _warte_auswahl(seite, set())
    expect(tid(seite, "mehrfach-leiste")).to_be_hidden()


@pytest.mark.kern
def test_mehrfach_kategorie(konto):
    server, seite, erw, ids, giro, r = konto
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    wahl = m8.kategorisierbare(erw, ids, r, 3, ohne=(haushalt,), ab=1)   # bekannte Wahrheit (W-007)
    andere = [b for b in r[:12] if b not in wahl]
    andere_vorher = {b: server.api.buchung_lesen(b)["kategorie_id"] for b in andere}
    _klick(seite, wahl[0])
    _klick(seite, wahl[1], ["Control"])
    _klick(seite, wahl[2], ["Control"])
    a0 = m8.max_aenderung(server.api)
    tid(seite, "mehrfach-kategorie").click()
    dialog = tid(seite, "kategorie-auswahl")
    expect(dialog).to_be_visible()
    expect(dialog).to_have_attribute("role", "dialog")
    expect(tid(seite, "kategorie-auswahl-suche")).to_be_focused()
    seite.keyboard.type("haush")
    tid(seite, f"kategorie-option-{haushalt}").click()
    expect(dialog).to_be_hidden()
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(server.api, a0), text="Änderung der Mehrfachbearbeitung")
    assert [(a["quelle"], a["aktion"]) for a in neu] == [("manuell", "mehrfach_kategorie")]
    for bid in wahl:
        assert server.api.buchung_lesen(bid)["kategorie_id"] == haushalt, bid
    assert {b: server.api.buchung_lesen(b)["kategorie_id"] for b in andere} == andere_vorher
    # die Oberfläche zeigt den Stand des Servers, die Auswahl bleibt
    for bid in wahl:
        expect(zeile(seite, bid).locator('[data-feld="kategorie"]')).to_have_attribute("data-kategorie-id",
                                                                                         str(haushalt))
    _warte_auswahl(seite, set(wahl))


@pytest.mark.kern
def test_einzelne_buchung_kategorie_per_put(konto):
    server, seite, erw, ids, giro, r = konto
    kino = ids.konto[erw["m8"]["konten"]["kino"]]
    (bid,) = m8.kategorisierbare(erw, ids, r, ohne=(kino,))
    _klick(seite, bid)
    a0 = m8.max_aenderung(server.api)
    tid(seite, "mehrfach-kategorie").click()
    tid(seite, f"kategorie-option-{kino}").click()
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(server.api, a0))
    assert [a["aktion"] for a in neu] == ["kategorie_setzen"]
    assert server.api.buchung_lesen(bid)["kategorie_id"] == kino


@pytest.mark.kern
def test_kategorie_auswahl_tastatur_und_esc(konto):
    server, seite, erw, ids, giro, r = konto
    strom = ids.konto[erw["m8"]["konten"]["strom"]]
    (bid,) = m8.kategorisierbare(erw, ids, r, ohne=(strom,))
    _klick(seite, bid)
    vorher = server.api.buchung_lesen(bid)
    a0 = m8.max_aenderung(server.api)
    tid(seite, "mehrfach-kategorie").click()
    expect(tid(seite, "kategorie-auswahl")).to_be_visible()
    seite.keyboard.press("Escape")
    expect(tid(seite, "kategorie-auswahl")).to_be_hidden()
    expect(tid(seite, "mehrfach-kategorie")).to_be_focused()
    assert m8.max_aenderung(server.api) == a0
    # Suche filtert nach Pfad, Enter übernimmt den markierten Eintrag
    tid(seite, "mehrfach-kategorie").click()
    seite.keyboard.type("wohnen strom")
    optionen = tid(seite, "kategorie-auswahl-liste").get_by_role("option")
    expect(optionen).to_have_count(1)
    expect(tid(seite, f"kategorie-option-{strom}")).to_have_text("Wohnen › Strom")
    seite.keyboard.press("ArrowDown")
    seite.keyboard.press("Enter")
    m8.warte_bis(lambda: server.api.buchung_lesen(bid)["kategorie_id"] == strom)
    assert vorher["kategorie_id"] != strom


def test_mehrfach_tags_neuer_tag_und_entfernen(konto):
    server, seite, erw, ids, giro, r = konto
    wahl = [r[0], r[1]]
    _klick(seite, wahl[0])
    _klick(seite, wahl[1], ["Shift"])
    tid(seite, "mehrfach-tags").click()
    expect(tid(seite, "tag-auswahl")).to_be_visible()
    tid(seite, "tag-auswahl-name").fill("Prüfung 2024")
    a0 = m8.max_aenderung(server.api)
    tid(seite, "tag-auswahl-hinzufuegen").click()
    neu = m8.warte_bis(lambda: [a for a in m8.aenderungen_seit(server.api, a0) if a["aktion"] == "mehrfach_tags"]
                       and m8.aenderungen_seit(server.api, a0))
    assert [a["aktion"] for a in neu] == ["tag_anlegen", "mehrfach_tags"]
    tag = next(t for t in server.api.get("/api/tags", erwartet=200).daten if t["name"] == "Prüfung 2024")
    for bid in wahl:
        assert tag["id"] in [t["id"] for t in server.api.buchung_lesen(bid)["tags"]]
        expect(zeile(seite, bid).locator(f'[data-testid="tag"][data-tag-id="{tag["id"]}"]')).to_be_visible()
    # Entfernen, Vergleich nach casefold
    tid(seite, "mehrfach-tags").click()
    tid(seite, "tag-auswahl-name").fill("PRÜFUNG 2024")
    tid(seite, "tag-auswahl-entfernen").click()
    m8.warte_bis(lambda: all(tag["id"] not in [t["id"] for t in server.api.buchung_lesen(b)["tags"]] for b in wahl))
    # unbekannter Name beim Entfernen: Fehler im Dialog, keine Anfrage
    a1 = m8.max_aenderung(server.api)
    tid(seite, "mehrfach-tags").click()
    tid(seite, "tag-auswahl-name").fill("Gibt es nicht")
    tid(seite, "tag-auswahl-entfernen").click()
    expect(tid(seite, "tag-auswahl").get_by_test_id("dialog-fehler")).to_be_visible()
    assert m8.max_aenderung(server.api) == a1


def test_mehrfach_loeschen_mit_rueckfrage(konto):
    server, seite, erw, ids, giro, r = konto
    wahl = [r[0], r[1], r[2]]
    _klick(seite, wahl[0])
    _klick(seite, wahl[2], ["Shift"])
    tid(seite, "mehrfach-loeschen").click()
    expect(tid(seite, "bestaetigen-dialog")).to_be_visible()
    expect(tid(seite, "bestaetigen-nein")).to_be_focused()
    tid(seite, "bestaetigen-nein").click()
    expect(tid(seite, "bestaetigen-dialog")).to_be_hidden()
    assert all(server.api.get(f"/api/buchungen/{b}").status_code == 200 for b in wahl)
    tid(seite, "mehrfach-loeschen").click()
    tid(seite, "bestaetigen-ja").click()
    m8.warte_bis(lambda: all(server.api.get(f"/api/buchungen/{b}").status_code == 404 for b in wahl))
    m8.warte_liste(seite, r[3:])
    expect(tid(seite, "buchungsliste-anzahl")).to_have_attribute("data-anzahl", str(len(r) - 3))


def test_mehrfach_fehler_atomar(konto):
    """Eine abgestimmte Buchung in der Auswahl: 409, nichts ändert sich, die Oberfläche meldet den Fehler."""
    server, seite, erw, ids, giro, r = konto
    api = server.api
    gesperrt = r[-1]  # älteste Buchung
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    # beide kategorisierbar (bekannte Wahrheit), damit allein die Sperre (409) die Ablehnung auslöst (W-007)
    (frei,) = m8.kategorisierbare(erw, ids, r, ohne=(haushalt,))
    assert m8.kategorisierbare(erw, ids, [gesperrt]) == [gesperrt]
    b = api.buchung_lesen(gesperrt)
    stichtag = b["datum"]
    saldo = sum(s["betrag"] for x in api.alle_buchungen(konto_id=giro, bis=stichtag)
                for s in x["splits"] if s["konto_id"] == giro)
    api.post("/api/abstimmungen", json={"konto_id": giro, "stichtag": stichtag, "saldo": saldo}, erwartet=200)
    seite.reload()
    m8.warte_liste(seite, r)
    vorher = {x: api.buchung_lesen(x)["kategorie_id"] for x in (frei, gesperrt)}
    _klick(seite, frei)
    _klick(seite, gesperrt, ["Control"])
    a0 = m8.max_aenderung(api)
    tid(seite, "mehrfach-kategorie").click()
    tid(seite, f"kategorie-option-{haushalt}").click()
    fehler = tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="fehler"]')
    expect(fehler).to_be_visible()
    expect(fehler).to_have_attribute("role", "alert")
    assert m8.max_aenderung(api) == a0
    assert {x: api.buchung_lesen(x)["kategorie_id"] for x in (frei, gesperrt)} == vorher
    expect(zeile(seite, frei).locator('[data-feld="kategorie"]')).to_have_attribute(
        "data-kategorie-id", str(vorher[frei] or ""))
