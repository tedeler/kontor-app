"""M4: GnuCash-Import aus XML (gzip/unkomprimiert) und SQLite – vollständig und exakt (gnucash.md, K 12, T 5).

Erwartungswerte stammen aus den Erwartungsdateien des Generators (bekannte
Wahrheit, aus dem Modell berechnet) oder für zufällige Bücher aus derselben
Erwartungsberechnung des Generators – nie aus einer Antwort der Anwendung.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import string

import pytest
from hypothesis import given, strategies as st

from generator.gnucash import GBuch, GBuchung, GKonto, GSplit, als_gnc_sqlite, als_gnc_xml, gnc_erwartung, guid
from generator.iban import fiktive_iban
from generator.kmy import FEHLT, packe_gzip
from tests.hilfen import kontor
from tests.hilfen.api import Api, neue_config
from tests.hilfen.erwartung import ZAEHLFELDER, pruefe_buchbestand, pruefe_ergebnis
from tests.hilfen.m3 import alle_aenderungen
from tests.hilfen.m4 import GNC, gnc_erwartung as lade_erw, import_gnc
from tests.hilfen.normal import eindeutiger_name
from tests.hilfen.vertrag import vertrag

GUELTIG = ["minimal", "minimal_unkomprimiert", "minimal.sqlite", "sonderfaelle", "sonderfaelle.sqlite",
           pytest.param("standard", marks=pytest.mark.langsam)]


def _invarianten(api, erw):
    for b in api.alle_buchungen():
        assert len(b["splits"]) >= 2 and sum(s["betrag"] for s in b["splits"]) == 0, b["extern_ids"]
        assert b["status"] == "importiert" and b["vorschlag"] is None and b["tags"] == []
    u = api.uebersicht()
    assert u["summe_gesamt"] == 0
    assert u["summe_bestand"] == erw["summen"]["summe_bestand"]


@pytest.mark.kern
@pytest.mark.parametrize("name", GUELTIG)
def test_import_rest_exakt(api, name):
    erw = lade_erw(name)
    r = import_gnc(api, GNC / f"{name}.gnucash")
    pruefe_ergebnis(r.daten, erw["ergebnis"], warnungen=erw["warnungen"])
    assert isinstance(r.daten["import_id"], int)
    pruefe_buchbestand(api, erw)
    _invarianten(api, erw)


def test_xml_und_sqlite_ergeben_denselben_bestand(api_fabrik):
    """Dasselbe Buch als gzip-XML, XML und SQLite ergibt denselben Buchbestand (bis auf das Format)."""
    zustaende = []
    for name in ("minimal", "minimal_unkomprimiert", "minimal.sqlite"):
        a = api_fabrik()
        r = import_gnc(a, GNC / f"{name}.gnucash").daten
        zustaende.append((a.zustand(), {f: r[f] for f in ZAEHLFELDER}))
    assert zustaende[0] == zustaende[1] == zustaende[2]


@pytest.mark.kern
def test_importvorgang_und_protokoll(api):
    inhalt = (GNC / "minimal.sqlite.gnucash").read_bytes()
    r = import_gnc(api, inhalt, dateiname="haushalt.gnucash").daten
    (iv,) = api.get("/api/importe", erwartet=200).daten
    assert (iv["id"], iv["art"], iv["dateiname"], iv["sha256"]) == (r["import_id"], "gnucash", "haushalt.gnucash",
                                                                     hashlib.sha256(inhalt).hexdigest())
    assert iv["ergebnis"] == r
    (a,) = alle_aenderungen(api)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("import", "import_gnucash", f"import:{r['import_id']}")


@pytest.mark.parametrize("name", ["minimal", "minimal.sqlite", "sonderfaelle"])
def test_import_python_api_exakt(tmp_path, name):
    """importiere_gnucash mit Pfad; eine vorher erzeugte App sieht das Ergebnis sofort (python-api.md 10.2)."""
    erw = lade_erw(name)
    config = neue_config(tmp_path)
    api = Api(config)
    m = kontor.modul("kontor.importer.gnucash")
    ergebnis = m.importiere_gnucash(config, GNC / f"{name}.gnucash")
    assert isinstance(ergebnis, kontor.modul("kontor.importer.ergebnis").ImportErgebnis)
    d = ergebnis.als_dict()
    fehler = list(vertrag().schema_validator("ImportErgebnis").iter_errors(d))
    assert not fehler, f"als_dict() verletzt das Schema ImportErgebnis: {fehler[0].message}"
    assert json.loads(json.dumps(d)) == d
    pruefe_ergebnis(d, erw["ergebnis"], warnungen=erw["warnungen"])
    assert ergebnis.erfolgreich is True and ergebnis.format == erw["ergebnis"]["format"]
    pruefe_buchbestand(api, erw)
    (iv,) = api.get("/api/importe", erwartet=200).daten
    assert (iv["dateiname"], iv["art"], iv["ergebnis"]) == (f"{name}.gnucash", "gnucash", d)
    (a,) = alle_aenderungen(api)
    assert (a["quelle"], a["aktion"]) == ("import", "import_gnucash")


def test_import_python_api_bytes_und_fehler(tmp_path):
    config = neue_config(tmp_path)
    m = kontor.modul("kontor.importer.gnucash")
    e = m.importiere_gnucash(config, (GNC / "minimal.gnucash").read_bytes(), dateiname="aus-bytes.gnucash")
    assert e.erfolgreich
    api = Api(config)
    assert api.get("/api/importe", erwartet=200).daten[0]["dateiname"] == "aus-bytes.gnucash"
    with pytest.raises(FileNotFoundError):
        m.importiere_gnucash(config, tmp_path / "gibt-es-nicht.gnucash")
    with pytest.raises(TypeError):
        m.importiere_gnucash(config, 12345)
    leer = m.importiere_gnucash(config, b"")
    assert (leer.erfolgreich, leer.import_id, leer.fehler[0].code) == (False, None, "import_datei_leer")


@pytest.mark.kern
@pytest.mark.parametrize("name", ["minimal", "minimal.sqlite", "sonderfaelle", "sonderfaelle.sqlite"])
def test_zweimal_importieren_aendert_nichts(api, name):
    """T 3.7: Der zweite Import ändert keinen Buchbestand und erzeugt keine Änderung im Protokoll."""
    erw = lade_erw(name)
    import_gnc(api, GNC / f"{name}.gnucash")
    vorher = api.zustand()
    n_aend = len(alle_aenderungen(api))
    r = import_gnc(api, GNC / f"{name}.gnucash").daten
    assert api.zustand() == vorher
    assert len(alle_aenderungen(api)) == n_aend
    e = erw["ergebnis"]
    assert {f: r[f] for f in ZAEHLFELDER} == {
        "konten_neu": 0, "konten_vorhanden": e["konten_neu"], "kategorien_neu": 0,
        "kategorien_vorhanden": e["kategorien_neu"], "empfaenger_neu": 0, "empfaenger_vorhanden": e["empfaenger_neu"],
        "tags_neu": 0, "tags_vorhanden": 0, "buchungen_neu": 0, "buchungen_vorhanden": e["buchungen_neu"],
        "buchungen_zusammengefuehrt": 0, "buchungen_zur_pruefung": 0,
        "buchungen_uebersprungen": e["buchungen_uebersprungen"], "splits_neu": 0}
    assert len(api.get("/api/importe", erwartet=200).daten) == 2


def _minimal_gbuch(zusatz: int = 0) -> GBuch:
    g = lambda n: guid("erw:" + n)  # noqa: E731
    gb = GBuch(g("buch"), g("root"))
    gb.konten = [GKonto(g("giro"), "Girokonto", "BANK", gb.root_guid, code=fiktive_iban(7101)),
                 GKonto(g("leb"), "Lebensmittel", "EXPENSE", gb.root_guid),
                 GKonto(g("ob"), "Obst", "EXPENSE", g("leb"))]
    for n in range(2 + zusatz):
        gb.buchungen.append(GBuchung(g(f"t{n}"), f"2024-03-{n + 1:02d} 10:59:00 +0000",
                                     [GSplit(g("giro"), -100 - n, guid=g(f"s{n}a")),
                                      GSplit(g("ob" if n % 2 else "leb"), 100 + n, guid=g(f"s{n}b"))],
                                     beschreibung="Markt" if n % 3 else "Bäckerei", notiz=f"Einkauf {n}"))
    return gb


@pytest.mark.kern
@pytest.mark.parametrize("fmt", ["gnc-xml", "gnc-sqlite"])
def test_erweiterte_fassung_fuegt_genau_das_neue_hinzu(api, fmt):
    schreib = (lambda b: als_gnc_sqlite(b)) if fmt == "gnc-sqlite" else als_gnc_xml
    import_gnc(api, schreib(_minimal_gbuch()))
    vorher = {e for b in api.alle_buchungen() for e in b["extern_ids"]}
    r = import_gnc(api, schreib(_minimal_gbuch(zusatz=3))).daten
    assert (r["buchungen_neu"], r["buchungen_vorhanden"], r["konten_neu"], r["kategorien_neu"]) == (3, 2, 0, 0)
    assert (r["empfaenger_neu"], r["empfaenger_vorhanden"]) == (0, 2)
    nachher = {e for b in api.alle_buchungen() for e in b["extern_ids"]}
    assert nachher - vorher == {"gnc:" + guid(f"erw:t{n}") for n in (2, 3, 4)}


def test_geloeschte_buchung_wird_neu_importiert(api):
    import_gnc(api, GNC / "minimal.gnucash")
    b = api.alle_buchungen()[0]
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    r = import_gnc(api, GNC / "minimal.gnucash").daten
    assert (r["buchungen_neu"], r["buchungen_vorhanden"]) == (1, 1)
    assert any(x["extern_ids"] == b["extern_ids"] for x in api.alle_buchungen())


def test_zugeordnete_objekte_bleiben_unveraendert(api):
    """gnucash.md 7: Kontor ist nach dem Import führend."""
    import_gnc(api, GNC / "minimal.gnucash")
    giro = next(k for k in api.konten() if k["art"] == "girokonto")
    api.patch(f"/api/konten/{giro['id']}", json={"name": "Umbenannt", "notiz": "eigene Notiz"}, erwartet=200)
    b = api.alle_buchungen()[0]
    api.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "geändert"}, erwartet=200)
    vorher = api.zustand()
    import_gnc(api, GNC / "minimal.gnucash")
    assert api.zustand() == vorher


def test_sonderfaelle_einzeln(api):
    """Ausgewählte Sonderfälle von T 5 ausdrücklich (zusätzlich zum Gesamtvergleich)."""
    erw = lade_erw("sonderfaelle")
    import_gnc(api, GNC / "sonderfaelle.gnucash")
    konten = {k["extern_id"]: k for k in api.konten()}
    g = lambda n: "gnc:" + guid(f"sonder:{n}")  # noqa: E731
    assert konten[g("giro")]["iban"] == fiktive_iban(6001), "IBAN aus Kontonummer, normalisiert"
    assert konten[g("karte")]["iban"] is None, "Kontonummer 1200 ist keine IBAN"
    assert konten[g("alt")]["geschlossen"] is True
    assert konten[g("doppelt")]["iban"] is None
    assert konten[g("kasse")]["art"] == "girokonto" and konten[g("anlage")]["art"] == "sparkonto"
    assert konten[g("verbindl")]["art"] == "kreditkonto" and konten[g("forderung")]["art"] == "sparkonto"
    assert g("depot") not in konten and g("usd") not in konten
    assert konten[g("unterdepot")]["eltern_id"] is None, "Elternkonto übersprungen → Wurzelkonto"
    assert konten[g("falschkat")]["eltern_id"] is None, "Elternkonto anderer Klasse → Wurzelkonto"
    assert konten[g("kino")]["eltern_id"] == konten[g("freizeit")]["id"], "Platzhalterkonten werden übernommen"
    bs = {e: b for b in api.alle_buchungen() for e in b["extern_ids"]}
    emoji = [b for b in bs.values() if b["empfaenger"] and "Emoji" in b["empfaenger"]["name"]]
    assert {b["empfaenger"]["name"] for b in emoji} == {"☕ Emoji-Kiosk 🙂"}, "Beschreibung mit strip()"
    lang = max(bs.values(), key=lambda b: len(b["verwendungszweck"]))
    assert len(lang["verwendungszweck"]) == 5000
    assert max(len(b["splits"]) for b in bs.values()) == 13
    namen = sorted(e["name"] for e in api.get("/api/empfaenger", erwartet=200).daten)
    assert namen == sorted(e["name"] for e in erw["empfaenger"])
    assert all(e["extern_id"] is None for e in api.get("/api/empfaenger", erwartet=200).daten)


def test_empfaenger_ueber_alias_zugeordnet(api):
    """gnucash.md 6.2: Beschreibung → exakter Name, sonst Alias, sonst neu (buchhaltungspflege.md 2.3)."""
    e = api.post("/api/empfaenger", json={"name": "Supermarkt Frischekorb GmbH",
                                          "aliase": ["SUPERMARKT FRISCHEKORB"]}, erwartet=201).daten
    r = import_gnc(api, GNC / "minimal.gnucash").daten
    assert (r["empfaenger_neu"], r["empfaenger_vorhanden"]) == (1, 1)
    b = next(b for b in api.alle_buchungen() if b["betrag"] == 2500)
    assert b["empfaenger"] == {"id": e["id"], "name": "Supermarkt Frischekorb GmbH"}
    assert api.get(f"/api/empfaenger/{e['id']}", erwartet=200).daten == e


# ------------------------------------------------------------- Hypothesis
NAMEN = st.text(string.ascii_letters + "äöüßÄ &<>\"'–☕", min_size=1, max_size=10)


@st.composite
def gnc_buch(draw) -> GBuch:
    nr = draw(st.integers(0, 10 ** 6))
    g = lambda n: guid(f"hyp{nr}:{n}")  # noqa: E731
    gb = GBuch(g("buch"), g("root"))
    konten = []
    vergeben = {"unausgeglichen"}  # M32: Kontonamen je Ebene eindeutig (E-307), hier über das ganze Buch
    for i in range(draw(st.integers(1, 3))):
        typ = draw(st.sampled_from(["BANK", "CREDIT", "CASH", "ASSET", "LIABILITY"]))
        code = draw(st.sampled_from(["", fiktive_iban(8100 + i), "4711"]))
        konten.append(GKonto(g(f"k{i}"), eindeutiger_name(draw(NAMEN), vergeben), typ, gb.root_guid, code=code, versteckt=draw(st.booleans()),
                             beschreibung=draw(st.sampled_from(["", "Notiz ä"]))))
    for j in range(draw(st.integers(1, 4))):
        typ = draw(st.sampled_from(["INCOME", "EXPENSE", "EQUITY", "STOCK"]))
        gleiche = [k for k in konten if k.typ == typ]
        eltern = draw(st.sampled_from(gleiche)).guid if gleiche and draw(st.booleans()) else gb.root_guid
        konten.append(GKonto(g(f"c{j}"), eindeutiger_name(draw(NAMEN), vergeben), typ, eltern))
    gb.konten = konten
    for n in range(draw(st.integers(0, 10))):
        k = draw(st.integers(1, 4))
        werte = draw(st.lists(st.integers(-50_000, 50_000), min_size=k, max_size=k))
        if k > 1 and draw(st.integers(0, 3)) > 0:
            werte[-1] = -sum(werte[:-1])
        splits = [GSplit(draw(st.sampled_from([x.guid for x in konten])), w,
                         memo=draw(st.sampled_from(["", "Memo ä&<", FEHLT])), guid=g(f"s{n}:{i}"))
                  for i, w in enumerate(werte)]
        d = draw(st.dates(min_value=dt.date(2020, 1, 1), max_value=dt.date(2025, 12, 31))).isoformat()
        gb.buchungen.append(GBuchung(g(f"t{n}"), f"{d} 10:59:00 +0000", splits,
                                     beschreibung=draw(st.sampled_from(["", "  Laden  ", "Laden", "Café Ä", FEHLT])),
                                     notiz=draw(st.sampled_from([FEHLT, "", "Zweck ü"])),
                                     waehrung=draw(st.sampled_from(["EUR", "EUR", "EUR", "USD"]))))
    return gb


@pytest.mark.kern
@given(gnc_buch(), st.sampled_from(["gnc-xml-gzip", "gnc-xml", "gnc-sqlite"]))
def test_zufaellige_buecher_exakt_und_idempotent(api_fabrik, buch, fmt):
    """Zufällige GnuCash-Bücher in allen drei Formaten: Wahrheit des Generators, danach idempotent."""
    erw = gnc_erwartung(buch, fixture="hypothesis", format_=fmt)
    daten = {"gnc-xml-gzip": lambda: packe_gzip(als_gnc_xml(buch)), "gnc-xml": lambda: als_gnc_xml(buch),
             "gnc-sqlite": lambda: als_gnc_sqlite(buch)}[fmt]()
    api = api_fabrik()
    r = import_gnc(api, daten).daten
    pruefe_ergebnis(r, erw["ergebnis"], warnungen=erw["warnungen"])
    pruefe_buchbestand(api, erw)
    assert api.uebersicht()["summe_gesamt"] == 0
    vorher = api.zustand()
    r2 = import_gnc(api, daten).daten
    assert api.zustand() == vorher
    assert r2["buchungen_neu"] == r2["konten_neu"] == r2["kategorien_neu"] == r2["empfaenger_neu"] == 0
