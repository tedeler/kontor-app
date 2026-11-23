"""M18: Inhalte ausliefern, Köpfe, Mails zerlegen, entschärftes HTML, Anhänge, Mail aus dem Spiegel
(dokumente.md 2.2, 2.9–2.13, E-208).

Alle Mails sind synthetisch und hier gebaut; Erwartungen (Nummern der MIME-Teile, dekodierte Größen) werden mit
der Standardbibliothek aus denselben Bytes berechnet.
"""

from __future__ import annotations

import base64
import datetime as dt
import email
from email import policy
from urllib.parse import unquote

import pytest

from tests.hilfen.api import fehlercode
from tests.hilfen.imap_attrappe import ImapAttrappe
from tests.hilfen.m2 import mock_api
from tests.hilfen.m6 import CLIENT_ID, CLIENT_SECRET, EINS, REDIRECT, abruf, nachrichten, postfach
from tests.hilfen.m18 import (
    CSP_INHALT, CSP_MAIL, MAIL, PDF, anhaengen, ascii_name, belege, csp_menge, dateiname_soll, disposition, fehler,
    imap_postfaecher, mail, mock_datei, ohne_wirkung, operation, pdf, png, rundreise, echt_mit_imap,
)
from tests.hilfen.oauth_attrappe import OAuthAttrappe

pytestmark = pytest.mark.kern

LOGO = png(2, 2, (10, 120, 200))
RECHNUNG = pdf("Rechnung 2024-0815")
BINAER = bytes(range(256))

HTML = """<html><head><style>@import url(http://stil.example.invalid/a.css);
body { background: url(https://stil.example.invalid/b.png) }</style>
<script>var geheimesSkript = 1;</script></head>
<body onload="boese()"><p onclick="boese()">Rechnung im Anhang</p>
<img src="cid:logo@example.invalid" alt="Logo">
<img src="https://zaehlpixel.example.invalid/p.gif" alt="Pixel">
<img src="//zaehlpixel.example.invalid/q.gif">
<img src="data:image/png;base64,iVBORw0KGgo=" alt="eingebettet">
<a href="javascript:boese()">Böse</a>
<a href="https://link.example.invalid/rechnung">Zur Rechnung</a>
<iframe src="https://rahmen.example.invalid/"></iframe>
<svg><script>alert(1)</script></svg>
<form action="https://formular.example.invalid/"><input name="x"></form>
<table background="https://hintergrund.example.invalid/t.png"><tr>
<td style="background-image:url('http://stil.example.invalid/c.png')">Zelle</td></tr></table>
<noscript>noscriptinhalt</noscript>
<meta http-equiv="refresh" content="0;url=https://meta.example.invalid/">
<base href="https://basis.example.invalid/">
</body></html>"""


def _b64(daten: bytes) -> str:
    return base64.encodebytes(daten).decode().replace("\n", "\r\n")


def komplexe_mail() -> bytes:
    """multipart/mixed mit alternative(text, related(html, inline-Bild)), PDF, Text-Anhang ohne Namen, CSV ohne
    Namen (kein Anhang) und Binäranhang."""
    teile = f"""From: "Fiktiver Shop" <shop@example.invalid>
To: Haushalt Eins <haushalt.eins@example.invalid>, zwei@example.invalid
Cc: <kopie@example.invalid>
Subject: =?utf-8?q?Ihre_Rechnung_M=C3=A4rz?=
  (fiktiv)
Date: Mon, 03 Jun 2024 11:30:00 +0200
Message-ID: <synth-0002@example.invalid>
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="AAA"

--AAA
Content-Type: multipart/alternative; boundary="BBB"

--BBB
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: base64

{_b64("Guten Tag,\ndie Rechnung liegt bei.\n".encode())}
--BBB
Content-Type: multipart/related; boundary="CCC"

--CCC
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: base64

{_b64(HTML.encode())}
--CCC
Content-Type: image/png
Content-ID: <logo@example.invalid>
Content-Transfer-Encoding: base64

{_b64(LOGO)}
--CCC--
--BBB--
--AAA
Content-Type: application/pdf; name="rechnung.pdf"
Content-Disposition: attachment; filename="rechnung.pdf"
Content-Transfer-Encoding: base64

{_b64(RECHNUNG)}
--AAA
Content-Type: text/plain; charset=utf-8
Content-Disposition: attachment
Content-Transfer-Encoding: base64

{_b64("Notiz ohne Namen".encode())}
--AAA
Content-Type: text/csv
Content-Transfer-Encoding: base64

{_b64(b"a;b")}
--AAA
Content-Type: application/x-kontor-test; name="daten.bin"
Content-Disposition: attachment; filename="daten.bin"
Content-Transfer-Encoding: base64

{_b64(BINAER)}
--AAA--
"""
    return teile.replace("\r\n", "\n").replace("\n", "\r\n").encode()


