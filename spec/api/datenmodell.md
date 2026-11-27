# Datenmodell – Meilenstein 1 bis 5, 11, 12 und 15

Verbindlich für Implementierung und Tests. Begriffe in `code` sind Feldnamen,
wie sie in der REST-API (`openapi.yaml`) und in Python-Objekten
(`python-api.md`) erscheinen. Das physische Datenbankschema (Tabellen,
Indizes) ist Sache der Implementierung; verbindlich ist nur das hier
beschriebene logische Modell und sein Verhalten an den Schnittstellen.

Wo dieses Dokument „später“ sagt, ist etwas nicht Teil von Meilenstein 1 und
wird nicht getestet. Ergänzungen für Meilenstein 2 stehen in Abschnitt 12
sowie in `synchronisation.md` und `kategorisierung.md`, Ergänzungen für
Meilenstein 3 in Abschnitt 13 sowie in `protokoll.md`,
`buchhaltungspflege.md` und `loeschen.md`, Ergänzungen für Meilenstein 4 in
Abschnitt 14 sowie in `gnucash.md`, `lernmodell.md` und `vorlagen.md`,
Ergänzungen für Meilenstein 5 in Abschnitt 15 sowie in `kredite.md`,
`wiederkehrend.md` und `berichte.md`; sie lassen das Verhalten früherer
Meilensteine unverändert (E-029).

## 1. Grundregeln

| Thema | Regel |
| --- | --- |
| IDs | Ganze Zahlen ≥ 1, von der Datenbank vergeben, je Entitätsart eindeutig, monoton steigend in Erzeugungsreihenfolge, nie wiederverwendet (auch nicht nach Löschen). |
| Beträge | Ganze Cent als `int` (in JSON: Ganzzahl ohne Nachkommastellen). Nie Gleitkommazahl, weder in der Datenbank noch an einer Schnittstelle. Zulässiger Bereich je Betrag: `-999 999 999 999 ≤ betrag ≤ 999 999 999 999`. |
| Währung | Ausschließlich `"EUR"` (Fremdwährungen bewusst nicht enthalten, K 16). Das Feld `waehrung` ist überall nur lesbar und hat immer den Wert `"EUR"`. |
| Datum | Kalenderdatum ohne Uhrzeit, Format `YYYY-MM-DD` (ISO 8601, `format: date`). |
| Zeitstempel | ISO 8601 in UTC mit `Z`, z. B. `2026-11-08T12:00:00Z` (`format: date-time`). |
| Texte | UTF-8. Namen (Konto, Empfänger, Tag) werden beim Anlegen/Ändern über REST an den Rändern von Leerraum befreit (`str.strip()`); ist der Rest leer, ist die Eingabe ungültig. Alle anderen Texte werden unverändert gespeichert (inkl. Umlaute, Sonderzeichen, Zeilenumbrüche, Emoji). |
| Textvergleich „normalisiert“ | `norm(s)`: `s.casefold()`, dann `ä→ae`, `ö→oe`, `ü→ue` (ß wird durch `casefold` bereits zu `ss`). Verwendet für Freitextsuche und Tag-Eindeutigkeit (dort nur `casefold`, siehe 6). |
| Empfängervergleich „passend“ | `ekey(s)`: `norm(s)` und danach alle Zeichen entfernen, die nicht in `[a-z0-9]` liegen. Zwei Empfänger sind *passend*, wenn beide fehlen oder `ekey` beider Namen gleich und nicht leer ist. |

## 2. Konto

Kategorien sind intern Konten der Arten `aufwand` und `ertrag` (K 4).

| Feld | Typ | Pflicht beim Anlegen | Regeln |
| --- | --- | --- | --- |
| `id` | int | – (vergeben) | |
| `name` | str | ja | 1–200 Zeichen nach `strip()`. Keine Eindeutigkeit gefordert (bis M31; ab M32 je Ebene eindeutig, `sammel3.md` 1). |
| `art` | Kontoart | ja | nach dem Anlegen unveränderlich |
| `eltern_id` | int \| null | nein (null) | muss existieren, gleiche *Klasse* (siehe unten), keine Zyklen |
| `iban` | str \| null | nein (null) | nur bei Klasse `bestand` erlaubt; siehe IBAN-Regeln; eindeutig über alle Konten |
| `waehrung` | `"EUR"` | – | nur lesbar |
| `geschlossen` | bool | nein (false) | geschlossene Konten bleiben vollständig nutzbar (keine Sperre in M1) |
| `eroeffnet_am` | date \| null | nein (null) | |
| `notiz` | str | nein (`""`) | max. 10 000 Zeichen |
| `extern_id` | str \| null | – (nur Import setzt) | Herkunftskennung, z. B. `kmy:A000001`; siehe Import |
| `ist_kategorie` | bool | – (abgeleitet) | `true` genau für `art ∈ {aufwand, ertrag}` |

### Kontoarten und Klassen

| `art` | Bedeutung | Klasse |
| --- | --- | --- |
| `girokonto` | Girokonto | `bestand` |
| `sparkonto` | Sparkonto | `bestand` |
| `kreditkonto` | Kreditkarte, Darlehen, sonstige Verbindlichkeit | `bestand` |
| `aufwand` | Ausgabenkategorie | `aufwand` |
| `ertrag` | Einnahmenkategorie | `ertrag` |
| `eigenkapital` | Eröffnungssalden, technische Gegenkonten | `eigenkapital` |

*Bestandskonten* sind Konten der Klasse `bestand`.

Hierarchie: beliebig tief. Ein Konto darf nur ein Elternkonto derselben
Klasse haben (z. B. `girokonto` unter `sparkonto` ist erlaubt, `aufwand`
unter `ertrag` nicht). Eine Änderung von `eltern_id`, die einen Zyklus
erzeugen würde (inkl. Konto als eigenes Elternkonto), wird abgelehnt.

Löschen eines Kontos ist nur erlaubt, wenn kein Split darauf bucht und es
keine Unterkonten hat (ab M2 zusätzlich: keine Regel verweist darauf,
`kategorisierung.md` 1.2). Ab M3 lässt sich auch ein benutztes Konto
löschen, und zwar über `POST /api/konten/{konto_id}/loeschen` mit Wahl des
Umgangs mit Buchungen, Unterkonten, Regeln, Standardkategorien und
Abstimmungen (`loeschen.md`). Das hier beschriebene `DELETE` bleibt
unverändert.

### IBAN-Regeln

Eingabe wird normalisiert: alle Leerzeichen entfernen, Großbuchstaben. Gültig
ist sie, wenn sie dem Muster `^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$` entspricht und
die Prüfsumme nach ISO 13616 (mod 97 = 1) stimmt. Gespeichert und ausgegeben
wird die normalisierte Form ohne Leerzeichen.

### Saldo

- `saldo(k)` = Summe der `betrag` aller Splits auf Konto `k` (mit Stichtag:
  nur Splits von Buchungen mit `datum ≤ stichtag`).
- `saldo_gesamt(k)` = `saldo(k)` + Summe `saldo` aller (auch indirekten) Unterkonten.
- Es gibt keine gespeicherten Salden, die von der Splitsumme abweichen dürfen.

### Vorzeichenkonvention (Soll positiv)

Ein Split mit positivem Betrag ist eine Soll-Buchung, ein negativer eine
Haben-Buchung. Daraus folgt:

| Vorgang | Splits |
| --- | --- |
| Gehalt 2 500,00 € aufs Girokonto | Girokonto `+250000`, Ertrag „Gehalt“ `-250000` |
| Einkauf 12,34 € vom Girokonto | Girokonto `-1234`, Aufwand „Lebensmittel“ `+1234` |
| Umbuchung 100 € Giro → Spar | Girokonto `-10000`, Sparkonto `+10000` |
| Kreditkartenzahlung 50 € | Kreditkonto `-5000`, Aufwand `+5000` (Schulden: Saldo negativ) |

Guthaben haben also positiven Saldo, Schulden und Erträge negativen,
Aufwände positiven. Die Oberfläche darf Vorzeichen zur Anzeige umkehren; die
Schnittstellen liefern immer die Rohwerte.

## 3. Buchung (Transaktion)

| Feld | Typ | Pflicht beim Anlegen | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `datum` | date | ja | |
| `empfaenger` | `{id, name}` \| null | – | Ausgabe; Eingabe über `empfaenger_id` |
| `empfaenger_id` | int \| null | nein (null) | nur Eingabe; muss existieren |
| `verwendungszweck` | str | nein (`""`) | max. 10 000 Zeichen über REST; Import ohne Längengrenze |
| `status` | Buchungsstatus | nein (`bestaetigt`) | siehe Statusübergänge |
| `splits` | Liste Split | ja | mindestens 2, Summe exakt 0 |
| `tags` | Liste `{id, name}` | – | Ausgabe, nach `id` aufsteigend, ohne Doppelte |
| `tag_ids` | Liste int | nein (`[]`) | nur Eingabe; Doppelte werden zusammengefasst; müssen existieren |
| `kategorie_id` | int \| null | – (abgeleitet) | siehe 3.2 |
| `betrag` | int | – (abgeleitet) | siehe 3.3 |
| `extern_ids` | Liste str | – | Herkunftskennungen aller zusammengeführten Quellen, aufsteigend sortiert (Zeichenkettenordnung), z. B. `["kmy:T000000000000000001"]`; manuell angelegte Buchungen: `[]` |
| `belege` | Liste Beleg | – | in M1 immer `[]` (Belege später, K 4/T 4) |
| `vorschlag` | Vorschlag \| null | – | ab M2 in jeder Buchungsantwort vorhanden; siehe `kategorisierung.md` 5 |

**Invarianten (gelten nach jeder Operation):**

1. Jede Buchung hat mindestens 2 Splits.
2. Die Summe der `betrag` aller Splits einer Buchung ist exakt 0.
3. Jeder Split verweist auf ein existierendes Konto.
4. Damit ist auch die Summe aller Kontensalden im Buch exakt 0.

Ein Split-Betrag von 0 ist zulässig.

### 3.1 Buchungsstatus

Werte: `importiert`, `vorlaeufig`, `bestaetigt`, `abgeglichen`.

- Beim manuellen Anlegen zulässig: `importiert`, `vorlaeufig`, `bestaetigt`
  (Vorgabe `bestaetigt`). `abgeglichen` ist beim Anlegen unzulässig (422).
- Der Import aus KMyMoney setzt immer `importiert`.
- Zulässige Übergänge: `importiert → bestaetigt`, `vorlaeufig → bestaetigt` (D-257),
  `bestaetigt → abgeglichen`, `vorlaeufig → abgeglichen`. Das Setzen des bereits aktuellen Status ist
  zulässig und ändert nichts. Alle anderen Übergänge werden mit 409
  `status_uebergang_unzulaessig` abgelehnt.
- **Status folgt der Zuordnung (D-261):** `importiert` heißt „noch nicht zugeordnet“, `vorlaeufig` „automatisch
  zugeordnet“, `bestaetigt` „von Hand zugeordnet oder bestätigt“.
  - *Automatisch:* Setzt eine Regel oder das Lernmodell einen Vorschlag (Synchronisation, „Regeln anwenden“,
    „Lernmodell anwenden“) oder teilt eine Split-Vorlage die Buchung auf, wird eine Buchung im Status `importiert`
    in derselben Änderung `vorlaeufig`.
  - *Von Hand:* `PUT /api/buchungen/{id}/kategorie` (Kategorie oder Bestandskonto),
    `POST /api/buchungen/mehrfach/kategorie`, `PUT /api/buchungen/{id}/splits` und das Annehmen eines Vorschlags
    (einzeln und mehrfach) setzen eine Buchung im Status `importiert` oder `vorlaeufig` auf `bestaetigt`.
  - Beides nur, wenn danach kein Split auf „Unkategorisiert“ liegt. Das Ablehnen eines Vorschlags setzt
    `vorlaeufig` wieder auf `importiert`. Importe aus Dateien und das Erfassen ändern den Status nicht.
  - Wie bei der Kreditrate sind das Wirkungen der Anwendung, keine Statuswechsel nach den Übergängen; Rückgängig
    stellt Zuordnung und Status zusammen wieder her.
- Eine Buchung im Status `abgeglichen` ist gesperrt: Änderungen an `datum`,
  `empfaenger_id`, `verwendungszweck`, Splits und Kategorie sowie Löschen
  werden mit 409 `buchung_gesperrt` abgelehnt. Tags dürfen weiterhin geändert
  werden. Maßgeblich ist der Status *vor* der Änderung.

### 3.2 Kategorie einer Buchung

- *Gegensplits* einer Buchung sind ihre Splits auf Konten, die keine
  Bestandskonten sind (Klassen `aufwand`, `ertrag`, `eigenkapital`).
- Eine Buchung ist **kategorisierbar**, wenn sie genau einen Gegensplit hat.
- `kategorie_id` = Konto dieses einen Gegensplits, falls die Buchung
  kategorisierbar ist und das Konto die Art `aufwand` oder `ertrag` hat;
  sonst `null`. (Umbuchungen zwischen Bestandskonten und Buchungen mit
  mehreren Kategorie-Splits haben also `kategorie_id = null`.)
- **Kategorie setzen** (einzeln oder Mehrfachbearbeitung) ersetzt bei einer
  kategorisierbaren Buchung das Konto des Gegensplits durch die neue
  Kategorie; Betrag, Memo und Split-`id` bleiben unverändert, ebenso alle
  anderen Splits, Status, Tags und übrigen Felder. Nicht kategorisierbare
  Buchungen werden abgelehnt (422 `nicht_kategorisierbar`). Die Zielkategorie
  muss ein Konto der Art `aufwand` oder `ertrag` sein (sonst 422
  `kategorie_ungueltig`).

### 3.3 Abgeleiteter Betrag

- In der Buchungsliste **mit** Filter `konto_id`: `betrag` = Summe der Splits
  dieser Buchung auf genau diesem Konto (vorzeichenbehaftet; Unterkonten
  zählen nicht).
- In allen anderen Fällen (Liste ohne `konto_id`, Einzelabruf, Antworten auf
  Änderungen): `betrag` = *Umsatz* = Summe aller positiven Split-Beträge der
  Buchung (≥ 0).

Die Filter `betrag_min`/`betrag_max` und die Sortierung nach Betrag beziehen
sich auf genau diesen Wert.

## 4. Split

