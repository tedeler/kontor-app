# Ergebnis der Implementierung

## Meilenstein 9 (Datensicherung und Wiederherstellung)

Stand: 2026-11-09, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `12438f8`** („M9 mit M4 und dem M3-Nachtrag abgeglichen
  (E-096)“), nach `git pull` im Lese-Klon unmittelbar vor dem Abschlusslauf.
- Aufruf im Wurzelverzeichnis des Lese-Klons gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, SQLite 3.53, Hypothesis-Profil `standard`:
  `python -m pytest -p no:cacheprovider -m "not m5 and not m6 and not m7 and not m8"` (Maßstab) und
  `python -m pytest -p no:cacheprovider` (vollständig).

| Auswahl | gesamt | bestanden | fehlgeschlagen | Fehler |
| --- | ---: | ---: | ---: | ---: |
| Maßstab (ohne m5–m8) | 1505 | 1505 | 0 | 0 |
| vollständig | 1505 | 1505 | 0 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |
| davon `-m m3` | 245 | 245 | 0 | 0 |
| davon `-m m4` (inkl. `langsam`) | 227 | 227 | 0 | 0 |
| davon `-m m9` | 56 | 56 | 0 | 0 |
| davon `m5`–`m8` (nicht beauftragt) | 0 | – | – | – |

(Die übrigen 77 Tests sind Generator- und Spezifikationstests; alle grün.) Tests späterer Meilensteine
gab es im getesteten Stand noch nicht. **Keine Fehlschläge, keine offenen Widersprüche;** W-002 wurde vom
Test-Thread behoben (E-095) und ist als erledigt markiert.

### Eigene Tests (kontor-app)

`python -m pytest tests`: 51 bestanden, darunter `tests/test_m9_eigen.py` (Rückgängig-Ketten mit
Bankkonto-Zustand, Python-Sicherung lässt die Datenbankdatei unverändert, Migration auf Schemaversion 5,
Laufsperre, Typfehler → `inhalt_ungueltig`) und der neue Playwright-Rauchtest `tests/test_browser_m9.py`
(Chrome headless, Desktop und Handy): Sicherung herunterladen (Dateiname vom Server), identische Datei im
Probelauf, Unterschied nach einer Änderung, gesperrter Knopf bis zum Häkchen, Bestätigungsdialog,
Einspielen mit Ergebnis und Änderung `sicherung_einspielen`, Rückgängig aus der Ergebnisanzeige,
verständliche Meldung bei kaputter Datei, keine horizontale Überbreite. Gestartete Server und Browser
wurden beendet.

### Umgesetzt

- `GET /api/sicherung` und `kontor.sicherung.erstelle_sicherung(config)`: ZIP mit `manifest.json` und
  `kontor.sqlite` (eigenes Schema, D-053), konsistenter Schnappschuss in einer Lesetransaktion, ohne
  Protokoll, Geheimnisse und Reste; Dateiname nach App-Uhr.
- `POST /api/sicherung/einspielen`: Prüfreihenfolge 5.1 mit allen elf Gründen, Modus, Bestätigung,
  Laufsperre; Probelauf; Einspielen als eine Änderung `sicherung_einspielen` (Quelle `sicherung`) mit der
  Nettowirkung; identischer Inhalt ohne Änderung; gleiche IDs (auch Splits); ID-Zähler nie
  zurückgesetzt; gemerkte Kennungen und Zustand je Bankkonto (inkl. Entscheidungen) ersetzt.
- Rückgängig/Wiederholen stellt zusätzlich Kennungen und Bankkonto-Zustand her (protokoll.md 10.2).
- Datenbank Schemaversion 5 (Betriebstabelle `sicherung_zustand`), Migration ohne Datenverlust.
- Weboberfläche „Datensicherung“ (D-058), README-Abschnitt „Datensicherung im Betrieb“ (zusätzlich zu
  Proxmox-Snapshots, Beispiel für eine nächtliche Sicherung).

### Einschränkungen