def _teile(roh: bytes) -> list:
    return list(email.message_from_bytes(roh, policy=policy.compat32).walk())


def _konto(api, name: str, art: str) -> int:
    """Vorhandenes Konto wiederverwenden: ab M32 Kontonamen je Ebene eindeutig (W-027, E-314)."""
    for x in api.konten():
        if x["name"] == name and x["art"] == art and x["eltern_id"] is None:
            return x["id"]
    return api.konto(name, art)["id"]


def _konto_und_buchung(api) -> int:
    g = _konto(api, "Girokonto", "girokonto")
    k = _konto(api, "Einkauf", "aufwand")
    return api.buchung("2024-06-03", [(g, -5990), (k, 5990)], verwendungszweck="Bestellung")["id"]


def _sicherheitskoepfe(r, csp: str) -> None:
    """2.12 ohne Cache-Control (eigener Test ``test_cache_control_privat``)."""
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert csp_menge(r.headers["content-security-policy"]) == csp_menge(csp), r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"


def _name_koepfe(r, art: str, name: str) -> None:
    d = disposition(r.headers["content-disposition"])
    assert d["art"] == art, r.headers["content-disposition"]
    assert d["filename"] == ascii_name(name), (d, ascii_name(name))
    assert d["filename*"].lower().startswith("utf-8''"), d
    assert unquote(d["filename*"][7:]) == name


# ------------------------------------------------------------------ Inhalt und Köpfe (2.9, 2.12)


def test_inhalt_pdf_bild_mail_mit_koepfen(api):
    b = _konto_und_buchung(api)
    p = anhaengen(api, [b], "Quittung März ?.pdf", RECHNUNG)
    assert p["dateiname"] == "Quittung März ?.pdf"
    r = api.get(f"/api/dokumente/{p['id']}/inhalt", erwartet=200)
    assert r.content == RECHNUNG and r.headers["content-type"].split(";")[0] == PDF
    _sicherheitskoepfe(r, CSP_INHALT)
    _name_koepfe(r, "inline", "Quittung März ?.pdf")
    for wert, art in (("true", "attachment"), ("1", "attachment"), ("false", "inline"), ("0", "inline")):
        r = api.get(f"/api/dokumente/{p['id']}/inhalt", params={"herunterladen": wert}, erwartet=200)
        assert disposition(r.headers["content-disposition"])["art"] == art, wert
        assert r.content == RECHNUNG
    for falsch in ("ja", "2", ""):
        fehler(api.get(f"/api/dokumente/{p['id']}/inhalt", params={"herunterladen": falsch}, erwartet=422),
               "validierung")
    fehler(api.get("/api/dokumente/999999/inhalt", erwartet=404), "nicht_gefunden")
    # Anführungszeichen im Namen (über PATCH): " → '
    api.patch(f"/api/dokumente/{p['id']}", json={"dateiname": 'Bon "Ä".pdf'}, erwartet=200)
    _name_koepfe(api.get(f"/api/dokumente/{p['id']}/inhalt", erwartet=200), "inline", 'Bon "Ä".pdf')
    # Bild
    q = anhaengen(api, [b], "logo.png", LOGO)
    r = api.get(f"/api/dokumente/{q['id']}/inhalt", erwartet=200)
    assert (r.content, r.headers["content-type"].split(";")[0]) == (LOGO, "image/png")
    _sicherheitskoepfe(r, CSP_INHALT)
    # Mail: immer application/octet-stream als Anhang
    roh = komplexe_mail()
    m = anhaengen(api, [b], "rechnung.eml", roh)
    for params in (None, {"herunterladen": "false"}):
        r = api.get(f"/api/dokumente/{m['id']}/inhalt", params=params, erwartet=200)
        assert r.content == roh and r.headers["content-type"].split(";")[0] == "application/octet-stream"
        assert disposition(r.headers["content-disposition"])["art"] == "attachment"
        _sicherheitskoepfe(r, CSP_INHALT)
    # alle anderen Antworten behalten DENY
    r = api.get(f"/api/dokumente/{m['id']}", erwartet=200)
    assert r.headers["x-frame-options"] == "DENY"
    assert api.get("/api/buchungen", erwartet=200).headers["x-frame-options"] == "DENY"


