"""Browser-Rauchtests des Sammelpakets `feature/sammel3` (D-218 ff.)."""

from __future__ import annotations

import sqlite3

import pytest

from .conftest import kmy, transaktion
from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

KONTEN = ('<ACCOUNT id="A1" name="Giro" type="1" parentaccount="AStd::Asset" currency="EUR"/>'
          '<ACCOUNT id="A3" name="Spar" type="1" parentaccount="AStd::Asset" currency="EUR"/>'
          '<ACCOUNT id="A2" name="Lebensmittel" type="13" parentaccount="AStd::Expense" currency="EUR"/>')
PAYEES = '<PAYEE id="P1" name="Markt"/><PAYEE id="P2" name="Bäcker"/>'


def _daten(config):
    from kontor.importer.kmymoney import importiere_kmy
    t = "".join(transaktion(f"T{i}", f"2024-01-{i:02d}", ("A1" if i < 4 else "A3", "-5/1"), ("A2", "5/1"))
                .replace("<TRANSACTION", "<TRANSACTION").replace('<SPLIT account="A', '<SPLIT payee="P1" account="A', 1)
                for i in range(1, 6))
    assert importiere_kmy(config, kmy(KONTEN, payees=PAYEES, transaktionen=t)).erfolgreich


def test_empfaenger_menue_regel_und_konto(tmp_path, browser):
    with server(tmp_path, daten=False) as (url, config), seite(browser, url, **DESKTOP) as page:
        _daten(config)
        con = sqlite3.connect(config.aktive_datenbank)
        markt, = con.execute("SELECT id FROM empfaenger WHERE name = 'Markt'").fetchone()
        con.execute("INSERT INTO empfaenger_alias (empfaenger_id, alias, ekey) VALUES (?, 'MARKT \"GMBH\"', 'marktgmbh')", (markt,))
        con.commit()
        con.close()
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        expect(tid(page, "empfaenger-liste")).not_to_contain_text("Standardkategorie")
        tid(page, f"empfaenger-{markt}").click(button="right")
        expect(tid(page, "em-regel")).to_be_visible()
        # zwei Konten mit Buchungen: Untermenü, das meistbenutzte zuerst
        tid(page, "em-im-konto").hover()
        eintraege = page.locator("[data-testid^=em-im-konto-]")
        expect(eintraege).to_have_count(2)
        expect(eintraege.first).to_have_text("Giro (3)")
        eintraege.first.click()
        bereit(page, "konto")
        assert "/konten/" in page.url
        expect(page.locator("[data-testid^=buchung-zeile-], [role=row][data-id]")).to_have_count(3)
        # Regel erstellen: Editor mit Empfänger und Alias vorbelegt
        page.goto(url + "/empfaenger")
        bereit(page, "empfaenger")
        tid(page, f"empfaenger-{markt}").click(button="right")
        tid(page, "em-regel").click()
        expect(tid(page, "regel-dialog")).to_be_visible()
        expect(tid(page, "regel-name")).to_have_value("Markt")


def test_spalten_ausblenden_und_bestaetigen(tmp_path, browser):
    with server(tmp_path) as (url, config), seite(browser, url, **DESKTOP) as page:
        con = sqlite3.connect(config.aktive_datenbank)
        giro, = con.execute("SELECT id FROM konto WHERE name = 'Giro'").fetchone()
        con.close()
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        kopf = page.locator(".liste-kopf")
        expect(kopf.locator(".zelle-tags")).to_be_visible()
        breite = kopf.locator(".zelle-betrag").bounding_box()
        kopf.locator(".zelle-verwendungszweck").click(button="right", position={"x": 5, "y": 5})
        tid(page, "km-spalten-wahl").hover()
        tid(page, "km-spalte-status").click()
        expect(kopf.locator(".zelle-status")).to_be_hidden()
        expect(page.locator(".zeile .zelle-status").first).to_be_hidden()
        expect(kopf.locator(".zelle-tags")).to_be_visible()
        # das Raster besteht nur noch aus den sichtbaren Spalten: der Betrag schließt an die Tags an
        # (ganz nach rechts gerollt: der Betrag klebt sonst am rechten Rand über den anderen Spalten, D-236)
        page.evaluate("() => { const s = document.querySelector('.listen-spalte'); s.scrollLeft = s.scrollWidth; }")
        neu = kopf.locator(".zelle-betrag").bounding_box()
        tags = kopf.locator(".zelle-tags").bounding_box()
        assert abs(neu["x"] - (tags["x"] + tags["width"])) < 2 and abs(neu["width"] - breite["width"]) < 2
        # gemerkt über das Neuladen
        page.reload()
        bereit(page, "konto")
        expect(page.locator(".liste-kopf .zelle-status")).to_be_hidden()
        # wieder einblenden
        page.locator(".liste-kopf .zelle-datum").click(button="right", position={"x": 5, "y": 5})
        tid(page, "km-spalten-wahl").hover()
        expect(tid(page, "km-spalte-status")).to_contain_text("Status")
        tid(page, "km-spalte-status").click()
        expect(page.locator(".liste-kopf .zelle-status")).to_be_visible()
        # Bestätigen setzt das Tag „Torsten-Bestätigt“ (D-262)
        zeile = page.locator(".zeile").first
        zeile.click(button="right", position={"x": 20, "y": 8})
        tid(page, "km-bestaetigen").click()
        expect(page.locator(".zeile[data-bestaetigt=Torsten] .tag-person").first).to_have_text("Torsten-Bestätigt")


