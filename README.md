# kontor-app

Implementierung von **Kontor**, einer selbst gehosteten Finanz-Web-App
(Python, FastAPI, SQLite, Single-Page-Weboberfläche). Stand: **Meilenstein 8** (M1–M9, Plan abgeschlossen)

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
- M6: Echte Anbindungen: FinTS-Bank über python-fints (nur lesend, camt.052
  bevorzugt, MT940 als Rückfall, QR-TAN mit Bild, PIN aus der Eingabe oder
  über systemd-creds), zwei Gmail-Postfächer über IMAP mit OAuth2/XOAUTH2
  (nur lesend, ohne Passwörter, parallel abgerufen, Token-Erneuerung,
  Vorwarnung, Ablauf im Testmodus nach sieben Tagen und Widerruf mit
  Benachrichtigung), Zustellung jeder Benachrichtigung per ntfy (genau eine
  Push-Nachricht, Wiederholung nur nach Fehlschlag, TAN-Push mit Link und
  Erinnerungen), verschlüsselter Geheimnisspeicher (AES-256-GCM) für Tokens
  und Client-Secret. Postfächer sind protokolliert und Teil der Sicherung;
  Geheimnisse nie.
- M7: Sicherheit und Betrieb: gemeinsamer Haushalts-Login (scrypt, Sitzungen
  mit Leerlauf- und Höchstdauer, Bremse mit Verdopplung nach falschen
  Passwörtern, CSRF-Token und Herkunftsprüfung, Ersteinrichtung mit
  Einrichtungscode), Beschränkung auf das Heimnetz, Sicherheitsköpfe (CSP ohne
  Inline-Skripte), Eingabehärtung und Größengrenzen, ausgelieferte
  systemd-Units mit Härtung und `LoadCredentialEncrypted`, tägliche Sicherung
  per Timer, sauberes Beenden mit WAL-Checkpoint, Gesundheitsprüfung und
  Leistung mit 50 000 Buchungen (Liste, Filter und Suche deutlich unter 1 s).
- M8: Vollständige Oberfläche als Single-Page-App mit Pfad-Routen: linke
  Navigation, Panels (verschiebbar, größenveränderbar, einklappbar, Layout im
  Browser gespeichert), Kontextmenüs, Drag and Drop, Mehrfachauswahl wie im
  Dateimanager, Tastaturkürzel und Befehlspalette, Inline-Bearbeitung mit
  Rückgängig per Strg+Z über das Änderungsprotokoll, helles/dunkles Design,
  installierbare PWA mit Offline-Hinweis, mobile Bedienung mit Gesten,
  TAN-Seite mit „QR-Code speichern“/„Teilen“, Barrierefreiheit.

**Alles lässt sich im Mock-Modus ohne echte Daten ausprobieren:** Mock-Bank,
Mock-Postfächer und Mock-Benachrichtigungen (Liste unter
`GET /api/mock/zustellungen`) arbeiten mit synthetischen Daten und bauen nie
eine Verbindung auf; auf Wunsch stellt der Mock-Modus auch per ntfy zu (Titel
beginnt mit `[Mock]`).

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

# 2. Konfiguration über Umgebungsvariablen (Kommandozeilenargumente gibt es nicht)
export KONTOR_DATENBANK="$PWD/daten/kontor.sqlite3"   # Echt-Datenbank (wird im Mock-Modus NICHT angelegt)
export KONTOR_MOCK_MODUS=ja                           # Mock-Modus: eigene Datenbank daten/kontor-mock.sqlite3
# Anmeldung bleibt hier aus (Vorgabe); zum Ausprobieren des Logins siehe „Anmeldung“ unten.

# 3. Server starten (127.0.0.1:8000; ändern über KONTOR_HOST/KONTOR_PORT)
python -m kontor

# 4. In einer zweiten Shell synthetische Testdaten importieren (Fixture aus kontor-tests)
curl -F datei=@../kontor-tests/fixtures/kmy/standard.kmy http://127.0.0.1:8000/api/import/kmymoney
```

Beenden mit Strg+C (bzw. `SIGTERM`): Kontor beendet einen laufenden Abruf
geordnet und schreibt das WAL in die Datenbankdatei zurück.

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
der Oberfläche unter **Import** hochladen (bei eingeschalteter Anmeldung nur
so oder mit Sitzungscookie und CSRF-Kopf). Ein zweiter Import derselben Datei
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
python -m kontor
```

