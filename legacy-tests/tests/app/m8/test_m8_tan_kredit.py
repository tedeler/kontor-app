"""M8: TAN-Seite mit QR-Code, „QR-Code speichern“/„Teilen“, PIN-Eingabe (oberflaeche.md 14, 15.4; K 6; E-147)
und Kreditabgleich (oberflaeche.md 13.4; K 10; T 19)."""

from __future__ import annotations

import json

import pytest

from tests.hilfen import m8
from tests.hilfen.m2 import SYNC_DATEN, SYNC_DATEN_PIN
from tests.hilfen.m8 import oeffnen, tid, tippen
from tests.hilfen.m31 import einstellung_oeffnen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

TEILEN_ATTRAPPE = """
window.__geteilt = [];
Object.defineProperty(Navigator.prototype, 'canShare', {configurable: true, writable: true,
  value: function (d) { return !!(d && d.files && d.files.length); }});
Object.defineProperty(Navigator.prototype, 'share', {configurable: true, writable: true,
  value: async function (d) {
    const f = d.files[0];
    const b = new Uint8Array(await f.arrayBuffer());
    window.__geteilt.push({name: f.name, type: f.type, title: d.title, bytes: Array.from(b)});
  }});
"""
OHNE_TEILEN = "delete Navigator.prototype.share; delete Navigator.prototype.canShare;"


def _bank(daten=SYNC_DATEN) -> dict:
    return json.loads(daten.read_text(encoding="utf-8"))["bank"]


@pytest.fixture
def tan(starte_server):
    server = starte_server(heute="2024-06-30", mock_szenario="tan_erforderlich", mock_daten=SYNC_DATEN)
    lauf = server.api.post("/api/sync", json={}, erwartet=200).daten
    assert lauf["status"] == "wartet_auf_tan"
    return server, lauf["tan_anforderung_id"]


def _tan_seite(seite, server, tan_id):
    oeffnen(seite, server, f"/tan/{tan_id}", seitenname="tan")
    expect(seite.locator("h1")).to_have_text("TAN-Freigabe")


def test_tan_seite_zeigt_qr_code(tan, neue_seite, geraet):
    server, tan_id = tan
    a = server.api.get(f"/api/tan-anforderungen/{tan_id}", erwartet=200).daten
    seite = neue_seite(server, geraet)
    seite.add_init_script(OHNE_TEILEN)
    _tan_seite(seite, server, tan_id)
    expect(tid(seite, "tan-status")).to_have_attribute("data-status", "offen")
    expect(tid(seite, "tan-challenge")).to_have_text(a["challenge"])
    expect(tid(seite, "tan-gueltig-bis")).to_have_attribute("data-zeitpunkt", a["gueltig_bis"])
    bild = tid(seite, "tan-bild")
    expect(bild).to_be_visible()
    assert bild.get_attribute("alt").strip()
    seite.wait_for_function("el => el.complete && el.naturalWidth > 0", arg=bild.element_handle())
    if geraet == "handy":
        assert bild.bounding_box()["width"] <= seite.viewport_size["width"]
    expect(tid(seite, "tan-eingabe")).to_have_attribute("autocomplete", "one-time-code")
    expect(tid(seite, "tan-eingabe")).to_have_value("")
    expect(tid(seite, "tan-bild-teilen")).to_be_hidden()          # ohne Web Share verborgen


def test_qr_code_speichern(tan, neue_seite, geraet):
    server, tan_id = tan
    roh = server.api.get(f"/api/tan-anforderungen/{tan_id}/bild", erwartet=200).content
    seite = neue_seite(server, geraet)
    _tan_seite(seite, server, tan_id)
    with seite.expect_download() as dl:
        tid(seite, "tan-bild-speichern").click()
    d = dl.value
    assert d.suggested_filename == f"kontor-tan-{tan_id}.png"
    with open(d.path(), "rb") as f:
        assert f.read() == roh, "genau die Bytes des Bildes (14)"


def test_qr_code_teilen(tan, neue_seite):
    server, tan_id = tan
    roh = server.api.get(f"/api/tan-anforderungen/{tan_id}/bild", erwartet=200).content
    seite = neue_seite(server, "handy")
    seite.add_init_script(TEILEN_ATTRAPPE)
    _tan_seite(seite, server, tan_id)
    knopf = tid(seite, "tan-bild-teilen")
    expect(knopf).to_be_visible()
    tippen(seite, knopf)
    seite.wait_for_function("() => window.__geteilt.length === 1")
    g = seite.evaluate("() => window.__geteilt[0]")
    assert (g["name"], g["type"], g["title"]) == (f"kontor-tan-{tan_id}.png", "image/png", "TAN-Freigabe")
    assert bytes(g["bytes"]) == roh


