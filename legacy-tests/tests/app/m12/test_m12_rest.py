"""M12: POST /api/buchungen/mehrfach/aendern – freie Statusänderung, Massenänderungen, Sperren, Protokoll
(datenmodell.md 17, E-168 bis E-170).

Alle Erwartungen werden im Test aus den angelegten Daten berechnet.
"""

from __future__ import annotations

import itertools
import random

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, bestand, letzte_aenderung_id, pruefe_eintraege, \
    pruefe_rueckgaengig_rundreise

STATUS = ["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"]
PFAD = "/api/buchungen/mehrfach/aendern"


def _aendern(api, ids, erwartet=200, **felder):
    return api.post(PFAD, json={"buchung_ids": ids, **felder}, erwartet=erwartet)


def _details(r) -> list[int]:
    return r.daten["fehler"]["details"]["buchung_ids"]


@pytest.fixture
def k(api):
    return {
        "giro": api.konto("Giro", "girokonto")["id"],
        "spar": api.konto("Spar", "sparkonto")["id"],
        "leb": api.konto("Lebensmittel", "aufwand")["id"],
        "cafe": api.konto("Café", "aufwand")["id"],
        "offen": api.konto("Unkategorisiert", "eigenkapital")["id"],
        "e1": api.empfaenger("Bäckerei Eins")["id"],
        "e2": api.empfaenger("Markt Zwei")["id"],
        "t": api.tag("Urlaub")["id"],
    }


def _buchung(api, k, status="bestaetigt", datum="2024-03-01", betrag=500, **felder):
    if status == "abgeglichen":
        b = api.buchung(datum, [(k["giro"], -betrag, "Giro-Memo"), (k["leb"], betrag, "Kat-Memo")],
                        status="bestaetigt", **felder)
        return api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200).daten
    return api.buchung(datum, [(k["giro"], -betrag, "Giro-Memo"), (k["leb"], betrag, "Kat-Memo")], status=status,
                       **felder)


def _ohne_aenderung(api, aufruf) -> None:
    vor = letzte_aenderung_id(api)
    z = bestand(api)
    aufruf()
    assert aenderungen_seit(api, vor) == [], "Anfrage ohne Wirkung bzw. mit Fehler darf keine Änderung erzeugen"
    assert bestand(api) == z


# ------------------------------------------------------------------ Status


@pytest.mark.kern
@pytest.mark.parametrize("von,nach", list(itertools.product(STATUS, STATUS)))
def test_status_jeder_uebergang(api, k, von, nach):
    """E-168: jeder Status aus jedem Status (Verlassen von abgeglichen mit entsperren)."""
    b = _buchung(api, k, von)
    extra = {"entsperren": True} if von == "abgeglichen" else {}
    r = _aendern(api, [b["id"]], status=nach, **extra).daten
    assert r == {"geaendert": [b["id"]], "anzahl": 1}
    assert api.buchung_lesen(b["id"]) == {**b, "status": nach}


@pytest.mark.kern
@pytest.mark.parametrize("nach", ["importiert", "vorlaeufig", "bestaetigt"])
def test_abgeglichen_verlassen_braucht_entsperren(api, k, nach):
    """E-169: ohne entsperren 409 bestaetigung_erforderlich; danach ist die Buchung frei bearbeitbar."""
    b = _buchung(api, k, "abgeglichen")
    for extra in ({}, {"entsperren": False}):
        r = _aendern(api, [b["id"]], 409, status=nach, **extra)
        assert fehlercode(r) == "bestaetigung_erforderlich"
        assert _details(r) == [b["id"]]
        assert api.buchung_lesen(b["id"]) == b
    _aendern(api, [b["id"]], status=nach, entsperren=True)
    # jetzt nicht mehr gesperrt: alle Bestandteile änderbar
    api.patch(f"/api/buchungen/{b['id']}", json={"datum": "2024-03-02", "verwendungszweck": "neu"}, erwartet=200)
    neu = api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": [
        {"konto_id": k["giro"], "betrag": -700, "memo": "Giro-Memo"},
        {"konto_id": k["cafe"], "betrag": 700, "memo": "Kat-Memo"}]}, erwartet=200).daten
    assert (neu["status"], neu["datum"], neu["kategorie_id"]) == (nach, "2024-03-02", k["cafe"])


