# Python-Schnittstelle – Meilenstein 1 bis 20

Verbindlich für die Implementierung (Repository kontor-app) und die Tests
(dieses Repository). Die Tests greifen **nur** über die hier genannten Namen
und über die REST-API (`openapi.yaml`) auf die Anwendung zu.

Fachliche Operationen (Konten, Buchungen, Tags, Filter, Mehrfachbearbeitung,
Dubletten) sind ausschließlich über REST spezifiziert. Die Python-Schnittstelle
umfasst nur, was REST nicht abdecken kann oder soll: Paket, Konfiguration,
App-Fabrik, Import aus einer Datei, Plugins, Fehlerklassen.

## 1. Paket

- pip-Distributionsname: **`kontor`**; Importname: **`kontor`**.
- Installierbar mit `pip install -e <pfad-zu-kontor-app>` (ein
  `pyproject.toml` im Wurzelverzeichnis von kontor-app).
- Python ≥ 3.11. Laufzeitabhängigkeiten wählt die Implementierung frei; sie
  müssen per pip installierbar sein.
- `kontor.__version__: str` – Versionszeichenkette (PEP 440).
  Ab Meilenstein 13 im Schema `MAJOR.MINOR` nach `version.md` 1.1
  (`^(0|[1-9][0-9]*)\.([0-9]{2}|[1-9][0-9]{2,})$`, z. B. `0.01`, `1.00`,
  `0.100`; vor dem ersten Release `0.00`), PEP-440-gültig und dieselbe
  Zeichenkette wie `version` in `GET /api/status`, `GET /api/gesundheit` und
  `GET /api/version` sowie `app_version` im Manifest einer Sicherung
  (`version.md` 1.4, E-177).

Alle unten genannten Module müssen existieren und die genannten Namen
exportieren. Zusätzliche Module/Namen sind erlaubt.

## 2. Fehlerklassen – `kontor.fehler`

```python
class KontorFehler(Exception):
    code: str                      # Klassenattribut, maschinenlesbarer Code
    def __init__(self, meldung: str = "", **details: object) -> None: ...
    meldung: str                   # Instanzattribut, deutscher Text
    details: dict[str, object]     # Instanzattribut, zusätzliche Angaben

class KonfigurationsFehler(KontorFehler):      code = "konfiguration_ungueltig"

class PluginFehler(KontorFehler):              code = "plugin_fehler"
class PluginNichtVerfuegbar(PluginFehler):     code = "plugin_nicht_verfuegbar"

class BankFehler(PluginFehler):                code = "bank_fehler"
class BankVerbindungsFehler(BankFehler):       code = "bank_verbindung"
class BankZeitueberschreitung(BankFehler):     code = "bank_zeitueberschreitung"
class BankKontoUnbekannt(BankFehler):          code = "bank_konto_unbekannt"
class TanErforderlich(BankFehler):             code = "tan_erforderlich"
    # zusätzliche Instanzattribute:
    #   anforderung_id: str
    #   gueltig_bis: datetime.datetime   (zeitzonenbehaftet, UTC)

class MailFehler(PluginFehler):                code = "mail_fehler"
class MailVerbindungsFehler(MailFehler):       code = "mail_verbindung"
class MailTokenAbgelaufen(MailFehler):         code = "mail_token_abgelaufen"
class PostfachUnbekannt(MailFehler):           code = "mail_postfach_unbekannt"
```

`str(fehler)` liefert `meldung`. Fehlermeldungen enthalten nie Geheimnisse
(PIN, Tokens).

## 3. Konfiguration – `kontor.config`

```python
@dataclass(frozen=True)
class KontorConfig:
    datenbank: pathlib.Path
    mock_modus: bool = False
    mock_datenbank: pathlib.Path | None = None
    bank_plugin: str | None = None
    mail_plugin: str | None = None
    mock_szenario: str = "normal"
    mock_daten: pathlib.Path | None = None
    mock_heute: datetime.date | None = None

    @property
    def aktive_datenbank(self) -> pathlib.Path: ...

    @classmethod
    def from_env(cls, umgebung: Mapping[str, str] | None = None) -> "KontorConfig": ...
```

Felder:

| Feld | Bedeutung |
| --- | --- |
| `datenbank` | Pfad der SQLite-Datenbank für **Echtdaten**. `str` wird in `Path` umgewandelt. |
| `mock_modus` | Mock-Modus an/aus (siehe `plugins.md`). |
| `mock_datenbank` | Pfad der Mock-Datenbank. Vorgabe (None): `datenbank.with_name(datenbank.stem + "-mock" + datenbank.suffix)`, z. B. `kontor.sqlite3` → `kontor-mock.sqlite3`. |
| `bank_plugin` | `"mock"` oder `"fints"`. None → `"mock"` im Mock-Modus, sonst `"fints"`. Ab M29 gibt es keine weiteren Werte (`"aqbanking"` → `KonfigurationsFehler`, 21.1). |
| `mail_plugin` | `"mock"` oder `"imap"`. None → `"mock"` im Mock-Modus, sonst `"imap"`. |
| `mock_szenario` | `"normal"`, `"bankfehler"`, `"zeitueberschreitung"`, `"tan_erforderlich"`, `"token_ablauf"` (siehe `plugins.md`). |
| `mock_daten` | Pfad einer Mock-Datendatei (Format in `plugins.md`); None → eingebauter Datensatz. |
| `mock_heute` | Simuliertes „heute“ für Mock-Plugins; None → `datetime.date.today()` zum Zeitpunkt jedes Abrufs. |

Verhalten:

- Nach der Konstruktion sind `bank_plugin` und `mail_plugin` nie None
  (Vorgabe eingesetzt), `datenbank`, `mock_datenbank` (falls gesetzt) und
  `mock_daten` (falls gesetzt) sind `Path`.
- `aktive_datenbank`: im Mock-Modus die (ggf. vorgegebene) Mock-Datenbank,
  sonst `datenbank`.
- Die Konstruktion wirft `KonfigurationsFehler`, wenn
  - `bank_plugin` ∉ {`mock`, `fints`} oder `mail_plugin` ∉ {`mock`, `imap`};
  - `mock_modus` wahr ist und ein Plugin nicht `"mock"` ist;
  - `mock_modus` falsch ist und ein Plugin `"mock"` ist (Mock-Daten dürfen nie
    in die Echt-Datenbank gelangen);
  - `mock_szenario` unbekannt ist;
  - im Mock-Modus die Mock-Datenbank auf dieselbe Datei wie `datenbank`
    zeigt (Vergleich nach `Path.resolve()`).
- Die Konstruktion legt keine Dateien an und baut keine Verbindungen auf.

`from_env(umgebung)` liest aus `umgebung` (None → `os.environ`):

