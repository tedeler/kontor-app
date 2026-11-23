# Wiederkehrende Buchungen – Meilenstein 5

Verbindlich für Implementierung und Tests. Umsetzung von K 9
(„Automatische Erkennung regelmäßiger Buchungen (Abos, Daueraufträge,
Lastschriften). Übersicht mit Empfänger, Rhythmus, Betrag und Jahreskosten.
Benachrichtigung bei unerwarteten Buchungen, z. B. neuer Empfänger,
geänderter Betrag oder ausbleibende Zahlung.“), T 10 und T 17 (Auslöser
unerwartete Buchung). Ergänzt `synchronisation.md` 17, `python-api.md` 12
und `openapi.yaml` (Tag `wiederkehrend`). Meilenstein 16 ersetzt die Kette
(2.2) und ergänzt die Begründung je Buchung (8).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Die Erkennung ist eine **Funktion des Buchbestands** ohne eigenen Zustand
(wie das Lernmodell, E-071, E-098): Sie wird bei jeder Abfrage aus den
Buchungen berechnet, erscheint nie im Änderungsprotokoll und nie in einer
Sicherung. Benachrichtigungen entstehen nur auf ausdrückliche Prüfung (4)
oder bei `wiederkehrend_automatisch = True` nach einem Synchronisationslauf
(5, Vorgabe aus, E-100). Ohne diese Prüfungen verhält sich die Anwendung
exakt wie nach M4 (E-029).

## 1. Begriffe

- `monat_plus(d, n)` wie `kredite.md` 1 (Tag auf das Monatsende begrenzt).
- **Toleranz** `T = 5` Tage (Wochenend- und Feiertagsverschiebung; die
  längste Verschiebung durch bundesweite Feiertage ist 4 Tage).
- **Rhythmen** (in dieser Prüfreihenfolge):

  | `rhythmus` | Monate `m` | Mindestanzahl | Zahlungen je Jahr |
  | --- | --- | --- | --- |
  | `monatlich` | 1 | 3 | 12 |
  | `vierteljaehrlich` | 3 | 3 | 4 |
  | `jaehrlich` | 12 | 2 | 1 |

## 2. Erkennung

### 2.1 Einträge und Gruppen

Für jede Buchung `b` mit Empfänger (`empfaenger ≠ null`) und jedes
Bestandskonto `k`, auf dem `b` Splits hat, ist `x = Σ` der Beträge dieser
Splits. Ist `x ≠ 0` und ist `k` nicht das Darlehenskonto (`konto_id`)
eines Kredits (`kredite.md`), entsteht ein **Eintrag** `(k, e, richtung,
datum, buchung_id, x)` mit `e = b.empfaenger.id` und `richtung =
"ausgabe"` für `x < 0`, sonst `"einnahme"`.

Eine **Gruppe** sind alle Einträge mit gleichem `(k, e, richtung)`, sortiert
nach (`datum`, `buchung_id`). Status, Kategorie, Tags und Herkunft der
Buchung spielen keine Rolle; eine Umbuchung zwischen zwei eigenen Konten
ergibt je Konto einen Eintrag.

### 2.2 Kette (ab M16, ersetzt die bisherige Regel; E-192)

Freigegebene Meilenstein-Definition M16 vom 2026-11-11, Abschnitt 1. Das
Verfahren ersetzt die bisherige Kette ohne Umschalter. Abstände sind ganze
Tage. Für eine Gruppe `e_1 … e_n` (sortiert nach `datum`, `buchung_id`) und
einen Rhythmus mit `m` Monaten entsteht die Kette so:

**2.2.1 Anker (jüngster Termin).** Anker-Kandidaten sind alle Einträge, die
höchstens `T` Tage vor dem jüngsten Eintrag der Gruppe liegen, einschließlich
des jüngsten Eintrags. Für jeden Kandidaten wird die Kette nach 2.2.2
gebildet. Ausgewählt wird

1. der Kandidat mit der längsten Kette, bei Gleichstand
2. der, dessen Betrag gleich dem Betrag seines Vorgängers in seiner Kette ist
   (gilt nicht für eine Kette mit nur einem Glied), bei Gleichstand
3. der jüngere (später nach `datum`, `buchung_id`).

Alle übrigen Anker-Kandidaten sind **zusätzliche Zahlungen** (E-193 Nr. 1).

**2.2.2 Rückwärts verketten.** Vom aktuellen Glied `c` (zu Beginn der Anker)
aus:

- **Vorgänger-Kandidaten** sind alle älteren Einträge `x` (vor `c` in der
  Gruppenfolge) mit `|c.datum − monat_plus(x.datum, m)| ≤ T`.
- Gibt es keinen Kandidaten, endet die Kette. Die Einträge unmittelbar vor
  `c`, die höchstens `T` Tage vor `c` liegen, sind zusätzliche Zahlungen. Der
  nächstältere Eintrag danach ist der „nächste ältere Eintrag“ der Begründung
  (8.4, Grund `abstand`). Gibt es keinen, gilt der Grund `kein_vorgaenger`.
- Sonst wird unter den Kandidaten ausgewählt: zuerst Betrag gleich
  `c.betrag`, dann die kleinste Abweichung `|c.datum − monat_plus(x.datum,
  m)|`, dann der jüngere Eintrag. Das ist der **Vorgänger** `p`.
