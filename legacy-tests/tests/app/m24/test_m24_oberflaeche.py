"""M24: Kachel „Was kommt noch?“ auf der Finanzübersicht und Serien auf ``/erwartet`` (oberflaeche.md 34, E-236)
– Playwright wie M8; nicht kern."""

from __future__ import annotations

import re

import pytest

from tests.hilfen.m8 import oeffnen, tid, warte_geladen
from tests.hilfen.m16 import Abo
from tests.hilfen.m20 import liste, mock_datei
from tests.hilfen.m24 import summen

pytestmark = pytest.mark.browser
expect = pytest.importorskip("playwright.sync_api", reason="Browsertests übersprungen: Playwright fehlt").expect

GRUENDE = ["bestellung", "paypal", "rueckerstattung", "manuell"]


def _server(starte_server, tmp_path, *, abgleich=True):
    datei = mock_datei(tmp_path / "m24-browser.json", [])
    return starte_server(heute="2024-06-20", mock_daten=datei, mail_abgleich=abgleich, mail_erstabruf_tage=365)


def _serien(api) -> dict:
    a = Abo(api)
    emp = a.empfaenger("Streamingdienst (fiktiv)")
    a.buchen(emp, ["2024-03-05", "2024-04-05", "2024-05-06", "2024-06-05"], -999)
    verein = a.empfaenger("Sportverein Musterstadt (fiktiv)")
    a.buchen(verein, ["2023-08-15", "2023-11-15", "2024-02-15"], -3000)
    return {"giro": a.giro, "abo": f"{a.giro}:{emp}:ausgabe", "verein": f"{a.giro}:{verein}:ausgabe"}


def _manuell(api, betrag, **kw):
    return api.post("/api/erwartungen", json={"richtung": "ausgabe", "haendler": "Laden Beispiel (fiktiv)",
                                              "betrag": betrag, **kw}, erwartet=201).daten


def _betrag_attr(seite, element) -> list[str]:
    return seite.evaluate("""el => [el, ...el.querySelectorAll('[data-betrag]')].map(e => e.getAttribute('data-betrag'))
        .filter(x => x !== null)""", element.element_handle())


def _zeilen_id(sid: str) -> str:
    return "erwartung-" + re.sub(r"[^a-zA-Z0-9-]", "-", sid)


# ------------------------------------------------------------------ Kachel
def test_kachel_nur_mit_mail_abgleich(starte_server, neue_seite, tmp_path):
    server = _server(starte_server, tmp_path, abgleich=False)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    expect(tid(seite, "kachel-erwartet")).to_have_count(0)


def test_kachel_leer(starte_server, neue_seite, tmp_path):
    server = _server(starte_server, tmp_path)
    _serien(server.api)
    seite = neue_seite(server)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    k = tid(seite, "kachel-erwartet")
    expect(k).to_be_visible()
    assert k.evaluate("e => e.tagName") == "A" and k.get_attribute("href") == "/erwartet"
    expect(k).to_contain_text("Was kommt noch?")
    expect(k).to_contain_text("0 offen")
    expect(k).not_to_contain_text("überfällig")
    assert _betrag_attr(seite, k) == ["0"], "Serien zählen in der Kachel nicht"


@pytest.mark.parametrize("geraet", ["desktop", "handy"])
def test_kachel_zahlen_und_klick(starte_server, neue_seite, tmp_path, geraet):
    server = _server(starte_server, tmp_path)
    api = server.api
    _serien(api)
    _manuell(api, 1234, datum="2024-06-01", frist="2024-06-10")
    _manuell(api, 500, datum="2024-06-18", frist="2024-06-30")
    soll = liste(api, grund=GRUENDE)
    anzahl, summe, ueber = summen(soll["eintraege"])
    assert (anzahl, summe, ueber) == (2, -1734, 1)
    seite = neue_seite(server, geraet)
    oeffnen(seite, server, "/", seitenname="uebersicht")
    k = tid(seite, "kachel-erwartet")
    expect(k).to_contain_text("2 offen")
    expect(k).to_contain_text("1 überfällig")
    assert _betrag_attr(seite, k) == [str(summe)]
    lage = k.evaluate("""k => { const s = document.querySelector('[data-testid="seite-uebersicht"]');
        const alle = [...s.querySelectorAll('*')].filter(e => e.offsetParent !== null && !k.contains(e) && e !== k);
        return alle.filter(e => !!(k.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING)
                         && !e.contains(k)).length; }""")
    assert lage == 0, "Kachel am Ende der Seite"
    k.click()
    warte_geladen(seite, "erwartet")
    assert seite.url.split("?")[0].endswith("/erwartet")
