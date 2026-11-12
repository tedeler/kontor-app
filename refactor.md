# Codequalität und Refactoring

Diese Analyse wird **vor jedem Meilenstein wiederholt** (siehe `CLAUDE.md`,
Abschnitt „Codequalität vor jedem Meilenstein“). Jeder Lauf ergänzt die
Kennzahlentabelle um eine Zeile und aktualisiert die Maßnahmenliste;
erledigte Maßnahmen werden abgehakt, nicht gelöscht.

## Ablauf der Analyse

Im Wurzelverzeichnis von kontor-app (Werkzeuge über `uvx`, nichts wird
installiert oder ins Projekt eingetragen):

```bash
# Lint (Fehler, Komplexität, Modernisierung); Zeilenlänge mit 120 bewerten
uvx ruff check --select E,F,W,B,C90,SIM,UP,PL --line-length 120 --statistics src
# Typannotationen, breite Ausnahmen, SQL aus Zeichenketten
uvx ruff check --select ANN,BLE,S608 --statistics src
# Zyklomatische Komplexität: alle Funktionen ab Note D
uvx radon cc -s -n D src
# Typprüfung
uvx mypy --ignore-missing-imports src | tail -1
# Umfang
find src -name '*.py' | xargs wc -l | tail -1
wc -l src/kontor/web/static/app.js
```

Danach Stichproben in den auffälligsten Funktionen lesen und die Bewertung
unten fortschreiben. Hinweise von `S608` sind nur dann echte Funde, wenn
Werte (nicht nur Platzhalterlisten `?, ?, …` oder feste Spaltennamen) in
SQL-Text eingesetzt werden.

## Kennzahlen

| Datum | Stand (kontor-app) | Meilenstein davor | Python-Zeilen | `app.js`-Zeilen | ruff-Funde¹ | C901 | radon D/E/F | mypy-Fehler | Parameter ohne Annotation | echte SQL-Funde |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-11-09 | `b04091f` | M7 (in Arbeit) | 13 811 | 2 846 | 305 | 43 | 36 | 121 | 361 | 0 |
| 2026-11-09 | `12cadb0` | M7 (abgeschlossen), vor M8 | 13 823 | 2 922 | 334 | 43 | 37 | 119 | 361 | 0 |
| 2026-11-09 | `a15f0f0` | M8 (abgeschlossen), vor M10 | 13 818 | 3 584² | 334 | 43 | 37 | 119 | 361 | 0 |
| 2026-11-09 | `99c2c95` | M10 (abgeschlossen), vor M11 | 14 351 | 3 584² | 337 | 44 | 36 | 119 | 361 | 0 |
| 2026-11-10 | `4487cff` | M11 (abgeschlossen), vor Versionierung | 14 612 | 3 744² | 349 | 44 | 36 | 125 | 367 | 0 |
| 2026-11-10 | `d2246ca` | M13 (abgeschlossen), vor M12 | 14 740 | 3 770² | 352 | 44 | 36 | 125 | 367 | 0 |
| 2026-11-10 | `d308b96` | M12 (abgeschlossen), vor M14 (Sammelpaket) | 14 801 | 3 927² | 352 | 44 | 37 | 125 | 368 | 0 |
| 2026-11-11 | `7e3719c` | M15 und Update (auf main), vor M16 (Tabs/Gegenbuchung) | 15 423 | 4 831² ³ | 360 | 45 | 37 | 127 | 378 | 0 |
| 2026-11-11 | `698d2fa` | M16, M17 und Nachzug (0.09), vor Dokumente | 15 734 | 4 997² | 363 | 46 | 38 | 127 | 379 | 0 |
| 2026-11-12 | `5191417` | Dokumente (Branch, noch nicht gemergt), vor Mail-Abgleich | 16 425 | 5 420² | 380 | 46 | 40 | 134 | 399 | 0 |
| 2026-11-12 | `698d2fa` | M16, M17 (auf main, Version 0.09), vor ALF-BanCo-Import | 15 734 | 4 997² | 363 | 46 | 38 | 127 | 379 | 0 |

