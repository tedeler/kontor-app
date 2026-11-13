"""IMAP-Mail-Plugin mit OAuth2/XOAUTH2, nur lesend (mail.md 3, Meilenstein 6).

Je Aufruf von ``nachrichten`` eine eigene Verbindung (Postfächer lassen sich parallel aus mehreren Threads
abrufen). Anmeldung über ``AUTHENTICATE XOAUTH2`` mit einem Access-Token aus ``zugang`` oder – für Postfächer mit
App-Passwort (D-130, z. B. Gmail ohne eigenes Google-Cloud-Projekt) – über ``LOGIN`` mit dem App-Passwort, das
``ImapPostfach.passwort`` erst unmittelbar vor der Anmeldung liefert. Ordner werden nur mit ``EXAMINE`` geöffnet, Inhalte nur mit ``BODY.PEEK[]``
gelesen – der Abruf ändert weder Inhalt noch Markierungen. Tokens erscheinen nie in Meldungen, ``details``,
``repr()`` oder Protokollen.
"""

from __future__ import annotations

import base64
import datetime as dt
import email
import email.errors
import email.header
import email.policy
import email.utils
import html
import imaplib
import re
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..config import KontorConfig
from ..fehler import (MailAnmeldungAbgelehnt, MailAnmeldungFehlt, MailFehler, MailOrdnerUnbekannt,
                      MailVerbindungsFehler, PluginNichtVerfuegbar, PostfachUnbekannt)
from ..netz import tls_kontext
from .mail import MailNachricht, MailPlugin

UTC = dt.timezone.utc
_MONATE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_INTERN = re.compile(rb'INTERNALDATE "\s?(\d{1,2})-([A-Za-z]{3})-(\d{4}) (\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})"')
_UID = re.compile(rb"\bUID (\d+)")
_TEIL = 200  # UIDs je FETCH


@dataclass(frozen=True)
class ImapPostfach:
    adresse: str
    ordner: str = "INBOX"
    # D-130: liefert das App-Passwort (oder None); ohne Wert gilt OAuth2/XOAUTH2. Nie in repr oder Vergleichen.
    passwort: Callable[[], str | None] | None = field(default=None, repr=False, compare=False)


def utf7_imap(name: str) -> str:
    """Modifiziertes UTF-7 für Ordnernamen (RFC 3501 5.1.3)."""
    aus: list[str] = []
    puffer: list[str] = []

    def leeren() -> None:
        if puffer:
            b = "".join(puffer).encode("utf-16-be")
            aus.append("&" + base64.b64encode(b).decode("ascii").rstrip("=").replace("/", ",") + "-")
            puffer.clear()

    for c in name:
        if 0x20 <= ord(c) <= 0x7E:
            leeren()
            aus.append("&-" if c == "&" else c)
        else:
            puffer.append(c)
    leeren()
    return "".join(aus)


