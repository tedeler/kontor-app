# Änderungsprotokoll und Rückgängig – Meilenstein 3, 4, 5, 6, 9, 15, 18, 19 und 20

Verbindlich für Implementierung und Tests. Umsetzung von K 14
(„Änderungsprotokoll: jede automatische und manuelle Änderung
nachvollziehbar, mit Rückgängig-Funktion“) und der globalen Invarianten
T 3.5 („Jede automatische Änderung erzeugt einen Eintrag im
Änderungsprotokoll“) und T 3.6 („Rückgängig machen einer Änderung stellt
den vorherigen Zustand exakt wieder her“). Ergänzt `datenmodell.md`
(Abschnitt 13) und `openapi.yaml` (Tag `aenderungen`). Die übrigen
M3-Funktionen stehen in `buchhaltungspflege.md`.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

## 1. Begriffe

- **Buchbestand** sind genau die *protokollierten Objekte* der Arten in 2:
  Konten (inkl. Kategorien), Empfänger (inkl. Aliase und
  Standardkategorie), Tags, Buchungen (inkl. Splits, Tag-Zuordnung,
  Vorschlag, Herkunftskennungen, Abstimmungsmarken), Regeln,
  Dublettenverdachte und Abstimmungen – dazu, nur intern, die gemerkten
  Umsatzkennungen der Synchronisation (`synchronisation.md` 4.3).
- **Nicht** zum Buchbestand gehören und werden weder protokolliert noch
  durch Rückgängig verändert: Importvorgänge (`/api/importe`),
  Synchronisationsläufe, Zustand je Bankkonto (`/api/sync/konten`, Ausnahme
  in 6.4), TAN-Anforderungen, Benachrichtigungen, PIN, simulierte Uhr und
  das Änderungsprotokoll selbst.
- Eine **Änderung** ist die protokollierte Wirkung *einer* atomaren
  Operation auf den Buchbestand (Tabelle in 4). Sie besteht aus
  **Einträgen**, je geändertem Objekt genau einer.

## 2. Protokollform der Objekte

Einträge enthalten den Zustand eines Objekts vor und nach der Änderung in
der folgenden *Protokollform*. Sie ist so gewählt, dass sie sich aus den
REST-Antworten eindeutig ableiten lässt; abgeleitete Zählungen gehören nicht
dazu.

| `objekt` | Protokollform | Ableitung aus REST |
| --- | --- | --- |
| `konto` | Schema `Konto` (alle Felder) | `GET /api/konten/{id}` |
| `empfaenger` | Schema `Empfaenger` mit den M3-Feldern `{id, name, extern_id, aliase, standardkategorie_id}` | `GET /api/empfaenger/{id}` |
| `tag` | `{id, name, extern_id}` (Schema `TagZustand`) | `GET /api/tags` ohne `anzahl_buchungen` |
| `buchung` | Schema `BuchungZustand`: `{id, datum, empfaenger_id, verwendungszweck, status, splits, tag_ids, extern_ids, vorschlag, gegen_iban}` | aus `GET /api/buchungen/{id}`: `empfaenger_id` = `empfaenger.id` oder null, `tag_ids` = IDs aus `tags` (aufsteigend), `splits` unverändert (mit `abstimmung_id`), übrige Felder unverändert |
| `regel` | Schema `Regel` | `GET /api/regeln/{id}` |
| `verdacht` | Schema `Dublettenverdacht` | `GET /api/dubletten` |
| `abstimmung` | Schema `Abstimmung` | `GET /api/abstimmungen/{id}` |

Abgeleitete Felder der Buchung (`kategorie_id`, `betrag`, `ist_umbuchung`,
`abgestimmt`, Empfänger- und Tag-Namen) und `Tag.anzahl_buchungen` gehören
nicht zur Protokollform (beim Konto bleibt das abgeleitete `ist_kategorie`
Teil der Form; es ändert sich nie). Das Umbenennen eines Tags oder
Empfängers ändert deshalb keine Buchung.

## 3. Datenobjekte

### 3.1 Änderung (`Aenderung`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | fortlaufend in Entstehungsreihenfolge |
| `zeitpunkt` | date-time | App-Uhr (`synchronisation.md` 8), ohne Sekundenbruchteile |
| `quelle` | `"manuell"` \| `"import"` \| `"sync"` \| `"regeln"` \| `"umbuchung"` \| `"rueckgaengig"` | siehe 4 |
| `aktion` | str | fester Code der Operation (Tabelle 4) |
| `beschreibung` | str | deutsch, nicht leer (Inhalt nicht getestet) |
| `gruppe` | str \| null | Gruppenschlüssel (5) oder null |
| `eintraege` | Liste `AenderungEintrag` | mindestens 1; sortiert nach (`objekt` in der Reihenfolge von 2, `objekt_id`) |
| `rueckgaengig_von` | Liste int | nur bei `quelle = "rueckgaengig"`: die durch sie rückgängig gemachten Änderungen, aufsteigend; sonst `[]` |
| `rueckgaengig_durch` | int \| null | die *wirksame* Rückgängig-Änderung, die diese Änderung in `rueckgaengig_von` führt; sonst null (6.5) |

Eine Änderung heißt **wirksam**, wenn `rueckgaengig_durch = null` ist.

### 3.2 Eintrag (`AenderungEintrag`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `objekt` | `"konto"` \| `"empfaenger"` \| `"tag"` \| `"buchung"` \| `"regel"` \| `"verdacht"` \| `"abstimmung"` | |
| `objekt_id` | int | |
| `art` | `"angelegt"` \| `"geaendert"` \| `"geloescht"` | |
| `vorher` | Protokollform \| null | null genau bei `angelegt` |
| `nachher` | Protokollform \| null | null genau bei `geloescht` |

**Nettowirkung:** Die Einträge beschreiben den Unterschied zwischen dem
Buchbestand unmittelbar vor und unmittelbar nach der Operation. Für jedes
Objekt, dessen Protokollform sich unterscheidet (oder das neu existiert bzw.
nicht mehr existiert), gibt es genau einen Eintrag; für alle anderen keinen.
Ein Objekt, das innerhalb derselben Operation angelegt und wieder gelöscht
wurde, erscheint nicht. Bei `geaendert` gilt `vorher ≠ nachher`.

