# Mail-Abgleich: erwartete Zahlungen – Meilenstein 20

Verbindlich für Implementierung und Tests. Übernahme der freigegebenen
Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`mail-abgleich`, kontor-app D-128 „Mail-Abgleich“, E-216). Setzt M18
(`dokumente.md`) voraus. Ergänzt `python-api.md` 20, `betrieb.md` 3,
`protokoll.md` 17 (Quelle `mail`, Objekt `erwartung`), `benachrichtigungen.md`
9, `sicherung.md` 2.8, `openapi.yaml` (2.17.0) und `oberflaeche.md` 30.
Prüfmerkmale der Tests: E-217 bis E-219.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.
Abschnitt 8 der Definition steht als Abschnitt 30 in `oberflaeche.md`.

**Nicht** enthalten: Serien regelmäßiger Mail-Einkäufe als Grund, Kachel auf der
Übersicht (spätere Erweiterung, kontor-app D-131). Setzt M18 (Dokumente an Buchungen)
voraus: Beim Zuordnen werden Mails und PDF-Anhänge als Dokumente an Buchungen gehängt.

Grundidee: Bestell- und Zahlungsmails von Amazon und PayPal aus dem Mail-Spiegel
(`mail.md` 6.5) werden zu **erwarteten Zahlungen** (Objektart `erwartung`). Eine
Erwartung ist keine Buchung und ändert keinen Saldo. Ihr `betrag` ist nur der
**Bankanteil**; was aus einem Guthaben (Amazon-Gutschein/-Guthaben, PayPal-Guthaben)
bezahlt wurde, bleibt außerhalb der Buchhaltung. Bankbuchungen werden den Erwartungen
automatisch oder vom Anwender zugeordnet.

Kennzeichnung: **[kern]** = REST/Python/Konfiguration (Marker `kern`),
**[browser]** = Playwright-Test wie M8 (nicht `kern`).

## 1. Konfiguration [kern]

| `KontorConfig` | Umgebungsvariable | Typ, Grenzen | Vorgabe |
| --- | --- | --- | --- |
| `mail_abgleich` | `KONTOR_MAIL_ABGLEICH` | bool; Umgebung wie andere Schalter (`python-api.md`) | `False` |
| `mail_abgleich_frist_tage` | `KONTOR_MAIL_ABGLEICH_FRIST_TAGE` | int 0–366 | `5` |

- `mail_abgleich` kein bool → `KonfigurationsFehler` mit `feld = "mail_abgleich"`;
  `mail_abgleich_frist_tage` keine Ganzzahl (auch `bool`) oder außerhalb 0–366 →
  `KonfigurationsFehler` mit `feld = "mail_abgleich_frist_tage"`.
- Umgebung: ungültiger Wahrheitswert für `KONTOR_MAIL_ABGLEICH` wie bei anderen Schaltern;
  `KONTOR_MAIL_ABGLEICH_FRIST_TAGE` nicht nur ASCII-Ziffern oder > 366 →
  `KonfigurationsFehler` mit `variable = "KONTOR_MAIL_ABGLEICH_FRIST_TAGE"`. Leer = Vorgabe.
- Ausgelieferte Umgebungsdatei (`betrieb.md`, Paketdaten `kontor.env`): enthält
  `KONTOR_MAIL_ABGLEICH=1` (aktiv) und `KONTOR_MAIL_ABGLEICH_FRIST_TAGE` nur
  auskommentiert (`#KONTOR_MAIL_ABGLEICH_FRIST_TAGE=5`).
- Ausgeschaltet (Vorgabe): Es wird nie etwas erkannt oder automatisch zugeordnet, keine
  Benachrichtigung `erwartung_ueberfaellig`; Abläufe und Protokoll früherer Meilensteine
  sind unverändert. Die Endpunkte unter `/api/erwartungen` funktionieren trotzdem (Liste,
  manuelle Erwartungen, Zuordnen), nur `POST /api/erwartungen/abgleich` → 409
  `mail_abgleich_aus`.

## 2. Erkennung von Mails [kern]

Geprüft wird jede gespiegelte Mail (`absender`, `betreff`, `text` wie in
`GET /api/mail/nachrichten`) aller Postfächer, in der Reihenfolge `empfangen`, dann
Spiegel-ID. Erkannt wird nur, was eindeutig ist; sonst bleibt die Mail nur im Spiegel
(keine Erwartung, kein Fehler).

### 2.1 Anbieter am Absender

Die Domäne ist der Teil nach dem letzten `@` der Absenderangabe (abschließendes `>`
entfernt, Groß/Klein egal; `Name <x@domäne>` ist erlaubt). Anbieter `amazon` bzw.
`paypal`, wenn die Domäne `amazon.de` bzw. `paypal.de` ist, mit `amazon.` bzw. `paypal.`
**beginnt** oder `.amazon.`/`.paypal.` als Teil enthält. Synthetische Testabsender:
`bestellbestaetigung@amazon.example.invalid`, `service@paypal.example.invalid`.
Andere Domänen (z. B. `shop@example.invalid`, `amazon-fake.example.invalid`) → nicht erkannt.

### 2.2 Beträge

- Format deutsch: `1.234,56`, `1234,56`, `12` jeweils optional mit `€` oder `EUR` davor
  oder danach, optional Vorzeichen (`-`, `−`, `–`, `+`), das **ignoriert** wird (Beträge
  sind immer ≥ 0). Ein Betrag braucht Nachkommastellen (`,dd`) **oder** `€`/`EUR`; eine
  bloße Ganzzahl ohne Währung ist kein Betrag.
- „Wert nach Stichwort“: Gesucht wird die erste Zeile (Zeilen = nicht leere, getrimmte
  Textzeilen), die das Stichwort enthält (Groß/Klein egal) und einen Wert liefert: der
  erste Betrag **hinter** dem Stichwort in derselben Zeile, sonst der erste Betrag der
  **nächsten** Zeile. Liefert eine Zeile keinen Wert, wird die nächste passende Zeile
  versucht. (Folge für Testmails: Stichwörter nicht in Fließtextzeilen ohne Betrag vor
  der eigentlichen Betragszeile verwenden, wenn die folgende Zeile einen anderen Betrag
  enthält.)

### 2.3 Amazon

Kennung = Amazon-Bestellnummer `ddd-ddddddd-ddddddd` (3-7-7 Ziffern) – zuerst im Betreff
gesucht, sonst im Text. **Ohne Bestellnummer → nicht erkannt.** Die Art ergibt sich aus
dem Betreff (Groß/Klein egal), in dieser Reihenfolge:

| Betreff enthält | Art | Betrag | Ergebnis |
| --- | --- | --- | --- |
| `storniert` oder `stornierung` | Stornierung | – | schließt die Bestellung (2.6) |
| `erstattung` (auch in „Rückerstattung“) | Erstattung | Wert nach `Gesamterstattung`, `Erstattung`, `Erstattungsbetrag`, `Erstattete Betrag`/`Erstatteter Betrag`; fehlt → nicht erkannt | Grund `rueckerstattung`, Richtung `eingang`, `gesamt` = Betrag, `guthaben` 0, Händler „Amazon“, Bezug = Bestellung mit derselben Nummer |
| `bestell` oder `bestätig` | Bestellung | `gesamt` = Wert nach `Gesamtsumme`, `Gesamtbetrag`, `Endbetrag`, `Summe der Bestellung` oder `Bestellsumme`; fehlt → nicht erkannt. `guthaben` = Wert nach `Geschenkgutschein`, `Gutschein`/`Gutscheine` (optional „eingelöst“), `Amazon-Guthaben` oder `Guthaben`, sonst 0; höchstens `gesamt` | Grund `bestellung`, Richtung `ausgabe`, Händler „Amazon“ |
| sonst | – | – | nicht erkannt |

- **Artikel** (nur Bestellung, für `beschreibung`): jede Zeile der Form
  `[<n> x ]<Name> <Betrag mit €/EUR>` (Betrag am Zeilenende, Name ≥ 3 Zeichen), deren Name
  keines der Wörter summe, betrag, zwischen, versand, verpackung, gutschein, guthaben,
  steuer, mwst, rabatt, erstattung, bestellnr, zahlung enthält; Name ohne
  Rand-Leerzeichen/`.`/`:`/`-`. `beschreibung` = Namen mit `", "` verbunden (höchstens
  50 Artikel, höchstens 2000 Zeichen).
- Beispiel (fiktiv): Betreff `Ihre Amazon.de Bestellung von „USB-Kabel (fiktiv)“
  (302-1234567-7654321)`, Text:
  `Bestellnr. 302-1234567-7654321` / `1 x USB-Kabel (fiktiv) 9,99 €` /
  `1 x Ladegerät (fiktiv) 49,91 €` / `Gesamtsumme: 59,90 €` /
  `Geschenkgutschein: -10,00 €` → `gesamt` 5990, `guthaben` 1000, `betrag` 4990,
  `beschreibung` „USB-Kabel (fiktiv), Ladegerät (fiktiv)“.
- Stornierung: `Ihre Bestellung 302-1234567-7654321 wurde storniert` (Text beliebig).
  Erstattung: Betreff `Ihre Erstattung`, Text `Bestellnr. 302-…` / `Erstattungsbetrag: 9,99 €`.

### 2.4 PayPal

Kennung = Transaktionscode: der **erste** Treffer von `Transaktionscode`,
`Transaktionsnummer` oder `Transaktions-ID` (Groß/Klein egal), optional `:`, dann genau 17
Zeichen aus `0-9A-Z` (Groß/Klein egal) mit Wortgrenze. **Ohne Code → nicht erkannt.**
Hinweis: Auch „Ursprünglicher Transaktionscode: …“ enthält das Stichwort; der eigene Code
muss deshalb im Text **vor** dem ursprünglichen stehen.

| Betreff enthält (Groß/Klein egal) | Art | Händler | Betrag |
| --- | --- | --- | --- |
| `Rückzahlung` oder `Erstattung` | Rückzahlung | aus dem Betreff: Text nach `Rückzahlung`/`Erstattung` + ` von `/` durch ` bis zum Ende, ein abschließendes ` erhalten` und umschließende Anführungszeichen entfernt, höchstens 200 Zeichen; fehlt → „PayPal“ (bzw. Händler der ursprünglichen Zahlung, wenn diese bekannt ist) | Wert nach `Rückzahlungsbetrag`, `Erstatteter Betrag`, `Betrag der Rückzahlung`, `Gesamt` oder `Betrag`; fehlt → nicht erkannt |
| `Zahlung` (sonst) | Zahlung | Text nach `Zahlung an ` bis zum Ende, abschließendes ` gesendet` entfernt; fehlt → „PayPal“ | `gesamt` = Wert nach `Gesendeter Betrag`, `Gesamtbetrag`, `Gesamt` oder `Betrag`; fehlt → nicht erkannt |
| sonst | – | – | nicht erkannt |

- **Zahlung:** Grund `paypal`, Richtung `ausgabe`. `guthaben` = Summe aller Beträge, die in
  einer Zeile **hinter** `PayPal-Guthaben` bzw. `PayPalGuthaben` stehen (gleiche Zeile),
  höchstens `gesamt`. `referenz` = Bestell-/Rechnungsnummer des Händlers: Wert nach
  `Bestellnummer`, `Bestellnr`, `Bestellnr.`, `Rechnungsnummer`, `Rechnungsnr`,
  `Rechnungsnr.` (Schreibweise wie angegeben, optional `:`; 3–40 Zeichen aus
  Buchstaben, Ziffern, `-`), sonst eine Amazon-Bestellnummer im Text, sonst leer.
- **Rückzahlung:** Grund `rueckerstattung`, Richtung `eingang`, `gesamt` = Betrag. Steht im
  Text „gutgeschrieben auf/an (Ihr) PayPal-Guthaben“ oder „überwiesen auf/an (Ihr)
  PayPal-Guthaben“, ist `guthaben` = `gesamt` (nichts zu erwarten, Zustand `guthaben`),
  sonst 0. Bezug = PayPal-Zahlung mit dem Code nach `Ursprünglicher`/`Ursprüngliche`/
  `Original`/`Original-` + `Transaktionscode`/`-nummer`/`-ID`.
- Beispiel Zahlung (fiktiv): Betreff `Sie haben eine Zahlung an Fiktiver Shop gesendet`,
  Text `Sie haben 25,00 € an Fiktiver Shop gesendet.` / `Transaktionscode:
  1AB23456CD789012E` / `Gesendeter Betrag: -25,00 €` / `Bezahlt mit` /
  `PayPal-Guthaben 5,00 €` / `Lastschrift Testbank` / `Bestellnummer: R-4711` →
  `gesamt` 2500, `guthaben` 500, `betrag` 2000, Händler „Fiktiver Shop“, `referenz` „R-4711“.
- Beispiel Rückzahlung: Betreff `Rückzahlung von Fiktiver Shop erhalten`, Text
  `Rückzahlungsbetrag: 25,00 €` / `Transaktionscode: 9ZZ23456CD789012E` /
  `Ursprünglicher Transaktionscode: 1AB23456CD789012E`.

### 2.5 Aus Mails angelegte Erwartungen

- Erkennungen mit `gesamt` = 0 werden ignoriert (außer Stornierung).
- `datum` = UTC-Datum von `empfangen` der Mail; `frist` = `datum` +
  `mail_abgleich_frist_tage`.
