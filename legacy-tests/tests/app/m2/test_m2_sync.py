"""M2: Synchronisation – Kontozuordnung, Übernahme, Wiederholung, Zeitraum (synchronisation.md 2–5, 8).

Erwartungen kommen aus der Mock-Datendatei und dem unabhängigen Orakel
``tests/hilfen/sync_orakel`` (nie aus Ausgaben der Anwendung).
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from hypothesis import given, strategies as st

from generator.iban import fiktive_iban
from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import (
    UNKATEGORISIERT, konto_nach_iban, laeufe, lade_sync, mock_api, nach_kennung, setze_zeit, status, sync,
    unkategorisiert, zeit,
)

VON = "2024-01-01"


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def sapi(tmp_path):
    return mock_api(tmp_path)


def _gebucht(daten, von="0000-01-01", bis="9999-12-31", iban=None):
    return [u for u in daten["bank"]["umsaetze"] if not u["vormerkung"] and von <= u["buchungstag"] <= bis
            and (iban is None or u["iban"] == iban)]


def _pruefe_buchbestand(api, daten, von, bis):
    """Buchungen aus der Synchronisation = Orakel über alle gebuchten Umsätze im Zeitraum."""
    konten = konto_nach_iban(api)
    unk = unkategorisiert(api)
    assert unk is not None
    bs = api.alle_buchungen()
    kennungen = nach_kennung(bs)
    soll = _gebucht(daten, von, bis)
    assert set(kennungen) == {orakel.kennung(u) for u in soll}
    for u in soll:
        b = kennungen[orakel.kennung(u)]
        assert orakel.sicht_buchung(b) == orakel.erwartete_buchung(u, konten[u["iban"]]["id"], unk["id"]), u
        assert b["kategorie_id"] is None and b["vorschlag"] is None and b["belege"] == []
    # Buchungs-IDs steigen je Konto in der Reihenfolge (buchungstag, umsatz_id)
    for iban in konten:
        reihe = [orakel.kennung(u) for u in sorted(_gebucht(daten, von, bis, iban),
                                                    key=lambda u: (u["buchungstag"], u["umsatz_id"]))]
        ids = [kennungen[k]["id"] for k in reihe]
        assert ids == sorted(ids), f"Reihenfolge der Buchungen für {iban}"
    for b in bs:
        assert len(b["splits"]) >= 2 and sum(s["betrag"] for s in b["splits"]) == 0
    return kennungen


# ------------------------------------------------------------- erster Lauf


@pytest.mark.kern
def test_erster_lauf_konten_und_buchungen(sapi, sd, netz_gesperrt):
    daten, erw = sd
    lauf = sync(sapi, von=VON)
    assert lauf["status"] == "erfolgreich" and lauf["ausloeser"] == "manuell"
    assert lauf["fehler"] is None and lauf["tan_anforderung_id"] is None
    assert (lauf["von"], lauf["bis"]) == (VON, None)
    assert zeit(lauf["gestartet_am"]) == zeit(lauf["beendet_am"]) == zeit("2024-06-30T12:00:00Z")
    ibans = sorted(k["iban"] for k in daten["bank"]["konten"])
    assert [k["iban"] for k in lauf["konten"]] == ibans
    konten = konto_nach_iban(sapi)
    for sk in lauf["konten"]:
        assert sk["status"] == "erfolgreich" and sk["konto_neu"] is True and sk["fehler"] is None
        assert (sk["von"], sk["bis"]) == (VON, "2024-06-30")
        k = konten[sk["iban"]]
        assert sk["konto_id"] == k["id"]
        bk = next(b for b in daten["bank"]["konten"] if b["iban"] == sk["iban"])
        assert (k["name"], k["art"]) == (bk["name"].strip(), bk["art"])
        assert (k["eltern_id"], k["extern_id"], k["geschlossen"], k["eroeffnet_am"], k["notiz"]) == (
            None, None, False, None, "")
    _pruefe_buchbestand(sapi, daten, VON, "2024-06-30")


@pytest.mark.kern
def test_zaehlungen_je_konto(sapi, sd, netz_gesperrt):
    daten, _ = sd
    lauf = sync(sapi, von=VON)
    for sk in lauf["konten"]:
        geliefert = orakel.im_zeitraum(daten["bank"]["umsaetze"], sk["iban"], dt.date(2024, 1, 1),
                                       dt.date(2024, 6, 30), dt.date(2024, 6, 30))
        vm = sum(u["vormerkung"] for u in geliefert)
        assert (sk["umsaetze_gesamt"], sk["vormerkungen_ignoriert"], sk["buchungen_neu"], sk["buchungen_vorhanden"],
                sk["buchungen_zusammengefuehrt"], sk["buchungen_zur_pruefung"], sk["buchungen_kategorisiert"]) == (
            len(geliefert), vm, len(geliefert) - vm, 0, 0, 0, 0), sk["iban"]


def test_salden_nach_lauf(sapi, sd, netz_gesperrt):
    daten, erw = sd
    sync(sapi, von=VON)
    konten = konto_nach_iban(sapi)
    s = sapi.salden()
    for iban, aenderung in erw["saldo_veraenderung"].items():
        assert s[konten[iban]["id"]]["saldo"] == aenderung
        assert s[konten[iban]["id"]]["anzahl_buchungen"] == erw["anzahl_gebucht"][iban]
    assert s[unkategorisiert(sapi)["id"]]["saldo"] == -sum(erw["saldo_veraenderung"].values())
    assert sapi.uebersicht()["summe_gesamt"] == 0


def test_empfaenger(sapi, sd, netz_gesperrt):
    daten, _ = sd
    sync(sapi, von=VON)
    namen = {(u["gegenpartei_name"] or "").strip() for u in _gebucht(daten)} - {""}
    empf = sapi.get("/api/empfaenger", erwartet=200).daten
    assert sorted(e["name"] for e in empf) == sorted(namen), "jeder Name genau einmal"
    assert all(e["extern_id"] is None for e in empf)
    kennungen = nach_kennung(sapi.alle_buchungen())
    for u in _gebucht(daten):
        b = kennungen[orakel.kennung(u)]
        if not (u["gegenpartei_name"] or "").strip():
            assert b["empfaenger"] is None
        else:
            assert b["empfaenger"]["name"] == u["gegenpartei_name"].strip()


def test_vorhandener_empfaenger_wird_verwendet(sapi, sd, netz_gesperrt):
    e = sapi.empfaenger("Café Bohne")
    sync(sapi, von=VON)
    cafe = [b for b in sapi.alle_buchungen() if b["empfaenger"] and b["empfaenger"]["name"] == "Café Bohne"]
    assert cafe and all(b["empfaenger"]["id"] == e["id"] for b in cafe)


def test_vorhandenes_konto_ueber_iban(sapi, sd, netz_gesperrt):
    _, erw = sd
    g = sapi.konto("Mein Giro (manuell)", "sparkonto", iban=erw["ibans"]["giro"], geschlossen=True, notiz="n")
    lauf = sync(sapi, von=VON)
    sk = next(k for k in lauf["konten"] if k["iban"] == erw["ibans"]["giro"])
    assert sk["konto_neu"] is False and sk["konto_id"] == g["id"]
    assert sapi.get(f"/api/konten/{g['id']}", erwartet=200).daten == g, "zugeordnetes Konto bleibt unverändert"
    assert sum(1 for k in sapi.konten() if k["iban"] == erw["ibans"]["giro"]) == 1


def test_unkategorisiert_konto(sapi, sd, netz_gesperrt):
    sync(sapi, von=VON, bis="2024-02-29")
    unk = unkategorisiert(sapi)
    assert (unk["name"], unk["art"], unk["eltern_id"], unk["iban"], unk["geschlossen"]) == (
        "Unkategorisiert", "eigenkapital", None, None, False)
    sapi.patch(f"/api/konten/{unk['id']}", json={"name": "Noch zuordnen"}, erwartet=200)
    sync(sapi)
    unk2 = unkategorisiert(sapi)
    assert unk2["id"] == unk["id"] and unk2["name"] == "Noch zuordnen"
    assert sum(1 for k in sapi.konten() if k["art"] == "eigenkapital") == 1


# ------------------------------------------------------------ Störfälle


def test_vormerkungen_nicht_gebucht(sapi, sd, netz_gesperrt):
    daten, erw = sd
    sync(sapi, von=VON)
    kennungen = nach_kennung(sapi.alle_buchungen())
    alle = {u["umsatz_id"]: u for u in daten["bank"]["umsaetze"]}
    for v in erw["vormerkungen"]:
        assert orakel.kennung(alle[v]) not in kennungen


def test_storno_eigene_buchung(sapi, sd, netz_gesperrt):
    daten, erw = sd
    sync(sapi, von=VON)
    kennungen = nach_kennung(sapi.alle_buchungen())
    for sid in erw["stornos"]:
        u = next(x for x in daten["bank"]["umsaetze"] if x["umsatz_id"] == sid)
        b = kennungen[orakel.kennung(u)]
        assert b["splits"][0]["betrag"] == u["betrag"] and b["verwendungszweck"] == u["verwendungszweck"]


@pytest.mark.kern
def test_zweimal_derselbe_kaffee(sapi, sd, netz_gesperrt):
    """T 6: zwei echte gleiche Umsätze am selben Tag werden beide gebucht, ohne Verdacht."""
    daten, _ = sd
    sync(sapi, von=VON)
    gleich = {}
    for u in _gebucht(daten):
        gleich.setdefault((u["iban"], u["buchungstag"], u["betrag"], u["gegenpartei_name"]), []).append(u)
    paare = [v for v in gleich.values() if len(v) >= 2]
    assert paare
    kennungen = nach_kennung(sapi.alle_buchungen())
    for v in paare:
        assert len({kennungen[orakel.kennung(u)]["id"] for u in v}) == len(v)
    assert sapi.get("/api/dubletten", erwartet=200).daten == []


def test_kategorie_setzen_auf_synchronisierter_buchung(sapi, sd, netz_gesperrt):
    sync(sapi, von=VON)
    kat = sapi.konto("Lebensmittel", "aufwand")
    b = next(x for x in sapi.alle_buchungen() if x["extern_ids"][0].startswith("bank:"))
    neu = sapi.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": kat["id"]}, erwartet=200).daten
    assert neu["kategorie_id"] == kat["id"] and neu["vorschlag"] is None


# ------------------------------------------------- Wiederholung, Zeitraum


@pytest.mark.kern
def test_wiederholter_abruf_keine_dubletten(sapi, sd, netz_gesperrt):
    daten, _ = sd
    sync(sapi, von=VON)
    vorher = sapi.zustand()
    lauf = sync(sapi, von=VON)
    assert lauf["status"] == "erfolgreich"
    for sk in lauf["konten"]:
        n = len(_gebucht(daten, VON, "2024-06-30", sk["iban"]))
        assert (sk["buchungen_vorhanden"], sk["buchungen_neu"], sk["buchungen_zusammengefuehrt"],
                sk["konto_neu"]) == (n, 0, 0, False)
    assert sapi.zustand() == vorher


@pytest.mark.kern
def test_geloeschte_buchung_kommt_nicht_wieder(sapi, sd, netz_gesperrt):
    daten, _ = sd
    sync(sapi, von=VON)
    bs = sapi.alle_buchungen()
    weg = bs[3]
    sapi.delete(f"/api/buchungen/{weg['id']}", erwartet=204)
    lauf = sync(sapi, von=VON)
    assert sum(k["buchungen_neu"] for k in lauf["konten"]) == 0
    assert weg["extern_ids"][0] not in nach_kennung(sapi.alle_buchungen())


@pytest.mark.kern
def test_zeitlich_fortlaufend(tmp_path, sd, netz_gesperrt):
    """T 21: Stichtage nacheinander; Zeitraum nach 4.1 (Erstabruf 90 Tage, Überlappung 14 Tage)."""
    daten, erw = sd
    api = mock_api(tmp_path, heute=erw["stufen"][0])
    letzter = None
    for stufe in erw["stufen"]:
        setze_zeit(api, f"{stufe}T08:00:00Z")
        heute = dt.date.fromisoformat(stufe)
        lauf = sync(api)
        assert (lauf["von"], lauf["bis"]) == (None, None)
        for sk in lauf["konten"]:
            von = heute - dt.timedelta(days=90) if letzter is None else letzter - dt.timedelta(days=14)
            assert (sk["von"], sk["bis"]) == (von.isoformat(), stufe), sk
            geliefert = orakel.im_zeitraum(daten["bank"]["umsaetze"], sk["iban"], von, heute, heute)
            vorhanden = [u for u in geliefert if not u["vormerkung"] and letzter is not None
                         and u["buchungstag"] <= letzter.isoformat()]
            vm = [u for u in geliefert if u["vormerkung"]]
            assert sk["umsaetze_gesamt"] == len(geliefert)
            assert sk["vormerkungen_ignoriert"] == len(vm)
            assert sk["buchungen_vorhanden"] == len(vorhanden)
            assert sk["buchungen_neu"] == len(geliefert) - len(vm) - len(vorhanden)
        zst = {z["iban"]: z for z in api.get("/api/sync/konten", erwartet=200).daten}
        assert all(z["letzter_abruf_bis"] == stufe for z in zst.values())
        assert all(zeit(z["letzter_erfolg_am"]) == zeit(f"{stufe}T08:00:00Z") for z in zst.values())
        _pruefe_buchbestand(api, daten, "0000-01-01", stufe)
        letzter = heute


def test_erstabruf_und_ueberlappung_konfigurierbar(tmp_path, sd, netz_gesperrt):
    api = mock_api(tmp_path, heute="2024-03-31", sync_erstabruf_tage=10, sync_ueberlappung_tage=0)
    lauf = sync(api)
    assert {(k["von"], k["bis"]) for k in lauf["konten"]} == {("2024-03-21", "2024-03-31")}
    setze_zeit(api, "2024-04-30T12:00:00Z")
    lauf = sync(api)
    assert {(k["von"], k["bis"]) for k in lauf["konten"]} == {("2024-03-31", "2024-04-30")}


def test_bis_aus_anfrage(sapi, sd, netz_gesperrt):
    daten, _ = sd
    lauf = sync(sapi, von=VON, bis="2024-03-31")
    assert (lauf["von"], lauf["bis"]) == (VON, "2024-03-31")
    assert {(k["von"], k["bis"]) for k in lauf["konten"]} == {(VON, "2024-03-31")}
    _pruefe_buchbestand(sapi, daten, VON, "2024-03-31")
    assert {z["letzter_abruf_bis"] for z in sapi.get("/api/sync/konten", erwartet=200).daten} == {"2024-03-31"}
    # ein früheres bis verkleinert letzter_abruf_bis nicht
    sync(sapi, von=VON, bis="2024-02-01")
    assert {z["letzter_abruf_bis"] for z in sapi.get("/api/sync/konten", erwartet=200).daten} == {"2024-03-31"}


@pytest.mark.parametrize("koerper", [
    {"von": "2024-05-01", "bis": "2024-04-30"}, {"von": "01.01.2024"}, {"bis": "2024-02-30"},
    {"von": 20240101}, {"unbekannt": 1}, {"von": None},
], ids=["von_nach_bis", "datumsformat", "kein_datum", "zahl", "feld_unbekannt", "null"])
def test_anfrage_validierung(sapi, koerper, netz_gesperrt):
    r = sapi.post("/api/sync", json=koerper, erwartet=422)
    assert fehlercode(r) == "validierung"
    assert laeufe(sapi) == [] and sapi.alle_buchungen() == []


def test_ohne_koerper(sapi, netz_gesperrt):
    r = sapi.post("/api/sync", erwartet=200)
    assert r.daten["status"] == "erfolgreich" and r.daten["von"] is None


# ------------------------------------------------------- Läufe, Status


def test_laeufe_und_status(sapi, netz_gesperrt):
    st = status(sapi)
    assert st == {"automatisch": False, "intervall_minuten": 0, "laeuft": False, "jetzt": st["jetzt"],
                  "naechster_lauf": None, "letzter_lauf": None, "offene_tan_anforderung": None,
                  "pin_vorhanden": False}
    assert zeit(st["jetzt"]) == zeit("2024-06-30T12:00:00Z")
    a = sync(sapi, von=VON)
    setze_zeit(sapi, "2024-06-30T13:30:00Z")
    b = sync(sapi)
    ls = laeufe(sapi)
    assert [x["id"] for x in ls] == [a["id"], b["id"]] and a["id"] < b["id"]
    assert ls == [a, b]
    assert sapi.get(f"/api/sync/laeufe/{b['id']}", erwartet=200).daten == b
    assert fehlercode(sapi.get("/api/sync/laeufe/4711", erwartet=404)) == "nicht_gefunden"
    st = status(sapi)
    assert st["letzter_lauf"] == b and st["laeuft"] is False and zeit(b["gestartet_am"]) == zeit(st["jetzt"])
    zst = sapi.get("/api/sync/konten", erwartet=200).daten
    assert [z["iban"] for z in zst] == sorted(z["iban"] for z in zst) and len(zst) == 3


def test_mock_zeit(tmp_path, netz_gesperrt):
    api = mock_api(tmp_path, heute=None)
    z = api.get("/api/mock/zeit", erwartet=200).daten
    assert z["simuliert"] is False and z["heute"] == zeit(z["jetzt"]).date().isoformat()
    z = setze_zeit(api, "2031-02-28T23:59:59Z")
    assert z == {"jetzt": "2031-02-28T23:59:59Z", "heute": "2031-02-28", "simuliert": True}
    assert api.get("/api/mock/zeit", erwartet=200).daten == z
    assert zeit(status(api)["jetzt"]) == zeit("2031-02-28T23:59:59Z")
    z = setze_zeit(api, "2024-01-01T00:00:00Z")  # auch rückwärts
    assert z["heute"] == "2024-01-01"
    for koerper in ({}, {"jetzt": "2024-01-01"}, {"jetzt": "gestern"}, {"jetzt": "2024-01-01T00:00:00Z", "x": 1}):
        assert fehlercode(api.put("/api/mock/zeit", json=koerper, erwartet=422)) == "validierung"
    api2 = mock_api(tmp_path / "b", heute="2024-05-17")
    z = api2.get("/api/mock/zeit", erwartet=200).daten
    assert z["simuliert"] is True and zeit(z["jetzt"]) == zeit("2024-05-17T12:00:00Z")


def test_echtmodus(api, netz_gesperrt):
    """Echtes FinTS-Plugin in M2: Lauf scheitert sauber (kein 5xx, keine Verbindung), Mock-Uhr gesperrt."""
    lauf = sync(api)
    assert lauf["status"] == "fehlgeschlagen" and lauf["fehler"]["code"] and lauf["fehler"]["meldung"].strip()
    assert lauf["beendet_am"] is not None and api.alle_buchungen() == []
    for r in (api.get("/api/mock/zeit", erwartet=409), api.put("/api/mock/zeit", json={"jetzt": "2024-01-01T00:00:00Z"},
                                                              erwartet=409)):
        assert fehlercode(r) == "nur_mock_modus"
    netz_gesperrt.versuche.clear()


def test_vorschlag_feld_in_jeder_buchung(sapi, netz_gesperrt):
    """E-029: ab M2 trägt jede Buchungsantwort das Feld ``vorschlag``."""
    g = sapi.konto("Giro")
    a = sapi.konto("Lebensmittel", "aufwand")
    b = sapi.buchung("2024-01-01", [(g["id"], -100), (a["id"], 100)])
    assert "vorschlag" in b and b["vorschlag"] is None
    assert sapi.buchung_lesen(b["id"])["vorschlag"] is None
    assert all("vorschlag" in x for x in sapi.seite()["eintraege"])
    sync(sapi, von=VON)
    assert all("vorschlag" in x and x["vorschlag"] is None for x in sapi.alle_buchungen())


# ------------------------------------------------------- Hypothesis


_TAGE = st.integers(0, 40).map(lambda n: (dt.date(2024, 3, 1) + dt.timedelta(days=n)).isoformat())
_NAMEN = st.sampled_from([None, "", "  ", "Laden A", " Laden A ", "Läden Ü", "LADEN A", "Café Bohne"])


@st.composite
def umsatzlisten(draw):
    ibans = [fiktive_iban(9101), fiktive_iban(9102)][:draw(st.integers(1, 2))]
    us = []
    for n in range(draw(st.integers(0, 25))):
        us.append({"umsatz_id": f"H-{n:03d}", "iban": draw(st.sampled_from(ibans)), "buchungstag": draw(_TAGE),
                   "valuta": None, "betrag": draw(st.integers(-5000, 5000)), "waehrung": "EUR",
                   "gegenpartei_name": draw(_NAMEN), "gegenpartei_iban": None,
                   "verwendungszweck": draw(st.sampled_from(["", "Zweck", "Äußerst ÜBEL"])),
                   "vormerkung": draw(st.booleans()) and draw(st.booleans()), "storno": draw(st.booleans())})
    us.sort(key=lambda u: (u["buchungstag"], u["umsatz_id"]))
    konten = [{"iban": i, "bic": None, "name": f"Konto {i[-4:]}", "art": "girokonto", "inhaber": "Testperson (fiktiv)",
               "waehrung": "EUR"} for i in ibans]
    return {"format": "kontor-mock-daten", "version": 1, "bank": {"konten": konten, "umsaetze": us},
            "mail": {"postfaecher": [], "nachrichten": []}}


@pytest.mark.kern
@given(daten=umsatzlisten(), teilung=st.integers(0, 40))
def test_zufaellige_umsaetze_exakt_und_wiederholbar(tmp_path_factory, daten, teilung):
    """Zwei Läufe mit zufälliger Zwischenzeit: Bestand = Orakel, keine Dubletten, Invarianten."""
    basis = tmp_path_factory.mktemp("sync")
    datei = basis / "daten.json"
    datei.write_text(json.dumps(daten), encoding="utf-8")
    mitte = (dt.date(2024, 3, 1) + dt.timedelta(days=teilung)).isoformat()
    api = mock_api(basis, daten=datei, heute=mitte)
    sync(api, von="2024-03-01")
    setze_zeit(api, "2024-04-30T12:00:00Z")
    sync(api, von="2024-03-01")
    sync(api, von="2024-03-01")
    konten = konto_nach_iban(api)
    bs = api.alle_buchungen()
    soll = _gebucht(daten)
    kennungen = nach_kennung(bs)
    assert len(bs) == len(soll) == len(kennungen)
    unk = unkategorisiert(api)
    for u in soll:
        assert orakel.sicht_buchung(kennungen[orakel.kennung(u)]) == orakel.erwartete_buchung(
            u, konten[u["iban"]]["id"], unk["id"] if unk else None)
    s = api.salden()
    for iban, k in konten.items():
        assert s[k["id"]]["saldo"] == sum(u["betrag"] for u in soll if u["iban"] == iban)
    assert api.uebersicht()["summe_gesamt"] == 0
    assert api.get("/api/dubletten", erwartet=200).daten == []
    assert all(k["extern_id"] != UNKATEGORISIERT or k["art"] == "eigenkapital" for k in api.konten())
