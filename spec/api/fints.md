# Echtes FinTS-Plugin und PIN über systemd-creds – Meilenstein 6

Verbindlich für Implementierung und Tests. Umsetzung von K 6 (nur
Lesezugriff, FinTS über python-fints, QR-TAN mit Bild, PIN über
systemd-creds oder nur im Arbeitsspeicher) und T 7 (FinTS-Attrappe mit
festgelegten Antworten, Vormerkungen und Storno, Fehler ohne Datenverlust,
keine schreibenden Aufträge). Ergänzt `plugins.md` (9), `synchronisation.md`
(18), `python-api.md` (13). Die Synchronisation selbst (Zuordnung, Übernahme,
TAN-Ablauf in der App) bleibt unverändert (`synchronisation.md` 1–17): Das
echte Plugin erfüllt dieselbe Schnittstelle wie das Mock-Plugin.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

**Stand Meilenstein 29 (E-258, E-261):** Die Abschnitte 3 (öffentliche
Methoden), 3.0, 3.1, 3.2, 3.3, 3.4 (Datumsformen), 3.5a und 6 (Betriebsarten
der Attrappe) sind nach der Meilenstein-Definition „Bankabruf über FinTS/camt
und Bankzugang in der Oberfläche“ (`bankzugang.md`) geändert bzw. neu. Wo ein
Absatz mit „M29“ gekennzeichnet ist, ersetzt er die Fassung von M6.

## 1. Bibliothek

- **python-fints** (pip-Distribution `fints`, Import `fints`), Version ≥ 5.0,
  `FinTS3PinTanClient` (FinTS 3.0, PIN/TAN über HTTPS). Geprüft am
  2026-11-09: `fints` 5.0.1 ist ein reines Python-Wheel auf PyPI und lässt
  sich mit `pip install fints` installieren (Abhängigkeiten `mt-940`,
  `sepaxml`, `bleach`, `lxml`, `requests`, `enum-tools`). Es gibt deshalb
  keine Alternative (E-113).
- Das Plugin darf python-fints beliebig verwenden (auch Segmentklassen
  direkt), solange es das Verhalten in 3 und 4 zeigt. Die Tests sprechen nur
  die Schnittstelle `BankPlugin` und die FinTS-Attrappe (6) an.

## 2. Konfiguration

Felder in `KontorConfig` (`python-api.md` 13.1): `fints_url` (Endpunkt
der Bank, z. B. `https://banking.example.invalid/fints`), `fints_blz`
(8 Ziffern), `fints_benutzer` (Anmeldename), `fints_kunden_id` (None →
`fints_benutzer`), `fints_produkt_id` (Produktregistrierung des Betreibers
bei der Deutschen Kreditwirtschaft), `fints_tan_verfahren` (Sicherheitsfunktion,
z. B. `"913"`; None → das erste angebotene Zwei-Schritt-Verfahren mit
TAN-Prozess 2), `fints_timeout_sekunden` (Vorgabe 30), `bank_pin_quelle`
(5). Die **Naht** für Tests ist `fints_url`: Sie zeigt auf die lokale
Attrappe (6).

**M29:** In der App sind `fints_url`, `fints_blz`, `fints_benutzer`,
`fints_kunden_id`, `fints_produkt_id` und `fints_tan_verfahren` nur die
Vorbelegung des Bankzugangs; wirksam ist je Feld der über REST gespeicherte
Wert, sonst die Vorbelegung (`bankzugang.md` 4). Ein unmittelbar mit einer
`KontorConfig` erzeugtes Plugin (wie in den Plugin-Tests) verwendet die Werte
der Konfiguration.

## 3. Plugin `kontor.plugins.fints.FintsBankPlugin`

```python
class FintsBankPlugin(BankPlugin):
    name = "fints"; ist_mock = False
    def __init__(self, config: KontorConfig, *,
                 pin_quelle: Callable[[], str | None] | None = None) -> None: ...
```

