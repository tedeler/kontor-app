"""M2: Auswertung der Regeln und Anwenden auf vorhandene Buchungen (kategorisierung.md 1.1, 3, 4; T 8).

Erwartungen: unabhängiges Orakel ``tests/hilfen/sync_orakel`` (regel_fuer).
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from generator.iban import fiktive_iban
from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.erwartung import lade
from tests.hilfen.pfade import KMY


class Buch:
    """Kleines Buch für Regeltests: Giro, Spar, Eigenkapitalkonto „Offen“, vier Kategorien."""

    def __init__(self, api) -> None:
        self.api = api
        self.giro = api.konto("Giro", iban=fiktive_iban(5201))["id"]
        self.spar = api.konto("Spar", "sparkonto", iban=fiktive_iban(5202))["id"]
        self.offen = api.konto("Offen", "eigenkapital")["id"]
        self.lebensmittel = api.konto("Lebensmittel", "aufwand")["id"]
        self.cafe = api.konto("Café", "aufwand")["id"]
        self.sonstiges = api.konto("Sonstiges", "aufwand")["id"]
        self.gehalt = api.konto("Gehalt", "ertrag")["id"]
        self._empf: dict[str, int] = {}

    def empf(self, name: str | None) -> int | None:
        if name is None:
            return None
        if name not in self._empf:
            self._empf[name] = self.api.empfaenger(name)["id"]
        return self._empf[name]

    def buche(self, betrag: int, empfaenger: str | None = None, zweck: str = "", konto: int | None = None,
              gegen: int | None = None, **felder) -> dict:
        konto = konto or self.giro
        gegen = gegen or self.offen
        return self.api.buchung("2024-03-01", [(konto, betrag), (gegen, -betrag)], empfaenger_id=self.empf(empfaenger),
                                verwendungszweck=zweck, **felder)

    def regel(self, kategorie: int, *bedingungen: dict, **felder) -> dict:
        body = {"name": felder.pop("name", "R"), "kategorie_id": kategorie, "bedingungen": list(bedingungen), **felder}
        return self.api.post("/api/regeln", json=body, erwartet=201).daten

    def anwenden(self, erwartet=200, **body):
        return self.api.post("/api/regeln/anwenden", json=body, erwartet=erwartet)


def bed(feld, operator, wert):
    return {"feld": feld, "operator": operator, "wert": wert}


@pytest.fixture
def buch(api):
    return Buch(api)


FAELLE = [
    # (Bedingung, Empfänger, Verwendungszweck, Betrag, Konto, Treffer)
    (bed("empfaenger", "enthaelt", "rewe"), "REWE Markt", "", -100, "giro", True),
    (bed("empfaenger", "enthaelt", "Müller"), "MUELLER GmbH", "", -100, "giro", True),
    (bed("empfaenger", "enthaelt", "mueller"), "Bäckerei Müller", "", -100, "giro", True),
    (bed("empfaenger", "enthaelt", "straße"), "HAUPTSTRASSE 5", "", -100, "giro", True),
    (bed("empfaenger", "enthaelt", "café"), "CAFÉ Bohne", "", -100, "giro", True),
    (bed("empfaenger", "enthaelt", "cafe"), "Café Bohne", "", -100, "giro", False),
    (bed("empfaenger", "enthaelt", "rewe"), None, "rewe", -100, "giro", False),
    (bed("empfaenger", "enthaelt", "Miete"), "Hausverwaltung", "Miete", -100, "giro", False),
    (bed("empfaenger", "gleich", "rewe markt"), "REWE Markt", "", -100, "giro", True),
    (bed("empfaenger", "gleich", "rewe"), "REWE Markt", "", -100, "giro", False),
    (bed("empfaenger", "beginnt_mit", "rewe"), "REWE Markt", "", -100, "giro", True),
    (bed("empfaenger", "beginnt_mit", "markt"), "REWE Markt", "", -100, "giro", False),
    (bed("verwendungszweck", "enthaelt", "miete"), "X", "Miete Januar", -100, "giro", True),
    (bed("verwendungszweck", "enthaelt", "x"), "x", "", -100, "giro", False),
    (bed("verwendungszweck", "beginnt_mit", "LOHN"), None, "lohn/gehalt 01", 100, "giro", True),
    (bed("verwendungszweck", "gleich", "Überweisung"), None, "UEBERWEISUNG", 100, "giro", True),
    (bed("betrag", "gleich", -1234), None, "", -1234, "giro", True),
    (bed("betrag", "gleich", -1234), None, "", 1234, "giro", False),
    (bed("betrag", "mindestens", -1000), None, "", -1000, "giro", True),
    (bed("betrag", "mindestens", -1000), None, "", -1001, "giro", False),
    (bed("betrag", "hoechstens", -5001), None, "", -5001, "giro", True),
    (bed("betrag", "hoechstens", -5001), None, "", -5000, "giro", False),
    (bed("konto_id", "gleich", "spar"), None, "", -100, "spar", True),
    (bed("konto_id", "gleich", "spar"), None, "", -100, "giro", False),
]


@pytest.mark.kern
@pytest.mark.parametrize("bedingung,empf,zweck,betrag,konto,treffer", FAELLE,
                         ids=[f"{i:02d}-{f[0]['feld']}-{f[0]['operator']}-{'ja' if f[5] else 'nein'}"
                              for i, f in enumerate(FAELLE)])
def test_bedingung(buch, bedingung, empf, zweck, betrag, konto, treffer):
    if bedingung["feld"] == "konto_id":
        bedingung = {**bedingung, "wert": getattr(buch, bedingung["wert"])}
    b = buch.buche(betrag, empf, zweck, konto=getattr(buch, konto))
    r = buch.regel(buch.cafe, bedingung)
    erg = buch.anwenden(trocken=True).daten
    assert erg["geprueft"] == 1
    assert erg["aenderungen"] == ([{"buchung_id": b["id"], "regel_id": r["id"], "kategorie_id": buch.cafe}]
                                  if treffer else [])


def test_bedingungen_und_verknuepft(buch):
    b1 = buch.buche(-6000, "Kaufhaus")
    b2 = buch.buche(-4000, "Kaufhaus")
    buch.buche(-6000, "Andere")
    buch.regel(buch.sonstiges, bed("empfaenger", "enthaelt", "kauf"), bed("betrag", "hoechstens", -5001))
    assert [a["buchung_id"] for a in buch.anwenden(trocken=True).daten["aenderungen"]] == [b1["id"]]
    assert b2


def test_regelbetrag_summe_der_bestandskonten(buch):
    b = buch.api.buchung("2024-03-01", [(buch.giro, -1000), (buch.spar, -500), (buch.offen, 1500)])
    buch.regel(buch.cafe, bed("betrag", "gleich", -1000), name="nur Giro")
    assert buch.anwenden(trocken=True).daten["aenderungen"] == []
    r = buch.regel(buch.cafe, bed("betrag", "gleich", -1500), name="Summe")
    assert buch.anwenden(trocken=True).daten["aenderungen"] == [
        {"buchung_id": b["id"], "regel_id": r["id"], "kategorie_id": buch.cafe}]


# ------------------------------------------------------------ Priorität


@pytest.mark.kern
def test_prioritaet(buch):
    b = buch.buche(-500, "Café Bohne", "Kartenzahlung")
    r_cafe = buch.regel(buch.cafe, bed("empfaenger", "enthaelt", "café"), prioritaet=20, name="café")
    r_karte = buch.regel(buch.sonstiges, bed("verwendungszweck", "enthaelt", "karten"), prioritaet=10, name="karte")
    assert buch.anwenden(trocken=True).daten["aenderungen"] == [
        {"buchung_id": b["id"], "regel_id": r_karte["id"], "kategorie_id": buch.sonstiges}]
    buch.api.patch(f"/api/regeln/{r_karte['id']}", json={"prioritaet": 30}, erwartet=200)
    assert buch.anwenden(trocken=True).daten["aenderungen"][0]["regel_id"] == r_cafe["id"]
    # Gleichstand: kleinere id gewinnt
    buch.api.patch(f"/api/regeln/{r_karte['id']}", json={"prioritaet": 20}, erwartet=200)
    assert buch.anwenden(trocken=True).daten["aenderungen"][0]["regel_id"] == r_cafe["id"]
    # inaktive Regel mit höchster Priorität wird ignoriert
    buch.regel(buch.gehalt, bed("empfaenger", "enthaelt", "bohne"), prioritaet=0, aktiv=False, name="inaktiv")
    assert buch.anwenden(trocken=True).daten["aenderungen"][0]["regel_id"] == r_cafe["id"]
    buch.api.patch(f"/api/regeln/{r_cafe['id']}", json={"aktiv": False}, erwartet=200)
    assert buch.anwenden(trocken=True).daten["aenderungen"][0]["regel_id"] == r_karte["id"]


def test_regel_ids_schraenkt_ein(buch):
    b = buch.buche(-500, "Café Bohne", "Kartenzahlung")
    r1 = buch.regel(buch.cafe, bed("empfaenger", "enthaelt", "café"), prioritaet=1)
    r2 = buch.regel(buch.sonstiges, bed("verwendungszweck", "enthaelt", "karten"), prioritaet=2)
    inaktiv = buch.regel(buch.gehalt, bed("verwendungszweck", "enthaelt", "karten"), prioritaet=0, aktiv=False)
    assert buch.anwenden(trocken=True, regel_ids=[r2["id"]]).daten["aenderungen"] == [
        {"buchung_id": b["id"], "regel_id": r2["id"], "kategorie_id": buch.sonstiges}]
    assert buch.anwenden(trocken=True, regel_ids=[inaktiv["id"]]).daten["aenderungen"] == []
    assert buch.anwenden(trocken=True, regel_ids=[inaktiv["id"], r1["id"]]).daten["aenderungen"][0]["regel_id"] == \
        r1["id"]


# --------------------------------------------------------------- Umfang


@pytest.fixture
def umfang(buch):
    api = buch.api
    b = {
        "unkat": buch.buche(-100, "Treffer"),
        "kat": buch.buche(-100, "Treffer", gegen=buch.lebensmittel),
        "umbuchung": api.buchung("2024-03-01", [(buch.giro, -100), (buch.spar, 100)],
                                 empfaenger_id=buch.empf("Treffer")),
        "split": api.buchung("2024-03-01", [(buch.giro, -100), (buch.lebensmittel, 60), (buch.offen, 40)],
                             empfaenger_id=buch.empf("Treffer")),
        "abgeglichen": buch.buche(-100, "Treffer"),
        "ohne_treffer": buch.buche(-100, "Andere"),
    }
    api.patch(f"/api/buchungen/{b['abgeglichen']['id']}", json={"status": "abgeglichen"}, erwartet=200)
    r = buch.regel(buch.cafe, bed("empfaenger", "gleich", "treffer"))
    return buch, b, r


@pytest.mark.kern
def test_umfang_nur_unkategorisiert(umfang):
    buch, b, r = umfang
    vorher = buch.api.zustand()
    probe = buch.anwenden(trocken=True).daten
    assert probe == {"geprueft": 2, "anzahl": 1, "trocken": True,
                     "aenderungen": [{"buchung_id": b["unkat"]["id"], "regel_id": r["id"], "kategorie_id": buch.cafe}]}
    assert buch.api.zustand() == vorher, "Probelauf ändert nichts"
    echt = buch.anwenden().daten
    assert echt == {**probe, "trocken": False}
    for name, x in b.items():
        neu = buch.api.buchung_lesen(x["id"])
        if name == "unkat":
            alt_split = x["splits"][1]
            assert neu["splits"] == [x["splits"][0], {**alt_split, "konto_id": buch.cafe}]
            assert neu["kategorie_id"] == buch.cafe
            assert neu["vorschlag"] == {"kategorie_id": buch.cafe, "regel_id": r["id"], "quelle": "regel",
                                        "vorher_konto_id": buch.offen}
            assert {f: neu[f] for f in ("status", "tags", "datum", "empfaenger", "verwendungszweck")} == \
                {f: x[f] for f in ("status", "tags", "datum", "empfaenger", "verwendungszweck")}
        else:
            assert neu["splits"] == x["splits"] and neu["vorschlag"] is None, name


def test_umfang_alle_kategorisierbaren(umfang):
    buch, b, r = umfang
    erg = buch.anwenden(nur_unkategorisiert=False).daten
    assert erg["geprueft"] == 3
    assert [a["buchung_id"] for a in erg["aenderungen"]] == sorted([b["unkat"]["id"], b["kat"]["id"]])
    kat = buch.api.buchung_lesen(b["kat"]["id"])
    assert kat["kategorie_id"] == buch.cafe and kat["vorschlag"]["vorher_konto_id"] == buch.lebensmittel


def test_umfang_buchung_ids(umfang):
    buch, b, r = umfang
    ids = sorted([b["unkat"]["id"], b["umbuchung"]["id"], b["abgeglichen"]["id"]])
    erg = buch.anwenden(trocken=True, buchung_ids=ids).daten
    assert erg["geprueft"] == 1 and [a["buchung_id"] for a in erg["aenderungen"]] == [b["unkat"]["id"]]


def test_gleiche_kategorie_bleibt_unveraendert(buch):
    b = buch.buche(-100, "Treffer", gegen=buch.cafe)
    buch.regel(buch.cafe, bed("empfaenger", "gleich", "treffer"))
    erg = buch.anwenden(nur_unkategorisiert=False).daten
    assert (erg["geprueft"], erg["aenderungen"]) == (1, [])
    assert buch.api.buchung_lesen(b["id"])["vorschlag"] is None


def test_offener_vorschlag_behaelt_vorher_konto(buch):
    b = buch.buche(-100, "Treffer")
    r1 = buch.regel(buch.cafe, bed("empfaenger", "gleich", "treffer"), prioritaet=50)
    buch.anwenden()
    r2 = buch.regel(buch.sonstiges, bed("empfaenger", "enthaelt", "treff"), prioritaet=10)
    assert buch.anwenden().daten["aenderungen"] == [], "nur unkategorisierte (kategorie_id null) werden geprüft"
    buch.anwenden(nur_unkategorisiert=False)
    v = buch.api.buchung_lesen(b["id"])["vorschlag"]
    assert v == {"kategorie_id": buch.sonstiges, "regel_id": r2["id"], "quelle": "regel", "vorher_konto_id": buch.offen}
    assert r1


@pytest.mark.parametrize("body,code,details", [
    ({"buchung_ids": [4711]}, "referenz_unbekannt", {"buchung_ids": [4711]}),
    ({"regel_ids": [4711]}, "referenz_unbekannt", {"regel_ids": [4711]}),
    ({"buchung_ids": [1, 1]}, "validierung", None),
    ({"buchung_ids": []}, "validierung", None),
    ({"regel_ids": "1"}, "validierung", None),
    ({"trocken": "ja"}, "validierung", None),
    ({"unbekannt": True}, "validierung", None),
])
def test_anwenden_fehler(buch, body, code, details):
    b = buch.buche(-100, "Treffer")
    buch.regel(buch.cafe, bed("empfaenger", "gleich", "treffer"))
    if body.get("buchung_ids") == [1, 1]:
        body = {"buchung_ids": [b["id"], b["id"]]}
    r = buch.anwenden(erwartet=422, **body)
    assert fehlercode(r) == code
    if details:
        for schl, wert in details.items():
            assert r.json()["fehler"]["details"][schl] == wert
    assert buch.api.buchung_lesen(b["id"])["vorschlag"] is None


def test_ohne_regeln(buch):
    buch.buche(-100, "x")
    assert buch.anwenden().daten == {"geprueft": 1, "anzahl": 0, "trocken": False, "aenderungen": []}


# ---------------------------------------------- keine automatische Anwendung


@pytest.mark.kern
def test_keine_automatische_anwendung(buch, tmp_path):
    vorher = buch.buche(-100, "Treffer")
    buch.regel(buch.cafe, bed("empfaenger", "gleich", "treffer"))
    nachher = buch.buche(-100, "Treffer")
    for b in (vorher, nachher):
        neu = buch.api.buchung_lesen(b["id"])
        assert neu["vorschlag"] is None and neu["kategorie_id"] is None
    # Import aus KMyMoney wird nicht kategorisiert, auch wenn Regeln passen würden
    buch.regel(buch.cafe, bed("verwendungszweck", "enthaelt", "e"), prioritaet=0)
    buch.api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    erw = lade("minimal")
    importiert = [b for b in buch.api.alle_buchungen() if b["extern_ids"]]
    assert len(importiert) == len(erw["buchungen"]) and all(b["vorschlag"] is None for b in importiert)


# ------------------------------------------------------------ Hypothesis

_EMPF = st.sampled_from([None, "REWE Markt", "rewe", "Bäckerei Müller", "MUELLER", "Café", "Straße 1"])
_ZWECK = st.sampled_from(["", "Miete", "Kartenzahlung REWE", "Überweisung", "lohn"])
_WERTE = st.sampled_from(["rewe", "Müller", "mueller", "café", "e", "MIETE", "über", "strasse", "x"])


@st.composite
def bedingungen(draw):
    art = draw(st.sampled_from(["text", "betrag", "konto"]))
    if art == "text":
        return {"feld": draw(st.sampled_from(["empfaenger", "verwendungszweck"])),
                "operator": draw(st.sampled_from(["enthaelt", "gleich", "beginnt_mit"])), "wert": draw(_WERTE)}
    if art == "betrag":
        return {"feld": "betrag", "operator": draw(st.sampled_from(["gleich", "mindestens", "hoechstens"])),
                "wert": draw(st.sampled_from([-500, -100, 0, 100]))}
    return {"feld": "konto_id", "operator": "gleich", "wert": draw(st.sampled_from(["giro", "spar"]))}


@pytest.mark.kern
@given(buchungen=st.lists(st.tuples(_EMPF, _ZWECK, st.sampled_from([-500, -100, 0, 100, 250]),
                                    st.sampled_from(["giro", "spar"]), st.sampled_from(["offen", "cafe"])),
                          min_size=1, max_size=8),
       regeln=st.lists(st.tuples(st.lists(bedingungen(), min_size=1, max_size=3), st.sampled_from([0, 10, 10, 20]),
                                 st.booleans(), st.sampled_from(["cafe", "sonstiges", "gehalt"])),
                       min_size=1, max_size=5),
       nur_unk=st.booleans())
def test_zufaellige_regeln_gegen_orakel(api_fabrik, buchungen, regeln, nur_unk):
    buch = Buch(api_fabrik())
    ids = {"giro": buch.giro, "spar": buch.spar, "offen": buch.offen, "cafe": buch.cafe,
           "sonstiges": buch.sonstiges, "gehalt": buch.gehalt}
    bs = [(buch.buche(b, e, z, konto=ids[k], gegen=ids[g]), e, z, b, k, g) for e, z, b, k, g in buchungen]
    rs = []
    for bedg, prio, aktiv, kat in regeln:
        bedg = [{**x, "wert": ids[x["wert"]]} if x["feld"] == "konto_id" else x for x in bedg]
        rs.append(buch.regel(ids[kat], *bedg, prioritaet=prio, aktiv=aktiv))
    soll = []
    geprueft = 0
    for b, e, z, betrag, k, g in bs:
        if nur_unk and g != "offen":
            continue
        geprueft += 1
        r = orakel.regel_fuer(rs, orakel.Sicht(e, z, betrag, {ids[k]}))
        if r and r["kategorie_id"] != ids[g]:
            soll.append({"buchung_id": b["id"], "regel_id": r["id"], "kategorie_id": r["kategorie_id"]})
    erg = buch.anwenden(nur_unkategorisiert=nur_unk).daten
    assert erg == {"geprueft": geprueft, "anzahl": len(soll), "trocken": False, "aenderungen": soll}
    nach = {a["buchung_id"]: a for a in soll}
    for b, *_rest in bs:
        neu = buch.api.buchung_lesen(b["id"])
        if b["id"] in nach:
            assert neu["kategorie_id"] == nach[b["id"]]["kategorie_id"]
            assert neu["vorschlag"]["regel_id"] == nach[b["id"]]["regel_id"]
            assert neu["vorschlag"]["vorher_konto_id"] == b["splits"][1]["konto_id"]
        else:
            assert neu["splits"] == b["splits"] and neu["vorschlag"] is None
        assert sum(s["betrag"] for s in neu["splits"]) == 0
