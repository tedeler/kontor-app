# Entscheidungen des Test-Threads

Jeder Eintrag: Nummer, Frage, Entscheidung, Begründung, Bezug zum Konzept.
Abkürzungen: K = `spec/konzept.md`, T = `spec/testkonzept.md`.

## E-001 Ordnername `specs/` oder `spec/`

- **Frage:** Im Repository lag die Spezifikation unter `specs/`, Projektanweisungen und Auftrag sprechen von `spec/` (z. B. `spec/api/`).
- **Entscheidung:** Ordner per `git mv specs spec` umbenannt; README-Verweise angepasst. Es gibt keinen Ordner `specs/` mehr.
- **Begründung:** Alle Pfade in den Projektanweisungen stimmen damit ohne Ausnahme; eine einzige Schreibweise vermeidet Verwechslungen zwischen Threads.
- **Bezug:** T 1 (Schnittstellenvertrag als einzige gemeinsame Grundlage).

## E-002 Paketname und Modulpfade

- **Frage:** Unter welchem Namen wird die Anwendung installiert und importiert?
- **Entscheidung:** pip-Distribution und Importpaket heißen `kontor`. Feste Module: `kontor.config`, `kontor.app`, `kontor.fehler`, `kontor.importer.kmymoney`, `kontor.importer.ergebnis`, `kontor.plugins` (mit `bank`, `mail`, `mock_bank`, `mock_mail`). App-Fabrik `kontor.app.create_app(config: KontorConfig | None) -> FastAPI`.
- **Begründung:** Kurz, eindeutig, passt zum Projektnamen; feste Pfade sind Voraussetzung, damit Tests ohne Einblick in den Code laufen.
- **Bezug:** T 1 (Schnittstellenvertrag), K 3.

## E-003 Fachliche Operationen nur über REST

- **Frage:** Werden Konten, Buchungen usw. zusätzlich über eine Python-API angeboten?
- **Entscheidung:** Nein. Fachliche Operationen sind nur über REST spezifiziert. Die Python-API umfasst Konfiguration, App-Fabrik, Dateiimport, Plugins und Fehlerklassen.
- **Begründung:** Eine einzige fachliche Schnittstelle halbiert den Implementierungs- und Testaufwand und vermeidet Abweichungen zwischen zwei Zugängen. Eigenschaftsbasierte Tests laufen über den TestClient.
- **Bezug:** T 1, T 2.

## E-004 Beträge

- **Frage:** Darstellung und Grenzen von Beträgen.
- **Entscheidung:** Ganze Cent als `int`, Bereich je Betrag ±999 999 999 999. In JSON werden Gleitkommazahlen (auch `12.0`), Zeichenketten und Booleans an Betragsstellen mit 422 abgelehnt.
- **Begründung:** Invariante 2 (nie Gleitkomma) wird so an der Schnittstelle prüfbar; der Bereich passt sicher in SQLite-INTEGER und JavaScript-Number.
- **Bezug:** T 3.2.

## E-005 Vorzeichenkonvention

- **Frage:** Welches Vorzeichen haben Splits und Salden?
- **Entscheidung:** Soll positiv, Haben negativ (wie KMyMoney intern). Saldo = Summe der Splits, ohne Vorzeichenumkehr; Schulden und Erträge sind negativ. Die Oberfläche darf zur Anzeige umkehren.
- **Begründung:** Damit gelten Invarianten 3 und 4 unmittelbar, und KMyMoney-Werte werden unverändert übernommen.
- **Bezug:** K 4, T 3.3, T 3.4.

## E-006 Nur EUR; Fremdwährung beim Import

- **Frage:** Wie werden Fremdwährungen behandelt?
- **Entscheidung:** Es gibt nur EUR. Beim KMyMoney-Import werden Konten in Fremdwährung übersprungen (Warnung `fremdwaehrung`), ebenso jede Buchung mit einem Split auf einem übersprungenen Konto oder mit `commodity` ≠ EUR (Warnung `buchung_uebersprungen`). Kein Abbruch des ganzen Imports.
- **Begründung:** Fremdwährungen sind bewusst ausgeschlossen; ein Abbruch würde Haushalte mit einem einzelnen Fremdwährungskonto vom Import ausschließen.
- **Bezug:** K 16, T 5.

## E-007 Kategorie einer Buchung

- **Frage:** Was ist „die Kategorie“ einer Buchung bei doppelter Buchführung, und was ändert „Kategorie setzen“?
- **Entscheidung:** Gegensplits = Splits auf Nicht-Bestandskonten. Kategorisierbar = genau ein Gegensplit. `kategorie_id` = dessen Konto, wenn Art aufwand/ertrag. Kategorie setzen ersetzt nur das Konto dieses Gegensplits. Splitbuchungen und Umbuchungen sind nicht kategorisierbar (422).
- **Begründung:** Eindeutig, verlustfrei, Invariante 1 bleibt erhalten; Gegensplits auf „Unausgeglichen“ oder Eigenkapital können so durch eine echte Kategorie ersetzt werden.
- **Bezug:** K 4, K 5, T 14 (Mehrfachbearbeitung).

## E-008 Statusübergänge und Sperre

- **Frage:** Anfangsstatus, Übergänge, Schutz abgeglichener Buchungen.
- **Entscheidung:** Manuell anlegbar: importiert, vorlaeufig, bestaetigt (Vorgabe bestaetigt); Import setzt importiert. Übergänge laut T 4; gleicher Status = zulässig ohne Wirkung; sonst 409. Abgeglichene Buchungen sind gesperrt (außer Tags).
- **Begründung:** Übergänge exakt nach Testkonzept; der Selbstübergang macht PATCH idempotent. Die Sperre nimmt T 13 („gegen Änderung geschützt“) in einfacher Form vorweg.
- **Bezug:** K 4, T 4, T 13.

## E-009 Importfehler als Ergebnis, atomar

- **Frage:** Wie meldet der Import Fehler, und was bedeutet „ohne Teilimport“?
- **Entscheidung:** `importiere_kmy` wirft bei Datei-/Inhaltsfehlern keine Ausnahme, sondern liefert `ImportErgebnis(erfolgreich=False, fehler=[…])`; REST antwortet 422 mit dem Ergebnis in `fehler.details`. Der Import läuft in einer Datenbanktransaktion; bei jedem Fehler bleibt das Buch unverändert, und es entsteht kein Importvorgang.
- **Begründung:** Der Auftrag verlangt ein Rückgabeobjekt mit Zählungen, Warnungen und Fehlern; Atomarität macht T 5 („ohne Teilimport“) streng prüfbar.
- **Bezug:** K 12, T 5.

## E-010 Idempotenz über Herkunftskennungen

- **Frage:** Wie wird erkannt, dass Daten schon importiert sind?
- **Entscheidung:** Jedes importierte Objekt trägt `extern_id`/`extern_ids` = `kmy:<KMyMoney-ID>`. Beim erneuten Import wird darüber zugeordnet; zugeordnete Objekte werden nicht verändert. Konten ohne Herkunft werden über IBAN (Bestandskonten) bzw. Art+Name+Elternkonto (übrige) übernommen, Empfänger über exakten Namen, Tags über casefold-Namen. Ein Kontor-Buch nimmt genau ein KMyMoney-Buch auf.
- **Begründung:** KMyMoney-IDs sind innerhalb einer Datei stabil; erweiterte Fassungen derselben Datei werden so inkrementell importierbar. Die Zuordnung über IBAN/Name verbindet vorab manuell angelegte Konten, damit die Dublettenprüfung greifen kann.
- **Bezug:** T 3.7, K 12.

## E-011 Dublettenerkennung beim Import

- **Frage:** Was ist eine eindeutige Dublette, was ein Zweifelsfall?
- **Entscheidung:** Kandidaten sind vorhandene Buchungen ohne `kmy:`-Herkunft mit Split gleichen Kontos und Betrags. Exakt = gleiches Datum und passender Empfänger (Vergleich nach `ekey`: casefold, Umlaute aufgelöst, nur `[a-z0-9]`). Ähnlich = bis 3 Tage Abstand oder Empfänger nicht passend. Genau ein exakter Kandidat, den keine andere neue Buchung ebenfalls exakt trifft → automatisch zusammenführen. Sonst bei Treffern → anlegen und Dublettenverdacht (`mehrdeutig`/`aehnlich`) zur Bestätigung.
- **Begründung:** Erfüllt K 12 und T 6 (gleicher Kaffee zweimal wird nicht zusammengeführt; ein Tag Abstand oder abweichender Empfängertext landen in der Bestätigungsliste). Die Zweiphasenbewertung macht das Ergebnis unabhängig von der Reihenfolge.
- **Bezug:** K 6, K 12, T 6.

## E-012 Unausgeglichene KMyMoney-Transaktionen

- **Frage:** KMyMoney erlaubt Transaktionen mit nur einem Split (ohne Kategorie). Kontor verlangt ≥ 2 Splits mit Summe 0.
- **Entscheidung:** Der Import ergänzt einen Ausgleichssplit auf das technische Eigenkapitalkonto „Unausgeglichen“ (`extern_id = kontor:unausgeglichen`) und warnt (`buchung_ausgeglichen`).
- **Begründung:** Salden der Bestandskonten bleiben wie in der Quelle, Invarianten 1 und 4 gelten, und die Buchung bleibt per „Kategorie setzen“ nachträglich kategorisierbar (Vorbild: Imbalance-Konto in GnuCash).
- **Bezug:** K 4, T 3.1, T 5.

## E-013 Abbildung der KMyMoney-Kontotypen

- **Frage:** Wie werden KMyMoney-Kontotypen auf die sechs Kontor-Arten abgebildet?
- **Entscheidung:** Tabelle in `datenmodell.md` 10.2. Bargeld (3), Asset (9), AssetLoan (14) werden ersetzt (mit Warnung), Investment/Stock/Currency/Unknown übersprungen. Die fünf Standardkonten `AStd::*` werden nicht übernommen; ihre Kinder werden Wurzelkonten.
- **Begründung:** Bargeldkonto und Depot sind bewusst ausgeschlossen bzw. zurückgestellt; Ersetzen erhält die Salden, Überspringen vermeidet Daten ohne EUR-Bewertung.
- **Bezug:** K 4, K 15, K 16.

## E-014 Mock-Modus, eigene Datenbank, Hinweis

- **Frage:** Wie werden Mock- und Echtdaten getrennt, und wie wird der Mock-Modus sichtbar?
- **Entscheidung:** Mock-Datenbank = eigener Pfad (Vorgabe `<stem>-mock<suffix>` neben der Echt-Datenbank). Im Mock-Modus sind nur Mock-Plugins erlaubt, außerhalb keine. Hinweis über `GET /api/status`, Header `X-Kontor-Modus` an jeder API-Antwort und ein serverseitig ausgeliefertes Element `id="mock-hinweis"` in `GET /`.
- **Begründung:** Erzwingt K 3 („getrennte Datenbanken, sichtbarer Hinweis“) technisch und macht ihn ohne Browser prüfbar.
- **Bezug:** K 3, T 21.

## E-015 Mock-Daten aus dem Generator

- **Frage:** Woher bekommen die Mock-Plugins ihre Daten, und wie werden sie prüfbar?
- **Entscheidung:** Die Mock-Plugins lesen eine JSON-Datei im Format `kontor-mock-daten` Version 1 (`plugins.md` 4); der Generator erzeugt sie. Ohne Datei liefern sie einen eingebauten Datensatz mit festgelegten Mindesteigenschaften. Fortlaufende Zeit wird über ein simuliertes „heute“ abgebildet.
- **Begründung:** Erfüllt T 21 („Daten aus dem Generator“), ohne dass die Anwendung Code aus kontor-tests importiert; die Ausgabe ist exakt prüfbar.
- **Bezug:** K 3, T 21.

## E-016 Szenarien der Mock-Plugins

- **Frage:** Welche Szenarien gibt es in Meilenstein 1?
- **Entscheidung:** `normal`, `bankfehler`, `zeitueberschreitung`, `tan_erforderlich`, `token_ablauf` (Verhalten in `plugins.md`). `beitragsaenderung` später.
- **Begründung:** Deckt die in T 7/T 16/T 21 genannten Fehlerbilder an der Schnittstelle ab; Beitragsänderung braucht Split-Vorlagen (späterer Meilenstein).
- **Bezug:** T 7, T 16, T 21.

## E-017 Echte Plugins in Meilenstein 1

- **Frage:** Müssen FinTS- und IMAP-Plugin schon funktionieren?
- **Entscheidung:** Nein. Sie müssen per Konfiguration wählbar und erzeugbar sein (`name` fints/imap, `ist_mock` False), dürfen bei Abrufen `PluginNichtVerfuegbar` werfen und dürfen beim Erzeugen keine Verbindung aufbauen.
- **Begründung:** Bank-Synchronisation ist Meilenstein 2 (K 18); die Austauschbarkeit ist trotzdem schon prüfbar.
- **Bezug:** K 18, T 7.

## E-018 Kein Login in Meilenstein 1

- **Frage:** Ist die API in Meilenstein 1 durch Login geschützt?
- **Entscheidung:** Nein, Login später. Tests setzen keinen Login voraus.
- **Begründung:** Gehört nicht zum Umfang von Meilenstein 1; T 18 wird mit dem Login-Meilenstein ergänzt.
- **Bezug:** K 2, T 18.

## E-019 Einheitliches Fehlerformat

- **Frage:** Wie sehen Fehlerantworten aus?
- **Entscheidung:** Immer `{"fehler": {"code", "meldung", "details"}}`, auch für FastAPI-Validierungsfehler (422 `validierung`), unbekannte Pfade (404) und falsche Methoden (405). Pfad-Referenz unbekannt → 404, Körper-Referenz unbekannt → 422 `referenz_unbekannt`.
- **Begründung:** Maschinenlesbare Codes machen Tests unabhängig von Fehlertexten; ein einziges Schema ist einfach zu validieren.
- **Bezug:** T 2 (API-Tests gegen Spezifikation).

## E-020 Semantik der Buchungsliste

- **Frage:** Worauf beziehen sich Betragsfilter, Freitextsuche, Sortierung?
- **Entscheidung:** Betrag mit `konto_id` = Splitsumme auf diesem Konto, sonst Umsatz (Summe positiver Splits). Freitext = Teilzeichenkette nach `norm` (casefold, ä/ö/ü → ae/oe/ue) in Empfänger, Verwendungszweck, Split-Memos, Tags. Sortierung stabil mit id als Nachrang; Empfänger ohne Namen stehen am Ende. Paginierung `seite`/`pro_seite` (max. 500), Antwort mit `gesamt` und `summe`.
- **Begründung:** Eindeutig unabhängig nachrechenbar (T 14: „Ergebnis entspricht einer unabhängig berechneten Erwartung“); Umlaut-Unabhängigkeit nach T 14.
- **Bezug:** K 5, K 14, T 14.

## E-021 Mehrfachbearbeitung atomar

- **Frage:** Was passiert, wenn eine von mehreren markierten Buchungen nicht geändert werden kann?
- **Entscheidung:** Nichts wird geändert; die Antwort nennt die betroffenen IDs in `details.buchung_ids`.
- **Begründung:** „Ändert genau die markierten Buchungen“ ist so ohne Teilzustände prüfbar.
- **Bezug:** K 5, T 14.

## E-022 Änderungsprotokoll und Rückgängig

- **Frage:** Gehören die Invarianten 5 und 6 (Änderungsprotokoll, Undo) zu Meilenstein 1?
- **Entscheidung:** Nein, später. Sie werden nicht getestet.
- **Begründung:** Nicht im Umfang von Meilenstein 1; das Protokoll ist in K 14 eine eigene Grundfunktion.
- **Bezug:** T 3.5, T 3.6, K 14.

## E-023 XML-Sicherheit beim Import

- **Frage:** Wie wird mit DTDs und Entitäten in .kmy-Dateien umgegangen?
- **Entscheidung:** `<!DOCTYPE KMYMONEY-FILE>` ohne internen Teil ist erlaubt; jede DTD mit internem Teil (Entitätsdeklarationen) wird als `import_format_ungueltig` abgelehnt; externe Ressourcen werden nie geladen.
- **Begründung:** KMyMoney schreibt nie Entitäten; Ablehnen schützt vor Entitätsexpansion und dem Auslesen von Dateien.
- **Bezug:** T 18 (Sicherheit, vorgezogen für den Import).

## E-024 Testlauf ohne installierte Anwendung

- **Frage:** Was passiert, wenn die Tests laufen, das Paket `kontor` aber nicht installiert oder nicht importierbar ist?
- **Entscheidung:** Jeder Test unter `tests/app/` schlägt mit einer deutlichen deutschen Meldung fehl (Ursache und Installationshinweis). Mit `pytest --ohne-app` oder `KONTOR_TESTS_OHNE_APP=1` werden die App-Tests stattdessen übersprungen. Generator- und Spezifikationstests (`tests/generator`, `tests/spec`) laufen immer, auch ohne Anwendung. Die Kopfzeile des Testlaufs zeigt, ob und welche Anwendung gefunden wurde.
- **Begründung:** Ein stilles Überspringen würde eine fehlende oder kaputte Installation in der CI als grünen Lauf erscheinen lassen. Das Überspringen ist nur bewusst per Schalter möglich, z. B. für Arbeiten an Spezifikation und Generator.
- **Bezug:** T 1 (Tests laufen in der CI gegen die Implementierung).

## E-025 Fehlercode für IBAN an Nicht-Bestandskonten

- **Frage:** `datenmodell.md` 2 erlaubt eine IBAN nur bei Bestandskonten, nennt aber keinen Fehlercode, wenn sie bei `aufwand`, `ertrag` oder `eigenkapital` angegeben wird.
- **Entscheidung:** Antwort 422 mit Code `validierung` oder `iban_ungueltig`; die Tests akzeptieren beide Codes. Das Konto bleibt unverändert bzw. wird nicht angelegt.
- **Begründung:** Beide Codes sind in `openapi.yaml` für 422 vorgesehen und fachlich vertretbar; eine nachträgliche Festlegung auf einen würde eine bereits begonnene Implementierung ohne fachlichen Gewinn brechen.
- **Bezug:** K 4 (Kontotypen), `datenmodell.md` 2.

## E-026 Gesperrte Buchung und unveränderter Wert

- **Frage:** Ist bei einer abgeglichenen Buchung das Setzen eines Felds auf seinen bisherigen Wert (z. B. gleiches `datum`, gleiche Kategorie) eine „Änderung“, die mit 409 `buchung_gesperrt` abzulehnen ist?
- **Entscheidung:** Offen gelassen: Die Tests akzeptieren in diesem Fall 200 (ohne Wirkung) oder 409 `buchung_gesperrt`. Jede tatsächliche Änderung von `datum`, `empfaenger_id`, `verwendungszweck`, Splits oder Kategorie sowie jedes Löschen und jedes Ersetzen der Splits wird mit 409 abgelehnt.
- **Begründung:** Beide Lesarten erfüllen den Zweck der Sperre (T 13: Schutz vor versehentlicher Änderung); der Fall hat keine fachliche Wirkung.
- **Bezug:** K 4, T 4, T 13, `datenmodell.md` 3.1, E-008.

## E-027 Meilensteinplan

- **Frage:** Wie wird der Restumfang des Konzepts (K 3–14) nach Meilenstein 1 geschnitten?
- **Entscheidung:** Sieben weitere Meilensteine laut `spec/meilensteine.md`: M2 Bank-Synchronisation und Regel-Kategorisierung, M3 Änderungsprotokoll/Empfänger/Umbuchungen/Abstimmung/Suche, M4 GnuCash/Lernmodell/Split-Vorlagen, M5 Wiederkehrende/Kredite/Berichte/Export, M6 echte Anbindungen und ntfy, M7 Sicherheit und Betrieb, M8 Oberfläche mit Playwright. K 15 und K 16 bleiben draußen.
- **Begründung:** M2 ist durch K 18 vorgegeben. Das Änderungsprotokoll kommt früh (M3), weil fast alle späteren Funktionen automatische Änderungen erzeugen, die protokolliert werden müssen (T 3.5). Echte Fremdsysteme und Login kommen spät, weil sie Tests nur erschweren, aber keine Fachlogik tragen; die Oberfläche kommt zuletzt, weil sie nur spezifizierte Endpunkte bedient. Jeder Schnitt ist für einen Agenten in einem Durchgang machbar.
- **Bezug:** K 18, T 1.

## E-028 Echte Fremdsysteme nur über Attrappen

- **Frage:** Wie werden echte Plugins (FinTS, IMAP/OAuth2, ntfy) getestet, ohne echte Daten oder Dienste zu verwenden?
- **Entscheidung:** Echte Plugins werden implementiert (M6), in Tests aber nur gegen lokale Attrappen auf Protokollebene betrieben (FinTS-Attrappe mit festgelegten synthetischen Antworten, IMAP- und OAuth2-Attrappe, ntfy als lokaler HTTP-Empfänger). Tests laufen mit gesperrtem Netz bis auf die lokale Attrappe. Kein Test spricht je eine echte Bank, Gmail oder einen ntfy-Server an; es gibt keine echten Zugangsdaten, PINs, TANs oder Tokens im Repository. Bis M6 genügt der Nachweis, dass echte Plugins erzeugbar sind und keine Verbindung aufbauen (E-017).
- **Begründung:** T 7, T 16 und T 21 verlangen Attrappen und synthetische Daten; echte Dienste wären weder reproduzierbar noch zulässig. Die Protokollebene prüft auch die echte Bibliothekseinbindung.
- **Bezug:** K 3, K 6, K 13, T 7, T 16, T 17, T 21.

## E-029 Rückwärtskompatible Erweiterung des Vertrags

- **Frage:** Wie werden Schemas und Schnittstellen aus M1 für M2 erweitert, ohne dass M1-Tests brechen?
- **Entscheidung:** Neue Felder bestehender Antwortschemas (z. B. `Buchung.vorschlag`) sind im OpenAPI-Schema optional und werden in M2-Tests ausdrücklich verlangt. Neue Konfigurationsfelder haben Vorgaben, die das M1-Verhalten ergeben (kein automatischer Abruf). Neue Plugin-Fähigkeiten kommen als Schlüsselwortargumente bzw. optionale Schlüssel der Mock-Datendatei; die Menge der öffentlichen Plugin-Methoden, die Mock-Szenarien und das Datendateiformat (Version 1) bleiben gleich. M1-Tests werden nicht geändert; nur `tests/spec` (Liste der Operationen) wächst mit.
- **Begründung:** „M1-Tests unverändert lauffähig“ – eine M1-Implementierung bleibt gegenüber den M1-Tests grün, während die M2-Tests rot sind, bis M2 umgesetzt ist (Tests zuerst, T 1).
- **Bezug:** T 1, `spec/meilensteine.md`.

## E-030 Synchronisation synchron, Läufe protokolliert, Planer abschaltbar

- **Frage:** Wie wird die Synchronisation ausgelöst und in Tests deterministisch?
- **Entscheidung:** `POST /api/sync` führt einen Lauf synchron aus und antwortet immer 200 mit dem Lauf (auch bei Fehler oder TAN). Läufe werden mit Status je Konto gespeichert. Der Planer ist über `sync_intervall_minuten` (Vorgabe 0 = aus) und `planer_starten` konfigurierbar; sein Thread startet nur im ASGI-Lifespan. `kontor.sync.planer_takt(app)` führt einen Takt synchron aus. Fälligkeit: sofort ohne vorherigen Lauf, sonst Ende des letzten Laufs plus Intervall bzw. Wiederholungsabstand nach Fehlschlag.
- **Begründung:** Synchrone Läufe machen jeden Test ohne Warten prüfbar; mit der Vorgabe 0 starten Test-Apps und M1-Apps keinen Hintergrundabruf. `planer_takt` macht K 3 („Scheduler“) und T 7 („Wiederholung“) ohne Zeitabhängigkeit testbar.
- **Bezug:** K 3, K 6, T 7.

## E-031 Simulierte Uhr im Mock-Modus

- **Frage:** Wie werden „zeitlich fortlaufende“ Abrufe und TAN-Abläufe in Tests gesteuert?
- **Entscheidung:** Im Mock-Modus hat die App eine simulierte Uhr: `mock_heute` 12:00Z als Start, stellbar über `PUT /api/mock/zeit` (im Echtmodus 409 `nur_mock_modus`). Die App setzt vor jedem Plugin-Aufruf `setze_heute` des Mock-Plugins. Alle Zeitstempel der App folgen dieser Uhr und haben keine Sekundenbruchteile.
- **Begründung:** Erfüllt T 21 („zeitlich fortlaufend wie im echten Betrieb“) und macht Ablauf (TAN gültig bis 23:59:59) und Planerabstände ohne Warten prüfbar; der Echtmodus bleibt unberührt.
- **Bezug:** K 3, K 6, T 21.

## E-032 Zuordnung der Bankkonten über die IBAN

- **Frage:** Wie werden Bankkonten den Kontor-Konten zugeordnet?
- **Entscheidung:** Über die normalisierte IBAN; existiert kein Konto, legt der Lauf eines an (Art und Name aus dem Plugin, `extern_id = null`). Vorhandene Konten werden nicht verändert.
- **Begründung:** Die IBAN ist die einzige stabile gemeinsame Kennung von Bank, KMyMoney und Kontor. Ohne `extern_id` übernimmt ein späterer KMyMoney-Import das Konto über seine IBAN-Regel (`datenmodell.md` 10.3), sodass die Dublettenprüfung beider Richtungen greift.
- **Bezug:** K 6, K 12, T 6.

## E-033 Abbildung der Umsätze, Vormerkungen und Storno

- **Frage:** Wie wird ein Bankumsatz zur Buchung, und was geschieht mit Vormerkungen und Stornos?
- **Entscheidung:** Zwei Splits (Bestandskonto, Gegenkonto), Status `importiert`, Empfänger über den getrimmten Namen der Gegenpartei (angelegt bei Bedarf), Gegenkonto aus der ersten passenden Regel, sonst technisches Konto „Unkategorisiert“ (`kontor:unkategorisiert`, Eigenkapital). Vormerkungen werden nie gebucht und nicht gemerkt; Stornos werden als eigene Buchung übernommen.
- **Begründung:** Vormerkungen ändern sich bis zur Buchung oder verschwinden; sie zu buchen, würde Dubletten oder Korrekturen erzwingen. Ein eigenes technisches Konto hält Invarianten 1 und 4 ein und lässt „Kategorie setzen“ unverändert funktionieren (wie „Unausgeglichen“, E-012), ohne Synchronisation und Importausgleich zu vermischen. Storno-Verrechnung ist fachlich nicht gefordert.
- **Bezug:** K 4, K 6, T 7.

## E-034 Dublettenerkennung beim Abruf

- **Frage:** Wie verhindert die Synchronisation Dubletten – gegenüber früheren Abrufen und gegenüber Altbestand?
- **Entscheidung:** (1) Kennung `bank:<IBAN>:<umsatz_id>`; jede gebuchte oder zusammengeführte Kennung wird dauerhaft gemerkt und nie erneut gebucht, auch nach Löschen der Buchung. (2) Abgleich mit vorhandenen Buchungen je Bankkonto nach den Regeln von `datenmodell.md` 10.4 (exakt/ähnlich, Zweiphasenbewertung); Kandidaten sind alle Buchungen ohne Kennung desselben Bankkontos. Eindeutige Treffer werden zusammengeführt, Zweifelsfälle als Dublettenverdacht vorgelegt.
- **Begründung:** Erfüllt K 6 und T 6 („wiederholter Bankabruf desselben Zeitraums erzeugt keine Dubletten“) auch bei überlappenden Zeiträumen. Dieselben Regeln wie beim Import machen das Verhalten in beiden Richtungen gleich; die Auswertung je Bankkonto erlaubt, dass beide Seiten einer importierten Umbuchung mit derselben Buchung zusammengeführt werden. Gemerkte Kennungen verhindern, dass bewusst gelöschte Buchungen wieder auftauchen.
- **Bezug:** K 6, K 12, T 6.

## E-035 Fehlerbehandlung, Wiederholung, interne Benachrichtigungen

- **Frage:** Was geschieht bei Bankfehlern, und wie wird ohne ntfy benachrichtigt?
- **Entscheidung:** Fehler werden je Konto festgehalten, andere Konten laufen weiter, jedes Konto wird atomar geschrieben. Ein Pluginfehler erzeugt nie eine 5xx-Antwort. Der Planer wiederholt nach `sync_wiederholung_minuten`. M2 führt eine interne Benachrichtigungsliste mit Entprellschlüssel ein: Solange eine ungelesene Benachrichtigung mit gleichem Schlüssel existiert, entsteht keine neue. Die Zustellung per ntfy und Erinnerungen folgen in M6.
- **Begründung:** T 7 („Benachrichtigung und Wiederholung, ohne Datenverlust“) und T 17 („keine Nachrichtenflut“) werden so ohne Fremdsystem prüfbar; M6 muss nur noch zustellen.
- **Bezug:** K 3, K 6, T 7, T 17.

## E-036 TAN-Ablauf

- **Frage:** Wie wird eine TAN-Anforderung gespeichert, angezeigt und beantwortet, ohne die Plugin-Schnittstelle zu brechen?
- **Entscheidung:** `TanErforderlich` trägt zusätzlich Anweisungstext und Bild. Die App speichert eine TAN-Anforderung (ohne interne Kennung, TAN, PIN), liefert das Bild unverändert aus und übergibt die TAN per Schlüsselwortargument `umsaetze(…, tan=TanAntwort(…))` an dieselbe Plugin-Instanz. Falsche TAN: 422, Anforderung bleibt offen. Ablauf nach `gueltig_bis` (App-Uhr): Anforderung `abgelaufen`, Lauf `abgebrochen`, Benachrichtigung. Neustart bricht offene Anforderungen ab. Mock: TAN aus `bank.tan` (Vorgabe `123456`), Freigabe je Instanz und Tag, deterministisches PNG.
- **Begründung:** Bildet K 6 Schritte 1, 3, 4 ab; die öffentliche Methodenmenge der Plugins (M1-Test „nur lesend“) bleibt gleich. python-fints hält den Dialog ebenfalls im Arbeitsspeicher, daher ist ein Neustart ein sauberer Abbruch (T 20).
- **Bezug:** K 6, T 7, T 20.

## E-037 PIN nur im Arbeitsspeicher

- **Frage:** Wie wird die Banking-PIN in M2 behandelt?
- **Entscheidung:** Nur die Variante „bei Bedarf eingeben, nur im Arbeitsspeicher“: `PUT /api/sync/pin`, Übergabe an das Plugin über eine `pin_quelle`, nie gespeichert oder ausgegeben; nach `BankPinFalsch` sofort verworfen. Das Mock-Plugin verlangt eine PIN nur, wenn die Datendatei `bank.pin` enthält. Tests suchen eine eindeutige synthetische PIN in allen Datenbankdateien, Logs, Ausgaben und Antworten. systemd-creds/TPM folgt in M6.
- **Begründung:** K 6 nennt diese Variante ausdrücklich; sie ist ohne Betriebssystemabhängigkeit prüfbar. Verwerfen nach falscher PIN verhindert, dass der Planer das Bankkonto sperren lässt.
- **Bezug:** K 6, T 18 („keine Geheimnisse in Logs oder Fehlermeldungen“).

## E-038 Regeln: Bedingungen und Priorität

- **Frage:** Welche Bedingungen haben Regeln, und welche Regel gewinnt?
- **Entscheidung:** Bedingungen auf Empfänger und Verwendungszweck (`enthaelt`, `gleich`, `beginnt_mit`, normalisiert wie die Freitextsuche), Regelbetrag (`gleich`, `mindestens`, `hoechstens`; Sicht der eigenen Konten) und Konto (`gleich`), UND-verknüpft, 1–20 je Regel. Keine regulären Ausdrücke. Reihenfolge: `prioritaet` aufsteigend, dann `id`; die erste passende aktive Regel gewinnt.
- **Begründung:** Deckt K 7 („Empfänger enthält REWE → Lebensmittel“) und den Auftrag (Empfänger, Verwendungszweck, Betrag) ab; eine Gesamtordnung ohne Gleichstand macht T 8 („festgelegte, getestete Priorität“) eindeutig. Reguläre Ausdrücke wären schwer gleich zu implementieren und anfällig für sehr langsame Muster.
- **Bezug:** K 7, T 8.

## E-039 Vorschläge und Bestätigung

- **Frage:** Wie werden automatisch gesetzte Kategorien als Vorschlag markiert und bestätigt?
- **Entscheidung:** Die Kategorie wird sofort in den Gegensplit geschrieben, zusätzlich trägt die Buchung `vorschlag = {kategorie_id, regel_id, quelle, vorher_konto_id}`. Erledigt durch annehmen, ablehnen (zurück auf `vorher_konto_id`), manuelles Kategorie setzen, Splits ersetzen oder Statuswechsel auf `bestaetigt`/`abgeglichen`. Filter `vorschlag=true|false`.
- **Begründung:** Salden und Kontenübersicht zeigen sofort die wahrscheinliche Kategorie, die Markierung bleibt bis zur Bestätigung sichtbar (K 7, T 8). `vorher_konto_id` macht Ablehnen verlustfrei. Der Status bleibt unabhängig, weil `vorlaeufig → bestaetigt` unzulässig ist (E-008).
- **Bezug:** K 4, K 7, T 8.

## E-040 Regeln auf vorhandene Buchungen anwenden

- **Frage:** Wie werden Regeln nachträglich auf vorhandene Buchungen angewendet?
- **Entscheidung:** Nur ausdrücklich über `POST /api/regeln/anwenden`, standardmäßig nur auf unkategorisierte (Gegensplit auf Eigenkapital), nie auf abgeglichene, mit Probelauf (`trocken`). Bestehende Vorschläge behalten ihr `vorher_konto_id`. Automatisch kategorisiert werden nur neue Buchungen aus der Synchronisation.
- **Begründung:** Erfüllt „optional vorhandene Buchungen“, ohne bestätigte Kategorien aus KMyMoney stillschweigend zu überschreiben.
- **Bezug:** K 7, T 8.

## E-041 Marker je Meilenstein und Testverzeichnis

- **Frage:** Wie lassen sich M2-Tests getrennt auswählen?
- **Entscheidung:** M2-Tests liegen in `tests/app/m2/` und erhalten automatisch den Marker `m2`; Tests direkt in `tests/app/` erhalten `m1`. Auswahl mit `python -m pytest -m m2` bzw. `-m m1`. Die Marker `app`, `kern`, `langsam` bleiben.
- **Begründung:** Ein Verzeichnis je Meilenstein macht den Umfang sichtbar, M1-Dateien bleiben unverändert.
- **Bezug:** T 1, E-029.

## E-042 Vertragsprüfung von Nicht-JSON-Antworten

- **Frage:** Wie prüft der Testclient Antworten, die kein JSON sind (TAN-Bild)?
- **Entscheidung:** `openapi.yaml` erlaubt dort `image/*`; der Vertragsprüfer prüft nur, dass der `Content-Type` zu einer erlaubten Medienart passt (Muster mit `/*`). Fehlerantworten bleiben immer JSON mit Schema `Fehler`.
- **Begründung:** Das Bild ist ein Rohbyte-Strom; sein Inhalt wird im Test gegen die Bytes des Mock-Plugins verglichen.
- **Bezug:** K 6, T 2.

## E-043 Konto mit Regelbezug nicht löschbar

- **Frage:** Was geschieht beim Löschen eines Kontos, auf das eine Regel verweist?
- **Entscheidung:** 409 `konto_in_verwendung`, wie bei Splits oder Unterkonten. Löschen einer Regel setzt `regel_id` in Vorschlägen auf null.
- **Begründung:** Keine Regel darf auf ein nicht existierendes Konto zeigen; der Vorschlag bleibt nachvollziehbar markiert.
- **Bezug:** K 7, `datenmodell.md` 2.

## E-044 Schnitt und Dokumente von Meilenstein 3

- **Frage:** Wie wird M3 (`spec/meilensteine.md`) spezifiziert, ohne M1/M2 zu brechen?
- **Entscheidung:** Zwei neue Dokumente: `spec/api/protokoll.md` (Änderungsprotokoll, Rückgängig) und `spec/api/buchhaltungspflege.md` (Empfänger, Erfassungshilfe, Umbuchungen, Abstimmung, Volltextsuche); je ein M3-Abschnitt in `datenmodell.md` (13), `synchronisation.md` (14), `kategorisierung.md` (6), `python-api.md` (9). `openapi.yaml` Version 2.1.0 (Minor: nur Ergänzungen, neue Felder optional). Der Plan in `meilensteine.md` bleibt unverändert; einzige Präzisierung: die Statistik-Aussage aus T 11 wird in M3 über Kontensalden geprüft, Berichte bleiben M5 (E-059).
- **Begründung:** Eigene Dokumente halten die großen Themen lesbar; die M3-Abschnitte zeigen, wo bestehendes Verhalten erweitert wird. Minor-Version, weil kein bestehender Vertrag geändert wird (E-029).
- **Bezug:** K 14, T 1, E-029.

## E-045 Buchbestand, Protokollform und Nettowirkung

- **Frage:** Was genau wird protokolliert, und wie wird „vorher/nachher“ prüfbar dargestellt?
- **Entscheidung:** Protokolliert wird der *Buchbestand*: Konten, Empfänger, Tags, Buchungen, Regeln, Dublettenverdachte, Abstimmungen (sichtbar) und gemerkte Umsatzkennungen (intern). Läufe, TAN, Benachrichtigungen, Importvorgänge, PIN, Uhr nicht. Jede Änderung trägt je geändertem Objekt genau einen Eintrag mit der *Protokollform* vor und nach der Operation (Nettowirkung); die Protokollform ist die REST-Darstellung ohne abgeleitete Felder (`protokoll.md` 2).
- **Begründung:** Die Protokollform ist aus öffentlichen Antworten ableitbar; Tests können deshalb für jede Operation unabhängig nachrechnen, dass genau die veränderten Objekte mit genau ihren Zuständen protokolliert sind (T 3.5). Ohne abgeleitete Felder ändert z. B. ein Tag-Umbenennen keine Buchung, und die Einträge bleiben klein.
- **Bezug:** K 14, T 3.5, T 3.6.

## E-046 Keine Änderung ohne Wirkung; Einheiten der Synchronisation

- **Frage:** Erzeugt jede Anfrage eine Änderung, und wie wird die Synchronisation geschnitten?
- **Entscheidung:** Nur Operationen, die mindestens eine Protokollform verändern, erzeugen eine Änderung (sonst keine, auch nicht bei Fehlern, Probeläufen, wiederholtem Import). Je REST-Operation höchstens eine Änderung. Die Synchronisation erzeugt je Lauf höchstens eine `sync_kontozuordnung`, je verarbeitetem Konto höchstens eine `sync_konto` und ggf. je Konto eine `umbuchung_erkennen`; alle mit der Gruppe `sync:<lauf_id>`. Ein Import bildet eine Änderung mit Gruppe `import:<id>`.
- **Begründung:** Leere Änderungen würden das Protokoll füllen und „genau ein Eintrag je Änderung“ unprüfbar machen. Der Schnitt der Synchronisation folgt ihrer Atomarität (`synchronisation.md` 4.5): Was einzeln geschrieben wird, ist einzeln rückgängig zu machen; die Gruppe erlaubt den ganzen Lauf.
- **Bezug:** T 3.5, T 3.7, K 6.

## E-047 Rückgängig mit Zustands- und Bezugsprüfung

- **Frage:** Darf nur die jeweils letzte Änderung rückgängig gemacht werden, und wann wird abgelehnt?
- **Entscheidung:** Jede wirksame Änderung kann rückgängig gemacht werden, wenn (1) jedes betroffene Objekt noch genau den Zustand `nachher` hat und (2) der Buchbestand danach alle Bezugs- und Eindeutigkeitsregeln erfüllt. Sonst 409 `rueckgaengig_konflikt`, nichts ändert sich. Wiederhergestellte Objekte und Splits erhalten ihre alten IDs (IDs werden nie neu vergeben, `datenmodell.md` 1). Rückgängig ist selbst eine Änderung und kann wiederum rückgängig gemacht werden (Wiederholen). Mehrere Änderungen bzw. eine Gruppe werden atomar in absteigender Reihenfolge behandelt.
- **Begründung:** Die zustandsbasierte Prüfung erlaubt das gezielte Zurücknehmen unabhängiger älterer Änderungen (z. B. einer Regelanwendung, obwohl danach Tags gesetzt wurden), schließt aber jeden Verlust späterer Arbeit aus; sie ist ohne Kenntnis der Implementierung exakt testbar (T 3.6: „exakt wiederhergestellt“). Gleiche IDs machen die Wiederherstellung auch für Verweise (Verdachte, Vorschläge) exakt.
- **Bezug:** K 14, T 3.6, `datenmodell.md` 1.

## E-048 Rückgängig unabhängig von Status- und Sperrregeln

- **Frage:** Darf Rückgängig eine abgeglichene oder abgestimmte Buchung verändern bzw. einen sonst unzulässigen Statusübergang bewirken?
- **Entscheidung:** Ja. Rückgängig stellt einen protokollierten früheren Zustand wieder her; Statusübergänge und Sperre gelten dafür nicht. Eine Buchung, die *nach* der rückgängig zu machenden Änderung abgestimmt oder abgeglichen wurde, hat einen anderen Zustand als `nachher`; der Versuch scheitert also an der Zustandsprüfung (E-047).
- **Begründung:** Sonst ließe sich z. B. eine versehentliche Abstimmung oder ein versehentliches „abgeglichen“ nicht zurücknehmen. Der Schutz vor *versehentlicher* Änderung (T 13) bleibt, weil Rückgängig nur die jeweils jüngste wirksame Fassung eines Objekts zurücknehmen kann.
- **Bezug:** T 4, T 13, E-008.

## E-049 Empfänger zusammenführen auch bei gesperrten Buchungen

- **Frage:** Darf das Zusammenführen von Empfängern `empfaenger_id` gesperrter Buchungen ändern?
- **Entscheidung:** Ja (Ausnahme von der Sperre, wie Tags). Alles andere an gesperrten Buchungen bleibt geschützt.
- **Begründung:** Zusammenführen ist Stammdatenpflege ohne Wirkung auf Beträge, Daten oder Salden; ohne Ausnahme könnte man Empfänger nach der ersten Abstimmung praktisch nie mehr zusammenführen.
- **Bezug:** K 14, T 13, T 14, E-008.

## E-050 Aliase

- **Frage:** Wie werden Aliase verglichen, und wo wirken sie?
- **Entscheidung:** Ein Name passt zu einem Alias bei gleichem, nicht leerem `ekey` (wie der Empfängervergleich der Dublettenerkennung). Aliase sind über alle Empfänger eindeutig (409 `alias_existiert`). Zuordnung eines Namens: exakter Name → Alias → neu anlegen; das gilt für die Synchronisation, die Erfassungshilfe und – als dritte Regel nach `extern_id` und exaktem Namen – den KMyMoney-Import. Beim Zusammenführen werden Namen und Aliase der Quellen zu Aliasen des Ziels.
- **Begründung:** `ekey` gleicht Groß-/Kleinschreibung, Umlautschreibweisen und Satzzeichen aus, ohne unscharf zu werden; Eindeutigkeit macht die Zuordnung deterministisch. Mit den Namen der Quellen als Aliase greift das Zusammenführen auch bei künftigen Importen (T 14). Ohne Aliase ist alles wie in M1/M2.
- **Bezug:** K 14, T 14, E-010, E-011.

## E-051 Standardkategorie und Empfängername bei der Synchronisation

- **Frage:** Wo steht die Standardkategorie in der Kategorisierung, und welcher Name gilt für Regeln und Abgleich, wenn ein Alias greift?
- **Entscheidung:** Reihenfolge Regel → Standardkategorie → „Unkategorisiert“; die Standardkategorie wird als Vorschlag mit `quelle = "standardkategorie"` und `regel_id = null` gesetzt und zählt in `buchungen_kategorisiert`. Für Regelauswertung und Empfängervergleich gilt der Name des zugeordneten Empfängers (Alias aufgelöst); ohne Aliase ist das `gegenpartei_name.strip()` wie in M2. Die Standardkategorie wirkt bei neuen Buchungen (Synchronisation, Erfassungshilfe), nicht rückwirkend.
- **Begründung:** Der Meilensteinplan legt die Stufe zwischen Regel und Lernmodell fest; als Vorschlag bleibt sie bis zur Bestätigung markiert (K 7). Aliase sollen die Kategorisierung verbessern (K 17), also müssen Regeln den bereinigten Namen sehen.
- **Bezug:** K 7, K 14, T 8, T 14, E-038, E-039.

## E-052 Erfassungshilfe für manuelle Buchungen

- **Frage:** Wie werden Korrekturen und Umbuchungen „von Hand erfasst“, ohne den M1-Endpunkt zu ändern?
- **Entscheidung:** Zusätzlicher Endpunkt `POST /api/buchungen/erfassen` mit den Arten `ausgabe`, `einnahme`, `umbuchung`, `korrektur`, positivem Betrag (Korrektur: vorzeichenbehaftet ≠ 0) und fester Splitbildung; Gegenkonto ohne Kategorie „Unkategorisiert“ bzw. für Korrekturen das technische Konto „Korrekturen“. Neuer Fehlercode `konto_ungueltig` für Nicht-Bestandskonten bzw. gleiche Konten. `POST /api/buchungen` bleibt unverändert.
- **Begründung:** Die vereinfachte Form vermeidet Vorzeichenfehler bei der Eingabe; das Ergebnis ist eine gewöhnliche Buchung, für die dieselben Invarianten und Regeln gelten (T 14). Ein eigenes Korrekturkonto hält Korrekturen von unkategorisierten Bankumsätzen getrennt.
- **Bezug:** K 14, T 14.

## E-053 Umbuchungserkennung

- **Frage:** Was heißt „gleicher Betrag mit umgekehrtem Vorzeichen, kurzes Zeitfenster, passende eigene IBAN“, und was geschieht bei Mehrdeutigkeit?
- **Entscheidung:** Kandidaten sind nicht gesperrte Buchungen mit genau einer Bankseite und einem Gegensplit auf „Unkategorisiert“. Zwei Kandidaten passen bei verschiedenen Konten, Betrag `x = −y`, Datumsabstand ≤ `umbuchung_fenster_tage` (Vorgabe 3) und passender Gegen-IBAN: keine Seite nennt eine andere IBAN als die des Gegenkontos, mindestens eine nennt genau diese. Dafür speichert die Synchronisation die Gegen-IBAN in `Buchung.gegen_iban`. Zusammengeführt werden nur gegenseitig eindeutige Paare; die ältere Buchung bleibt, die Bankseite der jüngeren wird mit unveränderter Split-ID übernommen. Mehrdeutige Paare bleiben stehen und lassen sich von Hand zusammenführen; Trennen geschieht über Rückgängig.
- **Begründung:** Kreditkartenumsätze nennen oft keine Gegen-IBAN, deshalb genügt eine Seite; eine widersprechende Gegen-IBAN schließt fremde Empfänger sicher aus (T 11). Gegenseitige Eindeutigkeit macht das Ergebnis reihenfolgeunabhängig und vermeidet falsche Paare (wie E-011). Bereits kategorisierte Buchungen bleiben unangetastet, damit keine bestätigte Entscheidung überschrieben wird.
- **Bezug:** K 14, K 17, T 11.

## E-054 Automatische Umbuchungserkennung abschaltbar, Vorgabe aus

- **Frage:** Läuft die Umbuchungserkennung bei jeder Synchronisation?
- **Entscheidung:** Nur bei `umbuchung_automatisch = True` (`KONTOR_UMBUCHUNG_AUTOMATISCH`); Vorgabe `False`. Unabhängig davon gibt es `POST /api/umbuchungen/erkennen`. Für den Betrieb wird `True` empfohlen.
- **Begründung:** Die M2-Tests erwarten je Bankumsatz eine eigene Buchung (z. B. eine Kennung je neuer Buchung). Mit Vorgabe `False` bleibt eine M3-Implementierung gegen alle M2-Tests grün (E-029), genau wie beim Planer (`sync_intervall_minuten = 0`, E-030).
- **Bezug:** T 11, E-029, E-030.

## E-055 Kontenabstimmung je Split, Sperre, Aufheben

- **Frage:** Wird eine Buchung oder ein Split abgestimmt, und wie hängt das mit dem Status `abgeglichen` zusammen?
- **Entscheidung:** Abgestimmt wird je Split (`Split.abstimmung_id`), wie das Abgleichskennzeichen in KMyMoney; eine Umbuchung kann so auf einem Konto abgestimmt sein, auf dem anderen noch nicht. Eine Buchung mit mindestens einem abgestimmten Split ist gesperrt wie eine abgeglichene; der Status ändert sich durch Abstimmen nicht (`abgeglichen` bleibt dem Kreditabgleich in M5 vorbehalten). Bei Differenz antwortet die Abstimmung 200 mit Differenz und ändert nichts. Aufheben nur für die letzte Abstimmung eines Kontos; Abstimmen mit Probelauf (`trocken`).
- **Begründung:** „abgeglichen“ ist ab „bestätigt“ erreichbar, Bankumsätze sind aber „importiert“ (E-008); ein eigenes Kennzeichen vermeidet Statussprünge. Die Sperre „baut auf der Sperre aus M1 auf“ (Plan) und schützt gegen versehentliche Änderung (T 13). Nur die letzte Abstimmung aufzuheben hält die Abstimmungsreihe eines Kontos lückenlos.
- **Bezug:** K 4, K 14, T 13, E-008, E-026.

## E-056 Volltextsuche

- **Frage:** Wie verhält sich die Volltextsuche, und wie weit geht die Umlaut-Unabhängigkeit?
- **Entscheidung:** Eigener Endpunkt `GET /api/suche` mit getrennten Trefferlisten für Konten, Empfänger (inkl. Aliase), Tags und Buchungen. Wörter werden UND-verknüpft, jedes Wort darf in einem anderen Feld treffen. Normalisierung `snorm` = NFC, `norm` aus M1, dann Akzente entfernen (NFKD ohne Kombinationszeichen). Buchungen werden auch über die Namen ihrer Konten gefunden. Die M1-Freitextsuche der Buchungsliste bleibt unverändert.
- **Begründung:** „Normalisierung wie M1“ (Plan) bleibt der Kern (ä → ae, ß → ss, Groß/klein); NFC macht zerlegte Umlaute aus Bankdaten gleichwertig, die Akzentfaltung findet „Café“ mit „Cafe“. UND über Wörter ist die übliche Erwartung an eine Suche („rewe 2024“). Die Festlegung über die Python-Standardbibliothek ist exakt nachrechenbar.
- **Bezug:** K 14, T 14, E-020.

## E-057 Rückgängig und Synchronisationszustand

- **Frage:** Was geschieht mit gemerkten Umsatzkennungen und dem Zustand je Bankkonto, wenn ein Lauf rückgängig gemacht wird?
- **Entscheidung:** Gemerkte Kennungen gehören zum Buchbestand: Rückgängig vergisst die Kennungen, die die Änderung gemerkt hat (Wiederholen merkt sie wieder). Normales Löschen einer Buchung vergisst sie weiterhin nicht (E-034). `/api/sync/konten` bleibt unverändert, außer ein durch Rückgängig entferntes Konto verliert seinen Eintrag.
- **Begründung:** Nach dem Zurücknehmen eines Laufs soll ein erneuter Abruf dieselben Umsätze wieder übernehmen; sonst wäre der Zustand nicht „exakt wie vorher“ (T 3.6). `letzter_abruf_bis` ist Betriebszustand, kein Buchbestand.
- **Bezug:** T 3.6, T 6, E-034.

## E-058 Marker und Testverzeichnis für Meilenstein 3

- **Frage:** Wie werden M3-Tests ausgewählt?
- **Entscheidung:** M3-Tests liegen in `tests/app/m3/` und erhalten automatisch den Marker `m3`; M3-Generatortests tragen `m3` ausdrücklich. Wie E-041.
- **Begründung:** Einheitlich mit M2; M1- und M2-Tests bleiben unverändert.
- **Bezug:** E-041, E-029.

## E-059 Umbuchungen in Statistiken

- **Frage:** Wie wird T 11 („Umbuchungen erscheinen in Statistiken weder als Einnahme noch als Ausgabe“) in M3 geprüft, solange es keine Berichte gibt?
- **Entscheidung:** Über die Kontensalden: Eine zusammengeführte Umbuchung bucht auf kein Konto der Arten `aufwand`/`ertrag`, ihre `kategorie_id` ist null und `ist_umbuchung` wahr; die Salden aller Aufwands- und Ertragskonten bleiben beim Zusammenführen unverändert. Berichte (M5) werten `ist_umbuchung` aus.
- **Begründung:** Ein eigener Statistik-Endpunkt gehört zu den Berichten (K 11, M5); die Eigenschaft ist schon jetzt über die doppelte Buchführung vollständig prüfbar.
- **Bezug:** K 11, K 14, T 11, `spec/meilensteine.md`.

## E-060 Benutzte Konten und Kategorien löschen

- **Frage:** Wie wird ein Konto oder eine Kategorie gelöscht, auf die noch Buchungen verweisen? Bisher war das nur ohne Splits, Unterkonten, Regel-, Standardkategorie- und Abstimmungsbezug möglich (409 `konto_in_verwendung`).
- **Entscheidung:** Neue Operation `POST /api/konten/{konto_id}/loeschen` mit drei Varianten für die betroffenen Buchungen: löschen, dem Elternkonto zuschlagen oder nach „Unkategorisiert“ umbuchen. Probelauf mit `trocken`. Eine Änderung `konto_loeschen_mit_buchungen` im Protokoll, rückgängig machbar. `DELETE /api/konten/{konto_id}` bleibt unverändert. Fachliche Regeln: `spec/api/loeschen.md`. Teil von M3, Tests in `tests/app/m3/` (E-058).
- **Begründung:** Auftrag des Anwenders vom 2026-11-08: „Es muss möglich sein, Konten und Kategorien zu löschen. Es muss gefragt werden, wie mit den Buchungen umgegangen wird.“ Ein eigener Endpunkt hält das Verhalten von `DELETE` unverändert (E-029). Er ist eine POST-Aktion, weil DELETE mit Körper unüblich ist. Für „unkategorisiert“ dient das vorhandene technische Konto „Unkategorisiert“. Es hat die Art `eigenkapital` und nimmt deshalb Splits jeder Kontoklasse auf, auch die von Bestandskonten.
- **Bezug:** K 4, K 5 (Kontextmenü auf Konten), K 14 (Änderungsprotokoll), `datenmodell.md` 2.

## E-061 Keine Vorgabe für den Umgang mit Buchungen

- **Frage:** Braucht die Anfrage Vorgabewerte für `buchungen` und `konflikte`?
- **Entscheidung:** Nein. Beide Felder sind Pflicht, auch `konflikte` bei der Variante `loeschen`, wo es nichts bewirkt. Die Oberfläche bietet keine Vorauswahl.
- **Begründung:** Der Auftrag verlangt ausdrücklich, dass gefragt wird. Eine Vorgabe würde stilles Löschen von Buchungen ermöglichen. Ein durchgehend gleiches Anfrageschema ist einfacher als bedingte Pflichtfelder.
- **Bezug:** K 5, `loeschen.md` 2.

## E-062 Konfliktbuchungen: Quelle und Ziel auf demselben Konto

- **Frage:** Was geschieht mit Buchungen, deren Splits nach dem Umbuchen alle auf demselben Konto liegen? Beispiele: Eine Umbuchung zwischen zwei gelöschten Bestandskonten geht danach von „Unkategorisiert“ nach „Unkategorisiert“. Oder eine Buchung zwischen Unterkonto und Elternkonto, wenn das Unterkonto dem Elternkonto zugeschlagen wird.
- **Entscheidung:** Solche Buchungen heißen Konfliktbuchungen. Antwort und Probelauf führen sie einzeln auf, die Anfrage entscheidet über `konflikte`. Bei `loeschen` wird die Buchung gelöscht. Bei `behalten` bleibt sie mit allen Splits auf dem Zielkonto bestehen, ohne Zusammenfassen. Kein neuer Buchungsstatus.
- **Begründung:**
  - Eine solche Buchung bewirkt nichts mehr (Summe 0 auf einem Konto) und verfälscht Umsatzlisten. Deshalb muss der Anwender bewusst entscheiden.
  - Behalten erhält Datum, Empfänger und Verwendungszweck zum späteren Neuzuordnen. Es verletzt keine Invariante, weil mindestens zwei Splits mit Summe 0 bleiben.
  - Ein neuer Status hätte die Statusübergänge aus M1 verändert.
- **Bezug:** K 4, T 3.1–3.4, T 4.

## E-063 Unterkonten rücken nach oben, Splits auf dem Zielkonto werden zusammengefasst

- **Frage:** Was geschieht mit Unterkonten des gelöschten Kontos, und was mit mehreren Splits einer Buchung, die danach auf demselben Konto buchen?
- **Entscheidung:**
  - Unterkonten erhalten das Elternkonto des gelöschten Kontos und werden nie mitgelöscht.
  - Splits einer Buchung, die nicht in Konflikt steht und die danach auf dem Zielkonto buchen, werden zusammengefasst: Position und ID des ersten, Summe der Beträge, Memos mit `" / "` verbunden.
  - Abgestimmte Splits werden nie zusammengefasst.
- **Begründung:**
  - Rekursives Löschen ganzer Teilbäume wäre eine zweite, schwer überschaubare Entscheidung im selben Dialog. Wer einen Teilbaum loswerden will, löscht die Unterkonten einzeln.
  - Das Zusammenfassen macht aus „Haushalt + Drogerie“ nach dem Zuschlagen wieder eine kategorisierbare Buchung (`datenmodell.md` 3.2) und verhindert doppelte Splits auf „Unkategorisiert“.
  - Ein abgestimmter Betrag darf sich nicht verändern (`buchhaltungspflege.md` 5).
- **Bezug:** K 4, K 8 (Splits), K 14 (Kontenabstimmung), `datenmodell.md` 2, 3.2.

## E-064 Gesperrte Buchungen, Vorschläge, Regeln, Standardkategorien und Abstimmungen beim Löschen

- **Frage:** Wie verhalten sich gesperrte Buchungen, offene Vorschläge und Objekte, die auf das gelöschte Konto verweisen?
- **Entscheidung:**
  - Gesperrte Buchungen (abgeglichen oder abgestimmt) werden nur mit `gesperrte_einbeziehen = true` gelöscht oder umgebucht, sonst 409 `buchung_gesperrt` mit allen IDs. Der Status bleibt erhalten.
  - Jede umgebuchte Buchung verliert ihren Vorschlag.
  - Bei `elternkonto` werden Regeln und Standardkategorien auf das Elternkonto umgestellt. Bei den anderen Varianten werden die Regeln gelöscht und die Standardkategorie auf null gesetzt.
  - Abstimmungen des gelöschten Kontos werden gelöscht, ihre Splitmarken entfernt.
- **Begründung:**
  - Die Sperre aus M1/M3 soll nicht stillschweigend umgangen werden. Eine ausdrückliche Bestätigung reicht aber, denn sonst wäre ein Konto mit gesperrten Buchungen nie löschbar.
  - Ein Vorschlag bezöge sich nach dem Umbuchen auf eine nicht mehr gültige Lage. Bei Bestandskonten nach „Unkategorisiert“ wäre die Buchung nicht mehr kategorisierbar, und die Invariante aus `kategorisierung.md` 5 wäre verletzt.
  - „Unkategorisiert“ ist weder als Regelziel noch als Standardkategorie zulässig (Art `eigenkapital`). Eine Regel, die auf ein entferntes Konto eingeschränkt war, würde ohne die Einschränkung breiter greifen als gewollt.
  - Eine Abstimmung bescheinigt den Saldo genau eines Kontos. Mit dem Konto entfällt ihr Gegenstand.
  - Rückgängig stellt alles wieder her (`protokoll.md` 6).
- **Bezug:** K 7, K 14, `datenmodell.md` 3.1, `kategorisierung.md` 1.2, 5, `buchhaltungspflege.md` 1.3, 2, 5.

## E-065 Umfang und Aufteilung der Spezifikation für Meilenstein 4

- **Frage:** Wie wird M4 (GnuCash-Import, Lernmodell, Split-Vorlagen; `spec/meilensteine.md`) spezifiziert?
- **Entscheidung:** Drei neue Dokumente `spec/api/gnucash.md`, `lernmodell.md`, `vorlagen.md`; M4-Abschnitte in `datenmodell.md` (14), `kategorisierung.md` (7), `synchronisation.md` (15), `plugins.md` (8), `python-api.md` (10), `protokoll.md` (9), `buchhaltungspflege.md` (9), `loeschen.md` (6); `openapi.yaml` 2.2.0 mit Tags `lernmodell`, `vorlagen` und `POST /api/import/gnucash`. Tests unter `tests/app/m4/` mit Marker `m4` (wie E-041, E-058). Der Plan bleibt unverändert.
- **Begründung:** Gleiche Aufteilung wie M2/M3: ein Dokument je fachlichem Thema, Ergänzungen bestehender Dokumente als eigene, rückwärtskompatible Abschnitte (E-029).
- **Bezug:** K 7, K 8, K 12; T 5, T 6, T 8, T 9, T 17, T 21.

## E-066 GnuCash: Empfänger aus der Beschreibung, Verwendungszweck aus der Notiz

- **Frage:** GnuCash kennt keine Empfänger. Woraus werden Empfänger und Verwendungszweck gebildet?
- **Entscheidung:** Empfängername = `trn:description` nach `strip()` (leer → kein Empfänger), Verwendungszweck = Notiz-Slot `notes` der Transaktion. Empfänger werden über Namen und Aliase zugeordnet oder angelegt (`extern_id = null`). Jeder verschiedene Name zählt einmal.
- **Begründung:** In GnuCash trägt die Beschreibung üblicherweise die Gegenpartei („Supermarkt“), die Notiz den Zusatztext. So vergleicht die Dublettenerkennung Empfänger aus KMyMoney und GnuCash auf gleicher Grundlage, und Aliase aus M3 greifen auch hier.
- **Bezug:** K 12, K 14 (Empfängerverwaltung), T 5, T 6.

## E-067 GnuCash: IBAN aus der Kontonummer, versteckt = geschlossen

- **Frage:** GnuCash hat kein IBAN-Feld und kein „geschlossen“.
- **Entscheidung:** Die IBAN kommt aus `act:code`/`accounts.code`, wenn der normalisierte Wert die Form einer IBAN hat (sonst gilt das Feld als gewöhnliche Kontonummer und wird ohne Warnung ignoriert); Form ja, Prüfsumme falsch → Warnung `iban_ungueltig`. `geschlossen` = Konto versteckt (`hidden`). `eroeffnet_am` bleibt null.
- **Begründung:** Die IBAN ist für die Zuordnung zu KMyMoney- und Bankkonten nötig (T 6: keine doppelten Salden). Kontonummern wie „1200“ aus Kontenrahmen sollen keine Warnflut erzeugen. Versteckte Konten sind in GnuCash die übliche Form stillgelegter Konten.
- **Bezug:** K 12, `datenmodell.md` 2, 10.2.

## E-068 Zuordnung über Quellen hinweg (KMyMoney und GnuCash)

- **Frage:** Ein Konto kann nur eine `extern_id` tragen. Wie werden Konten zugeordnet, wenn dasselbe Buch aus KMyMoney und GnuCash importiert wird?
- **Entscheidung:** Regel 2 (IBAN bzw. Art, Name, Elternkonto) gilt beim GnuCash-Import auch für Konten mit fremder `extern_id` (nicht `gnc:`, bei Kategorien auch nicht `kontor:`); beim KMyMoney-Import entsprechend auch für Konten mit `gnc:`-Kennung. Die vorhandene `extern_id` bleibt; jedes vorhandene Konto wird je Lauf höchstens einmal zugeordnet. Buchungen tragen weiterhin mehrere Kennungen (`kmy:`, `gnc:`, `bank:`).
- **Begründung:** Ohne diese Erweiterung würde jedes Konto doppelt angelegt und T 6 („überschneidende Zeiträume ergeben keine doppelten Salden“) wäre unerfüllbar. Weil Regel 2 bei jedem Lauf erneut greift, bleiben beide Importe idempotent. Ohne GnuCash-Import ändert sich am KMyMoney-Import nichts (E-029).
- **Bezug:** K 12, T 3.7, T 6, `datenmodell.md` 10.3.

## E-069 GnuCash-SQLite: unterstützter Ausschnitt

- **Frage:** Welche Teile des GnuCash-SQL-Schemas werden gelesen?
- **Entscheidung:** Tabellen `books`, `accounts`, `transactions`, `splits` (Pflicht), `commodities`, `slots` (optional) mit den in `gnucash.md` 4.2 genannten Spalten; Reihenfolge nach `rowid`; nur der Kontobaum unter `books.root_account_guid` gehört zum Buch (Vorlagenbaum geplanter Buchungen wird ignoriert); Datumsformate `YYYY-MM-DD …` und 14 Ziffern. Die Datei wird nur lesend geöffnet. Fehlende Tabellen/Spalten → `import_format_ungueltig`, unlesbare Datei → `import_datei_beschaedigt`.
- **Begründung:** Das ist der Teil, den GnuCash seit Version 2.4 unverändert schreibt; mehr braucht die Abbildung nicht. Das Python-Modul `sqlite3` gehört zur Standardbibliothek.
- **Bezug:** K 12, T 5.

## E-070 Lernmodell: Naive Bayes mit exakter Arithmetik, Schwelle 7/10

- **Frage:** Welches Verfahren nutzt das Lernmodell, und wann gilt die Sicherheit als gering?
- **Entscheidung:** Naive-Bayes-Klassifikator über binäre Merkmale (Empfänger-Schlüssel, Wörter des Verwendungszwecks, Vorzeichen und Größenordnung des Betrags) mit Laplace-Glättung, gerechnet mit exakten Brüchen; Vorschlag nur bei Wahrscheinlichkeit ≥ 7/10 und mindestens einem bekannten Empfänger- oder Wortmerkmal; Sicherheit als ganze Promille. Vollständig festgelegt in `lernmodell.md` 2–4.
- **Begründung:** Das Verfahren ist bekannt, erklärbar, ohne Netzwerk und nur mit der Standardbibliothek umsetzbar (keine schweren Abhängigkeiten wie scikit-learn). Exakte Brüche machen Ergebnisse, Gleichstände und die Schwelle für jede Implementierung gleich; deshalb kann jeder Vorschlag gegen ein Orakel geprüft werden. Auf dem Generatordatensatz (vier Startwerte) lag die Genauigkeit der Vorschläge bei der Schwelle 7/10 zwischen 98 % und 100 % bei 81–84 % Abdeckung; eine Variante mit gewichteter Merkmalsreinheit erreichte nur 70 % Abdeckung.
- **Bezug:** K 7, T 8, T 21.

## E-071 Lernmodell ohne eigenen Zustand

- **Frage:** Wann wird trainiert, und wie fließen Korrekturen ein?
- **Entscheidung:** Das Modell ist eine Funktion des aktuellen Buchbestands (Trainingsmenge = kategorisierte Buchungen ohne offenen Vorschlag). Es gibt keinen Trainingsbefehl, keinen gespeicherten Modellzustand und keine Protokolleinträge für das Training.
- **Begründung:** „Jede Korrektur verbessert das Modell“ (K 7) gilt so sofort und nachweisbar (T 8). Rückgängig (T 3.6) stellt das Modell automatisch mit wieder her, ohne dass das Protokoll einen weiteren Objekttyp braucht. Zwischenspeichern bleibt der Implementierung erlaubt.
- **Bezug:** K 7, K 14 (Änderungsprotokoll), T 3.5, T 3.6, T 8.

## E-072 Lernmodell bei neuen Buchungen abschaltbar, Vorgabe aus

- **Frage:** Wird das Lernmodell bei der Synchronisation immer befragt?
- **Entscheidung:** Nur bei `lernmodell_automatisch = True` (`KONTOR_LERNMODELL_AUTOMATISCH`); Vorgabe `False`. `POST /api/lernmodell/anwenden` und `…/vorhersage` wirken unabhängig davon. Für den Betrieb wird das Einschalten empfohlen.
- **Begründung:** Wie E-054: M2- und M3-Tests importieren Altdaten und erwarten danach unkategorisierte Abrufe. Mit eingeschaltetem Modell würden sie Vorschläge erhalten; die Vorgabe hält ihr Verhalten unverändert (E-029).
- **Bezug:** K 7, E-029, E-054.

## E-073 Messung der Mindestgenauigkeit

- **Frage:** Wie wird „Mindestgenauigkeit 85 %“ (T 21) gemessen, wenn bei geringer Sicherheit kein Vorschlag gemacht wird?
- **Entscheidung:** Genauigkeit = richtige Vorschläge / Vorschläge ≥ 85 % gegen die *richtige* Kategorie des Generators, zusätzlich Abdeckung = Vorschläge / Prüfbuchungen ≥ 70 %. Trennung: einfache Buchungen nach Datum, ältere 80 % Training (eigene Datei `m4_lernen_training.kmy`), neueste 20 % Prüfung über `POST /api/lernmodell/vorhersage`. Der Datensatz enthält absichtlich etwa 4 % falsch erfasster Trainingsbuchungen, Empfänger mit mehreren Kategorien und neue Empfänger.
- **Begründung:** Ohne Abdeckung wäre „nie vorschlagen“ die beste Strategie. Die Prüfung gegen die richtige statt die erfasste Kategorie entspricht der bekannten Wahrheit (T 21).
- **Bezug:** T 8, T 21, T 22.

## E-074 Split-Vorlagen: Erkennung, Vorrang, Verhalten bei Abweichung

- **Frage:** Wie werden Vorlagen erkannt, in welcher Reihenfolge stehen sie zu Regeln, und was geschieht bei Abweichung?
- **Entscheidung:** Vorlagen haben Bedingungen wie Regeln, aber ohne Betrag und mit mindestens einer Empfänger-Bedingung; der Gesamtbetrag ergibt sich aus den festen Teilen. Unter den passenden aktiven Vorlagen (Priorität, ID) gewinnt die erste mit exakt passendem Betrag. Vorlagen stehen vor den Regeln. Passt keine im Betrag, wird nicht aufgeteilt; die Buchung kommt ohne Vorschlag nach „Unkategorisiert“ (auch Regeln, Standardkategorie und Lernmodell werden übergangen), und es gibt eine Benachrichtigung. Aufgeteilte Buchungen tragen keinen Vorschlag.
- **Begründung:** K 8 verlangt „keine Toleranz“ und eine Benachrichtigung. Eine Regel oder das Lernmodell würde die Abweichung sonst still mit einer einzelnen Kategorie überdecken. Mehrere Vorlagen je Empfänger (z. B. Monats- und Jahresbeitrag) unterscheiden sich über Muster im Verwendungszweck. Ein Vorschlag setzt eine einzelne Kategorie voraus (`kategorisierung.md` 5), passt also nicht zu einer Aufteilung.
- **Bezug:** K 7, K 8, T 9.

## E-075 Benachrichtigung bei Split-Abweichung und Entprellung

- **Frage:** Wann entsteht eine Benachrichtigung `split_abweichung`, und was ist ein „gleiches Ereignis“ (T 17)?
- **Entscheidung:** Je Abweichung bei der Synchronisation, Schlüssel `split_abweichung:<vorlage_id>:<betrag>`, nur wenn keine ungelesene Benachrichtigung mit diesem Schlüssel existiert. `POST /api/vorlagen/anwenden` meldet Abweichungen nur in der Antwort.
- **Begründung:** Eine Beitragsänderung zeigt sich jeden Monat mit demselben neuen Betrag; das ist ein Ereignis und soll nicht jeden Monat neu melden, solange die erste Meldung ungelesen ist. Ein anderer Betrag (z. B. 1 Cent nach oben bzw. unten) ist ein neues Ereignis. Beim Anwenden von Hand sieht der Anwender das Ergebnis unmittelbar.
- **Bezug:** K 8, T 9, T 17, `synchronisation.md` 6.

## E-076 Mock-Szenario `beitragsaenderung`

- **Frage:** Wie bildet der Mock eine Beitragsänderung ab, ohne Dateiformat und Schnittstelle zu ändern?
- **Entscheidung:** Optionaler Schlüssel `betrag_beitragsaenderung` je Umsatz der Mock-Datendatei; im Szenario `beitragsaenderung` liefert der Bank-Mock diesen Betrag, sonst wird der Schlüssel ignoriert. Format und Version bleiben `kontor-mock-daten`/1.
- **Begründung:** Dieselbe Datei liefert so beide Verläufe (ohne und mit Beitragsänderung), und die bekannte Wahrheit des Generators deckt beide ab. M1-Plugins ignorieren unbekannte Schlüssel bereits (`plugins.md` 4).
- **Bezug:** K 3 (Mock-Szenarien), K 8, T 21.

## E-077 Protokoll: Objekt `vorlage`, Quellen `lernmodell` und `vorlage`

- **Frage:** Wie werden die neuen Operationen protokolliert?
- **Entscheidung:** Neues Objekt `vorlage` (Protokollform = Schema `Vorlage`, Reihenfolge nach `abstimmung`), neue Quellen `lernmodell` (`lernmodell_anwenden`) und `vorlage` (`vorlagen_anwenden`), Aktion `import_gnucash` unter Quelle `import`, manuelle Aktionen `vorlage_anlegen`, `vorlage_aendern`, `vorlage_loeschen`. Automatisches Aufteilen und Lernmodell-Vorschläge beim Abruf gehören zur Änderung `sync_konto`.
- **Begründung:** Erfüllt die Pflicht aus CLAUDE.md und T 3.5 für jede neue Operation mit Wirkung auf den Buchbestand. Eigene Quellen machen automatische Kategorisierung im Protokoll filterbar, wie `regeln` in M3.
- **Bezug:** K 14, T 3.5, T 3.6, `protokoll.md` 4.

## E-078 Spezifikationstest für M3 auf erweiterbare Aufzählungen umgestellt

- **Frage:** `tests/spec/test_openapi.py::test_m3_schemas_rueckwaertskompatibel` verlangte exakt die Version 2.1.0 und exakt die Quellen `regel`, `standardkategorie` des Vorschlags. M4 erhöht die Version und ergänzt `lernmodell`.
- **Entscheidung:** Der M3-Spezifikationstest prüft nun „mindestens 2.1.0“ und „enthält mindestens“; die exakte Prüfung für 2.2.0 steht im neuen `test_m4_schemas_rueckwaertskompatibel`. App-Tests von M1–M3 bleiben unverändert.
- **Begründung:** Die exakte Gleichheit war für einen Dokumenttest zu streng formuliert: Rückwärtskompatible Erweiterungen (E-029) sind ausdrücklich vorgesehen. Die Aussage des Tests (M3-Werte vorhanden, Pflichtfelder unverändert) bleibt erhalten.
- **Bezug:** E-029, T 1 (Änderungen an Tests nur bei Spezifikationsänderung, dokumentiert).

## E-079 Konto löschen und Split-Vorlagen

- **Frage:** Was geschieht mit Vorlagen, die auf ein gelöschtes Konto verweisen?
- **Entscheidung:** `DELETE /api/konten/{id}` → 409 `konto_in_verwendung`. `POST /api/konten/{id}/loeschen`: bei `elternkonto` Verweise auf das Elternkonto umstellen (gleiche Kategorie in mehreren Teilen bleibt erlaubt), sonst die Vorlage löschen; Ergebnisfelder `vorlagen_geaendert`, `vorlagen_geloescht` (im Schema optional).
- **Begründung:** Gleiche Behandlung wie Regeln (E-064): Eine Vorlage ohne eine ihrer Kategorien würde einen anderen Gesamtbetrag ergeben und damit still falsch aufteilen oder ständig abweichen.
- **Bezug:** K 4, K 8, `loeschen.md` 3.4.

## E-080 Gelöschtes Bankkonto bei der Synchronisation

- **Frage:** Was geschieht, wenn das einem Bankkonto zugeordnete Konto gelöscht wurde und danach synchronisiert wird? Bisher legte der Lauf nach `synchronisation.md` 3 Regel 2 still ein neues Konto an; weil die Kennungen gemerkt blieben (E-034) und der Zeitraum bei `letzter_abruf_bis` ansetzte, blieb es leer und hatte einen falschen Saldo. Beobachtung und Auftrag des Anwenders vom 2026-11-08: „Der User sollte gefragt werden, ob Konten neu erstellt werden sollen. Außerdem sollten dann nicht vorhandene Buchungen wieder hinzugefügt werden.“
- **Entscheidung:** Ein Bankkonto mit Sync-Eintrag, für das kein Konto mit seiner IBAN mehr existiert, wird nicht mehr automatisch angelegt. Es hat den Status `konto_fehlt`, wird in jedem Lauf übersprungen (`SyncLauf.uebersprungen`) und erzeugt eine entprellte Benachrichtigung `konto_fehlt`. Der Anwender entscheidet über `POST /api/sync/konten/{iban}/entscheidung`: `wiederherstellen` (beim nächsten Lauf anlegen) oder `ignorieren` (dauerhaft überspringen, ohne Benachrichtigung). Neue IBANs werden weiterhin ohne Rückfrage angelegt. Fachliche Regeln: `synchronisation.md` 16.
- **Begründung:** Wer ein Konto löscht, will es in der Regel nicht still zurückbekommen; ein leeres Konto mit falschem Saldo ist schlechter als keines. Der Planer läuft unbeaufsichtigt (K 6), deshalb ist „fragen“ eine offene Entscheidung mit Benachrichtigung statt eines Dialogs im Lauf. `ignorieren` ist nötig, weil Banken auch Konten liefern, die man bewusst nicht im Buch haben will; sonst käme die Frage bei jedem Lauf wieder. Für neue IBANs bleibt das bisherige Verhalten, damit der erste Abruf ohne Zusatzschritt funktioniert (T 6, M2-Tests unverändert).
- **Bezug:** K 5, K 6, T 6, `synchronisation.md` 3, 16; E-034.

## E-081 Wiederherstellen mit allen oder nur neuen Umsätzen

- **Frage:** Wie kommen die Buchungen eines wiederhergestellten Kontos zurück, ohne die Regel „gemerkte Kennungen werden nie erneut gebucht“ (E-034) allgemein aufzugeben?
- **Entscheidung:** Die Entscheidung `wiederherstellen` verlangt `buchungen = "alle"` oder `"nur_neue"`. Bei `"alle"` vergisst die Zuordnung im nächsten Lauf alle Kennungen dieser IBAN, die an keiner existierenden Buchung hängen, und setzt `letzter_abruf_bis` auf null; der Abruf beginnt dann bei `heute − sync_erstabruf_tage` (bzw. bei `von` der Anfrage). Bei `"nur_neue"` bleibt beides, wie bisher. Auch früher einzeln gelöschte Buchungen dieses Bankkontos kommen bei `"alle"` zurück.
- **Begründung:** E-034 schützt bewusst gelöschte Buchungen bei laufendem Konto; beim Wiederherstellen ist die ausdrückliche Wahl „alle“ genau die gegenteilige Absicht und betrifft nur dieses Bankkonto. Einzelne früher gelöschte Buchungen davon auszunehmen, würde eine zweite Merkliste verlangen; der Anwender kann sie nach dem Lauf wieder löschen. Ohne Zurücksetzen von `letzter_abruf_bis` lieferte der Abruf nur die letzten Tage (4.1), und nach einem Fehlschlag des ersten Abrufs ginge die Absicht verloren. Ältere Umsätze, als die Bank liefert, lassen sich nur über einen erneuten KMyMoney- oder GnuCash-Import zurückholen; das steht im Text der Oberfläche.
- **Bezug:** K 6, T 6, `synchronisation.md` 4.1, 4.3, 16.2; E-034, E-057.

## E-082 Noch existierende Buchungen eines gelöschten Kontos

- **Frage:** Wurde das Konto mit `elternkonto` oder `unkategorisiert` gelöscht (`loeschen.md` 3.2), existieren seine Buchungen mit ihren Bank-Kennungen weiter, aber auf einem anderen Konto. Werden sie beim Wiederherstellen mit `"alle"` erneut gebucht oder zurückverschoben?
- **Entscheidung:** Weder noch. Ihre Kennungen bleiben gemerkt; die Umsätze zählen als `buchungen_vorhanden`. Die Buchungen bleiben, wo sie sind.
- **Begründung:** Eine zweite Buchung desselben Umsatzes würde ihn doppelt zählen (T 6), und der Abgleich (4.4) findet sie nicht, weil Buchungen mit Kennungen desselben Bankkontos keine Kandidaten sind. Zurückverschieben hieße, eine frühere ausdrückliche Entscheidung des Anwenders still umzukehren; wer das will, macht das Löschen über das Protokoll rückgängig (vor dem Wiederherstellen) oder bucht die Buchungen per Mehrfachbearbeitung um.
- **Bezug:** T 6, `loeschen.md` 3.2, `synchronisation.md` 16.2.

## E-083 Form der Entscheidung, Status und Protokoll

- **Frage:** Wie wird die Entscheidung gespeichert, wann gilt ein Bankkonto als „fehlend“, und wird die Entscheidung protokolliert?
- **Entscheidung:** (1) `SyncKontoZustand.status` wird abgeleitet: `aktiv`, sobald irgendein Konto die IBAN trägt; sonst aus der gespeicherten Entscheidung (`konto_fehlt`, `ignoriert`, `wiederherstellen`). Damit „fehlt“ ein Bankkonto auch nach `DELETE /api/konten/{id}` oder nach Entfernen der IBAN, und ein manuell oder per Import wieder angelegtes Konto mit der IBAN wird ohne Entscheidung übernommen. (2) Beide Felder `aktion` und `buchungen` sind Pflicht, ohne Vorgabe, wie bei E-061. (3) Bei Status `aktiv` → 409 `konto_vorhanden`. (4) Die Entscheidung ist Betriebszustand wie `/api/sync/konten` und wird nicht protokolliert; die Wirkung auf den Buchbestand (Konto anlegen, Kennungen vergessen) gehört zur Änderung `sync_kontozuordnung` des nächsten Laufs. (5) Der Eintrag in `/api/sync/konten` bleibt beim Löschen des Kontos erhalten.
- **Begründung:** Ein abgeleiteter Status kann nicht mit dem Kontenbestand auseinanderlaufen, auch nicht durch Rückgängig. Eine Änderung im Protokoll braucht mindestens einen Eintrag (`protokoll.md` 3.1); die Entscheidung allein ändert kein protokolliertes Objekt. Gemeinsam mit dem Anlegen des Kontos bleibt das Vergessen der Kennungen rückgängig machbar.
- **Bezug:** K 14, T 3.5, T 3.6, `protokoll.md` 4.2, 6.1, 6.4, `synchronisation.md` 16.

## E-084 Einordnung als M3-Nachtrag, Rückgängig und Version

- **Frage:** Zu welchem Meilenstein gehört die Änderung, und wie verhält sich Rückgängig?
- **Entscheidung:** Nachtrag zu M3 (gehört zum Löschen von Konten, `loeschen.md`), Tests in `tests/app/m3/test_m3_sync_konto_fehlt.py`. `protokoll.md` 6.1 Schritt 4: Kennungen, die eine Änderung vergessen hat, werden beim Rückgängig wieder gemerkt. `protokoll.md` 6.4: Rückgängig einer wiederherstellenden Zuordnung entfernt das Konto, der Eintrag bleibt mit Status `konto_fehlt`; Einträge entfallen nie nur deshalb, weil ihr Konto nicht mehr existiert. `openapi.yaml` 2.3.0 (neue Felder optional, neuer Endpunkt, Benachrichtigungsart `konto_fehlt`). Der M4-Spezifikationstest prüft die Version nun als „mindestens 2.2.0“, die exakte Prüfung steht im neuen `test_m3_nachtrag_geloeschte_bankkonten` (wie E-078).
- **Begründung:** Die Lücke entsteht erst durch das Löschen benutzter Konten (M3) zusammen mit der Synchronisation (M2); M3 ist spezifiziert, aber noch nicht abgenommen. Nach Rückgängig soll der Zustand „exakt wie vorher“ sein (T 3.6): vor dem Lauf fehlte das Konto, also ist die Frage wieder offen. Rückwärtskompatibel nach E-029: M1/M2-Tests und deren Schemas bleiben unverändert; Läufe ohne gelöschte Bankkonten verhalten sich wie bisher.
- **Bezug:** E-029, E-057, E-058, E-078, T 1, T 3.6.

## E-085 Datensicherung als eigener Meilenstein M9

- **Frage:** Wo wird das neue Feature „Backup and Recovery“ (Auftrag des Anwenders vom 2026-11-08) eingeordnet? M7 enthielt bereits „Datenbank-Export und Wiederherstellung mit identischem Bestand“ (T 20), aber ohne Einspielen über die App und ohne Protokoll.
- **Entscheidung:** Neuer Meilenstein M9 „Datensicherung und Wiederherstellung“ (`spec/api/sicherung.md`), abhängig von M4, umzusetzen **nach M4 und vor M5**. Die Nummer folgt der Reihenfolge der Aufnahme, nicht der Umsetzung; M5–M8 behalten ihre Nummern, damit bestehende Verweise gültig bleiben. Der Punkt „Datenbank-Export und Wiederherstellung“ entfällt aus M7; T 20 wird durch M9 geprüft. Spätere Meilensteine nehmen neuen fachlichen Zustand in die Sicherung auf (`sicherung.md` 2.3).
- **Begründung:** M9 braucht das Änderungsprotokoll (M3, „als neue Version“) und alle bis dahin spezifizierten Objektarten einschließlich Vorlagen (M4), sonst wäre die Sicherung nicht vollständig. Es braucht weder Kredite noch Login; früh umgesetzt schützt es die Daten des Anwenders schon während der weiteren Entwicklung.
- **Bezug:** K 2 („zusätzlich Datenbank-Export“), K 17 (Datensicherung in der App), T 20, T 23.

## E-086 Format: ZIP mit SQLite-Datenbank und Manifest

- **Frage:** Welches „übliche Datenformat“? Bestätigte Vorgabe des Anwenders: ZIP-Datei, Inhalt eine SQLite-Datenbank ohne Änderungsprotokoll.
- **Entscheidung:** ZIP mit genau `manifest.json` und `kontor.sqlite` (`sicherung.md` 3). Das Schema der SQLite-Datei ist Sache der Implementierung (`python-api.md` 7) und wird über `schemaversion` versioniert; ältere Schemaversionen werden beim Einspielen migriert. Die Datei enthält nur Tabellen und Indizes, ist eigenständig (kein WAL) und enthält keine Reste gelöschter oder ausgeschlossener Daten.
- **Begründung:** ZIP und SQLite sind verbreitet und mit Standardwerkzeugen lesbar. Das Manifest erlaubt Prüfungen ohne Kenntnis des Schemas (Modus, Versionen, Prüfsummen). Ohne die Forderung nach „keinen Resten“ stünde ein entfernter Protokolleintrag oder eine gelöschte Buchung oft noch in freien Seiten der Datei. CSV scheidet aus, weil Splits, Hierarchien und Bezüge nicht verlustfrei abbildbar wären; KMyMoney/GnuCash-Formate scheiden aus, weil ihr Import zusammenführt statt zu ersetzen.
- **Bezug:** K 2, K 14 (Export), `sicherung.md` 3.

## E-087 Umfang der Sicherung

- **Frage:** „Alle Konten“ oder „gesamter interner Zustand“? Bestätigt: Der Export ist vollständig.
- **Entscheidung:** Enthalten sind der Buchbestand (alle Objektarten aus `protokoll.md` 2 und 9.1 mit IDs), die gemerkten Umsatzkennungen, der Zustand je Bankkonto (inkl. gespeicherter Entscheidung) und die ID-Zähler. Nicht enthalten: Änderungsprotokoll, Geheimnisse, Importvorgänge, Läufe, TAN-Anforderungen, Benachrichtigungen, simulierte Uhr.
- **Begründung:** Kennungen und `letzter_abruf_bis` gehören fachlich zum Buch: Ohne sie würde nach dem Einspielen einer älteren Sicherung der nächste Abruf entweder Umsätze doppelt buchen oder die Lücke seit der Sicherung nie schließen (`sicherung.md` 7). Die ID-Zähler sichern „IDs werden nie wiederverwendet“ über das Einspielen hinweg. Läufe, TANs und Benachrichtigungen sind Betriebszustand der Instanz und sagen über den Bestand der Sicherung nichts aus.
- **Bezug:** K 6, T 6, `datenmodell.md` 1, `synchronisation.md` 4.3, 16.

## E-088 Einspielen ersetzt und ist eine Änderung im Protokoll

- **Frage:** Wie wird „überschrieben und als neue Version angelegt“ umgesetzt? Bestätigt: Das Änderungsprotokoll ist nicht Bestandteil von Export oder Import; ein Import ist eine Änderung.
- **Entscheidung:** Das Einspielen ersetzt den Zustand aus E-087 vollständig und erzeugt eine Änderung `quelle = "sicherung"`, `aktion = "sicherung_einspielen"` mit der Nettowirkung über den ganzen Buchbestand. Die „Version“ ist diese Änderung; das Protokoll der Instanz bleibt erhalten. Rückgängig und Wiederholen funktionieren wie bei jeder Änderung und setzen zusätzlich Kennungen und Bankkonto-Zustand zurück (`protokoll.md` 10.2).
- **Begründung:** Das Protokoll speichert für jede Änderung den Zustand vorher und nachher; damit ist der Stand vor dem Einspielen ohne zweite Sicherungskopie wiederherstellbar, und es gelten dieselben Konfliktregeln wie sonst. Eine eigene Versionsverwaltung neben dem Protokoll wäre doppelt.
- **Bezug:** K 14 (Änderungsprotokoll), T 3.5, T 3.6, `protokoll.md` 6, 10.

## E-089 Identischer Inhalt erzeugt keine neue Version

- **Frage:** Widerspruch zu T 3.7 (Idempotenz) und zu „neue Version“ beim wiederholten Einspielen. Bestätigt: keine neue Version, wenn der Inhalt identisch ist.
- **Entscheidung:** „Identisch“ heißt: Die Protokollformen aller Objekte stimmen überein (gleichbedeutend mit gleicher `inhalt_sha256`). Dann ändert sich gar nichts, auch nicht an Kennungen, Bankkonto-Zustand und ID-Zählern, und es entsteht keine Änderung (`geaendert = false`). Zweimaliges Einspielen derselben Sicherung ändert beim zweiten Mal nichts (T 3.7).
- **Begründung:** Gleiche Grundregel wie `protokoll.md` 4 („Operationen ohne Wirkung erzeugen keine Änderung“). Ein Vergleich der Datei-Bytes wäre falsch: Zwei SQLite-Dateien mit gleichem Inhalt unterscheiden sich fast immer im Binärformat, und das Manifest enthält den Erstellungszeitpunkt. Teilweises Übernehmen (z. B. nur Kennungen) bei identischem Buchbestand wäre nicht rückgängig zu machen, weil keine Änderung entsteht.
- **Bezug:** T 3.7, `protokoll.md` 4, `sicherung.md` 5.2, 5.3.

## E-090 Geheimnisse werden nie exportiert

- **Frage:** Gehören verschlüsselte Tokens oder Zugangsdaten zur Sicherung? Bestätigt: niemals Geheimnisse exportieren.
- **Entscheidung:** Keine Geheimnisse in der Sicherung, auch nicht verschlüsselt; beim Einspielen bleiben vorhandene Geheimnisse der Instanz unverändert. Geprüft wird, dass eine gesetzte PIN in keinem Byte der ZIP-Datei vorkommt (in M6 entsprechend für Tokens).
- **Begründung:** Verschlüsselte Geheimnisse wären auf einem anderen Rechner ohnehin nicht entschlüsselbar (Schlüssel an Rechner bzw. TPM gebunden, K 6), und eine Sicherungsdatei wandert eher weiter als die Datenbank. Nach dem Einspielen auf neuer Hardware werden PIN und Tokens neu eingegeben.
- **Bezug:** K 3 (Geheimnisse), K 6 (PIN), `synchronisation.md` 12, `sicherung.md` 2.2.

## E-091 Prüfsummen und Rundreise ohne Versionsdaten

- **Frage:** T 20 verlangt „identischer Datenbestand“ nach Export und Wiederherstellung, durch das Einspielen ändern sich aber Protokoll und Versionsdaten. Bestätigt: Verglichen wird nur der fachliche Inhalt.
- **Entscheidung:** Die Rundreise gilt als erfüllt, wenn alle Lese-Endpunkte des Buchbestands (Protokollformen, Kontenübersicht, Buchungsliste) sowie `/api/sync/konten` nach dem Einspielen dem Zustand beim Erstellen entsprechen; Protokoll, Läufe und Benachrichtigungen sind ausgenommen. Das Manifest trägt zwei Prüfsummen: `inhalt_sha256` über die kanonische JSON-Form der Protokollformen (unabhängig nachrechenbar, `sicherung.md` 3.3) und `datenbank_sha256` über die Dateibytes.
- **Begründung:** Die Inhaltsprüfsumme macht „identisch“ (E-089) und die Rundreise ohne Kenntnis des Schemas prüfbar und erkennt beim Einspielen, ob die Implementierung die Datei vollständig und richtig gelesen hat. Die Dateiprüfsumme schützt auch die nicht über REST sichtbaren Teile (Kennungen, Zähler) gegen Beschädigung.
- **Bezug:** T 20, T 23, `sicherung.md` 3.3, 5.

## E-092 Modus, Bestätigung, Probelauf und Sperre

- **Frage:** Wie verhalten sich Mock- und Echtdaten, abgestimmte Buchungen und eine laufende Synchronisation beim Einspielen? Bestätigt: Modus prüfen, ausdrückliche Bestätigung, Sperre gegen gleichzeitige Synchronisation.
- **Entscheidung:** (1) `manifest.modus` muss zum Modus der App passen, sonst 409 `sicherung_modus`. (2) Ohne `bestaetigt=true` → 409 `bestaetigung_erforderlich`; `trocken=true` liefert den Unterschied je Objektart und die Zahl betroffener abgestimmter oder abgeglichener Buchungen, ohne etwas zu ändern. (3) Ein Lauf mit Status `laeuft` → 409 `sync_laeuft`, `wartet_auf_tan` → 409 `tan_ausstehend`; während des Einspielens startet kein Lauf. Status- und Sperrregeln für abgestimmte Buchungen gelten für das Einspielen nicht (wie beim Rückgängig).
- **Begründung:** K 3 verlangt getrennte Datenbanken für Mock- und Echtdaten. Das Einspielen überschreibt auch geschützte Buchungen (T 13); das ist gewollt, aber nur nach einer bewussten Bestätigung, die die Oberfläche mit dem Probelauf begründen kann. Ein pausierter Lauf würde nach der TAN Umsätze in einen Bestand schreiben, zu dem seine Zuordnung nicht mehr passt.
- **Bezug:** K 3, K 6, T 13, `sicherung.md` 5.1, 5.4.

## E-093 Prüfung eingespielter Dateien, IDs und Version

- **Frage:** Wie wird verhindert, dass eine untergeschobene oder beschädigte SQLite-Datei Schaden anrichtet, und was gilt für IDs und die Vertragsversion?
- **Entscheidung:** Die Datei wird vor jeder Übernahme vollständig geprüft, in der festen Reihenfolge aus `sicherung.md` 5.1 mit einem `details.grund` je Fall; das Schema muss genau zur `schemaversion` passen, Views und Trigger sind verboten, gelesen werden nur bekannte Tabellen und Spalten. Bei jedem Fehler ändert sich nichts. Eingespielte Objekte behalten ihre IDs; danach vergebene IDs sind größer als jede hier oder in der Quelle je vergebene. `openapi.yaml` 2.4.0 (neuer Tag `sicherung`, neue Quelle `sicherung`, neue Fehlercodes `sicherung_ungueltig`, `sicherung_modus`, `bestaetigung_erforderlich`). Der Spezifikationstest des M3-Nachtrags prüft die Version nun als „mindestens 2.3.0“, die exakte Prüfung steht in `test_m9_sicherung` (wie E-078, E-084).
- **Begründung:** Eine Sicherung ist eine Datei aus unsicherer Quelle; eine SQLite-Datei kann Trigger oder Views mitbringen, die beim bloßen Öffnen als App-Datenbank wirken würden. Feste Gründe machen die Fehlerfälle ohne Kenntnis des Schemas testbar (Tests verändern die Datei mit `sqlite3` und rechnen `datenbank_sha256` nach). Gleiche IDs sind Voraussetzung für die Inhaltsprüfsumme und für Rückgängig; die Zählerregel hält `datenmodell.md` 1 für alle neu angelegten Objekte ein.
- **Bezug:** E-029, E-078, E-084, `datenmodell.md` 1, `sicherung.md` 5.1, 5.3.

## E-094 Löschergebnis ohne Vorlagenfelder (ersetzt den letzten Teil von E-079)

- **Frage:** E-079 sah zusätzliche Felder `vorlagen_geaendert` und `vorlagen_geloescht` in `KontoLoeschErgebnis` vor, ab M4 in jeder Antwort. Der M3-Test `test_loeschen_gegen_orakel` vergleicht die ganze Antwort mit einem Orakel; zusätzliche Felder würden ihn rot machen.
- **Entscheidung:** `KontoLoeschErgebnis` bleibt unverändert. Welche Vorlagen umgestellt oder gelöscht werden, zeigen `GET /api/vorlagen` und die Änderung `konto_loeschen_mit_buchungen` im Protokoll. Das Verhalten (umstellen bzw. löschen, rückgängig machbar) bleibt wie in E-079.
- **Begründung:** E-029 verlangt, dass Tests früherer Meilensteine unverändert grün bleiben. Ein M3-Test darf nicht wegen eines M4-Felds angepasst werden; die Information ist auf anderem Weg vollständig verfügbar. Gefunden beim Lauf der Selbstprüfung gegen die erweiterte Referenz.
- **Bezug:** E-029, E-079, `loeschen.md` 6, `vorlagen.md` 1.

## E-095 W-002: M1-Tests verwenden für „unbekanntes Szenario“ einen nie vergebenen Namen (Ausnahme zu E-029)

- **Frage:** Gemeldeter Widerspruch W-002: Die M1-Tests `test_paket.py::test_ungueltige_konfiguration` (Fall `mock_modus=True, mock_szenario=beitragsaenderung`) und `test_plugins.py::test_unbekanntes_szenario` (MockBank, MockMail) verlangen, dass `beitragsaenderung` ungültig ist. Seit M4 ist es ein gültiges Szenario (E-076, `plugins.md` 8, `python-api.md` 10.1/10.3), und `test_m4_paket.py` verlangt das. Beides zugleich ist nicht erfüllbar.
- **Entscheidung:** Die Spezifikation gilt; die drei M1-Fälle verwenden statt `beitragsaenderung` den Namen `gibtsnicht_m1`, der in keinem Meilenstein ein Szenario wird. Was die Fälle prüfen (unbekannter Name → `KonfigurationsFehler`, Code `konfiguration_ungueltig`), bleibt gleich. Künftige Szenarien dürfen nie `gibtsnicht…` heißen. Ergänzend prüft `test_m4_paket.py`, dass auch der Mail-Mock `beitragsaenderung` annimmt (Verhalten wie `normal`, `plugins.md` 8) und `gibtsnicht_m1` weiterhin abgelehnt wird.
- **Begründung:** Abweichung von E-029 („M1-Tests werden nicht geändert“): E-029 setzt voraus, dass die Tests früherer Meilensteine nur Verhalten verlangen, das spätere Meilensteine nicht erweitern. Hier hat ein M1-Test einen in E-016 bereits als „später“ angekündigten Szenarionamen als Beispiel für „unbekannt“ benutzt, also eine Eigenschaft geprüft, die nie zum Vertrag von M1 gehörte. Die Änderung schwächt keine M1-Anforderung: Eine M1-Implementierung, die die alten Fälle erfüllte, erfüllt auch die neuen. Andere M1-Tests bleiben unverändert (z. B. `test_bekannte_szenarien` und `test_mock_modus.py`, die nur die M1-Szenarien aufzählen). Die Selbstprüfung hat den Widerspruch nicht gefunden, weil die betroffenen Tests keine `kern`-Tests sind.
- **Bezug:** E-016, E-029, E-076, K 3, T 1, `plugins.md` 3 und 8, `python-api.md` 10.1, 10.3.

## E-096 Abgleich der Sicherung mit M4 und dem M3-Nachtrag (ergänzt E-087)

- **Frage:** M9 wurde parallel zu M4 und zum Nachtrag `synchronisation.md` 16 spezifiziert. Erfasst `sicherung.md` 2 alle fachlichen Zustände bis einschließlich M4 eindeutig, insbesondere Kennungen gelöschter Buchungen, gespeicherte Entscheidungen je Bankkonto bei gelöschten Konten, Vorschläge des Lernmodells mit Sicherheit und die Konfiguration?
- **Entscheidung:** Ergänzt in `sicherung.md` 2.1, 2.2, neu 2.4 und 5.1: (1) Gesichert werden **alle** gemerkten Kennungen, auch die gelöschter Buchungen und Konten. (2) Die gespeicherte Entscheidung je Bankkonto (`aktion`, `buchungen`) gehört dazu, auch wenn `konto_id` auf ein gelöschtes Konto zeigt und auch solange ein Konto mit der IBAN sie verdeckt; `status` wird nach dem Einspielen abgeleitet. (3) Solche Einträge und Kennungen ohne Buchung sind kein `inhalt_ungueltig`. (4) Vorschläge aller Quellen samt `sicherheit` sind Teil der Buchung; das Lernmodell ergibt sich aus dem eingespielten Bestand (`GET /api/lernmodell` bis auf `automatisch` und Vorhersagen wie in der Quelle). (5) Die Konfiguration der Instanz (`lernmodell_automatisch`, `mock_szenario`, Planer) ist nie Teil der Sicherung. (6) Tabelle 2.4 ordnet jeden Zustand aus M1–M4 zu. Neue Kern-Tests in `tests/app/m9/test_m9_vollstaendigkeit.py`; `test_vorlagen_in_der_rundreise` ist jetzt `kern`, weil die Referenz M4 abdeckt.
- **Begründung:** Ohne die Kennungen gelöschter Buchungen käme nach dem Einspielen jede gelöschte Bankbuchung beim nächsten Abruf wieder (verletzt E-034, T 6). Ohne die Entscheidung legte der nächste Lauf ein gelöschtes Konto still neu an oder vergäße eine bereits gewählte Wiederherstellung – genau der Fehler, den der Nachtrag behebt. Eine Prüfung „`konto_id` muss existieren“ würde jede Sicherung mit gelöschtem Bankkonto ablehnen. Die Konfiguration gehört zur Instanz (Mock-/Echtbetrieb, K 3) und wird über `KontorConfig` gesetzt, nicht über das Buch. Gefunden beim Abgleich: Die Wegwerf-Referenz verlor beim Einspielen den Typ der gespeicherten Entscheidung und führte eine vermerkte Wiederherstellung `"alle"` nicht mehr aus; der neue Test erkennt das.
- **Bezug:** E-034, E-080 bis E-084, E-087, E-090, K 3, K 7, T 6, T 20, `sicherung.md` 2, 5.1, `synchronisation.md` 4.3, 16, `lernmodell.md` 1.

## E-097 Umfang und Aufteilung der Spezifikation für Meilenstein 5

- **Frage:** Wie wird M5 (wiederkehrende Buchungen, Kredite, Berichte, Export) geschnitten, damit ein Agent ohne Rückfragen implementieren kann, ohne frühere Tests zu brechen?
- **Entscheidung:** Drei neue Dokumente `spec/api/kredite.md`, `spec/api/wiederkehrend.md`, `spec/api/berichte.md` (Berichte und Export); M5-Abschnitte in `datenmodell.md` (15), `synchronisation.md` (17), `protokoll.md` (11), `sicherung.md` (2.5), `python-api.md` (12), `loeschen.md` (7); `openapi.yaml` 2.5.0 mit den Tags `kredite`, `wiederkehrend`, `berichte`, `export`. Tests unter `tests/app/m5/` mit Marker `m5`. Der Umfang folgt `spec/meilensteine.md` M5 ohne Abweichung. Neue Felder bestehender Schemas sind optional (`SyncKonto.buchungen_kredit`); neue Werte werden an Aufzählungen angehängt (`Aenderungsquelle`, `Objektart`, `Benachrichtigung.art`).
- **Begründung:** Gleiche Aufteilung wie M3/M4 (ein Dokument je Fachgebiet). Ohne Kredite und mit der Vorgabe `wiederkehrend_automatisch = False` bleibt jedes frühere Verhalten gleich (E-029); Berichte und Export lesen nur.
- **Bezug:** K 9, K 10, K 11, K 14, T 10, T 12, T 14, T 15, T 17, T 22, E-029, E-041.

## E-098 Wiederkehrende Buchungen ohne eigenen Zustand

- **Frage:** Wie werden Abos, Daueraufträge und Lastschriften erkannt, und braucht die Erkennung gespeicherten Zustand?
- **Entscheidung:** Die Erkennung ist eine Funktion des Buchbestands (`wiederkehrend.md` 2): Gruppen je (Bestandskonto, Empfänger, Richtung), eine rückwärts gebildete Kette ab der jüngsten Zahlung mit `|d_j − monat_plus(d_{j−1}, m)| ≤ 5` Tagen, Rhythmen monatlich (mindestens 3), vierteljährlich (3) und jährlich (2) in dieser Reihenfolge. Beträge dürfen sich ändern; `betrag` ist der jüngste. Darlehenskonten von Krediten bilden keine Gruppen. Nichts davon wird protokolliert oder gesichert.
- **Begründung:** Wie beim Lernmodell (E-071) kann eine abgeleitete Erkennung nicht mit den Buchungen auseinanderlaufen, auch nicht durch Rückgängig oder Einspielen einer Sicherung. Die Toleranz von 5 Tagen deckt Wochenende plus bundesweite Feiertage (längste Verschiebung 4 Tage, Ostern) ab, ohne zwei Zahlungen im selben Monat zu verbinden. `monat_plus` vom tatsächlichen Datum vermeidet Drift bei Monatsenden (31. → 28./29.). Mit der Mindestanzahl entsteht aus zwei zufälligen Einkäufen keine Monatsserie; jährliche Zahlungen sind nach zwei Jahren erkennbar.
- **Bezug:** K 9, T 10, E-071.

## E-099 Status, Jahreskosten und nächste Fälligkeit

- **Frage:** Wann gilt eine Zahlung als ausgeblieben, und wie werden Jahreskosten berechnet?
- **Entscheidung:** `naechste_faelligkeit = monat_plus(letzte, m)`; Status am Stichtag `aktiv` bis `F + 5`, `ausbleibend` bis `monat_plus(letzte, 2m) + 5`, danach `beendet`. `jahreskosten = −betrag · 12/m` (Ausgaben positiv), `summe_jahreskosten` über nicht beendete Ausgabenserien. Die Übersicht hat einen Stichtag (Vorgabe heute), damit sie deterministisch prüfbar ist.
- **Begründung:** Genau eine fehlende Zahlung ist das Ereignis „ausbleibende Zahlung“; danach (gekündigtes Abo, Altdaten aus dem Import) soll keine Meldung mehr kommen. Ganzzahlig, weil 12/m ∈ {12, 4, 1}.
- **Bezug:** K 9, T 10.

## E-100 Benachrichtigungen bei unerwarteten Buchungen

- **Frage:** Was ist eine „unerwartete Buchung“ (neuer Empfänger, geänderter Betrag, ausbleibende Zahlung), wann wird geprüft, und wie wird eine Nachrichtenflut verhindert?
- **Entscheidung:** Drei Ereignisse (`wiederkehrend.md` 3): `neuer_empfaenger` (Ausgabe, erste Buchung des Empfängers überhaupt), `wiederkehrend_betrag` (Zahlung setzt eine erkannte Serie fort, Betrag weicht ab), `wiederkehrend_ausbleibend` (Serie im Status `ausbleibend`). Jeder Schlüssel bezeichnet genau ein Ereignis; eine Benachrichtigung entsteht nur, wenn es noch **keine** mit diesem Schlüssel gibt (gelesen oder nicht) – abweichend von der M2-Entprellung „keine ungelesene“. Geprüft wird auf Wunsch (`POST /api/wiederkehrend/pruefen` mit Buchungs-IDs) oder bei `wiederkehrend_automatisch = True` nach jedem Lauf mit den neuen Buchungen von Konten, die schon vorher erfolgreich abgerufen wurden. Vorgabe `False`.
- **Begründung:** T 17 verlangt genau eine Nachricht je Auslöser. Bei Synchronisationsfehlern ist „derselbe Fehler noch ungelesen“ das richtige Maß; ein Ereignis wie „Miete März fehlt“ soll dagegen nach dem Lesen nicht wiederkommen. Ohne den Ausschluss des Erstabrufs wäre jeder Empfänger beim ersten Abruf „neu“. Abschaltbar mit Vorgabe aus wie E-054 und E-072, damit Tests früherer Meilensteine keine zusätzlichen Benachrichtigungen sehen.
- **Bezug:** K 9, T 10, T 17, E-054, E-072, E-075.

## E-101 Kredit als protokolliertes Objekt mit Darlehenskonto

- **Frage:** Wie wird ein Annuitätendarlehen „ohne direkten Kontozugriff“ abgebildet, und wo steht die Restschuld?
- **Entscheidung:** Neues Objekt `kredit` (`kredite.md` 2) mit Darlehenskonto (Art `kreditkonto`), Zahlungskonto, Zinskonto (`aufwand`), Parametern (Restschuld am Stichtag, Sollzins in Millionstel, Methode, Rate, erste Fälligkeit, Sondertilgungen, Erkennungsbedingungen) und den nur lesbaren Listen `zuordnungen` und `abgleiche`. Die gebuchte Restschuld ist der negative Saldo des Darlehenskontos. Beim Anlegen gleicht eine Anfangsbuchung (Gegenkonto „Korrekturen“) den Saldo an die Restschuld an (`saldo_angleichen`, Vorgabe true). Protokolliert (`kredit_anlegen`, `kredit_aendern`, `kredit_loeschen`) und Teil der Sicherung.
- **Begründung:** Die doppelte Buchführung bleibt die einzige Quelle der Salden (T 3.3); der Kredit speichert nur, was sich nicht aus Buchungen ergibt. Ganzzahlige Millionstel stellen jeden üblichen Sollzins (vier Nachkommastellen in Prozent) exakt dar (T 3.2). Die Zuordnungen machen eindeutig, welche Buchung welche Rate ist, auch nach Bearbeitung der Splits; sie ändern sich nur zusammen mit der Buchung in derselben Änderung und lassen sich daher exakt rückgängig machen.
- **Bezug:** K 4, K 10, T 3, T 12.

## E-102 Tilgungsplan: Fälligkeiten, Zinstage, Rundung

- **Frage:** Wie werden Zinsen je Rate exakt und für alle drei Methoden centgenau festgelegt (T 12: Schaltjahr, Monatsende; T 22: Rundung)?
- **Entscheidung:** Monatliche Raten, Fälligkeiten `monat_plus(erste_faelligkeit, i − 1)` (verankert). `30/360`: jede volle Periode zählt 30 Tage, gebrochene Teile (erste Periode, Sondertilgung innerhalb einer Periode) nach 30E/360. `act/360` und `act/365`: tatsächliche Tage, Basis 360 bzw. immer 365 (auch im Schaltjahr). Zins je Rate = exakte rationale Summe über die Teile, kaufmännisch auf ganze Cent gerundet; Tilgung = Rate − Zins; Schlussrate = Restschuld + Zins. Höchstens 1 200 Raten, sonst `kredit_rate_zu_klein`. Andere Ratenrhythmen sind nicht vorgesehen.
- **Begründung:** Deutsche Annuitätendarlehen rechnen mit 30/360 üblicherweise einen Monatszins von genau 1/12; die reine 30E/360-Tagezählung würde bei Fälligkeit am 28.–31. und im Februar 28 oder 32 Tage ergeben. act/365 „fixed“ ist die verbreitete Variante; mit 366 im Schaltjahr gäbe es zwei Konventionen. Rundung nur am Zins und exakte Ganzzahlen sonst sichern, dass Zins + Tilgung genau die Rate ist und Rundungsfehler nicht über die aufgezinsten halben Cent hinaus auflaufen. Die Verankerung an der ersten Fälligkeit verhindert, dass ein 31. nach dem Februar dauerhaft zum 28. wird.
- **Bezug:** K 10, T 12, T 22.

## E-103 Erkennung und Aufteilung der Raten

- **Frage:** Woran wird eine Ratenzahlung erkannt, welcher Rate wird sie zugeordnet, und welchen Status hat sie?
- **Entscheidung:** Zahlung auf dem Zahlungskonto, Bedingungen (Empfänger/Verwendungszweck wie Regeln) erfüllt, Betrag genau die Rate einer noch nicht zugeordneten Zeile, Datum höchstens 5 Tage von deren Fälligkeit entfernt (nächste, bei Gleichstand frühere). Aufteilung in Zahlungs-, Zins- und Tilgungssplit (Memos `Zinsanteil`, `Tilgungsanteil`), Status `vorlaeufig`. In der Synchronisation als Stufe 0 vor den Split-Vorlagen; für vorhandene Buchungen über `POST /api/kredite/{id}/zuordnen` (Änderungsquelle `kredit`).
- **Begründung:** K 10 nennt die vorläufige Aufteilung der Rate vom Girokonto. Ohne Betragsgleichheit wäre eine Sondertilgung oder eine fremde Zahlung leicht als Rate fehlgedeutet. Vorrang vor Vorlagen, weil eine Rate nach dem Plan aufgeteilt werden muss und keine feste Vorlage passt. Das automatische Setzen von `vorlaeufig` ist wie das Anlegen mit `importiert` eine Wirkung der Anwendung, keine Statusänderung durch den Anwender.
- **Bezug:** K 10, T 12, E-074.

## E-104 Sondertilgungen als Parameter, Buchung durch den Anwender

- **Frage:** Werden Sondertilgungen gebucht oder nur geplant?
- **Entscheidung:** Sondertilgungen sind Parameter des Plans (Datum, Betrag); sie mindern die Restschuld an ihrem Datum (Zins je Teil der Periode) und damit alle späteren Zinsanteile. Eine Sondertilgung über die Restschuld hinaus wird begrenzt. Die Zahlung bucht der Anwender wie jede Umbuchung; sie wird nicht automatisch als Rate aufgeteilt.
- **Begründung:** K 10 nennt Sondertilgungen als Parameter. Eine automatische Deutung beliebiger Zahlungen an die Bank als Sondertilgung wäre fehleranfällig; ein vergessener Eintrag zeigt sich im Jahresabgleich als Differenz.
- **Bezug:** K 10, T 12.

## E-105 Jahresabgleich mit genau einer Korrekturbuchung, ohne Neuverankerung

- **Frage:** Womit wird der Jahresauszug verglichen, wie sieht die Korrekturbuchung aus, und was bedeutet „zur Bestätigung“?
- **Entscheidung:** Verglichen wird mit der *gebuchten* Restschuld (negativer Saldo des Darlehenskontos am 31.12.) und der Zinssumme der Buchungen des Kredits im Jahr. Bei Abweichung genau eine Korrekturbuchung am 31.12. (Status `abgeglichen`) mit den Splits Zinskonto `+dz`, Darlehenskonto `−dr` und, falls `dz ≠ dr`, „Korrekturen“ `dr − dz`; danach stimmen beide Werte mit dem Auszug. Alle zugeordneten Raten des Jahres werden `abgeglichen`. Der Probelauf (`trocken`) ist der Vorschlag, der Aufruf ohne `trocken` die Bestätigung. Je Jahr ein Abgleich (`kredit_jahr_abgeglichen`). Der Plan wird nicht neu verankert.
- **Begründung:** Die Korrektur muss die Buchungen richtigstellen, also mit dem Gebuchten verglichen werden, nicht mit dem Plan. Bei korrekt gebuchten Raten gilt meist `dz = dr` (mehr Zins heißt weniger Tilgung), dann reicht eine Umbuchung von Tilgung zu Zins. Eine Neuverankerung des Plans am Auszug wäre bei Fälligkeiten zum Monatsanfang falsch (der Zins der Januar-Rate gehört zum Dezember) und schwer vorhersagbar; neue Parameter setzt der Anwender ausdrücklich. Ein zweiter Abgleich desselben Jahres würde eine zweite Korrektur erzeugen und T 12 („genau eine“) verletzen.
- **Bezug:** K 10, T 12, T 4 (vorläufig → abgeglichen).

## E-106 Berichte: Kontostandsverlauf und Einnahmen/Ausgaben

- **Frage:** Welche Berichte gehören zu M5, und wie werden Stichtage, leere Konten und Umbuchungen behandelt?
- **Entscheidung:** `GET /api/berichte/kontostand` liefert je Konto eine Datenreihe der Salden an den Stichtagen `von`, allen Intervallenden dazwischen und `bis` (Intervalle Tag, Woche, Monat, Jahr; Vorgabe Monat), inklusive des Stichtags, optional mit Unterkonten; ohne Kontoangabe alle Bestandskonten. `GET /api/berichte/einnahmen-ausgaben` summiert je Periode die Splits auf Ertrags- und Aufwandskonten (dazu „Unkategorisiert“ getrennt); Umbuchungen buchen auf keine solchen Konten und zählen daher nie (E-059). Höchstens 5 000 Punkte.
- **Begründung:** K 11 verlangt zunächst nur den Kontostandsverlauf; T 15 prüft ihn gegen die Summe der Splits je Stichtag, also genau `saldo(k, s)` wie in der Kontenübersicht. Der Einnahmen/Ausgaben-Bericht macht die in E-059 angekündigte Statistik prüfbar (T 11), ohne eine eigene Umbuchungslogik zu brauchen. Die Grenze schützt vor versehentlich riesigen Antworten (z. B. Tagesintervall über Jahrzehnte).
- **Bezug:** K 11, T 11, T 15, E-059.

## E-107 CSV-Export: eine Zeile je Split, verlustfrei

- **Frage:** Welches CSV-Format (Trennzeichen, Kodierung, Spalten) ist „verlustfrei wieder einlesbar“?
- **Entscheidung:** UTF-8 mit BOM, `;` als Trennzeichen, `\r\n`, Quoting nach RFC 4180 wie Pythons `csv` (`QUOTE_MINIMAL`), Spaltennamen in der ersten Zeile, eine Zeile je Split mit den Buchungsfeldern in jeder Zeile; Beträge als Euro mit Dezimalkomma und zwei Nachkommastellen; Listen (Tags, Herkunftskennungen) als JSON-Liste. Spalten fest (`berichte.md` 4.2). Alle Filter und die Sortierung der Buchungsliste gelten. Kein Schutz durch vorangestellte Zeichen gegen Formeln in Tabellenkalkulationen.
- **Begründung:** `;` und Dezimalkomma sind in deutschen Tabellenkalkulationen üblich, der BOM lässt sie UTF-8 erkennen. Eine Zeile je Split bildet Splitbuchungen vollständig ab; JSON-Listen sind eindeutig, auch wenn Namen Trennzeichen enthalten. „Verlustfrei“ (T 14) heißt: alle Felder der Protokollform außer dem flüchtigen Vorschlag lassen sich aus der Datei zurückgewinnen; ein Präfix gegen Formeln würde genau das verletzen (Archivzweck, K 14).
- **Bezug:** K 14, T 14.

## E-108 PDF-Export: Bibliothek frei, prüfbare Marken

- **Frage:** Wie wird ein PDF ohne Netzwerk erzeugt, und wie prüft ein Test „enthält alle gefilterten Buchungen“, ohne das Layout festzulegen?
- **Entscheidung:** Bibliothek frei, nur per pip installierbar oder Standardbibliothek (geprüft am 2026-11-09: `reportlab` 5.1 und `fpdf2` 2.9 als reine Python-Wheels von PyPI; `reportlab` war in der Testumgebung bereits installiert). Prüfbar sind: gültige PDF-Datei, mit `pypdf` extrahierbarer Text, je Buchung genau eine Marke `[#<id>]` mit Datum (`TT.MM.JJJJ`) und Betrag in derselben Zeile, keine fremden Marken, `Anzahl Buchungen: <n>`. Die Tests benötigen zusätzlich `pypdf` (neu in `requirements-tests.txt`).
- **Begründung:** Eine eindeutige ASCII-Marke übersteht die Textextraktion zuverlässig, auch bei Seitenumbrüchen und Standardschriften ohne Umlaut-Probleme; Empfänger und Verwendungszweck dürfen dagegen gekürzt oder ersetzt werden (z. B. Emoji ohne passende Schrift). Layout, Seitenformat und weitere Inhalte bleiben der Implementierung überlassen.
- **Bezug:** K 14, T 14, E-028 (kein Netzwerk).

## E-109 Kredite in Protokoll und Sicherung, Objektarten nur bei Vorhandensein

- **Frage:** Wie kommt das neue Objekt `kredit` in Protokoll und Sicherung, ohne die M9-Tests (`anzahl` mit genau acht Schlüsseln, Inhaltsprüfsumme) und die Spezifikationstests von M4/M9 zu brechen?
- **Entscheidung:** `kredit` ist protokolliertes Objekt (Sortierung nach `vorlage`, neue Quelle `kredit`) und Teil der Sicherung. In `anzahl` und `inhalt` erscheint der Schlüssel `kredit` nur, wenn die Sicherung Kredite enthält, in `unterschied` nur, wenn Sicherung oder Bestand welche enthalten (`sicherung.md` 2.5); fehlende Objektarten gelten wie bisher als leer (3.4). Die Pflichtschlüssel von `anzahl` im Schema bleiben die acht aus M9. Die Spezifikationstests `test_m4_schemas_rueckwaertskompatibel` (Objektart endet nicht mehr mit `vorlage`) und `test_m9_sicherung` (Version „mindestens 2.4.0“, Objektarten ohne `kredit`) werden wie in E-078/E-084/E-093 gelockert; die exakte Prüfung steht im neuen `test_m5_schemas`.
- **Begründung:** Ein immer vorhandener Schlüssel `kredit: 0` änderte die Inhaltsprüfsumme jeder Sicherung und machte unveränderte M9-Tests rot (E-029). „Nur bei Vorhandensein“ ist mit 3.4 verträglich und hält Sicherungen ohne Kredite byte-gleich im Inhalt mit M9. Spätere Objektarten folgen derselben Regel.
- **Bezug:** E-029, E-078, E-084, E-087, E-093, `sicherung.md` 2.3, 3.4.

## E-110 Konten mit Kreditbezug löschen, Buchungen mit Zuordnung löschen

- **Frage:** Was passiert beim Löschen eines Kontos, auf das ein Kredit verweist, und beim Löschen einer zugeordneten Rate?
- **Entscheidung:** Beide Löschwege für Konten (`DELETE` und `POST …/loeschen`, auch im Probelauf) antworten 409 `konto_in_verwendung` mit `details.kredit_ids`; der Anwender ändert oder löscht zuerst den Kredit. Wird eine zugeordnete Buchung gelöscht (gleich auf welchem Weg), entfällt ihre Zuordnung in derselben Änderung; die `buchung_id` eines Abgleichs wird null.
- **Begründung:** Ein Kredit ohne Darlehens-, Zahlungs- oder Zinskonto ist nicht mehr berechenbar; ein automatisches Umhängen (wie bei Regeln, E-064) hätte keine sinnvolle Bedeutung. Ohne Kredite ändert sich an beiden Operationen nichts (E-029). Zuordnungen auf gelöschte Buchungen würden die Bezugsprüfung beim Rückgängig scheitern lassen und eine Fälligkeit dauerhaft blockieren.
- **Bezug:** E-029, E-060, E-064, `loeschen.md` 7, `kredite.md` 2.3.

## E-111 Präzisierungen aus dem Lauf gegen die Wegwerf-Referenz (ergänzt E-102 und E-105)

- **Frage:** Zwei Randfälle von M5 waren beim ersten Entwurf nicht widerspruchsfrei: (1) Tilgt eine Sondertilgung zu Beginn einer Periode alles und fällt kein Zins an, wäre die Schlussrate 0; der Entwurf ließ diese Zeile weg, dann fehlte die Sondertilgung in `summe_sondertilgung`, und `summe_tilgung + summe_sondertilgung = restschuld` galt nicht mehr. (2) Im Probelauf des Jahresabgleichs kann der Korrektursplit auf das Konto „Korrekturen“ zeigen, das es noch nicht gibt; der Probelauf darf aber nichts anlegen.
- **Entscheidung:** (1) Die Zeile mit `rate = 0` bleibt im Plan (ein Plan hat immer mindestens eine Zeile, `letzte_faelligkeit` ist nie null); Zeilen mit `rate = 0` werden nie einer Zahlung zugeordnet (`kredite.md` 3.5, 4.1). (2) Im Probelauf hat ein solcher Split `konto_id = null` (`KorrekturSplit.konto_id` nullable, `kredite.md` 5); ohne `trocken` wird das Konto angelegt und seine ID eingetragen.
- **Begründung:** Die Summenregel ist eine einfache, prüfbare Invariante des Plans (Hypothesis-Test `test_zufaellige_plaene_gleich_orakel` hat den Widerspruch gefunden). Eine erfundene ID im Probelauf wäre falsch, ein Anlegen verletzte „Probelauf ändert nichts“ (`protokoll.md` 4).
- **Bezug:** E-102, E-105, `kredite.md` 3.5, 4.1, 5, `openapi.yaml` 2.5.0.

## E-112 Umfang und Aufteilung der Spezifikation für Meilenstein 6

- **Frage:** Wie wird M6 (echtes FinTS-Plugin, Mail über IMAP/OAuth2, ntfy, Geheimnisspeicher, PIN über systemd-creds, TAN-Erinnerungen) so geschnitten, dass ein anderer Agent ohne Rückfragen implementieren kann und keine echten Fremdsysteme berührt werden?
- **Entscheidung:** Vier neue Dokumente `spec/api/fints.md`, `spec/api/mail.md`, `spec/api/benachrichtigungen.md`, `spec/api/geheimnisse.md`; M6-Abschnitte in `python-api.md` (13), `plugins.md` (9), `synchronisation.md` (18), `protokoll.md` (12), `sicherung.md` (2.6); `openapi.yaml` 2.6.0 mit den Tags `geheimnisse` und `mail`. Jeder Endpunkt eines Fremdsystems ist konfigurierbar (`fints_url`, `imap_host`/`imap_port`/`imap_tls`, `oauth_*_url`, `ntfy_url`, `tls_ca_datei`, `credentials_verzeichnis`); das ist die Naht, an der die Tests lokale Attrappen auf `127.0.0.1` einsetzen (`tests/hilfen/fints_attrappe.py`, `imap_attrappe.py`, `oauth_attrappe.py`, `ntfy_attrappe.py`). Tests unter `tests/app/m6/` (Marker `m6`), Attrappen-Selbsttests ohne App unter `tests/attrappen/`. Der Umfang folgt `spec/meilensteine.md` M6; der Mail-Abgleich mit Sammelbuchungen bleibt außerhalb (K 1).
- **Begründung:** Gleiche Aufteilung wie M3–M5 (ein Dokument je Fachgebiet). Konfigurierbare Endpunkte sind auch im Betrieb nötig (Bank-URL, eigener ntfy-Server) und ersetzen jede Testhintertür. Ohne neue Konfiguration bleibt jedes frühere Verhalten gleich (E-029): unkonfigurierte echte Plugins werfen weiter `PluginNichtVerfuegbar` ohne Verbindung (E-017), das Benachrichtigungs-Plugin ist im Echtmodus `keins`.
- **Bezug:** K 3, K 6, K 13, T 7, T 16, T 17, T 18, T 21, E-017, E-028, E-029.

## E-113 python-fints ist installierbar; Attrappe auf Protokollebene

- **Frage:** Ist python-fints installierbar, und wie wird ohne echte Bank getestet?
- **Entscheidung:** Geprüft am 2026-11-09: `pip install fints` installiert 5.0.1 (reines Python-Wheel, Abhängigkeiten `mt-940`, `sepaxml`, `bleach`, `lxml`, `requests`, `enum-tools`). Keine Alternative nötig. Die FinTS-Attrappe ist ein HTTP-Server, der FinTS-3.0-Nachrichten mit den Segmentklassen von python-fints zerlegt und baut (BPD/UPD, HKSPA, HKCAZ camt.052.001.08 oder HKKAZ MT940, HKTAN Version 6 mit Matrix-Code-PNG, Aufsetzpunkte). Rückmeldecodes der Attrappe sind festgelegt (`fints.md` 6): 0030 TAN nötig, 3076 keine SCA nötig, 3040 Aufsetzpunkt, 9931 PIN falsch, 3938 gesperrt, 9941 TAN falsch (Auftrag bleibt offen), 9955 TAN-Auftrag abgelaufen/unbekannt, 9010 abgelehnt, 9210 Konto unbekannt. `fints` kommt in `requirements-tests.txt`. Ein Probelauf mit `FinTS3PinTanClient` gegen die Attrappe (beide Profile, QR-TAN, falsche und richtige TAN) war erfolgreich.
- **Begründung:** T 7 verlangt eine Attrappe mit festgelegten Antworten; auf Protokollebene prüft sie auch die Einbindung der Bibliothek (E-028). python-fints selbst testet mit einem ähnlichen lokalen Server. Die Segmentklassen vermeiden Fehler beim Maskieren und Zählen; die Attrappe ist kein Anwendungscode. Für den abgelaufenen TAN-Auftrag gibt es keinen einheitlichen Bankcode; 9955 ist Festlegung der Attrappe, jede andere 9xxx-Rückmeldung führt beim Plugin ohnehin zu einem Fehler.
- **Bezug:** K 6, T 7, E-028.

## E-114 camt.052 bevorzugt, MT940 als Rückfall, Hash-Kennung

- **Frage:** Welches Umsatzformat verwendet das Plugin, wie werden Felder abgebildet, und woher kommt eine stabile `umsatz_id`?
- **Entscheidung:** Bietet die Bank HKCAZ mit camt.052.001.08 an, wird es verwendet (gebuchte und vorgemerkte Umsätze, `RvslInd` als Storno, `AcctSvcrRef` als Kennung `ref:…`); sonst MT940 über HKKAZ (nur gebuchte Umsätze, `RC`/`RD` als Storno mit SWIFT-Vorzeichen: `RC` negativ, `RD` positiv, Buchungsjahr aus der Valuta mit 180-Tage-Regel). Verwendungszweck- und Namensteile werden ohne Trennzeichen verbunden. Ohne Bankreferenz: `h:` + 16 Hexziffern SHA-256 über die abgebildeten Felder + laufende Nummer gleicher Einträge im Abruf (`fints.md` 3.4). Die Abbildung ist vollständig festgelegt, damit die Tests sie gegen die Generatorwahrheit prüfen.
- **Begründung:** camt ist strukturiert und unterscheidet gebucht/vorgemerkt sowie Storno eindeutig; MT940 ist bei manchen Banken der einzige Weg. python-fints mischt bei MT940 gebuchte und vorgemerkte Teile; Vormerkungen werden ohnehin nie gebucht (`synchronisation.md` 4.2), daher entfallen sie dort. Die Bibliothek `mt-940` setzt das Vorzeichen bei `RC`/`RD` anders als SWIFT – deshalb steht die Regel ausdrücklich da. Die laufende Nummer macht zwei gleiche Kaffeekäufe am selben Tag unterscheidbar; weil Abrufe ganze Tage umfassen, ist sie stabil.
- **Bezug:** K 6, T 6, T 7, `synchronisation.md` 4.3.

## E-115 PIN über `$CREDENTIALS_DIRECTORY`, ohne Aufruf von systemd-creds

- **Frage:** Wie kommt die mit systemd-creds verschlüsselte PIN in die App, und wie wird das ohne systemd getestet (der Auftrag schlägt z. B. einen konfigurierbaren Befehl vor)?
- **Entscheidung:** Die App ruft `systemd-creds` nie selbst auf. systemd entschlüsselt beim Start (`LoadCredentialEncrypted=kontor-bank-pin:…`, möglichst TPM-gebunden) und stellt die PIN als Datei `kontor-bank-pin` in `$CREDENTIALS_DIRECTORY` bereit; die App liest sie bei jedem Bedarf (`bank_pin_quelle = "systemd-creds"`). Die Testnaht ist das Verzeichnis (`credentials_verzeichnis`). Nach `BankPinFalsch` oder `BankZugangGesperrt` ist die Quelle bis zum Neustart gesperrt; `PUT/DELETE /api/sync/pin` → 409 `pin_quelle_systemd`. Derselbe Mechanismus liefert optional den Geheimnisschlüssel (`kontor-geheimnisschluessel`).
- **Begründung:** So ist es der vorgesehene systemd-Weg; ein eigener Aufruf von `systemd-creds decrypt` bräuchte Rechte auf den Host-Schlüssel und brächte die PIN in einen Kindprozess (K 6: nie auf der Kommandozeile). Ein Befehl als Attrappe würde nur eine Funktion testen, die es im Betrieb nicht gibt. Die Sperre verhindert eine Kontosperre durch wiederholte falsche PIN, die die App nicht ändern kann.
- **Bezug:** K 6, T 18, `synchronisation.md` 12.

## E-116 Geheimnisspeicher mit AES-256-GCM; was ein Geheimnis ist

- **Frage:** Wie werden Tokens und Zugangsdaten „verschlüsselt gespeichert, nie im Klartext“ (K 3), woher kommt der Schlüssel, und was zählt als Geheimnis?
- **Entscheidung:** AES-256-GCM aus `cryptography` (geprüft am 2026-11-09: Version 50 per pip installierbar und in der Testumgebung vorhanden), je Schreiben eine zufällige 12-Byte-Nonce, Name als zusätzliche authentisierte Daten, Ablage in der aktiven Datenbank. Schlüssel: zuerst `$CREDENTIALS_DIRECTORY/kontor-geheimnisschluessel`, sonst eine Schlüsseldatei (Vorgabe neben der Datenbank, angelegt beim ersten Schreiben mit Rechten 0600, Base64 von 32 Bytes). Geheimnisse sind PIN, TAN, OAuth-Client-Secret, Refresh-/Access-Tokens, ntfy-Token, Schlüssel, PKCE-Werte; Benutzerkennung, BLZ, URLs, Postfachadressen, Client-ID und ntfy-Thema sind Konfiguration. Werte erscheinen in keiner Antwort; REST setzt und löscht nur `ntfy_token` und `oauth_client_secret`. Die PIN liegt nie im Speicher (K 6).
- **Begründung:** AES-GCM ist authentisiert (ein falscher Schlüssel wird erkannt, `lesbar = false`), die Bindung an den Namen verhindert das Vertauschen von Chiffretexten. Ein Schlüssel neben der Datenbank schützt die Datenbankdatei und jede Kopie davon; mit systemd-creds/TPM ist er zusätzlich an den Rechner gebunden. Die Benutzerkennung allein gewährt keinen Zugang (dafür braucht es PIN und TAN); als Konfiguration bleibt die Einrichtung einfach.
- **Bezug:** K 3, K 6, K 13, T 16, T 18, E-090.

## E-117 Gmail verlangt den vollen Scope; „nur lesend“ erzwingt der Client

- **Frage:** K 13 verlangt „nur Lesezugriff“. Gmail lässt IMAP aber nur mit dem Scope `https://mail.google.com/` zu (der Scope `gmail.readonly` gilt nur für die Gmail-API). Wie wird „nachweislich nur lesend“ (T 16) erfüllt?
- **Entscheidung:** Scope `https://mail.google.com/` (fest), dazu eine abgeschlossene Liste erlaubter IMAP-Befehle: Ordner nur mit `EXAMINE` (nie `SELECT`), Inhalte nur mit `BODY.PEEK[]`, keine schreibenden Befehle, nie `LOGIN`. Die IMAP-Attrappe beantwortet verbotene Befehle mit `NO` und zeichnet sie als Verstoß auf; die Tests prüfen, dass es keinen gibt und dass `\Seen` unverändert bleibt.
- **Begründung:** Eine Alternative über die Gmail-API widerspräche K 13 (IMAP). Mit `EXAMINE` ist der Ordner auf Serverseite schreibgeschützt, `PEEK` lässt Markierungen unberührt; die feste Befehlsliste macht das prüfbar.
- **Bezug:** K 13, T 16.

## E-118 Postfächer im Buchbestand, Mail-Spiegel als Betriebszustand

- **Frage:** Welche neuen Zustände von M6 gehören in Protokoll und Sicherung (CLAUDE.md, `sicherung.md` 2.3)?
- **Entscheidung:** Postfächer (Adresse, Bezeichnung, Ordner, Absenderfilter, aktiv) sind ein protokolliertes Objekt `postfach` (`postfach_anlegen`/`_aendern`/`_loeschen`) und Teil der Sicherung, wie Kredite nur bei Vorhandensein in `anzahl`/`inhalt`/`unterschied` (E-109). Abgerufene Nachrichten sind ein Spiegel des Postfachs und wie Synchronisationsläufe Betriebszustand: nicht protokolliert, nicht gesichert, erneut abrufbar. Anmeldestatus, Tokens, Zustellstatus und Erinnerungszähler sind Betriebszustand bzw. Geheimnis und nie Teil der Sicherung. Der Betriebszustand hängt an der Adresse, damit Anmeldung und Spiegel ein Einspielen mit gleicher Adresse überstehen. Die Spezifikationstests `test_m5_schemas` (Version genau 2.5.0, Objektarten genau bis `kredit`) und `test_m9_sicherung` (Objektarten ohne `kredit`) werden wie in E-109 gelockert; die exakte Prüfung steht im neuen `test_m6_schemas`.
- **Begründung:** Die Postfacheinstellungen gibt der Anwender ein und erwartet sie nach einer Wiederherstellung zurück. Mails dagegen bleiben beim Anbieter, enthalten Daten Dritter und würden die Sicherung stark vergrößern; ein Mail-Abgleich, der sie fachlich braucht, ist nicht Teil des Plans. „Nur bei Vorhandensein“ hält die M9- und M5-Prüfsummen unverändert.
- **Bezug:** K 13, K 17, E-029, E-087, E-090, E-109, `sicherung.md` 2.3.

## E-119 Zustellung per ntfy: Plugins, Ablauf, Mock-Modus

- **Frage:** Wie wird „jeder Auslöser genau eine Nachricht, keine Flut“ (T 17) mit einer austauschbaren Schnittstelle umgesetzt, und darf ntfy im Mock-Modus senden?
- **Entscheidung:** Plugins `keins` (Vorgabe im Echtmodus), `mock` (Liste im Arbeitsspeicher, Vorgabe im Mock-Modus, nur dort erlaubt) und `ntfy`. Jede Benachrichtigung der internen Liste wird genau einmal zugestellt: erster Versuch sofort in derselben Anfrage bzw. demselben Takt, Wiederholung nach Fehlschlag im Planer-Takt (Abstand `zustellung_wiederholung_minuten`, höchstens `zustellung_max_versuche`, danach `aufgegeben`). ntfy über JSON-Veröffentlichung an der Wurzel (`topic`, `title`, `message`, `priority`, `tags`, `click`) mit optionalem Bearer-Token aus dem Geheimnisspeicher; absolute Links über `oeffentliche_url`. ntfy darf auch im Mock-Modus senden; der Titel beginnt dann mit `[Mock] `.
- **Begründung:** Die Entprellung der Arten (M2–M5) ist die einzige Stelle, an der über „gleiches Ereignis“ entschieden wird; die Zustellung fügt keine eigene Logik hinzu und kann daher keine Flut erzeugen. JSON vermeidet die Kodierung von Umlauten in HTTP-Köpfen. Mock-Daten gelangen durch eine Push-Nachricht nicht in die Echtdatenbank (die Trennung aus K 3 bleibt), und gerade in der Debug-Phase will man die Meldungen auf dem Handy sehen; der Vorsatz verhindert Verwechslungen. Die Vorgabe `keins` im Echtmodus hält frühere Tests unverändert.
- **Bezug:** K 3, K 6, T 17, T 21, E-029, E-100.

## E-120 Refresh-Tokens im Google-Testmodus (sieben Tage)

- **Frage:** K 13: „Im Testmodus laufen Refresh-Tokens nach sieben Tagen ab, dafür ist eine Lösung zu finden.“ Wie geht die App damit um?
- **Entscheidung:** Der Ablauf lässt sich technisch nicht verhindern, aber vollständig beherrschen: (1) Die App kennt den Ablaufzeitpunkt (Feld `refresh_token_expires_in` der Tokenantwort, falls vorhanden, sonst Ausstellung + `oauth_refresh_gueltig_stunden`, Vorgabe 168) und zeigt ihn an. (2) `oauth_vorwarnung_stunden` (Vorgabe 24) vorher kommt einmal je Anmeldung eine ntfy-Nachricht mit Link zur Anmeldung. (3) Beim Ablauf wird proaktiv (ohne Anfrage beim Anbieter) bzw. reaktiv (`invalid_grant`) auf `abgelaufen` gestellt; ein `invalid_grant` mehr als eine Stunde vor dem bekannten Ablauf gilt als Widerruf. Beides erzeugt einmal je Anmeldung eine Benachrichtigung, Abrufe des Postfachs pausieren ohne Fehlermeldungsflut, das andere Postfach läuft weiter. (4) Erneute Anmeldung mit zwei Schritten (Link öffnen, Umleitungs-URL zurückgeben; PKCE, `prompt=consent`). (5) Betriebsempfehlung: das Google-Projekt veröffentlichen (Status „In production“, für den Eigengebrauch ohne Verifizierung möglich, mit Warnhinweis) und `oauth_refresh_gueltig_stunden=0` setzen; dann entfällt der Ablauf.
- **Begründung:** Google meldet abgelaufene und widerrufene Tokens gleich (`invalid_grant`, „Token has been expired or revoked.“); die bekannte Ablaufzeit unterscheidet beide Fälle und erlaubt die Vorwarnung, bevor Mails fehlen. Die Tests prüfen das ohne Uhrmanipulation über kurze Lebensdauern der OAuth-Attrappe.
- **Bezug:** K 13, T 16, T 17, E-100.

## E-121 TAN-Erinnerungen: Abstand, Höchstzahl, kein Nachholen

- **Frage:** K 6 Schritt 4: „erinnert in Abständen und bricht nach Ablauf der Gültigkeit sauber ab“ – wie oft, wie viele, und was passiert bei einem verspäteten Planer-Takt?
- **Entscheidung:** Erinnerung Nummer `n` (eigene Benachrichtigung `tan_erinnerung:<id>:<n>`, Link zur TAN-Seite) wird fällig, wenn `n · tan_erinnerung_minuten` seit `erstellt_am` vergangen sind, höchstens `tan_erinnerung_anzahl` (Vorgaben 5 Minuten, 3), nur solange die Anforderung offen und nicht abgelaufen ist; ein Takt erzeugt höchstens eine Erinnerung mit der höchsten fälligen Nummer, ausgelassene werden nicht nachgeholt. Der Ablauf selbst bleibt wie in M2 (`tan_abgelaufen`), jetzt mit Push.
- **Begründung:** Echte QR-TAN-Anforderungen gelten meist nur Minuten; mehr als drei Erinnerungen wären eine Flut (T 17). Je Erinnerung ein eigener Schlüssel hält die Entprellung einfach und prüfbar. Kein Nachholen verhindert mehrere Pushes in einem Takt nach einem Ausfall.
- **Bezug:** K 6, T 17, `synchronisation.md` 7.

## E-122 Klartext nur auf Loopback, eigene Vertrauensanker, Netzsperre in Tests

- **Frage:** Wie verhindert die Konfiguration, dass Tokens oder PIN unverschlüsselt über das Netz gehen, und wie testet man TLS ohne echte Zertifikate und ohne Netz?
- **Entscheidung:** `http://` und `imap_tls = False` sind nur für `127.0.0.1`, `::1` und `localhost` zulässig (sonst `KonfigurationsFehler`); Ausnahmen sind `oeffentliche_url` und `oauth_redirect_uri`, die keine Geheimnisse transportieren. `tls_ca_datei` ersetzt die Vertrauensanker für alle ausgehenden TLS-Verbindungen; Zertifikate werden immer geprüft, Umleitungen nicht verfolgt. Die Tests erzeugen ein selbst signiertes Zertifikat für 127.0.0.1 und prüfen Erfolg mit und Ablehnung ohne passenden Anker. Die bestehende Netzsperre (`netz_gesperrt`) bleibt unverändert streng; die neue Fixture `netz_nur_loopback` nutzt dieselbe Sperre, lässt aber Verbindungen und Namensauflösung nur für Loopback zu und entfernt Proxy-Umgebungsvariablen.
- **Begründung:** Die Attrappen laufen ohne TLS am einfachsten; die Ausnahme ist auf Loopback beschränkt und kann im Betrieb keinen Schaden anrichten. Eine gelockerte `netz_gesperrt` würde die Zusicherung „Mock-Plugins bauen keine Verbindung auf“ (auch nicht zu 127.0.0.1) früherer Tests schwächen.
- **Bezug:** K 3, K 13, T 16, T 18, E-028.

## E-123 Präzisierungen aus dem Lauf gegen python-fints, imaplib und die Wegwerf-Referenz (ergänzt E-113, `mail.md` 3.3)

- **Frage:** Beim Prüfen der Attrappen mit den echten Bibliotheken und der Tests mit der Wegwerf-Referenz zeigten sich zwei Lücken: (1) python-fints wertet die Rückmeldung 9010 überall als Fehler der Dialoginitialisierung (`FinTSClientError`), auch zu einem einzelnen Auftrag; die Attrappe meldete abgelehnte Umsatzabrufe aber mit 9010 (E-113). (2) `mail.md` 3.3 legte nicht fest, ob bei gleicher `nachricht_id` zuerst Doppelte entfernt oder zuerst nach `seit` gefiltert wird; bei einer erneut abgelegten Nachricht nach `seit` lieferten beide Reihenfolgen Verschiedenes.
- **Entscheidung:** (1) Die Attrappe lehnt Umsatzabrufe für Konten in `fehler_iban` mit **9380** ab (`fints.md` 6); das Plugin meldet jede andere 9xxx-Rückmeldung als `BankFehler` mit `details.rueckmeldung`. 9010 bleibt der Code für einen unbekannten Kunden bei der Dialoginitialisierung. (2) Erst bleibt unter den von `UID SEARCH` gelieferten Nachrichten bei gleicher `nachricht_id` die mit der kleinsten UID, danach wird nach `empfangen ≥ seit` gefiltert (`mail.md` 3.3 angepasst).
- **Begründung:** (1) Ein Code, den die Bibliothek als Abbruch des Dialogs deutet, prüft nicht das Verhalten bei einem einzelnen abgelehnten Konto. (2) So hängt das Ergebnis nicht davon ab, ob die erste Ablage zufällig vor `seit` liegt; die Kopie wird nie als eigene Nachricht gespiegelt, und Mock- und IMAP-Plugin liefern dasselbe.
- **Bezug:** K 6, K 13, T 7, T 21, E-113, `fints.md` 6, `mail.md` 3.3.

## E-124 Antworten mit späteren optionalen Feldern in Tests früherer Meilensteine (W-004, ergänzt E-029)

- **Frage:** Der Implementierungs-Thread meldete (W-004): `tests/app/m2/test_m2_sync.py::test_laeufe_und_status` vergleicht `GET /api/sync/status` auf exakte Gleichheit mit einem Objekt aus den acht M2-Feldern; das in M6 hinzugekommene, im Schema optionale Feld `pin_quelle` (`fints.md` 5, `synchronisation.md` 18.1), das der M6-Test `test_m6_pin_systemd.py::test_vorgabe_eingabe` auch bei der Vorgabe `eingabe` verlangt, lässt den M2-Test scheitern. Dieselbe Instanz kann nicht beide Tests erfüllen; der M2-Test widerspricht E-029. Gibt es weitere solche Tests, und wie werden sie robust, ohne Prüfungen abzuschwächen?
- **Entscheidung:** (1) `tests/hilfen/vertrag.py` liefert jedes JSON-Objekt einer geprüften Antwort, dessen Schema feste Eigenschaften hat, als `Antwortobjekt` (Unterklasse von `dict`) mit der Menge der im Schema **optionalen** Felder. Beim Vergleich mit einer Erwartung des Tests (gewöhnliches `dict`) muss jedes erwartete Feld vorhanden und gleich sein; zusätzliche Felder der Antwort sind nur erlaubt, wenn das Schema sie als optional führt. Zwei Antwortobjekte (beide von der Anwendung, z. B. vor/nach oder Instanz A/B) werden weiter exakt verglichen. Die Schemaprüfung mit `additionalProperties: false` läuft unverändert vorher, unbekannte Felder bleiben also verboten, Pflichtfelder Pflicht. Damit prüft der M2-Test weiter genau die acht M2-Felder mit ihren Werten und lässt `pin_quelle` zu; der Testtext bleibt unverändert. (2) Systematische Suche mit einem **Erweiterungslauf**: Mit `KONTOR_TESTS_ZUSATZFELDER=1` bekommt jedes solche Antwortobjekt nach der Schemaprüfung ein zusätzliches optionales Feld `zusatz_spaeter_e029`. Gegen die Wegwerf-Referenz scheiterten so zunächst 203 App-Tests an exakten Objektvergleichen (fast alle Meilensteine: Regeln, Vorschläge, Protokollformen, Kredite, Berichte, Postfächer, Geheimnisse, Sicherung); mit (1) blieben elf, davon fünf echte Schwachstellen, die gezielt angepasst wurden: `test_m5_kredite_api.py::test_anlegen_mit_anfangsbuchung` (exakte Schlüsselliste → `pruefe_felder`: genau diese Felder, weitere nur optionale), `test_m5_kredite_api.py::test_plan_des_kredits_gleich_orakel` und `test_m9_vollstaendigkeit.py::test_vorlagen_mit_bezuegen_reihenfolge_und_zaehler` (schickten gelesene Objekte als Anfragekörper zurück, was mit einem späteren Antwortfeld 422 ergäbe → nur die Felder des Anfrageschemas senden), `test_m3_konto_loeschen.py` (`ohne_lauf`) und `test_import_kmy.py::test_rest_und_python_gleich` (Kopie per Dict-Ausdruck verlor die Regel → Hilfe `ohne`). Die übrigen sechs waren Artefakte des Laufs: Inhaltsprüfsummen, die Test und Anwendung aus denselben REST-Daten berechnen (`sicherung.md` 3.3); das künstliche Feld wird vor dem Hashen entfernt (`ohne_zusatzfeld`, in normalen Läufen ohne Wirkung), der M6-Postfachtest nutzt dafür die gemeinsame Hilfe `inhalt_sha256`. Danach ist der Erweiterungslauf bis auf die schon ohne ihn gegen die Referenz scheiternden Tests (`test_plugins.py`, Referenz unvollständig) grün. (3) Der Erweiterungslauf gehört ab jetzt zur Selbstprüfung (Lauf „Referenz mit Zusatzfeldern“, Kern-Tests müssen grün bleiben) und steht Implementierungs-Threads zur Verfügung. (4) Grenzen: Er erfasst Vergleiche über `Api` (`r.daten`); rohe `r.json()`-Auswertungen vergleichen in den Tests nur einzelne Felder oder Listen in `details`, Python-Ergebnisse (`als_dict()`, `tilgungsplan`) sind eigene Verträge.
- **Begründung:** E-029 erlaubt spätere optionale Felder; ein Test darf sie deshalb nicht verbieten, soll aber alles prüfen, was sein Meilenstein festlegt. Die Regel „nur optionale Zusatzfelder“ ist genau E-029 und schwächt keine Prüfung: Werte, Vollständigkeit und Schema bleiben geprüft. Eine zentrale Regel statt über hundert einzelner Änderungen hält die Tests früherer Meilensteine textlich unverändert und gilt automatisch für künftige Felder; der Erweiterungslauf weist nach, dass sie greift.
- **Bezug:** E-029, E-112, `fints.md` 5, `synchronisation.md` 18.1, T 1 (Änderungen an Tests nur dokumentiert), T 3.5/3.6 (Protokollformen).

## E-125 Anmeldung abschaltbar (Vorgabe aus), Betrieb mit Anmeldung, Testhilfe für frühere Tests

- **Frage:** T 18 verlangt, dass ohne Login keine Seite und kein Endpunkt erreichbar ist; die Tests von M1 bis M6 und M9 laufen ohne Login, teils mit rohem `TestClient` (`test_create_app_aus_umgebung` über `from_env`, Planer-Tests mit Lifespan). Der Plan (`meilensteine.md` M7) sah vor, dass frühere Tests eine angemeldete Sitzung über die Testhilfe erhalten. Wie bleiben frühere Tests unverändert lauffähig, ohne dass der Betrieb ungeschützt startet?
- **Entscheidung:** `KontorConfig.anmeldung` (bool) mit Vorgabe `False` in Python **und** `from_env` (`KONTOR_ANMELDUNG`, leer/fehlend → aus). Im Betrieb ist sie an: Die ausgelieferte Umgebungsdatei setzt `KONTOR_ANMELDUNG=1` (`betrieb.md` 3, von den M7-Tests geprüft); im Echtmodus ohne Anmeldung schreibt `create_app` eine Warnung ins Log. Sicherheitsköpfe, Eingabehärtung und Größengrenzen gelten immer, weil sie keine gültige frühere Anfrage ablehnen. Zusätzlich die im Plan vorgesehene Testhilfe als **Anmeldelauf**: Mit `KONTOR_TESTS_ANMELDUNG=1` erzeugt `tests/hilfen/api.py` jede Konfiguration mit `anmeldung=True`, richtet das Passwort über `kontor.anmeldung.passwort_setzen` ein, meldet die `Api` an und sendet bei schreibenden Anfragen den CSRF-Kopf; die Tests selbst bleiben unverändert. Tests mit rohem `TestClient` sind davon nicht erfasst und im Anmeldelauf ausgenommen (Liste in `TESTS_AUSFUEHREN.md`). Abweichung vom Plan: Die Testhilfe ist ein zusätzlicher Lauf, nicht der Normalfall.
- **Begründung:** Eine Vorgabe „an“ in `from_env` hätte den M1-Test `test_create_app_aus_umgebung` (roher `TestClient`, `GET /api/status`) und die M2-Planer-Tests gebrochen; E-029 verlangt, dass sie unverändert bestehen. Dasselbe Muster gilt seit M3 für verhaltensändernde Funktionen (E-054, E-072, E-100, E-119). Der Betrieb startet nicht über eine selbst gebaute Konfiguration, sondern über `python -m kontor` mit der ausgelieferten Umgebungsdatei; dort ist die Anmeldung an und geprüft. Der Anmeldelauf weist nach, dass jede frühere Funktion auch angemeldet mit CSRF-Schutz funktioniert (z. B. Uploads mit Multipart), ohne die Tests zu verdoppeln.
- **Bezug:** K 2, T 18, E-029, `sicherheit.md` 3.3, `python-api.md` 14.1.

## E-126 Passwort-Hash mit scrypt aus der Standardbibliothek

- **Frage:** Welches Hash-Verfahren, mit welchen Parametern und welcher Textform, so dass Tests es unabhängig nachrechnen können?
- **Entscheidung:** scrypt über `hashlib.scrypt` mit `n = 2^15`, `r = 8`, `p = 1`, 32 Bytes Schlüssel, 16 Bytes Salz, `maxmem` 64 MiB; Textform `scrypt$<n>$<r>$<p>$<salz-b64>$<schluessel-b64>`; Prüfen mit den gespeicherten Parametern und `hmac.compare_digest`; maßgeblich die NFC-Form, 12–1 024 Zeichen. Nicht wohlgeformte Textformen ergeben `False`.
- **Begründung:** scrypt ist speicherhart, von OWASP für Passwörter empfohlen und ohne zusätzliche Abhängigkeit (argon2-cffi wäre eine neue) in jeder Python-Installation mit OpenSSL verfügbar. `n = 2^15` kostet etwa 0,1–0,2 s je Prüfung auf der Zielhardware: spürbar für Angreifer, unmerklich für den Haushalt. Gespeicherte Parameter erlauben spätere Erhöhung. NFC verhindert, dass dasselbe Passwort je nach Tastatur oder Gerät (macOS liefert NFD) verschieden ist.
- **Bezug:** K 2, K 3, T 18, `sicherheit.md` 2.

## E-127 Allgemein zulässige Antworten 401, 403, 413, 429

- **Frage:** Mit Anmeldung, CSRF-Schutz, Netzbeschränkung und Größengrenzen kann jede der über hundert Operationen mit 401, 403, 413 oder (Anmeldung) 429 antworten. Jede Operation einzeln erweitern?
- **Entscheidung:** Ein Abschnitt `x-allgemeine-antworten` auf oberster Ebene von `openapi.yaml` nennt diese vier Antworten (Schema `Fehler`); der Vertragsprüfer der Tests akzeptiert sie für jede Operation zusätzlich zu den dort genannten. Operationen, bei denen sie fachlich zum Ablauf gehören (Anmeldung, Einrichtung, Passwort), führen sie zusätzlich ausdrücklich. Die exakte Versionsprüfung in `test_m6_schemas` wird wie in E-109 und E-118 auf „mindestens 2.6.0“ gelockert; die exakte Prüfung steht im neuen `test_m7_schemas`.
- **Begründung:** OpenAPI kennt keine globalen Antworten; über hundert gleichlautende Einträge wären fehleranfällig und hätten die exakten Antwortmengen früherer Spezifikationstests geändert. Die Erweiterung (`x-`) ist erlaubt und hält die Spezifikation gültig. Welche Antwort wann kommt, regelt `sicherheit.md`; Tests früherer Meilensteine prüfen weiterhin ihren exakten Statuscode.
- **Bezug:** T 18, E-029, `sicherheit.md` 11.

## E-128 Sitzungen: serverseitig, Cookie-Attribute, Ablauf nach Systemuhr

- **Frage:** Wie werden Sitzungen gespeichert, welche Cookie-Attribute gelten im Heimnetz ohne TLS, wann laufen sie ab, und gilt im Mock-Modus die simulierte Uhr?
- **Entscheidung:** Zufälliges Token (`token_urlsafe(32)`) im Cookie `kontor_sitzung` mit `HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age` = Höchstdauer; `Secure` bei HTTPS-Anfragen oder auf Wunsch immer. In der Datenbank nur ein Hash des Tokens. Leerlauf 1 Tag, Höchstdauer 30 Tage (konfigurierbar in Sekunden). Neue Sitzung bei jeder Anmeldung (keine Fixierung), Abmelden serverseitig, Passwortänderung beendet die anderen Sitzungen, Sitzungen überstehen Neustarts. Sitzungen, Sperren und Einrichtung richten sich immer nach der Systemuhr, nie nach der Mock-Uhr.
- **Begründung:** Im Heimnetz läuft der Dienst meist ohne TLS; ein immer gesetztes `Secure` würde dort jede Anmeldung verhindern. `SameSite=Strict` plus CSRF-Token (E-129) schützt auch ohne TLS vor fremden Seiten. Lange Leerlaufzeiten passen zur PWA auf dem Handy des Haushalts, die Höchstdauer begrenzt gestohlene Cookies. Ein gestohlenes Datenbankabbild (z. B. Sicherung) enthält keine verwendbaren Tokens. Die Mock-Uhr lässt sich per REST verstellen und darf Sicherheitsfristen nicht beeinflussen. Sekunden als Einheit machen den Ablauf in Tests mit kurzen Wartezeiten prüfbar.
- **Bezug:** K 2, T 18, `sicherheit.md` 4.

## E-129 Bremse für das Haushaltskonto und CSRF-Schutz

- **Frage:** Wie wird „falsches Passwort wird nach mehreren Versuchen gebremst“ umgesetzt, und wie der CSRF-Schutz?
- **Entscheidung:** Ein gespeicherter Zähler aufeinanderfolgender Fehlversuche je Datenbank (Anmeldung, altes Passwort, Einrichtungscode); ab `anmeldung_fehlversuche` (5) führt jeder weitere Fehlversuch zu einer Sperre von `anmeldung_sperre_sekunden · 2^(k)` (60 s, verdoppelt, höchstens ein Tag); während der Sperre 429 mit `Retry-After`, ohne das Passwort zu prüfen. CSRF: Token je Sitzung im Kopf `X-Kontor-CSRF` für alle schreibenden Methoden auf geschützten Pfaden, zusätzlich Prüfung von `Origin`/`Sec-Fetch-Site` auch beim Anmelden.
- **Begründung:** Ein Haushalt hat ein Konto und oft eine gemeinsame Adresse (NAT); eine Sperre je Adresse wäre wirkungslos, eine je Konto ist einfach und prüfbar. Die Verdopplung macht Durchprobieren aussichtslos (nach zehn Fehlversuchen über eine Stunde je Versuch), ohne den Haushalt nach einem Tippfehler lange auszusperren. Keine Prüfung während der Sperre verhindert, dass ein Angreifer an der Antwortzeit oder einem richtigen Treffer etwas erkennt. Synchronizer-Token und Herkunftsprüfung sind die Standardabwehr (OWASP) und funktionieren mit `fetch` der SPA.
- **Bezug:** T 18, `sicherheit.md` 4.5, 4.6.

## E-130 Eingabehärtung, Größengrenzen, kein Umschreiben im CSV-Export

- **Frage:** Wie werden „gezielte Angriffseingaben“ gegen SQL-Injection und XSS festgelegt, welche Grenzen gelten für Uploads, und wird der CSV-Export gegen Formelinjektion verändert?
- **Entscheidung:** Verhaltensregeln statt Implementierungsvorgaben: Texte mit SQL- oder HTML-Syntax werden unverändert gespeichert und zurückgegeben und wirken in Filtern nur als Text (`%`, `_` keine Platzhalter); serverseitiges HTML enthält keine Daten aus dem Buchbestand und spiegelt keine Anfrageteile; nur externe Skripte (CSP `script-src 'self'`). Keine Eingabe ergibt 5xx (tiefe Verschachtelung, Nullbytes, ungültiges UTF-8). Grenzen: Uploads 200 MiB, andere Körper 4 MiB, je konfigurierbar, 413 vor jeder Wirkung. Der CSV-Export bleibt verlustfrei (keine Vorsilbe `'` vor `=`, `+`, `-`, `@`).
- **Begründung:** Tests können nur Verhalten prüfen; „parametrisierte Abfragen“ zeigen sich darin, dass Angriffstexte wörtlich behandelt werden und die Datenbank unversehrt bleibt. Die Vorgaben der Grenzen liegen weit über den größten Dateien des Haushalts (der 50 000-Buchungen-Datensatz hat 2 MB) und damit über allem, was frühere Tests senden. M5 sichert eine verlustfreie CSV-Rundreise auch für beliebige Texte zu (Hypothesis); eine Vorsilbe würde sie brechen. Die CSV-Datei entsteht nur für den Haushalt selbst.
- **Bezug:** T 14 (Export), T 18, `sicherheit.md` 7, 8, 12, `berichte.md` 4.

## E-131 systemd-Dienst mit festem Benutzer, verschlüsselten Credentials und Härtung

- **Frage:** Welche Eigenschaften muss die ausgelieferte Unit haben (Benutzer, Credentials, Härtung), und was ist in einem unprivilegierten LXC-Container möglich?
- **Entscheidung:** Ausgeliefert im Paket `kontor.betrieb`: `kontor.service` (Type `exec`, `User`/`Group` `kontor` über `sysusers.d`, `StateDirectory`, Umgebungsdatei, `ExecStart` ohne Argumente außer `-m kontor`, `LoadCredentialEncrypted` für PIN und Geheimnisschlüssel, nie `LoadCredential`), eine feste Liste von Härtungsoptionen (`ProtectSystem=strict`, `NoNewPrivileges`, leere Capabilities, `SystemCallFilter=@system-service`, `RestrictAddressFamilies`, `UMask=0077` u. a.), `Restart=on-failure` mit `RestartPreventExitStatus=2` für Konfigurationsfehler; dazu Timer und Dienst für die tägliche Sicherung und ein Drop-in für die Variante „PIN nur in der Oberfläche“. Kein `DynamicUser`; kein `MemoryDenyWriteExecute` (verträgt sich nicht mit cffi in `cryptography`). Die Tests lesen die Dateien statisch.
- **Begründung:** Ein fester Benutzer hält Dateieigentümer über Neustarts, Snapshots und die getrennte Sicherungs-Unit stabil; mit `DynamicUser` müssten zwei Units denselben dynamischen Benutzer teilen. `LoadCredentialEncrypted` setzt K 6 um (PIN nur verschlüsselt, nur dem Dienst übergeben, nie in Kommandozeilen); ohne TPM im Container verschlüsselt `systemd-creds --with-key=host`. Die gewählten Härtungsoptionen funktionieren im unprivilegierten Proxmox-LXC mit `nesting=1`. Exit-Code 2 verhindert eine Neustartschleife bei falscher Konfiguration.
- **Bezug:** K 2, K 3, K 6, T 20, E-115, `betrieb.md` 4.

## E-132 Datenbank-Export ist die M9-Sicherung; zeitgesteuert über systemd

- **Frage:** K 2 nennt „zusätzlich Datenbank-Export“. Braucht M7 einen eigenen Export neben der Sicherung aus M9?
- **Entscheidung:** Nein. Der Export ist die M9-Sicherung (eigenständige SQLite-Datei plus Manifest). M7 ergänzt `kontor.sicherung.sichere_in_verzeichnis` mit Aufbewahrung der neuesten `behalten` Dateien je Modus, atomarem Schreiben und Rechten `0600`, die Kommandozeile `python -m kontor.sicherung` und einen täglichen systemd-Timer. Die Ablage auf dem Server ist eine ausdrückliche Ausnahme zu `sicherung.md` 8.
- **Begründung:** Ein zweites Format wäre doppelte Pflege; die Sicherung ist schon prüfbar vollständig, ohne Geheimnisse und einspielbar. Ein Timer außerhalb der App läuft auch, wenn der Planer hängt, und lässt sich mit systemd überwachen.
- **Bezug:** K 2, K 17, T 20, E-085, `betrieb.md` 8, `sicherung.md` 9.

## E-133 Leistungsziele und Messverfahren

- **Frage:** T 20 nennt nur die Buchungsliste (unter 1 s bei 50 000 Buchungen) und den Import (Grenzwert vorab festlegen). Welche Werte, wie gemessen, damit es in der Testumgebung zuverlässig ist?
- **Entscheidung:** Grenzwerte für 15 Vorgänge (`leistung.md` 3): Import 120 s, Liste und Filter 1 s, Suche und Übersicht 1 s, Berichte und Lernmodell 3 s, Mehrfachbearbeitung von 1 000 Buchungen 10 s, wiederkehrende Buchungen 10 s, CSV-Export 20 s, Sicherung 30 s, Neustart 5 s. Gemessen in-process über `TestClient` ohne die Schemaprüfung der Tests, Median aus fünf Läufen nach einem Aufwärmlauf; jedes Ergebnis wird zusätzlich gegen die Generatorwahrheit geprüft. `KONTOR_LEISTUNG_FAKTOR` skaliert nur für erkennbar langsamere Rechner. Marker `leistung`.
- **Begründung:** Ein Haushalt arbeitet mit der Liste, Suche und Übersicht ständig, daher dieselbe Grenze wie T 20; seltenere Vorgänge bekommen großzügigere Grenzen. In-process misst die Anwendung, nicht das Netz; der Median glättet Ausreißer einer geteilten Testmaschine. Die Grenzen lassen genug Abstand, um Indizes zu verlangen, ohne Mikro-Optimierung zu erzwingen.
- **Bezug:** T 20, `leistung.md`.

## E-134 Großer Datensatz auf Abruf statt eingecheckt

- **Frage:** Der Leistungsdatensatz (50 000 Buchungen) ist etwa 2 MB komprimiert, die vollständige Erwartung im bisherigen Format wäre über 30 MB. Einchecken oder erzeugen?
- **Entscheidung:** Erzeugen auf Abruf (`python -m generator --gross` bzw. die Testfixture; drei Sekunden), nicht einchecken (`fixtures/gross/` in `.gitignore`); `fixtures/MANIFEST.json` enthält unter `auf_abruf` die SHA-256 (gepackt und entpackt), `tests/generator/test_m7_gross.py` prüft Reproduzierbarkeit und zählt die Probewerte unabhängig im XML nach. Die Erwartung ist kompakt (Zählungen, Salden, Probewerte). Generatorversion 7.0.0.
- **Begründung:** Die Erzeugung ist schnell und deterministisch; eingecheckte Megabytes würden jede Änderung des Generators aufblähen, ohne Nutzen gegenüber einer geprüften Prüfsumme.
- **Bezug:** T 21, CLAUDE.md (Testdaten), `leistung.md` 1.

## E-135 Anmeldedaten sind Betriebszustand

- **Frage:** Gehören Passwort, Sitzungen und Sperren in Protokoll, Rückgängig und Sicherung (CLAUDE.md: „ab M9 gehört jeder neue fachliche Zustand zur Sicherung“)?
- **Entscheidung:** Nein: Sie sind kein fachlicher Zustand, sondern Zugangsdaten. Nicht protokolliert, nicht rückgängig zu machen, nie in der Sicherung, unverändert beim Einspielen. M7 führt keine neue Objektart ein; die Prüfsummen von M9 bis M6 bleiben gleich.
- **Begründung:** Eine Wiederherstellung soll den Haushalt nicht aussperren oder ein altes Passwort zurückbringen; Rückgängig einer Passwortänderung wäre ein Sicherheitsrisiko. Der Passwort-Hash ist zwar kein Klartext, gehört aber wie die Geheimnisse (E-090, `geheimnisse.md`) nicht in eine Datei, die den Server verlässt.
- **Bezug:** K 3, K 14, K 17, E-090, `sicherung.md` 9, `protokoll.md` 13.

## E-136 Sauberes Beenden: Frist, WAL-Checkpoint, verzögertes Mock-Plugin

- **Frage:** T 20: Neustart während einer Synchronisation ohne inkonsistenten Zustand. Was passiert beim geordneten Beenden mit einem laufenden Lauf und der Datenbank, und wie wird das deterministisch getestet?
- **Entscheidung:** Beim Lifespan-Ende: kein neuer Takt, das gerade verarbeitete Konto darf binnen `beenden_frist_sekunden` (20) fertig werden, danach Lauf `abgebrochen`, übrige Konten `abgebrochen`; dann `wal_checkpoint(TRUNCATE)` und Schließen, sodass die Hauptdatei allein vollständig ist. Die Datenbank läuft im WAL-Modus. Für Tests verzögert `mock_verzoegerung_ms` jeden Umsatzabruf des Mock-Plugins. Harte Abbrüche bleiben wie in M2 (`synchronisation.md` 10).
- **Begründung:** Ein angefangenes Konto abzubrechen wäre ebenfalls konsistent (Atomarität je Konto, M2), fertig verarbeitete Konten zu behalten spart aber einen erneuten Abruf und eine mögliche TAN. Der Checkpoint macht Proxmox-Snapshots und Dateikopien nach einem Stopp trivial korrekt. Eine konfigurierbare Verzögerung ist die einfachste Naht, um ein Beenden „während“ eines Laufs ohne Zeitglück zu erzeugen.
- **Bezug:** K 2, T 20, E-034, `betrieb.md` 5.

## E-137 Netzbeschränkung auf das Heimnetz

- **Frage:** K 2: „Erreichbarkeit nur im Heimnetz“. Ist das allein Sache der Netzkonfiguration?
- **Entscheidung:** Zusätzlich in der App: `erlaubte_netze` (CIDR-Liste), Vorgabe None (keine Beschränkung, frühere Tests unverändert); die ausgelieferte Umgebungsdatei setzt Loopback und die privaten Bereiche (RFC 1918, ULA, Link-local). Andere Client-Adressen → 403 `netz_nicht_erlaubt` als erste Prüfung. Weitergeleitete Köpfe werden nicht ausgewertet (uvicorn ohne Proxy-Köpfe).
- **Begründung:** Eine versehentliche Portweiterleitung am Router machte die App sonst sofort aus dem Internet erreichbar; die Beschränkung kostet nichts und ist im `TestClient` über die Client-Adresse prüfbar. Ohne Auswertung von `X-Forwarded-For` lässt sie sich nicht durch einen gefälschten Kopf umgehen.
- **Bezug:** K 2, T 18, `sicherheit.md` 10.

## E-138 Test-Benachrichtigung in den Vertrag aufgenommen (W-005)

- **Frage:** Der Implementierungs-Thread meldete (W-005): Für den Knopf „Test-Benachrichtigung senden“ (Einstellungen → ntfy-Ziel) hat die Anwendung einen nicht spezifizierten Endpunkt `POST /api/benachrichtigungen/test` eingeführt; er löst über das konfigurierte Benachrichtigungs-Plugin eine Test-Zustellung aus, ist bei eingeschalteter Anmeldung geschützt, und im Mock-Modus wird die Nachricht nur bestätigt und erscheint nicht unter `GET /api/mock/zustellungen`. Gehört er in den Vertrag, und mit welchem Antwortschema, welchen Fehlerfällen und welcher Wirkung auf Benachrichtigungsliste, Zustellstatus, Protokoll und Sicherung?
- **Entscheidung:** Aufgenommen als `POST /api/benachrichtigungen/test` (`benachrichtigungen.md` 8, `openapi.yaml` 2.8.0, Schema `TestBenachrichtigung {plugin, zugestellt, gesendet, fehler}`). Ohne Körper. Plugin `keins` → 409 `kein_benachrichtigungs_plugin`; `mock` → 200 mit `zugestellt = true`, `gesendet = false`, ohne Aufruf von `senden`; `ntfy` → genau eine Veröffentlichung (Titel `Kontor: Test-Benachrichtigung`, im Mock-Modus mit `[Mock] `, Priorität 3, Tag `test`, `click` nur mit `oeffentliche_url` auf `/einstellungen`), Fehlschlag als 200 mit `zugestellt = false` und `fehler {code: benachrichtigung_fehler, meldung, status}`, ohne Wiederholung. Keine Benachrichtigung, kein Eintrag im Zustellstatus oder in `/api/mock/zustellungen`, keine Änderung im Protokoll, nicht in der Sicherung. Tests in `tests/app/m8/test_m8_testbenachrichtigung.py` (Marker `m8`, ohne Browser).
- **Begründung:** Der Knopf ist Teil der vollständigen Oberfläche (M8) und nur über REST bedienbar; ein ungeprüfter Endpunkt widerspräche T 1 („einzige gemeinsame Grundlage“). Das Verhalten des Implementierungs-Threads im Mock-Modus wird übernommen: `/api/mock/zustellungen` spiegelt nach 4.3 genau die Zustellungen der Benachrichtigungsliste (eine je Benachrichtigung, T 17), und `PushNachricht.benachrichtigung_id` verweist auf eine Benachrichtigung; eine Test-Nachricht dort würde die M6-Prüfungen „genau eine Nachricht je Auslöser“ verfälschen. Mit dem Feld `gesendet` sieht die Oberfläche trotzdem, dass im Mock-Modus nichts übertragen wurde. Den Fehlschlag als 200 zu melden trennt „Anfrage ungültig“ (4xx) von „ntfy-Server hat abgelehnt“ und hält 5xx für echte Fehler frei; der Statuscode der Attrappe ist so in der Oberfläche anzeigbar. Keine Wiederholung und keine Spuren in Zustellstatus und Protokoll, weil der Test eine Momentaufnahme des Zustellwegs ist und kein fachliches Ereignis. Marker `m8`, weil der Endpunkt mit der Oberfläche entsteht (E-029: frühere Tests unverändert).
- **Bezug:** K 3 (ntfy), K 5, T 17, E-029, E-119, `benachrichtigungen.md` 2–4, 8.

## E-139 Oberflächen-Vertrag über `data-testid`, ARIA und Zustandsattribute; Browsertests mit Playwright

- **Frage:** Wie wird eine Oberfläche so festgelegt, dass ein anderer Agent sie ohne Rückfragen baut und Playwright-Tests stabil bleiben, ohne Aussehen und Aufbau vorzuschreiben (T 19, `meilensteine.md` M8)?
- **Entscheidung:** `spec/api/oberflaeche.md` legt nur bedienbare Merkmale fest: Routen, `data-testid`-Werte (kebab-case, `<id>` = REST-ID), ARIA-Rollen und -Zustände, maschinenlesbare Attribute (`data-betrag` in Cent, `data-datum` ISO, `data-status`, `data-anzahl`), Bereitschaftsattribute (`data-bereit`, `data-geladen`, `data-layout`), Tastaturkürzel, Gesten und die REST-Aufrufe jeder Aktion. Tests: `tests/app/m8/` mit Marker `m8` (automatisch), Browsertests zusätzlich `browser`; Playwright für Python mit Chromium headless, Server über `create_app` mit uvicorn im Testprozess auf `127.0.0.1`, eigene temporäre Datenbank, Mock-Modus mit fester Uhr; Desktop 1280 × 800 und Handy 390 × 844 (Touch). Wirkungen werden zusätzlich über REST geprüft. Startet kein Browser oder fehlt Playwright, werden die Browsertests mit klarer Meldung übersprungen (nicht fehlgeschlagen), anders als fehlende Anwendung (E-024), weil der Browser eine Eigenschaft der Testumgebung ist und nicht der Anwendung. In jedem Browsertest scheitern unbehandelte Skriptfehler, CSP-Verletzungen und Anfragen an fremde Herkünfte.
- **Begründung:** Testkennungen und Rollen sind gegenüber Gestaltungsänderungen stabil; Rollen prüfen zugleich die Barrierefreiheit. Zustandsattribute ersetzen feste Wartezeiten. Cent-Werte in Attributen vermeiden Abhängigkeiten von Schriftsatz und Rundung; das Textformat wird zusätzlich an Stichproben geprüft. Ein Server im Prozess ist schnell, braucht keinen zweiten Prozess je Test und erlaubt die Prüfung über REST mit derselben App.
- **Bezug:** K 5, K 14, T 2 (End-to-End mit Playwright), T 19, `meilensteine.md` M8.

## E-140 Routen als Pfade, Filter in der URL mit REST-Parameternamen

- **Frage:** Hash-Routen oder Pfade? Wie werden Filter und Sortierung der Kontoansicht adressierbar?
- **Entscheidung:** Pfade nach `oberflaeche.md` 3 mit History API; der Server liefert für jede Route dieselbe Hülle (`sicherheit.md` 7.2 erlaubt das bereits). Filter und Sortierung stehen in der Abfrage der URL mit genau den Parameternamen von `GET /api/buchungen`; die Liste zeigt genau die Antwort dieses Aufrufs (Reihenfolge eingeschlossen, 200 je Seite, „Weitere laden“).
- **Begründung:** Die Links der Benachrichtigungen (`/tan/<id>`, `/mail/postfaecher/<id>`, M6) sind schon Pfade. Gleiche Parameternamen machen die Abbildung trivial und für Tests nachprüfbar (Liste = REST-Antwort), Lesezeichen und Neuladen behalten den Filter.
- **Bezug:** K 5 (Filter, ohne Seitenneuladen), K 6, `benachrichtigungen.md` 5, 6.

## E-141 Layout und Design im Speicher des Browsers

- **Frage:** K 5: „das Layout wird gespeichert“ – auf dem Server oder im Browser? Braucht es einen Endpunkt?
- **Entscheidung:** Im `localStorage` des Browsers (`kontor.layout` mit festem JSON-Format, `kontor.thema`), kein neuer Endpunkt, nicht Teil von Protokoll oder Sicherung. `layout-zuruecksetzen` stellt die Vorgaben her. Panels: `kategorien` und `details` in der Kontoansicht, zwei Andockbereiche, Breite 160–600 px.
- **Begründung:** Das Layout hängt vom Gerät ab (Laptop, großer Bildschirm, Handy); ein gemeinsamer Stand je Haushalt wäre auf jedem anderen Gerät falsch. Es ist kein fachlicher Zustand (CLAUDE.md, M9). Ohne Endpunkt bleibt der Vertrag unverändert (Auftrag: neue Endpunkte nur, wenn unvermeidbar).
- **Bezug:** K 5, `sicherung.md` 2.3, E-085.

## E-142 Undo per Strg+Z über das Änderungsprotokoll

- **Frage:** Wie wird „Undo per Strg+Z“ (K 5) mit dem Änderungsprotokoll (K 14, M3) verbunden, ohne neue Endpunkte, und was gilt bei mehreren Anfragen je Aktion?
- **Entscheidung:** Rückgängig der Oberfläche ist Rückgängig im Protokoll. Je Tab ein Rückgängig- und ein Wiederholen-Stapel im Arbeitsspeicher; ein Eintrag sind die IDs der Änderungen, die eine Aktion erzeugt hat (vorher höchste ID merken, danach neue Änderungen ohne Gruppe `sync:` übernehmen). Eine ID → `POST /api/aenderungen/{id}/rueckgaengig`, mehrere → `POST /api/aenderungen/rueckgaengig`; Wiederholen = Rückgängig der Rückgängig-Änderung (`protokoll.md` 6.3). Konflikte melden und den Eintrag verwerfen. Strg+Z in Texteingaben bleibt Text-Undo. Zusätzlich Knöpfe im Kopf und in der Erfolgsmeldung (für das Handy).
- **Begründung:** Ein eigener Undo-Speicher der Oberfläche könnte vom Protokoll abweichen und würde Änderungen anderer Geräte überschreiben; das Protokoll prüft Konflikte (6.1 Schritt 3) bereits. Die Ermittlung über „höchste ID davor“ braucht keinen neuen Kopf in Antworten; Änderungen des Planers tragen eine Gruppe `sync:…` und werden ausgeschlossen. Ein gleichzeitig arbeitendes zweites Gerät könnte eine Änderung dazwischen schieben; im Haushalt mit einem Konto ist das selten und wird dann vom Protokoll als eigene Änderung mit zurückgenommen (bewusst in Kauf genommen).
- **Bezug:** K 5, K 14, T 3.6, `protokoll.md` 6.

## E-143 „Als Dublette markieren“ für vorhandene Verdachte

- **Frage:** K 5 nennt im Kontextmenü „als Dublette markieren“; die REST-Schnittstelle kennt nur das Auflösen vorhandener Dublettenverdachte (`POST /api/dubletten/{id}/aufloesen`), keinen manuell angelegten Verdacht.
- **Entscheidung:** Der Eintrag ist für eine Buchung aktiv, die in einem offenen Verdacht vorkommt, und öffnet den Dubletten-Dialog (zusammenführen mit einem Kandidaten oder „keine Dublette“). Für andere Buchungen ist er deaktiviert; eine echte Doppelbuchung ohne Verdacht wird gelöscht (Rückgängig über das Protokoll möglich). Kein neuer Endpunkt.
- **Begründung:** Ein manueller Verdacht wäre neuer fachlicher Zustand (Protokoll, Sicherung, Invarianten) ohne Mehrwert gegenüber Zusammenführen bzw. Löschen; die Dublettenerkennung bei Import und Abruf legt Verdachte bereits an (T 6). Der Auftrag lässt neue Endpunkte nur zu, wenn unvermeidbar.
- **Bezug:** K 5, K 12, T 6, `datenmodell.md` 10.5.

## E-144 „Kategorien im Baum umsortieren“ heißt Elternkategorie ändern

- **Frage:** Kategorien haben kein Sortierfeld. Was bedeutet Umsortieren per Drag and Drop?
- **Entscheidung:** Ablegen auf eine Kategorie derselben Klasse macht sie zur Unterkategorie, Ablegen auf die Gruppenüberschrift macht sie zur Wurzelkategorie (`PATCH /api/konten/{id}` mit `eltern_id`). Geschwister stehen immer nach Name (`localeCompare` deutsch). Ungültige Ziele (eigener Nachfahre, andere Klasse) ändern nichts.
- **Begründung:** Ein Sortierfeld wäre eine Schemaänderung an `Konto` mit Folgen für Import, Protokoll und Sicherung, ohne fachliche Wirkung; die Hierarchie ist das, was Berichte und Filter (`unterkategorien`) auswerten. Die Regeln für `eltern_id` (gleiche Klasse, keine Zyklen) gelten unverändert.
- **Bezug:** K 5, `datenmodell.md` 2.

## E-145 Gesten auf dem Handy

- **Frage:** K 5: „lange Berührung und Wischgesten ersetzen Rechtsklick und Drag and Drop“ – welche Geste wofür, mit welchen Schwellen?
- **Entscheidung:** Lange Berührung (≥ 500 ms, ≤ 10 px Bewegung) = Kontextmenü; Wischen nach rechts (≥ 80 px, ≤ 40 px senkrecht, ≤ 1 s) = Auswahl umschalten (Mehrfachauswahl); Wischen nach links = Kategorie-Auswahl (ersetzt Ziehen auf eine Kategorie); Umsortieren von Kategorien über „Verschieben nach…“ im Menü der langen Berührung. Die Oberfläche erkennt Gesten selbst (Chromium löst bei langer Berührung kein `contextmenu` aus, getestet). Tests erzeugen echte Touch-Ereignisse über CDP.
- **Begründung:** Die Schwellen entsprechen gängigen Plattformwerten (lange Berührung um 500 ms, Wischen deutlich länger als ein Zittern) und lassen senkrechtes Scrollen zu. Eine Geste je Aufgabe statt Mehrdeutigkeiten macht die Bedienung vorhersehbar und testbar.
- **Bezug:** K 5, K 14, T 19.

## E-146 PWA: Manifest öffentlich, Service Worker unter `/sw.js`, offline nur die Hülle

- **Frage:** Wo liegen Manifest und Service Worker (Anmeldung, Bereich), und was darf offline gespeichert werden?
- **Entscheidung:** Manifest unter `/oeffentlich/manifest.webmanifest` (öffentlich, schon in `sicherheit.md` 3.1 vorgesehen), Service Worker unter `/sw.js` (geschützt wie jede andere Seite, Bereich `/` ohne Sonderkopf). Offline nur die Hülle und statische Dateien (Caches `kontor-…`), nie Antworten unter `/api/`, kein Buchbestand in `localStorage`, `sessionStorage` oder IndexedDB; ohne Netz ein Hinweis statt veralteter Daten. Installierbarkeit wird über Chromiums `Page.getInstallabilityErrors` geprüft.
- **Begründung:** Ein Service Worker unter `/oeffentlich/` bräuchte für den Bereich `/` den Kopf `Service-Worker-Allowed`; unter `/sw.js` ist er einfacher und wird ohnehin erst nach der Anmeldung registriert. Finanzdaten auf einem verlorenen Handy wären ein Risiko; die App ist im Heimnetz und offline ohnehin ohne Synchronisation nutzlos.
- **Bezug:** K 2, K 5, `sicherheit.md` 3, 6.

## E-147 TAN-Seite: Speichern als Download, Teilen über Web Share API

- **Frage:** Wie werden „QR-Code speichern“ und „Teilen“ (K 6, nur am Handy) umgesetzt und geprüft?
- **Entscheidung:** „Speichern“ lädt genau die Bildbytes als `kontor-tan-<id>.<endung>` herunter; „Teilen“ nutzt `navigator.share` mit einer Datei und ist nur sichtbar, wenn `navigator.canShare({files})` wahr ist. Beide Knöpfe gibt es in beiden Layouts. Die Tests prüfen den Download (Bytes = REST-Bild) und das Teilen mit einer im Test eingesetzten `navigator.share`-Attrappe; ohne Unterstützung muss der Knopf verborgen sein.
- **Begründung:** Download und Web Share sind die einzigen Wege, ein Bild aus dem Browser an eine Banking-App zu geben; Android-Chrome und iOS-Safari unterstützen das Teilen von Dateien. Headless-Chromium unterstützt es nicht, deshalb die Attrappe.
- **Bezug:** K 6, T 19.

## E-148 Vollständige Navigation mit Mindestumfang weiterer Seiten

- **Frage:** Der Plan nennt für M8 Finanzübersicht, Kontoansicht, Filter, Mehrfachbearbeitung, Split, Kreditabgleich und TAN-Seite; eine „vollständige Oberfläche“ braucht aber auch Seiten für Import, Berichte, Regeln, Empfänger, Protokoll usw. Wie genau werden diese festgelegt?
- **Entscheidung:** Die Navigation umfasst die acht Einträge aus K 5 und zusätzlich Protokoll, Empfänger, Regeln, Split-Vorlagen, Dubletten und Synchronisation. Die Seiten des Plans sind genau festgelegt und tief getestet; die übrigen haben einen Mindestumfang (`oberflaeche.md` 13.10: Liste je Objekt mit Kennung, Hauptaktionen) und werden auf Erreichbarkeit, Inhalt = REST-Liste und je eine Hauptaktion geprüft.
- **Begründung:** So ist jede REST-Funktion aus der Oberfläche erreichbar, ohne dass der Vertrag jedes Formular vorschreibt; Tiefe dort, wo der Plan und T 19 sie verlangen.
- **Bezug:** K 5, K 14, T 19, `meilensteine.md` M8.

## E-149 Selbstprüfung der Oberfläche mit einer kleinen Wegwerf-Seite

- **Frage:** Wie lassen sich Oberflächentests ohne Anwendung gegen eine Referenz prüfen, ohne eine zweite Oberfläche zu bauen?
- **Entscheidung:** Die Wegwerf-Referenz liefert eine kleine Seite (`referenz/kontor/oberflaeche/`, ein Skript ohne Framework) für die Kernfunktionen Kontoansicht mit Liste, Mehrfachauswahl (Klick, Strg, Umschalt, Tastatur), Kontextmenü mit Kategorie-Auswahl, Mehrfachbearbeitung, Befehlspalette, Mock-Hinweis und mobiles Menü. Nur die Tests dieser Funktionen tragen `kern`; Mutanten prüfen typische Fehler (Strg ersetzt statt umzuschalten, Umschalt ohne Anker, Rechtsklick ohne Auswahlwechsel, Palette ohne Umlautfaltung, Mehrfach nur mit erster Buchung, Mock-Hinweis mobil verborgen). Die übrigen Browsertests laufen nur gegen die Anwendung.
- **Begründung:** Eine vollständige Referenzoberfläche wäre fast so groß wie die Anwendung selbst; die gewählten Funktionen enthalten die meiste Logik (Auswahlregeln, Menü, Treffer der Palette), deren Fehler in Tests leicht übersehen werden. Die übrigen Tests prüfen meist eine Abbildung auf REST, die ihr REST-Gegenstück schon abdeckt.
- **Bezug:** CLAUDE.md (Selbstprüfung), T 2 (Mutationstests).

## E-150 Abschluss des Meilensteinplans mit M8; Vertragsprüfungen und offene Konzeptteile

- **Frage:** Was ändert M8 an bestehenden Prüfungen, und welche Teile des Konzepts sind nach dem letzten Meilenstein des Plans noch offen?
- **Entscheidung:** (1) `openapi.yaml` 2.8.0: Wie in E-109, E-118 und E-127 prüft `test_m7_schemas` die Version nur noch als „mindestens 2.7.0“; die exakte Prüfung steht in `test_m8_schemas`, die Liste aller Operationen in `test_openapi.py` erhält `OPERATIONEN_M8` mit genau `POST /api/benachrichtigungen/test`. (2) `python-api.md` 15 bindet die Oberfläche an die App-Fabrik (Hülle, statische Dateien, `/sw.js`, Betrieb unter uvicorn im Testprozess). (3) Generator 8.0.0 mit `fixtures/m8/`. (4) M8 ist der letzte Meilenstein des Plans. Nicht Teil des Plans und damit offen bleiben: K 1 und K 13 Mail-Abgleich von Sammelbuchungen (spätere Ausbaustufe), K 4 Belege (Datenmodell vorbereitet, Felder leer) samt „Belege auf Buchungen ziehen“ (K 5 „später“), K 3 PostgreSQL („später optional“), K 11 weitere Berichte („schrittweiser Ausbau nach Bedarf“), K 15 (Amazon/PayPal, Wertpapierdepot) und K 16 (bewusst nicht enthalten). Aus T 2 liegen Zeilen-/Zweigabdeckung und Mutationswert (mutmut) der Anwendung bei kontor-app; dieses Repository prüft die Wirksamkeit der Tests mit der eigenen Selbstprüfung.
- **Begründung:** Die Lockerung hält ältere Spezifikationstests gültig, ohne die exakte Prüfung zu verlieren (Muster seit M5). Eine ausdrückliche Liste der offenen Punkte verhindert, dass ein späterer Thread annimmt, der Plan decke das ganze Konzept ab.
- **Bezug:** K 1, K 3, K 4, K 5, K 11, K 13, K 15, K 16, T 2, E-029, E-109, E-127, `meilensteine.md`.

## E-151 Kategorie setzen auf nicht kategorisierbare Buchungen in der Oberfläche (W-007)

- **Frage:** Zwei M8-Tests zogen bzw. wischten die dritte Zeile der Girokonto-Liste („Sparrate“, eine Umbuchung zwischen Bestandskonten) auf eine Kategorie und erwarteten, dass die Kategorie gesetzt wird. Das widerspricht `datenmodell.md` 3.2 und E-007 (422 `nicht_kategorisierbar`). Wie verhält sich die Oberfläche, und wie wählen Tests ihre Zeilen?
- **Entscheidung:** (1) Die Spezifikation gilt, die Tests waren falsch. Oberflächentests wählen Buchungen für „Kategorie setzen“ (Drag and Drop, Wischen, Kategorie-Auswahl, Inline-Editor, Kontextmenü) nach der bekannten Wahrheit des Generators aus (`tests/hilfen/m8.kategorisierbare`: genau ein Gegensplit, Kategorie ungleich dem Ziel; für Umschalt-Bereiche lückenlos benachbart), nicht nach Listenposition. (2) `km-kategorie` und `mehrfach-kategorie` sind auch bei nicht kategorisierbaren Buchungen aktiv (8.2 „immer“); die Oberfläche sendet die Anfrage und zeigt die Ablehnung als Fehlermeldung mit der `meldung` des Servers (1 Nr. 8, 4.3), die Zeile zeigt weiter „Umbuchung“ bzw. „Gesplittet“ ohne `data-kategorie-id`. (3) Beim Ziehen bzw. Wischen einer nicht kategorisierbaren Buchung darf die Oberfläche die Ablage bereits ablehnen (Ziel zeigt „nicht annehmbar“, keine Anfrage) oder die Anfrage senden und den Fehler melden; in beiden Fällen ändert sich nichts und es entsteht kein Protokolleintrag. `oberflaeche.md` 10 nennt das ausdrücklich.
- **Begründung:** Die Ablehnung ist Sache des Servers (eine Regel, ein Ort); die Kategorie-Auswahl selbst bleibt einfach. Beim Ziehen ist eine frühe Ablehnung gute Bedienung, also kein Grund, sie zu verbieten. Auswahl über die Wahrheit statt über Positionen macht die Tests unabhängig von Gleichständen in der Sortierung und von späteren Änderungen des Datensatzes.
- **Bezug:** K 5, `datenmodell.md` 3.2, `oberflaeche.md` 1 Nr. 8, 4.3, 7.5, 8.2, 10, 16.4, E-007, E-144, E-145.

## E-152 AqBanking-Plugin als zweites echtes Bank-Plugin (Meilenstein 10)

- **Frage:** Der Anwender hat AqBanking bereits eingerichtet und möchte die Bankanbindung zuerst darüber; python-fints kommt eventuell später dazu (Auftrag vom 2026-11-09). Wie passt das zu K 6 („python-fints statt aqbanking-cli“) und zu E-113?
- **Entscheidung:** Neuer Meilenstein M10 mit dem Bank-Plugin `aqbanking` (`spec/api/aqbanking.md`), das die Programme von AqBanking 6 mit einer vorhandenen AqBanking-Konfiguration aufruft. `fints.md` und E-113 bleiben unverändert gültig; beide Plugins sind über `bank_plugin` wählbar, die Vorgabe im Echtmodus bleibt `fints`. M10 hängt nur von M2 ab und wird vor M6 umgesetzt. K 6 erhält dazu einen Satz.
- **Begründung:** Das Bank-Plugin war von Anfang an austauschbar (K 3). Eine beim Anwender funktionierende Einrichtung (Bankzugang, akzeptiertes Zertifikat, registrierte Produkt-ID von AqBanking) wiegt schwerer als die Vorteile von python-fints beim TAN-Ablauf, solange die Bank für reine Kontoabrufe selten eine TAN verlangt. Erprobt am 2026-11-09: `aqbanking-tools` 6.5.4 ist unter Ubuntu 24.04 installierbar und arbeitet gegen die FinTS-Attrappe (nach E-157).
- **Bezug:** K 3, K 6, T 7, T 21, E-017, E-113.

## E-153 Abbildung wie das FinTS-Plugin im Format MT940; Konten aus der lokalen Konfiguration

- **Frage:** Welche Daten liefert AqBanking, und wie werden Konten und Umsätze abgebildet, damit Kennungen stabil sind?
- **Entscheidung:** `konten()` liest die Konten aus der lokalen AqBanking-Konfiguration (`listaccs`, keine Bankverbindung, keine PIN); Kontoart nach dem AqBanking-Kontotyp (`aqbanking.md` 4.1), Währung immer `EUR`. Umsätze: nur gebuchte (`type = statement`), Verwendungszweck ohne Zeilenumbrüche, Name unverändert, `storno = false`, `vormerkung = false`; `umsatz_id` ist die Hash-Kennung aus `fints.md` 3.4 über diese Felder.
- **Begründung:** Erprobt mit AqBanking 6.5.4 gegen die Attrappe (Profil `mt940`): Für alle 91 Umsätze des Girokontos stimmen Buchungstag, Valuta, Betrag, Name, Gegen-IBAN und Verwendungszweck nach dieser Abbildung mit der MT940-Abbildung aus `fints.md` 3.4 überein (AqBanking trennt `?20`–`?29` durch Zeilenumbrüche und verbindet `?32`/`?33`). Dieselbe Hash-Kennung macht einen späteren Wechsel zum FinTS-Plugin (MT940) dublettenfrei außer bei Stornos. AqBanking speichert weder die Kontowährung noch den zweiten Inhaber noch ein Storno-Kennzeichen (RC/RD erscheinen nur mit richtigem Vorzeichen); das Profil `camt` (camt.052.001.08) verarbeitet AqBanking 6.5 nicht (es kennt camt.052.001.02 und nur mit dem Kontomerkmal `preferCamtDownload`). Konten aus der lokalen Konfiguration zu lesen spart eine Bankverbindung je Lauf und entspricht der Einrichtung durch den Betreiber.
- **Bezug:** K 6, K 15, T 6, T 21, `fints.md` 3.4, E-114.

## E-154 `bank_plugin = "aqbanking"` gültig; Anpassung eines M1-Tests

- **Frage:** `tests/app/test_paket.py::test_ungueltige_konfiguration` verwendete ausgerechnet `"aqbanking"` als Beispiel eines ungültigen `bank_plugin`. Bleibt das?
- **Entscheidung:** Nein. `bank_plugin` ∈ {`mock`, `fints`, `aqbanking`} (`python-api.md` 16.1); das Beispiel im M1-Test wird durch `"hbci"` ersetzt, die Prüfung selbst (unbekannter Name → `KonfigurationsFehler`) bleibt. `openapi.yaml` 2.9.0: `PluginInfo.name` um `aqbanking` erweitert (rückwärtskompatibel, keine neuen Endpunkte); `test_m8_schemas` prüft die Version nur noch als Untergrenze, `test_m10_schemas` exakt.
- **Begründung:** Echte Änderung des Vertrags durch den Auftrag (E-152); E-029 erlaubt die Anpassung eines früheren Tests bei echtem Grund mit eigenem Eintrag. Der Sinn des M1-Tests bleibt erhalten.
- **Bezug:** K 3, E-029, E-152.

## E-155 TAN im AqBanking-Plugin: eigener Fehler statt TAN-Ablauf

- **Frage:** Wie verhält sich das Plugin, wenn die Bank eine TAN verlangt?
- **Entscheidung:** `BankTanNichtUnterstuetzt` (`BankFehler`, Code `bank_tan_nicht_unterstuetzt`) mit dem Hinweis, die Freigabe einmal direkt in AqBanking zu erteilen; nie `TanErforderlich`. Der Lauf scheitert wie bei jedem Pluginfehler (Benachrichtigung `sync_fehler`), es entsteht keine TAN-Anforderung.
- **Begründung:** `aqbanking-cli` fragt die TAN nur interaktiv am Terminal ab (erprobt: im nicht interaktiven Modus „No TAN input in non-interactive mode“), ein Dialog lässt sich nicht pausieren und das QR-Bild nicht an die App durchreichen. Reine Kontoabrufe brauchen die TAN selten (K 6); die Freigabe gilt dann für alle Abrufe. Ein eigener Code macht die Ursache in Lauf und Benachrichtigung erkennbar. Den vollständigen TAN-Ablauf in Kontor liefert das FinTS-Plugin (M6).
- **Bezug:** K 6, `synchronisation.md` 5–7, `fints.md` 3.5.

## E-156 PIN über eine Pipe, Fehlerzuordnung aus der Ausgabe von AqBanking, Prozessgrenzen

- **Frage:** Wie erhält AqBanking die PIN, ohne sie in Dateien oder Argumente zu schreiben, und woran erkennt das Plugin Erfolg und Fehler?
- **Entscheidung:** PIN-Datei im Format von AqBanking (`PIN_<BLZ>_<Benutzerkennung> = "…"`, je Benutzer aus `listusers`) über einen vererbten Pipe-Deskriptor (`-P /dev/fd/N`); genau ein `request` je `umsaetze`, nicht interaktiv, ohne Wiederholung; Zuordnung der Fehler nach `aqbanking.md` 5.1 aus den Rückmeldungen der Bank und dem Auftragsstatus, Zeitgrenze je Programmaufruf (Vorgabe 120 s). Zwischendateien in einem eigenen temporären Verzeichnis, danach entfernt. Nur die Befehle `listaccs`, `request --transactions`, `listtrans`, `listusers`.
- **Begründung:** Erprobt: `/dev/fd/N` funktioniert mit AqBanking 6.5.4; AqBanking maskiert die PIN in seinen Bankprotokollen. Der Rückgabecode ist bei falscher PIN, abgelehntem Auftrag, HTTP 500, abgelehnter Verbindung und fehlender TAN 0; verlässlich sind die Zeilen `Result: … (NNNN: …)` und der Status von `JobGetTransactions` bei `AQHBCI_LOGLEVEL=info` (Hinweis in `aqbanking.md` 5.2). Nach einer falschen PIN gelingt der nächste Abruf mit richtiger PIN; nach drei falschen sperrt die Attrappe (3938). Eine einzige Verbindung je Abruf schützt vor Kontosperre. Die Zeitgrenze deckt AqBankings eigene, nicht einstellbare Wartezeiten je Nachricht ab.
- **Bezug:** K 6, `synchronisation.md` 12, `geheimnisse.md` 6, T 7.

## E-157 FinTS-Attrappe näher am Protokoll; Tests mit echtem AqBanking

- **Frage:** AqBanking lehnte Antworten der Attrappe ab („bad message reference“, Fehler beim Zerlegen von HIUPD, „No syncresponse found“). Wie wird das Plugin trotzdem ohne Bank getestet?
- **Entscheidung:** Die Attrappe (`tests/hilfen/fints_attrappe.py`) setzt jetzt in HNHBK die Bezugsnachricht, in HISYN, HISPA und HITAN das Bezugssegment und lässt leere Datenelemente am Segmentende weg (python-fints füllte wiederholbare Gruppen in HIUPD bis zur Höchstzahl auf); ihr Verhalten nach `fints.md` 6 bleibt sonst gleich, die Attrappen-Selbsttests (`tests/attrappen`) bleiben grün. Die M10-Tests (`tests/app/m10/`, Marker `m10`) verwenden echtes AqBanking 6 gegen die Attrappe im Profil `mt940` über HTTP auf 127.0.0.1; die Testhilfe `tests/hilfen/aqbanking.py` richtet je Test eine Konfiguration ein (`adduser`, `getsysid`) und zeichnet über Hüllskripte in `aqbanking_programme` Argumente und Umgebung auf. Fehlen `aqbanking-cli` oder `aqhbci-tool4`, werden die Tests mit deutlicher Meldung übersprungen und das in `ERGEBNIS.md` vermerkt. Erwartungswerte kommen aus der bekannten Wahrheit des Generators (`fixtures/m6/`) über `tests/hilfen/m10.py`, nicht aus Ausgaben von AqBanking oder der App.
- **Begründung:** Die Korrekturen machen die Attrappe näher an eine echte Bank (Bezüge sind in FinTS 3.0 vorgesehen und werden von echten Banken gesendet); python-fints kommt mit beiden Formen zurecht. Echtes AqBanking zu verwenden prüft genau das, was beim Anwender läuft; eine nachgebaute Kommandozeile würde nur Annahmen über AqBanking testen. HTTP statt HTTPS vermeidet in Tests die interaktive Zertifikatsbestätigung; die Ablehnung eines nicht vertrauten Zertifikats prüft ein eigener Test.
- **Bezug:** T 7, T 21, E-028, E-122, `fints.md` 6.

## E-158 Vier Wünsche vom 2026-11-09 als Meilenstein 11

- **Frage:** Der Anwender wünscht (1) dieselben Funktionen in der Buchungsliste einer Kategorie wie in der eines Kontos, (2) den Kontostand per Synchronisation mit Ausgleichsbuchung bei Differenz, (3) die Kategorien in der Finanzübersicht als Konten, abgesetzt und einklappbar, (4) das Zusammenfassen mehrerer Empfänger, wobei der neue Empfänger alle Namen als Suchtexte erhält. Wie werden sie bewertet und eingeordnet?
- **Entscheidung:** Alle vier werden übernommen, als neuer Meilenstein M11 mit Tests in `tests/app/m11/` (Marker `m11`). (1) war in `oberflaeche.md` 7.2 nur mit einem Satz geregelt: jetzt vollständig in 22.2 mit Spalte „Konto“, Bestandskonto-Filter und neuem REST-Filter `unterkonten` (E-163). (2) ist neu (`kontostand.md`, E-159 bis E-162). (3) braucht keine REST-Änderung, `GET /api/kontenuebersicht` liefert die Kategorien schon (E-164). (4) gibt es seit M3 (`buchhaltungspflege.md` 2.4); ergänzt werden ein neuer Name beim Zusammenführen und der Ablauf in der Oberfläche (E-165).
- **Begründung:** Alle vier passen zu K 5 (Bedienung wie ein Buchhaltungsprogramm), K 6 und K 14. Ein eigener Meilenstein hält frühere Tests unverändert (E-029) und gibt der Implementierung ein abgeschlossenes Paket. M11 hängt von M2, M3 und M8 ab.
- **Bezug:** K 5, K 6, K 7, K 14, T 6, T 14, T 19; E-029.

## E-159 Saldo als Teil des Umsatzabrufs, nicht als eigener Bankauftrag

- **Frage:** Wie kommt der Kontostand in die App, ohne zusätzliche PIN-Abfragen, TANs oder Dialoge, und ohne frühere Plugin- und Synchronisationstests zu ändern?
- **Entscheidung:** Der Saldo kommt mit dem Umsatzabruf: `umsaetze()` liefert eine `Umsatzliste` (Unterklasse von `list`) mit dem Attribut `saldo: BankSaldo | None`. Keine neue öffentliche Methode. FinTS sendet dafür `HKSAL` im Dialog des Umsatzabrufs (nur wenn BPD und UPD es anbieten), AqBanking hängt `--balance` an den einen `request` an und liest den gebuchten Saldo aus der Ergebnisdatei (nur mit `aqbanking_saldo`, E-166). Das Mock-Plugin liefert einen Saldo nur, wenn die Datendatei den neuen Schlüssel `bank.anfangssalden` hat; die FinTS-Attrappe bietet `HKSAL` nur mit der Steuerung `saldo_anbieten` an.
- **Begründung:** Ein eigener Auftrag hieße einen zweiten Dialog, unter Umständen eine zweite TAN und Änderungen an gezählten PIN-Abfragen und Aufrufen in M6/M10-Tests. Eine neue Methode `saldo()` hätte die Tests aus M1, M6 und M10 verletzt, die die öffentlichen Methoden der Plugins exakt festlegen („nur lesend“, T 7); ein Attribut des Ergebnisses ändert diese Menge nicht, und `Umsatzliste` vergleicht wie eine Liste, sodass alle bisherigen Tests unverändert bleiben (E-029). Banken melden in `HISAL` genau den gebuchten Saldo. `HKSAL` stand schon in der Liste der lesenden Segmente.
- **Bezug:** K 3, K 6, T 7, T 21; `plugins.md` 2, `fints.md` 3, `aqbanking.md` 4.2, 6; E-036, E-037.

## E-160 Saldoabgleich und Ausgleichsbuchung

- **Frage:** Wann und wogegen wird verglichen, und wie sieht die Ausgleichsbuchung aus?
- **Entscheidung:** Direkt nach der Verarbeitung jedes erfolgreich abgerufenen Bankkontos: `differenz = bank_saldo − saldo(k, stichtag)` mit dem Stichtag der Bank, nur Splits auf genau dem zugeordneten Konto, alle Status. Bei Differenz ≠ 0 eine Buchung am Stichtag `[{k, d}, {„Korrekturen“, −d}]`, Verwendungszweck „Saldoausgleich Bank“, Status `importiert`, Kennung `saldo:<iban>:<stichtag>` (bei Wiederholung `:2`, `:3`, …), eigene Änderung `sync_saldoausgleich` in der Lauf-Gruppe, Benachrichtigung `saldo_ausgeglichen` (entprellt). Ergebnis in `SyncKonto.saldo_abgleich`. Abschaltbar über `sync_saldo_angleichen` (Vorgabe an).
- **Begründung:** Der Anwender will, dass der Kontor-Saldo dem der Bank folgt. „Korrekturen“ ist schon das Gegenkonto für Korrekturen (Erfassungshilfe, Kreditabgleich), sodass keine neue Kategorie entsteht und Berichte über Ausgaben und Einnahmen nicht verfälscht werden. Status `importiert` macht die Buchung in der Liste sichtbar und prüfbar, statt sie still als bestätigt zu verbuchen. Der Stichtag der Bank schließt später datierte eigene Buchungen aus; Vormerkungen stehen nie im Buch und nicht im gebuchten Saldo der Bank. Eine eigene Änderung erlaubt, nur den Ausgleich rückgängig zu machen.
- **Bezug:** K 6, K 14, T 6; `synchronisation.md` 4, `buchhaltungspflege.md` 1.4, `protokoll.md` 4.2.

## E-161 Grenzen des automatischen Ausgleichs

- **Frage:** Verdeckt der automatische Ausgleich Fehler (fehlende Historie, eigene Buchungen vor der Bank)?
- **Entscheidung:** Er bleibt automatisch, wie gewünscht, aber jede Ausgleichsbuchung ist sichtbar (`importiert`, Benachrichtigung mit Differenz, Link auf `/sync`) und einzeln löschbar. Es gibt keine Zusammenfassung oder Anpassung früherer Ausgleichsbuchungen; jeder Lauf gleicht seine eigene Differenz aus. Die Grenzen (erster Abruf bucht den fehlenden Anfangsbestand, späterer Import alter Historie zählt doppelt, eigene Buchungen vor der Bank erzeugen Ausgleich und Gegenausgleich) stehen in `kontostand.md` 3.
- **Begründung:** Eine anpassende „laufende“ Ausgleichsbuchung wäre schwer nachvollziehbar und würde gesperrte oder abgestimmte Buchungen ändern müssen. Einzelne Buchungen sind im Protokoll klar und rückgängig machbar.
- **Bezug:** K 14, T 3.5, T 3.6, T 13.

## E-162 Schema und Version für M11

- **Frage:** Wie werden die REST-Erweiterungen von M11 rückwärtskompatibel?
- **Entscheidung:** `openapi.yaml` 2.10.0: `SyncKonto.saldo_abgleich` (optional, Schema `SaldoAbgleich`), Benachrichtigungsart `saldo_ausgeglichen` am Ende der Liste, Abfrageparameter `unterkonten` für Buchungsliste und Exporte, optionales `name` in `EmpfaengerZusammenfuehren`. Die Spezifikationstests von M6 und M10 prüfen Version und Aufzählung nun als Präfix bzw. „mindestens“; exakt prüft `test_m11_schemas` (wie E-078, E-084).
- **Begründung:** E-029, E-124: nur optionale Felder und Parameter, neue Aufzählungswerte am Ende.
- **Bezug:** E-029, E-078, E-124.

## E-163 Buchungsliste einer Kategorie

- **Frage:** Was heißt „gleiche Funktion wie die Buchungsliste der Konten“ für eine Kategorie genau?
- **Entscheidung:** Alle Funktionen der Kontoansicht gelten auch für Kategorien und technische Konten (`oberflaeche.md` 22.2). Zusätzlich eine Spalte `konto` mit dem Bestandskonto der Buchung (genau eins → Pfad, mehrere → „Mehrere“, keins → leer), ein Filter `filter-konto` über die Bestandskonten (REST `kategorie_id`, das jedes Konto akzeptiert), und in jeder Kontoansicht `filter-unterkonten` mit dem neuen REST-Parameter `unterkonten` (`datenmodell.md` 16.1: Treffer und `betrag` über das Konto und alle Unterkonten). Beträge bleiben Rohwerte aus Sicht der Kategorie (Ausgaben positiv).
- **Begründung:** In einer Kategorie ist die interessante Gegenseite das Konto, von dem bezahlt wurde; die Kategorienspalte allein zeigte nur die Kategorie selbst. Ohne `unterkonten` ließe sich eine Oberkategorie wie „Wohnen“ nicht mit ihren Unterkategorien ansehen; `kategorie_id` + `unterkategorien` liefert dafür nicht den vorzeichenrichtigen Betrag aus Sicht der Kategorie. Rohwerte statt Umkehr, weil Summe und Saldo der Liste dann mit `GET /api/kontenuebersicht` übereinstimmen.
- **Bezug:** K 5, K 7, T 19; `datenmodell.md` 2, 3.3, `oberflaeche.md` 7.

## E-164 Kategorien in der Finanzübersicht

- **Frage:** Wie erscheinen Kategorien in der Finanzübersicht?
- **Entscheidung:** Ein eigener Bereich unter den Bestandskonten mit Überschrift „Kategorien“, anfangs eingeklappt, Zustand im Browser gespeichert (wie das Layout, E-141). Gruppen „Ausgaben“, „Einnahmen“ und „Sonstige“ (Eigenkapital, z. B. „Unkategorisiert“), je als Baum mit `saldo_gesamt` über alle Buchungen und Summe je Gruppe; Einnahmen und Sonstige mit umgekehrtem Vorzeichen angezeigt (`data-betrag` bleibt der Rohwert). Kein Zeitraum.
- **Begründung:** „Als Konten aufgelistet“ heißt: wie die Bestandskonten, also Gesamtsaldo. Eingeklappt als Vorgabe, damit die Übersicht über das Vermögen oben unverändert bleibt. Auswertungen nach Zeitraum leisten die Berichte (M5). „Unkategorisiert“ sichtbar zu machen hilft beim Abarbeiten offener Buchungen.
- **Bezug:** K 5, K 11; `oberflaeche.md` 6, 15.3.

## E-165 Empfänger zusammenführen: neuer Name, keine Teilwort-Suchtexte

- **Frage:** Der Wunsch beschreibt das Zusammenführen aus M3 (`buchhaltungspflege.md` 2.4). Was fehlt, und sollen „Suchtexte“ Teilwörter finden?
- **Entscheidung:** Das Zusammenführen mit Übernahme aller Namen als Aliase besteht und wirkt bei Synchronisation und Import (2.3). Neu: optionales `name` (der zusammengeführte Empfänger erhält einen neuen Namen; der alte Name des Ziels wird Alias) und ein festgelegter Ablauf in der Oberfläche (Mehrfachauswahl, Ziel, Name, Vorschau der Aliase, `oberflaeche.md` 22.3). Aliase bleiben exakte Schreibweisen (Vergleich über `ekey`), keine Teilwort-Suche.
- **Begründung:** Bisher musste man für einen neuen Namen zuerst zusammenführen und dann umbenennen (zwei Änderungen, zwei Rückgängig-Schritte). Teilwörter würden falsch zuordnen (`ekey` „rewe“ steckt z. B. in „brewery“), und die Zuordnung von Empfängern ist anders als Regeln nicht prüfbar: Sie legt sonst stillschweigend den falschen Empfänger fest. Für Muster gibt es Regeln (`kategorisierung.md`).
- **Bezug:** K 14, T 14; `buchhaltungspflege.md` 2.3, 2.4, 10.

## E-166 Saldo über AqBanking nur auf Wunsch

- **Frage:** AqBanking lehnt `request --transactions --balance` vollständig ab, wenn die Bank die Saldenabfrage für das Konto nicht anbietet (geprüft mit AqBanking 6.5.4 gegen die FinTS-Attrappe: Rückgabecode 3, „Request "getBalance" … not supported“, keine Umsätze). Ein lokales Erkennungsmerkmal dafür bietet `aqbanking-cli` nicht. Wie wird der Saldo trotzdem abgefragt, ohne das Verhalten aus M10 (genau ein `request`, festgelegte Befehlsmenge) für alle zu ändern?
- **Entscheidung:** Neue Einstellung `aqbanking_saldo` (Vorgabe `false`). Ist sie an, enthält der eine `request` zusätzlich `--balance`; nur bei genau dieser lokalen Ablehnung folgt sofort ein zweiter `request` ohne `--balance`. Der Saldo kommt aus der Ergebnisdatei, die das Plugin ohnehin liest (Typ `booked`), ohne `listbal`. Ohne die Einstellung bleibt das Plugin wie in M10.
- **Begründung:** Die lokale Ablehnung erreicht die Bank nicht; der zweite Aufruf ist deshalb keine Wiederholung eines Bankauftrags (Schutz vor Kontosperre bleibt). Die Vorgabe `false` hält die M10-Tests unverändert (E-029). Der MT940-Schlusssaldo (`noted`) ist kein verlässlicher Kontostand (er gilt für den abgerufenen Zeitraum) und wird nicht verwendet. Hinweis für den Betrieb: Bei AqBanking `KONTOR_AQBANKING_SALDO=1` setzen; fast alle deutschen Banken bieten `HKSAL` an.
- **Bezug:** K 3, K 6, T 7; `aqbanking.md` 4.2, 6; E-152 bis E-157, E-159.

## E-167 Wünsche vom 2026-11-09 (Status, Bearbeitung, Massenänderungen, Filterleiste) als Meilenstein 12

- **Frage:** Der Anwender meldet: (1) Der Status einer Buchung lässt sich nicht ändern. (2) Jeder Bestandteil einer Buchung muss bearbeitbar sein. (3) Wo sinnvoll, sollen Massenänderungen möglich sein. (4) Das Filterpanel im Kontobuch muss einklappbar und standardmäßig eingeklappt sein. Wie werden die Wünsche eingeordnet?
- **Entscheidung:** Alle vier werden übernommen, als Meilenstein M12 mit Tests in `tests/app/m12/` (Marker `m12`). (1) Über REST ließ sich der Status bisher nur entlang der Übergänge aus `datenmodell.md` 3.1 ändern, in der Oberfläche gar nicht (7.6 kannte nur Datum, Verwendungszweck, Kategorie). Neu: freie Statusänderung über einen neuen Endpunkt (E-168) mit Bestätigung beim Verlassen von `abgeglichen` (E-169) und Statusbearbeitung in der Oberfläche (E-171). (2) Über REST waren alle Bestandteile bereits änderbar (`PATCH` für Datum, Empfänger, Verwendungszweck, Tags; `PUT …/splits` für Beträge, Konten, Memos; `PUT …/kategorie`); es fehlte die Oberfläche für Empfänger, Status und Betrag (E-171). (3) Neuer Endpunkt `POST /api/buchungen/mehrfach/aendern` für Status, Datum, Empfänger und Verwendungszweck; Kategorie und Tags gibt es schon (E-170). (4) Die Filterleiste gibt es schon einklappbar (`oberflaeche.md` 7.1); neu ist „anfangs eingeklappt“ auch auf dem Desktop (E-172).
- **Begründung:** K 5 verlangt Bedienung wie in einem Buchhaltungsprogramm mit Inline-Bearbeitung und Mehrfachbearbeitung; K 4 nennt den Status als Teil des Datenmodells. Ein eigener Meilenstein hält frühere Tests unverändert (E-029).
- **Bezug:** K 4, K 5, K 14; T 4, T 13, T 14, T 19; E-029.

## E-168 Freie Statusänderung über einen neuen Endpunkt, `PATCH` unverändert

- **Frage:** Soll der Status manuell in jeden anderen Status gesetzt werden können, und wie verträgt sich das mit den festen Übergängen (`datenmodell.md` 3.1) und den M1-Tests, die unzulässige Übergänge über `PATCH` mit 409 `status_uebergang_unzulaessig` erwarten?
- **Entscheidung:** Ja. `POST /api/buchungen/mehrfach/aendern` (auch für eine einzelne Buchung) setzt jeden Status aus jedem Status, auch `abgeglichen` und rückwärts (`datenmodell.md` 17). `PATCH /api/buchungen/{id}` behält seine Übergangsregeln unverändert; die Oberfläche benutzt für den Status nur den neuen Endpunkt. Automatische Abläufe (Import, Synchronisation, Kredite, Abstimmung) setzen den Status wie bisher.
- **Begründung:** Der Anwender muss Fehler korrigieren können, etwa eine versehentlich bestätigte Buchung zurück auf „importiert“ setzen oder eine Buchung von Hand als abgeglichen markieren; die festen Übergänge beschreiben den Ablauf der Automatik, nicht eine fachliche Grenze. Den Vertrag von `PATCH` zu ändern hieße, M1-Tests umzuschreiben (E-029); ein zusätzlicher Endpunkt ist rückwärtskompatibel. Wie bei `PATCH` bestätigt das Setzen von `bestaetigt` oder `abgeglichen` einen offenen Vorschlag (`kategorisierung.md` 5).
- **Bezug:** K 4, K 5; T 4; `datenmodell.md` 3.1, 17; E-029.

## E-169 Sperre bleibt, Verlassen von `abgeglichen` nur mit Bestätigung

- **Frage:** „Jeder Bestandteil editierbar“ – gilt das auch für gesperrte Buchungen (abgeglichen oder abgestimmt), die nach T 13 gegen versehentliche Änderung geschützt sind?
- **Entscheidung:** Die Sperre bleibt, wird aber aufhebbar: Den Status einer abgeglichenen Buchung zu ändern verlangt `entsperren: true`, sonst 409 `bestaetigung_erforderlich` (`details.buchung_ids`); danach ist die Buchung (sofern nicht abgestimmt) frei bearbeitbar. Datum, Empfänger und Verwendungszweck einer gesperrten Buchung bleiben auch im neuen Endpunkt mit 409 `buchung_gesperrt` geschützt (maßgeblich ist der Zustand vor der Änderung, nur tatsächliche Änderungen zählen, E-026). Eine abgestimmte Buchung wird über das Aufheben der Abstimmung frei (`buchhaltungspflege.md` 5.3); ihr Status ist wie bisher änderbar. Die Oberfläche fragt vor dem Verlassen von `abgeglichen` nach (`oberflaeche.md` 23.2).
- **Begründung:** So bleibt T 13 erfüllt (keine versehentliche Änderung), und trotzdem ist jede Buchung in höchstens zwei bewussten Schritten vollständig bearbeitbar. Der Fehlercode `bestaetigung_erforderlich` besteht schon seit M9 mit derselben Bedeutung. Eine Abstimmung gehört zu einem Kontoauszug; sie still mit zu ändern würde deren Saldo verfälschen.
- **Bezug:** K 4, K 14; T 13; `buchhaltungspflege.md` 1.3, 5.3, 5.4; E-026, E-092.

## E-170 Umfang der Massenänderungen

- **Frage:** Welche Bestandteile lassen sich sinnvoll für mehrere Buchungen auf einmal ändern?
- **Entscheidung:** Status, Datum, Empfänger (auch „ohne“) und Verwendungszweck über `POST /api/buchungen/mehrfach/aendern`, in einer Anfrage beliebig kombiniert; Kategorie und Tags wie bisher (`mehrfach/kategorie`, `mehrfach/tags`). Nicht als Massenänderung: Betrag, Splits und Konto, weil sie je Buchung verschieden sind und die Splitsumme 0 je Buchung erhalten bleiben muss. Die Änderung ist atomar und genau eine Änderung im Protokoll (`mehrfach_aendern`), auch wenn sich nur ein Teil der Buchungen tatsächlich ändert; ändert sich nichts, entsteht keine Änderung (`protokoll.md` 4).
- **Begründung:** Status (z. B. alle Importierten bestätigen), Empfänger (falsch erkannter Name) und Datum (Wertstellung über den Monatswechsel) sind typische Sammelkorrekturen. Konto verschieben deckt das Splitten je Buchung ab; eine Massenänderung müsste dafür Regeln für Buchungen mit mehreren Bestandskonten erfinden.
- **Bezug:** K 5; T 14 („Mehrfachbearbeitung ändert genau die markierten Buchungen“).

## E-171 Inline-Bearbeitung von Empfänger, Status und Betrag

- **Frage:** Wie werden Status, Empfänger und Betrag in der Buchungsliste bearbeitet?
- **Entscheidung:** Die Zellen `empfaenger`, `status` und `betrag` werden wie `datum` per Doppelklick inline bearbeitbar (`oberflaeche.md` 23.2): Empfänger als Auswahl (`PATCH`), Status als Auswahl (neuer Endpunkt, auch bei gesperrten Buchungen), Betrag nur bei genau zwei Splits mit genau einem Split auf dem angezeigten Konto (`PUT …/splits`, Gegensplit mit umgekehrtem Vorzeichen; Konten, Memos und Reihenfolge bleiben). Andere Buchungen bearbeitet der Split-Dialog (9.3), der Konten, Beträge und Memos schon abdeckt. Dazu kommen `mehrfach-status` und `mehrfach-bearbeiten` in der Mehrfach-Leiste sowie `km-status` und `km-mehrfach` im Kontextmenü.
- **Begründung:** Eine einfache Buchung hat genau zwei Splits; ihren Betrag zu ändern heißt beide Seiten zu ändern. Bei mehr Splits ist die Verteilung nicht eindeutig, dort ist der Split-Dialog richtig. Empfänger werden nur aus den vorhandenen ausgewählt; neue legt `/empfaenger` an (keine stillen Neuanlagen durch Tippfehler).
- **Bezug:** K 5; T 19; `oberflaeche.md` 7.6, 9.3.

## E-172 Filterleiste anfangs eingeklappt, Zustand nicht gespeichert

- **Frage:** „Standardmäßig eingeklappt“: Wird der zuletzt gewählte Zustand gespeichert? Was gilt, wenn Filter aus der URL kommen?
- **Entscheidung:** Jede Kontoansicht (Aufruf, Navigation, Neuladen) beginnt mit eingeklappter Filterleiste, auf Desktop wie mobil, auch wenn die URL Filter enthält. Der Zustand wird nicht gespeichert. Eingeklappt zeigt `filter-anzahl` (am Umschalter, sichtbar) die Zahl der gesetzten Filter, damit eine gefilterte Liste nicht unbemerkt bleibt; Filterwechsel klappen die Leiste nicht ein. Ersetzt in `oberflaeche.md` 7.1 „Desktop: anfangs eingeblendet“.
- **Begründung:** Der Wunsch lautet „standardmäßig“; ein gespeicherter Zustand würde nach einmaligem Aufklappen dauerhaft vom Standard abweichen. Die Zahl am Umschalter ersetzt die Sichtbarkeit der Felder. Die M8-Tests klappen die Leiste bei Bedarf auf und bleiben unverändert gültig.
- **Bezug:** K 5; T 19; `oberflaeche.md` 7.1, 15.3; E-029, E-164.

## E-173 Schema und Version für M12

- **Frage:** Wie wird die REST-Erweiterung von M12 rückwärtskompatibel?
- **Entscheidung:** `openapi.yaml` 2.11.0: neuer Pfad `POST /api/buchungen/mehrfach/aendern` mit Schema `MehrfachAenderung`, Antwort `MehrfachErgebnis` (unverändert). Keine Änderung bestehender Schemas. Die exakte Versionsprüfung wandert von `test_m11_schemas` nach `test_m12_schemas`; `test_m11_schemas` prüft die Version als Untergrenze (wie E-162).
- **Begründung:** E-029, E-124: nur Ergänzungen.
- **Bezug:** E-029, E-162.

## E-174 Frühere Oberflächentests klappen die Filterleiste auf (ergänzt E-172)

- **Frage:** Einzelne Tests aus M8 und M11 bedienen Filterfelder direkt nach dem Öffnen der Kontoansicht auf dem Desktop, wo die Filterleiste bisher anfangs eingeblendet war. Mit E-172 ist sie eingeklappt; Playwright kann ausgeblendete Felder nicht bedienen. E-172 nahm an, die früheren Tests blieben unverändert gültig – das trifft auf diese Stellen nicht zu.
- **Entscheidung:** Diese Stellen rufen vor der Bedienung die neue Testhilfe `m8.filter_aufklappen` auf (klappt nur auf, wenn eingeklappt): `test_m8_kontoansicht.py` (`test_filter_aus_der_url_und_status`, `test_ungueltige_betragseingabe`) und `test_m11_oberflaeche.py` (`test_kategorie_buchungsliste`, `test_bestandskonto_klasse_und_unterkonten`). Erwartungen ändern sich nicht. Der Anfangszustand selbst wird in `tests/app/m12/` geprüft.
- **Begründung:** Die Spezifikation ändert sich auf Wunsch des Anwenders (Testkonzept 1: Änderungen an Tests bei Änderung der Spezifikation). Die Hilfe funktioniert vor und nach M12, die Tests bleiben also auch gegen eine Implementierung ohne M12 grün.
- **Bezug:** E-029, E-172; T 19; `oberflaeche.md` 7.1, 23.1.

## E-175 Schnelllauf als Vorgabe, Volllauf mit `--voll`, parallel mit pytest-xdist

- **Frage:** Ein vollständiger Lauf (rund 2 600 Fälle) dauert auf einem Laptop über zehn Minuten. Gemessen gegen die Wegwerf-Referenz entfallen rund 40 % der Zeit auf etwa 25 Hypothesis- und Orakeltests; dazu kommen Leistungstests (50 000 Buchungen), Browsertests und Tests mit großen Fixtures, die bisher in jedem Lauf mitliefen. Wie wird der Alltagslauf schnell, ohne Prüfschärfe aufzugeben?
- **Entscheidung:** `python -m pytest` ist ein **Schnelllauf**: Marker `leistung`, `browser` und `langsam` werden abgewählt (als „deselected“ gemeldet), Hypothesis läuft mit Profil `schnell` (10 Beispiele, deterministisch), sofern `HYPOTHESIS_PROFILE` nicht gesetzt ist. Kein Schnelllauf, sondern der bisherige Lauf ist es, wenn `--voll` oder `KONTOR_TESTS_VOLL=1` gesetzt ist, ein `-m`-Ausdruck angegeben ist oder ein Argument eine Knoten-ID (`::`) enthält. Die Kopfzeile nennt die Laufart und das Hypothesis-Profil. Parallel laufen Tests mit `-n auto` (pytest-xdist, schon in `requirements-tests.txt`); jede App hat ihre eigene Datenbank, Server und Attrappen nutzen freie Ports. `-n` steht nicht in `addopts`, damit Kopfzeile und Selbstprüfung unverändert bleiben.
- **Abnahme:** Ein Meilenstein gilt erst als erfüllt, wenn der **Volllauf** grün ist (`python -m pytest --voll`, gern mit `-n auto`; Leistungstests notfalls getrennt mit `-m leistung` ohne `-n`, weil parallele Last die Zeitgrenzen verfälscht). Die Selbstprüfung ist unverändert (eigener `-m kern`, Profil `standard`).
- **Begründung:** Geprüft wird weiterhin dasselbe; nur die Abstufung fehlte. Gegen die Referenz liefen die 1 228 Kern-Tests ohne Browser/Leistung/langsam mit Profil `schnell` und `-n 2` in 3:53 min grün, mit Profil `standard` nacheinander dauerte derselbe Umfang gut 13 min (nach 9:40 min bei rund 73 % abgebrochen). Bestehende Tests bleiben unverändert (E-029).
- **Offen:** Zusammenlegen sich überschneidender Zufallsfolgen-Tests (Rückgängig in M3 und M4) und weniger REST-Fälle beim Tilgungsplan (M5) sowie feste Wartezeiten (Anmeldebremse M7, Planer M2, Betrieb M7) durch eine einstellbare Uhr zu ersetzen, wären weitere Gewinne; sie ändern Kern-Tests bzw. die Spezifikation und sind einem eigenen Auftrag vorbehalten.
- **Bezug:** T 1, T 2 (eigenschaftsbasierte Tests), E-029, E-041, E-133.

## E-176 Meilenstein-Definition M13 (Versionsnummer, Release, About-Fenster) übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-10 die Meilenstein-Definition M13 freigegeben (bereits als `v0.01` veröffentlicht). Wie wird sie in kontor-tests übernommen, und was davon ist prüfbar?
- **Entscheidung:** Übernahme als Meilenstein M13: `spec/api/version.md` (Abschnitte 1–3 und 5 der Definition), `oberflaeche.md` 24 (Abschnitt 4), `openapi.yaml` 2.12.0 (`GET /api/version`), `python-api.md` 1, `sicherung.md` 3.2 (`app_version`). Tests in `tests/app/m13/` (Marker `m13`). Geprüft wird nur, was über die spezifizierten Schnittstellen beobachtbar ist: das Schema 1.1 und die Gleichheit 1.4 aller Quellen (`kontor.__version__`, `/api/status`, `/api/gesundheit`, `/api/version`, Hülle, Oberfläche, `app_version` einer frischen Sicherung), `GET /api/version` (3) und die Oberfläche (4). Nicht geprüft: die Release-CI (2.1–2.3, laut 2.4 ausdrücklich nicht), das Hochzählen 1.2 und der Startwert 1.3 (eine laufende App kennt nur ihre eigene Version), die Normalisierung im Dateinamen von Wheel und Quellpaket (1.5). Keine Versionsnummer ist in Tests fest eingetragen.
- **Begründung:** Die Version ändert sich mit jedem Release; ein fester Wert würde jeden Release-Commit gegen die Abnahmetests brechen. Die Release-CI läuft in kontor-app ohne Zugang zu kontor-tests (2.4).
- **Bezug:** K 2 (Betrieb), T 1, T 19; `version.md`, `oberflaeche.md` 24; E-029.

## E-177 Regulärer Ausdruck des Versionsschemas; bestehende Schemas unverändert

- **Frage:** 1.1 sagt „`MINOR` besteht aus mindestens zwei Ziffern und wird zweistellig mit führender Null geschrieben (`00` … `99`). Nach `99` zählt Minor ohne Grenze weiter (`0.100`)“. Ist `0.012` oder `0.099` gültig? Und sollen `Status.version`, `Gesundheit.version` und `SicherungManifest.app_version` im Schema ein Muster bekommen?
- **Entscheidung:** `^(0|[1-9][0-9]*)\.([0-9]{2}|[1-9][0-9]{2,})$`: unter 100 genau zwei Ziffern, ab 100 ohne führende Null (`0.012`, `0.099` ungültig, weil 12 bzw. 99 als `0.12` bzw. `0.99` geschrieben werden). Die Prüfung im Test verwendet `fullmatch` (kein Zeilenende, kein Leerraum). Das Muster steht nur im neuen Schema `Versionsangaben`; die bestehenden Schemas behalten `{type: string, minLength: 1}` (nur eine Beschreibung kommt bei `Status.version` hinzu), die Gleichheit prüfen die M13-Tests. `test_version_pep440` (M1) bleibt unverändert; jede Zeichenkette nach 1.1 ist PEP-440-gültig.
- **Begründung:** „Zweistellig mit führender Null“ beschreibt die Schreibweise der Zahlen 0–99; eine Zahl hat nur eine Schreibweise, sonst wären `0.12` und `0.012` verschiedene Versionen derselben Zahl. Ein Muster an bestehenden Schemas würde Tests früherer Meilensteine verschärfen (E-029); die Definition (5) verlangt, dass `GET /api/gesundheit` in Form und Feldern unverändert bleibt.
- **Bezug:** `version.md` 1.1, 1.4, 1.5, 5; `python-api.md` 1; E-029.

## E-178 `GET /api/version`: Schema `Versionsangaben` und Prüfregeln

- **Frage:** Wie genau werden die Felder aus 3.2 geprüft, wo die Definition Spielraum lässt?
- **Entscheidung:** `openapi.yaml` 2.12.0, Pfad `GET /api/version` (Tag `status`, nur `200` außer den allgemeinen Antworten), Schema `Versionsangaben` mit allen elf Feldern als Pflicht und `additionalProperties: false`. Festlegungen: `commit` in Kleinbuchstaben (`^[0-9a-f]{7,40}$`, wie Git ihn ausgibt); `build_datum` `JJJJ-MM-TTTHH:MM:SS` mit optionalen Sekundenbruchteilen und `Z`, gültiges Datum; `entwicklungsstand` ist genau dann false, wenn `commit` und `build_datum` beide gesetzt sind (beide null oder beide gesetzt); `python` = `platform.python_version()` des laufenden Prozesses; `repository` mit `https`, Host und ohne Benutzer-/Passwortteil (keine Geheimnisse); `datenbank` absolut und nach `Path.resolve()` gleich `KontorConfig.aktive_datenbank` (auch bei relativ konfiguriertem Pfad, relativ zum Arbeitsverzeichnis beim Erzeugen der App); `datenbank_schema` und `sicherung_schema` ganze Zahlen ≥ 1 (kein bool), `sicherung_schema` gleich `schemaversion` im Manifest einer gleich danach erzeugten Sicherung; eine Gleichheit von `datenbank_schema` und `sicherung_schema` wird nicht verlangt (`sicherung.md` 3.2 nennt die Version des Schemas in `kontor.sqlite` der Sicherung, das Sache der Implementierung ist). Query-Parameter (auch unbekannte) haben keine Wirkung, also auch kein 422. Andere Methoden (`POST`, `PUT`, `PATCH`, `DELETE`) → 405 `methode_nicht_erlaubt`; bei aktiver Anmeldung ohne Sitzung 401 `nicht_angemeldet` für jede Methode (`sicherheit.md` 3.2). Kein Protokolleintrag, Bestand sowie `anzahl` und `inhalt_sha256` einer Sicherung unverändert. Tests verlangen die Felder als Mindestmenge (E-124); die Exaktheit sichert das Schema.
- **Begründung:** Die Definition legt Typen und Bedeutung fest; die Festlegungen machen sie prüfbar, ohne eine bestimmte Umsetzung vorzuschreiben. Kleinbuchstaben und `Z` sind die übliche Ausgabe von `git rev-parse --short` und `datetime.now(UTC)`. Ein Repository-Link mit Zugangsdaten wäre ein Geheimnis (3.3).
- **Bezug:** `version.md` 3; `sicherheit.md` 3; `sicherung.md` 3.2; E-029, E-124, E-127.

## E-179 About-Fenster: Lage des Knopfes, Laden bei jedem Öffnen, Fokus und Texte

- **Frage:** Wie werden 4.1–4.4 der Definition im Browser geprüft, und wie verhalten sie sich zu den allgemeinen Regeln für Dialoge (`oberflaeche.md` 9)?
- **Entscheidung:** (1) „Als letztes Element der Hauptnavigation“: `version-knopf` liegt in `navigation` und in Dokumentreihenfolge nach allen `nav-`Einträgen; die Liste der `nav-`Einträge (Bezeichner, Reihenfolge) ist genau die aus 3. Desktop „am unteren Rand“: ohne Interaktion sichtbar, unterhalb des letzten Navigationseintrags und innerhalb der Leiste; mobil im geöffneten Menü sichtbar, mindestens 44 px hoch. (2) „In der ausgelieferten Hülle“: Die per `GET` gelieferte Hülle enthält genau ein `<button>` mit `data-testid="version-knopf"` und dem Text `Version <Version>`; die Lage in der Hülle ist frei. (3) Der Dialog lädt `GET /api/version` bei jedem Öffnen (das folgt aus 4.4: ein Fehlschlag verhindert das Öffnen); die Werte im Dialog sind die der Antwort. (4) Fokus beim Öffnen auf `ueber-schliessen` und nach dem Schließen mobil auf `menue-knopf` gehen 9 vor. (5) Texte: `ueber-version`, `ueber-modus` und `ueber-schema` genau (Leerraum zusammengefasst, Mittelpunkt U+00B7); `ueber-python`, `ueber-datenbank` enthalten den Wert; `ueber-build` enthält im Release-Build den Commit (Datumsformat frei), sonst den Text „Entwicklungsstand (nicht über die Release-CI gebaut)“; `ueber-repository` ist `<a>` mit `href` = `repository`, `target="_blank"` und `rel` mit `noopener`. (6) Fehlerfall: kein `ueber-dialog`; Fehlermeldung mit `data-art="fehler"`, bei 4xx mit der `meldung` des Servers; bei 401 Wechsel nach `/anmelden?weiter=<Pfad>` (19).
- **Begründung:** So ist jede Aussage der Definition beobachtbar, ohne Aufbau oder Aussehen festzulegen. Der Fokus auf „Schließen“ ist ausdrücklich verlangt; der mobile Auslöser liegt im geschlossenen Menü und ist dann nicht fokussierbar.
- **Bezug:** `oberflaeche.md` 3, 4.1, 9, 16.2, 19, 24; T 19.

## E-180 Build-Zweige und Fehlerfälle im Browser über abgefangene Antworten

- **Frage:** Ob die App aus einem Release-Build stammt, lässt sich über keine Schnittstelle steuern; wie werden beide Zweige von `ueber-build` und der Fehlerfall 4.4 geprüft?
- **Entscheidung:** Die Browsertests ersetzen die Antwort von `GET /api/version` im Browser (Playwright `route`): einmal mit `commit`/`build_datum` gesetzt und `entwicklungsstand = false`, einmal mit beiden null und `entwicklungsstand = true`, sonst die echte Antwort des Servers (die Versionsnummer bleibt die der App, damit `version-knopf` und Dialog übereinstimmen); für 4.4 mit 404 und 500 (Schema `Fehler`). Der 401-Fall entsteht echt: Anmeldung an, Sitzung über REST beendet. Ein weiterer Test prüft die unveränderte Antwort des Servers gegen den Dialog.
- **Begründung:** Die Oberfläche bedient nur REST (1 Nr. 2); eine im Browser ersetzte Antwort ist für sie von einer echten nicht zu unterscheiden. Ohne das wäre jeweils nur einer der beiden Zweige prüfbar, abhängig davon, wie die getestete App installiert wurde.
- **Bezug:** `oberflaeche.md` 21, 24.2, 24.4; E-139.

## E-181 Meilenstein-Definition M15 (Sammelpaket Bedienung) übernommen; M14 bleibt frei

- **Frage:** Der Auftraggeber hat am 2026-11-10 die Meilenstein-Definition „Sammelpaket Bedienung“ freigegeben (Rückgängig bis zu einer Änderung, mehrere Buchungen in einer Änderung löschen, Buchungen verschieben, Zuordnung unbekannter Bankkonten, gesperrter PIN-Dialog, Vorschläge je Zeile, Berichtsgrafiken). M14 ist an das Feature `update` vergeben, aber in kontor-tests noch nicht übernommen. Wie wird M15 übernommen?
- **Entscheidung:** Übernahme als Meilenstein M15 mit Tests in `tests/app/m15/` (Marker `m15`); die Nummer M14 bleibt für `update` frei (keine Tests, kein Marker). Spezifikation: `protokoll.md` 4.1, 6.2a und 14; `datenmodell.md` 18; `synchronisation.md` 20; `python-api.md` 18; `betrieb.md` 3; `oberflaeche.md` 25 (mit Hinweisen in 7.5 und 13.9); `openapi.yaml` 2.13.0 (E-189). Geprüft werden nach Abschnitt 9 der Definition die REST-Schnittstellen, Protokoll- und Rückgängig-Invarianten, die Konfiguration samt ausgelieferter Umgebungsdatei und die Oberfläche über `data-testid` und Zustandsattribute; nicht geprüft werden Optik, Kreisel, genaue Anzeigezeiten und das Aussehen der Plotly-Diagramme.
- **Begründung:** Eine eigene Nummer hält frühere Tests unverändert (E-029). Wird M14 später übernommen, erhält es die nächste freie Schema-Version; die Reihenfolge der Nummern sagt nichts über die Reihenfolge der Umsetzung (wie M9 vor M5, E-085).
- **Bezug:** K 5, K 6, K 7, K 11, K 14; T 3.5, T 3.6, T 13, T 14, T 19; E-029.

## E-182 Rückgängig bis: Menge, Prüfung über Abzüge, unerreichbare Fehlerfälle

- **Frage:** Wie wird `bis_id` (`protokoll.md` 6.2a) geprüft, und wann treten 409 `bereits_rueckgaengig` und 409 `rueckgaengig_konflikt` auf?
- **Entscheidung:** (1) Die Tests nehmen vor jeder Operation einen Abzug des Buchbestands (Protokollform, `tests/hilfen/m6.bestand`) und vergleichen nach `bis_id = k` mit dem Abzug unmittelbar vor `k`; nach dem Wiederholen mit dem Abzug vor `U`. (2) Die erwartete Menge `rueckgaengig_von` und die Wirksamkeit aller Änderungen berechnet ein eigenes Modell in `tests/hilfen/m15.py` aus den im Test selbst ausgelösten Rückgängig-Operationen (absteigend, Wirksamkeit im Zwischenstand nach 6.5); verglichen wird `rueckgaengig_durch` jeder Änderung. (3) Validierung vor 404: zwei oder drei Felder, kein Feld, `bis_id` als `null`, Zeichenkette, Gleitkommazahl oder Boolean → 422 `validierung`; unbekannte ganze Zahl → 404 `nicht_gefunden`. (4) 409 `bereits_rueckgaengig` und 409 `rueckgaengig_konflikt` sind mit `bis_id` über REST nicht herbeizuführen: Die neueste Änderung ist immer wirksam (nur eine spätere Änderung kann sie zurücknehmen), es gibt also stets etwas zurückzunehmen; und weil alle wirksamen Änderungen `≥ bis_id` in umgekehrter Reihenfolge zurückgenommen werden, ist jeder Zwischenstand exakt der Stand nach der jeweils nächstälteren Operation, sodass weder Zustands- noch Bezugsprüfung scheitern können. Die Regeln bleiben als Absicherung in der Spezifikation; die Tests prüfen stattdessen, dass auch verschachtelte Folgen (Rückgängig, Wiederholen, ein früheres „bis“, dessen Spanne geschnitten wird) gelingen, und dass der Bestand bei jeder Fehlerantwort unverändert bleibt.
- **Begründung:** Abzüge sind unabhängig von der Implementierung und prüfen die Kernaussage „genau so wie unmittelbar vor der Änderung“. Das Modell der Wirksamkeit folgt wörtlich 6.5 und der Definition; Erwartungen werden nie aus Antworten abgeschrieben.
- **Bezug:** `protokoll.md` 6.2, 6.2a, 6.5, 8; T 3.6; Definition M15 Abschnitt 1.

## E-183 Mehrere Buchungen löschen: Vergleich mit einzelnen `DELETE`

- **Frage:** „Wirkung je Buchung wie `DELETE /api/buchungen/{id}`, Nebenwirkungen eingeschlossen“ – wie wird das unabhängig geprüft?
- **Entscheidung:** Zwei Apps werden mit denselben Anfragen gleich aufgebaut (IDs gleich); in der einen löscht `mehrfach/loeschen`, in der anderen löschen einzelne `DELETE`. Der Buchbestand (Protokollform inkl. Dublettenverdachte und Kredite) muss danach gleich sein, ebenso die Nettowirkung (Einträge der einen Änderung `mehrfach_loeschen` = Unterschied der Abzüge). Antwort `MehrfachLoeschErgebnis {geloescht, anzahl}` (`geloescht` = alle genannten IDs aufsteigend). Prüfreihenfolge 422 `validierung` → 422 `referenz_unbekannt` (`details.buchung_ids` aufsteigend) → 409 `buchung_gesperrt` (`details.buchung_ids` aufsteigend, abgeglichen oder abgestimmt). Die Oberfläche sendet bei mehr als einer Buchung genau diese eine Anfrage (ersetzt die Einzelanfragen in `oberflaeche.md` 7.5; der M8-Test dazu prüft nur die Wirkung und bleibt gültig).
- **Begründung:** Der Zwillingsvergleich deckt alle Nebenwirkungen ab, die `DELETE` hat oder später bekommt, ohne sie einzeln aufzuzählen.
- **Bezug:** `datenmodell.md` 18.1; `protokoll.md` 4.1, 14; `buchhaltungspflege.md` 1.3; E-029.

## E-184 Verschieben: Auswahl über eine Gruppe, Fehlerdetails, leere Auswahl

- **Frage:** Die Definition lässt offen, (a) welche Änderungen einer Gruppe „eine Buchung angelegt“ haben, (b) welche Form `details` hat, (c) wie die leere Auswahl antwortet und (d) wie mit dem Quellkonto als Elternkonto umzugehen ist.
- **Entscheidung:** (a) Jede Änderung mit diesem `gruppe`-Wert und einem Eintrag `objekt = "buchung"`, `art = "angelegt"`, gleich ob sie noch wirksam ist; ausgewählt werden die noch vorhandenen dieser Buchungen mit einem Split auf dem Quellkonto. Eine durch Rückgängig wiederhergestellte Buchung trägt dieselbe ID und zählt also mit. (b) Kontofehler mit `details.feld` (`"von_konto_id"`, `"nach_konto_id"`); Buchungsfehler mit `details.buchung_ids` aufsteigend; neuer Fehlercode `verschieben_unmoeglich` (422). (c) 200 `{verschoben: [], anzahl: 0}` ohne Änderung im Protokoll. (d) Nur Splits genau auf `von_konto_id` werden umgehängt; Unterkonten sind nicht betroffen. Antwort `MehrfachVerschiebeErgebnis {verschoben, anzahl}`. Geprüft wird, dass sich je gewählter Buchung genau `konto_id` des Quellsplits ändert (Protokollform sonst identisch, Split-IDs gleich) und alle anderen Buchungen unverändert bleiben.
- **Begründung:** Die Gruppe ist der Schlüssel aus `protokoll.md` 5; „angelegt“ ist dort als Eintragsart definiert. Die Detailform folgt den übrigen Mehrfach-Endpunkten.
- **Bezug:** `datenmodell.md` 18.2; `protokoll.md` 3.2, 5; Definition M15 Abschnitt 3.1.

## E-185 Herkunft: Zeitpunkt und Reihenfolge

- **Frage:** Welcher Zeitpunkt gilt für `GET /api/konten/{id}/herkunft`, und wie werden Gleichstände und null sortiert?
- **Entscheidung:** Import: `importiert_am` des Importvorgangs. Synchronisationslauf: `gestartet_am` oder `beendet_am` des Laufs (beides zulässig; die Tests legen Läufe und Importe mit simulierter Uhr weit genug auseinander, dass die Reihenfolge eindeutig ist). null nur, wenn der Vorgang nicht mehr bekannt ist; null steht zuletzt. Die Tests prüfen `gruppe`, `art`, `anzahl` exakt, `zeitpunkt` gegen Import bzw. Lauf, die Reihenfolge absteigend und `beschreibung` nur als nicht leer. Gruppen ohne noch vorhandene Buchungen auf dem Konto fehlen (auch nach dem Verschieben oder einem Rückgängig des Imports).
- **Begründung:** Die Definition nennt nur „Zeitstempel oder null“ und „Text nicht Teil der Abnahme“; der Lauf hat zwei gleich gute Zeitpunkte.
- **Bezug:** `datenmodell.md` 18.3; `synchronisation.md` 2.1, 8.

## E-186 `sync_konten_anlegen`: Konfiguration, Überspringen, Benachrichtigung

- **Frage:** Wie werden Konfiguration, Lauf und Zuordnung (Definition 4) prüfbar festgelegt?
- **Entscheidung:** `KontorConfig.sync_konten_anlegen: bool = True` (kein `int`, kein `None`), `KONTOR_SYNC_KONTEN_ANLEGEN` wie `KONTOR_MOCK_MODUS`, leer/fehlend → `True`, anderer Wert → `KonfigurationsFehler`. Die ausgelieferte Umgebungsdatei enthält `KONTOR_SYNC_KONTEN_ANLEGEN=0`; `from_env` mit ihren Variablen ergibt `False`. Mit `False` erscheint ein Bankkonto ohne Konto mit seiner IBAN und ohne Eintrag in `/api/sync/konten` in `uebersprungen` als `{iban, name, status: "nicht_zugeordnet", art}`, ohne Konto, Buchungen, Eintrag in `/api/sync/konten` oder Änderung im Protokoll; Benachrichtigung `konto_nicht_zugeordnet` mit Schlüssel `konto_nicht_zugeordnet:<iban>` und Link `/sync`, höchstens eine ungelesene je IBAN (nach dem Lesen entsteht beim nächsten Überspringen wieder eine). Ein `PATCH`/`POST`, nach dem ein Konto die IBAN trägt, liest sie in derselben Anfrage. Der nächste Lauf übernimmt wie ein erster Abruf (Zahl der Buchungen aus der Mock-Datei und dem Orakel `tests/hilfen/sync_orakel.py`). Gelöschte, schon einmal zugeordnete Bankkonten bleiben `konto_fehlt` (`synchronisation.md` 16). `uebersprungen[].art` ist im Schema optional (E-124), in den M15-Tests bei `nicht_zugeordnet` Pflicht.
- **Begründung:** Die Vorgabe `True` lässt alle früheren Tests unverändert (E-029); im Betrieb verhindert `0` stille Neuanlagen. Die Entprellung folgt `synchronisation.md` 6 und 16.5.
- **Bezug:** `synchronisation.md` 3, 16, 20; `python-api.md` 18; `betrieb.md` 3; `benachrichtigungen.md` 4.

## E-187 Oberfläche M15: Prüfmerkmale und Testwege

- **Frage:** Wie werden die Oberflächenteile der Definition (5–7, 1–4 jeweils „Oberfläche“) im Browser geprüft, wo die Definition Spielraum lässt?
- **Entscheidung:** (1) Gesendete Anfragen werden im Browser mitgeschnitten (Playwright `request`), damit „genau eine Anfrage“, „PATCH nur mit den geänderten Feldern“ und „keine Anfrage“ prüfbar sind. (2) `bis-markiert`: Zeiger auf `aenderung-bis-<id>` markiert genau die Einträge mit ID `≥ id`. Der Fehlerfall von 25.1 wird mit einer im Browser ersetzten Antwort (409) geprüft, weil er über REST nicht entsteht (E-182; wie E-180). (3) PIN-Dialog: Phasen über `mock_verzoegerung_ms` (`betrieb.md` 5.4) beobachtbar; geprüft werden `abruf`, `fertig`, `tan`, Sperre (`data-gesperrt`, `aria-busy`, `disabled`, Esc) und der Fehlerweg; die kurzen Phasen `pin` und `verbinden` werden nicht erzwungen. (4) `pin-abbrechen` ist eine neue Kennung für den vorhandenen Knopf „Abbrechen“. (5) Einnahmen/Ausgaben: Die Definition nennt nur „berechnen“ und `bericht-ea-diagramm`; der Knopf wird über seinen zugänglichen Namen gefunden. „Offline“ wird durch abgebrochene Anfragen an Dateien mit `plotly` im Pfad simuliert. Optik, Tooltips und Zoom sind nicht Teil der Abnahme. (6) Prozentangaben werden mit zusammengefasstem Leerraum verglichen (geschütztes Leerzeichen erlaubt); Titel bzw. `aria-label` der Vorschlagsmarke müssen den genannten Text enthalten. (7) Kandidaten „ab 1 %“ heißt Sicherheit ≥ 10 Promille. (8) Kontoeinstellungen: Bankkonten anderer Konten sind `disabled`; `PATCH` mit genau den geänderten Feldern. (9) Der Zuordnungsdialog folgt der Reihenfolge von `uebersprungen`; nach mindestens einer Zuordnung folgt ein weiterer Lauf, in dem nicht zugeordnete Bankkonten erneut gefragt werden.
- **Begründung:** Alles ist über die genannten Merkmale beobachtbar, ohne Aufbau oder Aussehen festzulegen (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 9, 11, 13.6, 13.9, 15.4, 21, 25; E-139, E-180.

## E-188 Kern-Tests von M15 und Selbstprüfung

- **Frage:** Welche M15-Tests tragen den Marker `kern`, und wie wird die Selbstprüfung erweitert?
- **Entscheidung:** Kern sind die REST- und Konfigurationstests (Rückgängig bis, mehrfach löschen, verschieben, Herkunft, `sync_konten_anlegen`, Umgebungsdatei, Sicherung). Die Wegwerf-Referenz erhält diese Teile (`referenz/kontor/m15.py`, kleine Ergänzungen in `m2.py`, `config.py`, `betrieb/kontor.env`) und neue Mutanten `m15_*`. Die Browsertests von M15 sind **nicht** kern: Die Referenz-Oberfläche ist eine kleine Wegwerf-Seite (E-149); Verschieben-, Zuordnungs- und Einstellungsdialoge, PIN-Phasen mit Abfrage des Laufstatus, Lernmodell-Kandidaten im Detailbereich und eine lokal ausgelieferte Diagrammbibliothek nachzubauen wäre unverhältnismäßig und würde vor allem die Referenz statt der Tests prüfen.
- **Begründung:** Die fachlichen Regeln (Protokoll, Atomarität, Prüfreihenfolgen, Konfiguration) sind der Kern der Abnahme und lassen sich mit wenig Referenzcode absichern; die Oberfläche prüft der Abnahmelauf gegen die echte Anwendung.
- **Bezug:** CLAUDE.md (Selbstprüfung); E-149, E-175.

## E-189 Schema und Version für M15

- **Frage:** Wie wird die REST-Erweiterung von M15 rückwärtskompatibel?
- **Entscheidung:** `openapi.yaml` 2.13.0: neue Pfade `POST /api/buchungen/mehrfach/loeschen` (`MehrfachLoeschen`, `MehrfachLoeschErgebnis`), `POST /api/buchungen/mehrfach/verschieben` (`MehrfachVerschieben`, `MehrfachVerschiebeErgebnis`), `GET /api/konten/{konto_id}/herkunft` (`Herkunft`); `Rueckgaengig.bis_id` (optional) und Antwort 404 bei `POST /api/aenderungen/rueckgaengig`; `SyncUebersprungen.status` um `nicht_zugeordnet` erweitert, `SyncUebersprungen.art` optional; `Benachrichtigung.art` um `konto_nicht_zugeordnet` erweitert (am Ende); Fehlercode `verschieben_unmoeglich`. Pflichtfelder bestehender Schemas bleiben unverändert. Die exakte Versionsprüfung wandert von `test_m13_schemas` nach `test_m15_schemas`; `test_m3_nachtrag_geloeschte_bankkonten` prüft die Statuswerte des Nachtrags als Anfang der Aufzählung und `test_m11_schemas` `saldo_ausgeglichen` als enthalten (bisher: letzter Wert) – beides Prüfungen des Schemas, keine App-Tests.
- **Begründung:** E-029, E-124: nur Ergänzungen; erweiterte Aufzählungen sind für frühere Antworten gültig.
- **Bezug:** E-029, E-124, E-173, E-178.

## E-190 Rückgängig bis ohne Nettowirkung: 409 `bereits_rueckgaengig` (ergänzt E-182)

- **Frage:** Nimmt ein „bis“ nur Änderungen zurück, die sich insgesamt aufheben (Beispiel: Änderungen 1–3, `U4` = bis 1, dann erneut bis 1 – zurückgenommen würden `U4`, 3, 2, 1), ist die Nettowirkung leer. Eine Änderung braucht aber mindestens einen Eintrag (`protokoll.md` 3.1, Schema `Aenderung.eintraege` `minItems: 1`), und Operationen ohne Wirkung erzeugen keine Änderung (4). E-182 hielt 409 `bereits_rueckgaengig` für unerreichbar; der Probelauf der Tests zeigte diesen Fall.
- **Entscheidung:** „Nichts zurückzunehmen“ (Definition 1) heißt: Die Nettowirkung ist leer, der Buchbestand entspricht schon dem Stand unmittelbar vor `bis_id`. Dann 409 `bereits_rueckgaengig`, keine Änderung, nichts ändert sich (`protokoll.md` 6.2a Nr. 4). Ersetzt E-182 Nr. 4, soweit es `bereits_rueckgaengig` betrifft; `rueckgaengig_konflikt` bleibt unerreichbar. Getestet in `test_ohne_nettowirkung_bereits_rueckgaengig` und in den Zufallsfolgen (`m15.Verlauf.bis`).
- **Begründung:** Eine Änderung ohne Einträge verletzt Schema und Grundregel T 3.5 („genau dann eine Änderung, wenn sich etwas ändert“); 409 `bereits_rueckgaengig` ist der in der Definition vorgesehene Code für „nichts zu tun“.
- **Bezug:** `protokoll.md` 3.1, 4, 6.2a; Definition M15 Abschnitt 1; E-182.

## E-191 Herkunft: Reihenfolge nur über die gelieferten Zeitpunkte geprüft (ergänzt E-185)

- **Frage:** E-185 nahm an, Importe und Läufe ließen sich mit der simulierten Uhr zeitlich ordnen. `importiert_am` ist aber nicht an die App-Uhr gebunden (`datenmodell.md` 8 nennt nur `date-time`; `synchronisation.md` 8 zählt Importvorgänge nicht auf), im Mock-Modus kann ein Import also „nach“ einem simulierten Lauf liegen.
- **Entscheidung:** Die Tests prüfen die Menge der Gruppen mit `art` und `anzahl` exakt, `zeitpunkt` je Gruppe gegen `importiert_am` bzw. `gestartet_am`/`beendet_am` und die Sortierung als „nach den gelieferten `zeitpunkt` absteigend“; eine bestimmte Reihenfolge von Import und Lauf wird nicht verlangt.
- **Begründung:** Die Spezifikation legt die Uhr der Importvorgänge nicht fest; eine Festlegung wäre eine neue Anforderung außerhalb von M15.
- **Bezug:** `datenmodell.md` 8, 18.3; `synchronisation.md` 8; E-185.

## E-192 Meilenstein-Definition M16 (robustere Erkennung wiederkehrender Buchungen mit Begründung) übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-11 die Meilenstein-Definition „Robustere Erkennung wiederkehrender Buchungen mit Begründung“ freigegeben (neue Kette mit zusätzlichen Zahlungen, Begründung je Buchung über REST und Oberfläche). M14 ist an das Feature `update` vergeben, M15 an das Sammelpaket. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als Meilenstein M16 mit Tests in `tests/app/m16/` (Marker `m16`); M14 bleibt frei. Spezifikation: `wiederkehrend.md` 2.2 (ersetzt, ohne Umschalter) und 8 (neu), `oberflaeche.md` 13.5 (Hinweis) und 26, `openapi.yaml` 2.14.0 (E-198). Geprüft werden die Kette über `GET /api/wiederkehrend`, die Begründung über den neuen Endpunkt (gegen eine unabhängige Referenz der Kette, E-193) und die Oberfläche über `data-testid` und Zustandsattribute. Nicht geprüft werden nach Abschnitt 5 der Definition der Wortlaut der Sätze (`text`, `gruppe`), die Gestaltung (Farben, Hervorhebungsdauer) und ob Alt+Rechtsklick in einer Desktopumgebung den Browser erreicht. Keine neue Objektart, kein neuer Zustand, keine Änderung an Protokoll und Sicherung (Definition 4).
- **Begründung:** Eigene Nummer wie bei M15 (E-181); die Definition ersetzt eine M5-Regel ausdrücklich, deshalb ist die Anpassung früherer Tests hier ausnahmsweise Teil des Meilensteins (E-194).
- **Bezug:** K 5, K 9; T 10; E-029, E-181.

## E-193 Kette nach M16: Auslegung und Referenz

- **Frage:** Die Definition (Abschnitt 1) lässt einige Einzelheiten offen: Gehören Anker-Kandidaten vor dem gewählten Anker zu den zusätzlichen Zahlungen? Was gilt für die Einträge zwischen `p` und `c`, wenn die Kette mit `fremde_zahlung` endet? Wie werden „unmittelbar vor `c`“, „jünger“ und Gleichstände gelesen?
- **Entscheidung:** (1) Alle Anker-Kandidaten außer dem gewählten sind zusätzliche Zahlungen; der Schritt `anker` führt sie in `uebersprungen` („die anderen Kandidaten“). Kandidaten vor dem Anker liegen höchstens `T` Tage vor ihm und werden im ersten Schritt ohnehin noch einmal als zusätzlich erkannt (sie dürfen dort erneut in `uebersprungen` stehen). (2) Die Regel „Für jeden Eintrag zwischen `p` und `c` gilt: Er ist eine zusätzliche Zahlung, wenn …“ gilt wörtlich auch dann, wenn die Kette mit `fremde_zahlung` endet: Einträge dazwischen, die das Kriterium erfüllen, sind zusätzlich (Rolle `zusaetzlich`, in `uebersprungen` des Bruchs); die übrigen sind `vor_beginn`; `fremd` ist der jüngste von ihnen. (3) Ohne Vorgänger-Kandidaten sind zusätzlich genau die Einträge, die in der Gruppenfolge lückenlos unmittelbar vor `c` liegen und für die `c.datum − x.datum ≤ T` gilt; der nächste davor ist der „nächste ältere Eintrag“ (`abstand`). Vorgänger-Kandidaten des vorigen Schritts zählen hier nicht mit (die Definition nennt das Kriterium nur für Einträge zwischen `p` und `c`). (4) „Jünger“ heißt später nach (`datum`, `buchung_id`); alle Abstände sind ganze Tage, „höchstens `T` Tage entfernt“ heißt Betrag des Abstands `≤ T`. (5) Die Kette und die Anker-Auswahl werden für jeden Rhythmus eigenständig gebildet (2.3: erster Rhythmus mit ausreichender Länge). (6) Die Tests berechnen alle Erwartungen mit einer eigenen Referenz der Kette (`tests/hilfen/wiederkehrend_orakel.py`: `kette`, `serie_mit_rhythmen`; darauf aufbauend `tests/hilfen/m16.py` für die Begründung). Der Generator prüft seine Daten mit einer zweiten, unabhängig geschriebenen Fassung (`generator/m5_daten.py`, `_spec_kette`), die Selbstprüfung mit einer dritten (`referenz/kontor/m16.py`).
- **Begründung:** (2) folgt dem Wortlaut („Ist mindestens ein Eintrag dazwischen keine zusätzliche Zahlung“ setzt voraus, dass die anderen zusätzliche Zahlungen sind). (1) und (3) folgen den Beispielen der Definition („13.01. ist zusätzlich (am selben Termin wie das erste Glied)“). Drei getrennte Fassungen machen Fehler der Referenz unwahrscheinlich.
- **Bezug:** `wiederkehrend.md` 2.2; Definition M16 Abschnitt 1.

## E-194 M5-Test, Orakel und Generator an die neue Kette angepasst

- **Frage:** Definition 4: Der M5-Test `test_doppelte_zahlung_unterbricht_die_kette` widerspricht der neuen Regel (15.01., 15.02., 15.03. und 15.03. doppelt sind nun eine Serie mit drei Gliedern). Welche früheren Tests, Hilfen und Fixtures sind betroffen?
- **Entscheidung:** (1) Der Test heißt jetzt `test_doppelte_zahlung_am_termin_ist_zusaetzlich` und erwartet eine Serie mit drei Gliedern, `buchung_ids` = erste, zweite und **vierte** Buchung (Anker ist die jüngere Zahlung am 15.03., Definition 1.1 Nr. 3), Betrag und Jahreskosten unverändert. (2) Das Orakel `tests/hilfen/wiederkehrend_orakel.py` (`serie`) rechnet mit der neuen Kette; damit folgen `test_serien_gleich_orakel`, `test_umbuchung_zaehlt_je_konto_darlehenskonto_nie`, die Ereignisse (`ereignisse`, Ereignis 2 mit der Serie der Vorgeschichte) und die Generatortests der neuen Regel. (3) Die Selbstkontrolle des Generators (`_spec_erkennung`) nutzt die neue Kette. `python -m generator` erzeugt danach byteweise dieselben Fixtures: Die Daten in `mock/m5_wiederkehrend.json` enthalten keine zusätzlichen Zahlungen am Termin, die konstruierte Wahrheit (`*.erwartung.json`) ist unter beiden Regeln dieselbe; alle übrigen M5-Tests (Mindestanzahl, Status, Toleranz, Betragsänderung, ausbleibende Zahlung) haben unter beiden Regeln dieselben Erwartungen und bleiben unverändert. (4) Die Wegwerf-Referenz der Selbstprüfung erkennt Serien mit der neuen Kette (`referenz/kontor/m16.py`); die M5-Mutanten bleiben wirksam.
- **Begründung:** Die Definition ersetzt `wiederkehrend.md` 2.2 ausdrücklich und ohne Umschalter; E-029 („Tests früherer Meilensteine bleiben unverändert“) gilt deshalb für diesen einen Test nicht. Die übrigen Erwartungen wurden unabhängig nach der neuen Regel nachgerechnet.
- **Bezug:** `wiederkehrend.md` 2.2, 2.3, 3; Definition M16 Abschnitt 4; E-029, E-098, E-099.

## E-195 Begründung je Buchung: Prüfregeln und Auslegung

- **Frage:** Welche Einzelheiten von `GET /api/buchungen/{id}/wiederkehrend` (Definition 2) prüfen die Tests, und wie werden offene Punkte gelesen?
- **Entscheidung:** (1) 422 `validierung` bei ungültigem `stichtag` (auch `2024-02-30`) und bei einem unbekannten Query-Parameter; 404 `nicht_gefunden` für eine unbekannte Buchung; die Reihenfolge, wenn beides zutrifft, wird nicht geprüft. Ohne `stichtag` gilt *heute* der App-Uhr (Mock: `mock_heute`). Kein Eintrag im Änderungsprotokoll, keine Wirkung auf den Buchbestand. (2) Verglichen wird die ganze Antwort mit der Erwartung aus `tests/hilfen/m16.py` ohne die Felder `text` und `gruppe` (nur nicht leer); `uebersprungen` wird ohne Rücksicht auf die Reihenfolge (sortiert nach `datum`, `buchung_id`) verglichen, alle anderen Listen in der festgelegten Reihenfolge. Alle Felder sind immer vorhanden: `kandidaten` ist außer beim Schritt `anker` leer, `glied` ist außer bei `glied` null (auch in `buchungen`). (3) Bestandskonten sind wie in 2.1 Konten der Arten `girokonto`, `sparkonto`, `kreditkonto`; `ausgeschlossen` ist nach `konto.id` sortiert. Hat die Buchung einen Empfänger und liegt sie nicht nach dem Stichtag, enthält `ausgeschlossen` genau ihre Bestandskonten ohne Eintrag; für ein Darlehenskonto mit Summe null gilt `darlehenskonto` (nicht geprüft). Ohne Empfänger oder nach dem Stichtag sind `urteil = ausgeschlossen` und `eintraege = []` geprüft, der Inhalt von `ausgeschlossen` nicht. (4) `serie` ist gleich der Serie derselben Gruppe in `GET /api/wiederkehrend` mit demselben Stichtag (einschließlich `status`); die Tests vergleichen beide Antworten auch direkt. (5) Die Rollen beziehen sich auf den ersten erfüllten Rhythmus; ohne Serie tragen alle Einträge der Gruppe `keine_serie`, `rhythmen` enthält dann alle drei. (6) Das Gesamturteil wird über alle Einträge der Buchung gebildet (z. B. Umbuchung mit Eintrag auf zwei Konten).
- **Begründung:** Die Felder sind in der Definition vollständig beschrieben; `uebersprungen` hat dort keine Reihenfolge, die übrigen Listen haben eine. Die Darlehens-/Null-Kombination und `ausgeschlossen` ohne Empfänger sind in der Definition nicht entschieden und werden deshalb nicht festgelegt.
- **Bezug:** `wiederkehrend.md` 2.1, 2.5, 8; Definition M16 Abschnitt 2.

## E-196 Oberfläche M16: Prüfmerkmale und Testwege

- **Frage:** Wie werden Begründungsdialog, versteckter Kontextmenüeintrag, Befehlspalette, Menü je Serie und Sprungziel (Definition 3) im Browser geprüft?
- **Entscheidung:** (1) Alt+Rechtsklick als Playwright-Klick mit `button="right"` und `modifiers=["Alt"]`; Alt+Umschalt+F10 und Alt+Menütaste als Tastendruck auf der fokussierten Zeile. Ohne Alt sind die Einträge des Menüs genau die bisherigen (gleiche Folge von `data-testid` wie beim Rechtsklick ohne Alt), mit Alt dieselben und als letzter `km-wiederkehrend`. Bei mehr als einer gewählten Buchung trägt er `aria-disabled="true"` und öffnet nichts. (2) Dialog: `wk-urteil` (`data-urteil`, Text beginnt nach Zusammenfassen von Leerraum mit „Wiederkehrend? Ja“ bzw. „Wiederkehrend? Nein“), der Stichtag als `TT.MM.JJJJ` im Dialog, `wk-text` nur ohne Einträge, je Eintrag `wk-eintrag` in der Reihenfolge von `eintraege` mit `data-urteil`, darin `wk-eintrag-text`, `wk-buchungen` mit den Zeilen `wk-buchung` (Reihenfolge, `data-id`, `data-rolle`; Rolle als Text „Glied n“, „zusätzlich“, „vor Beginn“ bzw. „–“ im Textinhalt, auch eingeklappt), „(diese Buchung)“ und Klasse `wk-betroffen` genau an der angefragten Buchung, je geprüftem Rhythmus genau ein `wk-rhythmus-<rhythmus>` mit den `wk-schritt` in Reihenfolge (`data-ergebnis`; `data-grund` = Grund, bei Schritten ohne Grund fehlend oder leer) und `wk-betroffen` genau an den Schritten mit Beteiligung der Buchung. „Aufgeklappt“ heißt: die Schritte des zuletzt geprüften Rhythmus sind sichtbar. Gruppenbeschriftung, Hinweis auf Gruppengröße und Toleranz und Texte werden nicht geprüft. (3) Fokus: Nach Schließen (Knopf oder Escape) liegt der Fokus auf dem Element, auf dem das Menü geöffnet wurde (Buchungszeile bzw. `wk-menue-<schluessel>` bzw. Zeile `serie-<schluessel>`); beim Weg über die Befehlspalette wird nur das Schließen geprüft. (4) Befehlspalette: `befehl-wiederkehrend-warum` erscheint genau bei einer gewählten Buchung auf einer Kontoansicht (nicht bei keiner oder zwei, nicht auf anderen Seiten); die Stelle in der Liste ist frei. (5) `/wiederkehrend`: `wk-menue-<schluessel>` ist das letzte Element der Zeile mit `aria-haspopup="menu"` und einem `aria-label`, das den Empfängernamen enthält; die Zeile ist fokussierbar (`tabindex`). Die Kopfspalte für Screenreader wird nicht geprüft. Leere Liste: Der sichtbare Text der Seite ohne Überschrift ist genau „Keine wiederkehrenden Buchungen erkannt.“. (6) Sprungziel: Ein Konto mit mehr als 200 Buchungen, das Ziel auf der zweiten Seite (Sortierung `-datum`); geprüft werden Auswahl genau dieser Zeile, Fokus, Lage im sichtbaren Bereich, `auswahl-anzahl` und die Adresse ohne `buchung`, mit den übrigen Parametern. Der Hinweis bei ausgefiltertem Ziel ist eine Meldung (4.3) mit `data-art="hinweis"`. Ein ungültiger Wert (`buchung=abc`) lässt die Seite normal laden, ohne Auswahl und ohne Fehlermeldung. (7) Mobil: Begründung über die Befehlspalette und das Menü je Serie über lange Berührung.
- **Begründung:** Alles ist über Testkennungen und Zustandsattribute beobachtbar, ohne Aufbau oder Aussehen festzulegen (`oberflaeche.md` 1). Die Hinweis-Meldung nutzt die schon spezifizierte Art `hinweis` statt einer neuen Kennung.
- **Bezug:** `oberflaeche.md` 4.3, 5, 7, 8, 12.3, 13.5, 16.4, 21, 26; Definition M16 Abschnitt 3 und 5.

## E-197 Kern-Tests von M16 und Selbstprüfung

- **Frage:** Welche M16-Tests tragen den Marker `kern`, und wie wird die Selbstprüfung erweitert?
- **Entscheidung:** Kern sind alle REST-Tests (Kette, Begründung, Fehlerfälle, Übereinstimmung mit der Übersicht) und die Browsertests auf dem Desktop (Dialog, versteckter Eintrag, Befehlspalette, Menü je Serie, Sprungziel). Die Wegwerf-Referenz erhält dafür die neue Kette und den Endpunkt (`referenz/kontor/m16.py`, eingebunden in `m5.py`) sowie eine kleine Fassung des Dialogs, des Menüs je Serie und des Sprungziels in `oberflaeche/app.js`; neue Mutanten `m16_*`. Nicht kern sind die Tests der mobilen Ansicht (lange Berührung): Die Referenz-Oberfläche erkennt keine Gesten (E-149).
- **Begründung:** Anders als die Dialoge von M15 (E-188) ist die M16-Oberfläche klein genug, um sie in der Referenz nachzubauen; so prüft die Selbstprüfung auch die Browsertests selbst.
- **Bezug:** CLAUDE.md (Selbstprüfung); E-149, E-188.

## E-198 Schema und Version für M16

- **Frage:** Wie wird die REST-Erweiterung von M16 rückwärtskompatibel?
- **Entscheidung:** `openapi.yaml` 2.14.0: neuer Pfad `GET /api/buchungen/{buchung_id}/wiederkehrend` (Query `stichtag`, Antworten 200, 404, 422) mit den Schemas `WiederkehrendBegruendung`, `BegruendungEintrag`, `BegruendungRhythmus`, `BegruendungSchritt` und den Hilfsschemas `BegruendungVerweis` (`{buchung_id, datum, betrag}`) und `BegruendungKonto` (`{id, name}`); alle Felder Pflicht, `additionalProperties: false`, `text` und `gruppe` nicht leer. Bestehende Schemas (insbesondere `WiederkehrendSerie`) bleiben unverändert. Die exakte Versionsprüfung wandert von `test_m15_schemas` nach `test_m16_schemas`.
- **Begründung:** E-029, E-124: nur Ergänzungen.
- **Bezug:** E-029, E-124, E-189.

## E-199 Meilenstein-Definition „Tabs der Ansichten, Gehe zur Gegenbuchung“ als M17 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-11 die Meilenstein-Definition des Features `tabs-gegenbuchung` freigegeben (Tabs für alle Ansichten mit Zustand, Speicherung im Browser, Kontextmenü „Gehe zur Gegenbuchung“); sie nennt sich „M16“. Am selben Tag hat ein anderer Test-Thread die Nummer M16 schon für das Feature `wiederkehrend-begruendung` vergeben (E-192, `oberflaeche.md` 26, `tests/app/m16/`, Marker `m16`). M14 ist weiter an `update` vergeben. Wie wird die Definition übernommen?
- **Entscheidung:** Übernahme als Meilenstein **M17** (nächste freie Nummer) mit Tests in `tests/app/m17/` (Marker `m17`, Hilfen `tests/hilfen/m17.py`); Spezifikation `oberflaeche.md` 27 (mit Hinweis in 8.2). Verweise der Definition auf „M16“ und ihre Abschnittsnummern gelten für M17; der Feature-Branch heißt weiter `feature/tabs-gegenbuchung`. `openapi.yaml` bleibt unverändert (2.14.0 nach M16, E-198), kein Eintrag in `protokoll.md` 4 (keine Operation mit Wirkung auf den Buchbestand), nichts in der Sicherung (`sicherung.md` 2.3: kein neuer fachlicher Zustand; die gespeicherten Tabs sind Gerätezustand wie Layout und Design, E-141). M14 bleibt frei. Verträglich mit M16: Das Alt-Kontextmenü (`oberflaeche.md` 26.2) hängt `km-wiederkehrend` als letzten Eintrag an; die M17-Tests öffnen das Menü ohne Alt, wo `km-loeschen` der letzte bleibt. Der Parameter `buchung=<id>` (26.4) ist kein Filter und wird aus der Adresse entfernt; für die Tabs zählt der verbleibende Abfrageteil.
- **Begründung:** Eine eigene Nummer lässt frühere Tests und die schon übernommene M16 unverändert (E-029); die Definition ist eine reine Verhaltensbeschreibung der Oberfläche.
- **Bezug:** K 5, K 14; T 19; `oberflaeche.md` 3, 7, 8, 11, 16, 23; E-029, E-141, E-181, E-192.

## E-200 Gehe zur Gegenbuchung: Prüfmerkmale

- **Frage:** Wie werden Eintrag, Wirkung und Fehlerfälle (Definition 2 und 3) im Browser geprüft, wo die Definition Spielraum lässt?
- **Entscheidung:** (1) Position: In der Liste der `role="menuitem"` des Kontextmenüs steht `km-gegenbuchung` unmittelbar nach `km-mehrfach`, `km-loeschen` ist der letzte. (2) Text nach Zusammenfassen des Leerraums genau „Gehe zur Gegenbuchung“ bzw. „Gehe zur Gegenbuchung…“ (U+2026). (3) „Ohne Gegenseite“ entsteht durch eine Buchung, deren Splits alle auf dem Konto der Ansicht liegen (zulässig, `datenmodell.md` 3: mindestens zwei Splits, Summe 0); „jedes Konto nur einmal“ durch zwei Splits auf derselben Kategorie (dann kein Untermenü). Die Split-Reihenfolge der Testbuchung weicht von der ID-Reihenfolge der Konten ab. (4) „Hat den Fokus“ heißt Fokuszeile der Liste (`tabindex="0"`, 7.4); „sichtbar“ heißt im sichtbaren Bereich des Fensters. (5) Esc im Untermenü schließt es ohne Wirkung; ob das Hauptmenü danach offen bleibt, ist frei. (6) „Ändert keine Daten“: Mitschnitt der Anfragen im Browser (nur GET), höchste Änderungs-ID unverändert, `rueckgaengig-knopf` bleibt deaktiviert. (7) Nachladen: Die Umbuchung liegt in der Zielansicht hinter den ersten 200 Zeilen (205 weitere Buchungen). (8) Fehlerfälle: Die Änderung (Konto löschen mit `POST /api/konten/{id}/loeschen` und `unkategorisiert`, Buchung löschen, Kategorie ändern) geschieht über REST, während das Kontextmenü schon offen ist; der Klick auf den Eintrag wirkt also mit dem Stand der angezeigten Zeile. (9) Filter-Reset: Ziel-Tab mit Statusfilter, der die Buchung ausblendet, und Sortierung `datum`; danach `filter-anzahl` 0, Abfrage der URL genau `sortierung=datum`, Hinweis mit dem Text der Definition. Blendet der Filter die Buchung nicht aus, bleibt er (Definition 1.3) und es erscheint kein Hinweis.
- **Begründung:** Alle Prüfungen nutzen nur die festgelegten Merkmale (`oberflaeche.md` 1); die Reihenfolge der Gegenseiten wird aus den angelegten Splits im Test bestimmt.
- **Bezug:** `oberflaeche.md` 7.4, 8, 11, 27.2, 27.3; `datenmodell.md` 3, 4; `loeschen.md` 2; Definition `tabs-gegenbuchung` Abschnitte 2 und 3.

## E-201 Tabs: Prüfmerkmale, Speicher und nicht geprüfte Teile

- **Frage:** Wie werden die Tabs (Definition 1) geprüft, wo die Definition keine Merkmale nennt (Speicherort, Scrollstände, offline)?
- **Entscheidung:** (1) Titel = Text von `tab-titel` nach Zusammenfassen des Leerraums; `href` als Pfad samt Abfrage verglichen. (2) „Inaktive Tabs hängen nicht im Dokument“: bei aktiver Finanzübersicht gibt es weder `seite-konto` noch `buchungsliste`. (3) Navigation zum Anfordern ohne Abfrageteil: Navigationsleiste und Befehlspalette (`befehl-konto-<id>`, 12.3); „Gehe zur Gegenbuchung“ in E-200. (4) Zustand beim Wechsel: Filter (Leiste, Häkchen, `filter-anzahl`, URL), Sortierung (`aria-sort`), Auswahl, Fokuszeile, nachgeladene Seiten (Zeilenzahl ohne erneutes „Mehr“); Scrollstände und Panels werden nicht geprüft. (5) Tastatur: Fokus gilt als „auf dem Tab“, wenn `document.activeElement` im Element `role="tab"` liegt oder es ist; „nur der aktive Tab per Tabulatortaste erreichbar“ heißt: nur im aktiven Tab gibt es ein Element mit `tabIndex ≥ 0`. (6) Strg-/Umschaltklick: geprüft wird, dass die Standardaktion des Browsers nicht verhindert wird (`defaultPrevented = false`) und der Tab nicht wechselt; ob headless Chromium das neue Fenster öffnet, ist im Probelauf nicht zuverlässig (Klick mit Strg kam an, nicht verhindert, trotzdem zeitweise kein neues Fenster). Mittelklick auf `tab-titel` schließt den Tab. (7) Speicherung: Ort und Format sind frei (`oberflaeche.md` 27.1.6). „Lädt erst, wenn aktiv“: nach dem Neuladen keine Anfrage `GET /api/buchungen` mit `konto_id` des inaktiven Kontos und kein `GET /api/konten/<id>`, bis der Tab aktiv wird; dann mit dem gespeicherten Abfrageteil. Grenze 40: 42 offene Tabs in der laufenden Seite (keine Begrenzung), nach dem Neuladen 1 bis 40 Tabs ohne doppelte Pfade, darunter der aufgerufene; welche wegfallen, ist frei. (8) Ungültiger Inhalt: alle Schlüssel des `localStorage` außer `kontor.layout` und `kontor.thema` werden mit ungültigen Werten überschrieben (liegen die Tabs nicht im `localStorage`, wird dieser Fall übersprungen). Nicht verfügbar: (a) der Zugriff auf `window.localStorage` wirft wie in Chromium bei gesperrtem Website-Speicher, (b) nur `getItem`/`setItem`/`removeItem` für andere Schlüssel als die von Layout und Design werfen; in beiden Fällen startet die Oberfläche ohne gespeicherte Tabs, ohne unbehandelte Fehler. (9) Nicht geprüft: das Verhalten offline (Definition 1.4 zweiter Punkt, kein festgelegtes Merkmal), ein Link mit abweichendem Abfrageteil (kein festgelegtes Element erzeugt einen solchen Link innerhalb der Oberfläche) und das Neuaufbauen bei exakt gleicher URL (von „Zustand behalten“ ohne festgelegtes Merkmal nicht unterscheidbar). (10) Mobil: `tab-leiste` sichtbar, der aktive Tab liegt waagrecht innerhalb der Leiste, kein waagerechtes Scrollen der Seite (16.2).
- **Begründung:** Die Definition legt Rollen, Attribute und Wirkungen fest, aber keinen Speicherort; die Tests bleiben bei beobachtbaren Merkmalen und legen nichts zusätzlich fest.
- **Bezug:** `oberflaeche.md` 1, 7.1, 7.4, 12.3, 15.3, 16, 17, 27.1; E-141, E-172; Definition `tabs-gegenbuchung` Abschnitt 1.

## E-202 M17 ohne Kern-Tests und ohne Selbstprüfungsreferenz

- **Frage:** Welche M17-Tests tragen `kern`, und braucht die Selbstprüfung eine Referenz für M17?
- **Entscheidung:** Kein M17-Test ist `kern`; alle sind Browsertests (`browser`). Die Wegwerf-Referenz (`tests/_selbstpruefung/referenz`) erhält keine M17-Teile und keine neuen Mutanten; die Selbstprüfung ist für M17 nicht nötig und bleibt unverändert. Abnahme ist der Lauf `python -m pytest -m m17` gegen die echte Anwendung.
- **Begründung:** Wie für die Oberflächentests von M15 (E-188): Tabs mit Zustand, Speicherung, Tastaturführung und Untermenü in der kleinen Referenz-Seite (E-149) nachzubauen prüfte vor allem die Referenz. M17 hat keine REST- oder Konfigurationsteile.
- **Bezug:** CLAUDE.md (Selbstprüfung); E-149, E-175, E-188.

## E-203 Begründungsdialog: Einzelheiten nur bei Buchungen mit einem Eintrag geprüft (ergänzt E-196)

- **Frage:** Die Kennungen `wk-buchungen`, `wk-buchung`, `wk-rhythmus-<rhythmus>` und `wk-schritt` kommen je Eintrag vor (Definition 3.1); bei einer Buchung mit zwei Einträgen (Umbuchung zwischen eigenen Konten) gibt es sie also doppelt, ohne dass die Definition festlegt, wie sie dem Eintrag zugeordnet sind (verschachtelt oder in Reihenfolge).
- **Entscheidung:** Für Buchungen mit genau einem Eintrag prüfen die Browsertests alle Einzelheiten nach E-196 Nr. 2 im ganzen Dialog. Bei mehreren Einträgen werden nur Anzahl und Reihenfolge der `wk-eintrag` mit `data-urteil` und je ein `wk-eintrag-text` geprüft; die Einzelheiten deckt dort die REST-Prüfung ab.
- **Begründung:** Keine Festlegung des Aufbaus über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 26.1; E-196.

## E-204 Leere Liste auf `/wiederkehrend`: Präzisierung von „kein weiterer Text“ (ergänzt E-196 Nr. 5)

- **Frage:** Der Testlauf von M16 meldet einen Widerspruch: `test_leere_liste_nur_hinweis` verlangte, dass bei leerer Liste nach der Überschrift überhaupt kein Text außer dem Hinweis steht. Die Seite zeigt aber wie seit M8 den Knopf „Jetzt prüfen“ im Seitenkopf, die Summenzeile („Summe der Jahreskosten: 0,00 €“) und den Tabellenkopf. Nach Auskunft des Implementierungs-Threads und des Auftraggebers meint Definition 3.3 („kein weiterer Text“) nur, dass neben bzw. unter der Tabelle kein weiterer Text steht, insbesondere nicht mehr das Wort „null“ eines früheren Anzeigefehlers. „Jetzt prüfen“ bleibt nötig, weil `POST /api/wiederkehrend/pruefen` auch ohne Serien Ereignisse erzeugt („neuer Empfänger“, `wiederkehrend.md` 3.1).
- **Entscheidung:** `oberflaeche.md` 26.3 ist präzisiert. Bei leerer Liste gibt es keine Zeilen `serie-<schluessel>`. Außerhalb von Seitenkopf mit „Jetzt prüfen“, Summenzeile und Tabellenkopf steht als Text nur der Hinweis „Keine wiederkehrenden Buchungen erkannt.“. Nirgends erscheint „null“. Der Test prüft: keine `serie-`-Zeilen, den Hinweis genau einmal und sichtbar, im sichtbaren Text der Seite kein Wort „null“, „undefined“ oder „NaN“. Weitere Bestandteile der Seite werden nicht festgelegt. Ersetzt E-196 Nr. 5, soweit es die leere Liste betrifft.
- **Begründung:** Die Klarstellung kommt vom Auftraggeber. Eine strukturelle Prüfung von „außerhalb von Kopf, Summenzeile und Tabellenkopf“ würde den Aufbau der Seite festlegen (`oberflaeche.md` 1); die beobachtbare Kernaussage ist der fehlende Fehltext.
- **Bezug:** `oberflaeche.md` 13.5, 26.3; `wiederkehrend.md` 3.1, 4; Definition M16 Abschnitt 3.3; E-196.

## E-205 Abstimmungsdialog: Schließen abwarten statt sofort prüfen (W-010)

- **Frage:** Der Testlauf meldet einen Widerspruch (W-010): `test_konten_anlegen_und_abstimmen` prüfte nach `abstimmung-speichern` und dem Warten auf die gespeicherte Abstimmung über REST einmalig ohne Warten, dass `abstimmung-dialog` geschlossen ist. Der Server hat die Abstimmung aber gespeichert, bevor seine Antwort im Browser ankommt; die Oberfläche kann erst danach schließen. Unter Last (parallele Browsertests) schlug der Test deshalb schwankend fehl.
- **Entscheidung:** Der Einwand ist berechtigt. Der Test wartet mit `expect(d).to_be_hidden()` (Zeitgrenze `WARTEN_MS`) auf das Schließen; die Aussage (Dialog fehlt oder ist unsichtbar) bleibt gleich. Eine Durchsicht von `tests/app/m8/` fand keine weitere Sofortprüfung eines Oberflächenzustands direkt nach `m8.warte_bis(...)` auf Serverzustand.
- **Begründung:** `oberflaeche.md` 9 und 13.3 verlangen nur, dass der Dialog nach dem Erfolg schließt, nicht gleichzeitig mit dem Speichern im Server. Zustände der Oberfläche werden in den M8-Tests abgewartet, Zustände des Servers mit `warte_bis` (`tests/hilfen/m8.py`).
- **Bezug:** `oberflaeche.md` 9, 13.3; E-148.

## E-206 Meilenstein-Definition „Dokumente an Buchungen“ als M18 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Meilenstein-Definition M18 (Feature `dokumente`, kontor-app D-123 „Dokumente“) freigegeben. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M18** mit Tests in `tests/app/m18/` (Marker `m18`, Hilfen `tests/hilfen/m18.py`). Abschnitte 1–4 und 6 der Definition stehen wörtlich in `spec/api/dokumente.md`, Abschnitt 5 als `oberflaeche.md` 28. Ergänzt sind `datenmodell.md` 7 (Belege ab M18), `protokoll.md` 15 (Objekt `dokument`, Feld `dokument_ids`, sechs Aktionen), `sicherung.md` 2.7 (nur bei Vorhandensein wie `kredit`/`postfach`), `sicherheit.md` 8 (`POST /api/dokumente` ist Upload-Pfad) und `openapi.yaml` (E-210). Die Konfiguration ist unverändert. M14 bleibt an `update` vergeben.
- **Begründung:** Neuer fachlicher Zustand ab M9 gehört zur Sicherung (CLAUDE.md), neue Operationen ins Protokoll (Tabelle 4); die Definition legt beides fest.
- **Bezug:** K 4, K 14; T 3.5, T 3.6, T 4; `dokumente.md`; E-029, E-109, E-118.

## E-207 M18: Bestand mit Dokumenten und Prüfung der Einträge

- **Frage:** Wie berechnen die Tests den Buchbestand mit Dokumenten, obwohl es keinen Listen-Endpunkt für Dokumente gibt?
- **Entscheidung:** `tests/hilfen/m18.bestand` nimmt den Bestand aus M6 und ergänzt (1) bei jeder Buchung mit nicht leeren `belege` das Feld `dokument_ids` (IDs aus `belege`, die aufsteigend sortiert sein müssen) und (2) je dort genannter ID das Objekt `dokument` aus `GET /api/dokumente/{id}` ohne `buchung_ids`. Weil ein Dokument nie ohne Buchung existiert (`dokumente.md` 1.1), ist das vollständig. Einträge werden in der Reihenfolge von `protokoll.md` 3.1 mit `dokument` nach `postfach` geprüft. Ohne Dokumente ist dieser Bestand gleich dem aus M6 (eigener Test). Die Inhaltsprüfsumme der Sicherung wird aus diesem Bestand mit dem Schlüssel `dokument` nur bei Vorhandensein berechnet. `erstellt_am` wird im Mock-Modus mit gesetzter Uhr exakt geprüft.
- **Begründung:** Die Protokollform ist laut Definition 3.1 „ableitbar aus `GET /api/dokumente/{id}` ohne `buchung_ids`“ und `dokument_ids` „aus `belege`“.
- **Bezug:** `dokumente.md` 1.1, 1.4, 3.1, 4; `protokoll.md` 2, 15; `sicherung.md` 3.3.

## E-208 M18: Auslegung offener Punkte der REST-Regeln

- **Frage:** Einige Regeln der Definition lassen Spielraum oder sind über httpx nicht direkt prüfbar.
- **Entscheidung:** (1) **Dateiname im Upload:** Die Tests bauen den `multipart/form-data`-Körper selbst, damit der Dateiname unverändert (UTF-8) im Kopf steht, auch leer (`filename=""` = „Upload ohne Namen“); httpx würde Steuerzeichen prozentkodieren und einen leeren Namen weglassen. Namen mit Steuerzeichen (NUL, Zeilenumbruch) werden über `PATCH /api/dokumente/{id}` geprüft, für den dieselben Regeln 1.3 gelten (2.4). (2) **Betreff als Name:** „höchstens 196 Zeichen“ (1.3, 2.2) heißt: der Betreff wird auf 196 Zeichen gekürzt; nur ein leerer Betreff ergibt „E-Mail“ (2.2: „leer → E-Mail“). Für Mails aus dem Spiegel ist es der Betreff der gespiegelten Nachricht (bei IMAP so, wie `mail.md` 3.3 ihn liefert). (3) **Typerkennung:** Erst führende Leerzeilen, dann eine optionale `From `-Zeile; der Kopfblock endet an der ersten Leerzeile; Fortsetzungszeilen zählen nicht als neue Kopfzeile. (4) **Unbekannte Felder** in JSON-Körpern (aus-mail, verknüpfen, umbenennen) und **Booleans** an Ganzzahlstellen → 422 `validierung` (allgemeine Regel von `openapi.yaml`). (5) **Rückgängig-Konflikt** (3.3) gilt nur, wenn ein Dokument durch das Rückgängig *entfernt* würde; Rückgängig eines Umbenennens oder Lösens (das Dokument bleibt) ist davon nicht betroffen. (6) **Anhänge (2.10):** Nummern aus der Tiefensuche über alle MIME-Teile wie `email.Message.walk()` (Wurzel 0); `groesse` = Länge der dekodierten Bytes. Ein eingebetteter `message/rfc822`-Teil erscheint als Anhang mit diesem Typ (2.13 „als ganze Nachricht“); seine Nummer und die Behandlung seiner Unterteile legen die Tests nicht fest. (7) **Mail-Ansicht:** `text` wird ohne abschließende Zeilenumbrüche verglichen, Text aus HTML nach Zusammenfassen des Leerraums. (8) **Köpfe:** `Cache-Control` wird als Menge der Direktiven `{private, no-store}` geprüft, die CSP als Menge der Direktiven; `filename*` muss nach Prozentdekodierung genau den Dateinamen ergeben. (9) **Entschärftes HTML:** geprüft wird das Fehlen der genannten Elemente, Ereignis-Attribute, gefährlichen URLs und jeder externen Adresse aus Bildern, Stilen, Rahmen und `base`; vorhanden bleiben Text, Links (`<a href>`), `data:image/png` und ein `<base … target="_blank">`. (10) **Zu große Rohfassung** (Fallback auf die Felder) wird nicht geprüft; geprüft sind die Rohfassung aus der IMAP-Attrappe und der Bau aus den Feldern im Mock-Modus.
- **Begründung:** Alle Punkte folgen aus dem Wortlaut der Definition oder den allgemeinen Regeln; wo beides offen ist, legen die Tests nichts fest.
- **Bezug:** `dokumente.md` 1.2, 1.3, 2.1–2.13, 3.3; `mail.md` 3.3; `openapi.yaml` (allgemeine Regeln).

## E-209 M18: Prüfmerkmale der Oberfläche

- **Frage:** Wie werden Marke, Einzelheiten, Mail-Auswahl, Betrachter, Kontextmenü und Ablage (`oberflaeche.md` 28) geprüft?
- **Entscheidung:** (1) `aria-label` der Marke: wörtlich „<n> Dokument(e) ansehen“ oder mit ausgeschriebener Ein-/Mehrzahl („1 Dokument ansehen“, „2 Dokumente ansehen“). (2) Die versteckten Dateiauswahlen dürfen erst beim Klick entstehen; geprüft wird das Element des Datei-Dialogs (`FileChooser.element`: `data-testid`, `type`, `multiple`, `accept`, `capture`). (3) Je hochgeladener Datei eine Änderung `dokument_anhaengen`; eine ungültige Datei erzeugt eine Fehlermeldung (`data-art="fehler"`), die übrigen werden trotzdem hochgeladen. (4) Kontextmenü: die drei Einträge folgen in dieser Reihenfolge direkt auf `km-gegenbuchung`; `km-dokument-foto` gibt es auf dem Desktop nicht; `km-dokumente-ansehen` trägt bei keiner Buchung mit Dokumenten oder mehreren gewählten `aria-disabled="true"`. (5) Ablage: `dragenter`/`dragover`/`drop` mit einem `DataTransfer`, das `File`-Objekte enthält; `data-ablage="ja"` wird direkt nach `dragover` gelesen. Ein Ziehen nur mit Text lädt nichts hoch und erzeugt keine Änderung; der Hinweis „Hier lassen sich nur Dateien ablegen.“ für eine Ablage mit Typ `Files` ohne Datei-Inhalt ist in Chromium nicht nachstellbar und wird nicht geprüft. (6) Kamera: ein PNG 3000×1000 wird als JPEG mit längster Kante 2400 px und gleichem Seitenverhältnis hochgeladen (Quelle `kamera`). (7) Text „Mit <n> Buchungen verknüpfen“ wird nur für n = 2 geprüft. (8) Nicht geprüft: Aussehen, Symbole, Fokus im PDF-Rahmen, Verzögerung der Suche im Verknüpfen-Dialog, Service-Worker-Liste (eigener Test der Hülle).
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 8.2, 16.4, 27.2, 28; E-196.

## E-210 Schema und Version für M18

- **Frage:** Wie wird `openapi.yaml` für M18 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.15.0; Tag `dokumente`; zwölf neue Operationen (`dokumente.md` 2.1–2.13) mit den Schemas `Dokument`, `DokumentZustand`, `Dokumenttyp`, `DokumentListe`, `DokumentAusMail`, `DokumentAenderung`, `DokumentBuchungen`, `DokumentGeloest`, `MailAnsicht`, `MailAdresse`, `MailAnhang`; Inhaltsantworten ohne JSON-Schema (`application/pdf`, `image/*`, `application/octet-stream`, `text/plain`, `text/html`). `Buchung.belege` verliert `maxItems: 0`; `Beleg` bleibt unverändert; `BuchungZustand.dokument_ids` optional; `Objektart` um `dokument`, `Objektzustand` um `DokumentZustand`; Fehlercodes `dokument_leer`, `dokument_typ_unbekannt`, `keine_mail`. In `tests/spec` prüfen `test_m6_schemas` die ersten zehn Objektarten und `test_m9_sicherung` die Pflichtschlüssel von `anzahl` ohne die Arten „nur bei Vorhandensein“ (`kredit`, `postfach`, `dokument`, `erwartung`); die exakte Versionsprüfung steht im jüngsten Schematest.
- **Begründung:** E-029, E-124: nur Ergänzungen; frühere App-Tests bleiben unverändert (`test_belege_immer_leer` legt keine Dokumente an).
- **Bezug:** E-029, E-124, E-198.

## E-211 Meilenstein-Definition „ALF-BanCo-Import und Kategorien zusammenführen“ als M19 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M19 (Feature `alfbanco-import`, kontor-app D-123 bis D-127) freigegeben und während der Übernahme eine überarbeitete Fassung abgelegt. Welche Fassung gilt, und wie wird sie übernommen?
- **Entscheidung:** Es gilt die überarbeitete Fassung (zuletzt abgelegt). Übernahme als **M19** mit Tests in `tests/app/m19/` (Marker `m19`, Hilfen `tests/hilfen/m19.py`). Abschnitte 1–6, 8 und 9 stehen wörtlich in `spec/api/alfbanco.md`, Abschnitt 7 als `oberflaeche.md` 29. Ergänzt sind `datenmodell.md` 8 (Importart `alfbanco`), `python-api.md` 19, `protokoll.md` 16, `sicherheit.md` 8 (Upload-Pfad) und `openapi.yaml` (E-215). Kein neuer fachlicher Zustand, Sicherung unverändert, Konfiguration unverändert.
- **Begründung:** Die Definition beschreibt nur neue Operationen auf bestehenden Objektarten; Protokoll und Rückgängig decken sie wie den KMyMoney-Import ab.
- **Bezug:** K 12, K 14; T 3.5–3.7, T 5, T 6; `alfbanco.md`; E-029.

## E-212 M19: Prüfmerkmale des QIF-Imports

- **Frage:** Wie prüfen die Tests den Import ohne Fixtures des Generators und ohne den Algorithmus der Kennung?
- **Entscheidung:** (1) QIF-Dateien werden im Test aus Sätzen gebaut (`tests/hilfen/m19.qif`, Kodierung und Zeilenende wählbar); das Beispiel aus 8 ist `BEISPIEL`. Die Generator-Fixtures bleiben unverändert (kleine Testdateien dürfen im Test entstehen). (2) Die Kennung wird nur über ihre Form (`alf:<konto_id>:` + 32 Hexziffern) und die Folgerungen aus 4.4 geprüft: gleiche Datei → gleiche Kennungen; Umstellen verschiedener Sätze, andere Schreibweise von Datum (`02.01.2024`/`2024-01-02`) und Betrag (`-12,34`/`-12,340`, `2.500,00`/`2500,00`) → gleiche Kennungen; eine geänderte Angabe → neue Kennung; anderes Zielkonto → andere Kennung (das Präfix genügt). (3) `multipart/form-data` wird selbst gebaut (E-208), damit `konto_id` als einfaches Textfeld und `datei` als Dateifeld bzw. als Textfeld („kein Dateifeld“) gesendet werden kann; „kein lesbares Formular“ ist ein JSON-Körper. (4) Fehlerorte werden über den Anfang von `ort` geprüft (`["body", "konto_id"]`, `["body", "datei"]`). (5) Reihenfolge der Inhaltsfehler: nach Satz, darin Datum, Betrag, Aufteilungen (3.3); Warnungen ohne Reihenfolge als Menge (4.7). (6) Dubletten: „Empfänger passend“ nach `ekey` (`datenmodell.md` 1); ein Kandidat ohne Empfänger zu einem Satz mit Empfänger ist nicht passend, also ähnlich. `extern_ids` bleiben aufsteigend sortiert (`datenmodell.md` 3), „angehängt“ heißt hinzugefügt. (7) Kategorien mit fremder bzw. `alf:`-Kennung entstehen über einen KMyMoney- bzw. früheren ALF-BanCo-Import (die REST-Anlage setzt keine `extern_id`) und werden danach umbenannt. (8) Der Zeitpunkt des Importvorgangs ist über Python im Mock-Modus `mock_heute` 12:00 UTC, über REST die Mock-Uhr; im Echtmodus liegt er zwischen den Systemzeiten vor und nach dem Aufruf.
- **Begründung:** Die Definition nennt diese Folgerungen ausdrücklich als „testbar ohne den Algorithmus“.
- **Bezug:** `alfbanco.md` 1–4, 8; `datenmodell.md` 1, 3, 10.4; E-208.

## E-213 M19: Kategorien zusammenführen – Orakel und offene Punkte

- **Frage:** Wie werden Wirkung und Antwort von `POST /api/kategorien/zusammenfuehren` unabhängig berechnet, und was bleibt offen?
- **Entscheidung:** (1) `tests/hilfen/m19.zusammenfuehren_soll` wendet je Quelle in der Reihenfolge von `quelle_ids` das bestehende Orakel für das Löschen mit Buchungen (`tests/hilfen/loeschen_orakel.py`, Variante `elternkonto`, `konflikte = behalten`) an, wobei das Ziel als Elternkonto der Quelle eingesetzt wird; Unterkategorien, Löschen der Quelle, Regeln, Standardkategorien und die Übernahme der `extern_id` folgen 5.3. Ohne `quellen_loeschen` werden nur Buchungen umgebucht. Split-Vorlagen werden einzeln geprüft (erster Teil zeigt auf das Ziel). (2) „Kreditbezug“ (5.2 Nr. 5) heißt wie in `loeschen.md` 7: Konto, Zahlungs- oder Zinskonto eines Kredits. (3) `aenderung_id = null` „wenn sich nichts geändert hat“ wird mit Quellen ohne Buchungen und `quellen_loeschen = false` geprüft. (4) Ablehnung des Rückgängig „wenn eine spätere Änderung darauf aufbaut“ wird mit einer späteren Änderung einer umgebuchten Buchung geprüft (409 `rueckgaengig_konflikt`, `protokoll.md` 6.1); ob ein späterer Import mit der übernommenen Kennung allein schon einen Konflikt nach 6.1 erzeugt, hängt von der Zustandsprüfung ab und wird nicht festgelegt. (5) Die Salden-Folgerung (5.3) wird mit den eigenen Salden (`saldo`, nicht `saldo_gesamt`) geprüft.
- **Begründung:** Die Definition beschreibt die Wirkung als „je Quelle wie `POST /api/konten/{id}/loeschen` … mit dem gewählten Ziel“; das vorhandene Orakel bildet genau diese Regeln ab.
- **Bezug:** `alfbanco.md` 5, 6; `loeschen.md` 3, 7; `protokoll.md` 6.1.

## E-214 M19: Prüfmerkmale der Oberfläche

- **Frage:** Wie werden Import-Seite, Mehrfachauswahl und Dialog (`oberflaeche.md` 29) geprüft?
- **Entscheidung:** (1) Import: Reihenfolge der Optionen von `import-format` beginnt mit `kmymoney`, `gnucash`, `alfbanco`; `import-konto` enthält nach der leeren Option genau die Bestandskonten (Wurzelkonten, Text = Name); ohne Datei bzw. ohne Konto je eine Meldung `data-art="fehler"` und keine schreibende Anfrage (Mitschnitt). (2) Mehrfachauswahl: Klicks auf den Namen des Eintrags (Text des Eintrags); geprüft werden Klick, Strg-Klick, Umschalt-Klick (ersetzt), Strg+Umschalt-Klick (ergänzt), Leertaste und Esc über `aria-selected`. „Bleibt beim Neuzeichnen erhalten“ und der Klick auf den Aufklappschalter haben kein festgelegtes Merkmal und werden nicht geprüft. (3) Dialog: Optionen in Baumfolge ohne die Quellen, Unterkategorien mit beiden Namen im Text, Einnahmen mit „ (Einnahme)“; der Probelauf wird im Mitschnitt mit `trocken = true` nachgewiesen, `zusammenfuehren-vorschau` über `data-anzahl` und den Satz „<n> Buchungen werden auf „<Zielpfad>“ umgebucht“. Der echte Lauf ist genau eine Anfrage ohne `trocken = true`. (4) Rückgängig mit Strg+Z auf der Kategorienseite.
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 8.2, 13.1, 13.7, 29; E-187, E-209.

## E-215 Schema und Version für M19

- **Frage:** Wie wird `openapi.yaml` für M19 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.16.0; neue Pfade `POST /api/import/alfbanco` (multipart mit `datei` und `konto_id`) und `POST /api/kategorien/zusammenfuehren` (Schemas `KategorienZusammenfuehren`, `ZusammenfuehrenErgebnis`); `ImportErgebnis.format` um `qif`, `Importvorgang.art` um `alfbanco`; keine neuen Fehlercodes. `test_m4_schemas_rueckwaertskompatibel` prüft die ersten beiden Werte von `Importvorgang.art`.
- **Begründung:** E-029, E-124.
- **Bezug:** E-029, E-124, E-210.

## E-216 Meilenstein-Definition „Mail-Abgleich: erwartete Zahlungen“ als M20 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M20 (Feature `mail-abgleich`, kontor-app D-128) freigegeben; sie setzt M18 voraus. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M20** mit Tests in `tests/app/m20/` (Marker `m20`, Hilfen `tests/hilfen/m20.py`). Abschnitte 1–7 und 9–11 stehen wörtlich in `spec/api/erwartungen.md` (dazu die Präzisierung 12, E-217), Abschnitt 8 als `oberflaeche.md` 30. Ergänzt sind `python-api.md` 20 (`mail_abgleich`, `mail_abgleich_frist_tage`), `betrieb.md` 3 (`KONTOR_MAIL_ABGLEICH=1`, Frist nur auskommentiert), `protokoll.md` 17 (Quelle `mail`, Objekt `erwartung`, sieben Aktionen), `benachrichtigungen.md` 9 (`erwartung_ueberfaellig`), `sicherung.md` 2.8 und `openapi.yaml` (E-220). Nicht enthalten (Definition): Serien regelmäßiger Mail-Einkäufe, Kachel auf der Übersicht.
- **Begründung:** Neuer fachlicher Zustand gehört zu Protokoll und Sicherung (CLAUDE.md); die Definition legt beides fest.
- **Bezug:** K 1, K 10, K 14; T 3.5, T 3.6, T 17, T 21; `erwartungen.md`; E-029, E-118, E-206.

## E-217 M20: Protokollform der Erwartung und Inhaltsprüfsumme

- **Frage:** Die Definition legt die Protokollform von `erwartung` nicht fest, verlangt aber „kein Feld `schluessel` in Antworten“ und für die Sicherung alle Felder „einschließlich des internen Schlüssels“. Was steht in den Einträgen des Änderungsprotokolls, und womit wird die Inhaltsprüfsumme berechnet?
- **Entscheidung:** Protokollform = Felder aus 3 ohne die abgeleiteten (`zugeordnet`, `offen_betrag`, `ueberfaellig`, `vorzeichen_betrag`) und ohne die Detailfelder (`erwartungen.md` 12, Schema `ErwartungZustand`, `additionalProperties: false`). Einträge des Protokolls sind Antworten; der interne Schlüssel steht deshalb nicht darin, ebenso nicht in der Inhaltsprüfsumme, die nach `sicherung.md` 3.3 aus den Protokollformen der REST-Schnittstelle berechnet wird. Er ist nur in `kontor.sqlite` der Sicherung enthalten. `tests/hilfen/m20.bestand` = Bestand aus M18 plus je Erwartung (alle Zustände über `GET /api/erwartungen`) diese Form; Sortierung der Einträge mit `erwartung` nach `dokument`.
- **Begründung:** `protokoll.md` 2 („aus den REST-Antworten eindeutig ableitbar; abgeleitete Zählungen gehören nicht dazu“) und Definition 3 („Kein Feld `schluessel` in Antworten“). Ein Rückgängig kann den Schlüssel aus den Feldern bzw. dem gespeicherten Zustand wiederherstellen; das ist Sache der Implementierung.
- **Bezug:** `erwartungen.md` 3, 7, 12; `protokoll.md` 2, 17; `sicherung.md` 2.8, 3.3.

## E-218 M20: Auslegung offener Punkte von Erkennung, Zuordnung und REST

- **Frage:** Wo lässt die Definition Spielraum, und wie wird geprüft?
- **Entscheidung:** (1) Mails werden über eine Mock-Datendatei je Test eingespeist (`tests/hilfen/m20.mock_datei`, Definition 10; kleine Testdaten, keine Generator-Fixtures); Echtmodus mit Rohfassung über die IMAP-Attrappe mit eigenem Postfach. Absender nur unter `amazon.example.invalid`/`paypal.example.invalid` und `example.invalid`. (2) `KonfigurationsFehler` trägt `feld` bzw. `variable` in `details` (`python-api.md` 2). Ob Leerraum um den Wert der Umgebungsvariable entfernt wird, wird nicht geprüft. (3) Erkennung: Stichwörter werden in der angegebenen Reihenfolge versucht; bei PayPal wird die Kennung ohne Rücksicht auf Groß/Klein verglichen; `mails` wird in der Reihenfolge der Verarbeitung (empfangen, Spiegel-ID) geprüft. (4) Die Zählung `ergaenzt` des Abgleichs bei einer Stornierungsmail (die die `mails` ebenfalls ergänzt) ist nicht festgelegt (1 oder 2 im Test). (5) „Nach jedem Synchronisationslauf mit Endstatus“ wird mit einem erfolgreichen Mock-Lauf geprüft, dessen Umsatz die Bestellnummer trägt: direkt danach ist die Erwartung erfüllt. (6) Kandidaten: „Empfängername“ ist der Name des Empfängers der Buchung; „Bestandskonto“ wie `datenmodell.md` 2 (`girokonto`, `sparkonto`, `kreditkonto`). (7) Dokumente beim Zuordnen: der Dateiname der Mail ist Betreff (höchstens 196 Zeichen) + `.eml` (E-208); ein Dokument, das beim Lösen entfällt, verschwindet aus `dokument_ids` (Definition 5.3 „bis es entfällt“ und „verwaiste Bezüge“). (8) Prüfreihenfolgen in 6.2–6.4 werden je Paar der Reihenfolge mit Körpern geprüft, die beide Fehler enthalten. (9) Benachrichtigung: Titel, Schlüssel, Link und Händler im Text werden geprüft, die Priorität nicht (kein Feld der Antwort). Gelesen markieren über `POST /api/benachrichtigungen/{id}/gelesen`. (10) Sicherung: `schemaversion ≥ 5` (die Definition nennt 5; spätere Meilensteine dürfen erhöhen); Sicherungen der Versionen 1–4 lassen sich ohne Kenntnis des Schemas nicht bauen und werden nicht geprüft, ebenso nicht manipulierte ungültige Werte (wie E-207 für Dokumente).
- **Begründung:** Keine Festlegung über die Definition hinaus; wo sie mehrdeutig ist, prüfen die Tests nur die gemeinsame Aussage.
- **Bezug:** `erwartungen.md` 1–7, 9, 10; `python-api.md` 2; `datenmodell.md` 2; E-208.

## E-219 M20: Prüfmerkmale der Oberfläche

- **Frage:** Wie wird die Seite `/erwartet` (`oberflaeche.md` 30) geprüft?
- **Entscheidung:** Nur Desktop. (1) `data-betrag` der Summe darf am Element `erwartet-summe` selbst oder an genau einem Element darin stehen. (2) Chips über `aria-pressed`, Zeilen über ihre Reihenfolge in `erwartet-tabelle`, Abfrageteil der Adresse für `grund` und `suche`. (3) „heute“ der Chips „Fällig“: die Browser-Uhr wird im Test auf die App-Uhr gesetzt (`page.clock`), weil die Definition nicht sagt, welche Uhr gemeint ist. (4) Ob der Detail-Dialog nach „Zuordnen“ oder „Lösen“ offen bleibt, ist nicht festgelegt; der Test öffnet ihn danach erneut über `/erwartet?id=<id>`. (5) Befehlspalette: Position des Eintrags über die Beschriftungen der Nachbarn. (6) Kontextmenü: Menge der Einträge je Zustand und Grund, ohne Reihenfolge. (7) Nicht geprüft: mobile Ansicht, Tastaturbedienung der Zeilen, Bestätigung beim Löschen, Texte außer den genannten.
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 12.3, 27, 30; E-209.

## E-220 Schema und Version für M20

- **Frage:** Wie wird `openapi.yaml` für M20 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.17.0; Tag `erwartungen`; zehn neue Operationen; Schemas `ErwartungGrund`, `ErwartungMail`, `ErwartungZustand`, `Erwartung`, `ErwartungDetail`, `ErwartungListe`, `ErwartungNeu`, `ErwartungAenderung`, `ErwartungZustandWechsel`, `ErwartungBuchungen`, `Kandidat`, `KandidatListe`, `AbgleichErgebnis` (vollständig oder `{}`); `Aenderungsquelle` um `mail`, `Objektart` um `erwartung`, `Objektzustand` um `ErwartungZustand`, `Benachrichtigung.art` um `erwartung_ueberfaellig`; neue Fehlercodes `mail_abgleich_aus`, `erwartung_aus_mail`, `zustand_unzulaessig`, `erwartung_nicht_offen`, `zuordnung_ungueltig`, `buchung_bereits_zugeordnet`, `zuordnung_zu_hoch`. In `tests/spec` prüfen frühere Schematests nur noch Präfixe bzw. Enthaltensein der Aufzählungen `Aenderungsquelle`, `Objektart` und `Benachrichtigung.art`; die exakte Versionsprüfung steht in `test_m20_schemas`.
- **Begründung:** E-029, E-124.
- **Bezug:** E-029, E-124, E-210, E-215.

## E-221 Meilenstein-Definition „Berichte: Einzelbuchungen, Zoom, Tooltip; Sprungziel mittig“ als M21 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M21 (Features `diagramm-dunkel` und Sprungziel, kontor-app D-128/D-129) freigegeben. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M21**, Spezifikation `oberflaeche.md` 31 (Hinweis in 26.4: Sprungziel in die vertikale Mitte), Tests in `tests/app/m21/` (Marker `m21`, Hilfen `tests/hilfen/m21.py`). Reine Oberfläche: `openapi.yaml` unverändert (2.17.0), kein Eintrag in `protokoll.md` 4, nichts in der Sicherung, keine Konfiguration. Kein Test ist `kern`; die Selbstprüfung erhält keine M21-Teile (wie E-202): Plotly-Zoom, Detailzeilen und Mittigkeit in der kleinen Referenz-Seite nachzubauen prüfte vor allem die Referenz.
- **Begründung:** Die Definition nennt ausdrücklich „nur Browsertests, keine `kern`-Tests“.
- **Bezug:** K 5, K 11; T 11, T 19; `oberflaeche.md` 13.6, 25.7, 26.4, 27.2, 31; E-202.

## E-222 M21: Prüfmerkmale

- **Frage:** Wie werden Einzelbuchungen, Zoom, Themen und Sprungziel geprüft?
- **Entscheidung:** (1) Datenzeilen sind die Zeilen des `tbody` der Berichtstabelle selbst (ohne die eingebetteten Tabellen der Detailzeilen); die Tabelle der Einnahmen/Ausgaben wird über ihre Knöpfe `bericht-ea-aufklappen-<i>` angesprochen. (2) Erwartete Buchungen je Zeile aus den Stichtagen von `GET /api/berichte/kontostand` bzw. den Zeiträumen von `GET /api/berichte/einnahmen-ausgaben` und den im Test angelegten Buchungen (mindestens ein Split auf einem gewählten Konto, ohne Umbuchungen bei Einnahmen/Ausgaben). (3) Geprüft: Knopf in der ersten Zelle ohne Textinhalt, `aria-expanded`, `aria-label`, `data-offen`, Detailzeile erst nach dem ersten Aufklappen, direkt nach der Datenzeile, eine Zelle über alle Spalten (Summe der `colSpan`), Reihenfolge und `data-id` der Zeilen, `data-betrag` (Summe der Splits auf den gewählten Konten), Empfänger bzw. „–“, Links je Konto mit `href` und gewählten Konten zuerst, Hinweis „Keine Buchungen in diesem Zeitraum.“ (Klasse `leer`), Abfragen je gewähltem Konto mit `von`, `bis`, `sortierung=datum`, `pro_seite=500`. Der Hinweis „Nur die ersten 500 Buchungen je Konto.“ und die Fehlermeldung einer gescheiterten Abfrage werden nicht geprüft (über 500 Buchungen in einem Zeitraum wären für einen Browsertest unverhältnismäßig). (4) Zoom: `Plotly.relayout` auf dem Element `bericht-diagramm` (Klasse `js-plotly-plot`) mit `xaxis.range` = zwei ISO-Daten; der Hinweis wird mit genau diesen Daten im Format TT.MM.JJJJ verglichen; Zoom der Einnahmen/Ausgaben wird nicht eigens geprüft. (5) Themen: nur, dass beide Diagramme im hellen und dunklen Farbschema ohne Seitenfehler zeichnen (Fixture `neue_seite`). (6) Sprungziel: Lage der Zeile zum nächsten senkrecht rollbaren Vorfahren (sonst Fenster), Abstand der Mitten höchstens eine Zeilenhöhe; über `?buchung=` (Ziel auf der zweiten Seite, Desktop und mobil) und über „Gehe zur Gegenbuchung“; waagerecht nur geprüft, dass die Scrollposition 0 bleibt; mobil liegt die Zeile nicht unter einer sichtbaren `mehrfach-leiste`. Hervorhebung (ca. 2 s) wird nicht geprüft.
- **Begründung:** Nur festgelegte Merkmale (`oberflaeche.md` 1); die Definition nennt die Prüfwege für Zoom und Mitte selbst.
- **Bezug:** `oberflaeche.md` 1, 13.6, 25.7, 26.4, 27.2, 31; `berichte.md` 2, 3; E-196, E-200.

## E-223 Meilenstein-Definition „Buchungsliste: Spaltenbreiten und Markierung“ als M22 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M22 (Feature `spalten-markierung`, kontor-app D-130) freigegeben; 3.2 setzt M20 voraus. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M22**, Spezifikation `oberflaeche.md` 32, Tests in `tests/app/m22/` (Marker `m22`). Reine Oberfläche: `openapi.yaml` unverändert (2.17.0), kein Protokoll, keine Sicherung (die Breiten sind Gerätezustand wie Layout und Tabs, E-141, E-201). Kein Test ist `kern`, keine Referenzteile und Mutanten (wie E-202).
- **Begründung:** Die Definition nennt „nur Browsertests, keine `kern`-Tests“.
- **Bezug:** K 5, K 14; T 19; `oberflaeche.md` 7.2, 22.2, 27.1, 32; E-141, E-201, E-202.

## E-224 M22: Prüfmerkmale

- **Frage:** Wie werden Trenner, Breiten, Speicherung, Markierung und Zusatzmarken geprüft?
- **Entscheidung:** (1) Spaltentitel im `aria-label` ist der Anfang des Textes der Kopfzelle (der Kopf darf zusätzlich ein Sortiersymbol tragen). (2) Breiten werden als gerundete `getBoundingClientRect().width` von Kopfzelle und allen Zellen `[data-feld]` der Spalte gemessen (Toleranz 1 px). Ziehen mit der Maus über `mouse.down/move/up` in Schritten; die untere Grenze mit einer Spalte, deren Ziehen über die Grenze hinausgeht, die obere Grenze in einem 2600 px breiten Fenster (eine Mausbewegung bleibt im Fenster). Jede Spalte muss sich um 30 px verbreitern und wieder verschmälern lassen. (3) „Kein Text abgeschnitten“: für jede Zelle der Spalte `scrollWidth ≤ clientWidth + 1`. (4) Kopfmenü über Rechtsklick auf die Kopfzeile (Element `role="row"` des Kopfs); „kein Buchungsmenü“ = keiner der Einträge `km-loeschen`, `km-mehrfach`, `km-gegenbuchung`. (5) Speicherung: Schlüssel `kontor.spalten` vorhanden, nach Neuladen und in einem anderen Bestandskonto gleiche Breite, Kategorieansicht unverändert; ungültiger Inhalt bzw. werfende `getItem`/`setItem` für diesen Schlüssel → Ziehen funktioniert ohne Seitenfehler. (6) Markierung: Unkategorisiert-Buchungen entstehen durch einen Mock-Abruf, Status über `mehrfach/aendern`; abgestimmt über eine Abstimmung auf einem eigenen Konto; die drei Werte unterscheiden sich in `background-image` + `background-color` der Zeile. „Folgt Änderungen“: nach einer Änderung über REST zeigt die neu geladene Liste den neuen Wert. (7) Zusatzmarken: `data-wiederkehrend`/`data-mail`, Text der Empfängerzelle unverändert, Titel exakt nach 3.1–3.3 (Grundtext, Händler, Kennung durch Leerzeichen getrennt); das Pseudo-Element selbst wird nicht geprüft. Fehlschlagende Abfragen von `GET /api/wiederkehrend` bzw. `GET /api/erwartungen` werden nicht nachgestellt; geprüft ist nur, dass ohne Mail-Abgleich keine Marke erscheint.
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 7.2, 8, 27.1, 32; E-201.

## E-225 Selbstprüfung für M18 bis M22

- **Frage:** Brauchen die neuen `kern`-Tests von M18, M19 und M20 Referenzteile und Mutanten in der Wegwerf-Referenz?
- **Entscheidung:** In diesem Auftrag erhalten M18, M19 und M20 **keine** Referenzteile und keine Mutanten. Die Selbstprüfung lässt ihre Kern-Tests aus (`OHNE_REFERENZ = ("m18", "m19", "m20")`, Markerausdruck `kern and not (m18 or m19 or m20)` in `tests/_selbstpruefung/__main__.py`); Referenzlauf und Erweiterungslauf bleiben für alle übrigen Kern-Tests unverändert grün. M21 und M22 haben keine Kern-Tests (E-221, E-223). Abnahme von M18–M20 ist der Lauf `python -m pytest --voll -m "m18 or m19 or m20"` gegen die Anwendung. Stattdessen sind die Erwartungen dieser Tests unabhängig abgesichert: eigene Fassungen der Regeln in den Hilfen (Typerkennung und Dateiname in `tests/hilfen/m18.py`, Bestand mit Dokumenten und Erwartungen, das Orakel für das Zusammenführen auf Grundlage von `loeschen_orakel`), Beispiele der Definitionen als feste Erwartungen und ein Probelauf gegen den Feature-Stand, dessen Abweichungen einzeln gegen die Definition geprüft wurden (ERGEBNIS.md). Eine Referenz kann ein späterer Auftrag nachtragen; dann wird der jeweilige Meilenstein aus `OHNE_REFERENZ` entfernt.
- **Begründung:** Jeder der drei Meilensteine wäre in der Referenz eine zweite Umsetzung eines großen Features (MIME-Zerlegung und HTML-Entschärfung, QIF-Leser mit Kategorienzuordnung und Zusammenführen, Mail-Erkennung mit Zuordnung, Sicherung). Das ist im Verhältnis zum Nutzen der Selbstprüfung unverhältnismäßig; ohne Auslassen würde der Referenzlauf rot und die Selbstprüfung für alle früheren Meilensteine wertlos.
- **Bezug:** CLAUDE.md (Selbstprüfung); E-149, E-188, E-202.

## E-226 Inhaltsprüfsumme im M20-Rundreisetest mit allen vorhandenen Objektarten (W-011)

- **Frage:** Der Implementierungs-Thread meldet (W-011): `test_sicherung_rundreise` (M20) berechnet die Inhaltsprüfsumme über die M9-Objektarten plus `dokument`/`erwartung`, lässt aber `postfach` weg, obwohl der Test ein Postfach anlegt.
- **Entscheidung:** Der Einwand ist berechtigt. Nach `sicherung.md` 2.5–2.8 (E-109, E-118) gehört jede Objektart ab M5 (`kredit`, `postfach`, `dokument`, `erwartung`) genau bei Vorhandensein in `anzahl` und Inhaltsprüfsumme. Der Test nimmt jetzt alle vorhandenen dieser Arten auf; die übrigen Aussagen bleiben unverändert.
- **Begründung:** Testfehler; die Spezifikation war eindeutig.
- **Bezug:** `sicherung.md` 2.5–2.8, 3.3; E-109, E-118, E-217.

## E-227 M22: Trenner vor dem Ziehen in den sichtbaren Bereich rollen (W-012)

- **Frage:** Der Implementierungs-Thread meldet (W-012): `test_jede_spalte_laesst_sich_ziehen` zieht beim Zurückziehen der Spalte `kategorie` an einem Trenner, der nach dem Verbreitern rechts außerhalb des sichtbaren Bereichs der waagerecht blätternden Liste liegt; an dieser Stelle liegt der Größengriff des Detailpanels.
- **Entscheidung:** Der Einwand ist berechtigt. Die Definition verlangt nicht, dass alle Trenner ohne Blättern sichtbar sind (32.1: „Ist die Summe der Breiten größer als die Breite der Liste, wird die Liste waagerecht geblättert“). Die Testhilfe `_ziehen` rollt den Trenner vor jedem Ziehen in den sichtbaren Bereich (`scroll_into_view_if_needed`); die Aussagen der Tests bleiben unverändert. Zugleich blenden die M19-Hilfen `zaehler` und `ohne_listen` das Feld des Erweiterungslaufs aus (E-124), damit `KONTOR_TESTS_ZUSATZFELDER=1` grün bleibt.
- **Begründung:** Testfehler; Bedienung wie ein Mensch (erst blättern, dann ziehen).
- **Bezug:** `oberflaeche.md` 32.1; E-124, E-224.

## E-228 Meilenstein-Definition „Geheimnisse mit dem Login-Passwort geschützt, gemerkte Bank-PIN, Gmail mit App-Passwort“ als M23 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M23 (Features `geheimnisse` und `gmail-app-passwort`, kontor-app D-129/D-130) freigegeben. Sie ändert bestehende Verträge. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M23** mit Tests in `tests/app/m23/` (Marker `m23`, Hilfen `tests/hilfen/m23.py`). Abschnitte 1–7, 9 und 10 stehen wörtlich in `spec/api/geheimnisschutz.md` (dazu die Präzisierungen 11, E-229), Abschnitt 8 als `oberflaeche.md` 33. Ausdrücklich geänderte Verträge: (a) K 13 und `mail.md` 3.2 – „nur XOAUTH2, nie `LOGIN`“ gilt nur für Postfächer ohne App-Passwort; ein Postfach mit App-Passwort meldet sich mit `LOGIN` an (Hinweis in `mail.md`); (b) `geheimnisse.md` 4 – neue Namen `bank_pin` und `mail_passwort:<adresse>` (nicht über REST ansprechbar; Hinweis in `geheimnisse.md` 4); (c) `synchronisation.md` 12 – die gemerkte PIN wird unter dem Schutz verschlüsselt gespeichert (Ergänzung dort); (d) `betrieb.md` 4.1 – `LimitCORE=0` in `kontor.service`. Ergänzt sind außerdem `sicherheit.md` 4.9, `python-api.md` 14.2, `protokoll.md` 18 (kein Protokoll), `sicherung.md` 2.6 (nie in der Sicherung) und `openapi.yaml` (E-232). Frühere Tests bleiben unverändert (E-029): Sie schalten den Schutz nie ein, setzen kein App-Passwort, `bank_pin` bleibt über `PUT /api/geheimnisse/{name}` 404, und `LOGIN` bleibt für Postfächer ohne App-Passwort ein Verstoß der IMAP-Attrappe. Kein neuer fachlicher Zustand: Schutz, gemerkte PIN und App-Passwörter sind Betriebszustand.
- **Begründung:** Die Definition legt die Vertragsänderungen selbst fest (Abschnitte 1, 6, 7); ohne eingeschalteten Schutz ist alles wie bisher.
- **Bezug:** K 6, K 13; T 16, T 18; `geheimnisschutz.md`; E-029, E-117, E-124, E-125.

## E-229 M23: Prüfmerkmale von REST, Python und Betrieb

- **Frage:** Wo lässt die Definition Spielraum, und wie wird geprüft?
- **Entscheidung:** (1) Die Tests setzen `anmeldung` stets ausdrücklich (meist `False` mit eingerichtetem Passwort, für Login und Passwortänderung `True` über `tests/hilfen/m7.py`); der Anmeldelauf (E-125) verändert sie daher nicht. (2) Neustart = neue `Api` auf derselben Konfiguration; „jede Instanz hat ihren eigenen Sperrzustand“ wird mit zwei gleichzeitig lebenden Instanzen geprüft; „Login entsperrt“ mit einem zweiten Client derselben Instanz; „Neustart mit gültiger Sitzung bleibt gesperrt“ mit dem Cookie einer früheren Instanz. (3) „Werte bleiben erhalten“ wird über die Wirkung geprüft: gemerkte PIN (Mock-Bank mit `bank.pin`, Lauf ohne Eingabe erfolgreich), App-Passwort (Abruf mit `LOGIN` gegen die Attrappe) – nie über eine Antwort. (4) „Zurücksetzen ohne altes Passwort“ (2.4) umfasst `kontor.anmeldung.passwort_setzen` und die Kommandozeile (`geheimnisschutz.md` 11): sonst bliebe der Schutz mit einer Hülle aktiv, die das neue Passwort nicht öffnet, und `huelle_unlesbar` wäre ohne Manipulation erreichbar, was die Definition ausschließt. Die Anzahl in der Ausgabe der Kommandozeile wird nur als enthaltene Ziffer geprüft. (5) Bremse: mit `anmeldung_fehlversuche = 2`; geprüft werden 403, Rücksetzen durch ein richtiges Passwort, 429 mit `Retry-After ≥ 1` für alle drei Endpunkte, Validierung vor der Bremse, „nicht eingerichtet“ vor dem Passwortvergleich und der gemeinsame Zähler mit `POST /api/anmeldung`. (6) `pin_gemerkt` wird nur im entsperrten Zustand geprüft (gesperrt ist es nicht festgelegt). (7) App-Passwort: Erfolg über die Befehlsfolge der Sitzung (`LOGIN`, `EXAMINE`, `LOGOUT` ohne `CAPABILITY`/`ID`/`NOOP`), `angemeldet_am` zwischen Systemzeiten vor und nach dem Aufruf; `mail_verbindung` über Abbruch nach dem Gruß und einen nicht lauschenden Port; bei Fehlern wird `LOGOUT` nicht verlangt. Nicht lesbares App-Passwort (anderer Systemschlüssel): kein `LOGIN`, Ergebnis nicht `erfolgreich`, ein gemeldeter Fehlercode ist `mail_anmeldung_fehlt` (ob als `fehlgeschlagen` oder `anmeldung_erforderlich`, lässt 6.3 offen). Ob `anmeldung_nr` durch ein App-Passwort steigt, ist nicht festgelegt und wird nicht geprüft. (8) Geheimnisse nirgends: Login-Passwort, falsches Passwort, PIN, App-Passwort (mit und ohne Leerraum) und Client-Secret in Antworten, Logs (alle Logger auf `DEBUG`, `imaplib` schreibt in Python 3.13 nicht über `logging`), stdout/stderr, Datenbankdateien (UTF-8, UTF-16) und Sicherung. `repr()` eines Plugins wird nicht geprüft (kein Zugriff über die Schnittstelle ohne Anwendungsinterna). (9) `RLIMIT_CORE` des Prozesses wird nicht geprüft (Definition 7), nur die Unit-Datei. (10) Sicherung: `anzahl` und `inhalt_sha256` gleich vor und nach Einschalten und Merken; Einspielen in eine geschützte, gesperrte Instanz ändert Schutz und Geheimnisse nicht.
- **Begründung:** Nur festgelegte Merkmale; wo die Definition mehrdeutig ist, prüfen die Tests die gemeinsame Aussage.
- **Bezug:** `geheimnisschutz.md` 1–7, 9–11; `sicherheit.md` 4.5; `mail.md` 6.2; E-125, E-126.

## E-230 M23: Betriebsart App-Passwörter der IMAP-Attrappe

- **Frage:** Wie wird die IMAP-Attrappe für `LOGIN` erweitert, ohne die M6-Prüfung „nie `LOGIN`“ zu schwächen?
- **Entscheidung:** `ImapAttrappe(passwoerter={adresse: passwort})` beantwortet `LOGIN` für genau diese Adressen (Vergleich nach `casefold()`) mit `OK` bei passendem Passwort, sonst `NO [AUTHENTICATIONFAILED]` (ohne Verstoß) und zeichnet `(adresse, erfolg)` in `logins` auf. `LOGIN` für jede andere Adresse und jedes `LOGIN` ohne diese Betriebsart bleiben Verstöße (M6 unverändert). `login_deaktiviert = True` meldet `LOGINDISABLED` in den Fähigkeiten; dann ist jedes `LOGIN` ein Verstoß. Ein Attrappentest prüft die Betriebsart mit `imaplib`.
- **Begründung:** Definition 6.5.
- **Bezug:** `mail.md` 8; `geheimnisschutz.md` 6.5; E-028, E-122.

## E-231 M23: Prüfmerkmale der Oberfläche

- **Frage:** Wie werden Sperrleiste, Entsperren-Dialog, Einstellungen, PIN-Dialog und Postfachseite (`oberflaeche.md` 33) geprüft?
- **Entscheidung:** Nur Desktop. (1) Das Login-Passwort ist das der Browsertests (`tests/hilfen/m8.PASSWORT`), bei abgeschalteter Anmeldung über `passwort_setzen` eingerichtet. Weil die Anmeldung des Browserkontexts die Instanz entsperrt, sperrt der Test erst danach über REST. (2) „Gibt es nicht bzw. `hidden`“ = nicht sichtbar. Lage „über der Tab-Leiste“ über die Dokumentreihenfolge. „Alle 60 s“ wird nicht geprüft. (3) Leeres Passwort im Dialog: keine Anfrage, Dialog bleibt offen mit Text; falsches Passwort: genau eine Anfrage, Feld geleert, Dialog offen; richtig mit Enter: Dialog geschlossen, Erfolgsmeldung „Entsperrt.“. (4) Einstellungen: sichtbare Knöpfe je Zustand genau nach 33 (übrige nicht sichtbar); „nach dem PIN-Abschnitt“ über die Dokumentreihenfolge zum ersten PIN-Element der Seite. (5) PIN-Dialog: `pin-merken` sichtbar genau bei Schutz ein und entsperrt; angehakt genau `PUT /api/sync/pin/gemerkt` und kein `PUT /api/sync/pin`. (6) Postfachseite im Echtmodus gegen die IMAP-Attrappe: Ordneränderung erst `PATCH`, dann `PUT …/app-passwort`; Erfolgsmeldung enthält die Zahl der Nachrichten; Fehler als Text in `postfach-app-ergebnis` nach der Antwort des Servers; Abschnitt vor dem OAuth2-Knopf `postfach-anmelden`. Nach einem Fehler muss sich mit korrigierten Angaben erneut speichern lassen: Das Leeren des Feldes „nach dem Absenden“ dient der neuen Eingabe, und die Definition nennt keinen Zustand, in dem der Knopf dauerhaft gesperrt bleibt (eigener Test).
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 25.5, 33; E-187, E-219.

## E-232 Schema und Version für M23

- **Frage:** Wie wird `openapi.yaml` für M23 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.18.0; neue Operationen `GET`/`POST /api/geheimnisse/schutz`, `POST /api/geheimnisse/schutz/ausschalten`, `POST /api/geheimnisse/entsperren`, `POST /api/geheimnisse/sperren`, `PUT`/`DELETE /api/sync/pin/gemerkt`, `PUT`/`DELETE /api/mail/postfaecher/{postfach_id}/app-passwort`; Schemas `GeheimnisSchutz`, `SchutzPasswort` (1–4096), `AppPasswortEingabe` (1–256), `AppPasswortErgebnis`; neue Fehlercodes `geheimnisse_gesperrt`, `schutz_bereits_aktiv`, `schutz_nicht_aktiv`, `huelle_unlesbar`; 409 `geheimnisse_gesperrt` zusätzlich bei `PUT /api/geheimnisse/{name}` und `POST /api/mail/abruf` (Statuscode schon vorhanden). 403 und 429 der Passwort-Endpunkte kommen aus `x-allgemeine-antworten` (E-127). Die exakte Versionsprüfung steht in `test_m23_schemas`; `test_m20_schemas` prüft nur noch `≥ 2.17.0`.
- **Begründung:** E-029, E-124; bestehende Schemas unverändert.
- **Bezug:** E-029, E-124, E-127, E-220.

## E-233 Meilenstein-Definition „Mail-Abgleich: Serien, Kachel, Kategorie bei Erstattungen, eingebaute Mock-Mails“ als M24 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M24 (Feature `mail-abgleich`, Fortsetzung; kontor-app D-131 und D-139) freigegeben. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M24** mit Tests in `tests/app/m24/` (Marker `m24`, Hilfen `tests/hilfen/m24.py`). Abschnitte 1, 3, 5 und 6 stehen als `erwartungen.md` 13.1–13.4, Abschnitte 2 und 4 als `oberflaeche.md` 34; `protokoll.md` 19 hält fest, dass die Umbuchung bei Erstattungen zur selben Änderung gehört. Rückwärtskompatibel (E-029): Ohne `grund=serie`/`serien=ja` bleibt jede Antwort aus M20 gleich; die M20-Tests bleiben unverändert. Kein neuer fachlicher Zustand, Sicherung unverändert. `openapi.yaml` E-237. Die Abweichungen der Definition gegenüber D-131/D-139 (Abschnitt 6) gelten wie dort beschrieben.
- **Begründung:** Die Definition nennt Abschnitte 1 und 3 `kern`, 2 und 4 Browsertests, 5 einen REST-Test ohne `kern`.
- **Bezug:** K 1, K 9, K 14; T 3.5, T 3.6, T 19; `erwartungen.md` 13; `wiederkehrend.md` 2; E-029, E-216.

## E-234 M24: Prüfmerkmale von Serien und Kategorie bei Erstattungen

- **Frage:** Wie werden Serieneinträge und die Umbuchung bei Erstattungen unabhängig geprüft?
- **Entscheidung:** (1) Erwartete Serieneinträge werden aus dem Buchbestand (REST-Darstellung von Buchungen, Konten, Krediten) mit der Referenzkette `tests/hilfen/wiederkehrend_orakel.uebersicht` am Stichtag „heute der App-Uhr“ berechnet und nach 13.1.3 in die Felder übertragen (`tests/hilfen/m24.soll_serien`), nie aus `GET /api/wiederkehrend` übernommen. Das Szenario hat Serien mit gleichbleibenden Beträgen (aktiv Ausgabe, aktiv Einnahme, ausbleibend, beendet), damit es von späteren Filtern der Kette (M25) unabhängig bleibt. (2) Reihenfolge: nur „nach `frist` nicht absteigend“ (13.1.4), Einträge als Menge nach `id`; `anzahl`, `summe_offen`, `ueberfaellig` unabhängig nachgerechnet. (3) Validierung: `serien` mit anderem Wert als `ja`/`nein` → 422 mit `ort` beginnend `["query", "serien"]`; `grund=serien` → 422. (4) Auslassen (13.1.2): mit einer manuellen Erwartung, der die letzte bzw. eine frühere Buchung der Serie zugeordnet wird, und einer zweiten (erfüllten) für eine Einnahmeserie. (5) Nicht abrufbar: alle sieben Pfade mit `serie:…` → 404 `nicht_gefunden` mit der Meldung „Der angeforderte Pfad existiert nicht.“. (6) Keine Wirkung: zwei Abgleiche ohne Änderung im Protokoll, keine `erwartung_ueberfaellig` für eine überfällige Serie, `anzahl` und `inhalt_sha256` der Sicherung unverändert. (7) Erstattung: Das technische Konto „Unkategorisiert“ entsteht durch einen Mock-Lauf; ursprüngliche Buchung und Gutschrift werden danach über REST gebucht (Split auf dieses Konto). Geprüft werden Umbuchung (Betrag und Status unverändert), dieselbe Änderung (Einträge Erwartung, Buchung und ggf. die beim Zuordnen angelegten Dokumente der Mail nach M20 5.3), Rückgängig und Wiederholen, automatischer Weg (`erwartung_erkennen`), Lösen ohne Rücksetzen, „kleinste ID“, und je verletzter Voraussetzung keine Umbuchung bei erfolgter Zuordnung (kein Bezug, Bestellung ohne Buchung, zwei Kategorien, drei Splits, schon kategorisiert, K = „Unkategorisiert“, schon zugeordnete Buchung, anderer Grund). Voraussetzung 4 (offener Vorschlag) wird nicht eigens geprüft: Ein Vorschlag setzt den Gegensplit bereits auf die vorgeschlagene Kategorie (`kategorisierung.md` 5), sodass Voraussetzung 3 schon nicht erfüllt ist.
- **Begründung:** Erwartungen nie aus Ausgaben der Anwendung (CLAUDE.md); nur festgelegte Merkmale.
- **Bezug:** `erwartungen.md` 5, 6.1, 13.1, 13.2; `kategorisierung.md` 5; `wiederkehrend.md` 2; E-192, E-218.

## E-235 M24: eingebauter Mock-Datensatz

- **Frage:** Was prüft der Ende-zu-Ende-Test des eingebauten Datensatzes (13.3)?
- **Entscheidung:** Mock-Modus ohne Datendatei mit `mock_heute = 2024-06-30`, `mail_abgleich` an, `mail_erstabruf_tage = 366`, beide Postfächer, Lauf, Abruf, Abgleich; unter `zustand=erfuellt` mindestens je eine Erwartung mit Grund `bestellung` und `paypal`, jede zugeordnete Buchung mit nicht leeren `belege`; dazu nur die in der Definition genannten Merkmale (Anbieter `amazon`, Bestellnummer 19 Zeichen, Händler „Buchhandlung Seitenweise (fiktiv)“). Beträge und Tage werden nicht geprüft. Nicht `kern`.
- **Begründung:** Definition 5.
- **Bezug:** `erwartungen.md` 13.3; `plugins.md` 3.

## E-236 M24: Prüfmerkmale der Oberfläche

- **Frage:** Wie werden Kachel und Serien auf `/erwartet` (`oberflaeche.md` 34) geprüft?
- **Entscheidung:** (1) Kachel: fehlt bei ausgeschaltetem Mail-Abgleich; sonst `<a href="/erwartet">` mit „Was kommt noch?“, „<n> offen“, bei Überfälligen „<k> überfällig“, `data-betrag` (am Element oder genau einem darin) = Σ unabhängig nachgerechnet ohne Serien; „am Ende der Seite“ = kein sichtbares Element der Übersicht folgt ihr in der Dokumentreihenfolge; Desktop und mobil; Klick öffnet `/erwartet`. Eine fehlschlagende Abfrage wird nicht nachgestellt. (2) `/erwartet`: fünf Grund-Chips, ohne gewählten Grund Serienzeilen mit der ersetzten ID, `data-grund="serie"`, `data-zustand`, Text „Serie“, Händler und Beschreibung; mit „Manuell“ keine Serien, mit „Serie“ wieder; Summe nach `serien=ja`. Der Abfrageteil der Adresse wird nicht geprüft (offener Punkt der Definition). (3) Menü über den Knopf mit Roh-ID und über Rechtsklick: genau `km-erwartung-serie` und `km-erwartung-konto` mit ihren Zielen; Doppelklick öffnet `/wiederkehrend` ohne Detaildialog. Enter und Umschalt+F10 werden nicht eigens geprüft (wie E-219).
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 30, 34; E-219.

## E-237 Schema und Version für M24

- **Frage:** Wie wird `openapi.yaml` für M24 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.19.0; Query `grund` mit neuem Schema `ErwartungGrundAbfrage` (Werte von `ErwartungGrund` plus `serie`; `ErwartungGrund` unverändert), neuer Query-Parameter `serien` (`ja`|`nein`, Vorgabe `nein`); `ErwartungListe.eintraege.items` = `oneOf` [`Erwartung`, `ErwartungSerie`]; neues Schema `ErwartungSerie` (`additionalProperties: false`, Felder nach 13.1.3 mit `const`/Mustern, `konto_id`, `serie`). Keine neuen Fehlercodes. Exakte Versionsprüfung in `test_m24_schemas`; `test_m23_schemas` prüft nur noch `≥ 2.18.0`.
- **Begründung:** E-029, E-124; frühere Antworten ändern sich nicht.
- **Bezug:** E-029, E-124, E-220, E-232.

## E-238 Meilenstein-Definition „Betragsfilter für wiederkehrende Buchungen“ als M25 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-13 die Definition M25 (Feature `betragsfilter-wiederkehrend`, kontor-app D-137) freigegeben. Sie ändert die Kette aus M16 über eine ausgelieferte Vorgabe. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M25** mit Tests in `tests/app/m25/` (Marker `m25`, Hilfen `tests/hilfen/m25.py`). Abschnitte 1–6 und 8 stehen als `wiederkehrend.md` 9.1–9.6 und 9.8 (dazu 9.9, E-240), Abschnitt 7 als `oberflaeche.md` 35; ergänzt sind `protokoll.md` 20 (Aktion `wiederkehrend_filter_setzen`, Feld `wiederkehrend` der Empfängerform), `sicherung.md` 10 (eigene Einstellungen in der Sicherung, `schemaversion ≥ 6`, Vorgabe nicht) und `openapi.yaml` (E-242). **Ausdrückliche Vertragsänderung:** Die ausgelieferte Vorgabe ist `toleranz` 10 %; damit gilt die Kette aus `wiederkehrend.md` 2.2 nur noch bei Vorgabe `aus` bzw. eigener Einstellung `aus` unverändert. Frühere Tests werden nur so weit angepasst, wie die Definition (9.6) es verlangt (E-244); im Übrigen E-029. Neuer fachlicher Zustand ist nur die eigene Einstellung je Empfänger (Protokoll, Rückgängig, Sicherung mit Rundreise); die Vorgabe ist Betriebszustand.
- **Begründung:** Definition 4 und 6.
- **Bezug:** K 9; T 10, T 3.5, T 3.6; `wiederkehrend.md` 2, 8, 9; E-029, E-192 bis E-197.

## E-239 M25: Prüfmerkmale von REST, Protokoll und Sicherung

- **Frage:** Wie werden Einstellungen, Prüfreihenfolge, Protokoll und Sicherung geprüft?
- **Entscheidung:** (1) Fachliche Fehler über die Menge der `details[].ort` (Anfang `["body", <feld>]`), „alle Verstöße gemeinsam“ mit einem Körper, der zwei Verstöße hat; Schemafehler (fehlender/unbekannter Modus, `bool`, Zeichenkette, Gleitkommazahl, unbekanntes Feld) nur über den Code. (2) Reihenfolge Schema → 404 → fachlich bei `PUT /api/empfaenger/{id}/wiederkehrend`; `DELETE` ohne Einstellung → 404. `null` für nicht verwendete Parameter ist erlaubt. Negative `mindestbetrag` sind 422 (REST „Cent > 0“; „Vorzeichen egal“ gilt nur für das Eingabefeld der Oberfläche). (3) Protokoll mit `tests/hilfen/m25.bestand` (Bestand aus M6 plus `wiederkehrend` an Empfängern mit eigener Einstellung, gelesen aus `GET /api/wiederkehrend/einstellungen`): Vorher/Nachher, „gleiche Einstellung ohne Änderung“, Rückgängig/Wiederholen, `DELETE`, Löschen und Zusammenführen eines Empfängers (Quelle verliert, Ziel behält, Rückgängig stellt her). (4) Sicherung: Rundreise mit je einer Einstellung `toleranz`, `mindestschwelle`, `aus`, Inhaltsprüfsumme unabhängig aus den Protokollformen (M9-Objektarten), Vorgabe des Ziels bleibt; ohne Einstellungen ändern Vorgabe-Wechsel `anzahl` und Prüfsumme nicht. Ältere Sicherungen (Schemaversion 5) werden nicht gebaut (wie E-218 Nr. 10).
- **Begründung:** Definition 3, 4.
- **Bezug:** `wiederkehrend.md` 9.3, 9.4; `protokoll.md` 6, 20; `sicherung.md` 3.3, 10; E-217, E-226.

## E-240 M25: Referenzkette mit Betragsfilter und Präzisierungen

- **Frage:** Wie wird die Kette mit Filter unabhängig berechnet, und wie werden Lücken der Definition geschlossen?
- **Entscheidung:** (1) `tests/hilfen/wiederkehrend_orakel.py` erhält `zugelassen`, `passt`, `kette_gefiltert` (9.2.1–9.2.4), die Mehrheitsregel (9.2.5, nur `quelle = vorgabe`) und Filter je Empfänger für Übersicht, Serie und Ereignisse (Zahlungen unter der Mindestschwelle melden nie einen geänderten Betrag). Ohne Filter bzw. mit `aus` bleibt das Orakel unverändert (M16). Die Begründung mit Rolle `anderer_betrag` (nicht zugelassen oder jünger als das erste Glied und weder Glied noch zusätzlich), `empfaenger`, `betragsfilter` und `betragsfilter_text` steht in `tests/hilfen/m25.erwartung`. (2) Lesarten: „Übergangen“ heißt in 9.2.2/9.2.4 jeder Eintrag zwischen den betrachteten Gliedern, der weder zu `c` noch zu `p` passt, nicht zugelassene eingeschlossen; im Fall „kein Kandidat“ zählen nur passende ältere Einträge (zusätzlich innerhalb von `T`, sonst der nächste als `vorgaenger` bei `abstand`). Ohne erfüllten Rhythmus gilt für alle Einträge `keine_serie` (8.5 unverändert). (3) `uebersprungen` des Schritts `anker` enthält wie in 8.3 die anderen Kandidaten. (4) Ist bei `mindestschwelle` kein Eintrag der Gruppe zugelassen, ist `laenge = 0` und `schritte` leer; `openapi.yaml` lässt das zu (`wiederkehrend.md` 9.9). (5) Tests: die sieben Beispiele aus 9.5 mit ausdrücklichen Aussagen und Vergleich mit der Referenz, Zufallsgruppen mit festen Saaten je Modus (Vorgabe Toleranz, Vorgabe aus, eigene Toleranz 20 % und 0 %, Mindestschwelle, eigene Einstellung aus) für Übersicht und alle Begründungen an zwei Stichtagen, Texte des Betragsfilters (Leerraum normalisiert), Ereignisse über `POST /api/wiederkehrend/pruefen`. Ein Probelauf gegen den Feature-Stand ergab für alle Beispiele und über 100 Zufallsgruppen Übereinstimmung mit dieser Lesart.
- **Begründung:** Erwartungen unabhängig berechnet (CLAUDE.md); die Definition nennt die Erweiterung der Referenzkette selbst.
- **Bezug:** `wiederkehrend.md` 2.2, 3, 8, 9.2, 9.5; E-193, E-195.

## E-241 M25: Prüfmerkmale der Oberfläche

- **Frage:** Wie werden Einstellungen, Filterdialog und Begründungsdialog (`oberflaeche.md` 35) geprüft?
- **Entscheidung:** Nur Desktop. (1) Vorgabe: Optionen von `wk-vorgabe-modus` genau `aus`, `toleranz`; Zahlenfeld nur bei Toleranz sichtbar; Speichern über die Antwort von `PUT …/vorgabe` abgewartet; keine Änderung im Protokoll. (2) Liste: Hinweis „Alle Empfänger verwenden die Vorgabe.“, Zeilen `wk-filter-<id>` mit `data-modus`, Name und Kurztext; Entfernen erzeugt eine Änderung, Strg+Z stellt sie wieder her. (3) Dialog: Werte von `wk-filter-empfaenger` sind die Empfänger-IDs; `wk-filter-modus` genau `vorgabe`, `toleranz`, `mindestschwelle`, `aus`; Felder je Modus sichtbar; Betrag in Euro mit Komma und Vorzeichen egal (−1.000,00 → 100 000 Cent); ungültige Toleranz → Dialog bleibt offen mit Text, nichts gespeichert; „wie Vorgabe“ ohne eigene Einstellung ohne Anfrage, sonst genau ein `DELETE`. (4) Begründungsdialog über den Kontextmenüeintrag mit Alt (M16): `wk-betragsfilter` mit `data-modus`, `data-quelle` und Text = `betragsfilter_text`, Zeile mit `data-rolle="anderer_betrag"` und Text „anderer Betrag“, Knopf `wk-filter-oeffnen` mit `aria-label`, der den Dialog ohne Empfängerauswahl öffnet und mit PUT speichert.
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 1, 13.2, 26, 35; E-196.

## E-242 Schema und Version für M25

- **Frage:** Wie wird `openapi.yaml` für M25 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.20.0; neue Operationen `GET /api/wiederkehrend/einstellungen`, `PUT /api/wiederkehrend/einstellungen/vorgabe`, `PUT`/`DELETE /api/empfaenger/{empfaenger_id}/wiederkehrend`; Schemas `Betragsfilter` (Körper, nur `modus` Pflicht, Parameter `int|null` – fachliche Grenzen prüft die App), `BetragsfilterVorgabe`, `BetragsfilterWerte`, `BetragsfilterAngabe`, `EmpfaengerBetragsfilter`, `WiederkehrendEinstellungen`, `EmpfaengerZustand` (Protokollform mit `wiederkehrend`, zusätzlich in `Objektzustand`; `Empfaenger` bleibt unverändert). Begründung: optionale Felder `empfaenger`, `betragsfilter`, `betragsfilter_text`; Aufzählungen um `anderer_betrag` und `betrag` erweitert; `laenge ≥ 0`, `schritte` ohne Mindestlänge (E-240 Nr. 4). Keine neuen Fehlercodes. `test_m16_schemas` prüft die Pflichtfelder und den Anfang der Aufzählung (E-244), die exakte Version steht in `test_m25_schemas`.
- **Begründung:** E-029, E-124; Definition 3.5 und 6.
- **Bezug:** E-029, E-124, E-198, E-237.

## E-243 Selbstprüfung für M23 bis M25

- **Frage:** Welche neuen Kern-Tests bekommen Referenzteile und Mutanten?
- **Entscheidung:** M25 erhält eine Referenz (`referenz/kontor/m25.py`: Filter, Kette mit Filter, Mehrheitsregel, REST der Einstellungen, Feld `wiederkehrend` in Protokollform und Sicherung; eingebunden in `m5._serie`, `m5.pruefen`, `m16.begruendung`, `m3.protokollform`; `SCHEMAVERSION = 6`) und elf Mutanten `m25_*`. M23 und M24 bleiben ohne Referenz und werden ausgelassen (`OHNE_REFERENZ` um `m23`, `m24`): M23 wäre eine zweite Umsetzung von Schlüsselhülle, Sperrzustand je Instanz, LOGIN-Abruf und Verbindungstest, M24 setzt den Mail-Abgleich aus M20 voraus, der selbst keine Referenz hat (E-225). Ihre Erwartungen sind unabhängig abgesichert (Attrappe mit Betriebsart App-Passwörter samt eigenem Attrappentest, Serien über die Referenzkette, Wirkungen statt Antworten), und der Lauf gegen den Feature-Stand ist ihre Abnahme.
- **Begründung:** wie E-225; M25 ist eine reine Regelerweiterung, die sich mit vertretbarem Aufwand in der kleinen Referenz abbilden lässt.
- **Bezug:** CLAUDE.md (Selbstprüfung); E-149, E-202, E-225.

## E-244 M25: Anpassung früherer Tests

- **Frage:** Welche früheren Tests ändern sich wegen M25, und wie?
- **Entscheidung:** Nur was Definition 9.6 verlangt: (1) `tests/app/m16/conftest.py` setzt für jede in den M16-Tests erzeugte App (`Api` und `LaufenderServer`, modulweit) sofort `PUT /api/wiederkehrend/einstellungen/vorgabe {"modus": "aus"}`; die Tests selbst bleiben unverändert (wie E-194). (2) `tests/hilfen/m16.vergleichbar` lässt die neuen optionalen Felder `betragsfilter`, `betragsfilter_text` und das Kopffeld `empfaenger` außer Betracht (E-029/E-124: zusätzliche, im Schema optionale Felder). (3) `test_m16_schemas` prüft die Pflichtfelder statt der Gleichheit von Pflicht- und Eigenschaftsmenge und den Anfang der Aufzählung `urteil`; `test_m20_schemas`/`test_m23_schemas`/`test_m24_schemas` prüfen die Version nur noch als Untergrenze. (4) `tests/hilfen/m24.serien_orakel` rechnet mit den gesetzten Filtern (das M24-Szenario hat gleichbleibende Beträge, die Erwartungen ändern sich nicht). M5-Tests bleiben unverändert (Definition 6: mit Vorgabe ±10 % grün).
- **Begründung:** Definition 6 („zulässige Anpassung früherer Tests wie E-194“).
- **Bezug:** E-194, E-029, E-124, E-210.

## E-245 M20: Reihenfolge der Mails derselben Erwartung aus zwei Postfächern

- **Frage:** Im Volllauf am 2026-11-13 schlug `test_idempotenz_und_zwei_postfaecher` (M20) einmal fehl: Dieselbe Mail aus beiden Postfächern stand in `mails` in der Reihenfolge zwei, eins statt eins, zwei. Ist das ein Fehler der Anwendung?
- **Entscheidung:** Nein, ein Testfehler. `mails` folgt der Verarbeitung (empfangen, Spiegel-ID; E-218 Nr. 3), und die beiden Postfächer werden parallel abgerufen (`mail.md` 6.2), sodass die Spiegel-IDs zweier gleichzeitig empfangener Mails nicht festgelegt sind. Der Test leitet die erwartete Reihenfolge jetzt aus `GET /api/mail/nachrichten` (empfangen, `id`) ab und prüft die Menge der Einträge zusätzlich fest.
- **Begründung:** Nicht deterministisch prüfbare Reihenfolge; die Aussage der Definition bleibt geprüft.
- **Bezug:** `erwartungen.md` 2.5; `mail.md` 6.2; E-218.

## E-246 Meilenstein-Definition „Bedienung auf dem Handy“ als M26 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-16 die Definition M26 (Feature `UXMobile`, kontor-app D-141, D-142) freigegeben; das Feature ist schon auf main der App (0.13). Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M26** mit Tests in `tests/app/m26/` (Marker `m26`, Hilfen `tests/hilfen/m26.py`). Abschnitte 1–8 stehen als `oberflaeche.md` 36.1–36.8, Abschnitt 9 als 36.9. `sicherheit.md` 6 erhält den Satz zu `Cache-Control: no-cache` und `ETag` unter `/oeffentlich/` (Definition 8.2); das widerspricht „dürfen zwischengespeichert werden“ nicht. `openapi.yaml` bleibt unverändert (2.20.0); kein Protokoll, keine Sicherung. **Vorrang:** Mit M28 (E-252) entfällt die Seite `/wiederkehrend`; 36.6.2 (Karten der wiederkehrenden Buchungen) und die Karten von `wiederkehrend-tabelle`/`wk-filter-liste` werden deshalb nicht getestet.
- **Begründung:** Definition M26 und Vorrangregel des Auftrags vom 2026-11-16.
- **Bezug:** K 5, K 14; `oberflaeche.md` 16, 27, 36; `sicherheit.md` 6; E-145, E-199.

## E-247 M26: Prüfmerkmale

- **Frage:** Wie werden die Festlegungen aus `oberflaeche.md` 36 geprüft, wo die Definition Lücken lässt?
- **Entscheidung:** (1) `kern` nur 36.8: alle in der Hülle verlinkten Dateien unter `/oeffentlich/` und das Manifest tragen `no-cache` und einen `ETag`; passendes `If-None-Match` → 304 ohne Körper, unpassendes → 200; Hülle, `/api/` und `/sw.js` unverändert. (2) Kopfzeile: Reihenfolge in Lesefolge (Zeilen von oben, darin von links), alle Knöpfe ≥ 44 × 44 px und innerhalb von `app-kopf`. „**Eine** Zeile“ wird nicht geprüft: mit dem Personenknopf aus M28 (37.1) sind es bei 390 px neun Knöpfe zu 44 px (396 px > 390 px), und „Wiederholen“ darf erst unter 390 px fehlen; beides zugleich ist nicht erfüllbar (Lücke, dem Auftraggeber zu melden). (3) `aria-controls` von `suche-knopf` und `tabs-knopf` muss auf ein vorhandenes Element bzw. auf `tab-leiste` verweisen (ID-Bezug wie ARIA), nicht wörtlich die Zeichenkette `tab-leiste` sein. (4) Mock-Hinweis: Höhe wächst nach Tippen und kehrt nach erneutem Tippen zurück. (5) Auswahlmodus: Sichtbarkeit von `mehrfach-kategorie`, `-tags`, `-loeschen`, `mehrfach-mehr`; verborgen müssen die übrigen Knöpfe aus 7.5/23.3 sein; `mehrfach-verschieben` wird nicht geprüft (M28 9: „in der Auswahlleiste nur mobil“). Die Einträge von `mehrfach-mehr` gleichen denen des Rechtsklicks auf Desktop bis auf die mobilen Zusätze aus M28 9 (`km-dokument-foto`, `km-verschieben`). Ein künstlich ausgelöstes `contextmenu`-Ereignis ist von einem Rechtsklick nicht zu unterscheiden und wird nicht geprüft; die Wirkung der langen Berührung prüft der Test der Geste. (6) Wischhinweis über schrittweise CDP-Touch-Ereignisse; „bereit“ vor/nach 80 px, Weg höchstens 160 px (+1), Abbruch bei 60 px senkrecht; langsames Wischen über 1,5 s. (7) Blätter: Kontextmenü der Auswahl und Kontomenü der Finanzübersicht unten über die ganze Breite (±2 px), aktive Einträge ≥ 48 px, deaktivierte verborgen; Erfassen-Dialog unten, ≤ 92 % hoch, Fokus im Dialog und nicht in Texteingabe/`textarea`, Tippen auf den Hintergrund schließt; Befehlspalette über die ganze Breite mit Oberkante höchstens an der Unterkante von `app-kopf` und Fokus in `befehlspalette-eingabe` (12.3, 36.5.3). (8) Karten: `thead` verborgen, Bezeichnung und Betrag mit Oberkanten ±8 px, Betrag höchstens 32 px vom rechten Rand der Karte, Zeile nicht `display: table-row`; geprüft für Finanzübersicht und Kontenbaum, Desktop als Tabelle. (9) Filterleiste: kein Feld breiter als die Liste, mindestens zwei verschiedene linke Kanten. (10) Kein waagerechtes Scrollen auf allen Seiten aus 3 ohne `/wiederkehrend` (M28) und mit offener Tab-Liste. Nicht automatisiert: 36.6.5, 36.7, 36.8.3.
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 16, 21, 36; E-145, E-200.

## E-248 M26: Anpassung früherer Tests

- **Frage:** Welche früheren Tests ändern sich wegen M26?
- **Entscheidung:** Genau die sechs aus Definition 9, keiner ist `kern`: (1) M8 `test_lange_beruehrung_oeffnet_menue` prüft Auswahlmodus, `auswahl-kopf` „1 ausgewählt“, kein Menü, verborgene Einzelheiten und danach das Menü über `mehrfach-mehr` im sichtbaren Bereich. (2) M8 `test_split_bearbeiten[handy]`, (3) M12 `test_status_inline_mobil_ueber_kontextmenue` und (4) M17 `test_mobil_lange_beruehrung` öffnen das Menü über die neue Hilfe `tests/hilfen/m8.auswahlmenue_mobil` (lange Berührung → `mehrfach-mehr`); (4) prüft zusätzlich `tab-leiste` verborgen und `tabs-zahl`. (5) M17 `test_tab_leiste_und_attribute[handy]` und (6) `test_mobil_viele_tabs_aktiver_sichtbar` prüfen die Leiste mobil über `tests/hilfen/m17.leiste_sichtbar`/`tabs_aufklappen` (verborgen, nach `tabs-knopf` sichtbar; senkrechte Liste, aktiver Tab oben/unten innerhalb, Wahl von „/“ klappt zu).
- **Begründung:** Definition 9 (beabsichtigte Änderung, D-141 der UXMobile-Reihe).
- **Bezug:** `oberflaeche.md` 16.4, 27.1.2, 36.9; E-029.

## E-249 Meilenstein-Definition „Fachliche und REST-Erweiterungen aus `feature/sammel`“ als M27 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-16 die Definition M27 (kontor-app D-145 bis D-170, REST-Teil) freigegeben. Wie wird sie übernommen?
- **Entscheidung:** Übernahme als **M27** mit Tests in `tests/app/m27/` (Marker `m27`, Hilfen `tests/hilfen/m27.py`). Definition 0–4 und 6–8 stehen in der neuen Datei `spec/api/sammel.md`, Abschnitt 5 als `mail.md` 6.6; ergänzt sind `protokoll.md` 21 (Aktion `dublette_anlegen`, `tags` der Empfängerform), `sicherung.md` 11 (`schemaversion` ≥ 7, Empfänger-Tags) und `openapi.yaml` (E-251). **Vorrang:** Der vorläufige Satz in Definition 10 („`GET /wiederkehrend` liefert weiterhin die Hülle“) ist durch M28 3 ersetzt (404, E-252/E-254). Alle REST-Tests sind `kern` außer der Inhaltsprüfung der Statistik.
- **Begründung:** Definition M27 und Vorrangregel des Auftrags vom 2026-11-16 (M28 vor M27).
- **Bezug:** K 5, K 9, K 13; T 3.5, T 3.6; `sammel.md`; `mail.md` 6.6; `protokoll.md` 21; `sicherung.md` 11; E-029, E-124.

## E-250 M27: Prüfmerkmale und Lesarten

- **Frage:** Wie werden die Regeln aus `sammel.md` geprüft, und wie werden Lücken geschlossen?
- **Entscheidung:** (1) **Verdacht:** unabhängige Referenz `m27.verdacht_soll` (Zahlungsbetrag, Median/MAD mit Abrundung Richtung −∞, robustes z in Hundertsteln) gegen `verdacht=ja` aller Buchungen; Grenzfälle (z = 349/350, 50 %/20,00 € bei MAD 0, |W| < 4, Buchungen ohne Zahlungsbetrag, Konten- und Filterunabhängigkeit) und Zufallsdaten. Vom Text nur „beginnt mit `Der `“ und „enthält den Empfängernamen“. Ungültige Werte von `verdacht` → 422 an allen drei Endpunkten; `GET /api/buchungen/{id}` erhält dafür die Antwort 422 im Schema. (2) **Bestätigen durch eine Person (Szenario aus 2):** `MehrfachAenderung` kennt keine Tags, und die Definition sagt „kein neuer Vertrag“; das Szenario nutzt deshalb `PATCH /api/buchungen/{id}` mit `tag_ids` und `status` (eine Anfrage, eine Änderung). Eine Mehrfachänderung mit Tag und Status in einer Anfrage ist ohne Vertragsänderung nicht möglich (Lücke, dem Auftraggeber zu melden; vgl. M28 O2). (3) **Empfänger-Tags:** Prüfreihenfolge Körper → 404 → M3 (z. B. `empfaenger_existiert`) → Tags; Protokoll mit `m27.bestand` (= M25-Bestand, `tags` aus `GET /api/empfaenger`), Rückgängig/Wiederholen, Zusammenführen (Vereinigung), Tag löschen, Konflikt beim Rückgängig des Tag-Anlegens; Sicherung als Rundreise mit unabhängiger Prüfsumme; ohne Tags unveränderte Prüfsumme. Ältere Sicherungen (Schemaversion 6) und die Migration einer Datenbank aus 0.14 (Definition 7) werden nicht gebaut. (4) **Filter:** Referenz `m27.filter_soll`; `zweck_leer=false` gilt als „ohne Filter“ und wird nicht geprüft; die Filter stehen auch an den Export-Endpunkten (gleiche Filter wie die Liste, `test_m5_schemas` nimmt dafür `verdacht` aus), geprüft wird nur die Liste. (5) **Dubletten:** Vorschläge über `m27.vorschlaege_soll`; „bewertet“ heißt: beide Buchungen im selben gespeicherten Verdacht (`buchung_id` oder `kandidat_ids`), beliebiger Status. (6) **Mail-Liste:** Erwartete Arten aus den Erwartungen der Testdaten; `zuordnung[].buchungen` ohne `warum` gleicht `GET /api/erwartungen/{id}` → `buchungen`; `warum` mit Referenz `m27.warum_soll` und wörtlich für alle vier Fälle (Kennung und Referenz in den Testdaten ohne Buchstaben bzw. ohne Leerraum, damit „<Wert>“ eindeutig ist; Amazon-Name auch „amzn“). (7) **Statistik:** `kern` sind Struktur, Schwellen, Vorgabe `stichtag`, gesammelte Parameterfehler, 404, `konto_ungueltig`, nur lesend und geschützt; das Schema der Unterobjekte ist offen (`additionalProperties: true`, `grund`/`bezeichnung` einer Reihe dürfen `null` sein). Nicht `kern`: das Szenario aus 6 (Toleranz ±1 % für `jahresrate`).
- **Begründung:** Erwartungen unabhängig berechnet (CLAUDE.md); keine Festlegung über die Definition hinaus.
- **Bezug:** `sammel.md` 0–6; `mail.md` 6.6; `protokoll.md` 6, 21; `sicherung.md` 3.3, 11; E-217, E-239.

## E-251 Schema und Version für M27

- **Frage:** Wie wird `openapi.yaml` für M27 rückwärtskompatibel erweitert?
- **Entscheidung:** Version 2.21.0. Parameter `verdacht` (`ja`|`nein`, Vorgabe `nein`) an `GET /api/buchungen`, `GET /api/buchungen/{id}` (dort zusätzlich Antwort 422) und `GET /api/suche`; Filter `zweck_gleich`, `zweck_leer`, `zweck_aehnlich`, `empfaenger_aehnlich` an der Buchungsliste und den Export-Endpunkten; optionales `Buchung.verdacht` (`BuchungVerdacht`); optionales `tags` (minItems 1) an `Empfaenger` und `EmpfaengerZustand`, `tag_ids` an `EmpfaengerAenderung` (nicht an `EmpfaengerNeu`); `POST /api/dubletten` (`DubletteNeu` → 201 `Dublettenverdacht`), `GET /api/dubletten` mit `vorschlaege` und Einträgen `oneOf [Dublettenverdacht, DublettenVorschlag]` (`Dublettenverdacht` unverändert); `MailNachrichtEintrag.postfach`/`zuordnung`, `MailNachrichtenSeite.stand` mit `MailZuordnung`, `MailZuordnungBuchung`, `MailStand`, `MailStandPostfach`, Parameter `reihenfolge`, `zuordnung`; `GET /api/statistik` mit `Statistik` und offenen Unterobjekten; `Aenderung.aktion` nennt `dublette_anlegen`. Die exakte Version steht in `test_m27_schemas`; `test_m25_schemas` prüft nur noch `≥ 2.20.0`.
- **Begründung:** E-029, E-124; Definition 9.
- **Bezug:** E-029, E-124, E-242.

## E-252 Meilenstein-Definition „Oberfläche aus `feature/sammel`“ als M28 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-16 die Definition M28 (kontor-app D-145 bis D-168, Oberflächenteil) freigegeben. Wie wird sie übernommen, und wie verhält sie sich zu M26 und M27?
- **Entscheidung:** Übernahme als **M28** mit Tests in `tests/app/m28/` (Marker `m28`, Hilfen `tests/hilfen/m28.py`). Abschnitte 1–12 stehen als `oberflaeche.md` 37.1–37.12, Abschnitt 13 als 37.13, die Codefehler C1–C4 als 37.14. **Vorrang:** M28 vor M27 (Route `/wiederkehrend` → 404, E-249) und damit Wegfall von M26 6.2 (E-246). Die Tests von C1–C4 prüfen das verlangte Verhalten. Neue Tests sind Browsertests ohne `kern`, dazu ein REST-Test der Routen ohne Browser (ebenfalls nicht `kern`). `openapi.yaml` bleibt bei 2.21.0 (M28 nutzt nur M27).
- **Begründung:** Definition M28 und Vorrangregel des Auftrags vom 2026-11-16.
- **Bezug:** K 5, K 14; `oberflaeche.md` 3, 7–9, 12, 13, 26, 27, 32, 34, 35, 37; E-246, E-249.

## E-253 Person in allen Browsertests

- **Frage:** Ohne gemerkte Person verdeckt der Pflichtdialog (37.1) jede Seite. Wie bleiben die Browsertests aller Meilensteine lauffähig?
- **Entscheidung:** Zentral in `tests/hilfen/browser_fixtures.neue_seite`: ein Init-Skript des Browserkontexts setzt vor dem ersten Laden `localStorage["kontor.person"] = "Torsten"`, falls der Schlüssel fehlt (`m8.PERSON`, `m8.person_skript`); `person=None` lässt es weg. Ist der Speicher gesperrt (M17 1.6), beantwortet `m8.person_waehlen` den Dialog über `person-torsten`; in M17 `test_ungueltiger_oder_fehlender_speicher` geschieht das nach jedem Laden der gesperrten Fälle. Derselbe Test schließt `kontor.person` aus den Schlüsseln aus, die er mit ungültigem Tab-Inhalt überschreibt (kein Tab-Zustand). Die einzelnen Tests bleiben sonst unverändert.
- **Begründung:** Definition 1 (letzter Punkt) und 13 A, J.
- **Bezug:** `oberflaeche.md` 21, 27.1, 37.1; E-139, E-201.

## E-254 M28: Anpassung früherer Tests

- **Frage:** Welche früheren Tests ändern sich wegen M28, und wie?
- **Entscheidung:** Nur die in Definition 13 genannten: **B** `tests/hilfen/m8.NAV` folgt der neuen Gruppenreihenfolge ohne `nav-wiederkehrend`; neu `NAV_LINKS` (16 Links), `NAV_GRUPPEN`, `ALT_ZIELE`, `PALETTE_GEHE`. M8 `test_navigation_ohne_neuladen_und_zurueck` vergleicht alle `a[data-testid]` der Navigation, `test_direkter_aufruf`/`test_kein_waagerechtes_scrollen_mobil` ohne `/wiederkehrend`, dazu `test_wiederkehrend_entfallen` (404 und „Nicht gefunden“ in der Oberfläche, nicht `kern`); `test_m8_seiten::test_wiederkehrende_buchungen` entfällt; `test_jede_route_liefert_die_huelle` ohne `/wiederkehrend` (404 in `tests/app/m28/test_m28_routen.py`); `test_alt_ziffern_und_schraegstrich` mit Alt+1…Alt+7 und Alt+8 ohne Wirkung; `test_palette_woerter_pfeile_und_konten` mit der neuen „Gehe zu“-Reihenfolge; M13 `test_versionsknopf_als_letztes_element_der_navigation` mit den 16 Links und – weil die längere Navigation in sich rollen darf – mit der Inhaltshöhe der Navigation als Untergrenze. **C** `tests/app/m16/test_m16_oberflaeche.py` und `tests/app/m25/test_m25_oberflaeche.py` entfallen, ebenso M24 `test_seite_zeigt_serien_ohne_grund` und `test_serienzeile_menue_und_doppelklick`; M22 `test_zusatzmarken_wiederkehrend_und_mail` prüft kein `data-wiederkehrend` mehr und den Titel nur mit dem Mail-Teil. **D** Neue Hilfen `m8.zweck_editor` (F2) und `m8.stift` (Stift der Einzelheiten): M8 `test_m8_bearbeiten` und `test_schreiben_mit_csrf_und_abmelden` öffnen den Verwendungszweck mit F2, das Datum über `stift-datum`, die Kategorie über `km-kategorie` (kein Stift für die Kategorie); M12 Empfänger und Status über die Stifte (gesperrt: `stift-empfaenger` deaktiviert), Betrag über `stift-splits`; M17 `test_aenderung_in_anderem_tab_beim_naechsten_zeigen` ändert den Betrag im Split-Dialog. **E** M15 Verschieben über Alt+Rechtsklick → `km-verschieben` (ohne Alt kein Eintrag, in der Kategorie-Ansicht nie; die Herkunftsprüfung ohne Herkunft nutzt ein Konto mit einer manuellen Buchung, weil der Dialog eine Zeile braucht). **F** `m8.zellen_ids` rollt bei `aria-rowcount` und sammelt nach `aria-rowindex`. **G** M15 schließt offene Meldungen vor Kontextmenü-Klicks. **I** M18/M12 bleiben unverändert (mit den Schemas aus M27 grün). Zusätzlich die Spezifikationstests: `test_m5_schemas` nimmt `verdacht` aus dem Filtervergleich mit dem Export, `test_m25_schemas` prüft die Version als Untergrenze (E-251).
- **Begründung:** Definition 13 (beabsichtigte Änderungen).
- **Bezug:** `oberflaeche.md` 37.13; E-029, E-139, E-244.

## E-255 M28: Prüfmerkmale und Lesarten

- **Frage:** Wie werden die Festlegungen aus `oberflaeche.md` 37 geprüft, wo die Definition Lücken lässt?
- **Entscheidung:** (1) Person: Pflichtdialog ohne Abbrechen, Esc wirkungslos, kein „null“; ungültige Werte (`Toni`, leer, `torsten`) gelten als keine Person; Personenknopf mit `data-person`, `data-kurz`, `aria-label`, Wechseln mit Abbrechen/Esc; Abmelden entfernt `kontor.person`; ohne Speicher gilt die Person für die geladene Seite. Bestätigen ohne Person ist wegen des Pflichtdialogs nicht erreichbar und wird nicht geprüft. (2) Navigation: `h2[data-testid=nav-gruppe-…]` mit `id`, Abschnitt mit `aria-labelledby` auf diese `id`; alle 16 Links sichtbar (Desktop und mobil). (3) Wiederkehrendes entfernt: kein `km-wiederkehrend` auch mit Alt, kein `data-wiederkehrend`, keine `wk-vorgabe-…`/`wk-filter-…`, kein Chip `erwartet-grund-serie`, keine Anfrage mit `serien=ja`. (4) Tab-Menü: Umschalt+F10 nach Fokus per Pfeiltaste in der Tab-Leiste; nach „Alle“ höchstens der Tab „/“. (5) Gruppierung: Balken, Summen und Anzahlen gegen die selbst summierten `betrag` der REST-Liste; Monatsnamen deutsch; zugeklappt nicht im Dokument; „Weitere laden“ nicht sichtbar. (6) Ausschnitt mit 140 Buchungen: `aria-rowcount` = 141, weniger als 140 gezeichnete Zeilen, Sprungziel `?buchung=` ausgewählt und sichtbar, vollständige Liste über Rollen. (7) Stifte: Doppelklick ohne Editor, sechs Stifte mit `aria-label` „… bearbeiten“, Esc ohne Anfrage, gesperrt nur Status und Tags aktiv. (8) Kontextmenü: Reihenfolge exakt (ohne Alt; mit Alt `km-verschieben` vor `km-loeschen`); `textContent` ohne Kürzel; mobil `km-dokument-foto` nach `km-dokument-anhaengen` und `km-verschieben`. Filter-Untermenü: Adresse und Liste wie die REST-Abfrage mit demselben Parameter (`empfaenger_id` für „gleicher Empfänger“). (9) Dublette aus zwei Buchungen: Abbrechen ohne Anfrage; „Keine Dublette“ → `dublette_anlegen` und `dublette_aufloesen`, ein Strg+Z entfernt den Verdacht. (10) Kürzel: `k`, `s`, `b`, Vortasten `f`/`v` mit `kuerzel-hinweis`, `f z` fokussiert `filter-verwendungszweck`, Esc zurück in die Liste, `v g` gruppiert, unbelegte zweite Taste bricht ab, `?` mit drei Tabellen und ohne „Alt+8“. (11) Mail-Blatt: Chips mit Zahlen aus `stand`, Reihenfolge neueste zuerst, `data-zuordnung`, Pfeil ab, `?filter=`, Sprung zur Buchung; Statistik: Abschnitte, Kontowechsel mit `?konto=`. (12) Listenbreite: rechte Kante der Buchungsliste höchstens an der linken Kante von `panel-details`. Nicht geprüft: Farbtöne der Gruppen, Bild↑/↓, alle übrigen Kürzel einzeln, Strg+Umschalt-Klick und Tastatur der Empfängerliste, Verteilung geänderter Vorlagensummen.
- **Begründung:** Keine Festlegung über die Definition hinaus (`oberflaeche.md` 1).
- **Bezug:** `oberflaeche.md` 37; E-241, E-247.

## E-257 Widersprüche W-013 und W-014 (M28)

- **Frage:** (W-013) Muss `navlink-erwartet` mobil sichtbar sein? (W-014) Wie wird „Listenbreite“ (37.12.7) gemessen, wenn schon die Mindestbreiten der Spalten breiter als der Listenbereich sind?
- **Entscheidung:** (W-013) Nein. `oberflaeche.md` 30 legt „mobil ausgeblendet“ fest; M28 2 ordnet nur Gruppen und Reihenfolge und hebt die Ausnahme nicht auf. `test_navigation_in_gruppen[handy]` erwartet `navlink-erwartet` verborgen und alle übrigen 15 Links sichtbar. (W-014) Die Liste darf nach 32.1 waagerecht geblättert werden; geprüft wird, dass ihre Breite mit und ohne 300 Zeichen langen Zweck gleich ist (±1 px) und dass ihr Bereich – der nächste Vorfahr mit waagerechtem Scrollbereich, sonst die Liste selbst – mit der rechten Kante höchstens an der linken Kante von `panel-details` endet. E-255 Nr. 12 ist insoweit ersetzt.
- **Begründung:** Testfehler; die Definition verlangt nur, dass die Liste nicht nach dem Inhalt wächst und nicht unter dem Panel liegt.
- **Bezug:** `oberflaeche.md` 30, 32.1, 37.2, 37.12.7; E-255.

## E-256 Selbstprüfung für M26 bis M28

- **Frage:** Welche neuen oder geänderten Kern-Tests bekommen Referenzteile und Mutanten?
- **Entscheidung:** **M26:** Die Kern-Tests (36.8) laufen gegen die Referenz; `referenz/kontor/m8.mit_cache` liefert `no-cache`, `ETag` und 304; Mutanten `m26_ohne_etag`, `m26_ohne_304`, `m26_cache_frei`. **M27** wird wie M18–M20, M23, M24 ausgelassen (`OHNE_REFERENZ` um `m27`): Die Mail-Liste setzt den Mail-Abgleich aus M20 voraus, der keine Referenz hat; Verdacht, Filter, Dubletten-Vorschläge und `warum` sind in den Tests bereits durch eigene, unabhängige Referenzen (`tests/hilfen/m27`) mit Zufallsdaten abgesichert, und die Statistik ist experimentell – eine zweite Umsetzung in der Wegwerf-Referenz wäre unverhältnismäßig (wie E-225). Die Abnahme ist der Lauf gegen die App. **M28** hat keine neuen Kern-Tests; die nach E-254 geänderten Kern-Tests von M8, M12 und M13 laufen gegen die nachgezogene Referenz-Oberfläche (Navigation in Gruppen mit `navlink-…`, Alt+1…7, Palettenreihenfolge, Stift für den Status in `panel-details`, kein Doppelklick-Editor, kein `km-wiederkehrend`, Routen `/mail`, `/statistik`, `/erwartet` ohne `/wiederkehrend`); Mutanten `m28_alt_acht`, `m28_palette_alt`, `m28_stift_ohne_status`. Mit `test_m16_oberflaeche.py` entfallen die Oberflächenmutanten von M16 (`m16_km_ohne_alt`, `m16_km_immer_aktiv`, `m16_palette_immer`, `m16_serie_erste_buchung`, `m16_sprung_ohne_nachladen`, `m16_sprung_parameter_bleibt`, `m16_dialog_fokus_weg`, `m16_schritt_betroffen_nur_von`, `m16_dialog_ohne_markierung`); ihr Code bleibt in der Referenz unerreichbar stehen. Wiederholt werden die Mutanten von M8, M12, M13, M16, M26 und M28.
- **Begründung:** CLAUDE.md (Selbstprüfung); E-149, E-225, E-243.
- **Bezug:** E-149, E-202, E-225, E-243, E-254.

## E-258 Meilenstein-Definition „Bankabruf über FinTS/camt und Bankzugang in der Oberfläche“ als M29 übernommen

- **Frage:** Der Auftraggeber hat am 2026-11-19 die Definition des Features `fints-camt` freigegeben (Auftrag vom 2026-11-22, Paket 1). Unter welcher Nummer und wo wird sie übernommen?
- **Entscheidung:** Übernahme als **M29** (nächste freie Nummer; M14 bleibt an `update` vergeben) mit Tests in `tests/app/m29/` (Marker `m29`, Hilfen `tests/hilfen/m29.py`). Auftrag, Abnahmestand von main und Definition liegen unverändert unter `spec/definitionen/`. Definition 1, 2, 4.1, 5, 6, 8, 9 stehen in der neuen Datei `spec/api/bankzugang.md`; Definition 3 in `fints.md` (3, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5a), Definition 4 in `synchronisation.md` 21, Definition 7 in `oberflaeche.md` 38, Definition 10 in `fints.md` 6; dazu `python-api.md` 21, `plugins.md` 12, `openapi.yaml` 2.22.0 (E-262), `meilensteine.md`. Anders als frühere Meilensteine ist M29 **nicht** rückwärtskompatibel im Sinne von E-029: Er entfernt M10 und ändert M6/M11 (E-259 bis E-261).
- **Begründung:** Auftrag vom 2026-11-22 („Was zu tun ist“ 1–2); Definition, Kopf und Abschnitt 9.
- **Bezug:** K 3, K 6; T 6, T 7, T 21; `bankzugang.md`; E-029, E-152.

## E-259 Meilenstein 10 (AqBanking) entfällt vollständig

- **Frage:** Wie wird Definition 9 („M10 entfällt vollständig“) in Spezifikation, Tests und Selbstprüfung umgesetzt?
- **Entscheidung:** Entfernt sind: `spec/api/aqbanking.md`; `tests/app/m10/` (drei Dateien); `tests/hilfen/aqbanking.py`, `tests/hilfen/m10.py`; der Marker `m10` (`pytest.ini`, `tests/conftest.py`); `test_m10_schemas` in `tests/spec`; in der Selbstprüfung `referenz/kontor/plugins/aqbanking.py`, `m10_config.py`, die AqBanking-Teile in `config.py` und `plugins/__init__.py` sowie die Mutanten `aq_*`. `python-api.md` 16 und `plugins.md` 10 bleiben als leere Abschnitte mit Verweis stehen (die Nummern werden andernorts zitiert). `PluginInfo.name` in `openapi.yaml` kennt `aqbanking` nicht mehr; der Fehlercode `bank_tan_nicht_unterstuetzt` entfällt. Der M1-Test der ungültigen Konfigurationen prüft zusätzlich `bank_plugin="aqbanking"`. E-152 bis E-157 sind damit gegenstandslos. Die Nummer M10 wird nicht neu vergeben.
- **Begründung:** Definition 1.1, 2, 9; Auftrag „Frühere Tests nachziehen“.
- **Bezug:** K 3; `bankzugang.md` 2, 7; `python-api.md` 16, 21; E-152 bis E-157.

## E-260 AqBanking-Teil von Meilenstein 11 entfällt

- **Frage:** Was wird aus „Saldo über AqBanking“ (M11)?
- **Entscheidung:** `kontostand.md` 1.3 und das Feld `aqbanking_saldo` (`python-api.md` 17.1) entfallen; `tests/app/m11/test_m11_aqbanking_saldo.py`, der Mutant `aq_saldo_noted` und die Referenzteile dazu sind entfernt. FinTS- und Mock-Saldo (1.1, 1.2) und ihre Tests bleiben unverändert. E-166 ist gegenstandslos.
- **Begründung:** Definition 9 (M11).
- **Bezug:** K 6; `kontostand.md` 1.3; E-158, E-166.

## E-261 Anpassung der M6-Tests des FinTS-Plugins und des gemeinsamen Plugin-Tests

- **Frage:** Welche früheren Tests ändern sich wegen Definition 3 und 9, und welche bleiben?
- **Entscheidung:** Geändert: (1) `tests/app/m6/test_m6_paket.py::test_oeffentliche_methoden` erwartet für `FintsBankPlugin` genau `konten`, `umsaetze`, `schliessen`, `tan_verfahren`. (2) `tests/app/test_plugins.py::test_nur_lesende_oeffentliche_methoden` erwartet für das echte Bank-Plugin zusätzlich `tan_verfahren` (Mock unverändert). (3) Docstrings der M6-Tests zu Kontenliste und camt verweisen auf die neue Fassung. **Unverändert** bleiben die übrigen M6-Tests des Plugins und der Synchronisation: Die Generatordaten (`fixtures/m6/fints_bank.json`) ergeben nach der neuen Kontenregel (`fints.md` 3.2) dieselbe Kontenliste (Depot: Kontoart außerhalb der Tabelle; Altkonto: nicht in HISPA; Dollarkonto: ausdrücklich USD), das Profil `camt` der Attrappe bietet weiter nur camt.052.001.08 an, das Profil `mt940` gar keinen camt-Abruf (MT940 bleibt dort richtig), und die Attrappe verlangt in der Vorgabe keine TAN bei der Anmeldung. Fixtures werden deshalb nicht neu erzeugt. Das neue Verhalten (camt-Version, Kontenvarianten, TAN bei der Anmeldung, Meldungstext) prüfen die M29-Tests.
- **Begründung:** Definition 9; Auftrag: Tests, deren Erwartung weiter gilt, nicht ändern.
- **Bezug:** `fints.md` 3–3.5a; `plugins.md` 2, 12; E-017, E-113.

## E-262 Schema und Version für M29

- **Frage:** Wie wird `openapi.yaml` für den Bankzugang erweitert?
- **Entscheidung:** Version 2.22.0. Neuer Tag `bank`; Pfade `GET`/`PUT /api/bank/zugang`, `POST /api/bank/zugang/tan-verfahren`, `POST /api/bank/zugang/konten/abrufen`, `PUT /api/bank/zugang/konten`, `GET`/`PUT /api/bank/zugang/diagnose`; Schemas `Bankzugang`, `BankzugangKonto`, `BankzugangAenderung`, `BankTanVerfahren`, `BankKontenAbrufAnfrage`, `BankKontenAbruf`, `BankKontenAuswahl`, `BankDiagnose`, `BankDiagnoseSchalter` (alle `additionalProperties: false`, alle Antwortfelder Pflicht). Neue Fehlercodes `bankzugang_nicht_aenderbar`, `bankzugang_unvollstaendig`, `tan_offen`. `PluginInfo.name` = `mock`, `fints`, `imap`. `tests/spec`: `test_m10_schemas` entfällt, `test_m27_schemas` prüft die Version mit `>=`, neu `test_m29_schemas` und `OPERATIONEN_M29`.
- **Begründung:** Definition 5; `tests/hilfen/api.py` prüft jede Antwort gegen das Schema.
- **Bezug:** `bankzugang.md` 4; E-029, E-124, E-251.

## E-263 FinTS-Attrappe: zusätzliche Betriebsarten

- **Frage:** Wie werden die Betriebsarten aus Definition 10 bereitgestellt, ohne die M6- und M11-Tests zu berühren?
- **Entscheidung:** `tests/hilfen/fints_attrappe.py` bekommt Schalter, deren Vorgaben das bisherige Verhalten lassen (`fints.md` 6): `profil="beide"` und `camt_formate` (angebotene camt-Formate, auch ohne lesbare Version) mit Aufzeichnung `camt_angefordert`/`camt_kontoverbindungen`; `tan_anmeldung` (`nie`/`einmal`/`immer`) und `anmeldung_entkoppelt` (3955); `erlaubte_verfahren` und `verfahren_zusatz`; `upd_ohne_kontoart`, `upd_ohne_iban`, `upd_ohne_konten`, `hispa_mit_nicht_sepa`, `hispa_ohne_bic`; `datum_form`, `datum_kaputt`, `betrag_kaputt`; `rueckmeldung_zusatz`. Die Attrappe verlangt die TAN bei der Anmeldung nur für Dialoginitialisierungen mit HKTAN (Prozess 4) ohne HKSYN und lehnt bis dahin – und in Ein-Schritt-Dialogen – Geschäftsvorfälle mit 9075 ab; so bleibt `tan_verfahren()` ohne TAN möglich (Definition 3.1). Die neuen Betriebsarten sind in `tests/attrappen/test_attrappen.py` mit python-fints geprüft. Keine neuen Fixtures.
- **Begründung:** Definition 10; E-028 (Attrappe auf Protokollebene); CLAUDE.md (Fixtures nur über den Generator).
- **Bezug:** T 7; `fints.md` 6; E-028, E-122.

## E-264 Übergang alter Kennungen: Naht `kontor.sync.kennungen_als_alt_markieren`

- **Frage:** Definition 10: Der Zustand „vor der Umstellung“ lässt sich nur in der Datenbank herstellen; der Test-Thread legt eine Testhilfe oder einen dokumentierten Weg fest. Welchen?
- **Entscheidung:** Eine öffentliche Funktion der Anwendung, `kontor.sync.kennungen_als_alt_markieren(config) -> None` (`bankzugang.md` 3.1, `python-api.md` 21.3): Sie markiert alle der aktiven Datenbank in diesem Augenblick bekannten Bank-Kennungen als „alt“, unabhängig vom einmaligen Übergang, ohne Protokoll und ohne Wirkung auf den Buchbestand. Die Tests rufen sie zwischen zwei App-Instanzen auf derselben Datenbank auf. Die Tests laufen mit dem Mock-Plugin (zwei Mock-Datendateien mit denselben Umsätzen und verschiedenen `umsatz_id`) und einmal mit dem FinTS-Plugin (Attrappe erst im Profil `mt940`, dann `camt`: Hash-Kennung wird Bankreferenz). **Das ist eine neue Anforderung an die Anwendung**, die die Definition nur als Auftrag an den Test-Thread benennt; der Implementierungs-Thread muss die Funktion bereitstellen.
- **Begründung:** Tests kennen kein Datenbankschema (CLAUDE.md, Rollentrennung); eine Datenbank „aus der Zeit davor“ lässt sich über REST, Import oder Sicherung nicht erzeugen (die Markierung gehört nicht zur Sicherung). Eine Funktion ist die kleinste Naht und auch im Betrieb brauchbar.
- **Bezug:** `bankzugang.md` 3; `synchronisation.md` 4.3, 21.2; T 6.

## E-265 M29: Prüfmerkmale und Lesarten

- **Frage:** Wie werden die Festlegungen geprüft, wo die Definition Lücken lässt?
- **Entscheidung:** (1) **`tan_offen`** wird wörtlich aus Definition 5.2 übernommen (neuer Code neben dem bisherigen `tan_ausstehend` von `POST /api/sync`). (2) „Konfigurationsfehler mit Feld“ = `details["feld"] == "bank_plugin"` (wie E-216). „Felder gibt es nicht mehr“ = kein Attribut, kein Dataclass-Feld; der Konstruktor lehnt sie ab (`TypeError` oder `KonfigurationsFehler`). (3) „Die Meldung verweist auf die Einstellungen“ = die Meldung enthält „Einstellungen“ (`PluginNichtVerfuegbar` und Lauf ohne gespeicherte Konten mit TAN bei der Anmeldung). (4) `tan_verfahren()`: Vergleich als Menge von Paaren (Reihenfolge frei, Liste oder Tupel); `999` nie enthalten. (5) Zeitpunkt in camt: geprüft werden beide Formen, `<DtTm>` (ISO 20022) und ein Zeitpunkt im Element `<Dt>`; ausgewertet wird das geschriebene Datum ohne Umrechnung. (6) „Kein Konto ausgewählt → der Lauf verarbeitet kein Konto“: `konten` des Laufs leer, keine Buchung, keine TAN-Anforderung; der Status des Laufs ist nicht festgelegt und wird nicht geprüft. Ob der Lauf die Kontenliste abfragt, wird am Ergebnis geprüft (nicht ausgewählte und bei der Bank neu hinzugekommene Konten erscheinen nicht), nicht an gesendeten Segmenten. (7) Lauf ohne gespeicherte Konten bei TAN zur Anmeldung: Status `fehlgeschlagen`, keine offene TAN-Anforderung; der Code ist nicht festgelegt („wie bisher“). (8) Bankzugang: `PUT` mit `{}` ändert nichts; falscher Typ, unbekanntes Feld und Regelverstoß sind 422 `validierung`; Ort `["body", <Feld>]` wird für Regelverstöße geprüft; der übergebene Wert darf im Antworttext nicht vorkommen. Die Reihenfolge zwischen `bankzugang_nicht_aenderbar`, `sync_laeuft`/`tan_offen` und `bankzugang_unvollstaendig` wird nicht geprüft (Tests kombinieren sie nicht), `sync_laeuft` wird nicht geprüft (nicht deterministisch herstellbar, ohne den Planer zu kennen). Im Mock-Modus antworten alle ändernden Endpunkte einschließlich der beiden Abrufe mit 409 `bankzugang_nicht_aenderbar`; `GET …/diagnose` liefert dort `aktiv = false`. (9) `bild` der TAN-Anforderung: Daten-URL `data:image/png;base64,…` mit den unveränderten Bytes der Bank. (10) „Nicht in der Datensicherung“: Die Sicherungsdatei (ZIP samt SQLite-Inhalt) enthält die gespeicherten Werte des Bankzugangs nicht; `anzahl` und Inhaltsprüfsumme ändern sich durch den Bankzugang nicht. „Nicht im Protokoll“: `GET /api/aenderungen` bleibt unverändert. (11) Diagnoseprotokoll: geprüft werden die Verbote (alle in Definition 6 genannten Werte der Attrappe kommen in keiner Zeile und in keinem Logeintrag vor; nach der Bereinigung keine Ziffernfolge ab fünf Stellen aus Rückmeldungstexten) und wenige positive Merkmale, die die Definition wörtlich nennt: Segmentarten (`HKCAZ`), das gewählte camt-Format, „Konto 1“, die Form unlesbarer Werte (`99.99.9999`), mindestens ein Logeintrag der Stufe INFO; Wortlaut und Aufbau der Zeilen sind frei. (12) Oberfläche: `bankzugang` ist das `data-testid` des Abschnitts; geprüft wird nur Genanntes (Attribute, Sichtbarkeit, Werte), keine Texte außer der Anzahl der Konten als Zahl in der Statuszeile. Der Abschnitt wird über `m29.bankzugang_oeffnen` aufgesucht (`/einstellungen`), damit spätere Meilensteine den Weg an einer Stelle ändern können. „Nutzt keinen Browser-Speicher“: `localStorage`/`sessionStorage` enthalten nach der Bedienung keinen der eingegebenen Werte und keinen Schlüssel mit `bank`; „keine Ressourcen von außen“: alle Anfragen gehen an den Ursprung der App oder sind `data:`-URLs.
- **Begründung:** Keine Festlegung über die Definition hinaus; Auftrag („Rate keine Einzelheiten der Oberfläche“).
- **Bezug:** `bankzugang.md`; `fints.md` 3; `synchronisation.md` 21; `oberflaeche.md` 38; E-216, E-255.

## E-266 Selbstprüfung für M29

- **Frage:** Welche neuen oder geänderten Kern-Tests bekommen Referenzteile und Mutanten?
- **Entscheidung:** **M29** wird wie M18–M20, M23, M24 und M27 ausgelassen (`OHNE_REFERENZ` um `m29`): Bankzugang, Diagnoseprotokoll, TAN bei der Anmeldung und der Übergang alter Kennungen bräuchten eine zweite Implementierung in der Referenz; die Abnahme ist der Lauf gegen die App. Die **geänderten** Kern-Tests früherer Meilensteine laufen gegen die Referenz: `FintsBankPlugin.tan_verfahren` ist dort als kleinste Fassung ergänzt, `bank_plugin="aqbanking"` ist ungültig. Entfernt sind die Referenzteile von M10 und die Mutanten `aq_*` (zehn aus M10, `aq_saldo_noted` aus M11). Kein neuer Mutant.
- **Begründung:** CLAUDE.md (Selbstprüfung, Referenz klein halten); Auftrag „Was zu tun ist“ 5; E-225, E-243, E-256.
- **Bezug:** E-149, E-225, E-243, E-256, E-259.

## E-267 M29: Nachträge zu den Prüfmerkmalen

- **Frage:** Welche Lesarten sind beim Schreiben der M29-Tests zu E-263 und E-265 hinzugekommen?
- **Entscheidung:** (1) **Übergang:** Eine zugeordnete Buchung bleibt bis auf die zusätzliche Kennung unverändert (Datum, Betrag, Empfänger), wie beim Zusammenführen nach `synchronisation.md` 4.4; der Empfängername entscheidet nur die Wahl zwischen mehreren passenden Buchungen, er ist keine Bedingung (`bankzugang.md` 3). Eine Buchung, die schon alte und neue Kennung trägt, steht nicht mehr zur Wahl. (2) **Diagnoseprotokoll:** Beträge stehen nicht in der Verbotsliste der Tests, weil sich Ziffernfolgen wie „125.50“ nicht von Größen und Dauern unterscheiden lassen; einzelne Wörter als Kontobezeichnung („Kreditkarte“) ebenfalls nicht. Geprüft werden PIN, TAN, Auftragsreferenzen, Kundensystem-IDs, Benutzerkennung, Produkt-ID, Server-Adresse (auch Rechner:Port), IBANs, Kontonummern, Inhaber, mehrteilige Kontobezeichnungen, Empfänger, Verwendungszwecke, Bankreferenzen, Gegen-IBANs und der Wortlaut der TAN-Anforderung. Die Bereinigung der Freitexte wird nur in den Zeilen geprüft, die den Rückmeldungstext enthalten (Ziffernfolgen ab fünf Stellen kommen sonst als Größen vor); die Grenze von 160 Zeichen und das Entfernen von Steuerzeichen sind nicht prüfbar (FinTS-Rückmeldungstexte sind höchstens 80 Zeichen lang und ohne Steuerzeichen). Für unlesbare Werte gilt: Ziffern werden `9`, Buchstaben `a`, andere Zeichen bleiben. Im Log wird nur verlangt, dass mindestens ein Eintrag der Stufe INFO (oder die Standardfehlerausgabe) eine Diagnosezeile mit `HKCAZ` enthält; persönliche Angaben in anderen Logeinträgen der App werden hier nicht geprüft, PIN und TAN in keinem. (3) **Attrappe:** Sie zeichnet ausgegebene Auftragsreferenzen (`referenzen`) und Kundensystem-IDs (`system_ids`) auf und merkt sich ihre Adresse (`letzte_url`). (4) **REST:** Nicht geprüft wird, ob das Entfernen einer gespeicherten Kunden-ID, die der Benutzerkennung gleicht, die Konten verwirft; `http://127.0.0.2/…` und andere Loopback-Adressen außer den drei genannten werden nicht geprüft. (5) **Oberfläche:** Die Ausgabe `bankzugang-diagnose-zeilen` darf ihre Zeilen als Text oder als Wert eines Eingabeelements tragen; `bankzugang-tan-bild` wird nur als `<img>` auf eine Daten-URL geprüft; der Hinweis auf die Vorbelegung und der Text der leeren Kontenliste haben kein genanntes Merkmal und werden nicht geprüft; nur Desktop.
- **Begründung:** Keine Festlegung über die Definition hinaus; Tests dürfen nicht an zufälligen Übereinstimmungen scheitern.
- **Bezug:** `bankzugang.md` 3, 5; `oberflaeche.md` 38; E-263, E-265.

## E-268 Übernahme der Definition „Kontor-Ausdrücke, Filter im Kontoblatt, Regeleditor und Regel-Tags“ als Meilenstein 30

- **Frage:** Auftrag vom 2026-11-22, Paket 2: Die Definition (`spec/definitionen/definition-2-ausdruecke-regeln.md`, Stand 2026-11-19) und ihr Nachtrag 1 (`definition-2-nachtrag.md`) tragen den Vermerk „Entwurf zur Freigabe“. Werden sie übernommen, und unter welcher Nummer?
- **Entscheidung:** Ja, auf Auftrag des Projektinhabers ohne gesonderte Freigabe (AUFTRAG.md „Lage“), als **Meilenstein 30** (nächste freie Nummer nach M29; Vorschlag der Definition). Der Nachtrag ersetzt den letzten Punkt von 9.3 der Definition und ergänzt den Tag-Dialog; beide Dateien bilden zusammen M30. Maßgeblich bleiben die Dateien unter `spec/definitionen/`; die Spezifikation gibt sie wieder und hält Lesarten als Entscheidungen fest.
- **Begründung:** Auftrag; Features sind bereits auf main der App.
- **Bezug:** K 5, K 7, K 14; T 3.5, T 3.6, T 8, T 19.

## E-269 Gliederung der Spezifikation für M30

- **Frage:** Wohin kommt die Definition in `spec/api/`?
- **Entscheidung:** Neue Datei `ausdruecke.md` (Sprache, Prüfen, Sprache abfragen, `als-regel`, Filter der Buchungsliste, Sicherheit; Definition 2 bis 4, 11, 14). Regeln mit Ausdruck und Tags als `kategorisierung.md` 8 (Definition 5). Protokoll `protokoll.md` 22, Sicherung `sicherung.md` 12, Verweise beim Löschen `loeschen.md` 8, Filterparameter `datenmodell.md` 19 (Definition 6, 5.4, 4). Oberfläche `oberflaeche.md` 39 (Definition 7 bis 10, Nachtrag). Frühere Abschnitte werden nicht umgeschrieben; die neuen nennen, was sie ersetzen.
- **Begründung:** CLAUDE.md (bestehende Festlegungen ergänzen statt umschreiben); eine eigene Datei, weil die Sprache von zwei Stellen (Regeln, Filter) benutzt wird.
- **Bezug:** K 5, K 7.

## E-270 Schema und Version für M30

- **Frage:** Wie wird `openapi.yaml` erweitert, und wie streng sind die neuen Schemas, wo die Definition nur Feldnamen nennt?
- **Entscheidung:** Version 2.23.0. Neuer Tag `ausdruck` mit `GET /api/ausdruck/sprache`, `POST /api/ausdruck/pruefen`, `POST /api/ausdruck/als-regel`; unter `regeln` neu `POST /api/regeln/reihenfolge`, `/test`, `/erklaeren`, `POST /api/regeln/{regel_id}/anwenden`. Parameter `filter` und `stichtag` an `GET /api/buchungen` und beiden Exporten; `Buchung.markierungen` (optional). `Regel`: Pflichtfelder unverändert (E-029), `kategorie_id` darf null sein, neu optional `ausdruck`, `ausdruck_form`, `tag_ids`, dazu `automatisch` und `empfaenger_id` (die Definition nennt sie „wie bisher“; kontor-tests kennt sie noch nicht, sie werden hier nur zugelassen, damit Antworten mit ihnen den Vertrag nicht verletzen; ihre Bedeutung legt das Paket mit dem Lernmodell fest). `bedingungen` lässt zusätzlich `BedingungAusdruck` zu (`feld = operator = "ausdruck"`, `wert` ein Objekt ohne festgelegten Aufbau). `RegelNeu`/`RegelAenderung` mit `ausdruck`, `tag_ids`, `kategorie_id` null. `RegelAnwendung.tags` optional. Neue Schemas: `Markierung`, `AusdruckSprache`, `AusdruckPruefen`, `AusdruckPruefung`, `AusdruckFehler`, `AusdruckDatumsangabe`, `AusdruckAlsRegelAnfrage`, `AusdruckAlsRegel`, `RegelnReihenfolge`, `RegelTestAnfrage`, `RegelTestErgebnis`, `RegelTestTreffer`, `RegelWirkung`, `RegelErklaerenAnfrage`, `RegelErklaerung`, `ErklaerKnoten`, `RegelEinzelAnwenden`, `RegelEinzelAnwendung`. **Strenge:** Objekte, deren Felder die Definition vollständig aufzählt, haben `additionalProperties: false`; wo sie nur den Namen eines Feldes nennt, bleibt der Wert offen (`werte`, `schluesselwoerter`, `aliase`, `methoden`, `kwargs`, `baum`, `hinweise`, `freitext`, `zusammenfassung`, `erwartet`, `entfernt`, in Treffern `empfaenger`, `kategorie_vorher`, `kategorie_nachher`, `tags_neu`; Knoten der Erklärung dürfen weitere Felder tragen). In `RegelTestTreffer` sind nur `buchung_id`, `datum`, `wirkung` Pflicht, weil die Definition nicht sagt, ob nicht zutreffende Felder (`verdeckt_von`, `grund`) fehlen oder null sind. Neue Fehlercodes `ausdruck_ungueltig`, `regel_ohne_aktion`. `tests/spec`: `test_m30_schemas`, `OPERATIONEN_M30`; `test_m29_schemas` prüft die Version mit `>=`.
- **Begründung:** Definition 3 bis 5, 12; `tests/hilfen/api.py` prüft jede Antwort gegen das Schema – ein zu enges Schema würde raten, ein fehlendes ließe frühere Tests an jeder Regel scheitern.
- **Bezug:** `ausdruecke.md` 4, 5; `kategorisierung.md` 8; E-029, E-124, E-262.

## E-271 Nachziehen früherer Meilensteine für M30

- **Frage:** Welche früheren Tests und Hilfen ändern sich nach Definition 12, welche bleiben?
- **Entscheidung:**
  1. **REST (M2, M3, M9 und alle späteren mit Regeln): Tests unverändert.** Die Erwartungen gelten weiter (Regeln der bisherigen Form wirken unverändert; fehlende Kategorie ohne Tags bleibt 422 `validierung`). Rot waren sie gegen die App nur, weil das Schema `Regel` die neuen Felder verbot (E-270) und weil die Protokollform der Regel nicht mehr die REST-Darstellung ist. Dafür gibt es `tests/hilfen/m3.regel_zustand` (ohne `ausdruck`, `ausdruck_form`; `tag_ids` nur bei Vorhandensein), das `m3.bestand` und damit alle späteren `bestand`-Hilfen (`m4` … `m27`), `m9.inhalt` (Inhaltsprüfsumme) und die Rückgängig-Rundreisen benutzen; `m3.bezuege_ok` kennt `kategorie_id = null` und `tag_ids`, das Löschorakel (`loeschen_orakel`) Regeln ohne Kategorie. Gegen die Referenz der Selbstprüfung (ohne die neuen Felder) ist `regel_zustand` die Identität.
  2. **Oberfläche, Filter (M8, M11, M12, M17, M26, M28):** `m8.filter_aufklappen` bedient `filter-baukasten-umschalten`; neu `m8.filter_ausdruck_setzen`, `m8.filter_ausdruck_wert`, `m8.filter_zuruecksetzen`. Statt der Einzelfelder setzen die Tests einen Ausdruck (`status == "importiert"`) oder öffnen die alte Adresse; `filter-umschalten` wird zu `filter-baukasten-umschalten`; statt „Kontrollkästchen angekreuzt“ wird der Text des Ausdrucksfelds geprüft; `filter-anzahl` wird nur noch auf 0 bzw. ungleich 0 geprüft (die Zählweise nennt die Definition nicht). Betroffen: `m8/test_m8_kontoansicht.py` (`test_filter` über alte Adressen, `test_filter_aus_der_url_und_status`, `test_ungueltige_betragseingabe` → `test_ungueltiger_filterausdruck`), `m12/test_m12_oberflaeche.py` (vier Filterleisten-Tests), `m17/test_m17_tabs.py`, `m17/test_m17_gegenbuchung.py`, `m28/test_m28_kontoblatt.py` (`test_filter_untermenue`, `test_filter_leerer_zweck_und_ohne_empfaenger`: geprüft wird die Trefferliste, nicht mehr der Name des Adressparameters), `m26/test_m26_oberflaeche.py` (`test_erfassen_schwebend_und_titelzeile` ohne die Zeile mit `filter-umschalten`). **Entfernt:** `m26::test_filterleiste_zweispaltig` (36.6.4 beschreibt die Einzelfelder).
  3. **Unverändert trotz Liste `abnahme-stand-main.txt`:** M2-/M3-/M9-/M15-/M19-Tests, deren Erwartung weiter gilt (siehe 1); Fehlschläge in M13, M19, M20, M27, M28 (Statistik, Navigation) gehören zu anderen Paketen.
- **Begründung:** Definition 12; Auftrag „Frühere Tests nachziehen“ und „Tests, deren Erwartung weiter gilt, nicht ändern“.
- **Bezug:** `oberflaeche.md` 39.8; `protokoll.md` 22; E-029, E-124, E-254.

## E-272 M30: Lesarten und Prüfmerkmale der REST-Tests

- **Frage:** Wie wird geprüft, wo die Definition Angaben offen lässt?
- **Entscheidung:**
  1. **Fehlercodes:** Je Code prüfen die Tests Beispiele, die die Definition wörtlich nennt oder die sich eindeutig ergeben. Wo zwei Codes vertretbar sind, sind beide zugelassen: Vergleich ungleicher Typen (`betrag > "10"`: `operator_unpassend` oder `wert_ungueltig`), regulärer Ausdruck über 500 Zeichen (`zu_lang` oder `regex_ungueltig`), Teiltext an einem Zahlenfeld (`operator_unpassend` oder `wert_ungueltig`). **Fehlerstelle:** geprüft werden `zeile` und `spalte` des Beginns (ab 1, in Zeichen) an eindeutigen Beispielen sowie `ende_zeile ≥ zeile`; ob `ende_spalte` ein- oder ausschließend zählt, ist offen und wird nicht geprüft. Der Hinweis bei einfachem `=` gilt als erfüllt, wenn `==` in `meldung` oder `erwartet` vorkommt.
  2. **Kanonische Form:** geprüft werden das Beispiel der Definition, die genannten Bausteine (volle Feldnamen, `and`/`or`/`not`, doppelte Anführungszeichen, führende Nullen, überflüssige Klammern), die Idempotenz und die Gleichwertigkeit (gleiche Trefferliste). Nicht geprüft: Schreibweise von Zahlen, `True`/`None`, Reihenfolge in Listen.
  3. **Datumsangaben** (`datumsangaben` mit `stichtag` 2026-11-16, ein Montag): `von`/`bis` als `JJJJ-MM-TT`, `tage` = Zahl der Tage von `von` bis `bis`. Eindeutig und geprüft: alle Zeilen der Tabelle außer den folgenden. `-1m`, `-1y`: `bis` = Bezugstag, `von` ist der Tag genau eine Einheit zurück oder der Tag danach (beide zugelassen). `+3d`: nur `von` = Bezugstag. `X + 1y`: nur `von`; `X - 30d`: nur `bis`. Zweistellige Jahre: geprüft `35` → 2035 und `38` → 1938 (nicht die Grenze 36/37). `relativ` wird nur für eindeutig relative (`heute`, `-5d`, `dieser_monat`) und eindeutig feste Angaben (`1.1.2017`, `2026-02-05`, `2/2025`, `q4/2025`, `kw46/2026`) geprüft. `text` der Angabe wird nicht geprüft.
  4. **Filter-Semantik:** Die Erwartung je Ausdruck rechnet der Test selbst aus den angelegten Buchungen. Text: Vergleich nach Kleinschreibung und Umlautangleich (ä→ae, ö→oe, ü→ue, ß→ss). `werktag` = Montag bis Freitag. `kategorie == "…"` trifft nur die genannte Kategorie, nicht ihre Unterkategorien (Definition 8: „`kategorie_id` mit Unterkategorien“ hat keine Entsprechung). `empfänger == ""` trifft Buchungen ohne Empfänger („ohne Empfänger leer“). `letzter_tag` ist allein und als `letzter_tag == True` gültig. Nicht geprüft: `betrag` einer Umbuchung ohne Konto, `kategorie` bei Splitbuchungen, Groß-/Kleinschreibung bei Tag-Namen.
  5. **`markierungen`:** Mit `filter` trägt jeder Eintrag das Feld (Liste). Bei einem Texttreffer in Empfänger bzw. Verwendungszweck gibt es mindestens eine Markierung, deren `feld` den Feldnamen meint (`empfänger`/`empfaenger`/`empf` bzw. `verwendungszweck`/`vwz`) und deren Stelle `[start, ende)` oder `[start, ende]` im angezeigten Text den gesuchten Text ergibt. Name des Feldes und Zählweise von `ende` sind offen.
  6. **Regeln:** Fälle aus 5.2 werden einzeln geprüft (keine Kombination, die Prüfreihenfolge ist offen). „Ort `body`, `kategorie_id`“ = ein Eintrag in `details`, dessen Ort beide Bestandteile enthält (wie E-265 Punkt 8). Gleichwertigkeit alter Regeln (Definition 13): dieselbe Buchungsmenge mit der bisherigen Form und mit dem von der App gelieferten übersetzten Ausdruck (als neue Regel angelegt) über `POST /api/regeln/test` mit leerer Testmenge, für alle Operatoren der bisherigen Form einschließlich vorzeichenbehafteter Betragsgrenzen und `konto_id`. Wörtlich geprüft wird nur das Beispiel `"REWE" in empfänger`.
  7. **Test (5.6):** `zaehlung` darf Wirkungen ohne Treffer weglassen. `anzahl` zählt alle Treffer der Bedingung in der Testmenge einschließlich gesperrter; `gesamt` wird nur gegen die Zahl der über alle Seiten gelieferten Treffer geprüft. Die Form von `kategorie_vorher`/`kategorie_nachher` und `tags_neu` (ID, Objekt mit `id` oder Name/Pfad) ist offen; die Hilfe `m30.als_id` normalisiert alle drei. `betrag` und `empfaenger` der Treffer werden nicht geprüft. Kombinationen, deren Wirkung die Definition nicht ordnet (gesperrt und zugleich Splitbuchung; anders kategorisiert und zugleich von einer früheren Regel getroffen), kommen in den Tests nicht vor.
  8. **Erklären (5.7):** `ergebnis` der Antwort ist `true`/`"wahr"` bzw. `false`/`"falsch"`. Bei `a and b` mit falschem `a` ist `b` `falsch` oder `nicht_ausgewertet`. Unbekannte `buchung_id`: 404 oder 422 `referenz_unbekannt` (offen).
  9. **Anwenden einer Regel (5.8):** Tests geben `testmenge` leer oder `stichtag` an. Unbekannte `buchung_ids`: 422 `referenz_unbekannt` wie in 3 (nicht geprüft, da nicht genannt).
  10. **Reihenfolge (5.5):** `details.fehlend` und `details.unbekannt` als Listen von IDs (Vergleich als Menge). Quelle der Änderung `manuell`.
  11. **Tag in der Bedingung gelöscht:** der Ausdruck enthält danach den Text `"#<id>"` mit der ID des gelöschten Tags; der Teil trifft nie.
  12. **`GET /api/ausdruck/sprache`:** geprüft werden die Feldnamen und Kurzformen aus 2.2, `nur_filter` und das Fehlen von `datum`, `jahr`, `kw` im Kontext `regel`; der Aufbau der übrigen Teile nicht. Fehlender `kontext` wird nicht geprüft (Vorgabe nicht genannt).
- **Begründung:** Keine Festlegung über die Definition hinaus (Auftrag „Umfang mit Augenmaß“); Tests dürfen nicht an geratenen Einzelheiten scheitern.
- **Bezug:** `ausdruecke.md`; `kategorisierung.md` 8; E-265.

## E-273 Umstellung der Datenbank und ältere Sicherungen sind in kontor-tests nicht prüfbar

- **Frage:** Definition 13: „Für die Datenbank-Umstellung lässt sich der Zustand ‚vor der Umstellung‘ nur in der Datenbank herstellen; den Weg legt der Test-Thread fest.“ Welchen Weg gibt es, auch für „Sicherungen der Versionen 1 bis 8 lassen sich weiter einspielen“?
- **Entscheidung:** Keinen innerhalb der Regeln von kontor-tests: Tests kennen das Datenbankschema nicht (CLAUDE.md), und eine Sicherungsdatei einer älteren `schemaversion` kann nur eine ältere Anwendung erzeugen; Fixtures entstehen nur aus dem Generator, der keine Anwendungsdatenbank baut. Anders als bei E-264 hilft hier auch keine Naht der Anwendung, weil der alte Zustand ein altes Schema ist. Beide Aussagen (Umstellung beim Start ohne Datenverlust; Einspielen der Versionen 1 bis 8) werden deshalb **nicht** durch Abnahmetests geprüft, sondern bleiben Sache der Entwicklungstests in kontor-app. Geprüft wird, was über die Schnittstellen sichtbar ist: Regeln der bisherigen Form bleiben gespeichert, wirken unverändert und überstehen Sicherung und Einspielen (`schemaversion` ≥ 9, Rundreise mit Tags und mit Regel ohne Kategorie).
- **Begründung:** Rollentrennung; E-091 (Tests verändern `kontor.sqlite` nur schemaunabhängig).
- **Bezug:** `sicherung.md` 3.4, 12; `kategorisierung.md` 8.9; E-264.

## E-274 M30: Lesarten und Prüfmerkmale der Oberflächentests

- **Frage:** Was prüfen die Browsertests, wo die Definition nur Kennungen nennt?
- **Entscheidung:** (1) Nur genannte `data-testid`, Attribute (`data-status`, `aria-invalid`, `aria-expanded`, `aria-pressed`, `data-anzahl`, `data-tags`, `data-geladen`, `data-veraltet`) und wörtlich genannte Texte („(keine Aktion)“, „+ Name“, „Noch keine Tags.“, „(alle)“, „(n von m)“, „Die Regel braucht eine Kategorie oder mindestens einen Tag.“, „Keine Buchung geändert.“, „(neu)“). (2) **`filter-unterkonten` und `filter-konto`** (M11) stehen nicht in der Liste der ersetzten Einzelfelder; sie bleiben nach `oberflaeche.md` 22.2 in `filter-leiste` und werden über `filter-baukasten-umschalten` erreicht – **Annahme**, vom Implementierungs-Thread zu bestätigen. (3) `filter-alt-<name>` trägt den Namen des Adressparameters (`filter-alt-betrag_min`, `filter-alt-kategorie_id` …). (4) `filter-zuruecksetzen` wird über `m8.filter_zuruecksetzen` bedient (klappt den Baukasten auf, falls der Knopf nicht sichtbar ist). (5) Die Wirkung eines Filters wird an der Liste (gleich `GET /api/buchungen` mit demselben `filter` und `stichtag` nach der Uhr der App) und an `filter=` in der Adresse geprüft; die Tests benutzen nur Ausdrücke ohne relative Datumsangaben oder die Zeitraum-Knöpfe mit der Mock-Uhr. (6) Baukasten: geprüft wird die Kopplung in Richtung Ausdruck → Baukasten (eine Zeile `bk-0-feld` bzw. die erste vorhandene Zeile erscheint) nur als Vorhandensein von Zeilen; welche Werte `bk-<n>-feld`/`-op` annehmen und ob `n` bei 0 oder 1 beginnt, ist offen und wird nicht geprüft. (7) Regeleditor und Testbereich: Bedienung über das Ausdrucksfeld (Vorgabe-Reiter); Anwenden über `regel-test-anwenden` und `regel-anwenden-ok`; Ergebnisse werden über REST geprüft. Nicht geprüft: Ziehen in der Regelliste (nur Alt+↑/↓), Vervollständigung, Hervorhebung, Kopieren, `regel-uebernehmen`, „Warum?“ über den Klick hinaus, Tastenkürzel `f …` außer `f a`. (8) Tag-Dialog: die 50er-Grenze nicht geladener Buchungen wird nicht geprüft. (9) Nur Desktop; keine `kern`-Tests.
- **Begründung:** Auftrag („Rate keine Einzelheiten der Oberfläche“); E-255, E-265 Punkt 12.
- **Bezug:** `oberflaeche.md` 39.

## E-275 Selbstprüfung für M30

- **Frage:** Welche neuen oder geänderten Kern-Tests bekommen Referenzteile und Mutanten?
- **Entscheidung:** **M30** wird wie M18–M20, M23, M24, M27 und M29 ausgelassen (`OHNE_REFERENZ` um `m30`): Die Ausdruckssprache (Zerlegung, Datumsangaben, kanonische Form, Fehlerstellen) wäre eine zweite vollständige Implementierung; die Abnahme ist der Lauf gegen die App. Die Kern-Tests von M2, M3 und M9 sind **unverändert** und laufen weiter gegen die Referenz, die die neuen Regel-Felder nicht kennt (`m3.regel_zustand` ist dort die Identität; das Schema lässt beide Formen zu). In der Referenz-Oberfläche heißt der Umschalter der Filterleiste jetzt `filter-baukasten-umschalten` (für die geänderten Kern-Browsertests von M11 und M12); sonst keine Referenzänderung, kein neuer Mutant, der Mutant `m12_filter_offen` bleibt.
- **Begründung:** CLAUDE.md (Referenz klein halten); Auftrag „Was zu tun ist“ 5; E-225, E-243, E-256, E-266.
- **Bezug:** E-149, E-266.

## E-276 M30: Nachträge zu den Prüfmerkmalen

- **Frage:** Welche Lesarten sind beim Schreiben der M30-Tests zu E-272 und E-274 hinzugekommen?
- **Entscheidung:** (1) **Baukasten** (ergänzt E-274 Punkt 6): Zusätzlich zur Richtung Ausdruck → Baukasten (für `betrag > 20` erscheint mindestens eine Zeile mit `bk-…-feld`, `-op`, `-wert`, `-weg`) wird die Gegenrichtung geprüft: Das Entfernen der Zeile (`bk-…-weg`) nimmt den Teil aus dem Ausdruck. Der Hinweis `filter-baukasten-hinweis` wird an `baukasten_faehig` aus `POST /api/ausdruck/pruefen` gemessen; welche Ausdrücke in den Baukasten passen, legt die Definition nicht fest. (2) **„Als Regel speichern…“ und „Bearbeiten“** haben keine genannte Kennung; die Tests finden sie über den genannten Text (Menüeintrag) bzw. über einen Knopf mit dem zugänglichen Namen „Bearbeiten“ in `regel-<id>`. Die Rückfrage vor dem Regeleditor wird, falls sie als `bestaetigen-dialog` (9.5) erscheint, mit `bestaetigen-ja` bestätigt. (3) **`regel-kategorie`** wird als `<select>` gelesen („erster Eintrag … mit leerem Wert“), `regel-anwenden-abweichende` als Ankreuzfeld oder als Element, das eines enthält. (4) **Namensvorschlag:** geprüft wird, dass der Platzhalter den ersten Text der Bedingung, „→“ und `#<Tag>` enthält und beim Speichern als Name übernommen wird. (5) **Ein Rückgängig-Schritt** für „neuer Tag und Regel“ und für das Umsortieren heißt: ein Klick auf `rueckgaengig-knopf` nimmt beides zurück; ob dahinter eine Änderung oder eine Gruppe steht, ist offen. (6) **Meldung nach dem Anwenden:** geprüft wird die Zahl der geänderten Buchungen im Bereich `meldungen`. (7) **Zählzeile** `test-zahlen`: „n Treffer in m Buchungen“ mit m = `testmenge_anzahl`. (8) **Nicht geprüft** (kein herstellbarer oder kein genannter Zustand): Fehlermeldungen mit Feld und Regel (`oberflaeche.md` 39.6 – über die Oberfläche lässt sich ohne Kenntnis ihrer eigenen Prüfungen kein 422 `validierung` gezielt auslösen), `regel-anwenden-nichts` (der Anwenden-Knopf ist gesperrt, wenn sich nichts ändern würde; der Fall ist nur über einen anderen Umfang erreichbar), `test-leer`/`test-alle`, `regel-prioritaet`, `regel-baukasten-*`, `regel-uebernehmen`, Duplizieren. (9) **REST, Ergänzung zu E-272:** Gleichwertigkeit der bisherigen Form wird doppelt geprüft – beide Regeln treffen exakt dieselben Buchungen, und beide stimmen mit der eigenen Rechnung überein; bei Betragsbedingungen bleibt die Umbuchung im Vergleich mit der eigenen Rechnung außen vor (E-272 Punkt 4), nicht aber im Vergleich der beiden Regeln. Bei `POST /api/regeln/reihenfolge` mit unveränderter Reihenfolge und Prioritäten 10, 20, … entsteht keine Änderung (`protokoll.md` 4, Grundregel).
- **Begründung:** Keine Festlegung über die Definition hinaus; Auftrag „Rate keine Einzelheiten der Oberfläche“.
- **Bezug:** `oberflaeche.md` 39; `kategorisierung.md` 8; E-272, E-274.

## E-277 Übernahme der Definition 3 als Meilenstein 31

- **Frage:** Auftrag vom 2026-11-22, Paket 3: Die Definition „übrige Features seit M28“ trägt keine gesonderte Freigabe. Wird sie übernommen, unter welcher Nummer und wohin?
- **Entscheidung:** Ja – der Auftraggeber hat ausdrücklich „direkt weiter“ entschieden (Kopf der Definition, Auftrag); keine gesonderte Freigabe. Nummer **M31** (nächste freie nach M30). Gliederung: Lernmodell `lernmodell.md` 8–10, Berichte `berichte.md` 6, Bestellnummer-Mails `erwartungen.md` 14, Branch `version.md` 6, Testinstanz `betrieb.md` 9, Konfiguration `python-api.md` 22, Protokoll `protokoll.md` 23, Sicherung `sicherung.md` 13, Oberfläche `oberflaeche.md` 40; Definition unverändert unter `spec/definitionen/`. Die Hinweise der Definition auf spätere Änderungen im Sammelbranch (Standardkategorie, Statistik, Meldung mit „Rückgängig“) gehören zu Paket 4 und werden hier nicht umgesetzt. Die Bedingung „Empfänger ohne Standardkategorie“ der automatischen Regeln steht in der Spezifikation, wird aber nicht geprüft (entfällt mit Paket 4).
- **Begründung:** Auftrag „Was zu tun ist“ 1–2; Definition 3, Kopf.
- **Bezug:** K 5, K 7, K 11, K 13, K 14; E-268.

## E-278 Schema und Version für M31

- **Frage:** Wie wird `openapi.yaml` erweitert, wo die Definition keine Antwortfelder nennt?
- **Entscheidung:** Version 2.24.0. Neu: `GET /api/buchungen/{buchung_id}/lernmodell` (`LernErklaerung`, `LernMerkmal`, `LernAehnlich`), `GET /api/lernmodell/uebersicht` (`LernUebersicht`, frei), `GET`/`PUT /api/lernmodell/einstellungen` (`LernEinstellungen`, `LernEinstellungenAenderung`, streng), `POST /api/mock/lerndaten` (200 oder 201, `MockLerndaten` frei, 409 `nur_mock_modus`/`bestand_nicht_leer`), `GET /api/berichte/monat` (`MonatsBericht` mit Pflichtfeldern nach E-282, sonst offen) und `GET /api/berichte/{vertraege,jahr,vorschau,vermoegen,kategorien,empfaenger,geldfluss,qualitaet,tags}` (`BerichtFrei`). Geändert: `LernZustand.schwelle_promille` 500–990 statt `const 700`, `sicherheit` in `LernVorhersage`/`LernAnwendung` ab 500; `Regel.automatisch`/`empfaenger_id` mit Bedeutung (`lernmodell.md` 9.3); `Empfaenger` und `EmpfaengerZustand` mit optionalem `lernregel_gesperrt: true`; `MailNachrichtEintrag.angehaengt` (`MailAngehaengt`, streng, alle Felder der Definition Pflicht). Neuer Fehlercode `bestand_nicht_leer`. Objekte mit offenem Aufbau tragen `additionalProperties: true`. `tests/spec`: `test_m31_schemas`, `OPERATIONEN_M31`; `test_m30_schemas` prüft die Version mit `>=`.
- **Begründung:** Definition 3 (D-182 bis D-184, D-206, D-208, D-217); `tests/hilfen/api.py` prüft jede Antwort gegen das Schema – ein geratenes strenges Schema würde Antworten der Anwendung grundlos verwerfen.
- **Bezug:** E-029, E-124, E-270.

## E-279 M31: automatische Regeln – Lesarten

- **Frage:** Was ist an D-179/D-184 offen, und wie wird es geprüft?
- **Entscheidung:** (1) **Kategorie** `K` = die häufigste Kategorie des Empfängers in `T`; Quoten exakt (`100 · Anzahl_K ≥ 95 · Anzahl`). (2) **Fenster:** die 365 Tage bis `d` (jüngste Buchung des Empfängers in `T`, höchstens heute); ob der Tag `d − 365` dazugehört, ist offen – Testfälle liegen nie an dieser Grenze, und die Referenzrechnung für die Mock-Lerndaten lässt Empfänger aus, bei denen beide Lesarten verschieden ausfallen. (3) **Bedingung:** zugelassen sind `bedingungen == [{"feld": "empfaenger", "operator": "gleich", "wert": <Name>}]` oder ein Ausdruck, der in einem Regeltest dieselben Buchungen trifft; geprüft wird zusätzlich die Trefferliste über `POST /api/regeln/test`. (4) **Änderung:** genau eine Änderung `lernmodell`/`regel_automatisch` mit der ID direkt nach der auslösenden; `gruppe` wird nicht geprüft (die Oberfläche fasst beide zusammen). (5) **Sperre:** `lernregel_gesperrt: true` steht in der Protokollform; ob auch `GET /api/empfaenger` es liefert, ist offen (beide Fälle zugelassen; die Hilfe `m31.bestand` ergänzt es aus dem bekannten Zustand). (6) **Auslöser:** geprüft für `POST /api/buchungen`, `PATCH`, Kategorie setzen und das Laden der Mock-Lerndaten (Quelle `import`); keine Regel nach Synchronisation, `POST /api/regeln/anwenden`, `POST /api/lernmodell/anwenden`, Rückgängig und `PUT /api/lernmodell/einstellungen`. (7) Nicht geprüft: Standardkategorie (E-277), Buchungen mit Datum nach heute, die Oberfläche (Meldung, ein Rückgängig-Schritt).
- **Begründung:** Keine Festlegung über die Definition hinaus; Tests dürfen nicht an Randfällen der Zählweise scheitern.
- **Bezug:** `lernmodell.md` 9; E-271.

## E-280 M31: Erklärung, Übersicht und Einstellungen des Lernmodells

- **Frage:** Die Definition nennt für `GET /api/buchungen/{id}/lernmodell` nur einen Teil der Feldnamen. Welche gelten?
- **Entscheidung:** **Festlegung des Test-Threads** (die Implementierung richtet sich danach oder meldet einen Widerspruch): Vorhersage als Objekt `vorhersage` (`LernVorhersage`); Merkmale als Liste `merkmale` mit `merkmal` (Zeichenkette nach `lernmodell.md` 2); ähnliche Buchungen als Liste `aehnliche` mit `buchung_id`. Weitere Felder (drei häufigste Kategorien, Grundwert) sind frei. Geprüft: `grund` in allen vier Fällen, `beste_kategorie_id`, `vergleich_kategorie_id`, je bekanntem Merkmal `anzahl`, `anzahl_kategorie`, `anzahl_vergleich`, `faktor_promille` exakt gegen das Orakel (`tests/hilfen/lern_orakel.py`), `aehnliche` (höchstens 5, nur aus `T`, Gewicht nicht steigend, eindeutig beste zuerst). Übersicht: nur 200, Objekt, keine Änderung. Einstellungen: Vorgaben, Teiländerung, 422 je Fehlerart, Wirkung der Schwelle auf Vorhersage, Anwenden und `GET /api/lernmodell`, Fortbestand über eine neue App-Instanz auf derselben Datenbank, kein Protokoll, keine Änderung an `anzahl`/Inhaltsprüfsumme der Sicherung, nach dem Einspielen unverändert.
- **Begründung:** Definition 3, Kopf („genaue Feldnamen einer Antwort“ entscheidet der Test-Thread).
- **Bezug:** `lernmodell.md` 8.

## E-281 M31: Mock-Lerndaten

- **Frage:** Was wird an `POST /api/mock/lerndaten` geprüft?
- **Entscheidung:** Status 200 oder 201 (nicht genannt), Antwortkörper frei; danach genau 3000 Buchungen mit Datum 2022-09-01 bis 2026-10-31, mindestens eine auf „Unkategorisiert“ und mindestens eine kategorisierte; genau eine Änderung `import`/`mock_lerndaten`, Rückgängig hinterlässt einen Bestand ohne Buchungen; 409 `nur_mock_modus` im Echtmodus (vor jeder anderen Prüfung) und 409 `bestand_nicht_leer` mit einer Buchung. Mit `regeln_automatisch` entspricht die Menge der Empfänger mit automatischer Regel der eigenen Rechnung nach `lernmodell.md` 9.1 (E-279 Punkt 2). Inhalte der Lerndaten (Muster, Fehlquote) werden nicht geprüft.
- **Begründung:** Definition D-181, D-184.
- **Bezug:** `lernmodell.md` 10.

## E-282 M31: Monatsbericht und weitere Berichte

- **Frage:** Die Definition nennt für die Berichte keine Antwortfelder. Was wird festgelegt und geprüft?
- **Entscheidung:** **Festlegung des Test-Threads** für den Monatsbericht (Pflichtfelder `monat`, `konto_ids`, `ausgaben`, `einnahmen`, `fest`, `variabel`, `umbuchungen`, Bedeutung `berichte.md` 6.2; Ausgaben als positive Cent). Darlehenskonto = Konto, das ein Kredit als `konto_id` führt. Fehler: Form von `monat` → 422 `validierung`, unbekanntes Konto → `referenz_unbekannt`, Nicht-Bestandskonto → `konto_ungueltig` (wie `berichte.md` 3). Geprüft an einem kleinen Bestand mit eigener Rechnung: Ausgabe, Einnahme, Erstattung, Umbuchung, Anfangsbestand (neutral), Zinsanteil einer Darlehensbuchung, feste Miete als Serie (gleichbleibender Betrag, sechs Monate), Vorgabe der Konten und Auswahl. Nicht geprüft: Hochrechnung, Vergleiche, Ausreißer, Größenklassen, laufender Monat. Für die neun weiteren Berichte nur: 200 ohne Parameter (Objekt), unbekannter Parameter → 422 `validierung`, keine Änderung im Protokoll und in der Sicherung.
- **Begründung:** Ohne genannte Felder lässt sich der Inhalt nicht prüfen, ohne zu raten; der Monatsbericht hat in D-206 eine eindeutige Rechenregel.
- **Bezug:** `berichte.md` 6; E-059.

## E-283 M31: Mails über die Bestellnummer

- **Frage:** Wie werden D-208/D-209 geprüft?
- **Entscheidung:** Mock-Modus mit Mails einer Mock-Datendatei (ohne Rohfassung) und Buchungen über REST; Echtmodus mit IMAP-Attrappe für Mails mit HTML-Teil, Verweisadresse und PDF-Anhang. Geprüft: aus in der Vorgabe; Treffer in Betreff, Text, Zweck, Empfänger und im umbrochenen Zweck; keine Treffer bei angrenzender Ziffer und anderer Nummer; Absender beliebig; Teillieferungen; zwei Postfächer mit derselben Nachrichten-ID; kein zweites Dokument gleichen Inhalts (über `POST /api/dokumente/aus-mail` in einer Instanz ohne die Einstellung, dann eine Instanz mit ihr auf derselben Datenbank); Auslösung nach Abruf und nach Synchronisation; genau eine Änderung `mail`/`bestellmail_anhaengen` mit Einträgen nach `m20.bestand`, Rückgängig/Wiederholen; zweiter Abruf ohne Änderung; nach Rückgängig und nach Lösen kein erneutes Anhängen; nach dem Einspielen einer Sicherung spätestens mit dem nächsten Abruf wieder angehängt; `angehaengt` (Felder, `nummer`), `stand.zugeordnet` und Filter `zuordnung=zugeordnet`; ohne Einstellung kein Feld. `warum` nur nicht leer. Nicht geprüft: Logzeile, maskierte Nummern (nur Anzeige, D-176).
- **Begründung:** Definition D-208, D-209.
- **Bezug:** `erwartungen.md` 14; `dokumente.md` 2.2; E-216.

## E-284 M31: Umgebungsdateien und Testinstanz

- **Frage:** Was ändert sich an `kontor.env`, und was ist an der Testinstanz prüfbar?
- **Entscheidung:** `kontor.env` setzt `KONTOR_MAIL_ABGLEICH=0`, `KONTOR_MAIL_BESTELLNUMMER=1`, `KONTOR_REGELN_AUTOMATISCH=1` (ändert die Pflichttabelle `betrieb.md` 3 und E-216). Der M20-Test `test_ausgelieferte_umgebungsdatei` erwartet jetzt `0` und `mail_abgleich is False` (die auskommentierte Frist bleibt). Testinstanz: statische Prüfung von `kontor-test.service`, `kontor-test.env`, Vorhandensein von `kontor-test.sh` und Importierbarkeit von `kontor.testinstanz` (`betrieb.md` 9). „Zeitgesteuerter Abruf und Mail-Abruf abgeschaltet“ nennt keine Variablen und wird nicht geprüft; ebenso wenig Kommandozeile, Datenkopie, Skript (root, systemd, Netz).
- **Begründung:** Definition D-205, D-208, D-213; Rollentrennung (keine Systemeingriffe in Tests).
- **Bezug:** `betrieb.md` 3, 9; E-216.

## E-285 M31: Branch-Anzeige

- **Frage:** Wie lässt sich D-178 prüfen, wenn der Branch vom Quellbaum der installierten Anwendung abhängt?
- **Entscheidung:** Bedingt: Enthält die Hülle `zweig-link`, muss dieser ein `<a>` mit `href` auf `/tree/<Branch>` (Zeichen aus `[A-Za-z0-9._/-]`, nicht `main`) und `target="_blank"` sein, `version-knopf` „Über“ heißen und das About-Fenster `ueber-zweig` mit dem Branch zeigen; sonst gilt `oberflaeche.md` 24 unverändert und `ueber-zweig` fehlt. Die M13-Tests der Knopfbeschriftung (`test_eine_version_ueberall`, `test_versionsknopf_in_der_huelle`, `test_versionsknopf_als_letztes_element_der_navigation`) erwarten deshalb „Über“, wenn die Hülle `zweig-link` enthält (Hilfe `m13.knopf_text_soll`). `GET /api/version` bleibt geprüft wie bisher.
- **Begründung:** Tests dürfen nicht vom Branch der geprüften Anwendung abhängen; Abnahme läuft auf main (Auftrag).
- **Bezug:** `version.md` 6; E-176 bis E-180.

## E-286 M31: Einstellungen in Bereichen

- **Frage:** Die Definition nennt die Bereiche nur mit Titeln. Wie heißen sie in der Adresse, und welches Element liegt wo?
- **Entscheidung:** **Festlegung:** `allgemein`, `bank`, `mail`, `benachrichtigungen`, `sicherheit`, `daten` (erstes Wort des Titels, klein, ohne Umlaut). Zuordnung der bisherigen Elemente nach den Themen der Definition (`oberflaeche.md` 40.3): `abmelden` gehört zu „Anmeldung“ (`sicherheit`), `status-modus` zu „Angaben zur Instanz“ (`allgemein`), `pin-status`/`pin-verwerfen` zu `bank` (auch im Mock-Modus). Die Hilfe `m31.einstellungen_oeffnen(seite, server, bereich)` öffnet `/einstellungen?bereich=<name>`; `m31.BEREICH_VON` hält die Zuordnung an einer Stelle. `m29.bankzugang_oeffnen` öffnet `/einstellungen?bereich=bank`. Geprüft: je Bereich ein sichtbares Leitelement und unsichtbare Leitelemente der anderen; ohne Angabe und mit unbekanntem Wert Desktop = `allgemein`, Handy = kein Leitelement sichtbar; je Bereich `einstellungen-status-<name>` mit gültigem `data-zustand`; `einstellungen-suche` vorhanden; Bereichswechsel über die Adresse ohne neuen Tab; Produkt-ID leer → Feld `bankzugang-produkt_id` ohne Aufklappen sichtbar. Nicht geprüft: Texte, Suchtreffer, Synonyme, Rückweg am Handy, Schritte des Bankzugangs, neue Kennungen außer `einstellungen-…`.
- **Begründung:** Auftrag (Bereich über die Adresse); „Rate keine Einzelheiten der Oberfläche“ – die Festlegungen sind die kleinsten, die die Tests brauchen.
- **Bezug:** `oberflaeche.md` 40.3; E-265.

## E-287 M31: Gruppierung mit Abschnitt und Tiefe

- **Frage:** Wie werden D-211/D-212 geprüft, und was wird aus den M28-Tests?
- **Entscheidung:** `m28.perioden_soll` kennt die Ebene `abschnitt` (Schlüssel `JJJJ-MM-a<n>`) und eine Tiefe (Vorgabe volle Tiefe); `m28.perioden_text` liefert für Abschnitte „TT.–TT.MM.“ mit dem tatsächlichen Monatsende. `test_gruppierung_nach_datum` und `test_gruppierung_direkt_aufsteigend_und_unbekannter_wert` bleiben inhaltlich, rechnen aber mit der Abschnittsebene (`?gruppierung=jahr` bleibt ein unbekannter Wert). `test_kuerzel_aktionen_und_vortasten` bleibt unverändert (`v g` setzt weiter `gruppierung=datum`). Neu geprüft: die fünf Knöpfe mit genau einem gedrückten, `tiefe` in der Adresse (nicht bei „Tag“), Balken je Tiefe gegen die eigene Rechnung, unbekannte `tiefe` = volle Tiefe, `v g` in der Reihenfolge, Zuklappen über den Tiefenwechsel.
- **Begründung:** Definition D-211, D-212 („Folge für die Abnahme“).
- **Bezug:** `oberflaeche.md` 37.6, 40.5; E-255.

## E-288 M31: übrige Oberfläche

- **Frage:** Was wird von 40.1, 40.2, 40.4 und 40.6 geprüft?
- **Entscheidung:** (1) Namen: in der Buchungsliste der Kontoansicht „AMAZON“ → „Amazon“, „CAFE AM MARKT“ → „Cafe am Markt“, „eBay GmbH“ unverändert, REST unverändert. Abkürzungen/Rechtsformen und die Gliederung des Verwendungszwecks werden nicht geprüft (keine Kennungen, keine vollständige Liste). (2) Lernmodell: `details-einschaetzung` mit Grund und je Kandidat ab 10 Promille `details-kandidat-<id>`; `lern-warum` vorhanden; `/lernmodell` als Route (Hülle 200) und ohne Navigationseintrag. (3) Mail-Datum: `dokument-datum-<id>` mit `data-zeitpunkt` am Mail-Dokument (gleicher Zeitpunkt wie `datum` der Mail-Ansicht), keines am PDF. (4) Berichtswahl: `/berichte/monat` endet bei `art=monat`, `/berichte?art=<name>` lädt für jede Art die Seite ohne Skriptfehler. Nur Desktop.
- **Begründung:** Auftrag („Rate keine Einzelheiten der Oberfläche“).
- **Bezug:** `oberflaeche.md` 40.

## E-289 Widerspruch W-015: 600 Zeilen des Diagnoseprotokolls

- **Frage:** `test_m29_diagnose.py::test_hoechstens_600_zeilen_aelteste_zuerst` setzte gleiche Zeilenzahl je Abruf voraus; die Anwendung schreibt beim ersten Abruf mehr Zeilen (einmalige Angaben). Wer hat recht?
- **Entscheidung:** Die Spezifikation (`bankzugang.md`, E-265 Punkt 11) legt die Zeilenzahl je Abruf nicht fest; der Test ist zu streng. Er wiederholt den Abruf jetzt, bis 600 Zeilen erreicht sind (höchstens 300 Abrufe), verlangt, dass jeder Abruf vor Erreichen der Grenze Zeilen hinzufügt, und prüft danach wie bisher genau 600 und das Herausfallen der ältesten.
- **Begründung:** W-015 (Text des Implementierungs-Threads); Spezifikation unverändert.
- **Bezug:** `bankzugang.md` 5; E-265, E-267.

## E-290 Widerspruch W-016: Benutzerparameter ohne neue Version

- **Frage:** Die FinTS-Attrappe änderte mit `upd_ohne_konten` den Inhalt der UPD, meldete aber dieselbe Version; eine Bank tut das nicht (`fints.md` 6).
- **Entscheidung:** Die Attrappe ist falsch. Ihre UPD-Version hängt jetzt von den Betriebsarten `upd_ohne_kontoart`, `upd_ohne_iban`, `upd_ohne_konten` ab (Vorgaben unverändert Version 1 bzw. 2 mit Saldo), sodass jedes Umschalten eine neue Version meldet und ein Kunde mit bekannter Version die neuen UPD bekommt. Der Test `test_konten_abrufen_behaelt_auswahl_und_ersetzt_die_liste` bleibt unverändert.
- **Begründung:** W-016; E-263 (Attrappe auf Protokollebene wie eine Bank).
- **Bezug:** `fints.md` 6; E-263.

## E-291 M31: Nachziehen früherer Meilensteine

- **Frage:** Welche früheren Tests und Hilfen ändern sich?
- **Entscheidung:** (1) Einstellungen (D-207, „Folge für die Abnahme“): Die sieben genannten Browsertests öffnen den Bereich über `m31.einstellungen_oeffnen` – M8 `test_einstellungen_geheimnis_und_sicherung` (`benachrichtigungen`, `mail`, `daten`), `test_einstellungen_test_benachrichtigung_mock` (`allgemein` und `benachrichtigungen`), `_ntfy` (`benachrichtigungen`), `test_pin_dialog` (`bank`), `test_schreiben_mit_csrf_und_abmelden` (`sicherheit`); M23 `test_einstellungen_schutz` und `test_einstellungen_reihenfolge` (`sicherheit`; die Reihenfolge „nach dem PIN-Abschnitt“ gilt nur noch, wenn beide im selben Bereich stehen); M28 `test_abmelden_vergisst_person` (`sicherheit`); dazu `test_ohne_anmeldung_kein_abmelden` (`sicherheit`), M8 `test_einstellungen_ohne_plugin` und der Postfach-Teil von `test_seiten_im_mindestumfang` (Bereich `mail`). `m29.bankzugang_oeffnen` nutzt den Bereich `bank`. (2) M13 nach E-285. (3) M20 `test_ausgelieferte_umgebungsdatei` nach E-284. (4) M28 Gruppierung nach E-287. (5) M29 Diagnose nach E-289, Attrappe nach E-290. (6) M4 `test_m4_lernmodell` erwartet unverändert `schwelle_promille = 700` (Vorgabe). Alle übrigen Tests der Liste `abnahme-stand-main.txt` mit Bezug zu anderen Paketen bleiben unverändert.
- **Begründung:** Definition 3; Auftrag „Frühere Tests nachziehen“.
- **Bezug:** E-254, E-265, E-271.

## E-292 Selbstprüfung für M31

- **Frage:** Welche neuen oder geänderten Kern-Tests bekommen Referenzteile und Mutanten?
- **Entscheidung:** **M31** wird wie M18–M20, M23, M24, M27, M29 und M30 ausgelassen (`OHNE_REFERENZ` um `m31`): Erklärung und Einstellungen des Lernmodells, automatische Regeln, Berichte und Bestellnummer-Mails bräuchten eine zweite Implementierung; die Abnahme ist der Lauf gegen die App. Die geänderten Kern-Tests von M13 laufen gegen die Referenz (sie hat keinen `zweig-link`, die Erwartung bleibt „Version …“); der geänderte M20-Test ist wie ganz M20 ausgelassen. Kein neuer Mutant.
- **Begründung:** CLAUDE.md (Referenz klein halten); E-266, E-275.
- **Bezug:** E-149, E-275.

## E-293 Übernahme der Definition 4 als Meilenstein 32

- **Frage:** Auftrag vom 2026-11-22, Paket 4: Die Definition „Sammelbranch `feature/sammel3`“ (D-218 bis D-239) trägt keine gesonderte Freigabe. Wird sie übernommen, unter welcher Nummer und wohin?
- **Entscheidung:** Ja – der Auftraggeber hat ausdrücklich „direkt weiter“ entschieden (Kopf der Definition, Auftrag); keine gesonderte Freigabe. Nummer **M32** (nächste freie nach M31). Fachlich neues Dokument `sammel3.md` (Gliederung nach den Abschnitten der Definition), Oberfläche `oberflaeche.md` 41, Hinweise in `datenmodell.md` 20, `buchhaltungspflege.md` 11, `sammel.md` 6, `erwartungen.md` 5.2/15, `sicherung.md` 14, `protokoll.md` 24, `python-api.md` 23, `betrieb.md` 10. Definition und Anlagen (`ANBIETER.md`, `HTTPS.md`, `TESTINSTANZ.md`) unverändert unter `spec/definitionen/`; die Anlagen `ANBIETER.md` (Format) und `HTTPS.md` (Ablauf der Skripte) gelten als Teil des Vertrags, soweit `sammel3.md` auf sie verweist. M32 ist **nicht rückwärtskompatibel** (E-029 gilt nicht; frühere Tests nach E-307).
- **Begründung:** Auftrag „Was zu tun ist“ 1–2; Definition 4, Kopf.
- **Bezug:** K 4, K 5, K 7, K 11, K 13, K 14; E-277.

## E-294 Schema und Version für M32

- **Frage:** Wie wird `openapi.yaml` geändert?
- **Entscheidung:** Version 2.25.0. Entfernt: `GET /api/statistik` und die Schemas `Statistik…`. Neu: `GET /api/empfaenger/anzahlen` (`EmpfaengerAnzahl`), `GET /api/empfaenger/{empfaenger_id}/konten` (`EmpfaengerKonto`), `POST /api/mail/nachrichten/{nachricht_id}/buchung` (201 `Dokument`), `GET /api/dokumente/{dokument_id}/mail/bilder` (`MailBilder`), `GET /api/konfiguration` (`Konfiguration`, Einträge mit `additionalProperties: true`, `wert`/`vorgabe` beliebig). Parameter `suche`, `gruppieren` (`ja`/`nein`) der Mail-Liste und `bilder` (`ja`/`nein`) der Mail-Ansicht. Geändert: `MailNachrichtEintrag.gruppe` (optional), `MailAngehaengt.betrag` (optional im Schema, Pflicht in den M32-Tests) und `nummer` ohne Muster; `anbieter` der Erwartungen als Name (`^[a-z0-9_]+$`) oder null; `Erwartung`, `ErwartungZustand`, `ErwartungDetail` mit optionalem `wiederholung` (`ErwartungWiederholung`), `ErwartungNeu`/`ErwartungAenderung` mit `wiederholung` und `wiederholung_bis`. Fehlercodes `konto_existiert`, `wiederholung_nur_geplant`, `wiederholung_fehlt`. `standardkategorie_id` bleibt im Schema (älteres Protokoll). `tests/spec`: `test_m32_schemas`, `OPERATIONEN_M32`; `test_m27_schemas` prüft das Fehlen von `Statistik`, `test_m31_schemas` die Version mit `>=`, `test_m20_schemas`/`test_m24_schemas` nehmen das optionale `wiederholung` aus dem Vergleich der Felder.
- **Begründung:** Definition 4 (D-220, D-221, D-226 bis D-230, D-235, D-236, D-238); ein strenges Schema für nicht genannte Felder wäre geraten.
- **Bezug:** E-029, E-124, E-278.

## E-295 M32: Kontonamen je Ebene – Lesarten

- **Frage:** Was lässt D-218 offen?
- **Entscheidung:** (1) Vergleich `strip().casefold()`; Umlaute zählen als verschieden (die Definition nennt nur Groß-/Kleinschreibung und Leerraum). (2) `details.konto_ids`: nicht leere Liste von IDs, die das vorhandene gleichnamige Konto enthält; mehr wird nicht geprüft. (3) Prüfreihenfolge: bisherige Prüfungen zuerst, bei Rückgängig also Zustand und Bezüge (409 `rueckgaengig_konflikt`) vor `konto_existiert`; das Orakel des M3-Zufallstests (`test_zufaelliges_rueckgaengig_gegen_orakel`) rechnet so. (4) Umbenennen in den eigenen Namen in anderer Schreibweise ist erlaubt. (5) Bereinigen beim Import gehört zur Importänderung (eine Änderung, Rückgängig des Imports stellt den Bestand her); Warnung `konto_zusammengefasst` bzw. `konto_umbenannt` mit `referenz` = Name aus der Datei (geprüft: der Name ist in `referenz` enthalten). (6) Zusatz „ (2)“ mit Leerzeichen; geprüft beim Import (GnuCash, Eigenkapitalkonto „Unausgeglichen“) und bei der Synchronisation mit `sync_konten_anlegen`. (7) Technisches Konto „Unkategorisiert“: ein vorhandenes gleichnamiges Eigenkapitalkonto ohne Kennung wird übernommen und erhält `extern_id = "kontor:unkategorisiert"` (sonst fände `synchronisation.md` 4.2 es nicht wieder). (8) Nicht prüfbar: Bereinigen des Altbestands beim Start und beim Einspielen (ein Bestand mit gleichnamigen Geschwistern lässt sich über die Schnittstellen nicht mehr herstellen; Sicherungen werden nicht von Hand gebaut, vgl. E-273).
- **Begründung:** Definition D-218; Tests dürfen nur prüfen, was die Definition festlegt.
- **Bezug:** `sammel3.md` 1; `datenmodell.md` 2, 10.3.

## E-296 M32: Standardkategorie entfällt – Lesarten

- **Frage:** Was gilt nach D-219 an den Schnittstellen?
- **Entscheidung:** (1) `POST`/`PATCH /api/empfaenger` mit `standardkategorie_id` ≠ null → 422 `kategorie_ungueltig` (auch für gültige Kategorien), `null` ohne Wirkung, Antworten immer `null`. (2) Erfassen (`buchhaltungspflege.md` 3) ohne `kategorie_id` bucht auf „Unkategorisiert“ ohne Vorschlag; die Definition nennt für das Erfassen nur den Wegfall der Stufe, und Regeln gelten bei von Hand angelegten Buchungen nach M30 nicht. (3) Konto löschen und Kategorien zusammenführen melden `empfaenger_geaendert = []`. (4) Nicht prüfbar: Umwandlung beim Start und beim Einspielen älterer Sicherungen, ebenso die Umbenennung der Personen-Tags (D-223) – beides setzt einen Bestand voraus, den die Schnittstellen nicht mehr erzeugen (E-273).
- **Begründung:** Definition D-219 („ein anderer Wert wird mit 422 `kategorie_ungueltig` abgelehnt“), D-223.
- **Bezug:** `sammel3.md` 2.1, 5.

## E-297 M32: Empfänger-Endpunkte

- **Frage:** Die Definition nennt für `GET /api/empfaenger/{id}/konten` und `GET /api/empfaenger/anzahlen` nur die Felder. Was gilt sonst?
- **Entscheidung:** **Festlegung:** Konten = Bestandskonten mit mindestens einer Buchung des Empfängers mit Split darauf; `anzahl` = Zahl solcher Buchungen (je Konto einmal); Reihenfolge `anzahl` absteigend, dann `konto_id`; ohne Buchungen `[]`; unbekannter Empfänger 404. Anzahlen: Buchungen je Empfänger, nur Empfänger mit Buchungen, nach `empfaenger_id` aufsteigend. Beide nur lesend (kein Protokoll).
- **Begründung:** „die meistbenutzten zuerst“ (D-220), „Empfänger ohne Buchung fehlen“ (D-236/10); eine feste Reihenfolge macht die Antwort prüfbar.
- **Bezug:** `sammel3.md` 2.2, 2.3.

## E-298 M32: Statistische Analyse entfällt

- **Frage:** Was wird aus M27 `GET /api/statistik` und M28 `/statistik`?
- **Entscheidung:** Entfernt (D-221). `tests/app/m27/test_m27_statistik.py` entfällt ganz; die M28-Tests `test_statistik_seite` und `test_statistik_ohne_bestandskonto` entfallen; `test_neue_routen_liefern_die_huelle` prüft `/statistik` nicht mehr; `/statistik` fehlt in der Liste von `test_keine_leerwoerter_und_texte_unveraendert`. Neu geprüft: `GET /api/statistik` → 404 `nicht_gefunden`, `/statistik` → 404, kein `navlink-statistik`, kein `befehl-gehe-statistik`.
- **Begründung:** Definition D-221; Auftrag (Beispiel „statistische Analyse entfällt“).
- **Bezug:** `sammel3.md` 3; E-251, E-252.

## E-299 M32: Mail-Liste – Suche, Zuordnen von Hand, Gruppen

- **Frage:** Was lässt D-226 bis D-228 offen?
- **Entscheidung:** **Festlegungen:** (1) `suche`: Wörter an Leerraum, je Wort eines der drei Felder, Vergleich mit `norm`; leer filtert nicht; `stand` bleibt ohne `suche`. (2) `POST /api/mail/nachrichten/{id}/buchung` antwortet 201 `Dokument` wie `aus-mail`; Prüfreihenfolge 404 Nachricht → 422 Körper → 404 Buchung; Aktion `dokument_aus_mail` (D-226). Ein zweiter Aufruf mit derselben Buchung legt kein zweites Dokument an. (3) Die von Hand zugeordnete Mail steht mit `nummer = ""` in `angehaengt`, auch ohne `mail_bestellnummer` (D-226: „gilt im Mail-Blatt als zugeordnet“); Lösen des Dokuments hebt das auf. (4) `gruppieren`: Werte `ja`/`nein`; `gruppe` fehlt ohne den Parameter; bei Mails ohne weitere Mail in der Gruppe lassen die Tests `null` oder die eigene ID zu; geprüft werden Gruppen über eine gemeinsame Buchung (Bestellnummer und von Hand) und die Reihenfolge „Gruppe an der Stelle der ersten Mail“. (5) `betrag` je Eintrag von `angehaengt` = Summe der Bestandskonto-Splits (D-236/9).
- **Begründung:** Definition 4; die kleinsten Festlegungen, die Tests brauchen.
- **Bezug:** `sammel3.md` 8.1–8.4; `erwartungen.md` 14.5; `mail.md` 6.6.

## E-300 M32: Bilder fremder Server in der Mail-Ansicht

- **Frage:** Wie werden D-229 geprüft?
- **Entscheidung:** Mail-Dokumente über Upload (`.eml` aus `m18.mail` mit HTML-Teil). Geprüft: ohne Parameter unverändert (fremde Adressen entfernt, Richtlinie wie M18); mit `bilder=ja` bleiben `https://`-, `http://`- und `//`-Adressen in `<img src>` stehen, `srcset`, Skripte und `@import` nicht; Richtlinie = M18 mit `img-src data: https: http:`; `…/mail/bilder` zählt die fremden Bildadressen (zwei verschiedene `<img>`), `data:`-Bilder nicht; Mail ohne fremde Bilder → 0; PDF → 409 `keine_mail`. Festlegung: anderer Wert von `bilder` → 422 `validierung`. `background`/`url()` werden nicht geprüft (Zählweise bei Stilen offen).
- **Begründung:** Definition D-229.
- **Bezug:** `sammel3.md` 8.5; `dokumente.md` 2.11.

## E-301 M32: Anbieter-Beschreibungen

- **Frage:** Was ist an D-230 prüfbar?
- **Entscheidung:** Mit dem Mock-Mail-Plugin und `mail_abgleich`: eine eigene Beschreibung `kaufhaus.toml` nach `ANBIETER.md` (Absender unter `example.invalid`) in `anbieter_verzeichnis` erzeugt beim Abgleich eine Erwartung mit `anbieter = "kaufhaus"`, Grund `bestellung`, Händler = `titel`, Betrag aus `gesamt`; eine Buchung mit der Kennung im Verwendungszweck wird zugeordnet. Eine zusätzliche fehlerhafte Datei (TOML ungültig) und eine mit einem Ausdruck über 500 Zeichen werden übergangen, ohne die gültige zu stören. Konfiguration: Vorgabe `None`, Pfad aus `KONTOR_ANBIETER_VERZEICHNIS`, ungültige Typen → `KonfigurationsFehler` mit `details["feld"]`. Ein nicht vorhandenes Verzeichnis wirkt wie keines (Festlegung). Nicht geprüft: Ersetzen mitgelieferter Beschreibungen, Neulesen der Kennungen bei geänderten Mustern, die 200 000-Zeichen-Grenze.
- **Begründung:** Definition D-230; `ANBIETER.md` ist das Format.
- **Bezug:** `sammel3.md` 9.1; `python-api.md` 23.

## E-302 M32: PayPal-Zuordnung (ändert erwartungen.md 5.2)

- **Frage:** Wie wird D-232 übernommen, und was wird aus dem M20-Test?
- **Entscheidung:** Für PayPal gilt `sammel3.md` 9.2: genau eine Buchung gleichen Betrags im Fenster ± 5 Tage, die den Händler in Teilen nennt; Buchungen ohne Händler stören nicht. `kennung_passt` bleibt die erste Stufe (Festlegung). `tests/app/m20/test_m20_zuordnung.py::test_automatisch_ueber_betrag_nur_eindeutig` ist danach umgeschrieben (Buchung ohne Händler → keine Zuordnung; mit Händler → Zuordnung trotz der anderen; zwei mit Händler → keine). `test_automatisch_nicht_wenn_kandidat_fuer_andere_erwartung` bleibt (die Buchung ist auch Kandidat einer zweiten offenen Erwartung; die Definition hebt diese Regel nicht auf). Neu geprüft: Fenster (6 Tage → nicht), kurze Wörter nur als ganzes Wort, Allerweltswort allein genügt nicht, gekürzter Name der Bank, Mail ohne Händler.
- **Begründung:** Definition D-232 („Folge für die Abnahme“).
- **Bezug:** `erwartungen.md` 5.2, 15; `sammel3.md` 9.2.

## E-303 M32: Geplante Zahlungen – Lesarten

- **Frage:** Was lässt D-238 offen?
- **Entscheidung:** **Festlegungen:** (1) `wiederholung` (auch `keine`) bei anderem Grund → 422 `wiederholung_nur_geplant`; `wiederholung_bis` ohne Wiederholung → 422 `wiederholung_fehlt`; Prüfreihenfolge 404 → `validierung` → `wiederholung_nur_geplant` → `wiederholung_fehlt` → bisherige. (2) `PATCH` mit `keine` entfernt die Wiederholung. (3) Folge: gleiche Angaben, Tag der ersten Fälligkeit, Monatsletzter in kürzeren Monaten, `frist − datum` gleich; geprüft mit einer Kette ab dem 31.01. (31.01. → 29.02.2024 → 31.03.). (4) „unberührt“ = seit dem Anlegen unverändert; geprüft wird nur der Wegfall einer unberührten Folge. (5) Vorschau: Ereignisse mit `quelle = "geplant"` werden irgendwo in der Antwort gesucht (Lage frei); Pflichtfelder `erwartung_id`, `konto_id = null`, `rhythmus`, `datum`. Geprüft: erstes Datum, Folgedaten eines Rhythmus, fällige am Folgetag, geschlossene fehlen. (6) Zuordnung nach Namen nur im Abgleich mit `mail_abgleich`. (7) Sicherung: `schemaversion` ≥ 10, Rundreise mit Wiederholungen; ohne Wiederholung kein Feld in Protokoll und Inhalt.
- **Begründung:** Definition D-238.
- **Bezug:** `sammel3.md` 14; `erwartungen.md` 6.

## E-304 M32: Konfiguration ansehen

- **Frage:** Wie wird `GET /api/konfiguration` geprüft, ohne die Form der Werte zu raten?
- **Entscheidung:** Die App wird nach dem Setzen von Umgebungsvariablen (`monkeypatch.setenv`) erzeugt. Geprüft: Variablen `KONTOR_…` erscheinen in `umgebung` mit `bekannt` (bekannt für eine Variable aus `python-api.md`, nicht bekannt für eine erfundene), fremde Variablen nicht; `CREDENTIALS_DIRECTORY` erscheint, wenn gesetzt; geheim klingende Variablen und `KONTOR_FINTS_BENUTZER`/`KONTOR_FINTS_KUNDEN_ID` tragen `verborgen = true`, ihr Wert steht nirgends in der Antwort; `KONTOR_BANK_PIN_QUELLE` und `…_TOKEN_URL` sind nicht verborgen. `wirksam` enthält je Einstellung einen Eintrag mit `variable = KONTOR_<NAME>` (für die geprüften Felder `mail_abgleich`, `regeln_automatisch`, `anbieter_verzeichnis`), `geaendert` für eine von der Vorgabe abweichende Einstellung wahr, für eine unveränderte falsch. Die Form von `wert`/`vorgabe` ist frei (JSON-Wert oder Text). Geschützt: mit Anmeldung ohne Sitzung 401. Kein Protokoll.
- **Begründung:** Definition D-235.
- **Bezug:** `sammel3.md` 11.

## E-305 M32: Betrieb hinter HTTPS

- **Frage:** Was ist an D-239 ohne root, systemd und Tailscale prüfbar?
- **Entscheidung:** (1) `kontor-https.sh` liegt in `kontor.betrieb`, nennt die Unterbefehle `einrichten`, `status`, `zurueck` und die Optionen `--tailscale-installieren`, `--name`, `--test-port`; weder `kontor-https.sh` noch `kontor-test.sh` enthalten `funnel` außerhalb von Kommentaren. Die Skripte werden **nicht ausgeführt**. (2) Die ausgelieferte `kontor.env` bleibt bei `KONTOR_HOST=0.0.0.0`. (3) Warnung: `create_app` mit `sitzung_cookie_secure = True` ohne `oeffentliche_url` protokolliert mehr `WARNING` (Logger `kontor…`) als mit `oeffentliche_url` (Wortlaut frei; Festlegung „beim Erzeugen der App“ wie `python-api.md` 6). (4) Herkunft hinter einem TLS-Proxy: Anfrage über `http` an 127.0.0.1 mit `Origin: https://<name>` wird mit `oeffentliche_url = https://<name>` angenommen und ohne abgelehnt (403 `csrf_ungueltig`) – Verhalten seit M7, hier als Szenario.
- **Begründung:** Definition, „Nicht automatisch prüfbar“; Auftrag (Skripte nur beschreiben, Fremdsysteme nie ansprechen).
- **Bezug:** `sammel3.md` 15; `betrieb.md` 10; `sicherheit.md` 4.6.

## E-306 M32: Oberfläche – Lesarten

- **Frage:** Was lässt die Definition an der Oberfläche offen?
- **Entscheidung:** (1) Stelle von `navlink-konfiguration` in der Gruppe `betrieb` und von `befehl-gehe-tags`/`-konfiguration` in der Palette offen; Kennungen nach dem bisherigen Schema (`befehl-gehe-<ziel>`, `seite-<name>`). Die Hilfen `m8.NAV_LINKS`, `m8.PALETTE_GEHE` enthalten die fest geordneten Einträge, `m8.NAV_LOSE`/`m8.GEHE_LOSE` die frei stehenden. (2) `em-im-konto` ohne Buchungen mit `aria-disabled="true"` (wie `km-dublette`, E-143); mit einem Konto direkt, mit mehreren Untermenü. (3) `empfaenger-treffer` trägt `data-anzahl` (Festlegung). (4) `km-spalte-<feld>` mit `aria-checked`; `data-spalten-aus` enthält die Felder. (5) Auswahl-Summen: Einnahmen und Summe mit Vorzeichen; Ausgaben als Betrag der negativen Summe mit beliebigem Vorzeichen. (6) Erfolgsmeldung: eingeschaltet über die Einstellung `einstellung-erfolgsmeldung` (Bereich `allgemein`, `check()`), nicht über einen geratenen Wert im Browser-Speicher (Hilfe `m32.erfolgsmeldung_einschalten`). (7) `mail-suche` schreibt `suche=` in die Adresse. (8) `tab-andere-schliessen` schließt alle außer dem aktiven. (9) Nicht geprüft: Texte, Tooltips, Darstellung (D-236/2, 3, 12, 13), Dialog zum Zuordnen von Mails im Einzelnen, „Weitere anzeigen“ und Suchfeld im Änderungsfenster, Bereichsauswahl mit Umschalt+Pfeil.
- **Begründung:** Auftrag („Rate keine Einzelheiten der Oberfläche“).
- **Bezug:** `oberflaeche.md` 41.

## E-307 M32: Nachziehen früherer Meilensteine

- **Frage:** Welche früheren Tests und Hilfen ändern sich wegen Definition 4?
- **Entscheidung:** (1) **Kontonamen** (E-295): M1 `test_konten.py::test_namen_nicht_eindeutig` → `test_namen_je_ebene_eindeutig` (zweites gleichnamiges Konto 409, andere Klasse oder anderes Elternkonto erlaubt); `test_idempotenz.py::test_kategorien_ueber_art_name_eltern` ohne zweites „Lebensmittel“; die Strategien `kmy_buch` (M1) und `gnc_buch` (M4) erzeugen Namen je Ebene eindeutig; M4 `test_vorhandenes_konto_hoechstens_einmal` nach 1.3 (Zusammenführen, Warnung, `kategorien_neu` beim zweiten Import erneut 1); M19 `test_umbuchungen_anfangssalden_und_unbekannte` ohne zweites Bestandskonto „Doppelt“, `test_zuordnung_vorhandener_kategorien` mit dem Zusammenführen der zweiten „Sport“; M3 `test_zufaelliges_rueckgaengig_gegen_orakel` erwartet 409 `konto_existiert`, wenn Zustand und Bezüge passen, aber gleichnamige Geschwister entstünden. (2) **Standardkategorie** (E-296): `m3.stammdaten_anlegen` legt statt der Standardkategorien je Empfänger die Regel „Empfänger ist <Name>“ am Ende an (die Umwandlung aus D-219); die Wahrheit des Generators bleibt, die Hilfe `m3.vorschlag_soll` bildet `quelle = "standardkategorie"` auf diese Regel ab. Angepasst: M3 `test_felder_und_vorgaben`, `test_aendern_und_loeschen`, `test_abruf_mit_stammdaten`, `test_standardkategorie_vorschlag_entscheiden` (→ `test_standardkategorie_abgelehnt`), `test_m3_protokoll.py` (Empfänger ohne Standardkategorie), `test_m3_rueckgaengig.py` (Operation `empfaenger_um` nur mit Aliasen), `test_m3_erfassen.py::test_empfaenger_name`, `test_m3_konto_loeschen.py::test_standardkategorie` (Empfänger bleiben unverändert, `empfaenger_geaendert = []`) und der Aufbau in Zeile „Laden“; M4 `test_stufenfolge_regel_standardkategorie_lernmodell` (→ Regel → Lernmodell), `test_abweichung_ohne_lernmodell_und_standardkategorie` (ohne Standardkategorie); M9 `test_vorschlaege_aller_quellen_aliase_und_lernmodell` (Quellen `regel`, `lernmodell`); M15 `test_vorschlag_marken` (ohne Fall „Empf.“); M19 `_aufbau` (Empfänger ohne Standardkategorie). (3) **Statistik** nach E-298; `m8.NAV_LINKS`, `m8.PALETTE_GEHE`, M28 `test_navigation_in_gruppen` (Gruppen nach 41.1). (4) **Bestätigen** (D-223): M28 `test_bestaetigen_durch_person`, `test_bestaetigen_vorlaeufig_bleibt_und_zuruecknehmen`, `test_empfaenger_markieren_und_bestaetigen` erwarten das Tag „B-Torsten“. (5) **Erfolgsmeldung** (D-234): M8 `test_rueckgaengig_ueber_meldung` schaltet sie vorher ein. (6) **Handy-Kontoblatt** (D-236/4): M8 `test_filter[handy-*]` erwartet `filter-ausdruck` erst nach `ansicht-umschalten`; `m8.filter_ausdruck_setzen`, `filter_ausdruck_wert`, `filter_zuruecksetzen` klappen am Handy über `m8.ansicht_aufklappen` auf. Die übrigen Handy-Tests von M26, M28 und M30 bedienen weder Filterfeld noch Zeitraum oder Gruppierung und bleiben. (7) **PayPal** nach E-302. (8) **M31** `test_route_lernmodell_ohne_navigationseintrag` über das neue `m8.NAV_LINKS`, `test_mail_liste_angehaengt_stand_und_filter` erwartet `betrag` (Hinweis aus W-Meldung vom 2026-11-22). Alle übrigen Tests der Liste `abnahme-stand-main.txt` bleiben unverändert.
- **Begründung:** Definition 4 („Folge für die Abnahme“, ersetzte Regeln); Auftrag „Frühere Tests nachziehen“.
- **Bezug:** E-271, E-291.

## E-308 Selbstprüfung für M32

- **Frage:** Welche neuen oder geänderten Kern-Tests bekommen Referenzteile und Mutanten?
- **Entscheidung:** **M32** wird wie M18–M20, M23, M24, M27, M29–M31 ausgelassen (`OHNE_REFERENZ` um `m32`). Die geänderten Kern-Tests früherer Meilensteine laufen weiter gegen die Referenz; dafür wird die Referenz nachgezogen, wo sie das neue Verhalten braucht: Kontonamen je Ebene eindeutig (409 `konto_existiert`), Standardkategorie ≠ null → 422 `kategorie_ungueltig`, Navigation und Palette nach 41.1 (Tags, Konfiguration, ohne Statistik). Neue Mutanten `m32_kontonamen_doppelt` und `m32_standardkategorie_bleibt`.
- **Begründung:** CLAUDE.md (Referenz klein halten); E-266, E-275, E-292.
- **Bezug:** E-149.

## E-309 Widersprüche W-017 bis W-019: Erklärung und Lerndaten des Lernmodells

- **Frage:** Drei M31-Tests (`test_m31_lernmodell.py`) widersprechen nach der Meldung vom 2026-11-22 der Spezifikation.
- **Entscheidung:** **W-017:** Der Test ist zu streng. `lernmodell.md` 8.1 verlangt je bekanntem Merkmal `anzahl = N(f)`, auch bei `grund = unbekannt` (z. B. das Betragsmerkmal). `m31.erklaerung_soll` liefert bei `unbekannt` die bekannten Merkmale mit `anzahl` und prüft die übrigen Zählungen nicht (sie hängen an der besten Kategorie, die es dann nicht gibt). **W-018:** Die Testdaten von `test_erklaerung_mehrere_merkmale_exakt` hatten zwei gleich gute Buchungen; der Zweck „Kuchen Kartenzahlung“ heißt jetzt „Kuchen Bar“, damit die beste Buchung eindeutig ist (die Reihenfolge bei Gleichstand legt 8.1 nicht fest). **W-019:** „3000 Buchungen nach den Mustern“ schließt eine Eröffnungsbuchung nicht aus; `test_lerndaten_laden_und_rueckgaengig` lässt höchstens eine zusätzliche Buchung gegen ein Eigenkapitalkonto (nicht „Unkategorisiert“/„Korrekturen“) zu und prüft Zahl und Datumsbereich an den übrigen.
- **Begründung:** Meldungen W-017 bis W-019 (Text des Implementierungs-Threads, `spec/definitionen/widersprueche-m31.md`); Spezifikation unverändert.
- **Bezug:** `lernmodell.md` 8.1, 10; E-280, E-281.

## E-310 Widerspruch W-020: „Erweitert“ im Bankzugang

- **Frage:** Drei M29-Browsertests bedienen Kunden-ID, Produkt-ID und Diagnoseprotokoll, die seit M31 (D-207) in „Erweitert“ (`<details>`, eingeklappt) stehen.
- **Entscheidung:** Die Tests sind veraltet. `m29.bankzugang_oeffnen` klappt jetzt nach dem Öffnen des Abschnitts alle `<details>` darin auf (`m29.erweitert_aufklappen`); den Anfangszustand („offen nur, wenn etwas fehlt oder läuft“) prüft weiter `test_m31_oberflaeche.py::test_erweitert_offen_ohne_produkt_id` ohne diese Hilfe.
- **Begründung:** W-020; `oberflaeche.md` 40.3.
- **Bezug:** E-286, E-291.

## E-311 Widerspruch W-021: Balken als Tupel

- **Frage:** `_pruefe_tiefe` (M31) verglich Listen aus `evaluate_all` mit Tupeln und war deshalb nie erfüllbar.
- **Entscheidung:** Fehler der Hilfe. `m28.balken` liefert jetzt Tupel `(ebene, schlüssel)`; die übrigen Nutzer (M28) zerlegen die Einträge nur und sind nicht betroffen.
- **Begründung:** W-021.
- **Bezug:** E-287.

## E-312 M32: Nachträge zum Nachziehen und zur Selbstprüfung

- **Frage:** Was hat sich beim Nachziehen und in der Selbstprüfung über E-307/E-308 hinaus ergeben?
- **Entscheidung:** (1) `m5.Kreditbuch` legt Girokonto, Darlehen, Zinsen und Lebensmittel nur an, wenn es auf der obersten Ebene noch kein gleichnamiges Konto derselben Art gibt, sonst nutzt es das vorhandene (der M15-Aufbau importierte vorher eine zweite „Lebensmittel“; ab M32 wäre das 409 `konto_existiert`). (2) Die Referenz der Selbstprüfung prüft Kontonamen beim Anlegen, Ändern, Löschen mit hochrutschenden Unterkonten und Rückgängig, bereinigt nach KMyMoney- und GnuCash-Importen (ohne Kreditbezug, klein gehalten) und vergibt bei der Synchronisation einen freien Namen; sie lehnt Standardkategorien nur am Empfänger ab (Erfassen mit `kategorie_id` bleibt). (3) Die Mutanten `standardkategorie_vor_regel` und `loeschen_standardkategorie_bleibt` entfallen, weil kein Test mehr eine Standardkategorie setzen kann; an ihre Stelle tritt `m32_standardkategorie_bleibt`. (4) Bei Mutanten ohne Meilensteinnummer in der Beschreibung (`m32_kontonamen_doppelt`) laufen zuerst die Tests unter `tests/app/*.py`.
- **Begründung:** Selbstprüfung (CLAUDE.md): Referenz grün, jeder Mutant rot.
- **Bezug:** E-307, E-308.

## E-313 Widersprüche W-022 bis W-026 aus dem M32-Lauf

- **Frage:** Fünf M32-Tests widersprechen nach der Meldung vom 2026-11-22 (`spec/definitionen/widersprueche-m32.md`) der Spezifikation.
- **Entscheidung:** **W-022:** Testfehler – das Mock-Mail-Plugin liefert nur Mails bis zum Tag der App-Uhr (`mail.md` 6.2); `_gruppen_app` setzt `heute = 2024-06-20`. **W-023:** Testfehler – `_mail_dokument` legte „Giro“ zweimal an (D-218); es nutzt vorhandene Konten. **W-024:** Lücke im Vertrag – `GET /api/dokumente/{dokument_id}/mail/html` nennt jetzt 422 (`Validierung`) für einen ungültigen Wert von `bilder` (E-300). **W-025:** Beide Stellen gelten: `em-im-konto` öffnet mit `empfaenger_id=`, die Kontoansicht übernimmt den Parameter danach nach `oberflaeche.md` 39.2 in `filter=`. Der Test prüft deshalb `empfaenger_id=<id>` **oder** einen `filter`-Ausdruck mit dem Namen und dass nur die Buchungen des Empfängers auf dem Konto sichtbar sind; 41.2 bleibt, die M8-Tests bleiben. **W-026:** Testfehler – die Mails liegen vor dem Erstabruf (`mail_erstabruf_tage` 30 vor `m8.HEUTE`); `_mail_server` startet mit `mail_erstabruf_tage = 365`.
- **Begründung:** Meldungen W-022 bis W-026 (Text des Implementierungs-Threads); `mail.md` 6.2, `sammel3.md` 1, 8.5, `oberflaeche.md` 39.2, 41.2.
- **Bezug:** E-295, E-299, E-300, E-306.

## E-314 Widersprüche W-027 bis W-030 aus dem Gesamtlauf

- **Frage:** Vier frühere Tests widersprechen nach dem Gesamtlauf vom 2026-11-22 (`spec/definitionen/widersprueche-gesamtlauf.md`) der Spezifikation.
- **Entscheidung:** **W-027:** Testfehler seit M32 – `_konto_und_buchung` (M18) legte „Girokonto“ und „Einkauf“ bei jedem Aufruf neu an; es nutzt vorhandene Konten. **W-028:** Testfehler seit M30 – `test_m2_regeln_api.py::test_aendern` vergleicht nach einem `PATCH` der Bedingungen ohne `ausdruck` (der kanonische Text folgt den neuen Bedingungen, `kategorisierung.md` 8). **W-029:** Fehler des Löschorakels – eine Regel mit `konto_id`-Bedingung behält ihren Bezug, aber der Ausdruck nennt den vollen Pfad, der sich beim Löschen eines Elternkontos ändert; das Orakel lässt `ausdruck` dann offen (wie bei umgestellten Regeln, E-271). **W-030:** Versäumnis in E-307 – `test_m19_zusammenfuehren.py::test_mit_loeschen_gegen_orakel` erwartet `empfaenger_geaendert = []` (`sammel3.md` 2.1).
- **Begründung:** Meldungen W-027 bis W-030 (Text des Implementierungs-Threads); Spezifikation unverändert.
- **Bezug:** E-271, E-307, E-312.
