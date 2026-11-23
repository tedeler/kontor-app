"""M3: Jede Operation mit Wirkung erzeugt genau eine Änderung mit genau den geänderten Objekten (T 3.5),
Rückgängig stellt den vorherigen Zustand exakt her und Wiederholen den späteren (T 3.6).

Erwartung: Die Einträge werden unabhängig aus dem REST-Zustand vor und nach der Operation berechnet
(Protokollform nach protokoll.md 2); kein Wert wird aus einer Antwort der Anwendung übernommen.
"""

from __future__ import annotations

import pytest

from generator.iban import fiktive_iban
from tests.hilfen.api import fehlercode
from tests.hilfen.kmybau import KBuch, KBuchung, KKonto, KSplit, gzip_bytes
from tests.hilfen.m3 import (aenderungen_seit, alle_aenderungen, bestand, erfassen, letzte_aenderung_id,
                             pruefe_eintraege, pruefe_rueckgaengig_rundreise, zeitstempel_ok, zustand_m3)
from tests.hilfen.pfade import KMY

GIRO_IBAN = fiktive_iban(7101)
SPAR_IBAN = fiktive_iban(7102)


def basis(api) -> dict:
    """Kleines Buch mit allen Objektarten; liefert Namen → Objekte."""
    c: dict = {}
    c["giro"] = api.konto("Girokonto", iban=GIRO_IBAN)
    c["spar"] = api.konto("Tagesgeld", "sparkonto", iban=SPAR_IBAN)
    c["kredit"] = api.konto("Kreditkarte", "kreditkonto")
    c["lebensmittel"] = api.konto("Lebensmittel", "aufwand")
    c["haushalt"] = api.konto("Haushalt", "aufwand")
    c["drogerie"] = api.konto("Drogerie", "aufwand", eltern_id=c["haushalt"]["id"])
    c["gehalt"] = api.konto("Gehalt", "ertrag")
    c["offen"] = api.konto("Offen", "eigenkapital")
    c["supermarkt"] = api.post("/api/empfaenger", json={"name": "Supermarkt", "aliase": ["SUPERMARKT GMBH"]},
                               erwartet=201).daten
    c["drogeriemarkt"] = api.empfaenger("Drogeriemarkt Beispiel")
    c["arbeitgeber"] = api.empfaenger("Arbeitgeber")
    c["urlaub"] = api.tag("Urlaub")
    c["steuer"] = api.tag("Steuer")
    g = c["giro"]["id"]
    c["b1"] = api.buchung("2024-01-10", [(g, -1234, "Wocheneinkauf"), (c["lebensmittel"]["id"], 1234, "Obst")],
                          empfaenger_id=c["supermarkt"]["id"], tag_ids=[c["urlaub"]["id"]],
                          verwendungszweck="Einkauf")
    c["b2"] = api.buchung("2024-01-28", [(g, 250000), (c["gehalt"]["id"], -250000)],
                          empfaenger_id=c["arbeitgeber"]["id"])
    c["b3"] = api.buchung("2024-01-12", [(g, -500), (c["offen"]["id"], 500)],
                          empfaenger_id=c["drogeriemarkt"]["id"], status="importiert")
    c["b4"] = api.buchung("2024-01-15", [(g, -3000), (c["haushalt"]["id"], 2000, "Putzmittel"),
                                         (c["drogerie"]["id"], 1000, "Seife")])
    c["b5"] = api.buchung("2024-01-20", [(g, -10000), (c["spar"]["id"], 10000)], verwendungszweck="Sparen")
    c["regel"] = api.post("/api/regeln", json={"name": "Drogerie", "kategorie_id": c["drogerie"]["id"],
                                               "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt",
                                                                "wert": "drogerie"}]}, erwartet=201).daten
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    assert api.buchung_lesen(c["b3"]["id"])["vorschlag"] is not None
    c["u1"] = erfassen(api, art="ausgabe", datum="2024-01-25", konto_id=g, betrag=777, verwendungszweck="Übertrag")
    c["u2"] = erfassen(api, art="einnahme", datum="2024-01-26", konto_id=c["spar"]["id"], betrag=777,
                       verwendungszweck="Übertrag")
    # Dublettenverdacht: gleicher Betrag einen Tag später aus KMyMoney (ähnlich)
    kb = KBuch()
    kb.konten = [KKonto("A000001", "Girokonto", 1, "AStd::Asset", iban=GIRO_IBAN),
                 KKonto("A000002", "Lebensmittel", 13, "AStd::Expense")]
    kb.empfaenger = [("P000001", "Supermarkt")]
    kb.buchungen = [KBuchung("T000000000000000001", "2024-01-11",
                             [KSplit("A000001", -1234, empfaenger="P000001"), KSplit("A000002", 1234)])]
    api.post("/api/import/kmymoney", files={"datei": ("d.kmy", gzip_bytes(kb), "x")}, erwartet=200)
    (c["verdacht"],) = api.get("/api/dubletten", erwartet=200).daten
    return c


