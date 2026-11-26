# Betrieb: Dienst, systemd, Sicherung, Neustart, Logging – Meilenstein 7

Verbindlich für Implementierung und Tests. Umsetzung von K 2 (Homeserver,
unprivilegierter LXC-Container, systemd-Dienst, Backups über
Proxmox-Snapshots und Datenbank-Export), K 3 (Geheimnisse), K 6 (PIN über
systemd-creds, nie in Kommandozeilen) und T 20 (Neustart während einer
Synchronisation ohne inkonsistenten Zustand). Anmeldung und Härtung der
Anwendung: `sicherheit.md`; Leistung: `leistung.md`. Abkürzungen wie dort.

## 1. Ausgelieferte Dateien

Die Anwendung liefert im Python-Paket das Unterpaket **`kontor.betrieb`**
(mit `__init__.py`) aus. Die folgenden Dateien liegen darin als Paketdaten
und sind über `importlib.resources.files("kontor.betrieb")` lesbar (UTF-8,
Zeilenende `\n`):

| Datei | Zweck | Ziel im System |
| --- | --- | --- |
| `kontor.service` | Hauptdienst | `/etc/systemd/system/kontor.service` |
| `kontor-sicherung.service` | zeitgesteuerte Sicherung (Einmallauf) | `/etc/systemd/system/` |
| `kontor-sicherung.timer` | Zeitplan der Sicherung | `/etc/systemd/system/` |
| `kontor.sysusers` | Systembenutzer `kontor` | `/etc/sysusers.d/kontor.conf` |
| `kontor.env` | Umgebungsdatei (Beispiel mit Betriebsvorgaben) | `/etc/kontor/kontor.env` (Rechte `0640`, `root:kontor`) |
| `pin-eingabe.conf` | Drop-in für die Variante „PIN nur in der Oberfläche“ | `/etc/systemd/system/kontor.service.d/pin-eingabe.conf` |

Feste Pfade im Betrieb: Programm in einer virtuellen Umgebung unter
`/opt/kontor/venv` (`/opt/kontor/venv/bin/python`), Daten in
`/var/lib/kontor` (über `StateDirectory=kontor`), Konfiguration und
verschlüsselte Credentials in `/etc/kontor`.

## 2. Startmodul `python -m kontor`

- `python -m kontor` (Modul `kontor.__main__`) liest
  `KontorConfig.from_env()`, richtet das Logging ein (7), erzeugt die App
  mit `create_app(config)` und startet uvicorn auf `config.host` und
  `config.port` mit `proxy_headers=False`, `lifespan="on"`,
  `server_header=False` und genau einem Arbeitsprozess.
- Kommandozeilenargumente werden nicht ausgewertet (keine Geheimnisse und
  keine Konfiguration in der Kommandozeile, K 6); unbekannte Argumente →
  Rückgabecode 2.
- `KonfigurationsFehler` (aus `from_env` oder `create_app`) → eine Zeile
  `Konfigurationsfehler: <Meldung>` auf stderr, ohne Stacktrace, Rückgabecode
  **2**. Die Meldung nennt Variablen, nie Werte geheimer Art.
- `SIGTERM` und `SIGINT` beenden den Dienst sauber (5.2); danach Rückgabecode 0
  oder Ende durch das empfangene Signal (wie uvicorn es tut; systemd wertet
  beides als Erfolg). Ein Stacktrace erscheint dabei nicht.
- Neue Konfigurationsfelder `host` (Vorgabe `127.0.0.1`) und `port`
  (Vorgabe 8000, `python-api.md` 14.1). Ports unter 1024 sind möglich,
  brauchen aber Rechte, die der Dienst nicht hat; der Betrieb nutzt 8000.
- Kein TLS im Anwendungsserver (`sicherheit.md` 12).

## 3. Umgebungsdatei `kontor.env`

- Format einer systemd-`EnvironmentFile`: Zeilen `NAME=WERT`, Leerzeilen und
  Kommentarzeilen (`#` am Zeilenanfang); Werte ohne Anführungszeichen und
  ohne Leerzeichen; jeder Name höchstens einmal.
