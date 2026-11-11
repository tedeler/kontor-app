# Ergebnis der Implementierung

## Abnahme M16 (Wiederkehrend: robuste Kette und Begründung) gegen kontor-tests `590f096`

Stand: 2026-11-11, Implementierungs-Thread, Branch `feature/wiederkehrend-begruendung` (main mit M15 übernommen).

- `-m m16`: zuerst 13/53; behoben: `kandidaten` immer als Liste (E-195), unbekannte Query-Parameter → 422,
  Zusatzregel auch beim Bruch durch eine fremde Zahlung (E-193), Kandidaten des aktuellen Termin-Fensters zählen nicht
  pauschal als zusätzlich (Definition 1.2). Danach **53/53**; zusätzlich 3 × 20 000 Zufallsgruppen gegen die
  Referenzkette der Tests ohne Abweichung.
- Widerspruch „leere Liste nur Hinweis“ als Text an den Test-Thread, dort gelöst (E-204); kein W-Eintrag.
- Nach Übernahme von main (M17, Version 0.07; D-120): Volllauf `--voll -n 4` **2851 / 2851** grün (inkl. M16, M17,
  Browser, Leistung, AqBanking; nichts übersprungen). Eigene Tests 165/165.
## Abnahme M17 (Tabs der Ansichten, Gehe zur Gegenbuchung) gegen kontor-tests `f137465`

Stand: 2026-11-11, Implementierungs-Thread, Branch `feature/tabs-gegenbuchung` (main mit M16 und Version 0.06
übernommen; Entscheidung als D-119, da D-115…D-118 an M16 vergeben). Meilenstein-Definition vom Auftraggeber
freigegeben; vom Test-Thread als **M17** übernommen (M16 war inzwischen an `wiederkehrend-begruendung` vergeben).

- `-m m17`: zuerst 34/35; behoben: ohne verfügbaren Browser-Speicher (Zugriff auf `localStorage` wirft) startete die
  Oberfläche nicht, weil Design und Layout ungeschützt lasen/schrieben. Danach **35/35**.
- Schnelllauf `-n 8`: 2343 grün, 28 übersprungen (AqBanking-Werkzeuge fehlen in dieser Umgebung), **28 rot – alle in
  `tests/app/m16/`** (REST, z. B. Schema verlangt `kandidaten` je Schritt). Identisch auf main ohne dieses Feature
  (Python-Code unverändert gegenüber main) – betrifft das Feature `wiederkehrend-begruendung`, nicht M17.
- Browsertests (`-m browser`): 313 grün; rot 12 M16-Oberflächentests (identisch auf main) und gelegentlich
  `test_m8_bearbeiten.py::test_konto_loeschen_rueckgaengig` (schwankt auch auf main; in Wiederholungen grün).
- Eigene Tests: **165 / 165** (neu `tests/test_browser_tabs.py`, 7 Fälle).
- Kein W-Eintrag.

## Merge `feature/wiederkehrend-begruendung` (M16) auf main

Stand: 2026-11-11, auf Anweisung des Auftraggebers vor den M16-Abnahmetests gemergt (`tests/app/m16/` gibt es in
kontor-tests `2e8f8ea` noch nicht; Spezifikation M16 und M5-Anpassung liegen vor).

- Der Merge `38f9b8a` (main in den Branch) hatte `src/kontor/wiederkehrend.py` auf 0 Zeilen geleert und
  `tests/test_wiederkehrend_eigen.py`, `tests/test_browser_wiederkehrend.py` gelöscht (Folge: 500 bei
  `/api/wiederkehrend`, 24 rote M5-Tests). Wiederhergestellt aus `5871330` mit den im Merge umnummerierten
  Entscheidungen (D-108…D-111 → D-115…D-118); übrige Konfliktauflösung geprüft und übernommen.
- Danach gegen kontor-tests `2e8f8ea`: Schnelllauf `-n auto` **2365 / 2365**; eigene Tests **158 / 158**.
- Offen: Abnahme mit den M16-Tests, sobald der Test-Thread sie gepusht hat.

## Abnahme M15 (Sammelpaket) gegen kontor-tests `8110ece`

Stand: 2026-11-11, Implementierungs-Thread, Branch `feature/sammelpaket` (main mit `feature/update` übernommen).

- `-m m15 --voll`: zuerst 75/78; behoben (D-114): Rückgängig bis ohne Nettowirkung antwortet 409
  `bereits_rueckgaengig` ohne Änderung (E-190), der Zuordnungsdialog bietet in einer Reihe das eben zugeordnete Konto
  nicht mehr an. Danach **78/78**.
- Volllauf `--voll -n 2`: **2762 / 2762** grün (inkl. Browser, Leistung, AqBanking), eigene Tests 148/148
  (`test_desktop_ablauf` schwankt wie bekannt gelegentlich im Gesamtlauf, einzeln grün).
- Kein W-Eintrag.

## Feature Sammelpaket (Meilenstein-Definition M15, Entwurf) gegen kontor-tests `65bffb0`

Stand: 2026-11-10, Implementierungs-Thread, Branch `feature/sammelpaket` (iterative Phase; Definition zur Freigabe im
Projekt als `claude/feature-sammelpaket.md`, Abnahmetests für M15 gibt es noch nicht).

| Auswahl | vorher (`d308b96`) | nachher |
| --- | ---: | ---: |
| Volllauf `--voll -n 2` (inkl. Browser, Leistung, AqBanking) | 2303 / 2303 (Schnelllauf) | **2683 / 2683**, 0 übersprungen |
| eigene Tests (`tests/`) | 106 | **126 / 126** |