1. **Regeln** → „Regel anlegen“, z. B. *empfaenger enthaelt Frischekorb →
   Lebensmittel* (vorher unter **Kategorien** eine Aufwandskategorie anlegen).
   Sie greift im eingebauten Datensatz wie in `sync_daten.json`.
2. **Synchronisation** → „Jetzt synchronisieren“ (oder ↻ im Kopf). Fehlende Konten werden über
   die IBAN angelegt, neue Umsätze gebucht, Gegenkonto ist die Kategorie der
   ersten passenden Regel oder das technische Konto „Unkategorisiert“. Die
   Liste der Läufe zeigt je Konto, was neu, vorhanden, zusammengeführt oder zur
   Prüfung vorgelegt wurde. Ein zweiter Lauf erzeugt keine Dubletten.
3. **Kontoansicht** des Girokontos: Regel-Kategorien tragen die Marke
   „Vorschlag“ und lassen sich per ✓/✗ in der Zeile, über die Mehrfachauswahl
   („Vorschläge annehmen“/„ablehnen“) oder das Kontextmenü bestätigen bzw.
   ablehnen.
4. **Mock-Uhr** (auf der Seite Synchronisation): Zeit vorstellen und erneut
   synchronisieren – neue Umsätze erscheinen, der
   Zeitraum überlappt den letzten Abruf um 14 Tage.
5. **TAN-Ablauf**: mit `KONTOR_MOCK_SZENARIO=tan_erforderlich` starten. Der
   Lauf pausiert, die Glocke oben zeigt eine Benachrichtigung, die TAN-Seite
   (`/tan/<id>`) zeigt Anweisung und QR-Bild mit „QR-Code speichern“ und
   „Teilen“. Richtige TAN: `123456` (bzw. `bank.tan` der Datendatei); nach
   23:59:59 UTC des simulierten Tages läuft die Anforderung ab.
6. **PIN**: mit `KONTOR_MOCK_DATEN=../kontor-tests/fixtures/mock/sync_daten_pin.json`
   verlangt die Mock-Bank eine PIN (steht synthetisch in der Datei unter
   `bank.pin`). Ohne PIN scheitert der Lauf mit `bank_pin_fehlt`; die Oberfläche
   fragt dann im PIN-Dialog danach (↻ im Kopf), die PIN liegt nur im Arbeitsspeicher und
   ist nach einem Neustart oder einer Ablehnung durch die Bank weg.
7. Fehlerfälle: `KONTOR_MOCK_SZENARIO=bankfehler` bzw. `zeitueberschreitung` –
   der Lauf scheitert ohne Datenverlust, es entsteht genau eine
   Benachrichtigung je Fehlercode, solange sie ungelesen ist.

## Anmeldung (Login) ausprobieren – Mock-Modus

```bash
export KONTOR_DATENBANK="$PWD/daten/kontor.sqlite3"
export KONTOR_MOCK_MODUS=ja
export KONTOR_ANMELDUNG=1
# Variante A: Passwort direkt setzen (liest eine Zeile von stdin; synthetisches Beispielpasswort)
echo 'Mein-Testhaushalt-2026' | python -m kontor.anmeldung passwort-setzen
python -m kontor
```

Variante B (wie im Betrieb): ohne Passwort starten; Kontor legt neben der
aktiven Datenbank die Datei `daten/kontor-mock.sqlite3.einrichtung` mit einem
Einrichtungscode an (Rechte 0600, im Log steht nur der Pfad). Auf
**http://127.0.0.1:8000/anmelden** den Code (`cat daten/kontor-mock.sqlite3.einrichtung`)
und das neue Passwort (12–1024 Zeichen) eingeben. Danach: **Einstellungen →
Anmeldung** zum Ändern des Passworts (beendet alle anderen Sitzungen) und zum
Abmelden (auch über die Befehlspalette). Nach fünf falschen Passwörtern ist die Anmeldung
60 s gesperrt, jede weitere Fehleingabe verdoppelt die Sperre (höchstens ein
Tag); die Anmeldeseite zeigt die Restzeit. Passwort vergessen: auf dem Server
`python -m kontor.anmeldung passwort-setzen` (mit denselben `KONTOR_*`-Variablen
bzw. `EnvironmentFile`) ausführen.

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

