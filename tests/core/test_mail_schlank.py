"""Core-Tests zum Feature „mail-schlank“ (D-255): Mails brauchen weniger Platz in der Datenbank.

- Mail-Dokumente (``message/rfc822``) liegen komprimiert in ``dokument_inhalt``; geliefert werden unverändert die
  Originalbytes, die Prüfsumme bleibt die des Originals. PDF und Bilder bleiben unkomprimiert.
- Die Datensicherung enthält die Originalbytes (Format unverändert); nach dem Einspielen liegt der Inhalt wieder
  komprimiert vor.
- Die Rohfassung im Mail-Spiegel ist komprimiert. Ist die Mail als Dokument angehängt, verweist der Spiegel nur noch
  auf den Inhalt des Dokuments (keine zweite Kopie); erneutes Anhängen liefert dieselben Bytes.
- Ein Bestand aus der Zeit davor wird beim Start umgestellt; die Datenbank gibt freien Platz zurück
  (``auto_vacuum = INCREMENTAL``, keine nennenswerten freien Seiten danach).
"""

from __future__ import annotations

import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from kontor import db, sicherung
from kontor.app import create_app
from kontor.config import KontorConfig

PDF = b"%PDF-1.4\n" + bytes(range(256)) * 40 + b"\n%%EOF\n"


