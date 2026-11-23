"""Idempotenz und Zuordnung zu Vorhandenem beim Import (T 3.7, datenmodell.md 10.3)."""

from __future__ import annotations

import datetime as dt
import string

import pytest
from hypothesis import given, strategies as st

from generator.iban import fiktive_iban
from generator.kmy import erwartung
from tests.hilfen.erwartung import ZAEHLFELDER, lade, pruefe_buchbestand, pruefe_ergebnis
from tests.hilfen.kmybau import KBuch, KBuchung, KKonto, KSplit, gzip_bytes
from tests.hilfen.normal import eindeutiger_name
from tests.hilfen.pfade import KMY

FIXTURES = ["minimal", "minimal_unkomprimiert", "sonderfaelle", "fremdwaehrung",
            pytest.param("standard", marks=pytest.mark.langsam)]


def _zweiter_lauf_erwartet(erste: dict) -> dict:
    """Zählungen eines zweiten Imports derselben Datei, hergeleitet aus dem ersten (in leeres Buch)."""
    return {
        "konten_neu": 0, "konten_vorhanden": erste["konten_neu"] + erste["konten_vorhanden"],
        "kategorien_neu": 0, "kategorien_vorhanden": erste["kategorien_neu"] + erste["kategorien_vorhanden"],
        "empfaenger_neu": 0, "empfaenger_vorhanden": erste["empfaenger_neu"] + erste["empfaenger_vorhanden"],
        "tags_neu": 0, "tags_vorhanden": erste["tags_neu"] + erste["tags_vorhanden"],
        "buchungen_neu": 0, "buchungen_vorhanden": erste["buchungen_neu"] + erste["buchungen_zusammengefuehrt"],
        "buchungen_zusammengefuehrt": 0, "buchungen_zur_pruefung": 0,
        "buchungen_uebersprungen": erste["buchungen_uebersprungen"], "splits_neu": 0,
    }


def _zweimal(api, inhalt: bytes, name="x.kmy"):
    r1 = api.post("/api/import/kmymoney", files={"datei": (name, inhalt, "x")}, erwartet=200).daten
    vorher = api.zustand()
    r2 = api.post("/api/import/kmymoney", files={"datei": (name, inhalt, "x")}, erwartet=200).daten
    assert api.zustand() == vorher, "zweiter Import derselben Datei hat den Buchbestand verändert"
    assert r2["erfolgreich"] and r2["fehler"] == [] and r2["import_id"] > r1["import_id"]
    ist = {f: r2[f] for f in ZAEHLFELDER}
    assert ist == _zweiter_lauf_erwartet(r1), f"Zählungen des zweiten Imports: {ist}"
    assert len(api.get("/api/importe", erwartet=200).daten) == 2
    return r1, r2


@pytest.mark.kern
@pytest.mark.parametrize("name", FIXTURES)
def test_zweimal_importieren_aendert_nichts(api, name):
    _zweimal(api, (KMY / f"{name}.kmy").read_bytes())
    pruefe_buchbestand(api, lade(name))


