# ALF-BanCo-Import und Kategorien zusammenführen – Meilenstein 19

Verbindlich für Implementierung und Tests. Übernahme der freigegebenen
Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`alfbanco-import`, kontor-app D-123 bis D-127, E-211) in der überarbeiteten
Fassung. Ergänzt `datenmodell.md` 8 und 10, `python-api.md` 19, `protokoll.md`
16, `loeschen.md` (Zusammenführen wirkt je Quelle wie das Löschen mit
`elternkonto`), `sicherheit.md` 8, `openapi.yaml` (2.16.0) und
`oberflaeche.md` 29. Kein neuer fachlicher Zustand; die Sicherung ändert sich
nicht. Prüfmerkmale der Tests: E-212 bis E-214.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.
Abschnitt 7 der Definition steht als Abschnitt 29 in `oberflaeche.md`.

- **Umfang:** Import des QIF-Exports von ALF-BanCo (eine Datei je Konto) in ein gewähltes
  Bestandskonto (Python und REST), Kategorien zusammenführen
  (`POST /api/kategorien/zusammenfuehren`), Oberfläche: Format „ALF-BanCo“ auf der
  Import-Seite, Mehrfachauswahl im Kategorienbaum, Kontextmenü „Zusammenführen in…“ mit
  Dialog `zusammenfuehren-dialog`.
- **Tests:** `tests/app/m19/` (Marker `m19`). REST und Python-API als `kern`;
  Oberfläche als Browsertests (nicht `kern`).
- **Abhängigkeiten:** M1 (Import, `ImportErgebnis`, Dubletten), M3 (Protokoll, Löschen mit
  Buchungen `loeschen.md`, Abstimmungen, Empfänger-Aliasse), M4 (Split-Vorlagen), M5
  (Kreditbezug), M7 (Schutz, Größengrenzen), M8 (Oberfläche).

## 1. Python-API – `kontor.importer.alfbanco`

```
importiere_alfbanco(config, quelle, *, konto_id, dateiname=None) -> ImportErgebnis
```

- `quelle`: Pfad (`str`/`os.PathLike`) oder `bytes`. Sonst `TypeError`. Pfad nicht
  vorhanden → `FileNotFoundError`. `dateiname` bei Pfad aus dem Dateinamen, sonst
  `None`, wenn nicht angegeben.
- `konto_id` (int, Pflicht, nur als Schlüsselwort): Zielkonto. Existiert es nicht oder ist
  es kein Bestandskonto (`girokonto`, `sparkonto`, `kreditkonto`) → `ValueError`
  (nichts geändert). Geschlossene Bestandskonten sind erlaubt.
- Sonst wie `importiere_gnucash` (`python-api.md` 10.2): Datenbank
  `config.aktive_datenbank` (Schema wird bei Bedarf angelegt), dieselbe Datenbank wie
  die App, atomar, Format- und Inhaltsfehler nur über das `ImportErgebnis`
  (`erfolgreich = false`). Zeitpunkt des Importvorgangs: im Mock-Modus mit `mock_heute`
  dieser Tag 12:00 UTC, sonst die aktuelle Zeit.
- Verhalten identisch mit `POST /api/import/alfbanco` (2).

## 2. REST – `POST /api/import/alfbanco`

- `multipart/form-data` mit den Feldern `datei` (Datei) und `konto_id` (Text: ganze Zahl
  > 0 ohne Vorzeichen und führende Null, höchstens 18 Ziffern; Leerraum außen erlaubt).
- **Prüfreihenfolge** (erste zutreffende Regel):
  1. Körper größer als `upload_max_mib` → 413 `datei_zu_gross` (der Pfad zählt zu den
     Upload-Pfaden in `sicherheit.md` 3, Tabelle der Grenzen); geschützt wie jeder
     Endpunkt (Anmeldung, CSRF, Netz, M7).
  2. Kein lesbares `multipart/form-data` → 422 `validierung`.
  3. `konto_id` fehlt oder ungültig → 422 `validierung` (Ort `body.konto_id`).
  4. `datei` fehlt oder ist kein Dateifeld → 422 `validierung` (Ort `body.datei`).
  5. Konto existiert nicht → 422 `referenz_unbekannt` mit `details = {"feld":
     "konto_id"}`; kein Bestandskonto (Kategorie, Eigenkapital) → 422
     `konto_ungueltig` mit `details = {"feld": "konto_id"}`. Diese Prüfung kommt **vor**
     dem Lesen der Datei (eine leere Datei an ein unbekanntes Konto ergibt
     `referenz_unbekannt`).
  6. Fehler der Datei (3.1, 3.3) → 422; `fehler.code` = Code der ersten Meldung,
     `fehler.details` = vollständiges `ImportErgebnis` (wie bei
     `POST /api/import/kmymoney`).
