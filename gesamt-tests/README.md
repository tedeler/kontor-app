# Gesamtsuite

Gekürzte Fassung der früheren Abnahmetests aus kontor-tests. Sie läuft in der CI auf main (zwei Jobs, siehe
`.github/workflows/release.yml`). Herkunft, Messungen und Auswahlregel stehen in `../TESTUMBAU.md`.

```bash
cd gesamt-tests
python -m pytest -n auto -m "not browser"   # REST, Importe, Plugins, Spezifikation, Generator
python -m pytest -n auto -m browser         # Oberfläche mit Playwright und Chrome
python -m pytest -n auto --alle             # zusätzlich abgewaehlt.txt sowie leistung und langsam
python -m pytest tests/app/m30 -k regel     # Auswahl wie gewohnt; ausdrücklich genannte Knoten-IDs laufen immer
```

- `abgewaehlt.txt`: Tests, die ohne `--alle` nicht laufen. Neue Tests gehören nicht hierher, sondern nach
  `../tests/` (Core-Tests nach `../tests/core/`).
- `spec` verweist auf `../spec`. Fixtures nur mit `python -m generator` erzeugen.
- Die Tests greifen nur über die Schnittstellen auf die App zu (`tests/hilfen/kontor.py`, `tests/hilfen/api.py`,
  das jede Antwort gegen `spec/api/openapi.yaml` prüft). Ändert ein Feature das Verhalten, werden die betroffenen
  Tests hier angepasst und in `../TESTUMBAU.md` unter „Geänderte Tests“ vermerkt.