## 4. Was protokolliert wird

**Grundregel (T 3.5):** Jede Operation, die den Buchbestand verändert,
erzeugt genau dann eine Änderung, wenn sich mindestens eine Protokollform
tatsächlich ändert. Operationen ohne Wirkung (Fehlerantwort, Probelauf
`trocken`, Setzen bereits gesetzter Werte, zweiter Import derselben Datei,
Abruf ohne neue Umsätze) erzeugen **keine** Änderung. Gemerkte Kennungen
entstehen nur zusammen mit einer neuen Buchung oder einer neuen
Herkunftskennung an einer vorhandenen Buchung; sie gehören zu der Änderung,
die diese Buchung enthält.

### 4.1 Manuelle Operationen (`quelle = "manuell"`, `gruppe = null`)

Je erfolgreicher Anfrage höchstens eine Änderung:

| Operation | `aktion` |
| --- | --- |
| `POST /api/konten` | `konto_anlegen` |
| `PATCH /api/konten/{id}` | `konto_aendern` |
| `DELETE /api/konten/{id}` | `konto_loeschen` |
| `POST /api/konten/{id}/loeschen` (ohne `trocken`) | `konto_loeschen_mit_buchungen` (`loeschen.md` 3.8) |
| `POST /api/buchungen` | `buchung_anlegen` |
| `POST /api/buchungen/erfassen` | `buchung_erfassen` |
| `PATCH /api/buchungen/{id}` | `buchung_aendern` |
| `DELETE /api/buchungen/{id}` | `buchung_loeschen` |
| `PUT /api/buchungen/{id}/splits` | `splits_ersetzen` |
| `PUT /api/buchungen/{id}/kategorie` | `kategorie_setzen` |
| `POST /api/buchungen/mehrfach/kategorie` | `mehrfach_kategorie` |
| `POST /api/buchungen/mehrfach/tags` | `mehrfach_tags` |
| `POST /api/buchungen/mehrfach/aendern` (M12, `datenmodell.md` 17.2) | `mehrfach_aendern` |
| `POST /api/buchungen/mehrfach/loeschen` (M15, `datenmodell.md` 18.1) | `mehrfach_loeschen` |
| `POST /api/buchungen/mehrfach/verschieben` (M15, `datenmodell.md` 18.2; nur mit Wirkung) | `mehrfach_verschieben` |
| `POST /api/buchungen/{id}/vorschlag` | `vorschlag_entscheiden` |
| `POST /api/buchungen/mehrfach/vorschlag` | `mehrfach_vorschlag` |
| `POST /api/tags`, `PATCH /api/tags/{id}`, `DELETE /api/tags/{id}` | `tag_anlegen`, `tag_umbenennen`, `tag_loeschen` |
| `POST /api/empfaenger`, `PATCH /api/empfaenger/{id}`, `DELETE /api/empfaenger/{id}` | `empfaenger_anlegen`, `empfaenger_aendern`, `empfaenger_loeschen` |
| `POST /api/empfaenger/{id}/zusammenfuehren` | `empfaenger_zusammenfuehren` |
| `POST /api/dubletten/{id}/aufloesen` | `dublette_aufloesen` |
| `POST /api/regeln`, `PATCH /api/regeln/{id}`, `DELETE /api/regeln/{id}` | `regel_anlegen`, `regel_aendern`, `regel_loeschen` |
| `POST /api/abstimmungen` (ohne `trocken`, abgestimmt) | `abstimmung_anlegen` |
| `DELETE /api/abstimmungen/{id}` | `abstimmung_aufheben` |
| `POST /api/umbuchungen/zusammenfuehren` | `umbuchung_zusammenfuehren` |

Nebenwirkungen gehören in dieselbe Änderung, z. B. beim Löschen eines Tags
die Einträge aller Buchungen, deren `tag_ids` sich ändern; beim Löschen einer
Regel die Buchungen, deren `vorschlag.regel_id` auf null gesetzt wird; beim
Löschen einer Buchung die entfernten offenen Dublettenverdachte; ein beim
Ablehnen eines Vorschlags neu angelegtes Konto „Unkategorisiert“.

### 4.2 Automatische und angestoßene Operationen

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| KMyMoney-Import (REST und `importiere_kmy`), erfolgreich | `import` | `import_kmymoney` | `"import:<import_id>"` |
| Synchronisation: Konten, die beim Zuordnen angelegt werden (`synchronisation.md` 3), zusammen; dazu die beim Wiederherstellen vergessenen Kennungen (`synchronisation.md` 16.2) | `sync` | `sync_kontozuordnung` | `"sync:<lauf_id>"` |
| Synchronisation: Verarbeitung eines Bankkontos (4.2–4.4, inkl. Empfänger, „Unkategorisiert“, Regel- und Standardkategorie-Vorschläge, Verdachte, gemerkte Kennungen) | `sync` | `sync_konto` | `"sync:<lauf_id>"` |
| automatische Umbuchungserkennung nach der Verarbeitung eines Bankkontos (`buchhaltungspflege.md` 4.4) | `umbuchung` | `umbuchung_erkennen` | `"sync:<lauf_id>"` |
| Ausgleichsbuchung nach dem Saldoabgleich eines Bankkontos (M11, `kontostand.md` 2.2) | `sync` | `sync_saldoausgleich` | `"sync:<lauf_id>"` |
| `POST /api/umbuchungen/erkennen` | `umbuchung` | `umbuchung_erkennen` | null |
| `POST /api/regeln/anwenden` | `regeln` | `regeln_anwenden` | null |
| Rückgängig (6) | `rueckgaengig` | `rueckgaengig` | null |

- Das gilt für manuell (`POST /api/sync`), durch den Planer und nach einer
  TAN-Antwort fortgesetzte Läufe gleichermaßen. Je verarbeitetem Bankkonto
  entsteht höchstens eine Änderung `sync_konto` (in der Reihenfolge der
  Verarbeitung), danach ggf. eine `umbuchung_erkennen`. Fehlgeschlagene
  Konten schreiben nichts und erzeugen keine Änderung.
- Werden alle neuen Umsätze eines Kontos mit vorhandenen Buchungen
  zusammengeführt, besteht `sync_konto` aus den Einträgen dieser Buchungen
  (geänderte `extern_ids`).

