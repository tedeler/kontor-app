# Meilenstein-Definition: Kontor-Ausdrücke, Filter im Kontoblatt, Regeleditor und Regel-Tags

Stand: 2026-11-19, **Entwurf zur Freigabe durch den Auftraggeber**. Features `ausdruecke`, `regeleditor-feinschliff` und `regel-tags`, in kontor-app auf main (Version 0.31, Entscheidungen D-185 bis D-196, D-214, D-215). Noch nicht in kontor-tests übernommen. Vorschlag für die Nummer: M30; die Nummer vergibt der Test-Thread.

Diese Definition beschreibt nur Verhalten. Sie ändert Teile der Meilensteine 2, 3, 8, 9, 12 und 17 (Abschnitt 12).

## 1 Umfang

1. Eine Ausdruckssprache für zwei Zwecke: Bedingungen von Regeln und Filter in Buchungslisten.
2. Prüfung eines Ausdrucks mit Fehlerstelle, kanonischer Schreibweise und Zusammenfassung.
3. Filter über einen Ausdruck in der Buchungsliste; im Kontoblatt ein Filterfeld mit Baukasten statt der bisherigen Einzelfelder.
4. Regeln mit Ausdruck, feste Reihenfolge, Test gegen vorhandene Buchungen, Erklärung je Buchung, Anwenden einer einzelnen Regel.
5. Regeln vergeben Tags; die Kategorie einer Regel ist optional.
6. Validierungsfehler nennen in der Oberfläche Feld und Regel.

Nicht im Umfang: Filter in der globalen Suche; die Aktionen „direkt bestätigen“ und „danach keine weiteren Regeln“; Tags per Regel entfernen; Regeln beim Import und bei von Hand angelegten Buchungen; Trefferzahl und Verdeckungswarnung in der Regelliste.

## 2 Ausdruckssprache

### 2.1 Grundsätze

- Jeder Ausdruck ergibt wahr oder falsch und hat keine Nebenwirkungen. Es gibt keine Zuweisungen, Schleifen, eigenen Funktionen oder Importe.
- Schreibweise wie Python-Ausdrücke: `and`, `or`, `not`, Klammern, Vergleiche, `in`, `not in`, `is None`, `is not None`. Als gleichwertige Schreibweise gelten `&&`, `||` und `!`.
- `not` bindet stärker als `and`, `and` stärker als `or`.
- `True`, `False`, `None` dürfen auch `true`, `false`, `null` geschrieben werden.
- Ein einzelnes `=` ist ein Fehler mit dem Hinweis auf `==`.
- Ein Ausdruck hat höchstens 4000 Zeichen, ein regulärer Ausdruck höchstens 500.
- Es gibt zwei Kontexte: `regel` und `filter`. Jeder im Kontext `regel` gültige Ausdruck ist auch als Filter gültig.

### 2.2 Felder

| Feld | Kurzform | Typ | Bedeutung | in Regeln |
| --- | --- | --- | --- | --- |
| `empfänger` | `empf` | Text | Name des Empfängers; ohne Empfänger leer | ja |
| `verwendungszweck` | `vwz` | Text | Verwendungszweck | ja |
| `betrag` | `bet` | Betrag | Betrag ohne Vorzeichen in Euro | ja |
| `richtung` | `dir` | Auswahl | `"ausgabe"`, `"einnahme"`, `"umbuchung"` | ja |
| `datum` | `dt` | Datum | Buchungsdatum | **nein** |
| `kategorie` | – | Verweis oder `None` | Kategorie; `None` = unkategorisiert | ja |
| `status` | – | Auswahl | `"importiert"`, `"vorlaeufig"`, `"bestaetigt"`, `"abgeglichen"` | ja |
| `tags` | – | Menge | Tags der Buchung | ja |
| `notiz` | – | Text | Memos der Splits | ja |
| `iban` | – | Text | IBAN der Gegenseite, sonst leer | ja |
| `konto` | – | Verweis | Bestandskonto der Buchung | ja |
| `monatstag` | – | Zahl 1–31 | Tag im Monat | ja |
| `monat` | – | Zahl 1–12 | Monat; Monatsnamen erlaubt (`dez`) | ja |
| `quartal` | – | Zahl 1–4 | Quartal | ja |
| `jahr` | – | Zahl | Jahr | **nein** |
| `kw` | – | Zahl 1–53 | ISO-Kalenderwoche | **nein** |
| `wochentag` | – | Auswahl | `"mo"` … `"so"`, dazu `"werktag"` und `"wochenende"` | ja |
| `letzter_tag` | – | Wahrheitswert | letzter Tag des Monats | ja |