- `betrag` = `gesamt` − `guthaben` (≥ 0); Zustand `offen`, bei `betrag` = 0 sofort
  `guthaben`.
- `kennung` = Bestellnummer bzw. Transaktionscode; `referenz` nur bei PayPal-Zahlungen
  (sonst `""`); `anbieter` = `amazon`/`paypal`; `bezug_id` = ID der Bezugserwartung
  (Erstattung → Bestellung bzw. Zahlung), wenn diese existiert, sonst `null`.
- **Schlüssel und Idempotenz:** Je Vorgang höchstens eine Erwartung: Amazon-Bestellung
  je Bestellnummer, PayPal-Zahlung je Transaktionscode, Erstattung je (Anbieter, Kennung,
  Betrag). Eine weitere Mail zum selben Vorgang (auch dieselbe Mail aus einem zweiten
  Postfach) legt nichts an, sondern ergänzt nur die Liste `mails` (je Postfach und
  Nachrichten-ID einmal). Wiederholtes Abgleichen ändert nichts.
- `mails`-Eintrag: `{postfach, nachricht_id, betreff (≤ 200 Zeichen), empfangen}`;
  `postfach` = Adresse des Postfachs in Kleinschreibung. Die Mails selbst bleiben
  Betriebszustand (Spiegel), nicht Buchbestand.

### 2.6 Stornierung

Eine Stornierung setzt die Amazon-Bestellung derselben Nummer auf `storniert` und ergänzt
ihre `mails` – nur wenn sie `offen` ist und **keine** Buchungen zugeordnet hat. Gibt es die
Bestellung (noch) nicht oder ist sie nicht offen/schon zugeordnet, geschieht nichts (eine
später verarbeitete Bestellmail legt die Bestellung dann normal an).

## 3. Objekt `Erwartung` und Ableitungen [kern]

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | |
| `grund` | `bestellung` \| `paypal` \| `rueckerstattung` \| `manuell` | |
| `richtung` | `ausgabe` \| `eingang` | |
| `anbieter` | `amazon` \| `paypal` \| null | manuell: null |
| `kennung`, `referenz` | str | ggf. `""` |
| `haendler` | str 1–200 | |
| `beschreibung` | str ≤ 2000 | |
| `betrag` | int Cent 0–999 999 999 999 | Bankanteil |
| `gesamt`, `guthaben` | int Cent ≥ 0 | `betrag` = `gesamt` − `guthaben` |
| `datum`, `frist` | date | |
| `zustand` | `offen` \| `erfuellt` \| `guthaben` \| `storniert` \| `erledigt` | |
| `bezug_id` | int \| null | |
| `buchung_ids` | Liste int, aufsteigend | zugeordnete Buchungen |
| `mails` | Liste `{postfach, nachricht_id, betreff, empfangen}` | |
| `dokument_ids` | Liste int, aufsteigend | angehängte Dokumente (M18) |
| `erstellt_am` | date-time (App-Uhr, UTC, `Z`) | |
| `zugeordnet` | int ≥ 0 | abgeleitet: Summe der Beträge (absolut) der zugeordneten Buchungen, die genau einen Split auf einem Bestandskonto haben (dieser Split) |
| `offen_betrag` | int ≥ 0 | abgeleitet: `max(0, betrag − zugeordnet)` bei `offen`, sonst 0 |
| `ueberfaellig` | bool | abgeleitet: `zustand = offen` und `frist` < heute (Datum der App-Uhr) |
| `vorzeichen_betrag` | int | abgeleitet: −`betrag` bei `ausgabe`, `betrag` bei `eingang` |

Kein Feld `schluessel` in Antworten. Detail (`GET /api/erwartungen/{id}` und alle
Antworten mit einer einzelnen Erwartung) zusätzlich:

- `buchungen`: je zugeordneter Buchung mit genau einem Bestandskonto-Split
  `{id, datum, betrag (Split auf dem Bestandskonto, mit Vorzeichen), konto_id, konto (Name),
  empfaenger (Name | null), verwendungszweck}`;
- `mail_eintraege`: je `mails`-Eintrag `{postfach, nachricht_id, betreff, empfangen,
  spiegel_id}`, `spiegel_id` = `id` der Mail in `GET /api/mail/nachrichten` oder null,
  wenn sie nicht mehr gespiegelt ist.

## 4. Abgleich [kern]

Ein Abgleich = (1) Erkennen (2) → (2) automatisch zuordnen (5.2) → (3) Überfällige
melden (4.2). Nur mit `mail_abgleich`.

### 4.1 Auslöser und Protokoll

- nach jedem Mail-Abruf (`POST /api/mail/abruf` und Planer), sobald mindestens ein aktives
  Postfach abgefragt wurde, auch wenn einzelne Postfächer scheitern;
- nach jedem Synchronisationslauf mit Endstatus (siehe 9, Abweichung);
- in jedem Planer-Takt nach Schritt 5 (`synchronisation.md` 18.2), auch ohne Abruf
  (prüft Fristen);
- per `POST /api/erwartungen/abgleich`.

Schritte (1) und (2) bilden **eine** Änderung mit `aktion = "erwartung_erkennen"`,
`quelle = "mail"`, `gruppe = null` (neue Quelle `mail` in `protokoll.md` 3/4), **nur**
wenn sich eine Protokollform ändert (T 3.5); dazu gehören auch beim automatischen
Zuordnen angelegte Dokumente und Verknüpfungen. Rückgängig entfernt die erkannten
Erwartungen und Zuordnungen wieder (ein späterer Abgleich erkennt sie erneut, solange die
Mails gespiegelt sind). Fehler im Abgleich lassen Abruf, Lauf und Planer nie scheitern.

### 4.2 Benachrichtigung `erwartung_ueberfaellig`

Je überfälliger Erwartung höchstens **eine** Benachrichtigung überhaupt (Entprellung
„einmal“, auch nach dem Lesen nicht erneut): `art = "erwartung_ueberfaellig"`,
Schlüssel `erwartung_ueberfaellig:<id>`, Link `/erwartet?id=<id>`, Priorität wie „alle
übrigen Arten“ (`benachrichtigungen.md` 4.4: 3). Titel „Zahlung nicht abgebucht“
(Ausgabe) bzw. „Erstattung überfällig“ (Eingang); Text deutsch mit Händler, Betrag und
Frist. Benachrichtigungen sind nicht Teil der Änderung (4.1). Neue Art in
`benachrichtigungen.md` aufnehmen.

## 5. Zuordnung [kern]

### 5.1 Kandidaten

Für eine Erwartung im Zustand `offen` mit `offen_betrag` > 0 (sonst leere Liste) ist eine
Buchung Kandidat, wenn

