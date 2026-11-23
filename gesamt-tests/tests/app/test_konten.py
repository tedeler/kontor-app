"""Konten und Kategorien: Anlegen, Ändern, Löschen, IBAN, Hierarchie, Salden (datenmodell.md 2)."""

from __future__ import annotations

import pytest

from generator.iban import fiktive_iban, ungueltige_iban
from tests.hilfen.api import fehlercode

ARTEN = ["girokonto", "sparkonto", "kreditkonto", "aufwand", "ertrag", "eigenkapital"]
KLASSE = {"girokonto": "bestand", "sparkonto": "bestand", "kreditkonto": "bestand",
          "aufwand": "aufwand", "ertrag": "ertrag", "eigenkapital": "eigenkapital"}


@pytest.mark.parametrize("art", ARTEN)
def test_konto_anlegen_vorgaben(api, art):
    k = api.konto("Mein Konto", art)
    assert k["name"] == "Mein Konto" and k["art"] == art
    assert k["eltern_id"] is None and k["iban"] is None and k["waehrung"] == "EUR"
    assert k["geschlossen"] is False and k["eroeffnet_am"] is None and k["notiz"] == ""
    assert k["extern_id"] is None
    assert k["ist_kategorie"] is (art in ("aufwand", "ertrag"))
    assert api.get(f"/api/konten/{k['id']}", erwartet=200).daten == k


def test_konto_alle_felder(api):
    iban = fiktive_iban(42)
    k = api.konto("Gemeinschaftskonto „Ärger“ & Co.", "girokonto", iban=iban, geschlossen=True,
                  eroeffnet_am="2020-02-29", notiz="Zeile 1\nZeile 2 – ☃")
    assert k["iban"] == iban and k["geschlossen"] is True and k["eroeffnet_am"] == "2020-02-29"
    assert k["notiz"] == "Zeile 1\nZeile 2 – ☃" and k["name"] == "Gemeinschaftskonto „Ärger“ & Co."


def test_name_wird_getrimmt(api):
    k = api.konto("  Girokonto \t", "girokonto")
    assert k["name"] == "Girokonto"
    r = api.patch(f"/api/konten/{k['id']}", json={"name": "  Neu  "}, erwartet=200)
    assert r.daten["name"] == "Neu"


@pytest.mark.parametrize("name", ["   ", "\t\n"])
def test_name_nur_leerraum_ungueltig(api, name):
    assert fehlercode(api.post("/api/konten", json={"name": name, "art": "girokonto"}, erwartet=422)) == "validierung"
    k = api.konto()
    assert fehlercode(api.patch(f"/api/konten/{k['id']}", json={"name": name}, erwartet=422)) == "validierung"
    assert api.get(f"/api/konten/{k['id']}", erwartet=200).daten["name"] == "Girokonto"


def test_namen_je_ebene_eindeutig(api):
    """Bis M31 „keine Eindeutigkeit gefordert“; ab M32 je Ebene eindeutig (sammel3.md 1, E-307)."""
    a = api.konto("Lebensmittel", "aufwand")
    r = api.post("/api/konten", json={"name": " lebensmittel ", "art": "aufwand"}, erwartet=409)
    assert r.json()["fehler"]["code"] == "konto_existiert" and a["id"] in r.json()["fehler"]["details"]["konto_ids"]
    b = api.konto("Lebensmittel", "ertrag")            # andere Klasse auf oberster Ebene
    c = api.konto("Lebensmittel", "aufwand", eltern_id=api.konto("Haushalt", "aufwand")["id"])  # anderes Elternkonto
    assert len({a["id"], b["id"], c["id"]}) == 3


def test_ids_steigend_und_nicht_wiederverwendet(api):
    a = api.konto("A")
    b = api.konto("B")
    assert b["id"] > a["id"] >= 1
    api.delete(f"/api/konten/{b['id']}", erwartet=204)
    c = api.konto("C")
    assert c["id"] > b["id"]


# ------------------------------------------------------------------- IBAN


def test_iban_normalisiert(api):
    iban = fiktive_iban(1234)
    eingabe = " ".join(iban[i:i + 4] for i in range(0, len(iban), 4)).lower()
    k = api.konto("Giro", iban=eingabe)
    assert k["iban"] == iban
    k2 = api.konto("Spar", "sparkonto")
    r = api.patch(f"/api/konten/{k2['id']}", json={"iban": " " + fiktive_iban(5678).lower() + " "}, erwartet=200)
    assert r.daten["iban"] == fiktive_iban(5678)


