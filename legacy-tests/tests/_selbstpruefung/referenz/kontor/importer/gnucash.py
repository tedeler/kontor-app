"""GnuCash-Import der Wegwerf-Referenz (spec/api/gnucash.md). KEIN Anwendungscode."""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
import zlib
from fractions import Fraction
from pathlib import Path
from xml.parsers import expat

from .. import mutant
from ..buch import KLASSE, MAX, Buch, buch_fuer, iban_gueltig, passend
from .ergebnis import ZAEHLER, ImportErgebnis, ImportMeldung
from .kmymoney import cent

__all__ = ["importiere_gnucash", "importiere_gnc_bytes", "ImportErgebnis", "ImportMeldung"]

N = {p: f"{{http://www.gnucash.org/XML/{p}}}" for p in ("gnc", "act", "book", "cmdty", "slot", "split", "trn", "ts")}
TYPEN = {"BANK": ("girokonto", None), "CASH": ("girokonto", "kontoart_ersetzt"),
         "ASSET": ("sparkonto", "kontoart_ersetzt"), "RECEIVABLE": ("sparkonto", "kontoart_ersetzt"),
         "CREDIT": ("kreditkonto", None), "LIABILITY": ("kreditkonto", None),
         "PAYABLE": ("kreditkonto", "kontoart_ersetzt"), "INCOME": ("ertrag", None), "EXPENSE": ("aufwand", None),
         "EQUITY": ("eigenkapital", None)}
IBAN_FORM = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


class _Fehler(Exception):
    def __init__(self, code: str, fmt: str | None, meldungen=None) -> None:
        super().__init__(code)
        self.code, self.fmt, self.meldungen = code, fmt, meldungen


def _datum(text: str | None) -> str | None:
    if not text:
        return None
    if re.fullmatch(r"[0-9]{14}", text):
        d = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    elif re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        d = text[:10]
    else:
        return None
    try:
        dt.date.fromisoformat(d)
    except ValueError:
        return None
    return d


def _eur(space: str | None, code: str | None) -> bool:
    if code is None:
        return True
    return space in ("ISO4217", "CURRENCY") and code == "EUR"


# ------------------------------------------------------------- Lesen
def _t(el, pfad):
    for teil in pfad.split("/"):
        if el is None:
            return None
        p, n = teil.split(":")
        el = el.find(N[p] + n)
    return None if el is None else (el.text or "")


def _slots(el) -> dict:
    if el is None:
        return {}
    return {_t(s, "slot:key"): _t(s, "slot:value") or "" for s in el.findall("slot")}


def _lies_xml(xml: bytes, fmt: str) -> dict:
    intern = []
    p = expat.ParserCreate()
    p.StartDoctypeDeclHandler = lambda name, sysid, pubid, hat_intern: intern.append(bool(hat_intern))
    try:
        p.Parse(xml, True)
    except expat.ExpatError:
        raise _Fehler("import_datei_beschaedigt", fmt) from None
    if any(intern):
        raise _Fehler("import_format_ungueltig", fmt)
    w = ET.fromstring(xml)
    buecher = w.findall(N["gnc"] + "book")
    if w.tag != "gnc-v2" or len(buecher) != 1:
        raise _Fehler("import_format_ungueltig", fmt)
    b = buecher[0]
    konten, buchungen = [], []
    for a in b.findall(N["gnc"] + "account"):
        cm = a.find(N["act"] + "commodity")
        konten.append({"guid": _t(a, "act:id"), "name": _t(a, "act:name"), "typ": _t(a, "act:type"),
                       "eltern": _t(a, "act:parent"), "code": _t(a, "act:code") or "",
                       "beschreibung": _t(a, "act:description") or "",
                       "eur": cm is None or _eur(_t(cm, "cmdty:space"), _t(cm, "cmdty:id")),
                       "versteckt": (_slots(a.find(N["act"] + "slots")).get("hidden") or "").lower() == "true"
                       and not mutant("gnc_versteckt_ignoriert"),
                       "eltern_angegeben": a.find(N["act"] + "parent") is not None})
    for t in b.findall(N["gnc"] + "transaction"):
        cur = t.find(N["trn"] + "currency")
        splits = [{"konto": _t(s, "split:account"), "wert": cent(_t(s, "split:value")), "roh": _t(s, "split:value"),
                   "memo": _t(s, "split:memo") or ""} for s in t.findall(f"{N['trn']}splits/{N['trn']}split")]
        buchungen.append({"guid": _t(t, "trn:id"), "datum_roh": _t(t, "trn:date-posted/ts:date"),
                          "beschreibung": _t(t, "trn:description"),
                          "notiz": _slots(t.find(N["trn"] + "slots")).get("notes"),
                          "eur": cur is None or _eur(_t(cur, "cmdty:space"), _t(cur, "cmdty:id")), "splits": splits})
    root = {k["guid"] for k in konten if k["typ"] == "ROOT"}
    return {"konten": [k for k in konten if k["typ"] != "ROOT"], "root": root, "buchungen": buchungen, "sqlite": False,
            "alle": {k["guid"] for k in konten}}


