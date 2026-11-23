"""M5: Kredit anlegen, lesen, ändern, löschen; Anfangsbuchung; Bezüge (kredite.md 2, loeschen.md 7, E-101, E-110)."""

from __future__ import annotations

import pytest

from tests.hilfen import kredit_orakel as ko
from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import KORREKTUR, konto_id
from tests.hilfen.m5 import Kreditbuch, bestand, kredit, letzte_aenderung_id, saldo
from tests.hilfen.vertrag import pruefe_felder

FELDER = ["id", "name", "konto_id", "zahlungskonto_id", "zins_konto_id", "restschuld", "stand_datum", "sollzins",
          "zinsmethode", "rate", "erste_faelligkeit", "sondertilgungen", "bedingungen", "aktiv", "zuordnungen",
          "abgleiche"]


@pytest.mark.kern
def test_anlegen_mit_anfangsbuchung(api):
    kb = Kreditbuch(api)
    k = kb.anlegen(name="  Baufinanzierung  ").daten
    pruefe_felder(k, FELDER)  # E-124: genau diese Felder, spätere nur optional
    assert (k["name"], k["zinsmethode"], k["aktiv"], k["sondertilgungen"], k["zuordnungen"], k["abgleiche"]) == (
        "Baufinanzierung", "30/360", True, [], [], [])
    assert kredit(api, k["id"]) == k and api.get("/api/kredite", erwartet=200).daten == [k]
    # gebuchte Restschuld am stand_datum = restschuld (kredite.md 2.1)
    assert saldo(api, kb.darlehen, "2024-01-15") == -1_000_000
    korr = konto_id(api, KORREKTUR)
    assert korr is not None
    (b,) = api.alle_buchungen(konto_id=kb.darlehen)
    assert (b["datum"], b["empfaenger"], b["verwendungszweck"], b["status"]) == (
        "2024-01-15", None, "Anfangsbestand Baufinanzierung", "bestaetigt")
    assert [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]] == [(kb.darlehen, -1_000_000, ""),
                                                                            (korr, 1_000_000, "")]


@pytest.mark.kern
def test_anfangsbuchung_nur_ueber_die_differenz(api):
    kb = Kreditbuch(api)
    ek = api.konto("Eröffnung", "eigenkapital")["id"]
    api.buchung("2023-12-01", [(kb.darlehen, -400_000), (ek, 400_000)])
    api.buchung("2024-02-01", [(kb.darlehen, -5), (ek, 5)])  # nach dem Stichtag: zählt nicht
    kb.anlegen()
    assert saldo(api, kb.darlehen, "2024-01-15") == -1_000_000
    (neu,) = [b for b in api.alle_buchungen(konto_id=kb.darlehen) if b["datum"] == "2024-01-15"]
    assert neu["splits"][0]["betrag"] == -600_000


@pytest.mark.kern
def test_ohne_angleichen_und_bei_passendem_saldo_keine_buchung(api):
    kb = Kreditbuch(api)
    kb.anlegen(saldo_angleichen=False)
    assert api.alle_buchungen() == []
    k2 = Kreditbuch.__new__(Kreditbuch)
    k2.api, k2.giro, k2.zinsen, k2.bank = api, kb.giro, kb.zinsen, kb.bank
    k2.darlehen = api.konto("Zweites Darlehen", "kreditkonto")["id"]
    ek = api.konto("EK", "eigenkapital")["id"]
    api.buchung("2024-01-10", [(k2.darlehen, -1_000_000), (ek, 1_000_000)])
    n = len(api.alle_buchungen())
    k2.anlegen()
    assert len(api.alle_buchungen()) == n, "Saldo stimmt schon: keine Anfangsbuchung"


def test_sondertilgungen_sortiert_stabil(api):
    kb = Kreditbuch(api)
    st = [{"datum": "2024-09-01", "betrag": 3}, {"datum": "2024-05-01", "betrag": 2},
          {"datum": "2024-09-01", "betrag": 1}]
    k = kb.anlegen(sondertilgungen=st).daten
    assert k["sondertilgungen"] == [st[1], st[0], st[2]]


@pytest.mark.kern
@pytest.mark.parametrize("fall", ["validierung_datum", "validierung_sonder", "referenz", "konto_kein_kredit",
                                  "zahlung_kategorie", "zahlung_gleich", "zins_ertrag", "belegt", "rate_zu_klein",
                                  "validierung_float", "validierung_feld"])
