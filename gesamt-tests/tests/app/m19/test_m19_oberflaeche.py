"""M19: Oberfläche – Import „ALF-BanCo“, Mehrfachauswahl im Kategorienbaum, Zusammenführen-Dialog
(oberflaeche.md 29, E-214). Playwright wie M8; nicht kern.
"""

from __future__ import annotations

import re

import pytest

from tests.hilfen import m8
from tests.hilfen.m8 import oeffnen, strg, tid, warte_bis
from tests.hilfen.m15 import Mitschnitt, text_normal
from tests.hilfen.m17 import menue_eintraege
from tests.hilfen.m19 import BEISPIEL, qif

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

FEHLER = '[data-testid="meldung"][data-art="fehler"]'
ERFOLG = '[data-testid="meldung"][data-art="erfolg"]'
NAMEN = ["Auto", "Bücher", "Café", "Drogerie", "Essen"]


def _kategorien(api) -> dict:
    k = {n: api.konto(n, "aufwand")["id"] for n in NAMEN}
    k["Zinsen"] = api.konto("Zinsen", "ertrag")["id"]
    k["Essen/Obst"] = api.konto("Obst", "aufwand", eltern_id=k["Essen"])["id"]
    k["giro"] = api.konto("Girokonto")["id"]
    return k


def _sel(seite) -> set[int]:
    return {int(x) for x in tid(seite, "kategorienbaum").locator('[role="treeitem"][aria-selected="true"]')
            .evaluate_all("els => els.map(e => e.getAttribute('data-testid').slice('kategorie-'.length))")}


def _name(seite, kid: int, name: str):
    return tid(seite, f"kategorie-{kid}").get_by_text(name, exact=True).first


# ------------------------------------------------------------------ Import-Seite (29.1)


def test_import_seite_alfbanco(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    giro = api.konto("Girokonto")["id"]
    spar = api.konto("Sparkonto", "sparkonto")["id"]
    api.konto("Haushalt", "aufwand")
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, "/import", seitenname="import")
    fmt = tid(seite, "import-format")
    werte = fmt.locator("option").evaluate_all("els => els.map(e => [e.value, e.textContent])")
    assert [w for w, _ in werte][:3] == ["kmymoney", "gnucash", "alfbanco"]
    assert text_normal(dict(werte)["alfbanco"]) == "ALF-BanCo (QIF-Export, eine Datei je Konto)"
    expect(tid(seite, "import-konto")).to_be_hidden()
    expect(tid(seite, "import-hinweis-alfbanco")).to_be_hidden()
    fmt.select_option("alfbanco")
    konto = tid(seite, "import-konto")
    expect(konto).to_be_visible()
    expect(tid(seite, "import-hinweis-alfbanco")).to_be_visible()
    opts = konto.locator("option").evaluate_all("els => els.map(e => [e.value, e.textContent])")
    assert opts[0][0] == "" and text_normal(opts[0][1]) == "– Konto wählen –"
    assert [v for v, _ in opts[1:]] == [str(giro), str(spar)], "alle Bestandskonten, keine Kategorien"
    assert [text_normal(t) for _, t in opts[1:]] == ["Girokonto", "Sparkonto"]
    # ohne Datei / ohne Konto: Fehlermeldung, keine Anfrage
    mit.leeren()
    tid(seite, "import-starten").click()
    expect(tid(seite, "meldungen").locator(FEHLER).last).to_be_visible()
    tid(seite, "import-datei").set_input_files({"name": "giro.qif", "mimeType": "application/octet-stream",
                                                "buffer": qif(BEISPIEL)})
    tid(seite, "import-starten").click()
    expect(tid(seite, "meldungen").locator(FEHLER)).to_have_count(2)
    assert mit.schreibend() == [], "ohne Datei oder Konto keine Anfrage"
    konto.select_option(str(giro))
    tid(seite, "import-starten").click()
    erg = tid(seite, "import-ergebnis")
    expect(erg).to_have_attribute("data-erfolgreich", "ja")
    expect(tid(seite, "import-zahl-buchungen_neu")).to_have_attribute("data-anzahl", "6")
    expect(tid(seite, "import-zahl-splits_neu")).to_have_attribute("data-anzahl", "13")
    expect(tid(seite, "import-meldung").first).to_contain_text("kategorieart_abgeleitet")
    assert [(m, p) for m, p, _ in mit.schreibend()] == [("POST", "/api/import/alfbanco")]
    assert len(api.alle_buchungen(konto_id=giro)) == 6
    # abgelehnter Import
    tid(seite, "import-datei").set_input_files({"name": "x.qif", "mimeType": "text/plain",
                                                "buffer": b"!Option:AutoSwitch\r\n"})
    tid(seite, "import-starten").click()
    expect(erg).to_have_attribute("data-erfolgreich", "nein")
    expect(tid(seite, "import-meldung").first).to_contain_text("import_format_ungueltig")
    # Rückgängig mit Strg+Z nimmt den Import zurück
    seite.locator("body").click(position={"x": 5, "y": 5})
    seite.keyboard.press(f"{strg()}+z")
    warte_bis(lambda: api.alle_buchungen(konto_id=giro) == [], text="Import zurückgenommen")
    # anderes Format blendet Konto und Hinweis wieder aus
    fmt.select_option("gnucash")
    expect(konto).to_be_hidden()


