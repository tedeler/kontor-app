"""Eigene Browsertests zum UX-Durchgang auf feature/sammel3 (D-236): Lesbarkeit und Platz in Kontoblatt, Mail-Blatt,
Tags, Empfängern und Dubletten. Nur synthetische Daten."""
from __future__ import annotations

import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

TEXTMAIL = ("From: Laden <laden@example.invalid>\r\nTo: haushalt.eins@example.invalid\r\nSubject: Ihre Erstattung\r\n"
            "Date: Mon, 03 Jun 2024 10:00:00 +0200\r\nMessage-ID: <text-1@example.invalid>\r\nMIME-Version: 1.0\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n\r\nHallo Erika,\r\nErstattungsbetrag: 9,99 EUR\r\n").encode()


def _client(url):
    import httpx
    return httpx.Client(base_url=url, trust_env=False, timeout=60)


def _giro(c):
    return next(k["id"] for k in c.get("/api/konten").json() if k["name"] == "Giro")


def _kasten(page, auswahl):
    return page.locator(auswahl).first.bounding_box()


def test_textmail_zeigt_keine_leeren_teile_als_wort(tmp_path, browser):
    """Fund 1: ohne Bilder-Leiste und Anhänge darf nicht „null“ in der Mail-Ansicht stehen."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        b = c.get("/api/buchungen", params={"pro_seite": 1}).json()["eintraege"][0]
        assert c.post("/api/dokumente", params={"buchung_id": [b["id"]]},
                      files={"datei": ("mail.eml", TEXTMAIL, "message/rfc822")}).status_code == 201
        page.goto(f"{url}/konten/{b['splits'][0]['konto_id']}?buchung={b['id']}")
        bereit(page, "konto")
        tid(page, f"beleg-marke-{b['id']}").click()
        text = page.get_by_text("Erstattungsbetrag: 9,99 EUR")
        expect(text).to_be_visible()
        # die ganze Ansicht um den Mailtext: Kopf, Text, sonst nichts
        rahmen = text.locator("xpath=ancestor::*[.//dt][1]")
        assert "null" not in rahmen.inner_text(), rahmen.inner_text()
        assert "Ihre Erstattung" in rahmen.inner_text()


def test_betrag_bleibt_sichtbar_und_markieren_verschiebt_nichts(tmp_path, browser):
    """Funde 2, 3, 6: Betrag und Gruppensumme liegen im sichtbaren Teil der Liste; die Auswahl-Summen verschieben
    die Liste nicht."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        giro = _giro(c)
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        spalte = _kasten(page, ".listen-spalte")
        zeile = page.locator(".buchungsliste .zeile").first
        betrag = zeile.locator(".zelle-betrag").bounding_box()
        assert betrag["x"] >= spalte["x"] and betrag["x"] + betrag["width"] <= spalte["x"] + spalte["width"] + 1, (betrag, spalte)
        vorher = _kasten(page, "[data-testid=buchungsliste]")["y"]
        zeile.locator(".zelle-datum").click()
        expect(tid(page, "auswahl-summen")).to_be_visible()
        assert _kasten(page, "[data-testid=buchungsliste]")["y"] == vorher
        page.keyboard.press("Escape")
        # gruppiert: die Summe am Balken ist zu sehen
        tid(page, "gruppierung-monat").click()
        summe = page.locator(".perioden-balken [data-testid^=periode-summe-]").first
        expect(summe).to_be_visible()
        s = summe.bounding_box()
        assert s["x"] + s["width"] <= spalte["x"] + spalte["width"] + 1, (s, spalte)
        expect(tid(page, "gruppierung-zu")).to_have_attribute("aria-label", "Alles zusammenklappen")


def test_handy_kontoblatt_beginnt_mit_der_liste(tmp_path, browser):
    """Fund 4: Filterfeld, Zeitraum und Gruppierung sind am Handy eingeklappt; ein Knopf klappt sie auf."""
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        c = _client(url)
        page.goto(f"{url}/konten/{_giro(c)}")
        bereit(page, "konto")
        erste = page.locator(".buchungsliste .zeile").first.bounding_box()
        assert erste["y"] < 844 * 0.45, erste
        expect(tid(page, "filter-schnell")).to_be_hidden()
        expect(tid(page, "gruppierung-keine")).to_be_hidden()
        expect(tid(page, "filter-baukasten-umschalten")).to_be_visible()
        tid(page, "ansicht-umschalten").click()
        expect(tid(page, "ansicht-umschalten")).to_have_attribute("aria-expanded", "true")
        expect(tid(page, "filter-schnell")).to_be_visible()
        expect(tid(page, "gruppierung-keine")).to_be_visible()
        expect(tid(page, "filter-ausdruck")).to_be_visible()


