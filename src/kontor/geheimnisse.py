"""Verschlüsselter Geheimnisspeicher (geheimnisse.md, Meilenstein 6).

AES-256-GCM (``cryptography``), je Schreiben eine neue Nonce von 12 Bytes, zusätzliche authentisierte Daten =
Name des Geheimnisses. In der Datenbank stehen nur Nonce und Chiffretext. Der Schlüssel kommt aus
``$CREDENTIALS_DIRECTORY/kontor-geheimnisschluessel`` (systemd-creds) oder aus einer Schlüsseldatei neben der
Datenbank, die erst beim ersten Schreiben angelegt wird (Rechte 0600).

Kein Wert verlässt dieses Modul anders als über ``lesen`` an die App selbst (Token an den ntfy-, OAuth- bzw.
IMAP-Server). Geheimnisse sind kein Buchbestand: nicht protokolliert, nie in einer Sicherung.
"""

from __future__ import annotations

import base64
import binascii
import os
import pathlib
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .config import KontorConfig
from .validierung import ApiFehler

REST_NAMEN = ("ntfy_token", "oauth_client_secret")
SYSTEMD_NAME = "kontor-geheimnisschluessel"
MAIL_PRAEFIX = "mail_token:"


@dataclass(frozen=True)
class _Quelle:
    art: str                  # "systemd-creds" | "datei"
    pfad: pathlib.Path

    def __repr__(self) -> str:
        return f"_Quelle({self.art!r})"


def _schluessel_aus(inhalt: bytes) -> bytes | None:
    """Format nach geheimnisse.md 2: Base64 (Standardalphabet, mit Auffüllung) von genau 32 Bytes + Leerraum."""
    text = inhalt.rstrip(b" \t\r\n\v\f")
    if len(text) != 44:
        return None
    try:
        roh = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    return roh if len(roh) == 32 else None


class Geheimnisspeicher:
    def __init__(self, config: KontorConfig, jetzt_text: Callable[[], str]) -> None:
        self._config = config
        self._jetzt_text = jetzt_text

    def __repr__(self) -> str:
        return "Geheimnisspeicher()"

    # ------------------------------------------------------------ Schlüssel
    def _quelle(self) -> _Quelle:
        c = self._config
        if c.credentials_verzeichnis is not None:
            p = pathlib.Path(c.credentials_verzeichnis) / SYSTEMD_NAME
            if p.is_file():
                return _Quelle("systemd-creds", p)
        datei = c.geheimnis_schluessel_datei or c.aktive_datenbank.with_suffix(".schluessel")
        return _Quelle("datei", pathlib.Path(datei))

    def _schluessel(self, anlegen: bool = False) -> bytes | None:
        q = self._quelle()
        try:
            inhalt = q.pfad.read_bytes()
        except FileNotFoundError:
            if not anlegen or q.art != "datei":
                return None
            return self._anlegen(q.pfad)
        except OSError:
            return None
        return _schluessel_aus(inhalt)

    @staticmethod
    def _anlegen(pfad: pathlib.Path) -> bytes | None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        roh = secrets.token_bytes(32)
        try:
            fd = os.open(str(pfad), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # gleichzeitig angelegt: den vorhandenen verwenden
            return _schluessel_aus(pfad.read_bytes())
        try:
            os.write(fd, base64.b64encode(roh) + b"\n")
        finally:
            os.close(fd)
        os.chmod(str(pfad), 0o600)
        return roh

    def schluessel_status(self) -> dict:
        q = self._quelle()
        try:
            inhalt = q.pfad.read_bytes()
            vorhanden = True
        except OSError:
            inhalt, vorhanden = b"", q.pfad.exists()
        return {"quelle": q.art, "vorhanden": vorhanden, "gueltig": vorhanden and _schluessel_aus(inhalt) is not None}

    # ------------------------------------------------------------ Lesen und Schreiben
    def setzen(self, con: sqlite3.Connection, name: str, wert: str) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        q = self._quelle()
        if q.pfad.exists() or q.art != "datei":
            schluessel = self._schluessel(anlegen=False)
        else:
            schluessel = self._schluessel(anlegen=True)
        if schluessel is None:
            raise ApiFehler(409, "geheimnis_schluessel_ungueltig",
                            "Der Geheimnisschlüssel fehlt oder ist ungültig; es wurde nichts gespeichert.")
        nonce = secrets.token_bytes(12)
        chiffre = AESGCM(schluessel).encrypt(nonce, wert.encode("utf-8"), name.encode("utf-8"))
        con.execute("INSERT INTO geheimnis (name, nonce, chiffre, gesetzt_am) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(name) DO UPDATE SET nonce = excluded.nonce, chiffre = excluded.chiffre,"
                    " gesetzt_am = excluded.gesetzt_am", (name, nonce, chiffre, self._jetzt_text()))

    def lesen(self, con: sqlite3.Connection, name: str) -> str | None:
        """Klartext oder None (fehlt, Schlüssel fehlt/ungültig/anders): nicht lesbar = nicht vorhanden."""
        r = con.execute("SELECT nonce, chiffre FROM geheimnis WHERE name = ?", (name,)).fetchone()
        if r is None:
            return None
        return self._entschluesseln(name, r["nonce"], r["chiffre"])

    def _entschluesseln(self, name: str, nonce: bytes, chiffre: bytes) -> str | None:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        schluessel = self._schluessel()
        if schluessel is None:
            return None
        try:
            return AESGCM(schluessel).decrypt(bytes(nonce), bytes(chiffre), name.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError):
            return None

    @staticmethod
    def loeschen(con: sqlite3.Connection, name: str) -> None:
        con.execute("PRAGMA secure_delete = ON")  # keine Reste des Chiffretexts in freien Seiten
        con.execute("DELETE FROM geheimnis WHERE name = ?", (name,))

    def uebersicht(self, con: sqlite3.Connection) -> dict:
        eintraege = []
        for r in con.execute("SELECT name, nonce, chiffre, gesetzt_am FROM geheimnis ORDER BY name").fetchall():
            eintraege.append({"name": r["name"], "gesetzt_am": r["gesetzt_am"],
                              "lesbar": self._entschluesseln(r["name"], r["nonce"], r["chiffre"]) is not None})
        return {"schluessel": self.schluessel_status(), "eintraege": eintraege}


def mail_name(adresse: str) -> str:
    return MAIL_PRAEFIX + adresse.casefold()


def verwaiste_entfernen(con: sqlite3.Connection) -> None:
    """Tokens, Spiegel und Betriebszustand von Postfächern, deren Adresse es nicht mehr gibt (mail.md 2.2, 6.5)."""
    vorhanden = {r[0] for r in con.execute("SELECT adresse_cf FROM postfach")}
    namen = [r[0] for r in con.execute("SELECT name FROM geheimnis WHERE substr(name, 1, ?) = ?",
                                       (len(MAIL_PRAEFIX), MAIL_PRAEFIX))
             if r[0][len(MAIL_PRAEFIX):] not in vorhanden]
    if namen:
        con.execute("PRAGMA secure_delete = ON")
        con.executemany("DELETE FROM geheimnis WHERE name = ?", [(n,) for n in namen])
    for tabelle in ("postfach_zustand", "mail_nachricht"):
        weg = [r[0] for r in con.execute(f"SELECT DISTINCT adresse_cf FROM {tabelle}") if r[0] not in vorhanden]
        con.executemany(f"DELETE FROM {tabelle} WHERE adresse_cf = ?", [(a,) for a in weg])


__all__ = ["Geheimnisspeicher", "REST_NAMEN", "mail_name", "verwaiste_entfernen"]
