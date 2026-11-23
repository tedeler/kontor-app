# Schutz der Geheimnisse mit dem Login-Passwort, gemerkte Bank-PIN, Gmail mit App-Passwort – Meilenstein 23

Verbindlich für Implementierung und Tests. Übernahme der freigegebenen
Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Features `geheimnisse`
und `gmail-app-passwort`, kontor-app D-129 „Schutz der Geheimnisse mit dem
Login-Passwort“ und D-130 „Gmail ohne Google-Cloud-Projekt“, E-228). Bezug: K 6,
K 13; ergänzt bzw. ändert `geheimnisse.md` 4, `mail.md` 3–5, `sicherheit.md`
4.2/4.8/5, `betrieb.md` 4.1, `synchronisation.md` 12/18.1, `protokoll.md` 12,
`sicherung.md` 2.6, `python-api.md` 14.2, `openapi.yaml` (2.18.0) und
`oberflaeche.md` 33. Prüfmerkmale der Tests: E-229 bis E-231.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

**Vertragsänderungen gegenüber früheren Meilensteinen (E-228):** (a) K 13 und
`mail.md` 3.2 („nur XOAUTH2, nie `LOGIN`“) gelten nur noch für Postfächer **ohne**
App-Passwort; (b) `geheimnisse.md` 4 kennt zusätzlich `bank_pin` und
`mail_passwort:<adresse>`; (c) `synchronisation.md` 12 („PIN nur im
Arbeitsspeicher“) gilt nicht für die gemerkte PIN (5), die nur unter dem Schutz
verschlüsselt gespeichert wird; (d) `betrieb.md` 4.1 verlangt zusätzlich
`LimitCORE=0`. Frühere Tests bleiben unverändert gültig, weil sie weder den
Schutz einschalten noch App-Passwörter setzen (E-029).

**kern:** alle REST-, Python- und Konfigurationsprüfungen (1–7, 9). **Browsertests:**
`oberflaeche.md` 33.

Begriffe: **Schutz** = zusätzliche Verschlüsselung der Geheimnisse mit einem Schlüssel, der nur über das
Login-Passwort (`sicherheit.md` 2) zugänglich ist. **Entsperrt** = die App-Instanz kennt diesen Schlüssel im
Arbeitsspeicher. **Neustart** = eine neue App-Instanz (`create_app`) auf derselben Datenbank; jede App-Instanz hat
ihren eigenen Sperrzustand.

## 1. Opt-in, Zustände, Rückwärtskompatibilität

- Der Schutz ist **ausgeschaltet**, bis er über REST (2.2) eingeschaltet wird. Ohne Schutz verhalten sich alle
  bestehenden Meilensteine unverändert (insbesondere M6 `geheimnisse.md`, M7 `sicherheit.md`); es gibt **keine**
  neue Konfigurationsoption, keine neue Umgebungsvariable und keine Änderung der ausgelieferten Umgebungsdatei.
- Zustände (`GET /api/geheimnisse/schutz`, 2.1):
  - **aus**: `aktiv=false, entsperrt=false, gesperrt=false, geschuetzt=0, pin_gemerkt=false`.
  - **ein, entsperrt**: `aktiv=true, entsperrt=true, gesperrt=false`.
  - **ein, gesperrt**: `aktiv=true, entsperrt=false, gesperrt=true` – nach jedem Neustart und nach „Sperren“.
- Geschützt sind alle Geheimnisse außer `ntfy_token` (bleibt nur mit dem Systemschlüssel verschlüsselt, damit
  Benachrichtigungen auch gesperrt zugestellt werden). `geschuetzt` = Anzahl der gespeicherten geschützten
  Geheimnisse (alle Namen außer `ntfy_token`, einschließlich `bank_pin` und `mail_passwort:…`); bei `aktiv=false`
  immer 0.
- Gesperrt gilt:
  - geschützte Geheimnisse sind nicht lesbar: in `GET /api/geheimnisse` haben sie `lesbar=false`, `ntfy_token`
    bleibt `lesbar=true`; entsperrt wieder `true`;
  - Schreiben eines geschützten Geheimnisses → 409 `geheimnisse_gesperrt`, es wird nichts gespeichert
    (`PUT /api/geheimnisse/oauth_client_secret`, `PUT /api/sync/pin/gemerkt`, `PUT …/app-passwort`);
    `PUT /api/geheimnisse/ntfy_token` funktioniert; Löschen (`DELETE …`) funktioniert immer;
  - Mail-Abruf: `POST /api/mail/abruf` → 409 `geheimnisse_gesperrt` (auch im Mock-Modus); der Planer ruft keine
    Mails ab (kein Abruf, kein Fehlerstatus der Postfächer, `mail.md` 6.4 gilt erst nach dem Entsperren);
  - Bankabruf: eine gemerkte PIN (5) ist nicht verfügbar; ohne eingegebene PIN verhält sich die Synchronisation wie
    ohne PIN (`synchronisation.md` 12: `bank_pin_fehlt`), mit `PUT /api/sync/pin` eingegebener PIN normal.
