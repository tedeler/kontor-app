"""Core-Tests zum Feature „konto-typ-inhaber“ (D-310): Kontotyp änderbar, Kontoinhaber, Kreditkonten mit
umgedrehtem Vorzeichen in der Anzeige.

- ``art`` ist bei Bestandskonten über ``PATCH /api/konten/{id}`` änderbar (``girokonto``, ``sparkonto``,
  ``kreditkonto``). Andere Werte sind ungültig (422 ``validierung``); Kategorien und technische Konten können den Typ
  nicht wechseln (422 ``art_ungueltig``). Ein Konto, auf das ein Kredit verweist, bleibt Kreditkonto (409
  ``konto_in_verwendung``).
- ``inhaber`` = ``{vorname, nachname}`` bei Bestandskonten, beide Teile dürfen leer bleiben. Sind beide leer,
  fehlt das Feld in der Antwort (wie in der Protokollform). ``null`` entfernt den Inhaber.
- Gespeichert wird unverändert (Soll positiv): das umgedrehte Vorzeichen ist reine Anzeige (Kontoblatt, Konten),
  der Saldo der Finanzübersicht bleibt negativ.
- Protokoll (Rückgängig) und Sicherung (Schemaversion 12, Tabelle ``konto_inhaber``) erfassen beides; ältere
  Sicherungen ohne die Tabelle lassen sich weiter einspielen.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile

import pytest

GIRO_IBAN = "DE89000000000000000001"


@pytest.fixture
def c(client):
    return client


def _konto(c, name, art, **mehr):
    r = c.post("/api/konten", json={"name": name, "art": art, **mehr})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------------------------- Kontotyp


@pytest.mark.parametrize("von,nach", [("girokonto", "kreditkonto"), ("kreditkonto", "sparkonto"),
                                      ("sparkonto", "girokonto")])
def test_art_von_bestandskonten_aenderbar(c, von, nach):
    k = _konto(c, "Karte", von)
    r = c.patch(f"/api/konten/{k['id']}", json={"art": nach})
    assert r.status_code == 200, r.text
    assert r.json()["art"] == nach
    assert c.get(f"/api/konten/{k['id']}").json()["art"] == nach


def test_art_nur_innerhalb_der_bestandskonten(c):
    kat = _konto(c, "Lebensmittel", "aufwand")
    giro = _konto(c, "Giro", "girokonto")
    r = c.patch(f"/api/konten/{kat['id']}", json={"art": "girokonto"})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "art_ungueltig"
    for art in ("aufwand", "ertrag", "eigenkapital", "giro"):
        r = c.patch(f"/api/konten/{giro['id']}", json={"art": art})
        assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung", art
    assert c.get(f"/api/konten/{kat['id']}").json()["art"] == "aufwand"
    assert c.get(f"/api/konten/{giro['id']}").json()["art"] == "girokonto"


def test_darlehenskonto_eines_kredits_bleibt_kreditkonto(c):
    giro = _konto(c, "Giro", "girokonto")
    darlehen = _konto(c, "Darlehen", "kreditkonto")
    zins = _konto(c, "Zinsen", "aufwand")
    r = c.post("/api/kredite", json={
        "name": "Darlehen Fiktiv", "konto_id": darlehen["id"], "zahlungskonto_id": giro["id"],
        "zins_konto_id": zins["id"], "restschuld": 1_000_000, "stand_datum": "2025-01-15", "sollzins": 36_000,
        "rate": 50_000, "erste_faelligkeit": "2025-02-01",
        "bedingungen": [{"feld": "empfaenger", "operator": "gleich", "wert": "Fiktivbank AG"}]})
    assert r.status_code == 201, r.text
    r = c.patch(f"/api/konten/{darlehen['id']}", json={"art": "girokonto"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "konto_in_verwendung"
    assert c.patch(f"/api/konten/{darlehen['id']}", json={"art": "kreditkonto"}).status_code == 200


def test_gespeicherte_betraege_bleiben_bei_typwechsel(c):
    karte = _konto(c, "Karte", "girokonto")
    kat = _konto(c, "Einkauf", "aufwand")
    c.post("/api/buchungen", json={"datum": "2026-11-02", "splits": [{"konto_id": karte["id"], "betrag": -4_990},
                                                                     {"konto_id": kat["id"], "betrag": 4_990}]})
    assert c.patch(f"/api/konten/{karte['id']}", json={"art": "kreditkonto"}).status_code == 200
    liste = c.get("/api/buchungen", params={"konto_id": karte["id"]}).json()
    assert [b["betrag"] for b in liste["eintraege"]] == [-4_990]
    u = c.get("/api/kontenuebersicht").json()
    saldo = {k["konto_id"]: k["saldo_gesamt"] for k in u["konten"]}
    assert saldo[karte["id"]] == -4_990          # Finanzübersicht: Schulden gehen negativ ein
    assert u["summe_bestand"] == -4_990


# ---------------------------------------------------------------------------------------------- Inhaber


def test_inhaber_anlegen_lesen_aendern_entfernen(c):
    k = _konto(c, "Giro", "girokonto", inhaber={"vorname": "  Erika ", "nachname": "Mustermann"})
    assert k["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
    assert c.get(f"/api/konten/{k['id']}").json()["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
    r = c.patch(f"/api/konten/{k['id']}", json={"inhaber": {"vorname": "", "nachname": "Muster"}})
    assert r.status_code == 200 and r.json()["inhaber"] == {"vorname": "", "nachname": "Muster"}
    r = c.patch(f"/api/konten/{k['id']}", json={"inhaber": None})
    assert r.status_code == 200 and "inhaber" not in r.json()
    r = c.patch(f"/api/konten/{k['id']}", json={"inhaber": {"vorname": " ", "nachname": ""}})
    assert r.status_code == 200 and "inhaber" not in r.json()
    assert all("inhaber" not in x for x in c.get("/api/konten").json())


def test_inhaber_teilweise_angeben_und_andere_felder_lassen_ihn(c):
    k = _konto(c, "Giro", "girokonto", inhaber={"nachname": "Mustermann"})
    assert k["inhaber"] == {"vorname": "", "nachname": "Mustermann"}
    r = c.patch(f"/api/konten/{k['id']}", json={"name": "Giro neu"})
    assert r.json()["inhaber"] == {"vorname": "", "nachname": "Mustermann"}


def test_inhaber_ungueltig(c):
    kat = _konto(c, "Lebensmittel", "aufwand")
    r = c.patch(f"/api/konten/{kat['id']}", json={"inhaber": {"vorname": "Erika", "nachname": ""}})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "inhaber_ungueltig"
    r = c.post("/api/konten", json={"name": "X", "art": "ertrag", "inhaber": {"vorname": "A"}})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "inhaber_ungueltig"
    giro = _konto(c, "Giro", "girokonto")
    for falsch in ({"vorname": "x" * 201}, {"vorname": 1}, {"titel": "Dr."}, "Erika"):
        r = c.patch(f"/api/konten/{giro['id']}", json={"inhaber": falsch})
        assert r.status_code == 422 and r.json()["fehler"]["code"] == "validierung", falsch
    # leerer Inhaber an einer Kategorie stört nicht
    assert c.patch(f"/api/konten/{kat['id']}", json={"inhaber": None}).status_code == 200


def test_typwechsel_behaelt_inhaber(c):
    k = _konto(c, "Karte", "girokonto", inhaber={"vorname": "Erika", "nachname": "Mustermann"})
    r = c.patch(f"/api/konten/{k['id']}", json={"art": "kreditkonto"})
    assert r.json()["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}


def test_konto_mit_inhaber_loeschen(c):
    k = _konto(c, "Giro", "girokonto", inhaber={"vorname": "Erika", "nachname": "Mustermann"})
    assert c.delete(f"/api/konten/{k['id']}").status_code == 204
    k2 = _konto(c, "Giro", "girokonto")
    assert "inhaber" not in k2


# ---------------------------------------------------------------------------------------------- Protokoll


def _letzte(c):
    return c.get("/api/aenderungen").json()["eintraege"][0]


def test_protokoll_und_rueckgaengig(c):
    k = _konto(c, "Giro", "girokonto")
    assert c.patch(f"/api/konten/{k['id']}", json={"art": "kreditkonto",
                                                   "inhaber": {"vorname": "Erika", "nachname": "Muster"}}).status_code == 200
    a = c.get(f"/api/aenderungen/{_letzte(c)['id']}").json()
    e = [x for x in a["eintraege"] if x["objekt"] == "konto"][0]
    assert "inhaber" not in e["vorher"] and e["vorher"]["art"] == "girokonto"
    assert e["nachher"]["inhaber"] == {"vorname": "Erika", "nachname": "Muster"}
    assert e["nachher"]["art"] == "kreditkonto"
    r = c.post(f"/api/aenderungen/{a['id']}/rueckgaengig")
    assert r.status_code == 200, r.text
    nach = c.get(f"/api/konten/{k['id']}").json()
    assert nach["art"] == "girokonto" and "inhaber" not in nach
    # Rückgängig eines Löschens stellt den Inhaber wieder her
    c.patch(f"/api/konten/{k['id']}", json={"inhaber": {"vorname": "Erika", "nachname": "Muster"}})
    assert c.delete(f"/api/konten/{k['id']}").status_code == 204
    assert c.post(f"/api/aenderungen/{_letzte(c)['id']}/rueckgaengig").status_code == 200
    assert c.get(f"/api/konten/{k['id']}").json()["inhaber"] == {"vorname": "Erika", "nachname": "Muster"}


# ---------------------------------------------------------------------------------------------- Sicherung


def _einspielen(c, datei: bytes):
    return c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                  files={"datei": ("s.zip", datei, "application/zip")})


def test_sicherung_erfasst_typ_und_inhaber(c):
    k = _konto(c, "Karte", "girokonto", inhaber={"vorname": "Erika", "nachname": "Mustermann"})
    _konto(c, "Spar", "sparkonto")
    c.patch(f"/api/konten/{k['id']}", json={"art": "kreditkonto"})
    datei = c.get("/api/sicherung").content
    with zipfile.ZipFile(io.BytesIO(datei)) as z:
        assert json.loads(z.read("manifest.json"))["schemaversion"] == 12
    c.patch(f"/api/konten/{k['id']}", json={"art": "girokonto", "inhaber": None})
    r = _einspielen(c, datei)
    assert r.status_code == 200, r.text
    nach = c.get(f"/api/konten/{k['id']}").json()
    assert nach["art"] == "kreditkonto"
    assert nach["inhaber"] == {"vorname": "Erika", "nachname": "Mustermann"}
    # Probelauf derselben Datei: gleicher Inhalt
    r = c.post("/api/sicherung/einspielen", params={"trocken": "true"},
               files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 200, r.text
    assert r.json()["geaendert"] is False, r.json()


def test_inhalt_ohne_inhaber_unveraendert(c, tmp_path):
    """Ohne Inhaber bleibt die Inhaltsprüfsumme die frühere (Form ohne Feld ``inhaber``)."""
    _konto(c, "Giro", "girokonto")
    datei = c.get("/api/sicherung").content
    with zipfile.ZipFile(io.BytesIO(datei)) as z:
        m = json.loads(z.read("manifest.json"))
    from kontor import sicherung
    form = {"konto": {1: {"id": 1, "name": "Giro", "art": "girokonto", "eltern_id": None, "iban": None,
                          "waehrung": "EUR", "geschlossen": False, "eroeffnet_am": None, "notiz": "",
                          "extern_id": None, "ist_kategorie": False}}}
    arten = [a for a in sicherung.OBJEKTE_IMMER]
    leer = {o: {} for o in sicherung.OBJEKTE}
    assert sicherung.inhalt_sha256({**leer, **form}, arten) == m["inhalt_sha256"]


def _als_version_11(datei: bytes, tmp_path) -> bytes:
    """Baut aus einer Sicherung ohne Inhaber eine der Schemaversion 11 (ohne Tabelle ``konto_inhaber``)."""
    with zipfile.ZipFile(io.BytesIO(datei)) as z:
        m = json.loads(z.read("manifest.json"))
        db = z.read("kontor.sqlite")
    p = tmp_path / "alt.sqlite"
    p.write_bytes(db)
    con = sqlite3.connect(p)
    con.execute("DROP TABLE konto_inhaber")
    con.commit()
    con.execute("VACUUM")
    con.close()
    db = p.read_bytes()
    m["schemaversion"] = 11
    m["datenbank_sha256"] = hashlib.sha256(db).hexdigest()
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(m))
        z.writestr("kontor.sqlite", db)
    return aus.getvalue()


def test_aeltere_sicherung_ohne_inhaber(c, tmp_path):
    k = _konto(c, "Giro", "girokonto")
    alt = _als_version_11(c.get("/api/sicherung").content, tmp_path)
    c.patch(f"/api/konten/{k['id']}", json={"inhaber": {"vorname": "Erika", "nachname": "Mustermann"}})
    r = _einspielen(c, alt)
    assert r.status_code == 200, r.text
    assert "inhaber" not in c.get(f"/api/konten/{k['id']}").json()


# ---------------------------------------------------------------------------------------------- Oberfläche


def test_oberflaeche_kennt_typ_inhaber_und_vorzeichen(auslieferung):
    ui = auslieferung.get("/oeffentlich/app/ui.js").text
    for tid in ("einstellungen-art", "einstellungen-inhaber-vorname", "einstellungen-inhaber-nachname"):
        assert f'"{tid}"' in ui, tid
    kern = auslieferung.get("/oeffentlich/app/kern.js").text
    assert "export function vorzeichen" in kern
