"""M32: Mail-Liste mit Suche, Zuordnen von Hand, Gruppen und Betrag; Bilder fremder Server in der Mail-Ansicht
(sammel3.md 8; D-226 bis D-229, D-236/9; E-299, E-300) – kern.

Mails aus einer Mock-Datendatei je Test (``m20.app``); welche Mail passt und welche Gruppen entstehen, rechnet
der Test selbst aus.
"""

from __future__ import annotations

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.m6 import abruf, nachrichten
from tests.hilfen.m18 import CSP_MAIL, MAIL, PDF, anhaengen, csp_menge, dokumente_der_buchung, mail, operation, pdf, \
    rundreise
from tests.hilfen.m20 import AMAZON, NR, app, ausgabe, konten, nachricht

pytestmark = pytest.mark.kern
SHOP = "Fiktiver Shop <shop@example.invalid>"
BESTAND = ("girokonto", "sparkonto", "kreditkonto")


def _ids(liste: list[dict]) -> list[int]:
    return [m["id"] for m in liste]


def _nach_betreff(api) -> dict[str, dict]:
    return {m["betreff"]: m for m in nachrichten(api)}


def _zuordnen(api, mid: int, bid, erwartet=201):
    r = api.post(f"/api/mail/nachrichten/{mid}/buchung", json={"buchung_id": bid}, erwartet=erwartet)
    return r.daten if erwartet == 201 else r


def _bestandsbetrag(api, bid: int) -> int:
    bestand = {k["id"] for k in api.konten() if k["art"] in BESTAND}
    return sum(s["betrag"] for s in api.buchung_lesen(bid)["splits"] if s["konto_id"] in bestand)


# ------------------------------------------------------------------ 8.1 Suche

SUCHMAILS = [
    nachricht(SHOP, "Rechnung März", "Betrag 12,00 €", "2024-06-01T08:00:00Z"),
    nachricht("Verein Beispiel <info@verein.example.invalid>", "Grüße", "Hallo Frau Müller", "2024-06-02T08:00:00Z"),
    nachricht("Bank Beispiel <info@bank.example.invalid>", "Bestellung", "Rechnung folgt", "2024-06-03T08:00:00Z"),
]


@pytest.mark.parametrize("suche,betreffe", [
    ("rechnung", {"Rechnung März", "Bestellung"}),
    ("RECHNUNG maerz", {"Rechnung März"}),              # jedes Wort, Umlaut wie norm
    ("müller", {"Grüße"}),
    ("muell", {"Grüße"}),
    ("shop rechnung", {"Rechnung März"}),               # Wörter in verschiedenen Feldern
    ("shop folgt", set()),
    ("  ", {"Rechnung März", "Grüße", "Bestellung"}),   # leer filtert nicht (E-299)
])
def test_suche(tmp_path, suche, betreffe):
    api = app(tmp_path, SUCHMAILS)
    abruf(api)
    ist = nachrichten(api, suche=suche)
    assert {m["betreff"] for m in ist} == betreffe
    seite = api.get("/api/mail/nachrichten", params={"suche": suche}, erwartet=200).daten
    assert seite["gesamt"] == len(betreffe)
    assert seite["stand"]["gesamt"] == len(SUCHMAILS), "stand ohne suche (E-299)"


def test_suche_mit_anderen_filtern(tmp_path):
    api = app(tmp_path, SUCHMAILS)
    abruf(api)
    assert {m["betreff"] for m in nachrichten(api, suche="rechnung", zuordnung="keine")} == {"Rechnung März",
                                                                                        "Bestellung"}
    assert nachrichten(api, suche="rechnung", zuordnung="zugeordnet") == []
    neueste = nachrichten(api, suche="rechnung", reihenfolge="neueste")
    assert [m["betreff"] for m in neueste] == ["Bestellung", "Rechnung März"]


# ------------------------------------------------------------------ 8.2/8.3 Zuordnen von Hand


