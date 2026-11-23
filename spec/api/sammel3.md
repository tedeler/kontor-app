# Meilenstein 32: Sammelbranch `feature/sammel3` (Definition 4)

Übernahme der Meilenstein-Definition 4 vom 2026-11-22
(`spec/definitionen/definition-4-sammelbranch-sammel3.md`, Entscheidungen der
Implementierung D-218 bis D-239, mit den Anlagen `ANBIETER.md`, `HTTPS.md`,
`TESTINSTANZ.md` unter `spec/definitionen/anlagen/`). Der Auftraggeber hat auf
eine gesonderte Freigabe verzichtet („direkt weiter“, E-293). Gliederung nach
den Abschnitten der Definition; maßgeblich ist ihr Endstand. Die Oberfläche
steht in `oberflaeche.md` 41, REST in `openapi.yaml` 2.25.0 (E-294).

**Nicht rückwärtskompatibel** (E-029 gilt hier nicht): Kontonamen sind je Ebene
eindeutig (1), die Standardkategorie je Empfänger entfällt (2), die statistische
Analyse entfällt (3), die PayPal-Zuordnung ändert `erwartungen.md` 5.2 (9.2),
die Erfolgsmeldung mit „Rückgängig“ ist ausgeschaltet (`oberflaeche.md` 41.9),
das Handy-Kontoblatt klappt Filter und Gruppierung ein (`oberflaeche.md` 41.11).
Welche früheren Tests deshalb geändert sind, steht in E-307.

Prüfmerkmale und Lesarten: E-295 bis E-306. Was hier als **Festlegung** steht,
nennt die Definition nicht; die Implementierung richtet sich danach oder meldet
einen Widerspruch als Text.

## 1. Kontonamen je Ebene eindeutig (D-218) [kern]

Ersetzt `datenmodell.md` 2 („Keine Eindeutigkeit gefordert“) und die
Namensregel 2 für Konten anderer Klassen in `datenmodell.md` 10.3 (es gibt
höchstens noch ein passendes Konto).

### 1.1 Regel

- Unter demselben Elternkonto ist ein Name nur einmal erlaubt. Verglichen wird
  `name.strip().casefold()` (ohne Leerraum am Rand, ohne Unterschied von Groß-
  und Kleinschreibung; Umlaute zählen als verschieden, Festlegung E-295).
- Auf der obersten Ebene (`eltern_id = null`) gilt das **je Klasse**
  (`bestand`, `aufwand`, `ertrag`, `eigenkapital`): „Zinsen“ als Aufwand und als
  Ertrag sind nebeneinander möglich, zwei Bestandskonten „Giro“ (auch
  `girokonto` und `sparkonto`) nicht. Unterkonten verschiedener Eltern dürfen
  gleich heißen.
- Gilt für alle Konten, auch geschlossene und technische.

### 1.2 Ablehnen

Jede protokollierte Änderung, die Konten berührt, wird an ihrem Ende geprüft.
Entstünden zwei gleichnamige Geschwister, wird sie mit **409
`konto_existiert`** abgelehnt, ohne Wirkung und ohne Eintrag im Protokoll;
`details.konto_ids` ist eine nicht leere Liste von Konto-IDs, die die
Kollision bilden (Festlegung E-295: mindestens das vorhandene gleichnamige
Konto; neu angelegte Konten haben keine ID und fehlen). Betroffen:

| Vorgang | Endpunkt |
| --- | --- |
| Anlegen | `POST /api/konten` |
| Umbenennen, Verschieben | `PATCH /api/konten/{id}` (`name`, `eltern_id`) |
| Löschen mit hochrutschenden Unterkonten | `POST /api/konten/{id}/loeschen` (`loeschen.md`), auch mit `trocken` |
| Zusammenführen mit mitwandernden Unterkategorien | `POST /api/kategorien/zusammenfuehren` (`alfbanco.md` 5), auch mit `trocken` |
| Rückgängig | `POST /api/aenderungen/{id}/rueckgaengig`, `POST /api/aenderungen/rueckgaengig` |

Prüfreihenfolge: alle bisherigen Prüfungen des Vorgangs zuerst (bei Rückgängig
Zustand und Bezüge, `protokoll.md` 6, 409 `rueckgaengig_konflikt`), danach die
Namensprüfung (E-295). Ein `PATCH` mit dem eigenen Namen in anderer
Schreibweise (`"giro"` statt `"Giro"`) ist erlaubt.

