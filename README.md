# kontor-app

Implementierung von **Kontor**, einer selbst gehosteten Finanz-Web-App
(Python, FastAPI, SQLite, Single-Page-Weboberfläche). Stand: **Meilenstein 5** (M1–M5 und M9)

- M1: KMyMoney-Import, Finanzübersicht, Konten- und Buchungsliste mit Filtern
  und Mehrfachbearbeitung, doppelte Buchführung mit Splits und Tags,
  Dublettenerkennung, Bank-/Mail-Plugins als Schnittstelle mit Mock-Varianten.
- M2: Bank-Synchronisation (manuell und per Planer) mit Kontozuordnung über
  die IBAN, Übernahme der Umsätze, Dublettenerkennung beim Abruf,
  Synchronisationsläufe mit Status je Konto, interne Benachrichtigungen,
  TAN-Ablauf mit QR-Bild, PIN nur im Arbeitsspeicher, simulierte Uhr im
  Mock-Modus, Regel-Kategorisierung mit Vorschlägen und Bestätigung.
- M3: Änderungsprotokoll für jede manuelle und automatische Änderung mit
  Rückgängig (einzeln, mehrere, ganze Gruppe wie ein Synchronisationslauf)
  und Wiederholen, Empfängerverwaltung (Aliase, Standardkategorie,
  Zusammenführen), Erfassungshilfe für manuelle Buchungen, Korrekturen und
  Umbuchungen, Umbuchungserkennung, Kontenabstimmung mit Sperre,
  Volltextsuche, Konten und Kategorien mit Buchungen löschen; gelöschte
  Bankkonten werden bei der Synchronisation erfragt und auf Wunsch (mit allen
  oder nur neuen Umsätzen) wiederhergestellt oder ignoriert.
- M4: GnuCash-Import (XML gzip-komprimiert/unkomprimiert und SQLite, nur
  lesend) mit Zuordnung zu KMyMoney-Daten ohne doppelte Salden, Lernmodell
  (Naive Bayes mit exakten Brüchen, Sicherheit in Promille, Schwelle 70 %,
  abschaltbar) als vierte Stufe der Kategorisierung, Split-Vorlagen für
  Sammelabbuchungen (Erkennung über Empfänger und Muster, feste Teilbeträge,
  keine Toleranz, Benachrichtigung bei Abweichung, nachträgliches Aufteilen).
- M9: Datensicherung und Wiederherstellung: vollständiger fachlicher Bestand
  als ZIP (SQLite-Datenbank und Manifest mit Prüfsummen), Einspielen mit
  Probelauf und ausdrücklicher Bestätigung als eine rückgängig machbare
  Änderung im Protokoll; Geheimnisse und Protokoll sind nie enthalten.
- M5: Wiederkehrende Buchungen (Erkennung aus dem Buchbestand, Übersicht mit
  Rhythmus, Betrag, Jahreskosten und Status, Benachrichtigungen bei neuem
  Empfänger, geändertem Betrag und ausbleibender Zahlung), Kredite
  (Annuitätendarlehen ohne Kontozugriff, Zinsmethoden 30/360, act/360,
  act/365, Sondertilgungen, centgenauer Tilgungsplan, automatische Aufteilung
  der Raten als „vorläufig“ bei der Synchronisation oder nachträglich,
  Jahresabgleich mit genau einer Korrekturbuchung und Status „abgeglichen“),
  Berichte (Kontostandsverlauf als Liniendiagramm, Einnahmen/Ausgaben ohne
  Umbuchungen), Export der gefilterten Buchungsliste als CSV (verlustfrei) und
  PDF (reportlab, ohne Netzwerk). Kredite sind protokolliert, rückgängig
  machbar und Teil der Sicherung.

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

## Synchronisation im Mock-Modus ausprobieren

Die Mock-Bank liefert synthetische Umsätze bis zum simulierten „heute“; es
wird nie eine echte Bank angesprochen.

