"""M30: Regeln mit Ausdruck und Tags (kategorisierung.md 8.1–8.8; E-268, E-272) – REST, kern.

Anlegen, Ändern, Fehler, Übersetzung der bisherigen Form, Auswertung (erste passende Regel mit Kategorie, Tags
aller passenden Regeln), ``POST /api/regeln/anwenden`` mit ``tags``, Synchronisation, Reihenfolge, Test, Erklären
und Anwenden einer einzelnen Regel.
"""

from __future__ import annotations

import pytest

from tests.hilfen import m30
from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m30 import STICHTAG, als_id, alle_treffer, anwenden, einzeln_anwenden, falte, regel, regel_test, \
    regeln, tags_von, wirkungen

pytestmark = pytest.mark.kern
REWE = '"REWE" in empfänger'
ALT = [{"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"}]


@pytest.fixture
def b(api):
    return m30.bestand(api)


def _patch(api, rid, erwartet=200, **body):
    r = api.patch(f"/api/regeln/{rid}", json=body, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def _lesen(api, rid):
    return api.get(f"/api/regeln/{rid}", erwartet=200).daten


# ------------------------------------------------------------------ 8.1 Aufbau
def test_anlegen_mit_ausdruck(b):
    api = b.api
    r = regel(api, "  Supermarkt  ", kategorie_id=b.k["Supermarkt"], ausdruck="empf=='REWE' && bet>20")
    assert r["name"] == "Supermarkt" and r["aktiv"] is True and r["prioritaet"] == 100
    assert r["kategorie_id"] == b.k["Supermarkt"]
    assert r["ausdruck"] == 'empfänger == "REWE" and betrag > 20', "kanonischer Text"
    assert r["ausdruck_form"] == "ausdruck" and r["tag_ids"] == []
    (bed,) = r["bedingungen"]
    assert bed["feld"] == "ausdruck" and bed["operator"] == "ausdruck" and isinstance(bed["wert"], dict)
    assert "automatisch" not in r and "empfaenger_id" not in r, "nur bei automatisch angelegten Regeln"
    assert _lesen(api, r["id"]) == r and regeln(api) == [r]
    r2 = regel(api, "Zweite", kategorie_id=b.k["Wohnen"], ausdruck="betrag >= 500", aktiv=False)
    assert (r2["prioritaet"], r2["aktiv"]) == (110, False), "Vorgabe: größte vorhandene + 10"
    r3 = regel(api, "Dritte", kategorie_id=b.k["Wohnen"], ausdruck="betrag >= 500", prioritaet=5)
    assert [x["id"] for x in regeln(api)] == [r3["id"], r["id"], r2["id"]]


def test_anlegen_bisherige_form_wird_uebersetzt(b):
    r = regel(b.api, "Alt", kategorie_id=b.k["Supermarkt"], bedingungen=ALT)
    assert r["ausdruck"] == REWE, "Empfänger enthält REWE"
    assert r["ausdruck_form"] == "bedingungen" and r["bedingungen"] == ALT and r["tag_ids"] == []
    assert _lesen(b.api, r["id"]) == r


def test_regel_nur_mit_tags(b):
    api, t = b.api, b.t
    ids = sorted(t.values())
    r = regel(api, "Nur Tags", ausdruck=REWE, tag_ids=list(reversed(ids)))
    assert r["kategorie_id"] is None and r["tag_ids"] == ids, "tag_ids aufsteigend"
    r2 = regel(api, "Null", kategorie_id=None, bedingungen=ALT, tag_ids=[t["Urlaub"]])
    assert r2["kategorie_id"] is None and r2["tag_ids"] == [t["Urlaub"]] and r2["ausdruck_form"] == "bedingungen"
    r3 = regel(api, "Beides", kategorie_id=b.k["Wohnen"], ausdruck=REWE, tag_ids=[t["Steuer"]])
    assert r3["kategorie_id"] == b.k["Wohnen"] and r3["tag_ids"] == [t["Steuer"]]


def test_zwanzig_tags(b):
    ids = [b.api.tag(f"T{i:02d}")["id"] for i in range(21)]
    r = regel(b.api, "Viele", ausdruck=REWE, tag_ids=ids[:20])
    assert r["tag_ids"] == sorted(ids[:20])
    f = regel(b.api, "Zu viele", 422, ausdruck=REWE, tag_ids=ids)
    assert fehlercode(f) == "validierung" and m30.ort_enthaelt(f, "body", "tag_ids")


# ------------------------------------------------------------------ 8.2 Fehler
def test_fehler_beim_anlegen(b):
    api, k, t = b.api, b.k, b.t
    for felder in ({"ausdruck": REWE}, {"ausdruck": REWE, "kategorie_id": None},
                   {"ausdruck": REWE, "tag_ids": []}, {"bedingungen": ALT, "kategorie_id": None, "tag_ids": []}):
        f = regel(api, "Ohne Aktion", 422, **felder)
        assert fehlercode(f) == "validierung", felder
        assert m30.ort_enthaelt(f, "body", "kategorie_id"), f"Ort body/kategorie_id: {f.text}"
    for felder in ({"kategorie_id": k["Wohnen"], "ausdruck": REWE, "bedingungen": ALT},
                   {"kategorie_id": k["Wohnen"]}, {"tag_ids": [t["Urlaub"]]}):
        assert fehlercode(regel(api, "Form", 422, **felder)) == "validierung", felder
    f = regel(api, "Doppelt", 422, ausdruck=REWE, tag_ids=[t["Urlaub"], t["Urlaub"]])
    assert fehlercode(f) == "validierung" and m30.ort_enthaelt(f, "body", "tag_ids")
    for kid in (k["Giro"], k["Offen"], 987654):
        assert fehlercode(regel(api, "Kategorie", 422, kategorie_id=kid, ausdruck=REWE)) == "kategorie_ungueltig"
    f = regel(api, "Tag", 422, ausdruck=REWE, tag_ids=[t["Urlaub"], 987654, 987653])
    assert fehlercode(f) == "referenz_unbekannt"
    assert sorted(f.json()["fehler"]["details"]["tag_ids"]) == [987653, 987654]
    for ausdruck in ("", "x" * 4001):
        assert fehlercode(regel(api, "Länge", 422, kategorie_id=k["Wohnen"], ausdruck=ausdruck)) in (
            "validierung", "ausdruck_ungueltig"), "1–4000 Zeichen"
    assert regeln(api) == []


@pytest.mark.parametrize("ausdruck,code", [("betrag >", "syntax"), ("datum == heute", "nur_im_filter"),
                                           ("jahr == 2026", "nur_im_filter"), ("rewe", "feld_unbekannt"),
                                           ('kategorie == "Gibt:Es:Nicht"', "referenz_unbekannt"),
                                           ("empfänger", "kein_wahrheitswert"),
                                           ('empfänger.search(r"(a)\\1")', "regex_nicht_unterstuetzt")])
def test_ungueltiger_ausdruck(b, ausdruck, code):
    """Ausdrücke von Regeln gelten im Kontext ``regel``; ``details.fehler`` hat die Form des Prüfens."""
    m30.ausdruck_ungueltig(regel(b.api, "Kaputt", 422, kategorie_id=b.k["Wohnen"], ausdruck=ausdruck), code)
    r = regel(b.api, "Heil", kategorie_id=b.k["Wohnen"], ausdruck="betrag > 1")
    m30.ausdruck_ungueltig(_patch(b.api, r["id"], 422, ausdruck=ausdruck), code)
    assert _lesen(b.api, r["id"]) == r


# ------------------------------------------------------------------ Ändern
def test_aendern(b):
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Regel", kategorie_id=k["Wohnen"], ausdruck="betrag > 1")
    r2 = _patch(api, r["id"], ausdruck="bet>=2 || vwz=='x'")
    assert r2 == {**r, "ausdruck": 'betrag >= 2 or verwendungszweck == "x"', "bedingungen": r2["bedingungen"]}
    assert r2["bedingungen"] != r["bedingungen"] and r2["bedingungen"][0]["feld"] == "ausdruck"
    r3 = _patch(api, r["id"], bedingungen=ALT)
    assert (r3["ausdruck_form"], r3["bedingungen"], r3["ausdruck"]) == ("bedingungen", ALT, REWE)
    r4 = _patch(api, r["id"], ausdruck=REWE, tag_ids=[t["Steuer"], t["Urlaub"]], name=" Neu ")
    assert (r4["ausdruck_form"], r4["ausdruck"], r4["name"]) == ("ausdruck", REWE, "Neu")
    assert r4["tag_ids"] == sorted(t.values()) and r4["kategorie_id"] == k["Wohnen"]
    r5 = _patch(api, r["id"], kategorie_id=None)
    assert r5["kategorie_id"] is None and r5["tag_ids"] == r4["tag_ids"], "nur Tags bleibt gültig"
    r6 = _patch(api, r["id"], tag_ids=[t["Urlaub"]])
    assert r6["tag_ids"] == [t["Urlaub"]]
    assert _lesen(api, r["id"]) == r6
    # Fehler ändern nichts
    assert fehlercode(_patch(api, r["id"], 422, tag_ids=[])) == "regel_ohne_aktion"
    assert fehlercode(_patch(api, r["id"], 422, ausdruck=REWE, bedingungen=ALT)) == "validierung"
    assert fehlercode(_patch(api, r["id"], 422, tag_ids=[987654])) == "referenz_unbekannt"
    assert fehlercode(_patch(api, r["id"], 422, tag_ids=[t["Urlaub"], t["Urlaub"]])) == "validierung"
    assert fehlercode(_patch(api, r["id"], 422, kategorie_id=k["Giro"])) == "kategorie_ungueltig"
    assert _lesen(api, r["id"]) == r6
    s = regel(api, "Nur Kategorie", kategorie_id=k["Wohnen"], bedingungen=ALT)
    assert fehlercode(_patch(api, s["id"], 422, kategorie_id=None)) == "regel_ohne_aktion"
    assert _lesen(api, s["id"]) == s


def test_umbenennen_zeigt_den_neuen_namen(b):
    """2.3: gespeichert wird der Bezug, nicht der Name."""
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Verweise", kategorie_id=k["Gehalt"],
              ausdruck='kategorie == "Lebensmittel:Supermarkt" or konto == "Spar" or "Urlaub" in tags')
    api.patch(f"/api/konten/{k['Lebensmittel']}", json={"name": "Essen"}, erwartet=200)
    api.patch(f"/api/konten/{k['Spar']}", json={"name": "Tagesgeld"}, erwartet=200)
    api.patch(f"/api/tags/{t['Urlaub']}", json={"name": "Ferien"}, erwartet=200)
    neu = _lesen(api, r["id"])
    assert neu["ausdruck"] == 'kategorie == "Essen:Supermarkt" or konto == "Tagesgeld" or "Ferien" in tags'
    assert {x: neu[x] for x in ("id", "kategorie_id", "tag_ids", "prioritaet")} == \
        {x: r[x] for x in ("id", "kategorie_id", "tag_ids", "prioritaet")}
    # die Regel trifft weiter dieselben Buchungen
    ids = {x["buchung_id"] for x in alle_treffer(api, regel_id=r["id"])}
    assert b.namen(ids) == b.soll(lambda f: f.kategorie == "Lebensmittel:Supermarkt" or "Spar" in f.konten
                                  or "Urlaub" in f.tags)


