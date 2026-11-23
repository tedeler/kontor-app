"""M8: weitere Seiten – Kategorienbaum, Konten, Einstellungen mit Test-Benachrichtigung (W-005), Import,
Erfassen, Berichte, wiederkehrende Buchungen und Seiten im Mindestumfang (oberflaeche.md 9.8, 13; E-148)."""

from __future__ import annotations

import pytest

from tests.hilfen import m8
from tests.hilfen.m5 import stichtage
from tests.hilfen.m6 import ntfy_felder
from tests.hilfen.m8 import oeffnen, tid
from tests.hilfen.m31 import einstellung_oeffnen
from tests.hilfen.ntfy_attrappe import NtfyAttrappe

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


@pytest.fixture
def daten(starte_server):
    server = starte_server()
    erw, ids = m8.oberflaeche(server)
    return server, erw, ids


# ------------------------------------------------------------------ Kategorienbaum (13.1)
def test_kategorienbaum(daten, neue_seite, geraet):
    server, erw, ids = daten
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    baum = tid(seite, "kategorienbaum")
    expect(baum).to_have_attribute("role", "tree")
    for gruppe, schluessel in (("aufwand", "baum_aufwand"), ("ertrag", "baum_ertrag")):
        expect(baum.get_by_test_id(f"kategorien-gruppe-{gruppe}")).to_be_visible()
        reihen = baum.locator('[data-testid^="kategorie-"][role="treeitem"]').evaluate_all(
            "els => els.map(e => e.getAttribute('data-testid'))")
        erwartet = [f"kategorie-{ids.konto[e]}" for e in erw["m8"][schluessel]]
        assert [r for r in reihen if r in erwartet] == erwartet, (gruppe, reihen)
    wohnen = tid(seite, f"kategorie-{ids.konto[erw['m8']['konten']['wohnen']]}")
    expect(wohnen).to_have_attribute("aria-level", "1")
    expect(wohnen).to_have_attribute("aria-expanded", "true")
    miete = wohnen.locator('[role="group"]').get_by_test_id(f"kategorie-{ids.konto[erw['m8']['konten']['miete']]}")
    expect(miete).to_have_attribute("aria-level", "2")
    lebensmittel = tid(seite, f"kategorie-{ids.konto[erw['m8']['konten']['lebensmittel']]}")
    assert lebensmittel.get_attribute("aria-expanded") is None, "ohne Unterkategorien kein aria-expanded"


