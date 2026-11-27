"""Entwicklungstest für das Feature „regelpruefung“ (D-307): Hinweise an automatisch angelegten Regeln, Bereich
„Deaktiviert“ ganz unten und die Meldung beim Deaktivieren.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _get


def _senden(methode, adresse, koerper):
    with httpx.Client(trust_env=False) as c:
        r = c.request(methode, adresse, json=koerper)
        assert r.status_code in (200, 201), r.text
        return r.json()


def _aufbauen(url):
    giro = _senden("POST", url + "/api/konten", {"name": "Giro RP", "art": "girokonto"})["id"]
    kat = {n: _senden("POST", url + "/api/konten", {"name": n, "art": "aufwand"})["id"] for n in ("Obst RP", "Zahnpflege RP")}
    buchungen = {}
    for empf, k in (("Zeta Markt", "Obst RP"), ("Alpha Drogerie", "Zahnpflege RP")):
        eid = _senden("POST", url + "/api/empfaenger", {"name": empf})["id"]
        buchungen[empf] = [_senden("POST", url + "/api/buchungen", {
            "datum": f"2024-06-{10 + i:02d}", "empfaenger_id": eid, "verwendungszweck": "Kartenzahlung",
            "splits": [{"konto_id": giro, "betrag": -500}, {"konto_id": kat[k], "betrag": 500}]})["id"] for i in range(5)]
    auto = {r["name"]: r["id"] for r in _get(url + "/api/regeln") if r.get("automatisch")}
    assert set(auto) == {"Zeta Markt", "Alpha Drogerie"}, auto
    # eine Buchung von Zeta Markt umhängen: nur noch 4 von 5 in „Obst RP“
    _senden("PUT", url + f"/api/buchungen/{buchungen['Zeta Markt'][0]}/kategorie", {"kategorie_id": kat["Zahnpflege RP"]})
    eigen = _senden("POST", url + "/api/regeln", {"name": "Eigene RP", "kategorie_id": kat["Obst RP"], "aktiv": False,
                                                   "bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt",
                                                                    "wert": "Wochenmarkt"}]})["id"]
    return auto, eigen


def test_hinweise_zuerst_und_bereich_deaktiviert(tmp_path, browser):  # noqa: F811
    with server(tmp_path, regeln_automatisch=True) as (url, _), seite(browser, url, **DESKTOP) as page:
        auto, eigen = _aufbauen(url)
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        expect(tid(page, "regeln-eigene")).to_contain_text("Eigene Regeln (0)")
        expect(tid(page, "regeln-automatisch")).to_contain_text("Automatisch angelegt (2, 1 mit Hinweis)")
        tid(page, "regeln-automatisch-kopf").click()
        # Regel mit Hinweis zuerst, obwohl nach Name sortiert
        expect(tid(page, "regel-liste-automatisch").locator("li strong")).to_have_text(["Zeta Markt", "Alpha Drogerie"])
        zeta = tid(page, f"regel-{auto['Zeta Markt']}")
        expect(zeta).to_have_attribute("data-inkonsistent", "anzahl")
        expect(tid(page, f"regel-hinweis-{auto['Zeta Markt']}")).to_contain_text("4 von 5")
        expect(tid(page, f"regel-hinweis-{auto['Alpha Drogerie']}")).to_have_count(0)
        # deaktivierte eigene Regel: eigener Bereich ganz unten, eingeklappt, ohne Griff
        deakt = tid(page, "regeln-deaktiviert")
        expect(deakt).to_contain_text("Deaktiviert (1)")
        expect(tid(page, f"regel-{eigen}")).to_be_hidden()
        expect(tid(page, f"regel-griff-{eigen}")).to_have_count(0)
        assert page.evaluate("() => { const s = [...document.querySelectorAll('.regel-abschnitt')];"
                             " return s[s.length - 1].dataset.testid; }") == "regeln-deaktiviert"
        # automatische Regel deaktivieren: Meldung nennt die Wirkung, Regel wandert in den Bereich
        tid(page, f"regel-aktiv-{auto['Alpha Drogerie']}").uncheck()
        expect(page.get_by_text("legt Kontor für diesen Empfänger keine neue an")).to_be_visible()
        expect(tid(page, "regeln-deaktiviert")).to_contain_text("Deaktiviert (2)")
        tid(page, "regeln-deaktiviert-kopf").click()
        expect(tid(page, "regel-liste-deaktiviert").locator(f'[data-testid="regel-{auto["Alpha Drogerie"]}"]')).to_be_visible()
        expect(tid(page, f"regel-automatisch-{auto['Alpha Drogerie']}")).to_be_visible()
        expect(tid(page, "regeln-automatisch")).to_contain_text("Automatisch angelegt (1, 1 mit Hinweis)")