| Variable | Feld | Format |
| --- | --- | --- |
| `KONTOR_DATENBANK` | `datenbank` | Pfad; **Pflicht**, fehlt/leer → `KonfigurationsFehler` |
| `KONTOR_MOCK_MODUS` | `mock_modus` | `1`, `true`, `ja`, `yes`, `on` → wahr; `0`, `false`, `nein`, `no`, `off`, leer/fehlend → falsch (Groß-/Kleinschreibung egal); sonst `KonfigurationsFehler` |
| `KONTOR_MOCK_DATENBANK` | `mock_datenbank` | Pfad; leer/fehlend → None |
| `KONTOR_BANK_PLUGIN` | `bank_plugin` | leer/fehlend → None |
| `KONTOR_MAIL_PLUGIN` | `mail_plugin` | leer/fehlend → None |
| `KONTOR_MOCK_SZENARIO` | `mock_szenario` | leer/fehlend → `normal` |
| `KONTOR_MOCK_DATEN` | `mock_daten` | Pfad; leer/fehlend → None |
| `KONTOR_MOCK_HEUTE` | `mock_heute` | `YYYY-MM-DD`; leer/fehlend → None; ungültig → `KonfigurationsFehler` |

## 4. App-Fabrik – `kontor.app`

```python
def create_app(config: KontorConfig | None = None) -> fastapi.FastAPI: ...
```

- `config=None` → `KontorConfig.from_env()`.
- Öffnet bzw. erzeugt die SQLite-Datei `config.aktive_datenbank` und legt
  das Schema an, **bevor** `create_app` zurückkehrt (Tests verwenden
  `fastapi.testclient.TestClient(app)` auch ohne Kontextmanager). Fehlende
  Elternverzeichnisse werden angelegt. Die jeweils andere Datenbank
  (Echt bzw. Mock) wird weder angelegt noch geöffnet.
- Mehrere Apps mit verschiedenen Konfigurationen im selben Prozess sind
  voneinander unabhängig (kein globaler Zustand außer Caches ohne
  fachliche Wirkung).
- Bindet alle Endpunkte aus `openapi.yaml` unter den dort genannten Pfaden ein
  sowie `GET /` (Weboberfläche, siehe `plugins.md` „Mock-Hinweis“).
- Baut keine Netzwerkverbindungen auf und erzeugt Plugins frühestens bei
  Bedarf.
- Start im Betrieb z. B.: `uvicorn --factory kontor.app:create_app`.

## 5. KMyMoney-Import – `kontor.importer.kmymoney`

```python
def importiere_kmy(
    config: KontorConfig,
    quelle: str | os.PathLike[str] | bytes,
    *,
    dateiname: str | None = None,
) -> ImportErgebnis: ...
```

- `quelle`: Pfad einer Datei oder die Bytes selbst. `dateiname` wird im
  Importvorgang gespeichert; bei Pfadangabe und `dateiname=None` wird der
  Dateiname des Pfads (`Path(quelle).name`) verwendet.
- Arbeitet auf `config.aktive_datenbank` (legt sie samt Schema an, falls
  nötig) – also auf genau derselben Datenbank wie eine mit derselben
  Konfiguration erzeugte App. Eine gleichzeitig laufende App sieht das
  Ergebnis sofort.
- Verhalten exakt wie in `datenmodell.md` Abschnitt 10; identisch mit
  `POST /api/import/kmymoney`.
- Inhaltliche/Formatfehler der Datei werden **nicht** als Ausnahme gemeldet,
  sondern über `ImportErgebnis.erfolgreich = False` und `fehler`. Ausnahmen
  nur bei Programmierfehlern bzw. Umgebung: `FileNotFoundError` (Pfad
  existiert nicht), `TypeError` (falscher Typ von `quelle`).
- Atomar: Entweder alles oder nichts wird geschrieben (eine Transaktion).

### `kontor.importer.ergebnis`

```python
@dataclass(frozen=True)
class ImportMeldung:
    code: str
    meldung: str
    referenz: str | None = None

@dataclass(frozen=True)
class ImportErgebnis:
    erfolgreich: bool
    format: str | None                 # "kmy-gzip" | "kmy-xml" | None
    konten_neu: int
    konten_vorhanden: int
    kategorien_neu: int
    kategorien_vorhanden: int
    empfaenger_neu: int
    empfaenger_vorhanden: int
    tags_neu: int
    tags_vorhanden: int
    buchungen_neu: int
    buchungen_vorhanden: int
    buchungen_zusammengefuehrt: int
    buchungen_zur_pruefung: int
    buchungen_uebersprungen: int
    splits_neu: int
    warnungen: tuple[ImportMeldung, ...]
    fehler: tuple[ImportMeldung, ...]
    import_id: int | None

    def als_dict(self) -> dict[str, object]: ...
```

`als_dict()` liefert genau das JSON-Objekt des Schemas `ImportErgebnis` aus
`openapi.yaml` (Listen statt Tupel, Meldungen als Dicts mit den Schlüsseln
`code`, `meldung`, `referenz`). `kontor.importer.kmymoney` re-exportiert
`ImportErgebnis` und `ImportMeldung`.

## 6. Plugins – `kontor.plugins`

Schnittstellen, Datenklassen und Verhalten: `plugins.md`. Modulpfade:

| Name | Modul |
| --- | --- |
| `BankPlugin`, `BankKonto`, `BankUmsatz` | `kontor.plugins.bank` |
| `MailPlugin`, `MailNachricht` | `kontor.plugins.mail` |
| `MockBankPlugin` | `kontor.plugins.mock_bank` |
| `MockMailPlugin` | `kontor.plugins.mock_mail` |
| `erzeuge_bank_plugin`, `erzeuge_mail_plugin` | `kontor.plugins` |

```python
def erzeuge_bank_plugin(config: KontorConfig) -> BankPlugin: ...
def erzeuge_mail_plugin(config: KontorConfig) -> MailPlugin: ...
```

## 7. Was die Tests nicht voraussetzen

Interne Module, Datenbankschema, ORM, Logging, Struktur der Weboberfläche
(außer Mock-Hinweis) sind frei.

## 8. Meilenstein 2: Ergänzungen

Rückwärtskompatibel (E-029): Alles aus 1–6 gilt unverändert.

### 8.1 Fehlerklassen – `kontor.fehler`

```python
class BankPinFehlt(BankFehler):       code = "bank_pin_fehlt"
class BankPinFalsch(BankFehler):      code = "bank_pin_falsch"
class TanUngueltig(BankFehler):       code = "tan_ungueltig"
class TanAbgelaufen(BankFehler):      code = "tan_abgelaufen"
```

`TanErforderlich` hat zusätzlich die Instanzattribute `challenge: str`,
`bild: bytes | None`, `bild_mime_typ: str | None` (`plugins.md` 7.1).

### 8.2 Konfiguration – `KontorConfig`, zusätzliche Felder