def test_cache_control_privat(api):
    """2.12: Inhaltsantworten (2.9, 2.11, 2.13) tragen ``Cache-Control: private, no-store``."""
    b = _konto_und_buchung(api)
    p = anhaengen(api, [b], "p.pdf", RECHNUNG)
    m = anhaengen(api, [b], "m.eml", komplexe_mail())
    for pfad in (f"/api/dokumente/{p['id']}/inhalt", f"/api/dokumente/{m['id']}/inhalt",
                 f"/api/dokumente/{m['id']}/mail/html", f"/api/dokumente/{m['id']}/mail/anhaenge/6"):
        r = api.get(pfad, erwartet=200)
        teile = {x.strip().lower() for x in r.headers.get("cache-control", "").split(",")}
        assert teile == {"private", "no-store"}, (pfad, r.headers.get("cache-control"))


# ------------------------------------------------------------------ Mail zerlegt (2.10)


def test_mail_ansicht(api):
    b = _konto_und_buchung(api)
    roh = komplexe_mail()
    m = anhaengen(api, [b], "r.eml", roh)
    v = api.get(f"/api/dokumente/{m['id']}/mail", erwartet=200).daten
    assert v["von"] == [{"name": "Fiktiver Shop", "adresse": "shop@example.invalid"}]
    assert v["an"] == [{"name": "Haushalt Eins", "adresse": "haushalt.eins@example.invalid"},
                       {"name": "", "adresse": "zwei@example.invalid"}]
    assert v["cc"] == [{"name": "", "adresse": "kopie@example.invalid"}]
    assert v["datum"] == "2024-06-03T09:30:00Z"
    assert v["betreff"] == "Ihre Rechnung März (fiktiv)"
    assert v["text"].rstrip("\n") == "Guten Tag,\ndie Rechnung liegt bei."
    assert "\r" not in v["text"]
    assert v["html"] is True
    teile = _teile(roh)
    groesse = {i: len(t.get_payload(decode=True)) for i, t in enumerate(teile) if not t.is_multipart()}
    assert [t.get_content_type() for t in teile] == [
        "multipart/mixed", "multipart/alternative", "text/plain", "multipart/related", "text/html", "image/png",
        "application/pdf", "text/plain", "text/csv", "application/x-kontor-test"], "Aufbau der Testmail"
    assert v["anhaenge"] == [
        {"nr": 5, "dateiname": "Anhang 5", "mime_typ": "image/png", "groesse": groesse[5], "inline": True},
        {"nr": 6, "dateiname": "rechnung.pdf", "mime_typ": "application/pdf", "groesse": len(RECHNUNG),
         "inline": False},
        {"nr": 7, "dateiname": "Anhang 7", "mime_typ": "text/plain", "groesse": groesse[7], "inline": False},
        {"nr": 9, "dateiname": "daten.bin", "mime_typ": "application/x-kontor-test", "groesse": 256,
         "inline": False},
    ]
    p = anhaengen(api, [b], "p.pdf", RECHNUNG)
    for pfad in ("mail", "mail/html", "mail/anhaenge/1"):
        fehler(api.get(f"/api/dokumente/{p['id']}/{pfad}", erwartet=409), "keine_mail")
        fehler(api.get(f"/api/dokumente/999999/{pfad}", erwartet=404), "nicht_gefunden")


