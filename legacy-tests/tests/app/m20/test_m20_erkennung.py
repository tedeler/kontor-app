"""M20: Konfiguration, Erkennung von Mails, Idempotenz, Stornierung, Auslöser, Protokoll
(erwartungen.md 1, 2, 3, 4; E-216 bis E-218).

Alle Mails sind synthetisch (``tests/hilfen/m20.py``); Erwartungswerte stehen in der Definition (Beispiele 2.3,
2.4) oder werden aus den Mails im Test berechnet.
"""

from __future__ import annotations

import pytest

from generator.iban import fiktive_iban
from tests.hilfen import kontor
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import setze_zeit
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import EINS, ZWEI, abruf, benachrichtigungen, nachrichten
from tests.hilfen.m7 import betriebsdatei
from tests.hilfen.m18 import pruefe_eintraege
from tests.hilfen.m20 import (
    AMAZON, CODE, NR, PAYPAL, abgleich, alle, amazon_bestellung, amazon_erstattung, amazon_storno, app, ausgabe,
    bestand, detail, form, heute_plus, konten, liste, nachricht, paypal_rueckzahlung, paypal_zahlung,
)
from tests.hilfen.systemd import umgebungsdatei

pytestmark = pytest.mark.kern


def _eine(api) -> dict:
    (e,) = alle(api)
    return e


# ------------------------------------------------------------------ Konfiguration (1)


def test_konfiguration(tmp_path):
    K = kontor.KontorConfig()
    F = kontor.fehler().KonfigurationsFehler
    db = tmp_path / "k.db"
    c = K(datenbank=db)
    assert (c.mail_abgleich, c.mail_abgleich_frist_tage) == (False, 5)
    assert K(datenbank=db, mail_abgleich=True, mail_abgleich_frist_tage=0).mail_abgleich_frist_tage == 0
    assert K(datenbank=db, mail_abgleich_frist_tage=366).mail_abgleich_frist_tage == 366
    for falsch in (1, 0, "ja", None):
        with pytest.raises(F) as e:
            K(datenbank=db, mail_abgleich=falsch)
        assert e.value.details.get("feld") == "mail_abgleich"
    for falsch in (-1, 367, True, False, 5.0, "5", None):
        with pytest.raises(F) as e:
            K(datenbank=db, mail_abgleich_frist_tage=falsch)
        assert e.value.details.get("feld") == "mail_abgleich_frist_tage"
    env = {"KONTOR_DATENBANK": str(db)}
    assert K.from_env(env).mail_abgleich is False and K.from_env(env).mail_abgleich_frist_tage == 5
    for w, soll in (("1", True), ("ja", True), ("ON", True), ("0", False), ("nein", False), ("", False)):
        assert K.from_env({**env, "KONTOR_MAIL_ABGLEICH": w}).mail_abgleich is soll, w
    with pytest.raises(F):
        K.from_env({**env, "KONTOR_MAIL_ABGLEICH": "vielleicht"})
    for w, soll in (("0", 0), ("12", 12), ("366", 366), ("", 5)):
        assert K.from_env({**env, "KONTOR_MAIL_ABGLEICH_FRIST_TAGE": w}).mail_abgleich_frist_tage == soll, w
    for falsch in ("367", "-1", "1.5", "zehn", "١٢", "+5"):
        with pytest.raises(F) as e:
            K.from_env({**env, "KONTOR_MAIL_ABGLEICH_FRIST_TAGE": falsch})
        assert e.value.details.get("variable") == "KONTOR_MAIL_ABGLEICH_FRIST_TAGE", falsch


