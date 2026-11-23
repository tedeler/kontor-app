# Sammelpaket M27: Verdacht, Bestätigung durch Personen, Filter, Dubletten, Statistik

Übernahme der freigegebenen Definition M27 (Auftraggeber, 2026-11-16, Feature `sammel`, kontor-app
D-145 bis D-170; E-249). Die Mail-Liste (Definition 5) steht in `mail.md` 6.6, die Oberfläche in
`oberflaeche.md` 37 (M28). Alle Erweiterungen sind rückwärtskompatibel (E-029): neue Felder erscheinen nur
auf Anfrage oder sind im Schema optional und ändern keine bisherige Antwort. `openapi.yaml` 2.21.0 (E-251).
Tests: `tests/app/m27/` (Marker `m27`, Hilfen `tests/hilfen/m27.py`); alle REST-Tests `kern` außer der
Inhaltsprüfung der Statistik (6). Prüfmerkmale und Lesarten: E-250.

## 0. Begriffe

- **Zahlungskonto:** Konto der Art `girokonto` oder `sparkonto` (nicht `kreditkonto`).
- **Zahlungsbetrag einer Buchung:** Summe (ganze Cent, mit Vorzeichen) ihrer Splits auf Zahlungskonten, **nur
  wenn** diese Splits auf genau **einem** Zahlungskonto liegen. Liegen sie auf keinem oder auf zwei und mehr
  verschiedenen Zahlungskonten, hat die Buchung keinen Zahlungsbetrag.
- **bestätigt** (für dieses Kapitel): Status `bestaetigt` oder `abgeglichen`. **unbestätigt:** `importiert`
  oder `vorlaeufig`.
- `norm`, `ekey`: wie `datenmodell.md` 1.
- **Robuster Median/MAD:** Median einer Liste ganzer Cent: bei ungerader Länge das mittlere Element der
  sortierten Liste, bei gerader Länge `(a + b) // 2` der beiden mittleren (Ganzzahldivision, abrundend Richtung
  −∞). MAD = Median der Beträge `|w − Median|`. **Robustes z in Hundertsteln:** `skala = MAD × 14826 // 10000`;
  ist `skala = 0`, so ist z = 0 für `w = Median`, sonst „unbestimmt“; sonst `z = |w − Median| × 100 // skala`.
  Schwelle „stark“: z ≥ 350 (robustes z 3,50) oder z unbestimmt.

## 1. Label „Verdächtig“ an Buchungen (D-157, D-159)

### 1.1 Anfordern

Das Feld `verdacht` erscheint **nur auf Anfrage**: Abfrageparameter `verdacht` ∈ {`ja`, `nein`} (Vorgabe
`nein`, wie `serien` und `vorschlaege`; jeder andere Wert → 422 `validierung`) an

- `GET /api/buchungen` (je Eintrag),
- `GET /api/buchungen/{id}`,
- `GET /api/suche` (je Eintrag in `buchungen`).

Ohne den Parameter sind diese Antworten unverändert gegenüber dem Stand vor M27. Andere Antworten (Anlegen, Ändern,
Mehrfachänderungen, Verschieben, Erwartungen, Protokoll, Sicherung, Export) tragen `verdacht` **nie**.

### 1.2 Regel

`verdacht` wird beim Lesen gebildet und nie gespeichert (keine Protokoll-, keine Sicherungswirkung). Es fehlt
(Feld nicht vorhanden) bei bestätigten Buchungen und bei Buchungen ohne Empfänger. Für eine unbestätigte Buchung
`B` mit Empfänger `E`, betrachtet über **alle** Buchungen mit Empfänger `E` (konto- und filterunabhängig, `B`
eingeschlossen):

1. **Empfänger unbekannt:** Hat `E` keine bestätigte Buchung → `{"grund": "empfaenger", "text": …}`.
   Text: `Der Empfänger „<Name>“ kommt nur in unbestätigten Buchungen vor (<n> Buchung|Buchungen).` mit `n` =
   Anzahl aller Buchungen von `E` („1 Buchung“, sonst „n Buchungen“).
