"""M3: Umbuchungserkennung (buchhaltungspflege.md 4, T 11).

Erwartung: bekannte Wahrheit des Generators (Paare je Abrufstufe, Gründe der Nicht-Zusammenführung), in
``tests/generator/test_m3_daten.py`` mit dem Orakel ``tests/hilfen/m3_orakel.py`` gegengeprüft; für den
Abruf auf Wunsch rechnet das Orakel direkt auf dem REST-Zustand.
"""

from __future__ import annotations

import pytest

from tests.hilfen import m3_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import nach_kennung, setze_zeit, sync
from tests.hilfen.m3 import (UNKATEGORISIERT, aenderungen_seit, alle_aenderungen, bestand, erfassen, konto_id,
                             lade_m3, letzte_aenderung_id, m3_api, pruefe_eintraege, stammdaten_anlegen)

VON = "2024-01-01"


@pytest.fixture(scope="module")
def md():
    return lade_m3()


def _kennung(u):
    return f"bank:{u['iban']}:{u['umsatz_id']}"


def _pruefe_paare(api, daten, paare, einzeln):
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    konten = {k["iban"]: k["id"] for k in api.konten() if k["iban"]}
    bank = nach_kennung(api.alle_buchungen())
    for p in paare:
        x, y = alle[p["behalten"]], alle[p["entfernt"]]
        b = bank[_kennung(x)]
        assert bank[_kennung(y)]["id"] == b["id"], f"{p} nicht zusammengeführt"
        assert b["extern_ids"] == sorted([_kennung(x), _kennung(y)])
        assert [(s["konto_id"], s["betrag"]) for s in b["splits"]] == [(konten[x["iban"]], x["betrag"]),
                                                                      (konten[y["iban"]], y["betrag"])]
        assert (b["datum"], b["verwendungszweck"], b["gegen_iban"]) == (x["buchungstag"], x["verwendungszweck"],
                                                                        x["gegenpartei_iban"])
        assert b["ist_umbuchung"] is True and b["kategorie_id"] is None and b["vorschlag"] is None
    for uid in einzeln:
        b = bank[_kennung(alle[uid])]
        assert b["extern_ids"] == [_kennung(alle[uid])], f"{uid} darf nicht zusammengeführt werden"
        assert b["ist_umbuchung"] is False


@pytest.mark.kern
def test_automatisch_stufe_fuer_stufe(tmp_path, md, netz_gesperrt):
    daten, erw = md
    api = m3_api(tmp_path, heute=erw["stufen"][0], umbuchung_automatisch=True)
    bisher: list[dict] = []
    for n, stufe in enumerate(erw["stufen"]):
        setze_zeit(api, f"{stufe}T12:00:00Z")
        vor = letzte_aenderung_id(api)
        lauf = sync(api, von=VON)
        assert lauf["status"] == "erfolgreich"
        bisher += erw["umbuchungen"]["je_stufe"][n]
        gebucht = {u["umsatz_id"] for u in daten["bank"]["umsaetze"] if not u["vormerkung"]
                   and u["buchungstag"] <= stufe}
        paarig = {v for p in bisher for v in p.values()}
        _pruefe_paare(api, daten, bisher, sorted(gebucht - paarig))
        neu = aenderungen_seit(api, vor)
        assert all(a["gruppe"] == f"sync:{lauf['id']}" for a in neu)
        erk = [a for a in neu if a["aktion"] == "umbuchung_erkennen"]
        assert all(a["quelle"] == "umbuchung" for a in erk)
        entfernt = sorted(e["objekt_id"] for a in erk for e in a["eintraege"]
                          if e["objekt"] == "buchung" and e["art"] == "geloescht")
        assert len(entfernt) == len(erw["umbuchungen"]["je_stufe"][n])
        if n == 2:
            assert any(erw["fall"][p["behalten"]] == "umbuchung_stufengrenze"
                       for p in erw["umbuchungen"]["je_stufe"][2]), "nachträglich beim Eintreffen der zweiten Seite"
    assert len(bisher) == len(erw["umbuchungen"]["endstand"])


