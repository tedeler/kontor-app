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