`erzeuge_bank_plugin(config, pin_quelle=…)` liefert bei `bank_plugin =
"fints"` genau diese Klasse. Das Erzeugen baut keine Verbindung auf, ruft
`pin_quelle` nicht auf und wirft nicht. Öffentliche Methoden (M29): genau
`konten`, `umsaetze`, `schliessen` und `tan_verfahren` (`plugins.md` 2, 12).
Ab M11 trägt das Ergebnis von `umsaetze` den Saldo (`kontostand.md` 1.2:
`HKSAL` im Dialog des Umsatzabrufs, wenn die Bank es anbietet).

```python
    def konten(self, *, tan: TanAntwort | None = None) -> list[BankKonto]: ...     # M29: tan (3.5a)
    def umsaetze(self, iban, von, bis, *, tan: TanAntwort | None = None) -> Umsatzliste: ...
    def tan_verfahren(self) -> list[tuple[str, str]]: ...                           # M29 (3.0)
    def schliessen(self) -> None: ...
```

### 3.0 TAN-Verfahren (M29)

`tan_verfahren()` liefert die Zwei-Schritt-Verfahren, die die Bank diesem
Zugang erlaubt (Rückmeldung 3920 der Dialoginitialisierung), als Liste von
Paaren aus dreistelliger Sicherheitsfunktion und Name (Name aus den
Bankparametern, HITANS). Sie braucht die PIN, sendet keinen Geschäftsvorfall
und verlangt keine TAN – auch dann nicht, wenn die Bank für die Anmeldung
eine TAN verlangt (3.5a). Nennt die Bank keine erlaubten Verfahren (keine
Rückmeldung 3920), kommen alle Zwei-Schritt-Verfahren aus den Bankparametern.
Das Ein-Schritt-Verfahren (`999`) gehört nie dazu. Die Reihenfolge der Liste
ist nicht festgelegt. Fehler nach 3.1 und 3.6.

### 3.1 Prüfreihenfolge

In `konten()`, `umsaetze()` und `tan_verfahren()` (M29: alle drei):

1. **Konfiguration:** Fehlt eines von `fints_url`, `fints_blz`,
   `fints_benutzer`, `fints_produkt_id` → `PluginNichtVerfuegbar` (ohne
   Verbindung; so bleibt E-017 für unkonfigurierte Instanzen gültig). M29:
   Die Meldung verweist auf die Einstellungen der Oberfläche (sie enthält
   das Wort „Einstellungen“).
2. **Argumente** (nur `umsaetze`): `von > bis` → `ValueError`; die IBAN wird
   normalisiert (`plugins.md` 2).
3. **Freigabe** (`umsaetze` und `konten` mit `tan`): 3.5, 3.5a.
4. **PIN:** `pin_quelle()` wird höchstens einmal je FinTS-Dialog aufgerufen,
   unmittelbar vor dessen Beginn; None oder keine `pin_quelle` →
   `BankPinFehlt` ohne Verbindung.
5. **Verbindung und Abruf** (3.2–3.4), Fehler nach 3.6.

### 3.2 Konten (M29, ersetzt die Fassung von M6)

`konten()` liefert je SEPA-Kontoverbindung der Bank (HISPA, Geschäftsvorfall
HKSPA), die eine IBAN hat und als SEPA-Konto gekennzeichnet ist, ein
`BankKonto`. Die Benutzerparameter der Bank (HIUPD) ergänzen es:

- Der passende Eintrag der Benutzerparameter wird über die IBAN gesucht,
  ersatzweise über die Kontonummer (führende Nullen zählen nicht).
- Daraus kommen Name, Inhaber und Kontoart (Tabelle).
- Gibt es keinen passenden Eintrag oder nennt er keine Kontoart, ist die Art
  `girokonto`; ohne Eintrag sind Name und Inhaber leer (`""`).
- **Nicht** geliefert wird ein Konto nur, wenn der Eintrag ausdrücklich eine
  andere Währung als EUR nennt oder eine Kontoart außerhalb der Tabelle
  (Depot und Ähnliches, K 15).

