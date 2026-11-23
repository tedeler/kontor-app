# GnuCash-Import – Meilenstein 4

Verbindlich für Implementierung und Tests. Umsetzung von K 12 („GnuCash:
Import aus XML- oder SQLite-Datei“), T 5 und T 6. Der Import folgt dem
KMyMoney-Import (`datenmodell.md` 10) überall, wo hier nichts anderes steht:
gleiche Prüfreihenfolge, kein Teilimport, Idempotenz, Dublettenerkennung,
Ausgleich unausgeglichener Buchungen, gleiches Ergebnisschema.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

## 1. Schnittstellen

- REST: `POST /api/import/gnucash` (multipart, Feld `datei`), Antworten wie
  `POST /api/import/kmymoney`: 200 `ImportErgebnis` bei Erfolg; 422 mit
  `fehler.code` = Code der ersten Fehlermeldung und `fehler.details` =
  vollständiges `ImportErgebnis` (`erfolgreich = false`); 422 `validierung`
  ohne Feld `datei`.
- Python: `kontor.importer.gnucash.importiere_gnucash(config, quelle, *,
  dateiname=None) -> ImportErgebnis` (`python-api.md` 10.2), Verhalten wie
  `importiere_kmy` (Pfad oder Bytes, gleiche Datenbank, atomar, Ausnahmen
  nur `FileNotFoundError`/`TypeError`).
- Importvorgang (`datenmodell.md` 8): `art = "gnucash"`.
- Protokoll: Änderung mit `quelle = "import"`, `aktion = "import_gnucash"`,
  `gruppe = "import:<import_id>"` (`protokoll.md` 4.2, 9).

## 2. Dateierkennung und Formatfehler

Eingabe sind die Bytes einer Datei. Prüfreihenfolge (erste zutreffende
Regel gilt; bei 1–7 genau eine Fehlermeldung):

1. 0 Bytes → `import_datei_leer`, `format = null`.
2. Beginnt mit `1F 8B` (gzip): entpacken. Beschädigt/abgeschnitten →
   `import_datei_beschaedigt`; entpackt 0 Bytes → `import_datei_leer`.
   Weiter mit Schritt 4 auf den entpackten Bytes, `format = "gnc-xml-gzip"`.
   (SQLite-Dateien werden nie entpackt; entpackte Bytes, die nicht mit `<`
   beginnen, → `import_format_ungueltig`.)
3. Beginnt mit den 16 Bytes `SQLite format 3\0` → SQLite-Datei,
   `format = "gnc-sqlite"`, weiter mit Abschnitt 4.
4. Beginnen die Bytes (nach optionalem UTF-8-BOM und Leerraum) mit `<` →
   XML, `format = "gnc-xml"` (bzw. `gnc-xml-gzip` aus Schritt 2), weiter mit
   Abschnitt 3. Sonst → `import_format_ungueltig`, `format = null`.
5. XML nicht wohlgeformt → `import_datei_beschaedigt`.
6. DTD mit internem Teil (insbesondere `<!ENTITY …>`) →
   `import_format_ungueltig`; externe Entitäten/DTDs werden nie geladen.
7. Wurzelelement nicht `gnc-v2` (ohne Namensraum) oder nicht genau ein
   Element `gnc:book` als Kind der Wurzel → `import_format_ungueltig`.
   (Eine KMyMoney-Datei ergibt hier also `import_format_ungueltig`.)

Bei `import_format_ungueltig` aus Schritt 4 ist `format = null`, bei den
Schritten 5–7 das erkannte Format (`gnc-xml`/`gnc-xml-gzip`). Für SQLite
siehe 4.1. Inhaltliche Fehler (5) → `import_inhalt_ungueltig` mit allen
gefundenen Fehlern. Bei jedem Fehler wird nichts importiert (kein
Teilimport, keine Änderung, kein Importvorgang, keine Änderung im
Protokoll), alle Zählungen 0, `import_id = null`.

## 3. GnuCash-XML

