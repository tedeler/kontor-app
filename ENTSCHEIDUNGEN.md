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