1. ihr Datum von `datum` − 3 Tage bis `datum` + 45 Tage reicht (einschließlich),
2. sie **genau einen** Split auf einem Bestandskonto hat (Umbuchungen zwischen zwei
   Bestandskonten scheiden aus) und dessen Vorzeichen zur Richtung passt (Ausgabe < 0,
   Eingang > 0),
3. sie noch **keiner** Erwartung zugeordnet ist,
4. |Split-Betrag| ≤ `offen_betrag`,
5. und `kennung_passt` oder `betrag_gleich` gilt:
   - `kennung_passt`: `kennung` oder `referenz` (jeweils ≥ 6 Zeichen) kommt – ohne
     Leerzeichen, Groß/Klein egal – im Verwendungszweck oder Empfängernamen (ebenfalls ohne
     Leerzeichen) vor;
   - `betrag_gleich`: |Split-Betrag| = `offen_betrag`.

Zusätzlich `anbieter_passt`: Verwendungszweck + Empfängername (Groß/Klein egal) enthält den
Anbieternamen (`amazon`/`paypal`), bei Amazon auch `amzn`, oder den Händlernamen (≥ 3
Zeichen). Reihenfolge: zuerst `kennung_passt`, dann `betrag_gleich`, dann `anbieter_passt`,
dann kleinster Datumsabstand (`abstand_tage`), dann ID.

### 5.2 Automatisch (im Abgleich; ab M32 für PayPal und geplante Zahlungen geändert, `sammel3.md` 9.2, 14.3)

Offene Erwartungen werden nach (`datum`, `id`) bearbeitet; eine im selben Abgleich schon
vergebene Buchung zählt nicht mehr als Kandidat.

- Kandidaten mit `kennung_passt` werden zugeordnet (mehrere möglich: Teillieferungen), in
  der Reihenfolge 5.1, solange die Summe `betrag` nicht übersteigt.
- Sonst nur, wenn es **genau einen** Kandidaten mit `betrag_gleich` gibt, dieser
  `anbieter_passt` hat und diese Buchung für **keine andere** offene Erwartung ein
  `betrag_gleich`-Kandidat ist.
- Alles andere bestätigt der Anwender (5.3). Gilt für alle Gründe, auch manuelle
  Erwartungen (z. B. über ihre `kennung`).

### 5.3 Zuordnen, Zustand, Dokumente

- Nach dem Zuordnen: `erfuellt`, wenn `zugeordnet` ≥ `betrag`, sonst bleibt `offen`
  (Teilzahlung, `offen_betrag` = Rest).
- **Dokumente (M18):** Hat die Erwartung schon Dokumente, werden diese mit der neuen
  Buchung verknüpft. Sonst wird je Mail (je Nachrichten-ID einmal, auch bei zwei Postfächern;
  nur wenn noch gespiegelt) ein Dokument vom Typ E-Mail (`message/rfc822`, Quelle `mail`,
  Dateiname aus dem Betreff) und je PDF-Anhang der Mail ein PDF-Dokument (Quelle `mail`)
  angelegt und an die Buchung gehängt; die IDs landen in `dokument_ids`. Die Buchung zeigt
  sie in `belege`. Mails aus dem Mock-Plugin haben keine Rohfassung und keine Anhänge
  (Dokument aus den Feldern gebaut, M18).
- **Lösen** entfernt die Buchung aus `buchung_ids` und die Verknüpfung aller Dokumente der
  Erwartung mit dieser Buchung (ein Dokument ohne Buchung entfällt nach M18; es bleibt in
  `dokument_ids`, bis es entfällt). `erfuellt` → `offen`; andere Zustände bleiben.
- **Verwaiste Bezüge:** Nach jeder protokollierten Operation entfallen gelöschte Buchungen
  aus `buchung_ids` und gelöschte Dokumente aus `dokument_ids` – in derselben Änderung; eine
  `erfuellt`e Erwartung, der danach Betrag fehlt, ist wieder `offen`. Rückgängig stellt
  beides wieder her.

## 6. REST [kern]

Alle Endpunkte sind geschützt (M7, nicht in `sicherheit.md` 3.1). Fehlerformat wie
bisher; `nicht_gefunden` = 404. Schreibende Endpunkte sind Änderungen mit `quelle =
"manuell"`, `gruppe = null` und der genannten Aktion (`protokoll.md` 4.1), nur bei
Wirkung.

| Endpunkt | Anfrage | Antwort |
| --- | --- | --- |
| `GET /api/erwartungen` | Query (6.1) | 200 `ErwartungListe` |
| `POST /api/erwartungen` | `ErwartungNeu` | 201 Erwartung (Detail); Aktion `erwartung_anlegen` |
| `POST /api/erwartungen/abgleich` | ohne Körper (oder `{}`) | 200 `{neu, ergaenzt, storniert, zugeordnet, gemeldet}` (int); 409 `mail_abgleich_aus` |
| `GET /api/erwartungen/{id}` | | 200 Detail; 404 |
| `PATCH /api/erwartungen/{id}` | `ErwartungAenderung` | 200 Detail; Aktion `erwartung_aendern` |
| `DELETE /api/erwartungen/{id}` | | 204; 404; 409 `erwartung_aus_mail`; Aktion `erwartung_loeschen` |
| `POST /api/erwartungen/{id}/zustand` | `{zustand}` | 200 Detail; Aktion `erwartung_zustand` |
| `GET /api/erwartungen/{id}/kandidaten` | | 200 `{eintraege: [Kandidat]}`; 404 |
| `POST /api/erwartungen/{id}/buchungen` | `{buchung_ids}` | 200 Detail; Aktion `erwartung_zuordnen` |
| `DELETE /api/erwartungen/{id}/buchungen/{buchung_id}` | | 200 Detail; 404; Aktion `erwartung_loesen` |

### 6.1 Liste

- Query: `grund` (wiederholbar, Werte 3.), `zustand` (wiederholbar, Werte 3. **und**
  `ueberfaellig`; ohne Angabe nur `offen`), `faellig_bis` (date: `frist` ≤), `suche`
  (Teilzeichenkette ohne Groß/Klein in `haendler`, `beschreibung`, `kennung` oder
  `referenz`), `richtung`. Unbekannte Werte/Parameter → 422 `validierung`. Mehrere
  Zustände sind ODER-verknüpft; `ueberfaellig` = offen mit `frist` < heute; die übrigen
  Filter sind UND-verknüpft.
- Sortierung `frist`, dann `id` aufsteigend.
- `ErwartungListe = {eintraege: [Erwartung ohne Detailfelder], anzahl, summe_offen,
  ueberfaellig, aktiv}`: `anzahl` = Länge, `summe_offen` = Σ `offen_betrag` mit Vorzeichen
  (Eingang +, Ausgabe −), `ueberfaellig` = Anzahl der überfälligen Einträge der Liste,
  `aktiv` = Wert von `mail_abgleich`.

