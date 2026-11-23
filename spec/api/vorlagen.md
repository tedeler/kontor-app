# Split-Vorlagen – Meilenstein 4

Verbindlich für Implementierung und Tests. Umsetzung von K 8
(„Split-Vorlagen für Sammelabbuchungen (z. B. DBK-Versicherung): Erkennung
über Empfänger und Muster, Aufteilung in feste Teilbeträge auf mehrere
Kategorien. Keine Toleranz: Weicht der Gesamtbetrag auch nur um einen Cent
von der Vorlage ab, wird die Buchung nicht automatisch gesplittet und eine
Benachrichtigung ausgelöst. Die Vorlage wird dann manuell angepasst (z. B.
nach Beitragsänderung).“), T 9, T 17 (Auslöser Split-Abweichung) und T 21
(Sammelabbuchung, Mock-Szenario `beitragsaenderung`).
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

## 1. Vorlage

| Feld | Typ | Pflicht beim Anlegen | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `name` | str | ja | 1–200 Zeichen nach `strip()` (gestrippt gespeichert) |
| `aktiv` | bool | nein (true) | inaktive Vorlagen werden nie angewendet und nie als Abweichung gemeldet |
| `prioritaet` | int | nein | 0 ≤ p ≤ 1 000 000, kleiner = wichtiger; Vorgabe: größte vorhandene `prioritaet` aller Vorlagen + 10, ohne Vorlage 100 |
| `bedingungen` | Liste Bedingung | ja | 1–20, UND-verknüpft; Schema und Auswertung wie Regeln (`kategorisierung.md` 1.1, 4), aber nur die Felder `empfaenger`, `verwendungszweck` und `konto_id`; **mindestens eine** Bedingung mit `feld = "empfaenger"` (K 8: „Erkennung über Empfänger und Muster“) |
| `teile` | Liste Teil | ja | 2–50 Teile `{kategorie_id, betrag, memo}` in fester Reihenfolge |
| `gesamtbetrag` | int | – (abgeleitet) | `−Σ teile.betrag`: der Regelbetrag (`kategorisierung.md` 1.1), den eine Buchung haben muss |

**Teil:** `kategorie_id` = Konto der Art `aufwand` oder `ertrag`;
`betrag` = Betrag des Kategorie-Splits in Cent (Soll positiv, also bei einer
Abbuchung positiv), `≠ 0`, Bereich wie `datenmodell.md` 1; `memo` Text,
Vorgabe `""`, höchstens 10 000 Zeichen. Mehrere Teile dürfen dieselbe
Kategorie haben.

Beispiel (Sammelabbuchung 37,90 €): `teile = [{Haftpflicht, 650, "Vertrag
0001"}, {Hausrat, 1290, "Vertrag 0002"}, {Unfall, 1850, "Vertrag 0003"}]`,
`gesamtbetrag = −3790`.

**Fehler** beim Anlegen und Ändern (in dieser Prüfreihenfolge, die erste
zutreffende bestimmt die Antwort, nichts wird geändert): 422 `validierung` (Schema, keine
`empfaenger`-Bedingung, Bedingung mit `feld = "betrag"`, Teilbetrag 0,
`Σ teile.betrag = 0`, Anzahl außerhalb der Grenzen, unbekannte Felder);
422 `kategorie_ungueltig` (Teil-Kategorie unbekannt oder nicht
`aufwand`/`ertrag`); 422 `referenz_unbekannt` (Bedingung `konto_id` kein
existierendes Bestandskonto).

**Reihenfolge** aller Vorlagen: `prioritaet` aufsteigend, bei Gleichstand
`id` aufsteigend; `GET /api/vorlagen` liefert genau diese Reihenfolge.

**Bezüge:** Ein Konto, auf das eine Vorlage verweist (Teil-`kategorie_id`
oder Bedingung `konto_id`), kann über `DELETE /api/konten/{id}` nicht
gelöscht werden (409 `konto_in_verwendung`). `POST
/api/konten/{id}/loeschen` (`loeschen.md`) behandelt Vorlagen wie Regeln
(E-079): Variante `elternkonto` stellt die Verweise auf das Elternkonto um,
die anderen Varianten löschen die betroffenen Vorlagen; das gehört zur
Änderung `konto_loeschen_mit_buchungen` (`loeschen.md` 6, E-094).

## 2. REST