| Feld | Typ | Pflicht | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `konto_id` | int | ja | existierendes Konto beliebiger Art |
| `betrag` | int | ja | ganze Cent, Bereich siehe 1; JSON-Gleitkommazahlen (auch `12.0`), Zeichenketten und Booleans sind ungültig |
| `memo` | str | nein (`""`) | max. 10 000 Zeichen über REST |

Splits werden in der beim Anlegen/Ersetzen übergebenen Reihenfolge
gespeichert und ausgegeben (Import: Dokumentreihenfolge). Ersetzen der Splits
(`PUT /api/buchungen/{id}/splits`) vergibt neue Split-IDs. Damit sind
manuelles Splitten und Zusammenführen von Splits abgedeckt (T 9).

## 5. Empfänger

| Feld | Typ | Pflicht | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `name` | str | ja | 1–200 Zeichen nach `strip()`; eindeutig (exakter Vergleich) |
| `extern_id` | str \| null | – | z. B. `kmy:P000001` |

Empfängerverwaltung (Zusammenführen, Aliase, Standardkategorie) ist später.

## 6. Tag

| Feld | Typ | Pflicht | Regeln |
| --- | --- | --- | --- |
| `id` | int | – | |
| `name` | str | ja | 1–100 Zeichen nach `strip()`; eindeutig unter `casefold()` |
| `extern_id` | str \| null | – | z. B. `kmy:G000001` |
| `anzahl_buchungen` | int | – (abgeleitet) | Anzahl Buchungen mit diesem Tag |

Mehrere Tags je Buchung. Umbenennen wirkt auf alle Buchungen (Zuordnung über
`id`). Löschen eines Tags entfernt nur die Zuordnungen; die Buchungen bleiben
sonst unverändert (T 4).

## 7. Beleg

`{id: int, dateiname: str, mime_typ: str, groesse: int}`. In M1 bis M17
existieren keine Belege; `belege` ist dort immer `[]`. Ab M18 sind Belege die
an der Buchung hängenden Dokumente (`dokumente.md` 1.4, E-206): `belege`
listet sie nach `id` aufsteigend; ohne Dokumente bleibt es `[]`.

## 8. Importvorgang (Importquelle)

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | |
| `art` | `"kmymoney"` | ab M4 `"gnucash"` (`gnucash.md`), ab M19 `"alfbanco"` (`alfbanco.md` 4.4) |
| `dateiname` | str \| null | übergebener Dateiname |
| `sha256` | str | Hex-Prüfsumme der hochgeladenen Bytes (vor dem Entpacken) |
| `importiert_am` | date-time | |
| `ergebnis` | ImportErgebnis | wie vom Import zurückgegeben |

Nur **erfolgreiche** Importe erzeugen einen Importvorgang. Das
Importprotokoll ist kein Buchbestand: „Import verändert nichts“
(Idempotenz) bezieht sich auf Konten, Buchungen, Splits, Empfänger, Tags,
Dublettenverdachte und Salden.

## 9. Dublettenverdacht

| Feld | Typ | Regeln |
| --- | --- | --- |
| `id` | int | |
| `buchung_id` | int | neu importierte Buchung |
| `kandidat_ids` | Liste int | vorher vorhandene Buchungen, aufsteigend, mind. 1 |
| `grund` | `"mehrdeutig"` \| `"aehnlich"` | siehe 10.4 |
| `status` | `"offen"` \| `"zusammengefuehrt"` \| `"keine_dublette"` | |
| `erstellt_am` | date-time | |

Wird eine Buchung gelöscht, werden alle *offenen* Verdachte gelöscht, in
denen sie als `buchung_id` oder in `kandidat_ids` vorkommt.

Auflösen:

- `zusammenfuehren` mit `behalten_id` ∈ `kandidat_ids`: Die Buchung
  `buchung_id` wird gelöscht, ihre `extern_ids` werden der Buchung
  `behalten_id` hinzugefügt; sonst ändert sich `behalten_id` nicht.
  Status → `zusammengefuehrt`.
- `keine_dublette`: Nichts an Buchungen ändert sich. Status → `keine_dublette`.
- Nur offene Verdachte können aufgelöst werden (sonst 409 `konflikt`).

## 10. KMyMoney-Import (K 12, T 5, T 6)

### 10.1 Dateierkennung und Fehlerfälle

Eingabe sind die Bytes einer Datei. Prüfreihenfolge:

1. 0 Bytes → Fehler `import_datei_leer`.
2. Beginnt mit `1F 8B` (gzip): entpacken. Beschädigtes/abgeschnittenes gzip
   → `import_datei_beschaedigt`. Entpackt 0 Bytes → `import_datei_leer`.
   Format im Ergebnis: `kmy-gzip`.
3. Sonst: Beginnen die Bytes (nach optionalem UTF-8-BOM und Leerraum) mit
   `<`, wird unkomprimiertes XML angenommen, Format `kmy-xml`. Sonst →
   `import_format_ungueltig`.
4. XML nicht wohlgeformt → `import_datei_beschaedigt`.
5. Enthält das Dokument eine DTD mit internem Teil (insbesondere
   `<!ENTITY …>`-Deklarationen) → `import_format_ungueltig`. Eine
   `<!DOCTYPE KMYMONEY-FILE>` ohne internen Teil ist erlaubt. Externe
   Entitäten/DTDs werden niemals geladen.
6. Wurzelelement nicht `KMYMONEY-FILE` → `import_format_ungueltig`.
7. Inhaltliche Fehler → `import_inhalt_ungueltig` (Liste aller gefundenen
   Fehler, je mit `referenz` auf die betroffene KMyMoney-ID):
   - fehlendes Pflichtattribut: `ACCOUNT@id`, `ACCOUNT@name`, `ACCOUNT@type`,
     `TRANSACTION@id`, `TRANSACTION@postdate`, `SPLIT@account`, `SPLIT@value`,
     `PAYEE@id`, `PAYEE@name`, `TAG@id`, `TAG@name`;
   - Split verweist auf unbekanntes Konto oder auf ein Standardkonto
     (`AStd::…`); `parentaccount` verweist auf unbekanntes Konto;
     `SPLIT@payee` (nicht leer) oder `SPLIT/TAG@id` verweist auf
     Unbekanntes;
   - `value` nicht im Format `[-]Z` oder `[-]Z/N` (Z, N Dezimalziffern,
     N > 0), oder der Wert ist nicht exakt in ganzen Cent darstellbar
     (z. B. `1/3`), oder außerhalb des Betragsbereichs;
   - `postdate` kein gültiges Datum (`YYYY-MM-DD`, optional gefolgt von
     `T…`, dann zählt nur der Datumsteil);
   - Transaktion ohne `SPLIT`.

Bei **jedem** Fehler wird nichts importiert (kein Teilimport, keine
Änderung am Buch, kein Importvorgang); das Ergebnis hat `erfolgreich =
false`, alle Zählungen 0, `import_id = null`, und `fehler` enthält mindestens
eine Meldung mit einem der obigen Codes (bei 1–6 genau eine).

### 10.2 Abbildung

**Konten** (`ACCOUNTS/ACCOUNT`, Dokumentreihenfolge):

- Die Standardkonten mit IDs `AStd::Asset`, `AStd::Liability`,
  `AStd::Expense`, `AStd::Income`, `AStd::Equity` werden nicht übernommen;
  ihre direkten Kinder werden Wurzelkonten (`eltern_id = null`).