| Feld | Quelle |
| --- | --- |
| `iban` | IBAN aus HISPA, normalisiert |
| `bic` | BIC aus HISPA, leer → None |
| `name` | Kontoproduktbezeichnung aus HIUPD, fehlt → `""` |
| `art` | Kontoart (HIUPD) 1–9 → `girokonto`, 10–29 → `sparkonto`, 40–59 → `kreditkonto`; fehlt → `girokonto`; andere (Depot 30–39, Fonds, Bausparen, Versicherung, Sonstige) werden **nicht** geliefert |
| `inhaber` | Name des Kontoinhabers 1, mit Inhaber 2 (falls vorhanden) durch ein Leerzeichen verbunden; ohne Eintrag `""` |
| `waehrung` | `"EUR"` |

Reihenfolge: nach `iban` aufsteigend.

### 3.3 Umsätze: Format

`umsaetze(iban, von, bis)` ruft die Umsätze des Kontos für `von`–`bis` ab:

- **camt** (M29): Bieten die Bankparameterdaten den camt-Abruf an (HICAZS),
  wird **immer** camt abgerufen (HKCAZ), gebuchte **und** vorgemerkte
  Umsätze. Verlangt wird genau ein Format:
  `urn:iso:std:iso:20022:tech:xsd:camt.052.001.08`, falls angeboten, sonst
  die höchste angebotene Version von `camt.052.001.07` bis `camt.052.001.02`.
- Bietet die Bank den camt-Abruf an, aber keine dieser Versionen, scheitert
  der Abruf mit `BankFehler` (Code `bank_fehler`). Auf MT940 wird dann nicht
  ausgewichen (kein HKKAZ).
- **MT940** über HKKAZ (gebuchte Umsätze; vorgemerkte MT942-Teile werden
  nicht geliefert) nur noch, wenn die Bank gar keinen camt-Abruf anbietet.
- Die Kontoverbindung im camt-Auftrag (HKCAZ) enthält nur IBAN und BIC, keine
  Kontonummer, kein Unterkontomerkmal und keine Bankleitzahl.
- Aufsetzpunkte (Rückmeldung 3040) werden bis zum Ende verfolgt; das
  Ergebnis enthält alle Seiten.
- Ergebnis: genau die abgebildeten Umsätze mit `von ≤ buchungstag ≤ bis`,
  Währung `EUR`, sortiert nach (`buchungstag`, `umsatz_id`).

### 3.4 Umsätze: Abbildung

**camt.052** (M29: jede Version .02 bis .08 mit denselben Regeln), je
`Rpt/Ntry` in Dokumentreihenfolge (Elementnamen ohne Namensraum; „TxDtls“ =
das erste `NtryDtls/TxDtls`):

| `BankUmsatz` | Quelle |
| --- | --- |
| `betrag` | `Amt` (Dezimalpunkt) in Cent; `CdtDbtInd = CRDT` → positiv, `DBIT` → negativ; `Amt@Ccy ≠ EUR` → Eintrag entfällt |
| `storno` | `RvslInd` = `true` |
| `vormerkung` | `Sts/Cd = PDNG` (bzw. `Sts = PDNG`); `BOOK` → false; andere Status entfallen |
| `buchungstag` | `BookgDt/Dt`, fehlt → `ValDt/Dt` |
| `valuta` | `ValDt/Dt`, fehlt → None |
| Seite der Gegenpartei | `CdtDbtInd`, bei `storno` umgekehrt; `DBIT` → `Cdtr`/`CdtrAcct`, `CRDT` → `Dbtr`/`DbtrAcct` |
| `gegenpartei_name` | `TxDtls/RltdPties/<Partei>/Pty/Nm` (sonst `…/<Partei>/Nm`), unverändert; fehlt oder leer → None |
| `gegenpartei_iban` | `TxDtls/RltdPties/<Konto>/Id/IBAN`, normalisiert, wenn prüfziffergültig; sonst None |
| `verwendungszweck` | alle `TxDtls/RmtInf/Ustrd` in Reihenfolge **ohne** Trennzeichen verbunden; keine → `""` |
| `umsatz_id` | `"ref:" + AcctSvcrRef` (nach `strip()`), wenn nicht leer; sonst Hash-Kennung (unten) |