### Sicherheit und Betrieb (M7)

| Variable | Bedeutung |
| --- | --- |
| `KONTOR_ANMELDUNG` | Haushalts-Login einschalten (Vorgabe aus; **im Betrieb `1`**, ausgelieferte `kontor.env`) |
| `KONTOR_SITZUNG_LEERLAUF_SEKUNDEN`, `KONTOR_SITZUNG_HOECHSTDAUER_SEKUNDEN` | Ablauf der Sitzung (1 Tag ohne Aktivität, höchstens 30 Tage) |
| `KONTOR_SITZUNG_COOKIE_SECURE` | `Secure`-Cookie erzwingen (`1`, hinter HTTPS-Proxy) oder verbieten; leer = nur bei HTTPS-Anfragen |
| `KONTOR_ANMELDUNG_FEHLVERSUCHE`, `KONTOR_ANMELDUNG_SPERRE_SEKUNDEN` | Bremse: nach 5 Fehlversuchen 60 s Sperre, danach verdoppelt |
| `KONTOR_ERLAUBTE_NETZE` | CIDR-Liste, z. B. `127.0.0.0/8,192.168.0.0/16`; andere Adressen → 403 (leer = alle) |
| `KONTOR_UPLOAD_MAX_MIB`, `KONTOR_ANFRAGE_MAX_KIB` | Größengrenzen für Importe/Sicherungen (200 MiB) und andere Körper (4 096 KiB) |
| `KONTOR_HOST`, `KONTOR_PORT` | Adresse und Port von `python -m kontor` (Vorgabe `127.0.0.1`, `8000`) |
| `KONTOR_LOG_STUFE` | `DEBUG`, `INFO` (Vorgabe), `WARNING`, `ERROR`; Ausgabe nach stderr `<STUFE> <logger>: <Meldung>` |
| `KONTOR_BEENDEN_FRIST_SEKUNDEN` | Frist für einen laufenden Abruf beim Beenden (Vorgabe 20) |
| `KONTOR_MOCK_VERZOEGERUNG_MS` | nur Mock-Modus: jeder Umsatzabruf der Mock-Bank wartet so lange (Testhilfe) |

`GET /api/gesundheit` antwortet ohne Anmeldung mit `{"status": "ok", "version": …}`
(für Überwachung), `GET /api/anmeldung` mit dem Anmeldestatus.

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
Mock-Datenbank darf nicht die Echt-Datenbank sein. Unkonfigurierte echte
Plugins (FinTS, IMAP) bauen keine Verbindung auf und melden bei Abrufen
`PluginNichtVerfuegbar`; eine Synchronisation endet dann sauber als
fehlgeschlagener Lauf. Die PIN steht nie in einer Umgebungsvariable oder der
Datenbank: Sie wird in der Weboberfläche eingegeben (nur Arbeitsspeicher) oder
von systemd verschlüsselt bereitgestellt (siehe unten).

### Konfiguration der echten Anbindungen (M6)

