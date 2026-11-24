"""Globale Invarianten (T 3) eigenschaftsbasiert mit zufälligen Operationsfolgen.

Nach jeder Operation gilt:
1. Summe aller Splits jeder Buchung ist exakt 0, jede Buchung hat ≥ 2 Splits.
2. Beträge sind ganze Zahlen (JSON-Ganzzahl), nie Gleitkommazahlen.
3. Saldo eines Kontos = Summe seiner Splits (auch mit Stichtag), saldo_gesamt rekursiv.
4. Summe aller Kontensalden ist 0.
Zusätzlich wird der Bestand mit einem unabhängigen Modell verglichen; abgelehnte
Operationen dürfen nichts verändern.

T 3.5/3.6 (Änderungsprotokoll, Rückgängig) sind nicht Teil von Meilenstein 1
(E-022); T 3.7 (Idempotenz) steht in test_idempotenz.py.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode

pytestmark = pytest.mark.kern

# Kontenrahmen je Beispiel: (Schlüssel, Art, Elternschlüssel)
RAHMEN = [
    ("giro", "girokonto", None), ("spar", "sparkonto", None), ("kk", "kreditkonto", None),
    ("ek", "eigenkapital", None), ("geh", "ertrag", None), ("wohn", "aufwand", None),
    ("miete", "aufwand", "wohn"), ("strom", "aufwand", "miete"), ("leb", "aufwand", None),
]
BESTAND = {"giro", "spar", "kk"}
KATEGORIE = {"geh", "wohn", "miete", "strom", "leb"}
SCHLUESSEL = [r[0] for r in RAHMEN]
STATUS_NEU = ["importiert", "vorlaeufig", "bestaetigt"]
UEBERGAENGE = {("importiert", "bestaetigt"), ("vorlaeufig", "bestaetigt"), ("bestaetigt", "abgeglichen"),
               ("vorlaeufig", "abgeglichen")}   # vorläufig → bestätigt seit D-257

datum = st.dates(min_value=dt.date(2023, 12, 25), max_value=dt.date(2024, 1, 10)).map(dt.date.isoformat)
betrag = st.one_of(st.integers(-10_000, 10_000), st.integers(-10**9, 10**9), st.sampled_from([0, 1, -1]))


@st.composite
def splits(draw):
    n = draw(st.integers(0, 6))
    konten = draw(st.lists(st.sampled_from(SCHLUESSEL), min_size=n, max_size=n))
    betraege = draw(st.lists(betrag, min_size=n, max_size=n))
    if n >= 1 and draw(st.integers(0, 4)) > 0:  # meist ausgeglichen
        betraege[-1] = -sum(betraege[:-1])
    return list(zip(konten, betraege))


operation = st.one_of(
    st.tuples(st.just("neu"), datum, splits(), st.sampled_from(STATUS_NEU)),
    st.tuples(st.just("ersetzen"), st.integers(0, 50), splits()),
    st.tuples(st.just("loeschen"), st.integers(0, 50)),
    st.tuples(st.just("kategorie"), st.integers(0, 50), st.sampled_from(SCHLUESSEL)),
    st.tuples(st.just("datum"), st.integers(0, 50), datum),
    st.tuples(st.just("status"), st.integers(0, 50), st.sampled_from(STATUS_NEU + ["abgeglichen"])),
)


@dataclass
class Modell:
    ids: dict[str, int]
    buchungen: dict[int, dict] = field(default_factory=dict)  # id -> {datum, splits[(schl, betrag)], status}

    def saldo(self, stichtag: str | None = None) -> tuple[dict[str, int], dict[str, int]]:
        saldo: dict[str, int] = defaultdict(int)
        anzahl: dict[str, int] = defaultdict(int)
        for b in self.buchungen.values():
            if stichtag and b["datum"] > stichtag:
                continue
            for schl, x in b["splits"]:
                saldo[schl] += x
            for schl in {s for s, _ in b["splits"]}:
                anzahl[schl] += 1
        return saldo, anzahl


def _gegensplits(splits_):
    return [i for i, (schl, _) in enumerate(splits_) if schl not in BESTAND]


def _gesamt(saldo: dict[str, int], schl: str) -> int:
    return saldo[schl] + sum(_gesamt(saldo, r[0]) for r in RAHMEN if r[2] == schl)


def pruefe(api, modell: Modell, stichtag: str | None = None) -> None:
    liste = api.alle_buchungen()
    rueck = {v: k for k, v in modell.ids.items()}
    ist = {}
    split_saldo: dict[int, int] = defaultdict(int)
    for b in liste:
        assert len(b["splits"]) >= 2, f"Buchung {b['id']} hat < 2 Splits"
        for s in b["splits"]:
            assert type(s["betrag"]) is int, f"Betrag {s['betrag']!r} ist keine Ganzzahl"
        assert sum(s["betrag"] for s in b["splits"]) == 0, f"Buchung {b['id']} unausgeglichen"
        if stichtag is None or b["datum"] <= stichtag:
            for s in b["splits"]:
                split_saldo[s["konto_id"]] += s["betrag"]
        ist[b["id"]] = {"datum": b["datum"], "status": b["status"],
                        "splits": [(rueck[s["konto_id"]], s["betrag"]) for s in b["splits"]]}
    if stichtag is None:
        assert ist == modell.buchungen, "Bestand weicht vom Modell ab"
    u = api.uebersicht(stichtag)
    assert u["summe_gesamt"] == 0, "Summe aller Salden ≠ 0"
    assert sum(k["saldo"] for k in u["konten"]) == 0
    saldo, anzahl = modell.saldo(stichtag)
    for k in u["konten"]:
        schl = rueck[k["konto_id"]]
        assert type(k["saldo"]) is int and type(k["saldo_gesamt"]) is int
        assert k["saldo"] == saldo[schl] == split_saldo[k["konto_id"]], f"Saldo {schl}"
        assert k["saldo_gesamt"] == _gesamt(saldo, schl), f"saldo_gesamt {schl}"
        assert k["anzahl_buchungen"] == anzahl[schl], f"anzahl_buchungen {schl}"
    assert u["summe_bestand"] == sum(saldo[s] for s in BESTAND)


def _waehle(modell: Modell, n: int) -> int | None:
    ids = sorted(modell.buchungen)
    return ids[n % len(ids)] if ids else None


def _body_splits(modell, sp):
    return [{"konto_id": modell.ids[s], "betrag": x} for s, x in sp]


def _erwarteter_split_fehler(sp) -> str | None:
    if len(sp) < 2:
        return "zu_wenige_splits"
    if sum(x for _, x in sp) != 0:
        return "buchung_unausgeglichen"
    return None


def fuehre_aus(api, modell: Modell, op) -> None:
    art = op[0]
    if art == "neu":
        _, d, sp, status = op
        r = api.post("/api/buchungen", json={"datum": d, "splits": _body_splits(modell, sp), "status": status})
        fehler = _erwarteter_split_fehler(sp)
        if fehler:
            assert r.status_code == 422 and fehlercode(r) == fehler, r.text
        else:
            assert r.status_code == 201, r.text
            modell.buchungen[r.daten["id"]] = {"datum": d, "splits": list(sp), "status": status}
        return
    bid = _waehle(modell, op[1])
    if bid is None:
        return
    b = modell.buchungen[bid]
    gesperrt = b["status"] == "abgeglichen"
    if art == "ersetzen":
        sp = op[2]
        r = api.put(f"/api/buchungen/{bid}/splits", json={"splits": _body_splits(modell, sp)})
        fehler = _erwarteter_split_fehler(sp)
        if gesperrt:
            assert r.status_code in (409, 422), r.text
            if r.status_code == 409:
                assert fehlercode(r) == "buchung_gesperrt"
            else:
                assert fehler, f"gesperrte Buchung, gültige Splits: erwartet 409, erhalten {r.text}"
        elif fehler:
            assert r.status_code == 422 and fehlercode(r) == fehler, r.text
        else:
            assert r.status_code == 200, r.text
            b["splits"] = list(sp)
    elif art == "loeschen":
        r = api.delete(f"/api/buchungen/{bid}")
        if gesperrt:
            assert r.status_code == 409 and fehlercode(r) == "buchung_gesperrt"
        else:
            assert r.status_code == 204, r.text
            del modell.buchungen[bid]
    elif art == "kategorie":
        ziel = op[2]
        r = api.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": modell.ids[ziel]})
        gegen = _gegensplits(b["splits"])
        unveraendert = len(gegen) == 1 and b["splits"][gegen[0]][0] == ziel
        if gesperrt and unveraendert and r.status_code == 200:
            pass  # Setzen des bereits gesetzten Werts: 200 oder 409 zulässig
        elif gesperrt:
            assert r.status_code == 409 and fehlercode(r) == "buchung_gesperrt", r.text
        elif ziel not in KATEGORIE or len(gegen) != 1:
            assert r.status_code == 422, r.text
            assert fehlercode(r) in ("kategorie_ungueltig", "nicht_kategorisierbar")
            if ziel not in KATEGORIE and len(gegen) == 1:
                assert fehlercode(r) == "kategorie_ungueltig"
            if ziel in KATEGORIE:
                assert fehlercode(r) == "nicht_kategorisierbar"
        else:
            assert r.status_code == 200, r.text
            i = gegen[0]
            b["splits"][i] = (ziel, b["splits"][i][1])
            assert r.daten["kategorie_id"] == modell.ids[ziel]
    elif art == "datum":
        r = api.patch(f"/api/buchungen/{bid}", json={"datum": op[2]})
        if gesperrt and op[2] == b["datum"] and r.status_code == 200:
            pass  # Setzen des bereits gesetzten Werts: 200 oder 409 zulässig
        elif gesperrt:
            assert r.status_code == 409 and fehlercode(r) == "buchung_gesperrt", r.text
        else:
            assert r.status_code == 200, r.text
            b["datum"] = op[2]
    elif art == "status":
        neu = op[2]
        r = api.patch(f"/api/buchungen/{bid}", json={"status": neu})
        if neu == b["status"] or (b["status"], neu) in UEBERGAENGE:
            assert r.status_code == 200, r.text
            b["status"] = neu
        else:
            assert r.status_code == 409 and fehlercode(r) == "status_uebergang_unzulaessig", r.text


def _neue_app(api_fabrik) -> tuple[object, Modell]:
    api = api_fabrik()
    ids: dict[str, int] = {}
    for schl, art, eltern in RAHMEN:
        body = {"name": schl, "art": art}
        if eltern:
            body["eltern_id"] = ids[eltern]
        ids[schl] = api.post("/api/konten", json=body, erwartet=201).daten["id"]
    return api, Modell(ids)


@given(ops=st.lists(operation, min_size=1, max_size=12), stichtag=datum)
def test_invarianten_nach_jeder_operation(api_fabrik, ops, stichtag):
    api, modell = _neue_app(api_fabrik)
    for op in ops:
        fuehre_aus(api, modell, op)
        pruefe(api, modell)
    pruefe(api, modell, stichtag)


@given(st.lists(st.integers(1, 99), min_size=2, max_size=40))
def test_viele_kleine_betraege_exakt(api_fabrik, centbetraege):
    """Viele Cent-Beträge summieren sich exakt (kein Gleitkomma-Rundungsfehler)."""
    api, modell = _neue_app(api_fabrik)
    sp = [("leb", c) for c in centbetraege] + [("giro", -sum(centbetraege))]
    r = api.post("/api/buchungen", json={"datum": "2024-01-01", "splits": _body_splits(modell, sp)}, erwartet=201)
    modell.buchungen[r.daten["id"]] = {"datum": "2024-01-01", "splits": sp, "status": "bestaetigt"}
    for _ in range(3):
        sp2 = [("giro", 10), ("leb", -3), ("leb", -3), ("leb", -4)]
        r = api.post("/api/buchungen", json={"datum": "2024-01-02", "splits": _body_splits(modell, sp2)},
                     erwartet=201)
        modell.buchungen[r.daten["id"]] = {"datum": "2024-01-02", "splits": sp2, "status": "bestaetigt"}
    pruefe(api, modell)
