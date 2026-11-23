"""M31: Erklärung, Übersicht und Einstellungen des Lernmodells, mitgelieferte Lerndaten
(lernmodell.md 8, 10; E-280, E-281) – REST, kern.

Erwartungen aus der unabhängigen Umsetzung ``tests/hilfen/lern_orakel.py`` (über ``m4.Buch``) und
``tests/hilfen/m31``.
"""

from __future__ import annotations

import pytest

from tests.hilfen import m31
from tests.hilfen.api import Api, fehlercode, neue_api, neue_config
from tests.hilfen.lern_orakel import merkmale
from tests.hilfen.m2 import mock_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id, rueckgaengig
from tests.hilfen.m4 import Buch
from tests.hilfen.m9 import einspielen, oeffne, sicherung
from tests.hilfen.m31 import einstellungen, einstellungen_setzen, erklaerung, erklaerung_soll, vorhersage_soll

pytestmark = pytest.mark.kern


def _vorhersage(api, **eintrag) -> dict:
    return api.post("/api/lernmodell/vorhersage", json={"eintraege": [eintrag]}, erwartet=200).daten["ergebnisse"][0]


def _buch_unter_schwelle(api) -> tuple[Buch, list[str]]:
    """Ein Bestand, in dem die Anfrage ``Markt Fiktiv``/``Einkauf`` zwischen 50 % und 70 % liegt."""
    b = Buch(api)
    for _ in range(2):
        b.einfach("Markt Fiktiv", "Einkauf Woche", -2500, "Lebensmittel")
    b.einfach("Markt Fiktiv", "Einkauf Kaffee", -2500, "Café")
    b.einfach("Tankstelle Fiktiv", "Diesel", -6000, "Tanken")
    m = merkmale("Markt Fiktiv", "Einkauf", -2500)
    p = m31.rangfolge(b.modell(), m)[0][0]
    assert 0.55 < p < 0.7, f"Voraussetzung des Tests: Sicherheit {float(p)} zwischen 55 % und 70 %"
    return b, m


# ------------------------------------------------------------------ 8.3 Einstellungen


def test_einstellungen_vorgabe(tmp_path):
    assert einstellungen(neue_api(tmp_path / "a")) == {"schwelle_promille": 700, "regeln_automatisch": False}
    assert einstellungen(neue_api(tmp_path / "b", regeln_automatisch=True)) == {
        "schwelle_promille": 700, "regeln_automatisch": True}, "Vorgabe aus der Konfiguration"
    assert neue_api(tmp_path / "c").get("/api/lernmodell", erwartet=200).daten["schwelle_promille"] == 700


def test_einstellungen_teilweise_ohne_protokoll_und_ueber_neustart(tmp_path):
    api = neue_api(tmp_path)
    a0 = letzte_aenderung_id(api)
    assert einstellungen_setzen(api, schwelle_promille=600) == {"schwelle_promille": 600, "regeln_automatisch": False}
    assert einstellungen_setzen(api) == {"schwelle_promille": 600, "regeln_automatisch": False}, "{} ändert nichts"
    assert einstellungen_setzen(api, regeln_automatisch=True) == {"schwelle_promille": 600,
                                                                   "regeln_automatisch": True}
    for grenze in (500, 990):
        assert einstellungen_setzen(api, schwelle_promille=grenze)["schwelle_promille"] == grenze
    einstellungen_setzen(api, schwelle_promille=650)
    assert api.get("/api/lernmodell", erwartet=200).daten["schwelle_promille"] == 650
    assert aenderungen_seit(api, a0) == [], "Einstellungen sind kein Buchbestand"
    neu = Api(neue_config(tmp_path, regeln_automatisch=False))
    assert einstellungen(neu) == {"schwelle_promille": 650, "regeln_automatisch": True}, (
        "gespeicherte Werte gelten über einen Neustart und gehen der Konfiguration vor")


@pytest.mark.parametrize("koerper", [
    {"schwelle_promille": 499}, {"schwelle_promille": 991}, {"schwelle_promille": "700"},
    {"schwelle_promille": 700.5}, {"schwelle_promille": True}, {"schwelle_promille": None},
    {"regeln_automatisch": "ja"}, {"regeln_automatisch": 1}, {"regeln_automatisch": None},
    {"unbekannt": 1}, [], "700",
])
def test_einstellungen_validierung(api, koerper):
    vorher = einstellungen(api)
    assert fehlercode(api.put(m31.EINSTELLUNGEN, json=koerper, erwartet=422)) == "validierung"
    assert einstellungen(api) == vorher


