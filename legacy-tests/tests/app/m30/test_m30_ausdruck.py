"""M30: Ausdruckssprache prüfen und abfragen (ausdruecke.md 2–4; E-268, E-272) – REST, kern.

``GET /api/ausdruck/sprache``, ``POST /api/ausdruck/pruefen`` (kanonische Schreibweise, Fehlercodes mit Stelle,
Datumsangaben mit festem ``stichtag``), ``POST /api/ausdruck/als-regel``. Der Bezugstag ist immer 2026-11-16.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import m30
from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m30 import STICHTAG, gueltig, ungueltig

pytestmark = pytest.mark.kern


@pytest.fixture
def b(api):
    return m30.bestand(api)


# ------------------------------------------------------------------ 4.1 Sprache
@pytest.mark.parametrize("kontext", ["regel", "filter"])
def test_sprache_felder(api, kontext):
    d = api.get("/api/ausdruck/sprache", params={"kontext": kontext}, erwartet=200).daten
    assert d["kontext"] == kontext
    felder = {f["name"]: f for f in d["felder"]}
    soll = {n for n, (_, in_regeln) in m30.FELDER.items() if in_regeln or kontext == "filter"}
    assert set(felder) == soll, f"Felder im Kontext {kontext}"
    for name, f in felder.items():
        assert f["kurz"] == m30.FELDER[name][0], f"Kurzform von {name}"
        assert f["nur_filter"] is (not m30.FELDER[name][1]), f"nur_filter von {name}"
        assert f["bezeichnung"].strip() and f["typ"].strip()
    for teil in ("schluesselwoerter", "aliase", "methoden", "kwargs"):
        assert d[teil] is not None, teil


def test_sprache_kontext_ungueltig(api):
    r = api.get("/api/ausdruck/sprache", params={"kontext": "suche"}, erwartet=422)
    assert fehlercode(r) == "validierung"


# ------------------------------------------------------------------ 4.2 Prüfen: Grundform
def test_pruefen_gueltig_form(api):
    p = gueltig(api, 'empfänger == "REWE"', "regel")
    assert p["datumsangaben"] == [] and p["freitext"] == []
    assert isinstance(p["baukasten_faehig"], bool)
    assert p["zusammenfassung"], "Zusammenfassung der Teile auf oberster Ebene"


def test_pruefen_ist_lesezugriff(b):
    a0 = letzte_aenderung_id(b.api)
    gueltig(b.api, '"Urlaub" in tags and kategorie == "Lebensmittel:Supermarkt"', "regel")
    ungueltig(b.api, "betrag >", "syntax")
    assert letzte_aenderung_id(b.api) == a0


@pytest.mark.parametrize("body", [{}, {"kontext": "filter"}, {"ausdruck": "betrag > 1", "kontext": "suche"},
                                  {"ausdruck": "betrag > 1", "zusatz": 1}, {"ausdruck": 5},
                                  {"ausdruck": "betrag > 1", "stichtag": "16.11.2026"},
                                  {"ausdruck": "betrag > 1", "festschreiben": "ja"}],
                         ids=["leer", "ohne_ausdruck", "kontext", "zusatzfeld", "zahl", "stichtag", "festschreiben"])
def test_pruefen_validierung(api, body):
    assert fehlercode(api.post("/api/ausdruck/pruefen", json=body, erwartet=422)) == "validierung"


# ------------------------------------------------------------------ 2.1/2.3 gültige Schreibweisen
REGEL_GUELTIG = [
    '"REWE" in empfänger', '"REWE" not in empfänger', 'empfänger == "REWE"', 'empfänger != "REWE"',
    'empfänger.startswith("REWE")', 'empfänger.endswith("GmbH")', 'empfänger.search(r"RE+WE")',
    'empfänger.startswith("REWE", case=True)', 'empfänger.endswith("mbh", fold=False)',
    'empfänger in ["REWE", "EDEKA"]', "betrag > 10", "betrag < 10", "betrag <= 10", "betrag >= 10", "betrag == 10",
    "betrag != 10", "30 <= betrag <= 40", "betrag == 12.5", "betrag == 12.50", "betrag >= 1_000",
    "kategorie is None", "kategorie is not None", "kategorie is null", 'wochentag in ["sa", "so"]',
    'wochentag == "werktag"', 'wochentag == "wochenende"', 'richtung == "ausgabe"', 'dir == "einnahme"',
    'status == "bestaetigt"', "monatstag == 31", "monat == 12", "monat == dez", "quartal == 4", "letzter_tag",
    "not letzter_tag", "letzter_tag == True", "letzter_tag == true", 'empf == "a" && bet > 1',
    'empf == "a" || bet > 1', '!(empf == "a")', 'not (empf == "a" or vwz == "b") and bet > 1',
    'empfaenger == "REWE"', '"x" in notiz', 'iban == ""', "empfänger == 'REWE'",
]


@pytest.mark.parametrize("ausdruck", REGEL_GUELTIG)
def test_gueltig_in_regel_und_filter(api, ausdruck):
    """Jeder im Kontext ``regel`` gültige Ausdruck ist auch als Filter gültig (2.1)."""
    for kontext in ("regel", "filter"):
        gueltig(api, ausdruck, kontext)


def test_verweise_gueltig(b):
    for ausdruck in ('kategorie == "Lebensmittel:Supermarkt"', 'kategorie == "Wohnen"', 'konto == "Giro"',
                     '"Urlaub" in tags', '"Urlaub" not in tags',
                     'kategorie in ["Wohnen", "Lebensmittel:Supermarkt"]'):
        gueltig(b.api, ausdruck, "regel")


# ------------------------------------------------------------------ 2.6 kanonische Schreibweise
KANONISCH = [
    ("rewe bet>20 && dt in -5d", '"rewe" and betrag > 20 and datum in -5d'),   # Beispiel der Definition
    ("empf=='REWE'", 'empfänger == "REWE"'),
    ('vwz != "x"   ||   bet<=5', 'verwendungszweck != "x" or betrag <= 5'),
    ('(betrag > 10)', "betrag > 10"),
    ('(empf == "a" or vwz == "b") and bet > 1', '(empfänger == "a" or verwendungszweck == "b") and betrag > 1'),
    ('empf == "a" or (vwz == "b" and bet > 1)', 'empfänger == "a" or verwendungszweck == "b" and betrag > 1'),
    ('empfaenger == "REWE"', 'empfänger == "REWE"'),
    ("dt == 5.2.", "datum == 05.02."),
    ("dt >= 1.1.2017", "datum >= 01.01.2017"),
    ("dt in dieser_monat", "datum in dieser_monat"),
    ('dir == "ausgabe"', 'richtung == "ausgabe"'),
    ('"Rewe Markt"', '"Rewe Markt"'),
]


@pytest.mark.parametrize("eingabe,soll", KANONISCH)
def test_kanonisch(api, eingabe, soll):
    p = gueltig(api, eingabe, "filter")
    assert p["kanonisch"] == soll
    assert "\n" not in p["kanonisch"]
    # die kanonische Schreibweise eines kanonischen Ausdrucks ist er selbst
    assert gueltig(api, soll, "filter")["kanonisch"] == soll


@pytest.mark.parametrize("eingabe", REGEL_GUELTIG)
def test_kanonisch_idempotent(api, eingabe):
    k1 = gueltig(api, eingabe, "regel")["kanonisch"]
    assert gueltig(api, k1, "regel")["kanonisch"] == k1
    for kurz, voll in (("empf ", "empfänger "), ("vwz ", "verwendungszweck "), ("bet ", "betrag "),
                       ("dir ", "richtung ")):
        if eingabe.startswith(kurz):
            assert k1.startswith(voll), "volle Feldnamen"
    assert "&&" not in k1 and "||" not in k1 and "'" not in k1


def test_freitext_teile_und_hinweis(api):
    p = gueltig(api, "rewe bet > 20", "filter")
    assert p["kanonisch"] == '"rewe" and betrag > 20'
    assert p["freitext"], "erkannter Freitext"
    assert p["hinweise"], "Hinweis: Wort wird als Freitext gelesen"
    p = gueltig(api, "rewe pfand", "filter")
    assert len(p["freitext"]) >= 1
    assert gueltig(api, "betrag > 20", "filter")["freitext"] == []


def test_festschreiben(api):
    frei = gueltig(api, "datum in -5d and betrag > 1", "filter")
    assert frei["kanonisch"] == "datum in -5d and betrag > 1", "relative Angaben bleiben relativ"
    fest = gueltig(api, "datum in -5d and betrag > 1", "filter", festschreiben=True)
    assert "-5d" not in fest["kanonisch"] and "betrag > 1" in fest["kanonisch"]
    # der festgeschriebene Text meint an jedem Bezugstag denselben Zeitraum
    d = gueltig(api, fest["kanonisch"], "filter", stichtag="2030-01-01")["datumsangaben"]
    assert (min(x["von"] for x in d), max(x["bis"] for x in d)) == ("2026-11-12", "2026-11-16")
    heute = gueltig(api, "datum == heute", "filter", festschreiben=True)
    assert "heute" not in heute["kanonisch"]
    (x,) = gueltig(api, heute["kanonisch"], "filter", stichtag="2031-05-05")["datumsangaben"]
    assert (x["von"], x["bis"]) == (STICHTAG, STICHTAG)


# ------------------------------------------------------------------ Fehlercodes
FEHLER = [
    # (Ausdruck, Kontext, zulässige Codes)
    ("", "filter", "syntax"), ("   ", "regel", "syntax"), ("betrag >", "filter", "syntax"),
    ('empfänger == "a" and', "regel", "syntax"), ('(empfänger == "a"', "regel", "syntax"),
    ('empfänger = "REWE"', "regel", "syntax"),
    ('foo == "x"', "regel", "feld_unbekannt"), ("rewe", "regel", "feld_unbekannt"),
    ('empfänger.foo("x")', "regel", "methode_unbekannt"),
    ('"x" in betrag', "regel", ("operator_unpassend", "wert_ungueltig")),
    ('betrag > "10"', "regel", ("operator_unpassend", "wert_ungueltig")),
    ("empfänger", "regel", "kein_wahrheitswert"), ("betrag", "regel", "kein_wahrheitswert"),
    ("betrag > 10.123", "regel", "wert_ungueltig"), ('richtung == "quatsch"', "regel", "wert_ungueltig"),
    ("monat == 13", "regel", "wert_ungueltig"), ('status == "offen"', "regel", "wert_ungueltig"),
    ('empfänger.search(r"(")', "regel", "regex_ungueltig"),
    ('empfänger.search(r"(a)\\1")', "regel", "regex_nicht_unterstuetzt"),
    ('empfänger.search(r"a(?=b)")', "regel", "regex_nicht_unterstuetzt"),
    ('empfänger.search(r"(?<!a)b")', "regel", "regex_nicht_unterstuetzt"),
    ('kategorie == "Gibt:Es:Nicht"', "regel", "referenz_unbekannt"),
    ('"Nichtvorhanden" in tags', "regel", "referenz_unbekannt"),
    ('konto == "Nichtvorhanden"', "regel", "referenz_unbekannt"),
    ("datum == heute", "regel", "nur_im_filter"), ("jahr == 2024", "regel", "nur_im_filter"),
    ("kw == 5", "regel", "nur_im_filter"), ("dt >= 1.1.2024 and betrag > 1", "regel", "nur_im_filter"),
    ("datum == 30.2.", "filter", "datum_ungueltig"), ("datum == 31.4.2025", "filter", "datum_ungueltig"),
    ("datum == 5.2", "filter", "datum_ungueltig"),
    ("datum in 1.3.2024 .. 1.2.2024", "filter", "zeitraum_leer"),
    ("datum in 5d", "filter", "dauer_ohne_vorzeichen"),
    ("datum in -5x", "filter", "einheit_unbekannt"),
    ('"' + "a" * 4000 + '" in empfänger', "regel", "zu_lang"),
    ('empfänger.search(r"' + "a" * 501 + '")', "regel", ("zu_lang", "regex_ungueltig")),
]


@pytest.mark.parametrize("ausdruck,kontext,codes", FEHLER,
                         ids=[f"{i:02d}-{c if isinstance(c, str) else c[0]}" for i, (_, _, c) in enumerate(FEHLER)])
def test_fehlercode(b, ausdruck, kontext, codes):
    f = ungueltig(b.api, ausdruck, codes, kontext)
    assert f["meldung"].strip()


def test_einfaches_gleich_nennt_doppeltes(api):
    f = ungueltig(api, 'empfänger = "REWE"', "syntax", "regel")
    assert "==" in f["meldung"] or "==" in str(f["erwartet"]), f


def test_fehlerstelle_zeile_und_spalte(api):
    """Zeile und Spalte zählen ab 1, in Zeichen (das ``ä`` ist eine Spalte)."""
    f = ungueltig(api, 'foo == "x"', "feld_unbekannt", "regel")
    assert (f["zeile"], f["spalte"]) == (1, 1)
    f = ungueltig(api, 'empfänger == "a" and foo == 1', "feld_unbekannt", "regel")
    assert (f["zeile"], f["spalte"]) == (1, 22)
    f = ungueltig(api, 'empfänger == "a" and\n  foo == 1', "feld_unbekannt", "regel")
    assert (f["zeile"], f["spalte"]) == (2, 3) and f["ende_zeile"] == 2
    f = ungueltig(api, 'betrag > 1 and empfänger.foo("x")', "methode_unbekannt", "regel")
    assert f["zeile"] == 1 and 16 <= f["spalte"] <= 26, "Stelle an Feld oder Methode"


def test_laengengrenzen(api):
    kurz = 'betrag > 1'
    genau = kurz + " " * (4000 - len(kurz) - len(" and betrag < 9")) + " and betrag < 9"
    assert len(genau) == 4000
    gueltig(api, genau, "regel")
    ungueltig(api, genau.replace(" and", "  and", 1), "zu_lang", "regel")
    gueltig(api, 'empfänger.search(r"' + "a" * 500 + '")', "regel")


def test_unbekanntes_wort_im_filter_ist_freitext(api):
    gueltig(api, "rewe", "filter")
    ungueltig(api, "rewe", "feld_unbekannt", "regel")


def test_relativer_zeitraum_vor_beginn_ist_gueltig(api):
    """2.4: Ein Zeitraum mit relativen Angaben, der vor seinem Beginn endet, ist gültig (und trifft nichts)."""
    gueltig(api, "datum in heute .. gestern", "filter")


# ------------------------------------------------------------------ 2.4 Datumsangaben
def _z(von: str, bis: str | None = None):
    return von, bis or von


DATUM = [
    ("5.2.", _z("2026-02-05")), ("05.02.", _z("2026-02-05")), ("5.2.26", _z("2026-02-05")),
    ("1.1.2017", _z("2017-01-01")), ("2026-02-05", _z("2026-02-05")), ("1.1.35", _z("2035-01-01")),
    ("1.1.38", _z("1938-01-01")), ("1.1.99", _z("1999-01-01")),
    ("heute", _z("2026-11-16")), ("gestern", _z("2026-11-15")), ("vorgestern", _z("2026-11-14")),
    ("morgen", _z("2026-11-17")),
    ("-5d", _z("2026-11-12", "2026-11-16")), ("-5t", _z("2026-11-12", "2026-11-16")),
    ("-2w", _z("2026-11-03", "2026-11-16")),
    ("2017", _z("2017-01-01", "2017-12-31")),
    ("2/2025", _z("2025-02-01", "2025-02-28")), ("2025-02", _z("2025-02-01", "2025-02-28")),
    ("feb", _z("2026-02-01", "2026-02-28")), ("mär/2024", _z("2024-03-01", "2024-03-31")),
    ("2/2024", _z("2024-02-01", "2024-02-29")),
    ("q3", _z("2026-07-01", "2026-09-30")), ("q4/2025", _z("2025-10-01", "2025-12-31")),
    ("kw46", _z("2026-11-09", "2026-11-15")), ("kw46/2026", _z("2026-11-09", "2026-11-15")),
    ("kw1/2026", _z("2025-12-29", "2026-01-04")),
    ("diese_woche", _z("2026-11-16", "2026-11-22")), ("letzte_woche", _z("2026-11-09", "2026-11-15")),
    ("naechste_woche", _z("2026-11-23", "2026-11-29")),
    ("dieser_monat", _z("2026-11-01", "2026-11-30")), ("letzter_monat", _z("2026-10-01", "2026-10-31")),
    ("naechster_monat", _z("2026-12-01", "2026-12-31")),
    ("dieses_quartal", _z("2026-10-01", "2026-12-31")), ("letztes_quartal", _z("2026-07-01", "2026-09-30")),
    ("dieses_jahr", _z("2026-01-01", "2026-12-31")), ("letztes_jahr", _z("2025-01-01", "2025-12-31")),
    ("vorjahr", _z("2025-01-01", "2025-12-31")), ("naechstes_jahr", _z("2027-01-01", "2027-12-31")),
    ("29.2.", _z("2026-02-28")),
]


def _spanne(p: dict) -> tuple[str, str]:
    d = p["datumsangaben"]
    assert d, "datumsangaben leer"
    for x in d:
        if x["von"] and x["bis"]:
            tage = (dt.date.fromisoformat(x["bis"]) - dt.date.fromisoformat(x["von"])).days + 1
            assert x["tage"] == max(tage, 0), f"tage von {x}"
    return min(x["von"] for x in d), max(x["bis"] for x in d)


@pytest.mark.parametrize("angabe,soll", DATUM, ids=[a for a, _ in DATUM])
def test_datumsangabe(api, angabe, soll):
    p = gueltig(api, f"datum in {angabe}", "filter")
    assert len(p["datumsangaben"]) == 1
    assert _spanne(p) == soll


def test_datumsangabe_folgt_dem_stichtag(api):
    assert _spanne(gueltig(api, "datum == 29.2.", stichtag="2024-06-01")) == _z("2024-02-29")
    assert _spanne(gueltig(api, "datum == heute", stichtag="2024-02-29")) == _z("2024-02-29")
    assert _spanne(gueltig(api, "datum in letzter_monat", stichtag="2024-03-31")) == _z("2024-02-01", "2024-02-29")
    assert _spanne(gueltig(api, "datum in letzte_woche", stichtag="2027-01-03")) == _z("2026-12-21", "2026-12-27")
    assert _spanne(gueltig(api, "datum in kw53", stichtag="2026-06-01")) == _z("2026-12-28", "2027-01-03")
    assert _spanne(gueltig(api, "datum == 1.1.38", stichtag="2030-06-01")) == _z("2038-01-01")


def test_datumsangabe_zeitraum_und_rechnen(api):
    assert _spanne(gueltig(api, "datum in 1.1.2024 .. 2/2024")) == _z("2024-01-01", "2024-02-29")
    assert _spanne(gueltig(api, "datum in 2/2024 .. 4/2024")) == _z("2024-02-01", "2024-04-30")
    assert _spanne(gueltig(api, "datum in letztes_jahr .. heute")) == _z("2025-01-01", "2026-11-16")
    # Lesart E-272 Punkt 3: nur das eindeutige Ende wird geprüft
    for angabe, einheit in (("-1m", "m"), ("-1y", "y"), ("-1j", "y"), ("-1q", "q")):
        von, bis = _spanne(gueltig(api, f"datum in {angabe}"))
        assert bis == STICHTAG, angabe
        zurueck = {"m": dt.date(2026, 10, 16), "y": dt.date(2025, 11, 16), "q": dt.date(2026, 8, 16)}[einheit]
        assert von in (zurueck.isoformat(), (zurueck + dt.timedelta(days=1)).isoformat()), f"{angabe}: von {von}"
    assert _spanne(gueltig(api, "datum in +3d"))[0] == STICHTAG
    assert _spanne(gueltig(api, "datum in 1.1.2025 + 1y"))[0] == "2025-01-01"
    assert _spanne(gueltig(api, "datum in 2/2025 - 30d"))[1] == "2025-02-28"
    # Monatsrechnung: fehlt der Tag im Zielmonat, gilt dessen letzter Tag
    von, bis = _spanne(gueltig(api, "datum in -1m", stichtag="2024-03-31"))
    assert bis == "2024-03-31" and von in ("2024-02-29", "2024-03-01")


def test_datumsangabe_relativ(api):
    for angabe in ("heute", "-5d", "dieser_monat"):
        (x,) = gueltig(api, f"datum in {angabe}")["datumsangaben"]
        assert x["relativ"] is True, angabe
    for angabe in ("1.1.2017", "2026-02-05", "2/2025", "q4/2025", "kw46/2026"):
        (x,) = gueltig(api, f"datum in {angabe}")["datumsangaben"]
        assert x["relativ"] is False, angabe


def test_jahr_nur_am_datumsfeld(api):
    assert _spanne(gueltig(api, "datum == 2017")) == _z("2017-01-01", "2017-12-31")
    assert gueltig(api, "jahr == 2017")["datumsangaben"] == [], "am Feld jahr ist 2017 eine Zahl"
    assert gueltig(api, "betrag == 2017")["datumsangaben"] == []


# ------------------------------------------------------------------ 4.3 als-regel
def _als_regel(api, ausdruck, erwartet=200, **felder):
    r = api.post("/api/ausdruck/als-regel", json={"ausdruck": ausdruck, **felder}, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def _kanon(api, d):
    """Regel-Ausdruck der Antwort in kanonischer Schreibweise (muss im Kontext ``regel`` gültig sein)."""
    return gueltig(api, d["ausdruck"], "regel")["kanonisch"]


def test_als_regel_entfernt_filterteile(api):
    d = _als_regel(api, 'empf == "REWE" and dt in -5d and bet > 20')
    assert _kanon(api, d) == 'empfänger == "REWE" and betrag > 20'
    assert len(d["entfernt"]) == 1
    d = _als_regel(api, 'betrag > 20 and jahr == 2025 and kw == 3')
    assert _kanon(api, d) == "betrag > 20" and len(d["entfernt"]) == 2


def test_als_regel_freitext(api):
    d = _als_regel(api, "rewe bet > 20")
    assert _kanon(api, d) == '"rewe" in empfänger and betrag > 20' and d["entfernt"] == []
    d = _als_regel(api, "rewe bet > 20", freitext_feld="verwendungszweck")
    assert _kanon(api, d) == '"rewe" in verwendungszweck and betrag > 20'
    d = _als_regel(api, "rewe", freitext_feld="empfänger")
    assert _kanon(api, d) == '"rewe" in empfänger'


def test_als_regel_unveraendert_und_leer(api):
    d = _als_regel(api, 'vwz.startswith("Miete") or betrag >= 500')
    assert _kanon(api, d) == 'verwendungszweck.startswith("Miete") or betrag >= 500' and d["entfernt"] == []
    d = _als_regel(api, "datum in dieses_jahr")
    assert d["ausdruck"] is None and len(d["entfernt"]) == 1


def test_als_regel_fehler(api):
    m30.ausdruck_ungueltig(_als_regel(api, "betrag >", erwartet=422), "syntax")
    for body in ({}, {"ausdruck": "betrag > 1", "freitext_feld": "notiz"}, {"ausdruck": "betrag > 1", "x": 1}):
        assert fehlercode(api.post("/api/ausdruck/als-regel", json=body, erwartet=422)) == "validierung"