**Datumsformen (M29):** Buchungs- und Wertstellungsdatum eines Eintrags
dürfen als Datum oder als Zeitpunkt vorliegen und eine Zeitzone tragen
(`2024-06-03`, `2024-06-03+02:00`, `2024-06-03Z`,
`2024-06-03T10:11:12+02:00`); ein Zeitpunkt steht im Element `DtTm` (ISO
20022) oder in `Dt` (E-265). Ausgewertet werden Jahr, Monat und Tag wie
geschrieben (keine Umrechnung in eine andere Zeitzone). Fehlt das
Buchungsdatum, gilt das Wertstellungsdatum; fehlen beide, entfällt der
Eintrag wie bisher. Hat ein Datum oder ein Betrag eine andere Form, scheitert
der ganze Abruf mit `BankFehler` (`bank_fehler`); einzelne Einträge werden
dann nicht stillschweigend ausgelassen.

**MT940** (HKKAZ), je Paar `:61:`/`:86:` aller gelieferten Auszüge in
Reihenfolge. Zeilenumbrüche innerhalb eines Feldes gehören nicht zum Inhalt.

| `BankUmsatz` | Quelle |
| --- | --- |
| `valuta` | `:61:` Stellen 1–6 `JJMMTT` (Jahr 2000 + JJ) |
| `buchungstag` | `:61:` optionale Stellen 7–10 `MMTT` mit dem Jahr der Valuta; liegt das Ergebnis mehr als 180 Tage nach der Valuta, ein Jahr früher, mehr als 180 Tage davor, ein Jahr später; fehlt → Valuta |
| `betrag` | Kennung `C` positiv, `D` negativ, `RC` (Storno einer Gutschrift) negativ, `RD` (Storno einer Lastschrift) positiv; Betrag mit Dezimalkomma in Cent |
| `storno` | Kennung `RC` oder `RD` |
| `vormerkung` | false |
| `verwendungszweck` | Unterfelder `?20`–`?29` und `?60`–`?63` aus `:86:` in Reihenfolge ohne Trennzeichen verbunden |
| `gegenpartei_name` | `?32` und `?33` ohne Trennzeichen verbunden, unverändert; leer → None |
| `gegenpartei_iban` | `?31`, normalisiert, wenn prüfziffergültige IBAN; sonst None |
| `umsatz_id` | Hash-Kennung |

**Hash-Kennung** (Umsätze ohne Bankreferenz): `"h:" + H + ":" + n` mit `H`
= die ersten 16 Hexziffern (klein) von SHA-256 über die UTF-8-Kodierung von
`"|".join([buchungstag, valuta oder "", str(betrag), gegenpartei_iban oder
"", gegenpartei_name oder "", verwendungszweck, "S" bei storno sonst ""])`
(Daten ISO 8601) und `n` = laufende Nummer (ab 1) unter den Einträgen
**desselben Abrufs** mit gleichem Hash in Lieferreihenfolge. Weil ein Abruf
immer ganze Tage umfasst, ist die Kennung über alle Abrufe stabil, auch für
zwei gleiche Umsätze am selben Tag (E-114).

`umsatz_id` ist damit stabil und je Konto eindeutig (`plugins.md` 1).

### 3.5 TAN mit QR-Bild

- Verlangt die Bank für den Umsatzabruf eine TAN (Rückmeldung 0030 mit
  HITAN), wirft `umsaetze` `TanErforderlich` mit
  - `anforderung_id`: nicht leer, vom Plugin gewählt (z. B. die
    Auftragsreferenz der Bank);
  - `challenge`: Anweisungstext der Bank (HITAN `challenge`), nicht leer
    (fehlt er: `"Bitte TAN eingeben"`);
  - `bild`, `bild_mime_typ`: der Matrix-Code aus HITAN `challenge_hhduc`
    (2 Byte Länge + MIME-Typ, 2 Byte Länge + Daten), z. B. `image/png` und
    die PNG-Bytes **unverändert**; ohne Matrix-Code beide None;
  - `gueltig_bis`: HITAN `challenge_valid_until` (Datum und Uhrzeit in
    Europe/Berlin) in UTC; fehlt es: jetzt + 5 Minuten.
  Der FinTS-Dialog bleibt dafür offen bzw. pausiert (python-fints
  `pause_dialog`/`resume_dialog`) in **derselben** Plugin-Instanz.
