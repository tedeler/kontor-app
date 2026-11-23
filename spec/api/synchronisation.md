# Bank-Synchronisation – Meilenstein 2 (Ergänzungen bis M6)

Verbindlich für Implementierung und Tests. Ergänzt `datenmodell.md`,
`plugins.md` (Abschnitt 7), `python-api.md` (Abschnitt 8) und
`openapi.yaml` (Tags `sync`, `tan`, `benachrichtigungen`, `mock`). Die
Kategorisierung neuer Buchungen durch Regeln steht in `kategorisierung.md`.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Alles hier gilt für echte und Mock-Plugins gleich. In Tests wird nur das
Mock-Plugin verwendet (E-028); das echte FinTS-Plugin darf in M2 weiterhin
`PluginNichtVerfuegbar` werfen (E-017).

## 1. Überblick

Ein **Synchronisationslauf** (kurz *Lauf*) holt über das Bank-Plugin die
Bankkonten und deren Umsätze und übernimmt neue Umsätze als Buchungen ins
Buch. Ein Lauf wird manuell (`POST /api/sync`) oder vom Planer (Abschnitt
9) gestartet und läuft **synchron** innerhalb der Anfrage bzw. des
Planer-Takts. Er endet mit einem der Status aus 2.1 oder pausiert, wenn die
Bank eine TAN verlangt (Abschnitt 7).

Es läuft höchstens ein Lauf gleichzeitig je Datenbank. Solange ein Lauf auf
eine TAN wartet, wird kein neuer gestartet.

## 2. Datenobjekte

Alle Zeitstempel sind UTC mit `Z` (`datenmodell.md` 1) und stammen von der
App-Uhr (Abschnitt 8).

### 2.1 Synchronisationslauf (`SyncLauf`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | fortlaufend |
| `ausloeser` | `"manuell"` \| `"planer"` | |
| `status` | `"laeuft"` \| `"erfolgreich"` \| `"fehlgeschlagen"` \| `"wartet_auf_tan"` \| `"abgebrochen"` | siehe 5 |
| `gestartet_am` | date-time | |
| `beendet_am` | date-time \| null | null genau bei `laeuft` und `wartet_auf_tan` |
| `von`, `bis` | date \| null | wie in der Anfrage angegeben, sonst null |
| `fehler` | `{code, meldung}` \| null | erster Fehler des Laufs (siehe 6), sonst null |
| `tan_anforderung_id` | int \| null | ID der zuletzt in diesem Lauf entstandenen TAN-Anforderung |
| `konten` | Liste `SyncKonto` | ein Eintrag je Bankkonto, nach `iban` aufsteigend (Zeichenkettenordnung) |

### 2.2 Ergebnis je Bankkonto (`SyncKonto`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `iban` | str | normalisiert |
| `konto_id` | int | zugeordnetes Kontor-Konto (3) |
| `konto_neu` | bool | in diesem Lauf angelegt |
| `status` | `"erfolgreich"` \| `"fehlgeschlagen"` \| `"wartet_auf_tan"` \| `"ausstehend"` \| `"abgebrochen"` | |
| `von`, `bis` | date \| null | tatsächlich abgefragter Zeitraum (4.1); null bei `ausstehend` und bei `abgebrochen` ohne Abfrage |
| `umsaetze_gesamt` | int | Anzahl vom Plugin gelieferter Umsätze |
| `vormerkungen_ignoriert` | int | Umsätze mit `vormerkung = true` |
| `buchungen_vorhanden` | int | Umsätze mit bereits gemerkter Kennung (4.3) |
| `buchungen_zusammengefuehrt` | int | als eindeutige Dublette mit Vorhandenem zusammengeführt (4.4) |
| `buchungen_neu` | int | neu angelegte Buchungen (inkl. zur Prüfung) |
| `buchungen_zur_pruefung` | int | Teilmenge von `buchungen_neu` mit Dublettenverdacht |
| `buchungen_kategorisiert` | int | Teilmenge von `buchungen_neu`, die eine Regel kategorisiert hat |
| `fehler` | `{code, meldung}` \| null | |

Für erfolgreich verarbeitete Konten gilt
`umsaetze_gesamt = vormerkungen_ignoriert + buchungen_vorhanden +
buchungen_zusammengefuehrt + buchungen_neu`. Konten mit anderem Status haben
alle Zählungen 0.

### 2.3 Zustand je Bankkonto (`SyncKontoZustand`, `GET /api/sync/konten`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `iban` | str | |
| `konto_id` | int | aktuell zugeordnetes Konto |
| `letzter_abruf_bis` | date \| null | größtes `bis` aller erfolgreichen Abrufe dieses Kontos |
| `letzter_erfolg_am` | date-time \| null | Ende des letzten erfolgreichen Abrufs |

Ein Eintrag entsteht, sobald ein Bankkonto in einem Lauf zugeordnet wurde.
Liste nach `iban` aufsteigend.

## 3. Zuordnung der Bankkonten

`konten()` des Plugins liefert die Bankkonten. Jedes wird über die IBAN
einem Kontor-Konto zugeordnet:

1. Existiert ein Konto mit genau dieser (normalisierten) IBAN, wird es
   verwendet – unabhängig von Art, Name, `geschlossen` und `extern_id`. Es
   wird nicht verändert.
2. Sonst wird ein Konto angelegt: `name` = `BankKonto.name` nach `strip()`
   (leer → die IBAN), `art` = `BankKonto.art`, `iban` = IBAN,
   `eltern_id = null`, `geschlossen = false`, `eroeffnet_am = null`,
   `notiz = ""`, `extern_id = null` (damit ein späterer KMyMoney-Import das
   Konto nach `datenmodell.md` 10.3 Regel 2 über die IBAN übernimmt).
   `konto_neu = true`. Ab M3 gilt das nur beim ersten Auftreten der IBAN;
   für Bankkonten, deren Konto gelöscht wurde, gilt 16.2.

Die Zuordnung (inkl. Anlegen) wird für alle Bankkonten vor dem ersten
Umsatzabruf vorgenommen und bleibt auch bestehen, wenn der Lauf danach
scheitert.

## 4. Übernahme der Umsätze

Die Bankkonten werden in IBAN-Reihenfolge nacheinander verarbeitet.

### 4.1 Abfragezeitraum

- `bis` = `bis` der Anfrage, sonst *heute* (App-Uhr, Abschnitt 8).
- `von` = `von` der Anfrage; sonst, wenn das Konto einen
  `letzter_abruf_bis` = L hat: `L − sync_ueberlappung_tage`; sonst
  `heute − sync_erstabruf_tage` (Konfiguration, `python-api.md` 8).
- Ist `von > bis` (aus der Anfrage) → 422 `validierung`, es entsteht kein
  Lauf. Ein berechnetes `von > bis` wird auf `von = bis` gesetzt.
