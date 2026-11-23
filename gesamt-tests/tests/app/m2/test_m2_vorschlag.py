"""M2: Kategorisierung neuer Buchungen beim Abruf und Vorschläge bis zur Bestätigung (kategorisierung.md 5; K 7, T 8).

Erwartung je Umsatz: ``regel_ergebnis`` der bekannten Wahrheit des Generators
(in ``tests/generator/test_sync_daten.py`` gegen ein Orakel geprüft).
"""

from __future__ import annotations

import pytest

from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import gegensplit, lade_sync, mock_api, nach_kennung, regeln_anlegen, sync, unkategorisiert

VON = "2024-01-01"


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def rapi(tmp_path):
    api = mock_api(tmp_path)
    ids = regeln_anlegen(api)
    sync(api, von=VON)
    return api, ids


def _bestand(api) -> set[int]:
    return {k["id"] for k in api.konten() if k["art"] in ("girokonto", "sparkonto", "kreditkonto")}


@pytest.mark.kern
def test_abruf_kategorisiert_nach_regeln(rapi, sd, netz_gesperrt):
    api, ids = rapi
    daten, erw = sd
    unk = unkategorisiert(api)
    assert unk is not None
    bank = nach_kennung(api.alle_buchungen())
    bestand = _bestand(api)
    for u in daten["bank"]["umsaetze"]:
        if u["vormerkung"]:
            continue
        b = bank[orakel.kennung(u)]
        soll = erw["regel_ergebnis"][u["umsatz_id"]]
        gs = gegensplit(b, bestand)
        if soll is None:
            assert gs["konto_id"] == unk["id"] and b["kategorie_id"] is None and b["vorschlag"] is None, u
        else:
            kat = ids["kategorien"][soll["kategorie"]]
            assert gs["konto_id"] == kat and b["kategorie_id"] == kat, u
            assert b["vorschlag"] == {"kategorie_id": kat, "regel_id": ids["regeln"][soll["regel"]]["id"],
                                      "quelle": "regel", "vorher_konto_id": unk["id"]}, u
        assert b["status"] == "importiert" and gs["betrag"] == -u["betrag"] and gs["memo"] == ""


def test_zaehlung_kategorisiert(tmp_path, sd, netz_gesperrt):
    daten, erw = sd
    api = mock_api(tmp_path)
    ids = regeln_anlegen(api)
    lauf = sync(api, von=VON)
    for sk in lauf["konten"]:
        n = sum(1 for u in daten["bank"]["umsaetze"] if u["iban"] == sk["iban"] and not u["vormerkung"]
                and erw["regel_ergebnis"][u["umsatz_id"]])
        assert sk["buchungen_kategorisiert"] == n and sk["konto_neu"] is False
        assert sk["konto_id"] == ids["konten"][sk["iban"]]


def test_filter_vorschlag(rapi, sd, netz_gesperrt):
    api, ids = rapi
    alle = api.alle_buchungen()
    mit = api.alle_buchungen(vorschlag=True)
    ohne = api.alle_buchungen(vorschlag=False)
    assert [b["id"] for b in mit] == [b["id"] for b in alle if b["vorschlag"]]
    assert [b["id"] for b in ohne] == [b["id"] for b in alle if not b["vorschlag"]]
    giro = ids["konten"][sd[1]["ibans"]["giro"]]
    kombiniert = api.alle_buchungen(vorschlag=True, konto_id=giro)
    assert [b["id"] for b in kombiniert] == [b["id"] for b in mit if any(s["konto_id"] == giro for s in b["splits"])]
    assert mit and ohne


def _eine_mit_vorschlag(api, n: int = 0) -> dict:
    return api.alle_buchungen(vorschlag=True)[n]


@pytest.mark.kern
def test_annehmen(rapi, netz_gesperrt):
    api, _ = rapi
    b = _eine_mit_vorschlag(api)
    neu = api.post(f"/api/buchungen/{b['id']}/vorschlag", json={"aktion": "annehmen"}, erwartet=200).daten
    assert neu == {**b, "vorschlag": None}
    assert api.buchung_lesen(b["id"]) == neu
    r = api.post(f"/api/buchungen/{b['id']}/vorschlag", json={"aktion": "annehmen"}, erwartet=409)
    assert fehlercode(r) == "kein_vorschlag"


