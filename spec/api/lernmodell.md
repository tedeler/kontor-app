# Lernmodell zur Kategorisierung – Meilenstein 4

Verbindlich für Implementierung und Tests. Umsetzung der zweiten Stufe von
K 7 („Lernmodell: Wo keine Regel greift, schlägt ein Klassifikator auf Basis
von Empfänger, Verwendungszweck und Betrag eine Kategorie vor.
Trainingsdaten sind die importierten Altdaten aus KMyMoney und GnuCash.
Jede Korrektur verbessert das Modell.“) und von T 8 und T 21.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Das Verfahren ist vollständig festgelegt und deterministisch: Für denselben
Buchbestand liefert jede Implementierung exakt dieselben Vorschläge und
Sicherheiten. Es braucht nur die Python-Standardbibliothek
(`fractions.Fraction`, `re`), kein Netzwerk und keine zusätzlichen Pakete
(E-070).

## 1. Grundsatz: Das Modell ist eine Funktion des Buchbestands

Das Modell wird nicht als eigener Zustand gespeichert. Es ist zu jedem
Zeitpunkt durch den aktuellen Buchbestand bestimmt (Trainingsmenge 3);
eine Implementierung darf zwischenspeichern, muss sich aber so verhalten,
als würde vor jeder Vorhersage neu trainiert (E-071). Daraus folgt:

- Importierte Altdaten (KMyMoney, GnuCash) sind sofort Trainingsdaten.
- Jede Korrektur (Kategorie setzen, Vorschlag annehmen oder ablehnen,
  Splits ersetzen …) wirkt ab der nächsten Vorhersage.
- Training erzeugt keine Änderung im Protokoll; Rückgängig stellt mit dem
  Buchbestand auch das Modell wieder her.
- Ohne Trainingsdaten gibt es keine Vorhersage (T 8).

## 2. Merkmale

Für eine Buchung bzw. eine Anfrage mit Empfängername `e` (Text oder keiner),
Verwendungszweck `v` (Text) und Betrag `r` (ganze Cent) ist die
Merkmalsmenge `M = E ∪ V ∪ B` (Zeichenketten):

| Gruppe | Merkmale |
| --- | --- |
| `E` (Empfänger) | `"e:" + ekey(e)`, falls `e` vorhanden und `ekey(e)` nicht leer (`datenmodell.md` 1); sonst keines |
| `V` (Verwendungszweck) | `"v:" + w` für jedes *Wort* `w`: Zerlege `norm(v)` an jedem Zeichen außerhalb `[a-z0-9]`; ein Wort hat mindestens 3 Zeichen und enthält mindestens einen Buchstaben `a`–`z`. Doppelte entfallen; höchstens die ersten 20 verschiedenen Wörter in Textreihenfolge |
| `B` (Betrag) | genau eines: `"b:0"` für `r = 0`, sonst `"b:" + s + str(len(str(abs(r))))` mit `s = "+"` für `r > 0`, `"-"` für `r < 0` (Größenordnung in Cent-Stellen, z. B. `-1234` → `"b:-4"`) |

Beispiel: `e = "Café Bohne"`, `v = "Kartenzahlung Café 12/2024"`,
`r = -340` → `{"e:cafbohne", "v:kartenzahlung", "v:caf", "b:-3"}`.

Werte je Buchung `B`:

- `e` = Name des Empfängers von `B` (aktueller Name) bzw. keiner;
- `v` = `B.verwendungszweck`;
- `r` = Regelbetrag von `B` (`kategorisierung.md` 1.1: Summe der Splits auf
  Bestandskonten).

Bei einem neuen Umsatz der Synchronisation: `e` = Empfängername nach
`synchronisation.md` 14.1, `v` = `verwendungszweck`, `r` = `betrag`.

## 3. Trainingsmenge

`T` = alle Buchungen des Buchbestands mit `kategorie_id ≠ null`
(`datenmodell.md` 3.2: kategorisierbar, Gegensplit auf `aufwand`/`ertrag`)
**und** `vorschlag = null` (offene Vorschläge sind keine Wahrheit, K 7).
Etikett `y(B)` = `kategorie_id`. Status, Sperre und Herkunft spielen keine
Rolle; Umbuchungen und Buchungen mit mehreren Kategorie-Splits sind nie in
`T`.

