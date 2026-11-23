"""M5: Jahresabgleich mit genau einer Korrekturbuchung (kredite.md 5; T 12; E-105).

Erwartungen aus dem Bruch-Orakel (gebuchte Raten nach Plan) und aus den eingegebenen Auszugswerten.
"""

from __future__ import annotations

import pytest

from tests.hilfen import kredit_orakel as ko
from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import KORREKTUR, konto_id
from tests.hilfen.m5 import (Kreditbuch, bestand, eine_aenderung, kredit, letzte_aenderung_id, pruefe_eintraege,
                             rundreise, saldo)

pytestmark = pytest.mark.kern


def _aufbau(api, *, angleichen: bool = True):
    kb = Kreditbuch(api)
    if not angleichen:
        ek = api.konto("Eröffnung", "eigenkapital")["id"]
        api.buchung("2024-01-15", [(kb.darlehen, -1_000_000), (ek, 1_000_000)])
    k = kb.anlegen(saldo_angleichen=angleichen).daten
    p = {f: k[f] for f in ("restschuld", "stand_datum", "sollzins", "zinsmethode", "rate", "erste_faelligkeit",
                           "sondertilgungen")}
    plan = ko.plan(p)["zeilen"]
    raten = {}
    for z in plan[:12]:          # Februar 2024 bis Januar 2025
        raten[z["faelligkeit"]] = kb.zahlung(z["faelligkeit"], z["rate"])["id"]
    api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200)
    im_jahr = [z for z in plan[:12] if z["faelligkeit"] <= "2024-12-31"]
    soll = {"zinsen": sum(z["zins"] for z in im_jahr), "restschuld": im_jahr[-1]["restschuld_nachher"],
            "ids": sorted(raten[z["faelligkeit"]] for z in im_jahr), "jan": raten[plan[11]["faelligkeit"]]}
    return kb, k, soll


def _zinsen_des_kredits(api, k, jahr: int) -> int:
    k = kredit(api, k["id"])
    ids = {z["buchung_id"] for z in k["zuordnungen"]} | {a["buchung_id"] for a in k["abgleiche"] if a["buchung_id"]}
    return sum(s["betrag"] for b in api.alle_buchungen() if b["id"] in ids and b["datum"].startswith(f"{jahr}-")
               for s in b["splits"] if s["konto_id"] == k["zins_konto_id"])


@pytest.mark.parametrize("dz,dr", [(0, 0), (123, 123), (50, -200), (0, 1), (-7, 0), (0, -1_000)])
def test_abgleich(api, dz, dr):
    kb, k, soll = _aufbau(api)
    korr = konto_id(api, KORREKTUR)
    body = {"jahr": 2024, "restschuld": soll["restschuld"] + dr, "zinsen": soll["zinsen"] + dz}
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    t = api.post(f"/api/kredite/{k['id']}/jahresabgleich", json={**body, "trocken": True}, erwartet=200).daten
    assert bestand(api) == vorher and letzte_aenderung_id(api) == a0, "Probelauf ändert nichts"
    r = api.post(f"/api/kredite/{k['id']}/jahresabgleich", json=body, erwartet=200).daten
    erw_splits = ([{"konto_id": kb.zinsen, "betrag": dz, "memo": "Zinskorrektur"}] if dz else []) + (
        [{"konto_id": kb.darlehen, "betrag": -dr, "memo": "Restschuldkorrektur"}] if dr else []) + (
        [{"konto_id": korr, "betrag": dr - dz, "memo": ""}] if dr != dz else [])
    assert {f: r[f] for f in ("kredit_id", "jahr", "trocken", "restschuld", "zinsen", "restschuld_berechnet",
                              "zinsen_berechnet", "differenz_restschuld", "differenz_zinsen", "korrektur_splits",
                              "abgeglichen_buchung_ids")} == {
        "kredit_id": k["id"], "jahr": 2024, "trocken": False, "restschuld": body["restschuld"],
        "zinsen": body["zinsen"], "restschuld_berechnet": soll["restschuld"], "zinsen_berechnet": soll["zinsen"],
        "differenz_restschuld": dr, "differenz_zinsen": dz, "korrektur_splits": erw_splits,
        "abgeglichen_buchung_ids": soll["ids"]}
    assert {**t, "trocken": False, "korrektur_buchung": r["korrektur_buchung"]} == r and t["korrektur_buchung"] is None
    neue = [b for b in api.alle_buchungen() if ("buchung", b["id"]) not in vorher]
    if dz == dr == 0:
        assert neue == [] and r["korrektur_buchung"] is None, "ohne Abweichung keine Korrekturbuchung"
    else:
        (kb_neu,) = neue          # genau eine Korrekturbuchung (T 12)
        assert r["korrektur_buchung"] == kb_neu
        assert (kb_neu["datum"], kb_neu["status"], kb_neu["empfaenger"], kb_neu["verwendungszweck"]) == (
            "2024-12-31", "abgeglichen", None, "Jahresabgleich 2024 Baufinanzierung")
        assert [{"konto_id": s["konto_id"], "betrag": s["betrag"], "memo": s["memo"]} for s in kb_neu["splits"]] == \
            erw_splits
    # danach stimmen Restschuld und Zinssumme mit dem Auszug überein (T 12)
    assert -saldo(api, kb.darlehen, "2024-12-31") == body["restschuld"]
    assert _zinsen_des_kredits(api, k, 2024) == body["zinsen"]
    for bid in soll["ids"]:
        assert api.buchung_lesen(bid)["status"] == "abgeglichen"
    assert api.buchung_lesen(soll["jan"])["status"] == "vorlaeufig", "Rate des Folgejahres bleibt vorläufig"
    assert kredit(api, k["id"])["abgleiche"] == [{"jahr": 2024, "restschuld": body["restschuld"],
                                                  "zinsen": body["zinsen"],
                                                  "buchung_id": r["korrektur_buchung"]["id"] if neue else None}]
    a = eine_aenderung(api, a0, "manuell", "kredit_jahresabgleich")
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    # abgeglichene Buchungen sind gesperrt
    assert fehlercode(api.delete(f"/api/buchungen/{soll['ids'][0]}", erwartet=409)) == "buchung_gesperrt"
    # genau ein Abgleich je Jahr
    assert fehlercode(api.post(f"/api/kredite/{k['id']}/jahresabgleich", json=body,
                               erwartet=409)) == "kredit_jahr_abgeglichen"
    rundreise(api, a, vorher, nachher)