### 6.2 Anlegen und Ändern (manuell)

- `ErwartungNeu`: `richtung` (Pflicht), `haendler` (Pflicht, 1–200 Zeichen, getrimmt),
  `betrag` (Pflicht, int 1–999 999 999 999), `datum` (date, Vorgabe heute), `frist`
  (date, Vorgabe `datum` + `mail_abgleich_frist_tage`), `beschreibung` (≤ 2000),
  `kennung` (≤ 200). Unbekannte Felder, falsche Typen (auch bool statt int) → 422
  `validierung`. Ergebnis: `grund = manuell`, `anbieter = null`, `gesamt = betrag`,
  `guthaben = 0`, `referenz = ""`, `mails = []`, `zustand = offen`.
- `ErwartungAenderung`: optional `haendler`, `betrag`, `datum`, `frist`, `beschreibung`,
  `kennung` (Regeln wie oben; `richtung` und andere Felder → 422). Für Erwartungen jedes
  Grundes. `betrag` < `zugeordnet` → 422 `zuordnung_zu_hoch`; sonst `gesamt` = `betrag` +
  `guthaben`. Ist sie danach `offen` oder `erfuellt` mit Zuordnungen, wird der Zustand neu
  bestimmt (5.3). Prüfreihenfolge: 404 → 422 `validierung` → 422 `zuordnung_zu_hoch`.

### 6.3 Zustand, Löschen

- `POST …/zustand` mit genau `{zustand}` ∈ `offen`, `guthaben`, `storniert`, `erledigt`
  (sonst 422 `validierung`). Schließen (`guthaben`/`storniert`/`erledigt`) nur aus `offen`;
  Öffnen (`offen`) nur aus `guthaben`/`storniert`/`erledigt` (nicht aus `erfuellt`) – sonst
  409 `zustand_unzulaessig`. Zuordnungen bleiben dabei unverändert. Prüfreihenfolge: 404 →
  422 → 409.
- `DELETE` nur für `grund = manuell`; aus Mails erkannte → 409 `erwartung_aus_mail` (sie
  werden geschlossen, sonst kämen sie beim nächsten Abgleich wieder).

### 6.4 Zuordnen, Lösen

- `POST …/buchungen` mit genau `{buchung_ids}` (nicht leere Liste von int, Doppelte
  zusammengefasst). Prüfreihenfolge: Erwartung unbekannt → 404; Körper → 422
  `validierung`; Erwartung nicht `offen` → 409 `erwartung_nicht_offen`; eine Buchung
  unbekannt → 404 `nicht_gefunden`; eine Buchung ohne genau einen Bestandskonto-Split →
  422 `zuordnung_ungueltig`; Vorzeichen passt nicht zur Richtung → 422
  `zuordnung_ungueltig`; Buchung gehört schon zu einer **anderen** Erwartung → 409
  `buchung_bereits_zugeordnet`; Summe aller zugeordneten Buchungen > `betrag` → 422
  `zuordnung_zu_hoch`. Das Datumsfenster aus 5.1 gilt hier nicht. Schon zugeordnete IDs
  derselben Erwartung sind erlaubt (ohne Wirkung).
- `DELETE …/buchungen/{buchung_id}`: Erwartung unbekannt oder Buchung nicht zugeordnet →
  404 `nicht_gefunden`.
- `Kandidat = {id, datum, betrag, konto_id, konto, empfaenger, verwendungszweck,
  kennung_passt, betrag_gleich, anbieter_passt, abstand_tage}` (Reihenfolge 5.1).

## 7. Sicherung [kern]

Sicherungsdatei Schemaversion **5**: Objektart `erwartung` mit allen Feldern aus 3 (ohne
abgeleitete) einschließlich des internen Schlüssels; `erwartung` steht in `anzahl`,
Inhaltsprüfsumme und `unterschied` nur, wenn Erwartungen vorhanden sind (`sicherung.md`
2.5, E-109). Mails sind Betriebszustand und **nicht** in der Sicherung (nach dem Einspielen
in eine leere App ist `spiegel_id` null). Sicherungen der Versionen 1–4 werden ohne
Erwartungen gelesen. Ungültige Werte (unbekannter Grund/Zustand/Richtung/Anbieter,
ungültiges Datum, Beträge außerhalb 0–999 999 999 999, Listenfelder kein JSON-Array) →
Sicherung ungültig nach `sicherung.md` 5.1. Rundreise-Test: Sicherung → Einspielen in
eine neue App ergibt dieselben Erwartungen (Felder aus 3) und dieselbe Prüfsumme.

## 8. Oberfläche [browser]

Siehe `oberflaeche.md` 30.

## 9. Abweichungen und Präzisierungen gegenüber kontor-app D-128

- **Auslöser nach Synchronisationsläufen:** Maßgeblich ist 4.1 („nach jedem Lauf mit
  Endstatus“, wie D-128). Der Stand des Branches gleicht nach erfolgreichen Läufen erst im
  nächsten Planer-Takt ab; das ist in der Implementierung anzupassen.
- Stornierung nur für offene Bestellungen ohne Zuordnung (2.6); Kandidaten- und
  Automatikregeln wie D-128, präzisiert in 5.
- Der Abgleich über REST liefert bei einem internen Fehler 200 mit `{}`.

## 10. Einspeisen synthetischer Mails in Tests

Nur über spezifizierte Schnittstellen, ausschließlich fiktive Inhalte, Postfächer unter
`example.invalid`:

- **Mock-Modus:** Mock-Datendatei (`plugins.md` 4, `mock_daten`/`KONTOR_MOCK_DATEN`) mit
  `mail.postfaecher` und `mail.nachrichten` (Absender mit den Domänen aus 2.1, Betreff,
  Text). Postfächer per `POST /api/mail/postfaecher` anlegen (ohne Postfach kein Spiegel;
  `absender_filter` leer lassen oder passend setzen), App-Uhr über `mock_heute`/die
  Mock-Uhr, dann `POST /api/mail/abruf` (löst den Abgleich aus) oder
  `POST /api/erwartungen/abgleich`. Bankbuchungen über `POST /api/buchungen` oder den
  Mock-Bank-Plugin-Lauf.
- **Echtmodus:** IMAP-Attrappe (`mail.md` 8) mit generierten mbox-Postfächern; dann
  haben Mails eine Rohfassung, PDF-Anhänge werden beim Zuordnen zu Dokumenten (5.3).
- Generator: neue synthetische Mails/Fixtures nur über `python -m generator`.

## 11. Umfang der Tests