- Hypothesis lief nur im Profil `standard` (nicht `gruendlich`).
- Ältere Schemaversionen der Sicherungsdatei gibt es noch nicht (Version 1); der Migrationspfad beim
  Einspielen ist vorbereitet (`OBJEKTE_JE_VERSION`), aber noch leer.
- Die Sicherung wird im Arbeitsspeicher aufgebaut; für sehr große Bestände (mehrere hundert MiB) wäre
  ein dateibasiertes Verfahren sparsamer.
- Die Oberfläche hat noch keine stabilen `data-testid` (M8).

## Meilenstein 4 (mit Nachtrag synchronisation.md 16)

Stand: 2026-11-08, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `ffe104c`**
  (`ffe104c0a84ae1647f349713ab2761196936c4ab`, „Selbstprüfung für M4: 684/684
  Kern-Tests, 105/105 Mutanten erkannt; ERGEBNIS.md M4“), nach `git pull` im Lese-Klon.
- Aufruf im Wurzelverzeichnis des Lese-Klons gegen die per
  `pip install --break-system-packages -e` installierte kontor-app, Python 3.13,
  Hypothesis-Profil `standard`: `python -m pytest -p no:cacheprovider -m "not m9"`
  (Maßstab) und `python -m pytest -p no:cacheprovider` (vollständig).

| Auswahl | gesamt | bestanden | fehlgeschlagen | Fehler |
| --- | ---: | ---: | ---: | ---: |
| ohne m9 (`-m "not m9"`, Maßstab) | 1448 | 1445 | 3 | 0 |
| vollständig (inkl. m9) | 1497 | 1445 | 28 | 24 |
| davon `-m m1` | 674 | 671 | 3 (W-002) | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |
| davon `-m m3` (inkl. Nachtrag gelöschte Bankkonten) | 245 | 245 | 0 | 0 |
| davon `-m m4` (inkl. `langsam`) | 226 | 226 | 0 | 0 |
| davon `-m m9` (nicht beauftragt) | 49 | 0 | 25 | 24 |

(Die übrigen 77 Tests sind Generator- und Spezifikationstests; alle grün.)

Fehlschläge ohne m9 – alle drei durch **W-002** (M1-Tests verlangen, dass das
ab M4 spezifizierte Szenario `beitragsaenderung` unbekannt ist):

- `tests/app/test_paket.py::test_ungueltige_konfiguration[mock_modus=True,mock_szenario=beitragsaenderung]`
- `tests/app/test_plugins.py::test_unbekanntes_szenario[MockBank]`
- `tests/app/test_plugins.py::test_unbekanntes_szenario[MockMail]`

m9 (Datensicherung) ist ausdrücklich nicht Teil dieses Auftrags: 25 Fehlschläge
und 24 Fehler, alle, weil `/api/sicherung…` bzw. `kontor.sicherung` noch fehlen
(404). Keiner davon verlangt eine Änderung an M1–M4-Verhalten, die der
Spezifikation widerspräche; daher kein W-Eintrag.

### Eigene Tests (kontor-app)

`python -m pytest tests`: 44 bestanden, darunter der neue Playwright-Rauchtest
`tests/test_browser_m4.py` (Chrome headless, Desktop und Handy): GnuCash-Import
über die Import-Seite, Split-Vorlage im Dialog anlegen, Abweichung bei der
Synchronisation mit genau einer Benachrichtigung, Link `/buchungen/<id>`,
Vorlage anpassen und nachträglich aufteilen, Lernmodell anwenden mit
Sicherheitsanzeige, Dialog für gelöschte Bankkonten (ohne Vorauswahl,
Wiederherstellen mit allen Umsätzen und sofortigem Lauf). Gestartete Server und
Browser wurden beendet.

### Umgesetzt

- GnuCash-Import (`kontor.importer.gnucash`, `POST /api/import/gnucash`): XML
  gzip/unkomprimiert und SQLite (nur als Kopie im Arbeitsspeicher, D-043),
  Prüfreihenfolge und Fehlerfälle ohne Teilimport, Abbildung, Zuordnung über
  Quellen (auch KMyMoney nach GnuCash, D-045), Dublettenerkennung, Idempotenz,
  Protokoll `import_gnucash`.
