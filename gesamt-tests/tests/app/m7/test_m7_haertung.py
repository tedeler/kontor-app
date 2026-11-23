"""M7: Sicherheitsköpfe, Eingabehärtung, Größengrenzen, Netzbeschränkung, keine Geheimnisse in Logs
(sicherheit.md 6–10)."""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

import pytest

from tests.hilfen.api import Api, fehlercode, neue_config
from tests.hilfen.m7 import (CSRF, NEUES_PASSWORT, PASSWORT, anmelden, csp, einrichtungsdatei, m7_api, m7_config,
                             sitzungstoken, zweiter_client)
from tests.hilfen.pfade import KMY

KOEPFE = {"x-content-type-options": "nosniff", "x-frame-options": "DENY", "referrer-policy": "no-referrer",
          "cross-origin-opener-policy": "same-origin"}
CSP_PFLICHT = {"default-src": ["'self'"], "script-src": ["'self'"], "object-src": ["'none'"],
               "base-uri": ["'none'"], "frame-ancestors": ["'none'"], "form-action": ["'self'"]}


def pruefe_koepfe(r, *, html_oder_api: bool = True) -> None:
    for k, v in KOEPFE.items():
        assert r.headers.get(k) == v, f"{r.request.method} {r.request.url.path} → {r.status_code}: {k}={r.headers.get(k)!r}"
    richtlinie = csp(r.headers.get("content-security-policy", ""))
    for direktive, quellen in CSP_PFLICHT.items():
        assert richtlinie.get(direktive) == quellen, f"CSP {direktive}: {richtlinie.get(direktive)}"
    for direktive, quellen in richtlinie.items():
        assert not any(q.startswith(("http:", "https:")) or q == "*" for q in quellen), (direktive, quellen)
    if html_oder_api:
        assert "no-store" in r.headers.get("cache-control", ""), r.request.url.path


# ------------------------------------------------------------------ Sicherheitsköpfe
@pytest.mark.kern
def test_sicherheitskoepfe_ohne_anmeldung(api):
    for r in (api.get("/api/status"), api.get("/api/gibt-es-nicht"), api.post("/api/konten", json={}),
              api.get("/"), api.get("/api/anmeldung"), api.client.get("/anmelden", follow_redirects=False),
              api.delete("/api/status")):
        pruefe_koepfe(r, html_oder_api=r.status_code != 303)


@pytest.mark.kern
def test_sicherheitskoepfe_mit_anmeldung(tmp_path):
    api = m7_api(tmp_path)
    for r in (api.get("/api/konten"), api.client.get("/", follow_redirects=False), api.get("/anmelden"),
              anmelden(api, "Falsch-Falsch-Falsch", erwartet=401), api.get("/api/gesundheit")):
        pruefe_koepfe(r, html_oder_api=r.status_code != 303)
    anmelden(api)
    for r in (api.get("/api/konten"), api.get("/"), api.post("/api/konten", json={"name": "x", "art": "girokonto"})):
        pruefe_koepfe(r)


