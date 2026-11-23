"""M20: Liste mit Filtern und Summen, manuelle Erwartungen, Zustände, Löschen, Überfällig und Benachrichtigung,
Schutz, Sicherung (erwartungen.md 3, 4.2, 6, 7; E-217, E-218)."""

from __future__ import annotations

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import setze_zeit
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import abruf, benachrichtigungen
from tests.hilfen.m7 import anmelden, m7_api
from tests.hilfen.m9 import einspielen, inhalt_sha256, oeffne, sicherung
from tests.hilfen.m18 import operation, rundreise
from tests.hilfen.m20 import (
    NR, abgleich, alle, amazon_bestellung, app, ausgabe, bestand, detail, form, konten, liste, paypal_rueckzahlung,
    paypal_zahlung,
)

pytestmark = pytest.mark.kern

OBJEKTE_M9 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]


def _op(api, aktion, aufruf):
    return operation(api, aktion, aufruf, zustand_fn=bestand)


def _ohne(api, aufruf):
    from tests.hilfen.m18 import ohne_wirkung
    ohne_wirkung(api, aufruf, zustand_fn=bestand)


def _neu(api, erwartet=201, **body):
    r = api.post("/api/erwartungen", json=body, erwartet=erwartet)
    return r.daten if erwartet == 201 else r


# ------------------------------------------------------------------ Anlegen, Ändern, Zustand, Löschen (6.2, 6.3)


def test_anlegen_mit_vorgaben_und_protokoll(tmp_path):
    api = app(tmp_path, [], heute="2024-06-10", mail_abgleich_frist_tage=7)
    setze_zeit(api, "2024-06-10T09:00:00Z")
    e, a, v, n = _op(api, "erwartung_anlegen", lambda: _neu(api, richtung="eingang", haendler="  Fiktive Bank  ",
                                                             betrag=1500))
    assert form(e) == {"id": e["id"], "grund": "manuell", "richtung": "eingang", "anbieter": None, "kennung": "",
                       "referenz": "", "haendler": "Fiktive Bank", "beschreibung": "", "betrag": 1500, "gesamt": 1500,
                       "guthaben": 0, "datum": "2024-06-10", "frist": "2024-06-17", "zustand": "offen",
                       "bezug_id": None, "buchung_ids": [], "mails": [], "dokument_ids": [],
                       "erstellt_am": "2024-06-10T09:00:00Z"}
    assert (e["vorzeichen_betrag"], e["offen_betrag"], e["buchungen"], e["mail_eintraege"]) == (1500, 1500, [], [])
    rundreise(api, a, v, n, zustand_fn=bestand)
    f = _neu(api, richtung="ausgabe", haendler="X", betrag=1, datum="2024-01-01", frist="2024-01-03",
             beschreibung="b" * 2000, kennung="k" * 200)
    assert (f["datum"], f["frist"], len(f["beschreibung"]), len(f["kennung"])) == ("2024-01-01", "2024-01-03", 2000, 200)
    assert _neu(api, richtung="ausgabe", haendler="X", betrag=1, datum="2024-02-01")["frist"] == "2024-02-08"


@pytest.mark.parametrize("body", [
    {}, {"richtung": "ausgabe", "haendler": "X"}, {"richtung": "aus", "haendler": "X", "betrag": 1},
    {"richtung": "ausgabe", "haendler": "", "betrag": 1}, {"richtung": "ausgabe", "haendler": "   ", "betrag": 1},
    {"richtung": "ausgabe", "haendler": "x" * 201, "betrag": 1}, {"richtung": "ausgabe", "haendler": "X", "betrag": 0},
    {"richtung": "ausgabe", "haendler": "X", "betrag": True}, {"richtung": "ausgabe", "haendler": "X", "betrag": 1.0},
    {"richtung": "ausgabe", "haendler": "X", "betrag": 1000000000000},
    {"richtung": "ausgabe", "haendler": "X", "betrag": 1, "beschreibung": "b" * 2001},
    {"richtung": "ausgabe", "haendler": "X", "betrag": 1, "kennung": "k" * 201},
    {"richtung": "ausgabe", "haendler": "X", "betrag": 1, "datum": "2024-02-30"},
    {"richtung": "ausgabe", "haendler": "X", "betrag": 1, "grund": "bestellung"},
    {"richtung": "ausgabe", "haendler": "X", "betrag": 1, "zustand": "offen"}, [],
], ids=lambda b: str(b)[:50])
def test_anlegen_validierung(tmp_path, body):
    api = app(tmp_path, [])

    def aufruf():
        assert fehlercode(api.post("/api/erwartungen", json=body, erwartet=422)) == "validierung"
    _ohne(api, aufruf)