def test_desktop_zeigt_filter_und_gruppierung_immer(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(f"{url}/konten/{_giro(_client(url))}")
        bereit(page, "konto")
        expect(tid(page, "ansicht-umschalten")).to_be_hidden()
        expect(tid(page, "filter-schnell")).to_be_visible()
        expect(tid(page, "gruppierung-keine")).to_be_visible()


def test_handy_mailblatt_zeigt_zuerst_die_liste(tmp_path, browser):
    """Fund 5: am Handy ist keine Mail vorgewählt; Antippen öffnet den Lesebereich, ✕ schließt ihn."""
    with server(tmp_path) as (url, _), seite(browser, url, **HANDY) as page:
        c = _client(url)
        assert c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
        assert c.post("/api/mail/abruf").status_code == 200
        mails = c.get("/api/mail/nachrichten", params={"reihenfolge": "neueste"}).json()["eintraege"]
        page.goto(url + "/mail")
        bereit(page, "mail")
        expect(tid(page, "mail-tabelle")).to_be_visible()
        expect(tid(page, "mail-lesen")).to_be_hidden()
        expect(page.locator("[data-testid=mail-tabelle] tr[aria-selected=true]")).to_have_count(0)
        tid(page, f"mail-{mails[0]['id']}").click()
        expect(tid(page, "mail-lesen")).to_be_visible()
        tid(page, "mail-lesen-schliessen").click()
        expect(tid(page, "mail-lesen")).to_be_hidden()


def test_mailblatt_desktop_blaettern_unter_der_liste(tmp_path, browser):
    """Fund 9: Blättern steht unter der Liste; die erste Mail ist am Desktop weiter vorgewählt."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        assert c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
        assert c.post("/api/mail/abruf").status_code == 200
        page.goto(url + "/mail")
        bereit(page, "mail")
        expect(page.locator("[data-testid=mail-tabelle] tr[aria-selected=true]")).to_have_count(1)
        liste = _kasten(page, "[data-testid=mail-liste]")
        blaettern = _kasten(page, "[data-testid=mail-blaetter]")
        assert blaettern["y"] >= liste["y"] + liste["height"] - 1, (liste, blaettern)


def test_empfaenger_suche_buchungszahl_und_menue(tmp_path, browser):
    """Fund 10: Suche über Name und Alias, Buchungszahl je Empfänger, Menü über „⋯“."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        a = c.post("/api/empfaenger", json={"name": "Stadtwerke Musterstadt"}).json()["id"]
        b = c.post("/api/empfaenger", json={"name": "Buchhandlung Seitenweise"}).json()["id"]
        assert c.patch(f"/api/empfaenger/{b}", json={"aliase": ["Lesestoff GmbH"]}).status_code == 200
        buchung = c.get("/api/buchungen", params={"pro_seite": 1}).json()["eintraege"][0]
        assert c.patch(f"/api/buchungen/{buchung['id']}", json={"empfaenger_id": a}).status_code == 200
        zahlen = {x["empfaenger_id"]: x["anzahl"] for x in c.get("/api/empfaenger/anzahlen").json()}
        assert zahlen.get(a) == 1 and b not in zahlen
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        expect(tid(page, f"empfaenger-{a}").locator("[data-feld=anzahl]")).to_have_text("1")
        expect(tid(page, f"empfaenger-{b}").locator("[data-feld=anzahl]")).to_have_text("0")
        tid(page, "empfaenger-suche").fill("lesestoff")
        expect(tid(page, f"empfaenger-{b}")).to_be_visible()
        expect(tid(page, f"empfaenger-{a}")).to_be_hidden()
        expect(tid(page, "empfaenger-treffer")).to_contain_text("1 von")
        tid(page, "empfaenger-suche").fill("")
        expect(tid(page, f"empfaenger-{a}")).to_be_visible()
        tid(page, f"empfaenger-menue-{a}").click()
        expect(tid(page, "em-bearbeiten")).to_be_visible()
        expect(tid(page, "em-regel")).to_be_visible()


def test_tags_dubletten_und_tabs_aufraeumen(tmp_path, browser):
    """Funde 7, 8, 11, 14: eigene Knöpfe je Tag, Gegenüberstellung der Dubletten, „Andere schließen“ ab sechs Tabs."""
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = _client(url)
        tag = c.post("/api/tags", json={"name": "Urlaub"}).json()["id"]
        buchungen = c.get("/api/buchungen", params={"pro_seite": 5, "sortierung": "datum"}).json()["eintraege"]
        ids = [x["id"] for x in buchungen[:2]]
        assert c.post("/api/dubletten", json={"buchung_ids": ids}).status_code == 201
        page.goto(url + "/tags")
        bereit(page, "tags")
        expect(tid(page, f"tag-umbenennen-{tag}")).to_be_visible()
        expect(tid(page, f"tag-loeschen-{tag}")).to_be_visible()
        page.goto(url + "/dubletten")
        bereit(page, "dubletten")
        vergleich = page.locator(".dubletten-vergleich").first
        expect(vergleich.locator("tr[data-feld=datum]")).to_have_attribute("data-abweichung", "ja")
        expect(vergleich.locator("tr[data-feld=konto]")).to_have_attribute("data-abweichung", "nein")
        expect(page.locator("[data-testid=dubletten-liste]")).to_contain_text("löscht die andere Buchung")
        expect(tid(page, f"dublette-buchung-{ids[0]}")).to_contain_text("Diese behalten")
        # Tabs: erst ab sechs erscheint „Andere schließen“
        expect(tid(page, "tab-andere-schliessen")).to_have_count(0)
        for pfad, name in (("/empfaenger", "empfaenger"), ("/regeln", "regeln"), ("/kategorien", "kategorien"), ("/", "uebersicht")):
            page.locator(f'nav a[href="{pfad}"]').first.click()
            bereit(page, name)
        expect(page.locator("[data-testid=tab-leiste] [data-pfad]")).to_have_count(6)
        tid(page, "tab-andere-schliessen").click()
        expect(page.locator("[data-testid=tab-leiste] [data-pfad]")).to_have_count(1)
        expect(tid(page, "tab-andere-schliessen")).to_have_count(0)
