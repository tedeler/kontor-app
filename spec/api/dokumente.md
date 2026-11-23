# Dokumente an Buchungen – Meilenstein 18

Verbindlich für Implementierung und Tests. Übernahme der freigegebenen
Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature `dokumente`,
E-206). Belege (K 4, `datenmodell.md` 7, bisher „vorgesehen, später“) werden
umgesetzt: PDF-Dateien, E-Mails und Bilder hängen an Buchungen, werden im
Browser angesehen und mobil per Kamera aufgenommen. Ergänzt `datenmodell.md`
7, `protokoll.md` (Abschnitt 15), `sicherung.md` (2.7), `sicherheit.md` 8,
`openapi.yaml` (Tag `dokumente`, 2.15.0) und `oberflaeche.md` 28.
Prüfmerkmale der Tests: E-207 bis E-209.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Kennzeichnung: **[kern]** = REST, Konfiguration, Protokoll, Sicherung (Kern-Tests);
**[browser]** = Playwright-Tests wie M8 (nicht `kern`). Abschnitt 5 der
Definition steht als Abschnitt 28 in `oberflaeche.md`.

Alle Beispiele und Testdaten synthetisch (Adressen unter `example.invalid`, Inhalte
selbst erzeugt: minimale PDF-Datei beginnend mit `%PDF-`, 1×1-PNG usw.).

---

## 1. Objekt `dokument` [kern]

### 1.1 Felder (Schema `Dokument`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int ≥ 1 | vergeben beim Anlegen, nie wiederverwendet (Rückgängig stellt dieselbe ID her) |
| `dateiname` | str, 1–200 Zeichen | gesäubert nach 1.3 |
| `mime_typ` | str | einer von `application/pdf`, `image/jpeg`, `image/png`, `image/webp`, `message/rfc822`; am Inhalt erkannt (1.2) |
| `groesse` | int ≥ 1 | Länge des Inhalts in Bytes |
| `sha256` | str | SHA-256 des Inhalts, 64 Kleinbuchstaben-Hexziffern |
| `quelle` | str | `upload`, `kamera` oder `mail` |
| `erstellt_am` | str | Zeitpunkt nach App-Uhr (`synchronisation.md` 8), Format `JJJJ-MM-TTTHH:MM:SSZ` |
| `buchung_ids` | Liste int | **nur in REST-Antworten** (nicht in der Protokollform): IDs der verknüpften Buchungen, aufsteigend, nie leer |

- Ein Dokument hängt an **mindestens einer** Buchung; dasselbe Dokument kann an mehreren
  Buchungen hängen (auch kontoübergreifend). Ein Dokument ohne Buchung existiert nie:
  Wird die letzte Verknüpfung entfernt (Lösen, Löschen der Buchung, Verschieben/Löschen
  über andere Operationen), entfällt das Dokument **in derselben Änderung**.
- Gleicher Inhalt (gleiche Bytes) wird nur einmal gespeichert; zwei Uploads derselben
  Datei ergeben trotzdem zwei Dokumente (verschiedene `id`, gleiches `sha256`).
- Inhalte werden durch keine Operation gelöscht (Rückgängig braucht sie); sie sind nicht
  Teil des Protokolls.

### 1.2 Typerkennung (nur am Inhalt)

Dateiname und vom Browser angegebener Typ zählen **nicht**. Reihenfolge:

1. beginnt mit `%PDF-` → `application/pdf`
2. beginnt mit den Bytes `FF D8 FF` → `image/jpeg`
3. beginnt mit der PNG-Signatur `89 50 4E 47 0D 0A 1A 0A` → `image/png`
4. Bytes 0–3 `RIFF` und Bytes 8–11 `WEBP` → `image/webp`
5. E-Mail (`message/rfc822`), wenn alle gelten:
   - kein NUL-Byte in den ersten 64 KiB;
   - nach Entfernen führender Leerzeilen (CR/LF) und einer optionalen mbox-Trennzeile
     (`From …`) hat die erste Zeile die Form einer Kopfzeile (`Name:` mit Name aus
     druckbaren ASCII-Zeichen ohne Doppelpunkt);
   - unter den Kopfzeilen sind mindestens **zwei** verschiedene aus {From, To, Subject,
     Date, Message-ID, Received, MIME-Version, Return-Path, Delivered-To}
     (Groß-/Kleinschreibung egal), darunter mindestens eine aus {From, Subject, Date}.
