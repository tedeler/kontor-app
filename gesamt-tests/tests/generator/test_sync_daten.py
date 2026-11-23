"""M2-Fixtures: Mock-Bankdaten für die Synchronisation, Regelsatz, Altbestand (ohne App).

Die von Hand konstruierte Wahrheit des Generators (Regelergebnis, Abgleich mit
dem Altbestand) wird hier mit dem unabhängigen Orakel ``tests/hilfen/sync_orakel``
gegengeprüft.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter

import pytest

from generator.iban import ist_gueltig
from tests.hilfen import sync_orakel as orakel
from tests.hilfen.pfade import FIXTURES, KMY, MOCK

pytestmark = pytest.mark.m2


def _lade(pfad):
    return json.loads(pfad.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def daten():
    return _lade(MOCK / "sync_daten.json")


@pytest.fixture(scope="module")
def erw():
    return _lade(MOCK / "sync_daten.erwartung.json")


@pytest.fixture(scope="module")
def regeln():
    return _lade(FIXTURES / "sync" / "regeln.json")


def test_format_und_synthetisch(daten, erw):
    assert daten["format"] == "kontor-mock-daten" and daten["version"] == 1
    ibans = [k["iban"] for k in daten["bank"]["konten"]]
    assert len(set(ibans)) == 3
    assert {k["art"] for k in daten["bank"]["konten"]} == {"girokonto", "sparkonto", "kreditkonto"}
    for i in ibans + [erw["ibans"]["fremd"]]:
        assert ist_gueltig(i) and i[4:12] == "00000000"
    ids = [u["umsatz_id"] for u in daten["bank"]["umsaetze"]]
    assert len(ids) == len(set(ids))
    pflicht = {"umsatz_id", "iban", "buchungstag", "valuta", "betrag", "waehrung", "gegenpartei_name",
               "gegenpartei_iban", "verwendungszweck", "vormerkung", "storno"}
    for u in daten["bank"]["umsaetze"]:
        assert set(u) == pflicht and u["iban"] in ibans and isinstance(u["betrag"], int)
        assert u["waehrung"] == "EUR" and dt.date.fromisoformat(u["buchungstag"])
        assert u["gegenpartei_iban"] is None or ist_gueltig(u["gegenpartei_iban"])
    s = [(u["buchungstag"], u["umsatz_id"]) for u in daten["bank"]["umsaetze"]]
    assert s == sorted(s)
    for adr in re.findall(r"[\w.+-]+@[\w.-]+", json.dumps(daten)):
        assert adr.endswith("example.invalid"), adr
    assert set(erw["wahre_kategorie"]) == set(ids) == set(erw["regel_ergebnis"]) == set(erw["abgleich_altbestand"])


def test_stoerfaelle_vorhanden(daten, erw):
    us = daten["bank"]["umsaetze"]
    assert len(erw["vormerkungen"]) >= 2 and erw["stornos"]
    assert any(u["gegenpartei_name"] is None for u in us)
    assert any(u["gegenpartei_name"] and u["gegenpartei_name"] != u["gegenpartei_name"].strip() for u in us)
    assert any(u["verwendungszweck"] == "" for u in us)
    assert any(len(u["verwendungszweck"]) > 500 for u in us)
    assert any(u["betrag"] == 0 for u in us)
    assert any(re.search("[äöüÄÖÜß]", u["gegenpartei_name"] or "") for u in us)
    paare = Counter((u["iban"], u["buchungstag"], u["betrag"], u["gegenpartei_name"]) for u in us if not u["vormerkung"])
    assert any(n >= 2 for n in paare.values()), "zweimal derselbe Kaffee fehlt"
    # eine Vormerkung, die später gebucht erscheint
    vm = [u for u in us if u["vormerkung"]]
    assert any(any(g["betrag"] == v["betrag"] and g["iban"] == v["iban"] and not g["vormerkung"]
                   and g["buchungstag"] > v["buchungstag"] for g in us) for v in vm)
    for st in erw["stufen"]:
        dt.date.fromisoformat(st)
    assert erw["stufen"] == sorted(erw["stufen"])


def test_pin_datei_gleich_bis_auf_pin(daten, erw):
    mit = _lade(MOCK / "sync_daten_pin.json")
    assert mit["bank"]["pin"] == erw["pin"]
    ohne = {**mit, "bank": {k: v for k, v in mit["bank"].items() if k != "pin"}}
    assert ohne == daten
    assert "pin" not in daten["bank"] and daten["bank"]["tan"] == erw["tan"]
    roh = (MOCK / "sync_daten.json").read_text(encoding="utf-8")
    assert erw["pin"] not in roh, "Die PIN darf nur in der PIN-Datei stehen"
    assert len(erw["pin"]) >= 12 and len(erw["tan"]) >= 8, "PIN/TAN müssen eindeutig auffindbar sein"


def _aufgeloest(regeln, ids_konten: dict[str, int], ids_kat: dict[str, int]) -> list[dict]:
    aus = []
    for n, r in enumerate(regeln["regeln"], start=1):
        bed = [{**b, "wert": ids_konten[b["wert"]["iban"]]} if b["feld"] == "konto_id" else b
               for b in r["bedingungen"]]
        aus.append({"id": n, "name": r["name"], "aktiv": r["aktiv"], "prioritaet": r["prioritaet"],
                    "kategorie_id": ids_kat[r["kategorie"]], "bedingungen": bed})
    return aus


def test_regelergebnis_stimmt_mit_orakel(daten, erw, regeln):
    ids_konten = {k["iban"]: 100 + n for n, k in enumerate(regeln["konten"])}
    ids_kat = {k["name"]: 200 + n for n, k in enumerate(regeln["kategorien"])}
    rs = _aufgeloest(regeln, ids_konten, ids_kat)
    nach_name = {r["name"]: r for r in rs}
    for u in daten["bank"]["umsaetze"]:
        if u["vormerkung"]:
            assert erw["regel_ergebnis"][u["umsatz_id"]] is None
            continue
        r = orakel.regel_fuer(rs, orakel.sicht_umsatz(u, ids_konten[u["iban"]]))
        soll = erw["regel_ergebnis"][u["umsatz_id"]]
        assert (r["name"] if r else None) == (soll["regel"] if soll else None), u["umsatz_id"]
        if soll:
            assert nach_name[soll["regel"]]["kategorie_id"] == ids_kat[soll["kategorie"]]
            assert soll["kategorie"] == erw["wahre_kategorie"][u["umsatz_id"]], "Regeltreffer ≠ Wahrheit"


def test_regelsatz_deckt_prioritaetsfaelle_ab(daten, erw, regeln):
    rs = regeln["regeln"]
    assert any(not r["aktiv"] for r in rs)
    prios = Counter(r["prioritaet"] for r in rs if r["aktiv"])
    assert any(n >= 2 for n in prios.values()), "Gleichstand der Priorität fehlt"
    # eine später angelegte Regel mit kleinerer Priorität gewinnt
    assert any(rs[j]["prioritaet"] < rs[i]["prioritaet"] for i in range(len(rs)) for j in range(i + 1, len(rs))
               if rs[i]["aktiv"] and rs[j]["aktiv"])
    felder = {(b["feld"], b["operator"]) for r in rs for b in r["bedingungen"]}
    for f in [("empfaenger", "enthaelt"), ("empfaenger", "gleich"), ("empfaenger", "beginnt_mit"),
              ("verwendungszweck", "enthaelt"), ("verwendungszweck", "beginnt_mit"), ("betrag", "gleich"),
              ("betrag", "mindestens"), ("betrag", "hoechstens"), ("konto_id", "gleich")]:
        assert f in felder, f
    getroffen = Counter(v["regel"] for v in erw["regel_ergebnis"].values() if v)
    assert all(getroffen[r["name"]] > 0 for r in rs if r["aktiv"] and "verliert" not in r["name"]), getroffen
    assert sum(v is None for k, v in erw["regel_ergebnis"].items() if k not in erw["vormerkungen"]) >= 5


def test_abgleich_altbestand_stimmt_mit_orakel(daten, erw):
    kmy = _lade(KMY / "sync_altbestand.erwartung.json")
    konto_ext = {k["iban"]: k["extern_id"] for k in kmy["konten"] if k["iban"]}
    kandidaten = [orakel.Kandidat(b["extern_id"][4:], b["datum"], b["empfaenger"],
                                  [(s["konto_extern_id"], s["betrag"]) for s in b["splits"]])
                  for b in kmy["buchungen"]]
    ist: dict[str, dict] = {}
    for k in daten["bank"]["konten"]:
        us = [u for u in daten["bank"]["umsaetze"] if u["iban"] == k["iban"] and not u["vormerkung"]]
        if k["iban"] in konto_ext:
            ist.update(orakel.abgleich(us, konto_ext[k["iban"]], kandidaten))
        else:
            ist.update({u["umsatz_id"]: {"ergebnis": "neu"} for u in us})
    for v in erw["vormerkungen"]:
        ist[v] = {"ergebnis": "vormerkung"}
    assert ist == erw["abgleich_altbestand"]
    arten = Counter((v["ergebnis"], v.get("grund")) for v in ist.values())
    for a in [("zusammengefuehrt", None), ("zur_pruefung", "mehrdeutig"), ("zur_pruefung", "aehnlich"), ("neu", None)]:
        assert arten[a] > 0, a
    # beide Seiten einer Umbuchung mit derselben KMyMoney-Buchung
    mit = Counter(v["mit"][0] for v in ist.values() if v["ergebnis"] == "zusammengefuehrt")
    assert any(n == 2 for n in mit.values())


def test_altbestand_nur_bis_stichtag(erw):
    kmy = _lade(KMY / "sync_altbestand.erwartung.json")
    assert max(b["datum"] for b in kmy["buchungen"]) <= erw["altbestand_bis"]
    ibans = {k["iban"] for k in kmy["konten"] if k["iban"]}
    assert ibans == {erw["ibans"]["giro"], erw["ibans"]["spar"]}, "Kreditkarte darf nur bei der Bank existieren"