def _ohne_aenderung(api, funktion) -> None:
    vor = letzte_aenderung_id(api)
    z = zustand_m3(api)
    funktion()
    assert aenderungen_seit(api, vor) == [], "Operation ohne Wirkung darf keine Änderung erzeugen"
    assert zustand_m3(api) == z


# --------------------------------------------------------------- Tabelle
def _abstimmung_vorbereiten(api, c):
    k = c["kredit"]["id"]
    api.buchung("2024-01-05", [(k, -4200), (c["lebensmittel"]["id"], 4200)])
    c["abst"] = api.post("/api/abstimmungen", json={"konto_id": k, "stichtag": "2024-01-31", "saldo": -4200},
                         erwartet=200).daten


OPERATIONEN = {
    "konto_anlegen": (None, lambda a, c: a.konto("Neu", "sparkonto", iban=fiktive_iban(7109))),
    "konto_aendern": (None, lambda a, c: a.patch(f"/api/konten/{c['giro']['id']}",
                                                 json={"name": "Giro", "notiz": "Hauptkonto"}, erwartet=200)),
    "konto_loeschen": (lambda a, c: c.update(leer=a.konto("Leer", "aufwand")),
                       lambda a, c: a.delete(f"/api/konten/{c['leer']['id']}", erwartet=204)),
    "buchung_anlegen": (None, lambda a, c: a.buchung("2024-02-01", [(c["giro"]["id"], -99),
                                                                     (c["lebensmittel"]["id"], 99)],
                                                      tag_ids=[c["steuer"]["id"]])),
    "buchung_erfassen": (None, lambda a, c: erfassen(a, art="ausgabe", datum="2024-02-02",
                                                     konto_id=c["giro"]["id"], betrag=4711,
                                                     empfaenger_name="Neuer Laden", memo="neu")),
    "buchung_aendern": (None, lambda a, c: a.patch(f"/api/buchungen/{c['b1']['id']}",
                                                   json={"verwendungszweck": "geändert",
                                                         "tag_ids": [c["steuer"]["id"]]}, erwartet=200)),
    "buchung_loeschen": (None, lambda a, c: a.delete(f"/api/buchungen/{c['b1']['id']}", erwartet=204)),
    "splits_ersetzen": (None, lambda a, c: a.put(f"/api/buchungen/{c['b4']['id']}/splits", json={"splits": [
        {"konto_id": c["giro"]["id"], "betrag": -3000}, {"konto_id": c["haushalt"]["id"], "betrag": 3000}]},
        erwartet=200)),
    "kategorie_setzen": (None, lambda a, c: a.put(f"/api/buchungen/{c['b1']['id']}/kategorie",
                                                  json={"kategorie_id": c["haushalt"]["id"]}, erwartet=200)),
    "mehrfach_kategorie": (None, lambda a, c: a.post("/api/buchungen/mehrfach/kategorie", json={
        "buchung_ids": [c["b1"]["id"], c["b2"]["id"]], "kategorie_id": c["lebensmittel"]["id"]}, erwartet=200)),
    "mehrfach_tags": (None, lambda a, c: a.post("/api/buchungen/mehrfach/tags", json={
        "buchung_ids": [c["b1"]["id"], c["b2"]["id"]], "hinzufuegen": [c["steuer"]["id"]],
        "entfernen": [c["urlaub"]["id"]]}, erwartet=200)),
    "vorschlag_entscheiden": (None, lambda a, c: a.post(f"/api/buchungen/{c['b3']['id']}/vorschlag",
                                                        json={"aktion": "ablehnen"}, erwartet=200)),
    "vorschlag_entscheiden:annehmen": (None, lambda a, c: a.post(f"/api/buchungen/{c['b3']['id']}/vorschlag",
                                                                 json={"aktion": "annehmen"}, erwartet=200)),
    "mehrfach_vorschlag": (None, lambda a, c: a.post("/api/buchungen/mehrfach/vorschlag", json={
        "buchung_ids": [c["b3"]["id"]], "aktion": "ablehnen"}, erwartet=200)),
    "tag_anlegen": (None, lambda a, c: a.tag("Neu")),
    "tag_umbenennen": (None, lambda a, c: a.patch(f"/api/tags/{c['urlaub']['id']}", json={"name": "Ferien"},
                                                  erwartet=200)),
    "tag_loeschen": (None, lambda a, c: a.delete(f"/api/tags/{c['urlaub']['id']}", erwartet=204)),
    "empfaenger_anlegen": (None, lambda a, c: a.post("/api/empfaenger", json={
        "name": "Bäckerei", "aliase": ["BAECKEREI GMBH"]},   # ab M32 ohne Standardkategorie (E-307)
        erwartet=201)),
    "empfaenger_aendern": (None, lambda a, c: a.patch(f"/api/empfaenger/{c['arbeitgeber']['id']}", json={
        "name": "Arbeitgeber GmbH", "aliase": ["ARBEITGEBER"]},
        erwartet=200)),
    "empfaenger_loeschen": (lambda a, c: c.update(leer=a.empfaenger("Niemand")),
                            lambda a, c: a.delete(f"/api/empfaenger/{c['leer']['id']}", erwartet=204)),
    "empfaenger_zusammenfuehren": (None, lambda a, c: a.post(
        f"/api/empfaenger/{c['supermarkt']['id']}/zusammenfuehren",
        json={"quelle_ids": [c["drogeriemarkt"]["id"]]}, erwartet=200)),
    "dublette_aufloesen": (None, lambda a, c: a.post(f"/api/dubletten/{c['verdacht']['id']}/aufloesen", json={
        "entscheidung": "zusammenfuehren", "behalten_id": c["verdacht"]["kandidat_ids"][0]}, erwartet=200)),
    "dublette_aufloesen:keine": (None, lambda a, c: a.post(f"/api/dubletten/{c['verdacht']['id']}/aufloesen",
                                                           json={"entscheidung": "keine_dublette"}, erwartet=200)),
    "regel_anlegen": (None, lambda a, c: a.post("/api/regeln", json={
        "name": "Gehalt", "kategorie_id": c["gehalt"]["id"],
        "bedingungen": [{"feld": "betrag", "operator": "mindestens", "wert": 100000}]}, erwartet=201)),
    "regel_aendern": (None, lambda a, c: a.patch(f"/api/regeln/{c['regel']['id']}",
                                                 json={"aktiv": False, "prioritaet": 7}, erwartet=200)),
    "regel_loeschen": (None, lambda a, c: a.delete(f"/api/regeln/{c['regel']['id']}", erwartet=204)),
    "regeln_anwenden": (lambda a, c: a.buchung("2024-02-03", [(c["giro"]["id"], -999), (c["offen"]["id"], 999)],
                                               empfaenger_id=c["drogeriemarkt"]["id"]),
                        lambda a, c: a.post("/api/regeln/anwenden", json={}, erwartet=200)),
    "abstimmung_anlegen": (lambda a, c: a.buchung("2024-01-05", [(c["kredit"]["id"], -4200),
                                                                  (c["lebensmittel"]["id"], 4200)]),
                           lambda a, c: a.post("/api/abstimmungen", json={
                               "konto_id": c["kredit"]["id"], "stichtag": "2024-01-31", "saldo": -4200},
                               erwartet=200)),
    "abstimmung_aufheben": (_abstimmung_vorbereiten,
                            lambda a, c: a.delete(f"/api/abstimmungen/{c['abst']['abstimmung']['id']}",
                                                  erwartet=204)),
    "umbuchung_zusammenfuehren": (None, lambda a, c: a.post("/api/umbuchungen/zusammenfuehren", json={
        "buchung_ids": [c["u1"]["id"], c["u2"]["id"]]}, erwartet=200)),
    "import_kmymoney": (None, lambda a, c: a.import_kmy(KMY / "minimal.kmy", erwartet=200)),
}

