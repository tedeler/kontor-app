"""KMyMoney-Import der Wegwerf-Referenz (datenmodell.md 10). KEIN Anwendungscode."""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import os
import re
import xml.etree.ElementTree as ET
import zlib
from fractions import Fraction
from pathlib import Path
from xml.parsers import expat

from .. import mutant
from ..buch import KLASSE, MAX, Buch, buch_fuer, iban_gueltig, passend
from .ergebnis import ZAEHLER, ImportErgebnis, ImportMeldung

__all__ = ["importiere_kmy", "importiere_bytes", "ImportErgebnis", "ImportMeldung"]

STANDARD = {"AStd::Asset", "AStd::Liability", "AStd::Expense", "AStd::Income", "AStd::Equity"}
TYPEN = {1: ("girokonto", None), 2: ("sparkonto", None), 6: ("sparkonto", None), 8: ("sparkonto", None),
         3: ("girokonto", "kontoart_ersetzt"), 9: ("sparkonto", "kontoart_ersetzt"),
         14: ("sparkonto", "kontoart_ersetzt"), 4: ("kreditkonto", None), 5: ("kreditkonto", None),
         10: ("kreditkonto", None), 12: ("ertrag", None), 13: ("aufwand", None), 16: ("eigenkapital", None)}
WERT = re.compile(r"^(-?)([0-9]+)(?:/([0-9]+))?$")
DATUM = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2})(T.*)?$")


def cent(wert: str | None) -> int | None:
    if wert is None:
        return None
    m = WERT.match(wert)
    if not m:
        return None
    n = int(m[3]) if m[3] is not None else 1
    if n == 0:
        return None
    f = Fraction(int(m[2]), n) * 100
    if f.denominator != 1 or f.numerator > MAX:
        return None
    return -f.numerator if m[1] else f.numerator


def datum(text: str | None) -> str | None:
    if text is None:
        return None
    m = DATUM.match(text)
    if not m:
        return None
    try:
        dt.date.fromisoformat(m[1])
    except ValueError:
        return None
    return m[1]


def importiere_kmy(config, quelle, *, dateiname: str | None = None) -> ImportErgebnis:
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
    return importiere_bytes(buch_fuer(config.aktive_datenbank), roh, dateiname, jetzt=jetzt)


def _fehlschlag(fmt, meldungen) -> ImportErgebnis:
    return ImportErgebnis(False, fmt, *([0] * len(ZAEHLER)), warnungen=(), fehler=tuple(meldungen), import_id=None)


def importiere_bytes(buch: Buch, roh: bytes, dateiname: str | None, *, jetzt: str | None = None) -> ImportErgebnis:
    def fehler(code, text, fmt):
        return _fehlschlag(fmt, [ImportMeldung(code, text, None)])

    if not roh:
        return fehler("import_datei_leer", "Die Datei ist leer.", None)
    if roh[:2] == b"\x1f\x8b":
        fmt = "kmy-gzip"
        try:
            xml = gzip.decompress(roh)
        except (OSError, EOFError, zlib.error):
            return fehler("import_datei_beschaedigt", "Die gzip-Datei ist beschädigt.", fmt)
        if not xml:
            return fehler("import_datei_leer", "Die Datei ist leer.", fmt)
    else:
        rest = roh[3:] if roh.startswith(b"\xef\xbb\xbf") else roh
        if not rest.lstrip(b" \t\r\n").startswith(b"<"):
            return fehler("import_format_ungueltig", "Keine KMyMoney-Datei.", None)
        fmt, xml = "kmy-xml", roh
    intern = []
    p = expat.ParserCreate()
    p.StartDoctypeDeclHandler = lambda name, sysid, pubid, hat_intern: intern.append(bool(hat_intern))
    try:
        p.Parse(xml, True)
    except expat.ExpatError:
        return fehler("import_datei_beschaedigt", "Das XML ist nicht wohlgeformt.", fmt)
    if any(intern):
        return fehler("import_format_ungueltig", "DTD mit internem Teil ist nicht erlaubt.", None)
    wurzel = ET.fromstring(xml)
    if wurzel.tag != "KMYMONEY-FILE":
        return fehler("import_format_ungueltig", "Wurzelelement ist nicht KMYMONEY-FILE.", None)
    meldungen = _pruefe_inhalt(wurzel)
    if meldungen:
        if mutant("import_teilimport"):
            for pe in wurzel.findall("PAYEES/PAYEE"):
                if pe.get("name"):
                    buch.empfaenger_anlegen(pe.get("name") + " (teil)", rest=False)
        return _fehlschlag(fmt, meldungen)
    neu = buch.kopie()
    ergebnis = _abbilden(buch, neu, wurzel, fmt)
    # M32 (sammel3.md 1.3): gleichnamige Geschwister bereinigen, in derselben Änderung
    from ..buch import bereinigen
    from .ergebnis import ImportMeldung as _IM
    extra = tuple(_IM(c, f"Konto „{n}“ bereinigt", n) for c, n in bereinigen(neu))
    if extra:
        ergebnis = ImportErgebnis(**{**ergebnis.__dict__, "warnungen": tuple(ergebnis.warnungen) + extra})
    vorgang_id = neu.neue_id("import")
    d = ergebnis.als_dict()
    d["import_id"] = vorgang_id
    neu.importe.append({"id": vorgang_id, "art": "kmymoney", "dateiname": dateiname,
                        "sha256": hashlib.sha256(roh).hexdigest(),
                        "importiert_am": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "ergebnis": d})
    from ..m3 import protokolliere, protokollform
    protokolliere(neu, protokollform(buch), "import", "import_kmymoney", f"import:{vorgang_id}",
                  jetzt or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "KMyMoney-Datei importiert")
    buch.uebernehme(neu)
    return ImportErgebnis(**{**ergebnis.__dict__, "import_id": vorgang_id})