def test_abgeglichen_bleibt_abgeglichen_ohne_bestaetigung(api, k):
    b = _buchung(api, k, "abgeglichen")
    _ohne_aenderung(api, lambda: _aendern(api, [b["id"]], status="abgeglichen"))


def test_entsperren_ohne_abgeglichene_buchung_ohne_wirkung(api, k):
    b = _buchung(api, k, "importiert")
    _aendern(api, [b["id"]], status="bestaetigt", entsperren=True)
    assert api.buchung_lesen(b["id"]) == {**b, "status": "bestaetigt"}


def test_patch_behaelt_die_uebergaenge(api, k):
    """E-168: PATCH bleibt unverändert (M1-Vertrag)."""
    b = _buchung(api, k, "bestaetigt")
    r = api.patch(f"/api/buchungen/{b['id']}", json={"status": "importiert"}, erwartet=409)
    assert fehlercode(r) == "status_uebergang_unzulaessig"
    b = _buchung(api, k, "abgeglichen")
    assert fehlercode(api.patch(f"/api/buchungen/{b['id']}", json={"status": "bestaetigt"},
                                erwartet=409)) == "status_uebergang_unzulaessig"


@pytest.mark.kern
def test_status_bestaetigt_vorschlag(api, k):
    """datenmodell.md 17.2: bestaetigt/abgeglichen bestätigen einen offenen Vorschlag; andere Werte nicht."""
    bids = [api.buchung("2024-02-0%d" % i, [(k["giro"], -100 * i), (k["offen"], 100 * i)], status="importiert",
                        empfaenger_id=k["e1"])["id"] for i in (1, 2, 3)]
    api.post("/api/regeln", json={"name": "Bäcker", "kategorie_id": k["cafe"],
                                  "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "bäckerei"}]},
             erwartet=201)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    vorher = {i: api.buchung_lesen(i) for i in bids}
    assert all(b["vorschlag"] is not None and b["kategorie_id"] == k["cafe"] for b in vorher.values())
    _aendern(api, [bids[0]], status="bestaetigt")
    _aendern(api, [bids[1]], status="abgeglichen")
    _aendern(api, [bids[2]], status="vorlaeufig", datum="2024-02-28", verwendungszweck="x")
    assert api.buchung_lesen(bids[0]) == {**vorher[bids[0]], "status": "bestaetigt", "vorschlag": None}
    assert api.buchung_lesen(bids[1]) == {**vorher[bids[1]], "status": "abgeglichen", "vorschlag": None}
    assert api.buchung_lesen(bids[2]) == {**vorher[bids[2]], "status": "vorlaeufig", "datum": "2024-02-28",
                                          "verwendungszweck": "x"}


def test_gleicher_status_mit_vorschlag_ohne_wirkung(api, k):
    b = api.buchung("2024-02-01", [(k["giro"], -100), (k["offen"], 100)], status="bestaetigt",
                    empfaenger_id=k["e1"])
    api.post("/api/regeln", json={"name": "Bäcker", "kategorie_id": k["cafe"],
                                  "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt", "wert": "bäckerei"}]},
             erwartet=201)
    api.post("/api/regeln/anwenden", json={}, erwartet=200)
    assert api.buchung_lesen(b["id"])["vorschlag"] is not None
    _ohne_aenderung(api, lambda: _aendern(api, [b["id"]], status="bestaetigt"))


# ------------------------------------------------------------------ Felder und Mehrfach


@pytest.mark.kern
def test_mehrere_felder_fuer_mehrere_buchungen(api, k):
    """E-170: angegebene Felder bei jeder genannten Buchung; alles andere unverändert."""
    b1 = _buchung(api, k, "importiert", datum="2024-03-01", empfaenger_id=k["e1"], verwendungszweck="alt 1",
                  tag_ids=[k["t"]])
    b2 = _buchung(api, k, "vorlaeufig", datum="2024-03-05", betrag=900)
    b3 = _buchung(api, k, "bestaetigt", datum="2024-03-09", empfaenger_id=k["e2"])
    rest = _buchung(api, k, "importiert", datum="2024-03-10", verwendungszweck="bleibt")
    r = _aendern(api, [b3["id"], b1["id"], b2["id"]], status="bestaetigt", datum="2024-04-01",
                 empfaenger_id=k["e2"], verwendungszweck="Sammelkorrektur").daten
    assert r == {"geaendert": sorted([b1["id"], b2["id"], b3["id"]]), "anzahl": 3}
    e2 = {"id": k["e2"], "name": "Markt Zwei"}
    for b in (b1, b2, b3):
        assert api.buchung_lesen(b["id"]) == {**b, "status": "bestaetigt", "datum": "2024-04-01", "empfaenger": e2,
                                              "verwendungszweck": "Sammelkorrektur"}
    assert api.buchung_lesen(rest["id"]) == rest


