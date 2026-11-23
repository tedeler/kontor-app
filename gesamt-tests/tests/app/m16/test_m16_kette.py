"""M16: Neue Kette der Erkennung wiederkehrender Buchungen (wiederkehrend.md 2.2; Definition M16 Abschnitt 1;
E-193, E-194).

Jeder Fall prüft handgerechnete Erwartungen (Glieder, zusätzliche Zahlungen, Kettenprotokoll) und zusätzlich die
ganze Übersicht und alle Begründungen gegen die unabhängige Referenz ``wiederkehrend_orakel.kette``.
"""

from __future__ import annotations

import datetime as dt
import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.hilfen import wiederkehrend_orakel as wo
from tests.hilfen.api import neue_api
from tests.hilfen.kredit_orakel import monat_plus
from tests.hilfen.m16 import (Abo, begruendung, eintrag, kredite, pruefe_begruendung, rhythmus, schritte,
                              uebersicht)

STICHTAG = "2024-12-31"


def _serien(api, emp: int, stichtag: str = STICHTAG) -> list[dict]:
    """Serien des Empfängers; die ganze Übersicht muss gleich der Referenz sein."""
    u = uebersicht(api, stichtag)
    assert u == wo.uebersicht(api.alle_buchungen(), api.konten(), kredite(api), stichtag)
    return [s for s in u["serien"] if s["empfaenger"]["id"] == emp]


def _alle_begruendungen(api, ids: list[int], stichtag: str = STICHTAG) -> dict[int, dict]:
    return {b: pruefe_begruendung(api, b, stichtag) for b in ids}


def _rollen(antwort: dict) -> dict[int, tuple]:
    return {x["buchung_id"]: (x["rolle"], x["glied"]) for x in eintrag(antwort)["buchungen"]}


def _tage(d1: str, d2: str) -> int:
    return (dt.date.fromisoformat(d1) - dt.date.fromisoformat(d2)).days


# ------------------------------------------------------------------ Beispiele der Definition (1.3)
@pytest.mark.kern
def test_beispiel_zusaetzlich_vor_dem_anker(api):
    """15.01., 15.02., 13.03., 15.03. → Kette 15.01., 15.02., 15.03.; 13.03. ist zusätzlich."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-13", "2024-03-15"])
    (s,) = _serien(api, e, "2024-03-31")
    assert (s["rhythmus"], s["anzahl"], s["buchung_ids"]) == ("monatlich", 3, [i[0], i[1], i[3]])
    assert (s["erste"], s["letzte"], s["naechste_faelligkeit"]) == ("2024-01-15", "2024-03-15", "2024-04-15")
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert [b[x]["urteil"] for x in i] == ["wiederkehrend", "wiederkehrend", "zusaetzlich", "wiederkehrend"]
    assert _rollen(b[i[2]]) == {i[3]: ("glied", 3), i[2]: ("zusaetzlich", None), i[1]: ("glied", 2),
                                i[0]: ("glied", 1)}
    e2 = eintrag(b[i[2]])
    assert [x["buchung_id"] for x in e2["buchungen"]] == [i[3], i[2], i[1], i[0]], "jüngste zuerst"
    assert [r["rhythmus"] for r in e2["rhythmen"]] == ["monatlich"], "bis zum ersten erfüllten Rhythmus"
    assert schritte(e2) == [("anker", None, i[3], None), ("verbunden", None, i[3], i[1]),
                            ("verbunden", None, i[1], i[0]), ("bruch", "kein_vorgaenger", i[0], None)]
    anker = rhythmus(e2, "monatlich")["schritte"][0]
    assert [x["buchung_id"] for x in anker["uebersprungen"]] == [i[2]]
    assert anker["kandidaten"] == [
        {"buchung_id": i[2], "datum": "2024-03-13", "betrag": -999, "laenge": 3, "gleicher_betrag": True},
        {"buchung_id": i[3], "datum": "2024-03-15", "betrag": -999, "laenge": 3, "gleicher_betrag": True}]
    v = rhythmus(e2, "monatlich")["schritte"][1]
    assert (v["erwartet"], v["abweichung_tage"], [x["buchung_id"] for x in v["uebersprungen"]]) == (
        "2024-03-15", 0, [i[2]])
    assert e2["serie"] == s and e2["juengste"] == {"buchung_id": i[3], "datum": "2024-03-15", "betrag": -999}
    assert e2["gruppe_anzahl"] == 4


@pytest.mark.kern
def test_beispiel_fremde_zahlung(api):
    """15.01., 15.02., 15.03., dazu 01.03. → keine Serie (ab 15.03. ist 01.03. fremd)."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-01", "2024-03-15"])
    assert _serien(api, e, "2024-03-31") == []
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert {x["urteil"] for x in b.values()} == {"nicht_wiederkehrend"}
    e3 = eintrag(b[i[3]])
    assert e3["urteil"] == "keine_serie" and e3["serie"] is None and e3["glied"] is None
    assert set(_rollen(b[i[3]]).values()) == {("keine_serie", None)}
    assert [(r["rhythmus"], r["monate"], r["mindestanzahl"], r["laenge"], r["erfuellt"]) for r in e3["rhythmen"]] == [
        ("monatlich", 1, 3, 1, False), ("vierteljaehrlich", 3, 3, 1, False), ("jaehrlich", 12, 2, 1, False)]
    (bruch,) = rhythmus(e3, "monatlich")["schritte"]
    assert (bruch["ergebnis"], bruch["grund"], bruch["von"]["buchung_id"]) == ("bruch", "fremde_zahlung", i[3])
    assert (bruch["vorgaenger"]["buchung_id"], bruch["fremd"]["buchung_id"]) == (i[1], i[2])
    assert (bruch["erwartet"], bruch["abweichung_tage"]) == ("2024-03-15", 0)
    for name, m in (("vierteljaehrlich", 3), ("jaehrlich", 12)):
        (bruch,) = rhythmus(e3, name)["schritte"]
        erw = monat_plus(dt.date(2024, 3, 1), m).isoformat()
        assert (bruch["grund"], bruch["vorgaenger"]["buchung_id"], bruch["erwartet"]) == ("abstand", i[2], erw)
        assert bruch["abweichung_tage"] == _tage("2024-03-15", erw) and bruch["fremd"] is None