- Klartext-Ablage: Bei eingeschaltetem Schutz steht weder ein Geheimnis noch das Login-Passwort im Klartext in den
  Datenbankdateien (`geheimnisse.md` 3 gilt weiter); der Sperrzustand und der entsperrte Schlüssel sind nie in
  Datenbank, Logs, Antworten oder Sicherung.
- Die neuen Namen erweitern `geheimnisse.md` 4 (bisher „weitere Namen gibt es nicht“):

| Name | Inhalt | Schreiben |
| --- | --- | --- |
| `bank_pin` | gemerkte Bank-PIN (5) | nur intern über `PUT /api/sync/pin/gemerkt` |
| `mail_passwort:<adresse>` | App-Passwort eines Postfachs (6); `<adresse>` nach `casefold()` | nur intern über `PUT …/app-passwort` |

  Beide erscheinen in `GET /api/geheimnisse` (ohne Wert) und sind über `PUT/DELETE /api/geheimnisse/{name}` nicht
  ansprechbar (404 `nicht_gefunden` wie `mail_token:…`). `mail_passwort:…` entfällt mit dem Postfach
  (`geheimnisse.md`, verwaiste Geheimnisse).

## 2. REST: Schutz der Geheimnisse (alle geschützt nach `sicherheit.md` 3.2, keiner öffentlich)

Alle Antworten 200 mit Schema **`GeheimnisSchutz`**:
`{"aktiv": bool, "entsperrt": bool, "gesperrt": bool, "geschuetzt": int ≥ 0, "pin_gemerkt": bool}` (alle Pflicht,
keine weiteren Felder).

### 2.1 `GET /api/geheimnisse/schutz` → 200 `GeheimnisSchutz`.

### 2.2 Endpunkte mit Login-Passwort

`POST /api/geheimnisse/schutz` (einschalten), `POST /api/geheimnisse/schutz/ausschalten`,
`POST /api/geheimnisse/entsperren`. Körper `{"passwort": "<1–4096 Zeichen>"}`.

Prüfreihenfolge (gilt auch bei abgeschalteter Anmeldung, M7 3.3; mit Anmeldung zusätzlich Sitzung, Herkunft und
CSRF wie jeder geschützte Pfad):
1. Körper ungültig (fehlt, kein Objekt, `passwort` fehlt/kein String/leer/zu lang, unbekanntes Feld) → 422
   `validierung`; der Wert erscheint nie in der Antwort.
2. Kein Login-Passwort gesetzt (nicht eingerichtet, `sicherheit.md` 5) → 409 `nicht_eingerichtet`.
3. Bremse aktiv (`sicherheit.md` 4.5) → 429 `anmeldung_gesperrt` mit `Retry-After`.
4. Passwort falsch → **403** `anmeldung_fehlgeschlagen`; zählt als Fehlversuch der Bremse (gemeinsam mit
   `POST /api/anmeldung`). Ein richtiges Passwort setzt die Fehlversuche wie ein Login zurück.
5. Endpunktspezifisch:
   - **einschalten:** Schutz schon aktiv → 409 `schutz_bereits_aktiv`. Sonst: Schutz ein, die App-Instanz ist
     danach entsperrt, alle vorhandenen geschützten Geheimnisse bleiben mit unverändertem Wert lesbar (nicht
     lesbare werden gelöscht). Antwort `GeheimnisSchutz` (`aktiv=true, entsperrt=true`).
   - **ausschalten:** Schutz nicht aktiv → 200 mit unverändertem Status. Sonst (auch im gesperrten Zustand; das
     Passwort entsperrt dafür): alle geschützten Geheimnisse bleiben mit unverändertem Wert erhalten, sind danach
     nur noch mit dem Systemschlüssel verschlüsselt und nach einem Neustart sofort lesbar; **die gemerkte PIN wird
     dabei gelöscht** (sie existiert nur unter dem Schutz, 5). Antwort mit `aktiv=false`.
   - **entsperren:** Schutz nicht aktiv → 409 `schutz_nicht_aktiv`. Öffnet das (richtige) Passwort die Hülle
     nicht → 409 `huelle_unlesbar` (nur nach Manipulation erreichbar, nicht testen). Sonst entsperrt
     (idempotent, auch wenn schon entsperrt). Antwort `GeheimnisSchutz`.

