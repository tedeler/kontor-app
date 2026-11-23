"""M3-Fixtures: Umbuchungen, Abstimmung, Aliase, Suche (ohne App).

Die Wahrheit des Generators wird mit den unabhängigen Orakeln aus
``tests/hilfen/m3_orakel.py`` und ``tests/hilfen/normal.py`` gegengeprüft.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata

import pytest

from generator.iban import ist_gueltig
from tests.hilfen import m3_orakel as orakel
from tests.hilfen.normal import ekey, norm
from tests.hilfen.pfade import FIXTURES, KMY, MOCK

pytestmark = pytest.mark.m3


def _lade(pfad):
    return json.loads(pfad.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def daten():
    return _lade(MOCK / "m3_daten.json")


@pytest.fixture(scope="module")
def erw():
    return _lade(MOCK / "m3_daten.erwartung.json")


@pytest.fixture(scope="module")
def stamm():
    return _lade(FIXTURES / "m3" / "stammdaten.json")


def _gebucht(daten):
    return [u for u in daten["bank"]["umsaetze"] if not u["vormerkung"]]


def test_format_und_synthetisch(daten, erw):
    assert daten["format"] == "kontor-mock-daten" and daten["version"] == 1
    ibans = [k["iban"] for k in daten["bank"]["konten"]]
    for i in ibans + [erw["ibans"]["fremd"]]:
        assert ist_gueltig(i) and i[4:12] == "00000000"
    ids = [u["umsatz_id"] for u in daten["bank"]["umsaetze"]]
    assert len(ids) == len(set(ids))
    for u in daten["bank"]["umsaetze"]:
        assert u["iban"] in ibans and isinstance(u["betrag"], int)
        assert u["gegenpartei_iban"] is None or ist_gueltig(u["gegenpartei_iban"])
        assert erw["von"] <= u["buchungstag"] <= erw["stufen"][-1]
    s = [(u["buchungstag"], u["umsatz_id"]) for u in daten["bank"]["umsaetze"]]
    assert s == sorted(s)
    for adr in re.findall(r"[\w.+-]+@[\w.-]+", json.dumps(daten)):
        assert adr.endswith(".invalid")
    assert erw["iban_reihenfolge"] == sorted(ibans)


def test_stoerfaelle_enthalten(daten, erw):
    namen = {(u["gegenpartei_name"] or "") for u in daten["bank"]["umsaetze"]}
    assert erw["nfd_name"] in namen and unicodedata.normalize("NFC", erw["nfd_name"]) in namen
    assert unicodedata.normalize("NFC", erw["nfd_name"]) != erw["nfd_name"]
    zwecke = " ".join(u["verwendungszweck"] for u in daten["bank"]["umsaetze"])
    assert "ß" in zwecke and "ﬁ" in zwecke and "é" in zwecke
    assert any(n != n.strip() for n in namen)
    faelle = set(erw["fall"].values())
    for f in ("umbuchung_gleicher_tag", "umbuchung_kredit_ohne_iban", "umbuchung_3_tage", "umbuchung_4_tage",
              "umbuchung_stufengrenze", "umbuchung_neben_fremd", "fremde_iban", "umbuchung_mehrdeutig",
              "umbuchung_iban_widerspruch", "umbuchung_ohne_iban", "vormerkung"):
        assert f in faelle, f


def _als_buchungen(gebucht, erw):
    """Simulierter Zustand „nur synchronisiert“: je Umsatz eine Buchung gegen „Unkategorisiert“."""
    konten = [{"id": i + 1, "art": a, "iban": iban, "extern_id": None}
              for i, (iban, a) in enumerate([(erw["ibans"]["giro"], "girokonto"), (erw["ibans"]["spar"], "sparkonto"),
                                             (erw["ibans"]["kredit"], "kreditkonto")])]
    konten.append({"id": 99, "art": "eigenkapital", "iban": None, "extern_id": "kontor:unkategorisiert"})
    kid = {k["iban"]: k["id"] for k in konten if k["iban"]}
    return konten, kid


def test_umbuchungen_gegen_orakel(daten, erw):
    """Stufe für Stufe wie bei aufeinanderfolgenden Abrufen; IDs in Verarbeitungsreihenfolge."""
    gebucht = _gebucht(daten)
    konten, kid = _als_buchungen(gebucht, erw)
    buchungen: list[dict] = []
    uid_von: dict[int, str] = {}
    naechste = [1]
    vorher = ""
    erwartet_je_stufe = erw["umbuchungen"]["je_stufe"]
    for n, stufe in enumerate(erw["stufen"]):
        gefunden = []
        for iban in erw["iban_reihenfolge"]:
            neu = []
            for u in gebucht:
                if u["iban"] == iban and vorher < u["buchungstag"] <= stufe:
                    b = {"id": naechste[0], "datum": u["buchungstag"], "status": "importiert",
                         "gegen_iban": u["gegenpartei_iban"],
                         "splits": [{"konto_id": kid[iban], "betrag": u["betrag"]},
                                    {"konto_id": 99, "betrag": -u["betrag"]}]}
                    uid_von[b["id"]] = u["umsatz_id"]
                    naechste[0] += 1
                    buchungen.append(b)
                    neu.append(b["id"])
            if not neu:
                continue
            for x, y in orakel.eindeutige_paare(buchungen, konten, erw["fenster_tage"]):
                if x in neu or y in neu:
                    gefunden.append({"behalten": uid_von[x], "entfernt": uid_von[y]})
                    bx = next(b for b in buchungen if b["id"] == x)
                    by = next(b for b in buchungen if b["id"] == y)
                    bx["splits"] = [bx["splits"][0], by["splits"][0]]
                    buchungen.remove(by)
        assert sorted(gefunden, key=str) == sorted(erwartet_je_stufe[n], key=str), stufe
        vorher = stufe
    alle = [p for s in erwartet_je_stufe for p in s]
    assert alle == erw["umbuchungen"]["endstand"]
    paarig = {u for p in alle for u in p.values()}
    assert not paarig & set(erw["umbuchungen"]["nicht_zusammengefuehrt"])


def test_umbuchungen_einmaliger_abruf(daten, erw):
    """Ein einziger Abruf bis zum Ende ergibt dieselben Paare (Ergebnis unabhängig vom Zeitpunkt)."""
    gebucht = _gebucht(daten)
    konten, kid = _als_buchungen(gebucht, erw)
    buchungen = []
    uid_von = {}
    for iban in erw["iban_reihenfolge"]:
        for u in gebucht:
            if u["iban"] == iban:
                b = {"id": len(buchungen) + 1, "datum": u["buchungstag"], "status": "importiert",
                     "gegen_iban": u["gegenpartei_iban"],
                     "splits": [{"konto_id": kid[iban], "betrag": u["betrag"]},
                                {"konto_id": 99, "betrag": -u["betrag"]}]}
                uid_von[b["id"]] = u["umsatz_id"]
                buchungen.append(b)
    ist = {frozenset((uid_von[x], uid_von[y])) for x, y in orakel.eindeutige_paare(buchungen, konten,
                                                                                    erw["fenster_tage"])}
    soll = {frozenset(p.values()) for p in erw["umbuchungen"]["endstand"]}
    assert ist == soll


def test_gruende_der_nicht_zusammenfuehrung(daten, erw):
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    f = erw["fenster_tage"]

    def gegenueber(u):
        return [v for v in alle.values() if v["betrag"] == -u["betrag"] and v["iban"] != u["iban"]
                and not v["vormerkung"]]

    def nah(u, v):
        return abs((dt.date.fromisoformat(v["buchungstag"]) - dt.date.fromisoformat(u["buchungstag"])).days) <= f

    def iban_ok(u, v):
        gu, gv = u["gegenpartei_iban"], v["gegenpartei_iban"]
        return not ((gu and gu != v["iban"]) or (gv and gv != u["iban"])) and (gu == v["iban"] or gv == u["iban"])

    for uid, grund in erw["umbuchungen"]["nicht_zusammengefuehrt"].items():
        u = alle[uid]
        partner = gegenueber(u)
        if grund == "zeitfenster":
            assert partner and not any(nah(u, v) for v in partner), uid
        elif grund == "iban":
            assert all(not iban_ok(u, v) for v in partner if nah(u, v)), uid
        else:
            assert grund == "mehrdeutig"
            passend = [v for v in partner if nah(u, v) and iban_ok(u, v)]
            assert len(passend) >= 2 or any(len([w for w in gegenueber(v) if nah(v, w) and iban_ok(v, w)]) >= 2
                                            for v in passend), uid


def test_stammdaten_wahrheit(daten, erw, stamm):
    emp = [{"name": e["name"], "aliase": e["aliase"]} for e in stamm["empfaenger"]]
    std = {e["name"]: e["standardkategorie"] for e in stamm["empfaenger"]}
    regeln = sorted(stamm["regeln"], key=lambda r: r["prioritaet"])
    for u in _gebucht(daten):
        w = erw["stammdaten"][u["umsatz_id"]]
        e = orakel.empfaenger_fuer(u["gegenpartei_name"], emp)
        name = e["name"] if e else ((u["gegenpartei_name"] or "").strip() or None)
        assert w["empfaenger"] == name and w["stamm_empfaenger"] == (e["name"] if e else None), u
        def gilt(r):
            for b in r["bedingungen"]:
                x = name if b["feld"] == "empfaenger" else u["verwendungszweck"]
                if x is None:
                    return False
                if b["operator"] == "enthaelt" and norm(b["wert"]) not in norm(x):
                    return False
                if b["operator"] == "gleich" and norm(b["wert"]) != norm(x):
                    return False
            return True
        r = next((r for r in regeln if r["aktiv"] and gilt(r)), None)
        if r:
            assert (w["kategorie"], w["quelle"], w["regel"]) == (r["kategorie"], "regel", r["name"])
        elif e and std[e["name"]]:
            assert (w["kategorie"], w["quelle"]) == (std[e["name"]], "standardkategorie")
        else:
            assert w["kategorie"] is None and w["quelle"] is None
    quellen = {w["quelle"] for w in erw["stammdaten"].values()}
    assert {"regel", "standardkategorie", None} <= quellen
    # Aliase sind eindeutig und kollidieren nicht
    schl = [ekey(a) for e in stamm["empfaenger"] for a in e["aliase"]]
    assert len(schl) == len(set(schl)) and all(schl)


def test_auszuege(daten, erw):
    gebucht = _gebucht(daten)
    for a in erw["auszuege"]:
        assert a["saldo"] == sum(u["betrag"] for u in gebucht if u["iban"] == a["iban"]
                                 and u["buchungstag"] <= a["stichtag"])
    for f in erw["auszuege_falsch"]:
        richtig = next(a for a in erw["auszuege"] if a["iban"] == f["iban"] and a["stichtag"] == f["stichtag"])
        assert f["saldo"] - richtig["saldo"] == f["differenz"] != 0
    for iban in erw["ibans"].values():
        if iban == erw["ibans"]["fremd"]:
            continue
        assert sum(a["neue_splits"] for a in erw["auszuege"] if a["iban"] == iban) == erw["anzahl_gebucht"][iban]


def test_suche_gegen_orakel(daten, erw):
    s = _lade(FIXTURES / "m3" / "suche.json")
    gebucht = _gebucht(daten)
    namen = sorted({(u["gegenpartei_name"] or "").strip() for u in gebucht} - {""})
    kontonamen = list(erw["konto_namen"].values()) + ["Unkategorisiert"]
    for a in s["anfragen"]:
        q = a["q"]
        felder = {u["umsatz_id"]: [u["verwendungszweck"], erw["konto_namen"][u["iban"]], "Unkategorisiert",
                                   (u["gegenpartei_name"] or "").strip()] for u in gebucht}
        assert set(a["buchungen"]) == {uid for uid, f in felder.items() if orakel.trifft(q, f)}, q
        assert a["empfaenger"] == sorted(n for n in namen if orakel.trifft(q, [n])), q
        assert a["konten"] == sorted(n for n in kontonamen if orakel.trifft(q, [n])), q
        tage = [next(u["buchungstag"] for u in gebucht if u["umsatz_id"] == uid) for uid in a["buchungen"]]
        assert tage == sorted(tage, reverse=True)
    beispiele = {a["q"]: a for a in s["anfragen"]}
    assert len(beispiele["bäckerei"]["buchungen"]) == 6, "auch NFD- und ausgeschriebene Schreibweisen"
    assert beispiele["STRAßE"]["buchungen"] == beispiele["strasse"]["buchungen"]
    assert beispiele["gibtsnicht"]["buchungen"] == []
    assert orakel.snorm("Bäckerei") == orakel.snorm("BAECKEREI") == "baeckerei"
    assert orakel.snorm("Café") == "cafe" and orakel.snorm("Straße") == "strasse"


def test_alias_buch(stamm):
    e = _lade(KMY / "m3_aliase.erwartung.json")
    emp = [{"name": x["name"], "aliase": x["aliase"]} for x in stamm["empfaenger"]]
    for p in e["empfaenger"]:
        z = e["alias_zuordnung"][p["extern_id"].removeprefix("kmy:")]
        treffer = orakel.empfaenger_fuer(p["name"], emp)
        if z["regel"] == "neu":
            assert treffer is None and z["empfaenger"] == p["name"]
        else:
            assert treffer is not None and treffer["name"] == z["empfaenger"]
            assert (treffer["name"] == p["name"]) == (z["regel"] == "name")
