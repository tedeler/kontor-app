"""Eigene Tests zum Feature „nachweis-pdf“ (D-303), die nicht in die Core-Tests passen (Zeitbudget): Reihenfolge,
Vorbelegung aus den Kontodaten der Bank, Fehlerfälle, nur lesend, Nachtragen aus dem Protokoll."""

from __future__ import annotations

from kontor import bankumsatz, bankzugang
from kontor.plugins.bank import BankKonto

from .core.test_nachweis_pdf import GIRO_IBAN, _con, _de, _nachweis, _text, _waehlen, welt  # noqa: F401


def test_reihenfolge_nach_datum(welt):
    c, giro, buchungen, _ = welt
    spaet, frueh = sorted(buchungen, key=lambda b: (b["datum"], b["id"]))[-1], buchungen[-1]
    frueh = min(buchungen, key=lambda b: (b["datum"], b["id"]))
    t = _text(_nachweis(c, giro, [spaet["id"], frueh["id"]]))
    assert t.index(_de(frueh["datum"])) < t.index(_de(spaet["datum"]))


def test_inhaber_und_bic_aus_den_kontodaten_der_bank(welt):
    c, giro, buchungen, pfad = welt
    assert c.get("/api/export/nachweis/angaben", params={"konto_id": giro}).json() == {"inhaber": "", "bic": None}
    con = _con(pfad)
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
    # D-316: der Kontoinhaber aus den Eigenschaften des Kontos geht den Angaben der Bank vor
    r = c.patch(f"/api/konten/{giro}", json={"inhaber": {"vorname": "Erika", "nachname": "Mustermann (fiktiv)"}})
    assert r.status_code == 200, r.text
    assert c.get("/api/export/nachweis/angaben", params={"konto_id": giro}).json() == {
        "inhaber": "Erika Mustermann (fiktiv)", "bic": "TESTDEFFXXX"}
    t = _text(_nachweis(c, giro, [buchungen[0]["id"]]))
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
    code(_nachweis(c, giro, [buchungen[0]["id"]], inhaber="x"), 422)                         # D-316: kein Parameter
    assert code(_nachweis(c, 999999, [buchungen[0]["id"]]), 404) == "nicht_gefunden"
    assert code(_nachweis(c, giro, [999999]), 404) == "nicht_gefunden"
    # D-311: Kategorien sind erlaubt, die Buchung muss aber zur Kategorie gehören; „Unkategorisiert“ nicht
    assert code(_nachweis(c, kat, [buchungen[0]["id"]]), 422) == "buchung_nicht_im_konto"
    unk = next(k["id"] for k in c.get("/api/konten").json() if k["extern_id"] == "kontor:unkategorisiert")
    assert code(_nachweis(c, unk, [buchungen[0]["id"]]), 422) == "kein_bestandskonto"
    assert code(_nachweis(c, giro, [buchungen[0]["id"], fremd]), 422) == "buchung_nicht_im_konto"
    assert c.get("/api/export/nachweis/angaben", params={"konto_id": kat}).status_code == 200
    assert code(c.get("/api/export/nachweis/angaben", params={"konto_id": unk}), 422) == "kein_bestandskonto"
    # doppelte Angabe zählt einmal
    t = _text(_nachweis(c, giro, [buchungen[0]["id"], buchungen[0]["id"]]))
    assert "Summe der 1 ausgewählten Buchung" in t


def test_nur_lesend(welt):
    c, giro, buchungen, _ = welt
    vorher = c.get("/api/aenderungen").json()["eintraege"][0]["id"]
    _text(_nachweis(c, giro, [b["id"] for b in buchungen]))
    assert c.get("/api/aenderungen").json()["eintraege"][0]["id"] == vorher


def test_nachtragen_aus_dem_protokoll(welt):
    """Schema 20: Bestand aus der Zeit davor wird einmalig aus dem (noch vorhandenen) Protokoll nachgetragen."""
    c, giro, buchungen, pfad = welt
    b = _waehlen(buchungen, "Miete 04")
    con = _con(pfad)
    try:
        with con:
            con.execute("DELETE FROM bank_umsatz")
            con.execute("DELETE FROM meta WHERE schluessel = ?", (bankumsatz.NACHGETRAGEN,))
    finally:
        con.close()
    t = _text(_nachweis(c, giro, [b["id"]]))
    assert "Hinweis: Abgleich mit dem Umsatz der Bank nicht möglich" in t
    con = _con(pfad)
    try:
        with con:
            bank = con.execute("SELECT COUNT(*) FROM buchung_extern WHERE extern_id LIKE 'bank:%'").fetchone()[0]
            assert bankumsatz.nachtragen(con) == bank > 0   # alle Bankumsätze beider Konten
            assert bankumsatz.nachtragen(con) == 0                    # nur einmal
    finally:
        con.close()
    assert c.patch(f"/api/buchungen/{b['id']}", json={"datum": "2024-04-05"}).status_code == 200
    t = _text(_nachweis(c, giro, [b["id"]]))
    assert "Hinweis: Weicht vom Umsatz der Bank ab: Datum" in t
