"""KMyMoney-Import: vollständige und exakte Übernahme, Sonderfälle (K 12, T 5, datenmodell.md 10).

Erwartungswerte stammen aus den Erwartungsdateien des Generators (bekannte
Wahrheit) oder werden im Test unabhängig hergeleitet.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from generator.iban import fiktive_iban
from tests.hilfen import kontor
from tests.hilfen.api import neue_config
from tests.hilfen.erwartung import ZAEHLFELDER, lade, pruefe_buchbestand, pruefe_ergebnis
from tests.hilfen.kmybau import (KBuch, KBuchung, KKonto, KSplit, als_bytes, gzip_bytes, konto, minimal_baum,
                                 packe_gzip, split, transaktion, veraendert)
from tests.hilfen.pfade import KMY
from tests.hilfen.vertrag import ohne, vertrag

GUELTIG = ["minimal", "minimal_unkomprimiert", "sonderfaelle", "fremdwaehrung",
           pytest.param("standard", marks=pytest.mark.langsam),
           pytest.param("standard_bis_2023", marks=pytest.mark.langsam)]


def _invarianten(api, erw):
    for b in api.alle_buchungen():
        assert len(b["splits"]) >= 2 and sum(s["betrag"] for s in b["splits"]) == 0, b["extern_ids"]
    u = api.uebersicht()
    assert u["summe_gesamt"] == 0
    assert u["summe_bestand"] == erw["summen"]["summe_bestand"]


@pytest.mark.kern
@pytest.mark.parametrize("name", GUELTIG)
def test_import_rest_exakt(api, name):
    erw = lade(name)
    r = api.import_kmy(KMY / f"{name}.kmy", erwartet=200)
    pruefe_ergebnis(r.daten, erw["ergebnis"], warnungen=erw["warnungen"])
    assert isinstance(r.daten["import_id"], int)
    pruefe_buchbestand(api, erw)
    _invarianten(api, erw)


@pytest.mark.parametrize("name", ["minimal", "sonderfaelle", "fremdwaehrung"])
def test_import_python_api_exakt(tmp_path, name):
    """importiere_kmy mit Pfad; eine vorher erzeugte App sieht das Ergebnis sofort."""
    from tests.hilfen.api import Api

    erw = lade(name)
    config = neue_config(tmp_path)
    api = Api(config)
    ergebnis = kontor.importiere_kmy(config, KMY / f"{name}.kmy")
    erg_cls = kontor.modul("kontor.importer.ergebnis").ImportErgebnis
    assert isinstance(ergebnis, erg_cls)
    d = ergebnis.als_dict()
    fehler = list(vertrag().schema_validator("ImportErgebnis").iter_errors(d))
    assert not fehler, f"als_dict() verletzt das Schema ImportErgebnis: {fehler[0].message}"
    assert json.loads(json.dumps(d)) == d, "als_dict() muss JSON-serialisierbar sein"
    pruefe_ergebnis(d, erw["ergebnis"], warnungen=erw["warnungen"])
    assert isinstance(ergebnis.warnungen, tuple) and isinstance(ergebnis.fehler, tuple)
    for w, wd in zip(ergebnis.warnungen, d["warnungen"]):
        assert {"code": w.code, "meldung": w.meldung, "referenz": w.referenz} == wd
    for f in ZAEHLFELDER:
        assert getattr(ergebnis, f) == d[f]
    assert ergebnis.erfolgreich is True and ergebnis.format == erw["ergebnis"]["format"]
    pruefe_buchbestand(api, erw)
    importe = api.get("/api/importe", erwartet=200).daten
    assert [i["id"] for i in importe] == [ergebnis.import_id]
    assert importe[0]["dateiname"] == f"{name}.kmy"
    assert importe[0]["ergebnis"] == d


def test_import_python_api_bytes(tmp_path):
    from tests.hilfen.api import Api

    config = neue_config(tmp_path)
    inhalt = (KMY / "minimal.kmy").read_bytes()
    e1 = kontor.importiere_kmy(config, inhalt)
    e2 = kontor.importiere_kmy(config, inhalt, dateiname="haushalt.kmy")
    assert e1.erfolgreich and e2.erfolgreich
    importe = Api(config).get("/api/importe", erwartet=200).daten
    assert [(i["id"], i["dateiname"]) for i in importe] == [(e1.import_id, None), (e2.import_id, "haushalt.kmy")]
    assert all(i["sha256"] == hashlib.sha256(inhalt).hexdigest() for i in importe)


def test_import_python_api_pfad_als_str_und_dateiname(tmp_path):
    from tests.hilfen.api import Api

    config = neue_config(tmp_path)
    e = kontor.importiere_kmy(config, str(KMY / "minimal.kmy"), dateiname="anders.kmy")
    assert e.erfolgreich
    assert Api(config).get("/api/importe", erwartet=200).daten[0]["dateiname"] == "anders.kmy"


def test_import_python_api_legt_datenbank_an(tmp_path):
    config = neue_config(tmp_path / "neu" / "verzeichnis")
    assert kontor.importiere_kmy(config, KMY / "minimal.kmy").erfolgreich
    assert config.aktive_datenbank.exists()


def test_import_python_api_ausnahmen(tmp_path):
    config = neue_config(tmp_path)
    with pytest.raises(FileNotFoundError):
        kontor.importiere_kmy(config, tmp_path / "gibtsnicht.kmy")
    for falsch in (42, None, ["a"], 3.5):
        with pytest.raises(TypeError):
            kontor.importiere_kmy(config, falsch)


def test_importvorgang(api):
    roh = (KMY / "minimal.kmy").read_bytes()
    r = api.post("/api/import/kmymoney", files={"datei": ("Mein Buch – Ärger.kmy", roh, "application/gzip")},
                 erwartet=200).daten
    importe = api.get("/api/importe", erwartet=200).daten
    assert len(importe) == 1
    i = importe[0]
    assert i["id"] == r["import_id"] and i["art"] == "kmymoney"
    assert i["dateiname"] == "Mein Buch – Ärger.kmy"
    assert i["sha256"] == hashlib.sha256(roh).hexdigest()
    assert i["ergebnis"] == r
    r2 = api.import_kmy(KMY / "minimal_unkomprimiert.kmy", erwartet=200).daten
    importe = api.get("/api/importe", erwartet=200).daten
    assert [x["id"] for x in importe] == [r["import_id"], r2["import_id"]] and r2["import_id"] > r["import_id"]
    assert importe[1]["sha256"] == hashlib.sha256((KMY / "minimal_unkomprimiert.kmy").read_bytes()).hexdigest()


def test_import_ohne_datei(api):
    r = api.post("/api/import/kmymoney", files={"anders": ("x.kmy", b"abc", "application/octet-stream")},
                 erwartet=422)
    assert r.json()["fehler"]["code"] == "validierung"
    assert api.get("/api/importe", erwartet=200).daten == []


def test_rest_und_python_gleich(tmp_path):
    """POST /api/import/kmymoney verhält sich wie importiere_kmy (python-api.md 5)."""
    from tests.hilfen.api import Api

    c1, c2 = neue_config(tmp_path / "a"), neue_config(tmp_path / "b")
    a1, a2 = Api(c1), Api(c2)
    d1 = a1.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200).daten
    d2 = kontor.importiere_kmy(c2, KMY / "sonderfaelle.kmy").als_dict()

    def ohne_id(d):
        aus = ohne(d, "import_id")  # E-124: Antwortobjekt bleibt erhalten
        aus["warnungen"] = sorted((w["code"], w["referenz"]) for w in d["warnungen"])
        return aus
    assert ohne_id(d1) == ohne_id(d2)


# ---------------------------------------------------------- Einzelregeln


def test_unkomprimiert_mit_bom(api):
    roh = b"\xef\xbb\xbf" + (KMY / "minimal_unkomprimiert.kmy").read_bytes()
    r = api.post("/api/import/kmymoney", files={"datei": ("bom.kmy", roh, "application/xml")}, erwartet=200).daten
    assert r["format"] == "kmy-xml" and r["buchungen_neu"] == 2


def test_unkomprimiert_mit_fuehrendem_leerraum(api):
    """Ohne XML-Deklaration darf Leerraum vor dem Wurzelelement stehen (vor <?xml wäre es nicht wohlgeformt)."""
    roh = (KMY / "minimal_unkomprimiert.kmy").read_bytes()
    roh = b"\xef\xbb\xbf\n  \r\n\t" + roh[roh.index(b"<!DOCTYPE"):]
    r = api.post("/api/import/kmymoney", files={"datei": ("ws.kmy", roh, "application/xml")}, erwartet=200).daten
    assert r["format"] == "kmy-xml" and r["buchungen_neu"] == 2


def test_ohne_doctype(api):
    roh = (KMY / "minimal_unkomprimiert.kmy").read_bytes().replace(b"<!DOCTYPE KMYMONEY-FILE>\n", b"")
    assert b"DOCTYPE" not in roh
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", packe_gzip(roh), "application/gzip")},
                 erwartet=200).daten
    assert r["format"] == "kmy-gzip" and r["buchungen_neu"] == 2


def test_externe_dtd_wird_nicht_geladen(api, netz_gesperrt):
    """Eine externe DTD wird nie geladen; Import gelingt oder wird als Formatfehler abgelehnt."""
    roh = (KMY / "minimal_unkomprimiert.kmy").read_bytes().replace(
        b"<!DOCTYPE KMYMONEY-FILE>", b'<!DOCTYPE KMYMONEY-FILE SYSTEM "http://kontor.example.invalid/kmy.dtd">')
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", roh, "application/xml")})
    assert r.status_code in (200, 422), r.text
    if r.status_code == 422:
        assert r.json()["fehler"]["code"] == "import_format_ungueltig"


def test_datum_mit_zeitanteil(api):
    def eingriff(w):
        transaktion(w, 0).set("postdate", "2024-01-31T23:59:59")
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", veraendert(eingriff), "x")}, erwartet=200)
    assert r.daten["buchungen_neu"] == 2
    assert sorted(b["datum"] for b in api.alle_buchungen()) == ["2024-01-31", "2024-02-02"]


@pytest.mark.parametrize("wert,cent", [("12", 1200), ("-617/50", -1234), ("1230/1000", 123), ("5/1", 500),
                                       ("0/100", 0), ("999999999999/100", 999_999_999_999), ("-999999999999/100", -999_999_999_999),
                                       ("-1/100", -1), ("7/10", 70)])
def test_betragsformate(api, wert, cent):
    def eingriff(w):
        split(w, 0, 0).set("value", wert)
        split(w, 0, 1).set("value", wert[1:] if wert.startswith("-") else "-" + wert)
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", veraendert(eingriff), "x")}, erwartet=200).daten
    assert r["warnungen"] == []
    b = next(b for b in api.alle_buchungen() if b["extern_ids"] == ["kmy:T000000000000000001"])
    assert [s["betrag"] for s in b["splits"]] == [cent, -cent]


@pytest.mark.parametrize("wert", ["yes", "YES", "Yes"])
def test_geschlossen_gross_klein(api, wert):
    def eingriff(w):
        konto(w, "A000001").find("KEYVALUEPAIRS").append(ET.Element("PAIR", key="mm-closed", value=wert))
    api.post("/api/import/kmymoney", files={"datei": ("x.kmy", veraendert(eingriff), "x")}, erwartet=200)
    giro = next(k for k in api.konten() if k["extern_id"] == "kmy:A000001")
    assert giro["geschlossen"] is True


def test_nicht_geschlossen_bei_anderem_wert(api):
    def eingriff(w):
        konto(w, "A000001").find("KEYVALUEPAIRS").append(ET.Element("PAIR", key="mm-closed", value="no"))
    api.post("/api/import/kmymoney", files={"datei": ("x.kmy", veraendert(eingriff), "x")}, erwartet=200)
    assert next(k for k in api.konten() if k["extern_id"] == "kmy:A000001")["geschlossen"] is False


def test_ignorierte_attribute(api):
    """shares, price, reconcileflag, action, number, bankid beeinflussen den Import nicht."""
    def eingriff(w):
        for s in w.iter("SPLIT"):
            s.set("shares", "999/1")
            s.set("price", "7/3")
            s.set("reconcileflag", "2")
            s.set("action", "Withdrawal")
            s.set("number", "4711")
            s.set("bankid", "XYZ")
    api.post("/api/import/kmymoney", files={"datei": ("x.kmy", veraendert(eingriff), "x")}, erwartet=200)
    pruefe_buchbestand(api, lade("minimal"))


def test_iban_nur_bei_bestandskonten(api):
    def eingriff(w):
        a = konto(w, "A000002")  # Kategorie Lebensmittel
        kv = ET.SubElement(a, "KEYVALUEPAIRS")
        ET.SubElement(kv, "PAIR", key="iban", value=fiktive_iban(8888))
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", veraendert(eingriff), "x")}, erwartet=200).daten
    assert not [w for w in r["warnungen"] if w["referenz"] == "A000002"]
    assert next(k for k in api.konten() if k["extern_id"] == "kmy:A000002")["iban"] is None


# Unabhängige Tabelle aus datenmodell.md 10.2
TYPEN = {
    1: ("girokonto", None), 2: ("sparkonto", None), 6: ("sparkonto", None), 8: ("sparkonto", None),
    3: ("girokonto", "kontoart_ersetzt"), 9: ("sparkonto", "kontoart_ersetzt"),
    14: ("sparkonto", "kontoart_ersetzt"),
    4: ("kreditkonto", None), 5: ("kreditkonto", None), 10: ("kreditkonto", None),
    12: ("ertrag", None), 13: ("aufwand", None), 16: ("eigenkapital", None),
    0: (None, "konto_uebersprungen"), 7: (None, "konto_uebersprungen"), 11: (None, "konto_uebersprungen"),
    15: (None, "konto_uebersprungen"), 99: (None, "konto_uebersprungen"),
}
STANDARD_ELTERN = {4: "AStd::Liability", 5: "AStd::Liability", 10: "AStd::Liability", 12: "AStd::Income",
                   13: "AStd::Expense", 16: "AStd::Equity"}


@pytest.mark.parametrize("typ", sorted(TYPEN))
def test_kontotypen(api, typ):
    art, warnung = TYPEN[typ]
    b = KBuch()
    b.konten = [KKonto("A000001", "Testkonto", typ, STANDARD_ELTERN.get(typ, "AStd::Asset")),
                KKonto("A000002", "Diverses", 13, "AStd::Expense")]
    b.buchungen = [KBuchung("T000000000000000001", "2024-01-01",
                            [KSplit("A000001", 1000), KSplit("A000002", -1000)])]
    r = api.post("/api/import/kmymoney", files={"datei": ("t.kmy", gzip_bytes(b), "x")}, erwartet=200).daten
    codes = sorted((w["code"], w["referenz"]) for w in r["warnungen"])
    konten = {k["extern_id"]: k for k in api.konten()}
    if art is None:
        assert codes == [("buchung_uebersprungen", "T000000000000000001"), ("konto_uebersprungen", "A000001")]
        assert "kmy:A000001" not in konten
        assert (r["buchungen_neu"], r["buchungen_uebersprungen"], r["konten_neu"], r["kategorien_neu"]) == (0, 1, 0, 1)
        assert api.alle_buchungen() == []
        return
    assert codes == ([(warnung, "A000001")] if warnung else [])
    k = konten["kmy:A000001"]
    assert k["art"] == art and k["eltern_id"] is None and k["name"] == "Testkonto"
    ist_kat = art in ("aufwand", "ertrag")
    assert (r["konten_neu"], r["kategorien_neu"]) == ((0, 2) if ist_kat else (1, 1))
    assert r["buchungen_neu"] == 1 and api.salden()[k["id"]]["saldo"] == 1000


def test_fremdwaehrung_konto_und_buchung(api):
    """Konto ≠ EUR und TRANSACTION@commodity ≠ EUR werden übersprungen (E-006)."""
    erw = lade("fremdwaehrung")
    r = api.import_kmy(KMY / "fremdwaehrung.kmy", erwartet=200).daten
    assert r["buchungen_uebersprungen"] == 4
    ext = {k["extern_id"] for k in api.konten()}
    assert not ext & {"kmy:A000002", "kmy:A000003", "kmy:A000004"}
    unter = next(k for k in api.konten() if k["extern_id"] == "kmy:A000005")
    assert unter["eltern_id"] is None and unter["iban"] == fiktive_iban(5005)
    pruefe_buchbestand(api, erw)


def test_unausgeglichen_wiederverwendet(api):
    """Ausgleichssplits gehen auf genau ein technisches Konto, auch über mehrere Importe."""
    api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    b = KBuch()
    b.konten = [KKonto("A000001", "Girokonto Ünïcödé & <Test> \"Haupt\"", 1, "AStd::Asset")]
    b.buchungen = [KBuchung("T000000000000000099", "2024-05-01", [KSplit("A000001", -777)])]
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", gzip_bytes(b), "x")}, erwartet=200).daten
    assert (r["konten_neu"], r["konten_vorhanden"], r["splits_neu"]) == (0, 1, 2)
    assert [(w["code"], w["referenz"]) for w in r["warnungen"]] == [("buchung_ausgeglichen", "T000000000000000099")]
    unaus = [k for k in api.konten() if k["extern_id"] == "kontor:unausgeglichen"]
    assert len(unaus) == 1
    u = unaus[0]
    assert (u["name"], u["art"], u["eltern_id"], u["iban"], u["geschlossen"], u["notiz"]) == \
        ("Unausgeglichen", "eigenkapital", None, None, False, "")
    assert api.salden()[u["id"]]["saldo"] == 1099 + 777


def test_nur_ein_split_mit_null(api):
    b = KBuch()
    b.konten = [KKonto("A000001", "Giro", 1, "AStd::Asset")]
    b.buchungen = [KBuchung("T000000000000000001", "2024-05-01", [KSplit("A000001", 0)])]
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", gzip_bytes(b), "x")}, erwartet=200).daten
    assert r["splits_neu"] == 2 and r["konten_neu"] == 1
    (buchung,) = api.alle_buchungen()
    assert [s["betrag"] for s in buchung["splits"]] == [0, 0]
    unaus = next(k for k in api.konten() if k["extern_id"] == "kontor:unausgeglichen")
    assert buchung["splits"][1]["konto_id"] == unaus["id"]


def test_ausgleich_ist_kategorisierbar(api):
    """Eine ausgeglichene Ein-Split-Buchung lässt sich nachträglich kategorisieren (E-012)."""
    erw = lade("sonderfaelle")
    api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    b = next(x for x in api.alle_buchungen() if x["verwendungszweck"] == "Buchung ohne Gegenbuchung")
    assert b["kategorie_id"] is None
    kat = next(k for k in api.konten() if k["extern_id"] == "kmy:A000014")
    r = api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": kat["id"]}, erwartet=200).daten
    assert r["kategorie_id"] == kat["id"]
    unaus = next(k for k in api.konten() if k["extern_id"] == "kontor:unausgeglichen")
    soll = next(k for k in erw["konten"] if k["extern_id"] == "kontor:unausgeglichen")["saldo"]
    assert api.salden()[unaus["id"]]["saldo"] == soll - 999


def test_empfaenger_vom_ersten_split_mit_payee(api):
    api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    b = next(x for x in api.alle_buchungen() if x["verwendungszweck"] == "Empfänger am zweiten Split")
    assert b["empfaenger"]["name"] == "Bäckerei Größenwahn – Inh. Jürgen Weiß"
    ohne = next(x for x in api.alle_buchungen() if x["extern_ids"] == ["kmy:T000000000000000005"])
    assert ohne["empfaenger"] is None and ohne["verwendungszweck"] == ""


def test_langer_verwendungszweck_unveraendert(api):
    from generator.szenarien import LANGER_TEXT

    api.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    assert any(b["verwendungszweck"] == LANGER_TEXT for b in api.alle_buchungen())
    assert len(LANGER_TEXT) == 5000


def test_neue_xml_bytes_aus_baum_identisch(api):
    """Selbstkontrolle der Testhilfe: minimal_baum() ergibt eine gleichwertige Datei."""
    roh = packe_gzip(als_bytes(minimal_baum()))
    api.post("/api/import/kmymoney", files={"datei": ("x.kmy", roh, "x")}, erwartet=200)
    pruefe_buchbestand(api, lade("minimal"))
