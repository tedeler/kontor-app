"""Dokumente an Buchungen (Feature „dokumente“, D-123).

Ein Dokument ist ein Objekt des Buchbestands (Objektart ``dokument``) mit Dateiname, Typ, Größe, Quelle und dem
SHA-256 seines Inhalts. Die Bytes liegen inhaltsadressiert in ``dokument_inhalt`` und werden nie protokolliert:
Die Protokollform eines Dokuments enthält nur den Hash. Inhalte bleiben erhalten, solange ein Dokument oder das
Änderungsprotokoll (für Rückgängig) sie braucht; sie werden nie durch eine Operation gelöscht.

Die Verknüpfung Dokument ↔ Buchung (``dokument_buchung``) gehört zur Protokollform der Buchung (``dokument_ids``,
nur wenn nicht leer). Ein Dokument ohne Buchung entfällt am Ende jeder protokollierten Operation
(``verwaiste_entfernen``); Rückgängig stellt beides gemeinsam wieder her.

Zulässige Typen werden am Inhalt erkannt: PDF, JPEG, PNG, WebP und E-Mails (RFC 5322, ``message/rfc822``).
E-Mails werden zur Anzeige zerlegt (``mail_lesen``); ihr HTML wird entschärft und nur mit eigener strenger
Inhaltsrichtlinie in einem abgeschotteten Rahmen ausgeliefert (``mail_html``).
"""

from __future__ import annotations

import base64
import datetime as dt
import email
import email.policy
import email.utils
import hashlib
import html
import re
import unicodedata
from email.message import EmailMessage, Message

from . import buch
from .validierung import ApiFehler, Validierungsfehler, fehler_eintrag

PDF, JPEG, PNG, WEBP, MAIL = "application/pdf", "image/jpeg", "image/png", "image/webp", "message/rfc822"
TYPEN = (PDF, JPEG, PNG, WEBP, MAIL)
QUELLEN = ("upload", "kamera", "mail")
_ENDUNG = {PDF: ".pdf", JPEG: ".jpg", PNG: ".png", WEBP: ".webp", MAIL: ".eml"}
_VORGABE = {PDF: "Dokument", JPEG: "Foto", PNG: "Bild", WEBP: "Bild", MAIL: "E-Mail"}
MAX_NAME = 200
MAX_INLINE_BILD = 5 * 1024 * 1024   # eingebettete Bilder einer Mail (cid:) als data:-URL bis zu dieser Größe
CSP_MAIL = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; "
            "frame-ancestors 'self'; base-uri 'none'; form-action 'none'; "
            "sandbox allow-popups allow-popups-to-escape-sandbox")
CSP_INHALT = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; frame-ancestors 'self'; sandbox"


# ================================================================ Erkennen und Prüfen


def typ_erkennen(roh: bytes) -> str | None:
    """Typ am Inhalt (nicht an Dateiname oder Angabe des Browsers)."""
    if roh.startswith(b"%PDF-"):
        return PDF
    if roh.startswith(b"\xff\xd8\xff"):
        return JPEG
    if roh.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if len(roh) >= 12 and roh[:4] == b"RIFF" and roh[8:12] == b"WEBP":
        return WEBP
    if _ist_mail(roh):
        return MAIL
    return None


_KOPFZEILE = re.compile(rb"^[!-9;-~]+:[ \t]?")
_MAILKOEPFE = {"from", "to", "subject", "date", "message-id", "received", "mime-version", "return-path", "delivered-to"}


def _ist_mail(roh: bytes) -> bool:
    if not roh or b"\x00" in roh[:65536]:
        return False
    kopf = roh.lstrip(b"\r\n")[:65536]
    if kopf.startswith(b"From ") and b"\n" in kopf:   # mbox-Trennzeile
        kopf = kopf.split(b"\n", 1)[1]
    erste = kopf.split(b"\n", 1)[0]
    if not _KOPFZEILE.match(erste):
        return False
    m = email.message_from_bytes(roh, policy=email.policy.compat32)
    namen = {k.lower() for k in m.keys()}
    return len(namen & _MAILKOEPFE) >= 2 and bool(namen & {"from", "subject", "date"})


