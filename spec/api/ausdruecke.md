# Kontor-Ausdrücke – Meilenstein 30

Verbindlich für Implementierung und Tests. Übernahme der Abschnitte 2 bis 4
und 11 der Meilenstein-Definition „Kontor-Ausdrücke, Filter im Kontoblatt,
Regeleditor und Regel-Tags“ (`spec/definitionen/definition-2-ausdruecke-regeln.md`,
E-268). Regeln mit Ausdruck und Tags stehen in `kategorisierung.md` 8, die
Oberfläche in `oberflaeche.md` 39, der Vertrag der Endpunkte in
`openapi.yaml` (Tag `ausdruck`). Wo die Definition eine Angabe offen lässt,
steht die Lesart der Tests in E-272.

## 1. Überblick

Eine Ausdruckssprache für zwei Zwecke: Bedingungen von Regeln (Kontext
`regel`) und Filter in Buchungslisten (Kontext `filter`). Ein Ausdruck
ergibt für eine Buchung wahr oder falsch und hat keine Nebenwirkungen.
Nicht im Umfang: Filter in der globalen Suche.

## 2. Sprache

### 2.1 Grundsätze

- Es gibt keine Zuweisungen, Schleifen, eigenen Funktionen oder Importe.
  Ausdrücke werden nie als Programmcode ausgeführt (6).
- Schreibweise wie Python-Ausdrücke: `and`, `or`, `not`, Klammern,
  Vergleiche, `in`, `not in`, `is None`, `is not None`. Gleichwertig sind
  `&&`, `||` und `!`.
- `not` bindet stärker als `and`, `and` stärker als `or`.
- `True`, `False`, `None` dürfen auch `true`, `false`, `null` geschrieben
  werden.
- Ein einzelnes `=` ist ein Fehler (`syntax`) mit dem Hinweis auf `==`.
- Ein Ausdruck hat höchstens 4000 Zeichen, ein regulärer Ausdruck höchstens
  500 (`zu_lang`).
- Jeder im Kontext `regel` gültige Ausdruck ist auch als Filter gültig.

### 2.2 Felder

| Feld | Kurzform | Typ | Bedeutung | in Regeln |
| --- | --- | --- | --- | --- |
| `empfänger` | `empf` | Text | Name des Empfängers; ohne Empfänger leer | ja |
| `verwendungszweck` | `vwz` | Text | Verwendungszweck | ja |
| `betrag` | `bet` | Betrag | Betrag ohne Vorzeichen in Euro | ja |
| `richtung` | `dir` | Auswahl | `"ausgabe"`, `"einnahme"`, `"umbuchung"` | ja |
| `datum` | `dt` | Datum | Buchungsdatum | **nein** |
| `kategorie` | – | Verweis oder `None` | Kategorie; `None` = unkategorisiert (`kategorie_id` der Buchung ist null) | ja |
| `status` | – | Auswahl | `"importiert"`, `"vorlaeufig"`, `"bestaetigt"`, `"abgeglichen"` | ja |
| `tags` | – | Menge | Tags der Buchung | ja |
| `notiz` | – | Text | Memos der Splits | ja |
| `iban` | – | Text | IBAN der Gegenseite (`gegen_iban`), sonst leer | ja |
| `konto` | – | Verweis | Bestandskonto der Buchung | ja |
| `monatstag` | – | Zahl 1–31 | Tag im Monat | ja |
| `monat` | – | Zahl 1–12 | Monat; Monatsnamen erlaubt (`dez`) | ja |
| `quartal` | – | Zahl 1–4 | Quartal | ja |
| `jahr` | – | Zahl | Jahr | **nein** |
| `kw` | – | Zahl 1–53 | ISO-Kalenderwoche | **nein** |
| `wochentag` | – | Auswahl | `"mo"` … `"so"`, dazu `"werktag"` (Montag bis Freitag) und `"wochenende"` | ja |
| `letzter_tag` | – | Wahrheitswert | letzter Tag des Monats | ja |
| `verdächtig` | – | Wahrheitswert | Buchung trägt das Label „Verdächtig“ (berechnet, D-261) | nein (nur Filter) |

- Statt `ä`, `ö`, `ü`, `ß` sind in Feldnamen und Auswahlwerten auch `ae`,
  `oe`, `ue`, `ss` erlaubt.
