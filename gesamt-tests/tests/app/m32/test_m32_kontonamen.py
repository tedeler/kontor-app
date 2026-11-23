"""M32: Kontonamen je Ebene eindeutig (sammel3.md 1, D-218; E-295) – kern.

Erwartungen aus der Regel 1.1 (eigene Rechnung mit ``m32.namen_eindeutig``), nie aus Antworten der Anwendung.
"""

from __future__ import annotations

import pytest

from generator.iban import fiktive_iban
from tests.hilfen.kmybau import KBuch, KBuchung, KKonto, KSplit, gzip_bytes
from tests.hilfen.m2 import mock_api, sync
from tests.hilfen.m3 import (KORREKTUR, UNKATEGORISIERT, aenderungen_seit, bestand, erfassen, letzte_aenderung_id,
                             rueckgaengig)
from tests.hilfen.m19 import zusammenfuehren
from tests.hilfen.m32 import konto_existiert, namen_eindeutig

pytestmark = pytest.mark.kern


def _neu(api, name, art="aufwand", erwartet=201, **felder):
    return api.post("/api/konten", json={"name": name, "art": art, **felder}, erwartet=erwartet)


def _ohne_wirkung(api, aufruf, *konto_ids):
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    konto_existiert(aufruf(), *konto_ids)
    assert bestand(api) == vorher and aenderungen_seit(api, a0) == [], "abgelehnt ohne Wirkung und ohne Protokoll"


# ------------------------------------------------------------------ 1.1/1.2 Anlegen


@pytest.mark.parametrize("name", ["Lebensmittel", "lebensmittel", " LEBENSMITTEL ", "Lebensmittel\t"])
def test_anlegen_gleicher_name_auf_derselben_ebene(api, name):
    a = api.konto("Lebensmittel", "aufwand")
    _ohne_wirkung(api, lambda: _neu(api, name, erwartet=409), a["id"])


def test_oberste_ebene_je_klasse(api):
    giro = api.konto("Giro", "girokonto")
    _ohne_wirkung(api, lambda: _neu(api, "giro", "sparkonto", erwartet=409), giro["id"])
    _ohne_wirkung(api, lambda: _neu(api, "Giro", "kreditkonto", erwartet=409), giro["id"])
    zins_a = api.konto("Zinsen", "aufwand")
    zins_e = api.konto("Zinsen", "ertrag")
    zins_k = api.konto("Zinsen", "eigenkapital")
    assert len({zins_a["id"], zins_e["id"], zins_k["id"]}) == 3
    _ohne_wirkung(api, lambda: _neu(api, "ZINSEN", "ertrag", erwartet=409), zins_e["id"])


def test_verschiedene_eltern_und_umlaute(api):
    wohnen = api.konto("Wohnen", "aufwand")
    auto = api.konto("Auto", "aufwand")
    a = api.konto("Versicherung", "aufwand", eltern_id=wohnen["id"])
    b = api.konto("Versicherung", "aufwand", eltern_id=auto["id"])
    c = api.konto("Versicherung", "aufwand")
    assert len({a["id"], b["id"], c["id"]}) == 3
    _ohne_wirkung(api, lambda: _neu(api, "versicherung", eltern_id=wohnen["id"], erwartet=409), a["id"])
    # Umlaute zählen als verschieden (nur Groß/Klein und Leerraum am Rand, E-295)
    api.konto("Getränke", "aufwand")
    api.konto("Getraenke", "aufwand")
    giro_unter = api.konto("Unterkonto", "girokonto", eltern_id=api.konto("Hauptgiro", "girokonto")["id"])
    assert giro_unter["eltern_id"] is not None
    assert namen_eindeutig(api.konten())


# ------------------------------------------------------------------ 1.2 Umbenennen, Verschieben


def test_umbenennen_und_verschieben(api):
    haus = api.konto("Haushalt", "aufwand")
    leb_oben = api.konto("Lebensmittel", "aufwand")
    leb_unter = api.konto("Lebensmittel", "aufwand", eltern_id=haus["id"])
    drog = api.konto("Drogerie", "aufwand")
    _ohne_wirkung(api, lambda: api.patch(f"/api/konten/{drog['id']}", json={"name": "lebensmittel "}, erwartet=409),
                  leb_oben["id"])
    _ohne_wirkung(api, lambda: api.patch(f"/api/konten/{leb_oben['id']}", json={"eltern_id": haus["id"]},
                                         erwartet=409), leb_unter["id"])
    # eigener Name in anderer Schreibweise ist kein Konflikt
    r = api.patch(f"/api/konten/{leb_oben['id']}", json={"name": "LEBENSMITTEL"}, erwartet=200).daten
    assert r["name"] == "LEBENSMITTEL"
    # Verschieben unter ein Elternkonto ohne gleichnamiges Kind gelingt
    api.patch(f"/api/konten/{drog['id']}", json={"eltern_id": haus["id"]}, erwartet=200)
    assert namen_eindeutig(api.konten())


