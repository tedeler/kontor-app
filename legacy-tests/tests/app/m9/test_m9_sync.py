"""M9: Sicherung und Synchronisation (sicherung.md 2.1, 5.1 Schritt 5, 6, 7; protokoll.md 10.2; E-087, E-092).

Gemerkte Kennungen und Zustand je Bankkonto gehören zur Sicherung. Erwartete Kennungen kommen aus der
Mock-Datendatei (``sync_daten.json``) über ``tests/hilfen/sync_orakel``, nie aus Ausgaben der Anwendung.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.hilfen import sync_orakel as orakel
from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import konto_nach_iban, lade_sync, mock_api, nach_kennung, sync, tans
from tests.hilfen.m3 import rueckgaengig
from tests.hilfen.m9 import aenderungsanzahl, bestand, einspielen, lesezustand, oeffne, sicherung, sync_konten

pytestmark = pytest.mark.kern

VON = "2024-01-01"
MITTE = "2024-03-31"
ENDE = "2024-06-30"


def _zeit(api, tag: str) -> None:
    api.put("/api/mock/zeit", json={"jetzt": f"{tag}T12:00:00Z"}, erwartet=200)


def _soll_kennungen(daten, bis: str) -> set[str]:
    aus = set()
    for k in daten["bank"]["konten"]:
        for u in orakel.im_zeitraum(daten["bank"]["umsaetze"], k["iban"], dt.date.fromisoformat(VON),
                                    dt.date.fromisoformat(bis), dt.date.fromisoformat(bis)):
            if not u["vormerkung"]:
                aus.add(orakel.kennung(u))
    return aus


@pytest.fixture
def lage(tmp_path, netz_gesperrt):
    """Mock-App: erster Lauf bis MITTE, Sicherung S0, zweiter Lauf bis ENDE."""
    daten, _ = lade_sync()
    api = mock_api(tmp_path, heute=MITTE)
    sync(api, von=VON)
    assert set(nach_kennung(api.alle_buchungen())) == _soll_kennungen(daten, MITTE)
    s0 = sicherung(api)
    z0 = lesezustand(api, vorlagen=False)
    _zeit(api, ENDE)
    sync(api)
    assert set(nach_kennung(api.alle_buchungen())) == _soll_kennungen(daten, ENDE)
    return api, daten, s0, z0


def test_aeltere_sicherung_dann_abruf_genau_einmal(lage):
    """7/T 6: Nach dem Einspielen von S0 holt der Abruf die späteren Umsätze genau einmal wieder."""
    api, daten, s0, z0 = lage
    assert _soll_kennungen(daten, ENDE) > _soll_kennungen(daten, MITTE), "Testdaten: zweiter Lauf bringt Neues"
    e = einspielen(api, s0).daten
    assert e["geaendert"] is True
    assert lesezustand(api, vorlagen=False) == z0, "Buchbestand und /api/sync/konten wie beim Erstellen"
    lauf = sync(api)
    assert lauf["status"] == "erfolgreich"
    assert set(nach_kennung(api.alle_buchungen())) == _soll_kennungen(daten, ENDE), (
        "fehlende Umsätze werden nachgeholt, keine Dublette (nach_kennung prüft Eindeutigkeit)")
    assert sum(k["buchungen_neu"] for k in lauf["konten"]) == len(_soll_kennungen(daten, ENDE)
                                                                  - _soll_kennungen(daten, MITTE))
    assert all(k["buchungen_neu"] == 0 for k in sync(api)["konten"]), "zweiter Abruf ohne Neues"


def test_sync_konten_aus_der_sicherung(lage):
    """2.1 Punkt 3: letzter_abruf_bis und letzter_erfolg_am kommen aus der Sicherung."""
    api, _, s0, z0 = lage
    vorher = sync_konten(api)
    assert vorher != z0["sync_konten"]
    assert {z["letzter_abruf_bis"] for z in z0["sync_konten"]} == {MITTE}
    einspielen(api, s0)
    assert sync_konten(api) == z0["sync_konten"]


def test_rueckgaengig_stellt_kennungen_und_sync_zustand_her(lage):
    """6/protokoll.md 10.2: Rückgängig des Einspielens stellt auch Kennungen und Bankkonto-Zustand her."""
    api, daten, s0, z0 = lage
    vorher = lesezustand(api, vorlagen=False)
    aid = einspielen(api, s0).daten["aenderung_id"]
    u = rueckgaengig(api, aid).daten
    assert lesezustand(api, vorlagen=False) == vorher
    lauf = sync(api)
    assert all(k["buchungen_neu"] == 0 for k in lauf["konten"]), (
        "nach Rückgängig sind die Kennungen von vor dem Einspielen wieder gemerkt")
    assert set(nach_kennung(api.alle_buchungen())) == _soll_kennungen(daten, ENDE)
    # Wiederholen: wieder Zustand der Sicherung (der Lauf eben hat nichts geändert)
    vor_wdh_konten = sync_konten(api)
    assert vor_wdh_konten != z0["sync_konten"]
    rueckgaengig(api, u["id"])
    assert lesezustand(api, vorlagen=False) == z0


def test_in_neue_instanz_und_weiter_synchronisieren(lage, tmp_path):
    """Sicherung einer Instanz in eine neue Instanz derselben Mock-Daten: dort genauso weiter."""
    api, daten, s0, z0 = lage
    b = mock_api(tmp_path / "b", heute=ENDE)
    einspielen(b, s0)
    assert lesezustand(b, vorlagen=False) == z0
    sync(b)
    assert set(nach_kennung(b.alle_buchungen())) == _soll_kennungen(daten, ENDE)


def test_entscheidung_fuer_geloeschtes_bankkonto_gesichert(lage, tmp_path):
    """2.1 Punkt 3: Die gespeicherte Entscheidung (synchronisation.md 16.3) gehört zur Sicherung."""
    api, daten, _, _ = lage
    iban, k = sorted(konto_nach_iban(api).items())[0]
    api.post(f"/api/konten/{k['id']}/loeschen", json={"buchungen": "loeschen", "konflikte": "behalten"},
             erwartet=200)
    api.post(f"/api/sync/konten/{iban}/entscheidung", json={"aktion": "ignorieren", "buchungen": "alle"},
             erwartet=200)
    soll = sync_konten(api)
    assert next(z for z in soll if z["iban"] == iban)["status"] == "ignoriert"
    b = mock_api(tmp_path / "b", heute=ENDE)
    einspielen(b, sicherung(api))
    assert sync_konten(b) == soll
    name = next(x["name"] for x in daten["bank"]["konten"] if x["iban"] == iban).strip()
    assert sync(b)["uebersprungen"] == [{"iban": iban, "name": name, "status": "ignoriert"}]


def test_sperre_bei_tan(tmp_path, netz_gesperrt):
    """5.1 Schritt 5/E-092: Während ein Lauf auf eine TAN wartet, wird nicht eingespielt; Probelauf geht."""
    quelle = mock_api(tmp_path / "q")
    sync(quelle, von=VON)
    daten = sicherung(quelle)
    api = mock_api(tmp_path / "t", szenario="tan_erforderlich")
    lauf = sync(api, von=VON)
    assert lauf["status"] == "wartet_auf_tan"
    vorher, n = bestand(api, vorlagen=False), aenderungsanzahl(api)
    r = einspielen(api, daten, erwartet=409)
    assert fehlercode(r) == "tan_ausstehend"
    assert bestand(api, vorlagen=False) == vorher and aenderungsanzahl(api) == n
    assert einspielen(api, daten, trocken=True).daten["geaendert"] is True
    # Reihenfolge 5.1: fehlende Bestätigung vor der Sperre
    assert fehlercode(einspielen(api, daten, bestaetigt=False, erwartet=409)) == "bestaetigung_erforderlich"
    t = tans(api)[0]
    api.post(f"/api/tan-anforderungen/{t['id']}/abbrechen", erwartet=200)
    e = einspielen(api, daten).daten
    assert e["geaendert"] is True
    assert oeffne(sicherung(api))[0]["inhalt_sha256"] == oeffne(daten)[0]["inhalt_sha256"]