@pytest.mark.parametrize("datum,soll", [
    (None, None), ("Mon, 3 Jun 2024 11:30:00", "2024-06-03T11:30:00Z"), ("kein Datum", None),
    ("Sun, 30 Jun 2024 23:30:00 -0230", "2024-07-01T02:00:00Z"),
])
def test_mail_ansicht_datum(api, datum, soll):
    roh = b"From: a@example.invalid\r\nSubject: Datum\r\n"
    if datum is not None:
        roh += f"Date: {datum}\r\n".encode()
    roh += b"\r\nText\r\n"
    m = anhaengen(api, [_konto_und_buchung(api)], "d.eml", roh)
    v = api.get(f"/api/dokumente/{m['id']}/mail", erwartet=200).daten
    assert v["datum"] == soll
    assert (v["betreff"], v["html"], v["anhaenge"], v["cc"]) == ("Datum", False, [], [])
    assert v["von"] == [{"name": "", "adresse": "a@example.invalid"}] and v["an"] == []


def test_mail_ansicht_nur_html_und_ohne_betreff(api):
    roh = ("From: a@example.invalid\r\nDate: Mon, 3 Jun 2024 10:00:00 +0000\r\nMIME-Version: 1.0\r\n"
           "Content-Type: text/html; charset=utf-8\r\n\r\n<html><head><style>.versteckt{color:red}</style>"
           "<script>var skriptinhalt=1;</script></head><body><p>Nur <b>HTML</b> Inhalt</p></body></html>\r\n").encode()
    m = anhaengen(api, [_konto_und_buchung(api)], "h.eml", roh)
    v = api.get(f"/api/dokumente/{m['id']}/mail", erwartet=200).daten
    assert v["betreff"] == "" and v["html"] is True and v["anhaenge"] == []
    assert " ".join(v["text"].split()) == "Nur HTML Inhalt"
    assert "skriptinhalt" not in v["text"] and "versteckt" not in v["text"] and "<" not in v["text"]
    # Mail ohne HTML-Teil → mail/html 404
    t = anhaengen(api, [_konto_und_buchung(api)], "t.eml", mail())
    assert api.get(f"/api/dokumente/{t['id']}/mail", erwartet=200).daten["html"] is False
    fehler(api.get(f"/api/dokumente/{t['id']}/mail/html", erwartet=404), "nicht_gefunden")


# ------------------------------------------------------------------ Entschärftes HTML (2.11)


def test_mail_html_entschaerft(api):
    m = anhaengen(api, [_konto_und_buchung(api)], "r.eml", komplexe_mail())
    r = api.get(f"/api/dokumente/{m['id']}/mail/html", erwartet=200)
    assert r.headers["content-type"].replace(" ", "").lower() == "text/html;charset=utf-8"
    _sicherheitskoepfe(r, CSP_MAIL)
    d = disposition(r.headers["content-disposition"])
    assert (d["art"], d["filename"]) == ("inline", "mail.html")
    html = r.text
    klein = html.lower()
    assert "<html" in klein and "<head" in klein, "vollständiges HTML-Dokument mit eigenem Kopf"
    for weg in ("<script", "geheimesskript", "alert(1)", "<iframe", "<svg", "<form", "noscriptinhalt", "<noscript",
                "http-equiv", "onload", "onclick", "javascript:", "@import", "zaehlpixel.example.invalid",
                "stil.example.invalid", "rahmen.example.invalid", "hintergrund.example.invalid",
                "basis.example.invalid", "meta.example.invalid", "formular.example.invalid"):
        assert weg not in klein, f"{weg!r} steht noch im entschärften HTML"
    assert "data:image/png;base64," + base64.b64encode(LOGO).decode() in html.replace("\n", "").replace("\r", ""), (
        "cid-Bild als data:-URL eingebettet")
    assert "data:image/png;base64,iVBORw0KGgo=" in html, "data:image/png bleibt"
    assert "https://link.example.invalid/rechnung" in html and "Zur Rechnung" in html, "Links bleiben"
    assert "Rechnung im Anhang" in html and "Zelle" in html, "Text bleibt"
    import re
    assert re.search(r"<base\b[^>]*target\s*=\s*[\"']?_blank", html, re.I), "Links öffnen im neuen Fenster"
    assert not re.search(r"""\b(src|href|background|action)\s*=\s*["']?\s*(https?:)?//[^"'>\s]*"""
                         r"""(zaehlpixel|stil|hintergrund|rahmen)""", html, re.I)


