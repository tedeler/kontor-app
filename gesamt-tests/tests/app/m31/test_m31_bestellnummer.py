"""M31: Mails über die Amazon-Bestellnummer an der Buchung (erwartungen.md 14; E-283) – REST, kern.

Mails aus einer Mock-Datendatei je Test (ohne Rohfassung), Buchungen über REST oder den Mock-Bank-Lauf; der
Echtmodus mit HTML-Teil und PDF-Anhang über die IMAP-Attrappe. Welche Mail an welche Buchung gehört, rechnet
der Test über ``m31.nummern`` selbst aus.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen.api import Api, neue_config
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m2 import mock_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id, rueckgaengig
from tests.hilfen.m4 import umsatz
from tests.hilfen.m6 import CLIENT_ID, CLIENT_SECRET, EINS, REDIRECT, ZWEI, abruf, nachrichten
from tests.hilfen.m9 import einspielen, sicherung
from tests.hilfen.m18 import MAIL, PDF, dokumente_der_buchung, echt_mit_imap, imap_postfaecher, inhalt, mail, pdf, \
    pruefe_eintraege, rundreise
from tests.hilfen.m20 import AMAZON, NR, app, ausgabe, bestand, konten, mock_datei, nachricht
from tests.hilfen.m31 import NUMMER, nummern
from tests.hilfen.oauth_attrappe import OAuthAttrappe

pytestmark = pytest.mark.kern
NR2 = "305-7654321-1234567"
AKTION = ("mail", "bestellmail_anhaengen")
IBAN = "DE02000000000000004712"


def _mails_der_buchung(api, bid) -> list[dict]:
    return [d for d in dokumente_der_buchung(api, bid) if d["mime_typ"] == MAIL]


def _betreffe(api, bid) -> list[str]:
    return sorted(api.get(f"/api/dokumente/{d['id']}/mail", erwartet=200).daten["betreff"]
                  for d in _mails_der_buchung(api, bid))


def _bestell_aenderungen(api, a0):
    return [a for a in aenderungen_seit(api, a0) if (a["quelle"], a["aktion"]) == AKTION]


def _mail_nummern(m: dict) -> set[str]:
    return set(NUMMER.findall(m["betreff"])) | set(NUMMER.findall(m["text"]))


def _soll(mails: list[dict], buchungen: dict[int, tuple[str, str | None]]) -> dict[int, list[str]]:
    """Buchung → Betreffe der zugehörigen Mails (14.2), Mails nach Nachrichten-ID einmal."""
    aus = {}
    for bid, (zweck, empf) in buchungen.items():
        n = nummern(zweck) | nummern(empf)
        aus[bid] = sorted({m["nachricht_id"]: m["betreff"] for m in mails if _mail_nummern(m) & n}.values())
    return aus


MAILS = [
    nachricht(AMAZON, f"Bestellung {NR} versandt", "Ihre Sendung ist unterwegs.", "2024-06-03T08:00:00Z"),
    nachricht("Paketdienst <info@paket.example.invalid>", "Zustellung heute",
              f"Ihre Sendung zur Bestellung {NR} kommt heute.", "2024-06-04T08:00:00Z"),
    nachricht(AMAZON, f"Bestellung {NR2} bestätigt", "Danke.", "2024-06-04T09:00:00Z"),
    nachricht(AMAZON, "Ähnliche Nummer", f"Kundennummer 1{NR}", "2024-06-04T10:00:00Z"),
    nachricht("Newsletter <news@example.invalid>", "Angebote", "Keine Nummer hier.", "2024-06-04T11:00:00Z"),
]


def _bestand_mit_buchungen(api) -> tuple[dict, dict[int, tuple[str, str | None]]]:
    k = konten(api)
    b = {}
    for zweck, empf in ((f"AMAZON PAYMENTS {NR}", None), ("Kartenzahlung", f"AMZN Mktp {NR}"),
                        (f"Lastschrift {NR[:12]} {NR[12:]}", None), (f"Ref 9{NR2}0", None), ("Supermarkt", None)):
        bid = ausgabe(api, k, "2024-06-02", 1999, zweck, empf)
        b[bid] = (zweck, empf)
    return k, b


def test_vorgabe_aus(tmp_path):
    api = app(tmp_path, MAILS, abgleich=False)
    _, b = _bestand_mit_buchungen(api)
    a0 = letzte_aenderung_id(api)
    abruf(api)
    assert _bestell_aenderungen(api, a0) == [] and all(dokumente_der_buchung(api, x) == [] for x in b)
    assert all("angehaengt" not in m for m in nachrichten(api)), "ohne Einstellung fehlt das Feld"


def test_treffer_protokoll_und_rundreise(tmp_path):
    api = app(tmp_path, MAILS, abgleich=False, mail_bestellnummer=True)
    _, b = _bestand_mit_buchungen(api)
    soll = _soll(MAILS, b)
    assert sum(1 for x in soll.values() if x) == 3, "Voraussetzung: drei Buchungen mit Treffern"
    v, a0 = bestand(api), letzte_aenderung_id(api)
    abruf(api)
    n = bestand(api)
    (a,) = _bestell_aenderungen(api, a0)
    assert [x for x in aenderungen_seit(api, a0) if x["quelle"] != "mail" or x["aktion"] != AKTION[1]] == []
    pruefe_eintraege(a, v, n)
    for bid in b:
        assert _betreffe(api, bid) == soll[bid], f"Buchung {b[bid]}"
        assert {d["quelle"] for d in dokumente_der_buchung(api, bid)} <= {"mail"}
        assert len(dokumente_der_buchung(api, bid)) == len(soll[bid]), "Mock-Mails haben keine Anhänge"
    rundreise(api, a, v, n, zustand_fn=bestand)
    a1 = letzte_aenderung_id(api)
    abruf(api)
    assert aenderungen_seit(api, a1) == [], "zweiter Abruf ohne Änderung"
    assert bestand(api) == n


def test_teillieferungen_und_zwei_postfaecher(tmp_path):
    gleich = [nachricht(AMAZON, f"Bestellung {NR} versandt", "Teil 1 und 2", "2024-06-03T08:00:00Z",
                        postfach=p, nid="<synth-bestell@example.invalid>") for p in (EINS, ZWEI)]
    api = app(tmp_path, gleich, abgleich=False, postfaecher=(EINS, ZWEI), mail_bestellnummer=True)
    k = konten(api)
    teile = [ausgabe(api, k, d, 1000, f"Amazon {NR}") for d in ("2024-06-02", "2024-06-04")]
    abruf(api)
    for bid in teile:
        assert len(_mails_der_buchung(api, bid)) == 1, "jede Teillieferung genau einmal, zwei Postfächer einmal"


def test_rueckgaengig_und_loesen_kommen_nicht_wieder(tmp_path):
    api = app(tmp_path, MAILS, abgleich=False, mail_bestellnummer=True)
    k = konten(api)
    eins = ausgabe(api, k, "2024-06-02", 1999, f"Amazon {NR}")
    a0 = letzte_aenderung_id(api)
    abruf(api)
    (a,) = _bestell_aenderungen(api, a0)
    assert len(_mails_der_buchung(api, eins)) == 2
    rueckgaengig(api, a["id"])
    assert dokumente_der_buchung(api, eins) == []
    a1 = letzte_aenderung_id(api)
    abruf(api)
    assert aenderungen_seit(api, a1) == [] and dokumente_der_buchung(api, eins) == [], "gemerkt: kommt nicht wieder"
    zwei = ausgabe(api, k, "2024-06-05", 500, f"Amazon {NR}")
    abruf(api)
    docs = _mails_der_buchung(api, zwei)
    assert len(docs) == 2, "eine neue Buchung bekommt die Mails"
    api.delete(f"/api/dokumente/{docs[0]['id']}", erwartet=204)
    a2 = letzte_aenderung_id(api)
    abruf(api)
    assert aenderungen_seit(api, a2) == [] and len(_mails_der_buchung(api, zwei)) == 1, "gelöstes bleibt weg"


def test_nach_dem_einspielen_neu_geprueft(tmp_path):
    api = app(tmp_path, MAILS, abgleich=False, mail_bestellnummer=True)
    k = konten(api)
    bid = ausgabe(api, k, "2024-06-02", 1999, f"Amazon {NR}")
    a0 = letzte_aenderung_id(api)
    abruf(api)
    (a,) = _bestell_aenderungen(api, a0)
    rueckgaengig(api, a["id"])
    s = sicherung(api)
    api.tag("Nach der Sicherung")
    einspielen(api, s)
    abruf(api)
    assert len(_mails_der_buchung(api, bid)) == 2, "das Gemerkte ist nach dem Einspielen geleert"


def test_kein_zweites_dokument_gleichen_inhalts(tmp_path):
    datei = mock_datei(tmp_path / "mock.json", [MAILS[0]])
    erst = mock_api(tmp_path / "db", daten=datei, heute="2024-06-05", mail_erstabruf_tage=365)
    erst.post("/api/mail/postfaecher", json={"adresse": EINS}, erwartet=201)
    k = konten(erst)
    bid = ausgabe(erst, k, "2024-06-02", 1999, f"Amazon {NR}")
    abruf(erst)
    (m,) = nachrichten(erst)
    erst.post("/api/dokumente/aus-mail", json={"nachricht_id": m["id"], "buchung_ids": [bid]}, erwartet=201)
    dann = Api(neue_config(tmp_path / "db", mock_modus=True, mock_daten=datei, mock_szenario="normal",
                           mock_heute=dt.date(2024, 6, 5), mail_erstabruf_tage=365, mail_bestellnummer=True))
    a0 = letzte_aenderung_id(dann)
    abruf(dann)
    assert len(_mails_der_buchung(dann, bid)) == 1 and _bestell_aenderungen(dann, a0) == []


def test_nach_der_synchronisation(tmp_path):
    konto = {"iban": IBAN, "bic": None, "name": "Girokonto", "art": "girokonto", "inhaber": "Erika Mustermann (fiktiv)",
             "waehrung": "EUR"}
    api = app(tmp_path, MAILS[:2], abgleich=False, mail_bestellnummer=True, konten=[konto],
              umsaetze=[umsatz("U-1", IBAN, "2024-06-03", -2999, "AMAZON PAYMENTS", f"Bestellung {NR}")])
    abruf(api)
    a0 = letzte_aenderung_id(api)
    lauf = api.post("/api/sync", json={}, erwartet=200).daten
    assert lauf["status"] == "erfolgreich", lauf
    (b,) = [x for x in api.alle_buchungen() if NR in x["verwendungszweck"]]
    assert len(_mails_der_buchung(api, b["id"])) == 2
    assert len(_bestell_aenderungen(api, a0)) == 1


def test_mail_liste_angehaengt_stand_und_filter(tmp_path):
    api = app(tmp_path, MAILS, abgleich=False, mail_bestellnummer=True)
    k, b = _bestand_mit_buchungen(api)
    abruf(api)
    soll = _soll(MAILS, b)
    alle = nachrichten(api)
    zugeordnet = set()
    for m in alle:
        assert "angehaengt" in m, "mit Einstellung trägt jeder Eintrag das Feld"
        erwartet = sorted(bid for bid, betreffe in soll.items() if m["betreff"] in betreffe)
        assert sorted(x["id"] for x in m["angehaengt"]) == erwartet, m["betreff"]
        for x in m["angehaengt"]:
            zweck, empf = b[x["id"]]
            assert (x["datum"], x["konto_id"], x["verwendungszweck"]) == ("2024-06-02", k["giro"], zweck)
            assert x["empfaenger"] == empf and x["nummer"] == NR and x["warum"]
            # ab M32 (sammel3.md 8.3, E-307): Betrag = Summe der Splits auf Bestandskonten
            bestand = {kk["id"] for kk in api.konten() if kk["art"] in ("girokonto", "sparkonto", "kreditkonto")}
            assert x["betrag"] == sum(s_["betrag"] for s_ in api.buchung_lesen(x["id"])["splits"]
                                      if s_["konto_id"] in bestand)
        if erwartet:
            zugeordnet.add(m["id"])
    assert len(zugeordnet) == 2
    seite = api.get("/api/mail/nachrichten", erwartet=200).daten
    assert seite["stand"]["zugeordnet"] == 2 and seite["stand"]["gesamt"] == len(MAILS)
    assert {m["id"] for m in nachrichten(api, zuordnung="zugeordnet")} == zugeordnet
    assert not zugeordnet & {m["id"] for m in nachrichten(api, zuordnung="keine")}


def test_echtmodus_html_verweis_und_pdf(tmp_path, netz_nur_loopback):
    """D-209: die Nummer steht nur im HTML-Teil (Verweisadresse); Mail und PDF-Anhang werden Dokumente."""
    roh = mail(betreff="Ihre Bestellung wurde versandt", von=AMAZON, text="Hallo,\nIhre Sendung ist unterwegs.\n",
               html=('<p>Hallo,</p><p><a href="https://www.amazon.example.invalid/gp/css/order-details?'
                     f'orderID={NR}">Bestellung ansehen</a></p>'),
               anhaenge=[("rechnung.pdf", PDF, pdf("Rechnung"))])
    o = OAuthAttrappe(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT).starte()
    i = ImapAttrappe(pruefe_token=o.access_gueltig, postfaecher=imap_postfaecher(EINS, [
        (dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(days=2), roh)])).starte()
    try:
        api, _ = echt_mit_imap(tmp_path, i, o, EINS, mail_bestellnummer=True)
        k = konten(api)
        bid = ausgabe(api, k, dt.date.today().isoformat(), 5990, f"AMAZON {NR}")
        a0 = letzte_aenderung_id(api)
        abruf(api)
        assert len(_bestell_aenderungen(api, a0)) == 1
        docs = dokumente_der_buchung(api, bid)
        assert sorted(d["mime_typ"] for d in docs) == sorted([MAIL, PDF]) and {d["quelle"] for d in docs} == {"mail"}
        assert inhalt(api, next(d for d in docs if d["mime_typ"] == MAIL)["id"]).content == roh
        assert inhalt(api, next(d for d in docs if d["mime_typ"] == PDF)["id"]).content == pdf("Rechnung")
    finally:
        i.stoppe()
        o.stoppe()
