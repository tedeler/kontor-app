"""M24: Serien wiederkehrender Buchungen als erwartete Zahlungen in ``GET /api/erwartungen``
(erwartungen.md 13.1; E-234). Erwartungen über die Referenzkette (``tests/hilfen/m24.soll_serien``)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import benachrichtigungen, setze_zeit
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m9 import oeffne, sicherung
from tests.hilfen.m20 import abgleich, liste
from tests.hilfen.m24 import (
    Serien, gespeicherte_der_liste, nach_id, serien_der_liste, soll_serien, summen,
)

pytestmark = pytest.mark.kern


@pytest.fixture
def sz(tmp_path):
    return Serien(tmp_path)


def _manuell(api, betrag=999, richtung="ausgabe", haendler="Laden Beispiel (fiktiv)", **kw):
    return api.post("/api/erwartungen", json={"richtung": richtung, "haendler": haendler, "betrag": betrag, **kw},
                    erwartet=201).daten


def _pruefe_liste(d: dict, soll: list[dict]) -> None:
    assert nach_id(d["eintraege"]) == nach_id(soll)
    assert len(d["eintraege"]) == len(soll)
    assert (d["anzahl"], d["summe_offen"], d["ueberfaellig"]) == summen(soll)
    fristen = [e["frist"] for e in d["eintraege"]]
    assert fristen == sorted(fristen), "nach frist sortiert"


def test_soll_hat_alle_arten(sz):
    """Selbstkontrolle des Szenarios: aktive Ausgabe und Einnahme, ausbleibende Serie, beendete fehlt."""
    soll = nach_id(soll_serien(sz.api))
    assert set(soll) == {"serie:" + sz.schluessel("abo"), "serie:" + sz.schluessel("gehalt", "einnahme"),
                         "serie:" + sz.schluessel("verein")}
    assert soll["serie:" + sz.schluessel("abo")]["beschreibung"] == "monatlich, zuletzt 2024-06-05"
    assert soll["serie:" + sz.schluessel("abo")]["datum"] == "2024-07-05"
    assert soll["serie:" + sz.schluessel("gehalt", "einnahme")]["richtung"] == "eingang"
    assert soll["serie:" + sz.schluessel("verein")]["ueberfaellig"] is True


def test_ohne_angabe_keine_serien(sz):
    m = _manuell(sz.api)
    for params in ({}, {"serien": "nein"}, {"grund": "manuell", "serien": "ja"},
                   {"grund": ["bestellung", "paypal", "rueckerstattung", "manuell"]},
                   {"zustand": ["offen", "erfuellt", "guthaben", "storniert", "erledigt"]}):
        d = liste(sz.api, **params)
        assert serien_der_liste(d) == [], params
        assert [e["id"] for e in d["eintraege"]] == [m["id"]], params
        assert "konto_id" not in d["eintraege"][0] and "serie" not in d["eintraege"][0]


def test_grund_serie_allein(sz):
    _manuell(sz.api)
    _pruefe_liste(liste(sz.api, grund="serie"), soll_serien(sz.api))


def test_serien_ja_ohne_grund(sz):
    m = _manuell(sz.api)
    d = liste(sz.api, serien="ja")
    gespeichert = gespeicherte_der_liste(d)
    assert [e["id"] for e in gespeichert] == [m["id"]]
    _pruefe_liste(d, soll_serien(sz.api) + gespeichert)


def test_grund_serie_und_manuell(sz):
    m = _manuell(sz.api)
    d = liste(sz.api, grund=["serie", "manuell"])
    _pruefe_liste(d, soll_serien(sz.api) + [e for e in d["eintraege"] if e["id"] == m["id"]])
    assert len(gespeicherte_der_liste(d)) == 1
    d = liste(sz.api, grund=["serie", "paypal"])
    _pruefe_liste(d, soll_serien(sz.api))


def test_zustandsfilter(sz):
    soll = soll_serien(sz.api)
    for z in ("erfuellt", "guthaben", "storniert", "erledigt"):
        assert liste(sz.api, grund="serie", zustand=z)["eintraege"] == [], z
    _pruefe_liste(liste(sz.api, grund="serie", zustand="ueberfaellig"), [e for e in soll if e["ueberfaellig"]])
    _pruefe_liste(liste(sz.api, grund="serie", zustand=["erfuellt", "offen"]), soll)
    _pruefe_liste(liste(sz.api, serien="ja", zustand="ueberfaellig"), [e for e in soll if e["ueberfaellig"]])
    assert serien_der_liste(liste(sz.api, serien="ja", zustand="erfuellt")) == []


def test_weitere_filter(sz):
    soll = soll_serien(sz.api)
    _pruefe_liste(liste(sz.api, grund="serie", richtung="eingang"), [e for e in soll if e["richtung"] == "eingang"])
    _pruefe_liste(liste(sz.api, grund="serie", richtung="ausgabe"), [e for e in soll if e["richtung"] == "ausgabe"])
    grenze = sorted(e["frist"] for e in soll)[1]
    _pruefe_liste(liste(sz.api, grund="serie", faellig_bis=grenze), [e for e in soll if e["frist"] <= grenze])
    _pruefe_liste(liste(sz.api, grund="serie", suche="STREAMINGDIENST"), [e for e in soll if "Streaming" in
                                                                              e["haendler"]])
    _pruefe_liste(liste(sz.api, grund="serie", suche="vierteljaehrlich"),
                  [e for e in soll if e["beschreibung"].startswith("vierteljaehrlich")])
    assert liste(sz.api, grund="serie", suche="gibt-es-nicht")["eintraege"] == []


def test_unabhaengig_vom_mail_abgleich(tmp_path):
    sz = Serien(tmp_path, abgleich=False)
    d = liste(sz.api, grund="serie")
    assert d["aktiv"] is False
    _pruefe_liste(d, soll_serien(sz.api))


def test_frist_aus_konfiguration_und_ueberfaellig(tmp_path):
    sz = Serien(tmp_path, mail_abgleich_frist_tage=0)
    _pruefe_liste(liste(sz.api, grund="serie"), soll_serien(sz.api))
    setze_zeit(sz.api, "2024-07-08T12:00:00Z")
    soll = soll_serien(sz.api)
    assert any(e["ueberfaellig"] and e["serie"] == sz.schluessel("abo") for e in soll)
    _pruefe_liste(liste(sz.api, grund="serie"), soll)


def test_validierung(sz):
    for params, ort in (({"serien": "vielleicht"}, ["query", "serien"]), ({"serien": "true"}, ["query", "serien"]),
                        ({"grund": "serien"}, None)):
        r = liste(sz.api, erwartet=422, **params)
        assert fehlercode(r) == "validierung"
        if ort:
            assert any(list(x["ort"])[:2] == ort for x in r.json()["fehler"]["details"]), r.text


def test_ausgelassen_bei_zuordnung_der_letzten_buchung(sz):
    api = sz.api
    letzte, vorletzte = sz.abo[-1], sz.abo[-2]
    m = _manuell(api, kennung="")
    api.post(f"/api/erwartungen/{m['id']}/buchungen", json={"buchung_ids": [vorletzte]}, erwartet=200)
    _pruefe_liste(liste(api, grund="serie"), soll_serien(api))  # nicht die letzte Buchung: Serie bleibt
    api.delete(f"/api/erwartungen/{m['id']}/buchungen/{vorletzte}", erwartet=200)
    api.post(f"/api/erwartungen/{m['id']}/buchungen", json={"buchung_ids": [letzte]}, erwartet=200)
    assert liste(api, zustand="erfuellt")["eintraege"][0]["zustand"] == "erfuellt"
    soll = soll_serien(api, ausgelassen={letzte})
    assert "serie:" + sz.schluessel("abo") not in nach_id(soll)
    _pruefe_liste(liste(api, grund="serie"), soll)
    g = _manuell(api, betrag=250000, richtung="eingang", haendler="Arbeitgeber")
    api.post(f"/api/erwartungen/{g['id']}/buchungen", json={"buchung_ids": [sz.gehalt[-1]]}, erwartet=200)
    api.post(f"/api/erwartungen/{g['id']}/zustand", json={"zustand": "offen"}, erwartet=409)
    soll = soll_serien(api, ausgelassen={letzte, sz.gehalt[-1]})
    _pruefe_liste(liste(api, grund="serie"), soll)
    assert len(soll) == 1


@pytest.mark.parametrize("methode,pfad,koerper", [
    ("get", "", None), ("patch", "", {"haendler": "x"}), ("delete", "", None), ("get", "/kandidaten", None),
    ("post", "/zustand", {"zustand": "erledigt"}), ("post", "/buchungen", {"buchung_ids": [1]}),
    ("delete", "/buchungen/1", None),
])
def test_serieneintraege_nicht_abrufbar(sz, methode, pfad, koerper):
    sid = "serie:" + sz.schluessel("abo")
    kw = {"json": koerper} if koerper is not None else {}
    r = sz.api.anfrage(methode, f"/api/erwartungen/{sid}{pfad}", erwartet=404, **kw)
    assert fehlercode(r) == "nicht_gefunden"
    assert r.json()["fehler"]["meldung"] == "Der angeforderte Pfad existiert nicht."


def test_keine_wirkung(sz):
    api = sz.api
    a0 = letzte_aenderung_id(api)
    m0, _ = oeffne(sicherung(api))
    for _ in range(2):
        abgleich(api)
    assert letzte_aenderung_id(api) == a0, "Serien erzeugen keine Änderung"
    assert not [b for b in benachrichtigungen(api) if b["art"] == "erwartung_ueberfaellig"], \
        "keine Benachrichtigung für überfällige Serien"
    m1, _ = oeffne(sicherung(api))
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])
    assert "erwartung" not in m1["anzahl"], "Serien sind nicht in der Sicherung"
    _pruefe_liste(liste(api, grund="serie"), soll_serien(api))
