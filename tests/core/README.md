# Core-Tests

Schnelle Tests für die Entwicklungsschleife (TDD). Aufruf: `python -m pytest tests/core`.

- **Vor dem Feature:** Die Core-Tests eines Features entstehen vor dem Feature-Code und werden als eigener
  Commit eingecheckt („<feature>: Core-Tests“). Danach wird gegen sie entwickelt.
- **Schnell:** Der ganze Ordner bleibt unter 30 Sekunden; darüber schlägt der Lauf fehl. Kein Browser, kein
  uvicorn, kein Netz, keine Wartezeiten, keine großen Fixtures. REST über `client`/`mock_client` aus
  `tests/conftest.py`.
- **Je Feature eine Datei** `test_<feature>.py`. Sie prüft das Verhalten an der Schnittstelle (REST,
  öffentliche Funktionen), nicht die Bauweise.
- **Test in der Schleife geändert:** Muss ein schon eingecheckter Core-Test angepasst werden, weil er falsch
  war oder sich die Anforderung geändert hat, bekommt die Änderung einen Eintrag in `tests/core/AENDERUNGEN.md`
  (Datum, Test, was vorher erwartet wurde, was jetzt, warum).
- Alles Langsame (Browser, Zufallstests, große Datenmengen) gehört nach `tests/` und läuft in der Gesamtsuite.