- Für jeden Eintrag zwischen `p` und `c` in der Gruppenfolge gilt: Er ist eine
  zusätzliche Zahlung, wenn er höchstens `T` Tage von `c` oder von `p`
  entfernt ist oder wenn er im vorigen Schritt (Vorgänger-Suche für das Glied
  nach `c`) Vorgänger-Kandidat war. Ist mindestens ein Eintrag dazwischen
  keine zusätzliche Zahlung, endet die Kette bei `c` mit dem Grund
  `fremde_zahlung` (`p` wird nicht Glied; die übrigen Einträge dazwischen
  bleiben zusätzliche Zahlungen, E-193 Nr. 2).
- Sonst wird `p` Glied der Kette, und es geht mit `c = p` weiter.

**2.2.3 Folgen.**

- Die Glieder in zeitlicher Reihenfolge bilden die Kette. Zusätzliche
  Zahlungen zählen nicht zur Länge, nicht zur Mindestanzahl und stehen nicht
  in `buchung_ids`. Sie verändern `betrag`, `jahreskosten`, `letzte` und
  `naechste_faelligkeit` nicht.
- 2.3 (Rhythmus in Prüfreihenfolge, erster mit ausreichender Länge), 2.4 und
  3–5 gelten unverändert mit dieser Kette.
- Eine ausgelassene Zahlung (Abstand zum nächsten passenden Eintrag deutlich
  über `T`) beendet die Kette weiterhin. Regelmäßige Zahlungen in kürzerem
  Abstand, etwa wöchentlich, ergeben keine Monatsserie, weil die Einträge
  dazwischen mehr als `T` Tage von beiden Terminen entfernt sind.
- Beispiele (monatlich, jeweils −9,99 €, wenn nicht anders angegeben):
  - 15.01., 15.02., 13.03., 15.03. → Kette 15.01., 15.02., 15.03. (Anker
    15.03.: gleich lange Ketten, gleicher Betrag, jünger); 13.03. ist
    zusätzlich.
  - 15.01., 15.02., 15.03., dazu 01.03. → keine Serie (ab 15.03. ist 01.03.
    fremd, die Kette hat nur ein Glied).
  - 04.08., 04.09., 05.10., 04.11. mit −320,32 € und 04.11. mit −50,00 €
    (später angelegt) → Kette mit vier Gliedern zu −320,32 €; die Buchung zu
    −50,00 € ist zusätzlich.
  - 13.01. sowie 15.01., 15.02., 15.03. → Kette 15.01.–15.03.; 13.01. ist
    zusätzlich (am selben Termin wie das erste Glied).
  - 15.01., 15.02., 15.03. und 15.03. (doppelt) → Serie mit drei Gliedern
    (bis M15: keine Serie; E-194).

Bis M15 galt: `j = n`, solange `|e_j.datum − monat_plus(e_{j−1}.datum, m)| ≤
T`, wird `j` verringert; die Kette war `e_j … e_n`, und jede zusätzliche
Zahlung beendete sie.

### 2.3 Serie

Die Gruppe ist eine **Serie** mit dem ersten Rhythmus aus 1, dessen Kette
mindestens die Mindestanzahl erreicht; sonst ist sie keine Serie. Felder
(`WiederkehrendSerie`):

| Feld | Wert |
| --- | --- |
| `schluessel` | `"<k>:<e>:<richtung>"`, z. B. `"3:17:ausgabe"` |
| `konto_id` | `k` |
| `empfaenger` | `{id, name}` |
| `richtung` | `"ausgabe"` \| `"einnahme"` |
| `rhythmus` | `"monatlich"` \| `"vierteljaehrlich"` \| `"jaehrlich"` |
| `anzahl` | Länge der Kette (Zahl der Glieder) |
| `erste`, `letzte` | `datum` des ersten bzw. letzten Kettenglieds |
| `betrag` | `x` des letzten Kettenglieds (vorzeichenbehaftet, aktueller Betrag; das ist der Anker) |
| `jahreskosten` | `−betrag · 12 / m` (ganze Cent; Ausgaben positiv, Einnahmen negativ) |
| `naechste_faelligkeit` | `F = monat_plus(letzte, m)` |
| `status` | siehe 2.4 |
| `buchung_ids` | die Buchungen der Kette in Kettenreihenfolge |

### 2.4 Status am Stichtag `H`

Mit `F = naechste_faelligkeit` und `F2 = monat_plus(letzte, 2m)`:

- `aktiv`: `H ≤ F + T`,
- `ausbleibend`: `F + T < H ≤ F2 + T` (genau eine Zahlung fehlt),
- `beendet`: `H > F2 + T` (mindestens zwei Zahlungen fehlen; z. B.
  gekündigtes Abo oder alte Altdaten).

### 2.5 Übersicht

`GET /api/wiederkehrend?stichtag=<date>` (Vorgabe: *heute* der App-Uhr,
`synchronisation.md` 8): Erkennung über alle Buchungen mit `datum ≤
stichtag`. Antwort 200 `WiederkehrendUebersicht = {stichtag, serien,
summe_jahreskosten}`; `serien` nach (`konto_id`, `empfaenger.id`,
`richtung` mit `ausgabe` vor `einnahme`); `summe_jahreskosten` = Summe der
`jahreskosten` aller Serien mit `richtung = "ausgabe"` und `status ≠
"beendet"`. 422 `validierung` bei ungültigem Datum.

## 3. Ereignisse (unerwartete Buchungen)

Geprüft wird eine Buchung `b` mit ihren Einträgen (2.1, nach `konto_id`
aufsteigend):

1. **Neuer Empfänger** (`neuer_empfaenger`): `b` hat einen Eintrag mit
   `richtung = "ausgabe"`, und es gibt keine andere Buchung mit demselben
   Empfänger und kleinerem (`datum`, `id`). Schlüssel
   `"neuer_empfaenger:" + e`.