| Feld | Typ, Vorgabe | Bedeutung | Umgebungsvariable |
| --- | --- | --- | --- |
| `sync_intervall_minuten` | int, `0` | Abstand automatischer Läufe; 0 = kein automatischer Abruf | `KONTOR_SYNC_INTERVALL_MINUTEN` |
| `sync_wiederholung_minuten` | int, `30` | Abstand bis zum nächsten automatischen Versuch nach einem fehlgeschlagenen Lauf | `KONTOR_SYNC_WIEDERHOLUNG_MINUTEN` |
| `sync_erstabruf_tage` | int, `90` | Zeitraum des ersten Abrufs eines Kontos | `KONTOR_SYNC_ERSTABRUF_TAGE` |
| `sync_ueberlappung_tage` | int, `14` | Überlappung folgender Abrufe | `KONTOR_SYNC_UEBERLAPPUNG_TAGE` |
| `planer_starten` | bool, `True` | Hintergrund-Thread des Planers starten (nur wirksam bei `sync_intervall_minuten > 0`) | `KONTOR_PLANER_STARTEN` |

- Ganzzahlen müssen `int` sein (nicht `bool`) mit `sync_intervall_minuten ≥
  0`, `sync_wiederholung_minuten ≥ 1`, `sync_erstabruf_tage ≥ 0`,
  `sync_ueberlappung_tage ≥ 0`; `planer_starten` muss `bool` sein. Sonst
  `KonfigurationsFehler`.
- `from_env`: Ganzzahlen als Dezimalziffern (leer/fehlend → Vorgabe;
  anderes → `KonfigurationsFehler`); `KONTOR_PLANER_STARTEN` wie
  `KONTOR_MOCK_MODUS` (leer/fehlend → `True`).
- Weiterhin gilt: Die Konstruktion legt nichts an und baut keine
  Verbindungen auf.

### 8.3 Planer – `kontor.sync`

```python
def planer_takt(app: fastapi.FastAPI) -> dict | None: ...
```

- `app` ist eine von `create_app` erzeugte Anwendung.
- Führt genau einen Planer-Takt aus (`synchronisation.md` 9): prüft
  TAN-Abläufe und startet, falls fällig, einen Lauf mit `ausloeser =
  "planer"`. Rückgabe: das JSON-Objekt des gestarteten Laufs (Schema
  `SyncLauf`, wie es `GET /api/sync/laeufe/{id}` liefert) oder `None`.
- Synchron, ohne Thread; dieselbe Wirkung wie ein Takt des
  Hintergrund-Threads. Damit sind Planer-Tests deterministisch.

### 8.4 Plugins

- `erzeuge_bank_plugin(config, *, pin_quelle=None)` und
  `MockBankPlugin(…, *, pin_quelle=None)`, `TanAntwort` in
  `kontor.plugins.bank`: `plugins.md` 7.
- `create_app` erzeugt das Bank-Plugin frühestens beim ersten Lauf und
  verwendet danach dieselbe Instanz für alle Läufe der App (nötig für die
  TAN-Freigabe, `plugins.md` 7.1).

## 9. Meilenstein 3: Ergänzungen

Rückwärtskompatibel (E-029): Alles aus 1–8 gilt unverändert. Keine neuen
Module und keine neuen Fehlerklassen.

### 9.1 Konfiguration – `KontorConfig`, zusätzliche Felder

| Feld | Typ, Vorgabe | Bedeutung | Umgebungsvariable |
| --- | --- | --- | --- |
| `umbuchung_automatisch` | bool, `False` | Umbuchungen nach jeder Kontoverarbeitung der Synchronisation automatisch erkennen und zusammenführen (`buchhaltungspflege.md` 4.4) | `KONTOR_UMBUCHUNG_AUTOMATISCH` |
| `umbuchung_fenster_tage` | int, `3` | größter Datumsabstand zweier Seiten einer Umbuchung (`buchhaltungspflege.md` 4.2) | `KONTOR_UMBUCHUNG_FENSTER_TAGE` |

- `umbuchung_automatisch` muss `bool` sein; `umbuchung_fenster_tage` muss
  `int` (nicht `bool`) mit Wert 0–366 sein. Sonst `KonfigurationsFehler`.
- `from_env`: `KONTOR_UMBUCHUNG_AUTOMATISCH` wie `KONTOR_MOCK_MODUS`
  (leer/fehlend → `False`); `KONTOR_UMBUCHUNG_FENSTER_TAGE` als
  Dezimalziffern (leer/fehlend → 3; anderes oder > 366 →
  `KonfigurationsFehler`).
- Für den Betrieb wird `KONTOR_UMBUCHUNG_AUTOMATISCH=1` empfohlen; die
  Vorgabe `False` hält das Verhalten von M2 (E-054).

### 9.2 Protokoll außerhalb von REST

- `importiere_kmy` erzeugt bei einem erfolgreichen Import mit Wirkung
  dieselbe Änderung wie `POST /api/import/kmymoney` (`protokoll.md` 4.2);
  `zeitpunkt` ist dann die Systemzeit (UTC, ohne Sekundenbruchteile), im
  Mock-Modus mit gesetztem `mock_heute` dessen 12:00:00Z.
- `kontor.sync.planer_takt(app)` protokolliert einen gestarteten Lauf wie
  `POST /api/sync`.

## 10. Meilenstein 4: Ergänzungen

Rückwärtskompatibel (E-029): Alles aus 1–9 gilt unverändert. Keine neuen
Fehlerklassen.

### 10.1 Konfiguration – `KontorConfig`, zusätzliches Feld

| Feld | Typ, Vorgabe | Bedeutung | Umgebungsvariable |
| --- | --- | --- | --- |
| `lernmodell_automatisch` | bool, `False` | Lernmodell als vierte Stufe bei neuen Buchungen der Synchronisation und bei `erfassen` (`lernmodell.md` 5.1) | `KONTOR_LERNMODELL_AUTOMATISCH` |

- Muss `bool` sein, sonst `KonfigurationsFehler`.
- `from_env`: wie `KONTOR_MOCK_MODUS` (leer/fehlend → `False`).
- `mock_szenario` akzeptiert zusätzlich `"beitragsaenderung"`
  (`plugins.md` 8), ebenso `KONTOR_MOCK_SZENARIO`.
- Für den Betrieb wird `KONTOR_LERNMODELL_AUTOMATISCH=1` empfohlen; die
  Vorgabe `False` hält das Verhalten von M3 (E-072).

### 10.2 GnuCash-Import – `kontor.importer.gnucash`

```python
def importiere_gnucash(
    config: KontorConfig,
    quelle: str | os.PathLike[str] | bytes,
    *,
    dateiname: str | None = None,
) -> ImportErgebnis: ...
```

- Verhalten exakt wie `gnucash.md`; identisch mit `POST /api/import/gnucash`.
  Sonst wie `importiere_kmy` (5): Pfad oder Bytes, `dateiname` aus dem Pfad,
  dieselbe Datenbank wie die App, atomar, Formatfehler nur über
  `ImportErgebnis`, Ausnahmen nur `FileNotFoundError`/`TypeError`.
