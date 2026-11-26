"""Core-Tests zum Feature „sonderposten“ (D-300): Buchungen mit dem Tag „Sonderposten“ fallen aus den Berichten
über Einnahmen und Ausgaben heraus und stehen dort in einem eigenen Abschnitt.

- Parameter ``sonderposten`` (``ohne`` Vorgabe, ``mit``) an ``/api/berichte/monat``, ``jahr``, ``kategorien``,
  ``empfaenger``, ``geldfluss`` und ``einnahmen-ausgaben``; andere Werte 422.
- Antwortfeld ``sonderposten``: ``modus``, ``tag_id``, ``anzahl``, ``ausgaben``, ``einnahmen``, ``eintraege`` (die
  Sonderposten im Zeitraum des Berichts), in beiden Modi.
- Kontostand, Vorschau, Vermögen, Verträge, Datenqualität und Tags kennen den Parameter nicht und zählen alles.
- Der Tag wird am Namen erkannt, ohne Groß- und Kleinschreibung; Tags am Empfänger zählen nicht.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

GROSS = 2_499_000


@pytest.fixture
def welt(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                           mock_heute=dt.date(2026, 6, 20), planer_starten=False)))
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    lm = c.post("/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()["id"]
    auto = c.post("/api/konten", json={"name": "Auto", "art": "aufwand"}).json()["id"]
    gehalt = c.post("/api/konten", json={"name": "Gehalt", "art": "ertrag"}).json()["id"]
    markt = c.post("/api/empfaenger", json={"name": "Markt"}).json()["id"]
    haendler = c.post("/api/empfaenger", json={"name": "Autohaus"}).json()["id"]

    def buchen(datum, kat, betrag, empf=None, zweck="Einkauf"):
        r = c.post("/api/buchungen", json={"datum": datum, "verwendungszweck": zweck, "empfaenger_id": empf,
                                           "splits": [{"konto_id": giro, "betrag": -betrag},
                                                      {"konto_id": kat, "betrag": betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    for m in range(1, 7):
        buchen(f"2026-{m:02d}-03", lm, 30_000, markt)
        buchen(f"2026-{m:02d}-01", gehalt, -300_000, None, "Gehalt")
    auto_id = buchen("2026-06-10", auto, GROSS, haendler, "Autokauf")
    tag = c.post("/api/tags", json={"name": "sonderPOSTEN"}).json()["id"]
    r = c.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [auto_id], "hinzufuegen": [tag], "entfernen": []})
    assert r.status_code == 200, r.text
    return c, {"giro": giro, "lm": lm, "auto": auto, "markt": markt, "haendler": haendler, "tag": tag,
               "buchung": auto_id}


def _get(c, pfad, **params):
    r = c.get(pfad, params=params)
    assert r.status_code == 200, (pfad, r.text)
    return r.json()


def _abschnitt_pruefen(d, w, modus):
    s = d["sonderposten"]
    assert s["modus"] == modus and s["tag_id"] == w["tag"]
    assert s["anzahl"] == 1 and s["ausgaben"] == GROSS and s["einnahmen"] == 0
    (e,) = s["eintraege"]
    assert e["id"] == w["buchung"] and e["betrag"] == GROSS and e["art"] == "ausgabe" and e["datum"] == "2026-06-10"


@pytest.mark.parametrize("modus", ["ohne", "mit"])
def test_monatsbericht(welt, modus):
    c, w = welt
    d = _get(c, "/api/berichte/monat", monat="2026-06", sonderposten=modus)
    assert d["ausgaben"] == 30_000 + (GROSS if modus == "mit" else 0)
    ids = {b["id"] for b in d["buchungen"]} | {b["id"] for b in d["top_buchungen"]["eintraege"]}
    assert (w["buchung"] in ids) == (modus == "mit")
    assert all(a.get("id") != w["buchung"] for a in d["auffaellig"]["ausreisser"]) or modus == "mit"
    _abschnitt_pruefen(d, w, modus)


def test_vorgabe_ist_ohne(welt):
    c, w = welt
    for pfad, params in (("/api/berichte/monat", {"monat": "2026-06"}), ("/api/berichte/jahr", {"jahr": 2026}),
                         ("/api/berichte/kategorien", {"monat": "2026-06"}), ("/api/berichte/empfaenger", {}),
                         ("/api/berichte/geldfluss", {"monat": "2026-06"}),
                         ("/api/berichte/einnahmen-ausgaben", {"von": "2026-01-01", "bis": "2026-06-30"})):
        d = _get(c, pfad, **params)
        assert d["sonderposten"]["modus"] == "ohne", pfad
        _abschnitt_pruefen(d, w, "ohne")


@pytest.mark.parametrize("modus", ["ohne", "mit"])
def test_jahr(welt, modus):
    c, w = welt
    d = _get(c, "/api/berichte/jahr", jahr=2026, sonderposten=modus)
    extra = GROSS if modus == "mit" else 0
    assert d["summen"]["ausgaben"] == 6 * 30_000 + extra
    assert d["monate"][5]["ausgaben"] == 30_000 + extra
    assert (w["buchung"] in {b["id"] for b in d["top_buchungen"]["eintraege"]}) == (modus == "mit")
    assert (w["haendler"] in {e["empfaenger"]["id"] for e in d["top_empfaenger"] if e["empfaenger"]}) == (modus == "mit")


@pytest.mark.parametrize("modus", ["ohne", "mit"])
def test_kategorien(welt, modus):
    c, w = welt
    d = _get(c, "/api/berichte/kategorien", monat="2026-06", sonderposten=modus)
    assert d["summen"]["ausgaben"] == 30_000 + (GROSS if modus == "mit" else 0)
    auto = [z for z in d["ausgaben"] if z["id"] == w["auto"]]
    assert (bool(auto) and auto[0]["summe"] == GROSS) == (modus == "mit")


@pytest.mark.parametrize("modus", ["ohne", "mit"])
def test_empfaenger(welt, modus):
    c, w = welt
    d = _get(c, "/api/berichte/empfaenger", sonderposten=modus)
    namen = {e["empfaenger"]["id"]: e for e in d["rangliste"] if e["empfaenger"]}
    assert (w["haendler"] in namen) == (modus == "mit")
    einzel = _get(c, "/api/berichte/empfaenger", empfaenger_id=w["haendler"], sonderposten=modus)
    assert einzel["kennzahlen"]["ausgaben"] == (GROSS if modus == "mit" else 0)
    _abschnitt_pruefen(einzel, w, modus)


@pytest.mark.parametrize("modus", ["ohne", "mit"])
def test_geldfluss(welt, modus):
    c, w = welt
    d = _get(c, "/api/berichte/geldfluss", monat="2026-06", sonderposten=modus)
    assert d["ausgaben"] == 30_000 + (GROSS if modus == "mit" else 0)


@pytest.mark.parametrize("modus", ["ohne", "mit"])
def test_einnahmen_ausgaben(welt, modus):
    c, w = welt
    d = _get(c, "/api/berichte/einnahmen-ausgaben", von="2026-01-01", bis="2026-06-30", sonderposten=modus)
    assert d["gesamt"]["ausgaben"] == 6 * 30_000 + (GROSS if modus == "mit" else 0)
    kat = {k["kategorie_id"]: k["summe"] for k in d["kategorien"]}
    assert kat.get(w["auto"], 0) == (GROSS if modus == "mit" else 0)
    _abschnitt_pruefen(d, w, modus)


def test_andere_berichte_zaehlen_alles(welt):
    c, w = welt
    for pfad in ("/api/berichte/vorschau", "/api/berichte/vermoegen", "/api/berichte/vertraege",
                 "/api/berichte/qualitaet", "/api/berichte/tags"):
        r = c.get(pfad, params={"sonderposten": "ohne"})
        assert r.status_code == 422, pfad
    # Kontostand zum Monatsende enthält den Autokauf
    k = _get(c, "/api/berichte/kontostand", konto_id=w["giro"], von="2026-06-30", bis="2026-06-30")
    assert k["reihen"][0]["werte"][-1] == 6 * (300_000 - 30_000) - GROSS


def test_ungueltiger_wert(welt):
    c, _w = welt
    r = c.get("/api/berichte/monat", params={"monat": "2026-06", "sonderposten": "vielleicht"})
    assert r.status_code == 422


def test_ohne_tag_und_tag_am_empfaenger(welt):
    c, w = welt
    # ein gleichnamiger Tag am Empfänger macht dessen Buchungen nicht zu Sonderposten
    r = c.patch(f"/api/empfaenger/{w['markt']}", json={"tag_ids": [w["tag"]]})
    assert r.status_code == 200, r.text
    d = _get(c, "/api/berichte/monat", monat="2026-06")
    assert d["ausgaben"] == 30_000 and d["sonderposten"]["anzahl"] == 1
    # Tag gelöscht: keine Sonderposten mehr, tag_id null
    assert c.delete(f"/api/tags/{w['tag']}").status_code in (200, 204)
    d = _get(c, "/api/berichte/monat", monat="2026-06")
    assert d["ausgaben"] == 30_000 + GROSS
    assert d["sonderposten"] == {"modus": "ohne", "tag_id": None, "anzahl": 0, "ausgaben": 0, "einnahmen": 0,
                                 "eintraege": []}


def test_oberflaeche(client):
    js = "".join(client.get(f"/oeffentlich/app/{m}.js").text for m in ("berichte", "berichte2", "berichtsteile",
                                                                          "monatsbericht", "konto"))
    for teil in ("sonderposten", "bericht-sonderposten", "bericht-sonderposten-schalter", "km-sonderposten"):
        assert teil in js, teil
