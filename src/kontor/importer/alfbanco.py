"""Import von Umsätzen aus ALF-BanCo über den QIF-Export (Feature ``alfbanco-import``, D-123 bis D-127).

ALF-BanCo speichert seine Daten verschlüsselt in einem nicht dokumentierten Format; übernommen wird deshalb der
QIF-Export (ab der Profi-Edition), eine Datei je Konto. Der Anwender wählt beim Import das Kontor-Konto, zu dem die
Datei gehört. Kategorien (``L``/``S``, Hierarchie mit ``:``) werden als Kategorien angelegt bzw. wiedererkannt,
Klassen (``/Klasse``) als Tags, Umbuchungen (``[Konto]``) gegen das gleichnamige Bestandskonto gebucht.

Ablauf wie beim KMyMoney- und GnuCash-Import: kein Teilimport, eine protokollierte Änderung ``import_alfbanco``
mit Gruppe ``import:<id>``, Idempotenz über die Herkunftskennung ``alf:<konto_id>:<prüfsumme>`` und
Dublettenerkennung gegen vorhandene Buchungen desselben Kontos.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
from dataclasses import dataclass, field

from .. import buch, db, protokoll
from ..buch import BESTAND
from ..text import passend
from ..validierung import BETRAG_MAX, ApiFehler
from .ergebnis import ImportErgebnis, ImportMeldung
from .kmymoney import MELDUNGEN as _KMY_MELDUNGEN

FORMAT = "qif"
KAT_PRAEFIX = "alf:kat:"
ANFANGSSALDEN = "alf:anfangssalden"

MELDUNGEN = {
    **_KMY_MELDUNGEN,
    "umbuchung_konto_unbekannt": "Das Gegenkonto der Umbuchung gibt es in Kontor nicht; die Buchung steht auf "
                                 "„Unkategorisiert“.",
    "split_differenz": "Die Teilbeträge ergeben nicht den Gesamtbetrag; der Rest steht auf „Unkategorisiert“.",
    "kategorieart_abgeleitet": "Die Kategorie ist in der Datei nicht als Einnahme oder Ausgabe gekennzeichnet; "
                               "die Art wurde aus den Beträgen abgeleitet.",
}

# Abschnitte mit Buchungen eines Bestandskontos; Wertpapierbuchungen werden übersprungen.
_BUCHUNGSTYPEN = {"bank", "ccard", "cash", "oth a", "oth l"}
_UEBERSPRINGEN = {"invst"}


class _Abbruch(Exception):
    def __init__(self, code: str, meldung: str, format_: str | None) -> None:
        super().__init__(meldung)
        self.code, self.meldung, self.format = code, meldung, format_


# ------------------------------------------------------------------ Lesen

@dataclass
class _Teil:
    kategorie: str
    memo: str
    betrag_text: str
    betrag: int = 0


@dataclass
class _Satz:
    nr: int  # laufende Nummer der Buchungssätze in der Datei (ab 1)
    abschnitt: str
    felder: dict[str, str] = field(default_factory=dict)
    teile: list[_Teil] = field(default_factory=list)
    datum: str = ""
    betrag: int = 0

    @property
    def ref(self) -> str:
        return f"Satz {self.nr}"


@dataclass
class _Datei:
    saetze: list[_Satz] = field(default_factory=list)
    kategorie_art: dict[str, str] = field(default_factory=dict)  # Pfad → aufwand/ertrag aus !Type:Cat
    konten_mit_buchungen: set[str] = field(default_factory=set)


def dekodieren(roh: bytes) -> str:
    """UTF-8 (mit oder ohne BOM), sonst Windows-1252 wie bei ALF-BanCo üblich; nicht belegte Bytes als Latin-1."""
    if roh.startswith(b"\xef\xbb\xbf"):
        roh = roh[3:]
    try:
        return roh.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return roh.decode("cp1252")
    except UnicodeDecodeError:
        return roh.decode("latin-1")


def _zerlegen(text: str) -> _Datei:
    """Zerlegt den QIF-Text in Buchungssätze; Format- und Strukturfehler als ``_Abbruch``."""
    zeilen = [z.rstrip() for z in text.splitlines()]
    erste = next((z.strip() for z in zeilen if z.strip()), "")
    if not erste.startswith("!"):
        raise _Abbruch("import_format_ungueltig", "Die Datei ist keine QIF-Datei (Kopfzeile „!Type:…“ fehlt).", None)
    datei = _Datei()
    abschnitt = ""
    konto: str | None = None
    feld_satz: dict[str, str] = {}
    teile: list[_Teil] = []
    nr = 0

    def satz_ende() -> None:
        nonlocal feld_satz, teile, nr, konto
        if not feld_satz and not teile:
            return
        if abschnitt == "account":
            konto = feld_satz.get("N", "").strip() or konto
        elif abschnitt == "cat":
            name = feld_satz.get("N", "").strip()
            if name:
                if "I" in feld_satz:
                    datei.kategorie_art[name] = "ertrag"
                elif "E" in feld_satz:
                    datei.kategorie_art[name] = "aufwand"
        elif abschnitt in _BUCHUNGSTYPEN or abschnitt in _UEBERSPRINGEN:
            nr += 1
            datei.saetze.append(_Satz(nr, abschnitt, feld_satz, teile))
            if abschnitt in _BUCHUNGSTYPEN:
                datei.konten_mit_buchungen.add(konto or "")
        feld_satz, teile = {}, []

    for zeile in zeilen:
        if not zeile.strip():
            continue
        if zeile.startswith("!"):
            satz_ende()
            kopf = zeile[1:].strip().lower()
            if kopf.startswith("type:"):
                abschnitt = kopf[5:].strip()
            elif kopf == "account":
                abschnitt = "account"
            elif kopf.startswith(("option:", "clear:")):
                continue
            else:
                abschnitt = "unbekannt"
            continue
        code, wert = zeile[0], zeile[1:]
        if code == "^":
            satz_ende()
        elif code == "S":
            teile.append(_Teil(wert.strip(), "", ""))
        elif code == "E" and teile:
            teile[-1].memo = wert
        elif code == "$" and teile:
            teile[-1].betrag_text = wert.strip()
        elif code in ("E", "I") and abschnitt == "cat":
            feld_satz[code] = wert
        elif code not in feld_satz:
            feld_satz[code] = wert
    satz_ende()
    if not datei.saetze and abschnitt == "" and not datei.kategorie_art:
        raise _Abbruch("import_format_ungueltig", "Die QIF-Datei enthält keinen bekannten Abschnitt.", FORMAT)
    if len(datei.konten_mit_buchungen) > 1:
        raise _Abbruch("import_format_ungueltig",
                       "Die Datei enthält Buchungen mehrerer Konten; bitte je Konto eine Datei exportieren.", FORMAT)
    return datei


_ZAHL = re.compile(r"^[+-]?[0-9.,]+$")


def dezimaltrenner(texte: list[str]) -> str:
    """Komma, sobald ein Betrag der Datei mit Komma und ein bis zwei Nachkommastellen endet, sonst Punkt."""
    return "," if any(re.search(r",\d{1,2}$", t.replace(" ", "")) for t in texte) else "."


def betrag_in_cent(text: str, trenner: str) -> int | None:
    """Betrag als ganze Cent; ``None`` bei ungültigem Text, mehr als zwei Nachkommastellen ≠ 0 oder zu groß."""
    t = text.replace(" ", "").replace(" ", "")
    if not t or not _ZAHL.match(t):
        return None
    vorzeichen = -1 if t.startswith("-") else 1
    t = t.lstrip("+-")
    if "," in t and "." in t:
        dez = "," if t.rfind(",") > t.rfind(".") else "."
    elif "," in t or "." in t:
        dez = trenner if trenner in t else ""
    else:
        dez = ""
    tausend = {",", "."} - {dez}
    for z in tausend:
        t = t.replace(z, "")
    ganz, _, rest = t.partition(dez) if dez else (t, "", "")
    if dez and (rest.count(dez) or not rest.isdigit()):
        return None
    if not ganz:
        ganz = "0"
    if not ganz.isdigit():
        return None
    rest = rest.rstrip("0") if len(rest) > 2 else rest
    if len(rest) > 2:
        return None
    cent = int(ganz) * 100 + int((rest + "00")[:2])
    if cent > BETRAG_MAX:
        return None
    return vorzeichen * cent


_DATUM_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DATUM_PUNKT = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$")
_DATUM_STRICH = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/|')(\d{2}|\d{4})$")


def _jahr(text: str, apostroph: bool) -> int:
    j = int(text)
    if len(text) == 4:
        return j
    if apostroph:
        return 2000 + j
    return 2000 + j if j < 70 else 1900 + j


def tag_zuerst(texte: list[str]) -> bool:
    """Datumsangaben mit „/“: Tag zuerst, wenn ein Wert an erster Stelle größer als 12 ist (sonst Monat zuerst)."""
    for t in texte:
        m = _DATUM_STRICH.match(t.replace(" ", ""))
        if m and int(m.group(1)) > 12:
            return True
    return False


def datum_iso(text: str, tag_vorn: bool) -> str | None:
    t = text.replace(" ", "")
    try:
        if m := _DATUM_ISO.match(t):
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        if m := _DATUM_PUNKT.match(t):
            return dt.date(_jahr(m.group(3), False), int(m.group(2)), int(m.group(1))).isoformat()
        if m := _DATUM_STRICH.match(t):
            a, b = int(m.group(1)), int(m.group(2))
            tag, monat = (a, b) if tag_vorn else (b, a)
            return dt.date(_jahr(m.group(3), "'" in t), monat, tag).isoformat()
    except ValueError:
        return None
    return None


def lesen(roh: bytes) -> tuple[_Datei, list[ImportMeldung]]:
    """Datei lesen und prüfen; Rückgabe der Datei und aller inhaltlichen Fehler."""
    if not roh:
        raise _Abbruch("import_datei_leer", "Die Datei ist leer.", None)
    datei = _zerlegen(dekodieren(roh))
    buchungen = [s for s in datei.saetze if s.abschnitt in _BUCHUNGSTYPEN]
    trenner = dezimaltrenner([s.felder.get("T", s.felder.get("U", "")) for s in buchungen]
                             + [t.betrag_text for s in buchungen for t in s.teile])
    tag_vorn = tag_zuerst([s.felder.get("D", "") for s in buchungen])
    fehler: list[ImportMeldung] = []

    def f(meldung: str, ref: str) -> None:
        fehler.append(ImportMeldung("import_inhalt_ungueltig", meldung, ref))

    for s in buchungen:
        d = datum_iso(s.felder.get("D", ""), tag_vorn)
        if not s.felder.get("D", "").strip():
            f("Das Buchungsdatum fehlt.", s.ref)
        elif d is None:
            f("Das Buchungsdatum ist ungültig.", s.ref)
        else:
            s.datum = d
        roh_betrag = s.felder.get("T", s.felder.get("U", "")).strip()
        b = betrag_in_cent(roh_betrag, trenner) if roh_betrag else None
        if not roh_betrag:
            f("Der Betrag fehlt.", s.ref)
        elif b is None:
            f("Der Betrag ist ungültig.", s.ref)
        else:
            s.betrag = b
        for t in s.teile:
            tb = betrag_in_cent(t.betrag_text, trenner) if t.betrag_text else None
            if tb is None:
                f("Der Betrag einer Aufteilung fehlt oder ist ungültig.", s.ref)
            else:
                t.betrag = tb
    return datei, fehler


# ---------------------------------------------------------------- Anwenden

@dataclass
class _Lauf:
    warnungen: list[ImportMeldung] = field(default_factory=list)
    gewarnt: set[tuple[str, str | None]] = field(default_factory=set)
    z: dict[str, int] = field(default_factory=lambda: {k: 0 for k in (
        "konten_neu", "konten_vorhanden", "kategorien_neu", "kategorien_vorhanden",
        "empfaenger_neu", "empfaenger_vorhanden", "tags_neu", "tags_vorhanden",
        "buchungen_neu", "buchungen_vorhanden", "buchungen_zusammengefuehrt",
        "buchungen_zur_pruefung", "buchungen_uebersprungen", "splits_neu")})

    def warn(self, code: str, referenz: str | None) -> None:
        if (code, referenz) not in self.gewarnt:  # je Element und Code genau eine Warnung
            self.gewarnt.add((code, referenz))
            self.warnungen.append(ImportMeldung(code, MELDUNGEN[code], referenz))


def kategorie_zerlegen(text: str) -> tuple[str, str]:
    """``Kategorie/Klasse`` → (Kategorie, Klasse); Umbuchungen ``[Konto]/Klasse`` ebenso (``/`` im Kontonamen
    bleibt erhalten)."""
    t = text.strip()
    if t.startswith("[") and "]" in t:
        ende = t.index("]") + 1
        rest = t[ende:].strip()
        return t[:ende], (rest[1:].strip() if rest.startswith("/") else "")
    kat, _, klasse = t.partition("/")
    return kat.strip(), klasse.strip()


def _pfad(kat: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in kat.split(":") if p.strip())


def _kategorie_arten(datei: _Datei, saetze: list[_Satz]) -> tuple[dict[str, str], set[str]]:
    """Art je Wurzelkategorie: Kennzeichen aus ``!Type:Cat`` (Wurzel, sonst erste gekennzeichnete Unterkategorie),
    sonst Summe der Gegenbeträge (Ausgaben positiv, D-125). Unterkategorien erben die Art ihrer Wurzel.
    Rückgabe: Arten und die Menge der Wurzeln, deren Art abgeleitet wurde."""
    arten: dict[str, str] = {}
    for name, art in datei.kategorie_art.items():
        p = _pfad(name)
        if len(p) == 1:
            arten[p[0]] = art
    for name, art in datei.kategorie_art.items():
        p = _pfad(name)
        if p:
            arten.setdefault(p[0], art)
    summe: dict[str, int] = {}
    for s in saetze:
        for kat, betrag in _gegenposten(s):
            p = () if kat.startswith("[") else _pfad(kat)
            if p:
                summe[p[0]] = summe.get(p[0], 0) + betrag
    abgeleitet = {w for w in summe if w not in arten}
    for w in abgeleitet:
        arten[w] = "ertrag" if summe[w] < 0 else "aufwand"
    return arten, abgeleitet


def _gegenposten(s: _Satz) -> list[tuple[str, int]]:
    """Kategorietext (ohne Klasse) und Betrag der Gegenseite (Soll positiv) je Teil der Buchung."""
    if s.teile:
        return [(kategorie_zerlegen(t.kategorie)[0], -t.betrag) for t in s.teile]
    return [(kategorie_zerlegen(s.felder.get("L", ""))[0], -s.betrag)]


class _Kategorien:
    """Zuordnung der Kategoriepfade zu Kontor-Kategorien (wie datenmodell.md 10.3, Kennung ``alf:kat:<Pfad>``)."""

    def __init__(self, con: sqlite3.Connection, lauf: _Lauf, arten: tuple[dict[str, str], set[str]],
                 max_konto: int) -> None:
        self.con, self.lauf, self.max_konto = con, lauf, max_konto
        self.arten, self.abgeleitet = arten
        self.ids: dict[tuple[str, ...], int] = {}
        self.vergeben: set[int] = set()

    def id_fuer(self, pfad: tuple[str, ...]) -> int:
        if pfad in self.ids:
            return self.ids[pfad]
        eltern = self.id_fuer(pfad[:-1]) if len(pfad) > 1 else None
        if eltern is not None:
            art = self.con.execute("SELECT art FROM konto WHERE id = ?", (eltern,)).fetchone()["art"]
        else:
            art = self.arten.get(pfad[0], "aufwand")
        ext = KAT_PRAEFIX + ":".join(pfad)
        r = self.con.execute("SELECT id FROM konto WHERE extern_id = ? AND art IN ('aufwand', 'ertrag')",
                             (ext,)).fetchone()
        treffer = r["id"] if r is not None else None
        if treffer is None:
            for k in self.con.execute(
                    "SELECT id FROM konto WHERE art = ? AND name = ? AND eltern_id IS ? AND id <= ?"
                    " AND (extern_id IS NULL OR (substr(extern_id, 1, 4) <> 'alf:'"
                    "      AND substr(extern_id, 1, 7) <> 'kontor:')) ORDER BY id",
                    (art, pfad[-1], eltern, self.max_konto)):
                if k["id"] not in self.vergeben:
                    treffer = k["id"]
                    break
            if treffer is not None:
                self.con.execute("UPDATE konto SET extern_id = ? WHERE id = ? AND extern_id IS NULL", (ext, treffer))
        if treffer is not None:
            self.vergeben.add(treffer)
            self.lauf.z["kategorien_vorhanden"] += 1
        else:
            treffer = self.con.execute(
                "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
                " VALUES (?, ?, ?, NULL, 0, NULL, '', ?)", (pfad[-1], art, eltern, ext)).lastrowid
            self.lauf.z["kategorien_neu"] += 1
            if eltern is None and pfad[0] in self.abgeleitet:
                self.lauf.warn("kategorieart_abgeleitet", pfad[0])
        self.ids[pfad] = treffer
        return treffer


@dataclass
class _Neu:
    satz: _Satz
    ext: str
    splits: list[dict]
    empfaenger_id: int | None
    empfaenger_name: str | None
    tag_ids: list[int]
    exakt: set[int] = field(default_factory=set)
    aehnlich: set[int] = field(default_factory=set)


class _Abbildung:
    """Gegenkonten, Empfänger und Tags eines Laufs."""

    def __init__(self, con: sqlite3.Connection, lauf: _Lauf, konto: dict, kategorien: _Kategorien) -> None:
        self.con, self.lauf, self.konto, self.kat = con, lauf, konto, kategorien
        self.empf: dict[str, int] = {}
        self.tags: dict[str, int] = {}

    def gegenkonto(self, kat: str, ref: str) -> int:
        if kat.startswith("[") and kat.endswith("]"):
            name = kat[1:-1].strip()
            if name == self.konto["name"]:
                return self._anfangssalden()
            r = self.con.execute(
                "SELECT id FROM konto WHERE name = ? AND art IN ('girokonto', 'sparkonto', 'kreditkonto')"
                " AND id <> ? ORDER BY id", (name, self.konto["id"])).fetchone()
            if r is not None:
                return r["id"]
            self.lauf.warn("umbuchung_konto_unbekannt", ref)
            return buch.unkategorisiert_id(self.con)
        pfad = _pfad(kat)
        return self.kat.id_fuer(pfad) if pfad else buch.unkategorisiert_id(self.con)

    def _anfangssalden(self) -> int:
        r = self.con.execute("SELECT id FROM konto WHERE extern_id = ?", (ANFANGSSALDEN,)).fetchone()
        if r is None:
            return self.con.execute(
                "INSERT INTO konto (name, art, eltern_id, iban, geschlossen, eroeffnet_am, notiz, extern_id)"
                " VALUES ('Anfangssalden', 'eigenkapital', NULL, NULL, 0, NULL, '', ?)", (ANFANGSSALDEN,)).lastrowid
        return r["id"]

    def empfaenger(self, name: str) -> int | None:
        if not name:
            return None
        if name not in self.empf:
            eid = buch.empfaenger_zu_name(self.con, name)
            if eid is not None:
                self.lauf.z["empfaenger_vorhanden"] += 1
            else:
                eid = self.con.execute("INSERT INTO empfaenger (name, extern_id) VALUES (?, NULL)", (name,)).lastrowid
                self.lauf.z["empfaenger_neu"] += 1
            self.empf[name] = eid
        return self.empf[name]

    def tag(self, name: str) -> int:
        cf = name.casefold()
        if cf not in self.tags:
            r = self.con.execute("SELECT id FROM tag WHERE name_cf = ?", (cf,)).fetchone()
            if r is not None:
                self.lauf.z["tags_vorhanden"] += 1
                self.tags[cf] = r["id"]
            else:
                self.tags[cf] = self.con.execute("INSERT INTO tag (name, name_cf, extern_id) VALUES (?, ?, NULL)",
                                                 (name, cf)).lastrowid
                self.lauf.z["tags_neu"] += 1
        return self.tags[cf]

    def splits(self, s: _Satz) -> tuple[list[dict], list[int]]:
        """Splits (Bestandskonto zuerst) und Tags einer Buchung."""
        splits = [{"konto_id": self.konto["id"], "betrag": s.betrag, "memo": ""}]
        tags: list[int] = []
        teile = s.teile or [_Teil(s.felder.get("L", ""), "", "", s.betrag)]
        for t in teile:
            kat, klasse = kategorie_zerlegen(t.kategorie)
            splits.append({"konto_id": self.gegenkonto(kat, s.ref), "betrag": -t.betrag, "memo": t.memo})
            if klasse and (tid := self.tag(klasse)) not in tags:
                tags.append(tid)
        rest = sum(x["betrag"] for x in splits)
        if rest:
            self.lauf.warn("split_differenz", s.ref)
            splits.append({"konto_id": buch.unkategorisiert_id(self.con), "betrag": -rest, "memo": ""})
        return splits, tags


def kennung(konto_id: int, s: _Satz, vorkommen: int) -> str:
    """Herkunftskennung einer Buchung: Konto, Inhalt des Satzes und laufende Nummer gleicher Sätze (D-124)."""
    inhalt = [s.datum, s.betrag, s.felder.get("P", "").strip(), s.felder.get("M", "").strip(),
              s.felder.get("L", "").strip(), s.felder.get("N", "").strip(),
              [[t.kategorie, t.memo.strip(), t.betrag] for t in s.teile], vorkommen]
    h = hashlib.sha256(json.dumps(inhalt, ensure_ascii=False).encode("utf-8")).hexdigest()[:32]
    return f"alf:{konto_id}:{h}"


def _bewerten(con: sqlite3.Connection, neue: list[_Neu], konto_id: int, max_buchung: int,
              belegt: set[int]) -> dict[int, int]:
    """Dublettenbewertung (datenmodell.md 10.4) gegen vorhandene Buchungen des Kontos; ``belegt`` sind Buchungen,
    die in diesem Lauf schon über ihre Kennung zugeordnet wurden (D-124). Ergebnis: Kandidat → Anzahl exakt."""
    for n in neue:
        b_datum = dt.date.fromisoformat(n.satz.datum)
        for c in con.execute(
                "SELECT b.id AS id, b.datum AS datum, e.name AS name FROM split s"
                " JOIN buchung b ON b.id = s.buchung_id LEFT JOIN empfaenger e ON e.id = b.empfaenger_id"
                " WHERE s.konto_id = ? AND s.betrag = ? AND b.id <= ?", (konto_id, n.satz.betrag, max_buchung)):
            if c["id"] in belegt:
                continue
            c_datum = dt.date.fromisoformat(c["datum"])
            if c_datum == b_datum and passend(n.empfaenger_name, c["name"]):
                n.exakt.add(c["id"])
            elif abs((c_datum - b_datum).days) <= 3:
                n.aehnlich.add(c["id"])
        n.aehnlich -= n.exakt
    zaehler: dict[int, int] = {}
    for n in neue:
        for c in n.exakt:
            zaehler[c] = zaehler.get(c, 0) + 1
    return zaehler


def _anwenden(con: sqlite3.Connection, datei: _Datei, konto: dict, lauf: _Lauf, roh: bytes,
              dateiname: str | None, jetzt: str) -> int:
    max_konto = con.execute("SELECT COALESCE(MAX(id), 0) AS m FROM konto").fetchone()["m"]
    max_buchung = con.execute("SELECT COALESCE(MAX(id), 0) AS m FROM buchung").fetchone()["m"]
    saetze = []
    for s in datei.saetze:
        if s.abschnitt in _BUCHUNGSTYPEN:
            saetze.append(s)
        else:
            lauf.z["buchungen_uebersprungen"] += 1
            lauf.warn("buchung_uebersprungen", s.ref)
    abb = _Abbildung(con, lauf, konto, _Kategorien(con, lauf, _kategorie_arten(datei, saetze), max_konto))
    # Alle Kategorien, Empfänger und Tags der Datei genau einmal zuordnen (auch bei schon vorhandenen Buchungen),
    # damit die Zählungen wie beim KMyMoney-Import jedes Element der Datei erfassen.
    for s in saetze:
        abb.empfaenger(s.felder.get("P", "").strip())
        for t in s.teile or [_Teil(s.felder.get("L", ""), "", "")]:
            kat, klasse = kategorie_zerlegen(t.kategorie)
            if (pfad := _pfad(kat)) and not kat.startswith("["):
                abb.kat.id_fuer(pfad)
            if klasse:
                abb.tag(klasse)
    vorkommen: dict[str, int] = {}
    neue: list[_Neu] = []
    belegt: set[int] = set()
    for s in saetze:
        basis = kennung(konto["id"], s, 0)
        vorkommen[basis] = vorkommen.get(basis, 0) + 1
        ext = kennung(konto["id"], s, vorkommen[basis] - 1)
        r = con.execute("SELECT buchung_id FROM buchung_extern WHERE extern_id = ?", (ext,)).fetchone()
        if r is not None:
            lauf.z["buchungen_vorhanden"] += 1
            belegt.add(r["buchung_id"])
            continue
        name = s.felder.get("P", "").strip() or None
        splits, tags = abb.splits(s)
        neue.append(_Neu(s, ext, splits, abb.empfaenger(name or ""), name, tags))
    exakt_zaehler = _bewerten(con, neue, konto["id"], max_buchung, belegt)
    for n in neue:
        if len(n.exakt) == 1 and exakt_zaehler[next(iter(n.exakt))] == 1:
            con.execute("INSERT INTO buchung_extern (buchung_id, extern_id) VALUES (?, ?)", (next(iter(n.exakt)), n.ext))
            lauf.z["buchungen_zusammengefuehrt"] += 1
            continue
        bid = buch.buchung_einfuegen(con, n.satz.datum, n.empfaenger_id, n.satz.felder.get("M", ""), "importiert",
                                     n.splits, n.tag_ids, [n.ext])
        lauf.z["buchungen_neu"] += 1
        lauf.z["splits_neu"] += len(n.splits)
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
        ("alfbanco", dateiname, hashlib.sha256(roh).hexdigest(), jetzt)).lastrowid


def zielkonto(con: sqlite3.Connection, konto_id: int) -> dict:
    """Kontor-Konto, in das importiert wird: muss existieren und ein Bestandskonto sein (422 sonst)."""
    r = buch.konto_zeile(con, konto_id)
    if r is None:
        raise ApiFehler(422, "referenz_unbekannt", "Das Konto existiert nicht.", {"feld": "konto_id"})
    if r["art"] not in BESTAND:
        raise ApiFehler(422, "konto_ungueltig", "Importiert werden kann nur in ein Bestandskonto.",
                        {"feld": "konto_id"})
    return buch.konto_dict(r)


def _fehlschlag(format_: str | None, fehler: list[ImportMeldung]) -> ImportErgebnis:
    return ImportErgebnis(erfolgreich=False, format=format_, fehler=tuple(fehler), import_id=None)


def importiere_bytes(con: sqlite3.Connection, roh: bytes, dateiname: str | None, konto_id: int,
                     zeitpunkt: str | None = None) -> ImportErgebnis:
    """Kern des Imports auf einer offenen Verbindung (eine protokollierte Transaktion)."""
    konto = zielkonto(con, konto_id)
    try:
        datei, fehler = lesen(roh)
    except _Abbruch as a:
        return _fehlschlag(a.format, [ImportMeldung(a.code, a.meldung, None)])
    if fehler:
        return _fehlschlag(FORMAT, fehler)
    lauf = _Lauf()
    jetzt = zeitpunkt or db.jetzt_utc()
    with protokoll.protokolliert(con, "import", "import_alfbanco", jetzt) as k:
        import_id = _anwenden(con, datei, konto, lauf, roh, dateiname, jetzt)
        k.gruppe = f"import:{import_id}"
        ergebnis = ImportErgebnis(erfolgreich=True, format=FORMAT, warnungen=tuple(lauf.warnungen),
                                  fehler=(), import_id=import_id, **lauf.z)
        con.execute("UPDATE importvorgang SET ergebnis = ? WHERE id = ?",
                    (json.dumps(ergebnis.als_dict(), ensure_ascii=False), import_id))
    return ergebnis


def importiere_alfbanco(config, quelle: str | os.PathLike[str] | bytes, *, konto_id: int,
                        dateiname: str | None = None) -> ImportErgebnis:
    """Importiert einen QIF-Export aus ALF-BanCo in ``config.aktive_datenbank``, Konto ``konto_id``.

    Unbekanntes Konto oder kein Bestandskonto → ``ValueError``; sonst wie ``importiere_gnucash``."""
    if isinstance(quelle, (bytes, bytearray, memoryview)):
        roh = bytes(quelle)
    elif isinstance(quelle, (str, os.PathLike)):
        pfad = pathlib.Path(quelle)
        roh = pfad.read_bytes()
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
        return importiere_bytes(con, roh, dateiname, konto_id, zeitpunkt)
    except ApiFehler as e:
        raise ValueError(e.meldung) from None
    finally:
        con.close()


__all__ = ["importiere_alfbanco", "importiere_bytes", "lesen"]
