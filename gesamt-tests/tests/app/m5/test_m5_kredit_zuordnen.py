"""M5: Ratenzahlungen erkennen und in Zins und Tilgung aufteilen (kredite.md 4.1, 4.3; E-103).

Erwartete Aufteilung aus dem Bruch-Orakel ``kredit_orakel.plan`` mit den gespeicherten Parametern.
"""

from __future__ import annotations

import pytest

from tests.hilfen import kredit_orakel as ko
from tests.hilfen.api import fehlercode
from tests.hilfen.m5 import (Kreditbuch, aenderungen_seit, bestand, eine_aenderung, kredit, letzte_aenderung_id,
                             pruefe_eintraege, rundreise)

pytestmark = pytest.mark.kern


def _plan(k: dict) -> dict[str, dict]:
    p = {f: k[f] for f in ("restschuld", "stand_datum", "sollzins", "zinsmethode", "rate", "erste_faelligkeit",
                           "sondertilgungen")}
    return {z["faelligkeit"]: z for z in ko.plan(p)["zeilen"]}


def _aufbau(api):
    kb = Kreditbuch(api)
    k = kb.anlegen(bedingungen=[{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktivbank AG"},
                                {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "darlehen 0815"}]).daten
    rate = k["rate"]
    b = {
        "feb": kb.zahlung("2024-02-01", rate, zweck="Rate Darlehen 0815"),
        "mar": kb.zahlung("2024-03-04", rate, zweck="RATE DARLEHEN 0815 03/24", status="bestaetigt"),
        "apr": kb.zahlung("2024-04-06", rate, zweck="Rate Darlehen 0815", gegen=api.konto("EK", "eigenkapital")["id"]),
        "mai_6_tage": kb.zahlung("2024-05-07", rate, zweck="Rate Darlehen 0815"),
        "jun_betrag": kb.zahlung("2024-06-01", rate - 1, zweck="Rate Darlehen 0815"),
        "jul_fremd": kb.zahlung("2024-07-01", rate, empfaenger=api.empfaenger("Möbelhaus Fiktiv")["id"],
                                zweck="Rate Darlehen 0815"),
        "aug_zweck": kb.zahlung("2024-08-01", rate, zweck="Rate Darlehen 4711"),
        "sep_ohne_empf": kb.zahlung("2024-09-02", rate, empfaenger=None, zweck="Rate Darlehen 0815"),
    }
    # drei Splits (nicht genau zwei) und Gegenbuchung auf einem Bestandskonto: nicht geprüft
    spar = api.konto("Sparkonto", "sparkonto")["id"]
    b["okt_drei_splits"] = api.buchung("2024-10-01", [(kb.giro, -rate), (kb.lebensmittel, rate - 10),
                                                      (kb.lebensmittel, 10)], empfaenger_id=kb.bank,
                                       verwendungszweck="Rate Darlehen 0815")
    b["nov_umbuchung"] = api.buchung("2024-11-01", [(kb.giro, -rate), (spar, rate)], empfaenger_id=kb.bank,
                                     verwendungszweck="Rate Darlehen 0815")
    return kb, k, b


def test_zuordnen_teilt_genau_die_passenden_raten(api):
    kb, k, b = _aufbau(api)
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    plan = _plan(k)
    soll = [(b["feb"]["id"], "2024-02-01"), (b["mar"]["id"], "2024-03-01"), (b["apr"]["id"], "2024-04-01")]
    assert r["trocken"] is False and r["anzahl"] == 3
    assert r["zuordnungen"] == [{"buchung_id": bid, "faelligkeit": f, "zins": plan[f]["zins"],
                                 "tilgung": plan[f]["tilgung"]} for bid, f in soll]
    # geprüft: alle Kandidaten mit genau zwei Splits, Abbuchung vom Zahlungskonto und passenden Bedingungen
    assert r["geprueft"] == 5, "feb, mar, apr, mai_6_tage, jun_betrag erfüllen Bedingungen und Splitform"
    for bid, f in soll:
        x = api.buchung_lesen(bid)
        assert x["status"] == "vorlaeufig" and x["vorschlag"] is None
        alt = vorher[("buchung", bid)]["splits"][0]
        assert x["splits"][0] == alt, "Split auf dem Zahlungskonto bleibt mit id, Betrag und Memo"
        assert [(s["konto_id"], s["betrag"], s["memo"]) for s in x["splits"][1:]] == [
            (kb.zinsen, plan[f]["zins"], "Zinsanteil"), (kb.darlehen, plan[f]["tilgung"], "Tilgungsanteil")]
        assert sum(s["betrag"] for s in x["splits"]) == 0
    for name in ("mai_6_tage", "jun_betrag", "jul_fremd", "aug_zweck", "sep_ohne_empf", "okt_drei_splits",
                 "nov_umbuchung"):
        assert ("buchung", b[name]["id"]) in vorher and bestand(api)[("buchung", b[name]["id"])] == vorher[
            ("buchung", b[name]["id"])], name
    assert kredit(api, k["id"])["zuordnungen"] == [{"faelligkeit": f, "buchung_id": bid} for bid, f in soll]
    a = eine_aenderung(api, a0, "kredit", "kredit_zuordnen")
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    rundreise(api, a, vorher, nachher)


def test_trocken_und_wiederholung(api):
    kb, k, b = _aufbau(api)
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    t = api.post(f"/api/kredite/{k['id']}/zuordnen", json={"trocken": True}, erwartet=200).daten
    assert bestand(api) == vorher and letzte_aenderung_id(api) == a0
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    assert {**t, "trocken": False} == r
    a1 = letzte_aenderung_id(api)
    z = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    assert (z["anzahl"], z["zuordnungen"], z["geprueft"]) == (0, [], 2), "zugeordnete Buchungen werden nicht geprüft"
    assert letzte_aenderung_id(api) == a1, "ohne Wirkung keine Änderung"


def test_buchung_ids_und_fehler(api):
    kb, k, b = _aufbau(api)
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={"buchung_ids": [b["mar"]["id"], b["jul_fremd"]["id"]]},
                 erwartet=200).daten
    assert [x["buchung_id"] for x in r["zuordnungen"]] == [b["mar"]["id"]] and r["geprueft"] == 1
    e = api.post(f"/api/kredite/{k['id']}/zuordnen", json={"buchung_ids": [999, 998]}, erwartet=422)
    assert fehlercode(e) == "referenz_unbekannt" and e.json()["fehler"]["details"]["buchung_ids"] == [998, 999]
    assert fehlercode(api.post(f"/api/kredite/{k['id']}/zuordnen", json={"buchung_ids": [1, 1]},
                               erwartet=422)) == "validierung"
    assert fehlercode(api.post("/api/kredite/999/zuordnen", json={}, erwartet=404)) == "nicht_gefunden"