- Umfang: Rückgängig bis einschließlich einer Änderung (`bis_id`, D-108), Mehrfach-Löschen als eine Änderung
  (D-109), Verschieben von Buchungen bzw. eines ganzen Imports/Laufs auf ein anderes Konto (D-110),
  Synchronisationskonto in den Kontoeinstellungen und Zuordnungsdialog für unbekannte Bankkonten
  (`KONTOR_SYNC_KONTEN_ANLEGEN`, ausgeliefert `0`, D-111), gesperrter PIN-Dialog mit Statusanzeige und Vorschläge
  je Zeile (D-112), Berichtsgrafiken mit Plotly (lokal ausgeliefert, D-113).
- Kein neuer W-Eintrag. Die neuen Endpunkte stehen noch nicht in `openapi.yaml`; das übernimmt der Test-Thread mit
  der Definition.
- Das Feature `update` (D-107) ist inzwischen auf main und wurde in den Branch übernommen; Konflikte in
  `ENTSCHEIDUNGEN.md`, `ERGEBNIS.md`, `app.py` und `haupt.js` (nur Importe) aufgelöst.

## Feature Update (Meilenstein-Definition M14 als Entwurf, D-107)

Stand: 2026-11-10, Implementierungs-Thread, Branch `feature/update`. Auf Anweisung des Auftraggebers vor den
Abnahmetests auf main gemergt (Tests für M14 gibt es in kontor-tests noch nicht; Definition im Projekt unter
`claude/feature-update.md`).

- Gegen **kontor-tests `65bffb0`**: Volllauf `--voll -m "not leistung" -n 4` **2661 / 2661**.
- Eigene Tests **128 / 128** (davon 22 neu in `tests/test_update_eigen.py`).
- Oberfläche im Browser gegen eine lokale Attrappe der GitHub-API geprüft (Punkt am Versionsknopf, Abschnitt
  „Aktualisierung“ im About-Dialog, Auftrag abgelegt).
- Einschränkungen: kein echter Abruf bei GitHub aus der Sandbox (direkte Verbindungen ohne Proxy werden dort mit
  403 abgewiesen; Kontor nutzt absichtlich keinen Proxy aus der Umgebung); Installation und Neustart über systemd
  nicht real ausgeführt, nur mit untergeschobenen Befehlen getestet.

## Meilenstein 12 (Bearbeiten, Massenänderungen, Filterleiste) gegen kontor-tests `65bffb0`

Stand: 2026-11-10, Implementierungs-Thread, Branch `feature/buchungsbearbeitung`. Definition und Abnahmetests lagen
in kontor-tests bereits vor (E-167 bis E-174, `tests/app/m12/`).

| Auswahl | vorher (`d2246ca`) | nachher |
| --- | ---: | ---: |
| `m12` (`--voll`) | 19 / 73 (54 rot) | **73 / 73** |
| Volllauf `--voll -m "not leistung" -n 4` | – | **2661 / 2661**, 0 übersprungen |
| `-m leistung` | – | **22 / 22** |
| `-m m12` mit `KONTOR_TESTS_ANMELDUNG=1` bzw. `KONTOR_TESTS_ZUSATZFELDER=1` | – | je 73 / 73 |
| eigene Tests (`tests/`) | 103 | **106 / 106** |

- Zusammen alle **2683** Abnahmetests grün (AqBanking 6.5.4 installiert, Browsertests mit Chrome headless liefen).
- Kein neuer W-Eintrag.
- Umsetzung: `POST /api/buchungen/mehrfach/aendern` (`buch.mehrfach_aendern`, Aktion `mehrfach_aendern`);
  Oberfläche: Filterleiste anfangs eingeklappt, Inline-Editoren für Empfänger, Status und Betrag, `mehrfach-status`,
  `mehrfach-bearbeiten`, `km-status`, `km-mehrfach`, `status-auswahl`, `mehrfach-dialog`; Entscheidungen D-106.
- Nebenbei behoben: Beim Fokussieren einer Zeile sprang die waagerecht gescrollte Liste an den Zeilenanfang (D-106).

## Abnahme M13 (Versionierung) gegen kontor-tests `65bffb0`

Stand: 2026-11-10, Implementierungs-Thread, Branch `feature/versionierung-abnahme`.

- `-m m13 --voll`: zuerst 36/40; behoben: `datenbank` in `/api/version` war bei relativ konfiguriertem Pfad nicht
  absolut (version.md 3.2), `ueber-repository` stand an der Tabellenzelle statt am Link. Danach **40/40**, ebenso
  mit `KONTOR_TESTS_ANMELDUNG=1` und `KONTOR_TESTS_ZUSATZFELDER=1` (je 40/40).
- Schnelllauf `-n auto`: 2249 bestanden, 54 rot – ausschließlich `tests/app/m12/` (M12 noch nicht umgesetzt).
- Eigene Tests 103/103; `tests/test_browser.py::test_desktop_ablauf` schwankt gelegentlich unter Last im
  Gesamtlauf (auch ohne diese Änderung, einzeln stets grün; in der Release-CI ohne Browser übersprungen).

## Feature Versionierung (Meilenstein-Definition M13, D-105)

Stand: 2026-11-10, Implementierungs-Thread, Branch `feature/versionierung`. Definition vom Auftraggeber freigegeben;
auf seine Anweisung vor den Abnahmetests auf main gemergt (Tests für M13 gibt es in kontor-tests noch nicht).

- Gegen **kontor-tests `569016f`**: Schnelllauf `python -m pytest -n auto` 2198 bestanden, 54 rot – alle in
  `tests/app/m12/` (M12 ist noch nicht umgesetzt); außerhalb von M12 keine Fehlschläge. `-m m8 --voll`: 258/258 nach
  der Umbenennung `nav-version` → `version-knopf` (die Navigation darf nur die spezifizierten `nav-`Einträge haben).
- Eigene Tests: alle grün außer dem vorbestehenden `test_m3_eigen.py::test_migration_von_schemaversion_2_ohne_datenverlust`
  (Datei `tests/daten/schema_m2.sql` fehlt im Repository, weil `.gitignore` `daten/` ausschließt; nicht Teil dieses
  Features).
