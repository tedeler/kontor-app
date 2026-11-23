"""Dublettenerkennung beim Import und Auflösen von Verdachten (K 12, T 6, datenmodell.md 9 und 10.4)."""

from __future__ import annotations

import datetime as dt

import pytest
from hypothesis import given, strategies as st

from generator.iban import fiktive_iban
from tests.hilfen.api import fehlercode
from tests.hilfen.erwartung import ZAEHLFELDER, lade
from tests.hilfen.kmybau import KBuch, KBuchung, KKonto, KSplit, gzip_bytes
from tests.hilfen.normal import passend
from tests.hilfen.pfade import KMY

pytestmark = pytest.mark.kern


def lege_vorbestand_an(api, vorbestand: dict) -> dict[str, dict]:
    """Legt den manuellen Vorbestand aus dubletten.erwartung.json an; liefert ref -> Objekt."""
    ref: dict[str, dict] = {}
    for k in vorbestand["konten"]:
        felder = {"iban": k["iban"]} if k["iban"] else {}
        ref[k["ref"]] = api.konto(k["name"], k["art"], **felder)
    for e in vorbestand["empfaenger"]:
        ref[e["ref"]] = api.empfaenger(e["name"])
    giro = next(k["ref"] for k in vorbestand["konten"] if k["art"] == "girokonto")
    for b in vorbestand["buchungen"]:
        felder = {"verwendungszweck": f"Vorbestand {b['ref']}"}
        if b["empfaenger"]:
            felder["empfaenger_id"] = ref[b["empfaenger"]]["id"]
        ref[b["ref"]] = api.buchung(b["datum"], [(ref[giro]["id"], b["betrag"]),
                                                 (ref[b["kategorie"]]["id"], -b["betrag"])], **felder)
    return ref


@pytest.fixture
def dubletten(api):
    erw = lade("dubletten")
    ref = lege_vorbestand_an(api, erw["vorbestand"])
    vorher = {r: api.buchung_lesen(o["id"]) for r, o in ref.items() if r.startswith("V")}
    r = api.import_kmy(KMY / "dubletten.kmy", erwartet=200).daten
    return api, erw, ref, vorher, r


def _nach_extern(api) -> dict[str, dict]:
    aus = {}
    for b in api.alle_buchungen():
        for e in b["extern_ids"]:
            aus[e] = b
    return aus


def test_ergebnis_der_dublettenpruefung(dubletten):
    api, erw, ref, vorher, r = dubletten
    soll = erw["dubletten"]["ergebnis"]
    assert {f: r[f] for f in ZAEHLFELDER} == {f: soll[f] for f in ZAEHLFELDER}
    assert r["fehler"] == [] and r["erfolgreich"] is True
    konten = {k["id"]: k for k in api.konten()}
    for ext, kref in erw["dubletten"]["konten_zuordnung"].items():
        assert konten[ref[kref]["id"]]["extern_id"] == ext
        assert konten[ref[kref]["id"]]["name"] == ref[kref]["name"], "zugeordnetes Konto behält seinen Namen"


def test_eindeutige_dubletten_zusammengefuehrt(dubletten):
    api, erw, ref, vorher, r = dubletten
    for tid, vref in erw["dubletten"]["zusammengefuehrt"].items():
        b = api.buchung_lesen(ref[vref]["id"])
        assert b == {**vorher[vref], "extern_ids": ["kmy:" + tid]}, \
            f"{vref}: nur extern_ids darf sich ändern"
    ext = _nach_extern(api)
    for tid in erw["dubletten"]["zusammengefuehrt"]:
        assert ext["kmy:" + tid]["id"] == ref[erw["dubletten"]["zusammengefuehrt"][tid]]["id"]
    assert len(api.alle_buchungen()) == len(erw["vorbestand"]["buchungen"]) + r["buchungen_neu"]