# ------------------------------------------------------------------ Gleichwertigkeit der bisherigen Form
def _alt(f, bed, giro_spar):
    feld, op, wert = bed["feld"], bed["operator"], bed["wert"]
    if feld in ("empfaenger", "verwendungszweck"):
        text = f.empf if feld == "empfaenger" else f.zweck
        if feld == "empfaenger" and not f.empf:
            return False
        a, w = falte(text), falte(wert)
        return {"enthaelt": w in a, "gleich": a == w, "beginnt_mit": a.startswith(w)}[op]
    if feld == "betrag":
        return {"gleich": f.cent == wert, "mindestens": f.cent >= wert, "hoechstens": f.cent <= wert}[op]
    return giro_spar[wert] in f.konten


ALTE_BEDINGUNGEN = [
    [{"feld": "empfaenger", "operator": "enthaelt", "wert": "markt"}],
    [{"feld": "empfaenger", "operator": "gleich", "wert": "edeka"}],
    [{"feld": "empfaenger", "operator": "beginnt_mit", "wert": "MUELLER"}],
    [{"feld": "verwendungszweck", "operator": "enthaelt", "wert": "überweisung"}],
    [{"feld": "verwendungszweck", "operator": "gleich", "wert": "brot"}],
    [{"feld": "verwendungszweck", "operator": "beginnt_mit", "wert": "Miete"}],
    [{"feld": "betrag", "operator": "gleich", "wert": -2550}],
    [{"feld": "betrag", "operator": "gleich", "wert": 1500}],
    [{"feld": "betrag", "operator": "hoechstens", "wert": -2000}],      # Ausgabe ab 20 €
    [{"feld": "betrag", "operator": "mindestens", "wert": -2000}],      # Ausgabe bis 20 € oder Eingang
    [{"feld": "betrag", "operator": "mindestens", "wert": 1500}],       # Eingang ab 15 €
    [{"feld": "betrag", "operator": "hoechstens", "wert": 1500}],
    [{"feld": "betrag", "operator": "mindestens", "wert": -4000}, {"feld": "betrag", "operator": "hoechstens",
                                                                  "wert": -1250}],
    [{"feld": "betrag", "operator": "hoechstens", "wert": 0}],
    [{"feld": "konto_id", "operator": "gleich", "wert": "Spar"}],
    [{"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"}, {"feld": "betrag", "operator": "mindestens",
                                                                     "wert": 1}],
]


