"""Entwicklungstests für das Feature „dialog-tastatur“ (D-298): Jeder Dialog lässt sich mit der Tastatur bedienen.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).

Geprüft wird je Dialog dasselbe (oberflaeche.md 9): Fokus beim Öffnen im Dialog, Tab und Umschalt+Tab bleiben im
Dialog, Pfeiltasten wechseln zwischen den Knöpfen einer Knopfleiste, Esc schließt und gibt den Fokus zurück.
"""

from __future__ import annotations

import httpx
import pytest

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _get

ZEILEN = '[data-testid="buchungsliste"] [role="row"][data-testid^="buchung-"]'

# Testkennung des Dialogs, in dem der Fokus steht (leer: außerhalb jedes Dialogs), und des fokussierten Elements
FOKUS = """() => {
  const a = document.activeElement;
  const d = a && a.closest ? a.closest('[role="dialog"]') : null;
  return { dialog: d ? d.dataset.testid : '', el: a ? (a.dataset.testid || a.tagName + ':' + (a.textContent || '').trim().slice(0, 30)) : '' };
}"""

# Knöpfe der ersten Knopfleiste im Dialog mit mindestens zwei bedienbaren Knöpfen
LEISTE = """(testid) => {
  const box = document.querySelector(`[data-testid="${testid}"]`);
  for (const l of box.querySelectorAll('.knopf-leiste')) {
    const k = [...l.querySelectorAll('button')].filter((b) => !b.disabled && b.offsetParent !== null);
    if (k.length >= 2) return k.map((b, i) => { b.dataset.pruefNr = String(i); return i; }).length;
  }
  return 0;
}"""


def _fokus(page):
    return page.evaluate(FOKUS)


def _pruefen(page, testid, oeffnen, mit_leiste=True):
    oeffnen()
    expect(tid(page, testid)).to_be_visible()
    vorher = None
    f = _fokus(page)
    assert f["dialog"] == testid, (testid, "Fokus beim Öffnen", f)
    for taste in ["Tab"] * 15 + ["Shift+Tab"] * 4:
        page.keyboard.press(taste)
        f = _fokus(page)
        assert f["dialog"] == testid, (testid, taste, f)
    n = page.evaluate(LEISTE, testid)
    if mit_leiste:
        assert n >= 2, (testid, "keine Knopfleiste mit zwei Knöpfen")
    if n >= 2:
        knopf = lambda i: tid(page, testid).locator(f'button[data-pruef-nr="{i}"]')  # noqa: E731
        knopf(0).focus()
        vorher = _fokus(page)["el"]
        page.keyboard.press("ArrowRight")
        assert _fokus(page)["el"] != vorher, (testid, "Pfeil rechts", vorher)
        expect(knopf(1)).to_be_focused()
        page.keyboard.press("ArrowLeft")
        expect(knopf(0)).to_be_focused()
        page.keyboard.press("ArrowLeft")                    # umlaufend
        expect(knopf(n - 1)).to_be_focused()
        page.keyboard.press("ArrowRight")
        expect(knopf(0)).to_be_focused()
        page.keyboard.press("End")
        expect(knopf(n - 1)).to_be_focused()
        page.keyboard.press("Home")
        expect(knopf(0)).to_be_focused()
        page.keyboard.press("ArrowDown")                    # wie Tab: nächstes Bedienelement
        assert _fokus(page)["dialog"] == testid
        assert _fokus(page)["el"] != vorher or len(tid(page, testid).locator("button, input, select, textarea").all()) == 1
    page.keyboard.press("Escape")
    expect(tid(page, testid)).to_have_count(0)
    f = _fokus(page)
    assert f["dialog"] == "" and not f["el"].startswith("BODY"), (testid, "Fokus nach Esc", f)


def _kontoblatt(page, url):
    giro = next(k["id"] for k in _get(url + "/api/konten") if k["name"] == "Giro")
    page.goto(f"{url}/konten/{giro}")
    bereit(page, "konto")
    zeile = page.locator(ZEILEN).nth(1)
    zeile.locator('[data-feld="datum"]').click()
    return zeile


@pytest.mark.parametrize("taste,testid,leiste", [
    ("Delete", "bestaetigen-dialog", True),
    ("k", "kategorie-auswahl", False),
    ("t", "tag-auswahl", True),
    ("s", "status-auswahl", False),
    ("e", "mehrfach-dialog", False),          # „Übernehmen“ erst nach einer Änderung bedienbar
    ("x", "split-dialog", True),
    ("M", "mail-auswahl-dialog", False),
    ("n", "erfassen-dialog", True),
    ("h", "tastatur-hilfe", False),
    ("Control+k", "befehlspalette", False),
])
def test_dialoge_im_kontoblatt(tmp_path, browser, taste, testid, leiste):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        zeile = _kontoblatt(page, url)

        def oeffnen():
            zeile.locator('[data-feld="datum"]').click()
            page.keyboard.press(taste)
        _pruefen(page, testid, oeffnen, leiste)


def test_dialoge_auf_anderen_seiten(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        kat = next(k["id"] for k in _get(url + "/api/konten") if k["art"] == "aufwand")
        with httpx.Client(trust_env=False) as c:
            assert c.post(url + "/api/regeln", json={"name": "Probe", "kategorie_id": kat, "bedingungen": [
                {"feld": "verwendungszweck", "operator": "enthaelt", "wert": "Probe"}]}).status_code == 201
        page.goto(url + "/regeln")
        bereit(page, "regeln")
        _pruefen(page, "bestaetigen-dialog", lambda: page.get_by_role("button", name="Regel Probe löschen").click())
        _pruefen(page, "regel-dialog", lambda: tid(page, "regel-anlegen").click())
        page.goto(url + "/konten")
        bereit(page, "konten")
        _pruefen(page, "konto-dialog", lambda: tid(page, "konto-anlegen").click())
        page.goto(url + "/tags")
        bereit(page, "tags")
        _pruefen(page, "tag-dialog", lambda: tid(page, "tag-anlegen").click())
        page.goto(url + "/erwartet")
        bereit(page, "erwartet")
        _pruefen(page, "erwartung-dialog", lambda: tid(page, "erwartung-anlegen").click())
        page.goto(url + "/")
        bereit(page, "uebersicht")
        _pruefen(page, "ueber-dialog", lambda: tid(page, "ueber-knopf").click(), False)
