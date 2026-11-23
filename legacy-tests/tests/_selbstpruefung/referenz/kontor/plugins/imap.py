"""IMAP-Plugin mit XOAUTH2 (mail.md 3) – Wegwerf-Referenz, KEIN Anwendungscode."""

from __future__ import annotations

import base64
import datetime as dt
import email
import email.header
import email.policy
import email.utils
import html
import imaplib
import re
import socket
import ssl
import time
from dataclasses import dataclass

from .. import mutant
from ..fehler import (MailAnmeldungAbgelehnt, MailFehler, MailOrdnerUnbekannt, MailVerbindungsFehler,
                      PluginNichtVerfuegbar, PostfachUnbekannt)
from .mail import MailNachricht, MailPlugin

UTC = dt.timezone.utc


@dataclass(frozen=True)
class ImapPostfach:
    adresse: str
    ordner: str = "INBOX"


def utf7(name: str) -> str:
    aus, puffer = [], []

    def leeren():
        if puffer:
            b = "".join(puffer).encode("utf-16-be")
            aus.append("&" + base64.b64encode(b).decode().rstrip("=").replace("/", ",") + "-")
            puffer.clear()
    for c in name:
        if 0x20 <= ord(c) <= 0x7E:
            leeren()
            aus.append("&-" if c == "&" else c)
        else:
            puffer.append(c)
    leeren()
    return "".join(aus)


def html_regel(h: str) -> str:
    t = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", h)
    t = re.sub(r"(?s)<[^>]*>", " ", t)
    t = html.unescape(t)
    return " ".join(t.split())


def _teil(teil) -> str:
    roh = teil.get_payload(decode=True) or b""
    cs = teil.get_content_charset() or "us-ascii"
    try:
        t = roh.decode(cs, errors="replace")
    except LookupError:
        t = roh.decode("utf-8", errors="replace")
    return t.replace("\r\n", "\n")


def abbilden(roh: bytes, postfach: str, empfangen: dt.datetime, uidvalidity: int, uid: int) -> MailNachricht:
    m = email.message_from_bytes(roh, policy=email.policy.compat32)
    mid = (m.get("Message-ID") or "").strip()
    von = str(email.header.make_header(email.header.decode_header(m.get("From", ""))))
    roh_b = m.get("Subject")
    betreff = ""
    if roh_b is not None:
        betreff = str(email.header.make_header(email.header.decode_header(re.sub(r"\r?\n[ \t]", " ", roh_b))))
    text = h = None
    for t in m.walk():
        if t.is_multipart():
            continue
        if (t.get("Content-Disposition") or "").split(";")[0].strip().lower() == "attachment" \
                and not mutant("imap_anhang_als_text"):
            continue
        if t.get_content_type() == "text/plain" and text is None:
            text = _teil(t)
        elif t.get_content_type() == "text/html" and h is None:
            h = html_regel(_teil(t))
    return MailNachricht(mid or f"imap:{uidvalidity}:{uid}", postfach, empfangen.astimezone(UTC),
                         email.utils.parseaddr(von)[1], betreff,
                         text if text is not None else (h if h is not None else ""))


class ImapMailPlugin(MailPlugin):
    name = "imap"
    ist_mock = False

    def __init__(self, config, *, postfaecher=(), zugang=None) -> None:
        self._c = config
        self._p = list(postfaecher)
        self._zugang = zugang

    def __repr__(self) -> str:
        return "<ImapMailPlugin>"

    def postfaecher(self) -> list[str]:
        return [p.adresse for p in self._p]

    def _verbinden(self):
        c = self._c
        try:
            if c.imap_tls:
                k = ssl.create_default_context(cafile=str(c.tls_ca_datei) if c.tls_ca_datei else None)
                m = imaplib.IMAP4_SSL(c.imap_host, c.imap_port, ssl_context=k, timeout=c.imap_timeout_sekunden)
            else:
                m = imaplib.IMAP4(c.imap_host, c.imap_port, timeout=c.imap_timeout_sekunden)
        except (OSError, imaplib.IMAP4.error, ssl.SSLError) as e:
            raise MailVerbindungsFehler("IMAP-Server nicht erreichbar") from None
        return m

    def nachrichten(self, postfach, seit):
        if seit.tzinfo is None:
            raise ValueError("seit ohne Zeitzone")
        p = next((x for x in self._p if x.adresse.casefold() == postfach.casefold()), None)
        if p is None:
            raise PostfachUnbekannt("Postfach unbekannt")
        if self._zugang is None:
            raise PluginNichtVerfuegbar("Kein Zugang konfiguriert")
        token = self._zugang(p.adresse, False)
        m = self._verbinden()
        try:
            return self._abruf(m, p, seit, token)
        except (socket.timeout, TimeoutError, OSError, imaplib.IMAP4.abort, ssl.SSLError):
            raise MailVerbindungsFehler("IMAP-Verbindung abgebrochen") from None
        finally:
            try:
                m.shutdown()
            except Exception:  # noqa: BLE001
                pass

    def _anmelden(self, m, adresse, token) -> bool:
        gesendet = []

        def mech(herausforderung):
            if gesendet:
                return b""
            gesendet.append(1)
            return f"user={adresse}\x01auth=Bearer {token}\x01\x01".encode()
        try:
            m.authenticate("XOAUTH2", mech)
            return True
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            return False

    def _abruf(self, m, p: ImapPostfach, seit, token):
        if "AUTH=XOAUTH2" not in m.capabilities:
            raise MailFehler("Server bietet kein XOAUTH2")
        if not self._anmelden(m, p.adresse, token):
            if mutant("imap_ohne_erneuern"):
                raise MailAnmeldungAbgelehnt("Anmeldung abgelehnt")
            token = self._zugang(p.adresse, True)
            if not self._anmelden(m, p.adresse, token):
                raise MailAnmeldungAbgelehnt("Anmeldung abgelehnt")
        typ, _ = m.select('"' + utf7(p.ordner) + '"', readonly=not mutant("imap_select_statt_examine"))
        if typ != "OK":
            raise MailOrdnerUnbekannt("Ordner unbekannt")
        uidvalidity = int(m.response("UIDVALIDITY")[1][0])
        typ, treffer = m.uid("SEARCH", None, "SINCE", seit.astimezone(UTC).strftime("%d-%b-%Y"))
        uids = treffer[0].split() if treffer and treffer[0] else []
        aus: dict[str, tuple[int, MailNachricht]] = {}
        if uids:
            element = "BODY[]" if mutant("imap_ohne_peek") else "BODY.PEEK[]"
            typ, teile = m.uid("FETCH", b",".join(uids).decode(), f"(UID INTERNALDATE {element})")
            for t in teile:
                if not isinstance(t, tuple):
                    continue
                kopf = t[0].decode()
                uid = int(re.search(r"UID (\d+)", kopf)[1])
                intern = imaplib.Internaldate2tuple(t[0])
                zeit = dt.datetime.fromtimestamp(time.mktime(intern), tz=UTC)
                n = abbilden(t[1], p.adresse, zeit, uidvalidity, uid)
                if n.nachricht_id not in aus or aus[n.nachricht_id][0] > uid:
                    aus[n.nachricht_id] = (uid, n)
        m.logout()
        return sorted((n for _, n in aus.values() if n.empfangen >= seit), key=lambda n: (n.empfangen, n.nachricht_id))
