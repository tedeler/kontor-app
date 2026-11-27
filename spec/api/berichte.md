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

## 7. Sonderposten (Feature `sonderposten`, D-300)

Einmalige große Posten wie ein Autokauf verfälschen Schnitte, Vergleiche und Ranglisten. Eine Buchung ist ein
**Sonderposten**, wenn sie den Tag „Sonderposten“ trägt (Name ohne Groß- und Kleinschreibung; nur Tags der Buchung,
nicht Tags des Empfängers). Es gibt keinen weiteren Zustand.

- **Parameter** `sonderposten` (`ohne` | `mit`, Vorgabe `ohne`) an `GET /api/berichte/einnahmen-ausgaben`, `monat`,
  `jahr`, `kategorien`, `empfaenger` und `geldfluss`; ein anderer Wert ergibt 422 `validierung`.
- Mit `ohne` zählen Sonderposten in keiner Zahl des Berichts: Summen, Monate, Vorjahresvergleich, Schnitte,
  Ranglisten, größte Buchungen, Kategorien, Fluss, Ausreißer und Einzelbuchungen.
- **Antwortfeld** `sonderposten` in diesen Berichten (in beiden Modi): `modus`, `tag_id` (null ohne den Tag),
  `anzahl`, `ausgaben` (Beitrag zu den Ausgaben in Cent, Erstattungen mindern), `einnahmen`, `eintraege` (Form wie
  `top_buchungen.eintraege`, nach Datum) – die Sonderposten im Zeitraum des Berichts; beim Empfängerbericht eines
  Empfängers nur dessen, bei der Rangliste die der zwölf Monate.
- Kontostand, Vorschau, Vermögen, Verträge, Datenqualität und Tag-Bericht zählen Sonderposten immer mit (echtes Geld
  bzw. eigene Auswahl); sie kennen den Parameter nicht.
- **Vorschlag im Monatsbericht:** `auffaellig.sonderposten` listet nicht feste Ausgaben des Monats ab 2.000 €, die
  mindestens die Hälfte des Monatsschnitts der Ausgaben der zwölf Monate davor ausmachen (ohne Schnitt nur die
  Grenze): `{buchung, ueblich_monat}`, größte zuerst. Bereits markierte Sonderposten erscheinen dort mit `ohne` nicht.
- **Oberfläche:** In Monat, Jahr, Kategorien, Empfänger und Geldfluss steht der Schalter
  `bericht-sonderposten-schalter` „ohne Sonderposten“ (sobald es den Tag gibt; Adresse `sonderposten=mit`, wenn aus),
  die Standzeile nennt Anzahl und Betrag, und der Kasten `bericht-sonderposten` listet die Posten (`bericht-
  sonderposten-<id>`, Klick zeigt die Buchung im Kontoblatt). Auf der Seite Berichte hat „Einnahmen und Ausgaben“ den
  Haken `bericht-ea-sonderposten`. Im Monatsbericht hat jeder Vorschlag den Knopf `mb-sonderposten-markieren-<id>`.
  Im Kontoblatt markiert `p` bzw. das Kontextmenü `km-sonderposten` die Buchungen oder nimmt die Markierung zurück
  (legt den Tag bei Bedarf an).

## 8. Nachweis markierter Buchungen als PDF (Feature `nachweis-pdf`, D-303)

Nur lesend: kein Zustand, kein Protokoll, nichts in der Sicherung. Noch nicht im OpenAPI-Vertrag (wie D-217).

- **`GET /api/export/nachweis.pdf?konto_id=<id>&buchung_id=<id>[&buchung_id=…][&inhaber=<text>]`** liefert
  `application/pdf` mit `Content-Disposition: attachment; filename="kontor-nachweis-<JJJJMMTT>.pdf"` und
  `Cache-Control: no-store`.
  - `konto_id` Pflicht; Konto fehlt → 404 `nicht_gefunden`; kein Bestandskonto (Kategorie, Eigenkapital) → 422
    `kein_bestandskonto`.
  - `buchung_id` 1 bis 500 verschiedene Werte (doppelte zählen einmal), sonst 422 `validierung`; eine fehlt → 404
    `nicht_gefunden`; eine ohne Split auf dem Konto → 422 `buchung_nicht_im_konto` (`details.buchung_ids`).
  - `inhaber` höchstens 200 Zeichen (sonst 422); fehlt der Parameter, gilt der Kontoinhaber aus den Kontodaten der
    Bank (leer → „–“). Unbekannte Parameter → 422.
- **Inhalt** (Text mit `pypdf` extrahierbar): Kopf „KONTOR Homebanking-Software“, Auszugsdatum = heute (App-Uhr),
  Titel „Kontoauszug“ mit „Nachweis ausgewählter Buchungen · kein Dokument der Bank“; Kontoinhaber, IBAN gekürzt
  (`DE79 XXXX XXXX XXXX XXXX 1001`: Ländercode, Prüfziffer, letzte vier Stellen, immer vier Gruppen `XXXX`;
  Konto ohne IBAN „–“), BIC aus den Kontodaten der Bank (sonst „–“), Kontoart. Je Buchung, nach Datum und ID:
  Buchungstag `TT.MM.JJJJ`, Empfänger, Verwendungszweck, Betrag auf diesem Konto (`+1.234,56` / `-1.234,56`).
  Danach „Summe der <n> ausgewählten Buchung(en)“ mit der Summe. Fußzeile mit Hinweis auf die Homebanking-Software
  und „Seite n von m“. Kontostände kommen nicht vor; die vollständige IBAN steht nirgends in der Datei.