def _mail(nid: str = "<m1@example.invalid>", wdh: int = 400) -> bytes:
    """Synthetische HTML-Mail, gut komprimierbar wie echte Bestellmails."""
    html = "<tr><td>Artikel (fiktiv)</td><td>9,99 €</td></tr>" * wdh
    return (f"From: bestellung@laden.example.invalid\r\nTo: erika@example.invalid\r\nSubject: Bestellung (fiktiv)"
            f"\r\nMessage-ID: {nid}\r\nMIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            f"<html><body><table>{html}</table></body></html>\r\n").encode()


def _cfg(tmp_path, name="k.sqlite3", **kw) -> KontorConfig:
    return KontorConfig(datenbank=tmp_path / name, planer_starten=False, **kw)


def _buchung(c: TestClient, datum: str = "2024-03-01") -> int:
    """Buchung Giro → Lebensmittel; die Konten werden beim ersten Aufruf angelegt."""
    konten = c.get("/api/konten").json()
    liste = konten if isinstance(konten, list) else konten.get("eintraege", [])
    ids = []
    for name, art in (("Giro", "girokonto"), ("Lebensmittel", "aufwand")):
        k = next((k["id"] for k in liste if k["name"] == name and k.get("extern_id") is None), None)
        if k is None:
            r = c.post("/api/konten", json={"name": name, "art": art})
            assert r.status_code == 201, r.text
            k = r.json()["id"]
        ids.append(k)
    r = c.post("/api/buchungen", json={"datum": datum, "splits": [
        {"konto_id": ids[0], "betrag": -999}, {"konto_id": ids[1], "betrag": 999}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _hochladen(c: TestClient, bid: int, inhalt: bytes, name: str) -> dict:
    r = c.post(f"/api/dokumente?buchung_id={bid}", files={"datei": (name, inhalt)})
    assert r.status_code == 201, r.text
    return r.json()


def _gespeichert(cfg, sha: str) -> int:
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        return con.execute("SELECT length(inhalt) FROM dokument_inhalt WHERE sha256 = ?", (sha,)).fetchone()[0]
    finally:
        con.close()


def _inhalt(c: TestClient, did: int) -> bytes:
    r = c.get(f"/api/dokumente/{did}/inhalt")
    assert r.status_code == 200, r.text
    return r.content


def test_mail_dokument_komprimiert_pdf_unveraendert(tmp_path):
    cfg = _cfg(tmp_path)
    c = TestClient(create_app(cfg))
    bid = _buchung(c)
    mail, pdf = _mail(), PDF
    dm, dp = _hochladen(c, bid, mail, "bestellung.eml"), _hochladen(c, bid, pdf, "rechnung.pdf")
    assert dm["mime_typ"] == "message/rfc822" and dm["groesse"] == len(mail)
    assert dm["sha256"] == hashlib.sha256(mail).hexdigest()
    assert _inhalt(c, dm["id"]) == mail and _inhalt(c, dp["id"]) == pdf
    assert _gespeichert(cfg, dm["sha256"]) < len(mail) // 4, "Mail komprimiert gespeichert"
    assert _gespeichert(cfg, dp["sha256"]) == len(pdf), "PDF unverändert gespeichert"
    # gleicher Inhalt noch einmal: wird erkannt (inhaltsadressiert), nicht doppelt gespeichert
    assert _hochladen(c, bid, mail, "nochmal.eml")["sha256"] == dm["sha256"]


def test_sicherung_mit_originalbytes_und_einspielen(tmp_path):
    cfg = _cfg(tmp_path)
    c = TestClient(create_app(cfg))
    mail = _mail()
    dm = _hochladen(c, _buchung(c), mail, "bestellung.eml")
    roh = c.get("/api/sicherung").content
    s = sicherung.pruefen(roh)   # prüft u. a. sha256(inhalt) == sha256 je Inhalt
    assert dict(s.zeilen["dokument_inhalt"])[dm["sha256"]] == mail
    cfg2 = _cfg(tmp_path, "neu.sqlite3")
    c2 = TestClient(create_app(cfg2))
    r = c2.post("/api/sicherung/einspielen?bestaetigt=true", files={"datei": ("s.zip", roh)})
    assert r.status_code == 200, r.text
    assert _inhalt(c2, dm["id"]) == mail
    assert _gespeichert(cfg2, dm["sha256"]) < len(mail) // 4


def _spiegeln(cfg, roh: bytes, nid: str) -> int:
    """Mail im Spiegel wie vor diesem Feature: Rohfassung unkomprimiert, ohne Angabe eines Verfahrens."""
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        with db.transaktion(con):
            return con.execute(
                "INSERT INTO mail_nachricht (adresse_cf, nachricht_id, empfangen, absender, betreff, text, roh)"
                " VALUES ('erika@example.invalid', ?, '2024-03-01T10:00:00Z', 'bestellung@laden.example.invalid',"
                " 'Bestellung (fiktiv)', 'Artikel', ?)", (nid, roh)).lastrowid
    finally:
        con.close()


def _altbestand(cfg) -> None:
    """Bestand wie vor diesem Feature: Inhalte unkomprimiert, kein Verfahren vermerkt, ohne auto_vacuum."""
    con = sqlite3.connect(cfg.aktive_datenbank, isolation_level=None)
    try:
        for sha, inhalt in con.execute("SELECT sha256, inhalt FROM dokument_inhalt").fetchall():
            con.execute("UPDATE dokument_inhalt SET inhalt = ?, verfahren = NULL WHERE sha256 = ?",
                        (_original(cfg, sha), sha))
        con.execute("PRAGMA journal_mode = DELETE")
        con.execute("PRAGMA auto_vacuum = NONE")
        con.execute("VACUUM")
    finally:
        con.close()


_ORIGINALE: dict[str, bytes] = {}


def _original(cfg, sha: str) -> bytes:
    return _ORIGINALE[sha]


def _db_wert(cfg, sql: str, *par):
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        return con.execute(sql, par).fetchone()
    finally:
        con.close()


def test_spiegel_komprimiert_und_verweist_nach_anhaengen(tmp_path):
    cfg = _cfg(tmp_path, mock_modus=True)
    c = TestClient(create_app(cfg))
    assert c.post("/api/mail/postfaecher", json={"adresse": "erika@example.invalid"}).status_code == 201
    bid = _buchung(c)
    mail = _mail("<s1@example.invalid>")
    sid = _spiegeln(cfg, mail, "<s1@example.invalid>")
    c = TestClient(create_app(cfg))   # Neustart: der Bestand wird umgestellt
    laenge = _db_wert(cfg, "SELECT length(roh) FROM mail_nachricht WHERE id = ?", sid)[0]
    assert laenge < len(mail) // 4, "Rohfassung im Spiegel komprimiert"

    r = c.post(f"/api/mail/nachrichten/{sid}/buchung", json={"buchung_id": bid})
    assert r.status_code == 201, r.text
    docs = c.get(f"/api/buchungen/{bid}/dokumente").json()["eintraege"]
    assert len(docs) == 1 and _inhalt(c, docs[0]["id"]) == mail
    roh, sha = _db_wert(cfg, "SELECT roh, roh_sha256 FROM mail_nachricht WHERE id = ?", sid)
    assert roh is None and sha == hashlib.sha256(mail).hexdigest(), "Spiegel verweist auf das Dokument"

    # noch einmal anhängen (andere Buchung): dieselben Bytes aus dem Verweis
    bid2 = _buchung(c, "2024-03-02")
    r = c.post("/api/dokumente/aus-mail", json={"nachricht_id": sid, "buchung_ids": [bid2]})
    assert r.status_code == 201, r.text
    assert r.json()["sha256"] == sha and _inhalt(c, r.json()["id"]) == mail


def test_neuer_abruf_speichert_rohfassung_komprimiert(tmp_path):
    import datetime as dt

    from kontor.plugins.mail import MailNachricht, MailPlugin, mit_roh

    mail = _mail("<a1@example.invalid>")

    class Attrappe(MailPlugin):
        name = "mock"
        ist_mock = True

        def postfaecher(self):
            return ["erika@example.invalid"]

        def nachrichten(self, postfach, seit):
            return [mit_roh(MailNachricht("<a1@example.invalid>", postfach,
                                          dt.datetime(2026, 11, 10, 9, tzinfo=dt.timezone.utc),
                                          "bestellung@laden.example.invalid", "Bestellung (fiktiv)", "Artikel"), mail)]

    cfg = _cfg(tmp_path, mock_modus=True, mock_heute=dt.date(2026, 11, 20))
    c = TestClient(create_app(cfg))
    assert c.post("/api/mail/postfaecher", json={"adresse": "erika@example.invalid"}).status_code == 201
    c.app.state.sync.mail._mock_plugin = Attrappe()
    assert c.post("/api/mail/abruf").json()["postfaecher"][0]["nachrichten_neu"] == 1
    sid, laenge = _db_wert(cfg, "SELECT id, length(roh) FROM mail_nachricht")
    assert laenge < len(mail) // 4
    bid = _buchung(c)
    r = c.post("/api/dokumente/aus-mail", json={"nachricht_id": sid, "buchung_ids": [bid]})
    assert r.status_code == 201, r.text
    assert _inhalt(c, r.json()["id"]) == mail


def test_altbestand_wird_umgestellt_und_verkleinert(tmp_path):
    cfg = _cfg(tmp_path)
    c = TestClient(create_app(cfg))
    bid = _buchung(c)
    mails = [_mail(f"<x{i}@example.invalid>", 600 + i) for i in range(6)]
    docs = []
    for i, m in enumerate(mails):
        d = _hochladen(c, bid, m, f"m{i}.eml")
        _ORIGINALE[d["sha256"]] = m
        docs.append(d)
    d = _hochladen(c, bid, PDF, "r.pdf")
    _ORIGINALE[d["sha256"]] = PDF
    del c
    _altbestand(cfg)
    assert _db_wert(cfg, "SELECT length(inhalt) FROM dokument_inhalt WHERE sha256 = ?", docs[0]["sha256"])[0] \
        == len(mails[0])

    c = TestClient(create_app(cfg))   # Neustart: umstellen und Platz zurückgeben
    for d, m in zip(docs, mails):
        assert _inhalt(c, d["id"]) == m
        assert _gespeichert(cfg, d["sha256"]) < len(m) // 4
    assert _gespeichert(cfg, hashlib.sha256(PDF).hexdigest()) == len(PDF)
    assert _db_wert(cfg, "PRAGMA auto_vacuum")[0] == 2, "auto_vacuum = INCREMENTAL"
    seiten, frei = _db_wert(cfg, "PRAGMA page_count")[0], _db_wert(cfg, "PRAGMA freelist_count")[0]
    assert frei <= max(8, seiten // 10), (seiten, frei)
    # ein zweiter Start ändert nichts mehr
    vorher = (tmp_path / "k.sqlite3").stat().st_size
    TestClient(create_app(cfg))
    assert (tmp_path / "k.sqlite3").stat().st_size <= vorher


@pytest.mark.parametrize("verfahren", ["", None])
def test_unkomprimierter_spiegel_bleibt_lesbar(tmp_path, verfahren):
    """Zeilen, die (noch) unkomprimiert sind, liefern ihre Bytes unverändert (z. B. Tests, Altbestand)."""
    cfg = _cfg(tmp_path, mock_modus=True)
    c = TestClient(create_app(cfg))
    assert c.post("/api/mail/postfaecher", json={"adresse": "erika@example.invalid"}).status_code == 201
    mail = _mail("<u1@example.invalid>", 5)
    sid = _spiegeln(cfg, mail, "<u1@example.invalid>")
    if verfahren is not None:
        con = db.verbinde(cfg.aktive_datenbank)
        con.execute("UPDATE mail_nachricht SET roh_verfahren = ? WHERE id = ?", (verfahren, sid))
        con.close()
    r = c.post("/api/dokumente/aus-mail", json={"nachricht_id": sid, "buchung_ids": [_buchung(c)]})
    assert r.status_code == 201, r.text
    assert _inhalt(c, r.json()["id"]) == mail
