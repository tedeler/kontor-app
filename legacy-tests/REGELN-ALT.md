# Frühere Regeln für Arbeits-Threads in kontor-tests (außer Kraft)

> Diese Regeln galten im aufgegebenen Repository kontor-tests und sind hier nur als Referenz erhalten.
> Es gelten `../CLAUDE.md` und `../TESTUMBAU.md`.

Dieses Repository enthält Konzept, Testkonzept, die verbindliche
Schnittstellenspezifikation, den Testdatengenerator und die Tests für
**Kontor** (selbst gehostete Finanz-Web-App: Python, FastAPI, SQLite,
Single-Page-Weboberfläche). Die Anwendung selbst liegt im getrennten
Repository kontor-app. Alle Dokumente, Kommentare und Commit-Nachrichten
sind auf Deutsch.

## Rollentrennung (unbedingt einhalten)

- **Test-Threads** arbeiten nur hier. Sie fügen sich kontor-app niemals
  hinzu (kein `add_repo`, kein `git clone`), lesen keinen Anwendungscode und
  schreiben keinen. Liegt irgendwo auf der Platte ein Verzeichnis
  `kontor-app` oder ein Implementierungsverzeichnis: nicht öffnen.
- **Implementierungs-Threads** dürfen dieses Repository nur lesen und die
  Tests ausführen. Sie ändern hier nichts, committen und pushen nichts.
- **Widersprüche** zwischen Tests und Spezifikation löst nur ein
  Test-Thread. Er bekommt den Widerspruch als Text beschrieben, nie als Code.
- Die Anwendung existiert für Tests nur über die spezifizierten
  Schnittstellen: `spec/api/python-api.md` (Paket `kontor`, Konfiguration,
  App-Fabrik, Import, Plugins, Fehlerklassen) und `spec/api/openapi.yaml`
  (REST). Tests importieren `kontor` nie auf Modulebene, sondern über
  `tests/hilfen/kontor.py`; REST-Zugriffe laufen über `tests/hilfen/api.py`,
  das jede Antwort gegen `openapi.yaml` prüft.

## Spezifikation

- `spec/konzept.md`, `spec/testkonzept.md` und `spec/api/*` sind der Vertrag.
  Änderungen nur bei einer echten Lücke oder einem Fehler.
- Jede offene Entscheidung und jede Änderung der Spezifikation bekommt einen
  neuen Eintrag in `spec/api/entscheidungen.md` (fortlaufende Nummer
  `E-0xx`, je Eintrag: Frage, Entscheidung, Begründung, Bezug zum
  Konzept-Abschnitt). Bestehende Einträge werden nicht umgeschrieben, sondern
  durch neue ersetzt bzw. ergänzt.
- Nach einer Änderung an `openapi.yaml`: `python -m pytest tests/spec`.

## Testdaten

- Ausschließlich synthetische Daten: fiktive Empfänger, Test-IBANs mit
  BLZ `00000000` (`generator/iban.py`), Adressen unter `example.invalid`.
  Niemals echte Bank-, Mail- oder Kreditdaten, keine Secrets.
- Fixtures unter `fixtures/` werden nur mit `python -m generator` erzeugt
  (fester Startwert 4711), nie von Hand bearbeitet. Danach
  `python -m pytest tests/generator` (prüft Reproduzierbarkeit und MANIFEST).
- Erwartungswerte kommen aus der bekannten Wahrheit des Generators
  (`*.erwartung.json`) oder werden im Test unabhängig berechnet – nie aus
  einer Ausgabe der Anwendung abgeschrieben.

## Tests

- pytest und Hypothesis; Konfiguration in `pytest.ini`, Abhängigkeiten in
  `requirements-tests.txt`. Ausführen: siehe `TESTS_AUSFUEHREN.md`.
- Marker: `kern` (läuft zusätzlich in der Selbstprüfung), `langsam`
  (große Fixtures), `leistung` (Leistungstests M7, getrennt ausführbar),
  `browser` (Playwright-Tests M8, ohne startbaren Browser übersprungen),
  `app` (automatisch für `tests/app`), `m1`…`m9`, `m11`…`m13` und `m15`…`m32` je
  Meilenstein (automatisch: `tests/app/*.py` = `m1`, `tests/app/m<N>/` =
  `m<N>`, `tests/attrappen/` = `m6`; E-041, E-058, E-065, E-097, E-112, E-125, E-139, E-157, E-158, E-167, E-176, E-181, E-192, E-199, E-206, E-211, E-216, E-221,
  E-223, E-228, E-233, E-238, E-246, E-249, E-252, E-258, E-268, E-277, E-293; `m10` ist mit M29 entfallen, E-259). Tests eines neuen
  Meilensteins `N` kommen nach `tests/app/m<N>/` mit Marker `m<N>` (in
  `tests/conftest.py` und `pytest.ini` eintragen).