- Pflichtinhalt (genau diese Werte):

  | Variable | Wert |
  | --- | --- |
  | `KONTOR_DATENBANK` | `/var/lib/kontor/kontor.sqlite3` |
  | `KONTOR_ANMELDUNG` | `1` |
  | `KONTOR_HOST` | `0.0.0.0` |
  | `KONTOR_PORT` | `8000` |
  | `KONTOR_ERLAUBTE_NETZE` | `127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7,fe80::/10` |
  | `KONTOR_BANK_PIN_QUELLE` | `systemd-creds` |
  | `KONTOR_UMBUCHUNG_AUTOMATISCH` | `1` |
  | `KONTOR_LERNMODELL_AUTOMATISCH` | `1` |
  | `KONTOR_WIEDERKEHREND_AUTOMATISCH` | `1` |
  | `KONTOR_SYNC_INTERVALL_MINUTEN` | eine Zahl ≥ 60 |
  | `KONTOR_SYNC_KONTEN_ANLEGEN` | `0` (ab M15, `synchronisation.md` 20, E-186) |
  | `KONTOR_MAIL_ABGLEICH` | `1` (ab M20, `erwartungen.md` 1, E-216); `KONTOR_MAIL_ABGLEICH_FRIST_TAGE` nur auskommentiert als `#KONTOR_MAIL_ABGLEICH_FRIST_TAGE=5` |
  | `KONTOR_MAIL_ABGLEICH` (ab M31) | **`0`** statt `1` (`erwartungen.md` 14.1, E-284); die Zeile davor gilt nur noch für die auskommentierte Frist |
  | `KONTOR_MAIL_BESTELLNUMMER` | `1` (ab M31, `erwartungen.md` 14.1) |
  | `KONTOR_REGELN_AUTOMATISCH` | `1` (ab M31, `lernmodell.md` 9) |

  Weitere `KONTOR_*`-Variablen (z. B. auskommentierte FinTS- oder
  ntfy-Einstellungen) sind erlaubt.
- **Keine Geheimnisse:** Kein Name enthält (ohne Beachtung der
  Groß-/Kleinschreibung) `PIN`, `PASSWORT`, `PASSWORD`, `TOKEN`, `SECRET`,
  `GEHEIM`, `KEY` oder `SCHLUESSEL`, außer er endet auf `_QUELLE` oder
  `_DATEI`. Auch auskommentierte Zeilen enthalten keine Werte solcher Namen.
  `CREDENTIALS_DIRECTORY` steht nicht in der Datei (setzt systemd).
- `KontorConfig.from_env(<Variablen der Datei> + {"CREDENTIALS_DIRECTORY":
  <Verzeichnis>})` gelingt und ergibt `anmeldung = True`,
  `bank_pin_quelle = "systemd-creds"` und (ab M15) `sync_konten_anlegen = False`.

## 4. systemd-Units

Die Tests lesen die Dateien statisch (ohne systemd): Abschnitte `[Name]`,
Zeilen `Schlüssel=Wert`, Kommentare mit `#` oder `;` am Zeilenanfang, keine
Fortsetzungszeilen. Mehrfach erlaubte Schlüssel dürfen mehrfach vorkommen;
sonst kommt jeder Schlüssel je Abschnitt höchstens einmal vor. Boolesche
Werte werden als `yes` geschrieben.

### 4.1 `kontor.service`

`[Unit]`:

- `Description=` nicht leer; `After=` und `Wants=` enthalten jeweils
  `network-online.target`.

`[Service]` (Pflichtwerte; „genau“ = dieser Wert, sonst „enthält“):

