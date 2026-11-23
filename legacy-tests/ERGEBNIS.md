# Ergebnis: Tests für Meilenstein 1 bis 9, 11 bis 13 und 15 bis 31 (M10 entfallen)

Inhalt: Meilenstein 1 (unten zuerst, unverändert gültig), danach
Abschnitt „Meilenstein 2“ und der Meilensteinplan (`spec/meilensteine.md`).

## Meilenstein 1

Stand: 2026-11-08, Test-Thread. Umfang: KMyMoney-Import, Kontenübersicht,
Buchungsliste mit Filtern und Mehrfachbearbeitung, Datenmodell mit doppelter
Buchführung, Splits und Tags, Bank- und Mail-Plugins als austauschbare
Schnittstelle mit Mock-Varianten.

### Was erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/` | Schnittstellenspezifikation (Datenmodell, Python-API, OpenAPI 3.1, Plugins) und Entscheidungsprotokoll E-001 bis E-026 |
| `generator/`, `fixtures/` | Testdatengenerator mit festem Startwert 4711 und erzeugte Fixtures: 7 gültige und 11 defekte `.kmy`-Dateien, Mock-Datendatei, Erwartungsdateien (bekannte Wahrheit), MANIFEST |
| `tests/hilfen/` | Zugriff auf die App nur über die Spezifikation: verzögerter Import von `kontor`, Testclient mit Vertragsprüfung jeder Antwort gegen `openapi.yaml`, Erwartungsvergleich, KMyMoney-Bausteine, Textnormalisierung |
| `tests/generator/`, `tests/spec/` | Tests von Generator, Fixtures und OpenAPI-Dokument (laufen ohne App) |
| `tests/app/` | Tests gegen die installierte Anwendung (14 Module) |
| `tests/_selbstpruefung/` | Wegwerf-Referenz (kein Anwendungscode), 20 Mutanten, Aufruf `python -m tests._selbstpruefung`, Protokoll `LETZTER_LAUF.md` |
| `pytest.ini`, `requirements-tests.txt` | Pytest-Konfiguration (Marker `kern`, `langsam`, `app`; Selbstprüfung ausgeschlossen) und Testabhängigkeiten |
| `CLAUDE.md`, `TESTS_AUSFUEHREN.md` | Regeln für künftige Threads, genaue Anleitung zum Testlauf |

### Anzahl Tests je Bereich

Gesammelte Testfälle (`python -m pytest --collect-only`, Parametrisierungen
einzeln gezählt): **734**, davon **213** mit Marker `kern`. Zehn Tests sind
eigenschaftsbasiert (Hypothesis, Profil `standard`: je 40 Beispiele).

| Bereich | Datei | Tests |
| --- | --- | ---: |
| Generator und Fixtures | `tests/generator/*` | 53 |
| OpenAPI und Vertragsprüfer | `tests/spec/test_openapi.py` | 7 |
| Paket, Fehlerklassen, Konfiguration | `test_paket.py` | 90 |
| REST-Grundregeln, Beträge, Fehlerformat | `test_api_allgemein.py` | 38 |
| Konten, IBAN, Hierarchie, Salden | `test_konten.py` | 71 |
| Empfänger und Tags | `test_empfaenger_tags.py` | 25 |
| Datenmodell: Splits, Kategorie, Status, Sperre | `test_buchungen.py` | 72 |
| Globale Invarianten (Hypothesis) | `test_invarianten.py` | 2 |
| KMyMoney-Import inkl. Sonderfälle | `test_import_kmy.py` | 61 |
| Import-Fehlerfälle, kein Teilimport | `test_import_fehler.py` | 85 |
| Idempotenz und Zuordnung | `test_idempotenz.py` | 17 |
| Dublettenerkennung | `test_dubletten.py` | 17 |
| Filter, Sortierung, Paginierung | `test_filter.py` | 93 |
| Mehrfachbearbeitung | `test_mehrfach.py` | 30 |
| Bank-/Mail-Plugins, Mock-Plugins | `test_plugins.py` | 57 |
| Mock-Modus | `test_mock_modus.py` | 16 |

Unabhängige Erwartungen: Import gegen die bekannte Wahrheit des Generators
(auch für zufällig erzeugte Bücher), Dublettenerkennung gegen ein eigenes
Orakel von `datenmodell.md` 10.4, Filter gegen ein Orakel über die
ungefilterte Liste, Invarianten und Mehrfachbearbeitung gegen ein Modell,
Mock-Plugins gegen die Mock-Datendatei.

### Verhalten ohne installierte Anwendung (E-024)

Ohne Paket `kontor` schlagen die 674 App-Tests mit deutlicher Meldung fehl;
mit `--ohne-app` bzw. `KONTOR_TESTS_OHNE_APP=1` werden sie übersprungen.
Die 60 Generator- und Spezifikationstests laufen immer (aktuell grün).

### Ergebnis der Selbstprüfung

Lauf am 2026-11-08 (Python 3.13, Profil `standard`), Protokoll in
`tests/_selbstpruefung/LETZTER_LAUF.md`:

- Referenz ohne Mutant: **213 von 213 Kern-Tests grün**.
- **Alle 20 Mutanten erkannt** (jeweils mindestens ein Kern-Test rot):
  Stichtag exklusiv, saldo_gesamt nicht rekursiv, Splitsumme ungeprüft,
  Ein-Split-Buchung, Gleitkommabeträge, falscher Umsatz, Memo-Verlust beim
  Kategorisieren, nicht atomare Mehrfachbearbeitung, Teilimport, fehlender
  Ausgleichssplit, Idempotenz (Buchungen, Empfänger), vier Fehler der
  Dublettenregeln (Eindeutigkeit, erster Kandidat, Empfängervergleich,
  Toleranz), Umlautnormalisierung, Filter `bis` exklusiv, Unterkategorien
  ignoriert, instabile Sortierung.

Zusätzlich wurde die Referenz einmalig lokal (nicht eingecheckt) um
Plugins, `from_env` und Fehlerklassen erweitert, um auch die nicht zum Kern
gehörenden Tests auf Widerspruchsfreiheit zu prüfen: Damit liefen alle 734
Tests grün. Dabei gefundene Testfehler (XML-Deklaration nach Leerraum,
Betragsgrenze in KMyMoney-Notation, Query-Wert `10.00`) sind korrigiert.

### Neue Entscheidungen

- **E-024** Testlauf ohne Anwendung: Fehlschlag mit Meldung, Überspringen nur per Schalter.
- **E-025** IBAN an Nicht-Bestandskonto: 422 mit `validierung` oder `iban_ungueltig`.
- **E-026** Gesperrte Buchung und unveränderter Wert: 200 ohne Wirkung oder 409 zulässig.

### Einschränkungen

- Gegen die echte kontor-app wurden die Tests nicht ausgeführt (Rollentrennung);
  geprüft sind sie gegen die Referenz. Abweichungen der Implementierung, die
  auf Lücken der Spezifikation beruhen, löst ein Test-Thread.
- Nicht getestet, weil nicht in Meilenstein 1 (`datenmodell.md` 11): Änderungsprotokoll
  und Rückgängig (T 3.5/3.6, E-022), Login und Sicherheit (T 18, E-018), GnuCash-Import,
  Bank-Synchronisation ins Buch, Kategorisierung, Split-Vorlagen, Kredite, Berichte,
  Leistung (T 20), Browser-/Playwright-Tests (T 19). Der Mock-Hinweis wird im
  ausgelieferten HTML statisch geprüft (Attribute `hidden`, `style`, Vorfahren), nicht
  per Browser-Rendering; CSS-Klassen, die ein Element verstecken, erkennt der Test nicht.
- Invariante 2 („nie Gleitkomma“) wird an der Schnittstelle geprüft, nicht im
  Datenbankschema (das physische Schema ist Sache der Implementierung).
- Die `referenz` von Inhaltsfehlern beim Import wird nur grob geprüft (vorhanden, ohne
  `kmy:`), weil die Spezifikation das betroffene Element nicht eindeutig festlegt.
  Warnungen eines zweiten Imports derselben Datei werden nicht geprüft.
- Statt Schemathesis und mutmut (T 2) werden eine eigene Vertragsprüfung jeder Antwort
  und gezielte Mutanten der Referenz verwendet; Zielwerte für Abdeckung und
  Mutationswert der Implementierung (T 2) misst diese Testsuite nicht.

### Nicht Erreichbares

Nichts. Alle benötigten Pakete (pytest, Hypothesis, jsonschema, PyYAML, httpx,
openapi-spec-validator, FastAPI für die Selbstprüfung) waren installiert; es wurde
keine externe Domain oder kein weiteres Repository benötigt.

## Meilenstein 2

Stand: 2026-11-08, Test-Thread. Umfang laut K 18: Bank-Synchronisation mit
Mock-Plugin und Regel-Kategorisierung, dazu Dublettenerkennung beim Abruf,
TAN-Ablauf, PIN im Arbeitsspeicher, Planer, interne Benachrichtigungen.

### Meilensteinplan (`spec/meilensteine.md`, E-027)

| Meilenstein | Inhalt |
| --- | --- |
| M1 (erledigt) | KMyMoney-Import, Kontenübersicht, Buchungsliste, Filter, Mehrfachbearbeitung, Datenmodell, Plugin-Schnittstellen mit Mocks |
| M2 | Bank-Synchronisation (Mock), Dublettenerkennung beim Abruf, TAN, PIN im Arbeitsspeicher, Planer, Regeln mit Vorschlägen |
| M3 | Änderungsprotokoll mit Rückgängig, Empfängerverwaltung, manuelle Buchungen und Umbuchungserkennung, Kontenabstimmung, Volltextsuche |
| M4 | GnuCash-Import, Lernmodell, Split-Vorlagen |
| M5 | Wiederkehrende Buchungen, Kredite, Berichte, Export CSV/PDF |
| M6 | FinTS-Plugin, Mail-Plugin (IMAP/OAuth2), ntfy-Benachrichtigungen, Geheimnisspeicher – nur gegen lokale Attrappen getestet (E-028) |
| M7 | Login und Sicherheit, Betrieb (systemd, Datenbank-Export, Neustart, Leistung) |
| M8 | Vollständige Oberfläche mit Playwright (Chromium headless vorhanden und geprüft) |

### Was für M2 erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/meilensteine.md` | Plan M2–M8 mit Umfang, Konzept-/Testkonzeptbezug, Abhängigkeiten |
| `spec/api/synchronisation.md` | Läufe, Kontozuordnung über IBAN, Übernahme, gemerkte Kennungen, Abgleich mit Altbestand, Fehler und Wiederholung, TAN-Ablauf, simulierte Uhr, Planer, Neustart, Benachrichtigungen, PIN |
| `spec/api/kategorisierung.md` | Regeln (Bedingungen, Priorität), Anwenden auf vorhandene Buchungen, Vorschläge |
| `spec/api/datenmodell.md`, `python-api.md`, `plugins.md` | M2-Ergänzungen (je eigener Abschnitt), rückwärtskompatibel |
| `spec/api/openapi.yaml` | Version 2.0.0: 24 neue Operationen, `Buchung.vorschlag` optional, Filter `vorschlag` |
| `spec/api/entscheidungen.md` | E-027 bis E-043 |
| `generator/sync_daten.py` | Mock-Bankdaten Jan.–Juni 2024 (drei Konten, Störfälle), PIN-Variante, KMyMoney-Altbestand, Regelsatz, bekannte Wahrheit |
| `fixtures/mock/sync_daten*.json`, `fixtures/kmy/sync_altbestand.*`, `fixtures/sync/regeln.json` | erzeugte Fixtures (Startwert 4711) |
| `tests/hilfen/m2.py`, `tests/hilfen/sync_orakel.py` | Hilfen und unabhängiges Orakel (Regelauswertung, Abgleich, Übernahme) |
| `tests/generator/test_sync_daten.py` | Wahrheit des Generators gegen das Orakel |
| `tests/app/m2/` | 11 Testmodule (Marker `m2`) |
| `tests/_selbstpruefung/referenz/kontor/{m2,sync}.py`, `plugins/` | Wegwerf-Referenz für M2, 18 neue Mutanten |

### Testanzahl

Gesamt gesammelt: **966** Testfälle (M1: 734, unverändert; M2: 232), davon
**327** mit Marker `kern` (M2: 114). Auswahl: `python -m pytest -m m2`
(226 Fälle: 219 App-Tests, 7 Generatortests); dazu kamen 4 parametrisierte
Generatortests für `sync_altbestand.kmy` und 2 Spezifikationstests.

| Bereich | Datei | Tests |
| --- | --- | ---: |
| M2-Fixtures gegen Orakel | `tests/generator/test_sync_daten.py` | 7 |
| Fehlerklassen, Signaturen, Konfiguration | `test_m2_paket.py` | 26 |
| Mock-Bank mit TAN und PIN | `test_m2_mock_bank.py` | 12 |
| Übernahme, Wiederholung, Zeitraum, Mock-Uhr | `test_m2_sync.py` | 28 |
| Abgleich mit Altbestand | `test_m2_altbestand.py` | 6 |
| Fehler, Wiederholung, Benachrichtigungen | `test_m2_fehler.py` | 8 |
| TAN-Ablauf | `test_m2_tan.py` | 17 |
| PIN | `test_m2_pin.py` | 13 |
| Planer | `test_m2_planer.py` | 8 |
| Regel-CRUD | `test_m2_regeln_api.py` | 39 |
| Regelauswertung und Anwenden | `test_m2_regeln_anwenden.py` | 43 |
| Vorschläge | `test_m2_vorschlag.py` | 19 |

Eigenschaftsbasiert (Hypothesis): zufällige Umsatzlisten mit zwei
Abrufzeitpunkten gegen das Orakel; zufällige Regeln und Buchungen gegen das
Orakel der Regelauswertung.

### Ergebnis der Selbstprüfung

Lauf am 2026-11-08 (Python 3.13, Profil `standard`), Protokoll in
`tests/_selbstpruefung/LETZTER_LAUF.md`:

- Referenz ohne Mutant: **327 von 327 Kern-Tests grün** (213 M1, 114 M2).
- **Alle 38 Mutanten erkannt** (20 aus M1, 18 neue für M2): Kennungen
  ungeprüft, gelöschte Buchungen kommen wieder, Vormerkungen gebucht, kein
  Abgleich mit Altbestand, Folgeabruf ohne Überlappung, Benachrichtigungsflut,
  umgekehrte Priorität, Gleichstand zugunsten der späteren Regel, Regeltexte
  ohne Umlautnormalisierung, inaktive Regeln greifen, Betragsbedingung auf
  Absolutbetrag, Regeltreffer nicht als Vorschlag markiert, Ablehnen ohne
  Rücksetzen, TAN-Ablauf ignoriert, falsche PIN nicht verworfen, PIN in
  Fehlermeldung, Planer ohne Wiederholungsabstand, Neustart ohne Abbruch.
- Zusätzlich liefen **alle 219 M2-App-Tests** (nicht nur Kern) grün gegen die
  Referenz; dabei gefundener Testfehler („Vermieter“ enthält „miete“) ist
  korrigiert.

### Neue Entscheidungen

- **E-027** Meilensteinplan
- **E-028** Echte Fremdsysteme nur über Attrappen
- **E-029** Rückwärtskompatible Erweiterung des Vertrags
- **E-030** Synchronisation synchron, Läufe protokolliert, Planer abschaltbar
- **E-031** Simulierte Uhr im Mock-Modus
- **E-032** Zuordnung der Bankkonten über die IBAN
- **E-033** Abbildung der Umsätze, Vormerkungen und Storno
- **E-034** Dublettenerkennung beim Abruf
- **E-035** Fehlerbehandlung, Wiederholung, interne Benachrichtigungen
- **E-036** TAN-Ablauf
- **E-037** PIN nur im Arbeitsspeicher
- **E-038** Regeln: Bedingungen und Priorität
- **E-039** Vorschläge und Bestätigung
- **E-040** Regeln auf vorhandene Buchungen anwenden
- **E-041** Marker je Meilenstein und Testverzeichnis
- **E-042** Vertragsprüfung von Nicht-JSON-Antworten
- **E-043** Konto mit Regelbezug nicht löschbar

### Einschränkungen und offene Punkte

- Gegen die echte kontor-app wurden die Tests nicht ausgeführt (Rollentrennung);
  alle 219 M2-App-Tests liefen grün gegen die Wegwerf-Referenz (vollständig
  für M2, nicht nur Kern). Die M1-Tests sind unverändert; eine
  M1-Implementierung bleibt gegen `-m m1` grün, die M2-Tests sind rot, bis M2
  umgesetzt ist (Tests zuerst).
- Nebenläufigkeit (409 `sync_laeuft`) ist spezifiziert, aber nicht getestet
  (nicht deterministisch prüfbar).
- Der Hintergrund-Thread des Planers wird mit einem Test (bis 15 s Wartezeit)
  geprüft, alle übrigen Planer-Tests rufen `kontor.sync.planer_takt` auf.
- Die PIN-Prüfung „nie in Logs“ erfasst Python-Logging (`caplog`) und
  stdout/stderr des Testprozesses; Logs eines separat gestarteten Servers
  (uvicorn) sind nicht Teil des Testlaufs.
- Nicht in M2 (siehe `spec/meilensteine.md`): Lernmodell, ntfy-Zustellung und
  TAN-Erinnerungen, echtes FinTS-Plugin, PIN über systemd-creds, TAN-Seite
  der Oberfläche, Umbuchungserkennung, Empfänger-Standardkategorie,
  Änderungsprotokoll (Invarianten T 3.5/3.6).

### Nicht Erreichbares

Nichts. Playwright 1.63 und Google Chrome (headless) sind vorhanden und
wurden mit einer Testseite geprüft; Browsertests sind für M8 eingeplant.
Es wurde keine externe Domain und kein weiteres Repository benötigt.

## Meilenstein 3: Konten und Kategorien löschen

(Abschnitt des parallelen Test-Threads. Das aktuelle Gesamtergebnis der
Selbstprüfung steht im folgenden Abschnitt „Meilenstein 3“.)

Stand: 2026-11-08, Test-Thread. Auftrag des Anwenders: Konten und Kategorien
müssen löschbar sein. Dabei wird gefragt, wie mit den Buchungen umgegangen
wird: löschen, dem Konto der Hierarchieebene darüber zuschlagen oder als
unkategorisiert einstufen. Buchungen, die danach zwei unkategorisierte
Seiten (Quelle und Ziel) hätten, werden besonders behandelt. Der Teil ist
eingebettet in die parallel entstandene M3-Spezifikation (Protokoll,
Abstimmung, Empfänger).

### Was erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/loeschen.md` | Fachliche Regeln: Varianten `loeschen`, `elternkonto`, `unkategorisiert`; Konfliktbuchungen (alle Splits danach auf demselben Konto) mit Wahl `loeschen`/`behalten`; Zusammenfassen von Splits auf dem Zielkonto; Unterkonten rücken nach oben; gesperrte Buchungen nur mit Bestätigung; Regeln, Standardkategorien, Abstimmungen; Probelauf; eine Änderung im Protokoll, rückgängig machbar; Dialog der Oberfläche (M8) |
| `spec/api/openapi.yaml` | `POST /api/konten/{konto_id}/loeschen`, Schemas `KontoLoeschen`, `KontoLoeschErgebnis`, Fehlercodes `kein_elternkonto`, `ziel_ungueltig` |
| `spec/konzept.md`, `testkonzept.md`, `meilensteine.md`, `api/datenmodell.md`, `api/kategorisierung.md`, `api/buchhaltungspflege.md`, `api/protokoll.md` | Verweise und Ergänzungen; `DELETE /api/konten/{id}` bleibt unverändert (E-029) |
| `spec/api/entscheidungen.md` | E-060 bis E-064 |
| `tests/hilfen/loeschen_orakel.py` | Unabhängiges Orakel auf REST-Momentaufnahmen |
| `tests/app/m3/test_m3_konto_loeschen.py` | 60 Testfälle, alle `kern` |
| `tests/spec/test_openapi.py` | Operation in `OPERATIONEN_M3`, Test „keine Vorgabe“ (E-061) |
| `tests/_selbstpruefung/referenz/kontor/m3_loeschen.py` | Wegwerf-Referenz des Endpunkts (nutzt die M3-Referenz für Protokoll, Abstimmung, Empfänger), 8 neue Mutanten |

### Abdeckung

- Jede Variante, mit Salden und Invarianten. Ein Eigenschaftstest
  (Hypothesis) prüft zufällige Bücher mit Kontenhierarchie und Folgen von
  bis zu drei Löschvorgängen (auch von „Unkategorisiert“) gegen das Orakel,
  jeweils als Probelauf und als echter Lauf.
- Konfliktbuchungen:
  - die Umbuchung Giro → Spar, nach zwei Löschvorgängen von
    „Unkategorisiert“ nach „Unkategorisiert“,
  - eine Buchung zwischen Unterkonto und Elternkonto,
  - eine Konfliktbuchung mit drei Splits,
  - jeweils mit Löschen und mit Behalten.
- Zusammenfassen von Splits mit Memoregeln, auch mit Betrag 0. Abgestimmte
  Splits werden nicht zusammengefasst.
- Fehlerfälle ändern nichts: Wurzelkonto mit `elternkonto`,
  „Unkategorisiert“ nach „Unkategorisiert“, unbekanntes Konto, fehlende
  Wahl (E-061), gesperrte Buchungen ohne Bestätigung.
- Regeln, Vorschläge, Standardkategorien, Abstimmungen.
- Protokoll: genau eine Änderung `konto_loeschen_mit_buchungen`. Rückgängig
  stellt den gesamten Bestand exakt wieder her.

### Ergebnis der Selbstprüfung

Lauf am 2026-11-08 (Python 3.13, Profil `standard`), Protokoll in
`tests/_selbstpruefung/LETZTER_LAUF.md`. Der Lauf umfasst den gesamten
Stand inklusive der parallel entstandenen M3-Tests.

- Referenz ohne Mutant: **529 von 529 Kern-Tests grün**. Davon sind 60 die
  Tests zum Löschen von Konten.
- **Alle 65 Mutanten erkannt**. Davon gehören 8 zum Löschen:
  - Sperre ignoriert,
  - Unterkonten werden Wurzelkonten,
  - Vorschlag bleibt,
  - Konflikte nicht erkannt,
  - kein Zusammenfassen,
  - Probelauf schreibt,
  - Abstimmung bleibt,
  - Standardkategorie bleibt.

  Konflikt-, Unterkonten- und Zusammenfassungsfehler erkennt auch der
  Eigenschaftstest allein.

### Einschränkungen

- Gegen die echte kontor-app wurde nicht getestet (Rollentrennung). Bis ein
  Implementierungs-Thread den Endpunkt umsetzt, sind diese Tests rot.
- Die Oberfläche (Dialog) ist in `loeschen.md` 5 beschrieben und wird mit
  M8 getestet.

## Meilenstein 3

Stand: 2026-11-08, Test-Thread. Umfang laut `spec/meilensteine.md` M3:
Änderungsprotokoll mit Rückgängig (rückwirkend für alle Operationen aus M1
und M2), Empfängerverwaltung, Erfassungshilfe für manuelle Buchungen,
Umbuchungserkennung, Kontenabstimmung, Volltextsuche. Ein paralleler
Test-Thread hat M3 um „Konten und Kategorien mit Buchungen löschen“ ergänzt
(`spec/api/loeschen.md`, E-060 bis E-064, `test_m3_konto_loeschen.py`); die
Zahlen unten enthalten diese Tests, beschrieben wird hier der übrige Teil.

### Was für M3 erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/protokoll.md` | Buchbestand, Protokollform je Objekt, Nettowirkung, Aktionen je Operation, Gruppen (`sync:<lauf>`, `import:<id>`), Rückgängig mit Zustands- und Bezugsprüfung, mehrere Änderungen/Gruppe, Wiederholen, Wirksamkeit, Lesen und Filter |
| `spec/api/buchhaltungspflege.md` | Neue Felder (`gegen_iban`, `ist_umbuchung`, `abgestimmt`, `Split.abstimmung_id`), Sperre, technische Konten, Empfänger (Aliase, Standardkategorie, Ändern, Löschen, Zusammenführen), Erfassungshilfe, Umbuchungen, Abstimmung, Volltextsuche |
| `spec/api/datenmodell.md` 13, `synchronisation.md` 14, `kategorisierung.md` 6, `python-api.md` 9 | M3-Ergänzungen, rückwärtskompatibel |
| `spec/api/openapi.yaml` | Version 2.1.0: 15 neue Operationen (dazu 1 aus dem Lösch-Auftrag), neue Felder optional, Filter `abgestimmt`, `Vorschlag.quelle` um `standardkategorie` erweitert |
| `spec/api/entscheidungen.md` | E-044 bis E-059 |
| `generator/m3_daten.py` | `mock/m3_daten.json` (Umbuchungsfälle, Namensvarianten, NFD, ß, Ligatur), `m3/stammdaten.json`, `m3/suche.json`, `kmy/m3_aliase.kmy`, Erwartungsdatei mit bekannter Wahrheit; Generatorversion 3.0.0 |
| `tests/hilfen/m3.py`, `tests/hilfen/m3_orakel.py` | Protokollform aus REST, Prüfung der Einträge, Rundreise Rückgängig/Wiederholen, Bezugs-Orakel; Orakel für Suche, Aliase, Umbuchungspaare |
| `tests/app/m3/` | 9 Testmodule (siehe Tabelle) |
| `tests/_selbstpruefung/referenz/kontor/m3.py` | Wegwerf-Referenz für M3; 19 neue Mutanten |

