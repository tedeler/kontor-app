"""M5: Kreditraten in der Synchronisation und Jahresabgleich mit Jahresauszügen (kredite.md 4.2, 5;
synchronisation.md 17; T 12).

Wahrheit aus ``fixtures/mock/m5_kredit.erwartung.json`` (Generator, Decimal-Rechnung je Zinsmethode).
"""

from __future__ import annotations

import pytest

from tests.hilfen.m3 import KORREKTUR, UNKATEGORISIERT, aenderungen_seit, konto_id, letzte_aenderung_id
from tests.hilfen.m5 import (KREDIT_MOCK, bestand, kredit, lade_kredit_sync, mock_api, nach_kennung,
                             pruefe_eintraege, saldo, sync)

DATEN, ERW = lade_kredit_sync()
HEUTE = ERW["abruf"]["bis"]


def _aufbau(tmp_path, methode: str, *, aktiv: bool = True, **felder):
    api = mock_api(tmp_path, KREDIT_MOCK, HEUTE, **felder)
    giro = api.konto("Girokonto", "girokonto", iban=ERW["iban"])["id"]
    darlehen = api.konto("Darlehen Fiktivbank 0815", "kreditkonto")["id"]
    zinsen = api.konto("Zinsen", "aufwand")["id"]
    kb = ERW["kredit"]
    body = {**{f: kb[f] for f in ("name", "restschuld", "stand_datum", "sollzins", "rate", "erste_faelligkeit",
                                  "sondertilgungen", "bedingungen")},
            "konto_id": darlehen, "zahlungskonto_id": giro, "zins_konto_id": zinsen, "zinsmethode": methode,
            "aktiv": aktiv}
    k = api.post("/api/kredite", json=body, erwartet=201).daten
    return api, k, {"giro": giro, "darlehen": darlehen, "zinsen": zinsen}


def _arten(art: str) -> list[str]:
    return [u for u, m in ERW["umsatz_art"].items() if m["art"] == art]


@pytest.mark.kern
@pytest.mark.parametrize("methode", ["30/360", "act/360", "act/365"])
def test_raten_werden_beim_abruf_aufgeteilt(tmp_path, methode):
    api, k, kt = _aufbau(tmp_path, methode)
    w = ERW["methoden"][methode]
    lauf = sync(api, von=ERW["abruf"]["von"], bis=ERW["abruf"]["bis"])
    (sk,) = lauf["konten"]
    raten = _arten("rate")
    assert sk["buchungen_kredit"] == len(raten) == 13
    assert sk["buchungen_kategorisiert"] == 0 and sk["buchungen_gesplittet"] == 0
    b = nach_kennung(api)
    unkat = konto_id(api, UNKATEGORISIERT)
    for uid in raten:
        a = w["aufteilung"][uid]
        x = b[uid]
        assert x["status"] == "vorlaeufig" and x["vorschlag"] is None, uid
        assert [(s["konto_id"], s["betrag"], s["memo"]) for s in x["splits"]] == [
            (kt["giro"], -ERW["kredit"]["rate"], ""), (kt["zinsen"], a["zins"], "Zinsanteil"),
            (kt["darlehen"], a["tilgung"], "Tilgungsanteil")], (uid, a)
    for art in ("sondertilgung", "fremd_gleicher_betrag", "gebuehr", "anderer_zweck", "sonstig"):
        for uid in _arten(art):
            x = b[uid]
            assert x["status"] == "importiert" and len(x["splits"]) == 2, (art, uid)
            assert x["splits"][1]["konto_id"] == unkat
    assert kredit(api, k["id"])["zuordnungen"] == sorted(
        ({"faelligkeit": w["aufteilung"][u]["faelligkeit"], "buchung_id": b[u]["id"]} for u in raten),
        key=lambda z: z["faelligkeit"])


