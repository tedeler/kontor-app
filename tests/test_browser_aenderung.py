"""Eigener Browsertest zum Fenster „Einzelheiten“ des Änderungsprotokolls (D-237). Nur synthetische Daten."""
from __future__ import annotations

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def _client(url):
    import httpx
    return httpx.Client(base_url=url, trust_env=False, timeout=60)


def _vorbereiten(c):
    b = c.get("/api/buchungen", params={"pro_seite": 1}).json()["eintraege"][0]
    tag = c.post("/api/tags", json={"name": "Urlaub"}).json()
    e = c.post("/api/empfaenger", json={"name": "Buchhandlung Seitenweise"}).json()
    assert c.patch(f"/api/buchungen/{b['id']}", json={"verwendungszweck": "Reiseführer", "tag_ids": [tag["id"]],
                                                    "empfaenger_id": e["id"]}).status_code == 200
    aenderung = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert aenderung["aktion"] == "buchung_aendern"
    return b, tag, e, aenderung


@pytest.mark.parametrize("geraet", [DESKTOP, HANDY], ids=["desktop", "handy"])
def test_einzelheiten_zeigen_vorher_und_nachher(tmp_path, browser, geraet):
    with server(tmp_path) as (url, _), seite(browser, url, **geraet) as page:
        c = _client(url)
        b, tag, e, aenderung = _vorbereiten(c)
        page.goto(url + "/protokoll")
        bereit(page, "protokoll")
        tid(page, f"aenderung-einzelheiten-{aenderung['id']}").click()
        d = tid(page, "aenderung-dialog")
        expect(d).to_be_visible()
        expect(tid(page, "ae-umfang")).to_have_text("1 Buchung geändert")
        expect(tid(page, "ae-stand")).to_have_text("wirksam")
        eintrag = tid(page, f"ae-eintrag-buchung-{b['id']}")
        expect(eintrag).to_have_attribute("data-art", "geaendert")
        # nur die geänderten Angaben, mit Namen statt Kennungen
        expect(eintrag.locator("tbody tr")).to_have_count(3)
        zweck = eintrag.locator("tr[data-feld=verwendungszweck]")
        expect(zweck.locator(".ae-vorher")).to_have_text(b["verwendungszweck"])
        expect(zweck.locator(".ae-nachher")).to_have_text("Reiseführer")
        expect(eintrag.locator("tr[data-feld=tag_ids] .ae-vorher")).to_have_text("–")
        expect(eintrag.locator("tr[data-feld=tag_ids] .ae-nachher")).to_have_text("Urlaub")
        expect(eintrag.locator("tr[data-feld=empfaenger_id] .ae-nachher")).to_have_text("Buchhandlung Seitenweise")
        expect(eintrag.locator("tr[data-feld=splits]")).to_have_count(0)
        tid(page, "ae-schliessen").click()
        expect(d).to_have_count(0)


def test_einzelheiten_einer_angelegten_und_einer_grossen_aenderung(tmp_path, browser):
    """Angelegte Objekte zeigen ihre Angaben; große Änderungen (Import) werden in Teilen gezeigt und sind durchsuchbar."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        _b, tag, _e, _a = _vorbereiten(c)
        konten = c.get("/api/konten").json()
        giro = next(k["id"] for k in konten if k["name"] == "Giro")
        gegen = next(k["id"] for k in konten if k["id"] != giro and k["art"] in ("ausgabe", "aufwand"))
        ids = []
        for i in range(60):
            r = c.post("/api/buchungen", json={"datum": "2024-03-03", "verwendungszweck": f"Probe {i}", "splits": [
                {"konto_id": giro, "betrag": -100 - i}, {"konto_id": gegen, "betrag": 100 + i}]})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
        assert c.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": ids, "hinzufuegen": [tag["id"]], "entfernen": []}).status_code == 200
        alle = c.get("/api/aenderungen", params={"pro_seite": 100}).json()["eintraege"]
        anlegen = next(a for a in alle if a["aktion"] == "tag_anlegen")
        gross = alle[0]
        assert len(gross["eintraege"]) == 60
        page.goto(url + "/protokoll")
        bereit(page, "protokoll")
        tid(page, "protokoll-mehr").click()          # die Liste zeigt 50 Änderungen je Seite
        tid(page, f"aenderung-einzelheiten-{anlegen['id']}").click()
        eintrag = tid(page, f"ae-eintrag-tag-{tag['id']}")
        expect(eintrag).to_have_attribute("data-art", "angelegt")
        expect(eintrag.locator("tr[data-feld=name] td")).to_have_text("Urlaub")
        tid(page, "ae-schliessen").click()
        tid(page, f"aenderung-einzelheiten-{gross['id']}").click()
        expect(page.locator("[data-testid=ae-liste] > section")).to_have_count(50)
        expect(tid(page, "ae-anzahl")).to_contain_text(f"50 von {len(gross['eintraege'])}")
        tid(page, "ae-mehr").click()
        expect(page.locator("[data-testid=ae-liste] > section")).to_have_count(60)
        tid(page, "ae-suche").fill("Probe 59")
        expect(tid(page, "ae-anzahl")).to_have_text("1 von 60 Objekten passen")
        expect(page.locator("[data-testid=ae-liste] > section")).to_have_count(1)
