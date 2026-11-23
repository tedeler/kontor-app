"""M18: Oberfläche der Dokumente (oberflaeche.md 28, E-209) – Playwright wie M8; nicht kern.

Daten werden über REST angelegt; Wirkungen werden über REST und das Änderungsprotokoll geprüft.
"""

from __future__ import annotations

import base64
import re

import pytest

from tests.hilfen import m8
from tests.hilfen.m6 import EINS, abruf, nachrichten, postfach
from tests.hilfen.m8 import ausgewaehlt, oeffnen, strg, tid, warte_bis, warte_liste, zeile
from tests.hilfen.m15 import text_normal
from tests.hilfen.m17 import menue_eintraege
from tests.hilfen.m18 import (MAIL, PDF, anhaengen, belege, dokument, jpeg_masse, mail, mock_datei, pdf, png)

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

#: aria-label der Marke (28.1, E-209): wörtlich „<n> Dokument(e) ansehen“ oder mit ausgeschriebener Mehrzahl
ARIA_1 = re.compile(r"^1 Dokument(\(e\))? ansehen$")
ARIA_2 = re.compile(r"^2 Dokument(\(e\)|e) ansehen$")
ERFOLG = '[data-testid="meldung"][data-art="erfolg"]'
FEHLER = '[data-testid="meldung"][data-art="fehler"]'
MAILS = [
    {"nachricht_id": "M-1", "postfach": EINS, "empfangen": "2024-06-01T08:15:00Z",
     "absender": "Fiktiver Shop <shop@example.invalid>", "betreff": "Ihre Bestellung (fiktiv)", "text": "Danke."},
    {"nachricht_id": "M-2", "postfach": EINS, "empfangen": "2024-06-05T08:15:00Z",
     "absender": "Bezahldienst <service@example.invalid>", "betreff": "", "text": "Zahlung."},
    {"nachricht_id": "M-3", "postfach": EINS, "empfangen": "2024-06-03T08:15:00Z",
     "absender": "Buchladen <buch@example.invalid>", "betreff": "Rechnung Buch (fiktiv)", "text": "Rechnung."},
]


def _daten(api) -> dict:
    k = {"giro": api.konto("Girokonto")["id"], "leb": api.konto("Lebensmittel", "aufwand")["id"]}
    b = [api.buchung(f"2024-06-0{i}", [(k["giro"], -100 * i), (k["leb"], 100 * i)], verwendungszweck=f"Einkauf {i}")
         ["id"] for i in range(1, 5)]
    return {"k": k, "b": b}


def _start(starte_server, neue_seite, geraet="desktop", **felder):
    server = starte_server(**felder)
    d = _daten(server.api)
    return server, server.api, d


def _konto(seite, server, api, kid):
    oeffnen(seite, server, f"/konten/{kid}", seitenname="konto")
    warte_liste(seite, m8.rest_liste(api, kid))


def _meldung(seite, art=ERFOLG):
    return tid(seite, "meldungen").locator(art).last


def _aenderungen(api, a0, aktion):
    return [a for a in m8.aenderungen_seit(api, a0) if a["aktion"] == aktion]


def _drop(seite, bid: int, dateien: list[tuple[str, bytes, str]] | None, text: str | None = None) -> str | None:
    """dragenter/dragover/drop mit einem DataTransfer (oberflaeche.md 28.6); liefert data-ablage nach dragover."""
    js = """([sel, dateien, text]) => {
        const el = document.querySelector(sel);
        const dt = new DataTransfer();
        for (const [name, b64, typ] of (dateien || [])) {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            dt.items.add(new File([bytes], name, {type: typ}));
        }
        if (text) dt.setData('text/plain', text);
        const opt = {bubbles: true, cancelable: true, dataTransfer: dt};
        el.dispatchEvent(new DragEvent('dragenter', opt));
        el.dispatchEvent(new DragEvent('dragover', opt));
        const ablage = el.getAttribute('data-ablage');
        el.dispatchEvent(new DragEvent('drop', opt));
        return ablage;
    }"""
    liste = [(n, base64.b64encode(b).decode(), t) for n, b, t in (dateien or [])]
    return seite.evaluate(js, [f'[data-testid="buchung-{bid}"]', liste, text])