def _lies_sqlite(roh: bytes) -> dict:
    fmt = "gnc-sqlite"
    con = sqlite3.connect(":memory:")
    try:
        con.deserialize(roh)
        tabellen = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    except sqlite3.DatabaseError:
        raise _Fehler("import_datei_beschaedigt", fmt) from None
    spalten = {"books": {"root_account_guid"}, "accounts": {"guid", "name", "account_type", "commodity_guid",
                                                             "parent_guid", "code", "description", "hidden"},
               "transactions": {"guid", "currency_guid", "post_date", "description"},
               "splits": {"guid", "tx_guid", "account_guid", "memo", "value_num", "value_denom"}}
    try:
        for tab, sp in spalten.items():
            if tab not in tabellen or not sp <= {r[1] for r in con.execute(f"PRAGMA table_info({tab})")}:
                raise _Fehler("import_format_ungueltig", fmt)
        buecher = con.execute("SELECT root_account_guid FROM books").fetchall()
        if len(buecher) != 1:
            raise _Fehler("import_format_ungueltig", fmt)
        root = buecher[0][0]
        cmd = {}
        if "commodities" in tabellen:
            cmd = {g: (ns, mn) for g, ns, mn in con.execute("SELECT guid, namespace, mnemonic FROM commodities")}
        notizen = {}
        if "slots" in tabellen:
            notizen = {g: s for g, s in con.execute("SELECT obj_guid, string_val FROM slots WHERE name = 'notes'")}
        alle = {r[0]: r for r in con.execute(
            "SELECT guid, name, account_type, commodity_guid, parent_guid, code, description, hidden FROM accounts "
            "ORDER BY rowid")}
        txs = con.execute("SELECT guid, currency_guid, post_date, description FROM transactions ORDER BY rowid").fetchall()
        sp = {}
        for g, tx, acc, memo, num, den in con.execute(
                "SELECT guid, tx_guid, account_guid, memo, value_num, value_denom FROM splits ORDER BY rowid"):
            sp.setdefault(tx, []).append((acc, memo, num, den))
    except sqlite3.DatabaseError:
        raise _Fehler("import_datei_beschaedigt", fmt) from None

    def im_baum(g):
        seen = set()
        while g is not None and g not in seen:
            if g == root:
                return True
            seen.add(g)
            g = alle[g][4] if g in alle else None
        return False

    def eur(cg):
        return cg is None or cg not in cmd or _eur(*cmd[cg])

    konten = [{"guid": g, "name": r[1], "typ": r[2], "eltern": r[4], "code": r[5] or "", "beschreibung": r[6] or "",
               "eur": eur(r[3]), "versteckt": bool(r[7]) and not mutant("gnc_versteckt_ignoriert"),
               "eltern_angegeben": True}
              for g, r in alle.items() if g != root and (im_baum(r[4]) or mutant("gnc_vorlagenbaum")
                                                          and r[2] != "ROOT")]
    baum = {k["guid"] for k in konten}
    buchungen = []
    for g, cur, datum, besch in txs:
        s = sp.get(g, [])
        if s and all(acc in alle and acc not in baum for acc, *_ in s) and not mutant("gnc_vorlagenbaum"):
            continue
        splits = []
        for acc, memo, num, den in s:
            w = None
            if isinstance(num, int) and isinstance(den, int) and den > 0:
                f = Fraction(num, den) * 100
                w = int(f) if f.denominator == 1 and abs(f.numerator) <= MAX else None
            splits.append({"konto": acc if acc in baum or acc not in alle else ("ausserhalb:" + acc), "wert": w,
                           "roh": "x", "memo": memo or ""})
        buchungen.append({"guid": g, "datum_roh": datum, "beschreibung": besch, "notiz": notizen.get(g),
                          "eur": eur(cur), "splits": splits})
    return {"konten": konten, "root": {root}, "buchungen": buchungen, "sqlite": True, "alle": set(baum) | {root}}