| Methode, Pfad | Ergebnis |
| --- | --- |
| `GET /api/vorlagen` | alle Vorlagen in Reihenfolge (1) |
| `POST /api/vorlagen` | 201 `Vorlage`; 422 wie 1 |
| `GET /api/vorlagen/{vorlage_id}` | 200; 404 |
| `PATCH /api/vorlagen/{vorlage_id}` | nur angegebene Felder; `bedingungen` und `teile` ersetzen die Liste; 200; 404; 422 wie 1 |
| `DELETE /api/vorlagen/{vorlage_id}` | 204; 404 |
| `POST /api/vorlagen/anwenden` | 5; 200 `VorlagenAnwendung`; 422 `validierung`, `referenz_unbekannt` |

Anlegen, Ändern (mit tatsächlicher Wirkung) und Löschen erzeugen je eine
Änderung `vorlage_anlegen`, `vorlage_aendern`, `vorlage_loeschen`
(`quelle = "manuell"`, `protokoll.md` 9).

## 3. Erkennung

Für eine Buchung bzw. einen neuen Umsatz mit Empfängername, Verwendungszweck,
Konten und Regelbetrag `r` (Texte wie `kategorisierung.md` 4 und
`synchronisation.md` 14.1):

1. *Kandidaten* `K` = aktive Vorlagen, deren Bedingungen alle zutreffen, in
   Reihenfolge (1).
2. `K` leer → **keine Vorlage** (die übrigen Stufen der Kategorisierung
   laufen normal).
3. Sonst: die erste Vorlage `V ∈ K` mit `V.gesamtbetrag = r` →
   **Treffer** `V`.
4. Sonst → **Abweichung** mit `V0` = erste Vorlage in `K`. Es gibt keine
   Toleranz: schon 1 Cent mehr oder weniger ist eine Abweichung.

**Aufteilen** einer Buchung mit Bestandskonto-Split `s` nach `V`: Die Splits
werden `[s, t_1, …, t_m]` mit `t_i = {konto_id: V.teile[i].kategorie_id,
betrag: V.teile[i].betrag, memo: V.teile[i].memo}`. Summe 0 gilt, weil
`s.betrag = r = −Σ teile.betrag`. `vorschlag = null`.

## 4. Synchronisation (K 8, T 9)

Für jeden neuen Umsatz (`synchronisation.md` 4.2) wird **vor** den Regeln
die Erkennung (3) ausgewertet (Text `empfaenger` = Empfängername nach 14.1,
`konto_id` = zugeordnetes Konto, `r` = `betrag`):

- **Treffer:** Die Buchung wird mit den Splits aus 3 angelegt
  (`[{Konto, betrag, ""}, t_1, …, t_m]`), `vorschlag = null`, Status
  `importiert` wie jeder Umsatz. Zählt in `SyncKonto.buchungen_gesplittet`
  (nicht in `buchungen_kategorisiert`). Regeln, Standardkategorie und
  Lernmodell werden nicht ausgewertet.
- **Abweichung:** keine automatische Aufteilung. Die Buchung wird mit
  Gegenkonto „Unkategorisiert“ und `vorschlag = null` angelegt; Regeln,
  Standardkategorie und Lernmodell werden **nicht** ausgewertet, damit die
  Abweichung auffällt (E-074). Zählt in `SyncKonto.vorlage_abweichungen`.
  Benachrichtigung (6).
- **Keine Vorlage:** unverändert (Regel → Standardkategorie → Lernmodell →
  „Unkategorisiert“).

Für Umsätze, die mit vorhandenen Buchungen zusammengeführt werden (4.4) oder
deren Kennung gemerkt ist, wird keine Vorlage ausgewertet. Für erfolgreich
verarbeitete Konten gilt `buchungen_gesplittet + vorlage_abweichungen ≤
buchungen_neu`. Alles gehört zur Änderung `sync_konto` des Kontos.

Nach einer Anpassung der Vorlage (`PATCH`, z. B. neuer Teilbetrag nach einer
Beitragsänderung) wird die nächste passende Buchung wieder korrekt
gesplittet (T 9). Bereits angelegte abweichende Buchungen lassen sich mit 5
nachträglich aufteilen.

## 5. Auf vorhandene Buchungen anwenden

`POST /api/vorlagen/anwenden` mit (alle optional) `{buchung_ids: [int],
vorlage_ids: [int], nur_unkategorisiert: bool = true, trocken: bool = false}`:

1. Unbekannte `buchung_ids` → 422 `referenz_unbekannt` mit
   `details.buchung_ids`; unbekannte `vorlage_ids` → 422
   `referenz_unbekannt` mit `details.vorlage_ids` (je aufsteigend); doppelte
   IDs → 422 `validierung`.