Zählungen über `T`: `n = |T|`; je Kategorie `c`: `N_c` = Anzahl Beispiele
mit `y = c`; je Merkmal `f`: `N(f)` = Anzahl Beispiele mit `f ∈ M`,
`N_c(f)` = Anzahl Beispiele mit `f ∈ M` und `y = c`. `C` = Menge der
Kategorien mit `N_c > 0`.

## 4. Vorhersage (Naive Bayes mit Laplace-Glättung, exakt)

Für eine Merkmalsmenge `M`:

1. *Bekannte Merkmale* `F = {f ∈ M : N(f) > 0}`.
2. Enthält `F` kein Merkmal der Gruppen `E` oder `V` (insbesondere bei
   `n = 0`) → **keine Vorhersage**: `kategorie_id = null`,
   `sicherheit = null`, `kandidaten = []`.
3. Für jedes `c ∈ C`:
   `S(c) = (N_c / n) · ∏_{f ∈ F} (N_c(f) + 1) / (N_c + 2)`.
4. `P(c) = S(c) / Σ_{d ∈ C} S(d)`.
5. Rangfolge der Kategorien: `P` absteigend, bei Gleichstand `kategorie_id`
   aufsteigend. `c*` = erste Kategorie.
6. **Vorschlag**, wenn `P(c*) ≥ 7/10` (Schwelle, E-070); sonst keine
   Kategorie (geringe Sicherheit, T 21).

Alle Rechnungen sind exakt (rationale Zahlen, z. B. `fractions.Fraction`);
Gleitkommazahlen sind nicht zulässig, weil sie Gleichstände und die Schwelle
verfälschen können. **Sicherheit** in Promille: `⌊1000 · P(c)⌋` (ganze Zahl
0–1000).

Ergebnis (`LernVorhersage`):

| Feld | Wert |
| --- | --- |
| `kategorie_id` | `c*`, falls Vorschlag (6), sonst null |
| `sicherheit` | Sicherheit von `c*` in Promille, falls Vorschlag, sonst null |
| `kandidaten` | die ersten höchstens 5 Kategorien der Rangfolge (5) als `{kategorie_id, sicherheit}`; leer bei 2 |

## 5. Anwendung

### 5.1 Stufenfolge bei neuen Buchungen (K 7)

Bei der Synchronisation (`synchronisation.md` 4.2, 14.2, 15) und bei
`POST /api/buchungen/erfassen` (Arten `ausgabe`, `einnahme` ohne
`kategorie_id`, `buchhaltungspflege.md` 3) gilt für das Gegenkonto:

1. (nur Synchronisation) Split-Vorlage (`vorlagen.md` 4);
2. (nur Synchronisation) erste passende Regel;
3. Standardkategorie des Empfängers;
4. **Lernmodell**, nur wenn `lernmodell_automatisch = True`
   (`python-api.md` 10.1, Vorgabe `False`, E-072): Vorhersage (4) mit den
   Merkmalen der neuen Buchung über die Trainingsmenge **zu Beginn der
   Verarbeitung des Bankkontos** bzw. der Anfrage;
5. „Unkategorisiert“.

Ausnahme (mögliche Umbuchung): Hat ein Umsatz eine gültige Gegen-IBAN
(`gegen_iban ≠ null`, `synchronisation.md` 14.1), die die IBAN eines
vorhandenen Kontos ist, wird das Lernmodell für ihn nicht befragt; er bleibt
für die Umbuchungserkennung (`buchhaltungspflege.md` 4) auf
„Unkategorisiert“.

Liefert das Lernmodell eine Kategorie, wird sie Gegenkonto, und die Buchung
erhält `vorschlag = {kategorie_id, regel_id: null, quelle: "lernmodell",
vorher_konto_id: <„Unkategorisiert“>, sicherheit}` („Unkategorisiert“ wird
dafür angelegt, falls nötig). Sie zählt in `buchungen_kategorisiert`.
Annehmen, Ablehnen und alle Erledigungsregeln aus `kategorisierung.md` 5
gelten unverändert; nach dem Erledigen ist die Buchung (mit ihrer dann
gültigen Kategorie) Teil von `T`.

Importe (KMyMoney, GnuCash) und `POST /api/buchungen` werden nie
automatisch kategorisiert.

### 5.2 Auf vorhandene Buchungen anwenden

`POST /api/lernmodell/anwenden` mit (alle optional)
`{buchung_ids: [int], trocken: bool = false}`:

1. Unbekannte IDs → 422 `referenz_unbekannt` mit `details.buchung_ids`
   (aufsteigend); doppelte IDs → 422 `validierung`.