def test_ausgelieferte_umgebungsdatei(tmp_path):
    text = betriebsdatei("kontor.env")
    werte, _ = umgebungsdatei(text)
    # M31 (erwartungen.md 14.1, E-284): erwartete Zahlungen sind im Betrieb vorerst aus
    assert werte.get("KONTOR_MAIL_ABGLEICH") == "0"
    assert "KONTOR_MAIL_ABGLEICH_FRIST_TAGE" not in werte, "Frist nur auskommentiert"
    assert "#KONTOR_MAIL_ABGLEICH_FRIST_TAGE=5" in [z.strip() for z in text.splitlines()]
    c = kontor.KontorConfig().from_env({**werte, "KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"),
                                        "CREDENTIALS_DIRECTORY": str(tmp_path)})
    assert c.mail_abgleich is False and c.mail_abgleich_frist_tage == 5


def test_ausgeschaltet(tmp_path):
    api = app(tmp_path, [amazon_bestellung()], abgleich=False)
    a0 = letzte_aenderung_id(api)
    abruf(api)
    assert alle(api) == [] and aenderungen_seit(api, a0) == [], "ausgeschaltet: nichts erkannt"
    assert fehlercode(abgleich(api, erwartet=409)) == "mail_abgleich_aus"
    kontor.modul("kontor.sync").planer_takt(api.app)
    assert alle(api) == []
    l = liste(api)
    assert (l["aktiv"], l["eintraege"], l["anzahl"]) == (False, [], 0)
    e = api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Fiktiv", "betrag": 100},
                 erwartet=201).daten
    assert e["grund"] == "manuell", "manuelle Erwartungen funktionieren trotzdem"


# ------------------------------------------------------------------ Beispiele (2.3, 2.4, 2.5)


def test_amazon_bestellung_beispiel(tmp_path):
    m = amazon_bestellung(empfangen="2024-06-03T23:30:00Z")
    api = app(tmp_path, [m])
    setze_zeit(api, "2024-06-05T10:00:00Z")
    a0, v = letzte_aenderung_id(api), bestand(api)
    abruf(api)
    e = _eine(api)
    assert form(e) == {
        "id": e["id"], "grund": "bestellung", "richtung": "ausgabe", "anbieter": "amazon", "kennung": NR,
        "referenz": "", "haendler": "Amazon", "beschreibung": "USB-Kabel (fiktiv), Ladegerät (fiktiv)",
        "betrag": 4990, "gesamt": 5990, "guthaben": 1000, "datum": "2024-06-03", "frist": "2024-06-08",
        "zustand": "offen", "bezug_id": None, "buchung_ids": [], "dokument_ids": [],
        "mails": [{"postfach": EINS, "nachricht_id": m["nachricht_id"], "betreff": m["betreff"],
                   "empfangen": m["empfangen"]}], "erstellt_am": "2024-06-05T10:00:00Z"}
    assert (e["zugeordnet"], e["offen_betrag"], e["ueberfaellig"], e["vorzeichen_betrag"]) == (0, 4990, False, -4990)
    assert "schluessel" not in e
    d = detail(api, e["id"])
    assert d["buchungen"] == []
    (n,) = nachrichten(api)
    assert d["mail_eintraege"] == [{"postfach": EINS, "nachricht_id": m["nachricht_id"], "betreff": m["betreff"],
                                    "empfangen": m["empfangen"], "spiegel_id": n["id"]}]
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("mail", "erwartung_erkennen", None)
    pruefe_eintraege(a, v, bestand(api))


