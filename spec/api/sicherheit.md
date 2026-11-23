# Anmeldung und Sicherheit – Meilenstein 7

Verbindlich für Implementierung und Tests. Umsetzung von K 2 (gemeinsamer
Login für den Haushalt, nur Heimnetz), K 3 (Geheimnisse nie im Klartext),
K 6 (PIN nie in Logs, Fehlermeldungen oder Kommandozeilen) und T 18 (ohne
Login keine Seite und kein API-Endpunkt, Angriffseingaben gegen
SQL-Injection, XSS und CSRF, Sitzungsablauf, Bremse bei falschen
Passwörtern, keine Geheimnisse in Logs oder Fehlermeldungen). Betrieb
(systemd, Neustart, Logging): `betrieb.md`; Leistung: `leistung.md`;
Python-Schnittstelle: `python-api.md` 14; REST: `openapi.yaml` ab 2.7.0
(Tag `anmeldung`). Abkürzungen: K = `konzept.md`, T = `testkonzept.md`,
E = `entscheidungen.md`.

**Rückwärtskompatibel (E-029, E-125):** Die Anmeldung ist abschaltbar;
Vorgabe `anmeldung = False` (Python und `from_env`). Ohne Anmeldung
verhält sich jede Instanz wie in M6, ergänzt nur um die Regeln, die nie
eine gültige frühere Anfrage ablehnen (Sicherheitsköpfe 6, Eingabehärtung
7, Größengrenzen 8 mit großzügigen Vorgaben). Im Betrieb schaltet die
ausgelieferte Umgebungsdatei die Anmeldung ein (`KONTOR_ANMELDUNG=1`,
`betrieb.md` 3); die M7-Tests prüfen das.

## 1. Begriffe

- **Haushaltskonto:** genau ein gemeinsames Passwort je Datenbank
  (`aktive_datenbank`; Mock- und Echtdatenbank haben je ein eigenes). Es
  gibt keine Benutzernamen und keine Rollen (K 16: keine mehreren Benutzer).
- **Eingerichtet:** In der aktiven Datenbank ist ein Passwort-Hash
  gespeichert.
- **Sitzung:** serverseitig gespeicherter Anmeldezustand, im Browser
  vertreten durch das Cookie `kontor_sitzung`.
- **Geschützter Pfad:** jeder Pfad außer den öffentlichen (3.1).
- **Anmeldedaten:** Passwort-Hash, Sitzungen, CSRF-Token, Fehlversuchszähler,
  Sperre und Einrichtungscode. Sie sind **Betriebszustand**: nicht im
  Änderungsprotokoll, nicht rückgängig zu machen, nie Teil einer Sicherung
  (`sicherung.md` 9), unverändert beim Einspielen einer Sicherung.
- **Geheimnisse dieses Dokuments:** Passwort (auch falsche Eingaben),
  Sitzungstoken, CSRF-Token, Einrichtungscode. Für sie gilt 9 zusätzlich zu
  `geheimnisse.md` 6.

## 2. Passwort

### 2.1 Regeln

- Das Passwort ist eine Zeichenkette; maßgeblich ist ihre
  **NFC-Normalform** (`unicodedata.normalize("NFC", …)`), kodiert als UTF-8.
  Eingaben in NFD und NFC sind also dasselbe Passwort.
- Länge der NFC-Form: 12 bis 1 024 Zeichen (Codepunkte). Sonst ist das
  Passwort ungültig (Python: `ValueError`; REST: 422 `validierung`, ohne
  das Passwort in Meldung oder `details`). Weitere Regeln (Zeichenklassen)
  gibt es nicht.

### 2.2 Hash-Verfahren (festgelegt, E-126)

scrypt (RFC 7914) über `hashlib.scrypt` der Standardbibliothek:

- Parameter `n = 32768` (2^15), `r = 8`, `p = 1`, Schlüssellänge 32 Bytes,
  `maxmem = 67108864` (64 MiB); Salz: 16 Bytes aus `secrets.token_bytes`,
  je Hash neu.
