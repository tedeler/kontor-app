"""M3-Nachtrag: gelöschte Bankkonten bei der Synchronisation (synchronisation.md 16, E-080 bis E-084).

Beobachtung des Anwenders: Nach dem Löschen eines synchronisierten Kontos legte der nächste Lauf es leer
neu an, ohne Buchungen. Neu wird gefragt (Status ``konto_fehlt``), und beim Wiederherstellen mit
``buchungen = "alle"`` kommen die Umsätze zurück, deren Buchung nicht mehr existiert.

Erwartungen kommen aus der Mock-Datendatei und ihrer bekannten Wahrheit (``sync_daten.erwartung.json``)
sowie aus ``tests/hilfen/sync_orakel`` – nie aus Ausgaben der Anwendung.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import benachrichtigungen, konto_nach_iban, lade_sync, mock_api, nach_kennung, sync
from tests.hilfen.m3 import aenderungen_seit, alle_aenderungen, letzte_aenderung_id, rueckgaengig

VON = "2024-01-01"
HEUTE = dt.date(2024, 6, 30)


@pytest.fixture(scope="module")
def sd():
    return lade_sync()


@pytest.fixture
def sapi(tmp_path):
    return mock_api(tmp_path)


# ------------------------------------------------------------------ Hilfen


def _zustand(api) -> dict[str, dict]:
    return {z["iban"]: z for z in api.get("/api/sync/konten", erwartet=200).daten}


def _entscheiden(api, iban: str, aktion: str, buchungen: str, erwartet: int = 200):
    r = api.post(f"/api/sync/konten/{iban}/entscheidung", json={"aktion": aktion, "buchungen": buchungen},
                 erwartet=erwartet)
    return r.daten if erwartet == 200 else r


def _loeschen(api, konto_id: int, variante: str = "loeschen") -> None:
    # Bankbuchungen gehen nach „Unkategorisiert“; bei Variante unkategorisiert sind es also Konfliktbuchungen
    # (loeschen.md 3.3), die hier behalten werden, damit die Buchungen weiter existieren.
    api.post(f"/api/konten/{konto_id}/loeschen", json={"buchungen": variante, "konflikte": "behalten"},
             erwartet=200)


def _gebucht(daten, iban, von=VON, bis="2024-06-30") -> list[dict]:
    geliefert = orakel.im_zeitraum(daten["bank"]["umsaetze"], iban, dt.date.fromisoformat(von),
                                   dt.date.fromisoformat(bis), HEUTE)
    return [u for u in geliefert if not u["vormerkung"]]


def _kennungen(api, iban: str) -> set[str]:
    return set(nach_kennung(api.alle_buchungen(), f"bank:{iban}:"))


def _sk(lauf, iban) -> dict | None:
    return next((k for k in lauf["konten"] if k["iban"] == iban), None)


def _synchronisiert_und_geloescht(api, daten, erw, variante: str = "loeschen") -> tuple[str, dict]:
    """Erster Lauf ab VON, dann Löschen des Girokontos. Rückgabe: (IBAN, Konto vor dem Löschen)."""
    sync(api, von=VON)
    giro = erw["ibans"]["giro"]
    k = konto_nach_iban(api)[giro]
    _loeschen(api, k["id"], variante)
    return giro, k


# ------------------------------------------------------- Status und Überspringen


@pytest.mark.kern
def test_geloeschtes_bankkonto_wird_nicht_still_neu_angelegt(sapi, sd, netz_gesperrt):
    """16.1/16.2 Regel 4: kein leeres Konto mehr, sondern Status konto_fehlt und Überspringen."""
    daten, erw = sd
    giro, alt = _synchronisiert_und_geloescht(sapi, daten, erw)
    z = _zustand(sapi)
    assert set(z) == set(erw["konto_namen"]), "der Eintrag bleibt beim Löschen erhalten"
    assert (z[giro]["status"], z[giro]["wiederherstellen_buchungen"]) == ("konto_fehlt", None)
    assert z[giro]["konto_id"] == alt["id"], "konto_id = zuletzt zugeordnetes Konto"
    for iban in set(z) - {giro}:
        assert (z[iban]["status"], z[iban]["wiederherstellen_buchungen"]) == ("aktiv", None)
    anzahl = len(sapi.alle_buchungen())
    lauf = sync(sapi, von=VON)
    assert lauf["status"] == "erfolgreich" and lauf["fehler"] is None
    assert [k["iban"] for k in lauf["konten"]] == sorted(set(erw["konto_namen"]) - {giro})
    assert lauf["uebersprungen"] == [{"iban": giro, "name": erw["konto_namen"][giro], "status": "konto_fehlt"}]
    assert giro not in konto_nach_iban(sapi), "kein neues Konto für das gelöschte Bankkonto"
    assert len(sapi.alle_buchungen()) == anzahl
    assert all(k["buchungen_neu"] == 0 for k in lauf["konten"])
    assert _zustand(sapi)[giro]["status"] == "konto_fehlt"


@pytest.mark.kern
def test_benachrichtigung_konto_fehlt_entprellt(sapi, sd, netz_gesperrt):
    """16.5: eine ungelesene Benachrichtigung je Bankkonto; die Entscheidung liest sie."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    assert not [b for b in benachrichtigungen(sapi) if b["art"] == "konto_fehlt"], "erst der Lauf fragt"
    sync(sapi, von=VON)
    sync(sapi, von=VON)
    bs = [b for b in benachrichtigungen(sapi) if b["art"] == "konto_fehlt"]
    assert len(bs) == 1, "Entprellung wie synchronisation.md 6"
    b = bs[0]
    assert (b["schluessel"], b["link"], b["gelesen"]) == (f"konto_fehlt:{giro}", "/sync/konten", False)
    assert b["titel"].strip() and giro in b["text"].replace(" ", "")
    _entscheiden(sapi, giro, "ignorieren", "nur_neue")
    assert all(x["gelesen"] for x in benachrichtigungen(sapi) if x["schluessel"] == f"konto_fehlt:{giro}")