### 1.3 Bereinigen

Beim Start der Anwendung (Altbestand), nach jedem Import (KMyMoney, GnuCash,
ALF-BanCo) und nach dem Einspielen einer Sicherung werden gleichnamige
Geschwister bereinigt:

- **Kategorien** (`aufwand`, `ertrag`) werden in die mit der kleinsten ID
  zusammengeführt: Buchungen, Regeln, Vorlagen und Unterkategorien wandern mit;
  entstehen dadurch neue gleichnamige Geschwister, werden auch sie bereinigt.
- **Bestandskonten, Eigenkapitalkonten und Kategorien mit Kreditbezug** werden
  nicht zusammengeführt, sondern umbenannt: das spätere bekommt den Zusatz
  „ (2)“, „ (3)“ … (Leerzeichen, Ziffer in runden Klammern; erste freie Zahl).
- **Altbestand:** eine Änderung (Quelle `manuell`, Aktion
  `kategorien_zusammenfuehren`, Beschreibung „Gleichnamige Konten bereinigt“);
  ihr Rückgängig wird nach 1.2 abgelehnt. Nicht prüfbar (E-295).
- **Import:** die Bereinigung gehört zur Änderung des Imports (Festlegung E-295);
  Warnungen `konto_zusammengefasst` (zusammengeführte Kategorie) bzw.
  `konto_umbenannt` (umbenanntes Konto), `referenz` = Name des betroffenen
  Kontos aus der Datei. Die zusammengeführte Kategorie behält keine eigene
  `extern_id`; ein erneuter Import derselben Datei legt sie deshalb kurz an und
  führt sie wieder zusammen: Bestand danach unverändert, `kategorien_neu`
  zählt sie aber erneut (Idempotenz T 3.7 gilt hier nur für den Bestand).
- **Einspielen:** die Bereinigung gehört zur Änderung `sicherung_einspielen`.
  Eine Sicherung aus Kontor enthält keine gleichnamigen Geschwister; nicht
  geprüft (E-295).

### 1.4 Technische Konten und Synchronisation

- „Unkategorisiert“ und „Korrekturen“: Gibt es beim ersten Bedarf schon ein
  gleichnamiges Eigenkapitalkonto ohne `extern_id` auf der obersten Ebene, wird
  es übernommen (es erhält die Kennung `kontor:unkategorisiert` bzw.
  `kontor:korrektur`, Festlegung E-295) statt ein zweites anzulegen.
- Ein bei der Synchronisation neu angelegtes Bankkonto bekommt bei
  Namensgleichheit den Zusatz „ (2)“ (bzw. die erste freie Zahl).

## 2. Empfänger: Standardkategorie entfällt, Konten und Anzahlen (D-219, D-220, D-236/10) [kern]

### 2.1 Standardkategorie entfällt

Ersetzt `buchhaltungspflege.md` 2.5 und die Stufe „Standardkategorie“ in
`kategorisierung.md` 6/7, `synchronisation.md` 14, `lernmodell.md` 5,
`vorlagen.md` 4 und `buchhaltungspflege.md` 3 (Erfassen).

- `standardkategorie_id` bleibt Feld der Empfängerform (Antwortschema
  `Empfaenger`, Protokollform `EmpfaengerZustand`) und ist in jeder Antwort
  `null`.
- `POST /api/empfaenger` und `PATCH /api/empfaenger/{id}` nehmen das Feld
  weiter an: `null` ist ohne Wirkung, jeder andere Wert (auch die ID einer
  Kategorie) → **422 `kategorie_ungueltig`**, ohne Wirkung. Ein nicht
  ganzzahliger Wert bleibt 422 `validierung`.
- Stufenfolge neuer Bankumsätze: Kreditrate → Vorlage → Regel → Lernmodell (nur
  `lernmodell_automatisch`) → „Unkategorisiert“. Erfassen ohne `kategorie_id`
  bucht auf „Unkategorisiert“ ohne Vorschlag (Lesart E-296: Regeln gelten bei
  von Hand angelegten Buchungen weiterhin nicht, `kategorisierung.md` 8).
