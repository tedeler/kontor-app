# Regeln für die Arbeit in kontor-app

Dieses Repository enthält **Kontor** (Python, FastAPI, SQLite, Single-Page-Weboberfläche) samt Spezifikation
und allen Tests. Alle Dokumente, Kommentare und Commit-Nachrichten sind auf Deutsch.

## Entwicklung und Tests (seit dem Testumbau, `TESTUMBAU.md`)

Das frühere Repository kontor-tests ist aufgegeben; die Trennung in Test- und Implementierungs-Threads gibt es
nicht mehr. Ein Thread schreibt Tests und Code.

- **Spezifikation:** `spec/` (`konzept.md`, `testkonzept.md`, `api/*`, `meilensteine.md`, `definitionen/`). Sie
  wird mit dem Feature fortgeschrieben; Entscheidungen in `ENTSCHEIDUNGEN.md` (fortlaufend `D-0xx`; bestehende
  Einträge nicht umschreiben, sondern durch neue ersetzen/ergänzen).
- **Ablauf eines Features (TDD):**
  1. Branch `feature/<kurzname>`.
  2. **Core-Tests zuerst:** `tests/core/test_<feature>.py`, als eigener Commit vor dem Feature-Code. Regeln in
     `tests/core/README.md`: Verhalten an der Schnittstelle, kein Browser, kein Netz, keine Wartezeiten; der ganze
     Ordner bleibt unter 30 Sekunden (sonst schlägt der Lauf fehl).
  3. Entwickeln gegen `python -m pytest tests/core` (bei Bedarf zusätzlich einzelne Dateien aus `tests/`).
  4. **Core-Test in der Schleife geändert** (Test war falsch oder die Anforderung hat sich geändert): Eintrag in
     `tests/core/AENDERUNGEN.md`. Nie einen Test abschwächen, nur damit er grün wird.
  5. Was nicht in die Core-Tests passt (Browser, Zufallstests, große Daten), kommt nach `tests/`
     (`test_browser_<feature>.py` bekommt automatisch den Marker `browser`).
  6. Ändert das Feature bestehendes Verhalten, die betroffenen Tests in `tests/` und `gesamt-tests/` anpassen und
     in `TESTUMBAU.md` („Geänderte Tests“) vermerken.
  7. Merge auf main (kein Force-Push). Die CI lässt dort die Gesamttests laufen und veröffentlicht nur bei Grün.
- **Gesamttests** laufen nur in der CI auf main, in vier parallelen Jobs mit je unter 5 Minuten: eigene Tests
  (`tests/core`, `tests`), `gesamt-tests` ohne Browser in zwei Teilen, Browser. Lokal nur gezielt ausführen, nicht als Ganzes in der
  Entwicklungsschleife. Aufrufe in `TESTUMBAU.md`. Wird ein Job langsamer als 5 Minuten, Tests kürzen oder
  abwählen (`gesamt-tests/abgewaehlt.txt`), nicht das Budget anheben.
- **`legacy-tests/`** ist der eingefrorene Stand von kontor-tests: nur lesen, nie ändern, nie in die CI.
- Keine Sonderfälle nur für Tests im Anwendungscode (kein Erkennen von Testumgebungen, keine auf Fixtures
  zugeschnittenen Ausnahmen). `WIDERSPRUECHE.md` ist abgeschlossen und wird nicht fortgeführt.

## Daten und Sicherheit

- Niemals echte Bank-, Mail- oder Kreditdaten, nur synthetische Testdaten
  (Test-IBANs mit Bankleitzahl 00000000, Adressen unter `example.invalid`).
- Keine Secrets anlegen oder erfragen. PIN und Tokens erscheinen nie in Logs,
  Datenbank oder Fehlermeldungen.
- Echte Plugins (FinTS, IMAP, ntfy) verbinden sich nur mit den konfigurierten
  Endpunkten; unkonfiguriert bauen sie keine Verbindung auf. Mock-Plugins nie
  mit Netzwerkzugriff. Eigene Prüfungen nur gegen Loopback-Attrappen, nie gegen
  echte Banken, Gmail/Google oder ntfy.sh.
- PIN, TAN und die interne TAN-Kennung des Plugins leben nur im Arbeitsspeicher
  (`SyncDienst`); nie in Datenbank, Logs, Antworten, Fehlermeldungen oder
  `repr()`. Validierungsfehler geben übergebene Werte nie wieder.
- Jede schreibende Operation auf dem Buchbestand (Konten, Empfänger, Tags,
  Buchungen, Regeln, Verdachte, Abstimmungen, gemerkte Kennungen) läuft in
  `protokoll.protokolliert(...)` bzw. über `aendern(...)` in `app.py` – genau
  eine Transaktion je Änderung (ab M4 auch Split-Vorlagen). Neue Tabellen des Buchbestands in
  `protokoll._TABELLEN` und in Protokollform/Wiederherstellung eintragen.