2. **Geänderter Betrag** (`wiederkehrend_betrag`): Für einen Eintrag
   `(k, e, r, x)` von `b` ist die Gruppe `(k, e, r)`, beschränkt auf die
   Einträge mit kleinerem (`datum`, `buchung_id`) als `b`, eine Serie `S`
   (2.3), `|b.datum − S.naechste_faelligkeit| ≤ T` (die Zahlung setzt die
   Serie fort) und `x ≠ S.betrag`. Schlüssel
   `"wiederkehrend_betrag:" + b.id` (je Buchung höchstens eines; maßgeblich
   ist der erste solche Eintrag nach `konto_id`).

Unabhängig von einzelnen Buchungen gilt am Stichtag `H`:

3. **Ausbleibende Zahlung** (`wiederkehrend_ausbleibend`): jede Serie der
   Übersicht am Stichtag `H` (2.5) mit `status = "ausbleibend"`. Schlüssel
   `"wiederkehrend_ausbleibend:" + schluessel + ":" + naechste_faelligkeit`
   (z. B. `wiederkehrend_ausbleibend:3:17:ausgabe:2024-07-03`).

Für Einnahmen gibt es kein Ereignis „neuer Empfänger“; für alle Serien
gelten 2 und 3.

## 4. Prüfung auf Wunsch

`POST /api/wiederkehrend/pruefen` mit `{buchung_ids: [int] = []}`:

1. 422 `validierung` (Schema, doppelte IDs, mehr als 10 000);
   422 `referenz_unbekannt` (`details.buchung_ids`, aufsteigend).
2. Ereignisse 1 und 2 für jede Buchung aus `buchung_ids` (nach `id`
   aufsteigend), danach Ereignis 3 am Stichtag *heute*.
3. Je Ereignis entsteht eine Benachrichtigung (6), **wenn es noch keine
   Benachrichtigung mit diesem Schlüssel gibt** – gelesen oder ungelesen
   (E-100: die Schlüssel bezeichnen ein einzelnes Ereignis; dasselbe
   Ereignis wird nie zweimal gemeldet).
4. Antwort 200 `WiederkehrendPruefung = {stichtag, benachrichtigungen}` mit
   den in diesem Aufruf neu entstandenen Benachrichtigungen in
   Entstehungsreihenfolge. Keine Änderung im Protokoll (Benachrichtigungen
   gehören nicht zum Buchbestand).

## 5. Automatische Prüfung bei der Synchronisation

Nur bei `wiederkehrend_automatisch = True` (`python-api.md` 12, Vorgabe
`False`): Wenn ein Lauf einen Endstatus erreicht (also nicht bei
`wartet_auf_tan`, wohl aber nach der Fortsetzung), wird wie in 4 geprüft
mit `buchung_ids` = alle in diesem Lauf neu angelegten, noch existierenden
Buchungen von Bankkonten, die **vor** dem Lauf schon einmal erfolgreich
abgerufen wurden (`letzter_erfolg_am ≠ null`, `synchronisation.md` 2.3).
Der Erstabruf eines Kontos meldet so nicht jeden Empfänger als „neu“.
Ereignis 3 wird nach jedem Lauf mit Endstatus geprüft. Fehlgeschlagene Läufe
und Läufe ohne neue Buchungen prüfen nur Ereignis 3.

## 6. Benachrichtigungen

| Feld | `neuer_empfaenger` | `wiederkehrend_betrag` | `wiederkehrend_ausbleibend` |
| --- | --- | --- | --- |
| `art` | `"neuer_empfaenger"` | `"wiederkehrend_betrag"` | `"wiederkehrend_ausbleibend"` |
| `schluessel` | 3.1 | 3.2 | 3.3 |
| `titel`, `text` | deutsch, nicht leer; nennt den Empfänger und den Betrag | nennt Empfänger, bisherigen und neuen Betrag | nennt Empfänger, Rhythmus und die fällige Zahlung |
| `link` | `"/buchungen/" + b.id` | `"/buchungen/" + b.id` | `"/wiederkehrend"` |

Benachrichtigungen gehören nicht zum Buchbestand und nicht zur Sicherung;
Rückgängig ändert sie nicht.

## 7. Konfiguration

`KontorConfig.wiederkehrend_automatisch: bool = False`
(`KONTOR_WIEDERKEHREND_AUTOMATISCH`), `python-api.md` 12. Für den Betrieb
wird `1` empfohlen.

## 8. Begründung je Buchung (Meilenstein 16)

Freigegebene Meilenstein-Definition vom 2026-11-11, Abschnitt 2 (E-192,
E-195). Neue Felder in bestehenden Antworten gibt es nicht;
`WiederkehrendSerie` bleibt unverändert.

### 8.1 `GET /api/buchungen/{buchung_id}/wiederkehrend`

- Query `stichtag` (Datum, optional, Vorgabe: *heute* wie `GET
  /api/wiederkehrend`). Ungültiges Datum oder unbekannter Parameter → 422
  `validierung`. Unbekannte Buchung → 404 `nicht_gefunden` (Reihenfolge,
  wenn beides zutrifft, nicht festgelegt; E-195 Nr. 1).
- Reiner Lesezugriff ohne Zustand und ohne Protokolleintrag. Grundlage sind
  dieselben Einträge (nur `datum ≤ stichtag`) und dieselbe Erkennung wie `GET
  /api/wiederkehrend` mit diesem Stichtag. Begründung und Übersicht stimmen
  also immer überein.
