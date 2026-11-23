"""M30: Protokoll, Rückgängig, Verweise und Datensicherung für Regeln mit Ausdruck und Tags
(protokoll.md 22, kategorisierung.md 8.4, loeschen.md 8, sicherung.md 12; E-271 bis E-273) – REST, kern.
"""

from __future__ import annotations

import pytest

from tests.hilfen import m30
from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m3 import aenderungen_seit, letzte_aenderung_id
from tests.hilfen.m6 import pruefe_eintraege
from tests.hilfen.m9 import einspielen, inhalt_sha256, oeffne, sicherung
from tests.hilfen.m19 import zusammenfuehren
from tests.hilfen.m27 import bestand
from tests.hilfen.m30 import alle_treffer, anwenden, einzeln_anwenden, regel, regeln, tags_von

pytestmark = pytest.mark.kern
OBJEKTE_M9 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage"]
REWE = '"REWE" in empfänger'


@pytest.fixture
def b(api):
    return m30.bestand(api)


def _lesen(api, rid):
    return api.get(f"/api/regeln/{rid}", erwartet=200).daten


def _rundreise(api, a, vorher, nachher):
    """Rückgängig stellt ``vorher`` exakt her, Wiederholen wieder ``nachher`` (T 3.6)."""
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert bestand(api) == vorher, f"Rückgängig von {a['aktion']}"
    pruefe_eintraege(u, nachher, vorher)
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher, f"Wiederholen von {a['aktion']}"


# ------------------------------------------------------------------ Protokollform
def test_protokollform_der_regel(b):
    api, k, t = b.api, b.k, b.t
    a0 = letzte_aenderung_id(api)
    mit = regel(api, "Mit Tags", kategorie_id=k["Wohnen"], ausdruck=REWE, tag_ids=[t["Urlaub"]])
    ohne = regel(api, "Ohne Tags", kategorie_id=k["Wohnen"], ausdruck=REWE)
    nur = regel(api, "Nur Tags", bedingungen=[{"feld": "betrag", "operator": "hoechstens", "wert": -1}],
                tag_ids=[t["Steuer"], t["Urlaub"]])
    a1, a2, a3 = aenderungen_seit(api, a0)
    for a, r in ((a1, mit), (a2, ohne), (a3, nur)):
        assert (a["quelle"], a["aktion"], a["gruppe"]) == ("manuell", "regel_anlegen", None)
        (e,) = a["eintraege"]
        form = e["nachher"]
        assert (e["objekt"], e["objekt_id"], e["art"], e["vorher"]) == ("regel", r["id"], "angelegt", None)
        assert "ausdruck" not in form and "ausdruck_form" not in form, "gehören nicht zur Protokollform"
        assert ("tag_ids" in form) == bool(r["tag_ids"]), "tag_ids nur, wenn die Regel Tags hat"
        assert form.get("tag_ids", []) == r["tag_ids"]
        for feld in ("id", "name", "aktiv", "prioritaet", "kategorie_id", "bedingungen"):
            assert form[feld] == r[feld], feld
    assert a3["eintraege"][0]["nachher"]["kategorie_id"] is None


# ------------------------------------------------------------------ Operationen: eine Änderung, umkehrbar
def _regel_anlegen(b):
    regel(b.api, "Neu", ausdruck='empf == "EDEKA" or kategorie == "Wohnen"', tag_ids=sorted(b.t.values()))


def _regel_aendern(b):
    b.api.patch(f"/api/regeln/{b.r['id']}", json={"tag_ids": [b.t["Urlaub"]], "kategorie_id": None,
                                                   "ausdruck": "betrag > 5"}, erwartet=200)


def _regel_loeschen(b):
    b.api.delete(f"/api/regeln/{b.r['id']}", erwartet=204)


def _reihenfolge(b):
    ids = [x["id"] for x in regeln(b.api)]
    b.api.post("/api/regeln/reihenfolge", json={"regel_ids": list(reversed(ids))}, erwartet=200)


def _einzeln(b):
    assert einzeln_anwenden(b.api, b.r["id"], abweichende_ueberschreiben=True)["anzahl"] == 3


def _alle(b):
    erg = anwenden(b.api)
    assert erg["anzahl"] == 1 and len(erg["tags"]) == 4


def _tag_loeschen(b):
    b.api.delete(f"/api/tags/{b.t['Steuer']}", erwartet=204)


OPERATIONEN = {
    "regel_anlegen": (_regel_anlegen, "manuell"), "regel_aendern": (_regel_aendern, "manuell"),
    "regel_loeschen": (_regel_loeschen, "manuell"), "regeln_reihenfolge": (_reihenfolge, "manuell"),
    "regeln_anwenden:einzeln": (_einzeln, "regeln"), "regeln_anwenden:alle": (_alle, "regeln"),
    "tag_loeschen": (_tag_loeschen, "manuell"),
}


