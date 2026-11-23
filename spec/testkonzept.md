# Testkonzept: Persönliche Finanz-Web-App

Die Korrektheit der Anwendung wird durch Tests belegt, die unabhängig von der Implementierung allein aus dem Konzeptdokument und dessen Schnittstellenspezifikation entstehen.

## 1. Grundsätze und Agententrennung

- **Zwei getrennte Agenten:** Ein Testagent schreibt die Tests, ein Implementierungsagent schreibt den Code.
- **Kein Zugriff auf die Implementierung:** Der Testagent sieht ausschließlich das Konzept, die Schnittstellenspezifikation (API, Datenmodell, Funktionssignaturen) und dieses Testkonzept. Er hat keinen Lesezugriff auf den Quellcode der Implementierung.
- **Umsetzung der Trennung:** getrennte Repositories oder Verzeichnisse mit getrennten Zugriffsrechten; der Testagent arbeitet nur im Test-Repository. Die Tests laufen in der CI gegen die Implementierung.
- **Tests zuerst:** Für jeden Meilenstein liegen die Tests vor, bevor implementiert wird. Der Implementierungsagent darf Tests ausführen und Fehlermeldungen lesen, aber Tests nicht ändern.
- **Änderungen an Tests** nur durch den Testagenten und nur bei Änderung der Spezifikation, nachvollziehbar dokumentiert.
- **Schnittstellenvertrag:** Vor Beginn wird die Spezifikation verbindlich festgelegt (z. B. OpenAPI für die Web-API, Python-Protokolle für interne Module). Sie ist die einzige gemeinsame Grundlage beider Agenten.

## 2. Testebenen und Werkzeuge

| Ebene | Zweck | Werkzeug |
| --- | --- | --- |
| Unit-Tests | Einzelne Funktionen, z. B. Zinsberechnung, Parser | pytest |
| Eigenschaftsbasierte Tests | Invarianten über zufällige Eingaben | Hypothesis |
| Integrationstests | Zusammenspiel mit Datenbank, AqBanking-Attrappe, IMAP-Attrappe | pytest, Testcontainer |
| API-Tests | Web-Schnittstelle gegen die Spezifikation | pytest mit HTTP-Client, Schemathesis |
| End-to-End-Tests | Bedienung im Browser, Desktop und mobil | Playwright |
| Mutationstests | Prüfen, ob die Tests Fehler wirklich finden | mutmut |

Zielwerte: Zeilenabdeckung mindestens 90 %, Zweigabdeckung mindestens 85 %, Mutationswert mindestens 80 % für die Kernmodule Buchhaltung, Kredite, Splits und Import.

## 3. Globale Invarianten

Diese Eigenschaften müssen nach jeder Operation gelten und werden eigenschaftsbasiert mit zufälligen Buchungsfolgen geprüft:

1. Die Summe aller Splits jeder Buchung ist exakt 0.
2. Beträge werden ausschließlich als ganze Cent oder Decimal gespeichert, nie als Gleitkommazahl.
3. Der Saldo eines Kontos ist gleich der Summe seiner Splits.
4. Die Summe aller Kontensalden im gesamten Buch ist 0.
5. Jede automatische Änderung erzeugt einen Eintrag im Änderungsprotokoll.
6. Rückgängig machen einer Änderung stellt den vorherigen Zustand exakt wieder her.
7. Ein Import derselben Daten zweimal hintereinander verändert beim zweiten Mal nichts (Idempotenz).

## 4. Datenmodell und doppelte Buchführung

- Buchung mit unausgeglichenen Splits wird abgelehnt.
- Buchung mit nur einem Split wird abgelehnt.
- Kategorien verhalten sich als Aufwands- und Ertragskonten.
- Statusübergänge: importiert → bestätigt → abgeglichen; vorläufig → abgeglichen; unzulässige Übergänge werden abgelehnt.
- Tags: mehrere je Buchung, Umbenennen eines Tags wirkt auf alle Buchungen, Löschen entfernt nur die Zuordnung.
- Datenmodell enthält Belegfelder, die ohne Belegfunktion leer bleiben dürfen.
- Konten und Kategorien löschen (`spec/api/loeschen.md`):
  - Jede der drei Varianten (löschen, dem Elternkonto zuschlagen, unkategorisiert) wird geprüft, jeweils mit Invarianten und Salden gegen ein unabhängiges Modell.
  - Elternkonto-Variante bei einem Wurzelkonto wird abgelehnt.
  - Unterkonten rücken nach oben.
  - Konfliktbuchungen (Quelle und Ziel auf demselben Konto) werden erkannt; sowohl Löschen als auch Behalten wird geprüft.
  - Splits auf dem Zielkonto werden zusammengefasst.
  - Gesperrte Buchungen nur nach Bestätigung.
  - Vorschläge, Regeln, Standardkategorien und Abstimmungen werden behandelt wie spezifiziert.
  - Probelauf und Fehlerfälle ändern nichts; Rückgängig stellt alles exakt wieder her.