- Erfolg: 200 mit `ImportErgebnis` (`format = "qif"`).
- `dateiname` des Importvorgangs = Dateiname des Uploads (leer → null).
- Zeitpunkt des Importvorgangs: App-Uhr (Mock-Uhr im Mock-Modus, wie bei den anderen
  Importen).

### 2.1 Schemaänderungen (`openapi.yaml`)

- `ImportErgebnis.format`: zusätzlich `"qif"`.
- `Importvorgang.art`: zusätzlich `"alfbanco"`.
- Neue Pfade `POST /api/import/alfbanco` und `POST /api/kategorien/zusammenfuehren` (5).
- Aktionen `import_alfbanco` und `kategorien_zusammenfuehren` im Protokoll (6).

## 3. Lesen der QIF-Datei

### 3.1 Datei- und Formatfehler (genau eine Meldung, `referenz = null`)

| Bedingung | Code | `format` |
| --- | --- | --- |
| 0 Bytes | `import_datei_leer` | null |
| erste nicht leere Zeile beginnt (nach Entfernen von Leerraum) nicht mit `!` | `import_format_ungueltig` | null |
| Buchungssätze (3.2) zu mehr als einem Konto in einer Datei (verschiedene `!Account`-Namen; Sätze vor dem ersten `!Account` zählen als eigenes, namenloses Konto) | `import_format_ungueltig` | `"qif"` |
| keine Buchungssätze, keine Kategorieliste und kein Abschnitt `!Type:…`/`!Account`/unbekannter Kopf (z. B. nur `!Option:…`/`!Clear:…`) | `import_format_ungueltig` | `"qif"` |

Eine Datei mit Abschnitt `!Type:Bank` ohne Sätze ist gültig (Erfolg, alle Zählungen 0).

### 3.2 Aufbau

- **Kodierung:** UTF-8 (ein UTF-8-BOM wird entfernt); ist die Datei kein gültiges UTF-8,
  Windows-1252; enthält sie in Windows-1252 nicht belegte Bytes, Latin-1. Zeilenenden
  `\n`, `\r\n` oder `\r`.
- **Zeilen:** Leere Zeilen werden übersprungen, nachgestellter Leerraum entfernt. Eine
  Zeile, die mit `!` beginnt, ist ein Kopf; sonst ist das erste Zeichen der Feldcode, der
  Rest der Wert. `^` beendet einen Satz; ein Kopf oder das Dateiende beendet einen
  offenen Satz ebenfalls.
- **Köpfe** (ohne Groß-/Kleinschreibung): `!Type:<Typ>` beginnt einen Abschnitt;
  `!Account` beginnt einen Kontoabschnitt (das Feld `N` seiner Sätze ist der Kontoname
  für die folgenden Buchungssätze); `!Option:…` und `!Clear:…` ändern nichts; jeder
  andere Kopf beginnt einen unbekannten Abschnitt, dessen Sätze ignoriert werden.
- **Abschnitte:**
  - `Bank`, `CCard`, `Cash`, `Oth A`, `Oth L`: **Buchungssätze**.
  - `Invst`: Sätze zählen als Buchungssätze, werden aber übersprungen (4.6) und nicht
    geprüft.
  - `Cat`: Kategorieliste; ein Satz mit Name `N` und Feld `I` (Einnahme) bzw. `E`
    (Ausgabe) legt die Art dieser Kategorie fest (`I` gewinnt, wenn beide). Kategorien
    werden nur über Buchungen angelegt, nie allein aus der Liste.
  - alle anderen (`Class`, `Memorized`, …): ignoriert.
- **Satznummer:** Buchungssätze (einschließlich `Invst`) werden in Dateireihenfolge ab 1
  gezählt; `referenz` von Meldungen zu Sätzen ist `"Satz <n>"`.
- **Felder eines Buchungssatzes:** `D` Datum, `T` Betrag (fehlt `T`, gilt `U`), `P`
  Empfänger, `M` Verwendungszweck, `L` Kategorie, `N` Nummer (nur für die Kennung),
  Aufteilungen: `S` beginnt eine Aufteilung (Kategorie), `E` Memo und `$` Betrag der
  letzten Aufteilung. Kommt ein Feldcode mehrfach vor, gilt das erste Vorkommen;
  `E`/`$` vor dem ersten `S` werden ignoriert; andere Codes werden ignoriert.