def _pruefe_inhalt(w: ET.Element) -> list[ImportMeldung]:
    aus: list[ImportMeldung] = []

    def f(text, ref):
        aus.append(ImportMeldung("import_inhalt_ungueltig", text, ref))

    konten = w.findall("ACCOUNTS/ACCOUNT")
    ids = {a.get("id") for a in konten if a.get("id")} | STANDARD
    for a in konten:
        for attr in ("id", "name", "type"):
            if a.get(attr) is None:
                f(f"ACCOUNT ohne Attribut {attr}", a.get("id"))
        par = a.get("parentaccount")
        if par and par not in ids:
            f("Elternkonto unbekannt", a.get("id"))
    payees = set()
    for pe in w.findall("PAYEES/PAYEE"):
        for attr in ("id", "name"):
            if pe.get(attr) is None:
                f(f"PAYEE ohne Attribut {attr}", pe.get("id"))
        payees.add(pe.get("id"))
    tags = set()
    for t in w.findall("TAGS/TAG"):
        for attr in ("id", "name"):
            if t.get(attr) is None:
                f(f"TAG ohne Attribut {attr}", t.get("id"))
        tags.add(t.get("id"))
    for t in w.findall("TRANSACTIONS/TRANSACTION"):
        ref = t.get("id")
        if ref is None:
            f("TRANSACTION ohne id", None)
        if t.get("postdate") is None:
            f("TRANSACTION ohne postdate", ref)
        elif datum(t.get("postdate")) is None:
            f("Ungültiges Datum", ref)
        splits = t.findall("SPLITS/SPLIT")
        if not splits:
            f("Transaktion ohne Split", ref)
        for s in splits:
            konto = s.get("account")
            if konto is None:
                f("SPLIT ohne account", ref)
            elif konto not in ids or konto in STANDARD:
                f("Split verweist auf unbekanntes Konto oder Standardkonto", ref)
            if s.get("value") is None:
                f("SPLIT ohne value", ref)
            elif cent(s.get("value")) is None:
                f("Ungültiger Betrag", ref)
            if s.get("payee") and s.get("payee") not in payees:
                f("Unbekannter Empfänger", ref)
            for tg in s.findall("TAG"):
                if tg.get("id") not in tags:
                    f("Unbekannter Tag", ref)
    return aus