- Konto löschen und Kategorien zusammenführen ändern keine Empfänger mehr:
  `empfaenger_geaendert` ist `[]` (`loeschen.md` 3.5, `alfbanco.md` 5).
- Vorschläge mit `quelle = "standardkategorie"` aus älteren Beständen bleiben
  gültig (Annehmen, Ablehnen wie bisher); neu entstehen keine.
- **Umwandlung** beim Start und beim Einspielen älterer Sicherungen: aus jeder
  Standardkategorie wird die Regel „Empfänger ist <Name>“ → Kategorie am Ende
  der Regelliste (Start: eine Änderung „Standardkategorien in Regeln
  umgewandelt“, Aktion `regel_anlegen`). Nicht prüfbar (E-296, wie E-273).
- Spalte der Datenbank und der Sicherungsdatei bleiben (leer).

### 2.2 `GET /api/empfaenger/{id}/konten`

Nur lesend. 200: Liste `[{konto_id, anzahl}]` (Schema `EmpfaengerKonto`) über
die Bestandskonten, auf denen mindestens eine Buchung des Empfängers einen
Split hat; `anzahl` = Zahl dieser Buchungen mit Split auf dem Konto (eine
Buchung zählt je Konto einmal). Reihenfolge `anzahl` absteigend, bei Gleichstand
`konto_id` aufsteigend (Festlegung E-297: „die meistbenutzten zuerst“). Ohne
Buchungen `[]`. Unbekannter Empfänger → 404 `nicht_gefunden`.

### 2.3 `GET /api/empfaenger/anzahlen`

Nur lesend. 200: Liste `[{empfaenger_id, anzahl}]` (Schema
`EmpfaengerAnzahl`), `anzahl` = Zahl der Buchungen mit diesem Empfänger
(≥ 1); Empfänger ohne Buchung fehlen. Reihenfolge `empfaenger_id` aufsteigend
(Festlegung E-297). Keine Parameter; ein unbekannter Parameter wird wie bei
anderen Listen behandelt (nicht geprüft).

## 3. Statistische Analyse entfällt (D-221) [kern]

Ersetzt `sammel.md` 6 und `oberflaeche.md` 37.12 (Seite `/statistik`):
`GET /api/statistik` → 404 `nicht_gefunden` (Fehlerschema), `/statistik` →
HTTP 404 (keine Hülle). Navigationseintrag `navlink-statistik` und
Palettenbefehl `befehl-gehe-statistik` entfallen. Schema `Statistik` entfällt.

## 4. Dubletten: zur Buchung springen (D-222, D-236/11)

Nur Oberfläche (`oberflaeche.md` 41.3).

## 5. Bestätigung mit Tag „B-<Name>“ (D-223)

REST unverändert (`sammel.md` 2: Personen sind gewöhnliche Tags). Die
Oberfläche bestätigt mit dem Tag „B-Torsten“ bzw. „B-Tina“
(`oberflaeche.md` 41.4). Umbenennen vorhandener Tags „Torsten“/„Tina“ beim Start
(eine Änderung, Aktion `tag_umbenennen`) und beim Einspielen älterer
Sicherungen; gibt es das neue Tag schon, wandern die Zuordnungen dorthin. Nicht
prüfbar (E-296).

## 6. Kontoblatt, 7. Tags-Seite

Nur Oberfläche (`oberflaeche.md` 41.5 bis 41.7).

## 8. Mail-Blatt und Mail-Ansicht (D-226 bis D-229, D-236/9) [kern]

### 8.1 Suche

`GET /api/mail/nachrichten` mit Parameter `suche` (Zeichenkette): Der Text wird
an Leerraum in Wörter geteilt; eine Nachricht passt, wenn **jedes** Wort in
`absender`, `betreff` oder `text` vorkommt (je Wort genügt eines der Felder),
verglichen mit `norm` (`datenmodell.md` 1: `casefold`, Umlaute als `ae`,
`oe`, `ue`). Leerer oder nur aus Leerraum bestehender Text filtert nicht
(Festlegung E-299). UND-verknüpft mit `postfach_id` und `zuordnung`; `gesamt`
und Seiten beziehen sich auf die gefilterte Menge, `stand` bleibt wie
`mail.md` 6.6 (ohne `suche`, Festlegung E-299).

### 8.2 Mail von Hand zuordnen