- Release-CI lokal nachgestellt (Version erhöhen, `build.json`, Wheel bauen, installiert prüfen); der erste echte Lauf
  folgt mit dem Merge auf main (erwartet: `v0.01`).
- Einschränkung: Kein Volllauf `--voll` aller Abnahmetests in einem Durchgang (Zeitgrenze der Sitzung).

## Meilenstein 11 (Kontostand, Kategorien als Konten, Empfänger zusammenführen)

Stand: 2026-11-09, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `9bee6bc`** („M11: Selbstprüfung festgehalten …“), Lese-Klon nach
  `git pull`. AqBanking 6.5.4 (`aqbanking-tools`), Python 3.13, Playwright mit Chrome headless.
- Aufrufe: `python -m pytest -m "not leistung" -n 3` (2519) und `python -m pytest -m leistung` (22); zusammen alle
  **2541** gesammelten Tests. Zusätzlich `-m m11` seriell, mit `KONTOR_TESTS_ZUSATZFELDER=1` und mit
  `KONTOR_TESTS_ANMELDUNG=1` (je 45/45, nichts übersprungen).

| Auswahl | vorher (Stand `99c2c95`) | nachher |
| --- | ---: | ---: |
| **vollständig** | 2503 / 2541 | **2541 / 2541** |
| `m1`–`m10` | 2409 / 2409 | 2409 / 2409 |
| `m11` | 7 / 45 | **45 / 45**, 0 übersprungen |

- „Vorher“: `-m m11` vor der ersten Änderung (38 Fehlschläge, alle in `tests/app/m11/`); frühere Meilensteine
  laut M10-Ergebnis vollständig grün.
- Im parallelen Gesamtlauf (`-n 3`) scheiterte einmal `tests/app/m8/test_m8_bearbeiten.py::
  test_neue_aktion_leert_wiederholen` an einer Zeitgrenze (Meldung noch sichtbar); im Lauf `-m "m8 or m11"` und
  dreimal einzeln wiederholt grün. Kein Zusammenhang mit M11 (Rückgängig/Wiederholen unverändert); kein W-Eintrag.
- Kein neuer W-Eintrag.

### Umsetzung

- **Kontostand** (`kontostand.md`): `BankSaldo`, `Umsatzliste` in `plugins/bank.py`; Mock mit
  `bank.anfangssalden`; FinTS sendet `HKSAL` im Dialog des Umsatzabrufs (auch nach TAN), AqBanking `--balance` nur
  mit `aqbanking_saldo` und genau einem zweiten `request` bei lokaler Ablehnung. Abgleich und Ausgleichsbuchung in
  `SyncDienst._saldo_abgleichen` (eigene Änderung `sync_saldoausgleich`, Benachrichtigung `saldo_ausgeglichen`),
  Ergebnis `SyncKonto.saldo_abgleich`; Konfiguration `sync_saldo_angleichen`, `aqbanking_saldo`. Datenbankschema 9
  (Spalte `sync_lauf_konto.saldo_abgleich`, Migration). D-102, D-103.
- **REST:** Filter `unterkonten` für Buchungsliste und Exporte; `name` beim Zusammenführen von Empfängern.
- **Oberfläche** (`oberflaeche.md` 22): Kategorien in der Finanzübersicht (einklappbar, Zustand im Browser),
  Kategorieansicht mit `data-kontoklasse`, Spalte „Konto“, `filter-konto`, `filter-unterkonten`; Empfänger mit
  Auswahl und Zusammenführen-Dialog (Ziel nach Buchungszahl, Name, Vorschau der Aliase); `/sync` zeigt den
  letzten Saldoabgleich je Bankkonto. D-104.
- Eigene Tests `tests/test_m11_eigen.py` (HISAL-Abbildung, AqBanking-Kontext, Migration 8→9); in
  `tests/test_m7_eigen.py` die Schemaversion nicht mehr fest auf 8.
- Codequalitätsanalyse vor M11 in `refactor.md` (eigener Commit).

### Einschränkungen

- Eigene Tests: weiterhin scheitert `tests/test_m3_eigen.py::test_migration_von_schemaversion_2_ohne_datenverlust`
  in einem frischen Klon (fehlende, nie eingecheckte `tests/daten/schema_m2.sql`, siehe unten); alle übrigen
  eigenen Tests grün.
- Keine echten Banken angesprochen; FinTS nur gegen die Attrappe, AqBanking gegen die Attrappe im Profil `mt940`.


## Meilenstein 10 (AqBanking-Plugin)

Stand: 2026-11-09, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `77a4cae`** („M10: Tests, Testhilfen und Selbstprüfung für das
  AqBanking-Plugin …“), Lese-Klon nach `git pull`. AqBanking 6.5.4 (`aqbanking-tools`, Gwenhywfar 5.10.2) unter
  Ubuntu 24.04, Python 3.13, Playwright mit Chrome headless.
- Aufrufe: `python -m pytest -m "not leistung" -n 2` (2473) und `python -m pytest -m leistung` (22); zusammen alle
  **2495** gesammelten Tests. Zusätzlich `-m m10` seriell, mit `KONTOR_TESTS_ZUSATZFELDER=1` und mit
  `KONTOR_TESTS_ANMELDUNG=1` (je 46/46).

| Auswahl | vorher (Stand `a15f0f0`) | nachher |
| --- | ---: | ---: |
| **vollständig** | 2451 / 2495 | **2495 / 2495** |
| `m1` | 674 / 674 | 674 / 674 |
| `m2` | 226 / 226 | 226 / 226 |
| `m3` | 245 / 245 | 245 / 245 |
| `m4` | 227 / 227 | 227 / 227 |
| `m5` | 212 / 212 | 212 / 212 |
| `m6` | 273 / 273 | 273 / 273 |
| `m7` (davon 22 `leistung`) | 192 / 192 | 192 / 192 |
| `m8` (davon 214 Browsertests) | 258 / 258 | 258 / 258 |
| `m9` | 56 / 56 | 56 / 56 |
| `m10` | 2 / 46 | **46 / 46**, 0 übersprungen |