- Textform (so gespeichert und von `kontor.anmeldung.passwort_hash`
  geliefert):

  ```
  scrypt$<n>$<r>$<p>$<salz>$<schluessel>
  ```

  `<n>`, `<r>`, `<p>` als Dezimalzahlen ohne führende Nullen, `<salz>` und
  `<schluessel>` Base64 (Standardalphabet mit Auffüllung, RFC 4648
  Abschnitt 4). Beispielaufbau: `scrypt$32768$8$1$<24 Zeichen>$<44 Zeichen>`.
- **Prüfen** (`passwort_pruefen`): Textform zerlegen, scrypt mit den
  **gespeicherten** Parametern über die NFC-Form rechnen, Vergleich mit
  `hmac.compare_digest`. Jede nicht wohlgeformte Textform (anderes
  Verfahren, falsche Anzahl Teile, ungültiges Base64, `n` keine Zweierpotenz
  ≥ 2, `n`, `r`, `p` außerhalb 1…2^20 bzw. 1…64, Schlüssel nicht 32 Bytes)
  ergibt `False`, nie eine Ausnahme. Damit lassen sich die Parameter
  später erhöhen, ohne alte Hashes ungültig zu machen.
- Das Passwort selbst wird nie gespeichert, protokolliert oder
  zurückgegeben.

## 3. Schutz der Pfade

### 3.1 Öffentliche Pfade

Bei eingeschalteter Anmeldung sind ohne Sitzung **nur** erreichbar:

| Methode und Pfad | Zweck |
| --- | --- |
| `GET /api/anmeldung` | Anmeldestatus (4.1) |
| `POST /api/anmeldung` | Anmelden (4.2) |
| `POST /api/anmeldung/einrichten` | Ersteinrichtung (5) |
| `GET /api/gesundheit` | Gesundheitsprüfung (`betrieb.md` 6) |
| `GET /anmelden` | Anmeldeseite (3.4) |
| `GET /oeffentlich/…` | statische Dateien der Anmeldeseite (CSS, Skript, Symbole, Manifest) |

`HEAD` ist für die `GET`-Pfade gleichwertig zulässig.

### 3.2 Geschützte Pfade

Jede andere Anfrage (jeder Pfad, jede Methode, auch unbekannte Pfade und
unzulässige Methoden) braucht eine **gültige Sitzung** (4.4):

- Pfade unter `/api/` ohne gültige Sitzung → **401** `nicht_angemeldet`
  (Schema `Fehler`, `details = {}`), vor jeder anderen Prüfung außer der
  Netzprüfung (10): also auch statt 404, 405, 413 oder 422. Kein Inhalt
  aus dem Buchbestand, kein Hinweis, ob ein Pfad existiert.
- Andere Pfade (Oberfläche, `GET /`, M8-Seiten) ohne gültige Sitzung →
  **303** mit `Location: /anmelden?weiter=<p>`; `<p>` ist der
  ursprüngliche Pfad samt Abfrage, prozentkodiert nach RFC 3986 (jedes
  Zeichen außer `A–Z a–z 0–9 - . _ ~ /` kodiert, also auch `?`, `&`, `%`,
  CR und LF). Der Körper ist leer oder ein kurzer Text ohne Teile der
  Anfrage.
- `GET /anmelden` **mit** gültiger Sitzung → 303 nach `/`.

### 3.3 Abgeschaltete Anmeldung

Bei `anmeldung = False` sind alle Pfade wie in M6 ohne Sitzung erreichbar;
es werden keine Cookies gesetzt und keine CSRF-Köpfe verlangt.
`GET /api/anmeldung` liefert `aktiv = false`; `POST /api/anmeldung`,
`/api/anmeldung/einrichten`, `/api/anmeldung/abmelden` und
`PUT /api/anmeldung/passwort` → 409 `anmeldung_abgeschaltet`.
`GET /anmelden` → 303 nach `/`.

### 3.4 Anmeldeseite (`GET /anmelden`)