## 5. Import aus KMyMoney und GnuCash

- Testdateien: kleine, handgebaute .kmy-Dateien und GnuCash-Dateien (XML und SQLite) mit bekanntem Inhalt.
- Konten, Kategorien, Empfänger, Splits, Datum, Beträge und Verwendungszwecke werden vollständig und exakt übernommen.
- Kontensalden nach Import entsprechen den Salden in der Quelldatei.
- Sonderfälle: Umlaute und Sonderzeichen, sehr lange Verwendungszwecke, Buchungen ohne Empfänger, verschachtelte Kategorien, Splits mit mehr als zehn Teilen, geschlossene Konten.
- Fehlerfälle: beschädigte Datei, falsches Format, leere Datei führen zu verständlicher Fehlermeldung ohne Teilimport.

## 6. Dublettenerkennung

- Eindeutige Dublette (gleiches Datum, Betrag, Konto, passender Empfänger) wird automatisch zusammengeführt.
- Zwei echte gleiche Buchungen am selben Tag (z. B. zweimal derselbe Kaffee) werden nicht fälschlich zusammengeführt, sondern zur Bestätigung vorgelegt.
- Abweichungen um einen Tag oder leicht abweichender Empfängertext landen in der Bestätigungsliste.
- Überschneidende Zeiträume aus KMyMoney und GnuCash ergeben keine doppelten Salden.
- Wiederholter Bankabruf desselben Zeitraums erzeugt keine Dubletten.

## 7. Bankanbindung über AqBanking

- Tests laufen gegen das Mock-Bank-Plugin bzw. eine FinTS-Attrappe mit festgelegten Antworten, nie gegen eine echte Bank.
- Ausgabe wird korrekt geparst, inklusive Vormerkbuchungen und Storno.
- Fehler wie Zeitüberschreitung, TAN-Anforderung oder Server nicht erreichbar führen zu Benachrichtigung und Wiederholung, ohne Datenverlust.
- Nachweis, dass keine schreibenden Bankaufträge ausgelöst werden können.

## 8. Automatische Kategorisierung

- Regeln greifen vor dem Lernmodell.
- Bei mehreren passenden Regeln gilt eine festgelegte, getestete Priorität.
- Lernmodell: Auf einem festen Testdatensatz erreicht es eine vorab festgelegte Mindestgenauigkeit.
- Vorschläge sind als Vorschlag markiert, bis sie bestätigt sind.
- Eine Korrektur fließt nachweisbar in künftige Vorschläge ein.
- Ohne Trainingsdaten wird keine Kategorie geraten, sondern die Buchung bleibt unkategorisiert.

## 9. Splitbuchungen und Split-Vorlagen

- Exakter Betrag: Vorlage wird angewendet, Teilbeträge stimmen centgenau.
- Abweichung um einen Cent nach oben oder unten: keine automatische Aufteilung, Benachrichtigung wird ausgelöst.
- Nach Anpassung der Vorlage wird die nächste Buchung wieder korrekt gesplittet.
- Manuelles Splitten und Zusammenführen von Splits ist jederzeit möglich, Invariante 1 bleibt erhalten.

## 10. Wiederkehrende Buchungen

- Erkennung monatlicher, vierteljährlicher und jährlicher Rhythmen aus synthetischen Buchungsreihen.
- Kleine Datumsverschiebungen (Wochenende, Feiertag) verhindern die Erkennung nicht.
- Jahreskosten werden korrekt berechnet.
- Benachrichtigung bei neuem Empfänger, geändertem Betrag und ausbleibender Zahlung, jeweils mit Positiv- und Negativfall.

## 11. Umbuchungserkennung

- Gegenläufige Beträge zwischen eigenen Konten im Zeitfenster werden zu einer Buchung zusammengeführt.
- Gleicher Betrag an fremde IBAN wird nicht als Umbuchung erkannt.
- Umbuchungen erscheinen in Statistiken weder als Einnahme noch als Ausgabe.
- Liegt nur eine Seite vor, wird nach Eintreffen der zweiten Seite nachträglich zusammengeführt.

## 12. Kredite

