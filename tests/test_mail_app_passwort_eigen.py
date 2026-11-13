"""Entwicklungstests für das Feature „gmail-app-passwort“ (D-130): IMAP-Anmeldung mit App-Passwort und Ordner
(Gmail-Label) gegen eine kleine Loopback-Attrappe; nie gegen Gmail. Synthetische Daten."""

from __future__ import annotations

import datetime as dt
import email.utils
import re
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from kontor import anmeldung, db
from kontor.app import create_app
from kontor.config import KontorConfig

ADRESSE = "erika@example.invalid"
APP_PW = "abcd efgh ijkl mnop"   # wie Google es anzeigt: Vierergruppen mit Leerzeichen
JETZT = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(days=1)
MAIL = (b"From: service@paypal.example.invalid\r\nTo: erika@example.invalid\r\nSubject: Test (fiktiv)\r\n"
        b"Message-ID: <t1@example.invalid>\r\nDate: " + email.utils.format_datetime(JETZT).encode()
        + b"\r\n\r\nHallo (fiktiv)\r\n")
INTERN = JETZT.strftime("%d-%b-%Y %H:%M:%S +0000").encode()


class Attrappe(threading.Thread):
    """Minimaler IMAP-Server: LOGIN, EXAMINE, UID SEARCH/FETCH; merkt sich die Befehle (ohne Passwort)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.befehle: list[str] = []
        self.logins: list[tuple[str, str]] = []

    def run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(c,), daemon=True).start()

    def _sitzung(self, c):
        f = c.makefile("rwb")
        f.write(b"* OK Attrappe bereit\r\n")
        f.flush()
        angemeldet = False
        for zeile in f:
            z = zeile.decode().rstrip("\r\n")
            tag, _, rest = z.partition(" ")
            befehl = rest.split(" ")[0].upper()
            self.befehle.append(befehl if befehl != "UID" else " ".join(rest.split(" ")[:2]).upper())
            if befehl == "CAPABILITY":
                f.write(b"* CAPABILITY IMAP4rev1 AUTH=PLAIN\r\n" + tag.encode() + b" OK fertig\r\n")
            elif befehl == "LOGIN":
                teile = re.findall(r'"((?:[^"\\]|\\.)*)"|(\S+)', rest[6:])
                user, pw = [a or b for a, b in teile][:2]
                self.logins.append((user, pw))
                angemeldet = pw == APP_PW.replace(" ", "")
                f.write(tag.encode() + (b" OK angemeldet\r\n" if angemeldet else b" NO [AUTHENTICATIONFAILED] nein\r\n"))
            elif befehl in ("EXAMINE", "SELECT") and angemeldet:
                if '"Kontor"' in rest:
                    f.write(b"* 1 EXISTS\r\n* OK [UIDVALIDITY 7] ok\r\n" + tag.encode() + b" OK [READ-ONLY] ok\r\n")
                else:
                    f.write(tag.encode() + b" NO unbekannt\r\n")
            elif befehl == "UID" and "SEARCH" in rest.upper():
                f.write(b"* SEARCH 1\r\n" + tag.encode() + b" OK ok\r\n")
            elif befehl == "UID" and "FETCH" in rest.upper():
                f.write(b'* 1 FETCH (UID 1 INTERNALDATE "' + INTERN + b'" BODY[] {'
                        + str(len(MAIL)).encode() + b"}\r\n" + MAIL + b")\r\n" + tag.encode() + b" OK ok\r\n")
            elif befehl == "LOGOUT":
                f.write(b"* BYE\r\n" + tag.encode() + b" OK tschuess\r\n")
                f.flush()
                break
            else:
                f.write(tag.encode() + b" BAD unbekannt\r\n")
            f.flush()
        c.close()


@pytest.fixture
def umgebung(tmp_path):
    imap = Attrappe()
    imap.start()
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=False, planer_starten=False,
                       imap_host="127.0.0.1", imap_port=imap.port, imap_tls=False)
    c = TestClient(create_app(cfg))
    r = c.post("/api/mail/postfaecher", json={"adresse": ADRESSE, "ordner": "Kontor"})
    assert r.status_code == 201, r.text
    yield c, cfg, imap, r.json()["id"], tmp_path
    imap.sock.close()


def test_app_passwort_pruefen_speichern_und_abrufen(umgebung):
    c, cfg, imap, pid, _ = umgebung
    r = c.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": "falsch"})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "mail_anmeldung_abgelehnt", r.text
    assert "falsch" not in r.text
    assert c.get(f"/api/mail/postfaecher/{pid}/status").json()["anmeldung"] == "fehlt"
    r = c.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": APP_PW})
    assert r.status_code == 200, r.text
    assert r.json()["nachrichten_im_ordner"] == 1
    st = c.get(f"/api/mail/postfaecher/{pid}/status").json()
    assert st["anmeldung"] == "angemeldet" and st["laeuft_ab_am"] is None
    r = c.post("/api/mail/abruf")
    assert r.status_code == 200, r.text
    (e,) = r.json()["postfaecher"]
    assert e["status"] == "erfolgreich" and e["nachrichten_neu"] == 1, e
    assert "EXAMINE" in imap.befehle and "SELECT" not in imap.befehle and "STORE" not in imap.befehle
    con = db.verbinde(cfg.aktive_datenbank)
    roh = b"".join(bytes(x[0]) for x in con.execute("SELECT chiffre FROM geheimnis"))
    con.close()
    assert b"abcdefghijklmnop" not in roh
    assert c.delete(f"/api/mail/postfaecher/{pid}/app-passwort").status_code == 204
    assert c.get(f"/api/mail/postfaecher/{pid}/status").json()["anmeldung"] == "fehlt"


def test_unbekanntes_label(umgebung):
    c, _, _, pid, _ = umgebung
    assert c.patch(f"/api/mail/postfaecher/{pid}", json={"ordner": "Gibt-es-nicht"}).status_code == 200
    r = c.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": APP_PW})
    assert r.status_code == 422 and r.json()["fehler"]["code"] == "mail_ordner_unbekannt", r.text


def test_mit_schutz_gesperrt_kein_abruf(umgebung):
    c, cfg, _, pid, tmp_path = umgebung
    anmeldung.passwort_setzen(cfg, "ein-langes-testpasswort-1")
    assert c.post("/api/geheimnisse/schutz", json={"passwort": "ein-langes-testpasswort-1"}).status_code == 200
    assert c.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": APP_PW}).status_code == 200
    c2 = TestClient(create_app(cfg))                         # Neustart: gesperrt
    assert c2.post("/api/mail/abruf").status_code == 409
    assert c2.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": APP_PW}).status_code == 409
    c2.post("/api/geheimnisse/entsperren", json={"passwort": "ein-langes-testpasswort-1"})
    assert c2.post("/api/mail/abruf").json()["postfaecher"][0]["status"] == "erfolgreich"


def test_mock_modus_ohne_app_passwort(tmp_path):
    c = TestClient(create_app(KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, planer_starten=False)))
    pid = c.post("/api/mail/postfaecher", json={"adresse": ADRESSE}).json()["id"]
    assert c.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": APP_PW}).status_code == 409
