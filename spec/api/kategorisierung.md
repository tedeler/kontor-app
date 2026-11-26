# Regel-Kategorisierung und Vorschläge – Meilenstein 2

Verbindlich für Implementierung und Tests. Umsetzung der ersten Stufe von
K 7 („Regeln: feste Zuordnungen“) und der Markierung „Vorschlag bis
bestätigt“. Das Lernmodell (zweite Stufe) ist M4. Ergänzt `datenmodell.md`
(Buchungsfeld `vorschlag`, Abschnitt 12) und `openapi.yaml` (Tag `regeln`).

## 1. Regel

| Feld | Typ | Pflicht beim Anlegen | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `name` | str | ja | 1–200 Zeichen nach `strip()` (wird gestrippt gespeichert) |
| `aktiv` | bool | nein (true) | inaktive Regeln greifen nie |
| `prioritaet` | int | nein | 0 ≤ p ≤ 1 000 000; kleiner = wichtiger. Vorgabe: größte vorhandene `prioritaet` + 10, ohne vorhandene Regel 100 |
| `kategorie_id` | int | ja | Konto der Art `aufwand` oder `ertrag`; sonst (auch unbekannt) 422 `kategorie_ungueltig` |
| `bedingungen` | Liste Bedingung | ja | 1–20 Einträge, UND-verknüpft |

Gleiche Prioritäten sind erlaubt. **Reihenfolge** aller Regeln:
`prioritaet` aufsteigend, bei Gleichstand `id` aufsteigend. `GET
/api/regeln` liefert genau diese Reihenfolge. Ab 8.10 (D-295): erst alle
eigenen, dann alle automatisch angelegten Regeln, je Gruppe in dieser
Reihenfolge.

### 1.1 Bedingung

`{feld, operator, wert}`:

| `feld` | `operator` | `wert` | trifft zu, wenn |
| --- | --- | --- | --- |
| `empfaenger` | `enthaelt`, `gleich`, `beginnt_mit` | str, 1–200 Zeichen, nicht nur Leerraum | die Buchung einen Empfänger hat und `norm(name)` den Text `norm(wert)` enthält / gleich ist / damit beginnt |
| `verwendungszweck` | `enthaelt`, `gleich`, `beginnt_mit` | wie oben | wie oben mit `verwendungszweck` (ggf. `""`) |
| `betrag` | `gleich`, `mindestens`, `hoechstens` | int (Betrag in Cent, Bereich wie `datenmodell.md` 1) | *Regelbetrag* `= / ≥ / ≤` `wert` |
| `konto_id` | `gleich` | int, existierendes Bestandskonto (sonst 422 `referenz_unbekannt`) | die Buchung einen Split auf diesem Konto hat |

- `norm` ist die Normalisierung aus `datenmodell.md` 1 (casefold, ä/ö/ü →
  ae/oe/ue). Der `wert` wird unverändert gespeichert.
- **Regelbetrag** einer Buchung = Summe der `betrag` aller Splits auf
  Bestandskonten (Sicht der eigenen Konten: Ausgaben negativ, Eingänge
  positiv). Bei einer synchronisierten Buchung ist das der Umsatzbetrag.
  Beispiel „Ausgabe von mehr als 50 €“: `{feld: betrag, operator:
  hoechstens, wert: -5001}`.
- Unbekanntes Feld, unpassender Operator, falscher Typ von `wert`, Wert
  außerhalb des Bereichs, unbekannte Zusatzfelder → 422 `validierung`.
- Reguläre Ausdrücke sind nicht vorgesehen.

### 1.2 Bezüge und Löschen

- Ein Konto, auf das eine Regel verweist (`kategorie_id` oder eine
  Bedingung `konto_id`), kann nicht gelöscht werden (409
  `konto_in_verwendung`, Erweiterung von `datenmodell.md` 2). Ab M3 ist
  das über `POST /api/konten/{konto_id}/loeschen` doch möglich; die Regel
  wird dann umgestellt oder gelöscht (`loeschen.md` 3.4).
