"""M3: Rückgängig – Zustands- und Bezugsprüfung, mehrere Änderungen, Wiederholen, Wirksamkeit (protokoll.md 6).

Eigenschaftsbasiert: zufällige Operationsfolgen werden in umgekehrter Reihenfolge zurückgenommen; nach jedem
Schritt muss der Bestand exakt dem vorher aufgezeichneten entsprechen (T 3.6). Ob ein Rückgängig gelingen muss,
berechnet ein unabhängiges Orakel aus Zustands- und Bezugsprüfung.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import (aenderungen_seit, alle_aenderungen, bestand, bezuege_ok, letzte_aenderung_id,
                             pruefe_eintraege, rueckgaengig, zustand_m3)

pytestmark = pytest.mark.kern


def _konten(api):
    g = api.konto("Giro")
    l = api.konto("Lebensmittel", "aufwand")
    h = api.konto("Haushalt", "aufwand")
    return g, l, h


def _summen_ok(api):
    for b in api.alle_buchungen():
        assert sum(s["betrag"] for s in b["splits"]) == 0 and len(b["splits"]) >= 2
    assert api.uebersicht()["summe_gesamt"] == 0


def test_spaetere_aenderung_blockiert(api):
    g, l, h = _konten(api)
    vor = letzte_aenderung_id(api)
    b = api.buchung("2024-03-01", [(g["id"], -500), (l["id"], 500)])
    (anlegen,) = aenderungen_seit(api, vor)
    api.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "später"}, erwartet=200)
    z = zustand_m3(api)
    assert fehlercode(rueckgaengig(api, anlegen["id"], 409)) == "rueckgaengig_konflikt"
    assert zustand_m3(api) == z
    assert api.get(f"/api/aenderungen/{anlegen['id']}", erwartet=200).daten["rueckgaengig_durch"] is None


def test_unabhaengige_aeltere_aenderung(api):
    g, l, h = _konten(api)
    b1 = api.buchung("2024-03-01", [(g["id"], -500), (l["id"], 500)])
    b2 = api.buchung("2024-03-02", [(g["id"], -700), (l["id"], 700)])
    vor = letzte_aenderung_id(api)
    api.put(f"/api/buchungen/{b1['id']}/kategorie", json={"kategorie_id": h["id"]}, erwartet=200)
    (k,) = aenderungen_seit(api, vor)
    api.patch(f"/api/buchungen/{b2['id']}", json={"verwendungszweck": "andere Buchung"}, erwartet=200)
    nach_b2 = api.buchung_lesen(b2["id"])
    rueckgaengig(api, k["id"])
    assert api.buchung_lesen(b1["id"])["kategorie_id"] == l["id"]
    assert api.buchung_lesen(b2["id"]) == nach_b2


def test_bezugspruefung(api):
    """Konto anlegen rückgängig, obwohl inzwischen eine Buchung darauf bucht → Konflikt."""
    g, l, h = _konten(api)
    vor = letzte_aenderung_id(api)
    k = api.konto("Freizeit", "aufwand")
    (a,) = aenderungen_seit(api, vor)
    api.buchung("2024-03-05", [(g["id"], -100), (k["id"], 100)])
    z = zustand_m3(api)
    assert fehlercode(rueckgaengig(api, a["id"], 409)) == "rueckgaengig_konflikt"
    assert zustand_m3(api) == z
    # Tag löschen, gleichnamigen Tag neu anlegen, Löschen rückgängig → Eindeutigkeit verletzt
    t = api.tag("Urlaub")
    vor = letzte_aenderung_id(api)
    api.delete(f"/api/tags/{t['id']}", erwartet=204)
    (loe,) = aenderungen_seit(api, vor)
    api.tag("URLAUB")
    assert fehlercode(rueckgaengig(api, loe["id"], 409)) == "rueckgaengig_konflikt"


def test_geloeschtes_kommt_mit_alter_id_zurueck(api):
    g, l, h = _konten(api)
    t = api.tag("Urlaub")
    b = api.buchung("2024-03-01", [(g["id"], -500, "a"), (l["id"], 300, "b"), (h["id"], 200, "c")],
                    tag_ids=[t["id"]])
    vorher = api.buchung_lesen(b["id"])
    vor = letzte_aenderung_id(api)
    api.delete(f"/api/buchungen/{b['id']}", erwartet=204)
    api.delete(f"/api/tags/{t['id']}", erwartet=204)
    loe_b, loe_t = aenderungen_seit(api, vor)
    assert fehlercode(rueckgaengig(api, loe_b["id"], 409)) == "rueckgaengig_konflikt", "Tag fehlt (Bezug)"
    rueckgaengig(api, loe_t["id"])
    rueckgaengig(api, loe_b["id"])
    assert api.buchung_lesen(b["id"]) == vorher
    neu = api.buchung("2024-03-02", [(g["id"], -1), (l["id"], 1)])
    assert neu["id"] > b["id"] and min(s["id"] for s in neu["splits"]) > max(s["id"] for s in vorher["splits"])


def test_mehrere_und_gruppe(api):
    g, l, h = _konten(api)
    z0 = bestand(api)
    vor = letzte_aenderung_id(api)
    b = api.buchung("2024-03-01", [(g["id"], -500), (l["id"], 500)])
    api.put(f"/api/buchungen/{b['id']}/kategorie", json={"kategorie_id": h["id"]}, erwartet=200)
    t = api.tag("Neu")
    api.patch(f"/api/buchungen/{b['id']}", json={"tag_ids": [t["id"]]}, erwartet=200)
    a1, a2, a3, a4 = aenderungen_seit(api, vor)
    z = bestand(api)
    assert fehlercode(api.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [a1["id"], 999999]},
                               erwartet=422)) == "referenz_unbekannt"
    for koerper in ({}, {"aenderung_ids": [a1["id"]], "gruppe": "x"}, {"aenderung_ids": []},
                    {"aenderung_ids": [a1["id"], a1["id"]]}):
        assert fehlercode(api.post("/api/aenderungen/rueckgaengig", json=koerper, erwartet=422)) == "validierung"
    assert fehlercode(api.post("/api/aenderungen/rueckgaengig", json={"gruppe": "gibt:es:nicht"},
                               erwartet=422)) == "referenz_unbekannt"
    assert fehlercode(api.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [a1["id"], a2["id"]]},
                               erwartet=409)) == "rueckgaengig_konflikt", "a4 ändert die Buchung danach noch"
    assert bestand(api) == z
    u = api.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [a4["id"], a1["id"], a3["id"], a2["id"]]},
                 erwartet=200).daten
    assert u["rueckgaengig_von"] == [a1["id"], a2["id"], a3["id"], a4["id"]]
    assert bestand(api) == z0
    pruefe_eintraege(u, z, z0)
    for a in (a1, a2, a3, a4):
        assert api.get(f"/api/aenderungen/{a['id']}", erwartet=200).daten["rueckgaengig_durch"] == u["id"]
    r = api.post("/api/aenderungen/rueckgaengig", json={"aenderung_ids": [a1["id"]]}, erwartet=409)
    assert fehlercode(r) == "bereits_rueckgaengig" and r.json()["fehler"]["details"]["aenderung_ids"] == [a1["id"]]
    rueckgaengig(api, u["id"])
    assert bestand(api) == z


def test_wirksamkeit_kette(api):
    g, l, h = _konten(api)
    vor = letzte_aenderung_id(api)
    api.konto("Neu", "aufwand")
    (a,) = aenderungen_seit(api, vor)
    u = rueckgaengig(api, a["id"]).daten
    r = rueckgaengig(api, u["id"]).daten
    assert r["rueckgaengig_von"] == [u["id"]]
    assert api.get(f"/api/aenderungen/{a['id']}", erwartet=200).daten["rueckgaengig_durch"] is None
    u2 = rueckgaengig(api, a["id"]).daten
    assert api.get(f"/api/aenderungen/{a['id']}", erwartet=200).daten["rueckgaengig_durch"] == u2["id"]
    assert fehlercode(rueckgaengig(api, u["id"], 409)) == "bereits_rueckgaengig"
    # r wirkt noch, aber das Konto existiert nicht mehr: Zustandsprüfung schlägt fehl
    assert fehlercode(rueckgaengig(api, r["id"], 409)) == "rueckgaengig_konflikt"
    assert "Neu" not in [k["name"] for k in api.konten()]
    rueckgaengig(api, u2["id"])
    assert "Neu" in [k["name"] for k in api.konten()]
    assert fehlercode(rueckgaengig(api, 999999, 404)) == "nicht_gefunden"


def test_rueckgaengig_ignoriert_status_und_sperre(api):
    """E-048: Statusänderung auf abgeglichen lässt sich zurücknehmen (abgeglichen → bestätigt)."""
    g, l, h = _konten(api)
    b = api.buchung("2024-03-01", [(g["id"], -500), (l["id"], 500)])
    vor = letzte_aenderung_id(api)
    api.patch(f"/api/buchungen/{b['id']}", json={"status": "abgeglichen"}, erwartet=200)
    (a,) = aenderungen_seit(api, vor)
    rueckgaengig(api, a["id"])
    assert api.buchung_lesen(b["id"])["status"] == "bestaetigt"


# ------------------------------------------------------------ Hypothesis
OPS = st.sampled_from(["buchung", "erfassen", "aendern", "kategorie", "splits", "loeschen", "tag_neu", "tag_um",
                       "tag_weg", "taggen", "konto_neu", "konto_weg", "empfaenger_neu", "empfaenger_um",
                       "empfaenger_zus", "regel_neu", "status"])


def _ausfuehren(api, op: str, n: int, wahl) -> None:
    """Führt eine zufällige, meist gültige Operation aus (Fehlerantworten sind erlaubt)."""
    konten = api.konten()
    bestand_k = [k for k in konten if k["art"] in ("girokonto", "sparkonto", "kreditkonto")]
    kats = [k for k in konten if k["art"] in ("aufwand", "ertrag")]
    bs = api.alle_buchungen()
    tags = api.get("/api/tags", erwartet=200).daten
    emp = api.get("/api/empfaenger", erwartet=200).daten
    ok = (200, 201, 204, 404, 409, 422)
    if op == "buchung" and bestand_k and kats:
        api.post("/api/buchungen", json={"datum": f"2024-0{1 + n % 9}-1{n % 10}", "splits": [
            {"konto_id": wahl(bestand_k)["id"], "betrag": -(n + 1), "memo": f"m{n}"},
            {"konto_id": wahl(kats)["id"], "betrag": n + 1}],
            "tag_ids": [wahl(tags)["id"]] if tags else [],
            "empfaenger_id": wahl(emp)["id"] if emp else None}, erwartet=201)
    elif op == "erfassen" and bestand_k:
        api.post("/api/buchungen/erfassen", json={"art": wahl(["ausgabe", "einnahme", "korrektur"]),
                                                  "datum": "2024-05-05", "konto_id": wahl(bestand_k)["id"],
                                                  "betrag": n + 3, "empfaenger_name": f"Laden {n % 3}"},
                 erwartet=201)
    elif op == "aendern" and bs:
        api.patch(f"/api/buchungen/{wahl(bs)['id']}", json={"verwendungszweck": f"v{n}", "datum": "2024-02-0"
                                                            + str(1 + n % 9)}, erwartet=ok)
    elif op == "kategorie" and bs and kats:
        api.put(f"/api/buchungen/{wahl(bs)['id']}/kategorie", json={"kategorie_id": wahl(kats)["id"]}, erwartet=ok)
    elif op == "splits" and bs and kats:
        b = wahl(bs)
        api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": [
            {"konto_id": b["splits"][0]["konto_id"], "betrag": -10 * (n + 1)},
            {"konto_id": wahl(kats)["id"], "betrag": 4 * (n + 1)}, {"konto_id": wahl(kats)["id"],
                                                                    "betrag": 6 * (n + 1)}]}, erwartet=ok)
    elif op == "loeschen" and bs:
        api.delete(f"/api/buchungen/{wahl(bs)['id']}", erwartet=ok)
    elif op == "tag_neu":
        api.post("/api/tags", json={"name": f"Tag {n % 4}"}, erwartet=ok)
    elif op == "tag_um" and tags:
        api.patch(f"/api/tags/{wahl(tags)['id']}", json={"name": f"Tag {n % 5}"}, erwartet=ok)
    elif op == "tag_weg" and tags:
        api.delete(f"/api/tags/{wahl(tags)['id']}", erwartet=ok)
    elif op == "taggen" and bs and tags:
        api.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": [wahl(bs)["id"]],
                                                       "hinzufuegen": [wahl(tags)["id"]],
                                                       "entfernen": [wahl(tags)["id"]]}, erwartet=ok)
    elif op == "konto_neu":
        api.post("/api/konten", json={"name": f"K{n}", "art": wahl(["aufwand", "ertrag", "girokonto"])}, erwartet=ok)
    elif op == "konto_weg" and konten:  # W-001: ein Buch ohne Konten ist gültig, dann ohne Wirkung
        api.delete(f"/api/konten/{wahl(konten)['id']}", erwartet=ok)
    elif op == "empfaenger_neu":
        api.post("/api/empfaenger", json={"name": f"E{n % 4}", "aliase": [f"Alias {n % 3}"]}, erwartet=ok)
    elif op == "empfaenger_um" and emp:
        # ab M32 ohne Standardkategorie (sammel3.md 2.1, E-307)
        api.patch(f"/api/empfaenger/{wahl(emp)['id']}", json={"aliase": [f"Alias {n % 6}"]}, erwartet=ok)
    elif op == "empfaenger_zus" and len(emp) >= 2:
        z, q = emp[0], wahl(emp[1:])
        api.post(f"/api/empfaenger/{z['id']}/zusammenfuehren", json={"quelle_ids": [q["id"]]}, erwartet=ok)
    elif op == "regel_neu" and kats:
        api.post("/api/regeln", json={"name": f"R{n}", "kategorie_id": wahl(kats)["id"],
                                      "bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt",
                                                       "wert": "v"}]}, erwartet=ok)
    elif op == "status" and bs:
        api.patch(f"/api/buchungen/{wahl(bs)['id']}", json={"status": wahl(["bestaetigt", "abgeglichen"])},
                  erwartet=ok)


_KLASSE = {"girokonto": "bestand", "sparkonto": "bestand", "kreditkonto": "bestand"}


def _kontonamen_eindeutig(z: dict) -> bool:
    """M32: unter einem Elternkonto (oberste Ebene: je Klasse) kein Name doppelt (strip, casefold)."""
    gesehen = set()
    for (objekt, _), k in z.items():
        if objekt != "konto":
            continue
        ebene = k["eltern_id"] if k["eltern_id"] is not None else "oben:" + _KLASSE.get(k["art"], k["art"])
        schluessel = (ebene, k["name"].strip().casefold())
        if schluessel in gesehen:
            return False
        gesehen.add(schluessel)
    return True


@given(ops=st.lists(st.tuples(OPS, st.integers(0, 50)), min_size=1, max_size=12), data=st.data())
def test_zufaellige_folgen_rueckwaerts(api_fabrik, ops, data):
    api = api_fabrik()
    api.konto("Giro")
    api.konto("Lebensmittel", "aufwand")
    zustaende = [bestand(api)]
    gelesen = [zustand_m3(api)]
    wirksame: list[int] = []
    for op, n in ops:
        vor = letzte_aenderung_id(api)
        _ausfuehren(api, op, n, lambda xs: data.draw(st.sampled_from(xs)))
        neu = aenderungen_seit(api, vor)
        z = bestand(api)
        assert len(neu) <= 1
        if neu:
            pruefe_eintraege(neu[0], zustaende[-1], z)
            zustaende.append(z)
            gelesen.append(zustand_m3(api))
            wirksame.append(neu[0]["id"])
        else:
            assert z == zustaende[-1], f"{op}: Bestand geändert ohne Änderung im Protokoll (T 3.5)"
        _summen_ok(api)
    for aid in reversed(wirksame):
        rueckgaengig(api, aid)
        zustaende.pop()
        gelesen.pop()
        assert bestand(api) == zustaende[-1]
        assert zustand_m3(api) == gelesen[-1], "abgeleitete Sichten (Salden, Tags) exakt wie vorher"
        _summen_ok(api)


@given(ops=st.lists(st.tuples(OPS, st.integers(0, 50)), min_size=2, max_size=10), data=st.data())
def test_zufaelliges_rueckgaengig_gegen_orakel(api_fabrik, ops, data):
    """Rückgängig einer beliebigen wirksamen Änderung gelingt genau dann, wenn Zustand und Bezüge passen."""
    api = api_fabrik()
    api.konto("Giro")
    api.konto("Lebensmittel", "aufwand")
    for op, n in ops:
        _ausfuehren(api, op, n, lambda xs: data.draw(st.sampled_from(xs)))
    kandidaten = alle_aenderungen(api, wirksam=True)
    if not kandidaten:
        return
    a = data.draw(st.sampled_from(kandidaten))
    z = bestand(api)
    zustand_passt = all(z.get((e["objekt"], e["objekt_id"])) == e["nachher"] for e in a["eintraege"])
    ziel = dict(z)
    for e in a["eintraege"]:
        k = (e["objekt"], e["objekt_id"])
        if e["vorher"] is None:
            ziel.pop(k, None)
        else:
            ziel[k] = e["vorher"]
    soll_ok = zustand_passt and bezuege_ok(ziel)
    namen_doppelt = soll_ok and not _kontonamen_eindeutig(ziel)   # M32 (sammel3.md 1.2, E-295/E-307)
    r = rueckgaengig(api, a["id"], (200, 409))
    if soll_ok and not namen_doppelt:
        assert r.status_code == 200, f"Rückgängig von {a['aktion']} hätte gelingen müssen: {r.text[:500]}"
        assert bestand(api) == ziel
    else:
        code = "konto_existiert" if namen_doppelt else "rueckgaengig_konflikt"
        assert r.status_code == 409 and fehlercode(r) == code
        assert bestand(api) == z
    _summen_ok(api)