@pytest.mark.kern
def test_ablehnen(rapi, netz_gesperrt):
    api, _ = rapi
    b = _eine_mit_vorschlag(api)
    bestand = _bestand(api)
    neu = api.post(f"/api/buchungen/{b['id']}/vorschlag", json={"aktion": "ablehnen"}, erwartet=200).daten
    gs_alt, gs_neu = gegensplit(b, bestand), gegensplit(neu, bestand)
    assert gs_neu == {**gs_alt, "konto_id": b["vorschlag"]["vorher_konto_id"]}
    assert neu["kategorie_id"] is None and neu["vorschlag"] is None and neu["status"] == b["status"]
    assert [s for s in neu["splits"] if s["konto_id"] in bestand] == [s for s in b["splits"] if s["konto_id"] in bestand]
    assert fehlercode(api.post(f"/api/buchungen/{b['id']}/vorschlag", json={"aktion": "ablehnen"},
                               erwartet=409)) == "kein_vorschlag"


def test_vorschlag_fehler(rapi, netz_gesperrt):
    api, _ = rapi
    b = _eine_mit_vorschlag(api)
    for koerper in ({}, {"aktion": "bestaetigen"}, {"aktion": "annehmen", "x": 1}):
        assert fehlercode(api.post(f"/api/buchungen/{b['id']}/vorschlag", json=koerper, erwartet=422)) == "validierung"
    assert fehlercode(api.post("/api/buchungen/999999/vorschlag", json={"aktion": "annehmen"},
                               erwartet=404)) == "nicht_gefunden"
    assert api.buchung_lesen(b["id"]) == b


@pytest.mark.kern
def test_mehrfach_atomar(rapi, netz_gesperrt):
    api, _ = rapi
    mit = api.alle_buchungen(vorschlag=True)[:3]
    ohne = api.alle_buchungen(vorschlag=False)[0]
    vorher = api.zustand()
    ids = sorted([b["id"] for b in mit] + [ohne["id"]])
    r = api.post("/api/buchungen/mehrfach/vorschlag", json={"buchung_ids": ids, "aktion": "annehmen"}, erwartet=409)
    assert fehlercode(r) == "kein_vorschlag" and r.json()["fehler"]["details"]["buchung_ids"] == [ohne["id"]]
    r = api.post("/api/buchungen/mehrfach/vorschlag", json={"buchung_ids": ids + [999999], "aktion": "annehmen"},
                 erwartet=422)
    assert fehlercode(r) == "referenz_unbekannt" and r.json()["fehler"]["details"]["buchung_ids"] == [999999]
    for koerper in ({"buchung_ids": [], "aktion": "annehmen"}, {"buchung_ids": [ids[0], ids[0]], "aktion": "annehmen"},
                    {"buchung_ids": ids, "aktion": "egal"}):
        assert fehlercode(api.post("/api/buchungen/mehrfach/vorschlag", json=koerper, erwartet=422)) == "validierung"
    assert api.zustand() == vorher
    ziel = sorted(b["id"] for b in mit)
    erg = api.post("/api/buchungen/mehrfach/vorschlag", json={"buchung_ids": list(reversed(ziel)),
                                                              "aktion": "ablehnen"}, erwartet=200).daten
    assert erg == {"geaendert": ziel, "anzahl": 3}
    unk = unkategorisiert(api)["id"]
    for b in mit:
        neu = api.buchung_lesen(b["id"])
        assert neu["vorschlag"] is None and gegensplit(neu, _bestand(api))["konto_id"] == unk


@pytest.mark.kern
@pytest.mark.parametrize("aktion", ["kategorie", "mehrfach_kategorie", "splits", "status_bestaetigt"])
def test_manuelle_entscheidung_erledigt_vorschlag(rapi, aktion, netz_gesperrt):
    api, ids = rapi
    b = _eine_mit_vorschlag(api)
    sonst = ids["kategorien"]["Sonstiges"]
    if aktion == "kategorie":
        api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": sonst}, erwartet=200)
        soll_kat = sonst
    elif aktion == "mehrfach_kategorie":
        api.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [b["id"]], "kategorie_id": sonst},
                 erwartet=200)
        soll_kat = sonst
    elif aktion == "splits":
        splits = [{"konto_id": s["konto_id"], "betrag": s["betrag"], "memo": "neu"} for s in b["splits"]]
        api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": splits}, erwartet=200)
        soll_kat = b["kategorie_id"]
    else:
        api.patch(f"/api/buchungen/{b['id']}", json={"status": "bestaetigt"}, erwartet=200)
        soll_kat = b["kategorie_id"]
    neu = api.buchung_lesen(b["id"])
    assert neu["vorschlag"] is None and neu["kategorie_id"] == soll_kat