def test_ignorieren_ueberspringt_ohne_benachrichtigung(sapi, sd, netz_gesperrt):
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    z = _entscheiden(sapi, giro, "ignorieren", "alle")
    assert (z["iban"], z["status"], z["wiederherstellen_buchungen"]) == (giro, "ignoriert", None)
    lauf = sync(sapi, von=VON)
    assert lauf["status"] == "erfolgreich"
    assert lauf["uebersprungen"] == [{"iban": giro, "name": erw["konto_namen"][giro], "status": "ignoriert"}]
    assert not [b for b in benachrichtigungen(sapi) if b["art"] == "konto_fehlt"]
    assert giro not in konto_nach_iban(sapi)
    # aus „ignoriert“ kann später noch „wiederherstellen“ werden
    z = _entscheiden(sapi, giro, "wiederherstellen", "alle")
    assert (z["status"], z["wiederherstellen_buchungen"]) == ("wiederherstellen", "alle")
    lauf = sync(sapi, von=VON)
    assert lauf["uebersprungen"] == [] and _sk(lauf, giro)["konto_neu"] is True


def test_ohne_geloeschte_konten_uebersprungen_leer(sapi, sd, netz_gesperrt):
    """E-029: Läufe ohne gelöschte Bankkonten verhalten sich wie bisher; uebersprungen ist leer."""
    _, erw = sd
    lauf = sync(sapi, von=VON)
    assert lauf["uebersprungen"] == []
    assert {z["status"] for z in _zustand(sapi).values()} == {"aktiv"}
    assert all(z["wiederherstellen_buchungen"] is None for z in _zustand(sapi).values())
    assert all(k["konto_neu"] for k in lauf["konten"]), "neue IBANs werden weiterhin ohne Rückfrage angelegt"


def test_alle_bankkonten_uebersprungen(sapi, sd, netz_gesperrt):
    daten, erw = sd
    sync(sapi, von=VON)
    for k in konto_nach_iban(sapi).values():
        _loeschen(sapi, k["id"])
    lauf = sync(sapi, von=VON)
    assert lauf["status"] == "erfolgreich" and lauf["konten"] == []
    assert [u["iban"] for u in lauf["uebersprungen"]] == sorted(erw["konto_namen"])
    assert konto_nach_iban(sapi) == {}


