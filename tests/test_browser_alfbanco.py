"""Browser-Rauchtest: ALF-BanCo-Import über die Import-Seite und Kategorien zusammenführen (D-123, D-126).

Synthetische Daten; Server im Mock-Modus auf einem freien Loopback-Port."""

from __future__ import annotations

from .test_alfbanco_eigen import roh
from .test_browser import DESKTOP, bereit, browser, expect, seite, server, tid  # noqa: F401 (Fixture)


def test_import_und_zusammenfuehren(tmp_path, browser):  # noqa: F811
    with server(tmp_path) as (url, _), seite(browser, url, **DESKTOP) as page:
        page.goto(url + "/import")
        bereit(page, "import")
        expect(tid(page, "import-konto")).to_be_hidden()
        tid(page, "import-format").select_option("alfbanco")
        expect(tid(page, "import-konto")).to_be_visible()
        tid(page, "import-konto").select_option(label="Giro")
        tid(page, "import-datei").set_input_files(files=[{"name": "giro.qif", "mimeType": "application/qif",
                                                           "buffer": roh()}])
        tid(page, "import-starten").click()
        expect(tid(page, "import-ergebnis")).to_have_attribute("data-erfolgreich", "ja")
        expect(tid(page, "import-zahl-buchungen_neu")).to_have_attribute("data-anzahl", "6")

        page.goto(url + "/kategorien")
        bereit(page, "kategorien")
        baum = tid(page, "kategorienbaum")
        kleidung = baum.get_by_role("treeitem", name="Kleidung", exact=True)
        haushalt = baum.get_by_role("treeitem", name="Haushalt", exact=True)
        kleidung.locator(".baum-name").click()
        haushalt.locator(".baum-name").first.click(modifiers=["Control"])
        expect(kleidung).to_have_attribute("aria-selected", "true")
        expect(haushalt).to_have_attribute("aria-selected", "true")
        haushalt.locator(".baum-name").first.click(button="right")
        expect(tid(page, "km-kategorie-zusammenfuehren")).to_contain_text("2 Kategorien")
        tid(page, "km-kategorie-zusammenfuehren").click()
        dlg = tid(page, "zusammenfuehren-dialog")
        expect(dlg).to_be_visible()
        tid(page, "zusammenfuehren-suche").fill("lebensmittel")
        ziel = dlg.get_by_role("option").filter(has_text="Lebensmittel").filter(has_not_text="Haushalt").first
        ziel.click()
        expect(tid(page, "zusammenfuehren-vorschau")).to_contain_text("Buchungen")
        tid(page, "zusammenfuehren-ausfuehren").click()
        expect(dlg).to_be_hidden()
        expect(baum.get_by_role("treeitem", name="Kleidung", exact=True)).to_have_count(0)
        expect(baum.get_by_role("treeitem", name="Haushalt", exact=True)).to_have_count(0)