- `extern_id = "kmy:" + ACCOUNT@id`, `name = ACCOUNT@name` (unverändert),
  `notiz = ACCOUNT@description` (fehlend → `""`),
  `eroeffnet_am = ACCOUNT@opened` (leer/fehlend → null; ungültig → null und
  Warnung `eroeffnungsdatum_ungueltig`),
  `geschlossen` = Schlüssel-Wert-Paar `mm-closed` mit Wert `yes`
  (Groß-/Kleinschreibung egal), `iban` = Paar `iban` (normalisiert; ungültig
  → null und Warnung `iban_ungueltig`; bereits bei anderem Konto vergeben →
  null und Warnung `iban_doppelt`; nur bei Bestandskonten, sonst ignoriert).
- `ACCOUNT@type` → `art`:

  | type | KMyMoney | `art` | Warnung |
  | --- | --- | --- | --- |
  | 1 | Checkings | girokonto | |
  | 2, 6, 8 | Savings, CertificateDep, MoneyMarket | sparkonto | |
  | 3 | Cash | girokonto | `kontoart_ersetzt` |
  | 9, 14 | Asset, AssetLoan | sparkonto | `kontoart_ersetzt` |
  | 4, 5, 10 | CreditCard, Loan, Liability | kreditkonto | |
  | 12 | Income | ertrag | |
  | 13 | Expense | aufwand | |
  | 16 | Equity | eigenkapital | |
  | 0, 7, 11, 15, sonstige | Unknown, Investment, Currency, Stock | – (Konto übersprungen) | `konto_uebersprungen` |

- `ACCOUNT@currency` fehlend → `EUR`. Ungleich `EUR` → Konto übersprungen,
  Warnung `fremdwaehrung`.
- Elternkonto übersprungen → `eltern_id = null`. Elternkonto anderer Klasse
  → `eltern_id = null`, Warnung `hierarchie_angepasst`.

**Empfänger** (`PAYEES/PAYEE`): `name = PAYEE@name` (unverändert),
`extern_id = "kmy:" + PAYEE@id`.

**Tags** (`TAGS/TAG`): `name = TAG@name`, `extern_id = "kmy:" + TAG@id`.

**Buchungen** (`TRANSACTIONS/TRANSACTION`, Dokumentreihenfolge):

- `extern_ids = ["kmy:" + TRANSACTION@id]`, `datum = postdate`,
  `verwendungszweck = TRANSACTION@memo` (fehlend → `""`), `status =
  importiert`.
- Splits: je `SPLIT` in Dokumentreihenfolge ein Split mit
  `konto_id` (Konto zu `SPLIT@account`), `betrag = value` in Cent,
  `memo = SPLIT@memo` (fehlend → `""`). `shares`, `price`, `reconcileflag`,
  `action`, `number`, `bankid` werden ignoriert.
- `empfaenger` = Empfänger des ersten `SPLIT` (Dokumentreihenfolge) mit nicht
  leerem `payee`-Attribut; keiner → null.
- `tags` = Vereinigung aller `SPLIT/TAG@id` der Transaktion.
- Bucht ein Split auf ein übersprungenes Konto oder ist
  `TRANSACTION@commodity` vorhanden und ≠ `EUR` → die ganze Buchung wird
  übersprungen, Warnung `buchung_uebersprungen` (referenz = Transaktions-ID).
- Ist die Split-Summe ≠ 0 oder gibt es nur einen Split: Es wird ein
  zusätzlicher Split über `-Summe` auf das technische Konto
  **„Unausgeglichen“** angefügt (`name = "Unausgeglichen"`, Art
  `eigenkapital`, Wurzelkonto, `iban = null`, `geschlossen = false`,
  `eroeffnet_am = null`, `notiz = ""`, `extern_id = "kontor:unausgeglichen"`;
  wird beim ersten Bedarf angelegt und danach wiederverwendet), Warnung `buchung_ausgeglichen`. Hat die
  Transaktion nur einen Split mit Betrag 0, wird ebenfalls ein Split über 0
  angefügt. Das technische Konto wird in keiner Zählung mitgezählt.

### 10.3 Zuordnung zu Vorhandenem und Idempotenz

„Vorhanden“ heißt: existierte vor Beginn dieses Importlaufs. Jedes Element
wird so zugeordnet (erste passende Regel gewinnt):

| Objekt | Regel 1 | Regel 2 |
| --- | --- | --- |
| Konto, Klasse `bestand` | gleiche `extern_id` | vorhandenes Konto ohne `extern_id` mit gleicher (normalisierter, gültiger) IBAN; es erhält dann die `extern_id` |
| Konto, andere Klassen | gleiche `extern_id` | vorhandenes Konto ohne `extern_id` mit gleicher `art`, exakt gleichem `name` und gleichem (bereits zugeordnetem) Elternkonto; bei mehreren das mit der kleinsten `id`; es erhält die `extern_id` |
| Empfänger | gleiche `extern_id` | Empfänger mit exakt gleichem Namen (auch einer, der in diesem Lauf angelegt wurde; dann Warnung `empfaenger_zusammengefasst`) |
| Tag | gleiche `extern_id` | Tag mit gleichem Namen unter `casefold()` (auch in diesem Lauf angelegt; dann Warnung `tag_zusammengefasst`) |
| Buchung | eine Buchung, deren `extern_ids` die Kennung enthält | Dublettenprüfung (10.4) |

Zugeordnete Objekte werden **nicht verändert** (Kontor ist nach dem Import
führend), abgesehen vom Setzen der `extern_id` bei Regel 2 für Konten.
Idempotenz (T 3.7): Ein zweiter Import derselben Datei ändert keinen
Buchbestand; alle `*_neu`-Zählungen sind 0, `buchungen_zusammengefuehrt = 0`,
`buchungen_zur_pruefung = 0`. Eine erweiterte Fassung derselben
KMyMoney-Datei (gleiche IDs, zusätzliche Transaktionen) fügt genau die
zusätzlichen Objekte hinzu.

Einschränkung: Ein Kontor-Buch nimmt genau *ein* KMyMoney-Buch auf (ggf.
mehrfach oder in aktualisierten Fassungen). KMyMoney-IDs zweier
verschiedener Dateien würden als dieselben Objekte behandelt.

### 10.4 Dublettenerkennung beim Import

Gilt für jede Transaktion `B`, die nicht über `extern_ids` zugeordnet wurde
und nicht übersprungen wird. *Kandidaten* sind vorhandene Buchungen `C`
(existierten vor dem Lauf), deren `extern_ids` keine Kennung mit Präfix
`kmy:` enthalten (Datensätze derselben Quelle sind nie Dubletten
voneinander).

Für einen Bestandskonto-Split `(k, x)` von `B` (Konto `k`, Betrag `x`)
*trifft* `C`, wenn `C` einen Split auf `k` mit Betrag `x` hat. Dann ist `C`

- **exakt**, wenn zusätzlich `C.datum = B.datum` und die Empfänger von `B`
  und `C` *passend* sind (1.);
- **ähnlich**, wenn `C` nicht exakt ist und `|C.datum − B.datum| ≤ 3` Tage.

`E(B)` = Menge der exakten, `A(B)` = Menge der ähnlichen Kandidaten über
alle Bestandskonto-Splits von `B` (eine Buchung, die über einen Split exakt
und über einen anderen ähnlich ist, zählt als exakt).