- Statt `ä`, `ö`, `ü`, `ß` sind in Feldnamen und Auswahlwerten auch `ae`, `oe`, `ue`, `ss` erlaubt.
- `richtung` ist `"umbuchung"`, wenn alle Splits der Buchung auf Bestandskonten liegen.
- Betrag und Richtung beziehen sich bei Regeln und ohne Konto auf die Summe der Splits auf Bestandskonten, im Kontoblatt auf die Splits des angezeigten Kontos.

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

- Textvergleiche ignorieren Groß- und Kleinschreibung und gleichen Umlaute an (`ü` = `ue`). Die Textmethoden kennen `case=True` (Schreibung beachten) und `fold=False` (Umlaute nicht angleichen). Mehrfache Leerzeichen werden nicht zusammengefasst.
- Reguläre Ausdrücke haben garantiert lineare Laufzeit: Rückverweise und Lookarounds sind ein Fehler (`regex_nicht_unterstuetzt`).
- Beträge: Dezimalpunkt, höchstens zwei Nachkommastellen, Unterstrich als Zifferntrenner.
- Verweise auf Konto, Kategorie und Tag stehen als Text; gespeichert wird der Bezug, nicht der Name. Nach einer Umbenennung zeigt der Ausdruck den neuen Namen. Ein unbekannter Name ist ein Fehler (`referenz_unbekannt`).
- Nicht erlaubt: Ausdrücke ohne Wahrheitswert (`empfänger` allein) und Vergleiche ungleicher Typen (`betrag > "10"`).

### 2.4 Datumsangaben (nur im Kontext `filter`)

Jede Datumsangabe steht für einen Zeitraum ganzer Tage. Relative Angaben beziehen sich auf den Bezugstag (heute nach der Uhr der App, über `stichtag` übersteuerbar).

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

- Einheiten: `d`/`t` Tag, `w` Woche, `m` Monat, `q` Quartal, `y`/`j` Jahr. Gibt es beim Rechnen mit Monaten den Tag im Zielmonat nicht, gilt dessen letzter Tag.
- Vergleiche mit einem Zeitraum von `a` bis `b`: `==` und `in` treffen von `a` bis `b`; `>=` ab `a`; `>` nach `b`; `<=` bis `b`; `<` vor `a`.
- `29.2.` ohne Jahr gilt in einem Nichtschaltjahr als 28.02. Andere unmögliche Tage (`30.2.`) sind ein Fehler (`datum_ungueltig`), ebenso `5.2` ohne Schlusspunkt an einem Datumsfeld.
- `5d` ohne Vorzeichen ist ein Fehler (`dauer_ohne_vorzeichen`).
- `X .. Y` mit vollständigen Jahreszahlen auf beiden Seiten und Ende vor Beginn ist ein Fehler (`zeitraum_leer`). Ein Zeitraum mit relativen Angaben, der vor seinem Beginn endet, ist gültig und trifft nichts.
- Im Kontext `regel` sind `datum`, `jahr`, `kw` und jede Datumsangabe ein Fehler (`nur_im_filter`).

### 2.5 Freitext (nur im Kontext `filter`)

- Enthält die Eingabe kein Feld, keinen Operator und kein Schlüsselwort, ist sie eine Volltextsuche: Alle Wörter müssen in Empfänger, Verwendungszweck, Notiz oder Tags vorkommen.
- Ein allein stehender Text in Anführungszeichen und ein allein stehendes unbekanntes Wort sind Freitext: `rewe bet > 20` bedeutet `"rewe" and betrag > 20`. Teile ohne Verknüpfung werden mit `and` verbunden.
- Im Kontext `regel` ist ein unbekanntes Wort ein Fehler (`feld_unbekannt`).

### 2.6 Kanonische Schreibweise

Volle Feldnamen, `and`/`or`/`not`, doppelte Anführungszeichen, eckige Listen, Leerzeichen um Operatoren, Klammern nur wo nötig. Datumsangaben mit führenden Nullen (`05.02.`), relative Angaben bleiben relativ. Freitext steht in Anführungszeichen mit `and`.

Beispiel: `rewe bet>20 && dt in -5d` wird zu `"rewe" and betrag > 20 and datum in -5d`.

## 3 Prüfen und Sprache abfragen

### 3.1 `GET /api/ausdruck/sprache`

Parameter `kontext` (`regel` oder `filter`). Antwort 200 mit `kontext`, `felder` (je Feld `name`, `kurz` oder `null`, `typ`, `bezeichnung`, `operatoren`, `werte`, `nur_filter`), `schluesselwoerter`, `aliase`, `methoden` und `kwargs`. Im Kontext `regel` fehlen die Felder `datum`, `jahr` und `kw`.

