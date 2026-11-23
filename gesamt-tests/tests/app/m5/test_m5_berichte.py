"""M5: Berichte – Kontostandsverlauf und Einnahmen/Ausgaben (berichte.md 1–3; T 15, T 11; E-059, E-106).

Erwartungen: Modell des Generators für ``kmy/standard.kmy`` (``fixtures/m5/berichte.erwartung.json``) und
unabhängig aus den Splits der Buchungsliste berechnete Salden.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import UNKATEGORISIERT, erfassen, konto_id, letzte_aenderung_id
from tests.hilfen.m5 import (M5, einnahmen_ausgaben, kontostand, lade, mock_api, saldo_aus_splits, stichtage,
                             unterkonten, WIEDER_MOCK)

pytestmark = pytest.mark.kern

WAHR = lade(M5 / "berichte.erwartung.json")


@pytest.fixture(scope="module")
def ids(standard_api):
    return {k["extern_id"]: k["id"] for k in standard_api.konten() if k["extern_id"]}


@pytest.mark.parametrize("i", range(len(WAHR["kontostand"])))
def test_kontostand_gleich_wahrheit(standard_api, ids, i):
    w = WAHR["kontostand"][i]
    konten = [ids[k] for k in w["konten"]]
    r = kontostand(standard_api, konto_id=konten, von=w["von"], bis=w["bis"], intervall=w["intervall"]).daten
    assert (r["von"], r["bis"], r["intervall"], r["unterkonten"]) == (w["von"], w["bis"], w["intervall"], False)
    assert r["stichtage"] == w["stichtage"] == stichtage(w["von"], w["bis"], w["intervall"])
    assert [x["konto_id"] for x in r["reihen"]] == sorted(konten)
    for x in r["reihen"]:
        ext = next(e for e, k in ids.items() if k == x["konto_id"])
        assert x["werte"] == w["werte"][ext], ext


@pytest.mark.parametrize("intervall", ["tag", "woche", "monat", "jahr"])
def test_kontostand_gleich_summe_der_splits(standard_api, intervall):
    """T 15: an jedem Stichtag die Summe aller Splits bis zu diesem Tag – auch für Kategorien mit Unterkonten."""
    von, bis = {"tag": ("2023-12-20", "2024-01-10"), "woche": ("2023-10-01", "2024-03-03"),
                "monat": ("2021-12-15", "2025-02-01"), "jahr": ("2020-02-29", "2025-12-31")}[intervall]
    buchungen = standard_api.alle_buchungen()
    konten = standard_api.konten()
    alle = [k["id"] for k in konten]
    for unter in (False, True):
        r = kontostand(standard_api, konto_id=alle, von=von, bis=bis, intervall=intervall, unterkonten=unter).daten
        assert r["stichtage"] == stichtage(von, bis, intervall)
        for x in r["reihen"]:
            menge = unterkonten(konten, x["konto_id"]) if unter else {x["konto_id"]}
            assert x["werte"] == [saldo_aus_splits(buchungen, menge, s) for s in r["stichtage"]], (x["name"], unter)


def test_kontostand_gleich_kontenuebersicht(standard_api):
    r = kontostand(standard_api, von="2023-01-01", bis="2023-12-31", intervall="monat").daten
    bestand = [k["id"] for k in standard_api.konten() if k["art"] in ("girokonto", "sparkonto", "kreditkonto")]
    assert [x["konto_id"] for x in r["reihen"]] == bestand, "ohne Angabe alle Bestandskonten nach id"
    for i in (0, 5, len(r["stichtage"]) - 1):
        s = r["stichtage"][i]
        sal = standard_api.salden(s)
        for x in r["reihen"]:
            assert x["werte"][i] == sal[x["konto_id"]]["saldo"], (s, x["name"])


@pytest.mark.parametrize("i", range(len(WAHR["einnahmen_ausgaben"])))
def test_einnahmen_ausgaben_gleich_wahrheit(standard_api, ids, i):
    w = WAHR["einnahmen_ausgaben"][i]
    params = {"von": w["von"], "bis": w["bis"], "intervall": w["intervall"]}
    if w["konten"]:
        params["konto_id"] = [ids[k] for k in w["konten"]]
    r = einnahmen_ausgaben(standard_api, **params).daten
    assert r["perioden"] == w["perioden"]
    assert r["gesamt"] == w["gesamt"]
    rev = {v: k for k, v in ids.items()}
    assert {rev[k["kategorie_id"]]: k["summe"] for k in r["kategorien"]} == w["kategorien"]
    assert [k["kategorie_id"] for k in r["kategorien"]] == sorted(k["kategorie_id"] for k in r["kategorien"])
    namen = {k["id"]: (k["name"], k["art"]) for k in standard_api.konten()}
    assert all((k["name"], k["art"]) == namen[k["kategorie_id"]] for k in r["kategorien"])


def test_umbuchungen_zaehlen_nicht(api):
    """T 11, E-059: Umbuchungen erscheinen weder als Einnahme noch als Ausgabe; Kredittilgung ist keine Ausgabe."""
    g, s = api.konto("Giro", "girokonto")["id"], api.konto("Spar", "sparkonto")["id"]
    lm, geh = api.konto("Lebensmittel", "aufwand")["id"], api.konto("Gehalt", "ertrag")["id"]
    zins, darl = api.konto("Zinsen", "aufwand")["id"], api.konto("Darlehen", "kreditkonto")["id"]
    api.buchung("2024-03-01", [(g, 300_000), (geh, -300_000)])
    api.buchung("2024-03-02", [(g, -1234), (lm, 1234)])
    api.buchung("2024-03-03", [(g, 500), (lm, -500)])   # Erstattung mindert die Ausgaben
    erfassen(api, art="umbuchung", datum="2024-03-04", konto_id=g, gegenkonto_id=s, betrag=50_000)
    api.buchung("2024-03-05", [(g, -50_000), (zins, 3_000), (darl, 47_000)])
    erfassen(api, art="ausgabe", datum="2024-03-06", konto_id=g, betrag=999)
    erfassen(api, art="einnahme", datum="2024-03-07", konto_id=g, betrag=111)
    r = einnahmen_ausgaben(api, von="2024-03-01", bis="2024-03-31", intervall="monat").daten
    soll = {"einnahmen": 300_000, "ausgaben": 1234 - 500 + 3_000, "saldo": 300_000 - 3_734,
            "nicht_kategorisiert": 999 - 111}
    assert r["gesamt"] == soll
    assert r["perioden"] == [{"von": "2024-03-01", "bis": "2024-03-31", **soll}]
    assert konto_id(api, UNKATEGORISIERT) is not None
    assert {k["kategorie_id"]: k["summe"] for k in r["kategorien"]} == {lm: 734, geh: -300_000, zins: 3_000}
    nur_spar = einnahmen_ausgaben(api, von="2024-03-01", bis="2024-03-31", konto_id=[s]).daten
    assert nur_spar["gesamt"] == {"einnahmen": 0, "ausgaben": 0, "saldo": 0, "nicht_kategorisiert": 0}
    assert nur_spar["kategorien"] == []


def test_leere_konten_und_zeitraeume(api):
    g, leer = api.konto("Giro")["id"], api.konto("Leer", "sparkonto")["id"]
    kat = api.konto("Kat", "aufwand")["id"]
    api.buchung("2024-01-10", [(g, -100), (kat, 100)])
    api.buchung("2024-06-10", [(g, -50), (kat, 50)])
    r = kontostand(api, von="2024-01-01", bis="2024-07-31").daten
    assert r["stichtage"] == ["2024-01-01", "2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30", "2024-05-31",
                              "2024-06-30", "2024-07-31"]
    werte = {x["konto_id"]: x["werte"] for x in r["reihen"]}
    assert werte == {g: [0, -100, -100, -100, -100, -100, -150, -150], leer: [0] * 8}
    ea = einnahmen_ausgaben(api, von="2024-02-15", bis="2024-04-10", intervall="monat").daten
    assert [(p["von"], p["bis"], p["ausgaben"]) for p in ea["perioden"]] == [
        ("2024-02-15", "2024-02-29", 0), ("2024-03-01", "2024-03-31", 0), ("2024-04-01", "2024-04-10", 0)]
    einer = kontostand(api, konto_id=[leer], von="2024-05-05", bis="2024-05-05", intervall="tag").daten
    assert einer["stichtage"] == ["2024-05-05"] and einer["reihen"][0]["werte"] == [0]


def test_vorgaben_fuer_zeitraum(tmp_path):
    api = mock_api(tmp_path, WIEDER_MOCK, "2024-05-20")
    r = kontostand(api).daten
    assert (r["von"], r["bis"], r["intervall"], r["stichtage"], r["reihen"]) == (
        "2024-05-20", "2024-05-20", "monat", ["2024-05-20"], [])
    g, kat = api.konto("Giro")["id"], api.konto("Kat", "aufwand")["id"]
    api.buchung("2024-03-15", [(g, -100), (kat, 100)])
    r = kontostand(api).daten
    assert (r["von"], r["bis"]) == ("2024-03-15", "2024-05-20")
    assert r["stichtage"] == ["2024-03-15", "2024-03-31", "2024-04-30", "2024-05-20"]
    e = einnahmen_ausgaben(api, intervall="jahr").daten
    assert (e["von"], e["bis"], e["gesamt"]["ausgaben"]) == ("2024-03-15", "2024-05-20", 100)


def test_fehler_und_keine_aenderung(api):
    g, kat = api.konto("Giro")["id"], api.konto("Kat", "aufwand")["id"]
    a0 = letzte_aenderung_id(api)
    assert fehlercode(kontostand(api, 422, von="2024-02-01", bis="2024-01-31")) == "validierung"
    assert fehlercode(kontostand(api, 422, intervall="quartal")) == "validierung"
    r = kontostand(api, 422, konto_id=[g, 99, 98])
    assert fehlercode(r) == "referenz_unbekannt" and r.json()["fehler"]["details"]["konto_ids"] == [98, 99]
    assert fehlercode(kontostand(api, 422, von="2000-01-01", bis="2020-01-01", intervall="tag")) == "bericht_zu_gross"
    assert len(kontostand(api, von="2010-01-01", bis="2023-09-09", intervall="tag").daten["stichtage"]) == 5000
    assert fehlercode(kontostand(api, 422, von="2010-01-01", bis="2023-09-10", intervall="tag")) == "bericht_zu_gross"
    assert fehlercode(einnahmen_ausgaben(api, 422, konto_id=[kat])) == "konto_ungueltig"
    assert fehlercode(einnahmen_ausgaben(api, 422, konto_id=[77])) == "referenz_unbekannt"
    assert fehlercode(einnahmen_ausgaben(api, 422, von="2000-01-01", bis="2020-01-01", intervall="tag")) == \
        "bericht_zu_gross"
    assert fehlercode(einnahmen_ausgaben(api, 422, von="2024-02-01", bis="2024-01-31")) == "validierung"
    assert letzte_aenderung_id(api) == a0


def test_stichtage_hilfsfunktion_selbst():
    """Gegenprobe der unabhängigen Stichtagsregel (Wochen enden sonntags, ISO 8601)."""
    assert stichtage("2024-02-26", "2024-03-12", "woche") == ["2024-02-26", "2024-03-03", "2024-03-10", "2024-03-12"]
    assert stichtage("2024-12-31", "2025-01-01", "jahr") == ["2024-12-31", "2025-01-01"]
    assert dt.date(2024, 3, 3).isoweekday() == 7
