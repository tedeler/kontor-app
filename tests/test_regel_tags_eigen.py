"""Regeln vergeben Tags (D-208): Kategorie optional, Tags additiv, alle passenden Regeln, Protokoll, Sicherung."""

from __future__ import annotations

import sqlite3

from kontor import db

from .test_ausdruck_eigen import _aufbau, _buchung, _client


def _tag(c, name: str) -> int:
    r = c.post("/api/tags", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tags(c, bid: int) -> list[str]:
    return sorted(t["name"] for t in c.get(f"/api/buchungen/{bid}").json()["tags"])


def test_regel_mit_tags_anlegen_und_aendern(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    urlaub, privat = _tag(c, "Urlaub"), _tag(c, "Privat")
    # nur Tags, ohne Kategorie
    r = c.post("/api/regeln", json={"name": "nur Tags", "ausdruck": '"rewe" in empf', "tag_ids": [privat, urlaub]})
    assert r.status_code == 201, r.text
    regel = r.json()
    assert regel["kategorie_id"] is None and regel["tag_ids"] == sorted([urlaub, privat])
    # ohne Kategorie und ohne Tags: keine Aktion
    r = c.post("/api/regeln", json={"name": "leer", "ausdruck": '"rewe" in empf'})
    assert r.status_code == 422 and r.json()["fehler"]["details"][0]["ort"] == ["body", "kategorie_id"]
    r = c.post("/api/regeln", json={"name": "leer", "ausdruck": '"rewe" in empf', "kategorie_id": None, "tag_ids": []})
    assert r.status_code == 422
    # unbekannter Tag, doppelte Tags
    r = c.post("/api/regeln", json={"name": "x", "ausdruck": '"rewe" in empf', "tag_ids": [99999]})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "referenz_unbekannt"
    assert c.post("/api/regeln", json={"name": "x", "ausdruck": '"rewe" in empf',
                                        "tag_ids": [urlaub, urlaub]}).status_code == 422
    # ändern: Kategorie dazu, Tags weg; letzte Aktion lässt sich nicht entfernen
    r = c.patch(f"/api/regeln/{regel['id']}", json={"kategorie_id": k["lm"], "tag_ids": []})
    assert r.status_code == 200 and r.json()["tag_ids"] == [] and r.json()["kategorie_id"] == k["lm"]
    r = c.patch(f"/api/regeln/{regel['id']}", json={"kategorie_id": None})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "regel_ohne_aktion"
    # Regeln ohne Tags melden eine leere Liste
    alt = c.post("/api/regeln", json={"name": "alt", "kategorie_id": k["lm"], "ausdruck": '"edeka" in empf'}).json()
    assert alt["tag_ids"] == []


def test_tags_aller_passenden_regeln_additiv(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    urlaub, privat, alt = _tag(c, "Urlaub"), _tag(c, "Privat"), _tag(c, "Bestand")
    rewe, togo = k["ids"][0], k["ids"][1]
    c.patch(f"/api/buchungen/{rewe}", json={"tag_ids": [alt]})
    c.post("/api/regeln", json={"name": "Kat", "kategorie_id": k["cafe"], "ausdruck": '"rewe" in empf', "tag_ids": [privat]})
    c.post("/api/regeln", json={"name": "Tag", "ausdruck": '"rewe" in empf and bet > 5', "tag_ids": [urlaub, privat]})
    # Probelauf ändert nichts, nennt aber die Tags
    t = c.post("/api/regeln/anwenden", json={"trocken": True}).json()
    assert {x["buchung_id"]: x["tag_ids"] for x in t["tags"]}[rewe] == sorted([urlaub, privat])
    assert _tags(c, rewe) == ["Bestand"]
    c.post("/api/regeln/anwenden", json={"nur_unkategorisiert": False})
    assert _tags(c, rewe) == ["Bestand", "Privat", "Urlaub"]      # beide Regeln, vorhandener Tag bleibt
    assert _tags(c, togo) == ["Privat"]                            # nur die erste Regel trifft (4,10 €)
    assert c.get(f"/api/buchungen/{rewe}").json()["vorschlag"]["quelle"] == "regel"   # Kategorie weiter als Vorschlag
    # zweiter Lauf: nichts Neues
    assert "tags" not in c.post("/api/regeln/anwenden", json={}).json()
    # Rückgängig nimmt die Tags wieder weg
    eintraege = c.get("/api/aenderungen").json()["eintraege"]
    erste = next(e for e in eintraege if e["aktion"] == "regeln_anwenden")
    c.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [erste["id"]]})
    assert _tags(c, rewe) == ["Bestand"] and _tags(c, togo) == []


def test_nur_tag_regel_verdeckt_keine_kategorie(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    urlaub = _tag(c, "Urlaub")
    c.post("/api/regeln", json={"name": "Tag zuerst", "ausdruck": '"rewe" in empf', "tag_ids": [urlaub], "prioritaet": 1})
    c.post("/api/regeln", json={"name": "Kat", "kategorie_id": k["cafe"], "ausdruck": '"rewe" in empf', "prioritaet": 2})
    t = c.post("/api/regeln/test", json={"ausdruck": '"rewe" in empf', "kategorie_id": k["lm"], "testmenge": ""}).json()
    assert {z["verdeckt_von"]["name"] for z in t["treffer"] if z["wirkung"] == "verdeckt"} == {"Kat"}
    c.post("/api/regeln/anwenden", json={"nur_unkategorisiert": False})
    b = c.get(f"/api/buchungen/{k['ids'][0]}").json()
    assert b["kategorie_id"] == k["cafe"] and [x["name"] for x in b["tags"]] == ["Urlaub"]


def test_testbereich_und_anwenden_einer_regel(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    urlaub = _tag(c, "Urlaub")
    c.patch(f"/api/buchungen/{k['ids'][1]}", json={"tag_ids": [urlaub]})
    t = c.post("/api/regeln/test", json={"ausdruck": '"rewe" in empf', "tag_ids": [urlaub], "testmenge": "datum in 2024"}).json()
    assert t["anzahl"] == 2 and t["tags_anzahl"] == 1
    neu = {z["buchung_id"]: z["tags_neu"] for z in t["treffer"]}
    assert neu == {k["ids"][0]: [urlaub], k["ids"][1]: []}
    assert all(z["wirkung"] == "treffer" for z in t["treffer"])
    assert c.post("/api/regeln/test", json={"ausdruck": "True", "tag_ids": [99999]}).status_code == 422
    regel = c.post("/api/regeln", json={"name": "U", "ausdruck": '"rewe" in empf', "tag_ids": [urlaub]}).json()
    r = c.post(f"/api/regeln/{regel['id']}/anwenden", json={"testmenge": ""})
    assert r.json() == {"geaendert": sorted([k["ids"][0], k["ids"][3]]), "anzahl": 2}
    assert _tags(c, k["ids"][3]) == ["Urlaub"]
    assert c.get(f"/api/buchungen/{k['ids'][0]}").json()["vorschlag"] is None   # keine Kategorie angefasst


def test_tag_loeschen_und_protokoll(tmp_path):
    c = _client(tmp_path)
    k = _aufbau(c)
    urlaub = _tag(c, "Urlaub")
    regel = c.post("/api/regeln", json={"name": "U", "kategorie_id": k["lm"], "ausdruck": '"rewe" in empf',
                                        "tag_ids": [urlaub]}).json()
    assert c.delete(f"/api/tags/{urlaub}").status_code == 204
    assert c.get("/api/regeln").json()[0]["tag_ids"] == []
    letzte = c.get("/api/aenderungen").json()["eintraege"][0]
    c.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [letzte["id"]]})
    assert c.get("/api/regeln").json()[0]["tag_ids"] == [urlaub]
    # Regel löschen und wiederherstellen: Tags kommen zurück
    c.delete(f"/api/regeln/{regel['id']}")
    letzte = c.get("/api/aenderungen").json()["eintraege"][0]
    c.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [letzte["id"]]})
    assert c.get("/api/regeln").json()[0]["tag_ids"] == [urlaub]