| Schlüssel | Wert |
| --- | --- |
| `Type` | genau `exec` |
| `User`, `Group` | genau `kontor` (kein `DynamicUser`, E-131) |
| `EnvironmentFile` | genau `/etc/kontor/kontor.env` |
| `ExecStart` | genau `/opt/kontor/venv/bin/python -m kontor` (einmal) |
| `LoadCredentialEncrypted` | genau zwei Zeilen: `kontor-bank-pin:/etc/kontor/kontor-bank-pin.cred` und `kontor-geheimnisschluessel:/etc/kontor/kontor-geheimnisschluessel.cred` |
| `StateDirectory` | genau `kontor` |
| `StateDirectoryMode` | genau `0700` |
| `UMask` | genau `0077` |
| `Restart` | genau `on-failure` |
| `RestartSec` | Ganzzahl ≥ 1 (Sekunden) |
| `RestartPreventExitStatus` | enthält `2` (Konfigurationsfehler nicht wiederholen) |
| `TimeoutStopSec` | Ganzzahl ≥ 30 (Sekunden; ≥ `beenden_frist_sekunden` + 10) |
| `LimitCORE` | genau `0` (ab M23, `geheimnisschutz.md` 7; nur `kontor.service`) |
| `NoNewPrivileges`, `PrivateTmp`, `PrivateDevices`, `ProtectHome`, `ProtectKernelTunables`, `ProtectKernelModules`, `ProtectKernelLogs`, `ProtectControlGroups`, `ProtectClock`, `ProtectHostname`, `RestrictSUIDSGID`, `RestrictRealtime`, `RestrictNamespaces`, `LockPersonality`, `RemoveIPC` | genau `yes` |
| `ProtectSystem` | genau `strict` |
| `ProtectProc` | genau `invisible` |
| `ProcSubset` | genau `pid` |
| `SystemCallArchitectures` | genau `native` |
| `SystemCallFilter` | genau `@system-service` |
| `CapabilityBoundingSet` | genau leer (`CapabilityBoundingSet=`) |
| `AmbientCapabilities` | genau leer |
| `RestrictAddressFamilies` | genau die Menge `AF_UNIX AF_INET AF_INET6` |

Verboten in `[Service]`: `LoadCredential=` und `SetCredential=` (die PIN
nie unverschlüsselt), `DynamicUser=`, `ExecStartPre=`/`ExecStartPost=` mit
`systemd-creds`, `PermissionsStartOnly=`, `User=root`, jede
`Environment=`-Zuweisung an einen Namen nach der Geheimnisregel aus 3, und
in `ExecStart` jeder Teil, der (ohne Groß-/Kleinschreibung) `pin`,
`passwort`, `password`, `token`, `secret`, `KONTOR_` oder `--` enthält.

`[Install]`: `WantedBy=multi-user.target`.

**Hinweise für den Betreiber** (nicht getestet): Im unprivilegierten
Proxmox-LXC braucht die Härtung die Container-Option `nesting=1`
(Vorgabe neuer Container). Credentials anlegen:
`systemd-creds encrypt --name=kontor-bank-pin - /etc/kontor/kontor-bank-pin.cred`
(PIN über stdin; `--with-key=host`, wenn im Container kein TPM verfügbar
ist) und ebenso `kontor-geheimnisschluessel` mit
`openssl rand -base64 32` als Eingabe. Wer die PIN nur in der Oberfläche
eingeben will, installiert `pin-eingabe.conf`.

### 4.2 `pin-eingabe.conf`

Drop-in mit genau: `[Service]`, `LoadCredentialEncrypted=` (leer, setzt
die Liste zurück), `LoadCredentialEncrypted=kontor-geheimnisschluessel:/etc/kontor/kontor-geheimnisschluessel.cred`
und `Environment=KONTOR_BANK_PIN_QUELLE=eingabe`.

### 4.3 `kontor-sicherung.service` und `kontor-sicherung.timer`

`kontor-sicherung.service`, `[Service]`: `Type=oneshot`, `User=kontor`,
`Group=kontor`, `EnvironmentFile=/etc/kontor/kontor.env`,
`ExecStart=/opt/kontor/venv/bin/python -m kontor.sicherung stunde --verzeichnis /var/lib/kontor/sicherungen`
(D-302, vorher `--verzeichnis /var/lib/kontor/sicherungen --behalten 14`),
`StateDirectory=kontor`, `UMask=0077` und dieselben Härtungswerte wie 4.1
(Tabellenzeilen ab `NoNewPrivileges`). Keine `LoadCredential*`-Zeile
(die Sicherung braucht keine Geheimnisse). Kein `[Install]`-Abschnitt.

`kontor-sicherung.timer`, `[Timer]`: `OnCalendar=hourly` (D-302, stündliche
Sicherungspunkte nach `sicherungspunkte.md`; vorher täglich), `Persistent=yes`;
`Unit=` fehlt oder ist `kontor-sicherung.service`. `[Install]`:
`WantedBy=timers.target`.

### 4.4 `kontor.sysusers`