- `richtung` ist `"umbuchung"`, wenn alle Splits der Buchung auf
  Bestandskonten liegen.
- Betrag und Richtung beziehen sich bei Regeln und ohne Konto auf die Summe
  der Splits auf Bestandskonten (Regelbetrag, `kategorisierung.md` 1.1), im
  Kontoblatt (`GET /api/buchungen` mit `konto_id`) auf die Splits des
  angezeigten Kontos. Negative Summe = `"ausgabe"`, positive = `"einnahme"`.

### 2.3 Operatoren

| Ausdruck | Bedeutung |
| --- | --- |
| `"REWE" in empfänger`, `not in` | Teiltext kommt (nicht) vor |
| `empfänger == "REWE"`, `!=` | Text ist (nicht) gleich |
| `empfänger.startswith("REWE")`, `.endswith("GmbH")` | beginnt bzw. endet mit |
| `empfänger.search(r"…")` | regulärer Ausdruck trifft irgendwo |
| `empfänger in ["REWE", "EDEKA"]` | gleich einem der Listenwerte |
| `betrag > 10`, `<`, `<=`, `>=`, `==`, `!=` | Zahlenvergleich |
| `30 <= betrag <= 40` | verketteter Vergleich in einer Richtung |
| `kategorie is None`, `is not None` | leer bzw. gesetzt |
| `kategorie == "Lebensmittel:Supermarkt"` | Verweis über den vollen Pfad |
| `"Urlaub" in tags` | Buchung trägt den Tag |
| `wochentag in ["sa", "so"]` | Auswahlwert ist einer der Listenwerte |

- Textvergleiche ignorieren Groß- und Kleinschreibung und gleichen Umlaute
  an (`ü` = `ue`). Die Textmethoden kennen `case=True` (Schreibung
  beachten) und `fold=False` (Umlaute nicht angleichen). Mehrfache
  Leerzeichen werden nicht zusammengefasst.
- Reguläre Ausdrücke haben garantiert lineare Laufzeit: Rückverweise und
  Lookarounds sind ein Fehler (`regex_nicht_unterstuetzt`).
- Beträge: Dezimalpunkt, höchstens zwei Nachkommastellen, Unterstrich als
  Zifferntrenner.
- Verweise auf Konto, Kategorie und Tag stehen als Text (Konten und
  Kategorien mit dem vollen Pfad, Ebenen durch `:` getrennt); gespeichert
  wird der Bezug, nicht der Name. Nach einer Umbenennung zeigt der Ausdruck
  den neuen Namen. Ein unbekannter Name ist ein Fehler
  (`referenz_unbekannt`).
- Nicht erlaubt: Ausdrücke ohne Wahrheitswert (`empfänger` allein,
  `kein_wahrheitswert`) und Vergleiche ungleicher Typen (`betrag > "10"`).

### 2.4 Datumsangaben (nur im Kontext `filter`)

Jede Datumsangabe steht für einen Zeitraum ganzer Tage. Relative Angaben
beziehen sich auf den Bezugstag (heute nach der Uhr der App, über `stichtag`
übersteuerbar).

| Schreibweise | Zeitraum (Beispiele für Bezugstag 16.11.2026) |
| --- | --- |
| `5.2.`, `05.02.` | 05.02.2026 (Schlusspunkt Pflicht) |
| `5.2.26`, `1.1.2017`, `2026-02-05` | fester Tag; zweistellige Jahre bis zehn Jahre voraus sind 20xx, sonst 19xx |
| `heute`, `gestern`, `vorgestern`, `morgen` | einzelner Tag |
| `-5d`, `-2w`, `-1m`, `-1y` | die letzten n Einheiten bis einschließlich heute (`-5d` = 12.11.–16.11.2026) |
| `+3d` | ab heute |
| `2017` | ganzes Jahr (nur an einem Datumsfeld) |
| `2/2025`, `2025-02`, `feb`, `mär/2024` | ganzer Monat |
| `q3`, `q4/2025` | Quartal |
| `kw46`, `kw46/2026` | ISO-Kalenderwoche |
| `diese_woche`, `letzte_woche`, `naechste_woche` | Kalenderwoche Montag bis Sonntag |
| `dieser_monat`, `letzter_monat`, `naechster_monat` | Kalendermonat |
| `dieses_quartal`, `letztes_quartal` | Kalenderquartal |
| `dieses_jahr`, `letztes_jahr` (auch `vorjahr`), `naechstes_jahr` | Kalenderjahr |
| `X + 1y`, `X - 30d` | Zeitraum ab dem ersten bzw. bis zum letzten Tag von X |
| `X .. Y` | erster Tag von X bis letzter Tag von Y |