| Variable | Bedeutung |
| --- | --- |
| `KONTOR_FINTS_URL`, `KONTOR_FINTS_BLZ`, `KONTOR_FINTS_BENUTZER` | FinTS-Endpunkt (https), Bankleitzahl (8 Ziffern), Anmeldename |
| `KONTOR_FINTS_KUNDEN_ID` | Kunden-ID, falls abweichend vom Anmeldenamen |
| `KONTOR_FINTS_PRODUKT_ID` | eigene Produktregistrierung bei der Deutschen Kreditwirtschaft (Pflicht für echte Banken) |
| `KONTOR_FINTS_TAN_VERFAHREN` | Sicherheitsfunktion (3 Ziffern); leer = erstes angebotenes Zwei-Schritt-Verfahren |
| `KONTOR_FINTS_TIMEOUT_SEKUNDEN` | Zeitgrenze je Anfrage (Vorgabe 30) |
| `KONTOR_BANK_PIN_QUELLE` | `eingabe` (Vorgabe, Oberfläche) oder `systemd-creds` |
| `CREDENTIALS_DIRECTORY` | setzt systemd; Datei `kontor-bank-pin` (PIN) und optional `kontor-geheimnisschluessel` |
| `KONTOR_IMAP_HOST`, `KONTOR_IMAP_PORT`, `KONTOR_IMAP_TLS` | Vorgabe `imap.gmail.com`, 993, TLS |
| `KONTOR_OAUTH_CLIENT_ID` | Client-ID des eigenen Google-Cloud-Projekts (das Secret kommt in den Geheimnisspeicher) |
| `KONTOR_OAUTH_REDIRECT_URI` | Umleitungsadresse (Vorgabe `http://127.0.0.1/oauth2/rueckruf`) |
| `KONTOR_OAUTH_REFRESH_GUELTIG_STUNDEN` | Gültigkeit des Refresh-Tokens ohne Angabe des Anbieters (Vorgabe 168 = Testmodus; `0` nach Veröffentlichung des Projekts) |
| `KONTOR_OAUTH_VORWARNUNG_STUNDEN` | Vorwarnung vor dem Ablauf (Vorgabe 24) |
| `KONTOR_MAIL_INTERVALL_MINUTEN` | automatischer Mail-Abruf (Vorgabe 0 = aus) |
| `KONTOR_MAIL_ERSTABRUF_TAGE`, `KONTOR_MAIL_UEBERLAPPUNG_STUNDEN` | Zeitraum des ersten Abrufs (30 Tage) und Überlappung (24 h) |
| `KONTOR_BENACHRICHTIGUNG_PLUGIN` | `keins` (Vorgabe im Echtbetrieb), `mock` (Vorgabe im Mock-Modus), `ntfy` |
| `KONTOR_NTFY_URL`, `KONTOR_NTFY_TOPIC` | ntfy-Server (Vorgabe `https://ntfy.sh`) und Thema (Pflicht bei `ntfy`) |
| `KONTOR_ZUSTELLUNG_MAX_VERSUCHE`, `KONTOR_ZUSTELLUNG_WIEDERHOLUNG_MINUTEN` | Wiederholung nach Fehlschlag (10 Versuche, alle 5 Minuten) |
| `KONTOR_TAN_ERINNERUNG_MINUTEN`, `KONTOR_TAN_ERINNERUNG_ANZAHL` | Erinnerungen an offene TANs (alle 5 Minuten, höchstens 3; `0` = keine) |
| `KONTOR_OEFFENTLICHE_URL` | Adresse von Kontor im Heimnetz für Links in Push-Nachrichten (z. B. `http://kontor.lan:8000`) |
| `KONTOR_GEHEIMNIS_SCHLUESSEL_DATEI` | Schlüsseldatei des Geheimnisspeichers (Vorgabe neben der Datenbank, `*.schluessel`) |
| `KONTOR_TLS_CA_DATEI` | eigene Vertrauensanker (PEM) für alle ausgehenden TLS-Verbindungen |

Unverschlüsseltes `http://` (und `KONTOR_IMAP_TLS=nein`) ist nur für
`127.0.0.1`, `::1` und `localhost` erlaubt. Kontor folgt keinen Umleitungen
und verwendet keine Proxy-Variablen der Umgebung.

### Installation als systemd-Dienst im Proxmox-LXC-Container

Kontor liefert alle Betriebsdateien im Paket `kontor.betrieb` aus
(`kontor.service`, `kontor-sicherung.service`, `kontor-sicherung.timer`,
`kontor.sysusers`, `kontor.env`, `pin-eingabe.conf`). Schritt für Schritt
(als root im Container, z. B. Debian 13 mit systemd):

1. **Container:** unprivilegierter LXC mit `nesting=1` (Vorgabe neuer
   Container; nötig für die Härtungsoptionen der Unit). Feste IP im Heimnetz,
   keine Portweiterleitung am Router.
