"""Entwicklungstests für den ALF-BanCo-Import (QIF) und das Zusammenführen von Kategorien.

Alle Daten sind synthetisch (fiktive Empfänger, Test-IBAN mit BLZ 00000000)."""

from __future__ import annotations

import pytest

from kontor.importer.alfbanco import betrag_in_cent, datum_iso, importiere_alfbanco, kategorie_zerlegen

IBAN = "DE57000000000532013000"

QIF = """!Type:Cat
NHaushalt
E
^
NHaushalt:Lebensmittel
E
^
NGehalt
I
^
!Type:Bank
D02.01.2024
T-12,34
PSupermarkt Beispiel
MEinkauf Woche 1
LHaushalt:Lebensmittel
^
D03.01.2024
T2.500,00
PArbeitgeber Muster GmbH
MLohn Januar
LGehalt/Steuer
^
D04.01.2024
T-100,00
PSparen
L[Sparkonto]
^
D05.01.2024
T-50,00
PKaufhaus Beispiel
MGemischter Einkauf
SHaushalt:Lebensmittel
EEssen
$-30,00
SKleidung
EHose
$-20,00
^
D06.01.2024
T-3,00
PCafé Beispiel
^
D06.01.2024
T-3,00
PCafé Beispiel
^
"""


def roh(text: str = QIF, kodierung: str = "cp1252") -> bytes:
    return text.replace("\n", "\r\n").encode(kodierung)


@pytest.fixture
def giro(client) -> dict:
    return client.post("/api/konten", json={"name": "Girokonto", "art": "girokonto", "iban": IBAN}).json()


@pytest.fixture
def spar(client) -> dict:
    return client.post("/api/konten", json={"name": "Sparkonto", "art": "sparkonto"}).json()


def hochladen(client, konto_id, daten: bytes, name: str = "giro.qif"):
    return client.post("/api/import/alfbanco", data={"konto_id": str(konto_id)},
                       files={"datei": (name, daten, "application/qif")})


@pytest.mark.parametrize("text,trenner,cent", [
    ("-12,34", ",", -1234), ("2.500,00", ",", 250000), ("1,234.56", ".", 123456), ("12.5", ".", 1250),
    ("+7", ",", 700), ("0,10", ",", 10), ("1.000", ",", 100000), ("-0,00", ",", 0), ("3,450", ".", 345000)])
def test_betrag(text, trenner, cent):
    assert betrag_in_cent(text, trenner) == cent


@pytest.mark.parametrize("text", ["", "abc", "1,234", "12,345", "1e3", "--1", "10000000000,00"])
def test_betrag_ungueltig(text):
    assert betrag_in_cent(text, ",") is None


@pytest.mark.parametrize("text,tag_vorn,iso", [
    ("02.01.2024", False, "2024-01-02"), ("2.1.24", False, "2024-01-02"), ("1/2/2024", False, "2024-01-02"),
    ("1/2'24", False, "2024-01-02"), ("13/02/2024", True, "2024-02-13"), ("2024-01-02", False, "2024-01-02"),
    (" 1/ 2'98", False, "2098-01-02"), ("1/2/98", False, "1998-01-02")])
def test_datum(text, tag_vorn, iso):
    assert datum_iso(text, tag_vorn) == iso


@pytest.mark.parametrize("text", ["31.02.2024", "2024/01/02", "", "1.13.2024"])
def test_datum_ungueltig(text):
    assert datum_iso(text, False) is None


def test_kategorie_zerlegen():
    assert kategorie_zerlegen("Haushalt:Lebensmittel/Urlaub") == ("Haushalt:Lebensmittel", "Urlaub")
    assert kategorie_zerlegen("[Giro/Haushalt]/Klasse") == ("[Giro/Haushalt]", "Klasse")
    assert kategorie_zerlegen("") == ("", "")