2. *Geprüfte Buchungen*: alle (bzw. nur `buchung_ids`), die kategorisierbar
   sind, `kategorie_id = null` haben (Gegensplit auf einem Eigenkapitalkonto)
   und nicht gesperrt sind (`buchhaltungspflege.md` 1.3). Andere werden
   stillschweigend übergangen.
3. Die Trainingsmenge wird einmal zu Beginn bestimmt. Für jede geprüfte
   Buchung mit Vorhersage wird der Vorschlag gesetzt wie in 5.1, mit
   `vorher_konto_id` = bisheriges Konto des Gegensplits.
4. Atomar; eine Änderung `quelle = "lernmodell"`, `aktion =
   "lernmodell_anwenden"`, `gruppe = null`, wenn sich etwas ändert
   (`protokoll.md` 9). Bei `trocken = true` wird nichts geändert, die
   Antwort ist dieselbe.

Antwort `LernAnwendung`: `{geprueft, anzahl, trocken, aenderungen:
[{buchung_id, kategorie_id, sicherheit}]}`, `aenderungen` nach `buchung_id`
aufsteigend, `anzahl` = Länge.

### 5.3 Vorhersage abfragen (ohne Wirkung)

`POST /api/lernmodell/vorhersage` mit `{"eintraege": [Anfrage, …]}`
(1–1000 Einträge). Eine Anfrage ist entweder `{"buchung_id": int}` (Merkmale
der vorhandenen Buchung nach 2; die Buchung selbst bleibt Teil von `T`,
falls sie dazugehört) oder `{"empfaenger": str | null, "verwendungszweck":
str (Vorgabe ""), "betrag": int}` (`betrag` Pflicht, Bereich wie
`datenmodell.md` 1; `empfaenger` höchstens 200 Zeichen, `verwendungszweck`
höchstens 10 000). Beide Formen in einer Anfrage oder unbekannte Felder →
422 `validierung`; unbekannte `buchung_id` → 422 `referenz_unbekannt` mit
`details.buchung_ids`. Antwort 200 `{"ergebnisse": [LernVorhersage, …]}` in
Anfragereihenfolge, alle gegen dieselbe Trainingsmenge. Ändert nichts.

### 5.4 Zustand

`GET /api/lernmodell` → `{trainingsbuchungen: n, kategorien: |C|,
merkmale: Anzahl verschiedener f mit N(f) > 0, automatisch:
lernmodell_automatisch, schwelle_promille: 700}`.

## 6. Mindestgenauigkeit (T 8, T 21)

Messung auf dem synthetischen Lerndatensatz des Generators (Wahrheit in
`fixtures/m4/lernen.erwartung.json`): Die einfachen Buchungen (ein
Bestandskonto, eine Kategorie) werden nach (Datum, KMyMoney-ID) geordnet;
die älteren 80 % sind Trainingsdaten (`fixtures/kmy/m4_lernen_training.kmy`
bzw. gleichwertig `fixtures/gnc/m4_lernen_training.gnucash` enthalten nur
diese, dazu Buchungen ohne Kategorie bis zum letzten Trainingstag), die
neuesten 20 % Prüfdaten (auch als Bankumsätze in
`fixtures/mock/m4_lernen.json`). Nach dem Import der
Trainingsdatei werden die Prüfdaten über 5.3 (Empfänger, Verwendungszweck,
Regelbetrag) vorhergesagt und mit der *richtigen* Kategorie verglichen
(der Datensatz enthält absichtlich etwa 4 % falsch erfasster
Trainingsbuchungen).

- **Genauigkeit** = richtige Vorschläge / Vorschläge **≥ 85 %**.
- **Abdeckung** = Vorschläge / Prüfbuchungen **≥ 70 %** (damit „nie
  vorschlagen“ die Genauigkeit nicht erfüllt).
- Prüfbuchungen ohne bekanntes Merkmal aus `E`/`V` erhalten keinen
  Vorschlag; Prüfbuchungen neuer Empfänger dürfen über
  Verwendungszweck-Wörter vorgeschlagen werden.

Da das Verfahren festgelegt ist, prüfen die Tests zusätzlich jede einzelne
Vorhersage gegen eine unabhängige Umsetzung (`tests/hilfen/lern_orakel.py`).

## 7. Zusammenspiel mit Regeln, Standardkategorien und Vorlagen

- Regeln greifen immer vor dem Lernmodell (T 8), ebenso Split-Vorlagen und
  Standardkategorien (5.1).