- Referenzwerte: Tilgungspläne für Annuitätendarlehen werden unabhängig berechnet (z. B. Tabellenkalkulation oder Referenzformel) und als feste Erwartungswerte hinterlegt.
- Zinsmethoden 30/360, act/360 und act/365 liefern jeweils centgenau die Referenzwerte, inklusive Schaltjahr und Monatsende.
- Rate wird korrekt in Zins- und Tilgungsanteil gesplittet, Restschuld sinkt um den Tilgungsanteil.
- Sondertilgung verringert Restschuld und künftige Zinsanteile korrekt.
- Jahresabgleich: Bei Abweichung entsteht genau eine Korrekturbuchung über die Differenz; danach stimmen Restschuld und Zinssumme mit dem Auszug überein, und die Buchungen sind abgeglichen.
- Rundung: festgelegte Rundungsregel, über viele Raten kein Auflaufen von Rundungsfehlern über die Referenz hinaus.

## 13. Kontenabstimmung

- Stimmt der berechnete Saldo mit dem eingegebenen Auszugssaldo überein, werden die Buchungen als abgestimmt markiert.
- Bei Differenz wird die Differenz angezeigt und nichts markiert.
- Abgestimmte Buchungen sind gegen versehentliche Änderung geschützt.

## 14. Empfängerverwaltung, manuelle Buchungen, Suche, Export

- Zusammenführen zweier Empfänger ordnet alle Buchungen um, Aliase greifen bei neuen Importen.
- Standardkategorie eines Empfängers wird bei neuen Buchungen angewendet.
- Manuelle Buchungen unterliegen denselben Invarianten wie importierte.
- Volltextsuche findet Treffer in Empfänger, Verwendungszweck und Tags, unabhängig von Groß- und Kleinschreibung und Umlauten.
- Filter lassen sich kombinieren; Ergebnis entspricht einer unabhängig berechneten Erwartung.
- Mehrfachbearbeitung ändert genau die markierten Buchungen.
- CSV-Export ist verlustfrei wieder einlesbar (Rundreise-Test), PDF-Export enthält alle gefilterten Buchungen.

## 15. Berichte

- Kontostandsverlauf entspricht an jedem Stichtag der Summe aller Splits bis zu diesem Tag.
- Konten ohne Buchungen und Zeiträume ohne Buchungen werden korrekt dargestellt.

## 16. E-Mail-Anbindung

- OAuth2-Ablauf gegen eine Attrappe: Token holen, erneuern, Ablauf und Widerruf führen zu Benachrichtigung statt Absturz.
- Es werden keine Passwörter gespeichert; Tokens liegen nur verschlüsselt vor.
- Zugriff ist nachweislich nur lesend.
- Zwei Postfächer werden getrennt und parallel verarbeitet.

## 17. Benachrichtigungen

- Jeder Auslöser (unerwartete Buchung, Split-Abweichung, Synchronisationsfehler, Token-Ablauf) erzeugt genau eine Nachricht an eine ntfy-Attrappe.
- Gleiche Ereignisse lösen keine Nachrichtenflut aus.

## 18. Sicherheit

- Ohne Login ist keine Seite und kein API-Endpunkt erreichbar.
- Schutz gegen SQL-Injection, XSS und CSRF wird mit gezielten Angriffseingaben geprüft.
- Sitzungen laufen ab; falsches Passwort wird nach mehreren Versuchen gebremst.
- Keine Geheimnisse in Logs oder Fehlermeldungen.

## 19. Oberfläche, Desktop und mobil

- Playwright-Tests für Finanzübersicht, Kontoansicht, Filtern, Mehrfachbearbeitung, Split bearbeiten, Kreditabgleich.
- Gleiche Abläufe in mobiler Bildschirmgröße, inklusive einblendbarem Menü.

Zusätzlich prüfen Playwright-Tests die native Bedienung: Panels verschieben und Größe ändern mit Speicherung des Layouts, Kontextmenüs per Rechtsklick, Drag and Drop von Buchungen auf Kategorien, Mehrfachauswahl mit Strg und Umschalt, Tastaturkürzel, Undo per Strg+Z sowie lange Berührung und Wischgesten auf dem Smartphone.

## 20. Betrieb

- Neustart des Dienstes während einer Synchronisation führt zu keinem inkonsistenten Zustand.
- Datenbank-Export und Wiederherstellung ergeben einen identischen Datenbestand (geprüft in Abschnitt 23).
- Leistung: Buchungsliste mit 50.000 Buchungen lädt in unter einer Sekunde, Import einer großen KMyMoney-Datei in vertretbarer Zeit (Grenzwert vorab festlegen).

## 21. Testdaten

Alle automatisierten Tests laufen ausschließlich mit synthetischen Daten; echte Bank-, Mail- oder Kreditdaten werden in Tests nie verwendet.