@pytest.mark.parametrize("nr", range(len(ALTE_BEDINGUNGEN)))
def test_bisherige_form_gleichwertig(b, nr):
    """Definition 13: dieselbe Buchungsmenge mit der bisherigen Form und mit dem übersetzten Ausdruck."""
    api = b.api
    bed = [{**x, "wert": b.k[x["wert"]]} if x["feld"] == "konto_id" else x for x in ALTE_BEDINGUNGEN[nr]]
    nach_id = {v: n for n, v in b.k.items()}
    alt = regel(api, "Alt", kategorie_id=b.k["Wohnen"], bedingungen=bed)
    assert alt["ausdruck_form"] == "bedingungen" and alt["bedingungen"] == bed
    neu = regel(api, "Neu", kategorie_id=b.k["Wohnen"], ausdruck=alt["ausdruck"])
    assert neu["ausdruck_form"] == "ausdruck" and neu["ausdruck"] == alt["ausdruck"], "Übersetzung ist kanonisch"
    # Betrag einer Umbuchung im Ausdruck: offen (E-272 Punkt 4) – gegen die eigene Rechnung ohne sie geprüft
    offen = {"sparen"} if any(x["feld"] == "betrag" for x in bed) else set()
    soll = b.soll(lambda f: all(_alt(f, x, nach_id) for x in bed)) - offen
    ist = {r["ausdruck_form"]: b.namen(x["buchung_id"] for x in alle_treffer(api, regel_id=r["id"]))
           for r in (alt, neu)}
    for form, menge in ist.items():
        assert menge - offen == soll, f"{form}: {alt['ausdruck']}"
    assert ist["bedingungen"] == ist["ausdruck"], f"gleichwertig: {alt['ausdruck']}"


# ------------------------------------------------------------------ 8.3 Auswertung, POST /api/regeln/anwenden
@pytest.fixture
def drei(b):
    """Regel nur mit Tag (vorn), Regel mit Kategorie, Regel mit Kategorie und Tag."""
    api, k, t = b.api, b.k, b.t
    r_tag = regel(api, "Tag", ausdruck=REWE, tag_ids=[t["Steuer"]], prioritaet=10)
    r_a = regel(api, "A", ausdruck=REWE, kategorie_id=k["Wohnen"], prioritaet=20)
    r_b = regel(api, "B", ausdruck='betrag < 100 and richtung in ["ausgabe", "einnahme"]',
                kategorie_id=k["Lebensmittel"], tag_ids=[t["Urlaub"]], prioritaet=30)
    return r_tag, r_a, r_b


def _soll_tags(b, ohne=()):
    s, u = b.t["Steuer"], b.t["Urlaub"]
    soll = {"rewe1": [s], "rewe2": [s, u], "erstattung": [s, u], "mueller": [u], "edeka": [u], "schalttag": [u]}
    return [{"buchung_id": b[n].id, "tag_ids": sorted(v)} for n, v in sorted(soll.items(), key=lambda x: b[x[0]].id)
            if n not in ohne]


