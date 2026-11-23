# Buchhaltungspflege – Meilenstein 3

Verbindlich für Implementierung und Tests. Umsetzung von K 14
(Empfängerverwaltung, manuelle Buchungen, Umbuchungserkennung,
Kontenabstimmung, Volltextsuche) und T 11, T 13, T 14. Das
Änderungsprotokoll steht in `protokoll.md`; jede hier beschriebene
Operation wird dort protokolliert. Ergänzt `datenmodell.md` (Abschnitt 13),
`synchronisation.md` (Abschnitt 14), `kategorisierung.md` (Abschnitt 6),
`python-api.md` (Abschnitt 9) und `openapi.yaml` (Tags `empfaenger`,
`buchungen`, `umbuchungen`, `abstimmungen`, `suche`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Alle Erweiterungen sind rückwärtskompatibel (E-029): Ohne Aliase,
Standardkategorien und Abstimmungen und mit der Vorgabe
`umbuchung_automatisch = False` verhält sich die Anwendung exakt wie nach M2.

## 1. Neue Felder und Begriffe

### 1.1 Buchung

| Feld | Typ | Regeln |
| --- | --- | --- |
| `gegen_iban` | str \| null | IBAN der Gegenpartei, nur von der Synchronisation gesetzt (14.1): `gegenpartei_iban` normalisiert (Leerzeichen entfernt, Großbuchstaben), wenn gültig (`datenmodell.md` 2), sonst null. Manuell, per Import und per `erfassen` angelegte Buchungen: null. Über REST nicht änderbar. |
| `ist_umbuchung` | bool | abgeleitet: alle Splits liegen auf Bestandskonten und auf mindestens zwei verschiedenen Konten |
| `abgestimmt` | bool | abgeleitet: mindestens ein Split hat `abstimmung_id ≠ null` (5) |

### 1.2 Split

| Feld | Typ | Regeln |
| --- | --- | --- |
| `abstimmung_id` | int \| null | Abstimmung, mit der dieser Split abgestimmt wurde (5); neue Splits: null |

### 1.3 Gesperrte Buchung

Eine Buchung ist **gesperrt**, wenn ihr Status `abgeglichen` ist **oder**
sie `abgestimmt` ist. Überall, wo M1 und M2 für abgeglichene Buchungen 409
`buchung_gesperrt` vorsehen oder sie übergehen, gilt das ab M3 für alle
gesperrten Buchungen (Details in 5.4).

### 1.4 Technische Konten

| Name | Art | `extern_id` | Verwendung |
| --- | --- | --- | --- |
| „Unkategorisiert“ | eigenkapital | `kontor:unkategorisiert` | wie M2 (`synchronisation.md` 4.2); zusätzlich Gegenkonto von `erfassen` ohne Kategorie (3) |
| „Korrekturen“ | eigenkapital | `kontor:korrektur` | Gegenkonto von `erfassen` mit `art = "korrektur"` ohne Kategorie (3) |

Beide: Wurzelkonto, `iban = null`, `geschlossen = false`, `eroeffnet_am =
null`, `notiz = ""`; beim ersten Bedarf angelegt (in derselben Änderung),
danach über die `extern_id` wiederverwendet, auch wenn umbenannt.

## 2. Empfängerverwaltung (K 14, T 14)

### 2.1 Felder

Das Schema `Empfaenger` erhält (im Schema optional, ab M3 in jeder Antwort
vorhanden):

| Feld | Typ | Regeln |
| --- | --- | --- |
| `aliase` | Liste str | weitere Schreibweisen desselben Empfängers; aufsteigend sortiert (Zeichenkettenordnung); anfangs `[]` |
| `standardkategorie_id` | int \| null | Konto der Art `aufwand` oder `ertrag`; anfangs null |

**Alias-Schlüssel:** Ein Name oder Alias `x` *passt* zu einem Alias `a`,
wenn `ekey(x) = ekey(a)` (`datenmodell.md` 1) und nicht leer ist.

Regeln für `aliase` (beim Anlegen und Ändern):

- Jeder Eintrag wird mit `strip()` bereinigt; danach 1–200 Zeichen und
  `ekey` nicht leer, sonst 422 `validierung`. Höchstens 100 Einträge.
- Einträge mit gleichem `ekey` innerhalb der Liste werden zu einem
  zusammengefasst (der erste in Eingabereihenfolge bleibt).
- Hat ein Alias denselben `ekey` wie ein Alias eines **anderen** Empfängers →
  409 `alias_existiert` (`details.alias`, `details.empfaenger_id`), nichts
  wird geändert. Gleicher `ekey` wie der eigene Name ist erlaubt.

### 2.2 Anlegen, Ändern, Löschen

- `POST /api/empfaenger` mit `{name, aliase?, standardkategorie_id?}`
  (Vorgaben `[]`, null). 409 `empfaenger_existiert` wie M1; 409
  `alias_existiert`; 422 `kategorie_ungueltig` (Standardkategorie unbekannt
  oder keine Art `aufwand`/`ertrag`).
- `PATCH /api/empfaenger/{id}` mit beliebigen dieser Felder; nur angegebene
  werden geändert, `aliase` ersetzt die Liste. Name eindeutig wie M1 (409
  `empfaenger_existiert`; eigener Name ist kein Konflikt). 404, 409, 422 wie
  oben. Das Umbenennen ändert keine Buchung (Zuordnung über `id`).
- `DELETE /api/empfaenger/{id}`: nur, wenn keine Buchung auf ihn verweist,
  sonst 409 `empfaenger_in_verwendung`; 204; 404.
- Ein Konto, das Standardkategorie eines Empfängers ist, kann nicht gelöscht
  werden (409 `konto_in_verwendung`, Erweiterung von `datenmodell.md` 2).
  Ausnahme: `POST /api/konten/{id}/loeschen` passt die Standardkategorie an
  (`loeschen.md` 3.5).

### 2.3 Zuordnung eines Namens zu einem Empfänger

Wo ein Empfänger über einen Namen `n` (nach `strip()`, nicht leer) bestimmt
wird – Synchronisation (`gegenpartei_name`, 14.1), `erfassen` mit
`empfaenger_name` (3) –, gilt diese Reihenfolge:

1. Empfänger mit exakt dem Namen `n` (wie M2).
2. Sonst der Empfänger, zu dessen Alias `n` passt (2.1; wegen der
   Eindeutigkeit höchstens einer).
3. Sonst wird ein Empfänger mit Namen `n` angelegt (`extern_id = null`,
   `aliase = []`, `standardkategorie_id = null`).

**KMyMoney-Import** (Erweiterung von `datenmodell.md` 10.3): Für ein
`PAYEE` gilt nach Regel 1 (`extern_id`) und Regel 2 (exakter Name) als
Regel 3: Empfänger, zu dessen Alias `PAYEE@name` passt. Ein so zugeordneter
Empfänger zählt in `empfaenger_vorhanden` und wird nicht verändert; die
Buchungen der Datei verweisen auf ihn. Keine zusätzliche Warnung.

### 2.4 Zusammenführen

`POST /api/empfaenger/{ziel_id}/zusammenfuehren` mit
`{"quelle_ids": [int, …]}` (1–100, ohne Doppelte):

1. Ziel unbekannt → 404. Ziel in `quelle_ids` → 422 `validierung`.
   Unbekannte Quellen → 422 `referenz_unbekannt` mit
   `details.empfaenger_ids` (aufsteigend).
2. Alle Buchungen mit `empfaenger_id` ∈ `quelle_ids` erhalten `empfaenger_id
   = ziel_id` – **auch gesperrte** (Stammdatenpflege, E-049); sonst ändert
   sich an ihnen nichts.
3. Neue Aliase des Ziels = bisherige Aliase des Ziels, dann je Quelle (nach
   `id` aufsteigend) deren Name und deren Aliase. Dabei entfällt jeder
   Kandidat, dessen `ekey` leer ist, gleich dem `ekey` des Zielnamens ist,
   bereits unter den neuen Aliasen vorkommt oder Alias eines dritten
   Empfängers (weder Ziel noch Quelle) ist. Ergebnis sortiert wie 2.1.
4. Die Quellen werden gelöscht. Name, `extern_id` und
   `standardkategorie_id` des Ziels bleiben unverändert.
5. Atomar, eine Änderung `empfaenger_zusammenfuehren`. Antwort 200 mit dem
   Ziel.

Danach greifen die Namen der Quellen als Aliase bei künftigen Abrufen und
Importen (T 14: „Zusammenführen zweier Empfänger ordnet alle Buchungen um,
Aliase greifen bei neuen Importen“).

### 2.5 Standardkategorie (Stufe zwischen Regel und Lernmodell; entfällt ab M32, `sammel3.md` 2.1)

- **Synchronisation:** Greift für einen neuen Umsatz keine Regel und hat
  der zugeordnete Empfänger (2.3) eine `standardkategorie_id`, wird das
  Gegenkonto diese Kategorie, und die Buchung erhält `vorschlag =
  {kategorie_id, regel_id: null, quelle: "standardkategorie",
  vorher_konto_id: <„Unkategorisiert“>}` („Unkategorisiert“ wird dafür
  angelegt, falls nötig). Sie zählt in `buchungen_kategorisiert`. Regeln
  haben immer Vorrang (K 7, M4 setzt das Lernmodell nach dieser Stufe).
- **Erfassen** (3): ohne `kategorie_id` gilt dasselbe.
- Für Vorschläge mit `quelle = "standardkategorie"` gelten Annehmen,
  Ablehnen und alle Erledigungsregeln aus `kategorisierung.md` 5
  unverändert.
- Vorhandene Buchungen werden durch das Setzen einer Standardkategorie
  nicht verändert; `POST /api/regeln/anwenden` wertet nur Regeln aus.

## 3. Manuelle Buchungen: Erfassungshilfe (K 14, T 14)

`POST /api/buchungen` (M1, vollständige Splits) bleibt unverändert und
dient z. B. für Splitbuchungen. Für häufige Fälle gibt es die vereinfachte
Erfassung `POST /api/buchungen/erfassen`:

| Feld | Typ | Pflicht | Regeln |
| --- | --- | --- | --- |
| `art` | `"ausgabe"` \| `"einnahme"` \| `"umbuchung"` \| `"korrektur"` | ja | |
| `datum` | date | ja | |
| `konto_id` | int | ja | Bestandskonto |
| `betrag` | int (Cent) | ja | `ausgabe`, `einnahme`, `umbuchung`: > 0; `korrektur`: ≠ 0 (vorzeichenbehaftete Saldoänderung von `konto_id`); Bereich wie `datenmodell.md` 1 |
| `kategorie_id` | int \| null | nein | nur `ausgabe`, `einnahme`, `korrektur`; Konto der Art `aufwand` oder `ertrag` |
| `gegenkonto_id` | int | bei `umbuchung` | nur `umbuchung`; Bestandskonto ≠ `konto_id` |
| `empfaenger_id` | int \| null | nein | nicht zusammen mit `empfaenger_name` |
| `empfaenger_name` | str | nein | 1–200 Zeichen nach `strip()`; Zuordnung nach 2.3 (legt ggf. an) |
| `verwendungszweck` | str | nein (`""`) | max. 10 000 Zeichen |
| `memo` | str | nein (`""`) | max. 10 000 Zeichen; wird in **jeden** Split geschrieben |
| `tag_ids` | Liste int | nein (`[]`) | wie `BuchungNeu` |
| `status` | `importiert` \| `vorlaeufig` \| `bestaetigt` | nein (`bestaetigt`) | |

Splits (in dieser Reihenfolge), `B` = `betrag`, `K` = `konto_id`, `G` =
Gegenkonto:

| `art` | Splits | Gegenkonto `G` |
| --- | --- | --- |
| `ausgabe` | `K: −B`, `G: +B` | `kategorie_id`; sonst Standardkategorie des Empfängers (2.5, als Vorschlag); sonst „Unkategorisiert“ |
| `einnahme` | `K: +B`, `G: −B` | wie `ausgabe` |
| `umbuchung` | `K: −B`, `gegenkonto_id: +B` | – |
| `korrektur` | `K: +B`, `G: −B` | `kategorie_id`; sonst „Korrekturen“ |

Weitere Felder: `extern_ids = []`, `gegen_iban = null`, `vorschlag` nur im
Fall der Standardkategorie. Antwort 201 `Buchung`; Änderung
`buchung_erfassen` (inkl. eines dabei angelegten Empfängers oder
technischen Kontos). Regeln werden nicht ausgewertet (wie M2 für manuelle
Buchungen).

Fehler (Prüfreihenfolge): 422 `validierung` (Schema, Betrag ≤ 0 bzw. = 0,
Feld bei unpassender `art`, fehlendes `gegenkonto_id`, beide
Empfängerfelder); 422 `referenz_unbekannt` (Konto, Gegenkonto, Empfänger,
Tag unbekannt); 422 `konto_ungueltig` (`konto_id` oder `gegenkonto_id` kein
Bestandskonto oder beide gleich); 422 `kategorie_ungueltig` (Kategorie
unbekannt oder keine Art `aufwand`/`ertrag`, wie M1 „Kategorie setzen“).

Manuell erfasste Buchungen unterliegen denselben Invarianten und Regeln wie
importierte (T 14): Sie lassen sich ändern, kategorisieren, splitten,
taggen, abstimmen, löschen und rückgängig machen.

## 4. Umbuchungen (K 14, T 11)

### 4.1 Kandidaten

Eine Buchung ist ein **Umbuchungskandidat**, wenn

- sie genau zwei Splits hat: einen auf einem Bestandskonto (*Bankseite*,
  Konto `k`, Betrag `x ≠ 0`) und einen auf dem technischen Konto
  „Unkategorisiert“ (also ohne Kategorie und ohne offenen Vorschlag),
- und sie nicht gesperrt ist (1.3).

Typisch ist das eine Seite eines Transfers, die die Synchronisation ohne
Regeltreffer übernommen hat.

### 4.2 Passendes Paar

Zwei verschiedene Kandidaten `X` (Konto `k_X`, Betrag `x`, IBAN `i_X` =
IBAN von `k_X`) und `Y` (analog) **passen**, wenn

1. `k_X ≠ k_Y`,
2. `x = −y`,
3. `|X.datum − Y.datum| ≤ umbuchung_fenster_tage` (Konfiguration, Vorgabe
   3, `python-api.md` 9),
4. **passende eigene IBAN:** `X.gegen_iban` ist null oder gleich `i_Y`, und
   `Y.gegen_iban` ist null oder gleich `i_X`, und mindestens eine der beiden
   Seiten trifft zu, d. h. `X.gegen_iban = i_Y ≠ null` oder `Y.gegen_iban =
   i_X ≠ null`.

Damit wird ein gleicher Betrag an eine fremde IBAN nie als Umbuchung erkannt
(T 11): Bei einer Seite mit fremder `gegen_iban` ist Bedingung 4 verletzt.

### 4.3 Erkennung (eindeutige Paare)

Sei `C` die Menge aller Kandidaten und `P(X) = {Y ∈ C : X, Y passen}`. Ein
Paar `{X, Y}` ist **eindeutig**, wenn `P(X) = {Y}` und `P(Y) = {X}`. Nur
eindeutige Paare werden automatisch zusammengeführt; mehrdeutige bleiben
unverändert (sie können mit 4.6 von Hand zusammengeführt werden). Die
Bewertung erfolgt vollständig vor dem Anwenden, das Ergebnis hängt nicht
von der Reihenfolge ab.

**Zusammenführen** eines Paars `{X, Y}` mit `X.id < Y.id`:

- `X` bleibt bestehen; `Y` wird gelöscht.
- `X.splits` = [Bankseite von `X` (unveränderte `id`, `konto_id`, `betrag`,
  `memo`), Bankseite von `Y` (unveränderte `id`, `konto_id`, `betrag`,
  `memo`)]; die beiden Splits auf „Unkategorisiert“ entfallen.
- `X.extern_ids` = Vereinigung beider (sortiert), `X.tag_ids` = Vereinigung
  beider. `datum`, `empfaenger_id`, `verwendungszweck`, `status`,
  `gegen_iban` von `X` bleiben; `vorschlag` ist null.
- Offene Dublettenverdachte, in denen `Y` vorkommt, werden gelöscht (wie
  beim Löschen einer Buchung).
- Danach ist `X.ist_umbuchung = true` und `X.kategorie_id = null`. Die
  Buchung bucht auf kein Aufwands- oder Ertragskonto (T 11: „weder als
  Einnahme noch als Ausgabe“; Berichte in M5 werten `ist_umbuchung` aus).
  Alle Kontensalden bleiben unverändert (die beiden entfallenden Splits auf
  „Unkategorisiert“ heben sich auf); „Unkategorisiert“ verliert zwei
  Buchungen.

### 4.4 Automatische Erkennung bei der Synchronisation

Nur wenn `umbuchung_automatisch = True` (Vorgabe False, `python-api.md` 9):
Nach jeder Verarbeitung eines Bankkontos mit mindestens einer neuen Buchung
werden die eindeutigen Paare von `C` bestimmt (4.3, über alle Kandidaten
des Buchs, auch aus früheren Läufen) und diejenigen zusammengeführt, die
mindestens eine in dieser Verarbeitung neu angelegte Buchung enthalten. Eine
eigene Änderung `umbuchung_erkennen` (`quelle = "umbuchung"`, gleiche Gruppe
wie der Lauf, `protokoll.md` 4.2). Damit wird eine Seite, die zunächst
allein vorliegt, beim Eintreffen der zweiten Seite nachträglich
zusammengeführt (T 11). `SyncKonto`-Zählungen bleiben unverändert (sie
zählen die Umsätze vor dem Zusammenführen).

### 4.5 Erkennung auf Wunsch

`POST /api/umbuchungen/erkennen` mit `{trocken: bool = false}` führt alle
eindeutigen Paare von `C` zusammen (unabhängig von
`umbuchung_automatisch`). Antwort 200 `UmbuchungErkennung = {trocken,
anzahl, paare: [{behalten_id, entfernt_id}]}` nach `behalten_id`
aufsteigend; eine Änderung `umbuchung_erkennen` (`gruppe = null`), wenn
nicht `trocken` und `anzahl > 0`.

### 4.6 Von Hand zusammenführen

`POST /api/umbuchungen/zusammenfuehren` mit `{"buchung_ids": [a, b]}`
(genau zwei verschiedene IDs):

- 422 `validierung` (Form); 422 `referenz_unbekannt`
  (`details.buchung_ids`); 409 `buchung_gesperrt` (`details.buchung_ids`);
  422 `keine_umbuchung`, wenn eine der beiden kein Kandidat ist (4.1) oder
  Bedingung 1 oder 2 aus 4.2 verletzt ist. Zeitfenster und IBAN werden hier
  **nicht** verlangt.
- Sonst Zusammenführen wie in 4.3; 200 mit der bleibenden Buchung; Änderung
  `umbuchung_zusammenfuehren`.

Getrennt wird eine Umbuchung durch Rückgängig der Änderung, die sie
zusammengeführt hat (`protokoll.md` 6). Ein abgelehntes Paar wird nicht
gemerkt.

## 5. Kontenabstimmung (K 14, T 13)

### 5.1 Abstimmung (`Abstimmung`)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | |
| `konto_id` | int | Bestandskonto |
| `stichtag` | date | |
| `saldo` | int | Auszugssaldo (Cent, Vorzeichen wie `datenmodell.md` 2) |
| `erstellt_am` | date-time | App-Uhr |

### 5.2 Abstimmen

`POST /api/abstimmungen` mit `{konto_id, stichtag, saldo, trocken: bool =
false}`:

1. 422 `validierung` (Schema); 422 `referenz_unbekannt` (Konto unbekannt);
   422 `konto_ungueltig` (kein Bestandskonto).
2. `berechneter_saldo` = `saldo(konto_id)` mit Stichtag (`datenmodell.md`
   2: Summe aller Splits auf genau diesem Konto, ohne Unterkonten, von
   Buchungen mit `datum ≤ stichtag`). `differenz = saldo −
   berechneter_saldo`.
3. *Zu markierende Splits* `M`: alle Splits auf `konto_id` mit
   `abstimmung_id = null`, deren Buchung `datum ≤ stichtag` hat.
4. Ist `differenz = 0` und nicht `trocken`: neue Abstimmung anlegen, alle
   Splits in `M` erhalten `abstimmung_id` = ihre ID. Eine Änderung
   `abstimmung_anlegen` (Abstimmung angelegt, betroffene Buchungen
   geändert). Auch mit leerem `M` entsteht die Abstimmung.
5. Sonst wird nichts geändert (T 13: „Bei Differenz wird die Differenz
   angezeigt und nichts markiert“).

Antwort immer 200 `AbstimmungErgebnis = {konto_id, stichtag, saldo,
berechneter_saldo, differenz, stimmt, abgestimmt, anzahl_splits,
abstimmung}` mit `stimmt = (differenz = 0)`, `abgestimmt` = ob in Schritt 4
markiert wurde, `anzahl_splits = |M|`, `abstimmung` = die neue Abstimmung
oder null.

Ein Stichtag vor einer früheren Abstimmung desselben Kontos ist erlaubt
(dann ist `M` meist leer).

### 5.3 Lesen und Aufheben

- `GET /api/abstimmungen` (optional `?konto_id=`), nach `id` aufsteigend;
  `GET /api/abstimmungen/{id}`; 404.
- `DELETE /api/abstimmungen/{id}`: nur für die **letzte** Abstimmung ihres
  Kontos (größter `stichtag`, bei Gleichstand größte `id`), sonst 409
  `abstimmung_nicht_letzte`. Alle Splits mit dieser `abstimmung_id` erhalten
  null; die Abstimmung wird gelöscht. 204; Änderung `abstimmung_aufheben`.

### 5.4 Schutz abgestimmter Buchungen

Abgestimmte Buchungen sind gesperrt (1.3). Im Einzelnen (Prüfreihenfolgen
der M1/M2-Endpunkte unverändert, „abgeglichen“ jeweils ersetzt durch
„gesperrt“):

| Operation | gesperrte Buchung |
| --- | --- |
| `PATCH` `datum`, `empfaenger_id`, `verwendungszweck` (tatsächliche Änderung, E-026) | 409 `buchung_gesperrt` |
| `PATCH` `tag_ids`, `status` | erlaubt (Statusregeln unverändert) |
| `DELETE`, `PUT …/splits`, `PUT …/kategorie` | 409 `buchung_gesperrt` |
| `mehrfach/kategorie` | 409 `buchung_gesperrt` (`details.buchung_ids`), atomar |
| `mehrfach/tags` | erlaubt |
| `mehrfach/aendern` (M12) | `status` erlaubt (Verlassen von `abgeglichen` nur mit `entsperren`), übrige Felder 409 `buchung_gesperrt` (`datenmodell.md` 17.3) |
| Vorschlag `ablehnen` (einzeln/mehrfach) | 409 `buchung_gesperrt` (mehrfach mit `details.buchung_ids`, nach `kein_vorschlag` geprüft) |
| Vorschlag `annehmen` | erlaubt |
| `POST /api/regeln/anwenden` | übergangen |
| Dublette `zusammenfuehren`, wenn `buchung_id` gesperrt | 409 `buchung_gesperrt` |
| Dublette `zusammenfuehren`, wenn `behalten_id` gesperrt | erlaubt (nur `extern_ids`) |
| Synchronisation: Zusammenführen mit vorhandener Buchung (`synchronisation.md` 4.4) | erlaubt (nur `extern_ids`) |
| Umbuchung | kein Kandidat; von Hand 409 |
| Empfänger zusammenführen | erlaubt (2.4) |
| Tag umbenennen/löschen | erlaubt |

### 5.5 Filter

`GET /api/buchungen?abgestimmt=true|false`: nur Buchungen mit bzw. ohne
`abgestimmt` (UND mit den übrigen Filtern).

## 6. Volltextsuche (K 14, T 14)

`GET /api/suche?q=<text>&limit=<n>`:

- `q`: 1–200 Zeichen; die *Wörter* sind `q.split()` (Python, Leerraum).
  Kein Wort → 422 `validierung`. `limit`: 1–500, Vorgabe 50.
- **Suchnormalisierung** `snorm(s)`: `unicodedata.normalize("NFC", s)`,
  dann `norm` (`datenmodell.md` 1: casefold, ä/ö/ü → ae/oe/ue), dann
  `unicodedata.normalize("NFKD", …)` und alle Zeichen der Kategorie `Mn`
  entfernen. Beispiele: „Bäckerei“, „BAECKEREI“ und „Bäckerei“ → `baeckerei`;
  „Café“ → `cafe`; „Straße“ → `strasse`. (Die M1-Freitextsuche
  `GET /api/buchungen?suche=` bleibt bei `norm`.)
- Ein Objekt ist ein **Treffer**, wenn für **jedes** Wort `w` gilt:
  `snorm(w)` ist Teilzeichenkette von `snorm(f)` für mindestens ein
  Suchfeld `f` des Objekts (verschiedene Wörter dürfen in verschiedenen
  Feldern treffen).

| Liste | Suchfelder | Reihenfolge |
| --- | --- | --- |
| `konten` (Schema `Konto`, alle Arten) | `name`, `iban` (falls vorhanden), `notiz` | `id` aufsteigend, vollständig |
| `empfaenger` (Schema `Empfaenger`) | `name`, jeder Alias | `id` aufsteigend, vollständig |
| `tags` (Schema `Tag`) | `name` | `id` aufsteigend, vollständig |
| `buchungen` (Schema `Buchung`, `betrag` = Umsatz) | Empfängername, `verwendungszweck`, jedes Split-`memo`, jeder Tag-Name, Name jedes Kontos, auf das ein Split bucht | `datum` absteigend, dann `id` absteigend; höchstens `limit` |

Antwort 200 `Suchergebnis = {q, konten, empfaenger, tags, buchungen,
buchungen_gesamt}` (`buchungen_gesamt` = Anzahl aller Buchungstreffer).

## 7. Konfiguration

Siehe `python-api.md` 9: `umbuchung_automatisch` (bool, Vorgabe False),
`umbuchung_fenster_tage` (int ≥ 0, Vorgabe 3).

## 8. REST-Endpunkte (Überblick; Schemas in `openapi.yaml`)

| Methode, Pfad | Zweck |
| --- | --- |
| `POST /api/empfaenger` (erweitert), `PATCH /api/empfaenger/{id}`, `DELETE /api/empfaenger/{id}` | Empfänger pflegen (2.2) |
| `POST /api/empfaenger/{id}/zusammenfuehren` | zusammenführen (2.4) |
| `POST /api/buchungen/erfassen` | manuelle Buchung (3) |
| `POST /api/umbuchungen/erkennen`, `POST /api/umbuchungen/zusammenfuehren` | Umbuchungen (4.5, 4.6) |
| `GET/POST /api/abstimmungen`, `GET/DELETE /api/abstimmungen/{id}` | Kontenabstimmung (5) |
| `GET /api/suche` | Volltextsuche (6) |
| `GET /api/aenderungen`, `GET /api/aenderungen/{id}`, `POST /api/aenderungen/{id}/rueckgaengig`, `POST /api/aenderungen/rueckgaengig` | Änderungsprotokoll (`protokoll.md`) |

Neue Fehlercodes: `alias_existiert`, `empfaenger_in_verwendung`,
`konto_ungueltig`, `keine_umbuchung`, `abstimmung_nicht_letzte`,
`bereits_rueckgaengig`, `rueckgaengig_konflikt`.

## 9. Meilenstein 4: Ergänzungen

- **Erfassen** (3): Für `ausgabe` und `einnahme` ohne `kategorie_id` gilt
  die Stufenfolge Standardkategorie → Lernmodell (nur bei
  `lernmodell_automatisch = True`, Vorschlag `quelle = "lernmodell"`,
  `lernmodell.md` 5.1) → „Unkategorisiert“. Merkmale: `empfaenger_name` bzw.
  Name zu `empfaenger_id`, `verwendungszweck`, Regelbetrag (`−betrag` bei
  `ausgabe`, `+betrag` bei `einnahme`). Split-Vorlagen werden beim Erfassen
  nicht angewendet.
- **Umbuchungskandidaten** (4.1): Buchungen mit Vorlagen-Aufteilung sind nie
  Kandidaten (mehr als zwei Splits). Ein Lernmodell-Vorschlag schließt eine
  Buchung wie jeder offene Vorschlag aus; deshalb befragt die
  Synchronisation das Lernmodell nicht für Umsätze mit eigener Gegen-IBAN
  (`lernmodell.md` 5.1).
- **Empfänger** (2): Aliase und Zusammenführen wirken auch beim
  GnuCash-Import (`gnucash.md` 6.2). Die Merkmale des Lernmodells nutzen den
  *aktuellen* Empfängernamen; Umbenennen und Zusammenführen ändern daher die
  Merkmale der betroffenen Trainingsbuchungen.

## 10. Meilenstein 11: Zusammenführen mit neuem Namen (ergänzt 2.4)

Auftrag des Anwenders vom 2026-11-09 (E-165): „Es können mehrere Empfänger
zusammengefasst werden. Dann erhält der neue Empfänger alle aufgenommenen als
Suchtexte, so dass eine Zuordnung bei neuen Buchungen gelingt.“ Das leistet
2.4 bereits (Namen und Aliase der Quellen werden Aliase des Ziels, 2.3
ordnet künftige Umsätze und Importe darüber zu). Ergänzt wird nur der neue
Name.

`POST /api/empfaenger/{ziel_id}/zusammenfuehren` akzeptiert zusätzlich
`name: str` (optional). Ablauf wie 2.4 mit diesen Ergänzungen:

1. `name` (Zeichenkette, nicht null) wird mit `strip()` bereinigt; 1–200 Zeichen, sonst 422
   `validierung`.
2. Nach den Prüfungen aus 2.4 Schritt 1: Trägt ein **dritter** Empfänger
   (weder Ziel noch Quelle) genau diesen Namen → 409 `empfaenger_existiert`,
   nichts wird geändert. Der Name einer Quelle oder der bisherige Name des
   Ziels ist erlaubt.
3. Die neuen Aliase werden wie 2.4 Schritt 3 gebildet, mit zwei
   Änderungen: Ist `name` angegeben und vom bisherigen Namen des Ziels
   verschieden, ist der bisherige Name des Ziels der erste Kandidat (vor den
   Quellen); „gleich dem `ekey` des Zielnamens“ bezieht sich auf den
   **neuen** Namen.
4. Das Ziel erhält `name` (ohne `name`: unverändert). Alles in derselben
   Änderung `empfaenger_zusammenfuehren`.

Ohne `name` ist das Verhalten exakt das aus 2.4 (M3-Tests unverändert). Die
Aliase bleiben exakte Schreibweisen (Vergleich über `ekey`); Teilwort-Suche
ist bewusst nicht vorgesehen (E-165).

## 11. Meilenstein 32: Standardkategorie entfällt, Empfänger-Endpunkte

Die Standardkategorie (2.5) und ihre Stufe beim Erfassen (3) entfallen;
`standardkategorie_id` ist immer `null`, andere Werte → 422
`kategorie_ungueltig`. Neu `GET /api/empfaenger/anzahlen` und
`GET /api/empfaenger/{id}/konten`. Einzelheiten: `sammel3.md` 2 (E-296, E-297).
