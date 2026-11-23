"""M27: Tags an Empfängern (sammel.md 2, protokoll.md 21, sicherung.md 11; E-249, E-250) – REST, kern."""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import pruefe_eintraege
from tests.hilfen.m9 import einspielen, inhalt_sha256, oeffne, sicherung
from tests.hilfen.m27 import bestand, tags_von

pytestmark = pytest.mark.kern
OBJEKTE_M9 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]


@pytest.fixture
def api(tmp_path):
    return neue_api(tmp_path)


def _patch(api, eid, erwartet=200, **body):
    return api.patch(f"/api/empfaenger/{eid}", json=body, erwartet=erwartet)


def _eine(api, a0, aktion):
    neu = aenderungen_seit(api, a0)
    assert [(x["quelle"], x["aktion"], x["gruppe"]) for x in neu] == [("manuell", aktion, None)], neu
    return neu[0]


def _rundreise(api, a, vorher, nachher):
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == vorher
    pruefe_eintraege(u, nachher, vorher)
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher


def test_ohne_tags_feld_fehlt(api):
    e = api.empfaenger("Ohne Tags (fiktiv)")
    assert "tags" not in e
    assert all("tags" not in x for x in api.get("/api/empfaenger", erwartet=200).daten)
    assert "tags" not in api.get(f"/api/empfaenger/{e['id']}", erwartet=200).daten


def test_setzen_ersetzen_entfernen_mit_protokoll(api):
    e = api.empfaenger("Bäckerei (fiktiv)")["id"]
    tina, torsten, z = api.tag("Tina")["id"], api.tag("Torsten")["id"], api.tag("Aaa")["id"]
    v, a0 = bestand(api), letzte_aenderung_id(api)
    r = _patch(api, e, tag_ids=[torsten, tina, z]).daten
    assert [t["name"] for t in r["tags"]] == ["Aaa", "Tina", "Torsten"], "nach (name, id)"
    assert r["tags"] == [{"id": z, "name": "Aaa"}, {"id": tina, "name": "Tina"}, {"id": torsten, "name": "Torsten"}]
    a = _eine(api, a0, "empfaenger_aendern")
    n = bestand(api)
    assert n[("empfaenger", e)]["tags"] == r["tags"]
    pruefe_eintraege(a, v, n)
    _rundreise(api, a, v, n)
    # ersetzen
    v, a0 = n, letzte_aenderung_id(api)
    assert [t["id"] for t in _patch(api, e, tag_ids=[tina]).daten["tags"]] == [tina]
    a = _eine(api, a0, "empfaenger_aendern")
    pruefe_eintraege(a, v, bestand(api))
    # ohne tag_ids unverändert
    assert tags_von(api, e) == ["Tina"]
    _patch(api, e, aliase=["Bäcker"])
    assert tags_von(api, e) == ["Tina"]
    # [] entfernt alle; Feld fehlt danach
    v, a0 = bestand(api), letzte_aenderung_id(api)
    r = _patch(api, e, tag_ids=[]).daten
    assert "tags" not in r
    a = _eine(api, a0, "empfaenger_aendern")
    n = bestand(api)
    assert "tags" not in n[("empfaenger", e)]
    _rundreise(api, a, v, n)


@pytest.mark.parametrize("body", [{"tag_ids": None}, {"tag_ids": [1, 1]}, {"tag_ids": "1"},
                                  {"tag_ids": list(range(1, 52))}, {"tag_ids": [1.5]}])
def test_validierung(api, body):
    e = api.empfaenger("Prüfling (fiktiv)")["id"]
    for i in range(3):
        api.tag(f"T{i}")
    assert fehlercode(_patch(api, e, erwartet=422, **body)) == "validierung"


def test_pruefreihenfolge_und_unbekannte_tags(api):
    e = api.empfaenger("Reihenfolge (fiktiv)")["id"]
    t = api.tag("Bekannt")["id"]
    api.empfaenger("Anderer (fiktiv)")
    a0 = letzte_aenderung_id(api)
    r = _patch(api, e, erwartet=422, tag_ids=[t, 999998, 999997])
    assert fehlercode(r) == "referenz_unbekannt"
    assert r.json()["fehler"]["details"] == {"tag_ids": [999997, 999998]}
    assert fehlercode(_patch(api, 999999, erwartet=404, tag_ids=[999998])) == "nicht_gefunden", "404 vor Tags"
    assert fehlercode(_patch(api, 999999, erwartet=422, tag_ids=[1, 1])) == "validierung", "Körper vor 404"
    assert fehlercode(_patch(api, e, erwartet=409, name="Anderer (fiktiv)", tag_ids=[999998])) == \
        "empfaenger_existiert", "übrige Prüfungen (M3) vor den Tags"
    assert aenderungen_seit(api, a0) == [] and tags_von(api, e) == []