- Antwort 200 `WiederkehrendBegruendung`:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `buchung_id` | int | angefragte Buchung |
| `stichtag` | Datum | verwendeter Stichtag |
| `urteil` | `wiederkehrend` \| `zusaetzlich` \| `nicht_wiederkehrend` \| `ausgeschlossen` | Gesamturteil (8.5) |
| `text` | str | deutscher Satz zum Gesamturteil (Inhalt nicht Teil der Abnahme) |
| `eintraege` | Liste `BegruendungEintrag` | je Eintrag der Buchung (Konto und Richtung), sortiert nach `konto.id`, dann Ausgabe vor Einnahme |
| `ausgeschlossen` | Liste `{konto: {id, name}, grund, text}` | Bestandskonten der Buchung, die keinen Eintrag ergeben: `grund` = `darlehenskonto` oder `summe_null` (E-195 Nr. 3) |

### 8.2 `BegruendungEintrag`

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `konto` | `{id, name}` | Bestandskonto des Eintrags |
| `richtung` | `ausgabe` \| `einnahme` | |
| `datum`, `betrag` | Datum, int (Cent) | des Eintrags |
| `gruppe` | str | Beschriftung der Gruppe (Konto · Empfänger · Richtung), Text nicht Teil der Abnahme |
| `gruppe_anzahl` | int | Zahl der Einträge der Gruppe |
| `juengste` | `{buchung_id, datum, betrag}` | jüngster Eintrag der Gruppe |
| `urteil` | `glied` \| `zusaetzlich` \| `vor_beginn` \| `keine_serie` | Rolle dieses Eintrags (8.5) |
| `glied` | int \| null | Nummer in der Kette (1 = ältestes Glied), nur bei `glied` |
| `text` | str | deutscher Satz (Inhalt nicht Teil der Abnahme) |
| `serie` | `WiederkehrendSerie` \| null | die Serie der Gruppe wie in `GET /api/wiederkehrend`, sonst null |
| `rhythmen` | Liste `BegruendungRhythmus` | die geprüften Rhythmen in Prüfreihenfolge bis einschließlich des ersten erfüllten (ohne Serie alle drei) |
| `buchungen` | Liste `{buchung_id, datum, betrag, rolle, glied}` | alle Einträge der Gruppe, jüngste zuerst; `rolle` wie `urteil` oben, `glied` nur bei `rolle = glied` (sonst null) |

### 8.3 `BegruendungRhythmus` und `BegruendungSchritt`

`BegruendungRhythmus`: `rhythmus`, `monate` (1, 3, 12), `mindestanzahl`,
`laenge` (Zahl der Glieder der Kette nach 2.2), `erfuellt` (`laenge ≥
mindestanzahl`), `schritte` (Liste `BegruendungSchritt`, Kettenprotokoll vom
Anker rückwärts).

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `ergebnis` | `anker` \| `verbunden` \| `bruch` | |
| `grund` | `kein_vorgaenger` \| `abstand` \| `fremde_zahlung` \| null | nur bei `bruch` |
| `von` | `{buchung_id, datum, betrag}` | aktuelles Glied `c` (bei `anker`: der gewählte Anker) |
| `vorgaenger` | wie `von` \| null | `verbunden`: gewählter Vorgänger; `abstand`: nächster älterer Eintrag; `fremde_zahlung`: der ausgewählte Vorgänger; sonst null |
| `erwartet` | Datum \| null | `monat_plus(vorgaenger.datum, m)`, wenn `vorgaenger` gesetzt ist |
| `abweichung_tage` | int \| null | `von.datum − erwartet` in Tagen (mit Vorzeichen) |
| `uebersprungen` | Liste wie `von` | in diesem Schritt als zusätzlich erkannte Einträge (bei `anker`: die anderen Kandidaten); Reihenfolge nicht festgelegt (E-195 Nr. 2) |
| `fremd` | wie `von` \| null | bei `fremde_zahlung`: der jüngste Eintrag dazwischen, der keine zusätzliche Zahlung ist |
| `kandidaten` | Liste `{buchung_id, datum, betrag, laenge, gleicher_betrag}` | nur bei `anker` (sonst leer), aufsteigend nach (`datum`, `buchung_id`) |
| `text` | str | deutscher Satz (Inhalt nicht Teil der Abnahme) |

Reihenfolge der Schritte: Ein Schritt `anker` steht genau dann vorn, wenn es
mehr als einen Anker-Kandidaten gibt. Danach folgt je verbundenem Glied ein
Schritt `verbunden`. Der letzte Schritt ist immer `bruch`.

### 8.4 Gründe des Bruchs

- `kein_vorgaenger`: Vor dem Glied (abgesehen von zusätzlichen Zahlungen am
  selben Termin) gibt es keinen Eintrag mehr.
- `abstand`: Der nächste ältere Eintrag passt nicht in das Termin-Fenster.
- `fremde_zahlung`: siehe 2.2.2.

### 8.5 Urteile

Je Eintrag gilt, bezogen auf den ersten erfüllten Rhythmus:

- `glied`: Der Eintrag ist Glied der Kette.
- `zusaetzlich`: Er ist eine zusätzliche Zahlung (2.2.1, 2.2.2).
- `vor_beginn`: Er liegt vor dem ersten Glied und ist weder Glied noch
  zusätzlich.
- `keine_serie`: Kein Rhythmus ist erfüllt. Das gilt dann für alle Einträge
  der Gruppe.

Gesamturteil:

- `ausgeschlossen`, wenn die Buchung keinen Empfänger hat, nach dem Stichtag
  liegt oder keinen Eintrag ergibt. Dann ist `eintraege` leer.
- sonst `wiederkehrend`, wenn ein Eintrag `glied` ist,
- sonst `zusaetzlich`, wenn ein Eintrag `zusaetzlich` ist,
- sonst `nicht_wiederkehrend`.