def test_gzip_und_xml_derselben_datei(api):
    """minimal.kmy und minimal_unkomprimiert.kmy enthalten dasselbe Buch."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    vorher = api.zustand()
    r = api.import_kmy(KMY / "minimal_unkomprimiert.kmy", erwartet=200).daten
    assert api.zustand() == vorher
    assert r["format"] == "kmy-xml" and r["buchungen_vorhanden"] == 2 and r["buchungen_neu"] == 0


@pytest.mark.langsam
@pytest.mark.kern
def test_inkrementell_erweiterte_fassung(api):
    """Eine erweiterte Fassung (gleiche IDs, mehr Transaktionen) fügt genau das Zusätzliche hinzu."""
    teil, voll = lade("standard_bis_2023"), lade("standard")
    api.import_kmy(KMY / "standard_bis_2023.kmy", erwartet=200)
    r = api.import_kmy(KMY / "standard.kmy", erwartet=200).daten
    neu = [b for b in voll["buchungen"] if b["datum"] > "2023-12-31"]
    assert r["buchungen_neu"] == len(neu) == len(voll["buchungen"]) - len(teil["buchungen"])
    assert r["buchungen_vorhanden"] == len(teil["buchungen"])
    assert r["splits_neu"] == sum(len(b["splits"]) for b in neu)
    assert (r["buchungen_zusammengefuehrt"], r["buchungen_zur_pruefung"]) == (0, 0)
    assert (r["konten_neu"], r["kategorien_neu"], r["empfaenger_neu"], r["tags_neu"]) == (0, 0, 0, 0)
    assert r["konten_vorhanden"] == voll["ergebnis"]["konten_neu"]
    pruefe_buchbestand(api, voll)
    assert api.get("/api/dubletten", erwartet=200).daten == []


def test_zugeordnete_objekte_bleiben_unveraendert(api):
    """Kontor ist nach dem Import führend: Änderungen in Kontor überstehen einen erneuten Import."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    giro = next(k for k in api.konten() if k["extern_id"] == "kmy:A000001")
    tag = api.get("/api/tags", erwartet=200).daten[0]
    b = api.alle_buchungen()[0]
    api.patch(f"/api/konten/{giro['id']}", json={"name": "Umbenannt", "notiz": "eigene Notiz", "geschlossen": True},
              erwartet=200)
    api.patch(f"/api/tags/{tag['id']}", json={"name": "Haushalt neu"}, erwartet=200)
    api.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "geändert", "status": "bestaetigt",
                                                  "datum": "2020-01-01", "empfaenger_id": None}, erwartet=200)
    vorher = api.zustand()
    r = api.import_kmy(KMY / "minimal.kmy", erwartet=200).daten
    assert api.zustand() == vorher
    assert r["buchungen_vorhanden"] == 2 and r["konten_vorhanden"] == 1 and r["tags_vorhanden"] == 1


def test_geloeschte_buchung_wird_neu_importiert(api):
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    b = api.alle_buchungen()[0]
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    r = api.import_kmy(KMY / "minimal.kmy", erwartet=200).daten
    assert (r["buchungen_neu"], r["buchungen_vorhanden"], r["buchungen_zur_pruefung"]) == (1, 1, 0)
    assert len(api.alle_buchungen()) == 2
    assert api.get("/api/dubletten", erwartet=200).daten == []
    pruefe_buchbestand(api, lade("minimal"))


def test_kmy_buchungen_sind_keine_dublettenkandidaten(api):
    """Datensätze derselben Quelle sind nie Dubletten voneinander (datenmodell.md 10.4)."""
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    b = KBuch()
    b.konten = [KKonto("A000001", "Girokonto", 1, "AStd::Asset"), KKonto("A000002", "Lebensmittel", 13,
                                                                           "AStd::Expense")]
    b.empfaenger = [("P000002", "Supermarkt Frischekorb")]
    b.buchungen = [KBuchung("T000000000000000777", "2024-02-02",
                            [KSplit("A000001", -2500, empfaenger="P000002"), KSplit("A000002", 2500)])]
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", gzip_bytes(b), "x")}, erwartet=200).daten
    assert (r["buchungen_neu"], r["buchungen_zusammengefuehrt"], r["buchungen_zur_pruefung"]) == (1, 0, 0)
    assert api.get("/api/dubletten", erwartet=200).daten == []


# ------------------------------------------------- Regel 2 der Zuordnung


def _minimal_import(api):
    return api.import_kmy(KMY / "minimal.kmy", erwartet=200).daten


def test_bestandskonto_ueber_iban(api):
    hand = api.konto("Mein Giro", "girokonto", iban=fiktive_iban(3001))
    r = _minimal_import(api)
    assert (r["konten_neu"], r["konten_vorhanden"]) == (0, 1)
    k = api.get(f"/api/konten/{hand['id']}", erwartet=200).daten
    assert k == {**hand, "extern_id": "kmy:A000001"}, "nur extern_id wird gesetzt"
    assert api.salden()[hand["id"]]["saldo"] == 100000 - 2500
    assert len([x for x in api.konten() if x["art"] == "girokonto"]) == 1