- Abruf: `plugin.umsaetze(iban, von, bis)` (nach einer TAN-Freigabe mit
  `tan=…`, Abschnitt 7).

### 4.2 Abbildung Umsatz → Buchung

Für jeden Umsatz, der nach 4.3 und 4.4 angelegt wird, in der vom Plugin
gelieferten Reihenfolge (`buchungstag`, `umsatz_id`); die Buchungs-IDs
steigen in dieser Reihenfolge:

| Buchungsfeld | Wert |
| --- | --- |
| `datum` | `buchungstag` |
| `empfaenger` | Empfänger mit exakt dem Namen `gegenpartei_name.strip()`; existiert keiner, wird er angelegt (`extern_id = null`). `gegenpartei_name` null oder nach `strip()` leer → kein Empfänger. |
| `verwendungszweck` | `verwendungszweck` unverändert |
| `status` | `importiert` |
| `splits` | genau zwei, in dieser Reihenfolge: `{konto_id: zugeordnetes Konto, betrag: betrag, memo: ""}` und `{konto_id: Gegenkonto, betrag: −betrag, memo: ""}` |
| Gegenkonto | Kategorie der ersten passenden Regel (`kategorisierung.md` 4); sonst das technische Konto **„Unkategorisiert“** |
| `tags` | `[]` |
| `extern_ids` | `[Kennung]` (4.3) |
| `vorschlag` | gesetzt, wenn eine Regel gegriffen hat (`kategorisierung.md` 5), sonst null |

Technisches Konto „Unkategorisiert“: `name = "Unkategorisiert"`, Art
`eigenkapital`, Wurzelkonto, `iban = null`, `geschlossen = false`,
`eroeffnet_am = null`, `notiz = ""`, `extern_id = "kontor:unkategorisiert"`.
Es wird beim ersten Bedarf angelegt und danach über die `extern_id`
wiederverwendet (auch wenn es umbenannt wurde); wurde es gelöscht, wird es
bei Bedarf neu angelegt. Buchungen darauf haben `kategorie_id = null` und
sind kategorisierbar (`datenmodell.md` 3.2).

- **Vormerkungen** (`vormerkung = true`) werden nie gebucht und nicht
  gemerkt; sie zählen in `vormerkungen_ignoriert`. Erscheint derselbe
  Umsatz später gebucht (`vormerkung = false`), wird er normal übernommen.
- **Storno** (`storno = true`) wird wie ein normaler Umsatz als eigene
  Buchung übernommen (Betrag mit dem gelieferten Vorzeichen); es gibt keine
  automatische Verrechnung mit der ursprünglichen Buchung.
- Ein Betrag 0 ist zulässig.

### 4.3 Kennung und Wiederholung

- *Kennung* eines Umsatzes: `"bank:" + iban + ":" + umsatz_id`.
- Die App merkt sich jede Kennung dauerhaft, sobald der Umsatz gebucht
  (4.2) oder zusammengeführt (4.4) wurde – auch wenn die Buchung später
  gelöscht oder per Dublettenauflösung entfernt wird.
- Ein Umsatz, dessen Kennung gemerkt ist, wird nie erneut gebucht
  (`buchungen_vorhanden`). Damit erzeugt ein wiederholter Abruf desselben
  Zeitraums keine Dubletten (T 6), auch bei Überlappung der Zeiträume.

Prüfreihenfolge je Umsatz: Vormerkung → gemerkte Kennung → Abgleich (4.4).

### 4.4 Abgleich mit vorhandenen Buchungen

Gilt für die Umsätze `N` eines Kontos `k` (IBAN `i`), die weder Vormerkung
noch gemerkt sind. Regeln wie `datenmodell.md` 10.4, mit diesen
Festlegungen:

- *Kandidaten* sind die Buchungen, die zu Beginn der Verarbeitung von `k`
  existieren und keine `extern_id` mit dem Präfix `"bank:" + i + ":"`
  haben (Umsätze desselben Bankkontos sind nie Dubletten voneinander;
  Buchungen aus KMyMoney, manuelle und aus anderen Bankkonten sind
  Kandidaten).
- Ein Kandidat `C` *trifft* den Umsatz `u`, wenn `C` einen Split auf `k`
  mit Betrag `u.betrag` hat. **Exakt**: zusätzlich `C.datum =
  u.buchungstag` und die Empfänger sind *passend* (`datenmodell.md` 1;
  Empfänger von `u` ist `gegenpartei_name.strip()` bzw. keiner).
  **Ähnlich**: nicht exakt und `|C.datum − u.buchungstag| ≤ 3` Tage.
- `E(u)`, `A(u)` wie in 10.4. Erst werden alle `u ∈ N` bewertet, dann
  angewendet:
  1. `|E(u)| = 1` und der einzige Kandidat `c` liegt in keinem `E(u')`
     eines anderen `u' ∈ N` → **zusammenführen**: keine neue Buchung;
     `c.extern_ids` erhält die Kennung; sonst bleibt `c` unverändert
     (insbesondere Kategorie, Status, Empfänger, Splits).
  2. Sonst, wenn `E(u) ∪ A(u)` nicht leer → Buchung nach 4.2 anlegen und
     offenen Dublettenverdacht (`datenmodell.md` 9) mit `buchung_id` = neue
     Buchung, `kandidat_ids = E(u) ∪ A(u)` (aufsteigend), `grund =
     "mehrdeutig"` falls `E(u)` nicht leer, sonst `"aehnlich"`.
  3. Sonst Buchung nach 4.2 anlegen.

Beispiel: Eine aus KMyMoney importierte Umbuchung Giro → Spar hat Splits
auf beiden Konten; der Giro-Umsatz und der Spar-Umsatz werden in ihrem
jeweiligen Konto exakt getroffen und beide mit derselben Buchung
zusammengeführt (sie erhält zwei `bank:`-Kennungen).

Dublettenverdachte aus der Synchronisation werden wie die aus dem Import
über `/api/dubletten` aufgelöst (`datenmodell.md` 9).

### 4.5 Atomarität

Die Verarbeitung eines Kontos (Buchungen, Empfänger, „Unkategorisiert“,
Kennungen, Verdachte, Zustand) wird als Ganzes geschrieben oder gar nicht.
Ergebnisse bereits erfolgreich verarbeiteter Konten bleiben erhalten, wenn
ein späteres Konto scheitert („ohne Datenverlust“, T 7).

## 5. Status eines Laufs

- Schlägt `konten()` fehl → Lauf `fehlgeschlagen`, `konten = []`.
- Schlägt `umsaetze()` eines Kontos mit einem anderen Fehler als
  `TanErforderlich` fehl → dieses Konto `fehlgeschlagen` (mit `fehler`,
  `von`, `bis`), die übrigen Konten werden weiter verarbeitet.
