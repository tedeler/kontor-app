"""Core-Tests zum Feature „nachweis-pdf“ (D-302): markierte Buchungen eines Bankkontos als Nachweis im Stil eines
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

from kontor import bankzugang, db
from kontor.app import create_app
from kontor.config import KontorConfig
from kontor.plugins.bank import BankKonto

GIRO_IBAN = "DE79000000000004711001"
GEKUERZT = "DE79 •••• •••• •••• •••• 1001"


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
    assert "Auszugsdatum" in t and "30.06.2024" in t
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


def test_reihenfolge_nach_datum(welt):
    c, giro, buchungen, _ = welt
    spaet, frueh = sorted(buchungen, key=lambda b: (b["datum"], b["id"]))[-1], buchungen[-1]
    frueh = min(buchungen, key=lambda b: (b["datum"], b["id"]))
    t = _text(_nachweis(c, giro, [spaet["id"], frueh["id"]]))
    assert t.index(_de(frueh["datum"])) < t.index(_de(spaet["datum"]))


def test_unveraenderte_bankbuchung_ohne_hinweis(welt):
    c, giro, buchungen, _ = welt
    t = _text(_nachweis(c, giro, [_waehlen(buchungen, "Miete")["id"]]))
    assert "Hinweis" not in t


@pytest.mark.parametrize("feld,wert,name", [
    ("verwendungszweck", "Miete geändert", "Verwendungszweck"),
    ("datum", "2024-04-02", "Datum"),
])
def test_geaenderte_bankbuchung_hat_hinweis(welt, feld, wert, name):
    c, giro, buchungen, _ = welt
    b = _waehlen(buchungen, "Miete 04")
    assert c.patch(f"/api/buchungen/{b['id']}", json={feld: wert}).status_code == 200
    t = _text(_nachweis(c, giro, [b["id"]]))
    assert f"Hinweis: Nach dem Abruf von der Bank geändert: {name}" in t


def test_geaenderter_betrag_hat_hinweis(welt):
    c, giro, buchungen, _ = welt
    b = _waehlen(buchungen, "Miete 04")
    splits = [{"konto_id": s["konto_id"], "betrag": s["betrag"] * 2, "memo": s["memo"]} for s in b["splits"]]
    r = c.put(f"/api/buchungen/{b['id']}/splits", json={"splits": splits})
    assert r.status_code == 200, r.text
    t = _text(_nachweis(c, giro, [b["id"]]))
    assert "Hinweis: Nach dem Abruf von der Bank geändert: Betrag" in t
    assert _eur(b["betrag"] * 2) in t


def test_umbenannter_empfaenger_hat_hinweis(welt):
    c, giro, buchungen, _ = welt
    b = _waehlen(buchungen, "Miete 04")
    r = c.patch(f"/api/empfaenger/{b['empfaenger']['id']}", json={"name": "Vermieter (fiktiv)"})
    assert r.status_code == 200, r.text
    t = _text(_nachweis(c, giro, [b["id"]]))
    assert "Vermieter (fiktiv)" in t
    assert "Hinweis: Nach dem Abruf von der Bank geändert: Empfänger" in t


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


def test_inhaber_und_bic_aus_den_kontodaten_der_bank(welt):
    c, giro, buchungen, pfad = welt
    assert c.get("/api/export/nachweis/angaben", params={"konto_id": giro}).json() == {"inhaber": "", "bic": None}
    con = db.verbinde(pfad)
    try:
        with con:
            bankzugang.konten_uebernehmen(con, [BankKonto(GIRO_IBAN, "TESTDEFFXXX", "Giro", "girokonto",
                                                          "Max Mustermann (fiktiv)", "EUR")])
    finally:
        con.close()
    assert c.get("/api/export/nachweis/angaben", params={"konto_id": giro}).json() == {
        "inhaber": "Max Mustermann (fiktiv)", "bic": "TESTDEFFXXX"}
    t = _text(_nachweis(c, giro, [buchungen[0]["id"]]))
    assert "Max Mustermann (fiktiv)" in t and "TESTDEFFXXX" in t
    t = _text(_nachweis(c, giro, [buchungen[0]["id"]], inhaber="Erika Mustermann (fiktiv)"))
    assert "Erika Mustermann (fiktiv)" in t and "Max Mustermann" not in t


def test_fehler(welt):
    c, giro, buchungen, _ = welt
    kat = c.post("/api/konten", json={"name": "Haushalt", "art": "aufwand"}).json()["id"]
    tagesgeld = next(k["id"] for k in c.get("/api/konten").json() if k["art"] == "sparkonto")
    fremd = next(b["id"] for b in c.get("/api/buchungen", params={"konto_id": tagesgeld}).json()["eintraege"])

    def code(r, status):
        assert r.status_code == status, r.text
        return r.json()["fehler"]["code"]

    code(c.get("/api/export/nachweis.pdf", params={"konto_id": giro}), 422)                 # keine Buchung
    code(c.get("/api/export/nachweis.pdf", params={"buchung_id": buchungen[0]["id"]}), 422)  # kein Konto
    code(_nachweis(c, giro, list(range(1, 502))), 422)                                       # zu viele
    code(_nachweis(c, giro, [buchungen[0]["id"]], inhaber="x" * 201), 422)
    assert code(_nachweis(c, 999999, [buchungen[0]["id"]]), 404) == "nicht_gefunden"
    assert code(_nachweis(c, giro, [999999]), 404) == "nicht_gefunden"
    assert code(_nachweis(c, kat, [buchungen[0]["id"]]), 422) == "kein_bestandskonto"
    assert code(_nachweis(c, giro, [buchungen[0]["id"], fremd]), 422) == "buchung_nicht_im_konto"
    assert code(c.get("/api/export/nachweis/angaben", params={"konto_id": kat}), 422) == "kein_bestandskonto"
    # doppelte Angabe zählt einmal
    t = _text(_nachweis(c, giro, [buchungen[0]["id"], buchungen[0]["id"]]))
    assert "Summe der 1 ausgewählten Buchung" in t


def test_nur_lesend(welt):
    c, giro, buchungen, _ = welt
    vorher = c.get("/api/aenderungen").json()["eintraege"][0]["id"]
    _text(_nachweis(c, giro, [b["id"] for b in buchungen]))
    assert c.get("/api/aenderungen").json()["eintraege"][0]["id"] == vorher


def test_kuerzel_v_p_und_kontextmenue(client):
    js = client.get("/oeffentlich/app/konto.js").text
    tabelle = js[js.index("const KUERZEL = ["):js.index("const VORTASTEN")]
    assert re.search(r'\["v", "p", "Nachweis als PDF[^"]*", .*"bestand"\]', tabelle)
    assert 'tid: "km-nachweis"' in js