def test_paypal_zahlung_und_rueckzahlung(tmp_path):
    z = paypal_zahlung(empfangen="2024-06-01T08:00:00Z")
    r = paypal_rueckzahlung(empfangen="2024-06-04T08:00:00Z")
    api = app(tmp_path, [z, r])
    abruf(api)
    zahlung, rueck = sorted(alle(api), key=lambda e: e["datum"])
    assert {k: zahlung[k] for k in ("grund", "richtung", "anbieter", "kennung", "referenz", "haendler", "gesamt",
                                     "guthaben", "betrag", "zustand", "bezug_id")} == {
        "grund": "paypal", "richtung": "ausgabe", "anbieter": "paypal", "kennung": CODE, "referenz": "R-4711",
        "haendler": "Fiktiver Shop", "gesamt": 2500, "guthaben": 500, "betrag": 2000, "zustand": "offen",
        "bezug_id": None}
    assert {k: rueck[k] for k in ("grund", "richtung", "anbieter", "kennung", "referenz", "haendler", "gesamt",
                                   "guthaben", "betrag", "zustand", "bezug_id", "vorzeichen_betrag")} == {
        "grund": "rueckerstattung", "richtung": "eingang", "anbieter": "paypal", "kennung": "9ZZ23456CD789012E",
        "referenz": "", "haendler": "Fiktiver Shop", "gesamt": 2500, "guthaben": 0, "betrag": 2500,
        "zustand": "offen", "bezug_id": zahlung["id"], "vorzeichen_betrag": 2500}


def test_paypal_rueckzahlung_ins_guthaben(tmp_path):
    api = app(tmp_path, [paypal_rueckzahlung(guthaben=True)])
    abruf(api)
    e = _eine(api)
    assert (e["gesamt"], e["guthaben"], e["betrag"], e["zustand"], e["bezug_id"]) == (2500, 2500, 0, "guthaben", None)
    assert e["offen_betrag"] == 0


def test_amazon_erstattung_mit_bezug(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z"),
                         amazon_erstattung(empfangen="2024-06-04T08:00:00Z")])
    abruf(api)
    best, erst = sorted(alle(api), key=lambda e: e["datum"])
    assert {k: erst[k] for k in ("grund", "richtung", "anbieter", "kennung", "haendler", "gesamt", "guthaben",
                                  "betrag", "bezug_id", "referenz")} == {
        "grund": "rueckerstattung", "richtung": "eingang", "anbieter": "amazon", "kennung": NR, "haendler": "Amazon",
        "gesamt": 999, "guthaben": 0, "betrag": 999, "bezug_id": best["id"], "referenz": ""}