def test_bestandskonto_ohne_passende_iban_neu(api):
    api.konto("Girokonto", "girokonto")  # gleicher Name, aber Bestandskonten werden nur über IBAN zugeordnet
    r = _minimal_import(api)
    assert (r["konten_neu"], r["konten_vorhanden"]) == (1, 0)
    assert len([x for x in api.konten() if x["art"] == "girokonto"]) == 2


def test_kategorien_ueber_art_name_eltern(api):
    leb1 = api.konto("Lebensmittel", "aufwand")  # ab M32 kein zweites gleichnamiges Konto mehr (E-307)
    api.konto("Gehalt", "aufwand")  # falsche Art
    oben = api.konto("Einkommen", "ertrag")
    api.konto("Gehalt", "ertrag", eltern_id=oben["id"])  # falsches Elternkonto
    r = _minimal_import(api)
    assert (r["kategorien_neu"], r["kategorien_vorhanden"]) == (1, 1)
    konten = {k["id"]: k for k in api.konten()}
    assert konten[leb1["id"]]["extern_id"] == "kmy:A000002"
    neu = [k for k in konten.values() if k["extern_id"] == "kmy:A000003"]
    assert len(neu) == 1 and neu[0]["art"] == "ertrag" and neu[0]["eltern_id"] is None
    assert api.salden()[leb1["id"]]["saldo"] == 2500


def test_kategorie_name_exakt(api):
    api.konto("lebensmittel", "aufwand")
    r = _minimal_import(api)
    assert (r["kategorien_neu"], r["kategorien_vorhanden"]) == (2, 0)


def test_unterkategorie_mit_zugeordnetem_eltern(api):
    b = KBuch()
    b.konten = [KKonto("A000001", "Wohnen", 13, "AStd::Expense"), KKonto("A000002", "Miete", 13, "A000001"),
                KKonto("A000003", "Giro", 1, "AStd::Asset", iban=fiktive_iban(9100))]
    b.buchungen = [KBuchung("T000000000000000001", "2024-01-01", [KSplit("A000003", -500), KSplit("A000002", 500)])]
    wohnen = api.konto("Wohnen", "aufwand")
    miete = api.konto("Miete", "aufwand", eltern_id=wohnen["id"])
    api.konto("Miete", "aufwand")  # gleicher Name, aber Wurzelkonto
    r = api.post("/api/import/kmymoney", files={"datei": ("x.kmy", gzip_bytes(b), "x")}, erwartet=200).daten
    assert (r["kategorien_neu"], r["kategorien_vorhanden"], r["konten_neu"]) == (0, 2, 1)
    assert api.get(f"/api/konten/{miete['id']}", erwartet=200).daten["extern_id"] == "kmy:A000002"
    assert api.salden()[miete["id"]]["saldo"] == 500


def test_empfaenger_und_tags_ueber_namen(api):
    hand_e = api.empfaenger("Supermarkt Frischekorb")
    hand_t = api.tag("HAUSHALT")
    r = _minimal_import(api)
    assert (r["empfaenger_neu"], r["empfaenger_vorhanden"], r["tags_neu"], r["tags_vorhanden"]) == (1, 1, 0, 1)
    codes = {w["code"] for w in r["warnungen"]}
    assert not codes & {"empfaenger_zusammengefasst", "tag_zusammengefasst"}, \
        "Warnung nur, wenn das Gegenstück in diesem Lauf angelegt wurde"
    assert api.get(f"/api/empfaenger/{hand_e['id']}", erwartet=200).daten["name"] == "Supermarkt Frischekorb"
    tags = api.get("/api/tags", erwartet=200).daten
    assert [(t["id"], t["name"], t["anzahl_buchungen"]) for t in tags] == [(hand_t["id"], "HAUSHALT", 1)]
    einkauf = next(b for b in api.alle_buchungen() if b["verwendungszweck"] == "Wocheneinkauf")
    assert einkauf["empfaenger"]["id"] == hand_e["id"] and einkauf["tags"] == [{"id": hand_t["id"],
                                                                                "name": "HAUSHALT"}]