def test_anlegen_kennt_tag_ids_nicht(api):
    t = api.tag("X")["id"]
    r = api.post("/api/empfaenger", json={"name": "Neu (fiktiv)", "tag_ids": [t]}, erwartet=422)
    assert fehlercode(r) == "validierung"


def test_zusammenfuehren_vereinigt(api):
    ziel = api.empfaenger("Ziel (fiktiv)")["id"]
    q1, q2 = api.empfaenger("Quelle Eins (fiktiv)")["id"], api.empfaenger("Quelle Zwei (fiktiv)")["id"]
    tina, torsten, x = api.tag("Tina")["id"], api.tag("Torsten")["id"], api.tag("Extra")["id"]
    _patch(api, ziel, tag_ids=[tina])
    _patch(api, q1, tag_ids=[tina, torsten])
    _patch(api, q2, tag_ids=[x])
    v, a0 = bestand(api), letzte_aenderung_id(api)
    r = api.post(f"/api/empfaenger/{ziel}/zusammenfuehren", json={"quelle_ids": [q1, q2]}, erwartet=200).daten
    assert tags_von(api, ziel) == ["Extra", "Tina", "Torsten"]
    if isinstance(r, dict) and "tags" in r:
        assert [t["name"] for t in r["tags"]] == ["Extra", "Tina", "Torsten"]
    a = _eine(api, a0, "empfaenger_zusammenfuehren")
    n = bestand(api)
    pruefe_eintraege(a, v, n)
    _rundreise(api, a, v, n)


def test_tag_loeschen_entfernt_von_empfaengern(api):
    e1, e2 = api.empfaenger("Eins (fiktiv)")["id"], api.empfaenger("Zwei (fiktiv)")["id"]
    t, bleibt = api.tag("Weg")["id"], api.tag("Bleibt")["id"]
    _patch(api, e1, tag_ids=[t, bleibt])
    _patch(api, e2, tag_ids=[t])
    v, a0 = bestand(api), letzte_aenderung_id(api)
    api.delete(f"/api/tags/{t}", erwartet=204)
    a = _eine(api, a0, "tag_loeschen")
    n = bestand(api)
    assert tags_von(api, e1) == ["Bleibt"] and "tags" not in n[("empfaenger", e2)]
    pruefe_eintraege(a, v, n)
    _rundreise(api, a, v, n)


def test_rueckgaengig_tag_anlegen_konflikt(api):
    e = api.empfaenger("Konflikt (fiktiv)")["id"]
    a0 = letzte_aenderung_id(api)
    t = api.tag("Später benutzt")["id"]
    (anlegen,) = aenderungen_seit(api, a0)
    _patch(api, e, tag_ids=[t])
    r = api.post(f"/api/aenderungen/{anlegen['id']}/rueckgaengig", erwartet=409)
    assert fehlercode(r) == "rueckgaengig_konflikt"
    assert tags_von(api, e) == ["Später benutzt"]


def test_sicherung_rundreise_mit_empfaenger_tags(tmp_path):
    quelle = neue_api(tmp_path / "q")
    e = quelle.empfaenger("Gesichert (fiktiv)")["id"]
    quelle.empfaenger("Ohne (fiktiv)")
    tags = [quelle.tag(n)["id"] for n in ("Tina", "Torsten")]
    _patch(quelle, e, tag_ids=tags)
    m, _ = oeffne(sicherung(quelle))
    assert m["schemaversion"] >= 7
    bs = bestand(quelle)
    inhalt = {o: [bs[k] for k in sorted(k for k in bs if k[0] == o)] for o in OBJEKTE_M9}
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt), "Prüfsumme über die Empfängerform mit tags"
    ziel = neue_api(tmp_path / "z")
    einspielen(ziel, sicherung(quelle))
    assert bestand(ziel) == bs
    assert tags_von(ziel, e) == ["Tina", "Torsten"]
    m2, _ = oeffne(sicherung(ziel))
    assert m2["inhalt_sha256"] == m["inhalt_sha256"]


def test_pruefsumme_ohne_empfaenger_tags_unveraendert(tmp_path):
    a = neue_api(tmp_path)
    e = a.empfaenger("Laden (fiktiv)")["id"]
    t = a.tag("Tina")["id"]
    m0, _ = oeffne(sicherung(a))
    _patch(a, e, tag_ids=[t])
    _patch(a, e, tag_ids=[])
    m1, _ = oeffne(sicherung(a))
    assert (m1["anzahl"], m1["inhalt_sha256"]) == (m0["anzahl"], m0["inhalt_sha256"])
    bs = bestand(a)
    assert m1["inhalt_sha256"] == inhalt_sha256({o: [bs[k] for k in sorted(k for k in bs if k[0] == o)]
                                                 for o in OBJEKTE_M9})