- Beträge sind immer ganze Cent (`int`), nie Gleitkomma – auch nicht im
  Datenbankschema oder in der Oberfläche (Umrechnung nur mit
  Ganzzahlarithmetik).

## Aufbau

| Pfad | Inhalt |
| --- | --- |
| `src/kontor/config.py`, `fehler.py` | Konfiguration und Fehlerklassen (python-api.md 2–3) |
| `src/kontor/app.py` | App-Fabrik, alle REST-Endpunkte, Fehlerformat, Header `X-Kontor-Modus` |
| `src/kontor/validierung.py` | strenge Prüfung von JSON-Körpern und Query-Parametern |
| `src/kontor/buch.py` | Fachlogik: Konten, Buchungen, Splits, Tags, Empfänger, Liste, Dubletten, Benachrichtigungen |
| `src/kontor/bankzugang.py` | Feature fints-camt: Bankzugang aus der Oberfläche (Speicherung, wirksame Konfiguration, TAN-Verfahren und Konten abrufen) |
| `src/kontor/sync.py` | M2: `SyncDienst` je App (Läufe, Übernahme, Abgleich, TAN, PIN, App-Uhr, Planer), `planer_takt` |
| `src/kontor/regeln.py` | M2: Regeln (Validierung, CRUD, Auswertung, Anwenden) und Vorschläge |
| `src/kontor/protokoll.py` | M3: Änderungsprotokoll (temporäre Trigger, Protokollform, Nettowirkung über eine lesende Zweitverbindung), Rückgängig mit Zustands- und Bezugsprüfung, Wirksamkeit |
| `src/kontor/lernmodell.py` | M4: Lernmodell (Merkmale, Naive Bayes mit `Fraction`, Trainingsmenge aus dem Buchbestand, Vorhersage, Anwenden) – keine Gleitkommazahlen, kein gespeicherter Zustand |
| `src/kontor/vorlagen.py` | M4: Split-Vorlagen (Validierung, CRUD, Erkennung, Aufteilen, Anwenden, Konto löschen) |
| `src/kontor/pflege.py` | M3: Empfängerverwaltung, Erfassungshilfe, Umbuchungen, Kontenabstimmung, Volltextsuche, Konto mit Buchungen löschen |
| `src/kontor/kredite.py` | M5: Kredite (Validierung, CRUD, Tilgungsplan mit Ganzzahlarithmetik, Ratenerkennung für Synchronisation und Zuordnen, Jahresabgleich, Bezüge, `verwaiste_entfernen`) |
| `src/kontor/wiederkehrend.py` | M5: Erkennung wiederkehrender Buchungen (ohne Zustand), Ereignisse und Benachrichtigungen |
| `src/kontor/monatsbericht.py` | Feature monatsbericht (D-206): Ausgaben eines Monats rein statistisch (`GET /api/berichte/monat`), nur lesend; Seite `app/monatsbericht.js`; enthält den gemeinsamen Lader `_laden` (Wirkung einer Buchung) |
| `src/kontor/auswertungen.py` | Feature berichte (D-217): Verträge, Jahr, Vorschau, Vermögen, Kategorien, Empfänger, Geldfluss, Datenqualität, Tags (`GET /api/berichte/<name>`, Tabelle `BERICHTE`), nur lesend; Oberfläche `app/berichte.js`, `berichte2.js`, `berichtsteile.js` unter `/berichte?art=<name>` (ein Tab) |
| `src/kontor/bestellmail.py` | Feature amazon-bestellnummer (D-208): Mails mit der Amazon-Bestellnummer einer Buchung als Dokumente anhängen (`mail_bestellnummer`), Tabelle `bestellmail` als Betriebszustand; Aufruf über `abgleich.nach_ereignis` |
| `src/kontor/berichte.py`, `export.py` | M5: Kontostandsverlauf, Einnahmen/Ausgaben; CSV- und PDF-Export (reportlab) der Buchungsliste |
| `src/kontor/sicherung.py` | M9: Datensicherung (eigenes Schema der Sicherungsdatei `SPALTEN`, Version `SCHEMAVERSION`), Prüfung nach sicherung.md 5.1, Inhaltsprüfung in einer App-Datenbank im Arbeitsspeicher, Probelauf, Einspielen |
| `src/kontor/anbieter/` | D-230: Anbieter-Beschreibungen für den Mail-Abgleich (`amazon.toml`, `paypal.toml`, Zusatzdateien aus `anbieter_verzeichnis`); `__init__.py` liest, prüft und wertet sie aus; Format in `ANBIETER.md`. Änderungen an den mitgelieferten Dateien gegen `tests/test_anbieter_eigen.py` prüfen (Vergleich mit `tests/referenz_mailerkennung.py`) |
| `src/kontor/kontonamen.py` | Sammelbranch sammel3 (D-218): Kontonamen je Ebene eindeutig – `pruefen` (409 `konto_existiert`, aufgerufen am Ende von `protokoll.protokolliert`), `bereinigen` (Altbestand, Importe, Sicherung), `freier_name` |
| `src/kontor/umbuchung.py` | Sammelbranch sammel4 (D-242): Zuordnung von Hand auf Kategorie oder Bestandskonto (`zuordnen`, `mehrfach`, `gegenbuchungen`) hinter `PUT /api/buchungen/{id}/kategorie`; beim Bestandskonto Umbuchung, passende Gegenseite des Zielkontos wird zusammengeführt |
| `src/kontor/ausgleich.py` | Feature ausgleich-aufraeumen (D-280, kontostand.md 5): Ausgleichsbuchungen des Saldoabgleichs, die sich innerhalb von sieben Tagen aufheben – `gegenstueck` (beim Abruf), `aufraeumen`/`altbestand_aufraeumen`, `paare`, `zusammenfuehren`, `getrennt_lassen` (Betriebszustand in `meta`); Fenster `ausgleichDialog` in `app/haupt.js` |
| `src/kontor/kompression.py` | D-255: zlib für Mail-Dokumente und Rohfassungen im Mail-Spiegel (`packen`, `entpacken`; Verfahren `zlib`, `''`, `NULL` = Altbestand) |
| `src/kontor/db.py` | SQLite-Schema (Version 18; `mails_packen` und `verkleinern` beim Start, D-255), WAL, Migration früherer Versionen ohne Datenverlust, Verbindungen, `checkpoint` |
| `src/kontor/geheimnisse.py` | M6: verschlüsselter Geheimnisspeicher (AES-256-GCM, Schlüssel aus systemd-creds oder Schlüsseldatei), `verwaiste_entfernen` |
| `src/kontor/mail.py` | M6: Postfächer (Buchbestand), Betriebszustand, OAuth2 mit PKCE, `zugang` (Token-Erneuerung, Ablauf, Widerruf), paralleler Abruf, Spiegel |
| `src/kontor/zustellung.py` | M6: Zustellung der Benachrichtigungen über das Benachrichtigungs-Plugin (erster Versuch, Wiederholung, Status) |
| `src/kontor/netz.py` | M6: ausgehende HTTP-Anfragen ohne Umleitungen/Proxy, TLS-Kontext mit `tls_ca_datei` |
| `src/kontor/importer/` | KMyMoney- und GnuCash-Import (`gnucash.py`: XML und SQLite, SQLite nur als Kopie im Arbeitsspeicher geöffnet) und `ImportErgebnis` |
| `src/kontor/plugins/` | Bank-/Mail-/Benachrichtigungs-Schnittstellen, Mock-Plugins, FinTS (python-fints, camt), IMAP (imaplib, XOAUTH2), ntfy |
| `src/kontor/anmeldung.py` | M7: Haushaltskonto (scrypt), Sitzungen (nur SHA-256 des Tokens gespeichert, CSRF-Token per HMAC abgeleitet), Bremse, Einrichtungscode, Kommandozeile `passwort-setzen` |
| `src/kontor/schutz.py` | M7: äußerste ASGI-Hülle: Netz → Sitzung → Herkunft → CSRF → Größe; Sicherheitsköpfe an jeder Antwort |
| `src/kontor/betrieb/` | M7: ausgelieferte systemd-Units, sysusers, `kontor.env`, Drop-in (Paketdaten) |
| `src/kontor/testinstanz.py`, `betrieb/kontor-test.*` | Feature testinstanz (D-205): zweite Instanz für einen Entwicklungsbranch (Mock-Modus, bereinigte Datenkopie); Kommandozeile `python -m kontor.testinstanz`; Bedienskript `betrieb/kontor-test.sh` und Anleitung `TESTINSTANZ.md` (D-213) |
| `src/kontor/demowelt.py`, `demodaten.py` | Feature demodaten (D-285): erfundener Haushalt für die Testinstanz – `demowelt` erzeugt Umsätze und Mails samt Wahrheit (rein, reproduzierbar) und die Mock-Datendatei; `demodaten.aufbauen` baut die Mock-Datenbank nur über die REST-Schnittstelle (ASGI im selben Prozess, simulierte Uhr); Kommandozeile `python -m kontor.demodaten`, aufgerufen von `python -m kontor.testinstanz demo` (`kontor-test demo`, ohne Anmeldung, Zusatz-Umgebungsdatei über ein Drop-in) |
| `src/kontor/betrieb/kontor-https.sh`, `HTTPS.md` | D-239: Betrieb nur über HTTPS mit Tailscale Serve – `kontor-https einrichten/status/zurueck` stellt Haupt- und Testinstanz um (drei Variablen der Umgebungsdateien, Sicherung `*.vor-https`); `kontor-test.sh` schaltet die Freigabe der Testinstanz ein und aus. Tests mit Attrappen: `tests/test_https_skript_eigen.py` |
| `src/kontor/__main__.py` | M7: Startmodul `python -m kontor` (ohne Argumente, Logging nach stderr, uvicorn) |
| `src/kontor/web/` | M8: Hülle `index.html`, Service Worker `sw.js`, Anmeldeseite `anmelden.html`; unter `oeffentlich/` Stile `app.css`, Symbole, Manifest und die ES-Module `app/` (`kern`, `ui`, `baum`, `konto`, `seiten`, `einstellungen`, `haupt`), ohne externe Ressourcen |
| `src/kontor/VERSION`, `version.py`, `release.py` | Versionsnummer `MAJOR.MINOR`, Build-Angaben aus `build.json`, Kommandozeile der Release-CI (D-105) |
| `.github/workflows/release.yml` | CI: bei jedem Push auf main Gesamttests in vier Jobs, danach Release mit Minor + 1; Major nur von Hand (D-105) |
| `tests/core/` | Core-Tests der Entwicklungsschleife (Marker `core`, zusammen unter 30 Sekunden) |
| `tests/` | eigene Tests je Feature; `test_browser*.py` mit Marker `browser` |
| `gesamt-tests/` | Gesamtsuite: gekürzte frühere Abnahmetests mit eigener `pytest.ini`, Fixtures und Generator |
| `legacy-tests/` | eingefrorener Stand von kontor-tests (nur Referenz) |
| `spec/` | Spezifikation |

