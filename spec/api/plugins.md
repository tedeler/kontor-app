# Bank- und Mail-Plugins – Meilenstein 1, 2, 4 und 6

Bank- und Mail-Anbindung sind austauschbare Plugins hinter einer festen
Schnittstelle (K 3, T 21). Meilenstein 1 legt die Schnittstellen, die
Mock-Varianten, die Auswahl per Konfiguration und den Mock-Modus fest. Der
Abruf in das Buch (Synchronisation, Dublettenprüfung beim Abruf) und der
TAN-Ablauf sind **Meilenstein 2** (Abschnitt 7 und `synchronisation.md`);
OAuth2, das echte FinTS-Plugin und die TAN-Seite der Oberfläche sind später
(`spec/meilensteine.md`).

## 1. Datenklassen

Alle Datenklassen sind `@dataclass(frozen=True)` und vergleichbar (`==`).

### `kontor.plugins.bank.BankKonto`

| Feld | Typ | Regeln |
| --- | --- | --- |
| `iban` | str | normalisiert (ohne Leerzeichen, Großbuchstaben), prüfziffergültig |
| `bic` | str \| None | |
| `name` | str | Kontobezeichnung |
| `art` | str | `girokonto`, `sparkonto` oder `kreditkonto` |
| `inhaber` | str | |
| `waehrung` | str | immer `"EUR"` |

### `kontor.plugins.bank.BankUmsatz`

| Feld | Typ | Regeln |
| --- | --- | --- |
| `umsatz_id` | str | stabil und eindeutig je Konto über alle Abrufe |
| `iban` | str | Konto, zu dem der Umsatz gehört |
| `buchungstag` | datetime.date | |
| `valuta` | datetime.date \| None | |
| `betrag` | int | ganze Cent, Sicht des Kontos (Eingang positiv, Ausgang negativ) |
| `waehrung` | str | `"EUR"` |
| `gegenpartei_name` | str \| None | |
| `gegenpartei_iban` | str \| None | |
| `verwendungszweck` | str | ggf. `""` |
| `vormerkung` | bool | noch nicht gebuchter (vorgemerkter) Umsatz |
| `storno` | bool | Stornobuchung |

### `kontor.plugins.mail.MailNachricht`

| Feld | Typ | Regeln |
| --- | --- | --- |
| `nachricht_id` | str | eindeutig je Postfach |
| `postfach` | str | Postfachkennung (Adresse) |
| `empfangen` | datetime.datetime | zeitzonenbehaftet, UTC |
| `absender` | str | |
| `betreff` | str | |
| `text` | str | Klartextinhalt |

## 2. Schnittstellen

```python
# kontor.plugins.bank
class BankPlugin(abc.ABC):
    name: ClassVar[str]        # "mock" | "fints"
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def konten(self) -> list[BankKonto]: ...

    @abc.abstractmethod
    def umsaetze(self, iban: str, von: datetime.date, bis: datetime.date) -> list[BankUmsatz]: ...

    def schliessen(self) -> None: ...   # nicht abstrakt; Vorgabe: tut nichts

# kontor.plugins.mail
class MailPlugin(abc.ABC):
    name: ClassVar[str]        # "mock" | "imap"
    ist_mock: ClassVar[bool]

    @abc.abstractmethod
    def postfaecher(self) -> list[str]: ...

    @abc.abstractmethod
    def nachrichten(self, postfach: str, seit: datetime.datetime) -> list[MailNachricht]: ...

    def schliessen(self) -> None: ...
```

Vertrag (für echte und Mock-Plugins gleich):

- **Nur lesend.** Die Schnittstellen haben genau die abstrakten Methoden
  oben; es gibt keine öffentliche Methode zum Überweisen, Senden, Löschen oder
  Verschieben. Öffentliche Methoden eines Plugins (Namen ohne führenden
  Unterstrich) sind genau: `konten`, `umsaetze`, `schliessen` (Bank) bzw.
  `postfaecher`, `nachrichten`, `schliessen` (Mail) – zusätzlich beim
  Mock-Bank-Plugin `setze_heute`, beim Mock-Mail-Plugin `setze_heute`, ab
  M29 beim echten Bank-Plugin `tan_verfahren` (12; lesend, sendet keinen
  Geschäftsvorfall).