QUELLE = {"regeln_anwenden": "regeln", "import_kmymoney": "import"}


@pytest.mark.kern
@pytest.mark.parametrize("name", list(OPERATIONEN))
def test_operation_protokolliert_und_umkehrbar(api, name):
    prep, op = OPERATIONEN[name]
    aktion = name.split(":")[0]
    c = basis(api)
    if prep:
        prep(api, c)
    vor_id = letzte_aenderung_id(api)
    vorher = bestand(api)
    op(api, c)
    nachher = bestand(api)
    neu = aenderungen_seit(api, vor_id)
    assert len(neu) == 1, f"{name}: genau eine Änderung erwartet, erhalten {[a['aktion'] for a in neu]}"
    (a,) = neu
    assert a["aktion"] == aktion
    assert a["quelle"] == QUELLE.get(aktion, "manuell")
    if aktion == "import_kmymoney":
        imp = api.get("/api/importe", erwartet=200).daten[-1]
        assert a["gruppe"] == f"import:{imp['id']}"
    else:
        assert a["gruppe"] is None
    assert a["rueckgaengig_von"] == [] and a["rueckgaengig_durch"] is None
    assert a["beschreibung"].strip()
    assert zeitstempel_ok(a["zeitpunkt"])
    pruefe_eintraege(a, vorher, nachher)
    assert api.get(f"/api/aenderungen/{a['id']}", erwartet=200).daten == a
    pruefe_rueckgaengig_rundreise(api, a, vorher, nachher)


