"""SQLite-Zugriff und Schema.

Beträge sind im Schema ausschließlich ganze Cent (INTEGER mit CHECK auf
``typeof = 'integer'``); Gleitkommazahlen können nicht gespeichert werden.
IDs werden über AUTOINCREMENT vergeben und nie wiederverwendet.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import pathlib
import sqlite3
from collections.abc import Iterator

from .text import norm

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    schluessel TEXT PRIMARY KEY,
    wert TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS konto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    art TEXT NOT NULL CHECK (art IN ('girokonto','sparkonto','kreditkonto','aufwand','ertrag','eigenkapital')),
    eltern_id INTEGER REFERENCES konto(id),
    iban TEXT UNIQUE,
    geschlossen INTEGER NOT NULL DEFAULT 0 CHECK (geschlossen IN (0, 1)),
    eroeffnet_am TEXT,
    notiz TEXT NOT NULL DEFAULT '',
    extern_id TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS konto_eltern ON konto(eltern_id);

CREATE TABLE IF NOT EXISTS empfaenger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    extern_id TEXT
);
CREATE INDEX IF NOT EXISTS empfaenger_extern ON empfaenger(extern_id);

CREATE TABLE IF NOT EXISTS tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_cf TEXT NOT NULL UNIQUE,
    extern_id TEXT
);
CREATE INDEX IF NOT EXISTS tag_extern ON tag(extern_id);

CREATE TABLE IF NOT EXISTS buchung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    empfaenger_id INTEGER REFERENCES empfaenger(id),
    verwendungszweck TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('importiert','vorlaeufig','bestaetigt','abgeglichen'))
);
CREATE INDEX IF NOT EXISTS buchung_datum ON buchung(datum);
CREATE INDEX IF NOT EXISTS buchung_empfaenger ON buchung(empfaenger_id);

CREATE TABLE IF NOT EXISTS split (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    konto_id INTEGER NOT NULL REFERENCES konto(id),
    betrag INTEGER NOT NULL CHECK (typeof(betrag) = 'integer'
                                  AND betrag BETWEEN -999999999999 AND 999999999999),
    memo TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS split_buchung ON split(buchung_id, position);
CREATE INDEX IF NOT EXISTS split_konto ON split(konto_id, betrag);

CREATE TABLE IF NOT EXISTS buchung_tag (
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    PRIMARY KEY (buchung_id, tag_id)
);
CREATE INDEX IF NOT EXISTS buchung_tag_tag ON buchung_tag(tag_id);

CREATE TABLE IF NOT EXISTS buchung_extern (
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    extern_id TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS buchung_extern_buchung ON buchung_extern(buchung_id);

-- Belege: im Datenmodell vorgesehen, Umsetzung später (K 4). In M1 immer leer.
CREATE TABLE IF NOT EXISTS beleg (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    dateiname TEXT NOT NULL,
    mime_typ TEXT NOT NULL,
    groesse INTEGER NOT NULL CHECK (typeof(groesse) = 'integer' AND groesse >= 0)
);

CREATE TABLE IF NOT EXISTS importvorgang (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    art TEXT NOT NULL,
    dateiname TEXT,
    sha256 TEXT NOT NULL,
    importiert_am TEXT NOT NULL,
    ergebnis TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dublettenverdacht (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buchung_id INTEGER NOT NULL,
    grund TEXT NOT NULL CHECK (grund IN ('mehrdeutig','aehnlich')),
    status TEXT NOT NULL CHECK (status IN ('offen','zusammengefuehrt','keine_dublette')),
    erstellt_am TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verdacht_kandidat (
    verdacht_id INTEGER NOT NULL REFERENCES dublettenverdacht(id) ON DELETE CASCADE,
    buchung_id INTEGER NOT NULL,
    PRIMARY KEY (verdacht_id, buchung_id)
);
CREATE INDEX IF NOT EXISTS verdacht_kandidat_buchung ON verdacht_kandidat(buchung_id);

-- ------------------------------------------------------------ Meilenstein 2
-- Regeln (kategorisierung.md 1); Bedingungen als JSON-Liste.
CREATE TABLE IF NOT EXISTS regel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    aktiv INTEGER NOT NULL CHECK (aktiv IN (0, 1)),
    prioritaet INTEGER NOT NULL CHECK (typeof(prioritaet) = 'integer' AND prioritaet BETWEEN 0 AND 1000000),
    kategorie_id INTEGER NOT NULL REFERENCES konto(id),
    bedingungen TEXT NOT NULL
);

-- Offene Vorschläge (kategorisierung.md 5); höchstens einer je Buchung.
CREATE TABLE IF NOT EXISTS vorschlag (
    buchung_id INTEGER PRIMARY KEY REFERENCES buchung(id) ON DELETE CASCADE,
    kategorie_id INTEGER NOT NULL,
    regel_id INTEGER,
    quelle TEXT NOT NULL CHECK (quelle IN ('regel')),
    vorher_konto_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS vorschlag_regel ON vorschlag(regel_id);

-- Synchronisationsläufe (synchronisation.md 2).
CREATE TABLE IF NOT EXISTS sync_lauf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ausloeser TEXT NOT NULL CHECK (ausloeser IN ('manuell','planer')),
    status TEXT NOT NULL CHECK (status IN ('laeuft','erfolgreich','fehlgeschlagen','wartet_auf_tan','abgebrochen')),
    gestartet_am TEXT NOT NULL,
    beendet_am TEXT,
    von TEXT,
    bis TEXT,
    fehler_code TEXT,
    fehler_meldung TEXT,
    tan_anforderung_id INTEGER
);

CREATE TABLE IF NOT EXISTS sync_lauf_konto (
    lauf_id INTEGER NOT NULL REFERENCES sync_lauf(id) ON DELETE CASCADE,
    iban TEXT NOT NULL,
    konto_id INTEGER NOT NULL,
    konto_neu INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('erfolgreich','fehlgeschlagen','wartet_auf_tan','ausstehend','abgebrochen')),
    von TEXT,
    bis TEXT,
    umsaetze_gesamt INTEGER NOT NULL DEFAULT 0,
    vormerkungen_ignoriert INTEGER NOT NULL DEFAULT 0,
    buchungen_vorhanden INTEGER NOT NULL DEFAULT 0,
    buchungen_zusammengefuehrt INTEGER NOT NULL DEFAULT 0,
    buchungen_neu INTEGER NOT NULL DEFAULT 0,
    buchungen_zur_pruefung INTEGER NOT NULL DEFAULT 0,
    buchungen_kategorisiert INTEGER NOT NULL DEFAULT 0,
    fehler_code TEXT,
    fehler_meldung TEXT,
    PRIMARY KEY (lauf_id, iban)
);

CREATE TABLE IF NOT EXISTS sync_konto_zustand (
    iban TEXT PRIMARY KEY,
    konto_id INTEGER NOT NULL,
    letzter_abruf_bis TEXT,
    letzter_erfolg_am TEXT
);

-- Dauerhaft gemerkte Umsatzkennungen (synchronisation.md 4.3).
CREATE TABLE IF NOT EXISTS sync_kennung (
    kennung TEXT PRIMARY KEY
);

-- TAN-Anforderungen (synchronisation.md 7). Die interne Kennung des Plugins,
-- die TAN und die PIN werden hier nie gespeichert.
CREATE TABLE IF NOT EXISTS tan_anforderung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lauf_id INTEGER NOT NULL,
    iban TEXT NOT NULL,
    konto_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('offen','beantwortet','abgelaufen','abgebrochen')),
    erstellt_am TEXT NOT NULL,
    gueltig_bis TEXT NOT NULL,
    beendet_am TEXT,
    challenge TEXT NOT NULL,
    bild BLOB,
    bild_mime_typ TEXT
);

-- Interne Benachrichtigungen (synchronisation.md 11).
CREATE TABLE IF NOT EXISTS benachrichtigung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    art TEXT NOT NULL,
    schluessel TEXT NOT NULL,
    titel TEXT NOT NULL,
    text TEXT NOT NULL,
    link TEXT,
    erstellt_am TEXT NOT NULL,
    gelesen INTEGER NOT NULL DEFAULT 0 CHECK (gelesen IN (0, 1))
);
CREATE INDEX IF NOT EXISTS benachrichtigung_schluessel ON benachrichtigung(schluessel, gelesen);
"""


def jetzt_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_sql(s):
    return None if s is None else norm(s)


def verbinde(pfad: pathlib.Path) -> sqlite3.Connection:
    """Öffnet die Datenbank (legt Datei und Elternverzeichnisse bei Bedarf an)."""
    pfad = pathlib.Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad), timeout=30, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 30000")
    con.create_function("norm", 1, _norm_sql, deterministic=True)
    return con


def schema_anlegen(pfad: pathlib.Path) -> None:
    con = verbinde(pfad)
    try:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(SCHEMA)
        con.execute("INSERT INTO meta (schluessel, wert) VALUES ('schema_version', ?)"
                    " ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
                    (str(SCHEMA_VERSION),))
    finally:
        con.close()


@contextlib.contextmanager
def transaktion(con: sqlite3.Connection, schreibend: bool = True) -> Iterator[sqlite3.Connection]:
    """Eine Datenbanktransaktion: alles oder nichts."""
    con.execute("BEGIN IMMEDIATE" if schreibend else "BEGIN")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")