`POST /api/mail/nachrichten/{id}/buchung` mit genau `{buchung_id: int}`:

- Hängt die Mail als Dokument an die Buchung wie `POST /api/dokumente/aus-mail`
  (`dokumente.md` 2.2) und vermerkt sie als „von Hand“ zugeordnet
  (Betriebszustand wie `erwartungen.md` 14.4, leere Nummer). Eine Änderung
  `manuell`/`dokument_aus_mail` (Einträge wie dort).
- Antwort **201 `Dokument`** (Festlegung E-299, wie `aus-mail`).
- Prüfreihenfolge: Nachricht unbekannt → 404 `nicht_gefunden`; Körper (kein
  Objekt, Feld fehlt, kein int, unbekanntes Feld) → 422 `validierung`; Buchung
  unbekannt → 404 `nicht_gefunden` (wie `aus-mail`).
- Hängt an der Buchung schon ein Dokument gleichen Inhalts, entsteht keines;
  der Vermerk wird trotzdem gesetzt (Festlegung E-299; geprüft wird nur, dass
  kein zweites Dokument entsteht).
- In der Mail-Liste gilt die Mail danach als `zugeordnet` (Filter
  `zuordnung`, `stand.zugeordnet`) und trägt die Buchung in `angehaengt`
  (`erwartungen.md` 14.5) mit `nummer = ""`. Das Feld `angehaengt` steht
  bei Mails mit solchem Vermerk unabhängig von `mail_bestellnummer`
  (Festlegung E-299).
- Wird das Dokument von der Buchung gelöst
  (`DELETE /api/dokumente/{id}/buchungen/{buchung_id}`), entfällt der Vermerk:
  die Mail ist wieder nicht zugeordnet (sofern sonst nichts zuordnet).
- Der Auswahldialog (14 Tage vor bis 30 Tage nach der Mail, „Betrag passt“)
  ist Sache der Oberfläche; er liest die Buchungsliste (kein eigener
  Endpunkt).

### 8.3 Betrag der angehängten Buchungen

Jeder Eintrag von `angehaengt` trägt zusätzlich `betrag` (int, Cent) = Summe der
Splits der Buchung auf Bestandskonten (D-236/9). `nummer` ist ab M32 eine
beliebige Zeichenkette (Bestellnummer, Kennung eines Anbieters nach 9, leer bei
Zuordnung von Hand).

### 8.4 Gruppieren

`GET /api/mail/nachrichten?gruppieren=ja` (Werte `ja`, `nein`; Vorgabe `nein`;
anderer Wert → 422 `validierung`):

- **Gruppe:** Mails, die dieselbe Buchung oder dieselbe erwartete Zahlung
  betreffen, auch mittelbar über eine dritte Mail (Zusammenhangskomponenten),
  gleich über welchen Weg (Bestellnummer/Kennung, erwartete Zahlung, von Hand).
- **Reihenfolge:** Eine Gruppe steht an der Stelle ihrer ersten Mail (nach der
  gewählten `reihenfolge`), die übrigen Mails der Gruppe direkt dahinter in
  derselben Reihenfolge. Gruppiert wird innerhalb der gefilterten Menge
  (`postfach_id`, `zuordnung`, `suche`) vor dem Teilen in Seiten.
- Jeder Eintrag trägt dann `gruppe` = ID der ersten Mail seiner Gruppe; eine
  Mail ohne weitere Mail in ihrer Gruppe trägt `null` (Lesart E-299; die
  Tests lassen bei solchen Mails auch die eigene ID zu).
- Ohne den Parameter (oder mit `nein`) Reihenfolge und Antwort wie bisher, ohne
  Feld `gruppe`.

### 8.5 Bilder fremder Server

- `GET /api/dokumente/{id}/mail/html?bilder=ja` (Werte `ja`, `nein`; Vorgabe
  `nein`; anderer Wert → 422 `validierung`, Festlegung E-300): Bildadressen mit
  `http://`, `https://` und `//` (als `https://`) bleiben in `<img src>`,
  `background` und `url(…)` in Stilen stehen. Die Inhaltsrichtlinie ist die von
  `dokumente.md` mit `img-src data: https: http:` statt `img-src data:`; alles
  andere bleibt wie bisher (keine Skripte, kein `srcset`, kein `@import`, keine
  Schriften von außen, `sandbox`, kein Referrer).