## Hinweise ab Meilenstein 4

- Stufenfolge neuer Bankumsätze in `sync._abgleichen_und_buchen`: Vorlage →
  Regel → Standardkategorie → Lernmodell (nur `lernmodell_automatisch`) →
  „Unkategorisiert“. Das Lernmodell wird je Bankkonto einmal zu Beginn
  trainiert; für Umsätze mit eigener Gegen-IBAN nie befragt.
- Gelöschte Bankkonten (synchronisation.md 16): `sync_konto_zustand` trägt
  die Entscheidung (Betriebszustand, nicht protokolliert); der Status wird
  immer abgeleitet. Wiederherstellende Kontozuordnungen werden in
  `sync_wiederherstellung` vermerkt, damit Rückgängig den Eintrag behält
  (protokoll.md 6.4). Nach M4-Datenmodelländerungen auch an Meilenstein 9
  (Datensicherung) denken.
## Hinweise ab Meilenstein 9 (Datensicherung)

- **Jeder neue fachliche Zustand gehört in die Sicherung** (sicherung.md 2.3):
  neue Tabelle des Buchbestands in `sicherung.SPALTEN`, `BUCH_TABELLEN`,
  `_LOESCHEN` und ggf. `ZAEHLER` eintragen, neue Objektart in
  `protokoll.OBJEKTE` (damit `anzahl` und Inhaltsprüfsumme sie erfassen) und
  `OBJEKTE_JE_VERSION`; `SCHEMAVERSION` der Sicherungsdatei erhöhen und für die
  alte Version eine Migration beim Einspielen vorsehen (3.4). Geheimnisse
  (PIN, Tokens) nie, auch nicht verschlüsselt.