Kein Fehlschlag, kein übersprungener Test, kein neuer W-Eintrag. „Vorher“ ist der Lauf vor der ersten Änderung
(`-m "not leistung" -n 2`: 2429 bestanden, 44 Fehlschläge/Fehler ausschließlich in `tests/app/m10/`; `leistung`
wurde vorher nicht erneut gemessen, laut Ergebnis von M8 22/22; die Spalte „vorher“ zählt sie als bestanden).

### Umsetzung

- `src/kontor/plugins/aqbanking.py` (neu): `AqbankingBankPlugin` nach aqbanking.md 3–6; Entscheidungen D-098 bis
  D-100. `erzeuge_bank_plugin` liefert es bei `bank_plugin = "aqbanking"`.
- `config.py`: `aqbanking_verzeichnis`, `aqbanking_programme`, `aqbanking_timeout_sekunden`, `bank_plugin`
  zusätzlich `aqbanking` (D-101); `fehler.py`: `BankTanNichtUnterstuetzt` (`BankZugangGesperrt` gab es seit M6).
- Betrieb: README-Abschnitt „Bankabruf über AqBanking (M10)“, `kontor.env` mit den vier Variablen als Kommentar;
  systemd-Units unverändert.
- Eigene Tests `tests/test_m10_eigen.py` (Auswertung, Kontextdatei, Kontoliste, PIN-Datei; ohne AqBanking).

### Einschränkungen

- Eigene Tests: `tests/test_m3_eigen.py::test_migration_von_schemaversion_2_ohne_datenverlust` scheitert in
  einem frischen Klon, weil `tests/daten/schema_m2.sql` wegen `daten/` in `.gitignore` nie eingecheckt wurde
  (schon vor M10, unabhängig vom AqBanking-Plugin); die übrigen 75 eigenen Tests sind grün.
- Gegen eine echte Bank ist das Plugin nicht geprüft (nur gegen die FinTS-Attrappe, E-028).

## Meilenstein 8 (vollständige Oberfläche) und W-005

Stand: 2026-11-09, Implementierungs-Thread (Nachtrag nach E-151).

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `bf35445`** („W-007/W-008: Selbstprüfung und ERGEBNIS festgehalten“), nach
  `git pull` im Lese-Klon unmittelbar vor dem Abschlusslauf.
- Aufruf im Wurzelverzeichnis des Lese-Klons gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, Hypothesis-Profil `standard`, Playwright mit dem installierten Google
  Chrome (Kanal `chrome`, headless). Wegen der 10-Minuten-Grenze je Aufruf in vier Vordergrund-Teilen, drei davon
  mit `pytest-xdist -n 2`:
  `-m "not leistung and not m8 and (m7 or not (m1 … m9)) or (m6 and not m7) or (m1 and not m6)"` (1202),
  `-m "((m2 or m3) and not m6) or ((m4 or m5 or m9) and not (m1 or m2 or m3 or m6 or m7))"` (966), `-m leistung`
  (22), `-m m8` (258); zusammen alle **2448** gesammelten Tests (`--collect-only`: 2448).

| Auswahl | gesamt | bestanden | fehlgeschlagen |
| --- | ---: | ---: | ---: |
| **vollständig** | **2448** | **2448** | **0** |
| `m1` | 674 | 674 | 0 |
| `m2` | 226 | 226 | 0 |
| `m3` | 245 | 245 | 0 |
| `m4` | 227 | 227 | 0 |
| `m5` | 212 | 212 | 0 |
| `m6` | 273 | 273 | 0 |
| `m7` (davon 22 `leistung`) | 192 | 192 | 0 |
| `m8` (davon 214 Browsertests) | 258 | 258 | 0 |
| `m9` | 56 | 56 | 0 |
| ohne Meilenstein-Marker (Generator, Spezifikation, Attrappen) | 85 | 85 | 0 |

**Kein Fehlschlag, kein offener W-Eintrag.** W-005 (E-138), W-006 und W-009 (`174b292`), W-007 (E-151) und W-008
(`bf35445`) sind erledigt. Zu E-151: Für nicht kategorisierbare Buchungen (Umbuchungen, gesplittete Buchungen) sendet
die Oberfläche beim Kategorie-Setzen, Ziehen und Wischen die spezifizierte Anfrage und zeigt die Ablehnung 422
`nicht_kategorisierbar` als Fehlermeldung mit der Meldung des Servers; die Zeile behält „Umbuchung“ bzw.
„Gesplittet“, es entsteht kein Protokolleintrag. Das war bereits so umgesetzt; die neuen Tests
(`test_kategorie_setzen_umbuchung_meldet_ablehnung`, `test_umbuchung_auf_kategorie_ziehen_aendert_nichts` u. a.)
sind ohne Änderung an der App grün.

**Einmalig instabiler Test** `test_m8_kontextmenue.py::test_menue_tastatur_und_klick_ausserhalb`: Er schlug in
einem früheren vollständigen `m8`-Lauf (gegen `48e3671`) einmal fehl. Seitdem in drei vollständigen `m8`-Läufen,
dreimal einzeln, viermal parallel mit `test_m8_tastatur.py` sowie in neun Läufen unter zusätzlicher Volllast
eines CPU-Kerns (`-n 2` mit `test_m8_auswahl.py` bzw. `test_m8_tastatur.py`) grün. Geprüfte mögliche Ursachen auf
Seiten der App ohne Befund: Umschalt+F10 löst in Chrome kein zusätzliches `contextmenu`-Ereignis aus (gemessen),
das Menü erhält den Fokus synchron beim Öffnen, der Klick außerhalb wird über ein `pointerdown` in der
Capture-Phase erkannt, das lange vor dem Klick registriert ist, und die Liste lädt während des Tests nicht neu.
Eine Ursache in der App wurde nicht gefunden; daher keine Änderung.