- Löschen einer Regel setzt in allen Vorschlägen mit dieser `regel_id` das
  Feld `regel_id` auf null; die Vorschläge selbst bleiben.

## 2. REST

| Methode, Pfad | Ergebnis |
| --- | --- |
| `GET /api/regeln` | alle Regeln in Reihenfolge (1) |
| `POST /api/regeln` | 201 `Regel`; 422 `validierung`, `kategorie_ungueltig`, `referenz_unbekannt` |
| `GET /api/regeln/{regel_id}` | 200; 404 |
| `PATCH /api/regeln/{regel_id}` | nur angegebene Felder; `bedingungen` ersetzt die Liste; 200; 404; 422 wie POST |
| `DELETE /api/regeln/{regel_id}` | 204; 404 |
| `POST /api/regeln/anwenden` | 3; 200 `RegelAnwendung`; 422 `validierung`, `referenz_unbekannt` |

## 3. Anwenden auf vorhandene Buchungen

`POST /api/regeln/anwenden` mit (alle Felder optional)
`{buchung_ids: [int], regel_ids: [int], nur_unkategorisiert: bool = true,
trocken: bool = false}`:

1. Unbekannte IDs in `buchung_ids` → 422 `referenz_unbekannt` mit
   `details.buchung_ids` (aufsteigend); unbekannte `regel_ids` → 422
   `referenz_unbekannt` mit `details.regel_ids`. Doppelte IDs → 422
   `validierung`.
2. *Geprüfte Buchungen*: alle Buchungen (bzw. nur `buchung_ids`), die
   kategorisierbar sind (`datenmodell.md` 3.2), nicht den Status
   `abgeglichen` haben und – bei `nur_unkategorisiert = true` –
   `kategorie_id = null` haben (Gegensplit auf einem Eigenkapitalkonto, z. B.
   „Unkategorisiert“ oder „Unausgeglichen“). Andere Buchungen werden
   stillschweigend übergangen, auch wenn sie in `buchung_ids` stehen.
3. *Verwendete Regeln*: die aktiven Regeln (bei `regel_ids` nur diese,
   inaktive darunter werden ignoriert) in Reihenfolge (1).
4. Für jede geprüfte Buchung greift die erste verwendete Regel `R`, deren
   Bedingungen alle zutreffen. Ist das Konto des Gegensplits bereits
   `R.kategorie_id`, bleibt die Buchung unverändert. Sonst wird die
   Kategorie als Vorschlag gesetzt (5). Greift keine Regel, bleibt sie
   unverändert.
5. Atomar. Bei `trocken = true` wird nichts geändert, die Antwort ist
   dieselbe.

Antwort `RegelAnwendung`: `{geprueft: int, anzahl: int, trocken: bool,
aenderungen: [{buchung_id, regel_id, kategorie_id}]}` mit `anzahl` =
Länge von `aenderungen`, nach `buchung_id` aufsteigend.

Neue Buchungen aus der Synchronisation werden beim Anlegen kategorisiert
(`synchronisation.md` 4.2): dieselbe Auswertung über alle aktiven Regeln.
Manuell angelegte und aus KMyMoney importierte Buchungen werden nicht
automatisch kategorisiert; Regeln werden beim Anlegen oder Ändern nicht
von selbst auf vorhandene Buchungen angewendet.

## 4. Auswertung (gemeinsam für Synchronisation und Anwenden)

- Text für `empfaenger`: Name des Empfängers der Buchung (bei der
  Synchronisation `gegenpartei_name.strip()`); ohne Empfänger trifft keine
  `empfaenger`-Bedingung zu.
- Text für `verwendungszweck`: `verwendungszweck` der Buchung.
- Erste passende aktive Regel in Reihenfolge (1) gewinnt (T 8: „festgelegte,
  getestete Priorität“).

