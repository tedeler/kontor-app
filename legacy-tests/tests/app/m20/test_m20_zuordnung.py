"""M20: Kandidaten, automatische und manuelle Zuordnung, Teilzahlung, Dokumente, Lösen, verwaiste Bezüge
(erwartungen.md 5, 6.4; E-218).

Buchungen werden über REST angelegt; Kandidaten und Zuordnungen werden aus den Regeln 5.1/5.2 im Test bestimmt.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import CLIENT_ID, CLIENT_SECRET, EINS, REDIRECT, ZWEI, abruf
from tests.hilfen.m18 import MAIL, PDF, belege, dokument, mail, operation, pdf, pruefe_eintraege, rundreise
from tests.hilfen.m20 import (
    CODE, NR, abgleich, alle, amazon_bestellung, app, ausgabe, bestand, detail, eingang, konten, paypal_zahlung,
)
from tests.hilfen.m18 import echt_mit_imap, imap_postfaecher
from tests.hilfen.oauth_attrappe import OAuthAttrappe

pytestmark = pytest.mark.kern


def _op(api, aktion, aufruf):
    return operation(api, aktion, aufruf, zustand_fn=bestand)


def _ohne(api, aufruf):
    from tests.hilfen.m18 import ohne_wirkung
    ohne_wirkung(api, aufruf, zustand_fn=bestand)


def _zuordnen(api, eid, ids, erwartet=200):
    return api.post(f"/api/erwartungen/{eid}/buchungen", json={"buchung_ids": ids}, erwartet=erwartet)


def _manuell(api, betrag, richtung="ausgabe", **felder):
    return api.post("/api/erwartungen", json={"richtung": richtung, "haendler": "Fiktiver Laden", "betrag": betrag,
                                               **felder}, erwartet=201).daten


def _kandidaten(api, eid):
    return api.get(f"/api/erwartungen/{eid}/kandidaten", erwartet=200).daten["eintraege"]


# ------------------------------------------------------------------ Kandidaten (5.1)


def test_kandidaten_regeln_und_reihenfolge(tmp_path):
    api = app(tmp_path, [], heute="2024-07-31")
    k = konten(api)
    e = _manuell(api, 5000, datum="2024-06-10", kennung="AUFTRAG-777")
    eid = e["id"]
    passt = ausgabe(api, k, "2024-06-20", 2000, "Auftrag-777 Teil 1")             # kennung_passt (ohne -, Groß/Klein)
    gleich_haendler = ausgabe(api, k, "2024-06-12", 5000, "Einkauf", "Fiktiver Laden GmbH")  # betrag + anbieter
    gleich = ausgabe(api, k, "2024-06-11", 5000, "Einkauf")                        # betrag_gleich
    rand_vorn = ausgabe(api, k, "2024-06-07", 5000)                                # −3 Tage: Kandidat
    rand_hinten = ausgabe(api, k, "2024-07-25", 5000)                              # +45 Tage: Kandidat
    zu_frueh = ausgabe(api, k, "2024-06-06", 5000)                                 # −4 Tage
    zu_spaet = ausgabe(api, k, "2024-07-26", 5000)                                 # +46 Tage
    zu_hoch = ausgabe(api, k, "2024-06-12", 5001, "Auftrag-777")                   # > offen_betrag
    eingang_ = eingang(api, k, "2024-06-12", 5000)                                 # falsches Vorzeichen
    umbuchung = api.buchung("2024-06-12", [(k["giro"], -5000), (k["spar"], 5000)])["id"]
    weder = ausgabe(api, k, "2024-06-12", 1000, "nichts")                          # weder Kennung noch Betrag
    ids = [x["id"] for x in _kandidaten(api, eid)]
    assert ids == [passt, gleich_haendler, gleich, rand_vorn, rand_hinten], (
        "Reihenfolge: kennung_passt, betrag_gleich, anbieter_passt, Abstand, ID")
    for ausgeschlossen in (zu_frueh, zu_spaet, zu_hoch, eingang_, umbuchung, weder):
        assert ausgeschlossen not in ids
    k0 = _kandidaten(api, eid)[0]
    assert {f: k0[f] for f in ("datum", "betrag", "konto_id", "konto", "empfaenger", "verwendungszweck",
                               "kennung_passt", "betrag_gleich", "anbieter_passt", "abstand_tage")} == {
        "datum": "2024-06-20", "betrag": -2000, "konto_id": k["giro"], "konto": "Girokonto", "empfaenger": None,
        "verwendungszweck": "Auftrag-777 Teil 1", "kennung_passt": True, "betrag_gleich": False,
        "anbieter_passt": False, "abstand_tage": 10}
    k1 = _kandidaten(api, eid)[1]
    assert (k1["betrag_gleich"], k1["anbieter_passt"], k1["empfaenger"], k1["abstand_tage"]) == (
        True, True, "Fiktiver Laden GmbH", 2)
    # bereits einer anderen Erwartung zugeordnet → kein Kandidat
    andere = _manuell(api, 5000, datum="2024-06-10")
    _zuordnen(api, andere["id"], [gleich])
    assert gleich not in [x["id"] for x in _kandidaten(api, eid)]
    # nicht offen → leer; 404
    api.post(f"/api/erwartungen/{eid}/zustand", json={"zustand": "erledigt"}, erwartet=200)
    assert _kandidaten(api, eid) == []
    assert fehlercode(api.get("/api/erwartungen/999999/kandidaten", erwartet=404)) == "nicht_gefunden"


# ------------------------------------------------------------------ Automatisch (5.2) mit Dokumenten (5.3)


def test_automatisch_ueber_kennung_mit_teillieferungen_und_dokument(tmp_path):
    m = amazon_bestellung(empfangen="2024-06-03T08:00:00Z", nid="<b1@example.invalid>")
    api = app(tmp_path, [m, {**m, "postfach": ZWEI}], postfaecher=(EINS, ZWEI), heute="2024-06-20")
    k = konten(api)
    t1 = ausgabe(api, k, "2024-06-05", 2990, f"AMZN Mktp DE {NR[:8]} {NR[8:]}", "AMAZON EU")   # Leerzeichen egal
    t2 = ausgabe(api, k, "2024-06-08", 2000, f"Amazon {NR}")
    v, a0 = bestand(api), letzte_aenderung_id(api)
    abruf(api)
    (e,) = alle(api)
    assert e["buchung_ids"] == sorted([t1, t2]) and e["zustand"] == "erfuellt"
    assert (e["zugeordnet"], e["offen_betrag"]) == (4990, 0)
    assert len(e["dokument_ids"]) == 1, "je Nachrichten-ID ein Dokument, auch bei zwei Postfächern"
    d = dokument(api, e["dokument_ids"][0])
    assert (d["mime_typ"], d["quelle"], d["buchung_ids"]) == (MAIL, "mail", sorted([t1, t2]))
    assert d["dateiname"] == m["betreff"][:196] + ".eml"
    assert belege(api, t1) == belege(api, t2) and belege(api, t1)[0]["id"] == d["id"]
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"]) == ("mail", "erwartung_erkennen")
    pruefe_eintraege(a, v, bestand(api))
    assert {x["objekt"] for x in a["eintraege"]} == {"erwartung", "buchung", "dokument"}
    det = detail(api, e["id"])
    assert [b["id"] for b in det["buchungen"]] == sorted([t1, t2])
    b1 = next(b for b in det["buchungen"] if b["id"] == t1)
    assert b1 == {"id": t1, "datum": "2024-06-05", "betrag": -2990, "konto_id": k["giro"], "konto": "Girokonto",
                  "empfaenger": "AMAZON EU", "verwendungszweck": f"AMZN Mktp DE {NR[:8]} {NR[8:]}"}
    # Rückgängig entfernt Erwartung, Zuordnungen und Dokument; ein späterer Abgleich erkennt neu
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == v
    abgleich(api)
    assert alle(api)[0]["buchung_ids"] == sorted([t1, t2])


def test_automatisch_ueber_betrag_nur_eindeutig(tmp_path):
    """Ab M32 (sammel3.md 9.2, E-302, ersetzt 5.2 für PayPal): zugeordnet wird die einzige Buchung gleichen Betrags
    im Fenster, die den Händler der Mail in Teilen nennt; Buchungen ohne den Händler stören nicht."""
    z1 = paypal_zahlung(empfangen="2024-06-03T08:00:00Z")
    api = app(tmp_path, [z1], heute="2024-06-20")
    k = konten(api)
    ausgabe(api, k, "2024-06-04", 2000, "Lastschrift")                                # betrag_gleich, ohne Händler
    abruf(api)
    (e,) = alle(api)
    assert e["buchung_ids"] == [], "ohne den Händler keine automatische Zuordnung"
    mit = ausgabe(api, k, "2024-06-05", 2000, "PAYPAL *FIKTIVERSH")                  # Händler gekürzt
    abgleich(api)
    (e,) = alle(api)
    assert e["buchung_ids"] == [mit] and e["zustand"] == "erfuellt", "die Buchung ohne Händler stört nicht"


def test_automatisch_nicht_wenn_kandidat_fuer_andere_erwartung(tmp_path):
    api = app(tmp_path, [paypal_zahlung(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20")
    k = konten(api)
    _manuell(api, 2000, datum="2024-06-03")                                         # zweite offene Erwartung
    ausgabe(api, k, "2024-06-05", 2000, "PayPal Fiktiver Shop")
    abruf(api)
    assert all(e["buchung_ids"] == [] for e in alle(api))


def test_manuelle_erwartung_ueber_kennung_automatisch(tmp_path):
    api = app(tmp_path, [], heute="2024-06-20")
    k = konten(api)
    e = _manuell(api, 3000, datum="2024-06-01", kennung="VERTRAG-4711")
    b = ausgabe(api, k, "2024-06-02", 3000, "Rate vertrag 4711".replace(" 4711", "-4711"))
    erg = abgleich(api)
    assert erg["zugeordnet"] == 1
    assert detail(api, e["id"])["buchung_ids"] == [b]
    assert detail(api, e["id"])["dokument_ids"] == [], "ohne Mails keine Dokumente"


# ------------------------------------------------------------------ Manuell zuordnen (6.4)


def test_zuordnen_pruefreihenfolge(tmp_path):
    api = app(tmp_path, [], heute="2024-06-20")
    k = konten(api)
    e = _manuell(api, 3000, datum="2024-06-01")
    eid = e["id"]
    ok = ausgabe(api, k, "2024-01-01", 1000)                       # außerhalb des Fensters: trotzdem erlaubt
    falsch_vz = eingang(api, k, "2024-06-02", 1000)
    umbuchung = api.buchung("2024-06-02", [(k["giro"], -1000), (k["spar"], 1000)])["id"]
    ohne_bestand = api.buchung("2024-06-02", [(k["einkauf"], 1000), (k["ertrag"], -1000)])["id"]
    gross = ausgabe(api, k, "2024-06-03", 2500)
    anderer = _manuell(api, 1000)
    belegt = ausgabe(api, k, "2024-06-04", 500)
    _zuordnen(api, anderer["id"], [belegt])
    geschlossen = _manuell(api, 1000)
    api.post(f"/api/erwartungen/{geschlossen['id']}/zustand", json={"zustand": "erledigt"}, erwartet=200)

    def faelle():
        assert fehlercode(_zuordnen(api, 999999, [ok], erwartet=404)) == "nicht_gefunden"
        assert fehlercode(api.post("/api/erwartungen/999999/buchungen", json={"x": 1}, erwartet=404)) == "nicht_gefunden"
        for k_ in ({}, {"buchung_ids": []}, {"buchung_ids": ["1"]}, {"buchung_ids": [True]}, {"buchung_ids": [ok],
                                                                                             "x": 1}):
            assert fehlercode(api.post(f"/api/erwartungen/{eid}/buchungen", json=k_, erwartet=422)) == "validierung"
        assert fehlercode(_zuordnen(api, geschlossen["id"], [999999], erwartet=409)) == "erwartung_nicht_offen"
        assert fehlercode(_zuordnen(api, eid, [ok, 999999], erwartet=404)) == "nicht_gefunden"
        assert fehlercode(_zuordnen(api, eid, [umbuchung], erwartet=422)) == "zuordnung_ungueltig"
        assert fehlercode(_zuordnen(api, eid, [ohne_bestand], erwartet=422)) == "zuordnung_ungueltig"
        assert fehlercode(_zuordnen(api, eid, [falsch_vz], erwartet=422)) == "zuordnung_ungueltig"
        assert fehlercode(_zuordnen(api, eid, [belegt, falsch_vz], erwartet=422)) == "zuordnung_ungueltig"
        assert fehlercode(_zuordnen(api, eid, [belegt], erwartet=409)) == "buchung_bereits_zugeordnet"
        assert fehlercode(_zuordnen(api, eid, [ok, gross], erwartet=422)) == "zuordnung_zu_hoch"
    _ohne(api, faelle)
    # Teilzahlung, Rest, dann erfüllt; Doppelte zusammengefasst; schon zugeordnete ohne Wirkung
    d, a, v, n = _op(api, "erwartung_zuordnen", lambda: _zuordnen(api, eid, [ok, ok]).daten)
    assert (d["zustand"], d["zugeordnet"], d["offen_betrag"], d["buchung_ids"]) == ("offen", 1000, 2000, [ok])
    rundreise(api, a, v, n, zustand_fn=bestand)
    _ohne(api, lambda: _zuordnen(api, eid, [ok]))
    rest = ausgabe(api, k, "2024-06-05", 2000)
    d = _zuordnen(api, eid, [rest]).daten
    assert (d["zustand"], d["offen_betrag"]) == ("erfuellt", 0)
    assert fehlercode(_zuordnen(api, eid, [ausgabe(api, k, "2024-06-06", 1)], erwartet=409)) == "erwartung_nicht_offen"


def test_zuordnen_haengt_mail_und_pdf_an(tmp_path, netz_nur_loopback):
    """5.3: Echtmodus mit Rohfassung – Mail und PDF-Anhang werden Dokumente an der Buchung."""
    roh = mail(betreff=f"Ihre Bestellung {NR}", von="Amazon.de <bestellbestaetigung@amazon.example.invalid>",
               text=f"Bestellnr. {NR}\nGesamtsumme: 59,90 €\n", anhaenge=[("rechnung.pdf", PDF, pdf("Rechnung"))])
    o = OAuthAttrappe(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT).starte()
    i = ImapAttrappe(pruefe_token=o.access_gueltig, postfaecher=imap_postfaecher(EINS, [
        (dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(days=2), roh)])).starte()
    try:
        api, _ = echt_mit_imap(tmp_path, i, o, EINS, mail_abgleich=True)
        (e,) = alle(api)
        k = konten(api)
        heute = dt.date.today().isoformat()
        b = ausgabe(api, k, heute, 5990, "Kartenzahlung")
        d = _zuordnen(api, e["id"], [b]).daten
        docs = [dokument(api, x) for x in d["dokument_ids"]]
        assert sorted(x["mime_typ"] for x in docs) == sorted([MAIL, PDF]) and {x["quelle"] for x in docs} == {"mail"}
        mail_doc = next(x for x in docs if x["mime_typ"] == MAIL)
        assert api.get(f"/api/dokumente/{mail_doc['id']}/inhalt", erwartet=200).content == roh
        pdf_doc = next(x for x in docs if x["mime_typ"] == PDF)
        assert api.get(f"/api/dokumente/{pdf_doc['id']}/inhalt", erwartet=200).content == pdf("Rechnung")
        assert sorted(x["id"] for x in belege(api, b)) == sorted(d["dokument_ids"])
    finally:
        i.stoppe()
        o.stoppe()


# ------------------------------------------------------------------ Lösen, verwaiste Bezüge (5.3)


def test_loesen_und_dokumente(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20")
    k = konten(api)
    abruf(api)
    (e,) = alle(api)
    b1 = ausgabe(api, k, "2024-01-01", 2990)
    b2 = ausgabe(api, k, "2024-01-02", 2000)
    _zuordnen(api, e["id"], [b1])
    d = _zuordnen(api, e["id"], [b2]).daten
    assert d["zustand"] == "erfuellt" and len(d["dokument_ids"]) == 1
    doc = d["dokument_ids"][0]
    assert dokument(api, doc)["buchung_ids"] == sorted([b1, b2]), "vorhandene Dokumente mit neuer Buchung verknüpft"
    r, a, v, n = _op(api, "erwartung_loesen", lambda: api.delete(f"/api/erwartungen/{e['id']}/buchungen/{b2}",
                                                                  erwartet=200).daten)
    assert (r["buchung_ids"], r["zustand"], r["dokument_ids"]) == ([b1], "offen", [doc])
    assert dokument(api, doc)["buchung_ids"] == [b1]
    rundreise(api, a, v, n, zustand_fn=bestand)
    r = api.delete(f"/api/erwartungen/{e['id']}/buchungen/{b1}", erwartet=200).daten
    assert (r["buchung_ids"], r["dokument_ids"]) == ([], []), "das Dokument entfällt ohne Buchung"
    assert api.get(f"/api/dokumente/{doc}").status_code == 404
    _ohne(api, lambda: fehlercode(api.delete(f"/api/erwartungen/{e['id']}/buchungen/{b1}", erwartet=404)))
    _ohne(api, lambda: fehlercode(api.delete(f"/api/erwartungen/999999/buchungen/{b1}", erwartet=404)))


def test_verwaiste_bezuege_nach_buchungsloeschung(tmp_path):
    api = app(tmp_path, [amazon_bestellung(empfangen="2024-06-03T08:00:00Z")], heute="2024-06-20")
    k = konten(api)
    abruf(api)
    (e,) = alle(api)
    b = ausgabe(api, k, "2024-06-04", 4990, f"Amazon {NR}")
    abgleich(api)
    e = detail(api, e["id"])
    assert e["zustand"] == "erfuellt" and e["buchung_ids"] == [b]
    _, a, v, n = _op(api, "buchung_loeschen", lambda: api.delete(f"/api/buchungen/{b}", erwartet=204))
    e2 = detail(api, e["id"])
    assert (e2["buchung_ids"], e2["dokument_ids"], e2["zustand"]) == ([], [], "offen")
    assert {x["objekt"] for x in a["eintraege"]} == {"buchung", "dokument", "erwartung"}, "in derselben Änderung"
    rundreise(api, a, v, n, zustand_fn=bestand)