@pytest.mark.parametrize("fall", sorted(OPERATIONEN))
def test_operation_protokolliert_und_umkehrbar(b, fall):
    """Genau eine Änderung mit der Nettowirkung je Objekt; Rückgängig und Wiederholen exakt (T 3.5, T 3.6)."""
    api = b.api
    b.r = regel(api, "Rewe", kategorie_id=b.k["Supermarkt"], ausdruck=REWE, tag_ids=[b.t["Steuer"]])
    regel(api, "Zweite", bedingungen=[{"feld": "empfaenger", "operator": "gleich", "wert": "EDEKA"}],
          tag_ids=[b.t["Steuer"]])
    operation, quelle = OPERATIONEN[fall]
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    operation(b)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == (quelle, fall.split(":")[0], None)
    nachher = bestand(api)
    assert nachher != vorher
    pruefe_eintraege(a, vorher, nachher)
    _rundreise(api, a, vorher, nachher)


def test_rueckgaengig_nimmt_vorschlaege_und_tags_zurueck(b):
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Rewe", kategorie_id=k["Supermarkt"], ausdruck=REWE, tag_ids=[t["Steuer"]])
    a0 = letzte_aenderung_id(api)
    einzeln_anwenden(api, r["id"])
    (a,) = aenderungen_seit(api, a0)
    api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    e = api.buchung_lesen(b["erstattung"].id)
    assert e["kategorie_id"] is None and e["vorschlag"] is None and tags_von(api, e["id"]) == set()
    assert tags_von(api, b["rewe1"].id) == {t["Urlaub"]}