- `ImportErgebnis.format` ∈ {`"gnc-xml-gzip"`, `"gnc-xml"`, `"gnc-sqlite"`,
  None}. `kontor.importer.gnucash` re-exportiert `ImportErgebnis` und
  `ImportMeldung`.
- Protokoll: wie 9.2 mit `aktion = "import_gnucash"`.

### 10.3 Plugins

`MockBankPlugin(…, szenario="beitragsaenderung")` nach `plugins.md` 8;
`erzeuge_bank_plugin` reicht das Szenario wie bisher durch.

## 11. Meilenstein 9: Ergänzungen (Datensicherung)

Rückwärtskompatibel (E-029): Alles aus 1–10 gilt unverändert. Keine neuen
Fehlerklassen, keine neuen Konfigurationsfelder.

### 11.1 Sicherung erstellen – `kontor.sicherung`

```python
def erstelle_sicherung(config: KontorConfig) -> bytes: ...
```

- Liefert die Bytes einer ZIP-Datei nach `sicherung.md` 3, mit demselben
  Inhalt wie `GET /api/sicherung` einer App mit derselben Konfiguration
  (gleiche `inhalt_sha256`, `modus` nach `config.mock_modus`).
- Arbeitet auf `config.aktive_datenbank` (legt sie samt Schema an, falls
  nötig), liest nur, ändert nichts, erzeugt keine Änderung. Darf laufen,
  während eine App dieselbe Datenbank verwendet (konsistenter
  Schnappschuss).
- `erstellt` ist die Systemzeit (UTC, ohne Sekundenbruchteile), im
  Mock-Modus mit gesetztem `mock_heute` dessen 12:00:00Z (wie 9.2).
- Einspielen ist nur über REST spezifiziert (`POST /api/sicherung/einspielen`).

## 12. Meilenstein 5: Ergänzungen

Rückwärtskompatibel (E-029): Alles aus 1–11 gilt unverändert.

### 12.1 Konfiguration – `KontorConfig`, zusätzliches Feld

| Feld | Typ, Vorgabe | Bedeutung | Umgebungsvariable |
| --- | --- | --- | --- |
| `wiederkehrend_automatisch` | bool, `False` | nach jedem Synchronisationslauf auf unerwartete Buchungen prüfen (`wiederkehrend.md` 5) | `KONTOR_WIEDERKEHREND_AUTOMATISCH` |

- Muss `bool` sein, sonst `KonfigurationsFehler`.
- `from_env`: wie `KONTOR_MOCK_MODUS` (leer/fehlend → `False`; ungültig →
  `KonfigurationsFehler`).
- Für den Betrieb wird `KONTOR_WIEDERKEHREND_AUTOMATISCH=1` empfohlen; die
  Vorgabe `False` hält das Verhalten von M4 (E-100).

### 12.2 Fehlerklasse – `kontor.fehler`

```python
class KreditRateZuKlein(KontorFehler):    code = "kredit_rate_zu_klein"
```

### 12.3 Tilgungsplan – `kontor.kredite`

```python
def tilgungsplan(parameter: Mapping[str, object]) -> dict: ...
```

- `parameter` hat die Schlüssel des Schemas `KreditParameter`
  (`restschuld`, `stand_datum`, `sollzins`, `rate`, `erste_faelligkeit`,
  optional `zinsmethode` (Vorgabe `"30/360"`) und `sondertilgungen`
  (Vorgabe `[]`)); Daten als `datetime.date` **oder** `YYYY-MM-DD`-Text,
  Beträge als `int` (nicht `bool`).
- Rückgabe: genau das JSON-Objekt `Tilgungsplan`, das
  `POST /api/kredite/tilgungsplan` mit denselben Parametern liefert (Daten
  als `YYYY-MM-DD`-Text), nach `kredite.md` 3.
- Ungültige Parameter (wie 422 `validierung`, `kredite.md` 2.1 Schritt 1)
  → `ValueError`; Plan endet nicht innerhalb von 1 200 Raten →
  `KreditRateZuKlein`. Reine Funktion: keine Datenbank, kein Netzwerk.

### 12.4 Protokoll außerhalb von REST

Keine neuen Wege: Kredite, Berichte, Export und die Prüfung wiederkehrender
Buchungen gibt es nur über REST; `kontor.sync.planer_takt(app)` führt nach
einem Lauf die automatische Prüfung wie `POST /api/sync` aus.

## 13. Meilenstein 6: Ergänzungen (echte Anbindungen)

Rückwärtskompatibel (E-029): Alles aus 1–12 gilt unverändert; ohne die
neuen Felder verhält sich jede Instanz wie in M5 (Benachrichtigungs-Plugin
im Echtmodus `keins`, unkonfigurierte echte Plugins werfen
`PluginNichtVerfuegbar` ohne Verbindung). Fachliche Regeln: `fints.md`,
`mail.md`, `benachrichtigungen.md`, `geheimnisse.md`.