def test_import_abbildung(client, giro, spar):
    r = hochladen(client, giro["id"], roh())
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["erfolgreich"] and e["format"] == "qif"
    assert e["buchungen_neu"] == 6 and e["kategorien_neu"] == 4  # Haushalt, Lebensmittel, Gehalt, Kleidung
    assert e["tags_neu"] == 1 and e["empfaenger_neu"] == 5
    assert {w["code"] for w in e["warnungen"]} == {"kategorieart_abgeleitet"}
    konten = {k["name"]: k for k in client.get("/api/konten").json()}
    assert konten["Gehalt"]["art"] == "ertrag" and konten["Haushalt"]["art"] == "aufwand"
    assert konten["Lebensmittel"]["eltern_id"] == konten["Haushalt"]["id"]
    assert konten["Lebensmittel"]["extern_id"] == "alf:kat:Haushalt:Lebensmittel"
    assert konten["Kleidung"]["art"] == "aufwand"
    u = client.get("/api/kontenuebersicht").json()
    assert u["summe_gesamt"] == 0
    liste = client.get("/api/buchungen", params={"konto_id": giro["id"]}).json()
    buchungen = liste["eintraege"]
    split_b = next(b for b in buchungen if b["verwendungszweck"] == "Gemischter Einkauf")
    assert sorted((s["betrag"], s["memo"]) for s in split_b["splits"]) == [(-5000, ""), (2000, "Hose"), (3000, "Essen")]
    umbuchung = next(b for b in buchungen if any(s["konto_id"] == spar["id"] for s in b["splits"]))
    assert {s["konto_id"]: s["betrag"] for s in umbuchung["splits"]} == {giro["id"]: -10000, spar["id"]: 10000}
    lohn = next(b for b in buchungen if b["verwendungszweck"] == "Lohn Januar")
    assert len(lohn["tags"]) == 1
    cafe = [b for b in buchungen if b["empfaenger"] and b["empfaenger"]["name"] == "Café Beispiel"]
    assert len(cafe) == 2  # zwei gleiche Sätze bleiben zwei Buchungen
    ohne = next(s for s in cafe[0]["splits"] if s["konto_id"] != giro["id"])
    assert konten.get("Unkategorisiert") and ohne["konto_id"] == konten["Unkategorisiert"]["id"]


def test_import_idempotent(client, giro, spar):
    e1 = hochladen(client, giro["id"], roh()).json()
    e2 = hochladen(client, giro["id"], roh()).json()
    assert e2["buchungen_vorhanden"] == e1["buchungen_neu"] and e2["buchungen_neu"] == 0
    assert e2["kategorien_neu"] == 0 and e2["kategorien_vorhanden"] == 4 and e2["empfaenger_neu"] == 0
    assert e2["buchungen_zur_pruefung"] == 0 and e2["buchungen_zusammengefuehrt"] == 0
    # erweiterte Fassung: ein dritter gleicher Kaffee kommt hinzu
    e3 = hochladen(client, giro["id"], roh(QIF + "D06.01.2024\nT-3,00\nPCafé Beispiel\n^\n")).json()
    assert e3["buchungen_neu"] == 1 and e3["buchungen_vorhanden"] == 6 and e3["buchungen_zusammengefuehrt"] == 0


def test_utf8_und_umlaute(client, giro, spar):
    e = hochladen(client, giro["id"], roh(kodierung="utf-8")).json()
    assert e["erfolgreich"]
    namen = {x["name"] for x in client.get("/api/empfaenger").json()}
    assert "Café Beispiel" in namen