Keine neue Objektart, kein neuer Zustand, keine Änderung an Protokoll und
Sicherung. Oberfläche: `oberflaeche.md` 26.

## 9. Meilenstein 25: Betragsfilter (E-238)

Übernahme der freigegebenen Meilenstein-Definition des Auftraggebers vom 2026-11-13
(Feature `betragsfilter-wiederkehrend`, kontor-app D-137). Ergänzt und ändert M16
(2.2 „Kette“, 8 „Begründung“, `oberflaeche.md` 26). Abschnitte 1–6 und 8 der
Definition stehen hier als 9.1–9.6 und 9.8; Verweise darin auf „1“, „2.x“, „3.x“, „5“
meinen 9.1, 9.2.x, 9.3.x, 9.5; „M16 1.2/1.3“ meint 2.2/2.3 dieses Dokuments.
Abschnitt 7 (Oberfläche) steht als `oberflaeche.md` 35. Tests in `tests/app/m25/`
(Marker `m25`); Prüfmerkmale: E-239 bis E-241.

Anlass: Gehalt und unregelmäßige Auslagenerstattungen kommen vom selben Empfänger. Eine Erstattung zwischen zwei
Gehältern brach bisher die Kette als „fremde Zahlung“, und eine Erstattung als jüngste Buchung wurde Anker.

Tests in `tests/app/m25/` (Marker `m25`). **kern:** REST, Kettenregeln (Übersicht `GET /api/wiederkehrend` und
Begründung `GET /api/buchungen/{id}/wiederkehrend`), Protokoll, Sicherung, Ereignisse. **Browsertests (nicht
kern):** Abschnitt 7.

Bezeichnungen wie in M16: Gruppe = Bankumsätze eines Bestandskontos zu einem Empfänger und einer Richtung, aufsteigend
nach (Datum, Buchungs-ID); `T` = 5 Tage; Rhythmen monatlich (m = 1, Mindestanzahl 3), vierteljährlich (3, 3),
jährlich (12, 2); Termin-Fenster eines Glieds `c` für einen älteren Eintrag `x`: `|c.datum − (x.datum + m Monate)| ≤ T`.

**Vertragsänderung (E-238):** Die ausgelieferte Vorgabe ist `toleranz` mit 10 %. Damit
ändert sich die Erkennung gegenüber M16 für Gruppen mit abweichenden Beträgen; mit
Vorgabe `aus` gilt M16 unverändert. Die M16-Tests setzen die Vorgabe `aus` (9.6).

### 9.1 Betragsfilter

Ein Betragsfilter hat einen **Modus**:

| Modus | Parameter | Bedeutung |
| --- | --- | --- |
| `aus` | – | jeder Betrag zählt (Verhalten von M16, unverändert) |
| `toleranz` | `toleranz_prozent`, ganze Zahl 0–100 | ein Eintrag `x` **passt** zum Bezug `c`, wenn `|x.betrag − c.betrag| · 100 ≤ toleranz_prozent · |c.betrag|` (Cent, Ganzzahlarithmetik, Grenze eingeschlossen) |
| `mindestschwelle` | `mindestbetrag`, Cent > 0 (ohne Vorzeichen) | nur Einträge mit `|betrag| ≥ mindestbetrag` sind **zugelassen**; zugelassene Einträge passen zueinander immer |

- **zugelassen:** bei `aus` und `toleranz` jeder Eintrag; bei `mindestschwelle` nur `|betrag| ≥ mindestbetrag`.
- **passt(c, x):** `x` ist zugelassen, und bei `toleranz` liegt `x.betrag` in der Toleranz um `c.betrag`. Bei `aus`
  passt alles.
- **Herkunft** (`quelle`): `vorgabe` (Einstellung der Instanz) oder `empfaenger` (eigene Einstellung des Empfängers).
  Für jede Gruppe gilt der Filter ihres Empfängers: die eigene Einstellung, sonst die Vorgabe.
- **Vorgabe der Instanz:** nur `aus` oder `toleranz`. Ohne gespeicherte Einstellung (neue Datenbank) gilt
  **`toleranz` mit 10 %** – das ist der ausgelieferte Wert. Keine Konfigurationsoption und keine Umgebungsvariable.

### 9.2 Kettenbildung mit Betragsfilter (ersetzt bei Modus ≠ `aus` Teile von `wiederkehrend.md` 2.2)

Mit Modus `aus` gelten die M16-Regeln unverändert. Mit `toleranz` oder `mindestschwelle` gilt Folgendes; nicht
zugelassene Einträge werden **überall übergangen**, als gäbe es sie für Glieder, Vorgänger und zusätzliche Zahlungen
nicht. Sie brechen nichts und erscheinen in der Begründung mit Rolle `anderer_betrag` (5).

#### 9.2.1 Anker-Kandidaten

- `aus` und `mindestschwelle`: alle zugelassenen Einträge höchstens `T` Tage vor dem jüngsten zugelassenen Eintrag
  (wie M16, nur über die zugelassenen).
- `toleranz`: Es sei `L` das Datum des jüngsten Eintrags. Kandidat ist jeder Eintrag `i` mit Datum ≥
  `L − 2·m Monate − T Tage`, nach dem **kein** Eintrag `j` folgt, der zu `i` passt und mehr als `T` Tage nach `i` liegt.
  Jeder Kandidat ist also der jüngste Termin seiner Betragsklasse. Eine spätere Zahlung mit anderem Betrag verdrängt
  die Serie damit nicht.
- Auswahl unter den Kandidaten wie M16: längste Kette, dann „gleicher Betrag wie das vorige Glied“, dann der jüngere.
  Bei mehr als einem Kandidaten steht vorn im Kettenprotokoll ein Schritt `anker` mit allen Kandidaten.

