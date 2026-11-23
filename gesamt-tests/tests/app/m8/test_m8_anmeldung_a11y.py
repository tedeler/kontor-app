"""M8: Anmeldung in der Oberfläche (oberflaeche.md 19; sicherheit.md 3.4, 4.6) und Barrierefreiheit (oberflaeche.md 20)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m7 import einrichtungsdatei
from tests.hilfen.m8 import oeffnen, tid, warte_geladen
from tests.hilfen.m31 import einstellung_oeffnen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


def _anmeldeseite(seite, server, pfad="/"):
    seite.goto(server.url + pfad)
    expect(tid(seite, "anmeldung-formular")).to_be_visible()


def test_anmelden_und_weiterleiten(starte_server, neue_seite, geraet):
    server = starte_server(anmeldung=True)
    seite = neue_seite(server, geraet, ohne_anmeldung=True)
    _anmeldeseite(seite, server, "/kredite")
    assert seite.url == server.url + "/anmelden?weiter=/kredite"  # sicherheit.md 3.2: „/“ bleibt
    feld = tid(seite, "anmeldung-passwort")
    feld.fill("ganz-falsches-passwort")
    feld.press("Enter")
    f = tid(seite, "anmeldung-fehler")
    expect(f).to_be_visible()
    expect(f).to_have_attribute("role", "alert")
    expect(feld).to_have_value("")
    feld.fill(m8.PASSWORT)
    feld.press("Enter")
    warte_geladen(seite, "kredite")
    assert seite.url == server.url + "/kredite"


def test_ersteinrichtung_mit_code(starte_server, neue_seite):
    server = starte_server(anmeldung=True, einrichten=False)
    code = einrichtungsdatei(server.config).read_text(encoding="utf-8").strip()
    seite = neue_seite(server, ohne_anmeldung=True)
    _anmeldeseite(seite, server, "/einstellungen")
    tid(seite, "anmeldung-einrichtungscode").fill(code)
    tid(seite, "anmeldung-passwort").fill("Neues-Haushaltspasswort-1")
    tid(seite, "anmeldung-passwort").press("Enter")
    warte_geladen(seite, "einstellungen")
    assert server.api.get("/api/anmeldung").status_code == 200


def test_schreiben_mit_csrf_und_abmelden(starte_server, neue_seite):
    server = starte_server(anmeldung=True)
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    r = m8.rest_liste(server.api, giro)
    m8.warte_liste(seite, r)
    e = m8.zweck_editor(seite, r[0])   # M28 (37.8, E-254): F2 statt Doppelklick
    e.fill("Mit CSRF-Kopf")
    e.press("Enter")
    m8.warte_bis(lambda: server.api.buchung_lesen(r[0])["verwendungszweck"] == "Mit CSRF-Kopf")
    seite.keyboard.press("Control+k")
    expect(tid(seite, "befehl-abmelden")).to_be_attached()
    seite.keyboard.press("Escape")
    einstellung_oeffnen(seite, server, "abmelden")              # M31: Bereich sicherheit (E-291)
    tid(seite, "abmelden").click()
    expect(tid(seite, "anmeldung-formular")).to_be_visible()
    assert "/anmelden" in seite.url
    seite.goto(server.url + "/konten")
    expect(tid(seite, "anmeldung-formular")).to_be_visible()


def test_sitzung_beendet_fuehrt_zur_anmeldung(starte_server, neue_seite):
    server = starte_server(anmeldung=True)
    m8.importiere(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    status = seite.context.request.get(server.url + "/api/anmeldung").json()
    r = seite.context.request.post(server.url + "/api/anmeldung/abmelden", headers={"X-Kontor-CSRF": status["csrf_token"]})
    assert r.status == 204
    tid(seite, "nav-kategorien").click()
    expect(tid(seite, "anmeldung-formular")).to_be_visible()
    assert seite.url == server.url + "/anmelden?weiter=/kategorien"


def test_ohne_anmeldung_kein_abmelden(starte_server, neue_seite):
    server = starte_server(anmeldung=False)
    seite = neue_seite(server)
    einstellung_oeffnen(seite, server, "abmelden")              # M31 (E-291)
    expect(tid(seite, "abmelden")).to_have_count(0)
    seite.keyboard.press("Control+k")
    expect(tid(seite, "befehlspalette")).to_be_visible()
    expect(tid(seite, "befehl-abmelden")).to_have_count(0)


# ------------------------------------------------------------------ Barrierefreiheit (20)
ROLLEN = {"link", "button", "textbox", "searchbox", "combobox", "listbox", "option", "menuitem", "treeitem",
          "checkbox", "radio", "spinbutton", "slider", "tab", "switch"}


def _ohne_namen(seite) -> list[str]:
    cdp = seite.context.new_cdp_session(seite)
    knoten = cdp.send("Accessibility.getFullAXTree")["nodes"]
    fehlt = []
    for k in knoten:
        if k.get("ignored"):
            continue
        rolle = (k.get("role") or {}).get("value")
        name = ((k.get("name") or {}).get("value") or "").strip()
        fokus = any(p["name"] == "focusable" and p["value"]["value"] for p in k.get("properties", []))
        if (rolle in ROLLEN or (rolle == "separator" and fokus)) and not name:
            fehlt.append(f"{rolle} (backendDOMNodeId {k.get('backendDOMNodeId')})")
    cdp.detach()
    return fehlt


@pytest.mark.parametrize("pfad", ["/", "/konto", "/kategorien", "/einstellungen", "/kredite", "/import", "/berichte"])
def test_zugaengliche_namen(starte_server, neue_seite, geraet, pfad):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    if pfad == "/konto":
        pfad = f"/konten/{ids.konto[erw['m8']['konten']['giro']]}"
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, pfad)
    seite.wait_for_selector('[data-testid^="seite-"][data-geladen="ja"]')
    fehlt = _ohne_namen(seite)
    assert not fehlt, f"bedienbare Elemente ohne zugänglichen Namen auf {pfad}: {fehlt[:10]}"


def test_fokus_sichtbar_und_dialog(starte_server, neue_seite):
    server = starte_server()
    m8.importiere(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    for _ in range(40):
        seite.keyboard.press("Tab")
        if seite.evaluate("() => document.activeElement?.getAttribute('data-testid') || ''").startswith("nav-"):
            break
    else:
        raise AssertionError("Navigation per Tab nicht erreichbar")
    stil = seite.evaluate("""() => { const s = getComputedStyle(document.activeElement);
        return [s.outlineStyle, parseFloat(s.outlineWidth), s.boxShadow]; }""")
    assert (stil[0] != "none" and stil[1] > 0) or stil[2] != "none", f"kein sichtbarer Fokus: {stil}"
    # Fokus bleibt im Dialog und kehrt zurück
    tid(seite, "befehlspalette-knopf").focus()
    seite.keyboard.press("Enter")
    expect(tid(seite, "befehlspalette")).to_be_visible()
    for _ in range(6):
        seite.keyboard.press("Tab")
        assert seite.evaluate("() => !!document.activeElement.closest('[data-testid=\"befehlspalette\"]')"), \
            "Tab verlässt den Dialog"
    seite.keyboard.press("Escape")
    expect(tid(seite, "befehlspalette-knopf")).to_be_focused()


def test_dialoge_modal_mit_ueberschrift(starte_server, neue_seite):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    r = m8.rest_liste(server.api, giro)
    m8.zeile(seite, r[0]).locator('[data-feld="betrag"]').click()
    for knopf, dialog in (("mehrfach-kategorie", "kategorie-auswahl"), ("mehrfach-tags", "tag-auswahl"),
                          ("mehrfach-loeschen", "bestaetigen-dialog")):
        tid(seite, knopf).click()
        d = tid(seite, dialog)
        expect(d).to_have_attribute("role", "dialog")
        expect(d).to_have_attribute("aria-modal", "true")
        ueberschrift = d.get_attribute("aria-labelledby")
        assert ueberschrift and seite.locator(f"#{ueberschrift}").inner_text().strip()
        seite.keyboard.press("Escape")
        expect(d).to_be_hidden()
        expect(tid(seite, knopf)).to_be_focused()