- Das Einspielen ersetzt den Buchbestand in `protokoll.protokolliert` (eine
  Änderung `sicherung_einspielen`); der Zustand je Bankkonto wird vorher/nachher
  in `sicherung_zustand` vermerkt, damit Rückgängig/Wiederholen ihn herstellen
  (protokoll.md 10.2). Während des Einspielens hält `SyncDienst.ohne_lauf()`
  die Laufsperre.

## Hinweise ab Meilenstein 5

- Kredite: Tabellen `kredit`, `kredit_zuordnung`, `kredit_abgleich` (eine
  Objektart `kredit` in `protokoll._TABELLEN`). Zuordnungen haben bewusst
  keinen Fremdschlüssel auf Buchungen; `protokoll.protokolliert` ruft am Ende
  jeder Operation `kredite.verwaiste_entfernen` auf (Zuordnung gelöschter
  Buchungen entfällt in derselben Änderung). Konten mit Kreditbezug sind nicht
  löschbar (`kredite.konto_pruefen`).
- Stufenfolge neuer Bankumsätze: Kreditrate (Stufe 0) → Vorlage → Regel →
  Standardkategorie → Lernmodell → „Unkategorisiert“.
- Sicherungsdatei Schemaversion 2: Kredittabellen; `kredit` steht in `anzahl`
  und Inhaltsprüfsumme nur, wenn Kredite vorhanden sind
  (`sicherung.OBJEKTE_OPTIONAL`); Sicherungen der Version 1 werden ohne
  Kredittabellen gelesen (`TABELLEN_AB`). Künftige Objektarten genauso.