- 200, `text/html; charset=utf-8`; vollständig ohne Inhalte aus dem
  Buchbestand.
- Enthält ein Formular mit `data-testid="anmeldung-formular"`, ein
  Passwortfeld (`<input type="password">`) mit
  `data-testid="anmeldung-passwort"` und – nur solange nicht eingerichtet –
  ein Feld mit `data-testid="anmeldung-einrichtungscode"`. Die Seite
  sendet per Skript an `POST /api/anmeldung` bzw.
  `POST /api/anmeldung/einrichten` und leitet danach zu `weiter` weiter,
  wenn es mit genau einem `/` beginnt (nicht `//`, nicht `/\`), sonst zu
  `/` (keine offene Weiterleitung).
- Im Mock-Modus zeigt sie den Mock-Hinweis wie `GET /` (`plugins.md` 6,
  Element `id="mock-hinweis"`); im Echtmodus enthält sie `mock-hinweis` nicht.
- Der Wert von `weiter` erscheint nicht unmaskiert im HTML (7.2).

## 4. Anmelden, Sitzungen, Abmelden

### 4.1 Status (`GET /api/anmeldung`, Schema `AnmeldeStatus`)

```json
{"aktiv": true, "eingerichtet": true, "angemeldet": true,
 "csrf_token": "…", "sitzung_ablauf": "2026-11-10T08:00:00Z", "gesperrt_bis": null}
```

- `aktiv` = `anmeldung`; `eingerichtet` (2); `angemeldet` = die Anfrage
  trägt eine gültige Sitzung.
- `csrf_token` und `sitzung_ablauf` nur bei `angemeldet`, sonst null.
  `sitzung_ablauf` = frühester Ablaufzeitpunkt nach 4.4 (nach Zählung
  dieser Anfrage als Aktivität).
- `gesperrt_bis`: Ende der laufenden Sperre (4.5) oder null.
- Öffentlich; zählt bei gültiger Sitzung als Aktivität.

### 4.2 Anmelden (`POST /api/anmeldung`)

Körper `{"passwort": "…"}` (Schema `AnmeldeEingabe`, 1–4 096 Zeichen,
keine weiteren Felder). Prüfreihenfolge:

1. Anmeldung abgeschaltet → 409 `anmeldung_abgeschaltet`.
2. Körper ungültig → 422 `validierung` (ohne Passwort in der Antwort).
3. Nicht eingerichtet → 409 `nicht_eingerichtet`.
4. Sperre läuft (4.5) → **429** `anmeldung_gesperrt`, `details =
   {"gesperrt_bis": <Zeitstempel>}`, Kopf `Retry-After` = verbleibende
   Sekunden aufgerundet (≥ 1). Das Passwort wird **nicht** geprüft, auch
   ein richtiges nicht; der Versuch zählt nicht als Fehlversuch.
5. Passwort falsch (2.2) → **401** `anmeldung_fehlgeschlagen`,
   `details = {}`; Fehlversuch zählen (4.5).
6. Erfolg → **200** mit `AnmeldeStatus` (`angemeldet = true`, neues
   `csrf_token`) und `Set-Cookie` für eine **neue** Sitzung (4.3);
   Fehlversuchszähler auf 0. Ein mitgesendetes altes Cookie wird nicht
   übernommen (keine Sitzungsfixierung); war es gültig, bleibt jene Sitzung
   unberührt bestehen.

Die Herkunftsprüfung (4.6) gilt auch hier.

### 4.3 Sitzungs-Cookie

- Name `kontor_sitzung`, Wert: 43 Zeichen aus `secrets.token_urlsafe(32)`.
- Attribute: `HttpOnly`, `SameSite=Strict`, `Path=/`,
  `Max-Age=<sitzung_hoechstdauer_sekunden>`; `Secure`, wenn
  `sitzung_cookie_secure` wahr ist oder (Vorgabe None) die Anfrage über
  `https` kam (Schema der ASGI-Anfrage). Kein `Domain`-Attribut.
- Serverseitig wird nur ein Hash des Tokens gespeichert (z. B. SHA-256);
  der Tokenwert selbst steht nie in einer Datei der Datenbank (auch nicht in
  `-wal`/`-shm`), in keinem Log und in keiner Antwort außer dem
  `Set-Cookie`-Kopf der Anmeldung bzw. Einrichtung.
- Zu jeder Sitzung gehört ein CSRF-Token (43 Zeichen aus
  `secrets.token_urlsafe(32)`), das sich während der Sitzung nicht ändert.

### 4.4 Gültigkeit und Ablauf

Eine Sitzung ist gültig, wenn sie existiert, nicht abgemeldet ist und

- seit ihrer letzten Aktivität höchstens `sitzung_leerlauf_sekunden`
  (Vorgabe 86 400 = 1 Tag) und
- seit ihrer Erstellung höchstens `sitzung_hoechstdauer_sekunden`
  (Vorgabe 2 592 000 = 30 Tage)

vergangen sind. Jede Anfrage mit gültiger Sitzung ist Aktivität. Maßgeblich
ist immer die **Systemuhr** (UTC), auch im Mock-Modus: Die simulierte
App-Uhr (`synchronisation.md` 8) wirkt nicht auf Sitzungen, Sperren und
Einrichtung (sonst ließe sich der Ablauf über `PUT /api/mock/zeit`
umgehen). Abgelaufene Sitzungen dürfen gelöscht werden; ihr Cookie ist dann
unbekannt (ebenfalls 401). Sitzungen überstehen einen Neustart der App
(sie liegen in der Datenbank).

### 4.5 Bremse bei falschen Passwörtern

- Der Zähler `fehlversuche` (je Datenbank, gespeichert, übersteht einen
  Neustart) zählt aufeinanderfolgende Fehlversuche: falsches Passwort bei
  der Anmeldung (4.2 Schritt 5), falsches `altes_passwort` (4.8) und
  falscher Einrichtungscode (5). Ein Erfolg (Anmeldung, Einrichtung,
  Passwortänderung) setzt ihn auf 0 und hebt eine Sperre auf.
- Nach einem Fehlversuch mit `fehlversuche ≥ anmeldung_fehlversuche`
  (Vorgabe 5) beginnt eine Sperre mit der Dauer
  `min(anmeldung_sperre_sekunden · 2^(fehlversuche − anmeldung_fehlversuche), 86 400)`
  Sekunden (Vorgabe `anmeldung_sperre_sekunden = 60`). Die Antwort auf
  genau diesen Versuch ist noch 401 bzw. 403; jeder weitere Versuch
  während der Sperre → 429 (4.2 Schritt 4), ohne Prüfung und ohne Zählung.
- Beispiel mit 3 und 1 s: Versuche 1 und 2 falsch → 401; Versuch 3 falsch →
  401 und 1 s Sperre; während der Sperre → 429; danach Versuch 4 falsch →
  401 und 2 s Sperre; Versuch 5 falsch → 401 und 4 s Sperre.
- Die Bremse gilt für das Haushaltskonto insgesamt, nicht je
  Client-Adresse (alle Geräte des Haushalts teilen ein Passwort; hinter NAT
  wäre die Adresse ohnehin dieselbe).
- Jeder Fehlversuch und jeder Beginn einer Sperre wird mit Stufe `WARNING`
  über den Logger `kontor.anmeldung` protokolliert (mit Client-Adresse, ohne
  Passwort oder Teile davon).

### 4.6 CSRF-Schutz und Herkunftsprüfung

Bei eingeschalteter Anmeldung gilt für jede Anfrage mit `POST`, `PUT`,
`PATCH` oder `DELETE` (Reihenfolge der Prüfungen: Netz (10), bei
geschützten Pfaden Sitzung (3.2), dann Herkunft, dann Token, erst danach
Größe, Routing und Validierung):

1. **Herkunft** (auch für die öffentlichen `POST`-Pfade): Trägt die Anfrage
   den Kopf `Origin`, muss dessen Ursprung (`schema://host[:port]`, ohne
   Standardport) gleich dem Ursprung der Anfrage selbst sein (Schema der
   ASGI-Anfrage, Kopf `Host`) oder gleich dem Ursprung von
   `oeffentliche_url` (falls gesetzt). `Origin: null` ist nie gleich. Trägt
   sie `Sec-Fetch-Site: cross-site`, ist sie abzulehnen. Sonst → 403
   `csrf_ungueltig`. Ohne beide Köpfe (z. B. Skripte, `TestClient`) gilt
   die Herkunft als in Ordnung.