Namensräume (Präfix → URI): `gnc` `http://www.gnucash.org/XML/gnc`, `act`
`…/act`, `book` `…/book`, `cmdty` `…/cmdty`, `slot` `…/slot`, `split`
`…/split`, `trn` `…/trn`, `ts` `…/ts` (alle `http://www.gnucash.org/XML/<x>`).
Ausgewertet werden nur diese direkten Kinder von `gnc:book`, in
Dokumentreihenfolge:

- `gnc:account` – Konten. Kindelemente: `act:name` (Pflicht), `act:id`
  (Pflicht, GUID), `act:type` (Pflicht), `act:commodity` (mit `cmdty:space`,
  `cmdty:id`; fehlt → EUR), `act:code`, `act:description`, `act:parent`
  (GUID), `act:slots` (Slots `hidden`, siehe 6.1).
- `gnc:transaction` – Buchungen. Kindelemente: `trn:id` (Pflicht, GUID),
  `trn:currency` (`cmdty:space`, `cmdty:id`; fehlt → EUR),
  `trn:date-posted/ts:date` (Pflicht), `trn:description`, `trn:slots`
  (Slot `notes`), `trn:splits/trn:split` mit `split:id`, `split:memo`,
  `split:value` (Pflicht), `split:account` (Pflicht, GUID).

Alles andere (z. B. `gnc:commodity`, `gnc:count-data`, `gnc:pricedb`,
`gnc:template-transactions`, `gnc:schedxaction`, `split:quantity`,
`split:reconciled-state`, `trn:num`, `trn:date-entered`) wird ignoriert.
Textinhalte werden unverändert übernommen (keine Änderung von Leerraum außer
wo angegeben). Ein **Slot** ist ein Element `slot` mit Kindern `slot:key`
und `slot:value`; sein Wert ist der Textinhalt von `slot:value`.

## 4. GnuCash-SQLite

### 4.1 Erkennung

Die Datei wird schreibgeschützt geöffnet (keine Änderung an der Datei, keine
Nebendateien). Lässt sie sich nicht als SQLite-Datenbank lesen (z. B.
beschädigte Seiten, `sqlite3.DatabaseError`) → `import_datei_beschaedigt`
(`format = "gnc-sqlite"`). Fehlt eine der Tabellen `books`, `accounts`,
`transactions`, `splits` oder eine der unten genannten Spalten, oder hat
`books` nicht genau eine Zeile → `import_format_ungueltig`
(`format = "gnc-sqlite"`). Die Tabellen `commodities` und `slots` sind
optional.

### 4.2 Tabellen und Spalten

| Tabelle | Spalten | Bedeutung |
| --- | --- | --- |
| `books` | `root_account_guid` | Wurzelkonto des Buchs (Typ `ROOT`) |
| `accounts` | `guid`, `name`, `account_type`, `commodity_guid`, `parent_guid`, `code`, `description`, `hidden` | wie `act:*`; `hidden` Ganzzahl, ≠ 0 → versteckt |
| `commodities` | `guid`, `namespace`, `mnemonic` | Währung eines Kontos bzw. einer Transaktion |
| `transactions` | `guid`, `currency_guid`, `post_date`, `description` | wie `trn:*` |
| `splits` | `guid`, `tx_guid`, `account_guid`, `memo`, `value_num`, `value_denom` | wie `split:*`; Wert = `value_num/value_denom` |
| `slots` | `obj_guid`, `name`, `string_val` | `name = 'notes'` an einer Transaktion → Notiz |

- **Reihenfolge** („Dokumentreihenfolge“ für SQLite): Konten und
  Transaktionen nach `rowid` aufsteigend, Splits einer Transaktion nach
  `rowid` aufsteigend.
