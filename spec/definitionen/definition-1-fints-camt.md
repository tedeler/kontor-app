# Meilenstein-Definition: Bankabruf über FinTS/camt und Bankzugang in der Oberfläche

Stand: 2026-11-19, **vom Auftraggeber freigegeben** (2026-11-19, unverändert gegenüber dem Entwurf). Feature `fints-camt`, in kontor-app auf main, veröffentlicht als Version 0.21. Noch nicht in kontor-tests übernommen. Vorschlag für die Nummer: M29; die Nummer vergibt der Test-Thread.

Diese Definition beschreibt nur Verhalten. Sie ersetzt Meilenstein 10 und ändert Teile von Meilenstein 6 und 11 (Abschnitt 9).

## 1 Umfang

1. Es gibt nur noch die Bank-Plugins `mock` und `fints`. Das AqBanking-Plugin entfällt.
2. Das FinTS-Plugin ruft Umsätze über camt in der Version ab, die die Bank anbietet.
3. Die Kontenliste des FinTS-Plugins beruht auf den SEPA-Kontoverbindungen der Bank.
4. Eine TAN schon bei der Anmeldung an der Bank ist kein Fehler mehr.
5. Der Bankzugang wird über REST und in der Oberfläche eingestellt und dauerhaft gespeichert.
6. Ein abschaltbares Diagnoseprotokoll zeigt den Austausch mit der Bank ohne persönliche Daten.
7. Umsätze, die vor der Umstellung schon gebucht wurden und danach mit anderer Kennung kommen, werden nicht doppelt gebucht.

Nicht im Umfang: entkoppelte Freigabe in einer Banking-App (bleibt ein Bankfehler), mehrere Bankzugänge je Instanz, Änderungen an der Saldenabfrage.

## 2 Konfiguration

- `bank_plugin` erlaubt `mock` und `fints`. Vorgabe wie bisher: `mock` im Mock-Modus, sonst `fints`.
- `bank_plugin="aqbanking"` beim Erzeugen der Konfiguration ist ein Konfigurationsfehler mit Feld `bank_plugin`.
- Beim Lesen aus der Umgebung gilt `KONTOR_BANK_PLUGIN=aqbanking` als `fints`; der Start scheitert daran nicht.
- Die Felder `aqbanking_verzeichnis`, `aqbanking_programme`, `aqbanking_timeout_sekunden` und `aqbanking_saldo` gibt es nicht mehr. Die Variablen `KONTOR_AQBANKING_*` werden nicht gelesen und stören nicht.
- Die Fehlerklasse für „TAN nicht unterstützt“ aus Meilenstein 10 (Code `bank_tan_nicht_unterstuetzt`) entfällt.
- Die Felder `fints_url`, `fints_blz`, `fints_benutzer`, `fints_kunden_id`, `fints_produkt_id` und `fints_tan_verfahren` bleiben. Sie sind die Vorbelegung des Bankzugangs, solange für das jeweilige Feld nichts gespeichert ist (Abschnitt 5).

## 3 FinTS-Plugin

### 3.1 Öffentliche Methoden

Zusätzlich zu `konten`, `umsaetze` und `schliessen` hat das FinTS-Plugin die öffentliche Methode `tan_verfahren`. Das Mock-Plugin bleibt unverändert.

- `tan_verfahren()` liefert die Zwei-Schritt-Verfahren, die die Bank diesem Zugang erlaubt, als Liste von Paaren aus dreistelliger Sicherheitsfunktion und Name. Sie braucht die PIN, sendet keinen Geschäftsvorfall und verlangt keine TAN. Nennt die Bank keine erlaubten Verfahren, kommen alle Zwei-Schritt-Verfahren aus den Bankparametern.
- `konten()` nimmt wahlweise eine TAN-Antwort als Schlüsselwortargument `tan` entgegen (3.4).
- Ist der Zugang unvollständig (Adresse, Bankleitzahl, Benutzerkennung oder Produkt-ID fehlt), scheitern alle drei Aufrufe ohne Verbindung mit `plugin_nicht_verfuegbar`. Die Meldung verweist auf die Einstellungen der Oberfläche.