# ------------------------------------------------------------------ Anhänge (2.13)


def test_mail_anhaenge_ausliefern(api):
    m = anhaengen(api, [_konto_und_buchung(api)], "r.eml", komplexe_mail())
    basis = f"/api/dokumente/{m['id']}/mail/anhaenge"
    r = api.get(f"{basis}/6", erwartet=200)
    assert (r.content, r.headers["content-type"].split(";")[0]) == (RECHNUNG, PDF)
    _sicherheitskoepfe(r, CSP_INHALT)
    _name_koepfe(r, "inline", "rechnung.pdf")
    assert disposition(api.get(f"{basis}/6", params={"herunterladen": "true"},
                               erwartet=200).headers["content-disposition"])["art"] == "attachment"
    r = api.get(f"{basis}/5", erwartet=200)
    assert (r.content, r.headers["content-type"].split(";")[0]) == (LOGO, "image/png")
    r = api.get(f"{basis}/7", erwartet=200)
    assert r.content == "Notiz ohne Namen".encode()
    assert r.headers["content-type"].replace(" ", "").lower() == "text/plain;charset=utf-8"
    r = api.get(f"{basis}/9", erwartet=200)
    assert r.content == BINAER and r.headers["content-type"].split(";")[0] == "application/octet-stream"
    assert disposition(r.headers["content-disposition"])["art"] == "attachment", "andere Typen immer als Anhang"
    for nr in (0, 1, 2, 3, 4, 8, 10, 99):
        fehler(api.get(f"{basis}/{nr}", erwartet=404), "nicht_gefunden")
    fehler(api.get(f"{basis}/6", params={"herunterladen": "ja"}, erwartet=422), "validierung")


def test_eingebettete_nachricht_als_ganze_nachricht(api):
    """2.13: ein eingebetteter message/rfc822-Teil wird als ganze Nachricht ausgeliefert (E-208: Nummer und
    Unterteile nicht festgelegt, nur der Eintrag mit diesem Typ)."""
    innen = mail(betreff="Weitergeleitet (fiktiv)", text="Innerer Text\n")
    roh = ("From: a@example.invalid\r\nSubject: Fwd\r\nMIME-Version: 1.0\r\n"
           'Content-Type: multipart/mixed; boundary="X"\r\n\r\n--X\r\nContent-Type: text/plain\r\n\r\nAussen\r\n'
           "--X\r\nContent-Type: message/rfc822\r\nContent-Disposition: attachment\r\n\r\n").encode() + innen + \
        b"\r\n--X--\r\n"
    m = anhaengen(api, [_konto_und_buchung(api)], "f.eml", roh)
    v = api.get(f"/api/dokumente/{m['id']}/mail", erwartet=200).daten
    eingebettet = [a for a in v["anhaenge"] if a["mime_typ"] == "message/rfc822"]
    assert len(eingebettet) == 1, v["anhaenge"]
    r = api.get(f"/api/dokumente/{m['id']}/mail/anhaenge/{eingebettet[0]['nr']}", erwartet=200)
    assert r.headers["content-type"].split(";")[0] == "application/octet-stream"
    assert disposition(r.headers["content-disposition"])["art"] == "attachment"
    inner = email.message_from_bytes(r.content, policy=policy.default)
    assert inner["Subject"] == "Weitergeleitet (fiktiv)" and "Innerer Text" in r.content.decode()