```bash
export KONTOR_DATENBANK="$PWD/daten/kontor.sqlite3"
export KONTOR_MOCK_MODUS=ja
export KONTOR_MOCK_HEUTE=2024-06-30                # Startzeitpunkt der simulierten Uhr (12:00 UTC)
# optional: Datendatei aus kontor-tests (3 Konten, Vormerkungen, Storno …)
export KONTOR_MOCK_DATEN=../kontor-tests/fixtures/mock/sync_daten.json
# optional: automatischer Abruf alle 60 Minuten (Planer-Thread im Server)
export KONTOR_SYNC_INTERVALL_MINUTEN=60
python -m kontor serve --host 127.0.0.1 --port 8000
```

1. **Regeln** → „+ Regel anlegen“, z. B. *Empfänger enthält „Frischekorb“ →
   Lebensmittel* (vorher unter **Kategorien** eine Aufwandskategorie anlegen).
   Sie greift im eingebauten Datensatz wie in `sync_daten.json`.
2. **Synchronisation** → „Jetzt synchronisieren“. Fehlende Konten werden über
   die IBAN angelegt, neue Umsätze gebucht, Gegenkonto ist die Kategorie der
   ersten passenden Regel oder das technische Konto „Unkategorisiert“. Die
   Liste der Läufe zeigt je Konto, was neu, vorhanden, zusammengeführt oder zur
   Prüfung vorgelegt wurde. Ein zweiter Lauf erzeugt keine Dubletten.
3. **Alle Buchungen** (Filter „Kategorie-Vorschlag: nur mit Vorschlag“):
   Regel-Kategorien tragen die Marke „Vorschlag“ und lassen sich per ✓/✗ in
   der Zeile, über die Mehrfachauswahl („✓ Vorschläge annehmen“, „✗ ablehnen“)
   oder das Kontextmenü bestätigen bzw. ablehnen.
4. **Mock-Uhr** (auf der Seite Synchronisation): Zeit vorstellen (z. B.
   „+1 Tag“) und erneut synchronisieren – neue Umsätze erscheinen, der
   Zeitraum überlappt den letzten Abruf um 14 Tage.
5. **TAN-Ablauf**: mit `KONTOR_MOCK_SZENARIO=tan_erforderlich` starten. Der
   Lauf pausiert, die Glocke oben zeigt eine Benachrichtigung, die TAN-Seite
   (`/tan/<id>`) zeigt Anweisung und QR-Bild mit „QR-Code speichern“ und
   „Teilen …“. Richtige TAN: `123456` (bzw. `bank.tan` der Datendatei); nach
   23:59:59 UTC des simulierten Tages läuft die Anforderung ab.
6. **PIN**: mit `KONTOR_MOCK_DATEN=../kontor-tests/fixtures/mock/sync_daten_pin.json`
   verlangt die Mock-Bank eine PIN (steht synthetisch in der Datei unter
   `bank.pin`). Ohne PIN scheitert der Lauf mit `bank_pin_fehlt`; die PIN wird
   auf der Seite Synchronisation eingegeben, liegt nur im Arbeitsspeicher und
   ist nach einem Neustart oder einer Ablehnung durch die Bank weg.
7. Fehlerfälle: `KONTOR_MOCK_SZENARIO=bankfehler` bzw. `zeitueberschreitung` –
   der Lauf scheitert ohne Datenverlust, es entsteht genau eine
   Benachrichtigung je Fehlercode, solange sie ungelesen ist.

## Konfiguration

