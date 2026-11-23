"""M30: Oberfläche – Ausdrucksfeld, Filter im Kontoblatt, Regelliste, Regeleditor mit Testbereich, Fenster „Regel
anwenden“, Tag-Dialog (oberflaeche.md 39; E-268, E-274).

Playwright wie M8 (E-139), nur Desktop, nicht kern. Geprüft wird nur, was die Definition nennt: ``data-testid``,
genannte Attribute und wörtlich genannte Texte; Wirkungen über REST. Die App läuft im Mock-Modus mit der Uhr
2024-12-31 (``m8.HEUTE``), das ist der Bezugstag relativer Datumsangaben.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.hilfen import m8, m30
from tests.hilfen.m8 import oeffnen, strg, tid, warte_bis, warte_liste, zeile

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect
HEUTE = m8.HEUTE
REWE = '"REWE" in empfänger'


def _daten(api) -> dict:
    """Zwei Konten, Kategorien, Tags, Empfänger und Buchungen um den Bezugstag 2024-12-31."""
    k = {"giro": api.konto("Girokonto")["id"], "leb": api.konto("Lebensmittel", "aufwand")["id"],
         "wohnen": api.konto("Wohnen", "aufwand")["id"], "offen": api.konto("Offen", "eigenkapital")["id"]}
    t = {n: api.tag(n)["id"] for n in ("Steuer", "Urlaub")}
    e = {n: api.empfaenger(n)["id"] for n in ("REWE Markt GmbH", "EDEKA")}
    g = k["giro"]
    b = {
        "rewe_neu": api.buchung("2024-12-30", [(g, -2550), (k["offen"], 2550)], empfaenger_id=e["REWE Markt GmbH"],
                                verwendungszweck="Einkauf", status="importiert")["id"],
        "rewe_leb": api.buchung("2024-12-12", [(g, -3500), (k["leb"], 3500)], empfaenger_id=e["REWE Markt GmbH"],
                                verwendungszweck="Getränke", tag_ids=[t["Urlaub"]])["id"],
        "rewe_wohnen": api.buchung("2024-11-20", [(g, -1500), (k["wohnen"], 1500)],
                                   empfaenger_id=e["REWE Markt GmbH"], verwendungszweck="Putzmittel")["id"],
        "edeka": api.buchung("2024-12-05", [(g, -2000), (k["leb"], 2000)], empfaenger_id=e["EDEKA"],
                             verwendungszweck="Brot", tag_ids=[t["Steuer"], t["Urlaub"]])["id"],
        "miete": api.buchung("2024-11-01", [(g, -80000), (k["wohnen"], 80000)], verwendungszweck="Miete")["id"],
        "alt": api.buchung("2023-06-15", [(g, -900), (k["offen"], 900)], empfaenger_id=e["REWE Markt GmbH"],
                           verwendungszweck="Altfall", status="importiert")["id"],
    }
    return {"k": k, "t": t, "e": e, "b": b}


@pytest.fixture
def start(starte_server, neue_seite):
    def starte(pfad: str | None = None, seitenname: str = "konto"):
        server = starte_server()
        d = _daten(server.api)
        seite = neue_seite(server)
        oeffnen(seite, server, pfad or f"/konten/{d['k']['giro']}", seitenname=seitenname)
        return server, server.api, seite, d
    return starte


def _rest(api, konto_id, ausdruck=None):
    p = {"filter": ausdruck, "stichtag": HEUTE} if ausdruck else {}
    return m8.rest_liste(api, konto_id, **p)


def _abfrage(seite) -> dict:
    return parse_qs(urlsplit(seite.url).query)


def _wert(locator) -> str:
    return locator.evaluate("e => 'value' in e ? e.value : e.textContent")


def _status(seite, kennung: str, status: str) -> None:
    expect(tid(seite, f"{kennung}-status")).to_have_attribute("data-status", status)


# ------------------------------------------------------------------ 39.1/39.2 Filter im Kontoblatt
def test_filterfeld_filtert_liste_und_adresse(start):
    server, api, seite, d = start()
    giro = d["k"]["giro"]
    warte_liste(seite, _rest(api, giro))
    feld = tid(seite, "filter-ausdruck")
    expect(feld).to_be_visible()
    _status(seite, "filter-ausdruck", "leer")
    expect(tid(seite, "filter-leiste")).to_be_hidden()
    expect(tid(seite, m8.FILTER_UMSCHALTER)).to_have_attribute("aria-expanded", "false")
    m8.filter_aktiv(seite, False)
    ausdruck = '"rewe" in empfänger and betrag > 20'
    a0 = m8.max_aenderung(api)
    m8.filter_ausdruck_setzen(seite, ausdruck)
    soll = _rest(api, giro, ausdruck)
    assert set(soll) == {d["b"]["rewe_neu"], d["b"]["rewe_leb"]}
    warte_liste(seite, soll)
    expect(feld).not_to_have_attribute("aria-invalid", "true")
    warte_bis(lambda: _abfrage(seite).get("filter") == [ausdruck], text="filter= in der Adresse")
    expect(tid(seite, "filter-zusammenfassung")).to_be_visible()
    expect(tid(seite, "filter-zusammenfassung")).to_contain_text("2")   # Zahl der Buchungen
    m8.filter_aktiv(seite)
    assert m8.max_aenderung(api) == a0, "Filtern ist ein Lesezugriff"
    # Neuladen behält den Filter aus der Adresse
    seite.reload()
    m8.warte_geladen(seite, "konto")
    warte_liste(seite, soll)
    assert "rewe" in m8.filter_ausdruck_wert(seite)
    # Leeren hebt ihn auf
    tid(seite, "filter-ausdruck-leeren").click()
    warte_liste(seite, _rest(api, giro))
    warte_bis(lambda: "filter" not in _abfrage(seite), text="Adresse ohne Filter")
    _status(seite, "filter-ausdruck", "leer")
    assert m8.filter_ausdruck_wert(seite).strip() == ""


def test_filterfehler_laesst_die_letzte_liste_stehen(start):
    server, api, seite, d = start()
    giro = d["k"]["giro"]
    m8.filter_ausdruck_setzen(seite, 'empfänger == "EDEKA"')
    warte_liste(seite, [d["b"]["edeka"]])
    m8.filter_ausdruck_setzen(seite, 'empfänger = "REWE Markt GmbH"', gueltig=False)
    feld = tid(seite, "filter-ausdruck")
    expect(feld).to_have_attribute("aria-invalid", "true")
    expect(tid(seite, "filter-ausdruck-fehler")).to_be_visible()
    expect(tid(seite, "filter-ausdruck-fehler")).not_to_be_empty()
    assert m8.zellen_ids(seite) == [d["b"]["edeka"]], "die letzte gültige Liste bleibt"
    assert _abfrage(seite).get("filter") == ['empfänger == "EDEKA"']
    m8.filter_ausdruck_setzen(seite, 'empfänger == "REWE Markt GmbH"')
    warte_liste(seite, _rest(api, giro, 'empfänger == "REWE Markt GmbH"'))
    expect(feld).not_to_have_attribute("aria-invalid", "true")


def test_zeitraum_knoepfe(start):
    server, api, seite, d = start()
    giro = d["k"]["giro"]
    for wert in ("heute", "-7d", "-30d", "dieser_monat", "letzter_monat", "dieses_jahr", "letztes_jahr"):
        expect(tid(seite, f"filter-schnell-{wert}")).to_be_visible()
    tid(seite, "filter-schnell-dieser_monat").click()
    soll = _rest(api, giro, "datum in dieser_monat")
    assert set(soll) == {d["b"]["rewe_neu"], d["b"]["rewe_leb"], d["b"]["edeka"]}
    warte_liste(seite, soll)
    warte_bis(lambda: "dieser_monat" in m8.filter_ausdruck_wert(seite) and "datum" in m8.filter_ausdruck_wert(seite),
              text="Zeitraum im Ausdruck")
    # ein weiterer Zeitraum ersetzt den vorhandenen datum-Teil
    tid(seite, "filter-schnell-letzter_monat").click()
    warte_liste(seite, _rest(api, giro, "datum in letzter_monat"))
    wert = m8.filter_ausdruck_wert(seite)
    assert "letzter_monat" in wert and "dieser_monat" not in wert
    # an einen anderen Ausdruck wird der Zeitraum mit and angehängt
    m8.filter_ausdruck_setzen(seite, REWE)
    tid(seite, "filter-schnell-dieses_jahr").click()
    soll = _rest(api, giro, f"{REWE} and datum in dieses_jahr")
    assert d["b"]["alt"] not in soll and len(soll) == 3
    warte_liste(seite, soll)
    wert = m8.filter_ausdruck_wert(seite)
    assert "REWE" in wert and " and " in wert and "dieses_jahr" in wert
    warte_bis(lambda: "dieses_jahr" in (_abfrage(seite).get("filter") or [""])[0], text="Adresse folgt")


def test_baukasten_einklappen_und_kopplung(start):
    server, api, seite, d = start()
    knopf, leiste = tid(seite, m8.FILTER_UMSCHALTER), tid(seite, "filter-leiste")
    expect(leiste).to_be_hidden()
    knopf.click()
    expect(leiste).to_be_visible()
    expect(tid(seite, "filter-baukasten")).to_be_visible()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    m8.filter_ausdruck_setzen(seite, "betrag > 20")
    warte_liste(seite, _rest(api, d["k"]["giro"], "betrag > 20"))
    # der Ausdruck schreibt den Baukasten: eine Zeile mit Feld, Operator, Wert und Entfernen
    for teil in ("feld", "op", "wert", "weg"):
        expect(tid(seite, "filter-baukasten").locator(f'[data-testid^="bk-"][data-testid$="-{teil}"]').first
               ).to_be_visible()
    expect(tid(seite, "filter-baukasten-hinweis")).to_be_hidden()
    # der Baukasten schreibt den Ausdruck: Zeile entfernen leert den Filter
    tid(seite, "filter-baukasten").locator('[data-testid^="bk-"][data-testid$="-weg"]').first.click()
    warte_liste(seite, _rest(api, d["k"]["giro"]))
    warte_bis(lambda: "betrag" not in m8.filter_ausdruck_wert(seite), text="Ausdruck folgt dem Baukasten")
    # Hinweis, wenn der Ausdruck nicht in den Baukasten passt (Maßstab: baukasten_faehig des Prüfens)
    schwer = 'empfänger.startswith("RE", case=True) or betrag > 20 and not (letzter_tag or monatstag == 1)'
    p = m30.pruefen(api, schwer, "filter", stichtag=HEUTE)
    assert p["gueltig"] is True
    m8.filter_ausdruck_setzen(seite, schwer)
    if p["baukasten_faehig"]:
        expect(tid(seite, "filter-baukasten-hinweis")).to_be_hidden()
    else:
        expect(tid(seite, "filter-baukasten-hinweis")).to_be_visible()
    for teil in ("startswith", "case=True", "betrag > 20", "letzter_tag", "monatstag == 1"):
        assert teil in m8.filter_ausdruck_wert(seite), f"es gehen keine Teile verloren: {teil}"
    knopf.click()
    expect(leiste).to_be_hidden()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    # Zurücksetzen entfernt alle Filter
    m8.filter_zuruecksetzen(seite)
    warte_liste(seite, _rest(api, d["k"]["giro"]))
    m8.filter_aktiv(seite, False)


def test_alte_adresse_ohne_entsprechung_bleibt_sichtbar(start):
    server, api, seite, d = start()
    giro = d["k"]["giro"]
    oeffnen(seite, server, f"/konten/{giro}?betrag_max=-3000&status=bestaetigt", seitenname="konto")
    soll = m8.rest_liste(api, giro, betrag_max=-3000, status="bestaetigt")
    assert set(soll) == {d["b"]["rewe_leb"], d["b"]["miete"]}
    warte_liste(seite, soll)
    expect(tid(seite, "filter-alt-betrag_max")).to_be_visible()
    warte_bis(lambda: "bestaetigt" in m8.filter_ausdruck_wert(seite), text="status im Ausdruck")
    assert "betrag" not in m8.filter_ausdruck_wert(seite)
    m8.filter_zuruecksetzen(seite)
    warte_liste(seite, _rest(api, giro))
    expect(tid(seite, "filter-alt-betrag_max")).to_have_count(0)


def test_als_regel_speichern_oeffnet_den_regeleditor(start):
    server, api, seite, d = start()
    m8.filter_ausdruck_setzen(seite, f"{REWE} and datum in dieses_jahr")
    soll = m30.pruefen(api, api.post("/api/ausdruck/als-regel", json={
        "ausdruck": f"{REWE} and datum in dieses_jahr"}, erwartet=200).daten["ausdruck"], "regel")["kanonisch"]
    assert soll == REWE
    tid(seite, "filter-ausdruck-menue").click()
    seite.get_by_text("Als Regel speichern").first.click()
    # die Rückfrage nennt die Teile, die nicht übernommen werden (hier der Zeitraum); nach Bestätigung der Editor
    warte_bis(lambda: tid(seite, "bestaetigen-ja").is_visible() or tid(seite, "regel-dialog").is_visible(),
              text="Rückfrage oder Regeleditor")
    if tid(seite, "bestaetigen-ja").is_visible():
        tid(seite, "bestaetigen-ja").click()
    expect(tid(seite, "regel-dialog")).to_be_visible()
    warte_bis(lambda: "REWE" in _wert(tid(seite, "regel-ausdruck")), text="Regel-Ausdruck im Editor")
    assert "dieses_jahr" not in _wert(tid(seite, "regel-ausdruck"))
    assert api.get("/api/regeln", erwartet=200).daten == [], "noch nichts gespeichert"


# ------------------------------------------------------------------ 39.3 Regelliste
def _regeln(api):
    return api.get("/api/regeln", erwartet=200).daten


def test_regelliste(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    d = _daten(api)
    k, t = d["k"], d["t"]
    weg = api.tag("Wegwerf")["id"]
    beide = m30.regel(api, "Beides", kategorie_id=k["leb"], ausdruck="empf=='EDEKA'", tag_ids=[t["Urlaub"]])
    nur = m30.regel(api, "Nur Tag", ausdruck=REWE, tag_ids=[t["Steuer"], t["Urlaub"]])
    leer = m30.regel(api, "Leer", ausdruck="betrag > 500", tag_ids=[weg])
    api.delete(f"/api/tags/{weg}", erwartet=204)
    seite = neue_seite(server)
    oeffnen(seite, server, "/regeln", seitenname="regeln")
    expect(tid(seite, "regel-anlegen")).to_be_visible()
    expect(tid(seite, "regeln-anwenden")).to_be_visible()
    for r in (beide, nur, leer):
        for teil in ("regel-{}", "regel-griff-{}", "regel-aktiv-{}", "regel-ziel-{}", "regel-ausdruck-{}"):
            expect(tid(seite, teil.format(r["id"]))).to_be_visible()
        expect(tid(seite, f"regel-{r['id']}")).to_contain_text(r["name"])
    expect(tid(seite, f"regel-ausdruck-{beide['id']}")).to_contain_text('empfänger == "EDEKA"')
    expect(tid(seite, f"regel-ziel-{beide['id']}")).to_contain_text("Lebensmittel")
    expect(tid(seite, f"regel-ziel-{beide['id']}")).to_contain_text("+ Urlaub")
    expect(tid(seite, f"regel-ziel-{nur['id']}")).to_contain_text("+ Steuer")
    expect(tid(seite, f"regel-ziel-{nur['id']}")).to_contain_text("+ Urlaub")
    expect(tid(seite, f"regel-ziel-{leer['id']}")).to_contain_text("(keine Aktion)")
    reihen = seite.locator('[data-testid^="regel-griff-"]').evaluate_all(
        "els => els.map(e => Number(e.getAttribute('data-testid').slice('regel-griff-'.length)))")
    assert reihen == [beide["id"], nur["id"], leer["id"]]
    # Schalter
    tid(seite, f"regel-aktiv-{nur['id']}").click()
    warte_bis(lambda: next(r for r in _regeln(api) if r["id"] == nur["id"])["aktiv"] is False, text="Regel inaktiv")
    # Reihenfolge mit Alt+↑ am Griff: ein Rückgängig-Schritt
    a0 = m8.max_aenderung(api)
    tid(seite, f"regel-griff-{leer['id']}").focus()
    seite.keyboard.press("Alt+ArrowUp")
    warte_bis(lambda: [r["id"] for r in _regeln(api)] == [beide["id"], leer["id"], nur["id"]], text="umsortiert")
    assert [r["prioritaet"] for r in _regeln(api)] == [10, 20, 30]
    assert [a["aktion"] for a in m8.aenderungen_seit(api, a0)] == ["regeln_reihenfolge"]
    tid(seite, "rueckgaengig-knopf").click()
    warte_bis(lambda: [r["id"] for r in _regeln(api)] == [beide["id"], nur["id"], leer["id"]], text="zurück")


# ------------------------------------------------------------------ 39.4 Regeleditor
def _editor_oeffnen(start):
    server, api, seite, d = start("/regeln", "regeln")
    tid(seite, "regel-anlegen").click()
    expect(tid(seite, "regel-dialog")).to_be_visible()
    return server, api, seite, d


def _ausdruck(seite, text: str, status: str = "ok") -> None:
    tid(seite, "regel-ausdruck").fill(text)
    _status(seite, "regel-ausdruck", status)


def test_regeleditor_elemente_und_fehler(start):
    server, api, seite, d = _editor_oeffnen(start)
    for teil in ("regel-name", "regel-aktiv", "regel-modus-baukasten", "regel-modus-ausdruck", "regel-ausdruck",
                 "regel-kategorie", "regel-tag-eingabe", "regel-tag-hinzufuegen", "regel-tags", "regel-speichern",
                 "regel-speichern-anwenden", "regel-test"):
        expect(tid(seite, teil)).to_be_visible()
    kategorie = tid(seite, "regel-kategorie")
    werte = kategorie.locator("option").evaluate_all("els => els.map(e => e.value)")
    assert werte[0] == "", "erster Eintrag „– keine Kategorie –“ mit leerem Wert"
    assert kategorie.input_value() != "", "bei einer neuen Regel ist die erste Kategorie vorgewählt"
    assert kategorie.input_value() == werte[1]
    # Kontext regel: Datumsangaben sind ein Fehler mit Fehlerzeile
    _ausdruck(seite, "datum == heute", "fehler")
    expect(tid(seite, "regel-ausdruck")).to_have_attribute("aria-invalid", "true")
    expect(tid(seite, "regel-ausdruck-fehler")).not_to_be_empty()
    _ausdruck(seite, REWE)
    expect(tid(seite, "regel-ausdruck")).not_to_have_attribute("aria-invalid", "true")
    # ohne Kategorie und ohne Tags
    kategorie.select_option("")
    tid(seite, "regel-speichern").click()
    expect(tid(seite, "regel-dialog")).to_contain_text("Die Regel braucht eine Kategorie oder mindestens einen Tag.")
    expect(tid(seite, "regel-dialog")).to_be_visible()
    assert _regeln(api) == []


def test_regeleditor_tags_und_namensvorschlag(start):
    server, api, seite, d = _editor_oeffnen(start)
    t = d["t"]
    _ausdruck(seite, '"Einkauf" in verwendungszweck')
    tid(seite, "regel-kategorie").select_option("")
    eingabe = tid(seite, "regel-tag-eingabe")
    eingabe.fill("urlaub")            # vorhandener Tag, unabhängig von der Schreibung
    eingabe.press("Enter")
    expect(tid(seite, "regel-tag-entfernen-Urlaub")).to_be_visible()
    expect(tid(seite, "regel-tags")).to_contain_text("Urlaub")
    expect(tid(seite, "regel-tags")).not_to_contain_text("(neu)")
    eingabe.fill("URLAUB")            # ein Name kommt nur einmal vor
    tid(seite, "regel-tag-hinzufuegen").click()
    expect(tid(seite, "regel-tags").locator('[data-testid^="regel-tag-entfernen-"]')).to_have_count(1)
    eingabe.fill("Neu 2026")
    tid(seite, "regel-tag-hinzufuegen").click()
    expect(tid(seite, "regel-tag-entfernen-Neu 2026")).to_be_visible()
    expect(tid(seite, "regel-tags")).to_contain_text("(neu)")
    eingabe.fill("Steuer")
    eingabe.press("Enter")
    tid(seite, "regel-tag-entfernen-Steuer").click()
    expect(tid(seite, "regel-tag-entfernen-Steuer")).to_have_count(0)
    assert {x["name"] for x in api.get("/api/tags", erwartet=200).daten} == set(t), "neue Tags erst beim Speichern"
    # leerer Name: Vorschlag als Platzhalter aus dem ersten Text der Bedingung und den Tags mit #
    name = tid(seite, "regel-name")
    assert name.input_value() == ""
    warte_bis(lambda: "Einkauf" in (name.get_attribute("placeholder") or ""), text="Namensvorschlag")
    vorschlag = name.get_attribute("placeholder")
    assert "#Urlaub" in vorschlag and "→" in vorschlag
    a0 = m8.max_aenderung(api)
    tid(seite, "regel-speichern").click()
    expect(tid(seite, "regel-dialog")).to_have_count(0)
    (r,) = warte_bis(lambda: _regeln(api), text="Regel gespeichert")
    tags = {x["name"]: x["id"] for x in api.get("/api/tags", erwartet=200).daten}
    assert r["name"] == vorschlag and r["kategorie_id"] is None
    assert r["tag_ids"] == sorted([tags["Urlaub"], tags["Neu 2026"]])
    assert r["ausdruck"] == '"Einkauf" in verwendungszweck' and r["ausdruck_form"] == "ausdruck"
    expect(tid(seite, f"regel-ziel-{r['id']}")).to_contain_text("+ Neu 2026")
    assert {a["aktion"] for a in m8.aenderungen_seit(api, a0)} <= {"tag_anlegen", "regel_anlegen"}
    # neuer Tag und Regel sind ein Rückgängig-Schritt
    tid(seite, "rueckgaengig-knopf").click()
    warte_bis(lambda: _regeln(api) == [] and "Neu 2026" not in {
        x["name"] for x in api.get("/api/tags", erwartet=200).daten}, text="Regel und neuer Tag zurückgenommen")


def test_regeleditor_abbrechen_legt_nichts_an(start):
    server, api, seite, d = _editor_oeffnen(start)
    a0 = m8.max_aenderung(api)
    _ausdruck(seite, REWE)
    tid(seite, "regel-tag-eingabe").fill("Nie angelegt")
    tid(seite, "regel-tag-eingabe").press("Enter")
    expect(tid(seite, "regel-tags")).to_contain_text("(neu)")
    seite.keyboard.press("Escape")
    if tid(seite, "regel-dialog").count():        # Esc im Eingabefeld darf zuerst nur das Feld verlassen
        seite.keyboard.press("Escape")
    expect(tid(seite, "regel-dialog")).to_have_count(0)
    assert _regeln(api) == [] and m8.max_aenderung(api) == a0
    assert "Nie angelegt" not in {x["name"] for x in api.get("/api/tags", erwartet=200).daten}


# ------------------------------------------------------------------ 39.5 Testbereich und Fenster „Regel anwenden“
def _test_geladen(seite) -> None:
    expect(tid(seite, "regel-test")).to_have_attribute("data-geladen", "ja")
    expect(tid(seite, "regel-test")).to_have_attribute("data-veraltet", "nein")


def test_testbereich(start):
    server, api, seite, d = _editor_oeffnen(start)
    k, b = d["k"], d["b"]
    a0 = m8.max_aenderung(api)
    expect(tid(seite, "regel-test-konto")).to_be_visible()
    expect(tid(seite, "test-zeitraum-12m")).to_have_attribute("aria-pressed", "true")
    for z in ("jahr", "vorjahr", "alle"):
        expect(tid(seite, f"test-zeitraum-{z}")).to_have_attribute("aria-pressed", "false")
    _ausdruck(seite, REWE)
    tid(seite, "regel-kategorie").select_option(str(k["leb"]))
    _test_geladen(seite)
    koerper = {"ausdruck": REWE, "kategorie_id": k["leb"], "stichtag": HEUTE}
    soll = api.post("/api/regeln/test", json=koerper, erwartet=200).daten      # Vorgabe: 12 Monate
    assert {x["buchung_id"]: x["wirkung"] for x in soll["treffer"]} == {
        b["rewe_neu"]: "neu", b["rewe_leb"]: "bereits_so", b["rewe_wohnen"]: "abweichend"}
    zahlen = tid(seite, "test-zahlen")
    expect(zahlen).to_have_attribute("data-anzahl", "3")
    expect(zahlen).to_contain_text(f"3 Treffer in {soll['testmenge_anzahl']} Buchungen")
    for bid in (b["rewe_neu"], b["rewe_leb"], b["rewe_wohnen"]):
        expect(tid(seite, f"test-treffer-{bid}")).to_be_visible()
        expect(tid(seite, f"test-zeile-{bid}")).to_be_visible()
    expect(tid(seite, f"test-treffer-{b['alt']}")).to_have_count(0)
    for wirkung, n in (("neu", 1), ("abweichend", 1), ("bereits_so", 1), ("alle", 3)):
        expect(tid(seite, f"test-wirkung-{wirkung}")).to_have_attribute("data-anzahl", str(n))
    expect(tid(seite, "test-nicht-erfasst")).to_be_visible()          # edeka hat die Kategorie, trifft aber nicht
    # Einschränkung auf eine Wirkung
    tid(seite, "test-wirkung-neu").click()
    expect(tid(seite, "test-liste").locator('[data-testid^="test-treffer-"]')).to_have_count(1)
    tid(seite, "test-wirkung-alle").click()
    expect(tid(seite, "test-liste").locator('[data-testid^="test-treffer-"]')).to_have_count(3)
    # Einzelheiten einer Trefferzeile
    tid(seite, f"test-zeile-{b['rewe_wohnen']}").click()
    expect(tid(seite, f"test-warum-{b['rewe_wohnen']}")).to_be_visible()
    expect(tid(seite, f"test-uebernehmen-{b['rewe_wohnen']}")).to_be_visible()
    expect(tid(seite, f"test-treffer-{b['rewe_wohnen']}")).to_contain_text("Putzmittel")
    # Zeitraum „alle“
    tid(seite, "test-zeitraum-alle").click()
    expect(tid(seite, "test-zeitraum-alle")).to_have_attribute("aria-pressed", "true")
    expect(tid(seite, "test-zeitraum-12m")).to_have_attribute("aria-pressed", "false")
    expect(zahlen).to_have_attribute("data-anzahl", "4")
    expect(tid(seite, f"test-treffer-{b['alt']}")).to_be_visible()
    # Tags: data-tags zählt die Treffer, die Tags erhielten
    tid(seite, "regel-tag-eingabe").fill("Urlaub")
    tid(seite, "regel-tag-eingabe").press("Enter")
    expect(zahlen).to_have_attribute("data-tags", "3")                # rewe_leb trägt den Tag schon
    # ungültige Bedingung: das letzte gültige Ergebnis bleibt als veraltet stehen
    _ausdruck(seite, '"REWE" in', "fehler")
    expect(tid(seite, "regel-test")).to_have_attribute("data-veraltet", "ja")
    expect(tid(seite, f"test-treffer-{b['rewe_neu']}")).to_be_visible()
    _ausdruck(seite, '"EDEKA" in empfänger')
    _test_geladen(seite)
    expect(zahlen).to_have_attribute("data-anzahl", "1")
    # ohne Kategorie läuft der Test und zeigt die Treffer
    tid(seite, "regel-kategorie").select_option("")
    _test_geladen(seite)
    expect(tid(seite, f"test-treffer-{b['edeka']}")).to_be_visible()
    assert m8.max_aenderung(api) == a0 and _regeln(api) == [], "der Test ändert nichts"


def test_testbereich_ohne_bedingung_und_uebernehmen(start):
    server, api, seite, d = _editor_oeffnen(start)
    b = d["b"]
    _test_geladen(seite)
    # ohne Bedingung: die Buchungen des Zeitraums (12 Monate vor dem 31.12.2024: ohne die Buchung von 2023)
    for name in ("rewe_neu", "rewe_leb", "rewe_wohnen", "edeka", "miete"):
        expect(tid(seite, f"test-treffer-{b[name]}")).to_be_visible()
    expect(tid(seite, f"test-treffer-{b['alt']}")).to_have_count(0)
    tid(seite, f"test-zeile-{b['edeka']}").click()
    tid(seite, f"test-uebernehmen-{b['edeka']}").click()
    warte_bis(lambda: "EDEKA" in _wert(tid(seite, "regel-ausdruck")), text="Bedingung übernommen")
    _status(seite, "regel-ausdruck", "ok")
    p = m30.gueltig(api, _wert(tid(seite, "regel-ausdruck")), "regel")
    assert p["kanonisch"] == 'empfänger == "EDEKA" and richtung == "ausgabe"'


def test_anwenden_fenster(start):
    server, api, seite, d = _editor_oeffnen(start)
    k, b, t = d["k"], d["b"], d["t"]
    _ausdruck(seite, REWE)
    tid(seite, "regel-kategorie").select_option(str(k["leb"]))
    tid(seite, "regel-tag-eingabe").fill("Steuer")
    tid(seite, "regel-tag-eingabe").press("Enter")
    tid(seite, "regel-name").fill("Rewe")
    _test_geladen(seite)
    knopf = tid(seite, "regel-test-anwenden")
    expect(knopf).to_be_enabled()
    expect(knopf).to_contain_text("1 × Kategorie")       # „Anwenden: n × Kategorie, m × Tags…“
    expect(knopf).to_contain_text("3 × Tags")
    a0 = m8.max_aenderung(api)
    knopf.click()
    dlg = tid(seite, "regel-anwenden-dialog")
    expect(dlg).to_be_visible()
    (r,) = warte_bis(lambda: _regeln(api), text="Anwenden speichert die neue Regel zuerst")
    assert (r["name"], r["kategorie_id"], r["tag_ids"], r["ausdruck"]) == ("Rewe", k["leb"], [t["Steuer"]], REWE)
    assert api.buchung_lesen(b["rewe_neu"])["vorschlag"] is None, "noch nicht angewendet"
    umfang = tid(seite, "regel-anwenden-umfang")
    expect(umfang).to_contain_text("Zeitraum")
    expect(umfang).to_contain_text("12 Monate")
    expect(tid(seite, "regel-anwenden-kategorie")).to_contain_text("Lebensmittel")
    expect(tid(seite, "regel-anwenden-kategorie")).to_contain_text("1")
    expect(tid(seite, "regel-anwenden-abweichende")).to_be_visible()
    expect(tid(seite, "regel-anwenden-tags")).to_contain_text("Steuer")
    expect(tid(seite, "regel-anwenden-tags")).to_contain_text("3")
    expect(tid(seite, "regel-anwenden-nichts")).to_be_hidden()
    text = dlg.inner_text()
    assert "null" not in text and "datum in" not in text and "-12m" not in text, text
    tid(seite, "regel-anwenden-ok").click()
    warte_bis(lambda: api.buchung_lesen(b["rewe_neu"])["vorschlag"] is not None, text="angewendet")
    neu = api.buchung_lesen(b["rewe_neu"])
    assert neu["kategorie_id"] == k["leb"] and neu["vorschlag"]["regel_id"] == r["id"]
    assert api.buchung_lesen(b["rewe_wohnen"])["kategorie_id"] == k["wohnen"], "abweichende nur mit Ankreuzen"
    for name in ("rewe_neu", "rewe_leb", "rewe_wohnen"):
        assert t["Steuer"] in m30.tags_von(api, b[name]), name
    assert m30.tags_von(api, b["alt"]) == set(), "außerhalb der 12 Monate"
    aktionen = [a["aktion"] for a in m8.aenderungen_seit(api, a0)]
    assert aktionen.count("regeln_anwenden") == 1 and aktionen.count("regel_anlegen") == 1
    expect(tid(seite, "meldungen")).to_contain_text("3")             # Zahl der geänderten Buchungen


def test_anwenden_fenster_nur_tags_und_abweichende(start):
    server, api, seite, d = start("/regeln", "regeln")
    k, b, t = d["k"], d["b"], d["t"]
    nur = m30.regel(api, "Nur Tag", ausdruck='"EDEKA" in empfänger or "Miete" in verwendungszweck',
                    tag_ids=[t["Steuer"]])
    kat = m30.regel(api, "Kategorie", ausdruck=REWE, kategorie_id=k["leb"])
    seite.reload()
    m8.warte_geladen(seite, "regeln")
    # Regel nur mit Tags: „keine Kategorie“ vorgewählt, keine Kategorie-Zeile, kein Ankreuzfeld
    tid(seite, f"regel-{nur['id']}").get_by_role("button", name=re.compile("Bearbeiten")).click()
    expect(tid(seite, "regel-dialog")).to_be_visible()
    assert tid(seite, "regel-kategorie").input_value() == ""
    _test_geladen(seite)
    expect(tid(seite, "test-zahlen")).to_have_attribute("data-anzahl", "2")
    expect(tid(seite, "test-zahlen")).to_have_attribute("data-tags", "1")      # edeka trägt den Tag schon
    expect(tid(seite, "regel-test-anwenden")).to_contain_text("Tags an 1 Buchung")
    tid(seite, "regel-test-anwenden").click()
    expect(tid(seite, "regel-anwenden-dialog")).to_be_visible()
    expect(tid(seite, "regel-anwenden-kategorie")).to_have_count(0)
    expect(tid(seite, "regel-anwenden-abweichende")).to_have_count(0)
    expect(tid(seite, "regel-anwenden-tags")).to_contain_text("Steuer")
    tid(seite, "regel-anwenden-ok").click()
    warte_bis(lambda: t["Steuer"] in m30.tags_von(api, b["miete"]), text="Tag vergeben")
    # Regel mit Kategorie, ohne Tags: mit Ankreuzen auch die abweichende Buchung
    oeffnen(seite, server, "/regeln", seitenname="regeln")
    tid(seite, f"regel-{kat['id']}").get_by_role("button", name=re.compile("Bearbeiten")).click()
    expect(tid(seite, "regel-dialog")).to_be_visible()
    _test_geladen(seite)
    expect(tid(seite, "regel-test-anwenden")).to_contain_text("Auf 1 Buchung")
    tid(seite, "regel-test-anwenden").click()
    expect(tid(seite, "regel-anwenden-tags")).to_have_count(0)
    expect(tid(seite, "regel-anwenden-abweichende")).to_be_visible()
    haken = tid(seite, "regel-anwenden-abweichende")
    (haken if haken.evaluate("e => e.tagName") == "INPUT" else haken.locator("input")).check()
    tid(seite, "regel-anwenden-ok").click()
    warte_bis(lambda: api.buchung_lesen(b["rewe_wohnen"])["kategorie_id"] == k["leb"], text="überschrieben")
    assert api.buchung_lesen(b["rewe_neu"])["kategorie_id"] == k["leb"]
    # danach würde sich nichts mehr ändern: der Anwenden-Knopf ist gesperrt
    oeffnen(seite, server, "/regeln", seitenname="regeln")
    tid(seite, f"regel-{kat['id']}").get_by_role("button", name=re.compile("Bearbeiten")).click()
    _test_geladen(seite)
    expect(tid(seite, "regel-test-anwenden")).to_be_disabled()


# ------------------------------------------------------------------ 39.7 Tag-Dialog im Kontoblatt
def _tag_dialog(seite, *bids):
    zeile(seite, bids[0]).click()
    for bid in bids[1:]:
        zeile(seite, bid).click(modifiers=[strg()])
    expect(tid(seite, "auswahl-anzahl")).to_have_attribute("data-anzahl", str(len(bids)))
    tid(seite, "mehrfach-tags").click()
    expect(tid(seite, "tag-auswahl")).to_be_visible()
    vorhanden = tid(seite, "tag-auswahl-vorhanden")
    expect(vorhanden).to_have_attribute("data-geladen", "ja")
    return vorhanden


def test_tag_dialog_zeigt_und_entfernt_vorhandene_tags(start):
    server, api, seite, d = start()
    b, t = d["b"], d["t"]
    warte_liste(seite, _rest(api, d["k"]["giro"]))
    vorhanden = _tag_dialog(seite, b["edeka"])
    knoepfe = vorhanden.locator('[data-testid^="tag-auswahl-weg-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    assert knoepfe == [f"tag-auswahl-weg-{t['Steuer']}", f"tag-auswahl-weg-{t['Urlaub']}"], "nach Namen sortiert"
    expect(vorhanden).to_contain_text("Steuer")
    expect(vorhanden).to_contain_text("Urlaub")
    a0 = m8.max_aenderung(api)
    tid(seite, f"tag-auswahl-weg-{t['Steuer']}").click()
    warte_bis(lambda: m30.tags_von(api, b["edeka"]) == {t["Urlaub"]}, text="Tag entfernt")
    (a,) = m8.aenderungen_seit(api, a0)
    assert a["aktion"] == "mehrfach_tags"
    # der Dialog bleibt offen und zeigt den neuen Stand
    expect(tid(seite, "tag-auswahl")).to_be_visible()
    expect(tid(seite, f"tag-auswahl-weg-{t['Steuer']}")).to_have_count(0)
    expect(tid(seite, f"tag-auswahl-weg-{t['Urlaub']}")).to_be_visible()
    tid(seite, f"tag-auswahl-weg-{t['Urlaub']}").click()
    warte_bis(lambda: m30.tags_von(api, b["edeka"]) == set(), text="letzter Tag entfernt")
    expect(vorhanden).to_contain_text("Noch keine Tags.")
    assert len(m8.aenderungen_seit(api, a0)) == 2, "je Entfernen ein Rückgängig-Schritt"
    # Hinzufügen verhält sich unverändert und schließt den Dialog
    tid(seite, "tag-auswahl-name").fill("Steuer")
    tid(seite, "tag-auswahl-hinzufuegen").click()
    warte_bis(lambda: m30.tags_von(api, b["edeka"]) == {t["Steuer"]}, text="Tag hinzugefügt")
    expect(tid(seite, "tag-auswahl")).to_have_count(0)


def test_tag_dialog_mehrere_buchungen(start):
    server, api, seite, d = start()
    b, t = d["b"], d["t"]
    warte_liste(seite, _rest(api, d["k"]["giro"]))
    vorhanden = _tag_dialog(seite, b["edeka"], b["rewe_leb"])
    expect(vorhanden).to_contain_text("(alle)")          # Urlaub an beiden
    expect(vorhanden).to_contain_text("(1 von 2)")       # Steuer nur an einer
    a0 = m8.max_aenderung(api)
    tid(seite, f"tag-auswahl-weg-{t['Urlaub']}").click()   # entfernt den Tag von allen gewählten Buchungen
    warte_bis(lambda: m30.tags_von(api, b["edeka"]) == {t["Steuer"]} and m30.tags_von(api, b["rewe_leb"]) == set(),
              text="Urlaub von beiden entfernt")
    (a,) = m8.aenderungen_seit(api, a0)
    assert a["aktion"] == "mehrfach_tags" and sorted(e["objekt_id"] for e in a["eintraege"]) == sorted(
        [b["edeka"], b["rewe_leb"]])
    expect(tid(seite, "tag-auswahl")).to_be_visible()
    expect(tid(seite, f"tag-auswahl-weg-{t['Urlaub']}")).to_have_count(0)
    expect(vorhanden).to_contain_text("(1 von 2)")


def test_tag_dialog_ohne_tags(start):
    server, api, seite, d = start()
    warte_liste(seite, _rest(api, d["k"]["giro"]))
    vorhanden = _tag_dialog(seite, d["b"]["miete"])
    expect(vorhanden).to_contain_text("Noch keine Tags.")
    expect(vorhanden.locator('[data-testid^="tag-auswahl-weg-"]')).to_have_count(0)