def test_anwenden_kategorie_und_tags(b, drei):
    api, k = b.api, b.k
    r_tag, r_a, r_b = drei
    vorher = {f.name: tags_von(api, f.id) for f in b.faelle}
    a0 = letzte_aenderung_id(api)
    soll_kat = sorted([{"buchung_id": b["erstattung"].id, "regel_id": r_a["id"], "kategorie_id": k["Wohnen"]},
                       {"buchung_id": b["mueller"].id, "regel_id": r_b["id"], "kategorie_id": k["Lebensmittel"]}],
                      key=lambda x: x["buchung_id"])
    trocken = anwenden(api, trocken=True)
    assert trocken["trocken"] is True and trocken["aenderungen"] == soll_kat and trocken["anzahl"] == 2
    assert trocken["tags"] == _soll_tags(b), "trocken nennt, was vergeben würde"
    assert {f.name: tags_von(api, f.id) for f in b.faelle} == vorher and letzte_aenderung_id(api) == a0
    echt = anwenden(api)
    assert echt["aenderungen"] == soll_kat and echt["tags"] == _soll_tags(b)
    # erste passende Regel mit Kategorie: die Regel nur mit Tag verdeckt nichts
    e = api.buchung_lesen(b["erstattung"].id)
    assert e["kategorie_id"] == k["Wohnen"]
    assert e["vorschlag"]["regel_id"] == r_a["id"] and e["vorschlag"]["quelle"] == "regel"
    assert api.buchung_lesen(b["mueller"].id)["vorschlag"]["regel_id"] == r_b["id"]
    # Tags aller passenden Regeln, vorhandene bleiben, auch an bereits kategorisierten Buchungen
    for eintrag in _soll_tags(b):
        name = next(f.name for f in b.faelle if f.id == eintrag["buchung_id"])
        assert tags_von(api, eintrag["buchung_id"]) == vorher[name] | set(eintrag["tag_ids"]), name
    for name in ("alt", "gehalt", "sparen", "miete"):
        assert tags_von(api, b[name].id) == vorher[name], name
    assert api.buchung_lesen(b["rewe1"].id)["vorschlag"] is None, "Tags sind keine Vorschläge"
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"]) == ("regeln", "regeln_anwenden")
    # zweiter Lauf: nichts mehr zu vergeben – das Feld fehlt, keine Änderung
    nochmal = anwenden(api)
    assert "tags" not in nochmal and nochmal["anzahl"] == 0
    assert len(aenderungen_seit(api, a0)) == 1


def test_anwenden_gesperrte_bleiben_unberuehrt(b, drei):
    api = b.api
    api.patch(f"/api/buchungen/{b['rewe2'].id}", json={"status": "abgeglichen"}, erwartet=200)
    vorher = api.buchung_lesen(b["rewe2"].id)
    echt = anwenden(api)
    assert echt["tags"] == _soll_tags(b, ohne=("rewe2",))
    assert api.buchung_lesen(b["rewe2"].id) == vorher


def test_anwenden_nur_tags_mit_buchung_ids_und_splitbuchung(b):
    api, k, t = b.api, b.k, b.t
    split = api.buchung("2026-11-13", [(k["Giro"], -5000), (k["Wohnen"], 3000), (k["Lebensmittel"], 2000)],
                        empfaenger_id=b.e["EDEKA"])["id"]
    regel(api, "Edeka", ausdruck='"EDEKA" in empfänger', tag_ids=[t["Steuer"]])
    a0 = letzte_aenderung_id(api)
    erg = anwenden(api, buchung_ids=[split, b["edeka"].id, b["rewe1"].id], nur_unkategorisiert=True)
    assert erg["aenderungen"] == [] and erg["anzahl"] == 0
    assert erg["tags"] == [{"buchung_id": i, "tag_ids": [t["Steuer"]]} for i in sorted([split, b["edeka"].id])]
    assert tags_von(api, split) == {t["Steuer"]}, "auch Splitbuchungen"
    assert tags_von(api, b["alt"].id) == {t["Steuer"], t["Urlaub"]} and tags_von(api, b["rewe1"].id) == {t["Urlaub"]}
    (a,) = aenderungen_seit(api, a0)
    assert a["aktion"] == "regeln_anwenden", "auch wenn nur Tags vergeben werden"


def test_inaktive_regel_wirkt_nicht(b):
    api, t = b.api, b.t
    regel(api, "Aus", ausdruck=REWE, tag_ids=[t["Steuer"]], kategorie_id=b.k["Wohnen"], aktiv=False)
    erg = anwenden(api)
    assert erg["aenderungen"] == [] and "tags" not in erg


def test_synchronisation_vergibt_tags(tmp_path, netz_gesperrt):
    """8.3: Tags an jeder neu angelegten Buchung, gleich welche Stufe die Kategorie bestimmt hat; eine Regel ohne
    Kategorie verdeckt die Kategorie späterer Regeln nicht."""
    from tests.hilfen import sync_orakel as orakel
    from tests.hilfen.m2 import lade_sync, mock_api, nach_kennung, regeln_anlegen, sync

    daten, erw = lade_sync()
    api = mock_api(tmp_path)
    ids = regeln_anlegen(api)
    aus, ein = api.tag("Ausgabe")["id"], api.tag("Eingang")["id"]
    regel(api, "Tag Ausgabe", ausdruck='richtung == "ausgabe"', tag_ids=[aus], prioritaet=0)
    regel(api, "Tag Eingang", ausdruck='richtung == "einnahme"', tag_ids=[ein], prioritaet=1000000,
          kategorie_id=ids["kategorien"]["Sonstiges"])
    sync(api, von="2024-01-01")
    bank = nach_kennung(api.alle_buchungen())
    geprueft = 0
    for u in daten["bank"]["umsaetze"]:
        soll = erw["regel_ergebnis"][u["umsatz_id"]]
        if u["vormerkung"] or soll is None or u["umsatz_id"] in erw["stornos"]:
            continue
        buchung = bank[orakel.kennung(u)]
        assert buchung["kategorie_id"] == ids["kategorien"][soll["kategorie"]], "Kategorie wie ohne Tag-Regeln"
        assert buchung["vorschlag"]["regel_id"] == ids["regeln"][soll["regel"]]["id"]
        assert {x["id"] for x in buchung["tags"]} == ({aus} if u["betrag"] < 0 else {ein}), u
        geprueft += 1
    assert geprueft > 20
    netz_gesperrt.pruefe()