### 2.3 `POST /api/geheimnisse/sperren`
Ohne Passwort, Körper wird nicht ausgewertet. Sperrt die App-Instanz (ohne Wirkung, wenn der Schutz aus ist)
→ 200 `GeheimnisSchutz`.

### 2.4 Login und Passwort (Ergänzung zu `sicherheit.md` 4.2, 4.8, Kommandozeile)
- Ein erfolgreicher `POST /api/anmeldung` entsperrt eine gesperrte App-Instanz (Antwort unverändert).
- `PUT /api/anmeldung/passwort` mit richtigem altem Passwort: Bei aktivem Schutz bleibt er aktiv; danach öffnet nur
  noch das **neue** Passwort (Entsperren mit dem alten → 403, mit dem neuen → 200); die Werte bleiben erhalten;
  die Instanz ist danach entsperrt. Antwort unverändert (M7).
- Zurücksetzen ohne altes Passwort (`python -m kontor.anmeldung passwort-setzen`, `python-api.md`): Ist der Schutz
  aktiv, werden alle geschützten Geheimnisse gelöscht und der Schutz ist danach aus (`ntfy_token` bleibt); die
  Kommandozeile gibt die Anzahl der gelöschten Geheimnisse als Hinweis aus (ohne Namen oder Werte). Ohne Schutz
  unverändert.

## 3. Protokoll und Sicherung
- Schutz, Sperrzustand, gemerkte PIN und App-Passwörter sind **Betriebszustand**: keine Änderung im Protokoll
  (`protokoll.md` 12), kein Rückgängig.
- Nichts davon ist Teil der Sicherung (`sicherung.md` 2.6): weder Werte noch Hülle; Einspielen einer Sicherung
  ändert Schutz, Sperrzustand und Geheimnisse nicht. `anzahl` und Inhaltsprüfsumme bleiben unverändert.

## 4. Bank-PIN: Quelle (Ergänzung `synchronisation.md` 12, 18.1)
- Reihenfolge der PIN-Quelle bei `bank_pin_quelle = "eingabe"`: PIN im Arbeitsspeicher (`PUT /api/sync/pin`),
  sonst gemerkte PIN (5), sonst keine. Bei `systemd-creds` unverändert (gemerkte PIN wird nicht benutzt).
- `GET /api/sync/status`: `pin_vorhanden` ist auch dann `true`, wenn nur eine lesbare gemerkte PIN vorliegt
  (gesperrt → `false`).

## 5. Gemerkte PIN
- `PUT /api/sync/pin/gemerkt`, Körper `{"pin": "<1–128 Zeichen>"}` → 204. Prüfreihenfolge:
  `bank_pin_quelle = systemd-creds` → 409 `pin_quelle_systemd` (ohne Körperprüfung) → Körper ungültig → 422
  `validierung` (ohne Wert) → Schutz nicht aktiv → 409 `schutz_nicht_aktiv` → gesperrt → 409
  `geheimnisse_gesperrt`. Wirkung: PIN gespeichert (geschützt) **und** in den Arbeitsspeicher übernommen;
  `pin_gemerkt=true`. Nach einem Neustart: gesperrt `pin_vorhanden=false`, nach Entsperren/Login `true`, und ein
  Lauf verwendet sie ohne Eingabe.
- `DELETE /api/sync/pin/gemerkt` → 204 (idempotent, auch gesperrt): löscht die gemerkte PIN; die PIN im
  Arbeitsspeicher bleibt.
- `DELETE /api/sync/pin` (PIN verwerfen) löscht zusätzlich die gemerkte PIN.
- Meldet die Bank `BankPinFalsch` oder `BankZugangGesperrt`, wird die gemerkte PIN sofort gelöscht (kein zweiter
  Versuch mit ihr; prüfbar mit dem Mock-Bank-Plugin über `bank.pin` der Mock-Datendatei, `plugins.md` 7).
- Ausschalten des Schutzes und Zurücksetzen des Passworts löschen sie (2.2, 2.4).
- Die PIN erscheint nie in Antworten, Fehlermeldungen, Logs, Datenbankdateien im Klartext oder der Sicherung
  (`synchronisation.md` 12 gilt sinngemäß).

## 6. Postfach mit App-Passwort (Gmail ohne Google-Cloud-Projekt)