# ------------------------------------------------------------------ Marke und Betrachter (28.1, 28.4)


def test_marke_und_betrachter_pdf_bild(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1, b2, b3, _ = d["b"]
    p = anhaengen(api, [b1], "beleg.pdf", pdf())
    q = anhaengen(api, [b1], "foto.png", png(30, 20))
    r = anhaengen(api, [b2], "einzeln.pdf", pdf("2"))
    seite = neue_seite(server)
    _konto(seite, server, api, d["k"]["giro"])
    marke = tid(seite, f"beleg-marke-{b1}")
    expect(marke).to_have_text("📎2")
    expect(marke).to_have_attribute("data-anzahl", "2")
    expect(marke).to_have_attribute("aria-label", ARIA_2)
    assert marke.get_attribute("title") == "beleg.pdf\nfoto.png"
    assert zeile(seite, b1).locator('[data-feld="verwendungszweck"]').get_by_test_id(f"beleg-marke-{b1}").count() == 1
    expect(tid(seite, f"beleg-marke-{b2}")).to_have_text("📎")
    expect(tid(seite, f"beleg-marke-{b2}")).to_have_attribute("aria-label", ARIA_1)
    assert tid(seite, f"beleg-marke-{b3}").count() == 0, "ohne Dokumente keine Marke"
    assert marke.get_attribute("draggable") != "true", "die Marke ist kein Ziehgriff"
    marke.click()
    bt = tid(seite, "dokument-betrachter")
    expect(bt).to_be_visible()
    expect(bt).to_have_attribute("data-dokument-id", str(p["id"]))
    expect(bt).to_have_attribute("data-typ", PDF)
    assert bt.get_attribute("role") == "dialog"
    expect(bt).to_contain_text("beleg.pdf")
    expect(tid(seite, "betrachter-pdf")).to_have_attribute("src", f"/api/dokumente/{p['id']}/inhalt")
    expect(tid(seite, "betrachter-zaehler")).to_have_text(re.compile(r"^\s*1\s*/\s*2\s*$"))
    lade = tid(seite, "betrachter-herunterladen")
    assert lade.get_attribute("href").endswith(f"/api/dokumente/{p['id']}/inhalt?herunterladen=true")
    assert lade.get_attribute("download") is not None
    tid(seite, "betrachter-naechstes").click()
    expect(bt).to_have_attribute("data-dokument-id", str(q["id"]))
    bild = tid(seite, "betrachter-bild")
    expect(bild).to_have_attribute("src", re.compile(rf"/api/dokumente/{q['id']}/inhalt$"))
    expect(bild).to_have_attribute("alt", "foto.png")
    expect(tid(seite, "betrachter-zaehler")).to_have_text(re.compile(r"^\s*2\s*/\s*2\s*$"))
    bild.click()
    expect(bild).to_have_class(re.compile(r"\bgross\b"))
    bild.click()
    expect(bild).not_to_have_class(re.compile(r"\bgross\b"))
    tid(seite, "betrachter-schliessen").focus()
    seite.keyboard.press("ArrowRight")
    expect(bt).to_have_attribute("data-dokument-id", str(p["id"])), "zyklisch"
    seite.keyboard.press("ArrowLeft")
    expect(bt).to_have_attribute("data-dokument-id", str(q["id"]))
    tid(seite, "betrachter-voriges").click()
    expect(bt).to_have_attribute("data-dokument-id", str(p["id"]))
    tid(seite, "betrachter-schliessen").click()
    expect(bt).to_be_hidden()
    tid(seite, f"beleg-marke-{b2}").click()
    expect(bt).to_have_attribute("data-dokument-id", str(r["id"]))
    expect(tid(seite, "betrachter-zaehler")).to_be_hidden()
    expect(tid(seite, "betrachter-naechstes")).to_be_hidden()
    tid(seite, "betrachter-schliessen").click()


# ------------------------------------------------------------------ Einzelheiten und Anhängen (28.2)


def test_details_anhaengen_loesen_rueckgaengig(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1 = d["b"][0]
    seite = neue_seite(server, erfolgsmeldung=True)   # Erfolgsmeldung ab M32 nur mit Einstellung (E-307)
    _konto(seite, server, api, d["k"]["giro"])
    zeile(seite, b1).click()
    ab = tid(seite, "details-dokumente")
    expect(ab).to_have_attribute("data-buchung-id", str(b1))
    expect(ab).to_have_attribute("data-anzahl", "0")
    expect(ab).to_contain_text("Dokumente")
    expect(ab).to_contain_text("Keine Dokumente. Datei hierher ziehen oder anhängen.")
    assert tid(seite, "dokument-foto").count() == 0 or not tid(seite, "dokument-foto").is_visible(), "nur mobil"
    expect(tid(seite, "dokument-anhaengen")).to_have_text(re.compile("Datei anhängen"))
    a0 = m8.max_aenderung(api)
    with seite.expect_file_chooser() as fc:
        tid(seite, "dokument-anhaengen").click()
    # die Dateiauswahl ist ein verstecktes <input type="file"> (E-209: darf beim Klick entstehen)
    eingabe = fc.value.element
    assert eingabe.get_attribute("data-testid") == "dokument-datei-eingabe"
    assert eingabe.get_attribute("type") == "file" and fc.value.is_multiple()
    accept = (eingabe.get_attribute("accept") or "").lower()
    for teil in ("pdf", "eml", "png", "webp"):
        assert teil in accept, (teil, accept)
    assert "jpeg" in accept or "jpg" in accept
    fc.value.set_files([{"name": "rechnung.pdf", "mimeType": "application/pdf", "buffer": pdf("R")},
                        {"name": "falsch.gif", "mimeType": "image/gif", "buffer": b"GIF89a\x01\x00"},
                        {"name": "foto.png", "mimeType": "image/png", "buffer": png(3, 3)}])
    warte_bis(lambda: len(belege(api, b1)) == 2, text="zwei Dokumente hochgeladen")
    expect(_meldung(seite, FEHLER)).to_be_visible()
    neu = _aenderungen(api, a0, "dokument_anhaengen")
    assert len(neu) == 2, "je Datei eine eigene Änderung"
    ids = [x["id"] for x in belege(api, b1)]
    assert {dokument(api, i)["quelle"] for i in ids} == {"upload"}
    expect(ab).to_have_attribute("data-anzahl", "2")
    for i in ids:
        expect(tid(seite, f"details-dokument-{i}")).to_be_visible()
    namen = {dokument(api, i)["dateiname"]: i for i in ids}
    tid(seite, f"dokument-loesen-{namen['foto.png']}").click()
    expect(_meldung(seite)).to_contain_text("„foto.png“ entfernt.")
    warte_bis(lambda: len(belege(api, b1)) == 1, text="gelöst")
    seite.keyboard.press(f"{strg()}+z")
    warte_bis(lambda: len(belege(api, b1)) == 2, text="Rückgängig stellt das Dokument wieder her")
    expect(ab).to_have_attribute("data-anzahl", "2")
    # Lösen eines geteilten Dokuments: Meldung „von der Buchung gelöst“
    api.post(f"/api/dokumente/{namen['rechnung.pdf']}/buchungen", json={"buchung_ids": [d["b"][1]]}, erwartet=200)
    seite.reload()
    expect(tid(seite, "app")).to_have_attribute("data-bereit", "ja")
    zeile(seite, b1).click()
    tid(seite, f"dokument-loesen-{namen['rechnung.pdf']}").click()
    expect(_meldung(seite)).to_contain_text("„rechnung.pdf“ von der Buchung gelöst.")
    tid(seite, f"dokument-ansehen-{namen['foto.png']}").click()
    expect(tid(seite, "dokument-betrachter")).to_have_attribute("data-dokument-id", str(namen["foto.png"]))
    tid(seite, "betrachter-schliessen").click()


# ------------------------------------------------------------------ E-Mail anhängen (28.3)


def test_mail_auswahl_dialog(starte_server, neue_seite, tmp_path):
    datei = mock_datei(tmp_path / "mails.json", MAILS, [EINS])
    server, api, d = _start(starte_server, neue_seite, mock_daten=datei, mail_erstabruf_tage=365)
    b1 = d["b"][0]
    seite = neue_seite(server)
    _konto(seite, server, api, d["k"]["giro"])
    zeile(seite, b1).click()
    tid(seite, "dokument-mail").click()
    dlg = tid(seite, "mail-auswahl-dialog")
    expect(dlg).to_be_visible()
    expect(dlg).to_contain_text("Keine abgerufenen E-Mails. Postfächer richtest du unter Einstellungen ein.")
    tid(seite, "mail-auswahl-abbrechen").click()
    expect(dlg).to_be_hidden()
    postfach(api, EINS)
    abruf(api)
    n = {x["nachricht_id"]: x["id"] for x in nachrichten(api)}
    tid(seite, "dokument-mail").click()
    expect(dlg).to_be_visible()
    liste = tid(seite, "mail-auswahl-liste")
    assert liste.get_attribute("role") == "listbox"
    expect(liste.locator('[role="option"]')).to_have_count(3)
    ids = [int(x) for x in liste.locator('[role="option"]').evaluate_all(
        "els => els.map(e => e.getAttribute('data-testid').slice('mail-auswahl-'.length))")]
    assert ids == [n["M-2"], n["M-3"], n["M-1"]], "neueste zuerst"
    expect(tid(seite, f"mail-auswahl-{n['M-2']}")).to_contain_text("(ohne Betreff)")
    tid(seite, "mail-auswahl-suche").fill("BUCHLADEN")
    expect(liste.locator('[role="option"]:visible')).to_have_count(1)
    expect(tid(seite, f"mail-auswahl-{n['M-3']}")).to_be_visible()
    tid(seite, "mail-auswahl-suche").fill("gibt es nicht")
    expect(dlg).to_contain_text("Keine passende E-Mail.")
    tid(seite, "mail-auswahl-suche").fill("bestellung")
    tid(seite, f"mail-auswahl-{n['M-1']}").click()
    expect(dlg).to_be_hidden()
    warte_bis(lambda: len(belege(api, b1)) == 1, text="Mail angehängt")
    doc = dokument(api, belege(api, b1)[0]["id"])
    assert (doc["quelle"], doc["mime_typ"], doc["dateiname"]) == ("mail", MAIL, "Ihre Bestellung (fiktiv).eml")
    # Tastatur: Enter auf einem Eintrag
    zeile(seite, d["b"][1]).click()
    tid(seite, "dokument-mail").click()
    tid(seite, f"mail-auswahl-{n['M-3']}").focus()
    seite.keyboard.press("Enter")
    expect(dlg).to_be_hidden()
    warte_bis(lambda: len(belege(api, d["b"][1])) == 1, text="Mail per Enter angehängt")


# ------------------------------------------------------------------ Kontextmenü (28.5)


def test_kontextmenue_dokumente(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1, b2, b3, _ = d["b"]
    p = anhaengen(api, [b1], "beleg.pdf", pdf())
    seite = neue_seite(server)
    _konto(seite, server, api, d["k"]["giro"])
    zeile(seite, b2).click(button="right")
    eintraege = menue_eintraege(seite)
    i = eintraege.index("km-gegenbuchung")
    assert eintraege[i + 1:i + 4] == ["km-dokument-anhaengen", "km-dokument-mail", "km-dokumente-ansehen"], eintraege
    assert "km-dokument-foto" not in eintraege, "nur mobil"
    if "km-verschieben" in eintraege:
        assert eintraege.index("km-verschieben") == i + 4
    km = tid(seite, "kontextmenue")
    expect(km.get_by_test_id("km-dokument-anhaengen")).to_have_text(re.compile("Dokument anhängen"))
    expect(km.get_by_test_id("km-dokument-mail")).to_have_text(re.compile("E-Mail anhängen"))
    expect(km.get_by_test_id("km-dokumente-ansehen")).to_have_attribute("aria-disabled", "true")
    seite.keyboard.press("Escape")
    zeile(seite, b1).click(button="right")
    ansehen = tid(seite, "kontextmenue").get_by_test_id("km-dokumente-ansehen")
    assert ansehen.get_attribute("aria-disabled") != "true"
    ansehen.click()
    expect(tid(seite, "dokument-betrachter")).to_have_attribute("data-dokument-id", str(p["id"]))
    tid(seite, "betrachter-schliessen").click()
    # zwei gewählte Buchungen: Ansehen gesperrt, Anhängen an alle gewählten (ein Dokument)
    zeile(seite, b2).click()
    zeile(seite, b3).click(modifiers=[strg()])
    assert ausgewaehlt(seite) == {b2, b3}
    zeile(seite, b3).click(button="right")
    km = tid(seite, "kontextmenue")
    expect(km.get_by_test_id("km-dokumente-ansehen")).to_have_attribute("aria-disabled", "true")
    with seite.expect_file_chooser() as fc:
        km.get_by_test_id("km-dokument-anhaengen").click()
    fc.value.set_files([{"name": "gemeinsam.png", "mimeType": "image/png", "buffer": png(2, 2)}])
    warte_bis(lambda: belege(api, b2) and belege(api, b3), text="an beide gewählten angehängt")
    (x,) = belege(api, b2)
    assert belege(api, b3) == [x] and dokument(api, x["id"])["buchung_ids"] == sorted([b2, b3])


# ------------------------------------------------------------------ Betrachter für Mails, Hängt an, Verknüpfen


def test_betrachter_mail_haengt_an_verknuepfen(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1, b2, b3, b4 = d["b"]
    roh = mail(betreff="Rechnung (fiktiv)", text="Textfassung der Rechnung\n",
               html="<html><body><p>Formatierte Rechnung</p></body></html>",
               anhaenge=[("rechnung.pdf", PDF, pdf("anhang")), ("daten.bin", "application/octet-stream", b"\x01\x02")])
    m = anhaengen(api, [b1, b2], "", roh)
    struktur = api.get(f"/api/dokumente/{m['id']}/mail", erwartet=200).daten
    nr_pdf = next(a["nr"] for a in struktur["anhaenge"] if a["mime_typ"] == PDF)
    nr_bin = next(a["nr"] for a in struktur["anhaenge"] if a["dateiname"] == "daten.bin")
    seite = neue_seite(server)
    _konto(seite, server, api, d["k"]["giro"])
    tid(seite, f"beleg-marke-{b1}").click()
    bt = tid(seite, "dokument-betrachter")
    expect(bt).to_have_attribute("data-typ", MAIL)
    expect(tid(seite, "betrachter-mail")).to_be_visible()
    expect(tid(seite, "mail-von")).to_contain_text("shop@example.invalid")
    expect(tid(seite, "mail-betreff")).to_contain_text("Rechnung (fiktiv)")
    rahmen = tid(seite, "mail-html")
    expect(rahmen).to_have_attribute("src", re.compile(rf"/api/dokumente/{m['id']}/mail/html$"))
    assert set(rahmen.get_attribute("sandbox").split()) == {"allow-popups", "allow-popups-to-escape-sandbox"}
    assert rahmen.get_attribute("referrerpolicy") == "no-referrer"
    um = tid(seite, "mail-ansicht-umschalten")
    expect(um).to_have_text(re.compile("Als Text zeigen"))
    um.click()
    expect(tid(seite, "mail-text")).to_contain_text("Textfassung der Rechnung")
    expect(um).to_have_text(re.compile("Formatiert zeigen"))
    expect(tid(seite, f"mail-anhang-{nr_pdf}")).to_be_visible()
    expect(tid(seite, f"mail-anhang-laden-{nr_bin}")).to_have_text(re.compile("Herunterladen"))
    assert tid(seite, f"mail-anhang-ansehen-{nr_bin}").count() == 0, "nur bei PDF/Bildern"
    hängt = tid(seite, "betrachter-buchungen")
    expect(hängt).to_have_attribute("data-anzahl", "2")
    expect(hängt).to_contain_text("Hängt an 2 Buchungen")
    tid(seite, f"mail-anhang-ansehen-{nr_pdf}").click()
    expect(tid(seite, "betrachter-pdf")).to_have_attribute(
        "src", re.compile(rf"/api/dokumente/{m['id']}/mail/anhaenge/{nr_pdf}$"))
    expect(tid(seite, "betrachter-buchungen")).to_be_hidden()
    expect(tid(seite, "betrachter-naechstes")).to_be_hidden()
    tid(seite, "betrachter-zur-mail").click()
    expect(tid(seite, "betrachter-mail")).to_be_visible()
    # lösen
    tid(seite, f"betrachter-loesen-{b2}").click()
    expect(tid(seite, "betrachter-buchungen")).to_have_attribute("data-anzahl", "1")
    expect(tid(seite, "betrachter-buchungen")).to_contain_text("Hängt an 1 Buchung")
    warte_bis(lambda: dokument(api, m["id"])["buchung_ids"] == [b1], text="gelöst")
    # verknüpfen
    tid(seite, "betrachter-verknuepfen").click()
    v = tid(seite, "verknuepfen-dialog")
    expect(v).to_be_visible()
    tid(seite, "verknuepfen-suche").fill("Einkauf")
    expect(tid(seite, f"verknuepfen-buchung-{b4}")).to_be_visible()
    alt = tid(seite, f"verknuepfen-buchung-{b1}")
    expect(alt).to_be_checked()
    expect(alt).to_be_disabled()
    expect(v).to_contain_text("(schon verknüpft)")
    ok = tid(seite, "verknuepfen-ok")
    expect(ok).to_be_disabled()
    tid(seite, f"verknuepfen-buchung-{b3}").check()
    tid(seite, f"verknuepfen-buchung-{b4}").check()
    expect(ok).to_have_text(re.compile("Mit 2 Buchungen verknüpfen"))
    ok.click()
    expect(v).to_be_hidden()
    warte_bis(lambda: dokument(api, m["id"])["buchung_ids"] == sorted([b1, b3, b4]), text="verknüpft")
    expect(tid(seite, "betrachter-buchungen")).to_have_attribute("data-anzahl", "3")
    # zur Buchung springen
    tid(seite, f"betrachter-zur-buchung-{b4}").click()
    expect(bt).to_be_hidden()
    warte_bis(lambda: ausgewaehlt(seite) == {b4}, text="Buchung gewählt")


def test_letzte_verknuepfung_loesen_schliesst_betrachter(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1 = d["b"][0]
    p = anhaengen(api, [b1], "einzig.pdf", pdf())
    seite = neue_seite(server)
    _konto(seite, server, api, d["k"]["giro"])
    tid(seite, f"beleg-marke-{b1}").click()
    tid(seite, f"betrachter-loesen-{b1}").click()
    expect(tid(seite, "dokument-betrachter")).to_be_hidden()
    warte_bis(lambda: api.get(f"/api/dokumente/{p['id']}").status_code == 404, text="Dokument entfallen")
    expect(tid(seite, f"beleg-marke-{b1}")).to_have_count(0)


# ------------------------------------------------------------------ Dateien auf eine Zeile ziehen (28.6)


def test_dateien_auf_zeile_ziehen(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1, b2, b3, _ = d["b"]
    seite = neue_seite(server)
    _konto(seite, server, api, d["k"]["giro"])
    ablage = _drop(seite, b1, [("zettel.pdf", pdf("z"), "application/pdf")])
    assert ablage == "ja", "die Zeile trägt data-ablage=ja, solange sie Ziel ist"
    warte_bis(lambda: len(belege(api, b1)) == 1, text="Datei an die Zeile gehängt")
    expect(zeile(seite, b1)).not_to_have_attribute("data-ablage", "ja")
    # mehrere gewählt, Ziel gewählt → an alle gewählten
    zeile(seite, b2).click()
    zeile(seite, b3).click(modifiers=[strg()])
    _drop(seite, b3, [("a.png", png(), "image/png"), ("b.pdf", pdf("b"), "application/pdf")])
    warte_bis(lambda: len(belege(api, b2)) == 2 and len(belege(api, b3)) == 2, text="an alle gewählten")
    assert belege(api, b2) == belege(api, b3)
    # Ziehen ohne Dateien (Text) ist kein Datei-Ziehen: kein Upload (Hinweis „ohne Datei-Inhalt“ nicht geprüft,
    # E-209)
    a0 = m8.max_aenderung(api)
    assert _drop(seite, b1, None, text="nur Text") != "ja"
    seite.wait_for_timeout(300)
    assert len(belege(api, b1)) == 1 and m8.max_aenderung(api) == a0


# ------------------------------------------------------------------ Mobil (28.1, 28.2: Kamera)


def test_mobil_marke_und_kamera(starte_server, neue_seite):
    server, api, d = _start(starte_server, neue_seite)
    b1, b2, _, _ = d["b"]
    anhaengen(api, [b2], "beleg.pdf", pdf())
    seite = neue_seite(server, "handy")
    _konto(seite, server, api, d["k"]["giro"])
    marke = tid(seite, f"beleg-marke-{b2}")
    expect(marke).to_be_visible()
    assert zeile(seite, b2).locator('[data-feld="empfaenger"]').get_by_test_id(f"beleg-marke-{b2}").count() == 1, (
        "mobil am Ende der Empfängerzelle")
    m8.tippen(seite, zeile(seite, b1))
    foto = tid(seite, "dokument-foto")
    expect(foto).to_be_visible()
    expect(foto).to_have_text(re.compile("Foto aufnehmen"))
    gross = png(3000, 1000, (20, 160, 60))
    with seite.expect_file_chooser() as fc:
        foto.click()
    kamera = fc.value.element
    assert kamera.get_attribute("data-testid") == "dokument-kamera-eingabe"
    assert kamera.get_attribute("accept") == "image/*" and kamera.get_attribute("capture") == "environment"
    fc.value.set_files([{"name": "aufnahme.png", "mimeType": "image/png", "buffer": gross}])
    warte_bis(lambda: len(belege(api, b1)) == 1, text="Foto hochgeladen")
    doc = dokument(api, belege(api, b1)[0]["id"])
    assert (doc["quelle"], doc["mime_typ"]) == ("kamera", "image/jpeg"), "im Browser als JPEG verkleinert"
    breite, hoehe = jpeg_masse(api.get(f"/api/dokumente/{doc['id']}/inhalt", erwartet=200).content)
    assert max(breite, hoehe) == 2400 and abs(breite / hoehe - 3) < 0.01, (breite, hoehe)
    assert text_normal(tid(seite, "details-dokumente").text_content())