Entscheidung (alle `B` werden zuerst bewertet, dann angewendet):

1. `|E(B)| = 1` und der einzige Kandidat `c` liegt in keinem `E(B')` einer
   anderen Transaktion `B'` dieses Laufs → **zusammenführen**: `B` wird nicht
   angelegt; `c.extern_ids` erhält `"kmy:" + id`; sonst bleibt `c`
   unverändert. Zählt als `buchungen_zusammengefuehrt`.
2. Sonst, wenn `E(B) ∪ A(B)` nicht leer → `B` wird angelegt und ein offener
   Dublettenverdacht erzeugt mit `kandidat_ids = E(B) ∪ A(B)` und `grund =
   "mehrdeutig"` falls `E(B)` nicht leer, sonst `"aehnlich"`. Zählt in
   `buchungen_neu` und zusätzlich in `buchungen_zur_pruefung`.
3. Sonst → `B` wird normal angelegt (`buchungen_neu`).

Damit werden zwei echte gleiche Buchungen am selben Tag (zweimal derselbe
Kaffee) nie automatisch zusammengeführt (T 6), und Abweichungen um einen Tag
oder im Empfängertext landen in der Bestätigungsliste.

### 10.5 Importergebnis

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `erfolgreich` | bool | `fehler` ist leer |
| `format` | `"kmy-gzip"` \| `"kmy-xml"` \| null | erkanntes Format nach 10.1 Schritt 2/3; null bei Fehler `import_format_ungueltig` und bei leerer Datei in Schritt 1 |
| `konten_neu`, `konten_vorhanden` | int | Konten der Klassen `bestand` und `eigenkapital` aus der Datei (ohne Standardkonten, ohne übersprungene, ohne „Unausgeglichen“) |
| `kategorien_neu`, `kategorien_vorhanden` | int | Konten der Arten `aufwand`/`ertrag` |
| `empfaenger_neu`, `empfaenger_vorhanden` | int | jedes `PAYEE`-Element zählt genau einmal |
| `tags_neu`, `tags_vorhanden` | int | jedes `TAG`-Element zählt genau einmal |
| `buchungen_neu` | int | angelegte Buchungen (inkl. zur Prüfung) |
| `buchungen_vorhanden` | int | über `extern_ids` zugeordnet |
| `buchungen_zusammengefuehrt` | int | als eindeutige Dublette zusammengeführt |
| `buchungen_zur_pruefung` | int | Teilmenge von `buchungen_neu` mit Verdacht |
| `buchungen_uebersprungen` | int | übersprungen (Fremdwährung, übersprungenes Konto) |
| `splits_neu` | int | Splits der neu angelegten Buchungen (inkl. Ausgleichssplits) |
| `warnungen` | Liste ImportMeldung | |
| `fehler` | Liste ImportMeldung | |
| `import_id` | int \| null | ID des Importvorgangs |

Es gilt: `buchungen_neu + buchungen_vorhanden + buchungen_zusammengefuehrt +
buchungen_uebersprungen` = Anzahl `TRANSACTION`-Elemente.

`ImportMeldung = {code: str, meldung: str, referenz: str | null}`; `meldung`
ist ein deutscher, für Menschen verständlicher Text (Inhalt nicht
getestet, aber nicht leer); `referenz` ist die KMyMoney-ID des betroffenen
Elements (ohne Präfix `kmy:`) oder null. Je betroffenem Element und Code
gibt es genau eine Warnung; die Reihenfolge der Warnungen ist nicht
festgelegt.

Warnungscodes: `kontoart_ersetzt`, `konto_uebersprungen`, `fremdwaehrung`,
`hierarchie_angepasst`, `iban_ungueltig`, `iban_doppelt`,
`eroeffnungsdatum_ungueltig`, `buchung_uebersprungen`,
`buchung_ausgeglichen`, `empfaenger_zusammengefasst`, `tag_zusammengefasst`.

Fehlercodes: `import_datei_leer`, `import_format_ungueltig`,
`import_datei_beschaedigt`, `import_inhalt_ungueltig`.

## 11. Später (nicht Meilenstein 1)

Änderungsprotokoll und Rückgängig (T 3.5/3.6), Login, Regeln und Lernmodell,
Split-Vorlagen, wiederkehrende Buchungen, Kredite, Umbuchungserkennung,
Kontenabstimmung, Empfängerverwaltung, Export, Berichte, GnuCash-Import,
Bank-Synchronisation (Abruf in das Buch), E-Mail-Abgleich, Belege,
laufender Saldo in der Kontoansicht.

Davon in Meilenstein 2 umgesetzt: Bank-Synchronisation und Regeln (Abschnitt
12). Zuordnung der übrigen Punkte zu Meilensteinen: `spec/meilensteine.md`.

## 12. Meilenstein 2: Ergänzungen

| Thema | Festlegung |
| --- | --- |
| Synchronisation | `synchronisation.md`: Läufe, Kontozuordnung über IBAN, Abbildung Umsatz → Buchung (`status = importiert`, `extern_ids = ["bank:<IBAN>:<umsatz_id>"]`), gemerkte Kennungen, Abgleich mit vorhandenen Buchungen, TAN-Anforderungen, Benachrichtigungen, PIN, Planer, simulierte Uhr |
| Technisches Konto „Unkategorisiert“ | Art `eigenkapital`, `extern_id = "kontor:unkategorisiert"`; Gegenkonto synchronisierter Buchungen ohne Regeltreffer (`synchronisation.md` 4.2) |
| Regeln | `kategorisierung.md` 1–4 |
| `Buchung.vorschlag` | `kategorisierung.md` 5; Invariante: `vorschlag ≠ null` ⇒ kategorisierbar und `kategorie_id = vorschlag.kategorie_id` |
| Dublettenverdacht | entsteht auch bei der Synchronisation (`synchronisation.md` 4.4); Schema und Auflösen unverändert (9) |
| Herkunftskennungen | Präfix `kmy:` (Import), `bank:` (Synchronisation); `extern_ids` sortiert wie bisher |

Die Invarianten aus 3 und die globalen Invarianten T 3.1–3.4 gelten auch
für alle Operationen aus Meilenstein 2.

## 13. Meilenstein 3: Ergänzungen

| Thema | Festlegung |
| --- | --- |
| Änderungsprotokoll, Rückgängig | `protokoll.md`: Protokollform je Objekt, Nettowirkung, Gruppen, Rückgängig mit Zustands- und Bezugsprüfung, Wiederholen |
| `Buchung.gegen_iban`, `Buchung.ist_umbuchung`, `Buchung.abgestimmt`, `Split.abstimmung_id` | `buchhaltungspflege.md` 1; ab M3 in jeder Buchungsantwort, im Schema optional (E-029) |
| Gesperrte Buchung | `abgeglichen` **oder** `abgestimmt`; alle Sperrregeln aus 3.1 gelten für beide (`buchhaltungspflege.md` 1.3, 5.4) |
| Empfänger (5) | zusätzlich `aliase`, `standardkategorie_id`; Ändern, Löschen, Zusammenführen (`buchhaltungspflege.md` 2) |
| Konto löschen (2) | zusätzlich 409 `konto_in_verwendung`, wenn es Standardkategorie eines Empfängers ist oder eine Abstimmung darauf verweist |
| Benutzte Konten und Kategorien löschen | `loeschen.md`: Varianten `loeschen`, `elternkonto`, `unkategorisiert`; Konfliktbuchungen; Unterkonten rücken nach oben; Regeln, Standardkategorien und Abstimmungen werden angepasst (E-060 bis E-064) |
| Technisches Konto „Korrekturen“ | Art `eigenkapital`, `extern_id = "kontor:korrektur"` (`buchhaltungspflege.md` 1.4) |
| KMyMoney-Import (10.3) | Empfänger-Regel 3: Alias passt (`buchhaltungspflege.md` 2.3) |
| Vorschlag | `quelle` zusätzlich `"standardkategorie"` (`buchhaltungspflege.md` 2.5) |
| Abstimmung | `buchhaltungspflege.md` 5 |
| Volltextsuche | `buchhaltungspflege.md` 6 (`snorm`); die Freitextsuche der Buchungsliste (`norm`) bleibt |