- Ohne `bilder=ja` unverändert: fremde Bildadressen werden entfernt.
- `GET /api/dokumente/{id}/mail/bilder` → 200 `{"anzahl": n}` (Schema
  `MailBilder`) = Zahl der Bildadressen fremder Server, die `bilder=ja` stehen
  ließe (`data:`- und `cid:`-Bilder zählen nicht). Kein Mail-Dokument → 409
  `keine_mail`, unbekannt → 404 (wie `…/mail/html`).
- Der Kontor-Server ruft nie selbst fremde Adressen ab.

## 9. Anbieter-Beschreibungen und PayPal (D-230, D-232) [kern]

### 9.1 Beschreibungen

- Format: `spec/definitionen/anlagen/ANBIETER.md` (verbindlich für Aufbau,
  Bausteine, Rollen und Zuordnung). Mitgeliefert `amazon` und `paypal`; die
  Erkennung nach `erwartungen.md` 2.3/2.4 bleibt das Verhalten der
  mitgelieferten Beschreibungen.
- Konfiguration `anbieter_verzeichnis` (`KONTOR_ANBIETER_VERZEICHNIS`, Pfad oder
  `None`, Vorgabe `None`; `python-api.md` 23): Dateien `*.toml` darin werden
  beim nächsten Abgleich gelesen, geänderte ohne Neustart. Eine Datei mit dem
  `name` eines mitgelieferten Anbieters ersetzt diesen. Ein nicht vorhandenes
  Verzeichnis ist wie keines (Festlegung E-301).
- Eine fehlerhafte Datei (TOML ungültig, Pflichtangabe fehlt, Ausdruck
  ungültig oder länger als 500 Zeichen) wird übergangen; andere Beschreibungen
  wirken weiter. Ausgewertet werden höchstens 200 000 Zeichen eines Textes.
- `Erwartung.anbieter` ist der `name` der Beschreibung (Kleinbuchstaben,
  Ziffern, `_`), `grund` bleibt `bestellung` oder `paypal` (aus `art.grund`).
  Schlüssel `<anbieter>:<mailart>:<kennung>` (intern).
- Mit `mail_bestellnummer` hängt jede Mail mit einer Kennung nach `bank.kennung`
  an jeder Buchung mit derselben Kennung (`erwartungen.md` 14 verallgemeinert);
  PayPal hat ab D-232 keine `bank.kennung` mehr.

### 9.2 PayPal: Betrag, Zeitfenster, Händler (ersetzt `erwartungen.md` 5.2 für PayPal)

Für Erwartungen mit `anbieter = "paypal"` (Beschreibung mit
`haendler_noetig = true`, `tage_vor = tage_nach = 5`) gilt im automatischen
Abgleich statt des zweiten Punkts von `erwartungen.md` 5.2:

- Zugeordnet wird, wenn es **genau eine** freie Buchung mit `|Betrag| =
  offen_betrag`, passendem Vorzeichen, genau einem Bestandskonto-Split und Datum
  von `datum − 5` bis `datum + 5` Tage gibt, die den **Händler der Mail in
  Teilen** nennt (Verwendungszweck oder Empfänger): ein Wort des Händlernamens
  mit mindestens 4 Zeichen irgendwo im Text (ohne Groß/Klein), kürzere nur als
  ganzes Wort; Allerweltswörter („Shop“, „GmbH“ …) zählen nicht; ein gekürzter
  Name der Bank zählt, wenn er der Anfang des zusammengeschriebenen Namens ist
  (`MEDIAMARKTSATU` ↔ „Media Markt Saturn“).
- Andere Buchungen gleichen Betrags **ohne** den Händler stören nicht mehr;
  zwei passende Buchungen bleiben zur Bestätigung von Hand.
- Nennt die Mail keinen Händler (Händler „PayPal“), wird nichts automatisch
  zugeordnet.
- Kennung (Transaktionscode) und Referenz der Erwartung wirken weiter nach
  `kennung_passt` (erster Punkt von 5.2), Festlegung E-302.
- Die Kandidatenliste (`erwartungen.md` 5.1, 6.4) bleibt unverändert.

## 10. Meldung mit „Rückgängig“ ausgeschaltet (D-234)