| Variable | Bedeutung |
| --- | --- |
| `KONTOR_DATENBANK` | **Pflicht.** Pfad der SQLite-Datei für Echtdaten |
| `KONTOR_MOCK_MODUS` | `ja`/`1`/`true`/`on` = Mock-Modus; leer/`nein` = Echtbetrieb |
| `KONTOR_MOCK_DATENBANK` | Pfad der Mock-Datenbank; Vorgabe `<name>-mock<endung>` neben der Echt-Datenbank |
| `KONTOR_BANK_PLUGIN` | `mock` oder `fints` (Vorgabe: `mock` im Mock-Modus, sonst `fints`) |
| `KONTOR_MAIL_PLUGIN` | `mock` oder `imap` (Vorgabe entsprechend) |
| `KONTOR_MOCK_SZENARIO` | `normal`, `bankfehler`, `zeitueberschreitung`, `tan_erforderlich`, `token_ablauf`, `beitragsaenderung` (M4: Umsätze mit `betrag_beitragsaenderung` in der Datendatei kommen mit diesem Betrag) |
| `KONTOR_MOCK_DATEN` | JSON-Datei im Format `kontor-mock-daten` (z. B. `kontor-tests/fixtures/mock/mock_daten.json`); leer = eingebauter Datensatz |
| `KONTOR_MOCK_HEUTE` | simuliertes „heute“ (`YYYY-MM-DD`); im Mock-Modus startet die App-Uhr dann bei diesem Tag 12:00 UTC (stellbar über `PUT /api/mock/zeit` bzw. die Oberfläche) |
| `KONTOR_SYNC_INTERVALL_MINUTEN` | Abstand automatischer Läufe; `0` (Vorgabe) = kein automatischer Abruf |
| `KONTOR_SYNC_WIEDERHOLUNG_MINUTEN` | erneuter Versuch nach fehlgeschlagenem Lauf (Vorgabe 30) |
| `KONTOR_SYNC_ERSTABRUF_TAGE` | Zeitraum des ersten Abrufs eines Kontos (Vorgabe 90) |
| `KONTOR_SYNC_UEBERLAPPUNG_TAGE` | Überlappung folgender Abrufe (Vorgabe 14) |
| `KONTOR_PLANER_STARTEN` | Planer-Thread im Server starten (Vorgabe ja; nur wirksam mit Intervall > 0) |
| `KONTOR_UMBUCHUNG_AUTOMATISCH` | Umbuchungen bei jeder Synchronisation automatisch erkennen und zusammenführen (Vorgabe nein; für den Betrieb empfohlen: `1`) |
| `KONTOR_UMBUCHUNG_FENSTER_TAGE` | größter Datumsabstand der beiden Seiten einer Umbuchung (0–366, Vorgabe 3) |
| `KONTOR_LERNMODELL_AUTOMATISCH` | Lernmodell bei neuen Buchungen (Synchronisation, Erfassen) als Vorschlag befragen (Vorgabe nein; für den Betrieb empfohlen: `1`) |
| `KONTOR_WIEDERKEHREND_AUTOMATISCH` | nach jedem Synchronisationslauf auf unerwartete Buchungen prüfen (neuer Empfänger, geänderter Betrag, ausbleibende Zahlung; Vorgabe nein; für den Betrieb empfohlen: `1`) |

### Empfohlene Konfiguration für den Betrieb

Die Vorgaben halten das Verhalten früherer Meilensteine (E-054, E-072). Im
täglichen Betrieb empfiehlt sich:

```bash
export KONTOR_DATENBANK=/var/lib/kontor/kontor.sqlite3
export KONTOR_SYNC_INTERVALL_MINUTEN=240     # automatischer Abruf alle 4 Stunden
export KONTOR_UMBUCHUNG_AUTOMATISCH=1        # Umbuchungen zwischen eigenen Konten zusammenführen
export KONTOR_LERNMODELL_AUTOMATISCH=1       # Kategorien aus dem Lernmodell vorschlagen
export KONTOR_WIEDERKEHREND_AUTOMATISCH=1    # Abos/Daueraufträge überwachen, Auffälligkeiten melden
```

Reihenfolge der Kategorisierung neuer Bankumsätze: Kreditrate (Aufteilung in
Zins und Tilgung, Status „vorläufig“) → Split-Vorlage → Regel →
Standardkategorie des Empfängers → Lernmodell → „Unkategorisiert“. Alles
außer Vorlagen-Treffern bleibt als Vorschlag markiert, bis es bestätigt ist.

