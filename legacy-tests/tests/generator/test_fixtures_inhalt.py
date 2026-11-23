"""Fixtures sind gültige KMyMoney-Dateien, Erwartungen sind in sich stimmig (ohne App).

Die XML-Auswertung hier ist unabhängig vom Generator: Sie parst die erzeugten
Bytes und rechnet Salden selbst nach.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import xml.etree.ElementTree as ET
import zlib
from collections import defaultdict
from fractions import Fraction

import pytest

from generator.iban import ist_gueltig
from tests.hilfen.pfade import KMY, MOCK

GUELTIGE = ["standard", "standard_bis_2023", "minimal", "minimal_unkomprimiert", "sonderfaelle",
            "fremdwaehrung", "dubletten", "sync_altbestand", "m3_aliase"]
DEFEKTE = ["leer", "leer_gzip", "abgeschnitten", "kaputtes_xml", "falsches_format", "kein_xml",
           "entitaeten", "inhalt_ungueltig", "betrag_ungueltig", "datum_ungueltig", "pflichtfeld_fehlt"]


def _xml(name: str) -> bytes:
    roh = (KMY / f"{name}.kmy").read_bytes()
    return gzip.decompress(roh) if roh[:2] == b"\x1f\x8b" else roh


def _erw(name: str) -> dict:
    return json.loads((KMY / f"{name}.erwartung.json").read_text(encoding="utf-8"))


def _cent(wert: str) -> int:
    f = Fraction(wert) * 100
    assert f.denominator == 1, wert
    return int(f)


@pytest.mark.parametrize("name", GUELTIGE)
def test_gueltiges_kmymoney_xml(name):
    x = _xml(name)
    assert x.startswith(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE KMYMONEY-FILE>\n')
    wurzel = ET.fromstring(x)
    assert wurzel.tag == "KMYMONEY-FILE"
    for abschnitt in ("FILEINFO", "PAYEES", "TAGS", "ACCOUNTS", "TRANSACTIONS", "CURRENCIES"):
        assert wurzel.find(abschnitt) is not None, abschnitt
    konten = {a.get("id"): a for a in wurzel.iter("ACCOUNT")}
    for std in ("AStd::Asset", "AStd::Liability", "AStd::Expense", "AStd::Income", "AStd::Equity"):
        assert std in konten
    for a in konten.values():
        p = a.get("parentaccount")
        assert p == "" or p in konten, f"{a.get('id')}: Elternkonto {p} fehlt"
        for sub in a.iter("SUBACCOUNT"):
            assert konten[sub.get("id")].get("parentaccount") == a.get("id")
    payees = {p.get("id") for p in wurzel.iter("PAYEE")}
    tags = {t.get("id") for t in wurzel.find("TAGS").iter("TAG")}
    for liste, tag in (("ACCOUNTS", "ACCOUNT"), ("PAYEES", "PAYEE"), ("TAGS", "TAG"), ("TRANSACTIONS", "TRANSACTION")):
        el = wurzel.find(liste)
        assert int(el.get("count")) == len(el.findall(tag)), liste
    for t in wurzel.iter("TRANSACTION"):
        assert re.fullmatch(r"T\d{18}", t.get("id"))
        dt.date.fromisoformat(t.get("postdate")[:10])
        for s in t.iter("SPLIT"):
            assert s.get("account") in konten and not s.get("account").startswith("AStd::")
            assert s.get("payee") in (None, "") or s.get("payee") in payees
            for tg in s.iter("TAG"):
                assert tg.get("id") in tags
            assert re.fullmatch(r"-?\d+(/\d+)?", s.get("value"))
            _cent(s.get("value"))


@pytest.mark.parametrize("name", GUELTIGE)
def test_erwartung_entspricht_xml(name):
    """Salden und Anzahlen in der Erwartung stimmen mit der Datei überein."""
    erw = _erw(name)
    wurzel = ET.fromstring(_xml(name))
    uebersprungen_b = {w["referenz"] for w in erw["warnungen"] if w["code"] == "buchung_uebersprungen"}
    ausgeglichen = {w["referenz"] for w in erw["warnungen"] if w["code"] == "buchung_ausgeglichen"}
    saldo: dict[str, int] = defaultdict(int)
    n = 0
    for t in wurzel.iter("TRANSACTION"):
        if t.get("id") in uebersprungen_b:
            continue
        n += 1
        summe = 0
        for s in t.iter("SPLIT"):
            saldo["kmy:" + s.get("account")] += _cent(s.get("value"))
            summe += _cent(s.get("value"))
        anzahl = len(t.findall("SPLITS/SPLIT"))
        assert (summe != 0 or anzahl < 2) == (t.get("id") in ausgeglichen), t.get("id")
        saldo["kontor:unausgeglichen"] -= summe
    assert n == erw["summen"]["anzahl_buchungen"] == len(erw["buchungen"])
    assert len(wurzel.findall("TRANSACTIONS/TRANSACTION")) == erw["summen"]["anzahl_transaktionen_in_datei"]
    for k in erw["konten"]:
        assert k["saldo"] == saldo.get(k["extern_id"], 0), k["name"]
    e = erw["ergebnis"]
    assert e["buchungen_neu"] + e["buchungen_vorhanden"] + e["buchungen_zusammengefuehrt"] + \
        e["buchungen_uebersprungen"] == erw["summen"]["anzahl_transaktionen_in_datei"]


@pytest.mark.parametrize("name", GUELTIGE)
def test_erwartung_invarianten(name):
    erw = _erw(name)
    for b in erw["buchungen"]:
        assert len(b["splits"]) >= 2
        assert sum(s["betrag"] for s in b["splits"]) == 0, b["extern_id"]
        assert all(isinstance(s["betrag"], int) for s in b["splits"])
    assert sum(k["saldo"] for k in erw["konten"]) == 0
    assert erw["summen"]["summe_gesamt"] == 0


@pytest.mark.parametrize("name", GUELTIGE)
def test_nur_synthetische_daten(name):
    """Nur Test-IBANs (BLZ 00000000) und Adressen unter example.invalid."""
    x = _xml(name).decode("utf-8")
    for iban in re.findall(r'key="iban" value="([^"]*)"', x):
        n = iban.replace(" ", "").upper()
        assert n[4:12] == "00000000", f"IBAN {iban} ist nicht offensichtlich fiktiv"
    for mail in re.findall(r"[\w.+-]+@[\w.-]+", x):
        assert mail.endswith("@example.invalid") or mail.endswith(".example.invalid"), mail
    erw = _erw(name)
    ungueltig = {w["referenz"] for w in erw["warnungen"] if w["code"] == "iban_ungueltig"}
    wurzel = ET.fromstring(_xml(name))
    for a in wurzel.iter("ACCOUNT"):
        for p in a.iter("PAIR"):
            if p.get("key") == "iban":
                assert ist_gueltig(p.get("value")) != (a.get("id") in ungueltig)


def test_standard_realistische_muster():
    """T 21: Gehalt, Miete, Abos, Umbuchungen, Sammelabbuchung mit Beitragsänderung, Störfälle."""
    erw = _erw("standard")
    b = erw["buchungen"]
    gehalt = [x for x in b if x["empfaenger"] == "Arbeitgeber Muster GmbH"]
    assert len(gehalt) == 36
    assert all(dt.date.fromisoformat(x["datum"]).weekday() < 5 for x in gehalt), "Wochenendverschiebung"
    assert any(dt.date.fromisoformat(x["datum"]).day != 28 for x in gehalt), "mindestens eine Verschiebung"
    abo = [x for x in b if x["empfaenger"] == "Streamio Media (fiktiv)"]
    assert len(abo) == 35 and not any(x["datum"].startswith("2023-08") for x in abo), "ausbleibende Zahlung"
    vers = [x for x in b if x["empfaenger"] == "Fiktiva Versicherung AG"]
    assert all(len(x["splits"]) == 4 and x["kategorie_extern_id"] is None for x in vers)
    assert {x["umsatz"] for x in vers} == {3700, 3790}, "Beitragsänderung"
    assert len(erw["umbuchungen"]) >= 36
    kaffee = [x for x in b if x["verwendungszweck"] == "Kartenzahlung Café Cappuccino"]
    assert len(kaffee) == 6 and len({x["datum"] for x in kaffee}) == 3, "zweimal derselbe Kaffee je Jahr"
    assert sum(1 for x in b if x["verwendungszweck"].startswith("STORNO")) == 3
    assert any("☃" in x["verwendungszweck"] for x in b)
    darlehen = [k for k in erw["konten"] if k["name"].startswith("Darlehen")]
    assert len(darlehen) == 2 and all(k["art"] == "kreditkonto" and k["saldo"] < 0 for k in darlehen)
    assert all(x["wahre_kategorie_extern_id"] == x["kategorie_extern_id"] for x in b
               if x["wahre_kategorie_extern_id"])


def test_standard_bis_2023_ist_praefix():
    voll = _erw("standard")
    teil = _erw("standard_bis_2023")
    ids_teil = [x["extern_id"] for x in teil["buchungen"]]
    ids_voll = [x["extern_id"] for x in voll["buchungen"] if x["datum"] <= "2023-12-31"]
    assert ids_teil == ids_voll
    assert len(voll["buchungen"]) > len(teil["buchungen"]) > 0


def test_sonderfaelle_abdeckung():
    erw = _erw("sonderfaelle")
    b = erw["buchungen"]
    assert any(len(x["verwendungszweck"]) >= 5000 for x in b)
    assert any(x["empfaenger"] is None for x in b)
    assert any(len(x["splits"]) > 10 for x in b)
    assert any(k["geschlossen"] for k in erw["konten"])
    tiefe = {k["extern_id"]: k["eltern_extern_id"] for k in erw["konten"]}

    def ebene(e):
        return 0 if tiefe[e] is None else 1 + ebene(tiefe[e])
    assert max(ebene(e) for e in tiefe) >= 3
    codes = {w["code"] for w in erw["warnungen"]}
    assert {"kontoart_ersetzt", "iban_ungueltig", "iban_doppelt", "eroeffnungsdatum_ungueltig",
            "hierarchie_angepasst", "buchung_ausgeglichen", "empfaenger_zusammengefasst",
            "tag_zusammengefasst"} <= codes
    x = _xml("sonderfaelle").decode()
    assert 'value="-617/50"' in x and 'value="12"' in x and 'value="-1230/1000"' in x


DEFEKT_PRUEFUNG = {
    "leer": lambda roh: roh == b"",
    "leer_gzip": lambda roh: roh[:2] == b"\x1f\x8b" and gzip.decompress(roh) == b"",
    "kein_xml": lambda roh: roh[:2] != b"\x1f\x8b" and not roh.lstrip().startswith(b"<"),
}


@pytest.mark.parametrize("name", DEFEKTE)
def test_defekte_dateien_wirklich_defekt(name):
    roh = (KMY / f"{name}.kmy").read_bytes()
    erw = _erw(name)
    assert erw["erfolgreich"] is False and erw["fehler_code"].startswith("import_")
    if name in DEFEKT_PRUEFUNG:
        assert DEFEKT_PRUEFUNG[name](roh)
        return
    assert roh[:2] == b"\x1f\x8b"
    if name == "abgeschnitten":
        with pytest.raises((EOFError, OSError, zlib.error)):
            gzip.decompress(roh)
        return
    x = gzip.decompress(roh)
    if name == "kaputtes_xml":
        with pytest.raises(ET.ParseError):
            ET.fromstring(x)
        return
    if name == "falsches_format":
        assert ET.fromstring(x).tag != "KMYMONEY-FILE"
        return
    if name == "entitaeten":
        assert b"<!ENTITY" in x
        return
    wurzel = ET.fromstring(x)
    assert wurzel.tag == "KMYMONEY-FILE"
    if name == "inhalt_ungueltig":
        assert any(s.get("account") == "A999999" for s in wurzel.iter("SPLIT"))
    elif name == "betrag_ungueltig":
        assert any(s.get("value") == "1/3" for s in wurzel.iter("SPLIT"))
    elif name == "datum_ungueltig":
        assert any(t.get("postdate") == "2023-02-30" for t in wurzel.iter("TRANSACTION"))
    elif name == "pflichtfeld_fehlt":
        assert any(s.get("value") is None for s in wurzel.iter("SPLIT"))
    else:  # pragma: no cover
        raise AssertionError(name)


def test_mock_daten_format():
    daten = json.loads((MOCK / "mock_daten.json").read_text(encoding="utf-8"))
    erw = json.loads((MOCK / "mock_daten.erwartung.json").read_text(encoding="utf-8"))
    assert daten["format"] == "kontor-mock-daten" and daten["version"] == 1
    konten = {k["iban"] for k in daten["bank"]["konten"]}
    for k in daten["bank"]["konten"]:
        assert ist_gueltig(k["iban"]) and k["iban"][4:12] == "00000000"
        assert k["art"] in ("girokonto", "sparkonto", "kreditkonto") and k["waehrung"] == "EUR"
    ids = set()
    for u in daten["bank"]["umsaetze"]:
        assert set(u) == {"umsatz_id", "iban", "buchungstag", "valuta", "betrag", "waehrung",
                          "gegenpartei_name", "gegenpartei_iban", "verwendungszweck", "vormerkung", "storno"}
        assert u["iban"] in konten and isinstance(u["betrag"], int) and u["waehrung"] == "EUR"
        assert u["umsatz_id"] not in ids
        ids.add(u["umsatz_id"])
        dt.date.fromisoformat(u["buchungstag"])
        assert u["umsatz_id"] in erw["wahre_kategorie"]
    for a, b in erw["umbuchungspaare"]:
        ua = next(u for u in daten["bank"]["umsaetze"] if u["umsatz_id"] == a)
        ub = next(u for u in daten["bank"]["umsaetze"] if u["umsatz_id"] == b)
        assert ua["betrag"] == -ub["betrag"] and ua["gegenpartei_iban"] == ub["iban"]
    assert erw["vormerkungen"] and erw["stornos"]
    assert len(daten["mail"]["postfaecher"]) == 2
    for m in daten["mail"]["nachrichten"]:
        assert m["postfach"] in daten["mail"]["postfaecher"]
        assert m["empfangen"].endswith("Z")
        assert m["absender"].endswith(".example.invalid") or m["absender"].endswith("@example.invalid")
    for p in daten["mail"]["postfaecher"]:
        assert p.endswith("@example.invalid")
