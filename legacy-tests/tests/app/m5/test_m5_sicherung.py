"""M5: Kredite in der Datensicherung (sicherung.md 2.5; T 23; E-109).

Erwartungen aus dem Zustand der Quelle beim Erstellen (REST), die Inhaltsprüfsumme unabhängig nach
sicherung.md 3.3 mit der Objektart kredit nur bei Vorhandensein.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import neue_api
from tests.hilfen.m5 import Kreditbuch, bestand, kredit
from tests.hilfen.m9 import einspielen, inhalt, inhalt_sha256, lesezustand, oeffne, sicherung

pytestmark = pytest.mark.kern


def _inhalt(api) -> dict:
    i = inhalt(api)
    kredite = api.get("/api/kredite", erwartet=200).daten
    if kredite:
        i["kredit"] = sorted(kredite, key=lambda k: k["id"])
    return i


def _quelle(api) -> dict:
    kb = Kreditbuch(api)
    k = kb.anlegen(sondertilgungen=[{"datum": "2024-06-15", "betrag": 10_000}], zinsmethode="act/365").daten
    for t in ("2024-02-01", "2024-03-01"):
        kb.zahlung(t, k["rate"])
    api.post(f"/api/kredite/{k['id']}/zuordnen", json={}, erwartet=200)
    api.post(f"/api/kredite/{k['id']}/jahresabgleich", json={"jahr": 2024, "restschuld": 900_000, "zinsen": 6_000},
             erwartet=200)
    zweit = api.konto("Zweitdarlehen", "kreditkonto")["id"]
    weg = api.post("/api/kredite", json=kb.body(konto_id=zweit, name="weg", saldo_angleichen=False),
                   erwartet=201).daten
    api.delete(f"/api/kredite/{weg['id']}", erwartet=204)   # Lücke in den Kredit-IDs
    return kredit(api, k["id"])


def test_manifest_mit_kredit(api):
    _quelle(api)
    m, _ = oeffne(sicherung(api))
    i = _inhalt(api)
    assert m["anzahl"] == {**{o: len(v) for o, v in i.items()}}
    assert m["anzahl"]["kredit"] == 1
    assert m["inhalt_sha256"] == inhalt_sha256(i)


def test_ohne_kredit_kein_schluessel(api):
    kb = Kreditbuch(api)
    k = kb.anlegen().daten
    api.delete(f"/api/kredite/{k['id']}", erwartet=204)
    m, _ = oeffne(sicherung(api))
    assert "kredit" not in m["anzahl"], "Objektarten ab M5 nur bei Vorhandensein (E-109)"
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt(api))


def test_rundreise_mit_kredit(api, tmp_path):
    k = _quelle(api)
    roh = sicherung(api)
    soll, plan = lesezustand(api), api.get(f"/api/kredite/{k['id']}/plan", erwartet=200).daten
    soll_b = bestand(api)
    ziel = neue_api(tmp_path / "ziel")
    e = einspielen(ziel, roh).daten
    assert e["geaendert"] is True and e["unterschied"]["kredit"] == {"angelegt": 1, "geaendert": 0, "geloescht": 0}
    assert bestand(ziel) == soll_b and lesezustand(ziel) == soll
    assert ziel.get(f"/api/kredite/{k['id']}/plan", erwartet=200).daten == plan
    # ID-Zähler: ein neuer Kredit erhält eine größere ID als je in der Quelle vergeben
    neu_konto = ziel.konto("Drittes Darlehen", "kreditkonto")["id"]
    kb = Kreditbuch.__new__(Kreditbuch)
    kb.api, kb.giro, kb.zinsen, kb.darlehen = ziel, k["zahlungskonto_id"], k["zins_konto_id"], neu_konto
    neu = ziel.post("/api/kredite", json=kb.body(saldo_angleichen=False), erwartet=201).daten
    assert neu["id"] > k["id"] + 1
    # Rückgängig des Einspielens entfernt den Kredit wieder
    ziel.post(f"/api/aenderungen/{e['aenderung_id']}/rueckgaengig", erwartet=409)  # später geändert: Konflikt
    ziel.delete(f"/api/kredite/{neu['id']}", erwartet=204)
    ziel.delete(f"/api/konten/{neu_konto}", erwartet=204)


def test_unterschied_und_rueckgaengig(api, tmp_path):
    leer = neue_api(tmp_path / "leer")
    leer_roh = sicherung(leer)
    _quelle(api)
    vorher = bestand(api)
    e = einspielen(api, leer_roh).daten
    assert e["unterschied"]["kredit"] == {"angelegt": 0, "geaendert": 0, "geloescht": 1}
    assert api.get("/api/kredite", erwartet=200).daten == []
    api.post(f"/api/aenderungen/{e['aenderung_id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher
    # Probelauf zeigt denselben Unterschied, ändert nichts
    t = einspielen(api, leer_roh, trocken=True).daten
    assert t["unterschied"]["kredit"]["geloescht"] == 1 and bestand(api) == vorher


def test_ohne_kredite_auf_beiden_seiten_kein_schluessel_im_unterschied(api, tmp_path):
    q = neue_api(tmp_path / "q")
    q.konto("Nur ein Konto")
    e = einspielen(api, sicherung(q)).daten
    assert "kredit" not in e["unterschied"] and "kredit" not in e["manifest"]["anzahl"]
