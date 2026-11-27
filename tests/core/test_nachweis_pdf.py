"""Core-Tests zum Feature „nachweis-pdf“ (D-303): markierte Buchungen eines Bankkontos als Nachweis im Stil eines
Kontoauszugs.

- ``GET /api/export/nachweis.pdf?konto_id=…&buchung_id=…&buchung_id=…[&inhaber=…]`` liefert ein PDF mit genau den
  angegebenen Buchungen (Datum, Empfänger, Verwendungszweck, Betrag auf diesem Konto), der Summe, dem Auszugsdatum
  (heute), Kontoinhaber, BIC und der gekürzten IBAN. Kontostände kommen nicht vor.
- Der Nachweis weist sich als Auszug aus der Homebanking-Software aus („kein Dokument der Bank“).
- Buchungen, die nicht von der Bank abgerufen oder danach geändert wurden, tragen einen Hinweis.
- ``GET /api/export/nachweis/angaben?konto_id=…`` liefert die Vorbelegung (Kontoinhaber, BIC) aus den Kontodaten der
  Bank.
"""

from __future__ import annotations

import datetime as dt
import io
import re

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from kontor import db, protokoll
from kontor.app import create_app
from kontor.config import KontorConfig

GIRO_IBAN = "DE79000000000004711001"
GEKUERZT = "DE79 XXXX XXXX XXXX XXXX 1001"


@pytest.fixture
def welt(tmp_path):
    pfad = tmp_path / "k.sqlite3"
    c = TestClient(create_app(KontorConfig(datenbank=pfad, mock_modus=True, mock_heute=dt.date(2024, 6, 30),
                                           planer_starten=False)))
    assert c.post("/api/sync", json={}).json()["status"] == "erfolgreich"
    giro = next(k for k in c.get("/api/konten").json() if k["iban"] == GIRO_IBAN)
    buchungen = c.get("/api/buchungen", params={"konto_id": giro["id"], "pro_seite": 200}).json()["eintraege"]
    return c, giro["id"], buchungen, pfad


def _text(r) -> str:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(r.content)).pages)


def _nachweis(c, konto_id, ids, **extra):
    return c.get("/api/export/nachweis.pdf", params={"konto_id": konto_id, "buchung_id": ids, **extra})


def _de(iso):
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def _eur(cent):
    e, r = divmod(abs(cent), 100)
    return f"{'-' if cent < 0 else '+'}{e:,}".replace(",", ".") + f",{r:02d}"


def _waehlen(buchungen, zweck_anfang):
    return next(b for b in buchungen if b["verwendungszweck"].startswith(zweck_anfang))


def test_enthaelt_genau_die_markierten_buchungen_und_die_summe(welt):
    c, giro, buchungen, _ = welt
    miete = _waehlen(buchungen, "Miete")
    gehalt = _waehlen(buchungen, "Gehalt")
    andere = [b for b in buchungen if b["id"] not in (miete["id"], gehalt["id"])]
    r = _nachweis(c, giro, [miete["id"], gehalt["id"]], inhaber="Erika Mustermann (fiktiv)")
    assert re.match(r'attachment; filename="kontor-nachweis-20240630\.pdf"', r.headers["content-disposition"])
    assert r.headers["cache-control"] == "no-store"
    t = _text(r)
    for b in (miete, gehalt):
        assert _de(b["datum"]) in t
        assert b["empfaenger"]["name"] in t
        assert b["verwendungszweck"] in t
        assert _eur(b["betrag"]) in t
    for b in andere:
        assert b["verwendungszweck"] not in t, "nicht markierte Buchungen gehören nicht in den Nachweis"
    assert "Summe der 2 ausgewählten Buchungen" in t
    assert _eur(miete["betrag"] + gehalt["betrag"]) in t
    assert "Erika Mustermann (fiktiv)" in t
    assert "auszugsdatum" in t.lower() and "30.06.2024" in t
    assert "kein Dokument der Bank" in t and "Homebanking-Software" in t
    assert "Kontostand" not in t


def test_iban_ist_gekuerzt_und_nie_vollstaendig_in_der_datei(welt):
    c, giro, buchungen, _ = welt
    r = _nachweis(c, giro, [buchungen[0]["id"]])
    assert GEKUERZT in _text(r)
    roh = r.content
    for teil in (GIRO_IBAN, "0000 0000 0047", "00000000000047"):
        assert teil.encode() not in roh
    assert b"4711001" not in roh and b"47110" not in roh


