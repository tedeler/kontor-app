"""M8: Datensätze der Oberflächentests (generator/m8_daten.py) – unabhängig aus dem XML nachgeprüft."""

from __future__ import annotations

import gzip
import json
import xml.etree.ElementTree as ET
from collections import Counter

import pytest

from generator.iban import ist_gueltig
from tests.hilfen.pfade import FIXTURES

pytestmark = pytest.mark.m8

M8 = FIXTURES / "m8"


def _xml(name: str) -> ET.Element:
    return ET.fromstring(gzip.decompress((M8 / name).read_bytes()))


def _erw(name: str) -> dict:
    return json.loads((M8 / name).read_text(encoding="utf-8"))


def _wert(text: str) -> int:
    z, n = text.split("/")
    assert n == "100", text
    return int(z)


def test_oberflaeche_inhalt_unabhaengig():
    wurzel = _xml("oberflaeche.kmy")
    erw = _erw("oberflaeche.erwartung.json")
    m8 = erw["m8"]
    giro = m8["konten"]["giro"].removeprefix("kmy:")
    trans = wurzel.findall(".//TRANSACTION")
    auf_giro = [t for t in trans if any(s.get("account") == giro for s in t.findall(".//SPLIT"))]
    assert len(auf_giro) == m8["giro_anzahl"] == 85
    saldo = sum(_wert(s.get("value")) for t in auf_giro for s in t.findall(".//SPLIT") if s.get("account") == giro)
    assert saldo == m8["giro_saldo"]
    # Filterfall Zeitraum unabhängig aus postdate
    maerz = sorted("kmy:" + t.get("id") for t in auf_giro if t.get("postdate", "").startswith("2024-03"))
    fall = next(f for f in m8["filterfaelle"] if f["name"] == "zeitraum_maerz")
    assert fall["erwartet"] == maerz
    # wörtlich darzustellender Text und Umlaute sind enthalten
    memos = {s.get("memo") for t in trans for s in t.findall(".//SPLIT")}
    assert m8["html_text"] in memos and m8["umlaut_zweck"] in memos
    # genau eine Splitbuchung mit drei Splits, ein geschlossenes Konto, Kategorienbaum mit drei Ebenen
    assert Counter(len(t.findall(".//SPLIT")) for t in trans)[3] == 1
    konten = {k.get("id"): k for k in wurzel.findall(".//ACCOUNT")}
    assert m8["pfade"]["kmy:A000019"] == "Freizeit › Kino › 3D-Vorstellungen"
    assert konten["A000019"].get("parentaccount") == "A000015"
    assert len(m8["baum_aufwand"]) == len(set(m8["baum_aufwand"])) == 10
    assert m8["baum_ertrag"] == ["kmy:A000021", "kmy:A000020"]  # Erstattungen vor Gehalt


def test_nur_synthetische_daten():
    for name in ("oberflaeche.kmy", "viele.kmy"):
        wurzel = _xml(name)
        ibans = [kv.get("value") for kv in wurzel.iter("PAIR") if kv.get("key", "").lower() == "iban"]
        assert ibans, name
        for iban in ibans:
            assert ist_gueltig(iban) and iban[4:12] == "00000000", iban


def test_viele_buchungen():
    wurzel = _xml("viele.kmy")
    assert len(wurzel.findall(".//TRANSACTION")) == 450
    assert _erw("viele.erwartung.json")["konten"][0]["anzahl_buchungen"] == 450


@pytest.mark.parametrize("name", ["oberflaeche", "viele"])
def test_im_manifest(name):
    m = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))["dateien"]
    assert f"m8/{name}.kmy" in m and f"m8/{name}.erwartung.json" in m