def dateiname_saeubern(name: str | None, typ: str) -> str:
    """Nur der letzte Pfadteil, ohne Steuerzeichen, höchstens MAX_NAME Zeichen, passende Endung."""
    n = unicodedata.normalize("NFC", name or "")
    n = re.split(r"[\\/]", n)[-1]
    n = "".join(c for c in n if unicodedata.category(c)[0] != "C").strip().strip(".")
    if not n:
        n = _VORGABE[typ]
    stamm, punkt, endung = n.rpartition(".")
    if not punkt or ("." + endung.lower()) not in _passende_endungen(typ):
        n = n + _ENDUNG[typ]
    if len(n) > MAX_NAME:
        e = _ENDUNG[typ] if n.lower().endswith(_ENDUNG[typ]) else ""
        n = n[:MAX_NAME - len(e)].rstrip() + e
    return n


def _passende_endungen(typ: str) -> set[str]:
    return {PDF: {".pdf"}, JPEG: {".jpg", ".jpeg"}, PNG: {".png"}, WEBP: {".webp"}, MAIL: {".eml"}}[typ]


def _fehler(code: str, meldung: str, status: int = 422) -> ApiFehler:
    return ApiFehler(status, code, meldung)


# ================================================================ Lesen


def dokument_dict(r, buchung_ids: list[int] | None = None) -> dict:
    d = {"id": r["id"], "dateiname": r["dateiname"], "mime_typ": r["mime_typ"], "groesse": r["groesse"],
         "sha256": r["sha256"], "quelle": r["quelle"], "erstellt_am": r["erstellt_am"]}
    if buchung_ids is not None:
        d["buchung_ids"] = buchung_ids
    return d


def formen(con, ids: list[int]) -> dict[int, dict]:
    """Protokollformen (ohne Inhalt)."""
    aus = {}
    for teil in buch._stueckweise(sorted(set(ids))):
        ph = buch._platzhalter(len(teil))
        for r in con.execute(f"SELECT * FROM dokument WHERE id IN ({ph})", teil):
            aus[r["id"]] = dokument_dict(r)
    return aus


def belege_je_buchung(con, buchung_ids: list[int]) -> dict[int, list[dict]]:
    """``belege`` der Buchungen (datenmodell.md 7): je Buchung die Dokumente nach ID."""
    aus: dict[int, list[dict]] = {}
    for teil in buch._stueckweise(buchung_ids):
        ph = buch._platzhalter(len(teil))
        for r in con.execute("SELECT db.buchung_id, d.id, d.dateiname, d.mime_typ, d.groesse FROM dokument_buchung db"
                             f" JOIN dokument d ON d.id = db.dokument_id WHERE db.buchung_id IN ({ph})"
                             " ORDER BY db.buchung_id, d.id", teil):
            aus.setdefault(r["buchung_id"], []).append(
                {"id": r["id"], "dateiname": r["dateiname"], "mime_typ": r["mime_typ"], "groesse": r["groesse"]})
    return aus


def _zeile(con, did: int):
    r = con.execute("SELECT * FROM dokument WHERE id = ?", (buch.sichere_id(did),)).fetchone()
    if r is None:
        raise buch.nicht_gefunden("Das Dokument")
    return r


def _buchungen_von(con, did: int) -> list[int]:
    return [r[0] for r in con.execute("SELECT buchung_id FROM dokument_buchung WHERE dokument_id = ? ORDER BY 1",
                                      (did,))]


def dokument_lesen(con, did: int) -> dict:
    r = _zeile(con, did)
    return dokument_dict(r, _buchungen_von(con, r["id"]))


def inhalt_lesen(con, did: int) -> tuple[dict, bytes]:
    r = _zeile(con, did)
    i = con.execute("SELECT inhalt FROM dokument_inhalt WHERE sha256 = ?", (r["sha256"],)).fetchone()
    if i is None:  # pragma: no cover - Inhalte werden nie gelöscht
        raise buch.nicht_gefunden("Der Inhalt des Dokuments")
    return dokument_dict(r), bytes(i["inhalt"])