#### 9.2.2 Einträge nach dem Anker

Jüngere Einträge als der Anker sind zusätzliche Zahlungen, wenn sie zum Anker passen, sonst übergangen
(`anderer_betrag`). Wurde dabei mindestens einer übergangen, ist die Kette von Anfang an **streng** (2.4).

#### 9.2.3 Vorgänger eines Glieds `c`

- **Kandidaten:** alle älteren zugelassenen Einträge im Termin-Fenster von `c` (wie M16).
- **Wahl:** zuerst gleicher Betrag wie `c`, dann Betrag passt zu `c`, dann geringste Abweichung vom Termin, bei
  Gleichstand der jüngere. Ein Vorgänger außerhalb der Toleranz ist möglich (Preisänderung am Termin), siehe 2.4.
- **Dazwischen:** Einträge zwischen Vorgänger `p` und `c`, die zu `c` oder zu `p` passen, zählen wie in M16
  (zusätzliche Zahlung oder `fremde_zahlung` nach der M16-Regel 1.2, E-193). Alle übrigen dazwischen werden
  **übergangen** und brechen die Kette nicht.
- Hat `c` keinen Kandidaten: Wie M16 endet die Kette (`kein_vorgaenger` bzw. `abstand`). Dabei werden ältere Einträge
  übergangen, die nicht zu `c` passen. Passende innerhalb von `T` Tagen um `c` sind zusätzliche Zahlungen. Der im
  Schritt genannte `vorgaenger` bei `abstand` ist der nächste ältere Eintrag, der zu `c` passt.

#### 9.2.4 Bruch wegen Betrag (neuer Grund `betrag`)

Liegt der gewählte Vorgänger `p` **außerhalb** der Toleranz von `c`, gibt es keinen fremden Eintrag dazwischen, und
gilt eines der beiden:
- die Kette ist streng (seit dem Anker wurde schon etwas übergangen, 2.2 oder ein früherer Schritt), oder
- in diesem Schritt wird etwas übergangen,

dann endet die Kette mit einem Schritt `{"ergebnis": "bruch", "grund": "betrag", "von": c, "vorgaenger": p}`. Die
passenden Einträge dazwischen sind dann zusätzliche Zahlungen (`uebersprungen`). Andernfalls ist es eine Preisänderung:
Die Kette wird verbunden (Text wie M16 „Der Betrag weicht ab …“). Nach jedem verbundenen Schritt, der etwas übergangen
hat, ist die Kette streng.

#### 9.2.5 Mehrheitsregel (nur für die Vorgabe)

Gilt der Filter aus der **Vorgabe** (`quelle = vorgabe`, Modus ≠ `aus`), muss die Kette außer der Mindestanzahl auch
die Mehrheit stellen. Gezählt werden die Einträge ab dem ersten (ältesten) Glied bis zum jüngsten Eintrag der Gruppe,
die weder Glied noch zusätzliche Zahlung sind („übergangen“). Sind es mehr, als die Kette Glieder hat, ist der
Rhythmus **nicht erfüllt** (`erfuellt = false` in der Begründung), und der nächste Rhythmus wird geprüft. Für eigene
Einstellungen eines Empfängers (beliebiger Modus) gilt die Mehrheitsregel nicht.

#### 9.2.6 Folgen für die Serie

Betrag, Jahreskosten, letzte Zahlung, nächste Fälligkeit, Status und `buchung_ids` kommen weiterhin allein aus den
Gliedern (M16 1.3). Übergangene Einträge ändern daran nichts.

#### 9.2.7 Ereignisse und Benachrichtigungen (`wiederkehrend.md` 3)

- `wiederkehrend_betrag` (geänderter Betrag): Die Serie wird mit dem Filter des Empfängers aus der Vorgeschichte
  gebildet. Eine Zahlung **unter der Mindestschwelle** löst nie eine Meldung aus. Bei `toleranz` wird eine Zahlung am
  Termin mit anderem Betrag weiterhin gemeldet, auch außerhalb der Toleranz.
- `wiederkehrend_ausbleibend` folgt der Übersicht mit Filter.

### 9.3 REST (`openapi.yaml`, rückwärtskompatibel)

Alle Endpunkte sind geschützt (Anmeldung/CSRF wie M7). Körper sind JSON-Objekte. Unbekannte Felder, falsche Typen
und Booleans an Ganzzahlstellen ergeben 422 `validierung` (Schemaprüfung, vor allem anderen).

**Filterkörper** `{"modus": "aus"|"toleranz"|"mindestschwelle", "toleranz_prozent": int|null, "mindestbetrag": int|null}`:
`modus` ist Pflicht; die beiden anderen dürfen fehlen.

Fachliche Prüfung (422 `validierung`, `details[].ort` wie angegeben; alle Verstöße gemeinsam):
- `modus = toleranz` ohne `toleranz_prozent` → `["body","toleranz_prozent"]`; außerhalb 0–100 → dasselbe;
- `toleranz_prozent` bei anderem Modus → `["body","toleranz_prozent"]`;
- `modus = mindestschwelle` ohne `mindestbetrag` → `["body","mindestbetrag"]`; `mindestbetrag ≤ 0` oder über dem
  Höchstbetrag (`BETRAG_MAX` wie bei Buchungsbeträgen) → dasselbe;
- `mindestbetrag` bei anderem Modus → `["body","mindestbetrag"]`;
- nur Vorgabe: `modus = mindestschwelle` → `["body","modus"]`.

#### 9.3.1 `GET /api/wiederkehrend/einstellungen` → 200