### 13.1 Konfiguration – `KontorConfig`, zusätzliche Felder

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `bank_pin_quelle` | str, `"eingabe"` | `KONTOR_BANK_PIN_QUELLE` | `eingabe` \| `systemd-creds` (`fints.md` 5) |
| `credentials_verzeichnis` | Path \| None | `CREDENTIALS_DIRECTORY` (von systemd gesetzt) | Pflicht bei `bank_pin_quelle = "systemd-creds"` |
| `fints_url` | str \| None | `KONTOR_FINTS_URL` | URL nach `geheimnisse.md` 7 |
| `fints_blz` | str \| None | `KONTOR_FINTS_BLZ` | genau 8 Ziffern |
| `fints_benutzer` | str \| None | `KONTOR_FINTS_BENUTZER` | 1–64 Zeichen |
| `fints_kunden_id` | str \| None | `KONTOR_FINTS_KUNDEN_ID` | 1–64 Zeichen; None → `fints_benutzer` |
| `fints_produkt_id` | str \| None | `KONTOR_FINTS_PRODUKT_ID` | 1–25 Zeichen |
| `fints_tan_verfahren` | str \| None | `KONTOR_FINTS_TAN_VERFAHREN` | 3 Ziffern |
| `fints_timeout_sekunden` | int, `30` | `KONTOR_FINTS_TIMEOUT_SEKUNDEN` | 1–600 |
| `imap_host` | str, `"imap.gmail.com"` | `KONTOR_IMAP_HOST` | nicht leer |
| `imap_port` | int, `993` | `KONTOR_IMAP_PORT` | 1–65535 |
| `imap_tls` | bool, `True` | `KONTOR_IMAP_TLS` | `False` nur bei Loopback-Host (`geheimnisse.md` 7) |
| `imap_timeout_sekunden` | int, `30` | `KONTOR_IMAP_TIMEOUT_SEKUNDEN` | 1–600 |
| `oauth_client_id` | str \| None | `KONTOR_OAUTH_CLIENT_ID` | 1–256 Zeichen |
| `oauth_autorisierung_url` | str, `"https://accounts.google.com/o/oauth2/v2/auth"` | `KONTOR_OAUTH_AUTORISIERUNG_URL` | URL |
| `oauth_token_url` | str, `"https://oauth2.googleapis.com/token"` | `KONTOR_OAUTH_TOKEN_URL` | URL |
| `oauth_widerruf_url` | str, `"https://oauth2.googleapis.com/revoke"` | `KONTOR_OAUTH_WIDERRUF_URL` | URL |
| `oauth_redirect_uri` | str, `"http://127.0.0.1/oauth2/rueckruf"` | `KONTOR_OAUTH_REDIRECT_URI` | URL (beliebiger `http`-Host erlaubt) |
| `oauth_timeout_sekunden` | int, `30` | `KONTOR_OAUTH_TIMEOUT_SEKUNDEN` | 1–600 |
| `oauth_refresh_gueltig_stunden` | int, `168` | `KONTOR_OAUTH_REFRESH_GUELTIG_STUNDEN` | 0–87600; 0 = ohne Ablauf (`mail.md` 5.2) |
| `oauth_vorwarnung_stunden` | int, `24` | `KONTOR_OAUTH_VORWARNUNG_STUNDEN` | 0–8760 |
| `mail_intervall_minuten` | int, `0` | `KONTOR_MAIL_INTERVALL_MINUTEN` | ≥ 0; 0 = kein automatischer Abruf |
| `mail_erstabruf_tage` | int, `30` | `KONTOR_MAIL_ERSTABRUF_TAGE` | 0–3650 |
| `mail_ueberlappung_stunden` | int, `24` | `KONTOR_MAIL_UEBERLAPPUNG_STUNDEN` | 0–8760 |
| `benachrichtigung_plugin` | str \| None | `KONTOR_BENACHRICHTIGUNG_PLUGIN` | `keins` \| `mock` \| `ntfy`; None → `mock` im Mock-Modus, sonst `keins` |
| `ntfy_url` | str, `"https://ntfy.sh"` | `KONTOR_NTFY_URL` | URL |
| `ntfy_topic` | str \| None | `KONTOR_NTFY_TOPIC` | `[A-Za-z0-9_-]{1,64}`; Pflicht bei `ntfy` |
| `ntfy_timeout_sekunden` | int, `10` | `KONTOR_NTFY_TIMEOUT_SEKUNDEN` | 1–600 |
| `zustellung_max_versuche` | int, `10` | `KONTOR_ZUSTELLUNG_MAX_VERSUCHE` | 1–1000 |
| `zustellung_wiederholung_minuten` | int, `5` | `KONTOR_ZUSTELLUNG_WIEDERHOLUNG_MINUTEN` | 1–1440 |
| `tan_erinnerung_minuten` | int, `5` | `KONTOR_TAN_ERINNERUNG_MINUTEN` | 0–1440; 0 = keine |
| `tan_erinnerung_anzahl` | int, `3` | `KONTOR_TAN_ERINNERUNG_ANZAHL` | 0–100 |
| `oeffentliche_url` | str \| None | `KONTOR_OEFFENTLICHE_URL` | URL (beliebiger `http`-Host erlaubt) |
| `geheimnis_schluessel_datei` | Path \| None | `KONTOR_GEHEIMNIS_SCHLUESSEL_DATEI` | None → `aktive_datenbank.with_suffix(".schluessel")` (`geheimnisse.md` 2) |
| `tls_ca_datei` | Path \| None | `KONTOR_TLS_CA_DATEI` | PEM-Datei mit Vertrauensankern |

- Ganzzahlen müssen `int` (nicht `bool`) im angegebenen Bereich sein,
  `imap_tls` muss `bool` sein, Zeichenketten `str` in der angegebenen Länge
  (leere Zeichenkette ist ungültig), Pfade werden aus `str` in `Path`
  umgewandelt. Verstöße → `KonfigurationsFehler`.
- Zusätzlich `KonfigurationsFehler`, wenn
  - `bank_pin_quelle = "systemd-creds"` und `credentials_verzeichnis` None;
  - `benachrichtigung_plugin = "mock"` im Echtmodus (Mock-Plugins nur im
    Mock-Modus) oder `"ntfy"` ohne `ntfy_topic`;
  - eine URL gegen `geheimnisse.md` 7 verstößt (kein `http`/`https`, kein
    Host, `http` an einen Nicht-Loopback-Host außer bei `oeffentliche_url`
    und `oauth_redirect_uri`) oder `imap_tls = False` mit
    Nicht-Loopback-`imap_host`.
- Nach der Konstruktion ist `benachrichtigung_plugin` nie None.
- `from_env`: leer/fehlend → Vorgabe bzw. None; Ganzzahlen als
  Dezimalziffern; `KONTOR_IMAP_TLS` wie `KONTOR_MOCK_MODUS` (leer/fehlend →
  `True`); ungültige Werte → `KonfigurationsFehler`.
- Die Konstruktion legt weiterhin nichts an, liest keine Dateien und baut
  keine Verbindungen auf. `repr(config)` enthält keine Geheimnisse (die
  Konfiguration enthält keine).

### 13.2 Fehlerklassen – `kontor.fehler`

```python
class BankZugangGesperrt(BankFehler):          code = "bank_zugang_gesperrt"
class MailTokenWiderrufen(MailFehler):         code = "mail_token_widerrufen"
class MailAnmeldungFehlt(MailFehler):          code = "mail_anmeldung_fehlt"
class MailAnmeldungAbgelehnt(MailFehler):      code = "mail_anmeldung_abgelehnt"
class MailOAuthFehler(MailFehler):             code = "mail_oauth_fehler"
class MailOrdnerUnbekannt(MailFehler):         code = "mail_ordner_unbekannt"
class BenachrichtigungFehler(PluginFehler):    code = "benachrichtigung_fehler"
```

### 13.3 Module und Namen

| Name | Modul |
| --- | --- |
| `FintsBankPlugin` | `kontor.plugins.fints` (`fints.md` 3) |
| `ImapMailPlugin`, `ImapPostfach` | `kontor.plugins.imap` (`mail.md` 3) |
| `BenachrichtigungsPlugin`, `PushNachricht` | `kontor.plugins.benachrichtigung` (`benachrichtigungen.md` 2) |
| `MockBenachrichtigungsPlugin` | `kontor.plugins.mock_benachrichtigung` |
| `NtfyPlugin` | `kontor.plugins.ntfy` |
| `erzeuge_benachrichtigungs_plugin` | `kontor.plugins` |

```python
# kontor.plugins
def erzeuge_bank_plugin(config, *, pin_quelle=None) -> BankPlugin: ...          # unverändert, fints → FintsBankPlugin
def erzeuge_mail_plugin(config, *, postfaecher=(), zugang=None) -> MailPlugin: ...   # imap → ImapMailPlugin
def erzeuge_benachrichtigungs_plugin(config, *, token_quelle=None) -> BenachrichtigungsPlugin | None: ...
```

Die bisherigen Aufrufe ohne Schlüsselwortargumente bleiben gültig.

