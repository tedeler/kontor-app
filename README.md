# kontor-app

Implementierung von **Kontor**, einer selbst gehosteten Finanz-Web-App
(Python, FastAPI, SQLite, Single-Page-Weboberfläche). Stand: **Meilenstein 1**
– KMyMoney-Import, Finanzübersicht, Konten- und Buchungsliste mit Filtern und
Mehrfachbearbeitung, doppelte Buchführung mit Splits und Tags,
Dublettenerkennung, Bank-/Mail-Plugins als Schnittstelle mit Mock-Varianten.

Die verbindliche Spezifikation liegt im getrennten Repository **kontor-tests**
(`spec/konzept.md`, `spec/api/*`); dort liegen auch die Tests.

## Schnellstart im Mock-Modus

Voraussetzung: Python ≥ 3.11, ein Checkout dieses Repositories.

```bash
# 1. Installieren (in einer virtuellen Umgebung …)
python -m venv .venv && . .venv/bin/activate
pip install -e .
#    … oder systemweit, z. B. in einem Container:
#    pip install --break-system-packages -e .

# 2. Konfiguration über Umgebungsvariablen
export KONTOR_DATENBANK="$PWD/daten/kontor.sqlite3"   # Echt-Datenbank (wird im Mock-Modus NICHT angelegt)
export KONTOR_MOCK_MODUS=ja                           # Mock-Modus: eigene Datenbank daten/kontor-mock.sqlite3

# 3. Synthetische Testdaten importieren (Fixture aus kontor-tests, nur fiktive Daten)
python -m kontor import ../kontor-tests/fixtures/kmy/standard.kmy

# 4. Server starten
python -m kontor serve --host 127.0.0.1 --port 8000
```

Danach im Browser **http://127.0.0.1:8000/** öffnen. Oben erscheint deutlich
der gelbe Hinweis „Mock-Modus“; `GET /api/status` meldet `"modus": "mock"`
und jede API-Antwort trägt den Header `X-Kontor-Modus: mock`.

Alternativ zum eigenen Startbefehl geht auch uvicorn direkt (gleiche
Umgebungsvariablen):

```bash
uvicorn --factory kontor.app:create_app --host 127.0.0.1 --port 8000
```

Weitere synthetische Dateien: `kontor-tests/fixtures/kmy/minimal.kmy`,
`sonderfaelle.kmy`, `dubletten.kmy` usw. Eine `.kmy`-Datei lässt sich auch in
der Oberfläche unter **Import** hochladen. Ein zweiter Import derselben Datei
ändert nichts; eine erweiterte Fassung (z. B. erst `standard_bis_2023.kmy`,
dann `standard.kmy`) fügt nur das Neue hinzu.

Mock-Daten neu beginnen: Server beenden und `daten/kontor-mock.sqlite3`
(samt `-wal`/`-shm`) löschen.

## Konfiguration

| Variable | Bedeutung |
| --- | --- |
| `KONTOR_DATENBANK` | **Pflicht.** Pfad der SQLite-Datei für Echtdaten |
| `KONTOR_MOCK_MODUS` | `ja`/`1`/`true`/`on` = Mock-Modus; leer/`nein` = Echtbetrieb |
| `KONTOR_MOCK_DATENBANK` | Pfad der Mock-Datenbank; Vorgabe `<name>-mock<endung>` neben der Echt-Datenbank |
| `KONTOR_BANK_PLUGIN` | `mock` oder `fints` (Vorgabe: `mock` im Mock-Modus, sonst `fints`) |
| `KONTOR_MAIL_PLUGIN` | `mock` oder `imap` (Vorgabe entsprechend) |
| `KONTOR_MOCK_SZENARIO` | `normal`, `bankfehler`, `zeitueberschreitung`, `tan_erforderlich`, `token_ablauf` |
| `KONTOR_MOCK_DATEN` | JSON-Datei im Format `kontor-mock-daten` (z. B. `kontor-tests/fixtures/mock/mock_daten.json`); leer = eingebauter Datensatz |
| `KONTOR_MOCK_HEUTE` | simuliertes „heute“ (`YYYY-MM-DD`) für die Mock-Plugins |

Im Mock-Modus sind nur Mock-Plugins erlaubt, im Echtbetrieb keine; die
Mock-Datenbank darf nicht die Echt-Datenbank sein. Die echten Plugins (FinTS,
IMAP) bauen in Meilenstein 1 keine Verbindungen auf und melden bei Abrufen
`PluginNichtVerfuegbar`. Die Bank-Synchronisation in das Buch folgt in
Meilenstein 2; bis dahin kommen Buchungen über den KMyMoney-Import oder
manuelle Erfassung ins Buch.

## Python-Schnittstelle (Auszug)

```python
from kontor.config import KontorConfig
from kontor.app import create_app
from kontor.importer.kmymoney import importiere_kmy

config = KontorConfig(datenbank="daten/kontor.sqlite3", mock_modus=True)
ergebnis = importiere_kmy(config, "standard.kmy")
print(ergebnis.als_dict())
app = create_app(config)   # FastAPI-App, Schema ist danach angelegt
```

## Weboberfläche

Single-Page-App ohne Build-Schritt und ohne externe Ressourcen
(`src/kontor/web/`). Bedienung:

- **Navigation** links (auf dem Handy über ☰ einblendbar); Breite per Ziehen
  am Rand änderbar, Doppelklick klappt ein (Layout wird gespeichert).
- **Finanzübersicht**: alle Bestandskonten mit Saldo; **Konten** und
  **Kategorien** als Baum; Klick öffnet die Buchungsliste.
- **Buchungsliste**: Filter (Freitext, Zeitraum, Betrag, Empfänger,
  Verwendungszweck, Kategorie, Tags, Status), Sortierung per Spaltenkopf,
  Mehrfachauswahl mit Strg/⌘ und Umschalt, Strg+A, Entf, `/` springt in die
  Suche. Rechtsklick (bzw. lange Berührung, Umschalt+F10) öffnet das
  Kontextmenü: bearbeiten/splitten, Kategorie setzen, Tags, bestätigen,
  abgleichen, löschen. Doppelklick/Enter bearbeitet eine Buchung.
- **Import**: `.kmy` hochladen, Ergebnis und Hinweise, Dublettenverdachte
  zusammenführen oder verwerfen.
- **Einstellungen**: Betriebsmodus, Plugins, Tags verwalten.
- Helles/dunkles Design folgt der Systemeinstellung.

## Tests

```bash
pip install -e . pytest httpx
python -m pytest tests          # eigene Tests (Browsertest nur mit Playwright + Chrome/Chromium)
```

Die maßgeblichen Tests liegen in kontor-tests; Anleitung dort in
`TESTS_AUSFUEHREN.md` (`python -m pytest` im Wurzelverzeichnis von
kontor-tests gegen diese installierte App). Ergebnis des letzten Laufs:
`ERGEBNIS.md`.

## Dokumente in diesem Repository

| Datei | Inhalt |
| --- | --- |
| `CLAUDE.md` | Regeln für Implementierungs-Threads (Rollentrennung) |
| `ENTSCHEIDUNGEN.md` | Entscheidungen der Implementierung |
| `WIDERSPRUECHE.md` | Widersprüche zwischen Tests und Spezifikation |
| `ERGEBNIS.md` | Ergebnis des letzten vollständigen Testlaufs |