Nur Oberfläche (`oberflaeche.md` 41.9).

## 11. Konfiguration ansehen (D-235) [kern]

`GET /api/konfiguration` (geschützt wie alle Endpunkte, nur lesend, kein
Protokoll) → 200 `Konfiguration`:

- `umgebung`: je Variable des Prozesses mit Präfix `KONTOR_` und für
  `CREDENTIALS_DIRECTORY` ein Eintrag `{variable, wert, verborgen, bekannt}`;
  `bekannt` = Kontor kennt die Variable (sonst „unbekannt“ in der Oberfläche).
  Andere Variablen des Prozesses erscheinen nicht. Reihenfolge nicht
  festgelegt.
- `wirksam`: je Einstellung von `KontorConfig` ein Eintrag `{name, variable,
  gesetzt, wert, vorgabe, geaendert, verborgen}`: `name` = Feldname,
  `variable` = Umgebungsvariable (`KONTOR_` + Name in Großbuchstaben, wo
  `python-api.md` nichts anderes nennt), `gesetzt` = Variable in der Umgebung
  vorhanden, `wert` = geltender Wert der laufenden App, `vorgabe` = Vorgabe,
  `geaendert` = Wert weicht von der Vorgabe ab. Form von `wert`/`vorgabe`
  (JSON-Wert oder Text) frei (Festlegung E-304).
- **Nie ausgegeben** (dann `verborgen = true` und der Wert erscheint nirgends in
  der Antwort): Werte von Variablen bzw. Einstellungen, deren Name nach einem
  Geheimnis klingt (enthält `secret`, `token` außer `…_token_url`, `passwort`,
  `password`, `pin` außer `bank_pin_quelle`), sowie `fints_benutzer` und
  `fints_kunden_id`.
- Gezeigt wird die Umgebung des Prozesses, nicht die Datei.

## 12. UX-Durchgang (D-236)

Nur Oberfläche (`oberflaeche.md` 41), außer 8.3 (Betrag) und 2.3 (Anzahlen).

## 13. Änderungsprotokoll: Einzelheiten (D-237)

Nur Oberfläche (`oberflaeche.md` 41.8); Daten aus `GET /api/aenderungen/{id}`
(unverändert).

## 14. Geplante Zahlungen (D-238) [kern]

Ergänzt `erwartungen.md` 6.2 und 6.3. Von Hand angelegte Erwartungen (Grund
`manuell`) heißen in der Oberfläche „Geplant“.

### 14.1 Wiederholung

- `POST /api/erwartungen` und `PATCH /api/erwartungen/{id}` nehmen zusätzlich
  `wiederholung` ∈ {`keine`, `monatlich`, `vierteljaehrlich`, `halbjaehrlich`,
  `jaehrlich`} und `wiederholung_bis` (Datum oder `null`).
- Nur für Grund `manuell`; sonst 422 **`wiederholung_nur_geplant`** (auch mit
  `keine`, Festlegung E-303). `wiederholung_bis` ohne bestehende oder
  gleichzeitig gesetzte Wiederholung (oder mit `keine`) → 422
  **`wiederholung_fehlt`**. Andere Werte/Typen → 422 `validierung`.
  Prüfreihenfolge: 404 → 422 `validierung` → 422 `wiederholung_nur_geplant`
  → 422 `wiederholung_fehlt` → bisherige Prüfungen (Festlegung E-303).
- `PATCH` mit `wiederholung = "keine"` entfernt die Wiederholung (samt Ende);
  `wiederholung_bis` allein ändert nur das Ende; `null` entfernt es.
- Antworten (Liste, Detail, alle schreibenden Endpunkte) und Protokollform
  tragen `wiederholung: {rhythmus, bis}` (`bis` Datum oder `null`) **nur**, wenn
  eine Wiederholung besteht. Ohne Wiederholung sehen Einträge aus wie bisher
  (auch Protokoll und Inhaltsprüfsumme der Sicherung).

### 14.2 Fortsetzung