- Lernmodell (`kontor.lernmodell`, `/api/lernmodell…`): exakt mit Brüchen,
  ohne gespeicherten Zustand, Schwelle 7/10, abschaltbar
  (`lernmodell_automatisch`, Vorgabe aus), Stufe 4 in Synchronisation und
  Erfassen, Ausnahme eigene Gegen-IBAN.
- Split-Vorlagen (`kontor.vorlagen`, `/api/vorlagen…`): Validierung,
  Reihenfolge, Bezüge (auch Konto löschen), Erkennung ohne Toleranz, Vorrang vor
  Regeln, Benachrichtigung `split_abweichung` mit Entprellung, Anwenden auf
  vorhandene Buchungen, Protokoll und Rückgängig (Objekt `vorlage`).
- Mock-Szenario `beitragsaenderung`, Zählungen `buchungen_gesplittet`,
  `vorlage_abweichungen`.
- Nachtrag synchronisation.md 16: Status je Bankkonto, Überspringen mit
  Benachrichtigung `konto_fehlt`, Entscheidung (`POST /api/sync/konten/{iban}/entscheidung`),
  Wiederherstellen mit allen/nur neuen Umsätzen, Rückgängig nach protokoll.md 6.4.
- Datenbank Schemaversion 4, Migration früherer Versionen ohne Datenverlust.
- Weboberfläche (nur REST, responsiv): siehe README und D-052.

### Einschränkungen

- Meilenstein 9 (Datensicherung) ist nicht umgesetzt.
- Hypothesis lief nur im Profil `standard` (nicht `gruendlich`).
- Die Oberfläche hat noch keine stabilen `data-testid` (M8).

## Meilenstein 3

Stand: 2026-11-08, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `ae6eacf`**
  (`ae6eacf5c3df597db159e57c78129bb370b2c68e`, „ERGEBNIS.md: M3-Abschnitt auf den
  Gesamtlauf der Selbstprüfung (529/529, 65/65) abgestimmt“), nach `git pull` im
  Lese-Klon.
- Aufruf: `python -m pytest -p no:cacheprovider` im Wurzelverzeichnis des Lese-Klons,
  gegen die per `pip install --break-system-packages -e` installierte kontor-app,
  Python 3.13, Hypothesis-Profil `standard`.

| Auswahl | gesamt | bestanden | fehlgeschlagen | übersprungen |
| --- | ---: | ---: | ---: | ---: |
| alle Tests | 1200 | 1200 | 0 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |
| davon `-m m3` | 227 | 227 | 0 | 0 |

(Die übrigen 73 Tests sind Generator- und Spezifikationstests.)

Fehlschläge im Standardlauf: keine.

Zusätzlich `HYPOTHESIS_PROFILE=gruendlich python -m pytest -m m3`: 225 von 227
bestanden; die zwei Fehlschläge (`test_m3_rueckgaengig.py::test_zufaellige_folgen_rueckwaerts`,
`::test_zufaelliges_rueckgaengig_gegen_orakel`) sind ein Fehler im Testablauf
(Zufallsauswahl aus leerer Kontenliste, bevor die Anwendung angefragt wird), siehe
**W-001**. Dieselben beiden Tests liefen zusätzlich mit sechs weiteren Hypothesis-Startwerten
(`--hypothesis-seed=1…6`) im Standardprofil grün.

### Eigene Tests (kontor-app/tests)

`python -m pytest tests`: **42 bestanden**, neu:

- `tests/test_m3_eigen.py`: Migration einer Datenbank mit dem Schema von M2
  (`tests/daten/schema_m2.sql`, mit Vorschlag) auf Schemaversion 3 ohne Datenverlust,
  danach Aliase, Abstimmung und Protokoll auf der migrierten Datenbank; Rückgängig einer
  Tag-Umbenennung behält Zuordnungen; Probelauf „Konto löschen“ verbraucht keine IDs;
  PIN erscheint nie im Protokoll.