2. Sonst **Betrag:** `W` = Zahlungsbeträge der bestätigten Buchungen von `E` (Buchungen ohne Zahlungsbetrag
   zählen nicht). Kein Label, wenn `|W| < 4` oder `B` keinen Zahlungsbetrag `w` hat. Sonst `m` = Median(W),
   `d` = MAD(W):
   - `d = 0`: Label, wenn `|w − m| × 100 > |m| × 50` **und** `|w − m| ≥ 2000` (20,00 €). Text:
     `Der Betrag <w> weicht stark von den bekannten Buchungen von „<Name>“ ab. Alle <k> bestätigten Zahlungen
     lauten auf <m>.`
   - `d > 0`: Label, wenn das robuste z von `w` gegen (`m`, `d`) stark ist (≥ 350 oder unbestimmt). Text:
     `Der Betrag <w> weicht stark von den bekannten Buchungen von „<Name>“ ab (Median <m>, Streuung <d>,
     robustes z <z>, <k> bestätigte Buchungen).` mit `z` als `x,yy` (bzw. `ohne messbare Streuung`).
   - Beträge im Text: `[-]T.TTT,cc €` (Tausenderpunkt, Komma, zwei Nachkommastellen); `k = |W|`.
   - Sonst kein Label.

`grund` ∈ {`empfaenger`, `betrag`}; Tests prüfen `grund` exakt und vom Text nur, dass er den Empfängernamen
enthält und mit `Der ` beginnt (Wortlaut ist nicht Vertrag).

### 1.3 Wirkung von Bestätigen (D-159)

Es gibt keinen neuen Endpunkt. Wird eine Buchung (z. B. per `PATCH` oder Mehrfachänderung) auf `bestaetigt`
oder `abgeglichen` gesetzt, trägt sie danach kein `verdacht`. Weil die Regel über alle Buchungen des Empfängers
rechnet, kann sich das Label **anderer** Buchungen desselben Empfängers dadurch ändern (z. B. entfällt „Empfänger
unbekannt“, sobald eine Buchung bestätigt ist).

## 2. Bestätigung durch Personen an Empfängern (D-155, D-156)

Personen werden als gewöhnliche Tags abgebildet (Namen sind Sache der Oberfläche, M28). REST kennt nur Tags an
Empfängern:

- `PATCH /api/empfaenger/{id}` akzeptiert zusätzlich `tag_ids` (Liste ganzer Zahlen, höchstens 50, eindeutig;
  Duplikate → 422 `validierung`; `null` → 422). Die Liste **ersetzt** die Tags des Empfängers; `[]` entfernt
  alle. Unbekannte Tag-IDs → 422 `referenz_unbekannt` mit `details = {"tag_ids": [fehlende, aufsteigend]}`.
  Prüfreihenfolge wie bisher bei `PATCH`: Körper (422 `validierung`) → Empfänger vorhanden (404) → übrige
  Prüfungen wie M3 → Tags (`referenz_unbekannt`). Ohne `tag_ids` bleiben die Tags unverändert.
- `POST /api/empfaenger` kennt `tag_ids` **nicht** (unverändert, unbekanntes Feld → 422).
- Antwortschema `Empfaenger` (alle Empfänger-Antworten, auch Liste und Zusammenführen): optionales Feld
  `tags` = Liste `TagKurz` (`{id, name}`) sortiert nach (`name`, `id`). Das Feld **fehlt**, wenn der Empfänger
  keine Tags hat (damit Antworten ohne Tags unverändert bleiben).
- **Zusammenführen** (`POST /api/empfaenger/{id}/zusammenfuehren`): Das Ziel erhält die Vereinigung seiner Tags
  und der Tags aller Quellen.
