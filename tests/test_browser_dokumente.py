"""Entwicklungstests (Browser) für das Feature „dokumente“ (D-123): Anhängen über das Detailpanel, Ziehen einer
Datei auf eine Zeile, Betrachter für PDF, Bild und E-Mail, E-Mail aus dem Postfach, mobil mit Kamera-Knopf.
Synthetische Daten; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import contextlib

import httpx
import pytest

from .test_browser import DESKTOP, HANDY, bereit, browser, expect, server, tid  # noqa: F401
from .test_browser_tabs import _daten, _get
from .test_dokumente_eigen import PDF, PNG, mail_bytes


@contextlib.contextmanager
def seite(browser, url, **kw):  # noqa: F811
    """Wie test_browser.seite, aber der eingebaute PDF-Betrachter von Chrome (chrome-extension://, chrome://) ist
    erlaubt; vom Server blockierte externe Inhalte einer E-Mail werden gesammelt statt als Fehler gewertet."""
    ctx = browser.new_context(locale="de-DE", timezone_id="Europe/Berlin", reduced_motion="reduce", **kw)
    ctx.set_default_timeout(10_000)
    page = ctx.new_page()
    fehler: list[str] = []
    page.blockiert = []
    eigen = (url, "data:", "blob:", "chrome-extension://", "chrome://", "about:")
    page.on("pageerror", lambda e: fehler.append(str(e)))

    def konsole(m):
        if "Content Security Policy" in m.text:
            (page.blockiert if "tracker.example.invalid" in m.text else fehler).append(m.text)
    page.on("console", konsole)
    page.on("request", lambda r: fehler.append("fremd: " + r.url) if not r.url.startswith(eigen) else None)
    try:
        yield page
    finally:
        ctx.close()
    assert not fehler, fehler


def _post(adresse, **kw):
    with httpx.Client(trust_env=False) as c:
        return c.post(adresse, **kw)


@pytest.fixture
def umgebung(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **DESKTOP) as page:
        konten = {k["name"]: k["id"] for k in _get(url + "/api/konten")}
        buchungen = _get(url + "/api/buchungen", konto_id=konten["Giro"], pro_seite=200)["eintraege"]
        yield url, page, konten, {b["verwendungszweck"]: b["id"] for b in buchungen}


def _oeffnen(page, url, konto, bid):
    page.goto(f"{url}/konten/{konto}")
    bereit(page, "konto")
    tid(page, f"buchung-{bid}").locator('[data-feld="datum"]').click()
    expect(tid(page, "details-dokumente")).to_have_attribute("data-buchung-id", str(bid))


def test_pdf_anhaengen_ansehen_loesen(umgebung, tmp_path):
    url, page, konten, zweck = umgebung
    bid = zweck["Einkauf 3"]
    _oeffnen(page, url, konten["Giro"], bid)
    datei = tmp_path / "Rechnung März.pdf"
    datei.write_bytes(PDF)
    with page.expect_file_chooser() as fc:
        tid(page, "dokument-anhaengen").click()
    fc.value.set_files(str(datei))
    expect(tid(page, "details-dokumente")).to_have_attribute("data-anzahl", "1")
    marke = tid(page, f"beleg-marke-{bid}")
    expect(marke).to_be_visible()
    d = _get(url + f"/api/buchungen/{bid}")["belege"][0]
    assert (d["dateiname"], d["mime_typ"]) == ("Rechnung März.pdf", "application/pdf")
    marke.click()
    b = tid(page, "dokument-betrachter")
    expect(b).to_be_visible()
    expect(b).to_have_attribute("data-typ", "application/pdf")
    expect(tid(page, "betrachter-pdf")).to_have_attribute("src", f"/api/dokumente/{d['id']}/inhalt")
    expect(b.locator("h2")).to_have_text("Rechnung März.pdf")
    tid(page, "betrachter-schliessen").click()   # Esc erreicht die Seite nicht, solange der PDF-Betrachter den Fokus hat
    expect(b).to_have_count(0)
    # lösen und Rückgängig
    tid(page, f"dokument-loesen-{d['id']}").click()
    expect(tid(page, "details-dokumente")).to_have_attribute("data-anzahl", "0")
    expect(tid(page, f"beleg-marke-{bid}")).to_have_count(0)
    page.keyboard.press("Control+z")
    expect(tid(page, f"beleg-marke-{bid}")).to_be_visible()


def test_datei_auf_zeile_ziehen_und_mehrfachauswahl(umgebung):
    url, page, konten, zweck = umgebung
    page.goto(f"{url}/konten/{konten['Giro']}")
    bereit(page, "konto")
    a, b = zweck["Einkauf 5"], zweck["Einkauf 6"]
    tid(page, f"buchung-{a}").locator('[data-feld="datum"]').click()
    tid(page, f"buchung-{b}").locator('[data-feld="datum"]').click(modifiers=["Control"])
    # Datei aus dem Betriebssystem simulieren (DataTransfer mit File) und auf eine gewählte Zeile fallen lassen
    page.evaluate("""([sel, bytes]) => {
        const ziel = document.querySelector(sel);
        const dt = new DataTransfer();
        dt.items.add(new File([new Uint8Array(bytes)], "kassenbon.png", { type: "image/png" }));
        for (const art of ["dragenter", "dragover", "drop"]) {
            ziel.dispatchEvent(new DragEvent(art, { bubbles: true, cancelable: true, dataTransfer: dt }));
        }
    }""", [f'[data-testid="buchung-{a}"] [data-feld="verwendungszweck"]', list(PNG)])
    expect(tid(page, f"beleg-marke-{a}")).to_be_visible()
    expect(tid(page, f"beleg-marke-{b}")).to_be_visible()
    d = _get(url + f"/api/buchungen/{a}")["belege"][0]
    assert _get(url + f"/api/dokumente/{d['id']}")["buchung_ids"] == sorted([a, b])
    tid(page, f"beleg-marke-{b}").click()
    expect(tid(page, "betrachter-bild")).to_be_visible()
    assert page.evaluate("() => document.querySelector('[data-testid=betrachter-bild]').naturalWidth") == 1


def test_mail_betrachter_html_und_anhang(umgebung):
    url, page, konten, zweck = umgebung
    bid = zweck["Einkauf 7"]
    r = _post(url + "/api/dokumente", params={"buchung_id": bid}, files={"datei": ("rechnung.eml", mail_bytes(), "message/rfc822")})
    assert r.status_code == 201, r.text
    _oeffnen(page, url, konten["Giro"], bid)
    tid(page, f"dokument-ansehen-{r.json()['id']}").click()
    expect(tid(page, "mail-betreff")).to_have_text("Ihre Rechnung Nr. 4711 (Testdaten)")
    expect(tid(page, "mail-von")).to_contain_text("shop@example.invalid")
    rahmen = tid(page, "mail-html")
    expect(rahmen).to_have_attribute("sandbox", "allow-popups allow-popups-to-escape-sandbox")
    inhalt = page.frame_locator('[data-testid="mail-html"]')
    expect(inhalt.locator("b")).to_have_text("Erika")
    assert inhalt.locator("script").count() == 0
    tid(page, "mail-ansicht-umschalten").click()
    expect(tid(page, "mail-text")).to_contain_text("anbei die Rechnung")
    assert not page.blockiert, "das Zählpixel wird schon vom Server entfernt und nie angefragt"
    anhang = page.locator('[data-testid^="mail-anhang-ansehen-"]')
    expect(anhang).to_have_text("Rechnung-4711.pdf")
    anhang.click()
    expect(tid(page, "betrachter-pdf")).to_be_visible()
    tid(page, "betrachter-zur-mail").click()
    expect(tid(page, "mail-betreff")).to_be_visible()


def test_mail_aus_postfach_anhaengen(umgebung):
    url, page, konten, zweck = umgebung
    assert _post(url + "/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
    assert _post(url + "/api/mail/abruf").status_code == 200
    mails = _get(url + "/api/mail/nachrichten", pro_seite=500)["eintraege"]
    neueste = mails[-1]
    bid = zweck["Einkauf 8"]
    _oeffnen(page, url, konten["Giro"], bid)
    tid(page, "dokument-mail").click()
    d = tid(page, "mail-auswahl-dialog")
    expect(d.locator('[role="option"]').first).to_have_attribute("data-testid", f"mail-auswahl-{neueste['id']}")
    tid(page, "mail-auswahl-suche").fill(neueste["betreff"][:20])
    tid(page, f"mail-auswahl-{neueste['id']}").click()
    expect(d).to_have_count(0)
    expect(tid(page, "details-dokumente")).to_have_attribute("data-anzahl", "1")
    beleg = _get(url + f"/api/buchungen/{bid}")["belege"][0]
    assert beleg["mime_typ"] == "message/rfc822"


def test_kontextmenue_eintraege(umgebung):
    url, page, konten, zweck = umgebung
    bid = zweck["Einkauf 9"]
    _post(url + "/api/dokumente", params={"buchung_id": bid}, files={"datei": ("a.pdf", PDF, "application/pdf")})
    page.goto(f"{url}/konten/{konten['Giro']}")
    bereit(page, "konto")
    tid(page, f"buchung-{bid}").click(button="right")
    expect(tid(page, "km-dokument-anhaengen")).to_be_visible()
    expect(tid(page, "km-dokument-foto")).to_have_count(0)
    tid(page, "km-dokumente-ansehen").click()
    expect(tid(page, "betrachter-pdf")).to_be_visible()


def test_mobil_kamera_knopf(tmp_path, browser):  # noqa: F811
    _daten(tmp_path)
    with server(tmp_path, daten=False) as (url, _), seite(browser, url, **HANDY) as page:
        konten = {k["name"]: k["id"] for k in _get(url + "/api/konten")}
        bid = _get(url + "/api/buchungen", konto_id=konten["Giro"], pro_seite=1)["eintraege"][0]["id"]
        page.goto(f"{url}/konten/{konten['Giro']}")
        bereit(page, "konto")
        tid(page, f"buchung-{bid}").click(button="right")
        expect(tid(page, "km-dokument-foto")).to_be_visible()
        with page.expect_file_chooser() as fc:
            tid(page, "km-dokument-foto").click()
        eingabe = fc.value.element
        assert eingabe.get_attribute("capture") == "environment" and eingabe.get_attribute("accept") == "image/*"
        datei = tmp_path / "foto.png"
        datei.write_bytes(PNG)
        fc.value.set_files(str(datei))
        expect(tid(page, f"beleg-marke-{bid}")).to_be_visible()
        d = _get(url + f"/api/buchungen/{bid}")["belege"][0]
        assert _get(url + f"/api/dokumente/{d['id']}")["quelle"] == "kamera"


def test_nachtraeglich_verknuepfen_und_zur_buchung(umgebung):
    url, page, konten, zweck = umgebung
    a, b = zweck["Einkauf 10"], zweck["Einkauf 11"]
    d = _post(url + "/api/dokumente", params={"buchung_id": a}, files={"datei": ("r.pdf", PDF, "application/pdf")}).json()
    _oeffnen(page, url, konten["Giro"], a)
    tid(page, f"dokument-ansehen-{d['id']}").click()
    abschnitt = tid(page, "betrachter-buchungen")
    expect(abschnitt).to_have_attribute("data-anzahl", "1")
    tid(page, "betrachter-verknuepfen").click()
    tid(page, "verknuepfen-suche").fill("Einkauf 11")
    expect(tid(page, f"verknuepfen-buchung-{a}")).to_have_count(0)
    tid(page, f"verknuepfen-buchung-{b}").check()
    tid(page, "verknuepfen-ok").click()
    expect(tid(page, "verknuepfen-dialog")).to_have_count(0)
    expect(abschnitt).to_have_attribute("data-anzahl", "2")
    assert _get(url + f"/api/dokumente/{d['id']}")["buchung_ids"] == sorted([a, b])
    expect(tid(page, f"beleg-marke-{b}")).to_be_visible()
    # zur anderen Buchung springen: Betrachter schließt, Buchung ist gewählt
    tid(page, f"betrachter-zur-buchung-{b}").click()
    expect(tid(page, "dokument-betrachter")).to_have_count(0)
    expect(tid(page, f"buchung-{b}")).to_have_attribute("aria-selected", "true")