## 5. Vorschlag (K 7: „als solche markiert, bis sie bestätigt sind“)

Buchungsfeld `vorschlag`: `null` oder

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `kategorie_id` | int | vorgeschlagene Kategorie = aktuelles Konto des Gegensplits |
| `regel_id` | int \| null | Regel, die gegriffen hat (null nach Löschen der Regel) |
| `quelle` | `"regel"` | weitere Quellen ab M3/M4 (Standardkategorie, Lernmodell) |
| `vorher_konto_id` | int | Konto des Gegensplits vor dem ersten noch offenen Vorschlag |

**Setzen eines Vorschlags** (Synchronisation oder Anwenden): Das Konto des
Gegensplits wird durch `R.kategorie_id` ersetzt (Betrag, Memo, Split-`id`
bleiben, wie „Kategorie setzen“, `datenmodell.md` 3.2). `vorschlag =
{kategorie_id, regel_id = R.id, quelle = "regel", vorher_konto_id}` mit
`vorher_konto_id` = bisheriges Konto des Gegensplits – hatte die Buchung
schon einen offenen Vorschlag, bleibt dessen `vorher_konto_id` erhalten.
Bei der Synchronisation ist `vorher_konto_id` das Konto „Unkategorisiert“
(es wird dafür angelegt, falls nötig). Status, Tags und übrige Felder
ändern sich nicht.

Invariante: Ist `vorschlag` nicht null, ist die Buchung kategorisierbar und
`kategorie_id = vorschlag.kategorie_id`.

**Bestätigen bzw. Erledigen** – danach ist `vorschlag = null`:

| Aktion | Wirkung auf die Kategorie |
| --- | --- |
| `POST /api/buchungen/{id}/vorschlag` `{"aktion": "annehmen"}` | bleibt |
| `POST /api/buchungen/{id}/vorschlag` `{"aktion": "ablehnen"}` | Gegensplit zurück auf `vorher_konto_id` (existiert das Konto nicht mehr: „Unkategorisiert“, ggf. neu angelegt) |
| `POST /api/buchungen/mehrfach/vorschlag` `{buchung_ids, aktion}` | wie einzeln, atomar |
| Kategorie setzen (einzeln oder Mehrfachbearbeitung) | die gesetzte Kategorie (manuelle Entscheidung) |
| Splits ersetzen | die neuen Splits |
| `PATCH` mit `status` `bestaetigt` oder `abgeglichen` (tatsächliche Änderung) | bleibt |

Andere Änderungen (Tags, Datum, Empfänger, Verwendungszweck) lassen den
Vorschlag unverändert. `annehmen`/`ablehnen` ändern den Status nicht.

Fehler: Buchung ohne offenen Vorschlag → 409 `kein_vorschlag` (einzeln)
bzw. 409 `kein_vorschlag` mit `details.buchung_ids` (mehrfach, nichts wird
geändert). Unbekannte Buchungen in der Mehrfachaktion → 422
`referenz_unbekannt` mit `details.buchung_ids`.

Filter `GET /api/buchungen?vorschlag=true|false`: nur Buchungen mit bzw.
ohne offenen Vorschlag (UND-verknüpft mit den übrigen Filtern).

Ein abgelehnter Vorschlag wird nicht gemerkt: Ein erneutes Anwenden der
Regeln kann ihn wieder setzen. Dass Korrekturen in künftige Vorschläge
einfließen, leistet das Lernmodell (M4).

## 6. Meilenstein 3: Ergänzungen

- `Vorschlag.quelle` hat zusätzlich den Wert `"standardkategorie"`
  (`buchhaltungspflege.md` 2.5); dann ist `regel_id = null`. Annehmen,
  Ablehnen und Erledigen wie in 5.
- Bei der Synchronisation ist der Text für `empfaenger` der Empfängername
  nach `synchronisation.md` 14.1 (Alias aufgelöst).
