"""M5: Erkennung wiederkehrender Buchungen (wiederkehrend.md 2; T 10; E-098, E-099; Kette seit M16 nach E-192, E-194).

Wahrheit aus der Konstruktion des Generators (``fixtures/mock/m5_wiederkehrend.erwartung.json``) und
Gegenrechnung mit dem Orakel ``tests/hilfen/wiederkehrend_orakel.py``.
"""

from __future__ import annotations

import pytest

from tests.hilfen import wiederkehrend_orakel as wo
from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m5 import (Kreditbuch, WIEDER_MOCK, lade_wiederkehrend, letzte_aenderung_id, mock_api, nach_kennung,
                             sync, uebersicht)

DATEN, ERW = lade_wiederkehrend()


@pytest.fixture(scope="module")
def voll(tmp_path_factory):
    """Nur lesend: ganzer Zeitraum 2023–2024 abgerufen."""
    api = mock_api(tmp_path_factory.mktemp("wieder"), WIEDER_MOCK, "2025-01-15")
    sync(api, von=ERW["von"], bis=ERW["bis"])
    return api


def _vergleichbar(api, serien: list[dict]) -> list[dict]:
    uid = {b["id"]: u for u, b in nach_kennung(api).items()}
    giro = next(k["id"] for k in api.konten() if k["iban"] == ERW["iban"])
    aus = []
    for s in serien:
        assert s["konto_id"] == giro
        assert s["schluessel"] == f"{s['konto_id']}:{s['empfaenger']['id']}:{s['richtung']}"
        aus.append({**{k: s[k] for k in ("richtung", "rhythmus", "anzahl", "erste", "letzte", "betrag",
                                         "jahreskosten", "naechste_faelligkeit", "status")},
                    "empfaenger": s["empfaenger"]["name"], "umsatz_ids": [uid[b] for b in s["buchung_ids"]]})
    return sorted(aus, key=lambda s: s["empfaenger"])


@pytest.mark.kern
@pytest.mark.parametrize("stichtag", sorted(ERW["serien"]))
def test_serien_gleich_wahrheit(voll, stichtag):
    u = uebersicht(voll, stichtag)
    assert u["stichtag"] == stichtag
    assert _vergleichbar(voll, u["serien"]) == ERW["serien"][stichtag]
    soll_summe = sum(s["jahreskosten"] for s in ERW["serien"][stichtag]
                     if s["richtung"] == "ausgabe" and s["status"] != "beendet")
    assert u["summe_jahreskosten"] == soll_summe


@pytest.mark.kern
@pytest.mark.parametrize("stichtag", ["2023-06-30", "2024-03-12", "2024-07-09", "2024-11-30", "2025-01-15"])
def test_serien_gleich_orakel(voll, stichtag):
    u = uebersicht(voll, stichtag)
    soll = wo.uebersicht(voll.alle_buchungen(), voll.konten(), [], stichtag)
    assert u == soll


@pytest.mark.kern
def test_rhythmen_jahreskosten_und_verschiebungen(voll):
    """T 10: monatlich, vierteljährlich, jährlich trotz Wochenend-/Feiertagsverschiebung; Jahreskosten."""
    s = {x["empfaenger"]["name"]: x for x in uebersicht(voll, "2024-12-31")["serien"]}
    assert s["Wohnbau Fiktiva eG"]["rhythmus"] == "monatlich" and s["Wohnbau Fiktiva eG"]["anzahl"] == 24
    assert s["Wohnbau Fiktiva eG"]["jahreskosten"] == 98_000 * 12
    assert s["Fiktiva Haftpflicht AG"]["rhythmus"] == "vierteljaehrlich"
    assert s["Fiktiva Haftpflicht AG"]["jahreskosten"] == 4_790 * 4
    assert s["Fiktive Kfz-Steuerkasse"]["rhythmus"] == "jaehrlich" and s["Fiktive Kfz-Steuerkasse"]["jahreskosten"] == 18_400
    assert s["Arbeitgeber Muster GmbH (fiktiv)"]["jahreskosten"] == -285_000 * 12
    assert s["Studio Muskelkater (fiktiv)"]["status"] == "beendet"
    for n in ERW["nicht_wiederkehrend"]:
        assert n not in s


@pytest.mark.kern
def test_vorgabe_stichtag_heute_und_keine_aenderung(voll):
    a0 = letzte_aenderung_id(voll)
    assert uebersicht(voll) == uebersicht(voll, "2025-01-15")
    assert letzte_aenderung_id(voll) == a0, "die Übersicht erzeugt keine Änderung"
    assert fehlercode(voll.get("/api/wiederkehrend", params={"stichtag": "2024-02-30"}, erwartet=422)) == "validierung"


# ------------------------------------------------------------------ kleine, handgebaute Fälle
def _buchen(api, konto, kat, emp, tage, betraege):
    return [api.buchung(t, [(konto, b), (kat, -b)], empfaenger_id=emp)["id"] for t, b in zip(tage, betraege)]


