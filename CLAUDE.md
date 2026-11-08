# Regeln für Implementierungs-Threads in kontor-app

Dieses Repository enthält die Implementierung von **Kontor** (Python,
FastAPI, SQLite, Single-Page-Weboberfläche). Alle Dokumente, Kommentare und
Commit-Nachrichten sind auf Deutsch.

## Rollentrennung (unbedingt einhalten)

- **Implementierungs-Threads** arbeiten hier. Spezifikation und Tests liegen
  im Repository **kontor-tests**; es ist für Implementierungs-Threads **nur
  lesbar**: nie ändern, nie committen, nie pushen.
- Ein Verzeichnis von kontor-tests, das einem Test-Thread gehört (z. B.
  `/home/claude/kontor-tests`), nicht betreten und nicht benutzen. Stattdessen
  einen eigenen Lese-Klon anlegen und das Pushen sperren:
  ```bash
  git clone https://github.com/tedeler/kontor-tests /home/claude/impl/kontor-tests-ro
  git -C /home/claude/impl/kontor-tests-ro remote set-url --push origin GESPERRT-nur-lesen
  git -C /home/claude/impl/kontor-tests-ro pull     # nur so aktualisieren
  ```
- **Test-Threads** fügen sich kontor-app nie hinzu und lesen keinen
  Anwendungscode.
- **Maßgeblich ist die Spezifikation** (`kontor-tests/spec/konzept.md`,
  `spec/api/datenmodell.md`, `python-api.md`, `openapi.yaml`, `plugins.md`,
  `entscheidungen.md`). Tests dürfen gelesen werden, um Fehlschläge zu
  verstehen.
- **Widerspricht ein Test der Spezifikation:** Test nicht ändern, nicht
  umgehen, keine Sonderfälle nur für Tests (kein Erkennen von
  Testumgebungen, keine auf Fixtures zugeschnittenen Ausnahmen). Stattdessen
  in `WIDERSPRUECHE.md` einen Eintrag `W-xxx` anlegen (Testdatei/Testname,
  was der Test erwartet, was die Spezifikation sagt mit Fundstelle, warum das
  widersprüchlich ist) – als Text, ohne Code aus kontor-app. Gelöst wird der
  Widerspruch nur von einem Test-Thread.
- Offene Entscheidungen selbst treffen und in `ENTSCHEIDUNGEN.md`
  dokumentieren (fortlaufend `D-0xx`; bestehende Einträge nicht umschreiben,
  sondern durch neue ersetzen/ergänzen).

## Daten und Sicherheit

- Niemals echte Bank-, Mail- oder Kreditdaten, nur synthetische Testdaten
  (Test-IBANs mit Bankleitzahl 00000000, Adressen unter `example.invalid`).
- Keine Secrets anlegen oder erfragen. PIN und Tokens erscheinen nie in Logs,
  Datenbank oder Fehlermeldungen.
- Echte Plugins (FinTS, IMAP) bauen bis Meilenstein 6 keine Verbindungen auf.
  Mock-Plugins nie mit Netzwerkzugriff.
- PIN, TAN und die interne TAN-Kennung des Plugins leben nur im Arbeitsspeicher
  (`SyncDienst`); nie in Datenbank, Logs, Antworten, Fehlermeldungen oder
  `repr()`. Validierungsfehler geben übergebene Werte nie wieder.
- Jede schreibende Operation auf dem Buchbestand (Konten, Empfänger, Tags,
  Buchungen, Regeln, Verdachte, Abstimmungen, gemerkte Kennungen) läuft in
  `protokoll.protokolliert(...)` bzw. über `aendern(...)` in `app.py` – genau
  eine Transaktion je Änderung. Neue Tabellen des Buchbestands in
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
| `src/kontor/sync.py` | M2: `SyncDienst` je App (Läufe, Übernahme, Abgleich, TAN, PIN, App-Uhr, Planer), `planer_takt` |
| `src/kontor/regeln.py` | M2: Regeln (Validierung, CRUD, Auswertung, Anwenden) und Vorschläge |
| `src/kontor/protokoll.py` | M3: Änderungsprotokoll (temporäre Trigger, Protokollform, Nettowirkung über eine lesende Zweitverbindung), Rückgängig mit Zustands- und Bezugsprüfung, Wirksamkeit |
| `src/kontor/pflege.py` | M3: Empfängerverwaltung, Erfassungshilfe, Umbuchungen, Kontenabstimmung, Volltextsuche, Konto mit Buchungen löschen |
| `src/kontor/db.py` | SQLite-Schema (Version 3), Migration früherer Versionen, Verbindungen |
| `src/kontor/importer/` | KMyMoney-Import und `ImportErgebnis` |
| `src/kontor/plugins/` | Bank-/Mail-Schnittstellen, Mock-Plugins, FinTS-/IMAP-Platzhalter |
| `src/kontor/web/` | Weboberfläche (HTML, CSS, Vanilla-JS, ohne externe Ressourcen) |
| `tests/` | eigene Tests (ergänzend; ersetzen nicht die Tests aus kontor-tests) |

## Arbeitsablauf

1. `pip install --break-system-packages -e /home/claude/impl/kontor-app`
2. Tests nach `kontor-tests/TESTS_AUSFUEHREN.md` aus dem Lese-Klon heraus:
   `cd /home/claude/impl/kontor-tests-ro && python -m pytest -p no:cacheprovider`
3. Eigene Tests: `python -m pytest tests` in kontor-app (inkl. Playwright-Rauchtests
   `tests/test_browser*.py`, die eigene Server auf freien lokalen Ports starten und
   wieder beenden).
4. Oberfläche prüfen: Server im Mock-Modus starten (siehe README), Seiten und
   Assets abrufen; gestartete Server-Prozesse danach beenden.
5. Am Ende vollständiger Testlauf nach `git pull` im Lese-Klon, Ergebnis in
   `ERGEBNIS.md` (Zahlen, Fehlschläge mit Verweis auf W-Einträge, Stand-Commit
   von kontor-tests, Einschränkungen).

## Git

- `user.name` „Kontor Impl-Thread“; E-Mail und Signierung nicht ändern.
- Direkt auf `main` committen und pushen, in kleinen Schritten. Keine
  Branches, keine Pull Requests, kein Force-Push. Vor jedem Push
  `git pull --rebase origin main`.
- Im Projektchat nur posten, wenn alles fertig ist oder etwas wirklich
  blockiert – auf Deutsch.
