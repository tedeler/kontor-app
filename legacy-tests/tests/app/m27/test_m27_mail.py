"""M27: Mail-Liste mit Stand, Reihenfolge und Zuordnung (mail.md 6.6; E-249, E-250) – REST, kern."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import mock_api
from tests.hilfen.m6 import EINS, ZWEI, abruf, postfach, postfach_status
from tests.hilfen.m20 import NR, PAYPAL, alle, amazon_bestellung, detail, konten, mock_datei, nachricht
from tests.hilfen.m27 import mails, warum_soll

pytestmark = pytest.mark.kern

REFERENZ = "471108150"


def _paypal(code: str, **kw) -> dict:
    text = (f"Sie haben 30,00 € an Versandhaus (fiktiv) gesendet.\nTransaktionscode: {code}\n"
            f"Gesendeter Betrag: -30,00 €\nBezahlt mit\nLastschrift Testbank\nBestellnummer: {REFERENZ}\n")
    return nachricht(PAYPAL, "Sie haben eine Zahlung an Versandhaus (fiktiv) gesendet", text, **kw)


@pytest.fixture
def welt(tmp_path):
    m = [amazon_bestellung(nr=NR, empfangen="2024-06-01T08:00:00Z"),                       # wird zugeordnet
         amazon_bestellung(nr="302-7654321-1234567", empfangen="2024-06-02T08:00:00Z"),    # nur erwartet
         nachricht("Verein <info@verein.example.invalid>", "", "Hallo", "2024-06-03T08:00:00Z"),   # keine
         _paypal("7AB23456CD789012E", empfangen="2024-06-03T08:00:00Z", postfach=ZWEI),
         nachricht("Newsletter <news@shop.example.invalid>", "Angebote", "Text", "2024-06-04T08:00:00Z",
                   postfach=ZWEI)]
    datei = mock_datei(tmp_path / "mock.json", m)
    api = mock_api(tmp_path / "a", daten=datei, heute="2024-06-05", mail_erstabruf_tage=365, mail_abgleich=True)
    p1 = postfach(api, EINS, bezeichnung="Torsten")["id"]
    p2 = postfach(api, ZWEI)["id"]
    abruf(api)
    k = konten(api)
    e = {x["kennung"]: x for x in alle(api)}
    return api, k, e, m, p1, p2


def _zuordnen(api, eid, bids):
    api.post(f"/api/erwartungen/{eid}/buchungen", json={"buchung_ids": bids}, erwartet=200)


def _ausgabe(api, k, betrag, zweck="", empfaenger=None, datum="2024-06-04"):
    felder = {"verwendungszweck": zweck}
    if empfaenger:
        felder["empfaenger_id"] = api.empfaenger(empfaenger)["id"]
    return api.buchung(datum, [(k["giro"], -betrag), (k["einkauf"], betrag)], **felder)["id"]


def test_standard_unveraendert_und_reihenfolge(welt):
    api, k, e, m, p1, p2 = welt
    d = mails(api)
    schluessel = [(x["empfangen"], x["postfach_id"], x["nachricht_id"]) for x in d["eintraege"]]
    assert schluessel == sorted(schluessel) and d["gesamt"] == 5
    assert mails(api, reihenfolge="aelteste")["eintraege"] == d["eintraege"]
    neu = mails(api, reihenfolge="neueste")["eintraege"]
    assert [x["id"] for x in neu] == [x["id"] for x in sorted(d["eintraege"], key=lambda x: (
        _neg(x["empfangen"]), x["postfach_id"], x["nachricht_id"]))]
    hinten = mails(api, seite=9, pro_seite=2)
    assert (hinten["eintraege"], hinten["seite"]) == ([], 9)
    for p, w in (("reihenfolge", "neu"), ("zuordnung", "alle"), ("zuordnung", "")):
        assert fehlercode(mails(api, erwartet=422, **{p: w})) == "validierung"


def _neg(zeit: str) -> tuple:
    return tuple(-ord(c) for c in zeit)


def test_postfach_und_stand(welt):
    api, k, e, m, p1, p2 = welt
    d = mails(api)
    for x in d["eintraege"]:
        assert x["postfach"] == ("Torsten" if x["postfach_id"] == p1 else ZWEI), "Bezeichnung, leer → Adresse"
    st = d["stand"]
    assert (st["gesamt"], st["zugeordnet"], st["erwartet"], st["keine"]) == (5, 0, 3, 2)
    assert [p["postfach_id"] for p in st["postfaecher"]] == [p1, p2]
    for p in st["postfaecher"]:
        s = postfach_status(api, p["postfach_id"])
        for f in ("nachrichten", "letzter_abruf_am", "letzter_erfolg_am", "letzter_fehler"):
            assert p[f] == s[f], f
        pf = api.get(f"/api/mail/postfaecher/{p['postfach_id']}", erwartet=200).daten
        assert (p["adresse"], p["bezeichnung"], p["aktiv"]) == (pf["adresse"], pf["bezeichnung"], pf["aktiv"])
    # postfach_id-Filter: Zählungen nur dieses Postfachs, postfaecher weiter alle
    st1 = mails(api, postfach_id=p1)["stand"]
    assert (st1["gesamt"], st1["erwartet"], st1["keine"]) == (3, 2, 1)
    assert [p["postfach_id"] for p in st1["postfaecher"]] == [p1, p2]


def test_zuordnung_arten_und_filter(welt):
    api, k, e, m, p1, p2 = welt
    eid = e[NR]["id"]
    bid = _ausgabe(api, k, 1234, "Sammelüberweisung")
    _zuordnen(api, eid, [bid])
    d = mails(api)
    arten = {}
    for x in d["eintraege"]:
        z = x["zuordnung"]
        arten[x["nachricht_id"]] = ("zugeordnet" if any(y["buchungen"] for y in z) else
                                    "erwartet" if z else "keine")
    assert sorted(arten.values()) == ["erwartet", "erwartet", "keine", "keine", "zugeordnet"]
    st = d["stand"]
    assert (st["gesamt"], st["zugeordnet"], st["erwartet"], st["keine"]) == (5, 1, 2, 2)
    for art in ("zugeordnet", "erwartet", "keine"):
        f = mails(api, zuordnung=art)
        ids = [x["nachricht_id"] for x in f["eintraege"]]
        assert sorted(ids) == sorted(n for n, a in arten.items() if a == art)
        assert f["gesamt"] == len(ids) and f["stand"] == st, "stand ohne zuordnung-Filter"
    seite = mails(api, zuordnung="erwartet", pro_seite=1, seite=2)
    assert seite["gesamt"] == 2 and len(seite["eintraege"]) == 1
    # Inhalt eines Zuordnungseintrags
    (x,) = [x for x in d["eintraege"] if x["nachricht_id"] == m[0]["nachricht_id"]]
    (z,) = x["zuordnung"]
    erw = detail(api, eid)
    assert {f: z[f] for f in ("erwartung_id", "grund", "zustand", "ueberfaellig", "haendler", "kennung",
                              "vorzeichen_betrag")} == {
        "erwartung_id": eid, "grund": erw["grund"], "zustand": erw["zustand"],
        "ueberfaellig": erw["zustand"] == "offen" and erw["frist"] < "2024-06-05", "haendler": erw["haendler"],
        "kennung": NR, "vorzeichen_betrag": -erw["betrag"]}
    assert [{f: b[f] for f in b if f != "warum"} for b in z["buchungen"]] == erw["buchungen"]


def test_ueberfaellig(welt):
    api, k, e, m, p1, p2 = welt
    from tests.hilfen.m2 import setze_zeit
    setze_zeit(api, "2024-07-30T10:00:00Z")
    erw = {x["erwartung_id"]: x for y in mails(api)["eintraege"] for x in y["zuordnung"]}
    for eid, z in erw.items():
        d = detail(api, eid)
        assert z["ueberfaellig"] == (d["zustand"] == "offen" and d["frist"] < "2024-07-30")
    assert any(z["ueberfaellig"] for z in erw.values())


@pytest.mark.parametrize("fall", ["kennung_zweck", "kennung_empfaenger", "referenz_zweck", "betrag_name",
                                  "betrag_amzn", "manuell"])
def test_warum(welt, fall):
    api, k, e, m, p1, p2 = welt
    amazon, paypal = e[NR], next(x for x in e.values() if x["anbieter"] == "paypal")
    ziel, bid = {
        "kennung_zweck": (amazon, lambda: _ausgabe(api, k, 999, f"Zahlung {NR} danke")),
        "kennung_empfaenger": (amazon, lambda: _ausgabe(api, k, 999, "x", empfaenger=f"Händler {NR}")),
        "referenz_zweck": (paypal, lambda: _ausgabe(api, k, 999, f"PP Bestellung {REFERENZ}")),
        "betrag_name": (amazon, lambda: _ausgabe(api, k, amazon["betrag"], "AMAZON EU Einkauf")),
        "betrag_amzn": (amazon, lambda: _ausgabe(api, k, amazon["betrag"], "x", empfaenger="AMZN Mktp (fiktiv)")),
        "manuell": (amazon, lambda: _ausgabe(api, k, amazon["betrag"], "Überweisung")),
    }[fall]
    b = bid()
    _zuordnen(api, ziel["id"], [b])
    z = [y for x in mails(api)["eintraege"] for y in x["zuordnung"] if y["erwartung_id"] == ziel["id"]]
    assert z, "Nachricht der Erwartung trägt die Zuordnung"
    (eintrag,) = [x for x in z[0]["buchungen"] if x["id"] == b]
    soll = warum_soll(eintrag, detail(api, ziel["id"]))
    assert eintrag["warum"] == soll
    erwartet = {"kennung_zweck": f"Die Kennung „{NR}“ steht im Verwendungszweck.",
                "kennung_empfaenger": f"Die Kennung „{NR}“ steht beim Empfänger.",
                "referenz_zweck": f"Die Referenz „{REFERENZ}“ steht im Verwendungszweck.",
                "betrag_name": "Der Betrag stimmt, und der Name des Händlers oder Anbieters steht in der Buchung.",
                "betrag_amzn": "Der Betrag stimmt, und der Name des Händlers oder Anbieters steht in der Buchung.",
                "manuell": "Manuell zugeordnet. Kennung, Betrag und Name erklären die Buchung nicht von selbst."}
    assert soll == erwartet[fall]


def test_nur_lesend(welt):
    api, k, e, m, p1, p2 = welt
    from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
    a0 = letzte_aenderung_id(api)
    for p in ({}, {"reihenfolge": "neueste"}, {"zuordnung": "keine"}):
        mails(api, **p)
    assert aenderungen_seit(api, a0) == []

