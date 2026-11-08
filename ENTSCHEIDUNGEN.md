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