- **Tag löschen** (`DELETE /api/tags/{id}`): entfernt den Tag auch von allen Empfängern, in derselben Änderung.
- **Protokoll:** Aktion `empfaenger_aendern` (bzw. `empfaenger_zusammenfuehren`, `tag_loeschen`) wie bisher,
  Quelle `manuell`, keine Gruppe; die Protokollform des Empfängers (`EmpfaengerZustand`) trägt `tags` genau dann,
  wenn er Tags hat. Rückgängig/Wiederholen stellen die Tags her. Rückgängig des **Anlegens** eines Tags, den
  inzwischen ein Empfänger außerhalb dieser Änderung trägt → 409 `rueckgaengig_konflikt` (wie bei Buchungen,
  `protokoll.md` 6).
- **Sicherung:** Empfänger-Tags gehören zum Buchbestand (Schemaversion der Sicherungsdatei 7; ältere Versionen
  werden ohne Empfänger-Tags gelesen). Keine neue Objektart; `anzahl` unverändert; die Inhaltsprüfsumme rechnet
  mit den Protokollformen (Empfänger mit `tags` nur bei Vorhandensein), Prüfsummen ohne Empfänger-Tags bleiben
  gleich. Rundreise-Test mit Empfänger-Tags.

Bestätigen einer **Buchung** durch eine Person ist REST-seitig eine gewöhnliche Mehrfachänderung (Tag hinzu und,
bei Status `importiert`, Status `bestaetigt`, in **einer** Anfrage `POST /api/buchungen/mehrfach/aendern`, damit
eine Änderung). Kein neuer Vertrag; nur ein Szenariotest: Nach der Änderung trägt die Buchung den Tag, Status
`bestaetigt`, und mit `verdacht=ja` kein `verdacht`.

## 3. Neue Filter der Buchungsliste (D-158)

`GET /api/buchungen` (und alle Stellen, die dieselben Filter annehmen, z. B. Export, Mehrfachauswahl „alle
gefilterten“, sofern sie die Filter der Buchungsliste übernehmen) kennt zusätzlich:

| Parameter | Typ | Wirkung |
| --- | --- | --- |
| `zweck_gleich` | Text, Länge ≥ 1 | `norm(verwendungszweck) = norm(Wert)` (keine Trimmung) |
| `zweck_leer` | Wahrheitswert | nur Buchungen mit Verwendungszweck exakt `""`; hat Vorrang vor `zweck_gleich` (beide gesetzt → nur `zweck_leer` wirkt) |
| `zweck_aehnlich` | Text, Länge ≥ 1 | siehe unten |
| `empfaenger_aehnlich` | Text, Länge ≥ 1 | siehe unten |

Alle Filter sind mit den übrigen UND-verknüpft; der bisherige Filter `verwendungszweck` (Teilzeichenkette)
bleibt. Leerer Text → 422 `validierung`.

- **Wörter eines Textes:** `norm(Text)` an jedem Zeichen außerhalb `[a-z0-9]` getrennt; behalten werden Teile
  mit mindestens 4 Zeichen, die nicht nur aus Ziffern bestehen, ohne Doppelte.
- **`zweck_aehnlich`:** Hat der Wert mindestens ein Wort, trifft jede Buchung, deren `norm(verwendungszweck)`
  mindestens eines dieser Wörter **als Teilzeichenkette** enthält (kein Wortgrenzen-Vergleich: „miete“ trifft
  „Mietezahlung“ und „Kaltmiete“). Hat der Wert kein Wort (z. B. „123“, „ab“), gilt `norm(verwendungszweck) =
  norm(Wert)`.
- **`empfaenger_aehnlich`:** Trifft Buchungen, deren Empfänger ähnlich ist. Ein Empfänger ist ähnlich, wenn sein
  Name **oder einer seiner Aliase** mit dem Wert ähnlich ist. Zwei Texte sind ähnlich, wenn beide `ekey` nicht
  leer sind und ihr gemeinsamer Anfang (längstes gemeinsames Präfix der `ekey`) **mindestens 4 Zeichen** lang ist.
  Folge: Namen mit `ekey` kürzer als 4 Zeichen sind mit nichts ähnlich, auch nicht mit sich selbst. Buchungen
  ohne Empfänger werden nie getroffen. Kein ähnlicher Empfänger → leere Liste.

Unbekannte Parameter verhalten sich wie bisher bei der Buchungsliste.

## 4. Dubletten: anlegen und vorschlagen (D-165)

