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

SCHEMA_VERSION = 12

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
    bild_mime_typ TEXT,
    erinnerung_nr INTEGER NOT NULL DEFAULT 0
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
    gelesen INTEGER NOT NULL DEFAULT 0 CHECK (gelesen IN (0, 1)),
    zustellung TEXT NOT NULL DEFAULT 'keine' CHECK (zustellung IN ('keine','ausstehend','zugestellt','aufgegeben')),
    zustellversuche INTEGER NOT NULL DEFAULT 0,
    zugestellt_am TEXT,
    naechster_versuch TEXT
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

-- ------------------------------------------------------------ Meilenstein 5
-- Kredite (kredite.md 2); Sondertilgungen und Bedingungen als JSON-Listen. Zuordnungen der Raten und
-- Jahresabgleiche in eigenen Tabellen, bewusst ohne Fremdschlüssel auf Buchungen (kredite.md 2.3: eine gelöschte
-- Buchung entfernt ihre Zuordnung in derselben Änderung, siehe kredite.verwaiste_entfernen).
CREATE TABLE IF NOT EXISTS kredit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    konto_id INTEGER NOT NULL UNIQUE REFERENCES konto(id),
    zahlungskonto_id INTEGER NOT NULL REFERENCES konto(id),
    zins_konto_id INTEGER NOT NULL REFERENCES konto(id),
    restschuld INTEGER NOT NULL CHECK (typeof(restschuld) = 'integer' AND restschuld BETWEEN 1 AND 999999999999),
    stand_datum TEXT NOT NULL,
    sollzins INTEGER NOT NULL CHECK (typeof(sollzins) = 'integer' AND sollzins BETWEEN 0 AND 1000000),
    zinsmethode TEXT NOT NULL CHECK (zinsmethode IN ('30/360','act/360','act/365')),
    rate INTEGER NOT NULL CHECK (typeof(rate) = 'integer' AND rate BETWEEN 1 AND 999999999999),
    erste_faelligkeit TEXT NOT NULL,
    sondertilgungen TEXT NOT NULL,
    bedingungen TEXT NOT NULL,
    aktiv INTEGER NOT NULL CHECK (aktiv IN (0, 1))
);
CREATE INDEX IF NOT EXISTS kredit_zahlungskonto ON kredit(zahlungskonto_id);

CREATE TABLE IF NOT EXISTS kredit_zuordnung (
    kredit_id INTEGER NOT NULL REFERENCES kredit(id) ON DELETE CASCADE,
    faelligkeit TEXT NOT NULL,
    buchung_id INTEGER NOT NULL UNIQUE,
    PRIMARY KEY (kredit_id, faelligkeit)
);

CREATE TABLE IF NOT EXISTS kredit_abgleich (
    kredit_id INTEGER NOT NULL REFERENCES kredit(id) ON DELETE CASCADE,
    jahr INTEGER NOT NULL CHECK (typeof(jahr) = 'integer' AND jahr BETWEEN 1900 AND 9999),
    restschuld INTEGER NOT NULL CHECK (typeof(restschuld) = 'integer' AND restschuld BETWEEN 0 AND 999999999999),
    zinsen INTEGER NOT NULL CHECK (typeof(zinsen) = 'integer' AND zinsen BETWEEN 0 AND 999999999999),
    buchung_id INTEGER,
    PRIMARY KEY (kredit_id, jahr)
);
CREATE INDEX IF NOT EXISTS kredit_abgleich_buchung ON kredit_abgleich(buchung_id);

-- ------------------------------------------------------------ Meilenstein 6
-- Geheimnisspeicher (geheimnisse.md 3): nur Nonce und AES-256-GCM-Chiffretext, nie Klartext.
CREATE TABLE IF NOT EXISTS geheimnis (
    name TEXT PRIMARY KEY,
    nonce BLOB NOT NULL,
    chiffre BLOB NOT NULL,
    gesetzt_am TEXT NOT NULL
);

-- Postfächer (mail.md 2.1): Buchbestand, protokolliert und gesichert.
CREATE TABLE IF NOT EXISTS postfach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    adresse TEXT NOT NULL,
    adresse_cf TEXT NOT NULL UNIQUE,
    bezeichnung TEXT NOT NULL DEFAULT '',
    ordner TEXT NOT NULL,
    absender_filter TEXT NOT NULL DEFAULT '[]',
    aktiv INTEGER NOT NULL CHECK (aktiv IN (0, 1))
);

-- Betriebszustand je Postfachadresse (mail.md 2.3, casefold); nie protokolliert oder gesichert.
CREATE TABLE IF NOT EXISTS postfach_zustand (
    adresse_cf TEXT PRIMARY KEY,
    anmeldung TEXT NOT NULL DEFAULT 'fehlt' CHECK (anmeldung IN ('fehlt','angemeldet','abgelaufen','widerrufen')),
    anmeldung_nr INTEGER NOT NULL DEFAULT 0,
    angemeldet_am TEXT,
    laeuft_ab_am TEXT,
    letzter_abruf_am TEXT,
    letzter_erfolg_am TEXT,
    fehler_code TEXT,
    fehler_meldung TEXT
);