def dokumente_liste(con, buchung_id: int) -> list[dict]:
    buch.buchung_lesen(con, buchung_id)
    return [dokument_dict(r, _buchungen_von(con, r["id"])) for r in con.execute(
        "SELECT d.* FROM dokument d JOIN dokument_buchung db ON db.dokument_id = d.id WHERE db.buchung_id = ?"
        " ORDER BY d.id", (buchung_id,)).fetchall()]


# ================================================================ Schreiben (immer in protokolliert)


def _buchungen_pruefen(con, buchung_ids) -> list[int]:
    if not isinstance(buchung_ids, list) or not buchung_ids or not all(type(b) is int for b in buchung_ids):
        raise Validierungsfehler([fehler_eintrag(["body", "buchung_ids"],
                                                 "Mindestens eine Buchungs-ID (ganze Zahl) erwartet.")])
    ids = sorted(set(buchung_ids))
    vorhanden = {r[0] for teil in buch._stueckweise(ids) for r in con.execute(
        f"SELECT id FROM buchung WHERE id IN ({buch._platzhalter(len(teil))})", teil)}
    if set(ids) - vorhanden:
        raise buch.nicht_gefunden("Die Buchung")
    return ids


def anlegen(con, roh: bytes, dateiname: str | None, buchung_ids: list[int], quelle: str, zeitpunkt: str) -> dict:
    """Neues Dokument aus ``roh`` an ``buchung_ids``. Gleicher Inhalt wird nur einmal gespeichert."""
    if quelle not in QUELLEN:
        raise Validierungsfehler([fehler_eintrag(["query", "quelle"], "Unbekannte Quelle.")])
    ids = _buchungen_pruefen(con, buchung_ids)
    if not roh:
        raise _fehler("dokument_leer", "Die Datei ist leer.")
    typ = typ_erkennen(roh)
    if typ is None:
        raise _fehler("dokument_typ_unbekannt",
                      "Nur PDF-Dateien, E-Mails (.eml) und Bilder (JPEG, PNG, WebP) können angehängt werden.")
    if typ == MAIL and not dateiname:
        dateiname = (_mail_betreff(roh) or "E-Mail")[:MAX_NAME - 4]
    sha = hashlib.sha256(roh).hexdigest()
    con.execute("INSERT OR IGNORE INTO dokument_inhalt (sha256, inhalt) VALUES (?, ?)", (sha, roh))
    did = con.execute("INSERT INTO dokument (dateiname, mime_typ, groesse, sha256, quelle, erstellt_am)"
                      " VALUES (?, ?, ?, ?, ?, ?)",
                      (dateiname_saeubern(dateiname, typ), typ, len(roh), sha, quelle, zeitpunkt)).lastrowid
    con.executemany("INSERT INTO dokument_buchung (dokument_id, buchung_id) VALUES (?, ?)", [(did, b) for b in ids])
    return dokument_lesen(con, did)


def verknuepfen(con, did: int, buchung_ids: list[int]) -> dict:
    r = _zeile(con, did)
    ids = _buchungen_pruefen(con, buchung_ids)
    con.executemany("INSERT OR IGNORE INTO dokument_buchung (dokument_id, buchung_id) VALUES (?, ?)",
                    [(r["id"], b) for b in ids])
    return dokument_lesen(con, r["id"])


def loesen(con, did: int, buchung_id: int) -> dict:
    """Verknüpfung entfernen; hing das Dokument an keiner weiteren Buchung, entfällt es (``geloescht``)."""
    r = _zeile(con, did)
    n = con.execute("DELETE FROM dokument_buchung WHERE dokument_id = ? AND buchung_id = ?",
                    (r["id"], buch.sichere_id(buchung_id))).rowcount
    if not n:
        raise buch.nicht_gefunden("Die Verknüpfung von Dokument und Buchung")
    rest = _buchungen_von(con, r["id"])
    return {"dokument_id": r["id"], "buchung_ids": rest, "geloescht": not rest}