### 3.3 Inhaltsfehler

Für jeden Buchungssatz außer `Invst` (alle Fehler werden gesammelt, Code
`import_inhalt_ungueltig`, `referenz = "Satz <n>"`, je Satz in der Reihenfolge Datum,
Betrag, Aufteilungen):

- `D` fehlt/leer oder kein gültiges Datum (3.4);
- Betrag (`T` bzw. `U`) fehlt/leer oder ungültig (3.5);
- eine Aufteilung ohne `$` oder mit ungültigem Betrag.

Bei jedem Fehler aus 3.1 oder 3.3: nichts wird geändert (kein Teilimport, kein
Importvorgang, keine Änderung im Protokoll), `erfolgreich = false`, alle Zählungen 0,
`warnungen = []`, `import_id = null`.

### 3.4 Datum

Leerzeichen (U+0020) im Wert werden entfernt. Formate:

- `JJJJ-M-T` (Monat und Tag ein- oder zweistellig);
- `T.M.JJJJ` oder `T.M.JJ`;
- `A/B/JJJJ`, `A/B/JJ`, `A/B'JJ`, `A/B'JJJJ` (QIF-Stil, Apostroph statt `/` vor dem Jahr).

Zweistellige Jahre: mit Apostroph immer `20JJ`; sonst `JJ < 70` → `20JJ`, sonst `19JJ`.
Bei `/`-Daten ist `A` der **Monat** und `B` der Tag – außer wenn in der Datei irgendein
Buchungsdatum im `/`-Format an erster Stelle einen Wert > 12 hat; dann ist bei allen
`A` der Tag. Ein nicht existierender Tag (z. B. `31.02.2024`, `1.13.2024`) oder ein anderes
Format (z. B. `2024/01/02`) ist ungültig.

Beispiele: `02.01.2024`, `2.1.24`, `1/2/2024` (Monat zuerst), `1/2'24`, ` 1/ 2'98`
→ 2024-01-02 bzw. 2098-01-02; `1/2/98` → 1998-01-02; Datei mit `13/02/2024` → Tag zuerst.

### 3.5 Betrag

- **Dezimaltrenner der Datei:** Komma, wenn irgendein Betrag der Datei (`T`/`U` der
  Buchungssätze außer `Invst` und alle `$`) nach Entfernen von U+0020 auf Komma und ein
  oder zwei Ziffern endet; sonst Punkt.
- **Ein Betrag** (nach Entfernen von U+0020 und U+00A0): optionales Vorzeichen `+`/`-`,
  dann nur Ziffern, `.` und `,`. Kommen beide Zeichen vor, ist das **letzte** der
  Dezimaltrenner; kommt nur eines vor, ist es Dezimaltrenner, wenn es dem Trenner der
  Datei entspricht, sonst Tausendertrenner. Tausendertrenner werden entfernt. Nach dem
  Dezimaltrenner dürfen nur Ziffern folgen (mindestens eine, kein zweiter
  Dezimaltrenner); fehlt der ganzzahlige Teil, gilt 0. Mehr als zwei Nachkommastellen nur,
  wenn die überzähligen 0 sind. Betrag höchstens 999 999 999 999 Cent. Sonst ungültig.
- Beispiele (Trenner `,`): `-12,34` → −1234; `2.500,00` → 250000; `+7` → 700; `0,10` → 10;
  `1.000` → 100000; `-0,00` → 0; ungültig: `1,234`, `12,345`, `abc`, `1e3`, `--1`,
  `10000000000,00`, `5,`. (Trenner `.`): `1,234.56` → 123456; `12.5` → 1250; `3,450` →
  345000.

## 4. Abbildung

### 4.1 Buchung

Je Buchungssatz (nicht `Invst`), sofern nicht vorhanden (4.4) oder zusammengeführt
(4.5), eine Buchung:

- `datum` (3.4), `status = "importiert"`, `verwendungszweck` = Wert von `M` (ohne
  Änderung außer dem entfernten nachgestellten Leerraum der Zeile; fehlt → `""`),
  `empfaenger` aus `P` (4.3; leer → null), `extern_ids = [<Kennung>]` (4.4), Tags aus den
  Klassen (4.3), kein `gegen_iban`.