- `umsaetze`: Ergebnis enthält genau die Umsätze des Kontos mit
  `von ≤ buchungstag ≤ bis`, sortiert nach (`buchungstag`, `umsatz_id`).
  `von > bis` → `ValueError`. Unbekannte IBAN → `BankKontoUnbekannt`.
  Die IBAN-Eingabe wird normalisiert (Leerzeichen entfernen, Großbuchstaben).
- `nachrichten`: Nachrichten des Postfachs mit `empfangen ≥ seit`, sortiert
  nach (`empfangen`, `nachricht_id`). `seit` ohne Zeitzone → `ValueError`.
  Unbekanntes Postfach → `PostfachUnbekannt`.
- Fehler werden ausschließlich als Unterklassen von `PluginFehler`
  gemeldet (bzw. `ValueError` bei falschen Argumenten).
- Wiederholte Aufrufe mit gleichen Argumenten liefern gleiche Ergebnisse,
  solange „heute“ gleich bleibt.

## 3. Mock-Plugins

```python
# kontor.plugins.mock_bank
class MockBankPlugin(BankPlugin):
    name = "mock"; ist_mock = True
    def __init__(self, daten: pathlib.Path | None = None, szenario: str = "normal",
                 heute: datetime.date | None = None) -> None: ...
    def setze_heute(self, heute: datetime.date | None) -> None: ...

# kontor.plugins.mock_mail
class MockMailPlugin(MailPlugin):
    name = "mock"; ist_mock = True
    def __init__(self, daten: pathlib.Path | None = None, szenario: str = "normal",
                 heute: datetime.date | None = None) -> None: ...
    def setze_heute(self, heute: datetime.date | None) -> None: ...
```

- `daten`: Mock-Datendatei (Abschnitt 4). None → eingebauter Datensatz.
  Datei nicht vorhanden oder ungültig → `KonfigurationsFehler` (im
  Konstruktor). Unbekanntes `szenario` → `KonfigurationsFehler`.
- `heute`: simuliertes Datum; None → `datetime.date.today()` bei jedem Abruf.
  **Zeitlich fortlaufend:** Es werden nur Umsätze mit `buchungstag ≤ heute`
  bzw. Nachrichten mit `empfangen.date() ≤ heute` (UTC) geliefert; rückt
  `heute` vor (`setze_heute`), erscheinen neue Daten, bereits gelieferte
  bleiben unverändert.
- **Deterministisch:** gleiche Datei, gleiches Szenario, gleiches `heute` →
  gleiche Ergebnisse, unabhängig von Aufrufreihenfolge und Prozess.
- **Keine Netzwerkverbindungen** (keine Sockets, kein DNS) – weder im
  Konstruktor noch bei Abrufen.
- Ausgabe ist eine exakte Abbildung der Datendatei: Felder 1:1, Datumswerte
  aus `YYYY-MM-DD`, Zeitstempel aus ISO 8601 mit `Z`.

### Szenarien

| Szenario | Bank-Mock | Mail-Mock |
| --- | --- | --- |
| `normal` | liefert Daten | liefert Daten |
| `bankfehler` | `konten()` und `umsaetze()` werfen `BankVerbindungsFehler` | normal |
| `zeitueberschreitung` | `konten()` und `umsaetze()` werfen `BankZeitueberschreitung` | normal |
| `tan_erforderlich` | `konten()` normal; `umsaetze()` wirft `TanErforderlich` (`anforderung_id` nicht leer, `gueltig_bis` = `heute` 23:59:59 UTC) | normal |
| `token_ablauf` | normal | `postfaecher()` und `nachrichten()` werfen `MailTokenAbgelaufen` |

Ab M4 zusätzlich: `beitragsaenderung` (Abschnitt 8, Split-Vorlagen).