2. **Token** (nur geschützte Pfade, nach der Sitzungsprüfung): Der Kopf
   `X-Kontor-CSRF` muss gleich dem CSRF-Token der Sitzung sein
   (`hmac.compare_digest`). Fehlt er oder weicht er ab → 403
   `csrf_ungueltig`, ohne Wirkung und ohne Änderung im Protokoll.

`GET`- und `HEAD`-Anfragen ändern nie Zustand (gilt seit M1) und brauchen
kein Token. Das Cookie mit `SameSite=Strict` ist eine zusätzliche, keine
alleinige Absicherung.

### 4.7 Abmelden (`POST /api/anmeldung/abmelden`)

Geschützt (Sitzung und CSRF-Token nötig). Beendet die Sitzung der Anfrage
serverseitig sofort; Antwort **204** mit `Set-Cookie: kontor_sitzung=;
Max-Age=0; Path=/; HttpOnly; SameSite=Strict`. Danach führt dasselbe
Cookie zu 401. Andere Sitzungen bleiben.

### 4.8 Passwort ändern (`PUT /api/anmeldung/passwort`)

Geschützt. Körper `{"altes_passwort": "…", "neues_passwort": "…"}`
(Schema `PasswortAenderung`). Prüfreihenfolge nach Sitzung und CSRF:
Körper ungültig oder `neues_passwort` verletzt 2.1 → 422 `validierung`;
Sperre → 429; `altes_passwort` falsch → **403** `anmeldung_fehlgeschlagen`
(Fehlversuch); sonst neuer Hash (neues Salz), **alle anderen** Sitzungen
beendet, die eigene bleibt (gleiches Cookie, gleiches CSRF-Token);
Antwort 200 `AnmeldeStatus`.

