# Entscheidungen des Implementierungs-Threads

Je Eintrag: Nummer, Frage, Entscheidung, Begründung. Verweise: K =
`kontor-tests/spec/konzept.md`, E-0xx = `kontor-tests/spec/api/entscheidungen.md`,
DM = `spec/api/datenmodell.md`.

## D-001 Paketaufbau und Abhängigkeiten

- **Frage:** Struktur und Laufzeitabhängigkeiten des Pakets `kontor`.
- **Entscheidung:** src-Layout (`src/kontor`), setuptools; Abhängigkeiten nur
  FastAPI, Starlette, python-multipart (Datei-Upload), uvicorn (Server).
  SQLite über die Standardbibliothek, kein ORM.
- **Begründung:** wenige, per pip installierbare Abhängigkeiten; das
  physische Schema bleibt vollständig unter Kontrolle.

## D-002 Strenge Validierung ohne Pydantic-Lax-Modus

- **Frage:** Wie werden Anfragekörper und Query-Parameter geprüft?
- **Entscheidung:** Eigene, kleine Schemaprüfung (`validierung.py`):
  Ganzzahlen nur als JSON-Ganzzahl (kein `12.0`, keine Zeichenkette, kein
  Boolean), unbekannte Felder → 422 `validierung`, Fehlerdetails als Liste
  `{ort, meldung}`. Query-Booleans akzeptieren `true`/`false`/`1`/`0`.
- **Begründung:** Pydantic würde im Standardmodus `12.0` und `"12"` als
  Ganzzahl annehmen (E-004 verbietet das); die eigene Prüfung erzeugt direkt
  das Fehlerformat aus E-019.

## D-003 Datenbankzugriff

- **Frage:** Verbindungen, Transaktionen, IDs.
- **Entscheidung:** Je Anfrage eine eigene SQLite-Verbindung auf
  `config.aktive_datenbank`, WAL-Journal, schreibende Operationen in
  `BEGIN IMMEDIATE … COMMIT`. IDs über `AUTOINCREMENT` (nie wiederverwendet).
  Beträge sind `INTEGER` mit `CHECK (typeof(betrag) = 'integer')` und
  Bereichsprüfung ±999 999 999 999 – Gleitkommazahlen können nicht
  gespeichert werden.
- **Begründung:** kein globaler Zustand (mehrere Apps je Prozess), Import und
  laufende App sehen sofort denselben Bestand, Atomarität für Import und
  Mehrfachbearbeitung.

## D-004 IBAN an Nicht-Bestandskonten

- **Frage:** E-025 erlaubt `validierung` oder `iban_ungueltig`.
- **Entscheidung:** 422 `iban_ungueltig`.
- **Begründung:** Der Fehler betrifft genau das Feld IBAN; ein fachlicher
  Code ist für die Oberfläche aussagekräftiger.

## D-005 Gesperrte Buchungen (Status abgeglichen)

- **Frage:** E-026 lässt offen, ob das Setzen eines unveränderten Werts eine
  Änderung ist.
- **Entscheidung:** PATCH mit unverändertem `datum`, `empfaenger_id` oder
  `verwendungszweck` → 200 ohne Wirkung. Kategorie setzen (einzeln und
  mehrfach), Splits ersetzen und Löschen werden bei abgeglichenen Buchungen
  immer mit 409 `buchung_gesperrt` abgelehnt, auch wenn sich nichts ändern
  würde.
- **Begründung:** PATCH bleibt idempotent; die übrigen Operationen sind
  ausdrücklich ändernd, eine immer gleiche Antwort ist einfacher zu
  verstehen.

## D-006 Prüfreihenfolgen der Buchungsendpunkte

- **Entscheidung:**
  - PATCH: Schema (422) → Buchung vorhanden (404) → Empfänger/Tags vorhanden
    (422 `referenz_unbekannt`) → 409 `buchung_gesperrt` → 409
    `status_uebergang_unzulaessig`.
  - Splits ersetzen: Schema → 404 → 409 gesperrt → `zu_wenige_splits` →
    `buchung_unausgeglichen` → `referenz_unbekannt`.
  - Kategorie setzen: Schema → 404 → 409 gesperrt → `kategorie_ungueltig` →
    `nicht_kategorisierbar`.
  - Anlegen: Schema → `zu_wenige_splits` → `buchung_unausgeglichen` →
    `referenz_unbekannt` (Konto, Empfänger, Tag).
  - Mehrfach-Kategorie wie in openapi.yaml; Mehrfach-Tags: Schema →
    unbekannte Buchungen → unbekannte Tags (beide 422 `referenz_unbekannt`
    mit `details.buchung_ids` bzw. `details.tag_ids`).
- **Begründung:** entspricht openapi.yaml, wo festgelegt; sonst „Anfrage vor
  Zustand“.

## D-007 Dublettenverdacht zusammenführen bei abgeglichener Buchung

- **Frage:** Was, wenn die verdächtige (neu importierte) Buchung inzwischen
  abgeglichen ist?
- **Entscheidung:** 409 `konflikt`; nichts wird geändert.
- **Begründung:** Zusammenführen löscht die Buchung; abgeglichene Buchungen
  sind gegen Löschen gesperrt (DM 3.1). Andere Codes sieht openapi.yaml für
  diesen Endpunkt nicht vor.

## D-008 KMyMoney: leere Namen

- **Frage:** `ACCOUNT@name`, `PAYEE@name`, `TAG@name` vorhanden, aber leer.
- **Entscheidung:** wie ein fehlendes Pflichtattribut →
  `import_inhalt_ungueltig`.
- **Begründung:** Die Schemas `Konto`, `Empfaenger`, `Tag` verlangen
  `minLength: 1`; ein leerer Name könnte sonst ungültige API-Antworten
  erzeugen.

## D-009 KMyMoney: Randfälle der Abbildung

- **Entscheidung:**
  - Jedes Konto, dessen ID mit `AStd::` beginnt, gilt als Standardkonto.
    `parentaccount` auf ein `AStd::`-Konto oder leer → Wurzelkonto.
  - Nicht numerisches `ACCOUNT@type` → wie „sonstige“ (Konto übersprungen,
    `konto_uebersprungen`).
  - Leeres `currency`/`commodity` gilt wie fehlend (EUR).
  - Ein Zyklus in den Elternbeziehungen der Datei wird aufgebrochen (Konto
    wird Wurzelkonto).
  - Leerraum vor `<` (DM 10.1 Schritt 3) = Leerzeichen, Tab, CR, LF.
  - Eine DTD mit internem Teil wird beim Lesen des DOCTYPE erkannt und als
    `import_format_ungueltig` gemeldet, bevor Entitäten verarbeitet werden;
    externe DTDs/Entitäten werden nie geladen (expat ohne
    Parameter-Entitäten).
  - `KEYVALUEPAIRS` werden nur direkt am `ACCOUNT` gelesen.
- **Begründung:** sicher, deterministisch, im Sinne von DM 10.1/10.2.

## D-010 KMyMoney: Warnungen bei wiederholten Importen

- **Frage:** DM 10.5 legt Warnungen eines zweiten Imports nicht fest.
- **Entscheidung:** Dateieigenschaften (`kontoart_ersetzt`,
  `konto_uebersprungen`, `fremdwaehrung`, `hierarchie_angepasst`,
  `buchung_uebersprungen`) werden bei jedem Lauf gemeldet; `iban_ungueltig`
  für jedes nicht über `extern_id` zugeordnete Bestandskonto;
  `iban_doppelt` und `eroeffnungsdatum_ungueltig` nur beim Neuanlegen;
  `buchung_ausgeglichen` für jede nicht über `extern_ids` zugeordnete
  Transaktion (auch wenn sie als Dublette zusammengeführt wird);
  `empfaenger_zusammengefasst`/`tag_zusammengefasst` nur bei Treffern aus
  demselben Lauf (DM 10.3).
- **Begründung:** Warnungen sollen nur auf tatsächlich Neues hinweisen, ohne
  Dateieigenschaften zu verschweigen.

## D-011 Dublettenprüfung: Empfängername

- **Frage:** Welcher Empfängername der neuen Buchung wird mit `passend`
  verglichen?
- **Entscheidung:** Der Name des Kontor-Empfängers, dem der KMyMoney-Payee
  zugeordnet wurde (bei Erstimport identisch mit `PAYEE@name`).
- **Begründung:** Die angelegte Buchung trüge genau diesen Empfänger.

## D-012 Mock-Plugins

- **Entscheidung:** Prüfreihenfolge: Argumente (`ValueError`) →
  Szenario-Fehler → unbekannte IBAN bzw. unbekanntes Postfach. Die
  Datendatei wird in jedem Mock-Plugin vollständig geprüft (Bank und Mail).
  Eingebauter Datensatz: zwei Konten (Giro, Tagesgeld, Test-IBANs mit BLZ
  00000000), monatlich ab Januar 2015 fortlaufend erzeugte Umsätze (Gehalt,
  Miete, Einkäufe, Strom, Sparrate, Quartalszinsen) und je Postfach eine
  Bestellmail pro Monat; Beträge deterministisch über SHA-256 der
  Monatskennung. `TanErforderlich.anforderung_id` = `mock-tan-<heute>`.
- **Begründung:** liefert für jedes simulierte „heute“ Daten im Vorjahr,
  bereits Geliefertes bleibt unverändert.

## D-013 Echte Plugins in Meilenstein 1

- **Entscheidung:** `FintsBankPlugin` (`kontor.plugins.fints`) und
  `ImapMailPlugin` (`kontor.plugins.imap`) werfen bei jedem Abruf
  `PluginNichtVerfuegbar`; ihre Erzeugung tut nichts (E-017).

## D-014 Mock-Daten im Buch

- **Frage:** Wie kommen im Mock-Modus Daten in das Buch, solange die
  Bank-Synchronisation (Meilenstein 2) fehlt?
- **Entscheidung:** Über den KMyMoney-Import synthetischer Dateien (z. B.
  `kontor-tests/fixtures/kmy/standard.kmy`) per Oberfläche oder
  `python -m kontor import`. Die Mock-Plugins sind erzeugbar und geprüft,
  werden aber noch nicht abgerufen.
- **Begründung:** Abruf in das Buch ist laut plugins.md später.

## D-015 Weboberfläche

- **Entscheidung:** Vanilla-JS-SPA ohne Build-Schritt und ohne externe
  Ressourcen, Hash-Routing (`#/uebersicht`, `#/konto/<id>`, …). Navigation
  mit allen Einträgen aus K 5; nicht umgesetzte Bereiche (Wiederkehrende
  Buchungen, Kredite, Berichte) sind mit „später“ gekennzeichnet, ebenso
  „Als Dublette markieren“ im Kontextmenü (dafür gibt es in M1 keine
  API). Zusätzlich „Alle Buchungen“ unten in der Navigation. Kontextmenü per
  Rechtsklick, Umschalt+F10 oder langer Berührung (550 ms). Layout
  (Navigationsbreite, eingeklappt) in `localStorage`. PWA-Manifest, aber noch
  kein Service Worker. Beträge werden zur Anzeige nicht umgekehrt: in der
  Kontoansicht der kontobezogene Betrag, sonst der Umsatz (DM 3.3).
  Der Mock-Hinweis wird serverseitig in das HTML geschrieben (plugins.md 6).
- **Begründung:** K 5 verlangt eine schnelle SPA; ohne Build und CDN bleibt
  der Betrieb offline im Heimnetz möglich.

## D-016 Kommandozeile

- **Entscheidung:** `python -m kontor serve [--host] [--port]` und
  `python -m kontor import DATEI` (auch als Skript `kontor`), Konfiguration
  aus `KONTOR_*`. Alternativ `uvicorn --factory kontor.app:create_app`.

## D-017 Sonstiges

- FastAPIs eigene Doku-Endpunkte (`/docs`, `/openapi.json`) sind
  abgeschaltet; die verbindliche OpenAPI liegt in kontor-tests.
- Unerwartete Fehler unter `/api/` → 500 `interner_fehler` im Fehlerformat,
  mit Header `X-Kontor-Modus`; Details nur im Server-Log.
- Pfad-IDs außerhalb des 64-Bit-Bereichs gelten als nicht vorhanden (404).

---

# Meilenstein 2

Weitere Abkürzungen: SY = `spec/api/synchronisation.md`, KA =
`spec/api/kategorisierung.md`, PL = `spec/api/plugins.md`.

## D-018 Aufbau und Schema für Meilenstein 2

- **Frage:** Wo liegen Synchronisation und Regeln, wie wird das Schema erweitert?
- **Entscheidung:** `kontor.sync.SyncDienst` (je App-Instanz in
  `app.state.sync`) bündelt Läufe, Übernahme, Abgleich, TAN, PIN, App-Uhr und
  Planer; `kontor.regeln` enthält Regeln und Vorschläge. Neue Tabellen
  (`regel`, `vorschlag`, `sync_lauf`, `sync_lauf_konto`, `sync_konto_zustand`,
  `sync_kennung`, `tan_anforderung`, `benachrichtigung`) werden mit
  `CREATE TABLE IF NOT EXISTS` angelegt, `schema_version` = 2; eine
  M1-Datenbank wird beim Start ohne Datenverlust erweitert. Gemerkte
  Kennungen (SY 4.3) liegen getrennt von `buchung_extern`, damit sie das
  Löschen einer Buchung überdauern.
- **Begründung:** Arbeitsspeicher-Zustand (Plugin, PIN, TAN-Kennung,
  simulierte Uhr) gehört zur App-Instanz, nicht zum Prozess (mehrere Apps je
  Prozess in Tests).

## D-019 Mock-Bank: Prüfreihenfolge und Anforderungskennung (ersetzt Teile von D-012)

- **Entscheidung:** Prüfreihenfolge nach PL 7.2: `umsaetze()` PIN →
  Szenario-Fehler → Argumente (`von > bis`, IBAN) → TAN → Daten; `konten()`
  PIN → Szenario-Fehler → Daten. `anforderung_id` = `MOCK-TAN-<heute>`
  (statt `mock-tan-<heute>` aus D-012). PIN und TAN werden mit
  `hmac.compare_digest` verglichen und nie in Meldungen oder `repr()`
  ausgegeben; `MockDaten.__repr__` verschweigt `bank.pin`/`bank.tan`. Ein
  vorhandener, aber nicht textueller `bank.pin`/`bank.tan` macht die
  Datendatei ungültig (`KonfigurationsFehler`).
- **Begründung:** PL 7.2 legt Reihenfolge und Kennung verbindlich fest.

## D-020 TAN-Bild des Mocks

- **Entscheidung:** Ein deterministisches 8-Bit-Graustufen-PNG (264 × 264
  Pixel) im Stil eines QR-Codes: 25 × 25 Module aus SHA-256 der
  `anforderung_id` mit drei Suchmustern. Es ist kein lesbarer QR-Code und
  enthält die Kennung nicht im Klartext.
- **Begründung:** PL 7.2 verlangt nur ein gültiges, von der Kennung
  abhängiges PNG; ein echter QR-Encoder wäre eine zusätzliche Abhängigkeit ohne
  fachlichen Nutzen für den Mock.

## D-021 Speicherung von TAN-Anforderungen

- **Entscheidung:** Bild und Bildtyp liegen in der Datenbank, solange die
  Anforderung offen ist; beim Beantworten, Ablauf, Abbruch und Neustart wird
  das Bild gelöscht (`hat_bild` bleibt über den Bildtyp erhalten). Die interne
  `anforderung_id` und die Plugin-Instanz leben nur im Arbeitsspeicher; fehlt
  dieser Kontext bei einer Antwort (z. B. weil eine andere App-Instanz auf
  derselben Datenbank läuft), wird die Anforderung abgebrochen und 409
  `tan_nicht_offen` gemeldet.
- **Begründung:** SY 7.2 („speichert Bild und Bildtyp“), SY 7.1 (Kennung nie
  in der Datenbank); keine unnötigen Daten nach Erledigung.

## D-022 Prüfreihenfolgen der M2-Endpunkte

- **Entscheidung:**
  - `POST /api/sync`: Körper (422) → TAN-Abläufe prüfen → 409 `sync_laeuft`
    → 409 `tan_ausstehend` → Lauf.
  - `POST /api/tan-anforderungen/{id}/antwort`: 404 → Körper (422) → Ablauf
    (409 `tan_abgelaufen`) → 409 `tan_nicht_offen` → Plugin (SY 7.3).
  - `PUT /api/mock/zeit`: 409 `nur_mock_modus` vor der Körperprüfung;
    Sekundenbruchteile werden angenommen und verworfen.
  - Regeln: Körper (422 `validierung`) → 404 (PATCH) → 422
    `kategorie_ungueltig` → 422 `referenz_unbekannt` (`details.konto_ids`).
  - Vorschlag einzeln: Körper → 404 → 409 `buchung_gesperrt` → 409
    `kein_vorschlag`; mehrfach wie openapi.yaml.
  - `POST /api/regeln/anwenden` und `POST /api/sync` akzeptieren auch einen
    leeren Körper (wie `{}`).
- **Begründung:** „Anfrage vor Zustand“ wie D-006; wo openapi.yaml/SY eine
  Reihenfolge nennen, gilt diese.

## D-023 Sonderfälle von TanErforderlich

- **Entscheidung:** Wirft bereits `konten()` `TanErforderlich`, scheitert der
  Lauf mit Code `tan_erforderlich` (ohne Konten, ohne TAN-Anforderung).
  Verlangt das Plugin nach einer TAN-Antwort für dasselbe Konto erneut eine
  TAN, gilt das als „anderer Fehler“ (SY 7.3): Anforderung abgebrochen, Konto
  fehlgeschlagen mit `tan_erforderlich`, übrige Konten laufen weiter.
- **Begründung:** SY beschreibt TAN-Anforderungen nur für den Umsatzabruf
  eines Kontos; so bleibt jeder Lauf endlich und ohne Schleifen.

## D-024 Randfälle der Kontozuordnung und Übernahme

- **Entscheidung:** Liefert das Plugin dieselbe (normalisierte) IBAN
  mehrfach, zählt der erste Eintrag. Eine Bankkonto-Art außerhalb
  girokonto/sparkonto/kreditkonto wird als `girokonto` angelegt. Liefert ein
  Abruf dieselbe `umsatz_id` zweimal, zählt die Wiederholung als
  `buchungen_vorhanden`. Die IBAN-Prüfziffer wird beim Anlegen nicht
  geprüft (die Bank ist maßgeblich).
- **Begründung:** Robust gegen fehlerhafte Plugin-Daten, ohne Daten zu
  verlieren; Zählungsinvariante aus SY 2.2 bleibt erhalten.

## D-025 Benachrichtigungen

- **Entscheidung:** `sync_fehler` je unterschiedlichem Fehlercode eines
  fehlgeschlagenen Laufs (entprellt über ungelesene Benachrichtigungen gleichen
  Schlüssels). `tan_erforderlich` und `tan_abgelaufen` haben je Anforderung
  eindeutige Schlüssel und werden immer erzeugt. Ein manueller Abbruch einer
  TAN-Anforderung erzeugt keine Benachrichtigung. Texte sind feste deutsche
  Sätze ohne Plugin-Meldungen (keine Geheimnisse möglich).
- **Begründung:** SY 6, 7.2, 7.4, 11.

## D-026 Zeitstempel und App-Uhr

- **Entscheidung:** Läufe, Kontozustände, TAN-Anforderungen,
  Benachrichtigungen und bei der Synchronisation entstehende
  Dublettenverdachte verwenden die App-Uhr (SY 8). Der KMyMoney-Import
  (`importiert_am`, Verdachte aus dem Import) verwendet weiterhin die
  Systemzeit wie in M1. `GET /api/mock/zeit` meldet `simuliert = true`,
  sobald die Zeit gesetzt wurde oder `mock_heute` konfiguriert ist.
- **Begründung:** SY 8 nennt ausdrücklich Läufe, TAN, Benachrichtigungen und
  Planer; das Importverhalten aus M1 bleibt unverändert (E-029).

## D-027 Planer-Thread

- **Entscheidung:** Start im ASGI-Lifespan, erster Takt nach 1 s, danach alle
  30 s; Ende beim Lifespan-Ende (Thread wird beendet und abgewartet). Fehler
  in einem Takt werden geloggt, der Thread läuft weiter. Läuft gerade ein
  manueller Lauf derselben App, lässt der Takt aus (kein Warten).
- **Begründung:** SY 9 (erster Takt ≤ 5 s, danach mindestens alle 60 s).

## D-028 Neustart

- **Entscheidung:** `create_app` setzt laufende/wartende Läufe und deren
  wartende/ausstehende Konten auf `abgebrochen` (`beendet_am` = App-Uhr der
  neuen Instanz) und offene TAN-Anforderungen auf `abgebrochen`. Konten, die
  vor dem Abbruch abgefragt wurden (wartende), behalten `von`/`bis`.
- **Begründung:** SY 10, SY 2.2 („null bei abgebrochen ohne Abfrage“).

## D-029 Regeln: Speicherung und Auswertung

- **Entscheidung:** Bedingungen als JSON-Liste an der Regel; `wert` unverändert
  gespeichert. Eine Bedingung `konto_id` muss auf ein Bestandskonto verweisen
  (sonst 422 `referenz_unbekannt`). Die Sicht einer Buchung für Regeln:
  Empfängername, Verwendungszweck, Regelbetrag = Summe der Splits auf
  Bestandskonten, Kontenmenge = Bestandskonten der Splits.
- **Begründung:** KA 1.1, 4.

## D-030 Vorschläge

- **Entscheidung:** Eigene Tabelle `vorschlag` (eine Zeile je Buchung, wird
  mit der Buchung gelöscht). Erledigt durch annehmen/ablehnen, Kategorie
  setzen (einzeln, mehrfach – auch mit gleicher Kategorie), Splits ersetzen
  und eine tatsächliche Statusänderung auf `bestaetigt`/`abgeglichen`.
  Ablehnen setzt den Gegensplit auf `vorher_konto_id` bzw. – wenn das Konto
  nicht mehr existiert – auf „Unkategorisiert“.
- **Begründung:** KA 5.

## D-031 Vorgabepriorität gedeckelt

- **Frage:** Was, wenn größte Priorität + 10 über 1 000 000 liegt?
- **Entscheidung:** Vorgabe = min(größte + 10, 1 000 000).
- **Begründung:** KA 1 begrenzt `prioritaet` auf 1 000 000; ein Anlegen ohne
  Priorität soll nie an der Vorgabe scheitern.

## D-032 Weboberfläche für Meilenstein 2

- **Entscheidung:** Neue Bereiche Synchronisation (Start mit optionalem
  Zeitraum, Status, Läufe, Kontozustände, PIN-Eingabe als Passwortfeld ohne
  Autovervollständigung, Mock-Uhr), Regeln (Dialog mit Bedingungseditor,
  Probelauf/Anwenden), Benachrichtigungen (Glocke im Kopf, Abfrage bei jedem
  Seitenwechsel und alle 30 s) und TAN-Seite `#/tan/<id>`. Der Pfad
  `/tan/<id>` aus den Benachrichtigungen liefert die Oberfläche aus, die
  daraus `#/tan/<id>` macht. „QR-Code speichern“ lädt das Bild als Datei
  herunter, „Teilen …“ nutzt die Web-Share-API mit Datei (deaktiviert, wenn der
  Browser das nicht kann). Vorschläge erscheinen in der Buchungsliste als
  Marke „Vorschlag“ mit ✓/✗; Mehrfachauswahl und Kontextmenü bieten
  annehmen/ablehnen; Filter „Kategorie-Vorschlag“. Die Oberfläche nutzt nur
  Endpunkte aus openapi.yaml.
- **Begründung:** Auftrag des Koordinators; K 5, K 6 (TAN-Seite mit
  Speichern/Teilen), K 7. `meilensteine.md` nennt die TAN-Seite zwar unter
  „Nicht in M2“ (gemeint: nicht getestet); sie schadet nicht und macht den
  TAN-Ablauf bedienbar.

## D-033 Echtes FinTS-Plugin in M2

- **Entscheidung:** Weiterhin Platzhalter (D-013): erzeugbar mit
  `pin_quelle` (wird nie aufgerufen), Abrufe werfen `PluginNichtVerfuegbar`;
  ein Lauf im Echtbetrieb endet als `fehlgeschlagen` mit
  `plugin_nicht_verfuegbar`.
- **Begründung:** PL 7.3; echte Anbindung in M6.

## D-034 Aufbau und Schema für Meilenstein 3

- **Entscheidung:** Neue Module `protokoll.py` (Änderungsprotokoll, Rückgängig)
  und `pflege.py` (Empfängerverwaltung, Erfassungshilfe, Umbuchungen,
  Abstimmung, Suche, Konto mit Buchungen löschen). Schemaversion 3: neue
  Tabellen `empfaenger_alias` (Alias, `ekey` eindeutig über alle Empfänger),
  `abstimmung`, `aenderung`, `aenderung_eintrag` (Protokollform als JSON);
  neue Spalten `empfaenger.standardkategorie_id`, `buchung.gegen_iban`,
  `split.abstimmung_id`; `vorschlag.quelle` erlaubt zusätzlich
  `standardkategorie`.
- **Migration:** `schema_anlegen` legt fehlende Tabellen an, ergänzt fehlende
  Spalten per `ALTER TABLE … ADD COLUMN` und baut `vorschlag` mit erweitertem
  CHECK neu auf (Inhalt wird übernommen) – in einer Transaktion, ohne
  Datenverlust. Getestet mit dem Schema von M2 (`tests/test_m3_eigen.py`,
  `tests/daten/schema_m2.sql`).
- **Begründung:** Auftrag (Migration ohne Datenverlust); SQLite kann CHECK
  nicht nachträglich ändern.

## D-035 Erfassung der Nettowirkung

- **Frage:** Wie entstehen die Einträge einer Änderung, ohne jede Operation
  einzeln zu instrumentieren?
- **Entscheidung:** Jede Operation läuft in genau einer Transaktion
  (`protokoll.protokolliert`). Temporäre Trigger der Verbindung merken jedes
  berührte Objekt (Kindtabellen wie `split`, `buchung_tag`, `vorschlag`,
  `empfaenger_alias`, `verdacht_kandidat` zählen für ihr Elternobjekt) sowie
  hinzugekommene/weggefallene Umsatzkennungen. Am Ende wird die Protokollform
  *nachher* auf der schreibenden Verbindung bestimmt und *vorher* auf einer
  zweiten, lesenden Verbindung: Im WAL-Modus sieht diese den letzten
  bestätigten Stand, also genau den Zustand vor der Operation. Nur Objekte mit
  verschiedener Form werden eingetragen; ohne Eintrag entsteht keine Änderung.
  Die Trigger verwenden kein `INSERT OR IGNORE`, weil die Konfliktbehandlung
  einer äußeren Anweisung (UPSERT) sie überschreiben würde.
- **Folge:** Eine Operation, die mehrere Änderungen erzeugt (Synchronisation:
  Kontozuordnung, je Konto, Umbuchungserkennung), schreibt jede in einer
  eigenen Transaktion. Die Protokollform wird mit denselben Funktionen
  berechnet wie die REST-Antworten.
- **Begründung:** protokoll.md 3.2 (Nettowirkung), T 3.5; die Erfassung ist
  für alle bestehenden und künftigen Operationen gleich und kann keine
  Nebenwirkung übersehen.

## D-036 Rückgängig: Umsetzung der Zustands- und Bezugsprüfung

- **Entscheidung:** Rückgängig ist selbst eine protokollierte Operation. Je
  Schritt (absteigende IDs) wird zuerst die aktuelle Form jedes Objekts mit
  `nachher` verglichen, dann werden die Objekte gelöscht und aus `vorher` mit
  ihren IDs neu eingefügt (Splits mit ihren IDs und ihrer Reihenfolge); ein
  umbenannter Tag wird in der Zeile zurückbenannt, damit Zuordnungen anderer
  Buchungen bleiben. Fremdschlüssel werden für die Transaktion aufgeschoben;
  danach prüft `bezuege_pruefen` alle Verweise und Zyklen auf dem gesamten
  Bestand. Eindeutigkeit sichern die UNIQUE-Bedingungen (IBAN, Name, Alias-
  `ekey`, Tag-Name). Zusätzlich darf die Nettowirkung nur Objekte der
  rückgängig gemachten Änderungen betreffen (sonst z. B. ein kaskadierend
  entfernter Tag an einer anderen Buchung). Jede Verletzung → 409
  `rueckgaengig_konflikt`, die Transaktion wird verworfen.
- **Wirksamkeit:** `rueckgaengig_durch` wird gespeichert und bei jedem
  (Un-)Wirksamwerden rekursiv an die durch die Änderung rückgängig gemachten
  Änderungen weitergegeben (protokoll.md 6.5).
- **Synchronisationszustand:** Nach jedem Rückgängig entfallen Einträge in
  `/api/sync/konten`, deren Konto nicht mehr existiert (protokoll.md 6.4).
- **Begründung:** protokoll.md 6, E-047, E-048, E-057.

## D-037 Sperre bei Vorschlägen und Dubletten

- **Entscheidung:** Einzelnes `POST /api/buchungen/{id}/vorschlag`: eine
  abgeglichene Buchung antwortet wie in M2 immer 409 `buchung_gesperrt`
  (vor `kein_vorschlag`); eine nur abgestimmte Buchung nur bei `ablehnen`.
  Mehrfach: erst `kein_vorschlag`, dann bei `ablehnen` `buchung_gesperrt`
  mit allen gesperrten IDs. Dublette zusammenführen mit gesperrter zu
  entfernender Buchung antwortet ab M3 `buchung_gesperrt` (statt bisher
  `konflikt` bei abgeglichenen; openapi.yaml 2.1.0).
- **Begründung:** buchhaltungspflege.md 5.4, kategorisierung.md 6; M2-
  Verhalten bleibt, wo die Spezifikation nichts Neues sagt.

## D-038 Erfassungshilfe: Prüfung unpassender Felder

- **Entscheidung:** „Feld bei unpassender `art`“ (422 `validierung`) gilt für
  `gegenkonto_id` bei jeder Angabe außerhalb von `umbuchung`; für
  `kategorie_id` bei `umbuchung` nur, wenn der Wert nicht `null` ist.
  „Beide Empfängerfelder“ gilt, wenn `empfaenger_id` nicht `null` ist und
  `empfaenger_name` angegeben ist. Ein angegebener Empfänger (ID oder Name)
  liefert die Standardkategorie für `ausgabe`/`einnahme` ohne Kategorie;
  „Unkategorisiert“ wird dafür als `vorher_konto_id` angelegt. Für
  `korrektur` gilt die Standardkategorie nicht (Tabelle in 3).
- **Begründung:** `null` bedeutet in allen Schemas „nicht gesetzt“; so kann
  die Oberfläche ein leeres Feld ohne Sonderfall senden.

## D-039 Umbuchungen: Kandidaten und Zusammenführen

- **Entscheidung:** Kandidaten zusätzlich ohne offenen Vorschlag (folgt aus
  dem Gegensplit auf „Unkategorisiert“). Zusammenführen verschiebt den
  Bankseiten-Split von Y mit unveränderter ID nach X (Position 1), löscht die
  beiden Splits auf „Unkategorisiert“, übernimmt Kennungen und Tags und löscht
  Y wie beim Löschen einer Buchung (offene Verdachte). Bei der automatischen
  Erkennung werden nur Paare mit einer in dieser Kontoverarbeitung neu
  angelegten Buchung zusammengeführt (eigene Transaktion und Änderung).
- **Begründung:** buchhaltungspflege.md 4.

## D-040 Konto mit Buchungen löschen: Probelauf

- **Entscheidung:** Der Probelauf führt die echte Operation in einem
  SQLite-Sicherungspunkt aus und verwirft sie (`ROLLBACK TO`). Dadurch liefert
  er garantiert dasselbe Ergebnis wie der echte Lauf; ein dabei angelegtes
  „Unkategorisiert“ verschwindet wieder (`ziel_konto_id = null`), IDs werden
  nicht verbraucht. Der Eintrag in `/api/sync/konten` eines gelöschten
  Bankkontos bleibt (Betriebszustand, kein Buchbestand); ein späterer Lauf
  legt das Konto neu an und überschreibt die Zuordnung.
- **Begründung:** loeschen.md 4 („Ein Probelauf liefert dasselbe Ergebnis“).

## D-041 Volltextsuche

- **Entscheidung:** Die Suche rechnet in Python über alle Objekte (`snorm`
  je Feld, Felder getrennt, UND über die Wörter). Ein SQL-Index (FTS5) wäre
  mit der Normalisierung aus E-056 (Teilzeichenketten nach NFKD-Faltung)
  nicht genau nachzubilden.
- **Begründung:** buchhaltungspflege.md 6; Buchbestände eines Haushalts
  bleiben klein genug (Leistung wird in M7 bewertet).

## D-042 Weboberfläche für Meilenstein 3

- **Entscheidung:** Neue Bereiche Empfänger, Umbuchungen, Kontenabstimmung,
  Änderungsprotokoll und Suche (Feld im Kopf). Strg+Z nimmt die neueste
  wirksame Änderung zurück, die selbst kein Rückgängig ist; mehrfaches Strg+Z
  geht so schrittweise zurück. Strg+Y bzw. Strg+Umschalt+Z nimmt das neueste
  wirksame Rückgängig zurück (Wiederholen). Beides wirkt nicht in
  Eingabefeldern und nicht bei offenem Dialog; für Touch gibt es den Knopf ↶
  im Kopf. Die Erfassungshilfe ersetzt den bisherigen Dialog „Neue Buchung“
  (Splitbuchungen weiterhin über „Bearbeiten / splitten“). Konto löschen:
  Ein Probelauf mit `loeschen` entscheidet, ob das Konto unbenutzt ist (dann
  einfache Rückfrage und `DELETE`); sonst Dialog nach loeschen.md 5 ohne
  Vorauswahl. Die stabilen `data-testid` folgen in M8.
- **Begründung:** Auftrag des Koordinators; loeschen.md 5; K 14.

## D-043 GnuCash-SQLite nur als Kopie im Arbeitsspeicher

- **Entscheidung:** Eine SQLite-Datei wird nicht auf der Platte geöffnet,
  sondern ihre Bytes werden mit `sqlite3.Connection.deserialize` in eine
  Datenbank im Arbeitsspeicher geladen (zusätzlich `PRAGMA query_only`).
  Pfad- und Bytes-Eingabe sowie REST verhalten sich damit gleich.
- **Begründung:** gnucash.md 4.1 verlangt „keine Änderung an der Datei, keine
  Nebendateien“; selbst ein schreibgeschütztes Öffnen kann bei WAL-Dateien
  `-shm`-Dateien anlegen. Beschädigte Dateien fallen beim Lesen als
  `sqlite3.DatabaseError` auf (`import_datei_beschaedigt`).

## D-044 GnuCash: gemeinsames Modell, Zuordnungsreihenfolge, Empfänger der Dublettenprüfung

- **Entscheidung:** XML und SQLite werden in dasselbe neutrale Modell
  übersetzt; Prüfung, Zuordnung und Anlegen sind danach identisch.
  Konten werden wie beim KMyMoney-Import in Dokumentreihenfolge mit
  Elternkonten vor ihren Kindern verarbeitet (Regel 2 braucht das bereits
  zugeordnete Elternkonto). Eine nach Regel 1 oder 2 zugeordnete vorhandene
  Kontozeile zählt für den Rest des Laufs als vergeben. Für die
  Dublettenprüfung (gnucash.md 8) wird als Empfänger der Buchung der
  Empfängername nach 6.2 (Beschreibung nach `strip()`) verglichen, nicht der
  Name eines per Alias zugeordneten Empfängers.
- **Begründung:** wörtliche Lesart von gnucash.md 7/8; die Vergleichsfunktion
  „passend“ (ekey) macht Groß-/Kleinschreibung und Satzzeichen ohnehin
  unerheblich.

## D-045 KMyMoney-Import nach GnuCash-Import

- **Entscheidung:** Regel 2 des KMyMoney-Imports berücksichtigt zusätzlich
  Konten mit `gnc:`-Kennung; neue Regel 3 für Bestandskonten ohne gültige
  IBAN (Art, Name, Elternkonto eines `gnc:`-Kontos ohne IBAN, kleinste ID).
  Eine vorhandene Kennung wird nie überschrieben (`UPDATE … WHERE extern_id
  IS NULL`). Ohne GnuCash-Konten im Buch ändert sich nichts.
- **Begründung:** gnucash.md 7 letzter Absatz, E-068.

## D-046 Lernmodell: Training bei jeder Anfrage, Brüche über ganze Zahlen

- **Entscheidung:** Kein Zwischenspeicher – die Trainingsmenge wird bei
  jeder Abfrage (Zustand, Vorhersage, Anwenden, Erfassen) und in der
  Synchronisation je Bankkonto einmal aus dem Buchbestand gelesen (eine
  SQL-Abfrage über Buchungen, Splits und Vorschläge). `S(c)` wird als
  Zähler/Nenner aus ganzen Zahlen gebildet und erst dann zu `Fraction`;
  Sicherheit `⌊1000·P⌋` per Ganzzahldivision. Der Knopf „Neu trainieren“ der
  Oberfläche liest nur den Zustand neu (es gibt keinen Trainingsbefehl, E-071).
- **Begründung:** lernmodell.md 1 und 4; ein Haushaltsbuch hat wenige tausend
  Buchungen, das Training dauert Millisekunden. Ein Cache müsste bei jeder
  Änderung (auch Rückgängig, Umbenennen von Empfängern) verworfen werden.

## D-047 Vorschlag.sicherheit nur bei quelle = lernmodell

- **Entscheidung:** Tabelle `vorschlag` erhält die Spalte `sicherheit`
  (NULL bei Regel und Standardkategorie); die Antwort enthält das Feld nur
  bei `quelle = "lernmodell"`. Ersetzt eine Regel einen Lernmodell-Vorschlag,
  wird `sicherheit` geleert. Die Protokollform übernimmt das Feld, sodass
  Rückgängig es exakt wiederherstellt.
- **Begründung:** openapi.yaml `Vorschlag` (additionalProperties false,
  `sicherheit` nur beim Lernmodell); M2/M3-Antworten bleiben unverändert.

## D-048 Split-Vorlagen: Speicherung, Prüfreihenfolge, PATCH

- **Entscheidung:** Tabelle `vorlage` mit Bedingungen und Teilen als JSON
  (wie Regeln); `gesamtbetrag` wird nie gespeichert, sondern abgeleitet.
  `PATCH` prüft zuerst die Existenz (404), dann den Körper (422
  `validierung`), dann Bezüge (`kategorie_ungueltig`, `referenz_unbekannt`).
  Eine Bedingung auf `betrag` ist ein Validierungsfehler; die Pflicht zu einer
  Empfänger-Bedingung gilt für jede übergebene Bedingungsliste.
- **Begründung:** vorlagen.md 1 und 2; gleiche Reihenfolge wie bei Regeln.

## D-049 Synchronisation: Vorlagen-Treffer ohne „Unkategorisiert“

- **Entscheidung:** Das technische Konto „Unkategorisiert“ wird in einem
  Abruf erst angelegt, wenn ein neuer Umsatz es braucht (also nicht für
  reine Vorlagen-Treffer). Treffer werden mit dem Bestandskonto-Split an
  erster Stelle und den Teilen in Vorlagenreihenfolge angelegt; offene
  Dublettenverdachte entstehen wie bei jedem neuen Umsatz.
- **Begründung:** vorlagen.md 3/4; ohne Vorlagen unverändert (E-029).

## D-050 Text der Benachrichtigungen split_abweichung und konto_fehlt

- **Entscheidung:** `split_abweichung`: Titel „Split-Vorlage passt nicht“,
  Text nennt Betrag der Buchung, Vorlagenname und erwarteten Gesamtbetrag
  (deutsches Format, Ganzzahlarithmetik) und rät zum Anpassen.
  `konto_fehlt`: Titel „Bankkonto ohne Konto“, Text nennt Name und IBAN und
  fragt nach Wiederherstellen oder Ignorieren. Server und Oberfläche
  verstehen die Links `/buchungen/<id>` und `/sync/konten` (wie `/tan/<id>`).
- **Begründung:** vorlagen.md 6, synchronisation.md 16.5.

## D-051 Gelöschte Bankkonten: Entscheidung und Rückgängig

- **Entscheidung:** Die Entscheidung steht in `sync_konto_zustand`
  (`entscheidung`, `entscheidung_buchungen`); der Status wird bei jedem Lesen
  aus „gibt es ein Konto mit der IBAN?“ und der Entscheidung abgeleitet. Bei
  `ignorieren` wird der Pflichtwert `buchungen` gespeichert, aber nie
  ausgegeben. Eine Kontozuordnung, die ein gelöschtes Bankkonto
  wiederherstellt, vermerkt (Aenderungs-ID, IBAN) in `sync_wiederherstellung`
  über einen Haken nach dem Speichern der Änderung in derselben
  Transaktion. Rückgängig einer `sync_kontozuordnung` entfernt den Eintrag in
  `/api/sync/konten` nur für erstmals angelegte Konten; vermerkte
  Wiederherstellungen behalten ihn (Status `konto_fehlt`). Das frühere
  pauschale Entfernen von Einträgen ohne Konto entfällt (protokoll.md 6.4).
  Das Vergessen der Kennungen bei „alle“ läuft durch die Protokoll-Trigger
  (`kennungen_weg`), sodass Rückgängig sie wieder merkt.
- **Begründung:** synchronisation.md 16, E-083, E-084.

## D-052 Weboberfläche für Meilenstein 4

- **Entscheidung:** Neue Bereiche „Split-Vorlagen“ und „Lernmodell“ in der
  Navigation; Import-Seite mit Wahl der Quelle (an der Dateiendung
  vorgewählt); Lernmodell-Vorschläge tragen die Marke „Lernmodell xx,x %“;
  Split-Vorlagen werden im Dialog mit Live-Summe angelegt/bearbeitet, auch
  aus einer Buchung über das Kontextmenü; Abweichungen erscheinen oben auf
  der Vorlagenseite mit „Vorlage anpassen …“. Der Dialog für gelöschte
  Bankkonten hat keine Vorauswahl (E-061/16.3) und bietet nach
  „wiederherstellen“ einen sofortigen Lauf an. Alles nur über REST.
- **Begründung:** Auftrag des Koordinators; vorlagen.md, lernmodell.md,
  synchronisation.md 16.3.

## D-053 Schema der Sicherungsdatei (M9)

- **Entscheidung:** `kontor.sqlite` hat ein eigenes, schmales Schema
  (`sicherung.SPALTEN`), versioniert über `schemaversion` = `sicherung.SCHEMAVERSION`
  (beginnt bei 1, unabhängig von der Schemaversion der App-Datenbank). Tabellen mit
  denselben Namen wie in der App: `konto`, `empfaenger`, `empfaenger_alias`, `tag`,
  `buchung`, `split`, `buchung_tag`, `buchung_extern`, `vorschlag`, `regel`,
  `dublettenverdacht`, `verdacht_kandidat`, `abstimmung`, `vorlage` (nur fachliche
  Spalten, ohne abgeleitete wie `name_cf`/`ekey`), dazu `sync_kennung` (alle gemerkten
  Kennungen), `sync_konto_zustand` (inkl. Entscheidung, ohne Status) und `id_zaehler`
  (`objekt`, `hoechste_id` für `konto` … `vorlage` und `split`, aus `sqlite_sequence`).
  Keine AUTOINCREMENT-Spalten, keine Trigger, Views oder Fremdschlüssel. Die Datei
  entsteht vollständig im Arbeitsspeicher (`serialize`) nach `VACUUM` und wird nie auf
  dem Server abgelegt; das Manifest ist eingerücktes UTF-8-JSON.
- **Begründung:** sicherung.md 3.1 lässt das Schema frei; ein eigenes Schema ohne
  Protokoll- und Betriebstabellen enthält konstruktiv keine Reste (2.2) und bleibt mit
  Standardwerkzeugen lesbar. Eine eigene Versionsnummer trennt Änderungen der
  Sicherungsdatei von internen Schemaänderungen.

## D-054 Prüfung hochgeladener Sicherungen

- **Entscheidung:** Reihenfolge exakt nach sicherung.md 5.1. Ergänzend: ZIP-Einträge
  mit anderer Kompression als Stored/Deflate → `zip_inhalt`; entpackte Größe höchstens
  4 GiB insgesamt (Manifest höchstens 1 MiB), beim Entpacken laufend gezählt →
  `zip_inhalt`; beschädigte Einträge (CRC, Deflate) → `kein_zip`. Manifest:
  `formatversion`/`schemaversion` ganze Zahlen ≥ 1 (keine Wahrheitswerte), `erstellt`
  im Format `JJJJ-MM-TTTHH:MM:SSZ`; die Schlüssel von `anzahl` werden nur bei
  unterstützter Version geprüft (unbekannte Objektart einer neueren Version ergibt
  `version_nicht_unterstuetzt`, nicht `manifest_ungueltig`). Die Datenbank wird nur im
  Arbeitsspeicher geöffnet (`deserialize`, `trusted_schema = OFF`, `query_only`);
  falscher Dateikopf oder eine Dateilänge, die nicht zur Seitenzahl im Kopf passt, ist
  `datenbank_ungueltig`. `datenbank_fremd`: andere Objekttypen als `table`/`index`,
  virtuelle Tabellen, Systemtabellen außer `sqlite_sequence`, versteckte/generierte
  Spalten, fehlende oder zusätzliche Tabellen bzw. Spalten; zusätzliche Indizes sind
  erlaubt.
- **Begründung:** sicherung.md 5.1, 8; E-093 (Schutz gegen untergeschobene Dateien).

## D-055 Inhaltsprüfung in einer App-Datenbank im Arbeitsspeicher

- **Entscheidung:** Die Zeilen der Sicherung werden typgeprüft (Ganzzahl, Text,
  0/1, `NULL` nur wo erlaubt) und in eine leere Datenbank mit dem vollständigen
  App-Schema im Arbeitsspeicher geladen. `inhalt_ungueltig` bei: verletzten
  CHECK-/UNIQUE-Regeln, `foreign_key_check`, Buchungen mit weniger als zwei Splits
  oder Summe ≠ 0, ungültigen Datumswerten/Zeitstempeln, Regeln bzw. Vorlagen, die die
  Validierung von `POST /api/regeln` bzw. `/api/vorlagen` nicht bestehen, der
  Bezugsprüfung aus protokoll.md 6.1 Schritt 5 (inkl. Zyklen), unbekannten Zählern
  oder Entscheidungen. Kein Fehler: Kennungen ohne Buchung, Einträge je Bankkonto mit
  `konto_id` ohne Konto (sicherung.md 5.1, E-096). Die Protokollformen für `anzahl`,
  `inhalt_sha256` und den Vergleich entstehen mit denselben Funktionen wie die
  REST-Antworten.
- **Begründung:** Damit ist „die Datei wurde vollständig und richtig gelesen“ genau
  dann erfüllt, wenn die Inhaltsprüfsumme stimmt (E-091).

## D-056 Einspielen, Rückgängig und Laufsperre

- **Entscheidung:** Die Prüfschritte 4 (Bestätigung) und 5 (Laufsperre) gelten
  auch, wenn der Inhalt identisch ist (sie stehen in 5.1 vor dem Vergleich).
  Während des Einspielens hält `SyncDienst.ohne_lauf()` die Laufsperre; ein Lauf
  `laeuft` → 409 `sync_laeuft`, `wartet_auf_tan` → 409 `tan_ausstehend`; neue Läufe
  (auch des Planers) bekommen in der Zeit 409 `sync_laeuft`. In
  `protokoll.protokolliert(quelle="sicherung")` wird der Vergleich in derselben
  Schreibtransaktion wiederholt; bei Unterschied werden alle Tabellen des
  Buchbestands geleert und aus der Sicherung neu befüllt – die Nettowirkung ergibt
  genau die Einträge nach 5.2. Gemerkte Kennungen werden als Differenz geändert (über
  die Protokoll-Trigger, damit Rückgängig sie herstellt). Der Zustand je Bankkonto wird
  ersetzt und vorher/nachher in der neuen Betriebstabelle `sicherung_zustand` zur
  Änderung vermerkt (App-Schemaversion 5); Rückgängig einer so vermerkten Änderung setzt
  den Stand davor und vermerkt seinerseits vorher/nachher, sodass Wiederholen und
  weitere Rückgängig-Schritte beliebig verkettet funktionieren. ID-Zähler:
  `sqlite_sequence` = Maximum aus hier, Quelle und eingespielten IDs; Rückgängig setzt
  sie nie zurück.
- **Begründung:** sicherung.md 5.3, 6, 7; protokoll.md 10.

## D-057 Python-Sicherung und Zeitpunkt

- **Entscheidung:** `erstelle_sicherung(config)` legt die Datenbank samt Schema nur an
  bzw. migriert sie nur, wenn sie fehlt oder eine ältere Schemaversion hat; sonst
  öffnet sie sie ausschließlich lesend (eine Lesetransaktion). `erstellt` kommt aus
  derselben App-Uhr wie bei REST (`SyncDienst.jetzt`, also `mock_heute` 12:00:00Z im
  Mock-Modus ohne simulierte Uhr). `GET /api/sicherung` verwendet die simulierte Uhr der
  App; die Antwort trägt `Cache-Control: no-store`.
- **Begründung:** python-api.md 11.1, sicherung.md 3.1, 4.

## D-058 Weboberfläche für Meilenstein 9

- **Entscheidung:** Neuer Bereich „Datensicherung“ (`#/sicherung`) in der Navigation:
  „Sicherung herunterladen“ (Link auf `GET /api/sicherung`, Dateiname vom Server);
  „Sicherung einspielen“ führt immer zuerst den Probelauf aus und zeigt Manifest,
  Unterschied je Objektart und betroffene abgestimmte/abgeglichene Buchungen; bei
  identischem Inhalt nur einen Hinweis. Einspielen erst nach Häkchen „Ich habe
  verstanden …“ und einem zweiten Dialog „Gesamten Bestand ersetzen?“; danach
  Ergebnis mit Link ins Änderungsprotokoll und „Einspielen rückgängig machen“.
  Fehler werden je `details.grund` verständlich erklärt („Es wurde nichts geändert.“).
  Alles nur über REST, responsiv (Tabelle scrollt auf schmalen Bildschirmen).
- **Begründung:** Auftrag des Koordinators; sicherung.md 5.3 („die Oberfläche zeigt
  vorher das Ergebnis eines Probelaufs“), E-092.

## D-059 Speicherung der Kredite und Zuordnungen ohne Fremdschlüssel auf Buchungen

- **Entscheidung:** Drei Tabellen: `kredit` (Parameter, Sondertilgungen und Bedingungen als JSON,
  `konto_id` UNIQUE), `kredit_zuordnung (kredit_id, faelligkeit, buchung_id UNIQUE)` und
  `kredit_abgleich (kredit_id, jahr, restschuld, zinsen, buchung_id NULL)`; alle drei bilden die Objektart
  `kredit` im Protokoll. Die Spalten `buchung_id` haben bewusst keinen Fremdschlüssel: Rückgängig entfernt
  Buchungen kurzzeitig und fügt sie mit derselben ID wieder ein; ein `ON DELETE CASCADE` würde dabei
  Zuordnungen außerhalb der Änderung verändern. Stattdessen entfernt `protokoll.protokolliert` am Ende jeder
  Operation Zuordnungen gelöschter Buchungen und setzt `buchung_id` eines Abgleichs auf null – in derselben
  Änderung (kredite.md 2.3). Beim Rückgängig prüft die Bezugsprüfung vorher, ob alle Bezüge bestehen
  (sonst 409 `rueckgaengig_konflikt`), sodass das Aufräumen dort nie greift.
- **Begründung:** Eine Stelle für alle Löschwege (Buchung löschen, Dublettenauflösung, Konto mit Buchungen
  löschen), ohne jede Operation einzeln anzupassen; exakt rückgängig machbar.

## D-060 Tilgungsplan nur mit ganzen Zahlen

- **Entscheidung:** Der Zins einer Periode wird als Zähler `Σ R_j · sollzins · länge_j` über dem Nenner
  `basis · 1 000 000` geführt und mit `(2·Z + N) // (2·N)` kaufmännisch gerundet; keine `Fraction`, keine
  Gleitkommazahl. Sondertilgungen werden nach Datum stabil sortiert (gleiche Daten in Eingabereihenfolge).
  `kontor.kredite.tilgungsplan` akzeptiert Daten als `datetime.date` (nicht `datetime.datetime`) oder Text,
  lehnt unbekannte Schlüssel ab (`ValueError`) und gibt Daten immer als Text zurück. Eine entfallende
  Nullrate (3.5 Schritt 3) wird wörtlich umgesetzt (siehe W-003).
- **Begründung:** kredite.md 3.4, T 22; identisch mit dem Bruch-Orakel der Tests.

## D-061 Ratenerkennung, Zuordnen und Prüfreihenfolgen der Kredit-Endpunkte

- **Entscheidung:** Passende Rate: Fälligkeiten im Abstand 0, 1, …, 5 Tage um das Buchungsdatum, jeweils
  die frühere zuerst; erste passende gewinnt (= kleinster Abstand, bei Gleichstand die frühere). Bei
  `PATCH`, `zuordnen` und `jahresabgleich` gilt 404 vor 422 (wie bei Vorlagen). `POST …/zuordnen` und
  `…/jahresabgleich` mit `trocken` rechnen in einem Sicherungspunkt und verwerfen ihn (gleiche Antwort,
  keine Änderung); beim Probelauf des Jahresabgleichs kann `korrektur_splits` die ID des Kontos
  „Korrekturen“ enthalten, das erst beim Bestätigen angelegt wird. Der Jahresabgleich entfernt bei den
  abgeglichenen Raten einen etwaigen offenen Vorschlag (wie die Statusänderung auf `abgeglichen`,
  kategorisierung.md 5). Das Löschen eines Kontos mit Kreditbezug wird direkt nach der Existenzprüfung
  abgelehnt (auch im Probelauf, loeschen.md 7).
- **Begründung:** kredite.md 2–5, E-103, E-105, E-110.

## D-062 Wiederkehrende Buchungen: Berechnung und Texte

- **Entscheidung:** Die Einträge (Buchung × Bestandskonto, ohne Darlehenskonten von Krediten) entstehen in
  einer SQL-Abfrage mit Gruppierung je Buchung und Konto; Ketten, Status und Ereignisse werden in Python
  genau nach wiederkehrend.md 2–3 gebildet. Benachrichtigungen: Titel „Neuer Empfänger: …“, „Geänderter
  Betrag: …“, „Zahlung ausgeblieben: …“; Texte nennen Empfänger, Beträge (Euro-Text aus Cent), Rhythmus und
  Datum. Ein Schlüssel wird nie zweimal angelegt (gelesen oder nicht).
- **Begründung:** wiederkehrend.md 3, 6; E-100.

## D-063 Automatische Prüfung nach Läufen

- **Entscheidung:** Ob ein Bankkonto vor dem Lauf schon erfolgreich abgerufen wurde, wird beim Zuordnen
  der Konten in `sync_lauf_konto.vorher_abgerufen` festgehalten (Schema 6). Die neuen Buchungen eines Laufs
  sind die in den Änderungen `sync_konto` der Gruppe `sync:<lauf>` angelegten, noch existierenden Buchungen,
  deren Umsatzkennung zu einem solchen Bankkonto gehört. Geprüft wird nach `erfolgreich`, `fehlgeschlagen`
  (auch beim Scheitern vor dem Kontenabruf) und `abgebrochen` (TAN abgebrochen oder abgelaufen) – jeweils
  in einer eigenen Transaktion nach dem Endstatus.
- **Begründung:** wiederkehrend.md 5, synchronisation.md 17.3.

## D-064 Berichte

- **Entscheidung:** Prüfreihenfolge: Query-Parameter (Typ, Intervall, `von > bis` bei beiden Angaben) →
  `referenz_unbekannt` → `konto_ungueltig` (nur Einnahmen/Ausgaben) → Vorgaben für `von`/`bis` und
  `von > bis` danach → `bericht_zu_gross`. Kontostände: je Konto die kumulierten Tagessummen bis `bis`,
  Wert per Binärsuche; bei `unterkonten` die Summe über alle Nachfahren. Einnahmen/Ausgaben: Summen je
  (Datum, Konto) der berücksichtigten Buchungen, Zuordnung zur Periode per Binärsuche; `kategorien` enthält
  auch Konten, deren Summe 0 ist, sofern sie einen berücksichtigten Split haben.
- **Begründung:** berichte.md 1–3.

## D-065 Export

- **Entscheidung:** Beide Exporte nutzen die Filter der Buchungsliste (gemeinsame Auswertung in
  `app.buchungsfilter`, ohne `seite`/`pro_seite`). CSV mit `csv.writer` (`;`, `\r\n`, `QUOTE_MINIMAL`), BOM
  vorangestellt. PDF mit **reportlab** (neue Abhängigkeit; reine Python-Bibliothek, Standardschrift
  Helvetica, keine Schriften oder Dateien aus dem Netz), A4 quer, je Buchung genau eine Textzeile
  „[#id] TT.MM.JJJJ Betrag Empfänger Verwendungszweck Kategorie Status“ (der variable Teil wird auf die
  Zeilenbreite gekürzt), Kopf mit Filter, „Anzahl Buchungen: n“ und Summe auf Seite 1. Anwendertexte werden
  bereinigt: `[`/`]` werden zu runden Klammern, Steuerzeichen zu Leerzeichen, „Anzahl Buchungen:“ wird
  entschärft – so kann kein Text eine Marke oder die Anzahlzeile vortäuschen. Nicht darstellbare Zeichen
  ersetzt reportlab.
- **Begründung:** berichte.md 4, 5; E-107, E-108.

## D-066 Sicherung ab M5

- **Entscheidung:** Schemaversion der Sicherungsdatei 2 mit den Tabellen `kredit`, `kredit_zuordnung`,
  `kredit_abgleich` und dem Zähler `kredit`. `anzahl`/Inhaltsprüfsumme enthalten `kredit` nur bei
  vorhandenen Krediten, `unterschied` nur, wenn Sicherung oder Bestand Kredite haben. Sicherungen der
  Version 1 (ohne Kredittabellen) werden weiter eingespielt (Kredite gelten als leer). Pflichtschlüssel in
  `anzahl` sind die acht aus M9; `kredit` ist erst ab Version 2 erlaubt. Die Inhaltsprüfung prüft Kredite
  wie `POST /api/kredite` (Schema, Kontoarten, Plan berechenbar) und die Bezüge aus kredite.md 2.3.
- **Begründung:** sicherung.md 2.5, 3.4; E-109.

## D-067 Weboberfläche für Meilenstein 5

- **Entscheidung:** Navigationseinträge „Wiederkehrende Buchungen“ (`#/wiederkehrend`, auch Link
  `/wiederkehrend`), „Kredite“ (`#/kredite`, `#/kredit/<id>`) und „Berichte“ (`#/berichte`) sind aktiv.
  Sollzins wird in Prozent mit bis zu vier Nachkommastellen eingegeben und ganzzahlig in Millionstel
  umgerechnet. Der Jahresabgleich-Dialog erlaubt das Bestätigen erst nach einem Probelauf mit unveränderten
  Eingaben. Das Liniendiagramm ist ein selbst gezeichnetes SVG mit Zeitachse nach Kalendertagen,
  überschneidungsfreien Datumsmarken, Fadenkreuz mit Tooltip, Legende ab zwei Reihen und Tabellenansicht;
  Reihenfarben aus einer geprüften kategorialen Palette (hell/dunkel), die Farbe folgt dem Konto. Export-
  Knöpfe stehen in jeder Buchungsliste und auf der Berichtsseite. Alles nur über REST, ohne externe
  Ressourcen; Tabellen scrollen auf schmalen Bildschirmen in ihrer Hülle.
- **Begründung:** Auftrag des Koordinators; K 9–11, K 14; kredite.md 5 („die Oberfläche zeigt vorher das
  Ergebnis des Probelaufs“).

## D-068 Umsetzung von E-111 (ersetzt den letzten Satz von D-060 und ergänzt D-061)

- **Entscheidung:** Eine Schlussrate 0 bleibt als Zeile im Plan (`letzte_faelligkeit` nie null); Zeilen mit
  `rate = 0` werden weder bei der Synchronisation noch beim Zuordnen einer Zahlung zugeordnet. Der Probelauf
  des Jahresabgleichs legt nichts an und rechnet ohne Sicherungspunkt-Buchung: Fehlt das Konto
  „Korrekturen“, hat der betreffende Korrektursplit `konto_id = null`; die Oberfläche zeigt dafür
  „Korrekturen (wird beim Bestätigen angelegt)“.
- **Begründung:** kredite.md 3.5, 4.1, 5 in der Fassung von E-111.

## D-069 FinTS-Plugin: python-fints auf mittlerer Ebene, ein Dialog je Aufruf

- **Frage:** Wie wird python-fints eingesetzt, damit Prüfreihenfolge, Fehlerabbildung (fints.md 3.6) und „nur
  lesend“ (3.7) exakt gelten?
- **Entscheidung:** `FinTS3PinTanClient` liefert Synchronisierung, Dialoginitialisierung, Signatur (PIN/TAN im
  HNSHA) und Verschlüsselungsumschlag; Aufträge baut das Plugin selbst aus den Segmentklassen (`HKSPA1`,
  `HKCAZ1` mit camt.052.001.08 bzw. die höchste angebotene `HKKAZ`-Version, `HKTAN` über
  `_get_tan_segment`) und sendet sie mit `dialog.send`. Die hohen Methoden (`get_transactions…`) werden nicht
  verwendet. Je `konten`/`umsaetze` genau ein Dialog (plus beim ersten Mal der Synchronisierungsdialog); die PIN
  wird unmittelbar davor einmal über `pin_quelle` geholt. BPD, UPD und System-ID bleiben als
  `deconstruct`-Daten nur im Arbeitsspeicher der Plugin-Instanz. Rückmeldungen werden je Auftrag und je
  Nachricht ausgewertet (PIN-Codes → `BankPinFalsch`, 3938 → `BankZugangGesperrt`, 9210 →
  `BankKontoUnbekannt`, sonst 9xxx → `BankFehler` mit `details.rueckmeldung`; 9050 „teilweise fehlerhaft“ nur,
  wenn es keinen genaueren Code gibt). Antwortsegmente ohne Bezugssegment (z. B. HISPA mancher Banken) werden
  angenommen, wenn kein Segment mit Bezug vorliegt. Die Abbildung von camt und MT940 sowie die Hash-Kennung
  sind eigener Code nach fints.md 3.4 (nicht `mt-940`/`camt_parser` der Bibliothek, deren Vorzeichen und
  Verkettung abweichen). Der Logger `fints` gibt nichts weiter (`propagate = False`, `NullHandler`).
- **Begründung:** fints.md 1 erlaubt die freie Verwendung der Bibliothek; nur so ist jede Rückmeldung und jedes
  gesendete Segment unter eigener Kontrolle (E-114, E-123).

## D-070 FinTS-TAN: Auftragsreferenz als Kennung, offener Dialog im Arbeitsspeicher

- **Entscheidung:** `anforderung_id` ist die Auftragsreferenz aus HITAN. Der Dialog, der Auftrag, das
  HITAN-Segment und die schon gelieferten Seiten bleiben in der Plugin-Instanz; eine neue Anforderung für
  dasselbe Konto beendet eine ältere. 9941 lässt die Anforderung offen, 9955 oder ein geschlossener Dialog
  beenden sie (`TanAbgelaufen`). Aufsetzpunkte werden nach der TAN im selben Dialog weiter abgerufen (mit HKTAN
  Prozess 4, wenn die BPD es verlangen). Eine Rückmeldung 3955 (entkoppelte Freigabe) ergibt `BankFehler`.
- **Begründung:** fints.md 3.5; K 6 (nur QR-TAN).

## D-071 Starke Kundenauthentifizierung schon beim Dialogbeginn

- **Frage:** Manche Banken verlangen eine TAN bereits für die Dialoginitialisierung (HKTAN Prozess 4 zu HKIDN →
  0030). fints.md 3.5 regelt nur die TAN zum Umsatzabruf.
- **Entscheidung:** Nicht unterstützt: Der Dialog wird beendet, `konten`/`umsaetze` werfen `BankFehler` mit
  einer deutschen Meldung. Die FinTS-Attrappe antwortet hier mit 3076.
- **Begründung:** Außerhalb der Spezifikation; eine halbe Umsetzung ohne Test wäre riskanter als ein klarer
  Fehler (Lauf scheitert ohne Datenverlust, Benachrichtigung `sync_fehler`).

## D-072 Ausgehende Verbindungen ohne Proxy und Umleitungen

- **Entscheidung:** FinTS, OAuth und ntfy laufen über `kontor.netz.http_anfrage` (`http.client`): genau eine
  Anfrage, keine Umleitungen, keine Proxy-Variablen der Umgebung, kein `.netrc`, nichts wird protokolliert.
  IMAP über `imaplib` (`IMAP4_SSL` mit eigenem `SSLContext`). Zertifikat und Hostname werden immer geprüft; mit
  `tls_ca_datei` gelten nur deren Zertifikate, und die strenge X.509-Prüfung von Python ≥ 3.13
  (`VERIFY_X509_STRICT`) wird dann abgeschaltet, weil selbst signierte Anker oft keine Schlüsselkennungen haben.
  Die Zeitgrenzen gelten je Anfrage bzw. je Socket-Operation.
- **Begründung:** geheimnisse.md 7 („nur zu den konfigurierten Hosts“, „folgt keinen Umleitungen“); ein
  Proxy aus der Umgebung wäre ein weiterer Host, der Tokens sehen könnte.

## D-073 Geheimnisspeicher

- **Entscheidung:** Tabelle `geheimnis (name, nonce, chiffre, gesetzt_am)` in der aktiven Datenbank; AES-256-GCM
  mit dem Namen als zusätzlichen Daten. Die Schlüsseldatei wird beim ersten Schreiben mit `O_EXCL` und Rechten
  0600 angelegt (Base64 + `\n`); ein vorhandener, ungültiger Schlüssel wird nie überschrieben (409). Löschen mit
  `PRAGMA secure_delete = ON`. Mail-Tokens stehen als JSON (Refresh-/Access-Token, Ablauf des Access-Tokens,
  Ausstellung) unter `mail_token:<adresse casefold>`; der Ablauf des Refresh-Tokens ist kein Geheimnis und steht
  im Betriebszustand des Postfachs (für Anzeige und proaktive Prüfung ohne Entschlüsseln).
- **Begründung:** geheimnisse.md 2–4, E-116.

## D-074 Zustellung der Benachrichtigungen

- **Entscheidung:** Neue Benachrichtigungen entstehen weiter an ihren bisherigen Stellen; ein Trigger setzt sie
  auf `ausstehend`, wenn `meta.zustellung_neu` (von `create_app` je nach Plugin geschrieben) das verlangt, sonst
  bleiben sie `keine`. Der erste Versuch läuft am Ende jeder REST-Anfrage (auch bei Fehlerantworten, z. B.
  `tan_abgelaufen`) und am Ende jedes Planer-Takts für alle noch nie versuchten; die Prüfung wiederkehrender
  Buchungen stellt vor ihrer Antwort zu und liest die Benachrichtigungen danach neu. Wiederholungen nur im
  Planer-Takt bzw. über `POST /api/benachrichtigungen/zustellen`. Eine Sperre je App verhindert gleichzeitige
  Zustellvorgänge. Der letzte Fehlschlag steht in `meta.zustellung_fehler` (Code, Meldung, Zeitpunkt; nie
  Token oder Antwortkörper). Der Planer-Thread läuft, wenn `sync_intervall_minuten` oder
  `mail_intervall_minuten` > 0 ist.
- **Begründung:** benachrichtigungen.md 4, synchronisation.md 18.2; eine Stelle für „neu“ statt Änderungen an
  allen Auslösern.

## D-075 Postfächer, Betriebszustand und Sicherung

- **Entscheidung:** Tabelle `postfach` (mit `adresse_cf UNIQUE`) ist Buchbestand (Objekt `postfach` in
  `protokoll.OBJEKTE`); `postfach_zustand` und `mail_nachricht` hängen an `adresse_cf`.
  `protokoll.protokolliert` ruft am Ende jeder Operation `geheimnisse.verwaiste_entfernen` auf: Tokens, Spiegel
  und Zustand von Adressen ohne Postfach entfallen in derselben Transaktion (Löschen, Rückgängig des Anlegens,
  Einspielen einer Sicherung). Sicherungsdatei Schemaversion 3 mit Tabelle `postfach`; Version 2 wird ohne
  Postfächer gelesen. Eine doppelte Adresse beim Rückgängig ergibt über die Eindeutigkeit 409
  `rueckgaengig_konflikt`.
- **Begründung:** mail.md 2, 6.5; protokoll.md 12; sicherung.md 2.6; E-118.

## D-076 Test-Benachrichtigung (App-Erweiterung)

- **Frage:** Der Auftrag verlangt in den Einstellungen eine Test-Benachrichtigung; `openapi.yaml` hat dafür keinen
  Endpunkt, die Oberfläche spricht aber nur REST.
- **Entscheidung:** Zusätzlicher Endpunkt `POST /api/benachrichtigungen/test` (nicht Teil des Vertrags): sendet
  genau eine Push-Nachricht „Kontor: Test-Benachrichtigung“ (Tag `test`, im Mock-Modus mit `[Mock] `) direkt über
  das Plugin, ohne Eintrag in der internen Liste; 200 `{"gesendet": true, "plugin": …}`, 409
  `kein_benachrichtigungs_plugin` bei `keins`, 409 `benachrichtigung_fehler` mit `details.status` bei einem
  Fehlschlag. Beim Mock-Plugin wird nichts in `gesendet` eingetragen (dort stehen nur Benachrichtigungen der
  Liste, `GET /api/mock/zustellungen`).
- **Begründung:** Prüfen der ntfy-Anbindung ohne künstlichen Auslöser; kein Einfluss auf die Liste und damit auf
  „jeder Auslöser genau eine Nachricht“.

## D-077 OAuth2-Anmeldung

- **Entscheidung:** `state` = 32 Zufallsbytes URL-sicher (43 Zeichen), `code_verifier` = 64 Zeichen aus dem
  Alphabet von RFC 7636; beide nur im Arbeitsspeicher des `MailDienst`, 10 Minuten gültig, je Postfach höchstens
  eine offene Anmeldung. Fehlen Client-ID oder lesbares Secret erst beim Abschluss, antwortet die App 409
  `oauth_client_fehlt`. Ohne `expires_in` gilt für das Access-Token eine Stunde. `GET /oauth2/rueckruf` liefert
  eine kurze deutsche HTML-Seite ohne Parameter. Abmelden widerruft beim Anbieter (Fehler ignoriert) und setzt
  `fehlt`.
- **Begründung:** mail.md 4.

## D-078 Mail-Abruf

- **Entscheidung:** Je aktivem Postfach ein Thread (`ThreadPoolExecutor`), im Echtmodus je Abruf eine neue
  `ImapMailPlugin`-Instanz mit den aktuellen Postfächern und `MailDienst.zugang`; im Mock-Modus eine
  `MockMailPlugin`-Instanz je App (vor jedem Abruf `setze_heute`). Bei `anmeldung_erforderlich` steht in `seit` der
  Beginn, der bei einem Abruf gegolten hätte; `letzter_abruf_am` bleibt dann unverändert. Gespiegelte Nachrichten
  sind je Postfach und `nachricht_id` eindeutig. Der Planer startet einen Abruf nur, wenn es ein aktives Postfach
  gibt.
- **Begründung:** mail.md 6 (Schema verlangt `seit` immer).

## D-079 PIN über systemd-creds

- **Entscheidung:** `kontor-bank-pin` wird bei jedem Bedarf als Bytes gelesen (UTF-8), genau ein abschließendes
  `\r\n` oder `\n` entfällt. `BankPinFalsch` und `BankZugangGesperrt` sperren die Quelle in der `SyncDienst`-Instanz
  (bis zum Neustart); bei `eingabe` wird die PIN in beiden Fällen verworfen. `PUT`/`DELETE /api/sync/pin` prüfen
  die Quelle vor dem Körper.
- **Begründung:** fints.md 5, synchronisation.md 18.1, E-115.

## D-080 Geheimnisse im Zugriffsprotokoll des Servers

- **Entscheidung:** `create_app` hängt an den Logger `uvicorn.access` einen Filter, der den Abfrageteil jeder
  protokollierten URL durch `?…` ersetzt (`/oauth2/rueckruf?state=…&code=…` trägt Autorisierungscode und
  `state`).
- **Begründung:** geheimnisse.md 6 Punkt 2 (kein Geheimnis in irgendeiner Logausgabe).

## D-081 Weboberfläche für Meilenstein 6

- **Entscheidung:** Neuer Bereich „Anbindungen“ (`#/anbindungen`; Links `/mail/postfaecher/<id>` markieren das
  Postfach, `/einstellungen` öffnet die Einstellungen): Bankzugang (Plugin, PIN-Quelle, PIN vorhanden),
  Geheimnisspeicher (Schlüsselquelle, Stand je Geheimnis, Setzen über Passwortfelder, die danach geleert werden,
  Löschen – Werte werden nie angezeigt), ntfy (Plugin, Zählungen, letzter Fehler, Test-Benachrichtigung,
  Ausstehende zustellen), Postfächer (Anlegen, Bearbeiten, Löschen, Status mit Ablaufwarnung unter 24 Stunden,
  Anmelden in zwei Schritten: Link öffnen, Umleitungs-URL einfügen; Abmelden). Neuer Bereich „Mails“
  (`#/mail`): Abruf starten mit Ergebnis je Postfach, Liste der gespiegelten Nachrichten mit Filter und Blättern.
  Die Synchronisationsseite blendet die PIN-Eingabe bei `systemd-creds` aus. Alles nur über REST, responsiv mit
  den vorhandenen Bausteinen.
- **Begründung:** Auftrag des Koordinators; K 3, K 6, K 13.

## D-082 TAN-Erinnerungen

- **Entscheidung:** Die Nummer der letzten Erinnerung steht in `tan_anforderung.erinnerung_nr` (Betriebszustand,
  nicht gesichert); Erinnerungen entstehen im Planer-Takt nach den TAN-Abläufen, je Schlüssel höchstens einmal.
- **Begründung:** benachrichtigungen.md 5, E-121.

## D-083 Speicherung der Anmeldedaten (M7)

- **Entscheidung:** Zwei neue Tabellen (Schemaversion 8, Migration durch `CREATE TABLE IF NOT EXISTS`):
  `anmeldung_konto` (genau eine Zeile: Passwort-Hash, Fehlversuche, `gesperrt_bis`) und `sitzung` (SHA-256 des
  Tokens, Erstellung, letzte Aktivität). Zeiten als Sekunden seit der Epoche nach `time.time()`, nie nach der
  Mock-Uhr. Das CSRF-Token wird nicht gespeichert, sondern als HMAC-SHA-256 des Sitzungstokens (Base64url,
  43 Zeichen) abgeleitet; es ist damit je Sitzung fest, übersteht Neustarts und steht in keiner Datei. Beide
  Tabellen sind Betriebszustand: weder im Protokoll noch in der Sicherung (E-135). Abgelaufene Sitzungen werden
  bei jeder neuen Anmeldung bzw. beim Zugriff gelöscht.
- **Begründung:** sicherheit.md 4.3/4.4 (nur Hash des Tokens, Systemuhr, Neustartfestigkeit); ein abgeleitetes
  Token braucht keine weitere Speicherung und ist ohne das Cookie nicht berechenbar.

## D-084 Aktivität der Sitzung bei gesperrter Datenbank

- **Entscheidung:** Die Gültigkeit wird bei jeder Anfrage in der Datenbank geprüft (Wirkung von
  `passwort_setzen` sofort). Die Aktualisierung der letzten Aktivität wartet höchstens 2 s auf die Schreibsperre;
  gelingt sie nicht (z. B. während eines langen Imports), gilt die Anfrage trotzdem als gültig und die Aktivität
  wird bei der nächsten Anfrage nachgetragen.
- **Begründung:** Lesende Anfragen sollen nicht an einer langen Schreibtransaktion hängen; der Leerlauf beträgt
  mindestens Sekunden, eine ausgelassene Aktualisierung verkürzt eine Sitzung höchstens unwesentlich.

## D-085 Schutzhülle als äußerste ASGI-Middleware

- **Entscheidung:** `kontor.schutz.Schutz` prüft in der Reihenfolge von sicherheit.md 4.6: Netz, Sitzung
  (geschützte Pfade), Herkunft, CSRF-Token, Größe – vor Routing und Validierung. Der Körper schreibender
  Anfragen wird dabei bis zur Grenze gelesen und an die App weitergereicht (bei `Content-Length` über der Grenze
  ohne Lesen abgelehnt). Sicherheitsköpfe werden an jede Antwort gehängt, auch an 5xx (letzte Absicherung in der
  Hülle). `Cache-Control: no-store` für `/api/`, HTML und alle übrigen Antworten außer `/static/` und
  `/oeffentlich/`. Die Anmeldeseite bezieht CSS, Skript und Symbol aus `/oeffentlich/`; die eigentliche
  Oberfläche (`/static/`) bleibt geschützt.
- **Begründung:** Eine zentrale Stelle schützt automatisch auch künftige Endpunkte; 401 statt 404/405/413/422
  verrät nichts über vorhandene Pfade (3.2).

## D-086 `python -m kontor` ohne Unterbefehle (ersetzt die Kommandozeile aus M1)

- **Entscheidung:** Die bisherigen Unterbefehle `serve` und `import` entfallen: `python -m kontor` startet den
  Server, jedes Argument ergibt Rückgabecode 2 (betrieb.md 2). Host und Port kommen aus `KONTOR_HOST`/`KONTOR_PORT`.
  Importe laufen über die Oberfläche bzw. `POST /api/import/kmymoney` (README zeigt `curl`). uvicorn startet mit
  `log_config=None`, damit auch seine Meldungen das Format `<STUFE> <logger>: <Meldung>` haben.
- **Begründung:** betrieb.md 2 lässt keine Argumente zu (K 6: keine Konfiguration in der Kommandozeile).

## D-087 Zugriffsprotokoll: Abfrageteil nur bei `/oauth2/` geschwärzt (ergänzt D-080)

- **Entscheidung:** Der Filter des uvicorn-Zugriffsprotokolls entfernt den Abfrageteil nur noch für Pfade unter
  `/oauth2/` (Rückruf mit `state`/`code`); alle anderen Einträge enthalten Methode, Pfad samt Abfrage und Status.
- **Begründung:** betrieb.md 7 verlangt Pfad samt Abfrage; die Schnittstelle nimmt Geheimnisse sonst nur im Körper
  an. Der OAuth-Rückruf bleibt geschützt (geheimnisse.md 6).

## D-088 Beenden während eines Laufs

- **Entscheidung:** `SyncDienst.beenden` setzt ein Beenden-Kennzeichen (kein neuer Takt, kein neuer Lauf, kein
  weiteres Konto), wartet bis `beenden_frist_sekunden` auf den Planer-Thread bzw. die Laufsperre und bricht danach
  den Lauf in der Datenbank ab (`abgebrochen`, `beendet_am`). Schreibvorgänge eines Kontos laufen unter einer
  Schreibsperre; nach dem Abbruch (`_abbruch`) schreibt der noch wartende Abruf nichts mehr, auch keine
  Zustellung. Danach `PRAGMA wal_checkpoint(TRUNCATE)`. Die Verzögerung des Mock-Plugins ist ein einfaches
  `time.sleep` in `umsaetze()`.
- **Begründung:** betrieb.md 5.2 und E-136; die Schreibsperre verhindert, dass Abbruch und Übernahme eines Kontos
  ineinander laufen.

## D-089 Leistung ohne neue Indizes und ohne Volltextindex

- **Entscheidung:** Die Filter der Buchungsliste nach Konto, Kategorie, Tag, Memo und Abstimmung werden als
  unkorrelierte Teilabfragen (`b.id IN (SELECT buchung_id …)`) formuliert; in den korrelierten Betragsabfragen
  verhindert `+s.konto_id` bzw. `+s.betrag`, dass SQLite den Index `split_konto` statt `split_buchung` wählt
  (vorher quadratisch, Konto-Filter > 1 min bei 50 000 Buchungen). Die Volltextsuche normalisiert reine
  ASCII-Texte direkt (`lower`), andere mit Zwischenspeicher, und prüft je Buchung einen zusammengesetzten Text.
  Kein FTS5-Index: die gemessenen Werte liegen weit unter den Grenzen, und ein Index müsste dieselben
  Vergleichsregeln (Teilwörter, Umlaute, NFKD) exakt nachbilden. Ergebnisse sind unverändert (M1/M3-Filter- und
  Suchtests grün).
- **Begründung:** leistung.md 3; geringstes Risiko für identische Ergebnisse.

## D-090 Weboberfläche für Meilenstein 7

- **Entscheidung:** Eigene Anmeldeseite `/anmelden` (Formular, bei fehlender Einrichtung mit Feld für den
  Einrichtungscode, Hinweis mit Restzeit bei Sperre, Weiterleitung nur auf eigene Pfade). In der Oberfläche liest
  `app.js` beim Start `GET /api/anmeldung`, sendet das CSRF-Token bei jeder schreibenden Anfrage und leitet bei
  401 zur Anmeldeseite (Rücksprung über `weiter`). Abmelden über den Knopf ⏻ im Kopf und in den Einstellungen;
  Passwort ändern unter **Einstellungen → Anmeldung**. Alles responsiv, ohne Inline-Skripte.
- **Begründung:** Auftrag des Koordinators; sicherheit.md 3.4, 6.

## D-091 Oberfläche M8 neu als ES-Module ohne Framework (ersetzt die Hash-Oberfläche aus M1–M7)

- **Entscheidung:** Die Single-Page-Oberfläche ist neu geschrieben: Pfad-Routen mit History API statt `#/…`
  (oberflaeche.md 3, E-140), Vanilla-JS als ES-Module ohne Bundler unter `/oeffentlich/app/` (`kern.js`: DOM,
  REST, Werte, Stammdaten, Meldungen, Ebenen, Rückgängig; `ui.js`: Dialoge und Kontextmenü; `baum.js`:
  Kategorienbaum, Konto-Kontextmenü, Ziehen, lange Berührung; `konto.js`: Kontoansicht mit Panels; `seiten.js`:
  übrige Seiten; `haupt.js`: Router, Kopf, Tastatur, Befehlspalette, Design, Offline, Start), Stile in
  `/oeffentlich/app.css`. Das alte `static/app.js` (2 900 Zeilen) entfällt; damit ist R-07 erledigt.
- **Begründung:** Die Hash-Routen, IDs und Bedienmuster der bisherigen Oberfläche passten nicht zum Vertrag aus
  `oberflaeche.md`; ein Umbau in derselben Datei hätte sie weiter vergrößert. Module halten jede Datei unter
  1 000 Zeilen, laufen ohne Build-Schritt und CSP-konform (`script-src 'self'`).

## D-092 Hülle nur für die Routen der Oberfläche

- **Entscheidung:** `create_app` registriert die Hülle für genau die Routen aus oberflaeche.md 3 (IDs als
  `int`) sowie `/sync/konten` und `/buchungen/<id>` (Links aus Benachrichtigungen); alle anderen Pfade außerhalb
  von `/api/` liefern 404 (sicherheit.md 7.2). Keine Sammelroute `/{pfad:path}`.
- **Begründung:** Eine Sammelroute für GET hätte auch `/api/…`-Pfade erfasst und dort 405 (`methode_nicht_erlaubt`)
  durch 404 ersetzt.

## D-093 Statische Dateien öffentlich unter `/oeffentlich/`, Service Worker unter `/sw.js`

- **Entscheidung:** Skripte, Stile, Symbole (SVG und PNG 192/512, maskierbar 512) und das Manifest liegen unter
  `/oeffentlich/` (öffentlich, sicherheit.md 3.1); `/static/` und `/manifest.webmanifest` entfallen. `/sw.js`
  (geschützt, `Cache-Control: no-cache`) legt die Hülle und die Liste der statischen Dateien in den Cache
  `kontor-huelle-1` (zuerst Netz, offline aus dem Cache), nie Antworten unter `/api/`; jede erfolgreiche Navigation
  aktualisiert die zwischengespeicherte Hülle. Neue Moduldateien müssen in `DATEIEN` in `sw.js` eingetragen werden
  (eigener Test prüft das).
- **Begründung:** oberflaeche.md 2, 18, E-146. Die Hülle enthält keinen Buchbestand, darf also offline liegen.

## D-094 Kategorienbaum: Eintrag eine Zeile hoch, Unterkategorien darunter angeordnet

- **Entscheidung:** Ein Baumeintrag (`role="treeitem"`) ist genau eine Zeile hoch; die Unterkategorien stehen im
  DOM innerhalb des Eintrags (`role="group"`), werden aber absolut darunter angeordnet; der Eintrag reserviert ihren
  Platz mit einem Außenabstand (`--nach` = Zahl der sichtbaren Nachfahren × Zeilenhöhe).
- **Begründung:** So liegt der Mittelpunkt eines Eintrags auf seiner eigenen Zeile. Klicks, Rechtsklicks, lange
  Berührungen und Ziehen „auf den Eintrag“ treffen damit die gemeinte Kategorie und nicht eine Unterkategorie.

## D-095 Rückgängig-Eintrag auch bei teilweise fehlgeschlagener Aktion

- **Entscheidung:** `aktion()` sammelt nach jeder eigenen Operation die neuen Änderungen (ohne Gruppe `sync:`),
  auch wenn ein späterer Teil fehlgeschlagen ist (z. B. Tag angelegt, Zuordnung abgelehnt), und legt sie als einen
  Eintrag auf den Stapel; danach wird die Fehlermeldung gezeigt. Dialoge werden nach Erfolg geschlossen, bevor die
  Seite neu geladen wird.
- **Begründung:** oberflaeche.md 11 legt nur den Erfolgsfall fest; was tatsächlich geändert wurde, soll sich auch
  dann mit Strg+Z zurücknehmen lassen.

## D-096 Weitere Bedienung über den Mindestumfang hinaus

- **Entscheidung:** Zusätzlich zu oberflaeche.md: Regeln anlegen/bearbeiten/löschen (Bedingungen als Zeilen
  „Feld Operator Wert“), Lernmodell und Vorlagen anwenden, Umbuchungen erkennen (Seite Dubletten), Tags umbenennen
  und löschen, Passwort ändern, Mails abrufen, Postfach anlegen, Kredit anlegen, Einnahmen/Ausgaben-Bericht,
  Mock-Uhr auf der Seite Synchronisation. Nicht mehr in der Oberfläche (nur über REST): Split-Vorlagen bearbeiten,
  Kredite bearbeiten/Raten zuordnen, Lernmodell-Vorhersage, Liste abgerufener Mails, Abstimmung aufheben,
  Synchronisation mit eigenem Zeitraum.
- **Begründung:** E-148 verlangt für diese Seiten einen Mindestumfang; die genannten Funktionen sind ohne viel Code
  möglich. Die übrigen Formulare der alten Oberfläche werden bei Bedarf nachgezogen.

## D-097 Test-Benachrichtigung nach E-138 (ersetzt D-076)

- **Entscheidung:** `POST /api/benachrichtigungen/test` folgt `benachrichtigungen.md` 8: Antwort
  `{plugin, zugestellt, gesendet, fehler}`, Mock ohne Aufruf von `senden`, ntfy genau ein Versuch, Fehlschlag als 200
  mit `fehler.status`; `keins` → 409 mit `details = {}`. W-005 erledigt.
- **Begründung:** Der Test-Thread hat die Spezifikationslücke mit E-138 geschlossen.

## D-098 AqBanking-Plugin: Konten über `listaccs` mit eigener Vorlage

- **Entscheidung:** `konten()` ruft `aqbanking-cli -D <verz> listaccs --template=…` mit den Feldern
  `$(iban)`, `$(bic)`, `$(typeAsString)`, `$(accountName)`, `$(ownerName)` auf; Datensätze beginnen mit dem
  Steuerzeichen RS (0x1E), Felder sind durch US (0x1F) getrennt. Die Kopfzeile von `listaccs` fällt so weg.
  Kontotyp-Namen nach aqbanking.md 4.1; `unknown`/`unspecified` → Girokonto, andere Typen entfallen. Die IBAN wird
  normalisiert und auf Prüfziffer geprüft; für `request --iban=` wird sie so übergeben, wie AqBanking sie kennt.
- **Begründung:** Die Standardausgabe enthält weder Kontobezeichnung noch Inhaber; Tabulatoren oder `|` könnten in
  Namen vorkommen, die Steuerzeichen praktisch nie. Der Typ als Text (`typeAsString`, Standardvorlage von
  AqBanking 6.5) ist stabiler als die interne Nummer.

## D-099 AqBanking-Plugin: Auswertung des Abrufs

- **Entscheidung:** Je `umsaetze()` genau ein `aqbanking-cli -D <verz> -P /dev/fd/N -n request --transactions
  --iban=… --fromdate=JJJJMMTT --todate=JJJJMMTT -c <temp>/abruf.ctx` mit `AQHBCI_LOGLEVEL=info`. Ausgewertet
  werden nur vollständig erkannte Diagnosezeilen (Präfix `<stufe>:<datum> <zeit>:<modul>(<pid>):<datei>: <zeile>:`),
  damit Hexdumps der Bankkommunikation nichts vortäuschen: Rückmeldungen `Result: … (NNNN: …)` (Fehler **und**
  Warnungen, da 3938 als Warnung erscheint), der letzte Status von `JobGetTransactions` und „No TAN input in
  non-interactive mode“. Reihenfolge nach aqbanking.md 5.1; Erfolg nur, wenn keine 9xxx-Rückmeldung, Rückgabecode 0
  und letzter Status `answered` (erprobt: bei 9380 steht der Auftrag trotzdem auf `answered`). Rückmeldung 0030
  gilt wie der Hinweistext als TAN-Bedarf. Ein Rückgabecode ≠ 0 ohne Rückmeldung (z. B. 2 für ein lokal
  unbekanntes Konto, nach der Prüfung über `konten()` nur bei gleichzeitiger Änderung der Konfiguration) ergibt
  `BankVerbindungsFehler`. Eine unlesbare oder fehlende Kontextdatei nach Erfolg ebenfalls.
- **Kontextdatei:** eigener kleiner Leser für das GWEN-DB-Textformat (Gruppen, `typ name="wert", "wert"`,
  URL-kodierte Werte); Beträge `Zähler/Nenner:Währung` exakt mit `Fraction` in Cent, Bruchteile von Cent → unlesbar.
  Gewählt wird die `accountInfo` mit der abgerufenen IBAN. Hash-Kennungen wie beim FinTS-Plugin
  (`kennungen_vergeben`, laufende Nummer in Lieferreihenfolge vor dem Datumsfilter, wie dort).
- **Begründung:** aqbanking.md 5.2 (Rückgabecode allein unzuverlässig); die Kontextdatei enthält Zeilenumbrüche im
  Verwendungszweck verlustfrei, eine Vorlage für `listtrans` nicht.

## D-100 AqBanking-Plugin: Prozesse, Umgebung, PIN-Datei

- **Entscheidung:** Jeder Programmaufruf läuft in einer eigenen Sitzung/Prozessgruppe (`start_new_session`) mit
  `stdin=/dev/null`, Ausgabe vollständig in Pipes (nie an Logger, stdout oder stderr). Bei Überschreiten von
  `aqbanking_timeout_sekunden` erst SIGTERM, nach 2 s SIGKILL an die Prozessgruppe, dann
  `BankZeitueberschreitung`. Je Aufruf ein eigenes temporäres Verzeichnis unter `tempfile.gettempdir()` (zur
  Laufzeit ermittelt), das auch Arbeitsverzeichnis und `TMPDIR` des Programms ist und danach entfernt wird; die
  Kontextdatei liegt in einem weiteren eigenen temporären Verzeichnis. Umgebung: die von Kontor ohne alle
  Variablen, deren Name `proxy` enthält (beliebige Schreibweise), Sprache fest `C.UTF-8` (`LANGUAGE`, `LC_*`
  entfernt bzw. gesetzt), damit die ausgewerteten Texte nicht übersetzt werden. Eine Sperre je Plugin-Instanz
  lässt höchstens ein Programm gleichzeitig laufen.
- **PIN-Datei:** Benutzer aus `aqhbci-tool4 listusers --xml` (BLZ, Benutzerkennung); je Benutzer eine Zeile
  `PIN_<BLZ>_<Kennung> = "<PIN>"` mit `\` → `\\` und `"` → `\"`. Die Datei wird vor dem Start vollständig in eine
  Pipe geschrieben (Grenze 60 000 Bytes, darüber `PluginNichtVerfuegbar`) und als `/dev/fd/N` übergeben.
  `listusers` ohne Benutzer oder mit Fehler → `PluginNichtVerfuegbar`. Eine PIN mit Zeilenumbruch oder NUL ist
  im Format nicht darstellbar → `BankPinFalsch` ohne Programmaufruf (die App verwirft sie dann).
- **Reihenfolge in `umsaetze()`:** Verfügbarkeit → `von > bis` → `tan` → Konto über `listaccs` → `pin_quelle()`
  (genau einmal) → `listusers` → `request`. `konten()` und `listusers` starten ohne `-P`.
- **Begründung:** aqbanking.md 5.3 und 6; die Prozessgruppe erfasst auch Kindprozesse, `TMPDIR` hält auch
  Zwischendateien von AqBanking selbst im aufgeräumten Verzeichnis.

## D-101 Konfiguration M10

- **Entscheidung:** `aqbanking_verzeichnis`/`aqbanking_programme`: `str`/`os.PathLike` → `Path`, leere
  Zeichenkette auch im Konstruktor → None (wie in der Umgebung); `aqbanking_timeout_sekunden` nur `int` (kein
  `bool`, keine Zeichenkette) von 1 bis 3600, in der Umgebung nur Dezimalziffern. `bank_plugin = "aqbanking"` im
  Mock-Modus ergibt wie `fints` `KonfigurationsFehler`. Die ausgelieferte `kontor.env` enthält die vier Variablen
  nur als Kommentar (Vorgabe im Betrieb bleibt `fints`); README beschreibt Einrichtung, Verzeichnis außerhalb von
  `/home` und die einmalige TAN-Freigabe in AqBanking. An der systemd-Härtung ändert sich nichts: das empfohlene
  Verzeichnis `/var/lib/kontor/aqbanking` liegt im `StateDirectory` und ist dort schreibbar.
- **Begründung:** python-api.md 16.1, aqbanking.md 7; keine Änderung, die M7-Tests der Units berühren könnte.

## D-102 Saldoabgleich: Ablage und Ablauf (M11)

- **Entscheidung:** Das Ergebnis `saldo_abgleich` steht als JSON in der neuen Spalte
  `sync_lauf_konto.saldo_abgleich` (Datenbankschema 9, Migration ergänzt die Spalte; NULL = nicht erfolgreich
  verarbeitet). Der Abgleich läuft in `SyncDienst._saldo_abgleichen` direkt nach `sync_konto` und ggf.
  `umbuchung_erkennen` desselben Bankkontos, in einer eigenen Funktion (nicht in `_abgleichen_und_buchen`, R-04).
  Die Ausgleichsbuchung ist eine eigene Änderung `sync_saldoausgleich`; „Korrekturen“ über `pflege.korrektur_id`.
  Kandidaten im Abgleich (synchronisation.md 4.4) schließen Buchungen mit einer Kennung `saldo:` aus. Der Lauf
  zählt den Saldo nicht als fachlichen Zustand: Die Sicherung ist unverändert (Ausgleichsbuchungen sind gewöhnliche
  Buchungen).
- **Begründung:** kontostand.md 2, 2.1, 2.2, 4; `sync_lauf_konto` ist Betriebszustand wie die übrigen Zählungen.

## D-103 Saldo in den Plugins (M11)

- **Entscheidung:** FinTS: `HKSAL` nur, wenn `HISALS` in der BPD und `HKSAL` unter den erlaubten
  Geschäftsvorfällen des Kontos in der UPD stehen; höchste von python-fints unterstützte Version; verlangt die
  Bank dafür eine TAN, wird nicht gefragt (Saldo None, kontostand.md 1: nie eine TAN für den Saldo). Rückmeldung
  9xxx zu `HKSAL` oder ein Verbindungsfehler nur bei dieser Abfrage → None, Umsätze bleiben. Betrag aus `Decimal`
  exakt in Cent (Bruchteile von Cent → None). AqBanking: lokale Ablehnung erkannt am Text
  `Request "getBalance" … not supported` bei Rückgabecode ≠ 0; nur dann genau ein zweiter `request` ohne
  `--balance`. Ein unlesbarer Saldoeintrag macht nur den Saldo None.
- **Begründung:** kontostand.md 1.2, 1.3, E-159, E-166.

## D-104 Oberfläche M11

- **Entscheidung:** Die URL der Kontoansicht enthält die Sortierung nur, wenn sie gewählt wurde (bisher immer
  `sortierung=-datum`); 7.1 nennt „gesetzte Filter und die Sortierung“, das Beispiel dort zeigt die Vorgabe nicht.
  Kategorien der Übersicht: Zustand unter `kontor.uebersicht.kategorien` im `localStorage` (Fehler beim Speicher
  werden ignoriert, dann eingeklappt). Die Vorschau der Aliase im Zusammenführen-Dialog bildet die Regel aus
  buchhaltungspflege.md 2.4/10 im Browser nach (Vergleich ohne Groß-/Kleinschreibung und Leerraum); maßgeblich
  bleibt der Server. Mobil zeigt die Kategorieansicht Kategorie und Konto nebeneinander in der zweiten Zeile.
- **Begründung:** oberflaeche.md 7.1, 22.1–22.4, E-163 bis E-165.

## D-105 Versionierung, Release-CI und About-Fenster (Feature `versionierung`)

- **Auftrag (2026-11-10, iterativ abgestimmt):** Versionsschema `MAJOR.MINOR` mit zweistelligem Minor (`0.07`,
  `1.00`); bei jedem Release auf main Minor + 1, Major nur auf Anweisung; Release-CI in GitHub; Klick auf die
  Versionsnummer öffnet ein About-Fenster.
- **Entscheidung:**
  - Einzige Quelle ist die Paketdatei `src/kontor/VERSION` (Startwert `0.00` = noch kein Release). Daraus lesen
    `kontor.__version__`, `pyproject.toml` (`dynamic`), `/api/status`, die Hülle (`{{VERSION}}`) und die Sicherung
    (`app_version`). `0.07` ist PEP 440-gültig (python-api.md 1); Paketwerkzeuge normalisieren es zu `0.7`, daher
    heißen Wheel und Quellpaket z. B. `kontor-0.7-…` – die Anzeige bleibt `0.07`.
  - Nach `0.99` folgt `0.100` (Minor zählt ohne Grenze weiter); Major steigt nie von selbst.
  - Release = jeder Push auf main (`.github/workflows/release.yml`), d. h. jeder Merge eines Feature-Branches.
    Major über „Run workflow“ mit `major` angekreuzt. Die CI führt die eigenen Tests aus, erhöht die Version
    (`python -m kontor.release`), committet sie als „Kontor Release-CI“ mit `[skip ci]`, setzt den Tag
    `vMAJOR.MINOR`, schreibt `build.json` (Commit, Build-Datum, nicht im Repository), baut Wheel und Quellpaket,
    prüft das installierte Wheel, pusht atomar und legt ein GitHub-Release mit automatischen Notizen an.
  - Die Abnahmetests aus kontor-tests laufen nicht in der CI: Dafür bräuchte die CI einen Zugang zu kontor-tests
    (Secret), und Secrets legen Threads nicht an. Abnahme bleibt Schritt 6 des Feature-Ablaufs.
  - Neuer Endpunkt `GET /api/version` (geschützt wie alle Endpunkte außer sicherheit.md 3.1): `name`, `version`,
    `commit` (12 Zeichen oder null), `build_datum` (oder null), `entwicklungsstand` (true ohne `build.json`),
    `python`, `repository`, `modus`, `datenbank` (Pfad der aktiven Datenbank), `datenbank_schema`,
    `sicherung_schema`. Kein fachlicher Zustand, nichts im Protokoll oder in der Sicherung.
  - Oberfläche: Knopf `version-knopf` („Version 0.07“) unten in der Navigation, serverseitig in die Hülle
    eingesetzt; Klick öffnet den Dialog `ueber-dialog` (Felder `ueber-version`, `ueber-build`, `ueber-modus`,
    `ueber-python`, `ueber-datenbank`, `ueber-schema`, `ueber-repository`, Knopf `ueber-schliessen`, Esc schließt,
    Fokus zurück auf den Knopf). Mobil schließt der Klick zuerst das Menü.
- **Begründung:** Eine Datei als Quelle verhindert abweichende Angaben; die CI ist der einzige Ort, der hochzählt,
  damit Feature-Branches keine Versionskonflikte erzeugen.

## D-106 Bearbeiten und Massenänderungen (M12, Feature `buchungsbearbeitung`)

- **Frage:** Offene Einzelheiten der Umsetzung von `datenmodell.md` 17 und `oberflaeche.md` 23.
- **Entscheidung:**
  - `buch.mehrfach_aendern` prüft in der Reihenfolge der Spezifikation (unbekannte Buchungen, unbekannter
    Empfänger, `buchung_gesperrt`, `bestaetigung_erforderlich`) und schreibt dann stückweise (je 500 IDs) ein
    `UPDATE` für alle genannten Buchungen. Buchungen ohne tatsächliche Änderung erscheinen nicht im Protokoll, weil
    das Protokoll die Nettowirkung erfasst; ändert sich nichts, entsteht keine Änderung. Der Vorschlag wird nur bei
    Buchungen entfernt, deren Status sich tatsächlich auf `bestaetigt`/`abgeglichen` ändert.
  - „Mindestens ein Feld“ wird nach der Schemaprüfung im Endpunkt geprüft (422 `validierung`, Ort `body`).
  - Oberfläche: Die Empfänger-Auswahl nutzt die Reihenfolge der Antwort von `GET /api/empfaenger`
    (`stamm.empfaengerFolge`), nicht die nach Namen sortierte Liste. Ein ungültiger Betrag bleibt bei Enter im
    Editor (`aria-invalid`); beim Verlassen des Feldes wird er verworfen, ohne Anfrage.
  - Inline-Status und `km-status`/`mehrfach-status` laufen über dieselbe Funktion mit der Rückfrage
    `bestaetigen-dialog`; der Bearbeiten-Dialog zeigt dafür `mehrfach-entsperren`.
  - Fokus einer Zeile führt die Liste nur noch senkrecht nach: Bei schmaler Liste (beide Panels offen) ist die
    Zeile breiter als die Liste; bisher sprang die waagerechte Scrolllage beim Fokussieren an den Zeilenanfang,
    sodass der zweite Klick eines Doppelklicks auf Status oder Betrag neben der Zelle landete.
- **Begründung:** Nah an `PATCH` und den übrigen Mehrfach-Endpunkten; eine Funktion je Oberflächenablauf hält
  Rückfrage und Fehlermeldung einheitlich.

## D-107 Aktualisierung über GitHub-Releases (Feature `update`)

- **Frage:** Wie sucht Kontor nach neuen Releases, zeigt sie an und aktualisiert sich aus dem About-Dialog, ohne
  die Härtung des Dienstes (`ProtectSystem=strict`, Benutzer `kontor`) aufzugeben?
- **Entscheidung (mit dem Auftraggeber abgestimmt 2026-11-10):**
  - Prüfen beim Start (nach 30 s) und alle `update_intervall_stunden` (Vorgabe 24) über
    `GET https://api.github.com/repos/tedeler/kontor-app/releases/latest` (öffentlich, ohne Token), zusätzlich
    „Jetzt prüfen“ im About-Dialog. Abschaltbar; in `KontorConfig` Vorgabe aus (`update_pruefen = False`, damit
    Tests und Entwicklungsstände nie ungefragt ins Netz gehen), in der ausgelieferten `kontor.env` an. Im
    Mock-Modus nie (409 `update_mock`). Ergebnis nur im Arbeitsspeicher (Betriebszustand, nicht in Datenbank,
    Protokoll oder Sicherung); Fehlertexte der Gegenstelle werden nie weitergegeben.
  - Anzeige: nur ein Punkt am Versionsknopf (mobil zusätzlich am Menüknopf), Text des Knopfs unverändert.
  - Installation über einen eigenen Update-Dienst: Kontor legt nur `auftrag.json` (gewünschte Version) in
    `update_verzeichnis` ab; `kontor-update.path` startet `kontor-update.service` (root). Das Programm
    `python -m kontor.aktualisierung ausfuehren` vertraut dem Auftrag nur die Versionsnummer an, fragt die API
    selbst, verlangt genau ein Wheel mit SHA-256-Digest, prüft die Prüfsumme, legt über
    `kontor-sicherung.service` eine Sicherung an (schlägt sie fehl, wird nicht installiert), installiert mit pip
    ins venv, schreibt `ergebnis.json` und startet `kontor.service` neu.
  - REST: `GET /api/update`, `POST /api/update/pruefen`, `POST /api/update/installieren` (202; 409
    `update_nicht_eingerichtet`, `update_nicht_verfuegbar`, `update_laeuft`, `update_mock`).
  - Konfiguration: `KONTOR_UPDATE_PRUEFEN`, `KONTOR_UPDATE_URL` (HTTPS, für Attrappen auch `http://127.0.0.1…`),
    `KONTOR_UPDATE_INTERVALL_STUNDEN` (1–720), `KONTOR_UPDATE_VERZEICHNIS`.
- **Begründung:** Die Rechtetrennung hält einen kompromittierten Webprozess davon ab, beliebigen Code als root zu
  installieren: Er kann nur das neueste offizielle Release mit passender Prüfsumme anstoßen. Die Sicherung vorher
  macht ein misslungenes Update rückholbar.

## D-108 Rückgängig bis zu einer Änderung (Feature `sammelpaket`)

- **Frage:** Wie nimmt „bis hierher rückgängig“ alle Änderungen seit einer gewählten Änderung in einem Schritt
  zurück, auch wenn dazwischen schon rückgängig gemacht oder wiederholt wurde?
- **Entscheidung:** `POST /api/aenderungen/rueckgaengig` kennt als drittes, ausschließendes Feld `bis_id`
  (einschließlich, mit dem Auftraggeber abgestimmt). Die Menge entsteht durch Simulation der Wirksamkeit
  (`protokoll.md` 6.5) von der neuesten Änderung abwärts: Jede Änderung `k >= bis_id`, die im Zwischenstand wirksam
  ist, wird gewählt; wird eine Rückgängig-Änderung gewählt, wirken ihre Ziele wieder (ältere bleiben so
  wiederhergestellt, neuere werden danach ebenfalls gewählt). Ausgeführt wird wie 6.2 (absteigend, Zustands- und
  Bezugsprüfung, eine neue Änderung). Sich aufhebende Paare stehen in `rueckgaengig_von`, ändern die Einträge aber
  nicht. Damit die Wirksamkeit stimmt, setzt `protokolliert` `rueckgaengig_durch` absteigend und gibt Ziele
  aufsteigend frei (eine freigegebene Rückgängig-Änderung bindet ihre eigenen Ziele wieder). Unbekannte `bis_id` →
  404, nichts mehr wirksam → 409 `bereits_rueckgaengig`.
- **Begründung:** Ergebnis ist immer exakt der Buchbestand unmittelbar vor der gewählten Änderung, und die neue
  Änderung lässt sich wie jede andere wiederholen.

## D-109 Mehrere Buchungen löschen (Feature `sammelpaket`)

- **Frage:** Gleichartige Änderungen sollen einen Änderungssatz ergeben; die Oberfläche löschte bisher je Buchung.
- **Entscheidung:** `POST /api/buchungen/mehrfach/loeschen` `{buchung_ids}` (≥ 1, ohne Doppelte), atomar, Aktion
  `mehrfach_loeschen` (`quelle = "manuell"`). Prüfreihenfolge: 422 `referenz_unbekannt` (`details.buchung_ids`),
  409 `buchung_gesperrt` (alle gesperrten). Antwort `{geloescht, anzahl}`. Die Oberfläche nutzt bei einer Buchung
  weiter `DELETE`, sonst den neuen Endpunkt. Alle übrigen Mehrfachaktionen der Oberfläche waren schon eine Anfrage.

## D-110 Buchungen auf ein anderes Konto verschieben (Feature `sammelpaket`)

- **Frage:** Wie werden Buchungen massenweise auf ein anderes Konto übertragen, auch ein ganzer Import?
- **Entscheidung:** `POST /api/buchungen/mehrfach/verschieben` `{von_konto_id, nach_konto_id, buchung_ids | gruppe}`
  hängt je Buchung den Split auf dem Quellkonto auf das Zielkonto um (Betrag, Memo, Gegensplits, Status, Tags,
  Herkunft bleiben). Beide Konten müssen Bestandskonten sein (422 `konto_ungueltig`, unbekannt 422
  `referenz_unbekannt`, gleich 422 `validierung`). `gruppe` = Herkunft (`import:<id>`, `sync:<id>`): alle noch
  vorhandenen Buchungen, die eine Änderung dieser Gruppe angelegt hat und die auf dem Quellkonto liegen.
  Buchungen ohne Split auf dem Quellkonto oder schon mit Split auf dem Zielkonto → 422 `verschieben_unmoeglich`
  (aus einer Umbuchung würde sonst eine Buchung auf sich selbst); gesperrte → 409 `buchung_gesperrt`. Aktion
  `mehrfach_verschieben`. `GET /api/konten/{id}/herkunft` listet die Herkunftsgruppen mit Buchungen auf dem Konto
  (`{gruppe, art, beschreibung, zeitpunkt, anzahl}`, neueste zuerst) für den Dialog.

## D-111 Synchronisationskonto und Zuordnung unbekannter Bankkonten (Feature `sammelpaket`)

- **Frage:** Die Synchronisation soll grundsätzlich ein vom Anwender bestimmtes Konto verlangen.
- **Entscheidung:** Das Synchronisationskonto eines Kontos ist seine IBAN (genau eins je Konto, abgestimmt). Neue
  Konfiguration `sync_konten_anlegen` / `KONTOR_SYNC_KONTEN_ANLEGEN` (Vorgabe wahr wie bisher, damit Verhalten und
  Abnahmetests von M2–M13 gleich bleiben; die ausgelieferte `kontor.env` setzt 0). Ist sie aus, legt der Lauf für
  ein Bankkonto ohne Konto und ohne gespeicherten Zustand kein Konto an, sondern überspringt es mit
  `uebersprungen[] = {iban, name, status: "nicht_zugeordnet", art}` und einer Benachrichtigung
  `konto_nicht_zugeordnet` (Link `/sync`). Bekannte, aber gelöschte Bankkonten bleiben bei `synchronisation.md` 16.
  Die Oberfläche bietet nach dem Lauf je Bankkonto `zuordnung-dialog` an (vorhandenes Bestandskonto ohne IBAN oder
  neues Konto) und trägt die IBAN über `PATCH`/`POST /api/konten` ein; danach startet sie den Abruf erneut. Trägt
  ein Konto die IBAN, wird die Benachrichtigung als gelesen markiert. Neuer Dialog `konto-einstellungen` (Name,
  Synchronisationskonto, eröffnet am, geschlossen, Notiz) aus dem Kontomenü und der Kontoansicht.

## D-112 Gesperrter PIN-Dialog, Vorschläge je Zeile (Feature `sammelpaket`)

- **Entscheidung PIN:** Nach „PIN senden“ ist der Dialog gesperrt (`data-gesperrt="ja"`, alle Eingaben und Knöpfe
  inaktiv, Esc wirkungslos). `pin-dialog-status` zeigt die Phase (`data-phase`: `pin`, `verbinden`, `abruf` mit
  „Rufe Umsätze ab … (n von m: Konto)“ aus `GET /api/sync/status`, `tan`, `fertig`, `fehler`). PIN falsch entsperrt
  und meldet in `dialog-fehler`. Ein PIN-loser Lauf bleibt ohne Dialog.
- **Entscheidung Vorschläge:** Die Kategoriezelle zeigt die vorgeschlagene Kategorie (kursiv) und in
  `vorschlag-marke` die Sicherheit („87 %“) bzw. „Regel“/„Empf.“ mit Quelle und Regelname im Titel
  (`data-quelle`, `data-sicherheit`); ✓/✗ liegen darüber und erscheinen bei Zeiger, Fokus oder Auswahl (mobil immer).
  Die Einzelheiten zeigen `details-vorschlag` mit Quelle, vorherigem Konto, Annehmen/Ablehnen und den Kandidaten
  des Lernmodells ab 1 % (`POST /api/lernmodell/vorhersage`, ohne Wirkung) zum Übernehmen.

## D-113 Berichtsgrafiken mit Plotly (Feature `sammelpaket`)

- **Entscheidung:** plotly.js Basis-Paket 4.2.0 (MIT, `plotly.js-basic-dist-min`) liegt unverändert unter
  `web/oeffentlich/vendor/` (mit Lizenz) und wird erst auf der Berichtsseite per `<script>` geladen (CSP
  `script-src 'self'` genügt, das Paket nutzt kein `eval`/`new Function`), im Service Worker zwischengespeichert.
  Kontostandsverlauf als Stufenlinie je Konto plus Summe, Einnahmen/Ausgaben als Balken mit Saldolinie
  (`bericht-ea-diagramm`). Beträge bleiben ganze Cent: Plotly erhält Cent-Werte, Achsenstriche
  (1/2/5·10^k Cent) und Beschriftungen entstehen mit Ganzzahlarithmetik (`betragText`). Ohne ladbares Plotly
  (offline) zeichnet die Seite das bisherige SVG. Der eigene Test „keine externen Ressourcen“ nimmt `vendor/` aus:
  Plotly enthält nur Vorgabe-URLs für nicht genutzte Funktionen (Chart Studio, Geo); die Optionen schalten sie ab,
  die CSP (`connect-src 'self'`) verhindert jeden Abruf.

## D-114 Abnahme M15: Rückgängig bis ohne Nettowirkung, frische Kontenliste im Zuordnungsdialog

- **Anlass:** Abnahmetests M15 (kontor-tests `8110ece`, E-190).
- **Entscheidung:** Ergibt ein Rückgängig bis keine Nettowirkung (z. B. zweimal bis zur selben Änderung), wird die
  Transaktion mit 409 `bereits_rueckgaengig` verworfen; es entsteht keine Änderung. Der Zuordnungsdialog liest die
  Konten bei jedem Öffnen frisch vom Server, damit in einer Reihe das eben zugeordnete Konto nicht mehr angeboten wird.

## D-115 Zusätzliche Zahlungen brechen die Kette nicht (Feature `wiederkehrend-begruendung`)

- **Frage:** Nach dem Import langer Altdaten (KMyMoney) verschwanden viele Serien, weil eine zweite Buchung am
  selben Termin (Dublette mit abweichendem Datum, Einmalzahlung) die Kette nach wiederkehrend.md 2.2 sofort beendet.
- **Entscheidung (mit dem Auftraggeber abgestimmt, ersetzt wiederkehrend.md 2.2):** Die Kette beginnt weiter beim
  jüngsten Eintrag und läuft rückwärts. Vorgänger-Kandidaten eines Glieds `c` sind alle älteren Einträge `x` mit
  `|c.datum − monat_plus(x.datum, m)| ≤ T`. Davon zählt der Kandidat mit gleichem Betrag wie `c`, dann mit der
  kleinsten Abweichung, dann der jüngere. Einträge zwischen Vorgänger und `c` sind **zusätzliche Zahlungen**, wenn
  sie höchstens `T` Tage von `c` oder vom Vorgänger entfernt sind oder selbst Kandidaten des vorigen Schritts
  waren; jeder andere Eintrag dazwischen beendet die Kette („fremde Zahlung“). Gibt es keinen Kandidaten, endet
  die Kette; Einträge höchstens `T` Tage vor dem ersten Glied gelten ebenfalls als zusätzlich. Zusätzliche Zahlungen
  zählen nicht zur Mindestanzahl und stehen nicht in `buchung_ids`. Mindestanzahl, Rhythmen, Status, Betrag und
  Ereignisse bleiben unverändert. Eine ausgelassene Zahlung beendet die Kette weiterhin.
- **Begründung:** Dubletten und Einmalzahlungen am Termin sind im Alltag häufig; wöchentliche oder unregelmäßige
  Zahlungen (Einkäufe) dürfen dadurch nicht zu Monatsserien werden, deshalb nur Einträge nahe an einem Termin.
- **Folge:** Der M5-Test `test_doppelte_zahlung_unterbricht_die_kette` widerspricht dem neuen Verhalten; die
  Anpassung von Spezifikation und Tests übernimmt ein Test-Thread über die Meilenstein-Definition.

## D-116 Begründung je Buchung (Feature `wiederkehrend-begruendung`)

- **Entscheidung:** `GET /api/buchungen/{id}/wiederkehrend?stichtag=` (Vorgabe heute; 404 unbekannt, 422 Datum)
  liefert ohne Zustand, warum eine Buchung (nicht) wiederkehrend ist: `urteil` (`wiederkehrend`,
  `nicht_wiederkehrend`, `ausgeschlossen`), `text`, ausgeschlossene Konten (Darlehenskonto, Summe 0) und je
  betrachtetem Konto einen Eintrag mit `urteil` (`glied`, `zusaetzlich`, `vor_beginn`, `keine_serie`), `glied`,
  der Serie und dem Kettenprotokoll je geprüftem Rhythmus (bis zum ersten erfüllten): Schritte mit `ergebnis`
  (`verbunden`/`bruch`), `grund` (`kein_vorgaenger`, `abstand`, `fremde_zahlung`), Vorgänger, erwartetes Datum,
  Abweichung, übersprungene Buchungen und einem deutschen Satz. Die Texte erzeugt der Server.
- **Begründung:** Nachvollziehbarkeit war die wichtigste Anforderung; die Berechnung ist dieselbe wie in der
  Übersicht, daher stimmen Begründung und Übersicht immer überein.

## D-117 Anker am jüngsten Termin und eindeutiges Urteil (ergänzt D-115, D-116)

- **Frage:** Der Anker der Kette war einfach die jüngste Buchung nach Datum und ID. Lagen am jüngsten Termin zwei
  Buchungen (z. B. Rate und Einmalzahlung am selben Tag), entschied die Reihenfolge des Anlegens, welche zur Serie
  gehört. Die Begründung nannte dabei eine Regel, die für den Anker gar nicht galt. Das Urteil
  „Nicht wiederkehrend“ für eine zusätzliche Zahlung neben einer bestehenden Serie wirkte widersprüchlich.
- **Entscheidung:** Anker-Kandidaten sind alle Einträge höchstens `T` Tage vor dem jüngsten Eintrag. Gewählt wird
  der Kandidat mit der längsten Kette, dann der mit gleichem Betrag wie sein Vorgänger in der Kette, dann der
  jüngere. Spätere Kandidaten sind zusätzliche Zahlungen. Bei mehreren Kandidaten beginnt das Kettenprotokoll mit
  einem Schritt `ergebnis = "anker"` (mit `kandidaten`). Die Begründung hat das Gesamturteil `zusaetzlich` (neben
  `wiederkehrend`, `nicht_wiederkehrend`, `ausgeschlossen`), nennt für zusätzliche Zahlungen den konkreten Grund
  der Auswahl und listet je Eintrag alle Buchungen der Gruppe mit Rolle (`glied` mit Nummer, `zusaetzlich`,
  `vor_beginn`, `keine_serie`). Die Oberfläche beantwortet oben „Wiederkehrend? Ja/Nein“ mit einem Zusatz.
- **Begründung:** Rückmeldung des Auftraggebers: Das Urteil muss auf einen Blick eindeutig sein, und die Auswahl am
  Termin darf nicht vom Zufall der Anlagereihenfolge abhängen.

## D-118 Menü je Serie und Sprung ins Kontoblatt (Feature `wiederkehrend-begruendung`)

- **Entscheidung:** Auf `/wiederkehrend` hat jede Zeile `serie-<schluessel>` eine letzte Spalte mit dem Knopf
  `wk-menue-<schluessel>` („…“, `aria-haspopup="menu"`); dasselbe Menü öffnen Rechtsklick, Umschalt+F10/Menütaste
  (Zeile ist fokussierbar) und lange Berührung. Einträge: `km-serie-begruendung` „Warum wiederkehrend?“ öffnet den
  Begründungsdialog (D-116) zur jüngsten Buchung der Serie (letzte ID in `buchung_ids`); `km-serie-springen`
  „Letzte Buchung im Kontoblatt zeigen“ navigiert zu `/konten/<konto_id>?buchung=<id>`. Der Parameter `buchung`
  ist kein Filter: Die Kontoansicht lädt bei Bedarf weitere Seiten nach, markiert die Buchung allein, fokussiert und
  rollt zu ihr, hebt sie kurz hervor und entfernt den Parameter aus der Adresse. Ist sie mit den Filtern nicht
  sichtbar, erscheint ein Hinweis.
- **Begründung:** Wunsch des Auftraggebers. Die Testkennung beginnt bewusst nicht mit `serie-`, weil Zeilen über
  `[data-testid^="serie-"]` gezählt werden (oberflaeche.md 13.5).

## D-119 Tabs der Ansichten und „Gehe zur Gegenbuchung“ (Feature `tabs-gegenbuchung`, iterativ)

- **Anlass:** Auftrag 2026-11-11; abgestimmt mit dem Auftraggeber: alle Seiten als Tabs, Tabs über Neuladen
  hinweg gespeichert, Gegenbuchung auch in Kategorien, bei mehreren Gegenseiten ein Untermenü.
- **Tabs:** Schlüssel eines Tabs ist der Pfad ohne Abfrageteil; dieselbe Ansicht erneut anfordern aktiviert ihren
  Tab, ein neuer Tab entsteht rechts neben dem aktiven. Ein offener Tab behält DOM und Seitenobjekt (Auswahl, Fokus,
  geladene Seiten, Scrollstand von Hauptbereich, Liste und Panels); inaktive Tabs hängen nicht im Dokument, damit
  jede `data-testid` nur einmal vorkommt. Gespeichert werden im `localStorage` unter `kontor.tabs` nur Pfad,
  Abfrageteil (Filter, Sortierung) und Titel (`{"version": 1, "tabs": [...], "aktiv": pfad}`, höchstens 40);
  gespeicherte Tabs laden erst beim Aktivieren.
- **URL gilt:** Ein direkter Aufruf (Adresszeile, Neuladen, Zurück/Vor) zeigt genau den Abfrageteil der URL. Nur
  Navigation innerhalb der Oberfläche ohne Abfrageteil (Navigation, Links, Tab-Klick) übernimmt den des offenen
  Tabs. Ein Link mit anderem Abfrageteil baut den Tab damit neu auf. Dieselbe aktive Ansicht erneut aufrufen baut
  sie wie bisher neu auf.
- **Aktualität:** Eine Änderung am Buchbestand (`aktion()` → Neuladen) markiert alle anderen geladenen Tabs als
  veraltet; sie laden beim nächsten Zeigen mit dem Stand des Servers (`aktualisieren()`, sonst Neuaufbau). Offline
  werden alle Tabs verworfen (keine veralteten Daten, oberflaeche.md 18).
- **Schließen:** `tab-schliessen`, Mittelklick oder Entf auf dem fokussierten Tab. Wird der aktive geschlossen,
  wird der rechte Nachbar aktiv, sonst der linke, sonst die Finanzübersicht. Tastatur in der Leiste: Pfeile, Pos1,
  Ende, Leertaste.
- **Gegenbuchung:** Kontextmenüeintrag `km-gegenbuchung` (nach „Bearbeiten…“, vor „Verschieben…“), aktiv bei genau
  einer gewählten Buchung mit mindestens einem Split auf einem anderen Konto. Gegenseiten sind die Konten der übrigen
  Splits (Bestandskonten und Kategorien), in Split-Reihenfolge ohne Doppelte. Bei genau einer wird direkt
  gesprungen, bei mehreren öffnet an derselben Stelle ein Untermenü mit `km-gegenbuchung-<konto_id>` (Text: Pfad).
  Ziel ist der Tab der Kontoansicht des Gegenkontos; dort wird die Buchung allein ausgewählt und fokussiert. Ist sie
  nicht geladen, werden weitere Seiten geladen; verdecken die Filter des Tabs sie, werden sie (bis auf die
  Sortierung) zurückgesetzt mit Hinweis „Filter zurückgesetzt, damit die Buchung sichtbar ist.“.
- **Filterleiste (mit dem Auftraggeber abgestimmt):** Klick auf den Tab und Zurück/Vor stellen die Ansicht
  vollständig her. Wird ein offener Tab über Navigation oder Link angefordert (auch der aktive, auch beim Sprung
  zur Gegenbuchung), bleiben Filter, Sortierung, Auswahl und Scrollstand, die Filterleiste beginnt aber wieder
  eingeklappt (oberflaeche.md 23.1, E-172 bleibt gültig).

## D-120 Abnahme M16: Feinheiten der Kette und der Begründung

- **Frage:** Der Abnahmelauf M16 (kontor-tests `590f096`) zeigte Abweichungen von der freigegebenen Definition.
- **Entscheidung:** (1) Einträge im aktuellen Termin-Fenster, die nicht als Vorgänger gewählt werden, sind nicht
  pauschal zusätzlich; es gilt allein Definition 1.2 (höchstens `T` Tage von `c` oder vom Vorgänger oder Kandidat des
  vorigen Schritts). D-115 wird insoweit präzisiert. (2) Beim Bruch durch eine fremde Zahlung gelten die übrigen
  Einträge dazwischen nach derselben Regel als zusätzlich und stehen in `uebersprungen` (E-193). (3) `kandidaten`
  ist außerhalb des Schritts `anker` eine leere Liste (E-195). (4) Unbekannte Query-Parameter der Begründung → 422.
- **Hinweis:** Ein anderer Implementierungs-Thread hatte den Branch vor dem Abnahmelauf auf main gemergt
  (Version 0.06); die Korrekturen kommen mit dem erneuten Merge.

## D-121 Inline-Editor übersteht das Neuzeichnen der Buchungsliste

- **Anlass:** In den M8-Tests (`test_neue_aktion_leert_wiederholen`, `test_import_ueber_die_oberflaeche`) und im
  Rauchtest schwankend rot: Wird ein Inline-Editor geöffnet, während die Liste nach einer vorigen Aktion (Ändern,
  Rückgängig) noch neu lädt, ersetzte das Neuzeichnen die Zeilen; der Editor verlor den Fokus und schloss sich
  (beim Verlassen wurde er sogar übernommen). Auch Anwender konnten das bei langsamer Verbindung erleben.
- **Entscheidung:** Zeichnet die Kontoansicht die Liste neu, während ein Editor offen ist, wird er vorher ohne
  Übernahme gelöst und in die gleiche Zelle der neuen Zeile mit Eingabe und Fokus eingesetzt; die Prüfungen beim
  Übernehmen nutzen den neuen Stand der Buchung. Ist die Buchung nach dem Neuladen nicht mehr da, entfällt der
  Editor ohne Änderung.

## D-122 Rückgängig und Wiederholen werden eingereiht

- **Anlass:** `test_strg_z_und_wiederholen` (M8) schwankend rot: Strg+Y direkt nach Strg+Z wurde verworfen, solange
  die Antwort der Rückgängig-Anfrage noch nicht im Browser war (der Server hatte bereits geändert).
- **Entscheidung:** Rückgängig- und Wiederholen-Schritte der Oberfläche laufen strikt nacheinander; ein weiterer
  Tastendruck oder Klick während eines laufenden Schritts wartet auf ihn und wird dann ausgeführt. Jeder Druck ist
  genau ein Schritt. Das Neuladen der Ansicht danach läuft außerhalb dieser Reihe.
- Ein Schritt wartet außerdem auf gerade laufende Aktionen, bis deren Änderungen auf dem Rückgängig-Stapel liegen:
  Strg+Z unmittelbar nach einer Änderung macht genau diese rückgängig, statt „nichts rückgängig zu machen“ zu melden.

## D-129 Schutz der Geheimnisse mit dem Login-Passwort (Feature `geheimnisse`, iterativ)

- **Anlass:** Auftrag 2026-11-13. Abgestimmt: Geheimnisse (Bank-PIN, Mail-Zugänge, Tokens) liegen verschlüsselt in
  der Datenbank, ein starker Datenschlüssel ist mit einem aus dem **Login-Passwort** abgeleiteten Schlüssel
  verpackt; das Masterpasswort ist das Login-Passwort; die Bank-PIN kann darunter gemerkt werden; **kein**
  automatisches Entsperren, **keine** Leerlaufsperre.
- **Aufbau (Schlüsselhülle):** Die bestehende äußere Schicht (Systemschlüssel aus systemd-creds bzw. Schlüsseldatei,
  geheimnisse.md) bleibt unverändert. Ist der Schutz eingeschaltet, trägt jedes Geheimnis außer `ntfy_token`
  (damit Benachrichtigungen wie „Bitte entsperren“ zugestellt werden) eine innere Schicht: AES-256-GCM mit einem
  zufälligen 256-Bit-Datenschlüssel, zusätzliche Daten `innen:<name>`, Kennung `M1:` im äußeren Klartext. Der
  Datenschlüssel liegt verpackt in `geheimnis_huelle` (eine Zeile; AES-256-GCM mit scrypt(Passwort, 16 Byte Salz,
  N=2^15, r=8, p=1), eigenes Salz unabhängig vom Login-Hash). Betriebszustand: nie protokolliert, nie gesichert.
- **Opt-in:** Der Schutz wird ausdrücklich eingeschaltet (`POST /api/geheimnisse/schutz` mit dem Login-Passwort,
  Bremse der Anmeldung); ohne ihn verhält sich alles wie bisher (alle bestehenden Meilensteine unverändert).
  Voraussetzung ist ein gesetztes Login-Passwort (409 `nicht_eingerichtet`), die Anmeldung selbst darf
  abgeschaltet sein.
- **Entsperren:** Jeder erfolgreiche Login entsperrt; sonst `POST /api/geheimnisse/entsperren` (Dialog aus dem
  roten Hinweis `sperr-leiste` oder in den Einstellungen). Das Passwort wird nach dem Ableiten verworfen; nur der
  Datenschlüssel bleibt bis zum Neustart oder `POST /api/geheimnisse/sperren` im Arbeitsspeicher. Gesperrt: geschützte
  Geheimnisse gelten als nicht lesbar, Schreiben → 409 `geheimnisse_gesperrt`, kein Mail-Abruf (Planer überspringt,
  manuell 409), Bankabruf nur mit eingegebener PIN.
- **Passwort:** Ändern (`PUT /api/anmeldung/passwort`) verpackt nur den Datenschlüssel neu. Zurücksetzen ohne altes
  Passwort (`passwort-setzen`) verwirft Hülle und geschützte Geheimnisse (die Kommandozeile nennt die Anzahl).
  `POST /api/geheimnisse/schutz/ausschalten` entfernt die innere Schicht wieder.
- **Gemerkte PIN:** `PUT /api/sync/pin/gemerkt` (nur mit eingeschaltetem, entsperrtem Schutz; Geheimnis `bank_pin`),
  `DELETE /api/sync/pin/gemerkt`; „PIN verwerfen“ löscht sie mit. Sie wird gelesen, wenn keine PIN im Arbeitsspeicher
  liegt; lehnt die Bank sie ab (`BankPinFalsch`/`BankZugangGesperrt`), wird sie sofort gelöscht (Schutz vor
  Kontosperre). Im PIN-Dialog erscheint dafür „PIN merken“.
- **Härtung:** systemd `LimitCORE=0` (zusätzlich zu `ProtectProc=invisible`); `python -m kontor` setzt
  `RLIMIT_CORE=0` und `PR_SET_DUMPABLE=0`. Grenze: Wer Root auf VM oder Hypervisor hat, kann den Arbeitsspeicher
  lesen – dagegen hilft keine Software (Betriebshinweis: Proxmox-Snapshots ohne RAM, kein Swap/Ruhezustand).

## D-130 Gmail ohne Google-Cloud-Projekt: IMAP mit App-Passwort und Ordner (Feature `gmail-app-passwort`)

- **Anlass:** Auftrag 2026-11-13: kein eigenes Google-Cloud-Projekt/keine API in der Konsole. Abgestimmt: Anmeldung
  per **App-Passwort** (Google-Konto mit Bestätigung in zwei Schritten), Kontor liest nur einen **Ordner bzw. ein
  Gmail-Label** (empfohlen „Kontor“, per Gmail-Filter für Amazon/PayPal gesetzt) und nur lesend. OAuth2 bleibt als
  Alternative unverändert (mail.md). Baut auf D-129 auf: Das App-Passwort ist ein geschütztes Geheimnis.
- **REST:** `PUT /api/mail/postfaecher/{id}/app-passwort` (`{passwort}`; Leerzeichen werden entfernt, wie Google es
  in Vierergruppen anzeigt) prüft zuerst `LOGIN` und `EXAMINE` des Ordners gegen den konfigurierten IMAP-Server und
  speichert erst danach (Geheimnis `mail_passwort:<adresse>`; ein OAuth2-Token des Postfachs entfällt). Antwort
  `{postfach_id, ordner, nachrichten_im_ordner}`; Fehler 422 mit dem Code des Mailfehlers
  (`mail_anmeldung_abgelehnt`, `mail_ordner_unbekannt`, `mail_verbindungsfehler` …), 409 im Mock-Modus bzw. bei
  gesperrten Geheimnissen. Das Postfach gilt danach als `angemeldet` ohne Ablauf (`laeuft_ab_am` null).
  `DELETE …/app-passwort` (und das bestehende Abmelden) entfernt es wieder (`fehlt`).
- **Plugin:** die Unterklasse `ImapPasswortPostfach` (Feld `passwort`, Aufrufbares, nie in `repr`/Vergleichen; `ImapPostfach` selbst bleibt nach plugins.md unverändert); damit
  meldet sich `ImapMailPlugin` mit `LOGIN` an (nicht bei `LOGINDISABLED`), sonst wie bisher mit XOAUTH2. Der Wert
  wird erst unmittelbar vor der Anmeldung gelesen und danach verworfen. `ImapMailPlugin._pruefen(adresse)` (nicht öffentlich, die Liste der Plugin-Methoden bleibt gleich) dient nur
  dem Verbindungstest. Antwortschemas bestehender Endpunkte bleiben unverändert (die Anmeldeart ist am Geheimnis
  erkennbar).
- **Oberfläche:** Auf der Postfachseite der Abschnitt „Zugang mit App-Passwort (empfohlen für Gmail)“ mit Anleitung,
  Ordner/Label, App-Passwort und „Speichern und Verbindung testen“; OAuth2 als Alternative darunter.
- **Konzept:** K 13 („ausschließlich OAuth2, keine Passwörter“) wird mit der Meilenstein-Definition angepasst.

## D-123 Dokumente an Buchungen (Feature `dokumente`, iterativ)

- **Anlass:** Auftrag 2026-11-11: PDF-Dateien, E-Mails (und Bilder) an Buchungen hängen und im Browser ansehen;
  mobil per Kamera. Abgestimmt: Hochladen, Ziehen auf eine Buchung und E-Mail aus dem Postfach; PDF, E-Mail, JPEG,
  PNG, WebP; E-Mail mit HTML, aber abgeschottet; ein Dokument an mehreren Buchungen.
- **Datenmodell:** Objektart `dokument` (Dateiname, Typ, Größe, SHA-256, Quelle `upload`/`kamera`/`mail`,
  angelegt). Verknüpfungen gehören zur Buchung (Protokollform `dokument_ids`, nur wenn vorhanden, damit Formen
  ohne Dokumente gleich bleiben); `belege` der Buchung listet `{id, dateiname, mime_typ, groesse}`
  (datenmodell.md 7). Ein Dokument ohne Buchung entfällt in derselben Änderung. Inhalte liegen inhaltsadressiert
  in `dokument_inhalt`, werden nie protokolliert und nie gelöscht (Rückgängig braucht sie).
- **Typ** am Inhalt erkannt, nicht an Dateiname oder Browserangabe; Dateinamen ohne Pfad und Steuerzeichen,
  höchstens 200 Zeichen, mit passender Endung. Größe begrenzt wie andere Uploads (`upload_max_mib`).
- **Auslieferung:** Inhalte mit eigener strenger Inhaltsrichtlinie (`sandbox`) und `X-Frame-Options: SAMEORIGIN`
  nur für diese Antworten; E-Mails nie als Seite, sondern zerlegt (`/mail`) und als entschärftes HTML
  (`/mail/html`: ohne Skripte, Ereignis-Attribute, Formulare, Rahmen; eingebettete `cid:`-Bilder als data:-URL;
  externe Bildquellen und Stil-URLs entfernt, damit Zählpixel nie angefragt werden) im Rahmen mit
  `sandbox="allow-popups allow-popups-to-escape-sandbox"`. Anhänge einer Mail einzeln ansehbar (PDF, Bilder) oder
  zum Herunterladen.
- **Mails aus dem Postfach:** Der Spiegel speichert zusätzlich die Rohfassung (Betriebszustand, Spalte `roh`, nur
  bis `upload_max_mib`); das IMAP-Plugin liefert sie als Zusatzattribut `roh` außerhalb der Datenklassenfelder
  (plugins.md legt die Felder von `MailNachricht` fest). Ohne Rohfassung (Mock) wird die Mail aus den Feldern
  gebaut.
- **Sicherung:** Schemaversion 4 mit `dokument_inhalt` (nur benötigte Inhalte), `dokument`, `dokument_buchung`;
  `dokument` in `anzahl` nur bei Vorhandensein; Prüfung von Hash, Größe und Typ beim Einspielen.
- **Oberfläche:** Abschnitt „Dokumente“ im Detailpanel (Liste, Ansehen, Lösen, „Datei anhängen…“, mobil
  „📷 Foto aufnehmen“ mit `capture="environment"`, „E-Mail…“), Kontextmenü „Dokument anhängen…“, mobil
  „Foto aufnehmen…“, „E-Mail anhängen…“, „Dokumente ansehen“ (für alle gewählten Buchungen), 📎-Marke je Zeile,
  Dateien aus dem Betriebssystem auf eine Zeile ziehen (gewählte Zeile bei Mehrfachauswahl → alle gewählten).
  Betrachter: PDF im Rahmen (mobil zusätzlich „PDF öffnen“), Bilder (Klick vergrößert), E-Mail mit Kopf,
  HTML/Text umschaltbar, Anhänge; Blättern zwischen den Dokumenten einer Buchung. Kamerafotos werden im Browser auf
  höchstens 2400 px Kantenlänge (JPEG) verkleinert.
- **Nachträglich verknüpfen (abgestimmt 2026-11-12):** Der Betrachter zeigt unter jedem Dokument die Buchungen,
  an denen es hängt (Sprung zur Buchung über das erste Bestandskonto ihrer Splits, Lösen je Buchung), und bietet
  „Mit weiteren Buchungen verknüpfen…“ (Suche über `suche` der Buchungsliste, Mehrfachauswahl). PDFs auf dem Handy
  bleiben beim Knopf „PDF öffnen“ (PDF-App des Geräts); jedes Kamerafoto ist ein eigenes Dokument.

## D-128 Mail-Abgleich: erwartete Zahlungen aus Bestell- und Zahlungsmails (Feature `mail-abgleich`, iterativ)

- **Anlass:** Auftrag 2026-11-12. Abgestimmt: Mails sind die einzige Quelle (kein Scraping, keine Amazon-/PayPal-
  Zugangsdaten); „Vorgang statt Kaskade“ (kein PayPal-Konto, keine Zwischenstufen); je Vorgang höchstens eine
  erwartete Bankbewegung mit **Grund** (Bestellung, PayPal, Rückerstattung, manuell; Serien folgen);
  Guthaben bleibt außerhalb der Buchhaltung (Variante A: erwartet wird nur der Bankanteil); Belege gehören zum
  Buchbestand; keine Splits nach Artikeln; ganze Mail und PDF-Anhänge als Dokumente; Frist 5 Tage.
- **Basis:** Branch `feature/dokumente` (D-123) – die Mails werden mit dessen Dokumenten an die Buchung gehängt;
  `dokumente` muss vor diesem Feature gemergt werden.
- **Schalter:** `mail_abgleich` (`KONTOR_MAIL_ABGLEICH`, Vorgabe aus, damit Abläufe und Protokoll bestehender
  Meilensteine unverändert bleiben; ausgelieferte Umgebungsdatei: an) und `mail_abgleich_frist_tage`
  (`KONTOR_MAIL_ABGLEICH_FRIST_TAGE`, Vorgabe 5).
- **Erkennung** (`mailerkennung.py`, reine Funktionen): Anbieter am Absender-Domänennamen (`amazon.…`, `paypal.…`),
  Pflicht sind Kennung (Amazon-Bestellnummer `ddd-ddddddd-ddddddd`, PayPal-Transaktionscode, 17 Zeichen) und
  Betrag. Amazon: Bestellung (Gesamtsumme, Geschenkgutschein/Guthaben, Artikel), Stornierung, Erstattung. PayPal:
  Zahlung (Händler aus dem Betreff, PayPal-Guthaben-Anteil, Bestell-/Rechnungsnummer des Händlers als Referenz),
  Rückzahlung (ursprünglicher Transaktionscode; „gutgeschrieben auf PayPal-Guthaben“ → nichts zu erwarten).
  Unklare Mails werden nicht erkannt und bleiben nur im Spiegel.
- **Datenmodell:** Objektart `erwartung` (Tabelle `erwartung`, protokolliert, rückgängig machbar, in der Sicherung
  ab Schemaversion 5, nur bei Vorhandensein in `anzahl`). Beträge in Cent ≥ 0 mit `richtung`
  (`ausgabe`/`eingang`); `betrag` = Bankanteil, `gesamt`, `guthaben`. Zustände `offen`, `erfuellt`, `guthaben`,
  `storniert`, `erledigt`; „überfällig“ wird abgeleitet (offen, Frist vorbei). `schluessel` (Anbieter:Art:Kennung)
  macht die Erkennung idempotent; dieselbe Mail aus zwei Postfächern ergänzt nur die Mail-Liste. Zuordnungen
  (`buchung_ids`) und angehängte Dokumente (`dokument_ids`) als JSON in der Zeile, ohne Fremdschlüssel;
  `erwartung.verwaiste_entfernen` am Ende jeder protokollierten Operation (gelöschte Buchung → wieder offen).
  Mails selbst bleiben Betriebszustand; die Erwartung merkt sich Postfach, Nachrichten-ID und Betreff.
- **Ablauf** (`abgleich.laufen`, eine Änderung mit Quelle `mail`, Aktion `erwartung_erkennen`, nur wenn sich etwas
  ändert): nach jedem Mail-Abruf, nach jedem Synchronisationslauf und in jedem Planer-Takt sowie per
  `POST /api/erwartungen/abgleich`. Danach je überfälliger Erwartung höchstens eine Benachrichtigung
  (`erwartung_ueberfaellig`, Entprellung „einmal“).
- **Zuordnung:** Kandidaten sind Buchungen mit genau einem Split auf einem Bestandskonto, passender Richtung,
  Betrag ≤ offener Betrag, Datum von 3 Tagen vor bis 45 Tage nach dem Datum der Erwartung, noch keiner Erwartung
  zugeordnet, und entweder mit Kennung/Referenz im Verwendungszweck oder Empfänger (ohne Leerzeichen, ab 6 Zeichen)
  oder genau dem offenen Betrag. **Automatisch** nur bei Kennung oder wenn die Buchung der einzige Kandidat mit
  vollem Betrag ist, den Anbieter-/Händlernamen enthält und für keine andere offene Erwartung infrage kommt; sonst
  bestätigt der Anwender. Teillieferungen: mehrere Buchungen, erfüllt bei vollem Betrag. Beim Zuordnen hängen die
  Mails (je Nachrichten-ID einmal) und ihre PDF-Anhänge als Dokumente (Quelle `mail`) an der Buchung; weitere
  Buchungen derselben Erwartung werden mit denselben Dokumenten verknüpft. Lösen entfernt auch diese Verknüpfung.
- **REST:** `GET/POST /api/erwartungen` (Filter `grund`, `zustand` inkl. `ueberfaellig`, `faellig_bis`, `suche`,
  `richtung`; Vorgabe `zustand=offen`), `POST /api/erwartungen/abgleich`, `GET/PATCH/DELETE
  /api/erwartungen/{id}` (Löschen nur manuelle; aus Mails erkannte werden geschlossen, sonst kämen sie wieder),
  `POST /api/erwartungen/{id}/zustand`, `GET …/kandidaten`, `POST …/buchungen`, `DELETE …/buchungen/{bid}`.
- **Oberfläche:** Seite `/erwartet` „Was kommt noch?“ (Link in der Navigation mit `data-testid="navlink-erwartet"`,
  damit die festgelegte Liste `nav-…` aus M8 unverändert bleibt; Befehlspalette „Gehe zu: Was kommt noch?“).
  Schnellfilter als Chips (Grund, Zustand mit Vorgabe „Offen“, Fällig bis, Suche) im Abfrageteil der Adresse (je
  Tab), eine Zeile je Vorgang, Details mit Mails, Zuordnungen, Belegen und Kandidaten; mobil als Karten.

## D-131 Mail-Abgleich, Fortsetzung: Serien, Kachel, Mock-Daten, Kategorie bei Erstattungen (ergänzt D-128)

- **Serien als Grund:** `GET /api/erwartungen` liefert bei offenen bzw. überfälligen Einträgen zusätzlich die nächste
  Zahlung jeder aktiven oder ausbleibenden wiederkehrenden Serie (wiederkehrend.md 2) als Eintrag mit
  `grund = "serie"`, `id = "serie:<schluessel>"`, Datum = nächste Fälligkeit, Frist = Datum +
  `mail_abgleich_frist_tage`, `konto_id`. Abgeleitet, nicht gespeichert; keine eigene Benachrichtigung (die
  Meldung „ausbleibend“ der Serien bleibt maßgeblich). Ausgelassen werden Serien, deren letzte Buchung schon
  einer erwarteten Zahlung aus einer Mail zugeordnet ist (regelmäßige Einkäufe, sonst doppelt). Filter `grund=serie`. In der Oberfläche führt die Zeile zu
  den wiederkehrenden Buchungen.
- **Kachel:** Die Finanzübersicht zeigt mit eingeschaltetem Mail-Abgleich unten die Kachel `kachel-erwartet`
  („Was kommt noch?“: offen, überfällig, Summe) für Bestellungen, PayPal, Rückerstattungen und manuelle Einträge
  (ohne Serien, damit Gehalt und Miete die Zahl nicht dominieren). Damit ist die Seite auch auf dem Handy erreichbar.
- **Mock-Daten:** Der eingebaute Datensatz enthält je Monat eine Amazon-Bestellung (Postfach eins), jedes dritte
  Monat eine Amazon-Erstattung, eine PayPal-Zahlung (Postfach zwei) und die passenden Umsätze im Girokonto
  (Bestellnummer bzw. Händlername im Verwendungszweck). Absender unter `example.invalid`.
- **Erstattung:** Wird eine Rückerstattung einer Gutschrift zugeordnet, deren Gegenbuchung (genau zwei Splits, kein
  offener Vorschlag) noch auf „Unkategorisiert“ steht, wird sie in derselben Änderung auf die Kategorie der
  ursprünglichen Buchung umgebucht (rückgängig machbar). Ein Vorschlag im Sinne von kategorisierung.md ist das
  nicht, weil dessen Quellen festgelegt sind.

## D-123 ALF-BanCo-Import über den QIF-Export (Feature `alfbanco-import`)

- **Frage:** ALF-BanCo 9 speichert seine Daten verschlüsselt (`HbDat001.dat`), das Format ist nicht dokumentiert.
  Welches Format wird importiert?
- **Entscheidung:** Der QIF-Export (Profi-Edition, „Datei > Export > Umsätze > QIF-Format“), eine Datei je Konto
  (Auftrag des Anwenders 2026-11-12). Neuer Endpunkt `POST /api/import/alfbanco` (multipart: `datei`, `konto_id`)
  und `kontor.importer.alfbanco.importiere_alfbanco(config, quelle, *, konto_id, dateiname=None)`. Das Zielkonto
  muss ein Bestandskonto sein (422 `referenz_unbekannt` bzw. `konto_ungueltig`, Python: `ValueError`); fehlt
  `konto_id` oder ist es keine positive Ganzzahl → 422 `validierung`. Ergebnis wie beim KMyMoney-Import
  (`ImportErgebnis`, `format = "qif"`), Importvorgang `art = "alfbanco"`, Änderung `import_alfbanco` mit Gruppe
  `import:<id>`; kein Teilimport. Fehler: leere Datei → `import_datei_leer`; erste nicht leere Zeile beginnt nicht
  mit `!` → `import_format_ungueltig` (`format = null`); Buchungen mehrerer `!Account`-Konten in einer Datei →
  `import_format_ungueltig`; fehlendes/ungültiges Datum oder fehlender/ungültiger Betrag eines Satzes oder einer
  Aufteilung → `import_inhalt_ungueltig` mit `referenz = "Satz <n>"` (n = laufende Nummer der Buchungssätze).
- **Lesen:** Kodierung UTF-8 (mit/ohne BOM), sonst Windows-1252, sonst Latin-1. Abschnitte `!Type:Bank`, `CCard`,
  `Cash`, `Oth A`, `Oth L` sind Buchungen; `!Type:Invst` wird gezählt und übersprungen (`buchung_uebersprungen`);
  `!Type:Cat` liefert die Art der Kategorien (`I` Einnahme, `E` Ausgabe); alles andere wird ignoriert. Felder:
  `D` Datum, `T` (sonst `U`) Betrag, `P` Empfänger, `M` Verwendungszweck, `L` Kategorie, `S`/`E`/`$` Aufteilung.
  Datum: `T.M.JJJJ`/`T.M.JJ`, `JJJJ-MM-TT`, `M/T/JJJJ`, `M/T'JJ` (Apostroph = 20JJ); bei `/` Tag zuerst, wenn ein
  Datum der Datei an erster Stelle > 12 hat; zweistellige Jahre < 70 → 20JJ, sonst 19JJ. Betrag: Dezimalkomma, wenn
  ein Betrag der Datei mit Komma und ein bis zwei Ziffern endet, sonst Dezimalpunkt; der andere Trenner gilt als
  Tausendertrenner; mehr als zwei Nachkommastellen nur, wenn sie 0 sind.

## D-124 Kennung und Dubletten beim ALF-BanCo-Import

- **Frage:** QIF hat keine Transaktions-IDs. Wie bleibt der Import idempotent, ohne zwei gleiche Kaffees zu
  verschmelzen?
- **Entscheidung:** Herkunftskennung `alf:<konto_id>:<32 Hex>` aus SHA-256 über Datum, Betrag, `P`, `M`, `L`, `N`,
  die Aufteilungen und die laufende Nummer gleicher Sätze in der Datei. Ein zweiter Import derselben Datei ordnet
  alles über die Kennung zu; eine erweiterte Fassung fügt genau die neuen Sätze hinzu. Dublettenprüfung wie
  `datenmodell.md` 10.4, aber nur über das Zielkonto und gegen alle vorher vorhandenen Buchungen auch derselben
  Quelle (ein nachträglich in ALF-BanCo geänderter Satz bekommt eine neue Kennung und soll trotzdem erkannt werden),
  ausgenommen Buchungen, die im selben Lauf schon über ihre Kennung zugeordnet wurden.

## D-125 Kategorien, Klassen und Umbuchungen beim ALF-BanCo-Import

- **Kategorien:** `L` bzw. `S` mit `:` ergibt die Hierarchie; je Pfad eine Kategorie mit
  `extern_id = "alf:kat:<Pfad>"`. Zuordnung: gleiche Kennung; sonst vorhandene Kategorie gleicher Art mit exakt
  gleichem Namen und gleichem (zugeordnetem) Elternkonto, deren Kennung nicht mit `alf:` oder `kontor:` beginnt
  (sie erhält die Kennung nur, wenn sie noch keine hat; Kategorien aus KMyMoney/GnuCash werden so jedes Mal über
  den Namen wiedererkannt); sonst neu. Gezählt wird jeder Pfad der Datei genau einmal, auch bei schon vorhandenen
  Buchungen.
- **Art:** je Wurzel aus `!Type:Cat` (Wurzel, sonst erste gekennzeichnete Unterkategorie), sonst aus der Summe der
  Gegenbeträge (≥ 0 Ausgabe, < 0 Einnahme) mit Warnung `kategorieart_abgeleitet` beim Neuanlegen. Unterkategorien
  erben die Art ihres Elternkontos.
- **Leere Kategorie** → „Unkategorisiert“. **Klasse** (`Kategorie/Klasse`) → Tag (Vergleich mit `casefold`).
  **Umbuchung** `[Name]` → Bestandskonto mit genau diesem Namen (kleinste ID, nicht das Zielkonto); unbekannt →
  „Unkategorisiert“ mit Warnung `umbuchung_konto_unbekannt`; `[eigener Kontoname]` (Anfangssaldo) → technisches
  Eigenkapitalkonto „Anfangssalden“ (`extern_id = "alf:anfangssalden"`). Ergeben die Aufteilungen nicht den
  Gesamtbetrag, geht der Rest auf „Unkategorisiert“ (Warnung `split_differenz`).

## D-126 Kategorien zusammenführen

- **Anlass:** Nach dem Import sollen ALF-BanCo-Kategorien in schon vorhandene gleichwertige Kategorien überführt
  werden können: mehrere markieren, Ziel wählen.
- **Entscheidung:** `POST /api/kategorien/zusammenfuehren` mit `{quelle_ids (1–1000, eindeutig), ziel_id,
  quellen_loeschen (Vorgabe true), gesperrte_einbeziehen (false), trocken (false)}`. Prüfreihenfolge: Körper → 422
  `validierung`; Ziel unter den Quellen → 422 `ziel_ungueltig`; unbekannte IDs → 422 `referenz_unbekannt`
  (`details.konto_ids`); Quelle oder Ziel keine Kategorie → 422 `konto_ungueltig`; zu löschende Quelle mit
  Kreditbezug → wie beim Löschen; gesperrte Buchungen ohne Bestätigung (nicht im Probelauf) → 409
  `buchung_gesperrt`. Wirkung je Quelle in der angegebenen Reihenfolge wie `loeschen.md` mit Variante
  `elternkonto`, aber mit dem gewählten Ziel: Splits umbuchen und auf dem Ziel zusammenfassen, Konfliktbuchungen
  behalten, Regeln, Split-Vorlagen und Standardkategorien auf das Ziel umstellen, Abstimmungen der Quelle
  entfernen, Quelle löschen. Unterkategorien einer Quelle wandern unter das Ziel, wenn es dieselbe Klasse hat und
  dabei kein Zyklus entsteht, sonst eine Ebene nach oben. Ohne `quellen_loeschen` werden nur die Buchungen
  umgebucht (samt Zusammenfassen und Entfernen der Abstimmungen der Quelle). Hat das Ziel keine `extern_id`, erhält
  es die der ersten gelöschten Quelle, damit ein späterer Import die gelöschte Kategorie nicht neu anlegt.
  Einnahme- und Ausgabekategorien dürfen gemischt werden (die abgeleitete Art kann falsch sein). Eine Änderung
  `kategorien_zusammenfuehren` (`quelle = "manuell"`), rückgängig machbar. Antwort: `ziel_id`, `quelle_ids`,
  `quellen_geloescht`, `buchungen_umgebucht`, `konfliktbuchungen`, `gesperrt`, `unterkategorien_verschoben`,
  `regeln_geaendert`, `empfaenger_geaendert`, `extern_id_uebernommen`, `trocken`, `aenderung_id`.
- **Oberfläche:** Kategorienbaum mit Mehrfachauswahl (Strg/⌘-Klick, Umschalt-Klick, Leertaste, Esc hebt auf;
  `aria-selected`), Kontextmenüeintrag `km-kategorie-zusammenfuehren` („Zusammenführen in…“, bei Auswahl „n
  Kategorien zusammenführen in…“), Dialog `zusammenfuehren-dialog` mit Suche, Zielliste, Schalter
  „Quellkategorien danach löschen“, Vorschau über den Probelauf und Bestätigung gesperrter Buchungen.
  Import-Seite: Format „ALF-BanCo“ mit Kontoauswahl `import-konto`.

## D-127 `_loeschen_ausfuehren` mit frei wählbarem Ziel

- Für D-126 ist das Umbuchen aus `_loeschen_ausfuehren` in `_umbuchen` und `_abstimmungen_entfernen` ausgelagert;
  die interne Variante `konto` wirkt wie `elternkonto` mit einem übergebenen Ziel. Das Verhalten von
  `POST /api/konten/{id}/loeschen` ist unverändert (Abnahmetests M3/M4/M5 grün).

## D-128 Berichtsdiagramme: Tooltip im Thema, Tabellen folgen dem Zoom, Einzelbuchungen (Feature `diagramm-dunkel`, iterativ)

D-123 bis D-127 sind auf den offenen Branches `dokumente` und `alfbanco-import` vergeben; daher D-128.

- **Tooltip:** Die Plotly-Diagramme setzen `hoverlabel` ausdrücklich auf die Farben des Themas (`--hg`, `--rand`,
  `--text`). Ohne Angabe zeichnete Plotly einen hellen Kasten, auf dem die helle Schrift des dunklen Themas nicht
  lesbar war. Der Reihenname steht im Text des Tooltips (`<extra></extra>` leer), weil Plotly das Namensfeld sonst
  hell hinterlegt.
- **Zoom:** Die Tabelle unter einem Diagramm zeigt nur die Zeilen, deren x-Wert (Stichtag bzw. Beginn des Zeitraums)
  im sichtbaren Bereich der x-Achse liegt; ein Hinweis nennt Ausschnitt und Zeilenzahl. Autorange (Doppelklick)
  zeigt wieder alle. Kein neuer Abruf, nur Ausblenden; die Zeilen bleiben im Dokument.
- **Einzelbuchungen:** Jede Tabellenzeile hat einen Aufklappknopf (Text der ersten Zelle unverändert, Symbol über
  CSS). Aufgeklappt folgt eine Zeile mit den Buchungen des Zeitraums: Kontostand Zeile i = nach dem vorigen Stichtag
  bis einschließlich Stichtag i (Zeile 0 = nur der erste Stichtag); Einnahmen/Ausgaben = der Zeitraum der Zeile ohne
  Umbuchungen. Quelle ist `GET /api/buchungen` je gewähltem Konto (ohne Auswahl: alle), höchstens 500 je Konto mit
  Hinweis. Betrag = Summe der Splits auf den gewählten Konten (ohne Auswahl: auf Bestandskonten). Je beteiligtem
  Konto ein Knopf (gewählte Konten zuerst), der `/konten/<id>?buchung=<id>` öffnet (Sprungziel nach M16 3.4).
  Die Detailzeile entsteht erst beim Aufklappen, damit die Zeilenzahl der Tabelle unverändert bleibt.
- Keine neuen Endpunkte, kein fachlicher Zustand.

## D-129 Sprungziel in der Kontoansicht immer mittig (ergänzt D-118, D-128)

- Alle Sprünge zu einer Buchung (Abfrageteil `?buchung=`, „Gehe zur Gegenbuchung“, Knöpfe der Einzelbuchungen in
  den Berichten, „Letzte Buchung im Kontoblatt zeigen“) wählen und fokussieren die Buchung, rollen sie in die
  **Mitte** der Liste und heben sie kurz hervor. Bisher rollte „Gehe zur Gegenbuchung“ nur bis an den Rand; mobil
  lag die Zeile dann unter der fest unten stehenden Mehrfachleiste.
- Die Knöpfe der Einzelbuchungen (D-128) und `km-serie-springen` springen über denselben Weg wie „Gehe zur
  Gegenbuchung“ (offener Tab des Kontos wird verwendet, Filter werden bei Bedarf mit Hinweis zurückgesetzt). Die
  Knöpfe bleiben Links auf `/konten/<id>?buchung=<id>`, damit Strg-/Mittelklick einen neuen Browser-Tab öffnet.

## D-130 Spaltenbreiten und Markierung der Buchungsliste (Feature `spalten-markierung`, iterativ)

- **Anlass:** Auftrag 2026-11-12: Spalten der Kontolisten in der Breite veränderbar, Doppelklick auf den
  Spaltentrenner passt die Spalte an (wie in Excel); Buchungen dezent nach Bearbeitungsstand markieren, dazu eine
  Zusatzmarke für wiederkehrende Buchungen. (Nummer D-130, weil D-123 bis D-129 auf offenen Branches vergeben sind.)
- **Spaltenbreiten:** Trenner am rechten Rand jeder Kopfzelle (`spalte-trenner-<feld>`, Rolle `separator`), nur
  in der Desktop-Liste. Ziehen ändert die Breite (40–1200 px); das erste Ziehen legt alle Spalten auf ihre
  gezeichnete Breite fest, damit die übrigen nicht springen. Doppelklick: Breite des breitesten Inhalts aus Kopf und
  geladenen Zeilen (gemessen an Kopien der Zellen ohne Abschneiden). Ist die Summe breiter als die Liste, wird
  waagerecht geblättert. Kontextmenü des Kopfes: „Alle Spalten an den Inhalt anpassen“
  (`km-spalten-anpassen`), „Spaltenbreiten zurücksetzen“ (`km-spalten-zuruecksetzen`). Gemerkt im Browser
  (`kontor.spalten`, je Liste `konto`/`kategorie`, gilt für alle Konten), Lesen/Schreiben nur in `try`.
- **Markierung** (`data-markierung` der Zeile, Streifen links und leichte Tönung, helles und dunkles Thema):
  `abgeglichen` (Status „Abgeglichen“ oder abgestimmt) grün-grau; sonst `kategorisiert` (kein Split auf
  „Unkategorisiert“, Umbuchungen und Splitbuchungen eingeschlossen) grün; sonst `importiert` (Status „Importiert“)
  grau; sonst keine Markierung. Hover und Auswahl überdecken die Tönung, der Streifen bleibt.
- **Wiederkehrend:** Zeilen, deren Buchung zu einer Serie aus `GET /api/wiederkehrend` gehört (auch ausbleibende
  und beendete), tragen `data-wiederkehrend="ja"` und ein „↻“ vor dem Empfänger (nur Gestaltung, der Text der
  Zelle bleibt unverändert).
- **Durch Mail bestätigt** (abgestimmt 2026-11-12): Zeilen, deren Buchung einer aus Mails erkannten Erwartung
  (Grund Bestellung, PayPal oder Rückerstattung, beliebiger Zustand) zugeordnet ist, tragen `data-mail="ja"` und
  ein „✉“ vor dem Empfänger; der Titel der Zelle nennt Grund, Händler und Kennung. Quelle ist
  `GET /api/erwartungen`. Der Branch enthält deshalb `feature/mail-abgleich` und kann erst nach diesem gemergt
  werden.
- **Vorrang** (abgestimmt): Eine importierte Buchung mit Kategorie ist grün; vorläufige oder bestätigte Buchungen
  ohne Kategorie bleiben unmarkiert. Keine Änderung an REST, Datenmodell oder Protokoll.

## D-132 Doppelte Nummern aus parallelen Branches; Reihenfolge des Merges

- **Anlass:** Auftrag 2026-11-13: `feature/sammeltest` (Dokumente, Mail-Abgleich, ALF-BanCo-Import,
  Diagramm-dunkel) und `feature/spalten-markierung` gemeinsam abnehmen und auf main mergen.
- **Doppelte Nummern:** Auf den parallelen Branches wurden D-123 und D-128 je zweimal vergeben. Bestehende Einträge
  werden nicht umgeschrieben; Verweise gelten wie folgt: **D-123** = Dokumente bzw. ALF-BanCo-Import (aus dem
  Zusammenhang), **D-128** = Mail-Abgleich bzw. Berichtsdiagramme (Feature `diagramm-dunkel`). D-129 (Sprungziel)
  bezieht sich auf D-128 Berichtsdiagramme. Neue Einträge ab D-132.
- **Reihenfolge:** `feature/spalten-markierung` wird in `feature/sammeltest` übernommen (beide enthalten denselben
  Stand von `dokumente` und `mail-abgleich`), damit die Marke „durch Mail bestätigt“ (D-130) mit abgenommen wird;
  abgenommen und gemergt wird `feature/sammeltest`. Die beiden jüngeren Commits auf `feature/mail-abgleich`
  (Serien, D-131) sind nicht enthalten und bleiben auf ihrem Branch.

## D-133 Mail-Abgleich nach jedem Synchronisationslauf (berichtigt D-128)

- **Befund:** Bei der Vorbereitung der Abnahme (Meilenstein-Definition M20) fiel auf, dass der Abgleich nur nach
  fehlgeschlagenen Läufen lief; nach erfolgreichen Läufen ordnete erst der nächste Planer-Takt zu.
- **Entscheidung:** Wie in D-128 vorgesehen läuft der Abgleich nach **jedem** Lauf mit Endstatus (erfolgreich,
  fehlgeschlagen, abgebrochen, TAN abgelaufen), direkt nach der Prüfung auf unerwartete wiederkehrende Buchungen.
  Ohne `mail_abgleich` geschieht nichts (bestehende Abläufe und Protokolle unverändert).

## D-134 Sicherung einspielen in den Einstellungen ohne Importfelder

- **Befund:** Beim Übernehmen der Import-Seite für ALF-BanCo (D-126) war die Abfrage des Importformats und des Kontos
  versehentlich auch in das Senden der Sicherung in den Einstellungen geraten; „Prüfen“ und „Einspielen“ brachen dort
  mit einem Skriptfehler ab. Entfernt; die Sicherung sendet wieder nur die Datei.

## D-135 Abnahme M18 (Dokumente): Feinheiten

- Typerkennung: führende Leerzeilen und eine mbox-Trennzeile werden auch beim Lesen der Kopfzeilen übergangen.
- `POST /api/dokumente`: unbekannte Abfrageparameter → 422 `validierung`; `POST /api/dokumente/aus-mail`: Felder
  außer `nachricht_id` und `buchung_ids` → 422 `validierung`.
- Inhaltsantworten: `Cache-Control: private, no-store`; `filename*` trägt den unveränderten Dateinamen (nur
  `filename` ersetzt `"` durch `'`).
- Eingebettete Nachrichten (`message/rfc822`) sind ein Anhang und werden als ganze Nachricht ausgeliefert; ihre
  Unterteile erscheinen nicht als eigene Anhänge.
- Rückgängig/Wiederholen von „Umbenennen“ ändert nur den Dateinamen; die Verknüpfungen bleiben (vorher Konflikt
  „Dokument hängt an einer anderen Buchung“).

## D-136 Abnahme M20 (Mail-Abgleich): Schlüssel intern, Feinheiten

- Der Schlüssel einer Erwartung (Idempotenz der Erkennung) bleibt intern: Er steht in der Sicherungsdatei und in
  den gespeicherten Protokolleinträgen (damit Rückgängig/Wiederholen ihn wiederherstellen), erscheint aber weder in
  Antworten von `/api/aenderungen` noch in der Inhaltsprüfsumme der Sicherung (erwartungen.md 12, E-217).
  Sicherungen der Version 5, die vor dieser Änderung erstellt wurden (nur auf Feature-Branches möglich), haben
  eine andere Inhaltsprüfsumme.
- `GET /api/erwartungen`: unbekannte Abfrageparameter → 422 `validierung`.
- Lösen der letzten Buchung: Dokumente, die dadurch an keiner Buchung mehr hängen, entfallen schon vor der Antwort,
  damit `dokument_ids` den Stand nach der Änderung zeigt.

## D-137 Betragsfilter für wiederkehrende Buchungen (Feature `betragsfilter-wiederkehrend`, in Arbeit)

- **Anlass:** Gehalt und unregelmäßige Auslagenerstattungen kommen vom selben Empfänger. Eine Erstattung zwischen
  zwei Gehältern war eine „fremde Zahlung“ und brach die Kette; eine Erstattung als jüngste Buchung wurde Anker.
- **Modi:** `aus` (Verhalten M16), `toleranz` (Prozent, Ganzzahl 0–100, bezogen auf das aktuelle Glied),
  `mindestschwelle` (Betrag in Cent ohne Vorzeichen; nur je Empfänger). Mit dem Auftraggeber abgestimmt: Vorgabe für
  alle Empfänger ist Toleranz ±10 %, je Empfänger überschreibbar.
- **Kette mit Toleranz:**
  - Anker-Kandidaten sind die jüngsten Termine je Betragsklasse (kein passender Eintrag mehr als `T` Tage später),
    gesucht in den letzten `2·m` Monaten + `T`; Auswahl wie M16 (längste Kette, gleicher Betrag, jünger).
  - Vorgänger: gleicher Betrag, dann innerhalb der Toleranz, dann Datumsnähe, dann jünger. Ein Vorgänger außerhalb
    der Toleranz bleibt möglich (Preisänderung am Termin) – aber nur, solange die Kette seit dem Anker nichts
    übergangen hat und in diesem Schritt nichts übergeht; sonst Bruch mit neuem Grund `betrag`.
  - Einträge zwischen Vorgänger und Glied, deren Betrag weder zum Glied noch zum Vorgänger passt, werden übergangen
    (Rolle `anderer_betrag`), statt die Kette zu brechen.
  - **Mehrheitsregel nur für die Vorgabe:** Übergeht die Kette (ab dem ersten Glied bis zur jüngsten Buchung) mehr
    Einträge, als sie Glieder hat, gilt der Rhythmus als nicht erfüllt. Auf dem großen Zufallsdatensatz (gross.kmy)
    lieferte die Toleranz ohne diese Regeln 160 zusätzliche Zufallsserien, mit ihnen 4 (aus: 34, ±10 %: 31 Serien).
- **Mindestschwelle:** Einträge unter der Schwelle werden vollständig übergangen; keine Mehrheitsregel (bewusste
  Einstellung). Eine Zahlung unter der Schwelle meldet keinen geänderten Betrag; mit Toleranz wird eine Abweichung am
  Termin weiterhin gemeldet (Preisänderung).
- **Speicherort:** Vorgabe in `meta` (`wk_filter_modus`, `wk_filter_toleranz`) als Einstellung der Instanz – nicht
  im Protokoll, nicht in der Sicherung (wie `KontorConfig`, E-096). Je Empfänger Tabelle `empfaenger_wiederkehrend`
  (Buchbestand, Objektart `empfaenger`, Protokollform-Feld `wiederkehrend` nur bei eigener Einstellung, damit
  bestehende Formen und Prüfsummen gleich bleiben), Sicherungsdatei Schemaversion 6.
- **REST:** `GET /api/wiederkehrend/einstellungen`, `PUT /api/wiederkehrend/einstellungen/vorgabe`,
  `PUT`/`DELETE /api/empfaenger/{id}/wiederkehrend` (Aktion `wiederkehrend_filter_setzen`). Begründung: neue Felder
  `empfaenger` (oben), `betragsfilter`, `betragsfilter_text` (je Eintrag), Rolle/Urteil `anderer_betrag`, Grund
  `betrag`. Oberfläche: Abschnitt „Wiederkehrende Buchungen“ in den Einstellungen, Dialog `wk-filter-dialog`, Knopf
  `wk-filter-oeffnen` im Begründungsdialog.
- **Auswirkung auf Abnahmetests:** Schema der Begründung (zusätzliche Felder und Werte) und die M16-Beispiele mit
  abweichendem Betrag (−50,00 € neben −320,32 € ist jetzt `anderer_betrag` statt `zusaetzlich`); die Referenz der
  Zufallsgruppen rechnet ohne Filter. Mit Vorgabe `aus` sind M5, M16 und Leistung grün. Klärung über die
  Meilenstein-Definition.

## D-138 Weitere doppelte Nummern aus parallelen Branches (ergänzt D-132)

- Auf `feature/geheimnisse`/`feature/gmail-app-passwort` wurden D-129 und D-130 erneut vergeben. Verweise gelten aus
  dem Zusammenhang: **D-129** = Schutz der Geheimnisse mit dem Login-Passwort bzw. Sprungziel mittig, **D-130** =
  Gmail mit App-Passwort bzw. Spaltenbreiten und Markierung. Abnahme als M23 (Geheimnisse und Gmail) und M24
  (Serien im Mail-Abgleich, D-131); neue Einträge ab D-139.

## D-139 Serien in der Liste der Erwartungen nur auf Anfrage (ergänzt D-131)

- **Anlass:** Vorbereitung der Abnahme (M24). Mit D-131 lieferte `GET /api/erwartungen` ohne Grundfilter auch
  Einträge mit `grund = "serie"`; das änderte die Antwort früherer Aufrufe (M20) rückwärtsinkompatibel.
- **Entscheidung:** Serien erscheinen nur mit `grund=serie` oder mit dem neuen Abfrageparameter `serien=ja` (ohne
  Grundfilter). Die Seite `/erwartet` setzt `serien=ja`, solange kein Grund gewählt ist; sichtbares Verhalten
  unverändert.

## D-140 Vorbereitung der Abnahme M23/M24: Korrekturen

- **Schutz ausschalten** löscht die gemerkte Bank-PIN (sie war danach nur noch mit dem Systemschlüssel gespeichert
  und wurde weiter benutzt, obwohl `pin_gemerkt` `false` meldete). Andere geschützte Geheimnisse bleiben.
- **Serien (D-131):** ausgelassen werden nur Serien, deren letzte Buchung einer Erwartung aus einer Mail (nicht
  `manuell`) zugeordnet ist; Sortierung bei gleicher Frist: gespeicherte Erwartungen nach Nummer, dann Serien.
  `serien=ja` steht nur in der REST-Abfrage, nicht in der Adresse der Seite `/erwartet` (berichtigt D-139).
- **Erstattung:** „Unkategorisiert“ wird an `extern_id = "kontor:unkategorisiert"` erkannt, nicht am Namen.

## D-141 Abnahme M23: Knopf „Speichern und Verbindung testen“ nach einem Fehler wieder bedienbar

- Nach einer fehlgeschlagenen Verbindung blieb der Knopf gesperrt (das Ereignisziel war nach der Anfrage nicht mehr
  gesetzt). Der Knopf wird jetzt vor der Anfrage gemerkt und danach immer wieder freigegeben.

## D-142 Serien: Auslassen bei Zuordnung zu jeder Erwartung (ersetzt den Serien-Teil von D-140)

- Die freigegebene Meilenstein-Definition M24 (1.2) lässt eine Serie aus, wenn ihre letzte Buchung irgendeiner
  gespeicherten Erwartung zugeordnet ist, auch einer manuellen (sonst erschiene dieselbe Zahlung doppelt). Die
  Einschränkung auf Mail-Erwartungen aus D-140 ist zurückgenommen.

## D-143 Abnahme M25: Vorgabe des Betragsfilters ohne Neuzeichnen speichern

- Nach „Speichern“ der Vorgabe wurde die Einstellungsseite neu gezeichnet; eine sofort folgende zweite Eingabe
  landete in den alten Feldern und ging verloren (zweites Speichern schickte den alten Stand). Die Vorgabe ist eine
  Instanz-Einstellung ohne Rückgängig: Die Felder übernehmen die Antwort des Servers, die Seite bleibt stehen, andere
  Tabs laden beim nächsten Zeigen neu.

## D-141 Bedienung auf dem Handy (Feature `UXMobile`, iterativ, Branch `feature/UXMobile`)

- **Anlass:** Auftrag 2026-11-13: Die Bedienung auf dem Handy (Pixel 7, 412 × 915 CSS-Pixel) ist an vielen Stellen
  schlecht: Im Kontoblatt wurden durch Tippen mal Buchungen markiert, mal die Einzelheiten gezeigt, ohne dass der
  Zustand sichtbar war; Tabellen (z. B. wiederkehrende Buchungen) waren in schmale Spalten gequetscht. Vorgabe: die
  Desktop-Bedienung bleibt unverändert. Nummer D-141, weil D-131 bis D-140 auf parallelen Branches vergeben sind.
- **Grundsatz:** Alle Änderungen wirken nur im mobilen Layout (`data-layout="mobil"`, < 768 CSS-Pixel). Neue
  Elemente, die es nur mobil gibt, tragen `nur-mobil` und sind auf dem Desktop ausgeblendet; Desktop-Bildschirmfotos
  von 16 Ansichten sind vorher/nachher pixelgleich.
- **Kopfzeile:** eine Zeile mit Menü, Suche (Lupe `suche-knopf`, blendet das Suchfeld als zweite Zeile ein), Sync,
  Rückgängig, Wiederholen (unter 390 px nur über die Palette), Palette, Glocke und `tabs-knopf` mit der Zahl offener
  Ansichten. Die Tab-Leiste ist mobil ausgeblendet; `tabs-knopf` klappt sie als Liste auf (Wahl schließt die Liste,
  Esc/Tippen daneben auch). Der Mock-Hinweis ist einzeilig, Tippen zeigt den ganzen Text.
  Entscheidung des Auftraggebers: „Kompakt, Tabs als Knopf“.
- **Auswahlmodus im Kontoblatt (Android-Standard, Entscheidung des Auftraggebers):**
  - Tippen ohne Auswahl öffnet die Einzelheiten (wie bisher). **Lange Berührung startet den Auswahlmodus** mit dieser
    Zeile (kurze Vibration), statt das Kontextmenü zu öffnen; im Auswahlmodus nimmt sie die Zeile hinzu. Das vom
    Browser zur langen Berührung gemeldete `contextmenu` wird in der Liste ignoriert. Auf dem Desktop (auch mit
    Touch) bleibt lange Berührung = Kontextmenü.
  - Im Auswahlmodus (`buchungsliste` mit `data-auswahlmodus="ja"`) zeigt jede Zeile links einen Kreis bzw. ein
    Häkchen; Tippen schaltet um. Direkt unter der App-Kopfzeile (über dem Seitenkopf, Rückgängig bleibt erreichbar)
    liegt die Leiste `auswahl-kopf` mit `auswahl-beenden` (✕), `auswahl-kopf-anzahl` („3 ausgewählt“) und
    `auswahl-alle`. Die Zurück-Taste des Handys beendet den Auswahlmodus
    (eigener History-Eintrag beim Start).
  - `mehrfach-leiste` zeigt mobil nur Kategorie, Tags, Löschen und `mehrfach-mehr` („⋮ Mehr“ = Kontextmenü der
    Auswahl); die übrigen Knöpfe bleiben im DOM, sind aber ausgeblendet. Der schwebende Knopf „+“ (= `buchung-erfassen`)
    ist im Auswahlmodus ausgeblendet.
  - Kein „klebendes“ Hover nach dem Tippen (`hover: none`): es sah wie eine Markierung aus.
- **Wischgesten** (Entscheidung „Behalten, mit Rückmeldung“): Die Zeile folgt dem Finger; darunter erscheint
  „✓ Auswählen“/„✕ Abwählen“ (rechts) bzw. „Kategorie …“ (links), farbig, sobald der Mindestweg von 80 px erreicht ist.
  Mobil zählt nur der Weg (≥ 80 px waagerecht, ≤ 40 px senkrecht), nicht mehr die Dauer ≤ 1 000 ms – sonst würde ein
  langsames Wischen „bereit“ anzeigen und beim Loslassen nichts tun.
- **Kompakte Liste:** Empfänger und Betrag in der ersten Zeile, Datum und Kategorie klein darunter; Kopfzeile als
  schmale Sortierleiste („Sortieren: Datum ↓ Empfänger Betrag“). Kontoblatt-Kopf in einer Zeile (Filter, ⚙, ⇄ als
  Symbolknöpfe), „Buchung erfassen“ als schwebender Knopf unten rechts. Filterleiste zweispaltig.
- **Kontextmenüs und Dialoge** mobil als Blatt vom unteren Rand (volle Breite, Griff, abgedunkelter Hintergrund;
  Tippen daneben schließt). Deaktivierte Menüeinträge sind mobil ausgeblendet. Dialoge setzen den Fokus mobil nicht in
  ein Textfeld, damit die Bildschirmtastatur erst auf Tippen erscheint. `interactive-widget=resizes-content` im
  Viewport hält Blätter über der Tastatur.
- **Tabellen als Karten:** `mobilKarten(tabelle, rollen)` (kern.js) gibt jeder Zelle eine Rolle (`data-mk`: titel,
  betrag, info mit Beschriftung aus der Spaltenüberschrift, info-, zeile, status, aktion, aktion2, auswahl, weg); CSS
  zeigt mobil je Zeile eine Karte (Titel und Betrag oben, Angaben darunter). Eingesetzt für Finanzübersicht,
  Kategorien der Übersicht, Konten, wiederkehrende Buchungen, Tilgungsplan, Berichte (Kontostand, Einnahmen/Ausgaben,
  Einzelbuchungen), Betragsfilter, Empfänger. Suchtreffer mobil wie die kompakte Liste, Tippen springt zur Buchung im
  Konto. Plotly-Werkzeugleiste mobil ausgeblendet.
- **Auswirkung auf Abnahmetests (Spezifikationsänderung, Klärung über die Meilenstein-Definition):** oberflaeche.md
  16.4 (lange Berührung auf einer Buchungszeile = Kontextmenü; Wischen ≤ 1 000 ms) und 27.1.2 (Tab-Leiste sichtbar)
  gelten mobil nicht mehr; betroffen sind die Handy-Tests zur langen Berührung im Kontoblatt (M8, M16, M17) und die
  Sichtbarkeit der Tab-Leiste auf dem Handy (M17).

## D-142 Statische Dateien immer prüfen; wiederkehrende Buchungen mobil als feste Karte (Nachtrag zu D-141)

- **Anlass:** Nach dem Update auf 0.12 zeigte das Handy des Auftraggebers weiter die alte Oberfläche (alte Tabelle der
  wiederkehrenden Buchungen). Ursache: Dateien unter `/oeffentlich/` wurden ohne `Cache-Control` ausgeliefert; der
  Browser hält sie dann nach eigener Schätzung (Alter der Datei) für frisch und fragt nicht nach – auch der Service
  Worker holte sie über diesen Zwischenspeicher.
- **Entscheidung:** Antworten unter `/oeffentlich/` und `/static/` tragen `Cache-Control: no-cache`, sofern sie keine
  eigene Angabe haben (bedingte Anfrage mit ETag, in der Regel 304). Der Service Worker (Cache `kontor-huelle-6`) ruft
  statische Dateien mit `cache: "no-cache"` ab. Nach einem Update genügt damit ein Neuladen; bereits betroffene Geräte
  bekommen den neuen Service Worker beim nächsten Aufruf und ab dem darauffolgenden Laden den aktuellen Stand.
  Die Spezifikation regelt nur `/sw.js` und die Hülle (oberflaeche.md 18); für die übrigen Dateien ist nichts festgelegt.
- **Wiederkehrende Buchungen mobil:** statt der allgemeinen Kartenansicht eine feste Karte in drei Zeilen: Empfänger
  (höchstens zwei Zeilen) und Betrag; Rhythmus · Konto (gekürzt) und „x € / Jahr“ rechtsbündig unter dem Betrag;
  Status-Marke und „Nächste TT.MM.JJJJ“. Farbiger linker Rand nach Status (aktiv grün, ausbleibend gelb), Summe der
  Jahreskosten als Kasten. Tippen auf die Karte öffnet die Aktionen der Serie (wie der Knopf „…“). Desktop unverändert.

## D-144 Doppelte Nummern durch `feature/UXMobile` (ergänzt D-132, D-138)

- `feature/UXMobile` wurde parallel ohne Abnahme auf main gemergt und vergibt D-131, D-141 und D-142 ein zweites Mal.
  Verweise gelten aus dem Zusammenhang: **D-131** = Serien im Mail-Abgleich bzw. Bedienung auf dem Handy (UXMobile),
  **D-141** = Knopf nach Fehler (M23) bzw. Bedienung auf dem Handy, **D-142** = Serien auslassen (M24) bzw.
  statische Dateien mit no-cache und mobile Karte der wiederkehrenden Buchungen. Neue Einträge ab D-145.
- UXMobile hat keine eigene Meilenstein-Definition und keine eigenen Abnahmetests; geprüft ist nur, dass die
  bestehende Abnahmesuite (einschließlich aller Browsertests) mit ihm grün bleibt.

## D-145 Statistische Analyse, experimentell

- **Anlass:** Das Kontoblatt soll zeigen, was sich regelmäßig wiederholt, was ungewöhnlich ist und was zum bekannten
  Rauschen gehört. Die bestehende Ketten-Erkennung (`wiederkehrend.py`) bleibt unverändert; sie ist ein Urteil mit
  festem Raster und letzter Rate, keine Beschreibung der Streuung.
- **Entscheidung:** Neuer nur lesender Endpunkt `GET /api/statistik?konto_id=&stichtag=` und die Seite `/statistik`.
  Antwort trägt `"experimentell": true`. Der Endpunkt steht nicht in `openapi.yaml`. Die lokale Oberfläche-Prüfung
  lässt `/api/statistik` ausdrücklich zu. Kein Buchbestand, kein Protokoll, keine Sicherung.
- **Rechnung:** Gegenpartei ist die IBAN, sonst der normalisierte Empfängername; mehrere Betragsgruppen derselben
  Gegenpartei werden getrennt (neuer Modus ab 15 % Abstand zum Median der Gruppe, mindestens 1 €). Je Gruppe mit
  mindestens drei Buchungen: Median und MAD der Abstände und der Beträge, ganze Cent. Regelmäßig ab vier Buchungen,
  wenn der Medianabstand in einem Raster liegt (5–9, 12–17, 26–35, 80–100, 330–400 Tage) und beide MAD höchstens
  15 % bzw. 10 % des Medians sind. Drei Buchungen mit denselben Schwellen sind „möglich“, eine Gruppe im Raster mit
  zu großer Streuung ist „Kandidat“. Die Jahresrate ist `Median der Kosten × 365 / Medianabstand`. Fixkosten summieren
  nur regelmäßige Ausgaben. Umbuchungen auf ein anderes Bestandskonto und Tilgung ohne Zinsaufwand (Konto aus
  `kredit`) zählen nicht. Rauschen sind die übrigen Buchungen je Kategorie als Monatssumme (Median, 10.- und
  90.-Perzentil). Ungewöhnlich ist ein robustes z ab 3,50 gegen die Reihe oder gegen das Rauschen der Kategorie;
  eine überfällige regelmäßige Reihe zusätzlich an der Lücke. Der Service-Worker-Cache heißt seit D-146
  `kontor-huelle-8`.

## D-146 Wiederkehrende Buchungen aus der Oberfläche

- **Anlass:** Die Seite „Wiederkehrende Buchungen“ und die daraus abgeleiteten Einträge unter „Was kommt noch?“
  überlagern sich. Die statistische Analyse (D-145) beschreibt die Regelmäßigkeit; für die erwarteten Zahlungen
  braucht es ein eigenes Konzept. Bis dahin soll die alte Seite nicht mehr in der Bedienung stehen.
- **Entscheidung:** Navigation, Adresse `/wiederkehrend`, Befehlspalette, Betragsfilter in den Einstellungen,
  Serienmarke im Kontoblatt und der Filter „Serie“ unter „Was kommt noch?“ entfallen. „Was kommt noch?“ zeigt
  nur noch Erwartungen aus Mails und manuelle Einträge. Die Erkennung in `wiederkehrend.py` und ihre
  REST-Endpunkte bleiben, bis das neue Konzept sie ablöst; sie schreiben weiterhin nichts in den Buchbestand.
  Der Service-Worker-Cache heißt seit D-147 `kontor-huelle-9`.

## D-147 Mail-Blatt

- **Anlass:** Abgerufene Mails waren nur als Anhang einer Buchung oder indirekt über „Was kommt noch?“ sichtbar.
  Die Zuordnung einer Mail zu einer erwarteten Zahlung und zu Buchungen soll auf einen Blick lesbar sein.
- **Entscheidung:** Seite `/mail` („Mail-Blatt“). `GET /api/mail/nachrichten` ergänzt jedes Element um
  `postfach` und `zuordnung`: die Erwartungen, deren Mail-Liste diese Nachricht enthält, mit Zustand, Händler,
  Betrag und den zugeordneten Bestandskonten-Buchungen. Kein neues Objekt, kein Protokoll. Der
  Service-Worker-Cache heißt seit D-148 `kontor-huelle-10`.

## D-148 Kontextmenü der Tabs

- **Anlass:** Ein Tab ließ sich nur über das Kreuz, den Mittelklick oder die Entf-Taste schließen.
- **Entscheidung:** Rechtsklick und Umschalt+F10 auf einem Tab öffnen „Schließen“, „Andere Tabs schließen“
  und „Alle Tabs schließen“. „Andere“ behält den angeklickten Tab und zeigt ihn, wenn er nicht aktiv war.
  „Alle“ leert die Leiste; die Oberfläche zeigt danach die Startseite, wie beim Schließen des letzten Tabs.
  Auf dem Handy gilt dieselbe Liste nach einer langen Berührung. Der Service-Worker-Cache heißt
  `kontor-huelle-10`. Seit D-149 heißt der Cache `kontor-huelle-11`.

## D-149 Navigation in Themengruppen

- **Anlass:** Die linke Leiste war eine lange Folge ohne Zusammenhang. Mail, erwartete Zahlungen und die
  statistische Analyse standen zwischen den Stammdaten.
- **Entscheidung:** Fünf Gruppen mit Überschrift: Buchhaltung, Zahlungen, Auswertung, Regeln, Betrieb.
  Alt+1 bis Alt+7 bleiben bei Finanzübersicht, Konten, Kategorien, Kredite, Berichte, Import und Einstellungen.
  Der Service-Worker-Cache heißt seit den Pastelltönen `kontor-huelle-12`. Jede Gruppe hat einen eigenen
  Ton: Blau, Pfirsich, Mint, Flieder, Sand. Im dunklen Thema dieselben Farben, nur gedämpft.

## D-150 Gruppierung im Kontoblatt

- **Anlass:** Im Kontoblatt lagen die Buchungen als fortlaufende Liste. Eine Periode war nur durch Mitlesen der
  Datumsspalte zu überblicken.
- **Entscheidung:** Über der Liste schaltet „Keine“, „Tage“ oder „Monate“ (`?gruppierung=tag` oder `monat`,
  kein Parameter der Buchungsliste). Jede Periode ist ein Balken mit Eingang (positive Beträge), Ausgang
  (negative Beträge), Summe und Anzahl. Der Balken klappt die Buchungen der Periode ein und aus. Solange
  gruppiert wird, lädt das Blatt alle Seiten des aktuellen Filters, damit die Zahlen der Periode vollständig
  sind. Der Service-Worker-Cache heißt seit D-151 `kontor-huelle-14`.

## D-151 Alle Perioden klappen, Tagessicht nur im Ausschnitt

- **Anlass:** In der Tagessicht wurden alle Buchungen auf einmal gezeichnet. Bei einigen tausend Buchungen
  stockte das Blatt. Es fehlte ein Schalter für alle Perioden zugleich.
- **Entscheidung:** „Alles zusammenklappen“ und „Alles aufklappen“ stehen neben der Gruppierung. Ab hundert
  Zeilen zeichnet das Kontoblatt nur den sichtbaren Ausschnitt samt einem kleinen Puffer; die Höhen der
  Balken und Zeilen werden einmal gemessen. Die Seiten der Buchungsliste lädt die Gruppierung parallel zu
  je 500 Einträgen. Der Service-Worker-Cache heißt seit D-152 `kontor-huelle-15`.

## D-152 Gruppierung nach Datum als Hierarchie

- **Anlass:** Tag und Monat ließen sich nur getrennt wählen. Ein Jahr, sein Monat und der Tag waren nicht
  ineinander geschachtelt.
- **Entscheidung:** Die Leiste bietet „Keine“ und „nach Datum“ (`?gruppierung=datum`). „nach Datum“ zeigt
  Jahre, darin Monate, darin Tage, darin die Buchungen. Jede Ebene hat Eingang, Ausgang, Summe und Anzahl
  und klappt ihre Kinder ein. Ein zugeklappter Knoten verbirgt die Ebenen darunter. „Alles zusammenklappen“
  und „Alles aufklappen“ gelten für Jahre, Monate und Tage. Der Service-Worker-Cache heißt seit D-153
  `kontor-huelle-16`.

## D-153 Mail-Blatt seitenweise, mit Grund der Buchungszuordnung

- **Anlass:** Das Mail-Blatt lud alle Mails auf einmal. Bei zehntausenden Einträgen blieb die Liste leer und
  „Mails abrufen“ grau, ohne dass ein Stand sichtbar war. An einer zugeordneten Buchung fehlte, warum sie passt.
- **Entscheidung:** Das Blatt zeigt 100 Mails je Seite, die neuesten zuerst, und den Stand je Postfach
  (Anzahl, letzter Erfolg, Fehler). Die Filter zählen Alle, Buchung zugeordnet, Nur erwartet und Nicht erkannt.
  Jede zugeordnete Buchung nennt den Grund: Kennung im Verwendungszweck oder beim Empfänger, passender Betrag
  und Name, oder manuelle Zuordnung. Der Service-Worker-Cache heißt seit D-154 `kontor-huelle-17`.

## D-154 Mail mit Pfeiltasten, festes Lesefenster, keine Leerwörter

- **Anlass:** Im Mail-Blatt ließ sich die Auswahl nicht mit den Pfeiltasten bewegen, und der Mailtext
  scrollte mit der Liste mit. In manchen Fenstern stand das Wort „null“, „nul“, „None“ oder „undefined“,
  wenn ein Wert fehlte.
- **Entscheidung:** Pfeil nach unten und oben wählen die nächste oder vorige Mail und zeigen ihren Inhalt.
  Am Seitenrand wird geblättert. Die Liste und der Inhalt haben getrennte Rollbereiche; auf dem Desktop
  bleibt der Inhalt neben der Liste stehen. Fehlende Werte werden nicht als diese Wörter gezeichnet.
  Die Nulllinie im einfachen Diagramm heißt in der Darstellung nur noch Basislinie.
  Der Service-Worker-Cache heißt seit D-155 `kontor-huelle-18`.

## D-155 Mailkonto wählen, Bestätigung durch Torsten oder Tina

- **Anlass:** Es gibt mehrere Postfächer, das Mail-Blatt zeigte sie aber nur gemischt. Buchungen sollen
  von Torsten oder Tina bestätigt werden können, bei einem gemeinsamen Passwort.
- **Entscheidung:** Im Mail-Blatt wählt man „Alle Konten“ oder ein Postfach. Die Liste und die Zähler gelten
  für diese Auswahl. Das Passwort bleibt das eine Haushaltspasswort. Nach dem Öffnen, und nach dem Abmelden
  erneut, fragt Kontor, wer gerade da ist. Der Name steht oben rechts und lässt sich wechseln, ohne das
  Passwort neu einzugeben. „Als Torsten bestätigen“ oder „Als Tina bestätigen“ setzt den gleichnamigen Tag
  an die Buchung; beide können dieselbe Buchung bestätigen. Der Service-Worker-Cache heißt seit D-156 `kontor-huelle-19`.

## D-156 Empfänger wie Buchungen bestätigen

- **Anlass:** Empfänger sollen sich genauso bestätigen lassen wie die Buchungen im Kontoblatt, von Torsten
  oder Tina.
- **Entscheidung:** Auf der Seite Empfänger trägt jede Zeile die Namen, die sie bestätigt haben, und den Knopf
  „Als Torsten bestätigen“ oder „Als Tina bestätigen“. Die Auswahl mehrerer Empfänger und das Kontextmenü tun
  dasselbe. Beide können denselben Empfänger bestätigen. Zurücknehmen gilt nur für den eigenen Namen. Beim
  Zusammenführen bleiben die Bestätigungen am Ziel erhalten. Der Service-Worker-Cache heißt seit D-157
  `kontor-huelle-20`.

## D-157 Label für verdächtige Buchungen

- **Anlass:** Ungewohnte Buchungen sollen im Kontoblatt auffallen, mit einer lesbaren Einschätzung. Sobald die
  Buchung bestätigt ist, soll das Label weg sein.
- **Entscheidung:** Eine Buchung mit Status Importiert oder Vorläufig trägt das Label „Verdächtig“, wenn ihr
  Empfänger ausschließlich in solchen Buchungen vorkommt oder ihr Zahlungsbetrag stark von den bestätigten
  Buchungen desselben Empfängers abweicht. Bestätigt und Abgeglichen tragen kein Label. Der Zahlungsbetrag ist
  die Summe auf genau einem Giro- oder Sparkonto. Für die Streuung braucht es mindestens vier bestätigte
  Zahlungen. Stark heißt robustes z ab 3,50, dieselbe Schwelle wie in der statistischen Analyse. Liegen alle
  bestätigten Zahlungen auf demselben Betrag, gilt eine Abweichung von mehr als der Hälfte und mindestens
  20 €. Die Erklärung steht am Label und in den Einzelheiten. Das Label wird beim Lesen gebildet und nicht
  gespeichert. Der Service-Worker-Cache heißt seit D-161 `kontor-huelle-22`.

## D-158 Filter im Kontextmenü einer Buchung

- **Anlass:** Aus einer Buchung heraus soll die Liste auf denselben oder einen ähnlichen Empfänger und auf
  denselben oder einen ähnlichen Verwendungszweck eingeschränkt werden.
- **Entscheidung:** Das Kontextmenü einer Buchung hat den Eintrag „Filter“ mit dem Untermenü „gleicher
  Empfänger“, „Gleicher Verwendungszweck“, „ähnlicher Verwendungszweck“ und „ähnlicher Empfänger“. Gleicher
  Empfänger ist die Empfänger-ID. Gleicher Verwendungszweck ist der Text nach der üblichen Normalisierung.
  Ein leerer Verwendungszweck trifft nur leere. Ähnlicher Verwendungszweck trifft Buchungen, die mindestens
  ein Wort ab vier Buchstaben teilen; Ziffernfolgen zählen nicht. Ähnlicher Empfänger trifft Namen, deren
  Vergleichsschlüssel gleich beginnt und der gemeinsame Anfang mindestens vier Zeichen lang ist, den Namen
  selbst eingeschlossen, Aliase mitgezählt. Die Filterleiste zeigt den gesetzten Wert und lässt sich
  zurücksetzen. Der bisherige Filter „Verwendungszweck“ bleibt eine Teilzeichenkette.

## D-159 Bestätigen setzt den Status

- **Anlass:** Die Bestätigung durch Torsten oder Tina soll den Status der Buchung verändern. Der Weg ist
  Importiert, dann Bestätigt.
- **Entscheidung:** „Als … bestätigen“ setzt bei Buchungen im Status Importiert zugleich den Status auf
  Bestätigt, in derselben Rückgängig-Gruppe wie die Namensmarkierung. Zurücknehmen nimmt nur den Namen weg.
  Vorläufig bleibt Vorläufig, weil dieser Übergang nicht vorgesehen ist. Das Label „Verdächtig“ verschwindet
  mit dem Status Bestätigt.

## D-160 Verschieben nur mit Alt

- **Anlass:** Buchungen verschieben soll möglich bleiben, der Knopf dafür aber nicht in der Titelzeile stehen.
- **Entscheidung:** Die Titelzeile des Kontoblatts hat keinen Knopf „Verschieben…“. Der Eintrag „Auf anderes
  Konto verschieben…“ erscheint im Kontextmenü nur, wenn es mit gehaltener Alt-Taste geöffnet wird. Auf dem
  Handy, wo es keine Alt-Taste gibt, bleibt der Eintrag im Menü und in der Auswahlleiste.

## D-161 Stifte in den Einzelheiten

- **Anlass:** Ein Doppelklick im Kontoblatt soll nicht mehr bearbeiten. Jeder Bestandteil einer Buchung soll
  in den Einzelheiten einen Stift zum Bearbeiten haben.
- **Entscheidung:** Doppelklick auf eine Zelle öffnet keinen Editor. In den Einzelheiten hat Datum, Empfänger,
  Verwendungszweck, die Buchungssätze, die Tags und der Status je einen Stift. Der Editor sitzt in der
  Zeile der Einzelheiten. Der Status bleibt auch bei abgestimmten Buchungen erreichbar, die übrigen Stifte
  nicht. F2 und der Menüeintrag für den Verwendungszweck bleiben. Der Service-Worker-Cache heißt seit D-164
  `kontor-huelle-23`.

## D-162 Split ausgleichen

- **Anlass:** Beim Anlegen eines Splits soll jede Zeile den Betrag übernehmen können, der die Buchung auf 0 stellt.
- **Entscheidung:** Im Split-Dialog hat jede Zeile den Knopf „Split Ausgleichen“. Er setzt den Betrag dieser Zeile
  auf die negative Summe der übrigen Zeilen, in ganzen Cent. Der bisherige Betrag der Zeile zählt nicht mit.
  Leere oder ungültige übrige Beträge zählen als 0. Ist der Rest schon 0, wird 0 gesetzt.

## D-163 Split zur Vorlage

- **Anlass:** Im Split-Fenster soll der gerade gezeigte Split als Split-Vorlage gespeichert werden können.
- **Entscheidung:** Der Dialog hat das Namensfeld und den Knopf „Diesen Split zur Vorlage machen“. Voreingestellt
  ist der Empfänger, sonst der Verwendungszweck. Gespeichert wird über `POST /api/vorlagen`: die Kategorie-Teile
  (Aufwand oder Ertrag) mit Betrag und Memo, dazu die Bedingung Empfänger gleich. Das Bestandskonto ist kein Teil.
  Der Dialog bleibt offen.

## D-164 Regel der Split-Vorlage

- **Anlass:** Eine Split-Vorlage soll nach Empfänger und Splitbetrag angewendet werden.
- **Entscheidung:** Auf der Seite Split-Vorlagen zeigt jede Vorlage die Schlüssel Empfänger und Splitbetrag und
  lässt sie speichern. Der Empfänger ist die Bedingung `empfaenger gleich`. Der Splitbetrag ist der Gesamtbetrag
  der Teile; ändert man ihn, wandert die Differenz in ganzen Cent auf einen Teil, damit Schlüssel und Teile
  zusammenpassen. Verwendungszweck und Konto sind keine Schlüssel. Eine Vorlage trifft, wenn Empfänger und
  Splitbetrag passen. Angewendet wird sie über „Vorlagen anwenden“ und beim Import, nicht durch Umschreiben
  bestehender Buchungen von selbst. Der Service-Worker-Cache heißt seit D-165 `kontor-huelle-24`.

## D-165 Zwei Buchungen als Dublette, Vorschlag nach Betrag, Datum und Empfänger

- **Anlass:** „Als Dublette markieren…“ war nur wählbar, wenn genau eine Buchung schon in einem offenen
  Dublettenverdacht stand. Zwei markierte Buchungen ließen sich deshalb nicht als Dublette kennzeichnen.
  Zusätzlich sollen Paare vorgeschlagen werden, die im Betrag, im Buchungsdatum und im Empfänger übereinstimmen.
- **Entscheidung:** Bei genau zwei ausgewählten Buchungen ist der Eintrag aktiv, auch ohne bestehenden Verdacht.
  Der bisherige Dialog gilt. Abbrechen speichert nichts. Erst „Diese behalten“ oder „Keine Dublette“ legt den
  Verdacht an (`POST /api/dubletten`) und löst ihn über die bisherige Auflösung auf. Dabei kann jede der beiden
  Buchungen behalten werden; entfernt wird die andere. Mehr als zwei bleibt deaktiviert. Eine einzelne Buchung
  verhält sich wie bisher. Vorschläge kommen zur Prüfung beim Import und bei der Synchronisation hinzu, sie
  ersetzen sie nicht: gleicher Zahlungsbetrag in ganzen Cent (Summe der Splits auf genau einem Giro- oder
  Sparkonto, das Vorzeichen zählt mit), gleiches Buchungsdatum, gleiche Empfänger-Id. Buchungen ohne Empfänger
  passen nicht zueinander. Zwei Buchungssätze einer Buchung sind keine zwei Buchungen. Ein Vorschlag wird nicht
  von selbst zusammengeführt und ändert keine Buchung. Er erscheint auf der Seite Dubletten und in der Liste
  offener Verdachte des Kontoblatts. Paare, die schon in einem Verdacht stehen, werden nicht noch einmal
  vorgeschlagen. Der Service-Worker-Cache heißt `kontor-huelle-24`.

## D-166 Empfänger markieren wie im Kontoblatt

- **Anlass:** Empfänger sollen sich auf dieselbe Art markieren lassen wie Buchungen im Kontoblatt, vor allem, um
  mehrere Empfänger bequem zusammenzuführen. Bisher ging das nur über die Kästchen der ersten Spalte.
- **Entscheidung:** Die Zeilen der Empfängerliste tragen `aria-selected` und werden wie im Kontoblatt bedient:
  Klick wählt genau einen Empfänger, Strg/⌘-Klick schaltet um, Umschalt-Klick markiert einen Bereich ab dem
  Anker, Strg+Umschalt-Klick fügt einen Bereich hinzu. Mit der Tastatur: Pfeiltasten, Pos1/Ende, Umschalt+Pfeil
  (Bereich), Strg+Pfeil (nur Fokus), Leertaste (umschalten), Strg+A (alle), Esc (Auswahl aufheben),
  Eingabe/F2/Doppelklick (Bearbeiten), Umschalt+F10/Kontextmenütaste (Menü). Rechtsklick auf eine nicht markierte
  Zeile markiert nur sie. Das Kontextmenü bietet ab zwei markierten Empfängern „n Empfänger zusammenführen…“
  (`em-zusammenfuehren`, derselbe Dialog wie der Knopf). Mobil schaltet Tippen um, die lange Berührung öffnet das
  Menü. Die Kästchen `empfaenger-auswahl-{id}` bleiben und zeigen die Auswahl an. Die Anzahl steht in
  `empfaenger-auswahl-anzahl` (`data-anzahl`). Der Service-Worker-Cache heißt `kontor-huelle-25`.

## D-167 Kontoblatt ganz mit der Tastatur bedienen

- **Anlass:** Im Kontoblatt sollen sich alle Einstellungen und Aktionen ohne Maus vornehmen lassen.
- **Entscheidung:** Kürzel sind einzelne Tasten ohne Strg/Alt. Sie wirken nur außerhalb von Textfeldern, Auswahllisten,
  Dialogen, Menüs und dem Kategorienbaum. So kollidieren sie weder mit Browser-Kürzeln noch mit Strg+K, Strg+Z oder
  Alt+1…8. Die Tabelle `KUERZEL` in `konto.js` ist die einzige Quelle für Wirkung, Hilfe (`?`) und Befehlspalette.
  - **Aktionen** auf die markierten Buchungen (ohne Markierung: die Buchung mit dem Fokus): `k` Kategorie, `t` Tags,
    `s` Status, `b` bestätigen/zurücknehmen, `a`/`A` Vorschlag annehmen/ablehnen, `e` Bearbeiten, `x` Splitten,
    `d` Dublette, `g` Gegenbuchung, `m`/`M` Dokument/E-Mail anhängen, `n` neue Buchung. Dazu kommen `Bild↑`/`Bild↓`
    in der Liste.
  - **Filter** mit der Vortaste `f`: `f` Leiste, `v`/`b` Von/Bis, `z` Zweck, `e` Empfänger, `k` Kategorie bzw. Konto,
    `t` Tag, `s` Status, `r` Betrag, `u` Unterkonten, `U` Unterkategorien, `.`/`,`/`;` wie die markierte Buchung,
    `m`/`l`/`j` dieser Monat/letzter Monat/dieses Jahr (Browserdatum), `0` zurücksetzen. Esc in einem Filterfeld
    setzt den Fokus zurück in die Liste.
  - **Ansicht** mit der Vortaste `v`: `g` Gruppierung, `+`/`-` alle auf/zu, `o` Sortierspalte, `r` Richtung,
    `d`/`k` Panels, `a`/`0` Spaltenbreiten, `,` Konto-Einstellungen. Auf einem Periodenkopf klappen `←`/`→` zu bzw. auf.
- Nach einer Vortaste zeigt `kuerzel-hinweis` die möglichen zweiten Tasten. Esc bricht ab, eine unbelegte Taste wird
  gemeldet. Das Kontextmenü zeigt die Kürzel rechts an (`kuerzel` im Eintrag, mobil nicht). Die Befehlspalette führt
  die Kürzel im Kontoblatt als Einträge „Kontoblatt (…)“ hinter den übrigen Befehlen. Der Service-Worker-Cache heißt
  `kontor-huelle-26`.

## D-168 Vorbereitung des Merge von `feature/sammel`

- **Anlass:** Vor dem Merge liefen die eigenen Tests nur zu 252/281. Ursachen: Der Pflichtdialog „Wer bist du?“
  (D-155) verdeckte jede Seite der Rauchtests. Der Dialog zeigte ohne „Abbrechen“ sichtbar den Text „null“. Mobil
  machte der Namensknopf die Kopfleiste 12 px breiter als das Gerät, sodass der Browser herauszoomte. Die
  Buchungsliste wuchs mit `width: max-content` nach dem längsten Verwendungszweck auf über 2500 px und lag unter dem
  Panel der Einzelheiten. Und die Kürzel im Kontextmenü (D-167) veränderten den Text der Einträge, etwa „Gehe zur
  Gegenbuchung“ zu „Gehe zur Gegenbuchungg“.
- **Entscheidung:**
  - Der Pflichtdialog bleibt wie in D-155 und bekommt keinen Rest „null“ mehr.
  - Mobil zeigt der Namensknopf nur den Anfangsbuchstaben in einem Kreis (`data-kurz`). Der volle Name steht im
    `aria-label`.
  - Die Buchungsliste ist mindestens so breit wie ihre Mindestspalten (`min-width: min-content`) und wächst nicht
    mehr nach dem Inhalt. Eigene Spaltenbreiten (`spalten-eigen`) bleiben wie bisher.
  - Das Kürzel im Kontextmenü ist reine Darstellung (CSS `::after` aus `data-kuerzel`). Der Text des Eintrags bleibt
    unverändert.
  - Die eigenen Rauchtests wählen vorab Torsten. Ein eigener Test prüft den Dialog selbst und die Breite mobil.
  - Der Service-Worker-Cache heißt `kontor-huelle-27`.

## D-169 Dublettenvorschläge nur auf Anfrage

- **Anlass:** Seit D-165 lieferte `GET /api/dubletten` (ohne Status oder mit `status=offen`) die berechneten
  Vorschläge in derselben Liste wie die gespeicherten Verdachte. Sie haben `id: null` und `erstellt_am: null`. Das
  brach den bestehenden Vertrag der Liste, etwa für Auflösen, Filter und Idempotenz.
- **Entscheidung:** Wie bei den Serien (D-139) gibt es die Vorschläge nur auf ausdrückliche Anfrage, mit dem
  Query-Parameter `vorschlaege=ja` (`ja`/`nein`, sonst 422). Ohne den Parameter enthält die Liste nur gespeicherte
  Verdachte. Kontoblatt und Seite Dubletten fragen mit `vorschlaege=ja`. Der Service-Worker-Cache heißt
  `kontor-huelle-28`.

## D-170 Vorbereitung der Abnahme M26–M28: Korrekturen an `feature/sammel`

- **Person ohne Browser-Speicher:** Die Wahl „Torsten“/„Tina“ gilt ohne Speicher bis zum Neuladen; Bestätigen
  funktioniert (M17 1.6).
- **Leere Werte:** Nur fehlende Werte (null, undefined, false) erscheinen nicht; echte Texte wie „None GmbH“ bleiben
  unverändert (berichtigt D-168, das auch Wörter aus Daten entfernte).
- **Ausschnitt langer Listen (D-151):** Die Liste trägt `aria-rowcount` (alle Einträge einschließlich Kopf), jede
  gezeichnete Zeile `aria-rowindex` (Kopf = 1).
- **Tastaturhilfe:** „Alt+1 … Alt+7“ (Navigation hat sieben Ziele).

## D-171 Vorbereitung der Abnahme M27: Rückwärtskompatibilität der REST-Antworten

- **`verdacht`** (D-157) nur auf Anfrage mit `verdacht=ja` an `GET /api/buchungen`, `GET /api/buchungen/{id}` und
  `GET /api/suche`; Antworten schreibender Aufrufe nie. Vorher stand das Feld in jeder Buchungsantwort und änderte
  so auch unbeteiligte Buchungen. Kontoblatt, Suche und Einzelansicht fragen mit `verdacht=ja`.
- **Mail-Liste** (D-153): Vorgabe wieder aufsteigend nach Empfang; absteigend nur mit `reihenfolge=neueste` (das
  Mail-Blatt fragt so). Eine Seite hinter dem Ende liefert wieder leere Einträge statt der letzten Seite.
- **Rückgängig des Anlegens eines Tags:** Konflikt (409), wenn inzwischen ein Empfänger außerhalb der Änderung den
  Tag trägt (Bestätigung D-156).
- Service-Worker-Cache `kontor-huelle-29`.

## D-172 Abnahme M26 (Handy): Startfokus und Manifest

- Mobil liegt der Startfokus eines Dialogs nicht in einem Textfeld (D-141); ausdrücklich festgelegter Startfokus
  bleibt (M26 36.5): Befehlspalette (`befehlspalette-eingabe`) und Entsperren (`entsperren-passwort`).
- Das Web-App-Manifest antwortet wie alle statischen Dateien mit `Cache-Control: no-cache`, `ETag` und 304 bei
  passendem `If-None-Match` (M26 36.8.1).

## D-173 Abnahme M28: Alt+8 ohne Wirkung und ohne Skriptfehler

- Nach dem Wegfall von „Wiederkehrende Buchungen“ in der Navigation (D-146) löste Alt+8 einen Skriptfehler aus
  (Link nicht vorhanden). Alt+Ziffer wirkt nur noch, wenn es ein Ziel gibt; sonst geschieht nichts (M28 2).

## D-174 Abnahme M26–M28: Meldungen und mobile Suche

- **Meldungen** (unten rechts) lassen Klicks auf darunterliegende Bedienelemente durch; nur ihre eigenen Knöpfe
  fangen Klicks. Vorher verdeckte eine Erfolgsmeldung z. B. den Knopf zum Lösen eines Dokuments im (seit M28
  längeren) Panel Einzelheiten.
- **Mobile Suche:** Das verzögerte Einklappen nach dem Verlassen des leeren Felds unterbleibt, wenn der Fokus
  inzwischen wieder im Feld liegt (Wettlauf beim schnellen Öffnen über die Lupe).
- Service-Worker-Cache `kontor-huelle-30`.

## D-175 Einzelheiten: gegliederte Darstellung und lesbarer Verwendungszweck (feature/detailansicht, Entwurf)

- **Kopf:** Empfänger und Betrag (Summe der Splits auf dem angezeigten Konto, `details-betrag`) groß, darunter
  Wochentag/Datum und der Status als farbige Marke; Randfarbe nach Ein-/Ausgang, 🔒 bei gesperrten Buchungen.
  Stifte, `data-feld` und Inline-Editoren bleiben wie in 37.8 (Namen nur für Vorleser verborgen).
- **Verwendungszweck nur in der Anzeige zerlegt** (`app/zweck.js`), gespeichert bleibt der Originaltext:
  Buchungsarten als Marken („Lastschrift / Belastung“, „Kartenzahlung“ …), SEPA-Schlüssel (EREF+, MREF+,
  CRED+, SVWZ+ …) als benannte Angaben, dazu Karte (mit Kartenart), ISO-Zeitpunkt und „Ref.“. Auch an
  zusammengeklebten Zeilen („BELASTUNGCAFE“) wird getrennt; Buchungsarten links nur nach Nicht-Buchstaben,
  rechts nicht vor Kleinbuchstaben. Wird nichts erkannt, erscheint der Text unverändert; sonst ist der
  Originaltext aufklappbar.
- Buchungssätze als Karten (eigenes Konto zurückgenommen, „Unkategorisiert“ hervorgehoben), Tags als Marken,
  Verdachtshinweis mit Warnsymbol (vorher wirkungslose Hintergrundfarbe wegen `--hg-1`).
- Service-Worker-Cache `kontor-huelle-31`, neues Modul in `DATEIEN`.

## D-176 Verwendungszweck: ausgeschriebene Schlüssel, PayPal, Amazon (ergänzt D-175)

- Ausgeschriebene Schlüssel wie bei comdirect („END-TO-END-REF.:“, „MANDATSREF.:“, „GLÄUBIGER-ID:“,
  „KUNDENREFERENZ:“) gliedern wie SEPA-Schlüssel; „Ref.“ beendet den Wert davor. Ein „CORE“/„B2B“/„COR1“ direkt
  vor „ / “ ist das Lastschriftverfahren und wird eigene Angabe. Leere Werte und „NOTPROVIDED“ entfallen.
- PayPal („<Kennung>/PP.<Nr>.PP/. <Händler>, IHR EINKAUF BEI <Händler>“): Marke „PayPal“, Kennung als
  PayPal-Referenz, Text „Einkauf bei <Händler>“. Amazon-Bestellnummern (`ddd-ddddddd-ddddddd`, auch mit x
  maskiert) als Bestellnummer. Kennungen, die schon als Angabe stehen, erscheinen nicht noch einmal im Text.
- Sichtbar bleiben Karte, Zeitpunkt, Bestellnummer und Verfahren; technische Kennungen (Referenzen, Mandat,
  Gläubiger-ID, PayPal) sind unter „Referenzen (n)“ aufklappbar.

## D-177 Empfängernamen in normaler Schreibweise (nur Anzeige)

- Namen, die ganz in Groß- oder ganz in Kleinbuchstaben vorliegen („AMAZON“, „amazon“), zeigt die Oberfläche in
  normaler Schreibweise („Amazon“): erster Buchstabe je Wort groß (auch nach Bindestrich und Schrägstrich),
  kleine Wörter mitten im Namen klein („Cafe am Markt“), bekannte Abkürzungen und Rechtsformen in üblicher Form
  (GmbH, KG, e.V., Co., DB, ADAC …; Liste `NAME_FEST` in `kern.js`). Gemischt geschriebene Namen („eBay GmbH“)
  bleiben unverändert, weil sie bewusst so erfasst sind.
- Nur Anzeige (`nameAnzeige`): Buchungsliste der Kontoansicht, Kopf der Einzelheiten, Suchergebnisse und
  Einzelbuchungen der Berichte. Gespeichert, gesucht, gefiltert und in Auswahllisten/Empfängerverwaltung wird
  der Name wie erfasst; Texte vom Server (z. B. Verdachtshinweis) bleiben unverändert.
- Verwendungszweck (Frage aus D-175): bleibt beim Import unverändert; die Gliederung erfolgt nur in der Anzeige,
  damit alte und neue Buchungen für Regeln, Lernmodell und Dublettenerkennung gleich aussehen.

## D-178 Branch statt Version außerhalb von main

- **Anlass:** Auf einem Entwicklungsstand soll man sofort sehen, welcher Branch läuft, und ihn im Repository öffnen
  können.
- **Entscheidung:** `version.zweig()` liest den Branch aus `.git/HEAD` des Quellbaums. Git wird dabei nicht
  aufgerufen, Worktrees mit einer `.git`-Datei werden unterstützt. Für Releases (mit `build.json`), bei losgelöstem
  HEAD und für Namen außerhalb von `[A-Za-z0-9._/-]` liefert sie None.
- Ist der Branch nicht `main`, schreibt der Server beim Ausliefern der Hülle statt „Version x.yy“ den Link
  `zweig-link` („⎇ Branch“, auf `<Repository>/tree/<Branch>`, neues Fenster) in den Fuß der Navigation. Der Knopf
  `version-knopf` heißt dann „Über“ und öffnet weiter das About-Fenster. Dort steht zusätzlich die Zeile „Branch“
  (`ueber-zweig`). Auf main und in Releases bleibt alles wie bisher.
- `GET /api/version` bleibt unverändert, der Branch steht nur in der Hülle. Der Service-Worker-Cache heißt
  `kontor-huelle-32`.

## D-179 Automatisch angelegte Regeln aus dem Gelernten (Feature `lernmodell-transparenz`, in Arbeit)

- **Auftrag (2026-11-16):** Gelerntes wird automatisch zur sichtbaren Regel, sofern das System danach genauso gut
  kategorisiert. Messung auf dem M4-Lerndatensatz des Generators (30 Startwerte, rund 7.900 Prüfbuchungen):
  Genauigkeit 98,40 % und Abdeckung 84,94 % mit und ohne automatische Regeln; 1.373 Prüfbuchungen liefen über eine
  automatische Regel, alle richtig.
- **Auslöser:** Ein Empfänger hat in der Trainingsmenge (lernmodell.md 3) mindestens 5 Buchungen derselben
  Kategorie, diese Kategorie hat mindestens 95 % seiner Buchungen in der Trainingsmenge (nachgeschärft nach der
  Messung mit `tests/lerndaten.py`: ohne diese Bedingung entstand für eine Tankstelle mit Kraftstoff und Shop eine
  Regel „Tanken“, die das am Verwendungszweck unterscheidende Lernmodell verdeckte), und alle seine Buchungen der Trainingsmenge aus den letzten 365 Tagen (App-Uhr) haben diese Kategorie
  (mindestens eine). Keine Regel, wenn der Empfänger eine Standardkategorie hat, wenn schon eine automatische Regel
  für ihn besteht oder gesperrt ist, oder wenn eine aktive Regel seine jüngste Buchung bereits trifft.
- **Regel:** Name = Empfängername (die Liste zeigt die Kategorie dahinter), Bedingung `empfaenger gleich <Name>`, aktiv, Priorität wie beim
  Anlegen ohne Angabe (ans Ende). Vermerk in `regel_automatisch` (Objektart `regel`); die Regel trägt in API und
  Protokollform zusätzlich `automatisch: true` und `empfaenger_id` (nur bei automatischen Regeln, sonst fehlen die
  Felder). Sonst eine gewöhnliche Regel: bearbeitbar, abschaltbar, löschbar.
- **Löschen** einer automatischen Regel sperrt den Empfänger (`empfaenger_lernregel_sperre`, Objektart
  `empfaenger`, Form `lernregel_gesperrt: true` nur bei gesperrten); Rückgängig hebt die Sperre mit auf.
- **Zeitpunkt:** nach jeder Änderung mit Quelle `manuell` oder `import`, die Buchungen berührt, für die Empfänger
  dieser Buchungen (vorher und nachher), als **eigene Änderung** `quelle = "lernmodell"`, `aktion =
  "regel_automatisch"` direkt danach. Die Oberfläche legt beide Änderungen als einen Rückgängig-Schritt ab und
  meldet „Regel „…“ automatisch angelegt.“ mit Link zu den Regeln. Synchronisation, Regeln, Lernmodell und
  Rückgängig lösen nichts aus (sie erzeugen keine neuen bestätigten Zuordnungen bzw. sollen nicht zurückwirken).
- **Einstellung:** `regeln_automatisch` / `KONTOR_REGELN_AUTOMATISCH`, Vorgabe aus (bestehende Abnahmetests
  unverändert); die ausgelieferte `kontor.env` schaltet ein. Die Seite „Lernmodell“ soll den Schalter später
  übernehmen.
- **Bekannte Grenze:** Die Bedingung vergleicht den Namen. Wird der Empfänger umbenannt, greift die Regel nicht
  mehr; die Regel wird nicht nachgezogen.
- Schema: Datenbank 13, Sicherungsdatei 8 (neue Tabellen `regel_automatisch`, `empfaenger_lernregel_sperre`;
  ältere Sicherungen ohne sie). Service-Worker-Cache `kontor-huelle-31`.

## D-180 Lernmodell: Doppelzählung Empfänger/Verwendungszweck bleibt

- Geprüft wurde, Zweckwörter, die auch im Empfängernamen stehen, nicht zusätzlich als Merkmal zu zählen. Messung
  wie D-179: Genauigkeit unverändert 98,40 %, Abdeckung 84,94 % → 84,63 %. Die Sicherheit ist auf diesen Daten
  nicht überhöht (Vorhersagen mit 50–60 % stimmen zu 90 %). Das Verfahren aus lernmodell.md 4 bleibt daher
  unverändert; die Verlässlichkeit der Prozentangabe soll stattdessen auf echten Daten angezeigt werden.

## D-181 Lerndaten nach echten Kontoauszugsmustern (`tests/lerndaten.py`)

- 3000 synthetische Buchungen eines Girokontos (09/2022–10/2026) nach Mustern des Auftraggebers: Miete, Gehalt,
  Supermärkte mit Uhrzeit/Terminal/Kartennummer, PayPal mit Händler im Zweck, Amazon ohne Artikel, Tankstelle
  (Kraftstoff/Shop), Lastschriften mit Mandat, Abos, Gutschriften, Umbuchungen auf eigene Konten, drei neue
  Empfänger in der Prüfzeit, etwa 3 % falsch erfasste Kategorien. Ältere 80 % kategorisiert, neueste 20 % auf
  „Unkategorisiert“ mit bekannter Wahrheit. Alle Namen und Nummern erfunden bzw. Beispielwerte.
- Messung 2026-11-16 (574 Prüfbuchungen mit Kategorie): Lernmodell allein 89,0 % Abdeckung, 99,2 % Genauigkeit;
  mit automatischen Regeln (16 Regeln) 89,5 % Abdeckung, 99,2 % Genauigkeit. Amazon bleibt erwartungsgemäß meist
  ohne Vorschlag (3 von 47), PayPal wird über den Händler im Zweck erkannt.

## D-182 „Lernmodell anwenden“ heißt „Vorschläge für unkategorisierte Buchungen“; Einschätzung ohne Vorschlag

- Der Knopf auf der Seite Regeln (`lernmodell-anwenden`, `POST /api/lernmodell/anwenden`) heißt jetzt
  „Vorschläge für unkategorisierte Buchungen“ und erklärt im Tooltip, was geschieht: nur Buchungen auf
  „Unkategorisiert“, ab 70 % ein Vorschlag, kein Training (das Modell lernt ohnehin laufend). Die Meldung nennt das
  Ergebnis („5 von 7 unkategorisierten Buchungen haben einen Vorschlag erhalten; 2 bleiben offen“).
- „Regeln anwenden“ meldet jetzt die Zahl der Vorschläge. Vorher las die Oberfläche das nicht vorhandene Feld
  `geaendert` und zeigte nie eine Zahl.
- Einzelheiten einer unkategorisierten Buchung ohne Vorschlag zeigen „Kein Vorschlag“ mit Grund (unbekannte
  Merkmale, beste Kategorie unter der Schwelle, oder: das Modell würde vorschlagen) und die Kandidaten des
  Lernmodells ab 1 % mit „Übernehmen“ (`details-einschaetzung`, `details-einschaetzung-grund`,
  `details-einschaetzung-kandidaten`, `details-kandidat-<id>`). Lesezugriff über `POST /api/lernmodell/vorhersage`.
  Service-Worker-Cache `kontor-huelle-32`.

## D-183 Transparenz des Lernmodells: Erklärung je Buchung, Seite „Lernmodell“, Einstellungen der Instanz

- **`GET /api/buchungen/{id}/lernmodell`** (Lesezugriff): `grund` (`vorschlag`, `unter_schwelle`, `unbekannt`,
  `kein_modell`), Vorhersage wie 5.3, `beste_kategorie_id`, `vergleich_kategorie_id` (zweitbeste), je Merkmal der
  Buchung die Zählungen `anzahl` = N(f), `anzahl_kategorie`, `anzahl_vergleich`, die drei häufigsten Kategorien und
  `faktor_promille` = ⌊1000 · Faktor(beste)/Faktor(zweite)⌋ mit Faktor = (N_c(f)+1)/(N_c+2) (lernmodell.md 4), dazu
  der Grundwert N_c/n. Das Produkt aller Faktoren ist genau P(beste)/P(zweite): keine Näherung, das Verfahren
  bleibt unverändert. `aehnliche`: bis zu 5 Trainingsbuchungen mit den meisten gemeinsamen Merkmalen (Empfänger
  zählt dreifach, Betrag nicht).
- **`GET /api/lernmodell/uebersicht`** (Lesezugriff, zwischengespeichert bis zur nächsten Änderung oder
  Schwellenänderung): Güte wie lernmodell.md 6 auf den eigenen Daten (Trainingsmenge nach Datum, neueste 20 %,
  höchstens 2000, als Prüfung), Vorschläge/richtig je Schwelle 50–95 %, Verlässlichkeit je Zehntel der Sicherheit,
  je Kategorie Beispiele, Prüfung, erkannt, häufigste Verwechslungen und die fünf stärksten Merkmale.
- **`GET`/`PUT /api/lernmodell/einstellungen`**: `schwelle_promille` (500–990, Vorgabe 700) und
  `regeln_automatisch` (Vorgabe aus `KONTOR_REGELN_AUTOMATISCH`) als **Einstellung der Instanz in `meta`**, nicht im
  Änderungsprotokoll und nicht in der Sicherung – wie die Vorgabe des Betragsfilters (D-137). Abweichend vom
  Konzept (dort: Änderung im Protokoll), weil eine Schwelle kein Buchbestand ist. `GET /api/lernmodell` meldet die
  wirksame Schwelle; mit der Vorgabe 700 ist alles wie lernmodell.md.
- **Oberfläche:** Einzelheiten zeigen bei Vorschlägen des Lernmodells „Warum dieser Vorschlag?“, bei Buchungen ohne
  Vorschlag „Warum?“ (aufklappbar, `lern-warum`): Satz, Merkmale mit Balken (dafür/dagegen gegenüber der
  nächstbesten Kategorie), Verwendungszweck mit markierten Wörtern, ähnliche Buchungen (Links `/buchungen/<id>`).
  Neue Seite `/lernmodell` (Modul `lernmodell.js`), erreichbar über „Lernmodell …“ auf der Seite Regeln und den
  Link in der Erklärung. **Kein Eintrag in der Navigation**: die Navigation ist in oberflaeche.md 37.2 fest
  aufgezählt (16 Links); ein Eintrag gehört in die Meilenstein-Definition. Service-Worker-Cache `kontor-huelle-34` (nach dem Zusammenführen mit main).

## D-184 Mock-Lerndaten eingecheckt; automatische Regeln mit Toleranz im letzten Jahr

- Die 3000 Lerndaten (D-181) gehören zum Mock: Generator `kontor/mock_lerndaten.py`, eingecheckt als
  `kontor/mockdaten/lerndaten-3000.csv` (Paketdaten). `POST /api/mock/lerndaten` lädt sie im Mock-Modus in einen
  Bestand ohne Buchungen (sonst 409 `bestand_nicht_leer`; außerhalb des Mock-Modus 409 `nur_mock_modus`), als eine
  Änderung `quelle = "import"`, `aktion = "mock_lerndaten"` (rückgängig zu machen). Die Seite Import bietet im
  Mock-Modus den Knopf „Lerndaten laden (3.000 Buchungen)“.
- **Ersetzt in D-179 die Bedingung „in den letzten 365 Tagen nie anders“:** in den 365 Tagen bis zur jüngsten
  Buchung des Empfängers in der Trainingsmenge (bzw. bis heute, falls früher) ebenfalls mindestens 95 %. Das
  Fenster hängt damit an der Geschichte des Empfängers, nicht an der Uhr. Beim Laden auf einmal verhinderte sonst ein einzelner Fehlgriff (3 % der Lerndaten) die Regel für
  häufige Empfänger wie den Supermarkt, während sie beim schrittweisen Erfassen früh entstand.
## D-185 Kontor-Ausdrücke: gemeinsame Sprache für Regeln und Kontoblatt-Filter (Feature `ausdruecke`)

Grundlage: Konzept `claude/feature-regeln.md` im Projekt (iterative Phase, abgestimmt am 2026-11-16).
- **Modul `ausdruck.py`:** Lexer, Parser (Python-Ausdrücke, C-Aliase `&&`, `||`, `!`), Typprüfung zu einem
  JSON-Baum mit Verweisen als IDs, kanonischer Text (`drucken`), Auswertung, „Warum?“-Baum, Markierungen.
  Ausgewertet wird nie mit `eval`.
- **Felder** deutsch nach dem Kontoblatt, Kurzformen `empf`, `vwz`, `bet`, `dir`, `dt` (vom Auftraggeber
  bestätigt). Kanonisch wird der volle Name gedruckt. `betrag` ohne Vorzeichen, Richtung in `richtung`
  (`ausgabe`, `einnahme`, `umbuchung` = alle Splits auf Bestandskonten). Auswahlwerte ohne Umlaute
  (`"bestaetigt"`); Eingaben mit Umlaut werden angenommen.
- **Textvergleiche** wie die Volltextsuche: Groß-/Kleinschreibung egal und Umlaute angeglichen (`text.norm`).
  `case=True` unterscheidet Groß-/Kleinschreibung, `fold=False` schaltet das Angleichen der Umlaute ab. Mehrfache
  Leerzeichen werden (anders als im Konzept skizziert) nicht zusammengefasst, damit Filter und Volltextsuche
  gleich zählen.
- **Reguläre Ausdrücke** über RE2 (`google-re2`, neue Abhängigkeit): lineare Laufzeit, keine Rückverweise oder
  Lookarounds. Vorprüfung mit `re` für die Fehlerstelle; RE2 ohne Fehlerausgabe auf stderr.
- **Kontexte:** `regel` (ohne `datum`, `jahr`, `kw`, Freitext) und `filter`. Datumsangaben nach Konzept 4.6;
  `-5d` ist Kurzform für `heute - 5d` (Zeitraum bis heute). `29.2.` ohne Jahr gilt in Nichtschaltjahren als
  28.02. Bezugstag ist `SyncDienst.heute()` (Mock-Uhr), über `stichtag` übersteuerbar.
- **Freitext im Filter:** unbekannte Wörter und allein stehende Texte sind Volltextsuche (Empfänger,
  Verwendungszweck, Notiz, Tags); Nebeneinander wirkt wie `and`. Ist der Text kein Ausdruck und enthält er keine
  Operatorzeichen, wird er als Suche aller Wörter gelesen.

## D-186 Regeln mit Ausdruck: Speicherung ohne Schemaänderung

- Ein Ausdruck wird als einzige Bedingung `{"feld": "ausdruck", "operator": "ausdruck", "wert": <Baum>}` in
  der vorhandenen Spalte `regel.bedingungen` gespeichert. Damit bleiben Datenbankschema, Sicherungsdatei
  (Schemaversion 7) und Protokollform unverändert; die Sicherungsprüfung akzeptiert diese Form (`intern=True`).
- API: `POST`/`PATCH /api/regeln` nehmen `ausdruck` (Text) statt `bedingungen` an (genau eines). Antworten
  enthalten zusätzlich `ausdruck` (kanonischer Text, bei alten Regeln übersetzt) und `ausdruck_form`
  (`ausdruck` | `bedingungen`). Alte Regeln bleiben unverändert gespeichert und werten wie bisher aus; die
  Übersetzung (`bedingungen_als_baum`) ist gleichbedeutend, auch für den vorzeichenbehafteten Regelbetrag.
- Verweise auf Konten und Kategorien im Ausdruck zählen wie `konto_id`-Bedingungen: Konto nicht löschbar,
  Umleiten beim Löschen mit Buchungen und Zusammenführen ersetzt die ID, Rückgängig prüft den Bezug. Tags werden
  per ID verwiesen; ein gelöschter Tag erscheint als `"#<id>"` und trifft nie.
- Neu: `POST /api/regeln/reihenfolge` (vollständige ID-Liste → Priorität 10, 20, …; Aktion
  `regeln_reihenfolge`), `POST /api/regeln/test`, `POST /api/regeln/erklaeren` (Lesezugriffe) und
  `POST /api/regeln/{id}/anwenden` (Aktion `regeln_anwenden`, Quelle `regeln`, wie das bestehende Anwenden).
  Das Anwenden ändert nur Buchungen, bei denen die Regel gewinnt (nicht „verdeckt“).
- Aktionen bleiben vorerst bei „Kategorie vorschlagen“. „Tags hinzufügen“, „direkt bestätigen“ und „danach keine
  weiteren Regeln“ (Konzept 3) brauchen eine Schemaänderung und warten auf die Entscheidung des Auftraggebers.

## D-187 Filter in Buchungslisten

- `GET /api/buchungen` (und damit Export) nimmt `filter` (Ausdruck, Kontext `filter`) und `stichtag` an.
  Verknüpfung mit den übrigen Parametern per `and`. Ungültig → 422 `ausdruck_ungueltig` mit `details.fehler`.
- Umsetzung: Die übrigen SQL-Bedingungen liefern die Kandidaten, der Ausdruck wird in Python ausgewertet, die
  Treffer gehen als `json_each` zurück in die Abfrage (Sortierung, Seiten, Summe unverändert).
- Im Kontoblatt bezieht sich `betrag`/`richtung` auf die Splits des angezeigten Kontos (wie die Spalte Betrag),
  ohne Konto auf alle Bestandskonten (wie bei Regeln). Einträge tragen bei aktivem Filter `markierungen`.
- `GET /api/ausdruck/sprache?kontext=…` und `POST /api/ausdruck/pruefen` (mit `datumsangaben`, `freitext`,
  `zusammenfassung`, `hinweise`, `baukasten_faehig`).

## D-188 Oberfläche der Kontor-Ausdrücke

- **Neue Module** `app/ausdruck.js` (Ausdrucksfeld mit Hervorhebung als Schicht unter einem transparenten
  Textfeld, Prüfung über `POST /api/ausdruck/pruefen` nach 300 ms, Fehlerstelle unterwellt, Vervollständigung von
  Feldern, Kurzformen, Schlüsselwörtern und Datumswörtern, Markierungen) und `app/regeleditor.js` (Regelliste,
  Editor, Baukasten, Testbereich). Kein eigener Code-Editor (kein CodeMirror): die Schicht reicht und braucht
  keine Fremdbibliothek. Service-Worker-Cache `kontor-huelle-31`.
- **Kontoblatt:** Über der Liste steht das Filterfeld `filter-ausdruck` (immer sichtbar) mit Zusammenfassung
  `filter-zusammenfassung`, Zeitraum-Chips `filter-schnell-<wert>`, Leeren `filter-ausdruck-leeren` und Menü
  `filter-ausdruck-menue` („Jahr festschreiben“, „Als Regel speichern…“). Gefiltert wird nach 400 ms Tipppause oder
  Enter, nur mit gültigem Ausdruck; sonst bleibt die letzte Liste. Adresse `?filter=…`. Treffer in Empfänger und
  Verwendungszweck sind mit `<mark class="treffer">` hervorgehoben. Kürzel `f a` fokussiert das Feld.
- **Bisherige Filterleiste bleibt** unverändert (Einzelfelder, M8/M12/M17-Verträge); sie wirkt zusätzlich per
  `and`. Ein Baukasten im Filter entfällt deshalb vorerst (Konzept 5.4 offen, Frage 9).
- **Regelliste:** Reihenfolge per Ziehen oder Alt+↑/↓ am Griff (eine Änderung `regeln_reihenfolge`), Aktiv-Schalter
  je Regel, Ausdruck hervorgehoben, Duplizieren. Testkennungen `regel-anlegen`, `regel-dialog`, `regel-<id>`,
  `regeln-anwenden` bleiben.
- **Editor:** Reiter Baukasten/Ausdruck (zuletzt gewählter Reiter im Browser-Speicher, Vorgabe Ausdruck). Der
  Baukasten wird aus dem geprüften Baum erzeugt; passt ein Ausdruck nicht hinein, bleibt er als Text. Die alte
  Zeilenform („empfaenger enthaelt Bäckerei“) wird weiter angenommen und als `bedingungen` gesendet. Kategorie,
  Priorität unter „Weitere Einstellungen“ (leer = ans Ende).
- **Testbereich:** Testmenge als Filterausdruck (Vorgabe `datum in -12m`, Chips), Zählung je Wirkung als Filter,
  Treffer mit Markierung, „Warum?“ als Prüfbaum, „Nicht erfasst“, „Auf n Buchungen anwenden…“ mit Rückfrage
  (abweichende überschreiben, Vorgabe aus).

## D-189 Rückmeldungen zum Regeleditor (2026-11-16)

- Markierter Text im Ausdrucksfeld ist durchscheinend hinterlegt (vorher verdeckte die Markierungsfarbe im dunklen
  Design die Schrift der Hervorhebungsschicht).
- „Kopieren“ funktioniert auch ohne sicheren Kontext (http im Heimnetz) über ein verstecktes Textfeld. Neu ist
  „Als Testmenge übernehmen“ (`regel-in-testmenge`, im Baukasten und unter dem Ausdruck): setzt den Ausdruck als
  Testmenge, damit der Test alle passenden Buchungen zeigt.
- Testbereich mit **Quellkonto** (`regel-test-konto`, Vorgabe alle Konten): `POST /api/regeln/test` und
  `/api/regeln/{id}/anwenden` nehmen `konto_id` (nur Bestandskonten, sonst 422 `konto_ungueltig`). Ist die
  Testmenge leer (z. B. Mock-Daten älter als zwölf Monate), erscheint `test-leer` mit „Alle Buchungen testen“.
- Die Vervollständigung öffnet sich nicht mehr bei Einheiten von Zeitangaben (`-12m`).

## D-190 Testbereich ohne Bedingung, Übernahme aus Buchung und Regel (2026-11-16)

- Ohne Bedingung zeigt der Testbereich die Buchungen der Testmenge (Abfrage mit der Bedingung `True`, ohne
  Kategorie, ohne Wirkungsmarken), damit man die Daten sieht, bevor man eine Regel formuliert.
- Je Buchung „→ Bedingung“ (`test-uebernehmen-<id>`): übernimmt `empf == "<Empfänger>" and dir == "<Richtung>"`,
  ohne Empfänger das erste Wort ab vier Buchstaben aus dem Verwendungszweck (`"…" in vwz`).
- Auswahl „Bedingung einer bestehenden Regel übernehmen …“ (`regel-uebernehmen`) übernimmt Ausdruck und Kategorie
  einer anderen Regel in den Editor; der Test läuft sofort.

## D-191 Platzhalter im Ausdrucksfeld schwächer

- Der Platzhalter (Beispielausdruck) erscheint kursiv mit 40 % Deckkraft, damit er im leeren Feld nicht wie eine
  eingegebene Bedingung wirkt.

## D-192 Regelfenster ruhig und sofort aktuell

- Das Regelfenster hat eine feste Höhe (höchstens 56 rem). Links rollt der Editor, rechts nur die Trefferliste;
  Treffer verändern die Fenstergröße nicht mehr. Fehlerzeile des Ausdrucks und Statuszeile des Tests haben einen
  festen Platz (gekürzt, voller Text als Tooltip). Der Baukasten-Hinweis erscheint nicht mehr beim Tippen; der
  gesperrte Reiter erklärt sich per Tooltip. Schmale Fenster und Handy: wie bisher untereinander, rollt als Ganzes.
- Der Test lädt sofort nach jeder erfolgreichen Prüfung des Ausdrucks (vorher zusätzlich 400 ms). Ab dem ersten
  Tastendruck ist das alte Ergebnis abgeblendet (`data-veraltet="ja"`) mit „aktualisiere …“ in `test-status`. Bei
  ungültigem Ausdruck oder unvollständigem Baukasten bleibt das letzte gültige Ergebnis abgeblendet stehen.

## D-193 Ausdrucksfeld wächst mit, kompakte Trefferliste

- Ausdrucksfelder (Regel, Testmenge, Kontoblatt-Filter) passen ihre Höhe dem Inhalt an; lange Ausdrücke brechen um
  statt verdeckt zu werden. Mehrzeilige Felder wachsen bis etwa 16 Zeilen und rollen danach. Enter im einzeiligen
  Feld wendet weiterhin an.
- Treffer im Testbereich sind eine Zeile (`test-zeile-<id>`: Datum, Empfänger bzw. Verwendungszweck gekürzt, Betrag,
  Wirkung; auf dem Handy ohne Wirkung). Ein Klick klappt die Einzelheiten auf: Verwendungszweck, Kategorie
  vorher → nachher, „→ Bedingung“ und „Warum?“.

## D-194 Kontoblatt-Filter wie bei den Regeln: Ausdruck oder Baukasten (ersetzt die Einzelfelder)

- Die Filterleiste (`filter-leiste`, Umschalter `filter-umschalten`) enthält statt der Einzelfelder (Von, Bis,
  Betrag, Empfänger, Verwendungszweck, Freitext, Kategorie, Tag, Status) den **Baukasten** (`filter-baukasten`,
  Zeilen `bk-<n>-feld/op/wert`) wie im Regeleditor, zusätzlich mit „Freitext“ und „Datum“ (liegt in, nicht in, ab,
  bis, nach, vor; Wert in der Schreibweise von 4.6, z. B. `-30d`, `2017`, `1.1. .. 31.3.`). Leere Zeilen zählen
  nicht. Baukasten und Ausdrucksfeld darüber sind gekoppelt: Änderungen im Baukasten schreiben den Ausdruck, ein
  getippter Ausdruck baut den Baukasten neu (passt er nicht hinein, erscheint `filter-baukasten-hinweis`).
- Bleiben: „mit Unterkategorien“, „mit Unterkonten“, „Filter zurücksetzen“, die Zeitraum-Chips am Ausdrucksfeld.
  Die Zahl am Umschalter zählt die Teile des Ausdrucks plus übrige Parameter.
- **Alte Adressen und Kontextmenüs:** `von`, `bis`, `empfaenger_id`, `ohne_empfaenger`, `verwendungszweck`,
  `zweck_gleich`, `zweck_leer`, `suche`, `kategorie_id` (ohne Unterkategorien), `tag_id` und `status` werden beim
  Öffnen in den Ausdruck übernommen. „gleicher Empfänger“ und „gleicher Verwendungszweck“ setzen
  `empf == "…"` bzw. `vwz == "…"`. Ohne Entsprechung im Ausdruck bleiben `betrag_min`/`betrag_max` (vorzeichen-
  behaftet), `zweck_aehnlich`, `empfaenger_aehnlich` und `kategorie_id` mit Unterkategorien; sie erscheinen als
  Chips „Weitere Filter“ mit ×.
- **Tastenkürzel:** `f f` Baukasten ein/aus (Fokus auf die erste Zeile), `f a` Ausdruck, Zeiträume `f h` heute,
  `f w` 7 Tage, `f d` 30 Tage, `f m` dieser Monat, `f l` letzter Monat, `f j` dieses Jahr, `f J` letztes Jahr,
  `f x` Zeitraum entfernen. Die Kürzel für die Einzelfelder (`f v/b/z/e/k/t/s/r`) entfallen.
- Auswirkung auf Abnahmetests: Tests, die die Einzelfelder der Filterleiste bedienen (M8, M12, M17 u. a.), passen
  nicht mehr; das gehört in die Meilenstein-Definition dieses Features.

## D-195 Filter-Baukasten ein- und ausklappbar am Ausdrucksfeld

- Neben dem Filterausdruck steht der Umschalter `filter-baukasten-umschalten` („Baukasten ▸/▾“, `aria-expanded`,
  `aria-controls="filter-leiste"`); er wirkt wie `filter-umschalten` und `f f`. Der Baukasten startet in jeder
  Kontoansicht eingeklappt (wie E-172) und klappt nicht mehr von selbst auf, auch nicht bei „ähnlicher Empfänger/
  Verwendungszweck“ aus dem Kontextmenü.
- Die Zusammenfassung unter dem Ausdruck nennt auch die übrigen Filter („Weitere Filter“, D-194), damit ein
  eingeklappter Baukasten nichts verbirgt.

## D-196 Ein einziger Umschalter für den Filter

- Der Knopf `filter-umschalten` („Filter“) im Seitenkopf der Kontoansicht entfällt (Auftraggeber, 2026-11-16).
  Einziger Umschalter ist `filter-baukasten-umschalten` am Ausdrucksfeld; er trägt jetzt die Zahl aktiver Filter
  (`filter-anzahl`, `data-anzahl`) und den Pfeil ▸/▾. `f f` wirkt wie bisher.
- Abnahmetests mit `filter-umschalten` (u. a. M12 23, M17, UXMobile 3.6) passen nicht mehr; sie gehören in die
  Meilenstein-Definition dieses Features.

## D-197 Umsatzabruf über camt in der Version, die die Bank anbietet (ergänzt D-069)

- **Frage:** D-069 verlangt genau camt.052.001.08 und weicht sonst auf MT940 (`HKKAZ`) aus. Banken wie die
  comdirect bieten camt.052.001.02 an; `HKKAZ` ist dort gestört und abgekündigt.
- **Entscheidung:** Bietet die Bank `HKCAZ` an, wird immer camt abgerufen: zuerst .08, sonst die höchste
  angebotene Version von .07 bis .02. Bietet sie nur unlesbare camt-Formate an, scheitert der Abruf mit
  `BankFehler`; auf MT940 wird dann nie ausgewichen. MT940 bleibt nur für Banken ganz ohne `HKCAZ`. Die
  Kontoverbindung im Auftrag trägt nur IBAN und BIC. Der Leser der Einträge ist für alle Versionen derselbe
  (`Sts` als Text oder `Sts/Cd`, Partei mit oder ohne `Pty`).
- **Begründung:** Auftrag vom 2026-11-19 (Totalausfall mit AqBanking bei der comdirect).

## D-198 TAN schon beim Dialogbeginn (ersetzt D-071)

- **Entscheidung:** Antwortet die Bank auf die Dialoginitialisierung mit 0030, werfen `konten()` und `umsaetze()`
  `TanErforderlich`; der Dialog bleibt in der Plugin-Instanz offen. `konten(tan=…)` bzw. `umsaetze(…, tan=…)`
  senden die TAN (HKTAN Prozess 2) und setzen im selben Dialog fort. In der Synchronisation läuft das über die
  vorhandene TAN-Anforderung des ersten Kontos. Ohne gespeicherte Kontenauswahl scheitert ein Lauf, dessen
  Kontenabruf eine TAN braucht, weiter nach D-023 – mit dem Hinweis, die Konten einmal in den Einstellungen
  abzurufen. Entkoppelte Freigaben (3955) bleiben ein `BankFehler` (D-070).
- **Offen:** Verlangt eine Bank die TAN bei jedem Dialog, braucht ein Lauf je Konto eine TAN, weil jeder Aufruf
  einen eigenen Dialog führt (D-069). Erst nach einem Abruf bei der echten Bank zu beurteilen.

## D-199 Bankzugang aus der Oberfläche

- **Entscheidung:** Server-Adresse, Bankleitzahl, Benutzerkennung, Kunden-ID, Produkt-ID, TAN-Verfahren und die
  abgerufenen Konten mit Auswahl liegen in `meta` (Betriebszustand, wie D-137: kein Protokoll, keine Sicherung).
  Die PIN gehört nie dazu; sie bleibt im Arbeitsspeicher bzw. – nur auf Wunsch – verschlüsselt gemerkt (D-129,
  am 2026-11-19 so bestätigt). `KONTOR_FINTS_*` ist Vorbelegung je Feld. Endpunkte: `GET/PUT /api/bank/zugang`,
  `POST /api/bank/zugang/tan-verfahren`, `POST /api/bank/zugang/konten/abrufen` (mit `vorgang` und `tan` zum
  Fortsetzen), `PUT /api/bank/zugang/konten`. Sind Konten gespeichert, synchronisiert ein Lauf genau die
  gewählten und fragt die Kontenliste nicht mehr bei der Bank ab. Ändern sich Adresse, Bankleitzahl, Benutzer
  oder Kunden-ID, entfallen die gespeicherten Konten. Alle Aufrufe mit Bankverbindung halten die Laufsperre;
  während eine Synchronisation auf eine TAN wartet, sind sie mit 409 `tan_offen` gesperrt. Neue öffentliche
  Plugin-Methode `FintsBankPlugin.tan_verfahren()`. Ein Zugang je Instanz.
- **Begründung:** Auftrag vom 2026-11-19; der offene Dialog bleibt bewusst im Arbeitsspeicher (ein Prozess),
  statt Dialogdaten zu serialisieren.

## D-200 Übergang alter Bank-Kennungen

- **Frage:** Dieselben Umsätze kommen nach der Umstellung mit anderer Kennung; der Abgleich (4.4) schließt
  Buchungen mit Bank-Kennung als Kandidaten aus und würde den Überlappungszeitraum doppelt buchen.
- **Entscheidung:** Beim ersten Start mit dieser Fassung werden alle vorhandenen `bank:`-Kennungen in
  `sync_kennung_alt` vermerkt (`meta.bank_uebergang`). Ein unbekannter Umsatz wird einer Buchung zugeordnet,
  die auf demselben Konto denselben Betrag und Buchungstag hat, nur alte Kennungen trägt und deren Kennung die
  Bank in diesem Abruf nicht wieder geliefert hat. Je Betrag und Tag so viele Zuordnungen wie solche Buchungen,
  bei Auswahl zuerst nach Empfängername; der Rest wird neu gebucht. Zählt als `buchungen_zusammengefuehrt`.
  Die Tabelle ist Betriebszustand (nicht gesichert): Nach dem Einspielen einer älteren Sicherung greift die
  Regel für deren Buchungen nicht.
- **Begründung:** Zählen statt Raten: Bei gleichem Betrag am selben Tag stimmt danach die Anzahl in jedem Fall;
  ein Dublettenverdacht wäre hier nur Mehrarbeit.

## D-201 AqBanking-Plugin entfernt (hebt D-099 und die M10-Teile auf)

- **Entscheidung:** `plugins/aqbanking.py`, die Felder `aqbanking_*`, die Fehlerklasse
  `BankTanNichtUnterstuetzt` und die eigenen M10-Tests entfallen. `KontorConfig(bank_plugin="aqbanking")` ist
  ein Konfigurationsfehler; nur beim Lesen der Umgebung gilt `KONTOR_BANK_PLUGIN=aqbanking` als `fints` (mit
  Warnung im Log), damit eine vorhandene Umgebungsdatei den Dienst nicht am Start hindert.
- **Folge für die Abnahme:** Die Tests von M10 und die M6-/M11-Tests zu camt.052.001.08-Zwang, TAN beim
  Dialogbeginn, AqBanking-Saldo und den öffentlichen Plugin-Methoden passen nicht mehr; das klärt der
  Test-Thread mit der Meilenstein-Definition dieses Features.

## D-202 Kontenliste aus der SEPA-Kontoverbindung, Benutzerparameter nur ergänzend (ergänzt fints.md 3.2)

- **Frage:** Bisher zählte nur ein HIUPD-Eintrag mit IBAN, Währung EUR und bekannter Kontoart. Beim ersten Abruf
  gegen die comdirect (2026-11-19) kamen so 0 Konten, obwohl die Bank SEPA-Konten meldet.
- **Entscheidung:** Grundlage ist jedes Konto aus HISPA mit IBAN. Der passende HIUPD-Eintrag wird über die IBAN,
  ersatzweise über die Kontonummer gesucht und liefert Name, Inhaber und Kontoart. Fehlt er oder fehlt die
  Kontoart, gilt `girokonto`. Ausgeschlossen bleibt ein Konto nur, wenn HIUPD ausdrücklich eine andere Währung
  als EUR oder eine Kontoart außerhalb der Tabelle (Depot usw., K 15) nennt.
- **Begründung:** Was in den Benutzerparametern steht, ist je Bank verschieden; die SEPA-Kontoverbindung ist das,
  womit der Umsatzabruf arbeitet. Für Banken mit vollständigem HIUPD ändert sich nichts (M6-Tests unverändert grün).

## D-203 Diagnoseprotokoll des FinTS-Plugins ohne persönliche Daten

- **Frage:** Für die Fehlersuche gegen eine echte Bank braucht es Einblick in den Austausch; fints.md 3.8 verbietet
  zu Recht jedes Protokoll der Nachrichten (PIN, TAN, Kennungen).
- **Entscheidung:** Ein abschaltbares Diagnoseprotokoll (Vorgabe aus; Einstellungen → Bankzugang, gespeichert als
  Betriebszustand `meta.bank_diagnose`). Es arbeitet mit einer Positivliste (`plugins/fints_diagnose.py`): je
  Nachricht die Segmentarten und -versionen, Rückmeldecodes mit bereinigtem Text, angebotene Formate und
  TAN-Verfahren, je Konto nur „Konto n“ mit Kontoart, Währung und der Angabe, welche Felder gefüllt sind,
  Längen und Anzahlen, HTTP-Status und Dauer, dazu die Entscheidungen des Plugins (Konto übernommen/ausgelassen
  mit Grund, gewähltes Format, TAN nötig, Ausgang jedes Aufrufs). Nie enthalten: PIN, TAN, Auftragsreferenz,
  Benutzerkennung, Kunden-ID, Kundensystem-ID, Produkt-ID, IBAN, Kontonummer, Inhaber, Kontobezeichnung, Beträge,
  Umsätze, Wortlaut der TAN-Anforderung, Server-Adresse. Freitexte der Bank: bekannte Kennungen, IBANs und
  Ziffernfolgen ab fünf Stellen werden ersetzt, höchstens 160 Zeichen; Parameter von Rückmeldungen nur als Anzahl
  (Ausnahme 3920: dreistellige Verfahrensnummern). Ablage: Ringpuffer mit 600 Zeilen im Arbeitsspeicher
  (`GET/PUT /api/bank/zugang/diagnose`) und, solange eingeschaltet, im Log des Dienstes (Logger
  `kontor.fints.diagnose`, Stufe INFO). Der Logger `fints` der Bibliothek bleibt stillgelegt.

## D-204 camt-Datum mit Zeitzone oder Zeitanteil

- **Anlass:** Erster Abruf gegen die comdirect (2026-11-19): Kontenliste und `HKCAZ` mit camt.052.001.02 liefen,
  die Umsatzdaten waren aber „unlesbar“ (`ValueError`), sobald Einträge enthalten waren.
- **Entscheidung:** Buchungs- und Wertstellungsdatum werden aus `Dt` oder `DtTm` gelesen; ausgewertet werden nur
  Jahr, Monat und Tag am Anfang (`2024-06-03+02:00`, `2024-06-03T10:11:12+02:00`). Beträge müssen die Form
  `Ziffern[.Ziffern]` haben. Hat ein Feld eine andere Form, scheitert der Abruf weiter als Ganzes (kein
  stilles Auslassen einzelner Umsätze); das Diagnoseprotokoll nennt dann Feld und Form (`9999-99-99`), nie den
  Wert. Außerdem nennt es, warum ein Saldo nicht abgefragt wurde.
- **Hinweis:** Dass die Zeitzone die Ursache war, ist aus dem Protokoll geschlossen (nur `ValueError` sichtbar),
  nicht an den Daten der Bank gesehen.

## D-205 Testinstanz für Entwicklungsbranches statt Branch-Wechsel im Update-Dienst

- **Anlass:** Ein Entwicklungsbranch soll sich mit den echten Daten ausprobieren lassen. Der Update-Dienst (D-107)
  installiert nur Releases mit Prüfsumme, und ein Branch kann das Schema migrieren; ein Zurück auf main gäbe es nur
  über Sicherung und Wiederherstellung. Mit dem Auftraggeber abgestimmt (2026-11-19): kein Branch-Wechsel im
  Update-Dienst, sondern eine zweite, getrennte Instanz. M14 und der About-Dialog bleiben unverändert.
- **Entscheidung:** Ausgeliefert werden `kontor-test.service` und `kontor-test.env` sowie die Kommandozeile
  `python -m kontor.testinstanz` (`einrichten <Branch>`, `stoppen [--loeschen]`, als root mit dem Python der
  Hauptinstanz). Programm unter `/opt/kontor-test` (Quellbaum `src`, eigene virtuelle Umgebung `venv`), Daten unter
  `/var/lib/kontor-test`, Port 8081.
- **Mock-Modus:** Die Testinstanz läuft mit `KONTOR_MOCK_MODUS=1`; ihre Mock-Datenbank ist die Datenkopie. Damit
  sind Bank-, Mail- und Benachrichtigungs-Plugin Attrappen, die Update-Suche entfällt, und die Oberfläche zeigt den
  Hinweisbalken. Zeitgesteuerter Abruf und Mail-Abruf sind zusätzlich abgeschaltet. Folge: Ein Branch, der am
  echten Bankabruf arbeitet, lässt sich so nicht gegen die Bank prüfen – das ist gewollt.
- **Datenkopie:** Online-Sicherung von SQLite aus der laufenden Hauptdatenbank (nur lesend geöffnet, Pfad aus
  `KONTOR_DATENBANK` in `/etc/kontor/kontor.env`). Vor der Übergabe werden `geheimnis`, `geheimnis_huelle`,
  `tan_anforderung` geleert und `meta.bank_fints_…` sowie `meta.bank_diagnose` entfernt; danach `VACUUM`, damit die
  Chiffretexte auch nicht in freien Seiten bleiben. Die Kopie ersetzt eine frühere erst, wenn sie fertig ist.
- **Anmeldung:** Haushaltspasswort und Sitzungen bleiben in der Kopie (nur Hashes). Das Sitzungs-Cookie gilt je
  Rechnername, nicht je Port; mit übernommenen Sitzungen ist man in beiden Instanzen angemeldet, statt sich
  gegenseitig abzumelden.
- **Installation des Branches:** `git clone --depth 1 --branch` in ein neues Verzeichnis, dann editierbar
  installieren. Nur so findet `version.zweig()` (D-178) `.git/HEAD` und zeigt den Branch statt der Version. Ein
  Git-Archiv oder Wheel hätte keinen Branchnamen. Schlägt das Klonen fehl (Branch unbekannt, kein Netz), bleibt
  eine laufende Testinstanz unberührt. Branchnamen werden streng geprüft (kein führendes `-`, kein `..`).
- **Benutzer:** dasselbe Systemkonto `kontor`, kein zweites. Die Trennung leistet die Unit:
  `StateDirectory=kontor-test`, `ProtectSystem=strict` und `InaccessiblePaths` für `/var/lib/kontor` und
  `/etc/kontor/kontor.env`; keine `LoadCredentialEncrypted`-Zeile, gleiche Härtung wie `kontor.service`.
- **Betrieb:** Kein `[Install]`-Abschnitt (startet nicht beim Hochfahren), keine Sicherungs-Unit, kein
  Update-Verzeichnis. Die Unit wird bei jedem Einrichten erneuert, die Umgebungsdatei nur angelegt.
- **Nicht im Umfang:** Rückweg von Änderungen aus der Testinstanz in die Hauptinstanz; Auswahl in der Oberfläche.
- **Prüfung:** `tests/test_testinstanz_eigen.py` (Kopie, Bereinigung, Ablauf mit untergeschobenen Befehlen, Unit,
  Umgebungsdatei, Start im Mock-Modus auf der Kopie). Der Betrieb unter systemd ist hier nicht prüfbar.

## D-206 Monatsbericht: Ausgaben eines Monats rein statistisch (Feature `monatsbericht`)

- **Anlass:** Auftrag vom 2026-11-19: ein Bericht, der ohne Kategorien eine bessere Übersicht über die Ausgaben
  eines Monats gibt; Tabellen und Grafiken ansprechend und interaktiv.
- **Entscheidung:** Neuer lesender Endpunkt `GET /api/berichte/monat` (`monat=JJJJ-MM`, Vorgabe der laufende
  Monat der App-Uhr; `konto_id` mehrfach, nur Bestandskonten, Vorgabe alle Bestandskonten ohne Darlehenskonten)
  und die Seite `/berichte/monat`. Kein Zustand, kein Protokoll, nichts in der Sicherung. Noch nicht im
  OpenAPI-Vertrag; das folgt mit der Meilenstein-Definition.
- **Was eine Ausgabe ist:** Die Wirkung einer Buchung ist die negierte Summe ihrer Splits auf Konten, die keine
  Bestandskonten sind. Wirkung 0 ist eine Umbuchung zwischen eigenen Konten und zählt nicht (die Anzahl wird
  genannt); von einer Kreditrate zählt so nur der Zinsanteil. Negative Wirkung ist eine Ausgabe, positive eine
  Einnahme. Ein Eingang, der nur gegen Aufwandskonten gebucht ist, gilt als Erstattung und mindert die Ausgaben
  (wie im Bericht Einnahmen und Ausgaben). Das ist die einzige Stelle, an der die Kontoart der Gegenseite
  eingeht; eine nicht kategorisierte Erstattung zählt als Einnahme.
- **Fest und variabel:** Fest sind Ausgaben, die zu einer Serie der Erkennung wiederkehrender Buchungen gehören
  (`wiederkehrend.serie` zum Stichtag, mit den Betragsfiltern). Alles andere ist variabel.
- **Laufender Monat:** Stichtag ist heute. Vergleiche in der Kachel „Ausgaben“ beziehen sich dann auf den Stand
  des Vormonats und des Schnitts am selben Tag, nicht auf deren Monatssumme. Hochrechnung = bisherige Ausgaben
  + noch fällige feste Zahlungen aktiver Serien + variabler Tagesschnitt der 90 Tage vor Monatsbeginn mal
  Resttage (ohne Vorgeschichte der Tagesschnitt des laufenden Monats).
- **Vergleiche:** Verlaufsschnitt über die letzten sechs Monate mit Daten; Monatsvergleich über zwölf Monate;
  „üblich“ je Empfänger ist der Monatsschnitt der letzten sechs Monate mit Daten. Ausreißer: Ausgabe außerhalb
  einer Serie, robustes z ≥ 3,5 gegenüber mindestens vier früheren Ausgaben an denselben Empfänger in zwölf
  Monaten und mindestens 5 € über deren Median. Neue Empfänger: keine Buchung in den zwölf Monaten davor.
  Größenklassen fest: unter 10 €, 10–50 €, 50–200 €, 200–1 000 €, ab 1 000 €.
- **Oberfläche:** Kein neuer Eintrag in der Navigation (die Abnahmetests zählen deren Einträge auf); erreichbar
  über den Knopf „Monatsbericht“ auf der Seite Berichte und die Befehlspalette. Monat und Konten stehen in der
  Adresse (`?monat=`, `?konto=`), der Tab merkt sie sich. Diagramme mit dem vorhandenen Plotly-Paket; Kalender,
  Balken und Anteile sind HTML, damit sie ohne Plotly und mit Tastatur bedienbar bleiben.

## D-207 Einstellungen in Bereichen mit Suche (Feature `einstellungen`, in Arbeit)

- **Anlass:** Die Einstellungen waren eine lange Seite mit elf Abschnitten; einzelne Einstellungen waren schwer zu
  finden, Seltenes (Diagnoseprotokoll, Produkt-ID, OAuth-Client-Secret) stand gleichrangig neben Alltäglichem.
- **Entscheidung:**
  - Sechs Bereiche: Allgemein (Design, Layout, Angaben zur Instanz), Bank (Bankzugang, PIN), Mail (Postfächer,
    Abruf), Benachrichtigungen (Zustellung, Test, ntfy-Token), Sicherheit (Anmeldung, Schutz der Geheimnisse),
    Daten und Sicherung (Datensicherung, Tags). Der Abschnitt „Geheimnisse“ entfällt: Jedes Geheimnis steht bei
    seiner Aufgabe (ntfy-Token bei den Benachrichtigungen, OAuth-Client-Secret bei Mail).
  - Navigation: am Desktop eine Spalte links neben dem Inhalt, am Handy eine Liste, die in den Bereich führt
    (Rückweg „Alle Einstellungen“). Reiter scheiden aus (zu eng am Handy, wachsen schlecht). Gezeigt wird immer
    genau ein Bereich; ohne Angabe am Desktop „Allgemein“, am Handy nur die Liste.
  - Adresse: `/einstellungen?bereich=<name>`. Der Bereich steht im Abfrageteil und nicht im Pfad, damit die
    Einstellungen ein einziger Tab bleiben (Tabs hängen am Pfad, D-119). Unbekannter Wert wie ohne Angabe. Der
    Wechsel des Bereichs lädt nichts nach (alle Bereiche werden einmal aufgebaut, die übrigen sind `hidden`).
  - Stand je Bereich in der Navigation (`einstellungen-status-<name>`, `data-zustand` = `ok`/`offen`/`fehler`/
    `neutral`), z. B. „Bankzugang unvollständig“, „Zugang vollständig · 2 von 3 Konten ausgewählt · PIN fehlt“.
    Die Bedeutung steht im Text; der farbige Punkt ist nur Beigabe.
  - Suche über den Bereichen (`einstellungen-suche`): filtert beim Tippen ein festes Verzeichnis der Einstellungen
    mit Synonymen („backup“ → Sicherung, „dunkelmodus“ → Design), Umlaute gefaltet wie in der Befehlspalette. Ein
    Treffer führt in den Bereich, klappt „Erweitert“ auf, rollt hin, hebt kurz hervor und setzt den Fokus. Einträge,
    die es in dieser Instanz nicht gibt (Bankzugang im Mock-Modus), erscheinen nicht.
  - „Erweitert“ (`<details>`, eingeklappt, nennt im Titel seinen Inhalt): Kunden-ID und Produkt-ID, Diagnoseprotokoll,
    OAuth-Client-Secret. Offen von Anfang an, wenn darin etwas fehlt oder läuft (Pflichtfeld Produkt-ID leer,
    Diagnose eingeschaltet). Was aufgeklappt wurde, bleibt über das Neuladen nach einer Aktion offen (nur im
    Arbeitsspeicher des Fensters).
  - Bankzugang in vier Schritten (Zugangsdaten, Bank-PIN, TAN-Verfahren, Konten), jeder Knopf bei seinem Schritt,
    die Meldung erscheint im Schritt der Aktion. Stand der PIN und „PIN verwerfen“ stehen im Schritt 2 (bisher
    eigener Abschnitt); im Mock-Modus bleiben sie eine eigene Karte.
  - Alle bisherigen `data-testid` bleiben unverändert; neu sind nur `einstellungen-…`, `passwort-alt`/`-neu`/
    `-aendern`, `postfach-neu-adresse`/`-anlegen`, `mail-abrufen`. Keine Änderung an Endpunkten oder Datenmodell.
  - Keine Einträge je Bereich in der Befehlspalette: Zwei Abnahmetests (M8, M28) prüfen deren Trefferlisten.
- **Folge für die Abnahme:** Sieben Browsertests öffnen `/einstellungen` und bedienen Elemente, die jetzt in einem
  anderen Bereich liegen (im Dokument vorhanden, aber nicht sichtbar): M8 `test_einstellungen_geheimnis_und_sicherung`,
  `test_einstellungen_test_benachrichtigung_mock`/`_ntfy`, `test_pin_dialog`, `test_schreiben_mit_csrf_und_abmelden`;
  M23 `test_einstellungen_schutz`; M28 `test_abmelden_vergisst_person`. Sie brauchen nur den Bereich in der Adresse.
  Das klärt der Test-Thread mit der Meilenstein-Definition. Die übrigen Browsertests verhalten sich wie auf main
  (dort schlagen 49 unabhängig von diesem Feature fehl).

## D-208 Mails über die Amazon-Bestellnummer an die Buchung, erwartete Zahlungen vorerst aus (Feature `amazon-bestellnummer`)

- **Auftrag (2026-11-19):** Die erwarteten Zahlungen (D-128) sind dem Auftraggeber noch zu fehleranfällig und
  werden vorerst abgeschaltet. Stattdessen: Trägt eine Buchung eine Amazon-Bestellnummer, hängen alle Mails mit
  dieser Nummer im Betreff oder Text an dieser Buchung.
- **Erwartete Zahlungen:** Der Code bleibt unverändert hinter `mail_abgleich`. Die ausgelieferten
  Umgebungsdateien (`kontor.env`, `kontor-test.env`) setzen `KONTOR_MAIL_ABGLEICH=0`. Vorhandene erwartete
  Zahlungen und ihre Zuordnungen bleiben in der Datenbank, es entstehen keine neuen und keine Meldungen
  „überfällig“. Eine schon installierte `/etc/kontor/kontor.env` ändert sich durch ein Update nicht; dort muss
  die Zeile von Hand umgestellt werden.
- **Neue Einstellung** `mail_bestellnummer` (`KONTOR_MAIL_BESTELLNUMMER`, Wahrheitswert wie die anderen Schalter,
  Vorgabe aus, ausgeliefert an). Vorgabe aus, damit bestehende Abläufe und Abnahmetests unverändert bleiben.
- **Regel:** Bestellnummer = `ddd-ddddddd-ddddddd` ohne angrenzende Ziffer. Gesucht wird in Verwendungszweck und
  Empfängername jeder Buchung (zusätzlich ohne Leerraum, weil Bankzeilen die Nummer umbrechen) und in Betreff und
  Text jeder gespiegelten Mail, unabhängig vom Absender. Je Treffer hängt die ganze Mail und jeder PDF-Anhang als
  Dokument (Quelle `mail`) an der Buchung. Beträge, Datum und Anbietername spielen keine Rolle. Mehrere Buchungen
  mit derselben Nummer (Teillieferungen) bekommen alle dieselben Mails; dieselbe Mail in zwei Postfächern zählt
  einmal. Hängt ein Dokument gleichen Inhalts schon an der Buchung, entsteht kein zweites.
- **Wann:** nach jedem Mail-Abruf und nach jedem Synchronisationslauf mit Endstatus, nach den erwarteten
  Zahlungen. Eine Änderung im Protokoll (Quelle `mail`, Aktion `bestellmail_anhaengen`) entsteht nur, wenn etwas
  angehängt wurde; sie lässt sich rückgängig machen.
- **Gemerkt wird** je (Buchung, Nachrichten-ID), dass die Mail behandelt ist (Tabelle `bestellmail`,
  Betriebszustand: nicht protokolliert, nicht in der Sicherung). Löst der Anwender ein so angehängtes Dokument
  oder macht er die Änderung rückgängig, kommt die Mail nicht von selbst wieder. Nach dem Einspielen einer
  Sicherung wird das Gemerkte geleert und neu geprüft.
- **Mail-Liste:** Mit `mail_bestellnummer` trägt jeder Eintrag von `GET /api/mail/nachrichten` das Feld
  `angehaengt` (Buchungen mit `id`, `datum`, `konto_id`, `empfaenger`, `verwendungszweck`, `nummer`, `warum`);
  solche Mails zählen in `stand` und im Filter als `zugeordnet`. Ohne die Einstellung fehlt das Feld (Vertrag
  `openapi.yaml` unverändert). Die Seite `/mail` zeigt die Buchung mit der Marke „Bestellnummer“.
- **Abnahmetests:** `tests/app/m20/test_m20_erkennung.py::test_ausgelieferte_umgebungsdatei` erwartet
  `KONTOR_MAIL_ABGLEICH=1` und ist damit bewusst rot, bis die Meilenstein-Definition dieses Features übernommen
  ist. Alle übrigen Tests von M6, M9, M18, M20, M24 und M27 verhalten sich wie auf main.

## D-209 Bestellnummer auch im Quelltext der Mail suchen (ergänzt D-208)

- **Anlass:** Eine Buchung mit Amazon-Bestellnummer bekam keine Mails, obwohl das Postfach sieben Mails mit der
  Nummer enthält (Bestellt, Versendet, In Zustellung, Zugestellt).
- **Vermutete Ursache (an echten Mails nicht prüfbar):** Der gespiegelte Text einer Mail ist nur ihr erster
  Klartextteil (mail.md 3.3). Steht die Nummer nur im HTML-Teil oder in der Adresse eines Verweises, fand D-208 sie
  nicht.
- **Entscheidung:** Zusätzlich zu Betreff und gespiegeltem Text werden alle Textteile der Rohfassung im Quelltext
  durchsucht (Klartext und HTML samt Verweisadressen). Jede Mail wird einmal durchsucht; die gefundenen Nummern
  stehen in `bestellmail_nummer` (Betriebszustand). Mails ohne Rohfassung (Mock, zu große Mails) zählen wie
  bisher nur mit Betreff und Text.
- Jeder Lauf schreibt eine Zeile ins Log (`kontor.bestellmail`, Stufe INFO) mit der Zahl der angehängten Mails.

## D-210 Datum der E-Mail in den Einzelheiten (Feature `mail-datum`)

- **Auftrag (2026-11-19):** Im Abschnitt „Dokumente“ der Einzelheiten soll bei angehängten E-Mails das Datum der
  Mail stehen.
- **Entscheidung:** Neben jeder angehängten E-Mail steht ihr Datum (`dokument-datum-<id>`, Tag.Monat.Jahr in
  Ortszeit, voller Zeitpunkt im Tooltip und in `data-zeitpunkt`), vor der Größe. Andere Dokumente bekommen kein
  Datum. Mails ohne lesbares Datum zeigen nichts.
- **Quelle:** das Feld `datum` der vorhandenen Mail-Ansicht `GET /api/dokumente/{id}/mail` (Kopfzeile `Date`),
  je Dokument einmal gelesen und für die Sitzung gemerkt. Kein neues Feld in `belege` oder im Dokument, damit der
  Vertrag `openapi.yaml` unverändert bleibt.

## D-211 Gruppierung nach Datum: vier feste Abschnitte je Monat (Feature `kontoblatt-gruppierung`)

- **Anlass:** Zwischen Monat und Tag fehlte eine Ebene; ein Monat mit vielen Buchungen zerfiel sofort in bis zu
  31 Tagesbalken. Kalenderwochen scheiden aus, weil sie am Monatswechsel geteilt werden müssten.
- **Entscheidung** (mit dem Auftraggeber am 2026-11-19 abgestimmt): „nach Datum“ zeigt Jahr → Monat → Abschnitt →
  Tag (ergänzt D-152). Jeder Monat hat vier feste Abschnitte: 1.–7., 8.–14., 15.–21. und 22. bis Monatsende
  (7 bis 10 Tage). Die Grenzen sind in jedem Monat gleich, damit feste Zahlungen (Miete, Gehalt) immer im selben
  Abschnitt stehen und die Abschnitte zusammen genau den Monat ergeben.
  - Beschriftung ist nur der Datumsbereich mit dem tatsächlichen Monatsende („08.–14.11.“, „22.–29.02.“), kein
    Wort wie „Woche“. Kalenderwochen bleiben als Filter (`kw46`) erhalten, nicht als Gruppierung.
  - Schlüssel des Abschnitts: `JJJJ-MM-a1` … `-a4` (`data-periode`, `periode-…`, `periode-summe-…` usw. wie bei den
    anderen Ebenen), `data-ebene="abschnitt"`. Abschnitte ohne Buchung erscheinen nicht.
  - Balken, Zahlen, Klappen, Pfeiltasten und „Alles zusammenklappen/aufklappen“ wie bei den übrigen Ebenen. Keine
    Änderung an Endpunkten, Adresse (`?gruppierung=datum`) oder Datenmodell.
  - Der Service-Worker-Cache heißt jetzt `kontor-huelle-39`.
- **Folge für die Abnahme:** Abnahmetests, die die Folge oder Anzahl der Balken unter einem Monat fest erwarten
  (Monat direkt gefolgt von Tagen), brauchen die neue Ebene; das klärt der Test-Thread mit der Meilenstein-Definition.

## D-212 Tiefe der Gruppierung wählbar (Feature `kontoblatt-gruppierung`)

- **Anlass:** Mit D-211 hat die Gruppierung vier Ebenen. Auf ruhigen Konten ist das zu viel, und ein Tag mit einer
  einzigen Buchung belegt zwei Zeilen (Tagesbalken und Buchung).
- **Entscheidung** (mit dem Auftraggeber am 2026-11-19 abgestimmt): Die Leiste über der Liste heißt jetzt
  „Keine | Jahr | Monat | Abschnitt | Tag“ und ersetzt „Keine | nach Datum“ (ergänzt D-152). Die gewählte Ebene ist
  die tiefste, alle darüber bleiben; die Buchungen stehen direkt unter der tiefsten Ebene. Eine Ebene in der Mitte
  lässt sich nicht auslassen (Monat → Tag ohne Abschnitt gibt es nicht); dem Auftraggeber reicht die Tiefe.
  - Adresse: `?gruppierung=datum&tiefe=jahr|monat|abschnitt`. Ohne `tiefe` und bei unbekanntem Wert gilt „Tag“
    (volle Tiefe), bestehende Adressen bleiben damit gültig; „Tag“ wird nicht in die Adresse geschrieben. `tiefe`
    ist wie `gruppierung` Ansicht und kein Parameter der Buchungsliste.
  - Kennungen: `gruppierung-keine` wie bisher, neu `gruppierung-jahr`, `gruppierung-monat`,
    `gruppierung-abschnitt`. Der Knopf „Tag“ behält die bisherige Kennung `gruppierung-datum`, weil er dieselbe
    Wirkung hat wie bisher „nach Datum“. Gedrückt (`aria-pressed`) ist immer genau ein Knopf.
  - Kürzel `v g` schaltet der Reihe nach: keine → Jahr → Monat → Abschnitt → Tag → keine (bisher keine ↔ nach Datum).
  - Zugeklappte Perioden bleiben beim Wechsel der Tiefe zugeklappt. Klappen, Summen und „Alles
    zusammenklappen/aufklappen“ gelten für die sichtbaren Ebenen.
  - Der Service-Worker-Cache heißt jetzt `kontor-huelle-40`.
- **Folge für die Abnahme:** Tests, die die Beschriftung „nach Datum“ erwarten oder mit `v g` zweimal hin und zurück
  schalten, brauchen die neue Leiste bzw. Reihenfolge; das klärt der Test-Thread mit der Meilenstein-Definition.

## D-213 Bedienskript und Anleitung für die Testinstanz (ergänzt D-205)

- **Auftrag (2026-11-19):** Eine Anleitung zum Starten der Testinstanz und ein Skript für die wiederkehrenden
  Schritte; auf ausdrückliche Anweisung ohne Meilenstein-Definition und Abnahmetests auf main gemergt (Branch
  `feature/testinstanz-skript`).
- **Entscheidung:** `betrieb/kontor-test.sh` (Paketdaten, Ziel `/usr/local/bin/kontor-test`) mit den Befehlen
  `start <branch>`, `neu`, `stop`, `loeschen`, `status`, `log`. Das Skript kopiert selbst nichts: Branch holen,
  Daten kopieren und Starten bleibt allein Sache von `python -m kontor.testinstanz` (D-205); das Skript ruft es
  auf, wartet bis zu 30 s auf den Port und zeigt die Adresse, bei Misserfolg die letzten Protokollzeilen.
- Ein Branchname ohne `/` außer `main` wird zu `feature/<name>` ergänzt. Der zuletzt eingerichtete Branch steht
  in `/root/.kontor-test-branch` (nur nach erfolgreichem Einrichten geschrieben); `neu` richtet ihn erneut ein.
- Der Port kommt aus `KONTOR_PORT` in `/etc/kontor/kontor-test.env`, ersatzweise 8081.
- Anleitung: `TESTINSTANZ.md` im Wurzelverzeichnis, Verweis in der README.
- **Nicht geprüft:** Lauf unter systemd auf dem echten Server (wie bei D-205). Eigene Tests
  `tests/test_testinstanz_skript_eigen.py` mit einer Attrappe statt des Programms.

## D-214 Regeleditor: Zeitraum statt Testmengen-Ausdruck, Test ohne Kategorie, Fehler am Feld (Feature `regeleditor-feinschliff`)

- **Anlass:** Rückmeldungen vom 2026-11-19: (1) Die Testliste zeigte ein altes Ergebnis, weil der Test ohne gültige
  Kategorie mit 422 scheiterte und nur eine kleine Statuszeile darauf hinwies. (2) Das Feld „Testmenge (Filter)“
  wurde für die Bedingung gehalten; die Bedingung filtert die rechte Seite ohnehin. (3) Speichern ohne Namen
  ergab nur „Die Anfrage ist ungültig.“
- **Testbereich:** Das freie Ausdrucksfeld für die Testmenge und der Knopf „Als Testmenge übernehmen“ entfallen
  (ändert D-185/D-193 und Konzept 5.3). Es bleiben das Quellkonto und der Zeitraum als Auswahl (12 Monate,
  dieses Jahr, Vorjahr, alle; Vorgabe 12 Monate), weil Regeln kein Datum kennen und der Zeitraum den Umfang von
  „Anwenden…“ bestimmt. „Als Regel speichern…“ aus dem Kontoblatt übergibt den Filter nicht mehr als Testmenge.
  Die Schnittstelle (`testmenge` in `/api/regeln/test` und `/anwenden`) bleibt unverändert.
- **Test ohne Kategorie:** Die Oberfläche schickt nur eine gewählte Kategorie mit; ohne Kategorie zeigt der Test
  die Treffer. Scheitert der Test dennoch, wird das alte Ergebnis entfernt und der Grund in der Zählzeile
  genannt, statt die alte Liste stehen zu lassen (ergänzt D-192, das nur ungültige Ausdrücke betrifft).
- **Fehlermeldungen:** `fehlerText` (`kern.js`) hängt bei `validierung` die Einzelheiten des Servers an (Feld und
  Regel, nie Werte); Dialoge (`imDialog`) und Meldungen (`fehlerMelden`) verwenden es. Der Regeleditor prüft
  vor dem Senden: Ohne Kategorie nennt er den Grund am Feld; ein leerer Name wird aus Bedingung und Kategorie
  vorgeschlagen (erster Text der Bedingung, „REWE → Lebensmittel“, Konzept 3), als Platzhalter sichtbar und
  beim Speichern übernommen.
- **Prüfung:** `tests/test_browser_ausdruck.py` (Zeitraum-Auswahl, Namensvorschlag, Editor ohne Kategorie).

## D-215 Regeln vergeben Tags; Kategorie optional (Feature `regel-tags`)

- **Anlass:** Auftrag vom 2026-11-19: Im Regeleditor lassen sich neben der Kategorie Tags vergeben. Tags sind
  additiv, eine Regel kann mehrere vergeben, und Tags lassen sich dabei neu anlegen. Mit dem Auftraggeber
  abgestimmt: Kategorie optional, Tags sofort ohne Bestätigung, Tags aller passenden Regeln.
- **Datenmodell:** Schema 14. `regel.kategorie_id` darf NULL sein (Tabelle wird bei der Migration neu aufgebaut,
  `regel_automatisch` und der ID-Zähler bleiben erhalten). Neue Tabelle `regel_tag (regel_id, tag_id)`, gehört
  zur Objektart `regel`. Eine Regel braucht beim Anlegen und Ändern mindestens eine Aktion (Kategorie oder Tag),
  sonst 422 (`validierung` bzw. beim Ändern `regel_ohne_aktion`). Höchstens 20 Tags je Regel.
- **Schnittstelle:** Regeln tragen `tag_ids` (aufsteigend, in Antworten immer vorhanden) und `kategorie_id` kann
  `null` sein. `POST /api/regeln/test` nimmt `tag_ids` an und liefert je Treffer `tags_neu` sowie `tags_anzahl`
  und `gesperrt_anzahl`. `POST /api/regeln/anwenden` liefert zusätzlich `tags` (je Buchung die neu vergebenen
  Tags), aber nur, wenn es welche gibt; sonst bleibt die Antwort wie bisher.
- **Auswertung:** Für die Kategorie gilt weiter die erste passende Regel **mit** Kategorie; Regeln ohne Kategorie
  verdecken nichts. Die Tags aller passenden aktiven Regeln werden der Buchung hinzugefügt, nie entfernt:
  bei der Synchronisation an jede neue Buchung (unabhängig davon, welche Stufe die Kategorie bestimmt hat),
  beim Sammel-Anwenden an jede nicht gesperrte Buchung im Umfang (auch Splitbuchungen und bereits
  kategorisierte, auch mit `nur_unkategorisiert`), beim Anwenden einer Regel an jeden nicht gesperrten Treffer
  (auch verdeckte und abweichende). Tags sind keine Vorschläge; sie gelten sofort und sind über Rückgängig
  bzw. an der Buchung wieder entfernbar. Gesperrte Buchungen bleiben unberührt.
- **Tag löschen:** Die Regel bleibt und verliert den Tag (in derselben Änderung, mit Rückgängig wiederhergestellt).
  Hatte sie nur diesen Tag und keine Kategorie, bleibt sie ohne Wirkung stehen und wird in der Liste als
  „(keine Aktion)“ gezeigt; die Prüfung einer Sicherung lässt solche Regeln zu.
- **Protokoll und Sicherung:** `regel_tag` in `protokoll._TABELLEN`; die Protokollform einer Regel enthält
  `tag_ids` nur, wenn sie Tags hat (bisherige Formen bleiben unverändert). Sicherungsdatei Schemaversion 9 mit
  `regel_tag`; ältere Sicherungen werden ohne die Tabelle gelesen.
- **Oberfläche:** Im Regeleditor steht unter „Dann“ die Kategorie mit dem Eintrag „– keine Kategorie –“ (Vorgabe
  bleibt die erste Kategorie) und das Feld „Tags hinzufügen“ (vorhandene Tags zur Auswahl, unbekannte Namen
  werden beim Speichern in derselben Aktion angelegt; Abbrechen legt nichts an). Der Testbereich zeigt je Treffer
  die Tags, die dazukämen; die Regelliste zeigt sie hinter der Kategorie.
- **Nicht im Umfang:** Tags entfernen per Regel, „Danach keine weiteren Regeln“, „direkt bestätigen“. Regeln wirken
  wie bisher nicht beim Import und nicht bei von Hand angelegten Buchungen.
- **Prüfung:** `tests/test_regel_tags_eigen.py`, `tests/test_browser_ausdruck.py::test_regeleditor_tags`.

## D-216 Anwenden-Fenster verständlich, Tags an Buchungen sichtbar bearbeiten (Feature `regel-anwenden-fenster`)

- **Anlass:** Rückmeldungen vom 2026-11-19. (1) Nach „Speichern und anwenden“ zeigte das Fenster das Wort „null“
  und den rohen Ausdruck der Testmenge (`datum in -12m`). (2) Tags an Buchungen sollen bearbeitbar sein: hinzufügen,
  neu anlegen, entfernen, auch für mehrere Buchungen im Kontoblatt.
- **Anwenden-Fenster:** Ursache von „null“ war ein leerer Teil, der als Text in das Fenster geschrieben wurde; Teile
  ohne Inhalt werden nicht mehr angehängt (derselbe Fehler im Fenster „Betragsfilter“ ist mit behoben). Das Fenster
  nennt jetzt den Zeitraum in Worten statt des Ausdrucks, die Kategorie beim Namen, die Zahl der Buchungen, die Tags
  erhalten, und bietet „abweichende überschreiben“ nur an, wenn es abweichende gibt. Ändert die Regel im gewählten
  Umfang nichts, steht das dort (`regel-anwenden-nichts`) und es gibt nur „Schließen“. Der Umfang steht in
  `regel-anwenden-umfang`.
- **Tag-Dialog (`tag-auswahl`, ergänzt oberflaeche.md 9.2):** Der Dialog zeigt die vorhandenen Tags der gewählten
  Buchungen (`tag-auswahl-vorhanden`, `data-geladen`), bei mehreren Buchungen mit „(alle)“ bzw. „(n von m)“. Ein ×
  je Tag (`tag-auswahl-weg-<tag-id>`) entfernt ihn von allen gewählten Buchungen; das ist ein Rückgängig-Schritt,
  und der Dialog bleibt offen, damit sich mehrere Tags entfernen lassen. Namensfeld, „Hinzufügen“ (legt unbekannte
  Tags an) und „Entfernen“ verhalten sich wie bisher. Die Tags kommen aus den geladenen Zeilen des Kontoblatts;
  für nicht geladene Buchungen werden höchstens 50 einzeln nachgelesen, darüber nennt der Dialog, dass er die
  Tags der übrigen nicht zeigt (Hinzufügen und Entfernen wirken trotzdem auf alle).
- **Prüfung:** `tests/test_browser_ausdruck.py::test_anwenden_fenster_ohne_unsinn` und
  `::test_tags_im_kontoblatt_bearbeiten`.

## D-217 Berichtswahl und neun weitere Berichte (Feature `berichte`)

- **Anlass:** Auftrag vom 2026-11-19: alle vorgeschlagenen Berichte umsetzen; die Berichtsart wird auf der
  Berichtsseite gewählt.
- **Berichtswahl:** Alle Berichte liegen unter `/berichte?art=<name>` in einem Tab; eine Leiste oben wechselt die
  Art. Ohne `art` (und mit `art=uebersicht`) erscheint die bisherige Seite mit Kontostandsverlauf und
  Einnahmen/Ausgaben unverändert, damit bestehende Adressen und Abnahmetests gelten. Der Monatsbericht ist die Art
  `monat`; die frühere Adresse `/berichte/monat` führt dorthin. Der Palettenbefehl „Gehe zu: Monatsbericht“ und
  der Knopf auf der Berichtsseite (D-206) entfallen, die Leiste ersetzt beide. Kein neuer Eintrag in Navigation
  oder Palette.
- **Endpunkte** (alle lesend, kein Zustand, noch nicht im OpenAPI-Vertrag): `GET /api/berichte/vertraege`, `jahr`,
  `vorschau`, `vermoegen`, `kategorien`, `empfaenger`, `geldfluss`, `qualitaet`, `tags`. Unbekannte Parameter sind
  ein Validierungsfehler.
- **Gemeinsame Grundlage:** die Wirkung einer Buchung wie in D-206. Neu, auch für den Monatsbericht: Splits auf
  Eigenkapitalkonten außer „Unkategorisiert“ (Anfangsbestand, Korrekturen) sind neutral wie Bestandskonten; ein
  Anfangsbestand ist also keine Einnahme.
- **Verträge:** Serien der Erkennung wiederkehrender Buchungen. Eine Serie, deren letzte Buchung nur Bestands- und
  Eigenkapitalkonten berührt, ist eine Umbuchung (Sparrate) und erscheint nicht. Jahreskosten = aktueller Betrag
  mal Zahlungen je Jahr; „neu“ = erste Zahlung in den letzten 90 Tagen.
- **Jahr:** Der Vergleich mit dem Vorjahr bis zum laufenden Monat erscheint nur, wenn das Vorjahr in jedem dieser
  Monate Buchungen hat.
- **Vorschau:** Vorgabe sind die offenen Girokonten. Ereignisse sind die fälligen Zahlungen aktiver Serien
  (hier einschließlich Umbuchungen, weil sie das Konto verlassen) und die Raten aktiver Kredite, sofern nicht
  schon eine Serie mit gleichem Betrag auf dem Zahlungskonto erkannt ist. Übliche Ausgaben: variabler Tagesschnitt
  der letzten 90 Tage. „Frei bis zum nächsten Eingang“ = Stand heute minus feste Zahlungen und übliche Ausgaben
  bis zum nächsten erkannten Eingang.
- **Vermögen:** alle Bestandskonten zum Monatsende; Guthaben ist die Summe der positiven, Schulden die der
  negativen Stände. Tilgung = Abstand zum höchsten Monatsendstand der Schuld.
- **Kategorien und Geldfluss:** Unterkategorien zählen in ihre Hauptkategorie. „Unkategorisiert“ folgt der
  Richtung der Buchung. Schnitt über die bis zu sechs Vormonate mit Buchungen. Im Geldfluss wandert eine im
  Saldo negative Kategorie auf die andere Seite; die Lücke heißt „Übrig“ oder „Aus dem Bestand“. Das Flussbild
  ist handgezeichnetes SVG (das vorhandene Plotly-Paket kennt kein Flussdiagramm); auf dem Handy stehen nur die
  beiden Tabellen.
- **Tags:** Eine Buchung trägt ihre eigenen Tags und die ihres Empfängers. Mit mehreren Tags zählt sie bei jedem
  voll; deshalb gibt es keine Summe über alle Tags, nur „mit Tag“ und „ohne Tag“. Vergleich für zwei bis vier Tags.
- **Datenqualität:** betrachtet die letzten zwölf Monate ohne Umbuchungen. Tags gelten als freiwillig und gehen
  in keine Bewertung ein.

## D-218 Kontonamen je Hierarchieebene eindeutig (Sammelbranch `feature/sammel3`)

- **Anlass:** Auftrag vom 2026-11-19: Kategorien dürfen auf ihrer Ebene nur einmal mit gleichem Namen vorkommen.
  Abgestimmt: Vergleich ohne Groß-/Kleinschreibung, gilt für alle Konten, Altbestand automatisch zusammenführen,
  Importe führen zusammen, alles andere wird abgelehnt. Ändert `datenmodell.md` („Keine Eindeutigkeit gefordert“).
- **Regel:** Unter demselben Elternkonto ist ein Name nur einmal erlaubt; verglichen wird nach `strip()` und
  `casefold()`. Auf der obersten Ebene gilt das je Kontoklasse (Bestand, Aufwand, Ertrag, Eigenkapital): „Zinsen“
  als Aufwand und als Ertrag bleiben nebeneinander möglich, zwei Bestandskonten „Giro“ nicht.
- **Ablehnen:** Anlegen, Umbenennen, Verschieben, Löschen mit hochrutschenden Unterkonten, Zusammenführen mit
  mitwandernden Unterkategorien und Rückgängig enden mit 409 `konto_existiert` (`details.konto_ids`), auch im
  Probelauf. Geprüft wird am Ende jeder protokollierten Änderung, die Konten berührt.
- **Bereinigen** (Altbestand beim Start, nach jedem Import, nach dem Einspielen einer Sicherung): gleichnamige
  Kategorien (Aufwand/Ertrag) werden in die mit der kleinsten ID zusammengeführt (Buchungen, Regeln, Vorlagen,
  Unterkategorien wandern mit; entstehen dadurch neue Dubletten, werden auch sie bereinigt). Bestandskonten,
  Eigenkapitalkonten und Kategorien mit Kreditbezug werden nicht zusammengeführt, sondern bekommen den Zusatz
  „(2)“, „(3)“ …; zwei Bankkonten automatisch zu vereinen wäre nicht umkehrbar und fachlich falsch.
- **Altbestand:** eine Änderung im Protokoll (Aktion `kategorien_zusammenfuehren`, Quelle `manuell`,
  Beschreibung „Gleichnamige Konten bereinigt“); ihr Rückgängig wird nach obiger Regel abgelehnt.
- **Importe:** Warnungen `konto_zusammengefasst` bzw. `konto_umbenannt` (Referenz: Name). Die zweite Kategorie
  behält keine eigene `extern_id`; ein erneuter Import legt sie deshalb kurz an und führt sie wieder zusammen
  (Bestand danach unverändert, der Zähler `kategorien_neu` nennt sie aber erneut).
- **Technische Konten** („Unkategorisiert“, „Korrekturen“): gibt es beim ersten Bedarf schon ein gleichnamiges
  Eigenkapitalkonto ohne Kennung auf der obersten Ebene, wird es übernommen statt ein zweites anzulegen.
- **Synchronisation:** ein neu angelegtes Bankkonto bekommt bei Namensgleichheit den Zusatz „(2)“.
- **Prüfung:** `tests/test_kontonamen_eigen.py`.

## D-219 Standardkategorie je Empfänger entfällt; „Regel erstellen…“ im Empfänger-Tab

- **Anlass:** Auftrag vom 2026-11-19; abgestimmt: ganz entfernen, vorhandene in Regeln umwandeln.
- **Umwandlung:** Beim Start (eine Änderung „Standardkategorien in Regeln umgewandelt“, Aktion `regel_anlegen`)
  und beim Einspielen älterer Sicherungen wird aus jeder Standardkategorie die Regel „Empfänger ist <Name>“ →
  Kategorie, am Ende der Regelliste (entspricht der bisherigen Stufe nach den Regeln).
- **Entfällt:** die Stufe „Standardkategorie“ bei Synchronisation und Erfassen (neu: Kreditrate → Vorlage → Regel →
  Lernmodell → „Unkategorisiert“), Feld und Spalte im Empfänger-Tab. `standardkategorie_id` bleibt als Feld der
  Empfängerform stehen und ist immer `null`, damit ältere Protokolleinträge und Sicherungen lesbar bleiben; ein
  anderer Wert wird mit 422 `kategorie_ungueltig` abgelehnt. Die Spalte der Datenbank und der Sicherungsdatei
  bleibt (leer). Alte Vorschläge mit Quelle `standardkategorie` bleiben gültig.
- **Kontextmenü `em-regel` „Regel erstellen…“:** öffnet den Regeleditor mit dem Namen des Empfängers und dem
  Ausdruck `empf == "<Name>" or empf == "<Alias>" …`; Kategorie und Tags wählt der Nutzer dort.
- **Prüfung:** `tests/test_standardkategorie_eigen.py`, `tests/test_browser_sammel3.py`.

## D-220 Empfänger-Tab: „Anzeigen im Konto …“

- Kontextmenü `em-im-konto`: öffnet das Kontoblatt eines Bestandskontos mit dem Empfänger als Filter
  (`/konten/<id>?empfaenger_id=<id>`). Mit Buchungen auf mehreren Konten ein Untermenü (`em-im-konto-<konto-id>`,
  die meistbenutzten zuerst, mit Anzahl), ohne Buchungen ausgegraut. Neuer lesender Endpunkt
  `GET /api/empfaenger/{id}/konten` → `[{konto_id, anzahl}]` (noch nicht im OpenAPI-Vertrag).

## D-221 Statistische Analyse entfällt

- Seite `/statistik` (jetzt 404), Navigationseintrag, Palettenbefehl und `GET /api/statistik` (D-145) sind
  entfernt; die Aussagen stehen in den Berichten (D-217). `statistik.py` enthält nur noch Median, MAD und
  robustes z für Monatsbericht, Berichte und Verdachtsprüfung.

## D-222 Dubletten: zur Buchung springen

- Jede Buchung eines Verdachts oder Vorschlags auf `/dubletten` zeigt ihren Verwendungszweck und je Bestandskonto
  einen Verweis „Zeigen in: <Konto>“ (`dublette-buchung-<id>-konto-<konto-id>`), der wie in den Berichten ins
  Kontoblatt springt und die Buchung markiert.

## D-223 Bestätigung trägt das Tag „B-<Name>“

- Abgestimmt: Die Bestätigung von Buchungen und Empfängern nutzt die Tags „B-Torsten“ / „B-Tina“ statt „Torsten“ /
  „Tina“. Vorhandene Tags werden beim Start (eine Änderung, Aktion `tag_umbenennen`) und beim Einspielen älterer
  Sicherungen umbenannt; gibt es das neue Tag schon, wandern die Zuordnungen dorthin. `data-bestaetigt` und
  `data-person` nennen weiter den Namen der Person.

## D-224 Kontoblatt: Spalten ein- und ausblenden

- Kontextmenü der Kopfzeile: „Spalten ein- und ausblenden“ (`km-spalten-wahl`) mit einem Eintrag je Spalte
  (`km-spalte-<feld>`, Haken = sichtbar). Mindestens eine Spalte bleibt. Gemerkt im Browser je Listenart (Konto,
  Kategorie) unter `kontor.spalten.aus`; in der kompakten Ansicht (Handy) ohne Wirkung. Die Zellen bleiben im
  Dokument (`data-spalten-aus` an der Liste, per CSS versteckt).

## D-225 Tags als eigene Ansicht

- Neue Seite `/tags` (Navigation `navlink-tags` nach „Kategorien“, Palette „Gehe zu: Tags“): Liste aller Tags mit
  Zahl der Buchungen, Anlegen, Umbenennen, Löschen. Ein Klick auf ein Tag zeigt darunter seine Buchungen (höchstens
  500, neueste zuerst) mit Summe und „Im Konto zeigen“; die Wahl steht in der Adresse (`?tag=<id>`). Anders als
  bei Kategorien öffnet sich kein Kontoblatt, weil Tags kein Konto sind; die Tag-Verwaltung in den Einstellungen
  bleibt.

## D-226 Mail-Blatt: Darstellung, Suche, Mail von Hand zuordnen

- **Darstellung:** drei Spalten (Empfangen, Absender und Betreff, Zuordnung). Datum („Heute“, „Gestern“ oder
  Datum) und Uhrzeit stehen untereinander und brechen nicht um; Absender einzeilig, Betreff höchstens zweizeilig;
  das Postfach erscheint nur, wenn mehrere Postfächer gemischt gezeigt werden.
- **Suche** (`mail-suche`, REST `suche`): jedes Wort muss in Absender, Betreff oder Text vorkommen (ohne
  Groß-/Kleinschreibung und Umlautunterschied); wirkt zusammen mit Postfach und Zuordnungsfilter, steht in der
  Adresse.
- **Zuordnen von Hand** (`mail-zuordnen` „Buchung zuordnen…“, `POST /api/mail/nachrichten/{id}/buchung` mit
  `buchung_id`, Aktion `dokument_aus_mail`): Dialog mit Buchungen von 14 Tagen vor bis 30 Tage nach der Mail
  (Zeitraum änderbar, Textsuche); Buchungen, deren Betrag in der Mail steht, zuerst und mit „Betrag passt“. Die
  Mail wird als Dokument an die Buchung gehängt und gilt im Mail-Blatt als zugeordnet („Von Hand“). Der Vermerk
  steht wie bei der Bestellnummer in `bestellmail` (leere Nummer, Betriebszustand); er entfällt, wenn das Dokument
  von der Buchung gelöst wird.
- Behoben: Der Lesebereich zeigte bei angehängten Mails „[object HTMLUListElement]“.

## D-227 Mail-Blatt: Zuordnung in der Liste als eine Zeile

- **Anlass:** Rückmeldung vom 2026-11-20: Die Zuordnungsspalte war unübersichtlich (mehrere Marken, dieselbe
  Buchung mehrfach, Begründungstexte in der Zeile).
- Die Spalte zeigt je Mail genau eine Zeile: Marke („Zugeordnet“, „Erwartet“, „Überfällig“), Ziel (erste Buchung als
  Sprung ins Kontoblatt bzw. Händler der erwarteten Zahlung), „+n“ für weitere, Betrag. Jede Buchung zählt einmal,
  auch wenn sie über Bestellnummer und erwartete Zahlung zugleich zugeordnet ist. Ohne Zuordnung steht „–“.
  Weg der Zuordnung als Tooltip; Begründungen, Kennung und alle Buchungen stehen nur im Lesebereich.

## D-228 Mail-Blatt: Mails derselben Zuordnung stehen beieinander

- **Anlass:** Auftrag vom 2026-11-20: Mails gruppieren, die zur gleichen Buchungszuordnung gehören.
- **Gruppe:** Mails, die dieselbe Buchung oder dieselbe erwartete Zahlung betreffen (auch mittelbar über eine
  dritte Mail), bilden eine Gruppe – gleich, ob über Bestellnummer, erwartete Zahlung oder von Hand zugeordnet.
- **Liste:** `GET /api/mail/nachrichten?gruppieren=ja` stellt eine Gruppe an die Stelle ihrer ersten Mail (nach der
  gewählten Reihenfolge), die übrigen Mails der Gruppe direkt dahinter; jede Mail trägt `gruppe` (ID der ersten
  Mail, sonst `null`). Ohne den Parameter bleiben Reihenfolge und Antwort wie bisher. Gruppiert wird innerhalb
  der gefilterten Menge (Postfach, Zuordnungsfilter, Suche); eine Gruppe kann über eine Seitengrenze reichen.
- **Oberfläche:** Das Mail-Blatt fordert immer gruppiert an. Die erste Mail zeigt die Zuordnung und „n Mails zu
  dieser Zuordnung“, die folgenden sind eingerückt und zeigen „↳ gehört dazu“; ein Balken am linken Rand
  verbindet die Gruppe (`data-gruppe`, `data-gruppe-rolle` = `kopf`/`folge`/`ende`).
- **Prüfung:** `tests/test_browser_sammel3.py::test_mails_derselben_zuordnung_stehen_beieinander`.

## D-229 Mail-Ansicht: Bilder fremder Server auf Wunsch nachladen

- **Anlass:** Auftrag vom 2026-11-20: In der Mail-Ansicht des Kontoblatts fehlen die Bilder der Mail. Bisher
  entfernte die Ansicht jede fremde Bildadresse (Schutz vor Zählpixeln, dokumente.md); das bleibt die Vorgabe.
- **Nachladen:** Enthält die Mail Bilder fremder Server, zeigt die Ansicht eine Leiste (`mail-bilder-leiste`) mit der
  Anzahl, dem Knopf „Bilder laden“ (`mail-bilder-laden`) und dem Haken „immer laden“ (`mail-bilder-immer`, gemerkt
  im Browser unter `kontor.mail.bilder`). Erst dann lädt der Browser die Bilder direkt vom fremden Server; der
  Kontor-Server ruft nie selbst fremde Adressen ab.
- **Schnittstelle:** `GET /api/dokumente/{id}/mail/html?bilder=ja` lässt Bildadressen mit `http(s)://` (und `//`,
  als https) in `<img src>`, `background` und `url(…)` in Stilen stehen und liefert die Inhaltsrichtlinie mit
  `img-src data: https: http:`; alles andere bleibt wie bisher (keine Skripte, kein `srcset`, kein `@import`, keine
  Schriften, `sandbox`, kein Referrer). `GET /api/dokumente/{id}/mail/bilder` → `{"anzahl": n}`.
- **Folge:** Mit geladenen Bildern erfährt der Absender, dass und von welcher Adresse die Mail geöffnet wurde.
- **Prüfung:** `tests/test_browser_sammel3.py::test_mail_bilder_serverseitig` und
  `::test_mail_bilder_nachladen_im_kontoblatt` (Bild vom eigenen Testserver, nur Loopback).

## D-230 Anbieter-Beschreibungen: Mail-Abgleich als zuladbare Module

- **Anlass:** Auftrag vom 2026-11-20: den Abgleich von Mail und Buchung für Amazon verallgemeinern und als
  zuladbare Module beschreiben (mit regulären Ausdrücken), damit er auch für PayPal und weitere Anbieter gilt.
- **Lösung:** Paket `kontor.anbieter`: Eine Beschreibung (TOML) nennt Absender, Kennung, Mailarten mit Rolle
  (`ausgabe`, `erstattung`, `storno`), Bausteine für Beträge und Texte und die Bankseite (Namen, Kennungsmuster).
  Mitgeliefert `amazon.toml` und `paypal.toml`; weitere aus `anbieter_verzeichnis`
  (`KONTOR_ANBIETER_VERZEICHNIS`). Beschreibung des Formats: `ANBIETER.md`.
- **Deckungsgleich mit dem bisherigen Code:** `tests/test_anbieter_eigen.py` vergleicht die beiden Beschreibungen
  mit der eingefrorenen bisherigen Erkennung (`tests/referenz_mailerkennung.py`) über 6000 zufällig gebaute Mails
  je Lauf, feste Beispiele und die Mock-Mails; ein zweiter Test stellt sicher, dass dabei jede Mailart beider
  Anbieter vorkommt. Kein Unterschied gefunden. Die Abnahmetests M20 und M24 bleiben wie zuvor.
- **Verallgemeinert:** (1) Erwartete Zahlungen: Schlüssel `<anbieter>:<mailart>:<kennung>` (für Amazon und PayPal
  unverändert), Storno und Erstattung beziehen sich auf die Mailart mit Rolle `ausgabe`. (2) „Name steht in der
  Buchung“: aus `bank.namen` statt des fest eingebauten „amzn“. (3) Anhängen über die Kennung (bisher nur
  Amazon-Bestellnummer, D-208): für jeden Anbieter mit `bank.kennung`; für PayPal der 17-stellige Transaktionscode,
  gesucht nur in PayPal-Mails (`alle_mails` aus), für Amazon weiter in allen Mails.
- **Datenbank:** Schemaversion 15: `erwartung.anbieter` lässt jeden Namen einer Beschreibung zu (Tabelle wird
  umgebaut, Inhalt und Zähler bleiben). Gemerkte Kennungen der Mails (`bestellmail_nummer`) werden einmal neu
  gesucht, wenn sich die Muster ändern (`meta.bestellmail_muster`).
- **Grenzen:** Der Grund einer erwarteten Zahlung bleibt `bestellung` oder `paypal` (Vertrag der Schnittstelle).
  Python-`re` kennt kein Zeitlimit; geschützt wird über die Länge der Ausdrücke (500) und des ausgewerteten Textes
  (200 000 Zeichen). Beschreibungen sind Dateien des Betreibers, nicht aus der Oberfläche änderbar.
- **Offen:** Ob der PayPal-Transaktionscode im Verwendungszweck der Bank steht, ist mit echten Auszügen zu prüfen;
  sonst greift für PayPal nur Betrag und Name.

## D-231 Kontoblatt: Summen der markierten Buchungen

- **Anlass:** Auftrag vom 2026-11-20 („markieren von Mails im Kontoblatt“ – gelesen als: markierte Buchungen im
  Kontoblatt): Beim Markieren immer die Summe der Ausgaben, der Einnahmen und über alles zeigen.
- Sobald Buchungen markiert sind, stehen neben „n ausgewählt“ drei Beträge aus Sicht des Blatts: Ausgaben
  (`auswahl-ausgaben`), Einnahmen (`auswahl-einnahmen`) und Summe (`auswahl-summe`), je mit `data-betrag` in Cent;
  ohne Markierung ist `auswahl-summen` verborgen. Auf dem Handy stehen sie im Auswahlkopf
  (`auswahl-kopf-summen`). Gerechnet wird mit den geladenen Zeilen in ganzen Cent.

## D-232 PayPal: Zuordnung nach Betrag, Zeitfenster und Händlername (ersetzt die Annahme aus D-230)

- **Anlass:** Recherche vom 2026-11-20: Die PayPal-Lastschrift nennt keinen Transaktionscode. Der Verwendungszweck
  lautet „PP.1234.PP . HAENDLER, Ihr Einkauf bei HAENDLER“, die End-to-End-Referenz trägt eine 13-stellige Nummer,
  die in keiner Mail steht (PayPals Aktivitäten-Export kennt ein Feld „Bank Reference ID“ mit 13 Zeichen; ob es
  dieselbe Nummer ist, ist ungeprüft). Auftrag: Heuristik aus gleichem Betrag, Datum ± 5 Tage und Händlername in
  Teilen im Verwendungszweck.
- **Beschreibung PayPal:** `bank.kennung` entfällt; neu `bank.haendler` (Händler aus „PP.….PP . <Händler>, Ihr
  E…“), `haendler_noetig = true`, `tage_vor = 5`, `tage_nach = 5`. Diese Angaben stehen jedem Anbieter offen
  (`ANBIETER.md`); Amazon bleibt unverändert (3 Tage davor, 45 danach, Kennung oder Name).
- **Regel bei `haendler_noetig`:** Automatisch zugeordnet wird, wenn genau eine freie Buchung im Fenster den
  gleichen Betrag hat und den Händler der Mail in Teilen nennt (`anbieter.name_in_teilen`): ein Wort des Namens mit
  mindestens 4 Zeichen irgendwo im Text, kürzere nur als ganzes Wort, Allerweltswörter zählen nicht; ein gekürzter
  Name der Bank zählt, wenn er der Anfang des zusammengeschriebenen Namens ist. Als PayPal-Buchung gilt, was
  „paypal“ nennt oder dem Muster des Verwendungszwecks entspricht. Nennt die Mail keinen Händler, wird nichts
  automatisch zugeordnet. Andere Buchungen gleichen Betrags ohne den Händler stören nicht mehr.
- **Folge für die Abnahme:** `m20/test_m20_zuordnung.py::test_automatisch_ueber_betrag_nur_eindeutig` ist rot: Der
  Test erwartet, dass eine zweite Buchung gleichen Betrags ohne Anbieter die Zuordnung der PayPal-Buchung
  verhindert. Für den Test-Thread als Änderung von erwartungen.md 5.2 zu übernehmen.
- **Prüfung:** `tests/test_anbieter_eigen.py` (`test_paypal_heuristik_…`, `test_paypal_zwei_passende_…`,
  `test_name_in_teilen`).

## D-233 Kontoblatt: Bereichsauswahl bei Gruppierung und anderer Sortierung

- **Anlass:** Fehlerbericht vom 2026-11-20: Nach Zeitraum gruppiert und nicht nach Datum sortiert, stimmen
  Darstellung und Markieren nicht.
- **Ursache:** Umschalt+Klick und Umschalt+Pfeil bestimmten den Bereich in der Reihenfolge der geladenen Liste
  (z. B. nach Betrag über alle Zeiträume), nicht in der angezeigten Reihenfolge (je Zeitraum). Dadurch wurden
  Buchungen quer durch die Zeiträume markiert. Jetzt gilt die angezeigte Reihenfolge; Buchungen in zugeklappten
  Zeiträumen gehören nicht zum Bereich.
- **Nicht gefunden:** eine davon unabhängige falsche Darstellung. Aufbau der Zeiträume, Reihenfolge innerhalb der
  Zeiträume und der gezeichnete Ausschnitt bei 700 Buchungen waren mit Sortierung nach Betrag und Empfänger
  richtig (geprüft im Browser).
- **Prüfung:** `tests/test_browser_sammel3.py::test_bereichsauswahl_folgt_der_anzeige_bei_gruppierung`.

## D-234 Meldung mit „Rückgängig“ nach Änderungen ist ausgeschaltet

- **Anlass:** Auftrag vom 2026-11-20: Die Rückgängig-Anzeige nach Aktionen stört.
- Die Erfolgsmeldung mit `meldung-rueckgaengig` nach eigenen Änderungen erscheint nicht mehr, außer sie wird unter
  Einstellungen → Allgemein eingeschaltet (`einstellung-erfolgsmeldung`, gemerkt im Browser unter
  `kontor.meldung.erfolg`). Rückgängig bleibt über die Kopfzeile, Strg+Z und die Palette. Fehlermeldungen, Hinweise
  (z. B. automatisch angelegte Regel) und die Meldung nach einem Rückgängig selbst bleiben.
- **Folge für die Abnahme:** Browsertests, die die Erfolgsmeldung erwarten (oberflaeche.md 4.3), brauchen die
  Einstellung vorab, wie die Person (`browser_fixtures.neue_seite`). Die eigenen Rauchtests setzen sie in
  `tests/test_browser.py::seite`.

## D-235 Seite „Konfiguration“ (Umgebungsdatei zum Nachsehen)

- **Anlass:** Auftrag vom 2026-11-20: eine Seite, die alle in der Umgebungsdatei gesetzten Konfigurationen zeigt; sie
  soll später in einem Entwicklermodus verschwinden.
- **Seite `/konfiguration`** (Navigation `navlink-konfiguration` unter „Betrieb“, auf dem Handy nicht in der
  Navigation; Palette „Gehe zu: Konfiguration“), nur lesend: (1) „In der Umgebung gesetzt“ – alle Variablen
  `KONTOR_…` (und `CREDENTIALS_DIRECTORY`) des laufenden Prozesses mit ihrem Text; Variablen, die Kontor nicht
  kennt, tragen „unbekannt“. (2) „Was gilt“ – jede Einstellung mit geltendem Wert, Vorgabe und Name der Variable,
  Abweichungen von der Vorgabe hervorgehoben und filterbar.
- **Schnittstelle** `GET /api/konfiguration` → `{umgebung: [{variable, wert, verborgen, bekannt}], wirksam: [{name,
  variable, gesetzt, wert, vorgabe, geaendert, verborgen}]}`; geschützt wie alle Endpunkte (Anmeldung).
- **Nie ausgegeben** werden Werte, deren Name nach einem Geheimnis klingt (Secret, Token außer `…_token_url`,
  Passwort, PIN außer `bank_pin_quelle`), sowie die Bank-Zugangskennungen `fints_benutzer` und `fints_kunden_id`;
  dort steht nur „verborgen“. Andere Umgebungsvariablen des Prozesses erscheinen nicht.
- **Grenze:** Gezeigt wird die Umgebung des Prozesses, nicht die Datei selbst; Kommentare und auskommentierte Zeilen
  der Datei sieht man nicht, dafür auch Werte aus der systemd-Unit.
- **Prüfung:** `tests/test_konfiguration_eigen.py`, `tests/test_browser_sammel3.py::test_konfiguration_seite`.

## D-236 UX-Durchgang auf `feature/sammel3`: 14 Funde umgesetzt

- **Anlass:** Auftrag vom 2026-11-20: UX-Tests ausführen, Verbesserungen mit Screenshots begründen; danach
  „Alle“ umsetzen. Geprüft im Mock-Modus mit synthetischen Daten, Desktop 1280 × 800 und Handy 390 × 844.
- **1 Mail-Ansicht:** leere Teile (Bilder-Leiste, Anhänge) erschienen als Wort „null“; sie entfallen jetzt.
- **2 Kontoblatt, Betrag:** die Betragsspalte klebt beim seitlichen Rollen am rechten Rand (Desktop); ist die Liste
  schmaler als 46 rem, gelten kleinere Mindestbreiten für Empfänger, Zweck und Kategorie. Eigene Spaltenbreiten
  (M22) bleiben unberührt. Die Vorgabe der Panels (beide offen, M8) ist bewusst nicht geändert.
- **3 Gruppenbalken:** so breit wie der sichtbare Teil der Liste, bleibt beim seitlichen Rollen stehen; in schmalen
  Listen nur die Zahlen (Eingang, Ausgang, „= Summe“), ohne Wörter und Buchungszahl. Alle `data-testid` bleiben.
- **4 Handy-Kontoblatt:** Filterfeld, Zeitraum-Chips und Gruppierung sind am Handy eingeklappt; `ansicht-umschalten`
  („Filter und Gruppierung“) klappt sie auf, ein Punkt zeigt einen aktiven Filter. „Baukasten“ bleibt sichtbar
  (oberflaeche.md 23.1). Am Desktop ändert sich nichts an der Sichtbarkeit.
- **5 Handy-Mail-Blatt:** keine Mail vorgewählt, die Liste steht zuerst (je Mail eine Karte); Antippen öffnet den
  Lesebereich, `mail-lesen-schliessen` schließt ihn. Am Desktop bleibt die erste Mail vorgewählt (oberflaeche.md 37).
- **6 Auswahl-Summen:** die Gruppierung steht jetzt in der Zeile der Zeitraum-Chips; die Infozeile gehört Anzahl,
  Summe und Auswahl allein, die Liste springt beim Markieren nicht mehr. Die Knöpfe heißen sichtbar „Alle zu“ /
  „Alle auf“; „Alles zusammenklappen“ / „Alles aufklappen“ (oberflaeche.md) stehen als `aria-label` und Tooltip.
- **7/8 Tags:** Datum ohne Umbruch, Knöpfe klein am Zeilenende (`tag-umbenennen-<id>`, `tag-loeschen-<id>`), am Handy
  Stift und Papierkorb mit Abstand, gewähltes Tag deutlich markiert, Sprungziele als Links mit „↗“ (gilt für alle
  Einzelbuchungstabellen, auch in den Berichten).
- **9 Mail-Blatt:** Status einzeilig (voller Text im Element, gekürzt angezeigt), Blättern unter der Liste, Betreff
  fett und Absender darüber in normaler Schrift, in der Zuordnung steht der Betrag vor dem Namen und wird nie
  gekürzt. Dafür trägt jede über Bestellnummer oder von Hand angehängte Buchung in der Mailliste `betrag` (Summe
  auf den Bestandskonten).
- **10 Empfänger:** Suche über Name und Aliase (`empfaenger-suche`, `empfaenger-treffer`; Tastatur und Strg+A folgen
  den sichtbaren Zeilen, verborgene verlieren die Auswahl), Spalte „Buchungen“ über `GET /api/empfaenger/anzahlen`
  → `[{empfaenger_id, anzahl}]` (nur lesend, Empfänger ohne Buchung fehlen), „Bearbeiten…“ ersetzt durch
  `empfaenger-menue-<id>` („⋯“, dasselbe Menü wie der Rechtsklick). `empfaenger-bestaetigen-<id>` bleibt mit Text.
- **11 Dubletten:** Gegenüberstellung als Tabelle, eine Spalte je Buchung, abweichende Angaben hervorgehoben
  (`data-abweichung`); Überschrift in Worten statt „Verdacht n (aehnlich)“; Hinweis, dass „Diese behalten“ die
  andere Buchung löscht. Knopftext „Diese behalten“ unverändert (oberflaeche.md).
- **12 Was kommt noch?:** bei überfälligen Einträgen sind nur Frist und Zustand rot, nicht die ganze Zeile.
- **13 Finanzübersicht:** Abstand in der Kachel, „Kategorien einblenden“ als Knopf mit Pfeil.
- **14 Tabs:** ab sechs Tabs steht am Ende der Leiste `tab-andere-schliessen` („Andere schließen“). Die Regel „jede
  Ansicht ein Tab“ (M17) bleibt; verworfen wurde, Navigationspunkte im selben Tab zu öffnen, weil das die
  freigegebene Definition ändern würde.
- **Nicht geändert:** grüne Hinterlegung kategorisierter Zeilen (M22).
- **Prüfung:** `tests/test_browser_ux.py`; `tests/test_browser_sammel3.py` angepasst (Spaltenraster wird ganz nach
  rechts gerollt gemessen).

## D-237 Änderungsprotokoll: Einzelheiten je Änderung in einem eigenen Fenster

- **Anlass:** Auftrag vom 2026-11-21 im Sammelthread: Das Änderungsprotokoll zeigt für jede Änderung eine
  detaillierte Liste der Änderungen in einem Extrafenster.
- **Entscheidung:** Jede Zeile des Protokolls hat den Knopf „Einzelheiten…“ (`aenderung-einzelheiten-<id>`; Tooltip:
  Umfang in Worten). Er öffnet das Fenster `aenderung-dialog` mit Zeitpunkt, Quelle, Vorgang (Code der Aktion),
  Umfang („3 Buchungen geändert, 1 Tag angelegt“), Stand (wirksam / rückgängig gemacht durch #n) und je betroffenem
  Objekt einem Abschnitt `ae-eintrag-<objekt>-<id>`: bei „geändert“ nur die abweichenden Angaben mit Vorher und
  Nachher, bei „angelegt“ und „gelöscht“ alle nicht leeren Angaben. Kennungen erscheinen als Namen (Konto mit Pfad,
  Empfänger, Tags; bei gelöschten Objekten aus derselben Änderung, sonst „#id“), Beträge in Euro, Datumsangaben
  deutsch, die Aufteilung je Split als „Konto: Betrag (Notiz)“.
- **Große Änderungen** (Import, Sicherung): zunächst 50 Objekte, „Weitere anzeigen“ in Schritten von 50; ab sechs
  Objekten ein Suchfeld über Titel und Angaben.
- **Daten:** `GET /api/aenderungen/{id}` (vorhanden, unverändert); kein neuer Endpunkt, nur lesend, kein
  Protokolleintrag. Neues Modul `app/aenderung.js` (in `sw.js` eingetragen).
- **Nicht enthalten:** Rückgängig aus dem Fenster heraus (bleibt in der Liste).
- **Prüfung:** `tests/test_browser_aenderung.py` (Desktop und Handy, angelegt/geändert, große Änderung, Suche).

## D-238 Geplante Zahlungen: Wiederholung, Vorschau, Zuordnung nach Namen

- **Anlass:** Auftrag vom 2026-11-21 im Sammelthread nach dem Vergleich mit KMyMoney und GnuCash: Zahlungen, die
  Kontor noch nicht aus der Vergangenheit ablesen kann (neuer Vertrag, einmalige Rechnung, seltene Beiträge), von
  Hand planen – einmalig oder mit Wiederholung –, in der Vorschau sehen und mit der Bankbuchung erledigen.
- **Grundlage:** Von Hand angelegte erwartete Zahlungen (Grund `manuell`, M20) gab es schon. Sie heißen in der
  Oberfläche jetzt „Geplant“; der Knopf auf „Was kommt noch?“ heißt „Zahlung planen…“ (`erwartet-neu` unverändert).
- **Wiederholung:** `POST`/`PATCH /api/erwartungen` nehmen `wiederholung` (`keine`, `monatlich`,
  `vierteljaehrlich`, `halbjaehrlich`, `jaehrlich`) und `wiederholung_bis` (Datum oder `null`); nur für Grund
  `manuell` (sonst 422 `wiederholung_nur_geplant`), ein Ende ohne Wiederholung ist 422 `wiederholung_fehlt`. Die
  Antwort trägt `wiederholung: {rhythmus, bis}` nur, wenn eine besteht – Einträge ohne Wiederholung sehen aus wie
  bisher (auch im Protokoll und in der Inhaltsprüfsumme der Sicherung).
- **Fortsetzung:** Wird eine solche Zahlung erfüllt (Buchung zugeordnet) oder als „erledigt“ geschlossen, entsteht in
  derselben Änderung die nächste: gleiche Angaben, Datum um den Rhythmus weiter (am Tag im Monat der ersten
  Fälligkeit, in kürzeren Monaten am Monatsletzten), gleiche Frist in Tagen. Keine Folge, wenn das Ende
  überschritten wäre oder es schon eine gibt. „Storniert“ und Löschen beenden die Wiederholung. Wird die Zahlung
  wieder offen (Zustand zurück, Zuordnung gelöst, Buchung gelöscht), entfällt ihre noch unberührte Folge.
  Rückgängig stellt beides gemeinsam wieder her.
- **Zuordnung:** Das Zeitfenster bleibt wie in erwartungen.md 5.1 (3 Tage vor dem Datum bis 45 Tage danach). Der
  Name passt, wenn ein aussagekräftiges Wort im Verwendungszweck oder Empfänger steht (wie D-232); automatisch
  zugeordnet wird die einzige Buchung mit gleichem Betrag, in der der Name steht – andere Buchungen mit gleichem
  Betrag stören nicht mehr. Der automatische Abgleich läuft weiter nur mit `mail_abgleich` (erwartungen.md).
- **Vorschau:** `GET /api/berichte/vorschau` enthält offene geplante Zahlungen samt Wiederholungen bis zum Ende des
  Zeitraums als Ereignisse mit `quelle = "geplant"`, `konto_id = null`, `rhythmus` (oder `einmalig`) und
  `erwartung_id`; schon fällige stehen am Folgetag. Sie zählen bei jeder Kontenwahl (geplante Zahlungen haben kein
  Konto) und werden nicht mit erkannten Serien abgeglichen: Wer eine schon erkannte Serie zusätzlich plant, sieht
  sie doppelt.
- **Datenmodell:** Tabelle `erwartung_wiederholung` (Rhythmus, Tag, Ende, Vorgänger) als Teil der Objektart
  `erwartung`; Datenbankschema 16, Sicherungsdatei Schemaversion 10 (ältere Sicherungen: ohne Wiederholungen).
- **Prüfung:** `tests/test_geplant_eigen.py`, `tests/test_browser_geplant.py`.

## D-239 Betrieb nur über HTTPS: Tailscale Serve, Skript `kontor-https`

- **Anlass:** Auftrag vom 2026-11-21 im Sammelthread: künftig nur noch über HTTPS arbeiten, mit Tailscale; ein
  Installationsskript für Debian; die Testinstanz bleibt per Skript leicht startbar; gut dokumentiert.
- **Grundsatz bleibt:** Kontor spricht kein TLS (`sicherheit.md` 12, `betrieb.md` 2: `proxy_headers=False`). Am
  Anwendungsserver ändert sich nichts außer einer Warnung beim Start.
- **Weg:** Tailscale Serve auf dem Kontor-Server nimmt HTTPS mit dem Zertifikat des Tailnet-Namens entgegen und
  reicht an Kontor auf 127.0.0.1 weiter. Verworfen: eigener Proxy mit eigener Zertifizierungsstelle (Zertifikat
  auf jedem Gerät installieren) und Let's Encrypt über eine eigene Domain (mehr Einrichtung); Tailscale ist
  vorhanden. Nie Funnel (öffentliches Internet).
- **Skript** `kontor-https` (`betrieb/kontor-https.sh`, Ziel `/usr/local/bin/kontor-https`):
  `einrichten [--tailscale-installieren] [--name <name>] [--test-port <port>]`, `status`, `zurueck`. Reihenfolge
  beim Einrichten: prüfen → Freigabe einrichten (scheitert sie, bleibt Kontor unverändert) → Umgebungsdatei einmalig
  als `*.vor-https` sichern → `KONTOR_HOST=127.0.0.1`, `KONTOR_SITZUNG_COOKIE_SECURE=1`,
  `KONTOR_OEFFENTLICHE_URL=https://<name>` setzen → Neustart → Testinstanz ebenso (Adresse mit Port, Vorgabe
  8443; Umgebungsdatei bei Bedarf aus der Vorlage) → Abfrage über HTTPS. Wiederholbar; `zurueck` stellt genau diese
  drei Variablen aus der Sicherung wieder her und beendet die Freigaben. Die ausgelieferte `kontor.env` bleibt bei
  `0.0.0.0` (betrieb.md 3); umgestellt wird nur die installierte Datei.
- **`KONTOR_OEFFENTLICHE_URL` ist hinter dem Proxy Pflicht:** Kontor sieht nur `http`, der Browser meldet die
  `https`-Herkunft; die Herkunftsprüfung (`sicherheit.md` 4.6) lässt sie nur über die öffentliche Adresse zu. Fehlt
  sie bei `KONTOR_SITZUNG_COOKIE_SECURE=1`, warnt Kontor beim Start.
- **Netzbeschränkung:** `KONTOR_ERLAUBTE_NETZE` sieht hinter dem Proxy nur 127.0.0.1 und schützt nicht mehr; den
  Zugriff regelt das Tailnet (dokumentiert in HTTPS.md).
- **Testinstanz:** `kontor-test` bleibt die Bedienung. Steht in `kontor-test.env` eine `https://`-Adresse, schaltet
  `start`/`neu` die Freigabe (`tailscale serve --bg --https=<port>`) ein, `stop`/`loeschen` aus; `status` und die
  Ausgabe nennen die https-Adresse. Ohne die Zeile unverändert http.
- **Tailscale installieren** nur auf ausdrücklichen Wunsch (`--tailscale-installieren`, offizielles
  Installationsskript); die Anmeldung (`tailscale up`) bleibt ein Schritt von Hand, weil sie einen Browser braucht.
- **Prüfung:** `tests/test_https_skript_eigen.py` (Tailscale und systemctl als Attrappen: Umstellung, Wiederholung,
  Rücknahme, Fehlerfälle, Testinstanz-Skript, Startwarnung, Herkunftsprüfung). Nicht geprüft: ein echter Lauf mit
  Tailscale auf einem Server.
- **Nachtrag Tests (2026-11-21):** `tests/test_https_proxy_eigen.py` prüft den Betrieb hinter einem echten
  TLS-Proxy auf Loopback (für den Lauf erzeugtes Zertifikat): Anmelden, Schreiben, Secure-Cookie, fremde Herkunft,
  fehlende öffentliche Adresse, direkter http-Zugriff ohne Sitzung, Proxy mit ersetztem Host-Kopf – per HTTP-Client
  und im Browser (Desktop, Handy). Dabei behoben: `kontor-https` hängte an eine Umgebungsdatei ohne Zeilenende
  die neue Variable an die letzte Zeile an.

## D-240 Feature saldo-tan: Kontostand auch bei zweischrittig gekennzeichnetem HKSAL (2026-11-22)

- **Anlass:** Eine echte Bank kennzeichnet in HIPINS sowohl HKCAZ als auch HKSAL als „mit TAN-Segment“, antwortet
  auf HKTAN Prozess 4 aber mit 3076 (keine starke Authentifizierung nötig). Kontor schickte HKSAL in diesem Fall
  gar nicht und meldete „Bank meldet keinen Kontostand“.
- **Entscheidung:** Ist HKSAL zweischrittig gekennzeichnet, geht es zusammen mit HKTAN Prozess 4 an die Bank, wie
  der Umsatzabruf. Antwortet die Bank zu HKTAN mit 0030 (TAN nötig) oder 3955 (Freigabe in einer App), bleibt der
  Saldo None; es wird nie eine TAN für den Saldo verlangt oder gesendet (`kontostand.md` 1), der Dialog endet mit
  HKEND wie sonst. Weiterhin genau ein HKSAL je Umsatzabruf (`kontostand.md` 1.2).
- **Diagnose:** Jeder Ausgang ohne Saldo hat jetzt eine Zeile im Diagnoseprotokoll (keine passende Version,
  Freigabe verlangt, Fehlercodes 9xxx – nur die Codes –, kein HISAL, HISAL ohne gebuchten EUR-Saldo); ein
  übernommener Saldo „Saldo: übernommen“ ohne Betrag.
- **Prüfung:** `tests/test_saldo_tan_eigen.py`; die Attrappe aus kontor-tests kennzeichnet HKSAL nicht
  zweischrittig, ihre Tests (M11) laufen unverändert.

## D-241 Feature saldo-tan: PIN über systemd-creds ohne PIN-Datei (2026-11-22)

- **Anlass:** Mit installiertem `pin-eingabe.conf` lud der Dienst die PIN-Datei nicht mehr, Kontor blieb aber bei
  `KONTOR_BANK_PIN_QUELLE=systemd-creds`: Ein Wert aus `EnvironmentFile=` (`kontor.env`) hat in systemd Vorrang
  vor `Environment=` im Drop-in. Jeder Abruf scheiterte mit `bank_pin_fehlt`, die Oberfläche öffnete den
  PIN-Dialog, der die Eingabe mit 409 `pin_quelle_systemd` ablehnte.
- **Entscheidung:** (1) Beim Start warnt Kontor, wenn `bank_pin_quelle = systemd-creds` gilt, im
  Credentials-Verzeichnis aber keine Datei `kontor-bank-pin` liegt, und nennt beide Auswege (PIN-Datei ohne
  Drop-in, oder `KONTOR_BANK_PIN_QUELLE=eingabe` in `kontor.env`). (2) Die Oberfläche öffnet bei `bank_pin_fehlt`
  /`bank_pin_falsch` den PIN-Dialog nur noch bei `pin_quelle = eingabe` (aus `GET /api/sync/status`); bei
  `systemd-creds` erscheint stattdessen eine Fehlermeldung mit dem, was auf dem Server zu tun ist. Das weicht von
  `oberflaeche.md` 15.4 ab und steht in der Meilenstein-Definition des Features.
- **Nicht geändert:** `pin-eingabe.conf` und `kontor.env` sind in `betrieb.md` 3 und 4.2 wörtlich festgelegt; der
  Fehler der Spezifikation ist W-015.

## D-242 Unter „Kategorie“ auch ein Bestandskonto: die Zuordnung wird zur Umbuchung (Sammelbranch `feature/sammel4`)

- **Anlass:** Auftrag vom 2026-11-22: unter „Kategorie“ soll auch ein normales Konto stehen können; dann ist es
  keine Kategoriezuordnung, sondern eine Umbuchung. Umfang: nur die Zuordnung von Hand; Regeln folgen später.
- **Datenmodell unverändert:** Eine Umbuchung ist weiter keine eigene Art, sondern abgeleitet (alle Splits auf
  Bestandskonten, `ist_umbuchung`). Berichte, Lernmodell und Auswertungen schließen sie damit von selbst aus.
- **Schnittstelle:** `PUT /api/buchungen/{id}/kategorie` und `POST /api/buchungen/mehrfach/kategorie` nehmen in
  `kategorie_id` eine Kategorie (Aufwand, Ertrag) oder ein Bestandskonto. Neu, alle optional:
  `konto_id` (das Konto, aus dessen Blatt zugeordnet wird; es bleibt) und – nur einzeln – `gegenbuchung_id`
  (Zahl: genau diese Buchung zusammenführen; `null`: keine zusammenführen; fehlt: automatisch).
  Neu lesend: `GET /api/buchungen/{id}/gegenbuchungen?konto_id=<ziel>[&sicht_konto_id=<blatt>]` →
  `{"kandidaten": [Buchung, …]}`.
- **Welche Seite sich ändert:** der eine Gegensplit (Kategorie, „Unkategorisiert“). Ist die Buchung schon eine
  Umbuchung aus zwei Splits, die Seite ohne Bankumsatz (keine Kennung `bank:<IBAN des Kontos>:…`, nicht
  abgestimmt); tragen beide keinen, entscheidet `konto_id`; tragen beide einen, lässt sich nichts umhängen
  (422 `nicht_kategorisierbar`) – ein echter Bankumsatz verlässt sein Konto nie über die Kategorie.
- **Gegenseite schon da:** Auf dem Zielkonto passt eine Buchung, wenn sie genau zwei Splits hat, die Bankseite
  den Betrag des Gegensplits trägt, die andere Seite noch nicht zugeordnet ist („Unkategorisiert“ oder nur ein
  Vorschlag), sie nicht gesperrt ist, das Datum höchstens `umbuchung_fenster_tage` abweicht und ihre Gegen-IBAN
  (falls bekannt) die IBAN des eigenen Kontos ist. Genau eine: beide werden zu einer Buchung zusammengeführt
  (die zugeordnete bleibt, Bankseite der anderen mit ihrer Split-ID, Kennungen und Tags gehen über). Mehrere:
  409 `gegenbuchung_mehrdeutig` mit `details.kandidaten`; die Oberfläche fragt vorher nach. Bei der
  Mehrfachzuordnung wird bei Mehrdeutigkeit (auch: zwei gewählte Buchungen teilen sich eine Gegenseite) nichts
  geändert (`details.buchung_ids`).
- **Gegenseite kommt später:** Die Synchronisation behandelt eine Umbuchung, deren Seite auf dem abgerufenen
  Konto noch keinen Bankumsatz trägt, als sicheren Treffer, wenn der Betrag stimmt und das Datum höchstens
  `umbuchung_fenster_tage` abweicht – Name und Tag dürfen abweichen (bisher: nur gleicher Tag und passender
  Empfänger, sonst neue Buchung mit Dublettenverdacht). Die Eindeutigkeitsregel bleibt (ein Umsatz, ein Kandidat).
- **Fehlerfälle:** Ziel weder Kategorie noch Bestandskonto → 422 `kategorie_ungueltig`; Ziel = das andere Konto
  der Buchung → 422 `konto_ungueltig`; gesplittet → 422 `nicht_kategorisierbar`; gesperrt → 409
  `buchung_gesperrt`; `gegenbuchung_id` passt nicht oder Ziel ist eine Kategorie → 422 `keine_umbuchung`.
- **Protokoll:** eine Änderung `kategorie_setzen` bzw. `mehrfach_kategorie`, auch mit Zusammenführen; Rückgängig
  stellt beide Buchungen wieder her.
- **Oberfläche:** Die Kategorie-Auswahl zeigt unter den Kategorien den Abschnitt „Umbuchung auf ein Konto“
  (`kategorie-auswahl-konten`; Einträge `kategorie-option-<id>` mit `data-umbuchung="ja"`, ohne das Konto des
  Blatts und ohne geschlossene Konten). Bei mehreren möglichen Gegenseiten fragt `gegenbuchung-dialog`
  (`gegenbuchung-<id>`, `gegenbuchung-keine`, `gegenbuchung-abbrechen`). Die Kategoriespalte zeigt im Blatt eines
  Bestandskontos „Umbuchung → <Konto>“ (Geld geht dorthin) bzw. „Umbuchung ← <Konto>“, sonst wie bisher
  „Umbuchung“. Ziehen einer Buchung auf ein Bestandskonto im Kontenbaum bucht ebenso um.
- **Nicht umgesetzt:** Regeln, Vorlagen und Lernmodell mit einem Konto als Ziel (Regeln folgen); eine
  zusammengeführte Umbuchung wieder trennen (nur über Rückgängig).
- **Prüfung:** `tests/test_umbuchung_zuordnen_eigen.py`, `tests/test_browser_umbuchung.py`.

## D-243 Feature kopfabruf: erst Kopfzeilen, Inhalt nur bei Bedarf; Pflicht-Vorauswahl der Anbieter (2026-11-22)

- **Anlass:** Ein Postfach mit 13 000 Mails; der Abruf lud jede Mail des Zeitraums samt Anhängen in den Spiegel,
  obwohl die Erkennung nur Bestell- und Zahlungsmails braucht. Der Absenderfilter des Postfachs griff erst nach dem
  Herunterladen.
- **Anbieter-Beschreibungen:** Pflichtangabe `[vorauswahl]` mit `absender` und/oder `betreff` (je ein Ausdruck;
  mit beiden müssen beide treffen). Sie bestimmt, welche Mails zum Anbieter gehören (`Anbieter.gehoert(absender,
  betreff)`), und damit, welche Inhalte geladen werden. Das bisherige `absender` auf oberster Ebene bleibt als
  Kurzform gültig, beides zugleich ist ein Fehler, ohne beides wird die Datei übergangen. Die mitgelieferten
  Beschreibungen tragen nur `absender` (Verhalten unverändert, Vergleich mit der Referenzerkennung grün).
- **Einstellung:** `mail_nur_koepfe` (`KONTOR_MAIL_NUR_KOEPFE`), Vorgabe aus, in `kontor.env` und `kontor-test.env`
  an. Aus: Abruf wie bisher über `nachrichten()`.
- **Abruf mit Einstellung:** Plugins mit `kann_koepfe` liefern `koepfe(postfach, seit)` (Kennung, Zeit, Absender,
  Betreff, Fundstelle `ort`) und `inhalte(postfach, koepfe)`. IMAP holt die Köpfe mit
  `BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT)]`, Inhalte mit `BODY.PEEK[]` (keine Markierung ändert sich);
  `ort` ist `<UIDVALIDITY>:<UID>`, bei geänderter UIDVALIDITY wird über die Message-ID gesucht. Das Mock-Plugin kann
  es ebenfalls. Gleich mitgeladen wird der Inhalt einer neuen Mail, wenn die Vorauswahl eines Anbieters trifft oder
  – mit `mail_bestellnummer` – ihr Betreff eine Kennung eines Anbieters mit `bank.alle_mails` trägt. Alle anderen
  stehen im Spiegel mit leerem Text, ohne Rohfassung und `inhalt = 0`. Kopf-Mails, die eine neue oder geänderte
  Vorauswahl jetzt betrifft, lädt jeder Abruf nach (ihre Kennungen werden danach neu gesucht). Scheitert das Laden
  der Inhalte, scheitert der Abruf des Postfachs wie bisher; gespeichert wird nichts.
- **Bei Bedarf:** `POST /api/mail/nachrichten/{id}/inhalt` lädt den Inhalt einer Kopf-Mail nach (Antwort `id`,
  `text`, `nachgeladen`; ist er schon da, geschieht nichts) und lässt danach den Abgleich laufen wie nach einem
  Abruf. Fehler: 404 unbekannte Mail, 409 `geheimnisse_gesperrt`, `anmeldung_erforderlich`,
  `mail_nicht_mehr_vorhanden` (im Postfach gelöscht), sonst der Code des Plugins. `POST …/buchung` (von Hand
  anhängen) lädt vorher nach. Das Mail-Blatt lädt beim Lesen einer Kopf-Mail nach („Erneut laden“ nach einem
  Fehler).
- **Schnittstelle:** Einträge von `GET /api/mail/nachrichten` tragen `ohne_inhalt: true` nur bei Kopf-Mails; das
  Abrufergebnis je Postfach trägt `nachrichten_ohne_inhalt` und `nachrichten_nachgeladen` nur mit der Einstellung.
- **Datenbank:** Schema 17, Spalten `mail_nachricht.inhalt` (Vorgabe 1) und `ort`; der Spiegel bleibt
  Betriebszustand (nicht im Protokoll, nicht in der Sicherung).
- **Grenzen:** Die Suche im Mail-Blatt findet in Kopf-Mails nur Absender und Betreff. Die Bestellnummer-Regel sieht
  in Kopf-Mails nur den Betreff. Eine im Postfach gelöschte Kopf-Mail lässt sich nicht mehr lesen.
- **Prüfung:** `tests/test_kopfabruf_eigen.py` (Attrappen-Plugin, IMAP gegen eine Loopback-Attrappe, Vorauswahl),
  `tests/test_browser_kopfabruf.py`.

## D-244 Feature postfach-loeschen: Postfach in der Oberfläche löschen, Bestand bleibt stimmig (2026-11-22)

- **Anlass:** Ein Postfach ließ sich nur über `DELETE /api/mail/postfaecher/{id}` löschen, nicht in der Oberfläche.
- **Oberfläche:** Abschnitt „Postfach löschen“ auf der Seite `/mail/postfaecher/{id}` mit Knopf `postfach-loeschen`
  und Rückfrage (`bestaetigen-dialog`). Sie nennt die Zahl der gespeicherten Mails und was bleibt. Nach dem Löschen
  geht es zu `/einstellungen?bereich=mail`; Rückgängig wie jede Aktion.
- **Was entfällt (eine Änderung `postfach_loeschen`):** Postfach; wie bisher Spiegel, Betriebszustand und
  Anmeldegeheimnisse (`geheimnisse.verwaiste_entfernen`); neu die Benachrichtigungen mit dem Verweis auf die Seite
  des Postfachs (sonst führten sie ins Leere und würden ggf. noch zugestellt) und die gemerkten Kennungen seiner
  Mails (`bestellmail_nummer`).
- **Was bleibt:** Dokumente an Buchungen, erwartete Zahlungen (ihre Mailverweise zeigen dann „nicht mehr im
  Spiegel“, wie schon vorgesehen) und der Vermerk `bestellmail` – nach dem Neuanlegen erkennt der Abgleich dieselben
  Mails an ihrer Kennung und hängt sie nicht doppelt an. Im Postfach beim Anbieter wird nichts gelöscht.
- **Kein Löschen während eines Abrufs:** `DELETE` hält die Abrufsperre; läuft ein Abruf, 409 `mail_abruf_laeuft`.
  So schreibt kein laufender Abruf mehr Mails eines gelöschten Postfachs in den Spiegel.
- **Rückgängig:** stellt das Postfach wieder her; Spiegel, Anmeldung und Benachrichtigungen kommen nicht zurück
  (Betriebszustand), ein neuer Abruf holt die Mails wieder.
- **Prüfung:** `tests/test_postfach_loeschen_eigen.py`, `tests/test_browser_postfach_loeschen.py`.

## D-245 Abnahme M29 (Bankabruf über FinTS/camt): Nachbesserungen

- **Anlass:** Die Abnahmetests zu Meilenstein 29 (kontor-tests `8304dfb`) liefen erstmals gegen die Anwendung.
- **Entscheidung:**
  1. **Naht `kontor.sync.kennungen_als_alt_markieren(config)`** (E-264, `bankzugang.md` 3.1): ersetzt die Menge
     der „alten“ Kennungen durch alle jetzt bekannten Bank-Kennungen (an Buchungen und gemerkte); Betriebszustand,
     kein Protokoll, mehrfach aufrufbar, legt die Datenbank bei Bedarf an.
  2. **Diagnoseschalter gilt ab dem Start:** Die gespeicherte Einstellung wird beim Start der Instanz gelesen,
     nicht erst beim ersten Zugriff auf den Bankzugang.
  3. **TAN-Verfahren ohne Angabe „erlaubt“:** Nennt die Bank keine zugelassenen Verfahren (Rückmeldung 3920
     fehlt), liefert `tan_verfahren()` alle Zwei-Schritt-Verfahren der Bankparameter (`bankzugang.md` 2.1).
  4. **Zweite TAN im selben Lauf:** Verlangt die Bank nach der TAN zur Anmeldung für den Umsatzabruf eine weitere
     TAN, wird die erste Anforderung als beantwortet abgeschlossen und eine neue angelegt; der Lauf wartet weiter.
- **Offen als Widerspruch:** W-016 (600 Zeilen), W-017 (Benutzerparameter ohne neue Version).
- **Prüfung:** `tests/app/m29` ohne Browsertests: 183 bestanden, 2 offen (W-016, W-017).

## D-246 Abnahme M30 (Kontor-Ausdrücke, Regeleditor): Nachbesserungen

- **Anlass:** Die Abnahmetests zu Meilenstein 30 (kontor-tests `f2e6273`) liefen erstmals gegen die Anwendung.
- **Entscheidung:**
  1. `GET /api/ausdruck/sprache`: die Datumswörter stehen unter `schluesselwoerter.datum` (Aufbau frei, E-272),
     nicht mehr als eigenes Feld auf oberster Ebene (Schema ohne Zusatzfelder); `schluesselwoerter.logik` nennt
     die Schlüsselwörter. Die Vervollständigung liest sie dort.
  2. `POST /api/ausdruck/pruefen`: `zusammenfassung` auch im Kontext `regel`; jedes als Freitext gelesene Wort
     bekommt einen Hinweis (mit „Meinten Sie …?“, wenn es einem Feldnamen ähnelt); eine Dauer mit unbekannter
     Einheit (`-5x`) ist `einheit_unbekannt`; zweistellige Jahre richten sich nach dem Bezugstag (`stichtag`);
     Ausdrücke über 4000 Zeichen sind 200 mit `zu_lang` statt 422 `validierung` (die Körperprüfung lässt
     längere Texte durch).
  3. `POST /api/regeln/test`: `wirkung` ist ein einzelner Wert (`RegelWirkung`), nicht mehr eine Liste.
  4. Regeleditor: der Anwenden-Knopf zählt bei „n × Kategorie“ nur die Buchungen, deren Kategorie mit der Vorgabe
     gesetzt wird (`neu`); abweichende bietet das Fenster an. Die leere Tag-Liste `regel-tags` bleibt sichtbar.
     Der Knopf „Bearbeiten…“ der Regelliste heißt für Hilfstechnik „Bearbeiten: Regel <Name>“ (sichtbarer Text
     am Anfang des Namens).
  5. Kontoblatt: Filter ohne Entsprechung im Ausdruck (`filter-alt-<name>`) stehen unter dem Ausdrucksfeld und
     sind auch bei eingeklapptem Baukasten sichtbar; übernommene alte Parameter werden beim Öffnen als
     `filter=…` in die Adresse geschrieben.
- **Offen:** Die Handy-Fälle von `m8::test_filter` erwarten das Filterfeld am Handy sichtbar; seit D-236 ist es
  dort eingeklappt (`ansicht-umschalten`). Das beschreibt Definition 4 (Paket 4) und zieht der Test-Thread dort
  nach – kein Widerspruch zu M30.
- **Prüfung:** `tests/app/m30` 418/418 grün; frühere Filtertests (M8, M12, M17, M26, M28) am Desktop grün.

## D-247 Abnahme M31 (übrige Features vor sammel3): Nachbesserungen

- **Anlass:** Die Abnahmetests zu Meilenstein 31 (kontor-tests `be6d7d8`) liefen erstmals gegen die Anwendung.
- **Entscheidung:**
  1. `GET /api/lernmodell/einstellungen` liefert nur `schwelle_promille` und `regeln_automatisch`; ob der Server
     neue Buchungen automatisch vorschlägt (`lernmodell_automatisch`), steht in der Übersicht.
  2. Erklärung je Buchung (E-280): zusätzlich `vorhersage` (wie `POST /api/lernmodell/vorhersage`); jedes
     Merkmal trägt immer `anzahl_kategorie`, `anzahl_vergleich` (0 ohne beste/zweite Kategorie) und
     `faktor_promille` (`null` ohne Vergleich).
  3. Monatsbericht (E-282): Kennzahlen `konto_ids`, `ausgaben` (netto), `einnahmen`, `fest`, `variabel`,
     `umbuchungen` auf oberster Ebene.
  4. FinTS: Lassen sich die gespeicherten Bank- und Benutzerparameter nicht wieder lesen (die Bibliothek scheitert
     an Benutzerparametern ohne Kontoeinträge), beginnt der Dialog ohne sie (Diagnosezeile).
  5. Oberfläche: `/berichte/monat` wird vor der Wahl des Tabs auf `/berichte?art=monat` umgeschrieben (ein Tab);
     eine leere Postfachliste zeigt „Noch kein Postfach eingerichtet.“
- **Offen als Widerspruch:** W-018 bis W-022 (an den Test-Thread übergeben).
- **Prüfung:** `tests/app/m29` ohne Browser 211/211 (mit Attrappentests); `tests/app/m31` ohne Browser 88/91
  (W-018, W-019, W-020 offen; `betrag` in `angehaengt` kommt mit Definition 4).

## D-248 Abnahme M32 (Sammelbranch sammel3): Nachbesserungen

- **Anlass:** Die Abnahmetests zu Meilenstein 32 (kontor-tests `752b407`) liefen erstmals gegen die Anwendung.
- **Entscheidung:**
  1. Wiederholung geplanter Zahlungen: nach außen (Protokoll, Inhaltsprüfsumme) nur `{rhythmus, bis}`; Tag der
     ersten Fälligkeit und Vorgängerin bleiben in der gespeicherten Protokollform für Rückgängig.
  2. Eine Folge gilt nur als „unberührt“ (entfällt beim Wiederöffnen), wenn sie seit dem Anlegen unverändert ist:
     offen, ohne Buchungen, Mails, Dokumente und mit den Angaben, die das Anlegen aus der Vorgängerin übernommen
     hätte.
  3. Mail-Liste: `stand` zählt ohne `suche` (E-299).
  4. `POST /api/mail/nachrichten/{id}/buchung`: Prüfreihenfolge 404 Nachricht → 422 Körper → 404 Buchung; ein
     zweiter Aufruf mit derselben Buchung gibt das vorhandene Dokument zurück, statt ein zweites anzulegen.
  5. Oberfläche: `empfaenger-treffer` trägt `data-anzahl`; die Einträge der Spaltenwahl sind
     `menuitemcheckbox` mit `aria-checked` (E-306).
- **Offen als Widerspruch:** W-023 bis W-027 (an den Test-Thread übergeben).

## D-249 Gesamtlauf der Abnahme: Personen-Tags beim Einspielen, Lerndaten

- **Anlass:** Gesamtlauf aller Abnahmetests (kontor-tests `fca9a20`) gegen `feature/sammel3`.
- **Entscheidung:**
  1. Beim Einspielen werden „Torsten“/„Tina“ nur bei Sicherungen von vor der Umstellung auf „B-<Name>“
     (`app_version` vor 0.35, Unlesbares gilt als älter) umbenannt (D-223: „ältere Sicherungen“). Eine
     Rundreise mit gewöhnlichen Tags dieser Namen bleibt unverändert.
  2. Mock-Lerndaten: Prüfbuchungen stehen auf dem technischen Konto „Unkategorisiert“ (Kennung
     `kontor:unkategorisiert`), nicht auf einem zweiten gleichnamigen Eigenkapitalkonto.
- **Offen als Widerspruch:** W-028 bis W-031 (an den Test-Thread übergeben).

## D-250 Gesamtlauf der Browsertests: Gruppierung, Kontoauswahl in Kategorien, Esc im Filterfeld

- **Anlass:** Browsertests aller Meilensteine gegen `feature/sammel3`.
- **Entscheidung:**
  1. Die Gruppe der Gruppierungsknöpfe heißt wieder „Buchungen gruppieren“ (`oberflaeche.md` 37).
  2. Kontoansicht einer Kategorie: `filter-konto` (Bestandskonten, Pfad als Beschriftung) steht im Baukasten und
     bildet auf `kategorie_id` ab (22.2, E-274); dort wird `kategorie_id` nicht in den Ausdruck übernommen und
     erscheint nicht als „Weitere Filter“.
  3. Esc im Filterfeld führt immer in die Liste zurück, auch wenn die Vervollständigung offen war (D-167).
- **Offen:** `m15::test_details_vorschlag_und_kandidaten` und `m8::test_seiten_im_mindestumfang` (beide schon vor
  diesem Auftrag auf main rot; der zweite wartet auf eine Erfolgsmeldung, die seit D-234 ausgeliefert aus ist).

## D-251 Sicherung und `passwort-setzen` ohne Credentials auch bei PIN-Quelle systemd-creds (2026-11-22)

- **Anlass:** Mit `KONTOR_BANK_PIN_QUELLE=systemd-creds` in `kontor.env` scheiterte `kontor-sicherung.service` mit
  „Für bank_pin_quelle „systemd-creds“ muss credentials_verzeichnis ($CREDENTIALS_DIRECTORY) gesetzt sein“. Die
  Unit bekommt bewusst keine Credentials. Weil das Update vorher eine Sicherung anlegt, brach auch jedes Update aus
  der Oberfläche ab („systemctl start kontor-sicherung.service … Rückgabecode 1“).
- **Entscheidung:** Werkzeuge außerhalb des Dienstes, die nie mit der Bank sprechen (`python -m kontor.sicherung`,
  `python -m kontor.anmeldung passwort-setzen`), lesen die Konfiguration über `KontorConfig.fuer_werkzeug`: Ohne
  `$CREDENTIALS_DIRECTORY` gilt eine PIN-Quelle `systemd-creds` für sie als `eingabe`. Alle anderen Prüfungen
  bleiben. Der Dienst selbst prüft unverändert streng (python-api.md 13.1).
- **Übergang:** Die schon installierte Fassung hat den Fehler noch. Für das Update auf die behobene Fassung die
  Zeile in `/etc/kontor/kontor.env` vorübergehend auskommentieren und danach wiederherstellen.
- **Prüfung:** `tests/test_sicherung_pinquelle_eigen.py`.

## D-252 Feature mail-fortschritt: Fortschritt des Abrufs, Abruf im Hintergrund, alle Kopfzeilen neu abrufen (2026-11-22)

- **Anlass:** Ein großes Postfach braucht für den Abruf Minuten; die Oberfläche zeigte nur „Mails werden
  abgerufen…“. Ältere Mails außerhalb des ersten Abrufzeitraums kamen nur über Löschen und Neuanlegen des
  Postfachs dazu.
- **Fortschritt:** Der Mail-Dienst führt je Postfach den Schritt (`wartet`, `anmelden`, `nachrichten`, `koepfe`,
  `inhalte`, `speichern`, `fertig`, `fehlgeschlagen`, `anmeldung_erforderlich`) und, wo bekannt, `erledigt`/`gesamt`.
  Plugins mit `kann_koepfe` melden über das neue optionale Argument `fortschritt(erledigt, gesamt)` von `koepfe` und
  `inhalte` (IMAP nach je 200 UIDs). Der Stand lebt nur im Arbeitsspeicher, auch für Abrufe des Planers.
- **`GET /api/mail/abruf/stand`:** `laeuft`, `nur_koepfe` (Einstellung), nach dem ersten Abruf zusätzlich
  `alle_koepfe`, `gestartet_am`, `beendet_am`, `postfaecher` (je `postfach_id`, `adresse`, `schritt`, `erledigt`,
  `gesamt`), `ergebnis` (Antwort des Abrufs) und `fehler` (`code`, `meldung`).
- **`POST /api/mail/abruf`:** neue Abfrageparameter `hintergrund=ja|nein` (ja: Antwort sofort mit dem Stand, der
  Abruf läuft weiter; 409 `mail_abruf_laeuft` wie bisher) und `alle_koepfe=ja|nein` (Suche ab dem 2. 1. 1970 statt
  ab dem letzten Erfolg; vorhandene Mails bleiben, fehlende kommen als Kopfzeilen bzw. – Vorauswahl – vollständig
  dazu; nur mit `mail_nur_koepfe`, sonst 409 `mail_nur_koepfe_aus`). Andere Werte: 422. Ohne Parameter wie bisher.
- **Oberfläche (Mail-Blatt):** „Mails abrufen“ startet im Hintergrund und zeigt in `mail-fortschritt` je Postfach
  Schritt, Zahl und Balken (`mail-fortschritt-<id>`, `data-schritt`), danach das Ergebnis wie bisher. Läuft beim
  Öffnen schon ein Abruf, folgt die Seite ihm. Knopf `mail-alle-koepfe` „Alle Kopfzeilen neu abrufen …“ mit
  Rückfrage, nur mit `mail_nur_koepfe` sichtbar.
- **Prüfung:** `tests/test_mail_fortschritt_eigen.py`, `tests/test_browser_mail_fortschritt.py`.

## D-253 Testumbau: Tests und Spezifikation im Anwendungs-Repository, Core-Tests und TDD (2026-11-23)

- **Anlass:** Auftrag vom 2026-11-23. Die strikte Trennung von kontor-app und kontor-tests (Meilenstein-Definition,
  Test-Thread, Widersprüche als Text) kostete zu viele Tokens und machte die Zyklen langsam; der Volllauf der
  Abnahmetests dauerte über 25 Minuten.
- **Entscheidung:** kontor-tests ist aufgegeben. `spec/` (Spezifikation), `legacy-tests/` (eingefrorene Referenz),
  `gesamt-tests/` (gekürzte Abnahmetests) und `tests/core/` (Core-Tests, vor dem Feature geschrieben, zusammen unter
  30 Sekunden) liegen in kontor-app. Die Gesamttests laufen nur in der CI auf main, in parallelen Jobs mit je
  unter 5 Minuten (vereinbart zwei, wegen der langsameren Runner vier), vor dem Release (ändert den Ablauf von D-105: das Release hängt an den Testjobs).
- **Ersetzt:** die Rollentrennung in `CLAUDE.md`; `WIDERSPRUECHE.md` und `ERGEBNIS.md` werden nicht fortgeführt
  (das Ergebnis steht im CI-Lauf). Entscheidungen der Spezifikation (`spec/api/entscheidungen.md`, `E-…`) bleiben
  als Bestand; neue Entscheidungen stehen hier.
- **Einzelheiten, Messungen, Auswahlregel und geänderte Tests:** `TESTUMBAU.md`.

## D-254 Kontoblatt: Zeilenfarbe nach Status (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Bestätigte und abgeglichene Buchungen stehen auf dem kontrastreichen Grund
  (im dunklen Thema schwarz), die übrigen Status sind farbig hinterlegt: Importiert rot, Vorläufig gelb.
- **Entscheidung:** Ersetzt die Markierung des Bearbeitungsstands aus D-130 (grün „kategorisiert“, grau
  „importiert“, grün-grau „abgeglichen“). `data-markierung` der Zeile folgt nur noch dem Status:
  `abgeglichen` (Status „Abgeglichen“ oder abgestimmt), sonst der Status selbst (`importiert`, `vorlaeufig`,
  `bestaetigt`). Ob die Buchung kategorisiert ist, spielt für die Farbe keine Rolle mehr.
- **Darstellung:** `importiert` roter Streifen links und rote Tönung, `vorlaeufig` gelber Streifen und gelbe Tönung;
  `bestaetigt` und `abgeglichen` ohne Streifen auf weißem (hell) bzw. schwarzem (dunkel) Grund. Hover und Auswahl
  überdecken die Tönung wie bisher; abgeglichene Zeilen behalten das Schloss.
- **Tests:** `tests/test_browser_spalten.py::test_markierung_der_zeilen` und
  `gesamt-tests/.../m22/test_m22_oberflaeche.py::test_markierung_rangfolge_und_darstellung` auf die neuen Werte
  umgestellt (`TESTUMBAU.md`, „Geänderte Tests“).

## D-255 Feature mail-schlank: Mails komprimiert, Spiegel ohne zweite Kopie, Datei gibt Platz zurück (2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24. Die Datenbank des Echtbetriebs war 235 MB groß und die Testinstanz ließ sich
  nicht mehr einrichten (Platte voll beim Kopieren). Messung: 110 MB Rohfassungen im Mail-Spiegel (990 Mails mit
  Inhalt von 6.543), 95 MB Mail-Dokumente (754), keine freien Seiten. zlib verkleinert die Mail-Dokumente des
  Bestands von 95,2 auf 16,8 MB. (Nummer D-255, weil D-254 auf `feature/status-farben` vergeben ist.)
- **Entscheidung:**
  - `dokument_inhalt` speichert E-Mails komprimiert (Spalte `verfahren`: `zlib`, `''` unkomprimiert, `NULL`
    Bestand vor Schema 18). PDF und Bilder bleiben unverändert. Prüfsumme, Größe, Auslieferung und Sicherung
    beziehen sich auf die Originalbytes (`kompression.py`, `dokumente.inhalt_bytes`/`inhalt_speichern`).
  - Die Rohfassung im Spiegel ist komprimiert (`mail_nachricht.roh_verfahren`). Wird die Mail als Dokument
    angehängt (von Hand, Mail-Abgleich, Bestellnummer), entfällt die Rohfassung im Spiegel; `roh_sha256` verweist
    auf den Inhalt des Dokuments (`dokumente.spiegel_verweisen`, gelesen über `spiegel_roh`). Inhalte werden nie
    gelöscht, der Verweis bleibt also gültig.
  - Das Format der Sicherung bleibt (unkomprimierte Inhalte, `SCHEMAVERSION` unverändert): die ZIP-Datei
    komprimiert ohnehin, und ältere Kontor-Versionen können neue Sicherungen weiter lesen.
  - Neue Datenbanken mit `auto_vacuum = INCREMENTAL`. Beim Start stellt `db.mails_packen` den Altbestand um
    (stückweise, je 50 Zeilen eine Transaktion), `db.verkleinern` stellt eine Datenbank ohne `auto_vacuum` einmal
    mit `VACUUM` um und gibt danach mit `incremental_vacuum` Platz zurück, sobald mehr als ein Viertel der Seiten
    frei ist. Scheitert das (Platte voll, Datenbank belegt), startet Kontor trotzdem; der nächste Start versucht
    es erneut.
- **Verworfen:** Rohfassungen nach einer Frist löschen und bei Bedarf aus dem Postfach nachladen. Nach Kompression
  und Verweis bleiben dafür nur wenige MB übrig; dagegen stünden ein zusätzlicher Zustand, wiederholtes Nachladen
  und Mails, die im Postfach schon gelöscht sind.
- **Schema 18.** Lasttest mit 990 synthetischen Mails (123 MB): Umstellung beim Start 1,3 s, danach 9,4 MB.
- **Tests:** `tests/core/test_mail_schlank.py`.

## D-256 Testinstanz: Datenkopie mit Platzprüfung und ohne doppelten Platzbedarf (2026-11-24)

- **Anlass:** `kontor-test start` scheiterte mit „Die Datenbank ließ sich nicht kopieren (OperationalError)“: Kopie,
  `VACUUM` mit Rücksprungjournal und die noch vorhandene alte Kopie brauchten zusammen mehr als die 406 MB freien
  Platzes (Datenbank 235 MB).
- **Entscheidung** (`testinstanz.daten_kopieren`): vorher den freien Platz prüfen (die alte Kopie zählt als frei)
  und mit einer verständlichen Meldung abbrechen; danach die alte Kopie entfernen (die Testinstanz ist gestoppt).
  Geheimnisse mit `PRAGMA secure_delete` überschreiben und freie Seiten mit `incremental_vacuum` entfernen, wenn die
  Datenbank `auto_vacuum = INCREMENTAL` hat (D-255); sonst wie bisher `VACUUM`. Bedarf damit etwa das 1,1-fache
  (sonst 2,1-fache) der Datenbank. SQLite-Fehler werden mit ihrer Meldung ausgegeben (sie nennen nur Ursachen,
  keine Inhalte).
- **Tests:** `tests/core/test_testinstanz_platz.py`.

## D-257 Zuordnung von Hand macht eine importierte Buchung vorläufig (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: „Wird eine Buchung einer Kategorie zugeordnet, ist sie automatisch Vorläufig
  bestätigt.“ Mit D-254 heißt das: Rot = noch nicht zugeordnet, Gelb = zugeordnet, ohne Farbe = bestätigt.
- **Entscheidung:** Eine Buchung im Status `importiert` wird `vorlaeufig`, wenn der Anwender sie zuordnet:
  Kategorie oder Bestandskonto setzen (einzeln, mehrfach), Splits ersetzen, Vorschlag annehmen (einzeln, mehrfach);
  nur wenn danach kein Split auf „Unkategorisiert“ liegt. `vorlaeufig`, `bestaetigt` und `abgeglichen` bleiben.
- **Nicht (Annahme, im Auftrag offen):** offene Vorschläge von Regel und Lernmodell, Split-Vorlagen und Importe –
  ein Vorschlag ist noch keine Zuordnung, erst das Annehmen. Das Ablehnen ändert den Status nicht.
- **Bestätigen (Annahme):** Der Übergang `vorlaeufig → bestaetigt` ist jetzt zulässig (ergänzt E-008); „Als
  <Person> bestätigen“ setzt importierte und vorläufige Buchungen auf `bestaetigt` (ändert D-159). Das gilt
  damit auch für vorläufige Kreditraten.
- **Rücknahme (Annahme):** Der Status geht nie von selbst auf `importiert` zurück, auch nicht beim Zuordnen auf
  „Unkategorisiert“; Rückgängig stellt Zuordnung und Status zusammen wieder her.
- **Altbestand (Annahme):** Beim ersten Start mit dieser Fassung werden importierte Buchungen ohne Split auf
  „Unkategorisiert“ und ohne offenen Vorschlag einmalig `vorlaeufig` (Merker `meta.status_vorlaeufig`, außerhalb
  des Änderungsprotokolls). Sicherungen älterer Fassungen werden beim Einspielen nicht umgestellt.
- **Tests:** `tests/core/test_status_farben.py`; angepasste Tests in `TESTUMBAU.md` („Geänderte Tests“). Auf dem
  Branch liefen auftragsgemäß nur die Core-Tests und einmal die eigenen Tests ohne Browser; weitere Gesamttests,
  die eine importierte Buchung zuordnen und danach `importiert` erwarten, zeigt erst die CI auf main.

## D-258 Bestätigen zeigt den Status sofort (Feature `status-farben`, 2026-11-24)

- **Anlass:** Rückmeldung vom 2026-11-24: Nach „b“ ändert sich der Status erst nach etwa einer halben Sekunde.
- **Ursache:** Die Aktion besteht aus fünf Anfragen nacheinander (höchste Änderung lesen, Tag setzen, Status setzen,
  Änderungen für Rückgängig lesen, Liste neu laden); die Zeile wurde erst nach der letzten neu gezeichnet.
- **Entscheidung:** Die Zeilen der betroffenen Buchungen (importiert oder vorläufig) zeigen `bestaetigt` (Text,
  `data-status`, `data-markierung`) sofort beim Auslösen; die Anfragen laufen wie bisher danach. Schlägt die
  Aktion fehl, wird die Anzeige zurückgenommen. Der Personen-Tag erscheint weiterhin erst mit dem Neuladen.
- **Prüfung:** nur gelesen und auf Syntax geprüft; kein Browsertest gelaufen (auf dem Branch laufen nur Core-Tests).

## D-259 Ausgewählte Zeilen: Status an der Schriftfarbe erkennbar (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Importierte und vorläufige Buchungen sollen auch markiert anders aussehen,
  mit farbiger Schrift. Bisher überdeckte die Auswahlfarbe die Tönung aus D-254; nur der Streifen links blieb.
- **Entscheidung:** In ausgewählten Zeilen ist die Schrift bei `importiert` rot und bei `vorlaeufig` gelbbraun
  (hell) bzw. gelb (dunkel), jeweils mit ausreichendem Kontrast auf der Auswahlfarbe. Nicht ausgewählte Zeilen
  bleiben wie in D-254 (Tönung, normale Schrift). Beträge behalten ihre eigene Farbe (negativ rot).
- **Prüfung:** nicht im Browser angesehen; Kontrast nur gerechnet (jeweils etwa 4,7 bis 5,9 zu 1).

## D-260 Bestätigen roter Buchungen verlangt eine Kategorie oder ein Konto (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: „Bestätigt man rote Buchungen, sollte immer eine Kategorie/Konto gefordert
  werden.“
- **Entscheidung (Lesart):** Gefordert wird die Zuordnung, wo sie fehlt: Bei importierten Buchungen mit einem
  Split auf „Unkategorisiert“ öffnet „Als <Person> bestätigen“ (Kürzel b, Kontextmenü, Einzelheiten) zuerst die
  Kategorieauswahl mit Bestandskonten. Die Wahl gilt für alle solchen Buchungen der Auswahl; danach wird
  bestätigt. Ohne Wahl wird keine der gewählten Buchungen bestätigt. Rote Buchungen, die schon eine Kategorie
  tragen (offener Vorschlag, Split-Vorlage, Import), werden wie bisher ohne Nachfrage bestätigt.
- **Nur Oberfläche:** Die REST-Schnittstelle lehnt das Setzen von `bestaetigt` weiterhin nicht ab; auch die
  Statusauswahl in der Zeile und „Mehrere ändern“ fragen nicht nach.
- **Rückgängig:** Zuordnen und Bestätigen sind zwei Änderungen (zweimal Strg+Z).
- **Prüfung:** nur gelesen und auf Syntax geprüft; kein Browsertest gelaufen.

## D-261 Automatisch zugeordnet ist vorläufig, von Hand zugeordnet ist bestätigt (Feature `status-farben`, 2026-11-24)

- **Anlass:** Präzisierung vom 2026-11-24: „Außer es gibt schon einen Vorschlag für die Kategorie. Dann wird diese
  genommen. Wird händisch eine Kategorie vergeben, ist die Buchung automatisch bestätigt.“
- **Ersetzt** die Regel aus D-257 (von Hand zugeordnet = vorläufig) und deren Annahmen zu Auslöser, Rücknahme und
  Altbestand. Aus D-257 bleibt der zulässige Übergang `vorlaeufig → bestaetigt` und dass Bestätigen auch vorläufige
  Buchungen erfasst.
- **Entscheidung:** Rot (`importiert`) = noch nicht zugeordnet; Gelb (`vorlaeufig`) = automatisch zugeordnet;
  ohne Farbe (`bestaetigt`) = von Hand zugeordnet oder bestätigt.
  - Vorschlag von Regel oder Lernmodell und Split-Vorlage (bei der Synchronisation und beim Anwenden): `importiert`
    wird `vorlaeufig` (Folgerung aus dem ersten Auftrag; sonst entstünde Gelb nur noch bei Kreditraten).
  - Zuordnung von Hand (Kategorie oder Bestandskonto, einzeln und mehrfach, Splits ersetzen) und Vorschlag
    annehmen: `importiert` und `vorlaeufig` werden `bestaetigt`. Das gilt auch für vorläufige Kreditraten.
  - Vorschlag ablehnen: `vorlaeufig` wird wieder `importiert`.
  - Bestätigen einer Buchung mit offenem Vorschlag übernimmt dessen Kategorie ohne Nachfrage (bestehendes
    Verhalten); die Nachfrage aus D-260 kommt nur ohne Zuordnung.
- **Personen-Tag (Annahme):** Die Zuordnung von Hand setzt nur den Status, nicht den Tag „B-<Name>“; den setzt
  weiterhin nur „Als <Person> bestätigen“.
- **Altbestand:** Einmalig (Merker `meta.status_farben`) werden importierte Buchungen ohne Split auf
  „Unkategorisiert“ `vorlaeufig`, auch mit offenem Vorschlag. Bestätigt wird nichts von selbst, weil nicht mehr
  erkennbar ist, ob eine alte Zuordnung von Hand kam.
- **Tests:** `tests/core/test_status_farben.py` umgestellt (`tests/core/AENDERUNGEN.md`). Der Weg über die
  Synchronisation hat keinen Core-Test. **Offen vor dem Merge:** Tests in `tests/` und `gesamt-tests/`, die nach
  einem Vorschlag, einer Split-Vorlage oder einer Zuordnung von Hand den bisherigen Status erwarten, sind noch
  nicht angepasst (auf dem Branch laufen auftragsgemäß nur die Core-Tests).

## D-262 Bestätigungs-Tag heißt „<Name>-Bestätigt“ und steht hinten (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Das Tag bleibt, heißt aber „<Benutzer>-Bestätigt“ und wird in der Oberfläche
  immer nachrangig gezeigt, damit es andere Tags nicht verdrängt. (Die zuvor erwogene Anzeige eines Kürzels am
  Status ist damit verworfen und nicht umgesetzt.)
- **Entscheidung:** Ersetzt den Namen aus D-223 („B-<Name>“). Vorhandene Tags „B-Torsten“/„B-Tina“ werden beim
  Start in einer Änderung umbenannt (wie in D-223: gibt es das neue Tag schon, wandern die Zuordnungen dorthin),
  ebenso beim Einspielen einer Sicherung. In der Spalte Tags des Kontoblatts stehen Bestätigungs-Tags hinter
  allen anderen. `data-bestaetigt` und `data-person` nennen weiter den Namen der Person.
- **Folge:** Regeln, die das Tag vergeben, und Zuordnungen an Empfängern wandern mit. Gespeicherte Filter oder
  Regelausdrücke, die den Tag-Namen „B-…“ als Text enthalten, werden nicht umgeschrieben.
- **Tests:** Core-Test `test_bestaetigungs_tags_heissen_name_bestaetigt`; angepasste Tests in `TESTUMBAU.md`.

## D-263 „Verdächtig“ als Feld des Filterausdrucks (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Nach „Verdächtig“ soll man filtern können. Erwogen war ein echtes Tag;
  abgestimmt ist der Filter ohne Tag, weil der Verdacht von anderen Buchungen desselben Empfängers abhängt und ein
  gespeichertes Tag nach jeder Änderung nachgeführt werden müsste (mit Einträgen im Änderungsprotokoll).
- **Entscheidung:** Der Filterausdruck kennt das Wahrheitsfeld `verdächtig` (auch `verdaechtig`; `verdächtig`,
  `not verdächtig`, `verdächtig == True`). Es trifft genau die Buchungen, die das Label „Verdächtig“ tragen (D-157),
  und wird nur berechnet, wenn der Ausdruck es nennt. Das Label bleibt berechnet und wird nicht gespeichert.
  In Regeln gibt es das Feld nicht (422 `nur_im_filter`). Es erscheint in `GET /api/ausdruck/sprache` (Kontext
  `filter`) und damit in Vervollständigung und Baukasten.
- **Nicht:** kein Tag „Verdächtig“ auf der Tag-Seite, kein Filter über `tag_id`.
- **Prüfung:** Core-Test `test_filter_verdaechtig`; Vervollständigung und Baukasten nicht im Browser angesehen.

## D-264 Kategorieauswahl kann Kategorien anlegen (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Der Dialog „Kategorie setzen“ (Kürzel k) soll Kategorien anlegen können.
- **Entscheidung:** Die Kategorieauswahl (`kategorie-auswahl`) hat unter der Liste den Knopf „Neue Kategorie
  anlegen…“ (`kategorie-auswahl-neu`). Er zeigt statt der Liste ein Formular (`kategorie-neu`): Name
  (`kategorie-neu-name`, vorbelegt mit dem Suchtext), Art (`kategorie-neu-art`: Ausgaben oder Einnahmen) und
  übergeordnete Kategorie (`kategorie-neu-eltern`, Kategorien derselben Art oder oberste Ebene). „Anlegen und
  wählen“ (`kategorie-neu-anlegen`) legt sie an und wählt sie; „Zurück zur Auswahl“ (`kategorie-neu-zurueck`)
  kehrt zur Liste zurück. Eingabe im Suchfeld ohne Treffer öffnet das Formular direkt. Fehler (z. B. gleichnamige
  Kategorie auf derselben Ebene) erscheinen im Dialog.
- **Gilt überall, wo die Auswahl erscheint:** Kategorie setzen (einzeln, mehrfach) und die Nachfrage beim
  Bestätigen (D-260). Bestandskonten lassen sich hier nicht anlegen.
- **Rückgängig:** Anlegen und Zuordnen sind zwei Änderungen.
- **Prüfung:** nur gelesen und auf Syntax geprüft; kein Browsertest gelaufen.

## D-265 Kontoblatt ohne Panel Kategorien (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Im Kontoblatt die Kategorienliste nicht anzeigen, das gibt mehr Platz.
- **Entscheidung:** Das Panel „Kategorien“ (`panel-kategorien`) wird im Kontoblatt nicht mehr aufgebaut; die Liste
  bekommt seine Breite. Das Kürzel „v k“ entfällt. Das Panel „Einzelheiten“ bleibt mit Einklappen, Verschieben
  und Breite. Der gespeicherte Layoutstand im Browser behält sein Format.
- **Entfällt damit:** das Ziehen von Buchungen auf eine Kategorie des Panels und der Sprung in eine Kategorie aus
  dem Panel. Zuordnen geht über „k“, das Kontextmenü, die Zelle und die Einzelheiten; Kategorien erreicht man über
  die Navigation.
- **Offen vor dem Merge:** Browsertests, die das Panel Kategorien bedienen (Layout, Ziehen und Ablegen), sind noch
  nicht angepasst und werden rot oder müssen entfallen.

## D-266 Einzelheiten rechts oder unten angedockt (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Die Einzelheiten können als Dockfenster rechts oder unten angezeigt werden.
- **Entscheidung:** Das Panel „Einzelheiten“ kennt den Bereich `unten` (`bereich-unten`): unter der Liste, über
  deren ganze Breite. Der Knopf `panel-verschieben-details` im Panelkopf wechselt zwischen rechts und unten
  (`data-ziel` nennt das Ziel). Unten ändert der Griff am oberen Rand die Höhe (120 bis 600 Pixel, Vorgabe 260,
  Pfeil auf/ab, Pos1/Ende); eingeklappt bleibt nur die Kopfzeile. Ort, Breite und Höhe werden wie bisher im
  Browser gemerkt (`kontor.layout`, neues Feld `hoehe`; ältere Stände bleiben gültig).
- **Unverändert:** Am Handy öffnen die Einzelheiten als Dialog. Ein gespeicherter Ort „links“ bleibt gültig; der
  Knopf führt von dort nach rechts.
- **Prüfung:** einmal im Browser angesehen (rechts, unten, Wechsel über den Knopf); kein Browsertest geschrieben.
  Dabei auch D-259 (Schriftfarbe in der Auswahl) und D-265 (kein Panel Kategorien) gesehen.

## D-267 Split-Dialog: Vorlage von Hand übernehmen (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Bei „Buchung splitten“ lässt sich eine Vorlage auswählen, auch wenn der
  Betrag nicht passt.
- **Entscheidung:** Der Split-Dialog hat die Auswahl `split-vorlage-wahl` mit allen Split-Vorlagen (Name und
  Gesamtbetrag, auch inaktive; Bedingungen der Vorlage spielen keine Rolle). Die Wahl ersetzt die Zeilen außer
  denen auf Bestandskonten durch die Teile der Vorlage (Kategorie, Betrag, Memo). Passt der Betrag nicht, bleiben
  die Teile wie in der Vorlage; `split-vorlage-hinweis` nennt den offenen Rest, und gespeichert wird wie bisher
  erst, wenn die Summe 0 ist (Teil ändern oder „Split Ausgleichen“). Es wird nicht anteilig umgerechnet.
- **Status:** Das Speichern ist eine Zuordnung von Hand, die Buchung wird also bestätigt (D-261).
- **Prüfung:** einmal im Browser durchgespielt (Vorlage 10 € auf Buchung 12 €, Ausgleichen, Speichern); kein
  Browsertest geschrieben.

## D-268 Einzelheiten unten: Abschnitte nebeneinander (Feature `status-farben`, 2026-11-24)

- **Anlass:** Rückmeldung vom 2026-11-24 mit Bildschirmfoto: Unten angedockt standen die Abschnitte der
  Einzelheiten untereinander über die ganze Breite; viel Platz blieb leer.
- **Entscheidung:** Unten angedockt stehen Kopf (Empfänger, Betrag, Datum, Status), Verwendungszweck,
  Buchungssätze, Tags mit Bestätigung, Dokumente und weitere Abschnitte nebeneinander in Spalten von mindestens
  19rem; reicht die Breite nicht, brechen sie in die nächste Zeile um. Die Herkunft steht über die ganze Breite
  darunter. Rechts angedockt und am Handy bleibt die Darstellung untereinander. Nur Darstellung (CSS), keine
  neuen Kennungen.
- **Prüfung:** einmal im Browser bei 1900 Pixel Breite angesehen (helles Thema, Buchung ohne Vorschlag und ohne
  Dokumente).

## D-269 Auswahl und Status auf getrennten Ebenen (Feature `status-farben`, 2026-11-24)

- **Anlass:** Rückmeldung vom 2026-11-24: Die blaue Unterlegung der gewählten Buchung hat dieselbe Struktur wie die
  rote und gelbe Statusfarbe; beim Wechsel zu einer anderen Buchung springen die Farben.
- **Entscheidung:** Der Status bestimmt Grundton und Streifen der Zeile und bleibt immer sichtbar. Die Auswahl
  ersetzt den Grundton nicht mehr, sondern legt einen farbneutralen Schleier darüber (die Zeile wird eine Stufe
  dunkler, im dunklen Thema heller) und rahmt sie oben und unten mit einer Linie in der Akzentfarbe. Hover ist
  derselbe Schleier, schwächer und ohne Linien. Die Akzentfarbe steht damit nur noch für „ausgewählt“, Rot und
  Gelb nur für den Status.
- **Ersetzt D-259:** Die farbige Schrift in ausgewählten Zeilen entfällt; sie war nötig, weil die Auswahl den
  Statuston überdeckte.
- **Technik:** `--toenung`, `--streifen`, `--schleier` je Zeile; die klebende Betragszelle nutzt dieselben Werte.
  `data-markierung`, `aria-selected` und alle Kennungen sind unverändert.
- **Prüfung:** im Browser angesehen, hell und dunkel, Auswahl auf roten, gelben und weißen Zeilen sowie Hover.
  Nicht angesehen: Handy-Ansicht, Zeilen mit Vorschlagsknöpfen.

## D-270 Auswahl mit kräftigem blauem Rahmen, kein gelber Fokusrahmen an Zeilen (Feature `status-farben`, 2026-11-24)

- **Anlass:** Rückmeldung vom 2026-11-24: Beim Drücken von Umschalt erscheint an der gewählten Buchung plötzlich ein
  gelber Rahmen. Die Stärke gefällt, das Verhalten nicht; die Auswahl soll mit einer dickeren blauen Linie umrandet
  sein.
- **Ursache:** Der gelbe Rahmen war die Tastatur-Fokusanzeige des Browsers (`:focus-visible`), die erst mit dem
  ersten Tastendruck erscheint.
- **Entscheidung (ändert D-269):** Ausgewählte Zeilen tragen einen Rahmen von 3 Pixeln in der Akzentfarbe rundum
  statt der feinen Linien oben und unten; direkt untereinander liegende ausgewählte Zeilen bilden einen gemeinsamen
  Rahmen. Der Fokusrahmen an Zeilen des Kontoblatts entfällt. Schleier und Statuston bleiben wie in D-269.
- **Folge für die Tastaturbedienung:** Eine Zeile, die den Fokus hat, aber nicht ausgewählt ist (etwa nach dem
  Abwählen mit Strg+Klick), ist nicht mehr eigens gekennzeichnet. Alle anderen Fokusanzeigen der Oberfläche
  bleiben.
- **Prüfung:** im Browser angesehen (hell und dunkel, einzelne Zeile, drei Zeilen untereinander, nach Umschalt).

## D-271 Filterwechsel behält die Auswahl, Fokus in der Liste (Feature `status-farben`, 2026-11-24)

- **Anlass:** Auftrag vom 2026-11-24: Wird der Filter geändert oder aufgelöst, bleibt die gewählte Buchung gewählt,
  das Kontoblatt hat den Fokus, und die Buchung steht nach Möglichkeit in der Mitte.
- **Entscheidung (ändert `oberflaeche.md` 7.1 „ein Filterwechsel hebt die Auswahl auf“):** Bei jedem Filterwechsel
  (Ausdruck, Zeitraum, Baukasten, Optionen, Zurücksetzen, auch Sortierung) bleiben die gewählten Buchungen gewählt,
  soweit sie zur neuen Liste gehören. Die Buchung mit dem Fokus (sonst die erste gewählte) wird in die Mitte
  gerollt und bekommt den Fokus; liegt sie auf einer späteren Seite, wird bis dorthin geladen. Gehört sie nicht
  mehr zur Liste, geht der Fokus auf die erste Zeile, ohne sie auszuwählen.
- **Beim Tippen:** Solange der Fokus in einem Eingabefeld steht (der Filter wirkt schon während des Tippens),
  bleibt er dort; Auswahl und Lage werden trotzdem nachgeführt. Eingabe im Filterfeld schließt ab: der Fokus geht
  in die Liste (ohne Auswahl wird die erste Zeile gewählt). „✕“ am Filterfeld gibt den Fokus ebenfalls an die
  Liste statt zurück ins Feld.
- **Schnittstelle:** `GET /api/buchungen` kennt `position_id` (≥ 1) und liefert dann zusätzlich `position`: die
  Stelle der Buchung (ab 0) in der gefilterten, sortierten Liste oder `null`. Ohne den Parameter fehlt das Feld.
- **Prüfung:** Core-Test `test_position_einer_buchung_in_der_liste`; im Browser mit 450 Buchungen durchgespielt
  (filtern, wählen, Filter leeren: gewählt, Fokus, Mitte, zweite Seite nachgeladen). Nicht geprüft: gruppierte
  Ansicht, Baukasten, Handy.
- **Offen vor dem Merge:** Tests, die nach einem Filterwechsel eine leere Auswahl erwarten.

## D-272 Zuordnung von Hand setzt auch das Tag der Person (Feature `status-farben`, 2026-11-24)

- **Anlass:** Antwort vom 2026-11-24 auf die offene Frage aus D-261: Die Zuordnung von Hand soll auch das Tag
  „<Name>-Bestätigt“ setzen.
- **Entscheidung (ändert die Annahme „Personen-Tag“ in D-261):** Wird eine importierte oder vorläufige Buchung in
  der Oberfläche von Hand zugeordnet (Kategorie oder Konto setzen, einzeln und mehrfach, auch durch Ziehen und in
  der Zeile; Splits speichern; Vorschlag annehmen) und ist oben rechts eine Person gewählt, bekommt sie in
  derselben Aktion deren Tag. Ein Strg+Z nimmt Zuordnung, Status und Tag zusammen zurück.
- **Nicht:** ohne gewählte Person (dann nur der Status, ohne Nachfrage); bei schon bestätigten oder abgeglichenen
  Buchungen (eine spätere Umkategorisierung ist keine neue Bestätigung); bei Zuordnung auf „Unkategorisiert“; beim
  Ablehnen eines Vorschlags.
- **Nur Oberfläche:** Der Server kennt die Person nicht; über die REST-Schnittstelle setzt die Zuordnung weiterhin
  nur den Status.
- **Prüfung:** einmal im Browser durchgespielt (Kategorie setzen auf importierter, vorläufiger und bestätigter
  Buchung, ein Strg+Z). Splits speichern und Vorschlag annehmen nur gelesen.

## D-273 Design steht vor dem ersten Zeichnen fest (Feature `status-farben`, 2026-11-24)

- **Anlass:** Rückmeldung vom 2026-11-24: Beim Neuladen im Dunkelmodus blitzt die Seite kurz hell auf.
- **Ursache:** Das Design (`data-thema` am Wurzelelement) setzte erst das Modul der Anwendung. Module laufen nach dem
  Einlesen der Seite; bis dahin war sie mit dem hellen Design gezeichnet.
- **Entscheidung:** Die Hülle lädt im Kopf, vor dem Stylesheet, das kleine blockierende Skript
  `/oeffentlich/thema.js`. Es setzt `data-thema` nach derselben Regel wie die Anwendung (gespeicherte Wahl
  `kontor.thema`, sonst das System). Kein Inline-Skript (CSP `script-src 'self'` bleibt). Die Datei steht in der
  Liste des Service Workers; dessen Cache heißt jetzt `kontor-huelle-43`.
- **Nicht geändert:** Die Anmeldeseite folgt weiterhin nur dem Design des Systems.
- **Prüfung:** Core-Test `tests/core/test_thema_start.py`; im Browser bei blockierter Anwendung geprüft, dass
  `data-thema` und Hintergrund für alle vier Fälle (System hell/dunkel, Wahl dunkel/hell/keine) stimmen.

## D-274 Sprung zur Gegenbuchung leert auch das Ausdrucksfeld (Feature `status-farben`, 2026-11-24)

- **Anlass:** CI-Lauf nach dem Merge von D-272/D-273: der Test
  `test_browser_tabs.py::test_gegenbuchung_setzt_verdeckende_filter_zurueck` war rot – nach „Filter zurückgesetzt“ stand der alte Filter wieder in der Adresse.
- **Ursache (vermutet, nicht nachgestellt):** Der Sprung setzte die Filter zurück, ließ aber den Text im
  Ausdrucksfeld stehen. Lief danach dessen verzögerte Prüfung ab, wendete sie den alten Ausdruck erneut an. Ob das
  den Fehler im CI-Lauf erklärt, zeigt erst der nächste Lauf; im Lauf davor war der Test grün.
- **Entscheidung:** Der Sprung leert beim Zurücksetzen auch das Ausdrucksfeld, wie „Filter zurücksetzen“.
- **Dazu:** `test_browser_ausdruck.py::test_tags_im_kontoblatt_bearbeiten` (in `TESTUMBAU.md` schon als gelegentlich
  rot vermerkt) wartet jetzt, bis die Zeile das neue Tag zeigt, bevor der Tag-Dialog erneut geöffnet wird.

## D-275 Handy: Schwung beim Rollen der Buchungsliste bremst wieder ab (Feature `status-farben`, 2026-11-24)

- **Anlass:** Fehlermeldung vom 2026-11-24: Am Handy rollt die Liste nach dem Loslassen des Fingers weiter, bremst
  aber nicht ab, sondern läuft endlos.
- **Nachgestellt:** Chrome in Handy-Größe (390 × 844, Touch), 700 synthetische Buchungen, schneller Wisch über
  Touch-Ereignisse, Rollposition alle 0,25 s gemessen. Vor der Korrektur lief die Liste mit gleichbleibender
  Geschwindigkeit (gruppiert etwa 1700 bzw. 7000 Pixel je Viertelsekunde, ohne Abbremsen) bis ans Ende; ohne
  Gruppierung sprang sie beim zweiten Wisch ebenfalls ans Ende. Nach der Korrektur klingt jeder Wisch in etwa einer
  Sekunde aus (z. B. 438, 275, 184, 39, 0 Pixel).
- **Ursache:** Ab 100 Zeilen zeichnet die Liste nur einen Ausschnitt und tauscht beim Rollen ihre Zeilen aus. Der
  Browser hielt eine der Zeilen als Scroll-Anker fest und schob die Rollposition bei jedem Austausch nach; das löste
  den nächsten Austausch aus, und so fort.
- **Entscheidung:** `.buchungsliste { overflow-anchor: none; }` – die Liste nimmt nicht am Scroll-Anker teil.
- **Grenzen:** Gemessen nur in Chrome. Auf einem iPhone (Safari) nicht geprüft; ältere Safari-Versionen kennen
  keinen Scroll-Anker, dort hätte der Fehler eine andere Ursache. Kein Browsertest dafür (der Browser-Job liegt
  schon über dem Budget); der Core-Test `tests/core/test_liste_scrollanker.py` sichert nur, dass die Angabe bleibt.

## D-276 Offline-Hinweis verschwindet von selbst, auch ohne `online`-Ereignis (Feature `offline-rueckkehr`, 2026-11-25)

- **Anlass:** Fehlermeldung vom 2026-11-25: Am Handy steht nach jeder Rückkehr des Browsers aus dem Hintergrund
  „Keine Verbindung zum Server – Kontor ist offline“ über einer leeren Seite; erst Neuladen von Hand hilft.
- **Ursache:** Jede gescheiterte Anfrage setzt den Offline-Zustand (auch die minütliche Abfrage der
  Benachrichtigungen). Aufgehoben wurde er nur durch das Ereignis `online`. Das kommt nicht, wenn das Gerät selbst
  nie offline war. Warum die Anfrage beim Zurückholen scheitert, ist auf dem Handy nicht nachgestellt (vermutet:
  eingefrorene Seite, abgebaute Verbindung).
- **Entscheidung:** Im Offline-Zustand prüft die Oberfläche die Verbindung selbst (`verbindungPruefen` in
  `app/haupt.js`, `GET /api/anmeldung`): nach 1 s, dann in verdoppelten Abständen bis höchstens 30 s, nur bei
  sichtbarer Seite; sofort bei `visibilitychange` (sichtbar), `pageshow` und `online`. Bei Erfolg wie bisher nach
  `online`: Hinweis weg, Seite und Benachrichtigungen laden. Jeder Fehler der Prüfung (auch eine Antwort des
  Proxys ohne JSON) gilt als „weiter offline“.
- **Nicht geändert:** Im Offline-Zustand zeigt die Seite weiter keine Daten (`oberflaeche.md` 18); nach einer
  einzelnen gescheiterten Anfrage ist sie also kurz leer, bevor sie neu lädt.
- **Prüfung:** Core-Test `tests/core/test_offline_rueckkehr.py`; Browsertest `tests/test_browser_offline.py`
  (Anfragen an `/api/` scheitern bei `navigator.onLine = true`; vor der Korrektur rot). Auf einem echten Handy
  nicht geprüft.

## D-277 Offline bleibt die geladene Seite stehen (Feature `offline-rueckkehr`, 2026-11-25)

- **Anlass:** Wunsch vom 2026-11-25 zu D-276: Die Seite soll im Offline-Zustand nicht mehr geleert werden. Am
  Handy genügt eine gescheiterte Anfrage nach der Rückkehr aus dem Hintergrund, und die Seite war leer.
- **Entscheidung:** Ersetzt in D-276 den Punkt „Nicht geändert“ und in `oberflaeche.md` 18 / 27.1.4 „keine
  veralteten Daten“. Der Offline-Zustand leert weder die aktive Seite noch die offenen Tabs (`Tabs.alleVerwerfen`
  entfällt). Der Hinweis lautet jetzt „… Angezeigte Daten können veraltet sein; sie werden neu geladen, sobald die
  Verbindung zurück ist.“ Geladene Tabs lassen sich offline zeigen. Nach der Rückkehr lädt die aktive Seite wie
  nach einer Änderung neu (`zeigen({ behalten: true })`: Auswahl und Rollposition bleiben), die anderen Tabs beim
  nächsten Zeigen.
- **Grenzen:** Eine Seite, die offline erst angefordert wird (neuer Tab, anderer Abfrageteil, Neuladen des
  Browsers), zeigt weiter nur ihre Überschrift. Schreibende Aktionen scheitern offline wie bisher ohne eigene
  Meldung (der Hinweis genügt).
- **Prüfung:** Core-Test `tests/core/test_offline_rueckkehr.py`; Browsertest `tests/test_browser_offline.py`
  (Seite unverändert während des Hinweises, danach neue Anfrage an `/api/konten`). Der abgewählte Gesamttest
  `m8/test_m8_thema_pwa.py::test_offline_huelle_und_keine_daten` ruft die Seite offline neu auf und gilt weiter.

## D-278 Mobil: Gesten auf der Buchungszeile neu belegt (Feature `mobil-gesten`, 2026-11-25)

- **Anlass:** Arbeitsanweisung vom 2026-11-25 (Gespräch mit Torsten): Am Handy sollen Bestätigen, Kategorie zuweisen
  und notfalls eine neue Kategorie direkt erreichbar sein; alles andere eine Ebene tiefer.
- **Bestand vor dem Umbau:** Tippen öffnete die Einzelheiten, lange Berührung begann den Auswahlmodus, Wischen nach
  rechts schaltete die Auswahl um, nach links öffnete die Kategorie-Auswahl (D-141, `oberflaeche.md` 36.3/36.4). Die
  Kategorie-Auswahl kann schon neue Kategorien anlegen (D-264). Das Kontextmenü gab es mobil nur über „Mehr“ im
  Auswahlmodus, als Blatt von unten.
- **Entscheidung** (`oberflaeche.md` 43): kurz tippen markiert genau eine Zeile (keine Auswahl, kein Fenster);
  Doppeltipp (400 ms) öffnet die Einzelheiten; lang tippen öffnet das Kontextmenü der Zeile mit „Einzelheiten“ und
  „Mehrfachauswahl“ vor den Einträgen des Desktops; nach rechts wischen bestätigt als die gewählte Person; nach links
  wischen wie bisher. Nach dem Bestätigen bietet die Zeile drei Sekunden „Rückgängig“ an; bei schon bestätigten
  Buchungen tut der Wisch nichts. Im Auswahlmodus schaltet Tippen weiter die Auswahl um.
- **Einzelheiten:** „Bestätigen“ ist die Bestätigung der Person (Tag und Status, D-155/D-257). Eine importierte
  Buchung ohne Zuordnung verlangt weiter zuerst eine Kategorie (D-260) – das ist die einzige Nachfrage beim Wisch.
  „Rückgängig“ in der Zeile nimmt die Änderungen dieses Wischs zurück, solange sie die letzten im Stapel sind
  (`stapelStand` in `app/kern.js`). Das Menü der einzelnen Zeile arbeitet mit `nurIds`, ohne die Auswahl zu setzen.
- **Nicht geändert:** Desktop (auch mit Touch), Gesten in anderen Ansichten, der Auswahlmodus selbst.
- **Prüfung:** Core-Test `tests/core/test_mobil_gesten.py`; Browsertest `tests/test_browser_gesten.py` (fünf Gesten bei
  390 px, über Touch-Ereignisse). Angepasste Tests in `TESTUMBAU.md`. Auf einem echten Handy nicht geprüft
  (Doppeltipp-Zeit, Zusammenspiel mit dem Menü des Browsers bei langer Berührung).

## D-279 Mobil: Kopfzeile wieder in einer Zeile (Feature `mobil-gesten`, 2026-11-25)

- **Anlass:** Am Handy stand der Menüknopf allein in einer Zeile über den übrigen Knöpfen (Screenshot vom 2026-11-25).
- **Nachgestellt:** Mock-Modus bei 390, 360 und 320 px: Kopfzeile 101 px hoch in zwei Zeilen; bei 320 px ragte sie
  7 px über den Rand. Ursache: mit dem Personenknopf (M28) sind es neun Knöpfe zu 44 px plus Abstände (über 420 px).
- **Entscheidung:** Mobil kein Abstand zwischen den Knöpfen, kein Umbruch (außer bei eingeblendeter Suche);
  „Wiederholen“ entfällt unter 403 px (vorher 390), der Knopf der Befehlspalette unter 359 px. Danach eine Zeile mit
  54 px Höhe bei allen drei Breiten, alle Knöpfe 44 × 44 px. „Wiederholen“ bleibt über die Befehlspalette erreichbar,
  unter 359 px mobil nicht mehr.
- **Prüfung:** Messung vor und nach der Änderung; `tests/test_browser_gesten.py` (eine Zeile bei 390 px),
  `m26/test_m26_oberflaeche.py::test_kopfzeile_eine_zeile_reihenfolge_und_groesse` prüft „eine Zeile“ jetzt wieder.
## D-280 Ausgleichsbuchungen, die sich aufheben, aufräumen (Feature `ausgleich-aufraeumen`, 2026-11-25)

- **Anlass:** Arbeitsanweisung vom 2026-11-25: Mehrfach entstand bei der Synchronisation eine Ausgleichsbuchung und
  einen Tag später die umgekehrte.
- **Bestand:** `sync._saldo_abgleichen` vergleicht nach jedem erfolgreich verarbeiteten Bankkonto den Saldo der Bank
  mit dem des Kontos und bucht die Differenz gegen „Korrekturen“ (Kennung `saldo:<iban>:<stichtag>`, Zweck
  „Saldoausgleich Bank“, eigene Änderung `sync_saldoausgleich`). E-161 schloss ein Zusammenfassen bewusst aus.
- **Ursache der Paare:** nicht an echten Daten untersucht. Nach `kontostand.md` 3 entstehen sie, wenn eine Buchung
  vor dem Bankumsatz im Buch steht; ebenso denkbar ist, dass die Bank den neuen Saldo vor dem Umsatz meldet. Das
  Aufräumen behandelt die Folge, nicht die Ursache.
- **Entscheidung** (`kontostand.md` 5, ersetzt E-161 in diesem Punkt), jeweils für unveränderte Ausgleichsbuchungen
  desselben Kontos mit höchstens sieben Tagen Abstand:
  - Summe 0: ohne Nachfrage weg. Beim Abruf wird statt der zweiten Buchung die erste gelöscht; der Altbestand wird
    beim ersten Start einmalig aufgeräumt.
  - Summe ungleich 0 (auch gleichgerichtete Beträge): Die Oberfläche fragt in einem Fenster, ob beide zu einer
    Buchung mit der Summe werden; „Getrennt lassen“ wird gemerkt, „Später“ gilt bis zum nächsten Laden.
- **Protokoll:** Das Entfernen beim Abruf ist die Änderung `sync_saldoausgleich` des Laufs (Eintrag „Buchung
  gelöscht“), der Altbestand eine Änderung `saldoausgleich_aufraeumen`, das Zusammenführen
  `saldoausgleich_zusammenfuehren`. Alle drei lassen sich rückgängig machen.
- **Einzelheiten:** Neues Modul `ausgleich.py`. Kein neuer fachlicher Zustand: „getrennt lassen“ und der Vermerk
  zum Altbestand liegen in `meta` (nach dem Einspielen einer Sicherung fragt Kontor über getrennte Paare erneut).
  `SaldoAbgleich` bekommt das optionale Feld `aufgehoben_buchung_id`. Abgestimmte, abgeglichene, umgebuchte oder
  gesplittete Ausgleichsbuchungen bleiben unberührt.
- **Grenzen:** Das Fenster erscheint in der Oberfläche (nach dem Laden, nach einer dort gestarteten
  Synchronisation, minütlich), nicht als Benachrichtigung aufs Handy. Paare werden nur aufeinanderfolgend gebildet.
- **Prüfung:** Core-Tests `tests/core/test_ausgleich_aufraeumen.py`; Browsertest `tests/test_browser_ausgleich.py`.
  Nicht an echten Bankdaten geprüft.

## D-281 Mobil: Doppeltipp nur bei ruhender Liste, Auswahlmodus nur ausdrücklich (Feature `mobil-gesten-2`, 2026-11-25)

- **Anlass:** Rückmeldung vom Handy nach Version 0.53: (1) Schnelles Rollen mit wiederholtem Ansetzen wurde als
  Doppeltipp erkannt und öffnete die Einzelheiten. (2) Die Ansicht landete oft im Auswahlmodus, z. B. beim Wechsel
  zur Gegenbuchung.
- **Ursache:** (1) Der Doppeltipp prüfte nur dieselbe Zeile und 400 ms. Auf dem Handy nicht nachgestellt; vermutlich
  meldet der Browser das Anhalten der rollenden Liste als Tippen. (2) Der Sprung zu einer Buchung
  (`sprungMarkieren`), das Wiederfinden nach dem Laden und Enter im Filterausdruck setzten die Auswahl auf die
  Zielbuchung – mobil ist jede Auswahl der Auswahlmodus.
- **Entscheidung:** (1) Ein Tipp zählt für den Doppeltipp nur, wenn 500 ms davor nichts gerollt wurde (Rollen durch
  das Markieren selbst ausgenommen), und beide Tipps liegen höchstens 24 px auseinander. (2) Mobil setzen diese drei
  Stellen keine Auswahl mehr; das Ziel ist markiert und fokussiert (`oberflaeche.md` 43 Nr. 7). Desktop unverändert.
- **Nicht geändert:** Maus und Tastatur im schmalen Fenster (Rechtsklick, Kürzel) wählen weiter aus.
- **Prüfung:** Core-Test in `tests/core/test_mobil_gesten.py`; `tests/test_browser_gesten.py` (Tippen direkt nach
  einem Rollereignis und an zwei Stellen der Zeile öffnet nichts). Angepasst: `test_browser.py::
  test_bericht_sprung_mobil_mit_nachladen_nicht_verdeckt`, `m26::test_suchtreffer_kompakt_und_tippen_springt`.
  Das Rollen am echten Handy ist nur über ein nachgestelltes Rollereignis geprüft.

## D-282 Mobil: lange Berührung nur bei ruhender Liste (Feature `mobil-gesten-3`, 2026-11-25)

- **Anlass:** Rückmeldung vom Handy nach Version 0.54: Ein langer Druck während des Rollens öffnete das Kontextmenü.
- **Ursache:** Die lange Berührung bricht nur ab, wenn sich der Finger um mehr als 10 px bewegt. Hält der Finger die
  rollende Liste an und bleibt liegen, sind nach 500 ms alle Bedingungen erfüllt. Auf dem Handy nicht nachgestellt.
- **Entscheidung:** Im mobilen Kontoblatt öffnet die lange Berührung das Menü nur, wenn seit 500 ms vor ihrem Beginn
  nichts gerollt wurde (derselbe Zeitstempel wie beim Doppeltipp, D-281). Danach folgt wie bisher kein Tippen.
- **Nicht geändert:** lange Berührung in anderen Ansichten (Kontenbaum, Kategorien, Tabs) und im Desktop-Layout.
- **Prüfung:** Core-Test in `tests/core/test_mobil_gesten.py`; `tests/test_browser_gesten.py` (lange Berührung
  direkt nach einem Rollereignis öffnet nichts, danach wieder). Am echten Handy nicht geprüft.

## D-283 Mobil: Wischhinweis als Overlay, Ansicht steht, kein Knopf „Buchung erfassen“ (Feature `mobil-gesten-3`, 2026-11-25)

- **Anlass:** Rückmeldungen vom Handy nach Version 0.54: (1) Beim Wischen erscheint nichts, auch kein „Rückgängig“.
  (2) Nach dem Bestätigen springt das Kontoblatt. (3) Der Knopf zum Erfassen kann mobil weg.
- **Ursache (1), nachgestellt:** Hinweis und „Rückgängig“ wurden mit `offsetTop` der Zeile gesetzt. Ab 100 Zeilen
  zeichnet die Liste nur einen Ausschnitt in einem eigenen Fenster; `offsetTop` gilt dann nicht mehr für die
  Listenspalte. Bei 320 Buchungen lagen beide rund 5000 px über der Zeile, außerhalb des Bildschirms. In den
  bisherigen Tests (20 Zeilen) fiel das nicht auf; schon bei gruppierter kurzer Liste lagen sie 47 px daneben.
- **Ursache (2), nicht nachgestellt:** Im Test mit gleich hohen Zeilen blieb die Rollposition stehen. Vermutet: Nach
  dem Neuladen misst die lange Liste die Zeilenhöhen nach; bei unterschiedlich hohen Zeilen verschiebt sich der Inhalt.
- **Entscheidung:** (1) Lage über die sichtbare Position der Zeile (`zeilenLage`); der Hinweis liegt als Overlay über
  der Zeile (vorher dahinter). (2) `ansichtHalten`: Nach dem Bestätigen und nach „Rückgängig“ in der Zeile wird die
  Rollposition so nachgeführt, dass die Zeile an ihrer Stelle bleibt (über drei Bilder, also auch nach dem
  Nachmessen). (3) `buchung-erfassen` ist mobil ausgeblendet; neue Buchungen von Hand gibt es am Handy damit nicht
  mehr (Desktop unverändert).
- **Prüfung:** Core-Test in `tests/core/test_mobil_gesten.py`; `tests/test_browser_gesten.py::
  test_wischen_in_langer_liste_bleibt_an_der_zeile` (130 Buchungen, gerollt: Hinweis, „Rückgängig“ und Zeile an
  derselben Stelle). Ob (2) am Handy damit behoben ist, zeigt erst der Versuch dort.

## D-284 Offene Ansichten folgen dem Buchbestand; Mail-Abruf im Takt der Kontosynchronisation (Feature `mail-aktuell`, 2026-11-25)

- **Anlass:** Fehlermeldung vom 2026-11-25: Bei offenem Kontoblatt ordnet ein Mail-Abruf Mails zu, das Kontoblatt
  zeigt sie aber erst nach Schließen und Öffnen. Dazu der Auftrag: Mail-Abruf periodisch wie die Kontosynchronisation.
- **Ursache, nachgestellt:** Nach „Mails abrufen“ lud nur das Mail-Blatt neu. Die übrigen Tabs wurden nicht als
  veraltet markiert (das geschieht sonst nur nach einer eigenen Aktion über `aktion()`), also zeigte der Tab des
  Kontoblatts beim Zurückwechseln den alten Stand. Dasselbe galt für jede Änderung im Hintergrund: Abrufe des
  Planers (Konto und Mail) und Änderungen von einem anderen Gerät.
- **Entscheidung (Ansichten):** Neuer Endpunkt `GET /api/bestand/stand` (höchste Kennung im Änderungsprotokoll). Die
  Oberfläche fragt ihn jede Minute und bei der Rückkehr ins Fenster ab; nach jedem eigenen Neuladen merkt sie sich
  den Stand. Weicht er ab, gelten die übrigen Tabs als veraltet, und die sichtbare Ansicht lädt neu, sobald niemand
  darin arbeitet (kein Feld im Fokus, kein Fenster, kein Menü). Nach „Mails abrufen“ im Mail-Blatt und in den
  Einstellungen gelten die übrigen Tabs sofort als veraltet.
- **Entscheidung (periodisch):** Den Planer-Abruf gab es schon (`KONTOR_MAIL_INTERVALL_MINUTEN`, Vorgabe aus, in
  der ausgelieferten `kontor.env` auskommentiert). Neu: Ist die Variable nicht gesetzt, gilt
  `KONTOR_SYNC_INTERVALL_MINUTEN`. Eine installierte Umgebungsdatei mit Kontoabruf alle 240 Minuten ruft damit
  ohne Handgriff auch Mails alle 240 Minuten ab; `0` schaltet ab, eine eigene Zahl gilt wie bisher. Die
  Testinstanz setzt `0`. `GET /api/mail/abruf/stand` nennt `automatisch` und `intervall_minuten`, das Mail-Blatt
  zeigt den Abstand.
- **Verworfen:** die Vorgabe des Felds `mail_intervall_minuten` zu ändern (träfe jede Konfiguration aus Python,
  auch alle Tests); ein eigener Kanal vom Server zum Browser (die Abfrage je Minute genügt).
- **Grenzen:** Die sichtbare Ansicht folgt einer Änderung im Hintergrund mit bis zu einer Minute Verzug. Eine eigene
  schreibende Anfrage ohne anschließendes Neuladen löst beim nächsten Takt ein überflüssiges Neuladen aus.
- **Tests:** `tests/core/test_mail_aktuell.py`, `tests/test_browser_mail_aktuell.py` (Abruf im Mail-Blatt bei
  offenem Kontoblatt; Zuordnung im Hintergrund bei sichtbarem Kontoblatt, Auswahl bleibt). Angepasst:
  `tests/test_mail_fortschritt_eigen.py` (Stand mit zwei neuen Feldern), `tests/test_oberflaeche.py` (neuer Pfad).

## D-285 Testinstanz mit Demodaten zum Vorführen (Feature `demodaten`, 2026-11-25)

- **Anlass:** Die Anwendung soll sich Freunden zeigen lassen, ohne dass echte Bankbewegungen sichtbar werden:
  ein Girokonto, ein Sparbuch, rund zehn teils hierarchische Kategorien, Kredite, mindestens 2000 Buchungen und
  100 Mails; alle Funktionen sollen sich zeigen lassen.
- **Mit dem Auftraggeber abgestimmt:** eigener Befehl `kontor-test demo [branch]` (ohne Angabe `main`); die
  Demo läuft **ohne Anmeldung**; Mails und Buchungen sind vorab geladen, und die Abrufe in der Vorführung
  bringen Neues.
- **Entscheidung, Daten:** Ein Generator (`demowelt.py`) erfindet, was Bank und Postfächer wüssten; daraus wird
  die Mock-Datendatei. Den Buchbestand baut `demodaten.py` ausschließlich über die REST-Schnittstelle im selben
  Prozess (ASGI, kein Server), mit der simulierten Uhr: so, wie ein Anwender über drei Jahre gearbeitet hätte.
  Dadurch sind Protokoll, Abrufe, Vorschläge, Kreditraten, Umbuchungen und Dokumente echt entstanden und passen
  zu jeder künftigen Fassung des Datenmodells; es gibt keine eingecheckte Datenbank und kein zweites Schema.
- **Entscheidung, Testinstanz:** Den Generator führt das Python der Testinstanz aus (der Stand des Branches
  baut seine eigenen Daten). Die Demo-Einstellungen (ohne Anmeldung, Mock-Datendatei) stehen in einer
  Zusatz-Umgebungsdatei, die ein Drop-in der Unit nach `kontor-test.env` lesen lässt. Die ausgelieferte Unit
  und `kontor-test.env` bleiben unverändert (`betrieb.md` 9); eigene Anpassungen der Umgebungsdatei bleiben
  erhalten. `einrichten` nimmt die Demo-Einstellungen zurück. Vor dem Aufbau wird eine vorhandene Datenkopie
  gelöscht, damit nie echte Daten ohne Anmeldung erreichbar sind, auch wenn der Aufbau scheitert.
- **Selbst entschieden:** 14 Kategorien (acht oberste, sechs Unterkategorien) statt genau zehn, damit Berichte
  und Lernmodell Stoff haben; zwei Kredite (Wohnungsdarlehen mit Sondertilgung und Korrektur im Jahresabgleich,
  Autokredit ohne Korrektur); der Bestand ist auf den Tag des Aufbaus bezogen und endet drei Tage davor, die
  letzten drei Wochen bleiben unbearbeitet; für 60 Tage danach liegen Umsätze und Mails bereit. Ein
  Dublettenverdacht ist eingebaut; der zugehörige Saldoausgleich folgt zwingend und zeigt D-280. Mail-Abgleich
  bleibt wie in der Hauptinstanz aus (D-208); PayPal-Mails sind deshalb zur Hälfte von Hand zugeordnet.
  Bestätigungen tragen die Tags der fest eingebauten Personen (D-262).
- **Verworfen:** eine eingecheckte fertige Datenbank (veraltet mit jeder Schemaänderung, Daten nicht auf „heute“
  bezogen); Schreiben mit SQL am Protokoll vorbei; ein Knopf in der Oberfläche (nicht bestellt); eine zweite
  `EnvironmentFile`-Zeile in der Unit (`betrieb.md` 9 legt genau eine fest).
- **Grenzen:** Ohne Anmeldung ist die Demo für jeden im erlaubten Netz offen und änderbar. Der Befehl `demo`
  steht erst zur Verfügung, wenn die Hauptinstanz eine Version mit diesem Feature hat. Nicht auf dem Server
  unter systemd geprüft (Drop-in, Rechte des Benutzers `kontor` an den vom Generator als root angelegten
  Dateien).
- **Tests:** `tests/core/test_demodaten.py` (kleiner Zeitraum, Befehl `demo` mit untergeschobenen Befehlen),
  `tests/test_demodaten_eigen.py` (voller Umfang, Kalenderränder, Umgebung der Instanz),
  `tests/test_testinstanz_skript_eigen.py` (`demo`, `neu`, `status`).

## D-286 Eigenes Logo der Testinstanz, auch als installierte Anwendung (Feature `testinstanz-logo`, 2026-11-25)

- **Anlass:** Haupt- und Testinstanz sehen in der Tab-Leiste und auf dem Startbildschirm des Handys gleich aus.
- **Entscheidung:** Im Mock-Modus heißt die Anwendung „Kontor Test“ und trägt ein eigenes Symbol: das K auf
  orangem Grund (`#c2570b`) mit dunklem Band „TEST“. Betroffen sind Manifest (`name`, `short_name`,
  `theme_color`), die vier Symbole (SVG, PNG 192 und 512, `maskable` 512), `theme-color`, Seitentitel und
  `apple-mobile-web-app-title` von Hülle und Anmeldeseite. Die Adressen bleiben dieselben; Hülle, Service Worker
  und Manifest-Verweise ändern sich nicht. Die Dateien liegen als `testinstanz-icon*` neben den bisherigen.
- **Warum der Mock-Modus und keine eigene Einstellung:** Die Testinstanz ist genau die Instanz im Mock-Modus.
  Eine neue Variable käme nicht an: Eine vorhandene `kontor-test.env` bleibt beim Einrichten erhalten, und die
  Unit schreibt das Programm der Hauptinstanz, die den neuen Stand noch nicht hat. So wirkt das Logo sofort mit
  jedem Branch, der es enthält.
- **Nicht geändert:** die Titel der Ansichten („… – Kontor“), der Schriftzug in der Kopfzeile, der Hinweisbalken
  „Mock-Modus“.
- **Grenzen:** Eine schon installierte Anwendung behält ihr altes Symbol; Android aktualisiert es frühestens nach
  einiger Zeit, iOS gar nicht. Sicher ist: entfernen und neu zum Startbildschirm hinzufügen. Die Symbole sind mit
  einem Skript außerhalb des Repositories erzeugt (Polygon des K aus `icon.svg`, Buchstaben aus Rechtecken, ohne
  Schriftdatei).
- **Tests:** `tests/core/test_testinstanz_logo.py`. Angepasst: `gesamt-tests/tests/app/m8/test_m8_auslieferung.py::
  test_manifest` (Name im Mock-Modus), in `TESTUMBAU.md` vermerkt.

## D-287 Bereich wechseln mit der Vortaste „w“ und F6 (Feature `tastatur`, 2026-11-25)

- **Anlass:** Auftrag vom 2026-11-25: bessere Tastaturbedienung, möglichst ganz ohne Maus. Erster Schritt: mit
  einer Tastenfolge den aktiven Bereich wechseln; „b“ führt im Kontoblatt immer ins Buchungsblatt.
- **Entscheidung:** Die Vortaste ist `w` (`v` ist im Kontoblatt die Ansicht, D-167). Sie gilt auf jeder Seite und
  liegt deshalb in `haupt.js`, nicht im Kontoblatt. Ziele: `b` Blatt der Seite, `n` Navigation, `t` Tab-Leiste,
  `s` Suche, `1`–`9` Tab mit dieser Nummer, `←`/`→` Nachbartab, `z` zuletzt aktiver Tab, `x` Tab schließen. Eine
  Seite meldet eigene Bereiche über `bereiche()`; das Kontoblatt `b` Buchungsblatt, `e` Einzelheiten, `f` Filter.
  Vertrag: `oberflaeche.md` 12.1a.
- **F6 / Umschalt+F6** wechseln die Bereiche reihum und wirken auch aus Textfeldern (dort tippt `w` ein w).
- **Esc** führt aus Navigation, Tab-Leiste und Einzelheiten zurück ins Blatt.
- **Sichtbar:** Der Bereich mit dem Fokus hat einen Rahmen (`bereich-aktiv`); er erscheint auch nach einem
  Mausklick in den Bereich.
- **Unverändert:** alle Kürzel aus D-167 (`v d` klappt die Einzelheiten weiter nur ein und aus, `f w` bleibt der
  Zeitraum der letzten sieben Tage), Alt+1 … Alt+7, `/`.
- **Nicht enthalten:** ein Ziel für den Kategorienbaum (das Panel gibt es im Kontoblatt seit D-265 nicht mehr),
  Pfeiltasten innerhalb der Einzelheiten (dort Tab), Zeilennavigation auf den übrigen Listenseiten.
- **Grenzen:** Mobil öffnet `w n` das Menü und `w e` die Einzelheiten als Dialog; nur am Desktop geprüft.
- **Tests:** `tests/core/test_tastatur.py`, `tests/test_browser_tastatur.py`. Der Service-Worker-Cache heißt
  `kontor-huelle-44`.

## D-288 Fokuszeile verschwindet nicht hinter dem Spaltenkopf (Feature `tastatur`, 2026-11-25)

- **Anlass:** Meldung vom 2026-11-25: Geht man im Kontoblatt mit den Pfeiltasten viele Buchungen nach oben, wird
  die erste Buchung nicht sichtbar.
- **Ursache:** Der Spaltenkopf klebt am oberen Rand der rollenden Liste. Das Nachführen der Fokuszeile rechnete
  ohne ihn: Die Zeile galt als sichtbar, sobald sie im Ausschnitt lag, auch wenn der Kopf sie verdeckte. Betroffen
  war jede Zeile, die beim Hochgehen an den oberen Rand kam, nicht nur die erste; in der kurzen Liste
  (`scrollIntoView`) ebenso wie in der Liste mit Fenstertechnik (`slotZeigen`).
- **Entscheidung:** Beide Wege ziehen die Höhe des klebenden Kopfs ab (`kopfUeberstand`). Die kurze Liste setzt sie
  als `scroll-padding-top` am rollenden Behälter, die Fenstertechnik rechnet sie in das Ziel ein. Gilt für
  Pfeiltasten, Bild↑, Pos1 und jeden anderen Sprung auf eine Zeile.
- **Tests:** `tests/test_browser_tastatur.py::test_pfeil_nach_oben_zeigt_die_erste_buchung_unter_dem_spaltenkopf`
  (40 und 700 Buchungen), `tests/core/test_tastatur.py`.

## D-289 Vorschlag annehmen und ablehnen wirken sofort (Feature `tastatur`, 2026-11-25)

- **Anlass:** Meldung vom 2026-11-25: Das Bestätigen einer Kategorieempfehlung mit dem Haken und das Ablehnen
  dauern zu lange; die Oberfläche muss sofort reagieren.
- **Ursache:** Je Entscheidung liefen nacheinander: Stand des Änderungsprotokolls lesen, Vorschlag entscheiden,
  Bestätigungs-Tag setzen, neue Änderungen lesen, Stammdaten und Liste neu laden. Erst danach änderte sich die
  Zeile.
- **Entscheidung:** Das Kontoblatt nimmt die Wirkung vorweg und zeichnet sofort: Vorschlag weg; beim Annehmen
  Status bestätigt und das Tag der gewählten Person, beim Ablehnen die vorherige Kategorie und `vorlaeufig` wieder
  `importiert` (dieselben Regeln wie `regeln._entscheiden`, D-261, D-272). Die Anfragen laufen danach im
  Hintergrund, eine Entscheidung nach der anderen, damit jede ihr eigener Rückgängig-Schritt bleibt. Neu geladen
  wird erst nach der letzten eingereihten Entscheidung; ein Neuladen dazwischen (etwa durch den Planer) behält die
  noch offenen Entscheidungen bei. Gilt für Haken und Kreuz in der Zeile, `a`/`A`, Kontextmenü, Einzelheiten und
  die Mehrfachleiste.
- **Fehler:** Lehnt der Server ab, erscheint die Meldung wie bisher und die Zeile zeigt wieder den Stand des
  Servers.
- **Grenzen:** Summen im Kopf und die Erfolgsmeldung mit „Rückgängig“ folgen erst mit der Antwort des Servers.
  Strg+Z unmittelbar nach dem Klick nimmt die Entscheidung erst zurück, wenn sie beim Server angekommen ist
  (bestehende Reihung, D-122). Andere Aktionen (Kategorie setzen, Status, Tags) warten weiter auf den Server.
- **Tests:** `tests/core/test_vorschlag_sofort.py`, `tests/test_browser_vorschlag_sofort.py` (Server je Anfrage um
  0,6 Sekunden verzögert; die Zeile ändert sich in unter 0,4 Sekunden).

## D-290 Kategorie, Status, Bestätigen und Tags wirken sofort (Feature `tastatur`, 2026-11-25)

- **Anlass:** Antwort vom 2026-11-25 auf die Frage aus D-289 („ja“) und die Meldung, dass auch das Zuweisen von
  Kategorien zu lange dauert.
- **Entscheidung:** Der Weg aus D-289 ist verallgemeinert (`Kontoansicht.sofort`): Eine Aktion beschreibt, wie sie
  eine geladene Buchung ändert, und welche Anfragen sie schickt. Das Blatt zeichnet sofort; die Anfragen laufen
  nacheinander im Hintergrund; neu geladen wird nach der letzten. Umgestellt sind Kategorie setzen, Status setzen,
  Bestätigen und Zurücknehmen der Person sowie Hinzufügen und Entfernen von Tags aus dem Kontoblatt. Vertrag:
  `oberflaeche.md` 45.
- **Kategorie nur im einfachen Fall vorweg:** Ziel ist eine Kategorie und jede Buchung hat genau eine Gegenseite.
  Bei einer Umbuchung auf ein Bestandskonto entscheidet der Server über das Zusammenführen; sie und gesplittete
  Buchungen zeigen sich weiter erst mit der Antwort (aber in derselben Reihung).
- **Kein unnötiges Neuzeichnen:** Gleicht der Stand des Servers dem gezeigten, bleiben die Zeilen stehen
  (`bildVon`). Vorher zeichnete jedes Neuladen alle Zeilen neu.
- **Neue Tags:** Ein neu angelegter Tag steht sofort im Stamm (`tagHolen`), damit die nächste eingereihte Aktion
  ihn nicht ein zweites Mal anlegt. Das Fenster der Tags zählt nach Namen, weil ein vorweg gezeigter Tag noch
  keine ID hat.
- **Ersetzt** das Vorab-Zeigen nur des Status beim Bestätigen (D-258, `statusVorab` entfällt) und in D-289 die
  Grenze „andere Aktionen warten weiter auf den Server“.
- **Für Tests:** `data-ausstehend` an `seite-konto` (0 = Anfragen und Neuladen abgeschlossen). Wer nach einer
  solchen Aktion mit Zeilen weiterarbeitet, wartet darauf; das Attribut der Zeile allein genügt nicht mehr als
  Zeichen, dass neu geladen ist.
- **Grenzen:** Aktionen außerhalb dieses Wegs (Löschen, Splitten, Inline-Bearbeitung, „Bearbeiten…“) reihen sich
  nicht ein; unmittelbar nach einer vorweggenommenen Aktion ausgelöst, können sie sich mit ihr überschneiden
  (wie schon bisher bei zwei schnellen Aktionen). Fehler beim Hinzufügen eines Tags erscheinen als Meldung, nicht
  mehr im Fenster. Mobil nur über die Gesamttests geprüft.
- **Außerdem (zu D-287):** Lädt ein mit `w` gewählter Tab noch und der Anwender hat inzwischen den Bereich
  gewechselt, holt ihn der Fokus nicht mehr ins Blatt zurück.
- **Tests:** `tests/core/test_aktionen_sofort.py`, `tests/test_browser_aktionen_sofort.py` und
  `tests/test_browser_vorschlag_sofort.py` (schreibende Anfragen im Browser angehalten, bis der Test sie freigibt).
  Angepasst: `gesamt-tests/tests/app/m8/test_m8_panels_mobil.py::test_wischen_links_setzt_kategorie_und_rueckgaengig`
  (wartet auf `data-ausstehend="0"`), in `TESTUMBAU.md` vermerkt.
- **Beobachtet, nicht behoben:** `tests/test_browser_mail_aktuell.py::test_abruf_im_hintergrund_…` und der
  Doppeltipp in `tests/test_browser.py` schlagen bei stark paralleler Ausführung gelegentlich fehl, auch auf dem
  Stand von main vor diesem Branch (mail_aktuell dort nachgestellt).


## D-291 Rollen in Fenstern und Menüs sperrt die Liste nicht (Feature `tastatur`, 2026-11-25)

- **Anlass:** Nach dem Merge von D-287 bis D-290 schlug in der CI auf main
  `m26::test_zurueck_beendet_auswahl_ohne_ansicht_zu_verlassen` fehl: Die lange Berührung auf eine Buchung öffnete
  das Kontextmenü nicht.
- **Ursache:** Die Sperre aus D-281/D-282 (kein Doppeltipp, keine lange Berührung kurz nach dem Rollen) hörte auf
  das Rollen jedes Elements der Seite. Der Test öffnet das Konto über die Befehlspalette; deren Trefferliste rollt
  beim Öffnen. Lag die lange Berührung weniger als eine Sekunde danach, galt die Liste als „gerade gerollt“. Das
  war schon vorher so und hing an der Laufzeit; seit diesem Branch ist das Blatt in der CI früher bedienbar, und
  der Abstand reichte nicht mehr. In der CI mit zusätzlicher Protokollierung nachgestellt (Rollen in
  `dialog-inhalt` 750 ms vor dem Auslösen).
- **Entscheidung:** Rollen innerhalb eines Fensters (`dialog-huelle`) oder Menüs (`kontextmenue`) zählt nicht. Die
  Sperre gilt weiter für die Liste und jeden anderen Bereich der Ansicht.
- **Tests:** `tests/core/test_mobil_gesten.py`,
  `tests/test_browser_tastatur.py::test_rollen_in_der_befehlspalette_sperrt_die_lange_beruehrung_nicht` (schlägt
  ohne die Änderung fehl).
- **Offen:** Ein dritter Lauf desselben CI-Jobs blieb in der Gesamtsuite mit Browser hängen, bis die Frist von
  12 Minuten ablief (einmal, nicht nachgestellt; zwei Läufe der Suite auf einem Diagnose-Branch liefen durch).

## D-292 Tastenbelegung systematisiert (Feature `tastenbelegung`, 2026-11-26)

- **Anlass:** Auftrag vom 2026-11-26: die Tastenkürzel systematisch ordnen; `u`/`d` bewegen die Markierung im
  Kontoblatt wie die Pfeiltasten; `w` bietet je Blatt sinnvolle Ziele; Tastaturhilfe je Blatt. Die Belegung wurde
  in mehreren Runden mit dem Auftraggeber abgestimmt (Projektdokument `feature-tastenbelegung.md`).
- **Entscheidung:** Vertrag `oberflaeche.md` 46. Regeln: einzelne Buchstaben = Tätigkeiten, Vortasten `w`/`f`/`v`
  = Ziele; klein = Grundform, groß = Gegenstück bzw. Variante, bei Zeiträumen groß = „letzter“; keine
  Satzzeichen; `0` setzt zurück, `x` entfernt.
  - `u`/`d`/`U`/`D` global (`BEWEGUNG` in `haupt.js`): gehen als Pfeiltaste an das fokussierte Element. Liegt der
    Fokus nicht im Blatt, führt der erste Druck dorthin. Tabellen ohne eigene Zeilentastatur bekommen Pfeil
    auf/ab zur Nachbarzeile (`zeileWeiter`), damit `u`/`d` dort wirken.
  - Dublette `d` → `X` (Gegenstück von `x` Splitten). `?` → `h`, `/` entfällt (`w s`).
  - Zeiträume `f t T w W m M q Q y Y`; „letzte 7/30 Tage“ nur noch als Knopf (`f w` heißt jetzt „diese Woche“).
  - Filter wie die markierte Buchung `f e E z Z b B`; `f b` = `bet == … and dir == "…"`, `f B` = `bet == …`;
    auch im Untermenü `km-filter` (`km-filter-betrag`, `km-filter-betrag-absolut`).
  - Ansicht `v g k K o r s 0 e`; `v d` (Panel) entfällt, `w e` klappt das Panel auf.
  - `w` je Blatt: Seiten ohne `bereiche()` bekommen ihre Ziele aus `BLATT_ZIELE` (Name der Seite → Taste, Text,
    Selektor); `w a` = Kopf der Seite (`.seiten-kopf`), wenn er Bedienelemente hat. Nicht sichtbare Ziele fehlen.
  - Tastaturhilfe je Blatt (`tastatur-hilfe-blatt`, `-ueberall`, `-liste`, `-alle`); `kontoKuerzel(seite)` nennt
    für die Hilfe, was gerade nicht wirkt.
- **Alte Folgen** entfallen ohne Übergang und werden als „nicht belegt“ gemeldet.
- **Grenzen:** Auf der Finanzübersicht gibt es keine Knöpfe im Kopf, also kein `w a`. Die Mail-Liste und die
  Tabellen sind nur stichprobenartig im Browser geprüft (Finanzübersicht, Konten, Kategorien, Empfänger,
  Einstellungen). Der Service-Worker-Cache heißt `kontor-huelle-45`.
- **Tests:** `tests/core/test_tastenbelegung.py`, `tests/test_browser_tastenbelegung.py`; angepasst
  `tests/test_browser_tastatur.py` sowie in `gesamt-tests` M8 und M28 (`TESTUMBAU.md`).

## D-293 Kein Umbruch mitten im Wort in Tabellen (Feature `tabellenbreite`, 2026-11-26)

- **Anlass:** Meldung vom 2026-11-26 mit Bildschirmfoto: In der Finanzübersicht stand am Handy „Ausgaben“ Buchstabe
  für Buchstabe untereinander; alle Tabellen prüfen und Spalten im Zweifel verbreitern.
- **Befund:** Geprüft mit den Demodaten (D-285) auf allen Seiten, zwölf Berichten und sechs Einstellungsbereichen in
  den Breiten 390, 768, 1024 und 1440 px (Suche nach Wörtern, die über mehrere Zeilen laufen). Ursachen:
  - `overflow-wrap: anywhere` an allen Tabellenzellen und Karten. Es macht die Mindestbreite einer Spalte fast
    null; bei knappem Platz schrumpfte der Browser Spalten bis auf einzelne Buchstaben (Tilgungsplan, Konten,
    Empfänger, Was kommt noch, Konfiguration, Lernmodell bei 768 px).
  - Am Handy bekam die `caption` einer Tabelle als Karten (Finanzübersicht) nur die Breite eines Buchstabens.
  - Regelliste bei 768 px: drei Knöpfe neben dem Inhalt ließen ihm etwa 100 px; Jahresraster: „September“ in
    einer Kachel von 65 px.
- **Entscheidung:**
  - Zellen und Karten mit `overflow-wrap: break-word`: Spalten sind mindestens so breit wie ihr längstes Wort.
    `anywhere` nur noch für Code, Mail-Links und `.technisch`; Werte der Konfiguration mindestens 7rem breit.
  - Jede `table.tabelle` bekommt einen Rahmen `.tabelle-rahmen` mit `overflow-x: auto` (MutationObserver in
    `haupt.js`, nicht in der Buchungsliste). Breite Tabellen rollen dort statt der ganzen Seite.
  - Mobile Karten: `caption` als Block. Lernmodell-Kategorien als Karten, Prozentangabe mit festem Leerzeichen.
  - Desktop bis 1100 px: Regelknöpfe unter dem Inhalt, Jahresraster in vier Spalten.
- **Bleibt:** Berichtstabellen mit `white-space: nowrap` (D-217) rollen wie bisher in ihrem Rahmen; technische
  Zeichenketten (URLs in der Konfiguration, Mail-Adressen) brechen weiter innerhalb der Spalte um.
- **Tests:** `tests/core/test_tabellenbreite.py`, `tests/test_browser_tabellenbreite.py` (drei Breiten, acht
  Seiten; scheitert ohne die Änderung). Service-Worker-Cache `kontor-huelle-46`.

## D-294 Änderungsprotokoll neu gestaltet (Feature `protokoll-gestaltung`, 2026-11-26)

- **Anlass:** Der Auftraggeber fand das Änderungsprotokoll hässlich: eine nummerierte Liste mit drei gleich lauten
  Knöpfen je Zeile, Zeitpunkt und Quelle ohne Abstand, technische Texte („sync_saldoausgleich“, „(1 Objekt)“), auf
  dem Handy je Eintrag fast ein Drittel des Bildschirms.
- **Entscheidung:** Gliederung nach Tagen in Karten; je Eintrag ein Raster aus Uhrzeit, farbiger Marke der Quelle
  (Töne der Navigationsgruppen), Beschreibung als Knopf zu den Einzelheiten und einer Zeile mit dem betroffenen
  Objekt bzw. dem Umfang; „Rückgängig“ und „Bis hierher“ rechts, gedämpft bis zum Zeigen. Filter nach Quellen
  über den vorhandenen Parameter `quelle`. Das Fenster der Einzelheiten bekommt Kacheln im Kopf, Karten je Objekt
  und lesbare Werte. Spezifikation `oberflaeche.md` 48.
- **Server:** Beschreibung für `sync_saldoausgleich` ergänzt; ältere Einträge mit dem rohen Namen zeigt die
  Oberfläche lesbar an. Ein Core-Test prüft, dass jede benutzte Aktion eine Beschreibung hat.
- **Selbst entschieden:** „Bis hierher“ nur ohne Filter (sonst würden ausgeblendete Änderungen mit
  zurückgenommen); der Knopf heißt sichtbar „Bis hierher“, die Bestätigung weiter „Bis hierher rückgängig“.
  „Heute“/„Gestern“ nach der Uhr des Browsers. Der Filter wird nicht gemerkt. Die Seite liegt jetzt in
  `app/aenderung.js` (zusammen mit dem Fenster), `seiten.js` reicht sie weiter.
- **Unverändert:** alle `data-testid`, `data-quelle`, `data-wirksam`, die Klasse `bis-markiert` und das Verhalten
  von Rückgängig (13.9, 25.1, 41.8).
- **Tests:** `tests/core/test_protokoll_gestaltung.py`, `tests/test_browser_protokoll.py`; bestehende Tests
  unverändert grün.

## D-295 Eigene Regeln vor automatisch angelegten, Übernehmen als eigene Regel (Feature `regelgruppen`, 2026-11-26)

- **Anlass:** Der Auftraggeber möchte die Regeln ordnen, getrennt nach eigenen und automatisch angelegten (D-179).
  Weil die Reihenfolge zugleich die Priorität ist, ist das keine reine Anzeige. Mit dem Auftraggeber abgestimmt
  (2026-11-25/26): zwei feste Abschnitte, eigene Regeln wirken immer vor automatischen; Übernehmen nur über einen
  ausdrücklichen Knopf, nicht beim Bearbeiten.
- **Reihenfolge:** erst alle eigenen, dann alle automatisch angelegten Regeln, je Gruppe `prioritaet`, dann `id`
  (`regeln._REIHENFOLGE`). Gilt für Liste, Auswertung und Verdeckung im Test. Keine Schemaänderung: Die Gruppe folgt
  aus `regel_automatisch`. Vorher konnte eine neue eigene Regel hinter automatischen landen; jetzt gewinnt eine
  eigene Regel immer.
- **`POST /api/regeln/reihenfolge`** nimmt weiter die vollständige Liste und ordnet sie nach Gruppen (eigene zuerst),
  statt eine gemischte Liste abzulehnen. So bleiben bisherige Aufrufe gültig.
- **`POST /api/regeln/{id}/uebernehmen`:** Vermerk weg, Priorität ans Ende der eigenen Regeln, Empfänger gesperrt
  (`empfaenger_lernregel_sperre`). Die Sperre verhindert, dass nach Ändern oder Löschen der übernommenen Regel für
  denselben Empfänger wieder eine automatische Regel entsteht; das ist dieselbe Wirkung wie beim Löschen einer
  automatischen Regel. 422 `regel_nicht_automatisch` für eigene Regeln. Eine Änderung `regel_uebernehmen` mit dem
  Namen in der Beschreibung (eigener Endpunkt mit `protokoll.protokolliert`, weil `aendern` keine Beschreibung setzt).
- **Oberfläche:** Abschnitt „Eigene Regeln“ wie bisher (Ziehen, Alt+↑/↓, Nummern). Abschnitt „Automatisch angelegt“
  als `<details>`, Vorgabe eingeklappt, ohne Griff und Nummer, sortierbar (Name, Kategorie, Zuletzt angelegt) und
  durchsuchbar; Zustand in `localStorage` (`kontor.regeln.automatisch`). Die im Konzept genannte Sortierung nach
  Treffern entfällt, weil die Regelliste noch keine Trefferzahl hat. Duplizieren einer automatischen Regel ergibt
  eine eigene Regel.
- **Tests:** `tests/core/test_regelgruppen.py`, `tests/test_browser_regelgruppen.py`. Bestehende Tests unverändert
  grün (Regeln, automatische Regeln, Ausdrücke, M15/M26/M30–M32 mit Browser).

## D-296 Kategorie-Auswahl vollständig mit der Tastatur (Feature `kategorie-tastatur`, 2026-11-26)

- **Anlass:** Auftrag vom 2026-11-26: Der Dialog zur Kategorieauswahl im Kontoblatt muss vollständig über die
  Tastatur bedienbar sein.
- **Befund:** Wählen ging schon mit Pfeilen und Enter, aber
  - Enter übernahm bei mehreren Treffern nichts, solange kein Eintrag mit dem Pfeil markiert war;
  - die Liste hatte kein Pos1/Ende und kein Blättern, und Pfeil auf am Anfang blieb stehen;
  - „Neue Kategorie“ war bei vorhandenen Treffern nur über Tab und den Knopf erreichbar;
  - Esc im Formular „Neue Kategorie“ schloss das ganze Fenster statt zur Auswahl zurückzuführen;
  - in Art und übergeordneter Kategorie legte Enter nicht an.
- **Entscheidung:** `oberflaeche.md` 9.1 „Tastatur“: Pfeile umlaufend, Bild ab/auf um zehn, Strg+Pos1/Ende; mit
  Suchtext ist der erste Treffer markiert (wie in der Befehlspalette), Enter übernimmt; Strg+Enter öffnet das
  Formular mit dem Suchtext; Enter in allen Feldern des Formulars legt an; Esc im Formular führt zurück. Pos1/Ende
  ohne Strg bleiben im Suchfeld beim Textcursor. Ein Hinweis unter der Liste nennt die Tasten (nur am Desktop).
- **Geändertes Verhalten:** Wer nach dem Tippen Pfeil ab drückt, landet jetzt auf dem zweiten Treffer (der erste
  ist schon markiert). Kein bestehender Test hing davon ab.
- **Tests:** `tests/core/test_kategorie_tastatur.py`, `tests/test_browser_kategorie_tastatur.py` (Wählen, neue
  Kategorie samt übergeordneter Kategorie, Abbrechen; jeweils nur Tastatur, Fokus zurück auf der Buchung).

## D-297 Filter „Bestätigung fehlt“: rote und gelbe Buchungen (Feature `filter-unbestaetigt`, 2026-11-26)

- **Anlass:** Auftrag vom 2026-11-26: Es muss eine Filtermöglichkeit nach gelben und roten Buchungen geben, also
  nach denen, bei denen noch eine Bestätigung fehlt.
- **Entscheidung:** Der Filterausdruck bekommt das Wahrheitsfeld `unbestätigt` (auch `unbestaetigt`,
  `not unbestätigt`, `unbestätigt == True`). Es trifft Buchungen mit Status Importiert oder Vorläufig, die nicht
  abgestimmt sind – dieselbe Bedingung wie die rote und gelbe Tönung im Kontoblatt (D-254). Nur im Filter, nicht
  in Regeln; es steht in `GET /api/ausdruck/sprache` und damit in Vervollständigung und Baukasten.
- **Bedienung:** Schalter „Bestätigung fehlt“ (`filter-unbestaetigt`) neben den Zeiträumen und das Kürzel `f o`
  („offen“). Beide setzen oder entfernen nur diesen Teil; Zeitraum und andere Teile bleiben. Vertrag:
  `oberflaeche.md` 47.
- **Rot und Gelb zusammen, nicht getrennt:** gefragt war nach den Buchungen ohne Bestätigung. Einzeln geht es wie
  bisher über `status == "importiert"` bzw. `status == "vorlaeufig"`; eigene Schalter dafür gibt es nicht.
- **Nicht gemeint:** die Bestätigung einer bestimmten Person (Tag „<Name>-Bestätigt“). Eine bestätigte Buchung
  ohne mein Tag gilt hier nicht als offen.
- **Grenze:** Steht `unbestätigt` in einem von Hand geschriebenen Ausdruck innerhalb von Klammern oder neben
  „oder“ (außer in der Form `(…) and unbestätigt`), erkennt der Schalter es nicht und zeigt „aus“.
- **Tests:** `tests/core/test_filter_unbestaetigt.py`, `tests/test_browser_filter_unbestaetigt.py`; die
  Kürzeltabelle in `tests/core/test_tastenbelegung.py` ist um `f o` erweitert (`AENDERUNGEN.md`). Der
  Service-Worker-Cache heißt `kontor-huelle-48`. Mobil nicht im Browser angesehen.


## D-298 Tastaturbedienung aller Dialoge (Feature `dialog-tastatur`, 2026-11-26)

- **Anlass:** Auftrag vom 2026-11-26: In der Löschabfrage ließ sich nicht mit Tasten navigieren; alle Dialoge prüfen.
- **Befund** (Browsertest über 16 Dialoge: Kontoblatt mit Entf, k, t, s, e, x, M, n, h, Strg+K; Regeln, Konten, Tags,
  Erwartet, Über):
  - Tab, Umschalt+Tab und Esc funktionierten überall, der Fokus kam nach Esc zurück.
  - **Pfeiltasten** wirkten in keinem Dialog außerhalb von Listen; in der Löschabfrage blieb der Fokus auf dem Knopf.
  - **Split-Dialog:** Der Fokus blieb nach dem Öffnen im Kontoblatt, weil das Grundgerüst das erste Auswahlfeld wählte,
    ohne deaktivierte zu übergehen (Auswahl der Split-Vorlage ist ohne Vorlagen deaktiviert). Tasten wirkten dann
    auf das Kontoblatt statt auf den Dialog.
- **Entscheidung:** im Grundgerüst `dialog()` (alle Dialoge entstehen dort, Core-Test sichert das):
  Anfangsfokus aus `fokussierbare()`, Rückfall auf den Dialog selbst; `dialogPfeil`: ←/→ und Pos1/Ende in der
  Knopfleiste, ↑/↓ wie Tab auf Knöpfen, Links und Ankreuzfeldern; Elemente mit eigener Pfeilbedienung und
  bereits behandelte Tasten (`defaultPrevented`) bleiben unberührt. `oberflaeche.md` 9.
- **Tests:** `tests/core/test_dialog_tastatur.py`, `tests/test_browser_dialog_tastatur.py`. Eigene Browsertests mit
  Dialogen (83) und Browser-Gesamtsuite grün; `m8/test_m8_bearbeiten.py::test_konto_loeschen_rueckgaengig` schlug
  einmal unter voller Last fehl, danach dreimal im Paket grün (wacklig, nicht durch diese Änderung).

## D-299 Nachrücken der Markierung im Kontoblatt (Feature `markierung-nachruecken`, 2026-11-26)

- **Anlass:** Auftrag vom 2026-11-26: Fällt eine markierte Buchung in der gefilterten Kontoliste durch eine Änderung
  (z. B. Kategoriezuweisung) aus der Liste, war keine Buchung mehr markiert. Gewünscht: die Buchung direkt darunter.
- **Entscheidung:** `Kontoansicht.nachruecken` beim Neuladen, nur wenn Konto, Filter, Sortierung und Gruppierung
  gleich geblieben sind (`gleicheAbfrage`); ein Filterwechsel bleibt bei D-271. Nachfolger ist die nächste noch
  vorhandene Buchung unter der untersten herausgefallenen in der angezeigten Reihenfolge, sonst die darüber.
  Fällt nur ein Teil der Auswahl heraus, bleibt der Rest; der Fokus geht zur nächsten verbliebenen markierten
  Buchung. Gilt ebenso nach dem Löschen. Mobil nur Markierung (D-281). `oberflaeche.md` 7.1.
- **Tests:** `tests/core/test_markierung_nachruecken.py`, `tests/test_browser_markierung_nachruecken.py` (Mitte,
  Ende, zwei markierte; jeweils weiter mit der Tastatur). Eigene Browsertests und Browser-Gesamtsuite grün;
  `test_browser_mail_aktuell.py` schlug einmal unter voller Last fehl (bekannt wacklig), einzeln zweimal grün.

## D-300 Sonderposten in den Berichten (Feature `sonderposten`, 2026-11-26)

- **Anlass:** Ein großer einmaliger Posten auf dem Girokonto (z. B. Autokauf) verfälscht die Berichte. Vom
  Auftraggeber gewählt (2026-11-26): Sonderposten markieren, in den Berichten standardmäßig auslassen und getrennt
  zeigen. Die richtige Buchung über Bestandskonten (Kredit, Vermögenskonto) bleibt der Weg für Fälle, in denen Geld
  nur durchläuft.
- **Markierung über einen festen Tag „Sonderposten“** statt eines neuen Feldes: kein Schemawechsel, Sicherung,
  Protokoll, Rückgängig und Tag-Oberfläche gelten ohne Zusatz. Erkannt wird der Name ohne Groß- und Kleinschreibung;
  Tags am Empfänger zählen nicht (ein Empfänger ist kein Einzelfall). Umbenennen des Tags beendet die Wirkung.
- **Vorgabe `ohne`** in Monat, Jahr, Kategorien, Empfänger, Geldfluss und Einnahmen/Ausgaben. Kontostand, Vorschau und
  Vermögen zählen alles, weil sie echte Bestände zeigen; der Tag-Bericht wählt seine Buchungen selbst.
- **Gemeinsamer Baustein** `sonderposten.py` (`trennen` nach dem Laden der Posten, `abschnitt`); in der Oberfläche
  `berichtRahmen` mit `sonderposten: true` (Schalter, Standzeile, Kasten).
- **Vorschlag:** Die vorhandene Ausreißer-Erkennung braucht frühere Buchungen beim selben Empfänger und erkennt einen
  Autokauf beim neuen Autohaus nicht. Deshalb eigene Liste `auffaellig.sonderposten`: nicht feste Ausgabe ab 2.000 €
  und mindestens die Hälfte des üblichen Monats.
- **Kürzel** `p` im Kontoblatt (D-292: Großbuchstaben sind Varianten; `S` wäre keine Variante von `s` Status).
- **Vertrag:** `openapi.yaml` – Parameter `BerichtSonderposten`, Schema `SonderpostenAbschnitt`, Feld in
  `EinnahmenAusgabenBericht` (sonst scheitert die strenge Schemaprüfung der M5-Tests).
- **Tests:** `tests/core/test_sonderposten.py`, `tests/test_browser_sonderposten.py`; angepasst
  `tests/core/test_tastenbelegung.py` (Eintrag in `tests/core/AENDERUNGEN.md`).
- **Offen:** keine Sonderposten in den Demodaten.


## D-301 Pfade von Unterkategorien im Ausdruck (Fehler `kategoriepfad`, 2026-11-26)

- **Fehler** (Meldung des Auftraggebers): Der Baukasten des Filters (und des Regeleditors) schrieb eine
  Unterkategorie als `kategorie == "Versicherungen › PKV"`. Der Server kennt Pfade nur mit `:` und meldete
  „Kategorie … gibt es nicht“. Ursache: Die Auswahllisten nahmen `kontoPfad` (Anzeige, Trenner „ › “) auch als Wert;
  ebenso der Rückweg vom Ausdruck in den Baukasten (`baukastenAusBaum`) und die Übersetzung alter Filteradressen
  (`kategorie_id` → Ausdruck). Bei Kategorien ohne Oberkategorie fiel es nicht auf.
- **Behebung:** `ausdruckPfad` in `kern.js` (Trenner `:`) für alle Werte, die in einen Ausdruck gehen; die Anzeige der
  Auswahl bleibt „ › “. Zusätzlich nimmt der Server `›` als gleichwertigen Trenner an (`Bezuege._suchen`), damit
  schon gespeicherte Filter, Lesezeichen und von Hand getippte Pfade gelten; die kanonische Form bleibt `:`.
  `ausdruecke.md` 2.3.
- **Tests:** `tests/core/test_kategoriepfad.py`, `tests/test_browser_kategoriepfad.py`.


## D-302 Sicherungspunkte: stündlich inkrementell, Zurück und Vorwärts, kurzes Änderungsprotokoll (Feature `sicherung-stuendlich`, 2026-11-26)

- **Auftrag** (mit dem Auftraggeber abgestimmt, Projektdokument `feature-sicherung-stuendlich.md`): stündliche,
  sehr kleine inkrementelle Sicherung; gute Wiederherstellung mit zuverlässigem Zurück und Vorwärts; jeder Punkt
  ansteuerbar und herunterladbar; Größe je Punkt und gesamt; ältere Punkte ausgedünnt (48 h / 30 Tage / 26 Wochen /
  24 Monate); keine leeren Punkte; Einspielen = bestehende Daten sichern, alles löschen, einspielen; nur auf dem
  Server; Belege stündlich mit; Änderungsprotokoll nur noch rund eine Stunde; tägliche volle Datei entfällt.
- **Bauweise:** `sicherungspunkte.py`. Ein Punkt ist die logische Zeilendifferenz (Tabellen der Sicherungsdatei,
  Schlüssel je Tabelle) zu seiner Basis, als LZMA-gepacktes JSON; Anker enthalten alles. Beleginhalte sind
  inhaltsadressiert und kommen nur als neue Zeile mit. Prüfwert = SHA-256 über Zeilen-Hashes ohne Begleitzustand
  (`id_zaehler`, `sync_konto_zustand`; sie bewegen sich ohne fachliche Änderung und stehen voll in jedem Punkt).
  Verworfen: Export des Änderungsprotokolls, Seitendifferenz der SQLite-Datei.
- **Ausdünnen:** Stufen nach `sicherungspunkte.md` 4. Statt eines eigenen Tages-Differenzpunkts zum Monatsanker
  (Konzept) bekommen behaltene Punkte außerhalb der Stundenstufe beim Ausdünnen den Anker ihrer Kette als Basis;
  fällt der Anker weg, wird der älteste behaltene Punkt der Kette Anker. Gleiche Wirkung (kurze Ketten, je Monat
  ein Anker), aber ohne doppelte Dateien.
- **Einspielen:** `sicherung.einspielen` bekam zwei Haken: `vor_einspielen` sichert den Stand in derselben
  Schreibtransaktion (andere Schreiber warten auf die Sperre der Datenbank, nichts geht verloren), `nach_einspielen`
  prüft den Prüfwert gegen den Sollwert (Sollwert aus derselben Ladung samt Nacharbeiten in einer Datenbank im
  Arbeitsspeicher; für Sicherungen vor Version 11 entfällt die Prüfung, weil die Einstellungen der Instanz bleiben).
  Zusätzlich `maildienst.ohne_abruf()`. Reihenfolge der Sperren: erst Dateisperre der Ablage, dann Datenbank.
- **Abweichung vom Konzept 10.3:** Das Einspielen bleibt eine Änderung `sicherung_einspielen` mit Nettowirkung (M9,
  unverändert, alle M9-Tests gelten weiter). Weil das Protokoll nach einer Stunde gekürzt wird, belastet der große
  Eintrag es nur kurz; danach führt der Punkt „Vor Wechsel“ zurück.
- **Kurzes Protokoll:** `protokoll.kuerzen` nach jedem stündlichen Lauf; Herkunft angelegter Buchungen in
  `buchung_herkunft` (Datenbankschema 19), gelesen von `verschieben.herkunft` und `_angelegt_von`. Andere Leser der
  Protokollgeschichte: `sync._wiederkehrend_pruefen` (nur der eben gelaufene Lauf) und `MAX(id)` (AUTOINCREMENT
  bleibt) – unkritisch.
- **Einstellungen:** Sicherungsdatei Schemaversion 11 mit `einstellung` (vier Schlüssel aus `meta`); `status_farben`
  ist ein Migrationsvermerk, kein Wert der Nutzer.
- **Oberfläche:** Seite `/sicherung` (`app/sicherung.js`); die Vorschau eines Punkts ist ein Fenster (Desktop und
  Handy gleich) statt einer Spalte rechts. Die Uhr des Servers bestimmt Tage und Warnungen (Mock-Uhr).
- **Betrieb:** `kontor-sicherung.timer` stündlich, `python -m kontor.sicherung stunde`. Der alte Aufruf bleibt.
- **Offen:** Die Marke „Vor Update“ setzt der Update-Dienst noch nicht (er startet `kontor-sicherung.service`, der
  einen gewöhnlichen Punkt anlegt; `--marke vor_update` gibt es). Vorhandene tägliche ZIP-Dateien werden nicht als
  Punkte übernommen. Keine Benachrichtigung bei einem fehlgeschlagenen Prüflauf (nur Anzeige). Nicht auf dem echten
  Server unter systemd geprüft.
- **Tests:** `tests/core/test_sicherung_stuendlich.py`, `tests/test_sicherung_stuendlich_eigen.py`,
  `tests/test_browser_sicherung_stuendlich.py`; geänderte Tests in `tests/core/AENDERUNGEN.md` und `TESTUMBAU.md`.
## D-303 Nachweis markierter Buchungen als PDF (Feature `nachweis-pdf`, 2026-11-26)

- **Anlass:** Zahlungen gegenüber Dritten (Vermieter, Versicherung …) belegen, ohne Kontostand und übrige Umsätze
  preiszugeben. Gestaltung mit dem Auftraggeber abgestimmt (2026-11-26): Stil eines Kontoauszugs, nur die markierten
  Buchungen mit Datum, Empfänger, Verwendungszweck und Betrag; keine Kontostände (am Ende die Summe); Auszugsdatum,
  Kontoinhaber und BIC lesbar, IBAN gekürzt; an den Buchungen selbst nichts unkenntlich.
- **Herkunft offen ausgewiesen:** „Auszug aus der Homebanking-Software Kontor – kein Dokument der Bank“ im Kopf und in
  der Fußzeile, kein Banklogo. Da sich Buchungen in Kontor bearbeiten und von Hand erfassen lassen, trägt jede
  Buchung, die nicht unverändert so dasteht, wie die Bank den Umsatz geliefert hat, einen Hinweis (`berichte.md` 8).
- **Maßstab `bank_umsatz` statt Änderungsprotokoll:** Ein erster Entwurf verglich mit dem ersten Stand der
  Synchronisation im Protokoll. Seit D-302 wird das Protokoll nach einer Stunde gekürzt; deshalb merkt sich die
  Synchronisation je Bankkennung Buchungstag, Empfängername (nach Alias-Auflösung, also wie Kontor ihn vergeben hat),
  Verwendungszweck und Betrag (Datenbankschema 20, `bankumsatz.py`). Schlüssel ist die Kennung (eindeutig), nicht die
  Buchung: Rückgängig, Wiederholen und Einspielen legen Buchungen neu an, die Kennung bleibt. Betriebszustand wie
  `buchung_herkunft`: nicht im Protokoll, nicht in der Sicherung (nach dem Einspielen auf einer frischen Installation
  heißt es bei älteren Buchungen „Abgleich nicht möglich“ – vorsichtig statt falsch). Altbestand wird beim ersten
  Start einmal aus dem noch vorhandenen Protokoll nachgetragen (nur Buchungen, die die Synchronisation angelegt hat).
  Auch Übergangskennungen (D-200) werden gemerkt.
- **IBAN:** Ländercode, Prüfziffer und letzte vier Stellen, dazwischen immer vier Gruppen `XXXX` (verbirgt auch die
  Länge). Nicht „•“: In der Standardschrift Helvetica (WinAnsi) kommt es beim Kopieren aus dem PDF als Steuerzeichen
  heraus.
- **Kontoinhaber:** aus den von der Bank gemeldeten Kontodaten (Bankzugang, nur FinTS), im Dialog änderbar; im
  Mock-Modus leer. Eigener Lesepunkt `GET /api/export/nachweis/angaben` für die Vorbelegung.
- **Kürzel** `v p` (Wunsch des Auftraggebers; `p` ohne Vortaste ist Sonderposten, D-300), Bedingung `bestand`;
  Kontextmenü `km-nachweis` nur in Bestandskonten. Download per `fetch` und Blob, damit Fehler im Dialog erscheinen.
- **Getrennt vom PDF-Export** (`berichte.md` 5): eigenes Modul `nachweis.py`, eigene Betragsformatierung mit
  Tausenderpunkten (der Export behält das Format aus 4.2). Noch nicht im OpenAPI-Vertrag.
- **Tests:** `tests/core/test_nachweis_pdf.py` (auch Kürzen des Protokolls), `tests/test_nachweis_pdf_eigen.py` (Fehler,
  Vorbelegung, Nachtragen), `tests/test_browser_nachweis_pdf.py`;
  angepasst `tests/core/test_tastenbelegung.py`, `tests/test_oberflaeche.py` (Einträge in `tests/core/AENDERUNGEN.md`, `TESTUMBAU.md`).
- **Offen:** kein Schritt in den Demodaten.


## D-304 Buchung teilen (Feature `buchung-teilen`, 2026-11-27)

- **Anlass:** Eine Buchung schnell weitergeben, etwa per WhatsApp. Kontextmenü „Teilen…“ (`oberflaeche.md` 50) mit
  Kurztext und Link auf das Kontoblatt mit markierter Buchung; mit dem Auftraggeber abgestimmt.
- **Nur Kontextmenü, keine Taste** (Wunsch des Auftraggebers): Rechtsklick am Computer, lange Berührung auf dem Handy.
- **Genau eine Buchung**, Link auf die gerade angezeigte Ansicht (auch eine Kategorie), weil der vorhandene Parameter
  `buchung` nur eine Buchung als Sprungziel kennt. Der Empfänger braucht einen Zugang zu Kontor; der Link enthält
  keine Anmeldung.
- **Weitergabe** über die Web-Share-Schnittstelle, sonst Zwischenablage, sonst Anzeige zum Kopieren. Nur in der
  Oberfläche; kein neuer Endpunkt, kein Zustand.
- **Tests:** `tests/core/test_buchung_teilen.py`, `tests/test_browser_buchung_teilen.py` (Teilen-Funktion und
  Zwischenablage als Attrappe).


## D-305 Keine Knöpfe ✓/✗ für Kategorievorschläge in der Buchungszeile (Feature `vorschlag-knoepfe`, 2026-11-27)

- **Anlass (Auftraggeber):** Die Knöpfe zum Annehmen und Ablehnen in der Kategoriezelle sind überflüssig; auf dem Handy
  erledigt das Wischen, am Computer die Tastatur.
- **Entfällt:** `vorschlag-annehmen-<id>`, `vorschlag-ablehnen-<id>` samt Stil `vorschlag-knoepfe` (`oberflaeche.md`
  7.2 und Abschnitt zu den Vorschlagsmarken). Die Marke `vorschlag-marke` bleibt.
- **Bleibt:** `a`/`A`, Kontextmenü `km-vorschlag-annehmen`/`km-vorschlag-ablehnen` (mobil per langer Berührung),
  Mehrfachleiste, Einzelheiten (`details-vorschlag-annehmen`/`-ablehnen`), Wischen nach rechts (Bestätigen nimmt den
  Vorschlag an). Keine Änderung am Server.
- **Tests:** `tests/core/test_vorschlag_knoepfe.py`; angepasst `tests/test_browser_vorschlag_sofort.py`,
  `gesamt-tests/tests/app/m8/test_m8_kontoansicht.py`, `gesamt-tests/tests/app/m15/test_m15_oberflaeche.py`
  (`TESTUMBAU.md`).


## D-306 Gestaltung des Teilen-Texts für WhatsApp (Feature `teilen-format`, 2026-11-27)

- **Anlass (Auftraggeber):** Der Kurztext aus D-304 ist unübersichtlich: Der Verwendungszweck steht als langer Block,
  der Betrag geht unter. Gewünscht ist eine Gestaltung mit der Textauszeichnung von WhatsApp, die gut aussieht.
- **Kein Bild** (Auftraggeber): Mit Bild verwirft WhatsApp oft den Begleittext und damit den Link; der klickbare Link
  ist wichtiger.
- **Form** (`oberflaeche.md` 50, ersetzt die Zeilen aus D-304): Empfänger und Betrag fett, Art der Buchung, dann
  Datum mit Wochentag, Konto, Kategorie und Tags je eine Zeile mit Symbol, der lesbare Teil des Verwendungszwecks
  als Zitat (Zerlegung aus D-175, ohne SEPA-Kennungen), zuletzt allein der Link. Leere Angaben entfallen samt Zeile.
- **Kategorieansicht:** Konto und Betrag aus Sicht der Bestandskonten, damit der Empfänger der Nachricht die Buchung
  so sieht wie auf dem Kontoauszug.
- **Auszeichnungszeichen** aus dem Buchbestand werden durch ähnlich aussehende Zeichen ersetzt; unsichtbare Trenner
  verhindern die Auszeichnung nicht in allen Fassungen von WhatsApp.
- **Umsetzung** als reine Funktion `teilenText` in `app/teilen.js` (ohne DOM, über Node prüfbar). Weitergabe,
  Zwischenablage und Kopierfenster unverändert. Kein neuer Endpunkt, kein Zustand.
- **Tests:** `tests/core/test_teilen_format.py`; angepasst `tests/test_browser_buchung_teilen.py` (neue Form, neuer
  Fall Kategorieansicht; `TESTUMBAU.md`).


## D-307 Stündliche Sicherung im Dienst, Prüfungen sichtbar, Tags nicht mehr in den Einstellungen (Feature `sicherung-nachzug`, 2026-11-27)

- **Befund des Auftraggebers:** Auf dem Server entstanden nach dem Update auf 0.67 keine stündlichen Punkte, und es
  gab keinen Hinweis, wenn sich nichts geändert hatte.
- **Ursache:** Die systemd-Units werden bei der Installation einmal nach `/etc/systemd/system` kopiert
  (`README.md`); der Update-Dienst installiert nur das Wheel und darf `/etc` nicht schreiben (`ProtectSystem=full`).
  Der Server lief deshalb weiter mit dem täglichen Timer und dem alten Aufruf `--verzeichnis … --behalten 14`, der
  nur die ZIP-Datei schrieb.
- **Lösung:** `sicherungspunkte.Stundenlauf` im Dienst (Lifespan, Takt 60 s, fällig, wenn für die laufende Stunde
  noch keine Prüfung vorliegt). Der alte Aufruf legt zusätzlich einen Punkt an. Die neue Timer-Unit bleibt
  ausgeliefert; wer sie installiert, hat eine zweite, harmlose Auslösung. Verworfen: Units durch den Update-Dienst
  erneuern (bräuchte selbst eine neue, von Hand installierte Unit mit Schreibrecht auf `/etc`).
- **Prüfungen ohne Änderung** werden im Stand vermerkt und in der Zeitleiste als „geprüft – keine Änderung“ gezeigt
  (statt der Lückenangabe), auch in der Kachel und im Stand des Einstellungsbereichs.
- **Tags** stehen nicht mehr unter Einstellungen › Daten und Sicherung (thematisch fremd); sie bleiben auf `/tags`.

## D-308 Prüfung automatisch angelegter Regeln, Löschen ohne Sperre, Bereich „Deaktiviert“ (Feature `regelpruefung`, 2026-11-27)

- **Anlass:** Mit dem Auftraggeber abgestimmt (2026-11-27): Werden die Zuordnungen, aus denen eine automatische Regel
  entstand, später von Hand geändert, bleibt die Regel stehen und schlägt weiter die alte Kategorie vor. Solche Regeln
  sollen auffallen, damit der Nutzer sie bearbeitet oder löscht. Außerdem war die Sperre nach dem Löschen (D-179) in
  der Oberfläche nicht erkennbar.
- **Prüfung (`lernmodell.md` 9.5):** `GET /api/regeln/pruefung` misst jede aktive automatische Regel an allen
  Anlagebedingungen (mindestens 5 Zuordnungen, mindestens 95 % insgesamt, mindestens 95 % im Fenster von 365 Tagen),
  mit der Kategorie der Regel. Befund je Regel `grund` (`keine_buchungen`, `anzahl`, `anteil`, `fenster`), `hinweis`,
  `anzahl`, `gesamt`. Nur lesend, ohne gespeicherten Zustand.
- **„Periodisch“:** Statt eines Laufs im Planer prüft Kontor bei jedem Öffnen der Regelansicht. Damit ist der Befund
  immer aktuell (auch direkt nach einer Änderung), und es entsteht kein Betriebszustand, der veralten oder in die
  Sicherung müsste. Der Aufwand entspricht dem Training für die betroffenen Empfänger.
- **Ersetzt in D-179 die Sperre nach dem Löschen:** Eine gelöschte automatische Regel darf wieder entstehen. Eine
  deaktivierte verhindert eine neue, solange sie besteht (das galt schon über „keine automatische Regel gleich
  welcher Zustand“). Ersetzt in D-295 die Sperre beim Übernehmen: Eine Regel, die die jüngste Buchung des Empfängers
  trifft, verhindert eine automatische jetzt auch deaktiviert (vorher nur aktiv); so wirkt eine übernommene Regel
  weiter, bis sie gelöscht ist. `empfaenger_lernregel_sperre` wird weder geschrieben noch beachtet. Frühere Sperren
  bleiben als Daten stehen (Protokollform `lernregel_gesperrt`, Sicherung), damit Prüfsummen, Rückgängig älterer
  Änderungen und Sicherungen unverändert bleiben; kein Schemawechsel.
- **Oberfläche (`oberflaeche.md` 39):** Regeln mit Befund stehen im Abschnitt „Automatisch angelegt“ vor allen
  anderen, gelb markiert, mit `regel-hinweis-<id>` („Passt nicht mehr: … Bearbeiten oder löschen.“); die Überschrift
  nennt „<n> mit Hinweis“. Deaktivierte Regeln (eigene und automatische) stehen im eigenen Bereich
  `regeln-deaktiviert` ganz unten, „Deaktiviert (<Anzahl>)“, Vorgabe eingeklappt, Zustand im Browser
  (`kontor.regeln.deaktiviert`). Die Nummern der eigenen Regeln zählen nur die aktiven; beim Umsortieren bleiben
  deaktivierte eigene Regeln hinter den aktiven. Beim Deaktivieren einer automatischen Regel (Schalter oder Editor)
  lautet die Meldung „… Solange diese Regel deaktiviert ist, legt Kontor für diesen Empfänger keine neue an.“; die
  Rückfrage vor dem Löschen einer automatischen Regel nennt, dass sie wiederkommen kann, und rät zum Deaktivieren.
- **Tests:** `tests/core/test_regelpruefung.py`, `tests/test_browser_regelpruefung.py`. Angepasst (D-308 statt Sperre):
  `tests/core/test_regelgruppen.py` (`AENDERUNGEN.md`), `tests/test_lernregeln_eigen.py`,
  `gesamt-tests` M31 `test_m31_regeln_automatisch.py`, M30 `test_regelliste`, `spec/test_openapi.py`
  (`TESTUMBAU.md`).

## D-309 Mobil: markierte Buchung behält die Farbe ihres Status (Feature `markierung-status`, 2026-11-27)

- **Anlass:** Arbeitsanweisung vom 2026-11-27: In der mobilen App wurde die getippte (markierte) Buchung ganz blau
  hinterlegt; ob sie importiert (rot), vorläufig (gelb) oder bestätigt ist, war nicht mehr zu sehen.
- **Ursache:** Die Regel für `data-markiert` aus D-278 setzte die Hintergrundfarbe auf die Auswahlfarbe `--auswahl`
  und legte einen 4 px breiten Akzentstreifen genau über den Statusstreifen.
- **Entscheidung** (`oberflaeche.md` 43.5): mobil gilt für die Markierung dasselbe Prinzip wie für die Auswahl am
  Desktop (D-269/D-270): Grundton (`--toenung`) und Statusstreifen bleiben, darüber der neutrale Schleier
  `--wahl-schleier` und ein 3 px breiter Rahmen in `--wahl-linie`. Der Statusstreifen rückt in den Rahmen und ist
  in der markierten Zeile 6 px breit, damit er neben dem Rahmen auffällt. Hell und dunkel geprüft.
- **Nicht geändert:** Auswahlmodus (Häkchen, `aria-selected`), Desktop, Wischgesten.
- **Prüfung:** Core-Test `tests/core/test_markierung_status.py`; Browsertest `tests/test_browser_markierung_status.py`
  (rote, gelbe und weiße Zeile bei 390 px: Grundton und Streifen vor und nach dem Tippen gleich, Rahmen vorhanden,
  die drei Status bleiben unterscheidbar).

## D-310 Beschriftung vor den Symbolen im Teilen-Text (Feature `teilen-beschriftung`, 2026-11-27)

- **Anlass (Auftraggeber):** Die Symbole aus D-306 sind nicht immer eindeutig. Nach jedem Symbol steht daher eine
  kurze Beschriftung: „📅 Datum:“, „🏦 Konto:“, „🏷️ Kategorie:“, „🔖 Tags:“ (`oberflaeche.md` 50, ergänzt D-306).
- **Unverändert:** Kopf mit Empfänger und Betrag, Zitat des Verwendungszwecks (als Zitat ohnehin erkennbar), Link
  in der letzten Zeile, Weitergabe.
- **Tests:** `tests/core/test_teilen_format.py` (Eintrag in `tests/core/AENDERUNGEN.md`),
  `tests/test_browser_buchung_teilen.py` (`TESTUMBAU.md`).

## D-311 Kategorienseite mit Beträgen, Nachweis aus dem Kontoblatt einer Kategorie (Feature `kategorien-uebersicht`, 2026-11-27)

- **Anlass:** Arbeitsanweisung vom 2026-11-27: Die Kategorienübersicht sei langweilig und hässlich, sie solle schön
  und gut bedienbar werden; im Kontoblatt einer Kategorie müsse auch der PDF-Export zur Verfügung stehen.
- **Entscheidung Seite** (`oberflaeche.md` 51, `berichte.md` 9): Die Seite bleibt die Verwaltung der Kategorien
  (Baum mit Ziehen, Mehrfachauswahl, Kontextmenü), zeigt aber je Kategorie, wofür sie steht: Summe im Zeitraum samt
  Unterkategorien, Zahl der Buchungen, Verlauf über zwölf Monate und einen Balken. Dazu Kennzahlen (Ausgaben,
  Einnahmen, Überschuss, Buchungen ohne Kategorie mit Link), Suche mit Hervorhebung und Anlegen bei fehlendem Treffer,
  Zeitraum (Vorgabe zwölf Monate), Sortierung nach Name oder Betrag, Auf-/Zuklappen aller Einträge und sichtbare
  Knöpfe je Zeile (Öffnen, Aktionen), damit nichts nur über Doppelklick oder Rechtsklick erreichbar ist.
  - Klick markiert weiter (29.2), Öffnen über Knopf, Doppelklick oder Enter: so bleiben Mehrfachauswahl und
    Zusammenführen unverändert.
  - Vorgabe A–Z, weil die Reihenfolge nach Namen spezifiziert ist (13.1) und beim Verwalten das Wiederfinden zählt;
    „Betrag“ ist eine Wahl im Browser-Speicher.
  - Eigener Endpunkt statt des Kategorienberichts (`/api/berichte/kategorien`): der Bericht rechnet je Monat mit
    Vergleichswerten und lässt Sonderposten weg; die Seite braucht frei wählbare Zeiträume, alle Kategorien (auch
    leere) und die Zahl der Buchungen. Sonderposten zählen hier mit.
  - Der Balken misst an der größten Wurzelkategorie der Gruppe (sonst blieben fast alle Balken winzig); der Anteil an
    der Gruppe steht im Titel der Zeile.
  - Neues Modul `app/kategorien.js` (in `sw.js`); `kategorienBaum` bekommt Optionen für Werte, Suche und Sortierung,
    ohne sie bleibt er im Seitenbereich der Kontoansicht wie bisher.
- **Entscheidung Nachweis** (`berichte.md` 8.1, `oberflaeche.md` 51.1): Der vorhandene Nachweis (D-303) gilt auch für
  Kategorien, statt eines zweiten PDF-Formats. Weil die Buchungen einer Kategorie von mehreren Bankkonten stammen
  können, steht das Bankkonto mit gekürzter IBAN an jeder Buchung, der Kopf nennt Kategorie und Bankkonten. Betrag ist
  der Anteil der Kategorie aus Sicht des Bankkontos (Ausgabe negativ wie auf dem Kontoauszug); bei aufgeteilten
  Buchungen steht der ganze Zahlbetrag als Zusatz dabei. Titel „Buchungsnachweis“, weil es kein Auszug eines Kontos
  ist. „Unkategorisiert“ bleibt ausgenommen.
- **Prüfung:** Core-Test `tests/core/test_kategorien_uebersicht.py`; Browsertest
  `tests/test_browser_kategorien_uebersicht.py`; geänderte Tests in `TESTUMBAU.md` und `tests/core/AENDERUNGEN.md`.

## D-312 Kontotyp änderbar, Kontoinhaber, Kreditkonten mit umgedrehtem Vorzeichen (Feature `konto-typ-inhaber`, 2026-11-27)

- **Anlass:** Arbeitsanweisung vom 2026-11-27: Zu den änderbaren Eigenschaften eines Kontos gehören Kontotyp (Giro,
  Sparbuch, Kreditkonto) und Kontoinhaber (Vorname, Nachname, darf leer bleiben). Kreditkonten haben umgedrehte
  Vorzeichen: eine Abbuchung zählt positiv; in der Finanzübersicht geht der Kontostand negativ ein. Die Sicherung
  muss die neuen Eigenschaften erfassen.
- **Kontotyp:** Die Arten `girokonto`, `sparkonto` und `kreditkonto` gab es schon; neu ist nur, dass sie sich ändern
  lassen. „Sparbuch“ ist `sparkonto`. Gewechselt wird nur innerhalb der Bestandskonten, weil Kategorien andere Regeln
  (Hierarchie, Regeln, Berichte) haben. Das Darlehenskonto eines Kredits bleibt Kreditkonto (sonst wäre der Kredit
  ungültig, `kredite.md`). Werte außerhalb der Bestandsarten sind ein Formfehler (`validierung`), damit der bisherige
  Test „Art nicht änderbar“ (Kategorie → andere Kategorie) unverändert gilt.
- **Vorzeichen nur in der Anzeige:** Die Speicherung bleibt nach der Vorzeichenkonvention (Soll positiv). So ändern
  sich beim Typwechsel keine Buchungen, Bankumsätze und Saldoabgleich behalten das Vorzeichen der Bank, und Berichte,
  Vermögen, Kredite, Regeln und Ausdrücke rechnen weiter richtig. Umgedreht wird dort, wo man das Konto selbst ansieht
  (Kontoblatt, Kontenliste, Abstimmung). Die Finanzübersicht bleibt, wie sie war: der Kontostand eines Kreditkontos
  ist dort negativ und zählt negativ in die Summe. Das gilt auch für Darlehenskonten (Art `kreditkonto`).
  Eingabe im Kontoblatt (Betrag an Ort und Stelle) folgt der Anzeige; der Erfassen-Dialog arbeitet ohnehin mit
  „Ausgabe/Einnahme“ und positivem Betrag. Filter (Ausdrücke, Betrag ab/bis) bleiben bei ihrer Bedeutung: `betrag`
  ohne Vorzeichen, Richtung nach dem gespeicherten Vorzeichen (eine Kartenzahlung ist eine Ausgabe).
- **Inhaber:** eigene Tabelle `konto_inhaber` (statt Spalten an `konto`), damit Sicherungen der Schemaversion ≤ 11
  ohne Spaltenversionen gelesen werden und die Form eines Kontos ohne Inhaber gleich bleibt (Inhaltsprüfsumme,
  Rückgängig älterer Einträge). Im REST und in der Protokollform erscheint `inhaber` nur, wenn er gesetzt ist (wie
  `wiederkehrend` beim Empfänger). Nur bei Bestandskonten; ein Teil darf leer sein.
- **Sicherung:** Schemaversion 12 mit `konto_inhaber`; ältere Sicherungen gelten als ohne Inhaber (3.4). Die
  Sicherungspunkte erfassen die Tabelle über `SPALTEN` automatisch.
- **OpenAPI 2.26.0:** `Konto.inhaber` (optional), `KontoInhaber`, `KontoInhaberEingabe`, `KontoNeu.inhaber`,
  `KontoAenderung.art`/`inhaber`, Codes `art_ungueltig`, `inhaber_ungueltig`.
- **Demodaten:** das Sparbuch hat die erfundene Inhaberin „Tina Muster“.
- **Tests:** `tests/core/test_konto_typ_inhaber.py`, `tests/test_browser_konto_typ_inhaber.py`. Angepasst:
  `tests/core/test_sicherung_stuendlich.py` (`AENDERUNGEN.md`), `tests/test_m6_eigen.py` (Schemaversion 12),
  `gesamt-tests/tests/spec/test_openapi.py` (`TESTUMBAU.md`).

## D-313 Unterkonten im Konto- und Kategorieblatt einblenden, Herkunft je Buchung (Feature `unterkonten-einblenden`, 2026-11-27)

Stand: erster Entwurf in der iterativen Phase, Feinheiten noch mit dem Auftraggeber abzustimmen.

- **Schalter im Kopf:** Neben „Buchung erfassen“ der Umschaltknopf `unterkonten-schalter` (`aria-pressed`),
  beschriftet „mit Unterkonten“ (Bestandskonto) bzw. „mit Unterkategorien“ (Kategorie). Er setzt denselben Filter
  `unterkonten=true` wie das Kontrollkästchen `filter-unterkonten` im Filter-Baukasten (beide zeigen denselben
  Zustand, Beschriftung gleich). Sichtbar nur, wenn das Konto Unterkonten hat (oder der Filter aus der Adresse schon
  gesetzt ist). Die Seite trägt `data-unterkonten="ja|nein"`.
- **Kürzel `f u`** gilt jetzt auch in Kategorien (bisher nur Bestandskonten); ohne Unterkonten ein Hinweis.
- **Herkunft:** Mit eingeblendeten Unterkonten trägt jede Buchung, die einen Split auf einem (auch indirekten)
  Unterkonto hat, vor dem Empfänger eine Marke `herkunft` mit dem Pfad ab dem Konto der Ansicht („Rücklage › Urlaub“
  statt „Giro › Rücklage › Urlaub“), `data-konto-ids`, Tooltip mit vollem Pfad. Mehrere Unterkonten (Split): alle,
  durch „, “ getrennt. Buchungen nur auf dem Konto selbst tragen keine Marke. Rein in der Oberfläche; Endpunkte
  unverändert (`unterkonten` aus `datenmodell.md` 16.1).
- **Warum eine Marke statt einer Spalte:** Die Spaltenraster (Breiten, ausgeblendete Spalten, mobile Anordnung)
  sind je Liste fest; eine Marke wirkt ohne Umbau auch mobil.
- **Tests:** `tests/test_browser_unterkonten.py`.
