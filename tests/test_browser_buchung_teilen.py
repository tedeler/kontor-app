"""Entwicklungstests für das Feature „buchung-teilen“ (D-304): Kontextmenü „Teilen…“ übergibt Kurztext und Link an die
Teilen-Funktion des Geräts (hier eine Attrappe), ohne sie an die Zwischenablage; der Link öffnet das Kontoblatt mit
markierter Buchung. Synthetische Daten, Server im Mock-Modus."""

from __future__ import annotations

import httpx

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401

ATTRAPPE = """
window.__geteilt = [];
window.__kopiert = [];
const ohneShare = new URLSearchParams(location.search).has("ohne_share") || sessionStorage.getItem("ohne_share");
if (ohneShare) { sessionStorage.setItem("ohne_share", "1"); try { delete Navigator.prototype.share; } catch (e) {} }
else { navigator.share = async (d) => { window.__geteilt.push(d); }; }
Object.defineProperty(navigator, "clipboard", { configurable: true,
  value: { writeText: async (t) => { window.__kopiert.push(t); } } });
"""


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        giro = c.post(url + "/api/konten", json={"name": "Giro Teilen", "art": "girokonto"}).json()["id"]
        kat = c.post(url + "/api/konten", json={"name": "Lebensmittel", "art": "aufwand"}).json()["id"]
        emp = c.post(url + "/api/empfaenger", json={"name": "Markt Beispiel (fiktiv)"}).json()["id"]
        ids = []
        for tag, zweck in (("03", "Einkauf Woche 1"), ("10", "Einkauf Woche 2")):
            r = c.post(url + "/api/buchungen", json={
                "datum": f"2026-11-{tag}", "verwendungszweck": zweck, "empfaenger_id": emp,
                "splits": [{"konto_id": giro, "betrag": -123_456}, {"konto_id": kat, "betrag": 123_456}]})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
    return giro, ids


def test_teilen_ueber_das_geraet_und_link_oeffnet_die_buchung(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.add_init_script(ATTRAPPE)
        giro, ids = _welt(url)
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        tid(page, f"buchung-{ids[1]}").click(button="right")
        tid(page, "km-teilen").click()
        page.wait_for_function("() => window.__geteilt.length === 1")
        text = page.evaluate("() => window.__geteilt[0].text")
        # Gestaltung für WhatsApp (D-306)
        assert text.split("\n") == [
            "*Markt Beispiel (fiktiv)*",
            "*\u22121.234,56\u00a0€* · Ausgabe",
            "",
            "📅 Di, 10.11.2026",
            "🏦 Giro Teilen",
            "🏷️ Lebensmittel",
            "",
            "> Einkauf Woche 2",
            "",
            f"{url}/konten/{giro}?buchung={ids[1]}",
        ]
        assert page.evaluate("() => window.__kopiert.length") == 0
        # zwei markierte: Teilen nur für genau eine Buchung
        tid(page, f"buchung-{ids[0]}").locator('[data-feld="datum"]').click()
        tid(page, f"buchung-{ids[1]}").locator('[data-feld="datum"]').click(modifiers=["Control"])
        tid(page, f"buchung-{ids[1]}").click(button="right")
        expect(tid(page, "km-teilen")).to_have_attribute("aria-disabled", "true")
        page.keyboard.press("Escape")
        # der Link öffnet das Kontoblatt mit der Buchung markiert
        page.goto(text.splitlines()[-1])
        bereit(page, "konto")
        expect(tid(page, f"buchung-{ids[1]}")).to_have_attribute("aria-selected", "true")
        expect(tid(page, f"buchung-{ids[0]}")).not_to_have_attribute("aria-selected", "true")


def test_ohne_teilen_funktion_in_die_zwischenablage(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.add_init_script(ATTRAPPE)
        giro, ids = _welt(url)
        page.goto(f"{url}/konten/{giro}?ohne_share=1")
        bereit(page, "konto")
        tid(page, f"buchung-{ids[0]}").click(button="right")
        tid(page, "km-teilen").click()
        page.wait_for_function("() => window.__kopiert.length === 1")
        assert page.evaluate("() => window.__kopiert[0]").endswith(f"/konten/{giro}?buchung={ids[0]}")
        assert page.evaluate("() => window.__geteilt.length") == 0
        expect(page.get_by_text("Kurztext und Link in die Zwischenablage kopiert.")).to_be_visible()


def test_aus_der_kategorie_aus_sicht_des_bankkontos(tmp_path, browser):  # noqa: F811
    """In der Kategorieansicht nennt der Text das Bestandskonto und den Betrag, wie das Konto ihn zeigt (D-306)."""
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.add_init_script(ATTRAPPE)
        giro, ids = _welt(url)
        with httpx.Client(trust_env=False) as c:
            kat = next(k["id"] for k in c.get(url + "/api/konten").json() if k["name"] == "Lebensmittel")
        page.goto(f"{url}/konten/{kat}")
        bereit(page, "konto")
        tid(page, f"buchung-{ids[0]}").click(button="right")
        tid(page, "km-teilen").click()
        page.wait_for_function("() => window.__geteilt.length === 1")
        zeilen = page.evaluate("() => window.__geteilt[0].text").split("\n")
        assert zeilen[1] == "*−1.234,56 €* · Ausgabe"
        assert "🏦 Giro Teilen" in zeilen and "🏷️ Lebensmittel" in zeilen
        assert zeilen[-1] == f"{url}/konten/{kat}?buchung={ids[0]}"