def test_einstellungen_nicht_in_der_sicherung(tmp_path):
    quelle = neue_api(tmp_path / "q")
    Buch(quelle).einfach("Markt Fiktiv", "Einkauf", -100, "Lebensmittel")
    m0, _ = oeffne(sicherung(quelle))
    einstellungen_setzen(quelle, schwelle_promille=800, regeln_automatisch=True)
    m1, _ = oeffne(sicherung(quelle))
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])
    ziel = neue_api(tmp_path / "z")
    einstellungen_setzen(ziel, schwelle_promille=550)
    einspielen(ziel, sicherung(quelle))
    assert einstellungen(ziel) == {"schwelle_promille": 550, "regeln_automatisch": False}


def test_schwelle_wirkt_auf_vorhersage_anwenden_und_zustand(api):
    b, m = _buch_unter_schwelle(api)
    offen = b.einfach("Markt Fiktiv", "Einkauf", -2500, None)
    anfrage = {"empfaenger": "Markt Fiktiv", "verwendungszweck": "Einkauf", "betrag": -2500}
    assert _vorhersage(api, **anfrage) == vorhersage_soll(b.modell(), m, 700)
    assert api.post("/api/lernmodell/anwenden", json={"buchung_ids": [offen["id"]]}, erwartet=200).daten[
        "anzahl"] == 0
    einstellungen_setzen(api, schwelle_promille=550)
    soll = vorhersage_soll(b.modell(), m, 550)
    assert soll["kategorie_id"] == b.kats["Lebensmittel"]
    assert _vorhersage(api, **anfrage) == soll
    assert _vorhersage(api, buchung_id=offen["id"]) == soll
    assert api.get("/api/lernmodell", erwartet=200).daten["schwelle_promille"] == 550
    a = api.post("/api/lernmodell/anwenden", json={"buchung_ids": [offen["id"]]}, erwartet=200).daten
    assert a["aenderungen"] == [{"buchung_id": offen["id"], "kategorie_id": soll["kategorie_id"],
                                 "sicherheit": soll["sicherheit"]}]
    v = api.buchung_lesen(offen["id"])["vorschlag"]
    assert (v["quelle"], v["kategorie_id"], v["sicherheit"]) == ("lernmodell", soll["kategorie_id"], soll["sicherheit"])


# ------------------------------------------------------------------ 8.1 Erklärung


def _vergleiche(ist: dict, soll: dict, vorhersage: dict) -> None:
    assert ist["grund"] == soll["grund"]
    assert ist["vorhersage"] == vorhersage
    assert (ist["beste_kategorie_id"], ist["vergleich_kategorie_id"]) == (soll["beste"], soll["vergleich"])
    eintraege = {e["merkmal"]: e for e in ist["merkmale"]}
    assert len(eintraege) == len(ist["merkmale"]), "je Merkmal ein Eintrag"
    for f, s in soll["merkmale"].items():
        assert f in eintraege, f"bekanntes Merkmal {f} fehlt"
        assert {k: eintraege[f][k] for k in s} == s, f
    for f, e in eintraege.items():
        if f not in soll["merkmale"]:
            assert e["anzahl"] == 0, f"{f}: nur bekannte Merkmale haben Zählungen"


def test_erklaerung_kein_modell(api):
    b = Buch(api)
    x = b.einfach("Markt Fiktiv", "Einkauf", -100, None)
    e = erklaerung(api, x["id"])
    assert e["grund"] == "kein_modell"
    assert e["vorhersage"] == {"kategorie_id": None, "sicherheit": None, "kandidaten": []}
    assert (e["beste_kategorie_id"], e["vergleich_kategorie_id"], e["aehnliche"]) == (None, None, [])


def test_erklaerung_unbekannt(api):
    b = Buch(api)
    b.einfach("Markt Fiktiv", "Einkauf", -100, "Lebensmittel")
    x = b.einfach("Ganz Anders", "zzz qqq", -100, None)
    m = merkmale("Ganz Anders", "zzz qqq", -100)
    _vergleiche(erklaerung(api, x["id"]), erklaerung_soll(b.modell(), m),
                {"kategorie_id": None, "sicherheit": None, "kandidaten": []})


