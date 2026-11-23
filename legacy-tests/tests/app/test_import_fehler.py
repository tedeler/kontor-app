"""Fehlerfälle beim KMyMoney-Import: verständliche Meldung, kein Teilimport (T 5, datenmodell.md 10.1)."""

from __future__ import annotations

import gzip
import json
import xml.etree.ElementTree as ET

import pytest
from hypothesis import given, strategies as st

from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_config
from tests.hilfen.erwartung import ZAEHLFELDER
from tests.hilfen.kmybau import KOPF, als_bytes, konto, minimal_baum, packe_gzip, split, transaktion, veraendert
from tests.hilfen.pfade import KMY
from tests.hilfen.vertrag import vertrag

FEHLERCODES = {"import_datei_leer", "import_format_ungueltig", "import_datei_beschaedigt", "import_inhalt_ungueltig"}
DEFEKTE = ["leer", "leer_gzip", "abgeschnitten", "kaputtes_xml", "falsches_format", "kein_xml", "entitaeten",
           "inhalt_ungueltig", "betrag_ungueltig", "datum_ungueltig", "pflichtfeld_fehlt"]


def _erwartung(name: str) -> dict:
    return json.loads((KMY / f"{name}.erwartung.json").read_text(encoding="utf-8"))


def pruefe_fehlschlag(ergebnis: dict, code: str, format_: str | None) -> None:
    """ImportErgebnis eines fehlgeschlagenen Imports (datenmodell.md 10.1 letzter Absatz)."""
    fehler = list(vertrag().schema_validator("ImportErgebnis").iter_errors(ergebnis))
    assert not fehler, f"Ergebnis verletzt das Schema ImportErgebnis: {fehler[0].message}"
    assert ergebnis["erfolgreich"] is False
    assert ergebnis["import_id"] is None
    assert ergebnis["format"] == format_, f"format {ergebnis['format']!r}, erwartet {format_!r}"
    assert {f: ergebnis[f] for f in ZAEHLFELDER} == {f: 0 for f in ZAEHLFELDER}
    assert ergebnis["fehler"], "fehler darf nicht leer sein"
    assert ergebnis["fehler"][0]["code"] == code, ergebnis["fehler"]
    assert all(f["code"] in FEHLERCODES for f in ergebnis["fehler"])
    assert all(f["meldung"].strip() for f in ergebnis["fehler"]), "Fehlermeldung ohne Text"
    if code != "import_inhalt_ungueltig":
        assert len(ergebnis["fehler"]) == 1, "bei Datei-/Formatfehlern genau eine Meldung"
    else:
        assert {f["code"] for f in ergebnis["fehler"]} == {"import_inhalt_ungueltig"}


def importiere_fehlerhaft(api, inhalt: bytes, code: str, format_: str | None, dateiname: str = "datei.kmy") -> dict:
    """Import über REST, der fehlschlagen muss; prüft, dass sich am Buch nichts ändert."""
    vorher = api.zustand()
    importe = api.get("/api/importe", erwartet=200).daten
    r = api.post("/api/import/kmymoney", files={"datei": (dateiname, inhalt, "application/octet-stream")},
                 erwartet=422)
    f = r.json()["fehler"]
    assert f["code"] == code, f
    assert f["meldung"].strip()
    pruefe_fehlschlag(f["details"], code, format_)
    assert api.zustand() == vorher, "fehlgeschlagener Import hat das Buch verändert (Teilimport)"
    assert api.get("/api/importe", erwartet=200).daten == importe, "fehlgeschlagener Import erzeugt Importvorgang"
    return f["details"]