- „Abgeglichen“ in 3 Schritt 2 und in 5 gilt ab M3 für alle gesperrten
  Buchungen (`buchhaltungspflege.md` 1.3, 5.4): `POST /api/regeln/anwenden`
  übergeht abgestimmte Buchungen; `ablehnen` einer gesperrten Buchung → 409
  `buchung_gesperrt` (mehrfach: nach `kein_vorschlag` geprüft, mit
  `details.buchung_ids`); `annehmen` bleibt erlaubt.
- Jede Anwendung mit Wirkung erzeugt eine Änderung `regeln_anwenden`
  (`protokoll.md` 4.2); jedes Annehmen/Ablehnen eine Änderung
  `vorschlag_entscheiden` bzw. `mehrfach_vorschlag`.

## 7. Meilenstein 4: Ergänzungen

- Zweite Stufe (K 7): Lernmodell nach `lernmodell.md`. Stufenfolge bei neuen
  Buchungen der Synchronisation: Split-Vorlage (`vorlagen.md` 4) → Regel →
  Standardkategorie → Lernmodell (nur bei `lernmodell_automatisch`) →
  „Unkategorisiert“.
- `Vorschlag.quelle` hat zusätzlich den Wert `"lernmodell"` (dann
  `regel_id = null` und zusätzlich `sicherheit`). Annehmen, Ablehnen und alle
  Erledigungsregeln aus 5 gelten unverändert.
- Mit erledigten Vorschlägen und gesetzten Kategorien wächst die
  Trainingsmenge; „Korrekturen fließen ein“ (5, letzter Absatz) leistet ab
  M4 das Lernmodell.
- Ohne Vorlagen und mit `lernmodell_automatisch = False` (Vorgabe) bleibt
  alles in 1–6 unverändert (E-029, E-072).

## 8. Meilenstein 30: Regeln mit Ausdruck und Tags

Übernahme von Abschnitt 5 der Definition „Kontor-Ausdrücke …“ (E-268). Die
Ausdruckssprache steht in `ausdruecke.md`. Ändert 1 bis 4: Eine Regel hat
eine Bedingung in einer von zwei Formen und als Aktionen eine Kategorie,
Tags oder beides. Nicht im Umfang: die Aktionen „direkt bestätigen“ und
„danach keine weiteren Regeln“, Tags per Regel entfernen, Regeln beim Import
und bei von Hand angelegten Buchungen, Trefferzahl und Verdeckungswarnung in
der Regelliste.

### 8.1 Aufbau

| Feld | Regel |
| --- | --- |
| `name` | 1–200 Zeichen ohne Rand-Leerraum (wie 1) |
| `aktiv` | Wahrheitswert, Vorgabe wahr |
| `prioritaet` | 0 bis 1 000 000; Vorgabe größte vorhandene + 10, ohne Regeln 100 |
| `kategorie_id` | Aufwands- oder Ertragskonto oder `null` |
| `tag_ids` | höchstens 20 verschiedene vorhandene Tags; Vorgabe leer |
| `ausdruck` | Text im Kontext `regel`, 1–4000 Zeichen |
| `bedingungen` | die bisherige Form (1.1); genau eines von `ausdruck` und `bedingungen` |

Antworten (`Regel`) enthalten zusätzlich:

- `ausdruck`: kanonischer Text (`ausdruecke.md` 2.6). Regeln in der
  bisherigen Form werden gleichbedeutend übersetzt, z. B. „Empfänger enthält
  REWE“ zu `"REWE" in empfänger`.
- `ausdruck_form`: `ausdruck` oder `bedingungen`.
- `tag_ids`: aufsteigend, immer vorhanden.
- `bedingungen`: bei Regeln mit Ausdruck genau ein Eintrag mit `feld` und
  `operator` gleich `ausdruck` und der strukturierten Form als `wert`; bei
  Regeln der bisherigen Form unverändert die Liste aus 1.1.
