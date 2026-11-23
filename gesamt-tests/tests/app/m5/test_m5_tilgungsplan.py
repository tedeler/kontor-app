"""M5: Tilgungsplan (kredite.md 3; T 12, T 22) über Python und REST.

Erwartungen: unabhängig mit Decimal berechnete Pläne des Generators (``fixtures/m5/kredite.json``) und das
Bruch-Orakel ``tests/hilfen/kredit_orakel.py`` für zufällige Parameter (Hypothesis).
"""

from __future__ import annotations

import datetime as dt
from fractions import Fraction

import pytest
from hypothesis import given, strategies as st

from tests.hilfen import kontor
from tests.hilfen import kredit_orakel as ko
from tests.hilfen.api import fehlercode
from tests.hilfen.m5 import kreditfaelle

pytestmark = pytest.mark.kern

FAELLE = kreditfaelle()


def _tp():
    return kontor.modul("kontor.kredite").tilgungsplan


@pytest.mark.parametrize("fall", FAELLE, ids=[f["name"] for f in FAELLE])
def test_plan_gleich_referenz_python(fall):
    if "fehler" in fall:
        with pytest.raises(kontor.fehler().KreditRateZuKlein):
            _tp()(fall["parameter"])
        return
    assert _tp()(fall["parameter"]) == fall["plan"], fall["beschreibung"]


@pytest.mark.parametrize("fall", FAELLE, ids=[f["name"] for f in FAELLE])
def test_plan_gleich_referenz_rest(api, fall):
    if "fehler" in fall:
        r = api.post("/api/kredite/tilgungsplan", json=fall["parameter"], erwartet=422)
        assert fehlercode(r) == "kredit_rate_zu_klein"
        return
    plan = api.post("/api/kredite/tilgungsplan", json=fall["parameter"], erwartet=200).daten
    assert plan == fall["plan"], fall["beschreibung"]


def test_zinsmethode_vorgabe_30_360(api):
    p = {k: v for k, v in next(f for f in FAELLE if f["name"] == "standard_30_360")["parameter"].items()
         if k not in ("zinsmethode", "sondertilgungen")}
    soll = next(f for f in FAELLE if f["name"] == "standard_30_360")["plan"]
    assert api.post("/api/kredite/tilgungsplan", json=p, erwartet=200).daten == soll
    assert _tp()(p) == soll
    assert api.get("/api/aenderungen", erwartet=200).daten["gesamt"] == 0, "Planberechnung erzeugt keine Änderung"