def test_personentags_werden_umbenannt(tmp_path):
    from fastapi.testclient import TestClient

    from kontor.app import create_app
    from kontor.config import KontorConfig
    config = KontorConfig(datenbank=tmp_path / "k.sqlite3")
    c = TestClient(create_app(config))
    c.post("/api/tags", json={"name": "Torsten"})
    c.post("/api/tags", json={"name": "Tina"})
    c.post("/api/tags", json={"name": "B-Tina"})
    c = TestClient(create_app(config))
    assert sorted(t["name"] for t in c.get("/api/tags").json()) == ["Tina-Bestätigt", "Torsten-Bestätigt"]


def test_tags_seite_und_dubletten_sprung(tmp_path, browser):
    import httpx
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False)
        tag = c.post("/api/tags", json={"name": "Urlaub"}).json()["id"]
        buchungen = c.get("/api/buchungen", params={"pro_seite": 5, "sortierung": "datum"}).json()["eintraege"]
        ids = [b["id"] for b in buchungen[:2]]
        assert c.post("/api/buchungen/mehrfach/tags", json={"buchung_ids": ids, "hinzufuegen": [tag], "entfernen": []}).status_code == 200
        assert c.post("/api/dubletten", json={"buchung_ids": ids}).status_code == 201
        page.goto(url + "/")
        bereit(page, "uebersicht")
        tid(page, "navlink-tags").click()
        bereit(page, "tags")
        expect(tid(page, f"tag-zeile-{tag}")).to_contain_text("Urlaub")
        tid(page, f"tag-zeile-{tag}").locator("td").first.click()
        expect(tid(page, "tag-summe")).to_contain_text("2 Buchungen")
        expect(page.locator("[data-testid=tag-buchungen] tbody tr")).to_have_count(2)
        assert page.url.endswith(f"/tags?tag={tag}")
        # neues Tag anlegen
        tid(page, "tag-anlegen").click()
        tid(page, "tag-name").fill("Steuer")
        tid(page, "tag-speichern").click()
        expect(tid(page, "tag-liste")).to_contain_text("Steuer")
        # von der Buchung des Tags ins Kontoblatt
        page.locator(f"[data-testid^=tag-buchung-{ids[0]}-konto-]").first.click()
        bereit(page, "konto")
        expect(tid(page, f"buchung-{ids[0]}")).to_have_attribute("aria-selected", "true")
        # Dubletten: zur Buchung springen (D-222)
        page.goto(url + "/dubletten")
        bereit(page, "dubletten")
        page.locator(f"[data-testid^=dublette-buchung-{ids[1]}-konto-]").first.click()
        bereit(page, "konto")
        expect(tid(page, f"buchung-{ids[1]}")).to_have_attribute("aria-selected", "true")