### 3.2 Kontenliste

Geliefert wird je SEPA-Kontoverbindung der Bank, die eine IBAN hat und als SEPA-Konto gekennzeichnet ist, ein Bankkonto. Die Benutzerparameter der Bank ergänzen es:

- Der passende Eintrag der Benutzerparameter wird über die IBAN gesucht, ersatzweise über die Kontonummer (führende Nullen zählen nicht).
- Daraus kommen Name (Kontoproduktbezeichnung), Inhaber und Kontoart. Die Zuordnung der Kontoart bleibt: 1–9 Girokonto, 10–29 Sparkonto, 40–59 Kreditkonto.
- Gibt es keinen passenden Eintrag oder nennt er keine Kontoart, ist die Art `girokonto`; ohne Eintrag sind Name und Inhaber leer.
- Nicht geliefert wird ein Konto nur, wenn der Eintrag ausdrücklich eine andere Währung als EUR nennt oder eine Kontoart außerhalb der Tabelle (Depot und Ähnliches).
- Die BIC kommt aus der SEPA-Kontoverbindung, leer wird zu „nicht vorhanden“. Die Liste ist nach IBAN sortiert.

### 3.3 Umsatzabruf

- Bietet die Bank den camt-Abruf an, wird immer camt abgerufen. Verlangt wird genau ein Format: camt.052.001.08, falls angeboten, sonst die höchste angebotene Version von .07 bis .02.
- Bietet die Bank den camt-Abruf an, aber keine dieser Versionen, scheitert der Abruf mit `bank_fehler`. Auf MT940 wird dann nicht ausgewichen.
- MT940 wird nur noch abgerufen, wenn die Bank gar keinen camt-Abruf anbietet.
- Die Kontoverbindung im camt-Auftrag enthält nur IBAN und BIC, keine Kontonummer, kein Unterkontomerkmal und keine Bankleitzahl.
- Buchungs- und Wertstellungsdatum eines Eintrags dürfen als Datum oder als Zeitpunkt vorliegen und eine Zeitzone tragen (`2024-06-03`, `2024-06-03+02:00`, `2024-06-03Z`, `2024-06-03T10:11:12+02:00`). Ausgewertet werden Jahr, Monat und Tag. Fehlt das Buchungsdatum, gilt das Wertstellungsdatum; fehlen beide, entfällt der Eintrag wie bisher.
- Hat ein Datum oder ein Betrag eine andere Form, scheitert der ganze Abruf mit `bank_fehler`; einzelne Einträge werden dann nicht stillschweigend ausgelassen.
- Alle übrigen Abbildungsregeln der camt-Einträge gelten für jede Version unverändert.

### 3.4 TAN bei der Anmeldung

Verlangt die Bank schon für die Anmeldung (Dialogbeginn) eine TAN, gilt:

- `konten()` und `umsaetze()` melden „TAN erforderlich“ mit Challenge-Text und, falls geliefert, Grafik – wie bisher beim Umsatzabruf.
- Derselbe Aufruf mit der TAN-Antwort setzt denselben Dialog fort und liefert das Ergebnis. Für `umsaetze()` kann danach eine zweite TAN-Anforderung für den Abruf selbst folgen.
- Falsche TAN, abgelaufene Anforderung und Abbruch verhalten sich wie beim Umsatzabruf.
- Verlangt die Bank stattdessen eine entkoppelte Freigabe, scheitert der Aufruf mit `bank_fehler`.
- Nach einem Neustart ist eine offene Anforderung verfallen.

## 4 Synchronisation