- **Hauptbaum:** Übernommen werden nur Konten, deren Elternkette über
  `parent_guid` bei `books.root_account_guid` endet (das Wurzelkonto selbst
  nicht). Andere Zeilen von `accounts` (z. B. der Vorlagenbaum geplanter
  Buchungen) gehören nicht zum Buch. Transaktionen mit mindestens einem
  Split, deren Splits *alle* auf solchen Konten außerhalb des Hauptbaums
  buchen, gehören nicht zum Buch und zählen nicht (auch nicht in
  `buchungen_*`); eine Transaktion ohne Split ist ein Fehler (5). Ein Split, dessen
  `account_guid` in `accounts` gar nicht vorkommt, ist ein Fehler (5).
- Währung: `commodity_guid`/`currency_guid` verweist auf `commodities`;
  fehlt die Tabelle, ist der Wert null oder unbekannt → EUR.
- NULL in Textspalten gilt wie ein fehlendes Element (leer).

## 5. Inhaltliche Fehler (`import_inhalt_ungueltig`)

Gefunden werden (je mit `referenz` = GUID des betroffenen Kontos bzw. der
Transaktion):

- Pflichtangabe fehlt oder ist leer: Konto `id`/`guid`, `name`, `type`;
  Transaktion `id`/`guid`, Buchungsdatum; Split Wert, Split Konto.
- `act:parent`/`parent_guid` verweist auf ein unbekanntes Konto (XML; bei
  SQLite: Konto nicht im Hauptbaum und nicht Wurzel → gehört nicht zum Buch,
  kein Fehler).
- Split verweist auf ein unbekanntes Konto (XML: kein `gnc:account` des
  Buchs mit dieser GUID; SQLite: keine Zeile in `accounts`) oder auf ein
  Konto vom Typ `ROOT`; bei SQLite zusätzlich: eine Transaktion bucht teils
  innerhalb, teils außerhalb des Hauptbaums.
- Wert nicht im Format `[-]Z/N` oder `[-]Z` (XML; Z, N Dezimalziffern,
  N > 0) bzw. `value_denom ≤ 0` (SQLite), nicht exakt in ganzen Cent
  darstellbar oder außerhalb des Betragsbereichs (`datenmodell.md` 1).
- Buchungsdatum ungültig: Gültig sind Texte, die mit `YYYY-MM-DD` beginnen
  (z. B. `2024-01-02 10:59:00 +0000`, `2024-01-02 10:59:00`) oder aus 14
  Ziffern `YYYYMMDDhhmmss` bestehen (ältere SQLite-Dateien); maßgeblich ist
  nur das Kalenderdatum ohne Zeitzonenumrechnung.
- Transaktion ohne Split.

## 6. Abbildung

### 6.1 Konten

- Das Konto vom Typ `ROOT` (XML: jedes; SQLite: `books.root_account_guid`)
  wird nicht übernommen; seine direkten Kinder werden Wurzelkonten. Ein
  Konto ohne Elternangabe (XML) wird ebenfalls Wurzelkonto.
- `extern_id = "gnc:" + GUID` (GUID in Kleinbuchstaben, wie in der Datei),
  `name` unverändert, `notiz` = Beschreibung (fehlend → `""`),
  `eroeffnet_am = null`, `geschlossen` = Slot `hidden` mit Wert `true`
  (Groß-/Kleinschreibung egal; SQLite: `hidden ≠ 0`).
- `iban` (nur Klasse `bestand`): `code` normalisiert (Leerzeichen entfernt,
  Großbuchstaben). Passt das Ergebnis auf `^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$`
  und stimmt die Prüfsumme → IBAN; passt es auf das Muster, aber die
  Prüfsumme nicht → null und Warnung `iban_ungueltig`; passt es nicht auf
  das Muster (z. B. Kontonummern wie `1200`) → null ohne Warnung. Bereits
  vergeben (an ein anderes Konto, das nicht nach 7 zugeordnet wird) → null,
  Warnung `iban_doppelt`.