### 3.2 `POST /api/ausdruck/pruefen`

Körper: `ausdruck` (Pflicht), `kontext` (`regel` oder `filter`), `stichtag`, `festschreiben`. Lesezugriff ohne Protokolleintrag. Antwort 200, auch bei einem fehlerhaften Ausdruck:

| Feld | Inhalt |
| --- | --- |
| `gueltig` | Wahrheitswert |
| `fehler` | Liste aus `code`, `meldung`, `zeile`, `spalte`, `ende_zeile`, `ende_spalte`, `erwartet` |
| `kanonisch` | kanonischer Text, sonst `null` |
| `baum` | strukturierte Form, sonst `null` |
| `baukasten_faehig` | Wahrheitswert |
| `hinweise` | Hinweise ohne Fehler, z. B. ein Wort, das als Freitext gelesen wird |
| `datumsangaben` | je Angabe `text`, `von`, `bis`, `tage`, `relativ` |
| `freitext` | erkannte Freitext-Teile |
| `zusammenfassung` | die Teile auf oberster Ebene als deutscher Text |

- Zeile und Spalte zählen ab 1.
- Mit `festschreiben` wahr sind relative Datumsangaben im kanonischen Text durch feste ersetzt.
- Ein leerer Ausdruck ist ungültig (`syntax`).

Fehlercodes: `syntax`, `feld_unbekannt`, `methode_unbekannt`, `operator_unpassend`, `kein_wahrheitswert`, `wert_ungueltig`, `regex_ungueltig`, `regex_nicht_unterstuetzt`, `referenz_unbekannt`, `nur_im_filter`, `datum_ungueltig`, `zeitraum_leer`, `dauer_ohne_vorzeichen`, `einheit_unbekannt`, `zu_lang`.

### 3.3 `POST /api/ausdruck/als-regel`

Körper: `ausdruck` (Filter, Pflicht), `freitext_feld` (`empfänger` oder `verwendungszweck`, Vorgabe `empfänger`). Antwort 200 mit `ausdruck` (Regel-Ausdruck) und `entfernt` (Liste der nicht übernommenen Teile). Teile auf oberster Ebene, die es nur im Filter gibt, entfallen; Freitext wird zu `"…" in <freitext_feld>`. Bleibt nichts übrig, ist `ausdruck` `null`.

## 4 Filter in der Buchungsliste

- `GET /api/buchungen` und der Export nehmen `filter` (Ausdruck im Kontext `filter`) und `stichtag` an.
- `filter` wird mit den übrigen Parametern per `and` verknüpft. Sortierung, Seiten und Summe verhalten sich wie bisher.
- Ein ungültiger Ausdruck ergibt 422 `ausdruck_ungueltig`; `details.fehler` hat die Form aus 3.2.
- Bei aktivem Filter trägt jeder Eintrag `markierungen`: Liste aus `feld`, `start`, `ende` für die Textstellen, die eine Bedingung erfüllt haben.
- Reiner Lesezugriff, kein Protokolleintrag.

## 5 Regeln

### 5.1 Aufbau

Eine Regel hat Name, Aktiv-Schalter, Priorität, Bedingung und Aktionen. Aktionen sind eine Kategorie, Tags oder beides.

| Feld | Regel |
| --- | --- |
| `name` | 1–200 Zeichen ohne Rand-Leerraum |
| `aktiv` | Wahrheitswert, Vorgabe wahr |
| `prioritaet` | 0 bis 1 000 000; Vorgabe größte vorhandene + 10, ohne Regeln 100 |
| `kategorie_id` | Aufwands- oder Ertragskonto oder `null` |
| `tag_ids` | höchstens 20 verschiedene vorhandene Tags; Vorgabe leer |
| `ausdruck` | Text im Kontext `regel`, 1–4000 Zeichen |
| `bedingungen` | die bisherige Form; genau eines von `ausdruck` und `bedingungen` |

Antworten enthalten zusätzlich:

- `ausdruck`: kanonischer Text. Regeln in der bisherigen Form werden gleichbedeutend übersetzt, z. B. „Empfänger enthält REWE“ zu `"REWE" in empfänger`.
- `ausdruck_form`: `ausdruck` oder `bedingungen`.
- `tag_ids`: aufsteigend, immer vorhanden.
- `bedingungen`: bei Regeln mit Ausdruck genau ein Eintrag mit `feld` und `operator` gleich `ausdruck` und der strukturierten Form als `wert`.
- `automatisch` und `empfaenger_id` nur bei automatisch angelegten Regeln, wie bisher.