### Testanzahl

Gesamt gesammelt: **1200** Testfälle (M1: 734 und M2: 232, beide
unverändert; M3: 234), davon **529** mit Marker `kern` (M3: 202).
Auswahl `python -m pytest -m m3`: 227 Fälle (218 App-Tests, 9
Generatortests). Davon aus diesem Auftrag: 158 App-Tests, 9
Generatortests, 2 Spezifikationstests und 4 parametrisierte Fixture-Tests
für `m3_aliase.kmy` (173 Fälle, 142 `kern`); aus dem Lösch-Auftrag 60
App-Tests und 1 Spezifikationstest (alle 60 App-Tests `kern`).

| Bereich | Datei | Tests |
| --- | --- | ---: |
| M3-Fixtures gegen Orakel | `tests/generator/test_m3_daten.py` | 9 |
| Konfiguration | `test_m3_paket.py` | 14 |
| Protokoll aller Operationen, Rückgängig/Wiederholen | `test_m3_protokoll.py` | 43 |
| Rückgängig: Konflikte, Gruppen, Hypothesis | `test_m3_rueckgaengig.py` | 9 |
| Protokoll von Synchronisation, Planer, TAN, Import | `test_m3_protokoll_sync.py` | 8 |
| Empfängerverwaltung | `test_m3_empfaenger.py` | 16 |
| Erfassungshilfe | `test_m3_erfassen.py` | 30 |
| Umbuchungserkennung | `test_m3_umbuchung.py` | 7 |
| Kontenabstimmung | `test_m3_abstimmung.py` | 10 |
| Volltextsuche | `test_m3_suche.py` | 21 |
| Konten mit Buchungen löschen (paralleler Auftrag) | `test_m3_konto_loeschen.py` | 60 |

Unabhängige Erwartungen: Protokolleinträge werden aus dem REST-Zustand vor
und nach jeder Operation berechnet (nie aus Antworten übernommen);
Umbuchungspaare je Abrufstufe, Kontoauszüge und Stammdaten-Zuordnung aus
der Generatorwahrheit (gegen das Orakel geprüft); Suche gegen ein Orakel
auf dem vollständigen Zustand. Eigenschaftsbasiert: zufällige
Operationsfolgen werden rückwärts zurückgenommen (exakter Zustand nach
jedem Schritt, T 3.6); zufälliges Rückgängig gegen Zustands- und
Bezugs-Orakel; Erfassungen gegen ein Saldenmodell; zufällige Suchtexte
mit Umlauten, ß, Akzenten, NFD und Ligatur.

### Ergebnis der Selbstprüfung

Lauf am 2026-11-08 18:15 über den Gesamtstand (Python 3.13, Profil
`standard`, Commit f952a1c), Protokoll in
`tests/_selbstpruefung/LETZTER_LAUF.md`; er deckt diesen Auftrag vollständig
ab (seitdem keine Änderung an Tests oder Referenz):

- Referenz ohne Mutant: **529 von 529 Kern-Tests grün** (213 M1, 114 M2,
  202 M3).
- **Alle 65 Mutanten erkannt** (38 aus M1/M2, 8 des Lösch-Auftrags, 19 neue):
  Protokoll fehlt bei Mehrfach-Tags bzw. bei der Kontoverarbeitung der
  Synchronisation, Änderung ohne Wirkung, Rückgängig ohne Zustandsprüfung,
  ohne Bezugsprüfung, mit neuen Split-IDs, ohne Vergessen der Kennungen,
  Aliase exakt statt `ekey`, Zusammenführen ohne Aliase, Standardkategorie
  vor Regel, Umbuchung ohne IBAN-Prüfung, ohne Eindeutigkeit, mit
  exklusivem Zeitfenster, Abstimmung trotz Differenz, ohne Sperre, mit
  exklusivem Stichtag, Suche ohne Akzentfaltung, mit ODER, ohne NFC.
- Zusätzlich liefen **alle 219 M2- und die 158 M3-App-Tests dieses Auftrags** (nicht
  nur Kern) grün gegen die Referenz. Dabei gefundene Testfehler (Vorschlag
  nach Statuswechsel schon erledigt; Alias-Kollision im Testaufbau; Empfänger
  eines früher verarbeiteten Kontos wird später verwendet; eine Buchung des
  Altbestands erhält Kennungen aus zwei Konten) sind korrigiert.
- Nachtrag (Lösch-Auftrag): `m3_loeschen.py` bildet inzwischen auch
  Standardkategorien, Abstimmungen und `aenderung_id` nach; alle 60 Tests
  zum Löschen sind Kern-Tests und grün.

### Neue Entscheidungen

- **E-044** Schnitt und Dokumente von Meilenstein 3
- **E-045** Buchbestand, Protokollform und Nettowirkung
- **E-046** Keine Änderung ohne Wirkung; Einheiten der Synchronisation
- **E-047** Rückgängig mit Zustands- und Bezugsprüfung
- **E-048** Rückgängig unabhängig von Status- und Sperrregeln
- **E-049** Empfänger zusammenführen auch bei gesperrten Buchungen
- **E-050** Aliase
- **E-051** Standardkategorie und Empfängername bei der Synchronisation
- **E-052** Erfassungshilfe für manuelle Buchungen
- **E-053** Umbuchungserkennung
- **E-054** Automatische Umbuchungserkennung abschaltbar, Vorgabe aus
- **E-055** Kontenabstimmung je Split, Sperre, Aufheben
- **E-056** Volltextsuche
- **E-057** Rückgängig und Synchronisationszustand
- **E-058** Marker und Testverzeichnis für Meilenstein 3
- **E-059** Umbuchungen in Statistiken

### Einschränkungen und offene Punkte

- Gegen die echte kontor-app wurden die Tests nicht ausgeführt
  (Rollentrennung); geprüft sind sie gegen die Wegwerf-Referenz. M1- und
  M2-Tests sind unverändert; mit `umbuchung_automatisch = False` (Vorgabe)
  bleibt eine M3-Implementierung gegen sie grün.
- T 11 „in Statistiken weder Einnahme noch Ausgabe“ wird über Kontensalden
  geprüft; Berichte folgen in M5 (E-059).
- Nicht getestet: Größe und Aufbewahrung des Protokolls, Leistung des
  Rückgängig bei sehr großen Gruppen, gleichzeitige Rückgängig-Anfragen.
- Die Oberfläche (Undo per Strg+Z, M8) nutzt später `POST
  /api/aenderungen/{id}/rueckgaengig`.

### Nicht Erreichbares

Nichts. Es wurden keine zusätzlichen Pakete, keine externe Domain und kein
weiteres Repository benötigt.

## Widerspruch W-001 (Testablauf, keine Spezifikationsänderung)

Stand: 2026-11-08, Test-Thread.

- **Meldung des Implementierungs-Threads:** In
  `tests/app/m3/test_m3_rueckgaengig.py` wählt die Hilfsfunktion
  `_ausfuehren` für die Operation `konto_weg` ein Konto ohne Vorbedingung aus
  der aktuellen Kontenliste. Sind alle Konten gelöscht, bricht Hypothesis
  mit „Cannot sample from a length-zero sequence“ ab, bevor die Anwendung
  angefragt wird. Betroffen: `test_zufaellige_folgen_rueckwaerts` und
  `test_zufaelliges_rueckgaengig_gegen_orakel`, nur im Profil `gruendlich`.
- **Prüfung:** Zutreffend. Gegen die Wegwerf-Referenz mit
  `HYPOTHESIS_PROFILE=gruendlich` reproduziert: `InvalidArgument` aus
  `st.sampled_from([])` nach zwei gelöschten Konten. Alle anderen
  Operationen prüfen ihre Auswahlliste; ein Buch ohne Konten ist laut
  Spezifikation gültig (`datenmodell.md` 2, Löschen ohne Splits).
- **Korrektur:** `konto_weg` wird nur ausgeführt, wenn mindestens ein Konto
  existiert (sonst ohne Wirkung wie die übrigen Operationen ohne Kandidaten).
  Die Prüfungen der Tests sind unverändert; die Spezifikation ist nicht
  betroffen, deshalb kein E-Eintrag.
- **Nachweis:** Beide Tests mit `HYPOTHESIS_PROFILE=gruendlich` (je 400
  zufällige Beispiele) gegen die Wegwerf-Referenz: 2 bestanden (321 s).

## Widerspruch W-002 (Szenario `beitragsaenderung` in M1-Tests, E-095)

Stand: 2026-11-08, Test-Thread.

- **Meldung des Implementierungs-Threads:** `tests/app/test_paket.py::
  test_ungueltige_konfiguration` (Fall `mock_modus=True,
  mock_szenario=beitragsaenderung`) und `tests/app/test_plugins.py::
  test_unbekanntes_szenario` (MockBank, MockMail) verlangen, dass
  `beitragsaenderung` unbekannt ist; seit M4 ist es gültig (`plugins.md` 8,
  `python-api.md` 10.1/10.3, E-076) und `test_m4_paket.py` verlangt das.
- **Prüfung:** Zutreffend. Gegen die Wegwerf-Referenz (die M4 umsetzt)
  waren die drei Fälle rot. Die Selbstprüfung hatte es nicht bemerkt, weil
  die Tests nicht `kern` sind. E-016 kündigte `beitragsaenderung` schon in
  M1 als späteres Szenario an; der Name war als Beispiel für „unbekannt“
  falsch gewählt.
- **Korrektur (E-095, begründete Ausnahme zu E-029):** Die drei M1-Fälle
  verwenden den nie zu vergebenden Namen `gibtsnicht_m1`; was sie prüfen,
  bleibt gleich. Neuer M4-Test
  `test_beitragsaenderung_auch_fuer_mail_mock_und_unbekannt_bleibt_unbekannt`:
  Mail-Mock nimmt `beitragsaenderung` an und liefert wie `normal`;
  `gibtsnicht_m1` bleibt für Bank-, Mail-Mock und `KontorConfig` ungültig.
- **Nachweis gegen die Referenz:** `test_ungueltige_konfiguration` (alle
  Fälle) und `test_unbekanntes_szenario[MockBank]` grün;
  `test_unbekanntes_szenario[MockMail]` und der neue M4-Test brauchen
  `kontor.plugins.mock_mail`, das die bewusst kleine Referenz nicht hat
  (wie alle übrigen Mail-Mock-Tests, keine `kern`-Tests).

## Meilenstein 4: GnuCash-Import, Lernmodell, Split-Vorlagen

Stand: 2026-11-08, Test-Thread. Umfang laut `spec/meilensteine.md` M4 (Plan
unverändert): GnuCash-Import aus XML (gzip und unkomprimiert) und SQLite,
Lernmodell als zweite Stufe der Kategorisierung (K 7), Split-Vorlagen mit
Mock-Szenario `beitragsaenderung` (K 8).

### Was erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/gnucash.md` | Dateierkennung (gzip, SQLite, XML) und Fehler ohne Teilimport, unterstützter XML- und SQLite-Ausschnitt, Abbildung (Kontoarten, IBAN aus der Kontonummer, versteckt = geschlossen, Empfänger aus der Beschreibung, Verwendungszweck aus der Notiz), Zuordnung über Quellen hinweg, Dublettenerkennung, Ergebnis |
| `spec/api/lernmodell.md` | Modell als Funktion des Buchbestands; Merkmale (Empfänger-Schlüssel, Wörter, Betragsgröße), Trainingsmenge, Naive Bayes mit Laplace-Glättung in exakten Brüchen, Schwelle 7/10, Sicherheit in Promille; Stufenfolge, Anwenden, Vorhersage, Zustand; Mindestgenauigkeit |
| `spec/api/vorlagen.md` | Vorlage (Bedingungen mit Empfänger-Pflicht, feste Teile, Gesamtbetrag), REST, Erkennung ohne Toleranz, Synchronisation (vor den Regeln), Anwenden auf vorhandene Buchungen, Benachrichtigung `split_abweichung` mit Entprellung, Szenario `beitragsaenderung` |
| M4-Abschnitte | `datenmodell.md` 14, `kategorisierung.md` 7, `synchronisation.md` 15, `plugins.md` 8, `python-api.md` 10 (`lernmodell_automatisch`, `kontor.importer.gnucash`), `protokoll.md` 9 (Objekt `vorlage`, Quellen `lernmodell`, `vorlage`), `buchhaltungspflege.md` 9, `loeschen.md` 6 |
| `spec/api/openapi.yaml` | 2.2.0 (inzwischen durch den M9-Thread 2.4.0): `POST /api/import/gnucash`, Tags `lernmodell`, `vorlagen`, neue Schemas; neue Felder bestehender Schemas optional |
| `spec/api/entscheidungen.md` | E-065 bis E-079, E-094 |
| `generator/gnucash.py`, `generator/m4_daten.py`, `generator/m4_lernen.py` | GnuCash-Modell mit Schreibern für XML und SQLite und Erwartungsberechnung; Sonderfälle, 18 Störfälle beider Formate, Standardbuch als GnuCash, Überschneidung mit KMyMoney (Dubletten-Wahrheit); Lerndatensatz (1 184 einfache Buchungen, ca. 4 % falsch erfasst, Empfänger mit mehreren Kategorien, neue Empfänger); Vorlagen-Mockdaten mit Beitragsänderung und Abweichungen um einen Cent |
| `fixtures/gnc/`, `fixtures/m4/`, `fixtures/kmy/m4_lernen_training.*`, `fixtures/mock/m4_*` | neu erzeugt mit `python -m generator` (Generatorversion 4.0.0); SQLite-Fixtures werden bei anderer SQLite-Version über einen Inhalts-Fingerabdruck verglichen |
| `tests/hilfen/m4.py`, `lern_orakel.py`, `gnc_leser.py` | Hilfen, unabhängiges Lernmodell-Orakel, unabhängiger GnuCash-Leser für die Generatortests |
| `tests/app/m4/` | 9 Testmodule, Marker `m4` |
| `tests/generator/test_m4_daten.py` | M4-Fixtures gegen Leser und Orakel |
| `tests/_selbstpruefung/referenz/kontor/m4.py`, `importer/gnucash.py` | Wegwerf-Referenz für M4; 22 neue Mutanten; Selbstprüfung prüft jeden Mutanten zuerst mit den Kern-Tests seines Meilensteins (gleiches Kriterium, deutlich kürzere Laufzeit) |

### Anzahl Tests

Gesammelt (`python -m pytest --collect-only`): **1 497** Testfälle insgesamt
(alle Meilensteine einschließlich M9 des parallelen Test-Threads), davon
**684** mit Marker `kern`.

`python -m pytest -m m4`: **226** Testfälle, davon **101** `kern`:

| Datei | Tests |
| --- | ---: |
| `tests/generator/test_m4_daten.py` | 45 |
| `test_m4_paket.py` | 13 |
| `test_m4_gnucash_import.py` | 23 |
| `test_m4_gnucash_fehler.py` | 45 |
| `test_m4_gnucash_zuordnung.py` | 11 |
| `test_m4_lernmodell.py` | 23 |
| `test_m4_lernmodell_anwendung.py` | 15 |
| `test_m4_vorlagen_api.py` | 27 |
| `test_m4_vorlagen_sync.py` | 19 |
| `test_m4_protokoll.py` | 5 |

Eigenschaftsbasiert (Hypothesis): zufällige GnuCash-Bücher in allen drei
Formaten, zufällige Bytes am Import, zufällige Trainingsmengen gegen das
Orakel, Toleranz der Vorlagen (Teile und Abweichung −2 … +2 Cent),
zufällige Folgen von M4-Operationen rückwärts.

Unabhängige Erwartungen: Import gegen die Wahrheit des Generators (auch für
zufällige Bücher); Lernmodell Vorhersage für Vorhersage gegen
`tests/hilfen/lern_orakel.py`; Vorlagen gegen die Generatorwahrheit und
`tests/hilfen/m4.erkenne`; Überschneidung gegen die Herkunft jeder
GnuCash-Buchung und die Salden des ganzen KMyMoney-Buchs.

### Lernmodell auf den Generatordaten

Mit dem festgelegten Verfahren (Orakel, Startwert 4711): 237 Prüfbuchungen,
193 Vorschläge, davon 189 richtig – **Genauigkeit 97,9 %, Abdeckung
81,4 %** (gefordert 85 % bzw. 70 %). Weitere Startwerte (4712, 4713, 1):
Genauigkeit 98–100 %, Abdeckung 81–84 %. Keine zusätzlichen Pakete nötig
(nur `fractions`, `re`); scikit-learn o. Ä. wurde bewusst nicht verwendet
(E-070).

### Ergebnis der Selbstprüfung

Gesamtlauf am 2026-11-08 (Python 3.13, Profil `standard`, Protokoll in
`tests/_selbstpruefung/LETZTER_LAUF.md`), nach dem Zusammenführen mit der
M9-Referenz des parallelen Test-Threads:

- Referenz ohne Mutant: **684 von 684 Kern-Tests grün** (M1–M4 und M9).
- **Alle 105 Mutanten erkannt**, davon 22 neue für M4:
  `gnc_zweck_aus_beschreibung`, `gnc_versteckt_ignoriert`,
  `gnc_iban_ohne_pruefsumme`, `gnc_vorlagenbaum`, `gnc_ohne_dubletten`,
  `kmy_ohne_gnc`, `lern_ohne_betrag`, `lern_vorschlaege_trainieren`,
  `lern_nur_betrag`, `lern_ohne_glaettung`, `lern_schwelle_halb`,
  `lern_bei_eigener_iban`, `vorlage_toleranz`, `vorlage_inaktiv_greift`,
  `vorlage_nur_erste`, `vorlage_ohne_memo`, `vorlage_ohne_empfaenger`,
  `vorlage_nicht_angewendet`, `vorlage_ohne_benachrichtigung`,
  `vorlage_abweichung_mit_regel`, `vorlage_protokoll_fehlt`,
  `beitragsaenderung_ignoriert`.
- Dauer des Gesamtlaufs: 47 Minuten. Die Selbstprüfung prüft jeden Mutanten
  jetzt zuerst mit den Kern-Tests seines Meilensteins und nur, wenn diese
  grün bleiben, mit allen (gleiches Kriterium; vorher wären es geschätzt
  über fünf Stunden gewesen).
- Der erste Lauf deckte einen echten Widerspruch auf: Zusätzliche Felder im
  `KontoLoeschErgebnis` (E-079) hätten den M3-Test
  `test_loeschen_gegen_orakel` gebrochen; sie entfallen (E-094).
- Die M9-Referenz (`sicherung.py`) sichert jetzt auch Vorlagen; damit ist
  auch der nicht-`kern`-Test `test_vorlagen_in_der_rundreise` gegen die
  Referenz grün, die 13 M9-Mutanten werden weiterhin erkannt.
- W-001: beide betroffenen Tests mit `HYPOTHESIS_PROFILE=gruendlich` gegen
  die Referenz grün (siehe Abschnitt W-001).

### Neue Entscheidungen

- **E-065** Umfang und Aufteilung der Spezifikation für Meilenstein 4
- **E-066** GnuCash: Empfänger aus der Beschreibung, Verwendungszweck aus der Notiz
- **E-067** GnuCash: IBAN aus der Kontonummer, versteckt = geschlossen
- **E-068** Zuordnung über Quellen hinweg (KMyMoney und GnuCash)
- **E-069** GnuCash-SQLite: unterstützter Ausschnitt
- **E-070** Lernmodell: Naive Bayes mit exakter Arithmetik, Schwelle 7/10
- **E-071** Lernmodell ohne eigenen Zustand
- **E-072** Lernmodell bei neuen Buchungen abschaltbar, Vorgabe aus
- **E-073** Messung der Mindestgenauigkeit
- **E-074** Split-Vorlagen: Erkennung, Vorrang, Verhalten bei Abweichung
- **E-075** Benachrichtigung bei Split-Abweichung und Entprellung
- **E-076** Mock-Szenario `beitragsaenderung`
- **E-077** Protokoll: Objekt `vorlage`, Quellen `lernmodell` und `vorlage`
- **E-078** Spezifikationstest für M3 auf erweiterbare Aufzählungen umgestellt
- **E-079** Konto löschen und Split-Vorlagen
- **E-094** Löschergebnis ohne Vorlagenfelder (ersetzt den letzten Teil von
  E-079; im Commit e4cfa73 noch als E-085 bezeichnet, umnummeriert, weil der
  M9-Thread E-085 bis E-093 belegt hatte)

### Hinweise für die Implementierung

- Rückwärtskompatibel: Ohne Vorlagen, ohne `gnc:`-Konten und mit
  `lernmodell_automatisch = False` (Vorgabe) verhält sich alles wie in M3.
  `KontoLoeschErgebnis` bleibt unverändert (E-094).
- Lernmodell exakt rechnen (`fractions.Fraction`), Gleichstände nach
  `kategorie_id`, Sicherheit abrunden (`⌊1000·P⌋`). Trainingsmenge =
  kategorisierte Buchungen ohne offenen Vorschlag, bei jeder Vorhersage
  aktuell (Zwischenspeichern erlaubt, aber nach jeder Änderung ungültig).
- Synchronisation: Stufenfolge Vorlage → Regel → Standardkategorie →
  Lernmodell → „Unkategorisiert“; bei Vorlagen-Abweichung keine weitere
  Stufe; keine Lernmodell-Befragung bei eigener Gegen-IBAN.
- GnuCash: KMyMoney-Import-Regel 2/3 für `gnc:`-Konten erweitern
  (`gnucash.md` 7), jedes vorhandene Konto höchstens einmal je Lauf;
  SQLite nur lesend öffnen (z. B. `sqlite3.connect(":memory:")` und
  `deserialize`, oder `file:…?mode=ro`), Datei unverändert lassen.
- Neue Benachrichtigungsart `split_abweichung`, neue Protokollquellen
  `lernmodell`, `vorlage`, neues Objekt `vorlage` (auch in Rückgängig und
  in der Sicherung aus M9).

### Einschränkungen und offene Punkte

- Gegen die echte kontor-app nicht ausgeführt (Rollentrennung); geprüft
  gegen die Wegwerf-Referenz.
- Die Rundreise der Sicherung mit Vorlagen (`test_vorlagen_in_der_rundreise`,
  M9, nicht `kern`) setzt eine M4-Implementierung voraus; M4-Tests selbst
  hängen nicht von M9 ab.
- Nicht `kern` und damit nicht durch Mutanten abgesichert: Szenario-Details
  der Mock-Bank (Datei mit falschem Typ), Python-API-Varianten des
  Imports, Validierungsfälle und die große Überschneidung in umgekehrter
  Reihenfolge (`langsam`).
- GnuCash-Funktionen außerhalb des Ausschnitts (Wertpapiere, geplante
  Buchungen, Kurse, Mehrwährung) werden nur übersprungen, nicht abgebildet.
- Die Leistung des Lernmodells bei sehr großen Büchern ist nicht getestet
  (gehört zu M7).

### Nicht Erreichbares

Nichts. Keine zusätzlichen Pakete (Lernmodell nur mit der
Standardbibliothek; `sqlite3`, `gzip`, `xml` ebenfalls Standardbibliothek),
keine externe Domain, kein weiteres Repository.

## Meilenstein 9: Datensicherung und Wiederherstellung

Stand: 2026-11-08, Test-Thread. Neues Feature laut Auftrag des Anwenders
(„Backup and Recovery“), Präzisierungen vom Anwender bestätigt. Als M9
nummeriert, umzusetzen nach M4 und vor M5 (E-085).