@pytest.mark.parametrize("feld,wert", [("datum", "2023-12-31"), ("empfaenger_id", None), ("empfaenger_id", "e2"),
                                       ("verwendungszweck", ""), ("verwendungszweck", "ä" * 10000),
                                       ("status", "vorlaeufig")])
def test_einzelnes_feld(api, k, feld, wert):
    if wert == "e2":
        wert = k["e2"]
    b1 = _buchung(api, k, "importiert", empfaenger_id=k["e1"], verwendungszweck="v1")
    b2 = _buchung(api, k, "bestaetigt", verwendungszweck="v2")
    _aendern(api, [b1["id"], b2["id"]], **{feld: wert})
    for b in (b1, b2):
        soll = dict(b)
        if feld == "empfaenger_id":
            soll["empfaenger"] = None if wert is None else {"id": wert, "name": "Markt Zwei"}
        else:
            soll[feld] = wert
        assert api.buchung_lesen(b["id"]) == soll


@pytest.mark.kern
@pytest.mark.parametrize("koerper", [
    {}, {"entsperren": True}, {"buchung_ids": [], "status": "bestaetigt"},
    {"buchung_ids": "DOPPELT", "status": "bestaetigt"}, {"status": "erledigt"}, {"datum": "2024-02-30"},
    {"datum": 20240101}, {"verwendungszweck": "x" * 10001}, {"verwendungszweck": None}, {"empfaenger_id": "1"},
    {"status": "bestaetigt", "entsperren": "ja"}, {"status": "bestaetigt", "tag_ids": []},
    {"status": "bestaetigt", "kategorie_id": 1}], ids=lambda x: ",".join(map(str, x)) or "leer")
def test_validierung(api, k, koerper):
    b = _buchung(api, k, "importiert")
    body = {"buchung_ids": [b["id"]], **koerper}
    if body["buchung_ids"] == "DOPPELT":
        body["buchung_ids"] = [b["id"], b["id"]]

    def aufruf():
        r = api.post(PFAD, json=body, erwartet=422)
        assert fehlercode(r) == "validierung"
    _ohne_aenderung(api, aufruf)


@pytest.mark.kern
def test_referenz_unbekannt(api, k):
    b = _buchung(api, k, "importiert")
    gesperrt = _buchung(api, k, "abgeglichen")

    def unbekannte_buchungen():
        r = _aendern(api, [999998, b["id"], 999997, gesperrt["id"]], 422, datum="2024-01-01")
        assert fehlercode(r) == "referenz_unbekannt"
        assert _details(r) == [999997, 999998]

    def unbekannter_empfaenger():
        r = _aendern(api, [b["id"], gesperrt["id"]], 422, empfaenger_id=999999)
        assert fehlercode(r) == "referenz_unbekannt"
    _ohne_aenderung(api, unbekannte_buchungen)
    _ohne_aenderung(api, unbekannter_empfaenger)


# ------------------------------------------------------------------ Sperren


@pytest.mark.kern
@pytest.mark.parametrize("feld", ["datum", "empfaenger_id", "verwendungszweck"])
def test_gesperrte_felder_atomar(api, k, feld):
    """datenmodell.md 17.3: abgeglichene Buchung → 409 buchung_gesperrt, auch mit entsperren; nichts geändert."""
    frei = _buchung(api, k, "importiert", empfaenger_id=k["e1"], verwendungszweck="a")
    g1 = _buchung(api, k, "abgeglichen", empfaenger_id=k["e1"], verwendungszweck="a")
    g2 = _buchung(api, k, "abgeglichen", empfaenger_id=k["e1"], verwendungszweck="a")
    wert = {"datum": "2024-05-05", "empfaenger_id": k["e2"], "verwendungszweck": "neu"}[feld]

    def aufruf(**extra):
        r = _aendern(api, [g2["id"], frei["id"], g1["id"]], 409, **{feld: wert}, **extra)
        assert fehlercode(r) == "buchung_gesperrt"
        assert _details(r) == sorted([g1["id"], g2["id"]])
    _ohne_aenderung(api, aufruf)
    _ohne_aenderung(api, lambda: aufruf(entsperren=True))
    _ohne_aenderung(api, lambda: aufruf(entsperren=True, status="bestaetigt"))


