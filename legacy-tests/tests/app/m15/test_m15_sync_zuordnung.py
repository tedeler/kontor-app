"""M15: Synchronisationskonto und Zuordnung unbekannter Bankkonten (synchronisation.md 20, python-api.md 18,
betrieb.md 3, E-186).

Erwartungen aus der Mock-Datendatei (``sync_daten.json`` und ``sync_daten.erwartung.json``) und dem Orakel
``tests/hilfen/sync_orakel.py``.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import kontor
from tests.hilfen import sync_orakel as orakel
from tests.hilfen.m2 import benachrichtigungen, konto_nach_iban, lade_sync, mock_api, sync
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m7 import betriebsdatei
from tests.hilfen.systemd import umgebungsdatei

VON = "2024-01-01"
HEUTE = dt.date(2024, 6, 30)
ART = "konto_nicht_zugeordnet"


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def aus(tmp_path):
    return mock_api(tmp_path, sync_konten_anlegen=False)


def _bank(daten) -> dict[str, dict]:
    return {k["iban"]: k for k in daten["bank"]["konten"]}


def _eintrag(daten, iban) -> dict:
    k = _bank(daten)[iban]
    art = k["art"] if k["art"] in ("girokonto", "sparkonto", "kreditkonto") else "girokonto"
    return {"iban": iban, "name": k["name"].strip() or iban, "status": "nicht_zugeordnet", "art": art}


def _gebucht(daten, iban) -> int:
    return len([u for u in orakel.im_zeitraum(daten["bank"]["umsaetze"], iban, dt.date.fromisoformat(VON), HEUTE,
                                              HEUTE) if not u["vormerkung"]])


def _ungelesen(api, iban) -> list[dict]:
    return [b for b in benachrichtigungen(api) if b["schluessel"] == f"{ART}:{iban}" and not b["gelesen"]]


def _sync_konten(api) -> dict[str, dict]:
    return {z["iban"]: z for z in api.get("/api/sync/konten", erwartet=200).daten}


# ------------------------------------------------------------------ Konfiguration


@pytest.mark.kern
def test_konfiguration(tmp_path):
    K = kontor.KontorConfig()
    db = str(tmp_path / "k.db")
    assert K(datenbank=tmp_path / "k.db").sync_konten_anlegen is True
    assert K.from_env({"KONTOR_DATENBANK": db}).sync_konten_anlegen is True
    assert K.from_env({"KONTOR_DATENBANK": db, "KONTOR_SYNC_KONTEN_ANLEGEN": ""}).sync_konten_anlegen is True
    for w, soll in (("0", False), ("false", False), ("Nein", False), ("OFF", False), ("no", False), ("1", True),
                    ("ja", True), ("TRUE", True), ("on", True), ("yes", True)):
        assert K.from_env({"KONTOR_DATENBANK": db, "KONTOR_SYNC_KONTEN_ANLEGEN": w}).sync_konten_anlegen is soll, w
    assert K(datenbank=tmp_path / "k.db", sync_konten_anlegen=False).sync_konten_anlegen is False
    for falsch in (1, 0, "ja", None):
        with pytest.raises(kontor.fehler().KonfigurationsFehler):
            K(datenbank=tmp_path / "k.db", sync_konten_anlegen=falsch)
    for falsch in ("vielleicht", "2", "an"):
        with pytest.raises(kontor.fehler().KonfigurationsFehler):
            K.from_env({"KONTOR_DATENBANK": db, "KONTOR_SYNC_KONTEN_ANLEGEN": falsch})


@pytest.mark.kern
def test_ausgelieferte_umgebungsdatei(tmp_path):
    werte, _ = umgebungsdatei(betriebsdatei("kontor.env"))
    assert werte.get("KONTOR_SYNC_KONTEN_ANLEGEN") == "0"
    c = kontor.KontorConfig().from_env({**werte, "KONTOR_DATENBANK": str(tmp_path / "k.sqlite3"),
                                        "CREDENTIALS_DIRECTORY": str(tmp_path)})
    assert c.sync_konten_anlegen is False


# ------------------------------------------------------------------ Lauf mit sync_konten_anlegen = False


@pytest.mark.kern
def test_unbekannte_bankkonten_uebersprungen(aus, sd, netz_gesperrt):
    daten, erw = sd
    giro, spar, kredit = erw["ibans"]["giro"], erw["ibans"]["spar"], erw["ibans"]["kredit"]
    sk = aus.konto("Mein Tagesgeld", "sparkonto", iban=spar)
    a0 = letzte_aenderung_id(aus)
    lauf = sync(aus, von=VON)
    assert (lauf["status"], lauf["fehler"]) == ("erfolgreich", None)
    assert [k["iban"] for k in lauf["konten"]] == [spar]
    assert (lauf["konten"][0]["konto_id"], lauf["konten"][0]["konto_neu"]) == (sk["id"], False)
    assert lauf["konten"][0]["buchungen_neu"] == _gebucht(daten, spar)
    assert lauf["uebersprungen"] == [_eintrag(daten, i) for i in sorted([giro, kredit])]
    assert set(konto_nach_iban(aus)) == {spar}, "kein Konto für unbekannte Bankkonten"
    assert set(_sync_konten(aus)) == {spar}, "kein Eintrag in /api/sync/konten"
    assert all(s["konto_id"] != k["id"] for b in aus.alle_buchungen() for s in b["splits"]
               for k in aus.konten() if k["iban"] in (giro, kredit))
    assert not any(e.startswith(f"bank:{i}:") for b in aus.alle_buchungen() for e in b["extern_ids"]
                   for i in (giro, kredit)), "kein Umsatz der übersprungenen Bankkonten"
    neu = aenderungen_seit(aus, a0)
    assert all(a["aktion"] != "sync_kontozuordnung" for a in neu), "keine Kontozuordnung"
    assert not [e for a in neu for e in a["eintraege"] if e["objekt"] == "konto" and e["nachher"]
                and e["nachher"]["iban"] in (giro, kredit)], "kein Konto für übersprungene Bankkonten"
    for iban in (giro, kredit):
        (b,) = _ungelesen(aus, iban)
        assert (b["art"], b["link"]) == (ART, "/sync")
        assert b["titel"].strip() and iban in b["text"].replace(" ", "")
    assert not _ungelesen(aus, spar)


@pytest.mark.kern
def test_alle_uebersprungen_erfolgreich_ohne_aenderung(aus, sd, netz_gesperrt):
    daten, erw = sd
    a0 = letzte_aenderung_id(aus)
    lauf = sync(aus, von=VON)
    assert (lauf["status"], lauf["fehler"], lauf["konten"]) == ("erfolgreich", None, [])
    assert lauf["uebersprungen"] == [_eintrag(daten, i) for i in sorted(erw["konto_namen"])]
    assert aenderungen_seit(aus, a0) == [] and aus.konten() == [] and aus.alle_buchungen() == []
    assert aus.get(f"/api/sync/laeufe/{lauf['id']}", erwartet=200).daten["uebersprungen"] == lauf["uebersprungen"]


@pytest.mark.kern
def test_benachrichtigung_entprellt(aus, sd, netz_gesperrt):
    _, erw = sd
    giro = erw["ibans"]["giro"]
    sync(aus, von=VON)
    sync(aus, von=VON)
    alle = [b for b in benachrichtigungen(aus) if b["schluessel"] == f"{ART}:{giro}"]
    assert len(alle) == 1, "höchstens eine ungelesene je IBAN"
    aus.post(f"/api/benachrichtigungen/{alle[0]['id']}/gelesen", erwartet=200)
    sync(aus, von=VON)
    alle = [b for b in benachrichtigungen(aus) if b["schluessel"] == f"{ART}:{giro}"]
    assert len(alle) == 2 and len(_ungelesen(aus, giro)) == 1, "nach dem Lesen entsteht wieder eine"


# ------------------------------------------------------------------ Zuordnen


@pytest.mark.kern
def test_zuordnen_per_patch_und_post(aus, sd, netz_gesperrt):
    daten, erw = sd
    giro, spar, kredit = erw["ibans"]["giro"], erw["ibans"]["spar"], erw["ibans"]["kredit"]
    vorhanden = aus.konto("Haushaltskonto", "girokonto", notiz="bleibt")
    sync(aus, von=VON)
    a0 = letzte_aenderung_id(aus)
    eingabe = " ".join(giro[i:i + 4] for i in range(0, len(giro), 4)).lower()
    k = aus.patch(f"/api/konten/{vorhanden['id']}", json={"iban": eingabe}, erwartet=200).daten
    assert k == {**vorhanden, "iban": giro}
    (a,) = aenderungen_seit(aus, a0)
    assert (a["quelle"], a["aktion"]) == ("manuell", "konto_aendern")
    assert not _ungelesen(aus, giro), "Zuordnung liest die Benachrichtigung"
    assert len(_ungelesen(aus, kredit)) == 1 and len(_ungelesen(aus, spar)) == 1
    neu = aus.konto("Karte", "kreditkonto", iban=kredit)
    assert not _ungelesen(aus, kredit) and len(_ungelesen(aus, spar)) == 1
    lauf = sync(aus, von=VON)
    ergebnis = {x["iban"]: x for x in lauf["konten"]}
    assert set(ergebnis) == {giro, kredit}
    assert (ergebnis[giro]["konto_id"], ergebnis[giro]["konto_neu"]) == (vorhanden["id"], False)
    assert (ergebnis[kredit]["konto_id"], ergebnis[kredit]["konto_neu"]) == (neu["id"], False)
    for iban in (giro, kredit):
        assert ergebnis[iban]["status"] == "erfolgreich"
        assert ergebnis[iban]["buchungen_neu"] == _gebucht(daten, iban)
    assert lauf["uebersprungen"] == [_eintrag(daten, spar)]
    assert aus.get(f"/api/konten/{vorhanden['id']}", erwartet=200).daten == k, "Konto unverändert (Regel 1)"
    assert set(_sync_konten(aus)) == {giro, kredit}


@pytest.mark.kern
def test_geloeschtes_zugeordnetes_bankkonto_bleibt_konto_fehlt(aus, sd, netz_gesperrt):
    """synchronisation.md 20.2 letzter Punkt: Einträge mit gelöschtem Konto folgen weiter 16."""
    daten, erw = sd
    giro = erw["ibans"]["giro"]
    k = aus.konto("Giro", "girokonto", iban=giro)
    sync(aus, von=VON)
    aus.post(f"/api/konten/{k['id']}/loeschen", json={"buchungen": "loeschen", "konflikte": "behalten"},
             erwartet=200)
    lauf = sync(aus, von=VON)
    eintraege = {x["iban"]: x for x in lauf["uebersprungen"]}
    assert eintraege[giro]["status"] == "konto_fehlt"
    assert {x["status"] for i, x in eintraege.items() if i != giro} == {"nicht_zugeordnet"}
    assert giro not in konto_nach_iban(aus)
    assert _sync_konten(aus)[giro]["status"] == "konto_fehlt"


@pytest.mark.kern
def test_vorgabe_legt_konten_an_wie_bisher(tmp_path, sd, netz_gesperrt):
    daten, erw = sd
    api = mock_api(tmp_path)
    lauf = sync(api, von=VON)
    assert sorted(x["iban"] for x in lauf["konten"]) == sorted(erw["konto_namen"])
    assert all(x["konto_neu"] for x in lauf["konten"])
    assert lauf.get("uebersprungen", []) == []
    assert set(konto_nach_iban(api)) == set(erw["konto_namen"])
    assert not [b for b in benachrichtigungen(api) if b["art"] == ART]