### 4.9 Ab M23: Schutz der Geheimnisse

Ein erfolgreicher `POST /api/anmeldung` entsperrt eine gesperrte App-Instanz;
`PUT /api/anmeldung/passwort` hält den Schutz mit dem neuen Passwort aktiv;
das Setzen ohne altes Passwort (5.1) löscht bei aktivem Schutz die geschützten
Geheimnisse und schaltet ihn aus. Die Endpunkte mit Login-Passwort
(`POST /api/geheimnisse/schutz`, `…/schutz/ausschalten`, `…/entsperren`) zählen
Fehlversuche in die Bremse (4.5) und antworten auf ein falsches Passwort mit
**403** `anmeldung_fehlgeschlagen` (`geheimnisschutz.md` 2).

## 5. Ersteinrichtung

Zwei gleichwertige Wege; beide setzen das Passwort, beenden alle Sitzungen
und löschen den Einrichtungscode.

1. **Python/Kommandozeile** (`python-api.md` 14.2):
   `kontor.anmeldung.passwort_setzen(config, passwort)` bzw.
   `python -m kontor.anmeldung passwort-setzen` (liest das Passwort von
   stdin, nie aus Argumenten oder Umgebungsvariablen). Funktioniert auch bei
   abgeschalteter Anmeldung und ersetzt ein vorhandenes Passwort (Notfall:
   Passwort vergessen).