## 5. Gruppen

Änderungen mit gleichem `gruppe`-Wert bilden eine Gruppe, z. B. alle
Änderungen eines Synchronisationslaufs (`"sync:<lauf_id>"`) oder eines
Imports (`"import:<import_id>"`). Gruppen können als Ganzes rückgängig
gemacht werden (6.3).

## 6. Rückgängig

### 6.1 Einzelne Änderung

`POST /api/aenderungen/{id}/rueckgaengig` (ohne Körper):

1. Unbekannte ID → 404 `nicht_gefunden`.
2. Nicht wirksam → 409 `bereits_rueckgaengig`.
3. **Zustandsprüfung:** Für jeden Eintrag muss die aktuelle Protokollform
   des Objekts gleich `nachher` sein (bei `geloescht`: das Objekt existiert
   nicht). Sonst → 409 `rueckgaengig_konflikt` (eine spätere, wirksame
   Änderung hat dasselbe Objekt verändert).
4. **Anwenden:** Jedes Objekt erhält wieder exakt die Protokollform
   `vorher` (bei `angelegt`: es wird entfernt; bei `geloescht`: es wird mit
   derselben ID und allen Feldern wiederhergestellt, ebenso Splits mit ihren
   IDs). Gemerkte Kennungen, die die Änderung hinzugefügt hat, werden
   wieder vergessen (ein späterer Abruf bucht diese Umsätze erneut); bei
   einer Rückgängig-Änderung, die das wiederholt, werden sie wieder
   gemerkt. Umgekehrt werden Kennungen, die die Änderung vergessen hat
   (`synchronisation.md` 16.2), wieder gemerkt.
5. **Bezugsprüfung** auf dem Ergebnis: Splits verweisen nur auf vorhandene
   Konten, `empfaenger_id`, `tag_ids`, `eltern_id` (ohne Zyklus),
   Regel-Bezüge (`kategorie_id`, Bedingungen `konto_id`),
   `vorschlag.regel_id`, `Empfaenger.standardkategorie_id`,
   `Abstimmung.konto_id` und `Split.abstimmung_id` nur auf vorhandene
   Objekte; offene Dublettenverdachte nur auf vorhandene Buchungen;
   Eindeutigkeit von IBAN, Empfängername, Alias (`ekey`) und Tag-Name
   (`casefold`). Verletzt → 409 `rueckgaengig_konflikt`, nichts wird
   geändert.
6. Erfolg: Es entsteht eine neue Änderung `U` mit `quelle = aktion =
   "rueckgaengig"`, `gruppe = null`, `rueckgaengig_von = [id]` und den
   Einträgen der Nettowirkung (vorher/nachher vertauscht). Antwort 200 mit
   `U`.

Status- und Sperrregeln (`datenmodell.md` 3.1, `buchhaltungspflege.md` 5.4)
gelten für Rückgängig nicht: Es stellt den protokollierten Zustand wieder
her, auch wenn eine Buchung dabei z. B. von `abgeglichen` auf `bestaetigt`
zurückgeht. Geschützt bleibt sie dadurch, dass jede spätere Änderung an ihr
die Zustandsprüfung scheitern lässt.

### 6.2 Mehrere Änderungen oder eine Gruppe

`POST /api/aenderungen/rueckgaengig` mit genau einem der Felder
`{"aenderung_ids": [int, …]}` (1–1000, ohne Doppelte) oder
`{"gruppe": "<schlüssel>"}`:

- Unbekannte `aenderung_ids` → 422 `referenz_unbekannt` mit
  `details.aenderung_ids`; eine davon nicht wirksam → 409
  `bereits_rueckgaengig` mit `details.aenderung_ids`. Beide oder keines der
  Felder → 422 `validierung`.
- `gruppe`: Menge = alle *wirksamen* Änderungen dieser Gruppe. Gibt es keine
  Änderung mit diesem Schlüssel → 422 `referenz_unbekannt`; sind alle
  bereits rückgängig gemacht → 409 `bereits_rueckgaengig`.
- Die Änderungen der Menge werden nach `id` **absteigend** nacheinander wie
  in 6.1 Schritt 3–4 behandelt (jede gegen den Zwischenstand nach den
  vorigen); die Bezugsprüfung (Schritt 5) erfolgt einmal am Ende. Scheitert
  irgendein Schritt → 409 `rueckgaengig_konflikt`, nichts wird geändert.
- Erfolg: **eine** neue Änderung `U` mit `rueckgaengig_von` = alle
  behandelten IDs (aufsteigend) und den Einträgen der Nettowirkung über alle
  Schritte. 200 mit `U`.

### 6.2a Rückgängig bis zu einer Änderung (M15)

`POST /api/aenderungen/rueckgaengig` mit `{"bis_id": <int>}` als drittem,
gleichrangigem Feld neben `aenderung_ids` und `gruppe`. Genau eines der
drei Felder ist anzugeben, sonst 422 `validierung`; `bis_id` kein `int`
(auch `null`, Zeichenkette, Gleitkommazahl, Boolean) → 422 `validierung`.

1. Unbekannte `bis_id` → 404 `nicht_gefunden` (nach der Validierung).
2. **Wirkung:** Der Buchbestand ist danach genau so wie unmittelbar vor der
   Änderung `bis_id`; die Änderung `bis_id` selbst wird mit zurückgenommen.
3. **Menge:** Von der neuesten Änderung abwärts wird jede Änderung
   `k ≥ bis_id` zurückgenommen, die im jeweiligen Zwischenstand wirksam ist
   (6.5). Wird dabei eine Rückgängig-Änderung zurückgenommen, wirken ihre
   Ziele wieder: Ziele `≥ bis_id` werden danach (weiter abwärts) ebenfalls
   zurückgenommen, ältere Ziele bleiben wiederhergestellt.
4. **Ausführung** wie 6.2: absteigend, jede gegen den Zwischenstand
   (Zustandsprüfung 6.1 Schritt 3–4), Bezugsprüfung einmal am Ende, atomar.
   Konflikt → 409 `rueckgaengig_konflikt`, nichts ändert sich (über die
   REST-Schnittstelle nicht herbeizuführen, E-182). Ist nichts
   zurückzunehmen → 409 `bereits_rueckgaengig`; das ist genau dann der Fall,
   wenn die Nettowirkung leer ist, der Buchbestand also schon dem Stand vor
   `bis_id` entspricht (z. B. ein zweites „bis“ auf dieselbe Änderung). Es
   entsteht keine Änderung (4, 3.1: mindestens ein Eintrag; E-190).
