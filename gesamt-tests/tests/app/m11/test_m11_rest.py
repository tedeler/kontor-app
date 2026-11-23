"""M11: REST-Ergänzungen – Filter `unterkonten` (datenmodell.md 16.1, E-163) und Zusammenführen von Empfängern
mit neuem Namen (buchhaltungspflege.md 10, E-165)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import konto_nach_iban, lade_sync, sync
from tests.hilfen.m3 import aenderungen_seit, bestand, letzte_aenderung_id, pruefe_eintraege, \
    pruefe_rueckgaengig_rundreise
from tests.hilfen.m11 import daten_mit_salden


def _liste(api, **params) -> dict:
    return api.get("/api/buchungen", params={"pro_seite": 500, **params}, erwartet=200).daten


@pytest.fixture
def baum(api):
    """Wohnen > (Miete, Nebenkosten > Strom); Giro, Giro-Unterkonto; Buchungen mit bekannten Beträgen."""
    giro = api.konto("Giro", "girokonto")["id"]
    unter = api.konto("Giro Rücklage", "girokonto", eltern_id=giro)["id"]
    wohnen = api.konto("Wohnen", "aufwand")["id"]
    miete = api.konto("Miete", "aufwand", eltern_id=wohnen)["id"]
    neben = api.konto("Nebenkosten", "aufwand", eltern_id=wohnen)["id"]
    strom = api.konto("Strom", "aufwand", eltern_id=neben)["id"]
    essen = api.konto("Essen", "aufwand")["id"]
    b = {
        "wohnen": api.buchung("2024-01-02", [(giro, -1000), (wohnen, 1000)])["id"],
        "miete": api.buchung("2024-01-03", [(giro, -80000), (miete, 80000)])["id"],
        "strom": api.buchung("2024-01-04", [(unter, -6000), (strom, 6000)])["id"],
        "erstattung": api.buchung("2024-01-05", [(giro, 2500), (strom, -2500)])["id"],
        # gesplittet: zwei Splits im Baum (Miete, Strom) und einer außerhalb (Essen)
        "split": api.buchung("2024-01-06", [(giro, -700), (miete, 300), (strom, 100), (essen, 300)])["id"],
        "essen": api.buchung("2024-01-07", [(giro, -450), (essen, 450)])["id"],
        "umbuchung": api.buchung("2024-01-08", [(giro, -5000), (unter, 5000)])["id"],
    }
    return {"giro": giro, "unter": unter, "wohnen": wohnen, "miete": miete, "neben": neben, "strom": strom,
            "essen": essen, "b": b}


@pytest.mark.kern
def test_unterkonten_kategorie(api, baum):
    k, b = baum, baum["b"]
    ohne = _liste(api, konto_id=k["wohnen"])
    assert [e["id"] for e in ohne["eintraege"]] == [b["wohnen"]], "ohne unterkonten unverändert"
    mit = _liste(api, konto_id=k["wohnen"], unterkonten="true", sortierung="datum")
    soll = {b["wohnen"]: 1000, b["miete"]: 80000, b["strom"]: 6000, b["erstattung"]: -2500, b["split"]: 400}
    assert {e["id"]: e["betrag"] for e in mit["eintraege"]} == soll
    assert [e["id"] for e in mit["eintraege"]] == sorted(soll, key=lambda i: i)
    assert (mit["gesamt"], mit["summe"]) == (5, sum(soll.values()))
    # Zwischenebene
    neben = _liste(api, konto_id=k["neben"], unterkonten="true")
    assert {e["id"]: e["betrag"] for e in neben["eintraege"]} == {b["strom"]: 6000, b["erstattung"]: -2500,
                                                                  b["split"]: 100}
    # Blatt: mit und ohne gleich
    assert _liste(api, konto_id=k["strom"], unterkonten="true") == _liste(api, konto_id=k["strom"])


@pytest.mark.kern
def test_unterkonten_mit_betragsfilter_und_sortierung(api, baum):
    k, b = baum, baum["b"]
    r = _liste(api, konto_id=k["wohnen"], unterkonten="true", betrag_min=500, betrag_max=10000, sortierung="-betrag")
    assert [(e["id"], e["betrag"]) for e in r["eintraege"]] == [(b["strom"], 6000), (b["wohnen"], 1000)]
    assert r["summe"] == 7000
    r = _liste(api, konto_id=k["wohnen"], unterkonten="true", betrag_max=0)
    assert [e["id"] for e in r["eintraege"]] == [b["erstattung"]]


def test_unterkonten_bestandskonto_und_ohne_konto_id(api, baum):
    k, b = baum, baum["b"]
    mit = _liste(api, konto_id=k["giro"], unterkonten="true")
    betraege = {e["id"]: e["betrag"] for e in mit["eintraege"]}
    assert betraege[b["strom"]] == -6000, "Split auf dem Unterkonto zählt"
    assert betraege[b["umbuchung"]] == 0, "Umbuchung innerhalb des Baums netto 0"
    assert set(betraege) == set(b.values())
    assert mit["summe"] == -1000 - 80000 - 6000 + 2500 - 700 - 450
    assert _liste(api, unterkonten="true") == _liste(api), "ohne konto_id ohne Wirkung"
    assert _liste(api, konto_id=999999, unterkonten="true")["eintraege"] == []


def test_unterkonten_mit_kategorie_filter(api, baum):
    """Kategorieansicht mit Bestandskonto-Filter (oberflaeche.md 22.2: filter-konto → kategorie_id)."""
    k, b = baum, baum["b"]
    r = _liste(api, konto_id=k["wohnen"], unterkonten="true", kategorie_id=k["unter"])
    assert {e["id"]: e["betrag"] for e in r["eintraege"]} == {b["strom"]: 6000}


def test_unterkonten_validierung(api, baum):
    assert fehlercode(api.get("/api/buchungen", params={"konto_id": baum["wohnen"], "unterkonten": "vielleicht"},
                              erwartet=422)) == "validierung"


def test_unterkonten_export(api, baum):
    k = baum
    from tests.hilfen.m5 import csv_buchungen, csv_lesen  # noqa: PLC0415
    mit = csv_buchungen(csv_lesen(api.get("/api/export/buchungen.csv", params={"konto_id": k["wohnen"],
                                                                              "unterkonten": "true"},
                                          erwartet=200).content))
    ohne = csv_buchungen(csv_lesen(api.get("/api/export/buchungen.csv", params={"konto_id": k["wohnen"]},
                                           erwartet=200).content))
    assert (len(mit), len(ohne)) == (5, 1)


# ------------------------------------------------------------------ Empfänger zusammenführen mit Namen


def _empf(api, name, aliase=()):
    return api.post("/api/empfaenger", json={"name": name, "aliase": list(aliase)}, erwartet=201).daten


def _zusammen(api, ziel, quellen, erwartet=200, **extra):
    return api.post(f"/api/empfaenger/{ziel}/zusammenfuehren", json={"quelle_ids": quellen, **extra},
                    erwartet=erwartet)


@pytest.mark.kern
def test_zusammenfuehren_mit_neuem_namen(api):
    a = _empf(api, "REWE Markt 1234", ["Rewe 1234"])
    b = _empf(api, "REWE MARKT GMBH")
    c = _empf(api, "Rewe Filiale Mitte")
    giro = api.konto("Giro", "girokonto")["id"]
    kat = api.konto("Lebensmittel", "aufwand")["id"]
    bids = [api.buchung("2024-01-0%d" % (i + 1), [(giro, -100), (kat, 100)], empfaenger_id=e["id"])["id"]
            for i, e in enumerate((a, b, c))]
    vorher = bestand(api)
    vor_id = letzte_aenderung_id(api)
    z = _zusammen(api, a["id"], [c["id"], b["id"]], name="  REWE  ").daten
    assert (z["id"], z["name"]) == (a["id"], "REWE")
    # bisherige Aliase, alter Name des Ziels, dann Quellen nach id; sortiert
    assert z["aliase"] == sorted(["Rewe 1234", "REWE Markt 1234", "REWE MARKT GMBH", "Rewe Filiale Mitte"])
    assert [e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten] == [a["id"]]
    for bid in bids:
        assert api.buchung_lesen(bid)["empfaenger"] == {"id": a["id"], "name": "REWE"}
    (aen,) = aenderungen_seit(api, vor_id)
    assert aen["aktion"] == "empfaenger_zusammenfuehren"
    nachher = bestand(api)
    pruefe_eintraege(aen, vorher, nachher)
    pruefe_rueckgaengig_rundreise(api, aen, vorher, nachher)


@pytest.mark.kern
def test_zusammenfuehren_name_regeln(api):
    a = _empf(api, "Alpha")
    b = _empf(api, "Beta")
    dritter = _empf(api, "Gamma")
    # Name eines dritten → 409, nichts geändert
    vorher = bestand(api)
    assert fehlercode(_zusammen(api, a["id"], [b["id"]], 409, name="Gamma")) == "empfaenger_existiert"
    assert bestand(api) == vorher
    # ungültige Namen → 422
    for falsch in ("", "   ", "x" * 201, 5, None):
        r = _zusammen(api, a["id"], [b["id"]], 422, name=falsch)
        assert fehlercode(r) == "validierung", falsch
    assert bestand(api) == vorher
    # Name einer Quelle ist erlaubt; der alte Zielname wird Alias, der neue Name nicht
    z = _zusammen(api, a["id"], [b["id"]], name="Beta").daten
    assert (z["name"], z["aliase"]) == ("Beta", ["Alpha"])
    assert dritter["id"] in [e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten]


def test_zusammenfuehren_gleicher_name_wie_vorher(api):
    """name = bisheriger Name: wie ohne name (der Name wird kein Alias)."""
    a = _empf(api, "Delta", ["delta gmbh"])
    b = _empf(api, "Epsilon")
    z = _zusammen(api, a["id"], [b["id"]], name="Delta").daten
    assert (z["name"], z["aliase"]) == ("Delta", ["Epsilon", "delta gmbh"])


def test_zusammenfuehren_ohne_name_unveraendert(api):
    a = _empf(api, "Zeta")
    b = _empf(api, "Eta")
    z = _zusammen(api, a["id"], [b["id"]]).daten
    assert (z["name"], z["aliase"]) == ("Zeta", ["Eta"])


@pytest.mark.kern
def test_zusammengefuehrte_namen_greifen_bei_der_synchronisation(tmp_path, netz_gesperrt):
    """Wunsch des Anwenders: Danach werden neue Buchungen über die aufgenommenen Namen zugeordnet."""
    from tests.hilfen.m2 import mock_api  # noqa: PLC0415
    daten, erw = lade_sync()
    giro = erw["ibans"]["giro"]
    api = mock_api(tmp_path, daten=daten_mit_salden(tmp_path, {}))
    sync(api, von="2024-01-01", bis="2024-03-31")
    namen = sorted({u["gegenpartei_name"].strip() for u in daten["bank"]["umsaetze"]
                    if u["iban"] == giro and u["gegenpartei_name"] and u["gegenpartei_name"].strip()
                    and u["buchungstag"] <= "2024-03-31" and not u["vormerkung"]})
    empf = {e["name"]: e for e in api.get("/api/empfaenger", erwartet=200).daten}
    # zwei Empfänger, die auch nach dem 31.03. wieder vorkommen
    spaeter = {u["gegenpartei_name"].strip() for u in daten["bank"]["umsaetze"]
               if u["iban"] == giro and u["buchungstag"] > "2024-03-31" and u["gegenpartei_name"]}
    paar = [n for n in namen if n in spaeter and n in empf][:2]
    assert len(paar) == 2, "Testdaten: zwei wiederkehrende Empfänger"
    ziel, quelle = empf[paar[0]], empf[paar[1]]
    _zusammen(api, ziel["id"], [quelle["id"]], name="Zusammengefasst")
    sync(api, von="2024-04-01")
    neu = [b for b in api.alle_buchungen() if b["datum"] >= "2024-04-01"
           and any(e.startswith(f"bank:{giro}:") for e in b["extern_ids"])]
    for u in daten["bank"]["umsaetze"]:
        if u["iban"] == giro and u["buchungstag"] >= "2024-04-01" and not u["vormerkung"] \
                and (u["gegenpartei_name"] or "").strip() in paar:
            b = next(x for x in neu if f"bank:{giro}:{u['umsatz_id']}" in x["extern_ids"])
            assert b["empfaenger"] == {"id": ziel["id"], "name": "Zusammengefasst"}, u["umsatz_id"]
    assert not {e["name"] for e in api.get("/api/empfaenger", erwartet=200).daten} & set(paar)
    assert konto_nach_iban(api)[giro]
