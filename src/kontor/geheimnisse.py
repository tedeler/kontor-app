"""Verschlüsselter Geheimnisspeicher (geheimnisse.md, Meilenstein 6).

AES-256-GCM (``cryptography``), je Schreiben eine neue Nonce von 12 Bytes, zusätzliche authentisierte Daten =
Name des Geheimnisses. In der Datenbank stehen nur Nonce und Chiffretext. Der Schlüssel kommt aus
``$CREDENTIALS_DIRECTORY/kontor-geheimnisschluessel`` (systemd-creds) oder aus einer Schlüsseldatei neben der
Datenbank, die erst beim ersten Schreiben angelegt wird (Rechte 0600).

Kein Wert verlässt dieses Modul anders als über ``lesen`` an die App selbst (Token an den ntfy-, OAuth- bzw.
IMAP-Server). Geheimnisse sind kein Buchbestand: nicht protokolliert, nie in einer Sicherung.

**Schutz mit dem Login-Passwort (D-129, Feature ``geheimnisse``):** Auf Wunsch liegt zusätzlich eine innere
Schicht um jedes Geheimnis (außer ``ntfy_token``, damit „Bitte entsperren“ zugestellt werden kann): ein zufälliger
Datenschlüssel (AES-256-GCM), der seinerseits mit einem per scrypt aus dem Login-Passwort abgeleiteten Schlüssel
verpackt in ``geheimnis_huelle`` liegt. Der Datenschlüssel lebt nur im Arbeitsspeicher; er entsteht beim Login
bzw. über „Entsperren“ und verschwindet beim Neustart oder mit „Sperren“. Gesperrt sind geschützte Geheimnisse
nicht lesbar (``lesen`` → None) und nicht schreibbar (409 ``geheimnisse_gesperrt``). Das Passwort selbst wird nach
dem Ableiten verworfen.
"""

from __future__ import annotations

import base64
import binascii
import os
import pathlib
import hashlib
import secrets
import sqlite3
import threading
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from .config import KontorConfig
from .validierung import ApiFehler

REST_NAMEN = ("ntfy_token", "oauth_client_secret")
SYSTEMD_NAME = "kontor-geheimnisschluessel"
MAIL_PRAEFIX = "mail_token:"
UNGESCHUETZT = ("ntfy_token",)
INNEN = "M1:"                      # Kennung der inneren Schicht im (außen verschlüsselten) Wert
HUELLE_N, HUELLE_R, HUELLE_P = 2 ** 15, 8, 1   # scrypt für den Hüllenschlüssel (32 MiB)
_MAXMEM = 64 * 1024 * 1024


def _huellenschluessel(passwort: str, salz: bytes, n: int, r: int, p: int) -> bytes:
    nfc = unicodedata.normalize("NFC", passwort)
    return hashlib.scrypt(nfc.encode("utf-8"), salt=salz, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32)


