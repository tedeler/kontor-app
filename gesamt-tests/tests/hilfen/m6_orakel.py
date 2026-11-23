"""Unabhängige Orakel für Meilenstein 6 (nur aus der Spezifikation, kein Generatorcode).

- ``mt940_umsaetze`` / ``camt_umsaetze``: Abbildung nach ``fints.md`` 3.4 aus MT940-Text bzw.
  camt.052-XML; Hash-Kennung mit laufender Nummer je Abruf.
- ``mail_nachricht``: Abbildung einer RFC-5322-Nachricht nach ``mail.md`` 3.3.
- ``erinnerungen``: Nummern der TAN-Erinnerungen je Planer-Takt (``benachrichtigungen.md`` 5).
- ``utf7_imap``: modifiziertes UTF-7 nach RFC 3501 5.1.3.
"""

from __future__ import annotations

import base64
import datetime as dt
import email
import email.header
import email.policy
import email.utils
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from fractions import Fraction

from generator.iban import ist_gueltig, normalisiere


# ================================================================ FinTS

def _iban_oder_none(text: str | None) -> str | None:
    if not text:
        return None
    t = normalisiere(text)
    return t if ist_gueltig(t) else None


def hash_kennung(u: dict, n: int) -> str:
    teile = [u["buchungstag"], u["valuta"] or "", str(u["betrag"]), u["gegenpartei_iban"] or "",
             u["gegenpartei_name"] or "", u["verwendungszweck"], "S" if u["storno"] else ""]
    return "h:" + hashlib.sha256("|".join(teile).encode("utf-8")).hexdigest()[:16] + f":{n}"


def _nummerieren(liste: list[dict]) -> list[dict]:
    gesehen: dict[str, int] = {}
    for u in liste:
        if u["umsatz_id"] is None:
            h = hash_kennung(u, 0)
            gesehen[h] = gesehen.get(h, 0) + 1
            u["umsatz_id"] = hash_kennung(u, gesehen[h])
    return liste


def mt940_umsaetze(iban: str, text: str) -> list[dict]:
    """MT940 (fints.md 3.4) → Liste von BankUmsatz-Dicts in Lieferreihenfolge."""
    felder: list[tuple[str, str]] = []
    for zeile in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^:([0-9]{2}[A-Z]?):(.*)$", zeile)
        if m:
            felder.append((m[1], m[2]))
        elif zeile == "-" or zeile == "":
            continue
        elif felder:
            felder[-1] = (felder[-1][0], felder[-1][1] + zeile)
    aus = []
    i = 0
    while i < len(felder):
        tag, wert = felder[i]
        if tag != "61":
            i += 1
            continue
        m = re.match(r"^([0-9]{2})([0-9]{2})([0-9]{2})([0-9]{4})?(RC|RD|C|D)[A-Z]?([0-9]+,[0-9]{0,2})N", wert)
        assert m, wert
        valuta = dt.date(2000 + int(m[1]), int(m[2]), int(m[3]))
        if m[4]:
            bt = dt.date(valuta.year, int(m[4][:2]), int(m[4][2:]))
            if (bt - valuta).days > 180:
                bt = bt.replace(year=bt.year - 1)
            elif (valuta - bt).days > 180:
                bt = bt.replace(year=bt.year + 1)
        else:
            bt = valuta
        ganz, _, rest = m[6].partition(",")
        cent = int(ganz) * 100 + int((rest + "00")[:2])
        vorzeichen = {"C": 1, "D": -1, "RC": -1, "RD": 1}[m[5]]
        unter: list[tuple[str, str]] = []
        if i + 1 < len(felder) and felder[i + 1][0] == "86":
            inhalt = felder[i + 1][1]
            for k, v in re.findall(r"\?([0-9]{2})([^?]*)", inhalt):
                unter.append((k, v))
            i += 1
        zweck = "".join(v for k, v in unter if 20 <= int(k) <= 29 or 60 <= int(k) <= 63)
        name = "".join(v for k, v in unter if k in ("32", "33")) or None
        konto = next((v for k, v in unter if k == "31"), None)
        aus.append({"iban": iban, "buchungstag": bt.isoformat(), "valuta": valuta.isoformat(), "betrag": vorzeichen * cent,
                    "waehrung": "EUR", "gegenpartei_name": name, "gegenpartei_iban": _iban_oder_none(konto),
                    "verwendungszweck": zweck, "vormerkung": False, "storno": m[5] in ("RC", "RD"),
                    "umsatz_id": None})
        i += 1
    return _nummerieren(aus)