- `umsaetze(…, tan=TanAntwort(anforderung_id, tan))`: Gibt es keine offene
  Anforderung mit dieser `anforderung_id` → `TanUngueltig`. Sonst sendet das
  Plugin die TAN im selben Dialog (HKTAN Prozess 2) und liefert die Umsätze
  des ursprünglichen Abrufs (Aufsetzpunkte wie 3.3). Rückmeldung 9941 →
  `TanUngueltig`, die Anforderung bleibt offen und kann erneut beantwortet
  werden; 9955 oder Dialogende → `TanAbgelaufen`, die Anforderung entfällt.
- Danach dürfen weitere Abrufe ohne TAN gelingen (Freigabe der Bank,
  `plugins.md` 7.1). Verlangt die Bank erneut eine TAN, entsteht eine neue
  Anforderung.
- Vom Plugin entkoppelte Freigaben (Rückmeldung 3955, Freigabe in einer
  App) werden nicht unterstützt → `BankFehler` (K 6: nur QR-TAN).

### 3.5a TAN bei der Anmeldung (M29)

Verlangt die Bank schon für die Anmeldung (Dialogbeginn; Rückmeldung 0030 mit
HITAN zur Dialoginitialisierung) eine TAN, gilt:

- `konten()` und `umsaetze()` werfen `TanErforderlich` mit Challenge-Text
  und, falls geliefert, Grafik – mit denselben Attributen wie in 3.5.
- Derselbe Aufruf mit der TAN-Antwort (`konten(tan=TanAntwort(…))` bzw.
  `umsaetze(…, tan=TanAntwort(…))`) setzt **denselben Dialog** fort und
  liefert das Ergebnis. Für `umsaetze()` kann danach eine zweite
  `TanErforderlich` für den Abruf selbst folgen (3.5), die genauso
  beantwortet wird.
- Falsche TAN (`TanUngueltig`, Anforderung bleibt offen), abgelaufene
  Anforderung (`TanAbgelaufen`) und unbekannte `anforderung_id`
  (`TanUngueltig`) verhalten sich wie beim Umsatzabruf.
- Verlangt die Bank stattdessen eine entkoppelte Freigabe (Rückmeldung 3955),
  scheitert der Aufruf mit `BankFehler` (`bank_fehler`).
- Eine offene Anforderung lebt nur in der Plugin-Instanz; nach einem Neustart
  ist sie verfallen.
- `tan_verfahren()` ist davon nicht betroffen (3.0).

### 3.6 Fehler

| Ereignis | Ausnahme (`kontor.fehler`) |
| --- | --- |
| Verbindung nicht möglich, HTTP-Status außerhalb 200–299, unlesbare Antwort, TLS-Fehler | `BankVerbindungsFehler` |
| keine Antwort innerhalb `fints_timeout_sekunden` (je HTTP-Anfrage) | `BankZeitueberschreitung` |
| Rückmeldung 9931, 9340, 9910, 9930 oder 9942 (PIN) | `BankPinFalsch` |
| Rückmeldung 3938 (Zugang gesperrt) | `BankZugangGesperrt` (neu, Code `bank_zugang_gesperrt`) |
| Rückmeldung 9210 (Konto unbekannt) oder IBAN nicht unter `konten()` | `BankKontoUnbekannt` |
| 9941 / 9955 im TAN-Ablauf | `TanUngueltig` / `TanAbgelaufen` (3.5) |
| jede andere Rückmeldung 9xxx zum Auftrag oder zur Nachricht | `BankFehler` mit `details.rueckmeldung` = Code |

Meldungen und `details` enthalten nie PIN, TAN oder Benutzerkennung. Nach
`BankPinFalsch` und `BankZugangGesperrt` verwendet das Plugin die PIN nicht
weiter (python-fints sperrt sie; die App verwirft sie, `synchronisation.md`
12 und 18.1).