- Sind im Bankzugang Konten gespeichert (5.4), verarbeitet ein Lauf mit dem FinTS-Plugin genau die ausgewählten Konten und fragt die Kontenliste nicht bei der Bank ab. Ist kein Konto ausgewählt, verarbeitet der Lauf kein Konto.
- Sind keine Konten gespeichert, fragt der Lauf die Kontenliste wie bisher bei der Bank ab. Braucht schon dieser Abruf eine TAN, scheitert der Lauf wie bisher; die Meldung nennt zusätzlich den Weg, die Konten einmal in den Einstellungen abzurufen.
- Verlangt die Bank beim Abruf eines Kontos eine TAN für die Anmeldung, wartet der Lauf wie bei einer TAN zum Umsatzabruf: eine TAN-Anforderung an diesem Konto, Antwort und Abbruch über die bestehenden Endpunkte und die TAN-Seite.
- Der Bankzugang aus der Oberfläche gilt ab dem nächsten Lauf, ohne Neustart.

### 4.1 Übergang alter Bank-Kennungen

Beim ersten Start mit dieser Fassung gelten alle bis dahin vergebenen Bank-Kennungen als „alt“. Das geschieht genau einmal je Datenbank; in einer neuen Datenbank gibt es keine alten Kennungen.

Ein Umsatz mit einer noch unbekannten Kennung wird einer vorhandenen Buchung zugeordnet statt neu gebucht, wenn die Buchung

- auf demselben Bankkonto denselben Betrag und denselben Buchungstag hat,
- für dieses Bankkonto nur alte Kennungen trägt und
- keine dieser alten Kennungen im selben Abruf wieder geliefert wurde.

Je Betrag und Buchungstag werden so viele Umsätze zugeordnet, wie es solche Buchungen gibt. Stehen mehrere zur Wahl, hat Vorrang, wessen Empfängername passt. Die übrigen Umsätze werden wie gewohnt abgeglichen und gebucht.

Eine Zuordnung zählt im Lauf als zusammengeführt, nicht als neu. Die Buchung trägt danach alte und neue Kennung; der nächste Abruf erkennt sie an der Kennung. Die Zuordnung gehört zur Änderung des Laufs im Protokoll und wird mit ihr rückgängig gemacht; ein erneuter Abruf ordnet dann wieder zu.

Die Markierung „alt“ ist Betriebszustand: nicht im Änderungsprotokoll, nicht in der Datensicherung.

## 5 Bankzugang über REST

Alle Endpunkte sind geschützt wie jeder andere. Der Bankzugang ist Betriebszustand: kein Eintrag im Änderungsprotokoll, nicht in der Datensicherung, kein Rückgängig. PIN und TAN werden nie gespeichert und erscheinen in keiner Antwort.

### 5.1 `GET /api/bank/zugang`

Antwort 200 mit:

| Feld | Inhalt |
| --- | --- |
| `url`, `blz`, `benutzer`, `kunden_id`, `produkt_id`, `tan_verfahren` | wirksamer Wert: gespeichert, sonst Vorbelegung aus der Konfiguration, sonst `null` |
| `plugin` | `mock` oder `fints` |
| `aenderbar` | wahr genau dann, wenn das Plugin `fints` ist |
| `gespeichert` | sortierte Liste der Feldnamen, für die ein Wert gespeichert ist |
| `vollstaendig` | wahr, wenn `url`, `blz`, `benutzer` und `produkt_id` einen wirksamen Wert haben |
| `konten` | gespeicherte Konten (5.4), sonst leere Liste |

### 5.2 `PUT /api/bank/zugang`

Körper: beliebige Teilmenge der sechs Felder, je Zeichenkette oder `null`. Nicht genannte Felder bleiben. `null` oder die leere Zeichenkette entfernt den gespeicherten Wert; dann gilt wieder die Vorbelegung. Unbekannte Felder (auch `pin`) sind ein Validierungsfehler. Antwort 200 wie 5.1.

