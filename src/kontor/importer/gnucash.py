"""GnuCash-Import (XML gzip/unkomprimiert und SQLite, nur lesend) – gnucash.md, Meilenstein 4.

Ablauf wie beim KMyMoney-Import (``kmymoney.py``):

1. Datei erkennen (gzip → XML, ``SQLite format 3``, XML) und sicher lesen.
   SQLite-Dateien werden nie auf der Platte geöffnet, sondern als Kopie im
   Arbeitsspeicher (``sqlite3.Connection.deserialize``) – die Datei bleibt
   unverändert, es entstehen keine Nebendateien.
2. Beide Formate werden in dasselbe neutrale Modell (``_GKonto``,
   ``_GBuchung``) übersetzt und vollständig geprüft (alle Fehler gesammelt).
3. In einer einzigen protokollierten Transaktion zuordnen (Idempotenz über
   ``gnc:<GUID>``), Dubletten bewerten und anlegen.

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

from .. import buch, db, protokoll
from ..buch import BESTAND, KLASSE, buchung_einfuegen
from ..text import iban_gueltig, iban_normalisieren, passend
from ..validierung import BETRAG_MAX
from .ergebnis import ImportErgebnis, ImportMeldung
from .kmymoney import MELDUNGEN, UNAUSGEGLICHEN

__all__ = ["importiere_gnucash", "importiere_bytes", "ImportErgebnis", "ImportMeldung"]

PRAEFIX = "gnc:"
_NS = {p: f"http://www.gnucash.org/XML/{p}" for p in ("gnc", "act", "book", "cmdty", "slot", "split", "trn", "ts")}
_SQLITE_KOPF = b"SQLite format 3\x00"

# GnuCash-Typ → (Kontor-Art, Kontoart ersetzt?) (gnucash.md 6.1); fehlt = übersprungen
TYPABBILDUNG: dict[str, tuple[str, bool]] = {
    "BANK": ("girokonto", False), "CASH": ("girokonto", True),
    "ASSET": ("sparkonto", True), "RECEIVABLE": ("sparkonto", True),
    "CREDIT": ("kreditkonto", False), "LIABILITY": ("kreditkonto", False), "PAYABLE": ("kreditkonto", True),
    "INCOME": ("ertrag", False), "EXPENSE": ("aufwand", False), "EQUITY": ("eigenkapital", False),
}
_IBAN_FORM = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")
_WERT = re.compile(r"^(-?)([0-9]+)(?:/([0-9]+))?$")
_DATUM = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})")
_DATUM14 = re.compile(r"^([0-9]{4})([0-9]{2})([0-9]{2})[0-9]{6}$")


class _Abbruch(Exception):
    def __init__(self, code: str, meldung: str, format_: str | None) -> None:
        super().__init__(meldung)
        self.code, self.meldung, self.format = code, meldung, format_


class _InterneDTD(Exception):
    pass


# ================================================================ Modell


@dataclass
class _GKonto:
    guid: str
    name: str
    typ: str
    eltern: str | None  # GUID (None = keine Elternangabe bzw. Wurzel)
    eur: bool
    code: str
    beschreibung: str
    versteckt: bool


@dataclass
class _GSplit:
    konto: str
    cent: int
    memo: str


@dataclass
class _GBuchung:
    guid: str
    datum: str
    beschreibung: str  # Rohtext (strip() erst bei der Abbildung)
    notiz: str
    eur: bool
    splits: list[_GSplit]


@dataclass
class _Buch:
    konten: list[_GKonto] = field(default_factory=list)
    buchungen: list[_GBuchung] = field(default_factory=list)


def _cent(vorzeichen: str, zaehler: int, nenner: int) -> int | None:
    if nenner <= 0 or (zaehler * 100) % nenner:
        return None
    cent = zaehler * 100 // nenner
    if vorzeichen:
        cent = -cent
    return cent if -BETRAG_MAX <= cent <= BETRAG_MAX else None


def _wert_text(text: str) -> int | None:
    m = _WERT.match(text)
    if not m:
        return None
    return _cent(m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) is not None else 1)


def _datum(text: str) -> str | None:
    """gnucash.md 5: ``YYYY-MM-DD…`` oder 14 Ziffern; nur das Kalenderdatum zählt."""
    m = _DATUM14.match(text)
    kandidat = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    if kandidat is None:
        m = _DATUM.match(text)
        kandidat = m.group(1) if m else None
    if kandidat is None:
        return None
    try:
        dt.date.fromisoformat(kandidat)
    except ValueError:
        return None
    return kandidat


def _ist_eur(space: str | None, ident: str | None) -> bool:
    return space in ("ISO4217", "CURRENCY") and ident == "EUR"


# =================================================================== XML


def _xml_parsen(xml_bytes: bytes, format_: str) -> ET.Element:
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
                       "Die Datei enthält eine DTD mit Entitätsdeklarationen; das ist keine GnuCash-Datei.",
                       format_) from None
    except (xml.parsers.expat.ExpatError, ValueError, RecursionError) as e:
        raise _Abbruch("import_datei_beschaedigt", f"Das XML ist nicht wohlgeformt: {e}", format_) from None
    try:
        wurzel = ET.fromstring(xml_bytes)
    except (ET.ParseError, ValueError, RecursionError) as e:
        raise _Abbruch("import_datei_beschaedigt", f"Das XML ist nicht wohlgeformt: {e}", format_) from None
    if wurzel.tag != "gnc-v2":
        raise _Abbruch("import_format_ungueltig",
                       f"Das Wurzelelement ist <{wurzel.tag}> statt <gnc-v2>; keine GnuCash-Datei.", format_)
    buecher = [k for k in wurzel if k.tag == f"{{{_NS['gnc']}}}book"]
    if len(buecher) != 1:
        raise _Abbruch("import_format_ungueltig",
                       f"Die Datei enthält {len(buecher)} Bücher (gnc:book); erwartet wird genau eines.", format_)
    return buecher[0]


def _q(tag: str) -> str:
    p, n = tag.split(":")
    return f"{{{_NS[p]}}}{n}"


def _kind(e: ET.Element, tag: str) -> ET.Element | None:
    return e.find(_q(tag))


def _text(e: ET.Element, tag: str) -> str | None:
    k = _kind(e, tag)
    if k is None:
        return None
    return k.text or ""


def _slots(e: ET.Element | None) -> dict[str, str]:
    aus: dict[str, str] = {}
    if e is None:
        return aus
    for s in e.findall("slot"):
        k, v = s.find(_q("slot:key")), s.find(_q("slot:value"))
        if k is None or v is None:
            continue
        schluessel = k.text or ""
        if schluessel not in aus:
            aus[schluessel] = "".join(v.itertext())
    return aus


def _waehrung_xml(e: ET.Element | None) -> bool:
    if e is None:
        return True
    return _ist_eur(_text(e, "cmdty:space"), _text(e, "cmdty:id"))


def _aus_xml(book: ET.Element) -> tuple[_Buch, set[str], list[ImportMeldung]]:
    """Liefert Buch, GUIDs der ROOT-Konten und gefundene Inhaltsfehler."""
    fehler: list[ImportMeldung] = []

    def f(meldung: str, ref: str | None) -> None:
        fehler.append(ImportMeldung("import_inhalt_ungueltig", meldung, ref or None))

    b = _Buch()
    wurzeln: set[str] = set()
    konto_elemente = [k for k in book if k.tag == _q("gnc:account")]
    alle = {(_text(a, "act:id") or "").strip() for a in konto_elemente} - {""}
    for a in konto_elemente:
        guid = (_text(a, "act:id") or "").strip()
        typ = (_text(a, "act:type") or "").strip()
        name = _text(a, "act:name")
        if not guid:
            f("Ein Konto hat keine GUID (act:id).", None)
            continue
        if typ == "ROOT":
            wurzeln.add(guid)
            continue
        if name is None or not name.strip():
            f(f"Konto {guid}: act:name fehlt oder ist leer.", guid)
        if not typ:
            f(f"Konto {guid}: act:type fehlt oder ist leer.", guid)
        eltern = _text(a, "act:parent")
        eltern = eltern.strip() if eltern is not None else None
        if eltern == "":
            eltern = None
        if eltern is not None and eltern not in alle:
            f(f"Konto {guid}: Elternkonto {eltern} ist unbekannt.", guid)
        slots = _slots(_kind(a, "act:slots"))
        b.konten.append(_GKonto(guid, name or "", typ, eltern, _waehrung_xml(_kind(a, "act:commodity")),
                                _text(a, "act:code") or "", _text(a, "act:description") or "",
                                (slots.get("hidden") or "").strip().lower() == "true"))
    konto_typ = {k.guid: k.typ for k in b.konten}
    for t in book:
        if t.tag != _q("gnc:transaction"):
            continue
        guid = (_text(t, "trn:id") or "").strip()
        ref = guid or None
        if not guid:
            f("Eine Transaktion hat keine GUID (trn:id).", None)
        dp = _kind(t, "trn:date-posted")
        datum_text = _text(dp, "ts:date") if dp is not None else None
        datum = None
        if datum_text is None or not datum_text.strip():
            f(f"Transaktion {guid}: Buchungsdatum fehlt.", ref)
        else:
            datum = _datum(datum_text.strip())
            if datum is None:
                f(f"Transaktion {guid}: Buchungsdatum {datum_text!r} ist ungültig.", ref)
        ss = _kind(t, "trn:splits")
        split_elemente = ss.findall(_q("trn:split")) if ss is not None else []
        if not split_elemente:
            f(f"Transaktion {guid}: keine Splits vorhanden.", ref)
        splits: list[_GSplit] = []
        for s in split_elemente:
            konto = (_text(s, "split:account") or "").strip()
            if not konto:
                f(f"Transaktion {guid}: Split ohne Konto (split:account).", ref)
            elif konto in wurzeln:
                f(f"Transaktion {guid}: Split bucht auf das Wurzelkonto {konto}.", ref)
            elif konto not in konto_typ:
                f(f"Transaktion {guid}: Split verweist auf unbekanntes Konto {konto}.", ref)
            wert = _text(s, "split:value")
            cent = None
            if wert is None or not wert.strip():
                f(f"Transaktion {guid}: Split ohne Betrag (split:value).", ref)
            else:
                cent = _wert_text(wert.strip())
                if cent is None:
                    f(f"Transaktion {guid}: Betrag {wert!r} ist ungültig oder nicht in ganzen Cent darstellbar.",
                      ref)
            splits.append(_GSplit(konto, cent or 0, _text(s, "split:memo") or ""))
        notiz = _slots(_kind(t, "trn:slots")).get("notes", "")
        b.buchungen.append(_GBuchung(guid, datum or "", _text(t, "trn:description") or "", notiz,
                                     _waehrung_xml(_kind(t, "trn:currency")), splits))
    return b, wurzeln, fehler


# ================================================================ SQLite

_PFLICHT = {
    "books": ("root_account_guid",),
    "accounts": ("guid", "name", "account_type", "commodity_guid", "parent_guid", "code", "description", "hidden"),
    "transactions": ("guid", "currency_guid", "post_date", "description"),
    "splits": ("guid", "tx_guid", "account_guid", "memo", "value_num", "value_denom"),
}
_OPTIONAL = {"commodities": ("guid", "namespace", "mnemonic"), "slots": ("obj_guid", "name", "string_val")}


def _s(wert) -> str:
    """NULL in Textspalten gilt wie ein fehlendes Element (gnucash.md 4.2)."""
    return "" if wert is None else str(wert)


def _aus_sqlite(roh: bytes) -> tuple[_Buch, list[ImportMeldung]]:
    fmt = "gnc-sqlite"
    con = sqlite3.connect(":memory:")
    try:
        try:
            con.deserialize(roh)
            con.execute("PRAGMA query_only = ON")
            tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for name in ("books", "accounts", "transactions", "splits"):
                if name not in tabellen:
                    raise _Abbruch("import_format_ungueltig",
                                   f"Die SQLite-Datei enthält keine Tabelle {name}; keine GnuCash-Datei.", fmt)
            vorhanden = set()
            for name, spalten in {**_PFLICHT, **_OPTIONAL}.items():
                if name not in tabellen:
                    continue
                vorhanden.add(name)
                ist = {r[1] for r in con.execute(f"PRAGMA table_info({name})")}
                fehlend = [s for s in spalten if s not in ist]
                if fehlend:
                    raise _Abbruch("import_format_ungueltig",
                                   f"Der Tabelle {name} fehlen die Spalten {', '.join(fehlend)}; keine GnuCash-Datei.",
                                   fmt)
            buecher = con.execute("SELECT root_account_guid FROM books").fetchall()
            if len(buecher) != 1:
                raise _Abbruch("import_format_ungueltig",
                               f"Die Tabelle books enthält {len(buecher)} Bücher; erwartet wird genau eines.", fmt)
            wurzel = _s(buecher[0][0])
            waehrung: dict[str, bool] = {}
            if "commodities" in vorhanden:
                for g, ns, mn in con.execute("SELECT guid, namespace, mnemonic FROM commodities"):
                    waehrung[_s(g)] = _ist_eur(_s(ns), _s(mn))

            def eur(g) -> bool:
                return waehrung.get(_s(g), True) if g is not None else True

            konten = con.execute("SELECT guid, name, account_type, commodity_guid, parent_guid, code, description,"
                                 " hidden FROM accounts ORDER BY rowid").fetchall()
            transaktionen = con.execute(
                "SELECT guid, currency_guid, post_date, description FROM transactions ORDER BY rowid").fetchall()
            splits_je: dict[str, list] = {}
            for r in con.execute("SELECT tx_guid, account_guid, memo, value_num, value_denom FROM splits"
                                 " ORDER BY rowid"):
                splits_je.setdefault(_s(r[0]), []).append(r)
            notizen: dict[str, str] = {}
            if "slots" in vorhanden:
                for g, wert in con.execute("SELECT obj_guid, string_val FROM slots WHERE name = 'notes'"
                                           " ORDER BY rowid"):
                    notizen.setdefault(_s(g), _s(wert))
        except sqlite3.DatabaseError as e:
            raise _Abbruch("import_datei_beschaedigt",
                           f"Die SQLite-Datei ist beschädigt oder nicht lesbar ({type(e).__name__}).", fmt) from None
    finally:
        con.close()

    fehler: list[ImportMeldung] = []

    def f(meldung: str, ref: str | None) -> None:
        fehler.append(ImportMeldung("import_inhalt_ungueltig", meldung, ref or None))

    eltern_von = {_s(r[0]): (_s(r[4]) or None) for r in konten}
    typ_von = {_s(r[0]): _s(r[2]) for r in konten}

    def im_hauptbaum(g: str) -> bool:
        gesehen: set[str] = set()
        e = eltern_von.get(g)
        while e is not None and e not in gesehen:
            if e == wurzel:
                return True
            gesehen.add(e)
            e = eltern_von.get(e)
        return False

    haupt = {g for g in eltern_von if g and g != wurzel and im_hauptbaum(g)}
    b = _Buch()
    for g, name, typ, cg, eltern, code, besch, hidden in konten:
        g = _s(g)
        if g not in haupt:
            continue
        if not _s(name).strip():
            f(f"Konto {g}: name fehlt oder ist leer.", g)
        if not _s(typ).strip():
            f(f"Konto {g}: account_type fehlt oder ist leer.", g)
        try:
            versteckt = hidden is not None and int(hidden) != 0
        except (TypeError, ValueError):
            versteckt = False
        e = _s(eltern) or None
        b.konten.append(_GKonto(g, _s(name), _s(typ).strip(), None if e == wurzel else e, eur(cg), _s(code),
                                _s(besch), versteckt))
    for g, cg, post, besch in transaktionen:
        g = _s(g)
        ref = g or None
        splits = splits_je.get(g, [])
        if not splits:
            if not g:
                f("Eine Transaktion hat keine GUID.", None)
            f(f"Transaktion {g}: keine Splits vorhanden.", ref)
            continue
        innen = aussen = 0
        sp: list[_GSplit] = []
        meldungen: list[str] = []
        for _tx, konto, memo, num, den in splits:
            konto = _s(konto)
            if not konto:
                meldungen.append(f"Transaktion {g}: Split ohne Konto.")
            elif konto not in typ_von:
                meldungen.append(f"Transaktion {g}: Split verweist auf unbekanntes Konto {konto}.")
            elif typ_von[konto] == "ROOT":
                meldungen.append(f"Transaktion {g}: Split bucht auf das Wurzelkonto {konto}.")
            elif konto in haupt:
                innen += 1
            else:
                aussen += 1
            cent = None
            if not isinstance(num, int) or not isinstance(den, int):
                meldungen.append(f"Transaktion {g}: Betrag fehlt oder ist keine Ganzzahl.")
            elif den <= 0:
                meldungen.append(f"Transaktion {g}: value_denom {den} ist nicht positiv.")
            else:
                cent = _cent("-" if num < 0 else "", abs(num), den)
                if cent is None:
                    meldungen.append(f"Transaktion {g}: Betrag {num}/{den} ist nicht in ganzen Cent darstellbar"
                                     " oder außerhalb des Betragsbereichs.")
            sp.append(_GSplit(konto, cent or 0, _s(memo)))
        if not meldungen and innen == 0 and aussen > 0:
            continue  # gehört nicht zum Buch (z. B. Vorlagenbaum geplanter Buchungen)
        if innen and aussen:
            meldungen.append(f"Transaktion {g}: bucht teils innerhalb, teils außerhalb des Kontenbaums.")
        if not g:
            meldungen.insert(0, "Eine Transaktion hat keine GUID.")
        datum = None
        if not _s(post).strip():
            meldungen.append(f"Transaktion {g}: Buchungsdatum fehlt.")
        else:
            datum = _datum(_s(post).strip())
            if datum is None:
                meldungen.append(f"Transaktion {g}: Buchungsdatum {_s(post)!r} ist ungültig.")
        for m in meldungen:
            f(m, ref)
        b.buchungen.append(_GBuchung(g, datum or "", _s(besch), notizen.get(g, ""), eur(cg), sp))
    return b, fehler


# ============================================================ 1. Erkennen


def lesen(roh: bytes) -> tuple[str, _Buch, list[ImportMeldung]]:
    """gnucash.md 2: liefert (format, Buch, Inhaltsfehler) oder wirft _Abbruch."""
    if len(roh) == 0:
        raise _Abbruch("import_datei_leer", "Die Datei ist leer.", None)
    if roh[:2] == b"\x1f\x8b":
        format_ = "gnc-xml-gzip"
        try:
            daten = gzip.decompress(roh)
        except (OSError, EOFError, zlib.error, ValueError) as e:
            raise _Abbruch("import_datei_beschaedigt",
                           f"Die gzip-Datei ist beschädigt oder unvollständig ({type(e).__name__}).", format_) from None
        if len(daten) == 0:
            raise _Abbruch("import_datei_leer", "Die gzip-Datei enthält keine Daten.", format_)
        rest = daten[3:] if daten.startswith(b"\xef\xbb\xbf") else daten
        if not rest.lstrip(b" \t\r\n").startswith(b"<"):
            raise _Abbruch("import_format_ungueltig",
                           "Der entpackte Inhalt ist kein XML; keine GnuCash-Datei.", None)
    elif roh[:16] == _SQLITE_KOPF:
        b, fehler = _aus_sqlite(roh)
        return "gnc-sqlite", b, fehler
    else:
        rest = roh[3:] if roh.startswith(b"\xef\xbb\xbf") else roh
        if not rest.lstrip(b" \t\r\n").startswith(b"<"):
            raise _Abbruch("import_format_ungueltig",
                           "Die Datei ist weder gzip-komprimiert noch SQLite noch XML; keine GnuCash-Datei.", None)
        format_ = "gnc-xml"
        daten = roh
    book = _xml_parsen(daten, format_)
    b, _wurzeln, fehler = _aus_xml(book)
    return format_, b, fehler


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


def _konten_anwenden(con, b: _Buch, lauf: _Lauf, max_konto: int) -> tuple[dict[str, int], set[str]]:
    art_von: dict[str, str] = {}
    uebersprungen: set[str] = set()
    for k in b.konten:
        abb = TYPABBILDUNG.get(k.typ)
        if abb is None:
            uebersprungen.add(k.guid)
            lauf.warn("konto_uebersprungen", k.guid)
            continue
        if not k.eur:
            uebersprungen.add(k.guid)
            lauf.warn("fremdwaehrung", k.guid)
            continue
        if abb[1]:
            lauf.warn("kontoart_ersetzt", k.guid)
        art_von[k.guid] = abb[0]

    eltern_von: dict[str, str | None] = {}
    for k in b.konten:
        if k.guid not in art_von:
            continue
        p = k.eltern
        if p is None or p not in art_von:  # Wurzel, übersprungen oder ROOT
            eltern_von[k.guid] = None
        elif KLASSE[art_von[p]] != KLASSE[art_von[k.guid]]:
            eltern_von[k.guid] = None
            lauf.warn("hierarchie_angepasst", k.guid)
        else:
            eltern_von[k.guid] = p

    reihenfolge: list[str] = []
    besucht: set[str] = set()

    def besuche(g: str, pfad: set[str]) -> None:
        if g in besucht:
            return
        p = eltern_von.get(g)
        if p is not None and p not in pfad:
            besuche(p, pfad | {g})
        elif p is not None:  # Zyklus in der Datei: Wurzelkonto
            eltern_von[g] = None
        if g not in besucht:
            besucht.add(g)
            reihenfolge.append(g)

    for k in b.konten:
        if k.guid in art_von:
            besuche(k.guid, set())

    nach_guid = {k.guid: k for k in b.konten}
    abbildung: dict[str, int] = {}
    vergeben: set[int] = set()  # in diesem Lauf zugeordnete vorhandene Konten
    for g in reihenfolge:
        k = nach_guid[g]
        art = art_von[g]
        klasse = KLASSE[art]
        zaehler = "konten" if klasse in ("bestand", "eigenkapital") else "kategorien"
        ext = PRAEFIX + g
        eltern_kontor = abbildung.get(eltern_von[g]) if eltern_von[g] else None
        iban = None
        if klasse == "bestand" and k.code:
            n = iban_normalisieren(k.code)
            if _IBAN_FORM.match(n):
                if iban_gueltig(n):
                    iban = n
                else:
                    lauf.warn("iban_ungueltig", g)
        treffer = None
        r = con.execute("SELECT id FROM konto WHERE extern_id = ? AND id <= ?", (ext, max_konto)).fetchone()
        if r is not None and r["id"] not in vergeben:
            treffer = r["id"]
        elif iban is not None:
            r = con.execute("SELECT id FROM konto WHERE iban = ? AND id <= ?"
                            " AND (extern_id IS NULL OR substr(extern_id, 1, 4) <> 'gnc:')",
                            (iban, max_konto)).fetchone()
            if r is not None and r["id"] not in vergeben:
                treffer = r["id"]
        else:
            for kandidat in con.execute(
                    "SELECT id FROM konto WHERE art = ? AND name = ? AND eltern_id IS ? AND iban IS NULL AND id <= ?"
                    " AND (extern_id IS NULL OR (substr(extern_id, 1, 4) <> 'gnc:'"
                    "      AND substr(extern_id, 1, 7) <> 'kontor:')) ORDER BY id",
                    (art, k.name, eltern_kontor, max_konto)):
                if kandidat["id"] not in vergeben:
                    treffer = kandidat["id"]
                    break
        if treffer is not None:
            con.execute("UPDATE konto SET extern_id = ? WHERE id = ? AND extern_id IS NULL", (ext, treffer))
            vergeben.add(treffer)
            abbildung[g] = treffer
            lauf.z[zaehler + "_vorhanden"] += 1
            continue
        if iban is not None and con.execute("SELECT 1 FROM konto WHERE iban = ?", (iban,)).fetchone():
            lauf.warn("iban_doppelt", g)
            iban = None
        cur = con.execute(
            "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
            " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
            (k.name, art, eltern_kontor, iban, 1 if k.versteckt else 0, k.beschreibung, ext))
        abbildung[g] = cur.lastrowid
        lauf.z[zaehler + "_neu"] += 1
    return abbildung, uebersprungen


@dataclass
class _Neu:
    gb: _GBuchung
    splits: list[dict]
    empfaenger_id: int | None
    empfaenger_name: str | None
    exakt: set[int] = field(default_factory=set)
    aehnlich: set[int] = field(default_factory=set)


def _max_id(con, tabelle: str) -> int:
    return con.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM {tabelle}").fetchone()["m"]


def _anwenden(con, b: _Buch, lauf: _Lauf, roh: bytes, dateiname: str | None, jetzt: str) -> int:
    max_konto = _max_id(con, "konto")
    max_buchung = _max_id(con, "buchung")
    konten, uebersprungen = _konten_anwenden(con, b, lauf, max_konto)

    def wird_uebersprungen(t: _GBuchung) -> bool:
        return not t.eur or any(s.konto in uebersprungen for s in t.splits)

    # 6.2 Empfänger: jeder verschiedene Name genau einmal (Dokumentreihenfolge).
    empf: dict[str, int] = {}
    for t in b.buchungen:
        name = t.beschreibung.strip()
        if not name or name in empf or wird_uebersprungen(t):
            continue
        eid = buch.empfaenger_zu_name(con, name)
        if eid is not None:
            lauf.z["empfaenger_vorhanden"] += 1
        else:
            eid = con.execute("INSERT INTO empfaenger (name, extern_id) VALUES (?, NULL)", (name,)).lastrowid
            lauf.z["empfaenger_neu"] += 1
        empf[name] = eid

    art_von = buch.kontoarten(con)
    neue: list[_Neu] = []
    for t in b.buchungen:
        if wird_uebersprungen(t):
            lauf.z["buchungen_uebersprungen"] += 1
            lauf.warn("buchung_uebersprungen", t.guid)
            continue
        if con.execute("SELECT 1 FROM buchung_extern WHERE extern_id = ?", (PRAEFIX + t.guid,)).fetchone():
            lauf.z["buchungen_vorhanden"] += 1
            continue
        name = t.beschreibung.strip() or None
        splits = [{"konto_id": konten[s.konto], "betrag": s.cent, "memo": s.memo} for s in t.splits]
        neue.append(_Neu(t, splits, empf.get(name) if name else None, name))

    # 8. Dublettenbewertung: erst alle bewerten, dann anwenden.
    for n in neue:
        b_datum = dt.date.fromisoformat(n.gb.datum)
        for s in n.splits:
            if art_von[s["konto_id"]] not in BESTAND:
                continue
            for c in con.execute(
                    "SELECT b.id AS id, b.datum AS datum, e.name AS name FROM split s"
                    " JOIN buchung b ON b.id = s.buchung_id LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                    " WHERE s.konto_id = ? AND s.betrag = ? AND b.id <= ?"
                    " AND NOT EXISTS (SELECT 1 FROM buchung_extern x WHERE x.buchung_id = b.id"
                    "                 AND substr(x.extern_id, 1, 4) = 'gnc:')",
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
    for n in neue:
        ext = PRAEFIX + n.gb.guid
        splits = list(n.splits)
        summe = sum(s["betrag"] for s in splits)
        if summe != 0 or len(splits) < 2:
            lauf.warn("buchung_ausgeglichen", n.gb.guid)
        if len(n.exakt) == 1 and exakt_zaehler[next(iter(n.exakt))] == 1:
            con.execute("INSERT INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)", (next(iter(n.exakt)), ext))
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
        bid = buchung_einfuegen(con, n.gb.datum, n.empfaenger_id, n.gb.notiz, "importiert", splits, (), [ext])
        lauf.z["buchungen_neu"] += 1
        lauf.z["splits_neu"] += len(splits)
        kandidaten = n.exakt | n.aehnlich
        if kandidaten:
            vid = con.execute(
                "INSERT INTO dublettenverdacht (buchung_id, grund, status, erstellt_am) VALUES (?, ?, 'offen', ?)",
                (bid, "mehrdeutig" if n.exakt else "aehnlich", jetzt)).lastrowid
            con.executemany("INSERT INTO verdacht_kandidat (verdacht_id, buchung_id) VALUES (?, ?)",
                            [(vid, c) for c in sorted(kandidaten)])
            lauf.z["buchungen_zur_pruefung"] += 1

    return con.execute(
        "INSERT INTO importvorgang (art, dateiname, sha256, importiert_am, ergebnis) VALUES (?, ?, ?, ?, '{}')",
        ("gnucash", dateiname, hashlib.sha256(roh).hexdigest(), jetzt)).lastrowid


def _fehlschlag(format_: str | None, fehler: list[ImportMeldung]) -> ImportErgebnis:
    return ImportErgebnis(erfolgreich=False, format=format_, fehler=tuple(fehler), import_id=None)


def importiere_bytes(con: sqlite3.Connection, roh: bytes, dateiname: str | None,
                     zeitpunkt: str | None = None) -> ImportErgebnis:
    """Kern des Imports auf einer offenen Verbindung (eine protokollierte Transaktion)."""
    try:
        format_, b, fehler = lesen(roh)
    except _Abbruch as a:
        return _fehlschlag(a.format, [ImportMeldung(a.code, a.meldung, None)])
    except (RecursionError, MemoryError):
        return _fehlschlag(None, [ImportMeldung("import_datei_beschaedigt", "Die Datei ist nicht lesbar.", None)])
    if fehler:
        return _fehlschlag(format_, fehler)
    lauf = _Lauf()
    jetzt = zeitpunkt or db.jetzt_utc()
    with protokoll.protokolliert(con, "import", "import_gnucash", jetzt) as k:
        import_id = _anwenden(con, b, lauf, roh, dateiname, jetzt)
        k.gruppe = f"import:{import_id}"
        ergebnis = ImportErgebnis(erfolgreich=True, format=format_, warnungen=tuple(lauf.warnungen),
                                  fehler=(), import_id=import_id, **lauf.z)
        con.execute("UPDATE importvorgang SET ergebnis = ? WHERE id = ?",
                    (json.dumps(ergebnis.als_dict(), ensure_ascii=False), import_id))
    return ergebnis


def importiere_gnucash(config, quelle: str | os.PathLike[str] | bytes, *,
                       dateiname: str | None = None) -> ImportErgebnis:
    """Importiert eine GnuCash-Datei in ``config.aktive_datenbank`` (python-api.md 10.2)."""
    if isinstance(quelle, (bytes, bytearray, memoryview)):
        roh = bytes(quelle)
    elif isinstance(quelle, (str, os.PathLike)):
        pfad = pathlib.Path(quelle)
        roh = pfad.read_bytes()  # FileNotFoundError, wenn der Pfad nicht existiert; nur lesend
        if dateiname is None:
            dateiname = pfad.name
    else:
        raise TypeError("quelle muss ein Pfad oder bytes sein, nicht " + type(quelle).__name__)
    db.schema_anlegen(config.aktive_datenbank)
    con = db.verbinde(config.aktive_datenbank)
    zeitpunkt = None
    if config.mock_modus and config.mock_heute is not None:
        zeitpunkt = config.mock_heute.isoformat() + "T12:00:00Z"
    try:
        return importiere_bytes(con, roh, dateiname, zeitpunkt)
    finally:
        con.close()