Im Mock-Modus sind nur Mock-Plugins erlaubt, im Echtbetrieb keine; die
Mock-Datenbank darf nicht die Echt-Datenbank sein. Die echten Plugins (FinTS,
IMAP) bauen bis Meilenstein 6 keine Verbindungen auf und melden bei Abrufen
`PluginNichtVerfuegbar`; eine Synchronisation im Echtbetrieb endet daher
sauber als fehlgeschlagener Lauf. Die PIN wird nie in einer Umgebungsvariable,
Datei oder Datenbank abgelegt, sondern nur in der Weboberfläche eingegeben.

### Datensicherung im Betrieb

Kontor sichert den **fachlichen Bestand** in der App (`GET /api/sicherung`,
Seite „Datensicherung“, Python `kontor.sicherung.erstelle_sicherung`):
Konten, Buchungen mit Splits, Empfänger, Tags, Regeln, Dublettenverdachte,
Abstimmungen, Split-Vorlagen, gemerkte Umsatzkennungen, Stand je Bankkonto
und ID-Zähler – als ZIP mit `kontor.sqlite` und `manifest.json`. Nicht
enthalten: Änderungsprotokoll, PIN/Geheimnisse, Importvorgänge, Läufe,
Benachrichtigungen und die Konfiguration (Umgebungsvariablen).

Empfehlung: **zusätzlich** zu Proxmox-Snapshots bzw. -Backups des Containers.
Ein Snapshot sichert die ganze Instanz einschließlich Protokoll und
Konfiguration (schnelles Zurücksetzen nach einem missglückten Update); die
Kontor-Sicherung ist klein, geprüft (Prüfsummen), unabhängig vom Container und
lässt sich auf neuer Hardware oder in eine frische Instanz einspielen. Eine
Sicherung im laufenden Betrieb ist ein konsistenter Schnappschuss; der Server
muss dafür nicht angehalten werden. Beispiel für eine nächtliche Sicherung per
cron (Ziel außerhalb des Containers, z. B. NAS):

```bash
#!/bin/sh
# /usr/local/bin/kontor-sicherung – mit denselben KONTOR_*-Umgebungsvariablen wie der Server
set -e
ziel=/mnt/nas/kontor
python3 -c 'import sys; from kontor.config import KontorConfig; from kontor.sicherung import erstelle_sicherung
open(sys.argv[1], "wb").write(erstelle_sicherung(KontorConfig.from_env()))' "$ziel/kontor-$(date +%F).zip"
find "$ziel" -name 'kontor-*.zip' -mtime +30 -delete      # 30 Tage aufbewahren
```

```bash
# /etc/cron.d/kontor-sicherung – täglich 02:17
17 2 * * * kontor . /etc/kontor.env && /usr/local/bin/kontor-sicherung
```

Die Dateien enthalten sensible Finanzdaten: nur auf verschlüsselten
bzw. zugriffsgeschützten Speichern ablegen. Wiederherstellen über die Seite
„Datensicherung“: Datei wählen, „Prüfen“ zeigt den Unterschied je Objektart
(und betroffene abgestimmte Buchungen), danach Bestätigung; das Einspielen
ist eine Änderung im Änderungsprotokoll und lässt sich rückgängig machen.
Eine Mock-Sicherung lässt sich nie in den Echtbetrieb einspielen und
umgekehrt. Nach dem Einspielen holt die nächste Synchronisation Umsätze nach,
die seit der Sicherung gebucht wurden – jeden genau einmal. Die PIN wird bei
Bedarf neu eingegeben.

## Python-Schnittstelle (Auszug)

