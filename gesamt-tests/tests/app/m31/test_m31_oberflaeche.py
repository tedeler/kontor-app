"""M31: Oberfläche – Namen in normaler Schreibweise, Einschätzung des Lernmodells, Route ``/lernmodell``,
Einstellungen in Bereichen, Datum angehängter E-Mails, Gruppierung mit Abschnitt und Tiefe, Berichtswahl
(oberflaeche.md 40; E-286 bis E-288).

Playwright wie M8 (E-139), nicht kern. Geprüft wird nur, was die Definition nennt; Erwartungen über REST und
eigene Rechnung (``tests/hilfen/m28.perioden_soll``, ``m31.vorhersage_soll``).
"""

from __future__ import annotations

import re

import pytest

from tests.hilfen import kontor, m8, m17, m28, m31
from tests.hilfen.lern_orakel import merkmale
from tests.hilfen.m4 import Buch
from tests.hilfen.m6 import EINS, abruf, nachrichten, postfach
from tests.hilfen.m8 import oeffnen, tid, warte_liste, zeile
from tests.hilfen.m17 import warte
from tests.hilfen.m18 import anhaengen, mock_datei, pdf
from tests.hilfen.m31 import BEREICHE, LEITELEMENT, einstellungen_oeffnen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect
ZUSTAENDE = re.compile("^(ok|offen|fehler|neutral)$")
ARTEN = ("uebersicht", "monat", "vertraege", "jahr", "vorschau", "vermoegen", "kategorien", "empfaenger",
         "geldfluss", "qualitaet", "tags")


# ------------------------------------------------------------------ 40.1 Namen