- `TanErforderlich` → Abschnitt 7: Konto `wartet_auf_tan`, alle später
  folgenden Konten `ausstehend`, Lauf `wartet_auf_tan` (pausiert).
- Am Ende: Lauf `fehlgeschlagen`, wenn mindestens ein Konto
  `fehlgeschlagen` ist, sonst `erfolgreich`. `beendet_am` = Ende.
- `abgebrochen`: TAN-Anforderung abgelaufen oder abgebrochen (7.4) oder
  Neustart (10); wartende und ausstehende Konten werden `abgebrochen`.
- Nach Erfolg eines Kontos: `letzter_abruf_bis = max(alt, bis)`,
  `letzter_erfolg_am` = jetzt.

## 6. Fehlerbehandlung und Benachrichtigungen

- Jeder Fehler des Plugins wird als `{code, meldung}` festgehalten: `code`
  = `PluginFehler.code` (z. B. `bank_verbindung`,
  `bank_zeitueberschreitung`, `bank_pin_fehlt`, `plugin_nicht_verfuegbar`).
  Das gilt auch für das Erzeugen des Plugins: Eine dabei geworfene
  `KontorFehler`-Ausnahme (z. B. `KonfigurationsFehler` wegen einer
  ungültigen Mock-Datendatei) ergibt einen fehlgeschlagenen Lauf mit deren
  `code` (`konfiguration_ungueltig`), `konten = []`. Andere Ausnahmen aus dem
  Plugin gelten als Fehler mit Code `plugin_fehler`. Ein Pluginfehler führt
  nie zu einer 5xx-Antwort.
- `SyncLauf.fehler` = erster Fehler in Verarbeitungsreihenfolge
  (`konten()` vor den Konten in IBAN-Reihenfolge); `TanErforderlich` zählt
  nicht als Fehler.
- Ein fehlgeschlagener Lauf ändert am Buch nichts außer der Kontozuordnung
  (3) und den Ergebnissen erfolgreicher Konten (4.5).
- **Wiederholung:** Der Planer startet nach einem fehlgeschlagenen Lauf
  erneut nach `sync_wiederholung_minuten` (9).
- **Benachrichtigungen** (Abschnitt 11): je fehlgeschlagenem Lauf und
  Fehlercode `c` eine Benachrichtigung `art = "sync_fehler"`,
  `schluessel = "sync_fehler:" + c` – aber nur, wenn es nicht bereits eine
  **ungelesene** Benachrichtigung mit diesem Schlüssel gibt (keine
  Nachrichtenflut, T 17).

## 7. TAN-Ablauf (K 6)

### 7.1 TAN-Anforderung (`TanAnforderung`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | |
| `lauf_id` | int | |
| `iban` | str | Konto, dessen Abruf die TAN verlangt |
| `konto_id` | int | |
| `status` | `"offen"` \| `"beantwortet"` \| `"abgelaufen"` \| `"abgebrochen"` | |
| `erstellt_am` | date-time | |
| `gueltig_bis` | date-time | aus `TanErforderlich.gueltig_bis` |
| `beendet_am` | date-time \| null | null genau bei `offen` |
| `challenge` | str | Anweisungstext der Bank (`TanErforderlich.challenge`) |
| `hat_bild` | bool | ob ein Bild (QR-Code) vorliegt |

Die interne `anforderung_id` des Plugins, die TAN und die PIN sind **nie**
Teil eines Datenobjekts, einer Antwort oder der Datenbank.

### 7.2 Entstehen

Wirft `umsaetze()` `TanErforderlich`: Die App legt eine TAN-Anforderung
(`offen`) an, merkt sich `anforderung_id` und die Plugin-Instanz im
Arbeitsspeicher, speichert Bild und Bildtyp, setzt Konto und Lauf auf
`wartet_auf_tan` und erzeugt eine Benachrichtigung `art =
"tan_erforderlich"`, `schluessel = "tan:" + id`, `link = "/tan/" + id`.
`POST /api/sync` antwortet 200 mit dem Lauf.

### 7.3 Beantworten

`POST /api/tan-anforderungen/{id}/antwort` mit `{"tan": "…"}`.
Prüfreihenfolge:

1. Unbekannte ID → 404. Ungültiger Körper → 422 `validierung`.
2. Abgelaufen (7.4) oder Status `abgelaufen` → 409 `tan_abgelaufen`.
3. Status nicht `offen` → 409 `tan_nicht_offen`.
4. Die App ruft für das wartende Konto erneut
   `umsaetze(iban, von, bis, tan=TanAntwort(anforderung_id, tan))` auf
   (gleicher Zeitraum, gleiche Plugin-Instanz):
   - `TanUngueltig` → 422 `tan_ungueltig`; die Anforderung bleibt `offen`,
     am Lauf ändert sich nichts.
   - `TanAbgelaufen` → wie Ablauf (7.4), 409 `tan_abgelaufen`.
   - anderer Fehler → Anforderung `abgebrochen`, Konto `fehlgeschlagen`,
     der Lauf verarbeitet die übrigen Konten weiter; 200 mit dem Lauf.
   - Erfolg → Anforderung `beantwortet`, Konto wird nach 4 verarbeitet,
     danach die ausstehenden Konten (dieselbe Plugin-Instanz, ohne `tan`);
     200 mit dem Lauf (Status nach 5). Verlangt dabei ein weiteres Konto
     eine TAN, pausiert der Lauf erneut (neue Anforderung).

Die TAN wird nach dem Aufruf verworfen; sie erscheint nie in Datenbank,
Logs, Antworten oder Fehlermeldungen.

### 7.4 Ablauf und Abbruch

- Eine offene Anforderung ist **abgelaufen**, sobald *jetzt* (App-Uhr) >
  `gueltig_bis`. Die App prüft das spätestens bei jedem Zugriff auf
  `/api/sync…` und `/api/tan-anforderungen…` sowie bei jedem Planer-Takt.
  Dann: Anforderung `abgelaufen` (`beendet_am` = jetzt), Lauf und dessen
  wartende/ausstehende Konten `abgebrochen`, Benachrichtigung `art =
  "tan_abgelaufen"`, `schluessel = "tan_abgelaufen:" + id`.
- `POST /api/tan-anforderungen/{id}/abbrechen`: offene Anforderung →
  `abgebrochen`, Lauf `abgebrochen`; 200 mit der Anforderung. Abgelaufen →
  409 `tan_abgelaufen`; sonst nicht offen → 409 `tan_nicht_offen`.
- Erinnerungen in Abständen (K 6 Schritt 4) und die Zustellung per ntfy
  sind M6.

### 7.5 Bild

