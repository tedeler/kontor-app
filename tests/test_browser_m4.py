"""Browser-Rauchtest der M4-Oberfläche (Playwright, Chrome headless): GnuCash-Import auf der Import-Seite,
Split-Vorlagen anlegen/anpassen/anwenden mit Hinweis bei Abweichung, Lernmodell (Zustand, Anwenden,
Vorschläge mit Sicherheit) und der Dialog für gelöschte Bankkonten (Handy).

Echte Server im Mock-Modus (eingebauter synthetischer Datensatz) auf freien lokalen Ports; nur
synthetische Daten, keine Verbindung nach außen.
"""

from __future__ import annotations

import pytest

from .test_browser_m2 import _neue_seite, _server, browser  # noqa: F401  (Fixture)

playwright = pytest.importorskip("playwright.sync_api")

GNC_XML = """<?xml version="1.0" encoding="utf-8" ?>
<gnc-v2 xmlns:gnc="http://www.gnucash.org/XML/gnc" xmlns:act="http://www.gnucash.org/XML/act"
        xmlns:trn="http://www.gnucash.org/XML/trn" xmlns:split="http://www.gnucash.org/XML/split"
        xmlns:ts="http://www.gnucash.org/XML/ts" xmlns:slot="http://www.gnucash.org/XML/slot"
        xmlns:cmdty="http://www.gnucash.org/XML/cmdty">
 <gnc:book version="2.0.0">
  <gnc:account version="2.0.0"><act:name>Root Account</act:name><act:id type="guid">r0</act:id>
   <act:type>ROOT</act:type></gnc:account>
  <gnc:account version="2.0.0"><act:name>Altes Giro</act:name><act:id type="guid">a1</act:id>
   <act:type>BANK</act:type><act:parent type="guid">r0</act:parent></gnc:account>
  <gnc:account version="2.0.0"><act:name>Bücher</act:name><act:id type="guid">a2</act:id>
   <act:type>EXPENSE</act:type><act:parent type="guid">r0</act:parent></gnc:account>
  <gnc:transaction version="2.0.0"><trn:id type="guid">t1</trn:id>
   <trn:date-posted><ts:date>2023-05-02 10:59:00 +0000</ts:date></trn:date-posted>
   <trn:description>Buchladen (fiktiv)</trn:description>
   <trn:splits>
    <trn:split><split:id type="guid">s1</split:id><split:value>-1990/100</split:value>
     <split:account type="guid">a1</split:account></trn:split>
    <trn:split><split:id type="guid">s2</split:id><split:value>1990/100</split:value>
     <split:account type="guid">a2</split:account></trn:split>
   </trn:splits></gnc:transaction>
 </gnc:book>
</gnc-v2>
""".encode("utf-8")


def _konten(page, url) -> dict[str, dict]:
    return {k["name"]: k for k in page.request.get(url + "/api/konten").json()}