Ergänzt `mail.md` 3–5 und **ändert K 13** („ausschließlich OAuth2, keine Passwörter“): Ein Postfach kann statt
OAuth2 ein App-Passwort haben; dann meldet sich das IMAP-Plugin mit `LOGIN` an. Für Postfächer ohne App-Passwort
gilt `mail.md` 3 unverändert (nur XOAUTH2, nie `LOGIN`). Weiterhin nur lesend: nur `EXAMINE`, `BODY.PEEK[]`,
keine schreibenden Befehle, nur der konfigurierte IMAP-Server (`imap_host`, `imap_port`, `imap_tls`).

### 6.1 `PUT /api/mail/postfaecher/{id}/app-passwort`
Körper `{"passwort": "<1–256 Zeichen>"}` → 200
`{"postfach_id": int, "ordner": str, "nachrichten_im_ordner": int ≥ 0}` (Schema **`AppPasswortErgebnis`**, alle
Pflicht). Prüfreihenfolge:
1. Körper ungültig (fehlt, kein String, leer, zu lang, unbekanntes Feld) → 422 `validierung` (ohne Wert).
2. Mock-Modus → 409 `nur_echtmodus`.
3. Nach Entfernen **aller** Leerraumzeichen leer → 422 `validierung`. (Leerzeichen werden immer entfernt: Google
   zeigt das Passwort in Vierergruppen.)
4. Postfach unbekannt → 404 `nicht_gefunden`.
5. Geheimnisse gesperrt → 409 `geheimnisse_gesperrt`.
6. Verbindungstest mit genau diesem Passwort gegen den IMAP-Server: `LOGIN <adresse> <passwort>`, dann `EXAMINE`
   des Postfach-Ordners (`ordner`, modifiziertes UTF-7 wie `mail.md` 3), dann `LOGOUT`. Fehler → 422 mit dem Code
   des Mailfehlers, nichts gespeichert, Status unverändert:
   - `LOGIN` mit `NO`/`BAD` → `mail_anmeldung_abgelehnt`;
   - Server meldet `LOGINDISABLED` in den Fähigkeiten → `mail_fehler` (kein `LOGIN` gesendet);
   - `EXAMINE` nicht `OK` → `mail_ordner_unbekannt`;
   - Verbindung nicht möglich/abgebrochen, TLS-Fehler, unerwartete Antwort → `mail_verbindung`.
   Die Meldung enthält das Passwort nie.
7. Erfolg: App-Passwort gespeichert (Geheimnis `mail_passwort:<adresse>`, bei aktivem Schutz geschützt); ein
   OAuth2-Token des Postfachs (`mail_token:…`) wird gelöscht; `GET /api/mail/postfaecher/{id}/status`:
   `anmeldung = "angemeldet"`, `angemeldet_am` = jetzt, `laeuft_ab_am = null`, kein Fehler. Antwort mit
   `nachrichten_im_ordner` = Zahl aus der `EXISTS`-Antwort des `EXAMINE`. Erneutes Setzen ersetzt den Wert.

### 6.2 `DELETE /api/mail/postfaecher/{id}/app-passwort` → 204
Postfach unbekannt → 404. Hat das Postfach ein App-Passwort: löschen, `anmeldung = "fehlt"`, `laeuft_ab_am = null`.
Sonst ohne Wirkung (idempotent, auch im Mock-Modus 204).
`DELETE /api/mail/postfaecher/{id}/anmeldung` (Abmelden, `mail.md` 4) entfernt bei einem Postfach mit App-Passwort
dieses (wie 6.2) und berührt keinen Token.

### 6.3 Abruf
- Hat ein Postfach ein App-Passwort, meldet sich der Abruf (`POST /api/mail/abruf`, Planer) mit `LOGIN` an,
  sonst wie bisher mit XOAUTH2. Das App-Passwort hat Vorrang vor einem gleichzeitig vorhandenen OAuth2-Token.
- `LOGIN` abgelehnt → Postfachstatus wie `mail_anmeldung_abgelehnt` (`mail.md` 6); App-Passwort nicht lesbar
  (z. B. anderer Systemschlüssel) → `mail_anmeldung_fehlt`. Kein Ablauf und keine Erneuerung (`mail.md` 5 gilt
  nicht für App-Passwörter).
- Postfächer mit und ohne App-Passwort können parallel abgerufen werden (`mail.md` 6).

### 6.4 Plugin-Vertrag
`plugins.md` (Mail-Plugin) bleibt unverändert: gleiche öffentliche Methoden, `ImapPostfach` unverändert. Das
App-Passwort wird erst unmittelbar vor der Anmeldung gelesen; es erscheint nie in `repr()` eines Plugins oder
Postfachobjekts, nie in Logs (auch nicht im `imaplib`-Logger auf `DEBUG`), Antworten oder der Sicherung, und nie
im Klartext in den Datenbankdateien.