### Eingebauter Datensatz

Ohne `daten` muss der Mock einen eingebauten synthetischen Datensatz liefern
mit mindestens einem `girokonto` und einem `sparkonto` (prüfziffergültige
IBANs mit Bankleitzahl `00000000`, also offensichtlich fiktiv), mindestens
einem Umsatz je Konto im Jahr vor `heute`, und mindestens zwei Postfächern
mit Adressen unter `example.invalid` und mindestens einer Nachricht. Inhalt
sonst frei, aber deterministisch.

## 4. Mock-Datendatei (`kontor-mock-daten`, Version 1)

UTF-8-JSON. Der Testdatengenerator erzeugt solche Dateien
(`fixtures/mock/mock_daten.json`).

```json
{
  "format": "kontor-mock-daten",
  "version": 1,
  "bank": {
    "konten": [
      {"iban": "DE..", "bic": "TESTDEFFXXX", "name": "Girokonto", "art": "girokonto",
       "inhaber": "Erika Mustermann", "waehrung": "EUR"}
    ],
    "umsaetze": [
      {"umsatz_id": "U-000001", "iban": "DE..", "buchungstag": "2024-01-02",
       "valuta": "2024-01-02", "betrag": -1234, "waehrung": "EUR",
       "gegenpartei_name": "Supermarkt", "gegenpartei_iban": null,
       "verwendungszweck": "Einkauf", "vormerkung": false, "storno": false}
    ]
  },
  "mail": {
    "postfaecher": ["haushalt.eins@example.invalid"],
    "nachrichten": [
      {"nachricht_id": "M-000001", "postfach": "haushalt.eins@example.invalid",
       "empfangen": "2024-01-02T08:15:00Z", "absender": "shop@example.invalid",
       "betreff": "Ihre Bestellung", "text": "..."}
    ]
  }
}
```

Alle gezeigten Schlüssel sind Pflicht; `bic`, `valuta`, `gegenpartei_name`,
`gegenpartei_iban` dürfen `null` sein. Unbekannte zusätzliche Schlüssel werden
ignoriert. `format` ≠ `kontor-mock-daten` oder `version` ≠ 1 → ungültig.

## 5. Auswahl per Konfiguration

| Schlüssel (`KontorConfig`) | Umgebungsvariable | Werte |
| --- | --- | --- |
| `bank_plugin` | `KONTOR_BANK_PLUGIN` | `mock`, `fints` |
| `mail_plugin` | `KONTOR_MAIL_PLUGIN` | `mock`, `imap` |
| `mock_modus` | `KONTOR_MOCK_MODUS` | siehe `python-api.md` |
| `mock_szenario` | `KONTOR_MOCK_SZENARIO` | Szenarien oben |
| `mock_daten` | `KONTOR_MOCK_DATEN` | Pfad |
| `mock_heute` | `KONTOR_MOCK_HEUTE` | `YYYY-MM-DD` |
| `mock_datenbank` | `KONTOR_MOCK_DATENBANK` | Pfad |

`kontor.plugins.erzeuge_bank_plugin(config)`:

- `bank_plugin == "mock"` → `MockBankPlugin(config.mock_daten, config.mock_szenario, config.mock_heute)`.
- `bank_plugin == "fints"` → Instanz einer `BankPlugin`-Unterklasse mit
  `name == "fints"`, `ist_mock == False`. In Meilenstein 1 darf sie bei
  `konten()`/`umsaetze()` `PluginNichtVerfuegbar` werfen; die Erzeugung selbst
  baut keine Verbindung auf und wirft nicht.

`erzeuge_mail_plugin(config)` entsprechend mit `"mock"` → `MockMailPlugin`
und `"imap"` (`name == "imap"`).

## 6. Mock-Modus

- Aktiviert über `KontorConfig.mock_modus` / `KONTOR_MOCK_MODUS`.
- **Eigene Datenbank:** Die App und der Import arbeiten ausschließlich auf
  `config.aktive_datenbank` (= Mock-Datenbank). Die Echt-Datenbank wird
  weder angelegt noch geöffnet noch verändert – und umgekehrt im Echtmodus
  die Mock-Datenbank nicht.