- Typ → `art`:

  | GnuCash-Typ | `art` | Warnung |
  | --- | --- | --- |
  | `BANK` | girokonto | |
  | `CASH` | girokonto | `kontoart_ersetzt` |
  | `ASSET`, `RECEIVABLE` | sparkonto | `kontoart_ersetzt` |
  | `CREDIT`, `LIABILITY` | kreditkonto | |
  | `PAYABLE` | kreditkonto | `kontoart_ersetzt` |
  | `INCOME` | ertrag | |
  | `EXPENSE` | aufwand | |
  | `EQUITY` | eigenkapital | |
  | `STOCK`, `MUTUAL`, `TRADING`, `CURRENCY`, sonstige | – (übersprungen) | `konto_uebersprungen` |

- Währung: Ein Konto, dessen Typ nicht übersprungen wird und dessen Währung
  nicht EUR ist (`cmdty:space`/`namespace` ∈ {`ISO4217`, `CURRENCY`} und
  `cmdty:id`/`mnemonic` = `EUR`), wird übersprungen, Warnung `fremdwaehrung`.
- Elternkonto übersprungen → `eltern_id = null`; Elternkonto anderer Klasse
  → `eltern_id = null`, Warnung `hierarchie_angepasst`.
- Platzhalterkonten (`placeholder`) werden wie andere Konten übernommen.

### 6.2 Empfänger

GnuCash kennt keine Empfänger. **Empfängername** einer Transaktion ist ihre
Beschreibung (`trn:description` bzw. `transactions.description`) nach
`strip()`; leer oder fehlend → kein Empfänger (E-066).

- Vor den Buchungen wird jeder verschiedene Empfängername der nicht
  übersprungenen Transaktionen (Dokumentreihenfolge) einem Empfänger
  zugeordnet: exakter Name, sonst Alias (`buchhaltungspflege.md` 2.3),
  sonst neu angelegt (`extern_id = null`, `aliase = []`,
  `standardkategorie_id = null`).
- `empfaenger_neu` = Anzahl der dabei angelegten, `empfaenger_vorhanden` =
  Anzahl der zugeordneten Namen. Jeder verschiedene Name zählt genau einmal;
  keine Warnung `empfaenger_zusammengefasst`.

### 6.3 Buchungen

- `extern_ids = ["gnc:" + GUID]`, `datum` nach 5, `empfaenger` nach 6.2,
  `verwendungszweck` = Slot `notes` der Transaktion (fehlend → `""`),
  `status = importiert`, `tags = []`, `vorschlag = null`,
  `gegen_iban = null`.
- Splits in Dokumentreihenfolge: `konto_id`, `betrag` = Wert in Cent,
  `memo` = `split:memo` (fehlend → `""`).
- Bucht ein Split auf ein übersprungenes Konto oder ist die Währung der
  Transaktion nicht EUR → ganze Buchung übersprungen, Warnung
  `buchung_uebersprungen`.
- Summe ≠ 0 oder nur ein Split → Ausgleichssplit auf „Unausgeglichen“ wie
  `datenmodell.md` 10.2, Warnung `buchung_ausgeglichen`.
- Split-Vorlagen, Regeln, Standardkategorien und Lernmodell werden beim
  Import nicht angewendet.

## 7. Zuordnung zu Vorhandenem und Idempotenz

„Vorhanden“ heißt: existierte vor Beginn dieses Laufs. Ein vorhandenes
Konto wird in einem Lauf höchstens einem Konto der Datei zugeordnet (erstes
in Dokumentreihenfolge). Erste passende Regel gewinnt:

| Objekt | Regel 1 | Regel 2 |
| --- | --- | --- |
| Konto mit IBAN in der Datei (Klasse `bestand`, gültige IBAN nach 6.1) | gleiche `extern_id` | vorhandenes Konto mit gleicher IBAN, dessen `extern_id` null ist oder nicht mit `gnc:` beginnt |
| übrige Konten | gleiche `extern_id` | vorhandenes Konto mit gleicher `art`, exakt gleichem `name`, gleichem (bereits zugeordnetem) Elternkonto, ohne IBAN, dessen `extern_id` null ist oder weder mit `gnc:` noch mit `kontor:` beginnt; bei mehreren das mit der kleinsten `id` |
| Buchung | eine Buchung, deren `extern_ids` die Kennung enthält | Dublettenprüfung (8) |

