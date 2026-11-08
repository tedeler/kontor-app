# Ergebnis: Implementierung Meilenstein 1

Stand: 2026-11-08, Implementierungs-Thread.

## Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `c708944`**
  (`c7089448362e5abd1be05384ceb3894705076e9f`, „ERGEBNIS.md: erstellte
  Dateien, Testanzahl je Bereich, Selbstprüfung“), nach `git pull` im
  Lese-Klon.
- Aufruf: `python -m pytest -p no:cacheprovider` im Wurzelverzeichnis des
  Lese-Klons, gegen die per `pip install --break-system-packages -e` installierte
  kontor-app (Version 0.1.0), Python 3.13, Hypothesis-Profil `standard`.

| gesamt | bestanden | fehlgeschlagen | übersprungen |
| ---: | ---: | ---: | ---: |
| 734 | 734 | 0 | 0 |

Fehlschläge: keine. Widersprüche (`WIDERSPRUECHE.md`): keine.

Zusätzlich lief `HYPOTHESIS_PROFILE=gruendlich python -m pytest tests/app`
(400 zufällige Beispiele je Eigenschaftstest): 674 von 674 bestanden.

## Eigene Tests (kontor-app/tests)

`python -m pytest tests`: **29 bestanden**, darunter ein Browser-Rauchtest mit
Playwright und Chrome (headless): Finanzübersicht, Kontoansicht,
Mehrfachauswahl mit Umschalt/Strg, Kontextmenü per Rechtsklick, Kategorie für
mehrere Buchungen setzen, mobiles Menü (390 px), lange Berührung öffnet das
Kontextmenü. Weitere eigene Tests: Auslieferung der Oberfläche und Assets,
keine externen Ressourcen, Oberfläche nutzt nur spezifizierte API-Pfade,
Schema lehnt Gleitkommabeträge ab, Import-Randfälle, eingebauter
Mock-Datensatz.

## Prüfung der Weboberfläche

Server im Mock-Modus gestartet (`python -m kontor serve`), `standard.kmy`
importiert, alle Seiten und Assets per curl abgerufen (200, korrekte
Content-Types, Mock-Hinweis im HTML, `X-Kontor-Modus: mock`) und mit
Playwright/Chrome im hellen und dunklen Design sowie in Handygröße bedient
(Filter, Sortierung, Bearbeiten/Splitten, Tags, Kategorie, Konto anlegen,
Import-Upload, Einstellungen). Dabei gefundene Fehler (verdeckte Dialoghülle,
Tabellenbreite auf dem Handy, „null“-Ausgabe) sind behoben. Gestartete
Server-Prozesse wurden beendet.

## Einschränkungen

- Nicht Teil von Meilenstein 1 und nicht umgesetzt: Bank-Synchronisation in
  das Buch, Kategorisierung, Split-Vorlagen, wiederkehrende Buchungen,
  Kredite, Berichte, Kontenabstimmung, Login, Änderungsprotokoll/Undo,
  Drag and Drop, Befehlspalette, Inline-Bearbeitung, Service Worker (PWA nur
  mit Manifest). In der Oberfläche als „später“ gekennzeichnet.
- FinTS- und IMAP-Plugin sind Platzhalter ohne Verbindung
  (`PluginNichtVerfuegbar`).
- Mock-Daten gelangen nur über den KMyMoney-Import synthetischer Dateien in
  das Buch (D-014).
- Der Browser-Rauchtest deckt die Kernabläufe ab, ersetzt aber keine
  vollständigen Playwright-Tests nach T 19 (die gehören in kontor-tests).