- `python -m pytest` ohne `-m` ist ein Schnelllauf (ohne `leistung`,
  `browser`, `langsam`; Hypothesis-Profil `schnell`); Abnahme und
  Abschluss eines Auftrags mit dem Volllauf `--voll` (E-175). Parallel mit
  `-n auto`; Tests dürfen keine festen Ports oder geteilten Dateien nutzen.
- Jede App in einem Test bekommt eine eigene temporäre Datenbank
  (Fixtures in `tests/app/conftest.py`). Plugin- und Mock-Tests laufen mit
  gesperrtem Netzwerk (`netz_gesperrt`); Tests echter Plugins gegen lokale
  Attrappen mit `netz_nur_loopback` (nur 127.0.0.1, E-122).
- Fehlt die Anwendung, schlagen App-Tests mit deutlicher Meldung fehl
  (E-024); überspringen nur bewusst mit `--ohne-app`.
- Meilensteinplan: `spec/meilensteine.md` (M1–M9, M8 als letzter). Umfang Meilenstein 1:
  KMyMoney-Import, Kontenübersicht, Buchungsliste mit Filtern und
  Mehrfachbearbeitung, Datenmodell, Bank-/Mail-Plugins als Schnittstelle mit
  Mock-Varianten. Meilenstein 2: Bank-Synchronisation mit Mock-Plugin, TAN,
  PIN im Arbeitsspeicher, Planer, Regel-Kategorisierung mit Vorschlägen
  (`spec/api/synchronisation.md`, `spec/api/kategorisierung.md`).
  Meilenstein 3: Änderungsprotokoll mit Rückgängig, Empfängerverwaltung,
  Erfassungshilfe, Umbuchungserkennung, Kontenabstimmung, Volltextsuche,
  Konten mit Buchungen löschen (`spec/api/protokoll.md`,
  `spec/api/buchhaltungspflege.md`, `spec/api/loeschen.md`).
  Meilenstein 4: GnuCash-Import (XML gzip/unkomprimiert, SQLite),
  Lernmodell (Naive Bayes, exakt, abschaltbar), Split-Vorlagen mit
  Szenario `beitragsaenderung` (`spec/api/gnucash.md`,
  `spec/api/lernmodell.md`, `spec/api/vorlagen.md`). Meilenstein 9
  (nach M4, vor M5 umzusetzen, E-085): Datensicherung und Wiederherstellung
  (`spec/api/sicherung.md`). Meilenstein 5: wiederkehrende Buchungen
  (zustandslos, Benachrichtigungen abschaltbar), Kredite (Tilgungsplan,
  Zinsmethoden, Aufteilung der Raten, Jahresabgleich), Berichte, Export
  CSV/PDF (`spec/api/wiederkehrend.md`, `spec/api/kredite.md`,
  `spec/api/berichte.md`). Meilenstein 6: echtes FinTS-Plugin (python-fints,
  camt/MT940, QR-TAN), PIN über systemd-creds, IMAP/OAuth2 (XOAUTH2, nur
  lesend, zwei Postfächer parallel, Ablauf im Google-Testmodus), ntfy-Zustellung
  und TAN-Erinnerungen, verschlüsselter Geheimnisspeicher (`spec/api/fints.md`,
  `spec/api/mail.md`, `spec/api/benachrichtigungen.md`,
  `spec/api/geheimnisse.md`); Attrappen unter `tests/hilfen/*_attrappe.py`.
  Meilenstein 7: gemeinsamer Haushalts-Login (scrypt, Sitzungen, Bremse,
  CSRF, Ersteinrichtung; abschaltbar, Vorgabe aus, im Betrieb über die
  ausgelieferte Umgebungsdatei an), Sicherheitsköpfe, Eingabehärtung,
  Größengrenzen, Netzbeschränkung, systemd-Units mit Härtung und
  `LoadCredentialEncrypted`, Startmodul `python -m kontor`, Beenden mit
  WAL-Checkpoint, zeitgesteuerte Sicherung, Leistung mit 50 000 Buchungen
  (`spec/api/sicherheit.md`, `spec/api/betrieb.md`, `spec/api/leistung.md`).
  Meilenstein 8 (letzter des Plans): vollständige Oberfläche nach
  `spec/api/oberflaeche.md` (Routen, `data-testid`, Mehrfachauswahl,
  Kontextmenüs, Drag and Drop, Undo über das Protokoll, Befehlspalette,
  Panels mit Layout im Browser, mobil mit Gesten, Design, PWA, TAN-Seite),
  Test-Benachrichtigung (W-005, `benachrichtigungen.md` 8); Tests mit
  Playwright/Chromium gegen uvicorn auf 127.0.0.1 (`tests/hilfen/m8.py`,
  `tests/app/m8/conftest.py`). Nach M8 offene Konzeptteile: E-150.
  Meilenstein 10 (AqBanking-Plugin) ist mit Meilenstein 29 vollständig
  entfallen (E-259): keine Spezifikation, keine Tests, kein Marker `m10`.
  Meilenstein 11 (Auftrag 2026-11-09, E-158): Kontostand bei der
  Synchronisation (Saldo als Attribut `saldo` der `Umsatzliste` aus
  `umsaetze()`, Ausgleichsbuchung gegen „Korrekturen“, FinTS `HKSAL`;
  der AqBanking-Teil ist entfallen, E-260; `spec/api/kontostand.md`), Buchungsliste
  einer Kategorie mit allen Funktionen und REST-Filter `unterkonten`,
  Kategorien in der Finanzübersicht (einklappbar), Empfänger zusammenführen
  mit neuem Namen (`oberflaeche.md` 22, `datenmodell.md` 16,
  `buchhaltungspflege.md` 10); Tests in `tests/app/m11/` (`tests/hilfen/m11.py`).
  Meilenstein 12 (Auftrag 2026-11-09, E-167): freie Statusänderung und
  Massenänderungen über `POST /api/buchungen/mehrfach/aendern` (`entsperren`
  zum Verlassen von `abgeglichen`; `PATCH` unverändert), Inline-Bearbeitung
  von Empfänger, Status und Betrag, Status-Auswahl und Bearbeiten-Dialog,
  Filterleiste anfangs eingeklappt (`datenmodell.md` 17, `oberflaeche.md`
  23); Tests in `tests/app/m12/`.
  Meilenstein 13 (freigegebene Definition 2026-11-10, E-176): Versionsnummer
  `MAJOR.MINOR` überall gleich (`kontor.__version__`, `/api/status`,
  `/api/gesundheit`, `/api/version`, Hülle, `app_version` der Sicherung),
  `GET /api/version` (Schema `Versionsangaben`), Versionsknopf am Ende der
  Navigation und About-Fenster `ueber-dialog` (`spec/api/version.md`,
  `oberflaeche.md` 24); Release-CI von kontor-app nicht getestet (2.4); keine
  Versionsnummer in Tests fest eintragen; Tests in `tests/app/m13/`
  (`tests/hilfen/m13.py`).
  Meilenstein 15 (freigegebene Definition 2026-11-10, E-181; M14 ist an das
  Feature `update` vergeben und noch nicht übernommen): Rückgängig bis zu
  einer Änderung (`bis_id`, `protokoll.md` 6.2a, E-182, E-190), mehrere
  Buchungen in einer Änderung löschen und Buchungen verschieben samt Herkunft
  eines Kontos (`datenmodell.md` 18), `sync_konten_anlegen` mit Zuordnung
  unbekannter Bankkonten (`synchronisation.md` 20, ausgeliefert `0`),
  Oberfläche `oberflaeche.md` 25 (Verlauf, Verschieben-, Zuordnungs- und
  Einstellungsdialog, gesperrter PIN-Dialog, Vorschläge je Zeile,
  Berichtsgrafiken); Tests in `tests/app/m15/` (`tests/hilfen/m15.py`), nur
  REST und Konfiguration als `kern` (E-188).
  Meilenstein 16 (freigegebene Definition 2026-11-11, E-192): neue Kette der
  Erkennung wiederkehrender Buchungen mit zusätzlichen Zahlungen am Termin
  (`wiederkehrend.md` 2.2 ersetzt, ohne Umschalter, E-193; M5-Test zur
  doppelten Zahlung angepasst, E-194), Begründung je Buchung
  `GET /api/buchungen/{id}/wiederkehrend` (`wiederkehrend.md` 8, E-195),
  Oberfläche `oberflaeche.md` 26 (Begründungsdialog, Kontextmenüeintrag mit
  Alt, Befehlspalette, Menü je Serie, Sprungziel `?buchung=`, E-196); Tests in
  `tests/app/m16/` (`tests/hilfen/m16.py`, Referenz der Kette in
  `tests/hilfen/wiederkehrend_orakel.py`), REST und Desktop-Oberfläche als
  `kern` (E-197).
  Meilenstein 17 (freigegebene Definition 2026-11-11, Feature
  `tabs-gegenbuchung`, dort „M16“ genannt, E-199): Tabs der Ansichten
  (`tab-leiste`, ein Tab je Pfad, Zustand je Tab, Speicherung im Browser
  höchstens 40, Tastatur) und Kontextmenü „Gehe zur Gegenbuchung“
  (`km-gegenbuchung`, Untermenü, Filter-Reset, kein Protokolleintrag),
  `oberflaeche.md` 27; reine Oberfläche, `openapi.yaml` unverändert; Tests in
  `tests/app/m17/` (`tests/hilfen/m17.py`), nur Browsertests, keine `kern`
  (E-202).
  Meilenstein 18 (freigegebene Definition 2026-11-13, E-206): Dokumente an
  Buchungen (PDF, JPEG, PNG, WebP, E-Mail; Typ am Inhalt, gesäuberter
  Dateiname), REST `/api/dokumente…` mit Mail-Ansicht, entschärftem HTML und
  Anhängen, eigene Sicherheitsköpfe der Inhalte, Objekt `dokument` und Feld
  `dokument_ids` im Protokoll, Sicherung nur bei Vorhandensein, Oberfläche
  `oberflaeche.md` 28 (`spec/api/dokumente.md`); Tests in `tests/app/m18/`
  (`tests/hilfen/m18.py`, multipart selbst gebaut, E-208).
  Meilenstein 19 (E-211, überarbeitete Fassung): ALF-BanCo-Import (QIF) über
  `kontor.importer.alfbanco.importiere_alfbanco` und `POST /api/import/alfbanco`,
  `POST /api/kategorien/zusammenfuehren`, Oberfläche `oberflaeche.md` 29
  (`spec/api/alfbanco.md`); Tests in `tests/app/m19/` (`tests/hilfen/m19.py`,
  QIF im Test gebaut, Orakel über `loeschen_orakel`, E-212, E-213).
  Meilenstein 20 (E-216, setzt M18 voraus): Mail-Abgleich mit erwarteten
  Zahlungen (`mail_abgleich`, Vorgabe aus, ausgeliefert an), Erkennung von
  Amazon-/PayPal-Mails, Zuordnung mit Dokumenten, Quelle `mail` und Objekt
  `erwartung` im Protokoll (Protokollform ohne `schluessel`, E-217),
  Benachrichtigung `erwartung_ueberfaellig`, Sicherung, Seite `/erwartet`
  (`oberflaeche.md` 30, `spec/api/erwartungen.md`); Tests in `tests/app/m20/`
  (`tests/hilfen/m20.py`, Mails über eine Mock-Datendatei je Test).
  Meilenstein 21 (E-221): Einzelbuchungen und Zoom in den Berichtstabellen,
  Sprungziel mittig (`oberflaeche.md` 31); Meilenstein 22 (E-223):
  Spaltenbreiten, Markierung und Zusatzmarken der Buchungsliste
  (`oberflaeche.md` 32). Beide nur Browsertests, `openapi.yaml` unverändert
  (2.17.0 nach M20), keine `kern`.
  Meilenstein 23 (E-228): Schutz der Geheimnisse mit dem Login-Passwort
  (abschaltbar, Vorgabe aus; Sperrzustand je App-Instanz, Entsperren über REST
  oder Login), gemerkte Bank-PIN, Postfach mit App-Passwort (`LOGIN` nur dafür,
  ändert K 13), `LimitCORE=0` (`spec/api/geheimnisschutz.md`, `oberflaeche.md`
  33, `openapi.yaml` 2.18.0); Tests in `tests/app/m23/` (`tests/hilfen/m23.py`,
  IMAP-Attrappe mit `passwoerter`, E-230); Betriebszustand: kein Protokoll,
  nichts in der Sicherung.
  Meilenstein 24 (E-233): Serien wiederkehrender Buchungen als abgeleitete
  Einträge von `GET /api/erwartungen` (`grund=serie`, `serien=ja`), Kategorie
  bei Erstattungen in derselben Änderung, eingebaute Mock-Mails, Kachel und
  Serien auf `/erwartet` (`erwartungen.md` 13, `oberflaeche.md` 34,
  `openapi.yaml` 2.19.0); Tests in `tests/app/m24/` (`tests/hilfen/m24.py`,
  Serien über die Referenzkette).
  Meilenstein 25 (E-238): Betragsfilter wiederkehrender Buchungen (Vorgabe der
  Instanz, ausgeliefert `toleranz` 10 %, nicht protokolliert, nicht gesichert;
  eigene Einstellung je Empfänger mit Protokoll und Sicherung), Kette mit
  Filter, Rolle `anderer_betrag`, Bruchgrund `betrag`, Mehrheitsregel
  (`wiederkehrend.md` 9, `oberflaeche.md` 35, `openapi.yaml` 2.20.0); Tests in
  `tests/app/m25/` (`tests/hilfen/m25.py`, Referenzkette mit Filtern); die
  M16-Tests setzen die Vorgabe `aus` (`tests/app/m16/conftest.py`, E-244).
  Meilenstein 26 (E-246): Bedienung auf dem Handy (Kopfzeile mit Such- und
  Tab-Knopf, Tab-Liste zum Aufklappen, Auswahlmodus durch lange Berührung mit
  `auswahl-kopf` und `mehrfach-mehr`, Wischhinweis, Blätter, Karten) und
  `Cache-Control: no-cache` mit `ETag` unter `/oeffentlich/` (`oberflaeche.md`
  36, `sicherheit.md` 6); Tests in `tests/app/m26/` (`tests/hilfen/m26.py`),
  nur 36.8 als `kern`; sechs frühere mobile Tests angepasst (E-248, Hilfe
  `m8.auswahlmenue_mobil`, `m17.tabs_aufklappen`).
  Meilenstein 27 (E-249): Label „Verdächtig“ nur mit `verdacht=ja`, Tags an
  Empfängern (`tag_ids`), Filter `zweck_gleich`/`zweck_leer`/`zweck_aehnlich`/
  `empfaenger_aehnlich`, `POST /api/dubletten` (`dublette_anlegen`) und
  Vorschläge, Mail-Liste mit `stand`/`reihenfolge`/`zuordnung`/`warum`,
  `GET /api/statistik` experimentell (`spec/api/sammel.md`, `mail.md` 6.6,
  `protokoll.md` 21, `sicherung.md` 11, `openapi.yaml` 2.21.0); Tests in
  `tests/app/m27/` (`tests/hilfen/m27.py`, Referenzen für Verdacht, Filter,
  Vorschläge, `warum`), ab M27 Protokoll mit `tests/hilfen/m27.bestand`.
  Meilenstein 28 (E-252): Oberfläche aus `feature/sammel` (Person
  Torsten/Tina mit Pflichtdialog, Navigation in Gruppen, `/mail`,
  `/statistik`, `/wiederkehrend` entfällt mit 404, Tab-Kontextmenü,
  Gruppierung, Ausschnitt mit `aria-rowcount`, Stifte statt Doppelklick,
  Verschieben nur mit Alt, Kürzel, Bestätigen, Label „Verdächtig“;
  `oberflaeche.md` 37); Tests in `tests/app/m28/` (`tests/hilfen/m28.py`),
  keine `kern`. Alle Browsertests setzen die Person vorab über
  `browser_fixtures.neue_seite` (E-253); frühere Tests nach Definition 13
  angepasst (E-254, `m8.NAV_LINKS`, `m8.stift`, `m8.zweck_editor`).
  Meilenstein 29 (E-258, Definition unter `spec/definitionen/`): nur noch die
  Bank-Plugins `mock` und `fints`; FinTS-Plugin mit `tan_verfahren()`,
  Kontenliste aus den SEPA-Kontoverbindungen, camt in der Version der Bank
  (.08, sonst .07–.02, kein Ausweichen auf MT940), TAN bei der Anmeldung;
  Bankzugang über REST (`/api/bank/zugang…`, Betriebszustand: kein Protokoll,
  nichts in der Sicherung), Diagnoseprotokoll ohne persönliche Daten, Übergang
  alter Bank-Kennungen über die Naht `kontor.sync.kennungen_als_alt_markieren`
  (E-264), Oberfläche `oberflaeche.md` 38 (`spec/api/bankzugang.md`,
  `fints.md`, `synchronisation.md` 21, `openapi.yaml` 2.22.0); Tests in
  `tests/app/m29/` (`tests/hilfen/m29.py`, FinTS-Attrappe mit zusätzlichen
  Betriebsarten, E-263); M29 ist nicht rückwärtskompatibel: M10 entfernt, M6-
  und Plugin-Test der öffentlichen Methoden angepasst (E-259 bis E-261). Der
  Abschnitt `bankzugang` wird in Browsertests über `m29.bankzugang_oeffnen`
  aufgesucht.
  Meilenstein 30 (E-268, Definition 2 mit Nachtrag unter `spec/definitionen/`):
  Kontor-Ausdrücke für Regel-Bedingungen und Filter (`spec/api/ausdruecke.md`:
  Sprache, `GET /api/ausdruck/sprache`, `POST /api/ausdruck/pruefen`,
  `/als-regel`, Parameter `filter`/`stichtag` an Buchungsliste und Export,
  `markierungen`), Regeln mit `ausdruck` oder `bedingungen`, Kategorie
  optional, Tags (`tag_ids`), erste passende Regel mit Kategorie,
  `POST /api/regeln/reihenfolge`, `/test`, `/erklaeren`,
  `POST /api/regeln/{id}/anwenden` (`kategorisierung.md` 8, `protokoll.md` 22,
  `sicherung.md` 12 mit `schemaversion` ≥ 9, `loeschen.md` 8, `openapi.yaml`
  2.23.0), Oberfläche `oberflaeche.md` 39 (Ausdrucksfeld, Filter im
  Kontoblatt mit Baukasten statt der Einzelfelder, Regeleditor mit
  Testbereich, Fenster „Regel anwenden“, Tag-Dialog); Tests in
  `tests/app/m30/` (`tests/hilfen/m30.py`: eigener Buchbestand mit
  Erwartung je Ausdruck, Bezugstag immer `stichtag` 2026-11-16), Lesarten
  E-272 und E-274. Die Protokollform der Regel ist ab M30 nicht mehr die
  REST-Darstellung: immer `tests/hilfen/m3.regel_zustand` bzw. eine
  `bestand`-Hilfe benutzen (E-271). Filter im Browser nur über
  `m8.filter_ausdruck_setzen`, `m8.filter_aufklappen` (Baukasten),
  `m8.filter_zuruecksetzen`, `m8.filter_aktiv` und `m17.filter_status_setzen`;
  die Einzelfelder `filter-von` … `filter-status-*` und `filter-umschalten`
  gibt es nicht mehr. Umstellung der Datenbank und ältere Sicherungen sind
  nicht prüfbar (E-273).
  Meilenstein 31 (E-277, Definition 3 unter `spec/definitionen/`): Lernmodell
  mit Erklärung je Buchung (`GET /api/buchungen/{id}/lernmodell`), Übersicht,
  Schwelle und `regeln_automatisch` als Einstellung der Instanz (nicht
  protokolliert, nicht gesichert), automatisch angelegte Regeln
  (`automatisch`, `empfaenger_id`, Sperre `lernregel_gesperrt` beim Löschen),
  Mock-Lerndaten (`lernmodell.md` 8–10); Monatsbericht und neun weitere
  Berichte (`berichte.md` 6, Felder des Monatsberichts E-282); Mails über die
  Bestellnummer an der Buchung (`mail_bestellnummer`, `erwartungen.md` 14;
  ausgeliefert `KONTOR_MAIL_ABGLEICH=0`); Branch statt Version
  (`version.md` 6, M13-Tests mit `m13.knopf_text_soll`); Testinstanz
  (`betrieb.md` 9); Oberfläche `oberflaeche.md` 40 (Einstellungen in
  Bereichen `allgemein`/`bank`/`mail`/`benachrichtigungen`/`sicherheit`/`daten`,
  Gruppierung mit Abschnitt und Tiefe, Berichtswahl); `openapi.yaml` 2.24.0.
  Tests in `tests/app/m31/` (`tests/hilfen/m31.py`). Einstellungen in
  Browsertests nur über `m31.einstellungen_oeffnen`/`einstellung_oeffnen`
  (Zuordnung `m31.BEREICH_VON`, E-286); `m28.perioden_soll` kennt die Ebene
  `abschnitt` und `tiefe` (E-287).
  Meilenstein 32 (E-293, Definition 4 mit Anlagen unter `spec/definitionen/`,
  nicht rückwärtskompatibel): Kontonamen je Ebene eindeutig (409
  `konto_existiert`, Bereinigen bei Import und Einspielen), Standardkategorie
  entfällt (immer `null`, sonst 422 `kategorie_ungueltig`), Statistik entfällt,
  `GET /api/empfaenger/anzahlen` und `/{id}/konten`, Mail-Liste mit `suche`,
  `gruppieren`, Zuordnen von Hand und `betrag`, Bilder fremder Server,
  Anbieter-Beschreibungen (`anbieter_verzeichnis`), PayPal nach Betrag, Fenster
  und Händler, `GET /api/konfiguration`, geplante Zahlungen mit Wiederholung
  (Sicherung `schemaversion` ≥ 10), HTTPS-Skript und Startwarnung
  (`spec/api/sammel3.md`, `betrieb.md` 10, `openapi.yaml` 2.25.0); Oberfläche
  `oberflaeche.md` 41. Tests in `tests/app/m32/` (`tests/hilfen/m32.py`).
  Frühere Tests nach E-307: `m3.stammdaten_anlegen` legt statt der
  Standardkategorien Regeln an (`m3.vorschlag_soll`), Zufallsbücher mit
  eindeutigen Namen (`normal.eindeutiger_name`), Navigation über
  `m8.NAV_LINKS`/`NAV_LOSE`/`ohne_lose_links`, Palette über
  `m8.gehe_geordnet`, Erfolgsmeldung mit „Rückgängig“ nur über
  `neue_seite(..., erfolgsmeldung=True)`, Handy-Kontoblatt über
  `m8.ansicht_aufklappen`; „Erweitert“ im Bankzugang klappt
  `m29.bankzugang_oeffnen` auf (E-310).
  Spätere Meilensteine werden erst getestet, wenn
  ihre Spezifikation steht.