# ------------------------------------------------------------------ Mail aus dem Spiegel (2.2)

NACHRICHTEN = [
    {"nachricht_id": "M-1", "postfach": EINS, "empfangen": "2024-06-01T08:15:00Z",
     "absender": "Fiktiver Shop <shop@example.invalid>", "betreff": "Ihre Bestellung (fiktiv)",
     "text": "Vielen Dank für Ihre Bestellung.\nGesamtsumme: 12,34 €\n"},
    {"nachricht_id": "<synth-7@example.invalid>", "postfach": EINS, "empfangen": "2024-06-02T09:00:00Z",
     "absender": "", "betreff": "", "text": "Ohne Absender und Betreff"},
    {"nachricht_id": "M-3", "postfach": EINS, "empfangen": "2024-06-03T10:00:00Z",
     "absender": "info@example.invalid", "betreff": "L" * 230, "text": "lang"},
]


@pytest.fixture
def spiegel(tmp_path):
    datei = mock_datei(tmp_path / "mock.json", NACHRICHTEN, [EINS])
    api = mock_api(tmp_path, daten=datei, heute="2024-06-30", mail_erstabruf_tage=365)
    postfach(api, EINS)
    abruf(api)
    n = {x["nachricht_id"]: x for x in nachrichten(api)}
    assert set(n) == {x["nachricht_id"] for x in NACHRICHTEN}
    return api, n


def test_aus_mail_mock_aus_feldern_gebaut(spiegel):
    api, n = spiegel
    b1, b2 = _konto_und_buchung(api), _konto_und_buchung(api)
    nid = n["M-1"]["id"]
    d, a, v, nach = operation(api, "dokument_aus_mail", lambda: api.post(
        "/api/dokumente/aus-mail", json={"nachricht_id": nid, "buchung_ids": [b2, b1, b2]}, erwartet=201).daten)
    assert (d["quelle"], d["mime_typ"], d["buchung_ids"]) == ("mail", MAIL, sorted([b1, b2]))
    assert d["dateiname"] == "Ihre Bestellung (fiktiv).eml"
    assert {(e["objekt"], e["objekt_id"]) for e in a["eintraege"]} == {("dokument", d["id"]), ("buchung", b1),
                                                                        ("buchung", b2)}
    roh = api.get(f"/api/dokumente/{d['id']}/inhalt", erwartet=200).content
    m = api.get(f"/api/dokumente/{d['id']}/mail", erwartet=200).daten
    assert m["betreff"] == "Ihre Bestellung (fiktiv)"
    assert m["text"].rstrip() == NACHRICHTEN[0]["text"].rstrip()
    assert [x["adresse"] for x in m["von"]] == ["shop@example.invalid"]
    assert [x["adresse"] for x in m["an"]] == [EINS]
    assert m["datum"] == "2024-06-01T08:15:00Z"
    kopf = email.message_from_bytes(roh, policy=policy.default)
    assert kopf["Message-ID"] is None, "Message-ID nur, wenn die Nachrichten-ID mit < beginnt"
    rundreise(api, a, v, nach, {d["id"]: roh})


def test_aus_mail_ohne_absender_ohne_betreff_langer_betreff(spiegel):
    api, n = spiegel
    b = _konto_und_buchung(api)
    d = api.post("/api/dokumente/aus-mail", json={"nachricht_id": n["<synth-7@example.invalid>"]["id"],
                                                  "buchung_ids": [b]}, erwartet=201).daten
    assert d["dateiname"] == "E-Mail.eml"
    roh = api.get(f"/api/dokumente/{d['id']}/inhalt", erwartet=200).content
    kopf = email.message_from_bytes(roh, policy=policy.default)
    assert kopf["Message-ID"] == "<synth-7@example.invalid>"
    m = api.get(f"/api/dokumente/{d['id']}/mail", erwartet=200).daten
    assert [x["adresse"] for x in m["von"]] == ["unbekannt@example.invalid"] and m["betreff"] == ""
    lang = api.post("/api/dokumente/aus-mail", json={"nachricht_id": n["M-3"]["id"], "buchung_ids": [b]},
                    erwartet=201).daten
    assert lang["dateiname"] == "L" * 196 + ".eml" == dateiname_soll("L" * 196, MAIL)
    assert [x["id"] for x in belege(api, b)] == [d["id"], lang["id"]]