- `automatisch` und `empfaenger_id` nur bei automatisch angelegten Regeln
  (Festlegung mit dem Lernmodell-Paket; hier nur im Schema zugelassen).

Regeln in der bisherigen Form bleiben gespeichert und wirken unverändert.
`PATCH` mit `ausdruck` oder `bedingungen` ersetzt die Bedingung in der
jeweils angegebenen Form.

### 8.2 Fehler beim Anlegen und Ändern

| Fall | Antwort |
| --- | --- |
| weder Kategorie noch Tags beim Anlegen (`kategorie_id` fehlt oder `null`, `tag_ids` fehlt oder leer) | 422 `validierung`, Ort `body`, `kategorie_id` |
| Ändern lässt weder Kategorie noch Tags übrig | 422 `regel_ohne_aktion` |
| `ausdruck` und `bedingungen` zugleich, oder keines beim Anlegen | 422 `validierung` |
| ungültiger Ausdruck | 422 `ausdruck_ungueltig` mit `details.fehler` (`ausdruecke.md` 4.2) |
| Kategorie ist kein Aufwands- oder Ertragskonto | 422 `kategorie_ungueltig` |
| unbekannter Tag | 422 `referenz_unbekannt` mit `details.tag_ids` (aufsteigend) |
| doppelte oder mehr als 20 Tags | 422 `validierung`, Ort `body`, `tag_ids` |

### 8.3 Auswertung (ersetzt „erste passende Regel“ in 3 und 4)

- Regeln laufen nach Priorität aufsteigend, bei Gleichstand nach ID. Nur
  aktive Regeln wirken.
- **Kategorie:** Es gilt die erste passende Regel, die eine Kategorie hat.
  Regeln ohne Kategorie verdecken nichts. Die Kategorie entsteht wie bisher
  als Vorschlag mit Quelle `regel` (5).
- **Tags:** Die Tags aller passenden Regeln werden der Buchung hinzugefügt.
  Vorhandene Tags bleiben; nie wird ein Tag entfernt. Tags sind keine
  Vorschläge und gelten sofort.
- Gesperrte Buchungen (abgestimmt oder abgeglichen) bleiben unberührt.

Wann Tags vergeben werden:

| Vorgang | Buchungen |
| --- | --- |
| Synchronisation | jede neu angelegte Buchung, gleich welche Stufe die Kategorie bestimmt hat |
| `POST /api/regeln/anwenden` | jede nicht gesperrte Buchung im Umfang, auch Splitbuchungen und bereits kategorisierte, auch mit `nur_unkategorisiert` |
| `POST /api/regeln/{id}/anwenden` | jeder nicht gesperrte Treffer der Regel, auch verdeckte und abweichende |

`POST /api/regeln/anwenden` liefert zusätzlich `tags`: je Buchung
`buchung_id` und `tag_ids` der neu vergebenen Tags (nach `buchung_id`
aufsteigend, `tag_ids` aufsteigend). Das Feld fehlt, wenn keine Tags
vergeben wurden. Mit `trocken` wird nichts geändert, `tags` nennt aber, was
vergeben würde. Werden nur Tags vergeben, entsteht ebenfalls eine Änderung
`regeln_anwenden` (6).

### 8.4 Verweise

- Konten und Kategorien, auf die ein Ausdruck verweist, zählen wie die
  Kategorie der Regel (1.2): Das Konto ist nicht löschbar (409
  `konto_in_verwendung`); beim Löschen mit Umleiten (`loeschen.md` 8) und
  beim Zusammenführen (`alfbanco.md` 5) wird der Verweis ersetzt.
- Wird ein Tag gelöscht, den ein Ausdruck in der Bedingung nennt, trifft
  dieser Teil nie mehr; der Ausdruck zeigt `"#<id>"`.