def test_aendern(tmp_path):
    api = app(tmp_path, [paypal_zahlung(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20")
    k = konten(api)
    abruf(api)
    (p,) = alle(api)
    e = _neu(api, richtung="ausgabe", haendler="Fiktiv", betrag=3000, datum="2024-06-01")
    b = ausgabe(api, k, "2024-06-02", 2000)
    api.post(f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [b]}, erwartet=200)

    def falsch():
        assert fehlercode(api.patch("/api/erwartungen/999999", json={"richtung": "x"}, erwartet=404)) == "nicht_gefunden"
        for body in ({"richtung": "eingang"}, {"grund": "paypal"}, {"betrag": 0}, {"betrag": "1"}, {"haendler": ""},
                     {"frist": "morgen"}, {"zustand": "erfuellt"}):
            assert fehlercode(api.patch(f"/api/erwartungen/{e['id']}", json=body, erwartet=422)) == "validierung", body
        assert fehlercode(api.patch(f"/api/erwartungen/{e['id']}", json={"betrag": 1999},
                                    erwartet=422)) == "zuordnung_zu_hoch"
        assert fehlercode(api.patch(f"/api/erwartungen/{e['id']}", json={"betrag": 1999, "x": 1},
                                    erwartet=422)) == "validierung", "422 validierung vor zuordnung_zu_hoch"
    _ohne(api, falsch)
    d, a, v, n = _op(api, "erwartung_aendern", lambda: api.patch(f"/api/erwartungen/{e['id']}",
                                                                  json={"betrag": 2000, "haendler": "Neu"},
                                                                  erwartet=200).daten)
    assert (d["betrag"], d["gesamt"], d["zustand"], d["haendler"]) == (2000, 2000, "erfuellt", "Neu")
    rundreise(api, a, v, n, zustand_fn=bestand)
    d = api.patch(f"/api/erwartungen/{e['id']}", json={"betrag": 2500}, erwartet=200).daten
    assert (d["zustand"], d["offen_betrag"]) == ("offen", 500), "erfuellt mit Zuordnungen wird neu bestimmt"
    _ohne(api, lambda: api.patch(f"/api/erwartungen/{e['id']}", json={"betrag": 2500}, erwartet=200))
    # für aus Mails erkannte Erwartungen: gesamt = betrag + guthaben
    d = api.patch(f"/api/erwartungen/{p['id']}", json={"betrag": 1500, "beschreibung": "korrigiert"},
                  erwartet=200).daten
    assert (d["betrag"], d["guthaben"], d["gesamt"], d["grund"]) == (1500, 500, 2000, "paypal")


def test_zustand_wechsel(tmp_path):
    api = app(tmp_path, [], heute="2024-06-20")
    k = konten(api)
    e = _neu(api, richtung="ausgabe", haendler="Fiktiv", betrag=1000, datum="2024-06-01")
    eid = e["id"]

    def falsch():
        assert fehlercode(api.post("/api/erwartungen/999999/zustand", json={"zustand": "x"},
                                   erwartet=404)) == "nicht_gefunden"
        for body in ({}, {"zustand": "erfuellt"}, {"zustand": "ueberfaellig"}, {"zustand": "offen", "x": 1}):
            assert fehlercode(api.post(f"/api/erwartungen/{eid}/zustand", json=body, erwartet=422)) == "validierung"
        assert fehlercode(api.post(f"/api/erwartungen/{eid}/zustand", json={"zustand": "offen"},
                                   erwartet=409)) == "zustand_unzulaessig"
    _ohne(api, falsch)
    for ziel in ("guthaben", "storniert", "erledigt"):
        d, a, v, n = _op(api, "erwartung_zustand", lambda: api.post(f"/api/erwartungen/{eid}/zustand",
                                                                     json={"zustand": ziel}, erwartet=200).daten)
        assert (d["zustand"], d["offen_betrag"], d["ueberfaellig"]) == (ziel, 0, False)
        rundreise(api, a, v, n, zustand_fn=bestand)
        assert fehlercode(api.post(f"/api/erwartungen/{eid}/zustand", json={"zustand": "erledigt"},
                                   erwartet=409)) == "zustand_unzulaessig", "schließen nur aus offen"
        api.post(f"/api/erwartungen/{eid}/zustand", json={"zustand": "offen"}, erwartet=200)
    b = ausgabe(api, k, "2024-06-02", 1000)
    api.post(f"/api/erwartungen/{eid}/buchungen", json={"buchung_ids": [b]}, erwartet=200)
    assert detail(api, eid)["zustand"] == "erfuellt"
    assert fehlercode(api.post(f"/api/erwartungen/{eid}/zustand", json={"zustand": "offen"},
                               erwartet=409)) == "zustand_unzulaessig", "öffnen nicht aus erfuellt"


def test_loeschen(tmp_path):
    api = app(tmp_path, [amazon_bestellung()], heute="2024-06-10")
    abruf(api)
    (m,) = alle(api)
    e = _neu(api, richtung="ausgabe", haendler="Fiktiv", betrag=1000)
    _, a, v, n = _op(api, "erwartung_loeschen", lambda: api.delete(f"/api/erwartungen/{e['id']}", erwartet=204))
    rundreise(api, a, v, n, zustand_fn=bestand)
    _ohne(api, lambda: fehlercode(api.delete(f"/api/erwartungen/{m['id']}", erwartet=409)) == "erwartung_aus_mail")
    assert fehlercode(api.delete(f"/api/erwartungen/{m['id']}", erwartet=409)) == "erwartung_aus_mail"
    assert fehlercode(api.delete("/api/erwartungen/999999", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.get("/api/erwartungen/999999", erwartet=404)) == "nicht_gefunden"


# ------------------------------------------------------------------ Liste (6.1)


def test_liste_filter_und_summen(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z"),
                         paypal_zahlung(empfangen="2024-06-02T08:00:00Z"),
                         paypal_rueckzahlung(empfangen="2024-06-04T08:00:00Z")], heute="2024-06-08")
    abruf(api)
    best = next(e for e in alle(api) if e["grund"] == "bestellung")       # frist 06-06 → überfällig
    zahl = next(e for e in alle(api) if e["grund"] == "paypal")           # frist 06-07 → überfällig
    rueck = next(e for e in alle(api) if e["grund"] == "rueckerstattung")  # frist 06-09
    m1 = _neu(api, richtung="ausgabe", haendler="Bücherstube (fiktiv)", betrag=700, datum="2024-06-08",
              beschreibung="Roman", kennung="RECHNUNG-55")                 # frist 06-13
    m2 = _neu(api, richtung="ausgabe", haendler="Erledigt", betrag=100, datum="2024-06-08")
    api.post(f"/api/erwartungen/{m2['id']}/zustand", json={"zustand": "erledigt"}, erwartet=200)
    l = liste(api)
    assert [e["id"] for e in l["eintraege"]] == [best["id"], zahl["id"], rueck["id"], m1["id"]], "nur offen, frist/id"
    assert (l["anzahl"], l["ueberfaellig"], l["aktiv"]) == (4, 2, True)
    assert l["summe_offen"] == -4990 - 2000 + 2500 - 700
    assert [e["ueberfaellig"] for e in l["eintraege"]] == [True, True, False, False]
    assert [e["id"] for e in liste(api, zustand="ueberfaellig")["eintraege"]] == [best["id"], zahl["id"]]
    assert [e["id"] for e in liste(api, zustand=["erledigt", "ueberfaellig"])["eintraege"]] == [
        best["id"], zahl["id"], m2["id"]]
    assert [e["id"] for e in liste(api, grund=["paypal", "manuell"])["eintraege"]] == [zahl["id"], m1["id"]]
    assert [e["id"] for e in liste(api, richtung="eingang")["eintraege"]] == [rueck["id"]]
    assert [e["id"] for e in liste(api, faellig_bis="2024-06-07")["eintraege"]] == [best["id"], zahl["id"]]
    for s, soll in (("BÜCHER", [m1["id"]]), ("roman", [m1["id"]]), ("rechnung-5", [m1["id"]]), ("r-4711", [zahl["id"]]),
                    (NR[:7], [best["id"]]), ("fiktiver shop", [zahl["id"], rueck["id"]])):
        assert [e["id"] for e in liste(api, suche=s)["eintraege"]] == soll, s
    assert [e["id"] for e in liste(api, grund="paypal", richtung="eingang")["eintraege"]] == [], "UND-verknüpft"
    for params in ({"grund": "x"}, {"zustand": "geschlossen"}, {"richtung": "beide"}, {"faellig_bis": "heute"}):
        assert fehlercode(liste(api, erwartet=422, **params)) == "validierung", params


def test_liste_unbekannter_parameter(tmp_path):
    api = app(tmp_path, [])
    assert fehlercode(liste(api, erwartet=422, unbekannt="1")) == "validierung"


# ------------------------------------------------------------------ Überfällig und Benachrichtigung (4.2)


def test_ueberfaellig_benachrichtigung_einmal(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z"),
                         paypal_rueckzahlung(code="8YY23456CD789012E", ursprung="1AB23456CD789099X",
                                             empfangen="2024-06-01T09:00:00Z")], heute="2024-06-05")
    abruf(api)
    best = next(e for e in alle(api) if e["richtung"] == "ausgabe")
    rueck = next(e for e in alle(api) if e["richtung"] == "eingang")
    assert not best["ueberfaellig"] and [b for b in benachrichtigungen(api) if b["art"] == "erwartung_ueberfaellig"] == []
    setze_zeit(api, "2024-06-07T08:00:00Z")                             # frist 06-06 < heute 06-07
    a0 = letzte_aenderung_id(api)
    erg = abgleich(api)
    assert erg["gemeldet"] == 2
    meld = {b["schluessel"]: b for b in benachrichtigungen(api) if b["art"] == "erwartung_ueberfaellig"}
    assert set(meld) == {f"erwartung_ueberfaellig:{best['id']}", f"erwartung_ueberfaellig:{rueck['id']}"}
    mb = meld[f"erwartung_ueberfaellig:{best['id']}"]
    assert (mb["titel"], mb["link"]) == ("Zahlung nicht abgebucht", f"/erwartet?id={best['id']}")
    assert "Amazon" in mb["text"]
    assert meld[f"erwartung_ueberfaellig:{rueck['id']}"]["titel"] == "Erstattung überfällig"
    assert aenderungen_seit(api, a0) == [], "Benachrichtigungen sind nicht Teil einer Änderung"
    for b in meld.values():
        api.post(f"/api/benachrichtigungen/{b['id']}/gelesen", erwartet=(200, 204))
    abgleich(api)
    kontor.modul("kontor.sync").planer_takt(api.app)
    assert len([b for b in benachrichtigungen(api) if b["art"] == "erwartung_ueberfaellig"]) == 2, "höchstens einmal"
    assert detail(api, best["id"])["ueberfaellig"] is True


# ------------------------------------------------------------------ Schutz (6)


def test_geschuetzt(tmp_path):
    api = m7_api(tmp_path)
    for methode, pfad, kw in [
        ("GET", "/api/erwartungen", {}), ("POST", "/api/erwartungen", {"json": {}}),
        ("POST", "/api/erwartungen/abgleich", {}), ("GET", "/api/erwartungen/1", {}),
        ("PATCH", "/api/erwartungen/1", {"json": {}}), ("DELETE", "/api/erwartungen/1", {}),
        ("POST", "/api/erwartungen/1/zustand", {"json": {}}), ("GET", "/api/erwartungen/1/kandidaten", {}),
        ("POST", "/api/erwartungen/1/buchungen", {"json": {}}), ("DELETE", "/api/erwartungen/1/buchungen/1", {}),
    ]:
        assert fehlercode(api.anfrage(methode, pfad, erwartet=401, **kw)) == "nicht_angemeldet", (methode, pfad)
    anmelden(api)
    csrf, api.csrf = api.csrf, None
    r = api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "X", "betrag": 1}, erwartet=403)
    assert fehlercode(r) == "csrf_ungueltig"
    api.csrf = csrf
    assert liste(api)["eintraege"] == []


