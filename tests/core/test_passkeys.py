"""Core-Tests zum Feature passkeys (D-284, sicherheit.md 13): Anmeldung mit Passkey (WebAuthn) und Bildschirmsperre.

Der Authentikator des Handys ist hier nachgebildet: ein P-256-Schlüssel, der die Aufgabe des Servers so signiert,
wie es der Browser nach der Nutzerprüfung (Fingerabdruck) liefert. Kein Browser, kein Netz.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from kontor import anmeldung
from kontor.app import create_app
from kontor.config import KontorConfig

PASSWORT = "Synthetisch-Passkey-2026"
URSPRUNG = "https://kontor.example.invalid"


def b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode("ascii")


class Authentikator:
    """Nachbildung eines Plattform-Authentikators mit Nutzerprüfung."""

    def __init__(self, rp_id: str = "kontor.example.invalid") -> None:
        self.schluessel = ec.generate_private_key(ec.SECP256R1())
        self.kennung = os.urandom(32)
        self.rp_id = rp_id
        self.zaehler = 0

    def _auth_daten(self, mit_schluessel: bool, uv: bool = True) -> bytes:
        self.zaehler += 1
        flags = 0x01 | (0x04 if uv else 0) | (0x40 if mit_schluessel else 0)
        daten = hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + self.zaehler.to_bytes(4, "big")
        if mit_schluessel:
            daten += bytes(16) + len(self.kennung).to_bytes(2, "big") + self.kennung + b"\xa0"   # COSE-Schlüssel (hier leer)
        return daten

    @staticmethod
    def _client_daten(typ: str, aufgabe: str, ursprung: str) -> bytes:
        return json.dumps({"type": typ, "challenge": aufgabe, "origin": ursprung, "crossOrigin": False}).encode()

    def anlegen(self, optionen: dict, ursprung: str = URSPRUNG, name: str = "Handy") -> dict:
        spki = self.schluessel.public_key().public_bytes(serialization.Encoding.DER,
                                                         serialization.PublicFormat.SubjectPublicKeyInfo)
        return {"name": name, "kennung": b64(self.kennung), "alg": -7, "schluessel": b64(spki),
                "client_daten": b64(self._client_daten("webauthn.create", optionen["challenge"], ursprung)),
                "auth_daten": b64(self._auth_daten(True))}

    def pruefen(self, optionen: dict, ursprung: str = URSPRUNG, uv: bool = True) -> dict:
        client = self._client_daten("webauthn.get", optionen["challenge"], ursprung)
        auth = self._auth_daten(False, uv)
        signatur = self.schluessel.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {"kennung": b64(self.kennung), "client_daten": b64(client), "auth_daten": b64(auth),
                "signatur": b64(signatur)}


def _client(config) -> TestClient:
    return TestClient(create_app(config), base_url=URSPRUNG, headers={"Origin": URSPRUNG})


def _anmelden(c: TestClient) -> dict:
    r = c.post("/api/anmeldung", json={"passwort": PASSWORT})
    assert r.status_code == 200, r.text
    c.headers["X-Kontor-CSRF"] = r.json()["csrf_token"]
    return r.json()


@pytest.fixture
def haushalt(tmp_path):
    config = KontorConfig(datenbank=tmp_path / "k.sqlite3", anmeldung=True, sitzung_cookie_secure=False)
    anmeldung.passwort_setzen(config, PASSWORT)
    c = _client(config)
    _anmelden(c)
    return config, c


def _passkey_anlegen(c: TestClient, a: Authentikator | None = None, name: str = "Handy") -> Authentikator:
    a = a or Authentikator()
    opt = c.post("/api/passkeys/optionen").json()
    assert opt["rp"]["id"] == "kontor.example.invalid" and opt["authenticatorSelection"]["userVerification"] == "required"
    r = c.post("/api/passkeys", json=a.anlegen(opt, name=name))
    assert r.status_code == 201, r.text
    return a


def test_passkey_anlegen_auflisten_loeschen(haushalt):
    config, c = haushalt
    assert c.get("/api/passkeys").json() == []
    a = _passkey_anlegen(c)
    (eintrag,) = c.get("/api/passkeys").json()
    assert eintrag["name"] == "Handy" and eintrag["benutzt"] is None and set(eintrag) == {"id", "name", "angelegt", "benutzt"}
    assert c.get("/api/anmeldung").json()["passkeys"] is True
    # dieselbe Kennung ein zweites Mal: abgelehnt
    opt = c.post("/api/passkeys/optionen").json()
    assert a.kennung and c.post("/api/passkeys", json=a.anlegen(opt)).status_code == 409
    assert c.delete(f"/api/passkeys/{eintrag['id']}").status_code == 204
    assert c.get("/api/passkeys").json() == []
    # der öffentliche Schlüssel und die Kennung erscheinen in keiner Antwort
    assert "schluessel" not in json.dumps(c.get("/api/anmeldung").json())


def test_anmelden_mit_passkey(haushalt):
    config, c = haushalt
    a = _passkey_anlegen(c)
    neu = _client(config)                                   # anderes Gerät ohne Sitzung
    assert neu.get("/api/konten").status_code == 401
    status = neu.get("/api/anmeldung").json()
    assert status["angemeldet"] is False and status["passkeys"] is True
    opt = neu.post("/api/anmeldung/passkey/optionen").json()
    assert opt["userVerification"] == "required" and opt["rpId"] == "kontor.example.invalid"
    r = neu.post("/api/anmeldung/passkey", json=a.pruefen(opt))
    assert r.status_code == 200, r.text
    assert r.json()["angemeldet"] is True and "kontor_sitzung=" in r.headers["set-cookie"]
    assert neu.get("/api/konten").status_code == 200
    assert c.get("/api/passkeys").json()[0]["benutzt"] is not None


@pytest.mark.parametrize("fall", ["aufgabe_doppelt", "fremde_aufgabe", "fremder_ursprung", "ohne_nutzerpruefung",
                                  "falsche_signatur", "unbekannte_kennung", "falsche_rp"])
def test_anmeldung_mit_passkey_wird_abgelehnt(haushalt, fall):
    config, c = haushalt
    a = _passkey_anlegen(c)
    neu = _client(config)
    opt = neu.post("/api/anmeldung/passkey/optionen").json()
    d = a.pruefen(opt)
    if fall == "aufgabe_doppelt":
        assert neu.post("/api/anmeldung/passkey", json=d).status_code == 200
        neu = _client(config)                               # dieselbe Antwort noch einmal (mitgeschnitten)
    elif fall == "fremde_aufgabe":
        d = a.pruefen({"challenge": b64(os.urandom(32))})
    elif fall == "fremder_ursprung":
        d = a.pruefen(opt, ursprung="https://boese.example.invalid")
    elif fall == "ohne_nutzerpruefung":
        d = a.pruefen(opt, uv=False)
    elif fall == "falsche_signatur":
        fremd = Authentikator()
        fremd.kennung = a.kennung
        d = fremd.pruefen(opt)
    elif fall == "unbekannte_kennung":
        d = Authentikator().pruefen(opt)
    elif fall == "falsche_rp":
        fremd = Authentikator("anders.example.invalid")
        fremd.schluessel, fremd.kennung = a.schluessel, a.kennung
        d = fremd.pruefen(opt)
    r = neu.post("/api/anmeldung/passkey", json=d)
    assert r.status_code == 401 and r.json()["fehler"]["code"] == "passkey_ungueltig", r.text
    assert "set-cookie" not in r.headers
    assert neu.get("/api/konten").status_code == 401


def test_passkey_anlegen_braucht_sitzung_und_gueltige_aufgabe(haushalt):
    config, c = haushalt
    fremd = _client(config)
    assert fremd.post("/api/passkeys/optionen").status_code == 401
    a = Authentikator()
    opt = c.post("/api/passkeys/optionen").json()
    d = a.anlegen(opt)
    falsch = dict(d, client_daten=b64(a._client_daten("webauthn.create", b64(os.urandom(32)), URSPRUNG)))
    r = c.post("/api/passkeys", json=falsch)
    assert r.status_code == 400 and r.json()["fehler"]["code"] == "passkey_ungueltig"
    assert c.get("/api/passkeys").json() == []


def test_bildschirmsperre_sperrt_und_passkey_entsperrt(haushalt, monkeypatch):
    config, c = haushalt
    a = _passkey_anlegen(c)
    st = c.get("/api/anmeldung").json()
    assert st["bildschirmsperre"] == {"minuten": None, "gesperrt": False}
    r = c.put("/api/anmeldung/bildschirmsperre", json={"minuten": 5})
    assert r.status_code == 200 and r.json()["bildschirmsperre"] == {"minuten": 5, "gesperrt": False}
    assert c.get("/api/konten").status_code == 200

    # sechs Minuten ohne Anfrage (App im Hintergrund)
    import time as zeit
    echt = zeit.time
    monkeypatch.setattr(zeit, "time", lambda: echt() + 6 * 60)
    r = c.get("/api/konten")
    assert r.status_code == 423 and r.json()["fehler"]["code"] == "bildschirm_gesperrt"
    assert c.get("/api/anmeldung").json()["bildschirmsperre"]["gesperrt"] is True
    assert c.get("/api/buchungen?konto_id=1").status_code == 423           # bleibt gesperrt, auch bei weiteren Anfragen
    assert c.put("/api/anmeldung/bildschirmsperre", json={"minuten": None}).status_code == 423   # nicht abschaltbar

    opt = c.post("/api/anmeldung/entsperren/optionen").json()
    falsch = Authentikator()
    falsch.kennung = a.kennung
    assert c.post("/api/anmeldung/entsperren", json=falsch.pruefen(opt)).status_code == 401
    opt = c.post("/api/anmeldung/entsperren/optionen").json()
    r = c.post("/api/anmeldung/entsperren", json=a.pruefen(opt))
    assert r.status_code == 200 and r.json()["bildschirmsperre"] == {"minuten": 5, "gesperrt": False}
    assert c.get("/api/konten").status_code == 200


def test_bildschirmsperre_sofort_und_mit_passwort_entsperren(haushalt):
    config, c = haushalt
    assert c.put("/api/anmeldung/bildschirmsperre", json={"minuten": 0}).status_code == 200
    assert c.get("/api/konten").status_code == 200
    assert c.post("/api/anmeldung/sperren").status_code == 204             # die Oberfläche meldet: im Hintergrund
    assert c.get("/api/konten").status_code == 423
    r = c.post("/api/anmeldung/entsperren", json={"passwort": "Falsches-Passwort-2026"})
    assert r.status_code == 401 and r.json()["fehler"]["code"] == "anmeldung_fehlgeschlagen"
    assert c.get("/api/konten").status_code == 423
    assert c.post("/api/anmeldung/entsperren", json={"passwort": PASSWORT}).status_code == 200
    assert c.get("/api/konten").status_code == 200
    # Abmelden geht auch gesperrt; eine andere Sitzung ist nicht betroffen
    zweite = _client(config)
    _anmelden(zweite)
    c.post("/api/anmeldung/sperren")
    assert zweite.get("/api/konten").status_code == 200
    assert c.post("/api/anmeldung/abmelden").status_code == 204


def test_ohne_sperre_bleibt_alles_wie_bisher(haushalt, monkeypatch):
    config, c = haushalt
    import time as zeit
    echt = zeit.time
    monkeypatch.setattr(zeit, "time", lambda: echt() + 30 * 60)
    assert c.get("/api/konten").status_code == 200
    assert c.post("/api/anmeldung/sperren").status_code == 409             # keine Sperre eingerichtet