# ------------------------------------------------------------------ 8.4 Tags löschen
def test_tag_loeschen_regel_verliert_den_tag(b):
    api, k, t = b.api, b.k, b.t
    beide = regel(api, "Beide", kategorie_id=k["Wohnen"], ausdruck=REWE, tag_ids=[t["Steuer"], t["Urlaub"]])
    nur = regel(api, "Nur", ausdruck=REWE, tag_ids=[t["Steuer"]])
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    api.delete(f"/api/tags/{t['Steuer']}", erwartet=204)
    (a,) = aenderungen_seit(api, a0)
    assert a["aktion"] == "tag_loeschen"
    assert {("regel", beide["id"]), ("regel", nur["id"]), ("tag", t["Steuer"])} <= {
        (e["objekt"], e["objekt_id"]) for e in a["eintraege"]}, "Regeln in derselben Änderung"
    assert _lesen(api, beide["id"])["tag_ids"] == [t["Urlaub"]]
    leer = _lesen(api, nur["id"])
    assert leer["tag_ids"] == [] and leer["kategorie_id"] is None, "bleibt ohne Wirkung bestehen"
    assert leer["ausdruck"] == REWE and leer["aktiv"] is True
    erg = anwenden(api)
    assert all(x["regel_id"] != nur["id"] for x in erg["aenderungen"])
    assert all(x["tag_ids"] == [t["Urlaub"]] for x in erg.get("tags", []))
    # Rückgängig stellt Tag und Zuordnung wieder her (die Anwendung zuerst zurücknehmen)
    for x in reversed(aenderungen_seit(api, a0)):
        api.post(f"/api/aenderungen/{x['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == vorher
    assert _lesen(api, nur["id"])["tag_ids"] == [t["Steuer"]]


def test_tag_in_der_bedingung_geloescht(b):
    api, k, t = b.api, b.k, b.t
    r = regel(api, "Bedingung", kategorie_id=k["Wohnen"], ausdruck='"Urlaub" in tags or empfänger == "EDEKA"')
    ids = {x["buchung_id"] for x in alle_treffer(api, regel_id=r["id"])}
    assert b.namen(ids) == {"rewe1", "alt", "edeka"}
    api.delete(f"/api/tags/{t['Urlaub']}", erwartet=204)
    neu = _lesen(api, r["id"])
    assert f'"#{t["Urlaub"]}"' in neu["ausdruck"] and "Urlaub" not in neu["ausdruck"]
    assert 'empfänger == "EDEKA"' in neu["ausdruck"]
    ids = {x["buchung_id"] for x in alle_treffer(api, regel_id=r["id"])}
    assert b.namen(ids) == {"alt", "edeka"}, "der Teil mit dem gelöschten Tag trifft nie mehr"
    # ein neuer Tag gleichen Namens ist ein anderer Tag
    neu_id = api.tag("Urlaub")["id"]
    api.patch(f"/api/buchungen/{b['miete'].id}", json={"tag_ids": [neu_id]}, erwartet=200)
    ids = {x["buchung_id"] for x in alle_treffer(api, regel_id=r["id"])}
    assert b.namen(ids) == {"alt", "edeka"}


def test_rueckgaengig_tag_anlegen_konflikt(b):
    api = b.api
    a0 = letzte_aenderung_id(api)
    tag = api.tag("Später vergeben")["id"]
    (anlegen,) = aenderungen_seit(api, a0)
    r = regel(api, "Vergibt", ausdruck=REWE, tag_ids=[tag])
    f = api.post(f"/api/aenderungen/{anlegen['id']}/rueckgaengig", erwartet=409)
    assert fehlercode(f) == "rueckgaengig_konflikt"
    assert _lesen(api, r["id"])["tag_ids"] == [tag]
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    api.post(f"/api/aenderungen/{anlegen['id']}/rueckgaengig", erwartet=200)
    assert all(x["id"] != tag for x in api.get("/api/tags", erwartet=200).daten)


# ------------------------------------------------------------------ 8.4 Verweise auf Konten und Kategorien
def test_konto_mit_verweis_aus_ausdruck_nicht_loeschbar(api):
    wohnen = api.konto("Wohnen", "aufwand")["id"]
    leer, bar = api.konto("Leer", "aufwand")["id"], api.konto("Bar", "girokonto")["id"]
    frei = api.konto("Frei", "aufwand")["id"]
    r = regel(api, "Verweise", kategorie_id=wohnen, ausdruck='kategorie in ["Leer"] or konto == "Bar"')
    for kid in (leer, bar, wohnen):
        assert fehlercode(api.delete(f"/api/konten/{kid}", erwartet=409)) == "konto_in_verwendung"
    api.delete(f"/api/konten/{frei}", erwartet=204)
    api.delete(f"/api/regeln/{r['id']}", erwartet=204)
    for kid in (leer, bar, wohnen):
        api.delete(f"/api/konten/{kid}", erwartet=204)


def _baum(api):
    k = {"giro": api.konto("Giro")["id"], "ober": api.konto("Ober", "aufwand")["id"],
         "gehalt": api.konto("Gehalt", "ertrag")["id"]}
    k["unter"] = api.konto("Unter", "aufwand", eltern_id=k["ober"])["id"]
    api.buchung("2026-11-10", [(k["giro"], -1000), (k["unter"], 1000)])
    return k


def _konto_loeschen(api, kid, buchungen, **felder):
    return api.post(f"/api/konten/{kid}/loeschen", json={"buchungen": buchungen, "konflikte": "behalten", **felder},
                    erwartet=200).daten


def test_loeschen_mit_umleiten_ersetzt_den_verweis(api):
    k = _baum(api)
    tag = api.tag("Marke")["id"]
    r = regel(api, "Unter", kategorie_id=k["gehalt"], ausdruck='kategorie == "Ober:Unter" and betrag > 5')
    fremd = regel(api, "Fremd", ausdruck="betrag > 5", tag_ids=[tag])
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    probe = _konto_loeschen(api, k["unter"], "elternkonto", trocken=True)
    assert probe["regeln_geaendert"] == [r["id"]] and bestand(api) == vorher
    erg = _konto_loeschen(api, k["unter"], "elternkonto")
    assert erg["regeln_geaendert"] == [r["id"]] and erg["regeln_geloescht"] == []
    neu = _lesen(api, r["id"])
    assert neu["ausdruck"] == 'kategorie == "Ober" and betrag > 5'
    assert {x: neu[x] for x in ("name", "aktiv", "prioritaet", "kategorie_id", "tag_ids", "ausdruck_form")} == \
        {x: r[x] for x in ("name", "aktiv", "prioritaet", "kategorie_id", "tag_ids", "ausdruck_form")}
    assert _lesen(api, fremd["id"]) == fremd
    assert len(alle_treffer(api, regel_id=r["id"])) == 1, "trifft die umgebuchte Buchung"
    (a,) = aenderungen_seit(api, a0)
    nachher = bestand(api)
    pruefe_eintraege(a, vorher, nachher)
    _rundreise(api, a, vorher, nachher)


@pytest.mark.parametrize("variante", ["loeschen", "unkategorisiert"])
def test_loeschen_ohne_umleiten_loescht_die_regel(api, variante):
    k = _baum(api)
    r = regel(api, "Unter", kategorie_id=k["gehalt"], ausdruck='kategorie == "Ober:Unter"')
    bleibt = regel(api, "Ober", kategorie_id=k["gehalt"], ausdruck='kategorie == "Ober"')
    erg = _konto_loeschen(api, k["unter"], variante)
    assert erg["regeln_geloescht"] == [r["id"]] and erg["regeln_geaendert"] == []
    assert regeln(api) == [bleibt]


def test_kategorien_zusammenfuehren_ersetzt_den_verweis(api):
    k = _baum(api)
    ziel = api.konto("Ziel", "aufwand")["id"]
    r = regel(api, "Quelle", kategorie_id=k["gehalt"], ausdruck='kategorie == "Ober:Unter" or kategorie == "Ziel"')
    erg = zusammenfuehren(api, [k["unter"]], ziel).daten
    assert r["id"] in erg["regeln_geaendert"]
    neu = _lesen(api, r["id"])
    assert "Unter" not in neu["ausdruck"] and neu["ausdruck"].count('"Ziel"') == 2
    assert neu["kategorie_id"] == k["gehalt"]
    assert len(alle_treffer(api, regel_id=r["id"])) == 1


# ------------------------------------------------------------------ Datensicherung
def _mit_regeln(pfad):
    api = neue_api(pfad)
    b = m30.bestand(api)
    regel(api, "Ausdruck", kategorie_id=b.k["Supermarkt"], tag_ids=[b.t["Steuer"], b.t["Urlaub"]],
          ausdruck='"REWE" in empfänger and kategorie == "Lebensmittel:Supermarkt" or konto == "Spar" '
                   'and "Urlaub" not in tags')
    regel(api, "Nur Tags", ausdruck="betrag > 20", tag_ids=[b.t["Urlaub"]], aktiv=False, prioritaet=7)
    regel(api, "Bisher", kategorie_id=b.k["Wohnen"],
          bedingungen=[{"feld": "empfaenger", "operator": "enthaelt", "wert": "REWE"},
                       {"feld": "konto_id", "operator": "gleich", "wert": b.k["Giro"]}])
    return api, b


def test_sicherung_rundreise(tmp_path):
    quelle, b = _mit_regeln(tmp_path / "q")
    m, _ = oeffne(sicherung(quelle))
    assert m["schemaversion"] >= 9
    bs = bestand(quelle)
    assert m["anzahl"]["regel"] == 3
    inhalt = {o: [bs[x] for x in sorted(x for x in bs if x[0] == o)] for o in OBJEKTE_M9}
    assert m["inhalt_sha256"] == inhalt_sha256(inhalt), "Prüfsumme über die Protokollform der Regeln"
    ziel = neue_api(tmp_path / "z")
    einspielen(ziel, sicherung(quelle))
    assert bestand(ziel) == bs
    assert regeln(ziel) == regeln(quelle), "Ausdruck, Form, Tags und leere Kategorie bleiben erhalten"
    nur = next(r for r in regeln(ziel) if r["name"] == "Nur Tags")
    assert nur["kategorie_id"] is None and nur["tag_ids"] == [b.t["Urlaub"]] and nur["aktiv"] is False
    for r in regeln(quelle):
        assert ([x["buchung_id"] for x in alle_treffer(ziel, regel_id=r["id"])]
                == [x["buchung_id"] for x in alle_treffer(quelle, regel_id=r["id"])]), r["name"]
    m2, _ = oeffne(sicherung(ziel))
    assert m2["inhalt_sha256"] == m["inhalt_sha256"]


def test_einspielen_rueckgaengig(tmp_path):
    quelle, b = _mit_regeln(tmp_path / "q")
    ziel = neue_api(tmp_path / "z")
    kat, tag = ziel.konto("Alt", "aufwand")["id"], ziel.tag("Vorher")["id"]
    regel(ziel, "Vorher", kategorie_id=kat, ausdruck="betrag > 1", tag_ids=[tag])
    vorher, a0 = bestand(ziel), letzte_aenderung_id(ziel)
    einspielen(ziel, sicherung(quelle))
    (a,) = aenderungen_seit(ziel, a0)
    assert a["aktion"] == "sicherung_einspielen"
    assert bestand(ziel) == bestand(quelle)
    ziel.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200)
    assert bestand(ziel) == vorher
    (r,) = regeln(ziel)
    assert r["tag_ids"] == [tag] and r["ausdruck"] == "betrag > 1"


def test_pruefsumme_haengt_an_den_regel_tags(tmp_path):
    api, b = _mit_regeln(tmp_path)
    m0, _ = oeffne(sicherung(api))
    r = next(x for x in regeln(api) if x["name"] == "Bisher")
    api.patch(f"/api/regeln/{r['id']}", json={"tag_ids": [b.t["Steuer"]]}, erwartet=200)
    m1, _ = oeffne(sicherung(api))
    assert m1["inhalt_sha256"] != m0["inhalt_sha256"]
    api.patch(f"/api/regeln/{r['id']}", json={"tag_ids": []}, erwartet=200)
    m2, _ = oeffne(sicherung(api))
    assert m2["inhalt_sha256"] == m0["inhalt_sha256"], "ohne Tags wieder die Form ohne tag_ids"