- `tests/test_browser_m3.py` (Playwright, Chrome headless, echte Server im Mock-Modus auf
  freien lokalen Ports, danach beendet): Umbuchungsvorschläge zusammenführen, Strg+Z,
  Buchung erfassen, globale Suche (umlautunabhängig), Kontenabstimmung mit Differenz und
  mit passendem Saldo, Rückgängig im Änderungsprotokoll; im Handyformat Empfänger mit
  Alias und Standardkategorie bearbeiten, Kategorie mit Buchungen löschen (keine
  Vorauswahl, Elternkonto bei Wurzel deaktiviert), Rückgängig über den Knopf im Kopf,
  Suche.

Die neuen Seiten wurden zusätzlich per Bildschirmfoto (Desktop 1280 px, Handy 390 px)
geprüft; gefundene Mängel (Ausgabe „null“ im Löschdialog, umbrechende Knöpfe im
Protokoll auf dem Handy) sind behoben.

### Einschränkungen

- Die automatische Umbuchungserkennung ist wie spezifiziert standardmäßig aus
  (`KONTOR_UMBUCHUNG_AUTOMATISCH=1` für den Betrieb empfohlen).
- Die Volltextsuche rechnet ohne Index in Python (D-041); Leistung wird in M7 bewertet.
- Das Änderungsprotokoll wächst unbegrenzt (kein Aufräumen; nicht spezifiziert).
- Stabile `data-testid` der Oberfläche und vollständige Playwright-Tests folgen in M8.
- Echtes FinTS-Plugin weiterhin Platzhalter (M6), wie in M2.

---

## Meilenstein 2 (frühere Fassung)

Stand: 2026-11-08, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `bda67eb`**
  (`bda67ebe9e5f0a234f63e95a46cd0a5608464497`, „TESTS_AUSFUEHREN.md, CLAUDE.md,
  ERGEBNIS.md für Meilenstein 2“), nach `git pull` im Lese-Klon.
- Aufruf: `python -m pytest -p no:cacheprovider` im Wurzelverzeichnis des
  Lese-Klons, gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, Hypothesis-Profil `standard`.

| Auswahl | gesamt | bestanden | fehlgeschlagen | übersprungen |
| --- | ---: | ---: | ---: | ---: |
| alle Tests | 966 | 966 | 0 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |

(Die übrigen 66 Tests sind Generator- und Spezifikationstests.)

Fehlschläge: keine. Widersprüche (`WIDERSPRUECHE.md`): keine.

Zusätzlich `HYPOTHESIS_PROFILE=gruendlich python -m pytest -m m2` (400 zufällige
Beispiele je Eigenschaftstest): 226 von 226 bestanden.

### Eigene Tests (kontor-app/tests)

`python -m pytest tests`: **36 bestanden**, darunter zwei neue Playwright-Rauchtests
mit Chrome headless (`tests/test_browser_m2.py`, echte Server im Mock-Modus auf
freien lokalen Ports, danach beendet): Regel über den Dialog anlegen,
Synchronisation auslösen, Läufe ansehen, Vorschläge in der Buchungsliste
erkennen, einzeln (✓) annehmen und mehrfach ablehnen; im Handyformat TAN-Ablauf
(QR-Bild geladen, „QR-Code speichern“ als PNG-Download, „Teilen …“,
Benachrichtigungsglocke, Link `/tan/<id>`, falsche und richtige TAN) und
Benachrichtigung als gelesen markieren. Weitere eigene Tests: gedeckelte
Vorgabepriorität, eingebauter Datensatz, deterministisches QR-Bild, TAN-Bild nur
bei offener Anforderung, Oberfläche nutzt nur spezifizierte API-Pfade.

Die Oberfläche wurde zusätzlich per Bildschirmfoto (Desktop 1280 px, Handy
390 px) geprüft; gefundene Mängel (Ausgabe „null“ in der Werkzeugleiste,
gequetschte Regeltabelle auf dem Handy) sind behoben.

### Einschränkungen

- Das echte FinTS-Plugin ist weiterhin ein Platzhalter (M6); Läufe im
  Echtbetrieb enden als `fehlgeschlagen` (`plugin_nicht_verfuegbar`).
