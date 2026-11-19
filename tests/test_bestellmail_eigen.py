"""Entwicklungstests für das Feature „amazon-bestellnummer“ (D-208): Mails mit der Amazon-Bestellnummer einer
Buchung hängen als Dokumente an dieser Buchung. Synthetische Daten; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

from email.message import EmailMessage
from importlib import resources

import pytest
from fastapi.testclient import TestClient

from kontor import abgleich, bestellmail, db
from kontor.app import create_app
from kontor.config import KontorConfig, KonfigurationsFehler

NR = "302-1234567-7654321"
NR2 = "028-7654321-1234567"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def app_c(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mail_bestellnummer=True, planer_starten=False)
    c = TestClient(create_app(cfg))
    for a in ("erika@example.invalid", "max@example.invalid"):
        assert c.post("/api/mail/postfaecher", json={"adresse": a}).status_code == 201
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    return c, cfg, giro, kat


def spiegeln(cfg, betreff, text, nid, postfach="erika@example.invalid", roh=None,
             absender="versand@amazon.example.invalid"):
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        with db.transaktion(con):
            con.execute("INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text, roh)"
                        " VALUES (?, ?, '2024-03-01T10:00:00Z', ?, ?, ?, ?)", (postfach, nid, absender, betreff, text, roh))
    finally:
        con.close()


def buchung(c, giro, kat, betrag, zweck):
    r = c.post("/api/buchungen", json={"datum": "2024-03-03", "verwendungszweck": zweck, "splits": [
        {"konto_id": giro, "betrag": betrag}, {"konto_id": kat, "betrag": -betrag}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def lauf(c, cfg):
    abgleich.nach_ereignis(cfg, c.app.state.sync.jetzt())   # wie nach jedem Mail-Abruf und Synchronisationslauf


def belege(c, b):
    return c.get(f"/api/buchungen/{b}").json()["belege"]


def test_nummern_erkennen():
    assert bestellmail.nummern(f"AMZN Mktp DE {NR} fiktiv", None, f"{NR2}") == [NR, NR2]
    assert bestellmail.nummern("302-1234567-\n7654321 Amazon.de") == [NR]          # von der Bank umbrochen
    assert bestellmail.nummern("1302-1234567-7654321", "302-1234567-76543210", "30-1234567-7654321") == []


def test_einstellung_und_ausgelieferte_umgebung():
    env = {"KONTOR_DATENBANK": "/tmp/x.sqlite3"}
    assert KontorConfig.from_env(env).mail_bestellnummer is False
    assert KontorConfig.from_env({**env, "KONTOR_MAIL_BESTELLNUMMER": "1"}).mail_bestellnummer is True
    with pytest.raises(KonfigurationsFehler):
        KontorConfig.from_env({**env, "KONTOR_MAIL_BESTELLNUMMER": "vielleicht"})
    for datei in ("kontor.env", "kontor-test.env"):
        text = resources.files("kontor.betrieb").joinpath(datei).read_text(encoding="utf-8")
        assert "\nKONTOR_MAIL_BESTELLNUMMER=1\n" in text and "\nKONTOR_MAIL_ABGLEICH=0\n" in text


def test_alle_mails_mit_nummer_haengen_an_der_buchung(app_c):
    c, cfg, giro, kat = app_c
    b = buchung(c, giro, kat, -4990, f"{NR} AMZN Mktp DE fiktiv")
    andere = buchung(c, giro, kat, -500, "Bäckerei fiktiv")
    spiegeln(cfg, f"Bestellt: USB-Kabel (fiktiv) {NR}", "ohne Summe", "<a1@example.invalid>")       # Nummer im Betreff
    spiegeln(cfg, "Versandt: Ihr Paket", f"Bestellnummer {NR}\nkommt morgen", "<a2@example.invalid>",
             absender="irgendwer@example.invalid")                                                  # Nummer im Text
    spiegeln(cfg, "Versandt: Ihr Paket", f"Bestellnummer {NR}\nkommt morgen", "<a2@example.invalid>",
             postfach="max@example.invalid", absender="irgendwer@example.invalid")                  # zweites Postfach
    spiegeln(cfg, "Andere Bestellung", f"Bestellnummer {NR2}", "<a3@example.invalid>")
    vorher = c.get("/api/aenderungen").json()["gesamt"]
    lauf(c, cfg)
    assert len(belege(c, b)) == 2 and {d["mime_typ"] for d in belege(c, b)} == {"message/rfc822"}
    assert sorted(d["dateiname"] for d in belege(c, b))[1].startswith("Versandt")
    assert belege(c, andere) == []
    assert c.get("/api/erwartungen").json()["eintraege"] == []       # keine erwartete Zahlung
    a = c.get("/api/aenderungen").json()
    assert a["gesamt"] == vorher + 1
    assert (a["eintraege"][0]["quelle"], a["eintraege"][0]["aktion"]) == ("mail", "bestellmail_anhaengen")
    # zweiter Lauf: nichts Neues, keine Änderung
    lauf(c, cfg)
    assert len(belege(c, b)) == 2 and c.get("/api/aenderungen").json()["gesamt"] == vorher + 1
    # eine spätere Mail und eine spätere zweite Abbuchung derselben Bestellung (Teillieferung)
    spiegeln(cfg, "Rechnung", f"zur Bestellung {NR}", "<a4@example.invalid>")
    b2 = buchung(c, giro, kat, -1000, f"AMAZON PAYMENTS {NR}")
    lauf(c, cfg)
    assert len(belege(c, b)) == 3 and len(belege(c, b2)) == 3


def test_geloestes_dokument_kommt_nicht_wieder_und_rueckgaengig_bleibt(app_c):
    c, cfg, giro, kat = app_c
    b = buchung(c, giro, kat, -4990, f"{NR} Amazon.de")
    spiegeln(cfg, f"Bestellung {NR}", "Text", "<a1@example.invalid>")
    lauf(c, cfg)
    (d,) = belege(c, b)
    assert c.delete(f"/api/dokumente/{d['id']}/buchungen/{b}").status_code in (200, 204)
    lauf(c, cfg)
    assert belege(c, b) == []
    # Rückgängig der automatischen Änderung: die Mail bleibt weg
    b2 = buchung(c, giro, kat, -100, f"{NR} Amazon.de zwei")
    lauf(c, cfg)
    assert len(belege(c, b2)) == 1
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["aktion"] == "bestellmail_anhaengen"
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    lauf(c, cfg)
    assert belege(c, b2) == []


def test_pdf_anhang_und_schon_angehaengte_mail(app_c):
    c, cfg, giro, kat = app_c
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "rechnung@amazon.example.invalid", "erika@example.invalid", f"Rechnung {NR}"
    m["Message-ID"] = "<r1@example.invalid>"
    m.set_content("Ihre Rechnung im Anhang")
    m.add_attachment(PDF, maintype="application", subtype="pdf", filename="Rechnung (fiktiv).pdf")
    spiegeln(cfg, f"Rechnung {NR}", "Ihre Rechnung im Anhang", "<r1@example.invalid>", roh=m.as_bytes())
    b = buchung(c, giro, kat, -4990, f"{NR} AMZN")
    # der Anwender hat die Mail schon von Hand angehängt: sie entsteht nicht doppelt, das PDF kommt dazu
    mid = c.get("/api/mail/nachrichten").json()["eintraege"][0]["id"]
    assert c.post("/api/dokumente/aus-mail", json={"nachricht_id": mid, "buchung_ids": [b]}).status_code == 201
    lauf(c, cfg)
    assert sorted(d["mime_typ"] for d in belege(c, b)) == ["application/pdf", "message/rfc822"]


def test_mail_liste_nennt_die_buchung(app_c):
    c, cfg, giro, kat = app_c
    b = buchung(c, giro, kat, -4990, f"{NR} AMZN")
    spiegeln(cfg, f"Bestellung {NR}", "Text", "<a1@example.invalid>")
    spiegeln(cfg, "Newsletter", "nichts", "<a2@example.invalid>")
    lauf(c, cfg)
    antwort = c.get("/api/mail/nachrichten").json()
    je = {m["nachricht_id"]: m for m in antwort["eintraege"]}
    (eintrag,) = je["<a1@example.invalid>"]["angehaengt"]
    assert (eintrag["id"], eintrag["konto_id"], eintrag["nummer"]) == (b, giro, NR) and NR in eintrag["warum"]
    assert je["<a2@example.invalid>"]["angehaengt"] == []
    assert (antwort["stand"]["zugeordnet"], antwort["stand"]["keine"]) == (1, 1)
    assert [m["nachricht_id"] for m in c.get("/api/mail/nachrichten", params={"zuordnung": "zugeordnet"})
            .json()["eintraege"]] == ["<a1@example.invalid>"]


def test_aus_ohne_einstellung(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", planer_starten=False)
    c = TestClient(create_app(cfg))
    assert c.post("/api/mail/postfaecher", json={"adresse": "erika@example.invalid"}).status_code == 201
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    b = buchung(c, giro, kat, -4990, f"{NR} AMZN")
    spiegeln(cfg, f"Bestellung {NR}", "Text", "<a1@example.invalid>")
    abgleich.nach_ereignis(cfg, c.app.state.sync.jetzt())
    assert belege(c, b) == []
    assert "angehaengt" not in c.get("/api/mail/nachrichten").json()["eintraege"][0]
