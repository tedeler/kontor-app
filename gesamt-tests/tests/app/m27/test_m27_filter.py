"""M27: Neue Filter der Buchungsliste (sammel.md 3; E-249, E-250) – REST, kern.

Erwartete Listen unabhängig über ``tests/hilfen/m27.filter_soll``.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.hilfen.api import fehlercode, neue_api
from tests.hilfen.m27 import empfaenger_aehnlich, filter_soll, texte_aehnlich, woerter, zweck_aehnlich

pytestmark = pytest.mark.kern

ZWECKE = ["Miete März", "Kaltmiete April", "Mietezahlung", "MIETE MÄRZ", "", "  ", "Rechnung 4711", "4711",
          "ab", "Strom Abschlag", "Abschlag Gas", "Café Ölmühle", "cafe oelmuehle", "123"]
NAMEN = [("Stadtwerke Musterstadt (fiktiv)", ["SWM Energie"]), ("Stadtwerk Nord (fiktiv)", []),
         ("Abc", []), ("Ab-C Handel", []), ("Bäckerei Krume (fiktiv)", ["Baeckerei K."]),
         ("Supermarkt Frischekorb (fiktiv)", [])]


def test_hilfsregeln_der_definition():
    assert woerter("Miete März 2024, ab 4711!") == ["miete", "maerz"]
    assert zweck_aehnlich("Kaltmiete", "Miete") and zweck_aehnlich("Mietezahlung", "miete")
    assert zweck_aehnlich("123", "123") and not zweck_aehnlich("1234", "123")
    assert texte_aehnlich("Stadtwerke Nord", "Stadtwerk") and not texte_aehnlich("Abc", "Abc")
    assert empfaenger_aehnlich({"name": "X", "aliase": ["SWM Energie"]}, "swm-e")


@pytest.fixture(scope="module")
def daten(tmp_path_factory):
    api = neue_api(tmp_path_factory.mktemp("m27f"))
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    emp = []
    for name, aliase in NAMEN:
        e = api.empfaenger(name)["id"]
        if aliase:
            api.patch(f"/api/empfaenger/{e}", json={"aliase": aliase}, erwartet=200)
        emp.append(e)
    n = 0
    for i, z in enumerate(ZWECKE):
        for e in (emp[i % len(emp)], None):
            n += 1
            felder = {"verwendungszweck": z}
            if e:
                felder["empfaenger_id"] = e
            api.buchung(f"2024-{n % 12 + 1:02d}-{n % 27 + 1:02d}", [(g, -100 - n), (leb, 100 + n)], **felder)
    alle = api.alle_buchungen()
    empfaenger = {x["id"]: x for x in api.get("/api/empfaenger", erwartet=200).daten}
    return api, alle, empfaenger, g


def _ist(api, **params):
    return [b["id"] for b in api.alle_buchungen(**params)]


@pytest.mark.parametrize("f", [
    {"zweck_gleich": "miete märz"}, {"zweck_gleich": "Miete"}, {"zweck_gleich": "  "},
    {"zweck_leer": True}, {"zweck_leer": True, "zweck_gleich": "Miete März"},
    {"zweck_aehnlich": "Miete"}, {"zweck_aehnlich": "die miete, bitte"}, {"zweck_aehnlich": "4711"},
    {"zweck_aehnlich": "ab"}, {"zweck_aehnlich": "Ölmühle"}, {"zweck_aehnlich": "123"},
    {"empfaenger_aehnlich": "Stadtwerke"}, {"empfaenger_aehnlich": "Stadtw"}, {"empfaenger_aehnlich": "Abc"},
    {"empfaenger_aehnlich": "SWM Energie AG"}, {"empfaenger_aehnlich": "Baeckerei"},
    {"empfaenger_aehnlich": "Nichts Ähnliches"},
    {"empfaenger_aehnlich": "Stadtwerke", "zweck_aehnlich": "Abschlag"},
])
def test_filter_gegen_regel(daten, f):
    api, alle, empfaenger, g = daten
    soll = filter_soll(alle, empfaenger, **f)
    assert _ist(api, **f) == soll
    # UND mit bestehenden Filtern
    assert _ist(api, konto_id=g, sortierung="-datum", **f) == [
        b["id"] for b in api.alle_buchungen(konto_id=g, sortierung="-datum") if b["id"] in set(soll)]


def test_ohne_empfaenger_nie_getroffen_und_leere_liste(daten):
    api, alle, empfaenger, g = daten
    treffer = _ist(api, empfaenger_aehnlich="Supermarkt")
    assert treffer and all(next(b for b in alle if b["id"] == i)["empfaenger"] for i in treffer)
    assert _ist(api, empfaenger_aehnlich="Zzzz Unbekannt") == []


@pytest.mark.parametrize("name", ["zweck_gleich", "zweck_aehnlich", "empfaenger_aehnlich"])
def test_leerer_text_422(daten, name):
    api = daten[0]
    r = api.get("/api/buchungen", params={name: ""})
    assert r.status_code == 422 and fehlercode(r) == "validierung"


@given(wert=st.text(alphabet="aäbcdeimnrstuwz 0123456789-", min_size=1, max_size=12))
def test_zufall_zweck_aehnlich(daten, wert):
    api, alle, empfaenger, g = daten
    assert _ist(api, zweck_aehnlich=wert) == filter_soll(alle, empfaenger, zweck_aehnlich=wert)


@given(wert=st.sampled_from(["Stadt", "Stadtwerke Süd", "SWM", "swme", "Bäck", "Baec", "Supermarkt", "Ab-C",
                             "abch", "Frischekorb"]))
def test_zufall_empfaenger_aehnlich(daten, wert):
    api, alle, empfaenger, g = daten
    assert _ist(api, empfaenger_aehnlich=wert) == filter_soll(alle, empfaenger, empfaenger_aehnlich=wert)