### 4.1 `POST /api/dubletten`

Körper `{"buchung_ids": [Id, …]}`, Pflicht, 2–50 eindeutige ganze Zahlen; weitere Felder → 422.
Prüfreihenfolge: Körper (422 `validierung`) → alle Buchungen vorhanden (sonst 422 `referenz_unbekannt`,
`details = {"buchung_ids": [fehlende aufsteigend]}`). Antwort **201** `Dublettenverdacht` (Schema unverändert):

- `buchung_id` = erste ID der Liste (sie wird beim Zusammenführen entfernt), `kandidat_ids` = die übrigen
  (aufsteigend), `grund` = `aehnlich` bei zwei IDs, `mehrdeutig` bei mehr, `status` = `offen`, `erstellt_am` =
  App-Uhr.
- Keine weitere Prüfung (gesperrte/abgestimmte Buchungen, bestehende Verdachte): angelegt wird immer; Sperren
  greifen erst beim Auflösen wie bisher.
- Auflösen über den bisherigen Endpunkt `POST /api/dubletten/{id}/aufloesen` (unverändert).
- **Protokoll:** neue Aktion `dublette_anlegen` („Dublettenverdacht angelegt“), Quelle `manuell`, keine Gruppe,
  ein Eintrag Objekt `verdacht` `angelegt`. Rückgängig entfernt den Verdacht; Rückgängig, nachdem er aufgelöst
  wurde → 409 `rueckgaengig_konflikt`. Eintrag in `protokoll.md` 4 und Protokolltests (T 3.5/3.6).
- Sicherung: wie bestehende Verdachte (keine Änderung).

### 4.2 Vorschläge in `GET /api/dubletten`

Neuer Parameter `vorschlaege` ∈ {`ja`, `nein`} (Vorgabe `nein`; jeder andere Wert → 422 `validierung`;
kontor-app D-169). **Ohne** `vorschlaege=ja` ist die Antwort
unverändert. Mit `vorschlaege=ja` und `status` fehlend oder `offen` hängt die Antwort nach den gespeicherten
Verdachten Einträge `DublettenVorschlag` an (bei `status=zusammengefuehrt|keine_dublette`: keine Vorschläge):

`{"vorschlag": true, "id": null, "buchung_id", "kandidat_ids", "grund": "gleich", "status": "offen",
"erstellt_am": null}`.

Regel: Gruppen von Buchungen mit **gleichem Datum, gleicher Empfänger-ID (nicht null) und gleichem
Zahlungsbetrag** (Vorzeichen zählt; Buchungen ohne Zahlungsbetrag zählen nicht). Ein Paar gilt als **bewertet**,
wenn beide Buchungen in einem gespeicherten Verdacht (beliebiger Status, `buchung_id` oder `kandidat_ids`)
vorkommen. Je Gruppe mit mindestens zwei Buchungen:

- ist **kein** Paar der Gruppe bewertet → **ein** Vorschlag mit allen Buchungen: `buchung_id` = kleinste ID,
  `kandidat_ids` = übrige aufsteigend;
- sind einige Paare bewertet → **je unbewertetem Paar** ein Vorschlag (`buchung_id` = kleinere ID,
  `kandidat_ids` = [größere]);
- alle bewertet → nichts.

Vorschläge sind nach (`buchung_id`, `kandidat_ids`) sortiert. Sie werden nicht gespeichert, ändern nichts, haben
keine Protokoll- und keine Sicherungswirkung und lassen sich nicht direkt auflösen (der Weg ist 4.1 mit den IDs
des Vorschlags). Vorschläge ersetzen die Prüfung beim Import/bei der Synchronisation nicht.

## 5. Mail-Liste

Siehe `mail.md` 6.6.

## 6. Statistische Analyse (D-145), experimentell – entfällt ab M32 (`sammel3.md` 3, E-298)

`GET /api/statistik?konto_id=<id>[&stichtag=YYYY-MM-DD]` – nur lesend, kein Zustand. Im Vertrag als
**experimentell** markiert: Struktur und Fehler sind verbindlich (`kern`), die fachlichen Inhalte (welche Reihen,
Rauschen, Ausreißer) nicht (Tests dazu nicht `kern`, dürfen sich mit dem neuen Konzept ändern).