¹ `--select E,F,W,B,C90,SIM,UP,PL --line-length 120`.
² Ab M8 Summe der ES-Module `src/kontor/web/oeffentlich/app/*.js` (R-07, `app.js` gibt es nicht mehr).
³ Gemessen auf `feature/tabs-gegenbuchung` (Python identisch mit `7e3719c`; JS einschließlich der rund 330 Zeilen von M16).

## Bewertung (2026-11-09)

**Gesamt: solide bis gut.** Fachlich und sicherheitlich sorgfältig,
strukturell an einigen Stellen über die Wartbarkeitsgrenze gewachsen.

### Stärken

- Fachliche Korrektheit durch kontor-tests abgesichert (M6: 1993/1994,
  einziger Fehlschlag als W-004 dokumentiert), ergänzt durch eigene Tests
  und Playwright-Rauchtests.
- Beträge durchgehend ganze Cent; Lernmodell mit `Fraction`.
- Geheimnisse sauber abgeschirmt (`raise … from None`, Logfilter,
  `fints`-Logger stillgelegt); Schreibzugriffe zentral über
  `protokoll.protokolliert(...)`.
- SQL durchgehend parametrisiert; die 58 `S608`-Hinweise sind Fehlalarme.
- Breite `except Exception` (23 Stellen) fast alle begründet und kommentiert.
- Oberfläche ohne `innerHTML` (DOM-APIs, kaum XSS-Fläche).
- Kommentare mit Fundstellen der Spezifikation; Entscheidungen und
  Widersprüche dokumentiert.

### Schwächen

1. **Funktionslänge und Verzweigung.** 43 Funktionen über der
   C901-Grenze, 36 mit radon-Note D oder schlechter. Die schlimmsten:

   | Funktion | radon |
   | --- | ---: |
   | `validierung._pruefe_wert` | F (49) |
   | `sync.SyncDienst._abgleichen_und_buchen` | F (42) |
   | `vorlagen.vorlage_koerper` | F (41) |
   | `pflege.erfassen` | E (40) |
   | `sicherung._inhalt_pruefen` | E (40) |
   | `pflege._loeschen_ausfuehren` | E (36) |
   | `kredite.parameter_pruefen` | D (28) |
   | `buch.buchungsliste` | D (27) |
   | `schutz.Schutz._bearbeiten` | D (26) |
   | `sicherung._zip_lesen` | D (26) |

2. **`app.py`: `create_app` ist eine Funktion mit rund 1 170 Zeilen**, alle
   Endpunkte als Closures. Folge u. a.: der Name `abmelden` ist doppelt
   definiert (`app.py:734` Postfach, `app.py:1333` Sitzung) – funktioniert
   nur, weil der Decorator vor dem Überschreiben registriert.
3. **Typisierung lückenhaft:** 361 Parameter ohne Annotation (typisch
   `con`, `z: dict`, `offen: list`), 121 mypy-Fehler (v. a. `arg-type`,
   `attr-defined`, `union-attr`).
4. **Keine Werkzeugkonfiguration:** weder ruff noch mypy in
   `pyproject.toml`, keine CI.
5. **Frontend monolithisch:** `app.js` mit 2 846 Zeilen in einer Datei.
6. **Kleinigkeiten:** ungenutzter Import (`sync.py:22`), veraltete
   Projektbeschreibung in `pyproject.toml` („Meilensteine 1–6 und 9“),
   88 magische Werte in Vergleichen, 15× `dt.timezone.utc` statt `dt.UTC`,
   wenige Docstrings an öffentlichen Funktionen.

## Fortschreibung vor M8 (2026-11-09, Stand `12cadb0`)