def test_gesperrt_nur_bei_tatsaechlicher_aenderung(api, k):
    """E-026: gleicher Wert an einer gesperrten Buchung ist keine Änderung."""
    frei = _buchung(api, k, "importiert", datum="2024-03-01")
    g = _buchung(api, k, "abgeglichen", datum="2024-03-01", verwendungszweck="gleich")
    _aendern(api, [frei["id"], g["id"]], datum="2024-03-01", verwendungszweck="gleich")
    assert api.buchung_lesen(frei["id"]) == {**frei, "verwendungszweck": "gleich"}
    assert api.buchung_lesen(g["id"]) == g


@pytest.mark.kern
def test_abgestimmte_buchung(api, k):
    """E-169: Status einer abgestimmten Buchung ist änderbar, die Abstimmung bleibt; übrige Felder gesperrt."""
    b = api.buchung("2024-01-05", [(k["spar"], 4200), (k["giro"], -4200)], status="bestaetigt")
    api.post("/api/abstimmungen", json={"konto_id": k["spar"], "stichtag": "2024-01-31", "saldo": 4200},
             erwartet=200)
    b = api.buchung_lesen(b["id"])
    assert b["abgestimmt"] is True, "Testvoraussetzung: Buchung abgestimmt"
    _aendern(api, [b["id"]], status="importiert")
    assert api.buchung_lesen(b["id"]) == {**b, "status": "importiert"}
    r = _aendern(api, [b["id"]], 409, verwendungszweck="neu", entsperren=True)
    assert (fehlercode(r), _details(r)) == ("buchung_gesperrt", [b["id"]])
    # abgestimmt und abgeglichen: Verlassen von abgeglichen braucht entsperren, die Abstimmung bleibt
    _aendern(api, [b["id"]], status="abgeglichen")
    r = _aendern(api, [b["id"]], 409, status="bestaetigt")
    assert fehlercode(r) == "bestaetigung_erforderlich"
    _aendern(api, [b["id"]], status="bestaetigt", entsperren=True)
    assert api.buchung_lesen(b["id"]) == {**b, "status": "bestaetigt"}


@pytest.mark.kern
def test_pruefreihenfolge(api, k):
    frei = _buchung(api, k, "importiert")
    g = _buchung(api, k, "abgeglichen")
    # 422 vor 409
    assert fehlercode(_aendern(api, [g["id"], 999999], 422, datum="2024-01-01")) == "referenz_unbekannt"
    assert fehlercode(_aendern(api, [g["id"]], 422, datum="2024-01-01", status="kaputt")) == "validierung"
    # buchung_gesperrt vor bestaetigung_erforderlich
    assert fehlercode(_aendern(api, [g["id"], frei["id"]], 409, datum="2024-01-01",
                               status="importiert")) == "buchung_gesperrt"
    assert api.buchung_lesen(g["id"]) == g and api.buchung_lesen(frei["id"]) == frei


@pytest.mark.kern
def test_bestaetigung_mehrere_atomar(api, k):
    frei = _buchung(api, k, "importiert")
    g1 = _buchung(api, k, "abgeglichen")
    g2 = _buchung(api, k, "abgeglichen")
    schon = _buchung(api, k, "bestaetigt")

    def aufruf():
        r = _aendern(api, [schon["id"], g2["id"], frei["id"], g1["id"]], 409, status="bestaetigt")
        assert fehlercode(r) == "bestaetigung_erforderlich"
        assert _details(r) == sorted([g1["id"], g2["id"]])
    _ohne_aenderung(api, aufruf)
    _aendern(api, [schon["id"], g2["id"], frei["id"], g1["id"]], status="bestaetigt", entsperren=True)
    for b in (frei, g1, g2, schon):
        assert api.buchung_lesen(b["id"]) == {**b, "status": "bestaetigt"}


# ------------------------------------------------------------------ Protokoll