def test_frist_aus_konfiguration(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-03T09:00:00Z")], mail_abgleich_frist_tage=0)
    abruf(api)
    assert _eine(api)["frist"] == "2024-06-03"
    api2 = app(tmp_path, [amazon_bestellung(empfangen="2024-06-03T09:00:00Z")], name="b", mail_abgleich_frist_tage=30)
    abruf(api2)
    assert _eine(api2)["frist"] == heute_plus("2024-06-03", 30)


# ------------------------------------------------------------------ Regeln der Erkennung (2.1–2.4)


def _bestellung(text: str, absender: str = AMAZON, betreff: str = f"Ihre Bestellung {NR}") -> dict:
    return nachricht(absender, betreff, text)


@pytest.mark.parametrize("absender,erkannt", [
    (AMAZON, True), ("bestellbestaetigung@AMAZON.example.invalid", True),
    ("Versand <versand@mail.amazon.example.invalid>", True), ("shop@example.invalid", False),
    ("x@amazon-fake.example.invalid", False), ("x@notamazon.example.invalid", False),
    ("amazon@example.invalid", False), ("<x@amazon.example.invalid>", True),
])
def test_anbieter_am_absender(tmp_path, absender, erkannt):
    api = app(tmp_path, [_bestellung("Gesamtsumme: 12,00 €", absender=absender)])
    abruf(api)
    assert len(alle(api)) == (1 if erkannt else 0)


@pytest.mark.parametrize("text,gesamt,guthaben,beschreibung", [
    ("Gesamtsumme: 1.234,56 €", 123456, 0, ""),
    ("Gesamtbetrag\nEUR 12", 1200, 0, ""),
    ("Summe der Bestellung: −7,50 EUR", 750, 0, ""),
    ("Endbetrag 3,00\nGutscheine eingelöst: 1,00 €", 300, 100, ""),
    ("Bestellsumme: 20,00 €\nAmazon-Guthaben: 25,00 €", 2000, 2000, ""),
    ("2 x Buch (fiktiv) 12,00 €\nVersandkosten 3,99 €\nZwischensumme 15,99 €\nKerze: 2,00 €\nTee  4,50 EUR\n"
     "Gesamtsumme: 18,50 €", 1850, 0, "Buch (fiktiv), Kerze, Tee"),
    ("Hinweis zur Gesamtsumme ohne Betrag\nGesamtsumme: 9,00 €", 900, 0, ""),
])
def test_betraege_und_artikel(tmp_path, text, gesamt, guthaben, beschreibung):
    api = app(tmp_path, [_bestellung(text)])
    abruf(api)
    e = _eine(api)
    assert (e["gesamt"], e["guthaben"], e["betrag"], e["beschreibung"]) == (
        gesamt, guthaben, gesamt - guthaben, beschreibung)
    assert e["zustand"] == ("guthaben" if gesamt == guthaben else "offen")


@pytest.mark.parametrize("fall,mail", [
    ("ohne_bestellnummer", nachricht(AMAZON, "Ihre Bestellung", "Gesamtsumme: 12,00 €")),
    ("bestellnummer_falsch", nachricht(AMAZON, "Ihre Bestellung 302-123456-7654321", "Gesamtsumme: 12,00 €")),
    ("ohne_gesamtsumme", nachricht(AMAZON, f"Ihre Bestellung {NR}", "Artikel 12,00 €")),
    ("ganzzahl_ohne_waehrung", nachricht(AMAZON, f"Ihre Bestellung {NR}", "Gesamtsumme: 12")),
    ("gesamt_null", nachricht(AMAZON, f"Ihre Bestellung {NR}", "Gesamtsumme: 0,00 €")),
    ("betreff_ohne_art", nachricht(AMAZON, f"Ihr Paket {NR} ist unterwegs", "Gesamtsumme: 12,00 €")),
    ("erstattung_ohne_betrag", nachricht(AMAZON, "Ihre Erstattung", f"Bestellnr. {NR}\nWir erstatten bald.")),
    ("paypal_ohne_code", nachricht(PAYPAL, "Zahlung an Fiktiver Shop gesendet", "Gesendeter Betrag: 5,00 €")),
    ("paypal_code_16", nachricht(PAYPAL, "Zahlung an Fiktiver Shop gesendet",
                                 "Transaktionscode: 1AB23456CD78901\nGesendeter Betrag: 5,00 €")),
    ("paypal_code_18", nachricht(PAYPAL, "Zahlung an Fiktiver Shop gesendet",
                                 "Transaktionscode: 1AB23456CD789012EF\nGesendeter Betrag: 5,00 €")),
    ("paypal_ohne_betrag", nachricht(PAYPAL, "Zahlung an Fiktiver Shop gesendet", f"Transaktionscode: {CODE}")),
    ("paypal_betreff_ohne_art", nachricht(PAYPAL, "Ihr Konto", f"Transaktionscode: {CODE}\nBetrag: 5,00 €")),
    ("fremder_absender", nachricht("shop@example.invalid", f"Ihre Bestellung {NR}", "Gesamtsumme: 12,00 €")),
])
def test_nicht_erkannt(tmp_path, fall, mail):
    api = app(tmp_path, [mail])
    a0 = letzte_aenderung_id(api)
    abruf(api)
    assert alle(api) == [] and aenderungen_seit(api, a0) == [], fall
    assert len(nachrichten(api)) == 1, "die Mail bleibt im Spiegel"


@pytest.mark.parametrize("betreff,text,haendler,referenz", [
    ("Sie haben eine Zahlung an Fiktiver Shop gesendet", f"Transaktionscode {CODE}\nGesamt: 5,00 €", "Fiktiver Shop",
     ""),
    ("Zahlung", f"Transaktions-ID: {CODE.lower()}\nBetrag 5,00 €\nRechnungsnr. RE-2024-17", "PayPal", "RE-2024-17"),
    ("Zahlung an Buchladen (fiktiv) gesendet", f"TRANSAKTIONSNUMMER: {CODE}\nGesamtbetrag: 5,00 €\n"
     f"Ihre Bestellung {'303-7654321-1234567'}", "Buchladen (fiktiv)", "303-7654321-1234567"),
])
def test_paypal_haendler_referenz_kennung(tmp_path, betreff, text, haendler, referenz):
    api = app(tmp_path, [nachricht(PAYPAL, betreff, text)])
    abruf(api)
    e = _eine(api)
    assert (e["haendler"], e["referenz"], e["kennung"].upper(), e["betrag"]) == (haendler, referenz, CODE, 500)


# ------------------------------------------------------------------ Idempotenz, zwei Postfächer, Stornierung (2.5, 2.6)


def test_idempotenz_und_zwei_postfaecher(tmp_path):
    m = amazon_bestellung(nid="<gleich@example.invalid>")
    m2 = {**m, "postfach": ZWEI}
    weitere = amazon_bestellung(empfangen="2024-06-04T09:00:00Z")
    api = app(tmp_path, [m, m2, weitere], postfaecher=(EINS, ZWEI))
    abruf(api)
    e = _eine(api)
    # Reihenfolge der Verarbeitung (empfangen, Spiegel-ID, E-218 Nr. 3); die Spiegel-IDs der beiden gleichzeitig
    # abgerufenen Postfächer sind nicht festgelegt (parallel, mail.md 6.2) – E-245
    adressen = {p["id"]: p["adresse"].lower() for p in api.get("/api/mail/postfaecher", erwartet=200).daten}
    gespiegelt = sorted(api.get("/api/mail/nachrichten", params={"pro_seite": 500}, erwartet=200).daten["eintraege"],
                        key=lambda n: (n["empfangen"], n["id"]))
    assert [(x["postfach"], x["nachricht_id"]) for x in e["mails"]] == [
        (adressen[n["postfach_id"]], n["nachricht_id"]) for n in gespiegelt]
    assert sorted((x["postfach"], x["nachricht_id"]) for x in e["mails"]) == sorted([
        (EINS, m["nachricht_id"]), (ZWEI, m["nachricht_id"]), (EINS, weitere["nachricht_id"])])
    a0, z = letzte_aenderung_id(api), bestand(api)
    erg = abgleich(api)
    assert erg == {"neu": 0, "ergaenzt": 0, "storniert": 0, "zugeordnet": 0, "gemeldet": 0}
    abruf(api)
    assert bestand(api) == z and aenderungen_seit(api, a0) == [], "wiederholtes Abgleichen ändert nichts"


def test_erstattungen_je_betrag(tmp_path):
    api = app(tmp_path, [amazon_erstattung(betrag="5,00 €"), amazon_erstattung(betrag="5,00 €"),
                         amazon_erstattung(betrag="7,00 €")])
    abruf(api)
    assert sorted(e["betrag"] for e in alle(api)) == [500, 700]


def test_stornierung(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z"),
                         amazon_storno(empfangen="2024-06-02T08:00:00Z")])
    abruf(api)
    e = _eine(api)
    assert e["zustand"] == "storniert" and len(e["mails"]) == 2


