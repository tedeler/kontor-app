"""M5-Testdaten: Kredite, wiederkehrende Buchungen, Berichte (ohne App).

Prüft die bekannte Wahrheit des Generators gegen unabhängige Orakel (``tests/hilfen/kredit_orakel.py`` mit
Brüchen, ``tests/hilfen/wiederkehrend_orakel.py``) und gegen die Spezifikationsinvarianten.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from generator.iban import ist_gueltig
from generator.m5_daten import feiertage, monat_plus, naechster_werktag
from tests.hilfen import kredit_orakel as ko
from tests.hilfen import wiederkehrend_orakel as wo
from tests.hilfen.pfade import FIXTURES, KMY

pytestmark = pytest.mark.m5


def lade(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kredite():
    return lade("m5/kredite.json")


def test_feiertage_und_werktage():
    f24 = feiertage(2024)
    for tag in ("2024-01-01", "2024-03-29", "2024-04-01", "2024-05-01", "2024-05-09", "2024-05-20", "2024-10-03",
                "2024-12-25", "2024-12-26"):
        assert dt.date.fromisoformat(tag) in f24
    assert len(f24) == 9 and dt.date(2024, 5, 30) not in f24  # Fronleichnam ist nicht bundesweit
    assert naechster_werktag(dt.date(2024, 3, 30)) == dt.date(2024, 4, 2)
    assert monat_plus(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29) == ko.monat_plus(dt.date(2024, 1, 31), 1)
    assert monat_plus(dt.date(2023, 1, 31), 13) == dt.date(2024, 2, 29)


def test_kreditfaelle_gegen_bruchorakel(kredite):
    """Decimal-Rechnung des Generators = Bruch-Orakel der Tests, für jeden Fall."""
    namen = {f["name"] for f in kredite["faelle"]}
    for m in ("30_360", "act_360", "act_365"):
        assert {f"standard_{m}", f"monatsende_{m}", f"sondertilgungen_{m}", f"erste_periode_lang_{m}"} <= namen
    for f in kredite["faelle"]:
        assert ko.plan_oder_fehler(f["parameter"]) == ({"fehler": f["fehler"]} if "fehler" in f else f["plan"]), f["name"]
        if "plan" in f:
            ko.pruefe_plan_eigenschaften(f["plan"], f["parameter"])


def test_kreditfaelle_decken_die_sonderfaelle_ab(kredite):
    nach = {f["name"]: f for f in kredite["faelle"]}
    # Schaltjahr: act/365 rechnet den 29.02. als Tag, Basis bleibt 365
    z = nach["schaltjahr_kurz_act_365"]["plan"]["zeilen"]
    assert z[0]["faelligkeit"] == "2024-02-29" and z[1]["zinstage"] == 29
    # Monatsende: Fälligkeit am 31. wird im Februar der 29., im April der 30., danach wieder der 31.
    fs = [x["faelligkeit"] for x in nach["monatsende_act_360"]["plan"]["zeilen"][:5]]
    assert fs == ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30", "2024-05-31"]
    assert [x["zinstage"] for x in nach["monatsende_30_360"]["plan"]["zeilen"][:4]] == [30, 30, 30, 30]
    assert [x["zinstage"] for x in nach["monatsende_act_360"]["plan"]["zeilen"][:4]] == [31, 29, 31, 30]
    # Sondertilgung innerhalb der Periode und am Fälligkeitstag
    st = nach["sondertilgungen_30_360"]["plan"]["zeilen"]
    assert sum(x["sondertilgung"] for x in st) == 2_050_000
    assert [x["sondertilgung"] for x in st if x["faelligkeit"] == "2025-04-01"] == [750_000]
    # über die Restschuld hinaus: begrenzt, letzte Rate nur Zins
    ue = nach["sondertilgung_ueber_rest"]["plan"]
    assert ue["zeilen"][-1]["tilgung"] == 0 and ue["zeilen"][-1]["rate"] == ue["zeilen"][-1]["zins"] > 0
    assert ue["summe_sondertilgung"] < 9_999_999
    assert nach["zins_null"]["plan"]["summe_zins"] == 0
    assert nach["rate_zu_klein"]["fehler"] == "kredit_rate_zu_klein"
    # gebrochene erste Periode: 30E/360 bzw. tatsächliche Tage
    assert nach["standard_30_360"]["plan"]["zeilen"][0]["zinstage"] == 16
    assert nach["standard_act_360"]["plan"]["zeilen"][0]["zinstage"] == 17
    assert nach["erste_periode_lang_30_360"]["plan"]["zeilen"][0]["zinstage"] == 75


def test_kredit_sync_wahrheit():
    daten, erw = lade("mock/m5_kredit.json"), lade("mock/m5_kredit.erwartung.json")
    umsaetze = daten["bank"]["umsaetze"]
    assert all(ist_gueltig(k["iban"]) and k["iban"][4:12] == "00000000" for k in daten["bank"]["konten"])
    raten = [u for u in umsaetze if erw["umsatz_art"][u["umsatz_id"]]["art"] == "rate"]
    assert len(raten) == 13
    for m, w in erw["methoden"].items():
        param = {**{k: erw["kredit"][k] for k in ("restschuld", "stand_datum", "sollzins", "rate",
                                                   "erste_faelligkeit", "sondertilgungen")}, "zinsmethode": m}
        pl = {z["faelligkeit"]: z for z in ko.plan(param)["zeilen"]}
        for u in raten:
            a = w["aufteilung"][u["umsatz_id"]]
            assert abs((dt.date.fromisoformat(u["buchungstag"]) - dt.date.fromisoformat(a["faelligkeit"])).days) <= 5
            assert (a["zins"], a["tilgung"]) == (pl[a["faelligkeit"]]["zins"], pl[a["faelligkeit"]]["tilgung"])
            assert a["zins"] + a["tilgung"] == erw["kredit"]["rate"]
        assert len(w["raten_2024"]) == 12
        for name, a in w["jahresauszug_2024"].items():
            assert sum(k["betrag"] for k in a["korrektur"]) == 0, name
            assert (a["restschuld"] - a["restschuld_berechnet"], a["zinsen"] - a["zinsen_berechnet"]) == (
                a["differenz_restschuld"], a["differenz_zinsen"])
            assert (len(a["korrektur"]) == 0) == (name == "exakt")


def test_wiederkehrend_wahrheit_gegen_orakel():
    """Die aus der Konstruktion abgeleiteten Serien sind genau die, die die Spezifikationsregel erkennt."""
    daten, erw = lade("mock/m5_wiederkehrend.json"), lade("mock/m5_wiederkehrend.erwartung.json")
    umsaetze = daten["bank"]["umsaetze"]
    konten = [{"id": 1, "art": "girokonto"}]
    namen = sorted({u["gegenpartei_name"] for u in umsaetze})
    eid = {n: i + 1 for i, n in enumerate(namen)}
    nach_uid = {}
    buchungen = []
    for i, u in enumerate(umsaetze, 1):
        buchungen.append({"id": i, "datum": u["buchungstag"], "empfaenger": {"id": eid[u["gegenpartei_name"]],
                                                                             "name": u["gegenpartei_name"]},
                          "splits": [{"konto_id": 1, "betrag": u["betrag"]}]})
        nach_uid[u["umsatz_id"]] = i
    for stichtag, soll in erw["serien"].items():
        ist = wo.uebersicht(buchungen, konten, [], stichtag)["serien"]
        ist_v = sorted(({**{k: s[k] for k in ("rhythmus", "anzahl", "erste", "letzte", "betrag", "jahreskosten",
                                               "naechste_faelligkeit", "status", "richtung")},
                         "empfaenger": s["empfaenger"]["name"], "buchung_ids": s["buchung_ids"]} for s in ist),
                       key=lambda s: s["empfaenger"])
        soll_v = [{**{k: v for k, v in s.items() if k != "umsatz_ids"},
                   "buchung_ids": [nach_uid[u] for u in s["umsatz_ids"]]} for s in soll]
        assert ist_v == soll_v, stichtag
    assert erw["serien"]["2023-02-15"] == []
    assert {s["status"] for s in erw["serien"]["2024-07-20"]} == {"aktiv", "ausbleibend"}
    assert {s["status"] for s in erw["serien"]["2024-08-09"]} == {"aktiv", "beendet"}
    assert {s["rhythmus"] for s in erw["serien"]["2024-12-31"]} == {"monatlich", "vierteljaehrlich", "jaehrlich"}
    for n in erw["nicht_wiederkehrend"]:
        assert all(s["empfaenger"] != n for v in erw["serien"].values() for s in v)
    # Wochenend- und Feiertagsverschiebung kommt in den Serien vor
    tage = {u["buchungstag"] for u in umsaetze if u["gegenpartei_name"] == "Wohnbau Fiktiva eG"}
    assert "2024-04-02" in tage and "2023-01-02" in tage


def test_wiederkehrend_progression_gegen_orakel():
    """Benachrichtigungen im wöchentlichen Abruf: Orakel über alle Abrufe = Wahrheit des Generators."""
    daten, erw = lade("mock/m5_wiederkehrend.json"), lade("mock/m5_wiederkehrend.erwartung.json")
    umsaetze = sorted(daten["bank"]["umsaetze"], key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    pr = erw["progression"]
    konten = [{"id": 1, "art": "girokonto"}]
    eid: dict[str, int] = {}
    buchungen, uid_id = [], {}
    gesehen: set[str] = set()
    alle: list[tuple[str, str]] = []
    grenze = pr["progression_start"]
    neu = [u for u in umsaetze if u["buchungstag"] <= grenze]
    for abruf in [None] + pr["abrufe"]:
        if abruf is not None:
            neu = [u for u in umsaetze if grenze < u["buchungstag"] <= abruf]
            grenze = abruf
        ids = []
        for u in neu:
            eid.setdefault(u["gegenpartei_name"], len(eid) + 1)
            bid = len(buchungen) + 1
            buchungen.append({"id": bid, "datum": u["buchungstag"], "empfaenger": {"id": eid[u["gegenpartei_name"]],
                                                                                   "name": u["gegenpartei_name"]},
                              "splits": [{"konto_id": 1, "betrag": u["betrag"]}]})
            uid_id[u["umsatz_id"]] = bid
            ids.append(bid)
        heute = abruf or pr["progression_start"]
        for art, schl in wo.ereignisse(buchungen, konten, [], ids if abruf else [], heute):
            if schl not in gesehen:
                gesehen.add(schl)
                alle.append((art, schl))
    soll = []
    for b in pr["benachrichtigungen"]:
        if b["art"] == "neuer_empfaenger":
            soll.append((b["art"], f"neuer_empfaenger:{eid[b['empfaenger']]}"))
        elif b["art"] == "wiederkehrend_betrag":
            soll.append((b["art"], f"wiederkehrend_betrag:{uid_id[b['umsatz_id']]}"))
        else:
            soll.append((b["art"], f"wiederkehrend_ausbleibend:1:{eid[b['empfaenger']]}:{b['richtung']}:"
                                   f"{b['naechste_faelligkeit']}"))
    assert sorted(alle) == sorted(soll)


def test_berichte_wahrheit_konsistent():
    b = lade("m5/berichte.erwartung.json")
    std = json.loads((KMY / "standard.erwartung.json").read_text(encoding="utf-8"))
    saldo = {k["extern_id"]: k["saldo"] for k in std["konten"]}
    gross = b["kontostand"][0]
    assert gross["intervall"] == "monat" and len(gross["stichtage"]) == 37
    letzte = max(x["datum"] for x in std["buchungen"])
    assert letzte <= gross["bis"]
    for k, werte in gross["werte"].items():
        assert werte[-1] == saldo[k], k
    tage = b["kontostand"][1]["stichtage"]
    assert "2024-02-29" in tage and len(tage) == 15
    for ea in b["einnahmen_ausgaben"]:
        g = ea["gesamt"]
        assert g["saldo"] == g["einnahmen"] - g["ausgaben"]
        art = {k["extern_id"]: k["art"] for k in std["konten"]}
        assert g["ausgaben"] == sum(v for k, v in ea["kategorien"].items() if art[k] == "aufwand")
        assert g["einnahmen"] == -sum(v for k, v in ea["kategorien"].items() if art[k] == "ertrag")
        per = ea["perioden"]
        assert per[0]["von"] == ea["von"] and per[-1]["bis"] == ea["bis"]
    assert b["umbuchungen_anzahl"] > 0 and len(b["export"]["extern_ids"]) > 10