5. **Erfolg:** genau eine neue Änderung `U` (`quelle = aktion =
   "rueckgaengig"`, `gruppe = null`). `rueckgaengig_von` enthält alle
   zurückgenommenen IDs aufsteigend, auch sich aufhebende Paare (eine
   Änderung und ihr späteres Rückgängig). Die Einträge sind die
   Nettowirkung (3.2). Antwort 200 mit `U`.
6. **Wirksamkeit** nach 6.5: Alle zurückgenommenen Änderungen haben
   `rueckgaengig_durch = U`. Wird `U` rückgängig gemacht (Wiederholen, 6.3),
   ist der Stand vor `U` wieder hergestellt, und die Wirksamkeit aller
   beteiligten Änderungen ist wieder wie vorher.

Beispiel: Änderungen 1–5, dann `U6` = bis 3 (`rueckgaengig_von = [3, 4,
5]`), dann 7. Bis 4: 7 wird zurückgenommen, dann `U6` (3, 4, 5 wirken
wieder), dann 5 und 4; `rueckgaengig_von = [4, 5, 6, 7]`, Stand = nach 3,
und 3 ist wieder wirksam.

### 6.3 Wiederholen (Rückgängig einer Rückgängig-Änderung)

Eine Änderung mit `quelle = "rueckgaengig"` kann selbst rückgängig gemacht
werden (6.1); das stellt den Zustand vor dem Rückgängig wieder her
(„Wiederholen“). Für `rueckgaengig_durch` gilt dabei 6.5.

### 6.4 Rückgängig und Synchronisation

- Wird ein Konto entfernt, weil eine `sync_kontozuordnung` rückgängig
  gemacht wird, entfällt auch sein Eintrag in `/api/sync/konten`; ein
  späterer Lauf beginnt für diese IBAN wie beim ersten Abruf. Ausnahme: Hat
  diese Zuordnung ein gelöschtes Bankkonto wiederhergestellt
  (`synchronisation.md` 16.2 Regel 3), bleibt der Eintrag und hat danach
  den Status `konto_fehlt` (ohne gespeicherte Entscheidung). Sonst bleiben
  Läufe und `/api/sync/konten` unverändert; insbesondere entfällt kein
  Eintrag, nur weil sein Konto (aus anderem Grund) nicht mehr existiert.
- Beispiel: `{"gruppe": "sync:7"}` nimmt einen ganzen Lauf zurück. Danach
  ist der Buchbestand exakt wie vor dem Lauf; ein erneuter Abruf desselben
  Zeitraums (mit `von`) übernimmt dieselben Umsätze wieder.

### 6.5 Wirksamkeit

`rueckgaengig_durch(A)` ist die ID der Änderung `U` mit `A ∈
U.rueckgaengig_von` und `U` wirksam; gibt es keine, ist es null. (Es gibt
höchstens eine.) Beispiel: `U` macht `A` rückgängig → `A.rueckgaengig_durch
= U`. `R` macht `U` rückgängig → `U.rueckgaengig_durch = R`,
`A.rueckgaengig_durch = null` (A wirkt wieder und kann erneut rückgängig
gemacht werden).

## 7. Lesen

- `GET /api/aenderungen` → `Aenderungsseite {eintraege, gesamt, seite,
  pro_seite}`, **nach `id` absteigend** (neueste zuerst). Filter
  (UND-verknüpft): `quelle` (mehrfach, ODER), `aktion`, `gruppe`, `objekt`
  und `objekt_id` (Änderungen mit einem Eintrag zu genau diesem Objekt;
  `objekt_id` ohne `objekt` → 422), `wirksam` (true/false). Paginierung wie
  die Buchungsliste (`seite` ≥ 1, `pro_seite` 1–500, Vorgabe 50).
- `GET /api/aenderungen/{id}` → `Aenderung`; 404.

## 8. Invarianten (zusätzlich zu `datenmodell.md` 3)

1. Für jede Änderung `A` ohne spätere wirksame Änderung an denselben
   Objekten gilt: Rückgängig von `A` und danach Rückgängig dieser
   Rückgängig-Änderung führen zurück zum Zustand nach `A`.
2. Wird eine Folge von Operationen in umgekehrter Reihenfolge rückgängig
   gemacht, ist der Buchbestand nach jedem Schritt exakt der Zustand vor der
   jeweiligen Operation (T 3.6), bezogen auf alle Lese-Endpunkte des
   Buchbestands (Konten, Kontenübersicht, Buchungen, Empfänger, Tags,
   Regeln, Dubletten, Abstimmungen).
3. Die globalen Invarianten T 3.1–3.4 gelten auch nach jedem Rückgängig.

## 9. Meilenstein 4: Ergänzungen

Alles in 1–8 gilt unverändert; ohne Vorlagen bleibt die Menge der Objekte
dieselbe (E-029, E-077).

### 9.1 Neues Objekt `vorlage`

| `objekt` | Protokollform | Ableitung aus REST |
| --- | --- | --- |
| `vorlage` | Schema `Vorlage` (alle Felder einschließlich des abgeleiteten `gesamtbetrag`, das sich nur mit `teile` ändert) | `GET /api/vorlagen/{id}` |

Sortierung der Einträge (3.1): `vorlage` folgt in der Reihenfolge der Objekte
nach `abstimmung`. Bezugsprüfung (6.1 Schritt 5) zusätzlich: Teil-
`kategorie_id` und Bedingungen `konto_id` von Vorlagen verweisen nur auf
vorhandene Konten. Das Lernmodell hat keinen eigenen Zustand
(`lernmodell.md` 1) und erscheint nie im Protokoll.

### 9.2 Neue Quellen und Aktionen