- Wiederkehrende Buchungen, Berichte und Export haben keinen Zustand; nur
  Benachrichtigungen werden gespeichert (je Schlüssel höchstens eine).
- Beträge im PDF/CSV nur über Ganzzahlarithmetik formatieren (`export.betrag_text`).

## Hinweise ab Meilenstein 6

- **Geheimnisse** (PIN, TAN, Tokens, Client-Secret, ntfy-Token, Schlüssel, `state`/`code_verifier`) nie in
  Datenbank (nur Chiffretext in `geheimnis`), Logs, Antworten, Fehlermeldungen, `details`, `repr()`, Sicherung
  oder Kommandozeile. Bibliotheks-Logger: `fints` ist stillgelegt (`plugins/fints.bibliothek_stilllegen`), das
  Zugriffsprotokoll von uvicorn ohne Abfrageteil (`app.protokolle_absichern`). Fremde Ausnahmetexte nie
  weitergeben (`raise … from None`).
- **Neue Benachrichtigungen** wie bisher in die Tabelle schreiben; die Zustellung erledigt `zustellung.py`
  (Trigger setzt `ausstehend`, erster Versuch am Ende jeder REST-Anfrage und jedes Planer-Takts). Antworten, die
  Benachrichtigungen enthalten, erst nach der Zustellung lesen.
- **Postfach-Betriebszustand** hängt an `adresse_cf`; alles ohne Postfach entfernt `geheimnisse.verwaiste_entfernen`
  am Ende von `protokoll.protokolliert`. Sicherungsdatei Schemaversion 3 (`postfach`, nur bei Vorhandensein in
  `anzahl`).
- Planer-Takt in der Reihenfolge von `synchronisation.md` 18.2 (`SyncDienst.takt`).

## Hinweise ab Meilenstein 7

- **Neue Endpunkte sind automatisch geschützt** (`schutz.py`); öffentlich sind nur die Pfade aus
  `sicherheit.md` 3.1 (`schutz.OEFFENTLICH`). Neue Upload-Endpunkte in `schutz.UPLOADS` eintragen.
- Anmeldedaten (`anmeldung_konto`, `sitzung`) sind Betriebszustand: nie in `protokoll._TABELLEN`, nie in
  `sicherung.SPALTEN`. Zeiten der Anmeldung immer nach `time.time()`, nie nach der Mock-Uhr.
- Weboberfläche: kein Inline-Skript, keine `on…`-Attribute, kein `eval`/`new Function` (CSP
  `script-src 'self'`); schreibende `fetch`-Aufrufe nur über `api()` in `app/kern.js` (sendet `X-Kontor-CSRF`).
  Browsertests nicht mit `page.wait_for_function("…")` (String-Auswertung), sondern `warte_js`.
- Lange Lesezugriffe: Filter als unkorrelierte Teilabfragen (`b.id IN (SELECT …)`), in korrelierten
  Teilabfragen mit `+s.konto_id` den falschen Index vermeiden. Leistung prüfen mit
  `python -m pytest -m leistung` (eigene Messung: `/home/claude/impl/werkzeug/messen.py`, nicht im Repo).
- Beenden: `SyncDienst.beenden` (Frist, `_schreib_sperre`/`_abbruch`), danach `db.checkpoint`.
- Die Leistungstests (Marker `leistung`) laufen nicht in der CI; nach Änderungen an langen Lesezugriffen von Hand:
  `cd gesamt-tests && python -m pytest --alle -m leistung`.

## Hinweise ab Meilenstein 8 (Oberfläche)

- Vertrag ist `oberflaeche.md`: `data-testid`, Rollen, Zustandsattribute (`data-geladen`, `data-bereit`,
  `data-layout`, `data-betrag` in Cent …). Texte aus dem Buchbestand nur über `h()`/`textContent`, nie HTML.
- Jede Operation mit Wirkung auf den Buchbestand in der Oberfläche läuft über `aktion()` (`kern.js`): legt den
  Rückgängig-Eintrag an und lädt danach mit dem Stand des Servers neu (`oberflaeche.neuLaden`). Dialoge mit
  `danach: () => d.schliessen(true)` vor dem Neuladen schließen; Fehler in Dialogen über `imDialog`.
