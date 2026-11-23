"""M4-Fixtures: GnuCash-Dateien, Lerndaten, Split-Vorlagen (ohne App).

Die Wahrheit des Generators wird gegen die erzeugten Dateien (unabhängiger
Leser ``tests/hilfen/gnc_leser.py``) und gegen unabhängige Orakel
(``tests/hilfen/lern_orakel.py``, ``tests/hilfen/m4.py``) geprüft.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction

import pytest

from generator.iban import ist_gueltig
from tests.hilfen import gnc_leser
from tests.hilfen.lern_orakel import bewerte, merkmale
from tests.hilfen.m4 import GNC, LERN_MOCK, M4, VORLAGEN_MOCK, erkenne, lade
from tests.hilfen.pfade import KMY, MOCK

pytestmark = pytest.mark.m4

GUELTIG = ["minimal", "minimal_unkomprimiert", "minimal.sqlite", "sonderfaelle", "sonderfaelle.sqlite", "standard"]
FORMAT = {"minimal": "gnc-xml-gzip", "minimal_unkomprimiert": "gnc-xml", "minimal.sqlite": "gnc-sqlite",
          "sonderfaelle": "gnc-xml", "sonderfaelle.sqlite": "gnc-sqlite", "standard": "gnc-xml-gzip"}
DEFEKT = ["leer", "leer_gzip", "abgeschnitten", "kaputtes_xml", "kein_xml", "kmy_datei", "zwei_buecher", "entitaeten",
          "inhalt_ungueltig", "betrag_ungueltig", "datum_ungueltig", "pflichtfeld_fehlt", "split_auf_wurzel",
          "eltern_unbekannt", "sqlite_kaputt", "sqlite_fremd", "sqlite_zwei_buecher", "sqlite_inhalt_ungueltig"]


def _bytes(name: str) -> bytes:
    return (GNC / f"{name}.gnucash").read_bytes()


def test_alle_gnucash_fixtures_haben_erwartung():
    dateien = {p.name[: -len(".gnucash")] for p in GNC.glob("*.gnucash")}
    assert dateien == set(GUELTIG) | set(DEFEKT) | {"ueberlappung.sqlite", "m4_lernen_training"}
    for n in dateien - {"m4_lernen_training"}:
        e = lade(GNC / f"{n.replace('.sqlite', '') if n == 'ueberlappung.sqlite' else n}.erwartung.json")
        assert e["art"] == "gnucash"


@pytest.mark.parametrize("name", GUELTIG)
def test_format_der_datei(name):
    d = _bytes(name)
    fmt = FORMAT[name]
    assert lade(GNC / f"{name}.erwartung.json")["ergebnis"]["format"] == fmt
    if fmt == "gnc-xml-gzip":
        assert d[:2] == b"\x1f\x8b" and d[4:8] == b"\x00\x00\x00\x00"
        d = gzip.decompress(d)
    if fmt == "gnc-sqlite":
        assert d[:16] == b"SQLite format 3\x00"
        con = sqlite3.connect(":memory:")
        con.deserialize(d)
        assert con.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert {"books", "accounts", "transactions", "splits", "commodities", "slots"} <= {
            r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    else:
        w = ET.fromstring(d)
        assert w.tag == "gnc-v2" and len(w.findall("{http://www.gnucash.org/XML/gnc}book")) == 1
        assert b"<!DOCTYPE" not in d and b"<!ENTITY" not in d


@pytest.mark.parametrize("name", GUELTIG)
def test_datei_entspricht_wahrheit(name):
    """Buchungen der Datei (unabhängig gelesen) = Erwartung: GUID, Datum, Empfänger, Notiz, Beträge."""
    erw = lade(GNC / f"{name}.erwartung.json")
    buch = gnc_leser.lies(_bytes(name))
    gebucht = {b["extern_id"]: b for b in erw["buchungen"]}
    uebersprungen = {w["referenz"] for w in erw["warnungen"] if w["code"] == "buchung_uebersprungen"}
    assert len(buch["buchungen"]) == erw["summen"]["anzahl_transaktionen_in_datei"]
    assert len(gebucht) + len(uebersprungen) == len(buch["buchungen"])
    for t in buch["buchungen"]:
        if t["guid"] in uebersprungen:
            continue
        b = gebucht["gnc:" + t["guid"]]
        d = t["datum"]
        datum = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"[0-9]{14}", d) else d[:10]
        assert b["datum"] == datum
        assert b["empfaenger"] == ((t["beschreibung"] or "").strip() or None)
        assert b["verwendungszweck"] == (t["notiz"] or "")
        werte = [s["wert"] * 100 for s in t["splits"]]
        assert all(w.denominator == 1 for w in werte)
        assert [s["betrag"] for s in b["splits"][: len(werte)]] == [int(w) for w in werte]
        assert [s["konto_extern_id"] for s in b["splits"][: len(werte)]] == ["gnc:" + s["konto"] for s in t["splits"]]
        if len(b["splits"]) > len(werte):
            assert b["splits"][-1]["konto_extern_id"] == "kontor:unausgeglichen"
            assert sum(s["betrag"] for s in b["splits"]) == 0
    konten = {k["extern_id"]: k for k in erw["konten"]}
    for k in buch["konten"]:
        e = konten.get("gnc:" + k["guid"])
        if e is None:
            assert any(w["referenz"] == k["guid"] and w["code"] in ("konto_uebersprungen", "fremdwaehrung")
                       for w in erw["warnungen"]), k
            continue
        assert e["name"] == k["name"] and e["geschlossen"] == k["versteckt"] and e["notiz"] == k["beschreibung"]
        if e["iban"]:
            assert ist_gueltig(e["iban"]) and e["iban"] == k["code"].replace(" ", "").upper()


def test_xml_und_sqlite_gleicher_inhalt():
    for name in ("minimal", "sonderfaelle"):
        a = lade(GNC / f"{name}.erwartung.json")
        b = lade(GNC / f"{name}.sqlite.erwartung.json")
        for feld in ("konten", "empfaenger", "buchungen", "warnungen", "summen"):
            assert a[feld] == b[feld], (name, feld)
        assert {**a["ergebnis"], "format": None} == {**b["ergebnis"], "format": None}
    assert lade(GNC / "minimal_unkomprimiert.erwartung.json")["buchungen"] == lade(GNC / "minimal.erwartung.json")[
        "buchungen"]


def test_sonderfaelle_decken_alles_ab():
    e = lade(GNC / "sonderfaelle.erwartung.json")
    codes = Counter(w["code"] for w in e["warnungen"])
    for c in ("kontoart_ersetzt", "konto_uebersprungen", "fremdwaehrung", "hierarchie_angepasst", "iban_ungueltig",
              "iban_doppelt", "buchung_uebersprungen", "buchung_ausgeglichen"):
        assert codes[c] >= 1, c
    assert max(len(b["splits"]) for b in e["buchungen"]) > 10
    assert any(b["empfaenger"] is None for b in e["buchungen"])
    assert any(len(b["verwendungszweck"]) > 1000 for b in e["buchungen"])
    assert any(k["geschlossen"] for k in e["konten"])
    tief = {k["extern_id"]: k["eltern_extern_id"] for k in e["konten"]}
    assert max(_tiefe(tief, k) for k in tief) >= 3
    assert any(re.fullmatch(r"[0-9]{14}", t["datum"]) for t in gnc_leser.lies(_bytes("sonderfaelle.sqlite"))["buchungen"])
    assert b"template-transactions" in _bytes("sonderfaelle")


def _tiefe(eltern: dict, k: str) -> int:
    n = 0
    while eltern.get(k):
        k, n = eltern[k], n + 1
    return n


@pytest.mark.parametrize("name", DEFEKT)
def test_stoerfaelle(name):
    e = lade(GNC / f"{name}.erwartung.json")
    assert e["erfolgreich"] is False and e["fehler_code"] in (
        "import_datei_leer", "import_format_ungueltig", "import_datei_beschaedigt", "import_inhalt_ungueltig")
    d = _bytes(name)
    if name.startswith("sqlite"):
        assert d[:16] == b"SQLite format 3\x00" and e["format"] == "gnc-sqlite"
    if e["fehler_code"] == "import_inhalt_ungueltig":
        assert e["referenzen"], "Inhaltsfehler brauchen erwartete Referenzen"


def test_sqlite_kaputt_ist_unlesbar():
    con = sqlite3.connect(":memory:")
    with pytest.raises(sqlite3.DatabaseError):
        con.deserialize(_bytes("sqlite_kaputt"))
        con.execute("SELECT name FROM sqlite_master").fetchall()


# ------------------------------------------------------------ Überlappung
@pytest.fixture(scope="module")
def ueber():
    return lade(GNC / "ueberlappung.erwartung.json")


def test_ueberlappung_ueberschneidet_kmy(ueber):
    kmy = lade(KMY / "standard_bis_2023.erwartung.json")
    voll = lade(KMY / "standard.erwartung.json")
    daten = sorted(b["datum"] for b in ueber["buchungen"])
    assert daten[0] >= "2023-03-01" and daten[-1] <= "2024-12-31" and daten[0] <= "2023-12-31"
    ids_kmy = {b["extern_id"] for b in kmy["buchungen"]}
    ids_voll = {b["extern_id"] for b in voll["buchungen"]}
    quellen = {"kmy:" + b["quelle"] for b in ueber["buchungen"]}
    assert quellen <= ids_voll
    assert len(quellen & ids_kmy) > 100, "zu wenig Überschneidung"
    assert quellen | ids_kmy == ids_voll, "KMyMoney bis 2023 und GnuCash ab März 2023 ergeben das ganze Buch"


def test_ueberlappung_dubletten_wahrheit(ueber):
    """Zusammengeführte gehören zu ihrer Quelle, Verdachte enthalten die wahre Quelle, Zählungen stimmen."""
    n = ueber["nach_kmy"]
    quelle = {b["extern_id"]: "kmy:" + b["quelle"] for b in ueber["buchungen"]}
    kmy = {b["extern_id"] for b in lade(KMY / "standard_bis_2023.erwartung.json")["buchungen"]}
    for g, k in n["zusammengefuehrt"].items():
        assert quelle[g] == k
    for v in n["verdacht"]:
        assert v["wahr"] is None or v["wahr"] in v["kandidaten"]
        assert v["extern_id"] in n["neu"]
    assert len(n["zusammengefuehrt"]) + len(n["neu"]) == len(ueber["buchungen"])
    # alle GnuCash-Buchungen mit Quelle im KMyMoney-Teil werden zusammengeführt oder zur Prüfung vorgelegt
    verdacht = {v["extern_id"] for v in n["verdacht"]}
    for g, q in quelle.items():
        if q in kmy:
            assert g in n["zusammengefuehrt"] or g in verdacht, g
    assert n["ergebnis"]["buchungen_zusammengefuehrt"] == len(n["zusammengefuehrt"])
    assert any(v["grund"] == "mehrdeutig" for v in n["verdacht"]), "zweimal derselbe Kaffee fehlt"


# --------------------------------------------------------------- Lerndaten
@pytest.fixture(scope="module")
def lern():
    return lade(M4 / "lernen.erwartung.json")


def test_lerndaten_trennung_80_20(lern):
    w = lern["buchungen"]
    sortiert = sorted(w, key=lambda x: (x["datum"], x["id"]))
    assert sortiert == w
    n_train = sum(x["teil"] == "training" for x in w)
    assert n_train == int(len(w) * 0.8)
    assert all(x["teil"] == "training" for x in w[:n_train]) and all(x["teil"] == "pruefung" for x in w[n_train:])
    assert lern["letztes_trainingsdatum"] == w[n_train - 1]["datum"]


def test_lerndaten_stoerfaelle(lern):
    w = lern["buchungen"]
    fehler = sum(x["fehlerhaft"] for x in w) / len(w)
    assert 0.02 < fehler < 0.07, "etwa 4 % falsch erfasste Buchungen"
    kats: dict[str, set] = {}
    for x in w:
        kats.setdefault(x["empfaenger"], set()).add(x["wahr"])
    assert sum(len(v) > 1 for v in kats.values()) >= 3, "Empfänger mit mehreren Kategorien"
    train_empf = {x["empfaenger"] for x in w if x["teil"] == "training"}
    assert {x["empfaenger"] for x in w if x["teil"] == "pruefung"} - train_empf, "neue Empfänger in der Prüfung"
    assert any(x["betrag"] > 0 for x in w)


def test_mindestgenauigkeit_auf_generatordaten(lern):
    """T 21: Genauigkeit ≥ 85 % und Abdeckung ≥ 70 % mit dem festgelegten Verfahren (Orakel)."""
    r = bewerte(lern["buchungen"])
    assert r["genauigkeit"] >= Fraction(85, 100), r
    assert r["abdeckung"] >= Fraction(70, 100), r
    assert r["vorgeschlagen"] < r["pruefung"], "bei geringer Sicherheit muss es Fälle ohne Vorschlag geben"


def test_lern_training_kmy_enthaelt_nur_training(lern):
    e = lade(KMY / "m4_lernen_training.erwartung.json")
    train = {"kmy:" + x["id"] for x in lern["buchungen"] if x["teil"] == "training"}
    pruef = {"kmy:" + x["id"] for x in lern["buchungen"] if x["teil"] == "pruefung"}
    ids = {b["extern_id"] for b in e["buchungen"]}
    assert train <= ids and not (pruef & ids)
    nach = {b["extern_id"]: b for b in e["buchungen"]}
    for x in lern["buchungen"]:
        if x["teil"] != "training":
            continue
        b = nach["kmy:" + x["id"]]
        assert (b["empfaenger"], b["verwendungszweck"]) == (x["empfaenger"], x["verwendungszweck"])
        name = {k["extern_id"]: k["name"] for k in e["konten"]}
        assert name[b["kategorie_extern_id"]] == x["kategorie"]
    # dieselben Trainingsbeispiele als GnuCash
    g = gnc_leser.lies((GNC / "m4_lernen_training.gnucash").read_bytes())
    assert len(g["buchungen"]) == len(e["buchungen"])


def test_lern_mock_enthaelt_pruefbuchungen(lern):
    d = lade(LERN_MOCK)
    pruef = [x for x in lern["buchungen"] if x["teil"] == "pruefung"]
    assert [u["umsatz_id"] for u in d["bank"]["umsaetze"]] == [x["umsatz_id"] for x in pruef]
    for u, x in zip(d["bank"]["umsaetze"], pruef):
        assert (u["buchungstag"], u["betrag"], u["gegenpartei_name"], u["verwendungszweck"]) == (
            x["datum"], x["betrag"], x["empfaenger"], x["verwendungszweck"])
        assert u["iban"] in lern["ibans"].values() and ist_gueltig(u["iban"]) and u["iban"][4:12] == "00000000"


def test_merkmale_beispiel_aus_spezifikation():
    """lernmodell.md 2, Beispiel."""
    assert sorted(merkmale("Café Bohne", "Kartenzahlung Café 12/2024", -340)) == sorted(
        ["e:cafbohne", "v:kartenzahlung", "v:caf", "b:-3"])
    assert merkmale(None, "", 0) == ["b:0"]
    assert merkmale("  ", "ab 12 xy3 Straße", 150000)[-1] == "b:+6"
    assert "v:strasse" in merkmale(None, "Straße", 1)


# ---------------------------------------------------------------- Vorlagen
@pytest.fixture(scope="module")
def vor():
    return lade(VORLAGEN_MOCK), lade(MOCK / "m4_vorlagen.erwartung.json"), lade(M4 / "vorlagen.json")


def _vorlagen(stamm: dict, angepasst: bool) -> list[dict]:
    aus = []
    for i, v in enumerate(stamm["vorlagen"], start=1):
        teile = stamm["angepasst"]["teile"] if angepasst and v["name"] == stamm["angepasst"]["vorlage"] else v["teile"]
        bed = [b if not isinstance(b["wert"], dict) else {**b, "wert": 1} for b in v["bedingungen"]]
        aus.append({"id": i, "name": v["name"], "aktiv": True, "prioritaet": v["prioritaet"], "bedingungen": bed,
                    "gesamtbetrag": -sum(t["betrag"] for t in teile), "teile": teile})
    return aus


@pytest.mark.parametrize("szenario", ["normal", "beitragsaenderung"])
def test_vorlagen_wahrheit_gegen_orakel(vor, szenario):
    daten, erw, stamm = vor
    for u in daten["bank"]["umsaetze"]:
        e = erw[szenario][u["umsatz_id"]]
        angepasst = szenario == "beitragsaenderung" and e["stufe"] == 2
        betrag = u.get("betrag_beitragsaenderung", u["betrag"]) if szenario == "beitragsaenderung" else u["betrag"]
        art, v = erkenne(_vorlagen(stamm, angepasst), u["gegenpartei_name"], u["verwendungszweck"], {1}, betrag)
        assert e["betrag"] == betrag
        assert e["ergebnis"] == {"treffer": "gesplittet", "abweichung": "abweichung", "keine": "keine"}[art], u
        if v:
            assert e["vorlage"] == v["name"]
        if art == "treffer":
            assert sum(s["betrag"] for s in e["splits"]) == -betrag


def test_vorlagen_daten_enthalten_cent_abweichungen_und_beitragsaenderung(vor):
    daten, erw, stamm = vor
    abw = [erw["normal"][u["umsatz_id"]] for u in daten["bank"]["umsaetze"]
           if erw["normal"][u["umsatz_id"]]["ergebnis"] == "abweichung"]
    assert sorted(a["betrag"] - a["gesamtbetrag"] for a in abw) == [-1, 1], "je 1 Cent nach oben und unten"
    mit = [u for u in daten["bank"]["umsaetze"] if "betrag_beitragsaenderung" in u]
    assert mit and all(u["buchungstag"][:7] >= erw["beitrag_ab"] for u in mit)
    assert all(isinstance(u["betrag_beitragsaenderung"], int) for u in mit)
    namen = {v["name"] for v in stamm["vorlagen"]}
    assert stamm["angepasst"]["vorlage"] in namen
    assert len(erw["benachrichtigungen_beitragsaenderung"]) == len(erw["benachrichtigungen_normal"]) + 1
    # ein Empfänger mit zwei Vorlagen, die sich nur im Muster unterscheiden, und ein Umsatz ohne Vorlage
    fiktiva = [e for u in daten["bank"]["umsaetze"] if u["gegenpartei_name"] == "Fiktiva Versicherung AG"
               for e in [erw["normal"][u["umsatz_id"]]]]
    assert {e.get("vorlage") for e in fiktiva} == {"Versicherung monatlich", "Versicherung jährlich", None}
    assert dt.date.fromisoformat(erw["stufen"][-1]) == dt.date(2024, 12, 31)
    json.dumps(erw)
