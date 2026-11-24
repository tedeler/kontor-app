"""M28: Kontoblatt – Gruppierung, Ausschnitt, Stifte, Kontextmenü, Filter, Dublette, Bestätigen, Verdacht,
Tastaturkürzel, Listenbreite (oberflaeche.md 37.6–37.11, 37.12.7; E-252, E-255). Browsertests, nicht kern.

Erwartete Listen und Summen stellt der Test selbst über REST fest (``tests/hilfen/m28``, ``tests/hilfen/m27``).
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import m8, m17, m28
from tests.hilfen.m8 import ausgewaehlt, oeffnen, strg, tid, warte_bis, warte_liste, zeile
from tests.hilfen.m17 import warte

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


def _start(starte_server, neue_seite, geraet="desktop", abfrage="", **kw):
    server = starte_server()
    d = m17.daten(server.api)
    seite = neue_seite(server, geraet, **kw)
    oeffnen(seite, server, f"/konten/{d['k']['giro']}{abfrage}", seitenname="konto")
    return server, server.api, seite, d["k"], d["b"]


def _liste(api, kid, **p):
    return m8.rest_liste(api, kid, **p)


# ------------------------------------------------------------------ 37.6 Gruppierung


def test_gruppierung_nach_datum(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    api.buchung("2023-12-30", [(k["giro"], 4200), (k["zins"], -4200)])
    seite.reload()
    m8.warte_geladen(seite, "konto")
    gruppe = seite.get_by_role("group", name="Buchungen gruppieren")
    expect(gruppe).to_be_visible()
    keine, datum = tid(seite, "gruppierung-keine"), tid(seite, "gruppierung-datum")
    expect(keine).to_have_attribute("aria-pressed", "true")
    expect(datum).to_have_attribute("aria-pressed", "false")
    expect(tid(seite, "gruppierung-zu")).to_be_disabled()
    expect(tid(seite, "gruppierung-auf")).to_be_disabled()
    datum.click()
    warte(seite, lambda: m28.abfrage(seite).get("gruppierung") == ["datum"], text="?gruppierung=datum")
    expect(datum).to_have_attribute("aria-pressed", "true")
    alle = api.alle_buchungen(konto_id=k["giro"], sortierung="-datum")
    soll = m28.perioden_soll(alle)
    warte(seite, lambda: len(m28.balken(seite)) == len(soll), text="alle Periodenbalken")
    reihe = m28.balken(seite)
    jahre = [s for e, s in reihe if e == "jahr"]
    assert jahre == sorted(jahre, reverse=True), "Datumsrichtung der Sortierung (absteigend)"
    for ebene, s in reihe:
        x = soll[s]
        assert ebene == x["ebene"]
        expect(tid(seite, f"periode-{s}")).to_have_attribute("aria-expanded", "true")
        expect(tid(seite, f"periode-{s}")).to_contain_text(m28.perioden_text(s))
        for f in ("eingang", "ausgang", "summe"):
            expect(tid(seite, f"periode-{f}-{s}")).to_have_attribute("data-betrag", str(x[f]))
        expect(tid(seite, f"periode-anzahl-{s}")).to_have_attribute("data-anzahl", str(x["anzahl"]))
        expect(tid(seite, f"periode-anzahl-{s}")).to_have_text(m28.anzahl_text(x["anzahl"]))
    assert m8.zellen_ids(seite) == [x["id"] for x in alle]
    expect(tid(seite, "buchungsliste-mehr")).to_be_hidden()
    expect(tid(seite, "gruppierung-auf")).to_be_disabled()
    expect(tid(seite, "gruppierung-zu")).to_be_enabled()
    # Zuklappen eines Jahres verbirgt alles darunter
    tid(seite, "periode-2023").click()
    expect(tid(seite, "periode-2023")).to_have_attribute("aria-expanded", "false")
    expect(tid(seite, "periode-2023-12")).to_have_count(0)
    expect(tid(seite, "periode-2023-12-30")).to_have_count(0)
    # Tastatur: Pfeil rechts klappt auf, links zu
    tid(seite, "periode-2023").focus()
    seite.keyboard.press("ArrowRight")
    expect(tid(seite, "periode-2023")).to_have_attribute("aria-expanded", "true")
    seite.keyboard.press("ArrowLeft")
    expect(tid(seite, "periode-2023")).to_have_attribute("aria-expanded", "false")
    tid(seite, "gruppierung-auf").click()
    expect(tid(seite, "periode-2023-12-30")).to_have_attribute("aria-expanded", "true")
    tid(seite, "gruppierung-zu").click()
    expect(tid(seite, "gruppierung-zu")).to_be_disabled()
    for s in soll:
        if soll[s]["ebene"] == "jahr":
            expect(tid(seite, f"periode-{s}")).to_have_attribute("aria-expanded", "false")
    assert m8.zellen_ids(seite) == []
    keine.click()
    warte(seite, lambda: "gruppierung" not in m28.abfrage(seite), text="Parameter entfernt")
    warte_liste(seite, _liste(api, k["giro"]))


def test_gruppierung_direkt_aufsteigend_und_unbekannter_wert(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, abfrage="?gruppierung=datum&sortierung=datum")
    alle = api.alle_buchungen(konto_id=k["giro"], sortierung="datum")
    warte(seite, lambda: len(m28.balken(seite)) == len(m28.perioden_soll(alle)), text="sofort gruppiert")
    tage = [s for e, s in m28.balken(seite) if e == "tag"]
    assert tage == sorted(tage), "aufsteigende Sortierung: Knoten aufsteigend"
    oeffnen(seite, server, f"/konten/{k['giro']}?gruppierung=jahr", seitenname="konto")
    warte_liste(seite, _liste(api, k["giro"]))
    assert m28.balken(seite) == []
    expect(tid(seite, "gruppierung-keine")).to_have_attribute("aria-pressed", "true")


# ------------------------------------------------------------------ 37.7 Ausschnitt


def test_ausschnitt_langer_listen(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, z = api.konto("Girokonto")["id"], api.konto("Zinsen", "ertrag")["id"]
    start = dt.date(2024, 1, 1)
    ids = [api.buchung((start + dt.timedelta(days=i)).isoformat(), [(g, 100 + i), (z, -(100 + i))],
                       verwendungszweck=f"Posten {i}")["id"] for i in range(140)]
    tief = ids[5]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}?buchung={tief}", seitenname="konto")
    liste = tid(seite, "buchungsliste")
    warte(seite, lambda: liste.get_attribute("aria-rowcount") not in (None, ""), text="aria-rowcount")
    assert int(liste.get_attribute("aria-rowcount")) == 141, "alle Einträge plus Kopfzeile"
    gezeichnet = liste.locator('[role="row"][data-testid^="buchung-"]').count()
    assert gezeichnet < 140, f"nur ein Ausschnitt im Dokument ({gezeichnet})"
    assert liste.locator('[role="row"][aria-rowindex]').count() >= gezeichnet
    warte(seite, lambda: ausgewaehlt(seite) == {tief}, text="Sprungziel ausgewählt")
    expect(zeile(seite, tief)).to_be_in_viewport()
    assert m8.zellen_ids(seite) == _liste(api, g)


# ------------------------------------------------------------------ 37.8 Stifte


def test_kein_doppelklick_editor_und_stifte(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    for feld in ("empfaenger", "status", "betrag", "verwendungszweck", "datum"):
        zelle = zeile(seite, b["einfach"]).locator(f'[data-feld="{feld}"]')
        if zelle.count():
            zelle.dblclick()
            expect(zeile(seite, b["einfach"]).get_by_test_id("inline-editor")).to_have_count(0)
    assert ausgewaehlt(seite) == {b["einfach"]}
    d = tid(seite, "panel-details")
    namen = {"datum": "Datum", "empfaenger": "Empfänger", "verwendungszweck": "Verwendungszweck",
             "splits": "Splits", "tags": "Tags", "status": "Status"}
    for feld in namen:
        s = d.get_by_test_id(f"stift-{feld}")
        expect(s).to_be_visible()
        expect(s).to_have_js_property("tagName", "BUTTON")
        assert (s.get_attribute("aria-label") or "").endswith(" bearbeiten")
    a0 = m8.max_aenderung(api)
    e = m8.stift(seite, b["einfach"], "verwendungszweck")
    e.fill("Über den Stift")
    e.press("Escape")
    expect(d.get_by_test_id("inline-editor")).to_have_count(0)
    assert m8.max_aenderung(api) == a0
    e = m8.stift(seite, b["einfach"], "verwendungszweck")
    e.fill("Über den Stift")
    e.press("Enter")
    warte_bis(lambda: api.buchung_lesen(b["einfach"])["verwendungszweck"] == "Über den Stift")
    assert [a["aktion"] for a in m8.aenderungen_seit(api, a0)] == ["buchung_aendern"]
    m8.stift(seite, b["einfach"], "splits")
    expect(tid(seite, "split-dialog")).to_be_visible()
    tid(seite, "split-abbrechen").click()
    # F2 und km-bearbeiten öffnen weiter den Editor des Verwendungszwecks in der Zeile
    e = m8.zweck_editor(seite, b["zweite"])
    expect(e).to_have_attribute("data-feld", "verwendungszweck")
    e.press("Escape")


def test_stifte_gesperrt(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [b["zweite"]], "status": "abgeglichen"},
             erwartet=200)
    seite.reload()
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["zweite"]).locator('[data-feld="betrag"]').click()
    d = tid(seite, "panel-details")
    for feld in ("datum", "empfaenger", "verwendungszweck", "splits"):
        expect(d.get_by_test_id(f"stift-{feld}")).to_be_disabled()
    for feld in ("status", "tags"):
        expect(d.get_by_test_id(f"stift-{feld}")).to_be_enabled()


# ------------------------------------------------------------------ 37.9 Kontextmenü


def test_kontextmenue_reihenfolge_und_kuerzel_nur_darstellung(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["einfach"]).click(button="right")
    expect(tid(seite, "kontextmenue")).to_be_visible()
    assert m28.menue(seite) == m28.KM_REIHENFOLGE
    expect(tid(seite, "km-gegenbuchung")).to_have_js_property("textContent", "Gehe zur Gegenbuchung")
    seite.keyboard.press("Escape")
    zeile(seite, b["einfach"]).click(button="right", modifiers=["Alt"])
    soll = m28.KM_REIHENFOLGE[:-1] + ["km-verschieben", "km-loeschen"]
    assert m28.menue(seite) == soll
    expect(tid(seite, "km-verschieben")).to_have_js_property("textContent", "Auf anderes Konto verschieben…")
    seite.keyboard.press("Escape")
    # Kategorie-Ansicht: nie Verschieben
    oeffnen(seite, server, f"/konten/{k['leb']}", seitenname="konto")
    warte_liste(seite, _liste(api, k["leb"]))
    zeile(seite, b["einfach"]).click(button="right", modifiers=["Alt"])
    expect(tid(seite, "km-verschieben")).to_have_count(0)


def test_kontextmenue_mobil_mit_foto_und_verschieben(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite, "handy")
    warte_liste(seite, _liste(api, k["giro"]))
    m8.auswahlmenue_mobil(seite, zeile(seite, b["einfach"]))
    ids = m28.menue(seite)
    i = ids.index("km-dokument-anhaengen")
    assert ids[i + 1] == "km-dokument-foto"
    assert "km-verschieben" in ids
    texte = tid(seite, "kontextmenue").locator('[role="menuitem"]').evaluate_all(
        "els => els.map(e => e.innerText)")
    assert not any("[" in t for t in texte), "mobil keine Kürzel"


@pytest.mark.parametrize("eintrag,param", [("km-filter-empfaenger", "empfaenger_id"),
                                           ("km-filter-zweck", "zweck_gleich"),
                                           ("km-filter-zweck-aehnlich", "zweck_aehnlich"),
                                           ("km-filter-empfaenger-aehnlich", "empfaenger_aehnlich")])
def test_filter_untermenue(starte_server, neue_seite, eintrag, param):
    server = starte_server()
    api = server.api
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    e1 = api.empfaenger("Bäckerei Krume (fiktiv)")["id"]
    e2 = api.empfaenger("Bäckerei Kruste (fiktiv)")["id"]
    ziel = api.buchung("2024-05-01", [(g, -300), (leb, 300)], empfaenger_id=e1, verwendungszweck="Brot und Mehl")["id"]
    for i, (e, z) in enumerate([(e1, "brot und mehl"), (e2, "Brotkorb"), (e2, "Kuchen"), (None, "Mehl 2kg")]):
        felder = {"verwendungszweck": z} | ({"empfaenger_id": e} if e else {})
        api.buchung(f"2024-05-0{i + 2}", [(g, -100 - i), (leb, 100 + i)], **felder)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, _liste(api, g))
    zeile(seite, ziel).click(button="right")
    tid(seite, "km-filter").hover()
    tid(seite, "km-filter").click()
    u = tid(seite, "untermenue")
    expect(u).to_be_visible()
    assert u.locator('[role="menuitem"]').evaluate_all("els => els.map(e => e.getAttribute('data-testid'))") == [
        "km-filter-empfaenger", "km-filter-zweck", "km-filter-zweck-aehnlich", "km-filter-empfaenger-aehnlich"]
    tid(seite, eintrag).click()
    wert = {"empfaenger_id": str(e1), "zweck_gleich": "Brot und Mehl", "zweck_aehnlich": "Brot und Mehl",
            "empfaenger_aehnlich": "Bäckerei Krume (fiktiv)"}[param]
    # ab M30 (oberflaeche.md 39.2, E-271): geprüft wird die Trefferliste; der Filter steht im Ausdruck
    # (`filter=`) oder bleibt als Adressparameter ohne Entsprechung (`filter-alt-<name>`)
    warte_liste(seite, _liste(api, g, **{param: wert}))
    warte(seite, lambda: bool({"filter", param} & set(m28.abfrage(seite))), text="Filter in der Adresse")
    m8.filter_aktiv(seite)
    assert ausgewaehlt(seite) == set()
    m8.filter_zuruecksetzen(seite)
    warte_liste(seite, _liste(api, g))


def test_filter_leerer_zweck_und_ohne_empfaenger(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    leer = api.buchung("2024-05-01", [(g, -300), (leb, 300)])["id"]
    api.buchung("2024-05-02", [(g, -301), (leb, 301)], verwendungszweck="x")
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, _liste(api, g))
    zeile(seite, leer).click(button="right")
    tid(seite, "km-filter").click()
    expect(tid(seite, "km-filter-empfaenger")).to_have_attribute("aria-disabled", "true")
    expect(tid(seite, "km-filter-empfaenger-aehnlich")).to_have_attribute("aria-disabled", "true")
    tid(seite, "km-filter-zweck").click()
    warte_liste(seite, [leer])   # ab M30 im Ausdruck oder als zweck_leer (E-271)
    warte(seite, lambda: bool({"filter", "zweck_leer"} & set(m28.abfrage(seite))), text="Filter in der Adresse")


def test_als_dublette_markieren_zwei(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    a0 = m8.max_aenderung(api)
    zeile(seite, b["einfach"]).click()
    zeile(seite, b["zweite"]).click(modifiers=[strg()])
    zeile(seite, b["zweite"]).click(button="right")
    tid(seite, "km-dublette").click()
    d = tid(seite, "dublette-dialog")
    expect(d).to_be_visible()
    expect(tid(seite, "dublette-erklaerung")).to_be_visible()
    for x in (b["einfach"], b["zweite"]):
        expect(tid(seite, f"dublette-zusammenfuehren-{x}")).to_have_text("Diese behalten")
    tid(seite, "dublette-abbrechen").click()
    expect(d).to_be_hidden()
    assert m8.max_aenderung(api) == a0 and api.get("/api/dubletten", erwartet=200).daten == []
    zeile(seite, b["zweite"]).click(button="right")
    tid(seite, "km-dublette").click()
    d.get_by_role("button", name="Keine Dublette").click()
    warte_bis(lambda: [v["status"] for v in api.get("/api/dubletten", erwartet=200).daten] == ["keine_dublette"])
    assert [a["aktion"] for a in m8.aenderungen_seit(api, a0)] == ["dublette_anlegen", "dublette_aufloesen"]
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.keyboard.press("Control+z")
    warte_bis(lambda: api.get("/api/dubletten", erwartet=200).daten == [], text="ein Rückgängig-Schritt")
    # drei Buchungen: deaktiviert
    zeile(seite, b["einfach"]).click()
    zeile(seite, b["zweite"]).click(modifiers=[strg()])
    zeile(seite, b["split"]).click(modifiers=[strg()])
    zeile(seite, b["split"]).click(button="right")
    expect(tid(seite, "km-dublette")).to_have_attribute("aria-disabled", "true")


# ------------------------------------------------------------------ 37.10 Bestätigen, Verdacht


def test_bestaetigen_durch_person(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["einfach"]).click(button="right")
    expect(tid(seite, "km-bestaetigen")).to_have_text("Als Torsten bestätigen")
    a0 = m8.max_aenderung(api)
    tid(seite, "km-bestaetigen").click()
    warte_bis(lambda: api.buchung_lesen(b["einfach"])["status"] == "bestaetigt", text="bestätigt")
    x = api.buchung_lesen(b["einfach"])
    assert [t["name"] for t in x["tags"]] == ["Torsten-Bestätigt"], "ab M32 Tag „B-<Name>“ (41.4, E-307)"
    expect(zeile(seite, b["einfach"])).to_have_attribute("data-bestaetigt", "Torsten")
    expect(zeile(seite, b["einfach"]).locator('[data-person="Torsten"]')).to_have_count(1)
    expect(tid(seite, "buchung-bestaetigung")).to_contain_text("Bestätigt von Torsten")
    zeile(seite, b["einfach"]).click(button="right")
    expect(tid(seite, "km-bestaetigen")).to_have_text("Bestätigung von Torsten zurücknehmen")
    seite.keyboard.press("Escape")
    # ein Strg+Z nimmt Tag und Status zusammen zurück
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.keyboard.press("Control+z")
    warte_bis(lambda: api.buchung_lesen(b["einfach"])["status"] == "importiert", text="Status zurück")
    assert api.buchung_lesen(b["einfach"])["tags"] == []
    assert m8.max_aenderung(api) > a0


def test_bestaetigen_vorlaeufig_bleibt_und_zuruecknehmen(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [b["split"]], "status": "vorlaeufig"},
             erwartet=200)
    seite.reload()
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["split"]).locator('[data-feld="betrag"]').click()
    expect(tid(seite, "buchung-bestaetigung")).to_contain_text("Noch von niemandem bestätigt.")
    tid(seite, "buchung-bestaetigen").click()
    warte_bis(lambda: [t["name"] for t in api.buchung_lesen(b["split"])["tags"]] == ["Torsten-Bestätigt"])   # M32: E-307
    assert api.buchung_lesen(b["split"])["status"] == "bestaetigt"   # D-257: Bestätigen erfasst auch vorläufige
    expect(tid(seite, "buchung-bestaetigen")).to_have_text("Bestätigung von Torsten zurücknehmen")
    tid(seite, "buchung-bestaetigen").click()
    warte_bis(lambda: api.buchung_lesen(b["split"])["tags"] == [], text="zurückgenommen")
    assert api.buchung_lesen(b["split"])["status"] == "bestaetigt"   # D-257: Bestätigen erfasst auch vorläufige


def test_label_verdaechtig(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    e = api.empfaenger("Unbekannter Laden (fiktiv)")["id"]
    v = api.buchung("2024-05-01", [(g, -300), (leb, 300)], empfaenger_id=e, status="importiert")["id"]
    ok = api.buchung("2024-05-02", [(g, -300), (leb, 300)], status="importiert")["id"]
    soll = api.get(f"/api/buchungen/{v}", params={"verdacht": "ja"}, erwartet=200).daten["verdacht"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, _liste(api, g))
    marke = zeile(seite, v).get_by_test_id("verdacht")
    expect(marke).to_have_text("Verdächtig")
    expect(marke).to_have_attribute("data-grund", soll["grund"])
    expect(marke).to_have_attribute("title", soll["text"])
    expect(marke).to_have_attribute("aria-label", soll["text"])
    expect(zeile(seite, v)).to_have_attribute("data-verdacht", soll["grund"])
    expect(zeile(seite, ok).get_by_test_id("verdacht")).to_have_count(0)
    assert zeile(seite, ok).get_attribute("data-verdacht") is None
    zeile(seite, v).locator('[data-feld="betrag"]').click()
    expect(tid(seite, "verdacht-erklaerung")).to_have_text(soll["text"])
    tid(seite, "buchung-bestaetigen").click()
    warte_bis(lambda: api.buchung_lesen(v)["status"] == "bestaetigt")
    expect(zeile(seite, v).get_by_test_id("verdacht")).to_have_count(0)


# ------------------------------------------------------------------ 37.11 Tastaturkürzel


def test_kuerzel_aktionen_und_vortasten(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["einfach"]).locator('[data-feld="betrag"]').click()
    seite.keyboard.press("k")
    expect(tid(seite, "kategorie-auswahl")).to_be_visible()
    seite.keyboard.press("Escape")
    zeile(seite, b["einfach"]).locator('[data-feld="betrag"]').click()
    seite.keyboard.press("s")
    expect(tid(seite, "status-auswahl")).to_be_visible()
    seite.keyboard.press("Escape")
    zeile(seite, b["einfach"]).locator('[data-feld="betrag"]').click()
    seite.keyboard.press("f")
    h = tid(seite, "kuerzel-hinweis")
    expect(h).to_be_visible()
    expect(h).to_have_attribute("role", "status")
    expect(h).to_have_attribute("data-vortaste", "f")
    seite.keyboard.press("Escape")
    expect(h).to_be_hidden()
    seite.keyboard.press("f")
    seite.keyboard.press("a")   # ab M30: `f a` Ausdrucksfeld, die Kürzel der Einzelfelder entfallen (39.2, E-271)
    expect(tid(seite, "filter-ausdruck")).to_be_focused()
    seite.keyboard.press("Escape")
    # der Fokus wandert erst nach dem Schließen des Vorschlagsfelds zurück: warten statt sofort prüfen
    m8.warte_bis(lambda: seite.evaluate(
        "() => !!document.activeElement.closest('[data-testid=\"buchungsliste\"]')"),
        text="Esc im Filterfeld setzt den Fokus zurück in die Liste")
    seite.keyboard.press("v")
    expect(tid(seite, "kuerzel-hinweis")).to_have_attribute("data-vortaste", "v")
    seite.keyboard.press("g")
    warte(seite, lambda: m28.abfrage(seite).get("gruppierung") == ["datum"], text="v g gruppiert")
    seite.keyboard.press("b")
    seite.keyboard.press("q")    # unbelegte zweite Taste: Meldung, Abbruch
    expect(tid(seite, "kuerzel-hinweis")).to_be_hidden()
    seite.keyboard.press("?")
    hilfe = tid(seite, "tastatur-hilfe")
    expect(hilfe).to_be_visible()
    for t in ("tastatur-hilfe-aktionen", "tastatur-hilfe-filter", "tastatur-hilfe-ansicht"):
        expect(tid(seite, t)).to_be_visible()
    assert "Alt+8" not in hilfe.inner_text(), "37.14 C4: Alt+1 … Alt+7"


def test_kuerzel_b_bestaetigt(starte_server, neue_seite):
    server, api, seite, k, b = _start(starte_server, neue_seite)
    warte_liste(seite, _liste(api, k["giro"]))
    zeile(seite, b["doppelt"]).locator('[data-feld="betrag"]').click()
    seite.keyboard.press("b")
    warte_bis(lambda: api.buchung_lesen(b["doppelt"])["status"] == "bestaetigt", text="per b bestätigt")


# ------------------------------------------------------------------ 37.12.7 Listenbreite


JS_BEREICH = """el => { let e = el.parentElement;
  while (e && e !== document.body && !['auto', 'scroll'].includes(getComputedStyle(e).overflowX)) e = e.parentElement;
  const b = (e && e !== document.body ? e : el).getBoundingClientRect(); return [b.left, b.right]; }"""


def test_listenbreite_bei_langem_zweck(starte_server, neue_seite):
    """37.12.7 (W-014, E-257): die Liste wächst nicht nach dem längsten Inhalt (gleiche Breite mit und ohne
    300 Zeichen langen Zweck); ihr Bereich (Liste bzw. waagerechter Scrollbereich, 32.1) liegt nicht unter dem
    Panel Einzelheiten."""
    server = starte_server()
    api = server.api
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    kurz = api.buchung("2024-05-01", [(g, -300), (leb, 300)], verwendungszweck="Kurz")["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, [kurz])
    ohne = tid(seite, "buchungsliste").bounding_box()["width"]
    lang = api.buchung("2024-05-02", [(g, -300), (leb, 300)], verwendungszweck="Langer Zweck " + "x" * 287)["id"]
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, [lang, kurz])
    mit = tid(seite, "buchungsliste").bounding_box()["width"]
    assert abs(mit - ohne) <= 1, f"Liste wächst mit dem Inhalt: {ohne} → {mit}"
    links, rechts = tid(seite, "buchungsliste").evaluate(JS_BEREICH)
    details = tid(seite, "panel-details").bounding_box()
    assert rechts <= details["x"] + 1, (links, rechts, details)
