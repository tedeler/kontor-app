# Datensicherung und Wiederherstellung – Meilenstein 9 (Ergänzungen M5, M6, M18, M20)

Verbindlich für Implementierung und Tests. Auftrag des Anwenders vom
2026-11-08: „Alle Konten müssen in einem üblichen Datenformat exportiert
werden können. Der Import muss auch möglich sein. Dann wird aber der
gesamte interne Zustand überschrieben und als neue Version angelegt.“
Dazu die bestätigten Präzisierungen (E-085 bis E-093). Ergänzt
`protokoll.md` (Abschnitt 10), `python-api.md` (Abschnitt 11) und
`openapi.yaml` (Tag `sicherung`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

## 1. Überblick

- **Sicherung erstellen:** `GET /api/sicherung` liefert eine ZIP-Datei mit
  dem vollständigen fachlichen Zustand als SQLite-Datenbank und einem
  Manifest.
- **Sicherung einspielen:** `POST /api/sicherung/einspielen` ersetzt den
  gesamten fachlichen Zustand durch den der Sicherung. Kein Zusammenführen,
  keine Dublettenerkennung; das ist etwas anderes als der KMyMoney- und
  GnuCash-Import.
- **Neue Version:** Das Einspielen ist eine Änderung im Änderungsprotokoll
  (`quelle = "sicherung"`) und lässt sich wie jede Änderung rückgängig
  machen. Ist der Inhalt identisch, entsteht keine Änderung.
- Das Änderungsprotokoll selbst und Geheimnisse sind **nie** Teil einer
  Sicherung.

## 2. Umfang

### 2.1 Was eine Sicherung enthält

1. Den **Buchbestand** (`protokoll.md` 1 und 9.1): alle Objekte der Arten
   `konto`, `empfaenger`, `tag`, `buchung`, `regel`, `verdacht`,
   `abstimmung`, `vorlage` mit allen Feldern und ihren IDs, einschließlich
   Splits mit ihren IDs.
2. Die **gemerkten Umsatzkennungen** der Synchronisation
   (`synchronisation.md` 4.3), und zwar **alle**: auch die Kennungen
   gelöschter Buchungen und gelöschter Konten, nicht nur die in `extern_ids`
   existierender Buchungen (E-034, E-096).
3. Den **Zustand je Bankkonto** (`synchronisation.md` 2.3, 16.1): IBAN,
   `konto_id`, `letzter_abruf_bis`, `letzter_erfolg_am` und die
   gespeicherte Entscheidung (16.3) mit `aktion` und `buchungen`
   (vermerkte Wiederherstellung `"alle"`/`"nur_neue"` bzw. `ignorieren`).
   Das gilt auch, wenn `konto_id` auf ein gelöschtes Konto zeigt, und auch
   für eine Entscheidung, die gerade durch ein Konto mit dieser IBAN
   verdeckt ist (Status `aktiv`; verworfen wird sie erst im nächsten Lauf,
   16.2 Regel 1). `status` wird nicht gespeichert, sondern nach dem
   Einspielen nach 16.1 aus dem eingespielten Kontenbestand abgeleitet.
4. Die **ID-Zähler**: je Objektart (auch Splits) die höchste in der Quelle
   je vergebene ID.

Das Lernmodell hat keinen eigenen Zustand (`lernmodell.md` 1); es entsteht
nach dem Einspielen aus dem eingespielten Bestand: `GET /api/lernmodell`
(bis auf `automatisch`) und alle Vorhersagen sind danach dieselben wie in
der Quelle. Offene Vorschläge aller Quellen (`regel`, `standardkategorie`,
`lernmodell` mit `sicherheit`) sind Teil der Protokollform der Buchung und
damit der Sicherung.

### 2.2 Was eine Sicherung nie enthält

- das Änderungsprotokoll (`/api/aenderungen`),
- Geheimnisse: PIN, Tokens, Zugangsdaten, Schlüssel (auch nicht
  verschlüsselt),
- Importvorgänge (`/api/importe`), Synchronisationsläufe, TAN-Anforderungen,
  Benachrichtigungen, die simulierte Uhr,
- die Konfiguration der Instanz (`KontorConfig`, z. B.
  `lernmodell_automatisch`, `mock_szenario`, Planer-Einstellungen): Sie
  gehört zur Instanz, nicht zum Buch, und bleibt beim Einspielen
  unverändert (E-096).

Die Datenbankdatei der Sicherung enthält auch keine **Reste** solcher Daten
oder gelöschter Objekte (z. B. in freien Seiten): Ein Text, der nur noch im
Protokoll oder nur in einem gelöschten Objekt vorkommt, steht nicht in der
Datei (z. B. nach `VACUUM`).

### 2.3 Spätere Meilensteine

Jeder spätere Meilenstein, der fachlichen Zustand hinzufügt (z. B. Kredite
in M5), legt fest, dass dieser Zustand Teil der Sicherung ist, und ergänzt
`anzahl` (3.2) um seine Objektart. Geheimnisse (M6) bleiben ausgeschlossen
und werden beim Einspielen nicht verändert (E-090).

### 2.4 Abgleich mit M1–M4 und dem M3-Nachtrag

Vollständige Zuordnung aller bis M4 spezifizierten fachlichen Zustände
(E-096); was hier nicht steht, ist Betriebszustand nach 2.2.

| Zustand (Spezifikation) | in der Sicherung als |
| --- | --- |
| Konten, Hierarchie, IBAN, `extern_id`, Notiz (`datenmodell.md`) | Objekt `konto` |
| Empfänger mit Aliasen und Standardkategorie (`buchhaltungspflege.md` 2) | Objekt `empfaenger` |
| Tags (`datenmodell.md`) | Objekt `tag` |
| Buchungen, Splits mit `abstimmung_id`, Status, `extern_ids`, `gegen_iban`, Vorschlag mit Quelle und Sicherheit (`kategorisierung.md` 5, `lernmodell.md` 5) | Objekt `buchung` |
| Regeln (`kategorisierung.md` 1) | Objekt `regel` |
| Dublettenverdachte (`datenmodell.md`) | Objekt `verdacht` |
| Abstimmungen (`buchhaltungspflege.md` 5) | Objekt `abstimmung` |
| Split-Vorlagen (`vorlagen.md` 1) | Objekt `vorlage` |
| Gemerkte Umsatzkennungen, auch gelöschter Buchungen (`synchronisation.md` 4.3) | 2.1 Punkt 2 |
| Zustand und Entscheidung je Bankkonto (`synchronisation.md` 2.3, 16) | 2.1 Punkt 3 |
| ID-Zähler aller Objektarten und Splits (`datenmodell.md` 1) | 2.1 Punkt 4 |
| Lernmodell (`lernmodell.md` 1) | kein eigener Zustand; folgt aus dem Bestand |

Ohne eigenen Zustand und daher nicht gesichert: abgelehnte Vorschläge und
abgelehnte Umbuchungspaare (werden nicht gemerkt, `kategorisierung.md` 5,
`buchhaltungspflege.md` 4.6), Suche und Erfassungshilfe (abgeleitet).

### 2.5 Meilenstein 5: Kredite (E-109)

- Das Objekt `kredit` (`kredite.md` 2, `protokoll.md` 11) gehört zum
  Buchbestand und damit zur Sicherung, mit allen Feldern einschließlich
  `zuordnungen` und `abgleiche`; ID-Zähler (2.1 Punkt 4) auch für Kredite.
- **Objektarten ab M5 nur bei Vorhandensein:** `anzahl` (3.2) und `inhalt`
  (3.3) enthalten den Schlüssel `kredit` genau dann, wenn die Sicherung
  mindestens einen Kredit enthält; `unterschied` (5.5) enthält ihn genau
  dann, wenn Sicherung oder aktueller Bestand mindestens einen Kredit
  enthält. Ohne Kredite sind Manifest, Inhaltsprüfsumme und Ergebnis also
  genau wie in M9 (Rückwärtskompatibilität, 3.4: eine fehlende Objektart
  gilt als leer). Unbekannte Schlüssel in `anzahl` (andere als die
  Objektarten aus 2.1 und `kredit`) → `manifest_ungueltig`.
- `inhalt_ungueltig` (5.1) zusätzlich, wenn ein Kredit die Bezugsregeln aus
  `kredite.md` 2.3 verletzt.
- Rundreise: Nach dem Einspielen liefern `GET /api/kredite`, die
  Tilgungspläne und alle Buchungen des Kredits dasselbe wie in der Quelle.
- Ohne eigenen Zustand und daher nicht gesichert: wiederkehrende Buchungen
  (`wiederkehrend.md`, folgen aus den Buchungen), Berichte und Export.
  Benachrichtigungen (auch die neuen Arten) und die Konfiguration
  `wiederkehrend_automatisch` gehören nach 2.2 nie dazu.

| Zustand (Spezifikation) | in der Sicherung als |
| --- | --- |
| Kredite mit Parametern, Sondertilgungen, Zuordnungen, Abgleichen (`kredite.md` 2) | Objekt `kredit` |
| Tilgungsplan (`kredite.md` 3) | kein eigener Zustand; folgt aus dem Kredit |
| Wiederkehrende Buchungen (`wiederkehrend.md`) | kein eigener Zustand; folgt aus den Buchungen |

### 2.6 Meilenstein 6: Postfächer (E-118)

- Das Objekt `postfach` (`mail.md` 2, `protokoll.md` 12) gehört zum
  Buchbestand und damit zur Sicherung, mit allen Feldern; ID-Zähler auch
  für Postfächer.
- Wie Kredite **nur bei Vorhandensein** (2.5): `anzahl` und `inhalt`
  enthalten `postfach` genau dann, wenn die Sicherung mindestens ein
  Postfach enthält; `unterschied`, wenn Sicherung oder Bestand eines
  enthalten. Unbekannte Schlüssel in `anzahl` (andere als 2.1, `kredit`,
  `postfach`) → `manifest_ungueltig`. `inhalt_ungueltig` zusätzlich bei
  ungültiger oder nach `casefold()` doppelter `adresse`.
- **Nie** Teil der Sicherung (2.2, `geheimnisse.md` 6): Geheimnisse jeder Art
  (OAuth-Tokens, `oauth_client_secret`, `ntfy_token`, Schlüssel), offene
  Anmeldungen, gespiegelte Nachrichten und `PostfachStatus` (Betriebszustand,
  `mail.md` 6.5), Zustellstatus und Erinnerungszähler von
  Benachrichtigungen, die PIN-Quelle.
- Beim Einspielen werden Postfächer wie jeder Buchbestand ersetzt;
  Geheimnisse bleiben unverändert (E-090). Spiegel, Betriebszustand und
  Tokens bleiben für jedes Postfach erhalten, dessen `adresse` danach noch
  existiert, die übrigen entfallen (`mail.md` 6.5). Rückgängig des
  Einspielens stellt die Postfächer wie jeden Buchbestand wieder her.

| Zustand (Spezifikation) | in der Sicherung als |
| --- | --- |
| Postfächer (`mail.md` 2) | Objekt `postfach` |
| Anmeldung, Tokens, Client-Secret, ntfy-Token, Schlüssel (`geheimnisse.md`) | nie |
| gespiegelte Nachrichten, `PostfachStatus` (`mail.md` 2.3, 6.5) | nie (Betriebszustand) |
| ab M23: Schutz der Geheimnisse (Hülle), Sperrzustand, gemerkte PIN, App-Passwörter (`geheimnisschutz.md` 3) | nie; Einspielen ändert sie nicht; `anzahl` und Inhaltsprüfsumme unverändert |
| ab M29: Bankzugang samt gespeicherten Konten und Auswahl, Schalter des Diagnoseprotokolls, Markierung „alt“ der Bank-Kennungen (`bankzugang.md` 3, 4) | nie (Betriebszustand); Einspielen ändert sie nicht; `anzahl` und Inhaltsprüfsumme unverändert |
| Zustellung, TAN-Erinnerungen (`benachrichtigungen.md`) | nie (Betriebszustand) |

### 2.7 Meilenstein 18: Dokumente (E-206)

Regeln in `dokumente.md` 4. Kurzfassung:

- Das Objekt `dokument` (`protokoll.md` 15) gehört zum Buchbestand und zur
  Sicherung, samt den Inhalten, die ein enthaltenes Dokument braucht, und den
  Verknüpfungen (Feld `dokument_ids` der Protokollform einer Buchung, nur wenn
  sie mindestens ein Dokument hat); ID-Zähler auch für Dokumente.
- Wie Kredite **nur bei Vorhandensein** (2.5): `anzahl` und `inhalt`
  enthalten `dokument` genau dann, wenn die Sicherung mindestens ein Dokument
  enthält; `unterschied`, wenn Sicherung oder Bestand eines enthalten.
  `dokument` ist ein zulässiger Schlüssel in `anzahl`. Ohne Dokumente bleiben
  Manifest und Prüfsummen wie vor M18.
- `schemaversion` steigt; ältere Sicherungen werden ohne Dokumente gelesen
  (3.4).
- `inhalt_ungueltig` zusätzlich bei einem Inhalt, der nicht zu seinem
  SHA-256 passt, einem Dokument ohne Inhalt, falscher `groesse`, einem am
  Inhalt erkannten Typ ≠ `mime_typ`, ungültiger `quelle` oder `erstellt_am`,
  nicht gesäubertem `dateiname` (`dokumente.md` 1.3) oder einem Dokument ohne
  Buchung.

| Zustand (Spezifikation) | in der Sicherung als |
| --- | --- |
| Dokumente mit Feldern (`dokumente.md` 1.1) | Objekt `dokument` |
| Inhalte (Bytes) der enthaltenen Dokumente | in `kontor.sqlite` (Schema frei) |
| Verknüpfungen Dokument–Buchung | `dokument_ids` der Buchung |

### 2.8 Meilenstein 20: Erwartete Zahlungen (E-216)

Regeln in `erwartungen.md` 7 und 12:

- Das Objekt `erwartung` gehört zum Buchbestand und zur Sicherung, mit allen
  Feldern aus `erwartungen.md` 3 ohne die abgeleiteten, einschließlich des
  internen Schlüssels; ID-Zähler auch für Erwartungen.
- Nur bei Vorhandensein (2.5): `anzahl`, `inhalt` und `unterschied`
  enthalten `erwartung` genau dann, wenn Erwartungen vorhanden sind; die
  Inhaltsprüfsumme verwendet die Protokollform (`erwartungen.md` 12).
- Gespiegelte Mails bleiben Betriebszustand (2.6): Nach dem Einspielen in eine
  leere App ist `spiegel_id` in `mail_eintraege` null.
- Die Definition nennt Schemaversion 5; Sicherungen kleinerer Versionen
  werden ohne Erwartungen gelesen (3.4). Ungültige Werte →
  `inhalt_ungueltig`.

## 3. Format

### 3.1 ZIP-Datei

- ZIP (Deflate oder Stored), unverschlüsselt, mit **genau zwei** Einträgen
  in beliebiger Reihenfolge: `manifest.json` und `kontor.sqlite`. Keine
  Verzeichniseinträge, keine anderen Namen.
- `kontor.sqlite`: SQLite-3-Datenbank. Schema frei (Sache der
  Implementierung), aber: `PRAGMA integrity_check` liefert `ok`, die Datei
  ist eigenständig (kein WAL-Modus, keine `-wal`/`-shm`-Datei nötig), und
  `sqlite_master` enthält nur Objekte der Typen `table` und `index`
  (keine Views, keine Trigger).
- Dateiname bei der Auslieferung (`Content-Disposition`):
  `kontor-sicherung-<modus>-<JJJJMMTT>T<HHMMSS>Z.zip`, mit `<modus>` ∈
  {`echt`, `mock`} und dem Zeitpunkt `erstellt` (App-Uhr).

### 3.2 Manifest (`manifest.json`, Schema `SicherungManifest`)

UTF-8-JSON-Objekt:

| Feld | Typ | Regeln |
| --- | --- | --- |
| `format` | `"kontor-sicherung"` | fest |
| `formatversion` | int | `1` |
| `erstellt` | date-time | App-Uhr (`synchronisation.md` 8), ohne Sekundenbruchteile |
| `modus` | `"echt"` \| `"mock"` | Modus der erzeugenden App |
| `app_version` | str | `kontor.__version__` der erzeugenden App (ab M13 im Schema `version.md` 1.1) |
| `schemaversion` | int ≥ 1 | Version des Datenbankschemas in `kontor.sqlite`; Sache der Implementierung, steigt bei jeder Schemaänderung |
| `anzahl` | Objekt | je Objektart aus 2.1 Punkt 1 die Anzahl der Objekte, z. B. `{"konto": 12, …, "vorlage": 0}`; genau diese Schlüssel |
| `inhalt_sha256` | str | Inhaltsprüfsumme (3.3), 64 Kleinbuchstaben-Hexziffern |
| `datenbank_sha256` | str | SHA-256 der Bytes von `kontor.sqlite`, 64 Kleinbuchstaben-Hexziffern |

Unbekannte Felder führen beim Einspielen zu `manifest_ungueltig`.

### 3.3 Inhaltsprüfsumme

`inhalt_sha256` = SHA-256 der UTF-8-Bytes von

```python
json.dumps(inhalt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

mit `inhalt` = Objekt, das für **jeden Schlüssel von `anzahl`** die Liste
der Protokollformen (`protokoll.md` 2, 9.1) aller Objekte dieser Art
enthält, nach `id` aufsteigend. Die Protokollformen sind genau die, die die
REST-Schnittstelle nach dem Einspielen liefert. Damit lässt sich die
Prüfsumme unabhängig aus den Lese-Endpunkten berechnen.

Gemerkte Kennungen, Bankkonto-Zustand und ID-Zähler sind nicht Teil der
Inhaltsprüfsumme; sie sind über `datenbank_sha256` gegen Beschädigung
gesichert.

### 3.4 Ältere Sicherungen

Sicherungen mit kleinerer `schemaversion` werden beim Einspielen auf das
aktuelle Schema gebracht (Migration); Objektarten, die in `anzahl` fehlen,
gelten als leer. Eine größere `formatversion` oder `schemaversion` als die
der App wird abgelehnt (`version_nicht_unterstuetzt`).

## 4. Sicherung erstellen

`GET /api/sicherung` → 200, `Content-Type: application/zip`,
`Content-Disposition: attachment; filename="…"` (3.1).

- Der Inhalt ist ein **konsistenter Schnappschuss** (eine Lesetransaktion),
  auch während eines Synchronisationslaufs.
- Erzeugt keine Änderung, keine Benachrichtigung und ändert nichts.
- Zweimal hintereinander erstellt, ohne Änderung dazwischen: gleiche
  `inhalt_sha256` (die Bytes dürfen sich unterscheiden, z. B. durch
  `erstellt`).
- Auch über Python: `kontor.sicherung.erstelle_sicherung(config)`
  (`python-api.md` 11), z. B. für zeitgesteuerte Sicherungen im Betrieb.

## 5. Sicherung einspielen

`POST /api/sicherung/einspielen` mit `multipart/form-data`, Feld `datei`
(wie der KMyMoney-Import), und den Query-Parametern `trocken` und
`bestaetigt` (beide bool, Vorgabe `false`).

### 5.1 Prüfreihenfolge

1. Feld `datei` fehlt oder Parameter ungültig → 422 `validierung`.
2. Datei ungültig → 422 `sicherung_ungueltig` mit `details = {"grund":
   <grund>}`, geprüft in dieser Reihenfolge:

   | `grund` | Fall |
   | --- | --- |
   | `datei_leer` | 0 Bytes |
   | `kein_zip` | keine lesbare ZIP-Datei |
   | `zip_inhalt` | nicht genau die beiden Einträge aus 3.1, Verzeichnisse, verschlüsselte Einträge, Pfadangaben (`/`, `\`, `..`) |
   | `manifest_ungueltig` | kein UTF-8-JSON-Objekt, Feld fehlt, falscher Typ, unbekanntes Feld |
   | `format_unbekannt` | `format ≠ "kontor-sicherung"` |
   | `version_nicht_unterstuetzt` | `formatversion` oder `schemaversion` größer als unterstützt |
   | `datenbank_pruefsumme` | `datenbank_sha256` passt nicht zu `kontor.sqlite` |
   | `datenbank_ungueltig` | keine SQLite-Datenbank oder `integrity_check` ≠ `ok` |
   | `datenbank_fremd` | Schema passt nicht zur `schemaversion`: fehlende oder zusätzliche Tabellen oder Spalten, Views, Trigger |
   | `inhalt_ungueltig` | Daten verletzen Invarianten (`datenmodell.md` 3, T 3.1–3.4) oder Bezugs-/Eindeutigkeitsregeln des Buchbestands (`protokoll.md` 6.1 Schritt 5, 9.1). Kein Fehler sind gemerkte Kennungen ohne Buchung und Einträge je Bankkonto, deren `konto_id` auf kein Konto des Bestands zeigt (2.1 Punkte 2 und 3) |
   | `inhalt_pruefsumme` | `anzahl` oder `inhalt_sha256` passen nicht zum Inhalt |

3. `manifest.modus` ≠ Modus der App → 409 `sicherung_modus` (eine
   Mock-Sicherung gelangt nie in die Echtdatenbank und umgekehrt, K 3).
4. Nur ohne `trocken`: `bestaetigt` ist nicht `true` → 409
   `bestaetigung_erforderlich`.
5. Nur ohne `trocken`: Ein Lauf hat Status `laeuft` → 409 `sync_laeuft`;
   ein Lauf hat Status `wartet_auf_tan` → 409 `tan_ausstehend`.

Bei jedem Fehler ändert sich nichts (kein Teilimport). Die Datei wird nie
als Datenbank der App übernommen oder geöffnet, bevor sie geprüft ist; die
Implementierung liest nur bekannte Tabellen und Spalten (Schutz gegen
untergeschobene Datenbanken). Ungültige Dateien führen nie zu 5xx.

### 5.2 Vergleich

Verglichen werden die Protokollformen des aktuellen Buchbestands mit denen
der Sicherung, je Objekt `(objekt, id)`:

- nur in der Sicherung → `angelegt`,
- nur aktuell → `geloescht`,
- in beiden, aber verschieden → `geaendert`.

**Identisch** heißt: kein Objekt unterscheidet sich (gleichbedeutend mit
gleicher Inhaltsprüfsumme).

### 5.3 Wirkung

- **Identisch:** Es ändert sich nichts – auch nicht an gemerkten
  Kennungen, Bankkonto-Zustand und ID-Zählern –, es entsteht keine
  Änderung. Antwort 200 mit `geaendert = false`, `aenderung_id = null`.
- **Sonst** (ohne `trocken`), atomar in einer Transaktion:
  1. Der Buchbestand wird exakt der der Sicherung (gleiche IDs, auch
     Splits).
  2. Gemerkte Kennungen und Bankkonto-Zustand werden durch die der
     Sicherung **ersetzt** (Einträge ohne Gegenstück entfallen).
  3. ID-Zähler: Neue IDs sind danach je Art größer als jede ID, die hier
     oder in der Quelle der Sicherung je vergeben wurde (`datenmodell.md`
     1: nie wiederverwendet; Ausnahme sind nur die eingespielten Objekte
     selbst).
  4. Es entsteht **eine** Änderung `quelle = "sicherung"`, `aktion =
     "sicherung_einspielen"`, `gruppe = null`, mit den Einträgen nach 5.2
     (`protokoll.md` 10).
  5. Antwort 200 mit `geaendert = true` und `aenderung_id`.
- Status- und Sperrregeln (`datenmodell.md` 3.1, `buchhaltungspflege.md`
  5.4) gelten nicht: Abgestimmte und abgeglichene Buchungen werden
  ebenfalls ersetzt. Deshalb ist `bestaetigt = true` Pflicht; die
  Oberfläche zeigt vorher das Ergebnis eines Probelaufs.
- Unverändert bleiben: Änderungsprotokoll (bis auf die neue Änderung),
  Importvorgänge, Läufe, TAN-Anforderungen, Benachrichtigungen, PIN,
  simulierte Uhr, Geheimnisse.

### 5.4 Probelauf

Mit `trocken = true`: Prüfung nach 5.1 Schritte 1–3, Vergleich nach 5.2,
keine Wirkung, keine Änderung, keine Sperrprüfung. Antwort 200 mit
`trocken = true`, `geaendert` = ob ein Einspielen etwas ändern würde,
`aenderung_id = null`.

### 5.5 Ergebnis (`SicherungErgebnis`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `trocken` | bool | |
| `geaendert` | bool | false genau bei „identisch“ |
| `aenderung_id` | int \| null | die neue Änderung; null bei `trocken` oder identisch |
| `manifest` | `SicherungManifest` | das gelesene Manifest |
| `unterschied` | Objekt | je Objektart aus `anzahl` ein Objekt `{angelegt, geaendert, geloescht}` (int ≥ 0) nach 5.2; bei Erfolg gleich den Einträgen der Änderung |
| `abgestimmte_buchungen_betroffen` | int | Anzahl aktueller Buchungen mit `abgestimmt = true` oder `status = "abgeglichen"`, die nach 5.2 `geaendert` oder `geloescht` sind |

## 6. Rückgängig

Die Änderung `sicherung_einspielen` wird wie jede andere nach
`protokoll.md` 6 rückgängig gemacht (Zustandsprüfung, Bezugsprüfung,
Wiederholen). Zusätzlich (`protokoll.md` 10.2):

- Rückgängig stellt auch gemerkte Kennungen und Bankkonto-Zustand von vor
  dem Einspielen exakt wieder her, Wiederholen wieder die der Sicherung.
- ID-Zähler werden nicht zurückgesetzt (IDs werden nie wiederverwendet).
- Ein laufender oder auf TAN wartender Lauf verhindert Rückgängig und
  Wiederholen dieser Änderung nicht; Sperrregeln gelten wie bei 5.1 nicht.

## 7. Zusammenspiel mit Synchronisation und Import

- Weil Kennungen und `letzter_abruf_bis` aus der Sicherung kommen, holt der
  nächste Abruf Umsätze, die nach dem Erstellen der Sicherung gebucht
  wurden, erneut – jeden genau einmal (T 6). Umsätze, die schon in der
  Sicherung gebucht sind, kommen nicht doppelt.
- Ein KMyMoney- oder GnuCash-Import nach dem Einspielen verhält sich wie
  auf dem Bestand der Sicherung (Zuordnung über `extern_id`, Idempotenz).
- Während des Einspielens startet kein Lauf (Planer und `POST /api/sync`
  warten bzw. antworten 409 `sync_laeuft`).

## 8. Sicherheit

- Sicherungen sind sensible Daten. Die Datei wird nur auf Anfrage
  erzeugt und nicht auf dem Server abgelegt.
- Die Implementierung begrenzt beim Einspielen die entpackte Größe
  (Schutz gegen ZIP-Bomben; Grenze frei, mindestens 1 GiB, Überschreitung
  → `zip_inhalt`).
- Nach M7 (Login) sind beide Endpunkte nur angemeldet erreichbar (`sicherheit.md` 3).

## 9. Meilenstein 7: Anmeldedaten und zeitgesteuerte Sicherung

- **Anmeldedaten** (Passwort-Hash, Sitzungen, CSRF-Tokens, Fehlversuche,
  Sperre, Einrichtungscode; `sicherheit.md` 1) sind Betriebszustand: nie
  Teil einer Sicherung (weder in `kontor.sqlite` noch im Manifest), keine
  Objektart in `anzahl`, kein Teil der Inhaltsprüfsumme (E-135). M9- bis
  M6-Prüfsummen bleiben dadurch unverändert.
- **Einspielen** lässt die Anmeldedaten der Zielinstanz unverändert:
  Passwort und bestehende Sitzungen gelten weiter (auch die Sitzung, die
  das Einspielen auslöst).
- **Zeitgesteuerte Sicherung** (`betrieb.md` 8,
  `kontor.sicherung.sichere_in_verzeichnis`, systemd-Timer): legt Dateien
  mit genau dem Inhalt von `erstelle_sicherung` auf dem Server ab (Rechte
  `0600`, Verzeichnis `0700`, Benutzer `kontor`). Das ist die bewusste
  Ausnahme zu 8 („nicht auf dem Server abgelegt“), die nur für Backups gilt
  (K 2, E-132); `GET /api/sicherung` legt weiterhin nichts ab.

## 10. Meilenstein 25: Betragsfilter (`wiederkehrend.md` 9.4)

Eigene Betragsfilter der Empfänger gehören zur Sicherung (Feld `wiederkehrend` der
Empfängerform in Inhaltsprüfsumme und `inhalt`); `schemaversion` ≥ 6, ältere Sicherungen
werden ohne Einstellungen eingespielt. Die Vorgabe der Instanz gehört nicht dazu und
bleibt beim Einspielen unverändert.

## 11. Meilenstein 27: Tags an Empfängern (`sammel.md` 2)

Empfänger-Tags gehören zum Buchbestand: `schemaversion` ≥ 7; ältere Sicherungen werden ohne
Empfänger-Tags eingespielt. Keine neue Objektart, `anzahl` unverändert; die Inhaltsprüfsumme rechnet mit
den Protokollformen (Empfänger mit `tags` nur bei Vorhandensein), sodass Prüfsummen ohne Empfänger-Tags
gleich bleiben. Manuell angelegte Dublettenverdachte sind gewöhnliche Verdachte (Objektart `verdacht`).
`verdacht` an Buchungen und Dublettenvorschläge sind abgeleitet und nicht Teil der Sicherung.

## 12. Meilenstein 30: Regeln mit Ausdruck und Tags (`kategorisierung.md` 8)

Die Tags der Regeln gehören zum Buchbestand, die Kategorie einer Regel darf
leer sein: `schemaversion` ≥ 9. Keine neue Objektart, `anzahl` unverändert;
die Inhaltsprüfsumme rechnet mit den Protokollformen (`protokoll.md` 22:
ohne `ausdruck` und `ausdruck_form`, `tag_ids` nur bei Vorhandensein),
sodass Prüfsummen von Beständen ohne Regel-Tags gleich bleiben. Sicherungen
der Versionen 1 bis 8 lassen sich weiter einspielen (Regeln ohne Tags; in
kontor-tests nicht prüfbar, E-273). `inhalt_ungueltig` (5.1) zusätzlich,
wenn eine Regel auf einen Tag verweist, den es nicht gibt.

## 13. Meilenstein 31: Automatische Regeln und Sperren (`lernmodell.md` 9)

Die Vermerke `automatisch`/`empfaenger_id` der Regeln und die Sperren der
Empfänger gehören zum Buchbestand (Objektarten `regel` und `empfaenger`,
keine neue Objektart, `anzahl` unverändert; Inhaltsprüfsumme über die
Protokollformen, Bestände ohne sie behalten ihre Prüfsumme). Nicht gesichert:
Einstellungen des Lernmodells (`lernmodell.md` 8.3), das Gemerkte der
Bestellnummer-Mails (`erwartungen.md` 14.4). `schemaversion` ≥ 9.

## 14. Meilenstein 32 (Definition 4)

Wiederholungen geplanter Zahlungen gehören zur Objektart `erwartung`
(`sammel3.md` 14.5): `schemaversion` ≥ 10; Protokollform und
Inhaltsprüfsumme tragen `wiederholung` nur bei Erwartungen mit Wiederholung.
Beim Einspielen werden gleichnamige Konten bereinigt (`sammel3.md` 1.3),
ältere Sicherungen mit Standardkategorien und Personen-Tags „Torsten“/„Tina“
umgewandelt (`sammel3.md` 2.1, 5; nicht prüfbar, E-296). Keine neue
Objektart.

## 15. Feature `sicherung-stuendlich` (D-302, `sicherungspunkte.md`)

- **Schemaversion 11:** neue Tabelle `einstellung (schluessel, wert)` mit den gesetzten Einstellungen
  `lern_regeln_automatisch`, `lern_schwelle_promille`, `wk_filter_modus`, `wk_filter_toleranz`. Sie gehören
  nicht zu `anzahl` und Inhaltsprüfsumme. Beim Einspielen ab Version 11 werden diese Einstellungen ersetzt, auch wenn
  der Buchbestand identisch ist (dann ohne Änderung im Protokoll); ältere Sicherungen lassen sie unverändert.
- **Ablauf des Einspielens** (5.3 ergänzt, `sicherungspunkte.md` 5.1): In derselben Schreibtransaktion wird zuerst
  der bestehende Stand als Sicherungspunkt gesichert (scheitert das: 409 `sicherung_vorher_fehlgeschlagen`, nichts
  geändert), nach dem Einfügen der Prüfwert gegen den Sollwert geprüft. Zusätzlich 409 `mail_abruf_laeuft`, solange
  ein Mail-Abruf läuft. Die Antwort enthält zusätzlich `vorher` und `ziel`.

## 16. Feature `konto-typ-inhaber` (D-310, `datenmodell.md` 21)

- **Schemaversion 12:** neue Tabelle `konto_inhaber (konto_id, vorname, nachname)`, je Konto mit Inhaber eine Zeile
  (Teil der Objektart `konto`). Der Kontotyp steht wie bisher in `konto.art`.
- Die Form eines Kontos ohne Inhaber ist unverändert; `anzahl` und Inhaltsprüfsumme bleiben für Bestände ohne Inhaber
  gleich. Sicherungen der Schemaversion 1–11 werden ohne Inhaber gelesen (3.4): Einspielen entfernt vorhandene Inhaber.
