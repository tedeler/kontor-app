"""M15: Mehrere Buchungen in einer Änderung löschen und Buchungen verschieben, Herkunft eines Kontos
(datenmodell.md 18, protokoll.md 4.1 und 14, E-183 bis E-185).

Erwartungen werden aus den im Test angelegten Daten berechnet; das Löschen wird mit einzelnen ``DELETE`` in einer
zweiten, gleich aufgebauten App verglichen (E-183).
"""

from __future__ import annotations

import datetime as dt

import pytest

from generator.iban import fiktive_iban
from tests.hilfen.api import neue_api
from tests.hilfen.kmybau import KBuch, KBuchung, KKonto, KSplit, gzip_bytes
from tests.hilfen.m2 import SYNC_DATEN, lade_sync, mock_api, nach_kennung, setze_zeit, sync
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m5 import Kreditbuch, kredit
from tests.hilfen.m6 import bestand, pruefe_eintraege, rundreise
from tests.hilfen.m9 import einspielen, inhalt, inhalt_sha256, lesezustand, oeffne, sicherung
from tests.hilfen.m15 import (LOESCHEN, VERSCHIEBEN, Verlauf, details, fehler, gruppen_buchungen, herkunft, loeschen,
                              ohne_wirkung, verschieben, verschoben_soll)
from tests.hilfen.pfade import KMY

GIRO_IBAN = fiktive_iban(7501)
VON = "2024-01-01"
HEUTE = dt.date(2024, 6, 30)


# ------------------------------------------------------------------ Aufbau


