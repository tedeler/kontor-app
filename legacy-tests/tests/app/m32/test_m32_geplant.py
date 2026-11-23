"""M32: Geplante Zahlungen – Wiederholung, Fortsetzung, Zuordnung nach Namen, Vorschau, Protokoll und Sicherung
(sammel3.md 14; D-238; E-303) – kern. Folgedaten rechnet ``m32.plus_monate`` selbst aus."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import abruf
from tests.hilfen.m9 import einspielen, oeffne, sicherung
from tests.hilfen.m18 import pruefe_eintraege
from tests.hilfen.m20 import abgleich, app, ausgabe, detail, konten, paypal_zahlung
from tests.hilfen.m32 import RHYTHMUS_MONATE, alle_erwartungen, bestand, geplant, geplante_ereignisse, plus_monate, \
    tage

pytestmark = pytest.mark.kern
HEUTE = "2024-06-20"
ANGABEN = ("richtung", "haendler", "betrag", "beschreibung", "kennung", "grund")


def _app(tmp_path, **kw):
    return app(tmp_path, [], heute=HEUTE, **kw)


def _eine_aenderung(api, a0, aktion):
    neu = aenderungen_seit(api, a0)
    assert [(x["quelle"], x["aktion"]) for x in neu] == [("manuell", aktion)], [(x["quelle"], x["aktion"]) for x in neu]
    return neu[0]


def _operation(api, aktion, aufruf):
    v, a0 = bestand(api), letzte_aenderung_id(api)
    erg = aufruf()
    n = bestand(api)
    a = _eine_aenderung(api, a0, aktion)
    pruefe_eintraege(a, v, n)
    return erg, a, v, n


def _rundreise(api, a, v, n):
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == v
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == n


def _zustand(api, eid, zustand, erwartet=200):
    return api.post(f"/api/erwartungen/{eid}/zustand", json={"zustand": zustand}, erwartet=erwartet)


def _folgen(api, e: dict) -> list[dict]:
    """Erwartungen mit denselben Angaben, nach Datum (ohne die Ausgangserwartung)."""
    return sorted([x for x in alle_erwartungen(api) if x["id"] != e["id"] and all(x[f] == e[f] for f in ANGABEN)],
                  key=lambda x: x["datum"])


# ------------------------------------------------------------------ 14.1 Wiederholung


@pytest.mark.parametrize("rhythmus", list(RHYTHMUS_MONATE))
def test_anlegen_mit_wiederholung(tmp_path, rhythmus):
    api = _app(tmp_path)
    e = geplant(api, 4500, "2024-07-01", wiederholung=rhythmus, wiederholung_bis="2025-12-31")
    assert e["wiederholung"] == {"rhythmus": rhythmus, "bis": "2025-12-31"} and e["grund"] == "manuell"
    assert detail(api, e["id"])["wiederholung"] == e["wiederholung"]
    (x,) = alle_erwartungen(api)
    assert x["wiederholung"] == e["wiederholung"]


def test_ohne_wiederholung_kein_feld(tmp_path):
    api = _app(tmp_path)
    a = geplant(api, 100, "2024-07-01")
    b = geplant(api, 200, "2024-07-02", wiederholung="keine")
    for e in (a, b, *alle_erwartungen(api)):
        assert "wiederholung" not in e
    c = geplant(api, 300, "2024-07-03", wiederholung="monatlich", wiederholung_bis=None)
    assert c["wiederholung"] == {"rhythmus": "monatlich", "bis": None}


def test_fehler_und_pruefreihenfolge(tmp_path):
    api = app(tmp_path, [paypal_zahlung(empfangen="2024-06-03T08:00:00Z")], heute=HEUTE)
    abruf(api)
    (mail,) = alle_erwartungen(api)
    assert mail["grund"] == "paypal"
    for falsch in ({"wiederholung": "woechentlich"}, {"wiederholung": None}, {"wiederholung_bis": "morgen"},
                   {"wiederholung": "monatlich", "wiederholung_bis": 5}):
        r = geplant(api, 100, "2024-07-01", erwartet=422, **falsch)
        assert fehlercode(r) == "validierung", falsch
    for falsch in ({"wiederholung_bis": "2025-01-01"}, {"wiederholung": "keine", "wiederholung_bis": "2025-01-01"}):
        assert fehlercode(geplant(api, 100, "2024-07-01", erwartet=422, **falsch)) == "wiederholung_fehlt", falsch
    pfad = f"/api/erwartungen/{mail['id']}"
    for k in ({"wiederholung": "monatlich"}, {"wiederholung": "keine"}, {"wiederholung_bis": "2025-01-01"}):
        assert fehlercode(api.patch(pfad, json=k, erwartet=422)) == "wiederholung_nur_geplant", k
    assert fehlercode(api.patch(pfad, json={"wiederholung": "monatlich", "wiederholung_bis": "x"},
                                erwartet=422)) == "validierung"
    assert fehlercode(api.patch("/api/erwartungen/999999", json={"wiederholung": "x"}, erwartet=404)) == \
        "nicht_gefunden"
    g = geplant(api, 100, "2024-07-01")
    assert fehlercode(api.patch(f"/api/erwartungen/{g['id']}", json={"wiederholung_bis": "2025-01-01"},
                                erwartet=422)) == "wiederholung_fehlt"
    assert [x["id"] for x in alle_erwartungen(api)] == [mail["id"], g["id"]], "Fehler ohne Wirkung"


def test_aendern_und_entfernen(tmp_path):
    api = _app(tmp_path)
    e = geplant(api, 4500, "2024-07-01")
    pfad = f"/api/erwartungen/{e['id']}"
    _, a, v, n = _operation(api, "erwartung_aendern",
                            lambda: api.patch(pfad, json={"wiederholung": "jaehrlich"}, erwartet=200).daten)
    assert detail(api, e["id"])["wiederholung"] == {"rhythmus": "jaehrlich", "bis": None}
    _rundreise(api, a, v, n)
    assert api.patch(pfad, json={"wiederholung_bis": "2030-07-01"}, erwartet=200).daten["wiederholung"] == {
        "rhythmus": "jaehrlich", "bis": "2030-07-01"}
    assert api.patch(pfad, json={"wiederholung_bis": None}, erwartet=200).daten["wiederholung"] == {
        "rhythmus": "jaehrlich", "bis": None}
    x = api.patch(pfad, json={"wiederholung": "keine"}, erwartet=200).daten
    assert "wiederholung" not in x and "wiederholung" not in detail(api, e["id"])


# ------------------------------------------------------------------ 14.2 Fortsetzung


def test_fortsetzung_durch_erledigt_am_monatsletzten(tmp_path):
    api = _app(tmp_path)
    e = geplant(api, 4500, "2024-01-31", frist="2024-02-10", wiederholung="monatlich", beschreibung="Abschlag",
                kennung="VERTRAG-11")
    abstand = tage(e["datum"], e["frist"])
    erwartet = ["2024-02-29", "2024-03-31", "2024-04-30"]
    vorige = e
    for i, datum in enumerate(erwartet):
        _, a, v, n = _operation(api, "erwartung_zustand", lambda: _zustand(api, vorige["id"], "erledigt"))
        folgen = _folgen(api, e)
        assert len(folgen) == i + 1
        neu = folgen[i]
        assert neu["datum"] == datum == plus_monate(e["datum"], i + 1), "Tag der ersten Fälligkeit"
        assert tage(neu["datum"], neu["frist"]) == abstand
        assert (neu["zustand"], neu["buchung_ids"], neu["mails"], neu["dokument_ids"]) == ("offen", [], [], [])
        assert neu["wiederholung"] == {"rhythmus": "monatlich", "bis": None}
        art = {(x["objekt"], x["objekt_id"]): x["art"] for x in a["eintraege"]}
        assert art == {("erwartung", vorige["id"]): "geaendert", ("erwartung", neu["id"]): "angelegt"}
        vorige = neu
    _rundreise(api, a, v, n)


def test_fortsetzung_durch_zuordnung_und_wegfall(tmp_path):
    api = _app(tmp_path)
    k = konten(api)
    e = geplant(api, 5000, "2024-03-15", wiederholung="vierteljaehrlich")
    b = ausgabe(api, k, "2024-03-16", 5000, "Beitrag")
    _, a, v, n = _operation(api, "erwartung_zuordnen", lambda: api.post(
        f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [b]}, erwartet=200))
    assert detail(api, e["id"])["zustand"] == "erfuellt"
    (folge,) = _folgen(api, e)
    assert folge["datum"] == "2024-06-15" and folge["zustand"] == "offen"
    _rundreise(api, a, v, n)
    # Lösen: wieder offen, die unberührte Folge entfällt in derselben Änderung
    _, a2, _, _ = _operation(api, "erwartung_loesen", lambda: api.delete(
        f"/api/erwartungen/{e['id']}/buchungen/{b}", erwartet=200))
    assert detail(api, e["id"])["zustand"] == "offen" and _folgen(api, e) == []
    assert ("erwartung", folge["id"]) in {(x["objekt"], x["objekt_id"]) for x in a2["eintraege"]}
    # erneut zuordnen, dann die Buchung löschen: wieder offen, Folge entfällt
    api.post(f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [b]}, erwartet=200)
    assert len(_folgen(api, e)) == 1
    api.delete(f"/api/buchungen/{b}", erwartet=204)
    assert detail(api, e["id"])["zustand"] == "offen" and _folgen(api, e) == []


def test_wieder_offen_entfernt_unberuehrte_folge(tmp_path):
    api = _app(tmp_path)
    e = geplant(api, 900, "2024-05-10", wiederholung="halbjaehrlich")
    _zustand(api, e["id"], "erledigt")
    (folge,) = _folgen(api, e)
    assert folge["datum"] == "2024-11-10"
    _zustand(api, e["id"], "offen")
    assert _folgen(api, e) == [] and detail(api, e["id"])["zustand"] == "offen"


@pytest.mark.parametrize("bis,folge", [("2024-02-28", None), ("2024-02-29", "2024-02-29")])
def test_ende_der_wiederholung(tmp_path, bis, folge):
    api = _app(tmp_path)
    e = geplant(api, 4500, "2024-01-31", wiederholung="monatlich", wiederholung_bis=bis)
    _zustand(api, e["id"], "erledigt")
    assert [x["datum"] for x in _folgen(api, e)] == ([folge] if folge else [])


def test_keine_zweite_folge(tmp_path):
    """Eine berührte Folge bleibt beim Wiederöffnen; erneutes Erledigen legt keine zweite an (14.2)."""
    api = _app(tmp_path)
    e = geplant(api, 4500, "2024-01-15", wiederholung="jaehrlich")
    _zustand(api, e["id"], "erledigt")
    (folge,) = _folgen(api, e)
    assert folge["datum"] == "2025-01-15"
    api.patch(f"/api/erwartungen/{folge['id']}", json={"beschreibung": "geprüft"}, erwartet=200)   # berührt
    _zustand(api, e["id"], "offen")
    assert [x["id"] for x in alle_erwartungen(api) if x["id"] != e["id"]] == [folge["id"]], "berührte Folge bleibt"
    _zustand(api, e["id"], "erledigt")
    assert [x["id"] for x in alle_erwartungen(api) if x["id"] != e["id"]] == [folge["id"]], "keine zweite Folge"


@pytest.mark.parametrize("ende", ["storniert", "loeschen"])
def test_storniert_und_loeschen_beenden(tmp_path, ende):
    api = _app(tmp_path)
    e = geplant(api, 4500, "2024-01-15", wiederholung="monatlich")
    if ende == "storniert":
        _zustand(api, e["id"], "storniert")
    else:
        api.delete(f"/api/erwartungen/{e['id']}", erwartet=204)
    assert _folgen(api, e) == []


# ------------------------------------------------------------------ 14.3 Zuordnung nach Namen


def test_zuordnung_nach_namen(tmp_path):
    api = _app(tmp_path)
    k = konten(api)
    e = geplant(api, 5000, "2024-06-01", haendler="Stadtwerke Musterstadt")
    ohne = ausgabe(api, k, "2024-06-02", 5000, "Lastschrift")
    mit = ausgabe(api, k, "2024-06-03", 5000, "STADTWERKE Abschlag Juni")
    abgleich(api)
    x = detail(api, e["id"])
    assert x["buchung_ids"] == [mit] and ohne not in x["buchung_ids"], "andere Buchungen gleichen Betrags stören nicht"


def test_zuordnung_nach_namen_nicht_eindeutig_und_fenster(tmp_path):
    api = _app(tmp_path)
    k = konten(api)
    e = geplant(api, 5000, "2024-06-01", haendler="Stadtwerke Musterstadt")
    ausgabe(api, k, "2024-05-28", 5000, "Stadtwerke Abschlag")         # −4 Tage: außerhalb von 5.1
    ausgabe(api, k, "2024-06-02", 5000, "Musterstadt Abschlag")
    ausgabe(api, k, "2024-06-03", 5000, "Stadtwerke Abschlag")
    abgleich(api)
    assert detail(api, e["id"])["buchung_ids"] == [], "zwei passende Buchungen: nichts automatisch"


def test_zuordnung_nach_namen_nur_mit_mail_abgleich(tmp_path):
    api = _app(tmp_path, abgleich=False)
    k = konten(api)
    e = geplant(api, 5000, "2024-06-01", haendler="Stadtwerke Musterstadt")
    ausgabe(api, k, "2024-06-03", 5000, "Stadtwerke Abschlag")
    assert fehlercode(abgleich(api, erwartet=409)) == "mail_abgleich_aus"
    assert detail(api, e["id"])["buchung_ids"] == []


# ------------------------------------------------------------------ 14.4 Vorschau


def test_vorschau_enthaelt_geplante_zahlungen(tmp_path):
    api = _app(tmp_path)
    api.konto("Girokonto", "girokonto")
    monatlich = geplant(api, 4500, "2024-06-30", wiederholung="monatlich")
    faellig = geplant(api, 1200, "2024-06-10")                     # schon fällig: am Folgetag
    zu = geplant(api, 999, "2024-07-05")
    _zustand(api, zu["id"], "erledigt")
    ev = geplante_ereignisse(api.get("/api/berichte/vorschau", erwartet=200).daten)
    assert ev, "Ereignisse mit quelle geplant"
    for x in ev:
        assert x["konto_id"] is None and x["erwartung_id"] in (monatlich["id"], faellig["id"]), x
    (f,) = [x for x in ev if x["erwartung_id"] == faellig["id"]]
    assert (f["datum"], f["rhythmus"]) == ("2024-06-21", "einmalig")
    m = sorted((x for x in ev if x["erwartung_id"] == monatlich["id"]), key=lambda x: x["datum"])
    assert m and all(x["rhythmus"] == "monatlich" for x in m)
    assert [x["datum"] for x in m] == [plus_monate("2024-06-30", i) for i in range(len(m))]


# ------------------------------------------------------------------ 14.5 Sicherung


def test_sicherung_rundreise_mit_wiederholung(tmp_path):
    api = _app(tmp_path)
    geplant(api, 4500, "2024-01-31", wiederholung="monatlich", wiederholung_bis="2024-12-31")
    e = geplant(api, 100, "2024-02-01")
    _zustand(api, alle_erwartungen(api)[0]["id"], "erledigt")
    quelle = alle_erwartungen(api)
    assert len(quelle) == 3 and sum("wiederholung" in x for x in quelle) == 2
    assert "wiederholung" not in next(x for x in quelle if x["id"] == e["id"])
    m, _ = oeffne(sicherung(api))
    assert m["schemaversion"] >= 10 and m["anzahl"]["erwartung"] == 3
    ziel = _app(tmp_path, name="ziel")
    einspielen(ziel, sicherung(api))
    assert alle_erwartungen(ziel) == quelle
    assert bestand(ziel) == bestand(api)
    m2, _ = oeffne(sicherung(ziel))
    assert m2["inhalt_sha256"] == m["inhalt_sha256"]
