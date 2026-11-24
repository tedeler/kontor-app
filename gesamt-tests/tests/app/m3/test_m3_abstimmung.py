"""M3: Kontenabstimmung – Auszugssaldo gegen berechneten Saldo, Markieren, Schutz (buchhaltungspflege.md 5, T 13).

Erwartung: Kontoauszüge aus der bekannten Wahrheit des Generators (``auszuege``, ``auszuege_falsch``) bzw.
im Test unabhängig berechnete Salden.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.kmybau import KBuch, KBuchung, KKonto, KSplit, gzip_bytes
from tests.hilfen.m2 import konto_nach_iban, sync
from tests.hilfen.m3 import erfassen, lade_m3, m3_api, zustand_m3

from generator.iban import fiktive_iban

VON = "2024-01-01"


def abstimmen(api, konto_id, stichtag, saldo, erwartet=200, **kw):
    return api.post("/api/abstimmungen", json={"konto_id": konto_id, "stichtag": stichtag, "saldo": saldo, **kw},
                    erwartet=erwartet)


@pytest.mark.kern
def test_monatsauszuege(tmp_path, netz_gesperrt):
    daten, erw = lade_m3()
    api = m3_api(tmp_path)
    sync(api, von=VON)
    konten = konto_nach_iban(api)
    for a in erw["auszuege"]:
        kid = konten[a["iban"]]["id"]
        r = abstimmen(api, kid, a["stichtag"], a["saldo"]).daten
        assert (r["konto_id"], r["stichtag"], r["saldo"], r["berechneter_saldo"], r["differenz"]) == (
            kid, a["stichtag"], a["saldo"], a["saldo"], 0)
        assert (r["stimmt"], r["abgestimmt"], r["anzahl_splits"]) == (True, True, a["neue_splits"])
        ab = r["abstimmung"]
        assert (ab["konto_id"], ab["stichtag"], ab["saldo"]) == (kid, a["stichtag"], a["saldo"])
        assert api.get(f"/api/abstimmungen/{ab['id']}", erwartet=200).daten == ab
        for b in api.alle_buchungen(konto_id=kid):
            for s in b["splits"]:
                if s["konto_id"] == kid:
                    assert (s["abstimmung_id"] is not None) == (b["datum"] <= a["stichtag"])
                    if b["datum"] <= a["stichtag"]:
                        assert b["abgestimmt"] is True
    alle = api.get("/api/abstimmungen", erwartet=200).daten
    assert [x["id"] for x in alle] == sorted(x["id"] for x in alle) and len(alle) == len(erw["auszuege"])
    giro = konten[erw["ibans"]["giro"]]["id"]
    assert api.get("/api/abstimmungen", params={"konto_id": giro}, erwartet=200).daten == [
        x for x in alle if x["konto_id"] == giro]
    assert api.alle_buchungen(abgestimmt=False) == []
    assert len(api.alle_buchungen(abgestimmt=True)) == len(api.alle_buchungen())


@pytest.mark.kern
def test_differenz_markiert_nichts(tmp_path, netz_gesperrt):
    daten, erw = lade_m3()
    api = m3_api(tmp_path)
    sync(api, von=VON)
    konten = konto_nach_iban(api)
    vorher = zustand_m3(api)
    for f in erw["auszuege_falsch"]:
        r = abstimmen(api, konten[f["iban"]]["id"], f["stichtag"], f["saldo"]).daten
        assert (r["differenz"], r["stimmt"], r["abgestimmt"], r["abstimmung"]) == (f["differenz"], False, False, None)
        assert r["berechneter_saldo"] == f["saldo"] - f["differenz"] and r["anzahl_splits"] > 0
    a = erw["auszuege"][0]
    t = abstimmen(api, konten[a["iban"]]["id"], a["stichtag"], a["saldo"], trocken=True).daten
    assert (t["stimmt"], t["abgestimmt"], t["abstimmung"], t["anzahl_splits"]) == (True, False, None, a["neue_splits"])
    assert zustand_m3(api) == vorher


@pytest.mark.kern
def test_stichtag_einschliesslich_und_nur_eigenes_konto(api):
    g = api.konto("Giro")
    s = api.konto("Spar", "sparkonto")
    unter = api.konto("Unterkonto", "girokonto", eltern_id=g["id"])
    lm = api.konto("Lebensmittel", "aufwand")
    b1 = api.buchung("2024-03-31", [(g["id"], -500), (lm["id"], 500)])
    b2 = api.buchung("2024-04-01", [(g["id"], -700), (lm["id"], 700)])
    u = erfassen(api, art="umbuchung", datum="2024-03-15", konto_id=g["id"], gegenkonto_id=s["id"], betrag=1000)
    api.buchung("2024-03-10", [(unter["id"], 99), (lm["id"], -99)])
    r = abstimmen(api, g["id"], "2024-03-31", -1500).daten
    assert (r["berechneter_saldo"], r["anzahl_splits"], r["abgestimmt"]) == (-1500, 2, True), \
        "Stichtag einschließlich, Unterkonten zählen nicht"
    assert api.buchung_lesen(b1["id"])["abgestimmt"] is True and api.buchung_lesen(b2["id"])["abgestimmt"] is False
    um = api.buchung_lesen(u["id"])
    assert um["abgestimmt"] is True
    assert [sp["abstimmung_id"] is not None for sp in um["splits"]] == [True, False], "nur der Split des Kontos"
    r2 = abstimmen(api, s["id"], "2024-03-31", 1000).daten
    assert r2["anzahl_splits"] == 1
    assert all(sp["abstimmung_id"] is not None for sp in api.buchung_lesen(u["id"])["splits"])
    nachtrag = api.buchung("2024-03-20", [(g["id"], -1), (lm["id"], 1)])
    r3 = abstimmen(api, g["id"], "2024-04-30", -2201).daten
    assert r3["anzahl_splits"] == 2, "nachträglich gebuchte und neue Splits"
    assert api.buchung_lesen(nachtrag["id"])["splits"][0]["abstimmung_id"] == r3["abstimmung"]["id"]


@pytest.mark.kern
def test_fehler(api):
    g = api.konto("Giro")
    lm = api.konto("Lebensmittel", "aufwand")
    vorher = zustand_m3(api)
    assert fehlercode(abstimmen(api, 999999, "2024-01-31", 0, 422)) == "referenz_unbekannt"
    assert fehlercode(abstimmen(api, lm["id"], "2024-01-31", 0, 422)) == "konto_ungueltig"
    for body in ({"konto_id": g["id"], "stichtag": "2024-01-31", "saldo": 1.0},
                 {"konto_id": g["id"], "stichtag": "31.01.2024", "saldo": 0}, {"konto_id": g["id"], "saldo": 0},
                 {"konto_id": g["id"], "stichtag": "2024-01-31", "saldo": 0, "x": 1}):
        assert fehlercode(api.post("/api/abstimmungen", json=body, erwartet=422)) == "validierung"
    assert zustand_m3(api) == vorher
    assert fehlercode(api.get("/api/abstimmungen/999999", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.delete("/api/abstimmungen/999999", erwartet=404)) == "nicht_gefunden"
    leer = api.konto("Leer", "sparkonto")
    a = abstimmen(api, leer["id"], "2024-01-31", 0).daten
    assert a["abgestimmt"] is True and a["anzahl_splits"] == 0
    assert fehlercode(api.delete(f"/api/konten/{leer['id']}", erwartet=409)) == "konto_in_verwendung"


@pytest.mark.kern
def test_aufheben_nur_letzte(api):
    g = api.konto("Giro")
    lm = api.konto("Lebensmittel", "aufwand")
    b1 = api.buchung("2024-01-10", [(g["id"], -100), (lm["id"], 100)])
    b2 = api.buchung("2024-02-10", [(g["id"], -200), (lm["id"], 200)])
    a1 = abstimmen(api, g["id"], "2024-01-31", -100).daten["abstimmung"]
    vor_a2 = zustand_m3(api)
    a2 = abstimmen(api, g["id"], "2024-02-29", -300).daten["abstimmung"]
    assert fehlercode(api.delete(f"/api/abstimmungen/{a1['id']}", erwartet=409)) == "abstimmung_nicht_letzte"
    api.delete(f"/api/abstimmungen/{a2['id']}", erwartet=204)
    assert zustand_m3(api) == vor_a2
    assert api.buchung_lesen(b2["id"])["abgestimmt"] is False and api.buchung_lesen(b1["id"])["abgestimmt"] is True
    api.delete(f"/api/abstimmungen/{a1['id']}", erwartet=204)
    assert api.get("/api/abstimmungen", erwartet=200).daten == []
    api.patch(f"/api/buchungen/{b1['id']}", json={"datum": "2024-01-11"}, erwartet=200)


@pytest.fixture
def gesperrt(api):
    """Eine abgestimmte Buchung mit offenem Vorschlag, Tag und Dublettenverdacht."""
    iban = fiktive_iban(7201)
    g = api.konto("Giro", iban=iban)
    lm = api.konto("Lebensmittel", "aufwand")
    hh = api.konto("Haushalt", "aufwand")
    offen = api.konto("Offen", "eigenkapital")
    e = api.empfaenger("Drogerie")
    t = api.tag("Steuer")
    b = api.buchung("2024-01-10", [(g["id"], -500), (offen["id"], 500)], empfaenger_id=e["id"], status="importiert")
    frei = api.buchung("2024-01-11", [(g["id"], -700), (lm["id"], 700)])
    api.post("/api/regeln", json={"name": "Drogerie", "kategorie_id": hh["id"], "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "drogerie"}]}, erwartet=201)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    abstimmen(api, g["id"], "2024-01-10", -500)
    kb = KBuch()
    kb.konten = [KKonto("A000001", "Giro", 1, "AStd::Asset", iban=iban), KKonto("A000002", "Haushalt", 13,
                                                                                   "AStd::Expense")]
    kb.empfaenger = [("P000001", "Drogerie")]
    kb.buchungen = [KBuchung("T000000000000000001", "2024-01-12", [KSplit("A000001", -500, empfaenger="P000001"),
                                                                   KSplit("A000002", 500)])]
    api.post("/api/import/kmymoney", files={"datei": ("d.kmy", gzip_bytes(kb), "x")}, erwartet=200)
    b = api.buchung_lesen(b["id"])
    assert b["abgestimmt"] and b["vorschlag"] and b["status"] == "vorlaeufig"   # D-261: Vorschlag macht vorläufig
    return {"b": b, "frei": frei, "lm": lm, "t": t, "g": g, "neu": api.get("/api/dubletten", erwartet=200).daten}


@pytest.mark.kern
def test_sperre_abgestimmter_buchungen(api, gesperrt):
    b, frei, lm, t = gesperrt["b"], gesperrt["frei"], gesperrt["lm"], gesperrt["t"]
    bid = b["id"]
    for feld, wert in (("datum", "2024-01-09"), ("verwendungszweck", "neu"), ("empfaenger_id", None)):
        assert fehlercode(api.patch(f"/api/buchungen/{bid}", json={feld: wert}, erwartet=409)) == "buchung_gesperrt"
    assert fehlercode(api.delete(f"/api/buchungen/{bid}", erwartet=409)) == "buchung_gesperrt"
    assert fehlercode(api.put(f"/api/buchungen/{bid}/splits", json={"splits": [
        {"konto_id": gesperrt["g"]["id"], "betrag": -500}, {"konto_id": lm["id"], "betrag": 500}]},
        erwartet=409)) == "buchung_gesperrt"
    assert fehlercode(api.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": lm["id"]},
                              erwartet=409)) == "buchung_gesperrt"
    r = api.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [frei["id"], bid],
                                                           "kategorie_id": lm["id"]}, erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt" and r.json()["fehler"]["details"]["buchung_ids"] == [bid]
    assert fehlercode(api.post(f"/api/buchungen/{bid}/vorschlag", json={"aktion": "ablehnen"},
                               erwartet=409)) == "buchung_gesperrt"
    r = api.post("/api/buchungen/mehrfach/vorschlag", json={"buchung_ids": [bid], "aktion": "ablehnen"}, erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt" and r.json()["fehler"]["details"]["buchung_ids"] == [bid]
    (v,) = gesperrt["neu"]
    assert bid in v["kandidat_ids"]
    assert api.buchung_lesen(bid) == b, "nichts wurde geändert"
    # erlaubt: Tags, Status, Vorschlag annehmen, Dublette mit gesperrter Buchung als behaltene
    api.patch(f"/api/buchungen/{bid}", json={"tag_ids": [t["id"]]}, erwartet=200)
    api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [bid], "entfernen": [t["id"]]}, erwartet=200)
    api.post(f"/api/buchungen/{bid}/vorschlag", json={"aktion": "annehmen"}, erwartet=200)
    api.patch(f"/api/buchungen/{bid}", json={"status": "bestaetigt"}, erwartet=200)
    api.post(f"/api/dubletten/{v['id']}/aufloesen", json={"entscheidung": "zusammenfuehren", "behalten_id": bid},
             erwartet=200)
    nach = api.buchung_lesen(bid)
    assert nach["splits"] == b["splits"] and nach["status"] == "bestaetigt" and len(nach["extern_ids"]) == 1


@pytest.mark.kern
def test_gesperrte_dublette_nicht_entfernbar(api):
    iban = fiktive_iban(7202)
    g = api.konto("Giro", iban=iban)
    lm = api.konto("Lebensmittel", "aufwand")
    alt = api.buchung("2024-01-10", [(g["id"], -500), (lm["id"], 500)])
    kb = KBuch()
    kb.konten = [KKonto("A000001", "Giro", 1, "AStd::Asset", iban=iban), KKonto("A000002", "Lebensmittel", 13,
                                                                                   "AStd::Expense")]
    kb.buchungen = [KBuchung("T000000000000000001", "2024-01-11", [KSplit("A000001", -500), KSplit("A000002", 500)])]
    api.post("/api/import/kmymoney", files={"datei": ("d.kmy", gzip_bytes(kb), "x")}, erwartet=200)
    (v,) = api.get("/api/dubletten", erwartet=200).daten
    abstimmen(api, g["id"], "2024-01-31", -1000)
    assert fehlercode(api.post(f"/api/dubletten/{v['id']}/aufloesen", json={"entscheidung": "zusammenfuehren",
                                                                            "behalten_id": alt["id"]},
                               erwartet=409)) == "buchung_gesperrt"
    assert api.get("/api/dubletten", erwartet=200).daten == [v]


@pytest.mark.kern
def test_regeln_und_umbuchung_uebergehen_gesperrte(api):
    g = api.konto("Giro")
    s = api.konto("Spar", "sparkonto")
    hh = api.konto("Haushalt", "aufwand")
    x = erfassen(api, art="ausgabe", datum="2024-01-01", konto_id=g["id"], betrag=500, verwendungszweck="drogerie")
    y = erfassen(api, art="einnahme", datum="2024-01-01", konto_id=s["id"], betrag=500)
    abstimmen(api, g["id"], "2024-01-31", -500)
    api.post("/api/regeln", json={"name": "D", "kategorie_id": hh["id"], "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "drogerie"}]}, erwartet=201)
    r = api.post("/api/regeln/anwenden", json={"nur_unkategorisiert": False}, erwartet=200).daten
    assert r["anzahl"] == 0 and x["id"] not in [a["buchung_id"] for a in r["aenderungen"]]
    assert fehlercode(api.post("/api/umbuchungen/zusammenfuehren", json={"buchung_ids": [x["id"], y["id"]]},
                               erwartet=409)) == "buchung_gesperrt"


def test_filter_abgestimmt(api):
    g = api.konto("Giro")
    lm = api.konto("Lebensmittel", "aufwand")
    b1 = api.buchung("2024-01-10", [(g["id"], -100), (lm["id"], 100)])
    b2 = api.buchung("2024-02-10", [(g["id"], -200), (lm["id"], 200)])
    abstimmen(api, g["id"], "2024-01-31", -100)
    assert [b["id"] for b in api.alle_buchungen(abgestimmt=True)] == [b1["id"]]
    assert [b["id"] for b in api.alle_buchungen(abgestimmt=False)] == [b2["id"]]
    assert [b["id"] for b in api.alle_buchungen(abgestimmt=True, konto_id=lm["id"])] == [b1["id"]]
    assert fehlercode(api.get("/api/buchungen", params={"abgestimmt": "vielleicht"}, erwartet=422)) == "validierung"


def test_abstimmung_im_protokoll_und_rueckgaengig(api):
    from tests.hilfen.m3 import aenderungen_seit, bestand, letzte_aenderung_id, pruefe_rueckgaengig_rundreise

    g = api.konto("Giro")
    lm = api.konto("Lebensmittel", "aufwand")
    api.buchung("2024-01-10", [(g["id"], -100), (lm["id"], 100)])
    vorher = bestand(api)
    vor = letzte_aenderung_id(api)
    abstimmen(api, g["id"], "2024-01-31", -100)
    (a,) = aenderungen_seit(api, vor)
    assert {e["objekt"] for e in a["eintraege"]} == {"abstimmung", "buchung"}
    pruefe_rueckgaengig_rundreise(api, a, vorher, bestand(api))