def aufbau(api) -> dict:
    """Konten, Buchungen mit Tags, Vorschlag, offenem Dublettenverdacht und Kreditrate (deterministisch)."""
    c: dict = {}
    c["giro"] = api.konto("Girokonto", iban=GIRO_IBAN)["id"]
    c["spar"] = api.konto("Tagesgeld", "sparkonto")["id"]
    c["karte"] = api.konto("Kreditkarte", "kreditkonto")["id"]
    c["leb"] = api.konto("Haushalt", "aufwand")["id"]
    c["offen"] = api.konto("Offen", "eigenkapital")["id"]
    c["markt"] = api.empfaenger("Supermarkt")["id"]
    c["drog"] = api.empfaenger("Drogeriemarkt Beispiel")["id"]
    c["tag"] = api.tag("Urlaub")["id"]
    g = c["giro"]
    c["b1"] = api.buchung("2024-01-10", [(g, -1234, "Wocheneinkauf"), (c["leb"], 1234, "Obst")],
                          empfaenger_id=c["markt"], tag_ids=[c["tag"]], verwendungszweck="Einkauf")["id"]
    c["b2"] = api.buchung("2024-01-12", [(g, -500), (c["offen"], 500)], empfaenger_id=c["drog"],
                          status="importiert")["id"]
    c["b3"] = api.buchung("2024-01-20", [(g, -10000), (c["spar"], 10000)], verwendungszweck="Sparen")["id"]
    c["b4"] = api.buchung("2024-01-21", [(c["spar"], -700), (c["leb"], 700)])["id"]
    regel = api.post("/api/regeln", json={"name": "Drogerie", "kategorie_id": c["leb"], "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "drogerie"}]}, erwartet=201).daten
    api.post("/api/regeln/anwenden", json={"regel_ids": [regel["id"]]}, erwartet=200)
    assert api.buchung_lesen(c["b2"])["vorschlag"] is not None, "Testvoraussetzung: Vorschlag"
    # offener Dublettenverdacht: gleicher Betrag einen Tag später aus KMyMoney
    kb = KBuch()
    kb.konten = [KKonto("A000001", "Girokonto", 1, "AStd::Asset", iban=GIRO_IBAN),
                 KKonto("A000002", "Lebensmittel", 13, "AStd::Expense")]
    kb.empfaenger = [("P000001", "Supermarkt")]
    kb.buchungen = [KBuchung("T000000000000000001", "2024-01-11",
                             [KSplit("A000001", -1234, empfaenger="P000001"), KSplit("A000002", 1234)])]
    api.post("/api/import/kmymoney", files={"datei": ("d.kmy", gzip_bytes(kb), "x")}, erwartet=200)
    (v,) = api.get("/api/dubletten", erwartet=200).daten
    c["verdacht"] = v["id"]
    c["dublette"] = v["buchung_id"]
    # Kreditrate, dem Kredit zugeordnet
    kr = Kreditbuch(api, giro=g)
    c["kredit"] = kr.anlegen(saldo_angleichen=False).daten["id"]
    c["rate"] = kr.zahlung("2024-02-01", 50_000)["id"]
    api.post(f"/api/kredite/{c['kredit']}/zuordnen", json={}, erwartet=200)
    assert kredit(api, c["kredit"])["zuordnungen"], "Testvoraussetzung: Rate zugeordnet"
    return c


def _ohne_zeit(b: dict) -> dict:
    """Entstehungszeit der Verdachte ist Systemzeit des Imports (nicht vergleichbar zwischen zwei Apps)."""
    return {k: ({**v, "erstellt_am": None} if k[0] == "verdacht" else v) for k, v in b.items()}


def _abgleichen(api, bid):
    api.patch(f"/api/buchungen/{bid}", json={"status": "bestaetigt"}, erwartet=(200,))
    api.patch(f"/api/buchungen/{bid}", json={"status": "abgeglichen"}, erwartet=200)


@pytest.fixture
def c(api):
    return aufbau(api)


# ================================================================== mehrfach/loeschen (18.1)


@pytest.mark.kern
def test_loeschen_wie_einzelne_delete(tmp_path):
    """E-183: gleicher Buchbestand wie nach einzelnen DELETE, inklusive Verdacht und Kreditzuordnung (beide Apps mit
    stehender simulierter Uhr, damit Zeitstempel gleich sind)."""
    api = neue_api(tmp_path / "eins", mock_modus=True, mock_heute=HEUTE)
    c = aufbau(api)
    zwilling = neue_api(tmp_path / "zwilling", mock_modus=True, mock_heute=HEUTE)
    c2 = aufbau(zwilling)
    assert c2 == c and _ohne_zeit(bestand(zwilling)) == _ohne_zeit(bestand(api)), "Testvoraussetzung"
    ids = [c["rate"], c["b1"], c["dublette"], c["b3"]]
    vorher = bestand(api)
    a0 = letzte_aenderung_id(api)
    r = loeschen(api, ids).daten
    assert r == {"geloescht": sorted(ids), "anzahl": 4}
    for b in sorted(ids):
        zwilling.delete(f"/api/buchungen/{b}", erwartet=204)
    nachher = bestand(api)
    assert _ohne_zeit(nachher) == _ohne_zeit(bestand(zwilling)), "Wirkung wie DELETE, Nebenwirkungen eingeschlossen"
    for b in ids:
        assert api.get(f"/api/buchungen/{b}", erwartet=404).status_code == 404
    assert ("verdacht", c["verdacht"]) not in nachher or nachher[("verdacht", c["verdacht"])]["status"] != "offen"
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"], a["rueckgaengig_von"]) == ("manuell", "mehrfach_loeschen", None,
                                                                              [])
    pruefe_eintraege(a, vorher, nachher)
    assert {("kredit", c["kredit"])} <= {(e["objekt"], e["objekt_id"]) for e in a["eintraege"]}
    rundreise(api, a, vorher, nachher)


@pytest.mark.kern
def test_loeschen_rueckgaengig_stellt_ids_wieder_her(api, c):
    vorher = bestand(api)
    splits = {b: [s["id"] for s in api.buchung_lesen(b)["splits"]] for b in (c["b1"], c["b4"])}
    a0 = letzte_aenderung_id(api)
    loeschen(api, [c["b4"], c["b1"]])
    (a,) = aenderungen_seit(api, a0)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher
    for b, s in splits.items():
        assert [x["id"] for x in api.buchung_lesen(b)["splits"]] == s


def test_loeschen_einer_buchung(api, c):
    a0 = letzte_aenderung_id(api)
    assert loeschen(api, [c["b4"]]).daten == {"geloescht": [c["b4"]], "anzahl": 1}
    assert [x["aktion"] for x in aenderungen_seit(api, a0)] == ["mehrfach_loeschen"]


@pytest.mark.kern
@pytest.mark.parametrize("koerper", [{}, {"buchung_ids": []}, {"buchung_ids": "DOPPELT"}, {"buchung_ids": [1.0]},
                                     {"buchung_ids": ["1"]}, {"buchung_ids": None}, {"buchung_ids": "ZUSATZ"}],
                         ids=["leer", "liste_leer", "doppelt", "float", "text", "null", "zusatzfeld"])
def test_loeschen_validierung(api, c, koerper):
    body = dict(koerper)
    if body.get("buchung_ids") == "DOPPELT":
        body["buchung_ids"] = [c["b1"], c["b1"]]
    if body.get("buchung_ids") == "ZUSATZ":
        body = {"buchung_ids": [c["b1"]], "trocken": True}

    def aufruf():
        assert fehler(api.post(LOESCHEN, json=body, erwartet=422)) == "validierung"
    ohne_wirkung(api, aufruf)


@pytest.mark.kern
def test_loeschen_pruefreihenfolge_und_atomar(api, c):
    _abgeglichen = c["b3"]
    _abgleichen(api, _abgeglichen)
    # abgestimmt: Tagesgeld bis 2024-01-21 (b3 +10000, b4 -700)
    api.post("/api/abstimmungen", json={"konto_id": c["spar"], "stichtag": "2024-01-21", "saldo": 9300},
             erwartet=200)
    assert api.buchung_lesen(c["b4"])["abgestimmt"] is True, "Testvoraussetzung"

    def unbekannt():
        r = loeschen(api, [999998, c["b1"], c["b3"], 999997], 422)
        assert (fehler(r), details(r)["buchung_ids"]) == ("referenz_unbekannt", [999997, 999998])

    def gesperrt():
        r = loeschen(api, [c["b4"], c["b1"], c["b3"]], 409)
        assert (fehler(r), details(r)["buchung_ids"]) == ("buchung_gesperrt", sorted([c["b3"], c["b4"]]))
    ohne_wirkung(api, unbekannt)
    ohne_wirkung(api, gesperrt)


# ================================================================== mehrfach/verschieben (18.2)


@pytest.mark.kern
def test_verschieben_auswahl(api, c):
    """Nur konto_id des Quellsplits ändert sich (Split-ID, Betrag, Memo, Vorschlag, Tags … gleich)."""
    ziel = api.konto("Altes Giro", "girokonto")["id"]
    ids = [c["b3"], c["b1"], c["b2"]]
    vorher = bestand(api)
    salden = api.salden()
    a0 = letzte_aenderung_id(api)
    r = verschieben(api, c["giro"], ziel, ids=ids).daten
    assert r == {"verschoben": sorted(ids), "anzahl": 3}
    nachher = bestand(api)
    for key, form in vorher.items():
        if key[0] == "buchung" and key[1] in ids:
            assert nachher[key] == verschoben_soll(form, c["giro"], ziel), key
    rest = {k: v for k, v in vorher.items() if not (k[0] == "buchung" and k[1] in ids)}
    assert {k: nachher[k] for k in rest} == rest, "nur die gewählten Buchungen ändern sich"
    summe = sum(s["betrag"] for b in ids for s in api.buchung_lesen(b)["splits"] if s["konto_id"] == ziel)
    neu = api.salden()
    assert neu[ziel]["saldo"] == summe and neu[c["giro"]]["saldo"] == salden[c["giro"]]["saldo"] - summe
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "mehrfach_verschieben", None)
    pruefe_eintraege(a, vorher, nachher)
    rundreise(api, a, vorher, nachher)


