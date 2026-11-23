"""Modell, Schreiber (XML, SQLite) und Erwartungsberechnung für GnuCash-Dateien.

Das Modell bildet genau die Teile des GnuCash-Formats ab, die Kontor nach
``spec/api/gnucash.md`` importiert. Die Erwartungen (bekannte Wahrheit) werden
aus dem Modell nach diesen Regeln berechnet – nicht durch Lesen der erzeugten
Datei. Alle Daten sind synthetisch; GUIDs werden deterministisch aus Namen
abgeleitet.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .iban import ist_gueltig, normalisiere
from .kmy import FEHLT, KBuch, KLASSE, TYPABBILDUNG, UNAUSGEGLICHEN

NS = {
    "gnc": "http://www.gnucash.org/XML/gnc",
    "act": "http://www.gnucash.org/XML/act",
    "book": "http://www.gnucash.org/XML/book",
    "cd": "http://www.gnucash.org/XML/cd",
    "cmdty": "http://www.gnucash.org/XML/cmdty",
    "slot": "http://www.gnucash.org/XML/slot",
    "split": "http://www.gnucash.org/XML/split",
    "trn": "http://www.gnucash.org/XML/trn",
    "ts": "http://www.gnucash.org/XML/ts",
}

# GnuCash-Typ -> (Kontor-Art, Warnung); fehlt = übersprungen (gnucash.md 6.1)
GNC_TYP: dict[str, tuple[str, str | None]] = {
    "BANK": ("girokonto", None),
    "CASH": ("girokonto", "kontoart_ersetzt"),
    "ASSET": ("sparkonto", "kontoart_ersetzt"),
    "RECEIVABLE": ("sparkonto", "kontoart_ersetzt"),
    "CREDIT": ("kreditkonto", None),
    "LIABILITY": ("kreditkonto", None),
    "PAYABLE": ("kreditkonto", "kontoart_ersetzt"),
    "INCOME": ("ertrag", None),
    "EXPENSE": ("aufwand", None),
    "EQUITY": ("eigenkapital", None),
}
# KMyMoney-Typ -> GnuCash-Typ (für die Umwandlung der Generatorbücher)
AUS_KMY = {1: "BANK", 2: "BANK", 6: "BANK", 8: "BANK", 3: "CASH", 9: "ASSET", 14: "ASSET", 4: "CREDIT",
           5: "LIABILITY", 10: "LIABILITY", 12: "INCOME", 13: "EXPENSE", 16: "EQUITY", 7: "STOCK", 15: "STOCK",
           0: "STOCK", 11: "CURRENCY"}
_IBAN_FORM = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def guid(text: str) -> str:
    """Deterministische GUID (32 Hex-Zeichen, Kleinbuchstaben)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


@dataclass
class GKonto:
    guid: str
    name: object  # str oder FEHLT
    typ: str
    eltern: str | None  # GUID des Elternkontos (auch ROOT); None = keine Elternangabe
    waehrung: str = "EUR"  # ISO-Code; "" = act:commodity fehlt
    code: str = ""
    beschreibung: object = ""  # str oder FEHLT
    versteckt: bool = False
    platzhalter: bool = False


@dataclass
class GSplit:
    konto: str
    wert: int | None
    memo: object = ""
    wert_text: str | None = None  # überschreibt XML-Darstellung (z. B. "617/50")
    sql_wert: tuple[int, int] | None = None  # überschreibt (value_num, value_denom)
    guid: str = ""


@dataclass
class GBuchung:
    guid: str
    datum: str  # Datumstext wie in der Datei
    splits: list[GSplit]
    beschreibung: object = ""  # str oder FEHLT
    notiz: object = FEHLT  # str oder FEHLT (Slot notes)
    waehrung: str = "EUR"
    wahre_kategorie: str | None = None  # GUID
    umbuchung: bool = False
    quelle: str | None = None  # ID der Ursprungsbuchung (KMyMoney-Transaktion), nur Generator
    sql_datum: str | None = None  # abweichender Datumstext in SQLite


@dataclass
class GBuch:
    buch_guid: str
    root_guid: str
    konten: list[GKonto] = field(default_factory=list)  # ohne ROOT
    buchungen: list[GBuchung] = field(default_factory=list)
    vorlagen: bool = False  # Vorlagenbaum mit einer geplanten Buchung (wird ignoriert)

    def konto(self, g: str) -> GKonto:
        return next(k for k in self.konten if k.guid == g)