`GET /api/tan-anforderungen/{id}/bild` liefert bei Status `offen` und
vorhandenem Bild genau die Bytes aus `TanErforderlich.bild` mit
`Content-Type` = `bild_mime_typ` (z. B. `image/png`), sonst 404
`nicht_gefunden`.

### 7.6 Während einer offenen Anforderung

- `POST /api/sync` → 409 `tan_ausstehend` (kein neuer Lauf).
- Der Planer startet keinen Lauf.
- Nach Ablauf oder Abbruch ist ein neuer Lauf wieder möglich; verlangt die
  Bank erneut eine TAN, entsteht eine neue Anforderung.

## 8. App-Uhr und simulierte Zeit im Mock-Modus

- *jetzt*: im Echtmodus die Systemzeit (UTC). Im Mock-Modus: der zuletzt
  per `PUT /api/mock/zeit` gesetzte Zeitpunkt; sonst, wenn
  `config.mock_heute` gesetzt ist, `mock_heute` 12:00:00Z; sonst die
  Systemzeit. Die simulierte Zeit steht still, bis sie neu gesetzt wird.
- *heute* = Datum von *jetzt* in UTC.
- Im Mock-Modus ruft die App vor jedem Plugin-Aufruf `setze_heute(heute)`
  des Mock-Bank-Plugins auf.
- `GET /api/mock/zeit` → `{jetzt, heute, simuliert}`; `PUT /api/mock/zeit`
  mit `{"jetzt": "<date-time mit Z>"}` setzt die Zeit (auch rückwärts) und
  liefert dasselbe Objekt. Im Echtmodus antworten beide mit 409
  `nur_mock_modus`. Die simulierte Zeit gilt je App-Instanz und wird nicht
  gespeichert.
- Alle Zeitstempel der App (Läufe, TAN-Anforderungen, Benachrichtigungen,
  Planer) verwenden *jetzt*. Zeitstempel werden ohne Sekundenbruchteile
  ausgegeben.

## 9. Planer (automatischer Abruf, K 3, K 6)

- Konfiguration (`python-api.md` 8): `sync_intervall_minuten` (0 = kein
  automatischer Abruf, Vorgabe 0), `sync_wiederholung_minuten`,
  `planer_starten`.
- *automatisch* = `sync_intervall_minuten > 0`.
- *Nächster Lauf* (`GET /api/sync/status`, `naechster_lauf`):
  - nicht automatisch, oder ein Lauf ist `laeuft`/`wartet_auf_tan` → null;
  - noch kein beendeter Lauf → *jetzt* (sofort fällig);
  - sonst sei `L` der beendete Lauf mit der größten `id`:
    `L.beendet_am + sync_wiederholung_minuten`, wenn `L` fehlgeschlagen ist,
    sonst `L.beendet_am + sync_intervall_minuten`.
- **Planer-Takt** (`kontor.sync.planer_takt(app)`, `python-api.md` 8):
  1. TAN-Abläufe prüfen (7.4).
  2. Ist automatisch, kein Lauf `laeuft`/`wartet_auf_tan` und *nächster
     Lauf* ≤ *jetzt* → Lauf mit `ausloeser = "planer"` starten (wie
     `POST /api/sync` ohne `von`/`bis`) und dessen JSON-Objekt (`SyncLauf`)
     zurückgeben; sonst `None`.
- **Hintergrund-Thread:** Nur wenn automatisch **und** `planer_starten`
  wahr ist. Er startet frühestens beim ASGI-Lifespan-Start der Anwendung
  (nie in `create_app`), führt den ersten Takt spätestens 5 s danach aus,
  danach mindestens alle 60 s, und endet beim Lifespan-Ende. Ohne Lifespan
  (z. B. `TestClient(app)` ohne `with`) läuft kein Planer.
- Manuelle Läufe zählen für *nächster Lauf* mit.

## 10. Neustart

Beim Erzeugen einer App (`create_app`) werden Läufe im Status `laeuft`
oder `wartet_auf_tan` und deren wartende/ausstehende Konten `abgebrochen`
(`beendet_am` = jetzt), offene TAN-Anforderungen `abgebrochen`. Die
Plugin-Instanz und die PIN gehen bei einem Neustart verloren; bereits
geschriebene Ergebnisse bleiben (T 20).

## 11. Benachrichtigungen (intern)

Benachrichtigungen sind in M2 eine Liste in der App (`GET
/api/benachrichtigungen`); die Zustellung per ntfy folgt in M6.

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | |
| `art` | `"sync_fehler"` \| `"tan_erforderlich"` \| `"tan_abgelaufen"` | spätere Meilensteine fügen Arten hinzu |
| `schluessel` | str | Entprellschlüssel (6, 7) |
| `titel` | str | nicht leer, deutsch |
| `text` | str | nicht leer, deutsch, ohne Geheimnisse |
| `link` | str \| null | `tan_erforderlich`: `"/tan/<id>"`, sonst null |
| `erstellt_am` | date-time | |
| `gelesen` | bool | anfangs false |

- `GET /api/benachrichtigungen` (optional `?gelesen=true|false`), nach
  `id` aufsteigend.
- `POST /api/benachrichtigungen/{id}/gelesen` → `gelesen = true`, 200 mit
  dem Objekt (idempotent).

## 12. PIN (K 6)

- In M2 ist nur die Variante „PIN gar nicht speichern und bei Bedarf in der
  Weboberfläche eingeben“ umgesetzt: `PUT /api/sync/pin` mit
  `{"pin": "…"}` legt die PIN **nur im Arbeitsspeicher** der App-Instanz
  ab (204), `DELETE /api/sync/pin` verwirft sie (204, auch wenn keine
  gesetzt ist). `GET /api/sync/status` zeigt nur `pin_vorhanden`.
- Die App übergibt dem Bank-Plugin eine `pin_quelle` (`plugins.md` 7), die
  die aktuelle PIN oder None liefert.
- Meldet das Plugin `BankPinFalsch`, verwirft die App die PIN sofort (kein
  erneuter Versuch mit derselben PIN, Schutz vor Kontosperre).
- Die PIN erscheint **nie** in: Datenbankdateien (einschließlich
  `-wal`/`-journal`/`-shm`), Logausgaben (jeder Logger, jede Stufe,
  stdout/stderr), API-Antworten (auch nicht in Validierungsfehlern zu
  `PUT /api/sync/pin`), Fehlermeldungen und `details` von Ausnahmen,
  `repr()` von Plugins oder Datenobjekten.
- Nach einem Neustart ist keine PIN vorhanden.
- systemd-creds/TPM folgt in M6.
- Ab M23 (`geheimnisschutz.md` 4, 5): Bei eingeschaltetem Schutz der Geheimnisse
  kann die PIN zusätzlich **gemerkt** werden (`PUT /api/sync/pin/gemerkt`,
  verschlüsselt unter dem Schutz); Quelle dann: PIN im Arbeitsspeicher, sonst
  lesbare gemerkte PIN. `DELETE /api/sync/pin` löscht auch die gemerkte PIN;
  `BankPinFalsch`/`BankZugangGesperrt` löschen sie sofort.