@pytest.mark.kern
def test_verschieben_gruppe_import(api):
    """gruppe import:<id>: genau die noch vorhandenen Buchungen des Imports mit Split auf dem Quellkonto."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    (imp,) = api.get("/api/importe", erwartet=200).daten
    gruppe = f"import:{imp['id']}"
    giro = next(k["id"] for k in api.konten() if k["extern_id"] == "kmy:A000001")
    leb = next(k["id"] for k in api.konten() if k["extern_id"] == "kmy:A000002")
    manuell = api.buchung("2024-03-01", [(giro, -100), (leb, 100)])["id"]
    importiert = gruppen_buchungen(api, gruppe)
    assert len(importiert) == 2 and manuell not in importiert
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    vorher = bestand(api)
    r = verschieben(api, giro, spar, gruppe=gruppe).daten
    assert r == {"verschoben": sorted(importiert), "anzahl": 2}
    nachher = bestand(api)
    for b in importiert:
        assert nachher[("buchung", b)] == verschoben_soll(vorher[("buchung", b)], giro, spar)
    assert nachher[("buchung", manuell)] == vorher[("buchung", manuell)]
    # erneut: Auswahl leer (keine Buchung der Gruppe mehr auf giro) → 200, keine Änderung
    ohne_wirkung(api, lambda: _leer(verschieben(api, giro, spar, gruppe=gruppe)))
    # nach dem Löschen einer Buchung des Imports nur die noch vorhandene
    eine = min(importiert)
    api.delete(f"/api/buchungen/{eine}", erwartet=204)
    assert verschieben(api, spar, giro, gruppe=gruppe).daten == {"verschoben": [max(importiert)], "anzahl": 1}


def _leer(r):
    assert r.daten == {"verschoben": [], "anzahl": 0}


@pytest.mark.kern
def test_verschieben_gruppe_sync(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path, daten=SYNC_DATEN)
    _, erw = lade_sync()
    lauf = sync(api, von=VON)
    gruppe = f"sync:{lauf['id']}"
    giro = next(k["id"] for k in api.konten() if k["iban"] == erw["ibans"]["giro"])
    unk = next(k["id"] for k in api.konten() if k["extern_id"] == "kontor:unkategorisiert")
    manuell = api.buchung("2024-03-01", [(giro, -100), (unk, 100)])["id"]
    soll = sorted(b["id"] for b in nach_kennung(api.alle_buchungen(), f"bank:{erw['ibans']['giro']}:").values())
    assert soll and set(soll) == {b for b in gruppen_buchungen(api, gruppe)
                                  if any(s["konto_id"] == giro for s in api.buchung_lesen(b)["splits"])}
    alt = api.konto("Altes Giro", "girokonto")["id"]
    vorher = bestand(api)
    assert verschieben(api, giro, alt, gruppe=gruppe).daten == {"verschoben": soll, "anzahl": len(soll)}
    nachher = bestand(api)
    for b in soll:
        assert nachher[("buchung", b)] == verschoben_soll(vorher[("buchung", b)], giro, alt)
    assert nachher[("buchung", manuell)] == vorher[("buchung", manuell)]
    assert {k: v for k, v in nachher.items() if k[0] != "buchung"} == {k: v for k, v in vorher.items()
                                                                       if k[0] != "buchung"}


@pytest.mark.kern
@pytest.mark.parametrize("fall", ["beide", "keines", "gleich", "liste_leer", "doppelt", "gruppe_leer", "zusatz",
                                  "text_id", "ohne_von"])
def test_verschieben_validierung(api, c, fall):
    g, s = c["giro"], c["karte"]
    body = {"beide": {"von_konto_id": g, "nach_konto_id": s, "buchung_ids": [c["b1"]], "gruppe": "import:1"},
            "keines": {"von_konto_id": g, "nach_konto_id": s},
            "gleich": {"von_konto_id": g, "nach_konto_id": g, "buchung_ids": [c["b1"]]},
            "liste_leer": {"von_konto_id": g, "nach_konto_id": s, "buchung_ids": []},
            "doppelt": {"von_konto_id": g, "nach_konto_id": s, "buchung_ids": [c["b1"], c["b1"]]},
            "gruppe_leer": {"von_konto_id": g, "nach_konto_id": s, "gruppe": ""},
            "zusatz": {"von_konto_id": g, "nach_konto_id": s, "buchung_ids": [c["b1"]], "trocken": True},
            "text_id": {"von_konto_id": str(g), "nach_konto_id": s, "buchung_ids": [c["b1"]]},
            "ohne_von": {"nach_konto_id": s, "buchung_ids": [c["b1"]]}}[fall]

    def aufruf():
        assert fehler(api.post(VERSCHIEBEN, json=body, erwartet=422)) == "validierung"
    ohne_wirkung(api, aufruf)


@pytest.mark.kern
def test_verschieben_pruefreihenfolge(api, c):
    """datenmodell.md 18.2: Quell-, dann Zielkonto, dann Buchungen, dann unmöglich, dann gesperrt."""
    g, karte, leb, offen = c["giro"], c["karte"], c["leb"], c["offen"]
    _abgleichen(api, c["b1"])
    faelle = [
        (dict(von=999999, nach=999998, ids=[999997]), 422, "referenz_unbekannt", {"feld": "von_konto_id"}),
        (dict(von=leb, nach=999998, ids=[999997]), 422, "konto_ungueltig", {"feld": "von_konto_id"}),
        (dict(von=g, nach=999998, ids=[999997]), 422, "referenz_unbekannt", {"feld": "nach_konto_id"}),
        (dict(von=g, nach=offen, ids=[999997]), 422, "konto_ungueltig", {"feld": "nach_konto_id"}),
        (dict(von=g, nach=karte, ids=[999997, c["b1"], 999996]), 422, "referenz_unbekannt",
         {"buchung_ids": [999996, 999997]}),
        (dict(von=g, nach=karte, gruppe="import:999999"), 422, "referenz_unbekannt", None),
        (dict(von=g, nach=karte, gruppe="kein-schluessel"), 422, "referenz_unbekannt", None),
        # b4 hat keinen Split auf giro, b3 schon einen auf Tagesgeld; b1 ist gesperrt, aber erst Schritt 5
        (dict(von=g, nach=c["spar"], ids=[c["b4"], c["b1"], c["b3"]]), 422, "verschieben_unmoeglich",
         {"buchung_ids": sorted([c["b3"], c["b4"]])}),
        (dict(von=g, nach=karte, ids=[c["b2"], c["b1"]]), 409, "buchung_gesperrt", {"buchung_ids": [c["b1"]]}),
    ]
    for f, status, code, det in faelle:
        def aufruf():
            r = verschieben(api, f["von"], f["nach"], ids=f.get("ids"), gruppe=f.get("gruppe"), erwartet=status)
            assert fehler(r) == code, (f, r.text)
            if det is not None:
                d = details(r)
                assert {k: d[k] for k in det} == det, (f, d)
        ohne_wirkung(api, aufruf)


@pytest.mark.kern
def test_verschieben_gruppe_ohne_angelegte_buchung(tmp_path, netz_gesperrt):
    """Ein Lauf ohne Umsätze legt nur Konten an: seine Gruppe hat keine Buchung angelegt → 422 (E-184)."""
    api = mock_api(tmp_path, daten=SYNC_DATEN)
    lauf = sync(api, von="2024-06-30", bis="2024-06-30")
    assert lauf["status"] == "erfolgreich" and not gruppen_buchungen(api, f"sync:{lauf['id']}"), "Testvoraussetzung"
    g = api.konten()[0]["id"]
    z = api.konto("Ziel", "girokonto")["id"]
    ohne_wirkung(api, lambda: _referenz(verschieben(api, g, z, gruppe=f"sync:{lauf['id']}", erwartet=422)))


def _referenz(r):
    assert fehler(r) == "referenz_unbekannt"


@pytest.mark.kern
def test_verschieben_gruppe_unmoeglich(api):
    """Auch bei gruppe: Buchungen mit Split auf dem Zielkonto → verschieben_unmoeglich."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    (imp,) = api.get("/api/importe", erwartet=200).daten
    giro = next(k["id"] for k in api.konten() if k["extern_id"] == "kmy:A000001")
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    b = min(gruppen_buchungen(api, f"import:{imp['id']}"))
    alt = api.buchung_lesen(b)
    andere = [s for s in alt["splits"] if s["konto_id"] != giro]
    teil = andere[0]["betrag"]
    api.put(f"/api/buchungen/{b}/splits", json={"splits": [
        *[{"konto_id": s["konto_id"], "betrag": s["betrag"], "memo": s["memo"]} for s in alt["splits"]
          if s["konto_id"] == giro],
        {"konto_id": andere[0]["konto_id"], "betrag": teil - 1, "memo": ""},
        {"konto_id": spar, "betrag": 1, "memo": ""}]}, erwartet=200)

    def aufruf():
        r = verschieben(api, giro, spar, gruppe=f"import:{imp['id']}", erwartet=422)
        assert (fehler(r), details(r)["buchung_ids"]) == ("verschieben_unmoeglich", [b])
    ohne_wirkung(api, aufruf)