### 13.4 Planer – `kontor.sync.planer_takt`

Unverändert in Signatur und Rückgabe (der gestartete `SyncLauf` oder
`None`); der Takt umfasst zusätzlich TAN-Erinnerungen, Prüfung der
Mail-Anmeldungen, Mail-Abruf und Zustellung (`synchronisation.md` 18.2).

### 13.5 Sicherung

`kontor.sicherung.erstelle_sicherung` enthält wie `GET /api/sicherung` die
Postfächer (`sicherung.md` 2.6), nie Geheimnisse, Spiegel oder
Betriebszustand der Postfächer.

## 14. Meilenstein 7: Ergänzungen (Sicherheit und Betrieb)

Rückwärtskompatibel (E-029, E-125): Alles aus 1–13 gilt unverändert. Mit den
Vorgaben der neuen Felder (insbesondere `anmeldung = False`,
`erlaubte_netze = None`) verhält sich jede Instanz wie in M6, ergänzt um
Sicherheitsköpfe, Eingabehärtung und Größengrenzen (`sicherheit.md` 6–8).
Fachliche Regeln: `sicherheit.md`, `betrieb.md`, `leistung.md`.

### 14.1 Konfiguration – `KontorConfig`, zusätzliche Felder

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `anmeldung` | bool, `False` | `KONTOR_ANMELDUNG` | Anmeldung einschalten (`sicherheit.md`) |
| `sitzung_leerlauf_sekunden` | int, `86400` | `KONTOR_SITZUNG_LEERLAUF_SEKUNDEN` | 1–31 536 000 |
| `sitzung_hoechstdauer_sekunden` | int, `2592000` | `KONTOR_SITZUNG_HOECHSTDAUER_SEKUNDEN` | 1–31 536 000 |
| `sitzung_cookie_secure` | bool \| None, `None` | `KONTOR_SITZUNG_COOKIE_SECURE` | None = `Secure` nur bei HTTPS-Anfragen |
| `anmeldung_fehlversuche` | int, `5` | `KONTOR_ANMELDUNG_FEHLVERSUCHE` | 1–100 |
| `anmeldung_sperre_sekunden` | int, `60` | `KONTOR_ANMELDUNG_SPERRE_SEKUNDEN` | 1–86 400 |
| `erlaubte_netze` | tuple[str, ...] \| None, `None` | `KONTOR_ERLAUBTE_NETZE` | CIDR-Netze; None = alle (`sicherheit.md` 10) |
| `upload_max_mib` | int, `200` | `KONTOR_UPLOAD_MAX_MIB` | 1–4 096 |
| `anfrage_max_kib` | int, `4096` | `KONTOR_ANFRAGE_MAX_KIB` | 16–1 048 576 |
| `host` | str, `"127.0.0.1"` | `KONTOR_HOST` | nicht leer (`betrieb.md` 2) |
| `port` | int, `8000` | `KONTOR_PORT` | 1–65 535 |
| `log_stufe` | str, `"INFO"` | `KONTOR_LOG_STUFE` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `beenden_frist_sekunden` | int, `20` | `KONTOR_BEENDEN_FRIST_SEKUNDEN` | 1–600 (`betrieb.md` 5.2) |
| `mock_verzoegerung_ms` | int, `0` | `KONTOR_MOCK_VERZOEGERUNG_MS` | 0–60 000; nur im Mock-Modus wirksam (`betrieb.md` 5.4) |

- Ganzzahlen müssen `int` (nicht `bool`) im Bereich sein, `anmeldung` muss
  `bool` sein, `sitzung_cookie_secure` `bool` oder None, `host` und
  `log_stufe` `str`. Verstöße → `KonfigurationsFehler`.
- `erlaubte_netze`: Liste oder Tupel von Zeichenketten; jede muss sich mit
  `ipaddress.ip_network(wert, strict=False)` lesen lassen; nach der
  Konstruktion ein Tupel der kanonischen Schreibweise
  (`str(ip_network(wert, strict=False))`, z. B. `"192.168.1.7/24"` →
  `"192.168.1.0/24"`), Reihenfolge wie angegeben. Eine leere Liste,
  ungültige Einträge oder ein anderer Typ (auch eine einzelne Zeichenkette)
  → `KonfigurationsFehler`.
- `from_env`: leer/fehlend → Vorgabe; Ganzzahlen als Dezimalziffern;
  `KONTOR_ANMELDUNG` wie `KONTOR_MOCK_MODUS` (leer/fehlend → `False`);
  `KONTOR_SITZUNG_COOKIE_SECURE` wie `KONTOR_MOCK_MODUS`, aber leer/fehlend
  → None; `KONTOR_ERLAUBTE_NETZE` durch Kommas getrennt (Leerraum um die
  Einträge wird entfernt); `KONTOR_LOG_STUFE` ohne Beachtung der
  Groß-/Kleinschreibung (gespeichert in Großbuchstaben); ungültige Werte →
  `KonfigurationsFehler`.
- Für den Betrieb wird `KONTOR_ANMELDUNG=1` verlangt (ausgelieferte
  Umgebungsdatei, `betrieb.md` 3); `create_app` protokolliert im Echtmodus
  ohne Anmeldung eine Warnung.
- Weiterhin legt die Konstruktion nichts an, liest keine Dateien und baut
  keine Verbindungen auf.

### 14.2 Anmeldung – `kontor.anmeldung`

```python
def passwort_hash(passwort: str) -> str: ...
def passwort_pruefen(passwort: str, hash_text: str) -> bool: ...
def passwort_setzen(config: KontorConfig, passwort: str) -> None: ...
def ist_eingerichtet(config: KontorConfig) -> bool: ...
```

- `passwort_hash`: Textform nach `sicherheit.md` 2.2 mit neuem Salz;
  Passwort verletzt 2.1 → `ValueError` (ohne das Passwort in der Meldung);
  kein `str` → `TypeError`.
- `passwort_pruefen`: nach 2.2; nie eine Ausnahme bei wohlgeformten
  Argumenttypen (`str`, `str`), sonst `TypeError`.
- `passwort_setzen`: setzt bzw. ersetzt das Haushaltspasswort in
  `config.aktive_datenbank` (legt sie samt Schema an, falls nötig), beendet
  alle Sitzungen, setzt Fehlversuche und Sperre zurück und löscht die
  Einrichtungscode-Datei (`sicherheit.md` 5). Unabhängig von
  `config.anmeldung`. Eine gleichzeitig laufende App mit derselben
  Datenbank sieht die Wirkung bei der nächsten Anfrage. Keine Änderung im
  Protokoll. Ungültiges Passwort → `ValueError` ohne Wirkung.
- Ab M23 (`geheimnisschutz.md` 2.4, 11): Ist der Schutz der Geheimnisse aktiv,
  löschen `passwort_setzen` und die Kommandozeile alle geschützten Geheimnisse und
  schalten den Schutz aus (`ntfy_token` bleibt); die Kommandozeile gibt die Anzahl
  der gelöschten Geheimnisse als Hinweis aus (ohne Namen oder Werte).