- **ruff-Funde 305 → 334 (+29), radon D/E/F 36 → 37:** Ursache ist der Abschluss von M7
  nach der ersten Messung (Schutzhülle `schutz.py`, `__main__.py`, Kommandozeilen der
  zeitgesteuerten Sicherung): überwiegend `PLR2004` (magische Werte bei HTTP-Statuscodes und
  Größengrenzen) und `PLR0911/0912` in `Schutz._bearbeiten`; neue D-Funktion ist die
  Aufbewahrungsregel der Sicherung. Keine neuen breiten `except` ohne Begründung, keine echten
  SQL-Funde. Maßnahme: in R-01 `PLR2004` für HTTP-Statuscodes über benannte Konstanten
  (`http.HTTPStatus`) abbauen (**R-08**).
- **mypy 121 → 119:** leicht verbessert.
- **M8 betrifft vor allem die Oberfläche:** `app.js` wächst durch M8 stark. R-07 (Aufteilung in
  ES-Module) wird mit M8 umgesetzt, damit die Oberfläche nicht als eine Datei mit mehreren
  tausend Zeilen weiterwächst.

## Fortschreibung vor M10 (2026-11-09, Stand `a15f0f0`)

- **Python-Kennzahlen unverändert** gegenüber der Messung vor M8 (ruff 334, C901 43, radon D/E/F 37,
  mypy 119, 361 Parameter ohne Annotation, keine echten SQL-Funde, 2 begründete `BLE001`). M8 hat fast
  nur die Oberfläche geändert; die Python-Zeilen sind leicht gesunken (13 823 → 13 818).
- **Oberfläche:** 3 584 Zeilen in sechs ES-Modulen statt einer Datei (R-07 erledigt); größtes Modul ist
  `seiten.js`.
- **M10 (AqBanking-Plugin)** kommt als eigenes Modul `plugins/aqbanking.py` dazu; es soll die Grenze
  C901 ≤ 15 einhalten (Auswertung der AqBanking-Ausgabe in kleine Funktionen zerlegt) und vollständig
  annotiert sein. Keine neue Maßnahme nötig.

## Fortschreibung vor M11 (2026-11-09, Stand `99c2c95`)

- **ruff-Funde 334 → 337 (+3), C901 43 → 44:** alle drei aus dem neuen Modul `plugins/aqbanking.py`
  (M10): `_werte_lesen` mit C901 11 (unter der Projektgrenze 15, eine Verzweigung je Feld der
  AqBanking-Ausgabe), ein `PLR0913` (sechs Parameter beim Unterprozessaufruf) und ein weiterer Hinweis
  derselben Art. Keine Maßnahme nötig; das Modul ist vollständig annotiert (Parameter ohne Annotation
  unverändert 361, mypy unverändert 119).
- **radon D/E/F 37 → 36:** gleich geblieben bzw. leicht besser (Zählweise `-n D`, eine Funktion knapp
  unter D gerutscht); keine neue D-Funktion.
- **Keine echten SQL-Funde, keine neuen breiten `except`** (weiterhin 2 begründete `BLE001`).
- **M11** berührt `sync._abgleichen_und_buchen` nicht direkt: Der Saldoabgleich kommt als eigene
  Funktion nach der Verarbeitung eines Bankkontos dazu (C901 ≤ 15), statt die F-Funktion weiter
  wachsen zu lassen (R-04 bleibt offen). Der Filter `unterkonten` in `buch.buchungsliste` (D) wird als
  Hilfsfunktion für die Kontenmenge ergänzt.

## Maßnahmen

Reihenfolge nach Nutzen. Jede Maßnahme als eigener kleiner Commit; nach
jedem Schritt muss die Testsuite aus kontor-tests unverändert grün bleiben
(Verhalten ändert sich nicht).

- [ ] **R-01 Werkzeuge einrichten:** `[tool.ruff]` und `[tool.mypy]` in
  `pyproject.toml` (Zeilenlänge 120, Regelauswahl wie oben, Ausnahmen
  begründet). Kleinigkeiten aus Punkt 6 mitbeheben.
- [ ] **R-02 Typen für die Datenbankschicht:** `con: sqlite3.Connection`
  überall annotieren; mypy-Fehler schrittweise abbauen, Ziel 0.