def test_mailblatt_suche_und_zuordnen(tmp_path, browser):
    import httpx
    with server(tmp_path, mail_abgleich=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        assert c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
        assert c.post("/api/mail/abruf").status_code == 200
        mails = c.get("/api/mail/nachrichten", params={"pro_seite": 100, "reihenfolge": "neueste"}).json()
        assert mails["gesamt"] > 2
        ziel = mails["eintraege"][-1]
        wort = ziel["absender"].split("@")[0].split("<")[-1]
        # Suche über die REST-Schnittstelle: jedes Wort muss vorkommen
        treffer = c.get("/api/mail/nachrichten", params={"suche": wort}).json()
        assert 0 < treffer["gesamt"] < mails["gesamt"]
        assert c.get("/api/mail/nachrichten", params={"suche": wort + " gibtsnichtxyz"}).json()["gesamt"] == 0
        buchung = c.get("/api/buchungen", params={"pro_seite": 1, "sortierung": "-datum"}).json()["eintraege"][0]
        page.goto(url + "/mail")
        bereit(page, "mail")
        zeilen = page.locator("[data-testid=mail-tabelle] tbody tr")
        expect(zeilen).to_have_count(min(100, mails["gesamt"]))
        # Datum bricht nicht mitten in der Zahl um
        assert zeilen.first.locator("td.mail-zeit div").first.bounding_box()["height"] < 30
        tid(page, "mail-suche").fill(wort)
        expect(zeilen).to_have_count(min(100, treffer["gesamt"]))
        assert "suche=" in page.url
        tid(page, f"mail-{ziel['id']}").click()
        tid(page, "mail-zuordnen").click()
        expect(tid(page, "mail-zuordnen-dialog")).to_be_visible()
        tid(page, "mail-zuordnen-von").fill("2024-01-01")
        tid(page, "mail-zuordnen-von").dispatch_event("change")
        tid(page, f"mail-zuordnen-buchung-{buchung['id']}").click()
        tid(page, "mail-zuordnen-ok").click()
        expect(tid(page, "mail-zuordnen-dialog")).to_be_hidden()
        expect(tid(page, f"mail-angehaengt-{buchung['id']}")).to_contain_text("Von Hand zugeordnet")
        dann = c.get("/api/mail/nachrichten", params={"suche": wort, "zuordnung": "zugeordnet"}).json()
        assert any(m["id"] == ziel["id"] for m in dann["eintraege"])


def test_mails_derselben_zuordnung_stehen_beieinander(tmp_path, browser):
    import httpx
    with server(tmp_path, mail_abgleich=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        for adresse in ("haushalt.eins@example.invalid", "haushalt.zwei@example.invalid"):
            assert c.post("/api/mail/postfaecher", json={"adresse": adresse}).status_code == 201
        assert c.post("/api/mail/abruf").status_code == 200
        mails = c.get("/api/mail/nachrichten", params={"reihenfolge": "neueste"}).json()["eintraege"]
        assert len(mails) >= 4
        buchung = c.get("/api/buchungen", params={"pro_seite": 1}).json()["eintraege"][0]["id"]
        erste, letzte = mails[0]["id"], mails[-1]["id"]
        for mid in (erste, letzte):
            assert c.post(f"/api/mail/nachrichten/{mid}/buchung", json={"buchung_id": buchung}).status_code == 201
        # ohne den Parameter bleibt die Reihenfolge wie bisher, ohne Feld „gruppe“
        alt = c.get("/api/mail/nachrichten", params={"reihenfolge": "neueste"}).json()["eintraege"]
        assert [m["id"] for m in alt] == [m["id"] for m in mails] and "gruppe" not in alt[0]
        neu = c.get("/api/mail/nachrichten", params={"reihenfolge": "neueste", "gruppieren": "ja"}).json()["eintraege"]
        assert [m["id"] for m in neu][:2] == [erste, letzte]
        assert [m["gruppe"] for m in neu] == [erste, erste] + [None] * (len(mails) - 2)
        assert sorted(m["id"] for m in neu) == sorted(m["id"] for m in mails)
        page.goto(url + "/mail")
        bereit(page, "mail")
        zeilen = page.locator("[data-testid=mail-tabelle] tbody tr")
        expect(zeilen.nth(0)).to_have_attribute("data-gruppe-rolle", "kopf")
        expect(zeilen.nth(0)).to_contain_text("2 Mails zu dieser Zuordnung")
        expect(zeilen.nth(1)).to_have_attribute("data-testid", f"mail-{letzte}")
        expect(zeilen.nth(1)).to_have_attribute("data-gruppe-rolle", "ende")
        expect(zeilen.nth(1)).to_contain_text("gehört dazu")
        expect(zeilen.nth(2)).not_to_have_attribute("data-gruppe", str(erste))


def _mail_mit_bild(bild_url):
    return ("From: Laden <laden@example.invalid>\r\nTo: haushalt.eins@example.invalid\r\nSubject: Ihre Bestellung\r\n"
            "Date: Mon, 03 Jun 2024 10:00:00 +0200\r\nMessage-ID: <bild-1@example.invalid>\r\nMIME-Version: 1.0\r\n"
            "Content-Type: text/html; charset=utf-8\r\n\r\n"
            f'<html><body><p>Danke</p><img id="logo" src="{bild_url}" srcset="{bild_url} 2x" onerror="x()">'
            f'<div style="background:url({bild_url})">Hintergrund</div><script>boese()</script></body></html>\r\n').encode()


def test_mail_bilder_serverseitig(tmp_path):
    from fastapi.testclient import TestClient

    from kontor.app import create_app
    from kontor.config import KontorConfig
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3")))
    giro = c.post("/api/konten", json={"name": "Giro", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Essen", "art": "aufwand"}).json()["id"]
    b = c.post("/api/buchungen", json={"datum": "2024-06-03", "splits": [
        {"konto_id": giro, "betrag": -500}, {"konto_id": kat, "betrag": 500}]}).json()["id"]
    adresse = "https://bilder.example.invalid/logo.png?a=1&b=2"
    dok = c.post("/api/dokumente", params={"buchung_id": [b]},
                 files={"datei": ("mail.eml", _mail_mit_bild(adresse.replace("&", "&amp;")), "message/rfc822")}).json()["id"]
    assert c.get(f"/api/dokumente/{dok}/mail/bilder").json() == {"anzahl": 2}
    ohne = c.get(f"/api/dokumente/{dok}/mail/html")
    assert "bilder.example.invalid" not in ohne.text and "img-src data:;" in ohne.headers["content-security-policy"]
    mit = c.get(f"/api/dokumente/{dok}/mail/html", params={"bilder": "ja"})
    assert "img-src data: https: http:;" in mit.headers["content-security-policy"]
    assert 'src="https://bilder.example.invalid/logo.png?a=1&amp;b=2"' in mit.text
    assert "url(https://bilder.example.invalid/logo.png?a=1&amp;b=2)" in mit.text
    for text in (ohne.text, mit.text):
        assert "srcset" not in text and "onerror" not in text and "boese" not in text
    assert "script-src" not in mit.headers["content-security-policy"] and "default-src 'none'" in mit.headers["content-security-policy"]


def test_mail_bilder_nachladen_im_kontoblatt(tmp_path, browser):
    import httpx
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        b = c.get("/api/buchungen", params={"pro_seite": 1}).json()["eintraege"][0]
        konto = b["splits"][0]["konto_id"]
        # das „fremde“ Bild liegt auf dem eigenen Testserver (nur Loopback)
        dok = c.post("/api/dokumente", params={"buchung_id": [b["id"]]}, files={
            "datei": ("mail.eml", _mail_mit_bild(url + "/oeffentlich/icon-192.png"), "message/rfc822")}).json()["id"]
        page.goto(f"{url}/konten/{konto}?buchung={b['id']}")
        bereit(page, "konto")
        tid(page, f"beleg-marke-{b['id']}").click()
        expect(tid(page, "mail-bilder-leiste")).to_contain_text("2 Bilder von fremden Servern nicht geladen")
        expect(tid(page, "mail-html")).to_have_attribute("data-bilder", "nein")
        expect(page.frame_locator('[data-testid="mail-html"]').locator("#logo")).to_have_count(0)
        tid(page, "mail-bilder-laden").click()
        expect(tid(page, "mail-html")).to_have_attribute("data-bilder", "ja")
        bild = page.frame_locator('[data-testid="mail-html"]').locator("#logo")
        expect(bild).to_be_visible()
        expect(bild).to_have_js_property("complete", True)
        assert bild.evaluate("e => e.naturalWidth") > 0
        expect(tid(page, "mail-bilder-leiste")).to_contain_text("geladen.")


def test_markierte_buchungen_zeigen_summen(tmp_path, browser):
    import httpx
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        konten = {k["name"]: k["id"] for k in c.get("/api/konten").json()}
        giro = konten["Giro"]
        gegen = next(i for n, i in konten.items() if n != "Giro")
        ein = c.post("/api/buchungen", json={"datum": "2024-02-01", "verwendungszweck": "Gutschrift", "splits": [
            {"konto_id": giro, "betrag": 5000}, {"konto_id": gegen, "betrag": -5000}]}).json()["id"]
        page.goto(f"{url}/konten/{giro}")
        bereit(page, "konto")
        expect(tid(page, "auswahl-summen")).to_be_hidden()
        ausgaben = [b for b in c.get("/api/buchungen", params={"konto_id": giro, "pro_seite": 50}).json()["eintraege"]
                    if b["id"] != ein][:2]
        soll_aus = sum(s["betrag"] for b in ausgaben for s in b["splits"] if s["konto_id"] == giro)
        assert soll_aus < 0
        tid(page, f"buchung-{ein}").locator(".zelle-datum").click()
        expect(tid(page, "auswahl-ausgaben")).to_have_attribute("data-betrag", "0")
        expect(tid(page, "auswahl-einnahmen")).to_have_attribute("data-betrag", "5000")
        for b in ausgaben:
            tid(page, f"buchung-{b['id']}").locator(".zelle-datum").click(modifiers=["Control"])
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "3")
        expect(tid(page, "auswahl-ausgaben")).to_have_attribute("data-betrag", str(soll_aus))
        expect(tid(page, "auswahl-einnahmen")).to_have_attribute("data-betrag", "5000")
        expect(tid(page, "auswahl-summe")).to_have_attribute("data-betrag", str(soll_aus + 5000))
        page.keyboard.press("Escape")
        expect(tid(page, "auswahl-summen")).to_be_hidden()


def test_bereichsauswahl_folgt_der_anzeige_bei_gruppierung(tmp_path, browser):
    """D-233: Gruppiert und nach Betrag sortiert wählt Umschalt+Klick die angezeigten Zeilen dazwischen."""
    import httpx
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        konten = {k["name"]: k["id"] for k in c.get("/api/konten").json()}
        giro = konten["Giro"]
        gegen = next(i for n, i in konten.items() if n != "Giro")
        for tag, betrag in (("2024-02-03", -300), ("2024-02-10", -4000), ("2024-03-05", -100), ("2024-03-20", -2500)):
            assert c.post("/api/buchungen", json={"datum": tag, "splits": [
                {"konto_id": giro, "betrag": betrag}, {"konto_id": gegen, "betrag": -betrag}]}).status_code == 201
        page.goto(f"{url}/konten/{giro}?gruppierung=datum&tiefe=monat&sortierung=betrag")
        bereit(page, "konto")
        zeilen = page.locator(".buchungsliste .zeile")
        zeilen.nth(1).locator(".zelle-datum").click()
        zeilen.nth(4).locator(".zelle-datum").click(modifiers=["Shift"])
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "4")
        gewaehlt = page.evaluate("() => [...document.querySelectorAll('.buchungsliste .zeile')]"
                                 ".map((r, i) => r.getAttribute('aria-selected') === 'true' ? i : -1).filter((i) => i >= 0)")
        assert gewaehlt == [1, 2, 3, 4]
        page.keyboard.press("Escape")
        zeilen.nth(1).locator(".zelle-datum").click()
        page.keyboard.press("Shift+ArrowDown")
        page.keyboard.press("Shift+ArrowDown")
        expect(tid(page, "auswahl-anzahl")).to_have_attribute("data-anzahl", "3")


def test_meldung_mit_rueckgaengig_ist_aus_und_einschaltbar(tmp_path, browser):
    """D-234: Nach einer Änderung erscheint keine Meldung mit „Rückgängig“, bis sie eingeschaltet wird."""
    with server(tmp_path) as (url, config), seite(browser, url, erfolgsmeldung=False, **DESKTOP) as page:
        con = sqlite3.connect(config.aktive_datenbank)
        giro, = con.execute("SELECT id FROM konto WHERE name = 'Giro'").fetchone()
        con.close()

        def bestaetigen(nr):
            page.goto(f"{url}/konten/{giro}")
            bereit(page, "konto")
            page.locator(".zeile").nth(nr).click(button="right", position={"x": 20, "y": 8})
            tid(page, "km-bestaetigen").click()
            expect(page.locator(".zeile[data-bestaetigt=Torsten]")).to_have_count(nr + 1)

        bestaetigen(0)
        expect(page.locator('[data-testid="meldung"][data-art="erfolg"]')).to_have_count(0)
        expect(tid(page, "rueckgaengig-knopf")).to_be_enabled()      # Rückgängig bleibt in der Kopfzeile
        page.goto(url + "/einstellungen?bereich=allgemein")
        bereit(page, "einstellungen")
        tid(page, "einstellung-erfolgsmeldung").check()
        bestaetigen(1)
        expect(tid(page, "meldung-rueckgaengig")).to_be_visible()


def test_konfiguration_seite(tmp_path, browser):
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/")
        bereit(page, "uebersicht")
        tid(page, "navlink-konfiguration").click()
        bereit(page, "konfiguration")
        expect(tid(page, "konfiguration-hinweis")).to_contain_text("Entwicklermodus")
        expect(tid(page, "konfiguration-mock_modus")).to_have_attribute("data-geaendert", "ja")
        expect(tid(page, "konfiguration-mock_modus")).to_contain_text("KONTOR_MOCK_MODUS")
        alle = page.locator("[data-testid=konfiguration-wirksam] tbody tr").count()
        tid(page, "konfiguration-nur-geaendert").check()
        geaendert = page.locator("[data-testid=konfiguration-wirksam] tbody tr")
        assert 0 < geaendert.count() < alle
        expect(page.locator("[data-testid=konfiguration-wirksam] tbody tr[data-geaendert=nein]")).to_have_count(0)