### Eigene Tests (kontor-app)

`python -m pytest tests`: **64 bestanden** – darunter `test_oberflaeche.py` (Hülle für alle Routen, 404 sonst,
Manifest, Service Worker kennt alle Module, kein `innerHTML`/`eval`, nur Pfade der REST-Schnittstelle) und die
Playwright-Rauchtests `test_browser.py` (Desktop-Ablauf mit Auswahl, Kontextmenü, Kategorie-Auswahl,
Inline-Bearbeitung, Strg+Z und Befehlspalette; Panels mit gespeichertem Layout; Handy mit langer Berührung,
Wischen und Menü; Service Worker und Offline-Hinweis) und `test_browser_anmeldung.py` (Ersteinrichtung,
Fehlermeldung, CSRF beim Schreiben, Abmelden; Desktop und Handy). Die Rauchtests der Hash-Oberfläche aus M2–M7/M9
sind entfallen (D-091).

### Umgesetzt

- Neue Single-Page-Oberfläche nach `oberflaeche.md` (D-091 bis D-096): Pfad-Routen, Grundgerüst mit Kopf,
  Navigation und Meldungen, Finanzübersicht, Kontoansicht mit Filtern in der URL, Liste = REST-Antwort,
  Mehrfachauswahl/-bearbeitung, Inline-Bearbeitung, Kontextmenüs, alle Dialoge aus 9, Drag and Drop (Buchungen auf
  Kategorien, Kategorien umsortieren, Panels), Rückgängig/Wiederholen über das Protokoll, Tastaturkürzel und
  Befehlspalette, alle Seiten aus 13, TAN-Seite mit Speichern/Teilen, Panels mit Layout im `localStorage`, mobile
  Ansicht mit Gesten, helles/dunkles Design, PWA (Manifest mit PNG-Symbolen, `/sw.js`, Offline-Hülle),
  Anmeldung, Barrierefreiheit; CSP-konform, ohne CDN.
- `POST /api/benachrichtigungen/test` nach E-138 (W-005 erledigt, D-097).
- Codequalität: Analyse vor M8 in `refactor.md`; R-07 (Oberfläche in ES-Module) erledigt.

### Einschränkungen

- Einige Formulare der alten Oberfläche gibt es nur noch über REST (D-096): Split-Vorlagen und Kredite bearbeiten,
  Raten zuordnen, Lernmodell-Vorhersage, Liste der abgerufenen Mails, Abstimmung aufheben, Synchronisation mit
  eigenem Zeitraum, Ordner/Absenderfilter von Postfächern.
- Die Browsertests liefen mit dem installierten Google Chrome; ein gebündeltes Playwright-Chromium ist nicht
  installiert (die Fixture fällt auf den Kanal `chrome` zurück).
- Installierbarkeit und Teilen wurden nur in Chrome headless geprüft (Teilen mit der Attrappe der Tests), nicht auf
  echten Android-/iOS-Geräten.

## Meilenstein 7 (Sicherheit, Betrieb, Leistung)

Stand: 2026-11-09, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `f17e23a`** („M7: ERGEBNIS.md (Abschnitt M7)“, nach Abschluss der
  M7-Selbstprüfung des Test-Threads), nach `git pull` im Lese-Klon unmittelbar vor dem Abschlusslauf.
- Aufruf im Wurzelverzeichnis des Lese-Klons gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, Hypothesis-Profil `standard`. Wegen der 10-Minuten-Grenze je Aufruf in
  sechs Teilen (Vordergrund): `-m "not leistung and (m7 or not (m1 or m2 or m3 or m4 or m5 or m6 or m9))"`,
  `-m "m6 and not m7"`, `-m "m1 and not m6"`, `-m "(m2 or m3) and not m6"`,
  `-m "(m4 or m5 or m9) and not (m1 or m2 or m3 or m6 or m7)"`, `-m leistung`; zusammen alle 2189
  gesammelten Tests (`--collect-only`: 2189).
- Tests für `m8`: keine vorhanden (0 gesammelt).

| Auswahl | gesamt | bestanden | fehlgeschlagen | Fehler |
| --- | ---: | ---: | ---: | ---: |
| **vollständig (alle gesammelten Tests)** | **2189** | **2189** | 0 | 0 |
| Teil 1: `m7` ohne `leistung` und Tests ohne Meilenstein-Marker | 254 | 254 | 0 | 0 |
| Teil 2: `m6` | 273 | 273 | 0 | 0 |
| Teil 3: `m1` | 674 | 674 | 0 | 0 |
| Teil 4: `m2`, `m3` | 471 | 471 | 0 | 0 |
| Teil 5: `m4`, `m5`, `m9` | 495 | 495 | 0 | 0 |
| Teil 6: `leistung` (großer Datensatz, 50 000 Buchungen) | 22 | 22 | 0 | 0 |
| `m8` | 0 | – | – | – |

W-004 (M2-Statusvergleich mit `pin_quelle`) ist durch E-124 behoben; der M2-Test ist grün. Es gibt **keinen
Fehlschlag**. Offen ist nur W-005 (Spezifikationslücke `POST /api/benachrichtigungen/test`, kein
Testwiderspruch).

### Gemessene Leistungswerte

Eigene Messung mit dem Datensatz `gross` (50 000 Buchungen, erzeugt mit `generator.__main__.gross_dateien`,
Startwert 4711) in-process über `TestClient`, Median aus drei Läufen nach einem Aufwärmlauf (Schreib- und
Exportvorgänge einmal), auf der Testmaschine (2 Kerne; parallel lief die Selbstprüfung des Test-Threads):