- [ ] **R-03 `create_app` aufteilen:** je Bereich ein `APIRouter`
  (Buchungen/Konten, Regeln/Vorlagen, Sync, Mail, Kredite/Berichte,
  Sicherung, Anmeldung); gemeinsame Helfer (`endpunkt`, `koerper`,
  `lesen`, `aendern`) in ein eigenes Modul. Doppelten Namen `abmelden`
  auflösen.
- [ ] **R-04 `_abgleichen_und_buchen` zerlegen:** Dublettenbewertung, je
  eine Funktion je Stufe (Kreditrate → Vorlage → Regel →
  Standardkategorie → Lernmodell → Unkategorisiert) und das Anlegen.
- [ ] **R-05 `validierung._pruefe_wert`:** Tabelle von Prüffunktionen je
  Typ statt `if`-Kette.
- [ ] **R-06 Übrige E/F-Funktionen** (`vorlage_koerper`, `erfassen`,
  `_inhalt_pruefen`, `_loeschen_ausfuehren`) in benannte Teilschritte
  zerlegen.
- [x] **R-07 `app.js` in ES-Module** (M8, D-091) je Ansicht aufteilen (ohne Bundler,
  `<script type="module">`, weiterhin ohne externe Ressourcen).
- [ ] **R-08 Magische Statuscodes** in `schutz.py`/`app.py` durch `http.HTTPStatus` ersetzen.
- [ ] **R-09 Rückgabetyp `Umsatzliste` (M11):** mypy-Fehler stiegen von 119 auf 125, weil
  `umsaetze()` in `plugins/fints.py` (und weiteren Plugins) Listen statt `Umsatzliste` zurückgibt bzw. so
  annotiert ist; Annotationen angleichen (verhaltensneutral). Ruff-Funde und Parameter ohne Annotation stiegen
  mit dem M11-Umfang (+261 Zeilen) leicht; keine neuen breiten `except`, keine echten SQL-Funde.

Neue Funktionen sollen die Grenze C901 ≤ 15 einhalten; Überschreitungen nur
mit Begründung im Code.

### Fortschreibung vor M12 (2026-11-10, Stand `d2246ca`)

Gegenüber `4487cff` stiegen nur die ruff-Funde um 3 (`PLC0415`, Importe innerhalb von Funktionen in
`version.py`/`release.py` aus der Versionierung, gewollt: die Release-Kommandozeile lädt nichts unnötig). C901,
radon D/E/F, mypy-Fehler und Parameter ohne Annotation unverändert; keine neuen breiten `except` (die zwei
`BLE001` in `app.py` bestehen seit M6 und sind begründet), keine echten SQL-Funde. Keine neue Maßnahme; R-03
(doppelter Name `abmelden`) bleibt offen.

### Fortschreibung vor dem Sammelpaket (2026-11-10, Stand `d308b96`)

Gegenüber `d2246ca` stieg radon D/E/F um 1: `buch.mehrfach_aendern` (M12) hat Note D (23), weil Validierung,
die zwei Sperrprüfungen (17.2 Schritt 3–4) und die Wirkung je Feld in einer Funktion stehen; C901 bleibt bei 44,
da ruff die Funktion knapp unter der Grenze sieht. Maßnahme **R-10**. Ein Parameter ohne Annotation mehr (M12);
ruff-Funde, mypy-Fehler unverändert, keine neuen breiten `except`, keine echten SQL-Funde.

- [ ] **R-10 `buch.mehrfach_aendern` zerlegen:** Sperrprüfungen (gesperrt / bestätigungspflichtig) als eigene
  Funktionen, die auch künftige Mehrfach-Operationen nutzen.

### Fortschreibung vor M16 (2026-11-11, Stand `7e3719c`)