### 6.5 Tests gegen die IMAP-Attrappe
Die bestehende Attrappe (`mail.md` 8) beantwortet `LOGIN` mit `NO` und vermerkt es als Verstoß. Für M23 braucht
sie (test-seitig) eine Betriebsart mit App-Passwörtern je Adresse: `LOGIN` mit passendem Paar → `OK`, sonst `NO`;
optional `LOGINDISABLED` in den Fähigkeiten. Für Postfächer ohne App-Passwort bleibt `LOGIN` ein Verstoß (M6-Tests
unverändert). Geprüft wird außerdem: kein `SELECT`, kein schreibender Befehl, das Passwort nie in Logs/Antworten.

## 7. Betrieb
- systemd-Unit zusätzlich `LimitCORE=0` (`betrieb.md` 3, Tabelle der Pflichtwerte: genau `0`; bestehende Werte
  unverändert).
- `python -m kontor` verhindert Speicherabbilder des Prozesses (Core-Limit 0, auf Linux nicht „dumpable“);
  beobachtbar als `RLIMIT_CORE = (0, 0)` des Prozesses. Nicht in Tests mit eigenem Prozessstart prüfen, wenn das
  zu aufwendig ist (nur Unit-Datei als `kern`).

## 8. Oberfläche

Steht als Abschnitt 33 in `oberflaeche.md` (Browsertests, keine `kern`).

## 9. Was nicht gilt / Abgrenzung
- Kein automatisches Entsperren, keine Leerlaufsperre, keine Benachrichtigung „Bitte entsperren“.
- Kein Schutz für `ntfy_token`.
- Sicherheitsregeln aus `geheimnisse.md` 6 und `sicherheit.md` 9 gelten für Login-Passwort, PIN und App-Passwort:
  nie in Antworten, `details`, Fehlermeldungen, Logs (jede Stufe), `repr()`, Sicherung, Kommandozeilen.
- `openapi.yaml`: neue Pfade 2.1–2.3, 5, 6.1–6.2; neue Schemas `GeheimnisSchutz`, `AppPasswortErgebnis`; neue
  Fehlercodes `geheimnisse_gesperrt`, `schutz_bereits_aktiv`, `schutz_nicht_aktiv`, `huelle_unlesbar`.
  Bestehende Schemas unverändert.
- Tests in `tests/app/m23/` (Marker `m23`); Abhängigkeiten M2, M6, M7, M8.

## 10. Abweichungen von D-129/D-130 und offene Punkte
- D-129 begründet den ungeschützten `ntfy_token` mit einer Benachrichtigung „Bitte entsperren“; eine solche gibt es
  nicht (9).
- D-130 nennt `mail_verbindungsfehler`; der Code heißt `mail_verbindung` (bestehender Code aus M6).
- 2.2 „ausschalten löscht die gemerkte PIN“ ist **festgelegt**, der Code behält sie bisher (nur mit dem
  Systemschlüssel) und verwendet sie weiter, obwohl `pin_gemerkt=false` meldet – Korrektur im Anwendungscode nötig.
- Vorrang App-Passwort vor OAuth2-Token (6.3): Eine spätere erfolgreiche OAuth2-Anmeldung entfernt das
  App-Passwort nicht; das App-Passwort bleibt maßgeblich, bis es gelöscht wird.

## 11. Präzisierungen der Übernahme (E-229)

- **Zurücksetzen ohne altes Passwort (2.4)** ist jeder Weg, der das Passwort ohne
  Kenntnis des alten setzt: `kontor.anmeldung.passwort_setzen` und die Kommandozeile
  `python -m kontor.anmeldung passwort-setzen` (`python-api.md` 14.2). Beide löschen bei
  aktivem Schutz alle geschützten Geheimnisse und schalten den Schutz aus; nur die
  Kommandozeile gibt die Anzahl als Hinweis aus. Damit ist `huelle_unlesbar` (2.2) nur
  nach Manipulation erreichbar. Eine laufende App-Instanz sieht die Wirkung bei der
  nächsten Anfrage (`python-api.md` 14.2).
- **LimitCORE (7)** gilt für `kontor.service` (Tabelle `betrieb.md` 4.1, vor den
  Härtungszeilen ab `NoNewPrivileges`); `kontor-sicherung.service` bleibt unverändert.
- **Bremse (2.2 Schritt 3/4):** Fehlversuche der drei Endpunkte zählen in denselben
  Zähler wie `POST /api/anmeldung` (`sicherheit.md` 4.5); Sperrdauer, `details` und
  `Retry-After` wie dort.
