"""Mehrfachbearbeitung: Kategorie und Tags für markierte Buchungen, atomar (K 5, T 14, E-021)."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode

KAT_PFAD = "/api/buchungen/mehrfach/kategorie"
TAG_PFAD = "/api/buchungen/mehrfach/tags"


@pytest.fixture
def welt(api):
    """Konten und verschiedene Buchungsarten."""
    k = {n: api.konto(n, a)["id"] for n, a in [("giro", "girokonto"), ("spar", "sparkonto"), ("leb", "aufwand"),
                                                ("cafe", "aufwand"), ("geh", "ertrag"), ("ek", "eigenkapital")]}
    b = {
        "einfach1": api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)]),
        "einfach2": api.buchung("2024-01-02", [(k["giro"], -200, "m"), (k["cafe"], 200, "Kaffee")]),
        "ertrag": api.buchung("2024-01-03", [(k["giro"], 300), (k["geh"], -300)], status="importiert"),
        "ek": api.buchung("2024-01-04", [(k["giro"], -400), (k["ek"], 400)], status="vorlaeufig"),
        "umbuchung": api.buchung("2024-01-05", [(k["giro"], -500), (k["spar"], 500)]),
        "split": api.buchung("2024-01-06", [(k["giro"], -600), (k["leb"], 300), (k["cafe"], 300)]),
        "nicht_markiert": api.buchung("2024-01-07", [(k["giro"], -700), (k["leb"], 700)]),
    }
    gesperrt = api.buchung("2024-01-08", [(k["giro"], -800), (k["leb"], 800)])
    b["gesperrt"] = api.patch(f"/api/buchungen/{gesperrt['id']}", json={"status": "abgeglichen"}, erwartet=200).daten
    return api, k, b


@pytest.mark.kern
def test_kategorie_genau_die_markierten(welt):
    api, k, b = welt
    markiert = [b["einfach2"]["id"], b["einfach1"]["id"], b["ertrag"]["id"], b["ek"]["id"]]
    vorher = {x["id"]: x for x in api.alle_buchungen()}
    r = api.post(KAT_PFAD, json={"buchung_ids": markiert, "kategorie_id": k["cafe"]}, erwartet=200).daten
    assert r == {"geaendert": sorted(markiert), "anzahl": 4}
    nachher = {x["id"]: x for x in api.alle_buchungen()}
    for bid, alt in vorher.items():
        neu = nachher[bid]
        if bid not in markiert:
            assert neu == alt, "nicht markierte Buchung verändert"
            continue
        gegen = [i for i, s in enumerate(alt["splits"]) if s["konto_id"] not in (k["giro"], k["spar"])]
        assert len(gegen) == 1
        erwartet_splits = [dict(s) for s in alt["splits"]]
        erwartet_splits[gegen[0]]["konto_id"] = k["cafe"]
        assert neu == {**alt, "splits": erwartet_splits, "kategorie_id": k["cafe"]}
    s = api.salden()
    assert s[k["cafe"]]["saldo"] == 100 + 200 - 300 + 400 + 300
    assert s[k["ek"]]["saldo"] == 0 and s[k["geh"]]["saldo"] == 0
    assert api.uebersicht()["summe_gesamt"] == 0


def test_kategorie_ein_einzelner_und_gleiche_kategorie(welt):
    api, k, b = welt
    vorher = api.zustand()
    r = api.post(KAT_PFAD, json={"buchung_ids": [b["einfach1"]["id"]], "kategorie_id": k["leb"]}, erwartet=200).daten
    assert r == {"geaendert": [b["einfach1"]["id"]], "anzahl": 1}
    assert api.zustand() == vorher


@pytest.mark.kern
@pytest.mark.parametrize("fall,code,status,ids", [
    ("umbuchung", "nicht_kategorisierbar", 422, ["umbuchung"]),
    ("split", "nicht_kategorisierbar", 422, ["split"]),
    ("beide", "nicht_kategorisierbar", 422, ["umbuchung", "split"]),
    ("gesperrt", "buchung_gesperrt", 409, ["gesperrt"]),
    ("gesperrt_vor_kategorisierbar", "buchung_gesperrt", 409, ["gesperrt"]),
    ("unbekannt", "referenz_unbekannt", 422, None),
])
def test_kategorie_atomar(welt, fall, code, status, ids):
    """Kann eine markierte Buchung nicht geändert werden, wird keine geändert (E-021)."""
    api, k, b = welt
    markiert = [b["einfach1"]["id"], b["einfach2"]["id"]]
    if fall == "beide":
        markiert += [b["umbuchung"]["id"], b["split"]["id"]]
    elif fall == "gesperrt_vor_kategorisierbar":
        markiert += [b["gesperrt"]["id"], b["split"]["id"]]
    elif fall == "unbekannt":
        markiert += [4711, 4712]
    else:
        markiert.append(b[fall]["id"])
    vorher = api.zustand()
    r = api.post(KAT_PFAD, json={"buchung_ids": markiert, "kategorie_id": k["geh"]}, erwartet=status)
    f = r.json()["fehler"]
    assert f["code"] == code
    soll_ids = sorted(b[n]["id"] for n in ids) if ids else [4711, 4712]
    assert sorted(f["details"]["buchung_ids"]) == soll_ids
    assert api.zustand() == vorher, "Mehrfachbearbeitung nicht atomar"


@pytest.mark.parametrize("ziel", ["giro", "spar", "ek", 4711])
def test_kategorie_ziel_ungueltig(welt, ziel):
    api, k, b = welt
    vorher = api.zustand()
    kid = k.get(ziel, ziel)
    r = api.post(KAT_PFAD, json={"buchung_ids": [b["einfach1"]["id"], b["split"]["id"]], "kategorie_id": kid},
                 erwartet=422)
    assert fehlercode(r) == "kategorie_ungueltig"
    assert api.zustand() == vorher


def test_kategorie_pruefreihenfolge(welt):
    """422 validierung → 422 referenz_unbekannt → 422 kategorie_ungueltig → 409 gesperrt → 422 nicht_kategorisierbar."""
    api, k, b = welt
    g, s = b["gesperrt"]["id"], b["split"]["id"]
    assert fehlercode(api.post(KAT_PFAD, json={"buchung_ids": [g, g], "kategorie_id": 4711},
                               erwartet=422)) == "validierung"
    assert fehlercode(api.post(KAT_PFAD, json={"buchung_ids": [g, s, 4711], "kategorie_id": 4711},
                               erwartet=422)) == "referenz_unbekannt"
    assert fehlercode(api.post(KAT_PFAD, json={"buchung_ids": [g, s], "kategorie_id": k["giro"]},
                               erwartet=422)) == "kategorie_ungueltig"
    assert fehlercode(api.post(KAT_PFAD, json={"buchung_ids": [s, g], "kategorie_id": k["leb"]},
                               erwartet=409)) == "buchung_gesperrt"
    assert fehlercode(api.post(KAT_PFAD, json={"buchung_ids": [s], "kategorie_id": k["leb"]},
                               erwartet=422)) == "nicht_kategorisierbar"


@pytest.mark.parametrize("body", [
    {"buchung_ids": [], "kategorie_id": 1}, {"kategorie_id": 1}, {"buchung_ids": [1]},
    {"buchung_ids": [1, 1], "kategorie_id": 1}, {"buchung_ids": "1", "kategorie_id": 1},
    {"buchung_ids": [1], "kategorie_id": 1, "tag_ids": []},
], ids=str)
def test_kategorie_validierung(welt, body):
    api, k, b = welt
    vorher = api.zustand()
    assert fehlercode(api.post(KAT_PFAD, json=body, erwartet=422)) == "validierung"
    assert api.zustand() == vorher


# --------------------------------------------------------------------- Tags


@pytest.mark.kern
def test_tags_hinzufuegen_und_entfernen(welt):
    api, k, b = welt
    t = {n: api.tag(n)["id"] for n in ("A", "B", "C")}
    api.patch(f"/api/buchungen/{b['einfach1']['id']}", json={"tag_ids": [t["A"], t["C"]]}, erwartet=200)
    api.patch(f"/api/buchungen/{b['nicht_markiert']['id']}", json={"tag_ids": [t["A"]]}, erwartet=200)
    markiert = [b["umbuchung"]["id"], b["einfach1"]["id"], b["gesperrt"]["id"], b["split"]["id"]]
    vorher = {x["id"]: x for x in api.alle_buchungen()}
    r = api.post(TAG_PFAD, json={"buchung_ids": markiert, "hinzufuegen": [t["B"], t["B"]], "entfernen": [t["A"]]},
                 erwartet=200).daten
    assert r == {"geaendert": sorted(markiert), "anzahl": 4}
    nachher = {x["id"]: x for x in api.alle_buchungen()}
    for bid, alt in vorher.items():
        if bid not in markiert:
            assert nachher[bid] == alt
            continue
        soll = ({x["id"] for x in alt["tags"]} - {t["A"]}) | {t["B"]}
        assert nachher[bid] == {**alt, "tags": [{"id": i, "name": n} for n, i in sorted(t.items(), key=lambda x: x[1])
                                                if i in soll]}
    anzahl = {x["id"]: x["anzahl_buchungen"] for x in api.get("/api/tags", erwartet=200).daten}
    assert anzahl == {t["A"]: 1, t["B"]: 4, t["C"]: 1}


def test_tags_erst_entfernen_dann_hinzufuegen(welt):
    api, k, b = welt
    t = api.tag("X")["id"]
    bid = b["einfach1"]["id"]
    api.post(TAG_PFAD, json={"buchung_ids": [bid], "hinzufuegen": [t], "entfernen": [t]}, erwartet=200)
    assert [x["id"] for x in api.buchung_lesen(bid)["tags"]] == [t]
    api.post(TAG_PFAD, json={"buchung_ids": [bid], "entfernen": [t]}, erwartet=200)
    assert api.buchung_lesen(bid)["tags"] == []
    # Entfernen eines nicht zugeordneten Tags und leere Listen sind kein Fehler
    vorher = api.zustand()
    assert api.post(TAG_PFAD, json={"buchung_ids": [bid], "entfernen": [t]}, erwartet=200).daten == \
        {"geaendert": [bid], "anzahl": 1}
    api.post(TAG_PFAD, json={"buchung_ids": [bid]}, erwartet=200)
    assert api.zustand() == vorher


@pytest.mark.kern
@pytest.mark.parametrize("fall", ["buchung", "tag_hinzu", "tag_entfernen"])
def test_tags_atomar_bei_unbekannter_referenz(welt, fall):
    api, k, b = welt
    t = api.tag("T")["id"]
    ids = [b["einfach1"]["id"], b["einfach2"]["id"]] + ([4711] if fall == "buchung" else [])
    body = {"buchung_ids": ids, "hinzufuegen": [t] + ([4712] if fall == "tag_hinzu" else []),
            "entfernen": [4713] if fall == "tag_entfernen" else []}
    vorher = api.zustand()
    assert fehlercode(api.post(TAG_PFAD, json=body, erwartet=422)) == "referenz_unbekannt"
    assert api.zustand() == vorher


@pytest.mark.parametrize("body", [
    {"buchung_ids": []}, {}, {"buchung_ids": [1, 1]}, {"buchung_ids": [1], "hinzufuegen": "A"},
    {"buchung_ids": [1], "setzen": [1]},
], ids=str)
def test_tags_validierung(welt, body):
    api, k, b = welt
    if body.get("buchung_ids") == [1]:
        body = {**body, "buchung_ids": [b["einfach1"]["id"]]}
    assert fehlercode(api.post(TAG_PFAD, json=body, erwartet=422)) == "validierung"


# ---------------------------------------------------- Hypothesis gegen Modell


@pytest.mark.kern
@given(markiert=st.sets(st.sampled_from(["einfach1", "einfach2", "ertrag", "ek", "umbuchung", "split",
                                         "nicht_markiert", "gesperrt", "fremd"]), min_size=1),
       ziel=st.sampled_from(["leb", "cafe", "geh", "giro", "ek", "fremd"]))
def test_mehrfach_kategorie_gegen_modell(api_fabrik, markiert, ziel):
    api = api_fabrik()
    k = {n: api.konto(n, a)["id"] for n, a in [("giro", "girokonto"), ("spar", "sparkonto"), ("leb", "aufwand"),
                                                ("cafe", "aufwand"), ("geh", "ertrag"), ("ek", "eigenkapital")]}
    b = {
        "einfach1": api.buchung("2024-01-01", [(k["giro"], -100), (k["leb"], 100)]),
        "einfach2": api.buchung("2024-01-02", [(k["giro"], -200), (k["cafe"], 200)]),
        "ertrag": api.buchung("2024-01-03", [(k["giro"], 300), (k["geh"], -300)]),
        "ek": api.buchung("2024-01-04", [(k["giro"], -400), (k["ek"], 400)]),
        "umbuchung": api.buchung("2024-01-05", [(k["giro"], -500), (k["spar"], 500)]),
        "split": api.buchung("2024-01-06", [(k["giro"], -600), (k["leb"], 300), (k["cafe"], 300)]),
        "nicht_markiert": api.buchung("2024-01-07", [(k["giro"], -700), (k["leb"], 700)]),
        "gesperrt": api.buchung("2024-01-08", [(k["giro"], -800), (k["leb"], 800)]),
    }
    api.patch(f"/api/buchungen/{b['gesperrt']['id']}", json={"status": "abgeglichen"}, erwartet=200)
    ids = {n: (b[n]["id"] if n in b else 999_999) for n in markiert}
    kid = k.get(ziel, 999_998)
    vorher = api.zustand()
    r = api.post(KAT_PFAD, json={"buchung_ids": sorted(ids.values()), "kategorie_id": kid})
    if "fremd" in markiert:
        erwartet = (422, "referenz_unbekannt", [999_999])
    elif ziel not in ("leb", "cafe", "geh"):
        erwartet = (422, "kategorie_ungueltig", None)
    elif "gesperrt" in markiert:
        erwartet = (409, "buchung_gesperrt", [ids["gesperrt"]])
    elif markiert & {"umbuchung", "split"}:
        erwartet = (422, "nicht_kategorisierbar", sorted(ids[n] for n in markiert & {"umbuchung", "split"}))
    else:
        erwartet = (200, None, None)
    assert r.status_code == erwartet[0], r.text
    if erwartet[0] != 200:
        assert fehlercode(r) == erwartet[1]
        if erwartet[2] is not None:
            assert sorted(r.json()["fehler"]["details"]["buchung_ids"]) == erwartet[2]
        assert api.zustand() == vorher
        return
    assert r.daten == {"geaendert": sorted(ids.values()), "anzahl": len(ids)}
    for n, bid in ids.items():
        assert api.buchung_lesen(bid)["kategorie_id"] == kid
    for n in set(b) - set(markiert):
        assert api.buchung_lesen(b[n]["id"]) == next(x for x in vorher["buchungen"] if x["id"] == b[n]["id"])
