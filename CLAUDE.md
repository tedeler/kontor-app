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
| `src/kontor/sync.py` | M2: `SyncDienst` je App (Läufe, Übernahme, Abgleich, TAN, PIN, App-Uhr, Planer), `planer_takt` |
| `src/kontor/regeln.py` | M2: Regeln (Validierung, CRUD, Auswertung, Anwenden) und Vorschläge |
| `src/kontor/protokoll.py` | M3: Änderungsprotokoll (temporäre Trigger, Protokollform, Nettowirkung über eine lesende Zweitverbindung), Rückgängig mit Zustands- und Bezugsprüfung, Wirksamkeit |
| `src/kontor/lernmodell.py` | M4: Lernmodell (Merkmale, Naive Bayes mit `Fraction`, Trainingsmenge aus dem Buchbestand, Vorhersage, Anwenden) – keine Gleitkommazahlen, kein gespeicherter Zustand |
| `src/kontor/vorlagen.py` | M4: Split-Vorlagen (Validierung, CRUD, Erkennung, Aufteilen, Anwenden, Konto löschen) |
| `src/kontor/pflege.py` | M3: Empfängerverwaltung, Erfassungshilfe, Umbuchungen, Kontenabstimmung, Volltextsuche, Konto mit Buchungen löschen |
| `src/kontor/kredite.py` | M5: Kredite (Validierung, CRUD, Tilgungsplan mit Ganzzahlarithmetik, Ratenerkennung für Synchronisation und Zuordnen, Jahresabgleich, Bezüge, `verwaiste_entfernen`) |
| `src/kontor/wiederkehrend.py` | M5: Erkennung wiederkehrender Buchungen (ohne Zustand), Ereignisse und Benachrichtigungen |
| `src/kontor/berichte.py`, `export.py` | M5: Kontostandsverlauf, Einnahmen/Ausgaben; CSV- und PDF-Export (reportlab) der Buchungsliste |
| `src/kontor/sicherung.py` | M9: Datensicherung (eigenes Schema der Sicherungsdatei `SPALTEN`, Version `SCHEMAVERSION`), Prüfung nach sicherung.md 5.1, Inhaltsprüfung in einer App-Datenbank im Arbeitsspeicher, Probelauf, Einspielen |
| `src/kontor/db.py` | SQLite-Schema (Version 9), WAL, Migration früherer Versionen ohne Datenverlust, Verbindungen, `checkpoint` |
| `src/kontor/geheimnisse.py` | M6: verschlüsselter Geheimnisspeicher (AES-256-GCM, Schlüssel aus systemd-creds oder Schlüsseldatei), `verwaiste_entfernen` |
| `src/kontor/mail.py` | M6: Postfächer (Buchbestand), Betriebszustand, OAuth2 mit PKCE, `zugang` (Token-Erneuerung, Ablauf, Widerruf), paralleler Abruf, Spiegel |
| `src/kontor/zustellung.py` | M6: Zustellung der Benachrichtigungen über das Benachrichtigungs-Plugin (erster Versuch, Wiederholung, Status) |
| `src/kontor/netz.py` | M6: ausgehende HTTP-Anfragen ohne Umleitungen/Proxy, TLS-Kontext mit `tls_ca_datei` |
| `src/kontor/importer/` | KMyMoney- und GnuCash-Import (`gnucash.py`: XML und SQLite, SQLite nur als Kopie im Arbeitsspeicher geöffnet) und `ImportErgebnis` |
| `src/kontor/plugins/` | Bank-/Mail-/Benachrichtigungs-Schnittstellen, Mock-Plugins, FinTS (python-fints), AqBanking (M10, `aqbanking-cli` als Unterprozess), IMAP (imaplib, XOAUTH2), ntfy |
| `src/kontor/anmeldung.py` | M7: Haushaltskonto (scrypt), Sitzungen (nur SHA-256 des Tokens gespeichert, CSRF-Token per HMAC abgeleitet), Bremse, Einrichtungscode, Kommandozeile `passwort-setzen` |
| `src/kontor/schutz.py` | M7: äußerste ASGI-Hülle: Netz → Sitzung → Herkunft → CSRF → Größe; Sicherheitsköpfe an jeder Antwort |
| `src/kontor/betrieb/` | M7: ausgelieferte systemd-Units, sysusers, `kontor.env`, Drop-in (Paketdaten) |
| `src/kontor/__main__.py` | M7: Startmodul `python -m kontor` (ohne Argumente, Logging nach stderr, uvicorn) |
| `src/kontor/web/` | M8: Hülle `index.html`, Service Worker `sw.js`, Anmeldeseite `anmelden.html`; unter `oeffentlich/` Stile `app.css`, Symbole, Manifest und die ES-Module `app/` (`kern`, `ui`, `baum`, `konto`, `seiten`, `haupt`), ohne externe Ressourcen |
| `src/kontor/VERSION`, `version.py`, `release.py` | Versionsnummer `MAJOR.MINOR`, Build-Angaben aus `build.json`, Kommandozeile der Release-CI (D-105) |
| `.github/workflows/release.yml` | Release-CI: bei jedem Push auf main Minor + 1, Major nur von Hand (D-105) |
| `tests/` | eigene Tests (ergänzend; ersetzen nicht die Tests aus kontor-tests) |

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
- Maßstab für „grün“: `python -m pytest` im Lese-Klon; Tests späterer
  Meilensteine (Marker `m7`, `m8`) erst, wenn beauftragt
  (`-m "not m7 and not m8"`).

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
- Maßstab: Tests mit Marker `m6` gehören dazu (ab M7 auch `m7`, siehe unten).

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
- Maßstab: alle Tests einschließlich `m7` und `leistung`; `m8` erst, wenn beauftragt.