def test_sicherung_mit_regel_tags(tmp_path):
    c = _client(tmp_path)
    _aufbau(c)
    urlaub = _tag(c, "Urlaub")
    c.post("/api/regeln", json={"name": "U", "ausdruck": '"rewe" in empf', "tag_ids": [urlaub]})
    datei = c.get("/api/sicherung").content
    for r in c.get("/api/regeln").json():
        c.delete(f"/api/regeln/{r['id']}")
    r = c.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
               files={"datei": ("s.zip", datei, "application/zip")})
    assert r.status_code == 200, r.text
    regel = c.get("/api/regeln").json()[0]
    assert regel["kategorie_id"] is None and regel["tag_ids"] == [urlaub]


def test_migration_von_schema_13(tmp_path):
    pfad = tmp_path / "alt.sqlite3"
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    con.executescript("""
        PRAGMA foreign_keys = OFF;
        DROP TABLE regel_tag;
        DROP TABLE regel;
        CREATE TABLE regel (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            aktiv INTEGER NOT NULL CHECK (aktiv IN (0, 1)),
            prioritaet INTEGER NOT NULL CHECK (typeof(prioritaet) = 'integer' AND prioritaet BETWEEN 0 AND 1000000),
            kategorie_id INTEGER NOT NULL REFERENCES konto(id), bedingungen TEXT NOT NULL);
        INSERT INTO konto (id, name, art, geschlossen, notiz) VALUES (900, 'K', 'aufwand', 0, '');
        INSERT INTO empfaenger (id, name) VALUES (7, 'E');
        INSERT INTO regel (id, name, aktiv, prioritaet, kategorie_id, bedingungen) VALUES (5, 'a', 1, 10, 900, '[]');
        INSERT INTO regel (id, name, aktiv, prioritaet, kategorie_id, bedingungen) VALUES (9, 'b', 1, 20, 900, '[]');
        DELETE FROM regel WHERE id = 9;
        INSERT INTO regel_automatisch (regel_id, empfaenger_id) VALUES (5, 7);
        UPDATE meta SET wert = '13' WHERE schluessel = 'schema_version';
    """)
    con.commit()
    con.close()
    db.schema_anlegen(pfad)
    con = sqlite3.connect(pfad)
    assert con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()[0] == str(db.SCHEMA_VERSION)
    assert con.execute("SELECT id, name, kategorie_id FROM regel").fetchall() == [(5, "a", 900)]
    assert con.execute("SELECT regel_id, empfaenger_id FROM regel_automatisch").fetchall() == [(5, 7)]
    assert con.execute("SELECT seq FROM sqlite_sequence WHERE name = 'regel'").fetchone()[0] == 9   # IDs nicht neu vergeben
    con.execute("INSERT INTO regel (name, aktiv, prioritaet, kategorie_id, bedingungen) VALUES ('c', 1, 30, NULL, '[]')")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def test_sync_vergibt_tags_aller_passenden_regeln(tmp_path):
    from .test_sammelpaket_eigen import _sync_client, ok, test_iban

    c = _sync_client(tmp_path, True, test_iban(4719))
    bank = _tag(c, "Bank")
    c.post("/api/regeln", json={"name": "alles", "ausdruck": "bet >= 0", "tag_ids": [bank]})
    lauf = ok(c.post("/api/sync", json={}))
    neu = sum(x["buchungen_neu"] for x in lauf["konten"])
    assert neu > 0
    buchungen = c.get("/api/buchungen").json()
    eintraege = buchungen["eintraege"] if isinstance(buchungen, dict) else buchungen
    assert len(eintraege) == neu and all([x["id"] for x in b["tags"]] == [bank] for b in eintraege)
