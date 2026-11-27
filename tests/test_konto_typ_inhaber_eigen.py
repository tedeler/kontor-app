"""Eigene Tests zum Feature „konto-typ-inhaber“ (D-312), aus den Core-Tests verschoben (Zeitbudget): Kredit hält
den Kontotyp, Protokoll und Rückgängig, Inhaltsprüfsumme ohne Inhaber, ältere Sicherungen ohne Tabelle
``konto_inhaber``."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile

import pytest

from .core.test_konto_typ_inhaber import _einspielen, _konto


@pytest.fixture
def c(client):
    return client


def _letzte(c):
    return c.get("/api/aenderungen").json()["eintraege"][0]


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