### 3.7 Nur lesend (K 6, T 7)

- Das Plugin sendet ausschließlich die Segmentarten `HNHBK`, `HNHBS`,
  `HNVSK`, `HNVSD`, `HNSHK`, `HNSHA`, `HKIDN`, `HKVVB`, `HKSYN`, `HKTAN`,
  `HKEND`, `HKSPA`, `HKKAZ`, `HKCAZ`, `HKSAL`, `HKTAB` – nie Überweisungen,
  Lastschriften, Daueraufträge oder andere Aufträge (z. B. `HKCCS`, `HKCCM`,
  `HKCDE`, `HKDSE`, `HKIPZ`), auch wenn die Bank sie anbietet.
- Es gibt keine öffentliche Methode, die einen schreibenden Auftrag
  auslösen kann (`plugins.md` 2).

### 3.8 Protokolle

python-fints schreibt auf Stufe `DEBUG` vollständige Nachrichten (mit TAN)
in den Logger `fints`. Die App sorgt dafür, dass weder dieser noch ein
anderer Logger PIN, TAN oder Benutzerkennung ausgibt (`geheimnisse.md` 6).

## 4. Verhalten in der App

Unverändert nach `synchronisation.md`; das echte Plugin ist für die App ein
Plugin wie jedes andere:

- Die App erzeugt das Plugin beim ersten Lauf und verwendet dieselbe
  Instanz für alle Läufe (`python-api.md` 8.4). Die PIN liefert `pin_quelle`
  nach `synchronisation.md` 12 bzw. 18.1.
- TAN-Anforderung, Bild (`GET /api/tan-anforderungen/{id}/bild` liefert die
  Bytes aus 3.5 unverändert), Beantworten, Ablauf und Abbruch wie
  `synchronisation.md` 7; dazu Push und Erinnerungen
  (`benachrichtigungen.md` 5).
- Fehler aus 3.6 ergeben einen fehlgeschlagenen Lauf bzw. ein
  fehlgeschlagenes Konto mit `code` der Ausnahme und eine Benachrichtigung
  `sync_fehler` (entprellt); bereits übernommene Konten bleiben erhalten
  (T 7: ohne Datenverlust).

## 5. PIN über systemd-creds (K 6)

- `bank_pin_quelle` ∈ {`eingabe`, `systemd-creds`}, Vorgabe `eingabe`
  (Verhalten von M2).
- `systemd-creds`: Die PIN steht in der Datei `kontor-bank-pin` im
  Verzeichnis `credentials_verzeichnis` (aus `$CREDENTIALS_DIRECTORY`, von
  systemd beim Start mit `LoadCredentialEncrypted=kontor-bank-pin:…`
  bereitgestellt; die Entschlüsselung, möglichst TPM-gebunden, übernimmt
  systemd). Ohne `credentials_verzeichnis` → `KonfigurationsFehler` bei der
  Konstruktion der Konfiguration.
- `pin_quelle()` liest die Datei **bei jedem Aufruf** neu (nicht beim
  Erzeugen der App), entfernt genau einen abschließenden Zeilenumbruch
  (`\n` oder `\r\n`) und liefert den Rest; fehlt die Datei oder ist der Rest
  leer → None (`BankPinFehlt`).
- Meldet das Plugin `BankPinFalsch` oder `BankZugangGesperrt`, sperrt die
  App diese Quelle bis zum nächsten Start (neue App-Instanz): `pin_quelle()`
  liefert dann None, kein erneuter Versuch mit derselben PIN (Schutz vor
  Kontosperre).
- `PUT /api/sync/pin` und `DELETE /api/sync/pin` → 409
  `pin_quelle_systemd`; der Körper von `PUT` wird dabei nicht ausgewertet
  und nie zurückgegeben.
- `GET /api/sync/status`: zusätzliches Feld `pin_quelle` (`eingabe` |
  `systemd-creds`; im Schema optional, in M6-Tests Pflicht);
  `pin_vorhanden` = Datei lesbar, nicht leer und Quelle nicht gesperrt.