- Neue Routen in `SPA_ROUTEN` (`app.py`) **und** in `ROUTEN` (`haupt.js`) eintragen; neue Moduldateien in
  `DATEIEN` von `sw.js` (eigener Test). Keine Sammelroute für GET (würde 405 der REST-Pfade verdecken).
- Browsertests: eigene `tests/test_browser*.py`, dazu `cd gesamt-tests && python -m pytest -m browser -n 2`.

## Hinweise zum Bankabruf über FinTS/camt (Feature `fints-camt`, D-197 bis D-201)

- Das AqBanking-Plugin (M10) ist entfallen; es gibt nur noch `mock` und `fints`. Umsätze kommen über `HKCAZ`
  (camt.052.001.02–.08, `plugins/fints.CAMT_FORMATE`); bietet die Bank camt an, nie auf MT940 ausweichen.
- Bankzugang aus der Oberfläche: `bankzugang.py` (Speicherung in `meta`, Schlüssel `bank_…`; Betriebszustand, nie
  Protokoll oder Sicherung, nie die PIN). `SyncDienst._plugin_holen` nimmt die wirksame Konfiguration; nach
  jeder Änderung `plugin_verwerfen()`. Aufrufe mit Bankverbindung nur unter der Laufsperre (`bankzugang._Gesperrt`).
- TAN beim Dialogbeginn: `konten(tan=…)`/`umsaetze(tan=…)` setzen denselben Dialog fort; die interne Kennung
  verlässt den Arbeitsspeicher nie (Oberfläche bekommt einen eigenen `vorgang`).
- Diagnoseprotokoll (D-203): `plugins/fints_diagnose.py` arbeitet mit einer Positivliste. Neue Angaben nur
  aufnehmen, wenn sie keine persönlichen Daten sind (nie Werte aus Kontoverbindungen, Kennungen, Referenzen,
  Freitexte ohne `bereinigen`); der Test `test_diagnose_enthaelt_keine_persoenlichen_daten` muss sie abdecken.
- Übergang alter Kennungen: `sync_kennung_alt` (einmal gefüllt, `meta.bank_uebergang`) und
  `SyncDienst._uebergang_abgleichen`.

## Hinweise ab Meilenstein 11 (Kontostand, Kategorien, Zusammenführen)

- `umsaetze()` aller Bank-Plugins liefert `plugins.bank.Umsatzliste` mit `saldo` (`BankSaldo` oder None); keine
  neue öffentliche Plugin-Methode. Saldoabgleich in `SyncDienst._saldo_abgleichen` (D-102), Ergebnis als JSON in
  `sync_lauf_konto.saldo_abgleich`.
- Buchungsliste: `unterkonten` bildet die Kontenmenge über `buch._listenkonten`; `buchungen_laden(konten=…)`.
- Oberfläche: Kontoansicht kennt `istKategorie` (Spalte `konto`, Filter `filter-konto`), URL ohne
  Vorgabesortierung (D-104).

## Hinweise zum Sammelbranch `feature/sammel3` (D-218 bis D-226)

- Neue Konten nie mit rohem `INSERT` und fremdem Namen anlegen, ohne `kontonamen.freier_name` oder die Prüfung zu
  bedenken: gleichnamige Geschwister lehnt `protokolliert` mit 409 ab.
- Die Standardkategorie je Empfänger ist entfallen (D-219); die Stufenfolge oben gilt ohne sie. Das Feld
  `standardkategorie_id` bleibt in der Empfängerform und ist immer `null`.
- Bestätigungs-Tags heißen „B-<Name>“ (`personTag`/`personVonTag` in `app/kern.js`, D-223).
- `/statistik` und `GET /api/statistik` gibt es nicht mehr (D-221); `/tags` ist neu (D-225).
- Geplante Zahlungen (D-238): Wiederholung in `erwartung_wiederholung` (Teil der Objektart `erwartung`,
  Sicherungsdatei Schemaversion 10); Fortsetzung und Rücknahme in `erwartung.folge_anlegen`/`folge_entfernen`, Vorschau über
  `erwartung.geplante`. Das Feld `wiederholung` erscheint nur, wenn eine besteht.
- Änderungsprotokoll: Seite `/protokoll` und Einzelheiten je Änderung liegen in `app/aenderung.js` (D-237, D-294;
  Quellen mit Bezeichnung und Farbton in `QUELLEN`, Filter in `FILTER`). Neue Felder der Protokollform
  bekommen dort einen Namen in `FELD_NAMEN` (sonst erscheint der Schlüssel) und ggf. eine Deutung in `wertText`.

## Hinweise zum Sammelbranch `feature/sammel4` (ab D-242)

