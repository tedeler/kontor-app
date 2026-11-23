"""Buchungsliste: alle Filter, Kombinationen, Sortierung, Paginierung (K 5, T 14, E-020).

Der Datenbestand ist standard.kmy plus gezielte Änderungen (Status, Tags,
manuelle Buchungen). Erwartungen werden unabhängig aus der ungefilterten
Liste berechnet (``Orakel``).
"""

from __future__ import annotations

import datetime as dt

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.normal import norm
from tests.hilfen.pfade import KMY

pytestmark = [pytest.mark.kern, pytest.mark.langsam]


class Bestand:
    def __init__(self, api) -> None:
        self.api = api
        self.alle = api.alle_buchungen()
        self.konten = api.konten()
        self.tags = api.get("/api/tags", erwartet=200).daten
        self.empfaenger = api.get("/api/empfaenger", erwartet=200).daten
        self.kinder: dict[int, list[int]] = {}
        for k in self.konten:
            if k["eltern_id"]:
                self.kinder.setdefault(k["eltern_id"], []).append(k["id"])

    def konto(self, name: str) -> dict:
        return next(k for k in self.konten if k["name"] == name)

    def nachfahren(self, kid: int) -> set[int]:
        aus = {kid}
        for c in self.kinder.get(kid, []):
            aus |= self.nachfahren(c)
        return aus


@pytest.fixture(scope="module")
def bestand(tmp_path_factory) -> Bestand:
    api = neue_api(tmp_path_factory.mktemp("filter"))
    api.import_kmy(KMY / "standard.kmy", erwartet=200)
    buchungen = api.alle_buchungen()
    t_extra = api.tag("Prüfen – später")
    t_urlaub = next(t for t in api.get("/api/tags", erwartet=200).daten if t["name"] == "Urlaub")
    for n, b in enumerate(buchungen):
        if n % 7 == 3:
            api.patch(f"/api/buchungen/{b['id']}", json={"status": "bestaetigt"}, erwartet=200)
            if n % 3 == 0:
                api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200)
        if n % 11 == 5:
            tags = sorted({t["id"] for t in b["tags"]} | {t_extra["id"]})
            api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": tags}, erwartet=200)
    konten = {k["name"]: k["id"] for k in api.konten()}
    e = api.empfaenger("Zoë’s Kiosk")
    api.buchung("2024-12-31", [(konten["Girokonto"], -995, "Zeitschrift"), (konten["Sonstiges"], 995, "Memo-ÄÖÜ")],
                status="vorlaeufig", empfaenger_id=e["id"], verwendungszweck="Kiosk")
    api.buchung("2021-12-31", [(konten["Girokonto"], -1), (konten["Tagesgeld"], 1)], status="vorlaeufig")
    api.buchung("2024-06-15", [(konten["Girokonto"], -7000), (konten["Miete"], 5000), (konten["Strom"], 2000)],
                verwendungszweck="Nebenkosten Nachzahlung", tag_ids=[t_urlaub["id"], t_extra["id"]])
    return Bestand(api)


# ------------------------------------------------------------------ Orakel


def orakel(best: Bestand, p: dict) -> tuple[list[dict], int]:
    konto_id = p.get("konto_id")
    treffer = []
    for b in best.alle:
        if konto_id is not None:
            if not any(s["konto_id"] == konto_id for s in b["splits"]):
                continue
            betrag = sum(s["betrag"] for s in b["splits"] if s["konto_id"] == konto_id)
        else:
            betrag = sum(s["betrag"] for s in b["splits"] if s["betrag"] > 0)
        if "von" in p and b["datum"] < p["von"]:
            continue
        if "bis" in p and b["datum"] > p["bis"]:
            continue
        if "betrag_min" in p and betrag < p["betrag_min"]:
            continue
        if "betrag_max" in p and betrag > p["betrag_max"]:
            continue
        if "kategorie_id" in p:
            ziel = best.nachfahren(p["kategorie_id"]) if p.get("unterkategorien") else {p["kategorie_id"]}
            if not any(s["konto_id"] in ziel for s in b["splits"]):
                continue
        tag_ids = {t["id"] for t in b["tags"]}
        if not set(p.get("tag_id", [])) <= tag_ids:
            continue
        if "empfaenger_id" in p and (b["empfaenger"] or {}).get("id") != p["empfaenger_id"]:
            continue
        if p.get("ohne_empfaenger") and b["empfaenger"] is not None:
            continue
        if "verwendungszweck" in p and norm(p["verwendungszweck"]) not in norm(b["verwendungszweck"]):
            continue
        if "suche" in p:
            felder = [b["verwendungszweck"]] + [s["memo"] for s in b["splits"]] + [t["name"] for t in b["tags"]]
            if b["empfaenger"]:
                felder.append(b["empfaenger"]["name"])
            if not any(norm(p["suche"]) in norm(f) for f in felder):
                continue
        if "status" in p and b["status"] not in p["status"]:
            continue
        treffer.append({**b, "betrag": betrag})
    return sortiere(treffer, p.get("sortierung", "datum")), sum(b["betrag"] for b in treffer)


