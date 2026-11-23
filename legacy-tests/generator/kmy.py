"""Modell, Schreiber und Erwartungsberechnung für KMyMoney-Dateien (.kmy).

Das Modell bildet genau die Teile des KMyMoney-XML-Formats ab, die Kontor in
Meilenstein 1 importiert. Die Erwartungen (bekannte Wahrheit) werden aus dem
Modell nach den Regeln in ``spec/api/datenmodell.md`` Abschnitt 10 berechnet –
nicht durch Parsen der erzeugten Datei.
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .iban import ist_gueltig, normalisiere

STANDARDKONTEN = {
    "AStd::Asset": ("Anlage", 9),
    "AStd::Liability": ("Verbindlichkeit", 10),
    "AStd::Expense": ("Ausgabe", 13),
    "AStd::Income": ("Einnahme", 12),
    "AStd::Equity": ("Eigenkapital", 16),
}

# KMyMoney-Kontotyp -> (Kontor-Art, Warnung) ; None = übersprungen
TYPABBILDUNG: dict[int, tuple[str, str | None]] = {
    1: ("girokonto", None),
    2: ("sparkonto", None),
    6: ("sparkonto", None),
    8: ("sparkonto", None),
    3: ("girokonto", "kontoart_ersetzt"),
    9: ("sparkonto", "kontoart_ersetzt"),
    14: ("sparkonto", "kontoart_ersetzt"),
    4: ("kreditkonto", None),
    5: ("kreditkonto", None),
    10: ("kreditkonto", None),
    12: ("ertrag", None),
    13: ("aufwand", None),
    16: ("eigenkapital", None),
}

KLASSE = {
    "girokonto": "bestand",
    "sparkonto": "bestand",
    "kreditkonto": "bestand",
    "aufwand": "aufwand",
    "ertrag": "ertrag",
    "eigenkapital": "eigenkapital",
}

UNAUSGEGLICHEN = "kontor:unausgeglichen"
FEHLT = object()  # Marker: Attribut weglassen


@dataclass
class KKonto:
    id: str
    name: str
    typ: int
    eltern: str  # KMyMoney-ID oder AStd::…
    waehrung: object = "EUR"  # str oder FEHLT
    eroeffnet: object = ""  # str oder FEHLT
    iban: str | None = None
    geschlossen: bool = False
    beschreibung: object = ""  # str oder FEHLT
    nummer: str = ""


@dataclass
class KSplit:
    konto: str
    wert: int | None  # Cent; None nur zusammen mit wert_text
    memo: object = ""  # str oder FEHLT
    empfaenger: object = ""  # Payee-ID, "" oder FEHLT
    tags: list[str] = field(default_factory=list)
    wert_text: str | None = None  # überschreibt die Darstellung von wert
    abgestimmt: str = "0"


@dataclass
class KBuchung:
    id: str
    datum: str
    splits: list[KSplit]
    memo: object = ""  # str oder FEHLT
    waehrung: object = "EUR"  # commodity; str oder FEHLT
    wahre_kategorie: str | None = None  # KMyMoney-ID der richtigen Kategorie
    umbuchung: bool = False


@dataclass
class KBuch:
    konten: list[KKonto] = field(default_factory=list)
    empfaenger: list[tuple[str, str]] = field(default_factory=list)
    tags: list[tuple[str, str]] = field(default_factory=list)
    buchungen: list[KBuchung] = field(default_factory=list)
    erstellt: str = "2021-12-31"
    geaendert: str = "2025-01-05"

    def konto(self, kid: str) -> KKonto:
        for k in self.konten:
            if k.id == kid:
                return k
        raise KeyError(kid)


# ---------------------------------------------------------------- Schreiben


def _wert_text(s: KSplit) -> str:
    if s.wert_text is not None:
        return s.wert_text
    assert s.wert is not None
    return f"{s.wert}/100"


def _setze(el: ET.Element, name: str, wert: object) -> None:
    if wert is FEHLT:
        return
    el.set(name, str(wert))


def als_xml(buch: KBuch) -> bytes:
    """Serialisiert das Buch deterministisch als KMyMoney-XML (UTF-8)."""
    wurzel = ET.Element("KMYMONEY-FILE")
    fi = ET.SubElement(wurzel, "FILEINFO")
    ET.SubElement(fi, "CREATION_DATE", date=buch.erstellt)
    ET.SubElement(fi, "LAST_MODIFIED_DATE", date=buch.geaendert)
    ET.SubElement(fi, "VERSION", id="1")
    ET.SubElement(fi, "FIXVERSION", id="5")
    benutzer = ET.SubElement(wurzel, "USER", email="erika.mustermann@example.invalid",
                             name="Erika Mustermann (fiktiv)")
    ET.SubElement(benutzer, "ADDRESS", street="Musterweg 1", city="Musterstadt",
                  zipcode="00000", county="", telephone="")

    inst = ET.SubElement(wurzel, "INSTITUTIONS", count="1")
    i = ET.SubElement(inst, "INSTITUTION", id="I000001", name="Testbank (fiktiv)",
                      manager="", sortcode="00000000")
    ET.SubElement(i, "ADDRESS", street="", city="", zip="", telephone="")
    ids = ET.SubElement(i, "ACCOUNTIDS")
    for k in buch.konten:
        if TYPABBILDUNG.get(k.typ, ("", None))[0] in ("girokonto", "sparkonto", "kreditkonto"):
            ET.SubElement(ids, "ACCOUNTID", id=k.id)

    pay = ET.SubElement(wurzel, "PAYEES", count=str(len(buch.empfaenger)))
    for pid, name in buch.empfaenger:
        p = ET.SubElement(pay, "PAYEE", id=pid, name=name, reference="", email="",
                          matchingenabled="0")
        ET.SubElement(p, "ADDRESS", street="", city="", postcode="", telephone="", state="")

    ET.SubElement(wurzel, "COSTCENTERS", count="0")

    tg = ET.SubElement(wurzel, "TAGS", count=str(len(buch.tags)))
    for tid, name in buch.tags:
        ET.SubElement(tg, "TAG", id=tid, name=name, closed="0", tagcolor="#3daee9")

    kinder: dict[str, list[str]] = {}
    for k in buch.konten:
        kinder.setdefault(k.eltern, []).append(k.id)

    acc = ET.SubElement(wurzel, "ACCOUNTS", count=str(len(buch.konten) + len(STANDARDKONTEN)))
    for sid, (sname, styp) in STANDARDKONTEN.items():
        a = ET.SubElement(acc, "ACCOUNT", id=sid, parentaccount="", lastmodified="",
                          lastreconciled="", institution="", number="", opened="",
                          type=str(styp), name=sname, description="", currency="EUR")
        if kinder.get(sid):
            sub = ET.SubElement(a, "SUBACCOUNTS")
            for c in kinder[sid]:
                ET.SubElement(sub, "SUBACCOUNT", id=c)
    for k in buch.konten:
        a = ET.Element("ACCOUNT")
        a.set("id", k.id)
        a.set("parentaccount", k.eltern)
        a.set("lastmodified", "")
        a.set("lastreconciled", "")
        bestand = TYPABBILDUNG.get(k.typ, ("", None))[0] in ("girokonto", "sparkonto", "kreditkonto")
        a.set("institution", "I000001" if bestand else "")
        a.set("number", k.nummer)
        _setze(a, "opened", k.eroeffnet)
        a.set("type", str(k.typ))
        a.set("name", k.name)
        _setze(a, "description", k.beschreibung)
        _setze(a, "currency", k.waehrung)
        acc.append(a)
        if kinder.get(k.id):
            sub = ET.SubElement(a, "SUBACCOUNTS")
            for c in kinder[k.id]:
                ET.SubElement(sub, "SUBACCOUNT", id=c)
        paare = []
        if k.iban is not None:
            paare.append(("iban", k.iban))
        if k.geschlossen:
            paare.append(("mm-closed", "yes"))
        if paare:
            kv = ET.SubElement(a, "KEYVALUEPAIRS")
            for schl, wert in paare:
                ET.SubElement(kv, "PAIR", key=schl, value=wert)

    tr = ET.SubElement(wurzel, "TRANSACTIONS", count=str(len(buch.buchungen)))
    for b in buch.buchungen:
        t = ET.Element("TRANSACTION")
        t.set("id", b.id)
        t.set("postdate", b.datum)
        _setze(t, "memo", b.memo)
        t.set("entrydate", b.datum)
        _setze(t, "commodity", b.waehrung)
        tr.append(t)
        ss = ET.SubElement(t, "SPLITS")
        for n, s in enumerate(b.splits, start=1):
            e = ET.Element("SPLIT")
            e.set("id", f"S{n:04d}")
            _setze(e, "payee", s.empfaenger)
            e.set("reconciledate", "")
            e.set("action", "")
            e.set("reconcileflag", s.abgestimmt)
            e.set("value", _wert_text(s))
            e.set("shares", _wert_text(s))
            e.set("price", "1/1")
            _setze(e, "memo", s.memo)
            e.set("account", s.konto)
            e.set("number", "")
            e.set("bankid", "")
            ss.append(e)
            for tag in s.tags:
                ET.SubElement(e, "TAG", id=tag)

    kv = ET.SubElement(wurzel, "KEYVALUEPAIRS")
    ET.SubElement(kv, "PAIR", key="kmm-baseCurrency", value="EUR")
    ET.SubElement(kv, "PAIR", key="kmm-id", value="{00000000-0000-4000-8000-000000004711}")
    ET.SubElement(wurzel, "SCHEDULES", count="0")
    ET.SubElement(wurzel, "SECURITIES", count="0")
    cur = ET.SubElement(wurzel, "CURRENCIES", count="1")
    ET.SubElement(cur, "CURRENCY", id="EUR", name="Euro", symbol="€", type="3",
                  saf="100", scf="100", pp="4", **{"rounding-method": "7"})
    ET.SubElement(wurzel, "PRICES", count="0")
    ET.SubElement(wurzel, "REPORTS", count="0")
    ET.SubElement(wurzel, "BUDGETS", count="0")
    ET.SubElement(wurzel, "ONLINEJOBS", count="0")

    ET.indent(wurzel, space=" ")
    rumpf = ET.tostring(wurzel, encoding="unicode")
    text = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE KMYMONEY-FILE>\n' + rumpf + "\n"
    return text.encode("utf-8")


def packe_gzip(daten: bytes) -> bytes:
    """gzip mit festen Kopfdaten (mtime=0, kein Dateiname) – reproduzierbar."""
    puffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=puffer, mtime=0, compresslevel=9) as gz:
        gz.write(daten)
    return puffer.getvalue()


# ------------------------------------------------------ Erwartung berechnen


def _datum_gueltig(text: str) -> bool:
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        return False
    return len(text) == 10


def erwartung(buch: KBuch, *, fixture: str, format_: str) -> dict:
    """Berechnet die bekannte Wahrheit für einen Import in ein leeres Buch."""
    warnungen: list[dict] = []

    def warn(code: str, ref: str | None) -> None:
        warnungen.append({"code": code, "referenz": ref})

    # Empfänger
    empf_namen: dict[str, str] = {}  # pid -> Name (nach Zusammenfassung)
    gesehen: dict[str, str] = {}
    empf_liste: list[dict] = []
    empf_neu = empf_vorh = 0
    for pid, name in buch.empfaenger:
        if name in gesehen:
            empf_vorh += 1
            warn("empfaenger_zusammengefasst", pid)
        else:
            gesehen[name] = pid
            empf_neu += 1
            empf_liste.append({"extern_id": "kmy:" + pid, "name": name})
        empf_namen[pid] = name

    # Tags
    tag_namen: dict[str, str] = {}
    tag_gesehen: dict[str, str] = {}
    tag_liste: list[dict] = []
    tags_neu = tags_vorh = 0
    tag_ext: dict[str, str] = {}
    for tid, name in buch.tags:
        schl = name.casefold()
        if schl in tag_gesehen:
            tags_vorh += 1
            warn("tag_zusammengefasst", tid)
            tag_ext[tid] = tag_gesehen[schl]
            tag_namen[tid] = next(t["name"] for t in tag_liste if t["extern_id"] == tag_gesehen[schl])
        else:
            tag_gesehen[schl] = "kmy:" + tid
            tags_neu += 1
            tag_liste.append({"extern_id": "kmy:" + tid, "name": name})
            tag_ext[tid] = "kmy:" + tid
            tag_namen[tid] = name

    # Konten
    art_von: dict[str, str] = {}
    uebersprungen: set[str] = set()
    konten: list[dict] = []
    vergebene_iban: set[str] = set()
    konten_neu = kat_neu = 0
    for k in buch.konten:
        abb = TYPABBILDUNG.get(k.typ)
        waehrung = "EUR" if k.waehrung is FEHLT else k.waehrung
        if abb is None:
            uebersprungen.add(k.id)
            warn("konto_uebersprungen", k.id)
            continue
        if waehrung != "EUR":
            uebersprungen.add(k.id)
            warn("fremdwaehrung", k.id)
            continue
        art, w = abb
        if w:
            warn(w, k.id)
        art_von[k.id] = art
    for k in buch.konten:
        if k.id in uebersprungen:
            continue
        art = art_von[k.id]
        eltern = None
        if not k.eltern.startswith("AStd::"):
            if k.eltern in uebersprungen:
                eltern = None
            elif KLASSE[art_von[k.eltern]] != KLASSE[art]:
                warn("hierarchie_angepasst", k.id)
            else:
                eltern = "kmy:" + k.eltern
        iban = None
        if k.iban is not None and KLASSE[art] == "bestand":
            n = normalisiere(k.iban)
            if not ist_gueltig(n):
                warn("iban_ungueltig", k.id)
            elif n in vergebene_iban:
                warn("iban_doppelt", k.id)
            else:
                iban = n
                vergebene_iban.add(n)
        eroeffnet = None
        if k.eroeffnet is not FEHLT and k.eroeffnet != "":
            if _datum_gueltig(k.eroeffnet):
                eroeffnet = k.eroeffnet
            else:
                warn("eroeffnungsdatum_ungueltig", k.id)
        if art in ("aufwand", "ertrag"):
            kat_neu += 1
        else:
            konten_neu += 1
        konten.append({
            "extern_id": "kmy:" + k.id,
            "name": k.name,
            "art": art,
            "eltern_extern_id": eltern,
            "geschlossen": k.geschlossen,
            "iban": iban,
            "eroeffnet_am": eroeffnet,
            "notiz": "" if k.beschreibung is FEHLT else k.beschreibung,
            "ist_kategorie": art in ("aufwand", "ertrag"),
        })

    art_ext = {"kmy:" + kid: a for kid, a in art_von.items()}

    # Buchungen
    buchungen: list[dict] = []
    b_neu = b_ueber = splits_neu = 0
    braucht_ausgleich = False
    for b in buch.buchungen:
        waehrung = "EUR" if b.waehrung is FEHLT else b.waehrung
        if waehrung != "EUR" or any(s.konto in uebersprungen for s in b.splits):
            b_ueber += 1
            warn("buchung_uebersprungen", b.id)
            continue
        splits = []
        for s in b.splits:
            assert s.wert is not None
            splits.append({
                "konto_extern_id": "kmy:" + s.konto,
                "betrag": s.wert,
                "memo": "" if s.memo is FEHLT else s.memo,
            })
        summe = sum(s["betrag"] for s in splits)
        if summe != 0 or len(splits) < 2:
            splits.append({"konto_extern_id": UNAUSGEGLICHEN, "betrag": -summe, "memo": ""})
            warn("buchung_ausgeglichen", b.id)
            braucht_ausgleich = True
            art_ext[UNAUSGEGLICHEN] = "eigenkapital"
        empf = None
        for s in b.splits:
            if s.empfaenger is not FEHLT and s.empfaenger != "":
                empf = empf_namen[s.empfaenger]
                break
        tags: list[str] = []
        for s in b.splits:
            for t in s.tags:
                ext = tag_ext[t]
                if ext not in tags:
                    tags.append(ext)
        gegen = [s for s in splits if KLASSE[art_ext[s["konto_extern_id"]]] != "bestand"]
        kategorie = None
        if len(gegen) == 1 and art_ext[gegen[0]["konto_extern_id"]] in ("aufwand", "ertrag"):
            kategorie = gegen[0]["konto_extern_id"]
        b_neu += 1
        splits_neu += len(splits)
        buchungen.append({
            "extern_id": "kmy:" + b.id,
            "datum": b.datum[:10],
            "empfaenger": empf,
            "verwendungszweck": "" if b.memo is FEHLT else b.memo,
            "status": "importiert",
            "tags": sorted(tags),
            "splits": splits,
            "kategorie_extern_id": kategorie,
            "umsatz": sum(s["betrag"] for s in splits if s["betrag"] > 0),
            "wahre_kategorie_extern_id": ("kmy:" + b.wahre_kategorie) if b.wahre_kategorie else None,
            "umbuchung": b.umbuchung,
        })

    if braucht_ausgleich:
        konten.append({
            "extern_id": UNAUSGEGLICHEN, "name": "Unausgeglichen", "art": "eigenkapital",
            "eltern_extern_id": None, "geschlossen": False, "iban": None,
            "eroeffnet_am": None, "notiz": "", "ist_kategorie": False,
        })

    # Salden
    saldo = {k["extern_id"]: 0 for k in konten}
    anzahl = {k["extern_id"]: 0 for k in konten}
    for b in buchungen:
        beteiligte = set()
        for s in b["splits"]:
            saldo[s["konto_extern_id"]] += s["betrag"]
            beteiligte.add(s["konto_extern_id"])
        for k in beteiligte:
            anzahl[k] += 1
    kinder: dict[str | None, list[str]] = {}
    for k in konten:
        kinder.setdefault(k["eltern_extern_id"], []).append(k["extern_id"])

    def gesamt(ext: str) -> int:
        return saldo[ext] + sum(gesamt(c) for c in kinder.get(ext, []))

    for k in konten:
        k["saldo"] = saldo[k["extern_id"]]
        k["saldo_gesamt"] = gesamt(k["extern_id"])
        k["anzahl_buchungen"] = anzahl[k["extern_id"]]

    for t in tag_liste:
        t["anzahl_buchungen"] = sum(1 for b in buchungen if t["extern_id"] in b["tags"])

    ergebnis = {
        "erfolgreich": True,
        "format": format_,
        "konten_neu": konten_neu,
        "konten_vorhanden": 0,
        "kategorien_neu": kat_neu,
        "kategorien_vorhanden": 0,
        "empfaenger_neu": empf_neu,
        "empfaenger_vorhanden": empf_vorh,
        "tags_neu": tags_neu,
        "tags_vorhanden": tags_vorh,
        "buchungen_neu": b_neu,
        "buchungen_vorhanden": 0,
        "buchungen_zusammengefuehrt": 0,
        "buchungen_zur_pruefung": 0,
        "buchungen_uebersprungen": b_ueber,
        "splits_neu": splits_neu,
    }
    return {
        "fixture": fixture,
        "art": "kmymoney",
        "erfolgreich": True,
        "fehler_code": None,
        "ergebnis": ergebnis,
        "warnungen": warnungen,
        "konten": konten,
        "empfaenger": empf_liste,
        "tags": tag_liste,
        "buchungen": buchungen,
        "summen": {
            "anzahl_transaktionen_in_datei": len(buch.buchungen),
            "anzahl_buchungen": len(buchungen),
            "anzahl_splits": splits_neu,
            "summe_bestand": sum(k["saldo"] for k in konten if KLASSE[k["art"]] == "bestand"),
            "summe_gesamt": sum(k["saldo"] for k in konten),
        },
        "umbuchungen": [b["extern_id"] for b in buchungen if b["umbuchung"]],
    }


def fehler_erwartung(fixture: str, code: str, format_: str | None, beschreibung: str) -> dict:
    return {
        "fixture": fixture,
        "art": "kmymoney",
        "erfolgreich": False,
        "fehler_code": code,
        "format": format_,
        "beschreibung": beschreibung,
    }