def geschuetzt(name: str) -> bool:
    return name not in UNGESCHUETZT


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
        self._datenschluessel: bytes | None = None
        self._sperre = threading.Lock()

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
        if geschuetzt(name) and self.schutz_aktiv(con):
            wert = self._innen_verschluesseln(name, wert)
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
            wert = AESGCM(schluessel).decrypt(bytes(nonce), bytes(chiffre), name.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError):
            return None
        if wert.startswith(INNEN):
            return self._innen_entschluesseln(name, wert)
        return wert

    # ------------------------------------------------------------ Schutz mit dem Login-Passwort (D-129)
    def _innen_verschluesseln(self, name: str, wert: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ds = self._datenschluessel
        if ds is None:
            raise ApiFehler(409, "geheimnisse_gesperrt", "Die Geheimnisse sind gesperrt; bitte zuerst mit dem "
                            "Login-Passwort entsperren. Es wurde nichts gespeichert.")
        nonce = secrets.token_bytes(12)
        c = AESGCM(ds).encrypt(nonce, wert.encode("utf-8"), b"innen:" + name.encode("utf-8"))
        return INNEN + base64.b64encode(nonce + c).decode("ascii")

    def _innen_entschluesseln(self, name: str, wert: str) -> str | None:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        ds = self._datenschluessel
        if ds is None:
            return None
        try:
            roh = base64.b64decode(wert[len(INNEN):], validate=True)
            return AESGCM(ds).decrypt(roh[:12], roh[12:], b"innen:" + name.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError, binascii.Error):
            return None

    @staticmethod
    def _huelle(con: sqlite3.Connection):
        return con.execute("SELECT * FROM geheimnis_huelle WHERE id = 1").fetchone()

    def schutz_aktiv(self, con: sqlite3.Connection) -> bool:
        return self._huelle(con) is not None

    def entsperrt(self) -> bool:
        return self._datenschluessel is not None

    def gesperrt(self, con: sqlite3.Connection) -> bool:
        """Schutz eingeschaltet, aber der Datenschlüssel fehlt im Arbeitsspeicher."""
        return self._datenschluessel is None and self.schutz_aktiv(con)

    def _auspacken(self, h, passwort: str) -> bytes | None:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        kek = _huellenschluessel(passwort, bytes(h["salz"]), h["n"], h["r"], h["p"])
        try:
            return AESGCM(kek).decrypt(bytes(h["nonce"]), bytes(h["chiffre"]), b"kontor-huelle")
        except InvalidTag:
            return None

    @staticmethod
    def _verpacken(con: sqlite3.Connection, ds: bytes, passwort: str, zeit: str) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salz, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
        kek = _huellenschluessel(passwort, salz, HUELLE_N, HUELLE_R, HUELLE_P)
        chiffre = AESGCM(kek).encrypt(nonce, ds, b"kontor-huelle")
        con.execute("INSERT INTO geheimnis_huelle (id, salz, n, r, p, nonce, chiffre, gesetzt_am)"
                    " VALUES (1, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET salz = excluded.salz,"
                    " n = excluded.n, r = excluded.r, p = excluded.p, nonce = excluded.nonce,"
                    " chiffre = excluded.chiffre, gesetzt_am = excluded.gesetzt_am",
                    (salz, HUELLE_N, HUELLE_R, HUELLE_P, nonce, chiffre, zeit))

    def entsperren(self, con: sqlite3.Connection, passwort: str) -> bool:
        """True, wenn der Schutz aktiv ist und das Passwort den Datenschlüssel öffnet (oder schon offen ist)."""
        h = self._huelle(con)
        if h is None:
            return False
        ds = self._auspacken(h, passwort)
        if ds is None:
            return False
        with self._sperre:
            self._datenschluessel = ds
        return True

    def sperren(self) -> None:
        with self._sperre:
            self._datenschluessel = None

    def _alle(self, con: sqlite3.Connection) -> list[str]:
        return [r[0] for r in con.execute("SELECT name FROM geheimnis ORDER BY name")]

    def schutz_einschalten(self, con: sqlite3.Connection, passwort: str) -> int:
        """Erzeugt den Datenschlüssel, verpackt ihn und legt die innere Schicht um alle geschützten Geheimnisse.
        Aufrufer prüft vorher das Login-Passwort; läuft in der Transaktion des Aufrufers."""
        if self.schutz_aktiv(con):
            raise ApiFehler(409, "schutz_bereits_aktiv", "Der Schutz der Geheimnisse ist bereits eingeschaltet.")
        werte = {n: self.lesen(con, n) for n in self._alle(con) if geschuetzt(n)}
        ds = secrets.token_bytes(32)
        self._verpacken(con, ds, passwort, self._jetzt_text())
        with self._sperre:
            self._datenschluessel = ds
        for n, w in werte.items():
            if w is None:
                self.loeschen(con, n)  # nicht lesbar: unbrauchbar, wird ohnehin neu angelegt
            else:
                self.setzen(con, n, w)
        return len(werte)

    def schutz_ausschalten(self, con: sqlite3.Connection) -> None:
        """Innere Schicht entfernen (nur entsperrt); danach gilt wieder nur der Systemschlüssel."""
        if not self.schutz_aktiv(con):
            return
        if self._datenschluessel is None:
            raise ApiFehler(409, "geheimnisse_gesperrt", "Zum Ausschalten des Schutzes bitte zuerst entsperren.")
        werte = {n: self.lesen(con, n) for n in self._alle(con) if geschuetzt(n)}
        con.execute("DELETE FROM geheimnis_huelle")
        self.sperren()
        for n, w in werte.items():
            if w is None:
                self.loeschen(con, n)
            else:
                self.setzen(con, n, w)

    def neu_verpacken(self, con: sqlite3.Connection, neues_passwort: str) -> None:
        """Passwortwechsel: nur der Datenschlüssel wird neu verpackt (nur entsperrt; sonst nichts zu tun)."""
        if self.schutz_aktiv(con) and self._datenschluessel is not None:
            self._verpacken(con, self._datenschluessel, neues_passwort, self._jetzt_text())

    def huelle_verwerfen(self, con: sqlite3.Connection) -> int:
        """Passwort zurückgesetzt (ohne das alte): geschützte Geheimnisse sind verloren und werden gelöscht."""
        if not self.schutz_aktiv(con):
            return 0
        weg = [n for n in self._alle(con) if geschuetzt(n)]
        for n in weg:
            self.loeschen(con, n)
        con.execute("DELETE FROM geheimnis_huelle")
        self.sperren()
        return len(weg)

    def schutz_status(self, con: sqlite3.Connection) -> dict:
        aktiv = self.schutz_aktiv(con)
        namen = [n for n in self._alle(con) if geschuetzt(n)]
        return {"aktiv": aktiv, "entsperrt": aktiv and self.entsperrt(), "gesperrt": aktiv and not self.entsperrt(),
                "geschuetzt": len(namen) if aktiv else 0,
                "pin_gemerkt": "bank_pin" in namen and aktiv}

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


__all__ = ["Geheimnisspeicher", "REST_NAMEN", "UNGESCHUETZT", "geschuetzt", "mail_name", "verwaiste_entfernen"]