Genau eine Zeile (außer Kommentaren): `u kontor - "Kontor" /var/lib/kontor`
(Feldtrenner: Leerzeichen; ein Systembenutzer ohne Anmeldeshell).

## 5. Neustart und Beenden

### 5.1 Datenbank

- Die aktive Datenbank läuft im **WAL-Modus** (`PRAGMA journal_mode=WAL`,
  dauerhaft in der Datei; `PRAGMA journal_mode` liefert danach `wal`).
- Jede fachliche Operation ist eine Transaktion (seit M1); nach einem
  Absturz zu jedem Zeitpunkt ist die Datenbank konsistent (`PRAGMA
  integrity_check` = `ok`, Invarianten aus `datenmodell.md` 3 und
  `synchronisation.md` 4.5).

### 5.2 Sauberes Beenden (Lifespan-Ende, `SIGTERM`)

Beim Ende des ASGI-Lifespans (uvicorn nach `SIGTERM`; in Tests das
Verlassen von `with TestClient(app):`) in dieser Reihenfolge:

1. Der Planer-Thread startet keinen neuen Takt und keinen neuen Lauf mehr.
2. Läuft ein Synchronisationslauf: Das gerade abgerufene Bankkonto darf bis
   zu `beenden_frist_sekunden` (Vorgabe 20) zu Ende verarbeitet werden
   (atomar nach `synchronisation.md` 4.5); weitere Konten werden nicht mehr
   abgerufen. Ist danach noch etwas offen, wird der Lauf `abgebrochen`
   (`beendet_am` gesetzt), noch nicht verarbeitete Konten `abgebrochen`;
   vollständig verarbeitete Konten behalten ihr Ergebnis. Ein Lauf, der in
   der Frist fertig wird, behält seinen normalen Status. Ein Konto, das die
   Frist überschreitet, wird nicht geschrieben (Rollback) und ist
   `abgebrochen`.
3. Ein auf TAN wartender Lauf bleibt, wie er ist (beim nächsten Start
   bricht ihn `synchronisation.md` 10 ab).
4. `PRAGMA wal_checkpoint(TRUNCATE)`, dann alle Verbindungen schließen.
   Danach existiert `<datenbank>-wal` nicht oder ist 0 Bytes groß; die
   Hauptdatei allein enthält den vollständigen Stand (wichtig für
   Snapshots und Kopien).

Das Lifespan-Ende ist spätestens `beenden_frist_sekunden + 5` Sekunden
nach seinem Beginn abgeschlossen. `TimeoutStopSec` der Unit ist größer.

### 5.3 Abbruch ohne Beenden

Wird der Prozess hart beendet (Absturz, `SIGKILL`, Stromausfall), gilt beim
nächsten Start `synchronisation.md` 10 unverändert; ein Lauf, der zum
Zeitpunkt des Abbruchs ein Konto verarbeitete, hat für dieses Konto nichts
geschrieben. In Tests wird das durch eine zweite App auf derselben
Datenbank ohne Lifespan-Ende der ersten simuliert.

### 5.4 Testhilfe: verzögertes Mock-Bank-Plugin

`KontorConfig.mock_verzoegerung_ms` (Vorgabe 0, 0–60 000, nur im
Mock-Modus wirksam): Das Mock-Bank-Plugin wartet bei jedem Aufruf von
`umsaetze()` diese Zeit, bevor es antwortet. So lässt sich ein Beenden
während eines Laufs deterministisch herbeiführen. Ohne das Feld verhält es
sich wie bisher.

## 6. Gesundheitsprüfung (`GET /api/gesundheit`)

Öffentlich (auch bei eingeschalteter Anmeldung, aber nicht außerhalb von
`erlaubte_netze`). 200 mit `{"status": "ok", "version": "<Version>"}`
(Schema `Gesundheit`), wenn die Datenbank mit einer Leseanfrage antwortet;
sonst 503 `nicht_bereit` (Schema `Fehler`). Keine weiteren Inhalte (kein
Modus außer dem Kopf `X-Kontor-Modus`, keine Zählungen). Ohne Wirkung, ohne
Protokoll, ohne Aktivität einer Sitzung.

## 7. Logging