2. **Pakete und Programm:**
   ```bash
   apt install python3 python3-venv git
   git clone https://github.com/tedeler/kontor-app /opt/kontor/src
   python3 -m venv /opt/kontor/venv
   /opt/kontor/venv/bin/pip install /opt/kontor/src
   B=$(/opt/kontor/venv/bin/python -c 'import importlib.resources as r; print(r.files("kontor.betrieb"))')
   ```
3. **Benutzer und Dateien:**
   ```bash
   install -m 0644 "$B/kontor.sysusers" /etc/sysusers.d/kontor.conf && systemd-sysusers
   install -d -m 0750 -o root -g kontor /etc/kontor
   install -m 0640 -o root -g kontor "$B/kontor.env" /etc/kontor/kontor.env
   install -m 0644 "$B/kontor.service" "$B/kontor-sicherung.service" "$B/kontor-sicherung.timer" /etc/systemd/system/
   ```
   In `/etc/kontor/kontor.env` die FinTS-, ntfy- und Mail-Einstellungen
   eintragen (die Datei enthält **keine Geheimnisse**; Anmeldung, Heimnetz und
   `systemd-creds` sind voreingestellt).
4. **Geheimnisse verschlüsselt ablegen** (die PIN wird nie in eine Datei,
   Umgebungsvariable oder Kommandozeile geschrieben):
   ```bash
   systemd-ask-password -n "Banking-PIN:" | systemd-creds encrypt --with-key=host --name=kontor-bank-pin - /etc/kontor/kontor-bank-pin.cred
   openssl rand -base64 32 | systemd-creds encrypt --with-key=host --name=kontor-geheimnisschluessel - /etc/kontor/kontor-geheimnisschluessel.cred
   ```
   Mit TPM im Container `--with-key=tpm2` (oder ohne Angabe) statt `host`.
   Wer die PIN nur in der Oberfläche eingeben will:
   `install -D -m 0644 "$B/pin-eingabe.conf" /etc/systemd/system/kontor.service.d/pin-eingabe.conf`
   und nur den Geheimnisschlüssel anlegen.
5. **Starten:**
   ```bash
   systemctl daemon-reload
   systemctl enable --now kontor.service kontor-sicherung.timer
   journalctl -u kontor -f          # Start-, Anmelde- und Fehlermeldungen
   curl -s http://127.0.0.1:8000/api/gesundheit
   ```
6. **Login einrichten:** Beim ersten Start legt Kontor
   `/var/lib/kontor/kontor.sqlite3.einrichtung` an (das Journal nennt den Pfad).
   `cat` dieser Datei liefert den Einrichtungscode; im Browser
   `http://<container-ip>:8000/anmelden` öffnen, Code und Haushaltspasswort
   eingeben. Alternativ direkt auf dem Server:
   `set -a; . /etc/kontor/kontor.env; set +a; sudo -u kontor -E /opt/kontor/venv/bin/python -m kontor.anmeldung passwort-setzen`.
7. **Daten übernehmen:** in der Oberfläche unter **Import** die KMyMoney- oder
   GnuCash-Datei hochladen.

Die Unit läuft als Benutzer `kontor` mit `ProtectSystem=strict`, leeren
Capabilities, `SystemCallFilter=@system-service`, nur IPv4/IPv6/Unix-Sockets
und `UMask=0077`; Daten liegen in `/var/lib/kontor` (`StateDirectory`, 0700).
Ein Konfigurationsfehler beendet den Dienst mit Rückgabecode 2 ohne
Neustartschleife (`RestartPreventExitStatus=2`). Beim Stoppen hat ein laufender
Abruf bis zu 20 s, danach schreibt Kontor das WAL zurück – ein Snapshot oder
eine Kopie von `kontor.sqlite3` ist dann vollständig. Updates:
`/opt/kontor/venv/bin/pip install --upgrade /opt/kontor/src` (nach `git pull`),
dann `systemctl restart kontor`; die Datenbank wird beim Start ohne
Datenverlust migriert.

HTTPS: Kontor selbst spricht kein TLS. Wer es will, setzt einen Reverse-Proxy
auf demselben Host davor (Kontor dann auf `127.0.0.1` binden) und
`KONTOR_SITZUNG_COOKIE_SECURE=1`.