Regeln in der bisherigen Form bleiben gespeichert und wirken unverändert.

### 5.2 Fehler beim Anlegen und Ändern

| Fall | Antwort |
| --- | --- |
| weder Kategorie noch Tags beim Anlegen | 422 `validierung`, Ort `body`, `kategorie_id` |
| Ändern lässt weder Kategorie noch Tags übrig | 422 `regel_ohne_aktion` |
| `ausdruck` und `bedingungen` zugleich, oder keines beim Anlegen | 422 `validierung` |
| ungültiger Ausdruck | 422 `ausdruck_ungueltig` mit `details.fehler` |
| Kategorie ist kein Aufwands- oder Ertragskonto | 422 `kategorie_ungueltig` |
| unbekannter Tag | 422 `referenz_unbekannt` mit `details.tag_ids` |
| doppelte oder mehr als 20 Tags | 422 `validierung`, Ort `body`, `tag_ids` |

### 5.3 Auswertung

- Regeln laufen nach Priorität aufsteigend, bei Gleichstand nach ID. Nur aktive Regeln wirken.
- **Kategorie:** Es gilt die erste passende Regel, die eine Kategorie hat. Regeln ohne Kategorie verdecken nichts. Die Kategorie entsteht wie bisher als Vorschlag mit Quelle `regel`.
- **Tags:** Die Tags aller passenden Regeln werden der Buchung hinzugefügt. Vorhandene Tags bleiben; nie wird ein Tag entfernt. Tags sind keine Vorschläge und gelten sofort.
- Gesperrte Buchungen (abgestimmt oder abgeglichen) bleiben unberührt.

Wann Tags vergeben werden:

| Vorgang | Buchungen |
| --- | --- |
| Synchronisation | jede neu angelegte Buchung, gleich welche Stufe die Kategorie bestimmt hat |
| `POST /api/regeln/anwenden` | jede nicht gesperrte Buchung im Umfang, auch Splitbuchungen und bereits kategorisierte, auch mit `nur_unkategorisiert` |
| `POST /api/regeln/{id}/anwenden` | jeder nicht gesperrte Treffer der Regel, auch verdeckte und abweichende |

`POST /api/regeln/anwenden` liefert zusätzlich `tags`: je Buchung `buchung_id` und `tag_ids` der neu vergebenen Tags. Das Feld fehlt, wenn keine Tags vergeben wurden. Mit `trocken` wird nichts geändert, `tags` nennt aber, was vergeben würde.

### 5.4 Verweise

- Konten und Kategorien, auf die ein Ausdruck verweist, zählen wie die Kategorie der Regel: Das Konto ist nicht löschbar; beim Löschen mit Umleiten und beim Zusammenführen wird der Verweis ersetzt.
- Wird ein Tag gelöscht, den ein Ausdruck in der Bedingung nennt, trifft dieser Teil nie mehr; der Ausdruck zeigt `"#<id>"`.
- Wird ein Tag gelöscht, den eine Regel vergibt, bleibt die Regel und verliert den Tag. Hat sie danach weder Kategorie noch Tags, bleibt sie ohne Wirkung bestehen.

### 5.5 `POST /api/regeln/reihenfolge`

Körper: `regel_ids`, vollständige Liste aller Regeln in der gewünschten Reihenfolge. Die Prioritäten werden 10, 20, 30 … Antwort 200: die Regelliste. Fehlt eine Regel, ist eine unbekannt oder doppelt: 422 `validierung`; `details` nennt `fehlend` und `unbekannt`.

### 5.6 `POST /api/regeln/test`

Lesezugriff ohne Protokolleintrag. Zeigt, was eine Regel an vorhandenen Buchungen bewirken würde.

Körper:

| Feld | Inhalt |
| --- | --- |
| `ausdruck` | ungespeicherte Bedingung; sonst die der Regel `regel_id` |
| `regel_id` | gespeicherte Regel; mit `ausdruck` zusammen: die Regel, die dieser Stand ersetzt |
| `kategorie_id` | Kategorie oder `null`; fehlt das Feld, gilt die der Regel `regel_id` |
| `tag_ids` | Tags; fehlt das Feld, gelten die der Regel `regel_id` |
| `testmenge` | Filter-Ausdruck; Vorgabe `datum in -12m`; leer = alle Buchungen |
| `konto_id` | nur Buchungen mit einem Split auf diesem Bestandskonto |
| `stichtag`, `wirkung`, `seite`, `pro_seite` | Bezugstag, Einschränkung auf Wirkungen, Seite (je 100) |

