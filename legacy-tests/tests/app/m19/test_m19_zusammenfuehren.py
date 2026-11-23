"""M19: Kategorien zusammenführen (alfbanco.md 5, 6; E-213).

Die erwartete Wirkung berechnet ``tests/hilfen/m19.zusammenfuehren_soll`` je Quelle mit dem Orakel für das Löschen
mit Buchungen (``loeschen_orakel``) und dem gewählten Ziel; nie aus Antworten der Anwendung.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m4 import vorlage
from tests.hilfen.m5 import Kreditbuch
from tests.hilfen.m18 import bestand, ohne_wirkung, pruefe_eintraege
from tests.hilfen.m19 import (
    erfolg, ist_zusammengefuehrt, kategorie, ohne_listen, qif, zusammenfuehren, zusammenfuehren_soll,
)

pytestmark = pytest.mark.kern


def _aufbau(api) -> dict:
    """Quellen Q1 (aufwand, zwei Unterkategorien, Regel, Vorlage, alf-Kennung) und Q2 (ertrag,
    eine Unterkategorie), Ziel Z (aufwand, ohne Kennung), dazu Buchungen aller Fälle."""
    g = api.konto("Girokonto")["id"]
    # Q1 mit alf-Kennung aus einem Import (Pfad „Alt“, Unterkategorien kommen aus der Datei)
    erfolg(api, g, qif(["!Type:Bank", ["D01.01.2024", "T-1,00", "LAlt:Eins", "MImport Eins"],
                        ["D01.01.2024", "T-2,00", "LAlt:Zwei", "MImport Zwei"],
                        ["D01.01.2024", "T-3,00", "LAlt", "MImport Alt"]]))
    q1 = kategorie(api, "alf:kat:Alt")["id"]
    c1, c2 = kategorie(api, "alf:kat:Alt:Eins")["id"], kategorie(api, "alf:kat:Alt:Zwei")["id"]
    q2 = api.konto("Nebeneinnahmen", "ertrag")["id"]
    c3 = api.konto("Flohmarkt", "ertrag", eltern_id=q2)["id"]
    z = api.konto("Haushalt", "aufwand")["id"]
    andere = api.konto("Freizeit", "aufwand")["id"]
    emp = api.empfaenger("Laden Beispiel")["id"]   # ab M32 ohne Standardkategorie (sammel3.md 2.1, E-307)
    b = {
        "nur_q1": api.buchung("2024-02-01", [(g, -500), (q1, 500, "a")], empfaenger_id=emp)["id"],
        "q1_und_z": api.buchung("2024-02-02", [(g, -500), (q1, 300, "Brot"), (z, 200, "Milch")])["id"],
        "q2": api.buchung("2024-02-03", [(g, 800), (q2, -800, "Verkauf")])["id"],
        "konflikt": api.buchung("2024-02-04", [(q1, 400, "hin"), (z, -400, "her")])["id"],
        "beide": api.buchung("2024-02-05", [(g, -100), (q1, 50), (q2, 50)])["id"],
        "fremd": api.buchung("2024-02-06", [(g, -900), (andere, 900)])["id"],
    }
    regel = api.post("/api/regeln", json={"name": "Laden", "kategorie_id": q1, "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "laden"}]}, erwartet=201).daten["id"]
    vl = vorlage(api, "Sammel", "Laden Beispiel", [(q1, 300), (andere, 200)])["id"]
    return {"g": g, "q1": q1, "q2": q2, "c1": c1, "c2": c2, "c3": c3, "z": z, "andere": andere, "emp": emp,
            "b": b, "regel": regel, "vorlage": vl}


def _fuehre_aus(api, quellen, ziel, **felder) -> tuple[dict, dict, dict, dict]:
    soll = zusammenfuehren_soll(api, quellen, ziel, loeschen=felder.get("quellen_loeschen", True))
    v, a0 = bestand(api), letzte_aenderung_id(api)
    salden = {k: x["saldo"] for k, x in api.salden().items()}
    erg = zusammenfuehren(api, quellen, ziel, **felder).daten
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "kategorien_zusammenfuehren", None)
    assert erg["aenderung_id"] == a["id"] and erg["trocken"] is False
    n = bestand(api)
    pruefe_eintraege(a, v, n)
    return erg, soll, {"v": v, "n": n, "a": a}, salden


# ------------------------------------------------------------------ Validierung und Prüfreihenfolge (5.1, 5.2)


@pytest.mark.parametrize("koerper", [
    {}, {"quelle_ids": [1]}, {"ziel_id": 1}, {"quelle_ids": [], "ziel_id": 1}, {"quelle_ids": [2, 2], "ziel_id": 1},
    {"quelle_ids": list(range(2, 1003)), "ziel_id": 1}, {"quelle_ids": [2], "ziel_id": True},
    {"quelle_ids": [True], "ziel_id": 1}, {"quelle_ids": "2", "ziel_id": 1}, {"quelle_ids": [2], "ziel_id": "1"},
    {"quelle_ids": [2], "ziel_id": 1, "trocken": "ja"}, {"quelle_ids": [2], "ziel_id": 1, "x": 1},
    {"quelle_ids": [2], "ziel_id": 1, "quellen_loeschen": None}, {"quelle_ids": [2.0], "ziel_id": 1}, [1],
], ids=lambda k: str(k)[:40])
def test_validierung(api, koerper):
    ohne_wirkung(api, lambda: _code(api.post("/api/kategorien/zusammenfuehren", json=koerper, erwartet=422),
                                    "validierung"))


def _code(r, code):
    assert fehlercode(r) == code, r.text[:300]
    return r.json()["fehler"]["details"]


def test_pruefreihenfolge(api):
    x = _aufbau(api)
    q1, q2, z, g = x["q1"], x["q2"], x["z"], x["g"]
    ek = api.konto("Eigenkapital", "eigenkapital")["id"]

    def faelle():
        # 2 vor 3: Ziel unter den Quellen, auch mit unbekannten IDs
        _code(zusammenfuehren(api, [q1, 999999, z], z, erwartet=422), "ziel_ungueltig")
        # 3: alle unbekannten, aufsteigend; vor 4
        assert _code(zusammenfuehren(api, [999998, g, 999990], 999999, erwartet=422),
                     "referenz_unbekannt") == {"konto_ids": [999990, 999998, 999999]}
        # 4: keine Kategorien, aufsteigend
        assert _code(zusammenfuehren(api, [ek, q1, g], z, erwartet=422), "konto_ungueltig") == {
            "konto_ids": sorted([ek, g])}
        assert _code(zusammenfuehren(api, [q1], g, erwartet=422), "konto_ungueltig") == {"konto_ids": [g]}
    ohne_wirkung(api, faelle)
    assert q2


def test_kreditbezug_nur_beim_loeschen(api):
    kr = Kreditbuch(api)
    kid = kr.anlegen().daten["id"]
    z = api.konto("Ziel", "aufwand")["id"]
    for trocken in (False, True):
        ohne_wirkung(api, lambda: _pruefe_kredit(api, kr.zinsen, z, kid, trocken))
    # ohne Löschen kein Kreditbezug-Fehler
    e = zusammenfuehren(api, [kr.zinsen], z, quellen_loeschen=False).daten
    assert e["quellen_geloescht"] is False


def _pruefe_kredit(api, quelle, ziel, kid, trocken):
    d = _code(zusammenfuehren(api, [quelle], ziel, trocken=trocken, erwartet=409), "konto_in_verwendung")
    assert d == {"kredit_ids": [kid]}


def test_gesperrte_buchungen(api):
    x = _aufbau(api)
    q1, z = x["q1"], x["z"]
    gesp = x["b"]["nur_q1"]
    api.patch(f"/api/buchungen/{gesp}", json={"status": "abgeglichen"}, erwartet=200)
    ohne_wirkung(api, lambda: _gesperrt(api, q1, z, gesp))
    # Probelauf: kein 409, gesperrte stehen in gesperrt
    v = bestand(api)
    t = zusammenfuehren(api, [q1], z, trocken=True).daten
    assert t["gesperrt"] == [gesp] and t["trocken"] is True and t["aenderung_id"] is None
    assert bestand(api) == v
    e = zusammenfuehren(api, [q1], z, gesperrte_einbeziehen=True).daten
    assert e["gesperrt"] == [gesp] and ohne_listen(e) == ohne_listen(t)
    b = api.buchung_lesen(gesp)
    assert b["status"] == "abgeglichen" and z in [s["konto_id"] for s in b["splits"]], "gesperrte umgebucht"


def _gesperrt(api, q, z, gesp):
    assert _code(zusammenfuehren(api, [q], z, erwartet=409), "buchung_gesperrt") == {"buchung_ids": [gesp]}


# ------------------------------------------------------------------ Wirkung (5.3, 5.4)


def test_mit_loeschen_gegen_orakel(api):
    x = _aufbau(api)
    q1, q2, z = x["q1"], x["q2"], x["z"]
    erg, soll, p, salden = _fuehre_aus(api, [q1, q2], z)
    assert ohne_listen(erg) == soll["antwort"]
    assert {x["b"][k] for k in ("nur_q1", "q1_und_z", "q2", "konflikt", "beide")} <= set(erg["buchungen_umgebucht"])
    assert x["b"]["fremd"] not in erg["buchungen_umgebucht"]
    assert erg["konfliktbuchungen"] == [x["b"]["konflikt"]]
    assert erg["unterkategorien_verschoben"] == sorted([x["c1"], x["c2"]]), "gleiche Art: unter das Ziel"
    assert erg["regeln_geaendert"] == [x["regel"]]
    assert erg["empfaenger_geaendert"] == [], "ab M32 ohne Standardkategorie (sammel3.md 2.1, W-030/E-314)"
    assert erg["extern_id_uebernommen"] == "alf:kat:Alt"
    ist_zusammengefuehrt(api, soll)
    konten = {k["id"]: k for k in api.konten()}
    assert q1 not in konten and q2 not in konten
    assert konten[x["c3"]]["eltern_id"] is None, "andere Art (ertrag → aufwand): eine Ebene nach oben"
    b = api.buchung_lesen(x["b"]["q1_und_z"])
    assert [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"] if s["konto_id"] == z] == [
        (z, 500, "Brot / Milch")] or [(s["konto_id"], s["betrag"]) for s in b["splits"] if s["konto_id"] == z] == [
        (z, 500)], "freie Splits auf dem Ziel zusammengefasst"
    vl = next(v for v in api.get("/api/vorlagen", erwartet=200).daten if v["id"] == x["vorlage"])
    assert vl["teile"][0]["kategorie_id"] == z, "Split-Vorlagen auf das Ziel umgestellt"
    # Salden: Ziel bekommt die eigenen Salden der Quellen, alle anderen unverändert
    neu = {k: v["saldo"] for k, v in api.salden().items()}
    assert neu[z] == salden[z] + salden[q1] + salden[q2]
    for k, v in neu.items():
        if k != z:
            assert v == salden[k], k
    assert sum(neu.values()) == 0
    # Rückgängig stellt den Zustand exakt her, Wiederholen wieder den neuen
    u = api.post(f"/api/aenderungen/{p['a']['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == p["v"]
    pruefe_eintraege(u, p["n"], p["v"])
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == p["n"]


def test_ohne_loeschen(api):
    x = _aufbau(api)
    q1, q2, z = x["q1"], x["q2"], x["z"]
    konten_vorher = {k["id"]: k for k in api.konten()}
    regeln_vorher = api.get("/api/regeln", erwartet=200).daten
    erg, soll, p, _ = _fuehre_aus(api, [q2, q1], z, quellen_loeschen=False)
    assert ohne_listen(erg) == {**soll["antwort"], "regeln_geaendert": [], "empfaenger_geaendert": [],
                                "unterkategorien_verschoben": [], "extern_id_uebernommen": None}
    assert erg["quelle_ids"] == [q2, q1], "Reihenfolge erhalten"
    assert {k["id"]: k for k in api.konten()} == konten_vorher, "Quellen, Unterkategorien, extern_id unverändert"
    assert api.get("/api/regeln", erwartet=200).daten == regeln_vorher
    assert api.alle_buchungen(konto_id=q1) == [] and api.alle_buchungen(konto_id=q2) == []
    assert {b["id"]: b for b in api.alle_buchungen()}.keys() == soll["buchungen"].keys()


def test_ziel_ist_unterkategorie_der_quelle(api):
    x = _aufbau(api)
    q1, c1, c2 = x["q1"], x["c1"], x["c2"]
    erg, soll, _, _ = _fuehre_aus(api, [q1], c1)
    assert erg["unterkategorien_verschoben"] == [], "Ziel ist Nachfahre: Unterkategorien rücken nach oben"
    konten = {k["id"]: k for k in api.konten()}
    assert konten[c1]["eltern_id"] is None and konten[c2]["eltern_id"] is None
    ist_zusammengefuehrt(api, soll)


def test_einnahme_in_ausgabe(api):
    x = _aufbau(api)
    erg, soll, _, _ = _fuehre_aus(api, [x["q2"]], x["andere"])
    assert erg["unterkategorien_verschoben"] == [] and erg["extern_id_uebernommen"] is None
    ist_zusammengefuehrt(api, soll)


def test_probelauf_gleich_echtem_lauf(api):
    x = _aufbau(api)
    v, a0 = bestand(api), letzte_aenderung_id(api)
    t = zusammenfuehren(api, [x["q1"], x["q2"]], x["z"], trocken=True).daten
    assert (t["trocken"], t["aenderung_id"]) == (True, None)
    assert bestand(api) == v and aenderungen_seit(api, a0) == []
    e = zusammenfuehren(api, [x["q1"], x["q2"]], x["z"]).daten
    assert ohne_listen(t) == ohne_listen(e)


def test_ohne_wirkung_keine_aenderung(api):
    """5.4: aenderung_id null, wenn sich nichts geändert hat (Quellen ohne Buchungen, ohne Löschen)."""
    q = api.konto("Leer", "aufwand")["id"]
    z = api.konto("Ziel", "aufwand")["id"]
    a0 = letzte_aenderung_id(api)
    e = zusammenfuehren(api, [q], z, quellen_loeschen=False).daten
    assert e["aenderung_id"] is None and e["buchungen_umgebucht"] == [] and aenderungen_seit(api, a0) == []


def test_extern_id_uebernahme_und_spaeterer_import(api):
    x = _aufbau(api)
    q1, z, g = x["q1"], x["z"], x["g"]
    zusammenfuehren(api, [q1], z)
    assert kategorie(api, "alf:kat:Alt")["id"] == z
    e = erfolg(api, g, qif(["!Type:Bank", ["D01.03.2024", "T-7,00", "LAlt", "MNach dem Zusammenführen"]]))
    assert (e["kategorien_neu"], e["kategorien_vorhanden"]) == (0, 1), "Regel 1: Pfad über die Kennung dem Ziel"
    b = next(b for b in api.alle_buchungen() if b["verwendungszweck"] == "Nach dem Zusammenführen")
    assert z in [s["konto_id"] for s in b["splits"]]


def test_rueckgaengig_abgelehnt_wenn_spaetere_aenderung_aufbaut(api):
    x = _aufbau(api)
    a0 = letzte_aenderung_id(api)
    zusammenfuehren(api, [x["q1"]], x["z"])
    (a,) = aenderungen_seit(api, a0)
    api.patch(f"/api/buchungen/{x['b']['nur_q1']}", json={"verwendungszweck": "später geändert"}, erwartet=200)
    ohne_wirkung(api, lambda: _code(api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=409),
                                    "rueckgaengig_konflikt"))