def test_zuordnen_von_hand(tmp_path):
    api = app(tmp_path, SUCHMAILS, abgleich=False)
    abruf(api)
    k = konten(api)
    bid = ausgabe(api, k, "2024-06-01", 1200, "Kartenzahlung")
    m = _nach_betreff(api)["Rechnung März"]
    assert "angehaengt" not in m, "ohne Zuordnung und ohne mail_bestellnummer kein Feld"
    d, a, v, n = operation(api, "dokument_aus_mail", lambda: _zuordnen(api, m["id"], bid))
    assert (d["quelle"], d["mime_typ"]) == ("mail", MAIL) and bid in d["buchung_ids"]
    assert [x["id"] for x in dokumente_der_buchung(api, bid)] == [d["id"]]
    m2 = _nach_betreff(api)["Rechnung März"]
    (x,) = m2["angehaengt"]
    assert (x["id"], x["nummer"], x["datum"], x["konto_id"]) == (bid, "", "2024-06-01", k["giro"])
    assert x["betrag"] == _bestandsbetrag(api, bid) == -1200 and x["warum"]
    assert _ids(nachrichten(api, zuordnung="zugeordnet")) == [m["id"]]
    assert m["id"] not in _ids(nachrichten(api, zuordnung="keine"))
    assert api.get("/api/mail/nachrichten", erwartet=200).daten["stand"]["zugeordnet"] == 1
    # zweiter Aufruf: kein zweites Dokument
    _zuordnen(api, m["id"], bid)
    assert len(dokumente_der_buchung(api, bid)) == 1
    # Lösen hebt die Zuordnung auf
    api.delete(f"/api/dokumente/{d['id']}/buchungen/{bid}", erwartet=200)
    assert m["id"] in _ids(nachrichten(api, zuordnung="keine"))
    assert api.get("/api/mail/nachrichten", erwartet=200).daten["stand"]["zugeordnet"] == 0


def test_zuordnen_von_hand_rundreise(tmp_path):
    api = app(tmp_path, SUCHMAILS, abgleich=False)
    abruf(api)
    bid = ausgabe(api, konten(api), "2024-06-02", 500, "Beitrag")
    m = _nach_betreff(api)["Grüße"]
    _, a, v, n = operation(api, "dokument_aus_mail", lambda: _zuordnen(api, m["id"], bid))
    rundreise(api, a, v, n)


def test_zuordnen_pruefreihenfolge(tmp_path):
    api = app(tmp_path, SUCHMAILS, abgleich=False)
    abruf(api)
    bid = ausgabe(api, konten(api), "2024-06-02", 500, "Beitrag")
    mid = nachrichten(api)[0]["id"]
    assert fehlercode(_zuordnen(api, 999999, bid, erwartet=404)) == "nicht_gefunden"
    assert fehlercode(api.post("/api/mail/nachrichten/999999/buchung", json={}, erwartet=404)) == "nicht_gefunden"
    for koerper in ({}, {"buchung_id": "1"}, {"buchung_id": True}, {"buchung_id": bid, "x": 1}, [bid]):
        r = api.post(f"/api/mail/nachrichten/{mid}/buchung", json=koerper, erwartet=422)
        assert fehlercode(r) == "validierung", koerper
    assert fehlercode(_zuordnen(api, mid, 999999, erwartet=404)) == "nicht_gefunden"
    assert dokumente_der_buchung(api, bid) == []


def test_betrag_bei_bestellnummer(tmp_path):
    """8.3: auch über die Bestellnummer angehängte Buchungen tragen ``betrag`` (Bestandskonten, mit Vorzeichen)."""
    mails = [nachricht(AMAZON, f"Bestellung {NR} versandt", "Unterwegs.", "2024-06-03T08:00:00Z")]
    api = app(tmp_path, mails, abgleich=False, mail_bestellnummer=True)
    k = konten(api)
    bid = api.buchung("2024-06-02", [(k["giro"], -1999), (k["spar"], 500), (k["einkauf"], 1499)],
                      verwendungszweck=f"AMAZON {NR}")["id"]
    abruf(api)
    (m,) = nachrichten(api)
    (x,) = m["angehaengt"]
    assert x["id"] == bid and x["nummer"] == NR and x["betrag"] == -1499


