"""Entwicklungstests für das Feature „mail-abgleich“ (Branch feature/mail-abgleich, D-128): Erkennung von Amazon-
und PayPal-Mails, erwartete Zahlungen, Zuordnung mit Dokumenten, Protokoll/Rückgängig, Sicherung.
Synthetische Daten (Adressen unter example.invalid bzw. fiktive Inhalte); ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from kontor import db, mailerkennung
from kontor.app import create_app
from kontor.config import KontorConfig

AMAZON = "bestellbestaetigung@amazon.example.invalid"
PAYPAL = "service@paypal.example.invalid"
NR = "302-1234567-7654321"
CODE = "1AB23456CD789012E"


def bestellung(nr=NR, summe="59,90 €", gutschein=None):
    t = f"Hallo Erika,\nvielen Dank für Ihre Bestellung.\nBestellnr. {nr}\n1 x USB-Kabel (fiktiv) 9,99 €\n" \
        f"1 x Ladegerät (fiktiv) 49,91 €\nGesamtsumme: {summe}\n"
    if gutschein:
        t += f"Geschenkgutschein: -{gutschein}\n"
    return AMAZON, f"Ihre Amazon.de Bestellung von „USB-Kabel (fiktiv)“ ({nr})", t


def paypal(betrag="25,00 €", guthaben=None, code=CODE, haendler="Fiktiver Shop"):
    t = f"Sie haben {betrag} an {haendler} gesendet.\nTransaktionscode: {code}\nGesendeter Betrag: -{betrag}\n" \
        f"Bezahlt mit\n"
    if guthaben:
        t += f"PayPal-Guthaben {guthaben}\n"
    t += "Lastschrift Testbank\nBestellnummer: R-4711\n"
    return PAYPAL, f"Sie haben eine Zahlung an {haendler} gesendet", t


# ================================================================ Parser


def test_parser_amazon_bestellung_mit_gutschein():
    e = mailerkennung.erkennen(*bestellung(gutschein="10,00 €"))
    assert (e.anbieter, e.art, e.kennung, e.gesamt, e.guthaben, e.bankanteil) == \
        ("amazon", "bestellung", NR, 5990, 1000, 4990)
    assert [a.name for a in e.artikel] == ["USB-Kabel (fiktiv)", "Ladegerät (fiktiv)"]


def test_parser_amazon_storno_und_erstattung():
    assert mailerkennung.erkennen(AMAZON, f"Ihre Bestellung {NR} wurde storniert", "").art == "storno"
    e = mailerkennung.erkennen(AMAZON, "Ihre Erstattung", f"Bestellnr. {NR}\nErstattungsbetrag: 9,99 €")
    assert (e.art, e.gesamt, e.bezug) == ("erstattung", 999, NR)


def test_parser_paypal_zahlung_rueckzahlung_und_unbekannt():
    e = mailerkennung.erkennen(*paypal(betrag="1.234,56 €", guthaben="34,56 €"))
    assert (e.anbieter, e.art, e.kennung, e.haendler, e.gesamt, e.guthaben, e.bezug) == \
        ("paypal", "zahlung", CODE, "Fiktiver Shop", 123456, 3456, "R-4711")
    r = mailerkennung.erkennen(PAYPAL, "Rückzahlung von Fiktiver Shop erhalten",
                               "Rückzahlungsbetrag: 25,00 €\nTransaktionscode: 9ZZ23456CD789012E\n"
                               f"Ursprünglicher Transaktionscode: {CODE}")
    assert (r.art, r.gesamt, r.bezug, r.guthaben) == ("erstattung", 2500, CODE, 0)
    assert mailerkennung.erkennen("shop@example.invalid", "Bestellung", "Gesamtsumme: 5,00 €") is None
    assert mailerkennung.erkennen(AMAZON, "Ihre Bestellung", "keine Nummer, Gesamtsumme: 5,00 €") is None
    assert mailerkennung.erkennen(PAYPAL, "Zahlung an X", "Betrag: 5,00 €") is None  # ohne Transaktionscode


# ================================================================ App


@pytest.fixture
def app_c(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mail_abgleich=True, planer_starten=False)
    c = TestClient(create_app(cfg))
    for a in ("erika@example.invalid", "max@example.invalid"):  # ohne Postfach entfällt der Spiegel
        assert c.post("/api/mail/postfaecher", json={"adresse": a}).status_code == 201
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    return c, cfg, giro, kat


def spiegeln(cfg, absender, betreff, text, nid, empfangen="2024-03-01T10:00:00Z", postfach="erika@example.invalid"):
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        with db.transaktion(con):
            con.execute("INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text)"
                        " VALUES (?, ?, ?, ?, ?, ?)", (postfach, nid, empfangen, absender, betreff, text))
    finally:
        con.close()


def buchung(c, giro, kat, betrag, datum="2024-03-03", zweck=""):
    r = c.post("/api/buchungen", json={"datum": datum, "verwendungszweck": zweck, "splits": [
        {"konto_id": giro, "betrag": betrag}, {"konto_id": kat, "betrag": -betrag}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def abgleich(c):
    r = c.post("/api/erwartungen/abgleich")
    assert r.status_code == 200, r.text
    return r.json()


def test_aus_ohne_einstellung(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", planer_starten=False)))
    assert c.post("/api/erwartungen/abgleich").status_code == 409
    assert c.get("/api/erwartungen").json()["aktiv"] is False


def test_erkennen_idempotent_zwei_postfaecher_und_kennung_zuordnung(app_c):
    c, cfg, giro, kat = app_c
    spiegeln(cfg, *bestellung(gutschein="10,00 €"), "<a1@example.invalid>")
    spiegeln(cfg, *bestellung(gutschein="10,00 €"), "<a1@example.invalid>", postfach="max@example.invalid")
    assert abgleich(c)["neu"] == 1
    assert abgleich(c) == {"neu": 0, "ergaenzt": 0, "storniert": 0, "zugeordnet": 0, "gemeldet": 0}
    liste = c.get("/api/erwartungen").json()
    (e,) = liste["eintraege"]
    assert (e["grund"], e["betrag"], e["guthaben"], e["frist"], len(e["mails"])) == \
        ("bestellung", 4990, 1000, "2024-03-06", 2)
    assert liste["summe_offen"] == -4990
    # Abbuchung mit Bestellnummer im Verwendungszweck → automatisch, Mail als Dokument an der Buchung
    b = buchung(c, giro, kat, -4990, zweck=f"AMAZON PAYMENTS EUROPE {NR} fiktiv")
    assert abgleich(c)["zugeordnet"] == 1
    e = c.get(f"/api/erwartungen/{e['id']}").json()
    assert e["zustand"] == "erfuellt" and e["buchung_ids"] == [b] and e["offen_betrag"] == 0
    belege = c.get(f"/api/buchungen/{b}").json()["belege"]
    assert len(belege) == 1 and belege[0]["mime_typ"] == "message/rfc822"
    assert c.get("/api/erwartungen").json()["anzahl"] == 0
    assert c.get("/api/erwartungen", params={"zustand": "erfuellt"}).json()["anzahl"] == 1
    # Buchung löschen → Erwartung wieder offen (in derselben Änderung), Rückgängig stellt alles her
    assert c.delete(f"/api/buchungen/{b}").status_code == 204
    assert c.get(f"/api/erwartungen/{e['id']}").json()["zustand"] == "offen"
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    e = c.get(f"/api/erwartungen/{e['id']}").json()
    assert e["zustand"] == "erfuellt" and e["buchung_ids"] == [b]


def test_kandidaten_ohne_kennung_bestaetigen_und_loesen(app_c):
    c, cfg, giro, kat = app_c
    spiegeln(cfg, *paypal(), "<p1@example.invalid>")
    abgleich(c)
    (e,) = c.get("/api/erwartungen").json()["eintraege"]
    b1 = buchung(c, giro, kat, -2500, zweck="Lastschrift fiktiv")    # Betrag passt, kein Name → nur Kandidat
    buchung(c, giro, kat, -2400, zweck="anderes")                     # passt nicht
    assert abgleich(c)["zugeordnet"] == 0
    k = c.get(f"/api/erwartungen/{e['id']}/kandidaten").json()["eintraege"]
    assert [x["id"] for x in k] == [b1] and k[0]["betrag_gleich"] and not k[0]["kennung_passt"]
    r = c.post(f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [b1]})
    assert r.status_code == 200 and r.json()["zustand"] == "erfuellt", r.text
    assert c.post(f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [b1]}).status_code == 409
    r = c.delete(f"/api/erwartungen/{e['id']}/buchungen/{b1}")
    assert r.json()["zustand"] == "offen" and c.get(f"/api/buchungen/{b1}").json()["belege"] == []


def test_eindeutig_mit_anbietername_automatisch_aber_nicht_bei_zwei_gleichen(app_c):
    c, cfg, giro, kat = app_c
    spiegeln(cfg, *paypal(code="1AB23456CD7890121"), "<p1@example.invalid>")
    b = buchung(c, giro, kat, -2500, zweck="PP.1234.PP . Fiktiver Shop, Ihr Einkauf bei Fiktiver Shop")
    assert abgleich(c)["zugeordnet"] == 1 and c.get(f"/api/buchungen/{b}").json()["belege"]
    spiegeln(cfg, *paypal(code="1AB23456CD7890122"), "<p2@example.invalid>", empfangen="2024-04-01T10:00:00Z")
    spiegeln(cfg, *paypal(code="1AB23456CD7890123"), "<p3@example.invalid>", empfangen="2024-04-02T10:00:00Z")
    buchung(c, giro, kat, -2500, datum="2024-04-03", zweck="PayPal Fiktiver Shop")
    assert abgleich(c)["zugeordnet"] == 0  # zwei Erwartungen für eine Buchung: bestätigen lassen


def test_teillieferung_storno_guthaben_und_erstattung(app_c):
    c, cfg, giro, kat = app_c
    spiegeln(cfg, *bestellung(), "<a1@example.invalid>")
    b1 = buchung(c, giro, kat, -999, zweck=f"AMZN Mktp {NR}")
    b2 = buchung(c, giro, kat, -4991, datum="2024-03-05", zweck=f"AMZN Mktp {NR}")
    abgleich(c)
    (e,) = c.get("/api/erwartungen", params={"zustand": "erfuellt"}).json()["eintraege"]
    assert sorted(e["buchung_ids"]) == [b1, b2]
    # Bestellung ganz aus Guthaben: keine erwartete Abbuchung
    spiegeln(cfg, *bestellung(nr="302-0000000-1111111", summe="20,00 €", gutschein="20,00 €"), "<a2@example.invalid>")
    # Storno einer offenen Bestellung
    spiegeln(cfg, *bestellung(nr="302-0000000-2222222"), "<a3@example.invalid>")
    spiegeln(cfg, AMAZON, "Ihre Bestellung 302-0000000-2222222 wurde storniert", "", "<a4@example.invalid>",
             empfangen="2024-03-02T10:00:00Z")
    # Erstattung zur ersten Bestellung: Eingang mit Bezug
    spiegeln(cfg, AMAZON, "Ihre Erstattung", f"Bestellnr. {NR}\nErstattungsbetrag: 9,99 €", "<a5@example.invalid>",
             empfangen="2024-03-10T10:00:00Z")
    abgleich(c)
    alle = {x["kennung"]: x for x in c.get("/api/erwartungen", params={
        "zustand": ["offen", "guthaben", "storniert"]}).json()["eintraege"]}
    assert alle["302-0000000-1111111"]["zustand"] == "guthaben"
    assert alle["302-0000000-2222222"]["zustand"] == "storniert"
    r = c.get("/api/erwartungen", params={"grund": "rueckerstattung"}).json()["eintraege"][0]
    assert (r["richtung"], r["betrag"], r["bezug_id"], r["vorzeichen_betrag"]) == ("eingang", 999, e["id"], 999)
    g = buchung(c, giro, kat, 999, datum="2024-03-12", zweck=f"Erstattung {NR}")
    abgleich(c)
    assert c.get(f"/api/erwartungen/{r['id']}").json()["buchung_ids"] == [g]


def test_manuell_zustand_ueberfaellig_benachrichtigung_sicherung(app_c, tmp_path):
    c, cfg, giro, kat = app_c
    r = c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": " Handwerker (fiktiv) ",
                                         "betrag": 45000, "datum": "2024-01-10"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert (e["haendler"], e["frist"], e["ueberfaellig"]) == ("Handwerker (fiktiv)", "2024-01-15", True)
    assert c.post("/api/erwartungen", json={"richtung": "seitwaerts", "haendler": "x", "betrag": 1}).status_code == 422
    assert c.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "x", "betrag": 0}).status_code == 422
    abgleich(c)
    alle = c.get("/api/benachrichtigungen").json()
    meldungen = [b for b in (alle["eintraege"] if isinstance(alle, dict) else alle)
                 if b["art"] == "erwartung_ueberfaellig"]
    assert len(meldungen) == 1
    assert abgleich(c)["gemeldet"] == 0
    assert c.get("/api/erwartungen", params={"zustand": "ueberfaellig"}).json()["anzahl"] == 1
    assert c.patch(f"/api/erwartungen/{e['id']}", json={"betrag": 40000}).json()["betrag"] == 40000
    assert c.post(f"/api/erwartungen/{e['id']}/zustand", json={"zustand": "erledigt"}).json()["zustand"] == "erledigt"
    assert c.post(f"/api/erwartungen/{e['id']}/zustand", json={"zustand": "erledigt"}).status_code == 409
    # Sicherung: Rundreise enthält die erwartete Zahlung
    daten = c.get("/api/sicherung").content
    assert c.delete(f"/api/erwartungen/{e['id']}").status_code == 204
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", daten, "application/zip")})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/erwartungen/{e['id']}").json()["zustand"] == "erledigt"


def test_aus_mail_erkannt_nicht_loeschbar(app_c):
    c, cfg, *_ = app_c
    spiegeln(cfg, *paypal(), "<p1@example.invalid>")
    abgleich(c)
    (e,) = c.get("/api/erwartungen").json()["eintraege"]
    assert c.delete(f"/api/erwartungen/{e['id']}").status_code == 409
    assert dt.date.fromisoformat(e["frist"]) == dt.date(2024, 3, 6)