# ------------------------------------------------------------------ 8.5 Reihenfolge
def test_reihenfolge(b):
    api, k = b.api, b.k
    r = [regel(api, n, kategorie_id=k["Wohnen"], ausdruck="betrag > 1", prioritaet=p)["id"]
         for n, p in (("a", 7), ("b", 7), ("c", 500), ("d", 0))]
    assert [x["id"] for x in regeln(api)] == [r[3], r[0], r[1], r[2]]
    neu = [r[2], r[0], r[3], r[1]]
    a0 = letzte_aenderung_id(api)
    liste = api.post("/api/regeln/reihenfolge", json={"regel_ids": neu}, erwartet=200).daten
    assert [(x["id"], x["prioritaet"]) for x in liste] == list(zip(neu, (10, 20, 30, 40)))
    assert regeln(api) == liste
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "regeln_reihenfolge", None)
    assert {(e["objekt"], e["art"]) for e in a["eintraege"]} == {("regel", "geaendert")}
    # dieselbe Reihenfolge noch einmal: keine Wirkung, keine Änderung
    assert api.post("/api/regeln/reihenfolge", json={"regel_ids": neu}, erwartet=200).daten == liste
    assert len(aenderungen_seit(api, a0)) == 1
    # Rückgängig stellt die alten Prioritäten her
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert [(x["id"], x["prioritaet"]) for x in regeln(api)] == [(r[3], 0), (r[0], 7), (r[1], 7), (r[2], 500)]


def test_reihenfolge_fehler(b):
    api, k = b.api, b.k
    r = [regel(api, n, kategorie_id=k["Wohnen"], ausdruck="betrag > 1")["id"] for n in "abc"]
    vorher = regeln(api)

    def fehler(ids):
        f = api.post("/api/regeln/reihenfolge", json={"regel_ids": ids}, erwartet=422)
        assert fehlercode(f) == "validierung"
        return f.json()["fehler"]["details"]

    d = fehler([r[0], r[1]])
    assert list(d["fehlend"]) == [r[2]] and list(d["unbekannt"]) == []
    d = fehler([r[2], r[1], r[0], 987654])
    assert list(d["unbekannt"]) == [987654] and list(d["fehlend"]) == []
    d = fehler([r[0], 987654])
    assert sorted(d["fehlend"]) == sorted(r[1:]) and list(d["unbekannt"]) == [987654]
    fehler([r[0], r[1], r[2], r[2]])
    for body in ({}, {"regel_ids": "alle"}, {"regel_ids": r, "x": 1}):
        assert fehlercode(api.post("/api/regeln/reihenfolge", json=body, erwartet=422)) == "validierung"
    assert regeln(api) == vorher


# ------------------------------------------------------------------ 8.6 Test
def _kat(b):
    """Namen und Pfade → ID (für Verweise offener Form, E-272 Punkt 7)."""
    return {**b.k, **{pfad: b.k[n] for n, pfad in m30.PFAD.items()}}


def test_test_wirkungen_und_zahlen(b):
    api, k, t = b.api, b.k, b.t
    a0 = letzte_aenderung_id(api)
    d = regel_test(api, ausdruck=REWE, kategorie_id=k["Supermarkt"], tag_ids=[t["Steuer"]])
    assert d["testmenge_anzahl"] == 10 and d["anzahl"] == 3 and d["gesamt"] == 3
    assert (d["seite"], d["pro_seite"]) == (1, 100)
    assert d["gesperrt_anzahl"] == 0 and d["tags_anzahl"] == 3
    assert {w: n for w, n in d["zaehlung"].items() if n} == {"neu": 1, "abweichend": 1, "bereits_so": 1}
    nach_id = {x["buchung_id"]: x for x in d["treffer"]}
    assert b.namen(nach_id) == {"rewe1", "rewe2", "erstattung"}
    assert {b.namen([i]).pop(): x["wirkung"] for i, x in nach_id.items()} == {
        "rewe1": "bereits_so", "rewe2": "abweichend", "erstattung": "neu"}
    r2 = nach_id[b["rewe2"].id]
    assert r2["datum"] == "2026-11-14" and r2["verwendungszweck"] == "Getränke"
    assert k["Giro"] in r2["konto_ids"]
    assert als_id(r2["kategorie_vorher"], _kat(b)) == k["Lebensmittel"]
    assert als_id(r2["kategorie_nachher"], _kat(b)) == k["Supermarkt"]
    neu = nach_id[b["erstattung"].id]
    assert als_id(neu.get("kategorie_vorher"), _kat(b)) in (None, k["Offen"])
    assert als_id(neu["kategorie_nachher"], _kat(b)) == k["Supermarkt"]
    for x in d["treffer"]:
        assert [als_id(y, t) for y in x["tags_neu"]] == [t["Steuer"]]
        assert x.get("verdeckt_von") is None and x.get("grund") is None
        assert isinstance(x["markierungen"], list)
    assert d["nicht_erfasst"]["anzahl"] == 2
    assert b.namen(d["nicht_erfasst"]["buchung_ids"]) == {"alt", "edeka"}
    assert letzte_aenderung_id(api) == a0 and regeln(api) == [], "Lesezugriff"


def test_test_vorgabe_testmenge_und_konto(b):
    api, k = b.api, b.k
    mueller = '"Müller" in empfänger'
    d = regel_test(api, ausdruck=mueller, kategorie_id=k["Wohnen"])
    assert d["testmenge_anzahl"] == 10 and b.namen(x["buchung_id"] for x in d["treffer"]) == {"mueller", "schalttag"}
    # Vorgabe der Testmenge: datum in -12m (zum Stichtag 16.11.2026: ohne die Buchung von 2024)
    d = api.post("/api/regeln/test", json={"ausdruck": mueller, "kategorie_id": k["Wohnen"], "stichtag": STICHTAG},
                 erwartet=200).daten
    assert d["testmenge_anzahl"] == 9 and b.namen(x["buchung_id"] for x in d["treffer"]) == {"mueller"}
    d = regel_test(api, ausdruck=mueller, kategorie_id=k["Wohnen"], testmenge="datum in 2024", stichtag=STICHTAG)
    assert d["testmenge_anzahl"] == 1 and b.namen(x["buchung_id"] for x in d["treffer"]) == {"schalttag"}
    d = regel_test(api, ausdruck="betrag >= 0 or betrag < 0", kategorie_id=k["Wohnen"], konto_id=k["Spar"])
    assert d["testmenge_anzahl"] == 1 and b.namen(x["buchung_id"] for x in d["treffer"]) == {"sparen"}
    d = regel_test(api, ausdruck=mueller, kategorie_id=k["Wohnen"], konto_id=k["Giro"],
                   testmenge='status == "importiert"')
    assert d["testmenge_anzahl"] == 3 and b.namen(x["buchung_id"] for x in d["treffer"]) == {"mueller"}


