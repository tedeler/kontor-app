"""M19: ALF-BanCo-Import (QIF) über REST und Python (alfbanco.md 1–4, 6, 8; E-211 bis E-213).

Testdateien werden im Test gebaut (``tests/hilfen/m19.qif``); Erwartungen kommen aus der Definition und werden aus
den Sätzen selbst berechnet.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import Api, fehlercode, neue_api, neue_config
from tests.hilfen.m2 import mock_config
from tests.hilfen.m3 import UNKATEGORISIERT, aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m18 import bestand, ohne_wirkung, orte, pruefe_eintraege
from tests.hilfen.m19 import (
    BEISPIEL, CAT, KENNUNG, SAETZE, bank, erfolg, import_rest, importiere, kategorie, leer_ergebnis, qif, splits,
    warnungen, zaehler,
)

pytestmark = pytest.mark.kern


def _konten(api) -> dict:
    return {"giro": api.konto("Girokonto")["id"], "spar": api.konto("Sparkonto", "sparkonto")["id"]}


def _geschlossen(api, name: str, art: str) -> int:
    k = api.konto(name, art)["id"]
    api.patch(f"/api/konten/{k}", json={"geschlossen": True}, erwartet=200)
    return k


def _je_satz(api, konto_id) -> list[dict]:
    """Buchungen des Kontos nach (datum, id) – entspricht der Dateireihenfolge, wenn die Daten aufsteigen."""
    return sorted(api.alle_buchungen(konto_id=konto_id), key=lambda b: (b["datum"], b["id"]))


def _importe(api) -> list[dict]:
    return api.get("/api/importe", erwartet=200).daten


# ------------------------------------------------------------------ Beispiel (8)


def test_beispiel_windows1252(api):
    k = _konten(api)
    g, s = k["giro"], k["spar"]
    daten = qif(BEISPIEL)
    assert "Café".encode("cp1252") in daten
    a0, v0 = letzte_aenderung_id(api), bestand(api)
    e = erfolg(api, g, daten, dateiname="Girokonto.qif")
    assert e["format"] == "qif"
    assert zaehler(e) == {"konten_neu": 0, "konten_vorhanden": 0, "kategorien_neu": 4, "kategorien_vorhanden": 0,
                          "empfaenger_neu": 5, "empfaenger_vorhanden": 0, "tags_neu": 1, "tags_vorhanden": 0,
                          "buchungen_neu": 6, "buchungen_vorhanden": 0, "buchungen_zusammengefuehrt": 0,
                          "buchungen_zur_pruefung": 0, "buchungen_uebersprungen": 0, "splits_neu": 13}
    assert warnungen(e) == {("kategorieart_abgeleitet", "Kleidung")} and len(e["warnungen"]) == 1
    haus, leb = kategorie(api, "alf:kat:Haushalt"), kategorie(api, "alf:kat:Haushalt:Lebensmittel")
    gehalt, kleid = kategorie(api, "alf:kat:Gehalt"), kategorie(api, "alf:kat:Kleidung")
    assert (haus["name"], haus["art"], haus["eltern_id"]) == ("Haushalt", "aufwand", None)
    assert (leb["name"], leb["art"], leb["eltern_id"]) == ("Lebensmittel", "aufwand", haus["id"])
    assert (gehalt["art"], kleid["art"], kleid["name"]) == ("ertrag", "aufwand", "Kleidung")
    unk = kategorie(api, UNKATEGORISIERT)["id"]
    b = _je_satz(api, g)
    assert [x["datum"] for x in b] == ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06",
                                       "2024-01-06"]
    assert [splits(x) for x in b] == [
        [(g, -1234, ""), (leb["id"], 1234, "")],
        [(g, 250000, ""), (gehalt["id"], -250000, "")],
        [(g, -10000, ""), (s, 10000, "")],
        [(g, -5000, ""), (leb["id"], 3000, "Essen"), (kleid["id"], 2000, "Hose")],
        [(g, -300, ""), (unk, 300, "")],
        [(g, -300, ""), (unk, 300, "")],
    ]
    assert [x["empfaenger"]["name"] for x in b] == ["Supermarkt Beispiel", "Arbeitgeber Muster GmbH", "Sparen",
                                                     "Kaufhaus Beispiel", "Café Beispiel", "Café Beispiel"]
    assert [x["verwendungszweck"] for x in b] == ["Einkauf Woche 1", "Lohn Januar", "", "Gemischter Einkauf", "", ""]
    assert {x["status"] for x in b} == {"importiert"} and all(x["gegen_iban"] is None for x in b)
    assert [[t["name"] for t in x["tags"]] for x in b] == [[], ["Steuer"], [], [], [], []]
    kennungen = [x["extern_ids"] for x in b]
    assert all(len(x) == 1 and KENNUNG.match(x[0]) and KENNUNG.match(x[0])[1] == str(g) for x in kennungen)
    assert len({x[0] for x in kennungen}) == 6, "zwei gleiche Kaffees ergeben zwei Buchungen mit eigener Kennung"
    assert b[4]["empfaenger"]["id"] == b[5]["empfaenger"]["id"]
    # Folgerungen (4.8)
    salden = api.salden()
    assert salden[g]["saldo"] == -1234 + 250000 - 10000 - 5000 - 300 - 300
    assert salden[s]["saldo"] == 10000
    assert sum(x["saldo"] for x in salden.values()) == 0
    # Importvorgang und Protokoll
    (vorgang,) = _importe(api)
    assert (vorgang["art"], vorgang["dateiname"], vorgang["sha256"]) == (
        "alfbanco", "Girokonto.qif", hashlib.sha256(daten).hexdigest())
    assert vorgang["ergebnis"] == e and e["import_id"] == vorgang["id"]
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("import", "import_alfbanco", f"import:{vorgang['id']}")
    pruefe_eintraege(a, v0, bestand(api))


@pytest.mark.parametrize("kodierung", ["utf8_bom", "utf8", "latin1_fallback", "lf", "cr"])
def test_kodierung_und_zeilenenden(api, kodierung):
    k = _konten(api)
    if kodierung == "utf8_bom":
        daten = qif(BEISPIEL, kodierung="utf-8", bom=True)
    elif kodierung == "utf8":
        daten = qif(BEISPIEL, kodierung="utf-8", zeilenende="\n")
    elif kodierung == "lf":
        daten = qif(BEISPIEL, zeilenende="\n")
    elif kodierung == "cr":
        daten = qif(BEISPIEL, zeilenende="\r")
    else:
        # 0x8F ist in Windows-1252 nicht belegt → Latin-1 (3.2)
        daten = qif(BEISPIEL[:-1] + [["D07.01.2024", "T-1,00", "PCafé Beispiel", "MEnde\u008f"]], kodierung="latin-1")
    e = erfolg(api, k["giro"], daten)
    assert e["kategorien_neu"] == 4 and e["empfaenger_neu"] == 5
    namen = {x["empfaenger"]["name"] for x in api.alle_buchungen(konto_id=k["giro"])}
    assert "Café Beispiel" in namen
    if kodierung == "latin1_fallback":
        assert "Ende\u008f" in {x["verwendungszweck"] for x in api.alle_buchungen()}


# ------------------------------------------------------------------ Idempotenz und Kennung (4.4)


def test_idempotenz_und_erweiterte_fassung(api):
    k = _konten(api)
    daten = qif(BEISPIEL)
    e1 = erfolg(api, k["giro"], daten)
    z = bestand(api)
    a0 = letzte_aenderung_id(api)
    e2 = erfolg(api, k["giro"], daten)
    assert bestand(api) == z and aenderungen_seit(api, a0) == [], "zweiter Import ändert keinen Buchbestand"
    assert zaehler(e2) == {**{f: 0 for f in zaehler(e1)}, "kategorien_vorhanden": 4, "empfaenger_vorhanden": 5,
                           "tags_vorhanden": 1, "buchungen_vorhanden": 6}
    assert len(_importe(api)) == 2 and e2["import_id"] != e1["import_id"]
    # erweiterte Fassung: ein dritter gleicher Kaffee am Ende
    e3 = erfolg(api, k["giro"], qif(BEISPIEL + [["D06.01.2024", "T-3,00", "PCafé Beispiel"]]))
    assert (e3["buchungen_neu"], e3["buchungen_vorhanden"], e3["splits_neu"]) == (1, 6, 2)
    assert len(api.alle_buchungen(konto_id=k["giro"])) == 7


def _kennungen(tmp_path, name, daten, *, ziel="giro") -> set[str]:
    api = neue_api(tmp_path / name)
    k = _konten(api)
    erfolg(api, k[ziel], daten)
    return {b["extern_ids"][0].split(":", 2)[2] for b in api.alle_buchungen(konto_id=k[ziel])}


def test_kennung_stabil_und_unabhaengig_von_schreibweise_und_reihenfolge(tmp_path):
    basis = _kennungen(tmp_path, "a", qif(BEISPIEL))
    umgestellt = qif(CAT + ["!Type:Bank"] + [SAETZE[3], SAETZE[0], SAETZE[5], SAETZE[2], SAETZE[1], SAETZE[4]])
    assert _kennungen(tmp_path, "b", umgestellt) == basis, "Reihenfolge verschiedener Sätze ändert die Kennung nicht"
    iso = [[(f"D{z[7:11]}-{z[4:6]}-{z[1:3]}") if z.startswith("D") else z for z in s] for s in SAETZE]
    assert iso[0][0] == "D2024-01-02"
    assert _kennungen(tmp_path, "c", qif(CAT + ["!Type:Bank"] + iso)) == basis, "Schreibweise des Datums"
    betrag = [[("T-12,340" if z == "T-12,34" else "T2500,00" if z == "T2.500,00" else z) for z in s] for s in SAETZE]
    assert _kennungen(tmp_path, "d", qif(CAT + ["!Type:Bank"] + betrag)) == basis, "Schreibweise des Betrags"
    geaendert = [s if i != 0 else s[:-2] + ["MEinkauf Woche 2", s[-1]] for i, s in enumerate(SAETZE)]
    anders = _kennungen(tmp_path, "e", qif(CAT + ["!Type:Bank"] + geaendert))
    assert len(anders & basis) == 5, "eine geänderte Angabe ergibt eine neue Kennung"


def test_anderes_zielkonto_andere_kennung(api):
    k = _konten(api)
    a = erfolg(api, k["giro"], bank(["D02.01.2024", "T-1,00", "PCafé Beispiel"]))
    b = erfolg(api, k["spar"], bank(["D02.01.2024", "T-1,00", "PCafé Beispiel"]))
    assert a["buchungen_neu"] == 1
    assert b["buchungen_neu"] == 1 and b["buchungen_zusammengefuehrt"] == 0
    kg = api.alle_buchungen(konto_id=k["giro"])[0]["extern_ids"][0]
    ks = api.alle_buchungen(konto_id=k["spar"])[0]["extern_ids"][0]
    assert kg.startswith(f"alf:{k['giro']}:") and ks.startswith(f"alf:{k['spar']}:") and kg != ks


# ------------------------------------------------------------------ Python-API (1)


def test_python_api_gleich_rest(tmp_path):
    daten = qif(BEISPIEL)
    pfad = tmp_path / "Export Giro.qif"
    pfad.write_bytes(daten)
    rest = neue_api(tmp_path / "rest")
    kr = _konten(rest)
    er = erfolg(rest, kr["giro"], daten)
    cfg = neue_config(tmp_path / "py")
    py = Api(cfg)
    kp = _konten(py)
    a0 = letzte_aenderung_id(py)
    ep = importiere(cfg, pfad, konto_id=kp["giro"])
    assert ep.erfolgreich is True and ep.format == "qif"
    for feld in ("kategorien_neu", "empfaenger_neu", "tags_neu", "buchungen_neu", "splits_neu"):
        assert getattr(ep, feld) == er[feld], feld
    assert {(w.code, w.referenz) for w in ep.warnungen} == warnungen(er)
    (vorgang,) = _importe(py)
    assert (vorgang["art"], vorgang["dateiname"], vorgang["id"]) == ("alfbanco", "Export Giro.qif", ep.import_id)
    (a,) = aenderungen_seit(py, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("import", "import_alfbanco", f"import:{ep.import_id}")
    # Bytes: dateiname None; zweiter Lauf ohne Wirkung
    e2 = importiere(cfg, daten, konto_id=kp["giro"])
    assert e2.buchungen_vorhanden == 6 and e2.buchungen_neu == 0
    assert _importe(py)[-1]["dateiname"] is None
    e3 = importiere(cfg, bytearray(daten), konto_id=kp["giro"], dateiname="x.qif")
    assert e3.buchungen_vorhanden == 6 and _importe(py)[-1]["dateiname"] == "x.qif"


def test_python_api_fehler(tmp_path):
    cfg = neue_config(tmp_path / "py")
    api = Api(cfg)
    k = _konten(api)
    kat = api.konto("Haushalt", "aufwand")["id"]
    ek = api.konto("Eigenkapital", "eigenkapital")["id"]
    z = bestand(api)
    with pytest.raises(TypeError):
        importiere(cfg, 42, konto_id=k["giro"])
    with pytest.raises(FileNotFoundError):
        importiere(cfg, tmp_path / "fehlt.qif", konto_id=k["giro"])
    for falsch in (999999, kat, ek):
        with pytest.raises(ValueError):
            importiere(cfg, b"", konto_id=falsch)
    with pytest.raises(TypeError):
        importiere(cfg, qif(BEISPIEL), k["giro"])  # konto_id nur als Schlüsselwort
    e = importiere(cfg, b"", konto_id=k["giro"])
    assert e.erfolgreich is False and [m.code for m in e.fehler] == ["import_datei_leer"]
    assert bestand(api) == z and _importe(api) == []
    # geschlossenes Bestandskonto ist erlaubt
    zu = _geschlossen(api, "Altes Konto", "girokonto")
    assert importiere(cfg, bank(["D02.01.2024", "T-1,00"]), konto_id=zu).buchungen_neu == 1


def test_mock_zeitpunkt(tmp_path):
    cfg = mock_config(tmp_path, heute="2024-03-15")
    api = Api(cfg)
    g = _konten(api)["giro"]
    importiere(cfg, bank(["D02.01.2024", "T-1,00"]), konto_id=g)
    assert _importe(api)[-1]["importiert_am"] == "2024-03-15T12:00:00Z"
    jetzt = api.get("/api/mock/zeit", erwartet=200).daten["jetzt"]
    erfolg(api, g, bank(["D03.01.2024", "T-2,00"]))
    assert _importe(api)[-1]["importiert_am"] == jetzt, "REST: App-Uhr"


# ------------------------------------------------------------------ REST: Prüfreihenfolge (2)

GUT = bank(["D02.01.2024", "T-1,00"])


@pytest.mark.parametrize("fall,felder,status,code,ort", [
    ("konto_id_fehlt", [("datei", "a.qif", GUT, None)], 422, "validierung", "konto_id"),
    ("konto_id_null", [("konto_id", None, b"0", None), ("datei", "a.qif", GUT, None)], 422, "validierung", "konto_id"),
    ("konto_id_negativ", [("konto_id", None, b"-1", None), ("datei", "a.qif", GUT, None)], 422, "validierung",
     "konto_id"),
    ("konto_id_text", [("konto_id", None, b"abc", None), ("datei", "a.qif", GUT, None)], 422, "validierung",
     "konto_id"),
    ("konto_id_dezimal", [("konto_id", None, b"1.5", None), ("datei", "a.qif", GUT, None)], 422, "validierung",
     "konto_id"),
    ("konto_id_leer", [("konto_id", None, b"", None), ("datei", "a.qif", GUT, None)], 422, "validierung", "konto_id"),
    ("konto_id_fuehrende_null", [("konto_id", None, b"01", None), ("datei", "a.qif", GUT, None)], 422, "validierung",
     "konto_id"),
    ("konto_id_19_ziffern", [("konto_id", None, b"1" * 19, None), ("datei", "a.qif", GUT, None)], 422, "validierung",
     "konto_id"),
    ("konto_id_vorzeichen", [("konto_id", None, b"+1", None), ("datei", "a.qif", GUT, None)], 422, "validierung",
     "konto_id"),
    ("konto_vor_datei", [("anders", None, b"x", None)], 422, "validierung", "konto_id"),
    ("datei_fehlt", [("konto_id", None, b"G", None)], 422, "validierung", "datei"),
    ("datei_kein_dateifeld", [("konto_id", None, b"G", None), ("datei", None, GUT, None)], 422, "validierung",
     "datei"),
    ("konto_unbekannt_leere_datei", [("konto_id", None, b"999999", None), ("datei", "a.qif", b"", None)], 422,
     "referenz_unbekannt", None),
    ("konto_kategorie", [("konto_id", None, b"K", None), ("datei", "a.qif", b"", None)], 422, "konto_ungueltig", None),
    ("konto_eigenkapital", [("konto_id", None, b"E", None), ("datei", "a.qif", GUT, None)], 422, "konto_ungueltig",
     None),
])
def test_rest_pruefreihenfolge(api, fall, felder, status, code, ort):
    g = _konten(api)["giro"]
    ersatz = {b"G": str(g).encode(), b"K": str(api.konto("Haushalt", "aufwand")["id"]).encode(),
              b"E": str(api.konto("Eigenkapital", "eigenkapital")["id"]).encode()}
    felder = [(n, f, ersatz.get(d, d), t) for n, f, d, t in felder]

    def aufruf():
        r = import_rest(api, None, b"", felder=felder, erwartet=status)
        assert fehlercode(r) == code, r.text[:300]
        if ort:
            assert any(o[:2] == ["body", ort] for o in orte(r)), orte(r)
        if code in ("referenz_unbekannt", "konto_ungueltig"):
            assert r.json()["fehler"]["details"] == {"feld": "konto_id"}
    ohne_wirkung(api, aufruf)
    assert _importe(api) == []


def test_rest_kein_formular_und_leerraum(api):
    g = _konten(api)["giro"]
    def json_koerper():
        assert fehlercode(api.post("/api/import/alfbanco", json={"konto_id": g}, erwartet=422)) == "validierung"
    ohne_wirkung(api, json_koerper)
    e = import_rest(api, f"  {g} ", GUT).daten
    assert e["buchungen_neu"] == 1, "umgebender Leerraum in konto_id ist erlaubt"


def test_rest_groessengrenze(tmp_path):
    api = neue_api(tmp_path, upload_max_mib=1, anfrage_max_kib=64)
    g = _konten(api)["giro"]
    gross = GUT + b"\r\n" * (600 * 1024)
    def zu_gross():
        assert fehlercode(import_rest(api, g, gross, erwartet=413)) == "datei_zu_gross"
    ohne_wirkung(api, zu_gross)
    assert erfolg(api, g, GUT + b"\r\n" * (100 * 1024))["buchungen_neu"] == 1, "Upload-Pfad: über anfrage_max_kib"


def test_rest_geschuetzt(tmp_path):
    from tests.hilfen.m7 import anmelden, m7_api

    api = m7_api(tmp_path)
    assert fehlercode(import_rest(api, 1, GUT, erwartet=401)) == "nicht_angemeldet"
    assert fehlercode(api.post("/api/kategorien/zusammenfuehren", json={"quelle_ids": [1], "ziel_id": 2},
                               erwartet=401)) == "nicht_angemeldet"
    anmelden(api)
    g = _konten(api)["giro"]
    csrf, api.csrf = api.csrf, None
    assert fehlercode(import_rest(api, g, GUT, erwartet=403)) == "csrf_ungueltig"
    api.csrf = csrf
    assert erfolg(api, g, GUT)["buchungen_neu"] == 1


# ------------------------------------------------------------------ Datei- und Formatfehler (3.1, 3.3)


@pytest.mark.parametrize("fall,daten,code,fmt", [
    ("leer", b"", "import_datei_leer", None),
    ("xml", b'<?xml version="1.0"?><KMYMONEY-FILE/>', "import_format_ungueltig", None),
    ("csv", "Datum;Betrag\r\n02.01.2024;-12,34\r\n".encode(), "import_format_ungueltig", None),
    ("leerzeilen_dann_text", b"\r\n\r\n  D02.01.2024\r\n", "import_format_ungueltig", None),
    ("nur_option", b"!Option:AutoSwitch\r\n", "import_format_ungueltig", "qif"),
    ("nur_clear", b"!Clear:AutoSwitch\r\n!Option:AutoSwitch\r\n", "import_format_ungueltig", "qif"),
    ("zwei_konten", qif(["!Account", ["NGiro A", "TBank"], "!Type:Bank", ["D02.01.2024", "T-1,00"], "!Account",
                         ["NGiro B", "TBank"], "!Type:Bank", ["D03.01.2024", "T-2,00"]]),
     "import_format_ungueltig", "qif"),
    ("namenlos_und_konto", qif(["!Type:Bank", ["D02.01.2024", "T-1,00"], "!Account", ["NGiro A", "TBank"],
                                "!Type:Bank", ["D03.01.2024", "T-2,00"]]), "import_format_ungueltig", "qif"),
])
def test_formatfehler(api, fall, daten, code, fmt):
    g = _konten(api)["giro"]

    def aufruf():
        r = import_rest(api, g, daten, erwartet=422)
        assert fehlercode(r) == code
        e = r.json()["fehler"]["details"]
        leer_ergebnis(e, fmt)
        assert [(m["code"], m["referenz"]) for m in e["fehler"]] == [(code, None)]
    ohne_wirkung(api, aufruf)
    assert _importe(api) == []


@pytest.mark.parametrize("fall,daten,neu", [
    ("bank_ohne_saetze", b"!Type:Bank\r\n", 0),
    ("nur_kategorieliste", qif(CAT), 0),
    ("ein_konto", qif(["!Account", ["NGiro A", "TBank"], "!Type:Bank", ["D02.01.2024", "T-1,00"],
                       ["D03.01.2024", "T-2,00"]]), 2),
    ("unbekannter_kopf", qif(["!Type:Memorized", ["KC", "T-1,00", "PDauerauftrag"], "!Type:Bank",
                              ["D02.01.2024", "T-1,00"]]), 1),
    ("satz_ohne_abschluss", b"!Type:Bank\r\nD02.01.2024\r\nT-1,00\r\n", 1),
    ("satz_vor_kopf_ohne_abschluss", b"!Type:Bank\r\nD02.01.2024\r\nT-1,00\r\n!Type:Bank\r\nD03.01.2024\r\nT-2,00\r\n^",
     2),
])
def test_gueltige_sonderformen(api, fall, daten, neu):
    g = _konten(api)["giro"]
    e = erfolg(api, g, daten)
    assert e["buchungen_neu"] == neu and e["format"] == "qif"


def test_inhaltsfehler_alle_gesammelt(api):
    g = _konten(api)["giro"]
    daten = qif(["!Type:Bank",
                 ["D02.01.2024", "T-1,00"],                                   # Satz 1 gültig
                 ["D33.01.2024", "T-2,00"],                                   # Satz 2 Datum ungültig
                 ["PNur Empfänger", "Tabc"],                                  # Satz 3 Datum fehlt, Betrag ungültig
                 "!Type:Invst", ["Dkein Datum", "Tkein Betrag"],              # Satz 4 Invst: nicht geprüft
                 "!Type:Bank",
                 ["D05.01.2024", "T-5,00", "SA", "$-2,00", "SB", "EOhne Betrag", "SC", "$x"],  # Satz 5 zwei Teile
                 ["D06.01.2024"]])                                            # Satz 6 Betrag fehlt

    def aufruf():
        r = import_rest(api, g, daten, erwartet=422)
        assert fehlercode(r) == "import_inhalt_ungueltig"
        e = r.json()["fehler"]["details"]
        leer_ergebnis(e, "qif")
        assert [(m["code"], m["referenz"]) for m in e["fehler"]] == [
            ("import_inhalt_ungueltig", "Satz 2"), ("import_inhalt_ungueltig", "Satz 3"),
            ("import_inhalt_ungueltig", "Satz 3"), ("import_inhalt_ungueltig", "Satz 5"),
            ("import_inhalt_ungueltig", "Satz 5"), ("import_inhalt_ungueltig", "Satz 6")]
    ohne_wirkung(api, aufruf)
    assert _importe(api) == []


# ------------------------------------------------------------------ Datum (3.4) und Betrag (3.5)


def _daten_import(api, werte: list[str], extra: list[list[str]] = ()) -> list[str]:
    g = _konten(api)["giro"]
    saetze = [[f"D{w}", "T-1,00", f"MS{i}"] for i, w in enumerate(werte)] + list(extra)
    erfolg(api, g, qif(["!Type:Bank", *saetze]))
    z = {b["verwendungszweck"]: b["datum"] for b in api.alle_buchungen(konto_id=g)}
    return [z[f"S{i}"] for i in range(len(werte))]


def test_datum_monat_zuerst(api):
    werte = ["02.01.2024", "2.1.24", "2024-1-2", "2024-01-02", "1/2/2024", "1/2'24", " 1/ 2'98", "1/2/98",
             "1/2'2024", "02.01.70", "02.01.69", "12/31/2024"]
    assert _daten_import(api, werte) == ["2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02",
                                         "2024-01-02", "2098-01-02", "1998-01-02", "2024-01-02", "1970-01-02",
                                         "2069-01-02", "2024-12-31"]


def test_datum_tag_zuerst_fuer_die_ganze_datei(api):
    assert _daten_import(api, ["1/2/2024", "13/02/2024", "02.01.2024"]) == ["2024-02-01", "2024-02-13",
                                                                           "2024-01-02"]


@pytest.mark.parametrize("wert", ["2024/01/02", "31.02.2024", "1.13.2024", "32.1.2024", "1/32/2024", "2024-13-01",
                                  "heute", "02.01", "02-01-2024"])
def test_datum_ungueltig(api, wert):
    g = _konten(api)["giro"]
    r = import_rest(api, g, bank(["D02.01.2024", "T-1,00"], [f"D{wert}", "T-1,00"]), erwartet=422)
    assert [(m["code"], m["referenz"]) for m in r.json()["fehler"]["details"]["fehler"]] == [
        ("import_inhalt_ungueltig", "Satz 2")]


KOMMA = [("-12,34", -1234), ("2.500,00", 250000), ("+7", 700), ("0,10", 10), ("1.000", 100000), ("-0,00", 0),
         ("12,500", 1250), ("1 234,50", 123450), ("1 234,50", 123450), (",5", 50), ("9.999.999.999,99",
                                                                                        999999999999)]
PUNKT = [("1,234.56", 123456), ("12.5", 1250), ("3,450", 345000), ("-0.10", -10)]


def _betraege(api, liste, *, trenner_satz: str) -> list[int]:
    g = _konten(api)["giro"]
    saetze = [["D02.01.2024", f"T{w}", f"MB{i}"] for i, (w, _) in enumerate(liste)]
    saetze.append(["D02.01.2024", f"T{trenner_satz}", "MTrenner"])
    erfolg(api, g, qif(["!Type:Bank", *saetze], kodierung="utf-8"))
    z = {b["verwendungszweck"]: next(s["betrag"] for s in b["splits"] if s["konto_id"] == g)
         for b in api.alle_buchungen(konto_id=g)}
    return [z[f"B{i}"] for i in range(len(liste))]


def test_betrag_kommadatei(api):
    assert _betraege(api, KOMMA, trenner_satz="-1,00") == [c for _, c in KOMMA]


def test_betrag_punktdatei(api):
    assert _betraege(api, PUNKT, trenner_satz="-1.00") == [c for _, c in PUNKT]


@pytest.mark.parametrize("wert", ["1,234", "12,345", "abc", "1e3", "--1", "10000000000,00", "5,", "1,2,3",
                                  "1.000,00,00", "€5", "1-2"])
def test_betrag_ungueltig(api, wert):
    g = _konten(api)["giro"]
    r = import_rest(api, g, qif(["!Type:Bank", ["D02.01.2024", "T-1,00"], ["D02.01.2024", f"T{wert}"]],
                                kodierung="utf-8"), erwartet=422)
    assert [(m["code"], m["referenz"]) for m in r.json()["fehler"]["details"]["fehler"]] == [
        ("import_inhalt_ungueltig", "Satz 2")], wert


def test_betrag_u_wenn_t_fehlt_und_erstes_vorkommen(api):
    g = _konten(api)["giro"]
    erfolg(api, g, bank(["D02.01.2024", "U-4,00", "PErster", "PZweiter", "MZweck"],
                        ["D03.01.2024", "T-1,00", "U-9,00", "T-7,00", "MZweite"]))
    z = {b["verwendungszweck"]: b for b in api.alle_buchungen(konto_id=g)}
    assert z["Zweck"]["splits"][0]["betrag"] == -400 and z["Zweck"]["empfaenger"]["name"] == "Erster"
    assert z["Zweite"]["splits"][0]["betrag"] == -100, "erstes Vorkommen von T gilt"


# ------------------------------------------------------------------ Abbildung (4)


def test_umbuchungen_anfangssalden_und_unbekannte(api):
    k = _konten(api)
    g, s = k["giro"], k["spar"]
    giro2 = api.konto("Giro/Haushalt", "girokonto")["id"]
    zu = _geschlossen(api, "Altkonto", "sparkonto")
    doppelt1 = api.konto("Doppelt", "sparkonto")["id"]   # ab M32 kein zweites gleichnamiges Bestandskonto (E-307)
    e = erfolg(api, g, bank(
        ["D01.01.2024", "T1.000,00", "MAnfang", "L[Girokonto]"],
        ["D02.01.2024", "T-5,00", "MUnbekannt", "L[Unbekannt]"],
        ["D03.01.2024", "T-6,00", "MSchraeg", "L[Giro/Haushalt]/Urlaub"],
        ["D04.01.2024", "T-7,00", "MGeschlossen", "L[Altkonto]"],
        ["D05.01.2024", "T-8,00", "MDoppelt", "L[Doppelt]"],
        ["D06.01.2024", "T-9,00", "MSpar", "L[Sparkonto]"],
    ))
    assert e["konten_neu"] == 0 and e["kategorien_neu"] == 0 and e["tags_neu"] == 1
    assert warnungen(e) == {("umbuchung_konto_unbekannt", "Satz 2")}
    anf = kategorie(api, "alf:anfangssalden")
    assert (anf["name"], anf["art"], anf["eltern_id"]) == ("Anfangssalden", "eigenkapital", None)
    z = {b["verwendungszweck"]: b for b in api.alle_buchungen()}
    unk = kategorie(api, UNKATEGORISIERT)["id"]
    assert splits(z["Anfang"]) == [(g, 100000, ""), (anf["id"], -100000, "")]
    assert splits(z["Unbekannt"]) == [(g, -500, ""), (unk, 500, "")]
    assert splits(z["Schraeg"]) == [(g, -600, ""), (giro2, 600, "")] and [t["name"] for t in z["Schraeg"]["tags"]] == [
        "Urlaub"]
    assert splits(z["Geschlossen"])[1][0] == zu
    assert splits(z["Doppelt"])[1][0] == doppelt1
    assert splits(z["Spar"])[1] == (s, 900, "")
    # Anfangssalden wird wiederverwendet
    erfolg(api, g, bank(["D07.01.2024", "T5,00", "MAnfang 2", "L[Girokonto]"]))
    assert [k_["id"] for k_ in api.konten() if k_["extern_id"] == "alf:anfangssalden"] == [anf["id"]]


def test_aufteilung_mit_rest_invst_leere_kategorie_und_pfade(api):
    g = _konten(api)["giro"]
    e = erfolg(api, g, qif([
        "!Type:Bank",
        ["D02.01.2024", "T-10,00", "MRest", "E-vor-S", "$-1,00", "SHaushalt", "$-6,00"],        # Satz 1
        "!Type:Invst", ["D03.01.2024", "NBuy", "T-100,00"],                                     # Satz 2
        "!Type:Bank",
        ["D04.01.2024", "T-2,00", "MLeer"],                                                    # Satz 3
        ["D05.01.2024", "T-3,00", "MNur Klasse", "L/Urlaub"],                                  # Satz 4
        ["D06.01.2024", "T-4,00", "MPfad", "L Haushalt : : Garten /urlaub"],                   # Satz 5
        ["D07.01.2024", "T-5,00", "MLeeres L", "L"],                                           # Satz 6
    ]))
    assert e["buchungen_neu"] == 5 and e["buchungen_uebersprungen"] == 1
    assert e["buchungen_neu"] + e["buchungen_vorhanden"] + e["buchungen_zusammengefuehrt"] + e[
        "buchungen_uebersprungen"] == 6
    assert warnungen(e) == {("split_differenz", "Satz 1"), ("buchung_uebersprungen", "Satz 2"),
                            ("kategorieart_abgeleitet", "Haushalt")}
    assert (e["kategorien_neu"], e["tags_neu"], e["splits_neu"]) == (2, 1, 3 + 2 + 2 + 2 + 2)
    unk = kategorie(api, UNKATEGORISIERT)["id"]
    haus, garten = kategorie(api, "alf:kat:Haushalt"), kategorie(api, "alf:kat:Haushalt:Garten")
    assert garten["eltern_id"] == haus["id"] and garten["name"] == "Garten"
    z = {b["verwendungszweck"]: b for b in api.alle_buchungen()}
    assert splits(z["Rest"]) == [(g, -1000, ""), (haus["id"], 600, ""), (unk, 400, "")]
    assert splits(z["Leer"])[1][0] == unk and splits(z["Nur Klasse"])[1][0] == unk and splits(z["Leeres L"])[1][0] == unk
    assert [t["name"] for t in z["Nur Klasse"]["tags"]] == ["Urlaub"]
    assert [t["name"] for t in z["Pfad"]["tags"]] == ["Urlaub"], "Tags unter casefold zusammengefasst"
    assert len(api.get("/api/tags", erwartet=200).daten) == 1


def test_kategorieart(api):
    g = _konten(api)["giro"]
    e = erfolg(api, g, qif([
        "!Type:Cat", ["NZinsen"], ["NZinsen:Tagesgeld", "I"], ["NZinsen:Depot", "E"], ["NBeides", "E", "I"],
        "!Type:Bank",
        ["D02.01.2024", "T-1,00", "LZinsen:Depot"],          # Wurzel Zinsen: erstes gekennzeichnetes Kind → I
        ["D03.01.2024", "T5,00", "LBonus"],                  # abgeleitet: Gegenbetrag −500 < 0 → ertrag
        ["D04.01.2024", "T-5,00", "LMuell"], ["D04.01.2024", "T5,00", "LMuell"],   # Summe 0 → aufwand
        ["D05.01.2024", "T-1,00", "LBeides"],                # I gewinnt, wenn beide
        ["D06.01.2024", "T-1,00", "LAuto:Benzin"], ["D06.01.2024", "T3,00", "LAuto:Erstattung"],  # −2 < 0 → ertrag
    ]))
    art = {k["extern_id"]: k["art"] for k in api.konten() if (k["extern_id"] or "").startswith("alf:kat:")}
    assert art == {"alf:kat:Zinsen": "ertrag", "alf:kat:Zinsen:Depot": "ertrag", "alf:kat:Bonus": "ertrag",
                   "alf:kat:Muell": "aufwand", "alf:kat:Beides": "ertrag", "alf:kat:Auto": "ertrag",
                   "alf:kat:Auto:Benzin": "ertrag", "alf:kat:Auto:Erstattung": "ertrag"}
    assert warnungen(e) == {("kategorieart_abgeleitet", "Bonus"), ("kategorieart_abgeleitet", "Muell"),
                            ("kategorieart_abgeleitet", "Auto")}
    assert "alf:kat:Zinsen:Tagesgeld" not in art, "Einträge nur aus !Type:Cat legen nichts an"


def test_zuordnung_vorhandener_kategorien(api):
    g = _konten(api)["giro"]
    from tests.hilfen.kmybau import KBuch, KKonto, gzip_bytes

    s = api.konto("Nebenkonto", "sparkonto")["id"]
    haus = api.konto("Haushalt", "aufwand")                                  # ohne Kennung → wird zugeordnet
    kb = KBuch()                                                             # fremde Kennung (KMyMoney) bleibt
    kb.konten = [KKonto("A000098", "Nebenkasse", 1, "AStd::Asset"), KKonto("A000099", "Freizeit", 13, "AStd::Expense")]
    api.post("/api/import/kmymoney", files={"datei": ("f.kmy", gzip_bytes(kb), "x")}, erwartet=200)
    fremd = next(k for k in api.konten() if k["name"] == "Freizeit")
    assert fremd["extern_id"].startswith("kmy:") and fremd["art"] == "aufwand"
    falsche_art = api.konto("Gehalt", "aufwand")                             # Art passt nicht (Gehalt ist I)
    # Kategorien mit alf:-Kennung aus einem früheren Lauf in ein anderes Konto, danach umbenannt
    erfolg(api, s, qif(["!Type:Cat", ["NKleidung", "I"], "!Type:Bank", ["D01.01.2023", "T1,00", "LKleidung"],
                        ["D01.01.2023", "T-1,00", "LAndere"]]))
    per_kennung = kategorie(api, "alf:kat:Kleidung")                         # Regel 1 trotz Art und Name
    api.patch(f"/api/konten/{per_kennung['id']}", json={"name": "Ganz anders"}, erwartet=200)
    alf_fremd = kategorie(api, "alf:kat:Andere")                             # alf:-Kennung, nicht über Namen
    api.patch(f"/api/konten/{alf_fremd['id']}", json={"name": "Sport"}, erwartet=200)
    unter = api.konto("Lebensmittel", "aufwand", eltern_id=fremd["id"])      # anderes Elternkonto → nicht
    z0 = api.konten()
    a0 = letzte_aenderung_id(api)
    e = erfolg(api, g, qif(BEISPIEL + [["D07.01.2024", "T-1,00", "LFreizeit"], ["D08.01.2024", "T-1,00", "LSport"]]))
    assert (e["kategorien_vorhanden"], e["kategorien_neu"]) == (3, 3), (
        "vorhanden: Haushalt, Kleidung (Kennung), Freizeit; neu: Haushalt:Lebensmittel, Gehalt, Sport")
    # M32 (sammel3.md 1.3, E-307): die neue „Sport“ ist Geschwister der umbenannten „Sport“ (alf:kat:Andere) und wird in
    # diese (kleinere ID) zusammengeführt; sie behält keine eigene Kennung
    assert any(w["code"] == "konto_zusammengefasst" and "Sport" in (w["referenz"] or "") for w in e["warnungen"])
    konten = {k["id"]: k for k in api.konten()}
    assert konten[haus["id"]]["extern_id"] == "alf:kat:Haushalt"
    assert konten[fremd["id"]]["extern_id"] == "kmy:A000099"
    assert kategorie(api, "alf:kat:Haushalt:Lebensmittel")["eltern_id"] == haus["id"]
    assert kategorie(api, "alf:kat:Haushalt:Lebensmittel")["id"] != unter["id"]
    gehalt = kategorie(api, "alf:kat:Gehalt")
    assert gehalt["id"] != falsche_art["id"] and gehalt["art"] == "ertrag"
    assert konten[per_kennung["id"]]["art"] == "ertrag" and konten[per_kennung["id"]]["name"] == "Ganz anders"
    assert kategorie(api, "alf:kat:Sport") is None
    sport = next(b for b in api.alle_buchungen() if b["datum"] == "2024-01-08" and b["verwendungszweck"] == "")
    assert alf_fremd["id"] in [s["konto_id"] for s in sport["splits"]]
    kleid = next(b for b in api.alle_buchungen() if b["verwendungszweck"] == "Gemischter Einkauf")
    assert per_kennung["id"] in [s["konto_id"] for s in kleid["splits"]]
    assert ("kategorieart_abgeleitet", "Kleidung") not in warnungen(e), "nicht neu angelegt → keine Warnung"
    # zweiter Import: Freizeit wird wieder über den Namen gefunden; „Sport“ wird erneut angelegt und zusammengeführt
    z1 = api.konten()
    e2 = erfolg(api, g, qif(BEISPIEL + [["D07.01.2024", "T-1,00", "LFreizeit"], ["D08.01.2024", "T-1,00", "LSport"]]))
    assert (e2["kategorien_neu"], e2["kategorien_vorhanden"]) == (1, 5)
    assert api.konten() == z1
    # Rückgängig des ersten Imports: GET /api/konten wie vorher (auch die gesetzte extern_id)
    (a,) = [x for x in aenderungen_seit(api, a0) if x["aktion"] == "import_alfbanco"]
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": a["gruppe"]}, erwartet=200)
    assert api.konten() == z0


def test_empfaenger_zuordnung_mit_alias(api):
    g = _konten(api)["giro"]
    vorhanden = api.post("/api/empfaenger", json={"name": "Supermarkt Muster", "aliase": ["SUPERMARKT BEISPIEL"]},
                         erwartet=201).daten
    exakt = api.empfaenger("Café Beispiel")
    e = erfolg(api, g, qif(BEISPIEL))
    assert (e["empfaenger_neu"], e["empfaenger_vorhanden"]) == (3, 2)
    z = {b["verwendungszweck"]: b for b in api.alle_buchungen(konto_id=g)}
    assert z["Einkauf Woche 1"]["empfaenger"]["id"] == vorhanden["id"]
    assert exakt["id"] in {b["empfaenger"]["id"] for b in api.alle_buchungen(konto_id=g)}
    assert not any(w["code"] == "empfaenger_zusammengefasst" for w in e["warnungen"])


# ------------------------------------------------------------------ Dubletten (4.5)


def test_dubletten(api):
    k = _konten(api)
    g = k["giro"]
    leb = api.konto("Lebensmittel", "aufwand")["id"]
    markt = api.empfaenger("Supermarkt Beispiel")["id"]
    exakt = api.buchung("2024-01-02", [(g, -1234), (leb, 1234)], empfaenger_id=markt)["id"]
    aehnlich = api.buchung("2024-01-07", [(g, -5000), (leb, 5000)])["id"]          # Kaufhaus, 2 Tage Abstand
    cafe = api.empfaenger("CAFÉ  Beispiel")["id"]                                 # passend über ekey
    m1 = api.buchung("2024-01-06", [(g, -300), (leb, 300)], empfaenger_id=cafe)["id"]   # exakt für beide Kaffees
    m2 = api.buchung("2024-01-06", [(g, -300), (leb, 300)], empfaenger_id=cafe)["id"]
    weit = api.buchung("2024-01-07", [(g, 250000), (leb, -250000)])["id"]          # 4 Tage Abstand → kein Kandidat
    e = erfolg(api, g, qif(BEISPIEL))
    assert (e["buchungen_neu"], e["buchungen_zusammengefuehrt"], e["buchungen_zur_pruefung"]) == (5, 1, 3)
    b = api.buchung_lesen(exakt)
    assert len(b["extern_ids"]) == 1 and KENNUNG.match(b["extern_ids"][0])
    assert splits(b) == [(g, -1234, ""), (leb, 1234, "")], "zusammengeführt: sonst unverändert"
    verdachte = api.get("/api/dubletten", erwartet=200).daten
    assert sorted((v["grund"], tuple(v["kandidat_ids"])) for v in verdachte) == sorted([
        ("aehnlich", (aehnlich,)), ("mehrdeutig", (m1, m2)), ("mehrdeutig", (m1, m2))])
    assert all(v["status"] == "offen" for v in verdachte)
    assert api.buchung_lesen(weit)["extern_ids"] == []
    # ohne Empfänger am Kandidaten: nicht passend → ähnlich (0 Tage)
    g2 = api.konto("Zweitkonto")["id"]
    o1 = api.buchung("2024-01-06", [(g2, -300), (leb, 300)])["id"]
    erfolg(api, g2, bank(["D06.01.2024", "T-3,00", "PCafé Beispiel"]))
    assert ("aehnlich", (o1,)) in {(v["grund"], tuple(v["kandidat_ids"])) for v in
                                   api.get("/api/dubletten", erwartet=200).daten}


def test_geaenderter_satz_wird_mit_alter_buchung_zusammengefuehrt(api):
    g = _konten(api)["giro"]
    erfolg(api, g, bank(["D02.01.2024", "T-12,34", "PSupermarkt Beispiel", "MEinkauf"]))
    (alt,) = api.alle_buchungen(konto_id=g)
    e = erfolg(api, g, bank(["D02.01.2024", "T-12,34", "PSupermarkt Beispiel", "MEinkauf korrigiert"]))
    assert (e["buchungen_neu"], e["buchungen_zusammengefuehrt"]) == (0, 1)
    neu = api.buchung_lesen(alt["id"])
    assert len(neu["extern_ids"]) == 2 and alt["extern_ids"][0] in neu["extern_ids"]
    assert neu["extern_ids"] == sorted(neu["extern_ids"]), "extern_ids aufsteigend (datenmodell.md 3)"
    assert neu["verwendungszweck"] == "Einkauf", "zusammengeführt: nur die Kennung kommt hinzu"


# ------------------------------------------------------------------ Protokoll (6)


def test_rueckgaengig_ueber_gruppe_und_aenderung(api):
    k = _konten(api)
    g = k["giro"]
    leb = api.konto("Haushalt", "aufwand")["id"]
    markt = api.empfaenger("Supermarkt Beispiel")["id"]
    api.buchung("2024-01-02", [(g, -1234), (leb, 1234)], empfaenger_id=markt)
    v, konten_vorher, a0 = bestand(api), api.konten(), letzte_aenderung_id(api)
    e = erfolg(api, g, qif(BEISPIEL))
    n = bestand(api)
    (a,) = aenderungen_seit(api, a0)
    pruefe_eintraege(a, v, n)
    assert e["buchungen_zusammengefuehrt"] == 1, "Testvoraussetzung: eine angehängte Kennung"
    u = api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"import:{e['import_id']}"}, erwartet=200).daten
    assert bestand(api) == v and api.konten() == konten_vorher
    pruefe_eintraege(u, n, v)
    w = api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == n
    pruefe_eintraege(w, v, n)


def test_import_ohne_wirkung_ohne_aenderung(api):
    g = _konten(api)["giro"]
    ohne_wirkung(api, lambda: erfolg(api, g, b"!Type:Bank\r\n"))
    assert len(_importe(api)) == 1, "auch ohne neue Buchungen entsteht ein Importvorgang"


def test_zeitpunkt_echtmodus(api):
    g = _konten(api)["giro"]
    vor = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    erfolg(api, g, GUT)
    t = dt.datetime.strptime(_importe(api)[0]["importiert_am"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    assert vor <= t <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)
    assert kontor.modul("kontor.importer.alfbanco")
