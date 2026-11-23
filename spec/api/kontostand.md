# Kontostand bei der Synchronisation – Meilenstein 11

Auftrag des Anwenders vom 2026-11-09: „Der Kontostand soll über die
Synchronisation mit abgerufen werden. Bei Differenz gibt es eine
Ausgleichsbuchung.“ Entscheidungen E-158 bis E-162, E-166.

Rückwärtskompatibel (E-029): Liefert das Plugin keinen Saldo (Mock ohne den
neuen Datenschlüssel, Bank ohne Saldenabfrage) oder ist der Abgleich
abgeschaltet, bleibt jeder Lauf genau wie bisher.

## 1. Plugin-Schnittstelle

```python
# kontor.plugins.bank
@dataclass(frozen=True)
class BankSaldo:
    iban: str                # normalisiert
    betrag: int              # gebuchter Saldo in Cent, Sicht des Kontos (Guthaben positiv)
    stichtag: datetime.date  # Buchungstag, bis zu dem (einschließlich) der Saldo gilt

class Umsatzliste(list):     # Liste von BankUmsatz
    saldo: BankSaldo | None  # Vorgabe None (Klassenattribut); Konstruktor: Umsatzliste(umsaetze, saldo=None)
```

- Der Saldo kommt **mit dem Umsatzabruf**: `umsaetze()` liefert eine
  `Umsatzliste` (Unterklasse von `list`, vergleicht und verhält sich wie die
  bisherige Liste) mit dem Attribut `saldo`. Es enthält den gebuchten Saldo
  des abgerufenen Kontos, den die Bank in diesem Abruf gemeldet hat, sonst
  None. Es gibt **keine neue öffentliche Methode**; die Methodenmengen aus
  `plugins.md` 2 und `fints.md` 3 bleiben gleich (E-159).
- Ein Plugin, das eine gewöhnliche `list` liefert (z. B. aus einem früheren
  Meilenstein), gilt als „kein Saldo“.
- Für den Saldo entsteht kein zusätzlicher Dialog, keine zusätzliche
  PIN-Abfrage und keine TAN; scheitert nur die Saldenabfrage, ist `saldo`
  None und das Ergebnis sonst unverändert.
- Der Saldo enthält nur gebuchte Umsätze, keine Vormerkungen. Er hängt nicht
  von `von`/`bis` des Abrufs ab.
- `BankSaldo` ist wie alle Datenklassen `frozen` und vergleichbar
  (`plugins.md` 1). Namen und Modul: `kontor.plugins.bank`.

### 1.1 Mock-Bank-Plugin

Neuer optionaler Schlüssel der Mock-Datendatei (Format und Version bleiben
`kontor-mock-daten`/1):

| Schlüssel | Typ | Bedeutung |
| --- | --- | --- |
| `bank.anfangssalden` | Objekt IBAN → int \| null | Ist er vorhanden, trägt das Ergebnis von `umsaetze(i, …)` für jede hier mit einer Zahl aufgeführte IBAN `i` den Saldo `anfangssalden[i] + Σ betrag` aller gebuchten Umsätze (`vormerkung = false`) von `i` mit `buchungstag ≤ heute`, unabhängig von `von`/`bis` des Abrufs; `stichtag = heute`. Für IBANs mit `null` oder ohne Eintrag: `saldo = None`. Fehlt der Schlüssel (und beim eingebauten Datensatz): immer None. Das Mock-Plugin liefert stets eine `Umsatzliste`. |

Im Szenario `beitragsaenderung` zählen die geänderten Beträge (`plugins.md`
8).

### 1.2 FinTS-Plugin (`fints.md` 3)

- Bietet die Bank die Saldenabfrage an (Parametersegment `HISALS` in der BPD
  und `HKSAL` unter den erlaubten Geschäftsvorfällen des Kontos in der UPD),
  sendet `umsaetze()` im **selben Dialog** nach dem erfolgreichen Umsatzabruf
  (auch nach einer TAN-Freigabe) genau ein `HKSAL` für das Konto (höchste von
  python-fints unterstützte Version, `get_balance`).
