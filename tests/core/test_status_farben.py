"""Core-Tests zum Feature status-farben (D-259): Automatisch zugeordnet ist „Vorläufig“, von Hand „Bestätigt“."""

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


def test_zuordnung_von_hand_bestaetigt(buch):
    client, k, neu = buch
    bid = neu()
    r = client.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": k["lm"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "bestaetigt"

    # Rückgängig stellt Kategorie und Status zusammen wieder her.
    letzte = client.get("/api/aenderungen").json()["eintraege"][0]
    assert client.post(f"/api/aenderungen/{letzte['id']}/rueckgaengig").status_code == 200
    b = client.get(f"/api/buchungen/{bid}").json()
    assert b["status"] == "importiert" and {s["konto_id"] for s in b["splits"]} == {k["giro"], k["alt"]}


def test_vorlaeufig_wird_von_hand_bestaetigt_und_bestaetigt_bleibt(buch):
    client, k, neu = buch
    for status in ("bestaetigt", "vorlaeufig"):
        bid = neu(status)
        assert client.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": k["lm"]}).status_code == 200
        assert _status(client, bid) == "bestaetigt"


def test_mehrfach_zuordnen(buch):
    client, k, neu = buch
    a, b, c = neu(), neu(), neu("bestaetigt")
    r = client.post("/api/buchungen/mehrfach/kategorie", json={"buchung_ids": [a, b, c], "kategorie_id": k["cafe"]})
    assert r.status_code == 200, r.text
    assert [_status(client, x) for x in (a, b, c)] == ["bestaetigt", "bestaetigt", "bestaetigt"]


def test_zuordnung_auf_bestandskonto(buch):
    """Auch die Umbuchung (Ziel ist ein Bestandskonto) ist eine Zuordnung von Hand."""
    client, k, neu = buch
    bid = neu()
    assert client.put(f"/api/buchungen/{bid}/kategorie", json={"kategorie_id": k["spar"]}).status_code == 200
    assert _status(client, bid) == "bestaetigt"


def test_splits_von_hand(buch):
    client, k, neu = buch
    bid = neu()
    r = client.put(f"/api/buchungen/{bid}/splits", json={"splits": [
        {"konto_id": k["giro"], "betrag": -1250}, {"konto_id": k["lm"], "betrag": 1000},
        {"konto_id": k["cafe"], "betrag": 250}]})
    assert r.status_code == 200, r.text
    assert _status(client, bid) == "bestaetigt"


def test_vorschlag_macht_vorlaeufig_annehmen_bestaetigt(buch):
    """Der Vorschlag einer Regel ist eine automatische Zuordnung: vorläufig. Annehmen bestätigt; Ablehnen nimmt die
    Zuordnung zurück, die Buchung ist wieder so importiert wie vorher."""
    client, k, neu = buch
    a, b, fest = neu(), neu(), neu("bestaetigt")
    r = client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"], "ausdruck": "betrag > 0"})
    assert r.status_code == 201, r.text
    r = client.post("/api/regeln/anwenden", json={"buchung_ids": [a, b, fest], "nur_unkategorisiert": False})
    assert r.status_code == 200, r.text
    for x in (a, b):
        z = client.get(f"/api/buchungen/{x}").json()
        assert z["vorschlag"] is not None and z["status"] == "vorlaeufig"
    assert _status(client, fest) == "bestaetigt"

    assert client.post(f"/api/buchungen/{a}/vorschlag", json={"aktion": "annehmen"}).status_code == 200
    assert client.post(f"/api/buchungen/{b}/vorschlag", json={"aktion": "ablehnen"}).status_code == 200
    assert (_status(client, a), _status(client, b)) == ("bestaetigt", "importiert")


def test_vorschlaege_mehrfach_annehmen(buch):
    client, k, neu = buch
    a, b = neu(), neu()
    assert client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"],
                                            "ausdruck": "betrag > 0"}).status_code == 201
    assert client.post("/api/regeln/anwenden", json={"buchung_ids": [a, b],
                                                     "nur_unkategorisiert": False}).status_code == 200
    r = client.post("/api/buchungen/mehrfach/vorschlag", json={"buchung_ids": [a, b], "aktion": "annehmen"})
    assert r.status_code == 200, r.text
    assert (_status(client, a), _status(client, b)) == ("bestaetigt", "bestaetigt")