def test_delete_und_iban_entfernen_zaehlen_als_fehlend(sapi, sd, netz_gesperrt):
    """E-083 (1): Status konto_fehlt, sobald kein Konto mehr die IBAN trägt – gleich auf welchem Weg."""
    daten, erw = sd
    sync(sapi, von=VON)
    konten = konto_nach_iban(sapi)
    spar = erw["ibans"]["spar"]
    sapi.patch(f"/api/konten/{konten[spar]['id']}", json={"iban": None}, erwartet=200)
    assert _zustand(sapi)[spar]["status"] == "konto_fehlt"
    lauf = sync(sapi, von=VON)
    assert spar in [u["iban"] for u in lauf["uebersprungen"]]
    assert spar not in konto_nach_iban(sapi), "kein zweites Konto neben dem ohne IBAN"
    # IBAN wieder eintragen: aktiv, ohne Entscheidung, das Konto wird wiederverwendet
    sapi.patch(f"/api/konten/{konten[spar]['id']}", json={"iban": spar}, erwartet=200)
    assert _zustand(sapi)[spar]["status"] == "aktiv"
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, spar)
    assert (sk["konto_id"], sk["konto_neu"], sk["buchungen_neu"]) == (konten[spar]["id"], False, 0)


def test_manuell_angelegtes_konto_mit_iban_wird_uebernommen(sapi, sd, netz_gesperrt):
    """16.2 Regel 1: ein neues Konto mit der IBAN beendet den Status konto_fehlt ohne Entscheidung."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    _entscheiden(sapi, giro, "ignorieren", "nur_neue")
    neu = sapi.konto("Mein Giro", "girokonto", iban=giro)
    assert _zustand(sapi)[giro]["status"] == "aktiv"
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, giro)
    assert (sk["konto_id"], sk["konto_neu"]) == (neu["id"], False)
    assert sk["buchungen_vorhanden"] == len(_gebucht(daten, giro)), "Kennungen bleiben ohne Wiederherstellen"
    z = _zustand(sapi)[giro]
    assert (z["konto_id"], z["status"], z["wiederherstellen_buchungen"]) == (neu["id"], "aktiv", None)
    # die Entscheidung „ignorieren“ wurde bei der Zuordnung verworfen
    _loeschen(sapi, neu["id"])
    assert _zustand(sapi)[giro]["status"] == "konto_fehlt"


# ------------------------------------------------------------ Wiederherstellen


@pytest.mark.kern
def test_wiederherstellen_alle_bringt_buchungen_zurueck(sapi, sd, netz_gesperrt):
    """16.2 Regel 3: das beobachtete leere Konto ist behoben – alle gelieferten Umsätze kommen zurück."""
    daten, erw = sd
    giro, alt = _synchronisiert_und_geloescht(sapi, daten, erw)
    assert _kennungen(sapi, giro) == set()
    z = _entscheiden(sapi, giro, "wiederherstellen", "alle")
    assert (z["status"], z["wiederherstellen_buchungen"]) == ("wiederherstellen", "alle")
    assert giro not in konto_nach_iban(sapi), "die Entscheidung legt noch nichts an"
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, giro)
    soll = _gebucht(daten, giro)
    assert len(soll) == erw["anzahl_gebucht"][giro]
    assert (sk["konto_neu"], sk["buchungen_neu"], sk["buchungen_vorhanden"], sk["buchungen_zusammengefuehrt"]) == (
        True, len(soll), 0, 0)
    k = konto_nach_iban(sapi)[giro]
    assert k["id"] != alt["id"] and sk["konto_id"] == k["id"]
    assert (k["name"], k["art"]) == (erw["konto_namen"][giro], alt["art"])
    assert _kennungen(sapi, giro) == {orakel.kennung(u) for u in soll}
    assert sapi.salden()[k["id"]]["saldo"] == erw["saldo_veraenderung"][giro]
    z = _zustand(sapi)[giro]
    assert (z["status"], z["konto_id"], z["wiederherstellen_buchungen"]) == ("aktiv", k["id"], None)
    # andere Bankkonten unberührt, zweiter Lauf ohne Dubletten (T 6)
    assert all(x["buchungen_neu"] == 0 for x in lauf["konten"] if x["iban"] != giro)
    lauf = sync(sapi, von=VON)
    assert _sk(lauf, giro)["buchungen_neu"] == 0 and _sk(lauf, giro)["konto_neu"] is False


@pytest.mark.kern
def test_wiederherstellen_alle_ohne_von_beginnt_beim_erstabruf(sapi, sd, netz_gesperrt):
    """E-081: letzter_abruf_bis wird null, der Abruf beginnt bei heute − sync_erstabruf_tage (90)."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    _entscheiden(sapi, giro, "wiederherstellen", "alle")
    lauf = sync(sapi)
    sk = _sk(lauf, giro)
    erst = (HEUTE - dt.timedelta(days=90)).isoformat()
    assert (sk["von"], sk["bis"]) == (erst, "2024-06-30")
    assert sk["buchungen_neu"] == len(_gebucht(daten, giro, von=erst))
    assert _zustand(sapi)[giro]["letzter_abruf_bis"] == "2024-06-30"