@pytest.fixture
def api_mit_bestand(api):
    """Nicht leeres Buch: minimal.kmy plus eine manuelle Buchung."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    g = api.konto("Handkonto")
    a = api.konto("Handkategorie", "aufwand")
    api.buchung("2024-03-01", [(g["id"], -100), (a["id"], 100)])
    return api


@pytest.mark.kern
@pytest.mark.parametrize("name", DEFEKTE)
def test_defekte_fixtures_rest(api_mit_bestand, name):
    erw = _erwartung(name)
    importiere_fehlerhaft(api_mit_bestand, (KMY / f"{name}.kmy").read_bytes(), erw["fehler_code"], erw["format"])


@pytest.mark.parametrize("name", DEFEKTE)
def test_defekte_fixtures_python(tmp_path, name):
    erw = _erwartung(name)
    config = neue_config(tmp_path)
    api = Api(config)
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    vorher = api.zustand()
    e = kontor.importiere_kmy(config, KMY / f"{name}.kmy")
    assert e.erfolgreich is False and e.import_id is None
    pruefe_fehlschlag(e.als_dict(), erw["fehler_code"], erw["format"])
    assert api.zustand() == vorher
    assert len(api.get("/api/importe", erwartet=200).daten) == 1


def test_leere_datei_in_leeres_buch(api):
    importiere_fehlerhaft(api, b"", "import_datei_leer", None)
    assert api.konten() == []


def test_entitaeten_nicht_expandiert(api):
    """Entitätsdeklarationen werden abgelehnt, bevor irgendetwas expandiert oder geladen wird (E-023)."""
    importiere_fehlerhaft(api, (KMY / "entitaeten.kmy").read_bytes(), "import_format_ungueltig", None)


# ---------------------------------------------------- Format (unkomprimiert)

MINI_XML = (KMY / "minimal_unkomprimiert.kmy").read_bytes()


@pytest.mark.parametrize("inhalt,code,format_", [
    (MINI_XML.replace(b"</TRANSACTIONS>", b"</TRANSAKTIONEN>"), "import_datei_beschaedigt", "kmy-xml"),
    (MINI_XML[: len(MINI_XML) // 2], "import_datei_beschaedigt", "kmy-xml"),
    (b"<?xml version='1.0'?><gnc-v2></gnc-v2>", "import_format_ungueltig", None),
    (b"<html><body>Kein Buch</body></html>", "import_format_ungueltig", None),
    (MINI_XML.replace(b"<!DOCTYPE KMYMONEY-FILE>", b'<!DOCTYPE KMYMONEY-FILE [\n<!ENTITY x "y">\n]>'),
     "import_format_ungueltig", None),
    (MINI_XML.replace(b"<!DOCTYPE KMYMONEY-FILE>", b"<!DOCTYPE KMYMONEY-FILE [ ]>"), "import_format_ungueltig", None),
    # externe Entität nur deklariert (eine Verwendung in Attributen wäre schon nicht wohlgeformt)
    (MINI_XML.replace(b"<!DOCTYPE KMYMONEY-FILE>",
                      b'<!DOCTYPE KMYMONEY-FILE [\n<!ENTITY datei SYSTEM "file:///etc/passwd">\n]>'),
     "import_format_ungueltig", None),
    (b"PK\x03\x04" + b"\x00" * 40, "import_format_ungueltig", None),
    (b"   \n\t ", "import_format_ungueltig", None),
    (b"\xef\xbb\xbf", "import_format_ungueltig", None),
    (b"\x1f", "import_format_ungueltig", None),
    (b"\x1f\x8b", "import_datei_beschaedigt", "kmy-gzip"),
    (b"\x1f\x8b\x08\x00garbage-garbage", "import_datei_beschaedigt", "kmy-gzip"),
    (packe_gzip(b"<KMYMONEY-FILE><ACCOUNTS>"), "import_datei_beschaedigt", "kmy-gzip"),
    (packe_gzip(b"<?xml version='1.0'?><KMYMONEY-FILE/>")[:-3], "import_datei_beschaedigt", "kmy-gzip"),
], ids=["xml_kaputt", "xml_abgeschnitten", "gnucash_wurzel", "html", "entity", "leere_interne_dtd", "xxe",
        "zip", "nur_leerraum", "nur_bom", "ein_byte_1f", "nur_gzip_magie", "gzip_kaputt", "gzip_xml_kaputt",
        "gzip_ohne_ende"])
def test_formatfehler(api_mit_bestand, inhalt, code, format_):
    importiere_fehlerhaft(api_mit_bestand, inhalt, code, format_)


# ------------------------------------------------------- inhaltliche Fehler


def _attr_weg(pfad_finden, attr):
    def eingriff(w):
        el = pfad_finden(w)
        assert attr in el.attrib, (attr, el.attrib)
        del el.attrib[attr]
    return eingriff


def _setze(pfad_finden, attr, wert):
    def eingriff(w):
        pfad_finden(w).set(attr, wert)
    return eingriff


def _konto2(w):
    return konto(w, "A000002")


def _payee1(w):
    return w.find("PAYEES/PAYEE")


def _tag1(w):
    return w.find("TAGS/TAG")


def _t0(w):
    return transaktion(w, 0)


def _s00(w):
    return split(w, 0, 0)


def _ohne_splits(w):
    ss = transaktion(w, 0).find("SPLITS")
    for s in list(ss):
        ss.remove(s)


def _ohne_splits_element(w):
    t = transaktion(w, 1)
    t.remove(t.find("SPLITS"))


def _unbekannter_tag(w):
    ET.SubElement(split(w, 0, 0), "TAG", id="G999999")


def _zwei_fehler(w):
    split(w, 0, 1).set("account", "A777777")
    split(w, 1, 0).set("value", "1/3")
    split(w, 1, 1).set("value", "-1/3")


INHALTSFEHLER = {
    "ACCOUNT@id": _attr_weg(_konto2, "id"),
    "ACCOUNT@name": _attr_weg(_konto2, "name"),
    "ACCOUNT@type": _attr_weg(_konto2, "type"),
    "TRANSACTION@id": _attr_weg(_t0, "id"),
    "TRANSACTION@postdate": _attr_weg(_t0, "postdate"),
    "SPLIT@account": _attr_weg(_s00, "account"),
    "SPLIT@value": _attr_weg(_s00, "value"),
    "PAYEE@id": _attr_weg(_payee1, "id"),
    "PAYEE@name": _attr_weg(_payee1, "name"),
    "TAG@id": _attr_weg(_tag1, "id"),
    "TAG@name": _attr_weg(_tag1, "name"),
    "split_auf_standardkonto": _setze(_s00, "account", "AStd::Asset"),
    "split_konto_unbekannt": _setze(_s00, "account", "A777777"),
    "eltern_unbekannt": _setze(_konto2, "parentaccount", "A888888"),
    "payee_unbekannt": _setze(_s00, "payee", "P999999"),
    "tag_unbekannt": _unbekannter_tag,
    "ohne_split": _ohne_splits,
    "ohne_splits_element": _ohne_splits_element,
    "zwei_fehler": _zwei_fehler,
}
for _wert in ["12.50", "abc", "1/0", "--1/100", "1/-100", "", "1e3", "1/3", "0x10", "1/3/4", "+5/100",
              "100000000000000/100", "-100000000000000/100", "1 /100"]:
    INHALTSFEHLER[f"value={_wert!r}"] = _setze(_s00, "value", _wert)
for _datum in ["2023-02-30", "2024-13-01", "20240131", "31.01.2024", "", "2024-1-31", "heute"]:
    INHALTSFEHLER[f"postdate={_datum!r}"] = _setze(_t0, "postdate", _datum)


@pytest.mark.kern
@pytest.mark.parametrize("name", list(INHALTSFEHLER))
def test_inhaltsfehler(api_mit_bestand, name):
    d = importiere_fehlerhaft(api_mit_bestand, veraendert(INHALTSFEHLER[name]), "import_inhalt_ungueltig", "kmy-gzip")
    if name == "zwei_fehler":
        assert len(d["fehler"]) >= 2, "alle gefundenen Fehler werden gemeldet"


def test_inhaltsfehler_unkomprimiert(api_mit_bestand):
    importiere_fehlerhaft(api_mit_bestand, veraendert(INHALTSFEHLER["split_konto_unbekannt"], gz=False),
                          "import_inhalt_ungueltig", "kmy-xml")


def test_inhaltsfehler_mit_referenz(api):
    d = importiere_fehlerhaft(api, veraendert(INHALTSFEHLER["split_konto_unbekannt"]), "import_inhalt_ungueltig",
                              "kmy-gzip")
    assert all(f["referenz"] is None or isinstance(f["referenz"], str) for f in d["fehler"])
    assert any(f["referenz"] for f in d["fehler"]), "Inhaltsfehler nennen die betroffene KMyMoney-ID"
    assert not any(f["referenz"].startswith("kmy:") for f in d["fehler"] if f["referenz"])


# --------------------------------------------- eigenschaftsbasierte Fehler

GZ_MINIMAL = (KMY / "minimal.kmy").read_bytes()


@pytest.mark.kern
@given(st.integers(min_value=2, max_value=len(GZ_MINIMAL) - 1))
def test_abgeschnittenes_gzip(api_fabrik, laenge):
    api = api_fabrik()
    importiere_fehlerhaft(api, GZ_MINIMAL[:laenge], "import_datei_beschaedigt", "kmy-gzip")


@given(st.one_of(
    st.binary(max_size=300),
    st.binary(max_size=300).map(lambda b: b"\x1f\x8b" + b),
    st.text(max_size=200).map(lambda t: ("<" + t).encode("utf-8")),
    st.binary(min_size=1, max_size=200).map(lambda b: packe_gzip(b)),
))
def test_zufallsbytes_nie_serverfehler(api_fabrik, inhalt):
    """Beliebige Bytes: nie 5xx, entweder Erfolg oder einer der vier Fehlercodes ohne Änderung."""
    api = api_fabrik()
    r = api.post("/api/import/kmymoney", files={"datei": ("z.kmy", inhalt, "application/octet-stream")})
    assert r.status_code in (200, 422), r.text
    if r.status_code == 422:
        f = r.json()["fehler"]
        assert f["code"] in FEHLERCODES
        pruefe_fehlschlag(f["details"], f["code"], f["details"]["format"])
        assert api.konten() == [] and api.get("/api/importe", erwartet=200).daten == []
        fmt = f["details"]["format"]
        if inhalt == b"":
            assert f["code"] == "import_datei_leer" and fmt is None
        elif f["code"] == "import_format_ungueltig":
            assert fmt is None
        elif inhalt[:2] == b"\x1f\x8b":
            assert fmt == "kmy-gzip"
        else:
            assert fmt == "kmy-xml"
        if inhalt and _weder_gzip_noch_xml(inhalt):
            assert f["code"] == "import_format_ungueltig"


def _weder_gzip_noch_xml(b: bytes) -> bool:
    """Sicher weder gzip noch XML, egal welche Leerraumzeichen die Anwendung überspringt."""
    rest = b[3:] if b.startswith(b"\xef\xbb\xbf") else b
    return b[:2] != b"\x1f\x8b" and not rest.lstrip().startswith(b"<") and b"<" not in rest[:1].lstrip()


@given(st.binary(min_size=1, max_size=200).filter(_weder_gzip_noch_xml))
def test_weder_gzip_noch_xml(api_fabrik, inhalt):
    importiere_fehlerhaft(api_fabrik(), inhalt, "import_format_ungueltig", None)


@pytest.mark.kern
@given(st.integers(min_value=0, max_value=200), st.sampled_from(["konto", "wert", "datum"]))
def test_kein_teilimport_bei_fehler_an_beliebiger_stelle(api_fabrik, position, art):
    """Ein Fehler in einer beliebigen Transaktion von standard_bis_2023 verhindert jeden Import."""
    w = ET.fromstring(gzip.decompress((KMY / "standard_bis_2023.kmy").read_bytes()))
    transaktionen = w.findall("TRANSACTIONS/TRANSACTION")
    t = transaktionen[position * len(transaktionen) // 201]
    s = t.find("SPLITS/SPLIT")
    if art == "konto":
        s.set("account", "A999999")
    elif art == "wert":
        s.set("value", "1/7")
    else:
        t.set("postdate", "2023-02-29")
    api = api_fabrik()
    importiere_fehlerhaft(api, packe_gzip(als_bytes(w, KOPF)), "import_inhalt_ungueltig", "kmy-gzip")
    assert api.konten() == [] and api.alle_buchungen() == []
