"""M32: Oberfläche aus dem Sammelbranch sammel3 (oberflaeche.md 41; E-306).

Playwright wie M8 (E-139), nicht kern. Geprüft wird nur, was die Definition nennt; Erwartungen über REST und eigene
Rechnung.
"""

from __future__ import annotations

import pytest

from tests.app.m8.test_m8_bearbeiten import _zweck_bearbeiten
from tests.hilfen import m8, m17, m28
from tests.hilfen.m6 import abruf, nachrichten
from tests.hilfen.m8 import ausgewaehlt, oeffnen, strg, tid, warte_bis, warte_geladen, warte_liste, zeile
from tests.hilfen.m17 import warte
from tests.hilfen.m20 import mock_datei, nachricht

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect
SHOP = "Fiktiver Shop <shop@example.invalid>"


def _wert(loc) -> str:
    return loc.evaluate("e => 'value' in e ? e.value : e.textContent")


def _konto(api):
    g = api.konto("Girokonto")["id"]
    leb = api.konto("Lebensmittel", "aufwand")["id"]
    lohn = api.konto("Gehalt", "ertrag")["id"]
    b = {"ein": api.buchung("2024-05-01", [(g, 100000), (lohn, -100000)], verwendungszweck="Gehalt Mai")["id"],
         "aus1": api.buchung("2024-05-02", [(g, -3000), (leb, 3000)], verwendungszweck="Einkauf 1")["id"],
         "aus2": api.buchung("2024-05-03", [(g, -2000), (leb, 2000)], verwendungszweck="Einkauf 2")["id"]}
    return g, leb, b


# ------------------------------------------------------------------ 41.1 Navigation, Palette


