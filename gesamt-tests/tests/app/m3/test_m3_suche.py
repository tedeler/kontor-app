"""M3: Volltextsuche über Konten, Empfänger, Verwendungszwecke und Tags (buchhaltungspflege.md 6, T 14).

Erwartung: Suchanfragen mit Treffern aus dem Generator (``m3/suche.json``) und ein unabhängiges Orakel
(``tests/hilfen/m3_orakel.suche_erwartet``) auf dem vollständigen REST-Zustand.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, strategies as st

from tests.hilfen import m3_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import nach_kennung, sync
from tests.hilfen.m3 import SUCHE, lade_m3, m3_api, stammdaten_anlegen

VON = "2024-01-01"


def suche(api, q, **p):
    return api.get("/api/suche", params={"q": q, **p}, erwartet=200).daten


@pytest.fixture(scope="module")
def sapi(tmp_path_factory):
    """Nur lesend verwenden: Zustand „nur synchronisiert“ aus m3/suche.json."""
    api = m3_api(tmp_path_factory.mktemp("suche"))
    sync(api, von=VON)
    return api


def _zustand(api):
    return {"konten": api.konten(), "empfaenger": api.get("/api/empfaenger", erwartet=200).daten,
            "tags": api.get("/api/tags", erwartet=200).daten, "buchungen": api.alle_buchungen()}


def _pruefe(api, q, z=None, limit=500):
    z = z or _zustand(api)
    soll = orakel.suche_erwartet(q, **z)
    r = suche(api, q, limit=limit)
    assert r["q"] == q
    assert [k["id"] for k in r["konten"]] == soll["konten"], q
    assert [e["id"] for e in r["empfaenger"]] == soll["empfaenger"], q
    assert [t["id"] for t in r["tags"]] == soll["tags"], q
    assert [b["id"] for b in r["buchungen"]] == soll["buchungen"][:limit], q
    assert r["buchungen_gesamt"] == len(soll["buchungen"])
    kd = {k["id"]: k for k in z["konten"]}
    for k in r["konten"]:
        assert k == kd[k["id"]]
    bd = {b["id"]: b for b in z["buchungen"]}
    for b in r["buchungen"]:
        assert b == bd[b["id"]], "Buchungen wie in der Liste ohne konto_id (betrag = Umsatz)"
    return r


@pytest.mark.kern
def test_anfragen_aus_dem_generator(sapi, netz_gesperrt):
    s = json.loads(SUCHE.read_text(encoding="utf-8"))
    bank = nach_kennung(sapi.alle_buchungen())
    daten, _ = lade_m3()
    uid_zu_id = {u["umsatz_id"]: bank[f"bank:{u['iban']}:{u['umsatz_id']}"]["id"]
                 for u in daten["bank"]["umsaetze"] if not u["vormerkung"]}
    for a in s["anfragen"]:
        r = suche(sapi, a["q"], limit=500)
        assert sorted(b["id"] for b in r["buchungen"]) == sorted(uid_zu_id[u] for u in a["buchungen"]), a["q"]
        assert [(b["datum"], b["id"]) for b in r["buchungen"]] == sorted(((b["datum"], b["id"]) for b in r["buchungen"]),
                                                                       reverse=True), "datum, dann id absteigend"
        assert sorted(e["name"] for e in r["empfaenger"]) == a["empfaenger"], a["q"]
        assert sorted(k["name"] for k in r["konten"]) == a["konten"], a["q"]
        assert r["tags"] == [] and r["buchungen_gesamt"] == len(a["buchungen"])


@pytest.mark.kern
@pytest.mark.parametrize("q", ["bäckerei müller", "BAECKEREI", "Bäckerei", "cafe", "CAFÉ", "STRAßE", "strasse",
                               "groß", "kino film", "kinofilm", "ﬁlm", "tagesgeld", "GIRO miete", "DE", "0000",
                               "unkategorisiert sparrate", "x"])
def test_suche_gegen_orakel(sapi, q, netz_gesperrt):
    _pruefe(sapi, q)


@pytest.mark.kern
def test_konten_tags_aliase_notizen(tmp_path, netz_gesperrt):
    api = m3_api(tmp_path)
    stammdaten_anlegen(api)
    sync(api, von=VON)
    konten = {k["name"]: k for k in api.konten()}
    api.patch(f"/api/konten/{konten['Girokonto']['id']}", json={"notiz": "Hausbank an der Hauptstraße"}, erwartet=200)
    t1 = api.tag("Steuer 2024")
    t2 = api.tag("Ölheizung")
    bs = api.alle_buchungen()
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [b["id"] for b in bs[:5]],
                                                   "hinzufuegen": [t1["id"]]}, erwartet=200)
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [bs[7]["id"]], "hinzufuegen": [t2["id"]]},
             erwartet=200)
    api.post("/api/buchungen", json={"datum": "2024-06-30", "verwendungszweck": "", "splits": [
        {"konto_id": konten["Girokonto"]["id"], "betrag": -1, "memo": "Spende Tierheim"},
        {"konto_id": konten["Sonstiges"]["id"], "betrag": 1, "memo": "Zweite Zeile"}]}, erwartet=201)
    z = _zustand(api)
    for q in ("steuer", "oelheizung", "ÖL", "hauptstrasse", "SWM", "swm energie", "cafe bohne", "spende",
              "zweite zeile", "steuer girokonto", "stadtwerke strom", "lebensmittel", "2024"):
        _pruefe(api, q, z)
    r = suche(api, "swm")
    assert [e["name"] for e in r["empfaenger"]] == ["Stadtwerke Musterstadt"], "Treffer über Alias"
    r = suche(api, "oelheizung")
    assert [t["id"] for t in r["tags"]] == [t2["id"]] and r["tags"][0]["anzahl_buchungen"] == 1
    assert [b["id"] for b in r["buchungen"]] == [bs[7]["id"]]


def test_limit_und_validierung(sapi, netz_gesperrt):
    voll = suche(sapi, "girokonto", limit=500)
    assert voll["buchungen_gesamt"] > 3
    drei = suche(sapi, "girokonto", limit=3)
    assert drei["buchungen"] == voll["buchungen"][:3] and drei["buchungen_gesamt"] == voll["buchungen_gesamt"]
    assert len(suche(sapi, "girokonto")["buchungen"]) == min(50, voll["buchungen_gesamt"]), "Vorgabe 50"
    for p in ({}, {"q": ""}, {"q": "   "}, {"q": "x" * 201}, {"q": "a", "limit": 0}, {"q": "a", "limit": 501},
              {"q": "a", "limit": "viele"}):
        assert fehlercode(sapi.get("/api/suche", params=p, erwartet=422)) == "validierung"


ZEICHEN = st.sampled_from(list("aeiouäöüÄÖÜßSsEeéÉcfnlrt -") + ["ä", "ö", "ﬁ", "Straße", "Mü"])


@given(q=st.lists(ZEICHEN, min_size=1, max_size=6).map("".join).filter(lambda s: s.strip()))
def test_zufaellige_anfragen(sapi, q):
    _pruefe(sapi, q)