- `POST /api/regeln/anwenden` wertet weiterhin nur Regeln aus.
- Ein abgelehnter Lernmodell-Vorschlag wird nicht gemerkt; die Buchung
  liegt danach wieder auf `vorher_konto_id` (meist „Unkategorisiert“) und ist
  damit nicht in `T`. Eine erneute Anwendung kann denselben Vorschlag wieder
  setzen. Wer die Kategorie korrigieren will, setzt sie (Kategorie setzen);
  diese Korrektur fließt sofort ein (1).

## 8. Meilenstein 31: Transparenz und Einstellungen (Definition 3, D-182, D-183; E-280)

Das Verfahren aus 2–4 bleibt unverändert; die Endpunkte dieses Abschnitts
lesen nur bzw. ändern nur Einstellungen der Instanz.

### 8.1 Erklärung je Buchung – `GET /api/buchungen/{id}/lernmodell`

Lesezugriff (kein Protokoll), unbekannte Buchung → 404 `nicht_gefunden`.
Merkmale der Buchung wie 2, Trainingsmenge wie 3 (die Buchung selbst bleibt
Teil von `T`, falls sie dazugehört, wie 5.3). Antwort `LernErklaerung`:

| Feld | Wert |
| --- | --- |
| `grund` | `kein_modell` bei `n = 0`; `unbekannt`, wenn `F` kein Merkmal der Gruppen `E`/`V` enthält; `vorschlag`, wenn die Vorhersage eine Kategorie liefert; sonst `unter_schwelle` |
| `vorhersage` | `LernVorhersage` wie 5.3 für `{buchung_id}` mit der wirksamen Schwelle (8.3) |
| `beste_kategorie_id` | `c*` (4.5), auch unter der Schwelle; null bei `kein_modell`/`unbekannt` |
| `vergleich_kategorie_id` | zweite Kategorie der Rangfolge; null, wenn es keine gibt oder bei `kein_modell`/`unbekannt` |
| `merkmale` | je bekanntem Merkmal `f ∈ F` ein Eintrag (weitere Einträge mit `anzahl = 0` sind erlaubt): `merkmal` (Zeichenkette nach 2, z. B. `"e:cafbohne"`), `anzahl` = N(f), `anzahl_kategorie` = N_{c*}(f), `anzahl_vergleich` = N_{v}(f) (0 ohne Vergleich), `faktor_promille` = ⌊1000 · Faktor(c*)/Faktor(v)⌋ mit Faktor(c) = (N_c(f)+1)/(N_c+2), null ohne Vergleichskategorie; dazu die drei häufigsten Kategorien des Merkmals (Feldname frei) |
| `aehnliche` | bis zu 5 Buchungen aus `T` (Einträge mit `buchung_id`) mit den meisten gemeinsamen Merkmalen, Gewicht Empfänger 3, Wort 1, Betrag 0; absteigend nach diesem Gewicht; nur Buchungen mit Gewicht > 0 |

Der Grundwert N_c/n darf zusätzlich erscheinen (Feldname frei). Das Produkt
aller Faktoren mal dem Verhältnis der Grundwerte ist genau
P(c*)/P(v); die Angabe in Promille ist abgerundet.

### 8.2 Übersicht – `GET /api/lernmodell/uebersicht`

Lesezugriff: Güte wie 6 auf den eigenen Daten (Trainingsmenge nach Datum,
neueste 20 %, höchstens 2000, als Prüfung), Vorschläge und Treffer je
Schwelle 50–95 %, Verlässlichkeit je Zehntel der Sicherheit, je Kategorie
Beispiele, Prüfung, erkannt, häufigste Verwechslungen und stärkste Merkmale.
Aufbau der Antwort frei (Objekt); darf bis zur nächsten Änderung oder
Schwellenänderung zwischengespeichert werden. Keine Änderung im Protokoll.

### 8.3 Einstellungen der Instanz – `GET`/`PUT /api/lernmodell/einstellungen`

- `{schwelle_promille: int 500–990, regeln_automatisch: bool}`. Vorgaben:
  `schwelle_promille = 700`, `regeln_automatisch` = Konfigurationsfeld
  `regeln_automatisch` (`python-api.md` 22).
- `PUT` mit einem Teil der Felder ändert nur diese; `{}` ändert nichts.
  Unbekanntes Feld, falscher Typ oder Wert außerhalb des Bereichs → 422
  `validierung`. Antwort 200 mit dem Stand danach.