def _pruefe(d: dict) -> list[ImportMeldung]:
    aus = []

    def f(text, ref):
        aus.append(ImportMeldung("import_inhalt_ungueltig", text, ref))
    bekannt = {k["guid"] for k in d["konten"]}
    for k in d["konten"]:
        if not k["guid"] or not k["name"] or not k["typ"]:
            f("Konto ohne Pflichtangabe", k["guid"])
        elif not d["sqlite"] and k["eltern"] is not None and k["eltern"] not in bekannt | d["root"]:
            f("Elternkonto unbekannt", k["guid"])
    for t in d["buchungen"]:
        if not t["guid"] or _datum(t["datum_roh"]) is None or not t["splits"]:
            f("Transaktion ungültig (Pflichtangabe, Datum oder ohne Split)", t["guid"])
            continue
        for s in t["splits"]:
            if s["wert"] is None or s["roh"] is None or not s["konto"] or s["konto"] not in bekannt:
                f("Split ungültig (Wert oder Konto)", t["guid"])
                break
    return aus


# ------------------------------------------------------------ Import
def importiere_gnucash(config, quelle, *, dateiname: str | None = None) -> ImportErgebnis:
    if isinstance(quelle, (bytes, bytearray)):
        roh = bytes(quelle)
    elif isinstance(quelle, (str, os.PathLike)):
        pfad = Path(quelle)
        roh = pfad.read_bytes()
        dateiname = dateiname if dateiname is not None else pfad.name
    else:
        raise TypeError("quelle muss Pfad oder Bytes sein")
    if config.mock_modus and config.mock_heute is not None:
        jetzt = config.mock_heute.isoformat() + "T12:00:00Z"
    else:
        jetzt = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return importiere_gnc_bytes(buch_fuer(config.aktive_datenbank), roh, dateiname, jetzt=jetzt)


def _fehlschlag(fmt, meldungen) -> ImportErgebnis:
    return ImportErgebnis(False, fmt, *([0] * len(ZAEHLER)), warnungen=(), fehler=tuple(meldungen), import_id=None)


