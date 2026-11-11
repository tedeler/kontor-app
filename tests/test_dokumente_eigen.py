"""Entwicklungstests für das Feature „dokumente“ (Branch feature/dokumente, D-123): Dokumente an Buchungen über
REST, Protokoll und Rückgängig, Sicherung, E-Mail-Anzeige. Synthetische Daten; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import datetime as dt
import hashlib
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from kontor import dokumente
from kontor.app import create_app
from kontor.config import KontorConfig

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n" \
      b"trailer<</Root 1 0 R>>\n%%EOF\n"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


def mail_bytes() -> bytes:
    m = EmailMessage()
    m["From"] = "Fiktiver Shop <shop@example.invalid>"
    m["To"] = "erika@example.invalid"
    m["Subject"] = "Ihre Rechnung Nr. 4711 (Testdaten)"
    m["Date"] = "Tue, 05 Mar 2024 10:15:00 +0100"
    m["Message-ID"] = "<rechnung-4711@example.invalid>"
    m.set_content("Hallo Erika,\nanbei die Rechnung.\n")
    m.add_alternative('<html><body><p onclick="alert(1)">Hallo <b>Erika</b></p><script>alert(2)</script>'
                      '<img src="cid:logo"><img src="https://tracker.example.invalid/p.gif">'
                      '<a href="javascript:alert(3)">x</a></body></html>', subtype="html")
    m.get_payload()[1].add_related(PNG, "image", "png", cid="<logo>")
    m.add_attachment(PDF, maintype="application", subtype="pdf", filename="Rechnung-4711.pdf")
    return m.as_bytes()


@pytest.fixture
def c(tmp_path) -> TestClient:
    k = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True,
                                           mock_heute=dt.date(2024, 6, 30))))
    assert k.post("/api/sync", json={"von": "2024-01-01"}).status_code == 200
    return k


def _buchungen(c, n=3):
    return [b["id"] for b in c.get("/api/buchungen", params={"pro_seite": n}).json()["eintraege"]]


def _hoch(c, ids, daten, name="beleg.pdf", **params):
    return c.post("/api/dokumente", params={"buchung_id": ids, **params}, files={"datei": (name, daten, "x/y")})


def test_typ_erkennen_und_dateiname():
    assert dokumente.typ_erkennen(PDF) == dokumente.PDF
    assert dokumente.typ_erkennen(PNG) == dokumente.PNG
    assert dokumente.typ_erkennen(b"\xff\xd8\xff\xe0rest") == dokumente.JPEG
    assert dokumente.typ_erkennen(mail_bytes()) == dokumente.MAIL
    assert dokumente.typ_erkennen(b"Hallo: Welt\nkein Mailkopf") is None
    assert dokumente.typ_erkennen(b"MZ\x90\x00") is None
    assert dokumente.dateiname_saeubern("../../etc/pass\x00wd", dokumente.PDF) == "passwd.pdf"
    assert dokumente.dateiname_saeubern("Scan.JPEG", dokumente.JPEG) == "Scan.JPEG"
    assert dokumente.dateiname_saeubern("", dokumente.JPEG) == "Foto.jpg"
    assert len(dokumente.dateiname_saeubern("a" * 500, dokumente.PDF)) == 200


def test_anhaengen_mehrfach_loesen_rueckgaengig(c):
    b1, b2, _ = _buchungen(c)
    r = _hoch(c, [b1, b2], PDF, "Rechnung März.pdf")
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["mime_typ"], d["groesse"], d["buchung_ids"], d["dateiname"]) == (
        "application/pdf", len(PDF), sorted([b1, b2]), "Rechnung März.pdf")
    assert d["sha256"] == hashlib.sha256(PDF).hexdigest()
    beleg = {"id": d["id"], "dateiname": "Rechnung März.pdf", "mime_typ": "application/pdf", "groesse": len(PDF)}
    assert c.get(f"/api/buchungen/{b1}").json()["belege"] == [beleg]
    inhalt = c.get(f"/api/dokumente/{d['id']}/inhalt")
    assert inhalt.content == PDF and inhalt.headers["content-type"] == "application/pdf"
    assert inhalt.headers["x-frame-options"] == "SAMEORIGIN" and "x-kontor-einbettbar" not in inhalt.headers
    assert "sandbox" in inhalt.headers["content-security-policy"]
    # lösen: an b2 bleibt es, an b1 nicht mehr
    r = c.delete(f"/api/dokumente/{d['id']}/buchungen/{b1}")
    assert r.json() == {"dokument_id": d["id"], "buchung_ids": [b2], "geloescht": False, "aenderung_id": None} or \
        r.json()["buchung_ids"] == [b2]
    assert c.get(f"/api/buchungen/{b1}").json()["belege"] == []
    # letztes Lösen löscht das Dokument; Rückgängig stellt es samt Verknüpfung wieder her
    r = c.delete(f"/api/dokumente/{d['id']}/buchungen/{b2}")
    assert r.json()["geloescht"] is True
    assert c.get(f"/api/dokumente/{d['id']}").status_code == 404
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert a["aktion"] == "dokument_loesen"
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    assert c.get(f"/api/dokumente/{d['id']}").json()["buchung_ids"] == [b2]
    assert c.get(f"/api/dokumente/{d['id']}/inhalt").content == PDF


def test_buchung_loeschen_nimmt_dokument_mit_und_rueckgaengig(c):
    b1 = _buchungen(c, 1)[0]
    d = _hoch(c, [b1], PNG, "kassenbon.png", quelle="kamera").json()
    assert d["quelle"] == "kamera"
    assert c.delete(f"/api/buchungen/{b1}").status_code == 204
    assert c.get(f"/api/dokumente/{d['id']}").status_code == 404
    a = c.get("/api/aenderungen", params={"pro_seite": 1}).json()["eintraege"][0]
    assert {e["objekt"] for e in c.get(f"/api/aenderungen/{a['id']}").json()["eintraege"]} == {"buchung", "dokument"}
    assert c.post(f"/api/aenderungen/{a['id']}/rueckgaengig").status_code == 200
    assert c.get(f"/api/buchungen/{b1}").json()["belege"][0]["id"] == d["id"]


def test_fehlerfaelle(c):
    b1 = _buchungen(c, 1)[0]
    assert _hoch(c, [b1], b"MZ\x90\x00binaer").json()["fehler"]["code"] == "dokument_typ_unbekannt"
    assert _hoch(c, [b1], b"").json()["fehler"]["code"] == "dokument_leer"
    assert _hoch(c, [], PDF).status_code == 422
    assert _hoch(c, [999999], PDF).status_code == 404
    assert c.get("/api/dokumente/424242/inhalt").status_code == 404


def test_mail_anzeige_html_entschaerft_und_anhaenge(c):
    b1 = _buchungen(c, 1)[0]
    d = _hoch(c, [b1], mail_bytes(), "rechnung").json()
    assert d["mime_typ"] == "message/rfc822" and d["dateiname"] == "rechnung.eml"
    m = c.get(f"/api/dokumente/{d['id']}/mail").json()
    assert m["betreff"] == "Ihre Rechnung Nr. 4711 (Testdaten)"
    assert m["von"] == [{"name": "Fiktiver Shop", "adresse": "shop@example.invalid"}]
    assert m["datum"] == "2024-03-05T09:15:00Z" and m["html"] is True and "anbei die Rechnung" in m["text"]
    pdfs = [a for a in m["anhaenge"] if a["mime_typ"] == "application/pdf"]
    assert [a["dateiname"] for a in pdfs] == ["Rechnung-4711.pdf"]
    h = c.get(f"/api/dokumente/{d['id']}/mail/html")
    assert h.headers["content-type"].startswith("text/html")
    csp = h.headers["content-security-policy"]
    assert "sandbox" in csp and "img-src data:" in csp and "script-src" not in csp
    t = h.text
    assert "<script" not in t and "alert(2)" not in t and "onclick" not in t and "javascript:" not in t
    assert "tracker.example.invalid" not in t
    assert "data:image/png;base64," in t and "cid:logo" not in t
    a = c.get(f"/api/dokumente/{d['id']}/mail/anhaenge/{pdfs[0]['nr']}")
    assert a.content == PDF and a.headers["content-type"] == "application/pdf"
    # E-Mails werden nie als Seite ausgeliefert
    assert c.get(f"/api/dokumente/{d['id']}/inhalt").headers["content-type"] == "application/octet-stream"


def test_mail_aus_postfach(c):
    assert c.post("/api/mail/postfaecher", json={"adresse": "haushalt.eins@example.invalid"}).status_code == 201
    assert c.post("/api/mail/abruf").json()["postfaecher"][0]["status"] == "erfolgreich"
    n = c.get("/api/mail/nachrichten", params={"pro_seite": 1}).json()["eintraege"][0]
    b1 = _buchungen(c, 1)[0]
    r = c.post("/api/dokumente/aus-mail", json={"nachricht_id": n["id"], "buchung_ids": [b1]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["quelle"], d["mime_typ"]) == ("mail", "message/rfc822")
    m = c.get(f"/api/dokumente/{d['id']}/mail").json()
    assert m["betreff"] == n["betreff"] and m["text"].strip() == n["text"].strip()


def test_sicherung_rundreise_mit_dokumenten(c, tmp_path):
    b1, b2, _ = _buchungen(c)
    d = _hoch(c, [b1, b2], PDF).json()
    _hoch(c, [b2], mail_bytes(), "rechnung.eml")
    s = c.get("/api/sicherung").content
    ziel = TestClient(create_app(KontorConfig(datenbank=tmp_path / "z.sqlite3", mock_modus=True,
                                              mock_heute=dt.date(2024, 6, 30))))
    r = ziel.post("/api/sicherung/einspielen", params={"bestaetigt": "true"},
                  files={"datei": ("s.zip", s, "application/zip")})
    assert r.status_code == 200, r.text
    assert ziel.get(f"/api/dokumente/{d['id']}/inhalt").content == PDF
    assert ziel.get(f"/api/buchungen/{b2}").json()["belege"] == c.get(f"/api/buchungen/{b2}").json()["belege"]