- Ein nach Regel 2 zugeordnetes Konto erhält die `extern_id` nur, wenn es
  bisher keine hatte; sonst behält es seine (z. B. `kmy:…`). Zugeordnete
  Objekte werden sonst nicht verändert. Ein zugeordnetes Konto zählt in
  `konten_vorhanden` bzw. `kategorien_vorhanden`.
- Idempotenz (T 3.7): Ein zweiter Import derselben Datei ändert nichts; alle
  `*_neu`-Zählungen, `buchungen_zusammengefuehrt` und
  `buchungen_zur_pruefung` sind 0. Eine erweiterte Fassung (gleiche GUIDs,
  zusätzliche Transaktionen) fügt genau die zusätzlichen Objekte hinzu.
- Ein Kontor-Buch nimmt genau ein GnuCash-Buch auf (ggf. mehrfach oder in
  aktualisierten Fassungen), zusätzlich zu höchstens einem KMyMoney-Buch.

**KMyMoney-Import nach GnuCash-Import** (Erweiterung von
`datenmodell.md` 10.3, ohne Wirkung auf Bücher ohne GnuCash-Import):

- Regel 2 für Konten gilt auch für vorhandene Konten, deren `extern_id` mit
  `gnc:` beginnt; sie behalten ihre `extern_id`.
- Zusätzlich gilt für ein Bestandskonto der Datei ohne gültige IBAN als
  Regel 3: vorhandenes Konto mit `extern_id` `gnc:…`, gleicher `art`, exakt
  gleichem `name`, gleichem (bereits zugeordnetem) Elternkonto und ohne
  IBAN; bei mehreren das mit der kleinsten `id`.
- Jedes vorhandene Konto wird dabei höchstens einem Konto der KMyMoney-Datei
  zugeordnet (E-068).

## 8. Dublettenerkennung

Wie `datenmodell.md` 10.4 mit diesen Festlegungen:

- Kandidaten sind vorhandene Buchungen, deren `extern_ids` keine Kennung mit
  Präfix `gnc:` enthalten (Buchungen aus KMyMoney, Synchronisation und
  manuell erfasste sind Kandidaten).
- Empfänger der neuen Buchung ist der Empfängername nach 6.2 (bzw. keiner);
  „passend“ wie `datenmodell.md` 1.
- Zusammenführen hängt `"gnc:" + GUID` an die `extern_ids` des Kandidaten an
  (sortiert); sonst bleibt er unverändert.

Damit ergeben überschneidende Zeiträume aus KMyMoney und GnuCash keine
doppelten Salden (T 6): Eindeutige Treffer werden zusammengeführt;
mehrdeutige (z. B. zweimal derselbe Kaffee) werden angelegt und zur
Bestätigung vorgelegt; nach dem Auflösen der Verdachte (`datenmodell.md` 9)
ist jeder Vorgang genau einmal im Buch. Umgekehrt gilt dasselbe für einen
KMyMoney-Import nach einem GnuCash-Import (10.4: Kandidaten ohne `kmy:`).

## 9. Ergebnis

Schema `ImportErgebnis` wie `datenmodell.md` 10.5 mit:

- `format` ∈ {`gnc-xml-gzip`, `gnc-xml`, `gnc-sqlite`, null}.
- `konten_*`, `kategorien_*` wie 10.5 (ohne Wurzelkonto, ohne übersprungene,
  ohne „Unausgeglichen“).
- `tags_neu = tags_vorhanden = 0`.
- `buchungen_neu + buchungen_vorhanden + buchungen_zusammengefuehrt +
  buchungen_uebersprungen` = Anzahl der Transaktionen des Buchs.
- `referenz` in Meldungen = GUID (ohne `gnc:`) oder null.
- Warnungscodes wie 10.5 (ohne `empfaenger_zusammengefasst`,
  `tag_zusammengefasst`, `eroeffnungsdatum_ungueltig`); Fehlercodes
  unverändert.