- **Splits** in dieser Reihenfolge:
  1. Zielkonto mit `betrag` = Betrag des Satzes, `memo = ""`;
  2. je Aufteilung (`S`) in Dateireihenfolge ein Split auf das Gegenkonto (4.2) mit
     `betrag` = −Betrag der Aufteilung und `memo` = `E`; ohne Aufteilungen ein Split auf das
     Gegenkonto aus `L` mit −Betrag des Satzes und `memo = ""`;
  3. ergibt die Summe aller Splits nicht 0: ein weiterer Split über den Rest auf
     „Unkategorisiert“ (`extern_id = "kontor:unkategorisiert"`), Warnung
     `split_differenz` (`referenz = "Satz <n>"`).
- Beispiel: `T-50,00`, `SHaushalt:Lebensmittel`/`EEssen`/`$-30,00`, `SKleidung`/`EHose`/
  `$-20,00` → Zielkonto −5000, Lebensmittel +3000 „Essen“, Kleidung +2000 „Hose“.

### 4.2 Gegenkonto (`L` bzw. `S`)

Der Text wird in Kategorie und Klasse zerlegt: bei `[Name]…` ist die Kategorie `[Name]`
(ein `/` im Kontonamen bleibt), eine folgende `/Klasse` die Klasse; sonst teilt das erste
`/` Kategorie und Klasse. Beide werden getrimmt.

- **Leer** → „Unkategorisiert“ (bei Bedarf angelegt wie bisher).
- **Umbuchung `[Name]`:**
  - `Name` gleich dem Namen des Zielkontos (Anfangssaldo in ALF-BanCo) → technisches
    Konto „Anfangssalden“: Art `eigenkapital`, Wurzelkonto, `extern_id =
    "alf:anfangssalden"`, beim ersten Bedarf angelegt und danach über die `extern_id`
    wiederverwendet; in keiner Zählung enthalten.
  - sonst das Bestandskonto mit genau diesem Namen (nicht das Zielkonto; bei mehreren
    das mit der kleinsten ID; auch geschlossene);
  - kein solches Konto → „Unkategorisiert“, Warnung `umbuchung_konto_unbekannt`
    (`referenz = "Satz <n>"`).
- **Kategorie:** Pfad = durch `:` getrennte, getrimmte, nicht leere Teile. Jeder Pfad
  (auch jeder Vorfahrenpfad) wird einer Kategorie zugeordnet:
  1. Kategorie (Art `aufwand` oder `ertrag`) mit `extern_id = "alf:kat:<Teile mit :
     verbunden>"` (z. B. `alf:kat:Haushalt:Lebensmittel`), unabhängig von Name, Art und
     Elternkonto;
  2. sonst eine **vor dem Lauf vorhandene** Kategorie mit der Art des Pfads (4.2.1),
     exakt gleichem Namen (letzter Teil) und dem zugeordneten Elternkonto des
     Elternpfads (Wurzel: kein Elternkonto), deren `extern_id` null ist oder nicht mit
     `alf:` oder `kontor:` beginnt und die in diesem Lauf noch keinem anderen Pfad
     zugeordnet wurde; bei mehreren die mit der kleinsten ID. Ist ihre `extern_id` null,
     erhält sie `alf:kat:<Pfad>`; eine andere `extern_id` (z. B. `kmy:…`) bleibt, die
     Kategorie wird dann bei jedem Import erneut über den Namen gefunden;
  3. sonst neu angelegt (Name = letzter Teil, Elternkonto = Kategorie des Elternpfads,
     `extern_id = "alf:kat:<Pfad>"`, nicht geschlossen, `notiz = ""`).
  Zugeordnete Kategorien werden sonst nicht verändert.

#### 4.2.1 Art einer Kategorie

- Unterkategorien haben die Art ihres (zugeordneten) Elternkontos.
- Wurzel: Art aus der Kategorieliste (`!Type:Cat`) für die Wurzel selbst, sonst die der
  ersten in der Liste gekennzeichneten Kategorie mit dieser Wurzel; `I` → `ertrag`, `E` →
  `aufwand`.
- Sonst abgeleitet aus der Summe der Gegenbeträge aller Buchungssätze auf Pfade dieser
  Wurzel (Gegenbetrag = −Betrag der Aufteilung bzw. des Satzes): Summe < 0 → `ertrag`,
  sonst `aufwand`. Wird eine solche Wurzel **neu angelegt**, Warnung
  `kategorieart_abgeleitet` mit `referenz` = Name der Wurzel.