- Nur Mock-Plugins sind erlaubt (sonst `KonfigurationsFehler`, siehe
  `python-api.md`).

### Sichtbarer Hinweis

- **API:** `GET /api/status` liefert `modus = "mock"`, `mock = true` und einen
  nicht leeren `hinweis`, der das Wort „Mock“ enthält. Im Echtmodus `modus =
  "echt"`, `mock = false`, `hinweis = null`. Zusätzlich trägt **jede** Antwort
  unter `/api/` den Header `X-Kontor-Modus: mock` bzw. `X-Kontor-Modus: echt`.
- **Oberfläche:** `GET /` liefert `text/html` (Status 200). Im Mock-Modus
  enthält bereits das ausgelieferte HTML (ohne JavaScript-Ausführung) ein
  Element mit `id="mock-hinweis"`, dessen Text „Mock-Modus“ enthält und das
  ohne Interaktion sichtbar ist (kein `hidden`, kein `display:none`). Im
  Echtmodus enthält das HTML die Zeichenkette `mock-hinweis` nicht.

## 7. Meilenstein 2: TAN, PIN und Mock-Erweiterungen

Rückwärtskompatible Erweiterungen (E-029). Die Menge der öffentlichen
Methoden (Abschnitt 2) bleibt unverändert; TAN und PIN werden über ein
Schlüsselwortargument bzw. den Konstruktor übergeben (E-036, E-037).

### 7.1 Schnittstelle

```python
# kontor.plugins.bank
@dataclass(frozen=True)
class TanAntwort:
    anforderung_id: str
    tan: str = field(repr=False)      # repr() enthält die TAN nie

class BankPlugin(abc.ABC):
    @abc.abstractmethod
    def umsaetze(self, iban: str, von: datetime.date, bis: datetime.date,
                 *, tan: TanAntwort | None = None) -> list[BankUmsatz]: ...
```

- `tan` ist nur nach einem `TanErforderlich` sinnvoll: Die App übergibt die
  vom Benutzer eingegebene TAN zusammen mit `TanErforderlich.anforderung_id`
  an **dieselbe Plugin-Instanz**. Nach erfolgreicher Freigabe darf das
  Plugin weitere Abrufe ohne `tan` beantworten (Sitzung freigegeben).
- `TanErforderlich` hat zusätzlich zu `anforderung_id` und `gueltig_bis`
  die Instanzattribute `challenge: str` (nicht leer, Anweisungstext),
  `bild: bytes | None` (z. B. QR-Code) und `bild_mime_typ: str | None`
  (gesetzt genau dann, wenn `bild` gesetzt ist).
- Neue Fehlerklassen (`python-api.md` 8.1): `TanUngueltig` (TAN oder
  `anforderung_id` falsch; die Anforderung bleibt gültig), `TanAbgelaufen`,
  `BankPinFehlt` (PIN wird benötigt, aber `pin_quelle` liefert keine),
  `BankPinFalsch`. Meldungen und `details` enthalten nie PIN oder TAN.

```python
# kontor.plugins
def erzeuge_bank_plugin(config: KontorConfig, *,
                        pin_quelle: Callable[[], str | None] | None = None) -> BankPlugin: ...
```

`pin_quelle` wird vom Plugin bei Bedarf aufgerufen (nicht beim Erzeugen) und
liefert die aktuelle PIN oder None. Das Plugin speichert die PIN nicht
dauerhaft und gibt sie nie aus.

### 7.2 Mock-Bank-Plugin

```python
class MockBankPlugin(BankPlugin):
    def __init__(self, daten: pathlib.Path | None = None, szenario: str = "normal",
                 heute: datetime.date | None = None, *,
                 pin_quelle: Callable[[], str | None] | None = None) -> None: ...
```

`erzeuge_bank_plugin` reicht `pin_quelle` an das Mock-Plugin weiter.