# ------------------------------------------------------------------ 1.2 Löschen mit hochrutschenden Unterkonten


@pytest.mark.parametrize("trocken", [True, False])
def test_loeschen_mit_hochrutschenden_unterkonten(api, trocken):
    haus = api.konto("Haushalt", "aufwand")
    oben = api.konto("Strom", "aufwand")
    zwischen = api.konto("Nebenkosten", "aufwand", eltern_id=haus["id"])
    unten = api.konto("Strom", "aufwand", eltern_id=zwischen["id"])
    # Nebenkosten löschen: „Strom“ rückt unter Haushalt – dort gibt es keinen „Strom“, also erlaubt
    api.post(f"/api/konten/{zwischen['id']}/loeschen", json={"buchungen": "loeschen", "konflikte": "loeschen",
                                                             "trocken": True}, erwartet=200)
    # Haushalt löschen: „Nebenkosten“ rückt auf die oberste Ebene – erlaubt; dann Nebenkosten löschen: „Strom“
    # rückt nach oben neben den vorhandenen „Strom“ → 409
    api.post(f"/api/konten/{haus['id']}/loeschen", json={"buchungen": "loeschen", "konflikte": "loeschen"},
             erwartet=200)
    _ohne_wirkung(api, lambda: api.post(f"/api/konten/{zwischen['id']}/loeschen", json={
        "buchungen": "loeschen", "konflikte": "loeschen", "trocken": trocken}, erwartet=409), oben["id"])
    assert unten["id"] in {k["id"] for k in api.konten()}


# ------------------------------------------------------------------ 1.2 Zusammenführen mit Unterkategorien


@pytest.mark.parametrize("trocken", [True, False])
def test_zusammenfuehren_mit_gleichnamigen_unterkategorien(api, trocken):
    q = api.konto("Auto", "aufwand")
    z = api.konto("Mobilität", "aufwand")
    api.konto("Versicherung", "aufwand", eltern_id=q["id"])
    zv = api.konto("versicherung", "aufwand", eltern_id=z["id"])
    _ohne_wirkung(api, lambda: zusammenfuehren(api, [q["id"]], z["id"], erwartet=409, trocken=trocken), zv["id"])


# ------------------------------------------------------------------ 1.2 Rückgängig


def test_rueckgaengig_abgelehnt_bei_gleichnamigen_geschwistern(api):
    alt = api.konto("Freizeit", "aufwand")
    a0 = letzte_aenderung_id(api)
    api.patch(f"/api/konten/{alt['id']}", json={"name": "Hobby"}, erwartet=200)
    (umbenennen,) = aenderungen_seit(api, a0)
    neu = api.konto("Freizeit", "aufwand")
    vorher = bestand(api)
    r = rueckgaengig(api, umbenennen["id"], 409)
    konto_existiert(r, neu["id"])
    assert bestand(api) == vorher
    # Löschen des neuen „Freizeit“ macht den Weg frei
    api.delete(f"/api/konten/{neu['id']}", erwartet=204)
    rueckgaengig(api, umbenennen["id"])
    assert next(k for k in api.konten() if k["id"] == alt["id"])["name"] == "Freizeit"


def test_rueckgaengig_einer_loeschung(api):
    a = api.konto("Kino", "aufwand")
    a0 = letzte_aenderung_id(api)
    api.delete(f"/api/konten/{a['id']}", erwartet=204)
    (loeschung,) = aenderungen_seit(api, a0)
    b = api.konto("kino", "aufwand")
    konto_existiert(rueckgaengig(api, loeschung["id"], 409), b["id"])


# ------------------------------------------------------------------ 1.3 Import


def _kmy(api, buch: KBuch) -> dict:
    return api.post("/api/import/kmymoney", files={"datei": ("x.kmy", gzip_bytes(buch), "x")}, erwartet=200).daten


def _warnung(r: dict, code: str, name: str) -> bool:
    return any(w["code"] == code and name in (w["referenz"] or "") for w in r["warnungen"])