### 4.3 Empfänger und Tags

- **Empfänger:** `P` getrimmt; Zuordnung wie `buchhaltungspflege.md` 2.3 Schritte 1–2
  (exakter Name, sonst passender Alias), sonst neu angelegt (`extern_id = null`). Jeder
  verschiedene Name der Datei zählt genau einmal (`empfaenger_neu` bzw.
  `empfaenger_vorhanden`), auch bei schon vorhandenen Buchungen.
- **Tags:** jede Klasse einer Buchung (aus `L` oder einem `S`) wird ein Tag der Buchung
  (je Buchung ohne Wiederholung). Zuordnung über den Namen unter `casefold()`, sonst neu
  (Name in der ersten Schreibweise der Datei). Jeder Name (unter `casefold()`) zählt genau
  einmal (`tags_neu`/`tags_vorhanden`).
- Keine Warnungen `empfaenger_zusammengefasst`/`tag_zusammengefasst`.

### 4.4 Herkunftskennung und Idempotenz (D-124)

- Kennung je Buchungssatz: `alf:<konto_id>:<32 Kleinbuchstaben-Hexziffern>`; abgeleitet
  (Prüfsumme) aus Zielkonto, Datum, Betrag, getrimmten `P`, `M`, `L`, `N`, den
  Aufteilungen (Kategorietext, getrimmtes Memo, Betrag) und der laufenden Nummer gleicher
  Sätze in der Datei (der erste von mehreren inhaltsgleichen Sätzen hat Nummer 0, der
  zweite 1 …). Damit gilt:
  - zwei inhaltsgleiche Sätze ergeben zwei Buchungen (zweimal derselbe Kaffee);
  - derselbe Satz in eine anderes Zielkonto ergibt eine andere Kennung;
  - eine Änderung eines dieser Felder ergibt eine neue Kennung.
- Eine Buchung, deren `extern_ids` die Kennung enthält, ist **vorhanden**
  (`buchungen_vorhanden`) und bleibt unverändert.
- Zweiter Import derselben Datei: keine Änderung am Buchbestand außer dem neuen
  Importvorgang; `buchungen_neu = 0`, `kategorien_neu = 0`, `empfaenger_neu = 0`,
  `tags_neu = 0`, `buchungen_zusammengefuehrt = 0`, `buchungen_zur_pruefung = 0`. Eine
  erweiterte Fassung (zusätzliche Sätze am Ende) fügt genau die neuen Sätze hinzu.
- Ein **neuer Importvorgang** entsteht bei jedem erfolgreichen Import (auch ohne neue
  Buchungen): `art = "alfbanco"`, `dateiname`, `sha256` der Datei, `importiert_am`,
  `ergebnis` = `ImportErgebnis`.

### 4.5 Dublettenprüfung (weicht von `datenmodell.md` 10.4 ab, D-124)

Für jeden Satz, der nicht über die Kennung zugeordnet wurde:

- **Kandidaten** sind Buchungen, die vor dem Lauf existierten, einen Split auf dem
  **Zielkonto** mit genau dem Betrag des Satzes haben und in diesem Lauf nicht schon
  über ihre Kennung zugeordnet wurden. Anders als bei KMyMoney sind Buchungen derselben
  Quelle (Kennung `alf:…`) **nicht** ausgenommen: ein nachträglich in ALF-BanCo
  geänderter Satz bekommt eine neue Kennung und soll trotzdem erkannt werden.
- exakt: gleiches Datum und Empfänger passend (`datenmodell.md` 1; beide ohne Empfänger
  zählt als passend); ähnlich: nicht exakt und Datumsabstand ≤ 3 Tage.
- Entscheidung wie 10.4 Punkt 1–3: genau ein exakter Kandidat, der für keinen anderen
  Satz dieses Laufs exakt ist → zusammenführen (die Kennung wird an `extern_ids` des
  Kandidaten angehängt, sonst unverändert, `buchungen_zusammengefuehrt`); sonst bei
  Kandidaten neu anlegen mit offenem Dublettenverdacht (`grund` `mehrdeutig` bei
  exakten, sonst `aehnlich`; `kandidat_ids` = alle Kandidaten; zählt in `buchungen_neu`
  und `buchungen_zur_pruefung`); sonst normal neu.

### 4.6 Übersprungene Sätze

Jeder Satz eines `Invst`-Abschnitts: keine Buchung, `buchungen_uebersprungen` + 1,
Warnung `buchung_uebersprungen` (`referenz = "Satz <n>"`).