- **Generator mit festem Startwert:** Ein Testdatengenerator erzeugt reproduzierbar mehrere Jahre Buchungshistorie für fiktive Konten (Girokonto, Sparkonto, zwei Annuitätendarlehen).
- **Realistische Muster:** fiktive Empfänger (z. B. Supermarkt, Tankstelle, Stromversorger), Gehaltseingang, Miete, Abos, Daueraufträge, Umbuchungen zwischen eigenen Konten, zufällige Einzelkäufe.
- **Sammelabbuchung:** fiktive Versicherung mit mehreren Verträgen in einer Abbuchung, inklusive Beitragsänderung im Lauf der Zeit.
- **Störfälle gezielt eingebaut:** Dubletten, fast-Dubletten, Wochenendverschiebungen, ausbleibende Zahlungen, Betragsänderungen, Storno, Sonderzeichen und Umlaute.
- **Bekannte Wahrheit:** Zu jeder Buchung speichert der Generator die richtige Kategorie, Splits und Umbuchungspaare als Erwartungswerte.
- **Fiktive IBANs:** nur prüfziffergültige Test-IBANs, keine echten Kontonummern.
- **Dateiformate:** Der Generator erzeugt daraus .kmy-Dateien, GnuCash-Dateien (XML, SQLite), AqBanking-Ausgaben und E-Mails als Testfixtures.
- **Lernmodell:** Training auf den älteren 80 % der synthetischen Historie, Prüfung auf den neuesten 20 %; Mindestgenauigkeit 85 %. Bei geringer Sicherheit wird kein Vorschlag gemacht.

Echte Daten nutzt nur der Anwender selbst im Betrieb, etwa zur Kontrolle des Lernmodells auf seinem eigenen Server.

**Mock-Plugins für die Debug-Phase:** Ein AqBanking-Mock und ein Mail-Mock implementieren dieselbe Schnittstelle wie die echten Plugins und liefern Daten aus dem Generator, zeitlich fortlaufend wie im echten Betrieb (neue Buchungen und Mails bei jedem Abruf). Szenarien sind wählbar, z. B. Normalbetrieb, Beitragsänderung, Bankfehler, Token-Ablauf. Tests prüfen, dass echte und Mock-Plugins sich an der Schnittstelle gleich verhalten (Vertragstests) und dass im Mock-Modus keinerlei Verbindung zu Bank oder Mailserver aufgebaut wird.

## 22. Offene Punkte

- Agententrennung mit Claude Code in der Cloud: zwei private Repositories. kontor-tests enthält Konzept, Testkonzept, Schnittstellenspezifikation, Testdatengenerator und Tests; kontor-app enthält die Implementierung. Die Sitzung des Testagenten bekommt nur kontor-tests zugeordnet; der GitHub-Proxy der Cloud-Sitzung verweigert jeden Zugriff auf nicht zugeordnete Repositories, die Trennung ist also technisch erzwungen. Die Sitzung des Implementierungsagenten bekommt beide Repositories, darf kontor-tests aber laut Auftrag nicht ändern; Verstöße sind in der Git-Historie sichtbar.

Entschieden: Rundung bei Krediten kaufmännisch auf den Cent für den Zinsanteil je Rate, Tilgung = Rate minus Zins. Mindestgenauigkeit Lernmodell 85 % auf synthetischen Daten.

## 23. Datensicherung und Wiederherstellung

- Rundreise: Sicherung erstellen und in eine leere Instanz einspielen ergibt denselben fachlichen Zustand (alle Lese-Endpunkte des Buchbestands, Zustand je Bankkonto); Protokoll und Versionsdaten sind vom Vergleich ausgenommen.
- Die Inhaltsprüfsumme im Manifest stimmt mit einer unabhängig aus der REST-Schnittstelle berechneten überein.
- Die Sicherung enthält weder Änderungsprotokoll noch Geheimnisse noch Reste gelöschter Daten (Prüfung mit Markierungstexten in den Dateibytes).
- Einspielen ersetzt den gesamten Zustand, erzeugt genau eine Änderung und lässt sich exakt rückgängig machen und wiederholen; bei identischem Inhalt entsteht keine Änderung (Idempotenz).
- Nach dem Einspielen einer älteren Sicherung holt die Synchronisation fehlende Umsätze genau einmal wieder, ohne Dubletten.
- Beschädigte, fremde oder manipulierte Dateien und Sicherungen aus dem anderen Modus (Mock/Echt) werden mit festem Fehlergrund abgelehnt, ohne Teiländerung.
- Ohne Bestätigung und während einer laufenden oder auf TAN wartenden Synchronisation wird nichts eingespielt; der Probelauf ändert nichts.