| Nr. | Vorgang | gemessen | Grenze |
| --- | --- | ---: | ---: |
| L1 | Import `gross.kmy` in leere Datenbank | 7,5 s | 120 s |
| L2 | zweiter Import (ohne Wirkung) | 2,5 s | 120 s |
| L3 | Buchungsliste Seite 1 (`pro_seite=100`) | 0,20 s | 1 s |
| L4 | letzte Seite | 0,14 s | 1 s |
| L5 | Filter Konto / Zeitraum / Kategorie+Unterkat. / Empfänger / Verwendungszweck / Suche / Betrag / Tag / `-betrag` | 0,10 / 0,01 / 0,03 / 0,01 / 0,03 / 0,15 / 0,14 / 0,01 / 0,24 s | je 1 s |
| L6 | Konto + Zeitraum + Suche | 0,21 s | 1 s |
| L7 | Volltextsuche / Kontenübersicht | 0,30 / 0,27 s | je 1 s |
| L8 | Mehrfachbearbeitung 1 000 Buchungen (mit Protokoll) | 0,13 s | 10 s |
| L9 | Einzeländerung | 0,03 s | 1 s |
| L10 | Kontostandsverlauf / Einnahmen-Ausgaben | 0,15 / 0,13 s | je 3 s |
| L11 | Lernmodell, 100 Vorhersagen | 0,59 s | 3 s |
| L12 | wiederkehrende Buchungen | 0,54 s | 10 s |
| L13 | CSV-Export 50 000 Buchungen | 2,0 s | 20 s |
| L14 | Sicherung | 2,4 s | 30 s |
| L15 | `create_app` auf gefüllter Datenbank | 0,03 s | 5 s |

Vor M7 brauchte der Konto-Filter über eine Minute (SQLite wählte in der korrelierten Teilabfrage den Index
`split_konto`, D-089); behoben ohne neue Indizes, Ergebnisse unverändert.

### Eigene Tests (kontor-app)

`python -m pytest tests`: **73 bestanden**. Neu: `tests/test_m7_eigen.py` (Migration der App-Datenbank von
Schemaversion 7 auf 8 ohne Datenverlust, Sicherung ohne Anmeldetabellen und ohne Passwort-Hash,
CSRF-Ableitung) und der Playwright-Rauchtest `tests/test_browser_m7.py` (Chrome headless, echter Server im
Mock-Modus auf freiem Loopback-Port, Desktop- und Handybreite): Weiterleitung zur Anmeldeseite mit `weiter`,
Mock-Hinweis, Ersteinrichtung mit falschem und richtigem Einrichtungscode, Rücksprung, kein waagerechtes
Scrollen, Passwort ändern (falsches/richtiges altes Passwort), Abmelden (danach 401), Sperre nach drei
Fehlversuchen mit Restzeit-Hinweis und Anmeldung nach Ablauf. Die bestehenden Browsertests verwenden statt
`wait_for_function("…")` eine Abfrage ohne String-Auswertung im Seitenkontext (die CSP verbietet
`unsafe-eval`). Rauchprobe von Hand: `python -m kontor` im Mock-Modus mit Anmeldung (Gesundheit 200, ohne
Sitzung 401, Anmeldung 200, mit Cookie 200, Beenden per `SIGTERM` mit Lognachrichten im Format
`<STUFE> <logger>: …`). Alle Server-, Browser- und Testprozesse sind beendet.

### Umgesetzt

- Haushalts-Login (D-083–D-085): scrypt (n = 2^15) mit NFC, Sitzungen mit Leerlauf/Höchstdauer nach Systemuhr,
  nur SHA-256 des Tokens gespeichert, CSRF-Token per HMAC abgeleitet, Herkunftsprüfung, Bremse mit
  Verdopplung, Ersteinrichtung per Einrichtungscode-Datei (0600) oder `python -m kontor.anmeldung
  passwort-setzen`, Abmelden, Passwort ändern; abschaltbar mit Vorgabe aus, Warnung im Echtmodus ohne
  Anmeldung.
- Schutzhülle `kontor.schutz`: Netzbeschränkung, 401/303 ohne Sitzung, Größengrenzen (auch chunked),
  Sicherheitsköpfe mit CSP an jeder Antwort, `no-store`; Eingabehärtung (tiefes JSON, übergroße Ganzzahlen → 422).
- Betrieb: `kontor.betrieb` mit `kontor.service` (Härtung, `LoadCredentialEncrypted`), Sicherungs-Service und
  -Timer, sysusers, `kontor.env`, Drop-in; `python -m kontor` ohne Argumente (D-086); Logging nach stderr;
  `GET /api/gesundheit`; sauberes Beenden mit Frist und WAL-Checkpoint (D-088); `sichere_in_verzeichnis` und
  `python -m kontor.sicherung` mit Aufbewahrung je Modus.
- Leistung (D-089), Datenbankschema 8 mit Migration ohne Datenverlust.
- Weboberfläche (D-090): Anmeldeseite mit Einrichtung und Sperrhinweis, Abmelden, Passwort ändern, CSRF in
  allen schreibenden Anfragen, responsiv. README: Installation als systemd-Dienst im LXC Schritt für Schritt,
  Login einrichten, Mock-Modus.

### Einschränkungen

- Die systemd-Units sind nur statisch (Tests) geprüft, nicht in einem echten Proxmox-LXC gestartet.
- Kein TLS im Anwendungsserver (sicherheit.md 12); HTTPS nur über einen Reverse-Proxy.
- `POST /api/benachrichtigungen/test` (D-076) steht nicht in `openapi.yaml` (W-005, offen für den Test-Thread).
- Die Leistungswerte stammen von einer geteilten Testmaschine; sie schwanken, liegen aber überall deutlich
  unter den Grenzen.

## Meilenstein 6 (echte Anbindungen und Benachrichtigungen)

Stand: 2026-11-09, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `5cbf031`** („M6: ERGEBNIS.md (Abschnitt M6)“, enthält `fe5f1ad`
  „Vorwarnungstest prüft auch nach dem Lesen“), nach `git pull` im Lese-Klon unmittelbar vor dem
  Abschlusslauf.
