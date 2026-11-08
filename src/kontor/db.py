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

SCHEMA_VERSION = 5

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
    extern_id TEXT,
    standardkategorie_id INTEGER REFERENCES konto(id)
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
    status TEXT NOT NULL CHECK (status IN ('importiert','vorlaeufig','bestaetigt','abgeglichen')),
    gegen_iban TEXT
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
    memo TEXT NOT NULL DEFAULT '',
    abstimmung_id INTEGER REFERENCES abstimmung(id)
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
    quelle TEXT NOT NULL CHECK (quelle IN ('regel','standardkategorie','lernmodell')),
    vorher_konto_id INTEGER NOT NULL,
    sicherheit INTEGER CHECK (sicherheit IS NULL OR (typeof(sicherheit) = 'integer' AND sicherheit BETWEEN 0 AND 1000))
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

-- ------------------------------------------------------------ Meilenstein 3
-- Aliase der Empfänger (buchhaltungspflege.md 2.1); ekey über alle Empfänger eindeutig.
CREATE TABLE IF NOT EXISTS empfaenger_alias (
    empfaenger_id INTEGER NOT NULL REFERENCES empfaenger(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    ekey TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS empfaenger_alias_empfaenger ON empfaenger_alias(empfaenger_id);

-- Kontenabstimmungen (buchhaltungspflege.md 5).
CREATE TABLE IF NOT EXISTS abstimmung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    konto_id INTEGER NOT NULL REFERENCES konto(id),
    stichtag TEXT NOT NULL,
    saldo INTEGER NOT NULL CHECK (typeof(saldo) = 'integer'),
    erstellt_am TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS abstimmung_konto ON abstimmung(konto_id);

-- Änderungsprotokoll (protokoll.md 3). Einträge als JSON der Protokollform.
CREATE TABLE IF NOT EXISTS aenderung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zeitpunkt TEXT NOT NULL,
    quelle TEXT NOT NULL,
    aktion TEXT NOT NULL,
    beschreibung TEXT NOT NULL,
    gruppe TEXT,
    rueckgaengig_von TEXT NOT NULL DEFAULT '[]',
    rueckgaengig_durch INTEGER,
    kennungen_neu TEXT NOT NULL DEFAULT '[]',
    kennungen_weg TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS aenderung_gruppe ON aenderung(gruppe);

CREATE TABLE IF NOT EXISTS aenderung_eintrag (
    aenderung_id INTEGER NOT NULL REFERENCES aenderung(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    objekt TEXT NOT NULL,
    objekt_id INTEGER NOT NULL,
    art TEXT NOT NULL,
    vorher TEXT,
    nachher TEXT,
    PRIMARY KEY (aenderung_id, position)
);
CREATE INDEX IF NOT EXISTS aenderung_eintrag_objekt ON aenderung_eintrag(objekt, objekt_id);

-- M3-Nachtrag (synchronisation.md 16.2, protokoll.md 6.4): Kontozuordnungen, die ein gelöschtes
-- Bankkonto wiederhergestellt haben (Betriebszustand, kein Buchbestand).
CREATE TABLE IF NOT EXISTS sync_wiederherstellung (
    aenderung_id INTEGER NOT NULL,
    iban TEXT NOT NULL,
    PRIMARY KEY (aenderung_id, iban)
);

-- ------------------------------------------------------------ Meilenstein 4
-- Split-Vorlagen (vorlagen.md 1); Bedingungen und Teile als JSON-Listen.
CREATE TABLE IF NOT EXISTS vorlage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    aktiv INTEGER NOT NULL CHECK (aktiv IN (0, 1)),
    prioritaet INTEGER NOT NULL CHECK (typeof(prioritaet) = 'integer' AND prioritaet BETWEEN 0 AND 1000000),
    bedingungen TEXT NOT NULL,
    teile TEXT NOT NULL
);

-- ------------------------------------------------------------ Meilenstein 9
-- Zustand je Bankkonto vor und nach einer Änderung sicherung_einspielen (und deren Rückgängig), damit
-- Rückgängig/Wiederholen ihn exakt wiederherstellt (protokoll.md 10.2). Betriebszustand, nie in einer Sicherung.
CREATE TABLE IF NOT EXISTS sicherung_zustand (
    aenderung_id INTEGER PRIMARY KEY,
    vorher TEXT NOT NULL,
    nachher TEXT NOT NULL
);
"""

# Spalten, die frühere Schemaversionen noch nicht haben (Migration ohne Datenverlust).
_NEUE_SPALTEN = (
    ("empfaenger", "standardkategorie_id", "INTEGER REFERENCES konto(id)"),
    ("buchung", "gegen_iban", "TEXT"),
    ("split", "abstimmung_id", "INTEGER REFERENCES abstimmung(id)"),
    # M4: Zählungen der Vorlagen je Konto und Lauf (synchronisation.md 15.2)
    ("sync_lauf_konto", "buchungen_gesplittet", "INTEGER NOT NULL DEFAULT 0"),
    ("sync_lauf_konto", "vorlage_abweichungen", "INTEGER NOT NULL DEFAULT 0"),
    # M3-Nachtrag: übersprungene Bankkonten je Lauf (JSON) und Entscheidung je Bankkonto (synchronisation.md 16)
    ("sync_lauf", "uebersprungen", "TEXT NOT NULL DEFAULT '[]'"),
    ("sync_konto_zustand", "entscheidung", "TEXT CHECK (entscheidung IN ('wiederherstellen','ignorieren'))"),
    ("sync_konto_zustand", "entscheidung_buchungen", "TEXT CHECK (entscheidung_buchungen IN ('alle','nur_neue'))"),
)
_NACH_MIGRATION = (
    "CREATE INDEX IF NOT EXISTS split_abstimmung ON split(abstimmung_id)",
    "CREATE INDEX IF NOT EXISTS empfaenger_standard ON empfaenger(standardkategorie_id)",
)


def _migrieren(con: sqlite3.Connection) -> None:
    """Bringt eine Datenbank früherer Schemaversion auf den aktuellen Stand (Daten bleiben erhalten)."""
    for tabelle, spalte, typ in _NEUE_SPALTEN:
        vorhanden = {r["name"] for r in con.execute(f"PRAGMA table_info({tabelle})")}
        if spalte not in vorhanden:
            con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")
    sql = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'vorschlag'").fetchone()["sql"]
    if "lernmodell" not in sql:
        # CHECK erweitern (M3: standardkategorie, M4: lernmodell) und Spalte sicherheit ergänzen:
        # Tabelle neu aufbauen und Inhalt übernehmen.
        con.execute("CREATE TABLE vorschlag_neu (buchung_id INTEGER PRIMARY KEY REFERENCES buchung(id)"
                    " ON DELETE CASCADE, kategorie_id INTEGER NOT NULL, regel_id INTEGER,"
                    " quelle TEXT NOT NULL CHECK (quelle IN ('regel','standardkategorie','lernmodell')),"
                    " vorher_konto_id INTEGER NOT NULL, sicherheit INTEGER CHECK (sicherheit IS NULL OR"
                    " (typeof(sicherheit) = 'integer' AND sicherheit BETWEEN 0 AND 1000)))")
        con.execute("INSERT INTO vorschlag_neu (buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id)"
                    " SELECT buchung_id, kategorie_id, regel_id, quelle, vorher_konto_id FROM vorschlag")
        con.execute("DROP TABLE vorschlag")
        con.execute("ALTER TABLE vorschlag_neu RENAME TO vorschlag")
        con.execute("CREATE INDEX IF NOT EXISTS vorschlag_regel ON vorschlag(regel_id)")
    for sql in _NACH_MIGRATION:
        con.execute(sql)



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
        con.execute("BEGIN IMMEDIATE")
        try:
            _migrieren(con)
        except BaseException:
            con.execute("ROLLBACK")
            raise
        con.execute("COMMIT")
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
        try:
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