- Die Datei wird nie geschrieben, kopiert oder als Argument an einen Prozess
  übergeben. Es gibt keinen Aufruf von `systemd-creds` durch die App; die
  Naht für Tests ist das Verzeichnis (E-115).
- Die Variante gilt im Mock- und Echtmodus gleich (das Mock-Plugin fragt
  die PIN ebenfalls über `pin_quelle`, `plugins.md` 7.2).

## 6. FinTS-Attrappe für Tests (`tests/hilfen/fints_attrappe.py`)

Die Attrappe ist eine lokale Bank auf Protokollebene (E-028): ein
HTTP-Server auf `127.0.0.1`, der base64-kodierte FinTS-3.0-Nachrichten
annimmt und beantwortet. Ihre Daten kommen aus dem Generator
(`fixtures/m6/fints_bank.json`, synthetisch, BLZ `00000000`). Verbindlich
für das Plugin ist nur, dass es mit diesem Verhalten (dem einer FinTS-Bank)
zurechtkommt:

- **Dialog:** Synchronisierung (HKSYN → HISYN), Dialoginitialisierung mit
  HKIDN/HKVVB (BPD und UPD bei veralteter Version, Rückmeldung 3920 mit dem
  einzigen zugelassenen Zwei-Schritt-Verfahren, Prozess 2), HKTAN Prozess 4
  beim Dialogbeginn → 3076, Dialogende HKEND → 0100. PIN in HNSHA; falsche
  PIN → 9931 (nach drei falschen in Folge Sperre → 3938).
- **Profile:** `camt` (Vorgabe; BPD nur mit HICAZS, Format
  camt.052.001.08, gebuchte Umsätze und vorgemerkte im zweiten Teil) und
  `mt940` (BPD nur mit HIKAZS Version 7).
- **TAN-Pflicht** laut HIPINS für HKCAZ bzw. HKKAZ: `einmal` (Vorgabe; bis
  zur ersten richtigen TAN, danach Freigabe für alle Dialoge), `immer`
  (einmal je Dialog), `nie`. Ohne HKTAN bei Pflicht → 9075. Mit Pflicht:
  0030 und HITAN Version 6 mit `challenge`, Matrix-Code `image/png` (Bild
  aus den Generatordaten), `challenge_valid_until` = jetzt + 10 Minuten
  (Europe/Berlin). HKTAN Prozess 2 mit der Auftragsreferenz: richtige TAN →
  0020 und die Umsätze; falsche → 9941 (Auftrag bleibt offen); abgelaufen
  (Steuerung `lasse_tan_ablaufen`) oder unbekannte Referenz → 9955.
- **Umsätze:** nur Konten der Kontenliste, `von ≤ buchungstag ≤ bis` und
  `buchungstag ≤ heute` (einstellbar, zeitlich fortlaufend wie die Mocks);
  Seiten zu höchstens `seitengroesse` Umsätzen mit Aufsetzpunkt 3040.
  Vorgemerkte Umsätze (nur `camt`) erscheinen, solange `heute` in ihrem
  Sichtbarkeitszeitraum liegt.
- **Saldo (ab M11):** Mit der Steuerung `saldo_anbieten` (Vorgabe aus)
  enthalten BPD (`HISALS` Versionen 5 und 7) und UPD (`HKSAL`) die Saldenabfrage;
  `HKSAL` liefert `HISAL` mit dem gebuchten Saldo = `anfangssaldo` des
  Kontos (Generatordaten, sonst 0) + Steuerung `saldo_versatz` (Cent,
  Vorgabe 0) + Summe der gebuchten EUR-Umsätze (mit MT940-Darstellung) mit
  `buchungstag ≤ heute`, Datum `heute`, Währung = Kontowährung; für IBANs in
  `saldo_fehler_iban` Rückmeldung 9380 zu `HKSAL`. Ohne die Steuerung bleibt
  alles wie in M6.