# ------------------------------------------------------------------ Sicherung (7)


def test_sicherung_ohne_erwartungen_ohne_schluessel(tmp_path):
    api = app(tmp_path, [])
    m, _ = oeffne(sicherung(api))
    assert "erwartung" not in m["anzahl"]


def test_sicherung_rundreise(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z")], heute="2024-06-10")
    k = konten(api)
    abruf(api)
    b = ausgabe(api, k, "2024-06-02", 4990, f"Amazon {NR}")
    abgleich(api)
    _neu(api, richtung="eingang", haendler="Fiktiv", betrag=10)
    quelle = alle(api)
    assert quelle[0]["buchung_ids"] == [b] and quelle[0]["dokument_ids"]
    m, _ = oeffne(sicherung(api))
    assert m["anzahl"]["erwartung"] == 2 and m["schemaversion"] >= 5
    ziel = app(tmp_path, [], name="ziel")
    e = einspielen(ziel, sicherung(api)).daten
    assert e["unterschied"]["erwartung"] == {"angelegt": 2, "geaendert": 0, "geloescht": 0}
    assert [form(x) for x in alle(ziel)] == [form(x) for x in quelle]
    assert bestand(ziel) == bestand(api)
    m2, _ = oeffne(sicherung(ziel))
    assert m2["inhalt_sha256"] == m["inhalt_sha256"]
    det = detail(ziel, quelle[0]["id"])
    assert [x["spiegel_id"] for x in det["mail_eintraege"]] == [None], "Mails sind Betriebszustand"
    # Inhaltsprüfsumme unabhängig aus den Protokollformen (E-217)
    bs = bestand(api)
    # Objektarten ab M5 nur bei Vorhandensein (sicherung.md 2.5–2.8, E-109), auch postfach (W-011, E-226)
    objekte = OBJEKTE_M9 + [o for o in ("kredit", "postfach", "dokument", "erwartung") if any(k_[0] == o for k_ in bs)]
    inhalt = {o: [bs[k_] for k_ in sorted(k_ for k_ in bs if k_[0] == o)] for o in objekte}
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt)