def test_hinweise_bei_abweichung_vom_umsatz_der_bank(welt):
    """Je geändertes Feld ein Hinweis; unveränderte Bankbuchungen ohne Hinweis. Eine Buchung je Fall."""
    c, giro, buchungen, _ = welt
    zweck, datum, betrag, empf = (_waehlen(buchungen, z) for z in ("Miete 04", "Miete 05", "Miete 06", "Gehalt 04"))
    unveraendert = _waehlen(buchungen, "Gehalt 05")
    assert c.patch(f"/api/buchungen/{zweck['id']}", json={"verwendungszweck": "Miete geändert"}).status_code == 200
    assert c.patch(f"/api/buchungen/{datum['id']}", json={"datum": "2024-05-04"}).status_code == 200
    splits = [{"konto_id": s["konto_id"], "betrag": s["betrag"] * 2, "memo": s["memo"]} for s in betrag["splits"]]
    r = c.put(f"/api/buchungen/{betrag['id']}/splits", json={"splits": splits})
    assert r.status_code == 200, r.text
    neu = c.post("/api/empfaenger", json={"name": "Anderer Arbeitgeber (fiktiv)"}).json()["id"]
    assert c.patch(f"/api/buchungen/{empf['id']}", json={"empfaenger_id": neu}).status_code == 200
    for b, feld in ((zweck, "Verwendungszweck"), (datum, "Datum"), (betrag, "Betrag"), (empf, "Empfänger")):
        t = _text(_nachweis(c, giro, [b["id"]]))
        assert t.count("Hinweis:") == 1 and f"Hinweis: Weicht vom Umsatz der Bank ab: {feld}" in t, feld
    assert _eur(betrag["betrag"] * 2) in _text(_nachweis(c, giro, [betrag["id"]]))
    assert "Hinweis" not in _text(_nachweis(c, giro, [unveraendert["id"]]))
    # Umbenennen des Empfängers ist eine Abweichung vom Namen beim Abruf
    r = c.patch(f"/api/empfaenger/{unveraendert['empfaenger']['id']}", json={"name": "Arbeitgeber neu (fiktiv)"})
    assert r.status_code == 200, r.text
    t = _text(_nachweis(c, giro, [unveraendert["id"]]))
    assert "Arbeitgeber neu (fiktiv)" in t and "Hinweis: Weicht vom Umsatz der Bank ab: Empfänger" in t


def test_von_hand_erfasste_buchung_hat_hinweis(welt):
    c, giro, buchungen, _ = welt
    kat = c.post("/api/konten", json={"name": "Haushalt", "art": "aufwand"}).json()["id"]
    r = c.post("/api/buchungen", json={"datum": "2024-06-01", "verwendungszweck": "Bar bezahlt",
                                       "splits": [{"konto_id": giro, "betrag": -1234},
                                                  {"konto_id": kat, "betrag": 1234}]})
    assert r.status_code == 201, r.text
    t = _text(_nachweis(c, giro, [r.json()["id"]]))
    assert "Hinweis: Nicht von der Bank abgerufen (von Hand erfasst oder importiert)" in t
    assert "-12,34" in t


def test_kuerzel_v_p_und_kontextmenue(auslieferung):
    js = auslieferung.get("/oeffentlich/app/konto.js").text
    tabelle = js[js.index("const KUERZEL = ["):js.index("const VORTASTEN")]
    assert re.search(r'\["v", "p", "Nachweis als PDF[^"]*", .*"bestand"\]', tabelle)
    assert 'tid: "km-nachweis"' in js


def _con(pfad):
    return db.verbinde(KontorConfig(datenbank=pfad, mock_modus=True).aktive_datenbank)


def test_hinweise_ueberstehen_das_kuerzen_des_protokolls(welt):
    """D-302 kürzt das Änderungsprotokoll; der Maßstab für den Nachweis bleibt (D-303)."""
    c, giro, buchungen, pfad = welt
    b = _waehlen(buchungen, "Miete 04")
    unveraendert = _waehlen(buchungen, "Gehalt 04")
    assert c.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "Miete geändert"}).status_code == 200
    con = _con(pfad)
    try:
        assert protokoll.kuerzen(con, "9999-12-31T00:00:00Z", 10**9) > 0
        assert con.execute("SELECT COUNT(*) FROM aenderung").fetchone()[0] == 0
    finally:
        con.close()
    t = _text(_nachweis(c, giro, [b["id"], unveraendert["id"]]))
    assert t.count("Hinweis:") == 1
    assert "Hinweis: Weicht vom Umsatz der Bank ab: Verwendungszweck" in t