Antwort 200:

- `testmenge_anzahl`, `anzahl` (Treffer), `zaehlung` je Wirkung, `tags_anzahl` (Treffer, denen mindestens ein Tag fehlt), `gesperrt_anzahl`, `gesamt`, `seite`, `pro_seite`.
- `treffer`: je Buchung `buchung_id`, `datum`, `betrag`, `empfaenger`, `verwendungszweck`, `konto_ids`, `kategorie_vorher`, `kategorie_nachher`, `wirkung`, `verdeckt_von` (`id`, `name`), `grund`, `markierungen`, `tags_neu`.
- `nicht_erfasst`: `anzahl` und `buchung_ids` der Buchungen der Testmenge, die die Kategorie haben, aber nicht treffen.

Wirkungen:

| Wirkung | Bedeutung |
| --- | --- |
| `neu` | unkategorisiert; die Regel würde die Kategorie setzen |
| `abweichend` | hat eine andere Kategorie |
| `bereits_so` | hat schon die Kategorie der Regel |
| `verdeckt` | eine frühere Regel mit Kategorie gewinnt; `verdeckt_von` nennt sie |
| `uebersprungen` | `grund` ist `gesperrt` oder `splitbuchung` |
| `treffer` | Regel ohne Kategorie |

- Ohne Kategorie ist jeder nicht gesperrte Treffer `treffer`, auch Splitbuchungen.
- `tags_neu` nennt die Tags der Regel, die der Buchung fehlen; bei gesperrten Buchungen ist die Liste leer.

Fehler: 422 `validierung` ohne `ausdruck` und ohne `regel_id`; 422 `ausdruck_ungueltig` (auch für `testmenge`); 422 `kategorie_ungueltig`; 422 `referenz_unbekannt` bei unbekanntem Tag; 422 `konto_ungueltig`, wenn `konto_id` kein Bestandskonto ist; 404 bei unbekannter `regel_id`.

### 5.7 `POST /api/regeln/erklaeren`

Körper: `ausdruck` oder `regel_id`, dazu `buchung_id` (Pflicht) und `stichtag`. Lesezugriff. Antwort 200 mit `buchung_id`, `ergebnis` und `baum`. Jeder Knoten hat `text`, `art` und `ergebnis` (`wahr`, `falsch`, `nicht_ausgewertet`); Vergleiche tragen den tatsächlichen Wert als `wert`, Verknüpfungen ihre `kinder`.

### 5.8 `POST /api/regeln/{id}/anwenden`

Körper: `testmenge`, `konto_id`, `buchung_ids`, `abweichende_ueberschreiben` (Vorgabe falsch), `stichtag`. Umfang wie beim Test.

- Die Kategorie der Regel wird als Vorschlag gesetzt bei Treffern mit Wirkung `neu`, mit `abweichende_ueberschreiben` auch bei `abweichend`.
- Die Tags der Regel kommen an jeden nicht gesperrten Treffer.
- Antwort 200: `geaendert` (aufsteigende Buchungs-IDs) und `anzahl`.

## 6 Protokoll und Datensicherung

- Anlegen, Ändern und Löschen von Regeln sind Änderungen wie bisher. Neu: Aktion `regeln_reihenfolge` für das Umsortieren.
- `POST /api/regeln/{id}/anwenden` ist genau eine Änderung mit Aktion `regeln_anwenden` und Quelle `regeln`, wenn sich etwas ändert. Rückgängig nimmt Kategorievorschläge und vergebene Tags zurück.
- Die Protokollform einer Regel enthält `tag_ids` nur, wenn die Regel Tags hat. Die Felder `ausdruck` und `ausdruck_form` gehören nicht zur Protokollform.
- Das Löschen eines Tags, den Regeln vergeben, ändert diese Regeln in derselben Änderung; Rückgängig stellt Tag und Zuordnung wieder her.
- Rückgängig einer Tag-Anlage scheitert, solange eine Regel den Tag vergibt, die nicht zum selben Schritt gehört.
- Datensicherung: Schemaversion 9 der Sicherungsdatei. Sie enthält die Tags der Regeln; die Kategorie einer Regel darf leer sein. Sicherungen der Versionen 1 bis 8 lassen sich weiter einspielen.
- Die Datenbank wird beim Start ohne Datenverlust umgestellt; Regeln, ihre IDs und der Vermerk „automatisch angelegt“ bleiben erhalten.

## 7 Oberfläche: Ausdrucksfeld

Ein Ausdrucksfeld mit der Kennung `<k>` besteht aus dem Textfeld `<k>`, der Marke `<k>-status` (`data-status`: `leer`, `pruefe`, `ok`, `fehler`) und der Zeile `<k>-fehler`.