def test_dublette_mit_vorhandener_buchung(client, giro, spar):
    lm = client.post("/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()
    emp = client.post("/api/empfaenger", json={"name": "Supermarkt Beispiel"}).json()
    client.post("/api/buchungen", json={"datum": "2024-01-02", "empfaenger_id": emp["id"],
                                        "splits": [{"konto_id": giro["id"], "betrag": -1234},
                                                   {"konto_id": lm["id"], "betrag": 1234}]})
    e = hochladen(client, giro["id"], roh()).json()
    assert e["buchungen_zusammengefuehrt"] == 1 and e["buchungen_neu"] == 5


def test_fehler_ohne_teilimport(client, giro):
    kaputt = QIF.replace("D03.01.2024", "D33.01.2024")
    r = hochladen(client, giro["id"], roh(kaputt))
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "import_inhalt_ungueltig"
    assert r.json()["fehler"]["details"]["fehler"][0]["referenz"] == "Satz 2"
    assert len(client.get("/api/konten").json()) == 1
    assert hochladen(client, giro["id"], b"").json()["fehler"]["code"] == "import_datei_leer"
    assert hochladen(client, giro["id"], b"<xml/>").json()["fehler"]["code"] == "import_format_ungueltig"


def test_konto_pruefung(client, giro):
    assert hochladen(client, 999, roh()).json()["fehler"]["code"] == "referenz_unbekannt"
    kat = client.post("/api/konten", json={"name": "Kat", "art": "aufwand"}).json()
    assert hochladen(client, kat["id"], roh()).json()["fehler"]["code"] == "konto_ungueltig"
    r = client.post("/api/import/alfbanco", files={"datei": ("x.qif", roh(), "text/plain")})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung"


def test_python_api(config, client, giro, spar):
    e = importiere_alfbanco(config, roh(), konto_id=giro["id"], dateiname="giro.qif")
    assert e.erfolgreich and e.buchungen_neu == 6
    with pytest.raises(ValueError):
        importiere_alfbanco(config, roh(), konto_id=999)


def test_rueckgaengig(client, giro, spar):
    vorher = client.get("/api/konten").json()
    e = hochladen(client, giro["id"], roh()).json()
    r = client.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"import:{e['import_id']}"})
    assert r.status_code == 200, r.text
    assert client.get("/api/konten").json() == vorher


def test_wiedererkennung_vorhandener_kategorie(client, giro, spar):
    haus = client.post("/api/konten", json={"name": "Haushalt", "art": "aufwand"}).json()
    e = hochladen(client, giro["id"], roh()).json()
    assert e["kategorien_vorhanden"] == 1 and e["kategorien_neu"] == 3
    k = next(x for x in client.get("/api/konten").json() if x["id"] == haus["id"])
    assert k["extern_id"] == "alf:kat:Haushalt"


# ------------------------------------------------------------ Kategorien zusammenführen

def _konten(client) -> dict[str, dict]:
    return {k["name"]: k for k in client.get("/api/konten").json()}


def _saldo(client, kid: int) -> int:
    return client.get(f"/api/konten/{kid}").json().get("saldo", 0)


def test_zusammenfuehren_mit_loeschen(client, giro, spar):
    wohnen = client.post("/api/konten", json={"name": "Wohnen & Leben", "art": "aufwand"}).json()
    hochladen(client, giro["id"], roh())
    k = _konten(client)
    regel = client.post("/api/regeln", json={"name": "Kaufhaus", "kategorie_id": k["Kleidung"]["id"],
                                            "bedingungen": [{"feld": "empfaenger", "operator": "enthaelt",
                                                             "wert": "Kaufhaus"}]})
    r = client.post("/api/kategorien/zusammenfuehren",
                    json={"quelle_ids": [k["Haushalt"]["id"], k["Kleidung"]["id"]], "ziel_id": wohnen["id"]})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["quellen_geloescht"] and e["aenderung_id"] and e["unterkategorien_verschoben"] == [k["Lebensmittel"]["id"]]
    assert e["extern_id_uebernommen"] == "alf:kat:Haushalt"
    neu = _konten(client)
    assert "Haushalt" not in neu and "Kleidung" not in neu
    assert neu["Lebensmittel"]["eltern_id"] == wohnen["id"]
    assert regel.status_code == 201, regel.text
    assert client.get(f"/api/regeln/{regel.json()['id']}").json()["kategorie_id"] == wohnen["id"]
    # Splitbuchung: Kleidung 20 wurde zu Wohnen, Lebensmittel bleibt eigener Split
    liste = client.get("/api/buchungen", params={"konto_id": giro["id"]}).json()["eintraege"]
    split_b = next(b for b in liste if b["verwendungszweck"] == "Gemischter Einkauf")
    assert {s["konto_id"]: s["betrag"] for s in split_b["splits"] if s["betrag"] > 0} == {
        neu["Lebensmittel"]["id"]: 3000, wohnen["id"]: 2000}
    assert client.get("/api/kontenuebersicht").json()["summe_gesamt"] == 0
    # erneuter Import legt die gelöschte Wurzel nicht wieder an (Kennung übernommen), Kleidung schon
    e2 = hochladen(client, giro["id"], roh()).json()
    assert e2["buchungen_neu"] == 0 and e2["kategorien_neu"] == 1
    # Rückgängig stellt alles wieder her
    rg = client.post(f"/api/aenderungen/{e['aenderung_id']}/rueckgaengig")
    assert rg.status_code == 409  # der spätere Import baut auf dem Zusammenführen auf