- Aufruf im Wurzelverzeichnis des Lese-Klons gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, SQLite 3.53.1, fints 5.0.1, cryptography 50.0.1, Hypothesis-Profil
  `standard`. Wegen der 10-Minuten-Grenze je Aufruf in vier Teilen:
  `-m "m6 or not (m1 or m2 or m3 or m4 or m5 or m9)"`, `-m "m1 and not m6"`, `-m "(m2 or m3) and not m6"`,
  `-m "(m4 or m5 or m9) and not (m1 or m2 or m3 or m6)"`; zusammen alle 1994 gesammelten Tests.
- Tests für `m7`/`m8`: keine vorhanden (0 gesammelt).

| Auswahl | gesamt | bestanden | fehlgeschlagen | Fehler |
| --- | ---: | ---: | ---: | ---: |
| vollständig (alle gesammelten Tests) | 1994 | 1993 | 1 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 225 | 1 (W-004) | 0 |
| davon `-m m3` | 245 | 245 | 0 | 0 |
| davon `-m m4` (inkl. `langsam`) | 227 | 227 | 0 | 0 |
| davon `-m m5` | 212 | 212 | 0 | 0 |
| davon `-m m6` (inkl. `tests/attrappen`, M6-Generatortests) | 273 | 273 | 0 | 0 |
| davon `-m m9` | 56 | 56 | 0 | 0 |
| ohne Meilenstein-Marker (Generator, Spezifikation) | 81 | 81 | 0 | 0 |
| `m7`, `m8` | 0 | – | – | – |

**Einziger Fehlschlag:** `tests/app/m2/test_m2_sync.py::test_laeufe_und_status` – der M2-Test vergleicht
`GET /api/sync/status` exakt und verträgt das in M6 verlangte Feld `pin_quelle` nicht (fints.md 5,
synchronisation.md 18.1; der M6-Test `test_vorgabe_eingabe` verlangt es auch bei `eingabe`). Dokumentiert als
**W-004** in `WIDERSPRUECHE.md`; umgesetzt ist die Spezifikation.

### Eigene Tests (kontor-app)

`python -m pytest tests`: 68 bestanden. Neu: `tests/test_m6_eigen.py` (Migration der App-Datenbank von
Schemaversion 6 auf 7 – frühere Benachrichtigungen gelten als `keine`; Sicherung der Schemaversion 2 ohne
Postfächer einspielbar; Spiegel bleibt beim Einspielen mit gleicher Adresse; Zugriffsprotokoll ohne
Abfrageteil; Logger `fints` gibt nichts weiter; MT940 mit `RC`/`RD` und Buchungsjahr; camt mit Vormerkung und
Referenz; Test-Benachrichtigung) und der Playwright-Rauchtest `tests/test_browser_m6.py` (Chrome headless,
echter Server auf freiem Loopback-Port): Anbindungen im Mock-Modus auf Desktop- und Handybreite
(Geheimnis setzen ohne Anzeige, Test-Benachrichtigung, Postfach anlegen, Mail-Abruf und -Liste, Link
`/mail/postfaecher/<id>`, kein waagerechtes Scrollen) und im Echtmodus der Start einer OAuth2-Anmeldung
(Autorisierungs-URL wird nur angezeigt) mit abgelehnter Umleitungs-URL. Alle Server-, Browser- und
Attrappen-Prozesse enden mit den Tests; es läuft kein Prozess weiter.

### Umgesetzt

- FinTS-Plugin über python-fints (D-069–D-071): Konten aus HIUPD/HISPA, camt.052.001.08 bevorzugt, MT940
  als Rückfall, Aufsetzpunkte, Hash-Kennungen, QR-TAN im offenen Dialog, Fehlerabbildung nach fints.md 3.6,
  nur lesende Segmente, Logger `fints` stillgelegt; PIN aus der Eingabe oder aus `$CREDENTIALS_DIRECTORY` mit
  Sperre nach Ablehnung (D-079).
- IMAP-Plugin mit XOAUTH2 (nur `EXAMINE`/`BODY.PEEK[]`), OAuth2 mit PKCE, Token-Erneuerung, Vorwarnung,
  proaktiver/reaktiver Ablauf und Widerruf mit je einer Benachrichtigung, paralleler Abruf, Spiegel
  (D-077, D-078).
- Benachrichtigungen: Plugins `keins`/`mock`/`ntfy`, Zustellung mit Wiederholung und Höchstzahl, TAN-Push mit
  Link, TAN-Erinnerungen (D-074, D-082); App-Erweiterung `POST /api/benachrichtigungen/test` (D-076).
- Geheimnisspeicher AES-256-GCM (D-073); ausgehende Verbindungen ohne Umleitungen und Proxy, eigene
  Vertrauensanker (D-072); Zugriffsprotokoll ohne Abfrageteil (D-080).
- Postfächer im Protokoll und in der Sicherung (Schemaversion 3), Betriebszustand je Adresse (D-075);
  Datenbankschema 7 mit Migration ohne Datenverlust.
- Weboberfläche „Anbindungen“ und „Mails“ (D-081); README mit Betrieb über systemd-creds, eigenem
  Google-Cloud-Projekt und ntfy.

### Einschränkungen

- Geprüft nur gegen die lokalen Attrappen aus kontor-tests und eigene Loopback-Server; keine echte Bank, kein
  Gmail/Google, kein ntfy.sh angesprochen.
- Starke Kundenauthentifizierung schon beim FinTS-Dialogbeginn und entkoppelte App-Freigaben (3955) werden
  nicht unterstützt (`BankFehler`, D-071, fints.md 3.5).
- Der Mail-Abgleich mit Sammelbuchungen ist nicht Teil von M6 (K 1).
- Die Test-Benachrichtigung ist kein Teil des Vertrags (`openapi.yaml`); beim Mock-Plugin wird sie nur
  bestätigt, nicht in die Zustellliste eingetragen.

## Meilenstein 5 (wiederkehrende Buchungen, Kredite, Berichte, Export)