- `python -m kontor` schreibt Logausgaben nach **stderr** (journald fügt
  Zeitstempel hinzu), eine Zeile je Eintrag im Format
  `<STUFE> <logger>: <Meldung>`; Stufe aus `log_stufe` (Vorgabe `INFO`;
  `DEBUG`, `INFO`, `WARNING`, `ERROR`). `create_app` selbst ändert die
  Logging-Konfiguration des Prozesses nicht (außer der Unterdrückung von
  Bibliotheks-Ausgaben mit Geheimnissen, `geheimnisse.md` 6).
- Anwendungslogger heißen `kontor` oder `kontor.<Bereich>`.
- Pflichteinträge: Start (`INFO`, mit Version und Modus), Ende (`INFO`),
  fehlgeschlagene Anmeldungen und Sperren (`WARNING`, `sicherheit.md` 4.5),
  Einrichtungscode-Datei angelegt (`WARNING`, nur Pfad), abgeschaltete
  Anmeldung im Echtmodus (`WARNING` beim Start).
- Nie in Logs: siehe `sicherheit.md` 9 und `geheimnisse.md` 6. Das
  Zugriffsprotokoll von uvicorn enthält Methode, Pfad samt Abfrage und
  Status; Abfragen enthalten keine Geheimnisse (die Schnittstelle nimmt
  Geheimnisse nur im Körper an).

## 8. Datenbank-Export und zeitgesteuerte Sicherung (Abgrenzung zu M9)

K 2 verlangt neben Proxmox-Snapshots einen Datenbank-Export. Das ist die
**Sicherung aus M9** (`sicherung.md`, ZIP mit eigenständiger SQLite-Datei
und Manifest); M7 führt kein zweites Exportformat ein (E-132). M7 ergänzt
nur die Automatisierung:

```python
# kontor.sicherung
def sichere_in_verzeichnis(config: KontorConfig, verzeichnis: str | os.PathLike[str], *,
                           behalten: int = 14) -> pathlib.Path: ...
```

- Erzeugt eine Sicherung mit `erstelle_sicherung(config)` (gleicher Inhalt,
  gleiche Regeln: nur lesend, keine Änderung im Protokoll) und schreibt sie
  als `<verzeichnis>/<Dateiname>` mit dem Dateinamen aus `sicherung.md` 3.1
  (`kontor-sicherung-<modus>-<JJJJMMTT>T<HHMMSS>Z.zip`, Zeitpunkt
  `erstellt` des Manifests). Gibt es die Datei schon (zwei Sicherungen in
  derselben Sekunde), wird sie ersetzt.
- Schreiben atomar (temporäre Datei im selben Verzeichnis, dann
  `os.replace`); Dateirechte `0600`. Fehlt das Verzeichnis, wird es mit
  `0700` angelegt.
- **Aufbewahrung:** Danach bleiben von den Dateien im Verzeichnis, deren
  Name dem Muster `kontor-sicherung-<modus>-…Z.zip` **desselben Modus**
  entspricht, die `behalten` neuesten (nach Zeitpunkt im Namen) erhalten;
  ältere werden gelöscht. Andere Dateien bleiben unberührt.
- `behalten` muss `int` ≥ 1 sein, sonst `ValueError` (vor jeder Wirkung).
- Rückgabe: Pfad der neuen Datei.

Kommandozeile `python -m kontor.sicherung --verzeichnis <pfad> [--behalten N]`:
Konfiguration aus `KontorConfig.from_env()`; schreibt den Pfad der neuen
Datei als einzige Zeile auf stdout, Rückgabecode 0; Konfigurationsfehler →
Rückgabecode 2 wie 2; andere Fehler (z. B. Verzeichnis nicht beschreibbar)
→ Meldung auf stderr, Rückgabecode 1. `--behalten` Vorgabe 14.

`sicherung.md` 8 („nicht auf dem Server abgelegt“) gilt weiter für
`GET /api/sicherung`; die zeitgesteuerte Ablage ist die bewusste Ausnahme
für Backups (`sicherung.md` 9).

**Proxmox-Snapshots** (Betrieb, nicht getestet): Wegen 5.1 und 5.2 ist ein
Snapshot des laufenden Containers konsistent (SQLite im WAL-Modus ist
absturzsicher); die tägliche Sicherung ist zusätzlich ein eigenständiges,
von Dateisystemzuständen unabhängiges Abbild.