def test_tan_falsch_dann_richtig(tan, neue_seite, geraet):
    server, tan_id = tan
    api = server.api
    seite = neue_seite(server, geraet)
    _tan_seite(seite, server, tan_id)
    tid(seite, "tan-eingabe").fill("000000")
    tid(seite, "tan-senden").click()
    fehler = tid(seite, "tan-fehler")
    expect(fehler).to_be_visible()
    expect(fehler).to_have_attribute("role", "alert")
    expect(tid(seite, "tan-eingabe")).to_have_value("")
    assert api.get(f"/api/tan-anforderungen/{tan_id}", erwartet=200).daten["status"] == "offen"
    richtig = _bank().get("tan", "123456")
    tid(seite, "tan-eingabe").fill(richtig)
    tid(seite, "tan-senden").click()
    expect(tid(seite, "tan-status")).to_have_attribute("data-status", "beantwortet")
    a = api.get(f"/api/tan-anforderungen/{tan_id}", erwartet=200).daten
    assert a["status"] == "beantwortet"
    lauf = api.get(f"/api/sync/laeufe/{a['lauf_id']}", erwartet=200).daten
    expect(tid(seite, "tan-ergebnis")).to_have_attribute("data-lauf-status", lauf["status"])
    expect(tid(seite, "tan-bild")).to_have_count(0)
    expect(tid(seite, "tan-eingabe")).to_have_count(0)
    speicher = seite.evaluate("() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), "
                              "location.href, history.length])")
    assert richtig not in speicher, "TAN in Speicher oder URL (14)"


def test_tan_abbrechen_und_abgelaufen(tan, neue_seite):
    server, tan_id = tan
    api = server.api
    seite = neue_seite(server)
    _tan_seite(seite, server, tan_id)
    tid(seite, "tan-abbrechen").click()
    tid(seite, "bestaetigen-ja").click()
    expect(tid(seite, "tan-status")).to_have_attribute("data-status", "abgebrochen")
    assert api.get(f"/api/tan-anforderungen/{tan_id}", erwartet=200).daten["status"] == "abgebrochen"
    expect(tid(seite, "tan-eingabe")).to_have_count(0)
    # zweite Anforderung, die abläuft
    lauf = api.post("/api/sync", json={}, erwartet=200).daten
    t2 = lauf["tan_anforderung_id"]
    api.put("/api/mock/zeit", json={"jetzt": "2024-07-01T00:00:10Z"}, erwartet=200)
    _tan_seite(seite, server, t2)
    expect(tid(seite, "tan-status")).to_have_attribute("data-status", "abgelaufen")
    expect(tid(seite, "tan-bild")).to_have_count(0)
    expect(tid(seite, "tan-eingabe")).to_have_count(0)


def test_von_der_benachrichtigung_zur_tan_seite(tan, neue_seite, geraet):
    server, tan_id = tan
    api = server.api
    ungelesen = api.get("/api/benachrichtigungen", params={"gelesen": "false"}, erwartet=200).daten
    b = next(x for x in ungelesen if x["art"] == "tan_erforderlich")
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(tid(seite, "benachrichtigungen-anzahl")).to_have_attribute("data-anzahl", str(len(ungelesen)))
    tid(seite, "benachrichtigungen-knopf").click()
    m8.warte_geladen(seite, "benachrichtigungen")
    link = tid(seite, f"benachrichtigung-link-{b['id']}")
    expect(link).to_have_attribute("href", f"/tan/{tan_id}")
    link.click()
    m8.warte_geladen(seite, "tan")
    expect(tid(seite, "tan-status")).to_have_attribute("data-status", "offen")


def test_sync_knopf_fuehrt_zur_tan(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_szenario="tan_erforderlich", mock_daten=SYNC_DATEN)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, "sync-starten").click()
    link = tid(seite, "sync-tan-link")
    expect(link).to_be_visible()
    tan_id = server.api.get("/api/sync/status", erwartet=200).daten["offene_tan_anforderung"]["id"]
    expect(link).to_have_attribute("href", f"/tan/{tan_id}")
    link.click()
    m8.warte_geladen(seite, "tan")


def test_pin_dialog(starte_server, neue_seite):
    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN_PIN)
    api = server.api
    pin = _bank(SYNC_DATEN_PIN)["pin"]
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, "sync-starten").click()
    d = tid(seite, "pin-dialog")
    expect(d).to_be_visible()
    feld = tid(seite, "pin-eingabe")
    expect(feld).to_have_attribute("type", "password")
    expect(feld).to_have_attribute("autocomplete", "off")
    feld.fill("FALSCHE-PIN")
    tid(seite, "pin-senden").click()
    expect(tid(seite, "pin-dialog")).to_be_visible()               # bank_pin_falsch: erneut fragen
    m8.warte_bis(lambda: (api.get("/api/sync/laeufe", erwartet=200).daten[-1]["fehler"] or {}).get("code") == "bank_pin_falsch")
    tid(seite, "pin-eingabe").fill(pin)
    tid(seite, "pin-senden").click()
    m8.warte_bis(lambda: api.get("/api/sync/laeufe", erwartet=200).daten[-1]["status"] == "erfolgreich")
    expect(tid(seite, "pin-dialog")).to_be_hidden()
    assert api.get("/api/sync/status", erwartet=200).daten["pin_vorhanden"] is True
    speicher = seite.evaluate("() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), "
                              "location.href])")
    assert pin not in speicher and pin not in seite.content()
    m8.navigiere(seite, "einstellungen")
    einstellung_oeffnen(seite, server, "pin-status")             # M31: Bereich bank (E-291)
    expect(tid(seite, "pin-status")).to_have_attribute("data-vorhanden", "ja")
    tid(seite, "pin-verwerfen").click()
    expect(tid(seite, "pin-status")).to_have_attribute("data-vorhanden", "nein")
    assert api.get("/api/sync/status", erwartet=200).daten["pin_vorhanden"] is False