- `kategorie_id` der Zuordnung von Hand kann ein Bestandskonto sein (D-242). Wer Buchungen nach „genau ein
  Gegensplit“ behandelt, muss Umbuchungen aus zwei Bestandssplits bedenken (`umbuchung.ziel_split`).
- Die Synchronisation hängt einen Umsatz an eine bestehende Umbuchung, deren Seite auf diesem Konto noch keinen
  Bankumsatz trägt (Betrag gleich, Datum im Fenster `umbuchung_fenster_tage`).
- Regeln, Vorlagen und Lernmodell kennen weiter nur Kategorien als Ziel.

## Hinweise zum Kopfabruf (Feature `kopfabruf`, D-243)

- Mit `mail_nur_koepfe` kann eine Zeile in `mail_nachricht` nur Kopfzeilen tragen (`inhalt = 0`, `text` leer,
  `roh` NULL). Wer Text oder Rohfassung einer Mail braucht, die nicht über die Vorauswahl kam, lädt vorher mit
  `MailDienst.inhalt_laden` nach (Netz, nie in einer offenen Transaktion).
- Jede Anbieter-Beschreibung braucht eine Vorauswahl (`absender` und/oder `betreff`); `Anbieter.gehoert` immer mit
  Absender **und** Betreff aufrufen.

## Hinweise zur Speicherung von Mails (Feature `mail-schlank`, D-255)

- `dokument_inhalt.inhalt` und `mail_nachricht.roh` nie direkt lesen: `dokumente.inhalt_bytes(con, sha)` bzw.
  `dokumente.spiegel_roh(con, zeile)` (Zeile mit `roh`, `roh_verfahren`, `roh_sha256`) liefern die Originalbytes.
  Schreiben nur über `dokumente.inhalt_speichern` bzw. `dokumente.spiegel_packen`.
- Wer eine gespiegelte Mail als Dokument anlegt, ruft danach `dokumente.spiegel_verweisen` auf (keine zweite Kopie).

## Hinweise zu den Einstellungen (Feature `einstellungen`, D-207)

- `app/einstellungen.js`: Bereiche (`BEREICHE`), Adresse `/einstellungen?bereich=<name>` (ein Tab), Suche über
  `VERZEICHNIS`. Eine neue Einstellung bekommt `data-einstellung="<schlüssel>"` und einen Eintrag im Verzeichnis
  (Titel, Synonyme); Seltenes gehört in `erweitert(…)`. Stand des Bereichs in `staende()` nachführen.
- Bisherige `data-testid` der Einstellungen nicht umbenennen. Eigener Rauchtest: `tests/test_browser_einstellungen.py`.

## Hinweise zu den Demodaten (Feature `demodaten`, D-285)

- Der Aufbau benutzt nur REST. Ändert ein Feature Anfragen oder Antworten, die `demodaten.py` verwendet, schlägt
  `tests/core/test_demodaten.py` fehl; dann den Aufbau nachziehen. Neue Funktionen, die sich zeigen lassen
  sollen, bekommen Stoff in `demowelt.py` (Umsätze, Mails) und einen Schritt in `demodaten.py`.
- Nur erfundene Angaben (Test-IBANs, `example.invalid`); nie aus einer Datenbank oder Datei lesen.
- Die ausgelieferte `kontor-test.service` nicht für die Demo ändern (`betrieb.md` 9); Demo-Einstellungen gehören
  in `testinstanz.DEMO_ENV`.

## Hinweise zum Logo der Testinstanz (Feature `testinstanz-logo`, D-286)

- Im Mock-Modus liefert `app.py` unter den Adressen der Symbole die Dateien `web/oeffentlich/testinstanz-icon*`
  und ändert Namen und Farbe in Manifest, Hülle und Anmeldeseite (`TEST_NAME`, `TEST_FARBE`, `_als_testinstanz`).
  Ein neues Symbol im Manifest braucht deshalb auch eine Fassung für die Testinstanz und einen Eintrag in
  `TEST_SYMBOLE`.

## Hinweise zur Versionierung (D-105)

- Die Version nie von Hand in `VERSION` ändern; das macht nur die Release-CI beim Push auf main. Nach einem
  Merge daher `git pull` (die CI committet „Version x.yy veröffentlicht“ auf main).
- Neue Angaben im About-Fenster über `GET /api/version` (`app.py`) und `ueberOeffnen` (`haupt.js`).

## Hinweise ab Meilenstein 17 (Tabs, Gegenbuchung)

- Jede Ansicht ist ein Tab (`app/tabs.js`, Router `zeigen` in `haupt.js`): inaktive Tabs hängen nicht im Dokument,
  behalten aber DOM und Seitenobjekt. Seiten können `aktualisieren()` (Neuladen nach Änderung, auch für veraltete
  Tabs), `layoutGeaendert()`, `wiederAngefordert()` (Anfordern über Navigation) und `buchungZeigen(id)` anbieten.