def test_zusammenfuehren_rueckgaengig(client, giro, spar):
    ziel = client.post("/api/konten", json={"name": "Ziel", "art": "aufwand"}).json()
    hochladen(client, giro["id"], roh())
    vorher = client.get("/api/konten").json()
    k = _konten(client)
    e = client.post("/api/kategorien/zusammenfuehren",
                    json={"quelle_ids": [k["Haushalt"]["id"]], "ziel_id": ziel["id"]}).json()
    assert client.post(f"/api/aenderungen/{e['aenderung_id']}/rueckgaengig").status_code == 200
    assert client.get("/api/konten").json() == vorher


def test_zusammenfuehren_ohne_loeschen_und_probelauf(client, giro, spar):
    ziel = client.post("/api/konten", json={"name": "Ziel", "art": "aufwand"}).json()
    hochladen(client, giro["id"], roh())
    k = _konten(client)
    vorher = client.get("/api/konten").json()
    p = client.post("/api/kategorien/zusammenfuehren",
                    json={"quelle_ids": [k["Kleidung"]["id"]], "ziel_id": ziel["id"], "trocken": True}).json()
    assert p["trocken"] and p["buchungen_umgebucht"] and p["aenderung_id"] is None
    assert client.get("/api/konten").json() == vorher
    e = client.post("/api/kategorien/zusammenfuehren",
                    json={"quelle_ids": [k["Kleidung"]["id"]], "ziel_id": ziel["id"],
                          "quellen_loeschen": False}).json()
    assert not e["quellen_geloescht"] and "Kleidung" in _konten(client)
    leer = client.get("/api/buchungen", params={"konto_id": k["Kleidung"]["id"]}).json()
    assert leer["gesamt"] == 0


def test_zusammenfuehren_fehler(client, giro):
    kat = client.post("/api/konten", json={"name": "A", "art": "aufwand"}).json()
    ziel = client.post("/api/konten", json={"name": "B", "art": "aufwand"}).json()
    def z(**d):
        return client.post("/api/kategorien/zusammenfuehren", json=d)
    assert z(quelle_ids=[kat["id"]], ziel_id=kat["id"]).json()["fehler"]["code"] == "ziel_ungueltig"
    assert z(quelle_ids=[999], ziel_id=ziel["id"]).json()["fehler"]["code"] == "referenz_unbekannt"
    assert z(quelle_ids=[giro["id"]], ziel_id=ziel["id"]).json()["fehler"]["code"] == "konto_ungueltig"
    assert z(quelle_ids=[], ziel_id=ziel["id"]).json()["fehler"]["code"] == "validierung"
    assert z(quelle_ids=[kat["id"]]).json()["fehler"]["code"] == "validierung"