Regeln je Feld, sonst 422 `validierung` mit dem Ort `body`, Feldname; die Meldung nennt nie den übergebenen Wert. Bei einem Fehler wird nichts gespeichert.

| Feld | Regel |
| --- | --- |
| `url` | https-Adresse; http nur für `127.0.0.1`, `::1` und `localhost` |
| `blz` | genau 8 Ziffern |
| `benutzer`, `kunden_id` | 1 bis 64 Zeichen |
| `produkt_id` | 1 bis 25 Zeichen |
| `tan_verfahren` | genau 3 Ziffern |

Ändert sich der wirksame Wert von `url`, `blz`, `benutzer` oder `kunden_id`, entfallen die gespeicherten Konten. Eine Änderung nur an `produkt_id` oder `tan_verfahren` lässt sie stehen.

Fehler: 409 `bankzugang_nicht_aenderbar`, wenn das Plugin nicht `fints` ist. 409 `sync_laeuft`, solange eine Synchronisation läuft. 409 `tan_offen`, solange eine Synchronisation auf eine TAN wartet.

### 5.3 `POST /api/bank/zugang/tan-verfahren`

Fragt die Bank nach den erlaubten TAN-Verfahren. Antwort 200: `verfahren` als Liste von Objekten mit `code` (drei Ziffern) und `name`. Gespeichert wird dabei nichts.

Fehler, jeweils 409: wie 5.2, dazu `bankzugang_unvollstaendig` (vor jeder anderen Prüfung des Zugangs und ohne Verbindung), `bank_pin_fehlt` (ohne Verbindung) und jeder Fehler des Plugins mit seinem Code (`bank_pin_falsch`, `bank_verbindung`, `bank_zeitueberschreitung`, `bank_fehler` …). Eine von der Bank abgelehnte PIN wird wie bei der Synchronisation verworfen.

### 5.4 `POST /api/bank/zugang/konten/abrufen`

Ruft die Konten bei der Bank ab und speichert sie. Körper leer, `{}` oder `vorgang` zusammen mit `tan`; nur eines von beiden ist ein Validierungsfehler.

Antwort 200 mit zwei Feldern:

- Erfolg: `konten` als Liste, `tan_erforderlich` ist `null`.
- TAN nötig: `konten` ist `null`, `tan_erforderlich` enthält `vorgang` (undurchsichtige Zeichenkette), `challenge` (Text, nie leer) und `bild` (Daten-URL der Grafik oder `null`).

Je Konto: `iban`, `bic` (oder `null`), `name`, `art`, `inhaber`, `aktiv`. Neue Konten sind ausgewählt; bei einem erneuten Abruf behalten bekannte Konten ihre Auswahl. Die Liste ist nach IBAN sortiert und ersetzt die gespeicherte.

Fortsetzen: derselbe Endpunkt mit `vorgang` und `tan`.

- 422 `tan_ungueltig` bei falscher TAN; der Vorgang bleibt offen.
- 409 `tan_abgelaufen`; der Vorgang ist beendet.
- 409 `tan_nicht_offen` bei unbekanntem oder beendetem Vorgang.
- Ein neuer Abruf ohne `vorgang` ersetzt einen offenen Vorgang.

Der Vorgang lebt nur im Arbeitsspeicher. Übrige Fehler wie 5.3.

### 5.5 `PUT /api/bank/zugang/konten`

Körper: `ibans` (Liste, Pflicht). Ausgewählt sind danach genau die genannten Konten. Antwort 200 wie 5.1. Eine IBAN, die nicht zu einem gespeicherten Konto gehört, ist 422 `validierung` mit Ort `body`, `ibans`, Index; dann ändert sich nichts. Fehler 409 wie 5.2.

### 5.6 `GET` und `PUT /api/bank/zugang/diagnose`