@pytest.mark.kern
def test_beispiel_anker_nach_betrag(api):
    """04.08., 04.09., 05.10., 04.11. (−320,32 €) und 04.11. (−50,00 €, später angelegt): vier Glieder zu −320,32 €."""
    a = Abo(api)
    e = a.empfaenger("Wohnbau Fiktiva eG")
    i = a.buchen(e, ["2024-08-04", "2024-09-04", "2024-10-05", "2024-11-04", "2024-11-04"],
                 [-32_032] * 4 + [-5_000])
    (s,) = _serien(api, e, "2024-11-30")
    assert (s["anzahl"], s["betrag"], s["jahreskosten"], s["buchung_ids"]) == (4, -32_032, 384_384, i[:4])
    b = _alle_begruendungen(api, i, "2024-11-30")
    assert b[i[4]]["urteil"] == "zusaetzlich" and eintrag(b[i[4]])["urteil"] == "zusaetzlich"
    anker = rhythmus(eintrag(b[i[4]]), "monatlich")["schritte"][0]
    assert anker["ergebnis"] == "anker" and anker["von"]["buchung_id"] == i[3]
    assert [(k["buchung_id"], k["laenge"], k["gleicher_betrag"]) for k in anker["kandidaten"]] == [
        (i[3], 4, True), (i[4], 4, False)]


@pytest.mark.kern
def test_beispiel_zusaetzlich_am_ersten_termin(api):
    """13.01. sowie 15.01., 15.02., 15.03. → Kette 15.01.–15.03.; 13.01. ist zusätzlich."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-13", "2024-01-15", "2024-02-15", "2024-03-15"])
    (s,) = _serien(api, e, "2024-03-31")
    assert s["buchung_ids"] == i[1:] and s["erste"] == "2024-01-15"
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert b[i[0]]["urteil"] == "zusaetzlich"
    letzter = rhythmus(eintrag(b[i[0]]), "monatlich")["schritte"][-1]
    assert (letzter["ergebnis"], letzter["grund"], letzter["von"]["buchung_id"]) == ("bruch", "kein_vorgaenger", i[1])
    assert [x["buchung_id"] for x in letzter["uebersprungen"]] == [i[0]]
    assert letzter["vorgaenger"] is None and letzter["erwartet"] is None and letzter["abweichung_tage"] is None


@pytest.mark.kern
def test_doppelte_zahlung_am_termin(api):
    """Definition 4: 15.01., 15.02., 15.03. und 15.03. (doppelt) sind eine Serie mit drei Gliedern (E-194)."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-03-15"])
    (s,) = _serien(api, e, "2024-03-31")
    assert (s["anzahl"], s["buchung_ids"]) == (3, [i[0], i[1], i[3]])
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert b[i[2]]["urteil"] == "zusaetzlich"