def test_fehler_in_pruefreihenfolge(api, fall):
    kb = Kreditbuch(api)
    ertrag = api.konto("Gehalt", "ertrag")["id"]
    anderes = api.konto("Anderes Darlehen", "kreditkonto")["id"]
    if fall == "belegt":
        vorh = api.post("/api/kredite", json=kb.body(konto_id=anderes), erwartet=201).daten
    faelle = {
        "validierung_datum": ({"erste_faelligkeit": "2024-01-15", "konto_id": 999}, 422, "validierung"),
        "validierung_sonder": ({"sondertilgungen": [{"datum": "2024-01-15", "betrag": 1}]}, 422, "validierung"),
        "validierung_float": ({"sollzins": 3.5}, 422, "validierung"),
        "validierung_feld": ({"zuordnungen": []}, 422, "validierung"),
        "referenz": ({"konto_id": 998, "zins_konto_id": 997, "zahlungskonto_id": kb.lebensmittel}, 422,
                     "referenz_unbekannt"),
        "konto_kein_kredit": ({"konto_id": kb.giro, "zins_konto_id": ertrag}, 422, "konto_ungueltig"),
        "zahlung_kategorie": ({"zahlungskonto_id": kb.lebensmittel}, 422, "konto_ungueltig"),
        "zahlung_gleich": ({"zahlungskonto_id": kb.darlehen}, 422, "konto_ungueltig"),
        "zins_ertrag": ({"zins_konto_id": ertrag, "konto_id": anderes}, 422, "kategorie_ungueltig"),
        "belegt": ({"konto_id": anderes, "rate": 1}, 409, "kredit_konto_belegt"),
        "rate_zu_klein": ({"rate": 3_000}, 422, "kredit_rate_zu_klein"),
    }
    felder, status, code = faelle[fall]
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    r = api.post("/api/kredite", json=kb.body(**felder), erwartet=status)
    assert fehlercode(r) == code
    if fall == "referenz":
        assert r.json()["fehler"]["details"]["konto_ids"] == [997, 998]
    if fall == "belegt":
        assert r.json()["fehler"]["details"]["kredit_id"] == vorh["id"]
    assert bestand(api) == vorher and letzte_aenderung_id(api) == a0, "Fehler darf nichts ändern"


@pytest.mark.kern
def test_plan_des_kredits_gleich_orakel(api):
    kb = Kreditbuch(api)
    k = kb.anlegen(zinsmethode="act/365", sondertilgungen=[{"datum": "2024-04-10", "betrag": 100_000}]).daten
    plan = api.get(f"/api/kredite/{k['id']}/plan", erwartet=200).daten
    p = {f: k[f] for f in ("restschuld", "stand_datum", "sollzins", "zinsmethode", "rate", "erste_faelligkeit")}
    p["sondertilgungen"] = [{"datum": s["datum"], "betrag": s["betrag"]} for s in k["sondertilgungen"]]  # E-124
    assert plan == ko.plan(p) == api.post("/api/kredite/tilgungsplan", json=p, erwartet=200).daten
    assert api.get("/api/kredite/999/plan", erwartet=404).json()["fehler"]["code"] == "nicht_gefunden"


@pytest.mark.kern
def test_aendern_und_loeschen(api):
    kb = Kreditbuch(api)
    k = kb.anlegen().daten
    n = len(api.alle_buchungen())
    neu = api.patch(f"/api/kredite/{k['id']}", json={"rate": 60_000, "aktiv": False, "zinsmethode": "act/360",
                                                     "sondertilgungen": [{"datum": "2024-06-01", "betrag": 7}]},
                    erwartet=200).daten
    assert (neu["rate"], neu["aktiv"], neu["zinsmethode"], neu["sondertilgungen"]) == (
        60_000, False, "act/360", [{"datum": "2024-06-01", "betrag": 7}])
    assert {f: neu[f] for f in FELDER if f not in ("rate", "aktiv", "zinsmethode", "sondertilgungen")} == {
        f: k[f] for f in FELDER if f not in ("rate", "aktiv", "zinsmethode", "sondertilgungen")}
    assert len(api.alle_buchungen()) == n, "PATCH erzeugt keine Buchung"
    for body, code in (({"konto_id": kb.giro}, "validierung"), ({"rate": 100}, "kredit_rate_zu_klein"),
                       ({"zahlungskonto_id": 999}, "referenz_unbekannt"), ({"zins_konto_id": kb.giro},
                                                                         "kategorie_ungueltig"),
                       ({"erste_faelligkeit": "2023-01-01"}, "validierung"), ({"abgleiche": []}, "validierung")):
        assert fehlercode(api.patch(f"/api/kredite/{k['id']}", json=body, erwartet=422)) == code, body
    assert kredit(api, k["id"]) == neu
    assert fehlercode(api.patch("/api/kredite/999", json={"rate": 1}, erwartet=404)) == "nicht_gefunden"
    api.delete(f"/api/kredite/{k['id']}", erwartet=204)
    api.delete(f"/api/kredite/{k['id']}", erwartet=404)
    api.get(f"/api/kredite/{k['id']}", erwartet=404)
    assert api.get("/api/kredite", erwartet=200).daten == [] and len(api.alle_buchungen()) == n


@pytest.mark.kern
@pytest.mark.parametrize("welches", ["darlehen", "giro", "zinsen"])
def test_konto_mit_kreditbezug_nicht_loeschbar(api, welches):
    kb = Kreditbuch(api)
    k = kb.anlegen(saldo_angleichen=False).daten
    kid = getattr(kb, welches)
    vorher = bestand(api)
    r = api.delete(f"/api/konten/{kid}", erwartet=409)
    assert fehlercode(r) == "konto_in_verwendung"
    assert r.json()["fehler"]["details"]["kredit_ids"] == [k["id"]]
    for trocken in (True, False):
        r = api.post(f"/api/konten/{kid}/loeschen", json={"buchungen": "loeschen", "konflikte": "loeschen",
                                                         "trocken": trocken}, erwartet=409)
        assert fehlercode(r) == "konto_in_verwendung" and r.json()["fehler"]["details"]["kredit_ids"] == [k["id"]]
    assert bestand(api) == vorher
    api.delete(f"/api/kredite/{k['id']}", erwartet=204)
    api.delete(f"/api/konten/{kid}", erwartet=204)
