# Geheimnisspeicher, Endpunkte und Netzregeln – Meilenstein 6

Verbindlich für Implementierung und Tests. Umsetzung von K 3 („Tokens und
Zugangsdaten verschlüsselt gespeichert, nie im Klartext“), K 6 (PIN nie in
Logs, Datenbank, Fehlermeldungen oder Kommandozeilenargumenten) und T 18
(„Keine Geheimnisse in Logs oder Fehlermeldungen“). Ergänzt
`python-api.md` (Abschnitt 13), `openapi.yaml` (Tag `geheimnisse`) und
`sicherung.md` (2.6). Die echten Anbindungen stehen in `fints.md`,
`mail.md` und `benachrichtigungen.md`.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

## 1. Begriffe

- **Geheimnis**: ein Wert, mit dem sich Zugang zu einem Fremdsystem
  verschaffen lässt. In Kontor genau: Banking-PIN, TAN, OAuth-Client-Secret,
  OAuth-Refresh- und Access-Tokens, ntfy-Zugriffstoken, der
  Geheimnisschlüssel (2) selbst und die PKCE-Werte `state`/`code_verifier`
  sowie Autorisierungscodes einer laufenden Anmeldung (`mail.md` 4).
- **Kein Geheimnis** (Konfiguration, darf im Klartext stehen): FinTS-URL,
  Bankleitzahl, Benutzerkennung, Kunden-ID, Produkt-ID, IMAP-Host,
  Postfachadressen, OAuth-Client-ID, ntfy-URL und -Thema, öffentliche URL
  (E-116).
- Die **PIN** liegt nie im Geheimnisspeicher: Sie wird nur im Arbeitsspeicher
  gehalten (`synchronisation.md` 12) oder beim Dienststart von systemd
  übergeben (`fints.md` 5). Die **TAN** wird nur durchgereicht.

## 2. Schlüssel

Alle Geheimnisse des Speichers werden mit einem 256-Bit-Schlüssel
verschlüsselt. Herkunft (die erste zutreffende Quelle gilt):

1. **systemd-creds:** Ist `KontorConfig.credentials_verzeichnis` gesetzt (aus
   `$CREDENTIALS_DIRECTORY`) und existiert darin die Datei
   `kontor-geheimnisschluessel`, ist ihr Inhalt der Schlüssel. So kann er mit
   `systemd-creds encrypt` (möglichst an das TPM gebunden) abgelegt und per
   `LoadCredentialEncrypted=kontor-geheimnisschluessel:…` nur dem Dienst
   übergeben werden. `quelle = "systemd-creds"`.
2. **Schlüsseldatei:** sonst `KontorConfig.geheimnis_schluessel_datei`;
   Vorgabe (None) ist `aktive_datenbank.with_suffix(".schluessel")`, z. B.
   `kontor.sqlite3` → `kontor.schluessel`, im Mock-Modus
   `kontor-mock.schluessel`. `quelle = "datei"`.

**Format:** Der Inhalt ist die Base64-Kodierung (Standardalphabet mit
Auffüllung, RFC 4648 Abschnitt 4) von genau 32 Bytes, optional gefolgt von
Leerraum (z. B. `\n`). Alles andere ist **ungültig**.

**Anlegen:** Fehlt bei Quelle `datei` die Datei, legt die App sie beim
ersten Schreiben eines Geheimnisses an (nie vorher, nie bei `create_app`):
32 Bytes aus `secrets.token_bytes`, Base64 + `\n`, Dateirechte `0600`
(fehlende Elternverzeichnisse werden angelegt). Bei Quelle `systemd-creds`
wird nie eine Datei angelegt.

**Ungültiger oder fehlender Schlüssel:** Lesen ist dann nicht möglich (alle
Einträge `lesbar = false`); Schreiben bei ungültigem Schlüssel → 409
`geheimnis_schluessel_ungueltig`. Ein Geheimnis, das mit einem anderen
Schlüssel verschlüsselt wurde, ist ebenfalls `lesbar = false`. Nicht lesbare
Geheimnisse gelten überall als **nicht vorhanden** (die App verwendet sie
nicht und meldet keinen Klartext oder Chiffretext).