Nachgeholt auf dem Feature-Branch: die ersten M16-Commits (nur Oberfläche) entstanden in der iterativen Phase vor
dieser Analyse; der Python-Code ist auf dem Branch unverändert gegenüber `7e3719c`. Gegenüber `d308b96` kamen
M15 (`verschieben.py`, Rückgängig bis, Kontenanlage) und das Update-Feature (`aktualisierung.py`) hinzu
(+622 Python-Zeilen). C901 stieg um 1 (`aktualisierung.ausfuehren`, 11), mypy um 2 (Argumenttyp in
`aktualisierung.py` und bei der Konfiguration), ruff-Funde um 8 und Parameter ohne Annotation um 10 mit dem
Umfang. radon D/E/F unverändert, keine neuen breiten `except` (weiter zwei begründete `BLE001`), keine echten
SQL-Funde. Maßnahme **R-11**. M16 selbst bringt nur die ES-Module `tabs.js` (neu) und Ergänzungen in `haupt.js`
und `konto.js`; neue Funktionen bleiben klein (größte: `zeigen` in `haupt.js`, als Router bewusst eine Funktion).

- [ ] **R-11 Typen in `aktualisierung.py` angleichen** (mypy-Fehler bei `ausfuehren`, verhaltensneutral) und
  `ausfuehren` in Teilschritte zerlegen (C901 11).

### Fortschreibung vor dem Feature „Dokumente“ (2026-11-11, Stand `698d2fa`)

Gegenüber `7e3719c` kamen M16 (neue Kette wiederkehrender Buchungen mit Begründung, +311 Python-Zeilen), M17
(Tabs, Gegenbuchung) und der Nachzug (D-121, D-122, nur Oberfläche) hinzu. C901 und radon D/E/F stiegen um je 1:
`wiederkehrend._schritt_text` (radon D 29, C901 11) baut die Begründungstexte aller Schrittarten in einer
Verzweigung; `_ereignisse` (D 22) war schon vorher gezählt. mypy unverändert, keine neuen breiten `except`, keine
echten SQL-Funde. Maßnahme **R-12**.

- [ ] **R-12 `wiederkehrend._schritt_text` in eine Tabelle je Schrittart zerlegen** (verhaltensneutral,
  Maßstab die M16-Tests).

### Fortschreibung vor dem Feature „Mail-Abgleich“ (2026-11-12, Stand `5191417`)

Gemessen auf `feature/dokumente` (Basis des Branches `feature/mail-abgleich`). Gegenüber `698d2fa` kamen
`dokumente.py` (+477 Zeilen), die Mail-Rohfassung und der Dokumentbetrachter hinzu. Ruff-Funde +17, Parameter ohne
Annotation +20 und mypy +7 stammen überwiegend aus `dokumente.py` (Hilfsfunktionen der Mailzerlegung ohne
Annotationen, `email.message`-Typen); radon D/E/F +2 (C901 unverändert 46). Keine neuen breiten `except` ohne
Begründung, keine echten SQL-Funde. Maßnahme **R-13**; R-03 (doppelter Name `abmelden`, F811) bleibt offen.

- [ ] **R-13 `dokumente.py` annotieren** (Mailzerlegung mit `EmailMessage`/`Message`-Typen, verhaltensneutral) und
  die mypy-Fehler dort beheben.
### Fortschreibung vor dem ALF-BanCo-Import (2026-11-12, Stand `698d2fa`)

Gegenüber `7e3719c` kam die neue Erkennungskette wiederkehrender Buchungen mit Begründung (M16) hinzu
(+311 Python-Zeilen, fast alle in `wiederkehrend.py`). C901 und radon D/E/F stiegen je um 1:
`wiederkehrend._schritt_text` (radon D, 29) baut den deutschen Satz je Schritt der Kette in einer langen
Fallunterscheidung. ruff-Funde +3 und Parameter ohne Annotation +1 mit dem Umfang; mypy unverändert, keine neuen
breiten `except`, keine echten SQL-Funde. Maßnahme **R-12**. Der Import selbst kommt als eigenes Modul
`importer/alfbanco.py`; Lesen (QIF-Zerlegung) und Anwenden werden in kleine Funktionen getrennt (Ziel C901 ≤ 15).

- [ ] **R-12 `wiederkehrend._schritt_text` als Tabelle je Schrittart** (Textbausteine je `art`, verhaltensneutral;
  Maßstab die M16-Tests).
