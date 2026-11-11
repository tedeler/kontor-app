"""Eigene Entwicklungstests zum Feature „wiederkehrend-begruendung“ (D-115, D-116): zusätzliche Zahlungen um einen
Termin brechen die Kette nicht; Begründung je Buchung über ``GET /api/buchungen/{id}/wiederkehrend``."""

from __future__ import annotations

import pytest


@pytest.fixture
def bb(client):
    g = client.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = client.post("/api/konten", json={"name": "Abo", "art": "aufwand"}).json()["id"]
    e = client.post("/api/empfaenger", json={"name": "Abo AG"}).json()["id"]

    def buchen(datum, betrag=-999, empf=e):
        r = client.post("/api/buchungen", json={"datum": datum, "empfaenger_id": empf,
                                                "splits": [{"konto_id": g, "betrag": betrag},
                                                           {"konto_id": kat, "betrag": -betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return client, buchen


def serien(client, stichtag):
    return client.get("/api/wiederkehrend", params={"stichtag": stichtag}).json()["serien"]


def warum(client, bid, stichtag="2024-06-30"):
    r = client.get(f"/api/buchungen/{bid}/wiederkehrend", params={"stichtag": stichtag})
    assert r.status_code == 200, r.text
    return r.json()


def test_doppelte_zahlung_wird_uebersprungen(bb):
    c, buchen = bb
    ids = [buchen(t) for t in ("2024-01-15", "2024-02-15", "2024-03-15")]
    dup = buchen("2024-03-13")  # Dublette mit abweichendem Datum (z. B. Valuta)
    (s,) = serien(c, "2024-03-31")
    assert s["buchung_ids"] == ids and s["anzahl"] == 3
    w = warum(c, dup, "2024-03-31")
    assert w["urteil"] == "zusaetzlich" and w["eintraege"][0]["urteil"] == "zusaetzlich"
    w = warum(c, ids[1], "2024-03-31")
    assert w["urteil"] == "wiederkehrend" and w["eintraege"][0]["glied"] == 2


def test_gleicher_betrag_wird_bevorzugt(bb):
    c, buchen = bb
    a = buchen("2024-01-15", -500)
    buchen("2024-02-14", -500)
    extra = buchen("2024-02-16", -123)  # näher am Termin, aber anderer Betrag
    b = buchen("2024-03-15", -500)
    (s,) = serien(c, "2024-03-31")
    assert s["buchung_ids"][0] == a and s["buchung_ids"][-1] == b and extra not in s["buchung_ids"]


def test_fremde_zahlung_zwischen_terminen_bricht(bb):
    c, buchen = bb
    for t in ("2024-01-15", "2024-02-15", "2024-03-15"):
        buchen(t)
    buchen("2024-03-01")  # mitten zwischen zwei Terminen
    assert serien(c, "2024-03-31") == []
    w = warum(c, buchen("2024-04-15"), "2024-04-30")
    (e,) = w["eintraege"]
    assert e["urteil"] == "keine_serie" and e["rhythmen"][0]["schritte"][-1]["grund"] == "fremde_zahlung"


def test_woechentliche_zahlungen_sind_keine_monatsserie(bb):
    c, buchen = bb
    import datetime as dt
    d = dt.date(2024, 1, 1)
    while d <= dt.date(2024, 5, 31):
        buchen(d.isoformat())
        d += dt.timedelta(days=7)
    assert serien(c, "2024-05-31") == []


def test_begruendung_vor_beginn_und_ausschluesse(bb, client):
    c, buchen = bb
    alt = buchen("2023-06-15")
    for t in ("2024-01-15", "2024-02-15", "2024-03-15"):
        buchen(t)
    w = warum(c, alt)
    assert w["eintraege"][0]["urteil"] == "vor_beginn"
    schritte = w["eintraege"][0]["rhythmen"][0]["schritte"]
    assert [s["ergebnis"] for s in schritte] == ["verbunden", "verbunden", "bruch"]
    assert schritte[-1]["grund"] == "abstand" and schritte[-1]["text"]
    g = client.get("/api/konten").json()[0]["id"]
    ohne = client.post("/api/buchungen", json={"datum": "2024-01-01", "splits": [
        {"konto_id": g, "betrag": -1}, {"konto_id": g + 1, "betrag": 1}]}).json()["id"]
    assert warum(c, ohne)["urteil"] == "ausgeschlossen"
    assert warum(c, alt, "2023-01-01")["urteil"] == "ausgeschlossen"
    assert c.get("/api/buchungen/9999/wiederkehrend").status_code == 404
    assert c.get(f"/api/buchungen/{alt}/wiederkehrend", params={"stichtag": "x"}).status_code == 422


def test_dublette_am_ersten_glied(bb):
    c, buchen = bb
    dup = buchen("2024-01-13")
    ids = [buchen(t) for t in ("2024-01-15", "2024-02-15", "2024-03-15")]
    (s,) = serien(c, "2024-03-31")
    assert s["buchung_ids"] == ids
    w = warum(c, dup, "2024-03-31")["eintraege"][0]
    assert w["urteil"] == "zusaetzlich"
    assert w["rhythmen"][0]["schritte"][-1]["grund"] == "kein_vorgaenger"


def test_anker_am_juengsten_termin_nach_betrag(bb):
    c, buchen = bb
    ids = [buchen(t, -32032) for t in ("2024-08-04", "2024-09-04", "2024-10-05", "2024-11-04")]
    extra = buchen("2024-11-04", -5000)  # später angelegt, gleicher Tag, anderer Betrag
    (s,) = serien(c, "2024-11-11")
    assert s["buchung_ids"] == ids and s["betrag"] == -32032
    w = warum(c, extra, "2024-11-11")
    (e,) = w["eintraege"]
    assert w["urteil"] == "zusaetzlich"
    schritte = e["rhythmen"][0]["schritte"]
    assert schritte[0]["ergebnis"] == "anker" and "Betrag" in schritte[0]["text"]
    assert "Betrag" in e["text"]
    rollen = {b["buchung_id"]: b["rolle"] for b in e["buchungen"]}
    assert rollen[extra] == "zusaetzlich" and all(rollen[i] == "glied" for i in ids)
    w = warum(c, ids[-1], "2024-11-11")
    assert w["urteil"] == "wiederkehrend" and w["eintraege"][0]["glied"] == 4


def test_anker_laengste_kette(bb):
    c, buchen = bb
    ids = [buchen(t) for t in ("2024-01-15", "2024-02-15", "2024-03-15")]
    spaet = buchen("2024-03-19")  # jünger, aber nur 4 Tage später: Kette ab 15.03. ist nicht kürzer
    (s,) = serien(c, "2024-03-31")
    assert s["anzahl"] == 3 and spaet not in s["buchung_ids"] or s["buchung_ids"][-1] == spaet
