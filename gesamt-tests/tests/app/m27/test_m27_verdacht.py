"""M27: Label „Verdächtig“ (sammel.md 1; E-249, E-250) – REST, kern.

Erwartungen unabhängig aus der Regel (robustes z) über ``tests/hilfen/m27.verdacht_soll``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m27 import (alle_mit_verdacht, kontoarten, mad, median, pruefe_text, robustes_z, verdacht_ist,
                              verdacht_soll)

pytestmark = pytest.mark.kern


@pytest.fixture
def api(tmp_path):
    a = neue_api(tmp_path)
    a.k = {"giro": a.konto("Girokonto")["id"], "spar": a.konto("Tagesgeld", "sparkonto")["id"],
           "karte": a.konto("Kreditkarte", "kreditkonto")["id"], "leb": a.konto("Lebensmittel", "aufwand")["id"]}
    return a


def _b(api, eid, betrag, status="bestaetigt", datum="2024-03-01", konto="giro", **kw):
    k = api.k
    anlegen = "bestaetigt" if status == "abgeglichen" else status
    bid = api.buchung(datum, [(k[konto], betrag), (k["leb"], -betrag)], empfaenger_id=eid, status=anlegen,
                      **kw)["id"]
    if status == "abgeglichen":   # nur über die Statusänderung erreichbar (M12)
        api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [bid], "status": "abgeglichen"},
                 erwartet=200)
    return bid


def _pruefe_alle(api):
    alle = alle_mit_verdacht(api)
    assert verdacht_ist(alle) == verdacht_soll(alle, kontoarten(api))
    for b in alle:
        if "verdacht" in b:
            pruefe_text(b)
    return {b["id"]: b for b in alle}


# ------------------------------------------------------------------ Hilfsrechnungen gegen die Definition

def test_median_und_mad_der_definition():
    assert median([3, 1, 2]) == 2 and median([1, 2, 3, 6]) == 2 and median([-3, -2]) == -3  # Richtung −∞
    assert mad([1000, 1000, 1000, 1000]) == 0 and mad([100, 200, 300, 400]) == 100
    assert robustes_z(1000, 1000, 0) == 0 and robustes_z(1001, 1000, 0) is None
    assert robustes_z(1500, 1000, 100) == 500 * 100 // 148


# ------------------------------------------------------------------ 1.1 Anfordern


def test_nur_auf_anfrage_und_parameter(api):
    e = api.empfaenger("Neuer Laden (fiktiv)")["id"]
    bid = _b(api, e, -1234, status="importiert")
    ohne = api.get(f"/api/buchungen/{bid}", erwartet=200).daten
    assert "verdacht" not in ohne
    assert api.get(f"/api/buchungen/{bid}", params={"verdacht": "nein"}, erwartet=200).daten == ohne
    mit = api.get(f"/api/buchungen/{bid}", params={"verdacht": "ja"}, erwartet=200).daten
    assert mit["verdacht"]["grund"] == "empfaenger"
    assert {k: v for k, v in mit.items() if k != "verdacht"} == ohne
    assert all("verdacht" not in b for b in api.seite()["eintraege"])
    assert api.seite(verdacht="nein") == api.seite()
    (x,) = api.seite(verdacht="ja")["eintraege"]
    assert x["verdacht"] == mit["verdacht"]
    s = api.get("/api/suche", params={"q": "Laden"}, erwartet=200).daten
    assert all("verdacht" not in b for b in s["buchungen"])
    s = api.get("/api/suche", params={"q": "Laden", "verdacht": "ja"}, erwartet=200).daten
    assert [b["verdacht"]["grund"] for b in s["buchungen"]] == ["empfaenger"]
    for pfad in ("/api/buchungen", f"/api/buchungen/{bid}", "/api/suche?q=Laden"):
        for wert in ("JA", "1", "true", ""):
            r = api.get(pfad, params={"verdacht": wert})
            assert r.status_code == 422 and fehlercode(r) == "validierung", (pfad, wert)


def test_andere_antworten_nie_mit_verdacht(api):
    e = api.empfaenger("Unbekannt (fiktiv)")["id"]
    k = api.k
    neu = api.post("/api/buchungen", json={"datum": "2024-03-02", "empfaenger_id": e, "status": "importiert",
                                           "splits": [{"konto_id": k["giro"], "betrag": -500},
                                                      {"konto_id": k["leb"], "betrag": 500}]},
                   params={"verdacht": "ja"}, erwartet=201).daten
    assert "verdacht" not in neu
    p = api.patch(f"/api/buchungen/{neu['id']}", json={"verwendungszweck": "x"}, params={"verdacht": "ja"},
                  erwartet=200).daten
    assert "verdacht" not in p
    assert all("verdacht" not in str(a) for a in aenderungen_seit(api, 0)), "nie im Protokoll"


# ------------------------------------------------------------------ 1.2 Regel


def test_empfaenger_unbekannt_und_ohne_empfaenger(api):
    e = api.empfaenger("Erstkontakt (fiktiv)")["id"]
    a = _b(api, e, -1000, status="importiert")
    b = _b(api, e, -2000, status="vorlaeufig", konto="spar")
    ohne = api.buchung("2024-03-03", [(api.k["giro"], -700), (api.k["leb"], 700)], status="importiert")["id"]
    x = _pruefe_alle(api)
    assert x[a]["verdacht"]["grund"] == x[b]["verdacht"]["grund"] == "empfaenger"
    assert "verdacht" not in x[ohne]
    assert "Erstkontakt (fiktiv)" in x[a]["verdacht"]["text"]


def test_bestaetigt_hat_nie_ein_label(api):
    e = api.empfaenger("Nur bestätigt (fiktiv)")["id"]
    ids = [_b(api, e, -1000, status=s) for s in ("bestaetigt", "abgeglichen")]
    x = _pruefe_alle(api)
    assert all("verdacht" not in x[i] for i in ids)


def test_betrag_ohne_streuung(api):
    e = api.empfaenger("Fester Betrag (fiktiv)")["id"]
    for i in range(4):
        _b(api, e, -5000, datum=f"2024-0{i + 1}-01")
    knapp = _b(api, e, -7400, status="importiert")       # |w−m| = 2400 ≤ 50 % von 5000 → kein Label
    gross = _b(api, e, -7600, status="importiert")       # 2600 > 2500 und ≥ 2000 → Label
    klein = _b(api, e, -5000, status="importiert")
    x = _pruefe_alle(api)
    assert "verdacht" not in x[knapp] and "verdacht" not in x[klein]
    assert x[gross]["verdacht"]["grund"] == "betrag"
    e2 = api.empfaenger("Kleiner Betrag (fiktiv)")["id"]
    for i in range(4):
        _b(api, e2, -1000, datum=f"2024-0{i + 1}-02")
    unter_20 = _b(api, e2, -2900, status="importiert")   # > 50 %, aber < 20,00 € → kein Label
    ueber_20 = _b(api, e2, -3000, status="importiert")
    x = _pruefe_alle(api)
    assert "verdacht" not in x[unter_20] and x[ueber_20]["verdacht"]["grund"] == "betrag"


def test_betrag_mit_streuung_robustes_z(api):
    e = api.empfaenger("Schwankend (fiktiv)")["id"]
    werte = [-4000, -4200, -4400, -4600, -4800]           # Median −4400, MAD 200, Skala 296
    for i, w in enumerate(werte):
        _b(api, e, w, datum=f"2024-0{i + 1}-03")
    grenze_drunter = _b(api, e, -4400 - 1035, status="importiert")   # z = 1035·100//296 = 349
    grenze_drauf = _b(api, e, -4400 - 1036, status="importiert")     # z = 350
    x = _pruefe_alle(api)
    assert robustes_z(-5435, -4400, 200) == 349 and robustes_z(-5436, -4400, 200) == 350
    assert "verdacht" not in x[grenze_drunter]
    assert x[grenze_drauf]["verdacht"]["grund"] == "betrag"


def test_weniger_als_vier_und_ohne_zahlungsbetrag(api):
    e = api.empfaenger("Wenig Daten (fiktiv)")["id"]
    for i in range(3):
        _b(api, e, -1000, datum=f"2024-0{i + 1}-04")
    # Bestätigte Buchung ohne Zahlungsbetrag zählt nicht mit (nur Kreditkonto bzw. zwei Zahlungskonten)
    k = api.k
    api.buchung("2024-05-04", [(k["karte"], -1000), (k["leb"], 1000)], empfaenger_id=e, status="bestaetigt")
    api.buchung("2024-05-05", [(k["giro"], -1000), (k["spar"], 500), (k["leb"], 500)], empfaenger_id=e,
                status="bestaetigt")
    weit = _b(api, e, -90000, status="importiert")
    x = _pruefe_alle(api)
    assert "verdacht" not in x[weit], "nur drei Zahlungsbeträge (|W| < 4)"
    _b(api, e, -1000, datum="2024-05-06")
    ohne_zb = api.buchung("2024-05-07", [(k["karte"], -90000), (k["leb"], 90000)], empfaenger_id=e,
                          status="importiert")["id"]
    x = _pruefe_alle(api)
    assert x[weit]["verdacht"]["grund"] == "betrag"
    assert "verdacht" not in x[ohne_zb], "B ohne Zahlungsbetrag"


def test_regel_ueber_alle_konten_und_filterunabhaengig(api):
    e = api.empfaenger("Zwei Konten (fiktiv)")["id"]
    for i, konto in enumerate(("giro", "giro", "spar", "spar")):
        _b(api, e, -2500, datum=f"2024-0{i + 1}-05", konto=konto)
    b = _b(api, e, -9900, status="importiert")
    gefiltert = api.get("/api/buchungen", params={"konto_id": api.k["giro"], "status": "importiert",
                                                  "verdacht": "ja"}, erwartet=200).daten["eintraege"]
    assert [x["verdacht"]["grund"] for x in gefiltert if x["id"] == b] == ["betrag"]


# ------------------------------------------------------------------ 1.3 Bestätigen


def test_bestaetigen_aendert_auch_andere(api):
    e = api.empfaenger("Bald bekannt (fiktiv)")["id"]
    a = _b(api, e, -1500, status="importiert")
    b = _b(api, e, -1600, status="importiert", datum="2024-03-09")
    x = _pruefe_alle(api)
    assert x[a]["verdacht"]["grund"] == x[b]["verdacht"]["grund"] == "empfaenger"
    api.post("/api/buchungen/mehrfach/aendern", json={"buchung_ids": [a], "status": "bestaetigt"}, erwartet=200)
    x = _pruefe_alle(api)
    assert "verdacht" not in x[a] and "verdacht" not in x[b], "„Empfänger unbekannt“ entfällt für alle"


def test_szenario_bestaetigen_durch_person(api):
    """sammel.md 2 (Szenario): Tag der Person und Status bestätigt in einer Anfrage (PATCH, E-250)."""
    e = api.empfaenger("Bestätigungsfall (fiktiv)")["id"]
    bid = _b(api, e, -2100, status="importiert")
    tag = api.tag("Torsten")["id"]
    a0 = letzte_aenderung_id(api)
    api.patch(f"/api/buchungen/{bid}", json={"tag_ids": [tag], "status": "bestaetigt"}, erwartet=200)
    assert len(aenderungen_seit(api, a0)) == 1, "eine Änderung"
    b = api.get(f"/api/buchungen/{bid}", params={"verdacht": "ja"}, erwartet=200).daten
    assert b["status"] == "bestaetigt" and [t["name"] for t in b["tags"]] == ["Torsten"]
    assert "verdacht" not in b


# ------------------------------------------------------------------ Zufall gegen die Regel

STATUS = st.sampled_from(["importiert", "vorlaeufig", "bestaetigt", "abgeglichen"])


@given(st.lists(st.tuples(st.integers(0, 2), st.sampled_from([-5000, -5100, -4900, -5000, -9000, -1000, 2000,
                                                               -5050, -12000]),
                          STATUS, st.sampled_from(["giro", "spar", "karte"])), min_size=1, max_size=14))
def test_zufall_gegen_regel(tmp_path_factory, daten):
    api = neue_api(tmp_path_factory.mktemp("z"))
    api.k = {"giro": api.konto("Girokonto")["id"], "spar": api.konto("Tagesgeld", "sparkonto")["id"],
             "karte": api.konto("Kreditkarte", "kreditkonto")["id"], "leb": api.konto("Leb", "aufwand")["id"]}
    emp = [api.empfaenger(f"Zufall {i} (fiktiv)")["id"] for i in range(3)]
    for n, (e, betrag, status, konto) in enumerate(daten):
        _b(api, emp[e], betrag, status=status, konto=konto, datum=f"2024-{n % 12 + 1:02d}-10")
    _pruefe_alle(api)