`GET` liefert `aktiv` (Wahrheitswert) und `zeilen` (Liste von Zeichenketten, älteste zuerst, höchstens 600). `PUT` mit `aktiv` schaltet das Protokoll und antwortet wie `GET`. Einschalten leert das Protokoll; Ausschalten lässt die Zeilen stehen. Die Einstellung übersteht einen Neustart, die Zeilen nicht. `PUT` im Mock-Modus: 409 `bankzugang_nicht_aenderbar`.

## 6 Diagnoseprotokoll

Ausgeliefert ausgeschaltet. Eingeschaltet schreibt das FinTS-Plugin je Aufruf Zeilen in das Protokoll aus 5.6 und zusätzlich in das Log des Dienstes (Stufe INFO).

Enthalten sind:

- Beginn und Ausgang jedes Aufrufs (Kontenabruf, Umsatzabruf mit Zeitraum, Abruf der TAN-Verfahren), bei Fehlern Fehlerklasse und Code.
- Je Nachricht die Richtung, die Segmentarten mit Version, HTTP-Status, Größe und Dauer.
- Rückmeldungen der Bank mit Code und bereinigtem Text; Parameter nur als Anzahl, bei den erlaubten TAN-Verfahren die dreistelligen Nummern.
- Angebote der Bank: camt-Formate, TAN-Verfahren mit Nummer und Name.
- Je Konto nur eine laufende Nummer („Konto 1“), Kontoart, Währung und die Angabe, welche Felder die Bank gefüllt hat, sowie ob es übernommen oder ausgelassen wurde und warum.
- Gewähltes camt-Format, ob eine TAN verlangt wurde, Zahl der gelesenen Einträge.
- Bei unlesbaren Umsatzdaten Feldname und Form des Werts (Ziffern als `9`, Buchstaben als `a`), nie der Wert.
- Warum kein Saldo abgefragt wurde.

Nie enthalten sind: PIN, TAN, Auftragsreferenz, Benutzerkennung, Kunden-ID, Kundensystem-ID, Produkt-ID, Server-Adresse, IBAN, Kontonummer, Inhaber, Kontobezeichnung, Beträge, Umsätze (Empfänger, Verwendungszweck, Referenzen) und der Wortlaut einer TAN-Anforderung.

Freitexte der Bank werden bereinigt: Benutzerkennung und Kunden-ID des Zugangs, IBANs und Ziffernfolgen ab fünf Stellen werden ersetzt, Steuerzeichen entfernt, die Länge auf 160 Zeichen begrenzt.

## 7 Oberfläche

Die Seite „Einstellungen“ zeigt einen Abschnitt `bankzugang` mit den Attributen `data-aenderbar` und `data-vollstaendig` (`ja`/`nein`).

Ist der Zugang nicht änderbar (Mock-Modus), enthält der Abschnitt nur den Hinweis `bankzugang-hinweis`.

Sonst:

| `data-testid` | Element |
| --- | --- |
| `bankzugang-url`, `-blz`, `-benutzer`, `-kunden_id`, `-produkt_id` | Eingabefelder, vorbelegt mit den wirksamen Werten |
| `bankzugang-tan-verfahren` | Auswahl; erster Eintrag „automatisch“ (leerer Wert), dazu der gespeicherte Wert und nach dem Abruf die Verfahren der Bank |
| `bankzugang-speichern` | speichert die Felder |
| `bankzugang-pin`, `bankzugang-pin-senden` | Kennwortfeld und Knopf; übergibt die PIN an den Arbeitsspeicher des Servers, das Feld ist danach leer |
| `bankzugang-pin-status` | `data-vorhanden` `ja`/`nein` |
| `bankzugang-verfahren-abrufen` | füllt die Auswahl der TAN-Verfahren |
| `bankzugang-konten-abrufen` | ruft die Konten ab |
| `bankzugang-meldung` | Statuszeile, `data-art` `hinweis` oder `fehler`; verborgen ohne Text |
| `bankzugang-tan` | Bereich der TAN-Anforderung, sonst verborgen: `bankzugang-tan-challenge`, `bankzugang-tan-bild` (nur mit Grafik), `bankzugang-tan-eingabe`, `bankzugang-tan-senden` |
| `bankzugang-konten` | Liste der Konten; je Konto ein Ankreuzfeld `bankzugang-konto` mit `data-iban`; dazu `bankzugang-konten-speichern` |
| `bankzugang-diagnose` | Ankreuzfeld `bankzugang-diagnose-aktiv`, Knöpfe `bankzugang-diagnose-laden` und `bankzugang-diagnose-kopieren`, Ausgabe `bankzugang-diagnose-zeilen` mit `data-zeilen` (Anzahl) |

