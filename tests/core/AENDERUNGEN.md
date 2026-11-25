# Änderungen an eingecheckten Core-Tests

Ein Eintrag je Änderung eines schon eingecheckten Core-Tests während der Entwicklung (siehe `README.md`).

| Datum | Feature | Test | vorher erwartet | jetzt erwartet | Grund |
| --- | --- | --- | --- | --- | --- |
| 2026-11-24 | testinstanz-platz | `test_testinstanz_platz.py` (alle, über `_haupt`) | 300 Füllzeilen | 1000 Füllzeilen | `test_alte_kopie_zaehlt_als_frei` rechnet mit Anteilen der Datenbankgröße; bei der sehr kleinen Datei überwog der feste Spielraum der Platzprüfung. Erwartung unverändert, nur realistischere Größe |
| 2026-11-24 | status-farben | `test_status_farben.py`: Zuordnung von Hand (einzeln, mehrfach, Bestandskonto, Splits), Vorschlag annehmen | Buchung wird `vorlaeufig`; vorläufige bleibt | Buchung wird `bestaetigt`, auch aus `vorlaeufig` | Anforderung präzisiert (D-261): von Hand zugeordnet heißt bestätigt |
| 2026-11-24 | status-farben | `test_status_farben.py`: offener Vorschlag, Ablehnen, Altbestand | Vorschlag lässt `importiert`; Altbestand mit Vorschlag bleibt `importiert` | Vorschlag macht `vorlaeufig`, Ablehnen wieder `importiert`; Altbestand mit Vorschlag wird `vorlaeufig` | Anforderung präzisiert (D-261): automatisch zugeordnet heißt vorläufig |
| 2026-11-25 | ausgleich-aufraeumen | `test_ausgleich_aufraeumen.py` (Fixture `bank`, Test zum Zusammenführen) | Fixture legte den Lauf mit Spalten an, die es nicht gibt; Test las `saldo` aus `GET /api/konten/{id}` | Lauf mit den Spalten des Schemas; der Saldo wird nur über die Buchungsliste geprüft | Der Test war falsch (lief vor dem Feature-Code nie bis zur Erwartung); die Erwartungen an das Verhalten sind unverändert |