@pytest.mark.parametrize("iban", [ungueltige_iban(1), "DE00", "DE12 ABCD", "XX" + "1" * 20, "1234567890123456",
                                  fiktive_iban(7)[:-1]])
def test_iban_ungueltig(api, iban):
    r = api.post("/api/konten", json={"name": "Giro", "art": "girokonto", "iban": iban}, erwartet=422)
    assert fehlercode(r) == "iban_ungueltig"
    k = api.konto()
    r = api.patch(f"/api/konten/{k['id']}", json={"iban": iban}, erwartet=422)
    assert fehlercode(r) == "iban_ungueltig"
    assert api.get(f"/api/konten/{k['id']}", erwartet=200).daten["iban"] is None


def test_iban_eindeutig(api):
    iban = fiktive_iban(99)
    a = api.konto("A", iban=iban)
    r = api.post("/api/konten", json={"name": "B", "art": "sparkonto", "iban": iban.lower()}, erwartet=409)
    assert fehlercode(r) == "iban_existiert"
    b = api.konto("B", "sparkonto")
    assert fehlercode(api.patch(f"/api/konten/{b['id']}", json={"iban": iban}, erwartet=409)) == "iban_existiert"
    # eigene IBAN erneut setzen ist kein Konflikt
    assert api.patch(f"/api/konten/{a['id']}", json={"iban": iban}, erwartet=200).daten["iban"] == iban
    # IBAN entfernen und anderswo verwenden
    api.patch(f"/api/konten/{a['id']}", json={"iban": None}, erwartet=200)
    assert api.patch(f"/api/konten/{b['id']}", json={"iban": iban}, erwartet=200).daten["iban"] == iban


@pytest.mark.parametrize("art", ["aufwand", "ertrag", "eigenkapital"])
def test_iban_nur_fuer_bestandskonten(api, art):
    """IBAN bei Nicht-Bestandskonto: 422 (Code siehe E-025)."""
    r = api.post("/api/konten", json={"name": "K", "art": art, "iban": fiktive_iban(5)}, erwartet=422)
    assert fehlercode(r) in ("validierung", "iban_ungueltig")
    k = api.konto("K", art)
    r = api.patch(f"/api/konten/{k['id']}", json={"iban": fiktive_iban(5)}, erwartet=422)
    assert fehlercode(r) in ("validierung", "iban_ungueltig")


# -------------------------------------------------------------- Hierarchie


@pytest.mark.parametrize("kind,eltern", [(a, b) for a in ARTEN for b in ARTEN])
def test_eltern_gleiche_klasse(api, kind, eltern):
    e = api.konto("Eltern", eltern)
    r = api.post("/api/konten", json={"name": "Kind", "art": kind, "eltern_id": e["id"]})
    if KLASSE[kind] == KLASSE[eltern]:
        assert r.status_code == 201, r.text
        assert r.daten["eltern_id"] == e["id"]
    else:
        assert r.status_code == 422 and fehlercode(r) == "hierarchie_ungueltig", r.text


def test_eltern_unbekannt(api):
    assert fehlercode(api.post("/api/konten", json={"name": "K", "art": "aufwand", "eltern_id": 4711},
                               erwartet=422)) == "referenz_unbekannt"
    k = api.konto("K", "aufwand")
    assert fehlercode(api.patch(f"/api/konten/{k['id']}", json={"eltern_id": 4711},
                                erwartet=422)) == "referenz_unbekannt"


def test_keine_zyklen(api):
    a = api.konto("A", "aufwand")
    b = api.konto("B", "aufwand", eltern_id=a["id"])
    c = api.konto("C", "aufwand", eltern_id=b["id"])
    for kid, eltern in ((a, a), (a, b), (a, c), (b, c), (b, b)):
        r = api.patch(f"/api/konten/{kid['id']}", json={"eltern_id": eltern["id"]}, erwartet=422)
        assert fehlercode(r) == "hierarchie_ungueltig"
    assert [k["eltern_id"] for k in api.konten()] == [None, a["id"], b["id"]]
    # Umhängen ohne Zyklus und Lösen sind erlaubt
    assert api.patch(f"/api/konten/{c['id']}", json={"eltern_id": a["id"]}, erwartet=200).daten["eltern_id"] == a["id"]
    assert api.patch(f"/api/konten/{c['id']}", json={"eltern_id": None}, erwartet=200).daten["eltern_id"] is None


