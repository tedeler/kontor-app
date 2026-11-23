# Selbstprüfung 2026-11-22 (M32)

Python 3, HYPOTHESIS_PROFILE=standard. Referenzläufe über `python -m tests._selbstpruefung`; die Mutantenläufe
wegen der Laufzeitgrenze (Teile unter 10 Minuten) gezielt auf die Kern-Tests ihres Bereichs, parallel (`-n 8`,
`--maxfail=1`), mit demselben Marker und derselben Referenz.

| Lauf | Erwartung | Ergebnis | Bewertung |
| --- | --- | --- | --- |
| Referenz (ohne Mutant) | alle Kern-Tests grün | 1572 passed, 2471 deselected | OK |
| Referenz mit Zusatzfeldern (E-124) | alle Kern-Tests grün | 1572 passed, 2471 deselected | OK |
| Mutant `m32_kontonamen_doppelt` | mindestens ein Test rot | 1 failed (`test_m4_gnucash_zuordnung.py::test_vorhandenes_konto_hoechstens_einmal`) | OK (erkannt) |
| Mutant `m32_standardkategorie_bleibt` | mindestens ein Test rot | 1 failed (`test_m3_empfaenger.py::test_felder_und_vorgaben`) | OK (erkannt) |
| Mutant `m28_palette_alt` (`test_m8_tastatur.py`) | mindestens ein Test rot | 1 failed, 4 passed | OK (erkannt) |
| Mutant `m28_alt_acht` (`test_m8_tastatur.py`) | mindestens ein Test rot | 1 failed, 4 passed | OK (erkannt) |
| Mutant `m13_navigation_erweitert` (`tests/app/m13`) | mindestens ein Test rot | 1 failed, 24 passed | OK (erkannt) |
| Mutant `regel_prioritaet_umgekehrt` (`test_m2_regeln_anwenden.py -k prioritaet`) | mindestens ein Test rot | 1 failed | OK (erkannt) |
| Mutant `undo_ohne_zustandspruefung` (`test_m3_rueckgaengig.py`) | mindestens ein Test rot | 3 failed, 5 passed | OK (erkannt) |
| Mutant `loeschen_vorschlag_bleibt` (`test_m3_konto_loeschen.py`) | mindestens ein Test rot | 2 failed, 53 passed | OK (erkannt) |
| Mutant `sicherung_pruefsumme_ungeprueft` (`tests/app/m9`) | mindestens ein Test rot | 1 failed, 48 passed, 1 error | OK (erkannt) |

Gesamtergebnis: BESTANDEN (Referenz grün, 9 von 9 Mutanten erkannt). Die Korrekturen zu W-022 bis W-026 (E-313)
betreffen nur M32-Tests (`OHNE_REFERENZ`) und eine zusätzliche 422-Antwort im Schema; die Referenzläufe stammen
vom Stand davor.

## Nachtrag (E-314, W-027 bis W-030)

| Lauf | Ergebnis | Bewertung |
| --- | --- | --- |
| Referenz, `test_m2_regeln_api.py` + `test_m3_konto_loeschen.py` | 90 passed | OK |
| Mutant `loeschen_vorschlag_bleibt` (dieselben Dateien) | 2 failed, 82 passed | OK (erkannt) |
