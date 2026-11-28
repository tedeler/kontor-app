"""Nachgezogene Tests zum Feature „status-farben“ (Aufräumen, D-327): Verhalten, das bisher nur von Hand geprüft war.

- D-260: Bestätigen einer roten (importierten) Buchung ohne Kategorie fragt zuerst nach Kategorie oder Konto; ohne
  Wahl wird nicht bestätigt.
- D-264: Die Kategorieauswahl legt eine neue Kategorie an und wählt sie.
- D-267: Im Split-Dialog lässt sich eine Split-Vorlage von Hand übernehmen, auch wenn ihr Betrag nicht passt.

Playwright mit Chrome headless gegen einen echten Server im Mock-Modus (synthetische Daten).
"""

from __future__ import annotations

import httpx
import pytest

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401


def _api(url, methode, pfad, **kw):
    with httpx.Client(trust_env=False) as c:
        r = c.request(methode, url + pfad, **kw)
        assert r.status_code < 300, r.text
        return r.json()


def _warte(page, pruefung, text):
    for _ in range(100):
        if pruefung():
            return
        page.wait_for_timeout(100)
    raise AssertionError(text)


@pytest.fixture
def blatt(tmp_path, browser):  # noqa: F811
    """Mock-Synchronisation: alle Umsätze des Girokontos sind importiert und ohne Kategorie (Unkategorisiert)."""
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        assert _api(url, "POST", "/api/sync", json={})["status"] == "erfolgreich"
        konten = {k["name"]: k["id"] for k in _api(url, "GET", "/api/konten")}
        for name in ("Lebensmittel", "Drogerie"):
            konten[name] = _api(url, "POST", "/api/konten", json={"name": name, "art": "aufwand"})["id"]
        giro = konten["Girokonto (Mock)"]
        buchungen = _api(url, "GET", f"/api/buchungen?konto_id={giro}&pro_seite=200")["eintraege"]
        offen = [b for b in buchungen if b["status"] == "importiert" and b["kategorie_id"] is None and b["betrag"] < 0]
        assert len(offen) >= 3
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        yield url, page, konten, offen


def _lesen(url, bid):
    return _api(url, "GET", f"/api/buchungen/{bid}")


def _markieren(page, bid):
    tid(page, f"buchung-{bid}").locator('[data-feld="datum"]').click()


def test_bestaetigen_ohne_kategorie_fragt_nach(blatt):
    url, page, konten, offen = blatt
    a, b = offen[0], offen[1]
    # ohne Wahl (Esc): nicht bestätigt
    _markieren(page, a["id"])
    page.keyboard.press("b")
    expect(tid(page, "kategorie-auswahl")).to_be_visible()
    page.keyboard.press("Escape")
    expect(tid(page, "kategorie-auswahl")).to_be_hidden()
    page.wait_for_timeout(300)
    assert _lesen(url, a["id"])["status"] == "importiert"
    # mit Wahl: zuerst zugeordnet, dann bestätigt (mit Personen-Tag)
    _markieren(page, b["id"])
    page.keyboard.press("b")
    tid(page, "kategorie-auswahl-suche").fill("Lebensmittel")
    page.keyboard.press("Enter")
    _warte(page, lambda: _lesen(url, b["id"])["status"] == "bestaetigt" and _lesen(url, b["id"])["tags"],
           "nicht bestätigt")
    s = _lesen(url, b["id"])
    assert s["kategorie_id"] == konten["Lebensmittel"]
    assert [t["name"] for t in s["tags"]] == ["Torsten-Bestätigt"]


def test_kategorie_in_der_auswahl_anlegen(blatt):
    url, page, konten, offen = blatt
    b = offen[2]
    _markieren(page, b["id"])
    page.keyboard.press("k")
    tid(page, "kategorie-auswahl-suche").fill("Haustier")
    # kein Treffer: Enter öffnet das Formular, vorbelegt mit dem Suchtext
    page.keyboard.press("Enter")
    expect(tid(page, "kategorie-neu")).to_be_visible()
    expect(tid(page, "kategorie-neu-name")).to_have_value("Haustier")
    tid(page, "kategorie-neu-eltern").select_option(label="Lebensmittel")
    tid(page, "kategorie-neu-anlegen").click()
    _warte(page, lambda: _lesen(url, b["id"])["kategorie_id"] not in (None,), "nicht zugeordnet")
    neu = _api(url, "GET", f"/api/konten/{_lesen(url, b['id'])['kategorie_id']}")
    assert (neu["name"], neu["art"], neu["eltern_id"]) == ("Haustier", "aufwand", konten["Lebensmittel"])
    # gleichnamige Kategorie auf derselben Ebene: Fehler im Fenster, nichts angelegt
    _markieren(page, offen[0]["id"])
    page.keyboard.press("k")
    tid(page, "kategorie-auswahl-neu").click()
    tid(page, "kategorie-neu-name").fill("Drogerie")
    tid(page, "kategorie-neu-anlegen").click()
    expect(tid(page, "kategorie-auswahl").get_by_test_id("dialog-fehler")).to_be_visible()
    assert sum(k["name"] == "Drogerie" for k in _api(url, "GET", "/api/konten")) == 1


def test_split_vorlage_von_hand_uebernehmen(blatt):
    url, page, konten, offen = blatt
    b = offen[0]
    betrag = -b["betrag"]
    teile = [{"kategorie_id": konten["Lebensmittel"], "betrag": 1000, "memo": "Essen"},
             {"kategorie_id": konten["Drogerie"], "betrag": 500, "memo": "Pflege"}]
    _api(url, "POST", "/api/vorlagen", json={"name": "Wocheneinkauf", "teile": teile,
                                             "bedingungen": [{"feld": "empfaenger", "operator": "gleich",
                                                              "wert": "Niemand (erfunden)"}]})
    _markieren(page, b["id"])
    page.keyboard.press("x")
    d = tid(page, "split-dialog")
    expect(d).to_be_visible()
    wahl = tid(page, "split-vorlage-wahl")
    expect(wahl).to_be_enabled()
    wahl.select_option(label="Wocheneinkauf (15,00 €)")
    # Teile wie in der Vorlage; der offene Rest wird genannt, gespeichert wird erst bei Summe 0
    expect(tid(page, "split-vorlage-hinweis")).to_be_visible()
    expect(tid(page, "split-vorlage-hinweis")).to_contain_text("Wocheneinkauf")
    zeilen = d.locator('[data-testid^="split-zeile-"]')
    expect(zeilen).to_have_count(3)
    ausgleichen = d.locator('[data-testid^="split-ausgleichen-"]').nth(1)
    ausgleichen.click()
    expect(tid(page, "split-rest")).to_have_attribute("data-betrag", "0")
    tid(page, "split-speichern").click()
    expect(d).to_be_hidden()

    def gespeichert():
        s = _lesen(url, b["id"])
        return len(s["splits"]) == 3

    _warte(page, gespeichert, "Splits nicht gespeichert")
    s = _lesen(url, b["id"])
    kat = {sp["konto_id"]: sp["betrag"] for sp in s["splits"] if sp["konto_id"] in (konten["Lebensmittel"], konten["Drogerie"])}
    assert sum(kat.values()) == betrag
    assert kat[konten["Drogerie"]] == 500 or kat[konten["Lebensmittel"]] == 1000
    assert s["status"] == "bestaetigt"   # D-261: Zuordnung von Hand bestätigt