### Was erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/sicherung.md` | Umfang (Buchbestand mit IDs, Kennungen, Bankkonto-Zustand, ID-Zähler; nie Protokoll, nie Geheimnisse, keine Reste), Format (ZIP mit `manifest.json` und `kontor.sqlite`), Inhaltsprüfsumme aus REST nachrechenbar, Einspielen mit Prüfreihenfolge und festen Fehlergründen, Vergleich und Wirkung, Probelauf, Rückgängig, Zusammenspiel mit Synchronisation |
| `spec/api/protokoll.md` 10, `python-api.md` 11 | Quelle `sicherung`, Aktion `sicherung_einspielen`, Rückgängig inkl. Kennungen und Bankkonto-Zustand; `kontor.sicherung.erstelle_sicherung(config)` |
| `spec/api/openapi.yaml` | Version 2.4.0: `GET /api/sicherung` (application/zip), `POST /api/sicherung/einspielen` (`trocken`, `bestaetigt`), Schemas `SicherungManifest`, `SicherungErgebnis`; neue Fehlercodes |
| `spec/meilensteine.md`, `konzept.md` 14, `testkonzept.md` 23 | M9 im Plan, Datenbank-Export aus M7 nach M9 verschoben, Grundsatz für spätere Meilensteine |
| `spec/api/entscheidungen.md` | E-085 bis E-093 |
| `tests/hilfen/m9.py` | Inhalt und Prüfsumme aus REST, ZIP öffnen/bauen, schemaunabhängige Manipulation der SQLite-Datei, Markierungssuche in Bytes (UTF-8/UTF-16), Testbestände |
| `tests/app/m9/` | 4 Testmodule, Marker `m9` |
| `tests/_selbstpruefung/referenz/kontor/sicherung.py` | Wegwerf-Referenz; 13 neue Mutanten |

### Testanzahl

`python -m pytest -m m9`: **49** Testfälle, davon **46** mit Marker `kern`.
Nicht `kern`: Vorlagen in der Rundreise (braucht M4), Texte mit Hypothesis,
leerer Bankkonto-Zustand im Echtmodus.

### Ergebnis der Selbstprüfung

- Referenz gegen alle Kern-Tests außer M4: **583 bestanden** (inkl. 46
  M9-Tests, alle M1–M3-Kern-Tests unverändert grün nach der Erweiterung von
  Rückgängig in `referenz/kontor/m3.py`), 177 s.
- Jeder der 13 M9-Mutanten wird von den M9-Kern-Tests erkannt
  (`KONTOR_MUTANT=<name> pytest tests/app/m9 -m kern`): `sicherung_mit_protokoll`
  (21 rot), `sicherung_ohne_kennungen` (2), `sicherung_sync_konten_bleiben`
  (5), `sicherung_zaehler_nicht_uebernommen` (1),
  `sicherung_db_pruefsumme_ungeprueft` (3), `sicherung_fremde_tabellen_erlaubt`
  (3), `sicherung_pruefsumme_ungeprueft` (2), `sicherung_modus_ungeprueft` (3),
  `sicherung_identisch_neue_version` (1), `sicherung_probelauf_schreibt` (3),
  `sicherung_ohne_bestaetigung` (2), `sicherung_tan_ignoriert` (1),
  `sicherung_undo_ohne_sync` (1).
- `tests/_selbstpruefung/LETZTER_LAUF.md` ist nicht neu geschrieben: Die
  M4-Kern-Tests (paralleler Test-Thread, Commit c82998b) sind bereits
  eingecheckt, die Referenz deckt M4 aber noch nicht ab. Ein Gesamtlauf wäre
  deshalb unabhängig von M9 rot; er gehört zum Abschluss von M4.

### Einschränkungen und offene Punkte

- Das Schema von `kontor.sqlite` ist bewusst nicht spezifiziert. Die Tests
  prüfen Fehlerfälle nur schemaunabhängig (zusätzliche View, Tabelle,
  Spalte, Trigger; gelöschte erste Tabelle; zerstörte Bytes).
- Migration älterer `schemaversion` (3.4) und die Größengrenze gegen
  ZIP-Bomben (8) sind spezifiziert, aber nicht getestet: Es gibt noch keine
  ältere Schemaversion, und eine Datei über 1 GiB ist für Tests zu groß.
- `sync_laeuft` beim Einspielen ist nur über den Zustand `wartet_auf_tan`
  getestet; ein gleichzeitig laufender Lauf lässt sich im synchronen
  Testclient nicht herstellen.

### Nicht Erreichbares

Nichts. Keine zusätzlichen Pakete, keine externe Domain, kein weiteres
Repository.

### Abgleich mit M4 und dem M3-Nachtrag (E-096)

Stand: 2026-11-09, Test-Thread. M9 war parallel zu M4 und zum Nachtrag
`synchronisation.md` 16 spezifiziert worden. Geprüft wurde jeder fachliche
Zustand aus M1–M4 gegen `sicherung.md` 2 und die M9-Tests (Ergebnis als
Tabelle in `sicherung.md` 2.4).

| Zustand | vorher | jetzt |
| --- | --- | --- |
| Split-Vorlagen | in `anzahl` und Inhaltsprüfsumme; ein einfacher Rundreise-Test, nicht `kern` | zusätzlich Bedingungen mit `konto_id`, inaktive Vorlage, Priorität, Bezug (`konto_in_verwendung`), gleiche Anwendung wie in der Quelle, ID-Zähler; beide Tests `kern` |
| Vorschläge (Regel, Standardkategorie, Lernmodell mit `sicherheit`) | über die Protokollform abgedeckt, aber in keinem Test vorhanden | Rundreise mit allen drei Quellen, danach Annehmen/Ablehnen auf Quelle und Ziel gleich |
| Lernmodell | „kein eigener Zustand“ | ausdrücklich: `GET /api/lernmodell` und Vorhersagen wie in der Quelle; `automatisch` ist Konfiguration des Ziels |
| Konfiguration (`lernmodell_automatisch`, `mock_szenario`, Planer) | nicht erwähnt | nie Teil der Sicherung (2.2) |
| Aliase, Standardkategorien | in der Protokollform | zusätzlich Zuordnung über Alias mit Standardkategorie nach dem Einspielen |
| Gemerkte Kennungen gelöschter Buchungen | nicht ausdrücklich, nicht getestet | ausdrücklich „alle“ (2.1 Punkt 2); Test: gelöschte Bankbuchung kommt nach Einspielen und Abruf nicht wieder |
| Entscheidung je Bankkonto | nur `ignorieren` getestet | zusätzlich `konto_fehlt` ohne Entscheidung, vermerkte Wiederherstellung `"alle"` (Konto und Buchungen kommen im nächsten Lauf zurück), von einem Konto mit der IBAN verdeckte Entscheidung; `konto_id` auf gelöschtes Konto ist kein `inhalt_ungueltig` (5.1) |
| Abstimmungen, Regeln, Verdachte, Tags, Protokoll | abgedeckt (`reicher_bestand`, `test_kein_protokoll_und_keine_reste`) | unverändert |
| Import nach dem Einspielen | spezifiziert (7), nicht getestet | KMyMoney- und GnuCash-Import idempotent auf dem eingespielten Bestand; Importvorgänge der Quelle fehlen |

**Gefundener Fehler in der Wegwerf-Referenz:** Die gespeicherte
Entscheidung ging beim Einspielen als JSON-Liste statt Tupel zurück; eine
vermerkte Wiederherstellung `"alle"` vergaß danach die Kennungen nicht, das
Konto kam leer zurück. `test_vermerkte_wiederherstellung_alle` war rot und
ist nach der Korrektur grün – genau der Fall, den der Nachtrag beheben soll.

Neu: `tests/app/m9/test_m9_vollstaendigkeit.py` (7 Kern-Tests),
`test_vorlagen_in_der_rundreise` jetzt `kern`, 4 neue Mutanten
(`sicherung_kennungen_nur_vorhandene`, `sicherung_ohne_entscheidung`,
`sicherung_zaehler_ohne_vorlage`, `sicherung_vorschlag_ohne_sicherheit`),
jeder von einem der neuen Tests erkannt. Generator unverändert (vorhandene
Fixtures genügen).

`python -m pytest -m m9`: **56** Testfälle, davon **54** `kern`.
Gesamt gesammelt: **1505**, davon **692** `kern`.

Selbstprüfung (Protokoll `tests/_selbstpruefung/LETZTER_LAUF.md`):
Referenz **692/692** Kern-Tests grün, **109/109** Mutanten erkannt
(Mutantenläufe in parallelen Teilläufen wegen der Zeitgrenze eines
Aufrufs).

**Hinweise für die Implementierung von M9:** Kennungen ungefiltert sichern
(auch ohne Buchung); Entscheidung je Bankkonto als eigenes Feld sichern,
Status nicht speichern, sondern ableiten; beim Einspielen keine
Bezugsprüfung für `konto_id` des Bankkonto-Zustands; Typen der gelesenen
Werte normalisieren (der Referenzfehler zeigt, wie leicht ein
Rundreise-Unterschied unbemerkt bleibt); Konfiguration nicht anfassen;
ID-Zähler auch für Vorlagen und Splits.

## M3-Nachtrag: gelöschte Bankkonten bei der Synchronisation

Stand: 2026-11-08, Test-Thread. Auftrag des Anwenders: Nach dem Löschen
eines synchronisierten Kontos legte der nächste Abruf es neu an, aber ohne
Buchungen. Der Anwender soll gefragt werden, ob das Konto neu angelegt wird,
und dann sollen die fehlenden Buchungen zurückkommen.

### Bewertung

Das beobachtete Verhalten entsprach der bisherigen Spezifikation
(`synchronisation.md` 3 Regel 2, gemerkte Kennungen nach 4.3/E-034,
Zeitraum ab `letzter_abruf_bis` nach 4.1), war aber eine echte Lücke: Das
neue Konto war leer und hatte einen falschen Saldo. Der Vorschlag wurde mit
drei Präzisierungen übernommen:

- „Fragen“ geschieht als offene Entscheidung mit Benachrichtigung, weil der
  Planer unbeaufsichtigt läuft; zusätzlich gibt es „ignorieren“, damit
  bewusst entfernte Bankkonten nicht bei jedem Lauf wieder nachfragen.
- Beim Wiederherstellen wählt der Anwender „alle“ oder „nur neue“ Umsätze.
  Bei „alle“ kommen alle von der Bank im Erstabrufzeitraum gelieferten
  Umsätze zurück, deren Buchung nicht mehr existiert; ältere Umsätze lassen
  sich nur durch einen erneuten Import zurückholen.
- Buchungen, die beim Löschen umgebucht wurden und noch existieren, werden
  nicht ein zweites Mal gebucht (sonst doppelte Salden).

### Was geändert wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/synchronisation.md` 16 | Status je Bankkonto, Überspringen im Lauf, Entscheidung, Benachrichtigung `konto_fehlt` |
| `spec/api/protokoll.md` 4.2, 6.1, 6.4 | Vergessen der Kennungen gehört zu `sync_kontozuordnung`; Rückgängig merkt sie wieder; Eintrag bleibt mit `konto_fehlt` |
| `spec/api/openapi.yaml` 2.3.0 | `POST /api/sync/konten/{iban}/entscheidung`, `SyncKontoEntscheidung`, `SyncUebersprungen`, optionale Felder `SyncKontoZustand.status`, `.wiederherstellen_buchungen`, `SyncLauf.uebersprungen` |
| `spec/api/entscheidungen.md` | E-080 bis E-084 |
| `tests/app/m3/test_m3_sync_konto_fehlt.py` | 18 Testfälle, davon 8 `kern` |
| `tests/spec/test_openapi.py` | neue Operation, `test_m3_nachtrag_geloeschte_bankkonten`; M4-Test prüft Version „mindestens 2.2.0“ (E-084) |
| `tests/_selbstpruefung/` | Referenz erweitert, 5 neue Mutanten (`sync_geloeschtes_neu`, `wiederherstellen_ohne_vergessen`, `wiederherstellen_vergisst_alle`, `wiederherstellen_zeitraum_bleibt`, `undo_wiederherstellung_eintrag_weg`) |

Gesammelte Testfälle insgesamt: **1221**, davon **537** `kern`. M1- und
M2-Tests sind unverändert; Läufe ohne gelöschte Bankkonten verhalten sich wie
bisher (E-029). Alle M2- und M3-Tests (455) bestehen gegen die erweiterte
Referenz.

### Ergebnis der Selbstprüfung

`python -m tests._selbstpruefung` (in zwei parallelen Teilläufen, Protokoll
in `tests/_selbstpruefung/LETZTER_LAUF.md`): Referenz **537/537** Kern-Tests
grün, **70/70** Mutanten erkannt (vorher 65). Jeder der fünf neuen Mutanten
wird von einem eigenen Test in `test_m3_sync_konto_fehlt.py` erkannt.

Während des Auftrags wurden M4 und M9 parallel nach `main` gepusht. Nach dem
Zusammenführen wurde erneut geprüft: Referenz **684/684** Kern-Tests grün
(inkl. M4/M9), die fünf neuen Mutanten weiterhin erkannt. `LETZTER_LAUF.md`
enthält den vollständigen Lauf mit 70 Mutanten vom Stand vor dem
Zusammenführen; die M4/M9-Mutanten hat der jeweilige Thread geprüft.

### Hinweis für die Implementierung

Die Anwendung muss für diesen Nachtrag `synchronisation.md` 16 umsetzen:
Bankkonten mit Sync-Eintrag ohne Konto mit ihrer IBAN nicht mehr anlegen,
sondern überspringen und melden; `POST /api/sync/konten/{iban}/entscheidung`;
beim Wiederherstellen mit `"alle"` Kennungen ohne existierende Buchung
vergessen und `letzter_abruf_bis` zurücksetzen (in der Änderung
`sync_kontozuordnung`); Rückgängig nach `protokoll.md` 6.1/6.4. Die
Oberfläche zeigt bei `konto_fehlt` die Frage mit den drei Möglichkeiten
(alle Umsätze, nur neue, ignorieren) ohne Vorauswahl.

## Meilenstein 5: Wiederkehrende Buchungen, Kredite, Berichte, Export

Stand: 2026-11-09, Test-Thread. Umfang laut `spec/meilensteine.md` M5 ohne
Abweichung vom Plan (E-097): wiederkehrende Buchungen (K 9, T 10),
Kredite (K 10, T 12, T 22), Berichte (K 11, T 15, T 11/E-059), Export CSV
und PDF (K 14, T 14).

### Was erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/kredite.md` | Kredit als protokolliertes Objekt (Darlehens-, Zahlungs-, Zinskonto, Parameter, Sondertilgungen, Bedingungen, Zuordnungen, Abgleiche), Anlegen mit Anfangsbuchung, Prüfreihenfolge, Bezüge; Tilgungsplan (Fälligkeiten, Zinstage je Methode, Sondertilgungen, Rundung je Rate, Schlussrate); Erkennung und Aufteilung der Raten (Synchronisation als Stufe 0, auf Wunsch), Jahresabgleich mit genau einer Korrekturbuchung |
| `spec/api/wiederkehrend.md` | zustandslose Erkennung (Gruppen, Kette mit 5 Tagen Toleranz, Rhythmen, Status, Jahreskosten), Ereignisse neuer Empfänger, geänderter Betrag, ausbleibende Zahlung; Prüfung auf Wunsch und automatisch nach dem Abruf (Vorgabe aus) |
| `spec/api/berichte.md` | Kontostandsverlauf (Stichtage je Intervall), Einnahmen/Ausgaben ohne Umbuchungen, CSV-Export (Format, Spalten, verlustfrei), PDF-Export (prüfbare Marken) |
| M5-Abschnitte | `datenmodell.md` 15, `synchronisation.md` 17, `protokoll.md` 11 (Objekt `kredit`, Quelle `kredit`), `sicherung.md` 2.5 (Kredite nur bei Vorhandensein), `python-api.md` 12 (`wiederkehrend_automatisch`, `KreditRateZuKlein`, `kontor.kredite.tilgungsplan`), `loeschen.md` 7 |
| `spec/api/openapi.yaml` | Version 2.5.0: Tags `kredite`, `wiederkehrend`, `berichte`, `export`, 15 neue Operationen, neue Schemas; neue Felder bestehender Schemas optional, Aufzählungen nur erweitert |
| `spec/api/entscheidungen.md` | E-097 bis E-111 |
| `generator/m5_daten.py` | Kreditfälle mit unabhängigem Decimal-Plan, Kredit-Synchronisation mit Jahresauszügen je Zinsmethode, wiederkehrende Buchungen 2023–2024 mit bundesweiten Feiertagen (Gaußsche Osterformel) und Störungen, Berichtswahrheit für `standard.kmy`; Generatorversion 5.0.0 |
| `fixtures/m5/`, `fixtures/mock/m5_*` | neu erzeugt mit `python -m generator`; alle übrigen Fixtures byte-gleich |
| `tests/hilfen/m5.py`, `kredit_orakel.py`, `wiederkehrend_orakel.py` | Hilfen (Bestand mit Krediten, Protokollprüfung, CSV-/PDF-Leser), Bruch-Orakel für Tilgungspläne, Orakel für Serien und Ereignisse |
| `tests/app/m5/` | 12 Testmodule, Marker `m5` |
| `tests/generator/test_m5_daten.py` | Generatorwahrheit gegen die Orakel |
| `tests/spec/test_openapi.py` | neuer `test_m5_schemas`; `test_m4_schemas_rueckwaertskompatibel` und `test_m9_sicherung` wie in E-078/E-084/E-093 gelockert (E-109) |
| `tests/_selbstpruefung/referenz/kontor/m5.py`, `kredite.py` | Wegwerf-Referenz für M5 (Kredite, wiederkehrende Buchungen, Berichte, Export mit reportlab); 30 neue Mutanten |
| `requirements-tests.txt` | zusätzlich `pypdf` (Text des PDF-Exports lesen) |

### Testanzahl

Gesammelt (`python -m pytest --collect-only`): **1 719** Testfälle
insgesamt (vorher 1 505), davon **869** mit Marker `kern`.

`python -m pytest -m m5`: **212** Testfälle (205 App-Tests, 7
Generatortests), davon **177** `kern`; dazu 2 neue Spezifikationstests.

| Datei | Tests | davon `kern` |
| --- | ---: | ---: |
| `tests/generator/test_m5_daten.py` | 7 | – |
| `test_m5_paket.py` | 11 | 3 |
| `test_m5_tilgungsplan.py` | 58 | 58 |
| `test_m5_kredite_api.py` | 20 | 19 |
| `test_m5_kredit_zuordnen.py` | 8 | 8 |
| `test_m5_jahresabgleich.py` | 15 | 15 |
| `test_m5_kredit_sync.py` | 14 | 6 |
| `test_m5_wiederkehrend.py` | 18 | 17 |
| `test_m5_benachrichtigungen.py` | 7 | 5 |
| `test_m5_berichte.py` | 17 | 17 |
| `test_m5_export.py` | 27 | 19 |
| `test_m5_protokoll.py` | 5 | 5 |
| `test_m5_sicherung.py` | 5 | 5 |

Eigenschaftsbasiert (Hypothesis): zufällige Kreditparameter aller
Zinsmethoden mit Sondertilgungen gegen das Bruch-Orakel, Schranke der
Rundungsfehler gegen die ungerundete Rechnung, CSV-Rundreise mit
beliebigen Texten (Trennzeichen, Anführungszeichen, Zeilenumbrüche,
Leerraum am Rand, Formelanfang).

Unabhängige Erwartungen: Tilgungspläne zweifach (Generator mit
`decimal.Decimal`, Tests mit `fractions.Fraction`; der Generatortest prüft
beide gegeneinander); Serien aus der Konstruktion des Generators
(Terminläufe ohne Lücke), gegengeprüft mit dem Orakel; Benachrichtigungen
im wöchentlichen Abruf aus der Konstruktion; Berichte aus dem Modell von
`standard.kmy` und aus den Splits der Buchungsliste; CSV gegen
`GET /api/buchungen`.

### Ergebnis der Selbstprüfung

Lauf am 2026-11-09 (Python 3.13, Profil `standard`, Protokoll in
`tests/_selbstpruefung/LETZTER_LAUF.md`):

- Referenz ohne Mutant: **869 von 869 Kern-Tests grün** (M1–M5 und M9,
  davon 177 neue M5-Kern-Tests); zusätzlich laufen **alle 205 M5-App-Tests**
  (auch die nicht `kern`) grün gegen die Referenz.
- **Alle 139 Mutanten erkannt**, davon 30 neue für M5:
  Kredite `kredit_30_360_tatsaechliche_tage`, `kredit_act365_schaltjahr`,
  `kredit_rundung_abschneiden`, `kredit_sondertilgung_periodenende`,
  `kredit_sondertilgung_unbegrenzt`, `kredit_monatsende_verkettet`,
  `kredit_status_bestaetigt`, `kredit_toleranz_null`,
  `kredit_sync_nicht_aufgeteilt`, `kredit_korrektur_zwei_buchungen`,
  `kredit_abgleich_ohne_status`, `kredit_abgleich_gegen_plan`,
  `kredit_loeschen_zuordnung_bleibt`, `kredit_konto_loeschbar`,
  `kredit_protokoll_fehlt`, `kredit_sicherung_fehlt`,
  `kredit_sicherung_immer_schluessel`; wiederkehrende Buchungen
  `wieder_ohne_toleranz`, `wieder_jahreskosten_monatlich`,
  `wieder_kette_mit_luecke`, `wieder_ausbleibend_ohne_toleranz`,
  `wieder_neuer_empfaenger_einnahme`, `wieder_entprellung_ungelesen`,
  `wieder_erstabruf_meldet`; Berichte und Export
  `bericht_stichtag_exklusiv`, `bericht_umbuchung_als_ausgabe`,
  `bericht_ohne_unterkonten`, `csv_betrag_punkt`, `csv_nur_erster_split`,
  `csv_ohne_bom`.
- Der Gesamtlauf wurde nach 91 Mutanten durch einen Neustart der Umgebung
  abgebrochen; die restlichen 48 liefen mit derselben Funktion in Teilen
  nach (im Protokoll vermerkt).
- Gefunden beim Lauf: zwei Randfälle der Spezifikation (Schlussrate 0,
  Probelauf ohne Konto „Korrekturen“), behoben in E-111.

### Neue Entscheidungen

- E-097 Umfang und Aufteilung der Spezifikation für M5
- E-098 Wiederkehrende Buchungen ohne eigenen Zustand
- E-099 Status, Jahreskosten und nächste Fälligkeit
- E-100 Benachrichtigungen bei unerwarteten Buchungen (je Ereignis genau einmal, abschaltbar, Erstabruf ausgenommen)
- E-101 Kredit als protokolliertes Objekt mit Darlehenskonto
- E-102 Tilgungsplan: Fälligkeiten, Zinstage, Rundung
- E-103 Erkennung und Aufteilung der Raten
- E-104 Sondertilgungen als Parameter, Buchung durch den Anwender
- E-105 Jahresabgleich mit genau einer Korrekturbuchung, ohne Neuverankerung
- E-106 Berichte: Kontostandsverlauf und Einnahmen/Ausgaben
- E-107 CSV-Export: eine Zeile je Split, verlustfrei
- E-108 PDF-Export: Bibliothek frei, prüfbare Marken
- E-109 Kredite in Protokoll und Sicherung, Objektarten nur bei Vorhandensein
- E-110 Konten mit Kreditbezug löschen, Buchungen mit Zuordnung löschen
- E-111 Präzisierungen aus dem Lauf gegen die Wegwerf-Referenz

### Hinweise für die Implementierung

- Rückwärtskompatibel: Ohne Kredite und mit `wiederkehrend_automatisch =
  False` (Vorgabe) verhält sich alles wie in M4/M9. Die Sicherung enthält
  `kredit` in `anzahl`, `inhalt` und `unterschied` **nur**, wenn es Kredite
  gibt; sonst bleiben Manifest und Inhaltsprüfsumme wie in M9 (E-109).
  `SyncKonto.buchungen_kredit` ist neu und ab M5 in jeder Antwort.
- Tilgungsplan exakt rechnen (`fractions.Fraction` oder Ganzzahlen):
  Sollzins in Millionstel, Zins je Rate = ⌊z + ½⌋ aus der exakten Summe
  über die Teile der Periode, Tilgung = Rate − Zins. 30/360: volle
  Perioden immer 30 Tage, nur gebrochene Teile nach 30E/360; act/365 auch
  im Schaltjahr mit 365. Fälligkeiten immer `monat_plus(erste_faelligkeit,
  i − 1)`. Eine Schlussrate von 0 bleibt als Zeile stehen (E-111).
- Raten: Stufe 0 der Synchronisation (vor Vorlagen), Betrag genau die Rate,
  ±5 Tage, Status `vorlaeufig`, Memos `Zinsanteil`/`Tilgungsanteil`;
  Zuordnungen stehen im Kredit und entfallen beim Löschen der Buchung in
  derselben Änderung.
- Jahresabgleich gegen die *gebuchte* Restschuld (Saldo des
  Darlehenskontos) und die Zinsen der Buchungen des Kredits; Splits der
  Korrekturbuchung in der Reihenfolge Zins, Darlehen, Korrekturen, jeweils
  nur ≠ 0; im Probelauf `konto_id = null` für ein noch fehlendes Konto
  „Korrekturen“.
- Wiederkehrende Buchungen ohne gespeicherten Zustand; Benachrichtigungen
  entprellen über *jede* vorhandene Benachrichtigung mit gleichem
  Schlüssel (auch gelesene), anders als `sync_fehler` (E-100).