- PIN nur per Eingabe in der Oberfläche (Arbeitsspeicher); systemd-creds/TPM,
  ntfy-Zustellung und TAN-Erinnerungen folgen in M6.
- Das Mock-QR-Bild ist ein QR-artiges, aber nicht lesbares Bild (D-020).
- Umbuchungen zwischen eigenen Konten werden noch nicht erkannt (M3): beide
  Bankseiten werden als eigene Buchungen gegen „Unkategorisiert“ gebucht.
- Der Browser-Rauchtest ersetzt keine vollständigen Playwright-Tests (M8).

---

## Meilenstein 1 (frühere Fassung)

Stand: 2026-11-08, Implementierungs-Thread.

## Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `c708944`**
  (`c7089448362e5abd1be05384ceb3894705076e9f`, „ERGEBNIS.md: erstellte
  Dateien, Testanzahl je Bereich, Selbstprüfung“), nach `git pull` im
  Lese-Klon.
- Aufruf: `python -m pytest -p no:cacheprovider` im Wurzelverzeichnis des
  Lese-Klons, gegen die per `pip install --break-system-packages -e` installierte
  kontor-app (Version 0.1.0), Python 3.13, Hypothesis-Profil `standard`.

| gesamt | bestanden | fehlgeschlagen | übersprungen |
| ---: | ---: | ---: | ---: |
| 734 | 734 | 0 | 0 |

Fehlschläge: keine. Widersprüche (`WIDERSPRUECHE.md`): keine.

Zusätzlich lief `HYPOTHESIS_PROFILE=gruendlich python -m pytest tests/app`
(400 zufällige Beispiele je Eigenschaftstest): 674 von 674 bestanden.

## Eigene Tests (kontor-app/tests)

`python -m pytest tests`: **29 bestanden**, darunter ein Browser-Rauchtest mit
Playwright und Chrome (headless): Finanzübersicht, Kontoansicht,
Mehrfachauswahl mit Umschalt/Strg, Kontextmenü per Rechtsklick, Kategorie für
mehrere Buchungen setzen, mobiles Menü (390 px), lange Berührung öffnet das
Kontextmenü. Weitere eigene Tests: Auslieferung der Oberfläche und Assets,
keine externen Ressourcen, Oberfläche nutzt nur spezifizierte API-Pfade,
Schema lehnt Gleitkommabeträge ab, Import-Randfälle, eingebauter
Mock-Datensatz.

## Prüfung der Weboberfläche

Server im Mock-Modus gestartet (`python -m kontor serve`), `standard.kmy`
importiert, alle Seiten und Assets per curl abgerufen (200, korrekte
Content-Types, Mock-Hinweis im HTML, `X-Kontor-Modus: mock`) und mit
Playwright/Chrome im hellen und dunklen Design sowie in Handygröße bedient
(Filter, Sortierung, Bearbeiten/Splitten, Tags, Kategorie, Konto anlegen,
Import-Upload, Einstellungen). Dabei gefundene Fehler (verdeckte Dialoghülle,
Tabellenbreite auf dem Handy, „null“-Ausgabe) sind behoben. Gestartete
Server-Prozesse wurden beendet.

## Einschränkungen

- Nicht Teil von Meilenstein 1 und nicht umgesetzt: Bank-Synchronisation in
  das Buch, Kategorisierung, Split-Vorlagen, wiederkehrende Buchungen,
  Kredite, Berichte, Kontenabstimmung, Login, Änderungsprotokoll/Undo,
  Drag and Drop, Befehlspalette, Inline-Bearbeitung, Service Worker (PWA nur
  mit Manifest). In der Oberfläche als „später“ gekennzeichnet.
- FinTS- und IMAP-Plugin sind Platzhalter ohne Verbindung
  (`PluginNichtVerfuegbar`).
- Mock-Daten gelangen nur über den KMyMoney-Import synthetischer Dateien in
  das Buch (D-014).
- Der Browser-Rauchtest deckt die Kernabläufe ab, ersetzt aber keine
  vollständigen Playwright-Tests nach T 19 (die gehören in kontor-tests).