def test_patch_andere_klasse_als_eltern(api):
    a = api.konto("A", "aufwand")
    e = api.konto("E", "ertrag")
    assert fehlercode(api.patch(f"/api/konten/{e['id']}", json={"eltern_id": a["id"]},
                                erwartet=422)) == "hierarchie_ungueltig"


def test_art_nicht_aenderbar(api):
    k = api.konto("K", "aufwand")
    assert fehlercode(api.patch(f"/api/konten/{k['id']}", json={"art": "ertrag"}, erwartet=422)) == "validierung"
    assert api.get(f"/api/konten/{k['id']}", erwartet=200).daten["art"] == "aufwand"


def test_patch_nur_angegebene_felder(api):
    k = api.konto("Giro", iban=fiktive_iban(3), notiz="alt", eroeffnet_am="2020-01-01")
    r = api.patch(f"/api/konten/{k['id']}", json={"geschlossen": True}, erwartet=200).daten
    assert r == {**k, "geschlossen": True}
    r = api.patch(f"/api/konten/{k['id']}", json={}, erwartet=200).daten
    assert r == {**k, "geschlossen": True}
    r = api.patch(f"/api/konten/{k['id']}", json={"notiz": "", "eroeffnet_am": None}, erwartet=200).daten
    assert r == {**k, "geschlossen": True, "notiz": "", "eroeffnet_am": None}


def test_geschlossenes_konto_bleibt_nutzbar(api):
    g = api.konto("Alt", geschlossen=True)
    a = api.konto("Lebensmittel", "aufwand")
    api.buchung("2024-01-01", [(g["id"], -100), (a["id"], 100)])
    assert api.salden()[g["id"]]["saldo"] == -100


# -------------------------------------------------------------- Löschen


def test_loeschen(api):
    k = api.konto("Weg")
    api.delete(f"/api/konten/{k['id']}", erwartet=204)
    api.get(f"/api/konten/{k['id']}", erwartet=404)
    assert api.konten() == []


def test_loeschen_mit_splits_verboten(api):
    g = api.konto()
    a = api.konto("Lebensmittel", "aufwand")
    b = api.buchung("2024-01-01", [(g["id"], -100), (a["id"], 100)])
    for k in (g, a):
        assert fehlercode(api.delete(f"/api/konten/{k['id']}", erwartet=409)) == "konto_in_verwendung"
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    api.delete(f"/api/konten/{a['id']}", erwartet=204)


def test_loeschen_mit_unterkonten_verboten(api):
    e = api.konto("E", "aufwand")
    k = api.konto("K", "aufwand", eltern_id=e["id"])
    assert fehlercode(api.delete(f"/api/konten/{e['id']}", erwartet=409)) == "konto_in_verwendung"
    api.delete(f"/api/konten/{k['id']}", erwartet=204)
    api.delete(f"/api/konten/{e['id']}", erwartet=204)


# ------------------------------------------------------ Listen und Filter


def test_kontenliste_sortiert_und_gefiltert(api):
    angelegt = [api.konto(f"K{n}", art, geschlossen=(n % 2 == 0)) for n, art in enumerate(ARTEN * 2)]
    alle = api.konten()
    assert [k["id"] for k in alle] == sorted(k["id"] for k in angelegt)
    assert alle == sorted(angelegt, key=lambda k: k["id"])
    r = api.get("/api/konten", params={"art": ["aufwand", "ertrag"]}, erwartet=200).daten
    assert [k["id"] for k in r] == [k["id"] for k in alle if k["art"] in ("aufwand", "ertrag")]
    r = api.get("/api/konten", params={"art": "girokonto"}, erwartet=200).daten
    assert [k["id"] for k in r] == [k["id"] for k in alle if k["art"] == "girokonto"]
    r = api.get("/api/konten", params={"geschlossen": "true"}, erwartet=200).daten
    assert [k["id"] for k in r] == [k["id"] for k in alle if k["geschlossen"]]
    r = api.get("/api/konten", params={"geschlossen": "false", "art": "sparkonto"}, erwartet=200).daten
    assert [k["id"] for k in r] == [k["id"] for k in alle if not k["geschlossen"] and k["art"] == "sparkonto"]
    assert fehlercode(api.get("/api/konten", params={"art": "bargeld"}, erwartet=422)) == "validierung"
    kat = api.get("/api/kategorien", erwartet=200).daten
    assert kat == [k for k in alle if k["art"] in ("aufwand", "ertrag")]
    assert all(k["ist_kategorie"] for k in kat)