Verhalten:

- „TAN-Verfahren abrufen“ und „Konten abrufen“ speichern zuerst geänderte Felder; scheitert das Speichern, wird die Bank nicht angesprochen.
- Validierungsfehler erscheinen in der Statuszeile mit Feldname und Meldung.
- Verlangt der Kontenabruf eine TAN, erscheint der TAN-Bereich. Nach einer falschen TAN bleibt er offen und das Eingabefeld ist leer; nach Erfolg oder einem anderen Fehler verschwindet er.
- Nach dem Abruf zeigt die Statuszeile die Anzahl der Konten; bei null Konten eine Fehlermeldung.
- Ohne abgerufene Konten nennt die Liste, dass dann alle Konten der Bank synchronisiert werden.
- Stammen alle Angaben aus der Vorbelegung, steht ein Hinweis darauf unter dem Abschnitt.
- Der Abschnitt lädt keine Ressourcen von außen und nutzt keinen Browser-Speicher.

## 8 Sicherheit

- Die PIN liegt nur im Arbeitsspeicher oder, auf Wunsch des Nutzers, im verschlüsselten Geheimnisspeicher wie bisher. Sie steht nie im Bankzugang, im Log, im Diagnoseprotokoll, in Antworten oder Fehlermeldungen.
- TAN, Auftragsreferenz und die interne Kennung einer TAN-Anforderung verlassen den Arbeitsspeicher nie; die Oberfläche bekommt nur den `vorgang`.
- Der Bankzugang enthält keine Geheimnisse und wird nicht in die Datensicherung übernommen.
- Ohne vollständigen Zugang und ohne PIN wird keine Verbindung aufgebaut.

## 9 Änderungen an früheren Meilensteinen

- **M10** entfällt vollständig (Plugin, Konfiguration, Tests).
- **M11**: Der Teil „Saldo über AqBanking“ entfällt. FinTS- und Mock-Saldo bleiben.
- **M6**, FinTS-Plugin: öffentliche Methoden nach 3.1; Kontenliste nach 3.2; camt-Version nach 3.3 (bisher nur .08, sonst MT940); TAN bei der Anmeldung nach 3.4 (bisher Fehler); Meldungstext bei unvollständigem Zugang.
- **Gemeinsamer Plugin-Test** der öffentlichen Methoden: für das echte Bank-Plugin zusätzlich `tan_verfahren`.

## 10 Hinweise für die Tests

Die FinTS-Attrappe braucht dafür zusätzliche Betriebsarten:

- wählbare camt-Version (mindestens .02 und .08) und ein Angebot ohne lesbare Version,
- TAN bei der Anmeldung, auch bei jedem Dialog,
- Benutzerparameter ohne Kontoart, ohne IBAN (nur Kontonummer) und ganz ohne Konten,
- Datumsangaben mit Zeitzone und als Zeitpunkt,
- Rückmeldungstexte, die Kennungen und Kontonummern enthalten (für das Diagnoseprotokoll).

Für den Übergang (4.1) lässt sich der Zustand „vor der Umstellung“ nur in der Datenbank herstellen; dafür ist eine Testhilfe oder ein dokumentierter Weg nötig, den der Test-Thread festlegt.

Alles nur mit synthetischen Daten und gegen lokale Attrappen.