- Einheiten: `d`/`t` Tag, `w` Woche, `m` Monat, `q` Quartal, `y`/`j` Jahr.
  Gibt es beim Rechnen mit Monaten den Tag im Zielmonat nicht, gilt dessen
  letzter Tag. Eine andere Einheit ist ein Fehler (`einheit_unbekannt`).
- Vergleiche mit einem Zeitraum von `a` bis `b`: `==` und `in` treffen von
  `a` bis `b`; `>=` ab `a`; `>` nach `b`; `<=` bis `b`; `<` vor `a`.
- `29.2.` ohne Jahr gilt in einem Nichtschaltjahr als 28.02. Andere
  unmögliche Tage (`30.2.`) sind ein Fehler (`datum_ungueltig`), ebenso
  `5.2` ohne Schlusspunkt an einem Datumsfeld.
- `5d` ohne Vorzeichen ist ein Fehler (`dauer_ohne_vorzeichen`).
- `X .. Y` mit vollständigen Jahreszahlen auf beiden Seiten und Ende vor
  Beginn ist ein Fehler (`zeitraum_leer`). Ein Zeitraum mit relativen
  Angaben, der vor seinem Beginn endet, ist gültig und trifft nichts.
- Im Kontext `regel` sind `datum`, `jahr`, `kw` und jede Datumsangabe ein
  Fehler (`nur_im_filter`).

### 2.5 Freitext (nur im Kontext `filter`)

- Enthält die Eingabe kein Feld, keinen Operator und kein Schlüsselwort, ist
  sie eine Volltextsuche: Alle Wörter müssen in Empfänger,
  Verwendungszweck, Notiz oder Tags vorkommen (jedes Wort in irgendeinem
  dieser Felder; Vergleich wie Textvergleiche in 2.3).
- Ein allein stehender Text in Anführungszeichen und ein allein stehendes
  unbekanntes Wort sind Freitext: `rewe bet > 20` bedeutet
  `"rewe" and betrag > 20`. Teile ohne Verknüpfung werden mit `and`
  verbunden.
- Im Kontext `regel` ist ein unbekanntes Wort ein Fehler (`feld_unbekannt`).

### 2.6 Kanonische Schreibweise

Volle Feldnamen, `and`/`or`/`not`, doppelte Anführungszeichen, eckige
Listen, Leerzeichen um Operatoren, Klammern nur wo nötig. Datumsangaben mit
führenden Nullen (`05.02.`), relative Angaben bleiben relativ. Freitext
steht in Anführungszeichen mit `and`. Kein Zeilenumbruch.

Beispiel: `rewe bet>20 && dt in -5d` wird zu
`"rewe" and betrag > 20 and datum in -5d`.

Folgerungen (getestet): Die kanonische Schreibweise eines kanonischen
Ausdrucks ist er selbst; ein Ausdruck und seine kanonische Schreibweise
treffen dieselben Buchungen.

## 3. Bekannte Abweichungen vom Konzept `feature-regeln.md`

Mehrfache Leerzeichen werden in Textvergleichen nicht zusammengefasst;
Umlaute werden standardmäßig angeglichen (`fold=False` schaltet das ab);
der Zeilenumbruch der kanonischen Form vor `or` entfällt.

## 4. Prüfen und Sprache abfragen

Alle drei Endpunkte sind Lesezugriffe ohne Protokolleintrag und wie jeder
Endpunkt geschützt (`sicherheit.md` 3).

### 4.1 `GET /api/ausdruck/sprache`

Parameter `kontext` (`regel` oder `filter`; anderer Wert 422
`validierung`). Antwort 200 (`AusdruckSprache`) mit `kontext`, `felder` (je
Feld `name`, `kurz` oder `null`, `typ`, `bezeichnung`, `operatoren`,
`werte`, `nur_filter`), `schluesselwoerter`, `aliase`, `methoden` und
`kwargs`. `name` und `kurz` sind die Namen aus 2.2. Im Kontext `regel`
fehlen die Felder `datum`, `jahr` und `kw`; im Kontext `filter` tragen genau
sie `nur_filter = true`.

