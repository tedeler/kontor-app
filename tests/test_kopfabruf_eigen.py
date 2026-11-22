"""Entwicklungstests für das Feature „kopfabruf“ (D-243): vom Postfach zuerst nur Kopfzeilen, der Inhalt nur für
Mails, die die Pflicht-Vorauswahl einer Anbieter-Beschreibung erfüllen, sonst erst bei Bedarf. Synthetische Daten;
ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import datetime as dt
from importlib import resources

import pytest
from fastapi.testclient import TestClient

from kontor import anbieter, db
from kontor.app import create_app
from kontor.config import KontorConfig, KonfigurationsFehler
from kontor.plugins.mail import MailKopf, MailNachricht, MailPlugin, mit_roh

UTC = dt.timezone.utc
NR = "302-1234567-7654321"
PF = "erika@example.invalid"


def nachricht(nid, absender, betreff, text, tag=10):
    roh = (f"From: {absender}\r\nSubject: {betreff}\r\nMessage-ID: {nid}\r\n\r\n{text}\r\n").encode()
    return mit_roh(MailNachricht(nid, PF, dt.datetime(2026, 11, tag, 9, 0, tzinfo=UTC), absender, betreff, text), roh)


class Attrappe(MailPlugin):
    """Mail-Plugin im Arbeitsspeicher; merkt sich, welche Inhalte verlangt wurden."""
    name = "mock"
    ist_mock = True
    kann_koepfe = True

    def __init__(self, liste):
        self.liste = list(liste)
        self.verlangt: list[list[str]] = []
        self.voll_abgerufen = 0

    def postfaecher(self):
        return [PF]

    def nachrichten(self, postfach, seit):
        self.voll_abgerufen += 1
        return [n for n in self.liste if n.empfangen >= seit]

    def koepfe(self, postfach, seit):
        return [MailKopf(n.nachricht_id, n.postfach, n.empfangen, n.absender, n.betreff, f"7:{i}")
                for i, n in enumerate(self.liste) if n.empfangen >= seit]

    def inhalte(self, postfach, koepfe):
        self.verlangt.append(sorted(k.nachricht_id for k in koepfe))
        je_id = {n.nachricht_id: n for n in self.liste}
        return {k.nachricht_id: je_id[k.nachricht_id] for k in koepfe if k.nachricht_id in je_id}


MAILS = [
    nachricht("<a1@x.invalid>", "bestellung@amazon.example.invalid", f"Bestellt: Kabel {NR}",
              f"Bestellnummer {NR}\nGesamtsumme: 9,99 €"),
    nachricht("<n1@x.invalid>", "news@laden.example.invalid", "Unser Angebot der Woche", "viel Text"),
    nachricht("<n2@x.invalid>", "freund@example.invalid", f"Weitergeleitet: Bestellung {NR}", "Text mit Anhang"),
    nachricht("<n3@x.invalid>", "verein@example.invalid", "Einladung", "Bitte kommen", tag=11),
]


@pytest.fixture
def umgebung(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2026, 11, 20),
                       planer_starten=False, mail_nur_koepfe=True, mail_bestellnummer=True)
    c = TestClient(create_app(cfg))
    assert c.post("/api/mail/postfaecher", json={"adresse": PF}).status_code == 201
    p = Attrappe(MAILS)
    c.app.state.sync.mail._mock_plugin = p
    return c, cfg, p


def spiegel(cfg):
    con = db.verbinde(cfg.aktive_datenbank)
    try:
        return {r["nachricht_id"]: dict(r) for r in con.execute("SELECT * FROM mail_nachricht")}
    finally:
        con.close()


def test_einstellung_und_ausgelieferte_umgebung():
    env = {"KONTOR_DATENBANK": "/tmp/x.sqlite3"}
    assert KontorConfig.from_env(env).mail_nur_koepfe is False
    assert KontorConfig.from_env({**env, "KONTOR_MAIL_NUR_KOEPFE": "1"}).mail_nur_koepfe is True
    with pytest.raises(KonfigurationsFehler):
        KontorConfig.from_env({**env, "KONTOR_MAIL_NUR_KOEPFE": "vielleicht"})
    for datei in ("kontor.env", "kontor-test.env"):
        text = resources.files("kontor.betrieb").joinpath(datei).read_text(encoding="utf-8")
        assert "\nKONTOR_MAIL_NUR_KOEPFE=1\n" in text


def test_abruf_laedt_inhalt_nur_fuer_vorauswahl_und_kennung_im_betreff(umgebung):
    c, cfg, p = umgebung
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["status"] == "erfolgreich" and erg["nachrichten_neu"] == 4
    assert erg["nachrichten_ohne_inhalt"] == 2 and erg["nachrichten_nachgeladen"] == 0
    assert p.voll_abgerufen == 0
    # Amazon nach der Vorauswahl (Absender), die weitergeleitete Mail wegen der Bestellnummer im Betreff
    assert p.verlangt == [["<a1@x.invalid>", "<n2@x.invalid>"]]
    s = spiegel(cfg)
    assert s["<a1@x.invalid>"]["inhalt"] == 1 and "Gesamtsumme" in s["<a1@x.invalid>"]["text"]
    assert s["<a1@x.invalid>"]["roh"] and s["<a1@x.invalid>"]["ort"] == "7:0"
    assert s["<n1@x.invalid>"]["inhalt"] == 0 and s["<n1@x.invalid>"]["text"] == "" and s["<n1@x.invalid>"]["roh"] is None
    assert s["<n1@x.invalid>"]["betreff"] == "Unser Angebot der Woche"
    liste = c.get("/api/mail/nachrichten").json()["eintraege"]
    ohne = {e["nachricht_id"] for e in liste if e.get("ohne_inhalt")}
    assert ohne == {"<n1@x.invalid>", "<n3@x.invalid>"}
    assert all("ohne_inhalt" not in e for e in liste if e["nachricht_id"] not in ohne)
    # zweiter Abruf: nichts Neues, nichts nachzuladen
    p.verlangt.clear()
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["nachrichten_neu"] == 0 and p.verlangt == []


def test_inhalt_bei_bedarf(umgebung):
    c, cfg, p = umgebung
    c.post("/api/mail/abruf")
    nid = spiegel(cfg)["<n1@x.invalid>"]["id"]
    r = c.post(f"/api/mail/nachrichten/{nid}/inhalt")
    assert r.status_code == 200, r.text
    assert r.json() == {"id": nid, "text": "viel Text", "nachgeladen": True}
    assert spiegel(cfg)["<n1@x.invalid>"]["inhalt"] == 1
    assert c.post(f"/api/mail/nachrichten/{nid}/inhalt").json()["nachgeladen"] is False
    assert c.post("/api/mail/nachrichten/999999/inhalt").status_code == 404
    # im Postfach gelöscht: nicht mehr nachzuladen
    n3 = spiegel(cfg)["<n3@x.invalid>"]["id"]
    p.liste = [n for n in p.liste if n.nachricht_id != "<n3@x.invalid>"]
    r = c.post(f"/api/mail/nachrichten/{n3}/inhalt")
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "mail_nicht_mehr_vorhanden"


def test_von_hand_anhaengen_laedt_den_inhalt(umgebung):
    c, cfg, p = umgebung
    c.post("/api/mail/abruf")
    giro = c.post("/api/konten", json={"name": "Giro Kopf", "art": "girokonto"}).json()["id"]
    kat = c.post("/api/konten", json={"name": "Feste", "art": "aufwand"}).json()["id"]
    b = c.post("/api/buchungen", json={"datum": "2026-11-12", "verwendungszweck": "Verein fiktiv", "splits": [
        {"konto_id": giro, "betrag": -500}, {"konto_id": kat, "betrag": 500}]}).json()["id"]
    nid = spiegel(cfg)["<n3@x.invalid>"]["id"]
    r = c.post(f"/api/mail/nachrichten/{nid}/buchung", json={"buchung_id": b})
    assert r.status_code == 201, r.text
    assert spiegel(cfg)["<n3@x.invalid>"]["inhalt"] == 1
    assert p.verlangt[-1] == ["<n3@x.invalid>"]


def test_neue_vorauswahl_laedt_beim_naechsten_abruf_nach(umgebung, tmp_path):
    c, cfg, p = umgebung
    c.post("/api/mail/abruf")
    ordner = tmp_path / "anbieter"
    ordner.mkdir()
    (ordner / "verein.toml").write_text('''name = "verein"
titel = "Verein"
[vorauswahl]
betreff = '(?i)einladung'
[kennung]
muster = 'Nr\\. (\\d+)'
[[art]]
name = "beitrag"
rolle = "ausgabe"
grund = "bestellung"
betreff = '(?i)einladung'
gesamt = { betrag_nach = 'Beitrag' }
''', encoding="utf-8")
    object.__setattr__(cfg, "anbieter_verzeichnis", ordner)
    p.verlangt.clear()
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["nachrichten_nachgeladen"] == 1 and p.verlangt == [["<n3@x.invalid>"]]
    assert spiegel(cfg)["<n3@x.invalid>"]["text"] == "Bitte kommen"


def test_ohne_einstellung_wie_bisher(tmp_path):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2026, 11, 20),
                       planer_starten=False)
    c = TestClient(create_app(cfg))
    c.post("/api/mail/postfaecher", json={"adresse": PF})
    p = Attrappe(MAILS)
    c.app.state.sync.mail._mock_plugin = p
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["nachrichten_neu"] == 4 and "nachrichten_ohne_inhalt" not in erg
    assert p.voll_abgerufen == 1 and p.verlangt == []
    assert all(r["inhalt"] == 1 for r in spiegel(cfg).values())


# ---------------------------------------------------------------- Pflicht-Vorauswahl der Beschreibungen

GRUND = '''name = "kaufhaus"
titel = "Kaufhaus"
{kopf}
[kennung]
muster = 'K(\\d{{6}})'
[[art]]
name = "bestellung"
rolle = "ausgabe"
grund = "bestellung"
betreff = '(?i)auftrag'
gesamt = {{ betrag_nach = 'Summe' }}
'''


def test_vorauswahl_ist_pflicht():
    with pytest.raises(anbieter.BeschreibungsFehler, match="vorauswahl fehlt"):
        anbieter.aus_toml(GRUND.format(kopf=""))
    with pytest.raises(anbieter.BeschreibungsFehler, match="absender und/oder betreff"):
        anbieter.aus_toml(GRUND.format(kopf="[vorauswahl]"))
    with pytest.raises(anbieter.BeschreibungsFehler, match="nicht an beiden Stellen"):
        anbieter.aus_toml(GRUND.format(kopf="absender = 'x'\n[vorauswahl]\nabsender = 'y'"))
    with pytest.raises(anbieter.BeschreibungsFehler, match="Unbekannte Angabe text"):
        anbieter.aus_toml(GRUND.format(kopf="[vorauswahl]\ntext = 'x'"))


def test_vorauswahl_absender_und_betreff():
    a = anbieter.aus_toml(GRUND.format(kopf="[vorauswahl]\nabsender = 'kaufhaus\\.example'\nbetreff = '(?i)auftrag'"))
    assert a.gehoert("shop@kaufhaus.example", "Ihr Auftrag K123456")
    assert not a.gehoert("shop@kaufhaus.example", "Newsletter")
    assert not a.gehoert("shop@anders.example", "Ihr Auftrag")
    nur_betreff = anbieter.aus_toml(GRUND.format(kopf="[vorauswahl]\nbetreff = '(?i)auftrag'"))
    assert nur_betreff.gehoert("wer@irgendwo.example", "Auftrag K123456")
    assert anbieter.erkennen("wer@irgendwo.example", "Auftrag K123456", "Auftrag K123456\nSumme 5,00 €", (nur_betreff,)).gesamt == 500
    kurz = anbieter.aus_toml(GRUND.format(kopf="absender = 'kaufhaus\\.example'"))   # bisherige Kurzform
    assert kurz.gehoert("a@kaufhaus.example") and kurz.betreff is None
    assert all(x.absender is not None for x in anbieter.eingebaute())


# ---------------------------------------------------------------- IMAP gegen eine Loopback-Attrappe

import email.utils  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402

APP_PW = "abcdefghijklmnop"
GESTERN = dt.datetime.now(UTC).replace(microsecond=0) - dt.timedelta(days=1)


def _roh(absender, betreff, mid, text):
    return (f"From: {absender}\r\nTo: {PF}\r\nSubject: {betreff}\r\nMessage-ID: {mid}\r\nDate: "
            f"{email.utils.format_datetime(GESTERN)}\r\n\r\n{text}\r\n").encode()


IMAP_MAILS = {1: _roh("service@paypal.example.invalid", "Zahlung an Laden (fiktiv)", "<p1@example.invalid>",
                      "Transaktionscode: 1AB23456CD7890123\nBetrag 5,00 EUR"),
              2: _roh("news@laden.example.invalid", "Angebot (fiktiv)", "<n1@example.invalid>", "Werbung"),
              3: _roh("verein@example.invalid", "Protokoll (fiktiv)", "<n2@example.invalid>", "Lange Mail")}


class ImapAttrappe(threading.Thread):
    """Minimaler IMAP-Server: LOGIN, EXAMINE, UID SEARCH/FETCH mit BODY.PEEK[] und HEADER.FIELDS."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.abrufe: list[tuple[str, str]] = []   # (UID-Menge, Art)
        self.uidvalidity = 7

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
        intern = GESTERN.strftime("%d-%b-%Y %H:%M:%S +0000").encode()
        for zeile in f:
            z = zeile.decode().rstrip("\r\n")
            tag, _, rest = z.partition(" ")
            t = tag.encode()
            befehl = rest.split(" ")[0].upper()
            if befehl == "CAPABILITY":
                f.write(b"* CAPABILITY IMAP4rev1\r\n" + t + b" OK fertig\r\n")
            elif befehl == "LOGIN":
                f.write(t + (b" OK angemeldet\r\n" if APP_PW in rest else b" NO nein\r\n"))
            elif befehl == "EXAMINE":
                f.write(f"* 3 EXISTS\r\n* OK [UIDVALIDITY {self.uidvalidity}] ok\r\n".encode() + t + b" OK [READ-ONLY] ok\r\n")
            elif befehl == "UID" and " SEARCH " in rest.upper():
                if "HEADER" in rest.upper():
                    mid = re.search(r'"(<[^>]+>)"', rest)[1]
                    treffer = [u for u, r in IMAP_MAILS.items() if mid.encode() in r]
                else:
                    treffer = list(IMAP_MAILS)
                f.write(b"* SEARCH " + " ".join(map(str, treffer)).encode() + b"\r\n" + t + b" OK ok\r\n")
            elif befehl == "UID" and " FETCH " in rest.upper():
                menge = rest.split(" ")[2]
                kopf = "HEADER.FIELDS" in rest.upper()
                self.abrufe.append((menge, "kopf" if kopf else "voll"))
                for u in (int(x) for x in menge.split(",")):
                    if u not in IMAP_MAILS:
                        continue
                    r = IMAP_MAILS[u]
                    if kopf:
                        r = b"".join(zl + b"\r\n" for zl in r.split(b"\r\n\r\n")[0].split(b"\r\n")
                                     if zl.split(b":")[0].upper() in (b"FROM", b"SUBJECT", b"MESSAGE-ID")) + b"\r\n"
                    art = b"BODY[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT)]" if kopf else b"BODY[]"
                    f.write(f"* {u} FETCH (UID {u} INTERNALDATE \"".encode() + intern + b'" ' + art + b" {"
                            + str(len(r)).encode() + b"}\r\n" + r + b")\r\n")
                f.write(t + b" OK ok\r\n")
            elif befehl == "LOGOUT":
                f.write(b"* BYE\r\n" + t + b" OK tschuess\r\n")
                f.flush()
                break
            else:
                f.write(t + b" BAD unbekannt\r\n")
            f.flush()
        c.close()


