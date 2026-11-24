"""M28: Mail-Blatt, Statistik, Empfänger markieren und bestätigen, Split-Dialog und Vorlagen, Dubletten, leere Werte
(oberflaeche.md 37.10, 37.12; E-252, E-255). Browsertests, nicht kern."""

from __future__ import annotations

import pytest

from tests.hilfen import m8, m28
from tests.hilfen.m6 import EINS, abruf, postfach
from tests.hilfen.m8 import ausgewaehlt, oeffnen, strg, tid, warte_bis, warte_geladen, warte_liste, zeile
from tests.hilfen.m17 import warte
from tests.hilfen.m20 import NR, amazon_bestellung, mock_datei, nachricht

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect


# ------------------------------------------------------------------ 37.12.1 Mail-Blatt


@pytest.fixture
def mailwelt(starte_server, tmp_path):
    m = [amazon_bestellung(empfangen="2024-12-01T08:00:00Z"),
         nachricht("Verein <info@verein.example.invalid>", "", "Hallo Verein", "2024-12-02T08:00:00Z"),
         amazon_bestellung("303-7654321-1234567", empfangen="2024-12-03T08:00:00Z")]
    datei = mock_datei(tmp_path / "mails.json", m)
    server = starte_server(mock_daten=datei, mail_erstabruf_tage=365, mail_abgleich=True)
    api = server.api
    g = api.konto("Girokonto")["id"]
    leb = api.konto("Einkauf", "aufwand")["id"]
    bid = api.buchung("2024-12-02", [(g, -4990), (leb, 4990)], verwendungszweck=f"Amazon {NR}")["id"]
    pf = postfach(api, EINS)["id"]
    abruf(api)
    erw = {x["kennung"]: x for x in api.get("/api/erwartungen", params=[("zustand", "offen"), ("zustand", "erfuellt")],
                                            erwartet=200).daten["eintraege"]}
    if bid not in erw[NR]["buchung_ids"]:
        api.post(f"/api/erwartungen/{erw[NR]['id']}/buchungen", json={"buchung_ids": [bid]}, erwartet=200)
    return server, api, m, pf, bid, g, erw


def test_mail_blatt(mailwelt, neue_seite):
    server, api, m, pf, bid, g, erw = mailwelt
    seite = neue_seite(server)
    oeffnen(seite, server, "/mail", seitenname="mail")
    expect(tid(seite, "seite-mail").locator("h1")).to_have_text("Mail-Blatt")
    stand = api.get("/api/mail/nachrichten", erwartet=200).daten["stand"]
    expect(tid(seite, f"mail-postfach-{pf}")).to_be_visible()
    for chip, n in (("alle", stand["gesamt"]), ("zugeordnet", stand["zugeordnet"]), ("erwartet", stand["erwartet"]),
                    ("keine", stand["keine"])):
        expect(tid(seite, f"mail-filter-{chip}")).to_contain_text(f"({n})")
    expect(tid(seite, "mail-filter-alle")).to_have_attribute("aria-pressed", "true")
    liste = api.get("/api/mail/nachrichten", params={"reihenfolge": "neueste"}, erwartet=200).daten["eintraege"]
    zeilen = tid(seite, "mail-tabelle").locator('[data-testid^="mail-"][aria-selected]')
    warte(seite, lambda: zeilen.evaluate_all("els => els.map(e => e.getAttribute('data-testid'))") ==
          [f"mail-{x['id']}" for x in liste], text="neueste zuerst")
    expect(tid(seite, f"mail-{liste[0]['id']}")).to_have_attribute("aria-selected", "true")
    expect(tid(seite, "mail-block")).to_contain_text(f"von {len(liste)}")
    arten = {x["id"]: ("zugeordnet" if any(z["buchungen"] for z in x["zuordnung"]) else
                       "erwartet" if x["zuordnung"] else "keine") for x in liste}
    for i, a in arten.items():
        expect(tid(seite, f"mail-{i}")).to_have_attribute("data-zuordnung", a)
    # ohne Betreff
    leer = next(x for x in liste if x["betreff"] == "")
    expect(tid(seite, f"mail-{leer['id']}")).to_contain_text("(ohne Betreff)")
    # Pfeil ab wählt die nächste
    tid(seite, f"mail-{liste[0]['id']}").click()
    seite.keyboard.press("ArrowDown")
    expect(tid(seite, f"mail-{liste[1]['id']}")).to_have_attribute("aria-selected", "true")
    # Filter-Chip
    tid(seite, "mail-filter-zugeordnet").click()
    warte(seite, lambda: m28.abfrage(seite).get("filter") == ["zugeordnet"], text="filter=zugeordnet")
    (z,) = [x for x in liste if arten[x["id"]] == "zugeordnet"]
    warte(seite, lambda: zeilen.count() == 1, text="nur zugeordnete")
    tid(seite, f"mail-{z['id']}").click()
    expect(tid(seite, "mail-lesen")).to_be_visible()
    eid = z["zuordnung"][0]["erwartung_id"]
    expect(tid(seite, f"mail-erwartung-{eid}")).to_be_visible()
    soll = z["zuordnung"][0]["buchungen"][0]["warum"]
    lesen = tid(seite, "mail-lesen")
    expect(lesen.get_by_test_id(f"mail-warum-{bid}").first).to_contain_text(soll)
    lesen.get_by_test_id(f"mail-buchung-{bid}").first.click()
    warte_geladen(seite, "konto")
    warte(seite, lambda: ausgewaehlt(seite) == {bid}, text="Sprung zur Buchung")