def test_stornierung_vor_bestellung_und_nach_zuordnung(tmp_path):
    api = app(tmp_path, [amazon_storno(empfangen="2024-06-01T08:00:00Z"),
                         amazon_bestellung(empfangen="2024-06-02T08:00:00Z")])
    abruf(api)
    assert _eine(api)["zustand"] == "offen", "Stornierung ohne vorhandene Bestellung wirkt nicht"
    # zugeordnete Bestellung wird durch eine spätere Stornierung nicht geschlossen
    b = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z")], name="b", heute="2024-06-10")
    abruf(b)
    e = _eine(b)
    k = konten(b)
    bid = ausgabe(b, k, "2024-06-02", 1000, "Teil")
    b.post(f"/api/erwartungen/{e['id']}/buchungen", json={"buchung_ids": [bid]}, erwartet=200)
    datei = tmp_path / "b-mock.json"
    import json
    d = json.loads(datei.read_text(encoding="utf-8"))
    d["mail"]["nachrichten"].append(amazon_storno(empfangen="2024-06-03T08:00:00Z"))
    datei.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    abruf(b)
    assert _eine(b)["zustand"] == "offen"


# ------------------------------------------------------------------ Auslöser (4.1)


def test_ausloeser_planer_takt_prueft_fristen(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z")], heute="2024-06-05")
    abruf(api)
    e = _eine(api)
    setze_zeit(api, "2024-06-20T10:00:00Z")
    kontor.modul("kontor.sync").planer_takt(api.app)
    assert [b["schluessel"] for b in benachrichtigungen(api) if b["art"] == "erwartung_ueberfaellig"] == [
        f"erwartung_ueberfaellig:{e['id']}"], "Planer-Takt prüft Fristen auch ohne Abruf"


def test_ausloeser_nach_synchronisationslauf(tmp_path):
    """4.1: nach jedem Synchronisationslauf mit Endstatus wird abgeglichen (Definition 9: auch nach erfolgreichen
    Läufen, nicht erst im nächsten Planer-Takt)."""
    iban = fiktive_iban(7701)
    konto = {"iban": iban, "bic": None, "name": "Girokonto", "art": "girokonto", "inhaber": "Erika Fiktiv",
             "waehrung": "EUR"}
    umsatz = {"umsatz_id": "U-1", "iban": iban, "buchungstag": "2024-06-04", "valuta": "2024-06-04",
              "betrag": -4990, "waehrung": "EUR", "gegenpartei_name": "AMAZON EU S.A R.L.",
              "gegenpartei_iban": None, "verwendungszweck": f"{NR} Amazon.de", "vormerkung": False, "storno": False}
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-03T08:00:00Z")], konten=[konto], umsaetze=[umsatz],
              heute="2024-06-05")
    abruf(api)
    e = _eine(api)
    assert e["zustand"] == "offen"
    lauf = api.post("/api/sync", json={"von": "2024-06-01"}, erwartet=200).daten
    assert lauf["status"] == "erfolgreich", lauf
    e = _eine(api)
    assert e["zustand"] == "erfuellt" and len(e["buchung_ids"]) == 1, "Abgleich direkt nach dem Lauf"


