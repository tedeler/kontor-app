"""M32: Standardkategorie entfällt, Konten und Anzahlen je Empfänger, Statistik entfällt (sammel3.md 2, 3;
D-219 bis D-221, D-236/10; E-296 bis E-298) – kern."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import UNKATEGORISIERT, aenderungen_seit, bestand, erfassen, konto_id, letzte_aenderung_id

pytestmark = pytest.mark.kern


def _ohne_wirkung(api, aufruf, code, status=422):
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    r = aufruf()
    assert r.status_code == status and fehlercode(r) == code, r.text[:300]
    assert bestand(api) == vorher and aenderungen_seit(api, a0) == []


# ------------------------------------------------------------------ 2.1 Standardkategorie


def test_standardkategorie_wird_abgelehnt(api):
    kat = api.konto("Lebensmittel", "aufwand")
    giro = api.konto("Giro", "girokonto")
    _ohne_wirkung(api, lambda: api.post("/api/empfaenger", json={"name": "Laden", "standardkategorie_id": kat["id"]},
                                        erwartet=422), "kategorie_ungueltig")
    e = api.post("/api/empfaenger", json={"name": "Laden", "standardkategorie_id": None}, erwartet=201).daten
    assert e["standardkategorie_id"] is None
    for wert in (kat["id"], giro["id"], 999999):
        _ohne_wirkung(api, lambda: api.patch(f"/api/empfaenger/{e['id']}", json={"standardkategorie_id": wert},
                                             erwartet=422), "kategorie_ungueltig")
    _ohne_wirkung(api, lambda: api.patch(f"/api/empfaenger/{e['id']}", json={"standardkategorie_id": "1"},
                                         erwartet=422), "validierung")
    a0 = letzte_aenderung_id(api)
    api.patch(f"/api/empfaenger/{e['id']}", json={"standardkategorie_id": None}, erwartet=200)
    assert aenderungen_seit(api, a0) == [], "null ist ohne Wirkung"
    assert all(x["standardkategorie_id"] is None for x in api.get("/api/empfaenger", erwartet=200).daten)


def test_erfassen_ohne_kategorie_unkategorisiert(api):
    giro = api.konto("Giro", "girokonto")
    api.konto("Lebensmittel", "aufwand")
    api.empfaenger("Bäckerei Korn")
    b = erfassen(api, art="ausgabe", datum="2024-03-01", konto_id=giro["id"], betrag=300,
                 empfaenger_name="Bäckerei Korn")
    assert b["vorschlag"] is None
    assert konto_id(api, UNKATEGORISIERT) in [s["konto_id"] for s in b["splits"]]


def test_loeschen_und_zusammenfuehren_aendern_keine_empfaenger(api):
    giro = api.konto("Giro", "girokonto")
    q = api.konto("Alt", "aufwand")
    z = api.konto("Neu", "aufwand")
    e = api.empfaenger("Laden")
    api.buchung("2024-01-02", [(giro["id"], -100), (q["id"], 100)], empfaenger_id=e["id"])
    r = api.post("/api/kategorien/zusammenfuehren", json={"quelle_ids": [q["id"]], "ziel_id": z["id"]},
                 erwartet=200).daten
    assert r["empfaenger_geaendert"] == []
    r = api.post(f"/api/konten/{z['id']}/loeschen", json={"buchungen": "unkategorisiert", "konflikte": "loeschen"},
                 erwartet=200).daten
    assert r["empfaenger_geaendert"] == []
    assert api.get(f"/api/empfaenger/{e['id']}", erwartet=200).daten["standardkategorie_id"] is None


# ------------------------------------------------------------------ 2.2 Konten eines Empfängers


def test_konten_eines_empfaengers(api):
    giro = api.konto("Giro", "girokonto")["id"]
    spar = api.konto("Tagesgeld", "sparkonto")["id"]
    karte = api.konto("Karte", "kreditkonto")["id"]
    kat = api.konto("Einkauf", "aufwand")["id"]
    e = api.empfaenger("Markt Fiktiv")["id"]
    leer = api.empfaenger("Niemand")["id"]
    andere = api.empfaenger("Andere")["id"]
    for _ in range(3):
        api.buchung("2024-01-02", [(spar, -100), (kat, 100)], empfaenger_id=e)
    api.buchung("2024-01-03", [(giro, -100), (kat, 100)], empfaenger_id=e)
    api.buchung("2024-01-04", [(karte, -100), (kat, 100)], empfaenger_id=e)
    api.buchung("2024-01-05", [(giro, -50), (spar, 50)], empfaenger_id=e)   # Umbuchung: je Konto einmal
    api.buchung("2024-01-06", [(karte, -100), (kat, 100)], empfaenger_id=andere)
    a0 = letzte_aenderung_id(api)
    soll = sorted([(spar, 4), (giro, 2), (karte, 1)], key=lambda x: (-x[1], x[0]))
    assert api.get(f"/api/empfaenger/{e}/konten", erwartet=200).daten == [
        {"konto_id": k, "anzahl": n} for k, n in soll]
    assert api.get(f"/api/empfaenger/{leer}/konten", erwartet=200).daten == []
    assert fehlercode(api.get("/api/empfaenger/999999/konten", erwartet=404)) == "nicht_gefunden"
    assert aenderungen_seit(api, a0) == []


def test_konten_gleichstand_nach_konto_id(api):
    a = api.konto("A-Konto", "girokonto")["id"]
    b = api.konto("B-Konto", "girokonto")["id"]
    kat = api.konto("Einkauf", "aufwand")["id"]
    e = api.empfaenger("Markt Fiktiv")["id"]
    for k in (b, a):
        api.buchung("2024-01-02", [(k, -100), (kat, 100)], empfaenger_id=e)
    assert [x["konto_id"] for x in api.get(f"/api/empfaenger/{e}/konten", erwartet=200).daten] == sorted([a, b])


# ------------------------------------------------------------------ 2.3 Anzahlen


def test_anzahlen(api):
    giro = api.konto("Giro", "girokonto")["id"]
    kat = api.konto("Einkauf", "aufwand")["id"]
    es = [api.empfaenger(n)["id"] for n in ("Eins", "Zwei", "Ohne")]
    for i, n in ((0, 3), (1, 1)):
        for _ in range(n):
            api.buchung("2024-01-02", [(giro, -100), (kat, 100)], empfaenger_id=es[i])
    api.buchung("2024-01-02", [(giro, -100), (kat, 100)])   # ohne Empfänger
    a0 = letzte_aenderung_id(api)
    assert api.get("/api/empfaenger/anzahlen", erwartet=200).daten == [
        {"empfaenger_id": es[0], "anzahl": 3}, {"empfaenger_id": es[1], "anzahl": 1}]
    assert aenderungen_seit(api, a0) == []


def test_anzahlen_leer(api):
    api.empfaenger("Niemand")
    assert api.get("/api/empfaenger/anzahlen", erwartet=200).daten == []


# ------------------------------------------------------------------ 3 Statistik entfällt


def test_statistik_entfaellt(api):
    k = api.konto("Giro", "girokonto")["id"]
    r = api.get("/api/statistik", params={"konto_id": k}, erwartet=404)
    assert fehlercode(r) == "nicht_gefunden"
    r = api.get("/statistik")
    assert r.status_code == 404 and r.text != api.get("/").text, "keine Hülle"
    assert 'data-testid="navlink-statistik"' not in api.get("/").text