def test_methoden_unterscheiden_sich_wie_spezifiziert():
    """Gleiche Parameter: 30/360 zählt volle Perioden zu 30 Tagen, act/* die tatsächlichen; act/365 < act/360."""
    nach = {f["name"]: f for f in FAELLE}
    a, b, c = (_tp()(nach[f"monatsende_{m}"]["parameter"]) for m in ("30_360", "act_360", "act_365"))
    assert [z["zinstage"] for z in a["zeilen"][1:13]] == [30] * 12
    assert [z["zinstage"] for z in b["zeilen"][:12]] == [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    assert [z["zinstage"] for z in c["zeilen"][:12]] == [z["zinstage"] for z in b["zeilen"][:12]]
    assert c["summe_zins"] < b["summe_zins"]
    # Februar 2024 (29 Tage) unter act/365: Zins auf Basis 365, nicht 366
    z = c["zeilen"][1]
    assert z["zins"] == ko.kaufmaennisch(Fraction(z["restschuld_vorher"] * 41_250 * 29, 365 * 1_000_000))


@pytest.mark.parametrize("feld,wert", [("restschuld", 0), ("rate", 0), ("sollzins", -1), ("sollzins", 1_000_001),
                                       ("rate", 12.5), ("restschuld", "100"), ("zinsmethode", "30E/360"),
                                       ("erste_faelligkeit", "2024-01-15"), ("erste_faelligkeit", "2024-01-01"),
                                       ("stand_datum", "15.01.2024"), ("unbekannt", 1),
                                       ("sondertilgungen", [{"datum": "2024-01-15", "betrag": 100}]),
                                       ("sondertilgungen", [{"datum": "2024-03-01", "betrag": 0}]),
                                       ("sondertilgungen", [{"datum": "2024-03-01"}])])
def test_ungueltige_parameter_422(api, feld, wert):
    p = {"restschuld": 1_000_000, "stand_datum": "2024-01-15", "sollzins": 30_000, "rate": 50_000,
         "erste_faelligkeit": "2024-02-01", feld: wert}
    r = api.post("/api/kredite/tilgungsplan", json=p, erwartet=422)
    assert fehlercode(r) == "validierung"


def test_ohne_pflichtfeld_422(api):
    for weg in ("restschuld", "stand_datum", "sollzins", "rate", "erste_faelligkeit"):
        p = {"restschuld": 1_000_000, "stand_datum": "2024-01-15", "sollzins": 30_000, "rate": 50_000,
             "erste_faelligkeit": "2024-02-01"}
        del p[weg]
        assert fehlercode(api.post("/api/kredite/tilgungsplan", json=p, erwartet=422)) == "validierung"


# ------------------------------------------------------------------ Hypothesis
TAG0 = dt.date(2020, 1, 1)


@st.composite
def parameter(draw, sonder: bool = True):
    methode = draw(st.sampled_from(["30/360", "act/360", "act/365"]))
    restschuld = draw(st.integers(1, 200_000_000))
    sollzins = draw(st.integers(0, 150_000))
    stand = TAG0 + dt.timedelta(days=draw(st.integers(0, 3650)))
    erste = stand + dt.timedelta(days=draw(st.integers(1, 80)))
    monatszins = restschuld * sollzins // 12_000_000
    rate = max(1, monatszins + draw(st.integers(1, restschuld // 50 + 1)))
    p = {"restschuld": restschuld, "stand_datum": stand.isoformat(), "sollzins": sollzins, "zinsmethode": methode,
         "rate": rate, "erste_faelligkeit": erste.isoformat()}
    if sonder:
        p["sondertilgungen"] = [{"datum": (stand + dt.timedelta(days=draw(st.integers(1, 1500)))).isoformat(),
                                 "betrag": draw(st.integers(1, restschuld))}
                                for _ in range(draw(st.integers(0, 3)))]
    return p


@given(p=parameter())
def test_zufaellige_plaene_gleich_orakel(p):
    soll = ko.plan_oder_fehler(p)
    if "fehler" in soll:
        with pytest.raises(kontor.fehler().KreditRateZuKlein):
            _tp()(p)
        return
    ist = _tp()(p)
    assert ist == soll
    ko.pruefe_plan_eigenschaften(ist, p)


@given(p=parameter(sonder=False))
def test_kein_auflaufen_von_rundungsfehlern(p):
    """T 12/T 22: Abweichung von der ungerundeten Rechnung höchstens die aufgezinsten halben Cent."""
    try:
        pl = _tp()(p)
    except kontor.fehler().KreditRateZuKlein:
        return
    satz = Fraction(p["sollzins"], 1_000_000)
    schranke = Fraction(0)
    for z in pl["zeilen"][:-1]:
        schranke = schranke * (1 + satz * z["zinstage"] / ko.basis(p["zinsmethode"])) + Fraction(1, 2)
        exakt = ko.exakte_restschuld(p, z["nr"])
        assert abs(z["restschuld_nachher"] - exakt) <= schranke, (z, exakt, schranke)
        assert z["zins"] + z["tilgung"] == p["rate"]


def test_rest_gleich_python_fuer_zufaellige_parameter(api):
    import random
    rnd = random.Random(4711)
    for _ in range(25):
        restschuld = rnd.randint(1, 50_000_000)
        sollzins = rnd.randint(0, 99_999)
        stand = TAG0 + dt.timedelta(days=rnd.randint(0, 3000))
        p = {"restschuld": restschuld, "stand_datum": stand.isoformat(), "sollzins": sollzins,
             "zinsmethode": rnd.choice(["30/360", "act/360", "act/365"]),
             "rate": restschuld * sollzins // 12_000_000 + rnd.randint(1, restschuld // 20 + 1),
             "erste_faelligkeit": (stand + dt.timedelta(days=rnd.randint(1, 45))).isoformat(),
             "sondertilgungen": [{"datum": (stand + dt.timedelta(days=rnd.randint(1, 900))).isoformat(),
                                  "betrag": rnd.randint(1, restschuld)} for _ in range(rnd.randint(0, 2))]}
        r = api.post("/api/kredite/tilgungsplan", json=p, erwartet=(200, 422))
        soll = ko.plan_oder_fehler(p)
        if r.status_code == 422:
            assert fehlercode(r) == "kredit_rate_zu_klein" and "fehler" in soll
        else:
            assert r.daten == soll == _tp()(p)