def test_erklaerung_unter_schwelle_und_vorschlag(api):
    b, m = _buch_unter_schwelle(api)
    x = b.einfach("Markt Fiktiv", "Einkauf", -2500, None)
    soll = erklaerung_soll(b.modell(), m)
    assert soll["grund"] == "unter_schwelle"
    _vergleiche(erklaerung(api, x["id"]), soll, vorhersage_soll(b.modell(), m))
    einstellungen_setzen(api, schwelle_promille=550)
    soll = erklaerung_soll(b.modell(), m, 550)
    assert soll["grund"] == "vorschlag"
    _vergleiche(erklaerung(api, x["id"]), soll, vorhersage_soll(b.modell(), m, 550))


def test_erklaerung_mehrere_merkmale_exakt(api):
    b = Buch(api)
    daten = [("Bäckerei Korn", "Brötchen Kartenzahlung Filiale", -450, "Lebensmittel"),
             ("Bäckerei Korn", "Kuchen Bar", -1290, "Café"),   # W-018 (E-309): beste Buchung eindeutig
             ("Bäckerei Korn", "Brötchen Filiale", -380, "Lebensmittel"),
             ("Café Bohne", "Kaffee Kartenzahlung", -340, "Café"),
             ("Café Bohne", "Kuchen Kaffee", -720, "Café"),
             ("Tankstelle Fiktiv", "Diesel Kartenzahlung", -6000, "Tanken"),
             ("Arbeitgeber Fiktiv", "Gehalt Oktober", 250000, "Gehalt")]
    for d in daten:
        b.einfach(*d)
    x = b.einfach("Bäckerei Korn", "Kuchen Brötchen Kartenzahlung", -500, None)
    m = merkmale("Bäckerei Korn", "Kuchen Brötchen Kartenzahlung", -500)
    soll = erklaerung_soll(b.modell(), m)
    assert soll["vergleich"] is not None and len(soll["merkmale"]) >= 4
    e = erklaerung(api, x["id"])
    _vergleiche(e, soll, vorhersage_soll(b.modell(), m))
    # ähnliche Buchungen: nur aus der Trainingsmenge, höchstens 5, Gewicht nicht steigend, die eindeutig beste zuerst
    training = {bu["id"]: merkmale(n, z, r) for bu, (n, z, r, _) in zip(b.buchungen, daten)}
    ids = [a["buchung_id"] for a in e["aehnliche"]]
    assert 1 <= len(ids) <= 5 and len(set(ids)) == len(ids)
    assert set(ids) <= set(training), "nur Trainingsbuchungen"
    gew = [m31.gewicht(m, training[i]) for i in ids]
    assert all(g > 0 for g in gew) and gew == sorted(gew, reverse=True)
    beste = max(training, key=lambda i: m31.gewicht(m, training[i]))
    assert sorted((m31.gewicht(m, v) for v in training.values()), reverse=True)[1] < m31.gewicht(m, training[beste])
    assert ids[0] == beste
    alle_mit_gewicht = [i for i in training if m31.gewicht(m, training[i]) > 0]
    assert len(ids) == min(5, len(alle_mit_gewicht))


def test_erklaerung_einer_trainingsbuchung_und_ohne_wirkung(api):
    b = Buch(api)
    t = [b.einfach("Markt Fiktiv", "Einkauf", -100, "Lebensmittel") for _ in range(3)]
    b.einfach("Tankstelle Fiktiv", "Diesel", -5000, "Tanken")
    a0 = letzte_aenderung_id(api)
    e = erklaerung(api, t[0]["id"])
    m = merkmale("Markt Fiktiv", "Einkauf", -100)
    _vergleiche(e, erklaerung_soll(b.modell(), m), vorhersage_soll(b.modell(), m))
    assert aenderungen_seit(api, a0) == []
    assert erklaerung(api, 999999, erwartet=404).status_code == 404


