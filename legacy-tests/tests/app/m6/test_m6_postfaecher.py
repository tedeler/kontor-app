"""M6: Postfächer als protokolliertes Objekt, Status, Sicherung (mail.md 2, protokoll.md 12, sicherung.md 2.6)."""

from __future__ import annotations


import pytest

from tests.hilfen.api import Api, fehlercode, neue_config
from tests.hilfen.m3 import letzte_aenderung_id
from tests.hilfen.m6 import EINS, ZWEI, bestand, eine_aenderung, postfach, postfach_status, pruefe_eintraege, rundreise
from tests.hilfen.m9 import einspielen, inhalt_sha256, oeffne, sicherung

OBJEKTE_M9 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]


@pytest.mark.kern
def test_anlegen_mit_vorgaben_und_lesen(api):
    p = postfach(api, EINS)
    assert p == {"id": p["id"], "adresse": EINS, "bezeichnung": "", "ordner": "INBOX", "absender_filter": [],
                 "aktiv": True}
    q = postfach(api, ZWEI, bezeichnung="Zweites (fiktiv)", ordner="Bestellungen/Bücher",
                 absender_filter=["buecherstube", "bezahldienst"], aktiv=False)
    assert api.get(f"/api/mail/postfaecher/{q['id']}", erwartet=200).daten == q
    assert api.get("/api/mail/postfaecher", erwartet=200).daten == [p, q]
    assert fehlercode(api.get("/api/mail/postfaecher/999", erwartet=404)) == "nicht_gefunden"


@pytest.mark.kern
@pytest.mark.parametrize("koerper", [
    {}, {"adresse": "ohne-at"}, {"adresse": "a@b@example.invalid"}, {"adresse": "@example.invalid"},
    {"adresse": "leer @example.invalid"}, {"adresse": "x" * 250 + "@e.de"}, {"adresse": EINS, "ordner": ""},
    {"adresse": EINS, "absender_filter": ["a", "a"]}, {"adresse": EINS, "absender_filter": [""]},
    {"adresse": EINS, "aktiv": "ja"}, {"adresse": EINS, "unbekannt": 1}, {"adresse": EINS, "bezeichnung": "b" * 201},
    {"adresse": EINS, "absender_filter": ["f"] * 51},
])
def test_validierung(api, koerper):
    assert fehlercode(api.post("/api/mail/postfaecher", json=koerper, erwartet=422)) == "validierung"
    assert api.get("/api/mail/postfaecher", erwartet=200).daten == []


@pytest.mark.kern
def test_adresse_eindeutig_und_unveraenderlich(api):
    p = postfach(api, EINS)
    r = api.post("/api/mail/postfaecher", json={"adresse": EINS.upper()}, erwartet=409)
    assert fehlercode(r) == "postfach_existiert"
    assert fehlercode(api.patch(f"/api/mail/postfaecher/{p['id']}", json={"adresse": ZWEI},
                                erwartet=422)) == "validierung"
    neu = api.patch(f"/api/mail/postfaecher/{p['id']}", json={"aktiv": False, "absender_filter": ["shop"]},
                    erwartet=200).daten
    assert neu == {**p, "aktiv": False, "absender_filter": ["shop"]}
    assert fehlercode(api.patch("/api/mail/postfaecher/999", json={"aktiv": False}, erwartet=404)) == "nicht_gefunden"


@pytest.mark.kern
def test_status_echt_und_mock(api, mock_api):
    p = postfach(api, EINS)
    s = postfach_status(api, p["id"])
    assert s == {"postfach_id": p["id"], "anmeldung": "fehlt", "anmeldung_nr": 0, "angemeldet_am": None,
                 "laeuft_ab_am": None, "letzter_abruf_am": None, "letzter_erfolg_am": None, "letzter_fehler": None,
                 "nachrichten": 0}
    m = postfach(mock_api, EINS)
    assert postfach_status(mock_api, m["id"])["anmeldung"] == "nicht_erforderlich"
    assert fehlercode(mock_api.post(f"/api/mail/postfaecher/{m['id']}/anmeldung", erwartet=409)) == "nur_echtmodus"
    assert fehlercode(mock_api.delete(f"/api/mail/postfaecher/{m['id']}/anmeldung", erwartet=409)) == "nur_echtmodus"


