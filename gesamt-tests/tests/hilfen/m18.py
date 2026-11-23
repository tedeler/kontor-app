"""Hilfen für Meilenstein-18-Tests (Dokumente an Buchungen) – nur über die Spezifikation (dokumente.md).

- Testdateien werden hier erzeugt (synthetisch, wenige Bytes): PDF, PNG, JPEG-Kopf, WebP-Kopf, E-Mails.
- ``typ`` und ``dateiname_soll`` sind eigene Fassungen der Regeln aus ``dokumente.md`` 1.2 und 1.3; die Tests
  vergleichen die Antworten der Anwendung damit (nie umgekehrt).
- ``bestand`` erweitert den Buchbestand aus M6 um das Objekt ``dokument`` und das Feld ``dokument_ids`` der
  Buchungen (``dokumente.md`` 3.1, E-207).
"""

from __future__ import annotations

import hashlib
import struct
import unicodedata
import zlib
from email.message import EmailMessage
from email.utils import format_datetime
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # nur für Typangaben
    import datetime as dt
    from pathlib import Path

from .api import Api, fehlercode
from .m3 import aenderungen_seit, letzte_aenderung_id
from .m6 import bestand as bestand_m6

OBJEKTE_M18 = ["konto", "empfaenger", "tag", "buchung", "regel", "verdacht", "abstimmung", "vorlage", "kredit",
               "postfach", "dokument", "erwartung"]  # erwartung ab M20 (erwartungen.md 12)
PDF, JPEG, PNG, WEBP, MAIL = "application/pdf", "image/jpeg", "image/png", "image/webp", "message/rfc822"
ENDUNG = {PDF: ".pdf", JPEG: ".jpg", PNG: ".png", WEBP: ".webp", MAIL: ".eml"}
ERLAUBT = {PDF: (".pdf",), JPEG: (".jpg", ".jpeg"), PNG: (".png",), WEBP: (".webp",), MAIL: (".eml",)}
VORGABE = {PDF: "Dokument", JPEG: "Foto", PNG: "Bild", WEBP: "Bild", MAIL: "E-Mail"}
CSP_INHALT = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; frame-ancestors 'self'; sandbox"
CSP_MAIL = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; frame-ancestors 'self'; "
            "base-uri 'none'; form-action 'none'; sandbox allow-popups allow-popups-to-escape-sandbox")
MAILKOEPFE = {"from", "to", "subject", "date", "message-id", "received", "mime-version", "return-path",
              "delivered-to"}


# ------------------------------------------------------------------ Testdateien
def pdf(text: str = "Beleg") -> bytes:
    """Minimale PDF-Datei (beginnt mit ``%PDF-``)."""
    return (b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj\n"
            + f"% {text}\n".encode() + b"trailer << /Root 1 0 R >>\n%%EOF\n")


