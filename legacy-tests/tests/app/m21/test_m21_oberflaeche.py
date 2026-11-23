"""M21: Einzelbuchungen in den Berichtstabellen, Tabelle folgt dem Zoom, Themen, Sprungziel mittig
(oberflaeche.md 31, E-221, E-222). Nur Browsertests (Playwright wie M8), nicht kern.

Erwartungen werden aus den im Test angelegten Buchungen und den Stichtagen bzw. Zeiträumen der Berichts-API
berechnet (``berichte.md`` 2, 3).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.hilfen import m8, m17
from tests.hilfen.m8 import ausgewaehlt, oeffnen, tid, warte_bis, warte_liste, zeile
from tests.hilfen.m15 import text_normal
from tests.hilfen.m21 import BIS, JS_LAGE, VON, berichtsdaten, de, viele

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

BESTAND = ("girokonto", "sparkonto", "kreditkonto")


def _bericht(starte_server, neue_seite, geraet="desktop", **kw):
    server = starte_server()
    d = berichtsdaten(server.api)
    seite = neue_seite(server, geraet, **kw)
    anfragen: list[str] = []
    seite.on("request", lambda r: anfragen.append(r.url) if urlsplit(r.url).path == "/api/buchungen" else None)
    oeffnen(seite, server, "/berichte", seitenname="berichte")
    tid(seite, "bericht-von").fill(VON)
    tid(seite, "bericht-bis").fill(BIS)
    tid(seite, "bericht-intervall").select_option("monat")
    tid(seite, "bericht-konten").select_option([str(d["k"]["giro"]), str(d["k"]["spar"])])
    expect(tid(seite, "bericht-diagramm")).to_have_attribute("data-reihen", "2")
    return server, server.api, seite, d, anfragen


def _stichtage(api, d) -> list[str]:
    return api.get("/api/berichte/kontostand", params=[("konto_id", d["k"]["giro"]), ("konto_id", d["k"]["spar"]),
                                                       ("von", VON), ("bis", BIS), ("intervall", "monat")],
                   erwartet=200).daten["stichtage"]


def _datenzeilen(tabelle):
    """Datenzeilen der Berichtstabelle selbst (nicht der eingebetteten Tabellen der Detailzeilen)."""
    return tabelle.locator(":scope > tbody > tr:not([data-testid*='details'])")


def _ids(detail, praefix="bericht-") -> list[int]:
    return [int(x) for x in detail.locator(f'[data-testid^="{praefix}buchung-"][data-id]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-id'))")]


def _soll(api, d, von: str | None, bis: str, *, ohne_umbuchung=False) -> list[dict]:
    sel = {d["k"]["giro"], d["k"]["spar"]}
    aus = []
    for b in api.alle_buchungen():
        if not any(s["konto_id"] in sel for s in b["splits"]):
            continue
        if (von is not None and b["datum"] < von) or b["datum"] > bis:
            continue
        if ohne_umbuchung and b["ist_umbuchung"]:
            continue
        aus.append(b)
    return sorted(aus, key=lambda b: (b["datum"], b["id"]))


def _vorher_tag(iso: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(iso) + dt.timedelta(days=1)).isoformat()


# ------------------------------------------------------------------ Kontostand (31.1)


def test_kontostand_einzelbuchungen(starte_server, neue_seite):
    server, api, seite, d, anfragen = _bericht(starte_server, neue_seite)
    tage = _stichtage(api, d)
    tabelle = tid(seite, "bericht-tabelle")
    zeilen = _datenzeilen(tabelle)
    expect(zeilen).to_have_count(len(tage))
    anzahl_vorher = tabelle.locator(":scope > tbody > tr").count()
    assert seite.locator('[data-testid^="bericht-details-"]').count() == 0, "Detailzeile erst beim Aufklappen"
    gesel = {d["k"]["giro"], d["k"]["spar"]}
    for i, tag in enumerate(tage):
        knopf = tid(seite, f"bericht-aufklappen-{i}")
        assert knopf.evaluate("e => e.tagName") == "BUTTON" and knopf.get_attribute("type") == "button"
        assert knopf.text_content() == "", "kein Textinhalt (Symbol nur über CSS)"
        assert knopf.evaluate("(e, z) => z.querySelector('td, th').contains(e)", zeilen.nth(i).element_handle())
        expect(knopf).to_have_attribute("aria-expanded", "false")
        expect(knopf).to_have_attribute("aria-label", "Einzelbuchungen zeigen")
    assert tabelle.locator(":scope > tbody > tr").count() == anzahl_vorher
    anfragen.clear()
    for i, tag in enumerate(tage):
        tid(seite, f"bericht-aufklappen-{i}").click()
        detail = tid(seite, f"bericht-details-{i}")
        expect(detail).to_be_visible()
        expect(tid(seite, f"bericht-aufklappen-{i}")).to_have_attribute("aria-expanded", "true")
        expect(tid(seite, f"bericht-aufklappen-{i}")).to_have_attribute("aria-label", "Einzelbuchungen ausblenden")
        expect(zeilen.nth(i)).to_have_attribute("data-offen", "ja")
        assert zeilen.nth(i).evaluate("z => z.nextElementSibling.dataset.testid") == f"bericht-details-{i}"
        spalten = zeilen.nth(i).evaluate("z => [...z.cells].reduce((n, c) => n + c.colSpan, 0)")
        assert detail.evaluate("d => d.cells.length") == 1 and detail.evaluate("d => d.cells[0].colSpan") == spalten
        von = None if i == 0 else _vorher_tag(tage[i - 1])
        soll = _soll(api, d, tag if i == 0 else von, tag)
        if not soll:
            expect(detail.locator(".leer")).to_have_text("Keine Buchungen in diesem Zeitraum.")
            continue
        warte_bis(lambda: _ids(detail) == [b["id"] for b in soll], text=f"Buchungen Zeile {i}")
        for b in soll:
            z = tid(seite, f"bericht-buchung-{b['id']}")
            betrag = sum(s["betrag"] for s in b["splits"] if s["konto_id"] in gesel)
            assert z.locator("[data-betrag]").first.get_attribute("data-betrag") == str(betrag)
            assert ((b["empfaenger"] or {}).get("name") or "–") in text_normal(z.text_content())
            konten = list(dict.fromkeys(s["konto_id"] for s in b["splits"]))
            links = [int(x) for x in z.locator(f'[data-testid^="bericht-buchung-{b["id"]}-konto-"]').evaluate_all(
                "els => els.map(e => e.dataset.testid.split('-konto-')[1])")]
            assert set(links) == set(konten)
            assert all(links.index(a) < links.index(c) for a in links for c in links
                       if a in gesel and c not in gesel), "gewählte Konten zuerst"
            for kid in konten:
                expect(tid(seite, f"bericht-buchung-{b['id']}-konto-{kid}")).to_have_attribute(
                    "href", f"/konten/{kid}?buchung={b['id']}")
    # Abfragen: je gewähltem Konto mit von, bis, sortierung=datum, pro_seite=500
    q = [parse_qs(urlsplit(u).query) for u in anfragen]
    assert q and all(x.get("sortierung") == ["datum"] and x.get("pro_seite") == ["500"] and "von" in x and "bis" in x
                     for x in q)
    assert {x["konto_id"][0] for x in q} == {str(d["k"]["giro"]), str(d["k"]["spar"])}
    # Zuklappen und wieder aufklappen ohne neue Zeile
    tid(seite, "bericht-aufklappen-1").click()
    expect(tid(seite, "bericht-details-1")).to_be_hidden()
    expect(zeilen.nth(1)).to_have_attribute("data-offen", "nein")
    tid(seite, "bericht-aufklappen-1").click()
    expect(tid(seite, "bericht-details-1")).to_be_visible()
    assert seite.locator('[data-testid="bericht-details-1"]').count() == 1


def test_einnahmen_ausgaben_ohne_umbuchungen(starte_server, neue_seite):
    server, api, seite, d, _ = _bericht(starte_server, neue_seite)
    seite.get_by_role("button", name=re.compile("berechnen", re.I)).first.click()
    expect(tid(seite, "bericht-ea-diagramm")).to_be_visible()
    knopf = tid(seite, "bericht-ea-aufklappen-0")
    expect(knopf).to_have_attribute("aria-expanded", "false")
    assert knopf.text_content() == ""
    perioden = api.get("/api/berichte/einnahmen-ausgaben", params=[
        ("konto_id", d["k"]["giro"]), ("konto_id", d["k"]["spar"]), ("von", VON), ("bis", BIS),
        ("intervall", "monat")], erwartet=200).daten["perioden"]
    for i, p in enumerate(perioden):
        tid(seite, f"bericht-ea-aufklappen-{i}").click()
        detail = tid(seite, f"bericht-ea-details-{i}")
        expect(detail).to_be_visible()
        soll = _soll(api, d, p["von"], p["bis"], ohne_umbuchung=True)
        if soll:
            warte_bis(lambda: _ids(detail, "bericht-ea-") == [b["id"] for b in soll], text=f"EA-Zeile {i}")
        else:
            expect(detail.locator(".leer")).to_have_text("Keine Buchungen in diesem Zeitraum.")
    assert d["b"]["b3"] not in _ids(seite.locator("body"), "bericht-ea-"), "ohne Umbuchungen"


def test_link_springt_wie_gegenbuchung(starte_server, neue_seite):
    server, api, seite, d, _ = _bericht(starte_server, neue_seite)
    tid(seite, "bericht-aufklappen-1").click()
    link = tid(seite, f"bericht-buchung-{d['b']['b2']}-konto-{d['k']['giro']}")
    expect(link).to_be_visible()
    link.click()
    m17.warte_konto(seite, d["k"]["giro"])
    warte_bis(lambda: ausgewaehlt(seite) == {d["b"]["b2"]}, text="Buchung gewählt")
    assert m17.fokuszeile(seite) == d["b"]["b2"]
    expect(zeile(seite, d["b"]["b2"])).to_be_in_viewport()


# ------------------------------------------------------------------ Zoom (31.2)


def test_tabelle_folgt_dem_zoom(starte_server, neue_seite):
    server, api, seite, d, _ = _bericht(starte_server, neue_seite)
    diagramm = tid(seite, "bericht-diagramm")
    expect(diagramm).to_have_class(re.compile(r"\bjs-plotly-plot\b"))
    tage = _stichtage(api, d)
    zeilen = _datenzeilen(tid(seite, "bericht-tabelle"))
    hinweis = tid(seite, "bericht-zoom-hinweis")
    expect(hinweis).to_be_hidden()
    tid(seite, "bericht-aufklappen-0").click()
    expect(tid(seite, "bericht-details-0")).to_be_visible()
    a, b = "2024-01-20", "2024-03-15"
    diagramm.evaluate("(el, r) => window.Plotly.relayout(el, {'xaxis.range': r})", [a, b])
    drin = [t for t in tage if a <= t <= b]
    for i, t in enumerate(tage):
        if t in drin:
            expect(zeilen.nth(i)).to_be_visible()
        else:
            expect(zeilen.nth(i)).to_be_hidden()
    expect(tid(seite, "bericht-details-0")).to_be_hidden()
    expect(hinweis).to_have_text(
        f"Tabelle zeigt den Ausschnitt {de(a)} – {de(b)} ({len(drin)} von {len(tage)} Zeilen). "
        "Doppelklick ins Diagramm zeigt wieder alles.")
    assert zeilen.count() == len(tage), "Zeilen bleiben im Dokument"
    diagramm.evaluate("el => window.Plotly.relayout(el, {'xaxis.autorange': true})")
    for i in range(len(tage)):
        expect(zeilen.nth(i)).to_be_visible()
    expect(hinweis).to_be_hidden()


@pytest.mark.parametrize("schema", ["light", "dark"])
def test_diagramme_in_beiden_themen_ohne_fehler(starte_server, neue_seite, schema):
    """31.3: nur, dass die Diagramme ohne Fehler der Seite zeichnen (die Fixture prüft pageerror)."""
    server, api, seite, d, _ = _bericht(starte_server, neue_seite, color_scheme=schema)
    expect(tid(seite, "bericht-diagramm")).to_have_class(re.compile(r"\bjs-plotly-plot\b"))
    seite.get_by_role("button", name=re.compile("berechnen", re.I)).first.click()
    expect(tid(seite, "bericht-ea-diagramm")).to_be_visible()
    tid(seite, "bericht-diagramm").hover()


# ------------------------------------------------------------------ Sprungziel mittig (31.4)


def _mitte(seite, bid):
    lage = warte_bis(lambda: (x := seite.evaluate(JS_LAGE, bid)) and x["abstand"] <= x["zeile"] and x,
                     text=f"Buchung {bid} mittig")
    return lage


@pytest.mark.parametrize("geraet", ["desktop", "handy"])
def test_sprung_ueber_adresse_mittig(starte_server, neue_seite, geraet):
    server = starte_server()
    api = server.api
    g = api.konto("Girokonto")["id"]
    leb = api.konto("Lebensmittel", "aufwand")["id"]
    ids = viele(api, g, leb)
    ziel = ids[250]
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, f"/konten/{g}?buchung={ziel}", seitenname="konto")
    warte_bis(lambda: ausgewaehlt(seite) == {ziel}, text="Ziel gewählt")
    assert m17.fokuszeile(seite) == ziel
    lage = _mitte(seite, ziel)
    assert lage["links"] == 0, "waagerechte Scrollposition unverändert"
    if geraet == "handy":
        expect(tid(seite, "app")).to_have_attribute("data-layout", "mobil")
        leiste = tid(seite, "mehrfach-leiste")
        if leiste.is_visible():
            assert lage["unten"] <= leiste.bounding_box()["y"] + 1, "nicht unter der Mehrfachleiste"


def test_gegenbuchung_springt_mittig(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g = api.konto("Girokonto")["id"]
    s = api.konto("Tagesgeld", "sparkonto")["id"]
    leb = api.konto("Lebensmittel", "aufwand")["id"]
    ids = viele(api, g, leb, 260)
    umb = api.buchung("2023-02-01", [(g, -777), (s, 777)], verwendungszweck="Umbuchung alt")["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{s}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, s))
    zeile(seite, umb).click(button="right")
    tid(seite, "kontextmenue").get_by_test_id("km-gegenbuchung").click()
    m17.warte_konto(seite, g)
    warte_bis(lambda: ausgewaehlt(seite) == {umb}, text="Gegenbuchung gewählt")
    _mitte(seite, umb)
    assert ids