- Filter der Kontoansicht über `urlSchreiben` melden sich mit `oberflaeche.urlGeaendert()` beim Tab.
- Browser-Speicher nur in `try` lesen/schreiben (M17 1.6).

## Hinweise zur Tastaturbedienung (Feature `tastatur`, D-287)

- Bereichswechsel mit der Vortaste `w` und F6 liegt in `app/haupt.js` (`BEREICH_ZIELE`, `bereichTaste`). Eine Seite
  mit eigenen Bereichen bietet `bereiche()` an: Liste aus `{ taste, text, tun, el }` in der Reihenfolge von F6
  (Vorbild `konto.js`). Hinweis, Hilfe und Befehlspalette lesen dieselbe Liste.
- `w` darf auf keiner Seite ein Kürzel ohne Vortaste werden.
- Belegung nach D-292 (`oberflaeche.md` 46): keine Satzzeichen; `u`/`d`/`U`/`D` (bewegen) und `h` (Hilfe) sind
  global und dürfen im Kontoblatt nicht ohne Vortaste belegt werden. Neue Kürzel in `KUERZEL` (`konto.js`) mit
  Bedingung für die Hilfe (`eine`, `person`, `bestand`); Seiten ohne `bereiche()` melden ihre `w`-Ziele in
  `BLATT_ZIELE` und ihre Listentasten in `HILFE_LISTE` (`haupt.js`).

## Hinweise zur sofortigen Wirkung im Kontoblatt (D-289, D-290)

- Aktionen auf Buchungen im Kontoblatt laufen über `Kontoansicht.sofort(ids, patch, ausfuehren, optionen)` statt
  direkt über `aktion()`: `patch(b)` ändert die geladene Buchung so, wie es der Server tun wird (Regeln dort
  nachlesen und in `tests/core/test_aktionen_sofort.py` gegen die REST-Schnittstelle absichern), `ausfuehren()`
  schickt die Anfragen. Steht die Wirkung nicht fest, ein leerer `patch`.
- Werte für die Anfrage (z. B. „welche Buchungen sind noch unbestätigt“) vor dem Aufruf von `sofort` bestimmen;
  danach sind die geladenen Buchungen schon geändert.
- Neue Tags über `tagHolen` (`kern.js`) anlegen. Browsertests warten nach solchen Aktionen auf
  `data-ausstehend="0"` an `seite-konto`, bevor sie mit Zeilen weiterarbeiten.

## Codequalität vor jedem Meilenstein

- **Vor Beginn jedes neuen Meilensteins** die Codequalitätsanalyse nach
  `refactor.md` („Ablauf der Analyse“) wiederholen: Kennzahlentabelle um eine
  Zeile ergänzen, Bewertung und Maßnahmenliste (`R-xx`) fortschreiben, als
  eigenen Commit („Mx: Codequalitätsanalyse“) vor der ersten Änderung des
  Meilensteins.
- Verschlechtert sich eine Kennzahl gegenüber der Vorzeile (mehr mypy-Fehler,
  mehr Funktionen mit radon D/E/F, echte SQL-Funde), die Ursache benennen und
  eine Maßnahme anlegen. Echte SQL-Funde und neue unbegründete breite
  `except` vor dem Meilenstein beheben.
- Refactorings ändern kein Verhalten; Maßstab sind die Gesamttests.
  Neue Funktionen mit C901 ≤ 15, Überschreitungen begründen.

## Arbeitsablauf

1. `pip install --break-system-packages -e ".[test]"` im Wurzelverzeichnis.
2. Entwicklungsschleife: `python -m pytest tests/core` (siehe oben).
3. Gezielte Läufe aus `tests/` und `gesamt-tests/` nach Bedarf; Browsertests starten eigene Server auf freien
   lokalen Ports und beenden sie wieder.
4. Oberfläche prüfen: Server im Mock-Modus starten (siehe README), Seiten und Assets abrufen; gestartete
   Server-Prozesse danach beenden.
5. Nach dem Merge den CI-Lauf auf main ansehen (`gh run list --branch main`); ist ein Job rot oder über
   5 Minuten, sofort beheben.

## Git

- `user.name` „Kontor Impl-Thread“; E-Mail und Signierung nicht ändern.
- Auf dem Feature-Branch in kleinen Schritten committen und pushen; main nur per Merge. Keine Pull Requests,
  kein Force-Push. Nach einem Merge `git pull` (die CI committet „Version x.yy veröffentlicht“ auf main).
- Im Projektchat immer auf Deutsch.