# ------------------------------------------------------------------ weitere Fälle
@pytest.mark.kern
def test_anker_nach_laenge(api):
    """Der jüngere Kandidat 17.03. hat keinen Vorgänger (Abweichung 7 Tage); der ältere 12.03. die längere Kette."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-10", "2024-02-10", "2024-03-12", "2024-03-17"])
    (s,) = _serien(api, e, "2024-03-31")
    assert (s["buchung_ids"], s["letzte"], s["naechste_faelligkeit"]) == (i[:3], "2024-03-12", "2024-04-12")
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert b[i[3]]["urteil"] == "zusaetzlich"
    anker = rhythmus(eintrag(b[i[3]]), "monatlich")["schritte"][0]
    assert [(k["buchung_id"], k["laenge"], k["gleicher_betrag"]) for k in anker["kandidaten"]] == [
        (i[2], 3, True), (i[3], 1, False)]
    assert anker["von"]["buchung_id"] == i[2]


@pytest.mark.kern
def test_anker_bei_gleichstand_der_juengere(api):
    """Gleich lange Ketten, beide mit gleichem Betrag: der jüngere (nach buchung_id bei gleichem Datum)."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-03-15", "2024-03-15"])
    (s,) = _serien(api, e, "2024-03-31")
    assert s["buchung_ids"] == [i[0], i[1], i[4]]
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert [b[x]["urteil"] for x in i[2:4]] == ["zusaetzlich", "zusaetzlich"]


@pytest.mark.kern
def test_vorgaenger_nach_betrag_vor_abweichung(api):
    """Unter den Vorgänger-Kandidaten zuerst der gleiche Betrag (12.02., 3 Tage), nicht die kleinste Abweichung
    (15.02., 0 Tage, anderer Betrag); 15.02. liegt dann höchstens T Tage nach p und ist zusätzlich."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-12", "2024-02-12", "2024-02-15", "2024-03-15"], [-999, -999, -500, -999])
    (s,) = _serien(api, e, "2024-03-31")
    assert s["buchung_ids"] == [i[0], i[1], i[3]]
    b = _alle_begruendungen(api, i, "2024-03-31")
    v = rhythmus(eintrag(b[i[3]]), "monatlich")["schritte"][0]
    assert (v["ergebnis"], v["vorgaenger"]["buchung_id"], v["erwartet"], v["abweichung_tage"]) == (
        "verbunden", i[1], "2024-03-12", 3)
    assert [x["buchung_id"] for x in v["uebersprungen"]] == [i[2]]


@pytest.mark.kern
def test_vorgaenger_bei_gleichem_betrag_kleinste_abweichung_dann_juenger(api):
    a = Abo(api)
    e = a.empfaenger()
    # 15.03.: Kandidaten 12.02. (3 Tage) und 14.02. (1 Tag) → 14.02.; 12.02. liegt 2 Tage vor p und ist zusätzlich
    i = a.buchen(e, ["2024-01-14", "2024-02-12", "2024-02-14", "2024-03-15"])
    (s,) = _serien(api, e, "2024-03-31")
    assert s["buchung_ids"] == [i[0], i[2], i[3]]
    _alle_begruendungen(api, i, "2024-03-31")
    # gleiche Abweichung (10.03. und 20.03. für den 15.04.): der jüngere
    f = a.empfaenger()
    j = a.buchen(f, ["2024-01-20", "2024-02-20", "2024-03-10", "2024-03-20", "2024-04-15"])
    (s,) = _serien(api, f, "2024-04-30")
    assert s["buchung_ids"] == [j[0], j[1], j[3], j[4]]
    _alle_begruendungen(api, j, "2024-04-30")


@pytest.mark.kern
def test_zusaetzliche_zahlung_zwischen_gliedern(api):
    """17.02. liegt zwischen 15.02. und 15.03. höchstens T Tage nach dem Vorgänger: zusätzlich, Kette läuft weiter."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-02-17", "2024-03-15", "2024-04-15"])
    (s,) = _serien(api, e, "2024-04-30")
    assert (s["anzahl"], s["buchung_ids"]) == (4, [i[0], i[1], i[3], i[4]])
    b = _alle_begruendungen(api, i, "2024-04-30")
    assert b[i[2]]["urteil"] == "zusaetzlich"
    assert schritte(eintrag(b[i[2]])) == [("verbunden", None, i[4], i[3]), ("verbunden", None, i[3], i[1]),
                                          ("verbunden", None, i[1], i[0]), ("bruch", "kein_vorgaenger", i[0], None)]
    assert [x["buchung_id"] for x in rhythmus(eintrag(b[i[2]]), "monatlich")["schritte"][1]["uebersprungen"]] == [i[2]]


