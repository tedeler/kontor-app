"""KMyMoney-Import (.kmy, gzip-komprimiert oder unkomprimiert) – datenmodell.md Abschnitt 10.

Ablauf:

1. Datei erkennen und XML sicher parsen (keine DTD mit internem Teil, keine
   externen Ressourcen).
2. Inhalt vollständig prüfen; alle gefundenen Fehler werden gesammelt.
3. In einer einzigen Datenbanktransaktion zuordnen (Idempotenz über
   ``extern_id``), Dubletten bewerten und anlegen.

Bei jedem Fehler wird nichts geschrieben.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import xml.etree.ElementTree as ET
import xml.parsers.expat
import zlib
from dataclasses import dataclass, field

from .. import db
from ..buch import BESTAND, KLASSE, buchung_einfuegen
from ..text import iban_gueltig, iban_normalisieren, passend
from ..validierung import BETRAG_MAX
from .ergebnis import ImportErgebnis, ImportMeldung

__all__ = ["importiere_kmy", "importiere_bytes", "ImportErgebnis", "ImportMeldung"]

PRAEFIX = "kmy:"
UNAUSGEGLICHEN = "kontor:unausgeglichen"

TYPABBILDUNG: dict[int, tuple[str, bool]] = {
    1: ("girokonto", False), 2: ("sparkonto", False), 6: ("sparkonto", False), 8: ("sparkonto", False),
    3: ("girokonto", True), 9: ("sparkonto", True), 14: ("sparkonto", True),
    4: ("kreditkonto", False), 5: ("kreditkonto", False), 10: ("kreditkonto", False),
    12: ("ertrag", False), 13: ("aufwand", False), 16: ("eigenkapital", False),
}

_WERT = re.compile(r"^(-?)([0-9]+)(?:/([0-9]+))?$")
_POSTDATE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})(T.*)?$", re.DOTALL)
_DATUM = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

MELDUNGEN = {
    "kontoart_ersetzt": "Die Kontoart wird in Kontor nicht unterstützt und wurde ersetzt.",
    "konto_uebersprungen": "Die Kontoart wird in Kontor nicht unterstützt; das Konto wurde übersprungen.",
    "fremdwaehrung": "Das Konto führt eine Fremdwährung und wurde übersprungen (nur EUR).",
    "hierarchie_angepasst": "Das Elternkonto gehört zu einer anderen Kontoklasse; das Konto wurde Wurzelkonto.",
    "iban_ungueltig": "Die IBAN des Kontos ist ungültig und wurde nicht übernommen.",
    "iban_doppelt": "Die IBAN ist bereits einem anderen Konto zugeordnet und wurde nicht übernommen.",
    "eroeffnungsdatum_ungueltig": "Das Eröffnungsdatum ist ungültig und wurde nicht übernommen.",
    "buchung_uebersprungen": "Die Buchung betrifft eine Fremdwährung oder ein übersprungenes Konto und "
                             "wurde übersprungen.",
    "buchung_ausgeglichen": "Die Buchung war nicht ausgeglichen; ein Ausgleichssplit auf das Konto "
                            "„Unausgeglichen“ wurde ergänzt.",
    "empfaenger_zusammengefasst": "Ein Empfänger gleichen Namens wurde bereits angelegt; beide wurden "
                                  "zusammengefasst.",
    "tag_zusammengefasst": "Ein Tag gleichen Namens wurde bereits angelegt; beide wurden zusammengefasst.",
}


class _Abbruch(Exception):
    def __init__(self, code: str, meldung: str, format_: str | None) -> None:
        super().__init__(meldung)
        self.code, self.meldung, self.format = code, meldung, format_


class _InterneDTD(Exception):
    pass


# ============================================================ 1. Erkennen


def _entpacken(roh: bytes) -> bytes:
    try:
        return gzip.decompress(roh)
    except (OSError, EOFError, zlib.error, ValueError) as e:
        raise _Abbruch("import_datei_beschaedigt",
                       f"Die gzip-Datei ist beschädigt oder unvollständig ({type(e).__name__}).",
                       "kmy-gzip") from None


def _parsen(xml_bytes: bytes, format_: str) -> ET.Element:
    # Durchgang 1: Wohlgeformtheit und DTD prüfen, ohne Entitäten zu expandieren oder etwas zu laden.
    p = xml.parsers.expat.ParserCreate()
    p.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def doctype(name, system_id, public_id, interner_teil):
        if interner_teil:
            raise _InterneDTD()

    def entitaet(*_):
        raise _InterneDTD()

    p.StartDoctypeDeclHandler = doctype
    p.EntityDeclHandler = entitaet
    try:
        p.Parse(xml_bytes, True)
    except _InterneDTD:
        raise _Abbruch("import_format_ungueltig",
                       "Die Datei enthält eine DTD mit Entitätsdeklarationen; das ist keine KMyMoney-Datei.",
                       None) from None
    except (xml.parsers.expat.ExpatError, ValueError, RecursionError) as e:
        raise _Abbruch("import_datei_beschaedigt", f"Das XML ist nicht wohlgeformt: {e}", format_) from None
    # Durchgang 2: Baum aufbauen (keine internen Entitäten mehr möglich).
    try:
        wurzel = ET.fromstring(xml_bytes)
    except (ET.ParseError, ValueError, RecursionError) as e:
        raise _Abbruch("import_datei_beschaedigt", f"Das XML ist nicht wohlgeformt: {e}", format_) from None
    if wurzel.tag != "KMYMONEY-FILE":
        raise _Abbruch("import_format_ungueltig",
                       f"Das Wurzelelement ist <{wurzel.tag}> statt <KMYMONEY-FILE>; keine KMyMoney-Datei.", None)
    return wurzel


def lesen(roh: bytes) -> tuple[str, ET.Element]:
    """Liefert (format, Wurzelelement) oder wirft _Abbruch."""
    if len(roh) == 0:
        raise _Abbruch("import_datei_leer", "Die Datei ist leer.", None)
    if roh[:2] == b"\x1f\x8b":
        format_ = "kmy-gzip"
        xml_bytes = _entpacken(roh)
        if len(xml_bytes) == 0:
            raise _Abbruch("import_datei_leer", "Die gzip-Datei enthält keine Daten.", format_)
    else:
        rest = roh[3:] if roh.startswith(b"\xef\xbb\xbf") else roh
        if not rest.lstrip(b" \t\r\n").startswith(b"<"):
            raise _Abbruch("import_format_ungueltig",
                           "Die Datei ist weder gzip-komprimiert noch XML; keine KMyMoney-Datei.", None)
        format_ = "kmy-xml"
        xml_bytes = roh
    return format_, _parsen(xml_bytes, format_)


# =========================================================== 2. Prüfen


def wert_in_cent(text: str) -> int | None:
    m = _WERT.match(text)
    if not m:
        return None
    vorzeichen, z, n = m.group(1), int(m.group(2)), m.group(3)
    nenner = int(n) if n is not None else 1
    if nenner == 0:
        return None
    if (z * 100) % nenner:
        return None
    cent = z * 100 // nenner
    if vorzeichen:
        cent = -cent
    if not -BETRAG_MAX <= cent <= BETRAG_MAX:
        return None
    return cent


def datum_aus_postdate(text: str) -> str | None:
    m = _POSTDATE.match(text)
    if not m:
        return None
    try:
        dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None
    return m.group(1)


def _ist_standard(kid: str) -> bool:
    return kid.startswith("AStd::")


@dataclass
class _KSplit:
    konto: str
    cent: int
    memo: str
    payee: str
    tags: list[str]


@dataclass
class _KBuchung:
    id: str
    datum: str
    memo: str
    commodity: str
    splits: list[_KSplit]


@dataclass
class _Datei:
    konten: list[ET.Element] = field(default_factory=list)  # ohne Standardkonten
    konto_ids: set[str] = field(default_factory=set)
    payees: list[tuple[str, str]] = field(default_factory=list)
    tags: list[tuple[str, str]] = field(default_factory=list)
    buchungen: list[_KBuchung] = field(default_factory=list)


def pruefen(wurzel: ET.Element) -> tuple[_Datei, list[ImportMeldung]]:
    fehler: list[ImportMeldung] = []

    def f(meldung: str, referenz: str | None) -> None:
        fehler.append(ImportMeldung("import_inhalt_ungueltig", meldung, referenz or None))

    d = _Datei()
    alle_konten = wurzel.findall("ACCOUNTS/ACCOUNT")
    alle_ids = {a.get("id") for a in alle_konten if a.get("id")}
    for a in alle_konten:
        kid = a.get("id")
        if not kid:
            f("Ein Konto hat kein Attribut id.", None)
            continue
        if _ist_standard(kid):
            continue
        if not (a.get("name") or "").strip():
            f(f"Konto {kid}: Attribut name fehlt oder ist leer.", kid)
        if a.get("type") is None:
            f(f"Konto {kid}: Attribut type fehlt.", kid)
        eltern = a.get("parentaccount") or ""
        if eltern and not _ist_standard(eltern) and eltern not in alle_ids:
            f(f"Konto {kid}: Elternkonto {eltern} ist unbekannt.", kid)
        d.konten.append(a)
        d.konto_ids.add(kid)

    payee_ids: set[str] = set()
    for p in wurzel.findall("PAYEES/PAYEE"):
        pid, name = p.get("id"), p.get("name")
        if not pid:
            f("Ein Empfänger hat kein Attribut id.", None)
            continue
        if name is None or not name.strip():
            f(f"Empfänger {pid}: Attribut name fehlt oder ist leer.", pid)
            continue
        payee_ids.add(pid)
        d.payees.append((pid, name))

    tag_ids: set[str] = set()
    for t in wurzel.findall("TAGS/TAG"):
        tid, name = t.get("id"), t.get("name")
        if not tid:
            f("Ein Tag hat kein Attribut id.", None)
            continue
        if name is None or not name.strip():
            f(f"Tag {tid}: Attribut name fehlt oder ist leer.", tid)
            continue
        tag_ids.add(tid)
        d.tags.append((tid, name))
    # Auch fehlerhafte Payees/Tags gelten als bekannt, damit Folgefehler nicht doppelt gemeldet werden.
    bekannte_payees = payee_ids | {p.get("id") for p in wurzel.findall("PAYEES/PAYEE") if p.get("id")}
    bekannte_tags = tag_ids | {t.get("id") for t in wurzel.findall("TAGS/TAG") if t.get("id")}

    for t in wurzel.findall("TRANSACTIONS/TRANSACTION"):
        tid = t.get("id")
        ref = tid or None
        if not tid:
            f("Eine Transaktion hat kein Attribut id.", None)
        postdate = t.get("postdate")
        datum = None
        if postdate is None:
            f(f"Transaktion {tid}: Attribut postdate fehlt.", ref)
        else:
            datum = datum_aus_postdate(postdate)
            if datum is None:
                f(f"Transaktion {tid}: Buchungsdatum {postdate!r} ist ungültig.", ref)
        split_elemente = t.findall("SPLITS/SPLIT")
        if not split_elemente:
            f(f"Transaktion {tid}: keine Splits vorhanden.", ref)
        splits: list[_KSplit] = []
        for s in split_elemente:
            konto = s.get("account")
            if konto is None:
                f(f"Transaktion {tid}: Split ohne Attribut account.", ref)
            elif _ist_standard(konto):
                f(f"Transaktion {tid}: Split bucht auf das Standardkonto {konto}.", ref)
            elif konto not in d.konto_ids:
                f(f"Transaktion {tid}: Split verweist auf unbekanntes Konto {konto}.", ref)
            wert = s.get("value")
            cent = None
            if wert is None:
                f(f"Transaktion {tid}: Split ohne Attribut value.", ref)
            else:
                cent = wert_in_cent(wert)
                if cent is None:
                    f(f"Transaktion {tid}: Betrag {wert!r} ist ungültig oder nicht in ganzen Cent darstellbar.",
                      ref)
            payee = s.get("payee") or ""
            if payee and payee not in bekannte_payees:
                f(f"Transaktion {tid}: Split verweist auf unbekannten Empfänger {payee}.", ref)
            stags = []
            for tg in s.findall("TAG"):
                tgid = tg.get("id")
                if not tgid or tgid not in bekannte_tags:
                    f(f"Transaktion {tid}: Split verweist auf unbekannten Tag {tgid}.", ref)
                else:
                    stags.append(tgid)
            splits.append(_KSplit(konto or "", cent or 0, s.get("memo") or "", payee, stags))
        d.buchungen.append(_KBuchung(tid or "", datum or "", t.get("memo") or "", t.get("commodity") or "",
                                     splits))
    return d, fehler


# ======================================================== 3. Anwenden


@dataclass
class _Lauf:
    warnungen: list[ImportMeldung] = field(default_factory=list)
    z: dict[str, int] = field(default_factory=lambda: {k: 0 for k in (
        "konten_neu", "konten_vorhanden", "kategorien_neu", "kategorien_vorhanden",
        "empfaenger_neu", "empfaenger_vorhanden", "tags_neu", "tags_vorhanden",
        "buchungen_neu", "buchungen_vorhanden", "buchungen_zusammengefuehrt",
        "buchungen_zur_pruefung", "buchungen_uebersprungen", "splits_neu")})

    def warn(self, code: str, referenz: str | None) -> None:
        self.warnungen.append(ImportMeldung(code, MELDUNGEN[code], referenz))


def _paare(a: ET.Element) -> dict[str, str]:
    aus: dict[str, str] = {}
    for kv in a.findall("KEYVALUEPAIRS"):
        for p in kv.findall("PAIR"):
            k = p.get("key")
            if k is not None and k not in aus:
                aus[k] = p.get("value") or ""
    return aus


def _konten_anwenden(con: sqlite3.Connection, datei: _Datei, lauf: _Lauf, max_konto: int) -> tuple[
        dict[str, int], set[str]]:
    art_von: dict[str, str] = {}
    uebersprungen: set[str] = set()
    for a in datei.konten:
        kid = a.get("id")
        try:
            typ = int(a.get("type") or "")
        except ValueError:
            typ = None
        abb = TYPABBILDUNG.get(typ) if typ is not None else None
        waehrung = a.get("currency") or "EUR"
        if abb is None:
            uebersprungen.add(kid)
            lauf.warn("konto_uebersprungen", kid)
            continue
        if waehrung != "EUR":
            uebersprungen.add(kid)
            lauf.warn("fremdwaehrung", kid)
            continue
        art, ersetzt = abb
        if ersetzt:
            lauf.warn("kontoart_ersetzt", kid)
        art_von[kid] = art

    nach_id = {a.get("id"): a for a in datei.konten}
    eltern_von: dict[str, str | None] = {}
    for a in datei.konten:
        kid = a.get("id")
        if kid in uebersprungen:
            continue
        p = a.get("parentaccount") or ""
        if not p or _ist_standard(p) or p in uebersprungen or p not in art_von:
            eltern_von[kid] = None
        elif KLASSE[art_von[p]] != KLASSE[art_von[kid]]:
            eltern_von[kid] = None
            lauf.warn("hierarchie_angepasst", kid)
        else:
            eltern_von[kid] = p

    # Reihenfolge: Dokumentreihenfolge, Elternkonten jeweils vor ihren Kindern.
    reihenfolge: list[str] = []
    besucht: set[str] = set()

    def besuche(kid: str, pfad: set[str]) -> None:
        if kid in besucht:
            return
        p = eltern_von.get(kid)
        if p is not None and p not in pfad:
            besuche(p, pfad | {kid})
        elif p is not None:  # Zyklus in der Datei: als Wurzelkonto übernehmen
            eltern_von[kid] = None
        if kid not in besucht:
            besucht.add(kid)
            reihenfolge.append(kid)

    for a in datei.konten:
        if a.get("id") in art_von:
            besuche(a.get("id"), set())

    abbildung: dict[str, int] = {}
    vergeben: set[int] = set()  # in diesem Lauf über Regel 2 zugeordnete Konten
    for kid in reihenfolge:
        a = nach_id[kid]
        art = art_von[kid]
        klasse = KLASSE[art]
        zaehler = "konten" if klasse in ("bestand", "eigenkapital") else "kategorien"
        ext = PRAEFIX + kid
        r = con.execute("SELECT id FROM konto WHERE extern_id = ?", (ext,)).fetchone()
        if r is not None:
            abbildung[kid] = r["id"]
            lauf.z[zaehler + "_vorhanden"] += 1
            continue
        eltern_kontor = abbildung.get(eltern_von[kid]) if eltern_von[kid] else None
        paare = _paare(a)
        iban = None
        if klasse == "bestand" and "iban" in paare:
            n = iban_normalisieren(paare["iban"])
            if iban_gueltig(n):
                iban = n
            else:
                lauf.warn("iban_ungueltig", kid)
        treffer = None
        if klasse == "bestand":
            if iban is not None:
                treffer = con.execute(
                    "SELECT id FROM konto WHERE extern_id IS NULL AND iban = ? AND id <= ?",
                    (iban, max_konto)).fetchone()
        else:
            for kandidat in con.execute(
                    "SELECT id FROM konto WHERE extern_id IS NULL AND art = ? AND name = ? AND id <= ?"
                    " AND eltern_id IS ? ORDER BY id", (art, a.get("name"), max_konto, eltern_kontor)):
                if kandidat["id"] not in vergeben:
                    treffer = kandidat
                    break
        if treffer is not None and treffer["id"] not in vergeben:
            con.execute("UPDATE konto SET extern_id = ? WHERE id = ?", (ext, treffer["id"]))
            vergeben.add(treffer["id"])
            abbildung[kid] = treffer["id"]
            lauf.z[zaehler + "_vorhanden"] += 1
            continue
        if iban is not None and con.execute("SELECT 1 FROM konto WHERE iban = ?", (iban,)).fetchone():
            lauf.warn("iban_doppelt", kid)
            iban = None
        eroeffnet = a.get("opened") or ""
        if eroeffnet:
            if _DATUM.match(eroeffnet):
                try:
                    dt.date.fromisoformat(eroeffnet)
                except ValueError:
                    eroeffnet = ""
                    lauf.warn("eroeffnungsdatum_ungueltig", kid)
            else:
                eroeffnet = ""
                lauf.warn("eroeffnungsdatum_ungueltig", kid)
        geschlossen = (paare.get("mm-closed") or "").lower() == "yes"
        cur = con.execute(
            "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (a.get("name"), art, eltern_kontor, iban, 1 if geschlossen else 0, eroeffnet or None,
             a.get("description") or "", ext))
        abbildung[kid] = cur.lastrowid
        lauf.z[zaehler + "_neu"] += 1
    return abbildung, uebersprungen


def _empfaenger_anwenden(con, datei: _Datei, lauf: _Lauf, max_id: int) -> dict[str, int]:
    abbildung: dict[str, int] = {}
    for pid, name in datei.payees:
        r = con.execute("SELECT id FROM empfaenger WHERE extern_id = ? AND id <= ? ORDER BY id",
                        (PRAEFIX + pid, max_id)).fetchone()
        if r is None:
            r = con.execute("SELECT id FROM empfaenger WHERE name = ?", (name,)).fetchone()
            if r is not None and r["id"] > max_id:
                lauf.warn("empfaenger_zusammengefasst", pid)
        if r is not None:
            abbildung[pid] = r["id"]
            lauf.z["empfaenger_vorhanden"] += 1
            continue
        cur = con.execute("INSERT INTO empfaenger (name, extern_id) VALUES (?, ?)", (name, PRAEFIX + pid))
        abbildung[pid] = cur.lastrowid
        lauf.z["empfaenger_neu"] += 1
    return abbildung


def _tags_anwenden(con, datei: _Datei, lauf: _Lauf, max_id: int) -> dict[str, int]:
    abbildung: dict[str, int] = {}
    for tid, name in datei.tags:
        r = con.execute("SELECT id FROM tag WHERE extern_id = ? AND id <= ? ORDER BY id",
                        (PRAEFIX + tid, max_id)).fetchone()
        if r is None:
            r = con.execute("SELECT id FROM tag WHERE name_cf = ?", (name.casefold(),)).fetchone()
            if r is not None and r["id"] > max_id:
                lauf.warn("tag_zusammengefasst", tid)
        if r is not None:
            abbildung[tid] = r["id"]
            lauf.z["tags_vorhanden"] += 1
            continue
        cur = con.execute("INSERT INTO tag (name, name_cf, extern_id) VALUES (?, ?, ?)",
                          (name, name.casefold(), PRAEFIX + tid))
        abbildung[tid] = cur.lastrowid
        lauf.z["tags_neu"] += 1
    return abbildung


@dataclass
class _Neu:
    kb: _KBuchung
    splits: list[dict]
    empfaenger_id: int | None
    empfaenger_name: str | None
    tag_ids: list[int]
    exakt: set[int] = field(default_factory=set)
    aehnlich: set[int] = field(default_factory=set)


def _max_id(con, tabelle: str) -> int:
    return con.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM {tabelle}").fetchone()["m"]


def _anwenden(con: sqlite3.Connection, datei: _Datei, lauf: _Lauf, roh: bytes, dateiname: str | None,
              format_: str) -> int:
    max_konto = _max_id(con, "konto")
    max_empf = _max_id(con, "empfaenger")
    max_tag = _max_id(con, "tag")
    max_buchung = _max_id(con, "buchung")
    konten, uebersprungen = _konten_anwenden(con, datei, lauf, max_konto)
    empfaenger = _empfaenger_anwenden(con, datei, lauf, max_empf)
    tags = _tags_anwenden(con, datei, lauf, max_tag)
    art_von = {r["id"]: r["art"] for r in con.execute("SELECT id, art FROM konto")}
    empf_name = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM empfaenger")}

    neue: list[_Neu] = []
    for kb in datei.buchungen:
        if (kb.commodity and kb.commodity != "EUR") or any(s.konto in uebersprungen for s in kb.splits):
            lauf.z["buchungen_uebersprungen"] += 1
            lauf.warn("buchung_uebersprungen", kb.id)
            continue
        if con.execute("SELECT 1 FROM buchung_extern WHERE extern_id = ?", (PRAEFIX + kb.id,)).fetchone():
            lauf.z["buchungen_vorhanden"] += 1
            continue
        splits = [{"konto_id": konten[s.konto], "betrag": s.cent, "memo": s.memo} for s in kb.splits]
        eid = next((empfaenger[s.payee] for s in kb.splits if s.payee), None)
        tag_ids: list[int] = []
        for s in kb.splits:
            for t in s.tags:
                if tags[t] not in tag_ids:
                    tag_ids.append(tags[t])
        neue.append(_Neu(kb, splits, eid, empf_name.get(eid) if eid else None, sorted(tag_ids)))

    # Dublettenbewertung (datenmodell.md 10.4): erst alle bewerten, dann anwenden.
    for n in neue:
        b_datum = dt.date.fromisoformat(n.kb.datum)
        for s in n.splits:
            if art_von[s["konto_id"]] not in BESTAND:
                continue
            for c in con.execute(
                    "SELECT b.id AS id, b.datum AS datum, e.name AS name FROM split s"
                    " JOIN buchung b ON b.id = s.buchung_id LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                    " WHERE s.konto_id = ? AND s.betrag = ? AND b.id <= ?"
                    " AND NOT EXISTS (SELECT 1 FROM buchung_extern x WHERE x.buchung_id = b.id"
                    "                 AND substr(x.extern_id, 1, 4) = 'kmy:')",
                    (s["konto_id"], s["betrag"], max_buchung)):
                c_datum = dt.date.fromisoformat(c["datum"])
                if c_datum == b_datum and passend(n.empfaenger_name, c["name"]):
                    n.exakt.add(c["id"])
                elif abs((c_datum - b_datum).days) <= 3:
                    n.aehnlich.add(c["id"])
        n.aehnlich -= n.exakt
    exakt_zaehler: dict[int, int] = {}
    for n in neue:
        for c in n.exakt:
            exakt_zaehler[c] = exakt_zaehler.get(c, 0) + 1

    unausgeglichen_id: int | None = None
    jetzt = db.jetzt_utc()
    for n in neue:
        ext = PRAEFIX + n.kb.id
        splits = list(n.splits)
        summe = sum(s["betrag"] for s in splits)
        if summe != 0 or len(splits) < 2:
            lauf.warn("buchung_ausgeglichen", n.kb.id)
        if len(n.exakt) == 1 and exakt_zaehler[next(iter(n.exakt))] == 1:
            c = next(iter(n.exakt))
            con.execute("INSERT INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)", (c, ext))
            lauf.z["buchungen_zusammengefuehrt"] += 1
            continue
        if summe != 0 or len(splits) < 2:
            if unausgeglichen_id is None:
                r = con.execute("SELECT id FROM konto WHERE extern_id = ?", (UNAUSGEGLICHEN,)).fetchone()
                if r is None:
                    r = con.execute(
                        "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz,"
                        " extern_id) VALUES ('Unausgeglichen', 'eigenkapital', NULL, NULL, 0, NULL, '', ?)"
                        " RETURNING id", (UNAUSGEGLICHEN,)).fetchone()
                unausgeglichen_id = r["id"]
            splits.append({"konto_id": unausgeglichen_id, "betrag": -summe, "memo": ""})
        bid = buchung_einfuegen(con, n.kb.datum, n.empfaenger_id, n.kb.memo, "importiert", splits,
                                n.tag_ids, [ext])
        lauf.z["buchungen_neu"] += 1
        lauf.z["splits_neu"] += len(splits)
        kandidaten = n.exakt | n.aehnlich
        if kandidaten:
            grund = "mehrdeutig" if n.exakt else "aehnlich"
            vid = con.execute(
                "INSERT INTO dublettenverdacht (buchung_id, grund, status, erstellt_am) VALUES (?, ?, 'offen', ?)",
                (bid, grund, jetzt)).lastrowid
            con.executemany("INSERT INTO verdacht_kandidat (verdacht_id, buchung_id) VALUES (?, ?)",
                            [(vid, c) for c in sorted(kandidaten)])
            lauf.z["buchungen_zur_pruefung"] += 1

    import_id = con.execute(
        "INSERT INTO importvorgang (art, dateiname, sha256, importiert_am, ergebnis) VALUES (?, ?, ?, ?, '{}')",
        ("kmymoney", dateiname, hashlib.sha256(roh).hexdigest(), jetzt)).lastrowid
    return import_id


def _fehlschlag(format_: str | None, fehler: list[ImportMeldung]) -> ImportErgebnis:
    return ImportErgebnis(erfolgreich=False, format=format_, fehler=tuple(fehler), import_id=None)


def importiere_bytes(con: sqlite3.Connection, roh: bytes, dateiname: str | None) -> ImportErgebnis:
    """Kern des Imports auf einer offenen Verbindung (eigene Transaktion)."""
    try:
        format_, wurzel = lesen(roh)
    except _Abbruch as a:
        return _fehlschlag(a.format, [ImportMeldung(a.code, a.meldung, None)])
    datei, fehler = pruefen(wurzel)
    if fehler:
        return _fehlschlag(format_, fehler)
    lauf = _Lauf()
    with db.transaktion(con):
        import_id = _anwenden(con, datei, lauf, roh, dateiname, format_)
        ergebnis = ImportErgebnis(erfolgreich=True, format=format_, warnungen=tuple(lauf.warnungen),
                                  fehler=(), import_id=import_id, **lauf.z)
        con.execute("UPDATE importvorgang SET ergebnis = ? WHERE id = ?",
                    (json.dumps(ergebnis.als_dict(), ensure_ascii=False), import_id))
    return ergebnis


def importiere_kmy(config, quelle: str | os.PathLike[str] | bytes, *,
                   dateiname: str | None = None) -> ImportErgebnis:
    """Importiert eine KMyMoney-Datei in ``config.aktive_datenbank`` (python-api.md 5)."""
    if isinstance(quelle, (bytes, bytearray, memoryview)):
        roh = bytes(quelle)
    elif isinstance(quelle, (str, os.PathLike)):
        pfad = pathlib.Path(quelle)
        roh = pfad.read_bytes()  # FileNotFoundError, wenn der Pfad nicht existiert
        if dateiname is None:
            dateiname = pfad.name
    else:
        raise TypeError("quelle muss ein Pfad oder bytes sein, nicht " + type(quelle).__name__)
    db.schema_anlegen(config.aktive_datenbank)
    con = db.verbinde(config.aktive_datenbank)
    try:
        return importiere_bytes(con, roh, dateiname)
    finally:
        con.close()