- **Hinweise je Buchung** (Zeile „Hinweis: …“). Maßstab ist der Umsatz, wie die Bank ihn geliefert hat: Die
  Synchronisation merkt sich je Bankkennung Buchungstag, Empfängername (nach Auflösung der Aliase), Verwendungszweck
  und Betrag (Betriebszustand, nicht im Protokoll und nicht in der Sicherung; beim ersten Start mit Schema 20 aus dem
  noch vorhandenen Änderungsprotokoll nachgetragen).
  - „Nicht von der Bank abgerufen (von Hand erfasst oder importiert)“ – keine Bankkennung `bank:<IBAN des Kontos>:…`.
  - „Abgleich mit dem Umsatz der Bank nicht möglich“ – Bankkennung vorhanden, aber kein gemerkter Umsatz.
  - „Weicht vom Umsatz der Bank ab: <Felder>“ – Felder in der Reihenfolge Datum, Empfänger, Verwendungszweck, Betrag
    (Betrag auf diesem Konto). Das gilt auch für von Hand erfasste Buchungen, an die die Synchronisation einen
    Bankumsatz angehängt hat.
- **`GET /api/export/nachweis/angaben?konto_id=<id>`** → `{"inhaber": str, "bic": str|null}` aus den von der Bank
  gemeldeten Kontodaten (Bankzugang); Fehler wie oben.
- **Oberfläche:** Im Kontoblatt eines Bestandskontos öffnen `v p`, das Kontextmenü `km-nachweis` „Nachweis als PDF…“
  und die Befehlspalette den Dialog `nachweis-dialog` für die markierten Buchungen: `nachweis-umfang` (Anzahl),
  Feld `nachweis-inhaber` (vorbelegt), `nachweis-ok` lädt die Datei herunter und schließt den Dialog; Fehler stehen
  im Dialog. In Kategorien gibt es weder Kürzel noch Menüeintrag.

### 8.1 Nachweis aus dem Kontoblatt einer Kategorie (D-311)

- `konto_id` darf auch eine Kategorie (Art `aufwand`/`ertrag`) sein; „Unkategorisiert“ und andere Konten ergeben
  weiter 422 `kein_bestandskonto`. Jede Buchung braucht einen Split auf der Kategorie oder einer ihrer
  Unterkategorien (gleicher Art), sonst 422 `buchung_nicht_im_konto`.
- Titel „Buchungsnachweis“ mit „Ausgewählte Buchungen einer Kategorie · kein Dokument der Bank“; Kopf: Kontoinhaber,
  Kategorie (Pfad mit „›“), Bankkonten (Namen der beteiligten Bankkonten). Keine IBAN und keine BIC im Kopf.
- Je Buchung: Betrag = Anteil der Kategorie (samt Unterkategorien) aus Sicht des Bankkontos, also die negative
  Summe dieser Splits (Ausgabe −, Erstattung/Einnahme +); darunter klein „<Bankkonto> · <gekürzte IBAN>“ und, wenn der
  Anteil vom Betrag auf dem Bankkonto abweicht, „Anteil an einer Zahlung über <Betrag>“. Hinweise wie in 8 gegen das
  Bankkonto der Buchung; ohne Bankkonto „Keinem Bankkonto zugeordnet“, mit mehreren „Mehrere Bankkonten beteiligt“.
  Summe = Summe der Anteile.
- `GET /api/export/nachweis/angaben?konto_id=<Kategorie>` → Kontoinhaber des ersten Bankkontos, für das die Bank einen
  meldet; `bic` immer `null`.

## 9. Beträge je Kategorie (Feature `kategorien-uebersicht`, D-311)

Nur lesend, kein Zustand. Noch nicht im OpenAPI-Vertrag (wie D-217).

- **`GET /api/kategorien/uebersicht[?zeitraum=<wert>]`**, `zeitraum` ∈ `monat`, `12monate` (Vorgabe), `jahr`,
  `vorjahr`, `gesamt`; anderer Wert oder unbekannter Parameter → 422 `validierung`.
  - Grenzen nach der App-Uhr: `monat` = laufender Kalendermonat; `12monate` = Monatserster vor elf Monaten bis
    Monatsende des laufenden Monats; `jahr`/`vorjahr` = Kalenderjahr; `gesamt` = `von`/`bis` `null`.
- **Antwort** `{zeitraum, von, bis, heute, monate, kategorien, summen, unkategorisiert}`:
  - `monate`: zwölf Schlüssel `JJJJ-MM`, der letzte ist der Monat, mit dem der Zeitraum endet (`gesamt`: laufender
    Monat).
  - `kategorien`: je Konto der Art `aufwand`/`ertrag` (auch ohne Buchungen), nach `id`: `{id, summe, eigen, anzahl,
    letzte, verlauf}`. `eigen` = Summe der eigenen Splits im Zeitraum, für Ausgaben `Σ`, für Einnahmen `−Σ` (beide
    üblicherweise positiv); `summe` = dasselbe einschließlich aller Unterkategorien gleicher Art; `anzahl` =
    verschiedene Buchungen im Teilbaum im Zeitraum; `letzte` = Datum der jüngsten Buchung im Teilbaum überhaupt
    (`null`, wenn keine); `verlauf` = `summe` je Monat aus `monate`.
  - `summen`: `{ausgaben, einnahmen}` = Summe aller `eigen` je Art.
  - `unkategorisiert`: `{konto_id, anzahl, summe}` für „Unkategorisiert“ im Zeitraum (`summe` = Summe der Splits,
    Ausgaben positiv; `konto_id` `null`, wenn es das Konto nicht gibt).
  - Sonderposten (D-300) zählen mit: Die Seite zeigt, was auf den Kategorien gebucht ist.