## 9. Meilenstein 31: Testinstanz für Entwicklungsstände (Definition 3, D-205, D-213; E-284)

Zusätzliche Paketdaten in `kontor.betrieb` (wie 1):

| Datei | Zweck | Ziel im System |
| --- | --- | --- |
| `kontor-test.service` | zweite Instanz für einen Entwicklungsbranch | `/etc/systemd/system/` |
| `kontor-test.env` | Umgebungsdatei der Testinstanz | `/etc/kontor/kontor-test.env` |
| `kontor-test.sh` | Bedienskript (`start`, `neu`, `stop`, `loeschen`, `status`, `log`) | `/usr/local/bin/kontor-test` |

- **`kontor-test.service`** (statisch geprüft wie 4): `[Service]` mit
  `User`/`Group` genau `kontor`, `EnvironmentFile` genau
  `/etc/kontor/kontor-test.env`, `ExecStart` genau
  `/opt/kontor-test/venv/bin/python -m kontor`, `StateDirectory` genau
  `kontor-test`, `ProtectSystem` genau `strict`, `InaccessiblePaths` enthält
  `/var/lib/kontor` und `/etc/kontor/kontor.env`; dieselbe Härtung wie
  `kontor.service` (Tabelle 4.1 ab `NoNewPrivileges`); **keine**
  `LoadCredentialEncrypted`-Zeile; **kein** Abschnitt `[Install]`.
- **`kontor-test.env`** (Format wie 3, keine Geheimnisse nach 3):
  `KONTOR_MOCK_MODUS=1`, `KONTOR_PORT=8081`, `KONTOR_MAIL_ABGLEICH=0`;
  `KONTOR_DATENBANK` (falls gesetzt) liegt unter `/var/lib/kontor-test/`.
  `KontorConfig.from_env` mit ihren Variablen gelingt und ergibt
  `mock_modus = True`, `port = 8081`, `mail_abgleich = False`.
- **Kommandozeile** `python -m kontor.testinstanz` (`einrichten <Branch>`,
  `stoppen [--loeschen]`): Modul `kontor.testinstanz` ist importierbar; das
  Verhalten (Klonen, Datenkopie ohne Geheimnisse, Start) ist in kontor-tests
  nicht prüfbar (braucht root, systemd, Netz; E-284).

## 10. Meilenstein 32: Betrieb nur über HTTPS (Definition 4, D-239; E-305)

Zusätzlich ausgeliefert im Paket `kontor.betrieb`: `kontor-https.sh`
(Unterbefehle `einrichten`, `status`, `zurueck`; Anleitung
`spec/definitionen/anlagen/HTTPS.md`); `kontor-test.sh` schaltet bei einer
`https://`-Adresse in `kontor-test.env` die Freigabe ein und aus
(`TESTINSTANZ.md`). Die ausgelieferte `kontor.env` bleibt bei
`KONTOR_HOST=0.0.0.0`. Geprüft werden nur Vorhandensein, Unterbefehle und
dass kein Skript `tailscale funnel` aufruft; Ausführen braucht root, systemd
und Tailscale und wird nicht geprüft.

## 11. Testinstanz mit Demodaten (Feature `demodaten`, D-285)

Für Vorführungen lässt sich die Testinstanz (9) statt mit einer Kopie der Daten mit einem erfundenen Haushalt
füllen.

### 11.1 Kommandozeile und Bedienskript

- `python -m kontor.testinstanz demo [<Branch>]` (Vorgabe `main`): Branch holen und installieren wie
  `einrichten`; eine frühere Datenkopie entfernen; mit dem Python der Testinstanz
  `python -m kontor.demodaten <Mock-Datenbank> <Mock-Datendatei>` ausführen; Zusatz-Umgebungsdatei und Drop-in
  schreiben; `systemctl daemon-reload`; starten. Die Umgebungsdatei und die Datenbank der Hauptinstanz werden
  nicht gelesen; es muss sie nicht geben.
- Zusatz-Umgebungsdatei `/etc/kontor/kontor-test-demo.env`: `KONTOR_ANMELDUNG=0`,
  `KONTOR_MOCK_DATEN=/var/lib/kontor-test/demo-mockdaten.json`. Drop-in
  `/etc/systemd/system/kontor-test.service.d/demo.conf` mit `EnvironmentFile=-` auf diese Datei; sie wird nach
  `kontor-test.env` gelesen, ihre Angaben gelten. Die ausgelieferte Unit bleibt wie in 9.
