"""M4: Änderungsprotokoll und Rückgängig für die neuen Operationen (protokoll.md 9; T 3.5, T 3.6).

Erwartete Einträge werden aus den Lese-Endpunkten abgeleitet (Protokollform,
``tests/hilfen/m4.bestand`` inkl. Vorlagen), nie aus dem Protokoll selbst.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from generator.gnucash import GBuch, GBuchung, GKonto, GSplit, als_gnc_xml, guid
from tests.hilfen.api import fehlercode
from tests.hilfen.m3 import aenderungen_seit, alle_aenderungen, letzte_aenderung_id
from tests.hilfen.m4 import GNC, bestand, import_gnc, pruefe_eintraege


def _rundreise(api, a, vorher, nachher):
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert (u["quelle"], u["aktion"], u["rueckgaengig_von"]) == ("rueckgaengig", "rueckgaengig", [a["id"]])
    assert bestand(api) == vorher
    pruefe_eintraege(u, nachher, vorher)
    api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200)
    assert bestand(api) == nachher


@pytest.mark.kern
@pytest.mark.parametrize("name", ["minimal", "minimal.sqlite", "sonderfaelle"])
def test_gnucash_import_eine_aenderung_und_rueckgaengig(api, name):
    api.konto("Vorher", "aufwand")
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    r = import_gnc(api, GNC / f"{name}.gnucash").daten
    nachher = bestand(api)
    (a,) = aenderungen_seit(api, a0)
    assert (a["quelle"], a["aktion"], a["gruppe"]) == ("import", "import_gnucash", f"import:{r['import_id']}")
    pruefe_eintraege(a, vorher, nachher)
    _rundreise(api, a, vorher, nachher)
    # Gruppe rückgängig, danach erneuter Import bringt alles wieder (Importvorgänge bleiben, protokoll.md 1)
    api.post("/api/aenderungen/rueckgaengig", json={"gruppe": f"import:{r['import_id']}"}, erwartet=200)
    assert bestand(api) == vorher
    r2 = import_gnc(api, GNC / f"{name}.gnucash").daten
    assert (r2["buchungen_neu"], r2["konten_neu"], r2["kategorien_neu"]) == (
        r["buchungen_neu"], r["konten_neu"], r["kategorien_neu"]), "nach dem Rückgängig ist alles wieder neu"
    assert len(api.get("/api/importe", erwartet=200).daten) == 2


@pytest.mark.kern
def test_vorschlag_mit_sicherheit_in_der_protokollform(api):
    """Der Lernmodell-Vorschlag (mit sicherheit) gehört zur Protokollform der Buchung (protokoll.md 2)."""
    g, k, ek = api.konto("G")["id"], api.konto("K", "aufwand")["id"], api.konto("E", "eigenkapital")["id"]
    e = api.empfaenger("Laden")["id"]
    for _ in range(3):
        api.buchung("2024-01-01", [(g, -100), (k, 100)], empfaenger_id=e)
    x = api.buchung("2024-01-05", [(g, -100), (ek, 100)], empfaenger_id=e)
    vorher, a0 = bestand(api), letzte_aenderung_id(api)
    api.post("/api/lernmodell/anwenden", json={}, erwartet=200)
    (a,) = aenderungen_seit(api, a0)
    (eintrag,) = a["eintraege"]
    assert eintrag["objekt_id"] == x["id"] and eintrag["nachher"]["vorschlag"]["sicherheit"] == 1000
    _rundreise(api, a, vorher, bestand(api))


# ------------------------------------------------------------- Hypothesis
OPS = st.sampled_from(["buchung", "kategorie", "vorlage_neu", "vorlage_um", "vorlage_weg", "vorlagen_anwenden",
                       "lernmodell_anwenden", "gnucash", "konto_weg", "splits"])


def _gnc(n: int) -> bytes:
    g = lambda x: guid(f"proto{n % 3}:{x}")  # noqa: E731
    gb = GBuch(g("b"), g("r"), [GKonto(g("giro"), "Giro", "BANK", g("r")), GKonto(g("k"), "Kat", "EXPENSE", g("r"))])
    gb.buchungen = [GBuchung(g(f"t{i}"), f"2024-02-0{i + 1} 10:59:00 +0000",
                             [GSplit(g("giro"), -300, guid=g(f"s{i}a")), GSplit(g("k"), 300, guid=g(f"s{i}b"))],
                             beschreibung="Fiktiva AG") for i in range(1 + n % 3)]
    return als_gnc_xml(gb)


def _ausfuehren(api, op: str, n: int, wahl) -> None:
    konten = api.konten()
    bestand_k = [k for k in konten if k["art"] == "girokonto"]
    kats = [k for k in konten if k["art"] == "aufwand"]
    ek = [k for k in konten if k["art"] == "eigenkapital"]
    bs = api.alle_buchungen()
    vs = api.get("/api/vorlagen", erwartet=200).daten
    ok = (200, 201, 204, 404, 409, 422)
    emp = api.get("/api/empfaenger", erwartet=200).daten
    if op == "buchung" and bestand_k and (kats or ek):
        api.post("/api/buchungen", json={"datum": "2024-03-01", "splits": [
            {"konto_id": wahl(bestand_k)["id"], "betrag": -300 - n % 2},
            {"konto_id": wahl(kats + ek)["id"], "betrag": 300 + n % 2}],
            "empfaenger_id": wahl(emp)["id"] if emp else None}, erwartet=201)
    elif op == "kategorie" and bs and kats:
        api.put(f"/api/buchungen/{wahl(bs)['id']}/kategorie", json={"kategorie_id": wahl(kats)["id"]}, erwartet=ok)
    elif op == "vorlage_neu" and len(kats) >= 1:
        api.post("/api/vorlagen", json={"name": f"V{n}", "bedingungen": [
            {"feld": "empfaenger", "operator": "enthaelt", "wert": "fiktiva"}],
            "teile": [{"kategorie_id": wahl(kats)["id"], "betrag": 100}, {"kategorie_id": wahl(kats)["id"],
                                                                          "betrag": 200 + n % 2}]}, erwartet=ok)
    elif op == "vorlage_um" and vs:
        api.patch(f"/api/vorlagen/{wahl(vs)['id']}", json={"prioritaet": n, "aktiv": n % 4 != 0}, erwartet=ok)
    elif op == "vorlage_weg" and vs:
        api.delete(f"/api/vorlagen/{wahl(vs)['id']}", erwartet=ok)
    elif op == "vorlagen_anwenden":
        api.post("/api/vorlagen/anwenden", json={"nur_unkategorisiert": n % 2 == 0}, erwartet=200)
    elif op == "lernmodell_anwenden":
        api.post("/api/lernmodell/anwenden", json={}, erwartet=200)
    elif op == "gnucash":
        import_gnc(api, _gnc(n))
    elif op == "konto_weg" and konten:
        api.delete(f"/api/konten/{wahl(konten)['id']}", erwartet=ok)
    elif op == "splits" and bs and kats:
        b = wahl(bs)
        api.put(f"/api/buchungen/{b['id']}/splits", json={"splits": [
            {"konto_id": b["splits"][0]["konto_id"], "betrag": -300}, {"konto_id": wahl(kats)["id"], "betrag": 300}]},
            erwartet=ok)


@pytest.mark.kern
@given(ops=st.lists(st.tuples(OPS, st.integers(0, 30)), min_size=1, max_size=10), data=st.data())
def test_zufaellige_folgen_rueckwaerts(api_fabrik, ops, data):
    """T 3.5/3.6 mit M4-Operationen: jede Wirkung genau eine Änderung, rückwärts exakt wiederhergestellt."""
    api = api_fabrik()
    api.konto("Giro")
    api.konto("Kat", "aufwand")
    api.konto("Offen", "eigenkapital")
    api.empfaenger("Fiktiva AG")
    zustaende = [bestand(api)]
    wirksame: list[int] = []
    for op, n in ops:
        vor = letzte_aenderung_id(api)
        _ausfuehren(api, op, n, lambda xs: data.draw(st.sampled_from(xs)))
        neu = aenderungen_seit(api, vor)
        z = bestand(api)
        assert len(neu) <= 1, [a["aktion"] for a in neu]
        if neu:
            pruefe_eintraege(neu[0], zustaende[-1], z)
            zustaende.append(z)
            wirksame.append(neu[0]["id"])
        else:
            assert z == zustaende[-1], f"{op}: Bestand geändert ohne Änderung im Protokoll (T 3.5)"
        for b in api.alle_buchungen():
            assert sum(s["betrag"] for s in b["splits"]) == 0
    for aid in reversed(wirksame):
        r = api.post(f"/api/aenderungen/{aid}/rueckgaengig", erwartet=200)
        assert r.status_code == 200
        zustaende.pop()
        assert bestand(api) == zustaende[-1]
    assert fehlercode(api.post("/api/aenderungen/999999/rueckgaengig", erwartet=404)) == "nicht_gefunden"
    assert all(a["quelle"] in ("manuell", "import", "vorlage", "lernmodell", "rueckgaengig")
               for a in alle_aenderungen(api))
