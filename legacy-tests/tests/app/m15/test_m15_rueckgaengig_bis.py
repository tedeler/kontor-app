"""M15: Rückgängig bis zu einer Änderung (protokoll.md 6.2a, E-182).

Erwartet wird der Abzug des Buchbestands unmittelbar vor der Änderung ``bis_id`` (tests/hilfen/m15.Verlauf); die
Menge ``rueckgaengig_von`` und die Wirksamkeit aller Änderungen berechnet das Modell ``m15.Wirksamkeit`` aus den im
Test ausgelösten Operationen.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from tests.hilfen.api import fehlercode
from tests.hilfen.m2 import SYNC_DATEN, mock_api, nach_kennung, setze_zeit, sync
from tests.hilfen.m6 import bestand
from tests.hilfen.m15 import RUECKGAENGIG, Verlauf, ohne_wirkung, pruefe_wirksamkeit
from tests.hilfen.pfade import KMY

VON = "2024-01-01"


@pytest.fixture
def k(api):
    return {"giro": api.konto("Giro", "girokonto")["id"], "spar": api.konto("Spar", "sparkonto")["id"],
            "leb": api.konto("Lebensmittel", "aufwand")["id"]}


def _ops(api, k):
    """Kleine Operationen mit genau einer Änderung."""
    return {
        "tag": lambda name: api.tag(name)["id"],
        "umbenennen": lambda tid, name: api.patch(f"/api/tags/{tid}", json={"name": name}, erwartet=200),
        "buchung": lambda betrag: api.buchung("2024-03-01", [(k["giro"], -betrag), (k["leb"], betrag)])["id"],
        "zweck": lambda bid, text: api.patch(f"/api/buchungen/{bid}", json={"verwendungszweck": text}, erwartet=200),
    }


def _folge(api, k, v):
    """a1 Tag, a2 Buchung, a3 Tag umbenennen, a4 Verwendungszweck, a5 zweiter Tag."""
    o = _ops(api, k)
    ids, w = {}, {}
    ids["a1"] = v.eine(lambda: w.setdefault("t", o["tag"]("Urlaub")))
    ids["a2"] = v.eine(lambda: w.setdefault("b", o["buchung"](1234)))
    ids["a3"] = v.eine(lambda: o["umbenennen"](w["t"], "Reise"))
    ids["a4"] = v.eine(lambda: o["zweck"](w["b"], "geändert"))
    ids["a5"] = v.eine(lambda: o["tag"]("Steuer"))
    return ids, w


# ------------------------------------------------------------------ Grundfall


@pytest.mark.kern
def test_grundfall_bis_einschliesslich(api, k):
    v = Verlauf(api)
    a, _ = _folge(api, k, v)
    u = v.bis(a["a3"])
    assert u["rueckgaengig_von"] == [a["a3"], a["a4"], a["a5"]], "einschließlich bis_id, aufsteigend"
    for x in ("a3", "a4", "a5"):
        assert api.get(f"/api/aenderungen/{a[x]}", erwartet=200).daten["rueckgaengig_durch"] == u["id"]
    for x in ("a1", "a2"):
        assert api.get(f"/api/aenderungen/{a[x]}", erwartet=200).daten["rueckgaengig_durch"] is None


@pytest.mark.kern
def test_bis_neueste_nimmt_nur_diese_zurueck(api, k):
    v = Verlauf(api)
    a, _ = _folge(api, k, v)
    u = v.bis(a["a5"])
    assert u["rueckgaengig_von"] == [a["a5"]]


@pytest.mark.kern
def test_wiederholen_stellt_stand_und_wirksamkeit_her(api, k):
    """Rückgängig von U (Wiederholen) stellt den Stand vor U und die frühere Wirksamkeit her (6.2a Nr. 6)."""
    v = Verlauf(api)
    a, _ = _folge(api, k, v)
    vor_u = bestand(api)
    u = v.bis(a["a2"])
    r = v.zurueck(u["id"])
    assert bestand(api) == vor_u
    for x in a.values():
        assert api.get(f"/api/aenderungen/{x}", erwartet=200).daten["rueckgaengig_durch"] is None
    assert api.get(f"/api/aenderungen/{u['id']}", erwartet=200).daten["rueckgaengig_durch"] == r["id"]
    # danach erneut bis a2: U und R gehören als sich aufhebendes Paar dazu
    u2 = v.bis(a["a2"])
    assert u2["rueckgaengig_von"] == [a["a2"], a["a3"], a["a4"], a["a5"], u["id"], r["id"]]


# ------------------------------------------------------------------ Rückgängig dazwischen


@pytest.mark.kern
def test_rueckgaengig_und_wiederholen_dazwischen(api, k):
    """Ziele ≥ bis_id werden mit zurückgenommen, sich aufhebende Paare stehen in rueckgaengig_von."""
    v = Verlauf(api)
    o, w = _ops(api, k), {}
    a1 = v.eine(lambda: w.setdefault("A", o["tag"]("Alpha")))
    a2 = v.eine(lambda: w.setdefault("B", o["tag"]("Beta")))
    a3 = v.eine(lambda: o["umbenennen"](w["A"], "Alpha neu"))
    u4 = v.zurueck(a2)["id"]
    a5 = v.eine(lambda: w.setdefault("C", o["tag"]("Gamma")))
    r6 = v.zurueck(u4)["id"]
    a7 = v.eine(lambda: o["umbenennen"](w["C"], "Gamma neu"))
    u = v.bis(a2)
    assert u["rueckgaengig_von"] == [a2, a3, u4, a5, r6, a7]
    assert {t["name"] for t in api.get("/api/tags", erwartet=200).daten} == {"Alpha"}
    assert api.get(f"/api/aenderungen/{a1}", erwartet=200).daten["rueckgaengig_durch"] is None


@pytest.mark.kern
def test_aelteres_ziel_bleibt_wiederhergestellt(api, k):
    """Ein zurückgenommenes Rückgängig lässt sein Ziel < bis_id wieder wirken (6.2a Nr. 3)."""
    v = Verlauf(api)
    o, w = _ops(api, k), {}
    a1 = v.eine(lambda: w.setdefault("A", o["tag"]("Alpha")))
    v.eine(lambda: o["tag"]("Beta"))
    u3 = v.zurueck(a1)["id"]
    a4 = v.eine(lambda: o["tag"]("Gamma"))
    u = v.bis(u3)
    assert u["rueckgaengig_von"] == [u3, a4]
    assert {t["name"] for t in api.get("/api/tags", erwartet=200).daten} == {"Alpha", "Beta"}
    assert api.get(f"/api/aenderungen/{a1}", erwartet=200).daten["rueckgaengig_durch"] is None
    assert api.get(f"/api/aenderungen/{u3}", erwartet=200).daten["rueckgaengig_durch"] == u["id"]


@pytest.mark.kern
def test_bis_in_die_spanne_eines_frueheren_bis(api, k):
    """Beispiel aus protokoll.md 6.2a: U6 = bis 3, dann 7; bis 4 nimmt 7, U6, 5, 4 zurück, 3 wirkt wieder."""
    v = Verlauf(api)
    a, _ = _folge(api, k, v)
    u6 = v.bis(a["a3"])["id"]
    a7 = v.eine(lambda: api.tag("Neu nach U6"))
    u = v.bis(a["a4"])
    assert u["rueckgaengig_von"] == [a["a4"], a["a5"], u6, a7]
    assert api.get(f"/api/aenderungen/{a['a3']}", erwartet=200).daten["rueckgaengig_durch"] is None
    assert {t["name"] for t in api.get("/api/tags", erwartet=200).daten} == {"Reise"}


# ------------------------------------------------------------------ Import und Synchronisation


@pytest.mark.kern
def test_bis_import_und_lauf(tmp_path, netz_gesperrt):
    """Bis zur ersten Änderung eines Laufs bzw. Imports: Stand davor; ein erneuter Abruf bucht dieselben Umsätze
    wieder (protokoll.md 6.4)."""
    api = mock_api(tmp_path, daten=SYNC_DATEN)
    v = Verlauf(api)
    v.eine(lambda: api.tag("Vorher"))
    setze_zeit(api, "2024-06-01T10:00:00Z")
    imp = v.eine(lambda: api.import_kmy(KMY / "minimal.kmy", erwartet=200))
    setze_zeit(api, "2024-06-30T12:00:00Z")
    lauf = v.schritt(lambda: sync(api, von=VON))
    assert len(lauf) >= 2 and all(x["gruppe"] == lauf[0]["gruppe"] for x in lauf)
    kennungen = set(nach_kennung(api.alle_buchungen()))
    assert kennungen
    v.eine(lambda: api.tag("Danach"))
    u = v.bis(lauf[0]["id"])
    assert u["rueckgaengig_von"][0] == lauf[0]["id"]
    assert not nach_kennung(api.alle_buchungen())
    v.schritt(lambda: sync(api, von=VON))
    assert set(nach_kennung(api.alle_buchungen())) == kennungen, "Kennungen wurden vergessen (6.1 Schritt 4)"
    v.bis(imp)
    assert [b for b in api.alle_buchungen()] == []


# ------------------------------------------------------------------ Fehlerfälle


@pytest.mark.kern
def test_ohne_nettowirkung_bereits_rueckgaengig(api, k):
    """E-190: Ist der Stand schon der vor bis_id (Nettowirkung leer), antwortet 409 bereits_rueckgaengig, und es
    entsteht keine Änderung mit leeren Einträgen."""
    v = Verlauf(api)
    a, _ = _folge(api, k, v)
    v.bis(a["a1"])
    assert v.bis(a["a1"]) == {}
    v.bis(a["a3"])   # Stand vor a3 ≠ jetziger Stand (alles bis a1 zurück): wirkt


@pytest.mark.kern
@pytest.mark.parametrize("koerper", [
    {}, {"bis_id": 1, "gruppe": "import:1"}, {"bis_id": 1, "aenderung_ids": [1]},
    {"bis_id": 1, "gruppe": "import:1", "aenderung_ids": [1]}, {"bis_id": None}, {"bis_id": "1"}, {"bis_id": 1.5},
    {"bis_id": 1.0}, {"bis_id": True}, {"bis_id": [1]}, {"bis_id": 1, "zusatz": 1}],
    ids=lambda x: ",".join(f"{a}={b!r}" for a, b in x.items()) or "leer")
def test_validierung(api, k, koerper):
    v = Verlauf(api)
    _folge(api, k, v)

    def aufruf():
        r = api.post(RUECKGAENGIG, json=koerper, erwartet=422)
        assert fehlercode(r) == "validierung"
    ohne_wirkung(api, aufruf)


@pytest.mark.kern
def test_unbekannte_bis_id(api, k):
    v = Verlauf(api)
    _folge(api, k, v)

    def aufruf():
        r = api.post(RUECKGAENGIG, json={"bis_id": 999999}, erwartet=404)
        assert fehlercode(r) == "nicht_gefunden"
    ohne_wirkung(api, aufruf)
    pruefe_wirksamkeit(api, v.modell)


def test_bis_ohne_aenderungen_404(api):
    def aufruf():
        assert fehlercode(api.post(RUECKGAENGIG, json={"bis_id": 1}, erwartet=404)) == "nicht_gefunden"
    ohne_wirkung(api, aufruf)


def test_bisherige_formen_unveraendert(api, k):
    """aenderung_ids und gruppe wirken wie in 6.2 (E-029)."""
    v = Verlauf(api)
    a, _ = _folge(api, k, v)
    u = api.post(RUECKGAENGIG, json={"aenderung_ids": [a["a5"]]}, erwartet=200).daten
    assert u["rueckgaengig_von"] == [a["a5"]]
    assert fehlercode(api.post(RUECKGAENGIG, json={"aenderung_ids": [a["a5"]]}, erwartet=409)) == \
        "bereits_rueckgaengig"


# ------------------------------------------------------------------ zufällige Folgen (T 3.6)


@given(st.lists(st.tuples(st.integers(0, 6), st.integers(0, 10_000)), min_size=4, max_size=12),
       st.integers(0, 10_000), st.booleans())
def test_zufaellige_folgen(api_fabrik, schritte, wahl, wiederholen):
    """Beliebige Folgen aus Anlegen, Ändern, Löschen, Rückgängig und „bis“; jedes „bis“ ergibt exakt den Abzug
    vor der gewählten Änderung, die Wirksamkeit folgt dem Modell (protokoll.md 6.2a, 6.5, 8)."""
    api = api_fabrik()
    k = {"giro": api.konto("Giro", "girokonto")["id"], "leb": api.konto("Lebensmittel", "aufwand")["id"]}
    o = _ops(api, k)
    v = Verlauf(api)
    n = [0]

    def tags():
        return [t["id"] for t in api.get("/api/tags", erwartet=200).daten]

    def buchungen():
        return [b["id"] for b in api.alle_buchungen()]

    for art, z in schritte:
        n[0] += 1
        if art == 0 or (art == 1 and not tags()):
            v.eine(lambda: o["tag"](f"Tag {n[0]}"))
        elif art == 1:
            t = tags()[z % len(tags())]
            v.eine(lambda: o["umbenennen"](t, f"Name {n[0]}"))
        elif art == 2 or (art in (3, 4) and not buchungen()):
            v.eine(lambda: o["buchung"](100 + z))
        elif art == 3:
            b = buchungen()[z % len(buchungen())]
            v.eine(lambda: o["zweck"](b, f"Zweck {n[0]}"))
        elif art == 4:
            b = buchungen()[z % len(buchungen())]
            v.eine(lambda: api.delete(f"/api/buchungen/{b}", erwartet=204))
        elif art == 5 and v.vor:
            eff = [x for x, w in v.modell.wirksam().items() if w and x in v.vor]
            x = eff[z % len(eff)]

            def zurueck():
                r = api.post(f"/api/aenderungen/{x}/rueckgaengig", erwartet=(200, 409))
                if r.status_code == 409:
                    assert fehlercode(r) == "rueckgaengig_konflikt"
            v.schritt(zurueck, lambda: [x])
        elif v.vor:
            ziel = sorted(v.vor)[z % len(v.vor)]
            v.bis(ziel)
    ziel = sorted(v.vor)[wahl % len(v.vor)]
    vor_u = bestand(api)
    u = v.bis(ziel)
    if wiederholen:
        v.zurueck(u["id"])
        assert bestand(api) == vor_u
    pruefe_wirksamkeit(api, v.modell)
