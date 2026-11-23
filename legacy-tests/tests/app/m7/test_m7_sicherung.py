"""M7: Anmeldedaten sind Betriebszustand – nicht in Protokoll und Sicherung (sicherung.md 9, protokoll.md 13,
E-135)."""

from __future__ import annotations

import pytest

from tests.hilfen.api import Api, neue_config
from tests.hilfen.m7 import (NEUES_PASSWORT, PASSWORT, anmelden, angemeldet, m7_api, sitzungstoken,
                             zweiter_client)
from tests.hilfen.m9 import aenderungsanzahl, einspielen, enthaelt, inhalt, inhalt_sha256, oeffne, sicherung
from tests.hilfen.pfade import KMY

OBJEKTARTEN_M9 = {"konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"}


@pytest.mark.kern
def test_anmeldedaten_nicht_in_der_sicherung(tmp_path):
    api = angemeldet(tmp_path)
    api.import_kmy(KMY / "minimal.kmy", erwartet=200)
    zweiter = zweiter_client(api)
    anmelden(zweiter)
    daten = sicherung(api)
    m, db = oeffne(daten)
    assert set(m["anzahl"]) == OBJEKTARTEN_M9, "keine neue Objektart durch M7"
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt(api))
    for geheim in (PASSWORT, sitzungstoken(api), sitzungstoken(zweiter), api.csrf, zweiter.csrf, "scrypt$"):
        assert not enthaelt(daten, geheim), f"Anmeldedaten in der Sicherung: {geheim[:7]}…"


@pytest.mark.kern
def test_einspielen_laesst_anmeldung_unveraendert(tmp_path):
    quelle = Api(neue_config(tmp_path / "q"))
    quelle.import_kmy(KMY / "minimal.kmy", erwartet=200)
    daten = sicherung(quelle)
    ziel = angemeldet(tmp_path / "z")
    ziel.konto("Wird ersetzt")
    andere = zweiter_client(ziel)
    anmelden(andere)
    e = einspielen(ziel, daten).daten
    assert e["geaendert"] is True
    assert inhalt(ziel) == inhalt(quelle)
    ziel.get("/api/konten", erwartet=200)
    andere.get("/api/konten", erwartet=200)
    st = ziel.get("/api/anmeldung", erwartet=200).daten
    assert st["angemeldet"] and st["eingerichtet"]
    anmelden(zweiter_client(ziel), PASSWORT)
    # Rückgängig des Einspielens berührt die Anmeldung ebenso wenig
    ziel.post(f"/api/aenderungen/{e['aenderung_id']}/rueckgaengig", erwartet=200)
    ziel.get("/api/konten", erwartet=200)


@pytest.mark.kern
def test_anmeldevorgaenge_nicht_im_protokoll(tmp_path):
    api = m7_api(tmp_path, anmeldung_fehlversuche=10)
    anmelden(api)
    vorher = aenderungsanzahl(api)
    anmelden(zweiter_client(api), "Falsch-Falsch-Falsch", erwartet=401)
    b = zweiter_client(api)
    anmelden(b)
    b.post("/api/anmeldung/abmelden", erwartet=204)
    api.put("/api/anmeldung/passwort", json={"altes_passwort": PASSWORT, "neues_passwort": NEUES_PASSWORT},
            erwartet=200)
    api.get("/api/gesundheit", erwartet=200)
    api.post("/api/konten", json={"name": "ohne Token", "art": "girokonto"}, headers={"X-Kontor-CSRF": "falsch"},
             erwartet=403)
    assert aenderungsanzahl(api) == vorher