def test_test_verdeckt(b):
    api, k = b.api, b.k
    frueh = regel(api, "Früher", kategorie_id=k["Wohnen"], ausdruck="betrag < 20", prioritaet=10)
    ohne_kat = regel(api, "Ohne Kategorie", ausdruck="betrag < 20", tag_ids=[b.t["Steuer"]], prioritaet=5)
    w = wirkungen(api, b, ausdruck=REWE, kategorie_id=k["Supermarkt"])
    assert w == {"rewe1": "bereits_so", "rewe2": "abweichend", "erstattung": "verdeckt"}
    (x,) = [y for y in alle_treffer(api, ausdruck=REWE, kategorie_id=k["Supermarkt"])
            if y["buchung_id"] == b["erstattung"].id]
    assert dict(x["verdeckt_von"]) == {"id": frueh["id"], "name": "Früher"}, "Regeln ohne Kategorie verdecken nichts"
    # gespeicherte Regel vor der früheren: nicht verdeckt; dahinter: verdeckt
    vorn = regel(api, "Vorn", kategorie_id=k["Supermarkt"], ausdruck=REWE, prioritaet=1)
    hinten = regel(api, "Hinten", kategorie_id=k["Supermarkt"], ausdruck=REWE, prioritaet=900)
    assert wirkungen(api, b, regel_id=vorn["id"])["erstattung"] == "neu"
    assert wirkungen(api, b, regel_id=hinten["id"])["erstattung"] == "verdeckt"
    # ungespeicherter Stand, der die Regel vorn ersetzt, steht an deren Stelle
    assert wirkungen(api, b, regel_id=vorn["id"], ausdruck='"rewe" in empfänger and betrag > 1') == {
        "rewe1": "bereits_so", "rewe2": "abweichend", "erstattung": "neu"}
    # inaktive Regeln verdecken nicht
    api.patch(f"/api/regeln/{frueh['id']}", json={"aktiv": False}, erwartet=200)
    api.delete(f"/api/regeln/{vorn['id']}", erwartet=204)
    assert wirkungen(api, b, regel_id=hinten["id"])["erstattung"] == "neu"
    assert ohne_kat["kategorie_id"] is None


def test_test_uebersprungen_und_ohne_kategorie(b):
    api, k, t = b.api, b.k, b.t
    split = api.buchung("2026-11-13", [(k["Giro"], -5000), (k["Wohnen"], 3000), (k["Lebensmittel"], 2000)],
                        empfaenger_id=b.e["EDEKA"])["id"]
    d = regel_test(api, ausdruck='"Arbeitgeber" in empfänger', kategorie_id=k["Gehalt"], tag_ids=[t["Steuer"]])
    (x,) = d["treffer"]
    assert (x["buchung_id"], x["wirkung"], x["grund"]) == (b["gehalt"].id, "uebersprungen", "gesperrt")
    assert x["tags_neu"] == [] and d["gesperrt_anzahl"] == 1 and d["tags_anzahl"] == 0 and d["anzahl"] == 1
    edeka = '"EDEKA" in empfänger'
    d = regel_test(api, ausdruck=edeka, kategorie_id=k["Wohnen"])
    nach_id = {y["buchung_id"]: y for y in d["treffer"]}
    assert (nach_id[split]["wirkung"], nach_id[split]["grund"]) == ("uebersprungen", "splitbuchung")
    assert nach_id[b["edeka"].id]["wirkung"] == "abweichend"
    # ohne Kategorie ist jeder nicht gesperrte Treffer „treffer“, auch Splitbuchungen
    d = regel_test(api, ausdruck=edeka, kategorie_id=None, tag_ids=[t["Steuer"]])
    assert {y["buchung_id"]: y["wirkung"] for y in d["treffer"]} == {split: "treffer", b["edeka"].id: "treffer",
                                                                     b["alt"].id: "treffer"}
    neu = {y["buchung_id"]: [als_id(z, t) for z in y["tags_neu"]] for y in d["treffer"]}
    assert neu == {split: [t["Steuer"]], b["edeka"].id: [t["Steuer"]], b["alt"].id: []}, "nur fehlende Tags"
    assert d["tags_anzahl"] == 2
    d = regel_test(api, ausdruck='"Arbeitgeber" in empfänger', kategorie_id=None, tag_ids=[t["Steuer"]])
    assert d["treffer"][0]["wirkung"] == "uebersprungen" and d["treffer"][0]["tags_neu"] == []


def test_test_gespeicherte_regel_und_ueberschreiben(b):
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Gespeichert", kategorie_id=k["Supermarkt"], ausdruck=REWE, tag_ids=[t["Steuer"]])
    erwartet = {"rewe1": "bereits_so", "rewe2": "abweichend", "erstattung": "neu"}
    assert wirkungen(api, b, regel_id=r["id"]) == erwartet
    d = regel_test(api, regel_id=r["id"])
    assert d["tags_anzahl"] == 3, "Tags der Regel gelten, wenn tag_ids fehlt"
    assert regel_test(api, regel_id=r["id"], tag_ids=[])["tags_anzahl"] == 0
    assert set(wirkungen(api, b, regel_id=r["id"], kategorie_id=None).values()) == {"treffer"}
    assert wirkungen(api, b, regel_id=r["id"], kategorie_id=k["Lebensmittel"]) == {
        "rewe1": "abweichend", "rewe2": "bereits_so", "erstattung": "neu"}
    assert wirkungen(api, b, regel_id=r["id"], ausdruck='"EDEKA" in empfänger') == {"alt": "bereits_so",
                                                                                   "edeka": "bereits_so"}


