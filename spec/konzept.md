# Konzept: Persönliche Finanz-Web-App

## 1. Ziel

Eine schlanke, selbst gehostete Web-Anwendung zur Verwaltung privater Finanzen, angelehnt an KMyMoney und GnuCash, aber mit deutlich reduziertem Funktionsumfang. Sie läuft dauerhaft im Hintergrund, synchronisiert Konten automatisch, kategorisiert Buchungen selbstständig und benachrichtigt bei Auffälligkeiten. Der Zugriff erfolgt über den Webbrowser.

Alleinstellungsmerkmal (spätere Ausbaustufe): Abgleich von Sammelbuchungen (Amazon, PayPal) mit Informationen aus E-Mails.

## 2. Betriebsumgebung

- Homeserver mit Proxmox, Anwendung in einem unprivilegierten LXC-Container (Debian oder Ubuntu)
- Betrieb als systemd-Dienst
- Backups über Proxmox-Snapshots, zusätzlich Datenbank-Export
- Erreichbarkeit nur im Heimnetz, gemeinsamer Login für den Haushalt

## 3. Technologie

- **Backend:** Python mit FastAPI
- **Hintergrundjobs:** Scheduler (z. B. APScheduler) für Synchronisation, Kategorisierung und Prüfungen
- **Datenbank:** SQLite (später optional PostgreSQL)
- **Bankanbindung:** FinTS/HBCI über python-fints (Details in Abschnitt 6)
- **Frontend:** schlanke Weboberfläche, Layout angelehnt an KMyMoney
- **Benachrichtigungen:** ntfy (Push aufs Smartphone)
- **Geheimnisse:** Tokens und Zugangsdaten verschlüsselt gespeichert, nie im Klartext

**Austauschbare Datenquellen:** Bankanbindung (AqBanking) und E-Mail-Anbindung sind Plugins hinter einer festen Schnittstelle. Per Konfiguration lassen sie sich durch Mock-Plugins ersetzen, die synthetische, aber realistische Daten aus dem Testdatengenerator liefern. So kann die gesamte Anwendung in der Debug-Phase ohne echte Bank- und Maildaten betrieben werden. Im Mock-Modus zeigt die Oberfläche deutlich sichtbar einen Hinweis, und Mock- und Echtdaten liegen in getrennten Datenbanken.

## 4. Datenmodell

- **Doppelte Buchführung:** Jede Buchung besteht aus mindestens zwei Splits, deren Summe null ergibt. Kategorien sind intern Konten (Aufwand, Ertrag).
- **Kontotypen:** Girokonto, Sparkonto, Kreditkonto, Aufwand, Ertrag, Eigenkapital
- **Buchungsstatus:** importiert, vorläufig (berechnet), bestätigt, abgeglichen
- **Tags:** frei vergebbare Markierungen zusätzlich zur Kategorie, mehrere je Buchung
- **Belege:** im Datenmodell vorgesehen, Umsetzung später
- **Konten und Kategorien löschen:** auch wenn noch Buchungen darauf verweisen. Vor dem Löschen wird gefragt, wie mit den Buchungen umgegangen wird: löschen, dem übergeordneten Konto der Hierarchie zuschlagen oder als unkategorisiert einstufen. Buchungen, deren Quelle und Ziel danach auf demselben Konto lägen (z. B. zweimal „Unkategorisiert“), werden gesondert angezeigt; der Anwender entscheidet, ob sie gelöscht oder behalten werden. Unterkonten rücken eine Ebene nach oben. Details: `spec/api/loeschen.md`.

## 5. Benutzeroberfläche

- **Linke Navigationsleiste:** Finanzübersicht, Konten, Kategorien, Wiederkehrende Buchungen, Kredite, Berichte, Import, Einstellungen
- **Finanzübersicht:** alle Konten mit aktuellem Saldo
- **Kontoansicht:** Buchungsliste des gewählten Kontos
- **Filter:** Zeitraum, Betrag, Empfänger, Verwendungszweck, Kategorie, Tag, Status
- **Mehrfachbearbeitung:** mehrere Buchungen markieren und gemeinsam Kategorie oder Tags setzen

