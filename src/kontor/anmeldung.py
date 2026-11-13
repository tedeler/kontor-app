"""Meilenstein 7: Haushaltskonto, Passwort-Hash, Sitzungen, Bremse, Einrichtung (sicherheit.md 2–5,
python-api.md 14.2).

Anmeldedaten sind Betriebszustand (E-135): nie im Änderungsprotokoll, nie in der Sicherung. Maßgeblich ist
immer die Systemuhr (``time.time()``), nie die Mock-Uhr. Das Sitzungstoken wird nur als SHA-256 gespeichert;
das CSRF-Token wird aus dem Sitzungstoken abgeleitet (HMAC) und nirgends gespeichert.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import os
import pathlib
import re
import secrets
import sqlite3
import sys
import time
import unicodedata

from . import db
from .config import KontorConfig

log = logging.getLogger("kontor.anmeldung")

N, R, P, LAENGE = 32768, 8, 1, 32
MAXMEM = 64 * 1024 * 1024
_ZAHL = re.compile(r"^[1-9][0-9]*$")
_B64 = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")
_CODE = re.compile(r"^[0-9a-f]{32}$")


# ================================================================ Passwort (2)
def _nfc(passwort: str) -> str:
    return unicodedata.normalize("NFC", passwort)


def passwort_gueltig(passwort: str) -> bool:
    return 12 <= len(_nfc(passwort)) <= 1024


def _pruefe_regeln(passwort: object) -> str:
    if not isinstance(passwort, str):
        raise TypeError("Das Passwort muss eine Zeichenkette sein.")
    if not passwort_gueltig(passwort):
        raise ValueError("Das Passwort muss 12 bis 1024 Zeichen lang sein.")
    return _nfc(passwort)


def passwort_hash(passwort: str) -> str:
    nfc = _pruefe_regeln(passwort)
    salz = secrets.token_bytes(16)
    schluessel = hashlib.scrypt(nfc.encode("utf-8"), salt=salz, n=N, r=R, p=P, maxmem=MAXMEM, dklen=LAENGE)
    return (f"scrypt${N}${R}${P}${base64.b64encode(salz).decode('ascii')}$"
            f"{base64.b64encode(schluessel).decode('ascii')}")


def _b64(text: str) -> bytes | None:
    if not text or len(text) % 4 or not _B64.match(text):
        return None
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def passwort_pruefen(passwort: str, hash_text: str) -> bool:
    if not isinstance(passwort, str) or not isinstance(hash_text, str):
        raise TypeError("passwort_pruefen erwartet zwei Zeichenketten.")
    teile = hash_text.split("$")
    if len(teile) != 6 or teile[0] != "scrypt" or not all(_ZAHL.match(t) for t in teile[1:4]):
        return False
    n, r, p = (int(t) for t in teile[1:4])
    if not (2 <= n <= 2 ** 20 and n & (n - 1) == 0 and 1 <= r <= 64 and 1 <= p <= 64):
        return False
    salz, soll = _b64(teile[4]), _b64(teile[5])
    if not salz or soll is None or len(soll) != LAENGE:
        return False
    try:
        ist = hashlib.scrypt(_nfc(passwort).encode("utf-8"), salt=salz, n=n, r=r, p=p, maxmem=MAXMEM,
                             dklen=LAENGE)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(ist, soll)


# ============================================================ Datenbankzugriff
def _verbinde(config_oder_pfad) -> sqlite3.Connection:
    pfad = config_oder_pfad.aktive_datenbank if isinstance(config_oder_pfad, KontorConfig) else config_oder_pfad
    return db.verbinde(pathlib.Path(pfad))


def _zeile(con) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM anmeldung_konto WHERE id = 1").fetchone()


def einrichtungsdatei(config: KontorConfig) -> pathlib.Path:
    d = pathlib.Path(config.aktive_datenbank)
    return d.with_name(d.name + ".einrichtung")


def passwort_setzen(config: KontorConfig, passwort: str) -> None:
    """python-api.md 14.2: setzt/ersetzt das Haushaltspasswort, beendet alle Sitzungen, hebt die Sperre auf."""
    _passwort_setzen(config, passwort)


def _passwort_setzen(config: KontorConfig, passwort: str) -> int:
    neu = passwort_hash(passwort)  # ValueError/TypeError vor jeder Wirkung
    if not _schema_aktuell(config):
        db.schema_anlegen(pathlib.Path(config.aktive_datenbank))
    con = _verbinde(config)
    try:
        with db.transaktion(con):
            _hash_speichern(con, neu)
            verloren = huelle_verwerfen(con)
    finally:
        con.close()
    einrichtungsdatei(config).unlink(missing_ok=True)
    return verloren


def huelle_verwerfen(con) -> int:
    """D-129: Ohne das alte Passwort lässt sich der Datenschlüssel nicht neu verpacken – die mit dem Login-Passwort
    geschützten Geheimnisse sind verloren und werden gelöscht. Liefert ihre Anzahl."""
    from .geheimnisse import geschuetzt
    if con.execute("SELECT 1 FROM geheimnis_huelle").fetchone() is None:
        return 0
    weg = [r[0] for r in con.execute("SELECT name FROM geheimnis") if geschuetzt(r[0])]
    con.execute("PRAGMA secure_delete = ON")
    con.executemany("DELETE FROM geheimnis WHERE name = ?", [(n,) for n in weg])
    con.execute("DELETE FROM geheimnis_huelle")
    return len(weg)


def _schema_aktuell(config: KontorConfig) -> bool:
    p = pathlib.Path(config.aktive_datenbank)
    if not p.exists():
        return False
    con = db.verbinde(p)
    try:
        r = con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()
        return r is not None and r["wert"] == str(db.SCHEMA_VERSION)
    except sqlite3.DatabaseError:
        return False
    finally:
        con.close()


def _hash_speichern(con, neu: str) -> None:
    con.execute("INSERT INTO anmeldung_konto (id, passwort_hash, fehlversuche, gesperrt_bis) VALUES (1, ?, 0, NULL)"
                " ON CONFLICT(id) DO UPDATE SET passwort_hash = excluded.passwort_hash, fehlversuche = 0,"
                " gesperrt_bis = NULL", (neu,))
    con.execute("DELETE FROM sitzung")


def ist_eingerichtet(config: KontorConfig) -> bool:
    p = pathlib.Path(config.aktive_datenbank)
    if not p.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error:
        return False
    try:
        r = con.execute("SELECT passwort_hash FROM anmeldung_konto WHERE id = 1").fetchone()
        return r is not None and bool(r[0])
    except sqlite3.Error:
        return False
    finally:
        con.close()


# ================================================================ Tokens
def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_token(token: str) -> str:
    """CSRF-Token der Sitzung: aus dem Sitzungstoken abgeleitet, 43 Zeichen, während der Sitzung fest."""
    roh = hmac.new(token.encode("utf-8"), b"kontor-csrf", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(roh).decode("ascii").rstrip("=")


class Anmeldedienst:
    """Anmeldung einer App (eine Datenbank). Gültigkeit wird bei jeder Anfrage in der Datenbank geprüft."""

    def __init__(self, config: KontorConfig) -> None:
        self.config = config
        self.pfad = pathlib.Path(config.aktive_datenbank)

    def __repr__(self) -> str:
        return "Anmeldedienst()"

    def _con(self):
        return db.verbinde(self.pfad)

    # ------------------------------------------------------------ Zustand
    def eingerichtet(self, con=None) -> bool:
        eigene = con is None
        con = con or self._con()
        try:
            r = _zeile(con)
            return r is not None and bool(r["passwort_hash"])
        finally:
            if eigene:
                con.close()

    def gesperrt_bis(self, con, jetzt: float) -> float | None:
        r = _zeile(con)
        if r is None or r["gesperrt_bis"] is None or r["gesperrt_bis"] <= jetzt:
            return None
        return r["gesperrt_bis"]

    def einrichtung_vorbereiten(self) -> None:
        """sicherheit.md 5 Weg 2: Einrichtungscode-Datei anlegen bzw. weiterverwenden (nur Pfad im Log)."""
        if self.eingerichtet():
            return
        datei = einrichtungsdatei(self.config)
        try:
            if _CODE.match(datei.read_text(encoding="ascii").rstrip("\n")) and datei.read_text(
                    encoding="ascii").endswith("\n"):
                os.chmod(datei, 0o600)
                log.warning("Kontor ist noch nicht eingerichtet; Einrichtungscode in %s", datei)
                return
        except (OSError, UnicodeDecodeError):
            pass
        tmp = datei.with_name(datei.name + f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, (secrets.token_hex(16) + "\n").encode("ascii"))
        finally:
            os.close(fd)
        os.chmod(tmp, 0o600)
        os.replace(tmp, datei)
        log.warning("Kontor ist noch nicht eingerichtet; Einrichtungscode in %s", datei)

    def einrichtungscode_stimmt(self, code: str) -> bool:
        try:
            soll = einrichtungsdatei(self.config).read_text(encoding="ascii").rstrip("\n")
        except (OSError, UnicodeDecodeError):
            soll = ""
        return bool(soll) and hmac.compare_digest(code.encode("utf-8"), soll.encode("utf-8"))

    # ---------------------------------------------------------- Sitzungen
    def sitzung_pruefen(self, token: str | None, jetzt: float | None = None) -> tuple[float, float] | None:
        """Gültige Sitzung → (erstellt, aktivitaet) nach Zählung dieser Anfrage als Aktivität; sonst None."""
        if not token or len(token) > 256:
            return None
        jetzt = time.time() if jetzt is None else jetzt
        h = token_hash(token)
        con = self._con()
        try:
            r = con.execute("SELECT erstellt, aktivitaet FROM sitzung WHERE token_hash = ?", (h,)).fetchone()
            if r is None:
                return None
            if (jetzt - r["aktivitaet"] > self.config.sitzung_leerlauf_sekunden
                    or jetzt - r["erstellt"] > self.config.sitzung_hoechstdauer_sekunden):
                try:
                    con.execute("DELETE FROM sitzung WHERE token_hash = ?", (h,))
                except sqlite3.OperationalError:
                    pass
                return None
            try:
                con.execute("PRAGMA busy_timeout = 2000")
                con.execute("UPDATE sitzung SET aktivitaet = MAX(aktivitaet, ?) WHERE token_hash = ?", (jetzt, h))
            except sqlite3.OperationalError:  # Datenbank gerade gesperrt: Aktivität beim nächsten Mal
                pass
            return r["erstellt"], max(r["aktivitaet"], jetzt)
        finally:
            con.close()

    def ablauf(self, erstellt: float, aktivitaet: float) -> float:
        return min(aktivitaet + self.config.sitzung_leerlauf_sekunden,
                   erstellt + self.config.sitzung_hoechstdauer_sekunden)

    def sitzung_anlegen(self, con, jetzt: float) -> str:
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sitzung (token_hash, erstellt, aktivitaet) VALUES (?, ?, ?)",
                    (token_hash(token), jetzt, jetzt))
        # abgelaufene Sitzungen aufräumen
        con.execute("DELETE FROM sitzung WHERE aktivitaet < ? OR erstellt < ?",
                    (jetzt - self.config.sitzung_leerlauf_sekunden, jetzt - self.config.sitzung_hoechstdauer_sekunden))
        return token

    def abmelden(self, token: str) -> None:
        con = self._con()
        try:
            con.execute("DELETE FROM sitzung WHERE token_hash = ?", (token_hash(token),))
        finally:
            con.close()

    # ------------------------------------------------------------- Bremse
    def fehlversuch(self, con, jetzt: float, client: str) -> None:
        """sicherheit.md 4.5: Fehlversuch zählen, ggf. Sperre beginnen (in der Transaktion des Aufrufers)."""
        con.execute("INSERT INTO anmeldung_konto (id, fehlversuche) VALUES (1, 0) ON CONFLICT(id) DO NOTHING")
        n = con.execute("SELECT fehlversuche FROM anmeldung_konto WHERE id = 1").fetchone()[0] + 1
        grenze = self.config.anmeldung_fehlversuche
        log.warning("Fehlgeschlagener Anmeldeversuch von %s (%d in Folge)", client, n)
        if n >= grenze:
            dauer = min(self.config.anmeldung_sperre_sekunden * 2 ** min(n - grenze, 40), 86400)
            con.execute("UPDATE anmeldung_konto SET fehlversuche = ?, gesperrt_bis = ? WHERE id = 1",
                        (n, jetzt + dauer))
            log.warning("Anmeldung für %d s gesperrt (nach %d Fehlversuchen, zuletzt von %s)", dauer, n, client)
        else:
            con.execute("UPDATE anmeldung_konto SET fehlversuche = ? WHERE id = 1", (n,))

    @staticmethod
    def erfolg(con) -> None:
        con.execute("UPDATE anmeldung_konto SET fehlversuche = 0, gesperrt_bis = NULL WHERE id = 1")

    def passwort_hash_lesen(self, con) -> str | None:
        r = _zeile(con)
        return r["passwort_hash"] if r is not None else None

    def neues_passwort(self, con, neu_hash: str, behalten: str) -> None:
        """Passwort ändern (4.8): neuer Hash, alle anderen Sitzungen beendet, die eigene bleibt."""
        con.execute("UPDATE anmeldung_konto SET passwort_hash = ?, fehlversuche = 0, gesperrt_bis = NULL"
                    " WHERE id = 1", (neu_hash,))
        con.execute("DELETE FROM sitzung WHERE token_hash <> ?", (token_hash(behalten),))

    def einrichten(self, con, neu_hash: str) -> None:
        _hash_speichern(con, neu_hash)


# ============================================================ Kommandozeile
def main(argv: list[str] | None = None) -> int:
    from .fehler import KonfigurationsFehler

    args = sys.argv[1:] if argv is None else argv
    if args != ["passwort-setzen"]:
        print("Aufruf: python -m kontor.anmeldung passwort-setzen  (Passwort über stdin)", file=sys.stderr)
        return 2
    try:
        config = KontorConfig.from_env()
    except KonfigurationsFehler as e:
        print(f"Konfigurationsfehler: {e}", file=sys.stderr)
        return 2
    if sys.stdin.isatty():
        import getpass
        passwort = getpass.getpass("Neues Haushaltspasswort: ")
    else:
        passwort = sys.stdin.readline().rstrip("\r\n")
    try:
        verloren = _passwort_setzen(config, passwort)
    except ValueError:
        print("Das Passwort ist ungültig (12 bis 1024 Zeichen).", file=sys.stderr)
        return 1
    print(f"Passwort für {config.aktive_datenbank} gesetzt; alle Sitzungen beendet.")
    if verloren:
        print(f"Hinweis: {verloren} mit dem bisherigen Passwort geschützte Geheimnisse (z. B. Bank-PIN, "
              "Mail-Zugänge) wurden gelöscht und müssen neu eingegeben werden; der Schutz ist ausgeschaltet.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

__all__ = ["passwort_hash", "passwort_pruefen", "passwort_setzen", "ist_eingerichtet"]
