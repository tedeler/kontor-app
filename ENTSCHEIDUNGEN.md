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