def sortiere(liste: list[dict], sortierung: str) -> list[dict]:
    absteigend = sortierung.startswith("-")
    feld = sortierung.lstrip("-")
    nach_id = sorted(liste, key=lambda b: b["id"])
    if feld == "empfaenger":
        mit = [b for b in nach_id if b["empfaenger"]]
        ohne = [b for b in nach_id if not b["empfaenger"]]
        return sorted(mit, key=lambda b: norm(b["empfaenger"]["name"]), reverse=absteigend) + ohne
    return sorted(nach_id, key=lambda b: b[feld], reverse=absteigend)


def pruefe(best: Bestand, params: dict) -> list[dict]:
    soll, summe = orakel(best, params)
    seite, pro_seite = params.get("seite", 1), params.get("pro_seite", 50)
    d = best.api.seite(**params)
    assert (d["gesamt"], d["seite"], d["pro_seite"]) == (len(soll), seite, pro_seite), params
    assert d["summe"] == summe, f"summe {d['summe']} ≠ {summe} für {params}"
    erwartet = soll[(seite - 1) * pro_seite: seite * pro_seite]
    ist_ids, soll_ids = [b["id"] for b in d["eintraege"]], [b["id"] for b in erwartet]
    if ist_ids != soll_ids:
        fehlen = set(soll_ids) - set(ist_ids)
        zuviel = set(ist_ids) - set(soll_ids)
        raise AssertionError(f"Filter {params}: Reihenfolge/Treffer weichen ab; fehlen {sorted(fehlen)[:10]}, "
                             f"zu viel {sorted(zuviel)[:10]}")
    assert [b["betrag"] for b in d["eintraege"]] == [b["betrag"] for b in erwartet]
    assert d["eintraege"] == erwartet, "Einträge der Liste müssen den vollständigen Buchungen entsprechen"
    return soll


# --------------------------------------------------------- einzelne Filter


def test_ohne_filter_vorgaben(bestand):
    d = bestand.api.seite()
    assert d["seite"] == 1 and d["pro_seite"] == 50 and d["gesamt"] == len(bestand.alle)
    assert len(d["eintraege"]) == 50
    pruefe(bestand, {})
    assert d["summe"] == sum(sum(s["betrag"] for s in b["splits"] if s["betrag"] > 0) for b in bestand.alle)


@pytest.mark.parametrize("name", ["Girokonto", "Tagesgeld", "Kreditkarte", "Darlehen Haus", "Altes Sparbuch",
                                  "Lebensmittel", "Wohnen", "Anfangsbestand"])
def test_filter_konto(bestand, name):
    soll = pruefe(bestand, {"konto_id": bestand.konto(name)["id"], "pro_seite": 500})
    if name == "Wohnen":
        assert len(soll) == 0, "konto_id zählt keine Unterkonten"
    else:
        assert soll


def test_filter_konto_saldo(bestand):
    """Summe über alle Buchungen eines Kontos (konto_id) = Saldo laut Kontenübersicht."""
    sal = bestand.api.salden()
    for k in bestand.konten:
        d = bestand.api.seite(konto_id=k["id"], pro_seite=1)
        assert d["summe"] == sal[k["id"]]["saldo"], k["name"]
        assert d["gesamt"] == sal[k["id"]]["anzahl_buchungen"], k["name"]


@pytest.mark.parametrize("von,bis", [("2023-01-01", "2023-12-31"), ("2022-03-17", "2022-03-17"),
                                     ("2024-12-31", None), (None, "2021-12-31"), ("2025-01-01", None),
                                     ("2024-02-29", "2024-03-01")])
def test_filter_zeitraum(bestand, von, bis):
    p = {k: v for k, v in (("von", von), ("bis", bis)) if v}
    soll = pruefe(bestand, {**p, "pro_seite": 500})
    if von == "2022-03-17":
        assert len([b for b in soll if b["verwendungszweck"] == "Kartenzahlung Café Cappuccino"]) == 2


@pytest.mark.parametrize("p", [
    {"betrag_min": 10000}, {"betrag_max": 340}, {"betrag_min": 340, "betrag_max": 340},
    {"betrag_min": 0, "betrag_max": 0},
    {"konto_id": "Girokonto", "betrag_min": 0}, {"konto_id": "Girokonto", "betrag_max": -50000},
    {"konto_id": "Tagesgeld", "betrag_min": -1, "betrag_max": 1},
], ids=str)
def test_filter_betrag(bestand, p):
    if "konto_id" in p:
        p = {**p, "konto_id": bestand.konto(p["konto_id"])["id"]}
    pruefe(bestand, {**p, "pro_seite": 500})


