# Ergebnis der Implementierung

## Meilenstein 3

Stand: 2026-11-08, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `ae6eacf`**
  (`ae6eacf5c3df597db159e57c78129bb370b2c68e`, „ERGEBNIS.md: M3-Abschnitt auf den
  Gesamtlauf der Selbstprüfung (529/529, 65/65) abgestimmt“), nach `git pull` im
  Lese-Klon.
- Aufruf: `python -m pytest -p no:cacheprovider` im Wurzelverzeichnis des Lese-Klons,
  gegen die per `pip install --break-system-packages -e` installierte kontor-app,
  Python 3.13, Hypothesis-Profil `standard`.

| Auswahl | gesamt | bestanden | fehlgeschlagen | übersprungen |
| --- | ---: | ---: | ---: | ---: |
| alle Tests | 1200 | 1200 | 0 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |
| davon `-m m3` | 227 | 227 | 0 | 0 |

(Die übrigen 73 Tests sind Generator- und Spezifikationstests.)

Fehlschläge im Standardlauf: keine.

Zusätzlich `HYPOTHESIS_PROFILE=gruendlich python -m pytest -m m3`: 225 von 227
bestanden; die zwei Fehlschläge (`test_m3_rueckgaengig.py::test_zufaellige_folgen_rueckwaerts`,
`::test_zufaelliges_rueckgaengig_gegen_orakel`) sind ein Fehler im Testablauf
(Zufallsauswahl aus leerer Kontenliste, bevor die Anwendung angefragt wird), siehe
**W-001**. Dieselben beiden Tests liefen zusätzlich mit sechs weiteren Hypothesis-Startwerten
(`--hypothesis-seed=1…6`) im Standardprofil grün.

### Eigene Tests (kontor-app/tests)

`python -m pytest tests`: **42 bestanden**, neu:

- `tests/test_m3_eigen.py`: Migration einer Datenbank mit dem Schema von M2
  (`tests/daten/schema_m2.sql`, mit Vorschlag) auf Schemaversion 3 ohne Datenverlust,
  danach Aliase, Abstimmung und Protokoll auf der migrierten Datenbank; Rückgängig einer
  Tag-Umbenennung behält Zuordnungen; Probelauf „Konto löschen“ verbraucht keine IDs;
  PIN erscheint nie im Protokoll.
- `tests/test_browser_m3.py` (Playwright, Chrome headless, echte Server im Mock-Modus auf
  freien lokalen Ports, danach beendet): Umbuchungsvorschläge zusammenführen, Strg+Z,
  Buchung erfassen, globale Suche (umlautunabhängig), Kontenabstimmung mit Differenz und
  mit passendem Saldo, Rückgängig im Änderungsprotokoll; im Handyformat Empfänger mit
  Alias und Standardkategorie bearbeiten, Kategorie mit Buchungen löschen (keine
  Vorauswahl, Elternkonto bei Wurzel deaktiviert), Rückgängig über den Knopf im Kopf,
  Suche.

Die neuen Seiten wurden zusätzlich per Bildschirmfoto (Desktop 1280 px, Handy 390 px)
geprüft; gefundene Mängel (Ausgabe „null“ im Löschdialog, umbrechende Knöpfe im
Protokoll auf dem Handy) sind behoben.

### Einschränkungen

- Die automatische Umbuchungserkennung ist wie spezifiziert standardmäßig aus
  (`KONTOR_UMBUCHUNG_AUTOMATISCH=1` für den Betrieb empfohlen).
- Die Volltextsuche rechnet ohne Index in Python (D-041); Leistung wird in M7 bewertet.
- Das Änderungsprotokoll wächst unbegrenzt (kein Aufräumen; nicht spezifiziert).
- Stabile `data-testid` der Oberfläche und vollständige Playwright-Tests folgen in M8.
- Echtes FinTS-Plugin weiterhin Platzhalter (M6), wie in M2.

---

## Meilenstein 2 (frühere Fassung)

Stand: 2026-11-08, Implementierungs-Thread.

### Testlauf kontor-tests

- Getestet gegen **kontor-tests Commit `bda67eb`**
  (`bda67ebe9e5f0a234f63e95a46cd0a5608464497`, „TESTS_AUSFUEHREN.md, CLAUDE.md,
  ERGEBNIS.md für Meilenstein 2“), nach `git pull` im Lese-Klon.
- Aufruf: `python -m pytest -p no:cacheprovider` im Wurzelverzeichnis des
  Lese-Klons, gegen die per `pip install --break-system-packages -e`
  installierte kontor-app, Python 3.13, Hypothesis-Profil `standard`.

| Auswahl | gesamt | bestanden | fehlgeschlagen | übersprungen |
| --- | ---: | ---: | ---: | ---: |
| alle Tests | 966 | 966 | 0 | 0 |
| davon `-m m1` | 674 | 674 | 0 | 0 |
| davon `-m m2` | 226 | 226 | 0 | 0 |

(Die übrigen 66 Tests sind Generator- und Spezifikationstests.)

Fehlschläge: keine. Widersprüche (`WIDERSPRUECHE.md`): keine.

Zusätzlich `HYPOTHESIS_PROFILE=gruendlich python -m pytest -m m2` (400 zufällige
Beispiele je Eigenschaftstest): 226 von 226 bestanden.

### Eigene Tests (kontor-app/tests)

`python -m pytest tests`: **36 bestanden**, darunter zwei neue Playwright-Rauchtests
mit Chrome headless (`tests/test_browser_m2.py`, echte Server im Mock-Modus auf
freien lokalen Ports, danach beendet): Regel über den Dialog anlegen,
Synchronisation auslösen, Läufe ansehen, Vorschläge in der Buchungsliste
erkennen, einzeln (✓) annehmen und mehrfach ablehnen; im Handyformat TAN-Ablauf
(QR-Bild geladen, „QR-Code speichern“ als PNG-Download, „Teilen …“,
Benachrichtigungsglocke, Link `/tan/<id>`, falsche und richtige TAN) und
Benachrichtigung als gelesen markieren. Weitere eigene Tests: gedeckelte
Vorgabepriorität, eingebauter Datensatz, deterministisches QR-Bild, TAN-Bild nur
bei offener Anforderung, Oberfläche nutzt nur spezifizierte API-Pfade.

Die Oberfläche wurde zusätzlich per Bildschirmfoto (Desktop 1280 px, Handy
390 px) geprüft; gefundene Mängel (Ausgabe „null“ in der Werkzeugleiste,
gequetschte Regeltabelle auf dem Handy) sind behoben.

### Einschränkungen

- Das echte FinTS-Plugin ist weiterhin ein Platzhalter (M6); Läufe im
  Echtbetrieb enden als `fehlgeschlagen` (`plugin_nicht_verfuegbar`).
- PIN nur per Eingabe in der Oberfläche (Arbeitsspeicher); systemd-creds/TPM,
  ntfy-Zustellung und TAN-Erinnerungen folgen in M6.
- Das Mock-QR-Bild ist ein QR-artiges, aber nicht lesbares Bild (D-020).
- Umbuchungen zwischen eigenen Konten werden noch nicht erkannt (M3): beide
  Bankseiten werden als eigene Buchungen gegen „Unkategorisiert“ gebucht.
- Der Browser-Rauchtest ersetzt keine vollständigen Playwright-Tests (M8).

---

## Meilenstein 1 (frühere Fassung)

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