- CSV genau wie Pythons `csv.writer(…, delimiter=";",
  lineterminator="\r\n")` mit UTF-8-BOM; Listen als JSON. PDF frei
  gestaltbar, aber je Buchung eine Textzeile mit `[#<id>]`, Datum
  `TT.MM.JJJJ` und Betrag; `Anzahl Buchungen: <n>`; geprüft mit `pypdf`.
  `reportlab` und `fpdf2` sind als reine Python-Wheels per pip
  installierbar (geprüft 2026-11-09).
- Konten mit Kreditbezug: `DELETE` und `POST …/loeschen` (auch Probelauf)
  → 409 `konto_in_verwendung` mit `details.kredit_ids`.

### Einschränkungen und offene Punkte

- Gegen die echte kontor-app nicht ausgeführt (Rollentrennung); alle 205
  M5-App-Tests laufen grün gegen die Wegwerf-Referenz.
- Nicht `kern`: PDF-Tests (Referenz nutzt reportlab, aber ohne Mutanten),
  Jahresabgleich mit allen Jahresauszügen über die Synchronisation (die
  Kernregeln prüft `test_m5_jahresabgleich.py`), `from_env`-Varianten,
  Python-API mit `datetime.date`, Benachrichtigungen ohne Automatik.
- Nur monatliche Kreditraten; Zinsanpassungen setzt der Anwender per
  `PATCH` (keine Neuverankerung des Plans, E-105). Sondertilgungen bucht der
  Anwender selbst (E-104).
- Automatische Erkennung von Sondertilgungen und Benachrichtigungen bei
  abweichender Ratenhöhe sind nicht vorgesehen (abweichende Raten laufen
  normal durch die Kategorisierung und fallen im Jahresabgleich auf).
- Die Leistung der Berichte und Exporte bei großen Büchern ist nicht
  getestet (gehört zu M7); spezifiziert sind 5 000 Stichtage und
  mindestens 5 000 Buchungen im PDF.

### Nicht Erreichbares

Nichts. `pypdf` (Testabhängigkeit) und `reportlab` (nur in der
Wegwerf-Referenz) waren bereits installiert; `fpdf2`, `pypdf` und
`reportlab` lassen sich von PyPI laden (geprüft mit `pip download`). Keine
externe Domain, kein weiteres Repository.


## Meilenstein 6: Echte Anbindungen und Benachrichtigungen

Stand: 2026-11-09, Test-Thread. Umfang laut `spec/meilensteine.md` M6 ohne
Abweichung vom Plan (E-112): echtes FinTS-Plugin über python-fints mit
QR-TAN, PIN über systemd-creds oder Eingabe, Mail-Plugin IMAP mit
OAuth2/XOAUTH2 nur lesend für zwei Postfächer, Zustellung per ntfy über eine
austauschbare Schnittstelle mit Mock, TAN-Erinnerungen, verschlüsselter
Geheimnisspeicher. Bezug K 3, K 6, K 13; T 7, T 16, T 17, T 18, T 21; E-028.

### Was erstellt wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/fints.md` | FinTS-Plugin: Prüfreihenfolge, Konten aus UPD/HISPA, camt.052 bevorzugt, MT940 als Rückfall, vollständige Feldabbildung, Hash-Kennung, TAN mit QR-Bild, Fehlerabbildung, nur lesende Segmente, Protokolle; PIN über `$CREDENTIALS_DIRECTORY`; Verhalten der FinTS-Attrappe; Vertrag mit dem Mock |
| `spec/api/mail.md` | Postfach als protokolliertes Objekt, IMAP-Plugin (XOAUTH2, EXAMINE, BODY.PEEK, modifiziertes UTF-7, Abbildung, Fehler), OAuth2 mit PKCE (Start, Abschluss per URL oder Rückruf, Abmelden), Tokens im Betrieb, Ablauf im Google-Testmodus, Abruf parallel mit Spiegel, Mock-Modus, Attrappen |
| `spec/api/benachrichtigungen.md` | Plugins `keins`/`mock`/`ntfy`, ntfy-JSON-Protokoll, Zustellung sofort und Wiederholung, Prioritäten, TAN-Erinnerungen, neue Arten |
| `spec/api/geheimnisse.md` | Was ein Geheimnis ist, Schlüsselquelle (systemd-creds, Datei 0600), AES-256-GCM, REST, „nie im Klartext“, konfigurierbare Endpunkte als Testnaht, Klartext nur auf Loopback, eigene Vertrauensanker |
| M6-Abschnitte | `python-api.md` 13 (35 Konfigurationsfelder, 7 Fehlerklassen, Module), `plugins.md` 9, `synchronisation.md` 18 (PIN-Quelle, Reihenfolge des Planer-Takts), `protokoll.md` 12 (Objekt `postfach`), `sicherung.md` 2.6 |
| `spec/api/openapi.yaml` | Version 2.6.0: Tags `geheimnisse`, `mail`; 17 neue Operationen; neue Felder (`Benachrichtigung.zustellung…`, `SyncStatus.pin_quelle`) optional, Aufzählungen nur erweitert |
| `spec/api/entscheidungen.md` | E-112 bis E-123 |
| `generator/m6_daten.py` | FinTS-Bank (6 Konten, 129 Umsätze Dez. 2023–Juli 2024 als MT940-Bruchstück und camt-Ntry, Störfälle, synthetische PIN/TAN, QR-PNG ohne zlib-Abhängigkeit), vier Postfachordner im mbox-Format (Bestell-/Zahlungsmails, Kodierungen, Anhänge, ohne Message-ID, Dubletten), Mock-Vergleichsdaten, Benachrichtigungserwartungen; Generatorversion 6.0.0 |
| `fixtures/m6/`, `fixtures/mock/m6_*` | neu erzeugt mit `python -m generator`; alle übrigen Fixtures byte-gleich |
| `tests/hilfen/fints_attrappe.py`, `imap_attrappe.py`, `oauth_attrappe.py`, `ntfy_attrappe.py`, `http_attrappe.py`, `tls.py` | lokale Attrappen nur auf 127.0.0.1 (FinTS 3.0 mit python-fints-Segmenten, IMAP4rev1 mit XOAUTH2 nach Gmail-Vorbild, OAuth2 nach Google-Vorbild, ntfy), Testzertifikate |
| `tests/hilfen/m6.py`, `m6_orakel.py` | Hilfen (Konfiguration, Anmeldung, Geheimnissuche, Bestand mit Postfächern) und unabhängige Orakel (MT940, camt, Mail-Abbildung, UTF-7, Erinnerungen) |
| `tests/app/conftest.py` | neue Fixture `netz_nur_loopback` (nur Loopback, ohne Proxy); `netz_gesperrt` unverändert |
| `tests/app/m6/` | 12 Testmodule, Marker `m6` |
| `tests/attrappen/test_attrappen.py` | Selbsttests der Attrappen mit python-fints, imaplib und HTTP (ohne App) |
| `tests/generator/test_m6_daten.py` | Generatorwahrheit gegen die Orakel |
| `tests/spec/test_openapi.py` | neuer `test_m6_schemas`, `test_vertrag_m6_pfade`; `test_m5_schemas` und `test_m9_sicherung` wie in E-109 gelockert (E-118) |
| `tests/_selbstpruefung/referenz/kontor/` | M6 in `m6.py`, `m6_config.py`, `plugins/fints.py` (python-fints), `plugins/imap.py` (imaplib), `plugins/ntfy.py`, Mock-Mail, Benachrichtigungs-Schnittstelle; Postfach in Protokoll und Sicherung; 30 neue Mutanten |
| `requirements-tests.txt` | zusätzlich `fints`, `cryptography`, `requests` |

### Testanzahl

Gesammelt (`python -m pytest --collect-only`): **1 994** Testfälle
insgesamt (vorher 1 719), davon **1 105** mit Marker `kern`.

`python -m pytest -m m6`: **273** Testfälle (246 App-Tests, 12
Attrappen-Selbsttests, 15 Generatortests), davon **236** `kern`; dazu 2 neue
Spezifikationstests.

| Datei | Tests | davon `kern` |
| --- | ---: | ---: |
| `test_m6_paket.py` | 78 | 72 |
| `test_m6_fints_plugin.py` | 30 | 28 |
| `test_m6_fints_sync.py` | 12 | 11 |
| `test_m6_pin_systemd.py` | 15 | 15 |
| `test_m6_geheimnisse.py` | 22 | 22 |
| `test_m6_benachrichtigung.py` | 11 | 11 |
| `test_m6_tan_erinnerung.py` | 14 | 14 |
| `test_m6_imap_plugin.py` | 13 | 13 |
| `test_m6_postfaecher.py` | 20 | 20 |
| `test_m6_mail_abruf.py` | 8 | 7 |
| `test_m6_oauth.py` | 23 | 23 |

Alle M6-App-Tests und Attrappen-Selbsttests laufen grün gegen die
Wegwerf-Referenz (258 Tests).

### Selbstprüfung

Siehe `tests/_selbstpruefung/LETZTER_LAUF.md`. Referenz: alle 1 105
Kern-Tests grün; 30 neue M6-Mutanten, alle erkannt (einer,
`vorwarnung_jeder_takt`, erst nach Verschärfung von
`test_vorwarnung_einmal_je_anmeldung`: Vorwarnung auch nach dem Lesen nur
einmal je Anmeldung). Die 139 Mutanten aus M1–M5/M9 wurden gegen die
erweiterte Referenz erneut ausgeführt (Teilläufe, je unter 10 Minuten):
alle erkannt. Gesamt: Referenz 1 105/1 105 Kern-Tests grün, 169/169
Mutanten erkannt.

### Entscheidungen

E-112 Umfang und Testnähte · E-113 python-fints installierbar, Attrappe auf
Protokollebene · E-114 camt bevorzugt, MT940 Rückfall, Hash-Kennung ·
E-115 PIN über `$CREDENTIALS_DIRECTORY` ohne Aufruf von systemd-creds ·
E-116 Geheimnisspeicher AES-256-GCM, Begriff Geheimnis · E-117 voller
Gmail-Scope, „nur lesend“ durch den Client · E-118 Postfächer im
Buchbestand, Mail-Spiegel Betriebszustand · E-119 Zustellung per ntfy,
auch im Mock-Modus mit `[Mock]` · E-120 sieben Tage im Testmodus:
Erkennung, Vorwarnung, erneute Anmeldung · E-121 TAN-Erinnerungen ·
E-122 Klartext nur auf Loopback, Netzsperre nur Loopback · E-123
Präzisierungen (9380, Doppelte vor `seit`).

### Hinweise für die Implementierung

- python-fints 5.x ist per pip installierbar. Die Attrappe ist mit
  `FinTS3PinTanClient` geprüft (`tests/attrappen`); offene TAN-Dialoge
  müssen in derselben Plugin-Instanz weiterlaufen (Dialog offen halten oder
  `pause_dialog`/`resume_dialog`; bei Pause auf Aufsetzpunkte achten).
  Rückmeldungen zu Aufträgen kommen nur über `add_response_callback`; eine
  falsche TAN liefert sonst eine leere Liste (9941 auswerten).
- python-fints schreibt auf `DEBUG` ganze Nachrichten mit TAN in den Logger
  `fints.connection`; die Tests setzen den Logger `fints` auf `DEBUG` und
  suchen die TAN – unterdrücken (z. B. Logger abschalten oder filtern).
- Die Bibliothek `mt-940` setzt das Vorzeichen bei `RC`/`RD` anders als
  SWIFT und verbindet `?31` mit dem Namen; die Abbildung steht vollständig in
  `fints.md` 3.4.
- Zeitgrenzen: requests in python-fints hat keinen Timeout; er muss gesetzt
  werden (`fints_timeout_sekunden`). TLS immer mit `tls_ca_datei`, wenn
  gesetzt.
- Gmail-IMAP erlaubt nur den Scope `https://mail.google.com/`; „nur
  lesend“ prüft die Attrappe über die Befehlsliste (EXAMINE, BODY.PEEK).
- Zustellung muss vor der Antwort geschehen; die Antwort von
  `POST /api/wiederkehrend/pruefen` (M5) wird mit `GET
  /api/benachrichtigungen` verglichen und enthält daher schon die
  Zustellfelder.
- `/api/status.plugins` bleibt unverändert (M1-Test vergleicht exakt).
- Einige Tests warten bis zu etwa 2,5 Sekunden (Zeitüberschreitungen,
  kurze Token-Lebensdauer).

### Einschränkungen und offene Punkte

- Gegen die echte kontor-app nicht ausgeführt (Rollentrennung); alle 258
  M6-Tests laufen grün gegen die Wegwerf-Referenz.
- Nicht `kern`: einige `from_env`-Varianten, Unkonfiguriert-Fälle,
  Protokoll der Bibliothek `fints` ohne TAN (deckt der Kern-Test
  `test_keine_geheimnisse_in_protokollen` mit ab), Planer ohne Intervall.
- Die echte Gmail-Anbindung, echte Banken und ntfy.sh werden nie
  angesprochen (E-028); ob eine konkrete Bank camt.052.001.08 anbietet,
  bleibt im Betrieb zu prüfen (MT940 ist der Rückfall).
- Entkoppelte Freigaben (Banking-App ohne QR, Rückmeldung 3955) sind nicht
  unterstützt (K 6: QR-TAN).
- Die TAN-Seite selbst (`/tan/<id>`) und die Anmeldeoberfläche gehören zu M8.
- Der Mail-Abgleich mit Sammelbuchungen bleibt außerhalb des Plans.

### Nicht Erreichbares

Nichts. `fints` 5.0.1 (mit `mt-940`, `sepaxml`, `bleach`, `enum-tools`)
wurde von PyPI installiert, `cryptography` 50 war vorhanden. Keine externe
Domain wurde von Tests angesprochen; kein weiteres Repository.

## Widerspruch W-004 (exakte Objektvergleiche gegen spätere optionale Felder, E-124)

Gemeldet vom Implementierungs-Thread (als Text): `tests/app/m2/test_m2_sync.py::test_laeufe_und_status`
verglich `GET /api/sync/status` exakt mit den acht M2-Feldern; das seit M6 optionale Feld `pin_quelle`
(im M6-Test auch bei der Vorgabe `eingabe` Pflicht) ließ ihn scheitern. Die Wegwerf-Referenz zeigte den
Widerspruch ebenso (sie liefert `pin_quelle` immer).

**Bewertung:** echter Fehler des M2-Tests gegenüber E-029. Lösung (E-124) ohne Änderung des Testtexts:

- `tests/hilfen/vertrag.py` liefert geprüfte Antwortobjekte als `Antwortobjekt`: Gegenüber einer
  Erwartung des Tests müssen alle erwarteten Felder vorhanden und gleich sein, zusätzliche Felder sind
  nur erlaubt, wenn das Schema sie optional führt; zwei Antwortobjekte werden exakt verglichen. Die
  Schemaprüfung (`additionalProperties: false`) bleibt davor.
- **Systematische Suche** mit dem neuen Erweiterungslauf `KONTOR_TESTS_ZUSATZFELDER=1` (jedes
  Antwortobjekt bekommt ein zusätzliches optionales Feld): vorher 203 zusätzliche Fehlschläge gegen die
  Referenz in allen Meilensteinen (Regeln, Vorschläge, Protokollformen, Kredite, Berichte, Geheimnisse,
  Postfächer, Sicherung), mit `Antwortobjekt` noch elf. Davon fünf echte Schwachstellen, gezielt
  angepasst: `test_m5_kredite_api.py::test_anlegen_mit_anfangsbuchung` (exakte Schlüsselliste →
  `pruefe_felder`), `test_m5_kredite_api.py::test_plan_des_kredits_gleich_orakel` und
  `test_m9_vollstaendigkeit.py::test_vorlagen_mit_bezuegen_reihenfolge_und_zaehler` (gelesene Objekte
  wurden als Anfragekörper zurückgeschickt → nur Felder des Anfrageschemas), `ohne_lauf` in
  `test_m3_konto_loeschen.py` und `ohne_id` in `test_import_kmy.py::test_rest_und_python_gleich`
  (Kopie verlor die Regel → Hilfe `ohne`). Sechs Artefakte (Inhaltsprüfsummen aus REST-Daten):
  `ohne_zusatzfeld` vor dem Hashen in `tests/hilfen/m9.py`, der M6-Postfachtest nutzt `inhalt_sha256`.
- Ergebnis gegen die Referenz (alle App-Tests, `-n 2`, Profil `schnell`): ohne Zusatzfelder und mit
  Zusatzfeldern dieselben 14 Fehlschläge, die nur an der unvollständigen Referenz liegen
  (`test_plugins.py`, `test_create_app_aus_umgebung`); `test_laeufe_und_status` ist jetzt grün.
- Die Selbstprüfung enthält den Erweiterungslauf als zweiten grünen Lauf („Referenz mit
  Zusatzfeldern“). Implementierungs-Threads können ihn ebenso gegen kontor-app ausführen:
  `KONTOR_TESTS_ZUSATZFELDER=1 python -m pytest tests/app`.

## Meilenstein 7: Sicherheit und Betrieb

Auftrag vom 2026-11-09. Spezifikation, Generator, Tests und Selbstprüfung für
Login und Sicherheit, Betrieb (systemd, Neustart, Datenbank-Export) und
Leistung; Grundlage K 2, K 3, K 6, T 18, T 20.

### Was erstellt wurde

- **Spezifikation:** `spec/api/sicherheit.md` (Haushaltskonto mit scrypt,
  Sitzungen mit Cookie-Attributen und Ablauf nach Systemuhr, Bremse mit
  Verdopplung, CSRF-Token und Herkunftsprüfung, Ersteinrichtung per
  Einrichtungscode oder Kommandozeile, Sicherheitsköpfe mit CSP,
  Eingabehärtung, Größengrenzen, Netzbeschränkung, keine Geheimnisse in
  Logs), `spec/api/betrieb.md` (Paket `kontor.betrieb` mit Units, Drop-in,
  sysusers und Umgebungsdatei; `python -m kontor`; Beenden mit Frist und
  WAL-Checkpoint; Gesundheitsprüfung; Logging; zeitgesteuerte Sicherung
  `sichere_in_verzeichnis` und `python -m kontor.sicherung`),
  `spec/api/leistung.md` (Datensatz, Messverfahren, 15 Grenzwerte);
  `python-api.md` 14, `protokoll.md` 13, `sicherung.md` 9, `openapi.yaml`
  2.7.0 (Tags `anmeldung`, `betrieb`, sechs Operationen,
  `x-allgemeine-antworten`), `meilensteine.md`, E-125 bis E-137.
- **Generator:** `generator/m7_gross.py`, `python -m generator --gross`
  (50 000 Buchungen, auf Abruf, Prüfsummen in `MANIFEST.json` unter
  `auf_abruf`), Version 7.0.0; `tests/generator/test_m7_gross.py`.
- **Tests:** `tests/app/m7/` (6 Dateien), `tests/hilfen/m7.py`,
  `tests/hilfen/systemd.py`; Anmeldelauf in `tests/hilfen/api.py`.
- **Selbstprüfung:** Referenz-Teile `m7.py`, `m7_config.py`,
  `anmeldung.py`, `betrieb/`, `__main__.py`, Beenden mit Frist in `m2.py`,
  Sicherung im Verzeichnis in `sicherung.py`; 23 neue Mutanten.

### Testanzahl

| Bereich | Tests |
| --- | --- |
| `test_m7_paket.py` | 66 |
| `test_m7_anmeldung.py` | 42 |
| `test_m7_haertung.py` | 38 |
| `test_m7_betrieb.py` | 18 |
| `test_m7_sicherung.py` | 3 |
| `test_m7_leistung.py` | 22 (Marker `leistung`) |
| `tests/generator/test_m7_gross.py` | 3 |
| Spezifikation (`test_m7_schemas`, allgemeine Antworten, Antwortobjekte) | 3 |

Gesamt nach M7: 2 189 Tests (vorher 1 994), davon 192 mit Marker `m7`,
113 `kern`-Tests in M7.

### Ergebnis gegen die Wegwerf-Referenz

- Alle M7-Tests ohne `leistung` grün bis auf zwei, die eine echte
  SQLite-Datenbank bzw. einen gemeinsamen Zustand über Prozesse brauchen
  (`test_wal_modus_und_checkpoint`, `test_kommandozeile_passwort`; die
  Referenz hält alles im Arbeitsspeicher). Beenden während eines Laufs,
  Frist, Startmodul mit SIGTERM und die anderen Kommandozeilen sind gegen
  die Referenz grün.
- Leistungstests gegen die Referenz mit `KONTOR_LEISTUNG_FAKTOR=50` grün
  (Prüfung der Ergebniswerte gegen die Generatorwahrheit; die Zeiten der
  Referenz sind kein Maßstab).
- Anmeldelauf (`KONTOR_TESTS_ANMELDUNG=1`) mit allen Kern-Tests von M1 und
  M2: 327 grün.

### Ergebnis der Selbstprüfung

`tests/_selbstpruefung/LETZTER_LAUF.md`: Referenz 1 218/1 218 Kern-Tests grün,
ebenso im Erweiterungslauf mit Zusatzfeldern (E-124); 192/192 Mutanten
erkannt, davon 23 neue für M7 (Hash/NFC, gespeicherte Parameter,
Passwortlänge, Schutzlücke, 404 statt 401, CSRF, Herkunft, Sperre,
Verdopplung, Leerlauf, Höchstdauer, Abmelden, Passwortänderung, HttpOnly,
nosniff, CSP, Upload- und Anfragegrenze, Netz, X-Forwarded-For, Hash in der
Sicherung, Aufbewahrung je Modus und der neuesten). Gefundene Schwäche:
`test_hoechstdauer` prüfte über das clientseitig verfallene Cookie statt
den Server; korrigiert. Alle 169 früheren Mutanten bleiben mit den
Antwortobjekten (E-124) erkannt – die nachsichtigere Gleichheit hat keine
Prüfung abgeschwächt.

### Entscheidungen

E-125 Anmeldung abschaltbar, Vorgabe aus, Betrieb mit Anmeldung,
Anmeldelauf als Testhilfe; E-126 scrypt; E-127 allgemein zulässige Antworten
401/403/413/429; E-128 Sitzungen; E-129 Bremse und CSRF; E-130
Eingabehärtung, Größengrenzen, CSV unverändert; E-131 systemd mit festem
Benutzer und `LoadCredentialEncrypted`; E-132 Datenbank-Export = M9-Sicherung,
zeitgesteuert; E-133 Leistungsziele; E-134 Datensatz auf Abruf; E-135
Anmeldedaten sind Betriebszustand; E-136 sauberes Beenden; E-137
Netzbeschränkung.

### Hinweise für die Implementierung

- Prüfreihenfolge als reine ASGI-Hülle vor FastAPI: Netz → Sitzung (401
  vor 404/405/413/422) → Herkunft → CSRF-Token → Größe (Körper zählen,
  auch ohne `Content-Length`) → Routing/Validierung. Sicherheitsköpfe auch
  auf selbst erzeugten Antworten (401, 303, 413) und `X-Kontor-Modus` auf
  allen `/api/`-Antworten.
- FastAPI validiert den Körper vor dem Endpunkt; für die Reihenfolge
  409 `anmeldung_abgeschaltet` vor 422 den Körper der Anmelde-Endpunkte
  selbst prüfen. Der Standard-422-Handler gibt `input` zurück – darf
  Passwort, Einrichtungscode, PIN und TAN nicht enthalten.
- `json.loads` wirft bei tiefer Verschachtelung `RecursionError` (sonst 500),
  ungültiges UTF-8 ergibt bei FastAPI 400 – beides muss 422 sein.
- Der Testclient (httpx) sendet `Secure`-Cookies nicht über `http` und
  verwirft Cookies nach `Max-Age`; die Tests berücksichtigen das.
- Sitzungen und Sperren nach Systemuhr, nie nach der Mock-Uhr.
- `python -m kontor`: uvicorn mit `proxy_headers=False`,
  `server_header=False`; nach SIGTERM darf der Prozess mit 0 oder durch das
  Signal enden. Konfigurationsfehler → Rückgabecode 2, eine Zeile
  `Konfigurationsfehler: …`.
- Beim Lifespan-Ende: Planer stoppen, laufendes Konto bis zur Frist,
  danach Lauf `abgebrochen`, ein verspätetes Konto darf nichts mehr
  schreiben; `wal_checkpoint(TRUNCATE)`.
- `kontor.betrieb` als Paket mit Paketdaten ausliefern (in
  `pyproject.toml` die Dateien einschließen).

### Einschränkungen und offene Punkte

- Leistungsgrenzen sind für die Testumgebung (2 Kerne) festgelegt; ein
  paralleler Implementierungslauf auf derselben Maschine kann Messungen
  verfälschen. `KONTOR_LEISTUNG_FAKTOR` nur für erkennbar langsamere
  Rechner.
- Kein TLS im Anwendungsserver, keine Formelinjektion-Abwehr im
  CSV-Export (bewusst, E-130), keine Reverse-Proxy-Unterstützung (E-137).