def umbenennen(con, did: int, dateiname) -> dict:
    r = _zeile(con, did)
    if not isinstance(dateiname, str) or not dateiname.strip():
        raise Validierungsfehler([fehler_eintrag(["body", "dateiname"], "Ein Dateiname ist erforderlich.")])
    con.execute("UPDATE dokument SET dateiname = ? WHERE id = ?", (dateiname_saeubern(dateiname, r["mime_typ"]),
                                                                    r["id"]))
    return dokument_lesen(con, r["id"])


def loeschen(con, did: int) -> None:
    r = _zeile(con, did)
    con.execute("DELETE FROM dokument WHERE id = ?", (r["id"],))


def verwaiste_entfernen(con) -> None:
    """Am Ende jeder protokollierten Operation: Dokumente ohne Buchung entfallen (Inhalt bleibt)."""
    con.execute("DELETE FROM dokument WHERE NOT EXISTS (SELECT 1 FROM dokument_buchung db"
                " WHERE db.dokument_id = dokument.id)")


def einfuegen(con, f: dict) -> None:
    """Rückgängig: Dokument mit derselben ID wiederherstellen (Inhalt ist noch vorhanden)."""
    con.execute("INSERT INTO dokument (id, dateiname, mime_typ, groesse, sha256, quelle, erstellt_am)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)", (f["id"], f["dateiname"], f["mime_typ"], f["groesse"], f["sha256"],
                                                  f["quelle"], f["erstellt_am"]))


BEZUG_SQL = (
    "SELECT 1 FROM dokument d WHERE NOT EXISTS (SELECT 1 FROM dokument_inhalt i WHERE i.sha256 = d.sha256)",
    "SELECT 1 FROM dokument_buchung x WHERE NOT EXISTS (SELECT 1 FROM dokument d WHERE d.id = x.dokument_id)",
    "SELECT 1 FROM dokument_buchung x WHERE NOT EXISTS (SELECT 1 FROM buchung b WHERE b.id = x.buchung_id)",
)


# ================================================================ E-Mail aus dem Postfach