def test_jede_faelligkeit_nur_einmal_und_naechste_gewinnt(api):
    kb = Kreditbuch(api)
    k = kb.anlegen().daten
    x = kb.zahlung("2024-01-30", k["rate"])   # 2 Tage vor 01.02.
    y = kb.zahlung("2024-02-03", k["rate"])   # 2 Tage nach 01.02., Fälligkeit schon vergeben
    z = kb.zahlung("2024-02-27", k["rate"])   # 3 Tage vor 01.03.
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    assert [(a["buchung_id"], a["faelligkeit"]) for a in r["zuordnungen"]] == [(x["id"], "2024-02-01"),
                                                                              (z["id"], "2024-03-01")]
    assert api.buchung_lesen(y["id"])["status"] == "importiert"


def test_gesperrte_buchung_wird_uebergangen(api):
    kb = Kreditbuch(api)
    k = kb.anlegen(saldo_angleichen=False).daten
    b = kb.zahlung("2024-02-01", k["rate"])
    api.post("/api/abstimmungen", json={"konto_id": kb.giro, "stichtag": "2024-02-01",
                                        "saldo": -k["rate"]}, erwartet=200)
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    assert (r["geprueft"], r["anzahl"]) == (0, 0) and api.buchung_lesen(b["id"])["status"] == "importiert"


def test_schlussrate_wird_erkannt(api):
    kb = Kreditbuch(api)
    k = kb.anlegen(restschuld=120_000, rate=50_000).daten
    plan = list(_plan(k).values())
    assert len(plan) == 3 and plan[-1]["rate"] < 50_000
    for z in plan:
        kb.zahlung(z["faelligkeit"], z["rate"])
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    assert [(a["faelligkeit"], a["zins"], a["tilgung"]) for a in r["zuordnungen"]] == [
        (z["faelligkeit"], z["zins"], z["tilgung"]) for z in plan]
    assert api.salden()[kb.darlehen]["saldo"] == 0, "nach allen Raten ist die gebuchte Restschuld 0"


def test_inaktiv_ohne_einfluss_auf_zuordnen(api):
    kb = Kreditbuch(api)
    k = kb.anlegen(aktiv=False).daten
    kb.zahlung("2024-02-01", k["rate"])
    assert api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten["anzahl"] == 1


def test_loeschen_einer_zugeordneten_buchung_entfernt_die_zuordnung(api):
    kb = Kreditbuch(api)
    k = kb.anlegen().daten
    b1, b2 = kb.zahlung("2024-02-01", k["rate"]), kb.zahlung("2024-03-01", k["rate"])
    api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200)
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    api.delete(f"/api/buchungen/{b1['id']}", erwartet=204)
    assert kredit(api, k["id"])["zuordnungen"] == [{"faelligkeit": "2024-03-01", "buchung_id": b2["id"]}]
    a = eine_aenderung(api, a0, "manuell", "buchung_loeschen")
    assert {(e["objekt"], e["objekt_id"]) for e in a["eintraege"]} == {("buchung", b1["id"]), ("kredit", k["id"])}
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    rundreise(api, a, vorher, nachher)
    # die frei gewordene Fälligkeit kann wieder zugeordnet werden
    neu = kb.zahlung("2024-02-02", k["rate"])
    r = api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200).daten
    assert [(x["buchung_id"], x["faelligkeit"]) for x in r["zuordnungen"]] == [(neu["id"], "2024-02-01")]
    assert len(aenderungen_seit(api, a0)) == 5
