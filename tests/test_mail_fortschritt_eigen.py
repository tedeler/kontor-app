"""Entwicklungstests für das Feature „mail-fortschritt“ (D-252): Fortschritt des Abrufs, Abruf im Hintergrund,
alle Kopfzeilen neu abrufen. Synthetische Daten; ersetzen nicht die Abnahmetests."""

from __future__ import annotations

import datetime as dt
import threading
import time

import pytest
from fastapi.testclient import TestClient

from kontor.app import create_app
from kontor.config import KontorConfig

from .test_kopfabruf_eigen import MAILS, PF, Attrappe, nachricht, spiegel


class Langsam(Attrappe):
    """Hält im Kopfabruf an, bis der Test weiterlässt; meldet vorher einen Zwischenstand."""

    def __init__(self, liste):
        super().__init__(liste)
        self.weiter = threading.Event()

    def koepfe(self, postfach, seit, fortschritt=None):
        if fortschritt:
            fortschritt(1, len(self.liste))
        assert self.weiter.wait(10)
        return super().koepfe(postfach, seit, fortschritt)


def app(tmp_path, **kw):
    cfg = KontorConfig(datenbank=tmp_path / "k.sqlite3", mock_modus=True, mock_heute=dt.date(2026, 11, 20),
                       planer_starten=False, **kw)
    c = TestClient(create_app(cfg))
    assert c.post("/api/mail/postfaecher", json={"adresse": PF}).status_code == 201
    return c, cfg


def warten(c):
    for _ in range(200):
        st = c.get("/api/mail/abruf/stand").json()
        if not st["laeuft"]:
            return st
        time.sleep(0.05)
    raise AssertionError("Abruf endet nicht")


def test_hintergrund_mit_fortschritt(tmp_path):
    c, cfg = app(tmp_path, mail_nur_koepfe=True)
    p = Langsam(MAILS)
    c.app.state.sync.mail._mock_plugin = p
    assert c.get("/api/mail/abruf/stand").json() == {"laeuft": False, "nur_koepfe": True}
    r = c.post("/api/mail/abruf", params={"hintergrund": "ja"})
    assert r.status_code == 200 and r.json()["laeuft"] is True, r.text
    for _ in range(100):
        st = c.get("/api/mail/abruf/stand").json()
        if st["postfaecher"] and st["postfaecher"][0]["schritt"] == "koepfe":
            break
        time.sleep(0.02)
    assert st["laeuft"] and st["postfaecher"][0] | {"postfach_id": 0} == {
        "postfach_id": 0, "adresse": PF, "schritt": "koepfe", "erledigt": 1, "gesamt": 4}
    assert c.post("/api/mail/abruf").json()["fehler"]["code"] == "mail_abruf_laeuft"
    p.weiter.set()
    st = warten(c)
    assert st["fehler"] is None and st["postfaecher"][0]["schritt"] == "fertig"
    assert st["ergebnis"]["postfaecher"][0]["nachrichten_neu"] == 4
    assert len(spiegel(cfg)) == 4
    assert c.post("/api/mail/abruf").status_code == 200   # Sperre wieder frei


def test_synchroner_abruf_fuehrt_den_stand_mit(tmp_path):
    c, _ = app(tmp_path)
    erg = c.post("/api/mail/abruf").json()
    st = c.get("/api/mail/abruf/stand").json()
    assert st["laeuft"] is False and st["ergebnis"] == erg and st["nur_koepfe"] is False


def test_alle_koepfe(tmp_path):
    c, cfg = app(tmp_path, mail_nur_koepfe=True)
    alt = nachricht("<alt@x.invalid>", "verein@example.invalid", "Protokoll 2019", "alt", tag=1)
    alt = type(alt)(alt.nachricht_id, alt.postfach, dt.datetime(2019, 3, 1, tzinfo=dt.timezone.utc), alt.absender,
                    alt.betreff, alt.text)
    p = Attrappe([alt, *MAILS])
    c.app.state.sync.mail._mock_plugin = p
    c.post("/api/mail/abruf")
    assert "<alt@x.invalid>" not in spiegel(cfg)          # außerhalb der 30 Tage des ersten Abrufs
    erg = c.post("/api/mail/abruf", params={"alle_koepfe": "ja"}).json()["postfaecher"][0]
    assert p.seit.year == 1970 and erg["nachrichten_neu"] == 1 and erg["nachrichten_vorhanden"] == 4
    s = spiegel(cfg)
    assert s["<alt@x.invalid>"]["inhalt"] == 0 and s["<alt@x.invalid>"]["betreff"] == "Protokoll 2019"
    assert c.get("/api/mail/abruf/stand").json()["alle_koepfe"] is True


def test_alle_koepfe_nur_mit_kopfabruf_und_parameter_geprueft(tmp_path):
    c, _ = app(tmp_path)
    r = c.post("/api/mail/abruf", params={"alle_koepfe": "ja"})
    assert r.status_code == 409 and r.json()["fehler"]["code"] == "mail_nur_koepfe_aus"
    assert c.post("/api/mail/abruf", params={"hintergrund": "vielleicht"}).status_code == 422
    assert c.post("/api/mail/abruf").status_code == 200   # die Sperre wurde nie belegt