- Wird ein Tag gelöscht, den eine Regel vergibt, bleibt die Regel und
  verliert den Tag. Hat sie danach weder Kategorie noch Tags, bleibt sie
  ohne Wirkung bestehen.

### 8.5 `POST /api/regeln/reihenfolge`

Körper: `regel_ids`, vollständige Liste aller Regeln in der gewünschten
Reihenfolge. Die Prioritäten werden 10, 20, 30 … Antwort 200: die
Regelliste (wie `GET /api/regeln`). Fehlt eine Regel, ist eine unbekannt
oder doppelt: 422 `validierung`; `details` nennt `fehlend` und `unbekannt`
(Listen von IDs). Nichts wird geändert.

### 8.6 `POST /api/regeln/test`

Lesezugriff ohne Protokolleintrag. Zeigt, was eine Regel an vorhandenen
Buchungen bewirken würde.

| Feld | Inhalt |
| --- | --- |
| `ausdruck` | ungespeicherte Bedingung; sonst die der Regel `regel_id` |
| `regel_id` | gespeicherte Regel; mit `ausdruck` zusammen: die Regel, die dieser Stand ersetzt |
| `kategorie_id` | Kategorie oder `null`; fehlt das Feld, gilt die der Regel `regel_id` |
| `tag_ids` | Tags; fehlt das Feld, gelten die der Regel `regel_id` |
| `testmenge` | Filter-Ausdruck; Vorgabe `datum in -12m`; leer = alle Buchungen |
| `konto_id` | nur Buchungen mit einem Split auf diesem Bestandskonto |
| `stichtag`, `wirkung`, `seite`, `pro_seite` | Bezugstag, Einschränkung auf Wirkungen, Seite (je 100) |

Antwort 200 (`RegelTestErgebnis`):

- `testmenge_anzahl`, `anzahl` (Treffer), `zaehlung` je Wirkung,
  `tags_anzahl` (Treffer, denen mindestens ein Tag fehlt),
  `gesperrt_anzahl`, `gesamt`, `seite`, `pro_seite`.
- `treffer`: je Buchung `buchung_id`, `datum`, `betrag`, `empfaenger`,
  `verwendungszweck`, `konto_ids`, `kategorie_vorher`, `kategorie_nachher`,
  `wirkung`, `verdeckt_von` (`id`, `name`), `grund`, `markierungen`,
  `tags_neu`.
- `nicht_erfasst`: `anzahl` und `buchung_ids` der Buchungen der Testmenge,
  die die Kategorie haben, aber nicht treffen.

| Wirkung | Bedeutung |
| --- | --- |
| `neu` | unkategorisiert; die Regel würde die Kategorie setzen |
| `abweichend` | hat eine andere Kategorie |
| `bereits_so` | hat schon die Kategorie der Regel |
| `verdeckt` | eine frühere Regel mit Kategorie gewinnt; `verdeckt_von` nennt sie |
| `uebersprungen` | `grund` ist `gesperrt` oder `splitbuchung` |
| `treffer` | Regel ohne Kategorie |

- Ohne Kategorie ist jeder nicht gesperrte Treffer `treffer`, auch
  Splitbuchungen.
- `tags_neu` nennt die Tags der Regel, die der Buchung fehlen; bei
  gesperrten Buchungen ist die Liste leer.
- „Frühere Regel“: eine aktive Regel mit Kategorie, die in der Reihenfolge
  (1) vor der getesteten steht; eine ungespeicherte Bedingung ohne
  `regel_id` steht am Ende.

Fehler: 422 `validierung` ohne `ausdruck` und ohne `regel_id`; 422
`ausdruck_ungueltig` (auch für `testmenge`); 422 `kategorie_ungueltig`; 422
`referenz_unbekannt` bei unbekanntem Tag; 422 `konto_ungueltig`, wenn
`konto_id` kein Bestandskonto ist; 404 bei unbekannter `regel_id`.

### 8.7 `POST /api/regeln/erklaeren`