`Aenderung.quelle` hat zusätzlich die Werte `"lernmodell"` und `"vorlage"`.

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/vorlagen` | `manuell` | `vorlage_anlegen` | null |
| `PATCH /api/vorlagen/{id}` | `manuell` | `vorlage_aendern` | null |
| `DELETE /api/vorlagen/{id}` | `manuell` | `vorlage_loeschen` | null |
| `POST /api/vorlagen/anwenden` | `vorlage` | `vorlagen_anwenden` | null |
| `POST /api/lernmodell/anwenden` | `lernmodell` | `lernmodell_anwenden` | null |
| GnuCash-Import (REST und `importiere_gnucash`), erfolgreich | `import` | `import_gnucash` | `"import:<import_id>"` |

- Synchronisation: Aufteilen nach Vorlagen, Abweichungen und
  Lernmodell-Vorschläge gehören zur Änderung `sync_konto` des Kontos
  (4.2); es entsteht keine eigene Änderung.
- `erfassen` mit Lernmodell-Vorschlag: eine Änderung `buchung_erfassen` wie
  bisher.
- `POST /api/konten/{id}/loeschen`: geänderte und gelöschte Vorlagen gehören
  zur Änderung `konto_loeschen_mit_buchungen`.
- Probeläufe (`trocken`), Vorhersagen (`POST /api/lernmodell/vorhersage`)
  und Operationen ohne Wirkung erzeugen keine Änderung (4).

## 10. Meilenstein 9: Ergänzungen (Datensicherung)

Alles in 1–9 gilt unverändert (E-029). Fachliche Regeln: `sicherung.md`.

### 10.1 Neue Quelle und Aktion

`Aenderung.quelle` hat zusätzlich den Wert `"sicherung"`.

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/sicherung/einspielen` (ohne `trocken`, nicht identisch) | `sicherung` | `sicherung_einspielen` | null |

- Einträge: Nettowirkung nach 3.2 über den gesamten Buchbestand
  (`sicherung.md` 5.2). Identischer Inhalt, Probelauf und Fehler erzeugen
  keine Änderung (4).
- `GET /api/sicherung` erzeugt nie eine Änderung.
- Das Änderungsprotokoll ist nie Teil einer Sicherung und wird durch das
  Einspielen nicht ersetzt; es erhält nur die neue Änderung.

### 10.2 Rückgängig

Rückgängig und Wiederholen einer Änderung `sicherung_einspielen` folgen 6.1
bis 6.5. Abweichend von 6.4 werden dabei auch die gemerkten Kennungen und
der Zustand je Bankkonto (`/api/sync/konten`, inkl. gespeicherter
Entscheidungen) auf den Stand vor bzw. nach dem Einspielen gesetzt
(`sicherung.md` 6). Läufe, Importvorgänge und Benachrichtigungen bleiben
unverändert.

## 11. Meilenstein 5: Ergänzungen (Kredite)

Alles in 1–10 gilt unverändert; ohne Kredite bleibt die Menge der Objekte
dieselbe (E-029, E-109). Wiederkehrende Buchungen, Berichte und Export haben
keinen Zustand und erscheinen nie im Protokoll; Benachrichtigungen ebenfalls
nicht (1).

### 11.1 Neues Objekt `kredit`

| `objekt` | Protokollform | Ableitung aus REST |
| --- | --- | --- |
| `kredit` | Schema `Kredit` (alle Felder einschließlich `zuordnungen` und `abgleiche`) | `GET /api/kredite/{id}` |

Sortierung der Einträge (3.1): `kredit` folgt nach `vorlage`. Bezugsprüfung
(6.1 Schritt 5) zusätzlich nach `kredite.md` 2.3: Konten jedes Kredits
existieren, `buchung_id` in `zuordnungen` und (≠ null) in `abgleiche`
existiert, `konto_id` ist über alle Kredite eindeutig.

### 11.2 Neue Quelle und Aktionen

`Aenderung.quelle` hat zusätzlich den Wert `"kredit"`.

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/kredite` (inkl. Anfangsbuchung) | `manuell` | `kredit_anlegen` | null |
| `PATCH /api/kredite/{id}` | `manuell` | `kredit_aendern` | null |
| `DELETE /api/kredite/{id}` | `manuell` | `kredit_loeschen` | null |
| `POST /api/kredite/{id}/zuordnen` (ohne `trocken`, mit Wirkung) | `kredit` | `kredit_zuordnen` | null |
| `POST /api/kredite/{id}/jahresabgleich` (ohne `trocken`) | `manuell` | `kredit_jahresabgleich` | null |

- Synchronisation: das Aufteilen einer Rate (Buchung angelegt, Kredit
  geändert) gehört zur Änderung `sync_konto` des Kontos (4.2).
- Nebenwirkungen (4.1): Wird eine zugeordnete Buchung gelöscht
  (`buchung_loeschen`, `dublette_aufloesen`, `konto_loeschen_mit_buchungen`),
  enthält dieselbe Änderung den geänderten Kredit.
- `POST /api/kredite/tilgungsplan`, `GET …/plan`, Probeläufe und
  Operationen ohne Wirkung erzeugen keine Änderung (4).
- Rückgängig eines Jahresabgleichs stellt Status, Korrekturbuchung und
  Kredit exakt wieder her (6.1); die Sperre abgeglichener Buchungen gilt
  dafür nicht.

## 12. Meilenstein 6: Ergänzungen (Postfächer)

Alles in 1–11 gilt unverändert; ohne Postfächer bleibt die Menge der
Objekte dieselbe (E-029, E-118).

### 12.1 Neues Objekt `postfach`

| `objekt` | Protokollform | Ableitung aus REST |
| --- | --- | --- |
| `postfach` | Schema `Postfach` (alle Felder) | `GET /api/mail/postfaecher/{id}` |

Sortierung der Einträge (3.1): `postfach` folgt nach `kredit`.
Bezugsprüfung (6.1 Schritt 5) zusätzlich: `adresse` ist nach `casefold()`
über alle Postfächer eindeutig.

### 12.2 Aktionen

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/mail/postfaecher` | `manuell` | `postfach_anlegen` | null |
| `PATCH /api/mail/postfaecher/{id}` (mit Wirkung) | `manuell` | `postfach_aendern` | null |
| `DELETE /api/mail/postfaecher/{id}` | `manuell` | `postfach_loeschen` | null |