def test_aus_mail_pruefreihenfolge(spiegel):
    api, n = spiegel
    b = _konto_und_buchung(api)
    nid = n["M-1"]["id"]

    def faelle():
        for k in ([], "x", {"buchung_ids": [b]}, {"nachricht_id": "1", "buchung_ids": [b]},
                  {"nachricht_id": True, "buchung_ids": [b]}, {"nachricht_id": 1.5, "buchung_ids": [b]}):
            fehler(api.post("/api/dokumente/aus-mail", json=k, erwartet=422), "validierung")
        # Nachricht unbekannt vor ungültigen buchung_ids
        fehler(api.post("/api/dokumente/aus-mail", json={"nachricht_id": 999999, "buchung_ids": []}, erwartet=404),
               "nicht_gefunden")
        for ids in ([], "1", ["1"], None):
            fehler(api.post("/api/dokumente/aus-mail", json={"nachricht_id": nid, "buchung_ids": ids},
                            erwartet=422), "validierung")
        fehler(api.post("/api/dokumente/aus-mail", json={"nachricht_id": nid}, erwartet=422), "validierung")
        fehler(api.post("/api/dokumente/aus-mail", json={"nachricht_id": nid, "buchung_ids": [b, 999999]},
                        erwartet=404), "nicht_gefunden")
    ohne_wirkung(api, faelle)
    assert fehlercode(api.post("/api/dokumente/aus-mail", json={"nachricht_id": nid, "buchung_ids": [b], "x": 1},
                               erwartet=422)) == "validierung"


@pytest.fixture
def imap_stubs(netz_nur_loopback):
    roh = komplexe_mail()
    o = OAuthAttrappe(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT).starte()
    i = ImapAttrappe(pruefe_token=o.access_gueltig, postfaecher=imap_postfaecher(EINS, [
        (dt.datetime(2024, 6, 3, 9, 30, tzinfo=dt.timezone.utc), roh)])).starte()
    yield o, i, roh
    i.stoppe()
    o.stoppe()


def test_aus_mail_imap_rohfassung(tmp_path, imap_stubs):
    """2.2: Nachricht aus einem echten Postfach → Inhalt genau die abgerufene Rohnachricht."""
    o, i, roh = imap_stubs
    api, _ = echt_mit_imap(tmp_path, i, o, EINS)
    (n,) = nachrichten(api)
    b = _konto_und_buchung(api)
    d = api.post("/api/dokumente/aus-mail", json={"nachricht_id": n["id"], "buchung_ids": [b]}, erwartet=201).daten
    assert (d["quelle"], d["mime_typ"], d["groesse"]) == ("mail", MAIL, len(roh))
    assert d["dateiname"] == dateiname_soll(n["betreff"][:196] or "E-Mail", MAIL), "Betreff der gespiegelten Mail"
    assert " ".join(n["betreff"].split()) == "Ihre Rechnung März (fiktiv)", "Testvoraussetzung: Betreff dekodiert"
    assert api.get(f"/api/dokumente/{d['id']}/inhalt", erwartet=200).content == roh
    v = api.get(f"/api/dokumente/{d['id']}/mail", erwartet=200).daten
    assert [a["nr"] for a in v["anhaenge"]] == [5, 6, 7, 9]
    assert api.get(f"/api/dokumente/{d['id']}/mail/anhaenge/6", erwartet=200).content == RECHNUNG
