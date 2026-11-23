# Tests gegen eine installierte kontor-app ausführen

Alle Befehle im Wurzelverzeichnis von **kontor-tests**. Die Tests greifen
nur über `spec/api/python-api.md` (Paket `kontor`) und `spec/api/openapi.yaml`
(REST über `fastapi.testclient.TestClient`) auf die Anwendung zu. Es werden
keine echten Daten verwendet; jede App im Test bekommt eine eigene temporäre
SQLite-Datenbank. Nur die Oberflächentests (M8, `spec/api/oberflaeche.md`)
starten die App mit uvicorn auf `127.0.0.1` (freier Port, im Testprozess) und
bedienen sie mit Playwright und Chromium headless.

## 1. Voraussetzungen

- Python ≥ 3.11
- ein Checkout von kontor-app (mit `pyproject.toml`, Distribution `kontor`)
- ein Checkout von kontor-tests (dieses Repository)

## 2. Installation

Empfohlen in einer virtuellen Umgebung:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e <pfad-zu-kontor-app>
pip install -r requirements-tests.txt
```

Ohne virtuelle Umgebung (systemweites Python, z. B. in Containern) an jeden
`pip install` zusätzlich `--break-system-packages` anhängen:

```bash
pip install --break-system-packages -e <pfad-zu-kontor-app>
pip install --break-system-packages -r requirements-tests.txt
```

FastAPI, Starlette, `python-multipart` usw. bringt die Anwendung als eigene
Abhängigkeiten mit; `requirements-tests.txt` enthält nur, was die Tests
selbst brauchen (pytest, Hypothesis, jsonschema, PyYAML, httpx,
openapi-spec-validator, ab M5 `pypdf` zum Lesen des PDF-Exports, ab M6
`fints` (python-fints, Segmentklassen der FinTS-Attrappe), `cryptography`
(Testzertifikate) und `requests`, ab M8 `playwright` für die Browsertests).

Browser für M8: `python -m playwright install chromium` (oder ein vorhandenes
Chrome/Chromium; Pfad mit `KONTOR_TESTS_CHROMIUM=/pfad/zu/chrome`). Die
Fixture versucht das gebündelte Chromium, dann den Kanal `chrome`, dann
`/usr/bin/google-chrome`. Startet kein Browser oder fehlt Playwright, werden die
Browsertests (Marker `browser`) mit der Meldung „Browsertests übersprungen: …“
übersprungen; die übrigen M8-Tests (Auslieferung, W-005) laufen trotzdem.

Kontrolle: Die erste Zeile jedes Testlaufs zeigt, welche Anwendung gefunden
wurde, z. B.

```
kontor: installiert, Version 0.1.0, Pfad /…/kontor-app/src/kontor/__init__.py
```

## 3. Tests ausführen

**Schnelllauf und Volllauf (E-175).** `python -m pytest` ohne `-m` ist ein
Schnelllauf: ohne die Marker `leistung`, `browser` und `langsam`,
Hypothesis-Profil `schnell` (10 Beispiele). Für die Abnahme eines
Meilensteins zählt der Volllauf mit `--voll` (oder `KONTOR_TESTS_VOLL=1`).
Jeder `-m`-Ausdruck und jede Knoten-ID (`datei.py::test`) wählt selbst aus
und ist kein Schnelllauf. Die Kopfzeile nennt Laufart und Profil.

```bash
python -m pytest -n auto              # Alltag: Schnelllauf, parallel (pytest-xdist)
python -m pytest --voll -n auto       # Volllauf: alle Tests (Generator, Spezifikation, App), Profil standard
python -m pytest --voll               # Volllauf nacheinander
python -m pytest -m leistung          # Leistungstests getrennt, ohne -n (Zeitgrenzen)
python -m pytest tests/app            # nur die App-Tests
python -m pytest -m "not langsam"     # ohne Tests, die große Fixtures importieren
python -m pytest -m kern              # nur die Kern-Tests
python -m pytest -m m1                # nur App-Tests von Meilenstein 1 (tests/app/*.py)
python -m pytest -m m2                # nur Tests von Meilenstein 2 (tests/app/m2/, M2-Generatortests)
python -m pytest -m m3                # nur Tests von Meilenstein 3 (tests/app/m3/, M3-Generatortests)
python -m pytest -m m4                # nur Tests von Meilenstein 4 (tests/app/m4/, M4-Generatortests)
python -m pytest -m "m4 and not langsam"  # M4 ohne die großen Überschneidungs-Imports
python -m pytest -m m9                # nur Tests von Meilenstein 9 Datensicherung (tests/app/m9/)
python -m pytest -m m5                # nur Tests von Meilenstein 5 (tests/app/m5/, M5-Generatortests)
python -m pytest -m m6                # nur Tests von Meilenstein 6 (tests/app/m6/, tests/attrappen/, M6-Generatortests)
python -m pytest -m m7                # nur Tests von Meilenstein 7 (tests/app/m7/, M7-Generatortests)
python -m pytest -m "m7 and not leistung"  # M7 ohne die Leistungstests
python -m pytest -m m8                # Meilenstein 8 Oberfläche und W-005 (tests/app/m8/, M8-Generatortests)
python -m pytest -m "m8 and not browser"   # M8 ohne Browser (Auslieferung, Test-Benachrichtigung)
python -m pytest tests/app/m8 -n 2    # mit pytest-xdist parallel (je Prozess ein Chromium)
python -m pytest -m m29               # Meilenstein 29 FinTS/camt, Bankzugang (tests/app/m29/; ersetzt M10)
python -m pytest -m m30               # Meilenstein 30 Kontor-Ausdrücke, Filter, Regeln mit Ausdruck und Tags (tests/app/m30/)
python -m pytest -m m31               # Meilenstein 31 Lernmodell-Transparenz, automatische Regeln, Berichte, Bestellnummer-Mails, Einstellungen in Bereichen (tests/app/m31/)
python -m pytest -m m32               # Meilenstein 32 Sammelbranch sammel3: Kontonamen, Empfänger, Mail-Blatt, Anbieter, PayPal, geplante Zahlungen, Konfiguration, HTTPS, Oberfläche (tests/app/m32/)
python -m pytest -m m11               # Meilenstein 11 Kontostand, Kategorien als Konten, Empfänger (tests/app/m11/)
python -m pytest -m m12               # Meilenstein 12 Statusänderung, Massenänderungen, Filterleiste (tests/app/m12/)
python -m pytest -m m13               # Meilenstein 13 Versionsnummer, GET /api/version, About-Fenster (tests/app/m13/)
python -m pytest -m m15 --voll -n 2   # Meilenstein 15 Sammelpaket Bedienung (tests/app/m15/, mit Browsertests)
python -m pytest -m m16 --voll -n 2   # Meilenstein 16 wiederkehrende Buchungen: Kette und Begründung (tests/app/m16/, mit Browsertests)
python -m pytest -m m17 -n 4 tests/app/m17  # Meilenstein 17 Tabs und Gegenbuchung (nur Browsertests)
python -m pytest -m leistung          # nur die Leistungstests (50 000 Buchungen, einige Minuten)
python -m pytest -m "not leistung"    # alles außer den Leistungstests
python -m pytest tests/attrappen      # Selbsttests der lokalen Attrappen (ohne App)
python -m pytest -m "m2 and not kern" # Marker lassen sich kombinieren
python -m pytest tests/app/test_filter.py -k suche   # Auswahl
python -m pytest -x -q                # beim ersten Fehler abbrechen
```

`python -m pytest` (statt nur `pytest`) stellt sicher, dass das Python der
Umgebung verwendet wird, in der `kontor` installiert ist. Die Konfiguration
steht in `pytest.ini` (`testpaths = tests`, `pythonpath = .`).

Testbereiche:

| Verzeichnis/Datei | Inhalt |
| --- | --- |
| `tests/generator/` | Testdatengenerator: Reproduzierbarkeit, gültige Fixtures, Test-IBANs (ohne App) |
| `tests/spec/` | `openapi.yaml` gültig und vollständig, Vertragsprüfer (ohne App) |
| `tests/app/test_paket.py` | Paket, Module, Fehlerklassen, `KontorConfig`, `from_env` |
| `tests/app/test_api_allgemein.py` | Status, Fehlerformat, 404/405/422, Header, Beträge |
| `tests/app/test_konten.py` | Konten, IBAN, Hierarchie, Löschen, Salden, Kontenübersicht |
| `tests/app/test_empfaenger_tags.py` | Empfänger, Tags (Eindeutigkeit, Umbenennen, Löschen) |
| `tests/app/test_buchungen.py` | Splits, Kategorie, Betrag, Statusübergänge, Sperre |
| `tests/app/test_invarianten.py` | globale Invarianten mit zufälligen Operationsfolgen |
| `tests/app/test_import_kmy.py` | KMyMoney-Import, Sonderfälle, Python-API |
| `tests/app/test_import_fehler.py` | Fehlerfälle ohne Teilimport |
| `tests/app/test_idempotenz.py` | Idempotenz, inkrementeller Import, Zuordnung |
| `tests/app/test_dubletten.py` | Dublettenerkennung und Auflösen |
| `tests/app/test_filter.py` | alle Filter, Sortierung, Paginierung |
| `tests/app/test_mehrfach.py` | Mehrfachbearbeitung (Kategorie, Tags, Atomarität) |
| `tests/app/test_plugins.py` | Bank-/Mail-Plugins, Mock-Plugins, Szenarien |
| `tests/app/test_mock_modus.py` | Mock-Modus: eigene Datenbank, Hinweis, keine Verbindungen |
| `tests/generator/test_sync_daten.py` | M2-Fixtures gegen ein unabhängiges Orakel (ohne App) |
| `tests/app/m2/test_m2_paket.py` | M2: neue Fehlerklassen, `TanAntwort`, Signaturen, Konfiguration, `kontor.sync` |
| `tests/app/m2/test_m2_mock_bank.py` | M2: Mock-Bank-Plugin mit TAN-Freigabe und PIN |
| `tests/app/m2/test_m2_sync.py` | M2: Kontozuordnung, Übernahme, Wiederholung, Zeitraum, Mock-Uhr (inkl. Hypothesis) |
| `tests/app/m2/test_m2_altbestand.py` | M2: Abgleich beim Abruf mit KMyMoney-Altbestand |
| `tests/app/m2/test_m2_fehler.py` | M2: Bankfehler, Wiederholung ohne Datenverlust, Benachrichtigungen |
| `tests/app/m2/test_m2_tan.py` | M2: TAN-Anforderung, Bild, Antwort, Ablauf, Abbruch, Neustart |
| `tests/app/m2/test_m2_pin.py` | M2: PIN nur im Arbeitsspeicher, nirgends gespeichert oder ausgegeben |
| `tests/app/m2/test_m2_planer.py` | M2: Planer abschaltbar, `planer_takt`, Intervall, Wiederholung, Thread |
| `tests/app/m2/test_m2_regeln_api.py` | M2: Regel-CRUD, Validierung, Reihenfolge, Bezüge |
| `tests/app/m2/test_m2_regeln_anwenden.py` | M2: Bedingungen, Priorität, Anwenden (inkl. Hypothesis) |
| `tests/app/m2/test_m2_vorschlag.py` | M2: Kategorisierung beim Abruf, Vorschläge annehmen/ablehnen |
| `tests/generator/test_m3_daten.py` | M3-Fixtures (Umbuchungen, Auszüge, Aliase, Suche) gegen ein unabhängiges Orakel (ohne App) |
| `tests/app/m3/test_m3_paket.py` | M3: Konfiguration `umbuchung_automatisch`, `umbuchung_fenster_tage`, `from_env` |
| `tests/app/m3/test_m3_protokoll.py` | M3: jede Operation erzeugt genau eine Änderung mit genau den geänderten Objekten; Rückgängig/Wiederholen; keine Änderung ohne Wirkung; Lesen und Filter |
| `tests/app/m3/test_m3_rueckgaengig.py` | M3: Zustands- und Bezugsprüfung, mehrere Änderungen, Gruppen, Wirksamkeit, zufällige Folgen rückwärts (Hypothesis) |
| `tests/app/m3/test_m3_protokoll_sync.py` | M3: Synchronisation, Planer, TAN-Fortsetzung und Import im Protokoll; ganzer Lauf rückgängig |
| `tests/app/m3/test_m3_empfaenger.py` | M3: Aliase, Standardkategorie, Ändern, Löschen, Zusammenführen; Aliase bei Abruf und Import |
| `tests/app/m3/test_m3_erfassen.py` | M3: Erfassungshilfe (Ausgabe, Einnahme, Umbuchung, Korrektur), Fehler, Invarianten (Hypothesis) |
| `tests/app/m3/test_m3_umbuchung.py` | M3: Umbuchungserkennung je Abrufstufe, fremde IBAN, auf Wunsch, von Hand, Salden |
| `tests/app/m3/test_m3_abstimmung.py` | M3: Kontenabstimmung mit Kontoauszügen, Differenz, Sperre, Aufheben, Filter |
| `tests/app/m3/test_m3_suche.py` | M3: Volltextsuche (Umlaute, ß, Akzente, NFD, Ligatur) gegen Orakel (inkl. Hypothesis) |
| `tests/app/m3/test_m3_konto_loeschen.py` | M3: Konten und Kategorien mit Buchungen löschen (`loeschen.md`), Konfliktbuchungen, Rückgängig (inkl. Hypothesis gegen `tests/hilfen/loeschen_orakel.py`); nur das Löschen: `python -m pytest tests/app/m3/test_m3_konto_loeschen.py` |
| `tests/generator/test_m4_daten.py` | M4-Fixtures: GnuCash-Dateien gegen einen unabhängigen Leser (`tests/hilfen/gnc_leser.py`), Störfälle, Überschneidung mit KMyMoney, Lerndaten (80/20, Mindestgenauigkeit über das Orakel), Vorlagen-Wahrheit (ohne App) |
| `tests/app/m4/test_m4_paket.py` | M4: `lernmodell_automatisch`, Szenario `beitragsaenderung` (Konfiguration, Mock-Bank), Modul `kontor.importer.gnucash` |
| `tests/app/m4/test_m4_gnucash_import.py` | M4: GnuCash-Import XML (gzip/unkomprimiert) und SQLite exakt gegen die Generatorwahrheit, Python-API, Importvorgang, Idempotenz, erweiterte Fassung, Sonderfälle, Aliase (inkl. Hypothesis) |
| `tests/app/m4/test_m4_gnucash_fehler.py` | M4: Störfälle beider Formate ohne Teilimport und ohne Protokolleintrag, SQLite-Schemafehler, Datei bleibt unverändert, zufällige Bytes (Hypothesis) |
| `tests/app/m4/test_m4_gnucash_zuordnung.py` | M4: Zuordnung über Quellen (KMyMoney ↔ GnuCash), Dubletten, überschneidende Zeiträume ohne doppelte Salden (`langsam`) |
| `tests/app/m4/test_m4_lernmodell.py` | M4: Lernmodell gegen das Orakel `tests/hilfen/lern_orakel.py` (inkl. Hypothesis), Trainingsmenge, Schwelle 7/10, Korrektur, Validierung, Mindestgenauigkeit auf Generatordaten |
| `tests/app/m4/test_m4_lernmodell_anwendung.py` | M4: Lernmodell anwenden, Annehmen/Ablehnen, Synchronisation mit `lernmodell_automatisch`, Stufenfolge Regel → Standardkategorie → Lernmodell, eigene Gegen-IBAN, Erfassen |
| `tests/app/m4/test_m4_vorlagen_api.py` | M4: Split-Vorlagen anlegen, validieren, ordnen, ändern, löschen, Bezüge, Konto löschen, Protokoll |
| `tests/app/m4/test_m4_vorlagen_sync.py` | M4: Vorlagen bei der Synchronisation (Szenarien `normal` und `beitragsaenderung`), keine Toleranz (Hypothesis), Benachrichtigung, Vorrang vor Regeln, Anwenden auf vorhandene Buchungen |
| `tests/app/m4/test_m4_protokoll.py` | M4: GnuCash-Import und Lernmodell-Vorschlag im Protokoll, zufällige Folgen mit M4-Operationen rückwärts (Hypothesis) |
| `tests/app/m3/test_m3_sync_konto_fehlt.py` | M3-Nachtrag: gelöschte Bankkonten bei der Synchronisation (`synchronisation.md` 16) – Status `konto_fehlt`, Überspringen, Benachrichtigung, Wiederherstellen mit allen/nur neuen Umsätzen, Ignorieren, Rückgängig; einzeln: `python -m pytest tests/app/m3/test_m3_sync_konto_fehlt.py` |
| `tests/app/m9/test_m9_export.py` | M9: Sicherung erstellen – ZIP-Aufbau, Manifest, Dateiname, unabhängig nachgerechnete Prüfsummen, SQLite ohne Views/Trigger/WAL, keine Protokollreste, keine PIN, `kontor.sicherung.erstelle_sicherung` |
| `tests/app/m9/test_m9_einspielen.py` | M9: Rundreise in leere Instanz, Ersetzen, Identität ohne neue Version, Rückgängig/Wiederholen, Probelauf, Bestätigung, Modus Mock/Echt, IDs, Vorlagen (braucht M4), Texte (Hypothesis) |
| `tests/app/m9/test_m9_fehler.py` | M9: ungültige, fremde und manipulierte Sicherungen mit festem `details.grund`, Prüfreihenfolge, nie Teiländerung |
| `tests/app/m9/test_m9_sync.py` | M9: Kennungen und Bankkonto-Zustand in der Sicherung, Abruf nach älterer Sicherung genau einmal, Rückgängig, Sperre bei TAN |
| `tests/generator/test_m5_daten.py` | M5-Fixtures: Tilgungspläne des Generators (Decimal) gegen das Bruch-Orakel `tests/hilfen/kredit_orakel.py`, Feiertage, Kredit-Synchronisation, Serien und Benachrichtigungen gegen `tests/hilfen/wiederkehrend_orakel.py`, Berichtswahrheit (ohne App) |
| `tests/app/m5/test_m5_paket.py` | M5: `wiederkehrend_automatisch`, `KreditRateZuKlein`, `kontor.kredite.tilgungsplan` |
| `tests/app/m5/test_m5_tilgungsplan.py` | M5: Tilgungspläne aller Zinsmethoden über Python und REST gegen die Generatorwahrheit, Validierung, zufällige Parameter gegen das Orakel und Rundungsschranke (Hypothesis) |
| `tests/app/m5/test_m5_kredite_api.py` | M5: Kredit anlegen mit Anfangsbuchung, Prüfreihenfolge der Fehler, Plan, Ändern, Löschen, Konten mit Kreditbezug |
| `tests/app/m5/test_m5_kredit_zuordnen.py` | M5: vorhandene Raten erkennen und in Zins/Tilgung aufteilen (Toleranz, Betrag, Bedingungen, gesperrt, Schlussrate), Löschen einer Rate, Protokoll |
| `tests/app/m5/test_m5_jahresabgleich.py` | M5: Jahresabgleich mit genau einer Korrekturbuchung, Splits je Differenz, Status abgeglichen, Probelauf, ein Abgleich je Jahr, Rückgängig |
| `tests/app/m5/test_m5_kredit_sync.py` | M5: Raten beim Abruf aufteilen (alle Zinsmethoden), inaktiv, Protokoll des Laufs, Jahresabgleich mit Jahresauszügen der Generatorwahrheit |
| `tests/app/m5/test_m5_wiederkehrend.py` | M5: Serien (monatlich, vierteljährlich, jährlich, Verschiebungen, Lücke, Status) gegen Generatorwahrheit und Orakel, handgebaute Grenzfälle |
| `tests/app/m5/test_m5_benachrichtigungen.py` | M5: neuer Empfänger, geänderter Betrag, ausbleibende Zahlung (positiv/negativ, genau einmal), automatische Prüfung nach dem Abruf gegen die Wahrheit |
| `tests/app/m5/test_m5_berichte.py` | M5: Kontostandsverlauf und Einnahmen/Ausgaben gegen die Generatorwahrheit für `standard.kmy` und gegen die Summe der Splits, Umbuchungen, leere Konten/Zeiträume, Vorgaben, Fehler |
| `tests/app/m5/test_m5_export.py` | M5: CSV-Format, verlustfreie Rundreise (auch beliebige Texte, Hypothesis), Filter; PDF mit Marken je Buchung (pypdf), ohne Netz |
| `tests/app/m5/test_m5_protokoll.py` | M5: Kreditoperationen im Protokoll, Rückgängig/Wiederholen, Bezugs- und Zustandsprüfung, Folge rückwärts |
| `tests/app/m5/test_m5_sicherung.py` | M5: Kredite in der Sicherung (Manifest, Inhaltsprüfsumme, Rundreise, ID-Zähler, Unterschied, Rückgängig), ohne Kredite kein Schlüssel |
| `tests/generator/test_m6_daten.py` | M6-Fixtures: MT940/camt-Bruchstücke, mbox-Postfächer und Erinnerungsfälle gegen die Orakel in `tests/hilfen/m6_orakel.py` (ohne App) |
| `tests/attrappen/test_attrappen.py` | M6: FinTS-, IMAP-, OAuth2- und ntfy-Attrappe mit python-fints, imaplib und HTTP (ohne App) |
| `tests/app/m6/test_m6_paket.py` | M6: Module, Fehlerklassen, Konfiguration, URL-/Loopback-Regeln, Erzeugen ohne Verbindung |
| `tests/app/m6/test_m6_fints_plugin.py` | M6: FinTS-Plugin gegen die Attrappe (Konten, camt/MT940, Zeiträume, Vormerkungen, TAN mit QR, Fehler, TLS, Vertrag mit Mock) |
| `tests/app/m6/test_m6_fints_sync.py` | M6: Synchronisation im Echtmodus über FinTS (TAN-Ablauf per REST, Bild, Vertrag echt = Mock, Fehler ohne Datenverlust) |
| `tests/app/m6/test_m6_pin_systemd.py` | M6: PIN aus `$CREDENTIALS_DIRECTORY`, Sperre nach falscher PIN, 409 für die Eingabe |
| `tests/app/m6/test_m6_geheimnisse.py` | M6: Geheimnisspeicher (Schlüssel, AES-GCM, nie Klartext, nie in der Sicherung) |
| `tests/app/m6/test_m6_benachrichtigung.py` | M6: ntfy-Plugin und Zustellung (Körper, Token, Wiederholung, Höchstzahl, jeder Auslöser genau einmal) |
| `tests/app/m6/test_m6_tan_erinnerung.py` | M6: TAN-Push und Erinnerungen in Abständen |
| `tests/app/m6/test_m6_imap_plugin.py` | M6: IMAP-Plugin gegen die IMAP-Attrappe (Abbildung, nur lesend, Erneuern, TLS, parallel, Vertrag) |
| `tests/app/m6/test_m6_postfaecher.py` | M6: Postfächer, Protokoll, Rückgängig, Status, Sicherung |
| `tests/app/m6/test_m6_mail_abruf.py` | M6: Mail-Abruf im Mock-Modus (Spiegel, Überlappung, Filter, Fehler, Planer) |
| `tests/app/m6/test_m6_oauth.py` | M6: OAuth2 mit PKCE, Token-Erneuerung, Vorwarnung, Ablauf/Widerruf, Abruf im Echtmodus |
| `tests/generator/test_m7_gross.py` | M7: großer Datensatz (50 000 Buchungen) reproduzierbar, Prüfsumme im MANIFEST, Probewerte unabhängig im XML gezählt (ohne App) |
| `tests/app/m7/test_m7_paket.py` | M7: Module, Konfiguration (Vorgaben, Grenzen, `from_env`), Passwort-Hash scrypt unabhängig nachgerechnet, NFC, unförmige Hashes |
| `tests/app/m7/test_m7_anmeldung.py` | M7: alle Pfade ohne Sitzung 401, Weiterleitung zur Anmeldeseite, Cookie-Attribute, Bremse mit Verdopplung, Leerlauf und Höchstdauer, Mock-Uhr wirkungslos, Abmelden, Passwort ändern, CSRF und Herkunft, Ersteinrichtung mit Einrichtungscode, Anmeldeseite |
| `tests/app/m7/test_m7_haertung.py` | M7: Sicherheitsköpfe und CSP, keine Inline-Skripte, SQL-Injection und XSS wörtlich, Pfadtraversal, robuste Eingaben, Größengrenzen (genau an der Grenze), Netzbeschränkung, keine Geheimnisse in Logs |
| `tests/app/m7/test_m7_betrieb.py` | M7: systemd-Units, Drop-in, sysusers und Umgebungsdatei statisch; zeitgesteuerte Sicherung mit Aufbewahrung; Kommandozeilen; WAL und Checkpoint; Beenden während eines Laufs; Startmodul mit SIGTERM |
| `tests/app/m7/test_m7_sicherung.py` | M7: Anmeldedaten nicht in der Sicherung, Einspielen lässt die Anmeldung unverändert, nichts davon im Protokoll |
| `tests/app/m7/test_m7_leistung.py` | M7: 15 Grenzwerte mit 50 000 Buchungen (Marker `leistung`) |
| `tests/generator/test_m8_daten.py` | M8: Datensätze der Oberflächentests unabhängig im XML geprüft, nur Test-IBANs (ohne App) |
| `tests/app/m8/test_m8_testbenachrichtigung.py` | W-005: `POST /api/benachrichtigungen/test` mit Mock-, ntfy- (Attrappe) und ohne Plugin, ohne Spuren in Liste, Zustellstatus, Protokoll und Sicherung (ohne Browser) |
| `tests/app/m8/test_m8_auslieferung.py` | M8: Hülle für alle Routen, Kopf, nur externe Skripte derselben Herkunft, Mock-Hinweis, kein Buchbestand im HTML, Manifest mit Symbolen, `/sw.js` (ohne Browser) |
| `tests/app/m8/test_m8_grundgeruest.py` | M8: Routen direkt und über die Navigation, Titel, `aria-current`, ohne Neuladen, Zurück/Vor, Landmarken, Mock-Hinweis immer sichtbar, mobiles Menü, Layoutwechsel, kein waagerechtes Scrollen |
| `tests/app/m8/test_m8_kontoansicht.py` | M8: Finanzübersicht gegen die Generatorwahrheit, Liste = REST, Darstellung (Beträge, Datum, Pfade), Texte nur als Text, sieben Filterfälle desktop und mobil, Filter in der URL, Sortierung, seitenweises Laden, Vorschläge |
| `tests/app/m8/test_m8_auswahl.py` | M8: Mehrfachauswahl mit Klick, Strg, Umschalt und Tastatur; Mehrfachbearbeitung (Kategorie, Tags, Löschen), atomar bei Fehlern |
| `tests/app/m8/test_m8_kontextmenue.py` | M8: Kontextmenü (Auswahlregel, Tastatur, deaktivierte Einträge), Kategorie setzen, Dublette, Kontomenü (Umbenennen, Unterkonto, Verschieben, Löschen nach `loeschen.md` 5), lange Berührung |
| `tests/app/m8/test_m8_tastatur.py` | M8: Befehlspalette (Umlautfaltung, Wörter, Pfeile, Konten), Alt+1…8, `/`, `?`, Entf, Enter |
| `tests/app/m8/test_m8_bearbeiten.py` | M8: Inline-Bearbeitung, Strg+Z/Strg+Umschalt+Z/Strg+Y über das Protokoll, mehrere Änderungen in einem Schritt, Konflikt, Protokollseite |
| `tests/app/m8/test_m8_split_dnd.py` | M8: Split-Dialog desktop und mobil, Drag and Drop Buchung → Kategorie und Kategorien umsortieren |
| `tests/app/m8/test_m8_panels_mobil.py` | M8: Panels (Größe, Einklappen, Verschieben, Speichern, Zurücksetzen), kompakte Liste, Wischen, lange Berührung, Rückgängig ohne Tastatur |
| `tests/app/m8/test_m8_thema_pwa.py` | M8: helles/dunkles Design mit Kontrast, Wechsel ohne Neuladen; PWA installierbar, Service Worker, offline nur Hülle, keine Daten im Browser |
| `tests/app/m8/test_m8_tan_kredit.py` | M8: TAN-Seite mit QR-Code, Speichern (Bytes), Teilen (Attrappe), falsche/richtige TAN, Abbruch, Ablauf, PIN-Dialog; Kreditabgleich desktop und mobil |
| `tests/app/m8/test_m8_seiten.py` | M8: Kategorienbaum, Konten, Einstellungen (Test-Benachrichtigung, Geheimnisse, Sicherung), Import, Erfassen, Berichte, wiederkehrende Buchungen, Seiten im Mindestumfang |
| `tests/app/m8/test_m8_anmeldung_a11y.py` | M8: Anmeldung, Ersteinrichtung, CSRF, Abmelden, abgelaufene Sitzung; zugängliche Namen (Barrierefreiheitsbaum von Chromium), sichtbarer Fokus, Dialoge |
| `tests/app/m11/test_m11_kontostand.py` | M11: Saldo mit dem Umsatzabruf (Mock, `Umsatzliste`), Konfiguration, Saldoabgleich im Lauf, Ausgleichsbuchung gegen „Korrekturen“, Kennung, Benachrichtigung, Protokoll und Rückgängig (`kontostand.md`) |
| `tests/app/m11/test_m11_fints_saldo.py` | M11: FinTS-Plugin mit `HKSAL` im selben Dialog gegen die Attrappe (`saldo_anbieten`), Soll-Saldo, TAN, abgelehnte Saldenabfrage, Lauf im Echtmodus |
| `tests/app/m11/test_m11_rest.py` | M11: Filter `unterkonten` (Liste, Betrag, Summe, Export), Empfänger zusammenführen mit neuem Namen, Zuordnung neuer Umsätze über die Aliase |
| `tests/app/m11/test_m11_oberflaeche.py` | M11: Browsertests – Kategorien in der Finanzübersicht (einklappbar, gespeichert), Buchungsliste einer Kategorie (Spalte Konto, Filter, Unterkonten), Empfänger zusammenführen (Dialog), Kontostand auf `/sync` |
| `tests/app/m12/test_m12_rest.py`, `test_m12_oberflaeche.py` | M12: `mehrfach/aendern`, Inline-Bearbeitung, Status-Auswahl, Bearbeiten-Dialog, Filterleiste |
| `tests/app/m13/test_m13_version.py` | M13: Versionsschema `MAJOR.MINOR`, gleiche Version in Paket, `/api/status`, `/api/gesundheit`, `/api/version`, Hülle und Sicherung; Felder von `GET /api/version`, 405, Schutz, ohne Wirkung (`version.md`) |
| `tests/app/m15/test_m15_rueckgaengig_bis.py` | M15: Rückgängig bis (`bis_id`) gegen Abzüge und ein Modell der Wirksamkeit, verschachtelte Folgen, Import und Lauf, Fehlerfälle, ohne Nettowirkung 409, Zufallsfolgen (Hypothesis) |
| `tests/app/m15/test_m15_mehrfach.py` | M15: `mehrfach/loeschen` (Zwillingsvergleich mit `DELETE`), `mehrfach/verschieben` (Auswahl, Import- und Laufgruppe, Prüfreihenfolge), Herkunft, Sicherung unverändert |
| `tests/app/m15/test_m15_sync_zuordnung.py` | M15: `sync_konten_anlegen`, ausgelieferte Umgebungsdatei, Überspringen mit `nicht_zugeordnet`, Benachrichtigung, Zuordnen per `PATCH`/`POST`, Folgelauf |
| `tests/app/m15/test_m15_oberflaeche.py` | M15: Browsertests – Rückgängig bis hierher, Löschen mit einer Anfrage, Verschieben-Dialog, Zuordnungsdialog und Folgelauf, `/sync`, Kontoeinstellungen, PIN-Dialog gesperrt, Vorschläge je Zeile, Berichtsgrafiken (`oberflaeche.md` 25) |
| `tests/app/m17/test_m17_tabs.py` | M17: Browsertests – Tab-Leiste und Attribute, ein Tab je Pfad, Zustand beim Wechsel und bei Zurück/Vor, Anfordern über Navigation, direkter Aufruf, Schließen und Wiederöffnen, Speicherung (lazy, höchstens 40, ungültig/nicht verfügbar), Aktualität, Tastatur, mobil (`oberflaeche.md` 27.1) |
| `tests/app/m17/test_m17_gegenbuchung.py` | M17: Browsertests – „Gehe zur Gegenbuchung“: Position und Aktivierung, Konto↔Kategorie, Umbuchung mit Nachladen, Untermenü, Filter-Reset mit Hinweis, mobil, Fehlerfälle, ohne Wirkung (`oberflaeche.md` 27.2, 27.3) |
| `tests/app/m13/test_m13_oberflaeche.py` | M13: Browsertests – Versionsknopf am Ende der Navigation, About-Fenster (Inhalt, Build-Zweige, Fokus, Esc, Tab, mobil), Fehlerfall und 401 (`oberflaeche.md` 24) |
| `tests/app/m16/test_m16_kette.py` | M16: neue Kette (`wiederkehrend.md` 2.2) – Beispiele der Definition, Anker nach Länge/Betrag/jünger, Vorgänger-Auswahl, zusätzliche Zahlungen zwischen Gliedern, Kandidaten des vorigen Schritts, fremde und ausgelassene Zahlungen, wöchentlich, vierteljährlich, jährlich, Zufallsgruppen gegen die Referenz (Hypothesis) |
| `tests/app/m16/test_m16_begruendung.py` | M16: `GET /api/buchungen/{id}/wiederkehrend` – 404/422, Vorgabe-Stichtag, kein Protokoll, Stichtag, Urteile und Rollen, Umbuchung, ausgeschlossen (ohne Empfänger, Summe null, Darlehenskonto), Übereinstimmung mit der Übersicht im M5-Datensatz |
| `tests/app/m16/test_m16_oberflaeche.py` | M16: Browsertests – Alt-Kontextmenü (Rechtsklick, Alt+Umschalt+F10, Alt+Menütaste), Begründungsdialog, Befehlspalette, Menü je Serie auf `/wiederkehrend`, Springen, Sprungziel mit Nachladen, ausgefiltert, ungültig, leere Liste, mobil (`oberflaeche.md` 26) |
| `tests/app/m29/test_m29_config.py` | M29: Konfiguration ohne AqBanking (`bank_plugin`, `from_env`, entfallene Felder, Fehlerklasse, Modul) |
| `tests/app/m29/test_m29_fints_plugin.py` | M29: FinTS-Plugin gegen die Attrappe – `tan_verfahren`, Kontenliste aus den SEPA-Kontoverbindungen, camt-Version, Datumsformen, unlesbare Werte, TAN bei der Anmeldung |
| `tests/app/m29/test_m29_bankzugang_rest.py` | M29: `/api/bank/zugang…` (Lesen, Speichern, Validierung, TAN-Verfahren, Konten abrufen mit TAN, Auswahl, `tan_offen`, Mock-Modus, Betriebszustand, Schutz, Geheimnisse) |
| `tests/app/m29/test_m29_sync.py` | M29: Lauf mit ausgewählten Konten, TAN bei der Anmeldung im Lauf, Bankzugang ohne Neustart wirksam |
| `tests/app/m29/test_m29_uebergang.py` | M29: Übergang alter Bank-Kennungen über `kontor.sync.kennungen_als_alt_markieren` (Mock und FinTS MT940 → camt), Protokoll, Rückgängig, Sicherung |
| `tests/app/m29/test_m29_diagnose.py` | M29: Diagnoseprotokoll (Schalter, Inhalt, keine persönlichen Daten, Bereinigung, Form unlesbarer Werte, 600 Zeilen) |
| `tests/app/m29/test_m29_oberflaeche.py` | M29: Browsertests – Abschnitt `bankzugang` der Einstellungen (Felder, PIN, TAN-Verfahren, Konten mit TAN, Diagnose) |
| `tests/app/m30/test_m30_ausdruck.py` | M30: `GET /api/ausdruck/sprache`, `POST /api/ausdruck/pruefen` (gültige Schreibweisen, kanonische Form, Fehlercodes mit Stelle, Längengrenzen, Datumsangaben zum Stichtag 2026-11-16, `festschreiben`), `POST /api/ausdruck/als-regel` |
| `tests/app/m30/test_m30_filter.py` | M30: Parameter `filter`/`stichtag` an `GET /api/buchungen` (Felder, Operatoren, Verknüpfungen, Datumsvergleiche, Freitext gegen eigene Rechnung; Kontoblatt; `markierungen`; 422 `ausdruck_ungueltig`) und am CSV-/PDF-Export |
| `tests/app/m30/test_m30_regeln.py` | M30: Regeln mit `ausdruck`, `tag_ids`, `kategorie_id` null (Anlegen, Ändern, Fehler), Übersetzung und Gleichwertigkeit der bisherigen Form, Auswertung und `tags` bei `POST /api/regeln/anwenden`, Tags bei der Synchronisation, `reihenfolge`, `test`, `erklaeren`, `POST /api/regeln/{id}/anwenden` |
| `tests/app/m30/test_m30_protokoll.py` | M30: Protokollform der Regel, Operationen mit Rückgängig-Rundreise, Tag löschen (vergeben bzw. in der Bedingung), Verweise beim Löschen und Zusammenführen von Konten, Sicherung (Rundreise, Rückgängig, Prüfsumme) |
| `tests/app/m30/test_m30_oberflaeche.py` | M30: Browsertests – Filterfeld im Kontoblatt, Zeitraum-Knöpfe, Baukasten, alte Adressen, „Als Regel speichern“, Regelliste, Regeleditor (Tags, Namensvorschlag, Abbrechen), Testbereich, Fenster „Regel anwenden“, Tag-Dialog (`oberflaeche.md` 39) |
| `tests/app/m31/test_m31_konfiguration.py` | M31: `regeln_automatisch`, `mail_bestellnummer`, ausgelieferte `kontor.env`, Testinstanz (`kontor-test.service`, `kontor-test.env`, Skript, Modul), Branch in der Hülle, Route `/lernmodell` |
| `tests/app/m31/test_m31_lernmodell.py` | M31: Einstellungen des Lernmodells (Schwelle, `regeln_automatisch`), Erklärung je Buchung gegen das Orakel, Übersicht, Mock-Lerndaten |
| `tests/app/m31/test_m31_regeln_automatisch.py` | M31: automatisch angelegte Regeln (Auslöser, Quote, Fenster, was nichts auslöst, Sperre beim Löschen, Rückgängig, Umbenennen, Sicherung) |
| `tests/app/m31/test_m31_berichte.py` | M31: Monatsbericht gegen eigene Rechnung, Fehler, neun weitere Berichte nur lesend |
| `tests/app/m31/test_m31_bestellnummer.py` | M31: Mails über die Bestellnummer an der Buchung (Mock und IMAP-Attrappe), Protokoll, Gemerktes, Sicherung, Mail-Liste |
| `tests/app/m31/test_m31_oberflaeche.py` | M31: Browsertests – Namen, Einschätzung, `/lernmodell`, Einstellungen in Bereichen, Datum der Mail, Gruppierung mit Abschnitt und Tiefe, Berichtswahl (`oberflaeche.md` 40) |
| `tests/app/m32/test_m32_kontonamen.py` | M32: Kontonamen je Ebene (Anlegen, Umbenennen, Verschieben, Löschen mit Unterkonten, Zusammenführen, Rückgängig mit 409 `konto_existiert`), Bereinigen beim Import, technische Konten, Synchronisation mit „ (2)“ |
| `tests/app/m32/test_m32_empfaenger.py` | M32: Standardkategorie abgelehnt, Erfassen ohne Kategorie, `GET /api/empfaenger/{id}/konten`, `/anzahlen`, Statistik entfällt |
| `tests/app/m32/test_m32_mail.py` | M32: Mail-Liste mit `suche`, Zuordnen von Hand, `betrag`, `gruppieren`; Bilder fremder Server (`bilder=ja`, `…/mail/bilder`) |
| `tests/app/m32/test_m32_anbieter.py` | M32: `anbieter_verzeichnis`, eigene und fehlerhafte Beschreibungen, PayPal nach Betrag, ± 5 Tagen und Händlername |
| `tests/app/m32/test_m32_geplant.py` | M32: geplante Zahlungen mit Wiederholung, Fortsetzung und Wegfall, Zuordnung nach Namen, Vorschau, Protokoll, Sicherung |
| `tests/app/m32/test_m32_betrieb.py` | M32: `GET /api/konfiguration` (verborgene Werte), HTTPS (`kontor-https.sh`, Warnung, Herkunft), Routen `/tags`, `/konfiguration` |
| `tests/app/m32/test_m32_oberflaeche.py` | M32: Browsertests (`oberflaeche.md` 41) |

Marker je Meilenstein (E-041, E-058): Tests direkt in `tests/app/` tragen
`m1`, Tests in `tests/app/m2/` tragen `m2`, Tests in `tests/app/m3/` tragen
`m3`, Tests in `tests/app/m4/` tragen `m4`, Tests in `tests/app/m5/` tragen
`m5` (E-097), Tests in `tests/app/m6/` und `tests/attrappen/` tragen `m6` (E-112), Tests in `tests/app/m7/` tragen
`m7` (E-125), Tests in `tests/app/m8/` tragen `m8` (E-139), Tests in `tests/app/m9/` tragen `m9`, Tests in `tests/app/m11/` tragen `m11` (E-158), Tests in `tests/app/m12/` tragen `m12` (E-167), Tests in `tests/app/m13/` tragen `m13` (E-176), Tests in `tests/app/m15/` tragen `m15` (E-181), Tests in `tests/app/m16/` tragen `m16` (E-192), Tests in `tests/app/m17/` tragen `m17` (E-199) (automatisch,
`tests/conftest.py`).
Die M1- bis M3-Tests sind seit ihrem Meilenstein unverändert (Ausnahme W-001,
siehe `ERGEBNIS.md`); eine Implementierung von M1 bis M3 bleibt gegen
`-m m1` bis `-m m3` grün (E-029). M4-Funktionen, die das Verhalten früherer
Meilensteine ändern würden, sind abschaltbar und standardmäßig aus
(`lernmodell_automatisch = False`, E-072) oder wirken nur mit M4-Objekten
(Vorlagen, `gnc:`-Konten).

Hinweise zu M2-Tests:

- Alle M2-Tests laufen im Mock-Modus mit simulierter Uhr
  (`mock_heute`, `PUT /api/mock/zeit`); es wird nie eine Bank angesprochen
  (Fixture `netz_gesperrt`). Nur `test_echtmodus` und
  `test_pin_im_echtmodus_annehmbar` nutzen den Echtmodus ohne Netz.
- Planer-Tests rufen `kontor.sync.planer_takt(app)` direkt auf; nur
  `test_hintergrund_thread` startet den Thread über den Lifespan
  (`with TestClient(app)`) und wartet bis zu 15 s.
- PIN- und TAN-Tests durchsuchen Datenbankdateien, Logausgaben (`caplog`,
  stdout/stderr) und alle Antworten nach den synthetischen Werten aus
  `fixtures/mock/sync_daten.erwartung.json`.

Hinweise zu M3-Tests:

- Protokolltests leiten die erwarteten Einträge selbst aus den
  Lese-Endpunkten ab (Protokollform, `protokoll.md` 2,
  `tests/hilfen/m3.py`). Jede M3-Antwort muss deshalb die M3-Felder tragen
  (`Buchung.gegen_iban`, `ist_umbuchung`, `abgestimmt`,
  `Split.abstimmung_id`, `Empfaenger.aliase`, `standardkategorie_id`).
- Synchronisationstests nutzen `fixtures/mock/m3_daten.json` im Mock-Modus
  mit simulierter Uhr; die automatische Umbuchungserkennung wird nur mit
  `umbuchung_automatisch=True` eingeschaltet (Vorgabe aus, E-054).
- Die eigenschaftsbasierten Rückgängig-Tests erzeugen je Beispiel eine
  frische App (`api_fabrik`); im Profil `gruendlich` dauern sie einige
  Minuten.

Hinweise zu M4-Tests:

- GnuCash-Fixtures liegen unter `fixtures/gnc/` (`*.gnucash`, Erwartung in
  `*.erwartung.json`); kleine Bücher bauen die Tests mit dem Modell des
  Generators (`generator/gnucash.py`) selbst. SQLite-Dateien werden nur über
  `POST /api/import/gnucash` bzw. `importiere_gnucash` gelesen.
- Lernmodell-Tests vergleichen jede Vorhersage exakt (Kategorie, Sicherheit
  in Promille, Kandidaten) mit `tests/hilfen/lern_orakel.py`. Abweichungen
  bei der Sicherheit deuten fast immer auf Gleitkomma statt exakter Brüche
  hin (`lernmodell.md` 4).
- Lernmodell in der Synchronisation nur mit `lernmodell_automatisch=True`
  (Vorgabe aus, E-072); Mindestgenauigkeit über
  `fixtures/kmy/m4_lernen_training.kmy` und `fixtures/m4/lernen.erwartung.json`.
- Vorlagen-Synchronisation: `fixtures/mock/m4_vorlagen.json` mit den
  Szenarien `normal` und `beitragsaenderung`, Stufen und Anpassung laut
  `fixtures/mock/m4_vorlagen.erwartung.json`.
- Die Überschneidungstests KMyMoney ↔ GnuCash importieren je etwa 1 000
  Buchungen und tragen den Marker `langsam`.

Hinweise zu M5-Tests:

- Tilgungspläne werden centgenau mit `fixtures/m5/kredite.json` (Decimal im
  Generator) und mit dem Bruch-Orakel `tests/hilfen/kredit_orakel.py`
  verglichen. Abweichungen um einzelne Cent deuten fast immer auf
  Gleitkomma, Rundung an der falschen Stelle oder eine andere Tageszählung
  hin (`kredite.md` 3.2–3.4).
- Kredit-Synchronisation: `fixtures/mock/m5_kredit.json` (Giro mit IBAN, vor
  dem Abruf angelegt, damit der Kredit sein Zahlungskonto kennt).
- Wiederkehrende Buchungen: `fixtures/mock/m5_wiederkehrend.json`; der
  Benachrichtigungstest ruft wöchentlich ab (gut 30 Abrufe) mit
  `wiederkehrend_automatisch=True` (Vorgabe aus, E-100).
- Berichte und CSV-Export nutzen `fixtures/kmy/standard.kmy` und
  `sonderfaelle.kmy`; der PDF-Export wird mit `pypdf` gelesen und läuft mit
  gesperrtem Netz (`netz_gesperrt`).
- Ohne Kredite und mit `wiederkehrend_automatisch=False` verhält sich eine
  M5-Implementierung wie M4/M9; die Sicherung enthält die Objektart
  `kredit` nur, wenn es Kredite gibt (E-109).

Hinweise zu M6-Tests:

- Echte Plugins laufen nur gegen lokale Attrappen auf `127.0.0.1`
  (`tests/hilfen/fints_attrappe.py`, `imap_attrappe.py`, `oauth_attrappe.py`,
  `ntfy_attrappe.py`, Zertifikate aus `tls.py`). Die Fixture
  `netz_nur_loopback` lässt nur Loopback zu, entfernt Proxy-Variablen und
  meldet jeden anderen Verbindungsversuch als Fehler; `netz_gesperrt` bleibt
  unverändert streng (E-122).
- Die Naht ist jeweils die Konfiguration (`fints_url`, `imap_host`/`imap_port`/
  `imap_tls`, `oauth_*_url`, `ntfy_url`, `tls_ca_datei`,
  `credentials_verzeichnis`); die Tests rufen nie echte Dienste.
- Die FinTS-Attrappe verwendet die Segmentklassen von python-fints und ist
  mit `FinTS3PinTanClient` geprüft (`tests/attrappen`). Rückmeldecodes:
  `fints.md` 6. python-fints protokolliert auf DEBUG ganze Nachrichten mit
  TAN; die Tests prüfen, dass die App das unterdrückt.
- Einige Tests warten wenige Sekunden (Zeitüberschreitung, kurze
  Token-Lebensdauer der OAuth-Attrappe); es gibt keine Uhrmanipulation im
  Echtmodus.

Hinweise zu M7-Tests:

- Frühere Tests laufen ohne Anmeldung (Vorgabe `anmeldung = False`, E-125).
  **Anmeldelauf:** `KONTOR_TESTS_ANMELDUNG=1 python -m pytest tests/app -m "not m7"`
  schaltet in jeder über `neue_config` erzeugten Konfiguration die Anmeldung
  ein; `Api` richtet das Passwort ein, meldet sich an und sendet den
  CSRF-Kopf. Ausgenommen (sie verwenden rohe `TestClient` ohne die
  Testhilfe): `test_mock_modus.py::test_create_app_aus_umgebung`,
  `m2/test_m2_planer.py::test_planer_starten_falsch` und
  `::test_hintergrund_thread`.
- M7-Tests verwenden `tests/hilfen/m7.py` (Anmelden, zweiter Client auf
  derselben App, Cookie-Auswertung, unabhängige scrypt-Prüfung) und
  `tests/hilfen/systemd.py` (statischer Unit-Leser).
- Ablauf- und Sperrtests warten einige Sekunden (Systemuhr, keine
  Uhrmanipulation; die Mock-Uhr wirkt absichtlich nicht auf Sitzungen).
- Betriebstests starten Unterprozesse (`python -m kontor`,
  `python -m kontor.sicherung`, `python -m kontor.anmeldung`) mit der
  Umgebung des Testprozesses (`PYTHONPATH` wird weitergegeben); das
  Startmodul lauscht nur auf `127.0.0.1` (`netz_nur_loopback`).
- Leistungstests erzeugen `fixtures/gross/` beim ersten Lauf (etwa 3 s,
  nicht eingecheckt) und importieren 50 000 Buchungen einmal je Lauf; auf
  langsameren Rechnern skaliert `KONTOR_LEISTUNG_FAKTOR` die Grenzwerte
  (Abnahme mit 1).

Hinweise zu M8-Tests:

- Server: `tests/hilfen/m8.py` startet `create_app(config)` unter uvicorn in
  einem Thread (eigene temporäre Datenbank, Mock-Modus mit `mock_heute =
  2024-12-31`); `server.api` prüft Wirkungen über HTTP mit derselben
  Vertragsprüfung wie `Api`. Daten: `fixtures/m8/oberflaeche.kmy` und
  `viele.kmy` (bekannte Wahrheit in `*.erwartung.json`).
- Browser: Chromium headless ohne Proxy, Namensauflösung nur für
  `127.0.0.1`; Desktop 1280 × 800, Handy 390 × 844 mit Touch. Jede Seite wird
  auf unbehandelte Skriptfehler, CSP-Verletzungen und Anfragen an fremde
  Herkünfte überwacht. Gesten (lange Berührung, Wischen) sind echte
  Touch-Ereignisse über CDP.
- Die Tests warten auf Zustände (`data-geladen`, `data-bereit`, Attribute,
  REST-Stand), höchstens 10 s je Erwartung. Fehlende Elemente zeigen sich
  daher als Zeitüberschreitung mit dem gesuchten `data-testid`
  (`get_by_test_id("…")`) und einem Ausschnitt des Barrierefreiheitsbaums.
- Anmeldelauf (`KONTOR_TESTS_ANMELDUNG=1`): Die Browsertests laufen dann mit
  eingeschalteter Anmeldung; jeder Browserkontext meldet sich vorher über
  `POST /api/anmeldung` an (gemeinsame Cookies), die Oberfläche muss den
  CSRF-Kopf selbst senden.
- Laufzeit: etwa 250 Tests, je nach Rechner 5–15 Minuten; mit `-n 2`
  (pytest-xdist) entsprechend kürzer.

## 4. Umgebungsvariablen

Die Tests setzen keine `KONTOR_*`-Variablen voraus; sie erzeugen ihre
`KontorConfig` selbst (Ausnahme: zwei Tests prüfen `from_env`/`create_app(None)`
und setzen die Variablen dafür vorübergehend selbst). Steuern lassen sich:

| Variable | Wirkung |
| --- | --- |
| `HYPOTHESIS_PROFILE` | `standard` (Vorgabe: 40 Beispiele, deterministisch; im Schnelllauf `schnell`), `schnell` (10 Beispiele), `gruendlich` (400 Beispiele, zufällig); gesetzt gilt es in jeder Laufart |
| `KONTOR_TESTS_VOLL=1` | wie `--voll`: Volllauf statt Schnelllauf (E-175) |
| `KONTOR_TESTS_OHNE_APP=1` | wie `--ohne-app`: App-Tests überspringen statt fehlschlagen, wenn `kontor` fehlt |
| `KONTOR_TESTS_ANMELDUNG=1` | Anmeldelauf (E-125): frühere Tests mit eingeschalteter Anmeldung und angemeldeter Sitzung |
| `KONTOR_TESTS_CHROMIUM=/pfad` | M8: ausführbare Datei des Browsers für die Oberflächentests (sonst gebündeltes Chromium bzw. Chrome) |
| `KONTOR_LEISTUNG_FAKTOR` | Faktor für die Grenzwerte der Leistungstests (Vorgabe 1) |
| `KONTOR_TESTS_ZUSATZFELDER=1` | Erweiterungslauf (E-124): jedes Antwortobjekt bekommt nach der Schemaprüfung ein zusätzliches optionales Feld; zeigt Tests, die spätere optionale Felder (E-029) verbieten würden. Muss grün bleiben wie der normale Lauf. |

Beispiel für einen gründlichen Lauf: `HYPOTHESIS_PROFILE=gruendlich python -m pytest --voll tests/app`.

## 5. Verhalten ohne installierte Anwendung (E-024)

- Ist `kontor` nicht importierbar, **schlägt jeder App-Test fehl** mit der
  Meldung „Die Anwendung (Python-Paket 'kontor') ist nicht installiert oder
  nicht importierbar“ samt Ursache und Installationshinweis.
- Generator- und Spezifikationstests laufen immer:
  `python -m pytest tests/generator tests/spec`.
- Bewusstes Überspringen der App-Tests: `python -m pytest --ohne-app` oder
  `KONTOR_TESTS_OHNE_APP=1 python -m pytest`.

## 6. Selbstprüfung (separat)

Prüft, dass die Kern-Tests bei richtiger Logik grün und bei eingebauten
Fehlern rot werden. Sie läuft gegen eine kleine Wegwerf-Referenz in
`tests/_selbstpruefung/referenz` (kein Anwendungscode), **nicht** gegen
kontor-app, und wird von normalen Testläufen nie eingesammelt.

```bash
pip install -r tests/_selbstpruefung/requirements.txt   # falls FastAPI nicht ohnehin installiert ist
python -m tests._selbstpruefung                          # Referenz + alle Mutanten (gut eine Stunde)
python -m tests._selbstpruefung --nur-referenz           # nur die grünen Läufe (normal und mit Zusatzfeldern, E-124)
python -m tests._selbstpruefung --mutant filter_ohne_umlaute
python -m tests._selbstpruefung --protokoll tests/_selbstpruefung/LETZTER_LAUF.md
```

Jeder Mutant läuft zuerst gegen die Kern-Tests seines Meilensteins
(`tests/app/m<N>` bzw. `tests/app/test_*.py` für M1) und nur, wenn diese grün
bleiben, gegen alle Kern-Tests; ein Mutant gilt als erkannt, sobald ein
Kern-Test rot wird.

Die Referenz wird nur im Unterprozess über `PYTHONPATH` eingebunden; sie
überdeckt dort eine eventuell installierte kontor-app, außerhalb nie.
Rückgabecode 0 = bestanden.

Ab M8 enthält die Referenz eine kleine Wegwerf-Oberfläche
(`referenz/kontor/oberflaeche/`, E-149) für die Kern-Tests der Oberfläche
(Auslieferung, Grundgerüst, Mehrfachauswahl, Kontextmenü, Befehlspalette,
mobiles Menü); die Kern-Tests brauchen dann einen startbaren Chromium. Ohne
Browser werden diese Tests übersprungen und die M8-Mutanten der Oberfläche
gelten als nicht erkannt.

## 7. Fixtures neu erzeugen (nur Test-Threads)

```bash
python -m generator            # schreibt fixtures/ und fixtures/MANIFEST.json
python -m pytest tests/generator
```

Der Generator ist deterministisch (Startwert 4711); `tests/generator` prüft,
dass die eingecheckten Dateien den erzeugten entsprechen.