@pytest.mark.kern
def test_nebenwirkungen_in_derselben_aenderung(api):
    """Tag löschen ändert Buchungen, Regel löschen Vorschläge, Buchung löschen offene Verdachte."""
    c = basis(api)
    vor = letzte_aenderung_id(api)
    api.delete(f"/api/tags/{c['urlaub']['id']}", erwartet=204)
    api.delete(f"/api/regeln/{c['regel']['id']}", erwartet=204)
    api.delete(f"/api/buchungen/{c['b1']['id']}", erwartet=204)
    t, r, b = aenderungen_seit(api, vor)
    assert {(e["objekt"], e["objekt_id"]) for e in t["eintraege"]} == {("tag", c["urlaub"]["id"]),
                                                                       ("buchung", c["b1"]["id"])}
    assert {(e["objekt"], e["objekt_id"]) for e in r["eintraege"]} == {("regel", c["regel"]["id"]),
                                                                       ("buchung", c["b3"]["id"])}
    assert {(e["objekt"], e["objekt_id"]) for e in b["eintraege"]} == {("buchung", c["b1"]["id"]),
                                                                       ("verdacht", c["verdacht"]["id"])}
    eb = next(e for e in r["eintraege"] if e["objekt"] == "buchung")
    assert eb["vorher"]["vorschlag"]["regel_id"] == c["regel"]["id"] and eb["nachher"]["vorschlag"]["regel_id"] is None


