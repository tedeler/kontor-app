# Änderungen an eingecheckten Core-Tests

Ein Eintrag je Änderung eines schon eingecheckten Core-Tests während der Entwicklung (siehe `README.md`).

| Datum | Feature | Test | vorher erwartet | jetzt erwartet | Grund |
| --- | --- | --- | --- | --- | --- |
| 2026-11-24 | testinstanz-platz | `test_testinstanz_platz.py` (alle, über `_haupt`) | 300 Füllzeilen | 1000 Füllzeilen | `test_alte_kopie_zaehlt_als_frei` rechnet mit Anteilen der Datenbankgröße; bei der sehr kleinen Datei überwog der feste Spielraum der Platzprüfung. Erwartung unverändert, nur realistischere Größe |
