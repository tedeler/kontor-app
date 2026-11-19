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
        # Bestätigen setzt das Tag „B-Torsten“ (D-223)
        zeile = page.locator(".zeile").first
        zeile.click(button="right", position={"x": 20, "y": 8})
        tid(page, "km-bestaetigen").click()
        expect(page.locator(".zeile[data-bestaetigt=Torsten] .tag-person").first).to_have_text("B-Torsten")


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
    assert sorted(t["name"] for t in c.get("/api/tags").json()) == ["B-Tina", "B-Torsten"]


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