def _lokal(e: ET.Element) -> str:
    return e.tag.rsplit("}", 1)[-1]


def _kind(e: ET.Element | None, *pfad: str) -> ET.Element | None:
    for name in pfad:
        if e is None:
            return None
        e = next((k for k in e if _lokal(k) == name), None)
    return e


def _text(e: ET.Element | None, *pfad: str) -> str | None:
    k = _kind(e, *pfad)
    return k.text if k is not None else None


def camt_ntry(iban: str, ntry: ET.Element) -> dict | None:
    """Ein camt.052-Ntry (fints.md 3.4) → BankUmsatz-Dict (umsatz_id None ohne Referenz) oder None."""
    amt = _kind(ntry, "Amt")
    if amt is None or amt.get("Ccy") != "EUR":
        return None
    ganz, _, rest = amt.text.strip().partition(".")
    cent = int(ganz) * 100 + int((rest + "00")[:2])
    ind = _text(ntry, "CdtDbtInd")
    storno = (_text(ntry, "RvslInd") or "").strip() == "true"
    sts = _text(ntry, "Sts", "Cd") or _text(ntry, "Sts")
    if sts not in ("BOOK", "PDNG"):
        return None
    bt = _text(ntry, "BookgDt", "Dt") or _text(ntry, "ValDt", "Dt")
    seite = ind if not storno else ("CRDT" if ind == "DBIT" else "DBIT")
    partei, konto = ("Cdtr", "CdtrAcct") if seite == "DBIT" else ("Dbtr", "DbtrAcct")
    tx = _kind(ntry, "NtryDtls", "TxDtls")
    pt = _kind(tx, "RltdPties")
    name = _text(pt, partei, "Pty", "Nm") or _text(pt, partei, "Nm") or None
    ref = (_text(ntry, "AcctSvcrRef") or "").strip()
    rmt = _kind(tx, "RmtInf")
    zweck = "".join((k.text or "") for k in (rmt if rmt is not None else []) if _lokal(k) == "Ustrd")
    return {"iban": iban, "buchungstag": bt, "valuta": _text(ntry, "ValDt", "Dt"),
            "betrag": cent if ind == "CRDT" else -cent, "waehrung": "EUR", "gegenpartei_name": name,
            "gegenpartei_iban": _iban_oder_none(_text(pt, konto, "Id", "IBAN")), "verwendungszweck": zweck,
            "vormerkung": sts == "PDNG", "storno": storno, "umsatz_id": ("ref:" + ref) if ref else None}


def camt_umsaetze(iban: str, dokumente: list[bytes]) -> list[dict]:
    aus = []
    for doc in dokumente:
        wurzel = ET.fromstring(doc)
        for e in wurzel.iter():
            if _lokal(e) == "Ntry":
                u = camt_ntry(iban, e)
                if u is not None:
                    aus.append(u)
    return _nummerieren(aus)


def sortiert(liste: list[dict]) -> list[dict]:
    return sorted(liste, key=lambda u: (u["buchungstag"], u["umsatz_id"]))


