# Tests von Kontor

Spezifikation, Tests und Anwendungscode liegen gemeinsam in diesem Repository (seit dem Testumbau vom 2026-11-23,
D-253; das frühere Repository kontor-tests ist aufgegeben). Ein Thread schreibt Tests und Code.

## Regeln

- Neue Features: zuerst Core-Tests (`tests/core/test_<feature>.py`, eigener Commit vor dem Feature-Code), dann TDD.
  Muss ein Core-Test in der Schleife angepasst werden, steht das in `tests/core/AENDERUNGEN.md`.
- Ändert ein Feature bestehendes Verhalten, werden die betroffenen Tests in `tests/` und `gesamt-tests/` angepasst
  und in `gesamt-tests/AENDERUNGEN.md` vermerkt.
- Zeitbudgets: Core-Tests unter 30 Sekunden; die Gesamttests laufen in parallelen CI-Jobs, jeder unter 5 Minuten.
- Die Gesamttests laufen in der CI bei jedem Push auf main, vor dem Release; veröffentlicht wird nur bei Grün.

## Aufbau

| Pfad | Inhalt | läuft |
| --- | --- | --- |
| `spec/` | Spezifikation (Konzept, Testkonzept, `api/`, Meilensteine, Definitionen) | – |
| `tests/core/` | Core-Tests der Entwicklungsschleife, Regeln in `tests/core/README.md` | bei jeder Änderung, CI |
| `tests/` | eigene Tests je Feature; `test_browser*.py` tragen den Marker `browser` | CI |
| `gesamt-tests/` | gekürzte Fassung der früheren Abnahmetests (eigene `pytest.ini`, Fixtures, Generator) | CI |
| `legacy-tests/` | unveränderter Stand von kontor-tests, nur Referenz | nie |

Aufrufe:

```bash
python -m pytest tests/core                                  # Entwicklungsschleife
python -m pytest -n auto -m "not browser and not core" tests # eigene Tests ohne Browser
python -m pytest -n auto -m browser tests                    # eigene Browsertests
cd gesamt-tests && python -m pytest -n auto -m "not browser" # Gesamtsuite ohne Browser
cd gesamt-tests && python -m pytest -n auto -m browser       # Gesamtsuite mit Browser
cd gesamt-tests && python -m pytest -n auto --alle           # auch die abgewählten Tests
cd gesamt-tests && python -m pytest -n auto --teil 1/2       # ein Teil von mehreren gleich großen (CI)
```

## Messung

| Lauf | Tests | Dauer | Rechenzeit |
| --- | --- | --- | --- |
| vorher: legacy-tests, Volllauf | 4288 | 25:20 min | 2996 s |
| vorher: eigene Tests | 589 | 3:18 min | 377 s |
| **jetzt: Job ohne Browser** (Core 2, eigene 500, Gesamtsuite 2971) | 3473 | 6:35 min | etwa 790 s |
| **jetzt: Job mit Browser** (eigene 89, Gesamtsuite 191) | 280 | 4:16 min | etwa 475 s |

Die Zeilen „jetzt“ sind lokal gemessen und fassen die Tests ohne Browser in einem Lauf zusammen. Die Zeiten der
CI-Jobs stehen im Abschnitt „CI“.

## CI

`.github/workflows/release.yml`: bei jedem Push auf main fünf parallele Jobs, danach (nur bei Grün) das Release. Seit 2026-11-28
(D-325) ist der frühere Job `browser` in `browser-eigene` (eigene Browsertests) und `browser-gesamt` (Gesamtsuite mit
Browser) geteilt: zusammen brauchten sie zuletzt 5:34 bis 6:42 min.

Erster grüner Lauf (2026-11-23, Version 0.47), Dauer je Job einschließlich Einrichtung:

| Job | Inhalt | Tests | Dauer |
| --- | --- | --- | --- |
| `eigene` | `tests/core`, eigene Tests ohne Browser | 502 | 1:18 min |
| `gesamt-1` | Gesamtsuite ohne Browser, Teil 1 von 2 | 1516 | 3:15 min |
| `gesamt-2` | Gesamtsuite ohne Browser, Teil 2 von 2 | 1459 | 3:44 min |
| `browser` | eigene Browsertests, Gesamtsuite mit Browser | 280 | 3:51 min |

