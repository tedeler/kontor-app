"""Entwicklungstests für D-289: Vorschlag annehmen und ablehnen wirken im Kontoblatt sofort, auch wenn der Server
langsam antwortet. Playwright mit Chrome headless gegen einen echten Server im Mock-Modus; die Antworten der
REST-Schnittstelle werden im Browser verzögert.
"""

from __future__ import annotations

import time

import httpx
import pytest

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _daten, _get

VERZOEGERUNG = 0.6     # Sekunden je REST-Anfrage
SOFORT = 400           # Millisekunden: deutlich weniger als eine einzige Anfrage


@pytest.fixture
def blatt(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        konten = {k["name"]: k["id"] for k in _get(url + "/api/konten")}
        with httpx.Client(trust_env=False, base_url=url) as c:
            regel = c.post("/api/regeln", json={"name": "Einkauf als Drogerie", "kategorie_id": konten["Drogerie"],
                                                "bedingungen": [{"feld": "verwendungszweck", "operator": "enthaelt",
                                                                 "wert": "Einkauf 1"}]})
            assert regel.status_code == 201, regel.text
            r = c.post("/api/regeln/anwenden", json={"regel_ids": [regel.json()["id"]], "nur_unkategorisiert": False})
            assert r.status_code == 200, r.text
        mit = [b for b in _get(url + "/api/buchungen", konto_id=konten["Giro"], pro_seite=200)["eintraege"] if b["vorschlag"]]
        assert len(mit) >= 5
        page.goto(f"{url}/konten/{konten['Giro']}")
        bereit(page, "konto")

        def langsam(route):
            time.sleep(VERZOEGERUNG)
            route.continue_()

        page.route("**/api/**", langsam)
        yield url, page, konten, mit


def _lesen(url, bid):
    return _get(f"{url}/api/buchungen/{bid}")


def test_annehmen_und_ablehnen_wirken_sofort(blatt):
    url, page, konten, mit = blatt
    a, b = mit[0], mit[1]
    za, zb = tid(page, f"buchung-{a['id']}"), tid(page, f"buchung-{b['id']}")
    expect(za).to_have_attribute("data-vorschlag", "ja")
    tid(page, f"vorschlag-annehmen-{a['id']}").click()
    expect(za).to_have_attribute("data-vorschlag", "nein", timeout=SOFORT)
    expect(za).to_have_attribute("data-status", "bestaetigt", timeout=SOFORT)
    expect(za.locator('[data-feld="kategorie"]')).to_have_attribute("data-kategorie-id", str(konten["Drogerie"]))
    assert _lesen(url, a["id"])["vorschlag"] is not None, "der Server war schneller als gedacht: Test prüft nichts"
    tid(page, f"vorschlag-ablehnen-{b['id']}").click()
    expect(zb).to_have_attribute("data-vorschlag", "nein", timeout=SOFORT)
    expect(zb.locator('[data-feld="kategorie"]')).to_have_attribute(
        "data-kategorie-id", str(b["vorschlag"]["vorher_konto_id"]), timeout=SOFORT)
    # der Server zieht nach; danach zeigt das Blatt weiter dasselbe
    for _ in range(100):
        if _lesen(url, a["id"])["vorschlag"] is None and _lesen(url, b["id"])["vorschlag"] is None:
            break
        page.wait_for_timeout(200)   # nicht time.sleep: nur so bedient Playwright die verzögerten Anfragen
    sa, sb = _lesen(url, a["id"]), _lesen(url, b["id"])
    assert (sa["vorschlag"], sa["kategorie_id"], sa["status"]) == (None, konten["Drogerie"], "bestaetigt")
    assert (sb["vorschlag"], sb["kategorie_id"]) == (None, b["vorschlag"]["vorher_konto_id"])
    expect(tid(page, "rueckgaengig-knopf")).to_be_enabled(timeout=20_000)
    expect(za).to_have_attribute("data-vorschlag", "nein")
    expect(zb).to_have_attribute("data-vorschlag", "nein")
    expect(tid(page, f"buchung-{mit[2]['id']}")).to_have_attribute("data-vorschlag", "ja")


def test_schnell_hintereinander_ohne_zurueckspringen(blatt):
    """Vier Entscheidungen in Folge: Keine Zeile zeigt zwischendurch wieder ihren Vorschlag, und Rückgängig nimmt
    sie einzeln zurück."""
    url, page, konten, mit = blatt
    ids = [b["id"] for b in mit[:4]]
    for i in ids:
        tid(page, f"vorschlag-annehmen-{i}").click()
    for i in ids:
        expect(tid(page, f"buchung-{i}")).to_have_attribute("data-vorschlag", "nein", timeout=SOFORT)
    ende = time.time() + 30
    while time.time() < ende and any(_lesen(url, i)["vorschlag"] for i in ids):
        for i in ids:   # währenddessen springt nichts zurück
            assert tid(page, f"buchung-{i}").get_attribute("data-vorschlag") == "nein"
        time.sleep(0.1)
    assert not any(_lesen(url, i)["vorschlag"] for i in ids)
    page.unroute("**/api/**")
    for i in ids:
        expect(tid(page, f"buchung-{i}")).to_have_attribute("data-vorschlag", "nein")
    # vier Schritte auf dem Rückgängig-Stapel: der letzte zuerst
    expect(tid(page, "rueckgaengig-knopf")).to_be_enabled()
    page.wait_for_timeout(1500)
    tid(page, "rueckgaengig-knopf").click()
    expect(tid(page, f"buchung-{ids[3]}")).to_have_attribute("data-vorschlag", "ja")
    expect(tid(page, f"buchung-{ids[2]}")).to_have_attribute("data-vorschlag", "nein")


def test_fehler_des_servers_stellt_die_zeile_wieder_her(blatt):
    url, page, konten, mit = blatt
    a = mit[0]
    page.unroute("**/api/**")
    page.route("**/api/buchungen/*/vorschlag", lambda route: route.fulfill(
        status=409, content_type="application/json",
        body='{"fehler":{"code":"buchung_gesperrt","meldung":"Die Buchung ist gesperrt.","details":null}}'))
    za = tid(page, f"buchung-{a['id']}")
    tid(page, f"vorschlag-annehmen-{a['id']}").click()
    expect(tid(page, "meldungen")).to_contain_text("gesperrt")
    expect(za).to_have_attribute("data-vorschlag", "ja")
