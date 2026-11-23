# kontor-tests

Konzept, Testkonzept, Schnittstellenspezifikation, Testdatengenerator und Tests
für **Kontor**, eine selbst gehostete Finanz-Web-App (Python, FastAPI, SQLite,
Single-Page-Weboberfläche).

| Pfad | Inhalt |
| --- | --- |
| `spec/konzept.md` | Fachkonzept |
| `spec/testkonzept.md` | Testkonzept |
| `spec/api/` | Verbindliche Schnittstellenspezifikation (Datenmodell, Python-API, OpenAPI, Plugins, Entscheidungen) |
| `generator/` | Testdatengenerator mit festem Startwert |
| `fixtures/` | Vom Generator erzeugte Testdateien samt Erwartungsdateien |
| `tests/` | pytest- und Hypothesis-Tests |

Wie die Tests gegen eine installierte Anwendung laufen: siehe `TESTS_AUSFUEHREN.md`.
Regeln für Arbeits-Threads in diesem Repository: siehe `CLAUDE.md`.