@pytest.mark.kern
def test_vorgaenger_kandidat_des_vorigen_schritts_ist_zusaetzlich(api):
    """15.03.: Kandidaten 10.02. und 20.02. (je 5 Tage) → 20.02.; zwischen 20.01. und 20.02. liegt 10.02., mehr als T
    Tage von beiden entfernt, aber Vorgänger-Kandidat des vorigen Schritts: zusätzlich (1.2)."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-20", "2024-02-10", "2024-02-20", "2024-03-15"])
    (s,) = _serien(api, e, "2024-03-31")
    assert s["buchung_ids"] == [i[0], i[2], i[3]]
    b = _alle_begruendungen(api, i, "2024-03-31")
    assert b[i[1]]["urteil"] == "zusaetzlich"
    v = rhythmus(eintrag(b[i[1]]), "monatlich")["schritte"]
    assert (v[0]["vorgaenger"]["buchung_id"], v[0]["abweichung_tage"]) == (i[2], -5)
    assert [x["buchung_id"] for x in v[1]["uebersprungen"]] == [i[1]]


@pytest.mark.kern
def test_ausgelassene_zahlung_beendet_die_kette(api):
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-04-15", "2024-05-15", "2024-06-15"])
    (s,) = _serien(api, e, "2024-06-30")
    assert (s["anzahl"], s["buchung_ids"], s["erste"]) == (3, i[2:], "2024-04-15")
    b = _alle_begruendungen(api, i, "2024-06-30")
    assert [b[x]["urteil"] for x in i] == ["nicht_wiederkehrend"] * 2 + ["wiederkehrend"] * 3
    assert _rollen(b[i[0]])[i[0]] == ("vor_beginn", None)
    letzter = rhythmus(eintrag(b[i[0]]), "monatlich")["schritte"][-1]
    assert (letzter["grund"], letzter["von"]["buchung_id"], letzter["vorgaenger"]["buchung_id"]) == (
        "abstand", i[2], i[1])
    assert (letzter["erwartet"], letzter["abweichung_tage"], letzter["uebersprungen"]) == ("2024-03-15", 31, [])


@pytest.mark.kern
def test_woechentliche_zahlungen_keine_monatsserie(api):
    a = Abo(api)
    e = a.empfaenger("Wochenmarkt Fiktiv")
    tage = [(dt.date(2024, 1, 5) + dt.timedelta(days=7 * k)).isoformat() for k in range(14)]
    i = a.buchen(e, tage)
    assert _serien(api, e, "2024-04-30") == []
    b = _alle_begruendungen(api, [i[0], i[-1]], "2024-04-30")
    assert b[i[-1]]["urteil"] == "nicht_wiederkehrend"
    (bruch,) = rhythmus(eintrag(b[i[-1]]), "monatlich")["schritte"]
    assert (bruch["ergebnis"], bruch["grund"]) == ("bruch", "fremde_zahlung")


@pytest.mark.kern
def test_vierteljaehrlich_mit_zusaetzlicher_zahlung(api):
    a = Abo(api)
    e = a.empfaenger("Fiktiva Haftpflicht AG")
    i = a.buchen(e, ["2024-01-02", "2024-04-02", "2024-07-02", "2024-07-04"], -4_590)
    (s,) = _serien(api, e, "2024-07-31")
    assert (s["rhythmus"], s["buchung_ids"], s["jahreskosten"]) == ("vierteljaehrlich", [i[0], i[1], i[3]], 18_360)
    b = _alle_begruendungen(api, i, "2024-07-31")
    e2 = eintrag(b[i[2]])
    assert e2["urteil"] == "zusaetzlich"
    assert [(r["rhythmus"], r["laenge"], r["erfuellt"]) for r in e2["rhythmen"]] == [
        ("monatlich", 1, False), ("vierteljaehrlich", 3, True)]
    assert [x[0] for x in schritte(e2, "monatlich")] == ["anker", "bruch"]
    assert schritte(e2, "monatlich")[-1][:2] == ("bruch", "abstand")


@pytest.mark.kern
def test_jaehrlich_mit_zusaetzlicher_zahlung(api):
    a = Abo(api)
    e = a.empfaenger("Fiktive Kfz-Steuerkasse")
    i = a.buchen(e, ["2023-03-11", "2024-03-11", "2024-03-12"], [-18_400, -18_400, -5_000])
    (s,) = _serien(api, e)
    assert (s["rhythmus"], s["anzahl"], s["buchung_ids"], s["status"]) == ("jaehrlich", 2, i[:2], "aktiv")
    b = _alle_begruendungen(api, i)
    assert [r["rhythmus"] for r in eintrag(b[i[2]])["rhythmen"]] == ["monatlich", "vierteljaehrlich", "jaehrlich"]
    assert b[i[2]]["urteil"] == "zusaetzlich"


@pytest.mark.kern
def test_zusaetzliche_zahlungen_aendern_betrag_und_faelligkeit_nicht(api):
    """1.3: Betrag, Jahreskosten, letzte Zahlung und nächste Fälligkeit kommen allein aus den Gliedern."""
    a = Abo(api)
    e = a.empfaenger()
    i = a.buchen(e, ["2024-01-15", "2024-02-15", "2024-03-15", "2024-03-18"], [-999, -999, -999, -12_345])
    (s,) = _serien(api, e, "2024-03-31")
    assert (s["betrag"], s["jahreskosten"], s["letzte"], s["naechste_faelligkeit"], s["anzahl"]) == (
        -999, 11_988, "2024-03-15", "2024-04-15", 3)
    assert i[3] not in s["buchung_ids"]


# ------------------------------------------------------------------ Zufallsgruppen gegen die Referenz
@pytest.fixture(scope="module")
def zufall_api(tmp_path_factory):
    a = Abo(neue_api(tmp_path_factory.mktemp("m16zufall")))
    return a


@st.composite
def _gruppe(draw):
    m = draw(st.sampled_from([1, 1, 1, 3, 12]))
    start = dt.date(2022, 1, 1) + dt.timedelta(days=draw(st.integers(0, 60)))
    n = draw(st.integers(2, 6 if m == 12 else 8))
    zahlungen = []
    for k in range(n):
        if k > 0 and draw(st.integers(0, 9)) == 0:
            continue  # ausgelassen
        tag = monat_plus(start, m * k) + dt.timedelta(days=draw(st.integers(-4, 4)))
        zahlungen.append((tag, draw(st.sampled_from([-999, -999, -999, -1_299]))))
        for _ in range(draw(st.integers(0, 2)) if draw(st.booleans()) else 0):
            zahlungen.append((tag + dt.timedelta(days=draw(st.integers(-6, 6))), draw(st.sampled_from([-999, -50]))))
    for _ in range(draw(st.integers(0, 2))):
        zahlungen.append((start + dt.timedelta(days=draw(st.integers(0, 30 * m * n))), -777))
    reihenfolge = draw(st.randoms(use_true_random=False))
    reihenfolge.shuffle(zahlungen)
    return zahlungen


@pytest.mark.kern
@given(zahlungen=_gruppe(), ende=st.integers(-40, 60))
def test_zufallsgruppen_gleich_referenz(zufall_api, zahlungen, ende):
    """Übersicht und Begründung jeder Buchung einer zufälligen Gruppe (Verschiebungen, Lücken, zusätzliche und
    fremde Zahlungen, beliebige Anlagereihenfolge) gleich der Referenz; Begründung und Übersicht stimmen überein."""
    a = zufall_api
    e = a.empfaenger()
    ids = [a.buchen(e, [t.isoformat()], b)[0] for t, b in zahlungen]
    stichtag = (max(t for t, _ in zahlungen) + dt.timedelta(days=ende)).isoformat()
    alle, konten = a.api.alle_buchungen(empfaenger_id=e), a.api.konten()
    soll = wo.uebersicht(alle, konten, [], stichtag)
    ist = [s for s in uebersicht(a.api, stichtag)["serien"] if s["empfaenger"]["id"] == e]
    assert ist == soll["serien"]
    from tests.hilfen.m16 import erwartung
    for bid in random.Random(len(ids)).sample(ids, min(len(ids), 4)):
        antwort = pruefe_begruendung(a.api, bid, stichtag, soll=erwartung(alle, konten, [], bid, stichtag))
        for x in antwort["eintraege"]:
            assert x["serie"] == (ist[0] if ist else None)
            assert (x["urteil"] == "glied") == bool(ist and bid in ist[0]["buchung_ids"])
    assert begruendung(a.api, ids[0], stichtag)["stichtag"] == stichtag