Stand: 2026-11-09, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `8cece3c`** („M5: E-111 (Schlussrate 0, Probelauf ohne Konto
  Korrekturen), TESTS_AUSFUEHREN.md und CLAUDE.md für M5“), nach `git pull` im Lese-Klon unmittelbar vor
  dem Abschlusslauf.
- Aufruf im Wurzelverzeichnis des Lese-Klons gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, SQLite 3.53, reportlab 5.0.1, pypdf 6.17, Hypothesis-Profil
  `standard`. Wegen der 10-Minuten-Grenze je Aufruf in zwei Teilen:
  `python -m pytest -p no:cacheprovider -m "not m4 and not m5 and not m9 and not m6 and not m7 and not m8"`
  und `python -m pytest -p no:cacheprovider -m "(m4 or m5 or m9) and not m6 and not m7 and not m8"`;
  zusammen genau die 1719 Tests des Maßstabs `-m "not m6 and not m7 and not m8"`.

| Auswahl | gesamt | bestanden | fehlgeschlagen | Fehler |
| --- | ---: | ---: | ---: | ---: |
| Maßstab (ohne m6–m8) | 1719 | 1719 | 0 | 0 |
| vollständig (alle gesammelten Tests) | 1719 | 1719 | 0 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |
| davon `-m m3` | 245 | 245 | 0 | 0 |
| davon `-m m4` (inkl. `langsam`) | 227 | 227 | 0 | 0 |
| davon `-m m5` (inkl. M5-Generatortests) | 212 | 212 | 0 | 0 |
| davon `-m m9` | 56 | 56 | 0 | 0 |
| davon `m6`–`m8` (nicht beauftragt) | 0 | – | – | – |

(Die übrigen 79 Tests sind Generator- und Spezifikationstests ohne Meilenstein-Marker; alle grün.)
**Keine Fehlschläge, keine offenen Widersprüche.** W-003 (entfallende Nullrate gegen Summeninvariante des
Tilgungsplans, gefunden von `test_zufaellige_plaene_gleich_orakel` gegen Commit `dbe9a7c`) hat der
Test-Thread mit E-111 behoben; umgesetzt (D-068) und als erledigt markiert.

### Eigene Tests (kontor-app)

`python -m pytest tests`: 57 bestanden, neu `tests/test_m5_eigen.py` (Migration der App-Datenbank von
Schemaversion 5 auf 6 ohne Datenverlust, Einspielen einer Sicherung der Schemaversion 1 ohne
Kredittabellen, PDF ohne vorgetäuschte Marken, Schlussrate 0) und der Playwright-Rauchtest
`tests/test_browser_m5.py` (Chrome headless, Desktop und Handy): wiederkehrende Buchungen mit
Jahreskosten und Prüfung, Kredit über den Dialog anlegen (Sollzins in Prozent → Millionstel), Tilgungsplan,
Raten zuordnen (Probelauf, dann aufteilen), Jahresabgleich-Dialog (Vorschlag ändert nichts, dann
bestätigen), Kontostandsverlauf als SVG-Liniendiagramm mit Legende und Tooltip, CSV/PDF-Export-Knöpfe,
keine horizontale Überbreite. Zusätzlich manuell geprüft: PDF mit 5 000 Buchungen (5 000 Marken, eine
Anzahlzeile, < 1 s), Bildschirmfotos von Diagramm, Kreditseite und Handy-Ansicht. Gestartete Server und
Browser wurden beendet.

### Umgesetzt

- Kredite (`kontor/kredite.py`): CRUD mit Prüfreihenfolge, Anfangsbuchung, Tilgungsplan (30/360, act/360,
  act/365, Sondertilgungen, Zins je Rate kaufmännisch gerundet, nur Ganzzahlen), `kontor.kredite.tilgungsplan`,
  Ratenerkennung als Stufe 0 der Synchronisation (`buchungen_kredit`), `…/zuordnen`, Jahresabgleich mit
  genau einer Korrekturbuchung und Status `abgeglichen`, Bezüge (Konten nicht löschbar, Zuordnung entfällt
  mit der Buchung), Protokoll (Objekt `kredit`, Quelle `kredit`) und Rückgängig.
- Wiederkehrende Buchungen (`kontor/wiederkehrend.py`): Übersicht zum Stichtag, Ereignisse, Prüfung auf
  Wunsch und automatisch nach Läufen (`wiederkehrend_automatisch`, `KONTOR_WIEDERKEHREND_AUTOMATISCH`).
- Berichte (`kontor/berichte.py`) und Export (`kontor/export.py`, CSV verlustfrei, PDF mit reportlab).
- Sicherung: Schemaversion 2 mit Kredittabellen, `kredit` nur bei Vorhandensein, Version 1 weiter lesbar.
- App-Datenbank Schemaversion 6 (Kredittabellen, zwei Spalten in `sync_lauf_konto`), Migration ohne
  Datenverlust.
- Weboberfläche: „Wiederkehrende Buchungen“, „Kredite“ (Plan, Zuordnen, Jahresabgleich-Dialog),
  „Berichte“ (Liniendiagramm, Einnahmen/Ausgaben), Export-Knöpfe in jeder Buchungsliste (D-067).
- README, CLAUDE.md, ENTSCHEIDUNGEN.md (D-059 bis D-068).

### Einschränkungen

- Hypothesis lief nur im Profil `standard` (nicht `gruendlich`).
- Neue Abhängigkeit `reportlab` (reine Python-Bibliothek, in `pyproject.toml`); Zeichen außerhalb der
  Standardschrift erscheinen im PDF als Ersatzzeichen (zulässig laut berichte.md 5).
- Die automatische Prüfung bei abgebrochenen Läufen greift beim Abbrechen bzw. Ablaufen einer TAN über
  `ablauf_pruefen`; ein Ablauf, der erst beim Beantworten der TAN festgestellt wird, prüft nicht erneut.

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