# ------------------------------------------------------------------ Kreditabgleich (13.4)
@pytest.fixture
def kredit(starte_server):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    k = erw["m8"]["konten"]
    body = {"name": "Baufinanzierung Muster", "konto_id": ids.konto[k["darlehen"]],
            "zahlungskonto_id": ids.konto[k["giro"]], "zins_konto_id": ids.konto[k["zinsen"]],
            "restschuld": 1_000_000, "stand_datum": "2024-01-15", "sollzins": 36_000, "rate": 50_000,
            "erste_faelligkeit": "2024-02-01",
            "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktivbank AG"}]}
    kr = server.api.post("/api/kredite", json=body, erwartet=201).daten
    return server, erw, ids, kr


def test_kreditabgleich(kredit, neue_seite, geraet):
    server, erw, ids, kr = kredit
    api = server.api
    zinsen = ids.konto[erw["m8"]["konten"]["zinsen"]]
    darlehen = kr["konto_id"]
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/kredite", seitenname="kredite")
    z = tid(seite, f"kredit-{kr['id']}")
    expect(z).to_contain_text("Baufinanzierung Muster")
    expect(z.locator('[data-betrag="1000000"]').first).to_be_attached()
    expect(z.locator('[data-betrag="50000"]').first).to_be_attached()
    z.click()
    m8.warte_geladen(seite, "kredit")
    expect(seite.locator("h1")).to_have_text("Baufinanzierung Muster")
    plan = api.get(f"/api/kredite/{kr['id']}/plan", erwartet=200).daten
    expect(tid(seite, "tilgungsplan").locator('[data-testid^="plan-zeile-"]')).to_have_count(len(plan["zeilen"]))
    # Auszug: Restschuld 9.500,00 €, Zinsen 300,00 €; gebucht sind 10.000,00 € (Anfangsbuchung) und 0 € Zinsen
    tid(seite, "abgleich-jahr").fill("2024")
    tid(seite, "abgleich-restschuld").fill("9.500,00")
    tid(seite, "abgleich-zinsen").fill("300,00")
    a0 = m8.max_aenderung(api)
    tid(seite, "abgleich-pruefen").click()
    erg = tid(seite, "abgleich-ergebnis")
    expect(erg).to_be_visible()
    dr, dz = 950_000 - 1_000_000, 30_000 - 0
    for t, wert in (("abgleich-restschuld-berechnet", 1_000_000), ("abgleich-zinsen-berechnet", 0),
                    ("abgleich-differenz-restschuld", dr), ("abgleich-differenz-zinsen", dz)):
        expect(tid(seite, t)).to_have_attribute("data-betrag", str(wert))
    korrektur = [(zinsen, dz), (darlehen, -dr), (None, dr - dz)]       # kredite.md 5 Schritt 4
    for i, (konto, betrag) in enumerate(korrektur):
        el = tid(seite, f"abgleich-korrektur-{i}")
        expect(el).to_be_visible()
        wert = el.evaluate("e => e.matches('[data-betrag]') ? e.dataset.betrag "
                           ": e.querySelector('[data-betrag]')?.dataset.betrag")
        assert wert == str(betrag), (i, wert)
    assert m8.max_aenderung(api) == a0, "Probelauf ändert nichts"
    tid(seite, "abgleich-bestaetigen").click()
    expect(tid(seite, "abgleich-2024")).to_be_visible()
    k = m8.warte_bis(lambda: api.get(f"/api/kredite/{kr['id']}", erwartet=200).daten["abgleiche"])
    assert [(x["jahr"], x["restschuld"], x["zinsen"]) for x in k] == [(2024, 950_000, 30_000)]
    korr = api.buchung_lesen(k[0]["buchung_id"])
    assert korr["status"] == "abgeglichen" and korr["datum"] == "2024-12-31"
    assert m8.aenderungen_seit(api, a0)[-1]["aktion"] == "kredit_jahresabgleich"
    # zweites Mal für dasselbe Jahr: 409 als Meldung, nichts ändert sich
    a1 = m8.max_aenderung(api)
    tid(seite, "abgleich-jahr").fill("2024")
    tid(seite, "abgleich-restschuld").fill("9.500,00")
    tid(seite, "abgleich-zinsen").fill("300,00")
    tid(seite, "abgleich-pruefen").click()
    expect(tid(seite, "meldungen").locator('[data-testid="meldung"][data-art="fehler"]')).to_be_visible()
    assert m8.max_aenderung(api) == a1
