"""Lokale IMAP4rev1-Attrappe mit XOAUTH2 nach dem Vorbild von Gmail (mail.md 8) – nur 127.0.0.1.

Liest die synthetischen Postfächer des Generators (``fixtures/m6/mail``). Nur lesende Befehle werden
ausgeführt; ``LOGIN``, ``SELECT`` und schreibende Befehle beantwortet sie mit ``NO`` und zeichnet sie als
Verstoß auf, ebenso ``BODY[…]`` ohne ``PEEK`` und ``RFC822`` (die trotzdem beantwortet werden).

Betriebsart App-Passwörter (M23, ``geheimnisschutz.md`` 6.5, E-230): Mit ``passwoerter`` (Adresse → Passwort)
beantwortet sie ``LOGIN`` für diese Adressen mit ``OK`` bei passendem Passwort, sonst mit ``NO`` (ohne Verstoß).
``LOGIN`` für jede andere Adresse bleibt ein Verstoß. ``login_deaktiviert`` meldet ``LOGINDISABLED`` in den
Fähigkeiten (dann ist jedes ``LOGIN`` ein Verstoß).
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import socket
import socketserver
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .m6_orakel import mbox_lesen, utf7_imap
from .pfade import FIXTURES
from .tls import TestZertifikat

MAIL = FIXTURES / "m6" / "mail"
FAEHIGKEITEN = "IMAP4rev1 AUTH=XOAUTH2 SASL-IR ID UIDPLUS"
SCHREIBEND = {"STORE", "COPY", "MOVE", "EXPUNGE", "APPEND", "CREATE", "DELETE", "RENAME", "SUBSCRIBE",
              "UNSUBSCRIBE"}
ZONE = dt.timezone(dt.timedelta(hours=1))
MONATE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@dataclass
class Nachricht:
    uid: int
    intern: dt.datetime
    roh: bytes
    flags: tuple[str, ...] = ()


@dataclass
class Ordner:
    name: str
    uidvalidity: int
    nachrichten: list[Nachricht]


@dataclass
class Sitzung:
    nummer: int
    adresse: str | None = None
    ordner: Ordner | None = None
    befehle: list[str] = field(default_factory=list)


def lade_postfaecher(verzeichnis: Path = MAIL) -> dict[str, dict[str, Ordner]]:
    index = json.loads((verzeichnis / "postfaecher.json").read_text(encoding="utf-8"))
    aus: dict[str, dict[str, Ordner]] = {}
    for adresse, ordner in index["postfaecher"].items():
        for name, info in ordner.items():
            liste = mbox_lesen((verzeichnis / info["datei"]).read_bytes())
            aus.setdefault(adresse.casefold(), {})[name] = Ordner(
                name, info["uidvalidity"],
                [Nachricht(uid, zeit, roh) for (zeit, roh), uid in zip(liste, info["uids"], strict=True)])
    return aus


def _datum(text: str) -> dt.date:
    t, m, j = text.strip('"').split("-")
    return dt.date(int(j), MONATE.index(m.capitalize()) + 1, int(t))


def _intern_text(d: dt.datetime) -> str:
    z = d.astimezone(ZONE)
    return f'"{z.day:02d}-{MONATE[z.month - 1]}-{z.year} {z:%H:%M:%S} +0100"'


def _menge(text: str, groesste: int) -> set[int]:
    aus: set[int] = set()
    for teil in text.split(","):
        if ":" in teil:
            a, b = teil.split(":")
            a_, b_ = (groesste if x == "*" else int(x) for x in (a, b))
            aus.update(range(min(a_, b_), max(a_, b_) + 1))
        else:
            aus.add(groesste if teil == "*" else int(teil))
    return aus


def _woerter(text: str) -> list[str]:
    """Zerlegt Argumente (Atome, "Zeichenketten", (Listen) und [Abschnitte] bleiben zusammen)."""
    aus, i = [], 0
    while i < len(text):
        c = text[i]
        if c == " ":
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < len(text) and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            aus.append(text[i:j + 1])
            i = j + 1
            continue
        if c == "(":
            tiefe, j = 0, i
            while j < len(text):
                tiefe += {"(": 1, ")": -1}.get(text[j], 0)
                if tiefe == 0:
                    break
                j += 1
            aus.append(text[i:j + 1])
            i = j + 1
            continue
        j = i
        tiefe = 0
        while j < len(text) and (text[j] != " " or tiefe):
            tiefe += {"[": 1, "]": -1}.get(text[j], 0)
            j += 1
        aus.append(text[i:j])
        i = j
    return aus


def _entquoten(s: str) -> str:
    if s.startswith('"') and s.endswith('"'):
        return re.sub(r"\\(.)", r"\1", s[1:-1])
    return s


class ImapAttrappe:
    def __init__(self, *, postfaecher: dict[str, dict[str, Ordner]] | None = None,
                 pruefe_token: Callable[[str, str], bool] | None = None, tokens: dict[str, str] | None = None,
                 tls: TestZertifikat | None = None, passwoerter: dict[str, str] | None = None) -> None:
        self.postfaecher = postfaecher if postfaecher is not None else lade_postfaecher()
        self.tokens = {k.casefold(): v for k, v in (tokens or {}).items()}
        self.pruefe_token = pruefe_token
        self.tls = tls
        #: M23: App-Passwörter je Adresse (casefold); None = Betriebsart nur XOAUTH2 (M6)
        self.passwoerter = None if passwoerter is None else {k.casefold(): v for k, v in passwoerter.items()}
        self.login_deaktiviert = False
        #: (Adresse, Erfolg) je LOGIN der Betriebsart App-Passwörter
        self.logins: list[tuple[str, bool]] = []
        self.verzoegerung = 0.0
        self.abbruch_nach_gruss = False
        self.ohne_xoauth2 = False
        self.schranke: threading.Barrier | None = None
        self.sitzungen: list[Sitzung] = []
        self.verstoesse: list[str] = []
        self.anmeldungen: list[tuple[str, bool]] = []
        self.interne_fehler: list[str] = []
        self._sperre = threading.Lock()
        self._server: socketserver.ThreadingTCPServer | None = None

    # ------------------------------------------------------------ Betrieb
    def parallel(self, anzahl: int, timeout: float = 8.0) -> None:
        """EXAMINE wartet, bis ``anzahl`` Sitzungen gleichzeitig dort sind (Nachweis paralleler Abrufe)."""
        self.schranke = threading.Barrier(anzahl, timeout=timeout)

    def starte(self) -> "ImapAttrappe":
        attrappe = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    attrappe._sitzung(self)
                except (ConnectionError, OSError, ssl.SSLError):
                    pass
                except Exception:  # noqa: BLE001
                    import traceback  # noqa: PLC0415
                    attrappe.interne_fehler.append(traceback.format_exc())

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

            def get_request(self):
                sock, adr = super().get_request()
                if attrappe.tls is not None:
                    sock = attrappe.tls.server_kontext().wrap_socket(sock, server_side=True)
                return sock, adr

        self._server = Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, name="imap-attrappe", daemon=True).start()
        return self

    def stoppe(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "ImapAttrappe":
        return self.starte()

    def __exit__(self, *a) -> None:
        self.stoppe()

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    @property
    def alle_befehle(self) -> list[str]:
        return [b for s in self.sitzungen for b in s.befehle]

    # ------------------------------------------------------------ Protokoll
    def _token_ok(self, adresse: str, token: str) -> bool:
        if self.pruefe_token is not None:
            return self.pruefe_token(adresse, token)
        return self.tokens.get(adresse.casefold()) == token

    def _sitzung(self, h) -> None:
        with self._sperre:
            s = Sitzung(len(self.sitzungen) + 1)
            self.sitzungen.append(s)

        def schreibe(zeile: str | bytes) -> None:
            if self.verzoegerung:
                time.sleep(self.verzoegerung)
            h.wfile.write(zeile if isinstance(zeile, bytes) else (zeile + "\r\n").encode("utf-8"))
            h.wfile.flush()

        faehig = FAEHIGKEITEN.replace(" AUTH=XOAUTH2", "") if self.ohne_xoauth2 else FAEHIGKEITEN
        if self.login_deaktiviert:
            faehig += " LOGINDISABLED"
        schreibe(f"* OK [CAPABILITY {faehig}] Kontor IMAP-Attrappe bereit")
        if self.abbruch_nach_gruss:
            return
        while True:
            roh = h.rfile.readline()
            if not roh:
                return
            zeile = roh.decode("utf-8", errors="replace").rstrip("\r\n")
            literal = re.search(r"\{(\d+)\+?\}$", zeile)
            if literal:   # Literal (z. B. APPEND) annehmen, damit die Sitzung lesbar bleibt
                schreibe("+ bereit")
                h.rfile.read(int(literal[1]))
                zeile = zeile[:literal.start()] + h.rfile.readline().decode("utf-8", errors="replace").rstrip("\r\n")
            teile = zeile.split(" ", 2)
            if len(teile) < 2:
                schreibe("* BAD Befehl unverständlich")
                continue
            tag, befehl = teile[0], teile[1].upper()
            rest = teile[2] if len(teile) > 2 else ""
            uid = False
            if befehl == "UID":
                uid = True
                befehl, _, rest = rest.partition(" ")
                befehl = befehl.upper()
            s.befehle.append(("UID " if uid else "") + befehl + (" " + rest.split(" ")[0].upper() if befehl in (
                "AUTHENTICATE",) else ""))
            if befehl == "LOGOUT":
                schreibe("* BYE Abmeldung")
                schreibe(f"{tag} OK LOGOUT completed")
                return
            if befehl == "CAPABILITY":
                schreibe(f"* CAPABILITY {faehig}")
                schreibe(f"{tag} OK CAPABILITY completed")
            elif befehl == "NOOP":
                schreibe(f"{tag} OK NOOP completed")
            elif befehl == "ID":
                schreibe('* ID ("name" "Kontor-Attrappe")')
                schreibe(f"{tag} OK ID completed")
            elif befehl == "LOGIN":
                self._login(s, tag, rest, schreibe)
            elif befehl == "AUTHENTICATE":
                self._authenticate(h, s, tag, rest, schreibe)
            elif s.adresse is None:
                schreibe(f"{tag} BAD nicht angemeldet")
            elif befehl == "SELECT":
                self.verstoesse.append("SELECT statt EXAMINE")
                schreibe(f"{tag} NO [CANNOT] Nur EXAMINE erlaubt (nur lesend)")
            elif befehl in SCHREIBEND:
                self.verstoesse.append(f"schreibender Befehl {befehl}")
                schreibe(f"{tag} NO [CANNOT] {befehl} ist nicht erlaubt (nur lesend)")
            elif befehl == "LIST":
                for name in self.postfaecher.get(s.adresse.casefold(), {}):
                    schreibe(f'* LIST (\\HasNoChildren) "/" "{utf7_imap(name)}"')
                schreibe(f"{tag} OK LIST completed")
            elif befehl == "EXAMINE":
                self._examine(s, tag, rest, schreibe)
            elif befehl == "STATUS":
                schreibe(f"{tag} OK STATUS completed")
            elif befehl in ("CLOSE", "UNSELECT"):
                s.ordner = None
                schreibe(f"{tag} OK {befehl} completed")
            elif s.ordner is None:
                schreibe(f"{tag} BAD kein Ordner geöffnet")
            elif befehl == "SEARCH":
                self._search(s, tag, rest, uid, schreibe)
            elif befehl == "FETCH":
                self._fetch(s, tag, rest, uid, schreibe)
            else:
                schreibe(f"{tag} BAD unbekannter Befehl")

    def _login(self, s: Sitzung, tag: str, rest: str, schreibe) -> None:
        woerter = [_entquoten(w) for w in _woerter(rest)]
        adresse = woerter[0] if woerter else ""
        if self.login_deaktiviert or self.passwoerter is None or adresse.casefold() not in self.passwoerter:
            self.verstoesse.append("LOGIN (Passwort)")
            schreibe(f"{tag} NO [ALERT] Passwörter sind nicht erlaubt (nur XOAUTH2)")
            return
        ok = len(woerter) == 2 and woerter[1] == self.passwoerter[adresse.casefold()]
        with self._sperre:
            self.logins.append((adresse, ok))
        if ok:
            s.adresse = adresse
            schreibe(f"{tag} OK [CAPABILITY {FAEHIGKEITEN}] {adresse} authenticated (Success)")
        else:
            schreibe(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials (Failure)")

    def _authenticate(self, h, s: Sitzung, tag: str, rest: str, schreibe) -> None:
        mech, _, anfang = rest.partition(" ")
        if mech.upper() != "XOAUTH2" or self.ohne_xoauth2:
            schreibe(f"{tag} NO [CANNOT] Mechanismus nicht unterstützt")
            return
        if not anfang:
            schreibe("+ ")
            anfang = h.rfile.readline().decode("ascii", errors="replace").strip()
        try:
            text = base64.b64decode(anfang).decode("utf-8")
            m = re.fullmatch(r"user=([^\x01]+)\x01auth=Bearer ([^\x01]+)\x01\x01", text)
        except (ValueError, UnicodeDecodeError):
            m = None
        ok = bool(m) and self._token_ok(m[1], m[2])
        with self._sperre:
            self.anmeldungen.append((m[1] if m else "", ok))
        if ok:
            s.adresse = m[1]
            schreibe(f"{tag} OK [CAPABILITY {FAEHIGKEITEN}] {m[1]} authenticated (Success)")
            return
        fehler = base64.b64encode(json.dumps({"status": "401", "schemes": "Bearer", "scope": "https://mail.google.com/"
                                              }).encode()).decode()
        schreibe("+ " + fehler)
        h.rfile.readline()
        schreibe(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials (Failure)")

    def _examine(self, s: Sitzung, tag: str, rest: str, schreibe) -> None:
        name_kodiert = _entquoten(rest.strip())
        ordner = next((o for n, o in self.postfaecher.get(s.adresse.casefold(), {}).items()
                       if utf7_imap(n) == name_kodiert), None)
        if self.schranke is not None:
            try:
                self.schranke.wait()
            except threading.BrokenBarrierError:
                self.verstoesse.append("nicht parallel: Schranke nicht erreicht")
                schreibe(f"{tag} NO [UNAVAILABLE] parallele Sitzungen erwartet")
                return
        if ordner is None:
            schreibe(f"{tag} NO [NONEXISTENT] Ordner unbekannt")
            return
        s.ordner = ordner
        groesste = max((n.uid for n in ordner.nachrichten), default=0)
        schreibe("* FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)")
        schreibe(f"* {len(ordner.nachrichten)} EXISTS")
        schreibe("* 0 RECENT")
        schreibe(f"* OK [UIDVALIDITY {ordner.uidvalidity}] UIDs gültig")
        schreibe(f"* OK [UIDNEXT {groesste + 1}] nächste UID")
        schreibe(f"{tag} OK [READ-ONLY] EXAMINE completed")

    def _passend(self, ordner: Ordner, kriterien: list[str]) -> list[tuple[int, Nachricht]]:
        liste = list(enumerate(ordner.nachrichten, start=1))
        groesste_uid = max((n.uid for n in ordner.nachrichten), default=0)
        i = 0
        while i < len(kriterien):
            k = kriterien[i].upper()
            if k == "ALL":
                i += 1
            elif k in ("SINCE", "BEFORE", "ON"):
                d = _datum(kriterien[i + 1])
                tag = lambda n: n.intern.astimezone(ZONE).date()  # noqa: E731
                if k == "SINCE":
                    liste = [(q, n) for q, n in liste if tag(n) >= d]
                elif k == "BEFORE":
                    liste = [(q, n) for q, n in liste if tag(n) < d]
                else:
                    liste = [(q, n) for q, n in liste if tag(n) == d]
                i += 2
            elif k == "UID":
                m = _menge(kriterien[i + 1], groesste_uid)
                liste = [(q, n) for q, n in liste if n.uid in m]
                i += 2
            elif k == "CHARSET":
                i += 2
            else:
                raise ValueError(f"Suchkriterium {k} nicht unterstützt")
        return liste

    def _search(self, s: Sitzung, tag: str, rest: str, uid: bool, schreibe) -> None:
        try:
            treffer = self._passend(s.ordner, _woerter(rest))
        except (ValueError, IndexError):
            schreibe(f"{tag} BAD Suchkriterium nicht unterstützt")
            return
        schreibe("* SEARCH" + "".join(f" {n.uid if uid else q}" for q, n in treffer))
        schreibe(f"{tag} OK SEARCH completed")

    def _fetch(self, s: Sitzung, tag: str, rest: str, uid: bool, schreibe) -> None:
        menge_text, _, elemente = rest.partition(" ")
        elemente = elemente.strip()
        if elemente.startswith("(") and elemente.endswith(")"):
            elemente = elemente[1:-1]
        namen = [e.upper() for e in _woerter(elemente)]
        nachrichten = list(enumerate(s.ordner.nachrichten, start=1))
        groesste = max((n.uid for _, n in nachrichten), default=0) if uid else len(nachrichten)
        if not nachrichten:
            schreibe(f"{tag} OK FETCH completed")
            return
        menge = _menge(menge_text, groesste)
        for q, n in nachrichten:
            if (n.uid if uid else q) not in menge:
                continue
            teile: list[bytes] = []
            if uid and "UID" not in namen:
                teile.append(f"UID {n.uid}".encode())
            for e in namen:
                if e == "UID":
                    teile.append(f"UID {n.uid}".encode())
                elif e == "INTERNALDATE":
                    teile.append(f"INTERNALDATE {_intern_text(n.intern)}".encode())
                elif e == "FLAGS":
                    teile.append(("FLAGS (" + " ".join(n.flags) + ")").encode())
                elif e == "RFC822.SIZE":
                    teile.append(f"RFC822.SIZE {len(n.roh)}".encode())
                elif e in ("BODY.PEEK[]", "BODY[]", "RFC822"):
                    if e != "BODY.PEEK[]":
                        self.verstoesse.append(f"{e} ohne PEEK")
                    name = b"RFC822" if e == "RFC822" else b"BODY[]"
                    teile.append(name + b" {" + str(len(n.roh)).encode() + b"}\r\n" + n.roh)
                elif e == "BODY.PEEK[HEADER]":
                    kopf = n.roh.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
                    teile.append(b"BODY[HEADER] {" + str(len(kopf)).encode() + b"}\r\n" + kopf)
                else:
                    schreibe(f"{tag} BAD FETCH-Element {e} nicht unterstützt")
                    return
            schreibe(f"* {q} FETCH (".encode() + b" ".join(teile) + b")\r\n")
        schreibe(f"{tag} OK FETCH completed")


def verbindung_moeglich(port: int) -> bool:  # pragma: no cover - Hilfe für Fehlersuche
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False