@pytest.mark.kern
def test_protokoll_eine_aenderung_und_rueckgaengig(api, k):
    """Genau eine Änderung mehrfach_aendern mit Einträgen nur für geänderte Buchungen; Rückgängig in einem Schritt
    stellt auch abgeglichen wieder her (protokoll.md 4.1, 6)."""
    b1 = _buchung(api, k, "importiert", empfaenger_id=k["e1"])
    b2 = _buchung(api, k, "abgeglichen", empfaenger_id=k["e1"])
    b3 = _buchung(api, k, "vorlaeufig", empfaenger_id=k["e1"])   # bleibt unverändert
    unbeteiligt = _buchung(api, k, "importiert")
    vorher = bestand(api)
    vor = letzte_aenderung_id(api)
    _aendern(api, [b1["id"], b2["id"], b3["id"]], status="vorlaeufig", entsperren=True)
    (a,) = aenderungen_seit(api, vor)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "mehrfach_aendern", None)
    nachher = bestand(api)
    assert {e["objekt_id"] for e in a["eintraege"]} == {b1["id"], b2["id"]}
    assert nachher[("buchung", unbeteiligt["id"])] == vorher[("buchung", unbeteiligt["id"])]
    pruefe_eintraege(a, vorher, nachher)
    pruefe_rueckgaengig_rundreise(api, a, vorher, nachher)


@pytest.mark.kern
def test_ohne_wirkung_keine_aenderung(api, k):
    b = _buchung(api, k, "bestaetigt", datum="2024-03-01", empfaenger_id=k["e1"], verwendungszweck="v")
    _ohne_aenderung(api, lambda: _aendern(api, [b["id"]], status="bestaetigt", datum="2024-03-01",
                                          empfaenger_id=k["e1"], verwendungszweck="v"))


def _wert(b: dict, feld: str):
    return (b["empfaenger"] or {}).get("id") if feld == "empfaenger_id" else b[feld]


def test_zufaellige_massenaenderungen_aendern_genau_die_markierten(api, k):
    """T 14: zufällige Auswahl und Felder (fester Startwert); Invarianten bleiben, nur Markierte ändern sich."""
    zufall = random.Random(4711)
    bids = [_buchung(api, k, zufall.choice(STATUS), datum=f"2024-0{1 + i % 9}-1{i % 9}",
                     empfaenger_id=zufall.choice([None, k["e1"], k["e2"]]), betrag=100 + i)["id"]
            for i in range(12)]
    for runde in range(25):
        auswahl = zufall.sample(bids, zufall.randint(1, 6))
        felder = {}
        for f, werte in (("status", STATUS), ("datum", ["2024-02-29", "2024-12-31"]),
                         ("empfaenger_id", [None, k["e1"], k["e2"]]), ("verwendungszweck", ["", "Runde"])):
            if zufall.random() < 0.4:
                felder[f] = zufall.choice(werte)
        if not felder:
            felder["status"] = zufall.choice(STATUS)
        vorher = {b["id"]: b for b in api.alle_buchungen()}
        r = api.post(PFAD, json={"buchung_ids": auswahl, "entsperren": True, **felder})
        gesperrt = sorted(i for i in auswahl if vorher[i]["status"] == "abgeglichen"
                          and any(_wert(vorher[i], f) != v for f, v in felder.items() if f != "status"))
        nachher = {b["id"]: b for b in api.alle_buchungen()}
        if gesperrt:
            assert r.status_code == 409 and fehlercode(r) == "buchung_gesperrt", (runde, r.text)
            assert _details(r) == gesperrt
            assert nachher == vorher
            continue
        assert r.status_code == 200, (runde, r.text)
        for i, b in vorher.items():
            if i not in auswahl:
                assert nachher[i] == b, f"Runde {runde}: nicht markierte Buchung {i} geändert"
                continue
            soll = dict(b)
            for f, v in felder.items():
                if f == "empfaenger_id":
                    soll["empfaenger"] = None if v is None else {"id": v, "name": "Bäckerei Eins" if v == k["e1"]
                                                                 else "Markt Zwei"}
                else:
                    soll[f] = v
            assert nachher[i] == soll, f"Runde {runde}: Buchung {i}"
            assert sum(s["betrag"] for s in nachher[i]["splits"]) == 0
    salden = api.salden()
    assert sum(s["saldo"] for s in salden.values()) == 0
