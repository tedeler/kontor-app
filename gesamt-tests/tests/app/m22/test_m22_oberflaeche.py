"""M22: Spaltenbreiten, Markierung des Bearbeitungsstands und Zusatzmarken der Buchungsliste
(oberflaeche.md 32, E-223, E-224). Nur Browsertests (Playwright wie M8), nicht kern.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

from generator.iban import fiktive_iban
from tests.hilfen import m8
from tests.hilfen.m6 import EINS, abruf, postfach
from tests.hilfen.m8 import ausgewaehlt, oeffnen, tid, warte_bis, warte_liste, zeile
from tests.hilfen.m15 import Mitschnitt, text_normal
from tests.hilfen.m17 import menue_eintraege
from tests.hilfen.m20 import NR, amazon_bestellung, mock_datei

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

FELDER_KONTO = ["datum", "empfaenger", "verwendungszweck", "kategorie", "tags", "status", "betrag", "saldo"]   # D-322: Summe
FELDER_KATEGORIE = ["datum", "empfaenger", "verwendungszweck", "kategorie", "konto", "tags", "status", "betrag",
                    "saldo"]

JS_BREITEN = """felder => felder.map(f => {
    const t = document.querySelector(`[data-testid="spalte-trenner-${f}"]`);
    const kopf = t.closest('[role="columnheader"]');
    const zellen = [...document.querySelectorAll(`[data-testid="buchungsliste"] [role="row"] [data-feld="${f}"]`)];
    return [Math.round(kopf.getBoundingClientRect().width), zellen.map(z => Math.round(z.getBoundingClientRect().width))];
})"""


def _liste(starte_server, neue_seite, geraet="desktop", *, lang="Verwendungszweck", **kw):
    server = starte_server()
    api = server.api
    k = {"giro": api.konto("Girokonto")["id"], "spar": api.konto("Tagesgeld", "sparkonto")["id"],
         "leb": api.konto("Lebensmittel", "aufwand")["id"]}
    for i in range(5):
        api.buchung(f"2024-06-0{i + 1}", [(k["giro"], -100 * (i + 1)), (k["leb"], 100 * (i + 1))],
                    verwendungszweck=f"{lang} {i}" if i else "Ein sehr langer Verwendungszweck " * 4)
    api.buchung("2024-06-07", [(k["spar"], -50), (k["leb"], 50)], verwendungszweck="Spar")
    seite = neue_seite(server, geraet, **kw)
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, k["giro"]))
    return server, api, seite, k


def _breiten(seite, felder=FELDER_KONTO) -> dict[str, tuple[int, list[int]]]:
    return dict(zip(felder, seite.evaluate(JS_BREITEN, felder)))


def _ziehen(seite, feld: str, dx: float) -> None:
    """Zieht den Trenner um ``dx``; er wird vorher in den sichtbaren Bereich gerollt (die Liste darf waagerecht
    blättern, W-012, E-227)."""
    trenner = tid(seite, f"spalte-trenner-{feld}")
    trenner.scroll_into_view_if_needed()
    box = trenner.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    seite.mouse.move(x, y)
    seite.mouse.down()
    schritte = max(1, int(abs(dx) // 20))
    for i in range(1, schritte + 1):
        seite.mouse.move(x + dx * i / schritte, y)
    seite.mouse.up()


# ------------------------------------------------------------------ Trenner (32.1)


def test_trenner_je_spalte_und_mobil_keine(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    for f in FELDER_KONTO:
        t = tid(seite, f"spalte-trenner-{f}")
        expect(t).to_have_attribute("role", "separator")
        expect(t).to_have_attribute("aria-orientation", "vertical")
        kopf = text_normal(t.evaluate("e => e.closest('[role=\"columnheader\"]').textContent"))
        label = t.get_attribute("aria-label") or ""
        assert label.startswith("Breite der Spalte "), label
        titel = label[len("Breite der Spalte "):]
        assert titel and kopf.startswith(titel), (f, kopf, label)  # Kopf ggf. mit Sortiersymbol (E-224)
    reihenfolge = seite.evaluate("""() => [...document.querySelectorAll('[data-testid^="spalte-trenner-"]')]
        .map(e => e.dataset.testid.slice('spalte-trenner-'.length))""")
    assert reihenfolge == FELDER_KONTO
    oeffnen(seite, server, f"/konten/{k['leb']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, k["leb"]))
    reihenfolge = seite.evaluate("""() => [...document.querySelectorAll('[data-testid^="spalte-trenner-"]')]
        .map(e => e.dataset.testid.slice('spalte-trenner-'.length))""")
    assert reihenfolge == FELDER_KATEGORIE
    mobil = neue_seite(server, "handy")
    oeffnen(mobil, server, f"/konten/{k['giro']}", seitenname="konto")
    expect(tid(mobil, "app")).to_have_attribute("data-layout", "mobil")
    assert mobil.locator('[data-testid^="spalte-trenner-"]').count() == 0


def test_klick_und_doppelklick_sortieren_nicht(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    kopf = tid(seite, "spalte-datum").evaluate("e => e.closest('[role=\"columnheader\"]').getAttribute('aria-sort')")
    mit = Mitschnitt(seite)
    mit.leeren()
    anfragen: list[str] = []
    seite.on("request", lambda r: anfragen.append(r.url) if urlsplit(r.url).path == "/api/buchungen" else None)
    tid(seite, "spalte-trenner-datum").click()
    tid(seite, "spalte-trenner-empfaenger").dblclick()
    seite.wait_for_timeout(300)
    assert tid(seite, "spalte-datum").evaluate(
        "e => e.closest('[role=\"columnheader\"]').getAttribute('aria-sort')") == kopf
    assert anfragen == [], "keine neue Abfrage"
    assert mit.schreibend() == []


def test_ziehen_grenzen_und_buendig(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    vorher = _breiten(seite)
    _ziehen(seite, "verwendungszweck", 80)
    nach = _breiten(seite)
    assert abs(nach["verwendungszweck"][0] - (vorher["verwendungszweck"][0] + 80)) <= 1, (vorher, nach)
    for f in FELDER_KONTO:
        if f != "verwendungszweck":
            assert abs(nach[f][0] - vorher[f][0]) <= 1, f"Breite von {f} verändert"
        assert all(abs(z - nach[f][0]) <= 1 for z in nach[f][1]), f"Zellen von {f} nicht bündig mit dem Kopf"
    _ziehen(seite, "datum", -(nach["datum"][0] - 5))
    assert abs(_breiten(seite)["datum"][0] - 40) <= 1, "untere Grenze 40 px"


def test_jede_spalte_laesst_sich_ziehen(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    for f in FELDER_KONTO:
        vorher = _breiten(seite)[f][0]
        _ziehen(seite, f, 30)
        assert abs(_breiten(seite)[f][0] - (vorher + 30)) <= 1, f"Spalte {f} lässt sich nicht verbreitern"
        _ziehen(seite, f, -30)
        assert abs(_breiten(seite)[f][0] - vorher) <= 1, f"Spalte {f} lässt sich nicht verschmälern"


def test_ziehen_obere_grenze_und_waagerecht_blaettern(starte_server, neue_seite):
    """Breites Fenster, damit eine Mausbewegung über 1200 px im Fenster bleibt (E-224)."""
    server, api, seite, k = _liste(starte_server, neue_seite, viewport={"width": 2600, "height": 800})
    _ziehen(seite, "kategorie", 1500)
    breit = _breiten(seite)
    assert abs(breit["kategorie"][0] - 1200) <= 1, "obere Grenze 1200 px"
    _ziehen(seite, "verwendungszweck", 1000)
    roll = seite.evaluate("""() => { let e = document.querySelector('[data-testid="buchungsliste"]');
        while (e && !(e.scrollWidth > e.clientWidth + 1 && /(auto|scroll)/.test(getComputedStyle(e).overflowX)))
            e = e.parentElement;
        return !!e && e !== document.body && e !== document.documentElement; }""")
    assert roll, "breiter als die Liste: waagerecht blätterbar"


def test_doppelklick_passt_an_den_inhalt(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    _ziehen(seite, "verwendungszweck", -3000)
    tid(seite, "spalte-trenner-verwendungszweck").dblclick()
    seite.wait_for_timeout(200)
    abgeschnitten = seite.evaluate("""() => [...document.querySelectorAll(
        '[data-testid="buchungsliste"] [role="row"] [data-feld="verwendungszweck"]')]
        .filter(z => z.scrollWidth > z.clientWidth + 1).length""")
    assert abgeschnitten == 0, "nach dem Doppelklick ist kein Text der Spalte abgeschnitten"
    b = _breiten(seite)["verwendungszweck"][0]
    assert 40 <= b <= 1200


def test_kopfmenue_anpassen_und_zuruecksetzen(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    vorgabe = _breiten(seite)
    erste = m8.rest_liste(api, k["giro"])[0]
    zeile(seite, erste).click()
    assert ausgewaehlt(seite) == {erste}
    kopf = tid(seite, "spalte-datum").evaluate_handle("e => e.closest('[role=\"row\"]')")
    kopf.as_element().click(button="right")
    eintraege = menue_eintraege(seite)
    assert {"km-spalten-anpassen", "km-spalten-zuruecksetzen"} <= set(eintraege)
    assert not any(e in eintraege for e in ("km-loeschen", "km-mehrfach", "km-gegenbuchung")), "kein Buchungsmenü"
    expect(tid(seite, "kontextmenue").get_by_test_id("km-spalten-zuruecksetzen")).to_have_attribute(
        "aria-disabled", "true")
    tid(seite, "kontextmenue").get_by_test_id("km-spalten-anpassen").click()
    assert ausgewaehlt(seite) == {erste}, "Auswahl bleibt"
    abgeschnitten = seite.evaluate("""() => [...document.querySelectorAll(
        '[data-testid="buchungsliste"] [role="row"] [data-feld]')].filter(z => z.scrollWidth > z.clientWidth + 1)
        .map(z => z.dataset.feld)""")
    assert abgeschnitten == [], abgeschnitten
    kopf.as_element().click(button="right")
    z = tid(seite, "kontextmenue").get_by_test_id("km-spalten-zuruecksetzen")
    assert z.get_attribute("aria-disabled") != "true"
    z.click()
    zurueck = _breiten(seite)
    for f in FELDER_KONTO:
        assert abs(zurueck[f][0] - vorgabe[f][0]) <= 1, f"{f}: Vorgaberaster nach dem Zurücksetzen"


def test_speicherung_je_listenart(starte_server, neue_seite):
    server, api, seite, k = _liste(starte_server, neue_seite)
    vorgabe_kat = None
    oeffnen(seite, server, f"/konten/{k['leb']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, k["leb"]))
    vorgabe_kat = _breiten(seite, FELDER_KATEGORIE)
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, k["giro"]))
    mit = Mitschnitt(seite)
    mit.leeren()
    _ziehen(seite, "empfaenger", 60)
    gezogen = _breiten(seite)["empfaenger"][0]
    assert mit.schreibend() == [], "keine REST-Anfrage für Breiten"
    assert seite.evaluate("() => localStorage.getItem('kontor.spalten')") is not None
    seite.reload()
    warte_liste(seite, m8.rest_liste(api, k["giro"]))
    assert abs(_breiten(seite)["empfaenger"][0] - gezogen) <= 1, "nach Neuladen gleich"
    oeffnen(seite, server, f"/konten/{k['spar']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, k["spar"]))
    assert abs(_breiten(seite)["empfaenger"][0] - gezogen) <= 1, "alle Bestandskonten gemeinsam"
    oeffnen(seite, server, f"/konten/{k['leb']}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, k["leb"]))
    kat = _breiten(seite, FELDER_KATEGORIE)
    assert all(abs(kat[f][0] - vorgabe_kat[f][0]) <= 1 for f in FELDER_KATEGORIE), "andere Listenart unberührt"


@pytest.mark.parametrize("fall", ["ungueltig", "wirft"])
def test_speicher_ungueltig_oder_nicht_verfuegbar(starte_server, neue_seite, fall):
    server = starte_server()
    api = server.api
    g = api.konto("Girokonto")["id"]
    leb = api.konto("Lebensmittel", "aufwand")["id"]
    api.buchung("2024-06-01", [(g, -100), (leb, 100)])
    seite = neue_seite(server)
    if fall == "ungueltig":
        seite.add_init_script("localStorage.setItem('kontor.spalten', '{kaputt'); ")
    else:
        seite.add_init_script("""(() => { const o = Storage.prototype.getItem, s = Storage.prototype.setItem;
            Storage.prototype.getItem = function (k) { if (k === 'kontor.spalten') throw new Error('gesperrt');
                return o.call(this, k); };
            Storage.prototype.setItem = function (k, v) { if (k === 'kontor.spalten') throw new Error('gesperrt');
                return s.call(this, k, v); }; })();""")
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    vorher = _breiten(seite)
    _ziehen(seite, "verwendungszweck", 50)
    assert abs(_breiten(seite)["verwendungszweck"][0] - (vorher["verwendungszweck"][0] + 50)) <= 1


# ------------------------------------------------------------------ Markierung (32.2)


def _sync_daten(tmp_path) -> tuple[str, list[dict], list[dict]]:
    iban = fiktive_iban(7802)
    konto = {"iban": iban, "bic": None, "name": "Girokonto", "art": "girokonto", "inhaber": "Erika Fiktiv",
             "waehrung": "EUR"}
    ums = [{"umsatz_id": f"U-{i}", "iban": iban, "buchungstag": f"2024-06-1{i}", "valuta": f"2024-06-1{i}",
            "betrag": -(100 + i), "waehrung": "EUR", "gegenpartei_name": f"Laden {i} (fiktiv)", "gegenpartei_iban": None,
            "verwendungszweck": f"Einkauf {i}", "vormerkung": False, "storno": False} for i in range(4)]
    return iban, [konto], ums


def test_markierung_rangfolge_und_darstellung(starte_server, neue_seite, tmp_path):
    iban, konten, ums = _sync_daten(tmp_path)
    datei = mock_datei(tmp_path / "bank.json", [], konten=konten, umsaetze=ums)
    server = starte_server(mock_daten=datei)
    api = server.api
    assert api.post("/api/sync", json={"von": "2024-06-01"}, erwartet=200).daten["status"] == "erfolgreich"
    g = next(x["id"] for x in api.konten() if x["iban"] == iban)
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    leb = api.konto("Lebensmittel", "aufwand")["id"]
    unk = next(x["id"] for x in api.konten() if x["extern_id"] == "kontor:unkategorisiert")
    b = {x["verwendungszweck"]: x["id"] for x in api.alle_buchungen(konto_id=g)}
    imp, vorl, best, abgl = b["Einkauf 0"], b["Einkauf 1"], b["Einkauf 2"], b["Einkauf 3"]
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [vorl], "status": "vorlaeufig"}, erwartet=200)
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [best], "status": "bestaetigt"}, erwartet=200)
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [abgl], "status": "abgeglichen"}, erwartet=200)
    kat_imp = api.buchung("2024-06-20", [(g, -10), (leb, 10)], status="importiert")["id"]
    umb = api.buchung("2024-06-21", [(g, -20), (spar, 20)])["id"]
    split = api.buchung("2024-06-22", [(g, -30), (leb, 10), (unk, 20)], status="bestaetigt")["id"]
    kasse = api.konto("Kasse (fiktiv)", "sparkonto")["id"]
    abst = api.buchung("2024-06-01", [(kasse, 500), (leb, -500)], status="bestaetigt")["id"]
    api.post("/api/abstimmungen", json={"konto_id": kasse, "stichtag": "2024-06-01", "saldo": 500}, erwartet=200)
    # D-254: Markierung nach Status; die Kategorie spielt keine Rolle mehr
    soll = {imp: "importiert", vorl: "vorlaeufig", best: "bestaetigt", abgl: "abgeglichen", kat_imp: "importiert",
            umb: "bestaetigt", split: "bestaetigt"}
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    for bid, wert in soll.items():
        assert zeile(seite, bid).get_attribute("data-markierung") == wert, (bid, wert)
    hintergrund = {}
    for bid in (imp, vorl, best):
        hintergrund[soll[bid]] = zeile(seite, bid).evaluate(
            "e => { const s = getComputedStyle(e); return s.backgroundImage + '|' + s.backgroundColor; }")
    assert len(set(hintergrund.values())) == 3, f"drei Werte optisch unterscheidbar: {hintergrund}"
    oeffnen(seite, server, f"/konten/{kasse}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, kasse))
    assert zeile(seite, abst).get_attribute("data-markierung") == "abgeglichen", "abgestimmt zählt als abgeglichen"
    # Markierung folgt Änderungen (neu geladene Liste)
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [imp], "status": "bestaetigt"}, erwartet=200)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    expect(zeile(seite, imp)).to_have_attribute("data-markierung", "bestaetigt")
    mobil = neue_seite(server, "handy")
    oeffnen(mobil, server, f"/konten/{g}", seitenname="konto")
    expect(zeile(mobil, abgl)).to_have_attribute("data-markierung", "abgeglichen")


# ------------------------------------------------------------------ Zusatzmarken (32.3)


def test_zusatzmarken_wiederkehrend_und_mail(starte_server, neue_seite, tmp_path):
    nr2 = "303-7654321-1234567"
    datei = mock_datei(tmp_path / "mails.json", [amazon_bestellung(empfangen="2024-12-01T08:00:00Z"),
                                                 amazon_bestellung(nr2, empfangen="2024-12-01T09:00:00Z")])
    server = starte_server(mock_daten=datei, mail_erstabruf_tage=365, mail_abgleich=True)
    api = server.api
    g = api.konto("Girokonto")["id"]
    leb = api.konto("Medien", "aufwand")["id"]
    dienst = api.empfaenger("Streamingdienst (fiktiv)")["id"]
    serie = [api.buchung(f"2024-{m:02d}-15", [(g, -999), (leb, 999)], empfaenger_id=dienst,
                         verwendungszweck="Abo")["id"] for m in range(7, 13)]
    laden = api.empfaenger("AMAZON EU (fiktiv)")["id"]
    mailb = api.buchung("2024-12-02", [(g, -4990), (leb, 4990)], empfaenger_id=laden,
                        verwendungszweck=f"Amazon {nr2}")["id"]
    manuell_b = api.buchung("2024-12-03", [(g, -123), (leb, 123)], verwendungszweck="Manuell")["id"]
    ohne = api.buchung("2024-12-04", [(g, -5), (leb, 5)], verwendungszweck="Nichts")["id"]
    postfach(api, EINS)
    abruf(api)
    best = {x["kennung"]: x for x in api.get("/api/erwartungen", params=[("zustand", "offen"), ("zustand", "erfuellt")],
                                             erwartet=200).daten["eintraege"]}
    if mailb not in best[nr2]["buchung_ids"]:
        api.post(f"/api/erwartungen/{best[nr2]['id']}/buchungen", json={"buchung_ids": [mailb]}, erwartet=200)
    beide = serie[-1]
    api.post(f"/api/erwartungen/{best[NR]['id']}/buchungen", json={"buchung_ids": [beide]}, erwartet=200)
    m = api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Fiktiv", "betrag": 123,
                                           "datum": "2024-12-03"}, erwartet=201).daten
    api.post(f"/api/erwartungen/{m['id']}/buchungen", json={"buchung_ids": [manuell_b]}, erwartet=200)
    wk = {bid for s in api.get("/api/wiederkehrend", erwartet=200).daten["serien"] for bid in s["buchung_ids"]}
    assert set(serie) <= wk, "Testvoraussetzung: Serie erkannt"
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))

    def zelle(bid):
        return zeile(seite, bid).locator('[data-feld="empfaenger"]')
    # M28 (oberflaeche.md 37.4, E-254): keine Marke „wiederkehrend“ mehr; nur die Mail-Marke
    for bid in serie[:-1]:
        assert zeile(seite, bid).get_attribute("data-wiederkehrend") is None
        assert zeile(seite, bid).get_attribute("data-mail") is None
        assert text_normal(zelle(bid).text_content()) == "Streamingdienst (fiktiv)", "Text der Zelle unverändert"
        assert "wiederkehrend" not in (zelle(bid).get_attribute("title") or "")
    expect(zeile(seite, mailb)).to_have_attribute("data-mail", "ja")
    assert zeile(seite, mailb).get_attribute("data-wiederkehrend") is None
    assert zelle(mailb).get_attribute("title") == f"AMAZON EU (fiktiv) – durch Mail bestätigt: Bestellung Amazon {nr2}"
    assert text_normal(zelle(mailb).text_content()) == "AMAZON EU (fiktiv)"
    expect(zeile(seite, beide)).to_have_attribute("data-mail", "ja")
    assert zeile(seite, beide).get_attribute("data-wiederkehrend") is None
    assert zelle(beide).get_attribute("title") == (
        f"Streamingdienst (fiktiv) – durch Mail bestätigt: Bestellung Amazon {NR}")
    for bid in (manuell_b, ohne):
        assert zeile(seite, bid).get_attribute("data-mail") is None, "manuelle Erwartungen setzen die Marke nicht"
        assert zeile(seite, bid).get_attribute("data-wiederkehrend") is None


def test_marke_fehlt_wenn_abgleich_aus(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g = api.konto("Girokonto")["id"]
    leb = api.konto("Medien", "aufwand")["id"]
    b = api.buchung("2024-12-02", [(g, -100), (leb, 100)], verwendungszweck="x")["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, [b])
    assert zeile(seite, b).get_attribute("data-mail") is None
    assert zeile(seite, b).locator('[data-feld="empfaenger"]').get_attribute("title") in (None, "")
