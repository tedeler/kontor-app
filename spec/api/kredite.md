# Kredite – Meilenstein 5

Verbindlich für Implementierung und Tests. Umsetzung von K 10
(„Abbildung laufender Annuitätendarlehen ohne direkten Kontozugriff.
Parameter: Restschuld, Sollzins, Rate, Zinsberechnungsmethode (wählbar:
30/360 als Standard, act/360, act/365), Sondertilgungen. Automatische
Aufteilung: Ratenzahlung vom Girokonto wird in Zinsanteil (Kategorie
Zinsen) und Tilgungsanteil (Minderung der Restschuld) gesplittet. Diese
Buchungen sind ‚vorläufig‘. Jahresabgleich: Eingabe von Restschuld und
gezahlten Zinsen laut Jahresauszug. Die Anwendung vergleicht mit der eigenen
Berechnung und erzeugt eine Korrekturbuchung zur Bestätigung. Danach werden
die Buchungen des Jahres als ‚abgeglichen‘ markiert.“), T 12 und T 22
(Rundung). Ergänzt `datenmodell.md` 15, `synchronisation.md` 17,
`protokoll.md` 11, `sicherung.md` 2.5, `python-api.md` 12 und
`openapi.yaml` (Tag `kredite`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Ohne Kredite verhält sich die Anwendung exakt wie nach M4 und M9 (E-029).

## 1. Begriffe

- **Darlehenskonto** (`konto_id`): ein Konto der Art `kreditkonto` ohne
  Bankzugriff (K 10). Sein Saldo ist die gebuchte Restschuld mit negativem
  Vorzeichen (Schulden, `datenmodell.md` 2): *gebuchte Restschuld* am
  Stichtag `s` = `−saldo(konto_id, s)`.
- **Zahlungskonto** (`zahlungskonto_id`): das Bestandskonto, von dem die
  Raten abgehen (meist das Girokonto).
- **Zinskonto** (`zins_konto_id`): die Kategorie „Zinsen“ (Art `aufwand`).
- **Tilgungsplan**: die aus den Parametern berechnete Folge der Raten (3).
  Er ist eine Funktion der Parameter, kein eigener Zustand.
- **Buchungen des Kredits**: die Buchungen in `zuordnungen` (Raten) und die
  Korrekturbuchungen in `abgleiche` (5).
- Monatliche Raten. Andere Ratenrhythmen sind nicht vorgesehen (E-102).
- `monat_plus(d, n)`: das Datum `d` um `n` Kalendermonate verschoben; der
  Tag wird auf den letzten Tag des Zielmonats begrenzt
  (`monat_plus(2024-01-31, 1) = 2024-02-29`).

## 2. Kredit (`Kredit`, protokolliertes Objekt `kredit`)

| Feld | Typ | Pflicht beim Anlegen | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `name` | str | ja | 1–200 Zeichen nach `strip()` (gestrippt gespeichert) |
| `konto_id` | int | ja | Darlehenskonto: existierendes Konto der Art `kreditkonto`; höchstens ein Kredit je Konto; nach dem Anlegen unveränderlich |
| `zahlungskonto_id` | int | ja | existierendes Bestandskonto, ≠ `konto_id` |
| `zins_konto_id` | int | ja | existierendes Konto der Art `aufwand` |
| `restschuld` | int | ja | Restschuld in Cent am `stand_datum`, 1 ≤ r ≤ 999 999 999 999 |
| `stand_datum` | date | ja | Stichtag der Restschuld |
| `sollzins` | int | ja | Sollzins p. a. in **Millionstel**: 3,45 % = 0,0345 = `34500`; 0 ≤ p ≤ 1 000 000 |
| `zinsmethode` | `"30/360"` \| `"act/360"` \| `"act/365"` | nein (`"30/360"`) | 3.2 |
| `rate` | int | ja | monatliche Rate (Zins + Tilgung) in Cent, 1 ≤ a ≤ 999 999 999 999 |
| `erste_faelligkeit` | date | ja | Fälligkeit der ersten Rate, `> stand_datum` |
| `sondertilgungen` | Liste `{datum, betrag}` | nein (`[]`) | 0–100 Einträge, `datum > stand_datum`, `1 ≤ betrag ≤ 999 999 999 999`; gespeichert nach `datum` aufsteigend, bei gleichem Datum in Eingabereihenfolge |
| `bedingungen` | Liste Bedingung | ja | 1–20, UND-verknüpft, Schema `BedingungText` (`kategorisierung.md` 1.1: Felder `empfaenger`, `verwendungszweck`); Erkennung der Ratenzahlung (4) |
| `aktiv` | bool | nein (true) | inaktive Kredite werden bei der Synchronisation nicht erkannt (4.2) |
| `zuordnungen` | Liste `{faelligkeit, buchung_id}` | – (nur lesbar, anfangs `[]`) | welche Buchung welche Rate ist (4); nach `faelligkeit` aufsteigend; je Fälligkeit höchstens ein Eintrag, jede Buchung höchstens einmal über alle Kredite |
| `abgleiche` | Liste `{jahr, restschuld, zinsen, buchung_id}` | – (nur lesbar, anfangs `[]`) | durchgeführte Jahresabgleiche (5); nach `jahr` aufsteigend; `buchung_id` = Korrekturbuchung oder null |

Der Kredit enthält keine abgeleiteten Felder, die sich mit Buchungen ändern;
seine Protokollform (`protokoll.md` 11) ist genau dieses Schema.

### 2.1 Anlegen (`POST /api/kredite`)

Körper `KreditNeu` = alle Pflichtfelder und optionalen Felder aus 2 (ohne
`id`, `zuordnungen`, `abgleiche`), dazu `saldo_angleichen: bool = true`
(wird nicht gespeichert).

**Fehler** (Prüfreihenfolge, die erste zutreffende bestimmt die Antwort,
nichts wird geändert):

1. 422 `validierung`: Schema (unbekannte Felder, Typen, Grenzen),
   `erste_faelligkeit ≤ stand_datum`, eine Sondertilgung mit
   `datum ≤ stand_datum`.
2. 422 `referenz_unbekannt`: `konto_id`, `zahlungskonto_id` oder
   `zins_konto_id` existiert nicht (`details.konto_ids`, aufsteigend).
3. 422 `konto_ungueltig`: `konto_id` ist kein Konto der Art `kreditkonto`;
   `zahlungskonto_id` ist kein Bestandskonto oder gleich `konto_id`.
4. 422 `kategorie_ungueltig`: `zins_konto_id` ist kein Konto der Art
   `aufwand`.
5. 409 `kredit_konto_belegt`: ein anderer Kredit hat dieselbe `konto_id`
   (`details.kredit_id`).
6. 422 `kredit_rate_zu_klein`: der Tilgungsplan (3) endet nicht innerhalb
   von 1 200 Raten.

**Wirkung:** Der Kredit wird angelegt. Ist `saldo_angleichen = true` und
`x = −restschuld − saldo(konto_id, stand_datum) ≠ 0`, wird zusätzlich eine
*Anfangsbuchung* angelegt: `datum = stand_datum`, ohne Empfänger,
`verwendungszweck = "Anfangsbestand " + name`, `status = "bestaetigt"`,
Splits `[{konto_id, x, ""}, {„Korrekturen“, −x, ""}]` (technisches Konto
`kontor:korrektur`, `buchhaltungspflege.md` 1.4, bei Bedarf angelegt).
Danach ist die gebuchte Restschuld am `stand_datum` gleich `restschuld`. Die
Anfangsbuchung ist keine Buchung des Kredits. Antwort 201 `Kredit`.
Eine Änderung `kredit_anlegen` (Kredit, ggf. Anfangsbuchung und Konto
„Korrekturen“).

### 2.2 Lesen, Ändern, Löschen

- `GET /api/kredite` → alle Kredite nach `id` aufsteigend;
  `GET /api/kredite/{kredit_id}` → 200; 404.
- `PATCH /api/kredite/{kredit_id}` mit `KreditAenderung`: beliebige der
  Felder `name`, `zahlungskonto_id`, `zins_konto_id`, `restschuld`,
  `stand_datum`, `sollzins`, `zinsmethode`, `rate`, `erste_faelligkeit`,
  `sondertilgungen` (ersetzt die Liste), `bedingungen` (ersetzt die Liste),
  `aktiv`. `konto_id`, `zuordnungen`, `abgleiche` und `saldo_angleichen`
  sind nicht änderbar (422 `validierung`). Das Ergebnis wird wie in 2.1
  geprüft (Schritte 1–4 und 6; 404 vor allem anderen). Es entsteht keine
  Buchung; vorhandene Buchungen, Zuordnungen und Abgleiche bleiben
  unverändert. 200; Änderung `kredit_aendern` bei tatsächlicher Wirkung.
- `DELETE /api/kredite/{kredit_id}` → 204; 404. Buchungen bleiben
  unverändert. Änderung `kredit_loeschen`.

### 2.3 Bezüge

- Ein Konto, auf das ein Kredit verweist (`konto_id`, `zahlungskonto_id`,
  `zins_konto_id`), kann weder über `DELETE /api/konten/{id}` noch über
  `POST /api/konten/{id}/loeschen` gelöscht werden: 409
  `konto_in_verwendung` (`details.kredit_ids`), nichts wird geändert (E-110).
- Wird eine Buchung gelöscht, die in `zuordnungen` eines Kredits steht –
  gleich durch welche Operation (`DELETE /api/buchungen/{id}`,
  Dublettenauflösung, Löschen eines Kontos mit Buchungen) –, entfällt dieser
  Eintrag in **derselben** Änderung. Wird eine Korrekturbuchung gelöscht,
  wird `buchung_id` ihres Abgleichs null (der Abgleich bleibt).
- Bezugsprüfung beim Rückgängig (`protokoll.md` 6.1 Schritt 5) zusätzlich:
  die drei Konten jedes Kredits existieren, jede `buchung_id` in
  `zuordnungen` und `abgleiche` (≠ null) existiert, `konto_id` ist über alle
  Kredite eindeutig.

## 3. Tilgungsplan

### 3.1 Fälligkeiten

`F_0 = stand_datum`, `F_i = monat_plus(erste_faelligkeit, i − 1)` für
`i ≥ 1` (verankert an `erste_faelligkeit`, nicht verkettet). Periode `i`
ist das Intervall `(F_{i−1}, F_i]`.

### 3.2 Zinstage und Basis

```python
def tage(methode, a, b):                 # a ≤ b
    if methode == "30/360":              # 30E/360
        return 360 * (b.year - a.year) + 30 * (b.month - a.month) + (min(b.day, 30) - min(a.day, 30))
    return (b - a).days                  # act/360, act/365: tatsächliche Tage

basis = 365 if methode == "act/365" else 360   # act/365 auch im Schaltjahr 365 („fixed“)
```

**Länge** der Periode `i`: `L_i = 30` bei `30/360` und `i ≥ 2` (jede volle
Periode zählt genau einen Monat = 30 Tage, unabhängig von Monatsende und
Februar); sonst `L_i = tage(methode, F_{i−1}, F_i)` (bei `30/360` also nur
die erste, gebrochene Periode nach 30E/360; bei `act/*` die tatsächlichen
Tage, inklusive 29. Februar).

### 3.3 Sondertilgungen

Eine Sondertilgung `S` gehört zur Periode `i` mit `F_{i−1} < S.datum ≤
F_i`. Ihre **Lage** in der Periode ist `pos(S) = min(L_i, tage(methode,
F_{i−1}, S.datum))`. Mehrere Sondertilgungen einer Periode werden in der
gespeicherten Reihenfolge angewendet; jede mindert die laufende Restschuld
`R` um `wirksam = min(S.betrag, R)` (eine Sondertilgung über die Restschuld
hinaus wird auf sie begrenzt). Sondertilgungen nach dem Ende des Plans sind
ohne Wirkung.

### 3.4 Zins einer Periode (Rundung, T 22)

Die Periode `i` zerfällt an den Lagen ihrer Sondertilgungen in Teile
`[0, pos_1], [pos_1, pos_2], …, [pos_k, L_i]` mit den Restschulden
`R_0` (zu Periodenbeginn), `R_1` (nach der ersten Sondertilgung), … `R_k`.
Exakter Zins (rationale Zahl, keine Gleitkommazahl):

`z = Σ_j R_j · sollzins · länge_j / (basis · 1 000 000)`

Der **Zinsanteil** ist `zins_i = ⌊z + 1/2⌋` (kaufmännisch auf ganze Cent;
`z ≥ 0`). Gerundet wird nur der Zins je Rate; alles andere ist exakte
Ganzzahlarithmetik.

### 3.5 Raten

Für `i = 1, 2, …` mit `R` = Restschuld nach Zeile `i − 1` (`R = restschuld`
für `i = 1`):

1. `restschuld_vorher = R`; Sondertilgungen der Periode anwenden (3.3),
   `sondertilgung = Σ wirksam`, danach `R_e = R − sondertilgung`.
2. `zins = zins_i` (3.4).
3. Ist `R_e + zins ≤ rate`: **Schlussrate** `rate_i = R_e + zins`,
   `tilgung = R_e`; der Plan endet nach dieser Zeile. Die Zeile steht auch
   dann im Plan, wenn `rate_i = 0` ist (eine Sondertilgung hat zu Beginn der
   Periode alles getilgt); so bleibt jede Sondertilgung in einer Zeile
   sichtbar. Ein Plan hat daher immer mindestens eine Zeile.
4. Sonst `rate_i = rate`, `tilgung = rate − zins` (kann bei einer langen
   ersten Periode negativ sein).
5. `restschuld_nachher = R_e − tilgung`.

Endet der Plan nicht innerhalb von 1 200 Zeilen → `kredit_rate_zu_klein`.

**Zeile** (`TilgungsplanZeile`): `{nr, faelligkeit, zinstage,
restschuld_vorher, sondertilgung, zins, tilgung, rate, restschuld_nachher}`
mit `nr = i`, `faelligkeit = F_i`, `zinstage = L_i`. Es gilt je Zeile
`rate = zins + tilgung` und `restschuld_nachher = restschuld_vorher −
sondertilgung − tilgung`.

**Plan** (`Tilgungsplan`): `{zeilen, anzahl_raten, summe_zins,
summe_tilgung, summe_sondertilgung, letzte_faelligkeit}`; es gilt
`summe_tilgung + summe_sondertilgung = restschuld` und die letzte Zeile hat
`restschuld_nachher = 0`.

Folgerung (T 12, „kein Auflaufen von Rundungsfehlern“): Die Restschuld
jeder Zeile weicht von der exakten, ungerundeten Rechnung höchstens um die
aufgezinsten Rundungsbeträge (je höchstens ½ Cent) ab; die Summe aus Zins
und Tilgung jeder Rate ist exakt die Rate.

### 3.6 Abruf

- `GET /api/kredite/{kredit_id}/plan` → 200 `Tilgungsplan` aus den
  gespeicherten Parametern; 404.
- `POST /api/kredite/tilgungsplan` mit `KreditParameter` (`restschuld`,
  `stand_datum`, `sollzins`, `zinsmethode` (Vorgabe `"30/360"`), `rate`,
  `erste_faelligkeit`, `sondertilgungen` (Vorgabe `[]`)) → 200
  `Tilgungsplan`, ohne etwas zu speichern; 422 `validierung` (wie 2.1
  Schritt 1), 422 `kredit_rate_zu_klein`. Erzeugt keine Änderung.
- Python: `kontor.kredite.tilgungsplan(parameter)` (`python-api.md` 12).

## 4. Ratenzahlungen erkennen und aufteilen

### 4.1 Passende Rate

Eine Zahlung mit Datum `d` und Betrag `x` auf dem Zahlungskonto passt zur
Zeile `i` des Plans eines Kredits `K`, wenn `rate_i > 0`, `x = −rate_i`,
`|d − F_i| ≤ 5` Tage (Wochenend- und Feiertagsverschiebung) und für `F_i`
noch keine Zuordnung besteht (auch keine aus demselben Vorgang). Passen
mehrere Zeilen, gilt die mit dem kleinsten `|d − F_i|`, bei Gleichstand die
frühere. Die Bedingungen (`kategorisierung.md` 4, Texte normalisiert wie bei
Regeln und Vorlagen) werden auf Empfängername und Verwendungszweck
angewendet.

**Aufteilung** nach Zeile `i`: Splits `[z, {zins_konto_id, zins_i,
"Zinsanteil"}, {konto_id, tilgung_i, "Tilgungsanteil"}]` mit `z` = Split auf
dem Zahlungskonto (Betrag `−rate_i`); `status = "vorlaeufig"` (K 10);
`vorschlag = null`; `K.zuordnungen` erhält `{faelligkeit: F_i, buchung_id}`.
Der Zinssplit steht auch bei `zins_i = 0` in der Buchung. Das Setzen von
`vorlaeufig` ist eine automatische Wirkung und unterliegt nicht den
Statusübergängen aus `datenmodell.md` 3.1.

### 4.2 Synchronisation

Für jeden neuen Umsatz (`synchronisation.md` 4.2 und 17) wird **vor** den
Split-Vorlagen geprüft: Ist das zugeordnete Konto das Zahlungskonto eines
aktiven Kredits, treffen dessen Bedingungen zu (Empfängername nach
`synchronisation.md` 14.1, Verwendungszweck) und passt eine Rate (4.1), wird
die Buchung mit `[{Konto, betrag, ""}, Zinssplit, Tilgungssplit]` und
`status = "vorlaeufig"` angelegt; Vorlagen, Regeln, Standardkategorie und
Lernmodell werden nicht ausgewertet. Bei mehreren Krediten gilt der mit der
kleinsten `id`, für den eine Rate passt. Zählt in
`SyncKonto.buchungen_kredit` (Teilmenge von `buchungen_neu`). Die geänderte
Zuordnung gehört zur Änderung `sync_konto` des Kontos. Für Umsätze, die mit
vorhandenen Buchungen zusammengeführt werden oder deren Kennung gemerkt ist,
wird kein Kredit ausgewertet. Passt keine Rate (z. B. Sondertilgung, andere
Höhe), läuft die Kategorisierung normal weiter (keine Benachrichtigung).

### 4.3 Vorhandene Buchungen zuordnen

`POST /api/kredite/{kredit_id}/zuordnen` mit `{buchung_ids?: [int],
trocken: bool = false}`:

1. 404 (Kredit); 422 `validierung` (Schema, doppelte IDs); 422
   `referenz_unbekannt` (`details.buchung_ids`, aufsteigend).
2. *Geprüfte Buchungen*: alle (bzw. nur `buchung_ids`), die nicht gesperrt
   sind, in keinem Kredit zugeordnet sind, genau zwei Splits haben, davon
   genau einen auf dem Zahlungskonto mit negativem Betrag und den anderen
   auf einem Konto, das kein Bestandskonto ist, und deren Empfängername und
   Verwendungszweck die Bedingungen erfüllen. `aktiv` spielt hier keine
   Rolle. Andere werden stillschweigend übergangen.
3. Die geprüften Buchungen werden nach (`datum`, `id`) nacheinander
   behandelt: passt eine Rate (4.1, Zuordnungen dieses Vorgangs zählen
   mit), werden die Splits ersetzt (der Split auf dem Zahlungskonto bleibt
   mit `id`, Betrag und Memo an erster Stelle, Zins- und Tilgungssplit
   erhalten neue IDs), `status = "vorlaeufig"`, `vorschlag = null`, und die
   Zuordnung wird eingetragen.
4. Atomar; eine Änderung `quelle = "kredit"`, `aktion = "kredit_zuordnen"`,
   `gruppe = null`, wenn sich etwas ändert. `trocken = true` ändert nichts,
   die Antwort ist dieselbe.

Antwort 200 `KreditZuordnung = {trocken, geprueft, anzahl, zuordnungen:
[{buchung_id, faelligkeit, zins, tilgung}]}` in der Reihenfolge von
Schritt 3; `anzahl` = Länge von `zuordnungen`.

## 5. Jahresabgleich

`POST /api/kredite/{kredit_id}/jahresabgleich` mit `{jahr, restschuld,
zinsen, trocken: bool = false}` (Werte laut Jahresauszug; `jahr` 1900–9999,
`restschuld` und `zinsen` 0 ≤ v ≤ 999 999 999 999):

1. 404; 422 `validierung`; 409 `kredit_jahr_abgeglichen`, wenn es für
   `jahr` schon einen Abgleich gibt.
2. Stichtag `s` = 31.12. des Jahres.
   `restschuld_berechnet = −saldo(konto_id, s)` (gebuchte Restschuld,
   `datenmodell.md` 2, alle Splits bis einschließlich `s`).
   `zinsen_berechnet` = Summe der Splits auf `zins_konto_id` aller
   Buchungen des Kredits (1) mit `datum` im Jahr.
3. `differenz_restschuld = restschuld − restschuld_berechnet`,
   `differenz_zinsen = zinsen − zinsen_berechnet`.
4. **Korrekturbuchung** genau dann, wenn eine Differenz ≠ 0 ist (genau
   eine, T 12): `datum = s`, ohne Empfänger,
   `verwendungszweck = "Jahresabgleich " + jahr + " " + name`, `status =
   "abgeglichen"`, Splits in dieser Reihenfolge, jeweils nur wenn ≠ 0:
   `{zins_konto_id, dz, "Zinskorrektur"}`, `{konto_id, −dr,
   "Restschuldkorrektur"}`, `{„Korrekturen“, dr − dz, ""}` mit
   `dz = differenz_zinsen`, `dr = differenz_restschuld`. (Bei `dz = dr`
   wird also nur Tilgung in Zins umgebucht; das Konto „Korrekturen“,
   `kontor:korrektur`, wird bei Bedarf angelegt.) Die Splits summieren sich
   zu 0. Danach stimmen gebuchte Restschuld am Stichtag und
   Zinssumme der Buchungen des Kredits im Jahr mit dem Auszug überein.
5. Alle Buchungen in `zuordnungen` mit `datum` im Jahr und `status ≠
   "abgeglichen"` erhalten `status = "abgeglichen"` (zulässig aus
   `vorlaeufig` und `bestaetigt`; auch gesperrte, da nur der Status sich
   ändert). Sie sind danach gesperrt (`datenmodell.md` 3.1).
6. `abgleiche` erhält `{jahr, restschuld, zinsen, buchung_id}`
   (Korrekturbuchung oder null).
7. Atomar; eine Änderung `quelle = "manuell"`, `aktion =
   "kredit_jahresabgleich"`, `gruppe = null`. Mit `trocken = true` ändert
   sich nichts; die Antwort ist dieselbe, nur `korrektur_buchung = null`.

Die „Bestätigung“ aus K 10 ist der Aufruf ohne `trocken`; die Oberfläche
zeigt vorher das Ergebnis des Probelaufs. Der Tilgungsplan wird durch den
Abgleich nicht verändert (keine Neuverankerung, E-105); neue Parameter
setzt der Anwender mit `PATCH`.

Antwort 200 `KreditAbgleich = {kredit_id, jahr, trocken, restschuld, zinsen,
restschuld_berechnet, zinsen_berechnet, differenz_restschuld,
differenz_zinsen, korrektur_splits: [{konto_id, betrag, memo}],
korrektur_buchung: Buchung | null, abgeglichen_buchung_ids: [int]}`
(`korrektur_splits` leer, wenn keine Korrektur nötig; im Probelauf hat ein
Split auf das noch nicht vorhandene Konto „Korrekturen“ `konto_id = null`, weil
der Probelauf nichts anlegt; `abgeglichen_buchung_ids` = die in Schritt 5
geänderten bzw. zu ändernden Buchungen, aufsteigend).

## 6. Sondertilgungen (E-104)

Sondertilgungen sind Parameter des Plans (2, 3.3): Sie mindern die
Restschuld an ihrem Datum und damit alle späteren Zinsanteile. Die Zahlung
selbst bucht der Anwender (z. B. `POST /api/buchungen/erfassen` mit
`art = "umbuchung"` vom Zahlungskonto auf das Darlehenskonto, oder die von
der Synchronisation übernommene Buchung mit `PUT …/splits` auf das
Darlehenskonto umstellen); sie wird nicht automatisch aufgeteilt (4.2, der
Betrag ist keine Rate). Fehlt die Buchung, zeigt der nächste Jahresabgleich
die Differenz.

## 7. REST-Endpunkte (Überblick; Schemas in `openapi.yaml`)

| Methode, Pfad | Zweck |
| --- | --- |
| `GET /api/kredite`, `POST /api/kredite` | Liste, anlegen (2.1) |
| `GET/PATCH/DELETE /api/kredite/{kredit_id}` | lesen, ändern, löschen (2.2) |
| `GET /api/kredite/{kredit_id}/plan` | Tilgungsplan des Kredits (3) |
| `POST /api/kredite/tilgungsplan` | Tilgungsplan aus Parametern, ohne Speichern (3.6) |
| `POST /api/kredite/{kredit_id}/zuordnen` | vorhandene Buchungen als Raten aufteilen (4.3) |
| `POST /api/kredite/{kredit_id}/jahresabgleich` | Jahresabgleich (5) |

Neue Fehlercodes: `kredit_konto_belegt`, `kredit_rate_zu_klein`,
`kredit_jahr_abgeglichen`.
