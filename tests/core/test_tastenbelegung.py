"""Core-Test (D-292): systematische Tastenbelegung.

Das Verhalten im Browser prüft `tests/test_browser_tastenbelegung.py`. Hier ist ohne Browser gesichert:
die Kürzeltabelle des Kontoblatts (vollständig, ohne Satzzeichen, ohne alte Folgen), die globalen Tasten (`h`
statt `?`, kein `/`, `u`/`d` bewegen), die adaptive Tastaturhilfe und dass die Filter, die die Kürzel setzen, in der
Ausdruckssprache gültig sind und das Erwartete treffen.
"""

from __future__ import annotations

import re

# Soll der Kürzeltabelle des Kontoblatts: (Vortaste, Taste)
SOLL = {
    ("", "k"), ("", "t"), ("", "s"), ("", "b"), ("", "a"), ("", "A"), ("", "e"), ("", "x"), ("", "X"),
    ("", "g"), ("", "m"), ("", "M"), ("", "n"),
    ("f", "a"), ("f", "f"), ("f", "0"), ("f", "u"), ("f", "U"),
    ("f", "t"), ("f", "T"), ("f", "w"), ("f", "W"), ("f", "m"), ("f", "M"), ("f", "q"), ("f", "Q"),
    ("f", "y"), ("f", "Y"), ("f", "x"),
    ("f", "e"), ("f", "E"), ("f", "z"), ("f", "Z"), ("f", "b"), ("f", "B"),
    ("v", "g"), ("v", "k"), ("v", "K"), ("v", "o"), ("v", "r"), ("v", "s"), ("v", "0"), ("v", "e"),
}


def _js(client, name):
    return client.get(f"/oeffentlich/app/{name}.js").text


def _kuerzel(js):
    tabelle = js[js.index("const KUERZEL = ["):js.index("const VORTASTEN")]
    return re.findall(r'^\s*\[\s*["`](\w*)["`],\s*"([^"]+)"', tabelle, re.M)


def test_kuerzeltabelle_des_kontoblatts_ist_die_neue_belegung(client):
    eintraege = _kuerzel(_js(client, "konto"))
    assert len(eintraege) == len(set(eintraege)), "eine Tastenfolge ist doppelt belegt"
    assert set(eintraege) == SOLL
    for _vor, taste in eintraege:
        assert re.fullmatch(r"[A-Za-z0-9]", taste), f"Satzzeichen im Kürzel: {taste!r}"


def test_u_und_d_sind_im_kontoblatt_frei(client):
    """`u`/`d` bewegen die Markierung (global); das Kontoblatt darf sie ohne Vortaste nicht belegen."""
    eintraege = set(_kuerzel(_js(client, "konto")))
    for taste in ("u", "d", "U", "D", "h", "w"):
        assert ("", taste) not in eintraege


def test_globale_tasten(client):
    js = _js(client, "haupt")
    assert not re.search(r'e\.key === "\?"', js), "? öffnet die Hilfe nicht mehr (h)"
    assert not re.search(r'e\.key === "/"', js), "/ ist entfallen (w s)"
    assert re.search(r'HILFE_TASTE\s*=\s*"h"', js), "h öffnet die Tastaturhilfe"
    bewegung = js[js.index("const BEWEGUNG"):]
    bewegung = bewegung[:bewegung.index("};")]
    for taste, ziel in (("u", "ArrowUp"), ("d", "ArrowDown"), ("U", "ArrowUp"), ("D", "ArrowDown")):
        assert re.search(rf'\b{taste}:\s*\[\s*"{ziel}"', bewegung), f"{taste} bewegt nicht wie {ziel}"


def test_tastaturhilfe_ist_adaptiv(client):
    js = _js(client, "haupt")
    hilfe = js[js.index("function tastaturHilfe("):]
    hilfe = hilfe[:hilfe.index("\n}\n")]
    for kennung in ("tastatur-hilfe-ueberall", "tastatur-hilfe-bereiche", "tastatur-hilfe-liste", "tastatur-hilfe-alle"):
        assert kennung in hilfe, f"{kennung} fehlt in der Tastaturhilfe"
    assert "data-blatt" in hilfe or "blatt:" in hilfe, "die Hilfe nennt das Blatt nicht"
    konto = _js(client, "konto")
    assert "export function kontoKuerzel(seite)" in konto, "die Kürzel kennen den Zustand des Blatts nicht"


def test_kontextmenue_filter_hat_den_betrag(client):
    js = _js(client, "konto")
    teil = js[js.index("  filterEintrag(b) {"):]
    teil = teil[:teil.index("\n  }\n")]
    for kennung in ("km-filter-empfaenger", "km-filter-empfaenger-aehnlich", "km-filter-zweck", "km-filter-zweck-aehnlich",
                    "km-filter-betrag", "km-filter-betrag-absolut"):
        assert f'"{kennung}"' in teil, f"{kennung} fehlt im Kontextmenü „Filter“"


def _pruefen(client, ausdruck):
    r = client.post("/api/ausdruck/pruefen", json={"ausdruck": ausdruck, "kontext": "filter", "stichtag": "2026-11-26"})
    assert r.status_code == 200, r.text
    return r.json()


def test_zeitraeume_der_kuerzel_sind_gueltige_ausdruecke(client):
    for teil in ("datum == heute", "datum == gestern", "datum in diese_woche", "datum in letzte_woche",
                 "datum in dieser_monat", "datum in letzter_monat", "datum in dieses_quartal",
                 "datum in letztes_quartal", "datum in dieses_jahr", "datum in letztes_jahr"):
        assert _pruefen(client, teil)["gueltig"] is True, teil


def test_filter_gleicher_betrag_trifft_mit_und_ohne_vorzeichen(client):
    def konto(name, art):
        r = client.post("/api/konten", json={"name": name, "art": art})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    giro, auf, ert = konto("Giro T", "girokonto"), konto("Einkauf T", "aufwand"), konto("Erstattung T", "ertrag")

    def buchung(tag, betrag, gegen):
        r = client.post("/api/buchungen", json={"datum": f"2024-05-{tag:02d}", "verwendungszweck": f"B{tag}", "splits": [
            {"konto_id": giro, "betrag": betrag}, {"konto_id": gegen, "betrag": -betrag}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    aus = buchung(1, -2340, auf)
    ein = buchung(2, 2340, ert)
    buchung(3, -2341, auf)

    def treffer(ausdruck):
        r = client.get("/api/buchungen", params={"konto_id": giro, "filter": ausdruck, "stichtag": "2026-11-26"})
        assert r.status_code == 200, r.text
        return {b["id"] for b in r.json()["eintraege"]}

    assert treffer('bet == 23.40 and dir == "ausgabe"') == {aus}      # f b auf der Ausgabe
    assert treffer('bet == 23.40 and dir == "einnahme"') == {ein}     # f b auf der Einnahme
    assert treffer("bet == 23.40") == {aus, ein}                       # f B