@pytest.mark.kern
def test_umbenennen_aendert_keine_buchung(api):
    c = basis(api)
    vor = letzte_aenderung_id(api)
    api.patch(f"/api/tags/{c['urlaub']['id']}", json={"name": "Ferien"}, erwartet=200)
    api.patch(f"/api/empfaenger/{c['supermarkt']['id']}", json={"name": "Supermarkt Neu"}, erwartet=200)
    for a in aenderungen_seit(api, vor):
        assert [e["objekt"] for e in a["eintraege"]] in (["tag"], ["empfaenger"])


@pytest.mark.kern
def test_ohne_wirkung_keine_aenderung(api):
    c = basis(api)
    g, b1 = c["giro"], c["b1"]
    _ohne_aenderung(api, lambda: api.patch(f"/api/buchungen/{b1['id']}", json={
        "verwendungszweck": "Einkauf", "tag_ids": [c["urlaub"]["id"]], "status": "bestaetigt"}, erwartet=200))
    _ohne_aenderung(api, lambda: api.patch(f"/api/konten/{g['id']}", json={"name": "Girokonto"}, erwartet=200))
    _ohne_aenderung(api, lambda: api.post("/api/buchungen/mehrfach/tags", json={
        "buchung_ids": [b1["id"]], "hinzufuegen": [c["urlaub"]["id"]]}, erwartet=200))
    _ohne_aenderung(api, lambda: api.put(f"/api/buchungen/{b1['id']}/kategorie",
                                         json={"kategorie_id": c["lebensmittel"]["id"]}, erwartet=200))
    _ohne_aenderung(api, lambda: api.post("/api/regeln/anwenden", json={"trocken": True, "nur_unkategorisiert": False},
                                          erwartet=200))
    _ohne_aenderung(api, lambda: api.post("/api/abstimmungen", json={
        "konto_id": g["id"], "stichtag": "2024-12-31", "saldo": 1}, erwartet=200))
    _ohne_aenderung(api, lambda: api.post("/api/abstimmungen", json={
        "konto_id": c["kredit"]["id"], "stichtag": "2024-12-31", "saldo": 0, "trocken": True}, erwartet=200))
    _ohne_aenderung(api, lambda: api.post("/api/umbuchungen/erkennen", json={"trocken": True}, erwartet=200))
    _ohne_aenderung(api, lambda: api.patch(f"/api/empfaenger/{c['supermarkt']['id']}",
                                           json={"aliase": ["SUPERMARKT GMBH", "supermarkt-gmbh"]}, erwartet=200))


@pytest.mark.kern
@pytest.mark.parametrize("fall", ["unausgeglichen", "gesperrt", "unbekannt", "kategorie_ungueltig", "mehrfach",
                                  "validierung"])
def test_fehler_erzeugen_keine_aenderung(api, fall):
    c = basis(api)
    g = c["giro"]["id"]
    api.patch(f"/api/buchungen/{c['b2']['id']}", json={"status": "abgeglichen"}, erwartet=200)
    aktion = {
        "unausgeglichen": lambda: api.post("/api/buchungen", json={"datum": "2024-02-01", "splits": [
            {"konto_id": g, "betrag": -1}, {"konto_id": c["lebensmittel"]["id"], "betrag": 2}]}, erwartet=422),
        "gesperrt": lambda: api.delete(f"/api/buchungen/{c['b2']['id']}", erwartet=409),
        "unbekannt": lambda: api.patch("/api/buchungen/999999", json={"verwendungszweck": "x"}, erwartet=404),
        "kategorie_ungueltig": lambda: api.put(f"/api/buchungen/{c['b1']['id']}/kategorie",
                                               json={"kategorie_id": g}, erwartet=422),
        "mehrfach": lambda: api.post("/api/buchungen/mehrfach/kategorie", json={
            "buchung_ids": [c["b1"]["id"], c["b2"]["id"]], "kategorie_id": c["haushalt"]["id"]}, erwartet=409),
        "validierung": lambda: erfassen(api, 422, art="ausgabe", datum="2024-02-01", konto_id=g, betrag=0),
    }[fall]
    _ohne_aenderung(api, aktion)