- `ist_eingerichtet`: ob in `config.aktive_datenbank` ein Passwort
  gespeichert ist (legt die Datenbank nicht an; fehlt sie → `False`).
- Kommandozeile `python -m kontor.anmeldung passwort-setzen`: Konfiguration
  aus `KontorConfig.from_env()`; liest das Passwort aus der ersten Zeile von
  stdin (ohne Zeilenumbruch; ist stdin ein Terminal, ohne Echo über
  `getpass`); Erfolg → Rückgabecode 0 und eine Zeile ohne Passwort auf
  stdout; ungültiges Passwort → Rückgabecode 1; Konfigurationsfehler →
  Rückgabecode 2.

### 14.3 Betrieb – `kontor.betrieb`, `kontor.__main__`

- `kontor.betrieb`: Paket mit den Dateien aus `betrieb.md` 1 als
  Paketdaten (`importlib.resources.files("kontor.betrieb")`).
- `python -m kontor`: Startmodul nach `betrieb.md` 2.

### 14.4 Sicherung – `kontor.sicherung`, Ergänzung

```python
def sichere_in_verzeichnis(config: KontorConfig, verzeichnis: str | os.PathLike[str], *,
                           behalten: int = 14) -> pathlib.Path: ...
```

Nach `betrieb.md` 8, samt Kommandozeile `python -m kontor.sicherung`.

### 14.5 Lifespan und Neustart

- Lifespan-Ende nach `betrieb.md` 5.2 (Planer anhalten, laufenden Lauf
  innerhalb `beenden_frist_sekunden` beenden, WAL-Checkpoint, Verbindungen
  schließen); danach ist die App nicht mehr zu verwenden.
- `create_app` auf einer vorhandenen Datenbank: `synchronisation.md` 10
  unverändert, Sitzungen bleiben gültig (`sicherheit.md` 4.4).

### 14.6 Fehlerklassen

Keine neuen Fehlerklassen; die neuen REST-Codes stehen in
`sicherheit.md` 11.

## 15. Meilenstein 8: Ergänzungen (Oberfläche)

Rückwärtskompatibel (E-029): Alles aus 1–14 gilt unverändert. Keine neuen
Module, Konfigurationsfelder oder Fehlerklassen. Abschnitt 7 („Struktur der
Weboberfläche frei“) gilt ab M8 mit den Merkmalen aus `oberflaeche.md`
(Routen, `data-testid`, Rollen, Verhalten); Aufbau, Framework und Dateien der
Oberfläche bleiben frei.

- `create_app` liefert die Hülle für alle Routen aus `oberflaeche.md` 3,
  die statischen Dateien unter `/oeffentlich/` (als Paketdaten ausliefern,
  ohne Netz zur Laufzeit, kein CDN) und `/sw.js` (`oberflaeche.md` 2, 18).
- Die Oberflächentests starten die App mit
  `uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1",
  port=<frei>, lifespan="on"))` in einem Thread des Testprozesses; mehrere
  solche Apps laufen nacheinander und gleichzeitig mit `TestClient`-Apps
  anderer Konfiguration im selben Prozess (Abschnitt 4: kein globaler
  Zustand).
- `POST /api/benachrichtigungen/test` nach `benachrichtigungen.md` 8 nutzt
  `erzeuge_benachrichtigungs_plugin` (13.3) bzw. die Plugin-Instanz der App.

## 16. Meilenstein 10: Ergänzungen (AqBanking-Plugin) – entfallen

Meilenstein 10 ist mit Meilenstein 29 vollständig entfallen (E-259): Es gibt
weder den Wert `bank_plugin = "aqbanking"` noch die Felder `aqbanking_*`, die
Fehlerklasse `BankTanNichtUnterstuetzt` oder das Modul
`kontor.plugins.aqbanking`. Siehe 21.

## 17. Meilenstein 11: Ergänzungen (Kontostand)

Rückwärtskompatibel (E-029). Fachliche Regeln: `kontostand.md`.

### 17.1 Konfiguration – `KontorConfig`

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `sync_saldo_angleichen` | bool, `True` | `KONTOR_SYNC_SALDO_ANGLEICHEN` | `bool` (nicht `int`, sonst `KonfigurationsFehler`); `from_env` wie `KONTOR_MOCK_MODUS`, leer/fehlend → Vorgabe `True` |

### 17.2 Module und Namen

| Name | Modul |
| --- | --- |
| `BankSaldo`, `Umsatzliste` | `kontor.plugins.bank` (`kontostand.md` 1) |

`umsaetze()` liefert eine `Umsatzliste` mit Attribut `saldo`; die
öffentlichen Methoden der Plugins bleiben unverändert.

## 18. Meilenstein 15: Ergänzungen (Sammelpaket Bedienung)

Rückwärtskompatibel (E-029). Fachliche Regeln: `synchronisation.md` 20.

### 18.1 Konfiguration – `KontorConfig`

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `sync_konten_anlegen` | bool, `True` | `KONTOR_SYNC_KONTEN_ANLEGEN` | `bool` (nicht `int`, nicht `None`, sonst `KonfigurationsFehler`); `from_env` wie `KONTOR_MOCK_MODUS` (`1`, `true`, `ja`, `yes`, `on` → wahr; `0`, `false`, `nein`, `no`, `off` → falsch; Groß-/Kleinschreibung egal), leer/fehlend → Vorgabe `True`, jeder andere Wert → `KonfigurationsFehler` |

Die ausgelieferte Umgebungsdatei setzt `KONTOR_SYNC_KONTEN_ANLEGEN=0`
(`betrieb.md` 3); im Betrieb werden unbekannte Bankkonten also nicht still
angelegt, sondern zur Zuordnung angeboten (`oberflaeche.md` 25.4).

## 19. Meilenstein 19: ALF-BanCo-Import (E-211)

```python
# kontor.importer.alfbanco
def importiere_alfbanco(
    config: KontorConfig,
    quelle: str | os.PathLike[str] | bytes,
    *,
    konto_id: int,
    dateiname: str | None = None,
) -> ImportErgebnis: ...
```

- Verhalten exakt wie `alfbanco.md` 1–4 und identisch mit
  `POST /api/import/alfbanco`; sonst wie `importiere_gnucash` (10.2): Pfad
  oder Bytes, `dateiname` aus dem Pfad, dieselbe Datenbank wie die App,
  atomar, Format- und Inhaltsfehler nur über `ImportErgebnis`.
- Ausnahmen: `TypeError` (anderer Typ von `quelle`), `FileNotFoundError`
  (Pfad fehlt), `ValueError` (Konto unbekannt oder kein Bestandskonto; nichts
  geändert).
- `ImportErgebnis.format` ∈ {`"qif"`, None}. `ImportErgebnis` und
  `ImportMeldung` wie bisher aus `kontor.importer.ergebnis`.