@pytest.fixture
def imap_umgebung(tmp_path):
    imap = ImapAttrappe()
    imap.start()
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=False, planer_starten=False,
                       imap_host="127.0.0.1", imap_port=imap.port, imap_tls=False, mail_nur_koepfe=True)
    c = TestClient(create_app(cfg))
    pid = c.post("/api/mail/postfaecher", json={"adresse": PF}).json()["id"]
    assert c.put(f"/api/mail/postfaecher/{pid}/app-passwort", json={"passwort": APP_PW}).status_code == 200
    yield c, cfg, imap
    imap.sock.close()


def test_imap_erst_koepfe_dann_inhalt_bei_bedarf(imap_umgebung):
    c, cfg, imap = imap_umgebung
    erg = c.post("/api/mail/abruf").json()["postfaecher"][0]
    assert erg["status"] == "erfolgreich" and erg["nachrichten_neu"] == 3 and erg["nachrichten_ohne_inhalt"] == 2, erg
    assert imap.abrufe == [("1,2,3", "kopf"), ("1", "voll")]   # nur PayPal ganz
    s = spiegel(cfg)
    assert s["<p1@example.invalid>"]["inhalt"] == 1 and "Transaktionscode" in s["<p1@example.invalid>"]["text"]
    assert s["<n1@example.invalid>"]["betreff"] == "Angebot (fiktiv)"
    assert s["<n1@example.invalid>"]["absender"] == "news@laden.example.invalid"
    assert s["<n1@example.invalid>"]["ort"] == "7:2" and s["<n1@example.invalid>"]["text"] == ""
    imap.abrufe.clear()
    r = c.post(f"/api/mail/nachrichten/{s['<n1@example.invalid>']['id']}/inhalt")
    assert r.status_code == 200 and r.json()["text"].strip() == "Werbung", r.text
    assert imap.abrufe == [("2", "voll")]
    # UIDVALIDITY geändert: Suche über die Message-ID
    imap.uidvalidity = 8
    imap.abrufe.clear()
    r = c.post(f"/api/mail/nachrichten/{s['<n2@example.invalid>']['id']}/inhalt")
    assert r.status_code == 200 and r.json()["text"].strip() == "Lange Mail", r.text
    assert imap.abrufe == [("3", "voll")]