@pytest.mark.kern
def test_wiederherstellen_nur_neue(sapi, sd, netz_gesperrt):
    """16.2 Regel 3, "nur_neue": Konto entsteht, gemerkte Kennungen und Zeitraum bleiben."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    vorher = _zustand(sapi)[giro]["letzter_abruf_bis"]
    _entscheiden(sapi, giro, "wiederherstellen", "nur_neue")
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, giro)
    assert (sk["konto_neu"], sk["buchungen_neu"], sk["buchungen_vorhanden"]) == (True, 0, len(_gebucht(daten, giro)))
    assert _zustand(sapi)[giro]["letzter_abruf_bis"] == vorher == "2024-06-30"


@pytest.mark.kern
def test_umgebuchte_buchungen_werden_nicht_verdoppelt(sapi, sd, netz_gesperrt):
    """E-082: nach Löschen mit "unkategorisiert" existieren die Buchungen weiter; "alle" bucht sie nicht neu."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw, variante="unkategorisiert")
    vorhanden = _kennungen(sapi, giro)
    assert vorhanden == {orakel.kennung(u) for u in _gebucht(daten, giro)}
    anzahl = len(sapi.alle_buchungen())
    _entscheiden(sapi, giro, "wiederherstellen", "alle")
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, giro)
    assert (sk["konto_neu"], sk["buchungen_neu"], sk["buchungen_vorhanden"]) == (True, 0, len(vorhanden))
    assert len(sapi.alle_buchungen()) == anzahl


def test_einzeln_geloeschte_buchung_kommt_mit_alle_zurueck(sapi, sd, netz_gesperrt):
    """E-081: bei "alle" kommen auch früher einzeln gelöschte Buchungen dieses Bankkontos zurück."""
    daten, erw = sd
    sync(sapi, von=VON)
    giro = erw["ibans"]["giro"]
    k = konto_nach_iban(sapi)[giro]
    eine = next(iter(nach_kennung(sapi.alle_buchungen(), f"bank:{giro}:").values()))
    sapi.delete(f"/api/buchungen/{eine['id']}", erwartet=204)
    _loeschen(sapi, k["id"])
    _entscheiden(sapi, giro, "wiederherstellen", "alle")
    lauf = sync(sapi, von=VON)
    assert _sk(lauf, giro)["buchungen_neu"] == len(_gebucht(daten, giro))


def test_entscheidung_ersetzt_fruehere(sapi, sd, netz_gesperrt):
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    _entscheiden(sapi, giro, "wiederherstellen", "alle")
    z = _entscheiden(sapi, giro, "wiederherstellen", "nur_neue")
    assert (z["status"], z["wiederherstellen_buchungen"]) == ("wiederherstellen", "nur_neue")
    z = _entscheiden(sapi, giro, "ignorieren", "alle")
    assert (z["status"], z["wiederherstellen_buchungen"]) == ("ignoriert", None)
    assert _zustand(sapi)[giro] == z


# ----------------------------------------------------------------- Fehlerfälle