- Die systemd-Units werden nur statisch geprüft (kein systemd in der
  Testumgebung); Härtung im LXC braucht `nesting=1`.

## Widerspruch W-005: Test-Benachrichtigung (E-138)

Meldung des Implementierungs-Threads: Die Anwendung hat für den Knopf
„Test-Benachrichtigung senden“ den nicht spezifizierten Endpunkt
`POST /api/benachrichtigungen/test` eingeführt.

### Entscheidung

In den Vertrag aufgenommen (`benachrichtigungen.md` 8, `openapi.yaml` 2.8.0,
Schema `TestBenachrichtigung {plugin, zugestellt, gesendet, fehler}`):

- ohne Körper, geschützt wie jeder Endpunkt (Sitzung, CSRF);
- Plugin `keins` → 409 `kein_benachrichtigungs_plugin`;
- Plugin `mock` → 200, `zugestellt = true`, `gesendet = false`, **kein**
  Aufruf von `senden`, nichts unter `/api/mock/zustellungen` (wie bisher in
  der Anwendung);
- Plugin `ntfy` → genau eine Veröffentlichung (Titel
  `Kontor: Test-Benachrichtigung`, im Mock-Modus mit `[Mock] `, Priorität 3,
  Tag `test`, `click` nur mit `oeffentliche_url` auf `/einstellungen`);
  Fehlschlag als 200 mit `zugestellt = false` und
  `fehler {code: benachrichtigung_fehler, meldung, status}`, keine
  Wiederholung;
- keine Benachrichtigung, keine Änderung an Zustellstatus, Protokoll oder
  Sicherung.

### Tests

`tests/app/m8/test_m8_testbenachrichtigung.py` (10 Tests, Marker `m8`, ohne
Browser; 6 davon `kern`), `tests/spec/test_openapi.py::test_m8_schemas`.
Gegen die Wegwerf-Referenz grün, Mutant `m8_test_in_mock_liste` erkannt.

### Hinweis für die Implementierung

Die bisherige Antwort der Anwendung (`{"gesendet": true, "plugin": "mock"}`)
passt nicht zum Schema: Im Mock-Fall `gesendet = false`, dazu die Felder
`zugestellt` und `fehler`; `keins` ist 409 statt 200.

## Meilenstein 8: Vollständige Oberfläche

Auftrag vom 2026-11-09. Spezifikation, Generator, Tests und Selbstprüfung für
die Single-Page-Oberfläche nach K 5, K 6 und K 14 (T 19). Playwright für
Python 1.63 mit dem gebündelten Chromium 153 (headless) war vorhanden und
startet in der Umgebung; geprüft mit `/usr/bin/google-chrome` als Ausweichweg.

### Was erstellt wurde

- **Spezifikation:** `spec/api/oberflaeche.md` (21 Abschnitte: Grundsätze,
  Auslieferung, Routen, Grundgerüst, Darstellung, Finanzübersicht,
  Kontoansicht mit Filtern/Sortierung/Seiten, Auswahl, Mehrfachbearbeitung,
  Inline-Bearbeitung, Kontextmenüs, Dialoge, Drag and Drop, Rückgängig,
  Tastatur und Befehlspalette, weitere Seiten, TAN-Seite, Panels und Layout,
  mobile Ansicht mit Gesten, Design, PWA, Anmeldung, Barrierefreiheit,
  Testumgebung); `benachrichtigungen.md` 8, `python-api.md` 15,
  `openapi.yaml` 2.8.0, `meilensteine.md` (Status, offene Teile),
  E-138 bis E-150.
- **Generator:** `generator/m8_daten.py`, Version 8.0.0:
  `fixtures/m8/oberflaeche.kmy` (Haushaltsbuch 2024, Kategorienbaum mit drei
  Ebenen, Umlaute, HTML-artiger Verwendungszweck, Splitbuchung, Tags,
  geschlossenes Konto, Darlehen; Erwartung mit Pfaden, Baumreihenfolge und
  sieben Filterfällen) und `fixtures/m8/viele.kmy` (450 Buchungen für das
  seitenweise Laden); `tests/generator/test_m8_daten.py`.
- **Testhilfen:** `tests/hilfen/m8.py` (App unter uvicorn im Testprozess,
  REST-Prüfung über HTTP mit Vertragsprüfung, Gesten über CDP, Maus-Drag,
  Betragsformat, Kontrast), `tests/app/m8/conftest.py` (Browser einmal je
  Lauf, Kontext je Test, Überwachung von Skriptfehlern, CSP-Verletzungen und
  fremden Anfragen, Anmeldelauf).
- **Tests:** `tests/app/m8/` (14 Dateien).
- **Selbstprüfung:** Wegwerf-Oberfläche `referenz/kontor/oberflaeche/`
  (`app.js`, `app.css`, `sw.js`) und `referenz/kontor/m8.py`; 9 neue
  Mutanten.

### Testanzahl

| Bereich | Tests | davon `kern` |
| --- | --- | --- |
| `test_m8_testbenachrichtigung.py` (W-005, ohne Browser) | 10 | 6 |
| `test_m8_auslieferung.py` (ohne Browser) | 29 | 26 |
| `test_m8_grundgeruest.py` | 60 | 46 |
| `test_m8_kontoansicht.py` | 30 | 0 |
| `test_m8_auswahl.py` | 9 | 6 |
| `test_m8_kontextmenue.py` | 11 | 4 |
| `test_m8_tastatur.py` | 8 | 5 |
| `test_m8_bearbeiten.py` | 14 | 0 |
| `test_m8_split_dnd.py` | 8 | 0 |
| `test_m8_panels_mobil.py` | 13 | 0 |
| `test_m8_thema_pwa.py` | 7 | 0 |
| `test_m8_tan_kredit.py` | 14 | 0 |
| `test_m8_seiten.py` | 16 | 0 |
| `test_m8_anmeldung_a11y.py` | 22 | 0 |
| `tests/generator/test_m8_daten.py` | 5 | – |
| Spezifikation (`test_m8_schemas`) | 1 | – |

Gesamt nach M8: 2 446 Tests (vorher 2 189), davon 256 mit Marker `m8`
(212 Browsertests, Marker `browser`), 93 `kern`-Tests in M8.
T 19 vollständig abgedeckt: Finanzübersicht, Kontoansicht, Filtern,
Mehrfachbearbeitung, Split bearbeiten und Kreditabgleich je desktop und
mobil (parametrisiert über `geraet`), einblendbares Menü, Panels verschieben
und Größe ändern mit Speicherung, Kontextmenüs, Drag and Drop, Mehrfachauswahl
mit Strg und Umschalt, Tastaturkürzel, Undo per Strg+Z, lange Berührung und
Wischgesten.

### Ergebnis der Selbstprüfung

`tests/_selbstpruefung/LETZTER_LAUF.md`: Referenz 1 311/1 311 Kern-Tests grün,
ebenso mit Zusatzfeldern (E-124); 9/9 neue Mutanten erkannt (Strg ersetzt
statt umzuschalten, Umschalt ohne Anker, Rechtsklick ohne Auswahlwechsel,
Palette ohne Umlautfaltung, Mehrfach nur mit erster Buchung, Mock-Hinweis
mobil verborgen, Inline-Skript in der Hülle, Esc ohne Fokusrückgabe,
Test-Benachrichtigung in der Mock-Liste); 12 Stichproben früherer Mutanten
(je Meilenstein mindestens einer) weiter erkannt. Die Referenz wurde für M8
nur additiv erweitert (neue Routen, Hülle, statische Dateien, ein Endpunkt),
deshalb wurden die 192 früheren Mutanten nicht vollständig wiederholt
(Zeitgrenze, 2 Kerne). M8-Kern-Tests auch im Anmeldelauf grün (93).
Gefundene Schwächen beim Prüfen gegen die Referenz: die Mock-Hinweis-Prüfung
schlug zu Recht an, solange die Referenzseite auf dem Handy breiter als der
Bildschirm war (Chrome verkleinert dann die Ansicht) – das deckt zugleich
die Regel „kein waagerechtes Scrollen“.

Die Browsertests ohne `kern` laufen nur gegen die Anwendung (die
Wegwerf-Seite deckt bewusst nur die Kernfunktionen ab, E-149); gegen die
Referenz scheitern sie an fehlenden Elementen, nicht an Fehlern der Tests
(geprüft: nur Zeitüberschreitungen beim Warten auf nicht vorhandene
`data-testid`).

### Neue Entscheidungen

E-138 Test-Benachrichtigung (W-005); E-139 Oberflächen-Vertrag über
`data-testid`/ARIA, Playwright, Überspringen ohne Browser; E-140 Routen als
Pfade, Filter in der URL; E-141 Layout und Design im Browser-Speicher;
E-142 Undo per Strg+Z über das Protokoll; E-143 „Als Dublette markieren“ für
vorhandene Verdachte; E-144 Kategorien umsortieren = Elternkategorie;
E-145 Gesten auf dem Handy; E-146 PWA (Manifest öffentlich, `/sw.js`,
offline nur Hülle); E-147 TAN-Seite: Speichern und Teilen; E-148 vollständige
Navigation mit Mindestumfang weiterer Seiten; E-149 Selbstprüfung mit
Wegwerf-Seite; E-150 Abschluss des Plans, Vertragsprüfungen, offene
Konzeptteile.

### Hinweise für die Implementierung

- Bereitschaft signalisieren: `app[data-bereit="ja"]`, je Seite
  `data-geladen` (beim Neuladen nach Änderungen kurz `nein`). Fast alle
  Tests warten darauf.
- Beträge und Daten zusätzlich maschinenlesbar (`data-betrag` in Cent,
  `data-datum` ISO); Text mit `Intl.NumberFormat("de-DE", EUR)`.
- Kein Inline-Skript, keine `on…`-Attribute (CSP aus M7); Texte nur per
  `textContent`. Keine fremden Hosts, auch keine Schriften.
- Buchungsliste = genau `GET /api/buchungen?konto_id=…&sortierung=-datum&
  pro_seite=200` plus Filter; Filter mit REST-Namen in der URL.
- Auswahlregeln (Anker!) und Kontextmenü-Regel (Rechtsklick außerhalb der
  Auswahl setzt sie neu) wie im Dateimanager; Gesten selbst erkennen
  (Chromium löst bei langer Berührung kein `contextmenu` aus).
- Undo: höchste Änderungs-ID vor der Aktion merken, danach die neuen
  Änderungen (ohne Gruppe `sync:`) als einen Stapeleintrag.
- Drag and Drop muss mit echten Mausereignissen funktionieren (HTML-DnD
  oder Pointer Events); während des Ziehens eines Panelkopfs die Ablagen
  `ablage-links`/`ablage-rechts` mindestens 48 px breit zeigen.
- Mobil (< 768 px): keine Elemente breiter als der Bildschirm, sonst
  verkleinert Chrome die Seite und der Mock-Hinweis rutscht aus dem Bild.
- Service Worker unter `/sw.js` mit `Cache-Control: no-cache`; nie `/api/`
  cachen; offline `offline-hinweis` statt Daten.
- `POST /api/benachrichtigungen/test` an E-138 anpassen (siehe W-005).
- Eine Rückfall-Route der Oberfläche (Hülle für alle Pfade) darf `/api/`
  nicht erfassen: `GET /api/benachrichtigungen/test` muss 405
  `methode_nicht_erlaubt` liefern, nicht 404 (allgemeine Regel in
  `openapi.yaml`); ein Lauf gegen die installierte Anwendung zeigte 404.

### Einschränkungen und offene Punkte

- Nur Chromium wird getestet (Firefox/Safari nicht in der Umgebung); Web
  Share wird mit einer Attrappe geprüft, weil Headless-Chromium Dateien
  nicht teilen kann.
- Die Browsertests ohne `kern` sind nicht gegen eine Implementierung
  erprobt (es gibt noch keine Oberfläche nach `oberflaeche.md`); Unklarheiten
  bitte als Widerspruch melden.
- Leistung der Oberfläche (große Listen) wird nicht gemessen; die Liste lädt
  seitenweise (200), die Grenzwerte der REST-Schnittstelle gelten (M7).
- Nach M8 offene Teile des Konzepts (E-150): Mail-Abgleich von
  Sammelbuchungen (K 1, K 13), Belege (K 4, K 5 „später“), PostgreSQL (K 3),
  weitere Berichte (K 11), K 15 und K 16; Abdeckung und Mutationswert der
  Anwendung (T 2) liegen bei kontor-app.

### Nicht Erreichbares

Nichts; Playwright und Chromium waren vorhanden.

## Widersprüche W-007 und W-008 (Oberflächentests, E-151)

Stand: 2026-11-09, Test-Thread.

- **W-007 (berechtigt, Testfehler):** `test_buchung_auf_kategorie_ziehen` und
  `test_wischen_links_setzt_kategorie_und_rueckgaengig` nahmen die dritte
  Zeile der Girokonto-Liste. Nach der Generatorwahrheit
  (`fixtures/m8/oberflaeche.erwartung.json`) ist das `kmy:T…093` „Sparrate“
  (15.12.2024, `umbuchung: true`, kein Gegensplit), also nach
  `datenmodell.md` 3.2/E-007 nicht kategorisierbar. Die Tests wählen jetzt
  über `tests/hilfen/m8.kategorisierbare` (genau ein Gegensplit nach der
  Wahrheit, Kategorie ≠ Ziel, für Umschalt-Bereiche lückenlos benachbart)
  bzw. `m8.umbuchung_zeile`. E-151 und `oberflaeche.md` 10 präzisieren:
  `km-kategorie`/`mehrfach-kategorie` senden auch bei Umbuchungen und zeigen
  die Ablehnung mit der `meldung` des Servers; beim Ziehen/Wischen darf die
  Oberfläche die Ablage auch früh ablehnen; der Bestand bleibt unverändert.
- **W-008 (berechtigt, Testfehler):** `test_protokollseite` schnitt von
  `aenderung-<id>` nur neun Zeichen ab. Die ID wird jetzt mit
  `^aenderung-([0-9]+)$` gelesen, zusätzlich: alle IDs positiv. Keine
  Spezifikationsänderung (in Chromium an einer statischen Seite geprüft).
- **Weitere robust gemachte Tests** (bisher nach Listenposition, zufällig
  ohne Umbuchung): `test_m8_auswahl.py::test_mehrfach_kategorie` (prüft nun
  auch, dass die übrigen Zeilen unverändert bleiben),
  `::test_einzelne_buchung_kategorie_per_put`,
  `::test_kategorie_auswahl_tastatur_und_esc`, `::test_mehrfach_fehler_atomar`
  (Prämisse: beide Buchungen kategorisierbar, damit allein die Sperre 409
  auslöst), `test_m8_kontextmenue.py::test_kategorie_setzen_ueber_menue`,
  `test_m8_bearbeiten.py::test_datum_und_kategorie` (wählte bisher aus einer
  Ausgabe der Anwendung). Auswahl-, Tag-, Lösch- und Inline-Tests für den
  Verwendungszweck sind für jede Buchung gültig und blieben unverändert.
- **Neue Tests:** `test_m8_kontextmenue.py::test_kategorie_setzen_umbuchung_meldet_ablehnung`
  (`kern`: Fehlermeldung mit `role="alert"` und Servermeldung, kein
  Protokolleintrag, Zelle weiter „Umbuchung“) und
  `test_m8_split_dnd.py::test_umbuchung_auf_kategorie_ziehen_aendert_nichts`.
  Gesamt 2 448 Tests (vorher 2 446), 1 312 `kern` (94 in M8).
- **Selbstprüfung:** Referenz 1 312/1 312 Kern-Tests grün (`-n 2`), M8-Kern
  auch mit Zusatzfeldern grün (94); alle 10 M8-Mutanten erkannt, darunter
  der neue `m8_fehler_ohne_servermeldung`. Die geänderten Nicht-Kern-Tests
  scheitern gegen die Wegwerf-Seite erwartungsgemäß nur an dort fehlenden
  Elementen (`panel-kategorien`, `kategorie-auswahl` nach Wischen,
  `inline-editor`), nach erfolgreicher Zeilenauswahl.

## Meilenstein 10: AqBanking-Plugin

Stand: 2026-11-09, Test-Thread. Auftrag des Anwenders: die Bankanbindung
zuerst über das bei ihm eingerichtete AqBanking umsetzen, python-fints
eventuell später (E-152).

### Was erstellt bzw. geändert wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/aqbanking.md` | Plugin `aqbanking`: Voraussetzungen, Konfiguration, Konten aus der lokalen AqBanking-Konfiguration, Umsatzabbildung (wie FinTS/MT940, ohne Storno/Vormerkung), Fehlerzuordnung, PIN über Pipe, TAN-Bedarf als `BankTanNichtUnterstuetzt`, nur lesende Befehle, Einrichtungshinweise |
| `spec/api/python-api.md` 16, `plugins.md` 10, `openapi.yaml` 2.9.0 | Felder `aqbanking_verzeichnis`, `aqbanking_programme`, `aqbanking_timeout_sekunden`; `bank_plugin = "aqbanking"`; Fehlerklasse; `PluginInfo.name` um `aqbanking` erweitert |
| `spec/meilensteine.md`, `spec/konzept.md` (K 6) | M10, Reihenfolge M1–M4, M9, M5, **M10**, M6, M7, M8 |
| `spec/api/entscheidungen.md` | E-152 bis E-157 |
| `tests/hilfen/fints_attrappe.py` | näher am Protokoll (Bezugsnachricht in HNHBK, Bezugssegmente HISYN/HISPA/HITAN, keine leeren Datenelemente am Segmentende), sonst unverändert (E-157) |
| `tests/hilfen/aqbanking.py`, `tests/hilfen/m10.py` | AqBanking-Konfiguration je Test gegen die Attrappe, Hüllskripte zum Aufzeichnen der Aufrufe; Erwartungen aus der Generatorwahrheit |
| `tests/app/m10/` (Marker `m10`) | 46 Tests, davon 36 `kern` |
| `tests/app/test_paket.py` | Beispiel für ein ungültiges `bank_plugin` von `aqbanking` auf `hbci` (E-154) |
| `tests/spec/test_openapi.py` | `test_m10_schemas`; `test_m8_schemas` prüft die Version als Untergrenze |
| `tests/_selbstpruefung/` | Referenz `plugins/aqbanking.py`, `m10_config.py`, Fehlerklasse; 10 Mutanten `aq_*` |

### Erprobung von AqBanking (2026-11-09)

AqBanking 6.5.4 (`apt install aqbanking-tools`) gegen die FinTS-Attrappe:
Einrichtung mit `adduser`/`getsysid` und PIN über `-P /dev/fd/N`
funktioniert; im Profil `mt940` stimmen alle 91 Umsätze des Girokontos (drei
Seiten mit Aufsetzpunkt) nach der Abbildung aus `aqbanking.md` 4.2 mit der
MT940-Erwartung überein. Nicht abgebildet werden von AqBanking:
Storno-Kennzeichen, Kontowährung, zweiter Inhaber, camt.052.001.08. Der
Rückgabecode von `aqbanking-cli request` ist bei falscher PIN, Ablehnung,
HTTP 500, Verbindungsabbruch und TAN-Bedarf 0; maßgeblich sind die
Rückmeldungen und der Auftragsstatus auf stderr (`aqbanking.md` 5.2).
Ein nicht vertrautes TLS-Zertifikat lehnt AqBanking im nicht interaktiven
Modus ab, bevor etwas gesendet wird.

### Anzahl Tests

Gesamt **2 495** Tests (vorher 2 448), **1 348** `kern` (vorher 1 312).
Ohne AqBanking werden 24 der 46 M10-Tests übersprungen.

| Datei | Tests | davon `kern` |
| --- | ---: | ---: |
| `tests/app/m10/test_m10_config.py` | 16 | 11 |
| `tests/app/m10/test_m10_aqbanking_plugin.py` | 25 | 20 |
| `tests/app/m10/test_m10_aqbanking_sync.py` | 5 | 5 |

### Prüfungen

- `python -m pytest tests/generator tests/spec tests/attrappen`: 189 grün.
- `python -m pytest --collect-only -q`: 2 495 Tests, keine Sammelfehler.
- Selbstprüfung (`tests/_selbstpruefung/LETZTER_LAUF.md`): Referenz
  1 348/1 348 Kern-Tests grün, Erweiterungslauf der geänderten Bereiche
  grün, alle 10 M10-Mutanten und die FinTS-Mutanten von M6 erkannt.

### Hinweise für den Implementierungs-Thread

- `apt install aqbanking-tools` vor dem Testlauf; die Tests richten ihre
  AqBanking-Konfigurationen selbst ein.
- M10 hängt nur von M2 ab; `BankZugangGesperrt` (M6) wird ggf. mit M10
  angelegt.

## Meilenstein 11: Kontostand, Kategorien als Konten, Empfänger zusammenführen

Stand: 2026-11-09, Test-Thread. Auftrag des Anwenders (vier Wünsche, E-158):

1. Die Buchungsliste der Kategorien soll dieselben Funktionen bieten wie die der Konten.
2. Der Kontostand soll bei der Synchronisation mit abgerufen werden; bei Differenz gibt es eine Ausgleichsbuchung.
3. Kategorien erscheinen in der Finanzübersicht als Konten, abgesetzt und einklappbar.
4. Mehrere Empfänger lassen sich zusammenfassen; der neue Empfänger erhält alle Namen als Suchtexte.

### Bewertung

- **(1) übernommen.** Bisher stand dazu nur ein Satz (`oberflaeche.md` 7.2). Jetzt vollständig geregelt
  (`oberflaeche.md` 22.2): alle Funktionen der Kontoansicht, zusätzlich Spalte „Konto“ (das Bestandskonto der
  Buchung), Filter nach Bestandskonto und ein neuer REST-Filter `unterkonten`, damit eine Oberkategorie mit ihren
  Unterkategorien und vorzeichenrichtigen Beträgen angezeigt werden kann (E-163).
- **(2) übernommen, mit Leitplanken.** Der Saldo kommt mit dem Umsatzabruf (kein zweiter Bankdialog, keine
  zweite TAN/PIN): Attribut `saldo` der neuen `Umsatzliste` (E-159). Bei Differenz bucht der Lauf eine
  Ausgleichsbuchung gegen „Korrekturen“ (Status `importiert`, eigene Änderung im Protokoll, Benachrichtigung,
  abschaltbar; E-160). Grenzen (E-161, `kontostand.md` 3): Der erste Lauf bucht den fehlenden Anfangsbestand;
  wer danach alte Historie importiert, zählt doppelt; eigene Buchungen vor der Bank erzeugen Ausgleich und
  Gegenausgleich. **AqBanking:** Es lehnt den ganzen Auftrag ab, wenn die Bank keine Saldenabfrage anbietet
  (erprobt mit AqBanking 6.5.4); deshalb dort nur mit `KONTOR_AQBANKING_SALDO=1` (E-166).
- **(3) übernommen.** Keine REST-Änderung nötig; Bereich unter den Bestandskonten, anfangs eingeklappt, Zustand
  im Browser gespeichert, Gruppen Ausgaben/Einnahmen/Sonstige (E-164).
- **(4) bestand schon** seit M3 (`buchhaltungspflege.md` 2.4: Namen und Aliase der Quellen werden Aliase des Ziels
  und greifen bei Synchronisation und Import). Ergänzt: neuer Name beim Zusammenführen (alter Name wird Alias)
  und ein festgelegter Ablauf in der Oberfläche mit Vorschau der Suchtexte. Bewusst **keine** Teilwort-Suche,
  weil sie Empfänger still falsch zuordnen würde (E-165).

### Was erstellt bzw. geändert wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/kontostand.md` (neu) | `BankSaldo`, `Umsatzliste`, Mock-Schlüssel `bank.anfangssalden`, FinTS `HKSAL`, AqBanking `--balance`, Abgleich, Ausgleichsbuchung, `SyncKonto.saldo_abgleich`, Protokoll, Benachrichtigung, Grenzen |
| `spec/api/oberflaeche.md` 22 | Kategorien in der Übersicht, Buchungsliste einer Kategorie, Empfänger-Dialog, Kontostand auf `/sync` |
| `spec/api/datenmodell.md` 16, `buchhaltungspflege.md` 10 | Filter `unterkonten`; Zusammenführen mit `name` |
| `spec/api/python-api.md` 17, `plugins.md` 11, `fints.md`, `aqbanking.md`, `synchronisation.md` 19, `protokoll.md` 4.2 | Konfiguration `sync_saldo_angleichen`, `aqbanking_saldo`; Verweise; Attrappe mit `saldo_anbieten` |
| `spec/api/openapi.yaml` 2.10.0 | `SaldoAbgleich`, `saldo_ausgeglichen`, `unterkonten`, `name`, 409 beim Zusammenführen |
| `spec/api/entscheidungen.md` | E-158 bis E-166 |
| `spec/meilensteine.md` | M11 |
| `tests/hilfen/fints_attrappe.py` | `HISALS`/`HKSAL` (Versionen 5 und 7) nur mit `saldo_anbieten`, `saldo_versatz`, `saldo_fehler_iban` |
| `tests/hilfen/m11.py`, `tests/hilfen/browser_fixtures.py` | Hilfen; Browser-Fixtures aus `tests/app/m8/conftest.py` nach `tests/app/conftest.py` verlegt (sonst startete Playwright bei M8 und M11 im selben Prozess zweimal) |
| `tests/app/m11/` (Marker `m11`) | 45 Tests, davon 25 `kern` (Mock, FinTS, AqBanking, REST, Browser) |
| `tests/spec/test_openapi.py` | `test_m11_schemas`; M6/M10-Tests prüfen Version und Aufzählung als Untergrenze bzw. Präfix (E-162) |
| `tests/_selbstpruefung/` | Referenz (`m2.py`, `buch.py`, `m3.py`, `config.py`, `m10_config.py`, `plugins/`, `oberflaeche/app.js`), 15 neue Mutanten; FinTS-Referenz schaltet das Protokoll von `fints.connection` bei jedem Dialog erneut ab (uvicorn schaltet es sonst wieder ein) |