```python
from kontor.config import KontorConfig
from kontor.app import create_app
from kontor.importer.kmymoney import importiere_kmy
from kontor.importer.gnucash import importiere_gnucash

config = KontorConfig(datenbank="daten/kontor.sqlite3", mock_modus=True)
ergebnis = importiere_kmy(config, "standard.kmy")
print(ergebnis.als_dict())
print(importiere_gnucash(config, "haushalt.gnucash").als_dict())   # XML oder SQLite, Datei bleibt unverändert
app = create_app(config)   # FastAPI-App, Schema ist danach angelegt

from kontor.sync import planer_takt
lauf = planer_takt(app)    # ein Planer-Takt, synchron (None, wenn nichts fällig ist)

from kontor.sicherung import erstelle_sicherung
zip_bytes = erstelle_sicherung(config)   # nur lesend; Einspielen nur über REST

from kontor.kredite import tilgungsplan   # reine Funktion (M5), Beträge in Cent, Sollzins in Millionstel
plan = tilgungsplan({"restschuld": 1_000_000, "stand_datum": "2024-01-15", "sollzins": 36_000,
                     "rate": 50_000, "erste_faelligkeit": "2024-02-01", "zinsmethode": "30/360"})
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
- **Vorschläge**: Kategorien aus Regeln und Standardkategorien sind mit
  „Vorschlag“ markiert, die aus dem Lernmodell mit „Lernmodell 93,8 %“
  (Sicherheit); alle
  werden per ✓/✗ (einzeln, mehrfach oder im Kontextmenü) bestätigt bzw.
  abgelehnt; Filter „Kategorie-Vorschlag“.
- **Synchronisation**: Lauf starten (optional mit Zeitraum), Status, nächster
  Lauf, Läufe mit Ergebnis je Konto, Bankkonten, PIN-Eingabe, Mock-Uhr.
- **TAN-Seite** (`#/tan/<id>`, auch über den Link `/tan/<id>`): Anweisung,
  QR-Bild, „QR-Code speichern“, „Teilen …“ (Web Share, falls der Browser
  Dateien teilen kann), TAN-Eingabe, Abbrechen.
- **Regeln**: anlegen, bearbeiten, (de)aktivieren, löschen, Probelauf und
  Anwenden auf vorhandene Buchungen.
- **Benachrichtigungen** (Glocke im Kopf mit Anzahl ungelesener).
- **Import**: KMyMoney (`.kmy`) oder GnuCash (XML/SQLite; die Quelle wird an
  der Endung vorgewählt) hochladen, Ergebnis und Hinweise, Dublettenverdachte
  zusammenführen oder verwerfen.
- **Lernmodell** (M4): Zustand (Trainingsbuchungen, Kategorien, Merkmale,
  Schwelle, automatisch an/aus), „Neu trainieren“ (das Modell wird ohnehin
  bei jeder Anfrage aus dem Buchbestand trainiert), Probelauf/Anwenden auf
  unkategorisierte Buchungen, Vorhersage ausprobieren mit Kandidaten.
- **Split-Vorlagen** (M4): anlegen (auch aus einer gesplitteten Buchung über
  das Kontextmenü „Als Split-Vorlage speichern …“), bearbeiten (z. B. neuer
  Teilbetrag nach Beitragsänderung), (de)aktivieren, löschen, Probelauf und
  Aufteilen vorhandener Buchungen; Hinweise zu Abweichungen aus der
  Synchronisation stehen oben auf der Seite mit „Vorlage anpassen …“. Der
  Link der Benachrichtigung (`/buchungen/<id>`) öffnet die Buchung.
- **Gelöschte Bankkonten**: Auf der Seite Synchronisation zeigt die Tabelle
  „Bankkonten“ den Status (aktiv, Konto fehlt, ignoriert, wird
  wiederhergestellt); „Entscheiden …“ fragt ohne Vorauswahl nach
  Wiederherstellen (mit allen oder nur neuen Umsätzen) oder Ignorieren und
  bietet danach einen sofortigen Lauf an (Link `/sync/konten`).
- **Datensicherung** (M9): „Sicherung herunterladen“ (ZIP); „Sicherung
  einspielen“ prüft die Datei zuerst (Probelauf: Unterschied je Objektart,
  betroffene abgestimmte/abgeglichene Buchungen, verständliche Meldung bei
  beschädigten oder fremden Dateien), verlangt dann ein Häkchen und eine
  zweite Bestätigung und zeigt das Ergebnis mit Link ins
  Änderungsprotokoll und „Einspielen rückgängig machen“.