-- Gespiegelte Nachrichten (mail.md 6.5): Betriebszustand, entfällt mit dem Postfach.
CREATE TABLE IF NOT EXISTS mail_nachricht (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    adresse_cf TEXT NOT NULL,
    nachricht_id TEXT NOT NULL,
    empfangen TEXT NOT NULL,
    absender TEXT NOT NULL,
    betreff TEXT NOT NULL,
    text TEXT NOT NULL,
    UNIQUE (adresse_cf, nachricht_id)
);
CREATE INDEX IF NOT EXISTS mail_nachricht_sortierung ON mail_nachricht(empfangen, nachricht_id);

-- ------------------------------------------------------------ Dokumente (D-123)
-- Inhalte inhaltsadressiert; nie protokolliert und nie durch eine Operation gelöscht (Rückgängig braucht sie).
CREATE TABLE IF NOT EXISTS dokument_inhalt (
    sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
    inhalt BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS dokument (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dateiname TEXT NOT NULL CHECK (length(dateiname) BETWEEN 1 AND 200),
    mime_typ TEXT NOT NULL CHECK (mime_typ IN ('application/pdf','image/jpeg','image/png','image/webp',
                                               'message/rfc822')),
    groesse INTEGER NOT NULL CHECK (groesse > 0),
    sha256 TEXT NOT NULL REFERENCES dokument_inhalt(sha256),
    quelle TEXT NOT NULL CHECK (quelle IN ('upload','kamera','mail')),
    erstellt_am TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dokument_buchung (
    dokument_id INTEGER NOT NULL REFERENCES dokument(id) ON DELETE CASCADE,
    buchung_id INTEGER NOT NULL REFERENCES buchung(id) ON DELETE CASCADE,
    PRIMARY KEY (dokument_id, buchung_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS dokument_buchung_buchung ON dokument_buchung(buchung_id, dokument_id);
CREATE INDEX IF NOT EXISTS dokument_sha256 ON dokument(sha256);

-- ------------------------------------------------------------ Mail-Abgleich (D-128)
-- Erwartete Zahlungen (Buchbestand, Objektart ``erwartung``). Beträge in Cent, immer >= 0; die Richtung sagt,
-- ob Geld abgeht oder eingeht. Zuordnungen (``buchung_ids``), Mails (``mails``: Postfach + Nachrichten-ID im
-- Spiegel) und Dokumente (``dokument_ids``) als JSON-Listen. „überfällig“ wird abgeleitet (offen, Frist vorbei).
CREATE TABLE IF NOT EXISTS erwartung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grund TEXT NOT NULL CHECK (grund IN ('bestellung','paypal','rueckerstattung','manuell')),
    richtung TEXT NOT NULL CHECK (richtung IN ('ausgabe','eingang')),
    anbieter TEXT CHECK (anbieter IS NULL OR anbieter IN ('amazon','paypal')),
    schluessel TEXT UNIQUE,
    kennung TEXT NOT NULL DEFAULT '',
    referenz TEXT NOT NULL DEFAULT '',
    haendler TEXT NOT NULL,
    beschreibung TEXT NOT NULL DEFAULT '',
    betrag INTEGER NOT NULL CHECK (typeof(betrag) = 'integer' AND betrag BETWEEN 0 AND 999999999999),
    gesamt INTEGER NOT NULL CHECK (typeof(gesamt) = 'integer' AND gesamt BETWEEN 0 AND 999999999999),
    guthaben INTEGER NOT NULL CHECK (typeof(guthaben) = 'integer' AND guthaben BETWEEN 0 AND 999999999999),
    datum TEXT NOT NULL,
    frist TEXT NOT NULL,
    zustand TEXT NOT NULL CHECK (zustand IN ('offen','erfuellt','guthaben','storniert','erledigt')),
    bezug_id INTEGER,
    buchung_ids TEXT NOT NULL DEFAULT '[]',
    mails TEXT NOT NULL DEFAULT '[]',
    dokument_ids TEXT NOT NULL DEFAULT '[]',
    erstellt_am TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS erwartung_zustand ON erwartung(zustand, frist);

-- ------------------------------------------------------------ Betragsfilter wiederkehrender Buchungen (D-137)
-- Eigene Einstellung je Empfänger (Buchbestand, gehört zur Objektart ``empfaenger``); ohne Zeile gilt die Vorgabe
-- aus ``meta`` (wk_filter_modus, wk_filter_toleranz). ``mindestbetrag`` in Cent ohne Vorzeichen.
CREATE TABLE IF NOT EXISTS empfaenger_wiederkehrend (
    empfaenger_id INTEGER PRIMARY KEY REFERENCES empfaenger(id) ON DELETE CASCADE,
    modus TEXT NOT NULL CHECK (modus IN ('aus','toleranz','mindestschwelle')),
    toleranz_prozent INTEGER CHECK (toleranz_prozent IS NULL OR toleranz_prozent BETWEEN 0 AND 100),
    mindestbetrag INTEGER CHECK (mindestbetrag IS NULL OR mindestbetrag > 0),
    CHECK ((modus = 'toleranz') = (toleranz_prozent IS NOT NULL)),
    CHECK ((modus = 'mindestschwelle') = (mindestbetrag IS NOT NULL))
);

-- ------------------------------------------------------------ Meilenstein 7
-- Anmeldedaten (sicherheit.md 1): Betriebszustand, nie protokolliert, nie in der Sicherung.
-- Zeiten in Sekunden seit der Epoche nach der Systemuhr (nie die Mock-Uhr, sicherheit.md 4.4).
CREATE TABLE IF NOT EXISTS anmeldung_konto (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    passwort_hash TEXT,
    fehlversuche INTEGER NOT NULL DEFAULT 0,
    gesperrt_bis REAL
);
-- Sitzungen: nur der SHA-256 des Tokens wird gespeichert.
CREATE TABLE IF NOT EXISTS sitzung (
    token_hash TEXT PRIMARY KEY,
    erstellt REAL NOT NULL,
    aktivitaet REAL NOT NULL
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
    # M5: Kreditraten je Konto und Lauf (synchronisation.md 17.2); ob das Bankkonto vor dem Lauf schon einmal
    # erfolgreich abgerufen wurde (wiederkehrend.md 5)
    ("sync_lauf_konto", "buchungen_kredit", "INTEGER NOT NULL DEFAULT 0"),
    ("sync_lauf_konto", "vorher_abgerufen", "INTEGER NOT NULL DEFAULT 0"),
    # M6: Zustellung je Benachrichtigung (benachrichtigungen.md 4.1; frühere gelten als „keine“) und Nummer der
    # letzten TAN-Erinnerung (benachrichtigungen.md 5)
    ("benachrichtigung", "zustellung", "TEXT NOT NULL DEFAULT 'keine'"
                                       " CHECK (zustellung IN ('keine','ausstehend','zugestellt','aufgegeben'))"),
    ("benachrichtigung", "zustellversuche", "INTEGER NOT NULL DEFAULT 0"),
    ("benachrichtigung", "zugestellt_am", "TEXT"),
    ("benachrichtigung", "naechster_versuch", "TEXT"),
    ("tan_anforderung", "erinnerung_nr", "INTEGER NOT NULL DEFAULT 0"),
    # M11: Ergebnis des Saldoabgleichs je Konto und Lauf als JSON (kontostand.md 2.1); NULL = nicht verarbeitet
    ("sync_lauf_konto", "saldo_abgleich", "TEXT"),
    # Dokumente (D-123): Rohfassung gespiegelter Mails (Betriebszustand), damit sie als Dokument übernommen werden
    ("mail_nachricht", "roh", "BLOB"),
)
_NACH_MIGRATION = (
    "CREATE INDEX IF NOT EXISTS split_abstimmung ON split(abstimmung_id)",
    "CREATE INDEX IF NOT EXISTS empfaenger_standard ON empfaenger(standardkategorie_id)",
    "CREATE INDEX IF NOT EXISTS benachrichtigung_zustellung ON benachrichtigung(zustellung, naechster_versuch)",
    # M6: Eine neue Benachrichtigung ist „ausstehend“, wenn die App ein Benachrichtigungs-Plugin hat
    # (meta.zustellung_neu, gesetzt von create_app), sonst bleibt sie „keine“ (benachrichtigungen.md 4.1).
    "CREATE TRIGGER IF NOT EXISTS benachrichtigung_zustellung_neu AFTER INSERT ON benachrichtigung"
    " WHEN NEW.zustellung = 'keine' AND (SELECT wert FROM meta WHERE schluessel = 'zustellung_neu') = 'ausstehend'"
    " BEGIN UPDATE benachrichtigung SET zustellung = 'ausstehend' WHERE id = NEW.id; END",
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


def verbinde_lesend(pfad: pathlib.Path) -> sqlite3.Connection:
    """Nur lesende Verbindung (legt nichts an; Gesundheitsprüfung, betrieb.md 6)."""
    con = sqlite3.connect(f"file:{pathlib.Path(pfad)}?mode=ro", uri=True, timeout=5, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def checkpoint(pfad: pathlib.Path) -> None:
    """betrieb.md 5.2 Schritt 4: WAL in die Hauptdatei übernehmen und leeren."""
    try:
        con = sqlite3.connect(str(pfad), timeout=10)
    except sqlite3.Error:
        return
    try:
        con.execute("PRAGMA busy_timeout = 10000")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    except sqlite3.Error:
        pass
    finally:
        con.close()