Gesammelte Testfälle insgesamt: **2541**, davon **1373** `kern`. Frühere Tests sind unverändert (E-029), außer den
Spezifikationstests (E-162) und der Verlagerung der Browser-Fixtures.

### Hinweis für die Implementierung

- Saldo: `umsaetze()` liefert eine `Umsatzliste`; keine neue öffentliche Plugin-Methode (die Tests aus M1, M6
  und M10 legen die Methodenmenge exakt fest).
- AqBanking: Saldo nur mit `aqbanking_saldo`; bei lokaler Ablehnung ein zweiter `request` ohne `--balance`.
- Oberfläche: neue `data-testid` in `oberflaeche.md` 22; die Kontoansicht trägt `data-kontoklasse`.

### Selbstprüfung

Protokoll: `tests/_selbstpruefung/LETZTER_LAUF.md`. Die Referenz besteht alle **1373/1373** Kern-Tests, auch mit
Zusatzfeldern (E-124). Erkannt wurden alle **15** neuen M11-Mutanten und alle **59** erneut geprüften Mutanten der
geänderten Bereiche (M1-Liste, M2-Synchronisation, M3-Zusammenführen/Rückgängig, M6-FinTS, M8-Oberfläche,
M10-AqBanking). Zwei Schwächen wurden dabei gefunden und behoben: Die Browser-Fixtures starteten Playwright im
selben Prozess zweimal, wenn M8- und M11-Tests zusammen liefen. Und `logging.config.dictConfig` (uvicorn) schaltete
den in der FinTS-Referenz stummgeschalteten Logger wieder ein. Den zweiten Fall prüft schon
`test_keine_geheimnisse_in_protokollen`; die Implementierung muss den Logger bei jedem Dialog stummschalten,
nicht nur beim Import.

### Nicht Erreichbares

Nichts. `aqbanking-tools` wurde in der Umgebung nachinstalliert (`apt-get install aqbanking-tools`, 6.5.4).

## Meilenstein 12: Statusänderung, Bearbeiten, Massenänderungen, Filterleiste

Stand: 2026-11-09, Test-Thread. Auftrag des Anwenders (E-167):

1. Der Status einer Buchung lässt sich nicht ändern.
2. Jeder Bestandteil einer Buchung muss bearbeitbar sein.
3. Wo sinnvoll, sind Massenänderungen möglich zu machen.
4. Das Filterpanel im Kontobuch muss einklappbar sein, standardmäßig eingeklappt.

### Bewertung

- **(1) übernommen.** Über REST ging der Status nur entlang der festen Übergänge (`PATCH`), in der Oberfläche gar
  nicht. Neu: `POST /api/buchungen/mehrfach/aendern` setzt jeden Status aus jedem Status (E-168). `PATCH` bleibt
  unverändert, damit die M1-Tests gültig bleiben. Das Verlassen von „abgeglichen“ verlangt `entsperren: true`
  (sonst 409 `bestaetigung_erforderlich`), die Oberfläche fragt vorher nach (E-169, T 13).
- **(2) übernommen.** Über REST war schon alles änderbar (`PATCH`, `PUT …/splits`, `PUT …/kategorie`); es fehlte
  die Oberfläche. Neu inline bearbeitbar: Status, Empfänger und Betrag (bei genau zwei Splits; sonst der
  Split-Dialog) (E-171). Gesperrte Buchungen bleiben gegen versehentliche Änderung geschützt: Erst den Status
  ändern bzw. die Abstimmung aufheben, dann ist alles bearbeitbar.
- **(3) übernommen.** Massenänderung für Status, Datum, Empfänger und Verwendungszweck, beliebig kombiniert,
  atomar, eine Änderung `mehrfach_aendern` im Protokoll, in einem Schritt rückgängig (E-170). Kategorie und Tags
  gab es schon. Bewusst nicht für Betrag, Splits und Konto (je Buchung verschieden).
- **(4) übernommen.** Die Filterleiste war schon einklappbar, auf dem Desktop aber anfangs offen. Jetzt beginnt
  jede Kontoansicht eingeklappt (Desktop und mobil, Zustand nicht gespeichert); die Zahl aktiver Filter steht am
  Umschalter (E-172).

### Was erstellt bzw. geändert wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/datenmodell.md` 17 | bearbeitbare Bestandteile, `mehrfach/aendern` (Prüfreihenfolge, Wirkung, Protokoll), Sperren im Überblick |
| `spec/api/oberflaeche.md` 23 (7.1 angepasst) | Filterleiste, Inline-Bearbeitung von Status/Empfänger/Betrag, `mehrfach-status`, `mehrfach-bearbeiten`, `km-status`, `km-mehrfach`, Status-Auswahl, Bearbeiten-Dialog |
| `spec/api/openapi.yaml` 2.11.0 | Pfad `POST /api/buchungen/mehrfach/aendern`, Schema `MehrfachAenderung` |
| `spec/api/protokoll.md` 4.1, `buchhaltungspflege.md` 5.4 | Aktion `mehrfach_aendern`; Sperrtabelle |
| `spec/api/entscheidungen.md` | E-167 bis E-174 |
| `spec/meilensteine.md` | M12 (Übersicht auch um M11 ergänzt) |
| `tests/app/m12/` (Marker `m12`) | 73 Tests, davon 50 `kern`: REST 55 (43 `kern`), Oberfläche 18 (7 `kern`) |
| `tests/spec/test_openapi.py` | `test_m12_schemas`; `test_m11_schemas` prüft die Version als Untergrenze (E-173) |
| `tests/hilfen/m8.py`, `tests/app/m8/test_m8_kontoansicht.py`, `tests/app/m11/test_m11_oberflaeche.py` | Hilfe `filter_aufklappen`; vier frühere Oberflächentests klappen die Leiste vor der Bedienung auf (E-174), Erwartungen unverändert |
| `tests/_selbstpruefung/` | Referenz (`buch.py`, `app.py`, `m3.py`, `oberflaeche/app.js`), 10 neue Mutanten |

Gesammelte Testfälle insgesamt: **2615**, davon **1423** `kern`.

### Hinweise für die Implementierung

- `PATCH /api/buchungen/{id}` nicht ändern; freie Statuswechsel nur über `mehrfach/aendern`.
- Sperrprüfung nur bei tatsächlicher Änderung (E-026); `entsperren` hebt nur die Statussperre auf, nie die der
  übrigen Felder.
- Das Setzen von `bestaetigt`/`abgeglichen` bestätigt einen offenen Vorschlag wie `PATCH`.
- Oberfläche: `km-status` und `km-mehrfach` stehen vor `km-loeschen` (ein M8-Test erwartet „Löschen…“ als letzten
  Eintrag). Die Mehrfach-Leiste darf beim Erscheinen die Liste nicht verschieben, sonst trifft der zweite Klick
  eines Doppelklicks eine andere Zeile (in der Referenz beobachtet).

### Selbstprüfung

Protokoll: `tests/_selbstpruefung/LETZTER_LAUF.md`. Die Referenz besteht alle **1400** ausführbaren Kern-Tests
(23 übersprungen, weil `aqbanking-tools` in dieser Umgebung fehlt), auch mit Zusatzfeldern (E-124). Erkannt wurden
alle **10** neuen M12-Mutanten und alle **16** erneut geprüften Mutanten der berührten Bereiche (M1-Mehrfach-
bearbeitung, M3-Protokoll, M8- und M11-Oberfläche). Die nicht-`kern`-Oberflächentests für Empfänger, Betrag und
Bearbeiten-Dialog setzt die kleine Referenz nicht um; sie sind nur gesammelt, nicht ausgeführt.

### Nicht Erreichbares

`aqbanking-tools` ist in dieser Umgebung nicht installiert; die AqBanking-Tests aus M10/M11 wurden deshalb
übersprungen. M12 berührt AqBanking nicht.

## Schnelllauf und Volllauf (E-175)

Stand: 2026-11-10, Test-Thread. Anlass: Ein vollständiger Lauf dauerte auf
dem Laptop des Anwenders über zehn Minuten.

- **Befund (gegen die Wegwerf-Referenz gemessen):** 2 615 Fälle. Rund 25
  Hypothesis- und Orakeltests verbrauchen etwa 40 % der Zeit; Leistungs-,
  Browser- und `langsam`-Tests (zusammen 363 Fälle) liefen bisher in jedem Lauf
  mit; jeder App-Test baut eine eigene App auf (≈ 0,13 s gegen die Referenz).
- **Änderung:** `python -m pytest` ist ein Schnelllauf (2 252 Fälle, ohne
  `leistung`, `browser`, `langsam`, Hypothesis-Profil `schnell`). Volllauf
  mit `--voll` oder `KONTOR_TESTS_VOLL=1`; jeder `-m`-Ausdruck und jede
  Knoten-ID wählen selbst aus. Parallel mit `-n auto` (pytest-xdist).
  Abnahme eines Meilensteins nur mit dem Volllauf (`spec/meilensteine.md`).
  Kein Test wurde geändert.
- **Messung:** 1 228 Kern-Tests (ohne Browser, Leistung, `langsam`) mit
  Profil `schnell` und `-n 2`: grün in 3:53 min; mit Profil `standard`
  nacheinander gut 13 min.
- **Prüfungen:** `python -m pytest --voll tests/generator tests/spec`
  179 grün; `--voll --collect-only` 2 615 Fälle ohne Sammelfehler;
  Selbstprüfung `--nur-referenz`: 1 400 Kern-Tests grün, auch mit
  Zusatzfeldern (E-124). Die Selbstprüfung ruft `-m kern` selbst auf und ist
  von der Änderung nicht betroffen; Kern-Tests sind unverändert, der
  Mutantenlauf vom 2026-11-09 (26/26 erkannt, `LETZTER_LAUF.md`) gilt weiter.
- **Offen (eigener Auftrag):** Rückgängig-Zufallsfolgen in M3 und M4
  zusammenlegen, REST-Fälle des Tilgungsplans (M5) auf Stichproben
  reduzieren, feste Wartezeiten (M2 Planer, M7 Anmeldebremse und Betrieb)
  durch eine einstellbare Uhr ersetzen.

## Meilenstein 13: Versionsnummer, Release und About-Fenster

Stand: 2026-11-10, Test-Thread. Grundlage: die vom Auftraggeber freigegebene
Meilenstein-Definition M13 (bereits als `v0.01` veröffentlicht), E-176.

### Was erstellt bzw. geändert wurde

| Pfad | Inhalt |
| --- | --- |
| `spec/api/version.md` (neu) | Versionsschema 1.1 mit regulärem Ausdruck, Hochzählen, Startwert, eine Quelle überall gleich, PEP 440; Release (nicht getestet, 2.4); `GET /api/version`; Abgrenzung |
| `spec/api/oberflaeche.md` 24 | `version-knopf` (Navigation, Hülle), `ueber-dialog`, Bedienung, Fehlerfall |
| `spec/api/openapi.yaml` 2.12.0 | Pfad `GET /api/version`, Schema `Versionsangaben`; bestehende Schemas unverändert (nur Beschreibung an `Status.version`) |
| `spec/api/python-api.md` 1, `sicherung.md` 3.2 | Schema von `kontor.__version__` bzw. `app_version` |
| `spec/api/entscheidungen.md` | E-176 bis E-180 |
| `spec/meilensteine.md` | M13 (Übersicht und Abschnitt) |
| `tests/app/m13/` (Marker `m13`) | 40 Tests, alle `kern`: `test_m13_version.py` 23 (REST/Python), `test_m13_oberflaeche.py` 17 (Browser) |
| `tests/hilfen/m13.py` | Versionsmuster, Prüfhilfen, Leser der Hülle |
| `tests/spec/test_openapi.py` | `test_m13_schemas`, `test_m13_versionsschema` (27 Fälle); `test_m12_schemas` prüft die Version als Untergrenze |
| `tests/conftest.py`, `pytest.ini`, `CLAUDE.md`, `TESTS_AUSFUEHREN.md` | Marker `m13`, Übersicht |
| `tests/_selbstpruefung/` | Referenz (`m13.py`, `__init__.py` Version `0.07`, Hülle in `m8.py`, `oberflaeche/app.js`), 10 neue Mutanten |

Gesammelte Testfälle insgesamt: **2683**, davon **1463** `kern`.

### Hinweise für die Implementierung

- Keine Versionsnummer ist in den Tests eingetragen; geprüft werden Schema 1.1 (`fullmatch`) und Gleichheit über
  Paket, `/api/status`, `/api/gesundheit`, `/api/version`, Hülle (`version-knopf` als `<button>`) und `app_version`.
- `datenbank` ist absolut, auch bei relativ konfiguriertem Pfad (Vergleich nach `Path.resolve()`); `python` ist
  `platform.python_version()`; `commit` in Kleinbuchstaben.
- Die Oberfläche lädt `GET /api/version` bei jedem Öffnen des Dialogs (E-179); die Tests ersetzen die Antwort
  im Browser für beide Build-Zweige und den Fehlerfall (E-180).
- Mobil geht der Fokus nach dem Schließen auf `menue-knopf`, das Menü bleibt zu.

### Selbstprüfung

Protokoll: `tests/_selbstpruefung/LETZTER_LAUF.md`. Die Referenz besteht alle **1463** Kern-Tests (keiner
übersprungen), auch mit Zusatzfeldern (E-124). Erkannt wurden alle **10** neuen M13-Mutanten und alle **13**
erneut geprüften Mutanten der berührten Bereiche (M8-Oberfläche und Hülle, M7 öffentliche Pfade, M12
Oberfläche). Zusätzlich liefen die M13-Tests gegen die Referenz im Anmeldelauf (`KONTOR_TESTS_ANMELDUNG=1`)
grün.

### Prüfungen

`python -m pytest --voll tests/generator tests/spec`: 207 grün; `--voll --collect-only`: 2683 Fälle ohne
Sammelfehler.

## Meilenstein 15: Sammelpaket Bedienung

Stand: 2026-11-11, Test-Thread. Grundlage: freigegebene Meilenstein-Definition vom 2026-11-10 (E-181);
M14 (`update`) bleibt frei.

- **Spezifikation:** `protokoll.md` 4.1, 6.2a, 14; `datenmodell.md` 18; `synchronisation.md` 20;
  `python-api.md` 18; `betrieb.md` 3; `oberflaeche.md` 25 (Hinweise in 7.5, 13.9); `openapi.yaml`
  2.13.0; `meilensteine.md` M15; E-181 bis E-191. `tests/spec`: neuer `test_m15_schemas`, exakte
  Versionsprüfung von `test_m13_schemas` dorthin verschoben; zwei Aufzählungsprüfungen gelockert (E-189).
- **Tests:** `tests/app/m15/` (Marker `m15`, Hilfen `tests/hilfen/m15.py`): 78 Fälle, davon 18
  `browser` und 55 `kern` (REST und Konfiguration, E-188).
- **Selbstprüfung:** Referenz um `m15.py`, `bis_id` (`m3.py`), Überspringen (`m2.py`), Konfiguration und
  `kontor.env` erweitert; 9 neue Mutanten `m15_*`, alle erkannt; Referenz und Erweiterungslauf grün
  (`tests/_selbstpruefung/LETZTER_LAUF.md`, einmaliger nicht reproduzierbarer Ausreißer dort vermerkt).
- **Lauf gegen die installierte Anwendung** (`python -m pytest -m m15 --voll -n 2`): 75 bestanden,
  3 fehlgeschlagen – nach Prüfung gegen Definition und Spezifikation weicht jeweils die Anwendung ab:
  1. `test_ohne_nettowirkung_bereits_rueckgaengig` und `test_zufaellige_folgen`: Ein „bis“, dessen
     zurückgenommene Änderungen sich aufheben (z. B. zweimal bis zur selben Änderung), antwortet 200 mit
     einer Änderung ohne Einträge; das verletzt `Aenderung.eintraege` (`minItems: 1`, `protokoll.md` 3.1)
     und die Grundregel 4. Erwartet: 409 `bereits_rueckgaengig` ohne Änderung (Definition 1 „Ist nichts
     zurückzunehmen“, `protokoll.md` 6.2a Nr. 4, E-190).
  2. `test_zuordnung_nach_lauf_und_folgelauf`: Im zweiten Zuordnungsdialog einer Reihe bietet
     `zuordnung-konto` noch das Konto an, dem im ersten Dialog eben die IBAN zugeordnet wurde; die
     Definition (4.4) verlangt „Bestandskonten ohne IBAN“ (`oberflaeche.md` 25.4). Alle übrigen
     Prüfungen dieses Tests (PATCH/POST-Körper, Folgelauf, Esc) bestehen.
- **Abschlussprüfungen:** `python -m pytest --voll tests/generator tests/spec` grün (208);
  `python -m pytest --voll --collect-only -q` ohne Sammelfehler (2762 Fälle).

## Meilenstein 17: Tabs der Ansichten und Gehe zur Gegenbuchung

Stand: 2026-11-11, Test-Thread. Grundlage: freigegebene Meilenstein-Definition vom 2026-11-11 (Feature
`tabs-gegenbuchung`). Die Definition nennt sich „M16“; die Nummer war am selben Tag schon an
`wiederkehrend-begruendung` vergeben (E-192), daher Übernahme als M17 (E-199). M14 (`update`) bleibt frei.

- **Spezifikation:** `oberflaeche.md` 27 (Hinweis in 8.2); `meilensteine.md` M17; E-199 bis E-202.
  `openapi.yaml` unverändert (2.14.0); kein Protokoll-, Sicherungs- oder Konfigurationsanteil.
- **Tests:** `tests/app/m17/` (Marker `m17`, Hilfen `tests/hilfen/m17.py`): 35 Fälle, alle `browser`, keine
  `kern` (E-202) – `test_m17_tabs.py` 22, `test_m17_gegenbuchung.py` 13.
- **Selbstprüfung:** nicht berührt; M17 hat keine Kern-Tests, keine Referenzteile und keine Mutanten (E-202).
- **Lauf gegen die installierte Anwendung** (`python -m pytest -p no:cacheprovider -m m17 -n 4 tests/app/m17`,
  mehrfach, auch mit `KONTOR_TESTS_ANMELDUNG=1`): 34 bestanden, 1 fehlgeschlagen –
  `test_ungueltiger_oder_fehlender_speicher[nicht_verfuegbar]`: Wirft schon der Zugriff auf
  `window.localStorage` (wie in Chromium bei gesperrtem Website-Speicher), wirft die Seite einen unbehandelten
  Fehler und wird nie bereit (`app` bleibt `data-bereit="nein"`). Erwartet nach Definition 1.6: Start ohne
  gespeicherte Tabs, sonst unverändert. Von außen ist nicht unterscheidbar, ob Tabs oder Layout/Design den Fehler
  auslösen; sind nur die Schlüssel außer `kontor.layout`/`kontor.thema` gesperrt (`nur_tabs_gesperrt`), besteht
  der Test.
- **Hinweis zu den Tests:** Strg-/Umschaltklick auf `tab-titel` wird über `defaultPrevented` geprüft, weil
  headless Chromium das neue Fenster im Probelauf nicht zuverlässig öffnete (E-201 Nr. 6).
- **Abschlussprüfungen:** `python -m pytest --voll tests/generator tests/spec` grün (209);
  `python -m pytest --voll --collect-only -q` ohne Sammelfehler (2851 Fälle).

## Meilenstein 16: Wiederkehrende Buchungen – robustere Kette mit Begründung

Stand: 2026-11-11, Test-Thread. Grundlage: freigegebene Meilenstein-Definition M16 vom 2026-11-11
(E-192). Kein Anwendungscode gelesen.

### Was erstellt bzw. geändert wurde

- Spezifikation: `wiederkehrend.md` 2.2 (neue Kette, ersetzt die alte Regel) und 8 (Begründung je
  Buchung), `oberflaeche.md` 13.5 und 26, `openapi.yaml` 2.14.0 (Pfad
  `GET /api/buchungen/{buchung_id}/wiederkehrend`, Schemas `WiederkehrendBegruendung`,
  `BegruendungEintrag`, `BegruendungRhythmus`, `BegruendungSchritt`, `BegruendungVerweis`,
  `BegruendungKonto`), `meilensteine.md` M16, E-192 bis E-198 und E-203, `CLAUDE.md`, `TESTS_AUSFUEHREN.md`.
  `tests/spec`: neuer `test_m16_schemas`, exakte Versionsprüfung von `test_m15_schemas` dorthin verschoben.
- Tests `tests/app/m16/` (Marker `m16`): 53 Testfälle, davon 52 `kern` –
  `test_m16_kette.py` (17), `test_m16_begruendung.py` (17), `test_m16_oberflaeche.py` (19, Playwright).
  Hilfen `tests/hilfen/m16.py` (Erwartung der Begründung, Vergleich ohne Texte); unabhängige Referenz
  der Kette in `tests/hilfen/wiederkehrend_orakel.py` (`kette`, `serie_mit_rhythmen`).
- M5 (E-194): `test_doppelte_zahlung_unterbricht_die_kette` ersetzt durch
  `test_doppelte_zahlung_am_termin_ist_zusaetzlich` (Serie mit drei Gliedern, Anker = jüngere Zahlung);
  das Orakel `wiederkehrend_orakel.serie` und die Selbstkontrolle des Generators (`_spec_kette`) nutzen
  die neue Kette. `python -m generator` erzeugt unveränderte Fixtures; alle übrigen M5-Erwartungen sind
  unter beiden Regeln gleich.

### Hinweise für die Implementierung

- Erwartungen stammen aus drei unabhängig geschriebenen Fassungen der Kette (Tests, Generator,
  Selbstprüfung), die für alle Fälle übereinstimmen. Auslegungen der Definition: E-193 (u. a.
  zusätzliche Zahlungen auch beim Bruch `fremde_zahlung`, alle übrigen Anker-Kandidaten sind
  zusätzlich), E-195 (Felder immer vorhanden, `uebersprungen` ohne Reihenfolge, `ausgeschlossen`),
  E-196/E-203 (Oberfläche; Hinweis bei ausgefiltertem Sprungziel als Meldung `data-art="hinweis"`).
- Sprungziel-Tests nutzen 230 Buchungen und die Parameter `unterkonten=true` bzw. `von=…`.

### Selbstprüfung

`python -m tests._selbstpruefung --mutant m16_*` (22 neue Mutanten): Referenz grün (1547 passed,
23 skipped), Erweiterungslauf mit Zusatzfeldern grün, jeder Mutant rot – Gesamtergebnis BESTANDEN
(`tests/_selbstpruefung/LETZTER_LAUF.md`).

### Nicht Erreichbares

- `aqbanking-tools` fehlt in dieser Umgebung; die AqBanking-Kern-Tests (M10) wurden in der
  Selbstprüfung übersprungen (23 skipped). Für M16 ohne Bedeutung.
- Die Abnahmetests wurden nicht gegen kontor-app ausgeführt (Rollentrennung).


## Widerspruch W-010: Abstimmungsdialog schwankend (E-205)

- `tests/app/m8/test_m8_seiten.py::test_konten_anlegen_und_abstimmen` wartet nach dem Speichern der
  Abstimmung mit `expect(...).to_be_hidden()` auf das Schließen von `abstimmung-dialog`, statt es
  einmalig sofort zu prüfen; die Aussage bleibt gleich (`oberflaeche.md` 9, 13.3).
- Durchsicht von `tests/app/m8/`: keine weiteren Sofortprüfungen eines Oberflächenzustands direkt
  nach `m8.warte_bis(...)`.
- Der Test ist nicht `kern`; die Selbstprüfung ist davon nicht betroffen und wurde nicht ausgeführt.

## Meilensteine 18 bis 22 (Auftrag 2026-11-13)