def test_zweifelsfaelle_zur_bestaetigung(dubletten):
    api, erw, ref, vorher, r = dubletten
    ext = _nach_extern(api)
    verdachte = api.get("/api/dubletten", erwartet=200).daten
    assert [v["id"] for v in verdachte] == sorted(v["id"] for v in verdachte)
    ist = sorted((v["buchung_id"], tuple(v["kandidat_ids"]), v["grund"], v["status"]) for v in verdachte)
    soll = sorted((ext["kmy:" + v["buchung"]]["id"], tuple(sorted(ref[c]["id"] for c in v["kandidaten"])),
                   v["grund"], "offen") for v in erw["dubletten"]["verdachte"])
    assert ist == soll
    for v in verdachte:
        assert v["kandidat_ids"] == sorted(v["kandidat_ids"])
    for tid in erw["dubletten"]["neu_ohne_verdacht"]:
        assert ext["kmy:" + tid]["extern_ids"] == ["kmy:" + tid]
        assert ext["kmy:" + tid]["id"] not in {v["buchung_id"] for v in verdachte}
    # Verdachtsbuchungen sind angelegt und unverändert importiert
    for v in erw["dubletten"]["verdachte"]:
        b = ext["kmy:" + v["buchung"]]
        assert b["status"] == "importiert" and b["extern_ids"] == ["kmy:" + v["buchung"]]
    for vref, b in vorher.items():
        if vref not in erw["dubletten"]["zusammengefuehrt"].values():
            assert api.buchung_lesen(ref[vref]["id"]) == b


def test_zweimal_derselbe_kaffee_nicht_zusammengefuehrt(dubletten):
    """T 6: zwei echte gleiche Buchungen am selben Tag werden nicht automatisch zusammengeführt."""
    api, erw, ref, vorher, r = dubletten
    for vref in ("V2", "V3", "V4"):
        assert api.buchung_lesen(ref[vref]["id"])["extern_ids"] == []
    ext = _nach_extern(api)
    assert {"kmy:T000000000000000002", "kmy:T000000000000000003", "kmy:T000000000000000004"} <= set(ext)


def test_dubletten_filter_status(dubletten):
    api, erw, ref, vorher, r = dubletten
    offen = api.get("/api/dubletten", params={"status": "offen"}, erwartet=200).daten
    assert len(offen) == 5
    assert api.get("/api/dubletten", params={"status": "zusammengefuehrt"}, erwartet=200).daten == []
    assert fehlercode(api.get("/api/dubletten", params={"status": "egal"}, erwartet=422)) == "validierung"


def test_import_nach_dubletten_idempotent(dubletten):
    api, erw, ref, vorher, r = dubletten
    zustand = api.zustand()
    r2 = api.import_kmy(KMY / "dubletten.kmy", erwartet=200).daten
    assert api.zustand() == zustand
    assert (r2["buchungen_neu"], r2["buchungen_vorhanden"], r2["buchungen_zusammengefuehrt"],
            r2["buchungen_zur_pruefung"]) == (0, 10, 0, 0)


# ---------------------------------------------------------------- Auflösen


def _verdacht(api, ext_tid: str) -> dict:
    ext = _nach_extern(api)
    bid = ext["kmy:" + ext_tid]["id"]
    return next(v for v in api.get("/api/dubletten", erwartet=200).daten if v["buchung_id"] == bid)


def test_aufloesen_zusammenfuehren(dubletten):
    api, erw, ref, vorher, r = dubletten
    v = _verdacht(api, "T000000000000000002")
    salden_vorher = api.salden()
    neu = api.buchung_lesen(v["buchung_id"])
    erg = api.post(f"/api/dubletten/{v['id']}/aufloesen",
                   json={"entscheidung": "zusammenfuehren", "behalten_id": ref["V3"]["id"]}, erwartet=200).daten
    assert erg == {**v, "status": "zusammengefuehrt"}
    api.get(f"/api/buchungen/{v['buchung_id']}", erwartet=404)
    assert api.buchung_lesen(ref["V3"]["id"]) == {**vorher["V3"], "extern_ids": ["kmy:T000000000000000002"]}
    assert api.buchung_lesen(ref["V2"]["id"]) == vorher["V2"]
    salden = api.salden()
    for s in neu["splits"]:
        salden_vorher[s["konto_id"]]["saldo"] -= s["betrag"]
    assert {k: s["saldo"] for k, s in salden.items()} == {k: s["saldo"] for k, s in salden_vorher.items()}
    # erneut auflösen: Konflikt
    for body in ({"entscheidung": "keine_dublette"},
                 {"entscheidung": "zusammenfuehren", "behalten_id": ref["V3"]["id"]}):
        assert fehlercode(api.post(f"/api/dubletten/{v['id']}/aufloesen", json=body, erwartet=409)) == "konflikt"
    assert api.get("/api/dubletten", params={"status": "zusammengefuehrt"}, erwartet=200).daten == [erg]
    # die zusammengeführte Kennung wird beim nächsten Import wiedererkannt
    zustand = api.zustand()
    r2 = api.import_kmy(KMY / "dubletten.kmy", erwartet=200).daten
    assert (r2["buchungen_neu"], r2["buchungen_vorhanden"]) == (0, 10)
    assert api.zustand() == zustand