- Die Eingabe wird nach kurzer Tipppause geprüft. Bei einem Fehler trägt das Textfeld `aria-invalid="true"`, die Fehlerzeile nennt Spalte und Meldung, und die Fehlerstelle ist hervorgehoben.
- Felder, Kurzformen, Schlüsselwörter und Datumswörter werden zur Vervollständigung angeboten.
- Das Feld wächst mit dem Inhalt.

## 8 Oberfläche: Filter im Kontoblatt

| `data-testid` | Element |
| --- | --- |
| `filter-ausdruck` | Ausdrucksfeld über der Liste, immer sichtbar |
| `filter-zusammenfassung` | Teile des Filters in Worten und Zahl der Buchungen |
| `filter-schnell-<wert>` | Zeitraum: `heute`, `-7d`, `-30d`, `dieser_monat`, `letzter_monat`, `dieses_jahr`, `letztes_jahr` |
| `filter-ausdruck-leeren` | leert den Filter |
| `filter-ausdruck-menue` | „Jahr festschreiben“, „Als Regel speichern…“ |
| `filter-baukasten-umschalten` | klappt den Baukasten ein und aus (`aria-expanded`), trägt `filter-anzahl` mit `data-anzahl` |
| `filter-leiste`, `filter-baukasten` | Baukasten; Zeilen `bk-<n>-feld`, `bk-<n>-op`, `bk-<n>-wert`, `bk-<n>-weg` |
| `filter-baukasten-hinweis` | erscheint, wenn der Ausdruck nicht in den Baukasten passt |
| `filter-zuruecksetzen` | setzt alle Filter zurück |
| `filter-alt-<name>` | Filter ohne Entsprechung im Ausdruck |

Verhalten:

- Gefiltert wird nach kurzer Tipppause oder Enter, aber nur mit gültigem Ausdruck. Bei einem Fehler bleibt die letzte gültige Liste stehen.
- Der Filter steht in der Adresse als `filter=…`.
- Treffer in Empfänger und Verwendungszweck sind hervorgehoben.
- Ein Zeitraum-Knopf ersetzt einen vorhandenen `datum`-Teil auf oberster Ebene oder hängt ihn mit `and` an.
- Der Baukasten ist beim Öffnen einer Kontoansicht eingeklappt. Baukasten und Ausdrucksfeld sind gekoppelt: Eine Änderung im einen schreibt das andere.
- Der Baukasten ersetzt die bisherigen Einzelfelder (Von, Bis, Betrag, Empfänger, Verwendungszweck, Freitext, Kategorie, Tag, Status). Den Knopf `filter-umschalten` gibt es nicht mehr.
- Alte Adressen: `von`, `bis`, `empfaenger_id`, `ohne_empfaenger`, `verwendungszweck`, `zweck_gleich`, `zweck_leer`, `suche`, `kategorie_id` ohne Unterkategorien, `tag_id` und `status` werden beim Öffnen in den Ausdruck übernommen.
- Ohne Entsprechung im Ausdruck bleiben `betrag_min`, `betrag_max`, `zweck_aehnlich`, `empfaenger_aehnlich` und `kategorie_id` mit Unterkategorien; sie erscheinen als `filter-alt-<name>` mit Entfernen-Knopf.
- „Als Regel speichern…“ nennt die Teile, die nicht übernommen werden, und öffnet nach Bestätigung den Regeleditor mit dem Regel-Ausdruck.
- Tastenkürzel: `f a` Ausdrucksfeld, `f f` Baukasten, `f h`/`w`/`d`/`m`/`l`/`j`/`J` Zeiträume, `f x` Zeitraum entfernen. Die Kürzel der Einzelfelder entfallen.

## 9 Oberfläche: Regeln

### 9.1 Regelliste

Je Regel `regel-<id>` mit Griff `regel-griff-<id>`, Schalter `regel-aktiv-<id>`, Name, Ziel `regel-ziel-<id>` und Ausdruck `regel-ausdruck-<id>`; Knöpfe Bearbeiten, Duplizieren, Löschen.

- Das Ziel zeigt die Kategorie und je vergebenem Tag „+ Name“. Ohne Kategorie und ohne Tags steht „(keine Aktion)“.
- Reihenfolge per Ziehen oder Alt+↑/↓ am Griff; jede Änderung ist ein Rückgängig-Schritt.
- `regel-anlegen` öffnet den Editor, `regeln-anwenden` bleibt.

### 9.2 Regeleditor (`regel-dialog`)