class _Skripte(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fehler: list[str] = []
        self._im_skript = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k, v in attrs:
            if k.lower().startswith("on"):
                self.fehler.append(f"<{tag}> mit Ereignisattribut {k}")
            if k.lower() in ("href", "src", "action") and v and v.strip().lower().startswith("javascript:"):
                self.fehler.append(f"<{tag} {k}={v!r}>")
        if tag == "script":
            src = a.get("src")
            if not src:
                self.fehler.append("<script> ohne src")
            elif re.match(r"^[a-z]+:|^//", src, re.I):
                self.fehler.append(f"<script src={src!r}> nicht derselben Herkunft")
            self._im_skript = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._im_skript = False

    def handle_data(self, data):
        if self._im_skript and data.strip():
            self.fehler.append("Inline-Skript")


@pytest.mark.kern
@pytest.mark.parametrize("mock", [False, True])
def test_html_ohne_inline_skripte(tmp_path, mock):
    api = m7_api(tmp_path, mock_modus=mock)
    seiten = [api.get("/anmelden").text]
    anmelden(api)
    seiten.append(api.get("/").text)
    for html in seiten:
        p = _Skripte()
        p.feed(html)
        assert not p.fehler, p.fehler


# ------------------------------------------------------------------ SQL-Injection
SQL = ["'; DROP TABLE buchungen; --", "\" OR 1=1 --", "%' OR '1'='1", "Robert'); DELETE FROM konten;--",
       "x' UNION SELECT name FROM sqlite_master --", "/* Kommentar */ 1", "a\\'b", "100%_Rabatt"]


@pytest.mark.kern
@pytest.mark.parametrize("text", SQL)
def test_sql_texte_woertlich(api, text):
    g = api.konto("Giro " + text)
    kat = api.konto("Kat " + text, "aufwand")
    e = api.empfaenger("Empf " + text)
    t = api.tag("Tag " + text)
    b = api.buchung("2024-01-05", [(g["id"], -100), (kat["id"], 100)], verwendungszweck="Zweck " + text,
                    empfaenger_id=e["id"], tag_ids=[t["id"]])
    api.buchung("2024-01-06", [(g["id"], -200), (kat["id"], 200)], verwendungszweck="Harmlos")
    assert api.buchung_lesen(b["id"])["verwendungszweck"] == "Zweck " + text
    assert {k["name"] for k in api.konten()} == {"Giro " + text, "Kat " + text}
    assert api.get(f"/api/empfaenger/{e['id']}", erwartet=200).daten["name"] == "Empf " + text
    for param in ("verwendungszweck", "suche"):
        ids = [x["id"] for x in api.alle_buchungen(**{param: text})]
        soll = [b["id"]]  # nur die Buchung mit dem Text (Verwendungszweck, Empfänger, Tag), nie „Harmlos“
        assert ids == soll, (param, ids, soll)
    api.get("/api/suche", params={"q": text}, erwartet=200)
    assert len(api.alle_buchungen()) == 2


@pytest.mark.kern
def test_platzhalter_wirken_nicht(api):
    g = api.konto("Giro")
    kat = api.konto("Kat", "aufwand")
    api.buchung("2024-01-05", [(g["id"], -100), (kat["id"], 100)], verwendungszweck="Miete Januar")
    api.buchung("2024-01-06", [(g["id"], -100), (kat["id"], 100)], verwendungszweck="Rabatt 100% sofort")
    assert [b["verwendungszweck"] for b in api.alle_buchungen(verwendungszweck="%")] == ["Rabatt 100% sofort"]
    assert api.alle_buchungen(verwendungszweck="_") == []
    assert api.alle_buchungen(verwendungszweck="M_ete") == []
    assert api.alle_buchungen(suche="%a%") == []


@pytest.mark.kern
@pytest.mark.parametrize("params", [{"konto_id": "1 OR 1=1"}, {"sortierung": "datum; DROP TABLE x"},
                                    {"seite": "1;--"}, {"betrag_min": "0 OR 1"}, {"tag_id": "1) OR (1"}])
def test_ungueltige_parameter_422(api, params):
    assert fehlercode(api.get("/api/buchungen", params=params, erwartet=422)) == "validierung"


# ------------------------------------------------------------------ XSS
XSS = ['<script>alert("xss")</script>', '<img src=x onerror=alert(1)>', '"><svg onload=alert(1)>',
       "javascript:alert(1)"]


@pytest.mark.kern
def test_xss_texte_woertlich_und_nicht_im_html(api):
    g = api.konto(XSS[0])
    kat = api.konto(XSS[1], "aufwand")
    e = api.empfaenger(XSS[2])
    b = api.buchung("2024-01-05", [(g["id"], -100, XSS[3]), (kat["id"], 100)], verwendungszweck=XSS[0],
                    empfaenger_id=e["id"])
    r = api.get(f"/api/buchungen/{b['id']}", erwartet=200)
    assert r.headers["content-type"].startswith("application/json")
    assert r.daten["verwendungszweck"] == XSS[0] and r.daten["empfaenger"]["name"] == XSS[2]
    assert r.daten["splits"][0]["memo"] == XSS[3]
    html = api.get("/").text
    for x in XSS[:3]:
        assert x not in html
    for pfad in ('/<script>alert(1)</script>', '/konten/"><img src=x onerror=alert(1)>'):
        r = api.client.get(pfad)
        assert r.status_code in (200, 404)
        assert "<script>alert(1)" not in r.text and "onerror=alert" not in r.text


# ------------------------------------------------------------------ Pfade, Robustheit
@pytest.mark.parametrize("pfad", ["/oeffentlich/../../../../etc/passwd", "/oeffentlich/..%2f..%2f..%2fetc%2fpasswd",
                                  "/oeffentlich/%2e%2e/%2e%2e/%2e%2e/etc/passwd", "/oeffentlich/..%5c..%5cetc%5cpasswd",
                                  "/oeffentlich//etc/passwd", "/oeffentlich/%00.js"])
def test_pfadtraversal(api, pfad):
    r = api.client.get(pfad)
    assert r.status_code in (400, 404) or (r.status_code == 200 and "root:" not in r.text), (pfad, r.status_code)
    assert "root:" not in r.text


@pytest.mark.kern
def test_robuste_eingaben(api):
    tief = b"[" * 100_000 + b"]" * 100_000
    for body, art in ((tief, "application/json"), (b'{"name": "\xff\xfe", "art": "girokonto"}', "application/json"),
                      (b"name=x", "text/plain"), (b'{"name": "x", "art": "girokonto"', "application/json"),
                      (b'{"name": "x", "art": "girokonto", "eltern_id": 1' + b"0" * 400 + b"}", "application/json")):
        r = api.post("/api/konten", content=body, headers={"content-type": art})
        assert r.status_code in (413, 422), (body[:40], r.status_code)
        assert "Traceback" not in r.text and "sqlite" not in r.text.lower()
    r = api.post("/api/konten", json={"name": "Null\u0000Byte", "art": "girokonto"})
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        assert api.get(f"/api/konten/{r.daten['id']}", erwartet=200).daten["name"] == "Null\u0000Byte"


# ------------------------------------------------------------------ Größengrenzen
def _multipart(gesamt: int) -> tuple[bytes, str]:
    grenze = "kontorgrenze4711"
    kopf = (f"--{grenze}\r\nContent-Disposition: form-data; name=\"datei\"; filename=\"gross.kmy\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode()
    fuss = f"\r\n--{grenze}--\r\n".encode()
    return kopf + b"x" * (gesamt - len(kopf) - len(fuss)) + fuss, f"multipart/form-data; boundary={grenze}"


@pytest.mark.kern
def test_upload_grenze(tmp_path):
    api = Api(neue_config(tmp_path, upload_max_mib=1))
    grenze = 1024 * 1024
    body, art = _multipart(grenze)
    r = api.post("/api/import/kmymoney", content=body, headers={"content-type": art})
    assert r.status_code != 413, "genau die Grenze ist erlaubt"
    importe = api.get("/api/importe", erwartet=200).daten
    body, art = _multipart(grenze + 1)
    r = api.post("/api/import/kmymoney", content=body, headers={"content-type": art}, erwartet=413)
    assert fehlercode(r) == "datei_zu_gross" and r.json()["fehler"]["details"] == {"grenze_bytes": grenze}
    for pfad in ("/api/import/gnucash", "/api/sicherung/einspielen"):
        r = api.post(pfad, content=body, headers={"content-type": art}, erwartet=413)
        assert fehlercode(r) == "datei_zu_gross"
    assert api.get("/api/importe", erwartet=200).daten == importe, "abgelehnt ohne Importvorgang"
    assert api.alle_buchungen() == [] and api.konten() == []
    # chunked ohne Content-Length
    def stuecke():
        for i in range(0, len(body), 65536):
            yield body[i:i + 65536]
    r = api.post("/api/import/kmymoney", content=stuecke(), headers={"content-type": art}, erwartet=413)
    assert fehlercode(r) == "datei_zu_gross"
    # normale Importe sind nicht betroffen
    assert api.import_kmy(KMY / "minimal.kmy", erwartet=200).daten["erfolgreich"]


@pytest.mark.kern
def test_anfrage_grenze(tmp_path):
    api = Api(neue_config(tmp_path, anfrage_max_kib=16))
    grenze = 16 * 1024
    vorlage = b'{"name": "x", "art": "girokonto", "notiz": "%s"}'
    fuell = grenze - len(vorlage % b"")
    r = api.post("/api/konten", content=vorlage % (b"n" * fuell), headers={"content-type": "application/json"})
    assert r.status_code in (201, 422), r.status_code
    r = api.post("/api/konten", content=vorlage % (b"n" * (fuell + 1)), headers={"content-type": "application/json"},
                 erwartet=413)
    assert fehlercode(r) == "anfrage_zu_gross" and r.json()["fehler"]["details"] == {"grenze_bytes": grenze}
    assert len(api.konten()) <= 1
    # Uploads haben ihre eigene Grenze
    assert api.import_kmy(KMY / "standard.kmy", erwartet=200).daten["erfolgreich"]


@pytest.mark.kern
def test_grenze_nach_anmeldung(tmp_path):
    api = m7_api(tmp_path, anfrage_max_kib=16)
    body = b'{"name": "' + b"x" * 20000 + b'", "art": "girokonto"}'
    assert api.post("/api/konten", content=body, headers={"content-type": "application/json"}).status_code == 401
    anmelden(api)
    r = api.post("/api/konten", content=body, headers={"content-type": "application/json", CSRF: api.csrf})
    assert r.status_code == 413


# ------------------------------------------------------------------ Netz
@pytest.mark.kern
@pytest.mark.parametrize("adresse,erlaubt", [("192.168.1.20", True), ("10.1.2.3", False), ("::1", True),
                                             ("203.0.113.9", False), ("testclient", False),
                                             ("::ffff:192.168.1.5", True), ("2001:db8::1", False)])
def test_erlaubte_netze(tmp_path, adresse, erlaubt):
    c = neue_config(tmp_path, erlaubte_netze=["192.168.0.0/16", "::1/128"])
    api = Api(c, client=(adresse, 50000))
    for pfad in ("/api/status", "/api/gesundheit", "/api/anmeldung"):
        r = api.get(pfad)
        if erlaubt:
            assert r.status_code == 200, (adresse, pfad)
        else:
            assert r.status_code == 403 and fehlercode(r) == "netz_nicht_erlaubt", (adresse, pfad, r.status_code)
    r = api.client.get("/", follow_redirects=False)
    assert (r.status_code == 200) is erlaubt
    if not erlaubt:
        assert r.status_code == 403
        r = api.get("/api/status", headers={"x-forwarded-for": "192.168.1.1", "forwarded": "for=192.168.1.1"})
        assert r.status_code == 403, "weitergeleitete Köpfe zählen nicht"


def test_netz_vor_anmeldung(tmp_path):
    api = m7_api(tmp_path, erlaubte_netze=["192.168.0.0/16"], client_kw={"client": ("203.0.113.9", 4711)})
    r = api.post("/api/anmeldung", json={"passwort": PASSWORT})
    assert r.status_code == 403 and fehlercode(r) == "netz_nicht_erlaubt"


# ------------------------------------------------------------------ Geheimnisse
def test_keine_geheimnisse_in_logs(tmp_path, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    c = m7_config(tmp_path, passwort=None, anmeldung_fehlversuche=10)
    api = Api(c)
    code = einrichtungsdatei(c).read_text(encoding="ascii").strip()
    falsch = "Falsches-Passwort-Logtest-1"
    api.post("/api/anmeldung/einrichten", json={"einrichtungscode": "1" * 32, "passwort": PASSWORT}, erwartet=403)
    r = api.post("/api/anmeldung/einrichten", json={"einrichtungscode": code, "passwort": PASSWORT}, erwartet=200)
    api.csrf = r.daten["csrf_token"]
    andere = zweiter_client(api)
    anmelden(andere, falsch, erwartet=401)
    anmelden(andere)
    api.konto("Giro")
    api.put("/api/anmeldung/passwort", json={"altes_passwort": PASSWORT, "neues_passwort": NEUES_PASSWORT},
            erwartet=200)
    api.post("/api/anmeldung", json={"passwort": "x", "zusatz": NEUES_PASSWORT}, erwartet=422)
    geheim = [PASSWORT, NEUES_PASSWORT, falsch, code, sitzungstoken(api), sitzungstoken(andere), api.csrf,
              andere.csrf]
    aus = capfd.readouterr()
    text = caplog.text + "\n".join(r.getMessage() for r in caplog.records) + aus.out + aus.err
    for g in geheim:
        assert g and g not in text, f"Geheimnis im Log: {g[:6]}…"
    assert "Traceback" not in text