def datum_text(d: str) -> str:
    return f"{d[:10]} 10:59:00 +0000"


def aus_kbuch(kb: KBuch, praefix: str, *, buchungen=None) -> tuple[GBuch, dict[str, str]]:
    """Wandelt ein Generator-KMyMoney-Buch in ein GnuCash-Buch um.

    Liefert das Buch und die Abbildung KMyMoney-Konto-ID → GUID. Empfänger
    werden zur Beschreibung, das Memo der Transaktion zur Notiz.
    """
    gb = GBuch(buch_guid=guid(praefix + ":buch"), root_guid=guid(praefix + ":root"))
    abb = {k.id: guid(f"{praefix}:konto:{k.id}") for k in kb.konten}
    for k in kb.konten:
        eltern = gb.root_guid if k.eltern.startswith("AStd::") else abb[k.eltern]
        gb.konten.append(GKonto(abb[k.id], k.name, AUS_KMY[k.typ], eltern,
                                waehrung="EUR" if k.waehrung is FEHLT else k.waehrung,
                                code=k.iban or k.nummer or "", beschreibung=k.beschreibung,
                                versteckt=k.geschlossen))
    namen = dict(kb.empfaenger)
    for b in (kb.buchungen if buchungen is None else buchungen):
        empf = ""
        for s in b.splits:
            if s.empfaenger is not FEHLT and s.empfaenger != "":
                empf = namen[s.empfaenger]
                break
        splits = [GSplit(abb[s.konto], s.wert, memo=s.memo, guid=guid(f"{praefix}:split:{b.id}:{n}"))
                  for n, s in enumerate(b.splits)]
        gb.buchungen.append(GBuchung(guid(f"{praefix}:trn:{b.id}"), datum_text(b.datum), splits, beschreibung=empf,
                                     notiz=b.memo, waehrung="EUR" if b.waehrung is FEHLT else b.waehrung,
                                     wahre_kategorie=abb[b.wahre_kategorie] if b.wahre_kategorie else None,
                                     umbuchung=b.umbuchung, quelle=b.id))
    return gb, abb


# ------------------------------------------------------------------ XML

def _el(eltern: ET.Element, tag: str, text: str | None = None, **attr) -> ET.Element:
    p, n = tag.split(":")
    e = ET.SubElement(eltern, f"{{{NS[p]}}}{n}")
    for k, v in attr.items():
        if ":" in k:
            ap, an = k.split(":")
            e.set(f"{{{NS[ap]}}}{an}", v)
        else:
            e.set(k, v)
    if text is not None:
        e.text = text
    return e


def _waehrung(eltern: ET.Element, tag: str, code: str) -> None:
    c = _el(eltern, tag)
    _el(c, "cmdty:space", "CURRENCY" if code == "EUR" else "ISO4217")
    _el(c, "cmdty:id", code)


def _slots(eltern: ET.Element, tag: str, paare: list[tuple[str, str]]) -> None:
    if not paare:
        return
    s = _el(eltern, tag)
    for k, v in paare:
        sl = ET.SubElement(s, "slot")
        _el(sl, "slot:key", k)
        _el(sl, "slot:value", v, type="string")


def _wert_xml(s: GSplit) -> str:
    if s.wert_text is not None:
        return s.wert_text
    return f"{s.wert}/100"


