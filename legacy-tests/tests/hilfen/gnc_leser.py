"""Unabhängiger Leser für GnuCash-Testdateien (nur für Generatortests, kein Import nach Kontor).

Liest XML (gzip/unkomprimiert) und SQLite in eine neutrale Form, damit die
Generatortests prüfen können, dass Datei und bekannte Wahrheit
übereinstimmen. Die Abbildung nach Kontor (gnucash.md 6) steckt bewusst
nicht hier, sondern nur im Vergleich der Tests.
"""

from __future__ import annotations

import gzip
import sqlite3
import xml.etree.ElementTree as ET
from fractions import Fraction

N = {p: f"{{http://www.gnucash.org/XML/{p}}}" for p in ("gnc", "act", "book", "cmdty", "slot", "split", "trn", "ts")}


def _t(el, pfad: str) -> str | None:
    teile = pfad.split("/")
    for t in teile:
        if el is None:
            return None
        p, n = t.split(":")
        el = el.find(N[p] + n)
    return None if el is None else (el.text or "")


def _slots(el) -> dict[str, str]:
    aus = {}
    if el is None:
        return aus
    for s in el.findall("slot"):
        aus[_t(s, "slot:key")] = _t(s, "slot:value")
    return aus


def lies(daten: bytes) -> dict:
    """{"format", "root", "konten": [...], "buchungen": [...]} in Dokument- bzw. rowid-Reihenfolge."""
    if daten[:2] == b"\x1f\x8b":
        return _xml(gzip.decompress(daten), "gnc-xml-gzip")
    if daten[:16] == b"SQLite format 3\x00":
        return _sqlite(daten)
    return _xml(daten, "gnc-xml")


def _xml(daten: bytes, fmt: str) -> dict:
    w = ET.fromstring(daten)
    assert w.tag == "gnc-v2"
    buecher = w.findall(N["gnc"] + "book")
    assert len(buecher) == 1
    b = buecher[0]
    konten, buchungen, root = [], [], None
    for a in b.findall(N["gnc"] + "account"):
        k = {"guid": _t(a, "act:id"), "name": _t(a, "act:name"), "typ": _t(a, "act:type"),
             "eltern": _t(a, "act:parent"), "code": _t(a, "act:code") or "",
             "beschreibung": _t(a, "act:description") or "",
             "waehrung": _t(a, "act:commodity/cmdty:id") or "EUR",
             "versteckt": (_slots(a.find(N["act"] + "slots")).get("hidden") or "").lower() == "true"}
        if k["typ"] == "ROOT":
            root = k["guid"]
        else:
            konten.append(k)
    for t in b.findall(N["gnc"] + "transaction"):
        splits = []
        for s in t.findall(f"{N['trn']}splits/{N['trn']}split"):
            z, _, n = (_t(s, "split:value") or "").partition("/")
            splits.append({"konto": _t(s, "split:account"), "wert": Fraction(int(z), int(n or 1)),
                           "memo": _t(s, "split:memo") or ""})
        buchungen.append({"guid": _t(t, "trn:id"), "datum": _t(t, "trn:date-posted/ts:date"),
                          "beschreibung": _t(t, "trn:description"),
                          "notiz": _slots(t.find(N["trn"] + "slots")).get("notes"),
                          "waehrung": _t(t, "trn:currency/cmdty:id") or "EUR", "splits": splits})
    return {"format": fmt, "root": root, "konten": konten, "buchungen": buchungen}


def _sqlite(daten: bytes) -> dict:
    con = sqlite3.connect(":memory:")
    con.deserialize(daten)
    (root,), = con.execute("SELECT root_account_guid FROM books").fetchall()
    cmd = dict(con.execute("SELECT guid, mnemonic FROM commodities"))
    alle = {r[0]: r for r in con.execute(
        "SELECT guid, name, account_type, commodity_guid, parent_guid, code, description, hidden FROM accounts "
        "ORDER BY rowid")}

    def im_baum(g):
        while g is not None:
            if g == root:
                return True
            g = alle[g][4] if g in alle else None
        return False

    konten = [{"guid": g, "name": r[1], "typ": r[2], "eltern": r[4], "code": r[5] or "", "beschreibung": r[6] or "",
               "waehrung": cmd.get(r[3], "EUR"), "versteckt": bool(r[7])}
              for g, r in alle.items() if g != root and im_baum(r[4])]
    baum = {k["guid"] for k in konten}
    notizen = dict(con.execute("SELECT obj_guid, string_val FROM slots WHERE name = 'notes'"))
    buchungen = []
    for g, cur, datum, besch in con.execute(
            "SELECT guid, currency_guid, post_date, description FROM transactions ORDER BY rowid").fetchall():
        splits = [{"konto": a, "wert": Fraction(num, den), "memo": m or ""} for a, m, num, den in con.execute(
            "SELECT account_guid, memo, value_num, value_denom FROM splits WHERE tx_guid = ? ORDER BY rowid", (g,))]
        if splits and not any(s["konto"] in baum for s in splits):
            continue  # Vorlagenbaum
        buchungen.append({"guid": g, "datum": datum, "beschreibung": besch, "notiz": notizen.get(g),
                          "waehrung": cmd.get(cur, "EUR"), "splits": splits})
    return {"format": "gnc-sqlite", "root": root, "konten": konten, "buchungen": buchungen}