## 13. REST-Endpunkte (Überblick; Schemas in `openapi.yaml`)

| Methode, Pfad | Zweck |
| --- | --- |
| `POST /api/sync` | Lauf starten (`{von?, bis?}`) → 200 `SyncLauf`; 409 `sync_laeuft`, `tan_ausstehend`; 422 `validierung` |
| `GET /api/sync/status` | `SyncStatus` |
| `GET /api/sync/laeufe`, `GET /api/sync/laeufe/{lauf_id}` | Läufe, nach `id` aufsteigend |
| `GET /api/sync/konten` | `SyncKontoZustand`-Liste |
| `POST /api/sync/konten/{iban}/entscheidung` | gelöschtes Bankkonto wiederherstellen oder ignorieren (16.3) → 200 `SyncKontoZustand`; 404 `nicht_gefunden`; 409 `konto_vorhanden`; 422 `validierung` |
| `PUT /api/sync/pin`, `DELETE /api/sync/pin` | PIN im Arbeitsspeicher |
| `GET /api/tan-anforderungen`, `GET /api/tan-anforderungen/{tan_id}` | TAN-Anforderungen, nach `id` aufsteigend |
| `GET /api/tan-anforderungen/{tan_id}/bild` | Bild der offenen Anforderung |
| `POST /api/tan-anforderungen/{tan_id}/antwort` | TAN eingeben |
| `POST /api/tan-anforderungen/{tan_id}/abbrechen` | abbrechen |
| `GET /api/benachrichtigungen`, `POST /api/benachrichtigungen/{id}/gelesen` | Benachrichtigungen |
| `GET /api/mock/zeit`, `PUT /api/mock/zeit` | simulierte Uhr (nur Mock-Modus) |

`SyncStatus = {automatisch, intervall_minuten, laeuft, jetzt,
naechster_lauf, letzter_lauf, offene_tan_anforderung, pin_vorhanden}` mit
`laeuft` = ein Lauf hat Status `laeuft`, `letzter_lauf` = Lauf mit größter
`id` oder null, `offene_tan_anforderung` = offene `TanAnforderung` oder
null.

## 14. Meilenstein 3: Ergänzungen

Ohne Aliase, Standardkategorien, Abstimmungen und mit
`umbuchung_automatisch = False` bleibt alles in 1–13 unverändert (E-029).

### 14.1 Empfänger und Gegen-IBAN

- Der Empfänger eines neuen Umsatzes wird nach `buchhaltungspflege.md` 2.3
  bestimmt (exakter Name, dann Alias, sonst neu). Der *Empfängername* des
  Umsatzes ist der Name des so gefundenen Empfängers bzw. – wenn keiner
  existiert – `gegenpartei_name.strip()`. Er gilt für die Regelauswertung
  (`kategorisierung.md` 4) **und** für den Empfängervergleich beim Abgleich
  (4.4). Ohne Aliase ist das genau `gegenpartei_name.strip()` wie in M2.
- `Buchung.gegen_iban` = `gegenpartei_iban` normalisiert, wenn gültig, sonst
  null (`buchhaltungspflege.md` 1.1).

### 14.2 Gegenkonto

Reihenfolge: erste passende Regel → Standardkategorie des Empfängers (als
Vorschlag mit `quelle = "standardkategorie"`, `buchhaltungspflege.md` 2.5)
→ „Unkategorisiert“. `buchungen_kategorisiert` zählt beide Stufen.

### 14.3 Umbuchungen

Bei `umbuchung_automatisch = True` folgt auf die Verarbeitung jedes Kontos
mit neuen Buchungen die automatische Erkennung (`buchhaltungspflege.md`
4.4) in einer eigenen Änderung derselben Gruppe.

### 14.4 Protokoll

Jede Kontozuordnung mit neu angelegten Konten und jede Kontoverarbeitung
mit Wirkung erzeugen Änderungen der Gruppe `"sync:<lauf_id>"`
(`protokoll.md` 4.2). Ein ganzer Lauf lässt sich über diese Gruppe
rückgängig machen; dabei werden auch seine gemerkten Kennungen vergessen
(`protokoll.md` 6.1 Schritt 4, 6.4).

### 14.5 Gesperrte Buchungen

Gesperrte (auch abgestimmte) Buchungen bleiben Kandidaten des Abgleichs
(4.4); beim Zusammenführen erhalten sie nur die Kennung (keine inhaltliche
Änderung).

## 15. Meilenstein 4: Ergänzungen

Ohne Split-Vorlagen und mit `lernmodell_automatisch = False` (Vorgabe) bleibt
alles in 1–14 unverändert (E-029).

### 15.1 Gegenkonto und Splits neuer Buchungen

Für jeden neuen Umsatz (4.2) in dieser Reihenfolge (erste zutreffende Stufe
gilt):

1. Split-Vorlage, Treffer → Buchung mit den Splits der Vorlage, ohne
   Vorschlag; Abweichung → Gegenkonto „Unkategorisiert“ ohne Vorschlag,
   Benachrichtigung `split_abweichung` (`vorlagen.md` 4, 6).
2. erste passende Regel (Vorschlag `quelle = "regel"`);
3. Standardkategorie des Empfängers (14.2);
4. Lernmodell bei `lernmodell_automatisch = True` (`lernmodell.md` 5.1,
   Trainingsmenge zu Beginn der Verarbeitung des Kontos);
5. „Unkategorisiert“.

### 15.2 Zählungen (`SyncKonto`, im Schema optional, ab M4 in jeder Antwort)

| Feld | Bedeutung |
| --- | --- |
| `buchungen_gesplittet` | Teilmenge von `buchungen_neu`, die nach einer Vorlage aufgeteilt wurde |
| `vorlage_abweichungen` | Teilmenge von `buchungen_neu` mit Abweichung von einer Vorlage |

`buchungen_kategorisiert` zählt die Stufen 2–4. Konten mit anderem Status als
`erfolgreich` haben alle Zählungen 0.

### 15.3 Benachrichtigungen

Zusätzliche Art `split_abweichung` (`vorlagen.md` 6), Entprellung wie in 6.

### 15.4 Mock-Szenario `beitragsaenderung`

`plugins.md` 8 und `vorlagen.md` 7.

## 16. Gelöschte Bankkonten (Nachtrag zu Meilenstein 3)

Auftrag des Anwenders vom 2026-11-08 (E-080 bis E-084). Ohne gelöschte
oder von der IBAN befreite Bankkonten bleibt alles in 1–15 unverändert.