def importiere_gnc_bytes(buch: Buch, roh: bytes, dateiname: str | None, *, jetzt: str | None = None) -> ImportErgebnis:
    def fehler(code, fmt):
        return _fehlschlag(fmt, [ImportMeldung(code, f"Import nicht möglich: {code}", None)])
    try:
        if not roh:
            return fehler("import_datei_leer", None)
        if roh[:2] == b"\x1f\x8b":
            fmt = "gnc-xml-gzip"
            try:
                inhalt = gzip.decompress(roh)
            except (OSError, EOFError, zlib.error):
                return fehler("import_datei_beschaedigt", fmt)
            if not inhalt:
                return fehler("import_datei_leer", fmt)
            rest = inhalt[3:] if inhalt.startswith(b"\xef\xbb\xbf") else inhalt
            if not rest.lstrip(b" \t\r\n").startswith(b"<"):
                return fehler("import_format_ungueltig", None)
            d = _lies_xml(inhalt, fmt)
        elif roh[:16] == b"SQLite format 3\x00":
            fmt = "gnc-sqlite"
            d = _lies_sqlite(roh)
        else:
            rest = roh[3:] if roh.startswith(b"\xef\xbb\xbf") else roh
            if not rest.lstrip(b" \t\r\n").startswith(b"<"):
                return fehler("import_format_ungueltig", None)
            fmt = "gnc-xml"
            d = _lies_xml(roh, fmt)
    except _Fehler as e:
        return fehler(e.code, e.fmt)
    meldungen = _pruefe(d)
    if meldungen:
        return _fehlschlag(fmt, meldungen)
    neu = buch.kopie()
    ergebnis = _abbilden(buch, neu, d, fmt)
    # M32 (sammel3.md 1.3): gleichnamige Geschwister bereinigen, in derselben Änderung
    from ..buch import bereinigen
    from .ergebnis import ImportMeldung as _IM
    extra = tuple(_IM(c, f"Konto „{n}“ bereinigt", n) for c, n in bereinigen(neu))
    if extra:
        ergebnis = ImportErgebnis(**{**ergebnis.__dict__, "warnungen": tuple(ergebnis.warnungen) + extra})
    vorgang_id = neu.neue_id("import")
    e = ergebnis.als_dict()
    e["import_id"] = vorgang_id
    neu.importe.append({"id": vorgang_id, "art": "gnucash", "dateiname": dateiname,
                        "sha256": hashlib.sha256(roh).hexdigest(),
                        "importiert_am": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ergebnis": e})
    from ..m3 import protokolliere, protokollform
    protokolliere(neu, protokollform(buch), "import", "import_gnucash", f"import:{vorgang_id}",
                  jetzt or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "GnuCash-Datei importiert")
    buch.uebernehme(neu)
    return ImportErgebnis(**{**ergebnis.__dict__, "import_id": vorgang_id})


def _abbilden(alt: Buch, neu: Buch, d: dict, fmt: str) -> ImportErgebnis:
    z = {k: 0 for k in ZAEHLER}
    warn: list[ImportMeldung] = []

    def warne(code, ref):
        warn.append(ImportMeldung(code, f"Hinweis: {code}", ref))
    art: dict[str, str] = {}
    elemente = {k["guid"]: k for k in d["konten"]}
    for g, k in elemente.items():
        if k["typ"] not in TYPEN:
            warne("konto_uebersprungen", g)
            continue
        if not k["eur"]:
            warne("fremdwaehrung", g)
            continue
        art[g], w = TYPEN[k["typ"]]
        if w:
            warne(w, g)
    zuordnung: dict[str, int] = {}
    benutzt: set[int] = set()

    def konto(g: str) -> int:
        if g in zuordnung:
            return zuordnung[g]
        k = elemente[g]
        k_art = art[g]
        eltern = None
        if k["eltern"] in art:
            if KLASSE[art[k["eltern"]]] != KLASSE[k_art]:
                warne("hierarchie_angepasst", g)
            else:
                eltern = konto(k["eltern"])
        ext = "gnc:" + g
        n = k["code"].replace(" ", "").upper()
        pruef = (lambda x: True) if mutant("gnc_iban_ohne_pruefsumme") else iban_gueltig
        iban = n if KLASSE[k_art] == "bestand" and IBAN_FORM.match(n) and pruef(n) else None
        treffer = next((x for x in neu.konten.values() if x["extern_id"] == ext), None)
        frei = [x for x in sorted(neu.konten.values(), key=lambda x: x["id"])
                if x["id"] in alt.konten and x["id"] not in benutzt]
        if treffer is None and iban is not None:
            treffer = next((x for x in frei if x["iban"] == iban and not (x["extern_id"] or "").startswith("gnc:")),
                           None)
        elif treffer is None:
            treffer = next((x for x in frei if x["art"] == k_art and x["name"] == k["name"] and x["eltern_id"] == eltern
                            and x["iban"] is None and not (x["extern_id"] or "").startswith(("gnc:", "kontor:"))),
                           None)
        ist_kat = k_art in ("aufwand", "ertrag")
        if treffer is not None:
            if treffer["extern_id"] is None:
                treffer["extern_id"] = ext
            benutzt.add(treffer["id"])
            z["kategorien_vorhanden" if ist_kat else "konten_vorhanden"] += 1
            zuordnung[g] = treffer["id"]
            return treffer["id"]
        if KLASSE[k_art] == "bestand" and IBAN_FORM.match(n):
            if not pruef(n):
                warne("iban_ungueltig", g)
            elif any(x["iban"] == n for x in neu.konten.values()):
                warne("iban_doppelt", g)
                iban = None
        x = {"id": neu.neue_id("konto"), "name": k["name"], "art": k_art, "eltern_id": eltern, "iban": iban,
             "geschlossen": k["versteckt"], "eroeffnet_am": None, "notiz": k["beschreibung"], "extern_id": ext}
        neu.konten[x["id"]] = x
        z["kategorien_neu" if ist_kat else "konten_neu"] += 1
        zuordnung[g] = x["id"]
        return x["id"]

    for g in elemente:
        if g in art:
            konto(g)

    def uebersprungen(t):
        return not t["eur"] or any(s["konto"] not in art for s in t["splits"])

    from ..m3 import alias_treffer
    empf: dict[str, int] = {}
    for t in d["buchungen"]:
        if uebersprungen(t):
            continue
        n = (t["beschreibung"] or "").strip()
        if not n or n in empf:
            continue
        e = next((x for x in neu.empfaenger.values() if x["name"] == n), None) or alias_treffer(neu, n)
        if e is None:
            e = {"id": neu.neue_id("empfaenger"), "name": n, "extern_id": None, "aliase": [],
                 "standardkategorie_id": None}
            neu.empfaenger[e["id"]] = e
            z["empfaenger_neu"] += 1
        else:
            z["empfaenger_vorhanden"] += 1
        empf[n] = e["id"]

    vorhandene = {e for b in neu.buchungen.values() for e in b["extern_ids"]}
    kandidaten = [b for b in alt.buchungen.values() if not any(e.startswith("gnc:") for e in b["extern_ids"])]
    neue = []
    for t in d["buchungen"]:
        if uebersprungen(t):
            warne("buchung_uebersprungen", t["guid"])
            z["buchungen_uebersprungen"] += 1
            continue
        if "gnc:" + t["guid"] in vorhandene:
            z["buchungen_vorhanden"] += 1
            continue
        sp = [{"konto_id": zuordnung[s["konto"]], "betrag": s["wert"], "memo": s["memo"]} for s in t["splits"]]
        summe = sum(s["betrag"] for s in sp)
        if summe != 0 or len(sp) < 2:
            u = next((k for k in neu.konten.values() if k["extern_id"] == "kontor:unausgeglichen"), None)
            if u is None:
                u = {"id": neu.neue_id("konto"), "name": "Unausgeglichen", "art": "eigenkapital", "eltern_id": None,
                     "iban": None, "geschlossen": False, "eroeffnet_am": None, "notiz": "",
                     "extern_id": "kontor:unausgeglichen"}
                neu.konten[u["id"]] = u
            sp.append({"konto_id": u["id"], "betrag": -summe, "memo": ""})
            warne("buchung_ausgeglichen", t["guid"])
        n = (t["beschreibung"] or "").strip()
        neue.append({"guid": t["guid"], "datum": _datum(t["datum_roh"]), "empfaenger_id": empf.get(n) if n else None,
                     "name": n or None, "splits": sp,
                     "verwendungszweck": (t["beschreibung"] or "") if mutant("gnc_zweck_aus_beschreibung")
                     else t["notiz"] or ""})

    def name(eid):
        return None if eid is None else neu.empfaenger[eid]["name"]
    for b in neue:
        exakt, aehnlich = set(), set()
        bd = dt.date.fromisoformat(b["datum"])
        for s in b["splits"]:
            if KLASSE[neu.konten[s["konto_id"]]["art"]] != "bestand":
                continue
            for c in kandidaten:
                if not any(cs["konto_id"] == s["konto_id"] and cs["betrag"] == s["betrag"] for cs in c["splits"]):
                    continue
                if c["datum"] == b["datum"] and passend(b["name"], name(c["empfaenger_id"])):
                    exakt.add(c["id"])
                elif abs((dt.date.fromisoformat(c["datum"]) - bd).days) <= 3:
                    aehnlich.add(c["id"])
        b["E"], b["A"] = exakt, aehnlich - exakt
    for b in neue:
        andere = set().union(*[x["E"] for x in neue if x is not b])
        if len(b["E"]) == 1 and not (b["E"] & andere) and not mutant("gnc_ohne_dubletten"):
            c = neu.buchungen[min(b["E"])]
            c["extern_ids"].append("gnc:" + b["guid"])
            z["buchungen_zusammengefuehrt"] += 1
            continue
        nb = {"id": neu.neue_id("buchung"), "datum": b["datum"], "empfaenger_id": b["empfaenger_id"],
              "verwendungszweck": b["verwendungszweck"], "status": "importiert",
              "splits": [{"id": neu.neue_id("split"), **s, "abstimmung_id": None} for s in b["splits"]],
              "tag_ids": set(), "extern_ids": ["gnc:" + b["guid"]], "vorschlag": None, "gegen_iban": None}
        neu.buchungen[nb["id"]] = nb
        z["buchungen_neu"] += 1
        z["splits_neu"] += len(nb["splits"])
        if (b["E"] | b["A"]) and not mutant("gnc_ohne_dubletten"):
            vid = neu.neue_id("verdacht")
            neu.verdachte[vid] = {"id": vid, "buchung_id": nb["id"], "kandidat_ids": sorted(b["E"] | b["A"]),
                                  "grund": "mehrdeutig" if b["E"] else "aehnlich", "status": "offen",
                                  "erstellt_am": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            z["buchungen_zur_pruefung"] += 1
    return ImportErgebnis(True, fmt, **z, warnungen=tuple(warn), fehler=(), import_id=None)