Körper: `ausdruck` oder `regel_id`, dazu `buchung_id` (Pflicht) und
`stichtag`. Lesezugriff. Antwort 200 mit `buchung_id`, `ergebnis` und
`baum`. Jeder Knoten hat `text`, `art` und `ergebnis` (`wahr`, `falsch`,
`nicht_ausgewertet`); Vergleiche tragen den tatsächlichen Wert als `wert`,
Verknüpfungen ihre `kinder`.

### 8.8 `POST /api/regeln/{id}/anwenden`

Körper: `testmenge`, `konto_id`, `buchung_ids`,
`abweichende_ueberschreiben` (Vorgabe falsch), `stichtag`. Umfang wie beim
Test (Vorgabe der Testmenge `datum in -12m`).

- Die Kategorie der Regel wird als Vorschlag gesetzt bei Treffern mit
  Wirkung `neu`, mit `abweichende_ueberschreiben` auch bei `abweichend`.
- Die Tags der Regel kommen an jeden nicht gesperrten Treffer.
- Antwort 200: `geaendert` (aufsteigende Buchungs-IDs) und `anzahl`.
- Unbekannte Regel: 404.

### 8.9 Protokoll, Sicherung, Umstellung

`protokoll.md` 22, `sicherung.md` 12. Die Datenbank wird beim Start ohne
Datenverlust umgestellt; Regeln, ihre IDs und der Vermerk „automatisch
angelegt“ bleiben erhalten (in kontor-tests nicht prüfbar, E-273).

### 8.10 Eigene und automatisch angelegte Regeln (Feature `regelgruppen`, D-295)

- **Zwei Gruppen:** Eigene Regeln (ohne `automatisch`) und automatisch
  angelegte Regeln (`automatisch: true`, `lernmodell.md` 9). Alle eigenen
  Regeln stehen vor allen automatisch angelegten, unabhängig von
  `prioritaet`. Innerhalb jeder Gruppe gilt `prioritaet` aufsteigend, dann
  `id`.
- Diese Reihenfolge gilt überall: `GET /api/regeln`, Auswertung bei der
  Synchronisation und beim Anwenden (8.3), Verdeckung im Test (8.6: nur
  Regeln davor in dieser Reihenfolge verdecken).
- `POST /api/regeln/reihenfolge` (8.5) nimmt weiter die vollständige Liste.
  Die Gruppen bleiben: Die Prioritäten werden 10, 20, 30 … in der
  Reihenfolge „eigene Regeln in der Reihenfolge der Liste, danach die
  automatisch angelegten in der Reihenfolge der Liste“.
- Eine neue Regel ohne `prioritaet` bekommt wie bisher die größte vorhandene
  `prioritaet` + 10; als eigene Regel steht sie damit am Ende der eigenen.

#### `POST /api/regeln/{id}/uebernehmen`

Ohne Körper. Macht aus einer automatisch angelegten Regel eine eigene.

- Name, Aktiv, Kategorie, Bedingungen und Tags bleiben. Der Vermerk
  „automatisch angelegt“ entfällt (`automatisch`, `empfaenger_id` fehlen
  danach). `prioritaet` wird die größte `prioritaet` der eigenen Regeln
  + 10 (ohne eigene Regeln 100): Die Regel steht am Ende der eigenen.
- Der Empfänger der Regel wird gesperrt (`lernregel_gesperrt`): Für ihn
  entsteht keine neue automatische Regel, auch wenn die übernommene Regel
  später geändert oder gelöscht wird.
- Antwort 200: die Regel (wie `GET /api/regeln/{id}`).
- Fehler: 404 bei unbekannter Regel; 422 `regel_nicht_automatisch`, wenn die
  Regel keine automatisch angelegte ist. Nichts wird geändert.
- Genau eine Änderung `regel_uebernehmen` (`protokoll.md` 25). Rückgängig
  stellt Vermerk, Priorität und Sperre wieder her.
