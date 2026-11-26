"""Entwicklungstests für das Feature „tabellenbreite“ (D-293): kein Umbruch mitten im Wort in Tabellen und Karten.
Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import httpx
import pytest

from .test_browser import HANDY, bereit, browser, expect, seite, server, tid  # noqa: F401
from .test_browser_tabs import _daten

# Wörter (nur Buchstaben und Ziffern, ab drei Zeichen), die über mehrere Zeilen laufen; technische Zeichenketten
# (code, Links) dürfen umbrechen.
ZERBROCHEN = r"""
() => {
  const funde = [];
  const haupt = document.querySelector('[data-testid="hauptbereich"]');
  const w = document.createTreeWalker(haupt, NodeFilter.SHOW_TEXT);
  const r = document.createRange();
  while (w.nextNode()) {
    const n = w.currentNode, el = n.parentElement;
    if (!el || !el.getClientRects().length || el.closest("code, a, .technisch")) continue;
    const re = /[\p{L}\p{N}]{3,}/gu;
    let m;
    while ((m = re.exec(n.data))) {
      r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
      const zeilen = new Set([...r.getClientRects()].filter((x) => x.width > 0.5).map((x) => Math.round(x.top)));
      if (zeilen.size > 1) funde.push(m[0]);
    }
  }
  return funde;
}
"""


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        for name, art in (("Versicherungen und Gesundheit", "aufwand"), ("Kraftfahrzeugversicherung", "aufwand"),
                          ("Wohnungsdarlehen Musterbank", "kreditkonto")):
            assert c.post(url + "/api/konten", json={"name": name, "art": art}).status_code == 201
        for name in ("Hausverwaltung Musterstadt (fiktiv)", "Verkehrsverbund Beispielland (fiktiv)"):
            assert c.post(url + "/api/empfaenger", json={"name": name}).status_code == 201


@pytest.mark.parametrize("ansicht", ["handy", "schmal", "breit"])
def test_keine_woerter_mitten_im_wort_umbrochen(tmp_path, browser, ansicht):  # noqa: F811
    _daten(tmp_path)
    groesse = {"handy": HANDY, "schmal": {"viewport": {"width": 768, "height": 900}},
               "breit": {"viewport": {"width": 1280, "height": 900}}}[ansicht]
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **groesse) as page:
        _welt(url)
        for pfad, name in (("/", "uebersicht"), ("/konten", "konten"), ("/kategorien", "kategorien"),
                           ("/empfaenger", "empfaenger"), ("/tags", "tags"), ("/erwartet", "erwartet"),
                           ("/protokoll", "protokoll"), ("/konfiguration", "konfiguration")):
            page.goto(url + pfad)
            bereit(page, name)
            umschalten = tid(page, "uebersicht-kategorien-umschalten")
            if pfad == "/" and umschalten.get_attribute("aria-expanded") == "false":
                umschalten.click()
                expect(tid(page, "uebersicht-gruppe-aufwand")).to_be_visible()
            assert page.evaluate(ZERBROCHEN) == [], (ansicht, pfad)
            # die Seite selbst rollt nicht waagerecht; breite Tabellen rollen in ihrem Rahmen
            assert page.evaluate("() => { const h = document.querySelector('[data-testid=\"hauptbereich\"]');"
                                 " return h.scrollWidth <= h.clientWidth + 2; }"), (ansicht, pfad)


def test_ueberschrift_der_kategorientabellen_am_handy(tmp_path, browser):  # noqa: F811
    """Die gemeldete Darstellung: „Ausgaben“ stand am Handy Buchstabe für Buchstabe untereinander."""
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        umschalten = tid(page, "uebersicht-kategorien-umschalten")
        if umschalten.get_attribute("aria-expanded") == "false":
            umschalten.click()
        titel = tid(page, "uebersicht-gruppe-aufwand").locator("caption")
        expect(titel).to_have_text("Ausgaben")
        box = titel.bounding_box()
        assert box["width"] > 200 and box["height"] < 60, box