6. sonst unbekannt → Fehler `dokument_typ_unbekannt` (z. B. GIF, Text, ausführbare
   Datei, eine Zeile `Hallo: Welt` ohne zweiten Mailkopf).

### 1.3 Dateiname

Aus dem übergebenen Namen (Upload: Dateiname des Formularfelds; PATCH: `dateiname`):

1. Unicode-NFC; nur der letzte Pfadteil (nach dem letzten `/` oder `\`);
2. alle Zeichen der Unicode-Kategorie „C“ (Steuer-, Format-, nicht zugewiesene Zeichen,
   z. B. NUL, Zeilenumbruch, Zero-Width-Space) entfernen; Leerraum und Punkte an Anfang
   und Ende entfernen;
3. leer → Vorgabe nach Typ: PDF „Dokument“, JPEG „Foto“, PNG/WebP „Bild“, E-Mail „E-Mail“;
4. passt die Endung nicht zum Typ (Vergleich ohne Groß-/Kleinschreibung; PDF `.pdf`,
   JPEG `.jpg` oder `.jpeg`, PNG `.png`, WebP `.webp`, E-Mail `.eml`) oder fehlt sie, wird
   die Standardendung (`.pdf`, `.jpg`, `.png`, `.webp`, `.eml`) **angehängt**
   (`foto.png` als JPEG → `foto.png.jpg`; `Scan.JPEG` bleibt);
5. länger als 200 Zeichen → auf 200 Zeichen gekürzt; endet der Name auf die
   Standardendung, bleibt sie erhalten (Beispiel: 500×`a` als PDF → 196×`a` + `.pdf`).

Beispiel: `../../etc/pass\x00wd` als PDF → `passwd.pdf`; leerer Name als JPEG → `Foto.jpg`.

**E-Mail ohne Dateinamen** (Upload ohne Namen): Name = Betreff der Mail (höchstens 196
Zeichen, sonst „E-Mail“), dann Regeln 1–5 (also mit `.eml`).

### 1.4 `belege` der Buchung (ersetzt `datenmodell.md` 7)

- `Buchung.belege` (alle Antworten mit Schema `Buchung`, auch `GET /api/buchungen`) listet
  die verknüpften Dokumente als `{id, dateiname, mime_typ, groesse}` (Schema `Beleg`),
  nach `id` aufsteigend; ohne Dokumente `[]`.
- `belege` ist abgeleitet; Ändern des Dateinamens ändert keine Buchung im Protokoll.

---

## 2. REST-Endpunkte [kern]

Alle Endpunkte sind geschützt (Anmeldung, Herkunft, CSRF nach `sicherheit.md`; nicht in
3.1). Fehlerformat wie bisher (`fehler.code`, `fehler.meldung`, `fehler.details`).
`422 validierung` für ungültige Körper/Parameter wie in `openapi.yaml` üblich.

### 2.1 `POST /api/dokumente` – Datei anhängen → 201 `Dokument`

- Query: `buchung_id` (int, **wiederholbar**, mindestens einmal) und optional
  `quelle` ∈ {`upload`, `kamera`, `mail`} (Vorgabe `upload`; die Oberfläche nutzt
  `upload` und `kamera`).
- Körper: `multipart/form-data` mit Dateifeld `datei` (Dateiname des Feldes = Vorschlag
  für `dateiname`).
- Prüfreihenfolge:
  1. Körper größer als `upload_max_mib` → **413 `datei_zu_gross`** (wie die anderen
     Uploads, `sicherheit.md` 8; der Pfad zählt zu den Upload-Pfaden);
  2. Query ungültig (`buchung_id` keine Ganzzahl, unbekannte `quelle`, unbekannter
     Parameter) → 422 `validierung`;
  3. kein multipart bzw. Feld `datei` fehlt oder ist kein Dateifeld → 422 `validierung`;
  4. kein `buchung_id` → 422 `validierung` (Ort `body.buchung_ids`);
  5. eine `buchung_id` existiert nicht → **404 `nicht_gefunden`**;
  6. Datei leer (0 Bytes) → **422 `dokument_leer`**;
  7. Typ unbekannt (1.2) → **422 `dokument_typ_unbekannt`**.
- Doppelte `buchung_id` zählen einmal. Eine Änderung `dokument_anhaengen`.

### 2.2 `POST /api/dokumente/aus-mail` – gespiegelte E-Mail anhängen → 201 `Dokument`

- Körper JSON `{nachricht_id: int, buchung_ids: [int, …]}`; `nachricht_id` ist die `id`
  einer gespiegelten Nachricht aus `GET /api/mail/nachrichten` (`mail.md`).
- Prüfreihenfolge: Körper kein Objekt oder `nachricht_id` keine Ganzzahl → 422
  `validierung`; Nachricht unbekannt → 404 `nicht_gefunden`; `buchung_ids` fehlt, leer,
  keine Liste oder nicht nur Ganzzahlen → 422 `validierung`; Buchung unbekannt → 404
  `nicht_gefunden`.
- Normale Anfragegrenze (`anfrage_max_kib`), kein Upload-Pfad.
- Ergebnis: Dokument mit `quelle = "mail"`, `mime_typ = "message/rfc822"`,
  `dateiname` = Betreff (höchstens 196 Zeichen; leer → „E-Mail“) + `.eml` nach 1.3.
- **Inhalt:**
  - Kam die Nachricht über ein echtes Postfach (IMAP, M6) und war ihre Rohfassung
    höchstens `upload_max_mib` groß, ist der Inhalt genau die abgerufene Rohnachricht
    (RFC 5322-Bytes, wie vom Server geliefert).
  - Sonst (Mock-Mail-Plugin, zu große Rohfassung) wird eine Mail aus den gespiegelten
    Feldern gebaut: `From` = Absender (fehlt er: `unbekannt@example.invalid`), `To` =
    Adresse des Postfachs, `Subject` = Betreff, `Date` = Empfangszeit, `Message-ID` =
    Nachrichten-ID, falls sie mit `<` beginnt, Textkörper = Text der Nachricht.
    Prüfbar über 2.8: `betreff` und `text` (bis auf Leerraum am Ende) entsprechen der
    gespiegelten Nachricht.
- Die Felder von `MailNachricht` (`plugins.md`) bleiben unverändert; gespiegelte
  Nachrichten bleiben Betriebszustand.
- Eine Änderung `dokument_aus_mail`.

### 2.3 `GET /api/dokumente/{id}` → 200 `Dokument`; unbekannt → 404 `nicht_gefunden`.

### 2.4 `PATCH /api/dokumente/{id}` – umbenennen → 200 `Dokument`

- Körper genau `{dateiname: str}` (andere/zusätzliche Felder → 422 `validierung`);
  `dateiname` keine Zeichenkette oder nur Leerraum → 422 `validierung`; unbekannte ID →
  404. Der neue Name wird nach 1.3 gesäubert (Typ bleibt). Änderung `dokument_umbenennen`
  (keine Änderung, wenn der gesäuberte Name gleich bleibt).

### 2.5 `DELETE /api/dokumente/{id}` → 204

Entfernt das Dokument samt allen Verknüpfungen (`belege` der Buchungen ändern sich);
unbekannt → 404. Änderung `dokument_loeschen`.

### 2.6 `POST /api/dokumente/{id}/buchungen` – verknüpfen → 200 `Dokument`

- Körper `{buchung_ids: [int, …]}` (nicht leer). Dokument unbekannt → 404; dann
  `buchung_ids` ungültig → 422 `validierung`; Buchung unbekannt → 404.
- Schon verknüpfte Buchungen werden ignoriert (sind alle schon verknüpft: keine Änderung
  im Protokoll). Änderung `dokument_verknuepfen`.

### 2.7 `DELETE /api/dokumente/{id}/buchungen/{buchung_id}` – lösen → 200

- Antwort genau `{dokument_id: int, buchung_ids: [int], geloescht: bool}`: verbleibende
  Buchungen; `geloescht = true`, wenn keine übrig blieb (das Dokument ist dann entfallen,
  `GET /api/dokumente/{id}` → 404).
- Dokument unbekannt → 404; Dokument nicht mit dieser Buchung verknüpft → 404
  `nicht_gefunden`. Änderung `dokument_loesen`.

### 2.8 `GET /api/buchungen/{id}/dokumente` → 200 `{eintraege: [Dokument]}`

Dokumente der Buchung nach `id` aufsteigend (mit `buchung_ids`); Buchung unbekannt → 404.

### 2.9 `GET /api/dokumente/{id}/inhalt` – Inhalt ausliefern

- Query `herunterladen` (`true`/`1`/`false`/`0`, sonst 422 `validierung`); unbekannt → 404.
- 200, Körper = gespeicherte Bytes; `Content-Type` = `mime_typ`, **außer** E-Mails: diese
  immer `application/octet-stream` und als Anhang (eine Mail wird nie als Seite
  ausgeliefert).
- Köpfe (2.12).

### 2.10 `GET /api/dokumente/{id}/mail` – E-Mail zerlegt → 200 `MailAnsicht`

Nur für Dokumente mit `mime_typ = message/rfc822`, sonst **409 `keine_mail`**; unbekannt →
404.

| Feld | Typ | Inhalt |
| --- | --- | --- |
| `von`, `an`, `cc` | Liste `{name: str, adresse: str}` | aus From/To/Cc (leere Einträge entfallen; `name` ggf. `""`) |
| `datum` | str (`…Z`) oder null | `Date` in UTC; ohne Zeitzone als UTC; ungültig/fehlt → null |
| `betreff` | str | dekodierter Betreff, Leerraum zu einem Leerzeichen zusammengefasst; fehlt → `""` |
| `text` | str | Textteil (`text/plain`); ohne Textteil der HTML-Teil als Text (ohne Tags, Skripte, Stile); sonst `""`; Zeilenenden `\n` |
| `html` | bool | ob die Mail einen HTML-Teil hat |
| `anhaenge` | Liste `{nr: int, dateiname: str, mime_typ: str, groesse: int, inline: bool}` | siehe unten |

- **Anhänge:** alle nicht-multipart-Teile der Mail außer dem gewählten Text- und
  HTML-Körper und außer `text/*`-Teilen ohne Dateinamen, die nicht als `attachment`
  markiert sind. `nr` = Position des Teils beim Durchlaufen aller MIME-Teile in
  Tiefensuche (Wurzel = 0). `dateiname` = Dateiname des Teils, sonst „Anhang <nr>“;
  `groesse` = dekodierte Bytes; `inline = true`, wenn der Teil eine `Content-ID` hat und
  nicht als `attachment` markiert ist (eingebettete Bilder).

### 2.11 `GET /api/dokumente/{id}/mail/html` – entschärftes HTML

- Keine Mail → 409 `keine_mail`; Mail ohne HTML-Teil → 404 `nicht_gefunden`.
- 200, `Content-Type: text/html; charset=utf-8`, Köpfe 2.12 mit der Mail-Richtlinie.
- Entschärfung (Ergebnis ist ein vollständiges HTML-Dokument mit eigenem Kopf):
  - Elemente `script`, `iframe`, `frameset`, `object`, `applet`, `svg`, `math`,
    `template`, `noscript` **samt Inhalt** entfernt (Skripttext bleibt nicht als Text
    stehen); übrige Tags `frame`, `embed`, `form`, `base`, `meta`, `link` entfernt;
  - alle Ereignis-Attribute (`on…=`) entfernt; `javascript:`, `vbscript:`,
    `data:text/html` in `href`, `src`, `action`, `formaction`, `background`,
    `xlink:href` → `#`;
  - Bilder: `cid:`-Verweise auf eingebettete Bildteile (außer SVG, je Bild höchstens
    5 MiB) werden zu `data:<typ>;base64,…`-URLs; `data:image/(png|jpeg|gif|webp)` bleibt;
    `<img>` mit jeder anderen Quelle (insbesondere `http(s)://`, `//…`) entfällt ganz;
    andere Bildattribute (`src`, `srcset`, `background`, `poster`, `lowsrc`, `dynsrc`)
    mit externen Werten werden zu `"data:,"`;
  - externe `url(…)` in Stilen (`http:`, `https:`, `//`) und `@import` → entfernt
    (`none`). Die Antwort enthält damit keine externe Adresse aus Bildern oder Stilen
    mehr (Zählpixel werden nie angefragt); Links (`<a href>`) bleiben und öffnen in einem
    neuen Fenster (`<base target="_blank">`).

### 2.12 Köpfe der Inhaltsantworten (2.9, 2.11, 2.13)

- `Content-Disposition: inline` (bzw. `attachment` bei `herunterladen=true`, bei Mails in
  2.9 und bei nicht ansehbaren Mail-Anhängen) mit `filename="<ASCII>"` (Nicht-ASCII und
  `?` → `_`, `"` → `'`) und `filename*=UTF-8''<prozentkodiert>`; in 2.11 Dateiname
  `mail.html`.
- `Cache-Control: private, no-store`.
- `X-Frame-Options: SAMEORIGIN` (statt `DENY`, nur für diese Antworten), damit die eigene
  Seite sie im Rahmen zeigen kann.
- `Content-Security-Policy` eigene, strengere Richtlinie statt der Seitenrichtlinie:
  - Inhalte (2.9, 2.13): `default-src 'none'; img-src 'self' data:; style-src
    'unsafe-inline'; frame-ancestors 'self'; sandbox`
  - Mail-HTML (2.11): `default-src 'none'; img-src data:; style-src 'unsafe-inline';
    font-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox
    allow-popups allow-popups-to-escape-sandbox` (kein `script-src`).
- Übrige Sicherheitsköpfe (`sicherheit.md`) wie bei jeder Antwort; kein interner
  Steuerkopf gelangt nach außen. Alle anderen Antworten behalten `X-Frame-Options: DENY`
  und die Seitenrichtlinie.

### 2.13 `GET /api/dokumente/{id}/mail/anhaenge/{nr}` – Anhang einer Mail

- Keine Mail → 409 `keine_mail`; `nr` kein Anhang nach 2.10 → 404 `nicht_gefunden`.
  Query `herunterladen` wie 2.9.
- Körper = dekodierte Bytes des Teils (ein eingebetteter `message/rfc822`-Teil als ganze
  Nachricht). `Content-Type`: `application/pdf`, `image/jpeg`, `image/png`, `image/webp`,
  `image/gif` unverändert, `text/plain` als `text/plain; charset=utf-8`; jeder andere Typ
  `application/octet-stream` und dann immer `attachment`. Köpfe 2.12.

### 2.14 Neue Fehlercodes

| Code | Status | Bedingung |
| --- | --- | --- |
| `dokument_leer` | 422 | hochgeladene Datei hat 0 Bytes |
| `dokument_typ_unbekannt` | 422 | Typ nach 1.2 nicht erkannt |
| `keine_mail` | 409 | Mail-Ansicht/-HTML/-Anhang für ein Dokument, das keine E-Mail ist |

### 2.15 `openapi.yaml`

Neue Pfade 2.1–2.13, Schemas `Dokument`, `DokumentGeloest` (2.7), `MailAnsicht` (2.10);
`Beleg` nicht mehr „vorgesehen“; `BuchungZustand` mit optionalem Feld `dokument_ids`
(3.1). Inhaltsantworten ohne JSON-Schema. Rückwärtskompatibel (E-029).

---

## 3. Protokoll [kern] (ergänzt `protokoll.md` 4)

### 3.1 Protokollformen

- Neues Objekt **`dokument`**: Form = `{id, dateiname, mime_typ, groesse, sha256, quelle,
  erstellt_am}` (ohne `buchung_ids`, ohne Inhalt); ableitbar aus `GET /api/dokumente/{id}`
  ohne `buchung_ids`.
- **`buchung`**: Die Verknüpfungen gehören zur Buchung. Die Form erhält das Feld
  `dokument_ids` (IDs aufsteigend) **nur, wenn die Buchung mindestens ein Dokument hat**;
  ohne Dokumente ist die Form unverändert gegenüber M17 (frühere Prüfsummen und Tests
  bleiben gleich). Ableitung: IDs aus `belege`.

### 3.2 Aktionen (`quelle = "manuell"`, `gruppe = null`, Beschreibungstexte frei)

| Aktion | Einträge |
| --- | --- |
| `dokument_anhaengen` | `dokument` angelegt; jede Ziel-Buchung geändert (`dokument_ids`) |
| `dokument_aus_mail` | wie `dokument_anhaengen` |
| `dokument_verknuepfen` | neu verknüpfte Buchungen geändert (Dokument selbst unverändert) |
| `dokument_loesen` | Buchung geändert; bei der letzten Verknüpfung zusätzlich `dokument` gelöscht |
| `dokument_umbenennen` | `dokument` geändert |
| `dokument_loeschen` | `dokument` gelöscht; alle verknüpften Buchungen geändert |

- **Bestehende Operationen:** Wird eine Buchung gelöscht (einzeln, mehrere, Konto mit
  Buchungen, Dublette, Einspielen …), enthält ihre `vorher`-Form `dokument_ids`; Dokumente,
  die an keiner anderen Buchung hängen, entfallen in **derselben** Änderung (Eintrag
  `dokument` gelöscht). Änderungen an einer Buchung ohne Bezug zu Dokumenten
  (Kategorie, Status …) lassen `dokument_ids` unverändert.
- Jede Operation, die nichts ändert, erzeugt keine Änderung.

### 3.3 Rückgängig

- Rückgängig stellt Dokumente mit derselben ID und alle Verknüpfungen wieder her; der
  Inhalt ist danach wieder abrufbar (`GET …/inhalt` liefert dieselben Bytes), auch nach
  dem Löschen der Buchung oder nach `dokument_loesen` mit `geloescht = true`.
- Rückgängig von `dokument_anhaengen` entfernt das Dokument und die Verknüpfungen.
- Zustandsprüfung wie `protokoll.md` 6.1; zusätzlich → 409 `rueckgaengig_konflikt`, wenn
  ein zu entfernendes Dokument inzwischen an einer Buchung hängt, die nicht Teil der
  rückgängig zu machenden Änderung ist.
- Bezugsprüfung (6.1 Punkt 5) zusätzlich: jede Verknüpfung zeigt auf ein vorhandenes
  Dokument und eine vorhandene Buchung; jedes Dokument hat seinen Inhalt.
- Invarianten T 3.5/3.6 gelten mit dem Objekt `dokument` (Bestandsabzug inkl.
  `dokument`).

---

## 4. Sicherung [kern] (ergänzt `sicherung.md` 2)

- `dokument` ist Buchbestand und Teil der Sicherung, samt Inhalten (nur die Inhalte, die
  ein enthaltenes Dokument braucht) und Verknüpfungen; ID-Zähler auch für Dokumente.
- **Nur bei Vorhandensein** (wie `kredit`, `postfach`, 2.5/2.6): `anzahl` und `inhalt`
  enthalten `dokument` genau dann, wenn die Sicherung mindestens ein Dokument enthält;
  `unterschied`, wenn Sicherung oder Bestand eines enthalten. `dokument` ist ein
  zulässiger Schlüssel in `anzahl`. Inhaltsprüfsumme mit den Protokollformen 3.1 (also
  auch `dokument_ids` an Buchungen, wo vorhanden). Ohne Dokumente bleiben Manifest und
  Prüfsummen wie vor M18.
- `schemaversion` steigt (Wert Sache der Implementierung); ältere Sicherungen werden ohne
  Dokumente gelesen (3.4).
- **Prüfung beim Einspielen** → `inhalt_ungueltig`, wenn ein enthaltener Inhalt nicht zu
  seinem SHA-256 passt, ein Dokument keinen Inhalt hat, `groesse` nicht zur Länge passt,
  der am Inhalt erkannte Typ nicht `mime_typ` ist, `quelle` oder `erstellt_am` ungültig
  ist, `dateiname` nicht schon gesäubert ist (1.3) oder ein Dokument an keiner Buchung
  hängt. (Manipulierte `kontor.sqlite` ist mit stimmiger `datenbank_sha256` und
  stimmigem Manifest zu bauen; das Schema der Datei ist Sache der Implementierung, daher
  genügt für Tests: Rundreise und eine Sicherung ohne Dokumente.)
- **Rundreise:** Sicherung mit Dokumenten in einer leeren App einspielen → gleiche
  Dokumente (IDs, Felder), gleiche `belege`, gleiche Inhalte (Bytes) über `…/inhalt`.
- Einspielen ersetzt Dokumente wie jeden Buchbestand; Rückgängig des Einspielens stellt
  sie wieder her.

---

## 5. Oberfläche

Siehe `oberflaeche.md` 28.

## 6. Abgrenzung

- Keine OCR, keine Volltextsuche in Dokumenten, keine Bearbeitung von Dokumentinhalten,
  kein Umbenennen und kein Löschen ganzer Dokumente in der Oberfläche (nur REST 2.4,
  2.5).
- Konfiguration unverändert (Größe über `upload_max_mib`).
- Tests in `tests/app/m18/` (Marker `m18`); REST, Protokoll, Sicherung und Schutz als
  `kern`, Oberfläche als Browsertests.
- Abhängigkeiten: M3 (Protokoll), M6 (Postfächer, Spiegel, IMAP-Attrappe), M7 (Schutz,
  Größengrenzen), M8 (Oberfläche), M9 (Sicherung), M15 (Buchungen löschen/verschieben),
  M17 (Gegenbuchung, Tabs).