def erwartete_umsaetze(erwartung: dict, profil: str, iban: str, von: dt.date, bis: dt.date,
                       heute: dt.date | None = None) -> list[dict]:
    """Erwartetes Ergebnis von ``umsaetze(iban, von, bis)`` gegen die Attrappe (fints.md 3.3, 6)."""
    heute = heute or dt.date.fromisoformat(erwartung["heute"])
    aus = []
    for w in erwartung["umsaetze"]:
        u = w[profil]
        if w["iban"] != iban or u is None:
            continue
        b = dt.date.fromisoformat(u["buchungstag"])
        if not (von <= b <= bis):
            continue
        if w["vormerkung"]:
            ab, bis_s = (dt.date.fromisoformat(x) for x in w["sichtbar"])
            if not (ab <= heute < bis_s):
                continue
        elif b > heute:
            continue
        aus.append(dict(u))
    return sortiert(aus)


# ================================================================ Mail

def html_regel(h: str) -> str:
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


def mail_nachricht(roh: bytes, postfach: str, empfangen: dt.datetime, uidvalidity: int, uid: int) -> dict:
    """mail.md 3.3 (Orakel mit ``email.message_from_bytes`` im Kompatibilitätsmodus)."""
    m = email.message_from_bytes(roh, policy=email.policy.compat32)
    mid = (m.get("Message-ID") or "").strip()
    absender = email.utils.parseaddr(str(email.header.make_header(email.header.decode_header(m.get("From", "")))))[1]
    betreff_roh = m.get("Subject")
    betreff = ""
    if betreff_roh is not None:
        betreff = str(email.header.make_header(email.header.decode_header(re.sub(r"\r?\n[ \t]", " ", betreff_roh))))
    text = None
    html_text = None
    for teil in m.walk():
        if teil.is_multipart():
            continue
        if (teil.get("Content-Disposition") or "").split(";")[0].strip().lower() == "attachment":
            continue
        art = teil.get_content_type()
        if art == "text/plain" and text is None:
            text = _teil_text(teil)
        elif art == "text/html" and html_text is None:
            html_text = html_regel(_teil_text(teil))
    return {"nachricht_id": mid or f"imap:{uidvalidity}:{uid}", "postfach": postfach,
            "empfangen": empfangen.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "absender": absender, "betreff": betreff,
            "text": text if text is not None else (html_text if html_text is not None else "")}


def mbox_lesen(inhalt: bytes) -> list[tuple[dt.datetime, bytes]]:
    """mbox (From-Zeile mit asctime in UTC) → [(INTERNALDATE, RFC-5322-Bytes mit CRLF)]."""
    aus = []
    for block in re.split(rb"(?m)^(?=From MAILER-DAEMON )", inhalt):
        if not block.strip():
            continue
        kopf, _, rest = block.partition(b"\n")
        zeit = dt.datetime.strptime(kopf.decode()[len("From MAILER-DAEMON "):], "%a %b %d %H:%M:%S %Y").replace(
            tzinfo=dt.timezone.utc)
        zeilen = rest.rstrip(b"\n").split(b"\n")
        zeilen = [z[1:] if z.startswith(b">From ") else z for z in zeilen]
        aus.append((zeit, b"\r\n".join(zeilen) + b"\r\n"))
    return aus


def utf7_imap(name: str) -> str:
    """Modifiziertes UTF-7 (RFC 3501 5.1.3)."""
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


# ================================================================ TAN-Erinnerungen

def erinnerungen(erstellt: dt.datetime, gueltig_bis: dt.datetime, intervall: int, anzahl: int,
                 takte: list[dt.datetime]) -> list[list[int]]:
    m = 0
    aus = []
    for t in takte:
        neu = []
        if intervall > 0 and t <= gueltig_bis:
            k = int(Fraction(int((t - erstellt).total_seconds()), intervall * 60))  # floor für ≥ 0
            if t < erstellt:
                k = -1
            n = min(k, anzahl)
            if n >= 1 and n > m:
                neu, m = [n], n
        aus.append(neu)
    return aus