- Protokoll: wie 9.2 mit `aktion = "import_alfbanco"`.

## 20. Meilenstein 20: Ergänzungen (Mail-Abgleich, E-216)

### 20.1 Konfiguration – `KontorConfig`

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `mail_abgleich` | bool, `False` | `KONTOR_MAIL_ABGLEICH` | `bool` (nicht `int`, nicht `None`), sonst `KonfigurationsFehler` mit `details["feld"] = "mail_abgleich"`; `from_env` wie `KONTOR_SYNC_KONTEN_ANLEGEN` (18.1), leer/fehlend → Vorgabe |
| `mail_abgleich_frist_tage` | int, `5` | `KONTOR_MAIL_ABGLEICH_FRIST_TAGE` | 0–366, keine Ganzzahl (auch `bool`) oder außerhalb → `KonfigurationsFehler` mit `details["feld"] = "mail_abgleich_frist_tage"`; Umgebung: nur ASCII-Ziffern, höchstens 366, sonst `KonfigurationsFehler` mit `details["variable"] = "KONTOR_MAIL_ABGLEICH_FRIST_TAGE"`; leer → Vorgabe |

Fachliche Regeln: `erwartungen.md`. Die ausgelieferte Umgebungsdatei setzt
`KONTOR_MAIL_ABGLEICH=1` (`betrieb.md` 3).

## 21. Meilenstein 29: Bankabruf über FinTS/camt, Bankzugang (E-258)

Fachliche Regeln: `bankzugang.md`, `fints.md`. Dieser Abschnitt **ändert**
frühere Festlegungen (M10 entfällt, E-259); alles Übrige gilt unverändert.

### 21.1 Konfiguration – `KontorConfig`

- `bank_plugin` ∈ {`mock`, `fints`}. `KontorConfig(…, bank_plugin="aqbanking")`
  → `KonfigurationsFehler` mit `details["feld"] = "bank_plugin"`.
- `from_env`: `KONTOR_BANK_PLUGIN=aqbanking` wird wie `fints` gelesen
  (`bank_plugin == "fints"`); kein Fehler.
- Die Felder `aqbanking_verzeichnis`, `aqbanking_programme`,
  `aqbanking_timeout_sekunden` und `aqbanking_saldo` gibt es nicht mehr
  (weder als Attribut noch als Argument des Konstruktors). `from_env` liest
  keine Variable `KONTOR_AQBANKING_*`; beliebige Werte darin führen nie zu
  einem Fehler.
- `fints_url`, `fints_blz`, `fints_benutzer`, `fints_kunden_id`,
  `fints_produkt_id`, `fints_tan_verfahren` (13.1) bleiben und sind die
  Vorbelegung des Bankzugangs (`bankzugang.md` 2, 4).

### 21.2 Fehlerklassen und Module

- `kontor.fehler.BankTanNichtUnterstuetzt` gibt es nicht mehr; ebenso das
  Modul `kontor.plugins.aqbanking`.
- `FintsBankPlugin` (`kontor.plugins.fints`) hat die öffentlichen Methoden
  `konten`, `umsaetze`, `schliessen`, `tan_verfahren` (`fints.md` 3);
  `konten(*, tan=None)`.
- REST-Fehlercodes ohne eigene Python-Klasse im Vertrag:
  `bankzugang_nicht_aenderbar`, `bankzugang_unvollstaendig`, `tan_offen`
  (`bankzugang.md` 4).

### 21.3 Übergang alter Kennungen – `kontor.sync`

```python
def kennungen_als_alt_markieren(config: KontorConfig) -> None: ...
```

Markiert alle Bank-Kennungen, die die aktive Datenbank der Konfiguration in
diesem Augenblick kennt, als „alt“ (`bankzugang.md` 3.1, E-264). Kein
Protokolleintrag, keine Änderung am Buchbestand, keine Verbindung; mehrfach
aufrufbar.

### 21.4 REST

`openapi.yaml` 2.22.0: Tag `bank` mit `/api/bank/zugang…` (`bankzugang.md`
4); `PluginInfo.name` ohne `aqbanking`.

## 22. Meilenstein 31: Ergänzungen (Definition 3, E-277)

### 22.1 Konfiguration – `KontorConfig`

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `regeln_automatisch` | bool, `False` | `KONTOR_REGELN_AUTOMATISCH` | wie `mail_abgleich` (20.1) mit `details["feld"] = "regeln_automatisch"`; Vorgabe der Einstellung der Instanz (`lernmodell.md` 8.3, 9) |
| `mail_bestellnummer` | bool, `False` | `KONTOR_MAIL_BESTELLNUMMER` | wie `mail_abgleich` (20.1) mit `details["feld"] = "mail_bestellnummer"` (`erwartungen.md` 14) |

### 22.2 Module

`kontor.testinstanz` (Kommandozeile der Testinstanz, `betrieb.md` 9).

### 22.3 REST

`openapi.yaml` 2.24.0 (E-278).

## 23. Meilenstein 32: Ergänzungen (Definition 4, E-293)

### 23.1 Konfiguration – `KontorConfig`

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `anbieter_verzeichnis` | Pfad \| None, `None` | `KONTOR_ANBIETER_VERZEICHNIS` | Pfad (str oder `Path`, gespeichert als `Path`); leer/fehlend → None; die Konstruktion prüft nicht, ob es existiert (`sammel3.md` 9.1, E-301) |

### 23.2 Warnung beim Start

`create_app` protokolliert mit Stufe `WARNING`, wenn
`sitzung_cookie_secure = True` und `oeffentliche_url` fehlt (`sammel3.md` 15,
E-305).

### 23.3 REST

`openapi.yaml` 2.25.0 (E-294).

## 24. Feature benutzer (D-324)

### 24.1 Konfiguration – `KontorConfig`

| Feld | Typ, Vorgabe | Umgebungsvariable | Regeln |
| --- | --- | --- | --- |
| `benutzer` | Tupel aus `str`, `()` | `KONTOR_BENUTZER` | Personen des Haushalts in der Reihenfolge der Auswahl. Umgebung: durch Kommas getrennte Namen, Leerraum um jeden Namen wird entfernt; leer/fehlend → `()`. Je Name 1 bis 40 Zeichen, ein Buchstabe vorn; danach Buchstaben und Ziffern, Leerzeichen, Punkt, Apostroph und Bindestrich nur zwischen Buchstaben oder Ziffern. Höchstens 20 Namen, ohne Beachtung der Groß-/Kleinschreibung eindeutig. Konstruktion nimmt auch eine Liste und speichert ein Tupel. Verstoß → `KonfigurationsFehler` mit `details.variable = "KONTOR_BENUTZER"`, die Meldung nennt keine Werte. |

### 24.2 REST

`GET /api/benutzer` → `{"benutzer": [<Name>, …]}` (Schema `Benutzerliste`), nur lesend, ohne Protokoll;
`/api/konfiguration` führt das Feld wie alle übrigen. `openapi.yaml` 2.28.0.