def mail_roh_aus_spiegel(r) -> bytes:
    """Rohnachricht einer gespiegelten Mail; ohne gespeicherte Rohfassung (z. B. Mock) aus den Feldern gebaut."""
    if r["roh"] is not None:
        return bytes(r["roh"])
    m = EmailMessage()
    m["From"] = r["absender"] or "unbekannt@example.invalid"
    m["To"] = r["adresse_cf"]
    m["Subject"] = r["betreff"]
    try:
        zeit = dt.datetime.strptime(r["empfangen"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        m["Date"] = email.utils.format_datetime(zeit)
    except ValueError:
        pass
    if r["nachricht_id"].startswith("<"):
        m["Message-ID"] = r["nachricht_id"]
    m.set_content(r["text"] or "")
    return m.as_bytes(policy=email.policy.SMTP)


def aus_mail(con, nachricht_id: int, buchung_ids: list[int], zeitpunkt: str) -> dict:
    r = con.execute("SELECT * FROM mail_nachricht WHERE id = ?", (buch.sichere_id(nachricht_id),)).fetchone()
    if r is None:
        raise buch.nicht_gefunden("Die E-Mail")
    roh = mail_roh_aus_spiegel(r)
    return anlegen(con, roh, (r["betreff"] or "E-Mail")[:MAX_NAME - 4], buchung_ids, "mail", zeitpunkt)


# ================================================================ E-Mail anzeigen


def _nachricht(roh: bytes) -> EmailMessage:
    m = email.message_from_bytes(roh, policy=email.policy.default)
    assert isinstance(m, EmailMessage)
    return m


def _kopf_text(m: Message, name: str) -> str:
    try:
        w = m.get(name)
        return "" if w is None else " ".join(str(w).split())
    except (ValueError, TypeError, IndexError, LookupError):
        return ""


def _mail_betreff(roh: bytes) -> str:
    try:
        return _kopf_text(_nachricht(roh), "Subject")
    except Exception:  # noqa: BLE001 - kaputte Kopfzeilen: ohne Betreff weiter
        return ""


def _adressen(m: Message, name: str) -> list[dict]:
    try:
        werte = m.get_all(name) or []
        return [{"name": n, "adresse": a} for n, a in email.utils.getaddresses([str(w) for w in werte]) if n or a]
    except (ValueError, TypeError, IndexError, LookupError):
        return []


def _inhalt_text(teil: Message) -> str:
    try:
        c = teil.get_content()
    except (LookupError, ValueError, AssertionError, KeyError):
        nutz = teil.get_payload(decode=True) or b""
        c = nutz.decode("utf-8", "replace") if isinstance(nutz, bytes) else str(nutz)
    if isinstance(c, bytes):
        c = c.decode("utf-8", "replace")
    return str(c).replace("\r\n", "\n")


def _teile(m: EmailMessage) -> tuple[Message | None, Message | None, list[tuple[int, Message]]]:
    """(Textteil, HTML-Teil, [(Nummer in walk-Reihenfolge, Anhang)])."""
    try:
        text = m.get_body(preferencelist=("plain",))
        htm = m.get_body(preferencelist=("html",))
    except (KeyError, ValueError, TypeError):
        text = htm = None
    anhaenge = []
    for nr, teil in enumerate(m.walk()):
        if teil.is_multipart() or teil is text or teil is htm:
            continue
        if nr == 0 and teil is m and text is None and htm is None:
            continue
        typ = teil.get_content_type()
        if typ.startswith("text/") and not teil.get_filename() and teil.get_content_disposition() != "attachment":
            continue
        anhaenge.append((nr, teil))
    return text, htm, anhaenge


def _anhang_dict(nr: int, teil: Message) -> dict:
    nutz = teil.get_payload(decode=True)
    groesse = len(nutz) if isinstance(nutz, bytes) else 0
    name = teil.get_filename() or ""
    typ = teil.get_content_type()
    cid = (teil.get("Content-ID") or "").strip().strip("<>")
    return {"nr": nr, "dateiname": " ".join(name.split()) or f"Anhang {nr}", "mime_typ": typ, "groesse": groesse,
            "inline": bool(cid) and teil.get_content_disposition() != "attachment"}


def mail_lesen(roh: bytes) -> dict:
    m = _nachricht(roh)
    text, htm, anhaenge = _teile(m)
    datum = None
    try:
        d = email.utils.parsedate_to_datetime(str(m.get("Date"))) if m.get("Date") else None
        if d is not None:
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            datum = d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError, IndexError):
        datum = None
    return {
        "von": _adressen(m, "From"), "an": _adressen(m, "To"), "cc": _adressen(m, "Cc"),
        "datum": datum, "betreff": _kopf_text(m, "Subject"),
        "text": _inhalt_text(text) if text is not None else (html_als_text(_inhalt_text(htm)) if htm is not None else ""),
        "html": htm is not None,
        "anhaenge": [_anhang_dict(nr, t) for nr, t in anhaenge],
    }


def html_als_text(h: str) -> str:
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1\s*>", " ", h)
    t = re.sub(r"(?i)<br\s*/?>|</p\s*>|</div\s*>|</tr\s*>|</h[1-6]\s*>", "\n", t)
    t = re.sub(r"(?s)<[^>]*>", " ", t)
    t = html.unescape(t)
    zeilen = [" ".join(z.split()) for z in t.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(zeilen)).strip()


_GEFAEHRLICH = re.compile(r"(?is)<(script|iframe|frame|frameset|object|embed|applet|form|base|meta|link|svg|math)"
                          r"\b.*?(?:</\1\s*>|/?>)")
_RESTTAG = re.compile(r"(?is)</?(script|iframe|frame|frameset|object|embed|applet|form|base|meta|link|svg|math)\b[^>]*>")
_EREIGNIS = re.compile(r"""(?is)\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""")
_JS_URL = re.compile(r"""(?is)(\s(?:href|src|action|xlink:href|formaction|background)\s*=\s*["']?)\s*(?:javascript|vbscript|data:text/html)[^"'\s>]*""")
_CID = re.compile(r"""(?i)(["'(])cid:([^"')\s>]+)""")
# externe Adressen in Bildern und Stilen (Zählpixel): gar nicht erst anfragen
_EXTERN_ATTR = re.compile(r"""(?is)(\s(?:src|srcset|background|poster|lowsrc|dynsrc)\s*=\s*)(?:"[^"]*"|'[^']*'|[^\s>]+)""")
_EXTERN_CSS = re.compile(r"""(?is)url\(\s*["']?\s*(?:https?:)?//[^)]*\)|@import[^;]*;?""")


def mail_html(roh: bytes) -> str:
    """Entschärftes HTML der Mail; eingebettete Bilder (cid:) als data:-URL. Externe Inhalte lädt der Browser
    wegen ``CSP_MAIL`` nicht; Skripte laufen wegen ``sandbox`` ohnehin nicht."""
    m = _nachricht(roh)
    _, htm, anhaenge = _teile(m)
    if htm is None:
        raise buch.nicht_gefunden("Der HTML-Teil der E-Mail")
    h = _inhalt_text(htm)
    bilder = {}
    for _, t in anhaenge:
        cid = (t.get("Content-ID") or "").strip().strip("<>")
        if cid and t.get_content_maintype() == "image" and t.get_content_type() != "image/svg+xml":
            nutz = t.get_payload(decode=True)
            if isinstance(nutz, bytes) and len(nutz) <= MAX_INLINE_BILD:
                bilder[cid] = f"data:{t.get_content_type()};base64,{base64.b64encode(nutz).decode('ascii')}"
    h = _GEFAEHRLICH.sub("", h)
    h = _RESTTAG.sub("", h)
    h = _EREIGNIS.sub("", h)
    h = _JS_URL.sub(r"\1#", h)
    h = _EXTERN_ATTR.sub(lambda x: x.group(1) + _attr_wert(x.group(0)[len(x.group(1)):], bilder), h)
    h = _EXTERN_CSS.sub("none", h)
    kopf = ('<!DOCTYPE html><html><head><meta charset="utf-8"><base target="_blank">'
            '<style>body{font-family:system-ui,sans-serif;margin:12px;color:#111;background:#fff}'
            'img{max-width:100%;height:auto}</style></head><body>')
    return kopf + h + "</body></html>"


def _attr_wert(wert: str, bilder: dict[str, str]) -> str:
    """Bildquelle: cid: → eingebettetes Bild, data:image → bleibt, alles andere → leeres Bild."""
    w = wert.strip().strip("\"'").strip()
    if w.lower().startswith("cid:"):
        return '"' + bilder.get(w[4:], "data:,") + '"'
    if re.match(r"(?i)data:image/(png|jpeg|gif|webp);", w):
        return '"' + w + '"'
    return '"data:,"'


def mail_anhang(roh: bytes, nr: int) -> tuple[str, str, bytes]:
    """(Dateiname, Typ, Bytes) eines Anhangs der Mail nach seiner Nummer."""
    m = _nachricht(roh)
    _, _, anhaenge = _teile(m)
    for n, t in anhaenge:
        if n == nr:
            nutz = t.get_payload(decode=True)
            if not isinstance(nutz, bytes):
                nutz = t.as_bytes() if t.get_content_type() == MAIL else b""
            d = _anhang_dict(n, t)
            return d["dateiname"], d["mime_typ"], nutz
    raise buch.nicht_gefunden("Der Anhang")


def anzeige_typ(typ: str) -> str:
    """Typ, mit dem ein Mail-Anhang ausgeliefert wird: nur ungefährliche Typen inline, sonst Download."""
    return typ if typ in (PDF, JPEG, PNG, WEBP, "image/gif", "text/plain") else "application/octet-stream"


__all__ = ["anlegen", "verknuepfen", "loesen", "umbenennen", "loeschen", "dokument_lesen", "inhalt_lesen",
           "mail_lesen", "mail_html", "mail_anhang", "aus_mail", "formen", "belege_je_buchung"]