def test_kategorie_anlegen(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    oeffnen(seite, server, "/kategorien", seitenname="kategorien")
    tid(seite, "kategorie-anlegen").click()
    tid(seite, "konto-name").fill("Spenden")
    tid(seite, "konto-art").select_option("aufwand")
    tid(seite, "konto-speichern").click()
    neu = m8.warte_bis(lambda: next((k for k in server.api.konten() if k["name"] == "Spenden"), None))
    assert (neu["art"], neu["eltern_id"]) == ("aufwand", None)
    expect(tid(seite, f"kategorie-{neu['id']}")).to_be_visible()


# ------------------------------------------------------------------ Konten (13.3)
def test_konten_anlegen_und_abstimmen(daten, neue_seite):
    from generator.iban import fiktive_iban

    server, erw, ids = daten
    api = server.api
    seite = neue_seite(server)
    oeffnen(seite, server, "/konten", seitenname="konten")
    for k in erw["konten"]:
        if k["art"] in ("girokonto", "sparkonto", "kreditkonto"):
            expect(tid(seite, f"kontenbaum-konto-{ids.konto[k['extern_id']]}")).to_be_attached()
    tid(seite, "konto-anlegen").click()
    tid(seite, "konto-name").fill("Haushaltskasse Giro")
    tid(seite, "konto-art").select_option("girokonto")
    iban = fiktive_iban(8999)
    tid(seite, "konto-iban").fill(iban)
    tid(seite, "konto-speichern").click()
    neu = m8.warte_bis(lambda: next((k for k in api.konten() if k["name"] == "Haushaltskasse Giro"), None))
    assert (neu["art"], neu["iban"]) == ("girokonto", iban)
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    saldo = sum(s["betrag"] for b in api.alle_buchungen(konto_id=giro, bis="2024-06-30")
                for s in b["splits"] if s["konto_id"] == giro)
    tid(seite, f"kontenbaum-abstimmen-{giro}").click()
    d = tid(seite, "abstimmung-dialog")
    tid(seite, "abstimmung-stichtag").fill("2024-06-30")
    tid(seite, "abstimmung-saldo").fill(m8.eingabe_betrag(saldo))
    tid(seite, "abstimmung-speichern").click()
    m8.warte_bis(lambda: api.get("/api/abstimmungen", params={"konto_id": giro}, erwartet=200).daten)
    expect(d).to_be_hidden(timeout=m8.WARTEN_MS)  # fehlt oder unsichtbar; Schließen nach der Antwort (E-205)
    assert all(b["abgestimmt"] for b in api.alle_buchungen(konto_id=giro, bis="2024-06-30"))


# ------------------------------------------------------------------ Einstellungen (13.2) und W-005
def test_einstellungen_test_benachrichtigung_mock(daten, neue_seite):
    server, erw, ids = daten
    seite = neue_seite(server)
    einstellung_oeffnen(seite, server, "status-modus")          # M31: Bereiche (E-291)
    expect(tid(seite, "status-modus")).to_have_attribute("data-modus", "mock")
    einstellung_oeffnen(seite, server, "zustellung-status")
    expect(tid(seite, "zustellung-status")).to_have_attribute("data-plugin", "mock")
    tid(seite, "benachrichtigung-test").click()
    erg = tid(seite, "benachrichtigung-test-ergebnis")
    expect(erg).to_have_attribute("data-zugestellt", "ja")
    expect(erg).to_have_attribute("data-gesendet", "nein")
    assert server.api.get("/api/mock/zustellungen", erwartet=200).daten == []
    assert server.api.get("/api/benachrichtigungen", erwartet=200).daten == []


def test_einstellungen_test_benachrichtigung_ntfy(starte_server, neue_seite, netz_nur_loopback):
    with NtfyAttrappe() as n:
        server = starte_server(**ntfy_felder(n))
        seite = neue_seite(server)
        einstellung_oeffnen(seite, server, "zustellung-status")  # M31 (E-291)
        expect(tid(seite, "zustellung-status")).to_have_attribute("data-plugin", "ntfy")
        tid(seite, "benachrichtigung-test").click()
        erg = tid(seite, "benachrichtigung-test-ergebnis")
        expect(erg).to_have_attribute("data-gesendet", "ja")
        expect(erg).to_have_attribute("data-zugestellt", "ja")
        assert [v.koerper["title"] for v in n.versuche] == ["[Mock] Kontor: Test-Benachrichtigung"]
        n.statusfolge = [500]
        tid(seite, "benachrichtigung-test").click()
        expect(erg).to_have_attribute("data-zugestellt", "nein")
        expect(erg).to_contain_text("500")
        assert len(n.versuche) == 2


def test_einstellungen_ohne_plugin(starte_server, neue_seite):
    server = starte_server(mock=False)
    seite = neue_seite(server)
    einstellung_oeffnen(seite, server, "status-modus")          # M31 (E-291)
    expect(tid(seite, "status-modus")).to_have_attribute("data-modus", "echt")
    einstellung_oeffnen(seite, server, "zustellung-status")
    expect(tid(seite, "zustellung-status")).to_have_attribute("data-plugin", "keins")
    expect(tid(seite, "benachrichtigung-test")).to_be_disabled()


def test_einstellungen_geheimnis_und_sicherung(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    wert = "SYNTH-NTFY-TOKEN-OBERFLAECHE"
    seite = neue_seite(server)
    for name in ("oauth_client_secret", "ntfy_token"):          # M31: je Geheimnis bei seiner Aufgabe (E-291)
        einstellung_oeffnen(seite, server, f"geheimnis-{name}")
        expect(tid(seite, f"geheimnis-{name}")).to_have_attribute("data-gesetzt", "nein")
        expect(tid(seite, f"geheimnis-wert-{name}")).to_have_attribute("type", "password")
    tid(seite, "geheimnis-wert-ntfy_token").fill(wert)
    tid(seite, "geheimnis-speichern-ntfy_token").click()
    expect(tid(seite, "geheimnis-ntfy_token")).to_have_attribute("data-gesetzt", "ja")
    expect(tid(seite, "geheimnis-wert-ntfy_token")).to_have_value("")
    assert [e["name"] for e in api.get("/api/geheimnisse", erwartet=200).daten["eintraege"]] == ["ntfy_token"]
    seite.reload()
    m8.warte_geladen(seite, "einstellungen")
    assert wert not in seite.content()
    expect(tid(seite, "geheimnis-wert-ntfy_token")).to_have_value("")
    tid(seite, "geheimnis-loeschen-ntfy_token").click()
    expect(tid(seite, "geheimnis-ntfy_token")).to_have_attribute("data-gesetzt", "nein")
    einstellung_oeffnen(seite, server, "sicherung-herunterladen")
    expect(tid(seite, "sicherung-herunterladen")).to_have_attribute("href", "/api/sicherung")
    with seite.expect_download() as dl:
        tid(seite, "sicherung-herunterladen").click()
    with open(dl.value.path(), "rb") as f:
        assert f.read(2) == b"PK", "ZIP der Sicherung (sicherung.md)"


# ------------------------------------------------------------------ Import (13.7)
def test_import_ueber_die_oberflaeche(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    erw = m8.lade_erwartung()
    seite = neue_seite(server)
    oeffnen(seite, server, "/import", seitenname="import")
    tid(seite, "import-format").select_option("kmymoney")
    tid(seite, "import-datei").set_input_files(str(m8.OBERFLAECHE))
    a0 = m8.max_aenderung(api)
    tid(seite, "import-starten").click()
    erg = tid(seite, "import-ergebnis")
    expect(erg).to_have_attribute("data-erfolgreich", "ja")
    for feld in ("buchungen_neu", "konten_neu", "kategorien_neu", "empfaenger_neu", "tags_neu", "splits_neu"):
        expect(tid(seite, f"import-zahl-{feld}")).to_have_attribute("data-anzahl", str(erw["ergebnis"][feld]))
    assert len(api.alle_buchungen()) == erw["ergebnis"]["buchungen_neu"]
    assert [a["aktion"] for a in m8.aenderungen_seit(api, a0)] == ["import_kmymoney"]
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.keyboard.press("Control+z")
    m8.warte_bis(lambda: api.alle_buchungen() == [], text="Import rückgängig")


def test_import_fehler(starte_server, neue_seite):
    from tests.hilfen.pfade import KMY

    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/import", seitenname="import")
    tid(seite, "import-format").select_option("kmymoney")
    tid(seite, "import-datei").set_input_files(str(KMY / "kein_xml.kmy"))
    tid(seite, "import-starten").click()
    expect(tid(seite, "import-ergebnis")).to_have_attribute("data-erfolgreich", "nein")
    expect(tid(seite, "import-meldung").first).to_contain_text("import_format_ungueltig")


# ------------------------------------------------------------------ Erfassen (9.8)
def test_buchung_erfassen(daten, neue_seite, geraet):
    server, erw, ids = daten
    api = server.api
    giro = ids.konto[erw["m8"]["konten"]["giro"]]
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, f"/konten/{giro}", seitenname="konto")
    tid(seite, "buchung-erfassen").click()
    d = tid(seite, "erfassen-dialog")
    expect(d).to_be_visible()
    tid(seite, "erfassen-art").select_option("ausgabe")
    tid(seite, "erfassen-datum").fill("2024-12-20")
    tid(seite, "erfassen-betrag").fill("12,34")
    tid(seite, "erfassen-empfaenger").fill("Neuer Laden Äpfel")
    tid(seite, "erfassen-verwendungszweck").fill("Von Hand")
    tid(seite, "erfassen-kategorie").select_option(str(haushalt))
    a0 = m8.max_aenderung(api)
    tid(seite, "erfassen-speichern").click()
    neu = m8.warte_bis(lambda: m8.aenderungen_seit(api, a0))
    assert [a["aktion"] for a in neu] == ["buchung_erfassen"]
    b = next(x for x in api.alle_buchungen(konto_id=giro) if x["verwendungszweck"] == "Von Hand")
    assert b["datum"] == "2024-12-20" and b["empfaenger"]["name"] == "Neuer Laden Äpfel"
    assert sorted((s["konto_id"], s["betrag"]) for s in b["splits"]) == sorted([(giro, -1234), (haushalt, 1234)])
    expect(m8.zeile(seite, b["id"])).to_be_visible()


# ------------------------------------------------------------------ Berichte (13.6)
def test_bericht_kontostand(daten, neue_seite):
    server, erw, ids = daten
    giro_ext = erw["m8"]["konten"]["giro"]
    giro = ids.konto[giro_ext]
    seite = neue_seite(server)
    oeffnen(seite, server, "/berichte", seitenname="berichte")
    tid(seite, "bericht-konten").select_option([str(giro)])
    tid(seite, "bericht-von").fill("2024-01-01")
    tid(seite, "bericht-bis").fill("2024-12-31")
    tid(seite, "bericht-intervall").select_option("monat")
    diagramm = tid(seite, "bericht-diagramm")
    expect(diagramm).to_have_attribute("role", "img")
    assert (diagramm.get_attribute("aria-label") or "").strip()
    giro_splits = [(b["datum"][:10], s["betrag"]) for b in erw["buchungen"] for s in b["splits"]
                   if s["konto_extern_id"] == giro_ext]
    tage = stichtage("2024-01-01", "2024-12-31", "monat")
    assert len(tage) == 13
    for tag in tage:
        soll = sum(betrag for d, betrag in giro_splits if d <= tag)
        zelle = tid(seite, f"bericht-zeile-{tag}").locator(f'[data-konto-id="{giro}"]')
        expect(zelle).to_have_attribute("data-betrag", str(soll))
    assert tid(seite, "export-csv").get_attribute("href").startswith("/api/export/buchungen.csv")
    assert tid(seite, "export-pdf").get_attribute("href").startswith("/api/export/buchungen.pdf")


# ------------------------------------------------------------------ Wiederkehrend (13.5) und Mindestumfang (13.10)
def test_seiten_im_mindestumfang(daten, neue_seite):
    server, erw, ids = daten
    api = server.api
    haushalt = ids.konto[erw["m8"]["konten"]["haushalt"]]
    regel = api.post("/api/regeln", json={"name": "Kino", "kategorie_id": haushalt, "bedingungen": [
        {"feld": "empfaenger", "operator": "enthaelt", "wert": "Kino"}]}, erwartet=201).daten
    pf = api.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}, erwartet=201).daten
    seite = neue_seite(server)
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    for e in api.get("/api/empfaenger", erwartet=200).daten:
        expect(tid(seite, f"empfaenger-{e['id']}")).to_contain_text(e["name"])
    oeffnen(seite, server, "/regeln", seitenname="regeln")
    expect(tid(seite, f"regel-{regel['id']}")).to_contain_text("Kino")
    a0 = m8.max_aenderung(api)
    tid(seite, "regeln-anwenden").click()
    m8.warte_bis(lambda: [a for a in m8.aenderungen_seit(api, a0) if a["aktion"] == "regeln_anwenden"] or
                 tid(seite, "meldungen").locator('[data-testid="meldung"]').count(), text="Regeln angewendet")
    oeffnen(seite, server, "/vorlagen", seitenname="vorlagen")
    expect(tid(seite, "vorlagen-anwenden")).to_be_visible()
    oeffnen(seite, server, "/dubletten", seitenname="dubletten")
    expect(seite.locator('[data-testid^="verdacht-"]')).to_have_count(0)
    oeffnen(seite, server, "/sync", seitenname="sync")
    expect(tid(seite, "sync-status")).to_have_attribute("data-laeuft", "nein")
    oeffnen(seite, server, f"/mail/postfaecher/{pf['id']}", seitenname="postfach")
    expect(seite.locator("h1")).to_have_text("haushalt.eins@example.invalid")
    expect(tid(seite, "postfach-anmelden")).to_be_visible()
    einstellung_oeffnen(seite, server, "postfaecher")            # M31 (E-291)
    expect(tid(seite, "postfaecher").locator(f'a[href="/mail/postfaecher/{pf["id"]}"]')).to_be_visible()