2. **Weboberfläche** mit **Einrichtungscode**: Erzeugt die App
   (`create_app`) eine Instanz mit `anmeldung = True`, die nicht
   eingerichtet ist, legt sie die Datei
   `<aktive_datenbank>.einrichtung` (z. B. `kontor.sqlite3.einrichtung`)
   mit Rechten `0600` an: genau 32 Kleinbuchstaben-Hexziffern aus
   `secrets.token_hex(16)` und `\n`. Eine vorhandene, wohlgeformte Datei
   wird weiterverwendet. Die App protokolliert mit Stufe `WARNING` den
   **Pfad** der Datei (nie den Code). Der Betreiber liest den Code auf dem
   Server (`cat`) und gibt ihn mit dem neuen Passwort auf der Anmeldeseite
   ein.

`POST /api/anmeldung/einrichten`, Körper `{"einrichtungscode": "…",
"passwort": "…"}` (Schema `EinrichtungEingabe`). Prüfreihenfolge:
abgeschaltet → 409 `anmeldung_abgeschaltet`; Körper ungültig oder Passwort
verletzt 2.1 → 422 `validierung`; eingerichtet → 409 `bereits_eingerichtet`;
Sperre → 429; Code ungleich dem Inhalt der Datei (ohne `\n`, Vergleich mit
`hmac.compare_digest`; fehlende Datei zählt als ungleich) → **403**
`einrichtungscode_ungueltig` (Fehlversuch nach 4.5); sonst Passwort setzen,
Datei löschen und wie 4.2 Schritt 6 anmelden (200, Cookie).

Ohne Einrichtung ist bei eingeschalteter Anmeldung nur 3.1 erreichbar.

## 6. Sicherheitsköpfe (immer, auch ohne Anmeldung)

Jede Antwort der App (jeder Pfad, jeder Status, auch 3xx, 401, 404, 5xx)
trägt:

