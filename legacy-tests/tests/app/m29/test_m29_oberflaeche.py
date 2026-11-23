"""M29: Abschnitt ``bankzugang`` der Einstellungen (oberflaeche.md 38, E-265) – Playwright wie M8; nicht kern.

Geprüft wird nur, was die Definition nennt: ``data-testid``, Attribute, Sichtbarkeit, Werte und die Wirkung über
REST. Texte sind frei (Ausnahme: die Anzahl der Konten als Zahl in der Statuszeile).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.hilfen.fints_attrappe import FintsAttrappe
from tests.hilfen.m6 import PRODUKT, fints_daten, fints_felder, pin_setzen
from tests.hilfen.m8 import tid, warte_bis
from tests.hilfen.m15 import Mitschnitt
from tests.hilfen.m29 import ZUSATZ_VERFAHREN, bankzugang_oeffnen, diagnose, soll_konten, zugang

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

URL = "https://banking.example.invalid/fints"
VORBELEGUNG = {"bank_plugin": "fints", "fints_url": URL, "fints_blz": "00000000", "fints_benutzer": "SYNTH-NUTZER",
               "fints_produkt_id": PRODUKT}
NUR_AENDERBAR = ["bankzugang-url", "bankzugang-blz", "bankzugang-benutzer", "bankzugang-kunden_id",
                 "bankzugang-produkt_id", "bankzugang-tan-verfahren", "bankzugang-speichern", "bankzugang-pin",
                 "bankzugang-pin-senden", "bankzugang-pin-status", "bankzugang-verfahren-abrufen",
                 "bankzugang-konten-abrufen", "bankzugang-meldung", "bankzugang-tan", "bankzugang-konten",
                 "bankzugang-konten-speichern", "bankzugang-diagnose", "bankzugang-diagnose-aktiv",
                 "bankzugang-diagnose-laden", "bankzugang-diagnose-kopieren", "bankzugang-diagnose-zeilen"]


@pytest.fixture(scope="module")
def bank():
    return fints_daten()


def _echt(starte_server, **felder):
    return starte_server(mock=False, heute=None, **felder)


def _mit_bank(starte_server, a, daten, *, pin: bool = True):
    server = _echt(starte_server, **fints_felder(a, daten))
    if pin:
        pin_setzen(server.api, daten["pin"])
    return server


def _speicher(seite) -> str:
    return seite.evaluate("() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])")


def _kein_speicher(seite, *werte: str) -> None:
    """Der Abschnitt nutzt keinen Browser-Speicher: keine der Angaben, kein Schlüssel mit ``bank`` (E-265)."""
    roh = _speicher(seite)
    for w in werte:
        assert w not in roh, f"{w!r} im Browser-Speicher"
    for bereich in json.loads(roh):
        assert not [k for k, _ in bereich if "bank" in k.lower()], f"Schlüssel des Bankzugangs im Browser-Speicher: {bereich}"


def _konten(seite):
    return tid(seite, "bankzugang-konten").get_by_test_id("bankzugang-konto")


def _ibans(seite) -> list[str]:
    return _konten(seite).evaluate_all("els => els.map(e => e.getAttribute('data-iban'))")


# ------------------------------------------------------------------ Mock-Modus: nur der Hinweis
def test_mock_modus_nur_hinweis(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    abschnitt = bankzugang_oeffnen(seite, server)
    expect(abschnitt).to_have_attribute("data-aenderbar", "nein")
    expect(abschnitt).to_have_attribute("data-vollstaendig", re.compile("^(ja|nein)$"))
    expect(abschnitt.get_by_test_id("bankzugang-hinweis")).to_be_visible()
    for x in NUR_AENDERBAR:
        assert seite.get_by_test_id(x).count() == 0, f"{x} darf es im Mock-Modus nicht geben"


# ------------------------------------------------------------------ Felder, Speichern
def test_felder_vorbelegt_mit_den_wirksamen_werten(starte_server, neue_seite):
    server = _echt(starte_server, **VORBELEGUNG, fints_kunden_id="SYNTH-KUNDE", fints_tan_verfahren="913")
    seite = neue_seite(server)
    abschnitt = bankzugang_oeffnen(seite, server)
    expect(abschnitt).to_have_attribute("data-aenderbar", "ja")
    expect(abschnitt).to_have_attribute("data-vollstaendig", "ja")
    for feld, wert in (("url", URL), ("blz", "00000000"), ("benutzer", "SYNTH-NUTZER"), ("kunden_id", "SYNTH-KUNDE"),
                       ("produkt_id", PRODUKT)):
        expect(tid(seite, f"bankzugang-{feld}")).to_have_value(wert)
    auswahl = tid(seite, "bankzugang-tan-verfahren")
    expect(auswahl).to_have_value("913")
    werte = auswahl.locator("option").evaluate_all("els => els.map(e => e.value)")
    assert werte[0] == "" and "913" in werte, "erster Eintrag automatisch (leerer Wert), dazu der gespeicherte Wert"
    expect(tid(seite, "bankzugang-pin")).to_have_attribute("type", "password")
    expect(tid(seite, "bankzugang-pin")).to_have_value("")
    expect(tid(seite, "bankzugang-pin-status")).to_have_attribute("data-vorhanden", "nein")
    expect(tid(seite, "bankzugang-meldung")).to_be_hidden()
    expect(tid(seite, "bankzugang-tan")).to_be_hidden()
    for x in ("bankzugang-speichern", "bankzugang-pin-senden", "bankzugang-verfahren-abrufen",
              "bankzugang-konten-abrufen", "bankzugang-konten", "bankzugang-diagnose-aktiv",
              "bankzugang-diagnose-laden"):
        expect(tid(seite, x)).to_be_visible()
    assert _konten(seite).count() == 0, "ohne abgerufene Konten gibt es kein Ankreuzfeld"
    expect(tid(seite, "bankzugang-diagnose-aktiv")).not_to_be_checked()


def test_speichern_und_vollstaendig(starte_server, neue_seite):
    server = _echt(starte_server, bank_plugin="fints")
    api = server.api
    seite = neue_seite(server)
    abschnitt = bankzugang_oeffnen(seite, server)
    expect(abschnitt).to_have_attribute("data-vollstaendig", "nein")
    for feld in ("url", "blz", "benutzer", "kunden_id", "produkt_id"):
        expect(tid(seite, f"bankzugang-{feld}")).to_have_value("")
    expect(tid(seite, "bankzugang-tan-verfahren")).to_have_value("")
    werte = {"url": URL, "blz": "00000000", "benutzer": "SYNTH-OBERFLAECHE", "produkt_id": "SYNTH-PRODUKT-UI"}
    for feld, wert in werte.items():
        tid(seite, f"bankzugang-{feld}").fill(wert)
    tid(seite, "bankzugang-speichern").click()
    expect(abschnitt).to_have_attribute("data-vollstaendig", "ja")
    z = zugang(api)
    assert {f: z[f] for f in werte} == werte and z["gespeichert"] == sorted(werte) and z["vollstaendig"] is True
    assert z["kunden_id"] is None and z["tan_verfahren"] is None
    seite.reload()
    bankzugang_oeffnen(seite, server)
    for feld, wert in werte.items():
        expect(tid(seite, f"bankzugang-{feld}")).to_have_value(wert)
    _kein_speicher(seite, "SYNTH-OBERFLAECHE", "SYNTH-PRODUKT-UI")


def test_validierungsfehler_in_der_statuszeile(starte_server, neue_seite):
    server = _echt(starte_server, **VORBELEGUNG)
    seite = neue_seite(server)
    bankzugang_oeffnen(seite, server)
    vorher = zugang(server.api)
    tid(seite, "bankzugang-blz").fill("1234")
    tid(seite, "bankzugang-speichern").click()
    meldung = tid(seite, "bankzugang-meldung")
    expect(meldung).to_be_visible()
    expect(meldung).to_have_attribute("data-art", "fehler")
    expect(meldung).to_contain_text(re.compile("blz|Bankleitzahl", re.I))
    assert zugang(server.api) == vorher


@pytest.mark.parametrize("knopf,pfad", [("bankzugang-verfahren-abrufen", "/api/bank/zugang/tan-verfahren"),
                                        ("bankzugang-konten-abrufen", "/api/bank/zugang/konten/abrufen")])
def test_abrufen_speichert_zuerst_und_spricht_die_bank_sonst_nicht_an(starte_server, neue_seite, bank, knopf, pfad,
                                                                     netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        mitschnitt = Mitschnitt(seite)
        # scheitert das Speichern, wird die Bank nicht angesprochen
        tid(seite, "bankzugang-blz").fill("12")
        tid(seite, knopf).click()
        meldung = tid(seite, "bankzugang-meldung")
        expect(meldung).to_be_visible()
        expect(meldung).to_have_attribute("data-art", "fehler")
        assert mitschnitt.schreibend(re.escape(pfad)) == [], "Abruf trotz gescheitertem Speichern"
        assert a.anfragen == []
        # geänderte Felder werden zuerst gespeichert, dann wird abgerufen
        tid(seite, "bankzugang-blz").fill(daten["blz"])
        tid(seite, "bankzugang-produkt_id").fill("SYNTH-PRODUKT-ZUERST")
        tid(seite, knopf).click()
        warte_bis(lambda: a.anfragen, text="Anfrage an die Bank")
        warte_bis(lambda: len(mitschnitt.schreibend(re.escape(pfad))) == 1, text="Abruf über REST")
        assert zugang(server.api)["produkt_id"] == "SYNTH-PRODUKT-ZUERST"
        assert {x.produkt_id for x in a.anfragen if x.produkt_id} == {"SYNTH-PRODUKT-ZUERST"}
        reihenfolge = [p for _, p, _ in mitschnitt.schreibend()]
        assert reihenfolge.index("/api/bank/zugang") < reihenfolge.index(pfad), "erst speichern, dann abrufen"


# ------------------------------------------------------------------ PIN
def test_pin_geht_in_den_arbeitsspeicher_des_servers(starte_server, neue_seite):
    server = _echt(starte_server, **VORBELEGUNG)
    seite = neue_seite(server)
    bankzugang_oeffnen(seite, server)
    pin = "SYNTH-PIN-OBERFLAECHE-29"
    tid(seite, "bankzugang-pin").fill(pin)
    tid(seite, "bankzugang-pin-senden").click()
    expect(tid(seite, "bankzugang-pin-status")).to_have_attribute("data-vorhanden", "ja")
    expect(tid(seite, "bankzugang-pin")).to_have_value("")
    assert server.api.get("/api/sync/status", erwartet=200).daten["pin_vorhanden"] is True
    assert pin not in seite.content() and pin not in seite.url
    _kein_speicher(seite, pin)
    assert pin not in server.api.get("/api/bank/zugang", erwartet=200).text
    seite.reload()
    bankzugang_oeffnen(seite, server)
    expect(tid(seite, "bankzugang-pin-status")).to_have_attribute("data-vorhanden", "ja")
    expect(tid(seite, "bankzugang-pin")).to_have_value("")


# ------------------------------------------------------------------ TAN-Verfahren
def test_tan_verfahren_abrufen_und_speichern(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    haupt = daten["tan_verfahren"]["funktion"]
    with FintsAttrappe(daten) as a:
        a.verfahren_zusatz = [ZUSATZ_VERFAHREN]
        a.erlaubte_verfahren = [haupt, ZUSATZ_VERFAHREN["funktion"]]
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        auswahl = tid(seite, "bankzugang-tan-verfahren")
        assert auswahl.locator("option").evaluate_all("els => els.map(e => e.value)") == [""]
        tid(seite, "bankzugang-verfahren-abrufen").click()
        expect(auswahl.locator(f'option[value="{ZUSATZ_VERFAHREN["funktion"]}"]')).to_have_count(1)
        werte = auswahl.locator("option").evaluate_all("els => els.map(e => e.value)")
        assert werte[0] == "" and sorted(werte[1:]) == sorted([haupt, ZUSATZ_VERFAHREN["funktion"]])
        assert zugang(server.api)["tan_verfahren"] is None, "der Abruf speichert nichts"
        auswahl.select_option(ZUSATZ_VERFAHREN["funktion"])
        tid(seite, "bankzugang-speichern").click()
        warte_bis(lambda: zugang(server.api)["tan_verfahren"] == ZUSATZ_VERFAHREN["funktion"], text="gespeichert")
        seite.reload()
        bankzugang_oeffnen(seite, server)
        auswahl = tid(seite, "bankzugang-tan-verfahren")
        expect(auswahl).to_have_value(ZUSATZ_VERFAHREN["funktion"])
        werte = auswahl.locator("option").evaluate_all("els => els.map(e => e.value)")
        assert werte[0] == "" and ZUSATZ_VERFAHREN["funktion"] in werte
        auswahl.select_option("")
        tid(seite, "bankzugang-speichern").click()
        warte_bis(lambda: zugang(server.api)["tan_verfahren"] is None, text="automatisch gespeichert")
    assert a.tans_empfangen == 0 and not a.interne_fehler


# ------------------------------------------------------------------ Konten
def test_konten_abrufen_und_auswaehlen(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    soll = [k["iban"] for k in soll_konten(daten)]
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        tid(seite, "bankzugang-konten-abrufen").click()
        expect(_konten(seite)).to_have_count(len(soll))
        assert sorted(_ibans(seite)) == soll
        for i in range(len(soll)):
            expect(_konten(seite).nth(i)).to_be_checked()
        meldung = tid(seite, "bankzugang-meldung")
        expect(meldung).to_be_visible()
        expect(meldung).to_have_attribute("data-art", "hinweis")
        expect(meldung).to_contain_text(str(len(soll)))
        expect(tid(seite, "bankzugang-tan")).to_be_hidden()
        assert [k["iban"] for k in zugang(server.api)["konten"]] == soll
        # Auswahl ändern und speichern
        abgewaehlt = soll[1]
        tid(seite, "bankzugang-konten").locator(f'[data-testid="bankzugang-konto"][data-iban="{abgewaehlt}"]').uncheck()
        tid(seite, "bankzugang-konten-speichern").click()
        warte_bis(lambda: {k["iban"]: k["aktiv"] for k in zugang(server.api)["konten"]}
                  == {i: i != abgewaehlt for i in soll}, text="Auswahl gespeichert")
        seite.reload()
        bankzugang_oeffnen(seite, server)
        expect(_konten(seite)).to_have_count(len(soll))
        ist = _konten(seite).evaluate_all("els => els.map(e => [e.getAttribute('data-iban'), e.checked])")
        assert {i: c for i, c in ist} == {i: i != abgewaehlt for i in soll}
        _kein_speicher(seite, *soll)
    assert not a.interne_fehler


def test_null_konten_ist_eine_fehlermeldung(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe({**daten, "konten": []}, tan_pflicht="nie") as a:
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        tid(seite, "bankzugang-konten-abrufen").click()
        meldung = tid(seite, "bankzugang-meldung")
        expect(meldung).to_be_visible()
        expect(meldung).to_have_attribute("data-art", "fehler")
        assert _konten(seite).count() == 0
    assert a.anfragen and not a.interne_fehler


def test_fehler_der_bank_in_der_statuszeile(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        server = _mit_bank(starte_server, a, daten, pin=False)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        tid(seite, "bankzugang-konten-abrufen").click()          # ohne PIN: bank_pin_fehlt
        meldung = tid(seite, "bankzugang-meldung")
        expect(meldung).to_be_visible()
        expect(meldung).to_have_attribute("data-art", "fehler")
        assert a.anfragen == [] and _konten(seite).count() == 0
        expect(tid(seite, "bankzugang-tan")).to_be_hidden()


def test_konten_abrufen_mit_tan(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    soll = [k["iban"] for k in soll_konten(daten)]
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        bereich = tid(seite, "bankzugang-tan")
        expect(bereich).to_be_hidden()
        tid(seite, "bankzugang-konten-abrufen").click()
        expect(bereich).to_be_visible()
        expect(tid(seite, "bankzugang-tan-challenge")).to_contain_text(daten["challenge"])
        bild = tid(seite, "bankzugang-tan-bild")
        expect(bild).to_be_visible()
        assert bild.evaluate("e => e.tagName !== 'IMG' || (e.currentSrc || e.src || '').startsWith('data:image/png')"), \
            "die Grafik kommt als Daten-URL, nicht von außen"
        assert _konten(seite).count() == 0
        # falsche TAN: der Bereich bleibt offen, das Eingabefeld ist leer
        tid(seite, "bankzugang-tan-eingabe").fill("000000")
        tid(seite, "bankzugang-tan-senden").click()
        meldung = tid(seite, "bankzugang-meldung")
        expect(meldung).to_have_attribute("data-art", "fehler")
        expect(bereich).to_be_visible()
        expect(tid(seite, "bankzugang-tan-eingabe")).to_have_value("")
        # richtige TAN: der Bereich verschwindet, die Konten stehen da
        tid(seite, "bankzugang-tan-eingabe").fill(daten["tan"])
        tid(seite, "bankzugang-tan-senden").click()
        expect(_konten(seite)).to_have_count(len(soll))
        expect(bereich).to_be_hidden()
        expect(meldung).to_have_attribute("data-art", "hinweis")
        expect(meldung).to_contain_text(str(len(soll)))
        assert sorted(_ibans(seite)) == soll
        assert daten["tan"] not in seite.content() and daten["tan"] not in seite.url
        _kein_speicher(seite, daten["tan"], "000000", daten["pin"])
        for ref in a.referenzen:
            assert ref not in seite.content(), "die Auftragsreferenz der Bank erreicht die Oberfläche nie"
    assert a.anmeldungs_tans == 1 and not a.interne_fehler


def test_tan_bereich_verschwindet_nach_anderem_fehler(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        tid(seite, "bankzugang-konten-abrufen").click()
        bereich = tid(seite, "bankzugang-tan")
        expect(bereich).to_be_visible()
        a.lasse_tan_ablaufen()
        tid(seite, "bankzugang-tan-eingabe").fill(daten["tan"])
        tid(seite, "bankzugang-tan-senden").click()
        expect(bereich).to_be_hidden()
        meldung = tid(seite, "bankzugang-meldung")
        expect(meldung).to_be_visible()
        expect(meldung).to_have_attribute("data-art", "fehler")
        assert _konten(seite).count() == 0 and zugang(server.api)["konten"] == []


def test_tan_ohne_grafik_kein_bild(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        a.tan_anmeldung = "immer"
        original = a._hitan

        def ohne_bild(referenz):
            seg = original(referenz)
            seg.challenge_hhduc = None
            return seg
        a._hitan = ohne_bild
        server = _mit_bank(starte_server, a, daten)
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        tid(seite, "bankzugang-konten-abrufen").click()
        expect(tid(seite, "bankzugang-tan")).to_be_visible()
        expect(tid(seite, "bankzugang-tan-challenge")).to_contain_text(daten["challenge"])
        bild = tid(seite, "bankzugang-tan-bild")
        assert bild.count() == 0 or not bild.is_visible(), "bankzugang-tan-bild nur mit Grafik"


# ------------------------------------------------------------------ Diagnose
def test_diagnose_schalten_und_laden(starte_server, neue_seite, bank, netz_nur_loopback):
    daten, _ = bank
    with FintsAttrappe(daten, tan_pflicht="nie") as a:
        server = _mit_bank(starte_server, a, daten)
        api = server.api
        seite = neue_seite(server)
        bankzugang_oeffnen(seite, server)
        schalter = tid(seite, "bankzugang-diagnose-aktiv")
        expect(schalter).not_to_be_checked()
        schalter.check()
        warte_bis(lambda: diagnose(api)["aktiv"] is True, text="Diagnose eingeschaltet")
        tid(seite, "bankzugang-konten-abrufen").click()
        expect(_konten(seite)).to_have_count(len(soll_konten(daten)))
        tid(seite, "bankzugang-diagnose-laden").click()
        ausgabe = tid(seite, "bankzugang-diagnose-zeilen")
        zeilen = warte_bis(lambda: diagnose(api)["zeilen"], text="Zeilen im Protokoll")
        expect(ausgabe).to_have_attribute("data-zeilen", str(len(zeilen)))
        warte_bis(lambda: zeilen[0] in ausgabe.evaluate("e => (e.value !== undefined ? e.value : '') + e.textContent"),
                  text="Zeilen in der Ausgabe")
        expect(tid(seite, "bankzugang-diagnose-kopieren")).to_be_visible()
        seite.reload()
        bankzugang_oeffnen(seite, server)
        expect(tid(seite, "bankzugang-diagnose-aktiv")).to_be_checked()
        tid(seite, "bankzugang-diagnose-aktiv").uncheck()
        warte_bis(lambda: diagnose(api)["aktiv"] is False, text="Diagnose ausgeschaltet")
        _kein_speicher(seite, zeilen[0])
    assert not a.interne_fehler