@pytest.mark.kern
def test_zweiter_import_ohne_aenderung(api):
    api.import_kmy(KMY / "standard_bis_2023.kmy", erwartet=200)
    _ohne_aenderung(api, lambda: api.import_kmy(KMY / "standard_bis_2023.kmy", erwartet=200))


def test_lesen_und_filter(api):
    c = basis(api)
    alle = alle_aenderungen(api)
    assert [a["id"] for a in alle] == sorted((a["id"] for a in alle), reverse=True), "neueste zuerst"
    assert len({a["id"] for a in alle}) == len(alle)
    assert {a["aktion"] for a in alle} >= {"konto_anlegen", "empfaenger_anlegen", "tag_anlegen", "buchung_anlegen",
                                           "regel_anlegen", "regeln_anwenden", "buchung_erfassen",
                                           "import_kmymoney"}
    s = api.get("/api/aenderungen", params={"pro_seite": 3, "seite": 2}, erwartet=200).daten
    assert (s["seite"], s["pro_seite"], s["gesamt"]) == (2, 3, len(alle))
    assert [a["id"] for a in s["eintraege"]] == [a["id"] for a in alle[3:6]]
    assert alle_aenderungen(api, quelle="import") == [a for a in alle if a["quelle"] == "import"]
    assert alle_aenderungen(api, aktion="konto_anlegen") == [a for a in alle if a["aktion"] == "konto_anlegen"]
    g = next(a["gruppe"] for a in alle if a["gruppe"])
    assert alle_aenderungen(api, gruppe=g) == [a for a in alle if a["gruppe"] == g]
    b1 = c["b1"]["id"]
    verlauf = alle_aenderungen(api, objekt="buchung", objekt_id=b1)
    assert verlauf == [a for a in alle if any(e["objekt"] == "buchung" and e["objekt_id"] == b1
                                              for e in a["eintraege"])]
    assert verlauf and verlauf[-1]["aktion"] == "buchung_anlegen"
    api.get("/api/aenderungen", params={"quelle": ["manuell", "regeln"]}, erwartet=200)
    rueckg = api.post(f"/api/aenderungen/{alle[0]['id']}/rueckgaengig", erwartet=200).daten
    assert [a["id"] for a in alle_aenderungen(api, wirksam=False)] == [alle[0]["id"]]
    assert rueckg["id"] in [a["id"] for a in alle_aenderungen(api, wirksam=True)]
    assert fehlercode(api.get("/api/aenderungen", params={"objekt_id": b1}, erwartet=422)) == "validierung"
    assert fehlercode(api.get("/api/aenderungen", params={"quelle": "unbekannt"}, erwartet=422)) == "validierung"
    assert fehlercode(api.get("/api/aenderungen/999999", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.get("/api/aenderungen", params={"pro_seite": 501}, erwartet=422)) == "validierung"


def test_python_import_protokolliert(tmp_path):
    from tests.hilfen import kontor
    from tests.hilfen.api import Api, neue_config

    cfg = neue_config(tmp_path)
    e = kontor.importiere_kmy(cfg, KMY / "minimal.kmy")
    assert e.erfolgreich
    api = Api(cfg)
    (a,) = alle_aenderungen(api)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("import", "import_kmymoney", f"import:{e.import_id}")
    vorher = bestand(api)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == {}
    assert vorher