# ------------------------------------------------ zufällige Bücher (Hypothesis)

NAMENSZEICHEN = string.ascii_letters + "äöüÄÖÜß &<>\"'–€☕"
namen = st.text(NAMENSZEICHEN, min_size=1, max_size=12).filter(lambda s: s.strip() == s and s)


@st.composite
def kmy_buch(draw) -> KBuch:
    b = KBuch()
    n_bestand = draw(st.integers(1, 3))
    konten = []
    vergeben = {"anfangsbestand"}  # M32: Kontonamen je Ebene eindeutig (E-307), hier über das ganze Buch
    for i in range(n_bestand):
        typ = draw(st.sampled_from([1, 2, 4, 5]))
        iban = fiktive_iban(8000 + i) if draw(st.booleans()) else None
        eltern = "AStd::Liability" if typ in (4, 5) else "AStd::Asset"
        konten.append(KKonto(f"A{i + 1:06d}", eindeutiger_name(draw(namen), vergeben), typ, eltern, iban=iban,
                             geschlossen=draw(st.booleans())))
    kat_ids = []
    for j in range(draw(st.integers(1, 4))):
        kid = f"A{100 + j:06d}"
        typ = draw(st.sampled_from([12, 13]))
        eltern = "AStd::Income" if typ == 12 else "AStd::Expense"
        gleiche = [k for k in konten if k.id in kat_ids and k.typ == typ]
        if gleiche and draw(st.booleans()):
            eltern = draw(st.sampled_from(gleiche)).id
        konten.append(KKonto(kid, eindeutiger_name(draw(namen), vergeben), typ, eltern))
        kat_ids.append(kid)
    if draw(st.booleans()):
        konten.append(KKonto("A000200", "Anfangsbestand", 16, "AStd::Equity"))
    b.konten = konten
    b.empfaenger = [(f"P{i + 1:06d}", draw(namen)) for i in range(draw(st.integers(0, 4)))]
    b.tags = [(f"G{i + 1:06d}", draw(st.sampled_from(["Urlaub", "urlaub", "Steuer", "STEUER", "Ölfass"])))
              for i in range(draw(st.integers(0, 3)))]
    payees = [p for p, _ in b.empfaenger] + [""]
    tags = [t for t, _ in b.tags]
    alle = [k.id for k in konten]
    buchungen = []
    for n in range(draw(st.integers(0, 12))):
        k = draw(st.integers(1, 4))
        werte = draw(st.lists(st.integers(-50_000, 50_000), min_size=k, max_size=k))
        if draw(st.integers(0, 3)) > 0:
            werte[-1] = -sum(werte[:-1]) if k > 1 else werte[-1]
        splits = [KSplit(draw(st.sampled_from(alle)), w, memo=draw(st.sampled_from(["", "Memo ä&<"])),
                         empfaenger=draw(st.sampled_from(payees)),
                         tags=draw(st.lists(st.sampled_from(tags), max_size=2, unique=True)) if tags else [])
                  for w in werte]
        datum = draw(st.dates(min_value=dt.date(2020, 1, 1), max_value=dt.date(2025, 12, 31))).isoformat()
        buchungen.append(KBuchung(f"T{n + 1:018d}", datum, splits, memo=draw(namen)))
    b.buchungen = buchungen
    return b


@pytest.mark.kern
@given(kmy_buch())
def test_zufaellige_buecher_exakt_und_idempotent(api_fabrik, buch):
    """Import zufälliger Bücher entspricht der bekannten Wahrheit des Generators und ist idempotent."""
    erw = erwartung(buch, fixture="hypothesis", format_="kmy-gzip")
    api = api_fabrik()
    r1, _ = _zweimal(api, gzip_bytes(buch))
    pruefe_ergebnis(r1, erw["ergebnis"], warnungen=erw["warnungen"])
    pruefe_buchbestand(api, erw)
    assert api.uebersicht()["summe_gesamt"] == 0