def test_m4_desktop(tmp_path, browser):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport={"width": 1280, "height": 900})
        # GnuCash-Import: Quelle wird an der Dateiendung erkannt
        page.goto(url + "/#/import")
        page.wait_for_selector("h1:has-text('Import')")
        page.set_input_files("input[type=file]", files=[{"name": "alt.gnucash", "mimeType": "application/xml",
                                                         "buffer": GNC_XML}])
        assert page.locator("input[value=gnucash]").is_checked()
        page.locator("button[type=submit]", has_text="Importieren").click()
        page.wait_for_selector("text=Import erfolgreich (gnc-xml)")
        assert "Altes Giro" in _konten(page, url)
        # Split-Vorlage über den Dialog anlegen – mit absichtlich falschem Teilbetrag (979,99 statt 980,00)
        kalt = page.request.post(url + "/api/konten", data={"name": "Kaltmiete", "art": "aufwand"}).json()
        nk = page.request.post(url + "/api/konten", data={"name": "Nebenkosten", "art": "aufwand"}).json()
        page.goto(url + "/#/vorlagen")
        page.locator("button", has_text="+ Split-Vorlage anlegen").click()
        page.fill(".dialog label:has-text('Name') input", "Miete")
        page.select_option(".dialog .bed-zeile select[aria-label=Operator]", value="gleich")
        page.fill(".dialog .bed-zeile input[aria-label=Wert]", "Wohnbau Beispiel eG (fiktiv)")
        teile = page.locator(".dialog .teil-zeile")
        teile.nth(0).locator("select").select_option(value=str(kalt["id"]))
        teile.nth(0).locator("input[aria-label=Teilbetrag]").fill("800,00")
        teile.nth(1).locator("select").select_option(value=str(nk["id"]))
        teile.nth(1).locator("input[aria-label=Teilbetrag]").fill("179,99")
        page.wait_for_selector(".dialog:has-text('Gesamtbetrag der Abbuchung: −979,99 €')")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector("td:has-text('Miete')")
        (v,) = page.request.get(url + "/api/vorlagen").json()
        assert v["gesamtbetrag"] == -97999
        # Synchronisation: keine Aufteilung, genau eine Benachrichtigung (keine Toleranz, Entprellung)
        lauf = page.request.post(url + "/api/sync", data={"von": "2024-01-01"}).json()
        assert sum(k["vorlage_abweichungen"] for k in lauf["konten"]) == 6
        hinweise = [n for n in page.request.get(url + "/api/benachrichtigungen").json() if n["art"] == "split_abweichung"]
        assert len(hinweise) == 1
        # Link aus der Benachrichtigung öffnet die Buchung
        page.goto(url + hinweise[0]["link"])
        page.wait_for_selector(".dialog")
        page.keyboard.press("Escape")
        # Hinweis auf der Vorlagenseite, Vorlage anpassen, nachträglich aufteilen
        page.goto(url + "/#/vorlagen")
        page.wait_for_selector(".hinweis-tan:has-text('Abweichungen')")
        page.locator(".hinweis-tan button", has_text="Vorlage anpassen").click()
        page.locator(".dialog .teil-zeile").nth(1).locator("input[aria-label=Teilbetrag]").fill("180,00")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Vorlage angepasst')")
        page.locator("button", has_text="Probelauf").first.click()
        page.wait_for_selector("text=6 würden aufgeteilt")
        page.locator("button", has_text="Jetzt aufteilen").click()
        page.wait_for_selector(".meldung:has-text('6 Buchung(en) aufgeteilt')")
        wohn = next(e for e in page.request.get(url + "/api/empfaenger").json() if e["name"].startswith("Wohnbau"))
        miete = page.request.get(url + f"/api/buchungen?empfaenger_id={wohn['id']}").json()["eintraege"]
        assert len(miete) == 6 and all([s["betrag"] for s in b["splits"]][1:] == [80000, 18000] for b in miete)
        # Lernmodell: drei Einkäufe kategorisieren, dann anwenden; Vorschläge zeigen die Sicherheit
        leb = page.request.post(url + "/api/konten", data={"name": "Lebensmittel", "art": "aufwand"}).json()
        markt = next(e for e in page.request.get(url + "/api/empfaenger").json() if e["name"].startswith("Supermarkt"))
        einkaeufe = page.request.get(url + f"/api/buchungen?empfaenger_id={markt['id']}").json()["eintraege"]
        for b in einkaeufe[:3]:
            page.request.put(url + f"/api/buchungen/{b['id']}/kategorie", data={"kategorie_id": leb["id"]})
        page.goto(url + "/#/lernmodell")
        page.wait_for_selector("li:has-text('Trainingsbuchungen: 4')")  # 3 Einkäufe + 1 GnuCash-Buchung
        page.locator("button", has_text="Probelauf").click()
        page.wait_for_selector("text=würden als Vorschlag kategorisiert")
        page.locator("button", has_text="Jetzt anwenden").click()
        page.wait_for_selector(".meldung:has-text('Vorschlag/Vorschläge gesetzt')")
        page.goto(url + "/#/buchungen?vorschlag=true")
        page.wait_for_selector(".vorschlag-lern")
        assert "%" in page.locator(".vorschlag-lern").first.inner_text()
        assert not fehler, fehler
        page.close()


def test_m4_handy_geloeschtes_bankkonto(tmp_path, browser):  # noqa: F811
    with _server(tmp_path, "normal") as url:
        page, fehler = _neue_seite(browser, viewport={"width": 390, "height": 840}, is_mobile=True, has_touch=True)
        page.request.post(url + "/api/sync", data={})
        tg = _konten(page, url)["Tagesgeld (Mock)"]
        page.request.post(url + f"/api/konten/{tg['id']}/loeschen", data={"buchungen": "loeschen", "konflikte": "loeschen"})
        lauf = page.request.post(url + "/api/sync", data={}).json()
        assert [u["status"] for u in lauf["uebersprungen"]] == ["konto_fehlt"]
        # Link aus der Benachrichtigung führt zu den Bankkonten
        (n,) = [x for x in page.request.get(url + "/api/benachrichtigungen").json() if x["art"] == "konto_fehlt"]
        page.goto(url + n["link"])
        page.wait_for_selector(".hinweis-tan:has-text('Rückfrage')")
        page.locator("tr.fehlt button", has_text="Entscheiden").click()
        page.wait_for_selector(".dialog:has-text('Gelöschtes Bankkonto')")
        assert page.locator(".dialog input[type=radio]:checked").count() == 0, "die Frage wird gestellt, nicht beantwortet"
        page.locator(".dialog input[value=wiederherstellen]").check()
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Bitte wählen, welche Umsätze')")
        page.locator(".dialog input[value=alle]").check()
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".dialog:has-text('Jetzt synchronisieren')")
        page.locator(".dialog button[type=submit]").click()
        page.wait_for_selector(".meldung:has-text('Synchronisation erfolgreich')")
        neu = _konten(page, url)["Tagesgeld (Mock)"]
        assert neu["id"] != tg["id"]
        assert page.request.get(url + f"/api/buchungen?konto_id={neu['id']}").json()["gesamt"] > 0
        z = {x["iban"]: x for x in page.request.get(url + "/api/sync/konten").json()}
        assert z[neu["iban"]]["status"] == "aktiv"
        assert all(x["gelesen"] for x in page.request.get(url + "/api/benachrichtigungen").json() if x["art"] == "konto_fehlt")
        assert not fehler, fehler
        page.close()