Bis alle Tests fertig waren, vergingen 3:51 min; mit dem Release danach 4:36 min.

- Im Browser-Job ist ein übersprungener Test ein Fehler (`KONTOR_TESTS_BROWSER_PFLICHT=1`), damit ein fehlender
  Browser nicht unbemerkt bleibt.
- 12 eigene Tests verlangen root und werden in der CI übersprungen (`test_https_skript_eigen.py`,
  `test_testinstanz_skript_eigen.py`); das war schon vor dem Umbau so.
- Wächst ein Job über 5 Minuten: zuerst kürzen oder abwählen; die Gesamtsuite lässt sich mit `--teil K/N` auch in
  mehr Teile schneiden.

### Wohin die Zeit ging

| Ursache | Anteil am Volllauf | Maßnahme |
| --- | --- | --- |
| Browser-, Leistungs- und Großdatentests (618 Tests) | 34 % | Browsertests ausgewählt (unten); `leistung` und `langsam` laufen nicht in der CI |
| Zufallstests mit 40 Beispielen | 22 % | Hypothesis-Profil `schnell` (10 Beispiele) ist die Vorgabe |
| Ein Thread mit Ereignisschleife je REST-Anfrage (Starlette `TestClient`) | etwa 13 % | eine gemeinsame Schleife je Testprozess (`tests/hilfen/api.py`, `tests/conftest.py`) |
| App-Aufbau je Test (etwa 0,1 s: 235 Routen, Schema) | etwa 12 % | unverändert; nur über weniger Tests zu senken |
| übrige Testarbeit | Rest | Auswahl (unten) |

Berichtigung zur ersten Fassung dieses Dokuments: Der App-Aufbau je Test ist mit rund 370 s über alle Tests sehr
wohl ein spürbarer Anteil, nur kein einzelner Engpass.

## Auswahl

`gesamt-tests/abgewaehlt.txt` nennt 998 Tests, die nur mit `--alle` laufen. Auswahlregel:

1. **Ohne Browser (697 abgewählt, 2971 bleiben):** Für jeden Test wurde gemessen, welche Zeilen und Verzweigungen
   von `src/kontor` er ausführt. Behalten wurden alle Tests unter 0,12 s, dann so lange der Test mit den meisten
   neuen Verzweigungen je Sekunde, bis alle 26 501 gemessenen Verzweigungen abgedeckt waren, und schließlich von
   jeder noch nicht vertretenen Testfunktion die schnellste Variante. Von 1720 Testfunktionen entfällt genau eine
   ganz (`m31/test_m31_lernmodell.py::test_lerndaten_laden_und_rueckgaengig`, 8 s); sonst entfallen nur weitere
   Parametervarianten.
2. **Mit Browser (301 abgewählt, 191 bleiben):** Gemessen wurden die ausgeführten JavaScript-Blöcke je Test. Die
   eigenen Browsertests bleiben vollständig; aus der Gesamtsuite bleiben die Tests, die darüber hinaus neue Blöcke
   ausführen (125), und bis zum Zeitbudget weitere Testfunktionen (schnellste zuerst). Alle 3890 gemessenen Blöcke
   bleiben abgedeckt; von 363 Testfunktionen bleiben 188.

Grenze der Methode: Abgedeckter Code ist nicht dasselbe wie geprüftes Verhalten. Ein abgewählter Test kann eine
Aussage prüfen, die kein verbleibender Test prüft, obwohl er denselben Code durchläuft. Die abgewählten Tests
bleiben deshalb im Verzeichnis und sind mit `--alle` jederzeit ausführbar. Die Liste gilt nach Knoten-ID: wird ein
Test umbenannt, läuft er wieder mit.

Nicht übernommen: `tests/_selbstpruefung` (Wegwerf-Referenz und Mutanten; nur in `legacy-tests`).