- **Wiederkehrende Buchungen** (M5): erkannte Serien mit Empfänger, Konto,
  Rhythmus, aktuellem Betrag, Jahreskosten, nächster Fälligkeit und Status
  (aktiv/ausbleibend/beendet) zu einem wählbaren Stichtag, Summe der
  Jahreskosten; „Ausbleibende Zahlungen prüfen“; Klick zeigt die Buchungen
  des Empfängers. Benachrichtigungen verlinken auf `/buchungen/<id>` bzw.
  `/wiederkehrend`.
- **Kredite** (M5): anlegen/bearbeiten (Darlehens-, Zahlungs- und Zinskonto,
  Restschuld, Sollzins in Prozent, Zinsmethode, Rate, erste Fälligkeit,
  Sondertilgungen, Erkennungsbedingungen, „Plan berechnen“), Tilgungsplan mit
  gebuchten Raten, „Raten in vorhandenen Buchungen suchen“ (Probelauf, dann
  aufteilen), Jahresabgleich-Dialog: Auszugswerte eingeben, Vorschlag mit
  Differenzen und Korrektursplits ansehen, erst dann bestätigen.
- **Berichte** (M5): Kontostandsverlauf je Konto als selbst gezeichnetes
  SVG-Liniendiagramm (Zeitachse, Fadenkreuz mit Werten, Legende, Werte auch
  als Tabelle), Einnahmen und Ausgaben je Intervall; Export-Knöpfe.
- **Export** (M5): „⤓ CSV“ und „⤓ PDF“ in jeder Buchungsliste exportieren
  genau die gefilterten Buchungen in der angezeigten Sortierung.
- **Einstellungen**: Betriebsmodus, Plugins, Tags verwalten.
- **Änderungsprotokoll** (M3): alle Änderungen, neueste zuerst, filterbar nach
  Quelle und Wirksamkeit, mit Einträgen je Objekt; Knöpfe „Rückgängig“,
  „Wiederholen“ und „Ganze Gruppe“. **Strg+Z** (bzw. ↶ im Kopf) nimmt die
  letzte Änderung zurück, **Strg+Y**/Strg+Umschalt+Z stellt sie wieder her.
- **Globale Suche** im Kopf (Volltext über Konten, Empfänger inkl. Aliase,
  Tags und Buchungen; Umlaut- und Akzent-unabhängig).
- **Empfänger**: anlegen, bearbeiten (Aliase je Zeile, Standardkategorie),
  löschen, mehrere markieren und zusammenführen.
- **Buchung erfassen** (Buchungsliste/Konto): Ausgabe, Einnahme, Umbuchung
  zwischen eigenen Konten, Korrektur – immer mit positivem Betrag (Korrektur
  vorzeichenbehaftet).
- **Umbuchungen**: Vorschläge eindeutiger Paare, einzeln oder alle
  zusammenführen; in der Buchungsliste zwei markierte Buchungen über das
  Kontextmenü zusammenführen. Getrennt wird über Rückgängig.
- **Kontenabstimmung**: Auszugssaldo prüfen (Differenz wird angezeigt) und
  abstimmen; abgestimmte Buchungen tragen „🔒 abgestimmt“ und sind gesperrt;
  die letzte Abstimmung lässt sich auf der Kontoseite aufheben.
- **Konto/Kategorie löschen** (Kontextmenü „Löschen …“ bzw. Kontoseite):
  unbenutzte nach einfacher Rückfrage; sonst Dialog mit Zahlen aus dem
  Probelauf und Wahl ohne Vorauswahl (Buchungen löschen / dem übergeordneten
  Konto zuschlagen / als unkategorisiert einstufen), ggf. Umgang mit
  Konfliktbuchungen und Bestätigung für gesperrte Buchungen.
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