# ------------------------------------------------------------------ Salden


@pytest.mark.kern
def test_salden_und_uebersicht(api):
    """Saldo = Summe der Splits; saldo_gesamt rekursiv; Stichtag inklusive (datenmodell.md 2)."""
    g = api.konto("Giro")
    s = api.konto("Spar", "sparkonto")
    kk = api.konto("Kreditkarte", "kreditkonto")
    ek = api.konto("Anfang", "eigenkapital")
    geh = api.konto("Gehalt", "ertrag")
    wohn = api.konto("Wohnen", "aufwand")
    miete = api.konto("Miete", "aufwand", eltern_id=wohn["id"])
    strom = api.konto("Strom", "aufwand", eltern_id=miete["id"])
    leer = api.konto("Leer", "aufwand", geschlossen=True)
    api.buchung("2024-01-01", [(g["id"], 100000), (ek["id"], -100000)])
    api.buchung("2024-01-28", [(g["id"], 250000), (geh["id"], -250000)])
    api.buchung("2024-02-01", [(g["id"], -95000), (miete["id"], 95000)])
    api.buchung("2024-02-05", [(g["id"], -8500), (strom["id"], 8500)])
    api.buchung("2024-02-05", [(kk["id"], -1999), (wohn["id"], 1999)])
    api.buchung("2024-02-29", [(g["id"], -15000), (s["id"], 15000)])
    # zwei Splits auf demselben Konto zählen als eine Buchung
    api.buchung("2024-03-01", [(g["id"], -100), (g["id"], -200), (wohn["id"], 300)])

    u = api.uebersicht()
    assert u["stichtag"] is None
    assert [k["konto_id"] for k in u["konten"]] == [k["id"] for k in api.konten()]
    sal = {k["konto_id"]: k for k in u["konten"]}
    erwartet = {
        g["id"]: (231200, 231200, 6), s["id"]: (15000, 15000, 1), kk["id"]: (-1999, -1999, 1),
        ek["id"]: (-100000, -100000, 1), geh["id"]: (-250000, -250000, 1),
        wohn["id"]: (2299, 2299 + 95000 + 8500, 2), miete["id"]: (95000, 103500, 1),
        strom["id"]: (8500, 8500, 1), leer["id"]: (0, 0, 0),
    }
    ist = {kid: (sal[kid]["saldo"], sal[kid]["saldo_gesamt"], sal[kid]["anzahl_buchungen"]) for kid in erwartet}
    assert ist == erwartet
    assert u["summe_bestand"] == 231200 + 15000 - 1999
    assert u["summe_gesamt"] == 0
    assert sal[leer["id"]]["geschlossen"] is True and sal[miete["id"]]["eltern_id"] == wohn["id"]
    assert sal[strom["id"]]["name"] == "Strom" and sal[strom["id"]]["art"] == "aufwand"

    u = api.uebersicht("2024-02-05")
    assert u["stichtag"] == "2024-02-05"
    sal = {k["konto_id"]: k for k in u["konten"]}
    assert (sal[g["id"]]["saldo"], sal[g["id"]]["anzahl_buchungen"]) == (100000 + 250000 - 95000 - 8500, 4)
    assert sal[wohn["id"]]["saldo_gesamt"] == 1999 + 95000 + 8500
    assert sal[s["id"]]["saldo"] == 0 and sal[s["id"]]["anzahl_buchungen"] == 0
    assert u["summe_gesamt"] == 0
    u = api.uebersicht("2023-12-31")
    assert all(k["saldo"] == 0 and k["saldo_gesamt"] == 0 and k["anzahl_buchungen"] == 0 for k in u["konten"])
    assert u["summe_bestand"] == 0


@pytest.mark.kern
def test_uebersicht_leeres_buch(api):
    u = api.uebersicht()
    assert u == {"stichtag": None, "konten": [], "summe_bestand": 0, "summe_gesamt": 0}
