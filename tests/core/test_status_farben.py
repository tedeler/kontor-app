"""Core-Tests zum Feature status-farben (D-255): Eine von Hand zugeordnete Buchung ist „Vorläufig“."""

from __future__ import annotations

import pytest


def _konto(client, name: str, art: str) -> int:
    r = client.post("/api/konten", json={"name": name, "art": art})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def buch(client):
    k = {"giro": _konto(client, "Giro", "girokonto"), "spar": _konto(client, "Sparbuch", "sparkonto"),
         "alt": _konto(client, "Sonstiges", "aufwand"), "lm": _konto(client, "Lebensmittel", "aufwand"),
         "cafe": _konto(client, "Café", "aufwand")}

    def neu(status: str = "importiert", betrag: int = -1250) -> int:
        r = client.post("/api/buchungen", json={"datum": "2024-03-01", "status": status, "splits": [
            {"konto_id": k["giro"], "betrag": betrag}, {"konto_id": k["alt"], "betrag": -betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    return client, k, neu


def _status(client, bid: int) -> str:
    return client.get(f"/api/buchungen/{bid}").json()["status"]


def test_zuordnung_von_hand_macht_vorlaeufig(buch):
    client, k, neu = buch
    bid = neu()
    r = client.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": k["lm"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "vorlaeufig"

    # Rückgängig stellt Kategorie und Status zusammen wieder her.
    letzte = client.get("/api/aenderungen").json()["eintraege"][0]
    assert client.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    b = client.get(f"/api/buchungen/{bid}").json()
    assert b["status"] == "importiert" and {s["konto_id"] for s in b["splits"]} == {k["giro"], k["alt"]}


def test_bestaetigt_und_vorlaeufig_bleiben(buch):
    client, k, neu = buch
    for status in ("bestaetigt", "vorlaeufig"):
        bid = neu(status)
        assert client.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": k["lm"]}).status_code == 200
        assert _status(client, bid) == status


def test_mehrfach_zuordnen(buch):
    client, k, neu = buch
    a, b, c = neu(), neu(), neu("bestaetigt")
    r = client.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [a, b, c], "kategorie_id": k["cafe"]})
    assert r.status_code == 200, r.text
    assert [_status(client, x) for x in (a, b, c)] == ["vorlaeufig", "vorlaeufig", "bestaetigt"]


def test_zuordnung_auf_bestandskonto(buch):
    """Auch die Umbuchung (Ziel ist ein Bestandskonto) ist eine Zuordnung von Hand."""
    client, k, neu = buch
    bid = neu()
    assert client.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": k["spar"]}).status_code == 200
    assert _status(client, bid) == "vorlaeufig"


def test_splits_von_hand(buch):
    client, k, neu = buch
    bid = neu()
    r = client.put(f"/api/buchungen/{bid}/splits", json={"splits": [
        {"konto_id": k["giro"], "betrag": -1250}, {"konto_id": k["lm"], "betrag": 1000},
        {"konto_id": k["cafe"], "betrag": 250}]})
    assert r.status_code == 200, r.text
    assert _status(client, bid) == "vorlaeufig"


def test_vorschlag_erst_beim_annehmen(buch):
    """Ein offener Vorschlag der Regel ist noch keine Zuordnung; Annehmen macht vorläufig, Ablehnen nicht."""
    client, k, neu = buch
    a, b = neu(), neu()
    r = client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"], "ausdruck": "betrag > 0"})
    assert r.status_code == 201, r.text
    r = client.post("/api/regeln/anwenden", json={"buchung_ids": [a, b], "nur_unkategorisiert": False})
    assert r.status_code == 200, r.text
    for x in (a, b):
        z = client.get(f"/api/buchungen/{x}").json()
        assert z["vorschlag"] is not None and z["status"] == "importiert"

    assert client.post(f"/api/buchungen/{a}/vorschlag", json={"aktion": "annehmen"}).status_code == 200
    assert client.post(f"/api/buchungen/{b}/vorschlag", json={"aktion": "ablehnen"}).status_code == 200
    assert (_status(client, a), _status(client, b)) == ("vorlaeufig", "importiert")


def test_vorschlaege_mehrfach_annehmen(buch):
    client, k, neu = buch
    a, b = neu(), neu()
    assert client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"],
                                            "ausdruck": "betrag > 0"}).status_code == 201
    assert client.post("/api/regeln/anwenden", json={"buchung_ids": [a, b],
                                                     "nur_unkategorisiert": False}).status_code == 200
    r = client.post("/api/buchungen/mehrfach/vorschlag", json={"buchung_ids": [a, b], "aktion": "annehmen"})
    assert r.status_code == 200, r.text
    assert (_status(client, a), _status(client, b)) == ("vorlaeufig", "vorlaeufig")


def test_vorlaeufig_laesst_sich_bestaetigen(buch):
    """Der Übergang vorläufig → bestätigt ist zulässig (einzeln und mehrfach); zurück nach importiert nicht."""
    client, k, neu = buch
    a, b = neu(), neu()
    for x in (a, b):
        assert client.put(f"/api/buchungen/{x}/kategorie", json={"kategorie_id": k["lm"]}).status_code == 200
    r = client.patch(f"/api/buchungen/{a}", json={"status": "bestaetigt"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "bestaetigt"
    r = client.patch(f"/api/buchungen/{b}", json={"status": "importiert"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "status_uebergang_unzulaessig"
    assert client.post("/api/buchungen/mehrfach/aendern",
                       json={"buchung_ids": [b], "status": "bestaetigt"}).status_code == 200
    assert _status(client, b) == "bestaetigt"


def test_altbestand_wird_einmalig_umgestellt(buch, config):
    """Datenbank aus einer früheren Fassung: importierte Buchungen mit Zuordnung werden beim Öffnen vorläufig,
    solche mit offenem Vorschlag und bestätigte nicht; ein zweites Öffnen ändert nichts mehr."""
    from kontor import db

    client, k, neu = buch
    zugeordnet, mit_vorschlag, bestaetigt = neu(), neu(), neu("bestaetigt")
    assert client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"],
                                            "ausdruck": "betrag > 0"}).status_code == 201
    assert client.post("/api/regeln/anwenden", json={"buchung_ids": [mit_vorschlag],
                                                     "nur_unkategorisiert": False}).status_code == 200
    con = db.verbinde(config.datenbank)
    con.execute("DELETE FROM meta WHERE schluessel = 'status_vorlaeufig'")
    con.close()

    db.schema_anlegen(config.datenbank)
    assert [_status(client, x) for x in (zugeordnet, mit_vorschlag, bestaetigt)] == [
        "vorlaeufig", "importiert", "bestaetigt"]

    spaeter = neu()
    db.schema_anlegen(config.datenbank)
    assert _status(client, spaeter) == "importiert"