**Mock-Datendatei, zusätzliche optionale Schlüssel** (Format und Version
bleiben `kontor-mock-daten`/1; Plugins aus M1 ignorieren sie):

| Schlüssel | Typ | Bedeutung |
| --- | --- | --- |
| `bank.pin` | str | Ist er vorhanden, verlangt das Mock-Plugin bei **jedem** Aufruf von `konten()` und `umsaetze()` diese PIN über `pin_quelle`: keine `pin_quelle` oder Ergebnis None → `BankPinFehlt`; anderer Wert → `BankPinFalsch`. Fehlt der Schlüssel (und beim eingebauten Datensatz), wird keine PIN verlangt. |
| `bank.tan` | str | Richtige TAN im Szenario `tan_erforderlich`. Fehlt der Schlüssel: `"123456"`. |

Prüfreihenfolge in `umsaetze()`: PIN → Szenario-Fehler (`bankfehler`,
`zeitueberschreitung`) → Argumente (`von > bis`, IBAN) → TAN → Daten.
In `konten()`: PIN → Szenario-Fehler → Daten.

**Szenario `tan_erforderlich`** (ergänzt Abschnitt 3):

- Jede Instanz hat eine *Freigabe* (anfangs keine). Ist die Instanz für
  das aktuelle `heute` freigegeben, liefert `umsaetze()` die Daten.
- Sonst ohne `tan` → `TanErforderlich` mit `anforderung_id =
  "MOCK-TAN-" + heute.isoformat()`, `gueltig_bis` = `heute` 23:59:59 UTC
  (wie M1), nicht leerem `challenge`, `bild` = ein gültiges PNG (beginnt
  mit `89 50 4E 47 0D 0A 1A 0A`, erster Chunk `IHDR`; Inhalt frei, aber
  nur von `anforderung_id` abhängig und damit deterministisch),
  `bild_mime_typ = "image/png"`.
- Mit `tan`: Stimmen `tan.anforderung_id` mit der aktuellen
  `anforderung_id` und `tan.tan` mit der richtigen TAN (`bank.tan`) überein,
  wird die Instanz für `heute` freigegeben und liefert die Daten; sonst
  `TanUngueltig`.
- Rückt `heute` vor (`setze_heute`), ist die Freigabe erloschen.
- In allen anderen Szenarien wird `tan` ignoriert.

Alles Übrige aus Abschnitt 3 (Determinismus, keine Netzwerkverbindungen,
zeitlich fortlaufend) gilt unverändert.

### 7.3 Echtes FinTS-Plugin in M2

Wie E-017: erzeugbar ohne Verbindung, Abrufe dürfen `PluginNichtVerfuegbar`
werfen. Die Synchronisation behandelt das wie jeden Pluginfehler
(`synchronisation.md` 6). Das echte Plugin folgt in M6.

## 8. Meilenstein 4: Szenario `beitragsaenderung`

Rückwärtskompatibel (E-029): Schnittstellen, öffentliche Methoden und das
Dateiformat (`kontor-mock-daten`, Version 1) bleiben unverändert.

| Szenario | Bank-Mock | Mail-Mock |
| --- | --- | --- |
| `beitragsaenderung` | wie `normal`; Umsätze mit dem optionalen Schlüssel `betrag_beitragsaenderung` werden mit diesem Betrag geliefert | normal |

- Optionaler Schlüssel je Eintrag in `bank.umsaetze`:
  `betrag_beitragsaenderung` (int, Cent, Bereich wie `datenmodell.md` 1;
  anderer Typ → Datei ungültig, `KonfigurationsFehler`). In allen anderen
  Szenarien wird er ignoriert.
- `KontorConfig.mock_szenario`, `KONTOR_MOCK_SZENARIO` und `MockBankPlugin`
  akzeptieren den Wert `"beitragsaenderung"`; `GET /api/status` meldet ihn in
  `mock_szenario`.
- Determinismus, zeitlich fortlaufende Lieferung, Netzfreiheit und die
  Prüfreihenfolge aus 7.2 (PIN → Szenario-Fehler → Argumente → TAN → Daten)
  gelten unverändert; das Szenario hat keine Szenario-Fehler.
