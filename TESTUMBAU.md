# Testumbau: Tests im Anwendungs-Repository

Branch `feature/testumbau`. Stand der Messung: 2026-11-23, kontor-app `667af00` (Version 0.46),
kontor-tests `b6f94f1`.

## Beschlossen

- kontor-tests wird aufgegeben. Tests, Fixtures und Generator liegen eingefroren unter `legacy-tests/`
  (nur Referenz, nicht in der CI), die Spezifikation unter `spec/` (`legacy-tests/spec` verweist darauf).
- Neue Features: zuerst Core-Tests (eigener Commit vor dem Feature-Code), dann TDD. Muss ein Core-Test in
  der Schleife angepasst werden, wird das dokumentiert.
- Zeitbudgets: Core-Tests unter 30 Sekunden, Gesamtsuite unter 5 Minuten.
- Die Gesamtsuite läuft nur in der CI auf main.

## Messung (2 Kerne, `-n 2`)

| Lauf | Tests | Dauer | Rechenzeit | Fehlschläge |
| --- | --- | --- | --- | --- |
| legacy-tests, Volllauf `--voll` | 4288 | 25:20 min | 2996 s | 19 |
| legacy-tests, Schnelllauf (ohne Browser, Leistung, große Fixtures; 10 Hypothesis-Beispiele) | 3670 | 11:06 min | 1307 s | 9 |
| eigene Tests `tests/` | 589 | 3:18 min | 377 s | 3 |

Wohin die 2996 s des Volllaufs gehen:

| Anteil | Tests | Rechenzeit | Anteil |
| --- | --- | --- | --- |
| Browser-, Leistungs- und Großdatentests | 618 | 1028 s | 34 % |
| Zufallstests: Mehraufwand des Profils `standard` gegenüber `schnell` | (in 3670 enthalten) | 661 s | 22 % |
| übrige Tests im Schnellprofil | 3670 | 1307 s | 44 % |

- Es gibt keinen einzelnen Engpass. Der App-Aufbau je Test kostet etwa 0,09 s und ist nicht das Problem.
- 31 Tests brauchen je mindestens 10 s und zusammen 639 s; fast alle sind Zufallstests gegen ein Orakel.
- Im Schnellprofil brauchen 220 Tests mindestens 1 s (505 s), 1914 Tests unter 0,2 s (147 s).
- Die eigenen Browsertests (89) brauchen 232 s, die übrigen 500 eigenen Tests 145 s.

## Fehlschläge im Ausgangsstand

Unverändert übernommen, kein Anwendungscode geändert. Ursachen nicht einzeln untersucht.

- legacy-tests (19): `test_mehrfach.py` (4), `test_buchungen.py` (1), `test_plugins.py` (2), `m6/test_m6_paket.py` (1),
  M8-Oberfläche (8), M13-Oberfläche (2), M15-Oberfläche (1). Die Namen passen zu Features, die nach M32
  ohne Abnahmetests gemergt wurden (Zuordnung auf Bestandskonto, Kopfabruf).
- eigene Tests (3): `test_browser.py::test_ueber_fenster`, `test_browser_ausdruck.py::test_tags_im_kontoblatt_bearbeiten`,
  `test_versionierung_eigen.py::test_huelle_zeigt_version_in_der_navigation`.