def png(breite: int = 1, hoehe: int = 1, farbe: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    """Gültiges PNG (RGB) mit einer Farbe."""
    def block(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
    zeile = b"\x00" + bytes(farbe) * breite
    roh = zlib.compress(zeile * hoehe, 9)
    return (b"\x89PNG\r\n\x1a\n" + block(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
            + block(b"IDAT", roh) + block(b"IEND", b""))


def jpeg_kopf() -> bytes:
    """Beginnt mit ``FF D8 FF`` (für die Typerkennung genügt der Anfang, dokumente.md 1.2)."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32 + b"\xff\xd9"


def webp_kopf() -> bytes:
    return b"RIFF" + struct.pack("<I", 26) + b"WEBPVP8 " + b"\x00" * 18


def jpeg_masse(daten: bytes) -> tuple[int, int]:
    """(Breite, Höhe) aus dem SOF-Segment eines JPEG."""
    i = 2
    while i < len(daten):
        assert daten[i] == 0xFF, "kein gültiges JPEG-Segment"
        marke = daten[i + 1]
        laenge = struct.unpack(">H", daten[i + 2:i + 4])[0]
        if marke in (0xC0, 0xC1, 0xC2):
            hoehe, breite = struct.unpack(">HH", daten[i + 5:i + 9])
            return breite, hoehe
        i += 2 + laenge
    raise AssertionError("JPEG ohne SOF-Segment")


def mail(betreff: str = "Rechnung (fiktiv)", text: str = "Hallo,\nanbei die Rechnung.\n", *,
         von: str = "Fiktiver Shop <shop@example.invalid>", an: str = "haushalt.eins@example.invalid",
         html: str | None = None, anhaenge: Iterable[tuple[str, str, bytes]] = (), datum=None) -> bytes:
    """Einfache E-Mail (RFC 5322) mit optionalem HTML-Teil und Anhängen ``(dateiname, mime_typ, bytes)``."""
    import datetime as dt

    m = EmailMessage()
    m["From"] = von
    m["To"] = an
    m["Subject"] = betreff
    m["Date"] = format_datetime(datum or dt.datetime(2024, 6, 3, 9, 30, tzinfo=dt.timezone.utc))
    m["Message-ID"] = "<synth-0001@example.invalid>"
    m.set_content(text)
    if html is not None:
        m.add_alternative(html, subtype="html")
    for name, art, daten in anhaenge:
        haupt, unter = art.split("/")
        m.add_attachment(daten, maintype=haupt, subtype=unter, filename=name)
    return m.as_bytes()


# ------------------------------------------------------------------ Orakel der Regeln (dokumente.md 1.2, 1.3)
def typ(daten: bytes) -> str | None:
    if daten.startswith(b"%PDF-"):
        return PDF
    if daten.startswith(b"\xff\xd8\xff"):
        return JPEG
    if daten.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if daten[:4] == b"RIFF" and daten[8:12] == b"WEBP":
        return WEBP
    if b"\x00" in daten[:65536]:
        return None
    text = daten.decode("latin-1")
    zeilen = text.replace("\r\n", "\n").split("\n")
    while zeilen and zeilen[0] == "":
        zeilen.pop(0)
    if zeilen and zeilen[0].startswith("From "):
        zeilen.pop(0)
    namen: list[str] = []
    for z in zeilen:
        if z == "":
            break
        if z[:1] in (" ", "\t"):
            continue
        name, sep, _ = z.partition(":")
        if not sep or not name or any(not (33 <= ord(c) <= 126) for c in name):
            if not namen:
                return None
            break
        namen.append(name.lower())
    if not namen:
        return None
    gefunden = set(namen) & MAILKOEPFE
    if len(gefunden) >= 2 and gefunden & {"from", "subject", "date"}:
        return MAIL
    return None


def dateiname_soll(name: str, mime: str) -> str:
    """dokumente.md 1.3 Schritte 1–5."""
    n = unicodedata.normalize("NFC", name)
    n = n.replace("\\", "/").rsplit("/", 1)[-1]
    n = "".join(c for c in n if not unicodedata.category(c).startswith("C"))
    while n and (n[0].isspace() or n[0] == "."):
        n = n[1:]
    while n and (n[-1].isspace() or n[-1] == "."):
        n = n[:-1]
    if not n:
        n = VORGABE[mime]
    if not n.lower().endswith(ERLAUBT[mime]):
        n += ENDUNG[mime]
    if len(n) > 200:
        e = ENDUNG[mime]
        n = n[:200 - len(e)] + e if n.endswith(e) else n[:200]
    return n


def sha256(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


# ------------------------------------------------------------------ REST-Kurzformen
def multipart(felder: list[tuple[str, str | None, bytes, str | None]]) -> tuple[bytes, str]:
    """Selbst gebauter ``multipart/form-data``-Körper: je Feld (Name, Dateiname oder None, Bytes, Typ).

    Der Dateiname steht unverändert (UTF-8) im Kopf, auch leer (``filename=""``); httpx würde ihn sonst kodieren
    oder weglassen (E-208)."""
    grenze = "kontor-test-grenze-7f3a"
    teile = []
    for name, dateiname, daten, art in felder:
        kopf = f'Content-Disposition: form-data; name="{name}"'
        if dateiname is not None:
            kopf += f'; filename="{dateiname}"'
        kopf += "\r\n"
        if art:
            kopf += f"Content-Type: {art}\r\n"
        teile.append(f"--{grenze}\r\n".encode() + kopf.encode("utf-8") + b"\r\n" + daten + b"\r\n")
    return b"".join(teile) + f"--{grenze}--\r\n".encode(), f"multipart/form-data; boundary={grenze}"


def anhaengen(api: Api, buchung_ids: list[int], name: str, daten: bytes, *, quelle: str | None = None,
              browsertyp: str = "application/octet-stream", erwartet: int | tuple = 201):
    """POST /api/dokumente; ``name`` darf keine Zeichen enthalten, die den Kopf brechen (CR, LF, ``"``)."""
    assert not any(c in name for c in '\r\n"'), "Steuerzeichen im Dateinamen über PATCH prüfen (E-208)"
    params: list[tuple[str, str]] = [("buchung_id", str(b)) for b in buchung_ids]
    if quelle is not None:
        params.append(("quelle", quelle))
    koerper, art = multipart([("datei", name, daten, browsertyp)])
    r = api.post("/api/dokumente", params=params, content=koerper, headers={"Content-Type": art},
                 erwartet=erwartet)
    return r.daten if erwartet == 201 else r


def dokument(api: Api, did: int) -> dict:
    return api.get(f"/api/dokumente/{did}", erwartet=200).daten


def dokumente_der_buchung(api: Api, bid: int) -> list[dict]:
    return api.get(f"/api/buchungen/{bid}/dokumente", erwartet=200).daten["eintraege"]


def inhalt(api: Api, did: int, **params):
    return api.get(f"/api/dokumente/{did}/inhalt", params=params or None, erwartet=200)


def belege(api: Api, bid: int) -> list[dict]:
    return api.buchung_lesen(bid)["belege"]


def zustand(d: dict) -> dict:
    """Protokollform eines Dokuments (dokumente.md 3.1): REST-Form ohne buchung_ids (und ohne Zusatzfelder)."""
    return {k: d[k] for k in ("id", "dateiname", "mime_typ", "groesse", "sha256", "quelle", "erstellt_am")}


# ------------------------------------------------------------------ Bestand und Protokoll
def bestand(api: Api) -> dict[tuple[str, int], dict]:
    """Buchbestand in Protokollform mit Dokumenten (dokumente.md 3.1, E-207)."""
    aus = bestand_m6(api)
    ids: set[int] = set()
    for b in api.alle_buchungen():
        if b["belege"]:
            dids = sorted(x["id"] for x in b["belege"])
            assert [x["id"] for x in b["belege"]] == dids, f"belege von Buchung {b['id']} nicht nach id sortiert"
            aus[("buchung", b["id"])]["dokument_ids"] = dids
            ids.update(dids)
    for did in sorted(ids):
        d = dokument(api, did)
        aus[("dokument", did)] = zustand(d)
    return aus


def sortierschluessel(e: dict) -> tuple[int, int]:
    return OBJEKTE_M18.index(e["objekt"]), e["objekt_id"]


def pruefe_eintraege(a: dict, vorher: dict, nachher: dict) -> None:
    """protokoll.md 3.2 mit Objekt dokument: genau ein Eintrag je geändertem Objekt, Nettowirkung, sortiert."""
    erwartet = {k: (vorher.get(k), nachher.get(k)) for k in set(vorher) | set(nachher)
                if vorher.get(k) != nachher.get(k)}
    ist = {(e["objekt"], e["objekt_id"]): e for e in a["eintraege"]}
    assert len(ist) == len(a["eintraege"]), f"Änderung {a['id']}: Objekt mehrfach eingetragen"
    assert set(ist) == set(erwartet), (
        f"Änderung {a['id']} ({a['aktion']}): Einträge {sorted(ist)} statt {sorted(erwartet)}")
    for k, (v, n) in erwartet.items():
        e = ist[k]
        assert e["art"] == ("angelegt" if v is None else "geloescht" if n is None else "geaendert"), k
        assert e["vorher"] == v, f"{k}: vorher weicht ab:\n{e['vorher']}\nerwartet\n{v}"
        assert e["nachher"] == n, f"{k}: nachher weicht ab:\n{e['nachher']}\nerwartet\n{n}"
    assert a["eintraege"] == sorted(a["eintraege"], key=sortierschluessel), "Einträge falsch sortiert"


def eine_aenderung(api: Api, a0: int, aktion: str, quelle: str = "manuell") -> dict:
    neu = aenderungen_seit(api, a0)
    assert [(x["quelle"], x["aktion"], x["gruppe"]) for x in neu] == [(quelle, aktion, None)], (
        [(x["quelle"], x["aktion"], x["gruppe"]) for x in neu])
    return neu[0]


def operation(api: Api, aktion: str, aufruf, *, quelle: str = "manuell", zustand_fn=None):
    """Führt ``aufruf`` aus und prüft genau eine Änderung ``aktion`` mit Nettowirkung (T 3.5).
    Rückgabe: (Ergebnis des Aufrufs, Änderung, Bestand vorher, Bestand nachher)."""
    zf = zustand_fn or bestand
    v, a0 = zf(api), letzte_aenderung_id(api)
    erg = aufruf()
    n = zf(api)
    a = eine_aenderung(api, a0, aktion, quelle)
    pruefe_eintraege(a, v, n)
    return erg, a, v, n


def rundreise(api: Api, a: dict, vorher: dict, nachher: dict, inhalte: dict[int, bytes] | None = None, *,
              zustand_fn=None) -> None:
    """Rückgängig stellt ``vorher`` her (samt Inhalten), Wiederholen wieder ``nachher`` (T 3.6)."""
    bestand_ = zustand_fn or bestand
    u = api.post(f"/api/aenderungen/{a['id']}/rueckgaengig", erwartet=200).daten
    assert bestand_(api) == vorher, f"Rückgängig von {a['aktion']} stellt den Bestand nicht wieder her"
    pruefe_eintraege(u, nachher, vorher)
    for did, daten in (inhalte or {}).items():
        if ("dokument", did) in vorher:
            assert inhalt(api, did).content == daten, f"Inhalt von Dokument {did} nach Rückgängig verändert"
    w = api.post(f"/api/aenderungen/{u['id']}/rueckgaengig", erwartet=200).daten
    assert bestand_(api) == nachher, f"Wiederholen von {a['aktion']} stellt den Bestand nicht wieder her"
    pruefe_eintraege(w, vorher, nachher)
    for did, daten in (inhalte or {}).items():
        if ("dokument", did) in nachher:
            assert inhalt(api, did).content == daten, f"Inhalt von Dokument {did} nach Wiederholen verändert"


def ohne_wirkung(api: Api, aufruf, *, zustand_fn=None) -> None:
    """Fehlerantwort oder Operation ohne Wirkung: keine Änderung, Bestand unverändert (T 3.5)."""
    zf = zustand_fn or bestand
    a0, z = letzte_aenderung_id(api), zf(api)
    aufruf()
    assert aenderungen_seit(api, a0) == [], "ohne Wirkung bzw. bei Fehlern darf keine Änderung entstehen"
    assert zf(api) == z, "ohne Wirkung bzw. bei Fehlern darf sich der Buchbestand nicht ändern"


def fehler(r, code: str, status: int | None = None) -> None:
    if status is not None:
        assert r.status_code == status, (r.status_code, r.text[:300])
    assert fehlercode(r) == code, r.text[:500]


def orte(r) -> list[list]:
    d = r.json()["fehler"]["details"]
    return [x["ort"] for x in d] if isinstance(d, list) else []


def disposition(kopf: str) -> dict[str, str]:
    """Teile von Content-Disposition: art, filename, filename* (ohne Anführungszeichen)."""
    teile = [t.strip() for t in kopf.split(";")]
    aus = {"art": teile[0].lower()}
    for t in teile[1:]:
        k, _, v = t.partition("=")
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        aus[k.strip().lower()] = v
    return aus


def ascii_name(name: str) -> str:
    """dokumente.md 2.12: Nicht-ASCII und ``?`` → ``_``, ``"`` → ``'``."""
    return "".join("_" if (ord(c) > 126 or ord(c) < 32 or c == "?") else ("'" if c == '"' else c) for c in name)


def csp_menge(kopf: str) -> set[tuple[str, ...]]:
    return {tuple(t.split()) for t in kopf.split(";") if t.strip()}


__all__ = ["aenderungen_seit", "letzte_aenderung_id", "fehlercode"]


# ------------------------------------------------------------------ Mails im Spiegel (Mock und IMAP-Attrappe)
def mock_datei(pfad, nachrichten: list[dict], postfaecher: list[str]) -> "Path":
    """Mock-Datendatei (plugins.md 4) nur mit Mails; ``nachrichten`` mit postfach, nachricht_id, empfangen,
    absender, betreff, text."""
    import json
    from pathlib import Path

    p = Path(pfad)
    p.write_text(json.dumps({"format": "kontor-mock-daten", "version": 1, "bank": {"konten": [], "umsaetze": []},
                             "mail": {"postfaecher": postfaecher, "nachrichten": nachrichten}},
                            ensure_ascii=False), encoding="utf-8")
    return p


def imap_postfaecher(adresse: str, mails: list[tuple["dt.datetime", bytes]]):
    """Postfächer der IMAP-Attrappe (mail.md 8) mit genau diesen Rohnachrichten im Ordner INBOX."""
    from .imap_attrappe import Nachricht, Ordner

    return {adresse.casefold(): {"INBOX": Ordner("INBOX", 4711, [Nachricht(i + 1, zeit, roh)
                                                                for i, (zeit, roh) in enumerate(mails)])}}


def echt_mit_imap(basis, imap, oauth, adresse: str, **felder) -> tuple[Api, dict]:
    """Echtmodus-App mit IMAP-Postfach, angemeldet über die OAuth-Attrappe, nach einem Abruf."""
    from .m6 import CLIENT_SECRET, abruf, anmelden, echt_api, geheimnis_setzen, mail_felder, postfach

    api = echt_api(basis, **mail_felder(imap, oauth, mail_erstabruf_tage=3650, **felder))
    geheimnis_setzen(api, "oauth_client_secret", CLIENT_SECRET)
    p = postfach(api, adresse)
    anmelden(api, oauth, p["id"])
    e = abruf(api)
    assert e["postfaecher"][0]["status"] == "erfolgreich", e
    return api, p
