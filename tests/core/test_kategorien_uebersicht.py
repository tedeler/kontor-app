"""Core-Tests zum Feature „kategorien-uebersicht“ (D-311): neue Kategorienseite mit Beträgen und Nachweis als PDF aus
dem Kontoblatt einer Kategorie.

- ``GET /api/kategorien/uebersicht[?zeitraum=monat|vormonat|30tage|12monate|jahr|vorjahr|gesamt]`` (Vorgabe ``12monate``) liefert je
  Kategorie die Summe im Zeitraum einschließlich Unterkategorien (Ausgaben und Einnahmen positiv), den eigenen Anteil,
  die Zahl der Buchungen, den Tag der letzten Buchung und den Verlauf der letzten zwölf Monate; dazu die Summen je
  Gruppe und die unkategorisierten Buchungen im Zeitraum. Nur lesend.
- ``GET /api/export/nachweis.pdf`` nimmt auch eine Kategorie als ``konto_id``: Buchungen der Kategorie oder ihrer
  Unterkategorien, Betrag aus Sicht des Bankkontos (Anteil der Kategorie), je Buchung das Bankkonto mit gekürzter IBAN.
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from kontor.app import create_app
from kontor.config import KontorConfig

GIRO_IBAN = "DE79000000000004711001"
GEKUERZT = "DE79 XXXX XXXX XXXX XXXX 1001"


@pytest.fixture(scope="module")
def welt(tmp_path_factory):
    """Ein Bestand für die ganze Datei (Zeitbudget der Core-Tests). Die Tests mit Splits ändern nur die
    Amazon-Buchung vom 11.06. und stehen am Ende; die Tests davor lesen nur."""
    tmp_path = tmp_path_factory.mktemp("kategorien")
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                           mock_heute=dt.date(2024, 6, 30), planer_starten=False)))
    assert c.post("/api/sync", json={}).json()["status"] == "erfolgreich"
    konten = c.get("/api/konten").json()
    giro = next(k["id"] for k in konten if k["iban"] == GIRO_IBAN)
    unk = next(k["id"] for k in konten if k["extern_id"] == "kontor:unkategorisiert")

    def kat(name, art, eltern=None):
        r = c.post("/api/konten", json={"name": name, "art": art, "eltern_id": eltern})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    k = {"wohnen": kat("Wohnen", "aufwand")}
    k["miete"] = kat("Miete", "aufwand", k["wohnen"])
    k["strom"] = kat("Strom", "aufwand", k["wohnen"])
    k["lebensmittel"] = kat("Lebensmittel", "aufwand")
    k["leer"] = kat("Hobby", "aufwand")
    k["gehalt"] = kat("Gehalt", "ertrag")
    buchungen = c.get("/api/buchungen", params={"konto_id": giro, "pro_seite": 200}).json()["eintraege"]

    def zuordnen(anfang, kategorie):
        ids = [b["id"] for b in buchungen if b["verwendungszweck"].startswith(anfang)]
        for i in ids:
            r = c.put(f"/api/buchungen/{i}/kategorie", json={"kategorie_id": k[kategorie]})
            assert r.status_code == 200, r.text
        return ids

    ids = {"miete": zuordnen("Miete", "miete"), "strom": zuordnen("Abschlag Strom", "strom"),
           "lebensmittel": zuordnen("Kartenzahlung", "lebensmittel"), "gehalt": zuordnen("Gehalt", "gehalt")}
    return c, giro, unk, k, ids, {b["id"]: b for b in buchungen}


def _uebersicht(c, **params):
    r = c.get("/api/kategorien/uebersicht", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _je(u):
    return {z["id"]: z for z in u["kategorien"]}


def test_summen_mit_unterkategorien_und_vorzeichen(welt):
    c, giro, unk, k, ids, b = welt
    u = _uebersicht(c)
    assert (u["zeitraum"], u["von"], u["bis"]) == ("12monate", "2023-07-01", "2024-06-30")
    assert u["monate"] == [f"2023-{m:02d}" for m in range(7, 13)] + [f"2024-{m:02d}" for m in range(1, 7)]
    je = _je(u)
    miete = -sum(b[i]["betrag"] for i in ids["miete"])
    strom = -sum(b[i]["betrag"] for i in ids["strom"])
    gehalt = sum(b[i]["betrag"] for i in ids["gehalt"])
    assert miete == 3 * 98000 and gehalt == 3 * 285000
    assert je[k["miete"]]["summe"] == miete and je[k["miete"]]["eigen"] == miete
    assert je[k["wohnen"]]["summe"] == miete + strom      # Unterkategorien zählen mit
    assert je[k["wohnen"]]["eigen"] == 0
    assert je[k["wohnen"]]["anzahl"] == len(ids["miete"]) + len(ids["strom"])
    assert je[k["gehalt"]]["summe"] == gehalt             # Einnahmen positiv
    assert je[k["gehalt"]]["anzahl"] == 3
    # leere Kategorien stehen mit 0 in der Liste
    assert je[k["leer"]] == {**je[k["leer"]], "summe": 0, "eigen": 0, "anzahl": 0, "letzte": None}
    assert je[k["leer"]]["verlauf"] == [0] * 12
    # Verlauf je Monat, der letzte Eintrag ist der laufende Monat
    assert je[k["miete"]]["verlauf"] == [0] * 9 + [98000, 98000, 98000]
    assert je[k["miete"]]["letzte"] == "2024-06-03"
    lebensmittel = -sum(b[i]["betrag"] for i in ids["lebensmittel"])
    assert u["summen"] == {"ausgaben": miete + strom + lebensmittel, "einnahmen": gehalt}
    # Unkategorisiert im Zeitraum (alle Konten): Summe der Splits, Ausgaben positiv
    alle = c.get("/api/buchungen", params={"pro_seite": 500}).json()["eintraege"]
    rest = [s["betrag"] for x in alle for s in x["splits"] if s["konto_id"] == unk]
    assert rest
    assert u["unkategorisiert"] == {"konto_id": unk, "anzahl": len(rest), "summe": sum(rest)}
    # nur Kategorien, keine Bestandskonten
    assert set(je) == set(k.values())


def test_zeitraeume(welt):
    c, giro, unk, k, ids, b = welt
    m = _uebersicht(c, zeitraum="monat")
    assert (m["von"], m["bis"]) == ("2024-06-01", "2024-06-30")
    assert _je(m)[k["miete"]]["summe"] == 98000 and _je(m)[k["miete"]]["anzahl"] == 1
    j = _uebersicht(c, zeitraum="jahr")
    assert (j["von"], j["bis"]) == ("2024-01-01", "2024-12-31")
    assert _je(j)[k["miete"]]["summe"] == 3 * 98000
    v = _uebersicht(c, zeitraum="vorjahr")
    assert (v["von"], v["bis"]) == ("2023-01-01", "2023-12-31")
    assert _je(v)[k["miete"]]["summe"] == 0
    assert v["monate"][-1] == "2023-12"                    # Verlauf endet mit dem Zeitraum
    assert _je(v)[k["miete"]]["letzte"] == "2024-06-03"    # letzte Buchung überhaupt
    # D-315: letzter Monat und letzte 30 Tage
    lm = _uebersicht(c, zeitraum="vormonat")
    assert (lm["von"], lm["bis"]) == ("2024-05-01", "2024-05-31")
    assert lm["monate"][-1] == "2024-05"
    assert _je(lm)[k["miete"]]["summe"] == 98000 and _je(lm)[k["miete"]]["anzahl"] == 1
    t = _uebersicht(c, zeitraum="30tage")
    assert (t["von"], t["bis"]) == ("2024-06-01", "2024-06-30")   # heute und die 29 Tage davor
    assert t["monate"][-1] == "2024-06"
    in_30 = [i for i in ids["miete"] if "2024-06-01" <= b[i]["datum"] <= "2024-06-30"]
    assert _je(t)[k["miete"]]["anzahl"] == len(in_30) == 1
    g = _uebersicht(c, zeitraum="gesamt")
    assert (g["von"], g["bis"]) == (None, None)
    assert _je(g)[k["miete"]]["summe"] == 3 * 98000


def test_ungueltige_angaben(welt):
    c = welt[0]
    for params in ({"zeitraum": "woche"}, {"von": "2024-01-01"}):
        r = c.get("/api/kategorien/uebersicht", params=params)
        assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung", r.text


def test_split_zaehlt_mit_seinem_anteil(welt):
    c, giro, unk, k, ids, b = welt
    amazon = next(x for x in b.values() if x["verwendungszweck"].startswith("302-2266490"))
    r = c.put(f"/api/buchungen/{amazon['id']}/splits", json={"splits": [
        {"konto_id": giro, "betrag": amazon["betrag"]},
        {"konto_id": k["lebensmittel"], "betrag": 1000},
        {"konto_id": k["leer"], "betrag": -amazon["betrag"] - 1000}]})
    assert r.status_code == 200, r.text
    je = _je(_uebersicht(c, zeitraum="monat"))
    assert je[k["leer"]]["summe"] == -amazon["betrag"] - 1000 and je[k["leer"]]["anzahl"] == 1


# ------------------------------------------------------------------ Nachweis aus dem Kontoblatt einer Kategorie

def _text(r) -> str:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(r.content)).pages)


def _eur(cent):
    e, r = divmod(abs(cent), 100)
    return f"{'-' if cent < 0 else '+'}{e:,}".replace(",", ".") + f",{r:02d}"


def test_nachweis_einer_kategorie(welt):
    c, giro, unk, k, ids, b = welt
    gewaehlt = ids["miete"][:2] + ids["strom"][:1]
    r = c.get("/api/export/nachweis.pdf", params={"konto_id": k["wohnen"], "buchung_id": gewaehlt,
                                                   "inhaber": "Erika Mustermann (fiktiv)"})
    assert r.headers["content-disposition"] == 'attachment; filename="kontor-nachweis-20240630.pdf"'
    t = _text(r)
    assert "Buchungsnachweis" in t and "kein Dokument der Bank" in t
    assert "Wohnen" in t and "Erika Mustermann (fiktiv)" in t
    assert GEKUERZT in t and GIRO_IBAN not in t
    for i in gewaehlt:
        assert b[i]["verwendungszweck"] in t
        assert _eur(b[i]["betrag"]) in t                    # Sicht des Bankkontos: Ausgaben negativ
    assert "Girokonto (Mock)" in t
    assert "Summe der 3 ausgewählten Buchungen" in t
    assert _eur(sum(b[i]["betrag"] for i in gewaehlt)) in t
    andere = [x for x in ids["miete"] if x not in gewaehlt]
    for i in andere:
        assert b[i]["verwendungszweck"] not in t


def test_nachweis_kategorie_mit_split_und_fehlern(welt):
    c, giro, unk, k, ids, b = welt
    amazon = next(x for x in b.values() if x["verwendungszweck"].startswith("302-2266490"))
    c.put(f"/api/buchungen/{amazon['id']}/splits", json={"splits": [
        {"konto_id": giro, "betrag": amazon["betrag"]}, {"konto_id": k["lebensmittel"], "betrag": 1000},
        {"konto_id": k["leer"], "betrag": -amazon["betrag"] - 1000}]})
    t = _text(c.get("/api/export/nachweis.pdf", params={"konto_id": k["lebensmittel"], "buchung_id": [amazon["id"]]}))
    assert _eur(-1000) in t and f"Anteil an einer Zahlung über {_eur(amazon['betrag'])}" in t
    # Buchung außerhalb der Kategorie
    r = c.get("/api/export/nachweis.pdf", params={"konto_id": k["miete"], "buchung_id": ids["strom"][:1]})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "buchung_nicht_im_konto"
    # Unkategorisiert ist keine Kategorie
    r = c.get("/api/export/nachweis.pdf", params={"konto_id": unk, "buchung_id": [amazon["id"]]})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "kein_bestandskonto"
    a = c.get("/api/export/nachweis/angaben", params={"konto_id": k["miete"]})
    assert a.status_code == 200 and set(a.json()) == {"inhaber", "bic"}


def test_30_tage_ueber_den_monatswechsel():
    """Die 30 Tage reichen in den Vormonat; Januar → Dezember des Vorjahres beim letzten Monat."""
    from kontor.kategorienuebersicht import grenzen
    assert grenzen("30tage", dt.date(2024, 3, 10))[:2] == ("2024-02-10", "2024-03-10")
    assert grenzen("vormonat", dt.date(2024, 1, 15)) == ("2023-12-01", "2023-12-31", (2023, 12))
    assert grenzen("vormonat", dt.date(2024, 3, 31))[:2] == ("2024-02-01", "2024-02-29")