Stand: 2026-11-13, Test-Thread. Grundlage: die am 2026-11-13 freigegebenen
Definitionen M18 (Dokumente), M19 (ALF-BanCo-Import, überarbeitete Fassung),
M20 (Mail-Abgleich), M21 (Berichte, Sprungziel) und M22 (Spaltenbreiten,
Markierung). M14 bleibt an `update` vergeben.

### Übernahme

| Meilenstein | Spezifikation | Entscheidungen | `openapi.yaml` |
| --- | --- | --- | --- |
| M18 | `dokumente.md`, `oberflaeche.md` 28, `protokoll.md` 15, `sicherung.md` 2.7, `datenmodell.md` 7, `sicherheit.md` 8 | E-206–E-210 | 2.15.0 |
| M19 | `alfbanco.md`, `oberflaeche.md` 29, `protokoll.md` 16, `python-api.md` 19 | E-211–E-215 | 2.16.0 |
| M20 | `erwartungen.md`, `oberflaeche.md` 30, `protokoll.md` 17, `python-api.md` 20, `betrieb.md` 3, `benachrichtigungen.md` 9, `sicherung.md` 2.8 | E-216–E-220 | 2.17.0 |
| M21 | `oberflaeche.md` 31 (Hinweis in 26.4) | E-221, E-222 | unverändert |
| M22 | `oberflaeche.md` 32 | E-223, E-224 | unverändert |

Dazu E-225 (Selbstprüfung), E-226 (W-011) und E-227 (W-012).

### Tests

| Meilenstein | Verzeichnis | kern | Browser |
| --- | --- | ---: | ---: |
| M18 | `tests/app/m18/` | 94 | 8 |
| M19 | `tests/app/m19/` | 106 | 5 |
| M20 | `tests/app/m20/` | 81 | 6 |
| M21 | `tests/app/m21/` | 0 | 9 |
| M22 | `tests/app/m22/` | 0 | 13 |

Testdateien (PDF, PNG, JPEG-/WebP-Köpfe, Mails, QIF, Mock-Datendateien) werden
in den Tests bzw. Hilfen erzeugt; der Generator und `fixtures/` sind
unverändert.

### Lauf gegen den Feature-Stand

`python -m pytest --voll -m "m18 or m19 or m20 or m21 or m22"` am 2026-11-13
(der Feature-Stand wurde während des Auftrags mehrfach aktualisiert):
nach den Korrekturen W-011 und W-012 alle 322 Tests grün; ebenso der
Anmeldelauf (`KONTOR_TESTS_ANMELDUNG=1`) und der Erweiterungslauf
(`KONTOR_TESTS_ZUSATZFELDER=1`) der Kern-Tests. Frühere Zwischenstände
zeigten Abweichungen, die nach der Definition als Fehler der Anwendung
gewertet wurden (u. a. `schluessel` in Protokollformen der Erwartung,
fehlendes `private` in `Cache-Control`, unbekannte Query-Parameter
angenommen, Dokument blieb nach Lösen in `dokument_ids`); sie sind im
letzten Lauf behoben.

### Selbstprüfung

Die Kern-Tests von M18–M20 haben keine Referenz und werden ausgelassen
(E-225); M21/M22 haben keine Kern-Tests. Referenzlauf und Erweiterungslauf
siehe `tests/_selbstpruefung/LETZTER_LAUF.md`: beide grün (1570 Kern-Tests), BESTANDEN.

## Meilensteine 23 bis 25 (Auftrag 2026-11-13)

Stand: 2026-11-13, Test-Thread. Grundlage: die am 2026-11-13 freigegebenen
Definitionen M23 (Geheimnisse mit dem Login-Passwort geschützt, gemerkte PIN,
Gmail mit App-Passwort), M24 (Mail-Abgleich: Serien, Kachel, Kategorie bei
Erstattungen, Mock-Mails) und M25 (Betragsfilter für wiederkehrende
Buchungen). M14 bleibt an `update` vergeben.

### Übernahme

| Meilenstein | Spezifikation | Entscheidungen | `openapi.yaml` |
| --- | --- | --- | --- |
| M23 | `geheimnisschutz.md`, `oberflaeche.md` 33, Hinweise in `geheimnisse.md` 4, `mail.md`, `sicherheit.md` 4.9, `synchronisation.md` 12, `betrieb.md` 4.1 (`LimitCORE`), `python-api.md` 14.2, `protokoll.md` 18, `sicherung.md` 2.6 | E-228–E-232 | 2.18.0 |
| M24 | `erwartungen.md` 13, `oberflaeche.md` 34, `protokoll.md` 19 | E-233–E-237 | 2.19.0 |
| M25 | `wiederkehrend.md` 9, `oberflaeche.md` 35, `protokoll.md` 20, `sicherung.md` 10 | E-238–E-244 | 2.20.0 |

Dazu E-245 (M20-Test, Reihenfolge der Mails zweier Postfächer). Vertragsänderungen
ausdrücklich in E-228 (LOGIN nur für App-Passwort-Postfächer, neue Geheimnisnamen,
gemerkte PIN, `LimitCORE=0`) und E-238 (Vorgabe ±10 % ändert die Kette).

### Tests

| Meilenstein | Verzeichnis | kern | Browser | sonst |
| --- | --- | ---: | ---: | ---: |
| M23 | `tests/app/m23/` | 74 | 10 | – |
| M24 | `tests/app/m24/` | 31 | 6 | 1 (Mock-Datensatz, REST) |
| M25 | `tests/app/m25/` | 59 | 5 | – |

Dazu ein Attrappentest der IMAP-Attrappe in der neuen Betriebsart
App-Passwörter (`tests/attrappen`, E-230).

**Geänderte frühere Tests:** `tests/app/m16/conftest.py` (Vorgabe `aus` für jede
App), `tests/hilfen/m16.vergleichbar` (ohne die optionalen M25-Felder),
Schematests in `tests/spec/test_openapi.py` (Pflichtfelder bzw. Versions-Untergrenze)
– E-244; `tests/hilfen/m24.serien_orakel` mit Filtern (E-244 Nr. 4);
`test_idempotenz_und_zwei_postfaecher` (M20) – E-245.

### Lauf gegen den Feature-Stand

- Volllauf `python -m pytest --voll -n 2` der gesamten Suite am 2026-11-13:
  3 365 bestanden, 1 rot (`test_idempotenz_und_zwei_postfaecher`, M20, nicht
  deterministisch; Testfehler, korrigiert, E-245; danach dreimal grün).
- Anmeldelauf und Erweiterungslauf (`KONTOR_TESTS_ANMELDUNG=1`,
  `KONTOR_TESTS_ZUSATZFELDER=1`) für `m16 or m23 or m24 or m25` mit `--voll`:
  je 239 grün.
- Frühere Zwischenstände (der Feature-Stand wurde während des Auftrags
  aktualisiert) zeigten zwei Abweichungen, die nach der Definition Fehler der
  Anwendung waren und im letzten Lauf behoben sind: Serie nicht ausgelassen,
  wenn ihre letzte Buchung einer manuellen Erwartung zugeordnet ist (M24
  1.2), und „Speichern“ auf der Postfachseite blieb nach einem Fehler dauerhaft
  gesperrt (M23 8, E-231 Nr. 6).

### Selbstprüfung

M25 hat Referenzteile (`referenz/kontor/m25.py`) und elf Mutanten `m25_*`, alle
erkannt; M23 und M24 sind wie M18–M20 ausgelassen (E-243). Referenzlauf und
Erweiterungslauf grün (je 1 629 Kern-Tests), siehe
`tests/_selbstpruefung/LETZTER_LAUF.md`.

### Prüfungen vor dem Abschluss

`python -m pytest --voll tests/generator tests/spec`: 215 grün;
`--voll --collect-only`: 3 366 Fälle ohne Sammelfehler.

## Meilensteine 26 bis 28 (Auftrag 2026-11-16)

Stand: 2026-11-16, Test-Thread. Grundlage: freigegebene Definitionen M26
(UXMobile), M27 (REST aus `feature/sammel`) und M28 (Oberfläche aus
`feature/sammel`); bei Widersprüchen gilt M28 vor M27.

### Übernahme

- M26: `oberflaeche.md` 36, `sicherheit.md` 6 (`no-cache`, `ETag`, 304),
  E-246 bis E-248.
- M27: neue Datei `spec/api/sammel.md`, `mail.md` 6.6, `protokoll.md` 21,
  `sicherung.md` 11, `openapi.yaml` 2.21.0, E-249 bis E-251.
- M28: `oberflaeche.md` 37, E-252 bis E-255; Widersprüche W-013 und W-014 des
  Implementierungs-Threads: E-257 (beides Testfehler, korrigiert).

### Tests

| Meilenstein | Verzeichnis | Tests | davon `kern` | Browser |
| --- | --- | --- | --- | --- |
| M26 | `tests/app/m26/` | 26 | 3 | 23 |
| M27 | `tests/app/m27/` | 83 | 81 | – |
| M28 | `tests/app/m28/` | 48 | – | 41 |

**Geänderte frühere Tests:** sechs mobile Tests nach M26 9 (E-248); Person
in allen Browsertests zentral über `browser_fixtures.neue_seite` (E-253);
nach M28 13 Navigation, Palette, Alt-Ziffern, Routen, Stifte statt
Doppelklick, Verschieben mit Alt, Ausschnitt, Meldungen über Menüs, entfallene
Oberflächentests von M16, M24 und M25, M22-Zusatzmarke, M13-Navigation,
M17-Speichertest (E-253, E-254); Schematests in `tests/spec` (E-251).

### Lauf gegen den Feature-Stand (0.15, während des Auftrags aktualisiert)

- Volllauf in zwei Teilen am 2026-11-16: ohne Browser 3 070 grün; Browser
  424 grün, 1 rot: M18 `test_details_anhaengen_loesen_rueckgaengig` – eine
  Erfolgsmeldung liegt über dem Knopf `dokument-loesen-…` im (durch M28
  längeren) Panel Einzelheiten. Die Definition nennt diesen Test nicht; die
  Schichtung von Meldungen ist offen (M28 O3). Der Test bleibt unverändert und
  rot, bis der Auftraggeber entscheidet.
- Anmeldelauf und Erweiterungslauf für M26 (REST), M27 und M28 grün.
- In früheren Zwischenständen rot und im letzten Stand grün: ETag des
  Manifests (M26 8.1), Fokus der Befehlspalette beim Öffnen (M26 5.3),
  Seitenfehler bei Alt+8 (M28 2).

### Selbstprüfung

Referenz grün (1 611 Kern-Tests); Mutanten von M8, M12, M13, M16 sowie neu
`m26_*` und `m28_*` erkannt, siehe `tests/_selbstpruefung/LETZTER_LAUF.md`.
M27 ist ausgelassen (E-256), die Oberflächenmutanten von M16 sind mit ihren
Tests entfallen.

### Prüfungen vor dem Abschluss

`python -m pytest --voll tests/generator tests/spec`: 216 grün;
`--voll --collect-only`: 3 495 Fälle ohne Sammelfehler.

### Offene Punkte für den Auftraggeber

- M26 2.1 „eine Zeile“ ist mit dem Personenknopf aus M28 bei 390 px nicht
  erfüllbar (neun Knöpfe zu 44 px); nicht geprüft (E-247).
- M27 2: Tag und Status in **einer** Mehrfachänderung sind ohne
  Vertragsänderung nicht möglich (`MehrfachAenderung` kennt keine Tags);
  das Szenario nutzt `PATCH` (E-250).
- Benachrichtigungen wiederkehrender Buchungen (M5) verlinken weiter auf
  `/wiederkehrend`, das seit M28 404 liefert; von keiner Definition geregelt.
- Meldungen über Panels und Menüs (M28 O3), siehe den roten M18-Test.

## Meilenstein 29 (Auftrag 2026-11-22, Paket 1): Bankabruf über FinTS/camt und Bankzugang

Stand: 2026-11-22, Test-Thread. Grundlage: freigegebene Definition vom
2026-11-19 (`spec/definitionen/definition-1-fints-camt.md`, dort auch
`AUFTRAG.md` und `abnahme-stand-main.txt`). Entscheidungen E-258 bis E-267.
Die Tests sind **nicht** gegen die Anwendung gelaufen (Auftrag: kein
Anwendungscode, keine App-Tests gegen die installierte Anwendung).

### Was übernommen wurde

| Teil | Ort |
| --- | --- |
| Konfiguration ohne AqBanking, Bankzugang über REST, Diagnoseprotokoll, Übergang alter Kennungen, Sicherheit | `spec/api/bankzugang.md` (neu) |
| FinTS-Plugin: `tan_verfahren`, Kontenliste, camt-Version, Datumsformen, TAN bei der Anmeldung, Betriebsarten der Attrappe | `fints.md` 3, 3.0–3.5a, 6 |
| Lauf mit ausgewählten Konten, TAN bei der Anmeldung, Übergang | `synchronisation.md` 21 |
| Python-Schnittstelle, Naht `kontor.sync.kennungen_als_alt_markieren` | `python-api.md` 21, `plugins.md` 12 |
| REST | `openapi.yaml` 2.22.0 (Tag `bank`, sieben Operationen, neun Schemas) |
| Oberfläche | `oberflaeche.md` 38 |
| Plan | `meilensteine.md` (M10 entfallen, M29 neu) |

### Frühere Meilensteine (Definition 9)

- **M10 entfernt** (E-259): `spec/api/aqbanking.md`, `tests/app/m10/` (46 Fälle),
  `tests/hilfen/aqbanking.py`, `tests/hilfen/m10.py`, Marker `m10`,
  `test_m10_schemas`, Referenzteile und zehn Mutanten `aq_*`.
- **M11** (E-260): `test_m11_aqbanking_saldo.py` (5 Fälle), `kontostand.md` 1.3,
  Mutant `aq_saldo_noted` entfernt.
- **M6 und gemeinsamer Plugin-Test** (E-261): öffentliche Methoden des echten
  Bank-Plugins mit `tan_verfahren` (`test_m6_paket.py::test_oeffentliche_methoden`,
  `test_plugins.py::test_nur_lesende_oeffentliche_methoden`); `test_paket.py`
  prüft zusätzlich `bank_plugin="aqbanking"` als ungültig. Die übrigen M6-Tests
  bleiben unverändert, weil ihre Erwartungen mit den Generatordaten auch nach
  den neuen Regeln gelten (Begründung in E-261); Fixtures unverändert.

### Tests

| Datei | Fälle | davon `kern` | Browser |
| --- | ---: | ---: | ---: |
| `tests/app/m29/test_m29_config.py` | 13 | 13 | – |
| `tests/app/m29/test_m29_fints_plugin.py` | 63 | 63 | – |
| `tests/app/m29/test_m29_bankzugang_rest.py` | 73 | 73 | – |
| `tests/app/m29/test_m29_sync.py` | 11 | 11 | – |
| `tests/app/m29/test_m29_uebergang.py` | 14 | 14 | – |
| `tests/app/m29/test_m29_diagnose.py` | 11 | 11 | – |
| `tests/app/m29/test_m29_oberflaeche.py` | 15 | – | 15 |
| `tests/attrappen/test_attrappen.py` (Betriebsarten der Attrappe, Marker `m6`) | 12 | – | – |
| `tests/spec/test_openapi.py::test_m29_schemas` | 1 | – | – |

Neu: 214 Fälle (200 in `tests/app/m29/`, 12 Attrappentests, 1 Schematest, 1
Parameter in `test_paket.py`). Geändert: 3 frühere Tests (siehe oben) und
drei Schematests (`test_alle_operationen_vorhanden`, `test_m8_schemas`,
`test_m27_schemas`). Entfernt: 52 Fälle (46 M10, 5 M11, `test_m10_schemas`).
Gesamt `--voll --collect-only`: 3 657 (vorher 3 495).

Hilfen: `tests/hilfen/m29.py` (REST-Kurzformen, erwartete Kontenliste nach
`fints.md` 3.2, Mock-Datendateien für den Übergang, Verbotsliste des
Diagnoseprotokolls, `bankzugang_oeffnen`); `tests/hilfen/fints_attrappe.py`
mit den Betriebsarten aus Definition 10 (E-263), geprüft mit python-fints.

### Selbstprüfung

`python -m tests._selbstpruefung` mit den Mutanten der betroffenen Bereiche
(`tests/_selbstpruefung/LETZTER_LAUF.md`): Referenz grün (1 572 Kern-Tests),
Erweiterungslauf grün, 17 von 17 Mutanten erkannt. M29 ist ausgelassen
(`OHNE_REFERENZ`, E-266); die Referenz hat für die geänderten Kern-Tests
`FintsBankPlugin.tan_verfahren` und kein `aqbanking` mehr. Mit dem Endstand
zusätzlich: Kern-Tests von `test_paket.py`, `test_plugins.py`, `tests/app/m6`,
M11-Saldo und alle Attrappentests gegen die Referenz grün (284).

### Prüfungen vor dem Abschluss

`python -m pytest --voll tests/generator tests/spec`: 216 grün;
`--voll --collect-only`: 3 657 Fälle ohne Sammelfehler. Die Läufe wurden mit
einer Importsperre für das installierte Paket `kontor` ausgeführt
(`PYTHONPATH` auf ein Verzeichnis mit einem `kontor`, das `ImportError`
wirft), weil die Kopfzeile von pytest sonst die Anwendung importiert.

### Offene Punkte für den Auftraggeber bzw. den Implementierungs-Thread

1. **Neue Anforderung an die Anwendung (E-264):**
   `kontor.sync.kennungen_als_alt_markieren(config) -> None` als Naht für den
   Übergang alter Kennungen (Definition 10 überlässt den Weg dem Test-Thread).
   Ohne diese Funktion sind 13 der 14 Übergangstests rot.
2. **`tan_offen` (Definition 5.2)** ist als neuer Code übernommen; `POST
   /api/sync` verwendet für denselben Zustand weiter `tan_ausstehend`. Falls
   in der Definition `tan_ausstehend` gemeint war, bitte als Widerspruch
   melden.
3. **Zeitpunkt in camt:** Die Definition nennt nur die Form des Werts
   (`2024-06-03T10:11:12+02:00`), nicht das Element. Geprüft werden `<DtTm>`
   (ISO 20022) und ein Zeitpunkt in `<Dt>` (E-265).
4. **Übergang auch mit dem Mock-Plugin:** Definition 4.1 steht unter
   „Synchronisation“ ohne Einschränkung auf FinTS; die Einzelfälle laufen
   deshalb im Mock-Modus, ein Fall mit FinTS (MT940 → camt).
5. **`sync_laeuft`** an den Endpunkten des Bankzugangs ist nicht geprüft
   (nicht deterministisch herstellbar); die Reihenfolge der 409-Prüfungen
   untereinander ebenfalls nicht.
6. **Lauf ohne ausgewähltes Konto:** Status des Laufs ist nicht festgelegt;
   geprüft ist nur, dass kein Konto verarbeitet wird. **Lauf ohne gespeicherte
   Konten bei TAN zur Anmeldung:** Code nicht festgelegt („wie bisher“);
   geprüft sind Status `fehlgeschlagen`, keine TAN-Anforderung und das Wort
   „Einstellungen“ in der Meldung.
7. **Diagnoseprotokoll:** Beträge, die 160-Zeichen-Grenze und Steuerzeichen
   sind nicht prüfbar (E-267); der genaue Wortlaut der Zeilen ist frei. Die
   Tests verlangen wörtlich `Konto 1`, Segmentarten wie `HKCAZ`, das
   camt-Format, Rückmeldecodes, den Fehlercode (`bank_pin_falsch`) und die
   Form unlesbarer Werte (`99.99.9999`, andere Zeichen bleiben).
8. **Oberfläche:** `bankzugang` ist als `data-testid` des Abschnitts gelesen;
   der Abschnitt wird unter `/einstellungen` erwartet. Paket 3 (Einstellungen
   in Bereichen) muss nur `m29.bankzugang_oeffnen` anpassen. Der Hinweis auf
   die Vorbelegung und der Text der leeren Kontenliste haben kein genanntes
   Merkmal und sind nicht geprüft; nur Desktop.
9. `spec/konzept.md` und `spec/testkonzept.md` nennen AqBanking an einigen
   Stellen noch als ursprüngliche Planung (K 3, T 7); nur der Absatz zur
   FinTS-Bibliothek ist angepasst.

## Meilenstein 30 (Auftrag 2026-11-22, Paket 2): Kontor-Ausdrücke, Filter im Kontoblatt, Regeleditor, Regel-Tags

Stand: 2026-11-22, Test-Thread. Grundlage: Definition vom 2026-11-19 mit
Nachtrag 1 (`spec/definitionen/definition-2-ausdruecke-regeln.md`,
`definition-2-nachtrag.md`; Vermerk „Entwurf zur Freigabe“, übernommen auf
Auftrag, E-268). Entscheidungen E-268 bis E-276. Die Tests sind **nicht**
gegen die Anwendung gelaufen (Auftrag: kein Anwendungscode, keine App-Tests
gegen die installierte Anwendung); die neuen Tests sind deshalb ungeprüft
gegen eine Implementierung geschrieben.

### Was übernommen wurde

| Teil | Ort |
| --- | --- |
| Ausdruckssprache, Prüfen, Sprache abfragen, `als-regel`, Filter an Buchungsliste und Export | `spec/api/ausdruecke.md` (neu), `datenmodell.md` 19 |
| Regeln mit Ausdruck und Tags, Auswertung, Reihenfolge, Test, Erklären, einzelne Regel anwenden | `kategorisierung.md` 8 |
| Protokoll (Aktion `regeln_reihenfolge`, Protokollform der Regel), Sicherung `schemaversion` ≥ 9, Verweise beim Löschen und Zusammenführen | `protokoll.md` 22, `sicherung.md` 12, `loeschen.md` 8 |
| REST | `openapi.yaml` 2.23.0 (Tag `ausdruck`, sieben neue Operationen, 18 neue Schemas, `Regel` erweitert) |
| Oberfläche | `oberflaeche.md` 39 |
| Plan | `meilensteine.md` (M30) |

### Frühere Meilensteine (Definition 12, E-271)

- **REST (M2, M3, M9, M15, M19 …): keine Testerwartung geändert.** Die
  Erwartungen gelten weiter. Rot gegen die Anwendung waren diese Tests, weil
  das Schema `Regel` die neuen Felder verbot und weil die Protokollform der
  Regel nicht mehr die REST-Darstellung ist. Geändert sind das Schema (neue
  Felder optional, `kategorie_id` null erlaubt) und die Hilfen:
  `m3.regel_zustand` (in `m3.bestand`, damit in allen späteren
  `bestand`-Hilfen, in `m9.inhalt` und in den Rückgängig-Rundreisen),
  `m3.bezuege_ok`, `loeschen_orakel` (der übersetzte Ausdruck einer
  umgestellten Regel bleibt offen). Ein Test angepasst:
  `m3/test_m3_konto_loeschen.py::test_regeln_elternkonto_umgestellt` (Vergleich
  ohne `ausdruck`).
- **Oberfläche, Filter:** Hilfen `m8.filter_aufklappen` (jetzt
  `filter-baukasten-umschalten`), neu `m8.filter_ausdruck_setzen`,
  `filter_ausdruck_wert`, `filter_zuruecksetzen`, `filter_aktiv`,
  `m17.filter_status_setzen`/`filter_abfrage`. Angepasst:
  `m8/test_m8_kontoansicht.py` (`test_filter` mit 14 Fällen über alte
  Adressen, `test_filter_aus_der_url_und_status`, `test_ungueltige_betragseingabe`
  → `test_ungueltiger_filterausdruck`), `m12/test_m12_oberflaeche.py` (vier
  Filterleisten-Tests, fünf Fälle), `m17/test_m17_tabs.py` (sechs Tests),
  `m17/test_m17_gegenbuchung.py` (zwei), `m28/test_m28_kontoblatt.py`
  (`test_filter_untermenue` mit vier Fällen,
  `test_filter_leerer_zweck_und_ohne_empfaenger`,
  `test_kuerzel_aktionen_und_vortasten`: `f a` statt `f z`),
  `m26/test_m26_oberflaeche.py::test_erfassen_schwebend_und_titelzeile` (ohne
  die Zeile mit `filter-umschalten`). **Entfernt:**
  `m26::test_filterleiste_zweispaltig`. Die M11-Tests mit `filter-unterkonten`
  und `filter-konto` sind unverändert und erreichen die Leiste über die
  Hilfe (Annahme, siehe offene Punkte).

### Tests

| Datei | Fälle | davon `kern` | Browser |
| --- | ---: | ---: | ---: |
| `tests/app/m30/test_m30_ausdruck.py` | 205 | 205 | – |
| `tests/app/m30/test_m30_filter.py` | 126 | 126 | – |
| `tests/app/m30/test_m30_regeln.py` | 50 | 50 | – |
| `tests/app/m30/test_m30_protokoll.py` | 20 | 20 | – |
| `tests/app/m30/test_m30_oberflaeche.py` | 17 | – | 17 |
| `tests/spec/test_openapi.py::test_m30_schemas` | 1 | – | – |