### 4.7 Importergebnis

`ImportErgebnis` wie `datenmodell.md` 10.5 mit:

- `format = "qif"` (bei Fehlern 3.1 ggf. null);
- `konten_neu = konten_vorhanden = 0` (Zielkonto, Umbuchungsgegenkonten, „Anfangssalden“
  und „Unkategorisiert“ werden nicht gezählt);
- `kategorien_neu`/`kategorien_vorhanden`: jeder in der Datei benutzte Kategoriepfad
  einschließlich seiner Vorfahrenpfade genau einmal (z. B. `Haushalt:Lebensmittel` zählt
  `Haushalt` und `Haushalt:Lebensmittel`), auch bei schon vorhandenen Buchungen;
  Umbuchungen und leere Kategorien zählen nicht;
- `splits_neu`: Splits der neu angelegten Buchungen (inkl. Restsplits);
- `buchungen_neu + buchungen_vorhanden + buchungen_zusammengefuehrt +
  buchungen_uebersprungen` = Anzahl der Buchungssätze (einschließlich `Invst`);
- Warnungscodes: `buchung_uebersprungen`, `umbuchung_konto_unbekannt`, `split_differenz`,
  `kategorieart_abgeleitet`; je Code und Referenz genau eine Warnung, Reihenfolge nicht
  festgelegt.
- Fehlercodes: `import_datei_leer`, `import_format_ungueltig`, `import_inhalt_ungueltig`.

### 4.8 Folgerungen (prüfbar)

- Invarianten `datenmodell.md` 3 gelten; Summe aller Kontensalden bleibt 0.
- Saldo des Zielkontos steigt um die Summe der Beträge der neu angelegten Buchungen.
- Umbuchung `[Sparkonto]` mit `T-100,00` → Zielkonto −10000, Sparkonto +10000.

## 5. `POST /api/kategorien/zusammenfuehren` (D-126)

Buchungen mehrerer Quellkategorien auf eine Zielkategorie umbuchen, die Quellen auf
Wunsch löschen. Wirkt je Quelle wie `POST /api/konten/{id}/loeschen` mit `buchungen =
"elternkonto"` und `konflikte = "behalten"` (`loeschen.md` 3), jedoch mit dem
**gewählten Ziel** statt des Elternkontos.

### 5.1 Körper

| Feld | Typ | Pflicht | Bedeutung |
| --- | --- | --- | --- |
| `quelle_ids` | Liste von Ganzzahlen, 1–1000 Einträge, ohne Wiederholung | ja | Quellkategorien in Verarbeitungsreihenfolge |
| `ziel_id` | Ganzzahl | ja | Zielkategorie |
| `quellen_loeschen` | bool | nein (`true`) | Quellen danach löschen |
| `gesperrte_einbeziehen` | bool | nein (`false`) | Bestätigung für gesperrte Buchungen |
| `trocken` | bool | nein (`false`) | Probelauf |

### 5.2 Prüfreihenfolge (nichts wird geändert)

1. Körper ungültig (kein Objekt, Pflichtfeld fehlt, falscher Typ – `true` ist keine
   Ganzzahl –, leere oder zu lange Liste, Wiederholung, unbekanntes Feld) → 422
   `validierung`.
2. `ziel_id` unter `quelle_ids` → 422 `ziel_ungueltig`.
3. Unbekannte IDs (Ziel oder Quellen) → 422 `referenz_unbekannt` mit `details =
   {"konto_ids": [...]}` (aufsteigend, alle unbekannten).
4. Quelle oder Ziel keine Kategorie (Art nicht `aufwand`/`ertrag`) → 422
   `konto_ungueltig` mit `details = {"konto_ids": [...]}` (aufsteigend).
5. Nur bei `quellen_loeschen = true`: eine Quelle mit Kreditbezug → 409
   `konto_in_verwendung` mit `details.kredit_ids` (wie `loeschen.md` 7); geprüft auch im
   Probelauf.
6. Kein Probelauf, `gesperrte_einbeziehen = false` und betroffene Buchungen sind
   gesperrt (abgeglichen oder abgestimmt) → 409 `buchung_gesperrt` mit `details =
   {"buchung_ids": [...]}` (aufsteigend).

Einnahme- und Ausgabekategorien dürfen gemischt werden (Quelle `ertrag`, Ziel `aufwand`
und umgekehrt).

### 5.3 Wirkung (atomar)