- Ab M9 gehört jeder neue fachliche Zustand zur Sicherung
  (`sicherung.md` 2.3): neue Objektart in `anzahl` und Inhaltsprüfsumme, ein
  Rundreise-Test im neuen Meilenstein; Geheimnisse nie. Objektarten ab M5
  stehen nur bei Vorhandensein in `anzahl`/`inhalt`/`unterschied`
  (`sicherung.md` 2.5, E-109), damit M9-Prüfsummen gleich bleiben.
- Ab M3 gilt für jede neue Operation mit Wirkung auf den Buchbestand:
  Eintrag in der Tabelle `protokoll.md` 4 (Aktion, Quelle, Gruppe) und
  ein Fall in `tests/app/m3/test_m3_protokoll.py` bzw. eigene Protokoll-
  und Rückgängig-Tests (Invarianten T 3.5/3.6); ab M4 mit
  `tests/hilfen/m4.bestand` (inkl. Objekt `vorlage`) wie in
  `tests/app/m4/test_m4_protokoll.py`, ab M5 mit `tests/hilfen/m5.bestand`
  (inkl. Objekt `kredit`) wie in `tests/app/m5/test_m5_protokoll.py`, ab M6
  mit `tests/hilfen/m6.bestand` (inkl. Objekt `postfach`), ab M18 mit
  `tests/hilfen/m18.bestand` (Objekt `dokument`, Feld `dokument_ids`), ab M20
  mit `tests/hilfen/m20.bestand` (Objekt `erwartung`), ab M25 mit
  `tests/hilfen/m25.bestand` (Feld `wiederkehrend` der Empfängerform). Die Oberfläche
  (M8) führt keinen fachlichen Zustand ein: Undo ist Rückgängig im
  Protokoll (E-142), Layout und Design liegen im Browser (E-141).