```
{"vorgabe": {"modus": "aus"|"toleranz", "toleranz_prozent": int|null},
 "empfaenger": [{"empfaenger": {"id", "name"}, "modus", "toleranz_prozent", "mindestbetrag"}, …]}
```
`vorgabe.toleranz_prozent` ist bei `aus` `null`. `empfaenger` enthält nur Empfänger mit eigener Einstellung, sortiert
nach Name, dann ID.

#### 9.3.2 `PUT /api/wiederkehrend/einstellungen/vorgabe` → 200 `{"modus", "toleranz_prozent"}`

Reihenfolge: Schema → fachliche Prüfung. Einstellung der Instanz: **kein** Protokolleintrag, nicht rückgängig zu
machen, **nicht** Teil der Sicherung. Einspielen einer Sicherung ändert die Vorgabe nicht. Wirkung sofort auf
Übersicht, Begründung und Ereignisse.

#### 9.3.3 `PUT /api/empfaenger/{id}/wiederkehrend` → 200

Antwort `{"empfaenger": {"id", "name"}, "modus", "toleranz_prozent", "mindestbetrag"}` (nicht verwendete Parameter
`null`). Reihenfolge: Schema (422) → Empfänger unbekannt (404 `nicht_gefunden`) → fachliche Prüfung (422).
Buchbestand: eine Änderung mit Aktion `wiederkehrend_filter_setzen` (Quelle `manuell`, ohne Gruppe), Eintrag
`{"objekt": "empfaenger", "art": "geaendert"}`. Bei gleicher Einstellung entsteht keine Änderung (wie M3: ohne
Wirkung kein Eintrag).

#### 9.3.4 `DELETE /api/empfaenger/{id}/wiederkehrend` → 204

Danach gilt für den Empfänger wieder die Vorgabe. 404 `nicht_gefunden`, wenn der Empfänger fehlt (zuerst geprüft) oder
keine eigene Einstellung hat. Protokoll: Aktion `wiederkehrend_filter_setzen` wie 3.3.

#### 9.3.5 Begründung `GET /api/buchungen/{id}/wiederkehrend` (Erweiterung von `wiederkehrend.md` 8)

Neue Felder, im Schema optional (Pflicht nur in M25-Tests):
- oben: `empfaenger` `{"id","name"}` der Buchung oder `null` (auch bei Urteil `ausgeschlossen`);
- je Eintrag: `betragsfilter` `{"modus","toleranz_prozent","mindestbetrag","quelle"}` (der für die Gruppe geltende
  Filter) und `betragsfilter_text`: „Betragsfilter: Toleranz ±10 % (Vorgabe)“, „Betragsfilter: nur Beträge ab
  2.500,00 € (Einstellung des Empfängers)“ bzw. „Betragsfilter: aus (Vorgabe)“. Herkunft „Vorgabe“ oder „Einstellung
  des Empfängers“, Betrag deutsch formatiert ohne Vorzeichen.
- Rolle in `buchungen[]` und Urteil je Eintrag: neuer Wert **`anderer_betrag`** für übergangene Einträge. Das sind
  nicht zugelassene Einträge sowie Einträge jünger als das erste Glied, die weder Glied noch zusätzlich sind. Ältere
  zugelassene Einträge vor Kettenbeginn bleiben `vor_beginn`. Urteil der ganzen Buchung bei nur `anderer_betrag`:
  `nicht_wiederkehrend`. Der Text nennt den Filter, z. B. „… gehört nicht zur monatlichen Serie, weil ihr Betrag nicht
  passt (Betragsfilter: Toleranz ±10 % (Vorgabe)). Sie wird bei der Kettenbildung übergangen und unterbricht die Serie
  nicht.“
- Schritt-Grund neu: **`betrag`** (2.4), mit `vorgaenger`, `erwartet`, `abweichung_tage`, `uebersprungen`.
- `rhythmen[].erfuellt` berücksichtigt die Mehrheitsregel (2.5).

### 9.4 Datenmodell, Protokoll, Sicherung

- Die eigene Einstellung gehört zum Objekt `empfaenger`. Die Protokollform eines Empfängers erhält das Feld
  `wiederkehrend` `{"modus","toleranz_prozent","mindestbetrag"}` **nur**, wenn er eine eigene Einstellung hat. Formen
  ohne Einstellung und Prüfsummen bleiben damit gleich. `GET /api/empfaenger…` bleibt unverändert, ohne das Feld.
- Rückgängig/Wiederholen (`protokoll.md` 6) stellen die Einstellung her bzw. entfernen sie.
- Empfänger löschen bzw. als Quelle zusammenführen: Die eigene Einstellung des Empfängers entfällt in derselben
  Änderung und kommt mit Rückgängig zurück. Das Ziel behält seine eigene Einstellung.
- Sicherung: Die eigenen Einstellungen gehören dazu. Schemaversion der Sicherungsdatei **6** (bisher 5; ältere
  Versionen werden weiter eingespielt, dann ohne Einstellungen). `anzahl` und Inhaltsprüfsumme ändern sich nur über
  das Feld `wiederkehrend` der Empfängerform. Die Vorgabe der Instanz gehört nicht zur Sicherung. Rundreise-Test mit
  einer Einstellung je Modus.

### 9.5 Beispiele (kern; Vorgabe ±10 %, Empfänger ohne eigene Einstellung)

1. Gehalt 2.500,00 € am 28. jedes Monats, dazwischen Erstattungen 37,40 € / 112,00 € vom selben Empfänger an
   beliebigen Tagen: monatliche Serie aus allen Gehältern. Die Erstattungen haben Rolle `anderer_betrag`, und der
   Kettenschritt über die Erstattungen ist `verbunden`. Mit Vorgabe `aus` bricht die Kette dort mit `fremde_zahlung`.
