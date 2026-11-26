"""Entwicklungstest für das Feature „regelgruppen“ (D-295): Regelliste mit den Abschnitten „Eigene Regeln“ und
„Automatisch angelegt“, Sortierung, Suche und „Als eigene übernehmen“.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _get


def _post(adresse, koerper):
    with httpx.Client(trust_env=False) as c:
        r = c.post(adresse, json=koerper)
        assert r.status_code in (200, 201), r.text
        return r.json()


def _aufbauen(url):
    giro = _post(url + "/api/konten", {"name": "Giro RG", "art": "girokonto"})["id"]
    kat = {n: _post(url + "/api/konten", {"name": n, "art": "aufwand"})["id"] for n in ("Obst RG", "Zahnpflege RG")}
    for empf, k in (("Zeta Markt", "Obst RG"), ("Alpha Drogerie", "Zahnpflege RG")):
        eid = _post(url + "/api/empfaenger", {"name": empf})["id"]
        for i in range(5):
            _post(url + "/api/buchungen", {"datum": f"2024-06-{10 + i:02d}", "empfaenger_id": eid,
                                           "verwendungszweck": "Kartenzahlung",
                                           "splits": [{"konto_id": giro, "betrag": -500}, {"konto_id": kat[k], "betrag": 500}]})
    eigen = _post(url + "/api/regeln", {"name": "Eigene RG", "kategorie_id": kat["Obst RG"], "bedingungen": [
        {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Wochenmarkt"}]})["id"]
    auto = {r["name"]: r["id"] for r in _get(url + "/api/regeln") if r.get("automatisch")}
    assert set(auto) == {"Zeta Markt", "Alpha Drogerie"}, auto
    return eigen, auto


def test_zwei_abschnitte_und_uebernehmen(tmp_path, browser):  # noqa: F811
    with server(tmp_path, regeln_automatisch=True) as (url, _), seite(browser, url, **DESKTOP) as page:
        eigen, auto = _aufbauen(url)
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        expect(tid(page, "regeln-eigene")).to_contain_text("Eigene Regeln (1)")
        expect(tid(page, f"regel-griff-{eigen}")).to_be_visible()
        abschnitt = tid(page, "regeln-automatisch")
        expect(abschnitt).to_contain_text("Automatisch angelegt (2)")
        # eingeklappt; automatische Regeln haben keinen Griff
        expect(tid(page, f"regel-{auto['Zeta Markt']}")).to_be_hidden()
        expect(page.locator('[data-testid^="regel-griff-"]')).to_have_count(1)
        tid(page, "regeln-automatisch-kopf").click()
        expect(tid(page, f"regel-{auto['Zeta Markt']}")).to_be_visible()
        namen = tid(page, "regel-liste-automatisch").locator("li strong")
        expect(namen).to_have_text(["Alpha Drogerie", "Zeta Markt"])
        tid(page, "regeln-automatisch-sortierung").select_option("kategorie")
        expect(namen).to_have_text(["Zeta Markt", "Alpha Drogerie"])
        tid(page, "regeln-automatisch-suche").fill("alpha")
        expect(namen).to_have_text(["Alpha Drogerie"])
        expect(tid(page, "regeln-automatisch-anzahl")).to_have_text("1 von 2")
        # Übernehmen: wandert zu den eigenen Regeln ans Ende
        tid(page, f"regel-als-eigene-{auto['Alpha Drogerie']}").click()
        expect(tid(page, "regeln-eigene")).to_contain_text("Eigene Regeln (2)")
        expect(tid(page, f"regel-griff-{auto['Alpha Drogerie']}")).to_be_visible()
        expect(tid(page, "regeln-automatisch")).to_contain_text("Automatisch angelegt (1)")
        reihen = [r["id"] for r in _get(url + "/api/regeln")]
        assert reihen == [eigen, auto["Alpha Drogerie"], auto["Zeta Markt"]]
        # Zustand des Abschnitts bleibt nach dem Neuladen (aufgeklappt, Sortierung)
        page.reload()
        bereit(page, "regeln")
        expect(tid(page, f"regel-{auto['Zeta Markt']}")).to_be_visible()
        expect(tid(page, "regeln-automatisch-sortierung")).to_have_value("kategorie")