def test_aufloesen_extern_ids_sortiert(dubletten):
    api, erw, ref, vorher, r = dubletten
    v3, v4 = _verdacht(api, "T000000000000000003"), _verdacht(api, "T000000000000000004")
    for v in (v4, v3):
        api.post(f"/api/dubletten/{v['id']}/aufloesen",
                 json={"entscheidung": "zusammenfuehren", "behalten_id": ref["V4"]["id"]}, erwartet=200)
    assert api.buchung_lesen(ref["V4"]["id"])["extern_ids"] == ["kmy:T000000000000000003",
                                                                "kmy:T000000000000000004"]


def test_aufloesen_keine_dublette(dubletten):
    api, erw, ref, vorher, r = dubletten
    v = _verdacht(api, "T000000000000000005")
    zustand = {k: x for k, x in api.zustand().items() if k != "dubletten"}
    erg = api.post(f"/api/dubletten/{v['id']}/aufloesen", json={"entscheidung": "keine_dublette"},
                   erwartet=200).daten
    assert erg == {**v, "status": "keine_dublette"}
    assert {k: x for k, x in api.zustand().items() if k != "dubletten"} == zustand
    assert fehlercode(api.post(f"/api/dubletten/{v['id']}/aufloesen", json={"entscheidung": "keine_dublette"},
                               erwartet=409)) == "konflikt"


@pytest.mark.parametrize("body", [
    {"entscheidung": "zusammenfuehren"},
    {"entscheidung": "zusammenfuehren", "behalten_id": "V1"},
    {"entscheidung": "zusammenfuehren", "behalten_id": 4711},
    {"entscheidung": "loeschen"},
    {},
    {"entscheidung": "keine_dublette", "grund": "x"},
], ids=["ohne_behalten", "kein_kandidat", "unbekannt", "entscheidung_unbekannt", "leer", "feld_unbekannt"])
def test_aufloesen_validierung(dubletten, body):
    api, erw, ref, vorher, r = dubletten
    v = _verdacht(api, "T000000000000000002")
    if body.get("behalten_id") == "V1":
        body = {**body, "behalten_id": ref["V1"]["id"]}
    zustand = api.zustand()
    assert fehlercode(api.post(f"/api/dubletten/{v['id']}/aufloesen", json=body, erwartet=422)) == "validierung"
    assert api.zustand() == zustand


def test_loeschen_entfernt_offene_verdachte(dubletten):
    api, erw, ref, vorher, r = dubletten
    v5 = _verdacht(api, "T000000000000000005")
    v6 = _verdacht(api, "T000000000000000006")
    api.post(f"/api/dubletten/{v6['id']}/aufloesen", json={"entscheidung": "keine_dublette"}, erwartet=200)
    api.delete(f"/api/buchungen/{v5['buchung_id']}", erwartet=204)
    ids = {v["id"] for v in api.get("/api/dubletten", erwartet=200).daten}
    assert v5["id"] not in ids
    # Kandidat löschen: offene Verdachte mit diesem Kandidaten verschwinden, aufgelöste bleiben
    v3, v4 = _verdacht(api, "T000000000000000003"), _verdacht(api, "T000000000000000004")
    api.delete(f"/api/buchungen/{ref['V4']['id']}", erwartet=204)
    api.delete(f"/api/buchungen/{ref['V6']['id']}", erwartet=204)
    v2 = _verdacht(api, "T000000000000000002")
    ids = {v["id"] for v in api.get("/api/dubletten", erwartet=200).daten}
    assert ids == {v2["id"], v6["id"]}, "übrig: T2 (offen) und T6 (keine_dublette)"


# ----------------------------------------- unabhängiges Orakel (Hypothesis)

NAMEN = ["Café Bohne", "CAFE BOHNE", "Cafe Bohne", "Bäckerei Müller", "BAECKEREI MUELLER", "Baeckerei-Mueller"]
IBAN = fiktive_iban(6001)
BETRAEGE = [-100, -250, -1000]
START = dt.date(2024, 3, 1)

eintrag = st.tuples(st.integers(0, 6), st.sampled_from(BETRAEGE), st.one_of(st.none(), st.integers(0, len(NAMEN) - 1)))