def test_uebersicht_lesend(api):
    b = Buch(api)
    for i in range(12):
        b.einfach("Markt Fiktiv", f"Einkauf {i}", -100 - i, "Lebensmittel")
        b.einfach("Tankstelle Fiktiv", "Diesel", -5000 - i, "Tanken")
    a0 = letzte_aenderung_id(api)
    assert isinstance(api.get("/api/lernmodell/uebersicht", erwartet=200).daten, dict)
    einstellungen_setzen(api, schwelle_promille=900)
    assert isinstance(api.get("/api/lernmodell/uebersicht", erwartet=200).daten, dict)
    assert isinstance(neue_api().get("/api/lernmodell/uebersicht", erwartet=200).daten, dict), "auch ohne Daten"
    assert aenderungen_seit(api, a0) == []


# ------------------------------------------------------------------ 10 Mock-Lerndaten


def _lerndaten(api, erwartet=(200, 201)):
    return api.post("/api/mock/lerndaten", erwartet=erwartet)


def test_lerndaten_laden_und_rueckgaengig(tmp_path):
    api = mock_api(tmp_path, daten=None, heute="2026-11-16")
    a0 = letzte_aenderung_id(api)
    _lerndaten(api)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"]) == ("import", "mock_lerndaten")
    alle = api.alle_buchungen()
    # W-019 (E-309): 3000 Buchungen nach den Mustern, dazu höchstens eine Eröffnungsbuchung gegen Eigenkapital
    eigen = {k["id"] for k in api.konten() if k["art"] == "eigenkapital"
             and k["extern_id"] not in ("kontor:unkategorisiert", "kontor:korrektur")}
    eroeffnung = [b for b in alle if any(s["konto_id"] in eigen for s in b["splits"])]
    assert len(eroeffnung) <= 1
    bs = [b for b in alle if b not in eroeffnung]
    assert len(bs) == 3000
    assert min(b["datum"] for b in bs) >= "2022-09-01" and max(b["datum"] for b in bs) <= "2026-10-31"
    unkat = [k["id"] for k in api.konten() if k["extern_id"] == "kontor:unkategorisiert"]
    assert unkat and any(s["konto_id"] in unkat for b in bs for s in b["splits"]), "neueste auf Unkategorisiert"
    assert any(b["kategorie_id"] is not None for b in bs)
    assert api.get("/api/lernmodell", erwartet=200).daten["trainingsbuchungen"] > 0
    assert fehlercode(_lerndaten(api, erwartet=409)) == "bestand_nicht_leer"
    rueckgaengig(api, a["id"])
    assert api.alle_buchungen() == []


def test_lerndaten_nur_im_mock_und_leeren_bestand(tmp_path, api):
    assert fehlercode(_lerndaten(api, erwartet=409)) == "nur_mock_modus"
    m = mock_api(tmp_path / "m", daten=None, heute="2026-11-16")
    g, k = m.konto("Giro", "girokonto")["id"], m.konto("Kat", "aufwand")["id"]
    m.buchung("2026-01-01", [(g, -100), (k, 100)])
    a0 = letzte_aenderung_id(m)
    assert fehlercode(_lerndaten(m, erwartet=409)) == "bestand_nicht_leer"
    assert aenderungen_seit(m, a0) == [] and len(m.alle_buchungen()) == 1


def test_lerndaten_mit_automatischen_regeln(tmp_path):
    api = mock_api(tmp_path, daten=None, heute="2026-11-16", regeln_automatisch=True)
    a0 = letzte_aenderung_id(api)
    _lerndaten(api)
    folge = aenderungen_seit(api, a0)
    assert folge[0]["aktion"] == "mock_lerndaten"
    soll, unsicher = m31.automatische_soll(api.alle_buchungen(), "2026-11-16")
    assert soll, "Voraussetzung: die Lerndaten ergeben automatische Regeln (D-181: 16)"
    assert len(folge) == 2 and (folge[1]["quelle"], folge[1]["aktion"]) == ("lernmodell", "regel_automatisch")
    assert folge[1]["id"] == folge[0]["id"] + 1, "direkt nach der auslösenden Änderung"
    ist = m31.automatische(api)
    assert {e: r["kategorie_id"] for e, r in ist.items() if e not in unsicher} == soll
    assert {e["objekt_id"] for e in folge[1]["eintraege"]} == {r["id"] for r in ist.values()}
    assert all(e["objekt"] == "regel" and e["art"] == "angelegt" for e in folge[1]["eintraege"])
