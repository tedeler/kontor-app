"""Datensicherung und Wiederherstellung (Meilenstein 9, sicherung.md, protokoll.md 10, python-api.md 11).

Eine Sicherung ist eine ZIP-Datei mit genau ``manifest.json`` und ``kontor.sqlite``. Die SQLite-Datei hat ein
eigenes, schmales Schema (``SPALTEN``, Version ``SCHEMAVERSION``): je Tabelle des Buchbestands genau die
fachlichen Spalten, dazu alle gemerkten Umsatzkennungen, der Zustand je Bankkonto und die ID-Zähler. Sie wird
vollständig im Arbeitsspeicher erzeugt (``sqlite3.Connection.serialize``) und nie auf dem Server abgelegt.

Einspielen:

1. Die hochgeladene Datei wird in der festen Reihenfolge von sicherung.md 5.1 geprüft. Die Datenbank wird nur
   im Arbeitsspeicher geöffnet (``deserialize``), ihr Schema muss exakt ``SPALTEN`` entsprechen (keine Views,
   Trigger, zusätzlichen Tabellen oder Spalten); gelesen werden nur bekannte Tabellen und Spalten.
2. Die gelesenen Zeilen werden in eine leere Datenbank mit dem vollständigen App-Schema im Arbeitsspeicher
   geladen. Dort werden Eindeutigkeit, Bezüge und Invarianten geprüft und die Protokollformen mit denselben
   Funktionen berechnet, die auch die REST-Schnittstelle verwendet; daraus folgen Anzahl und Inhaltsprüfsumme.
3. Das eigentliche Einspielen läuft in ``protokoll.protokolliert`` (eine Transaktion, eine Änderung
   ``sicherung_einspielen`` mit der Nettowirkung). Gemerkte Kennungen laufen durch die Protokoll-Trigger, der
   Zustand je Bankkonto wird vorher/nachher in ``sicherung_zustand`` vermerkt (für Rückgängig, protokoll.md 10.2).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import sqlite3
import zipfile
import zlib
from typing import Any

from . import __version__, buch, db, protokoll, regeln, vorlagen
from .config import KontorConfig
from .text import ekey
from .validierung import ApiFehler, datum_gueltig

FORMAT = "kontor-sicherung"
FORMATVERSION = 1
SCHEMAVERSION = 1
OBJEKTE = protokoll.OBJEKTE
NAMEN = ("manifest.json", "kontor.sqlite")
MAX_ENTPACKT = 4 * 1024 ** 3  # Schutz gegen ZIP-Bomben (sicherung.md 8: mindestens 1 GiB)
MAX_MANIFEST = 1024 ** 2

# Objektarten je Schemaversion der Sicherungsdatei (für spätere Meilensteine, sicherung.md 2.3, 3.4).
OBJEKTE_JE_VERSION = {1: OBJEKTE}

# Tabellen der Sicherungsdatei (Schemaversion 1): Name → [(Spalte, Typ, nullbar)]. Die Namen entsprechen den
# Tabellen der App-Datenbank; ``id_zaehler`` hält die höchste je vergebene ID je Objektart (auch Splits).
SPALTEN: dict[str, list[tuple[str, str, bool]]] = {
    "konto": [("id", "int", False), ("name", "str", False), ("art", "str", False), ("eltern_id", "int", True),
              ("iban", "str", True), ("geschlossen", "bool", False), ("eroeffnet_am", "str", True),
              ("notiz", "str", False), ("extern_id", "str", True)],
    "empfaenger": [("id", "int", False), ("name", "str", False), ("extern_id", "str", True),
                   ("standardkategorie_id", "int", True)],
    "empfaenger_alias": [("empfaenger_id", "int", False), ("alias", "str", False)],
    "tag": [("id", "int", False), ("name", "str", False), ("extern_id", "str", True)],
    "buchung": [("id", "int", False), ("datum", "str", False), ("empfaenger_id", "int", True),
                ("verwendungszweck", "str", False), ("status", "str", False), ("gegen_iban", "str", True)],
    "split": [("id", "int", False), ("buchung_id", "int", False), ("position", "int", False),
              ("konto_id", "int", False), ("betrag", "int", False), ("memo", "str", False),
              ("abstimmung_id", "int", True)],
    "buchung_tag": [("buchung_id", "int", False), ("tag_id", "int", False)],
    "buchung_extern": [("buchung_id", "int", False), ("extern_id", "str", False)],
    "vorschlag": [("buchung_id", "int", False), ("kategorie_id", "int", False), ("regel_id", "int", True),
                  ("quelle", "str", False), ("vorher_konto_id", "int", False), ("sicherheit", "int", True)],
    "regel": [("id", "int", False), ("name", "str", False), ("aktiv", "bool", False), ("prioritaet", "int", False),
              ("kategorie_id", "int", False), ("bedingungen", "str", False)],
    "dublettenverdacht": [("id", "int", False), ("buchung_id", "int", False), ("grund", "str", False),
                          ("status", "str", False), ("erstellt_am", "str", False)],
    "verdacht_kandidat": [("verdacht_id", "int", False), ("buchung_id", "int", False)],
    "abstimmung": [("id", "int", False), ("konto_id", "int", False), ("stichtag", "str", False),
                   ("saldo", "int", False), ("erstellt_am", "str", False)],
    "vorlage": [("id", "int", False), ("name", "str", False), ("aktiv", "bool", False), ("prioritaet", "int", False),
                ("bedingungen", "str", False), ("teile", "str", False)],
    "sync_kennung": [("kennung", "str", False)],
    "sync_konto_zustand": [("iban", "str", False), ("konto_id", "int", False), ("letzter_abruf_bis", "str", True),
                           ("letzter_erfolg_am", "str", True), ("entscheidung", "str", True),
                           ("entscheidung_buchungen", "str", True)],
    "id_zaehler": [("objekt", "str", False), ("hoechste_id", "int", False)],
}
_ORDNUNG = {
    "split": "buchung_id, position, id", "empfaenger_alias": "empfaenger_id, alias",
    "buchung_tag": "buchung_id, tag_id", "buchung_extern": "buchung_id, extern_id",
    "vorschlag": "buchung_id", "verdacht_kandidat": "verdacht_id, buchung_id", "sync_kennung": "kennung",
    "sync_konto_zustand": "iban", "id_zaehler": "objekt",
}
_SCHLUESSEL = {"empfaenger_alias": "PRIMARY KEY (empfaenger_id, alias)", "buchung_tag": "PRIMARY KEY (buchung_id, tag_id)",
               "buchung_extern": "PRIMARY KEY (extern_id)", "verdacht_kandidat": "PRIMARY KEY (verdacht_id, buchung_id)",
               "vorschlag": "PRIMARY KEY (buchung_id)", "sync_kennung": "PRIMARY KEY (kennung)",
               "sync_konto_zustand": "PRIMARY KEY (iban)", "id_zaehler": "PRIMARY KEY (objekt)"}
# Buchbestand (ohne Kennungen, Bankkonto-Zustand, Zähler) in Einfügereihenfolge.
BUCH_TABELLEN = ("konto", "empfaenger", "empfaenger_alias", "tag", "regel", "abstimmung", "buchung", "split",
                 "buchung_tag", "buchung_extern", "vorschlag", "dublettenverdacht", "verdacht_kandidat", "vorlage")
# Objektart (bzw. "split") → Tabelle der App-Datenbank mit AUTOINCREMENT-Zähler.
ZAEHLER = {"konto": "konto", "empfaenger": "empfaenger", "tag": "tag", "buchung": "buchung", "split": "split",
           "regel": "regel", "verdacht": "dublettenverdacht", "abstimmung": "abstimmung", "vorlage": "vorlage"}

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ZEIT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
MANIFEST_FELDER = ("format", "formatversion", "erstellt", "modus", "app_version", "schemaversion", "anzahl",
                   "inhalt_sha256", "datenbank_sha256")


def _ddl() -> str:
    teile = []
    for tabelle, spalten in SPALTEN.items():
        defs = []
        for name, typ, nullbar in spalten:
            sql_typ = "TEXT" if typ == "str" else "INTEGER"
            if name == "id" and tabelle not in _SCHLUESSEL:
                defs.append("id INTEGER PRIMARY KEY")
                continue
            defs.append(f"{name} {sql_typ}{'' if nullbar else ' NOT NULL'}")
        if tabelle in _SCHLUESSEL:
            defs.append(_SCHLUESSEL[tabelle])
        teile.append(f"CREATE TABLE {tabelle} ({', '.join(defs)});")
    return "\n".join(teile)


def _zeit(z: dt.datetime) -> str:
    return z.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def inhalt_sha256(formen: dict[str, dict[int, dict]], arten) -> str:
    """sicherung.md 3.3: SHA-256 der kanonischen JSON-Form aller Protokollformen je Objektart."""
    inhalt = {o: [formen.get(o, {})[i] for i in sorted(formen.get(o, {}))] for o in arten}
    text = json.dumps(inhalt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def alle_formen(con) -> dict[str, dict[int, dict]]:
    """Protokollformen des gesamten Buchbestands (je Objektart: ID → Form)."""
    tabellen = {"konto": "konto", "empfaenger": "empfaenger", "tag": "tag", "buchung": "buchung", "regel": "regel",
                "verdacht": "dublettenverdacht", "abstimmung": "abstimmung", "vorlage": "vorlage"}
    aus = {}
    for o in OBJEKTE:
        ids = [r[0] for r in con.execute(f"SELECT id FROM {tabellen[o]} ORDER BY id")]
        aus[o] = protokoll.formen(con, o, ids)
    return aus


# ================================================================ Erstellen


def _zaehler_lesen(con) -> dict[str, int]:
    seq = {r[0]: r[1] for r in con.execute("SELECT name, seq FROM sqlite_sequence")}
    aus = {}
    for o, tabelle in ZAEHLER.items():
        hoechste = con.execute(f"SELECT MAX(id) FROM {tabelle}").fetchone()[0] or 0
        aus[o] = max(int(seq.get(tabelle) or 0), int(hoechste))
    return aus


def _erstellen(pfad, modus: str, erstellt: dt.datetime) -> tuple[bytes, str]:
    con = db.verbinde(pfad)
    ziel = sqlite3.connect(":memory:", isolation_level=None)
    try:
        ziel.executescript(_ddl())
        ziel.execute("BEGIN")
        con.execute("BEGIN")  # eine Lesetransaktion: konsistenter Schnappschuss (sicherung.md 4)
        try:
            for tabelle, spalten in SPALTEN.items():
                if tabelle == "id_zaehler":
                    continue
                namen = [s[0] for s in spalten]
                ordnung = _ORDNUNG.get(tabelle, "id")
                ziel.executemany(
                    f"INSERT INTO {tabelle} ({', '.join(namen)}) VALUES ({', '.join('?' * len(namen))})",
                    (tuple(r) for r in con.execute(f"SELECT {', '.join(namen)} FROM {tabelle} ORDER BY {ordnung}")))
            ziel.executemany("INSERT INTO id_zaehler (objekt, hoechste_id) VALUES (?, ?)",
                             sorted(_zaehler_lesen(con).items()))
            formen = alle_formen(con)
        finally:
            con.execute("ROLLBACK")
        ziel.execute("COMMIT")
        ziel.execute("VACUUM")  # keine freien Seiten, keine Reste (sicherung.md 2.2)
        daten = ziel.serialize()
    finally:
        ziel.close()
        con.close()
    manifest = {
        "format": FORMAT,
        "formatversion": FORMATVERSION,
        "erstellt": _zeit(erstellt),
        "modus": modus,
        "app_version": __version__,
        "schemaversion": SCHEMAVERSION,
        "anzahl": {o: len(formen[o]) for o in OBJEKTE},
        "inhalt_sha256": inhalt_sha256(formen, OBJEKTE),
        "datenbank_sha256": hashlib.sha256(daten).hexdigest(),
    }
    zeit = erstellt.astimezone(dt.timezone.utc)
    stempel = (zeit.year, zeit.month, zeit.day, zeit.hour, zeit.minute, zeit.second)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, inhalt in (("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")),
                             ("kontor.sqlite", daten)):
            info = zipfile.ZipInfo(name, date_time=stempel)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, inhalt)
    name = f"kontor-sicherung-{modus}-{zeit.strftime('%Y%m%dT%H%M%SZ')}.zip"
    return puffer.getvalue(), name


def _schema_sicherstellen(pfad) -> None:
    """Legt die Datenbank samt Schema an bzw. migriert sie – nur, wenn nötig (python-api.md 11.1)."""
    import pathlib

    p = pathlib.Path(pfad)
    if p.exists():
        con = db.verbinde(p)
        try:
            r = con.execute("SELECT wert FROM meta WHERE schluessel = 'schema_version'").fetchone()
            if r is not None and r["wert"] == str(db.SCHEMA_VERSION):
                return
        except sqlite3.DatabaseError:
            pass
        finally:
            con.close()
    db.schema_anlegen(p)


def erstelle_sicherung(config: KontorConfig) -> bytes:
    """python-api.md 11.1: Bytes einer Sicherung von ``config.aktive_datenbank``; liest nur."""
    from .sync import SyncDienst

    _schema_sicherstellen(config.aktive_datenbank)
    erstellt = SyncDienst(config).jetzt()  # Systemzeit bzw. mock_heute 12:00:00Z
    daten, _ = _erstellen(config.aktive_datenbank, "mock" if config.mock_modus else "echt", erstellt)
    return daten


def erstellen(pfad, modus: str, erstellt: dt.datetime) -> tuple[bytes, str]:
    """Für ``GET /api/sicherung``: (Bytes, Dateiname)."""
    return _erstellen(pfad, modus, erstellt)


# ================================================================ Prüfen


class _Ungueltig(Exception):
    def __init__(self, grund: str, meldung: str) -> None:
        super().__init__(grund)
        self.grund = grund
        self.meldung = meldung


def _ungueltig(grund: str, meldung: str):
    raise _Ungueltig(grund, meldung)


def _zip_lesen(roh: bytes) -> tuple[bytes, bytes]:
    if len(roh) == 0:
        _ungueltig("datei_leer", "Die Datei ist leer.")
    try:
        z = zipfile.ZipFile(io.BytesIO(roh))
        infos = z.infolist()
    except Exception:  # noqa: BLE001 – jede unlesbare Datei
        _ungueltig("kein_zip", "Die Datei ist keine lesbare ZIP-Datei.")
    with z:
        namen = [i.filename for i in infos]
        if (len(infos) != 2 or sorted(namen) != sorted(NAMEN)
                or any(i.is_dir() or i.flag_bits & 0x1 for i in infos)
                or any("/" in n or "\\" in n or ".." in n for n in namen)
                or any(i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for i in infos)):
            _ungueltig("zip_inhalt", "Die ZIP-Datei muss genau manifest.json und kontor.sqlite enthalten.")
        if sum(i.file_size for i in infos) > MAX_ENTPACKT:
            _ungueltig("zip_inhalt", "Die ZIP-Datei ist entpackt zu groß.")
        teile = {}
        gesamt = 0
        for info in infos:
            grenze = MAX_MANIFEST if info.filename == "manifest.json" else MAX_ENTPACKT
            puffer = bytearray()
            try:
                with z.open(info) as f:
                    while True:
                        stueck = f.read(1024 * 1024)
                        if not stueck:
                            break
                        puffer += stueck
                        gesamt += len(stueck)
                        if len(puffer) > info.file_size or len(puffer) > grenze or gesamt > MAX_ENTPACKT:
                            _ungueltig("zip_inhalt", "Ein Eintrag der ZIP-Datei ist entpackt zu groß.")
            except _Ungueltig:
                raise
            except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError):
                _ungueltig("kein_zip", "Die ZIP-Datei ist beschädigt.")
            teile[info.filename] = bytes(puffer)
    return teile["manifest.json"], teile["kontor.sqlite"]


def _ganz(v: Any, minimum: int) -> bool:
    return type(v) is int and v >= minimum


def _manifest_pruefen(roh: bytes) -> dict:
    def schlecht(meldung: str):
        _ungueltig("manifest_ungueltig", f"manifest.json ist ungültig: {meldung}")

    try:
        m = json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        schlecht("kein UTF-8-JSON.")
    if not isinstance(m, dict):
        schlecht("kein JSON-Objekt.")
    if set(m) != set(MANIFEST_FELDER):
        fehlend, fremd = set(MANIFEST_FELDER) - set(m), set(m) - set(MANIFEST_FELDER)
        schlecht("Feld fehlt." if fehlend else f"unbekanntes Feld ({len(fremd)}).")
    if not isinstance(m["format"], str):
        schlecht("format")
    if not _ganz(m["formatversion"], 1):
        schlecht("formatversion")
    if not isinstance(m["erstellt"], str) or not _ZEIT.match(m["erstellt"]):
        schlecht("erstellt")
    try:
        dt.datetime.strptime(m["erstellt"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        schlecht("erstellt")
    if m["modus"] not in ("echt", "mock"):
        schlecht("modus")
    if not isinstance(m["app_version"], str) or not m["app_version"]:
        schlecht("app_version")
    if not _ganz(m["schemaversion"], 1):
        schlecht("schemaversion")
    a = m["anzahl"]
    if not isinstance(a, dict) or not all(isinstance(k, str) and _ganz(v, 0) for k, v in a.items()):
        schlecht("anzahl")
    if m["formatversion"] <= FORMATVERSION and m["schemaversion"] <= SCHEMAVERSION:
        # Schlüssel nur für unterstützte Versionen prüfbar (spätere Versionen: version_nicht_unterstuetzt)
        bekannt = OBJEKTE_JE_VERSION[m["schemaversion"]]
        if not set(a) <= set(bekannt) or (m["schemaversion"] == SCHEMAVERSION and set(a) != set(bekannt)):
            schlecht("anzahl")
    for feld in ("inhalt_sha256", "datenbank_sha256"):
        if not isinstance(m[feld], str) or not _SHA.match(m[feld]):
            schlecht(feld)
    return m


def _header_pruefen(daten: bytes) -> None:
    if len(daten) < 100 or daten[:16] != b"SQLite format 3\x00":
        _ungueltig("datenbank_ungueltig", "kontor.sqlite ist keine SQLite-Datenbank.")
    seite = int.from_bytes(daten[16:18], "big")
    seite = 65536 if seite == 1 else seite
    if seite < 512 or seite & (seite - 1) or len(daten) % seite:
        _ungueltig("datenbank_ungueltig", "kontor.sqlite ist beschädigt.")
    if daten[92:96] == daten[24:28]:
        seiten = int.from_bytes(daten[28:32], "big")
        if seiten * seite != len(daten):
            _ungueltig("datenbank_ungueltig", "kontor.sqlite ist unvollständig.")


def _oeffnen(daten: bytes) -> sqlite3.Connection:
    """Öffnet die Datenbank der Sicherung nur im Arbeitsspeicher; prüft integrity_check."""
    _header_pruefen(daten)
    con = sqlite3.connect(":memory:", isolation_level=None)
    try:
        con.execute("PRAGMA trusted_schema = OFF")
        con.deserialize(daten)
        con.execute("PRAGMA trusted_schema = OFF")
        con.execute("PRAGMA query_only = ON")
        ergebnis = [r[0] for r in con.execute("PRAGMA integrity_check")]
    except (sqlite3.DatabaseError, OverflowError, MemoryError):
        con.close()
        _ungueltig("datenbank_ungueltig", "kontor.sqlite ist keine gültige SQLite-Datenbank.")
    if ergebnis != ["ok"]:
        con.close()
        _ungueltig("datenbank_ungueltig", "kontor.sqlite ist beschädigt (integrity_check).")
    return con


def _schema_pruefen(con: sqlite3.Connection, schemaversion: int) -> None:
    def fremd(meldung: str):
        _ungueltig("datenbank_fremd", f"kontor.sqlite passt nicht zum erwarteten Schema: {meldung}")

    erwartet = SPALTEN  # Schemaversion 1 (ältere Versionen gibt es noch nicht)
    tabellen = {}
    for typ, name, sql in con.execute("SELECT type, name, sql FROM sqlite_master"):
        if typ not in ("table", "index"):
            fremd(f"unerlaubtes Objekt ({typ}).")
        if typ == "table" and not name.startswith("sqlite_"):
            if not isinstance(sql, str) or not re.match(r"\s*CREATE\s+TABLE\b", sql, re.IGNORECASE):
                fremd("unerlaubte Tabellenart.")
            tabellen[name] = sql
        elif typ == "table" and name != "sqlite_sequence":
            fremd("unerlaubte Systemtabelle.")
    if set(tabellen) != set(erwartet):
        fremd("fehlende oder zusätzliche Tabellen.")
    for tabelle, spalten in erwartet.items():
        info = con.execute(f'PRAGMA table_xinfo("{tabelle}")').fetchall()
        namen = [r[1] for r in info]
        if sorted(namen) != sorted(s[0] for s in spalten) or any(r[6] != 0 for r in info):
            fremd(f"Spalten der Tabelle {tabelle}.")


def _zeilen_lesen(con: sqlite3.Connection) -> dict[str, list[tuple]]:
    aus: dict[str, list[tuple]] = {}
    for tabelle, spalten in SPALTEN.items():
        namen = [s[0] for s in spalten]
        zeilen = []
        for r in con.execute(f'SELECT {", ".join(namen)} FROM "{tabelle}" ORDER BY rowid'):
            for wert, (name, typ, nullbar) in zip(r, spalten):
                if wert is None:
                    ok = nullbar
                elif typ == "int":
                    ok = type(wert) is int
                elif typ == "bool":
                    ok = type(wert) is int and wert in (0, 1)
                else:
                    ok = type(wert) is str
                if not ok:
                    _ungueltig("inhalt_ungueltig", f"Ungültiger Wert in {tabelle}.{name}.")
            zeilen.append(tuple(r))
        aus[tabelle] = zeilen
    return aus


def laden(con, zeilen: dict[str, list[tuple]]) -> None:
    """Fügt den Buchbestand aus den Zeilen einer Sicherung in die (leeren) Tabellen von ``con`` ein."""
    for tabelle in BUCH_TABELLEN:
        namen = [s[0] for s in SPALTEN[tabelle]]
        werte = zeilen[tabelle]
        if tabelle == "tag":
            namen = namen + ["name_cf"]
            werte = [r + (r[1].casefold(),) for r in werte]
        elif tabelle == "empfaenger_alias":
            namen = namen + ["ekey"]
            werte = [r + (ekey(r[1]),) for r in werte]
        con.executemany(f"INSERT INTO {tabelle} ({', '.join(namen)}) VALUES ({', '.join('?' * len(namen))})",
                        werte)


def _inhalt_pruefen(zeilen: dict[str, list[tuple]]) -> dict[str, dict[int, dict]]:
    """Lädt den Buchbestand in eine leere App-Datenbank im Arbeitsspeicher, prüft Regeln und liefert die Formen."""
    def schlecht(meldung: str):
        _ungueltig("inhalt_ungueltig", f"Der Inhalt der Sicherung ist ungültig: {meldung}")

    def spalte(tabelle: str, name: str) -> int:
        return [s[0] for s in SPALTEN[tabelle]].index(name)

    # Datumswerte und Zeitstempel
    for tabelle, name, art, nullbar in (("konto", "eroeffnet_am", "datum", True), ("buchung", "datum", "datum", False),
                                        ("abstimmung", "stichtag", "datum", False),
                                        ("abstimmung", "erstellt_am", "zeit", False),
                                        ("dublettenverdacht", "erstellt_am", "zeit", False),
                                        ("sync_konto_zustand", "letzter_abruf_bis", "datum", True),
                                        ("sync_konto_zustand", "letzter_erfolg_am", "zeit", True)):
        i = spalte(tabelle, name)
        for r in zeilen[tabelle]:
            w = r[i]
            if w is None and nullbar:
                continue
            if art == "datum" and not datum_gueltig(w):
                schlecht(f"{tabelle}.{name}")
            if art == "zeit" and not (isinstance(w, str) and _ZEIT.match(w)):
                schlecht(f"{tabelle}.{name}")
    for r in zeilen["sync_konto_zustand"]:
        if r[4] not in (None, "wiederherstellen", "ignorieren") or r[5] not in (None, "alle", "nur_neue"):
            schlecht("Entscheidung je Bankkonto")
    objekte = {o for o, _ in zeilen["id_zaehler"]}
    if len(objekte) != len(zeilen["id_zaehler"]) or not objekte <= set(ZAEHLER) or any(
            n < 0 for _, n in zeilen["id_zaehler"]):
        schlecht("ID-Zähler")
    if any(not k for (k,) in zeilen["sync_kennung"]):
        schlecht("Umsatzkennung")

    mem = db.verbinde(":memory:")  # type: ignore[arg-type]
    try:
        mem.executescript(db.SCHEMA)
        db._migrieren(mem)
        mem.execute("PRAGMA foreign_keys = OFF")
        try:
            mem.execute("BEGIN")
            laden(mem, zeilen)
            mem.executemany("INSERT INTO sync_kennung (kennung) VALUES (?)", zeilen["sync_kennung"])
            mem.executemany("INSERT INTO sync_konto_zustand (iban, konto_id, letzter_abruf_bis, letzter_erfolg_am,"
                            " entscheidung, entscheidung_buchungen) VALUES (?, ?, ?, ?, ?, ?)",
                            zeilen["sync_konto_zustand"])
            mem.execute("COMMIT")
        except sqlite3.DatabaseError:
            schlecht("Eindeutigkeits- oder Wertebereichsregel verletzt.")
        if mem.execute("PRAGMA foreign_key_check").fetchone() is not None:
            schlecht("Bezug auf ein nicht vorhandenes Objekt.")
        if mem.execute("SELECT 1 FROM buchung b WHERE (SELECT COUNT(*) FROM split s WHERE s.buchung_id = b.id) < 2"
                       " OR (SELECT COALESCE(SUM(betrag), 0) FROM split s WHERE s.buchung_id = b.id) <> 0"
                       " LIMIT 1").fetchone():
            schlecht("Buchung mit weniger als zwei Splits oder Summe ungleich 0.")
        for r in mem.execute("SELECT * FROM regel").fetchall():
            try:
                bed = json.loads(r["bedingungen"])
                regeln.regel_koerper(json.dumps({"name": r["name"], "aktiv": bool(r["aktiv"]),
                                                 "prioritaet": r["prioritaet"], "kategorie_id": r["kategorie_id"],
                                                 "bedingungen": bed}).encode(), True)
            except (ValueError, ApiFehler):
                schlecht("Regel")
        for r in mem.execute("SELECT * FROM vorlage").fetchall():
            try:
                vorlagen.vorlage_koerper(json.dumps({"name": r["name"], "aktiv": bool(r["aktiv"]),
                                                     "prioritaet": r["prioritaet"],
                                                     "bedingungen": json.loads(r["bedingungen"]),
                                                     "teile": json.loads(r["teile"])}).encode(), True)
            except (ValueError, ApiFehler):
                schlecht("Split-Vorlage")
        try:
            protokoll.bezuege_pruefen(mem)
        except ApiFehler:
            schlecht("Bezug auf ein nicht vorhandenes Objekt.")
        try:
            return alle_formen(mem)
        except (ValueError, KeyError, TypeError, sqlite3.DatabaseError):
            schlecht("Objekt nicht lesbar.")
    finally:
        mem.close()


class Sicherung:
    """Geprüfter Inhalt einer Sicherungsdatei."""

    def __init__(self, manifest: dict, zeilen: dict[str, list[tuple]], formen: dict[str, dict[int, dict]]) -> None:
        self.manifest = manifest
        self.zeilen = zeilen
        self.formen = formen

    @property
    def arten(self) -> tuple[str, ...]:
        return tuple(o for o in OBJEKTE if o in self.manifest["anzahl"])


def pruefen(roh: bytes) -> Sicherung:
    """sicherung.md 5.1 Schritt 2; wirft ApiFehler 422 ``sicherung_ungueltig`` mit ``details.grund``."""
    try:
        manifest_roh, daten = _zip_lesen(roh)
        m = _manifest_pruefen(manifest_roh)
        if m["format"] != FORMAT:
            _ungueltig("format_unbekannt", "Die Datei ist keine Kontor-Sicherung.")
        if m["formatversion"] > FORMATVERSION or m["schemaversion"] > SCHEMAVERSION:
            _ungueltig("version_nicht_unterstuetzt",
                       "Die Sicherung stammt von einer neueren Kontor-Version und wird nicht unterstützt.")
        if hashlib.sha256(daten).hexdigest() != m["datenbank_sha256"]:
            _ungueltig("datenbank_pruefsumme", "Die Prüfsumme der Datenbank stimmt nicht (Datei beschädigt).")
        con = _oeffnen(daten)
        try:
            _schema_pruefen(con, m["schemaversion"])
            zeilen = _zeilen_lesen(con)
        finally:
            con.close()
        formen = _inhalt_pruefen(zeilen)
        arten = tuple(o for o in OBJEKTE if o in m["anzahl"])
        if any(formen[o] for o in OBJEKTE if o not in arten):
            _ungueltig("inhalt_pruefsumme", "Anzahl oder Inhaltsprüfsumme passen nicht zum Inhalt.")
        if ({o: len(formen[o]) for o in arten} != {o: m["anzahl"][o] for o in arten}
                or inhalt_sha256(formen, arten) != m["inhalt_sha256"]):
            _ungueltig("inhalt_pruefsumme", "Anzahl oder Inhaltsprüfsumme passen nicht zum Inhalt.")
        return Sicherung(m, zeilen, formen)
    except _Ungueltig as e:
        raise ApiFehler(422, "sicherung_ungueltig", e.meldung, {"grund": e.grund}) from None


# ================================================================ Vergleich und Einspielen


def vergleich(aktuell: dict[str, dict[int, dict]], s: Sicherung) -> tuple[dict, int]:
    """sicherung.md 5.2 und 5.5: (Unterschied je Objektart, betroffene abgestimmte/abgeglichene Buchungen)."""
    unterschied = {}
    for o in s.arten:
        a, b = aktuell.get(o, {}), s.formen.get(o, {})
        unterschied[o] = {"angelegt": sum(1 for i in b if i not in a),
                          "geaendert": sum(1 for i in b if i in a and a[i] != b[i]),
                          "geloescht": sum(1 for i in a if i not in b)}
    betroffen = 0
    for i, f in aktuell.get("buchung", {}).items():
        gesperrt = f["status"] == "abgeglichen" or any(sp["abstimmung_id"] is not None for sp in f["splits"])
        if gesperrt and s.formen["buchung"].get(i) != f:
            betroffen += 1
    return unterschied, betroffen


def _identisch(aktuell: dict, s: Sicherung) -> bool:
    return all(aktuell.get(o, {}) == s.formen.get(o, {}) for o in OBJEKTE)


def _ergebnis(s: Sicherung, trocken: bool, geaendert: bool, aid: int | None, unterschied: dict,
              betroffen: int) -> dict:
    return {"trocken": trocken, "geaendert": geaendert, "aenderung_id": aid, "manifest": s.manifest,
            "unterschied": unterschied, "abgestimmte_buchungen_betroffen": betroffen}


def probelauf(con, s: Sicherung) -> dict:
    """sicherung.md 5.4: Vergleich ohne Wirkung."""
    with db.transaktion(con, schreibend=False):
        aktuell = alle_formen(con)
    unterschied, betroffen = vergleich(aktuell, s)
    return _ergebnis(s, True, not _identisch(aktuell, s), None, unterschied, betroffen)


_LOESCHEN = ("vorschlag", "buchung_tag", "buchung_extern", "verdacht_kandidat", "dublettenverdacht", "split",
             "buchung", "abstimmung", "regel", "vorlage", "empfaenger_alias", "empfaenger", "tag", "konto")


def einspielen(con, s: Sicherung, zeitpunkt: str) -> dict:
    """sicherung.md 5.3: ersetzt den fachlichen Zustand in einer Transaktion (eine Änderung) oder nichts."""
    erg: dict = {}
    with protokoll.protokolliert(con, "sicherung", "sicherung_einspielen", zeitpunkt) as k:
        aktuell = alle_formen(con)
        unterschied, betroffen = vergleich(aktuell, s)
        erg.update(unterschied=unterschied, betroffen=betroffen)
        if _identisch(aktuell, s):
            erg["geaendert"] = False
        else:
            erg["geaendert"] = True
            con.execute("PRAGMA defer_foreign_keys = ON")
            for tabelle in _LOESCHEN:
                con.execute(f"DELETE FROM {tabelle}")
            laden(con, s.zeilen)
            # gemerkte Kennungen ersetzen (über die Protokoll-Trigger: Rückgängig stellt sie wieder her)
            soll = {k_ for (k_,) in s.zeilen["sync_kennung"]}
            ist = {r[0] for r in con.execute("SELECT kennung FROM sync_kennung")}
            con.executemany("DELETE FROM sync_kennung WHERE kennung = ?", [(x,) for x in sorted(ist - soll)])
            con.executemany("INSERT INTO sync_kennung (kennung) VALUES (?)", [(x,) for x in sorted(soll - ist)])
            # Zustand je Bankkonto ersetzen; vorher/nachher für Rückgängig vermerken (protokoll.md 10.2)
            vorher = protokoll.sync_zustand_lesen(con)
            protokoll.sync_zustand_setzen(con, [dict(zip([c for c, _, _ in SPALTEN["sync_konto_zustand"]], r))
                                                for r in s.zeilen["sync_konto_zustand"]])
            nachher = protokoll.sync_zustand_lesen(con)
            k.danach.append(lambda aid: protokoll.sync_zustand_vermerken(con, aid, vorher, nachher))
            # ID-Zähler: nie kleiner als hier oder in der Quelle je vergeben (sicherung.md 5.3 Punkt 3)
            quelle = dict(s.zeilen["id_zaehler"])
            for o, tabelle in ZAEHLER.items():
                r = con.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (tabelle,)).fetchone()
                hier = 0 if r is None else int(r[0] or 0)
                hoechste = con.execute(f"SELECT MAX(id) FROM {tabelle}").fetchone()[0] or 0
                neu = max(hier, int(quelle.get(o, 0)), int(hoechste))
                if r is None:
                    con.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (tabelle, neu))
                elif neu != hier:
                    con.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (neu, tabelle))
    aid = k.aenderung_id if erg["geaendert"] else None
    return _ergebnis(s, False, erg["geaendert"], aid, erg["unterschied"], erg["betroffen"])


__all__ = ["erstelle_sicherung"]
