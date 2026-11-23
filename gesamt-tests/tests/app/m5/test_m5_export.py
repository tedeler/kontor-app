"""M5: Export der Buchungsliste als CSV und PDF (berichte.md 4, 5; T 14; E-107, E-108).

CSV: verlustfreie Rundreise gegen die REST-Darstellung (unabhängig aus ``GET /api/buchungen``). PDF: Marken je
Buchung im mit ``pypdf`` extrahierten Text.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import buchung_zustand, letzte_aenderung_id
from tests.hilfen.m5 import (M5, SPALTEN, betrag_text, csv_buchungen, csv_lesen, de_datum, export, lade,
                             pdf_marken, pdf_text, pdf_zeile, rest_als_csv_form)
from tests.hilfen.pfade import KMY

WAHR = lade(M5 / "berichte.erwartung.json")


@pytest.fixture(scope="module")
def sonder_api(api_fabrik):
    a = api_fabrik()
    a.import_kmy(KMY / "sonderfaelle.kmy", erwartet=200)
    a.import_kmy(KMY / "dubletten.kmy", erwartet=200)
    return a


# ------------------------------------------------------------------ CSV
@pytest.mark.kern
def test_csv_format(sonder_api):
    r = export(sonder_api, "csv")
    assert r.headers["content-type"].replace(" ", "").lower() == "text/csv;charset=utf-8"
    roh = r.content
    assert roh.startswith(b"\xef\xbb\xbf" + ";".join(SPALTEN).encode() + b"\r\n")
    zeilen = csv_lesen(roh)
    assert len(zeilen) == sum(len(b["splits"]) for b in sonder_api.alle_buchungen())


@pytest.mark.kern
@pytest.mark.parametrize("quelle", ["standard", "sonder"])
def test_csv_rundreise_verlustfrei(standard_api, sonder_api, quelle):
    api = standard_api if quelle == "standard" else sonder_api
    ist = csv_buchungen(csv_lesen(export(api, "csv").content))
    assert ist == rest_als_csv_form(api, api.alle_buchungen())


@pytest.mark.kern
def test_csv_ergibt_die_protokollform(sonder_api):
    """Verlustfrei heißt: alle Felder der Protokollform außer dem Vorschlag sind zurückzugewinnen (berichte.md 4.2)."""
    api = sonder_api
    emp = {e["name"]: e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten}
    tags = {t["name"].casefold(): t["id"] for t in api.get("/api/tags", erwartet=200).daten}
    aus_csv = {}
    for b in csv_buchungen(csv_lesen(export(api, "csv").content)):
        aus_csv[b["id"]] = {"id": b["id"], "datum": b["datum"], "empfaenger_id": emp[b["empfaenger"]] if b["empfaenger"]
                            else None, "verwendungszweck": b["verwendungszweck"], "status": b["status"],
                            "splits": [{k: s[k] for k in ("id", "konto_id", "betrag", "memo", "abstimmung_id")}
                                       for s in b["splits"]],
                            "tag_ids": sorted(tags[t.casefold()] for t in b["tags"]), "extern_ids": b["extern_ids"],
                            "gegen_iban": b["gegen_iban"]}
    rest = {}
    for b in api.alle_buchungen():
        z = buchung_zustand(b)
        del z["vorschlag"]
        rest[b["id"]] = z
    assert aus_csv == rest


@pytest.mark.kern
@pytest.mark.parametrize("params", [
    {"sortierung": "-betrag"}, {"sortierung": "empfaenger"}, {"von": "2023-02-01", "bis": "2023-04-30"},
    {"betrag_min": 10_000}, {"suche": "miete"}, {"status": ["importiert"], "sortierung": "-datum"},
    {"ohne_empfaenger": True}])
def test_csv_mit_filtern_wie_buchungsliste(standard_api, params):
    ist = csv_buchungen(csv_lesen(export(standard_api, "csv", **params).content))
    assert [b["id"] for b in ist] == [b["id"] for b in standard_api.alle_buchungen(**params)]


@pytest.mark.kern
def test_csv_kontofilter_gleich_wahrheit(standard_api):
    f = WAHR["export"]["filter"]
    kid = next(k["id"] for k in standard_api.konten() if k["extern_id"] == f["konto"])
    ist = csv_buchungen(csv_lesen(export(standard_api, "csv", konto_id=kid, von=f["von"], bis=f["bis"]).content))
    assert [b["extern_ids"] for b in ist] == [[e] for e in WAHR["export"]["extern_ids"]]
    # mit konto_id werden trotzdem alle Splits jeder Buchung exportiert
    voll = {b["id"]: b for b in standard_api.alle_buchungen()}
    assert all(len(b["splits"]) == len(voll[b["id"]]["splits"]) for b in ist)


@pytest.mark.kern
def test_csv_leer_und_fehler(api):
    zeilen = csv_lesen(export(api, "csv").content)
    assert zeilen == []
    assert fehlercode(api.get("/api/export/buchungen.csv", params={"von": "2024-02-01", "bis": "2024-01-01"},
                              erwartet=422)) == "validierung"
    assert fehlercode(api.get("/api/export/buchungen.csv", params={"sortierung": "zufall"},
                              erwartet=422)) == "validierung"


@pytest.mark.kern
@pytest.mark.parametrize("cent,text", [(0, "0,00"), (-5, "-0,05"), (100, "1,00"), (-123_456_789, "-1234567,89"),
                                       (999_999_999_999, "9999999999,99")])
def test_csv_betragsformat(api, cent, text):
    g, k = api.konto("Giro")["id"], api.konto("Gegen", "eigenkapital")["id"]
    api.buchung("2024-01-01", [(g, cent), (k, -cent)])
    (z1, z2) = csv_lesen(export(api, "csv").content)
    assert (z1[SPALTEN.index("betrag")], z2[SPALTEN.index("betrag")]) == (text, betrag_text(-cent))
    assert betrag_text(cent) == text


TEXT = st.text(st.characters(codec="utf-8", exclude_categories=["Cs"]), max_size=40)
NAME = st.text(st.characters(codec="utf-8", exclude_categories=["Cs", "Cc", "Zs", "Zl", "Zp"]),
               min_size=1, max_size=20)


@pytest.mark.kern
@given(zweck=TEXT, memo=TEXT, empf=NAME, tag=NAME, sonder=st.sampled_from(['; "x"', "a\r\nb", " lead", "trail ",
                                                                           '"', "\n", "=SUMME(A1)"]))
def test_csv_rundreise_beliebige_texte(api_fabrik, zweck, memo, empf, tag, sonder):
    api = api_fabrik()
    g, k = api.konto("Giro;\"Haupt\"")["id"], api.konto(f"Kat {sonder}", "aufwand")["id"]
    e = api.empfaenger(empf + sonder.strip() if (empf + sonder).strip() else "x")["id"]
    t = api.tag(tag)["id"]
    api.buchung("2024-02-29", [(g, -1999, memo + sonder), (k, 1999, sonder)], empfaenger_id=e,
                verwendungszweck=zweck + sonder, tag_ids=[t])
    ist = csv_buchungen(csv_lesen(export(api, "csv").content))
    assert ist == rest_als_csv_form(api, api.alle_buchungen())


def test_export_erzeugt_keine_aenderung(sonder_api):
    a0 = letzte_aenderung_id(sonder_api)
    export(sonder_api, "csv")
    export(sonder_api, "pdf")
    assert letzte_aenderung_id(sonder_api) == a0


# ------------------------------------------------------------------ PDF
def _pruefe_pdf(api, roh: bytes, buchungen: list[dict]) -> str:
    text = pdf_text(roh)
    assert sorted(pdf_marken(text)) == sorted(b["id"] for b in buchungen), "Marken = genau die exportierten Buchungen"
    assert text.count(f"Anzahl Buchungen: {len(buchungen)}") == 1
    return text


@pytest.mark.parametrize("quelle", ["standard", "sonder"])
def test_pdf_enthaelt_alle_buchungen(standard_api, sonder_api, quelle, netz_gesperrt):
    api = standard_api if quelle == "standard" else sonder_api
    bs = api.alle_buchungen()
    text = _pruefe_pdf(api, export(api, "pdf").content, bs)
    for b in bs[:: max(1, len(bs) // 40)]:
        z = pdf_zeile(text, b["id"])
        assert de_datum(b["datum"]) in z and betrag_text(b["betrag"]) in z, (z, b["datum"], b["betrag"])


@pytest.mark.parametrize("params", [{"von": "2023-03-01", "bis": "2023-03-31"}, {"suche": "strom"},
                                    {"betrag_min": 50_000, "sortierung": "-betrag"}])
def test_pdf_mit_filtern(standard_api, params, netz_gesperrt):
    bs = standard_api.alle_buchungen(**params)
    assert bs, params
    _pruefe_pdf(standard_api, export(standard_api, "pdf", **params).content, bs)


def test_pdf_kontobetrag_bei_kontofilter(standard_api, netz_gesperrt):
    kid = next(k["id"] for k in standard_api.konten() if k["extern_id"] == WAHR["export"]["filter"]["konto"])
    bs = standard_api.alle_buchungen(konto_id=kid, von="2023-03-01", bis="2023-03-31")
    text = _pruefe_pdf(standard_api, export(standard_api, "pdf", konto_id=kid, von="2023-03-01",
                                            bis="2023-03-31").content, bs)
    assert any(b["betrag"] < 0 for b in bs)
    for b in bs:
        assert betrag_text(b["betrag"]) in pdf_zeile(text, b["id"])


def test_pdf_leer(api, netz_gesperrt):
    text = pdf_text(export(api, "pdf").content)
    assert pdf_marken(text) == [] and text.count("Anzahl Buchungen: 0") == 1
    assert fehlercode(api.get("/api/export/buchungen.pdf", params={"betrag_min": 5, "betrag_max": 1},
                              erwartet=422)) == "validierung"
