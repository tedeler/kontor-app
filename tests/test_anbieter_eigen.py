"""D-230: Anbieter-Beschreibungen. Kern ist der Vergleich mit der eingefrorenen Erkennung von vor dem Umbau
(``referenz_mailerkennung.py``): Die Beschreibungen für Amazon und PayPal müssen jede Mail genauso lesen."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from kontor import anbieter, mailerkennung
from kontor.plugins.mock_mail import MockMailPlugin

from . import referenz_mailerkennung as alt

NR = st.sampled_from(["302-1234567-7654321", "028-0000001-0000002", "304-3102446-2863546", "12-1234567-1234567"])
CODE = st.sampled_from(["9AB12345CD678901E", "1234567890ABCDEFG", "9ab12345cd678901e", "9AB12345CD67890"])
BETRAG = st.sampled_from(["12,34 €", "1.234,56 €", "EUR 9,99", "€ 0,50", "45", "45 €", "-3,00 €", "1234,5", "",
                          "7,00", "10,00 EUR", "–12,00 €", "0,00 €", "999.999,99 €"])
WORT = st.sampled_from(["Fiktiver Shop", "Buchhandlung Seitenweise", "„Laden“", "Müller & Söhne", "X", "", "amazon",
                        "PayPal", "Ladekabel USB-C", "2 x Tee", "Versand", "Zwischensumme"])

ABSENDER = st.sampled_from([
    "bestellbestaetigung@amazon.de", "Amazon.de <versand@amazon.de>", "rueckgabe@amazon.example.invalid",
    "x@mail.amazon.co.uk", "service@paypal.de", "PayPal <service@paypal.example.invalid>", "info@paypal.com",
    "a@notamazon.de", "a@amazon", "a@paypal-kunden.de", "a@shop.example.invalid", "", "amazon.de", "a@AMAZON.DE>",
    "x@paypal.amazon.de", "x@amazon.paypal.de"])

BETREFF_TEIL = st.sampled_from([
    "Ihre Amazon.de Bestellung", "Bestellbestätigung", "BESTELLUNG", "Bestätigung", "wurde storniert", "Stornierung",
    "STORNIERT", "Ihre Erstattung", "Erstattung für", "ERSTATTUNG", "Sie haben eine Zahlung an", "gesendet",
    "Zahlung", "ZAHLUNG AN", "Rückzahlung von", "Rückzahlung durch", "erhalten", "Erstattung von", "rückzahlung",
    "Versandbestätigung", "Newsletter", "Nr.", "von", "an", "Zahlung an"])

ZEILE_MARKE = st.sampled_from([
    "Gesamtsumme", "Gesamtbetrag", "Endbetrag", "Summe der Bestellung", "Bestellsumme", "Geschenkgutschein",
    "Gutschein eingelöst", "Gutscheine", "Amazon-Guthaben", "Guthaben", "Erstattungsbetrag", "Gesamterstattung",
    "Erstatteter Betrag", "Erstattung", "Rückzahlungsbetrag", "Betrag der Rückzahlung", "Gesamt", "Betrag",
    "Gesendeter Betrag", "PayPal-Guthaben", "PayPal Guthaben", "PAYPAL-GUTHABEN", "Bezahlt mit", "Zwischensumme",
    "Versand", "gesamtsumme", "Bestellnr.", "Bestellnummer", "Rechnungsnr", "Rechnungsnummer", "Transaktionscode",
    "Transaktionsnummer", "Transaktions-ID", "Ursprünglicher Transaktionscode", "Original-Transaktions-ID",
    "transaktionscode"])
TRENNER = st.sampled_from([": ", " ", ":", "\t", " – ", ""])


@st.composite
def zeile(draw):
    art = draw(st.integers(0, 9))
    if art <= 3:
        return draw(ZEILE_MARKE) + draw(TRENNER) + draw(st.one_of(BETRAG, NR, CODE, WORT))
    if art == 4:
        return draw(ZEILE_MARKE)
    if art == 5:
        return draw(BETRAG)
    if art == 6:
        return draw(WORT) + " " + draw(BETRAG)
    if art == 7:
        return draw(st.sampled_from([
            "Der Betrag wurde gutgeschrieben auf Ihr PayPal-Guthaben", "Betrag überwiesen an PayPal Guthaben",
            "Bezahlt mit PayPal-Guthaben 5,00 € und Bankkonto 7,21 €", "PayPal-Guthaben 1,00 € PayPal-Guthaben 2,00 €",
            "gutgeschrieben auf PayPal-Guthaben", "Hallo Erika,", "  ", "Vielen Dank für Ihre Bestellung."]))
    if art == 8:
        return draw(ZEILE_MARKE) + draw(TRENNER) + draw(ZEILE_MARKE) + draw(TRENNER) + draw(BETRAG)
    return draw(st.one_of(NR, CODE)) + " " + draw(WORT)


@st.composite
def mail(draw):
    betreff = " ".join(draw(st.lists(st.one_of(BETREFF_TEIL, WORT, NR), min_size=0, max_size=4)))
    text = draw(st.sampled_from(["\n", "\r\n"])).join(draw(st.lists(zeile(), min_size=0, max_size=9)))
    return draw(ABSENDER), betreff, text


@st.composite
def gezielt(draw):
    """Plausible Mail eines Anbieters: passender Absender, Betreff aus dem Wortschatz der Mailarten, Kennung meist
    vorhanden, dazu zufällige Zeilen – damit jede Mailart oft genug getroffen wird."""
    paypal = draw(st.booleans())
    absender = draw(st.sampled_from(["service@paypal.de", "PayPal <service@paypal.example.invalid>"] if paypal else
                                    ["bestellbestaetigung@amazon.de", "rueckgabe@amazon.example.invalid"]))
    betreff = draw(st.sampled_from(
        ["Rückzahlung von Fiktiver Shop erhalten", "Erstattung durch „Laden“", "Rückzahlung", "ERSTATTUNG VON X ERHALTEN",
         "Sie haben eine Zahlung an Fiktiver Shop gesendet", "Zahlung an »Laden«", "Zahlung", "Zahlung und Rückzahlung"]
        if paypal else
        ["Ihre Amazon.de Bestellung", "Bestellbestätigung 302-1234567-7654321", "Ihre Bestellung wurde storniert",
         "Ihre Erstattung", "Erstattung zur Bestellung", "Stornierung und Erstattung", "Versand Ihrer Sendung"]))
    kennung = draw(st.sampled_from(
        ["Transaktionscode: 9AB12345CD678901E", "Transaktions-ID 1234567890ABCDEFG", "transaktionsnummer:9AB12345CD678901E", ""]
        if paypal else ["Bestellnr. 302-1234567-7654321", "302-1234567-7654321", ""]))
    zeilen = draw(st.lists(zeile(), min_size=0, max_size=8))
    zeilen.insert(draw(st.integers(0, len(zeilen))), kennung)
    return absender, betreff, "\n".join(zeilen)


MAIL = st.one_of(mail(), gezielt())


def _gleich(absender, betreff, text):
    soll = alt.erkennen(absender, betreff, text)
    ist = mailerkennung.erkennen(absender, betreff, text)
    assert (None if soll is None else dataclasses.asdict(soll)) == (None if ist is None else dataclasses.asdict(ist)), \
        (absender, betreff, text)
    return ist


@settings(max_examples=6000, deadline=None, suppress_health_check=list(HealthCheck))
@given(MAIL)
def test_beschreibungen_lesen_wie_die_bisherige_erkennung(m):
    _gleich(*m)


def test_zufallsmails_treffen_alle_mailarten():
    """Der Vergleich oben wäre wertlos, wenn die Zufallsmails nie erkannt würden."""
    gesehen = set()

    @settings(max_examples=4000, deadline=None, suppress_health_check=list(HealthCheck), database=None)
    @given(MAIL)
    def lauf(m):
        e = mailerkennung.erkennen(*m)
        if e is not None:
            gesehen.add((e.anbieter, e.art, e.guthaben > 0, e.bezug is not None, bool(e.artikel)))

    lauf()
    arten = {(a, b) for a, b, *_ in gesehen}
    assert arten == {("amazon", "storno"), ("amazon", "erstattung"), ("amazon", "bestellung"),
                     ("paypal", "zahlung"), ("paypal", "erstattung")}, arten
    assert any(g for _, _, g, _, _ in gesehen) and any(b for _, _, _, b, _ in gesehen)
    assert any(x for _, _, _, _, x in gesehen)


def test_eingebaute_mock_mails_gleich():
    plugin = MockMailPlugin()
    plugin.setze_heute(dt.date(2024, 6, 30))
    anzahl = erkannt = 0
    for postfach in plugin.postfaecher():
        for n in plugin.nachrichten(postfach, dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)):
            anzahl += 1
            erkannt += _gleich(n.absender, n.betreff, n.text) is not None
    assert anzahl >= 5 and erkannt >= 3


@pytest.mark.parametrize("absender, betreff, text", [
    ("bestellbestaetigung@amazon.de", "Ihre Amazon.de Bestellung 302-1234567-7654321",
     "Ladekabel USB-C 12,99 €\n2 x Tee 6,00 €\nVersand 0,00 €\nGesamtsumme: 18,99 €\nGutschein eingelöst\n5,00 €"),
    ("bestellbestaetigung@amazon.de", "IHRE BESTELLUNG WURDE STORNIERT", "Bestellnr. 302-1234567-7654321"),
    ("rueckgabe@amazon.de", "Ihre Erstattung", "Bestellnr. 302-1234567-7654321\nErstattungsbetrag: 9,99 €"),
    ("rueckgabe@amazon.de", "Ihre Erstattung", "Bestellnr. 302-1234567-7654321\nohne Betrag"),
    ("service@paypal.de", "Sie haben eine Zahlung an „Fiktiver Shop“ gesendet",
     "Transaktionscode: 9AB12345CD678901E\nGesendeter Betrag 1.234,56 €\nBezahlt mit PayPal-Guthaben 34,56 €\n"
     "Rechnungsnummer: R-2024-17"),
    ("service@paypal.de", "Zahlung an Laden", "Transaktionscode 9AB12345CD678901E\nBetrag\n12,00 EUR\n"
     "Bestellung 302-1234567-7654321"),
    ("service@paypal.de", "Rückzahlung von Fiktiver Shop erhalten",
     "Transaktionscode: 1234567890ABCDEFG\nRückzahlungsbetrag: 20,00 €\n"
     "Ursprünglicher Transaktionscode: 9AB12345CD678901E\nDer Betrag wurde gutgeschrieben auf Ihr PayPal-Guthaben."),
    ("service@paypal.de", "Erstattung", "Transaktions-ID: 1234567890ABCDEFG\nGesamt 3,00 €"),
    ("service@paypal.de", "Newsletter", "Transaktionscode: 1234567890ABCDEFG\nBetrag 3,00 €"),
    ("x@shop.example.invalid", "Ihre Bestellung 302-1234567-7654321", "Gesamtsumme 5,00 €"),
])
def test_beispiele_gleich(absender, betreff, text):
    _gleich(absender, betreff, text)


# ---------------------------------------------------------------- Beschreibungen prüfen und zuladen

MINI = '''
name = "kaufhaus"
titel = "Kaufhaus Muster"
absender = '(^|\\.)kaufhaus\\.example\\.invalid$'
[kennung]
muster = 'Auftrag\\s+(K\\d{6})'
suche_in = ["betreff", "text"]
[[art]]
name = "bestellung"
rolle = "ausgabe"
grund = "bestellung"
betreff = '(?i)auftragsbestätigung'
gesamt = { betrag_nach = '(?i)zu zahlen' }
[bank]
namen = ["kaufhaus muster"]
kennung = '(?<![A-Z0-9])K\\d{6}(?!\\d)'
'''


def test_zusatzdatei_wird_geladen_und_fehlerhafte_uebergangen(tmp_path, caplog):
    (tmp_path / "kaufhaus.toml").write_text(MINI, encoding="utf-8")
    (tmp_path / "kaputt.toml").write_text(MINI.replace("K\\d{6})'", "K\\d{6}'", 1).replace("kaufhaus", "kaputt"),
                                          encoding="utf-8")
    alle = anbieter.alle(tmp_path)
    assert [a.name for a in alle] == ["amazon", "paypal", "kaufhaus"]
    assert "kaputt.toml" in caplog.text and "kennung.muster" in caplog.text
    e = anbieter.erkennen("shop@kaufhaus.example.invalid", "Auftragsbestätigung", "Auftrag K123456\nZu zahlen: 49,90 €",
                          alle)
    assert (e.anbieter, e.art, e.kennung, e.haendler, e.gesamt) == ("kaufhaus", "bestellung", "K123456",
                                                                    "Kaufhaus Muster", 4990)
    assert anbieter.erkennen("shop@kaufhaus.example.invalid", "Auftragsbestätigung", "Auftrag K123456") is None
    assert alle[2].kennungen("SEPA K123456 KAUFHAUS", "nichts") == ["K123456"]


@pytest.mark.parametrize("aenderung, meldung", [
    (("rolle = \"ausgabe\"", "rolle = \"kauf\""), "rolle"),
    (("grund = \"bestellung\"\n", ""), "grund"),
    (("gesamt = { betrag_nach = '(?i)zu zahlen' }", "gesamt = { text = '(x)' }"), "Betrag"),
    (("'(?i)auftragsbestätigung'", "'('"), "ungültig"),
    (("titel = \"Kaufhaus Muster\"", "titel = \"Kaufhaus Muster\"\nfarbe = \"rot\""), "Unbekannte Angabe"),
    (("namen = [\"kaufhaus muster\"]", "namen = [\"k\"]"), "bank.namen"),
])
def test_fehlerhafte_beschreibung_nennt_die_stelle(aenderung, meldung):
    with pytest.raises(anbieter.BeschreibungsFehler, match=meldung):
        anbieter.aus_toml(MINI.replace(*aenderung))


# ---------------------------------------------------------------- im Zusammenspiel mit Abgleich und Buchungen

def _app(tmp_path, **cfg):
    from fastapi.testclient import TestClient

    from kontor.app import create_app
    from kontor.config import KontorConfig
    config = KontorConfig(datenbank=tmp_path / "k.sqlite3", planer_starten=False, **cfg)
    c = TestClient(create_app(config))
    assert c.post("/api/mail/postfaecher", json={"adresse": "erika@example.invalid"}).status_code == 201
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Einkauf", "art": "aufwand"}).json()["id"]
    return c, config, giro, kat


def _mail(config, nid, absender, betreff, text):
    from kontor import db
    con = db.verbinde(config.aktive_datenbank)
    try:
        with db.transaktion(con):
            con.execute("INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text)"
                        " VALUES ('erika@example.invalid', ?, '2024-03-01T10:00:00Z', ?, ?, ?)",
                        (nid, absender, betreff, text))
    finally:
        con.close()


def _buchung(c, giro, kat, betrag, zweck):
    r = c.post("/api/buchungen", json={"datum": "2024-03-03", "verwendungszweck": zweck, "splits": [
        {"konto_id": giro, "betrag": betrag}, {"konto_id": kat, "betrag": -betrag}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_paypal_code_im_verwendungszweck_haengt_die_mail_an(tmp_path):
    from kontor import abgleich
    c, config, giro, kat = _app(tmp_path, mail_bestellnummer=True)
    code = "9AB12345CD678901E"
    _mail(config, "<pp-1@example.invalid>", "service@paypal.example.invalid", "Sie haben eine Zahlung an Laden gesendet",
          f"Transaktionscode: {code}\nGesendeter Betrag 12,00 €")
    # dieselbe Zeichenfolge in einer fremden Mail zählt für PayPal nicht (alle_mails ist dort aus)
    _mail(config, "<fremd-1@example.invalid>", "news@shop.example.invalid", "Angebot", f"Gutscheincode {code}")
    mit = _buchung(c, giro, kat, -1200, f"PP.1234.PP . LADEN, Ihr Einkauf bei LADEN {code}")
    ohne = _buchung(c, giro, kat, -1200, "PP.1234.PP . LADEN, Ihr Einkauf bei LADEN")
    abgleich.nach_ereignis(config, c.app.state.sync.jetzt())
    belege = c.get(f"/api/buchungen/{mit}").json()["belege"]
    assert len(belege) == 1 and belege[0]["mime_typ"] == "message/rfc822"
    assert c.get(f"/api/buchungen/{ohne}").json()["belege"] == []
    mails = c.get("/api/mail/nachrichten").json()["eintraege"]
    haengt = {m["nachricht_id"]: m["angehaengt"] for m in mails}
    assert [b["id"] for b in haengt["<pp-1@example.invalid>"]] == [mit] and haengt["<fremd-1@example.invalid>"] == []


def test_zugeladener_anbieter_von_der_mail_bis_zur_buchung(tmp_path):
    from kontor import abgleich
    ordner = tmp_path / "anbieter"
    ordner.mkdir()
    (ordner / "kaufhaus.toml").write_text(MINI, encoding="utf-8")
    c, config, giro, kat = _app(tmp_path, mail_abgleich=True, mail_bestellnummer=True, anbieter_verzeichnis=ordner)
    _mail(config, "<kh-1@example.invalid>", "shop@kaufhaus.example.invalid", "Auftragsbestätigung",
          "Auftrag K123456\nZu zahlen: 49,90 €")
    _mail(config, "<kh-2@example.invalid>", "shop@kaufhaus.example.invalid", "Auftragsbestätigung",
          "Auftrag K654321\nZu zahlen: 10,00 €")
    abgleich.nach_ereignis(config, c.app.state.sync.jetzt())
    erwartet = {e["kennung"]: e for e in c.get("/api/erwartungen").json()["eintraege"]}
    assert erwartet["K123456"]["haendler"] == "Kaufhaus Muster" and erwartet["K123456"]["betrag"] == 4990
    assert erwartet["K123456"]["grund"] == "bestellung" and erwartet["K123456"]["zustand"] == "offen"
    # Kennung im Verwendungszweck → zugeordnet; Betrag und Name aus bank.namen → ebenfalls
    b1 = _buchung(c, giro, kat, -4990, "LASTSCHRIFT K123456")
    b2 = _buchung(c, giro, kat, -1000, "Kaufhaus Muster GmbH sagt Danke")
    abgleich.nach_ereignis(config, c.app.state.sync.jetzt())
    nach = {e["kennung"]: e for e in c.get("/api/erwartungen", params={"zustand": "erfuellt"}).json()["eintraege"]}
    assert nach["K123456"]["zustand"] == "erfuellt" and nach["K123456"]["buchung_ids"] == [b1]
    assert nach["K654321"]["zustand"] == "erfuellt" and nach["K654321"]["buchung_ids"] == [b2]
    assert len(c.get(f"/api/buchungen/{b1}").json()["belege"]) == 1


def test_migration_gibt_den_anbieter_frei(tmp_path):
    """Schemaversion 15: eine Datenbank mit der alten Einschränkung (nur amazon/paypal) behält Inhalt und Zähler."""
    from kontor import db
    pfad = tmp_path / "k.sqlite3"
    db.schema_anlegen(pfad)
    con = db.verbinde(pfad)
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name = 'erwartung'").fetchone()["sql"]
    alt = sql.replace("(anbieter GLOB '[a-z]*' AND length(anbieter) <= 30)", "anbieter IN ('amazon','paypal')")
    assert alt != sql
    con.execute("DROP TABLE erwartung")
    con.execute(alt)
    for i, name in enumerate(("amazon", "paypal", None)):
        con.execute("INSERT INTO erwartung (grund, richtung, anbieter, schluessel, haendler, betrag, gesamt, guthaben,"
                    " datum, frist, zustand, erstellt_am) VALUES ('bestellung', 'ausgabe', ?, ?, 'H', 1, 1, 0,"
                    " '2024-01-01', '2024-01-15', 'offen', '2024-01-01T00:00:00Z')", (name, f"s{i}"))
    con.execute("DELETE FROM erwartung WHERE schluessel = 's2'")
    con.close()
    db.schema_anlegen(pfad)
    con = db.verbinde(pfad)
    assert [tuple(r) for r in con.execute("SELECT id, anbieter FROM erwartung ORDER BY id")] == [(1, "amazon"), (2, "paypal")]
    neu = con.execute("INSERT INTO erwartung (grund, richtung, anbieter, haendler, betrag, gesamt, guthaben, datum, frist,"
                      " zustand, erstellt_am) VALUES ('bestellung', 'ausgabe', 'kaufhaus', 'H', 1, 1, 0, '2024-01-01',"
                      " '2024-01-15', 'offen', '2024-01-01T00:00:00Z')").lastrowid
    assert neu == 4   # der Zähler der gelöschten Zeile bleibt verbraucht
    con.close()