@pytest.mark.parametrize("name,unter", [("Wohnen", False), ("Wohnen", True), ("Miete", True), ("Versicherungen", True),
                                        ("Versicherungen", False), ("Haftpflicht", False), ("Gehalt", False),
                                        ("Girokonto", False), ("Anfangsbestand", True)])
def test_filter_kategorie(bestand, name, unter):
    soll = pruefe(bestand, {"kategorie_id": bestand.konto(name)["id"], "unterkategorien": unter, "pro_seite": 500})
    if name == "Wohnen":
        assert bool(soll) is unter
    if name == "Versicherungen" and unter:
        assert all(len(b["splits"]) == 4 for b in soll) and len(soll) == 36


def test_filter_tags_und_verknuepft(bestand):
    t = {x["name"]: x["id"] for x in bestand.tags}
    for ids in ([t["Urlaub"]], [t["Steuer"]], [t["Prüfen – später"]], [t["Urlaub"], t["Prüfen – später"]],
                [t["Urlaub"], t["Geschäftlich"]], [t["Steuer"], t["Urlaub"], t["Geschäftlich"]]):
        pruefe(bestand, {"tag_id": ids, "pro_seite": 500})
    beide = orakel(bestand, {"tag_id": [t["Urlaub"], t["Prüfen – später"]]})[0]
    assert beide, "Testdaten enthalten Buchungen mit beiden Tags"


def test_filter_empfaenger(bestand):
    for e in bestand.empfaenger:
        pruefe(bestand, {"empfaenger_id": e["id"], "pro_seite": 500})
    soll = pruefe(bestand, {"ohne_empfaenger": True, "pro_seite": 500})
    assert soll and all(b["empfaenger"] is None for b in soll)
    pruefe(bestand, {"ohne_empfaenger": False, "pro_seite": 50})


@pytest.mark.parametrize("text,mindestens", [
    ("miete", 36), ("MIETE 03/2023", 1), ("Ölgemälde", 3), ("OELGEMAELDE", 3), ("ölgemaelde", 3),
    ("<sonderposten> & \"rabatt\"", 3), ("☃", 3), ("storno:", 3), ("Gutschrift", 3), ("Xylophon", 0),
])
def test_filter_verwendungszweck(bestand, text, mindestens):
    soll = pruefe(bestand, {"verwendungszweck": text, "pro_seite": 500})
    assert len(soll) >= mindestens if mindestens else not soll


@pytest.mark.parametrize("text,feld", [
    ("MUELLER", "empfaenger"), ("müller & söhne", "empfaenger"), ("Muller", None), ("uebermass", "empfaenger"),
    ("tilgung", "memo"), ("zinsen", "memo"), ("hausrat nr. 0002", "memo"), ("urlaub", "tag"), ("STEUER", "tag"),
    ("pruefen – spaeter", "tag"), ("zoë’s", "empfaenger"), ("memo-aeoeue", "memo"), ("Nachzahlung", "vz"),
])
def test_freitextsuche(bestand, text, feld):
    """Volltext über Empfänger, Verwendungszweck, Split-Memos und Tags; Groß-/Kleinschreibung und Umlaute egal."""
    soll = pruefe(bestand, {"suche": text, "pro_seite": 500})
    if feld is None:
        assert not soll
    else:
        assert soll, f"Suche {text!r} muss Treffer in {feld} liefern"


@pytest.mark.parametrize("status", [["importiert"], ["bestaetigt"], ["abgeglichen"], ["vorlaeufig"],
                                    ["bestaetigt", "abgeglichen"], ["importiert", "vorlaeufig", "bestaetigt",
                                                                    "abgeglichen"]])
def test_filter_status(bestand, status):
    soll = pruefe(bestand, {"status": status, "pro_seite": 500})
    assert soll and {b["status"] for b in soll} <= set(status)


@pytest.mark.parametrize("sortierung", ["datum", "-datum", "betrag", "-betrag", "empfaenger", "-empfaenger"])
def test_sortierung(bestand, sortierung):
    for seite in (1, 2, 3):
        pruefe(bestand, {"sortierung": sortierung, "seite": seite, "pro_seite": 500})
    pruefe(bestand, {"sortierung": sortierung, "konto_id": bestand.konto("Girokonto")["id"], "pro_seite": 100,
                     "seite": 4})


