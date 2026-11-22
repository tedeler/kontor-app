"""Browser-Rauchtest des Features „kopfabruf“ (D-243): Mails nur mit Kopfzeilen laden ihren Inhalt beim Lesen."""

from __future__ import annotations

import httpx
import pytest

from .test_browser import DESKTOP, bereit, browser, seite, server, tid  # noqa: F401 (Fixture)

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect


def test_mail_ohne_inhalt_wird_beim_lesen_geladen(tmp_path, browser):
    with server(tmp_path, mail_nur_koepfe=True) as (url, _), seite(browser, url, **DESKTOP) as page:
        c = httpx.Client(base_url=url, trust_env=False, timeout=60)
        assert c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
        erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
        assert erg["nachrichten_ohne_inhalt"] > 0, erg
        mails = c.get("/api/mail/nachrichten", params={"pro_seite": 500}).json()["eintraege"]
        ziel = next(m for m in mails if m.get("ohne_inhalt"))
        assert ziel["text"] == ""
        page.goto(url + f"/mail?id={ziel['id']}")
        bereit(page, "mail")
        expect(tid(page, "mail-text")).not_to_have_attribute("data-inhalt", "laedt")
        expect(tid(page, "mail-text")).not_to_be_empty()
        neu = next(m for m in c.get("/api/mail/nachrichten", params={"pro_seite": 500}).json()["eintraege"]
                   if m["id"] == ziel["id"])
        assert "ohne_inhalt" not in neu and neu["text"]