- **Nicht** protokolliert (kein Buchbestand, 1): Anmeldung und Abmelden,
  Abruf und gespiegelte Nachrichten, `PostfachStatus`, Geheimnisse
  (`PUT`/`DELETE /api/geheimnisse/…`), Zustellung von Benachrichtigungen,
  TAN-Erinnerungen, die PIN-Quelle. Der FinTS-Abruf erzeugt dieselben
  Änderungen wie der des Mock-Plugins (4.2).
- Rückgängig von `postfach_loeschen` stellt das Postfach mit derselben `id`
  wieder her; Tokens und Spiegel kommen nicht zurück (Status `fehlt`).
  Rückgängig von `postfach_anlegen` entfernt das Postfach mit Betriebszustand,
  Tokens und Spiegel.

## 13. Meilenstein 7: Ergänzungen (Anmeldung und Betrieb)

M7 bringt **keine** neue Operation mit Wirkung auf den Buchbestand und
deshalb keine neue Aktion, Quelle oder Objektart (E-135). Nicht
protokolliert werden: Anmelden, Abmelden, Einrichten, Passwort ändern und
setzen, Fehlversuche und Sperren, Sitzungsablauf, Gesundheitsprüfung,
zeitgesteuerte Sicherungen (`sichere_in_verzeichnis` liest nur) und das
Beenden der App. Ein beim Beenden abgebrochener Lauf (`betrieb.md` 5.2)
erzeugt für die vollständig verarbeiteten Konten dieselben Änderungen wie
ohne Abbruch (4.2), für die übrigen keine. Eine mit 401, 403, 413 oder 429
abgelehnte Anfrage erzeugt keine Änderung.

## 14. Meilenstein 15: Ergänzungen (Sammelpaket Bedienung)

Alles in 1–13 gilt unverändert (E-029, E-181). M15 bringt keine neue
Objektart und keine neue Quelle.

- Neue Aktionen (4.1, beide `quelle = "manuell"`, `gruppe = null`):
  `mehrfach_loeschen` (`datenmodell.md` 18.1) und `mehrfach_verschieben`
  (`datenmodell.md` 18.2). Nebenwirkungen des Löschens (entfernte offene
  Dublettenverdachte, geänderte Kredite) gehören in dieselbe Änderung.
  Ein Verschieben ohne Wirkung (leere Auswahl) erzeugt keine Änderung (4).
- Rückgängig bis zu einer Änderung: 6.2a.
- Die Zuordnung eines unbekannten Bankkontos (`synchronisation.md` 20)
  läuft über `PATCH`/`POST /api/konten` (`konto_aendern`,
  `konto_anlegen`); übersprungene Bankkonten, ihre Benachrichtigungen und
  `GET /api/konten/{id}/herkunft` erzeugen keine Änderung.

## 15. Meilenstein 18: Ergänzungen (Dokumente)

Alles in 1–14 gilt unverändert; ohne Dokumente bleiben Objekte und
Protokollformen dieselben wie in M17 (E-029, E-206). Regeln im Einzelnen:
`dokumente.md` 3.

### 15.1 Neues Objekt `dokument`, Erweiterung von `buchung`

| `objekt` | Protokollform | Ableitung aus REST |
| --- | --- | --- |
| `dokument` | `{id, dateiname, mime_typ, groesse, sha256, quelle, erstellt_am}` (Schema `DokumentZustand`) | `GET /api/dokumente/{id}` ohne `buchung_ids` |
| `buchung` | wie 2, zusätzlich `dokument_ids` (aufsteigend) **nur**, wenn die Buchung mindestens ein Dokument hat | IDs aus `belege` |

Sortierung der Einträge (3.1): `dokument` folgt nach `postfach`. Inhalte
(Bytes) sind nie Teil des Protokolls.

### 15.2 Aktionen (`quelle = "manuell"`, `gruppe = null`)

| Operation | `aktion` | Einträge |
| --- | --- | --- |
| `POST /api/dokumente` | `dokument_anhaengen` | `dokument` angelegt; jede Ziel-Buchung geändert |
| `POST /api/dokumente/aus-mail` | `dokument_aus_mail` | wie `dokument_anhaengen` |
| `POST /api/dokumente/{id}/buchungen` (mit Wirkung) | `dokument_verknuepfen` | neu verknüpfte Buchungen geändert |
| `DELETE /api/dokumente/{id}/buchungen/{buchung_id}` | `dokument_loesen` | Buchung geändert; bei der letzten Verknüpfung zusätzlich `dokument` gelöscht |
| `PATCH /api/dokumente/{id}` (mit Wirkung) | `dokument_umbenennen` | `dokument` geändert |
| `DELETE /api/dokumente/{id}` | `dokument_loeschen` | `dokument` gelöscht; alle verknüpften Buchungen geändert |

- Bestehende Operationen, die Buchungen löschen (einzeln, mehrfach, Konto mit
  Buchungen, Dublette, Einspielen …), entfernen Dokumente ohne weitere
  Buchung in **derselben** Änderung (Eintrag `dokument` gelöscht).
- Rückgängig stellt Dokumente mit derselben ID, alle Verknüpfungen und den
  Inhalt wieder her; zusätzlich 409 `rueckgaengig_konflikt`, wenn ein zu
  entfernendes Dokument inzwischen an einer Buchung hängt, die nicht Teil der
  rückgängig zu machenden Änderung ist. Bezugsprüfung (6.1 Schritt 5)
  zusätzlich: jede Verknüpfung zeigt auf ein vorhandenes Dokument und eine
  vorhandene Buchung; jedes Dokument hat seinen Inhalt.

## 16. Meilenstein 19: Ergänzungen (ALF-BanCo-Import, Kategorien zusammenführen)

Keine neue Objektart und keine neue Quelle (E-211). Regeln: `alfbanco.md` 6.

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| ALF-BanCo-Import (REST und `importiere_alfbanco`), erfolgreich und mit Wirkung | `import` | `import_alfbanco` | `"import:<import_id>"` |
| `POST /api/kategorien/zusammenfuehren` (ohne `trocken`, mit Wirkung) | `manuell` | `kategorien_zusammenfuehren` | null |
| `POST /api/kategorien/verschieben` (mit Wirkung, D-326) | `manuell` | `kategorien_verschieben` | null |

- Ein Import ohne Wirkung (alles vorhanden) erzeugt einen Importvorgang, aber
  keine Änderung (4).
