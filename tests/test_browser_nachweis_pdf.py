"""Entwicklungstests für das Feature „nachweis-pdf“ (D-303): Nachweis markierter Buchungen über `v p` und das
Kontextmenü, Dialog mit Kontoinhaber, Herunterladen der Datei. Playwright mit Chrome headless gegen einen echten
Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import datetime as dt
import io

import httpx
from pypdf import PdfReader

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401


def _welt(url):
    with httpx.Client(trust_env=False) as c:
        giro = c.post(url + "/api/konten", json={"name": "Giro NW", "art": "girokonto",
                                                "iban": "DE57000000000004711009"}).json()["id"]
        kat = c.post(url + "/api/konten", json={"name": "Miete NW", "art": "aufwand"}).json()["id"]
        ids = []
        for m in (4, 5, 6):
            r = c.post(url + "/api/buchungen", json={
                "datum": f"2026-{m:02d}-03", "verwendungszweck": f"Miete {m:02d}/2026",
                "splits": [{"konto_id": giro, "betrag": -98_000}, {"konto_id": kat, "betrag": 98_000}]})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
    return giro, kat, ids


def _pdf_text(download) -> str:
    with open(download.path(), "rb") as f:
        return "\n".join(s.extract_text() for s in PdfReader(io.BytesIO(f.read())).pages)


def test_v_p_und_kontextmenue(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False, mock_heute=dt.date(2026, 6, 20)) as (url, _), \
            seite(browser, url, **DESKTOP) as page:
        giro, kat, ids = _welt(url)
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        # zwei Buchungen markieren, dann v p
        tid(page, f"buchung-{ids[0]}").locator('[data-feld="datum"]').click()
        tid(page, f"buchung-{ids[2]}").locator('[data-feld="datum"]').click(modifiers=["Control"])
        page.keyboard.press("v")
        page.keyboard.press("p")
        dlg = tid(page, "nachweis-dialog")
        expect(dlg).to_be_visible()
        expect(tid(page, "nachweis-umfang")).to_contain_text("2 markierte Buchungen")
        expect(tid(page, "nachweis-inhaber")).to_be_focused()
        tid(page, "nachweis-inhaber").fill("Erika Mustermann (fiktiv)")
        with page.expect_download() as info:
            tid(page, "nachweis-ok").click()
        dl = info.value
        assert dl.suggested_filename == "kontor-nachweis-20260620.pdf"
        t = _pdf_text(dl)
        assert "Erika Mustermann (fiktiv)" in t
        assert "Miete 04/2026" in t and "Miete 06/2026" in t and "Miete 05/2026" not in t
        assert "Summe der 2 ausgewählten Buchungen" in t and "-1.960,00" in t
        assert "DE57 XXXX XXXX XXXX XXXX 1009" in t
        expect(dlg).to_have_count(0)
        # Kontextmenü auf einer Buchung
        tid(page, f"buchung-{ids[1]}").locator('[data-feld="datum"]').click()
        tid(page, f"buchung-{ids[1]}").click(button="right")
        tid(page, "km-nachweis").click()
        expect(tid(page, "nachweis-umfang")).to_contain_text("1 markierte Buchung")
        page.keyboard.press("Escape")
        expect(tid(page, "nachweis-dialog")).to_have_count(0)
        # D-310: auch im Kontoblatt einer Kategorie, als „Buchungsnachweis“
        page.goto(f"{url}/konten/{kat}")
        bereit(page, "konto")
        tid(page, f"buchung-{ids[1]}").locator('[data-feld="datum"]').click()
        tid(page, f"buchung-{ids[1]}").click(button="right")
        tid(page, "km-nachweis").click()
        expect(tid(page, "nachweis-umfang")).to_contain_text("1 markierte Buchung")
        with page.expect_download() as info:
            tid(page, "nachweis-ok").click()
        t = _pdf_text(info.value)
        assert "Buchungsnachweis" in t and "Miete NW" in t and "Miete 05/2026" in t and "-980,00" in t
        assert "Giro NW · DE57 XXXX XXXX XXXX XXXX 1009" in t