## 3. Verschlüsselung und Ablage

- Verfahren: **AES-256-GCM** (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`,
  per pip installierbar; geprüft am 2026-11-09: `cryptography` 50.0, in der
  Testumgebung vorhanden), je Schreiben eine neue zufällige Nonce von 12
  Bytes, zusätzliche authentisierte Daten = Name des Geheimnisses (UTF-8).
  Gespeichert werden Nonce und Chiffretext (mit Authentisierungsmarke).
- Ablage in der aktiven Datenbank (Tabelle frei). Die Datenbankdateien
  (einschließlich `-wal`, `-journal`, `-shm`) enthalten den Klartext nie,
  auch nicht vorübergehend; nach dem Löschen eines Geheimnisses auch nicht
  dessen Chiffretext in freien Seiten (z. B. `secure_delete`), soweit SQLite
  das zulässt.
- Mock- und Echtmodus haben getrennte Datenbanken und damit getrennte
  Speicher und Schlüssel (K 3).

## 4. Namen

| Name | Inhalt | Schreiben |
| --- | --- | --- |
| `ntfy_token` | Zugriffstoken für den ntfy-Server (`benachrichtigungen.md` 3) | REST (5) |
| `oauth_client_secret` | Client-Secret des eigenen Google-Cloud-Projekts (`mail.md` 4) | REST (5) |
| `mail_token:<adresse>` | Refresh-Token, Access-Token und deren Ablauf eines Postfachs; `<adresse>` = Postfachadresse nach `casefold()` | nur intern (OAuth-Anmeldung, `mail.md` 4) |

Ab M23 (`geheimnisschutz.md` 1, E-228) zusätzlich `bank_pin` (gemerkte Bank-PIN,
nur intern über `PUT /api/sync/pin/gemerkt`) und `mail_passwort:<adresse>`
(App-Passwort eines Postfachs, nur intern über
`PUT /api/mail/postfaecher/{id}/app-passwort`); beide erscheinen in
`GET /api/geheimnisse` und sind über `PUT`/`DELETE /api/geheimnisse/{name}` nicht
ansprechbar (404). Weitere Namen gibt es nicht. Einträge `mail_token:…` entstehen nur durch eine
erfolgreiche Anmeldung und entfallen beim Abmelden, beim Löschen des
Postfachs und wenn der Anbieter den Refresh-Token ablehnt (`mail.md` 5).

**Schutz mit dem Login-Passwort (ab M23):** Optional werden alle Geheimnisse außer
`ntfy_token` zusätzlich mit einem nur über das Login-Passwort zugänglichen Schlüssel
verschlüsselt; gesperrt sind sie `lesbar = false` und nicht schreibbar
(`geheimnisschutz.md` 1, 2). Ohne eingeschalteten Schutz gilt dieses Dokument
unverändert.

## 5. REST (`openapi.yaml`, Tag `geheimnisse`)

| Methode, Pfad | Zweck |
| --- | --- |
| `GET /api/geheimnisse` | 200 `GeheimnisUebersicht` |
| `PUT /api/geheimnisse/{name}` | Körper `{"wert": "<1–4096 Zeichen>"}` → 204; ersetzt einen vorhandenen Wert |
| `DELETE /api/geheimnisse/{name}` | 204, auch wenn nicht gesetzt (idempotent) |

- `{name}` nur `ntfy_token` oder `oauth_client_secret`, sonst 404
  `nicht_gefunden` (auch für `mail_token:…`).
- Körper ungültig (fehlt, kein String, leer, zu lang, unbekanntes Feld) →
  422 `validierung`. Die Antwort enthält den übergebenen Wert **nie**, auch
  nicht in `details`.
- Weder Klartext noch Chiffretext erscheinen je in einer Antwort.
- `GeheimnisUebersicht`:

```json
{"schluessel": {"quelle": "datei", "vorhanden": true, "gueltig": true},
 "eintraege": [{"name": "ntfy_token", "gesetzt_am": "2026-11-09T10:00:00Z", "lesbar": true}]}
```

  `vorhanden` = Schlüsselquelle existiert; `gueltig` = vorhanden und im
  Format nach 2. `eintraege` nach `name` aufsteigend, je gespeichertem
  Geheimnis einer (auch `mail_token:…`); `gesetzt_am` = App-Uhr beim letzten
  Schreiben.
- Geheimnisse sind **kein** Buchbestand: Schreiben und Löschen erzeugen keine
  Änderung im Protokoll (`protokoll.md` 12).

## 6. Wo Geheimnisse nie erscheinen

Für jedes Geheimnis aus 1 gilt (Prüfung in den M6-Tests):

1. nicht im Klartext in Datenbankdateien (3);
2. in keiner Logausgabe (jeder Logger, jede Stufe einschließlich `DEBUG`,
   auch Logger verwendeter Bibliotheken wie `fints`, `urllib3`, `httpx`,
   `imaplib`; stdout/stderr) – die App konfiguriert Bibliotheks-Logger so,
   dass sie keine Geheimnisse ausgeben (python-fints protokolliert auf
   `DEBUG` vollständige Nachrichten einschließlich der TAN);
3. in keiner API-Antwort, keiner Fehlermeldung, keinem `details` einer
   Ausnahme, keinem `repr()` eines Plugins, einer Konfiguration oder eines
   Datenobjekts;
4. in keiner Benachrichtigung (Titel, Text, Link) und keiner Push-Nachricht
   außer dem ntfy-Token im `Authorization`-Kopf an den ntfy-Server;
5. in keiner Sicherung (`sicherung.md` 2.6), weder im Klartext noch
   verschlüsselt;
6. nie als Kommandozeilenargument eines Prozesses: Die App startet für
   Geheimnisse keine Unterprozesse; `systemd-creds` wird nur vom Betreiber
   aufgerufen (`fints.md` 5).

Ausnahmen, die zwangsläufig sind: Die PIN und die TAN gehen an den
FinTS-Server, Tokens an den OAuth- und IMAP-Server, jeweils nur an den
konfigurierten Endpunkt.

## 7. Endpunkte und Transportsicherheit

Alle Endpunkte von Fremdsystemen sind konfigurierbar (`python-api.md` 13.1);
das ist zugleich die **Naht** für die lokalen Attrappen der Tests (E-028).

- URL-Felder (`fints_url`, `oauth_*_url`, `oauth_redirect_uri`, `ntfy_url`,
  `oeffentliche_url`) müssen absolute `http`- oder `https`-URLs mit Host sein.
- **Klartext nur auf Loopback:** `http://` (und `imap_tls = False`) ist nur
  erlaubt, wenn der Host `127.0.0.1`, `::1` (in der URL `[::1]`) oder
  `localhost` ist – sonst `KonfigurationsFehler` bei der Konstruktion der
  Konfiguration. Ausnahmen: `oeffentliche_url` (Link für den Haushalt im
  Heimnetz, K 2) und `oauth_redirect_uri` (Loopback-Umleitung,
  `mail.md` 4.1) dürfen beliebige `http`-Hosts haben.
- TLS-Verbindungen prüfen Zertifikat und Hostnamen immer. Ist
  `tls_ca_datei` gesetzt (PEM), werden für **alle** ausgehenden
  TLS-Verbindungen (FinTS, OAuth, IMAP, ntfy) ausschließlich diese
  Zertifikate als Vertrauensanker verwendet; sonst die des Systems.
- Verbindungen gehen nur zu den konfigurierten Hosts; die App folgt keinen
  HTTP-Umleitungen zu anderen Hosts.
- Mock-Plugins bauen nie Verbindungen auf (`plugins.md` 3). Im Mock-Modus
  darf nur das Benachrichtigungs-Plugin `ntfy` echte Verbindungen aufbauen
  (`benachrichtigungen.md` 2, E-119).