# ------------------------------------------------------------------ 8.4 Gruppen


def _gruppen_app(tmp_path):
    """A, B: gleiche Bestellnummer (eine Buchung); C, D: von Hand derselben Buchung zugeordnet; E: eigene Nummer
    (allein); X: ohne Zuordnung. Empfangen in der Reihenfolge A, X, C, B, D, E."""
    nr2 = "306-1111111-2222222"
    mails = {"A": nachricht(AMAZON, f"Bestellung {NR}", "a", "2024-06-01T08:00:00Z"),
             "X": nachricht(SHOP, "Newsletter", "x", "2024-06-02T08:00:00Z"),
             "C": nachricht(SHOP, "Rechnung", "c", "2024-06-03T08:00:00Z"),
             "B": nachricht(AMAZON, f"Versand {NR}", "b", "2024-06-04T08:00:00Z"),
             "D": nachricht(SHOP, "Mahnung", "d", "2024-06-05T08:00:00Z"),
             "E": nachricht(AMAZON, f"Bestellung {nr2}", "e", "2024-06-06T08:00:00Z")}
    # W-022 (E-313): App-Uhr nach der letzten Mail, sonst liefert das Mock-Mail-Plugin sie noch nicht
    api = app(tmp_path, list(mails.values()), heute="2024-06-20", abgleich=False, mail_bestellnummer=True)
    k = konten(api)
    ausgabe(api, k, "2024-06-01", 4990, f"AMAZON {NR}")
    ausgabe(api, k, "2024-06-06", 990, f"AMAZON {nr2}")
    hand = ausgabe(api, k, "2024-06-03", 2500, "Rechnung Shop")
    abruf(api)
    b = _nach_betreff(api)
    i = {n: b[m["betreff"]]["id"] for n, m in mails.items()}
    for n in ("C", "D"):
        _zuordnen(api, i[n], hand)
    return api, i


def _gruppiert(api, **params):
    return nachrichten(api, gruppieren="ja", **params)


def _pruefe(g: list[dict], i: dict, folge: str, gruppen: dict[str, str]) -> None:
    namen = {v: n for n, v in i.items()}
    assert "".join(namen[m["id"]] for m in g) == folge
    for m in g:
        n = namen[m["id"]]
        if n in gruppen:
            assert m["gruppe"] == i[gruppen[n]], (n, m["gruppe"])
        else:
            assert m["gruppe"] in (None, m["id"]), "Mail ohne weitere Mail der Gruppe (E-299)"


def test_gruppieren_aelteste(tmp_path):
    api, i = _gruppen_app(tmp_path)
    ohne = nachrichten(api)
    assert all("gruppe" not in m for m in ohne), "ohne Parameter kein Feld gruppe"
    assert _ids(ohne) == [i[n] for n in "AXCBDE"], "ohne Parameter Reihenfolge wie bisher"
    assert _ids(nachrichten(api, gruppieren="nein")) == _ids(ohne)
    _pruefe(_gruppiert(api), i, "ABXCDE", {"A": "A", "B": "A", "C": "C", "D": "C"})
    assert api.get("/api/mail/nachrichten", params={"gruppieren": "ja"}, erwartet=200).daten["gesamt"] == 6


def test_gruppieren_neueste_und_filter(tmp_path):
    api, i = _gruppen_app(tmp_path)
    _pruefe(_gruppiert(api, reihenfolge="neueste"), i, "EDCBAX", {"D": "D", "C": "D", "B": "B", "A": "B"})
    _pruefe(_gruppiert(api, zuordnung="zugeordnet"), i, "ABCDE", {"A": "A", "B": "A", "C": "C", "D": "C"})
    for falsch in ("vielleicht", "1", ""):
        r = api.get("/api/mail/nachrichten", params={"gruppieren": falsch}, erwartet=422)
        assert fehlercode(r) == "validierung", falsch


