# Berichte und Export – Meilenstein 5

Verbindlich für Implementierung und Tests. Umsetzung von K 11
(„Kontostandsverlauf pro Konto als Liniendiagramm“), K 14 („Export: CSV und
PDF, z. B. für Steuer und Archiv“), T 15, T 14 („CSV-Export ist verlustfrei
wieder einlesbar (Rundreise-Test), PDF-Export enthält alle gefilterten
Buchungen“) und T 11 / E-059 (Umbuchungen in Statistiken). Ergänzt
`python-api.md` 12 und `openapi.yaml` (Tags `berichte`, `export`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Berichte und Export lesen nur; sie ändern nichts, erzeugen keine Änderung
und haben keinen eigenen Zustand. Die Oberfläche (M8) zeichnet aus den
Datenreihen das Liniendiagramm.

## 1. Zeitraum und Intervalle (gemeinsam)

- Parameter `von`, `bis` (date). Vorgabe `bis` = *heute* (App-Uhr,
  `synchronisation.md` 8); Vorgabe `von` = kleinstes `datum` aller Buchungen,
  höchstens `bis`; ohne Buchungen `von = bis`. `von > bis` → 422
  `validierung`.
- Parameter `intervall` ∈ {`tag`, `woche`, `monat`, `jahr`}, Vorgabe
  `monat`. **Intervallende**: `tag` jeder Tag; `woche` jeder Sonntag
  (Wochen Montag–Sonntag, ISO 8601); `monat` der letzte Tag jedes Monats;
  `jahr` der 31.12.
- **Perioden** (für 3): die Intervalle, die `[von, bis]` schneiden, jeweils
  auf `[von, bis]` beschnitten, aufsteigend. Beispiel `monat`,
  `von = 2024-01-15`, `bis = 2024-03-10`: `[01-15, 01-31]`,
  `[02-01, 02-29]`, `[03-01, 03-10]`.
- Höchstens 5 000 Stichtage bzw. Perioden je Bericht, sonst 422
  `bericht_zu_gross`.

## 2. Kontostandsverlauf (K 11, T 15)

`GET /api/berichte/kontostand` mit `konto_id` (mehrfach, optional), `von`,
`bis`, `intervall`, `unterkonten` (bool, Vorgabe false):

- **Konten**: die angegebenen (Doppelte zusammengefasst, nach `id`
  aufsteigend), beliebiger Art; ohne Angabe alle Bestandskonten nach `id`.
  Unbekannte → 422 `referenz_unbekannt` (`details.konto_ids`, aufsteigend).
- **Stichtage**: `von`; danach jedes Intervallende `e` mit `von < e < bis`;
  zuletzt `bis`, falls `bis > von`. (Bei `intervall = tag` also jeder Tag.)
- **Wert** am Stichtag `s`: `saldo(k, s)` (`datenmodell.md` 2: Summe aller
  Splits auf `k` von Buchungen mit `datum ≤ s`), bei `unterkonten = true`
  `saldo_gesamt(k, s)`. Also genau die Werte der Kontenübersicht mit
  `stichtag = s` (T 15).
- Antwort 200 `KontostandBericht = {von, bis, intervall, unterkonten,
  stichtage: [date], reihen: [{konto_id, name, art, werte: [int]}]}`;
  `werte` hat dieselbe Länge wie `stichtage`. Ein Konto ohne Buchungen hat
  überall 0; ein Zeitraum ohne Buchungen hat konstante Werte; Buchungen nach
  `bis` zählen nicht.

## 3. Einnahmen und Ausgaben (E-059, T 11)

`GET /api/berichte/einnahmen-ausgaben` mit `von`, `bis`, `intervall`,
`konto_id` (mehrfach, optional; nur Bestandskonten, sonst 422
`konto_ungueltig`; unbekannt 422 `referenz_unbekannt`):

- **Berücksichtigte Buchungen**: `datum` in `[von, bis]`; mit `konto_id`
  nur Buchungen mit mindestens einem Split auf einem dieser Konten.
- Je Periode (1): `einnahmen = −Σ` Beträge aller Splits auf Konten der Art
  `ertrag`, `ausgaben = Σ` Beträge aller Splits auf Konten der Art
  `aufwand` (Erstattungen mindern die Ausgaben, Werte können negativ sein),
  `saldo = einnahmen − ausgaben`, `nicht_kategorisiert = Σ` Beträge der
  Splits auf dem technischen Konto „Unkategorisiert“
  (`kontor:unkategorisiert`, Soll positiv: unkategorisierte Ausgaben
  zählen positiv).
- **Umbuchungen** (Buchungen nur zwischen Bestandskonten,
  `ist_umbuchung`) buchen auf kein Aufwands- oder Ertragskonto und zählen
  daher weder als Einnahme noch als Ausgabe (T 11); Splits auf
  Bestands- und Eigenkapitalkonten (außer „Unkategorisiert“) zählen nie.
  Die Tilgung eines Kredits ist keine Ausgabe, der Zinsanteil schon.
- Antwort 200 `EinnahmenAusgabenBericht = {von, bis, intervall, perioden:
  [{von, bis, einnahmen, ausgaben, saldo, nicht_kategorisiert}], gesamt:
  {einnahmen, ausgaben, saldo, nicht_kategorisiert}, kategorien:
  [{kategorie_id, name, art, summe}]}`; `gesamt` = Summe über alle
  Perioden; `kategorien` = alle Konten der Arten `aufwand`/`ertrag` mit
  mindestens einem berücksichtigten Split, nach `id` aufsteigend, `summe` =
  Summe ihrer Splits (vorzeichenbehaftet, ohne Unterkonten).

## 4. CSV-Export (K 14, T 14)

`GET /api/export/buchungen.csv` mit **allen Filter- und
Sortierparametern** von `GET /api/buchungen` (außer `seite`, `pro_seite`;
gleiche Bedeutung und gleiche 422-Fälle): alle passenden Buchungen in der
Reihenfolge der Buchungsliste.

### 4.1 Format

- `Content-Type: text/csv; charset=utf-8`;
  `Content-Disposition: attachment; filename="kontor-buchungen-<JJJJMMTT>.csv"`
  (*heute*).
- Kodierung UTF-8 **mit** BOM (`EF BB BF`), Trennzeichen `;`,
  Zeilenende `\r\n` (auch nach der letzten Zeile), Textbegrenzer `"`.
  Ein Feld wird genau dann in `"` eingeschlossen, wenn es `;`, `"`, `\r`
  oder `\n` enthält; `"` im Feld wird verdoppelt (RFC 4180; genau wie
  Pythons `csv.writer(f, delimiter=";", lineterminator="\r\n")` mit
  `QUOTE_MINIMAL`). Kein weiteres Escaping, keine Kürzung, keine Umwandlung
  von Zeichen; Leerraum am Feldrand bleibt erhalten.
- Erste Zeile: die Spaltennamen. Danach **eine Zeile je Split**; die
  Buchungsfelder stehen in jeder Zeile der Buchung.

### 4.2 Spalten (genau diese, in dieser Reihenfolge)

| Spalte | Inhalt |
| --- | --- |
| `buchung_id` | `id` der Buchung |
| `datum` | `YYYY-MM-DD` |
| `empfaenger` | Name des Empfängers; leer, wenn keiner |
| `verwendungszweck` | unverändert |
| `status` | z. B. `importiert` |
| `kategorie` | Name des Kontos `kategorie_id`; leer, wenn null |
| `tags` | JSON-Liste der Tag-Namen nach Tag-`id` aufsteigend, z. B. `["Steuer","Urlaub"]` (`json.dumps(…, ensure_ascii=False)` mit Standardtrennern `", "`) |
| `extern_ids` | JSON-Liste wie `extern_ids` |
| `gegen_iban` | IBAN oder leer |
| `split_nr` | Position des Splits in der Buchung, ab 1 |
| `split_id` | `id` des Splits |
| `konto_id` | Konto des Splits |
| `konto` | Name dieses Kontos |
| `betrag` | Split-Betrag in Euro mit Dezimalkomma und genau zwei Nachkommastellen, ohne Tausendertrennzeichen, Minus vorangestellt: `-12,34`, `0,00`, `1234567,89` |
| `memo` | Memo des Splits |
| `abstimmung_id` | `abstimmung_id` des Splits oder leer |

**Verlustfrei** (Rundreise, T 14): Aus der Datei lassen sich alle Felder der
Protokollform jeder exportierten Buchung (`protokoll.md` 2) außer
`vorschlag` eindeutig zurückgewinnen – `empfaenger_id` über den
eindeutigen Empfängernamen, `tag_ids` über die (unter `casefold`)
eindeutigen Tag-Namen, alle übrigen Felder direkt; dazu Kategorie- und
Kontonamen. Gleitkommazahlen kommen nicht vor (`betrag` ist exakt in
ganzen Cent umrechenbar).

## 5. PDF-Export (K 14, T 14)

`GET /api/export/buchungen.pdf` mit denselben Parametern wie 4: alle
passenden Buchungen in derselben Reihenfolge.

- `Content-Type: application/pdf`; `Content-Disposition: attachment;
  filename="kontor-buchungen-<JJJJMMTT>.pdf"`.
- Erzeugung ohne Netzwerk und ohne externe Programme, mit einer per pip
  installierbaren Bibliothek (geprüft 2026-11-09: `reportlab` 5.x und
  `fpdf2` 2.x, beide als reine Python-Wheels verfügbar) oder der
  Standardbibliothek. Schriften werden nicht aus dem Netz geladen.
- **Prüfbare Eigenschaften** (Tests lesen den Text mit `pypdf`,
  `PdfReader(...).pages[i].extract_text()`):
  1. Die Datei beginnt mit `%PDF-1.` und enthält `%%EOF` in ihren letzten
     1 024 Bytes; `pypdf` öffnet sie ohne Fehler; mindestens eine Seite.
  2. Der Text ist als Text extrahierbar (keine Bilder); die Marken unten
     stehen in Schriften mit Unicode-Zuordnung (z. B. Standardschrift
     Helvetica).
  3. Je exportierter Buchung genau eine **Marke** `[#<id>]` (z. B.
     `[#17]`), in derselben Textzeile wie ihr Datum im Format `TT.MM.JJJJ`
     und ihr Betrag (`betrag` nach `datenmodell.md` 3.3, also mit
     `konto_id`-Filter der Kontobetrag, sonst der Umsatz) im Format von 4.2
     (`-12,34`). Keine anderen Marken dieser Form. Empfänger und
     Verwendungszweck dürfen gekürzt sein; nicht darstellbare Zeichen dürfen
     ersetzt werden.
  4. Der Text enthält genau einmal `Anzahl Buchungen: <n>` mit `n` = Zahl
     der exportierten Buchungen.
- Seitenformat, Layout und weitere Inhalte (Splits, Kopf- und Fußzeilen)
  sind frei. Mindestens 5 000 Buchungen werden unterstützt.

## 6. REST-Endpunkte (Überblick; Schemas in `openapi.yaml`)

| Methode, Pfad | Zweck |
| --- | --- |
| `GET /api/berichte/kontostand` | Kontostandsverlauf (2) |
| `GET /api/berichte/einnahmen-ausgaben` | Einnahmen und Ausgaben (3) |
| `GET /api/export/buchungen.csv` | CSV-Export (4) |
| `GET /api/export/buchungen.pdf` | PDF-Export (5) |

Neuer Fehlercode: `bericht_zu_gross`.

## 6. Meilenstein 31: Monatsbericht und weitere Berichte (Definition 3, D-206, D-217; E-282)

Alle Endpunkte lesen nur: kein Zustand, kein Protokoll, nichts in der
Sicherung. Unbekannte Query-Parameter → 422 `validierung`.

### 6.1 Wirkung einer Buchung

Wirkung = negierte Summe ihrer Splits auf Konten, die weder Bestandskonten
noch Eigenkapitalkonten außer „Unkategorisiert“ sind (Anfangsbestand und
Korrekturen sind neutral). Wirkung 0 ist eine Umbuchung zwischen eigenen
Konten. Negative Wirkung ist eine Ausgabe, positive eine Einnahme. Ein
Eingang, der nur gegen Aufwandskonten gebucht ist, ist eine **Erstattung**
und mindert die Ausgaben (auch unter null); eine nicht kategorisierte
Erstattung (auf „Unkategorisiert“) zählt als Einnahme.

### 6.2 `GET /api/berichte/monat`

- `monat` = `JJJJ-MM` (Vorgabe: laufender Monat der App-Uhr); andere Form →
  422 `validierung`. `konto_id` mehrfach: unbekannt → 422
  `referenz_unbekannt` (`details.konto_ids`); kein Bestandskonto → 422
  `konto_ungueltig`. Vorgabe: alle Bestandskonten ohne Darlehenskonten
  (Konto, das ein Kredit als `konto_id` führt, `kredite.md`).
- Berücksichtigt werden Buchungen des Monats mit mindestens einem Split auf
  einem der Konten (im laufenden Monat bis heute).
- Pflichtfelder (E-282): `monat`, `konto_ids` (wirksame Konten nach `id`),
  `ausgaben` (Summe der Ausgaben als positive Cent, abzüglich Erstattungen),
  `einnahmen` (Summe der positiven Wirkungen ohne Erstattungen, Cent),
  `fest` (Anteil von `ausgaben` aus Ausgaben, die zu einer Serie der
  Erkennung wiederkehrender Buchungen mit den Betragsfiltern zum Stichtag
  gehören), `variabel` = `ausgaben − fest`, `umbuchungen` (Anzahl der
  Buchungen mit Wirkung 0). Weitere Angaben der Definition (Hochrechnung,
  Vergleiche, „üblich“, Ausreißer, neue Empfänger, Größenklassen) in
  weiteren Feldern frei.

### 6.3 Weitere Berichte

`GET /api/berichte/vertraege`, `jahr`, `vorschau`, `vermoegen`,
`kategorien`, `empfaenger`, `geldfluss`, `qualitaet`, `tags`: Inhalt nach
Definition 3, Abschnitt 9 (D-217); Aufbau der Antworten frei (Objekt). Ohne
Parameter 200.
