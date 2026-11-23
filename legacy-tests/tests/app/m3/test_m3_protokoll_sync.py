"""M3: Protokoll und Rückgängig für Synchronisation, Planer, TAN-Fortsetzung und Import (protokoll.md 4.2, 6.4).

T 3.5: Jede automatische Änderung (Abruf, Regel-Vorschläge, Abgleich mit Altbestand) steht im Protokoll.
T 3.6: Ein ganzer Lauf lässt sich exakt zurücknehmen; danach übernimmt ein erneuter Abruf dieselben Umsätze.
"""

from __future__ import annotations

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api
from tests.hilfen.m2 import lade_sync, mock_config, nach_kennung, regeln_anlegen, sync
from tests.hilfen.m3 import (aenderungen_seit, alle_aenderungen, bestand, diff, lade_m3, letzte_aenderung_id,
                             m3_api, pruefe_eintraege, zustand_m3)
from tests.hilfen.pfade import KMY

VON = "2024-01-01"


def _gruppe(api, lauf_id):
    return sorted(alle_aenderungen(api, gruppe=f"sync:{lauf_id}"), key=lambda a: a["id"])


def _bankkonto(b: dict, konten: dict[int, dict]) -> set[str]:
    return {konten[s["konto_id"]]["iban"] for s in b["splits"] if konten[s["konto_id"]]["iban"]}


@pytest.mark.kern
def test_lauf_erzeugt_gruppe(tmp_path, netz_gesperrt):
    api = m3_api(tmp_path)
    _, erw = lade_m3()
    vorher = bestand(api)
    vor = letzte_aenderung_id(api)
    lauf = sync(api, von=VON)
    assert lauf["status"] == "erfolgreich"
    nachher = bestand(api)
    neu = aenderungen_seit(api, vor)
    assert neu == _gruppe(api, lauf["id"]), "alle Änderungen des Laufs tragen die Gruppe sync:<lauf_id>"
    assert [a["aktion"] for a in neu] == ["sync_kontozuordnung"] + ["sync_konto"] * 3
    assert {a["quelle"] for a in neu} == {"sync"}
    zuordnung, *je_konto = neu
    assert {(e["objekt"], e["art"]) for e in zuordnung["eintraege"]} == {("konto", "angelegt")}
    assert sorted(e["nachher"]["iban"] for e in zuordnung["eintraege"]) == erw["iban_reihenfolge"]
    # Einträge aller Änderungen zusammen = Gesamtunterschied; jedes Objekt genau einmal
    gesamt = diff(vorher, nachher)
    gesehen = [(e["objekt"], e["objekt_id"]) for a in neu for e in a["eintraege"]]
    assert len(gesehen) == len(set(gesehen)) and set(gesehen) == set(gesamt)
    konten = {k["id"]: k for k in api.konten()}
    for a, iban in zip(je_konto, erw["iban_reihenfolge"]):
        bs = [e["nachher"] for e in a["eintraege"] if e["objekt"] == "buchung"]
        assert len(bs) == erw["anzahl_gebucht"][iban]
        assert all(_bankkonto(b, konten) == {iban} for b in bs), "sync_konto enthält nur Buchungen dieses Kontos"
        for e in a["eintraege"]:
            assert e["art"] == "angelegt" and e["nachher"] == gesamt[(e["objekt"], e["objekt_id"])][1]
    # zweiter Abruf ohne neue Umsätze: keine Änderung
    vor = letzte_aenderung_id(api)
    sync(api, von=VON)
    assert aenderungen_seit(api, vor) == []


@pytest.mark.kern
def test_lauf_als_gruppe_rueckgaengig_und_erneut(tmp_path, netz_gesperrt):
    api = m3_api(tmp_path)
    z0 = zustand_m3(api)
    lauf = sync(api, von=VON)
    erst = api.alle_buchungen()
    u = api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"}, erwartet=200).daten
    assert u["rueckgaengig_von"] == [a["id"] for a in _gruppe(api, lauf["id"])]
    assert zustand_m3(api) == z0
    assert api.get("/api/sync/konten", erwartet=200).daten == [], "entfernte Konten verlieren ihren Sync-Zustand"
    assert len(api.get("/api/sync/laeufe", erwartet=200).daten) == 1, "Läufe sind kein Buchbestand"
    lauf2 = sync(api, von=VON)
    assert all(k["buchungen_neu"] == k["umsaetze_gesamt"] - k["vormerkungen_ignoriert"] and k["konto_neu"]
               for k in lauf2["konten"]), "vergessene Kennungen: dieselben Umsätze werden erneut übernommen"
    zweit = api.alle_buchungen()

    def ohne_ids(bs):
        return sorted((b["datum"], b["verwendungszweck"], b["extern_ids"], [s["betrag"] for s in b["splits"]])
                      for b in bs)
    assert ohne_ids(zweit) == ohne_ids(erst)
    assert min(b["id"] for b in zweit) > max(b["id"] for b in erst), "IDs werden nie wiederverwendet"
    assert fehlercode_von(api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"},
                                   erwartet=409)) == "bereits_rueckgaengig"


def pruefe_kette(aenderungen: list[dict], vorher: dict, nachher: dict) -> None:
    """Mehrere Änderungen nacheinander: je Objekt schließt jeder Eintrag an den vorigen an (Nettowirkung je Änderung)."""
    stand = dict(vorher)
    for a in aenderungen:
        for e in a["eintraege"]:
            k = (e["objekt"], e["objekt_id"])
            assert stand.get(k) == e["vorher"], f"Änderung {a['id']}: vorher von {k} schließt nicht an"
            assert e["vorher"] != e["nachher"]
            if e["nachher"] is None:
                stand.pop(k, None)
            else:
                stand[k] = e["nachher"]
    assert stand == nachher, "Kette der Einträge ergibt nicht den Endzustand"