# ------------------------------------------------------------------ Mehrfachauswahl (29.2)


def test_mehrfachauswahl_im_kategorienbaum(starte_server, neue_seite):
    server = starte_server()
    k = _kategorien(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    baum = tid(seite, "kategorienbaum")
    expect(baum).to_have_attribute("aria-multiselectable", "true")
    for n in NAMEN + ["Zinsen"]:
        expect(tid(seite, f"kategorie-{k[n]}")).to_have_attribute("aria-selected", "false")
    a, b, c, d, e = (k[n] for n in NAMEN)
    _name(seite, a, "Auto").click()
    assert _sel(seite) == {a}
    _name(seite, c, "Café").click(modifiers=[strg()])
    assert _sel(seite) == {a, c}
    _name(seite, e, "Essen").click(modifiers=["Shift"])
    assert _sel(seite) == {c, d, e}, "Umschalt-Klick: Bereich vom zuletzt angeklickten, ersetzt die Markierung"
    _name(seite, a, "Auto").click(modifiers=[strg()])
    assert _sel(seite) == {a, c, d, e}
    _name(seite, b, "Bücher").click(modifiers=[strg()])           # Anker Bücher, Bücher dazu
    _name(seite, b, "Bücher").click(modifiers=[strg()])           # wieder ab, Anker bleibt Bücher
    assert _sel(seite) == {a, c, d, e}
    _name(seite, a, "Auto").click()
    _name(seite, e, "Essen").click(modifiers=[strg()])           # Anker Essen
    _name(seite, c, "Café").click(modifiers=[strg(), "Shift"])   # Bereich Café–Essen ergänzt
    assert _sel(seite) == {a, c, d, e}
    tid(seite, f"kategorie-{b}").focus()
    seite.keyboard.press("Space")
    assert b in _sel(seite), "Leertaste schaltet den fokussierten Eintrag um"
    seite.keyboard.press("Space")
    assert b not in _sel(seite)
    seite.keyboard.press("Escape")
    assert _sel(seite) == set()


# ------------------------------------------------------------------ Kontextmenü und Dialog (29.3, 29.4)


def test_kontextmenue_und_dialog(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    k = _kategorien(api)
    g = k["giro"]
    b1 = api.buchung("2024-03-01", [(g, -100), (k["Auto"], 100)])["id"]
    b2 = api.buchung("2024-03-02", [(g, -200), (k["Bücher"], 200)])["id"]
    api.buchung("2024-03-03", [(g, -300), (k["Café"], 300)])
    seite = neue_seite(server, erfolgsmeldung=True)   # Erfolgsmeldung ab M32 nur mit Einstellung (E-307)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    # unmarkiert: nur diese Kategorie
    _name(seite, k["Café"], "Café").click(button="right")
    eintraege = menue_eintraege(seite)
    assert eintraege[0] == "km-kategorie-zusammenfuehren" and any(x.startswith("km-konto-") for x in eintraege)
    expect(tid(seite, "kontextmenue").get_by_test_id("km-kategorie-zusammenfuehren")).to_have_text(
        re.compile(r"^\s*Zusammenführen in…\s*$"))
    seite.keyboard.press("Escape")
    # zwei markiert, Menü auf einer markierten
    _name(seite, k["Auto"], "Auto").click()
    _name(seite, k["Bücher"], "Bücher").click(modifiers=[strg()])
    _name(seite, k["Bücher"], "Bücher").click(button="right")
    eintrag = tid(seite, "kontextmenue").get_by_test_id("km-kategorie-zusammenfuehren")
    expect(eintrag).to_have_text(re.compile(r"^\s*2 Kategorien zusammenführen in…\s*$"))
    eintrag.click()
    dlg = tid(seite, "zusammenfuehren-dialog")
    expect(dlg).to_be_visible()
    expect(dlg).to_contain_text("2 Kategorien zusammenführen")
    expect(tid(seite, "zusammenfuehren-quellen")).to_have_text(re.compile(r"^\s*Auto, Bücher\s*$"))
    suche = tid(seite, "zusammenfuehren-suche")
    expect(suche).to_be_focused()
    assert suche.get_attribute("type") == "search"
    ziele = tid(seite, "zusammenfuehren-ziele")
    assert ziele.get_attribute("role") == "listbox"
    ids = [int(x) for x in ziele.locator('[role="option"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid').slice('zusammenfuehren-ziel-'.length))")]
    assert ids == [k["Café"], k["Drogerie"], k["Essen"], k["Essen/Obst"], k["Zinsen"]], "Baumfolge ohne Quellen"
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Zinsen']}")).to_have_text(re.compile(r"Zinsen \(Einnahme\)"))
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Essen/Obst']}")).to_contain_text("Obst")
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Essen/Obst']}")).to_contain_text("Essen")
    ausfuehren = tid(seite, "zusammenfuehren-ausfuehren")
    expect(ausfuehren).to_be_disabled()
    suche.fill("ESS")
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Café']}")).to_be_hidden()
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Essen']}")).to_be_visible()
    suche.fill("")
    loeschen = tid(seite, "zusammenfuehren-loeschen")
    expect(loeschen).to_be_checked()
    expect(tid(seite, "zusammenfuehren-gesperrte-bestaetigen")).to_be_hidden()
    mit.leeren()
    tid(seite, f"zusammenfuehren-ziel-{k['Café']}").click()
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Café']}")).to_have_attribute("aria-selected", "true")
    vorschau = tid(seite, "zusammenfuehren-vorschau")
    expect(vorschau).to_have_attribute("data-anzahl", "2")
    expect(vorschau).to_contain_text("2 Buchungen werden auf „Café“ umgebucht")
    warte_bis(lambda: mit.schreibend("/api/kategorien/zusammenfuehren"), text="Probelauf")
    (_, _, koerper), = mit.schreibend("/api/kategorien/zusammenfuehren")
    assert koerper["trocken"] is True and koerper["ziel_id"] == k["Café"]
    assert sorted(koerper["quelle_ids"]) == sorted([k["Auto"], k["Bücher"]])
    # Pfeiltaste wählt die nächste sichtbare Option
    seite.keyboard.press("ArrowDown")
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Drogerie']}")).to_have_attribute("aria-selected", "true")
    seite.keyboard.press("ArrowUp")
    expect(tid(seite, f"zusammenfuehren-ziel-{k['Café']}")).to_have_attribute("aria-selected", "true")
    mit.leeren()
    loeschen.uncheck()
    warte_bis(lambda: any(x[2].get("quellen_loeschen") is False for x in mit.schreibend()), text="Probelauf ohne Löschen")
    assert all(x[2]["trocken"] is True for x in mit.schreibend())
    loeschen.check()
    expect(ausfuehren).to_be_enabled()
    a0 = m8.max_aenderung(api)
    mit.leeren()
    ausfuehren.click()
    expect(dlg).to_be_hidden()
    expect(tid(seite, "meldungen").locator(ERFOLG).last).to_contain_text("Zusammengeführt in „Café“.")
    echt = [x for x in mit.schreibend("/api/kategorien/zusammenfuehren") if not x[2].get("trocken")]
    assert len(echt) == 1 and echt[0][2].get("quellen_loeschen", True) is True
    assert [a["aktion"] for a in m8.aenderungen_seit(api, a0)] == ["kategorien_zusammenfuehren"]
    expect(tid(seite, f"kategorie-{k['Auto']}")).to_have_count(0)
    expect(tid(seite, f"kategorie-{k['Bücher']}")).to_have_count(0)
    assert {s["konto_id"] for s in api.buchung_lesen(b1)["splits"]} == {g, k["Café"]}
    seite.keyboard.press(f"{strg()}+z")
    expect(tid(seite, f"kategorie-{k['Auto']}")).to_be_visible()
    assert {s["konto_id"] for s in api.buchung_lesen(b2)["splits"]} == {g, k["Bücher"]}


def test_gesperrte_bestaetigen_und_abbrechen(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    k = _kategorien(api)
    g = k["giro"]
    b = api.buchung("2024-03-01", [(g, -100), (k["Auto"], 100)])["id"]
    api.patch(f"/api/buchungen/{b}", json={"status": "abgeglichen"}, erwartet=200)
    seite = neue_seite(server)
    mit = Mitschnitt(seite)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    _name(seite, k["Auto"], "Auto").click(button="right")
    tid(seite, "kontextmenue").get_by_test_id("km-kategorie-zusammenfuehren").click()
    dlg = tid(seite, "zusammenfuehren-dialog")
    expect(dlg).to_contain_text("„Auto“ zusammenführen")
    # Abbrechen und Esc ohne Wirkung
    a0 = m8.max_aenderung(api)
    tid(seite, "zusammenfuehren-abbrechen").click()
    expect(dlg).to_be_hidden()
    _name(seite, k["Auto"], "Auto").click(button="right")
    tid(seite, "kontextmenue").get_by_test_id("km-kategorie-zusammenfuehren").click()
    expect(dlg).to_be_visible()
    seite.keyboard.press("Escape")
    expect(dlg).to_be_hidden()
    assert m8.max_aenderung(api) == a0
    _name(seite, k["Auto"], "Auto").click(button="right")
    tid(seite, "kontextmenue").get_by_test_id("km-kategorie-zusammenfuehren").click()
    tid(seite, f"zusammenfuehren-ziel-{k['Drogerie']}").click()
    best = tid(seite, "zusammenfuehren-gesperrte-bestaetigen")
    expect(best).to_be_visible()
    ausfuehren = tid(seite, "zusammenfuehren-ausfuehren")
    expect(ausfuehren).to_be_disabled()
    best.check()
    expect(ausfuehren).to_be_enabled()
    mit.leeren()
    ausfuehren.click()
    expect(dlg).to_be_hidden()
    (echt,) = [x for x in mit.schreibend("/api/kategorien/zusammenfuehren") if not x[2].get("trocken")]
    assert echt[2]["gesperrte_einbeziehen"] is True
    assert {s["konto_id"] for s in api.buchung_lesen(b)["splits"]} == {g, k["Drogerie"]}


def test_kein_eintrag_fuer_bestandskonten(starte_server, neue_seite):
    server = starte_server()
    k = _kategorien(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/konten", seitenname="konten")
    tid(seite, f"kontenbaum-konto-{k['giro']}").click(button="right")
    eintraege = menue_eintraege(seite)
    assert eintraege and "km-kategorie-zusammenfuehren" not in eintraege