| Kopf | Wert |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Content-Security-Policy` | siehe unten |
| `Cross-Origin-Opener-Policy` | `same-origin` |

Zusätzlich `Cache-Control: no-store` für jede Antwort unter `/api/` und
jede HTML-Antwort (`/`, `/anmelden`, Seiten der Oberfläche); Dateien unter
`/oeffentlich/` dürfen zwischengespeichert werden. Dateien unter
`/oeffentlich/` tragen `Cache-Control: no-cache` und einen `ETag`; eine
bedingte Anfrage mit passendem `If-None-Match` ergibt 304 ohne Körper (M26,
`oberflaeche.md` 36.8, E-246).

**Content-Security-Policy:** Die Direktiven sind durch `;` getrennt; diese
müssen mit genau diesen Quellen vorhanden sein (weitere Direktiven wie
`style-src`, `img-src`, `connect-src`, `manifest-src`, `worker-src` sind
frei, solange sie keine fremden Hosts nennen):

- `default-src 'self'`
- `script-src 'self'` (kein `'unsafe-inline'`, kein `'unsafe-eval'`, kein
  `*`, keine Nonce/Hash-Ausnahmen)
- `object-src 'none'`
- `base-uri 'none'`
- `frame-ancestors 'none'`
- `form-action 'self'`

Empfohlener Gesamtwert: `default-src 'self'; script-src 'self'; style-src
'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self';
object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action
'self'`. Folge für die Oberfläche: kein Inline-Skript, keine
`on…`-Attribute, kein `javascript:`-URL (7.2).

## 7. Eingabehärtung (immer)

### 7.1 SQL-Injection

Alle Eingaben (Körper, Pfad- und Abfrageparameter, Dateiinhalte beim
Import) werden ausschließlich als gebundene Parameter verwendet oder gegen
feste Listen geprüft (z. B. `sortierung`). Texte mit SQL-Syntax (`'`, `"`,
`;`, `--`, `/* */`, `%`, `_`, `\`, `OR 1=1`, `DROP TABLE`, `UNION
SELECT`) werden unverändert gespeichert und zurückgegeben und wirken in
Filtern und Suche nur als Text nach den bekannten Vergleichsregeln
(`datenmodell.md` 1, `buchhaltungspflege.md` Suche). `%` und `_` sind in
Text- und Suchfiltern **keine** Platzhalter. Ungültige Typen in Parametern
(`konto_id=1 OR 1=1`) → 422.

### 7.2 XSS

- Die REST-Schnittstelle liefert Texte unverändert (keine HTML-Maskierung
  in JSON) mit `Content-Type: application/json`; mit `nosniff` deutet kein
  Browser sie als HTML.
- Serverseitig erzeugtes HTML (`/`, `/anmelden`, Fehlerseiten, Seiten der
  Oberfläche) enthält **keine Texte aus dem Buchbestand** (die Oberfläche
  lädt sie per REST und setzt sie als Text, nie als HTML) und gibt keinen
  Teil der Anfrage (Pfad, Abfrage, Köpfe) unmaskiert wieder.
- Jedes `<script>`-Element im ausgelieferten HTML hat ein `src`-Attribut
  auf einen Pfad derselben Herkunft und keinen Inhalt; kein Element trägt
  ein Attribut, das mit `on` beginnt; kein `href`/`src` beginnt mit
  `javascript:`.
- Pfade außerhalb von `/api/`, `/oeffentlich/` und `/anmelden` liefern
  angemeldet die Oberfläche (wie `GET /`, für Routen der SPA) oder 404;
  in beiden Fällen erscheint der Pfad nicht unmaskiert.

### 7.3 Pfade und statische Dateien

- `/oeffentlich/…` liefert nur Dateien aus dem dafür vorgesehenen
  Paketverzeichnis. `..`, kodierte Varianten (`%2e%2e`, `%2f`, `%5c`),
  absolute Pfade und Nullbytes → 404 (oder 400), nie eine Datei außerhalb.
- Ein Nullbyte (`\u0000`) in einem JSON-Text wird entweder unverändert
  gespeichert und zurückgegeben oder mit 422 abgelehnt, nie 5xx.

### 7.4 Robustheit

Keine Eingabe führt zu 5xx, insbesondere nicht: tief verschachteltes JSON
(z. B. 100 000 Ebenen `[`) → 422 `validierung` (oder 413), nicht
parsebarer Körper → 422, falscher `Content-Type` → 422,
übergroße Ganzzahlen → 422, ungültiges UTF-8 → 422. Fehlermeldungen
enthalten keinen Stacktrace, keine Pfade des Servers und keine SQL-Texte.

## 8. Größengrenzen (immer)

| Grenze | Gilt für | Vorgabe | Antwort |
| --- | --- | --- | --- |
| `upload_max_mib` | Körper von `POST /api/import/kmymoney`, `POST /api/import/gnucash`, `POST /api/sicherung/einspielen`, ab M18 `POST /api/dokumente` (`dokumente.md` 2.1), ab M19 `POST /api/import/alfbanco` (`alfbanco.md` 2) | 200 MiB | 413 `datei_zu_gross` |
| `anfrage_max_kib` | Körper jeder anderen Anfrage | 4 096 KiB | 413 `anfrage_zu_gross` |

- Gemessen werden die Bytes des Anfragekörpers (wie übertragen, ohne
  Dekodierung); Grenze einschließlich (genau `upload_max_mib · 1 048 576`
  Bytes sind erlaubt, ein Byte mehr nicht).
- Ein `Content-Length` über der Grenze wird abgelehnt, ohne den Körper zu
  lesen; ohne `Content-Length` (chunked) wird beim Lesen gezählt und beim
  Überschreiten abgebrochen.
- Abgelehnte Anfragen haben keine Wirkung (kein Teilimport, keine
  Änderung, kein Importvorgang). `details = {"grenze_bytes": <int>}`.
- Bei eingeschalteter Anmeldung wird ohne gültige Sitzung 401 geliefert
  (3.2), bevor die Größe geprüft wird.
- Die Grenze für entpackte Sicherungen (`sicherung.md` 8) bleibt davon
  unberührt.

## 9. Keine Geheimnisse in Logs, Fehlermeldungen und Antworten

Zusätzlich zu `geheimnisse.md` 6 und `synchronisation.md` 12 (PIN, TAN):

- Passwort (richtig oder falsch), Sitzungstoken, CSRF-Token und
  Einrichtungscode erscheinen in **keiner** Logausgabe (jeder Logger, jede
  Stufe einschließlich `DEBUG`, stdout/stderr, auch Zugriffsprotokolle des
  ASGI-Servers), keiner Fehlermeldung, keinem `details`, keiner
  Benachrichtigung, keiner Sicherung und keinem `repr()`.
- Ausnahmen: das CSRF-Token im Körper von `AnmeldeStatus` für die eigene
  Sitzung, das Sitzungstoken im `Set-Cookie` der Anmeldung/Einrichtung, der
  Einrichtungscode in seiner Datei.
- 422-Antworten wiederholen nie die Werte der Felder `passwort`,
  `altes_passwort`, `neues_passwort`, `einrichtungscode` (auch nicht als
  `input`); dasselbe gilt seit M2 für `pin` und `tan`.
- Köpfe `Cookie`, `Set-Cookie`, `Authorization` und `X-Kontor-CSRF` werden
  nicht protokolliert.
- Passwort-Hash und Sitzungsdaten stehen in keiner Antwort und keiner
  Sicherung.

## 10. Netzbeschränkung (Heimnetz, K 2)

- `erlaubte_netze`: Liste von Netzen in CIDR-Schreibweise (IPv4/IPv6),
  Vorgabe None = keine Beschränkung. Gesetzt: Anfragen, deren
  Client-Adresse (ASGI `scope["client"][0]`) keine IP-Adresse in einem der
  Netze ist (auch nicht als IP lesbare Adressen), → **403**
  `netz_nicht_erlaubt` (unter `/api/` als `Fehler`, sonst Text), als
  allererste Prüfung, auch für öffentliche Pfade. IPv4-gemappte
  IPv6-Adressen (`::ffff:192.168.1.5`) gelten als IPv4.
- Weitergeleitete Köpfe (`X-Forwarded-For`, `Forwarded`) werden nicht
  ausgewertet (`betrieb.md` 2: der Server läuft ohne Proxy-Köpfe).
- Die ausgelieferte Umgebungsdatei setzt die privaten Netze
  (`betrieb.md` 3).

## 11. Fehlercodes (neu in M7)

| Code | Status | Bedeutung |
| --- | --- | --- |
| `nicht_angemeldet` | 401 | keine gültige Sitzung |
| `anmeldung_fehlgeschlagen` | 401 (Anmeldung), 403 (Passwort ändern) | Passwort falsch |
| `anmeldung_gesperrt` | 429 | Sperre nach Fehlversuchen |
| `anmeldung_abgeschaltet` | 409 | Anmeldung nicht eingeschaltet |
| `nicht_eingerichtet` | 409 | noch kein Passwort |
| `bereits_eingerichtet` | 409 | Einrichtung schon erfolgt |
| `einrichtungscode_ungueltig` | 403 | falscher Einrichtungscode |
| `csrf_ungueltig` | 403 | CSRF-Token oder Herkunft ungültig |
| `netz_nicht_erlaubt` | 403 | Client-Adresse außerhalb `erlaubte_netze` |
| `datei_zu_gross` | 413 | Upload über `upload_max_mib` |
| `anfrage_zu_gross` | 413 | Körper über `anfrage_max_kib` |

Die Statuscodes 401, 403, 413 und 429 mit diesen Codes sind für **jede**
Operation zulässig (`openapi.yaml`, `x-allgemeine-antworten`, E-127); welche
im Einzelfall auftreten, legt dieses Dokument fest.

## 12. Nicht in M7

- Mehrere Benutzer, Rollen, Zwei-Faktor-Anmeldung, Passwort-Zurücksetzen
  per Mail (K 16: ein Haushaltskonto; Notfallweg 5.1).
- TLS im Anwendungsserver; wer HTTPS will, setzt einen Reverse-Proxy auf
  demselben Host davor und `sitzung_cookie_secure = True` (`betrieb.md` 2).
- Schutz vor CSV-Formelinjektion im Export: der CSV-Export bleibt
  verlustfrei (`berichte.md` 4, E-130).
