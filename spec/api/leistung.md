# Leistung – Meilenstein 7

Verbindlich für Implementierung und Tests. Umsetzung von T 20
(„Buchungsliste mit 50.000 Buchungen lädt in unter einer Sekunde, Import
einer großen KMyMoney-Datei in vertretbarer Zeit (Grenzwert vorab
festlegen)“), erweitert um die übrigen häufigen Lesezugriffe (E-133).
Abkürzungen wie in `sicherheit.md`.

## 1. Datensatz `gross`

- Erzeugt vom Testdatengenerator **auf Abruf** (nicht eingecheckt, E-134):
  `python -m generator --gross` schreibt `fixtures/gross/gross.kmy`
  (KMyMoney, gzip) und `fixtures/gross/gross.erwartung.json`; das
  Verzeichnis steht in `.gitignore`. Die Tests erzeugen die Dateien bei
  Bedarf selbst (gleiche Funktion, fester Startwert 4711) und prüfen die
  SHA-256 der Datei gegen `fixtures/MANIFEST.json` (Schlüssel
  `auf_abruf`), damit alle Läufe dieselben Bytes messen.
- Inhalt (synthetisch, Test-IBANs, fiktive Empfänger): **genau 50 000
  Buchungen** vom 2019-01-01 bis 2024-12-31 auf vier Bestandskonten
  (zwei Girokonten und ein Tagesgeldkonto mit IBAN, eine Kreditkarte),
  ein Eigenkapitalkonto, 60 Kategorien in zwei Ebenen, 400 Empfänger,
  12 Tags; etwa 3 % Buchungen mit drei oder mehr Splits, etwa 2 %
  Umbuchungen zwischen eigenen Konten, Verwendungszwecke mit Umlauten. Für
  die Filterprüfung sind Merkmale gezielt eingestreut (Erwartungswerte in
  `gross.erwartung.json`): das Wort `ZEBRA4711` in genau 250
  Verwendungszwecken, der Empfänger `Leistungsprobe Ölmühle GmbH` in genau
  500 Buchungen.
- Größe: etwa 2 MB komprimiert, etwa 30 MB XML.

## 2. Messverfahren

- Eine App im Echtmodus mit frischer temporärer Datenbank, Anmeldung
  abgeschaltet, Planer aus, gesperrtes Netz; der Datensatz wird einmal
  importiert (Messung 3, L1) und dann für alle Lesemessungen verwendet.
- Gemessen wird die Dauer einer Anfrage über `fastapi.testclient.TestClient`
  (Wanduhr, `time.perf_counter`, ohne die Schemaprüfung der Tests). Je
  Messung **ein Aufwärmlauf, danach fünf Läufe; maßgeblich ist der
  Median**. Schreibende Messungen (L8, L9) werden einmal gemessen.
- Neben der Zeit prüft jeder Test das Ergebnis gegen die Erwartung des
  Generators (z. B. `gesamt`), damit nicht eine falsche, schnelle Antwort
  besteht.
- Referenzumgebung: die Testumgebung des Projekts (2 CPU-Kerne,
  Python 3.13). Die Grenzwerte haben großzügigen Abstand zu dem, was eine
  Implementierung mit Indizes und Abfragen im Datenbankserver erreicht; sie
  sind keine Mikro-Benchmarks.
- Die Umgebungsvariable `KONTOR_LEISTUNG_FAKTOR` (Vorgabe `1`) multipliziert
  alle Grenzwerte; nur für erkennbar langsamere Rechner gedacht, die
  Abnahme erfolgt mit 1.
- Leistungstests tragen den Marker `leistung` (zusätzlich `m7` und
  `langsam`) und lassen sich getrennt ausführen
  (`python -m pytest -m leistung`) oder auslassen (`-m "not leistung"`).

## 3. Grenzwerte (Median, Sekunden)

| Nr. | Vorgang | Grenze |
| --- | --- | --- |
| L1 | `POST /api/import/kmymoney` mit `gross.kmy` in eine leere Datenbank (einmal) | 120 |
| L2 | derselbe Import ein zweites Mal (Idempotenz, ohne Wirkung, einmal) | 120 |
| L3 | `GET /api/buchungen` ohne Filter, Seite 1, `pro_seite=100` (Vorgabesortierung) | 1,0 |
| L4 | `GET /api/buchungen`, letzte Seite bei `pro_seite=100` | 1,0 |
| L5 | `GET /api/buchungen` mit je einem Filter: `konto_id`; `von`/`bis` (ein Jahr); `kategorie_id` mit `unterkategorien=true`; `empfaenger_id`; `verwendungszweck=zebra4711`; `suche=zebra4711`; `betrag_min`/`betrag_max`; `tag_id`; Sortierung `-betrag` | je 1,0 |
| L6 | `GET /api/buchungen` mit `konto_id`, `von`, `bis` und `suche` zusammen | 1,0 |
| L7 | `GET /api/suche?q=zebra4711` (Volltextsuche) und `GET /api/kontenuebersicht` | je 1,0 |
| L8 | `POST /api/buchungen/mehrfach/kategorie` für 1 000 Buchungen (einmal, mit Protokoll) | 10 |
| L9 | `PATCH /api/buchungen/{id}` (Verwendungszweck, einmal) | 1,0 |
| L10 | `GET /api/berichte/kontostand` (alle Bestandskonten, `intervall=monat`, ganzer Zeitraum) und `GET /api/berichte/einnahmen-ausgaben` (ganzer Zeitraum) | je 3,0 |
| L11 | `POST /api/lernmodell/vorhersage` mit 100 Einträgen (Merkmale) | 3,0 |
| L12 | `GET /api/wiederkehrend` | 10 |
| L13 | `GET /api/export/buchungen.csv` ohne Filter (50 000 Buchungen) | 20 |
| L14 | `GET /api/sicherung` | 30 |
| L15 | `create_app` auf der gefüllten Datenbank (Neustart, ohne Lifespan) | 5,0 |

Filter und Sortierung: `openapi.yaml` (`GET /api/buchungen`) und
`datenmodell.md` 3.3; die Werte für `von`/`bis`, Kategorie, Empfänger, Tag und
Betragsgrenzen stehen in `gross.erwartung.json` (`proben`).

## 4. Nicht Gegenstand

Gleichzeitige Zugriffe vieler Clients (ein Haushalt), Speicherverbrauch,
Startzeit des Prozesses ohne Datenbank, Synchronisationsdauer (hängt an der
Bank). Die Oberfläche (M8) misst ihre eigene Bedienbarkeit.