Lehnt die Bank die PIN ab (oder sperrt den Zugang), verwendet Kontor die PIN
bis zum nächsten Neustart des Dienstes nicht mehr (Schutz vor Kontosperre).
Ohne TPM: `--with-key=host` statt `tpm2`. Ohne systemd bleibt
`KONTOR_BANK_PIN_QUELLE=eingabe`; der Geheimnisschlüssel liegt dann als Datei
mit Rechten 0600 neben der Datenbank (wird beim ersten Speichern angelegt) –
er gehört nicht in dieselbe Datensicherung wie die Datenbank.

### Gmail über ein eigenes Google-Cloud-Projekt

1. In der Google Cloud Console ein eigenes Projekt anlegen, die **Gmail API**
   aktivieren und den OAuth-Zustimmungsbildschirm („Extern“, eigene Adressen
   als Testnutzer) einrichten. Scope: `https://mail.google.com/` (nur damit
   erlaubt Gmail IMAP; Kontor liest trotzdem nur – Ordner per `EXAMINE`,
   Inhalte per `BODY.PEEK[]`, nie `LOGIN`).
2. OAuth-Client vom Typ **Desktop-App** anlegen; Client-ID nach
   `KONTOR_OAUTH_CLIENT_ID`, das Client-Secret in der Oberfläche unter
   **Einstellungen → Geheimnisse** eintragen (wird verschlüsselt
   gespeichert, nie angezeigt).
3. Unter **Einstellungen → Mail-Postfächer** beide Postfächer anlegen (Ordner
   und Absenderfilter über `PATCH /api/mail/postfaecher/{id}`) und auf der Seite
   des Postfachs je „Anmeldung starten“:
   Link öffnen, zustimmen; lädt die Umleitungsseite nicht (Browser nicht auf
   dem Server), die Adresse aus der Adresszeile kopieren und einfügen.
4. **Testmodus:** Refresh-Tokens laufen nach sieben Tagen ab. Kontor zeigt den
   Ablauf, warnt 24 Stunden vorher per ntfy und meldet Ablauf oder Widerruf
   einmal; das andere Postfach läuft weiter. Dauerhaft: das Projekt
   veröffentlichen („In production“, für den Eigengebrauch ohne
   Verifizierung möglich) und `KONTOR_OAUTH_REFRESH_GUELTIG_STUNDEN=0` setzen.

### ntfy

Eigener oder öffentlicher ntfy-Server; das Thema wirkt wie ein Passwort
(schwer erratbar wählen) oder der Server verlangt ein Zugriffstoken, das unter
**Einstellungen → Geheimnisse** als „ntfy-Token“ eingetragen wird.
Jede Benachrichtigung erzeugt genau eine Push-Nachricht (TAN-Anforderungen und
abgelaufene Mail-Anmeldungen mit hoher Priorität, Links über
`KONTOR_OEFFENTLICHE_URL`). „Test-Benachrichtigung senden“ prüft die
Verbindung. Im Mock-Modus kann ebenfalls per ntfy zugestellt werden
(`KONTOR_BENACHRICHTIGUNG_PLUGIN=ntfy`), die Titel beginnen dann mit `[Mock]`.

### Datensicherung im Betrieb

Kontor sichert den **fachlichen Bestand** in der App (`GET /api/sicherung`,
Einstellungen → Datensicherung, Python `kontor.sicherung.erstelle_sicherung`):
Konten, Buchungen mit Splits, Empfänger, Tags, Regeln, Dublettenverdachte,
Abstimmungen, Split-Vorlagen, gemerkte Umsatzkennungen, Stand je Bankkonto
und ID-Zähler – als ZIP mit `kontor.sqlite` und `manifest.json`. Nicht
enthalten: Änderungsprotokoll, PIN/Geheimnisse, Importvorgänge, Läufe,
Benachrichtigungen und die Konfiguration (Umgebungsvariablen). Ab M6 sind die
Postfächer (Adresse, Bezeichnung, Ordner, Filter) enthalten, nie aber Tokens,
Client-Secret, ntfy-Token, Schlüssel oder abgerufene Mails.