def test_korrekturen_konto_wird_bei_bedarf_angelegt(api):
    kb, k, soll = _aufbau(api, angleichen=False)
    assert konto_id(api, KORREKTUR) is None
    body = {"jahr": 2024, "restschuld": soll["restschuld"] + 5, "zinsen": soll["zinsen"]}
    t = api.post(f"/api/kredite/{k['id']}/jahresabgleich", json={**body, "trocken": True}, erwartet=200).daten
    assert t["korrektur_splits"] == [{"konto_id": kb.darlehen, "betrag": -5, "memo": "Restschuldkorrektur"},
                                     {"konto_id": None, "betrag": 5, "memo": ""}], "Probelauf legt nichts an"
    assert konto_id(api, KORREKTUR) is None
    r = api.post(f"/api/kredite/{k['id']}/jahresabgleich", json=body, erwartet=200).daten
    korr = konto_id(api, KORREKTUR)
    assert korr is not None
    assert r["korrektur_splits"] == [{"konto_id": kb.darlehen, "betrag": -5, "memo": "Restschuldkorrektur"},
                                     {"konto_id": korr, "betrag": 5, "memo": ""}]


def test_abgleich_ohne_raten_im_jahr(api):
    kb = Kreditbuch(api)
    k = kb.anlegen().daten
    r = api.post(f"/api/kredite/{k['id']}/jahresabgleich", json={"jahr": 2023, "restschuld": 0, "zinsen": 0},
                 erwartet=200).daten
    assert (r["restschuld_berechnet"], r["zinsen_berechnet"], r["abgeglichen_buchung_ids"]) == (0, 0, [])
    assert r["korrektur_buchung"] is None
    r = api.post(f"/api/kredite/{k['id']}/jahresabgleich", json={"jahr": 2024, "restschuld": 1_000_000,
                                                                 "zinsen": 0}, erwartet=200).daten
    assert r["korrektur_splits"] == [] and kredit(api, k["id"])["abgleiche"][1]["jahr"] == 2024


@pytest.mark.parametrize("body", [{"jahr": 1899, "restschuld": 0, "zinsen": 0},
                                  {"jahr": 2024, "restschuld": -1, "zinsen": 0},
                                  {"jahr": 2024, "restschuld": 0, "zinsen": 1.5},
                                  {"jahr": 2024, "restschuld": 0}, {"jahr": "2024", "restschuld": 0, "zinsen": 0},
                                  {"jahr": 2024, "restschuld": 0, "zinsen": 0, "x": 1}])
def test_abgleich_validierung(api, body):
    kb = Kreditbuch(api)
    k = kb.anlegen().daten
    vorher = bestand(api)
    assert fehlercode(api.post(f"/api/kredite/{k['id']}/jahresabgleich", json=body, erwartet=422)) == "validierung"
    assert bestand(api) == vorher
    assert fehlercode(api.post("/api/kredite/999/jahresabgleich", json={"jahr": 2024, "restschuld": 0, "zinsen": 0},
                               erwartet=404)) == "nicht_gefunden"


def test_korrekturbuchung_loeschen_nur_durch_rueckgaengig(api):
    kb, k, soll = _aufbau(api)
    r = api.post(f"/api/kredite/{k['id']}/jahresabgleich",
                 json={"jahr": 2024, "restschuld": soll["restschuld"] + 10, "zinsen": soll["zinsen"] + 10},
                 erwartet=200).daten
    assert fehlercode(api.delete(f"/api/buchungen/{r['korrektur_buchung']['id']}", erwartet=409)) == "buchung_gesperrt"
