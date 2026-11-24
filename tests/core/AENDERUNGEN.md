# Änderungen an eingecheckten Core-Tests

Ein Eintrag je Änderung eines schon eingecheckten Core-Tests während der Entwicklung (siehe `README.md`).

| Datum | Feature | Test | vorher erwartet | jetzt erwartet | Grund |
| --- | --- | --- | --- | --- | --- |
| 2026-11-24 | status-farben | `test_status_farben.py`: Zuordnung von Hand (einzeln, mehrfach, Bestandskonto, Splits), Vorschlag annehmen | Buchung wird `vorlaeufig`; vorläufige bleibt | Buchung wird `bestaetigt`, auch aus `vorlaeufig` | Anforderung präzisiert (D-259): von Hand zugeordnet heißt bestätigt |
| 2026-11-24 | status-farben | `test_status_farben.py`: offener Vorschlag, Ablehnen, Altbestand | Vorschlag lässt `importiert`; Altbestand mit Vorschlag bleibt `importiert` | Vorschlag macht `vorlaeufig`, Ablehnen wieder `importiert`; Altbestand mit Vorschlag wird `vorlaeufig` | Anforderung präzisiert (D-259): automatisch zugeordnet heißt vorläufig |