- Rückgängig des Imports (auch über `gruppe`) und des Zusammenführens stellt
  den Zustand vorher exakt her (`alfbanco.md` 6); baut eine spätere Änderung
  darauf auf, gilt 6.1.

## 17. Meilenstein 20: Ergänzungen (Mail-Abgleich)

Alles in 1–16 gilt unverändert; ohne Erwartungen bleiben Objekte und
Protokollformen dieselben (E-029, E-216). Regeln: `erwartungen.md` 4.1, 5, 6,
12.

### 17.1 Neues Objekt `erwartung`, neue Quelle `mail`

| `objekt` | Protokollform | Ableitung aus REST |
| --- | --- | --- |
| `erwartung` | Schema `ErwartungZustand` (`erwartungen.md` 12) | `GET /api/erwartungen` ohne abgeleitete Felder |

Sortierung der Einträge (3.1): `erwartung` folgt nach `dokument`. Neue
Quelle `mail` (3.1).

### 17.2 Aktionen

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| Abgleich: Erkennen und automatisch Zuordnen (nach Abruf, Lauf, Planer-Takt, `POST /api/erwartungen/abgleich`), nur mit Wirkung | `mail` | `erwartung_erkennen` | null |
| `POST /api/erwartungen` | `manuell` | `erwartung_anlegen` | null |
| `PATCH /api/erwartungen/{id}` (mit Wirkung) | `manuell` | `erwartung_aendern` | null |
| `DELETE /api/erwartungen/{id}` | `manuell` | `erwartung_loeschen` | null |
| `POST /api/erwartungen/{id}/zustand` (mit Wirkung) | `manuell` | `erwartung_zustand` | null |
| `POST /api/erwartungen/{id}/buchungen` (mit Wirkung) | `manuell` | `erwartung_zuordnen` | null |
| `DELETE /api/erwartungen/{id}/buchungen/{buchung_id}` | `manuell` | `erwartung_loesen` | null |

- Beim Zuordnen angelegte Dokumente und Verknüpfungen gehören in dieselbe
  Änderung. Benachrichtigungen und gespiegelte Mails sind nie Teil einer
  Änderung.
- Verwaiste Bezüge (gelöschte Buchungen bzw. Dokumente) entfallen aus
  `buchung_ids` bzw. `dokument_ids` in derselben Änderung wie die Löschung
  (`erwartungen.md` 5.3).

## 18. Meilenstein 23: Schutz der Geheimnisse, gemerkte PIN, App-Passwörter

Schutz der Geheimnisse (Ein-/Ausschalten, Entsperren, Sperren), gemerkte PIN und
App-Passwörter der Postfächer sind **Betriebszustand** wie Geheimnisse (12): keine
Änderung im Protokoll, kein Rückgängig (`geheimnisschutz.md` 3). Neue Aktionen gibt
es nicht; Objekte und Protokollformen bleiben unverändert.

## 19. Meilenstein 24: Kategorie bei Erstattungen

Neue Aktionen gibt es nicht. Wird einer Erstattung (`grund = rueckerstattung`) eine
Buchung neu zugeordnet und dabei deren Split von „Unkategorisiert“ auf die Kategorie der
ursprünglichen Buchung umgebucht (`erwartungen.md` 13.2), gehört die Umbuchung zur
**selben Änderung** wie die Zuordnung (`erwartung_zuordnen`, Quelle `manuell`, bzw.
`erwartung_erkennen`, Quelle `mail`); die Buchung erscheint dort mit Vorher/Nachher.
Rückgängig stellt Zuordnung und Split wieder her. Serieneinträge der Liste
(`erwartungen.md` 13.1) sind abgeleitet und erzeugen nie eine Änderung.

## 20. Meilenstein 25: Betragsfilter je Empfänger

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `PUT /api/empfaenger/{id}/wiederkehrend` (mit Wirkung) | `manuell` | `wiederkehrend_filter_setzen` | null |
| `DELETE /api/empfaenger/{id}/wiederkehrend` | `manuell` | `wiederkehrend_filter_setzen` | null |

Die Protokollform eines Empfängers (Schema `EmpfaengerZustand`) enthält das Feld
`wiederkehrend` `{modus, toleranz_prozent, mindestbetrag}` nur bei eigener Einstellung
(`wiederkehrend.md` 9.4, `sicherung.md` 10); Formen ohne Einstellung bleiben gleich. Löschen und
Zusammenführen nehmen die Einstellung der Quelle in derselben Änderung mit. Die Vorgabe
der Instanz ist Betriebszustand (kein Protokoll).

## 21. Meilenstein 27: Dubletten anlegen, Tags an Empfängern (`sammel.md` 2, 4)

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/dubletten` | `manuell` | `dublette_anlegen` | null |

`dublette_anlegen` („Dublettenverdacht angelegt“) hat genau einen Eintrag Objekt `verdacht`, Art
`angelegt`. Rückgängig entfernt den Verdacht; ist er inzwischen aufgelöst, → 409
`rueckgaengig_konflikt` (6).

Tags an Empfängern (`PATCH /api/empfaenger/{id}` mit `tag_ids`) laufen über die bestehenden Aktionen
`empfaenger_aendern`, `empfaenger_zusammenfuehren` (Ziel erhält die Vereinigung der Tags) und
`tag_loeschen` (entfernt den Tag in derselben Änderung auch von allen Empfängern), Quelle `manuell`, keine
Gruppe. Die Protokollform des Empfängers (`Empfaenger` bzw. `EmpfaengerZustand`) trägt `tags` (`TagKurz`
nach `name`, `id`) **nur**, wenn er Tags hat; Formen ohne Tags bleiben gleich. Rückgängig und Wiederholen
stellen die Tags her. Rückgängig des Anlegens eines Tags, den inzwischen ein Empfänger außerhalb dieser
Änderung trägt → 409 `rueckgaengig_konflikt`. Das Feld `verdacht` (`sammel.md` 1) ist abgeleitet und
erscheint nie im Protokoll; Dublettenvorschläge (`sammel.md` 4.2) erzeugen nie eine Änderung.

## 22. Meilenstein 30: Regeln mit Ausdruck und Tags (`kategorisierung.md` 8)

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/regeln/reihenfolge` (mit Wirkung) | `manuell` | `regeln_reihenfolge` | null |
| `POST /api/regeln/{id}/anwenden` (mit Wirkung) | `regeln` | `regeln_anwenden` | null |