def test_navigation_mit_tags_und_konfiguration(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    nav = tid(seite, "navigation")
    ids = nav.locator("a[data-testid]").evaluate_all("els => els.map(e => e.getAttribute('data-testid'))")
    assert ids.index("navlink-tags") == ids.index("nav-kategorien") + 1, ids
    assert "navlink-statistik" not in ids
    betrieb = nav.evaluate("""n => { const h = n.querySelector('[data-testid="nav-gruppe-betrieb"]');
      const a = document.querySelector('[aria-labelledby="' + h.id + '"]');
      return [...a.querySelectorAll('a[data-testid]')].map(x => x.getAttribute('data-testid')); }""")
    assert "navlink-konfiguration" in betrieb, betrieb
    expect(tid(seite, "navlink-konfiguration")).to_have_attribute("href", "/konfiguration")
    tid(seite, "navlink-tags").click()
    warte_geladen(seite, "tags")
    assert seite.url == server.url + "/tags"
    tid(seite, "navlink-konfiguration").click()
    warte_geladen(seite, "konfiguration")


def test_handy_ohne_konfiguration_in_der_navigation(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tid(seite, "menue-knopf").click()
    expect(tid(seite, "navlink-tags")).to_be_visible()
    k = tid(seite, "navlink-konfiguration")
    assert k.count() == 0 or k.is_hidden()


def test_palette_gehe_zu_tags_und_konfiguration(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    seite.keyboard.press("Control+k")
    expect(tid(seite, "befehlspalette")).to_be_visible()
    ids = tid(seite, "befehlspalette-liste").locator('[role="option"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    assert "befehl-gehe-tags" in ids and "befehl-gehe-konfiguration" in ids and "befehl-gehe-statistik" not in ids
    tid(seite, "befehl-gehe-tags").click()
    warte_geladen(seite, "tags")


def test_statistik_innerhalb_der_oberflaeche_nicht_gefunden(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    r = seite.goto(server.url + "/statistik")
    assert r.status == 404


# ------------------------------------------------------------------ 41.2 Empfänger


def _empfaenger(api):
    g, leb, _ = _konto(api)
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    ein = api.post("/api/empfaenger", json={"name": "Bäckerei Korn", "aliase": ["BAECKEREI KORN GMBH"]},
                   erwartet=201).daten["id"]
    zwei = api.empfaenger("Markt Fiktiv")["id"]
    leer = api.empfaenger("Niemand")["id"]
    api.buchung("2024-05-04", [(g, -100), (leb, 100)], empfaenger_id=ein)
    for k in (spar, spar, g):
        api.buchung("2024-05-05", [(k, -100), (leb, 100)], empfaenger_id=zwei)
    return {"g": g, "spar": spar, "ein": ein, "zwei": zwei, "leer": leer}


def test_empfaenger_regel_erstellen(starte_server, neue_seite):
    server = starte_server()
    e = _empfaenger(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    tid(seite, f"empfaenger-{e['ein']}").click(button="right")
    tid(seite, "em-regel").click()
    expect(tid(seite, "regel-dialog")).to_be_visible()
    expect(tid(seite, "regel-name")).to_have_value("Bäckerei Korn")
    ausdruck = _wert(tid(seite, "regel-ausdruck"))
    assert "empf" in ausdruck and '"Bäckerei Korn"' in ausdruck and '"BAECKEREI KORN GMBH"' in ausdruck, ausdruck


def _empfaengerfilter(seite, server, konto: int, empfaenger: int, name: str) -> None:
    """W-025 (E-313): Kontoblatt des Kontos mit dem Empfänger als Filter – als ``empfaenger_id=`` oder, nach der
    Übernahme in den Ausdruck (39.2), als ``filter=`` mit dem Namen; sichtbar nur dessen Buchungen."""
    warte(seite, lambda: seite.url.split("?")[0].endswith(f"/konten/{konto}"), text="Kontoblatt des Kontos")
    q = m28.abfrage(seite)
    assert q.get("empfaenger_id") == [str(empfaenger)] or name in " ".join(q.get("filter", [])), q
    soll = [b["id"] for b in server.api.alle_buchungen(konto_id=konto) if (b["empfaenger"] or {}).get("id") == empfaenger]
    warte_liste(seite, sorted(soll, key=lambda i: m8.rest_liste(server.api, konto).index(i)))


def test_empfaenger_anzeigen_im_konto(starte_server, neue_seite):
    server = starte_server()
    e = _empfaenger(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    tid(seite, f"empfaenger-{e['leer']}").click(button="right")
    expect(tid(seite, "em-im-konto")).to_have_attribute("aria-disabled", "true")
    seite.keyboard.press("Escape")
    tid(seite, f"empfaenger-{e['zwei']}").click(button="right")
    tid(seite, "em-im-konto").click()
    unter = seite.locator('[data-testid^="em-im-konto-"]').evaluate_all(
        "els => els.map(x => x.getAttribute('data-testid'))")
    assert unter == [f"em-im-konto-{e['spar']}", f"em-im-konto-{e['g']}"], "meistbenutzte zuerst"
    tid(seite, f"em-im-konto-{e['spar']}").click()
    warte_geladen(seite, "konto")
    _empfaengerfilter(seite, server, e["spar"], e["zwei"], "Markt Fiktiv")
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    tid(seite, f"empfaenger-{e['ein']}").click(button="right")
    tid(seite, "em-im-konto").click()
    warte_geladen(seite, "konto")
    _empfaengerfilter(seite, server, e["g"], e["ein"], "Bäckerei Korn")


def test_empfaenger_suche_und_menue(starte_server, neue_seite):
    server = starte_server()
    e = _empfaenger(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    tid(seite, "empfaenger-suche").fill("baeckerei korn gmbh")
    expect(tid(seite, f"empfaenger-{e['ein']}")).to_be_visible()
    expect(tid(seite, f"empfaenger-{e['zwei']}")).to_be_hidden()
    expect(tid(seite, "empfaenger-treffer")).to_have_attribute("data-anzahl", "1")
    tid(seite, "empfaenger-suche").fill("")
    expect(tid(seite, f"empfaenger-{e['zwei']}")).to_be_visible()
    tid(seite, f"empfaenger-menue-{e['zwei']}").click()
    expect(tid(seite, "kontextmenue")).to_be_visible()
    assert "em-im-konto" in m28.menue(seite) and "em-regel" in m28.menue(seite)
    expect(tid(seite, f"empfaenger-bestaetigen-{e['zwei']}")).to_be_attached()


# ------------------------------------------------------------------ 41.3 Dubletten


def test_dubletten_zur_buchung_springen(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, leb, b = _konto(api)
    doppelt = api.buchung("2024-05-02", [(g, -3000), (leb, 3000)], verwendungszweck="Einkauf 1 (Kopie)")["id"]
    api.post("/api/dubletten", json={"buchung_ids": [doppelt, b["aus1"]]}, erwartet=201)
    seite = neue_seite(server)
    oeffnen(seite, server, "/dubletten", seitenname="dubletten")
    link = tid(seite, f"dublette-buchung-{doppelt}-konto-{g}")
    expect(link).to_be_visible()
    expect(tid(seite, "seite-dubletten")).to_contain_text("Einkauf 1 (Kopie)")
    link.click()
    warte_geladen(seite, "konto")
    warte_bis(lambda: ausgewaehlt(seite) == {doppelt}, text="Buchung markiert")
    assert seite.url.split("?")[0].endswith(f"/konten/{g}")


# ------------------------------------------------------------------ 41.4 Bestätigen mit B-<Name>


def test_bestaetigen_mit_b_tag(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, _, b = _konto(api)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    zeile(seite, b["aus1"]).click(button="right")
    tid(seite, "km-bestaetigen").click()
    warte_bis(lambda: [t["name"] for t in api.buchung_lesen(b["aus1"])["tags"]] == ["Torsten-Bestätigt"], text="Torsten-Bestätigt")
    expect(zeile(seite, b["aus1"])).to_have_attribute("data-bestaetigt", "Torsten")


# ------------------------------------------------------------------ 41.5 Spalten, 41.6 Summen der Auswahl


def test_spalten_ein_und_ausblenden(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, _, b = _konto(api)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    tid(seite, "buchungsliste").locator('[role="columnheader"]').first.click(button="right")
    tid(seite, "km-spalten-wahl").click()
    eintrag = tid(seite, "km-spalte-verwendungszweck")
    expect(eintrag).to_have_attribute("aria-checked", "true")
    eintrag.click()
    liste = tid(seite, "buchungsliste")
    warte(seite, lambda: "verwendungszweck" in (liste.get_attribute("data-spalten-aus") or ""), text="ausgeblendet")
    expect(zeile(seite, b["aus1"]).locator('[data-feld="verwendungszweck"]')).to_be_attached()
    seite.reload()
    warte_geladen(seite, "konto")
    warte(seite, lambda: "verwendungszweck" in (tid(seite, "buchungsliste").get_attribute("data-spalten-aus") or ""),
          text="im Browser gemerkt")


def test_summen_der_auswahl(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, _, b = _konto(api)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    expect(tid(seite, "auswahl-summen")).to_be_hidden()
    zeile(seite, b["ein"]).click()
    zeile(seite, b["aus1"]).click(modifiers=[strg()])
    zeile(seite, b["aus2"]).click(modifiers=[strg()])
    expect(tid(seite, "auswahl-summen")).to_be_visible()
    expect(tid(seite, "auswahl-summe")).to_have_attribute("data-betrag", str(100000 - 3000 - 2000))
    expect(tid(seite, "auswahl-einnahmen")).to_have_attribute("data-betrag", "100000")
    assert abs(int(tid(seite, "auswahl-ausgaben").get_attribute("data-betrag"))) == 5000
    zeile(seite, b["aus1"]).click()
    expect(tid(seite, "auswahl-summe")).to_have_attribute("data-betrag", "-3000")


def test_alle_zu_alle_auf_beschriftung(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, _, _ = _konto(api)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}?gruppierung=datum", seitenname="konto")
    expect(tid(seite, "gruppierung-zu")).to_have_attribute("aria-label", "Alles zusammenklappen")
    expect(tid(seite, "gruppierung-auf")).to_have_attribute("aria-label", "Alles aufklappen")
    expect(tid(seite, "gruppierung-zu")).to_have_text("Alle zu")
    expect(tid(seite, "gruppierung-auf")).to_have_text("Alle auf")


# ------------------------------------------------------------------ 41.7 Tags


def test_tags_seite(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, _, b = _konto(api)
    t = api.tag("Urlaub")["id"]
    leer = api.tag("Leer")["id"]
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [b["aus1"], b["aus2"]], "hinzufuegen": [t],
                                                    "entfernen": []}, erwartet=200)
    seite = neue_seite(server)
    oeffnen(seite, server, "/tags", seitenname="tags")
    for i in (t, leer):
        expect(tid(seite, f"tag-umbenennen-{i}")).to_be_visible()
        expect(tid(seite, f"tag-loeschen-{i}")).to_be_visible()
    tid(seite, "seite-tags").get_by_text("Urlaub", exact=True).first.click()
    warte(seite, lambda: m28.abfrage(seite).get("tag") == [str(t)], text="?tag= in der Adresse")
    expect(tid(seite, "seite-tags")).to_contain_text("Einkauf 2")
    oeffnen(seite, server, f"/tags?tag={t}", seitenname="tags")
    expect(tid(seite, "seite-tags")).to_contain_text("Einkauf 1")
    assert "/konten/" not in seite.url, "kein Kontoblatt"


# ------------------------------------------------------------------ 41.8 Einzelheiten im Änderungsprotokoll


def test_einzelheiten_einer_aenderung(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, _, b = _konto(api)
    api.patch(f"/api/buchungen/{b['aus1']}", json={"verwendungszweck": "Geändert für das Protokoll"}, erwartet=200)
    a = m8.max_aenderung(api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/protokoll", seitenname="protokoll")
    tid(seite, f"aenderung-einzelheiten-{a}").click()
    d = tid(seite, "aenderung-dialog")
    expect(d).to_be_visible()
    expect(d.get_by_test_id(f"ae-eintrag-buchung-{b['aus1']}")).to_be_visible()
    expect(d.get_by_test_id(f"ae-eintrag-buchung-{b['aus1']}")).to_contain_text("Geändert für das Protokoll")


# ------------------------------------------------------------------ 41.9 Erfolgsmeldung


@pytest.mark.parametrize("eingeschaltet", [False, True])
def test_erfolgsmeldung_nur_mit_einstellung(starte_server, neue_seite, eingeschaltet):
    server = starte_server()
    api = server.api
    g, _, b = _konto(api)
    seite = neue_seite(server, erfolgsmeldung=eingeschaltet)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    a0 = m8.max_aenderung(api)
    _zweck_bearbeiten(seite, b["aus2"], "Meldung oder nicht")
    warte_bis(lambda: m8.max_aenderung(api) > a0, text="Änderung gespeichert")
    knopf = tid(seite, "meldungen").get_by_test_id("meldung-rueckgaengig")
    if eingeschaltet:
        expect(knopf.last).to_be_visible()
    else:
        seite.wait_for_timeout(500)   # Meldungen erscheinen sofort nach dem Speichern (kein Zustand zum Warten)
        expect(knopf).to_have_count(0)
    expect(tid(seite, "rueckgaengig-knopf")).to_be_attached()


# ------------------------------------------------------------------ 41.10 Mail-Blatt


def _mail_server(starte_server, tmp_path):
    mails = [nachricht(SHOP, "Rechnung Mai", "Betrag 30,00 €", "2024-06-01T08:00:00Z"),
             nachricht(SHOP, "Newsletter", "Angebote", "2024-06-02T08:00:00Z")]
    datei = mock_datei(tmp_path / "mails.json", mails)
    server = starte_server(mock_daten=datei, mail_erstabruf_tage=365)   # W-026 (E-313): m8.HEUTE ist 2024-12-31
    from tests.hilfen.m6 import EINS, postfach
    postfach(server.api, EINS)
    abruf(server.api)
    return server, {m["betreff"]: m["id"] for m in nachrichten(server.api)}


def test_mail_suche_in_der_adresse(starte_server, neue_seite, tmp_path):
    server, ids = _mail_server(starte_server, tmp_path)
    seite = neue_seite(server)
    oeffnen(seite, server, "/mail", seitenname="mail")
    tid(seite, "mail-suche").fill("rechnung")
    tid(seite, "mail-suche").press("Enter")
    expect(tid(seite, f"mail-{ids['Newsletter']}")).to_have_count(0)
    expect(tid(seite, f"mail-{ids['Rechnung Mai']}")).to_be_visible()
    warte(seite, lambda: m28.abfrage(seite).get("suche") == ["rechnung"], text="suche= in der Adresse")


def test_mail_handy_ohne_vorwahl(starte_server, neue_seite, tmp_path):
    server, ids = _mail_server(starte_server, tmp_path)
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, "/mail", seitenname="mail")
    z = tid(seite, f"mail-{ids['Rechnung Mai']}")
    expect(z).to_be_visible()
    expect(tid(seite, "seite-mail").locator('[data-testid^="mail-"][aria-selected="true"]')).to_have_count(0)
    z.click()
    expect(tid(seite, "mail-lesen")).to_be_visible()
    tid(seite, "mail-lesen-schliessen").click()
    expect(tid(seite, "mail-lesen")).to_be_hidden()


def test_mail_zuordnen_knopf(starte_server, neue_seite, tmp_path):
    server, ids = _mail_server(starte_server, tmp_path)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/mail?id={ids['Rechnung Mai']}", seitenname="mail")
    expect(tid(seite, "mail-zuordnen")).to_be_visible()
    for i in ids.values():
        g = tid(seite, f"mail-{i}").get_attribute("data-gruppe-rolle")
        assert g in (None, "kopf", "folge", "ende"), g


# ------------------------------------------------------------------ 41.11 Handy-Kontoblatt


@pytest.mark.parametrize("geraet", ["desktop", "handy"])
def test_handy_kontoblatt_eingeklappt(starte_server, neue_seite, geraet):
    server = starte_server()
    api = server.api
    g, _, _ = _konto(api)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    teile = ["filter-ausdruck", "filter-schnell-dieser_monat", "gruppierung-keine"]
    if geraet == "desktop":
        for t in teile:
            expect(tid(seite, t)).to_be_visible()
        return
    for t in teile:
        expect(tid(seite, t)).to_be_hidden()
    expect(tid(seite, m8.FILTER_UMSCHALTER)).to_be_visible()
    knopf = tid(seite, "ansicht-umschalten")
    expect(knopf).to_have_attribute("aria-expanded", "false")
    knopf.click()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    for t in teile:
        expect(tid(seite, t)).to_be_visible()


# ------------------------------------------------------------------ 41.12 Tabs


def test_andere_tabs_schliessen(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    tabs = m17.leiste(seite).locator('[role="tab"]')
    for ziel in ("konten", "kategorien", "empfaenger", "kredite"):
        m8.navigiere(seite, ziel)
    expect(tabs).to_have_count(5)
    knopf = tid(seite, "tab-andere-schliessen")
    assert knopf.count() == 0 or knopf.is_hidden(), "erst ab sechs Tabs"
    m8.navigiere(seite, "regeln")
    expect(tabs).to_have_count(6)
    expect(knopf).to_be_visible()
    knopf.click()
    expect(tabs).to_have_count(1)
    warte_geladen(seite, "regeln")


# ------------------------------------------------------------------ 41.13 Konfiguration


def test_konfiguration_zeigt_keine_geheimnisse(starte_server, neue_seite, monkeypatch):
    monkeypatch.setenv("KONTOR_NTFY_TOKEN", "tk_synth_geheim_oberflaeche")
    monkeypatch.setenv("KONTOR_LOG_STUFE", "INFO")
    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/konfiguration", seitenname="konfiguration")
    text = tid(seite, "seite-konfiguration").inner_text()
    assert "KONTOR_LOG_STUFE" in text and "KONTOR_NTFY_TOKEN" in text
    assert "tk_synth_geheim_oberflaeche" not in seite.content()