def test_test_wirkung_und_seiten(b):
    api, k = b.api, b.k
    koerper = {"ausdruck": REWE, "kategorie_id": k["Supermarkt"]}
    d = regel_test(api, wirkung="neu", **koerper)
    assert [x["buchung_id"] for x in d["treffer"]] == [b["erstattung"].id]
    assert regel_test(api, wirkung="verdeckt", **koerper)["treffer"] == []
    seiten = [regel_test(api, pro_seite=2, seite=s, **koerper) for s in (1, 2, 3)]
    assert [len(s["treffer"]) for s in seiten] == [2, 1, 0]
    assert all(s["gesamt"] == 3 and s["pro_seite"] == 2 for s in seiten) and seiten[1]["seite"] == 2
    ids = [x["buchung_id"] for s in seiten for x in s["treffer"]]
    assert sorted(ids) == b.ids("rewe1", "rewe2", "erstattung")


def test_test_fehler(b):
    api, k = b.api, b.k

    def f(erwartet=422, **body):
        return api.post("/api/regeln/test", json=body, erwartet=erwartet)

    assert fehlercode(f(kategorie_id=k["Wohnen"])) == "validierung", "weder ausdruck noch regel_id"
    assert fehlercode(f(ausdruck=REWE, zusatz=1)) == "validierung"
    assert fehlercode(f(ausdruck=REWE, wirkung="egal")) == "validierung"
    m30.ausdruck_ungueltig(f(ausdruck="betrag >", kategorie_id=k["Wohnen"]), "syntax")
    m30.ausdruck_ungueltig(f(ausdruck="datum == heute", kategorie_id=k["Wohnen"]), "nur_im_filter")
    m30.ausdruck_ungueltig(f(ausdruck=REWE, kategorie_id=k["Wohnen"], testmenge="datum in 5d"),
                           "dauer_ohne_vorzeichen")
    assert fehlercode(f(ausdruck=REWE, kategorie_id=k["Giro"])) == "kategorie_ungueltig"
    assert fehlercode(f(ausdruck=REWE, tag_ids=[987654])) == "referenz_unbekannt"
    assert fehlercode(f(ausdruck=REWE, kategorie_id=k["Wohnen"], konto_id=k["Wohnen"])) == "konto_ungueltig"
    assert fehlercode(f(404, regel_id=987654)) == "nicht_gefunden"
    # die Testmenge ist ein Filter: Datumsangaben sind dort erlaubt
    f(200, ausdruck=REWE, kategorie_id=k["Wohnen"], testmenge="datum in dieses_jahr", stichtag=STICHTAG)