def _abbilden(alt: Buch, neu: Buch, w: ET.Element, fmt: str) -> ImportErgebnis:
    z = {k: 0 for k in ZAEHLER}
    warn: list[ImportMeldung] = []

    def warne(code, ref):
        warn.append(ImportMeldung(code, f"Hinweis: {code}", ref))

    # ---------------------------------------------------------------- Konten
    elemente = {a.get("id"): a for a in w.findall("ACCOUNTS/ACCOUNT") if a.get("id") not in STANDARD}
    art: dict[str, str] = {}
    for kid, a in elemente.items():
        try:
            typ = int(a.get("type"))
        except ValueError:
            typ = -1
        if typ not in TYPEN:
            warne("konto_uebersprungen", kid)
            continue
        if (a.get("currency") or "EUR") != "EUR":
            warne("fremdwaehrung", kid)
            continue
        art[kid], w_code = TYPEN[typ]
        if w_code:
            warne(w_code, kid)
    zuordnung: dict[str, int] = {}
    benutzt: set[int] = set()

    def paare(a):
        return {p.get("key"): p.get("value") for p in a.findall("KEYVALUEPAIRS/PAIR")}

    def konto(kid: str) -> int:
        if kid in zuordnung:
            return zuordnung[kid]
        a = elemente[kid]
        k_art = art[kid]
        par = a.get("parentaccount") or ""
        eltern = None
        if par and par not in STANDARD and par in art:
            if KLASSE[art[par]] != KLASSE[k_art]:
                warne("hierarchie_angepasst", kid)
            else:
                eltern = konto(par)
        ext = "kmy:" + kid
        kv = paare(a)
        roh_iban = kv.get("iban")
        n_iban = roh_iban.replace(" ", "").upper() if roh_iban else None
        treffer = next((k for k in neu.konten.values() if k["extern_id"] == ext), None)
        if treffer is None:
            # M4 (gnucash.md 7): auch Konten mit gnc:-Kennung, jedes höchstens einmal je Lauf
            frei = [k for k in sorted(neu.konten.values(), key=lambda k: k["id"]) if k["id"] in alt.konten
                    and k["id"] not in benutzt and (k["extern_id"] is None
                                                    or (k["extern_id"].startswith("gnc:") and not mutant("kmy_ohne_gnc")))]
            if KLASSE[k_art] == "bestand":
                if n_iban and iban_gueltig(n_iban):
                    treffer = next((k for k in frei if k["iban"] == n_iban), None)
                else:
                    treffer = next((k for k in frei if (k["extern_id"] or "").startswith("gnc:") and k["iban"] is None
                                    and k["art"] == k_art and k["name"] == a.get("name")
                                    and k["eltern_id"] == eltern), None)
            else:
                treffer = next((k for k in frei if k["art"] == k_art
                                and k["name"] == a.get("name") and k["eltern_id"] == eltern), None)
            if treffer is not None:
                benutzt.add(treffer["id"])
                if treffer["extern_id"] is None:
                    treffer["extern_id"] = ext
        ist_kat = k_art in ("aufwand", "ertrag")
        if treffer is not None:
            z["kategorien_vorhanden" if ist_kat else "konten_vorhanden"] += 1
            zuordnung[kid] = treffer["id"]
            return treffer["id"]
        iban = None
        if roh_iban and KLASSE[k_art] == "bestand":
            if not iban_gueltig(n_iban):
                warne("iban_ungueltig", kid)
            elif any(k["iban"] == n_iban for k in neu.konten.values()):
                warne("iban_doppelt", kid)
            else:
                iban = n_iban
        eroeffnet = None
        if a.get("opened"):
            eroeffnet = datum(a.get("opened")) if len(a.get("opened")) == 10 else None
            if eroeffnet is None:
                warne("eroeffnungsdatum_ungueltig", kid)
        k = {"id": neu.neue_id("konto"), "name": a.get("name"), "art": k_art, "eltern_id": eltern, "iban": iban,
             "geschlossen": (kv.get("mm-closed") or "").lower() == "yes", "eroeffnet_am": eroeffnet,
             "notiz": a.get("description") or "", "extern_id": ext}
        neu.konten[k["id"]] = k
        z["kategorien_neu" if ist_kat else "konten_neu"] += 1
        zuordnung[kid] = k["id"]
        return k["id"]

    for kid in elemente:
        if kid in art:
            konto(kid)

    # ------------------------------------------------- Empfänger und Tags
    empf: dict[str, int] = {}
    in_lauf: set[int] = set()
    for pe in w.findall("PAYEES/PAYEE"):
        ext = "kmy:" + pe.get("id")
        t = next((e for e in neu.empfaenger.values() if e["extern_id"] == ext), None)
        if t is None:
            t = next((e for e in neu.empfaenger.values() if e["name"] == pe.get("name")), None)
            if t is None:
                from ..m3 import alias_treffer
                t = alias_treffer(neu, pe.get("name"))
            if t is not None and t["id"] in in_lauf:
                warne("empfaenger_zusammengefasst", pe.get("id"))
        if t is None or mutant("idempotenz_empfaenger"):
            t = {"id": neu.neue_id("empfaenger"), "name": pe.get("name"), "extern_id": ext, "aliase": [],
                 "standardkategorie_id": None}
            neu.empfaenger[t["id"]] = t
            in_lauf.add(t["id"])
            z["empfaenger_neu"] += 1
        else:
            z["empfaenger_vorhanden"] += 1
        empf[pe.get("id")] = t["id"]
    tag: dict[str, int] = {}
    in_lauf = set()
    for te in w.findall("TAGS/TAG"):
        ext = "kmy:" + te.get("id")
        t = next((x for x in neu.tags.values() if x["extern_id"] == ext), None)
        if t is None:
            t = next((x for x in neu.tags.values() if x["name"].casefold() == te.get("name").casefold()), None)
            if t is not None and t["id"] in in_lauf:
                warne("tag_zusammengefasst", te.get("id"))
        if t is None:
            t = {"id": neu.neue_id("tag"), "name": te.get("name"), "extern_id": ext}
            neu.tags[t["id"]] = t
            in_lauf.add(t["id"])
            z["tags_neu"] += 1
        else:
            z["tags_vorhanden"] += 1
        tag[te.get("id")] = t["id"]

    # ------------------------------------------------------------ Buchungen
    vorhandene = {e for b in neu.buchungen.values() for e in b["extern_ids"]}
    kandidaten = [b for b in alt.buchungen.values() if not any(e.startswith("kmy:") for e in b["extern_ids"])]
    neue: list[dict] = []
    for t in w.findall("TRANSACTIONS/TRANSACTION"):
        tid = t.get("id")
        splits = t.findall("SPLITS/SPLIT")
        if any(s.get("account") not in art for s in splits) or (t.get("commodity") or "EUR") != "EUR":
            warne("buchung_uebersprungen", tid)
            z["buchungen_uebersprungen"] += 1
            continue
        if "kmy:" + tid in vorhandene and not mutant("idempotenz_buchungen"):
            z["buchungen_vorhanden"] += 1
            continue
        sp = [{"konto_id": zuordnung[s.get("account")], "betrag": cent(s.get("value")), "memo": s.get("memo") or ""}
              for s in splits]
        summe = sum(s["betrag"] for s in sp)
        if (summe != 0 or len(sp) < 2) and not mutant("import_ohne_ausgleich"):
            u = next((k for k in neu.konten.values() if k["extern_id"] == "kontor:unausgeglichen"), None)
            if u is None:
                u = {"id": neu.neue_id("konto"), "name": "Unausgeglichen", "art": "eigenkapital", "eltern_id": None,
                     "iban": None, "geschlossen": False, "eroeffnet_am": None, "notiz": "",
                     "extern_id": "kontor:unausgeglichen"}
                neu.konten[u["id"]] = u
            sp.append({"konto_id": u["id"], "betrag": -summe, "memo": ""})
            warne("buchung_ausgeglichen", tid)
        empf_id = next((empf[s.get("payee")] for s in splits if s.get("payee")), None)
        tag_ids = {tag[tg.get("id")] for s in splits for tg in s.findall("TAG")}
        neue.append({"tid": tid, "datum": datum(t.get("postdate")), "empfaenger_id": empf_id,
                     "verwendungszweck": t.get("memo") or "", "splits": sp, "tag_ids": tag_ids})

    def name(eid):
        return None if eid is None else neu.empfaenger[eid]["name"]

    toleranz = 0 if mutant("dublette_ohne_toleranz") else 3
    for b in neue:
        exakt, aehnlich = set(), set()
        bd = dt.date.fromisoformat(b["datum"])
        for s in b["splits"]:
            if KLASSE[neu.konten[s["konto_id"]]["art"]] != "bestand":
                continue
            for c in kandidaten:
                if not any(cs["konto_id"] == s["konto_id"] and cs["betrag"] == s["betrag"] for cs in c["splits"]):
                    continue
                if c["datum"] == b["datum"] and passend(name(b["empfaenger_id"]), name(c["empfaenger_id"])):
                    exakt.add(c["id"])
                elif abs((dt.date.fromisoformat(c["datum"]) - bd).days) <= toleranz:
                    aehnlich.add(c["id"])
        b["E"], b["A"] = exakt, aehnlich - exakt
    for b in neue:
        andere = set().union(*[x["E"] for x in neue if x is not b])
        eindeutig = len(b["E"]) == 1 and (not (b["E"] & andere) or mutant("dublette_ohne_eindeutigkeit"))
        if mutant("dublette_erster_kandidat") and b["E"]:
            eindeutig = True
        if eindeutig:
            c = neu.buchungen[min(b["E"])]
            c["extern_ids"].append("kmy:" + b["tid"])
            z["buchungen_zusammengefuehrt"] += 1
            continue
        nb = neu.buchung_anlegen_roh(b)
        z["buchungen_neu"] += 1
        z["splits_neu"] += len(nb["splits"])
        if b["E"] | b["A"]:
            vid = neu.neue_id("verdacht")
            neu.verdachte[vid] = {"id": vid, "buchung_id": nb["id"], "kandidat_ids": sorted(b["E"] | b["A"]),
                                  "grund": "mehrdeutig" if b["E"] else "aehnlich", "status": "offen",
                                  "erstellt_am": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            z["buchungen_zur_pruefung"] += 1
    return ImportErgebnis(True, fmt, **z, warnungen=tuple(warn), fehler=(), import_id=None)
