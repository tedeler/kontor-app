"""Entwicklungstests für das Feature „kategorien-ordnen“ (D-326): Kategorien auf der Kategorienseite mit Suche,
Ziehen und Ablegen sowie Mehrfachauswahl neu ordnen. Playwright mit Chrome headless gegen einen echten Server im
Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import httpx

from .test_browser import (  # noqa: F401
    DESKTOP,
    bereit,
    browser,
    expect,
    seite,
    server,
    tid,
)


def _api(url, methode, pfad, **kw):
    with httpx.Client(trust_env=False) as c:
        return c.request(methode, url + pfad, **kw).json()


def _anlegen(url):
    k = {}
    for name, eltern in (("Wohnen", None), ("Freizeit", None), ("Kino", None), ("Miete", "Wohnen"),
                         ("Strom", "Wohnen"), ("Ökostrom", "Strom"), ("Essen", None), ("Supermarkt", "Essen")):
        r = _api(url, "POST", "/api/konten", json={"name": name, "art": "aufwand", "eltern_id": k[eltern] if eltern else None})
        assert "id" in r, r
        k[name] = r["id"]
    return k


def _eltern(url, kid):
    return _api(url, "GET", f"/api/konten/{kid}")["eltern_id"]


def _warte_eltern(page, url, kid, soll):
    """Wartet auf den Server und auf den neu gezeichneten Baum, bevor der Test weiter zieht."""
    for _ in range(60):
        if _eltern(url, kid) == soll:
            break
        page.wait_for_timeout(100)
    assert _eltern(url, kid) == soll
    im_baum = (f'[data-testid="kategorie-{kid}"][aria-level="1"]' if soll is None
               else f'[data-testid="kategorie-{soll}"] > [role="group"] > [data-testid="kategorie-{kid}"]')
    expect(page.locator(f'[data-testid="kategorienbaum"] {im_baum}')).to_have_count(1)
    expect(tid(page, "seite-kategorien")).to_have_attribute("data-geladen", "ja")


def _start(page, url):
    page.goto(f"{url}/kategorien")
    bereit(page, "kategorien")
    expect(page.locator('[data-testid="kategorienbaum"]').first).to_be_visible()


def _zeile(page, kid):
    return page.locator(f'[data-testid="kategorie-{kid}"] > .baum-zeile')


def _ziehen(page, quelle, ziel, anteil=0.5, warten=0, loslassen=True):
    a = quelle.bounding_box()
    b = ziel.bounding_box()
    page.mouse.move(a["x"] + 30, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(a["x"] + 40, a["y"] + a["height"] / 2 + 6, steps=3)
    page.mouse.move(b["x"] + 40, b["y"] + b["height"] * anteil, steps=8)
    if warten:
        page.wait_for_timeout(warten)
        b = ziel.bounding_box()
        page.mouse.move(b["x"] + 42, b["y"] + b["height"] * anteil, steps=2)
    if loslassen:
        page.mouse.up()


def test_suche_in_der_auswahl_und_zuletzt_gewaehlt(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        k = _anlegen(url)
        _start(page, url)
        _zeile(page, k["Kino"]).click()
        page.keyboard.press("v")
        suche = tid(page, "ziel-suche")
        expect(suche).to_be_focused()
        # nicht wählbar: sich selbst; Pfadsuche über mehrere Wörter, Umlaute gefaltet
        expect(tid(page, f"ziel-option-{k['Kino']}")).to_have_count(0)
        page.keyboard.type("woh oeko")
        optionen = page.locator('[data-testid="ziel-liste"] [role="option"]')
        expect(optionen).to_have_count(1)
        expect(optionen.first).to_contain_text("Ökostrom")
        expect(optionen.first.locator("mark")).to_have_count(2)
        page.keyboard.press("Escape")             # leert nur die Suche
        expect(suche).to_have_value("")
        expect(tid(page, "ziel-auswahl")).to_be_visible()
        page.keyboard.type("frei")
        page.keyboard.press("Enter")
        _warte_eltern(page, url, k["Kino"], k["Freizeit"])
        # zuletzt gewählt steht beim nächsten Mal oben; das verschobene Element bleibt fokussiert
        expect(page.locator(f'[data-testid="kategorie-{k["Kino"]}"]')).to_be_focused()
        expect(tid(page, "kategorien-status")).to_contain_text("Freizeit")
        _zeile(page, k["Miete"]).click()
        page.keyboard.press("v")
        expect(tid(page, "ziel-zuletzt")).to_be_visible()
        expect(tid(page, f"ziel-zuletzt-{k['Freizeit']}")).to_have_attribute("aria-selected", "true")
        page.keyboard.press("Enter")
        _warte_eltern(page, url, k["Miete"], k["Freizeit"])


def test_ablegen_zwischen_zeilen_macht_zur_oberkategorie(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        k = _anlegen(url)
        _start(page, url)
        # Ökostrom (Wohnen › Strom) in das obere Viertel von „Kino“ (oberste Ebene) → oberste Ebene
        _ziehen(page, _zeile(page, k["Ökostrom"]), _zeile(page, k["Kino"]), anteil=0.1, loslassen=False)
        expect(page.locator(f'[data-testid="kategorie-{k["Kino"]}"]')).to_have_attribute("data-ablage-ort", "davor")
        page.mouse.up()
        _warte_eltern(page, url, k["Ökostrom"], None)
        # Supermarkt in das untere Viertel von „Miete“ (unter Wohnen) → Unterkategorie von Wohnen
        _ziehen(page, _zeile(page, k["Supermarkt"]), _zeile(page, k["Miete"]), anteil=0.9)
        _warte_eltern(page, url, k["Supermarkt"], k["Wohnen"])
        # auf die Mitte → Unterkategorie
        _ziehen(page, _zeile(page, k["Kino"]), _zeile(page, k["Freizeit"]))
        _warte_eltern(page, url, k["Kino"], k["Freizeit"])


def test_verweilen_klappt_auf_und_esc_bricht_ab(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        k = _anlegen(url)
        _start(page, url)
        tid(page, "kategorien-zuklappen").click()
        wohnen = page.locator(f'[data-testid="kategorie-{k["Wohnen"]}"]')
        expect(wohnen).to_have_attribute("aria-expanded", "false")
        _ziehen(page, _zeile(page, k["Kino"]), _zeile(page, k["Wohnen"]), warten=1000, loslassen=False)
        expect(page.locator(f'[data-testid="kategorie-{k["Wohnen"]}"]')).to_have_attribute("aria-expanded", "true")
        # Esc bricht ab: nichts geändert, keine Markierung bleibt stehen
        page.keyboard.press("Escape")
        page.mouse.up()
        expect(page.locator("[data-ablage]")).to_have_count(0)
        page.wait_for_timeout(300)
        assert _eltern(url, k["Kino"]) is None
        # jetzt in die aufgeklappte Unterkategorie Strom ablegen
        _ziehen(page, _zeile(page, k["Kino"]), _zeile(page, k["Strom"]))
        _warte_eltern(page, url, k["Kino"], k["Strom"])


def test_mehrere_markierte_ziehen_eine_aenderung(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        k = _anlegen(url)
        _start(page, url)
        vorher = _api(url, "GET", "/api/aenderungen?limit=1")["eintraege"][0]["id"]
        _zeile(page, k["Kino"]).click()
        _zeile(page, k["Miete"]).click(modifiers=["Control"])
        # Ziel darf nicht unter einer gezogenen liegen
        _ziehen(page, _zeile(page, k["Miete"]), _zeile(page, k["Freizeit"]))
        _warte_eltern(page, url, k["Kino"], k["Freizeit"])
        assert _eltern(url, k["Miete"]) == k["Freizeit"]
        neu = [e for e in _api(url, "GET", "/api/aenderungen?limit=5")["eintraege"] if e["id"] > vorher]
        assert [e["aktion"] for e in neu] == ["kategorien_verschieben"]
        # beide bleiben markiert; Kontextmenü nennt die Zahl
        expect(page.locator('[data-testid="kategorienbaum"] [aria-selected="true"]')).to_have_count(2)
        _zeile(page, k["Kino"]).click(button="right")
        expect(tid(page, "km-konto-verschieben")).to_contain_text("2 Kategorien")