def als_gnc_xml(gb: GBuch, *, buecher: int = 1) -> bytes:
    for p, uri in NS.items():
        ET.register_namespace(p, uri)
    wurzel = ET.Element("gnc-v2")
    _el(wurzel, "gnc:count-data", str(buecher), **{"cd:type": "book"})
    for nr in range(buecher):
        buch = _el(wurzel, "gnc:book", version="2.0.0")
        _el(buch, "book:id", gb.buch_guid if nr == 0 else guid(gb.buch_guid + str(nr)), type="guid")
        _el(buch, "gnc:count-data", "1", **{"cd:type": "commodity"})
        _el(buch, "gnc:count-data", str(len(gb.konten) + 1), **{"cd:type": "account"})
        _el(buch, "gnc:count-data", str(len(gb.buchungen)), **{"cd:type": "transaction"})
        c = _el(buch, "gnc:commodity", version="2.0.0")
        _el(c, "cmdty:space", "CURRENCY")
        _el(c, "cmdty:id", "EUR")
        r = _el(buch, "gnc:account", version="2.0.0")
        _el(r, "act:name", "Root Account")
        _el(r, "act:id", gb.root_guid, type="guid")
        _el(r, "act:type", "ROOT")
        for k in gb.konten:
            a = _el(buch, "gnc:account", version="2.0.0")
            if k.name is not FEHLT:
                _el(a, "act:name", k.name)
            _el(a, "act:id", k.guid, type="guid")
            _el(a, "act:type", k.typ)
            if k.waehrung:
                _waehrung(a, "act:commodity", k.waehrung)
                _el(a, "act:commodity-scu", "100")
            if k.code:
                _el(a, "act:code", k.code)
            if k.beschreibung is not FEHLT and k.beschreibung != "":
                _el(a, "act:description", k.beschreibung)
            paare = []
            if k.versteckt:
                paare.append(("hidden", "true"))
            if k.platzhalter:
                paare.append(("placeholder", "true"))
            _slots(a, "act:slots", paare)
            if k.eltern is not None:
                _el(a, "act:parent", k.eltern, type="guid")
        for b in gb.buchungen:
            t = _el(buch, "gnc:transaction", version="2.0.0")
            _el(t, "trn:id", b.guid, type="guid")
            _waehrung(t, "trn:currency", b.waehrung)
            _el(t, "trn:num", "")
            dp = _el(t, "trn:date-posted")
            _el(dp, "ts:date", b.datum)
            de = _el(t, "trn:date-entered")
            _el(de, "ts:date", "2025-01-05 08:00:00 +0000")
            if b.beschreibung is not FEHLT:
                _el(t, "trn:description", b.beschreibung)
            if b.notiz is not FEHLT:
                _slots(t, "trn:slots", [("notes", b.notiz)])
            ss = _el(t, "trn:splits")
            for s in b.splits:
                e = _el(ss, "trn:split")
                _el(e, "split:id", s.guid or guid(b.guid + s.konto), type="guid")
                if s.memo is not FEHLT and s.memo != "":
                    _el(e, "split:memo", s.memo)
                _el(e, "split:reconciled-state", "n")
                if s.wert is not None or s.wert_text is not None:
                    _el(e, "split:value", _wert_xml(s))
                    _el(e, "split:quantity", _wert_xml(s))
                if s.konto:
                    _el(e, "split:account", s.konto, type="guid")
        if gb.vorlagen:
            tt = _el(buch, "gnc:template-transactions")
            vr = _el(tt, "gnc:account", version="2.0.0")
            _el(vr, "act:name", "Template Root")
            _el(vr, "act:id", guid(gb.buch_guid + ":vorlagenwurzel"), type="guid")
            _el(vr, "act:type", "ROOT")
            va = _el(tt, "gnc:account", version="2.0.0")
            _el(va, "act:name", guid(gb.buch_guid + ":vorlage"))
            _el(va, "act:id", guid(gb.buch_guid + ":vorlagekonto"), type="guid")
            _el(va, "act:type", "BANK")
            _el(va, "act:parent", guid(gb.buch_guid + ":vorlagenwurzel"), type="guid")
    ET.indent(wurzel, space=" ")
    text = '<?xml version="1.0" encoding="utf-8" ?>\n' + ET.tostring(wurzel, encoding="unicode") + "\n"
    return text.encode("utf-8")


# --------------------------------------------------------------- SQLite

SCHEMA = """
CREATE TABLE gnclock (Hostname varchar(255), PID int);
CREATE TABLE versions(table_name text(50) PRIMARY KEY NOT NULL, table_version integer NOT NULL);
CREATE TABLE books(guid text(32) PRIMARY KEY NOT NULL, root_account_guid text(32) NOT NULL,
  root_template_guid text(32) NOT NULL);
CREATE TABLE commodities(guid text(32) PRIMARY KEY NOT NULL, namespace text(2048) NOT NULL,
  mnemonic text(2048) NOT NULL, fullname text(2048), cusip text(2048), fraction integer NOT NULL,
  quote_flag integer NOT NULL, quote_source text(2048), quote_tz text(2048));
CREATE TABLE accounts(guid text(32) PRIMARY KEY NOT NULL, name text(2048) NOT NULL,
  account_type text(2048) NOT NULL, commodity_guid text(32), commodity_scu integer NOT NULL,
  non_std_scu integer NOT NULL, parent_guid text(32), code text(2048), description text(2048),
  hidden integer, placeholder integer);
CREATE TABLE transactions(guid text(32) PRIMARY KEY NOT NULL, currency_guid text(32) NOT NULL,
  num text(2048) NOT NULL, post_date text(19), enter_date text(19), description text(2048));
CREATE TABLE splits(guid text(32) PRIMARY KEY NOT NULL, tx_guid text(32) NOT NULL,
  account_guid text(32) NOT NULL, memo text(2048) NOT NULL, action text(2048) NOT NULL,
  reconcile_state text(1) NOT NULL, reconcile_date text(19), value_num bigint NOT NULL,
  value_denom bigint NOT NULL, quantity_num bigint NOT NULL, quantity_denom bigint NOT NULL,
  lot_guid text(32));
CREATE TABLE slots(id integer PRIMARY KEY AUTOINCREMENT NOT NULL, obj_guid text(32) NOT NULL,
  name text(4096) NOT NULL, slot_type integer NOT NULL, int64_val bigint, string_val text(4096),
  double_val float8, timespec_val text(19), guid_val text(32), numeric_val_num bigint,
  numeric_val_denom bigint, gdate_val text(8));
"""