Problem bisher: Wurde das einem Bankkonto zugeordnete Konto gelöscht, legte
der nächste Lauf nach 3 Regel 2 still ein neues, leeres Konto an. Die
Umsätze kamen nicht zurück, weil ihre Kennungen gemerkt bleiben (4.3), und
der Abfragezeitraum begann wegen `letzter_abruf_bis` erst kurz vor dem
letzten Abruf (4.1). Neu entscheidet der Anwender, was geschehen soll.

### 16.1 Zustand je Bankkonto

`SyncKontoZustand` (2.3) erhält zwei Felder (im Schema optional, in den
M3-Tests Pflicht):

| Feld | Typ | Regeln |
| --- | --- | --- |
| `status` | `"aktiv"` \| `"konto_fehlt"` \| `"ignoriert"` \| `"wiederherstellen"` | siehe unten |
| `wiederherstellen_buchungen` | `"alle"` \| `"nur_neue"` \| null | nicht null genau bei `status = "wiederherstellen"` |

- `aktiv`: Es existiert ein Konto mit dieser IBAN (gleich, wie es entstanden
  ist: Lauf, manuell, Import, Rückgängig).
- Sonst bestimmt die gespeicherte Entscheidung (16.3) den Status: keine →
  `konto_fehlt`, `ignorieren` → `ignoriert`, `wiederherstellen` →
  `wiederherstellen`.
- Ein Bankkonto „fehlt“ also, sobald kein Konto mehr diese IBAN trägt:
  nach `DELETE /api/konten/{id}`, nach `POST /api/konten/{id}/loeschen`
  (jede Variante) und nach dem Entfernen oder Ändern der IBAN.
- `konto_id` ist das zuletzt zugeordnete Konto; es wird wie bisher nur bei
  der Zuordnung in einem Lauf (3) gesetzt und kann daher auf ein gelöschtes
  Konto zeigen.
- Der Eintrag bleibt bestehen, wenn das Konto gelöscht wird. Er entfällt
  nur nach 6.4 von `protokoll.md` (Rückgängig der Zuordnung, die ihn
  angelegt hat).

### 16.2 Zuordnung im Lauf

Regel 3 gilt mit dieser Ergänzung. Für jedes Bankkonto mit IBAN `i`:

1. Existiert ein Konto mit IBAN `i` → wie 3 Regel 1. Eine gespeicherte
   Entscheidung wird verworfen.
2. Sonst, wenn es keinen Eintrag für `i` gibt → wie 3 Regel 2 (erstes
   Auftreten: Konto anlegen).
3. Sonst, bei Status `wiederherstellen` → Konto nach 3 Regel 2 anlegen
   (`konto_neu = true`), dann:
   - bei `wiederherstellen_buchungen = "alle"`: Alle gemerkten Kennungen mit
     dem Präfix `"bank:" + i + ":"` werden vergessen, die in keiner
     `extern_ids` einer existierenden Buchung stehen. `letzter_abruf_bis`
     wird null. Der folgende Abruf (4.1) beginnt deshalb ohne `von` bei
     `heute − sync_erstabruf_tage` und übernimmt nach 4.2–4.4 alle in diesem
     Zeitraum gelieferten Umsätze, deren Buchung nicht mehr existiert.
   - bei `"nur_neue"`: Kennungen und `letzter_abruf_bis` bleiben. Es kommen
     nur Umsätze hinzu, die noch nie übernommen wurden (Verhalten wie
     bisher, aber ausdrücklich gewählt).
   - Die Entscheidung wird verworfen; danach ist der Status `aktiv`.
4. Sonst (Status `konto_fehlt` oder `ignoriert`) → **übersprungen**: Es wird
   kein Konto angelegt, kein Umsatz abgerufen, und das Bankkonto erscheint
   nicht in `konten` des Laufs, sondern in `uebersprungen` (16.4). Bei
   `konto_fehlt` entsteht eine Benachrichtigung (16.5).

Umsätze, deren Buchung noch existiert (etwa nach dem Löschen mit
`elternkonto` oder `unkategorisiert`, `loeschen.md` 3.2), werden auch bei
`"alle"` nie erneut gebucht: Ihre Kennung hängt weiter an dieser Buchung,
und eine zweite Buchung würde den Umsatz doppelt zählen (E-082).

Das Anlegen und das Vergessen gehören zur Änderung `sync_kontozuordnung`
des Laufs (`protokoll.md` 4.2). Wird sie rückgängig gemacht, verschwindet
das Konto, die vergessenen Kennungen werden wieder gemerkt (`protokoll.md`
6.1 Schritt 4), und der Eintrag erhält wieder den Status `konto_fehlt`
(`protokoll.md` 6.4). `letzter_abruf_bis` bleibt, wie es ist
(Betriebszustand, E-057).

Der Planer (9) und nach einer TAN fortgesetzte Läufe verhalten sich
genauso; übersprungene Bankkonten zählen nie als Fehler. Ein Lauf, in dem
alle Bankkonten übersprungen werden, ist `erfolgreich` mit `konten = []`.

### 16.3 Entscheidung des Anwenders

`POST /api/sync/konten/{iban}/entscheidung` mit Körper
`SyncKontoEntscheidung`:

| Feld | Typ | Pflicht | Bedeutung |
| --- | --- | --- | --- |
| `aktion` | `"wiederherstellen"` \| `"ignorieren"` | ja | beim nächsten Lauf ein Konto anlegen bzw. das Bankkonto dauerhaft überspringen |
| `buchungen` | `"alle"` \| `"nur_neue"` | ja | nur bei `wiederherstellen` wirksam (16.2 Regel 3); bei `ignorieren` ohne Wirkung, aber trotzdem Pflicht |

`{iban}` wird wie jede IBAN normalisiert (Leerzeichen entfernt,
Großbuchstaben, IBAN-Regeln in `datenmodell.md` 2). Prüfreihenfolge (die erste
zutreffende Regel bestimmt die Antwort, nichts wird geändert):

1. Körper ungültig (fehlendes Feld, unbekannter Wert, falscher Typ,
   unbekanntes Feld) → 422 `validierung`.
2. Kein Eintrag für die IBAN → 404 `nicht_gefunden`.
3. Status `aktiv` → 409 `konto_vorhanden`.
4. Sonst wird die Entscheidung gespeichert (eine frühere ersetzt; aus
   `ignoriert` kann also später noch `wiederherstellen` werden). Ungelesene
   Benachrichtigungen mit dem Schlüssel `konto_fehlt:<iban>` werden gelesen.
   Antwort 200 mit dem aktualisierten `SyncKontoZustand`.