# ------------------------------------------------------------------ 8.7 Erklären
def _erklaeren(api, erwartet=200, **body):
    r = api.post("/api/regeln/erklaeren", json=body, erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def _wahr(wert) -> bool:
    assert wert in (True, False, "wahr", "falsch"), wert
    return wert in (True, "wahr")


def _knoten(k):
    assert isinstance(k["text"], str) and k["art"] and k["ergebnis"] in ("wahr", "falsch", "nicht_ausgewertet")
    for kind in k.get("kinder", []):
        _knoten(kind)


def test_erklaeren(b):
    api, bid = b.api, b["rewe1"].id
    a0 = letzte_aenderung_id(api)
    d = _erklaeren(api, ausdruck='"REWE" in empfänger and betrag > 100', buchung_id=bid)
    assert d["buchung_id"] == bid and _wahr(d["ergebnis"]) is False
    _knoten(d["baum"])
    assert d["baum"]["ergebnis"] == "falsch"
    links, rechts = d["baum"]["kinder"]
    assert (links["ergebnis"], rechts["ergebnis"]) == ("wahr", "falsch")
    assert "wert" in rechts and "wert" in links, "Vergleiche tragen den tatsächlichen Wert"
    assert "REWE" in str(links["wert"])
    d = _erklaeren(api, ausdruck='"REWE" in empfänger and betrag > 20', buchung_id=bid)
    assert _wahr(d["ergebnis"]) and [x["ergebnis"] for x in d["baum"]["kinder"]] == ["wahr", "wahr"]
    d = _erklaeren(api, ausdruck='"EDEKA" in empfänger and betrag > 20', buchung_id=bid)
    assert not _wahr(d["ergebnis"]) and d["baum"]["kinder"][0]["ergebnis"] == "falsch"
    assert d["baum"]["kinder"][1]["ergebnis"] in ("wahr", "nicht_ausgewertet")
    d = _erklaeren(api, ausdruck='betrag > 20 or "EDEKA" in empfänger', buchung_id=bid)
    assert _wahr(d["ergebnis"]) and d["baum"]["kinder"][0]["ergebnis"] == "wahr"
    assert d["baum"]["kinder"][1]["ergebnis"] in ("falsch", "nicht_ausgewertet")
    d = _erklaeren(api, ausdruck='not "EDEKA" in empfänger', buchung_id=bid)
    assert _wahr(d["ergebnis"]) and d["baum"]["ergebnis"] == "wahr"
    r = regel(api, "Gespeichert", kategorie_id=b.k["Wohnen"], bedingungen=ALT)
    a1 = letzte_aenderung_id(api)
    assert _wahr(_erklaeren(api, regel_id=r["id"], buchung_id=bid)["ergebnis"])
    assert not _wahr(_erklaeren(api, regel_id=r["id"], buchung_id=b["edeka"].id)["ergebnis"])
    assert letzte_aenderung_id(api) == a1 > a0, "Lesezugriff"


def test_erklaeren_fehler(b):
    api, bid = b.api, b["rewe1"].id
    assert fehlercode(_erklaeren(api, 422, ausdruck=REWE)) == "validierung", "buchung_id ist Pflicht"
    assert fehlercode(_erklaeren(api, 422, buchung_id=bid)) == "validierung"
    m30.ausdruck_ungueltig(_erklaeren(api, 422, ausdruck="betrag >", buchung_id=bid), "syntax")
    assert fehlercode(_erklaeren(api, 404, regel_id=987654, buchung_id=bid)) == "nicht_gefunden"
    r = _erklaeren(api, (404, 422), ausdruck=REWE, buchung_id=987654)
    assert fehlercode(r) in ("nicht_gefunden", "referenz_unbekannt")


# ------------------------------------------------------------------ 8.8 einzelne Regel anwenden
def test_einzelne_regel_anwenden(b):
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Rewe", kategorie_id=k["Supermarkt"], ausdruck=REWE, tag_ids=[t["Steuer"]])
    a0 = letzte_aenderung_id(api)
    erg = einzeln_anwenden(api, r["id"])
    assert erg == {"geaendert": b.ids("rewe1", "rewe2", "erstattung"), "anzahl": 3}
    e = api.buchung_lesen(b["erstattung"].id)
    assert e["kategorie_id"] == k["Supermarkt"]
    assert e["vorschlag"] == {"kategorie_id": k["Supermarkt"], "regel_id": r["id"], "quelle": "regel",
                              "vorher_konto_id": k["Offen"]}
    r2 = api.buchung_lesen(b["rewe2"].id)
    assert r2["kategorie_id"] == k["Lebensmittel"] and r2["vorschlag"] is None, "abweichende bleiben"
    for n in ("rewe1", "rewe2", "erstattung"):
        assert t["Steuer"] in tags_von(api, b[n].id), n
    assert tags_von(api, b["rewe1"].id) == {t["Steuer"], t["Urlaub"]}, "vorhandene Tags bleiben"
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("regeln", "regeln_anwenden", None)
    assert sorted(x["objekt_id"] for x in a["eintraege"]) == erg["geaendert"]
    # noch einmal: nichts ändert sich, keine Änderung
    assert einzeln_anwenden(api, r["id"]) == {"geaendert": [], "anzahl": 0}
    assert len(aenderungen_seit(api, a0)) == 1
    # mit abweichende_ueberschreiben auch die anders kategorisierte Buchung
    erg = einzeln_anwenden(api, r["id"], abweichende_ueberschreiben=True)
    assert erg == {"geaendert": [b["rewe2"].id], "anzahl": 1}
    r2 = api.buchung_lesen(b["rewe2"].id)
    assert r2["kategorie_id"] == k["Supermarkt"] and r2["vorschlag"]["vorher_konto_id"] == k["Lebensmittel"]


def test_einzelne_regel_umfang(b):
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Müller", kategorie_id=k["Wohnen"], ausdruck='"Müller" in empfänger', tag_ids=[t["Urlaub"]])
    # Vorgabe der Testmenge wie beim Test: datum in -12m
    erg = api.post(f"/api/regeln/{r['id']}/anwenden", json={"stichtag": STICHTAG}, erwartet=200).daten
    assert erg == {"geaendert": [b["mueller"].id], "anzahl": 1}
    assert tags_von(api, b["schalttag"].id) == {t["Steuer"]}
    s = regel(api, "Alle", ausdruck="betrag >= 0 or betrag < 0", tag_ids=[t["Steuer"]])
    erg = einzeln_anwenden(api, s["id"], buchung_ids=[b["edeka"].id, b["miete"].id, b["gehalt"].id])
    assert erg["geaendert"] == b.ids("edeka", "miete"), "gesperrte Buchungen bleiben unberührt"
    assert tags_von(api, b["gehalt"].id) == set()
    erg = einzeln_anwenden(api, s["id"], konto_id=k["Spar"])
    assert erg["geaendert"] == [b["sparen"].id]
    erg = einzeln_anwenden(api, s["id"], testmenge="datum in letzte_woche", stichtag=STICHTAG)
    assert erg["geaendert"] == b.ids("rewe2", "mueller", "erstattung"), "edeka und sparen tragen den Tag schon"


def test_einzelne_regel_tags_auch_an_verdeckte(b):
    api, k, t = b.api, b.k, b.t
    regel(api, "Früher", kategorie_id=k["Wohnen"], ausdruck="betrag < 20", prioritaet=10)
    r = regel(api, "Rewe", kategorie_id=k["Supermarkt"], ausdruck=REWE, tag_ids=[t["Steuer"]], prioritaet=20)
    erg = einzeln_anwenden(api, r["id"])
    assert erg["geaendert"] == b.ids("rewe1", "rewe2", "erstattung")
    e = api.buchung_lesen(b["erstattung"].id)
    assert e["kategorie_id"] is None and e["vorschlag"] is None, "verdeckt: keine Kategorie von dieser Regel"
    assert t["Steuer"] in tags_von(api, e["id"]), "aber die Tags"


def test_einzelne_regel_fehler(b):
    api, k = b.api, b.k
    r = regel(api, "Rewe", kategorie_id=k["Supermarkt"], ausdruck=REWE)
    assert fehlercode(einzeln_anwenden(api, 987654, 404)) == "nicht_gefunden"
    m30.ausdruck_ungueltig(einzeln_anwenden(api, r["id"], 422, testmenge="betrag >"), "syntax")
    assert fehlercode(einzeln_anwenden(api, r["id"], 422, konto_id=k["Wohnen"])) == "konto_ungueltig"
    assert fehlercode(einzeln_anwenden(api, r["id"], 422, zusatz=1)) == "validierung"
    assert fehlercode(einzeln_anwenden(api, r["id"], 422, abweichende_ueberschreiben="ja")) == "validierung"
    assert api.buchung_lesen(b["erstattung"].id)["vorschlag"] is None
