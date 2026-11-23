"""M5: Benachrichtigungen bei unerwarteten Buchungen (wiederkehrend.md 3–6; T 10, T 17; E-100).

Jeder Auslöser mit Positiv- und Negativfall; Entprellung je Ereignis (auch gelesene zählen); automatische
Prüfung nach dem Abruf mit der Wahrheit aus ``fixtures/mock/m5_wiederkehrend.erwartung.json``.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m5 import (WIEDER_MOCK, benachrichtigungen, lade_wiederkehrend, letzte_aenderung_id, mock_api,
                             nach_kennung, pruefen, sync, zeit)

DATEN, ERW = lade_wiederkehrend()
ARTEN = {"neuer_empfaenger", "wiederkehrend_betrag", "wiederkehrend_ausbleibend"}


def _app(tmp_path, heute="2024-06-20", **felder):
    api = mock_api(tmp_path, WIEDER_MOCK, heute, **felder)
    return api, api.konto("Giro")["id"], api.konto("Abo", "aufwand")["id"]


def _b(api, g, kat, emp, tag, betrag):
    return api.buchung(tag, [(g, betrag), (kat, -betrag)], empfaenger_id=emp)["id"]


def _schluessel(liste):
    return [(x["art"], x["schluessel"]) for x in liste]


@pytest.mark.kern
def test_neuer_empfaenger(tmp_path):
    api, g, kat = _app(tmp_path)
    karte = api.konto("Karte", "kreditkonto")["id"]
    neu, alt, ein = api.empfaenger("Neu GmbH")["id"], api.empfaenger("Alt GmbH")["id"], api.empfaenger("Zahler")["id"]
    _b(api, karte, kat, alt, "2024-01-03", -10)
    b1 = _b(api, g, kat, neu, "2024-06-01", -999)
    b2 = _b(api, g, kat, neu, "2024-06-02", -5)
    b3 = _b(api, g, kat, alt, "2024-06-03", -999)   # früher schon auf der Karte gebucht
    b4 = _b(api, g, kat, ein, "2024-06-04", 999)    # Einnahme: kein Ereignis
    a0 = letzte_aenderung_id(api)
    r = pruefen(api, [b4, b3, b2, b1]).daten
    assert r["stichtag"] == "2024-06-20"
    assert _schluessel(r["benachrichtigungen"]) == [("neuer_empfaenger", f"neuer_empfaenger:{neu}")]
    (n,) = r["benachrichtigungen"]
    assert (n["link"], n["gelesen"]) == (f"/buchungen/{b1}", False) and n["titel"].strip() and n["text"].strip()
    assert benachrichtigungen(api) == [n]
    assert letzte_aenderung_id(api) == a0, "Prüfen erzeugt keine Änderung im Protokoll"


@pytest.mark.kern
def test_geaenderter_betrag(tmp_path):
    api, g, kat = _app(tmp_path)
    e = api.empfaenger("Stream AG")["id"]
    for t in ("2024-01-15", "2024-02-15", "2024-03-15"):
        _b(api, g, kat, e, t, -1299)
    gleich = _b(api, g, kat, e, "2024-04-16", -1299)
    anders = _b(api, g, kat, e, "2024-05-17", -1499)
    r = pruefen(api, [gleich, anders]).daten["benachrichtigungen"]
    assert _schluessel(r) == [("wiederkehrend_betrag", f"wiederkehrend_betrag:{anders}")]
    assert r[0]["link"] == f"/buchungen/{anders}" and "Stream AG" in r[0]["text"]
    # Kette nicht fortgesetzt (11 Tage daneben) oder keine Serie in der Vorgeschichte: kein Ereignis
    weit = _b(api, g, kat, e, "2024-06-28", -1799)
    f = api.empfaenger("Neu AG")["id"]
    zwei = [_b(api, g, kat, f, t, -100) for t in ("2024-04-01", "2024-05-01")]
    dritte = _b(api, g, kat, f, "2024-06-01", -150)
    r = pruefen(api, [weit, dritte, *zwei]).daten["benachrichtigungen"]
    assert _schluessel(r) == [("neuer_empfaenger", f"neuer_empfaenger:{f}")], "nur der neue Empfänger, kein Betrag"


@pytest.mark.kern
def test_ausbleibende_zahlung_genau_einmal(tmp_path):
    api, g, kat = _app(tmp_path, "2024-04-15")
    e = api.empfaenger("Studio AG")["id"]
    for t in ("2024-01-10", "2024-02-10", "2024-03-10"):
        _b(api, g, kat, e, t, -3990)
    assert pruefen(api).daten["benachrichtigungen"] == [], "bis Fälligkeit + 5 Tage aktiv"
    zeit(api, "2024-04-16")
    r = pruefen(api).daten
    giro_schl = f"{g}:{e}:ausgabe"
    assert r["stichtag"] == "2024-04-16"
    assert _schluessel(r["benachrichtigungen"]) == [("wiederkehrend_ausbleibend",
                                                     f"wiederkehrend_ausbleibend:{giro_schl}:2024-04-10")]
    assert r["benachrichtigungen"][0]["link"] == "/wiederkehrend"
    assert pruefen(api).daten["benachrichtigungen"] == [], "dasselbe Ereignis nur einmal"
    api.post(f"/api/benachrichtigungen/{r['benachrichtigungen'][0]['id']}/gelesen", erwartet=200)
    zeit(api, "2024-05-01")
    assert pruefen(api).daten["benachrichtigungen"] == [], "auch nach dem Lesen nicht noch einmal (E-100)"
    zeit(api, "2024-05-16")
    assert pruefen(api).daten["benachrichtigungen"] == [], "beendet: keine weitere Meldung"
    assert len(benachrichtigungen(api)) == 1


@pytest.mark.kern
def test_neue_zahlung_beendet_ausbleiben_und_neue_faelligkeit_ist_neues_ereignis(tmp_path):
    api, g, kat = _app(tmp_path, "2024-04-16")
    e = api.empfaenger("Studio AG")["id"]
    for t in ("2024-01-10", "2024-02-10", "2024-03-10"):
        _b(api, g, kat, e, t, -3990)
    assert len(pruefen(api).daten["benachrichtigungen"]) == 1
    _b(api, g, kat, e, "2024-04-12", -3990)   # verspätet, Kette hält (2 Tage)
    zeit(api, "2024-05-17")
    assert pruefen(api).daten["benachrichtigungen"] == [], "nächste Fälligkeit 12.05. + 5 Tage: noch aktiv"
    zeit(api, "2024-05-18")
    (n,) = pruefen(api).daten["benachrichtigungen"]
    assert n["schluessel"].endswith(":2024-05-12")


def test_pruefen_fehler(tmp_path):
    api, g, kat = _app(tmp_path)
    r = pruefen(api, [5, 3], erwartet=422)
    assert fehlercode(r) == "referenz_unbekannt" and r.json()["fehler"]["details"]["buchung_ids"] == [3, 5]
    e = api.empfaenger("X")["id"]
    b = _b(api, g, kat, e, "2024-01-01", -1)
    assert fehlercode(pruefen(api, [b, b], erwartet=422)) == "validierung"
    assert fehlercode(api.post("/api/wiederkehrend/pruefen", json={"buchung_ids": "1"}, erwartet=422)) == "validierung"
    assert benachrichtigungen(api) == []


# ------------------------------------------------------------------ automatisch beim Abruf
def _progression(tmp_path, automatisch: bool):
    pr = ERW["progression"]
    api = mock_api(tmp_path, WIEDER_MOCK, pr["progression_start"], wiederkehrend_automatisch=automatisch)
    sync(api, von=ERW["von"], bis=pr["progression_start"])
    nach_erstabruf = [x for x in benachrichtigungen(api) if x["art"] in ARTEN]
    for tag in pr["abrufe"]:
        zeit(api, tag)
        lauf = sync(api)
        assert lauf["status"] == "erfolgreich", lauf
    return api, nach_erstabruf


@pytest.mark.kern
def test_automatisch_nach_dem_abruf_gleich_wahrheit(tmp_path):
    api, nach_erstabruf = _progression(tmp_path, True)
    assert nach_erstabruf == [], "der Erstabruf eines Kontos meldet keine unerwarteten Buchungen"
    emp = {e["name"]: e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten}
    giro = next(k["id"] for k in api.konten() if k["iban"] == ERW["iban"])
    bid = {u: b["id"] for u, b in nach_kennung(api).items()}
    soll = []
    for b in ERW["progression"]["benachrichtigungen"]:
        if b["art"] == "neuer_empfaenger":
            soll.append((b["art"], f"neuer_empfaenger:{emp[b['empfaenger']]}", f"/buchungen/{bid[b['umsatz_id']]}"))
        elif b["art"] == "wiederkehrend_betrag":
            soll.append((b["art"], f"wiederkehrend_betrag:{bid[b['umsatz_id']]}", f"/buchungen/{bid[b['umsatz_id']]}"))
        else:
            soll.append((b["art"], f"wiederkehrend_ausbleibend:{giro}:{emp[b['empfaenger']]}:{b['richtung']}:"
                                   f"{b['naechste_faelligkeit']}", "/wiederkehrend"))
    ist = [(x["art"], x["schluessel"], x["link"]) for x in benachrichtigungen(api) if x["art"] in ARTEN]
    assert sorted(ist) == sorted(soll)
    (aus,) = [x for x in benachrichtigungen(api) if x["art"] == "wiederkehrend_ausbleibend"]
    assert aus["erstellt_am"].startswith(ERW["progression"]["benachrichtigungen"][-1]["erster_abruf"])


def test_ohne_automatik_keine_benachrichtigungen(tmp_path):
    api, _ = _progression(tmp_path, False)
    assert [x for x in benachrichtigungen(api) if x["art"] in ARTEN] == []