Prüfreihenfolge: Parameter (`konto_id` Pflicht, ganze Zahl ≥ 1; `stichtag` gültiges Datum; jeder andere
Parameter → Fehler „Unbekannter Parameter.“; alle Parameterfehler gesammelt in **einem** 422 `validierung`) →
Konto vorhanden (404 `nicht_gefunden`) → Konto ist Bestandskonto (`girokonto`, `sparkonto`, `kreditkonto`,
sonst 422 `konto_ungueltig`). Vorgabe `stichtag` = heute (App-Uhr).

Antwort 200 (`Statistik`):
`{experimentell: true, konto: {id, name, art}, stichtag, schwellen: {abstand_mad_prozent: 15,
betrag_mad_prozent: 10, ausreisser_z_hundertstel: 350, mindestens_regelmaessig: 4}, ausgeschlossen:
{umbuchungen, umbuchungen_summe, tilgung_ohne_zins}, reihen: [Reihe], fixkosten: {kategorien: […],
summe_jahresrate, summe_letzte_zwoelf_monate}, rauschen: [Rauschen], ungewoehnlich: [Ausreisser]}`. Alle
Beträge ganze Cent.

- `Reihe`: `{status ∈ {regelmaessig, moeglich, kandidat}, grund, bezeichnung, empfaenger ({id, name} | null),
  richtung ∈ {ausgabe, einnahme}, rhythmus (null | woechentlich | vierzehntaegig | monatlich | vierteljaehrlich |
  jaehrlich), anzahl, abstand_median_tage, abstand_mad_tage, betrag_median, betrag_mad, betrag_quartil_unten,
  betrag_quartil_oben, kosten_median, jahresrate, kategorie ({id, name, art} | null), erste, letzte,
  buchung_ids}` (+ weitere Felder zulässig).
- `Rauschen`: `{kategorie: {id, name, art}, monate, anzahl_buchungen, median, band_unten, band_oben,
  band_stabil}`.
- `Ausreisser`: `{buchung_id, datum, betrag, empfaenger, grund, basis, z_hundertstel, kategorie}`; nach (`datum`,
  `buchung_id`, `grund`) aufsteigend.
- Schema mit `additionalProperties: true` in den Unterobjekten (experimentell); die Wurzel und die genannten
  Pflichtfelder sind fest.

Nicht-kern-Inhaltsprüfung (ein Szenario): Eine Gegenpartei mit 6 monatlichen Abbuchungen gleichen Betrags
(Abstände 28–31 Tage) ergibt eine `reihe` mit `status = regelmaessig`, `rhythmus = monatlich`, `richtung =
ausgabe`, `anzahl = 6`, `jahresrate = kosten_median × 365 // abstand_median_tage` (sofern so gerundet; nur grobe
Prüfung ±1 %). Umbuchungen auf ein anderes Bestandskonto erscheinen nicht in `reihen`, sondern in
`ausgeschlossen.umbuchungen`.

Der Endpunkt ist geschützt (Anmeldung, M7) wie alle neuen Endpunkte.

## 7. Datenbank und Migration

Eine Datenbank aus 0.14 wird beim Start ohne Datenverlust übernommen; danach sind Empfänger-Tags möglich. Nur
beobachtbar: Nach Start mit einer älteren Datenbank liefern alle bisherigen Endpunkte dieselben Daten.

## 8. Split-Ausgleich, Vorlagen aus dem Split, Vorlagenregel (D-162 bis D-164)

Rein Oberfläche über bestehende Endpunkte (`POST/PATCH /api/vorlagen` wie M4); keine neue REST-Regel. Gehört zu
M28. Die Aussage „Eine Vorlage trifft, wenn Empfänger und Splitbetrag passen“ ist die bestehende Vorlagenregel
(`vorlagen.md`) mit Bedingung `empfaenger gleich` und Betrag; kein neues Verhalten.