# ================================================================== herkunft (18.3)


@pytest.mark.kern
def test_herkunft(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path, daten=SYNC_DATEN)
    _, erw = lade_sync()
    setze_zeit(api, "2024-05-01T08:00:00Z")
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    (imp,) = api.get("/api/importe", erwartet=200).daten
    giro = next(k["id"] for k in api.konten() if k["extern_id"] == "kmy:A000001")
    leb = next(k["id"] for k in api.konten() if k["extern_id"] == "kmy:A000002")
    api.patch(f"/api/konten/{giro}", json={"iban": erw["ibans"]["giro"]}, erwartet=200)
    setze_zeit(api, "2024-06-30T12:00:00Z")
    lauf = sync(api, von=VON)
    alle = api.alle_buchungen()
    kmy = [b for b in alle if any(e.startswith("kmy:") for e in b["extern_ids"])]
    neu_sync = [b for b in alle if not any(e.startswith("kmy:") for e in b["extern_ids"])
                and any(e.startswith(f"bank:{erw['ibans']['giro']}:") for e in b["extern_ids"])]
    assert len(kmy) == 2 and neu_sync
    z0 = letzte_aenderung_id(api)
    h = herkunft(api, giro)
    assert sorted((x["gruppe"], x["art"], x["anzahl"]) for x in h) == sorted([
        (f"sync:{lauf['id']}", "sync", len(neu_sync)), (f"import:{imp['id']}", "import", 2)])
    zeit = {x["gruppe"]: x["zeitpunkt"] for x in h}
    assert zeit[f"sync:{lauf['id']}"] in (lauf["gestartet_am"], lauf["beendet_am"])
    assert zeit[f"import:{imp['id']}"] == imp["importiert_am"]
    assert [x["zeitpunkt"] for x in h] == sorted(zeit.values(), reverse=True), "nach zeitpunkt absteigend (E-191)"
    assert all(x["beschreibung"].strip() for x in h)
    assert [(x["gruppe"], x["anzahl"]) for x in herkunft(api, leb)] == [(f"import:{imp['id']}", 1)]
    assert aenderungen_seit(api, z0) == [], "reiner Lesezugriff"
    # gelöschte Buchungen zählen nicht
    api.delete(f"/api/buchungen/{neu_sync[0]['id']}", erwartet=204)
    assert {x["gruppe"]: x["anzahl"] for x in herkunft(api, giro)}[f"sync:{lauf['id']}"] == len(neu_sync) - 1
    # nach dem Verschieben der Importbuchungen fehlt die Gruppe beim Quellkonto
    spar = api.konto("Altkonto", "sparkonto")["id"]
    verschieben(api, giro, spar, gruppe=f"import:{imp['id']}")
    assert [x["gruppe"] for x in herkunft(api, giro)] == [f"sync:{lauf['id']}"]
    assert [(x["gruppe"], x["anzahl"]) for x in herkunft(api, spar)] == [(f"import:{imp['id']}", 2)]
    assert herkunft(api, api.konto("Leer", "girokonto")["id"]) == []