Die Entscheidung selbst ändert keinen Buchbestand und wird nicht
protokolliert (Betriebszustand wie `/api/sync/konten`). Wirkung auf den
Buchbestand hat erst der nächste Lauf. Die Oberfläche bietet nach dem
Wiederherstellen an, sofort einen Lauf zu starten, und schlägt
`buchungen = "alle"` nicht als Vorgabe vor: Die Frage wird gestellt, nicht
beantwortet (wie E-061).

### 16.4 Übersprungene Bankkonten im Lauf

`SyncLauf` erhält das Feld `uebersprungen` (im Schema optional, in den
M3-Tests Pflicht): Liste von `{iban, name, status}`, nach `iban`
aufsteigend, mit `name` = `BankKonto.name` nach `strip()` (leer → IBAN)
und `status` ∈ {`konto_fehlt`, `ignoriert`}. Leer, wenn nichts
übersprungen wurde. Die Zählungen und die Regel „ein Eintrag je Bankkonto“
in `konten` (2.1) beziehen sich nur auf nicht übersprungene Bankkonten.

### 16.5 Benachrichtigung

Neue Art `konto_fehlt`, Schlüssel `konto_fehlt:<iban>`, `link =
"/sync/konten"`. Sie entsteht in jedem Lauf, der das Bankkonto mit Status
`konto_fehlt` überspringt, aber nur, wenn keine ungelesene Benachrichtigung
mit diesem Schlüssel existiert (Entprellung wie 6). Text deutsch, nennt
Name und IBAN und fragt, ob das Konto wiederhergestellt oder das Bankkonto
ignoriert werden soll. Bei `ignoriert` gibt es keine Benachrichtigung.

## 17. Meilenstein 5: Ergänzungen

Ohne Kredite und mit `wiederkehrend_automatisch = False` (Vorgabe) bleibt
alles in 1–16 unverändert (E-029).

### 17.1 Gegenkonto und Splits neuer Buchungen

Vor Stufe 1 aus 15.1 steht als **Stufe 0** die Erkennung einer Kreditrate
(`kredite.md` 4.2): Treffer → Buchung mit Zahlungs-, Zins- und
Tilgungssplit, `status = "vorlaeufig"`, ohne Vorschlag; die übrigen Stufen
entfallen. Kein Treffer → weiter mit Stufe 1. Das gilt auch für Umsätze, die
nach 4.4 Regel 2 mit Dublettenverdacht angelegt werden.

### 17.2 Zählungen (`SyncKonto`, im Schema optional, ab M5 in jeder Antwort)

| Feld | Bedeutung |
| --- | --- |
| `buchungen_kredit` | Teilmenge von `buchungen_neu`, die als Kreditrate aufgeteilt wurde |

Es gilt `buchungen_kredit + buchungen_gesplittet + vorlage_abweichungen ≤
buchungen_neu`; `buchungen_kategorisiert` zählt Kreditraten nicht.

### 17.3 Wiederkehrende Buchungen

Bei `wiederkehrend_automatisch = True` folgt auf jeden Lauf mit Endstatus
die Prüfung auf unerwartete Buchungen (`wiederkehrend.md` 5) mit den neuen
Buchungen von Konten, die vor dem Lauf schon erfolgreich abgerufen wurden.
Sie erzeugt nur Benachrichtigungen (Arten `neuer_empfaenger`,
`wiederkehrend_betrag`, `wiederkehrend_ausbleibend`), keine Änderung.

## 18. Meilenstein 6: Ergänzungen

Ohne die neuen Konfigurationsfelder (Vorgaben: `bank_pin_quelle =
"eingabe"`, Benachrichtigungs-Plugin `keins` im Echtmodus) bleibt alles in
1–17 unverändert (E-029). Das echte FinTS-Plugin (`fints.md`) erfüllt die
Plugin-Schnittstelle; Lauf, Zuordnung, Übernahme, Abgleich, TAN-Ablauf und
Fehlerbehandlung sind für echte und Mock-Plugins gleich.

### 18.1 PIN-Quelle

`bank_pin_quelle = "systemd-creds"`: PIN aus `$CREDENTIALS_DIRECTORY`
nach `fints.md` 5; `PUT`/`DELETE /api/sync/pin` → 409 `pin_quelle_systemd`;
`BankPinFalsch` oder `BankZugangGesperrt` sperren die Quelle bis zum
Neustart. Bei `eingabe` verwirft die App die PIN auch nach
`BankZugangGesperrt` (wie nach `BankPinFalsch`, 12). `SyncStatus` erhält
das Feld `pin_quelle`.

### 18.2 Planer-Takt

Ein Takt (`kontor.sync.planer_takt`, Hintergrund-Thread) führt in dieser
Reihenfolge aus:

1. TAN-Abläufe prüfen (7.4);
2. TAN-Erinnerungen (`benachrichtigungen.md` 5);
3. Mail-Anmeldungen prüfen: Vorwarnung und Ablauf (`mail.md` 5.3);
4. Synchronisationslauf, falls fällig (9);
5. Mail-Abruf, falls fällig (`mail.md` 6.4);
6. Zustellung fälliger, noch ausstehender Benachrichtigungen
   (`benachrichtigungen.md` 4.3 Schritt 4).

Rückgabe unverändert: der in Schritt 4 gestartete Lauf oder `None`. Der
Hintergrund-Thread läuft wie bisher nur bei `planer_starten` und mindestens
einem automatischen Vorgang (`sync_intervall_minuten > 0` oder
`mail_intervall_minuten > 0`); TAN-Erinnerungen, Mail-Prüfungen und
Wiederholungen der Zustellung brauchen im Betrieb also ein Intervall > 0.

### 18.3 Benachrichtigungen

Jede Benachrichtigung aus 6, 7, 15.3, 16.5 und 17.3 wird zusätzlich nach
`benachrichtigungen.md` 4 zugestellt; die Entprellregeln bleiben, wie sie
sind. Neue Arten: `tan_erinnerung`, `mail_token_laeuft_ab`,
`mail_token_abgelaufen`, `mail_token_widerrufen`, `mail_fehler`
(`benachrichtigungen.md` 6).

### 18.4 Echtes Plugin

- Die App erzeugt das echte Plugin wie das Mock-Plugin frühestens beim
  ersten Lauf und behält die Instanz (für den offenen FinTS-Dialog einer
  TAN-Anforderung).
- Ein Neustart (10) bricht offene TAN-Anforderungen ab; der Dialog bei der
  Bank verfällt.

## 19. Meilenstein 11: Kontostand

Nach der Verarbeitung jedes erfolgreich abgerufenen Bankkontos vergleicht
der Lauf den von der Bank gemeldeten Saldo mit dem Kontor-Saldo und bucht
eine Differenz als Ausgleichsbuchung gegen „Korrekturen“
(`SyncKonto.saldo_abgleich`, Änderung `sync_saldoausgleich`,
Benachrichtigung `saldo_ausgeglichen`). Regeln: `kontostand.md`.