def test_sync_seite_und_benachrichtigungen(starte_server, neue_seite):
    from tests.hilfen.m2 import SYNC_DATEN

    server = starte_server(heute="2024-06-30", mock_daten=SYNC_DATEN, mock_szenario="bankfehler")
    api = server.api
    lauf = api.post("/api/sync", json={}, erwartet=200).daten
    seite = neue_seite(server)
    oeffnen(seite, server, "/sync", seitenname="sync")
    expect(tid(seite, f"lauf-{lauf['id']}")).to_have_attribute("data-status", lauf["status"])
    b = api.get("/api/benachrichtigungen", erwartet=200).daten[0]
    oeffnen(seite, server, "/benachrichtigungen", seitenname="benachrichtigungen")
    expect(tid(seite, f"benachrichtigung-{b['id']}")).to_have_attribute("data-gelesen", "nein")
    expect(tid(seite, "benachrichtigungen-anzahl")).to_have_attribute("data-anzahl", "1")
    tid(seite, f"benachrichtigung-gelesen-{b['id']}").click()
    expect(tid(seite, f"benachrichtigung-{b['id']}")).to_have_attribute("data-gelesen", "ja")
    expect(tid(seite, "benachrichtigungen-anzahl")).to_have_attribute("data-anzahl", "0")
    assert api.get("/api/benachrichtigungen", erwartet=200).daten[0]["gelesen"] is True