- Fachlicher Zweck: Split-Vorlagen (`vorlagen.md` 7).

## 9. Meilenstein 6: Echte Plugins und Benachrichtigungs-Plugin

Rückwärtskompatibel (E-029): Schnittstellen, Datenklassen und Mock-Plugins
bleiben unverändert. Neu:

| Plugin | Klasse | Spezifikation |
| --- | --- | --- |
| Bank `fints` | `kontor.plugins.fints.FintsBankPlugin` | `fints.md` 3 |
| Mail `imap` | `kontor.plugins.imap.ImapMailPlugin` | `mail.md` 3 |
| Benachrichtigung `mock`, `ntfy` | `MockBenachrichtigungsPlugin`, `NtfyPlugin` | `benachrichtigungen.md` 2 |

- E-017 gilt weiter für **unkonfigurierte** echte Plugins (Abrufe werfen
  `PluginNichtVerfuegbar` ohne Verbindung). Konfigurierte echte Plugins
  verbinden sich nur mit den konfigurierten Endpunkten (`geheimnisse.md` 7).
- **Vertragstests (T 21):** Echte Plugins gegen die lokalen Attrappen und
  Mock-Plugins mit gleichwertigen Mock-Daten liefern dieselben Ergebnisse,
  dieselbe Sortierung und dieselben Ausnahmen für falsche Argumente
  (`fints.md` 7, `mail.md` 9, `benachrichtigungen.md` 2). Die öffentlichen
  Methoden echter Plugins sind genau die der Schnittstelle (2).
- Im Mock-Modus baut weiterhin kein Bank- oder Mail-Plugin eine Verbindung
  auf; nur das Benachrichtigungs-Plugin `ntfy` darf dort senden (E-119).

## 10. Meilenstein 10: AqBanking-Plugin – entfallen

Mit Meilenstein 29 entfallen (E-259). `BankPlugin.name` ∈ {`mock`, `fints`}.

## 11. Meilenstein 11: Saldo

`umsaetze()` aller Bank-Plugins liefert eine `Umsatzliste` (Unterklasse von
`list`) mit dem Attribut `saldo: BankSaldo | None` (`kontostand.md` 1). Es
gibt keine neue öffentliche Methode. Mock: optionaler Datenschlüssel
`bank.anfangssalden` (`kontostand.md` 1.1); ohne ihn ist `saldo` wie bisher
None. FinTS: `HKSAL` im Dialog des Umsatzabrufs, wenn angeboten (1.2).
(Der AqBanking-Teil ist mit M29 entfallen, E-260.)

## 12. Meilenstein 29: FinTS/camt und TAN-Verfahren

Übernahme der Definition „Bankabruf über FinTS/camt und Bankzugang in der
Oberfläche“ (E-258, E-261). Das Mock-Plugin bleibt unverändert.

- Es gibt nur noch die Bank-Plugins `mock` und `fints`.
- Öffentliche Methoden des echten Bank-Plugins: `konten`, `umsaetze`,
  `schliessen`, `tan_verfahren`. `tan_verfahren()` liefert die erlaubten
  Zwei-Schritt-Verfahren als Liste von Paaren (Sicherheitsfunktion, Name),
  `fints.md` 3.0. Die abstrakte Schnittstelle `BankPlugin` (2) bleibt gleich.
- `konten()` des echten Bank-Plugins nimmt wahlweise `tan: TanAntwort | None`
  als Schlüsselwortargument entgegen und darf `TanErforderlich` werfen
  (TAN bei der Anmeldung, `fints.md` 3.5a). Das Mock-Plugin wirft bei
  `konten()` weiterhin nie `TanErforderlich`.
- Unvollständig konfiguriert werfen `konten`, `umsaetze` und `tan_verfahren`
  `PluginNichtVerfuegbar` ohne Verbindung (E-017); die Meldung verweist auf
  die Einstellungen der Oberfläche.