def orakel(vorbestand, neu):
    """Unabhängige Umsetzung von datenmodell.md 10.4 für Buchungen Giro ↔ Kategorie.

    vorbestand/neu: Listen (tag, betrag, empfänger_index|None). Liefert je neuer
    Buchung ("zusammen", c) | ("verdacht", kandidaten, grund) | ("neu",).
    """
    def name(i):
        return None if i is None else NAMEN[i]
    E, A = [], []
    for tb, xb, eb in neu:
        e, a = set(), set()
        for c, (tc, xc, ec) in enumerate(vorbestand):
            if xc != xb:
                continue
            if tc == tb and passend(name(eb), name(ec)):
                e.add(c)
            elif abs(tc - tb) <= 3:
                a.add(c)
        E.append(e)
        A.append(a - e)
    aus = []
    for i in range(len(neu)):
        andere = set().union(*(E[j] for j in range(len(neu)) if j != i)) if len(neu) > 1 else set()
        if len(E[i]) == 1 and not (E[i] & andere):
            aus.append(("zusammen", next(iter(E[i]))))
        elif E[i] | A[i]:
            aus.append(("verdacht", sorted(E[i] | A[i]), "mehrdeutig" if E[i] else "aehnlich"))
        else:
            aus.append(("neu",))
    return aus


@given(st.lists(eintrag, max_size=6), st.lists(eintrag, min_size=1, max_size=6))
def test_dublettenregeln_gegen_orakel(api_fabrik, vorbestand, neu):
    api = api_fabrik()
    giro = api.konto("Giro (Hand)", "girokonto", iban=IBAN)
    kat = api.konto("Diverses", "aufwand")
    empf = [api.empfaenger(n) for n in NAMEN]
    hand = []
    for tag, betrag, e in vorbestand:
        felder = {"empfaenger_id": empf[e]["id"]} if e is not None else {}
        hand.append(api.buchung((START + dt.timedelta(days=tag)).isoformat(),
                                [(giro["id"], betrag), (kat["id"], -betrag)], **felder))
    b = KBuch()
    b.konten = [KKonto("A000001", "Girokonto", 1, "AStd::Asset", iban=IBAN),
                KKonto("A000002", "Diverses", 13, "AStd::Expense")]
    b.empfaenger = [(f"P{i + 1:06d}", n) for i, n in enumerate(NAMEN)]
    b.buchungen = [KBuchung(f"T{n + 1:018d}", (START + dt.timedelta(days=tag)).isoformat(), [
        KSplit("A000001", betrag, empfaenger="" if e is None else f"P{e + 1:06d}"),
        KSplit("A000002", -betrag, empfaenger="" if e is None else f"P{e + 1:06d}")])
        for n, (tag, betrag, e) in enumerate(neu)]
    r = api.post("/api/import/kmymoney", files={"datei": ("d.kmy", gzip_bytes(b), "x")}, erwartet=200).daten
    soll = orakel(vorbestand, neu)
    assert (r["konten_vorhanden"], r["kategorien_vorhanden"], r["empfaenger_vorhanden"]) == (1, 1, len(NAMEN))
    assert r["buchungen_zusammengefuehrt"] == sum(1 for s in soll if s[0] == "zusammen")
    assert r["buchungen_zur_pruefung"] == sum(1 for s in soll if s[0] == "verdacht")
    assert r["buchungen_neu"] == sum(1 for s in soll if s[0] != "zusammen")
    ext = _nach_extern(api)
    verdachte = {v["buchung_id"]: v for v in api.get("/api/dubletten", erwartet=200).daten}
    assert len(verdachte) == r["buchungen_zur_pruefung"]
    for n, s in enumerate(soll):
        kennung = f"kmy:T{n + 1:018d}"
        b_ist = ext[kennung]
        if s[0] == "zusammen":
            assert b_ist["id"] == hand[s[1]]["id"], f"{kennung} hätte mit Vorbestand {s[1]} zusammengeführt werden müssen"
            assert b_ist["extern_ids"] == [kennung]
        else:
            assert b_ist["id"] not in {h["id"] for h in hand}, f"{kennung} fälschlich zusammengeführt"
            if s[0] == "verdacht":
                v = verdachte[b_ist["id"]]
                assert (v["kandidat_ids"], v["grund"], v["status"]) == ([hand[c]["id"] for c in s[1]], s[2], "offen")
            else:
                assert b_ist["id"] not in verdachte
    assert api.uebersicht()["summe_gesamt"] == 0