Neu: 419 Fälle (418 in `tests/app/m30/`, 1 Schematest). Geändert: 20 frühere
Testfunktionen (37 Fälle, siehe oben) und zwei Schematests
(`test_alle_operationen_vorhanden`, `test_m29_schemas`). Entfernt: 1.
Gesamt `--voll --collect-only`: 4 075 (vorher 3 657).

Hilfe `tests/hilfen/m30.py`: kleiner synthetischer Buchbestand (zehn
Buchungen, eine Umbuchung, eine gesperrte) mit den Werten, die die Felder der
Sprache je Buchung haben; die Erwartung je Ausdruck ist eine Funktion des
Tests über diese Werte. Bezugstag immer `stichtag` 2026-11-16 (ein Montag,
Beispiele der Definition). Verweise offener Form normalisiert `m30.als_id`.

### Selbstprüfung

`python -m tests._selbstpruefung` mit den Mutanten der betroffenen Bereiche
(`tests/_selbstpruefung/LETZTER_LAUF.md`): Referenz grün (1 572 Kern-Tests),
Erweiterungslauf (E-124) grün, 7 von 7 Mutanten erkannt
(`regel_prioritaet_umgekehrt`, `regel_inaktiv_greift`, `regelbetrag_absolut`,
`loeschen_vorschlag_bleibt`, `sicherung_pruefsumme_ungeprueft`,
`protokoll_fehlt_mehrfach_tags`, `m12_filter_offen`). M30 ist ausgelassen
(`OHNE_REFERENZ`, E-275), kein neuer Mutant.

### Prüfungen vor dem Abschluss

`python -m pytest --voll tests/generator tests/spec`: 217 grün;
`--voll --collect-only`: 4 075 Fälle ohne Sammelfehler; `--ohne-app` über
`tests/app/m30` und die geänderten Browsertests ohne Sammel- oder
Importfehler. Alle Läufe mit der Importsperre für `kontor` (`PYTHONPATH` auf
`/home/claude/test-thread/sperre`).

### Offene Punkte für den Auftraggeber bzw. den Implementierungs-Thread

1. **Ungeprüft gegen die Anwendung:** Die 418 neuen Tests sind ohne Lauf
   gegen eine Implementierung geschrieben. Wo die Definition Formen offen
   lässt, sind mehrere zugelassen (E-272, E-274, E-276); stößt ein Test auf
   eine andere vertretbare Lesart, bitte als Widerspruch melden.
2. **`filter-unterkonten` und `filter-konto` (M11)** nennt die Definition
   nicht bei den ersetzten Einzelfeldern; angenommen ist, dass sie in
   `filter-leiste` bleiben und über `filter-baukasten-umschalten` erreichbar
   sind (E-274 Punkt 2).
3. **`automatisch` und `empfaenger_id`** an Regeln nennt Definition 5.1 „wie
   bisher“; kontor-tests kannte sie nicht. Sie sind im Schema nur zugelassen,
   ihre Bedeutung kommt mit Paket 3 (Lernmodell-Transparenz).
4. **Nicht prüfbar (E-273):** Umstellung der Datenbank beim Start und
   Einspielen von Sicherungen der Versionen 1 bis 8; geprüft sind nur
   `schemaversion` ≥ 9 und die Rundreise.
5. **Offene Formen:** Zählweise von `ende` in Fehlerstellen und
   `markierungen`, Feldname in `markierungen`, Form von `kategorie_vorher`,
   `kategorie_nachher`, `tags_neu`, `ergebnis` der Erklärung, 404 oder 422 bei
   unbekannter `buchung_id` im Erklären; `-1m`/`-1y` (Beginn am Tag genau eine
   Einheit zurück oder am Tag danach); Betrag und Kategorie einer Umbuchung
   ohne Konto (E-272).
6. **Wirkung bei Kombinationen** (gesperrt und zugleich Splitbuchung;
   abweichend und zugleich verdeckt) ordnet die Definition nicht; die Tests
   vermeiden sie.
7. **Oberfläche, nicht geprüft:** Fehlermeldungen mit Feld und Regel (39.6),
   `regel-anwenden-nichts`, `test-leer`/`test-alle`, Ziehen in der
   Regelliste, Vervollständigung, Hervorhebung, `regel-uebernehmen`,
   Duplizieren, die 50er-Grenze im Tag-Dialog, mobil (E-274, E-276).
   „Als Regel speichern…“ und „Bearbeiten“ haben keine Kennung und werden über
   Text bzw. Knopfnamen gefunden.
8. **Frühere Tests:** Viele rote M2/M3/M9-Tests der Liste
   `abnahme-stand-main.txt` sind mit unveränderter Erwartung belassen; sie
   sollten mit dem neuen Schema und `m3.regel_zustand` grün werden. Bleiben
   sie rot, liegt es an der Anwendung oder an einem anderen Paket.

## Meilenstein 31 (Auftrag 2026-11-22, Paket 3): übrige Features vor dem Sammelbranch

Stand: 2026-11-22, Test-Thread. Grundlage: Definition 3
(`spec/definitionen/definition-3-uebrige-features-vor-sammel3.md`), übernommen
ohne gesonderte Freigabe („direkt weiter“, E-277). Entscheidungen E-277 bis
E-292. Wie bei M29/M30 sind die Tests **nicht** gegen die Anwendung gelaufen
(Importsperre für `kontor`); sie sind ungeprüft gegen eine Implementierung.

### Was übernommen wurde

| Teil der Definition | Ort |
| --- | --- |
| 3 Lernmodell: Erklärung, Übersicht, Einstellungen, automatische Regeln, Mock-Lerndaten | `lernmodell.md` 8–10 |
| 5, 9 Monatsbericht und weitere Berichte | `berichte.md` 6 (Felder des Monatsberichts: E-282) |
| 7 Mails über die Bestellnummer, `KONTOR_MAIL_ABGLEICH=0` | `erwartungen.md` 14, `betrieb.md` 3 |
| 2 Branch statt Version | `version.md` 6 |
| 4 Testinstanz | `betrieb.md` 9 |
| 1, 3, 6, 7, 8, 9 Oberfläche | `oberflaeche.md` 40 |
| Konfiguration, Protokoll, Sicherung | `python-api.md` 22, `protokoll.md` 23, `sicherung.md` 13 |
| REST | `openapi.yaml` 2.24.0 (15 neue Operationen, `LernZustand.schwelle_promille` 500–990, `Regel.automatisch`/`empfaenger_id`, `lernregel_gesperrt`, `MailNachrichtEintrag.angehaengt`, Fehlercode `bestand_nicht_leer`) |
| Plan | `meilensteine.md` (M31) |

### Frühere Meilensteine (E-291) und Widersprüche

- Einstellungen in Bereichen: Hilfe `m31.einstellungen_oeffnen` /
  `einstellung_oeffnen` (Zuordnung `m31.BEREICH_VON`); angepasst M8
  `test_einstellungen_test_benachrichtigung_mock`, `_ntfy`, `test_einstellungen_ohne_plugin`,
  `test_einstellungen_geheimnis_und_sicherung`, `test_seiten_im_mindestumfang`,
  `test_schreiben_mit_csrf_und_abmelden`, `test_ohne_anmeldung_kein_abmelden`, `test_pin_dialog`; M23
  `test_einstellungen_schutz`, `test_einstellungen_reihenfolge`; M28 `test_abmelden_vergisst_person`;
  `m29.bankzugang_oeffnen` öffnet den Bereich `bank`.
- M13: Knopf „Über“, wenn die Hülle `zweig-link` enthält (`m13.knopf_text_soll`; drei Testfunktionen,
  sechs Fälle).
- M20 `test_ausgelieferte_umgebungsdatei`: `KONTOR_MAIL_ABGLEICH=0`.
- M28: `m28.perioden_soll`/`perioden_text` mit der Ebene `abschnitt` (Gruppierungstests unverändert).
- **W-015** (E-289): `test_hoechstens_600_zeilen_aelteste_zuerst` wiederholt bis 600 Zeilen (höchstens 300 Abrufe).
- **W-016** (E-290): UPD-Version der FinTS-Attrappe hängt von `upd_ohne_*` ab; neuer Attrappentest
  `test_fints_m29_benutzerparameter_neue_version_beim_umschalten` (ohne die Korrektur rot, mit grün).

### Tests

| Datei | Fälle | davon `kern` | Browser |
| --- | ---: | ---: | ---: |
| `tests/app/m31/test_m31_konfiguration.py` | 9 | 9 | – |
| `tests/app/m31/test_m31_lernmodell.py` | 25 | 25 | – |
| `tests/app/m31/test_m31_regeln_automatisch.py` | 17 | 17 | – |
| `tests/app/m31/test_m31_berichte.py` | 31 | 31 | – |
| `tests/app/m31/test_m31_bestellnummer.py` | 9 | 9 | – |
| `tests/app/m31/test_m31_oberflaeche.py` | 16 | – | 16 |
| `tests/spec/test_openapi.py::test_m31_schemas` | 1 | – | – |
| `tests/attrappen/…neue_version_beim_umschalten` | 1 | – | – |

Neu: 109 Fälle (107 in `tests/app/m31/`). Geändert: 16 frühere Testfunktionen (siehe oben) und zwei
Schematests (`test_alle_operationen_vorhanden`, `test_m30_schemas`); Hilfen `m13`, `m28`, `m29`,
`fints_attrappe`. Gesamt `--voll --collect-only`: 4 184 (vorher 4 075).

### Prüfungen vor dem Abschluss

`python -m pytest --voll tests/generator tests/spec`: 218 grün; `--voll --collect-only`: 4 184 Fälle ohne
Sammelfehler; `tests/attrappen` 26 grün; `--ohne-app` über `tests/app/m31` ohne Import- oder Sammelfehler.
Alle Läufe mit der Importsperre für `kontor`.

### Selbstprüfung

`python -m tests._selbstpruefung` mit den Mutanten der Hülle und Navigation aus M13
(`tests/_selbstpruefung/LETZTER_LAUF.md`): Referenz grün (1 572 Kern-Tests), Erweiterungslauf (E-124) grün,
4 von 4 Mutanten erkannt (`m13_huelle_ohne_version`, `m13_version_normalisiert`, `m13_navigation_erweitert`,
`m13_knopf_zuerst`). M31 ist ausgelassen (`OHNE_REFERENZ`, E-292), kein neuer Mutant.

### Offene Punkte für den Implementierungs-Thread

1. **Festlegungen des Test-Threads**, nach denen sich die Anwendung richten oder einen Widerspruch melden soll:
   Feldnamen der Erklärung `GET /api/buchungen/{id}/lernmodell` (`vorhersage`, `merkmale[].merkmal`,
   `aehnliche[].buchung_id`; E-280); Pflichtfelder des Monatsberichts (`monat`, `konto_ids`, `ausgaben` als
   positive Cent, `einnahmen`, `fest`, `variabel`, `umbuchungen`; Darlehenskonto = Konto eines Kredits;
   `konto_ungueltig` für Nicht-Bestandskonten; E-282); Kennungen der Bereiche der Einstellungen
   (`allgemein`, `bank`, `mail`, `benachrichtigungen`, `sicherheit`, `daten`) und die Zuordnung der
   bisherigen Elemente (`abmelden`/`schutz-status` → `sicherheit`, `status-modus` → `allgemein`,
   `pin-status` → `bank` auch im Mock-Modus; E-286); `PUT /api/lernmodell/einstellungen` ändert nur
   angegebene Felder.
2. **Offen gelassen** (mehrere Formen zugelassen): Status 200 oder 201 der Lerndaten; `lernregel_gesperrt` in
   `GET /api/empfaenger` (ja oder nein); Bedingung der automatischen Regel (bisherige Form oder Ausdruck);
   Grenze des 365-Tage-Fensters; `gruppe` der Änderung `regel_automatisch`.
3. **Nicht geprüft:** Standardkategorie als Hindernis (entfällt mit Paket 4), Übersicht des Lernmodells
   (nur 200), Inhalt der neun weiteren Berichte, Hochrechnung/Vergleiche/Ausreißer des Monatsberichts,
   Kommandozeile und Skript der Testinstanz (root, systemd, Netz), Gliederung des Verwendungszwecks
   (keine Kennungen), Suche der Einstellungen (keine Kennungen der Treffer), Meldung und gemeinsamer
   Rückgängig-Schritt nach automatischen Regeln, Logzeile `kontor.bestellmail`.
4. **Branch-Anzeige:** Die M13-Tests erwarten auf einem Entwicklungsbranch „Über“; die Abnahme soll auf
   `main` laufen.

## Meilenstein 32 (Auftrag 2026-11-22, Paket 4): Sammelbranch `feature/sammel3`

Stand: 2026-11-22, Test-Thread. Grundlage: Definition 4
(`spec/definitionen/definition-4-sammelbranch-sammel3.md` mit den Anlagen
`ANBIETER.md`, `HTTPS.md`, `TESTINSTANZ.md` unter `spec/definitionen/anlagen/`),
übernommen ohne gesonderte Freigabe („direkt weiter“, E-293). Dazu die
Widersprüche W-017 bis W-021 aus dem M30/M31-Lauf
(`spec/definitionen/widersprueche-m31.md`). Entscheidungen E-293 bis E-313.
Wie bei M29–M31 sind die Tests **nicht** gegen die Anwendung gelaufen
(Importsperre für `kontor`); sie sind ungeprüft gegen eine Implementierung.

### Was übernommen wurde

| Teil der Definition | Ort |
| --- | --- |
| 1 Kontonamen je Ebene, Bereinigen | `sammel3.md` 1, `datenmodell.md` 20 |
| 2 Standardkategorie entfällt, Konten und Anzahlen je Empfänger | `sammel3.md` 2, `buchhaltungspflege.md` 11 |
| 3 Statistik entfällt | `sammel3.md` 3, `sammel.md` 6 |
| 8 Mail-Liste (Suche, Zuordnen von Hand, Gruppen, Betrag), Bilder | `sammel3.md` 8 |
| 9 Anbieter-Beschreibungen, PayPal | `sammel3.md` 9, `erwartungen.md` 5.2/15, `python-api.md` 23 |
| 11 Konfiguration | `sammel3.md` 11 |
| 14 Geplante Zahlungen | `sammel3.md` 14, `sicherung.md` 14, `protokoll.md` 24 |
| 15 HTTPS | `sammel3.md` 15, `betrieb.md` 10 |
| 4–7, 10, 12, 13 Oberfläche | `oberflaeche.md` 41 |
| REST | `openapi.yaml` 2.25.0 (fünf neue Operationen, `GET /api/statistik` entfernt, neue Parameter und Felder, drei Fehlercodes) |
| Plan | `meilensteine.md` (M32) |

### Frühere Meilensteine (E-307, E-312) und Widersprüche

- **Kontonamen:** M1 `test_namen_nicht_eindeutig` → `test_namen_je_ebene_eindeutig`,
  `test_kategorien_ueber_art_name_eltern`; Zufallsbücher `kmy_buch`/`gnc_buch` mit eindeutigen Namen
  (`normal.eindeutiger_name`); M4 `test_vorhandenes_konto_hoechstens_einmal`; M19
  `test_umbuchungen_anfangssalden_und_unbekannte`, `test_zuordnung_vorhandener_kategorien`; Orakel von
  `test_zufaelliges_rueckgaengig_gegen_orakel` mit 409 `konto_existiert`; `m5.Kreditbuch` nutzt vorhandene
  gleichnamige Konten.
- **Standardkategorie:** `m3.stammdaten_anlegen` legt Regeln „Empfänger ist <Name>“ an (`m3.vorschlag_soll`);
  angepasst M3 (`test_m3_empfaenger.py` fünf Tests, `test_m3_protokoll.py`, `test_m3_rueckgaengig.py`,
  `test_m3_erfassen.py::test_empfaenger_name`, `test_m3_konto_loeschen.py::test_standardkategorie` und Aufbau),
  M4 (zwei), M9 (`test_vorschlaege_aller_quellen_aliase_und_lernmodell`), M15 (`test_vorschlag_marken`),
  M19 (`_aufbau`).
- **Statistik:** `tests/app/m27/test_m27_statistik.py` entfernt (5 Testfunktionen), M28
  `test_statistik_seite`, `test_statistik_ohne_bestandskonto` entfernt, `/statistik` aus den Routen- und
  Leerwort-Tests; Navigation und Palette über `m8.NAV_LINKS` (mit `navlink-tags`), `NAV_LOSE`,
  `ohne_lose_links`, `GEHE_LOSE`, `gehe_geordnet` (M8, M13, M28).
- **Bestätigen** mit „B-Torsten“ (M28, drei Tests); **Erfolgsmeldung** über
  `neue_seite(..., erfolgsmeldung=True)` (M8 `test_rueckgaengig_ueber_meldung`, M15, M18, M19, M20 je ein Test);
  **Handy-Kontoblatt** über `m8.ansicht_aufklappen` (M8 `test_filter[handy-*]`, Hilfen); **PayPal** M20
  `test_automatisch_ueber_betrag_nur_eindeutig`; **M31** `test_mail_liste_angehaengt_stand_und_filter` mit
  `betrag`.
- **W-017 bis W-019** (E-309): Orakel der Erklärung bei `unbekannt`, eindeutige beste Buchung, Eröffnungsbuchung
  der Lerndaten. **W-020** (E-310): `m29.bankzugang_oeffnen` klappt „Erweitert“ auf. **W-021** (E-311):
  `m28.balken` liefert Tupel.

### Tests

| Datei | Fälle | davon `kern` | Browser |
| --- | ---: | ---: | ---: |
| `tests/app/m32/test_m32_kontonamen.py` | 18 | 18 | – |
| `tests/app/m32/test_m32_empfaenger.py` | 8 | 8 | – |
| `tests/app/m32/test_m32_mail.py` | 16 | 16 | – |
| `tests/app/m32/test_m32_anbieter.py` | 18 | 18 | – |
| `tests/app/m32/test_m32_geplant.py` | 20 | 20 | – |
| `tests/app/m32/test_m32_betrieb.py` | 10 | 10 | – |
| `tests/app/m32/test_m32_oberflaeche.py` | 23 | – | 23 |
| `tests/spec/test_openapi.py::test_m32_schemas` | 1 | – | – |

Neu: 114 Fälle (113 in `tests/app/m32/`). Geändert: rund 45 frühere Testfunktionen und Hilfen (siehe oben),
fünf Schematests (`test_alle_operationen_vorhanden`, `test_m20_schemas`, `test_m24_schemas`, `test_m27_schemas`,
`test_m31_schemas`). Entfernt: 7 Testfunktionen (10 Fälle). Gesamt `--voll --collect-only`: 4 288 (vorher 4 184).

### Prüfungen vor dem Abschluss

`python -m pytest --voll tests/generator tests/spec`: 219 grün; `--voll --collect-only`: 4 288 Fälle ohne
Sammelfehler; `--ohne-app` über `tests/app/m32` ohne Import- oder Sammelfehler. Alle Läufe mit der Importsperre
für `kontor`.

### Selbstprüfung

`tests/_selbstpruefung/LETZTER_LAUF.md`: Referenz grün (1 572 Kern-Tests), Erweiterungslauf (E-124) grün,
9 von 9 Mutanten erkannt (`m32_kontonamen_doppelt`, `m32_standardkategorie_bleibt`, `m28_palette_alt`,
`m28_alt_acht`, `m13_navigation_erweitert`, `regel_prioritaet_umgekehrt`, `undo_ohne_zustandspruefung`,
`loeschen_vorschlag_bleibt`, `sicherung_pruefsumme_ungeprueft`); Mutantenläufe gezielt auf ihren Bereich
(Laufzeitgrenze). M32 ist ausgelassen (`OHNE_REFERENZ`, E-308); die Referenz kennt Kontonamen je Ebene und
lehnt Standardkategorien ab (E-312).

### Widersprüche W-022 bis W-026 (E-313)

Aus dem Lauf der M32-Tests gegen die App: W-022 (App-Uhr vor der letzten Mail), W-023 (zweimal „Giro“), W-026
(Mails vor dem Erstabruf) waren Testfehler und sind behoben; W-024: `openapi.yaml` nennt 422 für
`…/mail/html`; W-025: „Anzeigen im Konto“ wird über `empfaenger_id=` oder den übernommenen `filter=` und die
sichtbaren Buchungen geprüft.

### Offene Punkte für den Implementierungs-Thread

1. **Festlegungen des Test-Threads** (bitte danach richten oder als Widerspruch melden): `details.konto_ids`
   enthält das vorhandene gleichnamige Konto; Bereinigung beim Import in derselben Änderung, Warnungen mit dem
   Namen in `referenz`; Umlaute zählen bei Kontonamen als verschieden; übernommenes „Unkategorisiert“/
   „Korrekturen“ erhält die technische Kennung (E-295). Reihenfolge von `GET /api/empfaenger/{id}/konten`
   (`anzahl` absteigend, dann `konto_id`) und `/anzahlen` (nach `empfaenger_id`) (E-297). Mail-Zuordnung von
   Hand: 201 `Dokument`, Prüfreihenfolge 404 → 422 → 404, `angehaengt` mit `nummer = ""` auch ohne
   `mail_bestellnummer`; `suche` mit `norm` je Wort, `stand` ohne `suche`; `gruppieren` mit `ja`/`nein`
   (E-299). `bilder` mit `ja`/`nein`, anderer Wert 422 (E-300). `anbieter_verzeichnis` als Pfad, nicht
   vorhandenes Verzeichnis wirkt wie keines (E-301). Wiederholung: Fehlercodes und Prüfreihenfolge, `PATCH`
   mit `keine` entfernt, Vorschau-Ereignisse mit `datum` (E-303). Konfiguration: `gesetzt`, `bekannt`,
   `geaendert` wie beschrieben, Form der Werte frei (E-304). Warnung beim Erzeugen der App (E-305).
   Oberfläche: `empfaenger-treffer` mit `data-anzahl`, `km-spalte-<feld>` mit `aria-checked`, `mail-suche`
   schreibt `suche=`, `tab-andere-schliessen` lässt nur den aktiven Tab (E-306).
2. **Nicht prüfbar:** Bereinigen des Altbestands beim Start und beim Einspielen, Umwandlung der
   Standardkategorien und der Personen-Tags, ältere Sicherungen (E-295, E-296, E-273); die Skripte
   `kontor-https`/`kontor-test` (nur Vorhandensein, Unterbefehle, kein `funnel`).
3. **Nicht geprüft:** Kreditbezug beim Bereinigen, Ersetzen mitgelieferter Anbieter-Beschreibungen, Neulesen der
   Kennungen bei geänderten Mustern, 200 000-Zeichen-Grenze, Zählweise von `background`/`url()`, Darstellung aus
   D-236 (Spaltenbreiten, Balken, Farben), Dialog zum Zuordnen von Mails im Einzelnen, „Weitere anzeigen“ und
   Suche im Änderungsfenster, Bereichsauswahl mit Umschalt+Pfeil, Mail-Blatt-Gruppierung in der Oberfläche
   über `data-gruppe` hinaus.
4. **Offen in der Definition:** Ob Erfassen ohne Kategorie Regeln auswertet (gelesen: nein, E-296); ob
   `gruppe` bei Mails ohne weitere Mail `null` oder die eigene ID ist (beides zugelassen); Stelle von
   `navlink-konfiguration` und der neuen Palettenbefehle (nicht geprüft); ob „Abgeglichen: …“ und ähnliche
   Hinweise unter die ausgeschaltete Erfolgsmeldung fallen (die betroffenen Tests schalten sie ein).
5. **Risiko:** Frühere Tests, die mehrere gleichnamige Konten anlegen, wurden statisch gesucht (keine weiteren
   Funde) und für die Kern-Tests über die Referenz geprüft; Browser- und Tests ohne Referenz (M18–M31) können
   trotzdem noch auf ein gleichnamiges Konto stoßen – dann bitte als Widerspruch melden.

### Widersprüche W-027 bis W-030 aus dem Gesamtlauf (E-314)

M18 `_konto_und_buchung` nutzt vorhandene Konten (W-027); M2 `test_aendern` vergleicht ohne `ausdruck`
(W-028); das Löschorakel lässt `ausdruck` bei Regeln mit `konto_id`-Bedingung offen (W-029); M19
`test_mit_loeschen_gegen_orakel` erwartet `empfaenger_geaendert = []` (W-030). Prüfung: Referenz grün für
`test_m2_regeln_api.py` und `test_m3_konto_loeschen.py` (90 Kern-Tests), Mutant `loeschen_vorschlag_bleibt`
erkannt; M18/M19 sind ohne Referenz (`OHNE_REFERENZ`), dort nur `--ohne-app` ohne Sammelfehler.
`--voll tests/generator tests/spec` 219 grün, `--voll --collect-only` 4 288 Fälle.