@pytest.mark.kern
def test_salden_und_kategorien_unveraendert(tmp_path, md, netz_gesperrt):
    """T 11: Umbuchungen zählen nicht als Einnahme oder Ausgabe; alle Salden bleiben, Unkategorisiert verliert sie."""
    daten, erw = md
    ohne = m3_api(tmp_path / "ohne")
    mit = m3_api(tmp_path / "mit", umbuchung_automatisch=True)
    for a in (ohne, mit):
        stammdaten_anlegen(a)
        sync(a, von=VON)

    def salden(a):
        return {(k["name"], k["art"]): (k["saldo"], k["anzahl_buchungen"]) for k in a.uebersicht()["konten"]}
    s_ohne, s_mit = salden(ohne), salden(mit)
    paare = len(erw["umbuchungen"]["endstand"])
    for key, (saldo, anzahl) in s_ohne.items():
        assert s_mit[key][0] == saldo, key
        if key == ("Unkategorisiert", "eigenkapital"):
            assert s_mit[key][1] == anzahl - 2 * paare
        elif key[1] in ("aufwand", "ertrag"):
            assert s_mit[key][1] == anzahl
    assert len(mit.alle_buchungen()) == len(ohne.alle_buchungen()) - paare
    assert len([b for b in mit.alle_buchungen() if b["ist_umbuchung"]]) == paare


@pytest.mark.kern
def test_ohne_automatik_wie_m2_und_auf_wunsch(tmp_path, md, netz_gesperrt):
    daten, erw = md
    api = m3_api(tmp_path)
    sync(api, von=VON)
    gebucht = [u["umsatz_id"] for u in daten["bank"]["umsaetze"] if not u["vormerkung"]]
    _pruefe_paare(api, daten, [], gebucht)
    assert alle_aenderungen(api, quelle="umbuchung") == []
    bs = api.alle_buchungen()
    konten = api.konten()
    soll = orakel.eindeutige_paare(bs, konten, erw["fenster_tage"])
    vorher = bestand(api)
    vor = letzte_aenderung_id(api)
    t = api.post("/api/umbuchungen/erkennen", json={"trocken": True}, erwartet=200).daten
    assert (t["trocken"], t["anzahl"]) == (True, len(soll))
    assert [(p["behalten_id"], p["entfernt_id"]) for p in t["paare"]] == soll
    assert bestand(api) == vorher and aenderungen_seit(api, vor) == []
    r = api.post("/api/umbuchungen/erkennen", erwartet=200).daten
    assert (r["trocken"], r["paare"]) == (False, t["paare"])
    (a,) = aenderungen_seit(api, vor)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("umbuchung", "umbuchung_erkennen", None)
    pruefe_eintraege(a, vorher, bestand(api))
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    endstand = {frozenset(p.values()) for p in erw["umbuchungen"]["endstand"]}
    bank = {b["id"]: b for b in api.alle_buchungen()}
    ist = {frozenset(e.split(":")[2] for e in bank[p["behalten_id"]]["extern_ids"]) for p in r["paare"]}
    assert ist == endstand
    assert api.post("/api/umbuchungen/erkennen", json={}, erwartet=200).daten["anzahl"] == 0
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher, "Rückgängig trennt die Umbuchungen wieder exakt"
    assert len(alle) > len(bank)


def test_zeitfenster_konfigurierbar(tmp_path, md, netz_gesperrt):
    daten, erw = md
    api = m3_api(tmp_path, umbuchung_automatisch=True, umbuchung_fenster_tage=4)
    sync(api, von=VON)
    vier = [uid for uid, f in erw["fall"].items() if f == "umbuchung_4_tage"]
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    bank = nach_kennung(api.alle_buchungen())
    assert bank[_kennung(alle[vier[0]])]["id"] == bank[_kennung(alle[vier[1]])]["id"]


@pytest.mark.kern
def test_fremde_iban_nie_umbuchung(tmp_path, md, netz_gesperrt):
    daten, erw = md
    api = m3_api(tmp_path, umbuchung_automatisch=True)
    sync(api, von=VON)
    bank = nach_kennung(api.alle_buchungen())
    for u in daten["bank"]["umsaetze"]:
        if u["vormerkung"]:
            continue
        b = bank[_kennung(u)]
        if not b["ist_umbuchung"]:
            assert b["gegen_iban"] == u["gegenpartei_iban"], "Gegen-IBAN aus dem Umsatz"
        if u["gegenpartei_iban"] == erw["ibans"]["fremd"]:
            assert not b["ist_umbuchung"], f"{u['umsatz_id']}: Betrag an fremde IBAN ist keine Umbuchung"