Die Invarianten aus 3 und die globalen Invarianten T 3.1–3.7 gelten auch für
alle Operationen aus Meilenstein 3, einschließlich Rückgängig.

## 14. Meilenstein 4: Ergänzungen

| Thema | Festlegung |
| --- | --- |
| GnuCash-Import | `gnucash.md`: XML (gzip/unkomprimiert) und SQLite, Herkunftskennung `gnc:<GUID>`, Formate `gnc-xml-gzip`, `gnc-xml`, `gnc-sqlite`, Importvorgang `art = "gnucash"` |
| KMyMoney-Import (10.3) | Regel 2 für Konten gilt auch für vorhandene Konten mit `extern_id` `gnc:…` (sie behalten ihre `extern_id`), dazu Regel 3 für Bestandskonten ohne IBAN (Art, Name, Elternkonto eines `gnc:`-Kontos); jedes vorhandene Konto höchstens einmal je Lauf (`gnucash.md` 7, E-068). Ohne GnuCash-Import unverändert. |
| Herkunftskennungen | Präfixe `kmy:`, `gnc:`, `bank:`; eine Buchung kann Kennungen mehrerer Quellen tragen (zusammengeführte Dubletten) |
| Lernmodell | `lernmodell.md`: Funktion des Buchbestands, kein eigener Zustand; `Vorschlag.quelle = "lernmodell"` mit `sicherheit` (Promille) |
| Vorschlag | zusätzliches Feld `sicherheit` (int 0–1000), nur bei `quelle = "lernmodell"`; im Schema optional |
| Split-Vorlage | `vorlagen.md` 1; neues protokolliertes Objekt `vorlage` |
| Konto löschen (2) | zusätzlich 409 `konto_in_verwendung`, wenn eine Vorlage darauf verweist (`vorlagen.md` 1) |
| Benachrichtigung | zusätzliche Art `split_abweichung` (`vorlagen.md` 6) |

Die Invarianten aus 3 und die globalen Invarianten T 3.1–3.7 gelten auch für
alle Operationen aus Meilenstein 4 (Import, Anwenden von Lernmodell und
Vorlagen, automatisches Aufteilen bei der Synchronisation, Rückgängig).

## 15. Meilenstein 5: Ergänzungen

| Thema | Festlegung |
| --- | --- |
| Kredit | `kredite.md` 2; neues protokolliertes Objekt `kredit` (Darlehenskonto der Art `kreditkonto`, Zahlungskonto, Zinskonto, Parameter, Zuordnungen der Raten, Jahresabgleiche); Teil der Sicherung (`sicherung.md` 2.5) |
| Tilgungsplan | `kredite.md` 3: Funktion der Parameter, kein Zustand; Zins je Rate kaufmännisch auf Cent gerundet, Tilgung = Rate − Zins (T 22) |
| Buchungsstatus (3.1) | `vorlaeufig` setzt die Aufteilung einer Rate automatisch (`kredite.md` 4.1), `abgeglichen` der Jahresabgleich (`kredite.md` 5); beides unterliegt nicht den Übergängen der REST-Statusänderung. Für `PATCH` gelten die Übergänge unverändert. |
| Konto löschen (2) | zusätzlich 409 `konto_in_verwendung`, wenn ein Kredit darauf verweist – bei `DELETE` und bei `POST …/loeschen` (`kredite.md` 2.3, `loeschen.md` 7) |
| Buchung löschen | eine Zuordnung eines Kredits zu dieser Buchung entfällt in derselben Änderung; `buchung_id` eines Abgleichs wird null (`kredite.md` 2.3) |
| Wiederkehrende Buchungen | `wiederkehrend.md`: Funktion des Buchbestands, kein eigener Zustand, nicht im Protokoll, nicht in der Sicherung |
| Benachrichtigung | zusätzliche Arten `neuer_empfaenger`, `wiederkehrend_betrag`, `wiederkehrend_ausbleibend` (`wiederkehrend.md` 6) |
| `SyncKonto` | zusätzliche Zählung `buchungen_kredit` (im Schema optional, ab M5 in jeder Antwort; `synchronisation.md` 17) |
| Berichte, Export | `berichte.md`: Kontostandsverlauf, Einnahmen/Ausgaben ohne Umbuchungen, CSV- und PDF-Export der Buchungsliste; nur lesend |

Die Invarianten aus 3 und die globalen Invarianten T 3.1–3.7 gelten auch für
alle Operationen aus Meilenstein 5 (Kredit anlegen mit Anfangsbuchung,
Aufteilen von Raten, Jahresabgleich, Rückgängig). Ohne Kredite und mit
`wiederkehrend_automatisch = False` (Vorgabe) verhält sich die Anwendung wie
nach M4 und M9.

## 16. Meilenstein 11: Ergänzungen

### 16.1 Filter `unterkonten` (E-163)

Neuer Abfrageparameter `unterkonten: bool = false` für `GET
/api/buchungen` und die Exporte mit demselben Filtersatz
(`/api/export/buchungen.csv`, `/api/export/buchungen.pdf`):

- Nur zusammen mit `konto_id` wirksam (ohne `konto_id` ohne Wirkung, kein
  Fehler).
- `unterkonten=true`: Die Menge `K` = `konto_id` und alle (auch indirekten)
  Unterkonten. Treffer sind Buchungen mit mindestens einem Split auf einem
  Konto aus `K`; `betrag` (3.3) = Summe der Splits dieser Buchung auf Konten
  aus `K`. Davon abhängig wie bisher: `betrag_min`/`betrag_max`, Sortierung
  nach Betrag und `summe` der Listenantwort.
- `unterkonten=false` oder fehlend: unverändert (nur genau `konto_id`).
- Gilt für Konten jeder Art, also für Kategorien und für Bestandskonten mit
  Unterkonten.

## 17. Meilenstein 12: Bearbeiten und Massenänderungen

Auftrag des Anwenders vom 2026-11-09 (E-167 bis E-173). Alles aus 1–16
gilt weiter; `PATCH /api/buchungen/{id}` behält seine Statusübergänge
(3.1, E-168).

### 17.1 Bearbeitbare Bestandteile einer Buchung

| Bestandteil | einzeln | mehrere Buchungen |
| --- | --- | --- |
| Datum, Empfänger, Verwendungszweck | `PATCH` | `mehrfach/aendern` |
| Status | `mehrfach/aendern` (freie Übergänge, 17.2); `PATCH` nur entlang 3.1 | `mehrfach/aendern` |
| Tags | `PATCH` (`tag_ids`) | `mehrfach/tags` |
| Kategorie | `PUT …/kategorie` | `mehrfach/kategorie` |
| Beträge, Konten, Memos der Splits | `PUT …/splits` | – |