def test_namen_in_normaler_schreibweise(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, k = api.konto("Girokonto")["id"], api.konto("Einkauf", "aufwand")["id"]
    ids = {}
    for name in ("AMAZON", "CAFE AM MARKT", "eBay GmbH"):
        e = api.empfaenger(name)["id"]
        ids[name] = api.buchung("2024-12-01", [(g, -1234), (k, 1234)], empfaenger_id=e,
                                verwendungszweck="Posten")["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, g))
    for name, soll in (("AMAZON", "Amazon"), ("CAFE AM MARKT", "Cafe am Markt"), ("eBay GmbH", "eBay GmbH")):
        text = zeile(seite, ids[name]).inner_text()
        assert soll in text, (name, text)
        if soll != name:
            assert name not in text, f"{name} wird in normaler Schreibweise gezeigt"
    zeile(seite, ids["AMAZON"]).click()
    expect(tid(seite, "details-betrag")).to_have_attribute("data-betrag", "-1234")
    assert api.get(f"/api/empfaenger/{api.buchung_lesen(ids['AMAZON'])['empfaenger']['id']}",
                   erwartet=200).daten["name"] == "AMAZON", "gespeichert wie erfasst"


# ------------------------------------------------------------------ 40.2 Lernmodell


def test_einschaetzung_ohne_vorschlag(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    b = Buch(api)
    for _ in range(2):
        b.einfach("Markt Fiktiv", "Einkauf Woche", -2500, "Lebensmittel")
    b.einfach("Markt Fiktiv", "Einkauf Kaffee", -2500, "Café")
    b.einfach("Tankstelle Fiktiv", "Diesel", -6000, "Tanken")
    offen = b.einfach("Markt Fiktiv", "Einkauf", -2500, None)
    soll = m31.vorhersage_soll(b.modell(), merkmale("Markt Fiktiv", "Einkauf", -2500))
    assert soll["kategorie_id"] is None and soll["kandidaten"], "Voraussetzung: unter der Schwelle"
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{b.giro}?buchung={offen['id']}", seitenname="konto")
    warte(seite, lambda: m8.ausgewaehlt(seite) == {offen["id"]}, text="Sprungziel ausgewählt")
    expect(tid(seite, "details-einschaetzung")).to_be_visible()
    expect(tid(seite, "details-einschaetzung-grund")).to_be_visible()
    expect(tid(seite, "details-einschaetzung-kandidaten")).to_be_visible()
    for kand in soll["kandidaten"]:
        loc = tid(seite, f"details-kandidat-{kand['kategorie_id']}")
        if kand["sicherheit"] >= 10:
            expect(loc).to_be_visible()
        else:
            expect(loc).to_have_count(0)
    expect(tid(seite, "lern-warum")).to_be_attached()


def test_route_lernmodell_ohne_navigationseintrag(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/lernmodell")
    assert seite.url.endswith("/lernmodell")
    expect(tid(seite, "nav-lernmodell")).to_have_count(0)
    expect(tid(seite, "navigation").locator('a[href="/lernmodell"]')).to_have_count(0)
    for testid, _ in m8.NAV_LINKS:
        expect(tid(seite, testid)).to_have_count(1)
    oeffnen(seite, server, "/regeln", seitenname="regeln")
    expect(tid(seite, "lernmodell-anwenden")).to_have_text(re.compile("Vorschläge für unkategorisierte Buchungen"))


# ------------------------------------------------------------------ 40.3 Einstellungen in Bereichen


def _server(starte_server, **felder):
    """Server mit eingerichtetem Haushaltspasswort, damit der Abschnitt „Schutz der Geheimnisse“ (M23) Inhalt hat."""
    server = starte_server(**felder)
    anm = kontor.modul("kontor.anmeldung")
    if not anm.ist_eingerichtet(server.config):
        anm.passwort_setzen(server.config, "Synthetisch-Fiktiv-2026")
    return server


def _nur_sichtbar(seite, bereich: str | None) -> None:
    for b, element in LEITELEMENT.items():
        if b == bereich:
            expect(tid(seite, element)).to_be_visible()
        else:
            expect(tid(seite, element)).to_be_hidden()


def test_bereiche_desktop(starte_server, neue_seite):
    server = _server(starte_server)
    seite = neue_seite(server)
    for b in BEREICHE:
        einstellungen_oeffnen(seite, server, b)
        _nur_sichtbar(seite, b)
        expect(tid(seite, "einstellungen-suche")).to_be_visible()
        for x in BEREICHE:
            expect(tid(seite, f"einstellungen-status-{x}")).to_have_attribute("data-zustand", ZUSTAENDE)
    assert [p for p in m17.pfade(seite) if p.startswith("/einstellungen")] == ["/einstellungen"], "ein Tab"


@pytest.mark.parametrize("abfrage", ["", "?bereich=unbekannt"])
def test_ohne_bereich_desktop_allgemein(starte_server, neue_seite, abfrage):
    server = _server(starte_server)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/einstellungen{abfrage}", seitenname="einstellungen")
    _nur_sichtbar(seite, "allgemein")


def test_ohne_bereich_mobil_nur_die_liste(starte_server, neue_seite):
    server = _server(starte_server)
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, "/einstellungen", seitenname="einstellungen")
    _nur_sichtbar(seite, None)
    einstellungen_oeffnen(seite, server, "bank")
    _nur_sichtbar(seite, "bank")


def test_erweitert_offen_ohne_produkt_id(starte_server, neue_seite):
    server = starte_server(mock=False)
    seite = neue_seite(server)
    einstellungen_oeffnen(seite, server, "bank")
    expect(tid(seite, "bankzugang")).to_be_visible()
    expect(tid(seite, "bankzugang-produkt_id")).to_be_visible()   # Pflichtfeld leer: „Erweitert“ offen
    server.api.put("/api/bank/zugang", json={"produkt_id": "KONTOR-TEST-PRODUKT"}, erwartet=200)
    einstellungen_oeffnen(seite, server, "bank")
    expect(tid(seite, "bankzugang-produkt_id")).to_be_hidden()    # nichts fehlt, nichts läuft: eingeklappt


# ------------------------------------------------------------------ 40.4 Datum der E-Mail


def test_datum_angehaengter_mails(starte_server, neue_seite, tmp_path):
    mails = [{"nachricht_id": "M-1", "postfach": EINS, "empfangen": "2024-06-03T08:15:00Z",
              "absender": "Fiktiver Shop <shop@example.invalid>", "betreff": "Rechnung (fiktiv)", "text": "Danke."}]
    server = starte_server(mock_daten=mock_datei(tmp_path / "mails.json", mails, [EINS]), mail_erstabruf_tage=365)
    api = server.api
    g, k = api.konto("Girokonto")["id"], api.konto("Einkauf", "aufwand")["id"]
    bid = api.buchung("2024-06-02", [(g, -500), (k, 500)], verwendungszweck="Einkauf")["id"]
    postfach(api, EINS)
    abruf(api)
    (n,) = nachrichten(api)
    md = api.post("/api/dokumente/aus-mail", json={"nachricht_id": n["id"], "buchung_ids": [bid]}, erwartet=201).daten
    pd = anhaengen(api, [bid], "beleg.pdf", pdf("Beleg"))
    datum = api.get(f"/api/dokumente/{md['id']}/mail", erwartet=200).daten["datum"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}?buchung={bid}", seitenname="konto")
    feld = tid(seite, f"dokument-datum-{md['id']}")
    expect(feld).to_be_visible()
    expect(feld).to_have_attribute("data-zeitpunkt", datum)
    expect(feld).to_have_text(re.compile(r"\d{2}\.\d{2}\.\d{4}"))
    expect(tid(seite, f"dokument-datum-{pd['id']}")).to_have_count(0)


# ------------------------------------------------------------------ 40.5 Gruppierung

KNOEPFE = {"keine": "gruppierung-keine", "jahr": "gruppierung-jahr", "monat": "gruppierung-monat",
           "abschnitt": "gruppierung-abschnitt", "tag": "gruppierung-datum"}


def _gruppierung_start(starte_server, neue_seite, abfrage=""):
    server = starte_server()
    d = m17.daten(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{d['k']['giro']}{abfrage}", seitenname="konto")
    alle = server.api.alle_buchungen(konto_id=d["k"]["giro"], sortierung="-datum")
    return server, seite, d, alle


def _gedrueckt(seite, tiefe: str) -> None:
    for t, knopf in KNOEPFE.items():
        expect(tid(seite, knopf)).to_have_attribute("aria-pressed", "true" if t == tiefe else "false")


def _pruefe_tiefe(seite, alle, tiefe: str) -> None:
    soll = m28.perioden_soll(alle, tiefe=tiefe)
    warte(seite, lambda: sorted(m28.balken(seite)) == sorted((x["ebene"], s) for s, x in soll.items()),
          text=f"Balken der Tiefe {tiefe}")
    for s, x in soll.items():
        expect(tid(seite, f"periode-summe-{s}")).to_have_attribute("data-betrag", str(x["summe"]))
        expect(tid(seite, f"periode-anzahl-{s}")).to_have_attribute("data-anzahl", str(x["anzahl"]))
        if x["ebene"] == "abschnitt":
            expect(tid(seite, f"periode-{s}")).to_contain_text(m28.perioden_text(s))


def test_leiste_und_tiefen(starte_server, neue_seite):
    server, seite, d, alle = _gruppierung_start(starte_server, neue_seite)
    expect(seite.get_by_role("group", name="Buchungen gruppieren")).to_be_visible()
    _gedrueckt(seite, "keine")
    for tiefe in ("jahr", "monat", "abschnitt", "tag"):
        tid(seite, KNOEPFE[tiefe]).click()
        _gedrueckt(seite, tiefe)
        soll_tiefe = None if tiefe == "tag" else [tiefe]
        warte(seite, lambda: m28.abfrage(seite).get("gruppierung") == ["datum"]
              and m28.abfrage(seite).get("tiefe") == soll_tiefe, text=f"Adresse mit tiefe={soll_tiefe}")
        _pruefe_tiefe(seite, alle, tiefe)
    tid(seite, KNOEPFE["keine"]).click()
    _gedrueckt(seite, "keine")
    warte(seite, lambda: "gruppierung" not in m28.abfrage(seite), text="ohne Gruppierung")
    assert m28.balken(seite) == []


@pytest.mark.parametrize("tiefe,soll", [("abschnitt", "abschnitt"), ("jahr", "jahr"), ("woche", "tag")])
def test_tiefe_aus_der_adresse(starte_server, neue_seite, tiefe, soll):
    server, seite, d, alle = _gruppierung_start(starte_server, neue_seite, f"?gruppierung=datum&tiefe={tiefe}")
    _gedrueckt(seite, soll)
    _pruefe_tiefe(seite, alle, soll)


def test_v_g_schaltet_der_reihe_nach(starte_server, neue_seite):
    server, seite, d, alle = _gruppierung_start(starte_server, neue_seite)
    warte_liste(seite, m8.rest_liste(server.api, d["k"]["giro"]))
    for tiefe in ("jahr", "monat", "abschnitt", "tag", "keine"):
        ziel = m8.zellen_ids(seite)[0]
        zeile(seite, ziel).locator('[data-feld="betrag"]').click()
        seite.keyboard.press("v")
        seite.keyboard.press("g")
        _gedrueckt(seite, tiefe)


def test_zugeklappt_bleibt_beim_wechsel_der_tiefe(starte_server, neue_seite):
    server, seite, d, alle = _gruppierung_start(starte_server, neue_seite, "?gruppierung=datum")
    _pruefe_tiefe(seite, alle, "tag")
    jahr = max(b["datum"][:4] for b in alle)
    tid(seite, f"periode-{jahr}").click()
    expect(tid(seite, f"periode-{jahr}")).to_have_attribute("aria-expanded", "false")
    tid(seite, KNOEPFE["monat"]).click()
    _gedrueckt(seite, "monat")
    expect(tid(seite, f"periode-{jahr}")).to_have_attribute("aria-expanded", "false")


# ------------------------------------------------------------------ 40.6 Berichtswahl


def test_berichtswahl(starte_server, neue_seite):
    server = starte_server()
    m17.daten(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/berichte/monat")
    warte(seite, lambda: m28.abfrage(seite).get("art") == ["monat"], text="/berichte/monat → ?art=monat")
    for art in ARTEN:
        oeffnen(seite, server, f"/berichte?art={art}", seitenname="berichte")
    assert [p for p in m17.pfade(seite) if p.startswith("/berichte")] == ["/berichte"], "ein Tab"