@pytest.mark.kern
def test_von_hand_zusammenfuehren(tmp_path, md, netz_gesperrt):
    daten, erw = md
    api = m3_api(tmp_path)
    sync(api, von=VON)
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    bank = nach_kennung(api.alle_buchungen())
    mehrdeutig = [uid for uid, f in erw["fall"].items() if f == "umbuchung_mehrdeutig"]
    giro_a, _, spar = sorted(mehrdeutig, key=lambda u: (alle[u]["iban"] != erw["ibans"]["giro"], u))
    a, b = bank[_kennung(alle[giro_a])], bank[_kennung(alle[spar])]
    t = api.tag("Sparen")
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [b["id"]], "hinzufuegen": [t["id"]]}, erwartet=200)
    vor = letzte_aenderung_id(api)
    vorher = bestand(api)
    r = api.post("/api/umbuchungen/zusammenfuehren", json={"buchung_ids": [b["id"], a["id"]]}, erwartet=200).daten
    klein, gross = sorted([a, b], key=lambda x: x["id"])
    assert r["id"] == klein["id"] and gross["id"] not in {x["id"] for x in api.alle_buchungen()}
    assert [s["id"] for s in r["splits"]] == [klein["splits"][0]["id"], gross["splits"][0]["id"]], \
        "Bankseiten behalten ihre Split-IDs"
    assert [t_["id"] for t_ in r["tags"]] == [t["id"]] and r["extern_ids"] == sorted(a["extern_ids"] + b["extern_ids"])
    (aend,) = aenderungen_seit(api, vor)
    assert aend["aktion"] == "umbuchung_zusammenfuehren"
    pruefe_eintraege(aend, vorher, bestand(api))
    unk = konto_id(api, UNKATEGORISIERT)
    assert not any(s["konto_id"] == unk for s in r["splits"])


@pytest.mark.kern
def test_von_hand_fehler(api):
    g = api.konto("Giro")
    s = api.konto("Spar", "sparkonto")
    lm = api.konto("Lebensmittel", "aufwand")
    x = erfassen(api, art="ausgabe", datum="2024-01-01", konto_id=g["id"], betrag=500)
    y = erfassen(api, art="einnahme", datum="2024-03-01", konto_id=s["id"], betrag=500)
    gleich = erfassen(api, art="einnahme", datum="2024-01-01", konto_id=g["id"], betrag=500)
    anders = erfassen(api, art="einnahme", datum="2024-01-01", konto_id=s["id"], betrag=501)
    kat = erfassen(api, art="einnahme", datum="2024-01-01", konto_id=s["id"], betrag=500, kategorie_id=lm["id"])
    gesperrt = erfassen(api, art="einnahme", datum="2024-01-01", konto_id=s["id"], betrag=500)
    api.patch(f"/api/buchungen/{gesperrt['id']}", json={"status": "abgeglichen"}, erwartet=200)
    vorher = api.zustand()

    def zf(ids, erwartet):
        return api.post("/api/umbuchungen/zusammenfuehren", json={"buchung_ids": ids}, erwartet=erwartet)
    for ids in ([x["id"]], [x["id"], x["id"]], [x["id"], y["id"], gleich["id"]], []):
        assert fehlercode(zf(ids, 422)) == "validierung"
    r = zf([x["id"], 999999], 422)
    assert fehlercode(r) == "referenz_unbekannt" and r.json()["fehler"]["details"]["buchung_ids"] == [999999]
    for ids in ([x["id"], gleich["id"]], [x["id"], anders["id"]], [x["id"], kat["id"]]):
        assert fehlercode(zf(ids, 422)) == "keine_umbuchung"
    r = zf([x["id"], gesperrt["id"]], 409)
    assert fehlercode(r) == "buchung_gesperrt" and r.json()["fehler"]["details"]["buchung_ids"] == [gesperrt["id"]]
    assert api.zustand() == vorher
    ok = zf([y["id"], x["id"]], 200).daten
    assert ok["id"] == x["id"] and ok["datum"] == "2024-01-01", "Zeitfenster gilt von Hand nicht"
    assert api.post("/api/umbuchungen/erkennen", json={"trocken": "ja"}, erwartet=422)