## 20. Meilenstein 15: Synchronisationskonto und unbekannte Bankkonten

Freigegebene Meilenstein-Definition vom 2026-11-10 (E-181, E-186). Mit
`sync_konten_anlegen = True` (Vorgabe) bleibt alles in 1–19 unverändert
(E-029).

### 20.1 Konfiguration

`KontorConfig.sync_konten_anlegen` (`python-api.md` 18,
Umgebungsvariable `KONTOR_SYNC_KONTEN_ANLEGEN`), Vorgabe `True`; in der
ausgelieferten Umgebungsdatei `0` (`betrieb.md` 3). `True`: Zuordnung wie
3 (unbekannte Bankkonten werden als Konto angelegt). `False`: unbekannte
Bankkonten werden übersprungen (20.2).

### 20.2 Lauf mit `sync_konten_anlegen = False`

Ein Bankkonto mit IBAN `i`, für die **kein Konto** die IBAN trägt **und**
für die es **keinen Eintrag** in `GET /api/sync/konten` gibt (16.2
Regel 2, „erstes Auftreten“):

- Es wird kein Konto angelegt, kein Umsatz abgerufen, und es entsteht kein
  Eintrag in `GET /api/sync/konten`.
- Das Bankkonto steht nicht in `konten` des Laufs, sondern in
  `uebersprungen` (16.4) als `{iban, name, status: "nicht_zugeordnet",
  art}` mit `name` wie 16.4 und `art` = `BankKonto.art`, wenn sie eine
  Bestandsart ist (`girokonto`, `sparkonto`, `kreditkonto`), sonst
  `girokonto`. Liste nach `iban` aufsteigend, gemeinsam mit den Einträgen
  aus 16.4.
- Es entsteht eine Benachrichtigung (Zustellung nach `benachrichtigungen.md` 4,
  Priorität 3 wie die übrigen Arten) der Art
  `konto_nicht_zugeordnet`, Schlüssel `konto_nicht_zugeordnet:<i>`, `link =
  "/sync"`, Titel und Text deutsch (Text nennt Name und IBAN), aber nur,
  wenn keine ungelesene Benachrichtigung mit diesem Schlüssel existiert
  (Entprellung wie 6). Höchstens eine ungelesene je IBAN.
- Übersprungene Bankkonten sind kein Fehler und zählen nicht in Zählungen
  und Fehlern des Laufs. Ein Lauf, in dem alle Bankkonten übersprungen
  werden, ist `erfolgreich` mit `konten = []` und erzeugt keine Änderung im
  Protokoll.
- Bankkonten, die ein Konto tragen (3 Regel 1), werden wie bisher
  verarbeitet. Bankkonten mit Eintrag in `GET /api/sync/konten`, deren
  Konto gelöscht wurde, verhalten sich weiter nach 16 (`konto_fehlt`,
  `ignoriert`, `wiederherstellen`).
- Planer (9) und nach einer TAN fortgesetzte Läufe verhalten sich genauso.

`uebersprungen[].status` kennt damit zusätzlich `nicht_zugeordnet`;
`uebersprungen[].art` ist im Schema optional (Pflicht nur bei
`nicht_zugeordnet`, in den M15-Tests geprüft).

### 20.3 Zuordnen

Das Synchronisationskonto eines Kontos ist seine `iban` (genau eines je
Konto, `datenmodell.md` 2). Zugeordnet wird über die vorhandenen Endpunkte
`PATCH /api/konten/{id}` `{iban}` bzw. `POST /api/konten` `{…, iban}`
(Protokoll wie bisher `konto_aendern` bzw. `konto_anlegen`). Trägt danach ein
Konto die IBAN `i`, sind alle Benachrichtigungen mit dem Schlüssel
`konto_nicht_zugeordnet:<i>` gelesen (`gelesen = true`, in derselben
Anfrage). Der nächste Lauf übernimmt die Umsätze nach 3 Regel 1 (Konto
unverändert, `konto_neu = false`) wie beim ersten Abruf (4.1).

## 21. Meilenstein 29: Bankzugang, ausgewählte Konten, TAN bei der Anmeldung, alte Kennungen

Übernahme von Abschnitt 4 der Definition „Bankabruf über FinTS/camt und
Bankzugang in der Oberfläche“ (E-258). Für das Mock-Plugin bleibt alles in
1–20 unverändert.

### 21.1 Lauf mit dem FinTS-Plugin

- Sind im Bankzugang Konten gespeichert (`bankzugang.md` 4.4), verarbeitet
  ein Lauf genau die ausgewählten Konten (`aktiv`) und fragt die Kontenliste
  nicht bei der Bank ab. Ist kein Konto ausgewählt, verarbeitet der Lauf kein
  Konto (`konten` des Laufs ist leer, keine Buchung entsteht).
- Sind keine Konten gespeichert, fragt der Lauf die Kontenliste wie bisher
  bei der Bank ab. Braucht schon dieser Abruf eine TAN (`fints.md` 3.5a),
  scheitert der Lauf wie bisher (Status `fehlgeschlagen`, keine
  TAN-Anforderung); die Meldung nennt zusätzlich den Weg, die Konten einmal
  in den Einstellungen abzurufen (sie enthält das Wort „Einstellungen“).
- Verlangt die Bank beim Abruf eines Kontos eine TAN für die Anmeldung,
  wartet der Lauf wie bei einer TAN zum Umsatzabruf (7): eine TAN-Anforderung
  an diesem Konto, Antwort und Abbruch über die bestehenden Endpunkte und die
  TAN-Seite. Folgt danach eine TAN für den Abruf selbst, entsteht eine neue
  TAN-Anforderung am selben Lauf.
- Der Bankzugang aus der Oberfläche (`bankzugang.md` 4) gilt ab dem nächsten
  Lauf, ohne Neustart.

### 21.2 Übergang alter Bank-Kennungen

`bankzugang.md` 3: Ein Umsatz mit unbekannter Kennung wird einer Buchung mit
nur alten Kennungen (gleiches Bankkonto, gleicher Betrag, gleicher
Buchungstag, alte Kennung nicht im selben Abruf geliefert) zugeordnet statt
neu gebucht. Die Prüfung steht in der Reihenfolge aus 4.3 nach „gemerkte
Kennung“ und vor dem Abgleich (4.4). Die Zuordnung zählt als
`buchungen_zusammengefuehrt`; die Summenregel aus 2.2 gilt weiter.

### 21.3 REST

Neue Endpunkte unter `/api/bank/zugang` (`bankzugang.md` 4). Solange ein Lauf
läuft oder auf eine TAN wartet, lehnen die ändernden Endpunkte des
Bankzugangs mit 409 `sync_laeuft` bzw. `tan_offen` ab.