def test_bestaetigen_mit_vorschlag_nimmt_ihn(buch):
    """Bestätigen einer Buchung mit offenem Vorschlag übernimmt dessen Kategorie."""
    client, k, neu = buch
    a = neu()
    assert client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"],
                                            "ausdruck": "betrag > 0"}).status_code == 201
    assert client.post("/api/regeln/anwenden", json={"buchung_ids": [a],
                                                     "nur_unkategorisiert": False}).status_code == 200
    assert client.post("/api/buchungen/mehrfach/aendern",
                       json={"buchung_ids": [a], "status": "bestaetigt"}).status_code == 200
    z = client.get(f"/api/buchungen/{a}").json()
    assert z["status"] == "bestaetigt" and z["vorschlag"] is None and z["kategorie_id"] == k["lm"]


def test_vorlaeufig_laesst_sich_bestaetigen(buch):
    """Der Übergang vorläufig → bestätigt ist zulässig; zurück nach importiert nicht."""
    client, k, neu = buch
    a, b = neu("vorlaeufig"), neu("vorlaeufig")
    r = client.patch(f"/api/buchungen/{a}", json={"status": "bestaetigt"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "bestaetigt"
    r = client.patch(f"/api/buchungen/{b}", json={"status": "importiert"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "status_uebergang_unzulaessig"


def test_altbestand_wird_einmalig_umgestellt(buch, config):
    """Datenbank aus einer früheren Fassung: importierte Buchungen mit Zuordnung (auch mit offenem Vorschlag) werden
    beim Öffnen vorläufig, bestätigte nicht; ein zweites Öffnen ändert nichts mehr."""
    from kontor import db

    client, k, neu = buch
    zugeordnet, mit_vorschlag, bestaetigt = neu(), neu(), neu("bestaetigt")
    assert client.post("/api/regeln", json={"name": "Alles", "kategorie_id": k["lm"],
                                            "ausdruck": "betrag > 0"}).status_code == 201
    assert client.post("/api/regeln/anwenden", json={"buchung_ids": [mit_vorschlag],
                                                     "nur_unkategorisiert": False}).status_code == 200
    con = db.verbinde(config.datenbank)
    con.execute("DELETE FROM meta WHERE schluessel = 'status_farben'")
    con.execute("UPDATE buchung SET status = 'importiert' WHERE id = ?", (mit_vorschlag,))   # Stand vor D-259
    con.close()

    db.schema_anlegen(config.datenbank)
    assert [_status(client, x) for x in (zugeordnet, mit_vorschlag, bestaetigt)] == [
        "vorlaeufig", "vorlaeufig", "bestaetigt"]

    spaeter = neu()
    db.schema_anlegen(config.datenbank)
    assert _status(client, spaeter) == "importiert"


def test_bestaetigungs_tags_heissen_name_bestaetigt(buch, config):
    """D-260: Das Tag der Bestätigung heißt „<Name>-Bestätigt“. Vorhandene „B-<Name>“ werden beim Start umbenannt
    und behalten ihre Buchungen; gibt es das neue Tag schon, wandern die Zuordnungen dorthin."""
    from kontor import pflege

    client, k, neu = buch
    alt = client.post("/api/tags", json={"name": "B-Torsten"}).json()["id"]
    alt2 = client.post("/api/tags", json={"name": "B-Tina"}).json()["id"]
    schon = client.post("/api/tags", json={"name": "Tina-Bestätigt"}).json()["id"]
    frei = client.post("/api/tags", json={"name": "Urlaub"}).json()["id"]
    a, b = neu("bestaetigt"), neu("bestaetigt")
    assert client.post("/api/buchungen/mehrfach/tags", json={
        "buchung_ids": [a], "hinzufuegen": [alt, alt2, frei], "entfernen": []}).status_code == 200
    assert client.post("/api/buchungen/mehrfach/tags", json={
        "buchung_ids": [b], "hinzufuegen": [schon], "entfernen": []}).status_code == 200

    pflege.altbestand_umwandeln(config.datenbank)

    assert sorted(t["name"] for t in client.get("/api/tags").json()) == ["Tina-Bestätigt", "Torsten-Bestätigt", "Urlaub"]
    tags = lambda x: sorted(t["name"] for t in client.get(f"/api/buchungen/{x}").json()["tags"])  # noqa: E731
    assert tags(a) == ["Tina-Bestätigt", "Torsten-Bestätigt", "Urlaub"] and tags(b) == ["Tina-Bestätigt"]