# ------------------------------------------------------------------ 8.5 Bilder fremder Server

HTML = ('<html><body><p>Ihre Rechnung</p>'
        '<img src="https://bilder.example.invalid/logo.png" srcset="https://srcset.example.invalid/x.png 2x">'
        '<img src="//cdn.example.invalid/banner.png">'
        '<img src="data:image/png;base64,iVBORw0KGgo=">'
        '<script>alert(1)</script></body></html>')


def _konto(api, name: str, art: str) -> int:
    """Vorhandenes Konto wiederverwenden (Kontonamen je Ebene eindeutig, W-023/E-313)."""
    for k in api.konten():
        if k["name"] == name and k["art"] == art and k["eltern_id"] is None:
            return k["id"]
    return api.konto(name, art)["id"]


def _mail_dokument(api, html: str | None = HTML) -> dict:
    giro = _konto(api, "Giro", "girokonto")
    kat = _konto(api, "Einkauf", "aufwand")
    bid = api.buchung("2024-06-03", [(giro, -100), (kat, 100)])["id"]
    return anhaengen(api, [bid], "r.eml", mail(html=html))


def test_bilder_nur_auf_wunsch(api, netz_gesperrt):
    d = _mail_dokument(api)
    pfad = f"/api/dokumente/{d['id']}/mail/html"
    ohne = api.get(pfad, erwartet=200)
    assert "bilder.example.invalid" not in ohne.text and "cdn.example.invalid" not in ohne.text
    assert csp_menge(ohne.headers["content-security-policy"]) == csp_menge(CSP_MAIL)
    for wert in ("nein",):
        assert api.get(pfad, params={"bilder": wert}, erwartet=200).text == ohne.text
    mit = api.get(pfad, params={"bilder": "ja"}, erwartet=200)
    klein = mit.text.lower()
    assert "https://bilder.example.invalid/logo.png" in mit.text
    assert "cdn.example.invalid/banner.png" in mit.text
    assert "srcset" not in klein and "srcset.example.invalid" not in klein and "<script" not in klein
    assert "data:image/png;base64,iVBORw0KGgo=" in mit.text
    soll = {t for t in csp_menge(CSP_MAIL) if t[0] != "img-src"} | {("img-src", "data:", "https:", "http:")}
    ist = {t if t[0] != "img-src" else ("img-src", *sorted(t[1:])) for t in
           csp_menge(mit.headers["content-security-policy"])}
    assert ist == {t if t[0] != "img-src" else ("img-src", *sorted(t[1:])) for t in soll}
    assert mit.headers["referrer-policy"] == "no-referrer"
    assert fehlercode(api.get(pfad, params={"bilder": "vielleicht"}, erwartet=422)) == "validierung"


def test_bilder_anzahl(api):
    d = _mail_dokument(api)
    assert api.get(f"/api/dokumente/{d['id']}/mail/bilder", erwartet=200).daten == {"anzahl": 2}
    ohne = _mail_dokument(api, html='<p>Nur Text <img src="data:image/png;base64,iVBORw0KGgo="></p>')
    assert api.get(f"/api/dokumente/{ohne['id']}/mail/bilder", erwartet=200).daten == {"anzahl": 0}
    giro = api.konto("Zweitgiro", "girokonto")["id"]
    kat = api.konto("Sonstiges", "aufwand")["id"]
    bid = api.buchung("2024-06-03", [(giro, -100), (kat, 100)])["id"]
    p = anhaengen(api, [bid], "r.pdf", pdf("R"))
    assert p["mime_typ"] == PDF
    assert fehlercode(api.get(f"/api/dokumente/{p['id']}/mail/bilder", erwartet=409)) == "keine_mail"
    assert fehlercode(api.get("/api/dokumente/999999/mail/bilder", erwartet=404)) == "nicht_gefunden"