Empfehlung: **zusätzlich** zu Proxmox-Snapshots bzw. -Backups des Containers.
Ein Snapshot sichert die ganze Instanz einschließlich Protokoll und
Konfiguration (schnelles Zurücksetzen nach einem missglückten Update); die
Kontor-Sicherung ist klein, geprüft (Prüfsummen), unabhängig vom Container und
lässt sich auf neuer Hardware oder in eine frische Instanz einspielen. Eine
Sicherung im laufenden Betrieb ist ein konsistenter Schnappschuss; der Server
muss dafür nicht angehalten werden. Die ausgelieferte Unit
`kontor-sicherung.timer` legt täglich eine Sicherung in
`/var/lib/kontor/sicherungen` ab (Rechte 0600, die 14 neuesten je Modus
bleiben):

```bash
systemctl list-timers kontor-sicherung.timer
systemctl start kontor-sicherung.service      # sofort eine Sicherung
# von Hand bzw. in ein anderes Verzeichnis (gleiche KONTOR_*-Variablen):
python -m kontor.sicherung --verzeichnis /mnt/nas/kontor --behalten 30
```

Dieses Verzeichnis zusätzlich außerhalb des Containers kopieren (z. B. NAS).

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

Single-Page-App ohne Build-Schritt, Framework und externe Ressourcen (ES-Module unter
`src/kontor/web/oeffentlich/app/`, Stile `app.css`, Service Worker `src/kontor/web/sw.js`). Verbindlich ist
`kontor-tests/spec/api/oberflaeche.md`; die Oberfläche nutzt ausschließlich die REST-Schnittstelle.

### Aufbau

- **Kopf:** ☰ (nur Handy), Suche (Enter → `/suche?q=…`), ↻ Synchronisieren (bei TAN mit Link zur TAN-Seite,
  bei fehlender/falscher PIN mit PIN-Dialog), ↶ Rückgängig, ↷ Wiederholen, ⌘ Befehlspalette, 🔔
  Benachrichtigungen mit Zahl der ungelesenen. Im Mock-Modus steht darüber immer der gelbe Mock-Hinweis.
- **Navigation links:** Finanzübersicht, Konten, Kategorien, Wiederkehrende Buchungen, Kredite, Berichte, Import,
  Einstellungen, Änderungsprotokoll, Empfänger, Regeln, Split-Vorlagen, Dubletten, Synchronisation. Jede Seite hat
  eine eigene Adresse (Lesezeichen, Zurück/Vor, Neuladen), z. B. `/konten/5?von=2024-03-01&status=bestaetigt`.
- **Kontoansicht** (`/konten/<id>`): Filterleiste (Zeitraum, Betrag, Empfänger, Verwendungszweck, Freitext,
  Kategorie mit Unterkategorien, Tag, Status; in der Adresse gespeichert), sortierbare Spalten, 200 Buchungen je
  Seite mit „Weitere laden“, Vorschläge mit ✓/✗, „Buchung erfassen“. Links das Panel **Kategorien** (Buchungen
  darauf ziehen), rechts **Einzelheiten** der fokussierten Buchung (alle Splits). Panels: Kopf ziehen bzw. ⇄
  verschiebt in den anderen Bereich, Rand ziehen oder Pfeiltasten ändert die Breite (160–600 px), ▾ klappt ein;
  das Layout liegt im `localStorage` (`kontor.layout`), „Layout zurücksetzen“ in den Einstellungen.
- **Mehrfachauswahl:** Klick, Strg/⌘+Klick (umschalten), Umschalt+Klick (Bereich), Strg+Umschalt+Klick
  (Bereich hinzu); die Leiste unten setzt Kategorie, Tags, Vorschläge oder löscht. Rechtsklick öffnet das
  Kontextmenü (Kategorie, Tags, Splitten, Als Dublette markieren, Vorschlag annehmen/ablehnen, Verwendungszweck
  bearbeiten, Löschen); auf Konten und Kategorien: Öffnen, Umbenennen, Unterkonto, Verschieben nach…, Löschen.
- **Inline-Bearbeitung:** Doppelklick auf Datum, Verwendungszweck oder Kategorie (F2 = Verwendungszweck); Enter,
  Tab oder Verlassen übernimmt, Esc bricht ab.
