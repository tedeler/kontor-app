"""M5: Änderungsprotokoll und Rückgängig für Kredite (protokoll.md 11; T 3.5, T 3.6; E-101, E-110).

Erwartete Einträge aus den Lese-Endpunkten (``tests/hilfen/m5.bestand`` inkl. Kredite), nie aus dem Protokoll.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m5 import (Kreditbuch, aenderungen_seit, bestand, eine_aenderung, letzte_aenderung_id,
                             pruefe_eintraege, rundreise)

pytestmark = pytest.mark.kern


def test_kredit_anlegen_aendern_loeschen(api):
    kb = Kreditbuch(api)
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    k = kb.anlegen().daten
    a = eine_aenderung(api, a0, "manuell", "kredit_anlegen")
    nachher = bestand(api)
    arten = {(e["objekt"], e["art"]) for e in a["eintraege"]}
    assert arten == {("konto", "angelegt"), ("buchung", "angelegt"), ("kredit", "angelegt")}, \
        "Kredit, Anfangsbuchung und Konto „Korrekturen“ in einer Änderung"
    pruefe_eintraege(a, vorher, nachher)
    rundreise(api, a, vorher, nachher)

    vorher, a0 = nachher, letzte_aenderung_id(api)
    api.patch(f"/api/kredite/{k['id']}", json={"sollzins": 40_000, "name": "Neu"}, erwartet=200)
    a = eine_aenderung(api, a0, "manuell", "kredit_aendern")
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    rundreise(api, a, vorher, nachher)
    a1 = letzte_aenderung_id(api)
    api.patch(f"/api/kredite/{k['id']}", json={"sollzins": 40_000}, erwartet=200)
    assert letzte_aenderung_id(api) == a1, "PATCH ohne Wirkung erzeugt keine Änderung"

    vorher, a0 = nachher, letzte_aenderung_id(api)
    api.delete(f"/api/kredite/{k['id']}", erwartet=204)
    a = eine_aenderung(api, a0, "manuell", "kredit_loeschen")
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    rundreise(api, a, vorher, nachher)


def test_fehler_erzeugen_keine_aenderung(api):
    kb = Kreditbuch(api)
    a0 = letzte_aenderung_id(api)
    kb.anlegen(erwartet=422, rate=1)
    api.post("/api/kredite/tilgungsplan", json={"restschuld": 100, "stand_datum": "2024-01-01", "sollzins": 0,
                                                "rate": 10, "erste_faelligkeit": "2024-02-01"}, erwartet=200)
    assert letzte_aenderung_id(api) == a0


def test_bezugspruefung_beim_rueckgaengig(api):
    """Rückgängig, das einen Kredit ohne Konto hinterließe, scheitert (protokoll.md 11.1)."""
    a0 = letzte_aenderung_id(api)
    kb = Kreditbuch(api)
    (darlehen_anlegen,) = [a for a in aenderungen_seit(api, a0) if a["aktion"] == "konto_anlegen"
                           and a["eintraege"][0]["objekt_id"] == kb.darlehen]
    k = kb.anlegen(saldo_angleichen=False).daten
    vorher = bestand(api)
    r = api.post(f"/api/aenderungen/{darlehen_anlegen['id']}/rueckgaengig", erwartet=409)
    assert fehlercode(r) == "rueckgaengig_konflikt" and bestand(api) == vorher
    # Eindeutigkeit der konto_id über alle Kredite
    a1 = letzte_aenderung_id(api)
    api.delete(f"/api/kredite/{k['id']}", erwartet=204)
    (weg,) = aenderungen_seit(api, a1)
    kb.anlegen(saldo_angleichen=False)
    vorher = bestand(api)
    assert fehlercode(api.post(f"/api/aenderungen/{weg['id']}/rueckgaengig", erwartet=409)) == "rueckgaengig_konflikt"
    assert bestand(api) == vorher


def test_zustandspruefung_nach_zuordnung(api):
    kb = Kreditbuch(api)
    a0 = letzte_aenderung_id(api)
    k = kb.anlegen().daten
    (anlegen,) = aenderungen_seit(api, a0)
    kb.zahlung("2024-02-01", k["rate"])
    api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200)
    assert fehlercode(api.post(f"/api/aenderungen/{anlegen['id']}/rueckgaengig",
                               erwartet=409)) == "rueckgaengig_konflikt", "der Kredit wurde später geändert"


def test_folge_in_umgekehrter_reihenfolge_rueckgaengig(api):
    """T 3.6: jede Operation der Folge lässt sich in umgekehrter Reihenfolge exakt zurücknehmen."""
    kb = Kreditbuch(api)
    zustaende, ids = [bestand(api)], []

    def schritt(f):
        a0 = letzte_aenderung_id(api)
        f()
        neu = aenderungen_seit(api, a0)
        assert len(neu) == 1, [x["aktion"] for x in neu]
        ids.append(neu[0]["id"])
        zustaende.append(bestand(api))

    k = {}
    schritt(lambda: k.update(kb.anlegen().daten))
    raten = []
    for t in ("2024-02-01", "2024-03-01", "2024-04-02"):
        schritt(lambda t=t: raten.append(kb.zahlung(t, k["rate"])))
    schritt(lambda: api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200))
    schritt(lambda: api.delete(f"/api/buchungen/{raten[1]['id']}", erwartet=204))
    schritt(lambda: api.patch(f"/api/kredite/{k['id']}", json={"sondertilgungen": [{"datum": "2024-05-15",
                                                                                    "betrag": 1000}]},
                              erwartet=200))
    schritt(lambda: api.post(f"/api/kredite/{k['id']}/jahresabgleich",
                             json={"jahr": 2024, "restschuld": 5, "zinsen": 7}, erwartet=200))
    for aid, z in zip(reversed(ids), reversed(zustaende[:-1])):
        api.post(f"/api/aenderungen/{aid}/rueckgaengig", erwartet=200)
        assert bestand(api) == z
