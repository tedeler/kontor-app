"""M11: Kontostand bei der Synchronisation mit dem Mock-Plugin (kontostand.md 1.1, 2; E-159 bis E-161).

Erwartete Salden werden aus der Mock-Datendatei unabhängig berechnet (tests/hilfen/m11.py).
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen.api import neue_config
from tests.hilfen.m2 import (SYNC_DATEN, benachrichtigungen, konto_nach_iban, laeufe, lade_sync, mock_api, mock_bank,
                             sync)
from tests.hilfen.m3 import (KORREKTUR, aenderungen_seit, bestand, konto_id, letzte_aenderung_id, pruefe_eintraege,
                             pruefe_rueckgaengig_rundreise)
from tests.hilfen.m11 import (AUSGLEICH_ZWECK, HEUTE, bank_saldo, daten_mit_salden, gebucht_ab, konto_saldo,
                              ohne_saldo, sk)

VON = "2024-01-01"
STICHTAG = HEUTE.isoformat()


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


def _api(tmp_path, salden, **kw):
    return mock_api(tmp_path, daten=daten_mit_salden(tmp_path, salden), **kw)


def _alle(erw, wert=0):
    return {i: wert for i in erw["konto_namen"]}


# ------------------------------------------------------------------ Plugin (kontostand.md 1, 1.1)


@pytest.mark.kern
def test_mock_plugin_saldo(tmp_path, sd, netz_gesperrt):
    """Der Saldo kommt mit dem Umsatzabruf als Attribut der Umsatzliste (kontostand.md 1, E-159)."""
    daten, erw = sd
    giro, spar, kredit = erw["ibans"]["giro"], erw["ibans"]["spar"], erw["ibans"]["kredit"]
    pfad = daten_mit_salden(tmp_path, {giro: 12345, spar: None})
    p = mock_bank(pfad)
    bank = kontor.modul("kontor.plugins.bank")
    r = p.umsaetze(giro, dt.date(2024, 6, 1), dt.date(2024, 6, 2))
    assert isinstance(r, bank.Umsatzliste) and isinstance(r, list)
    assert r.saldo == bank.BankSaldo(giro, bank_saldo(daten, giro, 12345), HEUTE), "unabhängig vom Zeitraum"
    assert (r.saldo.iban, r.saldo.betrag, r.saldo.stichtag) == (giro, bank_saldo(daten, giro, 12345), HEUTE)
    with pytest.raises(Exception):
        r.saldo.betrag = 0  # frozen
    assert list(r) == r and r == list(r), "vergleicht wie eine Liste"
    assert p.umsaetze(giro.lower(), dt.date(2024, 1, 1), HEUTE).saldo == r.saldo, "IBAN normalisiert"
    assert p.umsaetze(spar, dt.date(2024, 1, 1), HEUTE).saldo is None, "null in anfangssalden → kein Saldo"
    assert p.umsaetze(kredit, dt.date(2024, 1, 1), HEUTE).saldo is None, "ohne Eintrag → kein Saldo"


def test_umsatzliste(netz_gesperrt):
    bank = kontor.modul("kontor.plugins.bank")
    assert bank.Umsatzliste().saldo is None and bank.Umsatzliste() == []
    s = bank.BankSaldo("DE28000000000000008001", -5, HEUTE)
    u = bank.Umsatzliste([], saldo=s)
    assert u.saldo == s and u == []


@pytest.mark.kern
def test_mock_plugin_ohne_schluessel_kein_saldo(netz_gesperrt, sd):
    """Ohne bank.anfangssalden bleibt alles wie bisher; die öffentlichen Methoden sind unverändert."""
    for p in (mock_bank(SYNC_DATEN), mock_bank(None)):
        for k in p.konten():
            assert getattr(p.umsaetze(k.iban, dt.date(2024, 1, 1), HEUTE), "saldo", None) is None
        assert not hasattr(p, "saldo")


def test_mock_plugin_saldo_beitragsaenderung(tmp_path, netz_gesperrt):
    """Im Szenario beitragsaenderung zählen die geänderten Beträge (kontostand.md 1.1)."""
    import json
    from tests.hilfen.m4 import VORLAGEN_MOCK as VORLAGEN_DATEN  # noqa: PLC0415
    daten = json.loads(VORLAGEN_DATEN.read_text(encoding="utf-8"))
    iban = daten["bank"]["konten"][0]["iban"]
    pfad = daten_mit_salden(tmp_path, {iban: 0}, quelle=VORLAGEN_DATEN)
    p = mock_bank(pfad, szenario="beitragsaenderung")
    soll = sum(u.get("betrag_beitragsaenderung", u["betrag"]) for u in daten["bank"]["umsaetze"]
               if u["iban"] == iban and not u["vormerkung"] and dt.date.fromisoformat(u["buchungstag"]) <= HEUTE)
    assert p.umsaetze(iban, dt.date(2000, 1, 1), HEUTE).saldo.betrag == soll


# ------------------------------------------------------------------ Konfiguration (python-api.md 17.1)


def test_konfiguration(tmp_path):
    K = kontor.KontorConfig()
    db = str(tmp_path / "k.db")
    assert K(datenbank=tmp_path / "k.db").sync_saldo_angleichen is True
    assert K.from_env({"KONTOR_DATENBANK": db}).sync_saldo_angleichen is True
    assert K.from_env({"KONTOR_DATENBANK": db, "KONTOR_SYNC_SALDO_ANGLEICHEN": ""}).sync_saldo_angleichen is True
    for w, soll in (("0", False), ("nein", False), ("OFF", False), ("1", True), ("ja", True), ("true", True)):
        assert K.from_env({"KONTOR_DATENBANK": db, "KONTOR_SYNC_SALDO_ANGLEICHEN": w}).sync_saldo_angleichen is soll
    for falsch in (1, 0, "ja", None):
        with pytest.raises(kontor.fehler().KonfigurationsFehler):
            K(datenbank=tmp_path / "k.db", sync_saldo_angleichen=falsch)
    with pytest.raises(kontor.fehler().KonfigurationsFehler):
        K.from_env({"KONTOR_DATENBANK": db, "KONTOR_SYNC_SALDO_ANGLEICHEN": "vielleicht"})


# ------------------------------------------------------------------ Abgleich im Lauf (kontostand.md 2)


@pytest.mark.kern
def test_ohne_saldo_unveraendert(tmp_path, sd, netz_gesperrt):
    """E-029: Mock ohne anfangssalden → nicht_verfuegbar, keine Ausgleichsbuchung."""
    _, erw = sd
    api = mock_api(tmp_path)
    lauf = sync(api, von=VON)
    for k in lauf["konten"]:
        assert k["saldo_abgleich"] == ohne_saldo("nicht_verfuegbar"), k["iban"]
    assert konto_id(api, KORREKTUR) is None
    assert not [b for b in api.alle_buchungen() if b["verwendungszweck"] == AUSGLEICH_ZWECK]
    assert not [b for b in benachrichtigungen(api) if b["art"] == "saldo_ausgeglichen"]


@pytest.mark.kern
def test_voller_abruf_stimmt(tmp_path, sd, netz_gesperrt):
    daten, erw = sd
    api = _api(tmp_path, _alle(erw))
    lauf = sync(api, von=VON)
    assert lauf["status"] == "erfolgreich"
    konten = konto_nach_iban(api)
    for iban in erw["konto_namen"]:
        soll = bank_saldo(daten, iban, 0)
        assert soll == erw["saldo_veraenderung"][iban]
        assert sk(lauf, iban)["saldo_abgleich"] == {"status": "stimmt", "bank_saldo": soll, "stichtag": STICHTAG,
                                                     "kontor_saldo": soll, "differenz": 0, "buchung_id": None}
        assert konto_saldo(api, konten[iban]["id"]) == soll
    assert konto_id(api, KORREKTUR) is None, "ohne Differenz keine Buchung und kein Konto „Korrekturen“"
    assert not [b for b in benachrichtigungen(api) if b["art"] == "saldo_ausgeglichen"]


@pytest.mark.kern
def test_erstabruf_bucht_fehlenden_anfangsbestand(tmp_path, sd, netz_gesperrt):
    """Erster Lauf ohne von holt 90 Tage; die Differenz ist Anfangssaldo + ältere Umsätze (kontostand.md 3)."""
    daten, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 50000})
    anzahl = len(api.alle_buchungen())
    lauf = sync(api)
    k = sk(lauf, giro)
    erst = HEUTE - dt.timedelta(days=90)
    assert k["von"] == erst.isoformat()
    soll_bank = bank_saldo(daten, giro, 50000)
    kontor_vorher = gebucht_ab(daten, giro, erst)
    d = soll_bank - kontor_vorher
    assert d != 0
    sa = k["saldo_abgleich"]
    assert {x: sa[x] for x in ("status", "bank_saldo", "stichtag", "kontor_saldo", "differenz")} == {
        "status": "ausgeglichen", "bank_saldo": soll_bank, "stichtag": STICHTAG, "kontor_saldo": kontor_vorher,
        "differenz": d}
    b = api.get(f"/api/buchungen/{sa['buchung_id']}", erwartet=200).daten
    kid, korr = konto_nach_iban(api)[giro]["id"], konto_id(api, KORREKTUR)
    assert korr is not None
    assert (b["datum"], b["empfaenger"], b["verwendungszweck"], b["status"], b["tags"]) == (
        STICHTAG, None, AUSGLEICH_ZWECK, "importiert", [])
    assert [(s["konto_id"], s["betrag"], s["memo"]) for s in b["splits"]] == [(kid, d, ""), (korr, -d, "")]
    assert b["extern_ids"] == [f"saldo:{giro}:{STICHTAG}"]
    assert b.get("vorschlag") is None
    assert konto_saldo(api, kid) == soll_bank
    assert len(api.alle_buchungen()) == anzahl + sum(x["buchungen_neu"] for x in lauf["konten"]) + 1
    # nur dieses Bankkonto hat einen Saldo
    for andere in set(erw["konto_namen"]) - {giro}:
        assert sk(lauf, andere)["saldo_abgleich"] == ohne_saldo("nicht_verfuegbar")
    # Benachrichtigung (2.3)
    bs = [x for x in benachrichtigungen(api) if x["art"] == "saldo_ausgeglichen"]
    assert len(bs) == 1
    assert (bs[0]["schluessel"], bs[0]["link"], bs[0]["gelesen"]) == (f"saldo:{giro}", f"/konten/{kid}", False)
    assert bs[0]["titel"].strip() and bs[0]["text"].strip()
    # zweiter Lauf: stimmt, keine weitere Buchung, keine weitere Benachrichtigung
    lauf2 = sync(api)
    sa2 = sk(lauf2, giro)["saldo_abgleich"]
    assert (sa2["status"], sa2["differenz"], sa2["buchung_id"], sa2["bank_saldo"]) == ("stimmt", 0, None, soll_bank)
    assert len([x for x in benachrichtigungen(api) if x["art"] == "saldo_ausgeglichen"]) == 1


@pytest.mark.kern
def test_neue_differenz_am_selben_tag(tmp_path, sd, netz_gesperrt):
    """Gelöschte Bankbuchung bleibt gemerkt → Differenz; zweite Kennung mit Zusatz ":2" (kontostand.md 2)."""
    daten, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 7000})
    sync(api)
    kid = konto_nach_iban(api)[giro]["id"]
    weg = next(b for b in api.alle_buchungen()
               if any(e.startswith(f"bank:{giro}:") for e in b["extern_ids"]))
    betrag = sum(s["betrag"] for s in weg["splits"] if s["konto_id"] == kid)
    api.delete(f"/api/buchungen/{weg['id']}", erwartet=204)
    lauf = sync(api)
    sa = sk(lauf, giro)["saldo_abgleich"]
    assert (sa["status"], sa["differenz"], sa["kontor_saldo"]) == ("ausgeglichen", betrag,
                                                                    bank_saldo(daten, giro, 7000) - betrag)
    b = api.get(f"/api/buchungen/{sa['buchung_id']}", erwartet=200).daten
    assert b["extern_ids"] == [f"saldo:{giro}:{STICHTAG}:2"]
    assert konto_saldo(api, kid) == bank_saldo(daten, giro, 7000)


@pytest.mark.kern
def test_negative_differenz_und_spaetere_buchungen(tmp_path, sd, netz_gesperrt):
    """Eigene Buchung vor der Bank → Ausgleich in Gegenrichtung; Buchungen nach dem Stichtag zählen nicht."""
    daten, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 0})
    sync(api, von=VON)
    kid = konto_nach_iban(api)[giro]["id"]
    kat = api.konto("Bargeld-Test", "aufwand")["id"]
    api.buchung("2024-06-29", [(kid, -4200), (kat, 4200)], verwendungszweck="vor der Bank")
    api.buchung("2024-07-05", [(kid, -9900), (kat, 9900)], verwendungszweck="nach dem Stichtag")
    lauf = sync(api, von=VON)
    sa = sk(lauf, giro)["saldo_abgleich"]
    assert (sa["status"], sa["differenz"]) == ("ausgeglichen", 4200)
    b = api.get(f"/api/buchungen/{sa['buchung_id']}", erwartet=200).daten
    assert b["splits"][0] == {**b["splits"][0], "konto_id": kid, "betrag": 4200}
    assert konto_saldo(api, kid, STICHTAG) == bank_saldo(daten, giro, 0)


def test_abgleich_abgeschaltet(tmp_path, sd, netz_gesperrt):
    _, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 99999}, sync_saldo_angleichen=False)
    lauf = sync(api)
    for k in lauf["konten"]:
        assert k["saldo_abgleich"] == ohne_saldo("aus")
    assert konto_id(api, KORREKTUR) is None


def test_fehlgeschlagener_lauf_ohne_abgleich(tmp_path, sd, netz_gesperrt):
    _, erw = sd
    api = _api(tmp_path, _alle(erw, 100), szenario="bankfehler")
    lauf = sync(api)
    assert lauf["status"] == "fehlgeschlagen"
    assert all(k["saldo_abgleich"] is None for k in lauf["konten"])
    assert konto_id(api, KORREKTUR) is None


def test_ausgleich_ist_keine_bankbuchung(tmp_path, sd, netz_gesperrt):
    """Die Ausgleichsbuchung wird nicht gemerkt und bei späteren Läufen nicht als Kandidat zusammengeführt."""
    daten, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 123})
    lauf = sync(api)
    bid = sk(lauf, giro)["saldo_abgleich"]["buchung_id"]
    lauf2 = sync(api)
    k2 = sk(lauf2, giro)
    assert k2["buchungen_zusammengefuehrt"] == 0
    b = api.get(f"/api/buchungen/{bid}", erwartet=200).daten
    assert b["extern_ids"] == [f"saldo:{giro}:{STICHTAG}"], "Kennung unverändert, keine Bankkennung angehängt"
    assert k2["saldo_abgleich"]["status"] == "stimmt"


# ------------------------------------------------------------------ Protokoll (kontostand.md 2.2)


@pytest.mark.kern
def test_protokoll_und_rueckgaengig(tmp_path, sd, netz_gesperrt):
    daten, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 2500})
    sync(api, von=VON)                      # erster Lauf: Differenz 2500
    erster = [a for a in aenderungen_seit(api, 0) if a["aktion"] == "sync_saldoausgleich"]
    assert len(erster) == 1
    a = erster[0]
    lauf_id = max(x["id"] for x in laeufe(api))
    assert (a["quelle"], a["gruppe"]) == ("sync", f"sync:{lauf_id}")
    arten = {(e["objekt"], e["art"]) for e in a["eintraege"]}
    assert arten == {("buchung", "angelegt"), ("konto", "angelegt")}, "Buchung und „Korrekturen“"
    alle = aenderungen_seit(api, 0)
    i = alle.index(next(x for x in alle if x["id"] == a["id"]))
    assert [x["aktion"] for x in alle[:i]][-1] in ("sync_konto", "umbuchung_erkennen"), "nach sync_konto"
    # zweiter Ausgleich nach Löschen einer Bankbuchung: Einträge und Rundreise
    kid = konto_nach_iban(api)[giro]["id"]
    weg = next(b for b in api.alle_buchungen() if any(e.startswith(f"bank:{giro}:") for e in b["extern_ids"]))
    api.delete(f"/api/buchungen/{weg['id']}", erwartet=204)
    vorher = bestand(api)
    vor_id = letzte_aenderung_id(api)
    sync(api, von=VON)
    neu = [x for x in aenderungen_seit(api, vor_id) if x["aktion"] == "sync_saldoausgleich"]
    assert len(neu) == 1
    nachher = bestand(api)
    assert len([k for k in nachher if k[0] == "buchung" and k not in vorher]) == 1
    pruefe_eintraege(neu[0], vorher, nachher)
    pruefe_rueckgaengig_rundreise(api, neu[0], vorher, nachher)
    assert konto_saldo(api, kid) == bank_saldo(daten, giro, 2500)


def test_rueckgaengig_der_gruppe(tmp_path, sd, netz_gesperrt):
    _, erw = sd
    giro = erw["ibans"]["giro"]
    api = _api(tmp_path, {giro: 1})
    vorher = bestand(api)
    lauf = sync(api)
    assert sk(lauf, giro)["saldo_abgleich"]["status"] == "ausgeglichen"
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"}, erwartet=200)
    assert bestand(api) == vorher


def test_neue_config_ohne_feld_bleibt_gueltig(tmp_path):
    """Die Testhilfe erzeugt Konfigurationen ohne das neue Feld; Vorgabe True (E-029)."""
    assert neue_config(tmp_path).sync_saldo_angleichen is True