def test_paginierung(bestand):
    n = len(bestand.alle)
    gesehen = []
    for seite in range(1, n // 97 + 3):
        d = bestand.api.seite(seite=seite, pro_seite=97)
        assert d["gesamt"] == n
        gesehen.extend(b["id"] for b in d["eintraege"])
    assert sorted(gesehen) == sorted(b["id"] for b in bestand.alle) and len(gesehen) == n
    d = bestand.api.seite(seite=10_000, pro_seite=500)
    assert d["eintraege"] == [] and d["gesamt"] == n and d["seite"] == 10_000
    pruefe(bestand, {"seite": 3, "pro_seite": 1})


def test_kombination_beispiel(bestand):
    p = {"konto_id": bestand.konto("Girokonto")["id"], "von": "2023-01-01", "bis": "2023-06-30",
         "betrag_max": -1000, "empfaenger_id": next(e["id"] for e in bestand.empfaenger
                                                    if e["name"] == "Supermarkt Frischekorb"),
         "status": ["importiert", "bestaetigt"], "sortierung": "-betrag", "pro_seite": 20, "seite": 2}
    pruefe(bestand, p)


@pytest.mark.parametrize("p", [
    {"konto_id": 999999}, {"kategorie_id": 999999}, {"tag_id": [999999]}, {"empfaenger_id": 999999},
    {"kategorie_id": 999999, "unterkategorien": True},
], ids=str)
def test_unbekannte_ids_leere_liste(bestand, p):
    d = bestand.api.seite(**p)
    assert d["eintraege"] == [] and d["gesamt"] == 0 and d["summe"] == 0


@pytest.mark.parametrize("p", [
    {"von": "2024-02-01", "bis": "2024-01-31"}, {"betrag_min": 5, "betrag_max": 4}, {"sortierung": "id"},
    {"sortierung": "datum,betrag"}, {"seite": 0}, {"pro_seite": 0}, {"pro_seite": 501}, {"verwendungszweck": ""},
    {"suche": ""}, {"status": ["storniert"]}, {"von": "2024-02-30"}, {"bis": "gestern"}, {"konto_id": "eins"},
    {"betrag_min": "1.5"}, {"tag_id": ["x"]}, {"unterkategorien": "vielleicht"},
], ids=str)
def test_ungueltige_parameter(bestand, p):
    r = bestand.api.get("/api/buchungen", params=p, erwartet=422)
    assert fehlercode(r) == "validierung"


# --------------------------------------------- Kombinationen (Hypothesis)

DATUM = st.dates(min_value=dt.date(2021, 12, 1), max_value=dt.date(2025, 1, 31)).map(dt.date.isoformat)
TEXTE = ["miete", "Café", "CAFE", "müller", "MUELLER", "tilgung", "urlaub", "Steuer", "0815", "/2023", "e", "ä",
         "Kartenzahlung", "Ölgemälde", "zinsen q4", "Prüfen"]


@st.composite
def filter_params(draw, best: Bestand):
    p: dict = {}
    ids_konten = [k["id"] for k in best.konten] + [999999]
    if draw(st.booleans()):
        p["konto_id"] = draw(st.sampled_from(ids_konten))
    if draw(st.booleans()):
        a, b = sorted([draw(DATUM), draw(DATUM)])
        if draw(st.booleans()):
            p["von"] = a
        if draw(st.booleans()):
            p["bis"] = b
    if draw(st.integers(0, 3)) == 0:
        a, b = sorted([draw(st.integers(-200_000, 200_000)), draw(st.integers(-200_000, 200_000))])
        if draw(st.booleans()):
            p["betrag_min"] = a
        if draw(st.booleans()):
            p["betrag_max"] = b
    if draw(st.integers(0, 3)) == 0:
        p["kategorie_id"] = draw(st.sampled_from(ids_konten))
        p["unterkategorien"] = draw(st.booleans())
    if draw(st.integers(0, 3)) == 0:
        p["tag_id"] = draw(st.lists(st.sampled_from([t["id"] for t in best.tags]), max_size=2, unique=True))
    if draw(st.integers(0, 4)) == 0:
        p["empfaenger_id"] = draw(st.sampled_from([e["id"] for e in best.empfaenger] + [999999]))
    elif draw(st.integers(0, 5)) == 0:
        p["ohne_empfaenger"] = True
    if draw(st.integers(0, 3)) == 0:
        p["verwendungszweck"] = draw(st.sampled_from(TEXTE))
    if draw(st.integers(0, 3)) == 0:
        p["suche"] = draw(st.sampled_from(TEXTE))
    if draw(st.integers(0, 3)) == 0:
        p["status"] = draw(st.lists(st.sampled_from(["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"]),
                                    min_size=1, max_size=3, unique=True))
    if draw(st.booleans()):
        p["sortierung"] = draw(st.sampled_from(["datum", "-datum", "betrag", "-betrag", "empfaenger", "-empfaenger"]))
    p["pro_seite"] = draw(st.sampled_from([1, 7, 50, 500]))
    p["seite"] = draw(st.integers(1, 4))
    return p


@given(data=st.data())
def test_filterkombinationen_gegen_orakel(bestand, data):
    pruefe(bestand, data.draw(filter_params(bestand)))
