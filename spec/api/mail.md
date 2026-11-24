# Mail-Anbindung: IMAP mit OAuth2 (XOAUTH2), zwei Postfächer – Meilenstein 6

Verbindlich für Implementierung und Tests. Umsetzung von K 13 (zwei
Gmail-Postfächer über IMAP, ausschließlich OAuth2/XOAUTH2, nur lesend, keine
Passwörter, Ablauf der Refresh-Tokens nach sieben Tagen im Testmodus) und
T 16 (OAuth2 gegen eine Attrappe: holen, erneuern, Ablauf und Widerruf führen
zu Benachrichtigung statt Absturz; keine Passwörter; Tokens nur
verschlüsselt; nachweislich nur lesend; zwei Postfächer getrennt und
parallel). Der Abgleich von Sammelbuchungen mit Mails ist **nicht** Teil von
M6 (K 1, `meilensteine.md`); M6 holt Bestell- und Zahlungsmails ab und hält
sie für den späteren Abgleich bereit. Ergänzt `plugins.md` (9),
`python-api.md` (13), `protokoll.md` (12), `sicherung.md` (2.6),
`openapi.yaml` (Tag `mail`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

**Ab M23 (E-228):** Ein Postfach kann statt OAuth2 ein App-Passwort haben; dann
meldet sich das IMAP-Plugin mit `LOGIN` an (`geheimnisschutz.md` 6). Die Regeln
„ausschließlich OAuth2/XOAUTH2, nie `LOGIN`“ dieses Dokuments gelten für Postfächer
ohne App-Passwort unverändert; „nur lesend“ gilt für alle.

## 1. Überblick

- **Postfächer** (2) sind protokollierte Objekte des Buchbestands: Adresse,
  Bezeichnung, Ordner, Absenderfilter, aktiv. Sie gehören zur Sicherung.
- **Anmeldung** (4): OAuth2 Authorization Code mit PKCE gegen Google; Tokens
  liegen nur verschlüsselt im Geheimnisspeicher (`geheimnisse.md`).
- **Abruf** (6): Das Mail-Plugin holt je Postfach die Nachrichten seit dem
  letzten Abruf; die App spiegelt sie (Betriebszustand, nicht gesichert).
  Postfächer werden getrennt und parallel verarbeitet.
- **Token-Ablauf** (5): Erkennung, Vorwarnung, Benachrichtigung und
  erneute Anmeldung.

## 2. Postfach

### 2.1 Objekt `Postfach`

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | fortlaufend |
| `adresse` | str | E-Mail-Adresse: 3–254 Zeichen, genau ein `@` mit nicht leeren Teilen, ohne Leerraum; eindeutig nach `casefold()`; **unveränderlich** |
| `bezeichnung` | str | 0–200 Zeichen, Vorgabe `""` |
| `ordner` | str | IMAP-Ordner, 1–200 Zeichen, Vorgabe `"INBOX"` (Gmail z. B. `"[Gmail]/Alle Nachrichten"`) |
| `absender_filter` | Liste str | 0–50 Einträge, je 1–200 Zeichen, ohne Doppelte; leer = alle Nachrichten |
| `aktiv` | bool | Vorgabe true; inaktive werden nicht abgerufen |

### 2.2 REST

| Methode, Pfad | Zweck |
| --- | --- |
| `GET /api/mail/postfaecher` | Liste nach `id` |
| `POST /api/mail/postfaecher` | `PostfachNeu {adresse, bezeichnung?, ordner?, absender_filter?, aktiv?}` → 201 `Postfach`; 409 `postfach_existiert`; 422 `validierung` |
| `GET /api/mail/postfaecher/{id}` | 200 `Postfach`; 404 |
| `PATCH /api/mail/postfaecher/{id}` | `PostfachAenderung {bezeichnung?, ordner?, absender_filter?, aktiv?}` (kein `adresse`) → 200; 404; 422 |
| `DELETE /api/mail/postfaecher/{id}` | 204; entfernt auch Anmeldung (ohne Widerruf beim Anbieter), gespiegelte Nachrichten und Betriebszustand des Postfachs; 404 |
| `GET /api/mail/postfaecher/{id}/status` | 200 `PostfachStatus` (2.3); 404 |

Postfächer sind im Mock- und Echtmodus gleich verwaltbar. Protokoll:
`postfach_anlegen`, `postfach_aendern`, `postfach_loeschen` (`protokoll.md`
12); Operationen ohne Wirkung erzeugen keine Änderung.

### 2.3 `PostfachStatus` (Betriebszustand)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `postfach_id` | int | |
| `anmeldung` | `"nicht_erforderlich"` \| `"fehlt"` \| `"angemeldet"` \| `"abgelaufen"` \| `"widerrufen"` | Mock-Modus immer `nicht_erforderlich`; sonst nach 4 und 5 |
| `anmeldung_nr` | int | Anzahl erfolgreicher Anmeldungen dieses Postfachs (anfangs 0) |
| `angemeldet_am` | date-time \| null | Zeitpunkt der letzten erfolgreichen Anmeldung |
| `laeuft_ab_am` | date-time \| null | Ablauf des Refresh-Tokens (5.2) bei `angemeldet`, sonst null |
| `letzter_abruf_am` | date-time \| null | Beginn des letzten Abrufs dieses Postfachs |
| `letzter_erfolg_am` | date-time \| null | Beginn des letzten erfolgreichen Abrufs |
| `letzter_fehler` | `{code, meldung}` \| null | Fehler des letzten Abrufs, sonst null |
| `nachrichten` | int | Anzahl gespiegelter Nachrichten |

Der Betriebszustand ist kein Buchbestand: nicht protokolliert, nicht
gesichert. Er hängt an der `adresse` (`casefold`), nicht an der `id`.

## 3. IMAP-Plugin `kontor.plugins.imap`

```python
@dataclass(frozen=True)
class ImapPostfach:
    adresse: str
    ordner: str = "INBOX"

class ImapMailPlugin(MailPlugin):
    name = "imap"; ist_mock = False
    def __init__(self, config: KontorConfig, *, postfaecher: Sequence[ImapPostfach] = (),
                 zugang: Callable[[str, bool], str] | None = None) -> None: ...
```

- `erzeuge_mail_plugin(config, *, postfaecher=(), zugang=None)` liefert bei
  `mail_plugin = "imap"` diese Klasse (Mock-Modus: `MockMailPlugin`, die
  neuen Schlüsselwortargumente werden ignoriert). Das Erzeugen baut keine
  Verbindung auf und ruft `zugang` nicht auf.
- `zugang(adresse, erneuern)` liefert ein OAuth2-Access-Token für das
  Postfach; `erneuern=True` verlangt ein frisch erneuertes Token. Es darf
  `MailFehler`-Unterklassen werfen (5.1); das Plugin reicht sie unverändert
  durch.
- Öffentliche Methoden genau `postfaecher`, `nachrichten`, `schliessen`.
  `nachrichten` darf für verschiedene Postfächer gleichzeitig aus mehreren
  Threads aufgerufen werden.

### 3.1 `postfaecher()` und Prüfreihenfolge von `nachrichten(postfach, seit)`

`postfaecher()` → die Adressen in der übergebenen Reihenfolge, ohne
Verbindung. `nachrichten`:

1. `seit` ohne Zeitzone → `ValueError`.
2. Postfach (Vergleich nach `casefold()`) nicht unter `postfaecher` →
   `PostfachUnbekannt`.
3. `zugang` None → `PluginNichtVerfuegbar` (ohne Verbindung; E-017 bleibt
   für unkonfigurierte Instanzen gültig).
4. `token = zugang(adresse, False)`.
5. Verbindung nach 3.2, Abbildung nach 3.3.

### 3.2 IMAP-Ablauf (RFC 3501, RFC 7628/Google XOAUTH2)

1. Verbindung zu `imap_host:imap_port`, mit `imap_tls` als TLS von Anfang an
   (IMAPS; `geheimnisse.md` 7), Zeitgrenze `imap_timeout_sekunden` für
   Aufbau und jede Antwort. Fehler, Abbruch oder Zeitüberschreitung →
   `MailVerbindungsFehler`.
2. Die Fähigkeiten müssen `AUTH=XOAUTH2` enthalten, sonst `MailFehler`.
3. `AUTHENTICATE XOAUTH2` mit der Base64-Kodierung von
   `"user=" + adresse + "\x01auth=Bearer " + token + "\x01\x01"` (als
   Anfangsantwort oder nach der Fortsetzungsanforderung `+`). Lehnt der
   Server ab (auf eine Fortsetzungsanforderung mit Fehlerbeschreibung
   antwortet der Client mit einer leeren Zeile; danach `NO`), holt das
   Plugin `zugang(adresse, True)` und versucht es genau einmal erneut; eine
   zweite Ablehnung → `MailAnmeldungAbgelehnt`. `LOGIN` und jede andere
   Anmeldung mit Passwort werden **nie** verwendet.
4. `EXAMINE` des Ordners (Name nach RFC 3501 5.1.3, modifiziertes UTF-7,
   z. B. `Bestellungen/Bücher` → `Bestellungen/B&APw-cher`); `NO` →
   `MailOrdnerUnbekannt`. `UIDVALIDITY` aus der Antwort wird gemerkt.
5. `UID SEARCH SINCE <TT-Mon-JJJJ>` mit dem UTC-Datum von `seit`
   (englische Monatskürzel).
6. `UID FETCH <UIDs> (UID INTERNALDATE BODY.PEEK[])` (in beliebig großen
   Teilmengen).
7. `LOGOUT`.

**Nur lesend (K 13, T 16):** Das Plugin sendet nur `CAPABILITY`, `ID`,
`NOOP`, `AUTHENTICATE`, `EXAMINE`, `LIST`, `STATUS`, `SEARCH`/`UID SEARCH`,
`FETCH`/`UID FETCH` (Datenelemente nur `UID`, `INTERNALDATE`, `FLAGS`,
`RFC822.SIZE`, `BODY.PEEK[…]`), `CLOSE`, `UNSELECT`, `LOGOUT`. Nie `SELECT`,
`STORE`, `COPY`, `MOVE`, `EXPUNGE`, `APPEND`, `CREATE`, `DELETE`, `RENAME`,
`SUBSCRIBE`, `UNSUBSCRIBE`, `LOGIN`, `BODY[…]` ohne `PEEK`, `RFC822`. Damit
ändert der Abruf weder Inhalt noch Markierungen (auch nicht `\Seen`), obwohl
Gmail für IMAP den vollen Scope `https://mail.google.com/` verlangt (E-117).

### 3.3 Abbildung auf `MailNachricht`

Je Nachricht (MIME nach RFC 5322/2045 ff.):

| Feld | Quelle |
| --- | --- |
| `nachricht_id` | Kopf `Message-ID` nach `strip()` (mit spitzen Klammern); fehlt/leer → `"imap:" + UIDVALIDITY + ":" + UID` |
| `postfach` | `ImapPostfach.adresse` wie übergeben |
| `empfangen` | `INTERNALDATE` in UTC |
| `absender` | Adressteil (addr-spec) des Kopfes `From` nach `email.utils.parseaddr`, unverändert; fehlt → `""` |
| `betreff` | Kopf `Subject` nach RFC 2047 dekodiert, Zeilenfaltung entfernt; fehlt → `""` |
| `text` | erster Teil (Reihenfolge von `Message.walk()`) mit Typ `text/plain`, der kein Anhang ist (`Content-Disposition: attachment`): Inhalt nach Transfer-Kodierung und `charset` dekodiert (unbekannt → UTF-8 mit Ersetzung), `\r\n` → `\n`. Gibt es keinen, der erste solche `text/html`-Teil nach der HTML-Regel. Sonst `""`. |

**HTML-Regel:** `t = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", html)`;
`t = re.sub(r"(?s)<[^>]*>", " ", t)`; `t = html.unescape(t)`;
`text = " ".join(t.split())`.

Ergebnis: Unter den von `UID SEARCH` gelieferten Nachrichten bleibt bei
gleicher `nachricht_id` nur die mit der kleinsten UID (zuerst); davon die mit
`empfangen ≥ seit`; sortiert nach (`empfangen`, `nachricht_id`)
(`plugins.md` 2, E-123).

### 3.4 Fehler

| Ereignis | Ausnahme |
| --- | --- |
| Verbindung, TLS, Zeitüberschreitung, Abbruch, unerwartete Antwort | `MailVerbindungsFehler` |
| `AUTH=XOAUTH2` fehlt | `MailFehler` |
| zweimal abgelehnte Anmeldung | `MailAnmeldungAbgelehnt` (neu, `mail_anmeldung_abgelehnt`) |
| Ordner unbekannt | `MailOrdnerUnbekannt` (neu, `mail_ordner_unbekannt`) |
| Fehler aus `zugang` | unverändert (z. B. `MailTokenAbgelaufen`) |

Meldungen und `details` enthalten nie Tokens.

## 4. OAuth2-Anmeldung (Echtmodus)

### 4.1 Konfiguration und Client

- `oauth_client_id` (Konfiguration, kein Geheimnis) und das Geheimnis
  `oauth_client_secret` (`geheimnisse.md` 4) des eigenen Google-Cloud-Projekts
  (Client-Typ „Desktop-App“, K 13). Fehlt eines (oder ist das Secret nicht
  lesbar) → Anmeldung nicht möglich: 409 `oauth_client_fehlt`.
- Endpunkte (Naht für die Attrappe): `oauth_autorisierung_url` (Vorgabe
  `https://accounts.google.com/o/oauth2/v2/auth`), `oauth_token_url`
  (`https://oauth2.googleapis.com/token`), `oauth_widerruf_url`
  (`https://oauth2.googleapis.com/revoke`), `oauth_redirect_uri` (Vorgabe
  `http://127.0.0.1/oauth2/rueckruf`, Loopback-Umleitung für
  Desktop-Clients).
- Scope fest: `https://mail.google.com/` (nur damit erlaubt Gmail IMAP;
  E-117).

### 4.2 Anmeldung starten

`POST /api/mail/postfaecher/{id}/anmeldung` (ohne Körper):

1. 404 unbekanntes Postfach; Mock-Modus → 409 `nur_echtmodus`; 409
   `oauth_client_fehlt` (4.1).
2. Die App erzeugt `state` (zufällig, mindestens 128 Bit, URL-sicher, ≥ 22
   Zeichen) und `code_verifier` (43–128 Zeichen aus `A–Z a–z 0–9 - . _ ~`,
   RFC 7636) und merkt beide **nur im Arbeitsspeicher**, gültig 10 Minuten.
   Eine frühere offene Anmeldung desselben Postfachs verfällt.
3. Antwort 200 `{autorisierung_url, gueltig_bis}`: `oauth_autorisierung_url`
   mit den Abfrageparametern `response_type=code`, `client_id`,
   `redirect_uri` (= `oauth_redirect_uri`), `scope`, `state`,
   `code_challenge` (= BASE64URL ohne Auffüllung von SHA-256 des
   `code_verifier`), `code_challenge_method=S256`, `access_type=offline`,
   `prompt=consent` (damit Google stets einen Refresh-Token liefert),
   `login_hint` (= Adresse).

Der Anwender öffnet die URL im Browser, meldet sich bei Google an und wird
auf `oauth_redirect_uri?state=…&code=…` umgeleitet. Läuft der Browser nicht
auf dem Server, schlägt das Laden dieser Adresse fehl; der Anwender kopiert
sie aus der Adresszeile in die Oberfläche (4.3).

### 4.3 Anmeldung abschließen

Zwei gleichwertige Wege:

- `POST /api/mail/anmeldung/abschluss` mit `{"antwort_url": "<URL>"}` → 200
  `PostfachStatus`;
- `GET /oauth2/rueckruf?state=…&code=…` (außerhalb von `/api/`, für einen
  Browser auf dem Server oder über einen Tunnel) → 200 `text/html` bei
  Erfolg, 400 `text/html` bei Fehler; Inhalt frei, ohne Geheimnisse.

Ablauf (Abfrageparameter der URL bzw. der Anfrage):

1. Körper ungültig → 422 `validierung`. `state` fehlt, ist unbekannt oder
   abgelaufen → 422 `oauth_zustand_ungueltig`.
2. Die offene Anmeldung wird verbraucht (jeder `state` gilt höchstens
   einmal). Parameter `error` (z. B. `access_denied`) → 422 `oauth_abgelehnt`;
   `code` fehlt → 422 `oauth_zustand_ungueltig`.
3. Tokenaustausch: `POST oauth_token_url` mit
   `application/x-www-form-urlencoded`: `grant_type=authorization_code`,
   `code`, `redirect_uri`, `client_id`, `client_secret`, `code_verifier`.
   Fehlerantwort (Status ≠ 200), Verbindungsfehler, Zeitüberschreitung
   (`oauth_timeout_sekunden`) → 409 `oauth_fehler` (`details.error` = Feld
   `error` der Antwort, falls vorhanden).
4. Antwort 200 (JSON): `scope` (durch Leerzeichen getrennt) muss
   `https://mail.google.com/` enthalten, sonst 422 `oauth_scope_fehlt`;
   fehlt `refresh_token` → 422 `oauth_kein_refresh_token`. Sonst speichert
   die App verschlüsselt (`mail_token:<adresse>`): Refresh-Token,
   Access-Token, Ablauf des Access-Tokens (jetzt + `expires_in`), Zeitpunkt
   der Ausstellung und Ablauf des Refresh-Tokens (5.2). `anmeldung_nr` + 1,
   `anmeldung = "angemeldet"`, `angemeldet_am` = jetzt. Ungelesene
   Benachrichtigungen mit den Schlüsselpräfixen
   `mail_token_laeuft_ab:<id>:`, `mail_token_abgelaufen:<id>:`,
   `mail_token_widerrufen:<id>:` und `mail_fehler:<id>:` werden gelesen.

Codes, Tokens, `state` und `code_verifier` erscheinen nie in Antworten,
Logs oder Fehlermeldungen. Eine Anmeldung ist keine Änderung des
Buchbestands (kein Protokolleintrag).

### 4.4 Abmelden

`DELETE /api/mail/postfaecher/{id}/anmeldung` → 204 (auch ohne Anmeldung):
Ist ein Refresh-Token gespeichert, sendet die App `POST oauth_widerruf_url`
mit `token=<refresh_token>` (Fehler werden ignoriert) und löscht das
Geheimnis; `anmeldung = "fehlt"`. Mock-Modus → 409 `nur_echtmodus`.

## 5. Tokens im Betrieb

### 5.1 Zugang für das Plugin

Die App übergibt dem IMAP-Plugin ein `zugang(adresse, erneuern)`:

1. Status `fehlt` → `MailAnmeldungFehlt` (neu, `mail_anmeldung_fehlt`);
   `abgelaufen` → `MailTokenAbgelaufen`; `widerrufen` → `MailTokenWiderrufen`
   (neu, `mail_token_widerrufen`). Keine Verbindung.
2. Ablaufprüfung nach 5.3 (proaktiv).
3. Access-Token vorhanden, `jetzt < Ablauf − 60 s` und nicht `erneuern` →
   zurückgeben.
4. Erneuern: `POST oauth_token_url` (Formular) mit
   `grant_type=refresh_token`, `refresh_token`, `client_id`,
   `client_secret`. Antwort 200 → neues Access-Token mit Ablauf jetzt +
   `expires_in` speichern; enthält sie `refresh_token`, ersetzt er den alten
   (Ausstellung = jetzt, Ablauf neu nach 5.2; `anmeldung_nr` bleibt).
5. Antwort mit `error = "invalid_grant"` (der Anbieter lehnt den
   Refresh-Token ab: abgelaufen oder widerrufen, Google: „Token has been
   expired or revoked.“): Ist ein Ablauf (5.2) bekannt und jetzt ≥ Ablauf −
   1 Stunde → **abgelaufen**, sonst **widerrufen**. Die App löscht die
   Tokens, setzt den Status, erzeugt die Benachrichtigung (5.3) und wirft
   `MailTokenAbgelaufen` bzw. `MailTokenWiderrufen`.
6. Jede andere Fehlerantwort, Verbindungsfehler, Zeitüberschreitung, fehlendes
   oder unlesbares Client-Secret → `MailOAuthFehler` (neu,
   `mail_oauth_fehler`); der Status bleibt.

### 5.2 Ablauf des Refresh-Tokens (K 13: sieben Tage im Testmodus)

Ablauf = Ausstellung + `refresh_token_expires_in` Sekunden, wenn die
Tokenantwort dieses Feld enthält (Google liefert es für zeitlich begrenzte
Zugriffe); sonst Ausstellung + `oauth_refresh_gueltig_stunden` Stunden
(Vorgabe 168 = sieben Tage, wie im Testmodus eines Google-Cloud-Projekts);
bei `oauth_refresh_gueltig_stunden = 0` (Projekt veröffentlicht) ohne
Ablauf. `laeuft_ab_am` (2.3) zeigt ihn an.

### 5.3 Erkennung, Vorwarnung, Benachrichtigung, erneute Anmeldung

Geprüft wird bei jedem Planer-Takt (`synchronisation.md` 18.2 Schritt 3),
vor jedem Abruf eines Postfachs und in `zugang`, für jedes Postfach mit
`anmeldung = "angemeldet"` und bekanntem Ablauf `A`:

- `jetzt ≥ A` → **abgelaufen** ohne Anfrage an den Anbieter (proaktiv):
  Tokens löschen, Status `abgelaufen`, Benachrichtigung
  `mail_token_abgelaufen`.
- sonst `jetzt ≥ A − oauth_vorwarnung_stunden` (Vorgabe 24) →
  Benachrichtigung `mail_token_laeuft_ab` („Mail-Anmeldung läuft bald ab“,
  mit Link zur Anmeldung).

Schlüssel `<art>:<postfach_id>:<anmeldung_nr>` (`benachrichtigungen.md` 6);
eine Benachrichtigung entsteht nur, wenn es noch **keine** mit diesem
Schlüssel gibt (gelesen oder nicht, wie E-100): je Anmeldung höchstens eine
Vorwarnung und höchstens eine Meldung über Ablauf bzw. Widerruf. Die
Benachrichtigungen werden per ntfy zugestellt (Priorität 4 bzw. 3).

Erneute Anmeldung: wie 4.2/4.3; danach beginnt mit neuer `anmeldung_nr` ein
neuer Zyklus. Abrufe eines Postfachs mit Status `fehlt`, `abgelaufen` oder
`widerrufen` bauen keine Verbindung auf und haben im Abrufergebnis den
Status `anmeldung_erforderlich`; sie erzeugen keine weitere Benachrichtigung.
Das andere Postfach ist davon unberührt.

## 6. Abruf

### 6.1 REST

`POST /api/mail/abruf` (ohne Körper) → 200 `MailAbruf`; läuft bereits ein
Abruf → 409 `mail_abruf_laeuft`. Jeder Abruf erfasst alle aktiven
Postfächer.

`MailAbruf = {gestartet_am, beendet_am, postfaecher}`, `postfaecher` nach
`postfach_id` aufsteigend, je Eintrag `MailAbrufPostfach`:

| Feld | Regeln |
| --- | --- |
| `postfach_id`, `adresse` | |
| `status` | `erfolgreich` \| `fehlgeschlagen` \| `anmeldung_erforderlich` |
| `seit` | date-time, abgefragter Beginn (6.2) |
| `nachrichten_gesamt` | vom Plugin gelieferte Nachrichten |
| `nachrichten_neu` | neu gespiegelt |
| `nachrichten_vorhanden` | bereits gespiegelt (gleiche `nachricht_id` im Postfach) |
| `nachrichten_gefiltert` | vom Absenderfilter ausgeschlossen |
| `fehler` | `{code, meldung}` \| null |

Bei `erfolgreich` gilt `nachrichten_gesamt = nachrichten_neu +
nachrichten_vorhanden + nachrichten_gefiltert`; sonst sind alle Zählungen 0.

`GET /api/mail/nachrichten` (Filter `postfach_id`, Paginierung `seite`,
`pro_seite` wie die Buchungsliste) → `{eintraege, gesamt, seite,
pro_seite}`, Einträge `MailNachrichtEintrag {id, postfach_id, nachricht_id,
empfangen, absender, betreff, text}` nach (`empfangen`, `postfach_id`,
`nachricht_id`) aufsteigend. Ab M27 zusätzlich `reihenfolge`, `zuordnung`, `postfach`, `zuordnung` je Eintrag und
`stand` (6.6).

### 6.2 Ablauf je Postfach

1. Status `fehlt`/`abgelaufen`/`widerrufen` (nur Echtmodus, nach der
   Prüfung 5.3) → `anmeldung_erforderlich`.
2. `seit` = `letzter_erfolg_am − mail_ueberlappung_stunden`, ohne früheren
   Erfolg `jetzt − mail_erstabruf_tage` Tage. `letzter_abruf_am` = jetzt.
3. `plugin.nachrichten(adresse, seit)` (Mock-Modus: vorher `setze_heute`
   mit dem Datum der App-Uhr).
4. Je Nachricht in Lieferreihenfolge: gleiche `nachricht_id` schon
   gespiegelt → `vorhanden`; sonst Absenderfilter: nicht leer und kein
   Eintrag ist (nach `casefold()`) Teilzeichenkette von `absender` →
   `gefiltert`; sonst spiegeln → `neu`.
5. Erfolg → `letzter_erfolg_am` = Beginn (2), `letzter_fehler` = null.
   Fehler → `fehlgeschlagen`, `letzter_fehler`, nichts gespiegelt; Folgen in
   6.3.

**Getrennt und parallel:** Die Postfächer werden gleichzeitig verarbeitet
(je Postfach eine eigene Verbindung, z. B. je ein Thread); ein Fehler,
Zeitüberschreitung oder Ablauf in einem Postfach beeinflusst das andere
nicht. Die Spiegelung je Postfach ist atomar.

### 6.3 Fehler und Benachrichtigungen

| Fehler | Folge |
| --- | --- |
| `MailTokenAbgelaufen`, `MailTokenWiderrufen` aus `zugang` (Echtmodus) | Status nach 5.1, Benachrichtigung schon dort |
| `MailTokenAbgelaufen` des Mock-Plugins (Szenario `token_ablauf`) | Benachrichtigung `mail_token_abgelaufen` mit `anmeldung_nr = 0` (einmal) |
| jeder andere Fehler | Benachrichtigung `mail_fehler`, Schlüssel `mail_fehler:<postfach_id>:<code>`, nur wenn keine **ungelesene** mit diesem Schlüssel existiert (wie `sync_fehler`) |

Ein Pluginfehler führt nie zu einer 5xx-Antwort.

### 6.4 Planer

`mail_intervall_minuten` (Vorgabe 0 = kein automatischer Abruf). Ist es
> 0, startet der Planer-Takt (`synchronisation.md` 18.2 Schritt 5) einen
Abruf, wenn noch kein Postfach einen `letzter_abruf_am` hat oder der jüngste
`letzter_abruf_am` aller Postfächer + Intervall ≤ jetzt ist.

### 6.5 Spiegel

Gespiegelte Nachrichten sind Betriebszustand (E-118): Sie lassen sich aus
dem Postfach erneut abrufen, werden weder protokolliert noch gesichert und
entfallen mit ihrem Postfach. Beim Einspielen einer Sicherung bleiben
Spiegel, Betriebszustand und Tokens jedes Postfachs erhalten, dessen
`adresse` (`casefold`) danach noch existiert; die übrigen entfallen.

Speicherung (D-255): Die Rohfassung einer gespiegelten Mail liegt verlustfrei komprimiert vor.
Ist die Mail als Dokument angehängt, hält der Spiegel statt einer zweiten Kopie nur einen
Verweis auf den Inhalt des Dokuments; erneutes Anhängen liefert dieselben Bytes. Die
Datenbank gibt frei gewordenen Platz an das Dateisystem zurück (`auto_vacuum`).

### 6.6 Meilenstein 27: Mail-Liste mit Stand und Zuordnung (D-147, D-153; E-249)

`GET /api/mail/nachrichten` (mail.md 6.1) bleibt im Standard **unverändert in Reihenfolge und Seitenverhalten**:
nach (`empfangen`, `postfach_id`, `nachricht_id`) aufsteigend; eine Seite hinter dem Ende liefert leere
`eintraege` und die angefragte `seite`.

Neu:

- Parameter `reihenfolge` ∈ {`aelteste` (Vorgabe), `neueste`}; `neueste` = nach `empfangen` absteigend, dann
  `postfach_id`, `nachricht_id` aufsteigend. Anderer Wert → 422.
- Parameter `zuordnung` ∈ {`zugeordnet`, `erwartet`, `keine`}; anderer Wert → 422. `gesamt` und die Seiten
  beziehen sich auf die gefilterte Menge.
- Je Eintrag zusätzlich (optional im Schema, immer geliefert):
  - `postfach`: Bezeichnung des Postfachs, leer → Adresse.
  - `zuordnung`: Liste der Erwartungen (M20), deren `mails` diese Nachricht (Postfach und `nachricht_id`)
    enthalten, in Reihenfolge der Erwartungs-ID: `{erwartung_id, grund, zustand, ueberfaellig, haendler, kennung,
    vorzeichen_betrag, buchungen}`. `ueberfaellig` = Zustand `offen` und `frist` < heutiges Datum der App-Uhr.
    `vorzeichen_betrag` = `−betrag` bei Richtung `ausgabe`, sonst `betrag`. `buchungen` = die zugeordneten
    Buchungen mit `{id, datum, betrag, konto_id, konto, empfaenger, verwendungszweck, warum}` wie in den
    Erwartungsantworten (M20), zusätzlich `warum` (Text, 5.1).
- **Art einer Nachricht:** `zugeordnet`, wenn mindestens eine ihrer Erwartungen Buchungen hat; `erwartet`, wenn
  sie Erwartungen hat, aber keine mit Buchungen; sonst `keine`.
- Antwort zusätzlich `stand` (optional im Schema, immer geliefert):
  `{gesamt, zugeordnet, erwartet, keine, postfaecher}` – Zählungen über alle Nachrichten **des
  `postfach_id`-Filters** (ohne `zuordnung`-Filter, ohne Seiten); `gesamt` = Summe der drei Arten.
  `postfaecher` = **alle** Postfächer nach `id`: `{postfach_id, adresse, bezeichnung, aktiv, nachrichten,
  letzter_abruf_am, letzter_erfolg_am, letzter_fehler}` mit denselben Werten wie der Postfachstatus (mail.md).

#### 6.6.1 `warum`

Für jede zugeordnete Buchung, in dieser Reihenfolge (erste zutreffende): Kennung, dann Referenz der Erwartung —
jeweils nur, wenn sie ohne Leerraum und klein geschrieben mindestens 6 Zeichen hat:
steht sie (ohne Leerraum, klein) im Verwendungszweck → `Die Kennung|Referenz „<Wert>“ steht im
Verwendungszweck.`; beim Empfänger → `… steht beim Empfänger.`. Sonst, wenn `|Buchungsbetrag| = betrag` der
Erwartung und Anbieter oder Händler (ab 3 Zeichen; bei Amazon auch „amzn“) klein geschrieben in Verwendungszweck
oder Empfänger vorkommt → `Der Betrag stimmt, und der Name des Händlers oder Anbieters steht in der Buchung.`
Sonst `Manuell zugeordnet. Kennung, Betrag und Name erklären die Buchung nicht von selbst.` Tests prüfen den
Wortlaut der Fälle (kern), da er die einzige Begründung ist.

Kein Protokoll, keine Sicherung (nur lesend).

## 7. Mock-Modus

Im Mock-Modus verwendet der Abruf das Mock-Mail-Plugin (`plugins.md` 3)
mit den Postfächern aus 2; Postfächer, die die Mock-Daten nicht kennen,
scheitern mit `mail_postfach_unbekannt`. Anmelden ist nicht möglich und nicht
nötig (`anmeldung = "nicht_erforderlich"`).

## 8. Attrappen für Tests

- **IMAP** (`tests/hilfen/imap_attrappe.py`): IMAP4rev1-Server auf
  `127.0.0.1`, optional mit TLS (eigenes Zertifikat, `tests/hilfen/tls.py`,
  App mit `tls_ca_datei`). Fähigkeiten `IMAP4rev1 AUTH=XOAUTH2 SASL-IR ID`;
  prüft XOAUTH2-Tokens über die OAuth-Attrappe (oder feste Tokens),
  Ablehnung wie Gmail (Fortsetzung mit Base64-JSON-Fehler, dann `NO
  [AUTHENTICATIONFAILED]`); `LOGIN`, `SELECT` und jeder schreibende Befehl →
  `NO` und Aufzeichnung als Verstoß; `BODY[]`/`RFC822` werden beantwortet,
  aber als Verstoß aufgezeichnet. Postfächer aus den Generatordaten
  (`fixtures/m6/mail/*.mbox`, INTERNALDATE aus der `From `-Zeile).
  Steuerung: Verzögerung, Abbruch nach dem Gruß, Schranke für parallele
  Sitzungen (wartet in `EXAMINE`, bis die erwartete Zahl von Sitzungen
  gleichzeitig dort ist; sonst `NO`).
- **OAuth2** (`tests/hilfen/oauth_attrappe.py`): HTTP-Server auf `127.0.0.1`
  mit `/auth` (Zustimmung im Test über `genehmige(url)`; prüft Client-ID,
  Umleitungsadresse, Scope, PKCE S256, `access_type`, `prompt`), `/token`
  (`authorization_code` mit Prüfung von Secret, Code, `code_verifier`;
  `refresh_token`; Fehler `invalid_grant`, `invalid_client` wie Google),
  `/revoke`. Steuerung: Lebensdauer der Access-Tokens, optional
  `refresh_token_expires_in`, Ablauf oder Widerruf eines Refresh-Tokens,
  Fehlerstatus, Verzögerung. Alle Tokens synthetisch (`SYNTH-…`).

## 9. Vertrag mit dem Mock-Plugin (T 21)

Der Generator liefert dieselben Nachrichten als Mock-Datendatei
(`fixtures/mock/m6_mail_vergleich.json`). `ImapMailPlugin` gegen die
IMAP-Attrappe und `MockMailPlugin` mit dieser Datei liefern für jedes
Postfach und jedes `seit` dieselben `MailNachricht`-Listen und dieselben
Ausnahmen (naives `seit`, unbekanntes Postfach).