- Gespeichert in der Datenbank der Instanz (bleibt über einen Neustart),
  **nicht** im Änderungsprotokoll und **nicht** in der Sicherung (wie die
  Vorgabe des Betragsfilters, `wiederkehrend.md` 9). Ein einmal gespeicherter
  Wert geht der Konfiguration vor.
- Die Schwelle ersetzt `7/10` in 4.6 überall (5.1, 5.2, 5.3, 8.1);
  `GET /api/lernmodell` meldet sie als `schwelle_promille`. Mit der Vorgabe
  700 gilt alles wie in 1–7.

## 9. Meilenstein 31: Automatisch angelegte Regeln (D-179, D-184; E-279)

### 9.1 Auslöser

Für einen Empfänger `E` mit Buchungen in `T` (3): Sei `K` die Kategorie mit
den meisten Buchungen von `E` in `T`. Eine Regel entsteht, wenn alle
Bedingungen gelten:

1. mindestens 5 Buchungen von `E` in `T` haben `K`;
2. mindestens 95 % der Buchungen von `E` in `T` haben `K` (exakt);
3. im **Fenster** – den 365 Tagen bis zum Datum `d` der jüngsten Buchung von
   `E` in `T` (bzw. bis heute nach der App-Uhr, falls heute früher ist) –
   haben ebenfalls mindestens 95 % der Buchungen von `E` in `T` die
   Kategorie `K`;
4. für `E` besteht noch keine automatische Regel (gleich welcher Zustand),
   und `E` ist nicht gesperrt (9.4);
5. keine aktive Regel trifft die jüngste Buchung von `E` bereits;
6. `E` hat keine Standardkategorie (entfällt mit dem Sammelbranch).

### 9.2 Zeitpunkt

Nach jeder Änderung mit `quelle` `manuell` oder `import`, die Buchungen
berührt, für die Empfänger dieser Buchungen (vorher und nachher), als
**eigene Änderung** direkt danach: `quelle = "lernmodell"`, `aktion =
"regel_automatisch"`, je neuer Regel ein Eintrag Objekt `regel`, Art
`angelegt`. Ohne neue Regel keine Änderung. Synchronisation, Regeln,
Lernmodell, Rückgängig und alle anderen Quellen lösen nichts aus. Nur bei
wirksamem `regeln_automatisch = True` (8.3).

### 9.3 Die Regel

`name` = Empfängername, Bedingung `empfaenger gleich <Name>` (bisherige Form
oder gleichwertiger Ausdruck), `kategorie_id` = `K`, `aktiv = true`,
Priorität wie beim Anlegen ohne Angabe (`kategorisierung.md` 1), keine Tags.
In REST und Protokollform zusätzlich `automatisch: true` und `empfaenger_id`
= `E`; bei allen anderen Regeln fehlen beide Felder. Sonst eine gewöhnliche
Regel: bearbeitbar, abschaltbar, löschbar. Wird `E` umbenannt, bleibt die
Regel unverändert (sie greift dann nicht mehr); eine zweite entsteht nicht.

### 9.4 Löschen sperrt den Empfänger

Das Löschen einer automatischen Regel (`regel_loeschen`) sperrt `E` in
derselben Änderung: Der Empfänger trägt in der Protokollform (und in der
REST-Darstellung, falls geliefert, E-279) `lernregel_gesperrt: true`; ohne
Sperre fehlt das Feld. Ein gesperrter Empfänger bekommt keine automatische
Regel mehr. Rückgängig des Löschens stellt Regel und Zustand ohne Sperre
wieder her. Regeln mit `automatisch`, Sperren und ihre Bezüge gehören zum
Buchbestand und zur Sicherung (`sicherung.md` 13).

## 10. Meilenstein 31: Mitgelieferte Lerndaten (D-181, D-184; E-281)

`POST /api/mock/lerndaten` (ohne Körper) lädt im Mock-Modus 3000 synthetische
Buchungen eines Girokontos (09/2022 bis 10/2026) in einen Bestand **ohne
Buchungen**: ältere 80 % kategorisiert, neueste 20 % auf „Unkategorisiert“.
Außerhalb des Mock-Modus 409 `nur_mock_modus`; mit vorhandenen Buchungen 409
`bestand_nicht_leer`. Eine Änderung `quelle = "import"`, `aktion =
"mock_lerndaten"`, rückgängig zu machen; mit `regeln_automatisch` folgen
automatische Regeln nach 9.2. Antwort 200 oder 201, Körper frei.