def test_kategorie_setzen_auf_gleiche_kategorie_bestaetigt(rapi, netz_gesperrt):
    api, _ = rapi
    b = _eine_mit_vorschlag(api)
    api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": b["kategorie_id"]}, erwartet=200)
    assert api.buchung_lesen(b["id"])["vorschlag"] is None


@pytest.mark.parametrize("feld", ["tag_ids", "verwendungszweck", "datum", "empfaenger_id"])
def test_andere_aenderungen_lassen_vorschlag(rapi, feld, netz_gesperrt):
    api, _ = rapi
    b = _eine_mit_vorschlag(api)
    wert = {"tag_ids": [api.tag("Prüfen")["id"]], "verwendungszweck": "geändert", "datum": "2024-12-24",
            "empfaenger_id": None}[feld]
    neu = api.patch(f"/api/buchungen/{b['id']}", json={feld: wert}, erwartet=200).daten
    assert neu["vorschlag"] == b["vorschlag"] and neu["kategorie_id"] == b["kategorie_id"]


def test_regel_loeschen(rapi, sd, netz_gesperrt):
    api, ids = rapi
    r = ids["regeln"]["Supermarkt"]
    betroffen = [b for b in api.alle_buchungen(vorschlag=True) if b["vorschlag"]["regel_id"] == r["id"]]
    assert betroffen
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    for b in betroffen:
        neu = api.buchung_lesen(b["id"])
        assert neu["vorschlag"] == {**b["vorschlag"], "regel_id": None} and neu["kategorie_id"] == b["kategorie_id"]


def test_ablehnen_wenn_vorher_konto_fehlt(api, netz_gesperrt):
    """Existiert vorher_konto_id nicht mehr, geht der Gegensplit auf „Unkategorisiert“ (ggf. neu angelegt)."""
    g = api.konto("Giro")
    offen = api.konto("Offen", "eigenkapital")
    kat = api.konto("Café", "aufwand")
    b = api.buchung("2024-03-01", [(g["id"], -300), (offen["id"], 300)], verwendungszweck="Kaffee")
    api.post("/api/regeln", json={"name": "K", "kategorie_id": kat["id"], "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "kaffee"}]}, erwartet=201)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    api.delete(f"/api/konten/{offen['id']}", erwartet=204)
    neu = api.post(f"/api/buchungen/{b['id']}/vorschlag", json={"aktion": "ablehnen"}, erwartet=200).daten
    unk = unkategorisiert(api)
    assert unk and unk["art"] == "eigenkapital" and unk["name"] == "Unkategorisiert"
    assert neu["splits"][1]["konto_id"] == unk["id"] and neu["vorschlag"] is None


@pytest.mark.kern
def test_invariante_vorschlag(rapi, netz_gesperrt):
    api, _ = rapi
    b0, b1 = _eine_mit_vorschlag(api, 0), _eine_mit_vorschlag(api, 1)
    api.post(f"/api/buchungen/{b0['id']}/vorschlag", json={"aktion": "ablehnen"}, erwartet=200)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)  # setzt den abgelehnten Vorschlag wieder
    assert api.buchung_lesen(b0["id"])["vorschlag"] == b0["vorschlag"]
    api.post(f"/api/buchungen/{b1['id']}/vorschlag", json={"aktion": "annehmen"}, erwartet=200)
    for b in api.alle_buchungen():
        if b["vorschlag"] is not None:
            assert b["kategorie_id"] == b["vorschlag"]["kategorie_id"]
        assert sum(s["betrag"] for s in b["splits"]) == 0
    assert api.uebersicht()["summe_gesamt"] == 0