2. *Geprüfte Buchungen*: alle (bzw. nur `buchung_ids`), die kategorisierbar
   sind (genau ein Gegensplit), genau einen Split auf einem Bestandskonto
   haben, nicht gesperrt sind und – bei `nur_unkategorisiert = true` –
   `kategorie_id = null` haben. Andere werden stillschweigend übergangen.
3. Verwendete Vorlagen: die aktiven (bei `vorlage_ids` nur diese) in
   Reihenfolge (1). Erkennung (3) je geprüfter Buchung mit `r` =
   Regelbetrag.
4. Treffer → Splits werden ersetzt: der Bestandskonto-Split bleibt mit
   `id`, Betrag und Memo an erster Stelle, danach die Teile (neue Split-IDs);
   ein offener Vorschlag entfällt. Abweichung → die Buchung bleibt
   unverändert und wird in `abweichungen` gemeldet (keine Benachrichtigung).
5. Atomar; eine Änderung `quelle = "vorlage"`, `aktion = "vorlagen_anwenden"`,
   `gruppe = null`, wenn sich etwas ändert. `trocken = true` ändert nichts,
   die Antwort ist dieselbe.

Antwort `VorlagenAnwendung`: `{geprueft, anzahl, trocken, aenderungen:
[{buchung_id, vorlage_id}], abweichungen: [{buchung_id, vorlage_id, betrag,
gesamtbetrag}]}` (je nach `buchung_id` aufsteigend; `betrag` = Regelbetrag
der Buchung, `gesamtbetrag` der Vorlage `V0`; `anzahl` = Länge von
`aenderungen`).

## 6. Benachrichtigung bei Abweichung (T 9, T 17)

Je Abweichung in der Synchronisation (4) mit Vorlage `V0` und Regelbetrag
`r` eine Benachrichtigung (`synchronisation.md` 11):

| Feld | Wert |
| --- | --- |
| `art` | `"split_abweichung"` |
| `schluessel` | `"split_abweichung:" + V0.id + ":" + r` (z. B. `split_abweichung:3:-3840`) |
| `titel`, `text` | deutsch, nicht leer; der Text nennt Vorlage, Betrag der Buchung und erwarteten Gesamtbetrag |
| `link` | `"/buchungen/" + id` der abweichenden Buchung |

Entprellung wie bei Synchronisationsfehlern (keine Nachrichtenflut): Gibt es
bereits eine **ungelesene** Benachrichtigung mit demselben Schlüssel, entsteht
keine neue. Eine Beitragsänderung (derselbe neue Betrag Monat für Monat)
erzeugt also eine Nachricht, bis sie gelesen ist; ein anderer Betrag oder
eine andere Vorlage ist ein neues Ereignis. Benachrichtigungen gehören nicht
zum Buchbestand (Rückgängig ändert sie nicht).

## 7. Mock-Szenario `beitragsaenderung` (T 21)

Neues Szenario für `KontorConfig.mock_szenario` und `MockBankPlugin`
(`plugins.md` 8):

- Mock-Datendatei, zusätzlicher optionaler Schlüssel je Umsatz:
  `betrag_beitragsaenderung` (int, Cent). Im Szenario `beitragsaenderung`
  liefert der Bank-Mock für jeden Umsatz mit diesem Schlüssel `betrag =
  betrag_beitragsaenderung`; alle übrigen Felder und Umsätze sind wie im
  Szenario `normal`. In allen anderen Szenarien wird der Schlüssel ignoriert.
- Bank- und Mail-Mock verhalten sich sonst wie `normal` (keine Fehler, keine
  TAN). Der eingebaute Datensatz darf den Schlüssel enthalten, muss aber
  nicht.
- Der Generator erzeugt `fixtures/mock/m4_vorlagen.json` mit monatlichen
  Sammelabbuchungen einer fiktiven Versicherung, deren Betrag ab einem
  Stichtag im Szenario `beitragsaenderung` abweicht, und die Wahrheit in
  `fixtures/mock/m4_vorlagen.erwartung.json`.

## 8. Manuelles Splitten

Unverändert aus M1: `PUT /api/buchungen/{id}/splits` teilt und führt Splits
jederzeit zusammen (T 9); Invariante 1 (Summe 0) bleibt erhalten. Eine
automatisch gesplittete Buchung lässt sich so wie jede andere bearbeiten.