@pytest.mark.kern
def test_kette_und_mindestanzahl(api):
    g, kat = api.konto("Giro")["id"], api.konto("Abo", "aufwand")["id"]
    e = api.empfaenger("Abo AG")["id"]
    _buchen(api, g, kat, e, ["2024-01-31", "2024-02-29"], [-500, -500])
    assert uebersicht(api, "2024-03-01")["serien"] == [], "zwei Monatszahlungen sind noch keine Serie"
    ids = _buchen(api, g, kat, e, ["2024-04-03"], [-700])
    (s,) = uebersicht(api, "2024-04-03")["serien"]  # monat_plus(29.02.) = 29.03., +5 Tage = 03.04.: Kette hält
    assert (s["anzahl"], s["betrag"], s["naechste_faelligkeit"], s["buchung_ids"][-1]) == (3, -700, "2024-05-03",
                                                                                         ids[0])
    assert s["erste"] == "2024-01-31" and s["jahreskosten"] == 8_400
    _buchen(api, g, kat, e, ["2024-05-09"], [-700])  # 6 Tage nach 03.05.: Kette reißt
    assert uebersicht(api, "2024-05-09")["serien"] == []
    assert uebersicht(api, "2024-05-08")["serien"][0]["status"] == "aktiv", "Stichtag filtert Buchungen danach"


@pytest.mark.kern
def test_status_grenzen(api):
    g, kat = api.konto("Giro")["id"], api.konto("Abo", "aufwand")["id"]
    e = api.empfaenger("Abo AG")["id"]
    _buchen(api, g, kat, e, ["2024-01-10", "2024-02-10", "2024-03-10"], [-1, -1, -1])
    st = {t: uebersicht(api, t)["serien"][0]["status"] for t in
          ("2024-04-15", "2024-04-16", "2024-05-15", "2024-05-16")}
    assert st == {"2024-04-15": "aktiv", "2024-04-16": "ausbleibend", "2024-05-15": "ausbleibend",
                  "2024-05-16": "beendet"}


@pytest.mark.kern
def test_gruppen_je_konto_empfaenger_richtung(api):
    g, k2, kat = api.konto("Giro")["id"], api.konto("Karte", "kreditkonto")["id"], api.konto("Abo", "aufwand")["id"]
    e = api.empfaenger("Abo AG")["id"]
    tage = ["2024-01-15", "2024-02-15", "2024-03-15"]
    _buchen(api, g, kat, e, tage, [-100] * 3)
    _buchen(api, k2, kat, e, tage, [-100] * 3)
    _buchen(api, g, kat, e, tage, [50] * 3)
    ohne = [api.buchung(t, [(g, -9), (kat, 9)])["id"] for t in tage]
    serien = uebersicht(api, "2024-03-31")["serien"]
    assert [(s["konto_id"], s["richtung"]) for s in serien] == [(g, "ausgabe"), (g, "einnahme"), (k2, "ausgabe")]
    assert not {b for s in serien for b in s["buchung_ids"]} & set(ohne), "ohne Empfänger keine Serie"


@pytest.mark.kern
def test_doppelte_zahlung_am_termin_ist_zusaetzlich(api):
    """Geändert mit M16 (E-194): Eine zusätzliche Zahlung am Termin beendet die Kette nicht mehr; sie zählt
    nicht zur Serie. Bisher: ``test_doppelte_zahlung_unterbricht_die_kette`` (keine Serie)."""
    g, kat = api.konto("Giro")["id"], api.konto("Abo", "aufwand")["id"]
    e = api.empfaenger("Abo AG")["id"]
    ids = _buchen(api, g, kat, e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-03-15"], [-100] * 4)
    (s,) = uebersicht(api, "2024-03-31")["serien"]
    assert (s["anzahl"], s["erste"], s["letzte"], s["betrag"]) == (3, "2024-01-15", "2024-03-15", -100)
    assert s["buchung_ids"] == [ids[0], ids[1], ids[3]], "Anker ist die jüngere der beiden Zahlungen am 15.03."
    assert s["jahreskosten"] == 1_200


@pytest.mark.kern
def test_umbuchung_zaehlt_je_konto_darlehenskonto_nie(api):
    kb = Kreditbuch(api)
    spar = api.konto("Spar", "sparkonto")["id"]
    e = api.empfaenger("Erika Mustermann (fiktiv)")["id"]
    for t in ("2024-01-01", "2024-02-01", "2024-03-01"):
        api.buchung(t, [(kb.giro, -2_500), (spar, 2_500)], empfaenger_id=e)
        api.buchung(t, [(kb.giro, -50_000), (kb.zinsen, 3_000), (kb.darlehen, 47_000)], empfaenger_id=kb.bank)
    k = kb.anlegen(saldo_angleichen=False).daten
    serien = uebersicht(api, "2024-03-31")["serien"]
    assert {(s["konto_id"], s["empfaenger"]["id"], s["richtung"]) for s in serien} == {
        (kb.giro, e, "ausgabe"), (spar, e, "einnahme"), (kb.giro, kb.bank, "ausgabe")}
    assert all(s["konto_id"] != k["konto_id"] for s in serien)
    soll = wo.uebersicht(api.alle_buchungen(), api.konten(), api.get("/api/kredite", erwartet=200).daten,
                         "2024-03-31")
    assert uebersicht(api, "2024-03-31") == soll


def test_leere_instanz(tmp_path):
    api = neue_api(tmp_path)
    u = api.get("/api/wiederkehrend", params={"stichtag": "2024-01-01"}, erwartet=200).daten
    assert u == {"stichtag": "2024-01-01", "serien": [], "summe_jahreskosten": 0}