| `data-testid` | Element |
| --- | --- |
| `regel-name`, `regel-aktiv` | Name und Aktiv-Schalter |
| `regel-modus-baukasten`, `regel-modus-ausdruck` | Reiter; Vorgabe Ausdruck, die letzte Wahl wird gemerkt |
| `regel-ausdruck` | Ausdrucksfeld (Kontext `regel`) |
| `bk-<n>-feld`, `-op`, `-wert`, `-weg`, `bk-plus`, `bk-gruppe-plus` | Baukasten |
| `regel-baukasten-ausdruck`, `regel-ausdruck-kopieren` | erzeugter Ausdruck und Kopieren |
| `regel-baukasten-hinweis` | erklärt, warum der Baukasten nicht geht |
| `regel-uebernehmen` | Bedingung und Kategorie einer anderen Regel übernehmen |
| `regel-kategorie` | Kategorie; erster Eintrag „– keine Kategorie –“ mit leerem Wert |
| `regel-tag-eingabe`, `regel-tag-hinzufuegen` | Tag wählen oder neuen Namen eingeben |
| `regel-tags` | Tags der Regel; je Tag `regel-tag-entfernen-<name>` |
| `regel-prioritaet` | unter „Weitere Einstellungen“; leer = ans Ende |
| `regel-speichern`, `regel-speichern-anwenden` | Speichern |

Verhalten:

- Passt ein Ausdruck nicht in den Baukasten, ist der Reiter gesperrt; es gehen keine Teile verloren.
- Die bisherige Zeilenform („empfaenger enthaelt Bäckerei“) wird weiter angenommen.
- Kategorie: Bei einer neuen Regel ist die erste Kategorie vorgewählt. „keine Kategorie“ ist vorgewählt bei einer Regel, die nur Tags vergibt.
- Tags: Enter, Komma oder „Hinzufügen“ übernimmt die Eingabe. Ein vorhandener Tag wird unabhängig von der Schreibung erkannt; ein Name kommt nur einmal vor. Ein unbekannter Name ist als „(neu)“ gekennzeichnet.
- Neue Tags entstehen erst beim Speichern, zusammen mit der Regel in einem Rückgängig-Schritt. Abbrechen legt nichts an.
- Speichern ohne Kategorie und ohne Tags meldet „Die Regel braucht eine Kategorie oder mindestens einen Tag.“ und markiert das Kategorie-Feld.
- Leerer Name: Der Name wird vorgeschlagen aus dem ersten Text der Bedingung und der Kategorie, ohne Kategorie den Tags mit `#` (z. B. „AMAZON → Amazon“, „Einkauf → #Urlaub“). Der Vorschlag steht als Platzhalter im Feld und wird beim Speichern übernommen.

### 9.3 Testbereich (`regel-test`)

| `data-testid` | Element |
| --- | --- |
| `regel-test-konto` | Quellkonto, Vorgabe alle Konten |
| `test-zeitraum-12m`, `-jahr`, `-vorjahr`, `-alle` | Zeitraum der getesteten Buchungen (`aria-pressed`), Vorgabe 12 Monate |
| `test-zahlen` | Zählzeile mit `data-anzahl` (Treffer) und `data-tags` (Treffer, die Tags erhielten) |
| `test-status` | Zustand der Aktualisierung |
| `test-wirkung-<wirkung>`, `test-wirkung-alle` | Einschränkung auf eine Wirkung, mit `data-anzahl` |
| `test-liste` | Treffer; je Buchung `test-treffer-<id>` mit Kopfzeile `test-zeile-<id>` |
| `test-uebernehmen-<id>`, `test-warum-<id>` | „→ Bedingung“ und „Warum?“ in den Einzelheiten |
| `test-leer`, `test-alle` | Hinweis ohne Buchungen im Zeitraum und „Alle Buchungen testen“ |
| `test-nicht-erfasst` | Buchungen mit der Kategorie, die nicht treffen |
| `regel-test-anwenden` | Anwenden |

Verhalten:

- Ein eigenes Filterfeld für die Testmenge gibt es nicht. Die Bedingung der Regel filtert; eingrenzen lassen sich nur Zeitraum und Quellkonto.
- Der Test läuft nach jeder erfolgreichen Prüfung der Bedingung und nach jeder Änderung von Kategorie, Tags, Zeitraum oder Quellkonto. `regel-test` trägt `data-geladen` (`ja`/`nein`) und `data-veraltet` (`ja`/`nein`).
- Die Zählzeile lautet „n Treffer in m Buchungen (Zeitraum)“.
- Ohne Bedingung zeigt der Testbereich die Buchungen des Zeitraums. „→ Bedingung“ übernimmt `empf == "<Empfänger>" and dir == "<Richtung>"`, ohne Empfänger ein Wort aus dem Verwendungszweck.
- Ist die Bedingung ungültig, bleibt das letzte gültige Ergebnis als veraltet gekennzeichnet stehen.
- Scheitert der Test aus einem anderen Grund, verschwindet das alte Ergebnis und die Zählzeile nennt den Grund.
- Ohne gewählte Kategorie läuft der Test und zeigt die Treffer.
- Ein Klick auf eine Trefferzeile klappt die Einzelheiten auf: Verwendungszweck, Kategorie vorher → nachher, die Tags, die dazukämen, „→ Bedingung“ und „Warum?“.
- Anwenden-Knopf: ohne Tags „Auf n Buchung(en) anwenden…“; mit Kategorie und Tags „Anwenden: n × Kategorie, m × Tags…“; nur mit Tags „Tags an m Buchung(en) vergeben…“. Er ist gesperrt, wenn sich nichts ändern würde.
- Anwenden speichert eine neue oder geänderte Regel zuerst und fragt dann nach (`regel-anwenden-dialog`): `regel-anwenden-abweichende` nur bei Regeln mit Kategorie, `regel-anwenden-tags` nennt die Tags, `regel-anwenden-ok` führt aus.

## 10 Oberfläche: Fehlermeldungen

Lehnt der Server eine Eingabe mit `validierung` ab, zeigen Dialoge und Meldungen zusätzlich zu „Die Anfrage ist ungültig.“ je betroffenem Feld den Feldnamen und die Regel, z. B. „Name: 1–200 Zeichen (ohne Rand-Leerraum).“. Übergebene Werte erscheinen nie.

## 11 Sicherheit und Leistung

- Ausdrücke werden nie als Programmcode ausgeführt.
- Reguläre Ausdrücke können die App nicht blockieren (lineare Laufzeit, Längengrenze).
- Die Oberfläche lädt für Ausdrucksfeld und Editor keine Ressourcen von außen.

## 12 Änderungen an früheren Meilensteinen

- **M2 (Regeln):** Regeln liefern zusätzlich `ausdruck`, `ausdruck_form` und `tag_ids`; `kategorie_id` darf `null` sein und ist beim Anlegen nur noch Pflicht, wenn keine Tags genannt sind; `ausdruck` als Alternative zu `bedingungen`. `POST /api/regeln/anwenden` kann `tags` liefern. Die erste passende Regel ist die erste mit Kategorie.
- **M3 (Protokoll, Konto löschen, Suche):** Protokollform der Regel nach Abschnitt 6; Verweise aus Ausdrücken zählen beim Löschen und Zusammenführen von Konten.
- **M9 (Datensicherung):** Schemaversion 9; Regel ohne Kategorie und Tags der Regeln.
- **M8, M12, M17 und UXMobile (Oberfläche):** Die Einzelfelder der Filterleiste und der Knopf `filter-umschalten` entfallen; Filter über `filter-ausdruck` und Baukasten nach Abschnitt 8. Der Regel-Dialog hat die Elemente aus Abschnitt 9.
- **OpenAPI-Vertrag:** neue Endpunkte aus Abschnitt 3 und 5, Parameter `filter` und `stichtag` an der Buchungsliste, geänderte Schemata für Regel und Regel-Anwenden.

## 13 Hinweise für die Tests

- Bezugstag immer über `stichtag` bzw. die Uhr der App festlegen, damit relative Datumsangaben eindeutig sind.
- Für die Gleichwertigkeit alter Regeln: dieselbe Buchungsmenge einmal mit der bisherigen Form und einmal mit dem übersetzten Ausdruck prüfen, auch für vorzeichenbehaftete Betragsgrenzen.
- Für die Datenbank-Umstellung lässt sich der Zustand „vor der Umstellung“ nur in der Datenbank herstellen; den Weg legt der Test-Thread fest.
- Alles nur mit synthetischen Daten.

## 14 Bekannte Abweichungen vom Konzept `feature-regeln.md`

- Mehrfache Leerzeichen werden in Textvergleichen nicht zusammengefasst.
- Umlaute werden standardmäßig angeglichen; `fold=False` schaltet das ab.
- Statt eines Code-Editors gibt es ein Textfeld mit Hervorhebung.
- Der Zeilenumbruch der kanonischen Form vor `or` entfällt.
- Der Testbereich hat kein Filterfeld für die Testmenge mehr.
- Regeln speichern ihren Ausdruck in der bisherigen Bedingungsliste.