def test_herkunft_unbekanntes_konto(api):
    assert fehler(herkunft(api, 999999, erwartet=404)) == "nicht_gefunden"


# ================================================================== Sicherung (protokoll.md 14, sicherung.md)


@pytest.mark.kern
def test_sicherung_unveraendert(api, c, tmp_path):
    """Kein neuer fachlicher Zustand: Objektarten und Prüfsumme wie bisher, Rundreise gleich (E-181)."""
    v = Verlauf(api)
    v.eine(lambda: loeschen(api, [c["b4"], c["dublette"]]))
    v.eine(lambda: verschieben(api, c["giro"], c["karte"], ids=[c["b1"]]))
    a = v.eine(lambda: api.tag("Zwischen"))
    v.bis(a)
    m, _ = oeffne(sicherung(api))
    i = inhalt(api)
    kredite = sorted(api.get("/api/kredite", erwartet=200).daten, key=lambda x: x["id"])
    i["kredit"] = kredite
    assert set(m["anzahl"]) == set(i), "keine neue Objektart"
    assert m["anzahl"] == {o: len(x) for o, x in i.items()}
    assert m["inhalt_sha256"] == inhalt_sha256(i)
    soll, soll_b = lesezustand(api), bestand(api)
    ziel = neue_api(tmp_path / "ziel")
    einspielen(ziel, sicherung(api))
    assert bestand(ziel) == soll_b and lesezustand(ziel) == soll