def _sql_datum(b: GBuchung) -> str:
    if b.sql_datum is not None:
        return b.sql_datum
    return b.datum[:19]


def _sql_wert(s: GSplit) -> tuple[int, int]:
    if s.sql_wert is not None:
        return s.sql_wert
    if s.wert_text is not None:
        z, _, n = s.wert_text.partition("/")
        return int(z), int(n or 1)
    return s.wert, 100


def _fertig(con: sqlite3.Connection) -> bytes:
    con.commit()
    daten = bytearray(con.serialize())
    con.close()
    # Kopffelder 92–99 (version-valid-for, SQLITE_VERSION_NUMBER) fest setzen: reproduzierbar
    daten[92:100] = (1).to_bytes(4, "big") + (3000000).to_bytes(4, "big")
    daten[24:28] = (1).to_bytes(4, "big")
    return bytes(daten)


def als_gnc_sqlite(gb: GBuch, *, buecher: int = 1) -> bytes:
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA page_size = 4096")
    con.executescript(SCHEMA)
    vorlagenwurzel = guid(gb.buch_guid + ":vorlagenwurzel")
    for nr in range(buecher):
        con.execute("INSERT INTO books VALUES (?,?,?)",
                    (gb.buch_guid if nr == 0 else guid(gb.buch_guid + str(nr)), gb.root_guid, vorlagenwurzel))
    waehrungen = sorted({k.waehrung for k in gb.konten if k.waehrung} | {b.waehrung for b in gb.buchungen} | {"EUR"})
    cg = {w: guid(gb.buch_guid + ":cmdty:" + w) for w in waehrungen}
    for w in waehrungen:
        con.execute("INSERT INTO commodities VALUES (?,?,?,?,?,?,?,?,?)",
                    (cg[w], "CURRENCY", w, w, "", 100, 0, None, None))
    con.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (gb.root_guid, "Root Account", "ROOT", cg["EUR"], 100, 0, None, "", "", 0, 0))
    for k in gb.konten:
        con.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (k.guid, "" if k.name is FEHLT else k.name, k.typ, cg.get(k.waehrung) if k.waehrung else None,
                     100, 0, k.eltern, k.code, "" if k.beschreibung is FEHLT else k.beschreibung,
                     int(k.versteckt), int(k.platzhalter)))
    if gb.vorlagen:
        con.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (vorlagenwurzel, "Template Root", "ROOT", None, 0, 0, None, "", "", 0, 0))
        vk = guid(gb.buch_guid + ":vorlagekonto")
        con.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (vk, guid(gb.buch_guid + ":vorlage"), "BANK", cg["EUR"], 100, 0, vorlagenwurzel, "", "", 0, 0))
        vt = guid(gb.buch_guid + ":vorlagebuchung")
        con.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?)",
                    (vt, cg["EUR"], "", "2024-01-01 10:59:00", "2024-01-01 10:59:00", "Geplante Buchung (Vorlage)"))
        con.execute("INSERT INTO splits VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (guid(vt + ":1"), vt, vk, "", "", "n", None, 0, 1, 0, 1, None))
    for b in gb.buchungen:
        con.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?)",
                    (b.guid, cg[b.waehrung], "", _sql_datum(b), "2025-01-05 08:00:00",
                     "" if b.beschreibung is FEHLT else b.beschreibung))
        if b.notiz is not FEHLT:
            con.execute("INSERT INTO slots (obj_guid, name, slot_type, string_val) VALUES (?,?,?,?)",
                        (b.guid, "notes", 4, b.notiz))
        for s in b.splits:
            num, den = _sql_wert(s)
            con.execute("INSERT INTO splits VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (s.guid or guid(b.guid + s.konto), b.guid, s.konto, "" if s.memo is FEHLT else s.memo, "",
                         "n", None, num, den, num, den, None))
    return _fertig(con)