**Bedienung wie eine native Anwendung:** modernes, schnelles Single-Page-Frontend ohne Seitenneuladen.

- **Verschiebbare und größenveränderbare Seitenpanels**, ein- und ausklappbar; das Layout wird gespeichert.
- **Kontextmenüs per rechter Maustaste**, z. B. auf Buchungen (Kategorie setzen, splitten, taggen, als Dublette markieren) und auf Konten.
- **Drag and Drop**, z. B. Buchungen auf eine Kategorie ziehen, Kategorien im Baum umsortieren, später Belege auf Buchungen ziehen.
- **Mehrfachauswahl** mit Strg und Umschalt wie im Dateimanager.
- **Tastaturkürzel** für häufige Aktionen und eine Befehlspalette.
- **Inline-Bearbeitung** direkt in der Buchungsliste, Undo per Strg+Z.
- **Helles und dunkles Design**, passend zur Systemeinstellung.
- Installierbar als **PWA**, damit die App ohne Browserleiste in einem eigenen Fenster läuft.
- Auf dem Smartphone ersetzen lange Berührung und Wischgesten Rechtsklick und Drag and Drop.

## 6. Bankanbindung

- Nur Lesezugriff, keine Überweisungen
- Regelmäßiger automatischer Abruf über FinTS (python-fints)
- Dublettenerkennung beim Abruf

**Banking-PIN:** verschlüsselt mit systemd-creds gespeichert, möglichst an das TPM gebunden, und nur dem Dienst beim Start übergeben. Alternativ wählbar: PIN gar nicht speichern und bei Bedarf in der Weboberfläche eingeben (nur im Arbeitsspeicher). Die PIN erscheint nie in Logs, Datenbank, Fehlermeldungen oder Kommandozeilenargumenten.

**FinTS-Bibliothek:** python-fints statt aqbanking-cli, da sie TAN-Anforderungen samt QR-Bild direkt an die Anwendung liefert. Das Bank-Plugin bleibt austauschbar. Das zwischenzeitlich vorgesehene Plugin über eine vorhandene AqBanking-Konfiguration (Meilenstein 10) ist entfallen; der Abruf läuft über FinTS mit camt, der Bankzugang wird in der Oberfläche eingestellt (Meilenstein 29, E-258, E-259).

**QR-TAN-Ablauf (Bank bietet nur QR-TAN):**

1. Verlangt die Bank beim Abruf eine TAN (für reine Kontoabrufe etwa alle 180 Tage), pausiert die Synchronisation und speichert die TAN-Anforderung.
2. Per ntfy kommt eine Push-Nachricht aufs Handy mit Link zur TAN-Seite der Weboberfläche.
3. Die TAN-Seite zeigt den QR-Code an. Er wird an einem zweiten Bildschirm (z. B. Laptop) mit der Banking-App gescannt; die TAN wird in der Weboberfläche eingegeben.
4. Die Synchronisation läuft weiter. Bleibt die TAN-Anforderung unbeantwortet, erinnert die App in Abständen und bricht nach Ablauf der Gültigkeit sauber ab.

**Nur am Handy:** Die Banking-App kann QR-Codes aus Bildern lesen. Die TAN-Seite bietet deshalb einen Knopf „QR-Code speichern“ bzw. „Teilen“, damit das Bild direkt an die Banking-App übergeben werden kann. Die TAN-Freigabe ist so komplett am Handy möglich, ein zweiter Bildschirm ist optional.

## 7. Automatische Kategorisierung

Zweistufiges Verfahren beim Eingang neuer Buchungen:

1. **Regeln:** feste Zuordnungen, z. B. Empfänger enthält „REWE“ → Lebensmittel
2. **Lernmodell:** Wo keine Regel greift, schlägt ein Klassifikator auf Basis von Empfänger, Verwendungszweck und Betrag eine Kategorie vor. Trainingsdaten sind die importierten Altdaten aus KMyMoney und GnuCash. Jede Korrektur verbessert das Modell.

Vorschläge werden als solche markiert, bis sie bestätigt sind.

## 8. Splitbuchungen und Split-Vorlagen

- Splitbuchungen sind Kernfunktion.
- **Split-Vorlagen** für Sammelabbuchungen (z. B. DBK-Versicherung): Erkennung über Empfänger und Muster, Aufteilung in feste Teilbeträge auf mehrere Kategorien.
- **Keine Toleranz:** Weicht der Gesamtbetrag auch nur um einen Cent von der Vorlage ab, wird die Buchung nicht automatisch gesplittet und eine Benachrichtigung ausgelöst. Die Vorlage wird dann manuell angepasst (z. B. nach Beitragsänderung).

## 9. Wiederkehrende Buchungen

- Automatische Erkennung regelmäßiger Buchungen (Abos, Daueraufträge, Lastschriften)
- Übersicht mit Empfänger, Rhythmus, Betrag und Jahreskosten
- Benachrichtigung bei unerwarteten Buchungen, z. B. neuer Empfänger, geänderter Betrag oder ausbleibende Zahlung

## 10. Kredite

- Abbildung laufender Annuitätendarlehen ohne direkten Kontozugriff
- **Parameter:** Restschuld, Sollzins, Rate, Zinsberechnungsmethode (wählbar: 30/360 als Standard, act/360, act/365), Sondertilgungen
- **Automatische Aufteilung:** Ratenzahlung vom Girokonto wird in Zinsanteil (Kategorie Zinsen) und Tilgungsanteil (Minderung der Restschuld) gesplittet. Diese Buchungen sind „vorläufig“.
- **Jahresabgleich:** Eingabe von Restschuld und gezahlten Zinsen laut Jahresauszug. Die Anwendung vergleicht mit der eigenen Berechnung und erzeugt eine Korrekturbuchung zur Bestätigung. Danach werden die Buchungen des Jahres als „abgeglichen“ markiert.

## 11. Berichte

- **Start:** Kontostandsverlauf pro Konto als Liniendiagramm
- Schrittweiser Ausbau nach Bedarf

## 12. Import

- **KMyMoney:** direkter Import der .kmy-Datei (gzip-komprimiertes XML) inklusive Konten, Kategorien, Empfänger und Splits
- **GnuCash:** Import aus XML- oder SQLite-Datei
- **Dublettenerkennung:** Eindeutige Treffer (gleiches Datum, Betrag, Konto, passender Empfänger) werden automatisch zusammengeführt, Zweifelsfälle werden zur Bestätigung vorgelegt.

## 13. E-Mail-Anbindung (vorbereitet)

- Zwei Gmail-Postfächer über IMAP
- Authentifizierung ausschließlich per OAuth2 (XOAUTH2), nur Lesezugriff, keine Passwörter
- Hinweis: Eigenes Google-Cloud-Projekt nötig. Im Testmodus laufen Refresh-Tokens nach sieben Tagen ab, dafür ist eine Lösung zu finden.
- Zweck: Auslesen von Bestell- und Zahlungsmails für den späteren Abgleich

## 14. Ergänzende Grundfunktionen

Aus der Lückenanalyse übernommen:

- **Mobile Ansicht:** responsives Layout, Navigationsleiste als einblendbares Menü, kompakte Buchungsliste
- **Umbuchungserkennung:** gleicher Betrag mit umgekehrtem Vorzeichen, kurzes Zeitfenster, passende eigene IBAN; Zusammenführung zu einer Buchung, zählt nicht als Einnahme oder Ausgabe
- **Kontenabstimmung:** Saldo gegen Kontoauszug prüfen, Buchungen als abgestimmt markieren
- **Empfängerverwaltung:** Empfänger zusammenführen, Aliase pflegen, Standardkategorie je Empfänger
- **Manuelle Buchungen:** Korrekturen und Umbuchungen von Hand erfassen
- **Volltextsuche:** über alle Konten, Empfänger, Verwendungszwecke und Tags
- **Export:** CSV und PDF, z. B. für Steuer und Archiv
- **Änderungsprotokoll:** jede automatische und manuelle Änderung nachvollziehbar, mit Rückgängig-Funktion
- **Datensicherung und Wiederherstellung:** vollständiger Export als ZIP-Datei mit einer SQLite-Datenbank, ohne Änderungsprotokoll und ohne Geheimnisse; der Import überschreibt den gesamten fachlichen Zustand und wird als neue Version (Änderung im Protokoll, rückgängig machbar) angelegt, bei identischem Inhalt entsteht keine neue Version; Mock- und Echtdaten werden nicht vermischt; Einspielen nur nach Bestätigung und nicht während einer Synchronisation (Auftrag vom 2026-11-08, Details in `spec/api/sicherung.md`)

## 15. Zurückgestellt

- Direkte Anbindung an Amazon und PayPal sowie Wertpapierdepot
- Belege an Buchungen (konzeptionell vorgesehen)

## 16. Bewusst nicht enthalten

- Überweisungen und andere schreibende Bankaufträge
- Budgets und Budgetlimits
- Kontostandsprognose
- Mehrere Benutzerkonten, Fremdwährungen und Bargeldkonto

## 17. Lückenanalyse im Vergleich zu KMyMoney und GnuCash

Alle Punkte sind entschieden: übernommen in Abschnitt 14, zurückgestellt in 15, verworfen in 16. Ursprüngliche Analyse:

| Funktion | Bedeutung | Empfehlung |
| --- | --- | --- |
| Kontenabstimmung (Reconciliation) | Saldo gegen Kontoauszug prüfen und Buchungen als abgestimmt markieren | Aufnehmen, ähnlich dem Kreditabgleich |
| Empfängerverwaltung | Empfänger zusammenführen, Aliase pflegen, Standardkategorie | Aufnehmen, verbessert Kategorisierung stark |
| Manuelle Buchungen | Bargeld, Korrekturen, Umbuchungen | Aufnehmen, Grundfunktion |
| Umbuchungen zwischen eigenen Konten | Transfers erkennen, damit sie nicht als Ausgabe zählen | Aufnehmen, wichtig für Statistiken |
| Depot und Wertpapiere | Kurse, Bestände, Dividenden | Klären, ob benötigt |
| Fremdwährungen | Konten oder Buchungen in anderer Währung | Klären, ob benötigt |
| Volltextsuche | Suche über alle Konten | Aufnehmen |
| Export | CSV- oder PDF-Export für Steuer und Archiv | Aufnehmen |
| Steuerauswertung | Summen steuerlich relevanter Kategorien je Jahr | Später, über Tags lösbar |
| Änderungsprotokoll und Rückgängig | Nachvollziehbarkeit automatischer Änderungen | Aufnehmen, da viel automatisiert wird |
| Datensicherung in der App | Export der gesamten Datenbank | Ergänzend zu Proxmox-Snapshots |
| Mobile Ansicht | Bedienung am Smartphone | Klären |
| Bargeldkonto | Erfassung von Barausgaben | Klären |

## 18. Nächste Schritte

1. Schnittstellenspezifikation festlegen (Testagent)
2. Datenmodell im Detail ausarbeiten
3. Erster Meilenstein: KMyMoney-Import, Kontenübersicht, Buchungsliste
4. Zweiter Meilenstein: Bank-Synchronisation (mit Mock-Plugin) und Regel-Kategorisierung