@pytest.mark.kern
def test_entscheidung_fehlerfaelle(sapi, sd, netz_gesperrt):
    """16.3 Prüfreihenfolge: 422 vor 404 vor 409; nichts wird geändert."""
    daten, erw = sd
    sync(sapi, von=VON)
    giro, spar = erw["ibans"]["giro"], erw["ibans"]["spar"]
    pfad = f"/api/sync/konten/{giro}/entscheidung"
    for body in ({}, {"aktion": "wiederherstellen"}, {"buchungen": "alle"},
                 {"aktion": "anlegen", "buchungen": "alle"}, {"aktion": "ignorieren", "buchungen": "keine"},
                 {"aktion": "wiederherstellen", "buchungen": "alle", "extra": 1},
                 {"aktion": 1, "buchungen": "alle"}):
        assert fehlercode(sapi.post(pfad, json=body, erwartet=422)) == "validierung", body
    assert fehlercode(sapi.post(f"/api/sync/konten/{erw['ibans']['fremd']}/entscheidung",
                                json={"aktion": "ignorieren", "buchungen": "alle"}, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(sapi.post(f"/api/sync/konten/{erw['ibans']['fremd']}/entscheidung",
                                json={"aktion": "x"}, erwartet=422)) == "validierung", "422 vor 404"
    assert fehlercode(_entscheiden(sapi, giro, "ignorieren", "alle", erwartet=409)) == "konto_vorhanden"
    assert _zustand(sapi)[giro]["status"] == "aktiv"
    # IBAN im Pfad wird normalisiert
    _loeschen(sapi, konto_nach_iban(sapi)[spar]["id"])
    z = _entscheiden(sapi, spar.lower(), "ignorieren", "nur_neue")
    assert (z["iban"], z["status"]) == (spar, "ignoriert")


def test_entscheidung_ist_nicht_protokolliert(sapi, sd, netz_gesperrt):
    """E-083 (4): die Entscheidung ändert keinen Buchbestand und erzeugt keine Änderung."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    vor = letzte_aenderung_id(sapi)
    _entscheiden(sapi, giro, "wiederherstellen", "alle")
    _entscheiden(sapi, giro, "ignorieren", "alle")
    assert aenderungen_seit(sapi, vor) == []


# ----------------------------------------------------------- Protokoll und Rückgängig


@pytest.mark.kern
def test_rueckgaengig_der_wiederherstellung(sapi, sd, netz_gesperrt):
    """protokoll.md 6.1 Schritt 4 und 6.4: vergessene Kennungen werden wieder gemerkt, die Frage ist wieder offen."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    anzahl = len(sapi.alle_buchungen())
    _entscheiden(sapi, giro, "wiederherstellen", "alle")
    vor = letzte_aenderung_id(sapi)
    lauf = sync(sapi, von=VON)
    neu = aenderungen_seit(sapi, vor)
    zuordnung = [a for a in neu if a["aktion"] == "sync_kontozuordnung"]
    assert len(zuordnung) == 1 and zuordnung[0]["gruppe"] == f"sync:{lauf['id']}"
    k = konto_nach_iban(sapi)[giro]
    assert [(e["objekt"], e["objekt_id"], e["art"]) for e in zuordnung[0]["eintraege"]] == [
        ("konto", k["id"], "angelegt")]
    rueckgaengig_gruppe = sapi.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"sync:{lauf['id']}"},
                                    erwartet=200).daten
    assert rueckgaengig_gruppe["quelle"] == "rueckgaengig"
    assert giro not in konto_nach_iban(sapi) and len(sapi.alle_buchungen()) == anzahl
    z = _zustand(sapi)[giro]
    assert (z["status"], z["wiederherstellen_buchungen"]) == ("konto_fehlt", None), "die Frage ist wieder offen"
    # die beim Wiederherstellen vergessenen Kennungen sind wieder gemerkt: "nur_neue" bucht nichts
    _entscheiden(sapi, giro, "wiederherstellen", "nur_neue")
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, giro)
    assert (sk["konto_neu"], sk["buchungen_neu"], sk["buchungen_vorhanden"]) == (True, 0, len(_gebucht(daten, giro)))


def test_rueckgaengig_des_loeschens_macht_aktiv(sapi, sd, netz_gesperrt):
    """Rückgängig des Löschens stellt das Konto her; der Status ist wieder aktiv, der Lauf übernimmt es."""
    daten, erw = sd
    giro, alt = _synchronisiert_und_geloescht(sapi, daten, erw)
    loesch = [a for a in alle_aenderungen(sapi) if a["aktion"] == "konto_loeschen_mit_buchungen"]
    assert len(loesch) == 1
    rueckgaengig(sapi, loesch[0]["id"])
    assert _zustand(sapi)[giro]["status"] == "aktiv"
    lauf = sync(sapi, von=VON)
    sk = _sk(lauf, giro)
    assert (sk["konto_id"], sk["konto_neu"], sk["buchungen_neu"]) == (alt["id"], False, 0)


def test_anderes_rueckgaengig_entfernt_eintrag_nicht(sapi, sd, netz_gesperrt):
    """protokoll.md 6.4: ein Eintrag entfällt nicht, nur weil sein Konto aus anderem Grund fehlt."""
    daten, erw = sd
    giro, _ = _synchronisiert_und_geloescht(sapi, daten, erw)
    vor = letzte_aenderung_id(sapi)
    sapi.tag("Irgendwas")
    (a,) = aenderungen_seit(sapi, vor)
    rueckgaengig(sapi, a["id"])
    assert _zustand(sapi)[giro]["status"] == "konto_fehlt"
