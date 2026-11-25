"""Passkeys (WebAuthn) für Anmeldung und Bildschirmsperre (Feature ``passkeys``, D-284, sicherheit.md 13).

Der Browser fragt den Authentikator des Geräts (Fingerabdruck, Gesicht oder Gerätesperre); der Server sieht davon nur
eine Signatur über seine Aufgabe. Gespeichert wird je Passkey die Kennung und der öffentliche Schlüssel
(Betriebszustand wie die Sitzungen: nicht im Protokoll, nicht in der Sicherung). Geprüft wird ohne zusätzliche
Bibliothek mit ``cryptography``:

- die Aufgabe (einmal verwendbar, wenige Minuten gültig, an Art und ggf. Sitzung gebunden),
- der Ursprung der Seite und daraus die Kennung der Gegenstelle (``rpIdHash``),
- Anwesenheit **und** Nutzerprüfung (``UP`` und ``UV``),
- die Signatur über ``authenticatorData || SHA-256(clientDataJSON)``.

Beim Anlegen liefert die Oberfläche den öffentlichen Schlüssel aus ``getPublicKey()``; eine Beglaubigung des
Authentikators (Attestation) wird nicht verlangt und nicht ausgewertet – anlegen darf nur eine angemeldete Sitzung.
Aufgaben, Kennungen und Schlüssel erscheinen in keinem Log und keiner Fehlermeldung.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import threading
import urllib.parse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

from .validierung import ApiFehler

AUFGABE_SEKUNDEN = 300
AUFGABEN_HOECHSTENS = 1000
HOECHSTENS = 20                      # Passkeys je Haushalt
ALGORITHMEN = (-7, -257, -8)         # ES256, RS256, EdDSA
_UP, _UV, _AT = 0x01, 0x04, 0x40
_NUTZER = "passkey_nutzer"


def b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode("ascii")


def b64_lesen(text: object) -> bytes | None:
    if not isinstance(text, str) or not text or len(text) > 16384:
        return None
    try:
        return base64.b64decode(text.replace("-", "+").replace("_", "/") + "=" * (-len(text) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None


class Ungueltig(Exception):
    """Die Antwort des Authentikators besteht die Prüfung nicht (nach außen ohne Einzelheiten)."""


class Aufgaben:
    """Offene Aufgaben (Challenges) im Arbeitsspeicher: einmal verwendbar, kurz gültig, an Art und Bezug gebunden."""

    def __init__(self) -> None:
        self._offen: dict[str, tuple[str, str, float]] = {}
        self._schloss = threading.Lock()

    def __repr__(self) -> str:
        return "Aufgaben()"

    def neu(self, art: str, bezug: str, jetzt: float) -> str:
        aufgabe = b64(secrets.token_bytes(32))
        with self._schloss:
            for k in [k for k, (_, _, bis) in self._offen.items() if bis < jetzt]:
                del self._offen[k]
            while len(self._offen) >= AUFGABEN_HOECHSTENS:
                del self._offen[next(iter(self._offen))]
            self._offen[aufgabe] = (art, bezug, jetzt + AUFGABE_SEKUNDEN)
        return aufgabe

    def einloesen(self, aufgabe: object, art: str, bezug: str, jetzt: float) -> bool:
        if not isinstance(aufgabe, str):
            return False
        with self._schloss:
            eintrag = self._offen.pop(aufgabe, None)
        return eintrag is not None and eintrag[0] == art and hmac.compare_digest(eintrag[1], bezug) and eintrag[2] >= jetzt


def rp_id(ursprung: str) -> str:
    return (urllib.parse.urlsplit(ursprung).hostname or "").lower()


def _nutzer(con) -> str:
    """Kennung des Haushalts beim Authentikator: zufällig je Datenbank (Haupt- und Testinstanz überschreiben sich
    auf dem Gerät nicht gegenseitig)."""
    r = con.execute("SELECT wert FROM meta WHERE schluessel = ?", (_NUTZER,)).fetchone()
    if r is not None:
        return r["wert"]
    wert = b64(secrets.token_bytes(16))
    con.execute("INSERT OR IGNORE INTO meta (schluessel, wert) VALUES (?, ?)", (_NUTZER, wert))
    return con.execute("SELECT wert FROM meta WHERE schluessel = ?", (_NUTZER,)).fetchone()["wert"]


def vorhanden(con) -> bool:
    return con.execute("SELECT 1 FROM passkey LIMIT 1").fetchone() is not None


def liste(con) -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "angelegt": r["angelegt"], "benutzt": r["benutzt"]}
            for r in con.execute("SELECT id, name, angelegt, benutzt FROM passkey ORDER BY angelegt, id")]


def loeschen(con, passkey_id: int) -> None:
    if con.execute("DELETE FROM passkey WHERE id = ?", (passkey_id,)).rowcount == 0:
        raise ApiFehler(404, "nicht_gefunden", "Diesen Passkey gibt es nicht.")


# ------------------------------------------------------------------ Optionen für den Browser
def optionen_anlegen(con, aufgaben: Aufgaben, ursprung: str, bezug: str, jetzt: float) -> dict:
    return {"challenge": aufgaben.neu("anlegen", bezug, jetzt), "rp": {"id": rp_id(ursprung), "name": "Kontor"},
            "user": {"id": _nutzer(con), "name": "Haushalt", "displayName": "Kontor-Haushalt"},
            "pubKeyCredParams": [{"type": "public-key", "alg": a} for a in ALGORITHMEN],
            "authenticatorSelection": {"userVerification": "required", "residentKey": "preferred"},
            "excludeCredentials": [{"type": "public-key", "id": r["kennung"]}
                                   for r in con.execute("SELECT kennung FROM passkey ORDER BY id")],
            "attestation": "none", "timeout": AUFGABE_SEKUNDEN * 1000}


def optionen_pruefen(con, aufgaben: Aufgaben, art: str, ursprung: str, bezug: str, jetzt: float) -> dict:
    return {"challenge": aufgaben.neu(art, bezug, jetzt), "rpId": rp_id(ursprung), "userVerification": "required",
            "allowCredentials": [{"type": "public-key", "id": r["kennung"]}
                                 for r in con.execute("SELECT kennung FROM passkey ORDER BY id")],
            "timeout": AUFGABE_SEKUNDEN * 1000}


# ------------------------------------------------------------------ Prüfung
def _client_daten(roh: bytes | None, typ: str, aufgaben: Aufgaben, art: str, bezug: str, urspruenge: set[str],
                  jetzt: float) -> str:
    """Prüft ``clientDataJSON`` und löst die Aufgabe ein; liefert die Kennung der Gegenstelle (Hostname)."""
    try:
        d = json.loads(roh.decode("utf-8")) if roh else None
    except (ValueError, UnicodeDecodeError):
        d = None
    if not isinstance(d, dict) or d.get("type") != typ or d.get("crossOrigin") is True:
        raise Ungueltig
    ursprung = d.get("origin")
    if not isinstance(ursprung, str) or ursprung not in urspruenge:
        raise Ungueltig
    if not aufgaben.einloesen(d.get("challenge"), art, bezug, jetzt):
        raise Ungueltig
    return rp_id(ursprung)


def _auth_daten(daten: bytes | None, rp: str) -> tuple[int, int, bytes]:
    if daten is None or len(daten) < 37 or not rp:
        raise Ungueltig
    if not hmac.compare_digest(daten[:32], hashlib.sha256(rp.encode("utf-8")).digest()):
        raise Ungueltig
    flags = daten[32]
    if not flags & _UP or not flags & _UV:        # anwesend und geprüft (Fingerabdruck, Gesicht oder Gerätesperre)
        raise Ungueltig
    return flags, int.from_bytes(daten[33:37], "big"), daten[37:]


def _schluessel(spki: bytes | None, alg: int):
    try:
        s = serialization.load_der_public_key(spki) if spki else None
    except (ValueError, TypeError):
        s = None
    passt = ((alg == -7 and isinstance(s, ec.EllipticCurvePublicKey) and isinstance(s.curve, ec.SECP256R1))
             or (alg == -257 and isinstance(s, rsa.RSAPublicKey) and s.key_size >= 2048)
             or (alg == -8 and isinstance(s, ed25519.Ed25519PublicKey)))
    if not passt:
        raise Ungueltig
    return s


def anlegen(con, d: dict, aufgaben: Aufgaben, bezug: str, urspruenge: set[str], jetzt: float) -> dict:
    """Neuen Passkey speichern (Transaktion beim Aufrufer)."""
    rp = _client_daten(b64_lesen(d["client_daten"]), "webauthn.create", aufgaben, "anlegen", bezug, urspruenge, jetzt)
    flags, zaehler, rest = _auth_daten(b64_lesen(d["auth_daten"]), rp)
    kennung = b64_lesen(d["kennung"])
    if not flags & _AT or kennung is None or len(rest) < 18:
        raise Ungueltig
    laenge = int.from_bytes(rest[16:18], "big")
    if not 1 <= laenge <= 1023 or not hmac.compare_digest(rest[18:18 + laenge], kennung):
        raise Ungueltig
    spki = b64_lesen(d["schluessel"])
    _schluessel(spki, d["alg"])
    if con.execute("SELECT 1 FROM passkey WHERE kennung = ?", (b64(kennung),)).fetchone():
        raise ApiFehler(409, "passkey_existiert", "Dieser Passkey ist schon eingerichtet.")
    if con.execute("SELECT COUNT(*) FROM passkey").fetchone()[0] >= HOECHSTENS:
        raise ApiFehler(409, "passkey_grenze", f"Es sind höchstens {HOECHSTENS} Passkeys möglich.")
    pid = con.execute("INSERT INTO passkey (kennung, schluessel, alg, zaehler, name, rp_id, angelegt)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?)", (b64(kennung), spki, d["alg"], zaehler, d["name"], rp, jetzt)).lastrowid
    return next(e for e in liste(con) if e["id"] == pid)


def pruefen(con, d: dict, aufgaben: Aufgaben, art: str, bezug: str, urspruenge: set[str], jetzt: float) -> int:
    """Antwort des Authentikators prüfen; liefert die Nummer des Passkeys und vermerkt die Benutzung."""
    rp = _client_daten(b64_lesen(d["client_daten"]), "webauthn.get", aufgaben, art, bezug, urspruenge, jetzt)
    auth = b64_lesen(d["auth_daten"])
    _, zaehler, _ = _auth_daten(auth, rp)
    kennung, signatur = b64_lesen(d["kennung"]), b64_lesen(d["signatur"])
    if kennung is None or signatur is None:
        raise Ungueltig
    r = con.execute("SELECT * FROM passkey WHERE kennung = ?", (b64(kennung),)).fetchone()
    if r is None or r["rp_id"] != rp:
        raise Ungueltig
    schluessel = _schluessel(bytes(r["schluessel"]), r["alg"])
    nachricht = auth + hashlib.sha256(b64_lesen(d["client_daten"])).digest()
    try:
        if isinstance(schluessel, ec.EllipticCurvePublicKey):
            schluessel.verify(signatur, nachricht, ec.ECDSA(hashes.SHA256()))
        elif isinstance(schluessel, rsa.RSAPublicKey):
            schluessel.verify(signatur, nachricht, padding.PKCS1v15(), hashes.SHA256())
        else:
            schluessel.verify(signatur, nachricht)
    except (InvalidSignature, ValueError):
        raise Ungueltig from None
    if (zaehler or r["zaehler"]) and zaehler <= r["zaehler"]:      # Zähler läuft rückwärts: kopierter Schlüssel
        raise Ungueltig
    con.execute("UPDATE passkey SET zaehler = ?, benutzt = ? WHERE id = ?", (zaehler, jetzt, r["id"]))
    return r["id"]