- Abbildung von `HISAL`: gebuchter Saldo (`balance_booked`) mit
  Soll/Haben-Kennzeichen → `betrag` (Haben = positiv, Soll = negativ),
  Datum des gebuchten Saldos → `stichtag`. Währung ≠ EUR → None.
- Bietet die Bank keine Saldenabfrage an, wird kein `HKSAL` gesendet, und
  `saldo` ist None. Scheitert nur `HKSAL` (Rückmeldung 9xxx zu diesem
  Segment), bleibt das Ergebnis von `umsaetze()` unverändert, `saldo` ist
  None.
- `HKSAL` ist lesend und steht schon in der Liste aus `fints.md` 3.7.

### 1.3 AqBanking-Plugin – entfallen

Mit Meilenstein 29 entfallen (E-260): Das AqBanking-Plugin und das Feld
`aqbanking_saldo` gibt es nicht mehr. FinTS- und Mock-Saldo (1.1, 1.2)
bleiben unverändert.

## 2. Abgleich im Lauf

Konfiguration (`python-api.md` 17): `sync_saldo_angleichen: bool = True`
(`KONTOR_SYNC_SALDO_ANGLEICHEN`, `from_env` wie andere Wahrheitswerte).

Für jedes Bankkonto, dessen Abruf in diesem Lauf erfolgreich war
(`SyncKonto.status = "erfolgreich"`), direkt nach seiner Verarbeitung
(`synchronisation.md` 4.2–4.4, Umbuchungserkennung `buchhaltungspflege.md`
4.4, Vorlagen und Kredite der späteren Meilensteine), in der Reihenfolge der
Verarbeitung:

1. Ist `sync_saldo_angleichen = false` → `saldo_abgleich.status = "aus"`,
   sonst `s` = Attribut `saldo` des Ergebnisses des letzten erfolgreichen
   `umsaetze()` für dieses Bankkonto in diesem Lauf (auch nach einer
   TAN-Freigabe); fehlt das Attribut (gewöhnliche `list`), gilt None.
2. `s` ist None → `status = "nicht_verfuegbar"`.
3. Sonst `kontor_saldo = saldo(k)` des zugeordneten Kontos `k` mit Stichtag
   `s.stichtag` (`datenmodell.md` 2: nur Splits auf genau `k`, Buchungen
   mit `datum ≤ stichtag`, alle Status), `differenz = s.betrag −
   kontor_saldo`.
4. `differenz = 0` → `status = "stimmt"`, nichts wird gebucht.
5. Sonst → **Ausgleichsbuchung** und `status = "ausgeglichen"`:

| Feld | Wert |
| --- | --- |
| `datum` | `s.stichtag` |
| `empfaenger_id` | null |
| `verwendungszweck` | `"Saldoausgleich Bank"` |
| `status` | `importiert` (zur Prüfung, wie neue Bankbuchungen) |
| Splits | `[{k, differenz, ""}, {„Korrekturen“, −differenz, ""}]` (technisches Konto `kontor:korrektur`, `buchhaltungspflege.md` 1.4, bei Bedarf angelegt) |
| `extern_ids` | `["saldo:" + iban + ":" + stichtag]` |
| `tag_ids` | `[]` |
| `vorschlag` | null |

Die Ausgleichsbuchung ist eine ganz normale Buchung (bearbeiten, löschen,
abstimmen). Sie ist keine Bankbuchung: Ihre Kennung beginnt nicht mit
`bank:`, sie wird nicht gemerkt (`synchronisation.md` 4.3) und ist im
Abgleich (4.4) kein Kandidat. Hat schon eine Buchung dieselbe Kennung (zweite
Differenz am selben Stichtag), wird an die Kennung `":2"`, `":3"`, … bis zur
ersten freien angehängt. Regeln, Lernmodell, Vorlagen, Umbuchungs- und
Dublettenerkennung werden auf sie nicht angewendet.

Danach gilt nach dem nächsten Lauf `kontor_saldo = s.betrag`, solange sich
weder Bank noch Kontor ändern. Jeder Lauf gleicht nur seine eigene Differenz
aus; es gibt keine Zusammenfassung früherer Ausgleichsbuchungen (E-161).