def test_abgleich_rest_zaehlungen_und_rueckgaengig(tmp_path):
    """4.1: Rückgängig entfernt die erkannten Erwartungen; ein späterer Abgleich erkennt sie erneut (E-218: Zählung
    ``ergaenzt`` bei einer Stornierung nicht festgelegt)."""
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-01T08:00:00Z"),
                         amazon_storno(empfangen="2024-06-02T08:00:00Z"),
                         paypal_zahlung(empfangen="2024-06-02T09:00:00Z"),
                         paypal_zahlung(empfangen="2024-06-02T10:00:00Z")])
    v, a0 = bestand(api), letzte_aenderung_id(api)
    abruf(api)
    n = bestand(api)
    (a,) = aenderungen_seit(api, a0)
    assert sorted(e["zustand"] for e in alle(api)) == ["offen", "storniert"]
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == v and alle(api) == []
    erg = abgleich(api)
    assert (erg["neu"], erg["storniert"], erg["zugeordnet"], erg["gemeldet"]) == (2, 1, 0, 0), erg
    assert erg["ergaenzt"] in (1, 2), erg
    nach = bestand(api)
    assert {k[0] for k in nach} == {k[0] for k in n} and len(alle(api)) == 2
    assert sorted(form(e)["kennung"] for e in alle(api)) == sorted([NR, CODE])