- **Rückgängig:** Jede eigene Änderung (auch Import, Löschen, Drag and Drop, Jahresabgleich) ist ein Schritt auf dem
  Rückgängig-Stapel des Tabs; Strg+Z nimmt ihn über das Änderungsprotokoll zurück, Strg+Umschalt+Z/Strg+Y stellt
  ihn wieder her. Die Seite Änderungsprotokoll bietet Rückgängig je Änderung.
- **Kategorien:** Baum mit Ausgaben/Einnahmen; Kategorie auf eine andere ziehen = Unterkategorie, auf die
  Gruppenüberschrift = oberste Ebene.
- **Weitere Seiten:** Kredite mit Tilgungsplan und Jahresabgleich (Prüfen, dann Buchen), Berichte
  (Kontostandsverlauf als SVG und Tabelle, Einnahmen/Ausgaben, Export CSV/PDF), Import (KMyMoney/GnuCash),
  Einstellungen (Design, Test-Benachrichtigung, PIN verwerfen, Geheimnisse, Datensicherung, Postfächer, Tags,
  Passwort, Abmelden), Empfänger, Regeln, Split-Vorlagen, Dubletten, Synchronisation (Läufe, Bankkonten, Mock-Uhr),
  Benachrichtigungen, Suche, TAN-Seite (`/tan/<id>`: QR-Code, „QR-Code speichern“, „Teilen“ wo der Browser Dateien
  teilen kann, TAN-Eingabe), Postfach (`/mail/postfaecher/<id>`: OAuth2-Anmeldung).

### Tastaturkürzel

| Kürzel | Wirkung |
| --- | --- |
| Strg+K, ⌘+K, Strg+Umschalt+P | Befehlspalette (Navigation, Rückgängig, Synchronisieren, Design, Konto öffnen …) |
| `/` | in die Suche springen |
| `?` | Übersicht der Kürzel |
| Strg+Z / Strg+Umschalt+Z, Strg+Y | Rückgängig / Wiederholen (in Textfeldern das Text-Rückgängig des Browsers) |
| Alt+1 … Alt+8 | Finanzübersicht, Konten, Kategorien, Wiederkehrend, Kredite, Berichte, Import, Einstellungen |
| Esc | Menü/Dialog/Palette schließen, sonst Auswahl leeren |
| Pfeil auf/ab, Pos1, Ende | Buchung wählen (mit Umschalt: Bereich, mit Strg: nur Fokus) |
| Leertaste, Strg+A | Buchung umschalten, alle wählen |
| F2, Entf, Enter | Verwendungszweck bearbeiten, Auswahl löschen (Rückfrage), Einzelheiten |
| Umschalt+F10, Kontextmenü-Taste | Kontextmenü |

### Handy

Unter 768 px Breite: Navigation über ☰, kompakte Buchungsliste (Tippen zeigt die Einzelheiten), **lange
Berührung** = Kontextmenü, **nach rechts wischen** = Buchung zur Auswahl hinzufügen/entfernen (danach schaltet
Tippen um), **nach links wischen** = Kategorie wählen; Kategorien verschieben über „Verschieben nach…“ im Menü der
langen Berührung. Rückgängig über ↶ im Kopf oder in der Erfolgsmeldung.

### Design und Installation als App (PWA)

Hell/dunkel folgt der Systemeinstellung; fest einstellbar unter Einstellungen → Design oder in der
Befehlspalette (`localStorage` `kontor.thema`). Kontor ist installierbar: in Chrome/Edge über „App installieren“
in der Adresszeile, auf Android über „Zum Startbildschirm hinzufügen“, auf iOS in Safari über „Teilen → Zum
Home-Bildschirm“. Voraussetzung ist ein sicherer Ursprung (HTTPS oder `http://127.0.0.1`/`localhost`; im Heimnetz
z. B. hinter einem Reverse-Proxy mit Zertifikat). Ohne Netz zeigt die installierte App die Hülle mit dem Hinweis
„offline“, aber keine Daten; Finanzdaten werden nie im Browser zwischengespeichert.

## Tests

```bash
pip install -e . pytest httpx
python -m pytest tests          # eigene Tests (Browser-Rauchtests nur mit Playwright + Chrome/Chromium)
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