*Betroffen* sind alle Buchungen mit mindestens einem Split auf einer Quelle (vor der
Operation). Die Quellen werden in der Reihenfolge von `quelle_ids` verarbeitet, jeweils
mit dem aktuellen Stand nach den vorigen.

**Mit `quellen_loeschen = true`** je Quelle Q:

1. **Unterkategorien:** Hat Q dieselbe Klasse wie das Ziel (beide `aufwand` oder beide
   `ertrag`) und ist das Ziel kein Nachfahre von Q, werden alle direkten Unterkategorien
   von Q Unterkategorien des Ziels (`unterkategorien_verschoben`). Sonst rücken sie wie
   `loeschen.md` 3.1 eine Ebene nach oben (Elternkonto = Elternkonto von Q).
2. Abstimmungen von Q werden entfernt (`loeschen.md` 3.6).
3. Splits auf Q buchen auf das Ziel; Zusammenfassen freier Splits auf dem Ziel
   (`loeschen.md` 3.2 Punkt 3, Memos mit `" / "`); Konfliktbuchungen (alle Splits danach
   auf dem Ziel) bleiben ohne Zusammenfassen erhalten (`loeschen.md` 3.3 `behalten`);
   `vorschlag` der umgebuchten Buchungen wird null.
4. Regeln (`kategorie_id` und Bedingungen `konto_id`), Split-Vorlagen und
   Standardkategorien von Empfängern, die auf Q verweisen, verweisen danach auf das Ziel
   (`loeschen.md` 3.4, 3.5, 6 wie `elternkonto`).
5. Q wird gelöscht.

Danach: Hat das Ziel keine `extern_id`, erhält es die `extern_id` der ersten Quelle in
`quelle_ids`, die eine hat (`extern_id_uebernommen`); so legt ein späterer Import die
gelöschte Kategorie nicht neu an (der Pfad wird über die Kennung dem Ziel zugeordnet).

**Mit `quellen_loeschen = false`:** je Quelle nur Schritt 2 und 3 (Abstimmungen der
Quelle entfernen, umbuchen, zusammenfassen, Konfliktbuchungen behalten). Quellen,
Unterkategorien, Regeln, Vorlagen, Standardkategorien und `extern_id` bleiben unverändert;
die Quellen haben danach keine Buchungen mehr.

Gesperrte Buchungen werden mit `gesperrte_einbeziehen = true` genauso umgebucht.

**Folgerungen:** `saldo_neu(Ziel) = saldo_alt(Ziel) + Σ saldo_alt(Quellen)` (eigene
Splits, ohne Unterkategorien); alle übrigen Konten behalten ihren Saldo (auch
Bestandskonten); Summe aller Salden bleibt 0; Invarianten `datenmodell.md` 3.

### 5.4 Antwort (200, auch im Probelauf)

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `ziel_id` | int | wie angefragt |
| `quelle_ids` | int[] | wie angefragt (Reihenfolge) |
| `quellen_geloescht` | bool | = `quellen_loeschen` |
| `buchungen_umgebucht` | int[] | alle betroffenen Buchungen, aufsteigend (einschließlich gesperrter und Konfliktbuchungen) |
| `konfliktbuchungen` | int[] | aufsteigend |
| `gesperrt` | int[] | betroffene gesperrte Buchungen, aufsteigend (auch im Probelauf) |
| `unterkategorien_verschoben` | int[] | unter das Ziel verschobene Kategorien, aufsteigend |
| `regeln_geaendert` | int[] | umgestellte Regeln, aufsteigend (leer bei `quellen_loeschen = false`) |
| `empfaenger_geaendert` | int[] | Empfänger mit umgestellter Standardkategorie, aufsteigend |
| `extern_id_uebernommen` | string \| null | übernommene Kennung |
| `trocken` | bool | Probelauf |
| `aenderung_id` | int \| null | ID der Änderung; null im Probelauf und wenn sich nichts geändert hat |

**Probelauf** (`trocken = true`): liefert dasselbe Ergebnis wie der echte Lauf (gerechnet,
als wäre `gesperrte_einbeziehen = true`, also nie 409 `buchung_gesperrt`), ändert nichts
und erzeugt keine Änderung im Protokoll.

## 6. Protokoll

Zusätzliche Zeilen für `protokoll.md` 4:

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| ALF-BanCo-Import (REST und `importiere_alfbanco`), erfolgreich | `import` | `import_alfbanco` | `"import:<import_id>"` |
| Kategorien zusammenführen (ohne `trocken`) | `manuell` | `kategorien_zusammenfuehren` | null |

