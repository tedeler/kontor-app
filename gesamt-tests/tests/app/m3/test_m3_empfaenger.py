"""M3: Empfängerverwaltung – Aliase, Standardkategorie, Ändern, Löschen, Zusammenführen (buchhaltungspflege.md 2, T 14).

Erwartungen: Stammdaten-Wahrheit des Generators (``mock/m3_daten.erwartung.json``, ``kmy/m3_aliase``) und
unabhängige Nachrechnung der Alias-Regeln mit ``ekey`` aus ``tests/hilfen/normal.py``.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.erwartung import lade
from tests.hilfen.m2 import nach_kennung, sync
from tests.hilfen.m3 import UNKATEGORISIERT, konto_id, lade_m3, m3_api, stammdaten_anlegen, vorschlag_soll
from tests.hilfen.normal import ekey
from tests.hilfen.pfade import KMY

VON = "2024-01-01"


def _neu(api, name, erwartet=201, **felder):
    return api.post("/api/empfaenger", json={"name": name, **felder}, erwartet=erwartet)


@pytest.mark.kern
def test_felder_und_vorgaben(api):
    e = api.empfaenger("Laden")
    assert (e["aliase"], e["standardkategorie_id"]) == ([], None)
    k = api.konto("Lebensmittel", "aufwand")
    # ab M32 keine Standardkategorie mehr (sammel3.md 2.1, E-307): ein Wert ≠ null wird abgelehnt
    assert fehlercode(_neu(api, "Bäckerei", 422, standardkategorie_id=k["id"])) == "kategorie_ungueltig"
    f = _neu(api, "Bäckerei", aliase=["  Zweite Schreibweise ", "BAECKEREI KORN", "baeckerei-korn", "Andere"],
             standardkategorie_id=None).daten
    assert f["aliase"] == ["Andere", "BAECKEREI KORN", "Zweite Schreibweise"], "gestrippt, nach ekey zusammengefasst, sortiert"
    assert f["standardkategorie_id"] is None
    assert api.get(f"/api/empfaenger/{f['id']}", erwartet=200).daten == f
    assert api.get("/api/empfaenger", erwartet=200).daten == [e, f]


@pytest.mark.kern
@pytest.mark.parametrize("aliase", [[""], ["   "], ["!!! ---"], ["x" * 201], [f"A{i}" for i in range(101)], ["ok", 5]],
                         ids=["leer", "leerraum", "ekey_leer", "zu_lang", "zu_viele", "kein_text"])
def test_alias_validierung(api, aliase):
    e = api.empfaenger("Laden")
    assert fehlercode(_neu(api, "Neu", 422, aliase=aliase)) == "validierung"
    assert fehlercode(api.patch(f"/api/empfaenger/{e['id']}", json={"aliase": aliase}, erwartet=422)) == "validierung"
    assert api.get("/api/empfaenger", erwartet=200).daten == [e]


@pytest.mark.kern
def test_alias_eindeutig(api):
    a = _neu(api, "Stadtwerke", aliase=["SWM GmbH"]).daten
    r = _neu(api, "Andere", 409, aliase=["swm-gmbh"])
    assert fehlercode(r) == "alias_existiert" and r.json()["fehler"]["details"]["empfaenger_id"] == a["id"]
    b = api.empfaenger("Zweite")
    assert fehlercode(api.patch(f"/api/empfaenger/{b['id']}", json={"aliase": ["S.W.M. GMBH"]},
                                erwartet=409)) == "alias_existiert"
    assert api.patch(f"/api/empfaenger/{a['id']}", json={"aliase": ["SWM GmbH", "stadtwerke"]},
                     erwartet=200).daten["aliase"] == ["SWM GmbH", "stadtwerke"], "eigener Name ist kein Konflikt"
    assert api.get(f"/api/empfaenger/{b['id']}", erwartet=200).daten["aliase"] == []


@pytest.mark.kern
def test_aendern_und_loeschen(api):
    g = api.konto("Giro")
    k = api.konto("Strom", "aufwand")
    a = api.empfaenger("Stadtwerke")
    b = api.empfaenger("Anderer")
    assert fehlercode(api.patch(f"/api/empfaenger/{a['id']}", json={"name": "Anderer"}, erwartet=409)) == \
        "empfaenger_existiert"
    for kid in (g["id"], 999999):
        assert fehlercode(api.patch(f"/api/empfaenger/{a['id']}", json={"standardkategorie_id": kid},
                                    erwartet=422)) == "kategorie_ungueltig"
    assert fehlercode(_neu(api, "Dritter", 422, standardkategorie_id=g["id"])) == "kategorie_ungueltig"
    assert fehlercode(api.patch(f"/api/empfaenger/{a['id']}", json={"standardkategorie_id": k["id"]},
                                erwartet=422)) == "kategorie_ungueltig", "ab M32 (sammel3.md 2.1)"
    neu = api.patch(f"/api/empfaenger/{a['id']}", json={"name": " Stadtwerke Musterstadt ", "standardkategorie_id":
                                                        None}, erwartet=200).daten
    assert (neu["name"], neu["standardkategorie_id"], neu["aliase"]) == ("Stadtwerke Musterstadt", None, [])
    assert api.patch(f"/api/empfaenger/{a['id']}", json={"name": "Stadtwerke Musterstadt"}, erwartet=200)
    bu = api.buchung("2024-01-05", [(g["id"], -100), (k["id"], 100)], empfaenger_id=a["id"])
    assert api.buchung_lesen(bu["id"])["empfaenger"] == {"id": a["id"], "name": "Stadtwerke Musterstadt"}
    assert fehlercode(api.delete(f"/api/konten/{k['id']}", erwartet=409)) == "konto_in_verwendung"
    assert fehlercode(api.delete(f"/api/empfaenger/{a['id']}", erwartet=409)) == "empfaenger_in_verwendung"
    api.delete(f"/api/empfaenger/{b['id']}", erwartet=204)
    assert fehlercode(api.delete(f"/api/empfaenger/{b['id']}", erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.patch("/api/empfaenger/999999", json={"name": "x"}, erwartet=404)) == "nicht_gefunden"
    api.patch(f"/api/empfaenger/{a['id']}", json={"standardkategorie_id": None}, erwartet=200)
    leer = api.konto("Unbenutzt", "aufwand")
    assert fehlercode(api.patch(f"/api/empfaenger/{a['id']}", json={"standardkategorie_id": leer["id"]},
                                erwartet=422)) == "kategorie_ungueltig"
    api.delete(f"/api/konten/{leer['id']}", erwartet=204)   # kein Empfänger verweist mehr auf eine Kategorie


def _aliase_nach_zusammenfuehren(ziel: dict, quellen: list[dict], dritte: list[dict]) -> list[str]:
    """buchhaltungspflege.md 2.4 Schritt 3, unabhängig nachgerechnet."""
    belegt = {ekey(a) for d in dritte for a in d["aliase"]}
    aus: list[str] = []
    schl: set[str] = set()
    for kand in list(ziel["aliase"]) + [x for q in sorted(quellen, key=lambda q: q["id"])
                                        for x in [q["name"], *q["aliase"]]]:
        k = ekey(kand)
        if not k or k == ekey(ziel["name"]) or k in schl or k in belegt:
            continue
        schl.add(k)
        aus.append(kand)
    return sorted(aus)


@pytest.mark.kern
def test_zusammenfuehren(api):
    g = api.konto("Giro")
    kat = api.konto("Strom", "aufwand")
    z = _neu(api, "Stadtwerke Musterstadt", aliase=["SWM"]).daten   # ab M32 ohne Standardkategorie (E-307)
    q1 = _neu(api, "STADTWERKE MUSTERSTADT", aliase=["Stadtwerke MS", "SWM Ost"]).daten
    q2 = _neu(api, "Stadtwerke Musterstadt GmbH", aliase=["Energie Nord"]).daten
    dritter = _neu(api, "Netzbetreiber", aliase=["STADTWERKE-MUSTERSTADT-GMBH"]).daten
    q3 = _neu(api, "– – –").daten
    bs = [api.buchung(f"2024-01-0{i + 1}", [(g["id"], -100 - i), (kat["id"], 100 + i)], empfaenger_id=e["id"])
          for i, e in enumerate([z, q1, q2, q1, dritter])]
    api.patch(f"/api/buchungen/{bs[1]['id']}", json={"status": "abgeglichen"}, erwartet=200)
    vorher = {b["id"]: api.buchung_lesen(b["id"]) for b in bs}
    soll = _aliase_nach_zusammenfuehren(z, [q1, q2, q3], [dritter])
    r = api.post(f"/api/empfaenger/{z['id']}/zusammenfuehren", json={"quelle_ids": [q2["id"], q1["id"], q3["id"]]},
                 erwartet=200).daten
    assert r == {**z, "aliase": soll}
    assert "STADTWERKE MUSTERSTADT" not in soll, "gleicher ekey wie der Zielname entfällt"
    assert "Stadtwerke Musterstadt GmbH" not in soll, "Alias eines dritten Empfängers entfällt"
    assert "– – –" not in soll and "Energie Nord" in soll and "SWM Ost" in soll
    ids = {e["id"] for e in api.get("/api/empfaenger", erwartet=200).daten}
    assert ids == {z["id"], dritter["id"]}
    for b in bs:
        nach = api.buchung_lesen(b["id"])
        alt = vorher[b["id"]]
        erwartet_e = alt["empfaenger"] if alt["empfaenger"]["id"] == dritter["id"] else {"id": z["id"],
                                                                                         "name": z["name"]}
        assert nach == {**alt, "empfaenger": erwartet_e}, "auch gesperrte Buchungen werden umgeordnet (E-049)"


@pytest.mark.kern
def test_zusammenfuehren_fehler(api):
    a = api.empfaenger("A")
    b = api.empfaenger("B")
    vorher = api.get("/api/empfaenger", erwartet=200).daten
    assert fehlercode(api.post("/api/empfaenger/999999/zusammenfuehren", json={"quelle_ids": [b["id"]]},
                               erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.post(f"/api/empfaenger/{a['id']}/zusammenfuehren", json={"quelle_ids": [a["id"]]},
                               erwartet=422)) == "validierung"
    r = api.post(f"/api/empfaenger/{a['id']}/zusammenfuehren", json={"quelle_ids": [b["id"], 999998, 999997]},
                 erwartet=422)
    assert fehlercode(r) == "referenz_unbekannt" and r.json()["fehler"]["details"]["empfaenger_ids"] == [999997, 999998]
    for k in ({"quelle_ids": []}, {"quelle_ids": [b["id"], b["id"]]}, {}):
        assert fehlercode(api.post(f"/api/empfaenger/{a['id']}/zusammenfuehren", json=k, erwartet=422)) == \
            "validierung"
    assert api.get("/api/empfaenger", erwartet=200).daten == vorher


@pytest.mark.kern
def test_abruf_mit_stammdaten(tmp_path, netz_gesperrt):
    """Aliase und (ab M32) die umgewandelten Regeln der Standardkategorien greifen beim Abruf; die Stammregeln haben
    Vorrang (Wahrheit des Generators, E-307)."""
    api = m3_api(tmp_path)
    daten, erw = lade_m3()
    s = stammdaten_anlegen(api)
    lauf = sync(api, von=VON)
    assert lauf["status"] == "erfolgreich"
    bank = nach_kennung(api.alle_buchungen())
    unk = konto_id(api, UNKATEGORISIERT)
    kategorisiert: dict[str, int] = {}
    for u in daten["bank"]["umsaetze"]:
        if u["vormerkung"]:
            continue
        w = erw["stammdaten"][u["umsatz_id"]]
        b = bank[f"bank:{u['iban']}:{u['umsatz_id']}"]
        assert (b["empfaenger"]["name"] if b["empfaenger"] else None) == w["empfaenger"], u["umsatz_id"]
        if w["stamm_empfaenger"]:
            assert b["empfaenger"]["id"] == s["empfaenger"][w["stamm_empfaenger"]]["id"]
        if w["kategorie"] is None:
            assert b["kategorie_id"] is None and b["vorschlag"] is None
        else:
            kat = s["kategorien"][w["kategorie"]]
            assert b["kategorie_id"] == kat
            quelle, rid = vorschlag_soll(w, s)
            assert b["vorschlag"] == {"kategorie_id": kat, "quelle": quelle, "vorher_konto_id": unk, "regel_id": rid}
            kategorisiert[u["iban"]] = kategorisiert.get(u["iban"], 0) + 1
    for k in lauf["konten"]:
        assert k["buchungen_kategorisiert"] == kategorisiert.get(k["iban"], 0)
    namen = [e["name"] for e in api.get("/api/empfaenger", erwartet=200).daten]
    assert len(namen) == len(set(namen))
    assert erw["nfd_name"] in namen, "zerlegte Umlaute passen nicht über ekey (eigener Empfänger)"


@pytest.mark.kern
def test_standardkategorie_abgelehnt(tmp_path, netz_gesperrt):
    """Ab M32 (sammel3.md 2.1, E-307; ersetzt test_standardkategorie_vorschlag_entscheiden): keine Standardkategorie,
    keine Vorschläge mit quelle „standardkategorie“; die umgewandelten Regeln liefern Vorschläge der Quelle regel,
    die sich wie bisher annehmen und ablehnen lassen."""
    api = m3_api(tmp_path)
    s = stammdaten_anlegen(api, regeln=False)
    sync(api, von=VON)
    unk = konto_id(api, UNKATEGORISIERT)
    std = api.alle_buchungen(vorschlag=True)
    ids = {r["id"] for r in s["std_regeln"].values()}
    assert std and all(b["vorschlag"]["quelle"] == "regel" and b["vorschlag"]["regel_id"] in ids for b in std)
    a, b = std[0], std[1]
    api.post(f"/api/buchungen/{a['id']}/vorschlag", json={"aktion": "annehmen"}, erwartet=200)
    assert api.buchung_lesen(a["id"])["kategorie_id"] == a["kategorie_id"]
    nb = api.post(f"/api/buchungen/{b['id']}/vorschlag", json={"aktion": "ablehnen"}, erwartet=200).daten
    assert nb["kategorie_id"] is None and nb["vorschlag"] is None
    assert any(sp["konto_id"] == unk for sp in nb["splits"])
    vorher = api.alle_buchungen()
    e = s["empfaenger"]["Café Bohne"]["id"]
    r = api.patch(f"/api/empfaenger/{e}", json={"standardkategorie_id": s["kategorien"]["Sonstiges"]}, erwartet=422)
    assert fehlercode(r) == "kategorie_ungueltig"
    assert api.alle_buchungen() == vorher
    assert all(x["standardkategorie_id"] is None for x in api.get("/api/empfaenger", erwartet=200).daten)


@pytest.mark.kern
def test_alias_beim_kmymoney_import(api):
    stammdaten_anlegen(api, regeln=False)
    erw = lade("m3_aliase")
    vorher = {e["name"]: e for e in api.get("/api/empfaenger", erwartet=200).daten}
    r = api.import_kmy(KMY / "m3_aliase.kmy", erwartet=200).daten
    soll = erw["alias_zuordnung"]
    assert r["empfaenger_neu"] == sum(z["regel"] == "neu" for z in soll.values())
    assert r["empfaenger_vorhanden"] == sum(z["regel"] != "neu" for z in soll.values())
    nachher = {e["name"]: e for e in api.get("/api/empfaenger", erwartet=200).daten}
    for name, e in vorher.items():
        assert nachher[name] == e, "zugeordnete Empfänger werden nicht verändert"
    bs = nach_kennung(api.alle_buchungen(), "kmy:")
    for b in erw["buchungen"]:
        tid = b["extern_id"]
        payee = b["empfaenger"]
        got = bs[tid]["empfaenger"]
        if payee is None:
            assert got is None
            continue
        pid = next(p["extern_id"] for p in erw["empfaenger"] if p["name"] == payee).removeprefix("kmy:")
        assert got["name"] == soll[pid]["empfaenger"], tid
    zweiter = api.import_kmy(KMY / "m3_aliase.kmy", erwartet=200).daten
    assert zweiter["buchungen_neu"] == zweiter["empfaenger_neu"] == 0


@pytest.mark.kern
def test_zusammengefuehrte_namen_greifen_beim_import(api):
    """T 14: Nach dem Zusammenführen ordnet ein neuer Import die alte Schreibweise dem Ziel zu."""
    ziel = api.empfaenger("Stadtwerke Musterstadt")
    alt = api.empfaenger("STADTWERKE MUSTERSTADT GMBH")
    api.post(f"/api/empfaenger/{ziel['id']}/zusammenfuehren", json={"quelle_ids": [alt["id"]]}, erwartet=200)
    api.import_kmy(KMY / "m3_aliase.kmy", erwartet=200)
    bs = [b for b in api.alle_buchungen() if b["verwendungszweck"] == "Abschlag Strom 12/2023"]
    assert len(bs) == 1 and bs[0]["empfaenger"]["id"] == ziel["id"]


def test_ohne_stammdaten_wie_m2(tmp_path, netz_gesperrt):
    api = m3_api(tmp_path)
    daten, _ = lade_m3()
    sync(api, von=VON)
    namen = {e["name"] for e in api.get("/api/empfaenger", erwartet=200).daten}
    assert namen == {(u["gegenpartei_name"] or "").strip() for u in daten["bank"]["umsaetze"]
                     if not u["vormerkung"]} - {""}
    assert all(e["aliase"] == [] for e in api.get("/api/empfaenger", erwartet=200).daten)
    assert api.alle_buchungen(vorschlag=True) == []