- `tests/app/m20/` (Marker `m20`). [kern]: Konfiguration, Erkennung (je Regel aus 2 mit
  positiven und negativen Fällen), Idempotenz und zwei Postfächer, Stornierung,
  Zuordnung automatisch/manuell mit allen Fehlercodes und Prüfreihenfolgen, Teilzahlung,
  Dokumente an der Buchung, Lösen, verwaiste Bezüge nach Buchungslöschung und
  Rückgängig, Liste mit Filtern und Summen, Überfällig und Benachrichtigung (einmal),
  Auslöser (Abruf, Planer-Takt, Lauf), Protokoll (Aktionen, Quelle `mail`, keine leeren
  Änderungen), Sicherung (Version 5, Rundreise, ältere Versionen, ungültige Werte),
  Schutz (M7). [browser]: Seite, Chips und Adresse, Menü, Dialoge, Zuordnen über
  Kandidaten, Sprung aus `?id=`.
- `openapi.yaml`: neue Pfade und Schemas (`Erwartung`, `ErwartungDetail`,
  `ErwartungListe`, `ErwartungNeu`, `ErwartungAenderung`, `Kandidat`, Abgleich-Ergebnis),
  neue Fehlercodes, `quelle` um `mail` und Benachrichtigungsart `erwartung_ueberfaellig`
  erweitert (rückwärtskompatibel, E-029).
- Abhängigkeiten: M3 (Protokoll), M6 (Postfächer, Spiegel, Abruf, Benachrichtigungen),
  M7 (Schutz), M8 (Oberfläche), M9 (Sicherung), M17 (Tabs), M18 (Dokumente).

## 12. Protokollform des Objekts `erwartung` (Präzisierung, E-217)

Die Definition legt die Protokollform nicht ausdrücklich fest. Sie lautet:
die Felder aus 3 **ohne** die abgeleiteten Felder (`zugeordnet`,
`offen_betrag`, `ueberfaellig`, `vorzeichen_betrag`) und ohne die Felder des
Details (`buchungen`, `mail_eintraege`), also `{id, grund, richtung, anbieter,
kennung, referenz, haendler, beschreibung, betrag, gesamt, guthaben, datum,
frist, zustand, bezug_id, buchung_ids, mails, dokument_ids, erstellt_am}`
(Schema `ErwartungZustand`). Sie ist aus `GET /api/erwartungen` ableitbar.
Der interne Schlüssel ist kein Teil von Antworten (3) und damit auch nicht
der Protokollform; er ist nur in der Sicherung enthalten (7). Einträge mit
`objekt = "erwartung"` folgen in der Sortierung (`protokoll.md` 3.1) nach
`dokument`. Die Inhaltsprüfsumme der Sicherung (`sicherung.md` 3.3) wird mit
den Protokollformen berechnet.

## 13. Meilenstein 24: Serien, Kategorie bei Erstattungen, eingebaute Mock-Mails (E-233)

Übernahme der freigegebenen Meilenstein-Definition des Auftraggebers vom 2026-11-13
(Feature `mail-abgleich`, Fortsetzung; kontor-app D-131 und D-139). Ergänzt 1–12
rückwärtskompatibel: Ohne die neuen Angaben (`grund=serie`, `serien=ja`) bleiben alle
Antworten aus M20 unverändert. Kein neuer gespeicherter Zustand, keine neue Objektart,
Sicherung unverändert. Abschnitte 1, 3, 5 und 6 der Definition stehen hier als 13.1 bis
13.4 (Verweise darin auf „1.x“, „3“, „5“ und „6“ meinen die Abschnitte der Definition,
also 13.1, 13.2, 13.3 und 13.4; Verweise auf „M20 3“, „M20 5.2“ meinen 3 und 5.2 dieses
Dokuments); die Abschnitte 2 und 4 (Kachel „Was kommt noch?“, Seite `/erwartet` mit
Serien) stehen als `oberflaeche.md` 34. Tests in `tests/app/m24/` (Marker `m24`);
13.1 und 13.2 sind `kern`, 13.3 ein REST-Test ohne `kern`. Prüfmerkmale: E-234, E-235.

### 13.1 Serien als erwartete Zahlungen in `GET /api/erwartungen` [kern]


#### 13.1.1 Wann Serien enthalten sind

- Neuer Abfrageparameter `serien` = `ja` | `nein` (Vorgabe `nein`; andere Werte → 422 `validierung`,
  `details[].ort = ["query", "serien"]`). Neuer Wert `serie` für den wiederholbaren Parameter `grund`.
- Serieneinträge erscheinen genau dann, wenn
  - `grund=serie` unter den angegebenen Gründen ist, **oder**
  - `serien=ja` und **kein** `grund` angegeben ist (mit irgendeinem `grund` ohne `serie` wird `serien=ja`
    ignoriert),
  - **und** der Zustandsfilter `offen` oder `ueberfaellig` enthält (ohne `zustand` gilt wie in M20 `offen`).
    Mit nur `erfuellt`/`guthaben`/`storniert`/`erledigt` keine Serien.
- `grund=serie` allein liefert nur Serien (keine gespeicherten Erwartungen); `grund=serie&grund=paypal` liefert
  beides.
- Ohne `grund=serie` und ohne `serien=ja` enthält die Liste **keine** Serien (M20 unverändert).
- Unabhängig von `mail_abgleich` (auch bei `aktiv = false` werden Serien geliefert, wie die übrigen Einträge).

#### 13.1.2 Welche Serien

Grundlage ist die Übersicht der wiederkehrenden Buchungen (`GET /api/wiederkehrend` mit Stichtag = heute nach
App-Uhr, `wiederkehrend.md` 2/M16): je Serie mit `status` `aktiv` oder `ausbleibend` ein Eintrag; `beendet` nie.

Ausgelassen wird eine Serie, deren **letzte** Buchung (letzter Eintrag ihrer `buchung_ids`) in den `buchung_ids`
irgendeiner gespeicherten Erwartung steht – gleich welchen Grundes (auch `manuell`) und Zustands (regelmäßige
Einkäufe, die schon über Mails erwartet werden, nicht doppelt). Abweichung von D-131: dort „einer erwarteten
Zahlung aus einer Mail“; tatsächlich zählt jede Erwartung.

#### 13.1.3 Felder eines Serieneintrags

Ein Serieneintrag hat alle Felder einer Erwartung aus M20 3 (ohne Detailfelder) mit diesen Werten, dazu zwei
zusätzliche Felder:

| Feld | Wert |
| --- | --- |
| `id` | **Zeichenkette** `"serie:" + schluessel` der Serie, z. B. `"serie:1:1:ausgabe"` (Muster `^serie:[0-9]+:[0-9]+:(ausgabe\|einnahme)$`) |
| `grund` | `"serie"` |
| `richtung` | Serie `ausgabe` → `"ausgabe"`, `einnahme` → `"eingang"` |
| `anbieter` | `null` |
| `kennung`, `referenz` | `""` |
| `haendler` | Name des Empfängers der Serie (nie leer) |
| `beschreibung` | `"<rhythmus>, zuletzt <letzte>"`, z. B. `"monatlich, zuletzt 2026-10-05"` (Werte aus der Serie) |
| `betrag`, `gesamt` | Betrag der Serie ohne Vorzeichen (`abs(betrag)`) |
| `guthaben` | `0` |
| `datum` | `naechste_faelligkeit` der Serie |
| `frist` | `datum` + `mail_abgleich_frist_tage` Tage (Konfiguration aus M20 1) |
| `zustand` | `"offen"` |
| `bezug_id` | `null` |
| `buchung_ids`, `mails`, `dokument_ids` | `[]` |
| `erstellt_am` | `null` |
| `zugeordnet` | `0` |
| `offen_betrag` | = `betrag` |
| `ueberfaellig` | `frist` < heute (App-Uhr) |
| `vorzeichen_betrag` | −`betrag` bei `ausgabe`, `betrag` bei `eingang` |
| `konto_id` | `konto_id` der Serie (int) – **nur** an Serieneinträgen |
| `serie` | `schluessel` der Serie (str) – **nur** an Serieneinträgen |

Gespeicherte Erwartungen tragen `konto_id`/`serie` nicht.

#### 13.1.4 Filter, Sortierung, Summen

- `richtung`, `faellig_bis` (`frist` ≤) und `suche` (in `haendler`, `beschreibung`, `kennung`, `referenz`, ohne
  Groß/Klein) gelten auch für Serien. Bei Zustand nur `ueberfaellig` nur überfällige Serien.
- Sortierung der gesamten Liste nach `frist`, dann `id`; sobald Serien enthalten sind, wird `id` dabei **als
  Zeichenkette** verglichen (Abweichung, siehe 6). Tests sollen nur die Reihenfolge nach `frist` und bei gleicher
  Frist nicht die Reihenfolge zwischen Einträgen prüfen.
- `anzahl`, `summe_offen` (Σ `offen_betrag`, Eingang +, Ausgabe −) und `ueberfaellig` (Anzahl) zählen die
  Serieneinträge der Liste mit.

#### 13.1.5 Nicht abrufbar, keine Wirkung

- Serieneinträge sind abgeleitet, nicht gespeichert: `GET/PATCH/DELETE /api/erwartungen/serie:…`,
  `…/kandidaten`, `…/zustand`, `…/buchungen` → 404 `nicht_gefunden` („Der angeforderte Pfad existiert nicht.“),
  da die Pfade nur ganzzahlige IDs kennen.
- Keine Benachrichtigung `erwartung_ueberfaellig` für Serien (die Meldung „ausbleibend“ der wiederkehrenden
  Buchungen bleibt maßgeblich), kein Protokolleintrag, nicht in der Sicherung, nicht im automatischen Zuordnen.
- `POST /api/erwartungen/abgleich` und Abruf ändern an Serieneinträgen nichts.

#### 13.1.6 Schema (`openapi.yaml`, rückwärtskompatibel)

- Query `grund`: Werte zusätzlich `serie` (eigene Aufzählung für die Abfrage; `ErwartungGrund` der
  gespeicherten Erwartungen bleibt ohne `serie`). Neuer Query-Parameter `serien` (`ja`|`nein`).
- `ErwartungListe.eintraege.items`: `oneOf` [`Erwartung`, `ErwartungSerie`]. Neues Schema `ErwartungSerie`
  (`additionalProperties: false`) mit den Feldern aus 1.3: `id` string mit Muster, `grund` const `serie`,
  `anbieter` null, `bezug_id` null, `erstellt_am` null, `buchung_ids`/`mails`/`dokument_ids` leere Arrays,
  `zustand` const `offen`, `zugeordnet` 0, `konto_id` Id, `serie` string (Muster des Serienschlüssels).
- Frühere Tests (M20) bleiben unverändert grün, weil sie weder `grund=serie` noch `serien=ja` senden.


### 13.2 Kategorie bei Erstattungen [kern]


Wird einer Erwartung mit `grund = "rueckerstattung"` eine Buchung **neu** zugeordnet – von Hand
(`POST /api/erwartungen/{id}/buchungen`) oder automatisch im Abgleich (M20 5.2) –, gilt für jede neu
zugeordnete Buchung G (Gutschrift):

Voraussetzungen (alle):
1. Die Erstattung hat einen `bezug_id`, die bezogene Erwartung U existiert und hat mindestens eine zugeordnete
   Buchung. „Ursprüngliche Buchung“ = die kleinste ID in `U.buchung_ids`.
2. Die ursprüngliche Buchung hat **genau einen** Split auf einem Nicht-Bestandskonto (Bestandskonten:
   `girokonto`, `sparkonto`, `kreditkonto`); dessen Konto ist die Zielkategorie K.
3. G hat **genau zwei** Splits, genau einer davon auf einem Nicht-Bestandskonto, und dieser liegt auf dem
   technischen Konto „Unkategorisiert“.
4. Für G besteht kein offener Kategorievorschlag (`kategorisierung.md`, Vorschläge).

Dann wird der Split von G auf „Unkategorisiert“ auf K umgebucht (Betrag unverändert, Status der Buchung
unverändert). Sonst bleibt G unverändert; die Zuordnung selbst geschieht in jedem Fall.

- Protokoll: Die Umbuchung gehört zur **selben Änderung** wie die Zuordnung (`erwartung_zuordnen`, Quelle
  `manuell`, bzw. `erwartung_erkennen`, Quelle `mail`, M20 4.1) – die Buchung G erscheint dort mit Vorher/Nachher.
  Rückgängig dieser Änderung stellt Zuordnung **und** Split wieder her; Wiederholen setzt beides erneut.
- Lösen der Buchung (`DELETE …/buchungen/{id}`) setzt die Kategorie **nicht** zurück.
- „Unkategorisiert“: Die App erkennt das Konto am Namen `Unkategorisiert`, Art `eigenkapital`, oberste Ebene
  (Abweichung zu `datenmodell.md` (technisches Konto mit `extern_id = "kontor:unkategorisiert"`), siehe 6).
  Tests verwenden das technische Konto, wie es ein Synchronisationslauf (Mock) anlegt; dann gelten beide Lesarten.
- Ist K selbst „Unkategorisiert“, ändert sich nichts.


### 13.3 Eingebauter Mock-Datensatz [REST, nicht kern]


Im Mock-Modus **ohne** Mock-Datendatei (eingebauter Datensatz, `plugins.md`) enthält jeder Monat (ab Beginn des
eingebauten Datensatzes bis zum Monat von heute) zusätzlich:

- Postfach `haushalt.eins@example.invalid`: eine Amazon-Bestellmail (Absender
  `bestellbestaetigung@amazon.example.invalid`, Betreff beginnt mit „Ihre Amazon.de Bestellung“, Bestellnummer
  `302-NNNNNNN-NNNNNNN`, Gesamtsumme), in jedem dritten Monat (Monat 3, 6, 9, 12) zusätzlich eine
  Erstattungsmail (`rueckgabe@amazon.example.invalid`, „Ihre Erstattung (Testdaten)“, 9,99 €) zur selben
  Bestellnummer;
- Postfach `haushalt.zwei@example.invalid`: eine PayPal-Zahlungsmail (`service@paypal.example.invalid`) an
  „Buchhandlung Seitenweise (fiktiv)“;
- im eingebauten Girokonto die passenden Umsätze: Abbuchung der Amazon-Gesamtsumme (Verwendungszweck enthält die
  Bestellnummer), Abbuchung des PayPal-Betrags (Verwendungszweck enthält den Händlernamen), in den
  Erstattungsmonaten eine Gutschrift über 9,99 € mit „Erstattung <Bestellnummer>“.

Prüfbar (ein Ende-zu-Ende-Test): Mock-Modus mit `mail_abgleich` an, beide Postfächer anlegen
(`POST /api/mail/postfaecher`), `POST /api/sync`, `POST /api/mail/abruf`, `POST /api/erwartungen/abgleich` →
unter `zustand=erfuellt` gibt es Erwartungen mit den Gründen `bestellung` und `paypal`; die zugeordneten
Buchungen haben Belege (`belege` nicht leer, M18). Weitere Eigenschaften des eingebauten Datensatzes (Beträge,
Tage) sind nicht festgelegt.


### 13.4 Abweichungen und offene Punkte gegenüber D-131/D-139


- Auslassen von Serien (1.2) bei Zuordnung zu **jeder** Erwartung, nicht nur zu Mail-Erwartungen.
- Sortierung mit Serien vergleicht `id` als Zeichenkette (bei gleicher Frist kann z. B. `10` vor `9` stehen);
  ohne Serien numerisch wie M20.
- „Unkategorisiert“ wird am Namen erkannt, nicht an `extern_id` (3).
- Die Seite `/erwartet` schreibt ohne gewählten Grund `serien=ja` in den Abfrageteil der Adresse; nach
  `oberflaeche.md` 30 enthält er nur `grund`, `zustand`, `faellig`, `suche`.
- Menüknopf mit Roh-ID (Doppelpunkte), Zeile mit ersetzter ID (4).
- D-131 nennt Serien „in der Liste“ ohne Bedingung; D-139 macht sie abfragepflichtig (1.1).

## 14. Meilenstein 31: Mails über die Bestellnummer an der Buchung (Definition 3, D-208, D-209; E-283)

### 14.1 Konfiguration

`mail_bestellnummer` (`KONTOR_MAIL_BESTELLNUMMER`, Wahrheitswert wie
`mail_abgleich`, Vorgabe `False`; `python-api.md` 22). Die ausgelieferten
Umgebungsdateien setzen `KONTOR_MAIL_BESTELLNUMMER=1` und
`KONTOR_MAIL_ABGLEICH=0` (`betrieb.md` 3, 9; ändert 1 und E-216: erwartete
Zahlungen sind im Betrieb vorerst aus). Der Mail-Abgleich selbst bleibt
unverändert hinter `mail_abgleich`.

### 14.2 Regel

- Bestellnummer = `ddd-ddddddd-ddddddd` (Ziffern), ohne angrenzende Ziffer
  davor oder danach.
- Gesucht in Verwendungszweck und Empfängername jeder Buchung, jeweils auch
  ohne Leerraum (umbrochene Bankzeilen), und in Betreff und Text jeder
  gespiegelten Mail, unabhängig vom Absender; bei Mails mit Rohfassung
  (IMAP) zusätzlich in allen Textteilen der Rohfassung (Klartext und HTML
  samt Verweisadressen).
- Je Treffer (Buchung, Mail) hängt die ganze Mail als Dokument
  (`message/rfc822`, Quelle `mail`, wie `dokumente.md` 2.2) und jeder
  PDF-Anhang als PDF-Dokument (Quelle `mail`) an der Buchung. Beträge, Datum
  und Anbieter spielen keine Rolle. Mehrere Buchungen mit derselben Nummer
  bekommen alle dieselben Mails; dieselbe Mail (Nachrichten-ID) in zwei
  Postfächern zählt einmal. Hängt an der Buchung schon ein Dokument gleichen
  Inhalts, entsteht kein zweites.

### 14.3 Zeitpunkt und Protokoll

Nach jedem Mail-Abruf und nach jedem Synchronisationslauf mit Endstatus
(nach dem Mail-Abgleich). Nur wenn etwas angehängt wurde, eine Änderung
`quelle = "mail"`, `aktion = "bestellmail_anhaengen"` (Einträge `dokument`
angelegt, `buchung` geändert mit `dokument_ids`), rückgängig zu machen.

### 14.4 Gemerkte Mails

Je (Buchung, Nachrichten-ID) wird gemerkt, dass die Mail behandelt ist
(Betriebszustand: kein Protokoll, nicht in der Sicherung). Löst der Anwender
ein so angehängtes Dokument oder macht er die Änderung rückgängig, kommt die
Mail nicht von selbst wieder. Nach dem Einspielen einer Sicherung wird das
Gemerkte geleert und neu geprüft (spätestens beim nächsten Abruf).

### 14.5 Mail-Liste

Mit `mail_bestellnummer` trägt jeder Eintrag von `GET /api/mail/nachrichten`
das Feld `angehaengt`: Liste der Buchungen, an denen die Mail über die
Bestellnummer hängt, `{id, datum, konto_id, empfaenger, verwendungszweck,
nummer, warum}` (`nummer` = die Bestellnummer, `warum` Text, frei). Solche
Mails zählen in `stand` und im Filter `zuordnung` als `zugeordnet` (mail.md
6.6). Ohne die Einstellung fehlt das Feld.

## 15. Meilenstein 32: Anbieter-Beschreibungen, PayPal, geplante Zahlungen

- Erkennung über Anbieter-Beschreibungen (TOML, `anbieter_verzeichnis`),
  `anbieter` = Name der Beschreibung: `sammel3.md` 9.1 (E-301).
- PayPal: Zuordnung nach Betrag, ± 5 Tagen und Händlername in Teilen; ersetzt
  den zweiten Punkt von 5.2 für PayPal: `sammel3.md` 9.2 (E-302).
- Geplante Zahlungen (Grund `manuell`): Wiederholung, Fortsetzung, Zuordnung
  nach Namen, Vorschau, Sicherung `schemaversion` ≥ 10: `sammel3.md` 14
  (E-303).