- Rückgängig des Imports (auch über `gruppe`) entfernt alle angelegten Buchungen,
  Kategorien, Empfänger, Tags, Dublettenverdachte und „Anfangssalden“ und nimmt gesetzte
  `extern_id`s an vorhandenen Kategorien und angehängte Kennungen zusammengeführter
  Buchungen zurück; danach ist `GET /api/konten` gleich dem Stand vor dem Import.
- Rückgängig des Zusammenführens stellt den Zustand vorher exakt her (Quellen mit
  denselben IDs, Unterkategorienzuordnung, Splits mit IDs, Beträgen, Memos, Vorschläge,
  Regeln, Vorlagen, Standardkategorien, Abstimmungen samt Splitmarken, `extern_id` des
  Ziels). Baut eine spätere Änderung darauf auf (z. B. ein Import, der eine Kategorie über
  die übernommene Kennung dem Ziel zugeordnet hat), gilt `protokoll.md` 6 (409
  `rueckgaengig_konflikt` bzw. der dort festgelegte Code).
- Die Änderungen erscheinen im Protokoll mit Text „ALF-BanCo-Import“ bzw. „Kategorien
  zusammengeführt“; der Importvorgang wird in der Oberfläche als „ALF-BanCo“ bezeichnet.

## 7. Oberfläche

Siehe `oberflaeche.md` 29.

## 8. Synthetisches QIF-Beispiel (für Generator/Fixtures)

Nur fiktive Namen; Zielkonto „Girokonto“, zusätzlich ein Bestandskonto „Sparkonto“.
Kodierung Windows-1252 mit `\r\n` (wie ALF-BanCo), Variante in UTF-8 mit BOM.

```
!Type:Cat
NHaushalt
E
^
NHaushalt:Lebensmittel
E
^
NGehalt
I
^
!Type:Bank
D02.01.2024
T-12,34
PSupermarkt Beispiel
MEinkauf Woche 1
LHaushalt:Lebensmittel
^
D03.01.2024
T2.500,00
PArbeitgeber Muster GmbH
MLohn Januar
LGehalt/Steuer
^
D04.01.2024
T-100,00
PSparen
L[Sparkonto]
^
D05.01.2024
T-50,00
PKaufhaus Beispiel
MGemischter Einkauf
SHaushalt:Lebensmittel
EEssen
$-30,00
SKleidung
EHose
$-20,00
^
D06.01.2024
T-3,00
PCafé Beispiel
^
D06.01.2024
T-3,00
PCafé Beispiel
^
```

Erwartung (frisches Buch mit Girokonto und Sparkonto): 6 Buchungen neu, Kategorien neu
4 (`Haushalt`, `Haushalt:Lebensmittel`, `Gehalt`, `Kleidung`), Empfänger neu 5, Tags neu 1
(`Steuer`), Warnung genau `kategorieart_abgeleitet` mit `referenz = "Kleidung"`
(`Kleidung` → `aufwand`), `Gehalt` → `ertrag`; die zwei Kaffee-Sätze ergeben zwei
Buchungen auf „Unkategorisiert“; `splits_neu` = 13.

Weitere sinnvolle Varianten für Tests: `!Type:Invst`-Abschnitt (übersprungen), `[Girokonto]`
(Anfangssaldo → „Anfangssalden“), `[Unbekannt]` (Warnung), Aufteilungen mit Rest
(`split_differenz`), `/`-Daten mit und ohne Tag > 12, Punkt als Dezimaltrenner,
zwei `!Account`-Abschnitte mit Buchungen (Formatfehler), erweiterte Fassung (Sätze
angehängt), geänderter Satz (neue Kennung → zusammengeführt mit der alten Buchung).

## 9. Abweichungen gegenüber den Entscheidungen von kontor-app

- D-123 nennt für das Format nur `!`-Kopfzeile und mehrere Konten; tatsächlich gibt es
  zusätzlich den Fehler „kein bekannter Abschnitt“ (3.1, letzte Zeile).
- D-125 „Gezählt wird jeder Pfad“: gezählt werden auch alle Vorfahrenpfade (4.7).
- `konten_neu` zählt das technische Konto „Anfangssalden“ nicht (in D-125 nicht genannt).
- Prüfung des Zielkontos vor dem Lesen der Datei (2, Punkt 5) – in D-123 ohne Reihenfolge.