def test_import_fuehrt_gleichnamige_kategorien_zusammen(api):
    b = KBuch()
    b.konten = [KKonto("A000001", "Giro", 1, "AStd::Asset", iban=fiktive_iban(9301)),
                KKonto("A000002", "Lebensmittel", 13, "AStd::Expense"),
                KKonto("A000003", "lebensmittel", 13, "AStd::Expense")]
    b.buchungen = [KBuchung("T000000000000000001", "2024-01-02", [KSplit("A000001", -500), KSplit("A000002", 500)]),
                   KBuchung("T000000000000000002", "2024-01-03", [KSplit("A000001", -700), KSplit("A000003", 700)])]
    a0 = letzte_aenderung_id(api)
    r = _kmy(api, b)
    assert len(aenderungen_seit(api, a0)) == 1, "die Bereinigung gehört zur Änderung des Imports (E-295)"
    assert r["kategorien_neu"] == 2
    assert _warnung(r, "konto_zusammengefasst", "ebensmittel"), r["warnungen"]
    kats = [k for k in api.konten() if k["art"] == "aufwand"]
    assert len(kats) == 1 and kats[0]["extern_id"] == "kmy:A000002", "in die mit der kleinsten ID"
    giro = next(k["id"] for k in api.konten() if k["art"] == "girokonto")
    assert api.salden()[kats[0]["id"]]["saldo"] == 1200 and api.salden()[giro]["saldo"] == -1200
    assert namen_eindeutig(api.konten())
    # erneuter Import: Bestand unverändert, kategorien_neu nennt die zweite erneut
    vorher = api.zustand()
    r2 = _kmy(api, b)
    assert api.zustand() == vorher
    assert r2["kategorien_neu"] == 1 and r2["buchungen_neu"] == 0


def test_import_benennt_gleichnamige_bestandskonten_um(api):
    vorhanden = api.konto("Tagesgeld", "sparkonto")
    b = KBuch()
    b.konten = [KKonto("A000001", "Tagesgeld", 2, "AStd::Asset", iban=fiktive_iban(9311)),
                KKonto("A000002", "Kasse", 1, "AStd::Asset"), KKonto("A000003", "Kasse", 1, "AStd::Asset")]
    r = _kmy(api, b)
    assert r["konten_neu"] == 3
    namen = sorted(k["name"] for k in api.konten() if k["art"] in ("girokonto", "sparkonto"))
    assert namen == ["Kasse", "Kasse (2)", "Tagesgeld", "Tagesgeld (2)"]
    assert next(k for k in api.konten() if k["id"] == vorhanden["id"])["name"] == "Tagesgeld", "das vorhandene bleibt"
    assert _warnung(r, "konto_umbenannt", "Tagesgeld") and _warnung(r, "konto_umbenannt", "Kasse"), r["warnungen"]
    assert namen_eindeutig(api.konten())


# ------------------------------------------------------------------ 1.4 Technische Konten, Synchronisation


def test_unkategorisiert_wird_uebernommen(api):
    giro = api.konto("Giro", "girokonto")
    eigen = api.konto("Unkategorisiert", "eigenkapital")
    b = erfassen(api, art="ausgabe", datum="2024-03-01", konto_id=giro["id"], betrag=300)
    konten = [k for k in api.konten() if k["name"].casefold() == "unkategorisiert" and k["eltern_id"] is None]
    assert [k["id"] for k in konten] == [eigen["id"]], "kein zweites Konto „Unkategorisiert“"
    assert konten[0]["extern_id"] == UNKATEGORISIERT
    assert eigen["id"] in [s["konto_id"] for s in b["splits"]]


def test_korrekturen_wird_uebernommen(api):
    giro = api.konto("Giro", "girokonto")
    eigen = api.konto("Korrekturen", "eigenkapital")
    b = erfassen(api, art="korrektur", datum="2024-03-01", konto_id=giro["id"], betrag=300)
    konten = [k for k in api.konten() if k["name"].casefold() == "korrekturen" and k["eltern_id"] is None]
    assert [k["id"] for k in konten] == [eigen["id"]] and konten[0]["extern_id"] == KORREKTUR
    assert eigen["id"] in [s["konto_id"] for s in b["splits"]]


def test_synchronisation_haengt_zusatz_an(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path, sync_konten_anlegen=True)
    hand = api.konto("Girokonto", "girokonto")   # ohne IBAN: wird nicht über die IBAN zugeordnet
    lauf = sync(api, von="2024-01-01")
    assert lauf["status"] == "erfolgreich"
    giro = [k for k in api.konten() if k["art"] == "girokonto"]
    assert sorted(k["name"] for k in giro) == ["Girokonto", "Girokonto (2)"]
    assert next(k for k in giro if k["id"] == hand["id"])["name"] == "Girokonto"
    assert namen_eindeutig(api.konten())