- Spätere Meilensteine erweitern den Vertrag rückwärtskompatibel (E-029):
  neue Felder bestehender Antwortschemas optional im Schema, Pflicht nur in
  den Tests des neuen Meilensteins; Tests früherer Meilensteine bleiben
  unverändert. Antwortobjekte der Testhilfe lassen dafür gegenüber
  Erwartungen nur zusätzliche, im Schema optionale Felder zu (E-124); der
  Erweiterungslauf `KONTOR_TESTS_ZUSATZFELDER=1` muss grün bleiben. Keine
  Antwortobjekte unverändert als Anfragekörper zurückschicken.
- Ab M7: frühere Tests laufen ohne Anmeldung; der Anmeldelauf
  `KONTOR_TESTS_ANMELDUNG=1` meldet sie über `tests/hilfen/api.py` an
  (E-125). Neue Endpunkte sind geschützt, außer `sicherheit.md` 3.1 nennt
  sie; Anmeldedaten sind nie Teil von Protokoll oder Sicherung (E-135).
- Fremdsysteme (Bank, Gmail, ntfy) nie ansprechen; echte Plugins nur gegen
  lokale Attrappen testen (E-028).

## Selbstprüfung

- `tests/_selbstpruefung/` enthält eine kleine Wegwerf-Referenz (kein
  Anwendungscode) und Mutanten. Aufruf: `python -m tests._selbstpruefung`.
  Sie ist von normalen Testläufen ausgeschlossen.