def fehlercode_von(r):
    return r.json()["fehler"]["code"]


@pytest.mark.kern
def test_ein_konto_rueckgaengig(tmp_path, netz_gesperrt):
    api = m3_api(tmp_path)
    _, erw = lade_m3()
    lauf = sync(api, von=VON)
    gruppe = _gruppe(api, lauf["id"])
    # das zuletzt verarbeitete Konto: seine Empfänger werden von keinem anderen Konto verwendet
    letztes = erw["iban_reihenfolge"][-1]
    a = gruppe[-1]
    assert a["aktion"] == "sync_konto"
    vorher = zustand_m3(api)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    konten = {k["id"]: k for k in api.konten()}
    assert not any(_bankkonto(b, konten) == {letztes} for b in api.alle_buchungen())
    lauf2 = sync(api, von=VON)
    neu = {k["iban"]: k["buchungen_neu"] for k in lauf2["konten"]}
    assert neu[letztes] == erw["anzahl_gebucht"][letztes] and all(v == 0 for i, v in neu.items() if i != letztes)
    nachher = zustand_m3(api)
    assert len(nachher["buchungen"]) == len(vorher["buchungen"])


@pytest.mark.kern
def test_regelvorschlaege_und_altbestand_im_protokoll(tmp_path, netz_gesperrt):
    """M2-Daten: Regeln greifen beim Abruf, Altbestand wird zusammengeführt – alles in sync_konto."""
    api = Api(mock_config(tmp_path))
    api.import_kmy(KMY / "sync_altbestand.kmy", erwartet=200)
    regeln_anlegen(api)
    vorher = bestand(api)
    lauf = sync(api, von=VON)
    nachher = bestand(api)
    gruppe = _gruppe(api, lauf["id"])
    pruefe_kette(gruppe, vorher, nachher)
    eintraege = [e for a in gruppe for e in a["eintraege"]]
    assert any(e["art"] == "geaendert" and e["objekt"] == "buchung" and len(e["nachher"]["extern_ids"])
               > len(e["vorher"]["extern_ids"]) for e in eintraege), "Zusammenführung mit Altbestand"
    assert any(e["art"] == "angelegt" and e["objekt"] == "buchung" and e["nachher"]["vorschlag"]
               for e in eintraege), "Regel-Vorschläge"
    assert any(e["objekt"] == "verdacht" for e in eintraege), "Dublettenverdachte"
    kennungen = set(nach_kennung(api.alle_buchungen()))
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"}, erwartet=200)
    assert bestand(api) == vorher
    assert nach_kennung(api.alle_buchungen()) == {}
    sync(api, von=VON)
    assert set(nach_kennung(api.alle_buchungen())) == kennungen, "Kennungen vergessen, erneut übernommen"


def test_planer_lauf_protokolliert(tmp_path, netz_gesperrt):
    api = m3_api(tmp_path, sync_intervall_minuten=60, planer_starten=False)
    lauf = kontor.modul("kontor.sync").planer_takt(api.app)
    assert lauf and lauf["ausloeser"] == "planer"
    g = _gruppe(api, lauf["id"])
    assert g and {a["quelle"] for a in g} == {"sync"}


def test_tan_fortsetzung_protokolliert(tmp_path, netz_gesperrt):
    _, erw = lade_sync()
    api = Api(mock_config(tmp_path, szenario="tan_erforderlich"))
    lauf = sync(api, von=VON)
    assert lauf["status"] == "wartet_auf_tan"
    vor_antwort = _gruppe(api, lauf["id"])
    assert [a["aktion"] for a in vor_antwort] == ["sync_kontozuordnung"], "Zuordnung vor dem ersten Abruf"
    vor = letzte_aenderung_id(api)
    vorher = bestand(api)
    r = api.post(f"/api/tan-anforderungen/{lauf['tan_anforderung_id']}/antwort", json={"tan": erw["tan"]},
                 erwartet=200).daten
    assert r["status"] == "erfolgreich"
    neu = aenderungen_seit(api, vor)
    assert neu and all(a["gruppe"] == f"sync:{lauf['id']}" and a["aktion"] == "sync_konto" for a in neu)
    gesehen = {(e["objekt"], e["objekt_id"]) for a in neu for e in a["eintraege"]}
    assert gesehen == set(diff(vorher, bestand(api)))
    assert erw["tan"] not in api.get("/api/aenderungen", params={"pro_seite": 500}, erwartet=200).text


@pytest.mark.kern
def test_import_rueckgaengig_und_erneut(api):
    z0 = zustand_m3(api)
    r = api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200).daten
    z1 = zustand_m3(api)
    (a,) = alle_aenderungen(api, gruppe=f"import:{r['import_id']}")
    assert (a["quelle"], a["aktion"]) == ("import", "import_kmymoney")
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"import:{r['import_id']}"}, erwartet=200)
    assert zustand_m3(api) == z0
    assert len(api.get("/api/importe", erwartet=200).daten) == 1, "Importvorgänge bleiben (kein Buchbestand)"
    r2 = api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200).daten
    assert r2["buchungen_neu"] == r["buchungen_neu"] and r2["konten_neu"] == r["konten_neu"]
    z2 = zustand_m3(api)
    assert len(z2["buchungen"]) == len(z1["buchungen"])
    assert z2["uebersicht"]["summe_bestand"] == z1["uebersicht"]["summe_bestand"]


def test_eintraege_entsprechen_differenz_beim_import(api):
    vorher = bestand(api)
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    (a,) = alle_aenderungen(api)
    pruefe_eintraege(a, vorher, bestand(api))