- Anlegen, Ändern und Löschen von Regeln sind Änderungen wie bisher
  (`regel_anlegen`, `regel_aendern`, `regel_loeschen`).
- `regeln_reihenfolge` hat je Regel, deren Priorität sich ändert, einen
  Eintrag Objekt `regel`, Art `geaendert`. Ändert sich keine Priorität,
  entsteht keine Änderung (4, Grundregel).
- `POST /api/regeln/{id}/anwenden` ist genau eine Änderung, wenn sich etwas
  ändert; Rückgängig nimmt Kategorievorschläge und vergebene Tags zurück.
  Dasselbe gilt für Tags aus `POST /api/regeln/anwenden` und aus der
  Synchronisation (Teil der jeweiligen Änderung).
- **Protokollform der Regel:** wie die REST-Darstellung, aber **ohne**
  `ausdruck` und `ausdruck_form`, und mit `tag_ids` **nur**, wenn die Regel
  Tags hat. `kategorie_id` darf null sein. Formen von Regeln ohne Tags
  bleiben damit wie vor M30.
- Das Löschen eines Tags, den Regeln vergeben, ändert diese Regeln in
  derselben Änderung (`tag_loeschen`); Rückgängig stellt Tag und Zuordnung
  wieder her.
- Rückgängig einer Tag-Anlage scheitert (409 `rueckgaengig_konflikt`),
  solange eine Regel den Tag vergibt, die nicht zum selben Schritt gehört
  (Bezugsprüfung 6.1 Schritt 5: `tag_ids` der Regeln nur auf vorhandene
  Tags).
- Prüfen, Sprache, `als-regel`, Test, Erklären und der Filter der
  Buchungsliste sind Lesezugriffe und erzeugen nie eine Änderung.

## 23. Meilenstein 31: Automatische Regeln, Lerndaten, Bestellnummer-Mails

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| automatische Regeln nach einer Änderung (`lernmodell.md` 9.2) | `lernmodell` | `regel_automatisch` | frei |
| `POST /api/mock/lerndaten` | `import` | `mock_lerndaten` | null |
| Mails über die Bestellnummer anhängen (`erwartungen.md` 14.3) | `mail` | `bestellmail_anhaengen` | null |

- Protokollform der Regel (22) zusätzlich mit `automatisch: true` und
  `empfaenger_id` bei automatischen Regeln; Protokollform des Empfängers mit
  `lernregel_gesperrt: true` nur bei gesperrten (`lernmodell.md` 9.4).
- Das Löschen einer automatischen Regel ändert in derselben Änderung
  (`regel_loeschen`) den Empfänger (Sperre).
- `PUT /api/lernmodell/einstellungen`, die Erklärung und die Übersicht des
  Lernmodells, alle Berichte und das Gemerkte der Bestellnummer-Mails
  erzeugen keine Änderung.

## 24. Meilenstein 32 (Definition 4)

| Vorgang | Quelle | Aktion | Gruppe |
| --- | --- | --- | --- |
| Mail von Hand zuordnen (`POST /api/mail/nachrichten/{id}/buchung`, `sammel3.md` 8.2) | `manuell` | `dokument_aus_mail` | null |
| Bereinigen gleichnamiger Konten im Altbestand (`sammel3.md` 1.3) | `manuell` | `kategorien_zusammenfuehren` | null |
| Umwandeln der Standardkategorien beim Start (`sammel3.md` 2.1) | `manuell` | `regel_anlegen` | null |
| Umbenennen der Personen-Tags beim Start (`sammel3.md` 5) | `manuell` | `tag_umbenennen` | null |

Rückgängig kann mit 409 `konto_existiert` abgelehnt werden (`sammel3.md`
1.2). Fortsetzung und Wegfall geplanter Zahlungen stehen in der auslösenden
Änderung (`sammel3.md` 14.5). Die Protokollform der Erwartung trägt
`wiederholung` nur bei Erwartungen mit Wiederholung.

## 25. Feature `regelgruppen` (D-295, `kategorisierung.md` 8.10)

| Operation | `quelle` | `aktion` | `gruppe` |
| --- | --- | --- | --- |
| `POST /api/regeln/{id}/uebernehmen` | `manuell` | `regel_uebernehmen` | null |

- Einträge: Objekt `regel`, Art `geaendert` (Vermerk `automatisch` und
  `empfaenger_id` entfallen, neue `prioritaet`), dazu Objekt `empfaenger`,
  Art `geaendert` (`lernregel_gesperrt`), wenn der Empfänger noch nicht
  gesperrt war.
- Beschreibung: „Regel „<Name>“ als eigene übernommen“.

## 26. Kurzes Änderungsprotokoll (D-302, `sicherungspunkte.md` 6)

- Der stündliche Lauf entfernt Änderungen, die älter als `protokoll_stunden` (Vorgabe 1) Stunden sind und deren
  Stand ein geprüfter Sicherungspunkt abdeckt. Rückgängig-Paare werden nur zusammen entfernt. Rückgängig,
  „Bis hierher“ und `gruppe` wirken nur auf die verbliebenen Änderungen.
- Die Herkunft angelegter Buchungen (`import:<id>`, `sync:<id>`) bleibt in `buchung_herkunft`; `GET
  /api/konten/{id}/herkunft` und das Verschieben nach Gruppe (`buchhaltungspflege.md`) lesen beides.
- `GET /api/aenderungen` liefert zusätzlich `gekuerzt_bis`.
- Beleginhalte ohne Dokument, ohne Verweis aus dem Mail-Spiegel und ohne verbliebenen Protokolleintrag entfallen beim
  Kürzen.

## 27. Kontotyp und Kontoinhaber (D-312, `datenmodell.md` 21)

- Die Protokollform eines Kontos (= REST-Darstellung) enthält `inhaber` nur, wenn das Konto einen Inhaber hat. Eine
  Typänderung erscheint als geänderter Wert `art`. Aktion wie bisher `konto_aendern` (Quelle `manuell`).
- Rückgängig stellt Typ und Inhaber her, auch nach dem Löschen eines Kontos mit Inhaber.