def _quoten(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def html_text(h: str) -> str:
    """HTML-Regel aus mail.md 3.3."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", h)
    t = re.sub(r"(?s)<[^>]*>", " ", t)
    t = html.unescape(t)
    return " ".join(t.split())


def _teil_text(teil) -> str:
    roh = teil.get_payload(decode=True) or b""
    cs = teil.get_content_charset() or "us-ascii"
    try:
        t = roh.decode(cs, errors="replace")
    except LookupError:
        t = roh.decode("utf-8", errors="replace")
    return t.replace("\r\n", "\n")


def _kopf(roh: str | None) -> str:
    if roh is None:
        return ""
    entfaltet = re.sub(r"\r?\n[ \t]", " ", str(roh))
    try:
        return str(email.header.make_header(email.header.decode_header(entfaltet)))
    except (LookupError, UnicodeError, ValueError, email.errors.HeaderParseError):
        return entfaltet


def abbilden(roh: bytes, postfach: str, empfangen: dt.datetime, uidvalidity: str, uid: int) -> MailNachricht:
    """Abbildung einer RFC-5322-Nachricht auf ``MailNachricht`` (mail.md 3.3)."""
    m = email.message_from_bytes(roh, policy=email.policy.compat32)
    mid = str(m.get("Message-ID") or "").strip()
    absender = email.utils.parseaddr(_kopf(m.get("From", "")))[1] if m.get("From") is not None else ""
    betreff = _kopf(m.get("Subject")) if m.get("Subject") is not None else ""
    text = None
    html_inhalt = None
    for teil in m.walk():
        if teil.is_multipart():
            continue
        if str(teil.get("Content-Disposition") or "").split(";")[0].strip().lower() == "attachment":
            continue
        art = teil.get_content_type()
        if art == "text/plain" and text is None:
            text = _teil_text(teil)
        elif art == "text/html" and html_inhalt is None:
            html_inhalt = html_text(_teil_text(teil))
    return MailNachricht(mid or f"imap:{uidvalidity}:{uid}", postfach, empfangen, absender, betreff,
                         text if text is not None else (html_inhalt if html_inhalt is not None else ""))


def _internaldate(kopf: bytes) -> dt.datetime | None:
    m = _INTERN.search(kopf)
    if m is None:
        return None
    monat = _MONATE.index(m[2].decode().capitalize()) + 1
    versatz = dt.timedelta(hours=int(m[8]), minutes=int(m[9]))
    zone = dt.timezone(versatz if m[7] == b"+" else -versatz)
    return dt.datetime(int(m[3]), monat, int(m[1]), int(m[4]), int(m[5]), int(m[6]), tzinfo=zone).astimezone(UTC)


class ImapMailPlugin(MailPlugin):
    name = "imap"
    ist_mock = False

    def __init__(self, config: KontorConfig | None = None, *, postfaecher: Sequence[ImapPostfach] = (),
                 zugang: Callable[[str, bool], str] | None = None) -> None:
        # Das Erzeugen baut keine Verbindung auf und ruft zugang nicht auf (mail.md 3).
        self._config = config
        self._postfaecher = tuple(postfaecher)
        self._zugang = zugang

    def __repr__(self) -> str:
        return f"ImapMailPlugin(postfaecher={len(self._postfaecher)})"

    __str__ = __repr__

    def postfaecher(self) -> list[str]:
        return [p.adresse for p in self._postfaecher]

    def nachrichten(self, postfach: str, seit: dt.datetime) -> list[MailNachricht]:
        if not isinstance(seit, dt.datetime) or seit.tzinfo is None or seit.utcoffset() is None:
            raise ValueError("seit muss ein zeitzonenbehafteter Zeitpunkt sein.")
        ziel = str(postfach).casefold()
        p = next((x for x in self._postfaecher if x.adresse.casefold() == ziel), None)
        if p is None:
            raise PostfachUnbekannt("Das Postfach ist unbekannt.")
        if p.passwort is not None and self._config is not None:
            return self._abrufen(p, seit, None)
        if self._zugang is None or self._config is None:
            raise PluginNichtVerfuegbar("Für das Postfach ist kein OAuth2-Zugang eingerichtet.")
        token = self._zugang(p.adresse, False)
        return self._abrufen(p, seit, token)

    # ------------------------------------------------------------ IMAP
    def _verbinden(self) -> imaplib.IMAP4:
        c = self._config
        try:
            if c.imap_tls:
                return imaplib.IMAP4_SSL(c.imap_host, c.imap_port, ssl_context=tls_kontext(c),
                                         timeout=c.imap_timeout_sekunden)
            return imaplib.IMAP4(c.imap_host, c.imap_port, timeout=c.imap_timeout_sekunden)
        except (OSError, imaplib.IMAP4.error, ssl.SSLError, EOFError):
            raise MailVerbindungsFehler("Die Verbindung zum Mailserver ist fehlgeschlagen.") from None

    @staticmethod
    def _anmelden(verbindung: imaplib.IMAP4, adresse: str, token: str) -> bool:
        schritte = {"n": 0}
        anfang = f"user={adresse}\x01auth=Bearer {token}\x01\x01".encode("utf-8")

        def antwort(_herausforderung: bytes) -> bytes:
            schritte["n"] += 1
            # Erste Fortsetzung: Anmeldedaten; eine zweite trägt die Fehlerbeschreibung → leere Zeile (RFC 7628)
            return anfang if schritte["n"] == 1 else b""

        try:
            verbindung.authenticate("XOAUTH2", antwort)
            return True
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            return False

    @staticmethod
    def _mit_passwort(v: imaplib.IMAP4, p: ImapPostfach) -> None:
        """D-130: LOGIN mit dem App-Passwort; der Wert lebt nur in dieser Funktion."""
        if "LOGINDISABLED" in {str(x).upper() for x in (v.capabilities or ())}:
            raise MailFehler("Der Mailserver erlaubt keine Anmeldung mit Passwort.")
        pw = p.passwort() if p.passwort is not None else None
        if not pw:
            raise MailAnmeldungFehlt("Für das Postfach ist kein lesbares App-Passwort gespeichert.")
        try:
            v.login(p.adresse, pw)
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            raise MailAnmeldungAbgelehnt("Der Mailserver hat das App-Passwort abgelehnt.") from None
        finally:
            del pw

    def pruefen(self, postfach: str) -> int:
        """D-130: Anmeldung und Ordner prüfen (für „Verbindung testen“); liefert die Zahl der Nachrichten im Ordner."""
        ziel = str(postfach).casefold()
        p = next((x for x in self._postfaecher if x.adresse.casefold() == ziel), None)
        if p is None or p.passwort is None or self._config is None:
            raise PostfachUnbekannt("Das Postfach ist unbekannt.")
        v = self._verbinden()
        try:
            try:
                self._mit_passwort(v, p)
                typ, daten = v.select(_quoten(utf7_imap(p.ordner)), readonly=True)  # EXAMINE
                if typ != "OK":
                    raise MailOrdnerUnbekannt("Der IMAP-Ordner bzw. das Gmail-Label ist im Postfach unbekannt.")
                try:
                    anzahl = int(daten[0]) if daten and daten[0] else 0
                except ValueError:
                    anzahl = 0
                try:
                    v.logout()
                except (OSError, imaplib.IMAP4.error, EOFError):
                    pass
                v = None
                return anzahl
            except (OSError, imaplib.IMAP4.abort, ssl.SSLError, EOFError):
                raise MailVerbindungsFehler("Die Verbindung zum Mailserver wurde unterbrochen.") from None
            except imaplib.IMAP4.error:
                raise MailVerbindungsFehler("Unerwartete Antwort des Mailservers.") from None
        finally:
            if v is not None:
                try:
                    v.shutdown()
                except Exception:  # noqa: BLE001
                    pass

    def _abrufen(self, p: ImapPostfach, seit: dt.datetime, token: str | None) -> list[MailNachricht]:
        v = self._verbinden()
        try:
            try:
                if token is None:
                    self._mit_passwort(v, p)
                else:
                    if "AUTH=XOAUTH2" not in {str(x).upper() for x in (v.capabilities or ())}:
                        raise MailFehler("Der Mailserver bietet keine Anmeldung über XOAUTH2 an.")
                    if not self._anmelden(v, p.adresse, token):
                        token = self._zugang(p.adresse, True)
                        if not self._anmelden(v, p.adresse, token):
                            raise MailAnmeldungAbgelehnt("Der Mailserver hat die Anmeldung mit OAuth2 abgelehnt.")
                del token
                typ, _ = v.select(_quoten(utf7_imap(p.ordner)), readonly=True)  # EXAMINE
                if typ != "OK":
                    raise MailOrdnerUnbekannt("Der IMAP-Ordner ist im Postfach unbekannt.")
                _, werte = v.response("UIDVALIDITY")
                uidvalidity = (werte[0].decode("ascii", "replace") if werte and werte[0] else "0").strip()
                s = seit.astimezone(UTC)
                kriterium = f"{s.day:02d}-{_MONATE[s.month - 1]}-{s.year}"
                typ, daten = v.uid("SEARCH", "SINCE", kriterium)
                if typ != "OK":
                    raise MailVerbindungsFehler("Der Mailserver hat die Suche nicht beantwortet.")
                uids = sorted({int(x) for x in b" ".join(d for d in daten if d).split()})
                gesammelt: dict[int, tuple[dt.datetime, bytes]] = {}
                for i in range(0, len(uids), _TEIL):
                    teil = ",".join(str(u) for u in uids[i:i + _TEIL])
                    typ, daten = v.uid("FETCH", teil, "(UID INTERNALDATE BODY.PEEK[])")
                    if typ != "OK":
                        raise MailVerbindungsFehler("Der Mailserver hat den Abruf nicht beantwortet.")
                    for eintrag in daten:
                        if not isinstance(eintrag, tuple) or len(eintrag) < 2:
                            continue
                        kopf, inhalt = eintrag[0], eintrag[1]
                        m = _UID.search(kopf)
                        zeit = _internaldate(kopf)
                        if m is None or zeit is None:
                            raise MailVerbindungsFehler("Unerwartete Antwort des Mailservers.")
                        gesammelt[int(m[1])] = (zeit, bytes(inhalt))
                try:
                    v.logout()
                except (OSError, imaplib.IMAP4.error, EOFError):
                    pass
                v = None
            except (OSError, imaplib.IMAP4.abort, ssl.SSLError, EOFError):
                raise MailVerbindungsFehler("Die Verbindung zum Mailserver wurde unterbrochen.") from None
            except imaplib.IMAP4.error:
                raise MailVerbindungsFehler("Unerwartete Antwort des Mailservers.") from None
        finally:
            if v is not None:
                try:
                    v.shutdown()
                except Exception:  # noqa: BLE001
                    pass
        nachrichten: dict[str, MailNachricht] = {}
        for uid in sorted(gesammelt):
            zeit, roh = gesammelt[uid]
            n = abbilden(roh, p.adresse, zeit, uidvalidity, uid)
            nachrichten.setdefault(n.nachricht_id, n)  # bei gleicher Kennung die kleinste UID (E-123)
        aus = [n for n in nachrichten.values() if n.empfangen >= seit]
        aus.sort(key=lambda n: (n.empfangen, n.nachricht_id))
        return aus


__all__ = ["ImapMailPlugin", "ImapPostfach", "utf7_imap", "abbilden"]