- Neue oder geänderte `kern`-Tests: Selbstprüfung ausführen; die Referenz
  muss grün bleiben, jeder Mutant rot. Neue Kernregeln möglichst mit einem
  neuen Mutanten absichern. Ergebnis in `tests/_selbstpruefung/LETZTER_LAUF.md`
  (`--protokoll`) und `ERGEBNIS.md` festhalten.
- Die Referenz bleibt klein. Sie ist kein Vorbild für die Implementierung.
  M2-Teile stehen in `referenz/kontor/m2.py`, `plugins/`, `sync.py`,
  M3-Teile in `referenz/kontor/m3.py` (Protokoll entsteht dort generisch aus
  Vorher/Nachher-Abzügen) und `m3_loeschen.py`, M4-Teile in
  `referenz/kontor/m4.py` (Lernmodell, Vorlagen) und
  `referenz/kontor/importer/gnucash.py`, M9 in `sicherung.py`, M5 in
  `referenz/kontor/m5.py` (Kredite, wiederkehrende Buchungen, Berichte,
  Export) und `kredite.py`, M6 in `referenz/kontor/m6.py`, `m6_config.py` und
  `plugins/` (FinTS über python-fints, IMAP über imaplib, ntfy, Mock-Mail),
  M7 in `referenz/kontor/m7.py` (ASGI-Hülle für Netz, Anmeldung, CSRF,
  Grenzen, Köpfe), `m7_config.py`, `anmeldung.py`, `betrieb/` und
  `__main__.py`, M8 in `referenz/kontor/m8.py` und `oberflaeche/` (kleine
  Wegwerf-Seite ohne Framework nur für die Kern-Tests der Oberfläche,
  E-149; Mutanten über `<html data-mutant>`); die M10-Teile sind entfernt (E-259). M11 in `m2.py` (`_saldo_abgleich`), `plugins/` (`Umsatzliste`,
  Saldo in Mock und FinTS), `buch.py` (`unterkonten`), `m3.py`
  (Zusammenführen mit Namen) und `oberflaeche/app.js`. M12 in `buch.py`
  (`mehrfach_aendern`), `app.py`, `m3.py` (Aktion) und `oberflaeche/app.js`. M13 in `m13.py`,
  `__init__.py` (`__version__`), `m8.py` (Hülle) und `oberflaeche/app.js`. M15 in `m15.py`
  (Löschen, Verschieben, Herkunft), `m3.py` (`bis_id`), `m2.py` (Überspringen), `config.py` und
  `betrieb/kontor.env`; die M15-Browsertests sind nicht kern (E-188). M16 in `m16.py` (Kette,
  Begründung; `m5.py` nutzt die Kette) und `oberflaeche/app.js` (Dialog, Menü je Serie, Sprungziel). M17 hat keine Referenzteile und keine Mutanten (nur Browsertests, E-202). Die Kern-Tests von M18, M19, M20, M23 und M24 haben keine Referenz und werden von der Selbstprüfung ausgelassen (`OHNE_REFERENZ` in `__main__.py`, E-225, E-243); ihre Abnahme ist der Lauf gegen die App. M21 und M22 haben nur Browsertests (E-221, E-223). M25 in `m25.py` (Filter, Kette mit Filter, Mehrheitsregel, Einstellungen), eingebunden in `m5.py` (`_serie`, `pruefen`), `m16.py` (Begründung), `m3.py` (Empfängerform, Aktion) und `sicherung.py` (`SCHEMAVERSION = 6`), Mutanten `m25_*` (E-243). M26 in `m8.py` (`mit_cache`, Mutanten `m26_*`); M27 ausgelassen (`OHNE_REFERENZ`, E-256); M28 ohne neue Kern-Tests, die geänderten Kern-Tests von M8/M12/M13 laufen gegen die nachgezogene `oberflaeche/app.js` (Gruppen, Alt+1…7, Palette, Stift für den Status), Mutanten `m28_*`; die Oberflächenmutanten von M16 sind entfallen (E-256). M29 ausgelassen (`OHNE_REFERENZ`, E-266); für die geänderten Kern-Tests von M1/M6 hat die Referenz `FintsBankPlugin.tan_verfahren` und kein `aqbanking` mehr. M30 ausgelassen (`OHNE_REFERENZ`, E-275); die Referenz kennt die neuen Regel-Felder nicht (das Schema lässt beide Formen zu), ihre Oberfläche hat den Umschalter `filter-baukasten-umschalten`. M31 ausgelassen (`OHNE_REFERENZ`, E-292); die geänderten M13-Kern-Tests laufen gegen die Referenz (kein `zweig-link`). M32 ausgelassen (`OHNE_REFERENZ`, E-308); für die nachgezogenen Kern-Tests prüft die Referenz Kontonamen je Ebene (`buch.namen_pruefen`, `bereinigen` in den Importern, Rückgängig, Löschen), lehnt Standardkategorien ab und hat Tags/Konfiguration in Navigation und Palette; Mutanten `m32_*`, die Mutanten der Standardkategorie sind entfallen. Die Selbstprüfung enthält einen zweiten grünen Lauf mit
  Zusatzfeldern (E-124).

## Git

- Direkt auf `main` committen und pushen, in kleinen Schritten. Keine
  Branches, keine Pull Requests, kein Force-Push. Vor jedem Push
  `git pull --rebase origin main`.
- `user.name` ist „Kontor Test-Thread“; E-Mail und Signierung nicht ändern.

## Vor dem Abschluss eines Auftrags

1. `python -m pytest --voll tests/generator tests/spec` grün.
2. `python -m pytest --voll --collect-only -q` ohne Sammelfehler.
3. Selbstprüfung ausgeführt und Ergebnis festgehalten.
4. `ERGEBNIS.md` aktualisiert, `git status` sauber, alles gepusht.
5. Im Projektchat nur posten, wenn alles fertig ist oder etwas wirklich
   blockiert – auf Deutsch, ohne Zwischenstände.
