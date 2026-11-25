"""Entwicklungstests für D-290: Kategorie setzen, Status setzen, Bestätigen und Tags wirken im Kontoblatt sofort,
noch bevor der Server davon weiß (schreibende Anfragen sind angehalten, bis der Test sie freigibt).
"""

from __future__ import annotations

from .test_browser import browser, expect, tid  # noqa: F401
from .test_browser_vorschlag_sofort import _lesen, blatt  # noqa: F401


def _ohne(url, konten):
    from .test_browser_tabs import _get
    alle = _get(url + "/api/buchungen", konto_id=konten["Giro"], pro_seite=200)["eintraege"]
    return [b for b in alle if not b["vorschlag"] and b["kategorie_id"] == konten["Lebensmittel"]]


def _zeile(page, bid):
    return tid(page, f"buchung-{bid}")


def _warte_server(page, pruefung):
    for _ in range(150):
        if pruefung():
            return
        page.wait_for_timeout(200)
    raise AssertionError("der Server hat die Änderung nicht bekommen: " + tid(page, "meldungen").inner_text())


def test_kategorie_setzen_wirkt_sofort(blatt):  # noqa: F811
    url, page, konten, mit, schranke = blatt
    b = _ohne(url, konten)[0]
    z = _zeile(page, b["id"])
    z.locator('[data-feld="datum"]').click()
    page.keyboard.press("k")
    PROBE = "(el) => { el.dataset.probe = 'ja'; }"
    tid(page, "kategorie-auswahl-suche").fill("Drogerie")
    page.keyboard.press("Enter")
    kat = z.locator('[data-feld="kategorie"]')
    expect(kat).to_have_attribute("data-kategorie-id", str(konten["Drogerie"]))
    expect(kat).to_contain_text("Drogerie")
    assert _lesen(url, b["id"])["kategorie_id"] == konten["Lebensmittel"], "der Server kennt die Änderung schon"
    # eine Buchung mit Vorschlag: Kategorie von Hand erledigt den Vorschlag und bestätigt
    v = mit[0]
    zv = _zeile(page, v["id"])
    zv.locator('[data-feld="datum"]').click()
    page.keyboard.press("k")
    tid(page, "kategorie-auswahl-suche").fill("Lebensmittel")
    page.keyboard.press("Enter")
    expect(zv).to_have_attribute("data-vorschlag", "nein")
    expect(zv.locator('[data-feld="kategorie"]')).to_have_attribute("data-kategorie-id", str(konten["Lebensmittel"]))
    z.evaluate(PROBE)   # dieselbe Zeile soll das Neuladen überstehen
    assert _lesen(url, v["id"])["vorschlag"] is not None, "der Server kennt die Änderung schon"
    schranke.freigeben()
    _warte_server(page, lambda: _lesen(url, b["id"])["kategorie_id"] == konten["Drogerie"]
                  and _lesen(url, v["id"])["vorschlag"] is None)
    expect(tid(page, "seite-konto")).to_have_attribute("data-ausstehend", "0", timeout=30_000)
    sv = _lesen(url, v["id"])
    assert (sv["kategorie_id"], sv["status"]) == (konten["Lebensmittel"], zv.get_attribute("data-status"))
    expect(kat).to_have_attribute("data-kategorie-id", str(konten["Drogerie"]))
    # der Stand des Servers gleicht dem vorweggenommenen: die Zeile wurde nicht neu gezeichnet
    expect(z).to_have_attribute("data-probe", "ja")
    expect(z.locator('[data-testid="tag"]')).not_to_have_attribute("data-tag-id", "0")


def test_bestaetigen_status_und_tags_wirken_sofort(blatt):  # noqa: F811
    url, page, konten, mit, schranke = blatt
    a, b, c = _ohne(url, konten)[:3]
    # b: als Torsten bestätigen – Tag und Status sofort
    za = _zeile(page, a["id"])
    za.locator('[data-feld="datum"]').click()
    page.keyboard.press("b")
    expect(za).to_have_attribute("data-bestaetigt", "Torsten")
    assert not _lesen(url, a["id"])["tags"], "der Server kennt die Änderung schon"
    # s: Status setzen
    zb = _zeile(page, b["id"])
    zb.locator('[data-feld="datum"]').click()
    page.keyboard.press("s")
    ziel = "bestaetigt" if b["status"] != "bestaetigt" else "importiert"
    tid(page, f"status-waehlen-{ziel}").click()
    expect(zb).to_have_attribute("data-status", ziel)
    # t: Tag hinzufügen – das Fenster schließt gleich, der Tag steht in der Zeile
    zc = _zeile(page, c["id"])
    zc.locator('[data-feld="datum"]').click()
    page.keyboard.press("t")
    tid(page, "tag-auswahl-name").fill("Urlaub")
    page.keyboard.press("Enter")
    expect(tid(page, "tag-auswahl")).to_be_hidden(timeout=5000)
    expect(zc.locator('[data-testid="tag"]')).to_have_text("Urlaub")
    assert _lesen(url, b["id"])["status"] == b["status"] and not _lesen(url, c["id"])["tags"], "der Server kennt die Änderung schon"
    schranke.freigeben()
    # währenddessen springt nichts zurück; am Ende hat der Server alle drei
    def fertig():
        assert za.get_attribute("data-bestaetigt") == "Torsten"
        assert zb.get_attribute("data-status") == ziel
        return (["Torsten" in t["name"] for t in _lesen(url, a["id"])["tags"]] == [True] and _lesen(url, b["id"])["status"] == ziel
                and [t["name"] for t in _lesen(url, c["id"])["tags"]] == ["Urlaub"])
    _warte_server(page, fertig)
    expect(tid(page, "seite-konto")).to_have_attribute("data-ausstehend", "0", timeout=30_000)
    expect(za).to_have_attribute("data-bestaetigt", "Torsten")
    expect(zc.locator('[data-testid="tag"]')).to_have_text("Urlaub")
    # Bestätigung zurücknehmen wirkt ebenfalls sofort
    za.locator('[data-feld="datum"]').click()
    page.keyboard.press("b")
    expect(za).not_to_have_attribute("data-bestaetigt", "Torsten")