def sqlite_fingerabdruck(daten: bytes) -> str | None:
    """SHA-256 über den logischen Inhalt (SQL-Abzug) einer SQLite-Datei; None, wenn unlesbar.

    Damit lassen sich SQLite-Fixtures auch mit einer anderen SQLite-Version auf
    gleichen Inhalt prüfen (die Seitenaufteilung darf sich unterscheiden).
    """
    try:
        con = sqlite3.connect(":memory:")
        con.deserialize(daten)
        text = "\n".join(con.iterdump())
        con.close()
    except sqlite3.DatabaseError:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sqlite_aus_sql(sql: str) -> bytes:
    """Kleine SQLite-Datei aus beliebigem SQL (für Störfälle)."""
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA page_size = 4096")
    con.executescript(sql)
    return _fertig(con)


# ------------------------------------------------------ Erwartung berechnen

def _art(k: GKonto) -> tuple[str | None, str | None]:
    abb = GNC_TYP.get(k.typ)
    if abb is None:
        return None, "konto_uebersprungen"
    if (k.waehrung or "EUR") != "EUR":
        return None, "fremdwaehrung"
    return abb


def gnc_erwartung(gb: GBuch, *, fixture: str, format_: str) -> dict:
    """Bekannte Wahrheit für den Import in ein leeres Buch (gnucash.md 6, 9)."""
    warnungen: list[dict] = []

    def warn(code: str, ref: str | None) -> None:
        warnungen.append({"code": code, "referenz": ref})

    art_von: dict[str, str] = {}
    ueber: set[str] = set()
    for k in gb.konten:
        art, w = _art(k)
        if art is None:
            ueber.add(k.guid)
            warn(w, k.guid)
            continue
        if w:
            warn(w, k.guid)
        art_von[k.guid] = art
    konten: list[dict] = []
    vergeben: set[str] = set()
    konten_neu = kat_neu = 0
    for k in gb.konten:
        if k.guid in ueber:
            continue
        art = art_von[k.guid]
        eltern = None
        if k.eltern is not None and k.eltern != gb.root_guid and k.eltern not in ueber:
            if KLASSE[art_von[k.eltern]] != KLASSE[art]:
                warn("hierarchie_angepasst", k.guid)
            else:
                eltern = "gnc:" + k.eltern
        iban = None
        if KLASSE[art] == "bestand" and k.code:
            n = normalisiere(k.code)
            if _IBAN_FORM.match(n):
                if not ist_gueltig(n):
                    warn("iban_ungueltig", k.guid)
                elif n in vergeben:
                    warn("iban_doppelt", k.guid)
                else:
                    iban = n
                    vergeben.add(n)
        if art in ("aufwand", "ertrag"):
            kat_neu += 1
        else:
            konten_neu += 1
        konten.append({"extern_id": "gnc:" + k.guid, "name": k.name, "art": art, "eltern_extern_id": eltern,
                       "geschlossen": k.versteckt, "iban": iban, "eroeffnet_am": None,
                       "notiz": "" if k.beschreibung is FEHLT else k.beschreibung,
                       "ist_kategorie": art in ("aufwand", "ertrag")})
    art_ext = {"gnc:" + g: a for g, a in art_von.items()}

    def uebersprungen(b: GBuchung) -> bool:
        return b.waehrung != "EUR" or any(s.konto in ueber for s in b.splits)

    namen: list[str] = []
    for b in gb.buchungen:
        if uebersprungen(b):
            continue
        n = "" if b.beschreibung is FEHLT else b.beschreibung.strip()
        if n and n not in namen:
            namen.append(n)

    buchungen: list[dict] = []
    b_neu = b_ueber = splits_neu = 0
    ausgleich = False
    for b in gb.buchungen:
        if uebersprungen(b):
            b_ueber += 1
            warn("buchung_uebersprungen", b.guid)
            continue
        splits = [{"konto_extern_id": "gnc:" + s.konto, "betrag": s.wert, "memo": "" if s.memo is FEHLT else s.memo}
                  for s in b.splits]
        summe = sum(s["betrag"] for s in splits)
        if summe != 0 or len(splits) < 2:
            splits.append({"konto_extern_id": UNAUSGEGLICHEN, "betrag": -summe, "memo": ""})
            warn("buchung_ausgeglichen", b.guid)
            ausgleich = True
            art_ext[UNAUSGEGLICHEN] = "eigenkapital"
        gegen = [s for s in splits if KLASSE[art_ext[s["konto_extern_id"]]] != "bestand"]
        kategorie = None
        if len(gegen) == 1 and art_ext[gegen[0]["konto_extern_id"]] in ("aufwand", "ertrag"):
            kategorie = gegen[0]["konto_extern_id"]
        n = "" if b.beschreibung is FEHLT else b.beschreibung.strip()
        b_neu += 1
        splits_neu += len(splits)
        buchungen.append({
            "extern_id": "gnc:" + b.guid, "datum": _datum(b.datum), "empfaenger": n or None,
            "verwendungszweck": "" if b.notiz is FEHLT else b.notiz, "status": "importiert", "tags": [],
            "splits": splits, "kategorie_extern_id": kategorie,
            "umsatz": sum(s["betrag"] for s in splits if s["betrag"] > 0),
            "wahre_kategorie_extern_id": ("gnc:" + b.wahre_kategorie) if b.wahre_kategorie else None,
            "umbuchung": b.umbuchung, "quelle": b.quelle,
        })
    if ausgleich:
        konten.append({"extern_id": UNAUSGEGLICHEN, "name": "Unausgeglichen", "art": "eigenkapital",
                       "eltern_extern_id": None, "geschlossen": False, "iban": None, "eroeffnet_am": None,
                       "notiz": "", "ist_kategorie": False})
    saldo = {k["extern_id"]: 0 for k in konten}
    anzahl = {k["extern_id"]: 0 for k in konten}
    for b in buchungen:
        for s in b["splits"]:
            saldo[s["konto_extern_id"]] += s["betrag"]
        for e in {s["konto_extern_id"] for s in b["splits"]}:
            anzahl[e] += 1
    kinder: dict[str | None, list[str]] = {}
    for k in konten:
        kinder.setdefault(k["eltern_extern_id"], []).append(k["extern_id"])

    def gesamt(e: str) -> int:
        return saldo[e] + sum(gesamt(c) for c in kinder.get(e, []))

    for k in konten:
        k["saldo"], k["saldo_gesamt"], k["anzahl_buchungen"] = saldo[k["extern_id"]], gesamt(k["extern_id"]), \
            anzahl[k["extern_id"]]
    ergebnis = {"erfolgreich": True, "format": format_, "konten_neu": konten_neu, "konten_vorhanden": 0,
                "kategorien_neu": kat_neu, "kategorien_vorhanden": 0, "empfaenger_neu": len(namen),
                "empfaenger_vorhanden": 0, "tags_neu": 0, "tags_vorhanden": 0, "buchungen_neu": b_neu,
                "buchungen_vorhanden": 0, "buchungen_zusammengefuehrt": 0, "buchungen_zur_pruefung": 0,
                "buchungen_uebersprungen": b_ueber, "splits_neu": splits_neu}
    return {
        "fixture": fixture, "art": "gnucash", "erfolgreich": True, "fehler_code": None, "ergebnis": ergebnis,
        "warnungen": warnungen, "konten": konten,
        "empfaenger": [{"extern_id": None, "name": n} for n in namen], "tags": [], "buchungen": buchungen,
        "summen": {"anzahl_transaktionen_in_datei": len(gb.buchungen), "anzahl_buchungen": len(buchungen),
                   "anzahl_splits": splits_neu,
                   "summe_bestand": sum(k["saldo"] for k in konten if KLASSE[k["art"]] == "bestand"),
                   "summe_gesamt": sum(k["saldo"] for k in konten)},
        "umbuchungen": [b["extern_id"] for b in buchungen if b["umbuchung"]],
    }


def _datum(text: str) -> str:
    if re.fullmatch(r"[0-9]{14}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    d = text[:10]
    dt.date.fromisoformat(d)
    return d


def fehler_erwartung(fixture: str, code: str, format_: str | None, beschreibung: str) -> dict:
    return {"fixture": fixture, "art": "gnucash", "erfolgreich": False, "fehler_code": code, "format": format_,
            "beschreibung": beschreibung}


__all__ = ["GBuch", "GBuchung", "GKonto", "GSplit", "TYPABBILDUNG", "aus_kbuch", "als_gnc_sqlite", "als_gnc_xml",
           "datum_text", "fehler_erwartung", "gnc_erwartung", "guid", "sqlite_aus_sql"]
