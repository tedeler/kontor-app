"""M4: Split-Vorlagen bei der Synchronisation und auf vorhandene Buchungen (vorlagen.md 3–7; K 8; T 9, T 17, T 21).

Erwartungen: Wahrheit des Generators (``mock/m4_vorlagen.erwartung.json``)
und für zufällige Fälle eine unabhängige Nachrechnung (``tests/hilfen/m4.erkenne``).
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from generator.iban import fiktive_iban
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import benachrichtigungen
from tests.hilfen.m3 import UNKATEGORISIERT, aenderungen_seit, konto_id, letzte_aenderung_id
from tests.hilfen.m4 import (M4, MOCK, VORLAGEN_MOCK, bank_buchungen, bestand, erkenne, kategorien_anlegen,
                             konto_nach_iban, lade, mock_api, mock_datei, pruefe_eintraege, sync, umsatz, vorlage,
                             vorlage_body, zeit)

GIRO = fiktive_iban(7701)


@pytest.fixture(scope="module")
def daten():
    return lade(VORLAGEN_MOCK), lade(MOCK / "m4_vorlagen.erwartung.json"), lade(M4 / "vorlagen.json")


def _einrichten(api, stamm, erw):
    giro = api.konto("Girokonto", "girokonto", iban=erw["iban"])["id"]
    kats = kategorien_anlegen(api, stamm["kategorien"])
    ibans = konto_nach_iban(api)
    vs = {v["name"]: api.post("/api/vorlagen", json=vorlage_body(v, kats, ibans), erwartet=201).daten
          for v in stamm["vorlagen"]}
    return giro, kats, vs


def _splits(b):
    return [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]]


def _pruefe(api, umsaetze, soll: dict, giro, kats, vs, nur=None):
    unk = konto_id(api, UNKATEGORISIERT)
    bank = bank_buchungen(api)
    for u in umsaetze:
        if nur is not None and not nur(soll[u["umsatz_id"]]):
            continue
        e, b = soll[u["umsatz_id"]], bank[u["umsatz_id"]]
        assert b["vorschlag"] is None, (u["umsatz_id"], b["vorschlag"])
        if e["ergebnis"] == "gesplittet":
            assert _splits(b) == [(giro, e["betrag"], "")] + [(kats[s["kategorie"]], s["betrag"], s["memo"])
                                                              for s in e["splits"]], u["umsatz_id"]
            assert b["kategorie_id"] is None and b["status"] == "vorlaeufig"   # D-261: Split-Vorlage macht vorläufig
        else:
            assert _splits(b) == [(giro, e["betrag"], ""), (unk, -e["betrag"], "")], (u["umsatz_id"], e)


@pytest.mark.kern
def test_szenario_normal_exakt(tmp_path, daten):
    """Treffer werden centgenau aufgeteilt, 1 Cent mehr oder weniger nicht (T 9); je Abweichung eine Nachricht."""
    d, erw, stamm = daten
    api = mock_api(tmp_path, VORLAGEN_MOCK, erw["stufen"][-1])
    giro, kats, vs = _einrichten(api, stamm, erw)
    lauf = sync(api, von="2024-01-01")
    (k,) = lauf["konten"]
    soll = erw["normal"]
    _pruefe(api, d["bank"]["umsaetze"], soll, giro, kats, vs)
    assert k["buchungen_gesplittet"] == sum(e["ergebnis"] == "gesplittet" for e in soll.values())
    assert k["vorlage_abweichungen"] == sum(e["ergebnis"] == "abweichung" for e in soll.values())
    assert k["buchungen_kategorisiert"] == 0 and k["buchungen_neu"] == len(soll)
    bank = bank_buchungen(api)
    nachrichten = [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"]
    erwartet = []
    for n in erw["benachrichtigungen_normal"]:
        erste = next(u for u in d["bank"]["umsaetze"] if soll[u["umsatz_id"]]["ergebnis"] == "abweichung"
                     and (soll[u["umsatz_id"]]["vorlage"], soll[u["umsatz_id"]]["betrag"]) == (n["vorlage"], n["betrag"]))
        erwartet.append((f"split_abweichung:{vs[n['vorlage']]['id']}:{n['betrag']}",
                         f"/buchungen/{bank[erste['umsatz_id']]['id']}"))
    assert [(n["schluessel"], n["link"]) for n in nachrichten] == erwartet
    assert all(not n["gelesen"] and n["titel"].strip() and n["text"].strip() for n in nachrichten)
    assert api.uebersicht()["summe_gesamt"] == 0


@pytest.mark.kern
def test_beitragsaenderung_anpassen_und_nachtraeglich_aufteilen(tmp_path, daten):
    """K 8 / T 9: Beitragsänderung → keine Aufteilung, eine Nachricht; nach Anpassung wieder korrekt."""
    d, erw, stamm = daten
    st0, st1, st2 = erw["stufen"]
    api = mock_api(tmp_path, VORLAGEN_MOCK, st0, mock_szenario="beitragsaenderung")
    giro, kats, vs = _einrichten(api, stamm, erw)
    soll = erw["beitragsaenderung"]
    sync(api, von="2024-01-01")
    _pruefe(api, d["bank"]["umsaetze"], soll, giro, kats, vs, nur=lambda e: e["stufe"] == 0)
    assert [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"] == []
    zeit(api, st1)
    sync(api)
    _pruefe(api, d["bank"]["umsaetze"], soll, giro, kats, vs, nur=lambda e: e["stufe"] == 1)
    mon = vs[stamm["angepasst"]["vorlage"]]
    abw = [u for u in d["bank"]["umsaetze"] if soll[u["umsatz_id"]]["stufe"] == 1
           and soll[u["umsatz_id"]]["ergebnis"] == "abweichung" and soll[u["umsatz_id"]]["vorlage"] == mon["name"]]
    assert len(abw) == 3
    schl = [n["schluessel"] for n in benachrichtigungen(api) if n["art"] == "split_abweichung"]
    assert schl.count(f"split_abweichung:{mon['id']}:{abw[0]['betrag_beitragsaenderung']}") == 1, \
        "dieselbe Beitragsänderung Monat für Monat: eine Nachricht (keine Flut)"
    # Vorlage anpassen (manuell, K 8)
    teile = [{"kategorie_id": kats[t["kategorie"]], "betrag": t["betrag"], "memo": t["memo"]}
             for t in stamm["angepasst"]["teile"]]
    neu = api.patch(f"/api/vorlagen/{mon['id']}", json={"teile": teile}, erwartet=200).daten
    assert neu["gesamtbetrag"] == abw[0]["betrag_beitragsaenderung"]
    zeit(api, st2)
    sync(api)
    _pruefe(api, d["bank"]["umsaetze"], soll, giro, kats, vs, nur=lambda e: e["stufe"] == 2)
    # nachträglich: die abweichenden Buchungen mit der angepassten Vorlage aufteilen (vorlagen.md 5)
    bank = bank_buchungen(api)
    ids = sorted(bank[u["umsatz_id"]]["id"] for u in abw)
    r = api.post("/api/vorlagen/anwenden", json={"vorlage_ids": [mon["id"]]}, erwartet=200).daten
    assert [a["buchung_id"] for a in r["aenderungen"]] == ids
    for u in abw:
        b = api.buchung_lesen(bank[u["umsatz_id"]]["id"])
        assert _splits(b)[1:] == [(t["kategorie_id"], t["betrag"], t["memo"]) for t in teile]
        assert b["splits"][0]["id"] == bank[u["umsatz_id"]]["splits"][0]["id"], "Bestandskonto-Split bleibt"
    alle = [n["schluessel"] for n in benachrichtigungen(api) if n["art"] == "split_abweichung"]
    assert len(alle) == len(erw["benachrichtigungen_beitragsaenderung"])


def _klein(tmp_path, umsaetze, **felder):
    p = mock_datei(tmp_path / "bank.json", [(GIRO, "Giro", "girokonto")], umsaetze)
    api = mock_api(tmp_path, p, "2024-06-30", **felder)
    giro = api.konto("Giro", "girokonto", iban=GIRO)["id"]
    kats = {n: api.konto(n, "aufwand")["id"] for n in ("A", "B", "C", "Sammel")}
    return api, giro, kats


@pytest.mark.kern
@given(st.lists(st.integers(1, 99_999), min_size=2, max_size=4), st.integers(-2, 2))
def test_keine_toleranz(tmp_path_factory, teile, delta):
    """T 9: exakter Betrag → centgenau aufgeteilt; jede Abweichung (auch 1 Cent) → nicht aufgeteilt, Nachricht."""
    gesamt = -sum(teile)
    tmp = tmp_path_factory.mktemp("tol")
    api, giro, kats = _klein(tmp, [umsatz("S1", GIRO, "2024-06-03", gesamt + delta, "Fiktiva AG", "Beitrag")])
    kl = [kats["A"], kats["B"], kats["C"], kats["A"]]
    v = vorlage(api, "V", "Fiktiva AG", [(kl[i], t, f"Teil {i}") for i, t in enumerate(teile)])
    lauf = sync(api, von="2024-06-01")
    b = bank_buchungen(api)["S1"]
    assert sum(s["betrag"] for s in b["splits"]) == 0
    nachr = [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"]
    (k,) = lauf["konten"]
    if delta == 0:
        assert _splits(b) == [(giro, gesamt, "")] + [(kl[i], t, f"Teil {i}") for i, t in enumerate(teile)]
        assert nachr == [] and (k["buchungen_gesplittet"], k["vorlage_abweichungen"]) == (1, 0)
    else:
        unk = konto_id(api, UNKATEGORISIERT)
        assert _splits(b) == [(giro, gesamt + delta, ""), (unk, -(gesamt + delta), "")]
        assert [n["schluessel"] for n in nachr] == [f"split_abweichung:{v['id']}:{gesamt + delta}"]
        assert nachr[0]["link"] == f"/buchungen/{b['id']}"
        assert (k["buchungen_gesplittet"], k["vorlage_abweichungen"]) == (0, 1)


@pytest.mark.kern
def test_vorlage_vor_regel_und_abweichung_ohne_regel(tmp_path):
    """E-074: Vorlagen stehen vor Regeln; bei Abweichung greift auch keine Regel; ohne Kandidat gilt die Regel."""
    us = [umsatz("S1", GIRO, "2024-06-03", -300, "Fiktiva AG", "Beitrag"),
          umsatz("S2", GIRO, "2024-06-04", -301, "Fiktiva AG", "Beitrag"),
          umsatz("S3", GIRO, "2024-06-05", -300, "Fiktiva AG", "Erstattung")]
    api, giro, kats = _klein(tmp_path, us)
    vorlage(api, "V", "Fiktiva AG", [(kats["A"], 100), (kats["B"], 200)], zweck="beitrag")
    api.post("/api/regeln", json={"name": "R", "kategorie_id": kats["C"], "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "fiktiva"}]}, erwartet=201)
    sync(api, von="2024-06-01")
    x = bank_buchungen(api)
    assert len(x["S1"]["splits"]) == 3 and x["S1"]["vorschlag"] is None
    assert x["S2"]["vorschlag"] is None and x["S2"]["kategorie_id"] is None
    assert x["S3"]["vorschlag"]["quelle"] == "regel" and x["S3"]["kategorie_id"] == kats["C"]


def test_abweichung_ohne_lernmodell_und_standardkategorie(tmp_path):
    us = [umsatz("S1", GIRO, "2024-06-03", -301, "Fiktiva AG", "Beitrag")]
    api, giro, kats = _klein(tmp_path, us, lernmodell_automatisch=True)
    emp = api.empfaenger("Fiktiva AG")
    for _ in range(3):
        api.buchung("2024-01-02", [(giro, -300), (kats["Sammel"], 300)], empfaenger_id=emp["id"],
                    verwendungszweck="Beitrag")
    # bis M31 zusätzlich mit Standardkategorie; die gibt es ab M32 nicht mehr (E-307)
    vorlage(api, "V", "Fiktiva AG", [(kats["A"], 100), (kats["B"], 200)])
    sync(api, von="2024-06-01")
    b = bank_buchungen(api)["S1"]
    assert b["vorschlag"] is None and b["kategorie_id"] is None


@pytest.mark.kern
def test_mehrere_vorlagen_erste_mit_passendem_betrag(tmp_path):
    """vorlagen.md 3: unter den passenden aktiven Vorlagen gewinnt die erste mit exaktem Betrag; sonst Abweichung
    mit der ersten Kandidatin; inaktive zählen nicht."""
    us = [umsatz("S1", GIRO, "2024-06-03", -500, "Fiktiva AG", "x"),
          umsatz("S2", GIRO, "2024-06-04", -300, "Fiktiva AG", "x"),
          umsatz("S3", GIRO, "2024-06-05", -999, "Fiktiva AG", "x"),
          umsatz("S4", GIRO, "2024-06-06", -700, "Fiktiva AG", "x")]
    api, giro, kats = _klein(tmp_path, us)
    a = vorlage(api, "A", "Fiktiva AG", [(kats["A"], 100), (kats["B"], 200)], prioritaet=50)
    vorlage(api, "B", "Fiktiva AG", [(kats["A"], 200), (kats["C"], 300)], prioritaet=60)
    vorlage(api, "C", "Fiktiva AG", [(kats["A"], 300), (kats["C"], 400)], prioritaet=10, aktiv=False)
    vs = api.get("/api/vorlagen", erwartet=200).daten
    sync(api, von="2024-06-01")
    x = bank_buchungen(api)
    for uid, r in (("S1", -500), ("S2", -300), ("S3", -999), ("S4", -700)):
        art, v = erkenne(vs, "Fiktiva AG", "x", {giro}, r)
        if art == "treffer":
            assert [s["konto_id"] for s in x[uid]["splits"][1:]] == [t["kategorie_id"] for t in v["teile"]]
        else:
            assert len(x[uid]["splits"]) == 2
    assert [s["betrag"] for s in x["S1"]["splits"]] == [-500, 200, 300], "B, obwohl A die höhere Priorität hat"
    assert [s["betrag"] for s in x["S2"]["splits"]] == [-300, 100, 200]
    nachr = sorted(n["schluessel"] for n in benachrichtigungen(api) if n["art"] == "split_abweichung")
    assert nachr == sorted([f"split_abweichung:{a['id']}:-999", f"split_abweichung:{a['id']}:-700"]), \
        "Abweichung mit der ersten aktiven Kandidatin, inaktive Vorlage C bleibt unbeachtet"


def test_bedingung_konto_und_muster(tmp_path):
    spar = fiktive_iban(7702)
    p = mock_datei(tmp_path / "bank.json", [(GIRO, "Giro", "girokonto"), (spar, "Spar", "sparkonto")],
                   [umsatz("S1", GIRO, "2024-06-03", -300, "Stadtwerke Muster", "Abschlag 06"),
                    umsatz("S2", spar, "2024-06-03", -300, "Stadtwerke Muster", "Abschlag 06"),
                    umsatz("S3", GIRO, "2024-06-04", -300, "Stadtwerke Muster", "Nachzahlung")])
    api = mock_api(tmp_path, p, "2024-06-30")
    giro = api.konto("Giro", "girokonto", iban=GIRO)["id"]
    a, b = api.konto("Strom", "aufwand")["id"], api.konto("Gas", "aufwand")["id"]
    api.post("/api/vorlagen", json={"name": "SW", "bedingungen": [
        {"feld": "empfaenger", "operator": "beginnt_mit", "wert": "STADTWERKE"},
        {"feld": "verwendungszweck", "operator": "beginnt_mit", "wert": "abschlag"},
        {"feld": "konto_id", "operator": "gleich", "wert": giro}],
        "teile": [{"kategorie_id": a, "betrag": 100}, {"kategorie_id": b, "betrag": 200}]}, erwartet=201)
    sync(api, von="2024-06-01")
    x = bank_buchungen(api)
    assert len(x["S1"]["splits"]) == 3 and len(x["S2"]["splits"]) == 2 and len(x["S3"]["splits"]) == 2
    assert [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"] == []


def test_gelesen_dann_neue_nachricht(tmp_path):
    """Entprellung nur solange ungelesen (vorlagen.md 6)."""
    us = [umsatz("S1", GIRO, "2024-06-03", -301, "Fiktiva AG"), umsatz("S2", GIRO, "2024-06-20", -301, "Fiktiva AG"),
          umsatz("S3", GIRO, "2024-06-21", -299, "Fiktiva AG")]
    api, giro, kats = _klein(tmp_path, us)
    vorlage(api, "V", "Fiktiva AG", [(kats["A"], 100), (kats["B"], 200)])
    zeit(api, "2024-06-10")
    sync(api, von="2024-06-01")
    (n,) = [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"]
    api.post(f"/api/benachrichtigungen/{n['id']}/gelesen", erwartet=200)
    zeit(api, "2024-06-30")
    sync(api)
    neu = [x for x in benachrichtigungen(api, gelesen=False) if x["art"] == "split_abweichung"]
    assert sorted(x["schluessel"] for x in neu) == sorted([n["schluessel"], n["schluessel"][:-4] + "-299"])


def test_zusammengefuehrte_umsaetze_ohne_vorlage(tmp_path):
    us = [umsatz("S1", GIRO, "2024-06-03", -301, "Fiktiva AG")]
    api, giro, kats = _klein(tmp_path, us)
    e = api.empfaenger("Fiktiva AG")
    alt = api.buchung("2024-06-03", [(giro, -301), (kats["Sammel"], 301)], empfaenger_id=e["id"])
    vorlage(api, "V", "Fiktiva AG", [(kats["A"], 100), (kats["B"], 200)])
    lauf = sync(api, von="2024-06-01")
    assert lauf["konten"][0]["buchungen_zusammengefuehrt"] == 1 and lauf["konten"][0]["vorlage_abweichungen"] == 0
    assert api.buchung_lesen(alt["id"])["splits"] == alt["splits"]
    assert [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"] == []


@pytest.mark.kern
def test_sync_mit_aufteilung_rueckgaengig_und_manuell_bearbeitbar(tmp_path):
    us = [umsatz("S1", GIRO, "2024-06-03", -300, "Fiktiva AG"), umsatz("S2", GIRO, "2024-06-04", -301, "Fiktiva AG")]
    api, giro, kats = _klein(tmp_path, us)
    vorlage(api, "V", "Fiktiva AG", [(kats["A"], 100), (kats["B"], 200)])
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    lauf = sync(api, von="2024-06-01")
    (a,) = aenderungen_seit(api, a0)
    assert (a["aktion"], a["gruppe"]) == ("sync_konto", f"sync:{lauf['id']}")
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    b = bank_buchungen(api)["S1"]
    # manuelles Zusammenführen der Teile (T 9: jederzeit möglich, Invariante 1)
    r = api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": [
        {"konto_id": giro, "betrag": -300}, {"konto_id": kats["Sammel"], "betrag": 300}]}, erwartet=200).daten
    assert r["kategorie_id"] == kats["Sammel"]
    api.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [a["id"] + 1]}, erwartet=200)
    assert bestand(api) == nachher
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"}, erwartet=200)
    assert bestand(api) == vorher


# ------------------------------------------------------------- anwenden
@pytest.fixture
def anw(api):
    giro, spar = api.konto("Giro")["id"], api.konto("Spar", "sparkonto")["id"]
    ek = api.konto("Unkat", "eigenkapital")["id"]
    a, b, c = (api.konto(n, "aufwand")["id"] for n in ("A", "B", "C"))
    e = api.empfaenger("Fiktiva AG")["id"]
    v = vorlage(api, "V", "Fiktiva AG", [(a, 100, "a"), (b, 200)])

    def neu(splits, **kw):
        return api.buchung("2024-05-01", splits, empfaenger_id=e, **kw)
    return {"giro": giro, "spar": spar, "ek": ek, "a": a, "b": b, "c": c, "v": v, "neu": neu}


@pytest.mark.kern
def test_anwenden_auswahl_trocken_protokoll(api, anw):
    x = anw["neu"]([(anw["giro"], -300), (anw["ek"], 300)])
    kat = anw["neu"]([(anw["giro"], -300), (anw["c"], 300)])
    abw = anw["neu"]([(anw["giro"], -299), (anw["ek"], 299)])
    zwei = anw["neu"]([(anw["giro"], -150), (anw["spar"], -150), (anw["ek"], 300)])
    gesp = anw["neu"]([(anw["giro"], -300), (anw["ek"], 300)])
    api.patch(f"/api/buchungen/{gesp['id']}", json={"status": "abgeglichen"}, erwartet=200)
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    soll = {"geprueft": 2, "anzahl": 1, "trocken": True,
            "aenderungen": [{"buchung_id": x["id"], "vorlage_id": anw["v"]["id"]}],
            "abweichungen": [{"buchung_id": abw["id"], "vorlage_id": anw["v"]["id"], "betrag": -299,
                              "gesamtbetrag": -300}]}
    assert api.post("/api/vorlagen/anwenden", json={"trocken": True}, erwartet=200).daten == soll
    assert bestand(api) == vorher and aenderungen_seit(api, a0) == []
    r = api.post("/api/vorlagen/anwenden", json={}, erwartet=200).daten
    assert r == {**soll, "trocken": False}
    neu = api.buchung_lesen(x["id"])
    assert _splits(neu) == [(anw["giro"], -300, ""), (anw["a"], 100, "a"), (anw["b"], 200, "")]
    assert neu["splits"][0]["id"] == x["splits"][0]["id"]
    assert api.buchung_lesen(kat["id"]) == kat and api.buchung_lesen(zwei["id"]) == zwei
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("vorlage", "vorlagen_anwenden", None)
    pruefe_eintraege(a, vorher, bestand(api))
    assert [n for n in benachrichtigungen(api) if n["art"] == "split_abweichung"] == [], \
        "anwenden meldet Abweichungen nur in der Antwort"
    r2 = api.post("/api/vorlagen/anwenden", json={"nur_unkategorisiert": False}, erwartet=200).daten
    assert [c["buchung_id"] for c in r2["aenderungen"]] == [kat["id"]]
    api.post(f"/api/aenderungen/{a['id'] + 1}/rueckgaengig", erwartet=200)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher


def test_anwenden_offener_vorschlag_entfaellt(api, anw):
    x = anw["neu"]([(anw["giro"], -300), (anw["ek"], 300)], verwendungszweck="beitrag")
    api.post("/api/regeln", json={"name": "R", "kategorie_id": anw["c"], "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "beitrag"}]}, erwartet=201)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    assert api.buchung_lesen(x["id"])["vorschlag"]["quelle"] == "regel"
    r = api.post("/api/vorlagen/anwenden", json={"buchung_ids": [x["id"]], "nur_unkategorisiert": False},
                 erwartet=200).daten
    assert r["anzahl"] == 1 and api.buchung_lesen(x["id"])["vorschlag"] is None


@pytest.mark.parametrize("koerper,code,feld", [
    ({"buchung_ids": [999]}, "referenz_unbekannt", "buchung_ids"),
    ({"vorlage_ids": [999, 998]}, "referenz_unbekannt", "vorlage_ids"),
    ({"buchung_ids": [1, 1]}, "validierung", None), ({"vorlage_ids": []}, "validierung", None),
    ({"trocken": 1}, "validierung", None), ({"regel_ids": [1]}, "validierung", None)])
def test_anwenden_fehler(api, anw, koerper, code, feld):
    r = api.post("/api/vorlagen/anwenden", json=koerper, erwartet=422)
    assert fehlercode(r) == code
    if feld:
        assert r.json()["fehler"]["details"][feld] == sorted(koerper[feld])


def test_buch_ohne_vorlagen_unveraendert(tmp_path):
    """E-029: ohne Vorlagen gibt es keine Aufteilung und keine Abweichung; Zählungen 0."""
    api, giro, kats = _klein(tmp_path, [umsatz("S1", GIRO, "2024-06-03", -300, "Fiktiva AG")])
    (k,) = sync(api, von="2024-06-01")["konten"]
    assert (k["buchungen_gesplittet"], k["vorlage_abweichungen"], k["buchungen_neu"]) == (0, 0, 1)
