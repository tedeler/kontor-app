"""M20: Seite „Was kommt noch?“ (oberflaeche.md 30, E-219) – Playwright wie M8; nicht kern, nur Desktop."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.hilfen import m8
from tests.hilfen.m6 import EINS, abruf, postfach
from tests.hilfen.m8 import oeffnen, strg, tid, warte_bis
from tests.hilfen.m15 import text_normal
from tests.hilfen.m20 import (
    alle, amazon_bestellung, ausgabe, detail, konten, liste, mock_datei, paypal_zahlung,
)

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

ERFOLG = '[data-testid="meldung"][data-art="erfolg"]'
MAILS = [amazon_bestellung(empfangen="2024-12-01T08:00:00Z"), paypal_zahlung(empfangen="2024-12-28T08:00:00Z")]


def _start(starte_server, tmp_path, *, abgleich=True, mails=MAILS):
    datei = mock_datei(tmp_path / "mails.json", mails)
    server = starte_server(mock_daten=datei, mail_erstabruf_tage=365, mail_abgleich=abgleich)
    api = server.api
    postfach(api, EINS)
    abruf(api)
    return server, api


def _zeilen(seite) -> list[int]:
    return [int(x) for x in tid(seite, "erwartet-tabelle").locator('[data-testid^="erwartung-"]').evaluate_all(
        "els => els.filter(e => /^erwartung-[0-9]+$/.test(e.dataset.testid)).map(e => e.dataset.testid.slice(10))")]


def _warte_zeilen(seite, soll):
    warte_bis(lambda: _zeilen(seite) == soll, text=f"Zeilen {soll}")


def _abfrage(seite) -> dict:
    return parse_qs(urlsplit(seite.url).query)


def test_seite_navigation_und_tabelle(starte_server, neue_seite, tmp_path):
    server, api = _start(starte_server, tmp_path)
    best, zahl = sorted(alle(api), key=lambda e: e["frist"])
    seite = neue_seite(server)
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    s = tid(seite, "seite-erwartet")
    expect(s).to_have_attribute("data-aktiv", "ja")
    expect(s).to_contain_text("Was kommt noch?")
    assert tid(seite, "navlink-erwartet").count() == 1
    l = liste(api)
    _warte_zeilen(seite, [e["id"] for e in l["eintraege"]])
    z = tid(seite, f"erwartung-{best['id']}")
    expect(z).to_have_attribute("data-zustand", "ueberfaellig")
    expect(z).to_have_attribute("data-grund", "bestellung")
    expect(tid(seite, f"erwartung-{zahl['id']}")).to_have_attribute("data-zustand", "offen")
    summe = tid(seite, "erwartet-summe")
    # data-betrag am Element selbst oder an dem Betrag darin (E-219)
    assert seite.evaluate("""el => [el, ...el.querySelectorAll('[data-betrag]')].map(e => e.getAttribute('data-betrag'))
        .filter(x => x !== null)""", summe.element_handle()) == [str(l["summe_offen"])]
    expect(summe).to_contain_text("2 Einträge")
    expect(summe).to_contain_text("1 überfällig")
    expect(summe).to_contain_text("noch offen:")
    # Befehlspalette: nach „Gehe zu: Synchronisation“, vor „Gehe zu: Benachrichtigungen“
    seite.keyboard.press(f"{strg()}+k")
    expect(tid(seite, "befehlspalette")).to_be_visible()
    texte = [text_normal(t) for t in tid(seite, "befehlspalette-liste").locator('[role="option"]').all_text_contents()]
    i = texte.index("Gehe zu: Was kommt noch? (erwartete Zahlungen)")
    assert texte.index("Gehe zu: Synchronisation") < i < texte.index("Gehe zu: Benachrichtigungen")
    seite.keyboard.press("Escape")


def test_ausgeschaltet_und_leer(starte_server, neue_seite, tmp_path):
    server, api = _start(starte_server, tmp_path, abgleich=False)
    seite = neue_seite(server)
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    expect(tid(seite, "seite-erwartet")).to_have_attribute("data-aktiv", "nein")
    expect(tid(seite, "erwartet-summe")).to_contain_text("Der Mail-Abgleich ist ausgeschaltet")
    expect(tid(seite, "erwartet-leer")).to_be_visible()


def test_chips_und_adresse(starte_server, neue_seite, tmp_path):
    server, api = _start(starte_server, tmp_path)
    best, zahl = sorted(alle(api), key=lambda e: e["frist"])
    m = api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Bücherstube (fiktiv)", "betrag": 900,
                                           "datum": "2024-12-30"}, erwartet=201).daten
    api.post(f"/api/erwartungen/{m['id']}/zustand", json={"zustand": "erledigt"}, erwartet=200)
    seite = neue_seite(server)
    # „heute“ der Chips Fällig: Browser-Uhr gleich der App-Uhr (E-219), damit beide Lesarten übereinstimmen
    seite.clock.set_fixed_time("2024-12-31T12:00:00Z")
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    offen = tid(seite, "erwartet-zustand-offen")
    expect(offen).to_have_attribute("aria-pressed", "true")
    _warte_zeilen(seite, [best["id"], zahl["id"]])
    tid(seite, "erwartet-grund-paypal").click()
    expect(tid(seite, "erwartet-grund-paypal")).to_have_attribute("aria-pressed", "true")
    _warte_zeilen(seite, [zahl["id"]])
    assert _abfrage(seite).get("grund") == ["paypal"]
    tid(seite, "erwartet-grund-paypal").click()
    tid(seite, "erwartet-zustand-geschlossen").click()
    _warte_zeilen(seite, [best["id"], zahl["id"], m["id"]])
    offen.click()
    _warte_zeilen(seite, [m["id"]])
    tid(seite, "erwartet-zustand-geschlossen").click()
    expect(offen).to_have_attribute("aria-pressed", "true"), "letzter Chip abgewählt → wieder Offen"
    _warte_zeilen(seite, [best["id"], zahl["id"]])
    tid(seite, "erwartet-zustand-ueberfaellig").click()
    offen.click()
    _warte_zeilen(seite, [best["id"]])
    tid(seite, "erwartet-zustand-ueberfaellig").click()
    tid(seite, "erwartet-suche").fill("fiktiver shop")
    _warte_zeilen(seite, [zahl["id"]])
    assert _abfrage(seite).get("suche") == ["fiktiver shop"]
    tid(seite, "erwartet-suche").fill("")
    _warte_zeilen(seite, [best["id"], zahl["id"]])
    tid(seite, "erwartet-faellig-0").click()
    expect(tid(seite, "erwartet-faellig-0")).to_have_attribute("aria-pressed", "true")
    _warte_zeilen(seite, [best["id"]])
    # direkter Aufruf setzt die Chips
    oeffnen(seite, server, "/erwartet?grund=manuell&zustand=geschlossen", seitenname="erwartet")
    expect(tid(seite, "erwartet-grund-manuell")).to_have_attribute("aria-pressed", "true")
    expect(tid(seite, "erwartet-zustand-geschlossen")).to_have_attribute("aria-pressed", "true")
    expect(tid(seite, "erwartet-zustand-offen")).to_have_attribute("aria-pressed", "false")
    _warte_zeilen(seite, [m["id"]])


def test_menue_zustand_und_rueckgaengig(starte_server, neue_seite, tmp_path):
    server, api = _start(starte_server, tmp_path)
    best, zahl = sorted(alle(api), key=lambda e: e["frist"])
    m = api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Fiktiv", "betrag": 500},
                 erwartet=201).daten
    seite = neue_seite(server)
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    _warte_zeilen(seite, [e["id"] for e in liste(api)["eintraege"]])
    tid(seite, f"erwartung-menue-{best['id']}").click()
    km = tid(seite, "kontextmenue")
    expect(km).to_be_visible()
    ids = [x for x in km.locator('[role="menuitem"]').evaluate_all("els => els.map(e => e.dataset.testid)")]
    assert {"km-erwartung-details", "km-erwartung-bearbeiten", "km-erwartung-erledigt", "km-erwartung-guthaben",
            "km-erwartung-storniert"} <= set(ids)
    assert "km-erwartung-oeffnen" not in ids and "km-erwartung-loeschen" not in ids
    km.get_by_test_id("km-erwartung-erledigt").click()
    warte_bis(lambda: detail(api, best["id"])["zustand"] == "erledigt", text="erledigt")
    seite.keyboard.press(f"{strg()}+z")
    warte_bis(lambda: detail(api, best["id"])["zustand"] == "offen", text="Rückgängig")
    tid(seite, f"erwartung-{m['id']}").click(button="right")
    ids = tid(seite, "kontextmenue").locator('[role="menuitem"]').evaluate_all("els => els.map(e => e.dataset.testid)")
    assert "km-erwartung-loeschen" in ids
    seite.keyboard.press("Escape")
    api.post(f"/api/erwartungen/{zahl['id']}/zustand", json={"zustand": "storniert"}, erwartet=200)
    oeffnen(seite, server, "/erwartet?zustand=geschlossen", seitenname="erwartet")
    tid(seite, f"erwartung-menue-{zahl['id']}").click()
    ids = tid(seite, "kontextmenue").locator('[role="menuitem"]').evaluate_all("els => els.map(e => e.dataset.testid)")
    assert "km-erwartung-oeffnen" in ids and "km-erwartung-erledigt" not in ids


def test_dialog_anlegen_und_bearbeiten(starte_server, neue_seite, tmp_path):
    server, api = _start(starte_server, tmp_path, mails=[])
    seite = neue_seite(server)
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    tid(seite, "erwartet-neu").click()
    dlg = tid(seite, "erwartung-dialog")
    expect(dlg).to_be_visible()
    tid(seite, "erwartung-richtung").select_option("ausgabe")
    tid(seite, "erwartung-haendler").fill("Fiktiver Bäcker")
    tid(seite, "erwartung-betrag").fill("abc")
    tid(seite, "erwartung-ok").click()
    expect(dlg.get_by_test_id("dialog-fehler")).to_be_visible()
    tid(seite, "erwartung-betrag").fill("12,34")
    tid(seite, "erwartung-datum").fill("2024-12-20")
    tid(seite, "erwartung-frist").fill("2024-12-27")
    tid(seite, "erwartung-beschreibung").fill("Torte")
    tid(seite, "erwartung-ok").click()
    expect(dlg).to_be_hidden()
    (e,) = warte_bis(lambda: alle(api), text="angelegt")
    assert (e["betrag"], e["haendler"], e["datum"], e["frist"], e["beschreibung"], e["richtung"]) == (
        1234, "Fiktiver Bäcker", "2024-12-20", "2024-12-27", "Torte", "ausgabe")
    tid(seite, f"erwartung-menue-{e['id']}").click()
    tid(seite, "kontextmenue").get_by_test_id("km-erwartung-bearbeiten").click()
    expect(dlg).to_be_visible()
    expect(tid(seite, "erwartung-richtung")).to_be_disabled()
    tid(seite, "erwartung-betrag").fill("20,00")
    tid(seite, "erwartung-ok").click()
    warte_bis(lambda: detail(api, e["id"])["betrag"] == 2000, text="geändert")


def test_details_kandidaten_belege_und_sprung(starte_server, neue_seite, tmp_path):
    server, api = _start(starte_server, tmp_path)
    best = next(e for e in alle(api) if e["grund"] == "bestellung")
    k = konten(api)
    b = ausgabe(api, k, "2024-12-02", 4990, "Kartenzahlung")
    seite = neue_seite(server, erfolgsmeldung=True)   # Erfolgsmeldung ab M32 nur mit Einstellung (E-307)
    oeffnen(seite, server, f"/erwartet?id={best['id']}", seitenname="erwartet")
    det = tid(seite, "erwartung-details")
    expect(det).to_be_visible()
    tid(seite, "erwartung-details-schliessen").click()
    expect(det).to_be_hidden()
    oeffnen(seite, server, f"/erwartet?id={best['id']}", seitenname="erwartet")
    expect(det).to_be_visible()
    expect(tid(seite, "erwartung-mails")).to_contain_text("Bestellung")
    expect(tid(seite, f"kandidat-{b}")).to_be_visible()
    tid(seite, f"kandidat-zuordnen-{b}").click()
    warte_bis(lambda: detail(api, best["id"])["buchung_ids"] == [b], text="zugeordnet")
    # ob die Details danach offen bleiben, ist nicht festgelegt (E-219): erneut über die Adresse öffnen
    oeffnen(seite, server, f"/erwartet?id={best['id']}&zustand=erfuellt", seitenname="erwartet")
    expect(det).to_be_visible()
    expect(tid(seite, "erwartung-buchungen")).to_contain_text("Kartenzahlung")
    expect(tid(seite, "erwartung-zustand")).to_contain_text(re.compile("erfüllt", re.I))
    tid(seite, "erwartung-belege").click()
    expect(tid(seite, "dokument-betrachter")).to_be_visible()
    tid(seite, "betrachter-schliessen").click()
    tid(seite, f"erwartung-loesen-{b}").click()
    warte_bis(lambda: detail(api, best["id"])["buchung_ids"] == [], text="gelöst")
    oeffnen(seite, server, "/erwartet", seitenname="erwartet")
    # Jetzt abgleichen: Meldung mit Zählungen
    tid(seite, "erwartet-abgleichen").click()
    expect(tid(seite, "meldungen").locator(ERFOLG).last).to_contain_text(
        re.compile(r"Abgeglichen: \d+ neu erkannt, \d+ zugeordnet\."))
    assert m8.max_aenderung(api) >= 1