@pytest.mark.kern
def test_inaktiver_kredit_wird_nicht_erkannt(tmp_path):
    api, k, kt = _aufbau(tmp_path, "30/360", aktiv=False)
    (sk,) = sync(api, von=ERW["abruf"]["von"], bis=ERW["abruf"]["bis"])["konten"]
    assert sk["buchungen_kredit"] == 0
    assert all(len(x["splits"]) == 2 for x in api.alle_buchungen(konto_id=kt["giro"]))
    assert kredit(api, k["id"])["zuordnungen"] == []


@pytest.mark.kern
def test_ohne_kredit_wie_bisher(tmp_path):
    api = mock_api(tmp_path, KREDIT_MOCK, HEUTE)
    (sk,) = sync(api, von=ERW["abruf"]["von"], bis=ERW["abruf"]["bis"])["konten"]
    assert sk["buchungen_kredit"] == 0 and sk["buchungen_neu"] == len(DATEN["bank"]["umsaetze"])


@pytest.mark.kern
def test_kredit_gehoert_zur_aenderung_sync_konto(tmp_path):
    api, k, kt = _aufbau(tmp_path, "act/360")
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    lauf = sync(api, von=ERW["abruf"]["von"], bis=ERW["abruf"]["bis"])
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("sync", "sync_konto", f"sync:{lauf['id']}")
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    assert ("kredit", k["id"]) in {(e["objekt"], e["objekt_id"]) for e in a["eintraege"]}
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"}, erwartet=200)
    assert bestand(api) == vorher, "Rückgängig des Laufs entfernt Buchungen und Zuordnungen"
    (sk,) = sync(api, von=ERW["abruf"]["von"], bis=ERW["abruf"]["bis"])["konten"]
    assert sk["buchungen_kredit"] == 13 and len(kredit(api, k["id"])["zuordnungen"]) == 13


def _sondertilgung_buchen(api, kt) -> None:
    (uid,) = _arten("sondertilgung")
    x = nach_kennung(api)[uid]
    api.put(f"/api/buchungen/{x['id']}/splits", json={"splits": [
        {"konto_id": kt["giro"], "betrag": -1_000_000}, {"konto_id": kt["darlehen"], "betrag": 1_000_000}]},
        erwartet=200)


FAELLE = [("30/360", v) for v in ("exakt", "zins_hoeher", "abweichend", "nur_restschuld", "nur_zinsen")] + [
    (m, "abweichend") for m in ("act/360", "act/365")] + [("act/365", "exakt")]


@pytest.mark.parametrize("methode,auszug", FAELLE)
def test_jahresabgleich_mit_jahresauszug(tmp_path, methode, auszug):
    api, k, kt = _aufbau(tmp_path, methode)
    sync(api, von=ERW["abruf"]["von"], bis=ERW["abruf"]["bis"])
    _sondertilgung_buchen(api, kt)
    w = ERW["methoden"][methode]
    a = w["jahresauszug_2024"][auszug]
    r = api.post(f"/api/kredite/{k['id']}/jahresabgleich",
                 json={"jahr": 2024, "restschuld": a["restschuld"], "zinsen": a["zinsen"]}, erwartet=200).daten
    assert (r["restschuld_berechnet"], r["zinsen_berechnet"], r["differenz_restschuld"], r["differenz_zinsen"]) == (
        a["restschuld_berechnet"], a["zinsen_berechnet"], a["differenz_restschuld"], a["differenz_zinsen"])
    konten = {"zins": kt["zinsen"], "darlehen": kt["darlehen"], "korrekturen": konto_id(api, KORREKTUR)}
    soll = [{"konto_id": konten[s["konto"]], "betrag": s["betrag"], "memo": s["memo"]} for s in a["korrektur"]]
    assert r["korrektur_splits"] == soll
    assert (r["korrektur_buchung"] is None) == (soll == [])
    b = nach_kennung(api)
    assert r["abgeglichen_buchung_ids"] == sorted(b[u]["id"] for u in w["raten_2024"])
    for u in w["raten_2024"]:
        assert b[u]["status"] == "abgeglichen"
    (jan,) = [u for u in _arten("rate") if u not in w["raten_2024"]]
    assert b[jan]["status"] == "vorlaeufig"
    assert -saldo(api, kt["darlehen"], "2024-12-31") == a["restschuld"]
