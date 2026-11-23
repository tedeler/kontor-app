"""M30: Filter über einen Ausdruck an ``GET /api/buchungen`` und am Export (ausdruecke.md 2, 5; E-272) – REST, kern.

Die Erwartung je Ausdruck rechnet der Test aus den selbst angelegten Buchungen (``m30.bestand``); der Bezugstag
relativer Datumsangaben ist immer ``stichtag`` = 2026-11-16 (Definition 13).
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import m30
from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m5 import csv_buchungen, csv_lesen, export
from tests.hilfen.m30 import STICHTAG, falte, gefiltert, gueltig, treffer

pytestmark = pytest.mark.kern
D = dt.date


@pytest.fixture(scope="module")
def b(api_fabrik):
    """Nur lesend verwendet."""
    return m30.bestand(api_fabrik())


def _zwischen(f, von, bis):
    return D.fromisoformat(von) <= f.datum <= D.fromisoformat(bis)


#: (Ausdruck, Erwartung als Funktion des Falls)
FAELLE = [
    # Text (2.3): Groß-/Kleinschreibung egal, Umlaute angeglichen
    ('"REWE" in empfänger', lambda f: f.hat("rewe")),
    ('"rewe" in empf', lambda f: f.hat("rewe")),
    ('"REWE" not in empfänger', lambda f: not f.hat("rewe")),
    ('"mueller" in empfänger', lambda f: f.hat("müller")),
    ('"MÜLLER" in empfaenger', lambda f: f.hat("müller")),
    ('empfänger == "edeka"', lambda f: falte(f.empf) == "edeka"),
    ('empfänger != "EDEKA"', lambda f: falte(f.empf) != "edeka"),
    ('empfänger == ""', lambda f: f.empf == ""),
    ('empfänger.startswith("rewe")', lambda f: falte(f.empf).startswith("rewe")),
    ('empfänger.startswith("rewe", case=True)', lambda f: False),
    ('empfänger.startswith("REWE", case=True)', lambda f: f.empf.startswith("REWE")),
    ('empfänger.endswith("gmbh")', lambda f: falte(f.empf).endswith("gmbh")),
    ('empfänger.startswith("mueller")', lambda f: falte(f.empf).startswith("mueller")),
    ('empfänger.startswith("mueller", fold=False)', lambda f: False),
    ('empfänger.startswith("müller", fold=False)', lambda f: f.empf.casefold().startswith("müller")),
    ('empfänger.search(r"^(REWE|EDEKA)")', lambda f: f.empf.startswith(("REWE", "EDEKA"))),
    ('empfänger.search(r"Markt")', lambda f: "Markt" in f.empf),
    ('empfänger in ["EDEKA", "Müller Drogerie"]', lambda f: f.empf in ("EDEKA", "Müller Drogerie")),
    ('"REWE  Markt" in empfänger', lambda f: False),            # mehrfache Leerzeichen bleiben
    ('"überweisung" in verwendungszweck', lambda f: f.hat("überweisung", "zweck")),
    ('"UEBERWEISUNG" in vwz', lambda f: f.hat("überweisung", "zweck")),
    ('verwendungszweck == "Brot"', lambda f: f.zweck == "Brot"),
    ('"Pfand" in notiz', lambda f: "Pfand" in f.notiz),
    ('notiz == "Dauerauftrag"', lambda f: f.notiz == "Dauerauftrag"),
    # Betrag ohne Vorzeichen in Euro, Richtung
    ("betrag > 20", lambda f: f.betrag > 2000),
    ("betrag >= 20", lambda f: f.betrag >= 2000),
    ("betrag < 20", lambda f: f.betrag < 2000),
    ("betrag == 25.5", lambda f: f.betrag == 2550),
    ("bet == 25.50", lambda f: f.betrag == 2550),
    ("betrag != 25.5", lambda f: f.betrag != 2550),
    ("12 <= betrag <= 35", lambda f: 1200 <= f.betrag <= 3500),
    ("betrag >= 2_500", lambda f: f.betrag >= 250000),
    ('richtung == "ausgabe"', lambda f: f.richtung == "ausgabe"),
    ('dir == "einnahme"', lambda f: f.richtung == "einnahme"),
    ('richtung == "umbuchung"', lambda f: f.umbuchung),
    ('richtung in ["einnahme", "umbuchung"]', lambda f: f.richtung != "ausgabe"),
    # Kategorie, Status, Tags, Konto
    ("kategorie is None", lambda f: f.kategorie is None),
    ("kategorie is not None", lambda f: f.kategorie is not None),
    ('kategorie == "Lebensmittel:Supermarkt"', lambda f: f.kategorie == "Lebensmittel:Supermarkt"),
    ('kategorie == "Lebensmittel"', lambda f: f.kategorie == "Lebensmittel"),
    ('kategorie in ["Wohnen", "Gehalt"]', lambda f: f.kategorie in ("Wohnen", "Gehalt")),
    ('status == "bestaetigt"', lambda f: f.status == "bestaetigt"),
    ('status in ["importiert", "vorlaeufig"]', lambda f: f.status in ("importiert", "vorlaeufig")),
    ('status != "abgeglichen"', lambda f: f.status != "abgeglichen"),
    ('"Urlaub" in tags', lambda f: "Urlaub" in f.tags),
    ('"Urlaub" not in tags', lambda f: "Urlaub" not in f.tags),
    ('"Urlaub" in tags and "Steuer" in tags', lambda f: {"Urlaub", "Steuer"} <= f.tags),
    ('konto == "Spar"', lambda f: "Spar" in f.konten),
    ('konto == "Giro"', lambda f: True),
    # Kalenderfelder
    ("monatstag == 16", lambda f: f.datum.day == 16), ("monatstag >= 29", lambda f: f.datum.day >= 29),
    ("monat == 11", lambda f: f.datum.month == 11), ("monat == dez", lambda f: f.datum.month == 12),
    ("monat == feb", lambda f: f.datum.month == 2),
    ("quartal == 1", lambda f: f.quartal == 1), ("quartal == 4", lambda f: f.quartal == 4),
    ("jahr == 2026", lambda f: f.datum.year == 2026), ("jahr < 2026", lambda f: f.datum.year < 2026),
    ("kw == 46", lambda f: f.kw == 46), ("kw == 47", lambda f: f.kw == 47),
    ('wochentag == "mo"', lambda f: f.wochentag == "mo"),
    ('wochentag in ["sa", "so"]', lambda f: f.wochentag in ("sa", "so")),
    ('wochentag == "wochenende"', lambda f: f.wochentag in ("sa", "so")),
    ('wochentag == "werktag"', lambda f: f.wochentag not in ("sa", "so")),
    ("letzter_tag", lambda f: f.letzter_tag), ("not letzter_tag", lambda f: not f.letzter_tag),
    ("letzter_tag == True", lambda f: f.letzter_tag),
    # Verknüpfungen: not vor and vor or
    ('not "REWE" in empfänger and betrag > 20', lambda f: not f.hat("rewe") and f.betrag > 2000),
    ('"REWE" in empfänger or "EDEKA" in empfänger and betrag > 15',
     lambda f: f.hat("rewe") or (f.hat("edeka") and f.betrag > 1500)),
    ('("REWE" in empfänger or "EDEKA" in empfänger) and betrag > 15',
     lambda f: (f.hat("rewe") or f.hat("edeka")) and f.betrag > 1500),
    ('"REWE" in empf && bet > 20 || !("Urlaub" not in tags)',
     lambda f: (f.hat("rewe") and f.betrag > 2000) or "Urlaub" in f.tags),
    ("kategorie is null and betrag > 13", lambda f: f.kategorie is None and f.betrag > 1300),
    # Datumsangaben und Vergleiche mit Zeiträumen (2.4), Bezugstag 16.11.2026
    ("datum == heute", lambda f: f.datum == D(2026, 11, 16)),
    ("dt == gestern", lambda f: f.datum == D(2026, 11, 15)),
    ("datum in -5d", lambda f: _zwischen(f, "2026-11-12", "2026-11-16")),
    ("datum in -2w", lambda f: _zwischen(f, "2026-11-03", "2026-11-16")),
    ("datum == 5.2.", lambda f: f.datum == D(2026, 2, 5)),
    ("datum == 29.2.2024", lambda f: f.datum == D(2024, 2, 29)),
    ("datum == 2024-02-29", lambda f: f.datum == D(2024, 2, 29)),
    ("datum == 2025", lambda f: f.datum.year == 2025), ("datum in 2026", lambda f: f.datum.year == 2026),
    ("datum == feb", lambda f: _zwischen(f, "2026-02-01", "2026-02-28")),
    ("datum == 2/2024", lambda f: _zwischen(f, "2024-02-01", "2024-02-29")),
    ("datum in q4", lambda f: _zwischen(f, "2026-10-01", "2026-12-31")),
    ("datum in kw46", lambda f: _zwischen(f, "2026-11-09", "2026-11-15")),
    ("datum in diese_woche", lambda f: _zwischen(f, "2026-11-16", "2026-11-22")),
    ("datum in letzte_woche", lambda f: _zwischen(f, "2026-11-09", "2026-11-15")),
    ("datum in dieser_monat", lambda f: _zwischen(f, "2026-11-01", "2026-11-30")),
    ("datum in letzter_monat", lambda f: _zwischen(f, "2026-10-01", "2026-10-31")),
    ("datum in letztes_jahr", lambda f: f.datum.year == 2025), ("datum in vorjahr", lambda f: f.datum.year == 2025),
    ("datum >= letzte_woche", lambda f: f.datum >= D(2026, 11, 9)),      # >= ab a
    ("datum > letzte_woche", lambda f: f.datum > D(2026, 11, 15)),       # > nach b
    ("datum <= letzte_woche", lambda f: f.datum <= D(2026, 11, 15)),     # <= bis b
    ("datum < letzte_woche", lambda f: f.datum < D(2026, 11, 9)),        # < vor a
    ("datum >= 2026", lambda f: f.datum.year >= 2026), ("datum < 2026", lambda f: f.datum.year < 2026),
    ("datum > 2025", lambda f: f.datum.year > 2025), ("datum <= 2025", lambda f: f.datum.year <= 2025),
    ("datum in 1.11.2026 .. 15.11.2026", lambda f: _zwischen(f, "2026-11-01", "2026-11-15")),
    ("datum in 2/2024 .. letztes_jahr", lambda f: _zwischen(f, "2024-02-01", "2025-12-31")),
    ("datum in heute .. gestern", lambda f: False),                      # endet vor Beginn: trifft nichts
    ('datum in dieser_monat and "REWE" in empfänger', lambda f: f.datum.month == 11 and f.datum.year == 2026
     and f.hat("rewe")),
    # Freitext (2.5)
    ("rewe", lambda f: f.freitext("rewe")),
    ("pfand", lambda f: f.freitext("pfand")),                            # Notiz und Verwendungszweck
    ("urlaub", lambda f: f.freitext("urlaub")),                          # Tag
    ("rewe pfand", lambda f: f.freitext("rewe", "pfand")),
    ("müller vorrat", lambda f: f.freitext("müller", "vorrat")),
    ('"rewe markt"', lambda f: f.freitext("rewe markt")),
    ("rewe bet > 20", lambda f: f.freitext("rewe") and f.betrag > 2000),
    ("gibtesnicht", lambda f: False),
]


@pytest.mark.parametrize("ausdruck,erwartung", FAELLE, ids=[f"{i:03d}" for i in range(len(FAELLE))])
def test_filter_trifft(b, ausdruck, erwartung):
    # Betrag und Kategorie einer Umbuchung ohne Konto legt die Definition nicht fest (E-272 Punkt 4)
    offen = {"sparen"} if any(w in ausdruck for w in ("bet", "kategorie")) else set()
    soll = b.soll(erwartung) - offen
    assert treffer(b, ausdruck) - offen == soll, ausdruck
    # ein Ausdruck und seine kanonische Schreibweise treffen dieselben Buchungen (2.6)
    kanonisch = gueltig(b.api, ausdruck, "filter")["kanonisch"]
    assert treffer(b, kanonisch) - offen == soll, f"kanonisch: {kanonisch}"


def test_stichtag_uebersteuert_heute(b):
    assert treffer(b, "datum == heute", stichtag="2026-02-05") == {"miete"}
    assert treffer(b, "datum in letzter_monat", stichtag="2026-12-03") == b.soll(
        lambda f: f.datum.year == 2026 and f.datum.month == 11)
    assert treffer(b, "datum == 29.2.", stichtag="2024-12-01") == {"schalttag"}
    assert treffer(b, "datum == 29.2.", stichtag=STICHTAG) == set(), "29.2. gilt 2026 als 28.02."


def test_filter_und_uebrige_parameter(b):
    """``filter`` wird mit den übrigen Parametern per and verknüpft; Sortierung, Seiten und Summe wie bisher."""
    api, giro = b.api, b.k["Giro"]
    ausdruck = '"REWE" in empfänger or "EDEKA" in empfänger'
    soll = b.soll(lambda f: f.hat("rewe") or f.hat("edeka"))
    assert treffer(b, ausdruck, von="2026-11-01") == {n for n in soll if b[n].datum >= D(2026, 11, 1)}
    assert treffer(b, ausdruck, status="bestaetigt") == {n for n in soll if b[n].status == "bestaetigt"}
    assert treffer(b, ausdruck, tag_id=b.t["Urlaub"]) == {n for n in soll if "Urlaub" in b[n].tags}
    assert treffer(b, ausdruck, konto_id=b.k["Spar"]) == set()
    ids = [x["id"] for x in gefiltert(api, ausdruck, konto_id=giro, sortierung="-datum")]
    assert ids == [b[n].id for n in sorted(soll, key=lambda n: (-b[n].datum.toordinal(), b[n].id))]
    ohne = api.seite(konto_id=giro, empfaenger_id=b.e["EDEKA"])
    mit = api.seite(konto_id=giro, filter='empfänger == "EDEKA"', stichtag=STICHTAG)
    assert [x["id"] for x in mit["eintraege"]] == [x["id"] for x in ohne["eintraege"]]
    assert mit["gesamt"] == ohne["gesamt"] == 2
    for feld in ("summe", "seite", "pro_seite"):
        if feld in ohne:
            assert mit[feld] == ohne[feld], feld
    s1 = api.seite(filter='status != "abgeglichen"', stichtag=STICHTAG, pro_seite=3, seite=1, sortierung="datum")
    s2 = api.seite(filter='status != "abgeglichen"', stichtag=STICHTAG, pro_seite=3, seite=2, sortierung="datum")
    assert s1["gesamt"] == s2["gesamt"] == len(b.soll(lambda f: f.status != "abgeglichen"))
    assert len(s1["eintraege"]) == len(s2["eintraege"]) == 3
    assert not {x["id"] for x in s1["eintraege"]} & {x["id"] for x in s2["eintraege"]}


def test_betrag_und_richtung_im_kontoblatt(api):
    """2.2: ohne Konto die Summe der Splits auf Bestandskonten, im Kontoblatt die Splits des angezeigten Kontos."""
    giro, spar = api.konto("Giro")["id"], api.konto("Spar", "sparkonto")["id"]
    wohnen = api.konto("Wohnen", "aufwand")["id"]
    um = api.buchung("2026-11-10", [(giro, -10000), (spar, 10000)])["id"]
    gem = api.buchung("2026-11-11", [(giro, -10000), (spar, 3000), (wohnen, 7000)])["id"]

    def ids(ausdruck, **p):
        return {x["id"] for x in gefiltert(api, ausdruck, **p)}

    assert ids("betrag == 70") == {gem} and ids('richtung == "ausgabe"') == {gem}
    assert ids('richtung == "umbuchung"') == {um}
    assert ids("betrag == 100", konto_id=giro) == {um, gem}
    assert ids("betrag == 100", konto_id=spar) == {um}
    assert ids("betrag == 30", konto_id=spar) == {gem}
    assert ids('richtung == "einnahme"', konto_id=spar) >= {gem}
    assert ids('richtung == "ausgabe"', konto_id=giro) >= {gem}
    assert ids("betrag == 30") == set() and ids("betrag == 70", konto_id=spar) == set()


def test_iban_der_gegenseite(tmp_path, netz_gesperrt):
    """``iban``: IBAN der Gegenseite (nur von der Synchronisation gesetzt), sonst leer."""
    from tests.hilfen.m2 import mock_api, regeln_anlegen, sync

    api = mock_api(tmp_path)
    regeln_anlegen(api)
    sync(api, von="2024-01-01")
    alle = api.alle_buchungen()
    mit = [x for x in alle if x["gegen_iban"]]
    assert mit, "die Mock-Daten enthalten Umsätze mit Gegen-IBAN"
    iban = mit[0]["gegen_iban"]
    assert {x["id"] for x in gefiltert(api, f'iban == "{iban}"')} == {x["id"] for x in alle if x["gegen_iban"] == iban}
    assert {x["id"] for x in gefiltert(api, 'iban == ""')} == {x["id"] for x in alle if not x["gegen_iban"]}
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ markierungen
def _stelle(text: str, m: dict) -> set:
    """Markierter Text für die offenen Zählweisen (``ende`` aus- oder einschließend, Beginn ab 0 oder 1;
    E-272 Punkt 5)."""
    s, e = m["start"], m["ende"]
    return {falte(text[s:e]), falte(text[s:e + 1]), falte(text[max(s - 1, 0):e])}


def test_markierungen(b):
    for x in gefiltert(b.api, '"rewe" in empfänger'):
        assert isinstance(x["markierungen"], list)
        m = [y for y in x["markierungen"] if falte(y["feld"]) in ("empfaenger", "empf")]
        assert m, f"Markierung im Empfänger fehlt: {x['markierungen']}"
        assert any("rewe" in _stelle(x["empfaenger"]["name"], y) for y in m), m
    (x,) = gefiltert(b.api, '"woche" in verwendungszweck')
    m = [y for y in x["markierungen"] if y["feld"] in ("verwendungszweck", "vwz")]
    assert any("woche" in _stelle(x["verwendungszweck"], y) for y in m), x["markierungen"]
    assert x["verwendungszweck"] == "Einkauf Wochenmarkt"
    for x in gefiltert(b.api, "betrag > 20"):
        assert x["markierungen"] == [] or all(y["ende"] >= y["start"] for y in x["markierungen"])


# ------------------------------------------------------------------ Fehler, Lesezugriff
@pytest.mark.parametrize("ausdruck,code", [("betrag >", "syntax"), ("datum == 30.2.", "datum_ungueltig"),
                                           ('kategorie == "Gibt:Es:Nicht"', "referenz_unbekannt"),
                                           ("datum in 5d", "dauer_ohne_vorzeichen"),
                                           ('empfänger.search(r"(a)\\1")', "regex_nicht_unterstuetzt")])
def test_ungueltiger_filter(b, ausdruck, code):
    r = b.api.get("/api/buchungen", params={"filter": ausdruck, "stichtag": STICHTAG}, erwartet=422)
    fehler = m30.ausdruck_ungueltig(r, code)
    assert fehler[0]["zeile"] == 1 and fehler[0]["spalte"] >= 1


def test_stichtag_ungueltig(b):
    r = b.api.get("/api/buchungen", params={"filter": "betrag > 1", "stichtag": "gestern"}, erwartet=422)
    assert fehlercode(r) == "validierung"


def test_filter_ist_lesezugriff(b):
    a0 = letzte_aenderung_id(b.api)
    vorher = b.api.alle_buchungen()
    gefiltert(b.api, '"REWE" in empfänger and datum in dieses_jahr')
    b.api.get("/api/buchungen", params={"filter": "betrag >"}, erwartet=422)
    assert letzte_aenderung_id(b.api) == a0 and b.api.alle_buchungen() == vorher


# ------------------------------------------------------------------ Export
def test_export_csv_mit_filter(b):
    api = b.api
    ausdruck = '"REWE" in empfänger and datum in -2w'
    ids = {x["id"] for x in csv_buchungen(csv_lesen(export(api, "csv", filter=ausdruck, stichtag=STICHTAG).content))}
    assert b.namen(ids) == b.soll(lambda f: f.hat("rewe") and _zwischen(f, "2026-11-03", "2026-11-16"))
    gleich = export(api, "csv", status="bestaetigt").content
    assert export(api, "csv", filter='status == "bestaetigt"', stichtag=STICHTAG).content == gleich
    kombiniert = csv_buchungen(csv_lesen(export(api, "csv", filter='"REWE" in empfänger', stichtag=STICHTAG,
                                                status="bestaetigt").content))
    assert b.namen(x["id"] for x in kombiniert) == b.soll(lambda f: f.hat("rewe") and f.status == "bestaetigt")


@pytest.mark.parametrize("endung", ["csv", "pdf"])
def test_export_ungueltiger_filter(b, endung):
    r = b.api.get(f"/api/export/buchungen.{endung}", params={"filter": "betrag >"}, erwartet=422)
    m30.ausdruck_ungueltig(r, "syntax")
    export(b.api, endung, filter="betrag > 20", stichtag=STICHTAG)