Gesperrte Buchungen (abgeglichen oder abgestimmt, `buchhaltungspflege.md`
1.3) bleiben gesperrt; nur der Status ist änderbar (17.2).

### 17.2 `POST /api/buchungen/mehrfach/aendern`

Anfrage `MehrfachAenderung`:

| Feld | Typ | Regeln |
| --- | --- | --- |
| `buchung_ids` | Liste int | mindestens 1, ohne Doppelte |
| `status` | Buchungsstatus | optional |
| `datum` | date | optional |
| `empfaenger_id` | int \| null | optional; null = ohne Empfänger |
| `verwendungszweck` | str | optional, max. 10 000 Zeichen |
| `entsperren` | bool | optional, Vorgabe `false` |

Mindestens eines der Felder `status`, `datum`, `empfaenger_id`,
`verwendungszweck` muss angegeben sein, sonst 422 `validierung`. Jedes
angegebene Feld wird bei **jeder** genannten Buchung auf den Wert gesetzt;
nicht angegebene Felder bleiben unverändert.

**Prüfreihenfolge** (atomar: bei einem Fehler ändert sich nichts):

1. 422 `validierung` (Anfrage).
2. 422 `referenz_unbekannt` mit `details.buchung_ids` (unbekannte Buchungen,
   aufsteigend), danach 422 `referenz_unbekannt` für ein unbekanntes
   `empfaenger_id`.
3. 409 `buchung_gesperrt` mit `details.buchung_ids`: alle Buchungen, die vor
   der Anfrage gesperrt sind und bei denen sich `datum`, `empfaenger_id`
   oder `verwendungszweck` tatsächlich ändern würde (E-026). `entsperren`
   ändert daran nichts.
4. 409 `bestaetigung_erforderlich` mit `details.buchung_ids`: ohne
   `entsperren = true` alle Buchungen mit Status `abgeglichen`, deren Status
   sich tatsächlich ändern würde.

**Wirkung:**

- **Status:** jeder Wert aus jedem Wert, auch `abgeglichen` (keine
  Übergangsregeln). Ändert sich der Status tatsächlich auf `bestaetigt`
  oder `abgeglichen`, wird ein offener Vorschlag bestätigt (`vorschlag =
  null`, Kategorie bleibt; wie `PATCH`, `kategorisierung.md` 5). Die
  Abstimmungsmarke (`abgestimmt`, `Split.abstimmung_id`) hängt nicht am
  Status und bleibt unverändert.
- **Datum, Empfänger, Verwendungszweck:** wie `PATCH` (3); Vorschlag
  unverändert.
- Splits, Tags, Herkunftskennungen und alle übrigen Felder bleiben
  unverändert; die Invarianten aus 3 gelten weiter.
- Antwort 200 `MehrfachErgebnis`: `geaendert` = alle genannten IDs
  aufsteigend, `anzahl` = ihre Zahl (wie die übrigen Mehrfach-Endpunkte,
  auch wenn sich bei einzelnen nichts ändert).
- **Protokoll:** genau eine Änderung `mehrfach_aendern` (`quelle =
  "manuell"`) mit je einem Eintrag für jede Buchung, deren Protokollform sich
  ändert; ändert sich keine, entsteht keine Änderung (`protokoll.md` 4).
  Rückgängig stellt alle Buchungen in einem Schritt wieder her, auch den
  Status `abgeglichen` (wie jedes Rückgängig, ohne Status- und
  Sperrregeln, `protokoll.md` 6).

### 17.3 Sperren im Überblick (ergänzt `buchhaltungspflege.md` 5.4)

| Buchung vor der Anfrage | `status` ändern | `datum`/`empfaenger_id`/`verwendungszweck` ändern |
| --- | --- | --- |
| nicht gesperrt | erlaubt | erlaubt |
| abgeglichen, nicht abgestimmt | nur mit `entsperren = true` | 409 `buchung_gesperrt` (erst Status ändern) |
| abgestimmt (Status nicht `abgeglichen`) | erlaubt | 409 `buchung_gesperrt` (erst Abstimmung aufheben) |
| abgestimmt und abgeglichen | nur mit `entsperren = true` | 409 `buchung_gesperrt` |

## 18. Meilenstein 15: Mehrere Buchungen löschen und verschieben

Freigegebene Meilenstein-Definition vom 2026-11-10 (E-181, E-183 bis
E-185). Alles aus 1–17 gilt weiter.

### 18.1 `POST /api/buchungen/mehrfach/loeschen`

Anfrage `MehrfachLoeschen` `{buchung_ids: [int]}` (mindestens 1, ohne
Doppelte, keine weiteren Felder; sonst 422 `validierung`).

**Prüfreihenfolge** (atomar: bei einem Fehler ändert sich nichts):

1. 422 `validierung` (Anfrage).
2. 422 `referenz_unbekannt` mit `details.buchung_ids` (unbekannte IDs,
   aufsteigend).
3. 409 `buchung_gesperrt` mit `details.buchung_ids` (alle genannten
   Buchungen, die abgeglichen oder abgestimmt sind, aufsteigend;
   `buchhaltungspflege.md` 1.3).

**Wirkung:** je Buchung wie `DELETE /api/buchungen/{id}`, Nebenwirkungen
eingeschlossen (offene Dublettenverdachte, Kreditzuordnungen). Der
Buchbestand danach ist derselbe wie nach den einzelnen `DELETE` in
beliebiger Reihenfolge. Antwort 200 `MehrfachLoeschErgebnis`
`{geloescht: [int] aufsteigend, anzahl}` (`geloescht` = alle genannten IDs).

**Protokoll:** genau eine Änderung `mehrfach_loeschen` (`quelle =
"manuell"`, `gruppe = null`, `protokoll.md` 14). Ein Rückgängig stellt alle
Buchungen mit ihren IDs (auch der Splits) wieder her.

### 18.2 `POST /api/buchungen/mehrfach/verschieben`

Anfrage `MehrfachVerschieben`:

| Feld | Typ | Regeln |
| --- | --- | --- |
| `von_konto_id` | int | Pflicht; Quellkonto |
| `nach_konto_id` | int | Pflicht; Zielkonto, ≠ `von_konto_id` |
| `buchung_ids` | Liste int | mindestens 1, ohne Doppelte |
| `gruppe` | str | mindestens 1 Zeichen, z. B. `"import:3"`, `"sync:7"` (`protokoll.md` 5) |

Genau eines von `buchung_ids` und `gruppe`; beide oder keines, unbekannte
Felder, falsche Typen oder `von_konto_id = nach_konto_id` → 422
`validierung`.

**Prüfreihenfolge** (die erste zutreffende Regel bestimmt die Antwort,
nichts ändert sich):

1. 422 `validierung` (Anfrage).
2. Quellkonto, dann Zielkonto: unbekannt → 422 `referenz_unbekannt`; kein
   Bestandskonto (Art `girokonto`, `sparkonto`, `kreditkonto`) → 422
   `konto_ungueltig`. Beide mit `details.feld` = `"von_konto_id"` bzw.
   `"nach_konto_id"`.