@pytest.mark.kern
def test_protokoll_und_rueckgaengig(api):
    v0, a0 = bestand(api), letzte_aenderung_id(api)
    p = postfach(api, EINS)
    v1 = bestand(api)
    a = eine_aenderung(api, a0, "postfach_anlegen")
    pruefe_eintraege(a, v0, v1)
    rundreise(api, a, v0, v1)
    a1 = letzte_aenderung_id(api)
    api.patch(f"/api/mail/postfaecher/{p['id']}", json={"aktiv": True}, erwartet=200)
    assert letzte_aenderung_id(api) == a1, "ohne Wirkung keine Änderung"
    api.patch(f"/api/mail/postfaecher/{p['id']}", json={"ordner": "Archiv"}, erwartet=200)
    v2 = bestand(api)
    a = eine_aenderung(api, a1, "postfach_aendern")
    pruefe_eintraege(a, v1, v2)
    rundreise(api, a, v1, v2)
    a2 = letzte_aenderung_id(api)
    api.delete(f"/api/mail/postfaecher/{p['id']}", erwartet=204)
    v3 = bestand(api)
    a = eine_aenderung(api, a2, "postfach_loeschen")
    pruefe_eintraege(a, v2, v3)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == v2 and postfach_status(api, p["id"])["anmeldung"] == "fehlt"


@pytest.mark.kern
def test_rueckgaengig_mit_doppelter_adresse_scheitert(api):
    p = postfach(api, EINS)
    a0 = letzte_aenderung_id(api)
    api.delete(f"/api/mail/postfaecher/{p['id']}", erwartet=204)
    loeschen = letzte_aenderung_id(api)
    assert loeschen > a0
    postfach(api, EINS.upper())
    r = api.post(f"/api/aenderungen/{loeschen}/rueckgaengig", erwartet=409)
    assert fehlercode(r) == "rueckgaengig_konflikt"


@pytest.mark.kern
def test_sicherung_ohne_postfaecher_wie_m9(api):
    api.konto("Girokonto")
    m, _ = oeffne(sicherung(api))
    assert set(m["anzahl"]) == set(OBJEKTE_M9), "ohne Postfächer kein Schlüssel postfach (E-118)"


@pytest.mark.kern
def test_sicherung_mit_postfaechern_und_rundreise(tmp_path):
    a = Api(neue_config(tmp_path / "a"))
    p1 = postfach(a, EINS, absender_filter=["buecherstube"])
    p2 = postfach(a, ZWEI, ordner="Bestellungen/Bücher", aktiv=False)
    m, _ = oeffne(sicherung(a))
    assert set(m["anzahl"]) == set(OBJEKTE_M9) | {"postfach"} and m["anzahl"]["postfach"] == 2
    b0 = bestand(a)
    inhalt = {o: [b0[k] for k in sorted(k for k in b0 if k[0] == o)] for o in OBJEKTE_M9 + ["postfach"]}
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt)
    b = Api(neue_config(tmp_path / "b"))
    e = einspielen(b, sicherung(a)).daten
    assert e["unterschied"]["postfach"] == {"angelegt": 2, "geaendert": 0, "geloescht": 0}
    assert b.get("/api/mail/postfaecher", erwartet=200).daten == [p1, p2]
    assert postfach_status(b, p1["id"])["anmeldung"] == "fehlt"
    api3 = postfach(b, "drei@example.invalid")
    assert api3["id"] > p2["id"], "ID-Zähler der Postfächer übernommen"
    u = b.post(f"/api/aenderungen/{e['aenderung_id']}/rueckgaengig", erwartet=200).daten
    assert u["quelle"] == "rueckgaengig"
    assert [p["adresse"] for p in b.get("/api/mail/postfaecher", erwartet=200).daten] == ["drei@example.invalid"]