- Wird eine Erwartung mit Wiederholung **erfüllt** (Zuordnung, Zustand
  `erfuellt`) oder als **`erledigt`** geschlossen, entsteht in derselben
  Änderung die nächste: gleiche Angaben (`richtung`, `haendler`, `betrag`,
  `beschreibung`, `kennung`, Wiederholung), `datum` um den Rhythmus weiter (1,
  3, 6, 12 Monate; am Tag im Monat der **ersten** Fälligkeit der Kette, in
  kürzeren Monaten am Monatsletzten), `frist` mit demselben Abstand in Tagen zu
  `datum` wie bei der Vorgängerin, Zustand `offen`, keine Buchungen, keine
  Mails, keine Dokumente.
- Keine Folge, wenn das neue `datum` nach `bis` läge oder die Erwartung schon
  eine Folge hat.
- `storniert` und `DELETE` beenden die Wiederholung (keine Folge).
- Wird die Erwartung wieder `offen` (Zustand zurück auf `offen`, Zuordnung
  gelöst, zugeordnete Buchung gelöscht), entfällt ihre noch **unberührte** Folge
  (seit dem Anlegen unverändert) in derselben Änderung.
- Rückgängig stellt Erwartung und Folge gemeinsam wieder her.

### 14.3 Zuordnung nach Namen

Für Erwartungen mit Grund `manuell` gilt im automatischen Abgleich (nur mit
`mail_abgleich`, `erwartungen.md` 4) statt des zweiten Punkts von 5.2: Das
Zeitfenster bleibt 5.1 (−3 bis +45 Tage). Zugeordnet wird die **einzige**
Buchung mit `|Betrag| = offen_betrag`, in deren Verwendungszweck oder
Empfänger der Händlername nach der Regel aus 9.2 (aussagekräftiges Wort) steht;
andere Buchungen gleichen Betrags ohne den Namen stören nicht. Gibt es zwei
solche Buchungen, wird nichts zugeordnet. `kennung_passt` wirkt wie bisher.

### 14.4 Vorschau

`GET /api/berichte/vorschau` enthält offene Erwartungen mit Grund `manuell`
samt ihrer Wiederholungen bis zum Ende des Zeitraums als Ereignisse mit
`quelle = "geplant"`, `konto_id = null`, `rhythmus` (Rhythmus oder
`einmalig`), `erwartung_id` und `datum` (Festlegung E-303; Lage der Ereignisse
in der Antwort frei). Schon fällige (`datum` < heute) stehen am Folgetag
(heute + 1). Sie zählen bei jeder Kontenwahl und werden nicht mit erkannten
Serien abgeglichen. Geschlossene Erwartungen (`erfuellt`, `guthaben`,
`storniert`, `erledigt`) erscheinen nicht.

### 14.5 Protokoll und Sicherung

- Die Wiederholung ist Teil der Objektart `erwartung` (kein neues Objekt). Die
  Folge erscheint als `erwartung` angelegt in der auslösenden Änderung
  (`erwartung_zuordnen`, `erwartung_zustand`, bei Abgleich `mail`/…), die
  entfallende Folge als `erwartung` gelöscht.
- Sicherungsdatei: `schemaversion` ≥ 10; Rundreise mit Wiederholungen; ältere
  Sicherungen werden ohne Wiederholungen gelesen (nicht prüfbar, E-273).

## 15. Betrieb nur über HTTPS (D-239)

- Ausgeliefert im Paket `kontor.betrieb`: `kontor-https.sh` (Unterbefehle
  `einrichten [--tailscale-installieren] [--name <name>] [--test-port <port>]`,
  `status`, `zurueck`) und das geänderte `kontor-test.sh`. Die ausgelieferte
  `kontor.env` bleibt bei `KONTOR_HOST=0.0.0.0` (`betrieb.md` 3). Anleitung:
  `spec/definitionen/anlagen/HTTPS.md`.
- `create_app` protokolliert mit Stufe `WARNING` (Logger `kontor…`), wenn
  `sitzung_cookie_secure = True` und `oeffentliche_url` fehlt (Festlegung E-305:
  beim Erzeugen der App, wie die Warnung ohne Anmeldung, `python-api.md` 6).
- Hinter dem Proxy prüft die Herkunftsprüfung (`sicherheit.md` 4.6) gegen
  `oeffentliche_url` – unverändert seit M7.
- Nicht prüfbar (root, systemd, Tailscale): die Skripte selbst; geprüft werden
  nur Vorhandensein, Unterbefehle und dass sie nie `funnel` aufrufen (E-305).