- **Betriebsarten ab M29** (E-263; Vorgaben so, dass sich ohne sie nichts
  ändert):
  - `profil="beide"`: BPD mit HICAZS **und** HIKAZS; `camt_formate` (Liste
    der in HICAZS angebotenen Formate, Vorgabe nur camt.052.001.08; Kurzform
    `camt_format(n)` für `…camt.052.001.0n`). Die Attrappe liefert das
    Dokument im verlangten Format; verlangt der Client mehr oder weniger als
    genau ein angebotenes Format → Ablehnung 9930. Aufzeichnung:
    `camt_angefordert` (verlangte Formate je HKCAZ) und
    `camt_kontoverbindungen` (gefüllte Felder der Kontoverbindung je HKCAZ).
  - `tan_anmeldung` ∈ {`nie` (Vorgabe), `einmal`, `immer`}: Dialoginitialisierung
    mit HKTAN Prozess 4 (ohne HKSYN) → 0030 und HITAN wie beim Umsatzabruf;
    HKTAN Prozess 2 mit richtiger TAN → 0020, falsche → 9941, abgelaufen →
    9955. Bis dahin lehnt der Dialog Geschäftsvorfälle mit 9075 ab; ebenso
    Dialoge ohne HKTAN (Ein-Schritt-Dialog), solange die Anmeldung eine TAN
    braucht. `einmal`: bis zur ersten richtigen TAN, `immer`: in jedem
    Dialog. `anmeldung_entkoppelt = True`: statt 0030 die Rückmeldung 3955.
  - `erlaubte_verfahren` (Liste der Sicherheitsfunktionen in 3920; None →
    keine Rückmeldung 3920) und `verfahren_zusatz` (weitere
    Zwei-Schritt-Verfahren in HITANS).
  - Benutzerparameter: `upd_ohne_kontoart`, `upd_ohne_iban` (nur
    Kontonummer, ohne führende Nullen), `upd_ohne_konten` (kein HIUPD);
    `hispa_mit_nicht_sepa` (Konten mit `sepa: false` stehen als
    Nicht-SEPA-Konto in HISPA), `hispa_ohne_bic`.
  - `datum_form` ∈ {None, `zone`, `z`, `zeitpunkt`, `zeitpunkt_dt`}:
    Datumsangaben der camt-Einträge als `2024-06-03+02:00`, `…Z`,
    `<DtTm>…T10:11:12+02:00</DtTm>` bzw. derselbe Zeitpunkt in `<Dt>`;
    `datum_kaputt`/`betrag_kaputt` (Zeichenkette): ersetzt im ersten
    gelieferten Eintrag das Buchungsdatum bzw. den Betrag.
  - `rueckmeldung_zusatz` (Zeichenkette): wird jedem Rückmeldungstext zu
    Segmenten vorangestellt (zusammen höchstens 80 Zeichen; für das
    Diagnoseprotokoll, `bankzugang.md` 5).
- **Störungen** (Steuerung im Test): Verzögerung je Antwort (für
  Zeitüberschreitung), HTTP-Status ≠ 200, Rückmeldung 9380 für bestimmte
  IBANs, unbekanntes Konto 9210, gestoppter Server (Verbindung abgelehnt).
- **Aufzeichnung:** je Nachricht die Segmentarten, ob PIN/TAN vorhanden
  waren und die Produkt-ID (nie die Werte selbst in Fehlermeldungen); damit
  prüfen die Tests „nur lesend“ (3.7).
- Die Attrappe verwendet die Segmentklassen von python-fints; für Tests ist
  `fints` deshalb in `requirements-tests.txt`.

## 7. Vertrag mit dem Mock-Plugin (T 21)

Der Generator liefert zusätzlich eine Mock-Datendatei mit denselben Konten
und Umsätzen (`fixtures/mock/m6_fints_vergleich.json`, `umsatz_id` nach
3.4 für das Profil `camt`). Für jeden Zeitraum liefern `FintsBankPlugin`
gegen die Attrappe und `MockBankPlugin` mit dieser Datei dieselben
`BankKonto`- und `BankUmsatz`-Listen (Konten verglichen nach `iban`
sortiert), dieselben Ausnahmen bei `von > bis` und unbekannter IBAN, und eine
Synchronisation in der App ergibt denselben Buchbestand.