2. Jüngste Buchung ist eine Erstattung: Anker bleibt das jüngste Gehalt (2.1); die Erstattung ist `anderer_betrag`.
3. 04.08., 04.09., 05.10., 04.11. je −320,32 € und 04.11. −50,00 €: Serie mit vier Gliedern zu −320,32 €; −50,00 € ist
   `anderer_betrag` (unter `aus`: `zusaetzlich`). Der Schritt `anker` nennt beide Kandidaten.
4. Preisänderung ohne Übergehen: 15.01., 15.02. −9,99 €, 15.03., 15.04. −12,99 € (30 %): eine Kette mit vier
   Gliedern (verbunden mit Hinweis auf den abweichenden Betrag).
5. Preisänderung nach Übergehen: wie 4, aber am 20.03. eine weitere Zahlung −1,00 €. Die Kette 15.04.–15.03. ist streng.
   Der Schritt von 15.03. zu 15.02. bricht mit Grund `betrag`, die Serie hat nur zwei Glieder und ist nicht erfüllt.
6. Mehrheitsregel: 3 monatliche Zahlungen −50,00 € und dazwischen 4 andere Beträge (> 10 % Abweichung) desselben
   Empfängers: keine Serie (übergangen 4 > 3 Glieder). Mit eigener Einstellung `toleranz` 10 % beim Empfänger:
   Serie mit drei Gliedern.
7. Mindestschwelle 1.000,00 € beim Empfänger: Zahlungen unter 1.000,00 € sind `anderer_betrag`, auch vor Kettenbeginn.
   Keine Meldung „geänderter Betrag“ für sie.

Die Referenzkette der Tests (`tests/hilfen/wiederkehrend_orakel.py`) wird um die Regeln 2.1–2.5 erweitert;
Zufallsgruppen werden je Modus gegen die Übersicht und die Begründung geprüft.

### 9.6 Folgen für M16 (verbindlich)

- Die M16-Erwartungen gelten mit Vorgabe **`aus`**. Die M16-Tests setzen dazu zu Beginn jeder App
  `PUT /api/wiederkehrend/einstellungen/vorgabe {"modus":"aus"}`, z. B. in der Hilfe bzw. im Fixture. Das ist eine
  zulässige Anpassung früherer Tests wie E-194: Der ausgelieferte Wert ändert sich, das Verhalten bei `aus` nicht.
- Zusätzlich ist das Schema der Begründung zu erweitern: optionale Felder aus 3.5, Werte `anderer_betrag` und
  `betrag` in den Aufzählungen. Frühere Schematests prüfen bei erweiterten Aufzählungen auf Enthaltensein (wie E-210).
- Beobachtet gegen die App (feature/sammeltest2, enthält main):
  - **Mit unverändertem Schema:** Alle M16-Begründungstests und die M16-Browsertests sind rot, nur weil
    `empfaenger`, `betragsfilter` und `betragsfilter_text` im Schema fehlen.
  - **Mit erweitertem Schema und Vorgabe ±10 %:** Rot sind `test_m16_kette.py::test_beispiel_anker_nach_betrag`
    (−50,00 € wird `anderer_betrag` statt `zusaetzlich`), `::test_vorgaenger_nach_betrag_vor_abweichung` (−5,00 € am
    15.02. wird `anderer_betrag` statt `zusaetzlich`; zusätzlicher Schritt `anker`, weil −5,00 € eigener Anker-Kandidat
    ist) und `::test_jaehrlich_mit_zusaetzlicher_zahlung` (−50,00 € wird `anderer_betrag`, Urteil
    `nicht_wiederkehrend` statt `zusaetzlich`). Ebenso rot: `::test_zufallsgruppen_gleich_referenz` (Referenz ohne
    Filter), `test_m16_begruendung.py::test_urteile_und_rollen` (−0,50 € am 16.05. wird `anderer_betrag`) und
    `::test_begruendung_stimmt_mit_uebersicht_ueberein[*]` (Referenz ohne Filter).
  - **Mit erweitertem Schema und Vorgabe `aus`:** M16 und M5 sind vollständig grün (246/246), die M16-Browsertests
    19/19.
- M5-Tests (`-m m5`) sind auch mit Vorgabe ±10 % grün (212/212). Die Leistungstests (`-m leistung`, darunter L12
  `GET /api/wiederkehrend`) sind mit Vorgabe ±10 % grün (22/22).

### 9.8 Abweichungen von D-137 und Hinweise

- D-137 nennt die Mehrheitsregel „ab dem ersten Glied bis zur jüngsten Buchung“; so ist sie hier festgelegt (2.5). Ein
  Kommentar im Code spricht von „zwischen erstem und letztem Glied“, das Verhalten folgt D-137.
- Bei `toleranz` gelten die Anker-Kandidaten nach 2.1, auch wenn der Filter vom Empfänger stammt. Die Mehrheitsregel
  gilt dann aber nicht.
- Die Vorgabe ist nicht über Konfiguration oder Umgebungsdatei einstellbar, nur über REST/Oberfläche.
- Die Gesamtbegründung kennt kein neues Urteil; nur übergangene Einträge ergeben `nicht_wiederkehrend`.

### 9.9 Präzisierungen der Übernahme (E-240)

- Ist bei `mindestschwelle` kein Eintrag der Gruppe zugelassen, hat jeder geprüfte
  Rhythmus `laenge = 0` und keine Schritte (`openapi.yaml`: `laenge ≥ 0`, `schritte`
  darf leer sein).
- `uebersprungen` des Schritts `anker` enthält wie in 8.3 die anderen Kandidaten.