def test_mail_blatt_ohne_postfach(starte_server, neue_seite):
    server = starte_server()
    seite = neue_seite(server)
    oeffnen(seite, server, "/mail", seitenname="mail")
    expect(tid(seite, "mail-stand")).to_contain_text("Kein Postfach eingerichtet.")
    expect(tid(seite, "mail-leer")).to_be_visible()


# 37.12.2 Statistik: entfällt mit M32 (sammel3.md 3, E-298)


# ------------------------------------------------------------------ 37.12.3 Empfänger, 37.10 Empfänger bestätigen


def test_empfaenger_markieren_und_bestaetigen(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    ids = [api.empfaenger(n)["id"] for n in ("Anton (fiktiv)", "Berta (fiktiv)", "Cäsar (fiktiv)", "Dora (fiktiv)")]
    seite = neue_seite(server)
    oeffnen(seite, server, "/empfaenger", seitenname="empfaenger")
    expect(tid(seite, "empfaenger-liste")).to_have_attribute("aria-multiselectable", "true")
    anzahl = tid(seite, "empfaenger-auswahl-anzahl")
    expect(anzahl).to_have_text("keine Auswahl")
    tid(seite, f"empfaenger-{ids[0]}").click()
    expect(anzahl).to_have_attribute("data-anzahl", "1")
    tid(seite, f"empfaenger-{ids[2]}").click(modifiers=["Shift"])
    expect(anzahl).to_have_attribute("data-anzahl", "3")
    expect(anzahl).to_have_text("3 ausgewählt")
    tid(seite, f"empfaenger-{ids[1]}").click(modifiers=[strg()])
    expect(anzahl).to_have_attribute("data-anzahl", "2")
    expect(tid(seite, f"empfaenger-{ids[1]}")).to_have_attribute("aria-selected", "false")
    expect(tid(seite, f"empfaenger-auswahl-{ids[0]}")).to_be_checked()
    # Bestätigen je Zeile
    k = tid(seite, f"empfaenger-bestaetigen-{ids[3]}")
    expect(k).to_have_text("Als Torsten bestätigen")
    k.click()
    warte_bis(lambda: [t["name"] for t in api.get(f"/api/empfaenger/{ids[3]}", erwartet=200).daten.get("tags", [])]
              == ["Torsten-Bestätigt"], text="Tag Torsten-Bestätigt am Empfänger (M32, E-307)")
    expect(tid(seite, f"empfaenger-{ids[3]}")).to_have_attribute("data-bestaetigt", "Torsten")
    expect(tid(seite, f"empfaenger-bestaetigen-{ids[3]}")).to_have_text("Bestätigung von Torsten zurücknehmen")
    # Kopfknopf für die Auswahl (Anton, Cäsar)
    tid(seite, f"empfaenger-{ids[0]}").click()
    tid(seite, f"empfaenger-{ids[2]}").click(modifiers=[strg()])
    expect(anzahl).to_have_attribute("data-anzahl", "2")
    expect(tid(seite, "empfaenger-bestaetigen")).to_have_text("Auswahl als Torsten bestätigen")
    tid(seite, "empfaenger-bestaetigen").click()
    warte_bis(lambda: all("tags" in api.get(f"/api/empfaenger/{i}", erwartet=200).daten for i in (ids[0], ids[2])))
    # Strg+Z: ein Rückgängig-Schritt
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.keyboard.press("Control+z")
    warte_bis(lambda: all("tags" not in api.get(f"/api/empfaenger/{i}", erwartet=200).daten
                          for i in (ids[0], ids[2])), text="Rückgängig")
    assert "tags" in api.get(f"/api/empfaenger/{ids[3]}", erwartet=200).daten
    # Kontextmenü
    tid(seite, f"empfaenger-{ids[0]}").click()
    tid(seite, f"empfaenger-{ids[1]}").click(modifiers=[strg()])
    tid(seite, f"empfaenger-{ids[1]}").click(button="right")
    expect(tid(seite, "em-zusammenfuehren")).to_have_text("2 Empfänger zusammenführen…")
    expect(tid(seite, "em-bestaetigen")).to_be_visible()


# ------------------------------------------------------------------ 37.12.4 Split-Dialog und Vorlagen


def test_split_ausgleichen_und_vorlage(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, leb, hh = (api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"],
                  api.konto("Haushalt", "aufwand")["id"])
    e = api.empfaenger("Drogerie (fiktiv)")["id"]
    bid = api.buchung("2024-05-01", [(g, -3000), (leb, 3000)], empfaenger_id=e)["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, [bid])
    m8.stift(seite, bid, "splits")
    d = tid(seite, "split-dialog")
    expect(d).to_be_visible()
    d.get_by_test_id("split-hinzufuegen").click()
    d.get_by_test_id("split-konto-2").select_option(str(hh))
    d.get_by_test_id("split-betrag-1").fill(m8.eingabe_betrag(1000))
    d.get_by_test_id("split-ausgleichen-2").click()
    assert m8.lies_betrag(d.get_by_test_id("split-betrag-2").input_value()) == 2000
    expect(d.get_by_test_id("split-rest")).to_have_attribute("data-betrag", "0")
    expect(d.get_by_test_id("split-vorlage-name")).to_have_value("Drogerie (fiktiv)")
    a0 = m8.max_aenderung(api)
    d.get_by_test_id("split-vorlage").click()
    warte_bis(lambda: api.get("/api/vorlagen", erwartet=200).daten, text="Vorlage angelegt")
    expect(d).to_be_visible()
    assert [a["aktion"] for a in m8.aenderungen_seit(api, a0)] == ["vorlage_anlegen"]
    (v,) = api.get("/api/vorlagen", erwartet=200).daten
    d.get_by_test_id("split-abbrechen").click()
    oeffnen(seite, server, "/vorlagen", seitenname="vorlagen")
    expect(tid(seite, f"vorlage-{v['id']}")).to_be_visible()
    expect(tid(seite, f"vorlage-splitbetrag-{v['id']}")).to_have_attribute("data-betrag", str(v["gesamtbetrag"]))
    expect(tid(seite, f"vorlage-empfaenger-{v['id']}")).to_contain_text("Drogerie (fiktiv)")


# ------------------------------------------------------------------ 37.12.5 Dubletten


def test_dubletten_seite_mit_vorschlag(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    e = api.empfaenger("Doppelt (fiktiv)")["id"]
    a = api.buchung("2024-05-01", [(g, -700), (leb, 700)], empfaenger_id=e)["id"]
    b = api.buchung("2024-05-01", [(g, -700), (leb, 700)], empfaenger_id=e)["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, "/dubletten", seitenname="dubletten")
    expect(tid(seite, "dubletten-regel")).to_be_visible()
    seite.get_by_role("button", name="Keine Dublette").first.click()
    warte_bis(lambda: [v["status"] for v in api.get("/api/dubletten", erwartet=200).daten] == ["keine_dublette"])
    (v,) = api.get("/api/dubletten", erwartet=200).daten
    assert {v["buchung_id"], *v["kandidat_ids"]} == {a, b}


# ------------------------------------------------------------------ 37.12.6 leere Werte (C2)


def test_keine_leerwoerter_und_texte_unveraendert(starte_server, neue_seite):
    server = starte_server()
    api = server.api
    g, leb = api.konto("Girokonto")["id"], api.konto("Lebensmittel", "aufwand")["id"]
    e = api.empfaenger("None GmbH (fiktiv)")["id"]
    bid = api.buchung("2024-05-01", [(g, -700), (leb, 700)], empfaenger_id=e,
                      verwendungszweck="Rechnung undefined 4711")["id"]
    ohne = api.buchung("2024-05-02", [(g, -1), (leb, 1)])["id"]
    seite = neue_seite(server)
    oeffnen(seite, server, f"/konten/{g}", seitenname="konto")
    warte_liste(seite, [ohne, bid])
    expect(zeile(seite, bid).locator('[data-feld="empfaenger"]')).to_contain_text("None GmbH (fiktiv)")
    expect(zeile(seite, bid).locator('[data-feld="verwendungszweck"]')).to_contain_text("Rechnung undefined 4711")
    assert m28.leere_woerter(zeile(seite, ohne).inner_text()) == []
    for pfad in ("/", "/konten", "/empfaenger", "/erwartet", "/mail", "/dubletten"):   # /statistik entfällt (E-298)
        oeffnen(seite, server, pfad)
        warte(seite, lambda: seite.locator('[data-testid^="seite-"][data-geladen="ja"]').count() >= 1, text=pfad)
        text = tid(seite, "hauptbereich").inner_text().replace("None GmbH (fiktiv)", "")
        assert m28.leere_woerter(text) == [], (pfad, m28.leere_woerter(text))
