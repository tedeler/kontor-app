# Bankabruf über FinTS/camt und Bankzugang in der Oberfläche – Meilenstein 29

Verbindlich für Implementierung und Tests. Übernahme der freigegebenen
Meilenstein-Definition vom 2026-11-19 (`spec/definitionen/definition-1-fints-camt.md`,
Feature `fints-camt`, E-258). Das Dokument beschreibt den Bankzugang
(Konfiguration, REST, Diagnoseprotokoll, Sicherheit) und den Übergang alter
Bank-Kennungen. Die Änderungen am FinTS-Plugin selbst stehen in `fints.md`
(3, 3.1–3.5, 6), die Änderungen an der Synchronisation in
`synchronisation.md` 21, die Oberfläche in `oberflaeche.md` 38.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`,
D = Definition (Abschnittsnummer der Meilenstein-Definition).

Meilenstein 29 **ersetzt Meilenstein 10** (AqBanking-Plugin, entfällt
vollständig, E-259) und ändert Teile von Meilenstein 6 und 11 (E-260, E-261).

## 1. Umfang (D 1)

1. Es gibt nur noch die Bank-Plugins `mock` und `fints`. Das AqBanking-Plugin
   entfällt.
2. Das FinTS-Plugin ruft Umsätze über camt in der Version ab, die die Bank
   anbietet (`fints.md` 3.3).
3. Die Kontenliste des FinTS-Plugins beruht auf den SEPA-Kontoverbindungen
   der Bank (`fints.md` 3.2).
4. Eine TAN schon bei der Anmeldung an der Bank ist kein Fehler mehr
   (`fints.md` 3.5a).
5. Der Bankzugang wird über REST und in der Oberfläche eingestellt und
   dauerhaft gespeichert (4, `oberflaeche.md` 38).
6. Ein abschaltbares Diagnoseprotokoll zeigt den Austausch mit der Bank ohne
   persönliche Daten (5).
7. Umsätze, die vor der Umstellung schon gebucht wurden und danach mit
   anderer Kennung kommen, werden nicht doppelt gebucht (3).

Nicht im Umfang: entkoppelte Freigabe in einer Banking-App (bleibt ein
Bankfehler), mehrere Bankzugänge je Instanz, Änderungen an der
Saldenabfrage.

## 2. Konfiguration (D 2)

- `bank_plugin` erlaubt `mock` und `fints`. Vorgabe wie bisher: `mock` im
  Mock-Modus, sonst `fints`.
- `bank_plugin="aqbanking"` beim Erzeugen der Konfiguration ist ein
  `KonfigurationsFehler` mit `details["feld"] = "bank_plugin"`.
- Beim Lesen aus der Umgebung (`from_env`) gilt `KONTOR_BANK_PLUGIN=aqbanking`
  als `fints`; der Start scheitert daran nicht. (Im Mock-Modus gelten für den
  so entstandenen Wert `fints` die bisherigen Regeln, `python-api.md` 3.)
- Die Felder `aqbanking_verzeichnis`, `aqbanking_programme`,
  `aqbanking_timeout_sekunden` und `aqbanking_saldo` gibt es nicht mehr. Die
  Variablen `KONTOR_AQBANKING_*` werden nicht gelesen und stören nicht (auch
  nicht mit Werten, die früher ungültig waren).
- Die Fehlerklasse `BankTanNichtUnterstuetzt` (Code
  `bank_tan_nicht_unterstuetzt`) und das Modul `kontor.plugins.aqbanking`
  entfallen.
- Die Felder `fints_url`, `fints_blz`, `fints_benutzer`, `fints_kunden_id`,
  `fints_produkt_id` und `fints_tan_verfahren` bleiben (`python-api.md` 13.1).
  Sie sind die **Vorbelegung** des Bankzugangs, solange für das jeweilige Feld
  nichts gespeichert ist (4).

## 3. Übergang alter Bank-Kennungen (D 4.1)

Beim ersten Start mit dieser Fassung gelten alle bis dahin vergebenen
Bank-Kennungen als „alt“. Das geschieht genau einmal je Datenbank; in einer
neuen Datenbank gibt es keine alten Kennungen.

Ein Umsatz mit einer noch unbekannten Kennung wird einer vorhandenen Buchung
zugeordnet statt neu gebucht, wenn die Buchung

- auf demselben Bankkonto denselben Betrag und denselben Buchungstag hat,
- für dieses Bankkonto nur alte Kennungen trägt und
- keine dieser alten Kennungen im selben Abruf wieder geliefert wurde.

Je Betrag und Buchungstag werden so viele Umsätze zugeordnet, wie es solche
Buchungen gibt. Stehen mehrere zur Wahl, hat Vorrang, wessen Empfängername
passt. Die übrigen Umsätze werden wie gewohnt abgeglichen und gebucht
(`synchronisation.md` 4.3, 4.4).

Eine Zuordnung zählt im Lauf als zusammengeführt (`buchungen_zusammengefuehrt`),
nicht als neu. Die Buchung trägt danach alte und neue Kennung
(`extern_ids`); der nächste Abruf erkennt sie an der Kennung. Sonst bleibt
die Buchung unverändert (wie beim Zusammenführen, `synchronisation.md` 4.4;
E-265). Die Zuordnung
gehört zur Änderung des Laufs im Protokoll und wird mit ihr rückgängig
gemacht; ein erneuter Abruf ordnet dann wieder zu.

Die Markierung „alt“ ist Betriebszustand: nicht im Änderungsprotokoll, nicht
in der Datensicherung.

### 3.1 Naht für Tests und Betrieb (E-264)

Der Zustand „vor der Umstellung“ lässt sich über REST nicht herstellen. Dafür
gibt es eine öffentliche Funktion (`python-api.md` 21.3):

```python
# kontor.sync
def kennungen_als_alt_markieren(config: KontorConfig) -> None: ...
```

- Sie markiert **alle** Bank-Kennungen, die die aktive Datenbank in diesem
  Augenblick kennt (Kennungen an Buchungen und gemerkte Kennungen gelöschter
  Buchungen), als „alt“ – unabhängig davon, ob der einmalige Übergang für
  diese Datenbank schon stattgefunden hat. Das Ergebnis ist dasselbe, als
  wäre die Datenbank in diesem Zustand zum ersten Mal mit dieser Fassung
  gestartet worden.
- Sie legt keinen Protokolleintrag an, ändert den Buchbestand nicht, baut
  keine Verbindung auf und darf mehrfach aufgerufen werden. Später vergebene
  Kennungen sind wieder „nicht alt“.
- Sie wird aufgerufen, wenn keine App-Instanz für diese Datenbank einen Lauf
  ausführt; eine danach erzeugte App-Instanz (`create_app`) sieht die
  Markierung. Fehlt die Datenbank, wird sie wie bei `create_app` angelegt.

Die Tests stellen den Zustand so her: Lauf mit den alten Kennungen →
App-Instanz schließen → `kennungen_als_alt_markieren(config)` → neue
App-Instanz auf derselben Datenbank → Lauf mit den neuen Kennungen.

## 4. Bankzugang über REST (D 5)

Alle Endpunkte sind geschützt wie jeder andere (`sicherheit.md` 3.2; keiner
steht in 3.1). Der Bankzugang ist Betriebszustand: kein Eintrag im
Änderungsprotokoll, nicht in der Datensicherung, kein Rückgängig. PIN und TAN
werden nie gespeichert und erscheinen in keiner Antwort. Schemas:
`openapi.yaml` (Tag `bank`).

### 4.1 `GET /api/bank/zugang` → 200 `Bankzugang`

| Feld | Inhalt |
| --- | --- |
| `url`, `blz`, `benutzer`, `kunden_id`, `produkt_id`, `tan_verfahren` | wirksamer Wert: gespeichert, sonst Vorbelegung aus der Konfiguration, sonst `null` |
| `plugin` | `mock` oder `fints` |
| `aenderbar` | wahr genau dann, wenn das Plugin `fints` ist |
| `gespeichert` | sortierte Liste der Feldnamen, für die ein Wert gespeichert ist |
| `vollstaendig` | wahr, wenn `url`, `blz`, `benutzer` und `produkt_id` einen wirksamen Wert haben |
| `konten` | gespeicherte Konten (4.4), sonst leere Liste |

### 4.2 `PUT /api/bank/zugang` → 200 `Bankzugang`

Körper: beliebige Teilmenge der sechs Felder, je Zeichenkette oder `null`
(`{}` ändert nichts). Nicht genannte Felder bleiben. `null` oder die leere
Zeichenkette entfernt den gespeicherten Wert; dann gilt wieder die
Vorbelegung. Unbekannte Felder (auch `pin`) sind ein Validierungsfehler.

Regeln je Feld, sonst 422 `validierung` mit dem Ort `["body", <Feldname>]`;
Meldung und `details` nennen nie den übergebenen Wert. Bei einem Fehler wird
nichts gespeichert (auch nicht die gültigen Felder desselben Körpers).

| Feld | Regel |
| --- | --- |
| `url` | https-Adresse; http nur für `127.0.0.1`, `::1` und `localhost` |
| `blz` | genau 8 Ziffern |
| `benutzer`, `kunden_id` | 1 bis 64 Zeichen |
| `produkt_id` | 1 bis 25 Zeichen |
| `tan_verfahren` | genau 3 Ziffern |

Ändert sich der wirksame Wert von `url`, `blz`, `benutzer` oder `kunden_id`,
entfallen die gespeicherten Konten. Eine Änderung nur an `produkt_id` oder
`tan_verfahren` lässt sie stehen.

Fehler: 409 `bankzugang_nicht_aenderbar`, wenn das Plugin nicht `fints` ist.
409 `sync_laeuft`, solange eine Synchronisation läuft. 409 `tan_offen`,
solange eine Synchronisation auf eine TAN wartet.

### 4.3 `POST /api/bank/zugang/tan-verfahren` → 200 `BankTanVerfahren`

Fragt die Bank nach den erlaubten TAN-Verfahren (`fints.md` 3.0,
`tan_verfahren()`). Antwort: `verfahren` als Liste von Objekten mit `code`
(drei Ziffern) und `name`. Gespeichert wird dabei nichts. Kein Körper.

Fehler, jeweils 409: wie 4.2, dazu `bankzugang_unvollstaendig` (vor jeder
anderen Prüfung des Zugangs und ohne Verbindung), `bank_pin_fehlt` (ohne
Verbindung) und jeder Fehler des Plugins mit seinem Code (`bank_pin_falsch`,
`bank_verbindung`, `bank_zeitueberschreitung`, `bank_fehler` …). Eine von der
Bank abgelehnte PIN wird wie bei der Synchronisation verworfen
(`synchronisation.md` 12).

### 4.4 `POST /api/bank/zugang/konten/abrufen` → 200 `BankKontenAbruf`

Ruft die Konten bei der Bank ab (`fints.md` 3.2) und speichert sie. Körper
leer, `{}` oder `vorgang` zusammen mit `tan`; nur eines von beiden ist ein
Validierungsfehler (422 `validierung`).

Antwort 200 mit zwei Feldern:

- Erfolg: `konten` als Liste, `tan_erforderlich` ist `null`.
- TAN nötig (`fints.md` 3.5a): `konten` ist `null`, `tan_erforderlich`
  enthält `vorgang` (undurchsichtige Zeichenkette), `challenge` (Text, nie
  leer) und `bild` (Daten-URL der Grafik, `data:<MIME-Typ>;base64,…`, oder
  `null`).

Je Konto: `iban`, `bic` (oder `null`), `name`, `art`, `inhaber`, `aktiv`.
Neue Konten sind ausgewählt (`aktiv = true`); bei einem erneuten Abruf
behalten bekannte Konten ihre Auswahl. Die Liste ist nach IBAN sortiert und
ersetzt die gespeicherte.

Fortsetzen: derselbe Endpunkt mit `vorgang` und `tan`.

- 422 `tan_ungueltig` bei falscher TAN; der Vorgang bleibt offen.
- 409 `tan_abgelaufen`; der Vorgang ist beendet.
- 409 `tan_nicht_offen` bei unbekanntem oder beendetem Vorgang.
- Ein neuer Abruf ohne `vorgang` ersetzt einen offenen Vorgang (der alte
  `vorgang` ist danach `tan_nicht_offen`).

Der Vorgang lebt nur im Arbeitsspeicher (nach einem Neustart:
`tan_nicht_offen`). Der `vorgang` ist nicht die Auftragsreferenz der Bank und
nicht die `anforderung_id` des Plugins (6). Übrige Fehler wie 4.3.

### 4.5 `PUT /api/bank/zugang/konten` → 200 `Bankzugang`

Körper: `ibans` (Liste, Pflicht). Ausgewählt sind danach genau die genannten
Konten (`aktiv`); eine leere Liste wählt alle ab. Eine IBAN, die nicht zu
einem gespeicherten Konto gehört, ist 422 `validierung` mit Ort
`["body", "ibans", <Index>]`; dann ändert sich nichts. Fehler 409 wie 4.2.

### 4.6 `GET` und `PUT /api/bank/zugang/diagnose` → 200 `BankDiagnose`

`GET` liefert `aktiv` (Wahrheitswert) und `zeilen` (Liste von Zeichenketten,
älteste zuerst, höchstens 600). `PUT` mit `aktiv` schaltet das Protokoll und
antwortet wie `GET`. Einschalten leert das Protokoll; Ausschalten lässt die
Zeilen stehen. Die Einstellung übersteht einen Neustart, die Zeilen nicht.
`PUT` im Mock-Modus: 409 `bankzugang_nicht_aenderbar`.

## 5. Diagnoseprotokoll (D 6)

Ausgeliefert ausgeschaltet. Eingeschaltet schreibt das FinTS-Plugin je Aufruf
Zeilen in das Protokoll aus 4.6 und zusätzlich in das Log des Dienstes (Stufe
INFO).

Enthalten sind:

- Beginn und Ausgang jedes Aufrufs (Kontenabruf, Umsatzabruf mit Zeitraum,
  Abruf der TAN-Verfahren), bei Fehlern Fehlerklasse und Code.
- Je Nachricht die Richtung, die Segmentarten mit Version, HTTP-Status,
  Größe und Dauer.
- Rückmeldungen der Bank mit Code und bereinigtem Text; Parameter nur als
  Anzahl, bei den erlaubten TAN-Verfahren die dreistelligen Nummern.
- Angebote der Bank: camt-Formate, TAN-Verfahren mit Nummer und Name.
- Je Konto nur eine laufende Nummer („Konto 1“), Kontoart, Währung und die
  Angabe, welche Felder die Bank gefüllt hat, sowie ob es übernommen oder
  ausgelassen wurde und warum.
- Gewähltes camt-Format, ob eine TAN verlangt wurde, Zahl der gelesenen
  Einträge.
- Bei unlesbaren Umsatzdaten Feldname und Form des Werts (Ziffern als `9`,
  Buchstaben als `a`), nie der Wert.
- Warum kein Saldo abgefragt wurde.

Nie enthalten sind: PIN, TAN, Auftragsreferenz, Benutzerkennung, Kunden-ID,
Kundensystem-ID, Produkt-ID, Server-Adresse, IBAN, Kontonummer, Inhaber,
Kontobezeichnung, Beträge, Umsätze (Empfänger, Verwendungszweck, Referenzen)
und der Wortlaut einer TAN-Anforderung.

Freitexte der Bank werden bereinigt: Benutzerkennung und Kunden-ID des
Zugangs, IBANs und Ziffernfolgen ab fünf Stellen werden ersetzt,
Steuerzeichen entfernt, die Länge auf 160 Zeichen begrenzt.

## 6. Sicherheit (D 8)

- Die PIN liegt nur im Arbeitsspeicher oder, auf Wunsch des Nutzers, im
  verschlüsselten Geheimnisspeicher wie bisher (`geheimnisschutz.md` 5). Sie
  steht nie im Bankzugang, im Log, im Diagnoseprotokoll, in Antworten oder
  Fehlermeldungen.
- TAN, Auftragsreferenz und die interne Kennung einer TAN-Anforderung
  verlassen den Arbeitsspeicher nie; die Oberfläche bekommt nur den
  `vorgang`.
- Der Bankzugang enthält keine Geheimnisse und wird nicht in die
  Datensicherung übernommen.
- Ohne vollständigen Zugang und ohne PIN wird keine Verbindung aufgebaut.

## 7. Änderungen an früheren Meilensteinen (D 9)

- **M10** entfällt vollständig (Plugin, Konfiguration, Tests; E-259).
  `aqbanking.md` ist gelöscht; `python-api.md` 16 und `plugins.md` 10 sind
  leer.
- **M11**: Der Teil „Saldo über AqBanking“ (`kontostand.md` 1.3) entfällt.
  FinTS- und Mock-Saldo bleiben (E-260).
- **M6**, FinTS-Plugin: öffentliche Methoden (`fints.md` 3), Kontenliste
  (3.2), camt-Version (3.3, bisher nur .08, sonst MT940), TAN bei der
  Anmeldung (3.5a, bisher Fehler), Meldungstext bei unvollständigem Zugang
  (3.1; E-261).
- **Gemeinsamer Plugin-Test** der öffentlichen Methoden: für das echte
  Bank-Plugin zusätzlich `tan_verfahren` (E-261).

## 8. Tests (D 10)

`tests/app/m29/` (Marker `m29`, Hilfen `tests/hilfen/m29.py`). Die
FinTS-Attrappe hat dafür zusätzliche Betriebsarten (`fints.md` 6, E-263).
Alles nur mit synthetischen Daten und gegen lokale Attrappen. Prüfmerkmale
und Lesarten: E-265.
