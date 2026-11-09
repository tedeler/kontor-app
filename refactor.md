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

¹ `--select E,F,W,B,C90,SIM,UP,PL --line-length 120`.
² Ab M8 Summe der ES-Module `src/kontor/web/oeffentlich/app/*.js` (R-07, `app.js` gibt es nicht mehr).

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

Neue Funktionen sollen die Grenze C901 ≤ 15 einhalten; Überschreitungen nur
mit Begründung im Code.
