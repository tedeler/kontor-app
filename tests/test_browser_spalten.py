"""Browser-Rauchtest zu D-130: veränderbare Spaltenbreiten der Buchungsliste (Ziehen, Doppelklick passt an, merken,
zurücksetzen) und dezente Markierung der Zeilen (Bearbeitungsstand, wiederkehrend). Synthetische Daten, eigener
Server auf einem freien Loopback-Port."""

from __future__ import annotations

import httpx

from kontor import buch, db, erwartung

from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401

LANG = "Sehr langer Verwendungszweck einer fiktiven Buchung, der weit über die übliche Spaltenbreite hinausgeht"


def _daten(url, config):
    c = httpx.Client(base_url=url)
    g = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Abo", "art": "aufwand"}).json()["id"]
    con = db.verbinde(config.aktive_datenbank)   # technisches Konto „Unkategorisiert“ wie bei der Synchronisation
    with db.transaktion(con):
        unk = buch.unkategorisiert_id(con)
    con.close()
    abo = c.post("/api/empfaenger", json={"name": "Abo AG (fiktiv)"}).json()["id"]
    laden = c.post("/api/empfaenger", json={"name": "Laden (fiktiv)"}).json()["id"]

    def buchen(datum, empf, gegen, status="bestaetigt", zweck=""):
        r = c.post("/api/buchungen", json={"datum": datum, "empfaenger_id": empf, "status": status,
                                            "verwendungszweck": zweck, "splits": [
                                                {"konto_id": g, "betrag": -1000}, {"konto_id": gegen, "betrag": 1000}]})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    ids = {"serie": [buchen(t, abo, kat) for t in ("2024-03-15", "2024-04-15", "2024-05-15", "2024-06-15")]}
    ids["importiert"] = buchen("2024-06-01", laden, unk, "importiert", LANG)
    ids["offen"] = buchen("2024-06-02", laden, unk, "vorlaeufig")
    ids["abgeglichen"] = buchen("2024-06-03", laden, kat)
    r = c.patch(f"/api/buchungen/{ids['abgeglichen']}", json={"status": "abgeglichen"})
    assert r.status_code == 200, r.text
    # aus einer Mail erkannte Bestellung (synthetisch), zugeordnet über die REST-Schnittstelle
    con = db.verbinde(config.aktive_datenbank)
    with db.transaktion(con):
        eid = erwartung._neu(con, grund="bestellung", richtung="ausgabe", anbieter="amazon", schluessel="amazon:bestellung:1",
                             kennung="000-0000000-0000001", referenz="", haendler="Amazon (fiktiv)", beschreibung="",
                             gesamt=1000, guthaben=0, datum="2024-06-01", frist="2024-06-06", bezug_id=None, mails=[],
                             zeitpunkt="2024-06-01T10:00:00Z")
    con.close()
    r = c.post(f"/api/erwartungen/{eid}/buchungen", json={"buchung_ids": [ids["serie"][-1]]})
    assert r.status_code == 200, r.text
    return g, ids


def test_markierung_der_zeilen(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **DESKTOP) as page:
        g, ids = _daten(url, config)
        page.goto(f"{url}/konten/{g}")
        bereit(page, "konto")
        zeile = lambda i: tid(page, f"buchung-{i}")  # noqa: E731
        expect(zeile(ids["importiert"])).to_have_attribute("data-markierung", "importiert")
        expect(zeile(ids["abgeglichen"])).to_have_attribute("data-markierung", "abgeglichen")
        assert zeile(ids["offen"]).get_attribute("data-markierung") is None
        for i in ids["serie"]:
            expect(zeile(i)).to_have_attribute("data-markierung", "kategorisiert")
            expect(zeile(i)).to_have_attribute("data-wiederkehrend", "ja")
        assert zeile(ids["importiert"]).get_attribute("data-wiederkehrend") is None
        # durch Mail bestätigt: nur die zugeordnete Buchung
        expect(zeile(ids["serie"][-1])).to_have_attribute("data-mail", "ja")
        assert zeile(ids["serie"][-1]).locator('[data-feld="empfaenger"]').get_attribute("title").endswith(
            "durch Mail bestätigt: Bestellung Amazon (fiktiv) 000-0000000-0000001")
        assert zeile(ids["serie"][0]).get_attribute("data-mail") is None
        # Zusatzmarke nur als Gestaltung: der Text der Zelle bleibt der Empfängername
        expect(zeile(ids["serie"][0]).locator('[data-feld="empfaenger"]')).to_have_text("Abo AG (fiktiv)")


def test_spaltenbreiten_ziehen_anpassen_merken(tmp_path, browser):  # noqa: F811
    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **DESKTOP) as page:
        g, ids = _daten(url, config)
        page.goto(f"{url}/konten/{g}")
        bereit(page, "konto")
        liste = tid(page, "buchungsliste")
        kopf = liste.locator('.liste-kopf [data-feld="empfaenger"]')
        breite = lambda loc: loc.bounding_box()["width"]  # noqa: E731
        vorher = breite(kopf)
        # Ziehen am Trenner verbreitert die Spalte, Zeilen folgen dem Kopf
        t = tid(page, "spalte-trenner-empfaenger").bounding_box()
        x, y = t["x"] + t["width"] / 2, t["y"] + t["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 60, y, steps=4)
        page.mouse.up()
        assert abs(breite(kopf) - (vorher + 60)) <= 2
        zelle = tid(page, f"buchung-{ids['importiert']}").locator('[data-feld="empfaenger"]')
        assert abs(breite(zelle) - breite(kopf)) <= 1
        # das Ziehen sortiert nicht
        expect(liste.locator('.liste-kopf [data-feld="empfaenger"]')).to_have_attribute("aria-sort", "none")
        # Doppelklick auf den Trenner: Verwendungszweck so breit wie der längste Text
        zweck = liste.locator('.liste-kopf [data-feld="verwendungszweck"]')
        tid(page, "spalte-trenner-verwendungszweck").dblclick()
        z = tid(page, f"buchung-{ids['importiert']}").locator('[data-feld="verwendungszweck"]')
        assert z.evaluate("e => e.scrollWidth <= e.clientWidth")
        assert breite(zweck) > 400
        gemerkt = breite(zweck)
        # gemerkt über das Neuladen hinweg
        page.reload()
        bereit(page, "konto")
        assert abs(breite(liste.locator('.liste-kopf [data-feld="verwendungszweck"]')) - gemerkt) <= 1
        # Kontextmenü des Kopfes setzt zurück
        liste.locator(".liste-kopf").click(button="right")
        tid(page, "km-spalten-zuruecksetzen").click()
        expect(liste).not_to_have_class("buchungsliste spalten-eigen")
        assert breite(liste.locator('.liste-kopf [data-feld="verwendungszweck"]')) < gemerkt