## Hinweise ab Meilenstein 8 (Oberfläche)

- Vertrag ist `oberflaeche.md`: `data-testid`, Rollen, Zustandsattribute (`data-geladen`, `data-bereit`,
  `data-layout`, `data-betrag` in Cent …). Texte aus dem Buchbestand nur über `h()`/`textContent`, nie HTML.
- Jede Operation mit Wirkung auf den Buchbestand in der Oberfläche läuft über `aktion()` (`kern.js`): legt den
  Rückgängig-Eintrag an und lädt danach mit dem Stand des Servers neu (`oberflaeche.neuLaden`). Dialoge mit
  `danach: () => d.schliessen(true)` vor dem Neuladen schließen; Fehler in Dialogen über `imDialog`.
- Neue Routen in `SPA_ROUTEN` (`app.py`) **und** in `ROUTEN` (`haupt.js`) eintragen; neue Moduldateien in
  `DATEIEN` von `sw.js` (eigener Test). Keine Sammelroute für GET (würde 405 der REST-Pfade verdecken).
- Browsertests aus kontor-tests: `python -m pytest -m m8 -n 2` (Chrome über den Kanal `chrome`, ca. 2–3 min);
  eigene Rauchtests `tests/test_browser*.py`. Debug-Hilfe außerhalb des Repos: `/home/claude/impl/werkzeug/sicht.py`.
- Maßstab: alle Tests einschließlich `m8` und `leistung`.

## Hinweise ab Meilenstein 10 (AqBanking-Plugin)

- `plugins/aqbanking.py` startet nur `aqbanking-cli` (`listaccs`, `request --transactions`) und
  `aqhbci-tool4 listusers`, immer mit `-D <aqbanking_verzeichnis>`. Ausgaben von AqBanking nie loggen oder
  weitergeben; die PIN nur über die Pipe (`-P /dev/fd/N`). Auswertung über `fehler_aus_ausgabe` (D-099).
- Tests brauchen `aqbanking-tools` (`sudo apt-get install -y aqbanking-tools`); ohne werden 24 M10-Tests
  übersprungen – das gilt nicht als grün.
- Maßstab: alle Tests einschließlich `m10`.

## Hinweise ab Meilenstein 11 (Kontostand, Kategorien, Zusammenführen)

- `umsaetze()` aller Bank-Plugins liefert `plugins.bank.Umsatzliste` mit `saldo` (`BankSaldo` oder None); keine
  neue öffentliche Plugin-Methode. Saldoabgleich in `SyncDienst._saldo_abgleichen` (D-102), Ergebnis als JSON in
  `sync_lauf_konto.saldo_abgleich`.
- Buchungsliste: `unterkonten` bildet die Kontenmenge über `buch._listenkonten`; `buchungen_laden(konten=…)`.
- Oberfläche: Kontoansicht kennt `istKategorie` (Spalte `konto`, Filter `filter-konto`), URL ohne
  Vorgabesortierung (D-104).
- Maßstab: alle Tests einschließlich `m11` (AqBanking- und Browsertests laufen, nicht übersprungen).

## Hinweise zur Versionierung (D-105)

- Die Version nie von Hand in `VERSION` ändern; das macht nur die Release-CI beim Push auf main. Nach einem
  Merge daher `git pull` (die CI committet „Version x.yy veröffentlicht“ auf main).
- Neue Angaben im About-Fenster über `GET /api/version` (`app.py`) und `ueberOeffnen` (`haupt.js`).

## Hinweise ab Meilenstein 17 (Tabs, Gegenbuchung)

- Jede Ansicht ist ein Tab (`app/tabs.js`, Router `zeigen` in `haupt.js`): inaktive Tabs hängen nicht im Dokument,
  behalten aber DOM und Seitenobjekt. Seiten können `aktualisieren()` (Neuladen nach Änderung, auch für veraltete
  Tabs), `layoutGeaendert()`, `wiederAngefordert()` (Anfordern über Navigation) und `buchungZeigen(id)` anbieten.
- Filter der Kontoansicht über `urlSchreiben` melden sich mit `oberflaeche.urlGeaendert()` beim Tab.
- Browser-Speicher nur in `try` lesen/schreiben (M17 1.6). Maßstab: alle Tests einschließlich `m17`.

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
- Refactorings ändern kein Verhalten; Maßstab bleibt die Testsuite aus
  kontor-tests. Neue Funktionen mit C901 ≤ 15, Überschreitungen begründen.

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
