"""M3: Konten und Kategorien mit Buchungen löschen (spec/api/loeschen.md, E-060 bis E-064).

Erwartungen: unabhängiges Orakel ``tests/hilfen/loeschen_orakel`` auf
REST-Momentaufnahmen sowie von Hand gerechnete Beispiele.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from generator.iban import fiktive_iban
from tests.hilfen import loeschen_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.vertrag import ohne

PFAD = "/api/konten/{}/loeschen"
UNK = orakel.UNKATEGORISIERT
VARIANTEN = ("loeschen", "elternkonto", "unkategorisiert")


# ----------------------------------------------------------------- Hilfen
def loeschen(api, kid: int, buchungen: str, konflikte: str = "loeschen", erwartet=200, **felder):
    body = {"buchungen": buchungen, "konflikte": konflikte, **felder}
    return api.post(PFAD.format(kid), json=body, erwartet=erwartet)


def regeln(api) -> list[dict]:
    return api.get("/api/regeln", erwartet=200).daten


def bestand(api) -> dict:
    """Vergleichbarer Buchbestand aus M1/M2-Endpunkten."""
    z = api.zustand()
    z["regeln"] = regeln(api)
    return z


def unk(api) -> dict | None:
    ks = [k for k in api.konten() if k["extern_id"] == UNK]
    assert len(ks) <= 1
    return ks[0] if ks else None


def nach_id(liste: list[dict]) -> dict[int, dict]:
    return {x["id"]: x for x in liste}


def salden(api) -> dict[int, int]:
    return {k["konto_id"]: k["saldo"] for k in api.uebersicht()["konten"]}


def pruefe_invarianten(api) -> None:
    for b in api.alle_buchungen():
        assert len(b["splits"]) >= 2, b
        assert sum(s["betrag"] for s in b["splits"]) == 0, b
    assert sum(salden(api).values()) == 0


def ohne_lauf(ergebnis: dict) -> dict:
    return ohne(ergebnis, "trocken", "aenderung_id")  # E-124: spätere optionale Felder erlaubt


def pruefe_gegen_orakel(api, vorher: dict, erw: dict, ergebnis: dict, *, trocken: bool = False) -> int | None:
    """Vergleicht Antwort und Bestand mit dem Orakel. Rückgabe: ID eines neu angelegten „Unkategorisiert“."""
    alt_ids = {k["id"] for k in vorher["konten"]}
    neu_id = None
    e = erw["ergebnis"]
    if e["ziel_konto_id"] == orakel.NEU:
        if trocken:
            assert ergebnis["ziel_konto_id"] is None, "Probelauf: Unkategorisiert existiert noch nicht → null"
            assert unk(api) is None, "Probelauf darf „Unkategorisiert“ nicht anlegen"
            e = {**e, "ziel_konto_id": None}
        else:
            neu = unk(api)
            assert neu is not None, "„Unkategorisiert“ muss angelegt werden"
            neu_id = neu["id"]
            assert neu_id not in alt_ids and ergebnis["ziel_konto_id"] == neu_id
            assert (neu["name"], neu["art"], neu["eltern_id"], neu["iban"]) == (
                "Unkategorisiert", "eigenkapital", None, None)
            e = orakel.ersetze_neu(e, neu_id)
    assert ohne_lauf(ergebnis) == e
    assert ergebnis["trocken"] is trocken
    if trocken:
        assert ergebnis["aenderung_id"] is None
    if trocken:
        assert bestand(api) == vorher, "Probelauf hat den Bestand verändert"
        return None

    erw_b = orakel.ersetze_neu(erw["buchungen"], neu_id) if neu_id else erw["buchungen"]
    # Konten: genau die erwarteten, nur eltern_id darf sich ändern
    konten = nach_id(api.konten())
    if neu_id:
        konten.pop(neu_id)
    assert {i: k["eltern_id"] for i, k in konten.items()} == erw["konten"]
    vorher_k = nach_id(vorher["konten"])
    for i, k in konten.items():
        assert {**k, "eltern_id": None} == {**vorher_k[i], "eltern_id": None}, f"Konto {i} verändert"
    # Buchungen
    ist = nach_id(api.alle_buchungen())
    assert set(ist) == set(erw_b), "falsche Menge verbleibender Buchungen"
    for bid, b in erw_b.items():
        assert orakel.buchung_kern(ist[bid]) == orakel.buchung_kern(b), f"Buchung {bid}"
    # Regeln
    assert nach_id(regeln(api)) == (orakel.ersetze_neu(erw["regeln"], neu_id) if neu_id else erw["regeln"])
    # Salden unabhängig aus den erwarteten Splits
    erw_saldo: dict[int, int] = {i: 0 for i in konten}
    if neu_id:
        erw_saldo[neu_id] = 0
    for b in erw_b.values():
        for s in b["splits"]:
            erw_saldo[s["konto_id"]] += s["betrag"]
    assert salden(api) == erw_saldo
    pruefe_invarianten(api)
    return neu_id


class Buch:
    """Kleines Buch: Giro mit Unterkonto, Spar, Kategorienbaum Haushalt > Drogerie > Kosmetik."""

    def __init__(self, api) -> None:
        self.api = api
        self.giro = api.konto("Giro", iban=fiktive_iban(6101))["id"]
        self.unter = api.konto("Giro Unterkonto", eltern_id=self.giro)["id"]
        self.spar = api.konto("Spar", "sparkonto", iban=fiktive_iban(6102))["id"]
        self.haushalt = api.konto("Haushalt", "aufwand")["id"]
        self.drogerie = api.konto("Drogerie", "aufwand", eltern_id=self.haushalt)["id"]
        self.kosmetik = api.konto("Kosmetik", "aufwand", eltern_id=self.drogerie)["id"]
        self.lebensmittel = api.konto("Lebensmittel", "aufwand")["id"]
        self.gehalt = api.konto("Gehalt", "ertrag")["id"]

    def buche(self, *splits, datum="2024-03-01", **felder) -> dict:
        return self.api.buchung(datum, list(splits), **felder)

    def abgleichen(self, bid: int) -> None:
        self.api.patch(f"/api/buchungen/{bid}", json={"status": "abgeglichen"}, erwartet=200)


@pytest.fixture
def buch(api):
    return Buch(api)


# ------------------------------------------------- Varianten im Einzelnen
@pytest.mark.kern
def test_kategorie_unkategorisiert(buch):
    api = buch.api
    b1 = buch.buche((buch.giro, -1234), (buch.lebensmittel, 1234))
    b2 = buch.buche((buch.giro, -500), (buch.haushalt, 500))
    assert unk(api) is None
    r = loeschen(api, buch.lebensmittel, "unkategorisiert").daten
    u = unk(api)
    assert u is not None and r["ziel_konto_id"] == u["id"]
    assert r["buchungen_betroffen"] == [b1["id"]] and r["buchungen_umgebucht"] == [b1["id"]]
    assert r["buchungen_geloescht"] == [] and r["konfliktbuchungen"] == []
    neu = api.buchung_lesen(b1["id"])
    assert [(s["id"], s["konto_id"], s["betrag"]) for s in neu["splits"]] == [
        (b1["splits"][0]["id"], buch.giro, -1234), (b1["splits"][1]["id"], u["id"], 1234)]
    assert neu["kategorie_id"] is None
    assert api.buchung_lesen(b2["id"])["splits"] == b2["splits"]
    api.get(f"/api/konten/{buch.lebensmittel}", erwartet=404)
    assert salden(api)[u["id"]] == 1234


@pytest.mark.kern
def test_vorhandenes_unkategorisiert_wird_wiederverwendet(buch):
    api = buch.api
    buch.buche((buch.giro, -100), (buch.lebensmittel, 100))
    buch.buche((buch.giro, -200), (buch.gehalt, 200))
    z1 = loeschen(api, buch.lebensmittel, "unkategorisiert").daten["ziel_konto_id"]
    z2 = loeschen(api, buch.gehalt, "unkategorisiert").daten["ziel_konto_id"]
    assert z1 == z2 == unk(api)["id"]
    assert salden(api)[z1] == 300


@pytest.mark.kern
def test_elternkonto_mit_zusammenfassen(buch):
    """Beispiel aus loeschen.md 3.2: Haushalt +600 „Putzmittel“, Drogerie +400 „Seife“."""
    api = buch.api
    b = buch.buche((buch.giro, -1000), (buch.haushalt, 600, "Putzmittel"), (buch.drogerie, 400, "Seife"))
    r = loeschen(api, buch.drogerie, "elternkonto").daten
    assert r["ziel_konto_id"] == buch.haushalt
    neu = api.buchung_lesen(b["id"])
    assert [(s["id"], s["konto_id"], s["betrag"], s["memo"]) for s in neu["splits"]] == [
        (b["splits"][0]["id"], buch.giro, -1000, ""),
        (b["splits"][1]["id"], buch.haushalt, 1000, "Putzmittel / Seife")]
    assert neu["kategorie_id"] == buch.haushalt


@pytest.mark.kern
@pytest.mark.parametrize("memos, erwartet", [
    (("", "", ""), ""), (("x", "", "x"), "x"), (("", "b", "a"), "b / a"), (("a", "b", "a"), "a / b"),
])
def test_zusammenfassen_memos(buch, memos, erwartet):
    api = buch.api
    b = buch.buche((buch.drogerie, 100, memos[0]), (buch.giro, -300), (buch.haushalt, 50, memos[1]),
                   (buch.drogerie, 150, memos[2]))
    loeschen(api, buch.drogerie, "elternkonto")
    neu = api.buchung_lesen(b["id"])
    # erster Split auf dem Ziel ist der frühere Drogerie-Split an Position 0
    assert [(s["id"], s["konto_id"], s["betrag"], s["memo"]) for s in neu["splits"]] == [
        (b["splits"][0]["id"], buch.haushalt, 300, erwartet), (b["splits"][1]["id"], buch.giro, -300, "")]


@pytest.mark.kern
def test_zusammengefasster_split_mit_betrag_null_bleibt(buch):
    api = buch.api
    b = buch.buche((buch.giro, -100), (buch.haushalt, 100), (buch.drogerie, 50), (buch.lebensmittel, -50))
    loeschen(api, buch.lebensmittel, "unkategorisiert")
    loeschen(api, buch.drogerie, "unkategorisiert")
    u = unk(api)["id"]
    neu = api.buchung_lesen(b["id"])
    assert [(s["konto_id"], s["betrag"]) for s in neu["splits"]] == [(buch.giro, -100), (buch.haushalt, 100), (u, 0)]


@pytest.mark.kern
def test_variante_loeschen(buch):
    api = buch.api
    b1 = buch.buche((buch.giro, -1000), (buch.lebensmittel, 700), (buch.haushalt, 300))
    b2 = buch.buche((buch.spar, -50), (buch.lebensmittel, 50))
    b3 = buch.buche((buch.giro, -20), (buch.haushalt, 20))
    vorher = salden(api)
    r = loeschen(api, buch.lebensmittel, "loeschen").daten
    assert r["ziel_konto_id"] is None
    assert r["buchungen_geloescht"] == r["buchungen_betroffen"] == sorted([b1["id"], b2["id"]])
    assert r["buchungen_umgebucht"] == [] and r["konfliktbuchungen"] == []
    for b in (b1, b2):
        api.get(f"/api/buchungen/{b['id']}", erwartet=404)
    assert api.buchung_lesen(b3["id"])["splits"] == b3["splits"]
    nachher = salden(api)
    assert nachher[buch.giro] == vorher[buch.giro] + 1000
    assert nachher[buch.spar] == vorher[buch.spar] + 50
    assert nachher[buch.haushalt] == vorher[buch.haushalt] - 300
    assert buch.lebensmittel not in nachher
    assert unk(api) is None, "Variante loeschen legt kein „Unkategorisiert“ an"


@pytest.mark.kern
def test_unbenutztes_konto(buch):
    api = buch.api
    r = loeschen(api, buch.lebensmittel, "unkategorisiert", "behalten").daten
    assert r["buchungen_betroffen"] == [] and r["unterkonten"] == []
    api.get(f"/api/konten/{buch.lebensmittel}", erwartet=404)


# ---------------------------------------------------------- Unterkonten
@pytest.mark.kern
@pytest.mark.parametrize("variante", VARIANTEN)
def test_unterkonten_ruecken_nach_oben(buch, variante):
    api = buch.api
    if variante == "elternkonto":
        r = loeschen(api, buch.drogerie, variante).daten
        assert api.get(f"/api/konten/{buch.kosmetik}", erwartet=200).daten["eltern_id"] == buch.haushalt
    else:
        r = loeschen(api, buch.haushalt, variante).daten
        assert api.get(f"/api/konten/{buch.drogerie}", erwartet=200).daten["eltern_id"] is None
        assert api.get(f"/api/konten/{buch.kosmetik}", erwartet=200).daten["eltern_id"] == buch.drogerie
        assert r["unterkonten"] == [buch.drogerie]


@pytest.mark.kern
def test_elternkonto_saldo_gesamt_bleibt(buch):
    api = buch.api
    buch.buche((buch.giro, -100), (buch.kosmetik, 100))
    buch.buche((buch.giro, -200), (buch.drogerie, 200))
    buch.buche((buch.giro, -300), (buch.haushalt, 300))
    vor = {k["konto_id"]: k for k in api.uebersicht()["konten"]}
    loeschen(api, buch.drogerie, "elternkonto")
    nach = {k["konto_id"]: k for k in api.uebersicht()["konten"]}
    assert nach[buch.haushalt]["saldo_gesamt"] == vor[buch.haushalt]["saldo_gesamt"] == 600
    assert nach[buch.haushalt]["saldo"] == 500
    assert nach[buch.kosmetik]["eltern_id"] == buch.haushalt


# ------------------------------------------------------- Konfliktbuchungen
@pytest.mark.kern
@pytest.mark.parametrize("konflikte", ["loeschen", "behalten"])
def test_umbuchung_zweimal_unkategorisiert(buch, konflikte):
    """Auftrag: Buchung mit Quelle und Ziel „Unkategorisiert“ nach zwei Löschvorgängen."""
    api = buch.api
    um = buch.buche((buch.giro, -10000, "an Spar"), (buch.spar, 10000, "von Giro"))
    andere = buch.buche((buch.spar, -50), (buch.lebensmittel, 50))
    r1 = loeschen(api, buch.spar, "unkategorisiert", konflikte).daten
    assert r1["konfliktbuchungen"] == []
    u = r1["ziel_konto_id"]
    r2 = loeschen(api, buch.giro, "unkategorisiert", konflikte).daten
    assert r2["konfliktbuchungen"] == [um["id"]]
    assert r2["buchungen_betroffen"] == [um["id"]]
    if konflikte == "loeschen":
        assert r2["buchungen_geloescht"] == [um["id"]] and r2["buchungen_umgebucht"] == []
        api.get(f"/api/buchungen/{um['id']}", erwartet=404)
    else:
        assert r2["buchungen_geloescht"] == [] and r2["buchungen_umgebucht"] == [um["id"]]
        neu = api.buchung_lesen(um["id"])
        assert [(s["id"], s["konto_id"], s["betrag"], s["memo"]) for s in neu["splits"]] == [
            (um["splits"][0]["id"], u, -10000, "an Spar"), (um["splits"][1]["id"], u, 10000, "von Giro")]
        assert neu["kategorie_id"] is None and neu["vorschlag"] is None
    # die Buchung Spar/Lebensmittel ist keine Konfliktbuchung
    assert [s["konto_id"] for s in api.buchung_lesen(andere["id"])["splits"]] == [u, buch.lebensmittel]
    assert salden(api)[u] == -50
    pruefe_invarianten(api)


@pytest.mark.kern
@pytest.mark.parametrize("konflikte", ["loeschen", "behalten"])
def test_konflikt_unterkonto_und_elternkonto(buch, konflikte):
    api = buch.api
    b = buch.buche((buch.giro, -700), (buch.unter, 700))
    andere = buch.buche((buch.unter, -100), (buch.lebensmittel, 100))
    r = loeschen(api, buch.unter, "elternkonto", konflikte).daten
    assert r["konfliktbuchungen"] == [b["id"]]
    assert r["buchungen_betroffen"] == sorted([b["id"], andere["id"]])
    if konflikte == "loeschen":
        assert r["buchungen_geloescht"] == [b["id"]]
        api.get(f"/api/buchungen/{b['id']}", erwartet=404)
    else:
        assert r["buchungen_umgebucht"] == sorted([b["id"], andere["id"]])
        assert [(s["konto_id"], s["betrag"]) for s in api.buchung_lesen(b["id"])["splits"]] == [
            (buch.giro, -700), (buch.giro, 700)]
    assert salden(api)[buch.giro] == -100


@pytest.mark.kern
def test_konflikt_mit_mehreren_splits(buch):
    """Drei Splits, alle danach auf demselben Konto: Konflikt, kein Zusammenfassen beim Behalten."""
    api = buch.api
    b = buch.buche((buch.drogerie, 30), (buch.haushalt, -50), (buch.drogerie, 20))
    r = loeschen(api, buch.drogerie, "elternkonto", "behalten").daten
    assert r["konfliktbuchungen"] == [b["id"]]
    assert [(s["id"], s["konto_id"], s["betrag"]) for s in api.buchung_lesen(b["id"])["splits"]] == [
        (s["id"], buch.haushalt, s["betrag"]) for s in b["splits"]]


# ---------------------------------------------------------------- Fehler
@pytest.mark.kern
def test_wurzelkonto_ohne_elternkonto(buch):
    api = buch.api
    buch.buche((buch.giro, -1), (buch.lebensmittel, 1))
    vorher = bestand(api)
    r = loeschen(api, buch.lebensmittel, "elternkonto", erwartet=422)
    assert fehlercode(r) == "kein_elternkonto"
    r = loeschen(api, buch.lebensmittel, "elternkonto", trocken=True, erwartet=422)
    assert fehlercode(r) == "kein_elternkonto"
    assert bestand(api) == vorher


@pytest.mark.kern
def test_unkategorisiert_nach_unkategorisiert(buch):
    api = buch.api
    buch.buche((buch.giro, -1), (buch.lebensmittel, 1))
    u = loeschen(api, buch.lebensmittel, "unkategorisiert").daten["ziel_konto_id"]
    vorher = bestand(api)
    r = loeschen(api, u, "unkategorisiert", erwartet=422)
    assert fehlercode(r) == "ziel_ungueltig"
    assert bestand(api) == vorher
    # mit „loeschen“ ist auch „Unkategorisiert“ selbst löschbar
    loeschen(api, u, "loeschen")
    assert unk(api) is None


@pytest.mark.kern
def test_unbekanntes_konto(buch):
    r = loeschen(buch.api, 999_999, "loeschen", erwartet=404)
    assert fehlercode(r) == "nicht_gefunden"


@pytest.mark.kern
@pytest.mark.parametrize("body", [
    {"buchungen": "loeschen"},
    {"konflikte": "loeschen"},
    {},
    {"buchungen": "alles", "konflikte": "loeschen"},
    {"buchungen": "loeschen", "konflikte": "egal"},
    {"buchungen": "loeschen", "konflikte": "loeschen", "trocken": "ja"},
    {"buchungen": "loeschen", "konflikte": "loeschen", "unterkonten": "loeschen"},
    {"buchungen": None, "konflikte": "loeschen"},
])
def test_validierung_ohne_vorgabe(buch, body):
    """E-061: ohne ausdrückliche Wahl wird nichts gelöscht."""
    api = buch.api
    buch.buche((buch.giro, -1), (buch.lebensmittel, 1))
    vorher = bestand(api)
    r = api.post(PFAD.format(buch.lebensmittel), json=body, erwartet=422)
    assert fehlercode(r) == "validierung"
    assert bestand(api) == vorher


@pytest.mark.kern
def test_delete_bleibt_unveraendert(buch):
    """E-029: DELETE löscht weiterhin nur unbenutzte Konten."""
    api = buch.api
    buch.buche((buch.giro, -1), (buch.lebensmittel, 1))
    assert fehlercode(api.delete(f"/api/konten/{buch.lebensmittel}", erwartet=409)) == "konto_in_verwendung"
    assert fehlercode(api.delete(f"/api/konten/{buch.haushalt}", erwartet=409)) == "konto_in_verwendung"


# ---------------------------------------------------- Gesperrte Buchungen
@pytest.mark.kern
@pytest.mark.parametrize("variante", VARIANTEN)
def test_abgeglichene_nur_mit_bestaetigung(buch, variante):
    api = buch.api
    b1 = buch.buche((buch.giro, -100), (buch.drogerie, 100))
    b2 = buch.buche((buch.giro, -200), (buch.drogerie, 200))
    b3 = buch.buche((buch.giro, -300), (buch.drogerie, 300))
    buch.abgleichen(b3["id"])
    buch.abgleichen(b1["id"])
    vorher = bestand(api)
    r = loeschen(api, buch.drogerie, variante, erwartet=409)
    assert fehlercode(r) == "buchung_gesperrt"
    assert r.json()["fehler"]["details"]["buchung_ids"] == sorted([b1["id"], b3["id"]])
    assert bestand(api) == vorher
    t = loeschen(api, buch.drogerie, variante, trocken=True).daten
    assert t["gesperrt"] == sorted([b1["id"], b3["id"]])
    assert bestand(api) == vorher
    r = loeschen(api, buch.drogerie, variante, gesperrte_einbeziehen=True).daten
    assert r["gesperrt"] == sorted([b1["id"], b3["id"]])
    if variante == "loeschen":
        assert r["buchungen_geloescht"] == sorted([b1["id"], b2["id"], b3["id"]])
    else:
        assert api.buchung_lesen(b1["id"])["status"] == "abgeglichen"
        assert api.buchung_lesen(b2["id"])["status"] == "bestaetigt"
        assert api.buchung_lesen(b3["id"])["splits"][1]["konto_id"] == r["ziel_konto_id"]


@pytest.mark.kern
def test_gesperrte_ausserhalb_bleiben_unberuehrt(buch):
    api = buch.api
    b = buch.buche((buch.giro, -100), (buch.haushalt, 100))
    buch.abgleichen(b["id"])
    buch.buche((buch.giro, -5), (buch.lebensmittel, 5))
    r = loeschen(api, buch.lebensmittel, "loeschen").daten
    assert r["gesperrt"] == []
    assert api.buchung_lesen(b["id"])["status"] == "abgeglichen"


# --------------------------------------------------------------- Probelauf
@pytest.mark.kern
@pytest.mark.parametrize("variante", VARIANTEN)
@pytest.mark.parametrize("konflikte", ["loeschen", "behalten"])
def test_probelauf_gleich_echtem_lauf(buch, variante, konflikte):
    api = buch.api
    buch.buche((buch.drogerie, 100), (buch.haushalt, -100))
    buch.buche((buch.giro, -40), (buch.drogerie, 30, "a"), (buch.haushalt, 10, "b"))
    buch.buche((buch.giro, -10), (buch.kosmetik, 10))
    vorher = bestand(api)
    t = loeschen(api, buch.drogerie, variante, konflikte, trocken=True).daten
    assert t["trocken"] is True and t["aenderung_id"] is None
    assert bestand(api) == vorher
    if variante == "unkategorisiert":
        assert t["ziel_konto_id"] is None and unk(api) is None
    r = loeschen(api, buch.drogerie, variante, konflikte).daten
    assert r["trocken"] is False
    vergleich = ohne_lauf(t) | {"ziel_konto_id": r["ziel_konto_id"]}
    assert vergleich == ohne_lauf(r)


# ----------------------------------------------------- Vorschläge, Regeln
def regel(api, kategorie: int, *bedingungen, name: str = "R") -> dict:
    return api.post("/api/regeln", json={"name": name, "kategorie_id": kategorie,
                                         "bedingungen": list(bedingungen)}, erwartet=201).daten


@pytest.mark.kern
@pytest.mark.parametrize("variante", ["elternkonto", "unkategorisiert"])
def test_vorschlag_entfaellt_bei_umgebuchten(buch, variante):
    api = buch.api
    offen = api.konto("Offen", "eigenkapital")["id"]
    b1 = buch.buche((buch.giro, -100), (offen, 100), verwendungszweck="Seife")
    b2 = buch.buche((buch.spar, -100), (offen, 100), verwendungszweck="Seife")
    regel(api, buch.kosmetik, {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Seife"})
    api.post("/api/regeln/anwenden", json={"nur_unkategorisiert": False}, erwartet=200)
    assert api.buchung_lesen(b1["id"])["vorschlag"] is not None
    # Konto Giro (Bestandskonto) löschen: b1 umgebucht → Vorschlag weg; b2 behält ihn
    if variante == "elternkonto":
        api.patch(f"/api/konten/{buch.spar}", json={"eltern_id": buch.giro}, erwartet=200)
        loeschen(api, buch.spar, "elternkonto")
        assert api.buchung_lesen(b2["id"])["vorschlag"] is None
        assert api.buchung_lesen(b1["id"])["vorschlag"] is not None
    else:
        loeschen(api, buch.giro, "unkategorisiert", gesperrte_einbeziehen=True)
        neu = api.buchung_lesen(b1["id"])
        assert neu["vorschlag"] is None and neu["kategorie_id"] is None
        assert api.buchung_lesen(b2["id"])["vorschlag"] is not None
    pruefe_invarianten(api)


@pytest.mark.kern
def test_regeln_elternkonto_umgestellt(buch):
    api = buch.api
    r1 = regel(api, buch.kosmetik, {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Creme"},
               name="Creme")
    r2 = regel(api, buch.lebensmittel, {"feld": "konto_id", "operator": "gleich", "wert": buch.unter},
               {"feld": "betrag", "operator": "hoechstens", "wert": -1}, name="Unterkonto")
    r3 = regel(api, buch.haushalt, {"feld": "empfaenger", "operator": "enthaelt", "wert": "Markt"}, name="Fremd")
    e = loeschen(api, buch.kosmetik, "elternkonto").daten
    assert e["regeln_geaendert"] == [r1["id"]] and e["regeln_geloescht"] == []
    assert api.get(f"/api/regeln/{r1['id']}", erwartet=200).daten == {**r1, "kategorie_id": buch.drogerie}
    e = loeschen(api, buch.unter, "elternkonto").daten
    assert e["regeln_geaendert"] == [r2["id"]]
    neu = api.get(f"/api/regeln/{r2['id']}", erwartet=200).daten
    assert neu["bedingungen"] == [{"feld": "konto_id", "operator": "gleich", "wert": buch.giro},
                                  {"feld": "betrag", "operator": "hoechstens", "wert": -1}]
    # ab M30 nennt der übersetzte Ausdruck das Konto beim Namen und ändert sich mit (E-271)
    assert ({k: v for k, v in neu.items() if k not in ("bedingungen", "ausdruck")}
            == {k: v for k, v in r2.items() if k not in ("bedingungen", "ausdruck")})
    assert api.get(f"/api/regeln/{r3['id']}", erwartet=200).daten == r3


@pytest.mark.kern
@pytest.mark.parametrize("variante", ["loeschen", "unkategorisiert"])
def test_regeln_geloescht(buch, variante):
    api = buch.api
    offen = api.konto("Offen", "eigenkapital")["id"]
    b = buch.buche((buch.spar, -5), (offen, 5), verwendungszweck="Brot")
    r1 = regel(api, buch.lebensmittel, {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Brot"})
    r2 = regel(api, buch.haushalt, {"feld": "konto_id", "operator": "gleich", "wert": buch.giro})
    r3 = regel(api, buch.haushalt, {"feld": "konto_id", "operator": "gleich", "wert": buch.spar})
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    assert api.buchung_lesen(b["id"])["vorschlag"]["regel_id"] == r1["id"]
    e = loeschen(api, buch.giro, variante).daten
    assert e["regeln_geloescht"] == [r2["id"]]
    e = loeschen(api, buch.lebensmittel, variante, gesperrte_einbeziehen=True).daten
    assert e["regeln_geloescht"] == [r1["id"]] and e["buchungen_betroffen"] == [b["id"]]
    assert [r["id"] for r in regeln(api)] == [r3["id"]]


@pytest.mark.kern
def test_vorschlag_regel_id_null_bei_unbetroffener_buchung(buch):
    """Regel auf ein Bestandskonto wird gelöscht; Vorschläge anderer Buchungen verlieren nur regel_id."""
    api = buch.api
    offen = api.konto("Offen", "eigenkapital")["id"]
    b = buch.buche((buch.spar, -5), (offen, 5))
    r = regel(api, buch.lebensmittel, {"feld": "konto_id", "operator": "gleich", "wert": buch.spar},
              {"feld": "betrag", "operator": "gleich", "wert": -5})
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    andere = api.konto("Anderes Giro")["id"]
    regel(api, buch.haushalt, {"feld": "konto_id", "operator": "gleich", "wert": andere})
    api.patch(f"/api/regeln/{r['id']}", json={"bedingungen": [
        {"feld": "konto_id", "operator": "gleich", "wert": andere}]}, erwartet=200)
    loeschen(api, andere, "loeschen")
    v = api.buchung_lesen(b["id"])["vorschlag"]
    assert v is not None and v["regel_id"] is None and v["kategorie_id"] == buch.lebensmittel


# ------------------------------------------------ Eigenschaft: Orakel
KONTEN = [  # (Name, Art, Elternindex)
    ("G1", "girokonto", None), ("G2", "girokonto", 0), ("S1", "sparkonto", None),
    ("H", "aufwand", None), ("D", "aufwand", 3), ("K", "aufwand", 4), ("L", "aufwand", None),
    ("E", "ertrag", None),
]

# Kontengruppen, innerhalb derer Buchungen leicht zu Konfliktbuchungen werden (Kind/Eltern, zwei Wurzeln)
GRUPPEN = [(0, 1), (3, 4), (4, 5), (3, 4, 5), (0, 2), (6, 7)]
MEMO_ST = st.sampled_from(["", "a", "b"])


def _buchung_aus(konten: list[int]):
    konto = st.sampled_from(konten)
    split = st.tuples(konto, st.integers(-5000, 5000), MEMO_ST)
    return st.tuples(st.lists(split, min_size=1, max_size=3), konto, st.booleans())


buchung_st = st.one_of(_buchung_aus(list(range(len(KONTEN)))),
                       st.sampled_from(GRUPPEN).flatmap(lambda g: _buchung_aus(list(g))))
schritt_st = st.tuples(st.integers(0, len(KONTEN)), st.sampled_from(VARIANTEN),
                       st.sampled_from(["loeschen", "behalten"]), st.booleans())


@pytest.mark.kern
@given(st.lists(buchung_st, max_size=10), st.lists(schritt_st, min_size=1, max_size=3))
def test_loeschen_gegen_orakel(api_fabrik, buchungen, schritte):
    """Zufällige Bücher und Folgen von Löschvorgängen; Index len(KONTEN) = „Unkategorisiert“."""
    api = api_fabrik()
    ids: list[int] = []
    for name, art, eltern in KONTEN:
        ids.append(api.konto(name, art, **({"eltern_id": ids[eltern]} if eltern is not None else {}))["id"])
    for splits, gegen, abgeglichen in buchungen:
        liste = [(ids[i], b, m) for i, b, m in splits]
        liste.append((ids[gegen], -sum(b for _, b, _ in splits)))
        b = api.buchung("2024-05-01", liste)
        if abgeglichen:
            api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200)
    regel(api, ids[5], {"feld": "konto_id", "operator": "gleich", "wert": ids[1]})
    regel(api, ids[6], {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "x"})

    for idx, variante, konflikte, einbeziehen in schritte:
        vorher = bestand(api)
        if idx == len(KONTEN):
            u = unk(api)
            kid = u["id"] if u else 999_999
        else:
            kid = ids[idx]
        for trocken in (True, False):
            f = orakel.fehler(vorher["konten"], vorher["buchungen"], kid, variante, trocken=trocken,
                              gesperrte_einbeziehen=einbeziehen)
            body = {"buchungen": variante, "konflikte": konflikte, "trocken": trocken,
                    "gesperrte_einbeziehen": einbeziehen}
            r = api.post(PFAD.format(kid), json=body, erwartet=f[0] if f else 200)
            if f:
                assert fehlercode(r) == f[1]
                assert bestand(api) == vorher
                continue
            erw = orakel.berechne(vorher["konten"], vorher["buchungen"], kid, variante, konflikte,
                                  regeln=vorher["regeln"])
            pruefe_gegen_orakel(api, vorher, erw, r.daten, trocken=trocken)


# --------------------------------------- M3: Standardkategorie, Abstimmung
@pytest.mark.kern
@pytest.mark.parametrize("variante, erwartet", [("elternkonto", "eltern"), ("unkategorisiert", None),
                                                 ("loeschen", None)])
def test_standardkategorie(buch, variante, erwartet):
    """Ab M32 gibt es keine Standardkategorie (sammel3.md 2.1, E-307): Löschen ändert keine Empfänger."""
    api = buch.api
    e1 = api.post("/api/empfaenger", json={"name": "Drogeriemarkt"}, erwartet=201).daten
    e2 = api.post("/api/empfaenger", json={"name": "Bäcker"}, erwartet=201).daten
    buch.buche((buch.giro, -10), (buch.kosmetik, 10))
    r = loeschen(api, buch.kosmetik, variante).daten
    assert r["empfaenger_geaendert"] == []
    for e in (e1, e2):
        assert api.get(f"/api/empfaenger/{e['id']}", erwartet=200).daten == e


def abstimmen(api, konto: int, stichtag: str, saldo: int) -> dict:
    r = api.post("/api/abstimmungen", json={"konto_id": konto, "stichtag": stichtag, "saldo": saldo},
                 erwartet=200).daten
    assert r["abgestimmt"] is True, r
    return r["abstimmung"]


@pytest.mark.kern
@pytest.mark.parametrize("variante", VARIANTEN)
def test_abstimmungen_des_kontos_entfallen(buch, variante):
    api = buch.api
    b1 = buch.buche((buch.giro, 1000), (buch.unter, -1000), datum="2024-01-10")
    b2 = buch.buche((buch.unter, -50), (buch.lebensmittel, 50), datum="2024-01-20")
    a_unter = abstimmen(api, buch.unter, "2024-01-31", -1050)
    a_giro = abstimmen(api, buch.giro, "2024-01-31", 1000)
    assert api.buchung_lesen(b2["id"])["abgestimmt"] is True
    vorher = bestand(api)
    r = loeschen(api, buch.unter, variante, "behalten", erwartet=409)
    assert r.json()["fehler"]["details"]["buchung_ids"] == sorted([b1["id"], b2["id"]])
    assert bestand(api) == vorher
    r = loeschen(api, buch.unter, variante, "behalten", gesperrte_einbeziehen=True).daten
    assert r["abstimmungen_geloescht"] == [a_unter["id"]]
    assert r["gesperrt"] == sorted([b1["id"], b2["id"]])
    api.get(f"/api/abstimmungen/{a_unter['id']}", erwartet=404)
    assert api.get(f"/api/abstimmungen/{a_giro['id']}", erwartet=200).daten == a_giro
    if variante != "loeschen":
        n1 = api.buchung_lesen(b1["id"])
        # Marke der Giro-Abstimmung bleibt, die der gelöschten Abstimmung entfällt
        assert [s["abstimmung_id"] for s in n1["splits"]] == [a_giro["id"], None]
        n2 = api.buchung_lesen(b2["id"])
        assert [s["abstimmung_id"] for s in n2["splits"]] == [None, None]
        assert n2["abgestimmt"] is False
        if variante == "elternkonto":
            # b1 wird Konflikt (Giro ↔ Giro); behalten ohne Zusammenfassen
            assert r["konfliktbuchungen"] == [b1["id"]]
            assert [(s["konto_id"], s["betrag"]) for s in n1["splits"]] == [(buch.giro, 1000), (buch.giro, -1000)]


@pytest.mark.kern
def test_abgestimmter_split_wird_nicht_zusammengefasst(buch):
    api = buch.api
    b = buch.buche((buch.giro, -100, "x"), (buch.unter, 60, "y"), (buch.lebensmittel, 40))
    a = abstimmen(api, buch.giro, "2024-03-31", -100)
    r = loeschen(api, buch.unter, "elternkonto", gesperrte_einbeziehen=True).daten
    assert r["konfliktbuchungen"] == []
    neu = api.buchung_lesen(b["id"])
    assert [(s["konto_id"], s["betrag"], s["memo"], s["abstimmung_id"]) for s in neu["splits"]] == [
        (buch.giro, -100, "x", a["id"]), (buch.giro, 60, "y", None), (buch.lebensmittel, 40, "", None)]


# ---------------------------------------------------------- Protokoll
def aenderungen(api, **params) -> list[dict]:
    return api.get("/api/aenderungen", params=params or None, erwartet=200).daten["eintraege"]


def m3_bestand(api) -> dict:
    z = bestand(api)
    z["abstimmungen"] = api.get("/api/abstimmungen", erwartet=200).daten
    return z


@pytest.mark.kern
@pytest.mark.parametrize("variante, konflikte", [
    ("loeschen", "loeschen"), ("elternkonto", "behalten"), ("elternkonto", "loeschen"),
    ("unkategorisiert", "behalten"), ("unkategorisiert", "loeschen"),
])
def test_eine_aenderung_und_rueckgaengig(buch, variante, konflikte):
    api = buch.api
    buch.buche((buch.giro, -100), (buch.unter, 100, "u"))
    buch.buche((buch.unter, -30), (buch.drogerie, 30))
    b = buch.buche((buch.unter, -20), (buch.kosmetik, 20))
    buch.abgleichen(b["id"])
    sub = api.konto("Unter-Unter", eltern_id=buch.unter)["id"]
    buch.buche((sub, -5), (buch.lebensmittel, 5))
    regel(api, buch.lebensmittel, {"feld": "konto_id", "operator": "gleich", "wert": buch.unter})
    api.post("/api/empfaenger", json={"name": "Laden"}, erwartet=201)   # ab M32 ohne Standardkategorie (E-307)
    abstimmen(api, buch.unter, "2024-03-31", 50)
    vorher = m3_bestand(api)
    anzahl = len(aenderungen(api, pro_seite=500))

    loeschen(api, buch.unter, variante, konflikte, trocken=True)
    assert len(aenderungen(api, pro_seite=500)) == anzahl, "Probelauf erzeugt keine Änderung"
    r = loeschen(api, buch.unter, variante, konflikte, gesperrte_einbeziehen=True).daten
    alle = aenderungen(api, pro_seite=500)
    assert len(alle) == anzahl + 1
    a = alle[0]
    assert a["id"] == r["aenderung_id"]
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "konto_loeschen_mit_buchungen", None)
    eintrag = {(e["objekt"], e["objekt_id"]): e for e in a["eintraege"]}
    assert eintrag[("konto", buch.unter)]["art"] == "geloescht"
    assert eintrag[("konto", sub)]["nachher"]["eltern_id"] == buch.giro

    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert m3_bestand(api) == vorher, "Rückgängig stellt den Zustand vor dem Löschen nicht exakt her"
    pruefe_invarianten(api)