### 2.1 Ergebnis (`SyncKonto.saldo_abgleich`)

Neues Feld (im Schema optional, in den M11-Tests Pflicht) `saldo_abgleich`:
null, solange das Bankkonto nicht erfolgreich verarbeitet ist (`ausstehend`,
`wartet_auf_tan`, `fehlgeschlagen`, `abgebrochen`), sonst:

| Feld | Typ | Regeln |
| --- | --- | --- |
| `status` | `"aus"` \| `"nicht_verfuegbar"` \| `"stimmt"` \| `"ausgeglichen"` | siehe 2 |
| `bank_saldo` | int \| null | `s.betrag`; null bei `aus`/`nicht_verfuegbar` |
| `stichtag` | date \| null | `s.stichtag`; null wie oben |
| `kontor_saldo` | int \| null | vor der Ausgleichsbuchung; null wie oben |
| `differenz` | int \| null | `bank_saldo − kontor_saldo`; null wie oben |
| `buchung_id` | int \| null | die Ausgleichsbuchung, sonst null |

`saldo_abgleich` zählt in keine der bisherigen Zählungen (`buchungen_neu`
usw.); der Lauf-Status hängt nicht davon ab.

### 2.2 Protokoll

Die Ausgleichsbuchung ist eine eigene Änderung (ergänzt `protokoll.md` 4.2):
`quelle = "sync"`, `aktion = "sync_saldoausgleich"`, `gruppe =
"sync:<lauf_id>"`, nach `sync_konto` (und ggf. `umbuchung_erkennen`)
desselben Bankkontos. Eintrag: Buchung angelegt (und ggf. das Konto
„Korrekturen“). Rückgängig entfernt sie wie jede angelegte Buchung; das
Rückgängigmachen der Gruppe entfernt sie zusammen mit dem Lauf.

### 2.3 Benachrichtigung

Neue Art `saldo_ausgeglichen` (`synchronisation.md` 11), Schlüssel
`"saldo:" + iban`, `link = "/konten/<konto_id>"`, entprellt wie dort (nur,
wenn keine ungelesene mit diesem Schlüssel existiert). Text deutsch: Name des
Kontos, Bank- und Kontor-Saldo und Differenz (Format `oberflaeche.md` 5).
Bei `stimmt`, `aus`, `nicht_verfuegbar` keine Benachrichtigung.

## 3. Grenzen (Hinweis für Anwender und Oberfläche)

- **Erster Abruf:** Der erste Lauf holt nur `sync_erstabruf_tage` (90)
  Tage. Liegen ältere Umsätze nicht im Buch, ist die erste Ausgleichsbuchung
  der fehlende Anfangsbestand. Wer danach die alte Historie importiert,
  zählt sie doppelt und muss die Ausgleichsbuchung löschen.
- **Eigene Buchungen vor der Bank:** Eine in Kontor erfasste Buchung, die
  die Bank noch nicht gebucht hat, erzeugt eine Ausgleichsbuchung in
  Gegenrichtung; kommt der Bankumsatz später und wird mit ihr
  zusammengeführt (`synchronisation.md` 4.4), gleicht der folgende Lauf
  wieder aus. Die Ausgleichsbuchungen bleiben `importiert` und lassen sich
  in der Buchungsliste prüfen und löschen.
- Wer das nicht will, schaltet den Abgleich in der Konfiguration ab
  (`KONTOR_SYNC_SALDO_ANGLEICHEN=0`). Die Oberfläche zeigt den letzten
  Abgleich je Bankkonto auf der Seite `/sync` (`oberflaeche.md` 22.4).

## 4. REST

Keine neuen Endpunkte. Erweitert: `SyncKonto.saldo_abgleich`
(`openapi.yaml`, Schema `SaldoAbgleich`), Benachrichtigungsart
`saldo_ausgeglichen`. Die Sicherung (`sicherung.md`) enthält Ausgleichsbuchungen
als gewöhnliche Buchungen; neuer fachlicher Zustand entsteht nicht.