### 4.2 `POST /api/ausdruck/pruefen`

Körper (`AusdruckPruefen`): `ausdruck` (Pflicht), `kontext` (`regel` oder
`filter`), `stichtag`, `festschreiben`. Antwort 200 (`AusdruckPruefung`),
auch bei einem fehlerhaften Ausdruck:

| Feld | Inhalt |
| --- | --- |
| `gueltig` | Wahrheitswert |
| `fehler` | Liste aus `code`, `meldung`, `zeile`, `spalte`, `ende_zeile`, `ende_spalte`, `erwartet`; leer bei gültigem Ausdruck |
| `kanonisch` | kanonischer Text (2.6), sonst `null` |
| `baum` | strukturierte Form, sonst `null` |
| `baukasten_faehig` | Wahrheitswert |
| `hinweise` | Hinweise ohne Fehler, z. B. ein Wort, das als Freitext gelesen wird |
| `datumsangaben` | je Angabe `text`, `von`, `bis` (Datum `JJJJ-MM-TT`), `tage`, `relativ` |
| `freitext` | erkannte Freitext-Teile |
| `zusammenfassung` | die Teile auf oberster Ebene als deutscher Text |

- Zeile und Spalte zählen ab 1 (Zeichen, nicht Bytes); `spalte` ist der
  Beginn der Fehlerstelle.
- Mit `festschreiben` wahr sind relative Datumsangaben im kanonischen Text
  durch feste ersetzt.
- Ein leerer Ausdruck ist ungültig (`syntax`).
- Ein Körper ohne `ausdruck`, mit unbekanntem `kontext` oder unbekanntem
  Feld ist 422 `validierung` (allgemeine Regel).

Fehlercodes: `syntax`, `feld_unbekannt`, `methode_unbekannt`,
`operator_unpassend`, `kein_wahrheitswert`, `wert_ungueltig`,
`regex_ungueltig`, `regex_nicht_unterstuetzt`, `referenz_unbekannt`,
`nur_im_filter`, `datum_ungueltig`, `zeitraum_leer`,
`dauer_ohne_vorzeichen`, `einheit_unbekannt`, `zu_lang`.

### 4.3 `POST /api/ausdruck/als-regel`

Körper: `ausdruck` (Filter, Pflicht), `freitext_feld` (`empfänger` oder
`verwendungszweck`, Vorgabe `empfänger`). Antwort 200 mit `ausdruck`
(Regel-Ausdruck) und `entfernt` (Liste der nicht übernommenen Teile). Teile
auf oberster Ebene, die es nur im Filter gibt, entfallen; Freitext wird zu
`"…" in <freitext_feld>`. Bleibt nichts übrig, ist `ausdruck` `null`. Ein
ungültiger Filter-Ausdruck ist 422 `ausdruck_ungueltig` (5).

## 5. Filter in der Buchungsliste

- `GET /api/buchungen` und der Export (`GET /api/export/buchungen.csv`,
  `.pdf`) nehmen `filter` (Ausdruck im Kontext `filter`) und `stichtag` an.
- `filter` wird mit den übrigen Parametern per `and` verknüpft. Sortierung,
  Seiten und Summe verhalten sich wie bisher.
- Ein ungültiger Ausdruck ergibt 422 `ausdruck_ungueltig`; `details.fehler`
  hat die Form aus 4.2 (Liste `AusdruckFehler`).
- Bei aktivem Filter trägt jeder Eintrag `markierungen`: Liste aus `feld`,
  `start`, `ende` für die Textstellen, die eine Bedingung erfüllt haben
  (leer, wenn keine Textstelle beteiligt ist).
- Reiner Lesezugriff, kein Protokolleintrag.

## 6. Sicherheit und Leistung

- Ausdrücke werden nie als Programmcode ausgeführt.
- Reguläre Ausdrücke können die App nicht blockieren (lineare Laufzeit,
  Längengrenze).
- Die Oberfläche lädt für Ausdrucksfeld und Editor keine Ressourcen von
  außen (`oberflaeche.md` 39.6).