3. `buchung_ids`: unbekannte → 422 `referenz_unbekannt` mit
   `details.buchung_ids` (aufsteigend). `gruppe`: Hat keine Änderung mit
   diesem `gruppe`-Wert eine Buchung angelegt (Eintrag `objekt =
   "buchung"`, `art = "angelegt"`, gleich ob die Änderung noch wirksam ist)
   → 422 `referenz_unbekannt`.
4. 422 `verschieben_unmoeglich` mit `details.buchung_ids` (aufsteigend):
   gewählte Buchungen ohne Split auf dem Quellkonto (nur bei
   `buchung_ids`) oder mit einem Split auf dem Zielkonto.
5. 409 `buchung_gesperrt` mit `details.buchung_ids` (aufsteigend): gewählte
   Buchungen, die gesperrt sind (`buchhaltungspflege.md` 1.3).

**Auswahl bei `gruppe`:** alle noch vorhandenen Buchungen, die eine Änderung
dieser Gruppe angelegt hat (wie 3) und die einen Split auf dem Quellkonto
haben. Eine leere Auswahl ist erlaubt: 200 `{verschoben: [], anzahl: 0}`,
nichts ändert sich, keine Änderung im Protokoll.

**Wirkung:** Bei jeder gewählten Buchung wird der Split auf dem Quellkonto
dem Zielkonto zugeordnet (`konto_id`). Split-ID, Betrag, Memo,
Abstimmungsmarke, Gegensplits und deren Reihenfolge, Datum, Empfänger,
Verwendungszweck, Status, Vorschlag, Tags, Herkunftskennungen und
`gegen_iban` bleiben unverändert. Unterkonten des Quellkontos sind nicht
betroffen (nur Splits genau auf `von_konto_id`). Atomar. Antwort 200
`MehrfachVerschiebeErgebnis` `{verschoben: [int] aufsteigend, anzahl}`.

**Protokoll:** genau eine Änderung `mehrfach_verschieben` (`quelle =
"manuell"`, `gruppe = null`), wenn sich etwas ändert; ein Rückgängig stellt
alle Splits wieder auf das Quellkonto.

Die IBAN der Konten ändert sich nicht: Künftige Umsätze eines Bankkontos
landen weiter in dem Konto, das seine IBAN trägt (`synchronisation.md` 3,
20.3).

### 18.3 `GET /api/konten/{id}/herkunft`

Unbekanntes Konto → 404 `nicht_gefunden`. Antwort 200: Liste
`Herkunft` `{gruppe, art, beschreibung, zeitpunkt, anzahl}` aller Importe
und Synchronisationsläufe, deren Änderungen (Gruppe `"import:<id>"` bzw.
`"sync:<lauf_id>"`) noch vorhandene Buchungen mit einem Split auf genau
diesem Konto angelegt haben (wie 18.2 Schritt 3):

| Feld | Regeln |
| --- | --- |
| `gruppe` | Gruppenschlüssel, verwendbar als `gruppe` in 18.2 |
| `art` | `"import"` bei `import:…`, `"sync"` bei `sync:…` |
| `beschreibung` | deutsch, nicht leer, z. B. „KMyMoney-Import haushalt.kmy“ bzw. „Synchronisation #7“ (Text nicht Teil der Abnahme) |
| `zeitpunkt` | Zeitstempel (`synchronisation.md` 2) oder null: beim Import `importiert_am` des Importvorgangs, beim Lauf `gestartet_am` oder `beendet_am` (E-185) |
| `anzahl` | Zahl dieser Buchungen (≥ 1) |

Sortiert nach `zeitpunkt` absteigend (null zuletzt); Gruppen ohne solche
Buchungen fehlen. Reiner Lesezugriff ohne Wirkung und ohne Protokoll.

## 19. Meilenstein 30: Filter über einen Ausdruck

`GET /api/buchungen` und der Export nehmen zusätzlich `filter`
(Kontor-Ausdruck im Kontext `filter`) und `stichtag` (Bezugstag relativer
Datumsangaben) an; Einzelheiten in `ausdruecke.md` 5. `filter` ist mit allen
übrigen Filtern UND-verknüpft; mit `konto_id` beziehen sich `betrag` und
`richtung` des Ausdrucks auf die Splits dieses Kontos (`ausdruecke.md` 2.2).
Ein ungültiger Ausdruck ist 422 `ausdruck_ungueltig`. Bei aktivem Filter
trägt jede Buchung der Liste das Feld `markierungen`.

## 20. Meilenstein 32: Kontonamen je Ebene eindeutig

Ab M32 sind Kontonamen unter demselben Elternkonto (oberste Ebene: je Klasse)
ohne Groß-/Kleinschreibung und Leerraum am Rand eindeutig; Verstöße → 409
`konto_existiert`. Importe und das Einspielen bereinigen gleichnamige
Geschwister (Warnungen `konto_zusammengefasst`, `konto_umbenannt`). Ersetzt
die Aussage in 2 und Regel 2 für Konten anderer Klassen in 10.3. Einzelheiten:
`sammel3.md` 1 (E-295).

## 21. Kontotyp änderbar, Kontoinhaber, Vorzeichen bei Kreditkonten (Feature `konto-typ-inhaber`, D-312)

- **Kontotyp:** `art` ist bei Bestandskonten über `PATCH /api/konten/{id}` änderbar, und zwar nur innerhalb der
  Klasse `bestand` (`girokonto`, `sparkonto`, `kreditkonto`). Ersetzt „nach dem Anlegen unveränderlich“ in 2 für
  Bestandskonten. Andere Werte → 422 `validierung`; Kategorien und technische Konten (`aufwand`, `ertrag`,
  `eigenkapital`) wechseln den Typ nicht → 422 `art_ungueltig`. Das Darlehenskonto eines Kredits (`kredite.md`)
  bleibt `kreditkonto` → 409 `konto_in_verwendung`. Splits, Salden und Unterkonten bleiben unverändert.
- **Kontoinhaber:** neues Feld `inhaber` = `{vorname, nachname}` (je höchstens 200 Zeichen, Ränder entfernt), nur bei
  Bestandskonten. Beide Teile dürfen leer bleiben; sind beide leer, hat das Konto keinen Inhaber und das Feld fehlt in
  der Antwort. Beim Anlegen und Ändern darf ein Teil fehlen (gilt als leer); `null` entfernt den Inhaber. Ein
  nicht leerer Inhaber bei einem anderen Konto → 422 `inhaber_ungueltig`. Andere Änderungen (auch des Typs) lassen den
  Inhaber stehen; Löschen des Kontos löscht ihn mit.
- **Vorzeichen bei Kreditkonten:** Gespeichert wird weiter nach der Vorzeichenkonvention (Soll positiv); REST,
  Berichte, Filter und Ausdrücke rechnen unverändert. Nur die Anzeige des Kreditkontos selbst dreht das Vorzeichen um
  (`oberflaeche.md` 52): eine Abbuchung erscheint positiv, der Kontostand als Schuld positiv. In der Finanzübersicht
  und der Summe der Bestandskonten geht der Kontostand eines Kreditkontos wie gespeichert negativ ein.
- **Protokoll und Sicherung:** `inhaber` gehört zur Protokollform des Kontos (`protokoll.md` 27); Sicherung ab
  Schemaversion 12 mit Tabelle `konto_inhaber` (`sicherung.md` 16).
