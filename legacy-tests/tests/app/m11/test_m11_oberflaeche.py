"""M11: Oberfläche – Kategorien in der Finanzübersicht (oberflaeche.md 22.1), Buchungsliste einer Kategorie (22.2),
Empfänger zusammenführen (22.3) und Kontostand auf /sync (22.4). Playwright wie M8 (E-139).

Die Daten entstehen über REST mit bekannten Beträgen; Erwartungen werden im Test berechnet.
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.hilfen import m8
from tests.hilfen.m2 import lade_sync
from tests.hilfen.m8 import betrag_text, oeffnen, tid, warte_liste, zeile, zellen_ids
from tests.hilfen.m11 import daten_mit_salden

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


def _daten(api) -> dict:
    """Konten- und Kategorienbaum mit Buchungen; Rückgabe: IDs und erwartete Salden."""
    k = {
        "giro": api.konto("Girokonto", "girokonto")["id"],
        "wohnen": api.konto("Wohnen", "aufwand")["id"],
        "essen": api.konto("Lebensmittel", "aufwand")["id"],
        "gehalt": api.konto("Gehalt", "ertrag")["id"],
        "sonst": api.konto("Eröffnung", "eigenkapital")["id"],
    }
    k["unter"] = api.konto("Rücklage", "girokonto", eltern_id=k["giro"])["id"]
    k["miete"] = api.konto("Miete", "aufwand", eltern_id=k["wohnen"])["id"]
    k["strom"] = api.konto("Strom", "aufwand", eltern_id=k["wohnen"])["id"]
    k["alt"] = api.konto("Alte Kategorie", "aufwand")["id"]
    api.patch(f"/api/konten/{k['alt']}", json={"geschlossen": True}, erwartet=200)
    b = {
        "start": api.buchung("2024-01-01", [(k["giro"], 300000), (k["sonst"], -300000)])["id"],
        "gehalt": api.buchung("2024-01-31", [(k["giro"], 250000), (k["gehalt"], -250000)])["id"],
        "wohnen": api.buchung("2024-02-01", [(k["giro"], -1500), (k["wohnen"], 1500)])["id"],
        "miete": api.buchung("2024-02-02", [(k["giro"], -90000), (k["miete"], 90000)])["id"],
        "strom": api.buchung("2024-02-03", [(k["unter"], -7000), (k["strom"], 7000)])["id"],
        "erstattung": api.buchung("2024-02-04", [(k["giro"], 2000), (k["strom"], -2000)])["id"],
        "essen": api.buchung("2024-02-05", [(k["giro"], -4500), (k["essen"], 4500)])["id"],
        "split": api.buchung("2024-02-06", [(k["giro"], -1000), (k["unter"], -500), (k["miete"], 1500)])["id"],
    }
    return {"k": k, "b": b}


def _saldo_gesamt(api, kid) -> int:
    u = api.get("/api/kontenuebersicht", erwartet=200).daten
    return next(x["saldo_gesamt"] for x in u["konten"] if x["konto_id"] == kid)


def _rest_ids(api, **params) -> list[int]:
    d = api.get("/api/buchungen", params={"pro_seite": 200, "sortierung": "-datum", **params}, erwartet=200).daten
    return [e["id"] for e in d["eintraege"]]


def _abfrage(seite) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(seite.url).query).items()}


# ------------------------------------------------------------------ 22.1 Finanzübersicht


@pytest.mark.kern
def test_uebersicht_kategorien_einklappbar(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    d = _daten(api)
    k = d["k"]
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    # Bestandskonten unverändert, keine Kategorie in der Tabelle
    tabelle = tid(seite, "uebersicht-tabelle")
    expect(tabelle.get_by_test_id(f"uebersicht-konto-{k['giro']}")).to_have_count(1)
    expect(tabelle.locator('[data-testid^="uebersicht-kategorie-"]')).to_have_count(0)
    bereich = tid(seite, "uebersicht-kategorien")
    knopf = tid(seite, "uebersicht-kategorien-umschalten")
    expect(bereich).to_be_visible()
    expect(knopf).to_have_attribute("aria-expanded", "false")
    expect(tid(seite, f"uebersicht-kategorie-{k['wohnen']}")).to_be_hidden()
    knopf.click()
    expect(knopf).to_have_attribute("aria-expanded", "true")
    # Gruppen in Reihenfolge, Zeilen mit Rohwert und angezeigtem Wert
    gruppen = bereich.locator('[data-testid^="uebersicht-gruppe-"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid'))")
    assert gruppen == ["uebersicht-gruppe-aufwand", "uebersicht-gruppe-ertrag", "uebersicht-gruppe-eigenkapital"]
    for name, art in (("wohnen", "aufwand"), ("miete", "aufwand"), ("strom", "aufwand"), ("essen", "aufwand"),
                      ("gehalt", "ertrag"), ("sonst", "eigenkapital")):
        z = tid(seite, f"uebersicht-kategorie-{k[name]}")
        expect(z).to_be_visible()
        roh = _saldo_gesamt(api, k[name])
        s = z.locator('[data-feld="saldo"]')
        expect(s).to_have_attribute("data-betrag", str(roh))
        expect(s).to_have_text(betrag_text(roh if art == "aufwand" else -roh))
        expect(tid(seite, f"uebersicht-gruppe-{art}").get_by_test_id(f"uebersicht-kategorie-{k[name]}")).to_have_count(1)
    assert _saldo_gesamt(api, k["wohnen"]) == 1500 + 90000 + 1500 + 7000 - 2000
    expect(tid(seite, f"uebersicht-kategorie-{k['miete']}")).to_have_attribute("aria-level", "2")
    expect(tid(seite, f"uebersicht-kategorie-{k['wohnen']}")).to_have_attribute("aria-level", "1")
    expect(tid(seite, "uebersicht-summe-aufwand")).to_have_attribute("data-betrag", str(1500 + 90000 + 1500 + 7000
                                                                                         - 2000 + 4500))
    expect(tid(seite, "uebersicht-summe-ertrag")).to_have_attribute("data-betrag", "-250000")
    expect(tid(seite, "uebersicht-summe-ertrag")).to_have_text(betrag_text(250000))
    # geschlossene Kategorie nur mit dem Kontrollkästchen
    expect(tid(seite, f"uebersicht-kategorie-{k['alt']}")).to_be_hidden()
    tid(seite, "uebersicht-geschlossene").check()
    expect(tid(seite, f"uebersicht-kategorie-{k['alt']}")).to_have_attribute("data-geschlossen", "ja")
    # Zustand bleibt nach dem Neuladen
    seite.reload()
    m8.warte_geladen(seite, "uebersicht")
    expect(tid(seite, "uebersicht-kategorien-umschalten")).to_have_attribute("aria-expanded", "true")
    tid(seite, "uebersicht-kategorien-umschalten").click()
    expect(tid(seite, f"uebersicht-kategorie-{k['wohnen']}")).to_be_hidden()
    seite.reload()
    m8.warte_geladen(seite, "uebersicht")
    expect(tid(seite, "uebersicht-kategorien-umschalten")).to_have_attribute("aria-expanded", "false")
    # Klick öffnet die Kategorie
    tid(seite, "uebersicht-kategorien-umschalten").click()
    tid(seite, f"uebersicht-kategorie-{k['essen']}").locator('[data-feld="name"]').click()
    m8.warte_geladen(seite, "konto")
    assert seite.url == f"{server.url}/konten/{k['essen']}"


# ------------------------------------------------------------------ 22.2 Buchungsliste einer Kategorie


@pytest.mark.kern
def test_kategorie_buchungsliste(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    d = _daten(api)
    k, b = d["k"], d["b"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{k['wohnen']}", seitenname="konto")
    expect(tid(seite, "seite-konto")).to_have_attribute("data-kontoklasse", "aufwand")
    warte_liste(seite, _rest_ids(api, konto_id=k["wohnen"]))
    # Spalte Konto
    z = zeile(seite, b["wohnen"]).locator('[data-feld="konto"]')
    expect(z).to_have_attribute("data-konto-id", str(k["giro"]))
    expect(z).to_have_text("Girokonto")
    # Unterkonten einschließen
    m8.filter_aufklappen(seite)   # ab M12 anfangs eingeklappt (E-174)
    tid(seite, "filter-unterkonten").check()
    mit = _rest_ids(api, konto_id=k["wohnen"], unterkonten="true")
    assert set(mit) == {b["wohnen"], b["miete"], b["strom"], b["erstattung"], b["split"]}
    warte_liste(seite, mit)
    assert _abfrage(seite).get("unterkonten") == "true"
    zelle = zeile(seite, b["strom"]).locator('[data-feld="konto"]')
    expect(zelle).to_have_attribute("data-konto-id", str(k["unter"]))
    expect(zelle).to_have_text("Girokonto › Rücklage")
    expect(zeile(seite, b["split"]).locator('[data-feld="konto"]')).to_have_text("Mehrere")
    expect(zeile(seite, b["split"]).locator('[data-feld="konto"]')).to_have_attribute("data-konto-id", "")
    expect(zeile(seite, b["erstattung"]).locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", "-2000")
    expect(tid(seite, "buchungsliste-summe")).to_have_attribute("data-betrag", str(1500 + 90000 + 7000 - 2000 + 1500))
    # Filter Konto (Bestandskonto) → kategorie_id
    expect(tid(seite, "filter-kategorie")).to_have_count(0)
    tid(seite, "filter-konto").select_option(str(k["unter"]))
    warte_liste(seite, _rest_ids(api, konto_id=k["wohnen"], unterkonten="true", kategorie_id=k["unter"]))
    assert _abfrage(seite) == {"unterkonten": "true", "kategorie_id": str(k["unter"])}
    # direkter Aufruf mit Abfrage setzt die Felder
    oeffnen(seite, server, f"/konten/{k['wohnen']}?unterkonten=true", seitenname="konto")
    expect(tid(seite, "filter-unterkonten")).to_be_checked()
    warte_liste(seite, mit)
    # Mehrfachauswahl und Umkategorisieren: die Buchung verschwindet aus der Liste
    zeile(seite, b["wohnen"]).click()
    tid(seite, "mehrfach-kategorie").click()
    tid(seite, f"kategorie-option-{k['essen']}").click()
    m8.warte_bis(lambda: api.buchung_lesen(b["wohnen"])["kategorie_id"] == k["essen"], text="umkategorisiert")
    warte_liste(seite, _rest_ids(api, konto_id=k["wohnen"], unterkonten="true"))
    assert b["wohnen"] not in zellen_ids(seite)


@pytest.mark.kern
def test_bestandskonto_klasse_und_unterkonten(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    d = _daten(api)
    k, b = d["k"], d["b"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{k['giro']}", seitenname="konto")
    expect(tid(seite, "seite-konto")).to_have_attribute("data-kontoklasse", "bestand")
    expect(seite.locator('[data-testid="buchungsliste"] [data-feld="konto"]')).to_have_count(0)
    expect(tid(seite, "filter-konto")).to_have_count(0)
    warte_liste(seite, _rest_ids(api, konto_id=k["giro"]))
    assert b["strom"] not in zellen_ids(seite)
    m8.filter_aufklappen(seite)   # ab M12 anfangs eingeklappt (E-174)
    tid(seite, "filter-unterkonten").check()
    warte_liste(seite, _rest_ids(api, konto_id=k["giro"], unterkonten="true"))
    assert b["strom"] in zellen_ids(seite)
    expect(zeile(seite, b["split"]).locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", "-1500")


def test_kategorie_buchungsliste_mobil_und_technisches_konto(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    d = _daten(api)
    k, b = d["k"], d["b"]
    seite = neue_seite(server, "handy")
    oeffnen(seite, server, f"/konten/{k['sonst']}", seitenname="konto")
    expect(tid(seite, "seite-konto")).to_have_attribute("data-kontoklasse", "eigenkapital")
    warte_liste(seite, [b["start"]])
    expect(zeile(seite, b["start"]).locator('[data-feld="betrag"]')).to_have_attribute("data-betrag", "-300000")


# ------------------------------------------------------------------ 22.3 Empfänger zusammenführen


def _empfaenger_daten(api):
    giro = api.konto("Girokonto", "girokonto")["id"]
    kat = api.konto("Lebensmittel", "aufwand")["id"]
    e = {n: api.post("/api/empfaenger", json={"name": n, "aliase": a}, erwartet=201).daten["id"]
         for n, a in (("REWE Markt 1234", ["Rewe 1234"]), ("REWE MARKT GMBH", []), ("Rewe Filiale", []),
                      ("Bäckerei", []))}
    anzahl = {"REWE Markt 1234": 1, "REWE MARKT GMBH": 3, "Rewe Filiale": 2, "Bäckerei": 1}
    tag = 1
    for n, x in anzahl.items():
        for _ in range(x):
            api.buchung(f"2024-03-{tag:02d}", [(giro, -100), (kat, 100)], empfaenger_id=e[n])
            tag += 1
    return e


@pytest.mark.kern
def test_empfaenger_zusammenfuehren(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    e = _empfaenger_daten(api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    knopf = tid(seite, "empfaenger-zusammenfuehren")
    expect(knopf).to_be_disabled()
    tid(seite, f"empfaenger-auswahl-{e['REWE Markt 1234']}").check()
    expect(knopf).to_be_disabled()
    tid(seite, f"empfaenger-auswahl-{e['REWE MARKT GMBH']}").check()
    tid(seite, f"empfaenger-auswahl-{e['Rewe Filiale']}").check()
    expect(knopf).to_be_enabled()
    knopf.click()
    dlg = tid(seite, "zusammenfuehren-dialog")
    expect(dlg).to_be_visible()
    expect(tid(seite, "zusammenfuehren-ziel")).to_have_value(str(e["REWE MARKT GMBH"]), timeout=m8.WARTEN_MS)
    expect(tid(seite, "zusammenfuehren-name")).to_have_value("REWE MARKT GMBH")
    tid(seite, "zusammenfuehren-name").fill("REWE")
    for text in ("REWE Markt 1234", "Rewe 1234", "REWE MARKT GMBH", "Rewe Filiale"):
        expect(tid(seite, "zusammenfuehren-aliase")).to_contain_text(text)
    # Fehler: Name eines dritten Empfängers → Meldung im Dialog, nichts geändert
    tid(seite, "zusammenfuehren-name").fill("Bäckerei")
    tid(seite, "zusammenfuehren-ausfuehren").click()
    expect(dlg).to_be_visible()
    expect(dlg.get_by_role("alert")).to_be_visible()
    assert len(api.get("/api/empfaenger", erwartet=200).daten) == 4
    tid(seite, "zusammenfuehren-name").fill("REWE")
    tid(seite, "zusammenfuehren-ausfuehren").click()
    expect(dlg).to_have_count(0)
    rest = {x["name"]: x for x in api.get("/api/empfaenger", erwartet=200).daten}
    assert set(rest) == {"REWE", "Bäckerei"}
    z = rest["REWE"]
    assert z["id"] == e["REWE MARKT GMBH"]
    assert z["aliase"] == sorted(["REWE MARKT GMBH", "REWE Markt 1234", "Rewe 1234", "Rewe Filiale"])
    expect(tid(seite, f"empfaenger-{z['id']}")).to_contain_text("REWE")
    for n in ("REWE Markt 1234", "Rewe Filiale"):
        expect(tid(seite, f"empfaenger-{e[n]}")).to_have_count(0)
    alle = api.alle_buchungen()
    assert sum(1 for x in alle if x["empfaenger"] and x["empfaenger"]["id"] == z["id"]) == 6


# ------------------------------------------------------------------ 22.4 Kontostand auf /sync


def test_sync_seite_zeigt_saldoabgleich(starte_server, neue_seite, tmp_path):
    _, erw = lade_sync()
    giro = erw["ibans"]["giro"]
    server = starte_server(mock_daten=daten_mit_salden(tmp_path, {giro: 4711}), heute="2024-06-30")
    api = server.api
    lauf = api.post("/api/sync", json={}, erwartet=200).daten
    sk = next(x for x in lauf["konten"] if x["iban"] == giro)
    assert sk["saldo_abgleich"]["status"] == "ausgeglichen"
    seite = neue_seite(server)
    oeffnen(seite, server, "/sync", seitenname="sync")
    s = tid(seite, f"bankkonto-{giro}").get_by_test_id("bankkonto-saldo")
    expect(s).to_have_attribute("data-status", "ausgeglichen")
    expect(s).to_contain_text(betrag_text(sk["saldo_abgleich"]["differenz"]))
    link = tid(seite, f"bankkonto-ausgleich-{giro}")
    expect(link).to_have_attribute("href", f"/konten/{sk['konto_id']}")
    andere = next(x for x in lauf["konten"] if x["iban"] != giro)
    expect(tid(seite, f"bankkonto-{andere['iban']}").get_by_test_id("bankkonto-saldo")).to_have_attribute(
        "data-status", "nicht_verfuegbar")
    assert dt.date.fromisoformat(sk["saldo_abgleich"]["stichtag"]) == dt.date(2024, 6, 30)