- `einrichten` und `stoppen --loeschen` entfernen Zusatz-Umgebungsdatei, Drop-in und Mock-Datendatei.
- `kontor-test demo [branch]` ruft `demo` auf (Kurzname wie bei `start`, ohne Angabe `main`) und nennt, dass es
  keine Anmeldung gibt. `kontor-test neu` wiederholt, was zuletzt lief (`start` oder `demo`); `status` nennt die
  Art der Daten.

### 11.2 Generator `python -m kontor.demodaten`

`python -m kontor.demodaten <Mock-Datenbank> <Mock-Datendatei> [--heute JJJJ-MM-TT] [--monate N]`
(Vorgaben: heute, 36). Rückgabecode 0 und eine Zeile mit dem Umfang, sonst 1 und eine Meldung auf der
Fehlerausgabe. Python: `kontor.demodaten.aufbauen(datenbank, mock_datei, heute=None, monate=36) -> dict`,
`konfiguration(datenbank, mock_datei, **mehr) -> KontorConfig`, `welt(heute, monate=36) -> Welt`.

- Die **Welt** ist eine Funktion von Bezugstag, Zeitraum und festem Startwert (reproduzierbar). Sie reicht von
  `monate` Monaten vor dem Monat des Bezugstags bis 60 Tage danach. Nur erfundene Angaben: IBANs mit
  Bankleitzahl 00000000, Mailadressen unter `example.invalid`, keine PIN, keine TAN.
- Die **Mock-Datendatei** (`plugins.md` 7, Version 1) enthält zwei Bankkonten (Girokonto, Sparbuch) mit
  Anfangssalden, alle Umsätze und zwei Postfächer mit allen Mails der Welt.
- Die **Mock-Datenbank** entsteht neu (eine vorhandene Datei wird ersetzt) und nur über die REST-Schnittstelle
  der Anwendung, mit der simulierten Uhr des Mock-Modus: Stammdaten zum ersten Tag; danach Arbeitsgänge im
  Abstand von 90 Tagen (Konten abrufen, Mails abrufen, zuordnen, Tags, Belege, bestätigen, Benachrichtigungen
  lesen), nach jedem Jahreswechsel Jahresabgleich der Kredite, Abstimmung beider Konten zum 31.12. und Status
  `abgeglichen`; ein letzter voller Arbeitsgang 21 Tage, ein letzter Abruf ohne Nacharbeit 3 Tage vor dem
  Bezugstag.
- Mit dem vollen Zeitraum enthält der Bestand: ein Girokonto, ein Sparbuch, zwei Kreditkonten mit je einem
  Kredit; 14 Kategorien (acht oberste, sechs Unterkategorien); mindestens 2000 Buchungen; mindestens 100
  gespiegelte Mails in zwei Postfächern, ein Teil als Dokument an Buchungen; Belege als PDF; acht Regeln von
  Hand und automatisch angelegte; eine Split-Vorlage, zu der die letzten Abschläge nicht mehr passen; Tags;
  vier geplante Zahlungen, eine überfällig; genau einen offenen Dublettenverdacht (von Hand erfasste Ausgabe,
  die die Bank noch einmal liefert) und deshalb beim letzten Abruf einen Saldoausgleich im Girokonto; sonst
  stimmen die Kontostände mit den Salden der Mock-Bank.
- Offen (`importiert` oder `vorlaeufig`) sind nur Buchungen der letzten Wochen vor dem Bezugstag. Ein Abruf am
  Bezugstag liefert neue Buchungen und neue Mails.
- Die Konfiguration des Aufbaus entspricht der ausgelieferten `kontor-test.env` (Umbuchungen, Lernmodell,
  automatische Regeln, wiederkehrende Buchungen, Bestellnummern, nur Kopfzeilen; kein Mail-Abgleich).

Geprüft: `tests/core/test_demodaten.py`, `tests/test_demodaten_eigen.py`,
`tests/test_testinstanz_skript_eigen.py`. Nicht prüfbar: der Lauf unter systemd auf dem Server.

