# Meilensteinplan Kontor

Verbindlicher Plan des Test-Threads für alle Meilensteine bis zum
vollständigen Umfang von `spec/konzept.md` (Abschnitte 3–14).
Abkürzungen: K = `spec/konzept.md`, T = `spec/testkonzept.md`,
E = `spec/api/entscheidungen.md`.

## Grundsätze

- **Tests zuerst (T 1):** Für jeden Meilenstein schreibt ein Test-Thread
  Schnittstellenspezifikation, Generator-Erweiterung und Tests, bevor ein
  Implementierungs-Thread beginnt. Jeder Meilenstein ist so geschnitten,
  dass je ein Agent ihn in einem Durchgang spezifizieren/testen bzw.
  implementieren kann.
- **Rückwärtskompatibel (E-029):** Spätere Meilensteine erweitern den
  Vertrag. Tests früherer Meilensteine bleiben unverändert gültig; Änderungen
  nur bei echter Lücke oder echtem Fehler mit eigenem E-Eintrag.
- **Marker:** Tests eines Meilensteins tragen den Marker `m<N>` (z. B.
  `python -m pytest -m m2`), siehe E-041.
- **Abnahme (E-175):** Ein Meilenstein ist erfüllt, wenn der Volllauf
  `python -m pytest --voll` grün ist; `python -m pytest` allein ist ein
  Schnelllauf ohne Leistungs-, Browser- und `langsam`-Tests.
- **Fremdsysteme (E-028):** FinTS-Bank, Gmail/IMAP, OAuth2-Anbieter und
  ntfy-Server werden in Tests nie angesprochen. Echte Plugins werden
  implementiert, aber nur gegen lokale Attrappen auf Protokollebene
  getestet; alle Daten sind synthetisch.
- **Datensicherung (E-085):** Ab M9 ist jeder neue fachliche Zustand Teil
  der Sicherung (`spec/api/sicherung.md` 2.3); ein Meilenstein, der neuen
  Zustand einführt, ergänzt dafür Objektart, Inhaltsprüfsumme und einen
  Rundreise-Test. Geheimnisse sind nie Teil der Sicherung.
- **Benachrichtigungen:** M2 führt eine interne Benachrichtigungsliste ein
  (`/api/benachrichtigungen`); spätere Meilensteine fügen Auslöser hinzu,
  M6 stellt sie per ntfy zu.
- **Außerhalb des Plans:** Zurückgestelltes (K 15: Amazon/PayPal-Anbindung,
  Wertpapierdepot, Belege an Buchungen) und bewusst nicht Enthaltenes
  (K 16: Überweisungen, Budgets, Kontostandsprognose, mehrere Benutzer,
  Fremdwährungen, Bargeldkonto) gehören zu keinem Meilenstein. Belegfelder
  bleiben leer (T 4); der Mail-Abgleich mit Sammelbuchungen (K 1, spätere
  Ausbaustufe) ist nicht Teil dieses Plans.

## Übersicht

| Meilenstein | Thema | Hängt ab von |
| --- | --- | --- |
| M1 (erledigt) | KMyMoney-Import, Kontenübersicht, Buchungsliste, Filter, Mehrfachbearbeitung, Datenmodell, Plugin-Schnittstellen mit Mocks | – |
| M2 (erledigt) | Bank-Synchronisation mit Mock-Plugin, TAN-Ablauf, PIN im Arbeitsspeicher, Planer, Regel-Kategorisierung mit Vorschlägen | M1 |
| M3 (erledigt) | Änderungsprotokoll mit Rückgängig, Empfängerverwaltung, manuelle Buchungen und Umbuchungserkennung, Kontenabstimmung, Volltextsuche | M2 |
| M4 (spezifiziert, getestet) | GnuCash-Import, Lernmodell, Split-Vorlagen | M3 |
| M5 (spezifiziert, getestet, umgesetzt) | Wiederkehrende Buchungen, Kredite, Berichte, Export CSV/PDF | M4 |
| M6 (spezifiziert, getestet) | Echte Anbindungen: FinTS-Plugin, Mail-Plugin (IMAP/OAuth2), ntfy-Benachrichtigungen, verschlüsselter Geheimnisspeicher | M2, M5 |
| M7 (spezifiziert, getestet) | Sicherheit (Login) und Betrieb (systemd, Neustartfestigkeit, Leistung) | M6 |
| M8 (spezifiziert, getestet) | Vollständige Oberfläche (SPA, native Bedienung, mobil, PWA) mit Playwright-Tests | M7 |
| M9 (spezifiziert, getestet) | Datensicherung und Wiederherstellung: Export als ZIP mit SQLite, Einspielen als neue Version im Protokoll | M4 |
| M10 (**entfallen** mit M29, E-259) | AqBanking-Plugin – Plugin, Konfiguration und Tests entfernt | – |
| M11 (spezifiziert, getestet) | Kontostand bei der Synchronisation, Buchungsliste einer Kategorie, Kategorien in der Finanzübersicht, Empfänger zusammenführen mit Namen | M2, M3, M8 |
| M12 (spezifiziert, getestet) | Freie Statusänderung, Bearbeiten aller Bestandteile in der Liste, Massenänderungen, Filterleiste anfangs eingeklappt | M3, M8 |
| M13 (spezifiziert, getestet) | Versionsnummer `MAJOR.MINOR`, Release über die CI von kontor-app, `GET /api/version`, Versionsanzeige und About-Fenster | M7, M8, M9 |
| M15 (spezifiziert, getestet) | Sammelpaket Bedienung: Rückgängig bis, Löschen/Verschieben, Zuordnung unbekannter Bankkonten, Oberfläche | M3, M4, M5, M8, M12 |
| M16 (spezifiziert, getestet) | Wiederkehrende Buchungen: robustere Kette mit zusätzlichen Zahlungen, Begründung je Buchung, Oberfläche | M5, M8, M12, M15 |
| M17 (spezifiziert, getestet) | Tabs der Ansichten, Gehe zur Gegenbuchung (nur Oberfläche) | M8, M11, M12 |
| M18 (spezifiziert, getestet) | Dokumente an Buchungen: PDF, E-Mails, Bilder; Betrachter, Kamera, Protokoll, Sicherung | M3, M6, M7, M8, M9, M15, M17 |
| M19 (spezifiziert, getestet) | ALF-BanCo-Import (QIF) und Kategorien zusammenführen | M1, M3, M4, M5, M7, M8 |
| M20 (spezifiziert, getestet) | Mail-Abgleich: erwartete Zahlungen aus Amazon-/PayPal-Mails, Zuordnung, Seite „Was kommt noch?“ | M3, M6, M7, M8, M9, M17, M18 |
| M21 (spezifiziert, getestet) | Berichte: Einzelbuchungen, Tabelle folgt dem Zoom, Tooltip; Sprungziel mittig (nur Oberfläche) | M5, M8, M15, M16, M17 |
| M22 (spezifiziert, getestet) | Buchungsliste: Spaltenbreiten, Markierung des Bearbeitungsstands, Zusatzmarken (nur Oberfläche) | M3, M5, M8, M11, M16, M17, M20 |
| M23 (spezifiziert, getestet) | Schutz der Geheimnisse mit dem Login-Passwort, gemerkte Bank-PIN, Gmail mit App-Passwort | M2, M6, M7, M8 |
| M24 (spezifiziert, getestet) | Mail-Abgleich: Serien als erwartete Zahlungen, Kachel „Was kommt noch?“, Kategorie bei Erstattungen, eingebaute Mock-Mails | M5, M16, M18, M20 |
| M25 (spezifiziert, getestet) | Betragsfilter für wiederkehrende Buchungen (Vorgabe ±10 %, Einstellung je Empfänger) | M3, M5, M9, M16 |
| M26 (spezifiziert, getestet) | Bedienung auf dem Handy: Kopfzeile, Tab-Liste, Auswahlmodus, Wischhinweis, Blätter, Karten; `Cache-Control` statischer Dateien | M8, M17 |
| M27 (spezifiziert, getestet) | Label „Verdächtig“, Empfänger-Tags (Personen), Filter, Dubletten anlegen und vorschlagen, Mail-Liste mit Stand, Statistik (experimentell) | M3, M7, M9, M12, M20, M25 |
| M28 (spezifiziert, getestet) | Oberfläche aus `feature/sammel`: Person, Navigation in Gruppen, Mail-Blatt, Statistik, Gruppierung, Ausschnitt, Stifte, Kürzel; wiederkehrende Buchungen aus der Bedienung entfernt | M8, M17, M26, M27 |
| M29 (spezifiziert, getestet) | Bankabruf über FinTS/camt (camt-Version der Bank, Kontenliste aus den SEPA-Kontoverbindungen, TAN bei der Anmeldung), Bankzugang über REST und Oberfläche, Diagnoseprotokoll, Übergang alter Bank-Kennungen; ersetzt M10 | M2, M3, M6, M7, M8, M9, M11, M23 |

Reihenfolge der Umsetzung: M1, M2, M3, M4, **M9**, M5, **M10**, M6, M7, M8.
M9 wurde später aufgenommen und deshalb hinten nummeriert (E-085); ebenso
M10, das auf Wunsch des Anwenders vor M6 umgesetzt werden sollte (E-152) und
mit M29 entfallen ist (E-259).

## M1 – Import und Buchungsliste (erledigt)

- **Umfang:** siehe `spec/api/datenmodell.md` 1–10, `python-api.md`,
  `plugins.md`, `openapi.yaml` (Stand M1), E-001 bis E-026.
- **Bezug:** K 3 (Plugins, Mock-Modus), K 4, K 5 (Liste, Filter,
  Mehrfachbearbeitung), K 12 (KMyMoney, Dubletten); T 3.1–3.4, 3.7, T 4–6,
  T 14 (Filter, Mehrfachbearbeitung), T 21.

## M2 – Bank-Synchronisation und Regel-Kategorisierung (erledigt)

Pflicht laut K 18 Schritt 4.

- **Umfang:**
  - Synchronisation über das Bank-Plugin (in Tests nur Mock): manuell per
    API, automatisch per Planer (konfigurierbar, in Tests abschaltbar und
    über `kontor.sync.planer_takt` deterministisch), simulierte Uhr im
    Mock-Modus.
  - Zuordnung der Bankkonten über die IBAN (fehlende werden angelegt),
    Übernahme der Umsätze als Buchungen, Vormerkungen und Storno.
  - Dublettenerkennung beim Abruf: stabile Umsatzkennung, gemerkte
    Kennungen, Abgleich mit Altbestand (KMyMoney, manuell) nach den Regeln
    von M1.
  - Zustand und Fehler: Synchronisationsläufe mit Status je Konto,
    Wiederholung durch den Planer, interne Benachrichtigungen mit
    Entprellung, Neustart während eines Laufs.
  - TAN-Ablauf (K 6 Schritte 1, 3, 4 ohne Erinnerungen): Anforderung
    speichern, anzeigen (Text, Bild), beantworten, abbrechen, Ablauf.
  - PIN: Eingabe nur im Arbeitsspeicher; nie in Logs, Datenbank,
    Fehlermeldungen oder Antworten; falsche PIN wird verworfen.
  - Regeln (K 7 Stufe 1): Datenmodell, CRUD, Bedingungen auf Empfänger,
    Verwendungszweck, Betrag und Konto, Priorität, Anwendung auf neue und
    auf Wunsch auf vorhandene Buchungen, Markierung als Vorschlag bis zur
    Bestätigung.
- **Spezifikation:** `spec/api/synchronisation.md`,
  `spec/api/kategorisierung.md`, Ergänzungen in `datenmodell.md`,
  `python-api.md`, `plugins.md`, `openapi.yaml`; E-027 bis E-043.
- **Bezug:** K 3, K 6, K 7 (Regeln), K 18; T 3.1–3.4, T 6 (wiederholter
  Abruf), T 7, T 8 (Regeln, Vorschläge), T 17 (Entprellung, intern), T 20
  (Neustart während Synchronisation), T 21 (Mock-Szenarien).
- **Nicht in M2:** Lernmodell, ntfy-Zustellung und Erinnerungen, echtes
  FinTS-Plugin, PIN über systemd-creds, TAN-Seite der Oberfläche,
  Umbuchungserkennung, Empfänger-Standardkategorie, Änderungsprotokoll.

## M3 – Nachvollziehbarkeit und Buchhaltungspflege

- **Umfang:**
  - Änderungsprotokoll für jede automatische und manuelle Änderung
    (rückwirkend für alle Operationen aus M1 und M2, inkl. Synchronisation
    und Regelanwendung) und Rückgängig einzelner Änderungen bzw. Gruppen
    (z. B. ein ganzer Synchronisationslauf); exakte Wiederherstellung.
  - Empfängerverwaltung: zusammenführen, Aliase (wirken bei Import und
    Synchronisation), Standardkategorie je Empfänger (Stufe zwischen Regel
    und Lernmodell, als Vorschlag markiert).
  - Manuelle Buchungen: Erfassungshilfe für Korrekturen und Umbuchungen
    zwischen eigenen Konten (gleiche Invarianten wie importierte).
  - Umbuchungserkennung: gegenläufige Beträge zwischen eigenen Konten im
    Zeitfenster mit passender eigener IBAN werden zu einer Buchung
    zusammengeführt, auch nachträglich beim Eintreffen der zweiten Seite.
  - Kontenabstimmung: Auszugssaldo gegen berechneten Saldo, Markieren als
    abgestimmt, Schutz abgestimmter Buchungen (baut auf der Sperre aus M1
    auf).
  - Volltextsuche über Konten, Empfänger, Verwendungszwecke und Tags
    (eigener Endpunkt; Normalisierung wie M1).
  - Konten und Kategorien löschen, auch mit Buchungen: Wahl zwischen
    Löschen, Zuschlagen zum Elternkonto und „Unkategorisiert“;
    Konfliktbuchungen, Unterkonten, Regeln, Standardkategorien,
    Abstimmungen; rückgängig machbar.
  - Gelöschte Bankkonten: keine stille Neuanlage beim Abruf; der Anwender
    entscheidet „wiederherstellen“ (mit allen oder nur neuen Umsätzen) oder
    „ignorieren“.
- **Bezug:** K 14 (Umbuchungserkennung, Kontenabstimmung,
  Empfängerverwaltung, manuelle Buchungen, Volltextsuche,
  Änderungsprotokoll); T 3.5, T 3.6, T 11, T 13, T 14.
- **Abhängigkeiten:** M2 (automatische Änderungen durch Synchronisation
  und Regeln müssen protokolliert werden; Aliase greifen beim Abruf;
  Umbuchungen entstehen vor allem aus zwei Bankseiten).
- **Spezifikation:** `spec/api/protokoll.md`, `spec/api/buchhaltungspflege.md`,
  M3-Abschnitte in `datenmodell.md` (13), `synchronisation.md` (14),
  `kategorisierung.md` (6), `python-api.md` (9), `openapi.yaml` 2.1.0;
  E-044 bis E-059; dazu Konten und Kategorien mit Buchungen löschen
  (`spec/api/loeschen.md`, E-060 bis E-064, Auftrag vom 2026-11-08);
  Nachtrag: gelöschte Bankkonten bei der Synchronisation erfragen und
  wiederherstellen (`synchronisation.md` 16, E-080 bis E-084).
  Präzisierung: Die Statistik-Aussage aus T 11 wird in M3
  über Kontensalden geprüft, Berichte bleiben M5 (E-059); die automatische
  Umbuchungserkennung ist abschaltbar, Vorgabe aus (E-054).
- **Status:** spezifiziert, getestet (`tests/app/m3/`, Marker `m3`) und laut
  Koordination von kontor-app erfüllt (Stand 2026-11-08); der Nachtrag
  gelöschte Bankkonten (E-080 bis E-084) kam danach hinzu.

## M4 – GnuCash-Import, Lernmodell, Split-Vorlagen

- **Umfang:**
  - GnuCash-Import aus XML (gzip/unkomprimiert) und SQLite, analog
    `datenmodell.md` 10 (Abbildung, Fehlerfälle ohne Teilimport,
    Idempotenz, Dublettenerkennung; überschneidende Zeiträume aus KMyMoney
    und GnuCash ergeben keine doppelten Salden). Generator erzeugt
    GnuCash-Fixtures.
  - Lernmodell (K 7 Stufe 2): Klassifikator auf Empfänger, Verwendungszweck,
    Betrag; Training auf Altdaten, Korrekturen fließen ein; Mindestgenauigkeit
    85 % auf dem synthetischen Datensatz (ältere 80 % Training, neueste
    20 % Prüfung); bei geringer Sicherheit kein Vorschlag; ohne
    Trainingsdaten keine Kategorie; Regeln greifen vorher.
  - Split-Vorlagen (K 8): Erkennung über Empfänger und Muster, feste
    Teilbeträge, keine Toleranz, Benachrichtigung bei Abweichung, Anpassung
    der Vorlage; Mock-Szenario `beitragsaenderung`.
- **Bezug:** K 7, K 8, K 12 (GnuCash); T 5, T 6, T 8 (Lernmodell), T 9,
  T 17 (Auslöser Split-Abweichung), T 21 (Lernmodell, Sammelabbuchung).
- **Abhängigkeiten:** M3 (Vorschläge und automatische Splits werden
  protokolliert und sind rückgängig zu machen; Standardkategorie als Stufe
  vor dem Lernmodell).
- **Spezifikation:** `spec/api/gnucash.md`, `spec/api/lernmodell.md`,
  `spec/api/vorlagen.md`, M4-Abschnitte in `datenmodell.md` (14),
  `kategorisierung.md` (7), `synchronisation.md` (15), `plugins.md` (8),
  `python-api.md` (10), `protokoll.md` (9), `buchhaltungspflege.md` (9),
  `loeschen.md` (6); `openapi.yaml` ab 2.2.0; E-065 bis E-079 und E-094.
  Präzisierungen: Lernmodell als Naive Bayes mit exakten Brüchen, Schwelle
  7/10, gemessen als Genauigkeit ≥ 85 % und Abdeckung ≥ 70 % (E-070,
  E-073); Lernmodell bei neuen Buchungen abschaltbar, Vorgabe aus (E-072);
  Vorlagen vor Regeln, bei Abweichung keine Kategorisierung (E-074).
- **Status:** spezifiziert und getestet (`tests/app/m4/`, Marker `m4`);
  Implementierung offen.

## M5 – Wiederkehrende Buchungen, Kredite, Berichte, Export

- **Umfang:**
  - Wiederkehrende Buchungen: Erkennung monatlicher, vierteljährlicher und
    jährlicher Rhythmen trotz Wochenend-/Feiertagsverschiebung, Übersicht mit
    Empfänger, Rhythmus, Betrag, Jahreskosten; Benachrichtigung bei neuem
    Empfänger, geändertem Betrag, ausbleibender Zahlung.
  - Kredite: Annuitätendarlehen ohne Kontozugriff, Zinsmethoden 30/360,
    act/360, act/365, Sondertilgungen, automatische Aufteilung der Rate in
    Zins und Tilgung (Status `vorlaeufig`), Jahresabgleich mit genau einer
    Korrekturbuchung, danach `abgeglichen`; Rundung laut T 22.
  - Berichte: Kontostandsverlauf je Konto (Datenreihe für das
    Liniendiagramm), leere Konten und Zeiträume.
  - Export CSV (verlustfreie Rundreise) und PDF (alle gefilterten
    Buchungen).
- **Bezug:** K 9, K 10, K 11, K 14 (Export); T 10, T 12, T 14 (Export),
  T 15, T 17 (Auslöser unerwartete Buchung), T 22 (Rundung).
- **Abhängigkeiten:** M4 (Splits aus Vorlagen und Kategorien sind
  Grundlage für Rhythmen und Berichte), M3 (Korrekturbuchungen
  protokolliert, abgeglichene Buchungen geschützt).
- **Spezifikation:** `spec/api/kredite.md`, `spec/api/wiederkehrend.md`,
  `spec/api/berichte.md` (Berichte und Export), M5-Abschnitte in
  `datenmodell.md` (15), `synchronisation.md` (17), `protokoll.md` (11),
  `sicherung.md` (2.5), `python-api.md` (12), `loeschen.md` (7);
  `openapi.yaml` 2.5.0; E-097 bis E-111. Präzisierungen: Erkennung
  wiederkehrender Buchungen ohne eigenen Zustand, Toleranz 5 Tage (E-098);
  Benachrichtigungen je Ereignis genau einmal, automatische Prüfung
  abschaltbar, Vorgabe aus (E-100); Zinstage je Methode, 30/360 mit vollen
  Perioden zu 30 Tagen, act/365 fixed, Zins je Rate kaufmännisch gerundet
  (E-102); Jahresabgleich gegen das Gebuchte ohne Neuverankerung (E-105);
  Kredite in der Sicherung nur bei Vorhandensein (E-109).
- **Status:** spezifiziert und getestet (`tests/app/m5/`, Marker `m5`);
  Implementierung offen.

## M6 – Echte Anbindungen und Benachrichtigungen

- **Umfang:**
  - Benachrichtigungen per ntfy über eine austauschbare Schnittstelle
    (Plugin `ntfy` und `mock`): jeder Auslöser genau eine Nachricht, keine
    Flut, TAN-Push mit Link zur TAN-Seite, Erinnerungen in Abständen bis zum
    Ablauf (K 6 Schritte 2 und 4), Token-Ablauf.
  - Echtes FinTS-Plugin mit python-fints (nur Lesezugriff, TAN mit QR-Bild),
    PIN alternativ über systemd-creds (`$CREDENTIALS_DIRECTORY`); Tests nur
    gegen eine lokale FinTS-Attrappe mit synthetischen Antworten.
  - Mail-Plugin für zwei Gmail-Postfächer über IMAP mit OAuth2 (XOAUTH2),
    nur lesend, ohne Passwörter; Tokenerneuerung, Ablauf (sieben Tage im
    Testmodus) und Widerruf führen zu Benachrichtigung; Postfächer getrennt
    und parallel. Tests gegen lokale IMAP- und OAuth2-Attrappen.
  - Verschlüsselter Geheimnisspeicher für Tokens und Zugangsdaten (K 3),
    nie Klartext in Datenbank oder Logs.
  - Vertragstests: echte und Mock-Plugins verhalten sich an der
    Schnittstelle gleich (T 21).
- **Bezug:** K 3, K 6, K 13; T 7, T 16, T 17, T 21.
- **Abhängigkeiten:** M2 (Synchronisation, TAN, interne Benachrichtigungen),
  M5 (alle Auslöser für Benachrichtigungen vorhanden).
- **Spezifikation:** `spec/api/fints.md` (FinTS-Plugin, PIN über
  systemd-creds, FinTS-Attrappe), `spec/api/mail.md` (Postfächer, IMAP,
  OAuth2, Token-Ablauf, Abruf), `spec/api/benachrichtigungen.md` (ntfy,
  Zustellung, TAN-Erinnerungen), `spec/api/geheimnisse.md`
  (Geheimnisspeicher, Endpunkte, Transportsicherheit); M6-Abschnitte in
  `python-api.md` (13), `plugins.md` (9), `synchronisation.md` (18),
  `protokoll.md` (12), `sicherung.md` (2.6); `openapi.yaml` 2.6.0; E-112 bis
  E-123. Präzisierungen: python-fints ist installierbar, keine Alternative
  (E-113); camt.052 bevorzugt, MT940 als Rückfall, Hash-Kennung für Umsätze
  ohne Bankreferenz (E-114); PIN über `$CREDENTIALS_DIRECTORY` ohne Aufruf von
  `systemd-creds` (E-115); Postfächer als protokolliertes Objekt in der
  Sicherung, Mail-Spiegel als Betriebszustand (E-118); ntfy auch im
  Mock-Modus, mit `[Mock]` im Titel (E-119); sieben Tage im Testmodus:
  Erkennung, Vorwarnung, erneute Anmeldung (E-120).
- **Status:** spezifiziert und getestet (`tests/app/m6/`, `tests/attrappen/`,
  Marker `m6`); Implementierung offen.

## M7 – Sicherheit und Betrieb

- **Umfang:**
  - Gemeinsamer Haushalts-Login: ohne Login keine Seite und kein
    API-Endpunkt (außer Login selbst), Sitzungen laufen ab, Bremse nach
    mehreren falschen Passwörtern, Schutz gegen SQL-Injection, XSS und
    CSRF mit gezielten Angriffseingaben, keine Geheimnisse in Logs oder
    Fehlermeldungen. Bestehende Tests erhalten eine angemeldete Sitzung
    über die Testhilfe (keine inhaltliche Änderung).
  - Betrieb: systemd-Unit (Dienstdatei wird geprüft, z. B. kein Geheimnis in
    `ExecStart`, `LoadCredentialEncrypted`), zeitgesteuerte Sicherung
    über `kontor.sicherung.erstelle_sicherung` (M9), Neustart während einer
    Synchronisation, Leistung: Buchungsliste mit 50 000 Buchungen unter einer
    Sekunde, Import einer großen KMyMoney-Datei unter einem vorab
    festgelegten Grenzwert.
- **Bezug:** K 2, K 3 (Geheimnisse); T 18, T 20.
- **Abhängigkeiten:** M6 (alle Endpunkte und Geheimnisse vorhanden).
- **Spezifikation:** `spec/api/sicherheit.md` (Haushaltskonto, scrypt,
  Sitzungen, Bremse, CSRF, Ersteinrichtung, Sicherheitsköpfe,
  Eingabehärtung, Größengrenzen, Netzbeschränkung, keine Geheimnisse in
  Logs), `spec/api/betrieb.md` (`python -m kontor`, Umgebungsdatei,
  systemd-Units mit Härtung und `LoadCredentialEncrypted`, Beenden mit
  WAL-Checkpoint, Gesundheitsprüfung, Logging, zeitgesteuerte Sicherung),
  `spec/api/leistung.md` (Datensatz mit 50 000 Buchungen, 15 Grenzwerte);
  M7-Abschnitte in `python-api.md` (14), `protokoll.md` (13),
  `sicherung.md` (9); `openapi.yaml` 2.7.0; E-125 bis E-137.
  Anpassungen des Plans: Die Anmeldung ist abschaltbar mit Vorgabe aus, im
  Betrieb über die ausgelieferte Umgebungsdatei an; frühere Tests laufen
  ohne Anmeldung, die Testhilfe meldet sie zusätzlich im Anmeldelauf
  `KONTOR_TESTS_ANMELDUNG=1` an (E-125). Der Datenbank-Export ist die
  M9-Sicherung, zeitgesteuert per systemd-Timer (E-132). Leistung über die
  Liste hinaus für Suche, Berichte, Lernmodell, Export, Sicherung (E-133).
- **Status:** spezifiziert und getestet (`tests/app/m7/`, Marker `m7`,
  Leistungstests zusätzlich `leistung`); Implementierung offen.

## M8 – Vollständige Oberfläche

- **Umfang:** Single-Page-Frontend nach K 5 und K 14 (mobile Ansicht):
  Navigationsleiste, Finanzübersicht, Kontoansicht, Filter,
  Mehrfachbearbeitung, Split bearbeiten, Kreditabgleich, TAN-Seite mit
  QR-Code, „QR-Code speichern“/„Teilen“; verschiebbare und
  größenveränderbare Panels mit gespeichertem Layout, Kontextmenüs, Drag and
  Drop (Buchung auf Kategorie, Kategorien umsortieren), Mehrfachauswahl mit
  Strg/Umschalt, Tastaturkürzel, Befehlspalette, Inline-Bearbeitung mit Undo
  per Strg+Z, helles/dunkles Design nach Systemeinstellung, PWA
  (Manifest, Service Worker), mobile Bedienung (einblendbares Menü, lange
  Berührung, Wischgesten), Mock-Hinweis.
- **Tests:** Playwright (Python, Chromium headless; in der Umgebung
  vorhanden und geprüft) gegen einen lokal gestarteten Server mit
  Mock-Modus und temporärer Datenbank, Desktop- und Mobil-Viewport. Die
  Oberfläche wird nur über stabile, in der Spezifikation festgelegte
  Merkmale angesprochen (`data-testid`, ARIA-Rollen). Fehlt Chromium,
  werden die Browsertests mit deutlicher Meldung übersprungen und das in
  `ERGEBNIS.md` vermerkt.
- **Bezug:** K 5, K 6 (TAN-Seite, nur am Handy), K 14 (mobile Ansicht);
  T 19.
- **Abhängigkeiten:** alle vorherigen (die Oberfläche bedient nur
  spezifizierte REST-Endpunkte; Login aus M7, Undo aus M3, Kredite aus M5).
- **Spezifikation:** `spec/api/oberflaeche.md` (Routen, Grundgerüst,
  Darstellung, Finanzübersicht, Kontoansicht mit Filtern in der URL,
  Mehrfachauswahl und -bearbeitung, Inline-Bearbeitung, Kontextmenüs,
  Dialoge inkl. Split und Konto löschen, Drag and Drop, Rückgängig über das
  Protokoll, Tastatur und Befehlspalette, weitere Seiten, TAN-Seite, Panels
  mit gespeichertem Layout, mobile Ansicht mit Gesten, Design, PWA,
  Anmeldung, Barrierefreiheit, Testumgebung); `benachrichtigungen.md` 8
  (Test-Benachrichtigung, W-005), `python-api.md` 15, `openapi.yaml` 2.8.0;
  E-138 bis E-150. Anpassungen des Plans: Layout und Design im Speicher des
  Browsers (E-141); „Als Dublette markieren“ für vorhandene Verdachte
  (E-143); „Kategorien umsortieren“ = Elternkategorie ändern (E-144);
  zusätzlich Seiten im Mindestumfang für alle REST-Funktionen (E-148).
- **Status:** spezifiziert und getestet (`tests/app/m8/`, Marker `m8`,
  Browsertests zusätzlich `browser`); Implementierung offen. M8 ist der
  letzte Meilenstein des Plans; danach offene Teile des Konzepts: E-150.

## M9 – Datensicherung und Wiederherstellung

Auftrag des Anwenders vom 2026-11-08, Präzisierungen bestätigt (E-085 bis
E-093); mit M4 und dem M3-Nachtrag (gelöschte Bankkonten) abgeglichen
(E-096, `sicherung.md` 2.4).

- **Umfang:**
  - Sicherung erstellen (`GET /api/sicherung`,
    `kontor.sicherung.erstelle_sicherung`): ZIP mit `manifest.json` und
    `kontor.sqlite`; vollständiger fachlicher Zustand (Buchbestand mit IDs,
    alle gemerkten Kennungen auch gelöschter Buchungen, Zustand und
    gespeicherte Entscheidung je Bankkonto auch bei gelöschtem Konto,
    ID-Zähler einschließlich Vorlagen); ohne Änderungsprotokoll, ohne
    Geheimnisse, ohne Konfiguration, ohne Reste gelöschter Daten. Vorlagen
    und Vorschläge aller Quellen (mit Sicherheit des Lernmodells) gehören
    zum Buchbestand; das Lernmodell folgt aus dem eingespielten Bestand.
  - Manifest mit Modus, Versionen, Anzahlen, Inhalts- und
    Dateiprüfsumme; die Inhaltsprüfsumme ist aus der REST-Schnittstelle
    nachrechenbar.
  - Sicherung einspielen (`POST /api/sicherung/einspielen`): ersetzt den
    gesamten fachlichen Zustand atomar; Prüfung der Datei mit festen
    Fehlergründen, Modusprüfung (Mock/Echt), Bestätigung, Probelauf,
    Sperre bei laufender oder auf TAN wartender Synchronisation.
  - Neue Version: eine Änderung `sicherung_einspielen` im Protokoll,
    rückgängig machbar (inkl. Kennungen und Bankkonto-Zustand); bei
    identischem Inhalt keine Änderung.
- **Bezug:** K 2 (Datenbank-Export), K 3 (Mock/Echt, Geheimnisse), K 14
  (Änderungsprotokoll), K 17 (Datensicherung in der App); T 3.5–3.7, T 6,
  T 13, T 20 (Export und Wiederherstellung), T 23.
- **Abhängigkeiten:** M3 (Protokoll, Rückgängig), M4 (Vorlagen sind Teil des
  Buchbestands). M5–M8 ergänzen die Sicherung um ihren Zustand.
- **Spezifikation:** `spec/api/sicherung.md`, `protokoll.md` 10,
  `python-api.md` 11, `openapi.yaml` 2.4.0; E-085 bis E-093, E-096.
- **Status:** spezifiziert und getestet (`tests/app/m9/`, Marker `m9`);
  Implementierung offen.

## Abdeckung des Konzepts

| Konzept-Abschnitt | Meilenstein |
| --- | --- |
| 3 Technologie (Scheduler, Plugins, Mock-Modus, Geheimnisse) | M1, M2, M6 |
| 4 Datenmodell (inkl. Status, Tags) | M1, Ergänzungen M2–M5 |
| 5 Benutzeroberfläche | M1 (Mock-Hinweis), M8 (Belege per Drag and Drop: später, E-150) |
| 6 Bankanbindung, PIN, TAN | M2 (Mock, Arbeitsspeicher), M6 (FinTS, systemd-creds, ntfy) |
| 7 Kategorisierung | M2 (Regeln), M4 (Lernmodell) |
| 8 Splitbuchungen und Split-Vorlagen | M1 (Splits), M4 (Vorlagen) |
| 9 Wiederkehrende Buchungen | M5 |
| 10 Kredite | M5 |
| 11 Berichte | M5 |
| 12 Import | M1 (KMyMoney), M4 (GnuCash) |
| 13 E-Mail-Anbindung (vorbereitet) | M1 (Schnittstelle), M6 (IMAP/OAuth2) |
| 14 Ergänzende Grundfunktionen | M3 (Protokoll, Empfänger, manuelle Buchungen, Umbuchungen, Abstimmung, Suche), M5 (Export), M8 (mobile Ansicht), M9 (Datensicherung) |
| 2 Betrieb (systemd, Login) | M7 |
| 2 Betrieb (Datenbank-Export), 17 Datensicherung in der App | M9 |
| 1/13 Mail-Abgleich, 4 Belege, 3 PostgreSQL, 11 weitere Berichte, 15, 16 | kein Meilenstein (offen bzw. bewusst nicht enthalten, E-150) |

## M10 – AqBanking-Plugin (entfallen)

Mit Meilenstein 29 vollständig entfallen (Definition „Bankabruf über
FinTS/camt und Bankzugang in der Oberfläche“, Abschnitt 9; E-259): Plugin,
Konfiguration, Fehlerklasse, Spezifikation (`aqbanking.md`), Tests
(`tests/app/m10/`, Marker `m10`), Hilfen sowie Referenz- und Mutantenteile
der Selbstprüfung sind entfernt. Die Nummer wird nicht neu vergeben.

## M11 – Kontostand, Kategorien als Konten, Empfänger zusammenführen

Auftrag des Anwenders vom 2026-11-09 (E-158).

- **Umfang:**
  - Kontostand bei der Synchronisation: Saldo der Bank mit dem Umsatzabruf (`Umsatzliste.saldo`;
    Mock, FinTS `HKSAL`; der AqBanking-Teil ist mit M29 entfallen, E-260), Vergleich mit dem
    Kontor-Saldo, bei Differenz Ausgleichsbuchung gegen „Korrekturen“,
    Benachrichtigung, abschaltbar (`kontostand.md`).
  - Buchungsliste einer Kategorie mit allen Funktionen der Kontoansicht,
    Spalte und Filter für das Bestandskonto, REST-Filter `unterkonten`
    (`oberflaeche.md` 22.2, `datenmodell.md` 16).
  - Finanzübersicht: Kategorien als einklappbarer, abgesetzter Bereich
    (`oberflaeche.md` 22.1).
  - Empfänger zusammenführen mit neuem Namen und Ablauf in der Oberfläche
    (`buchhaltungspflege.md` 10, `oberflaeche.md` 22.3).
- **Bezug:** K 5, K 6, K 7, K 14; T 6, T 14, T 19, T 21.
- **Tests:** `tests/app/m11/` (Marker `m11`); Browsertests mit Playwright wie
  M8; FinTS gegen die Attrappe (Steuerung `saldo_anbieten`).
- **Spezifikation:** `spec/api/kontostand.md`, `oberflaeche.md` 22,
  `datenmodell.md` 16, `buchhaltungspflege.md` 10, `plugins.md` 11,
  `python-api.md` 17, `openapi.yaml` 2.10.0; E-158 bis E-166.
- **Abhängigkeiten:** M2, M3, M8; für das echte Plugin M6.
- **Status:** spezifiziert und getestet (`tests/app/m11/`, Marker `m11`);
  Implementierung offen.

## M12 – Bearbeiten, Massenänderungen, Filterleiste

Auftrag des Anwenders vom 2026-11-09 (E-167): Status jeder Buchung änderbar,
jeder Bestandteil bearbeitbar, Massenänderungen wo sinnvoll, Filterleiste im
Kontobuch einklappbar und standardmäßig eingeklappt.

- **Umfang:**
  - Neuer Endpunkt `POST /api/buchungen/mehrfach/aendern` (Status, Datum,
    Empfänger, Verwendungszweck für eine oder mehrere Buchungen; atomar,
    eine Änderung `mehrfach_aendern` im Protokoll); freie Statusübergänge,
    Verlassen von `abgeglichen` nur mit `entsperren` (`datenmodell.md` 17,
    E-168 bis E-170). `PATCH` bleibt unverändert.
  - Oberfläche: Inline-Bearbeitung von Empfänger, Status und Betrag,
    `mehrfach-status`, `mehrfach-bearbeiten`, `km-status`, `km-mehrfach`,
    Status-Auswahl und Bearbeiten-Dialog (`oberflaeche.md` 23.2 bis 23.5,
    E-171).
  - Filterleiste der Kontoansicht in beiden Layouts anfangs eingeklappt,
    Zahl der Filter am Umschalter (`oberflaeche.md` 23.1, E-172).
- **Bezug:** K 4, K 5, K 14; T 4, T 13, T 14, T 19.
- **Tests:** `tests/app/m12/` (Marker `m12`); REST und Browser (Playwright
  wie M8).
- **Spezifikation:** `datenmodell.md` 17, `oberflaeche.md` 23,
  `protokoll.md` 4.1, `buchhaltungspflege.md` 5.4, `openapi.yaml` 2.11.0;
  E-167 bis E-173.
- **Abhängigkeiten:** M3 (Protokoll, Sperre abgestimmter Buchungen), M8
  (Oberfläche).
- **Status:** spezifiziert und getestet (`tests/app/m12/`, Marker `m12`);
  Implementierung offen.

## M13 – Versionsnummer, Release und About-Fenster

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-10 (E-176);
bereits als `v0.01` veröffentlicht, Abnahmetests standen noch aus.

- **Umfang:**
  - Versionsnummer `MAJOR.MINOR` (`0.01`, `1.00`, `0.100`), eine Quelle und
    überall gleich: `kontor.__version__`, `/api/status`, `/api/gesundheit`,
    `/api/version`, Oberfläche, `app_version` der Sicherung (`version.md` 1,
    E-177).
  - Release bei jedem Push auf `main` von kontor-app (Minor + 1, Major von
    Hand), Tag `v<Version>`, GitHub-Release mit Wheel und Quellpaket
    (`version.md` 2; nicht durch kontor-tests geprüft, 2.4).
  - `GET /api/version` mit Build-Angaben, Python-Version, Modus, aktiver
    Datenbank und Schemaversionen (`version.md` 3, E-178).
  - Oberfläche: `version-knopf` als letztes Element der Navigation (auch in
    der Hülle), About-Fenster `ueber-dialog`, Fokus, Fehlerfall
    (`oberflaeche.md` 24, E-179, E-180).
- **Bezug:** K 2, K 5, K 14; T 19.
- **Tests:** `tests/app/m13/` (Marker `m13`); REST und Python ohne Browser,
  Oberfläche mit Playwright wie M8. Keine Versionsnummer fest eingetragen.
- **Spezifikation:** `spec/api/version.md`, `oberflaeche.md` 24,
  `python-api.md` 1, `sicherung.md` 3.2, `openapi.yaml` 2.12.0; E-176 bis
  E-180.
- **Abhängigkeiten:** M7 (Schutz), M8 (Oberfläche), M9 (Sicherung).
- **Status:** spezifiziert und getestet (`tests/app/m13/`, Marker `m13`);
  Implementierung bereits veröffentlicht, Abnahme gegen diese Tests offen.

## M15 – Sammelpaket Bedienung

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-10 (E-181).
Die Nummer M14 ist an das Feature `update` vergeben und wird später
übernommen.

- **Umfang:**
  - Rückgängig bis einschließlich einer gewählten Änderung über
    `POST /api/aenderungen/rueckgaengig` `{bis_id}` (`protokoll.md` 6.2a,
    E-182); Knopf `aenderung-bis-<id>` im Änderungsprotokoll
    (`oberflaeche.md` 25.1).
  - Mehrere Buchungen in einer Änderung löschen
    (`POST /api/buchungen/mehrfach/loeschen`, `datenmodell.md` 18.1, E-183).
  - Buchungen auf ein anderes Bestandskonto verschieben, für eine Auswahl
    oder alle Buchungen eines Imports bzw. Laufs
    (`POST /api/buchungen/mehrfach/verschieben`,
    `GET /api/konten/{id}/herkunft`, `datenmodell.md` 18.2–18.3, E-184,
    E-185; Dialog `oberflaeche.md` 25.3).
  - Synchronisationskonto: `sync_konten_anlegen` (Vorgabe an, ausgeliefert
    aus), unbekannte Bankkonten werden übersprungen und zur Zuordnung
    angeboten (`synchronisation.md` 20, `python-api.md` 18, `betrieb.md` 3,
    E-186; Zuordnungsdialog und Kontoeinstellungen `oberflaeche.md` 25.4).
  - Gesperrter PIN-Dialog mit Statusanzeige, Vorschläge je Zeile mit
    Quelle und Sicherheit, Berichtsgrafiken (`oberflaeche.md` 25.5–25.7,
    E-187).
- **Bezug:** K 5, K 6, K 7, K 11, K 14; T 3.5, T 3.6, T 13, T 14, T 19.
- **Tests:** `tests/app/m15/` (Marker `m15`, Hilfen `tests/hilfen/m15.py`);
  REST und Konfiguration (kern, E-188), Oberfläche mit Playwright wie M8.
- **Spezifikation:** `protokoll.md` 4.1, 6.2a, 14; `datenmodell.md` 18;
  `synchronisation.md` 20; `python-api.md` 18; `betrieb.md` 3;
  `oberflaeche.md` 25; `openapi.yaml` 2.13.0; E-181 bis E-189.
- **Abhängigkeiten:** M3 (Protokoll, Rückgängig), M3-Nachtrag (gelöschte
  Bankkonten), M4 (Lernmodell), M5 (Berichte), M8 (Oberfläche), M12.
- **Status:** spezifiziert und getestet (`tests/app/m15/`, Marker `m15`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M16 – Wiederkehrende Buchungen: robustere Erkennung mit Begründung

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-11 (E-192).
Die Nummer M14 ist weiterhin an das Feature `update` vergeben.

- **Umfang:**
  - Neue Kette der Erkennung (`wiederkehrend.md` 2.2, ersetzt die bisherige
    Regel ohne Umschalter): Anker unter den Einträgen der letzten `T` Tage,
    rückwärts verketten, zusätzliche Zahlungen am Termin überspringen,
    fremde Zahlungen und ausgelassene Zahlungen beenden die Kette (E-193).
    Der M5-Test zur doppelten Zahlung ist angepasst (E-194).
  - Begründung je Buchung `GET /api/buchungen/{id}/wiederkehrend` mit
    Gesamturteil, Rollen der Einträge und Kettenprotokoll je Rhythmus
    (`wiederkehrend.md` 8, E-195); ohne Zustand und ohne Protokolleintrag.
  - Oberfläche: Begründungsdialog, versteckter Kontextmenüeintrag mit Alt,
    Befehlspalette, Menü je Serie auf `/wiederkehrend`, Sprungziel
    `?buchung=` im Kontoblatt (`oberflaeche.md` 26, E-196).
- **Bezug:** K 5, K 9; T 10.
- **Tests:** `tests/app/m16/` (Marker `m16`, Hilfen `tests/hilfen/m16.py`,
  Referenz der Kette in `tests/hilfen/wiederkehrend_orakel.py`); REST und
  Oberfläche mit Playwright wie M8 (Kern nach E-197).
- **Spezifikation:** `wiederkehrend.md` 2.2 und 8; `oberflaeche.md` 13.5 und
  26; `openapi.yaml` 2.14.0; E-192 bis E-198.
- **Abhängigkeiten:** M5 (wiederkehrende Buchungen), M8 (Oberfläche), M12,
  M15.
- **Status:** spezifiziert und getestet (`tests/app/m16/`, Marker `m16`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M17 – Tabs und Gegenbuchung

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-11
(Feature `tabs-gegenbuchung`, dort „M16“ genannt; die Nummer M16 war schon an
`wiederkehrend-begruendung` vergeben, E-199). Die Nummer M14 bleibt an das
Feature `update` vergeben.

- **Umfang:**
  - Tabs für jede Ansicht der Oberfläche: Tab-Leiste `tab-leiste` mit
    `tab`, `tab-titel`, `tab-schliessen`, ein Tab je Pfad ohne Abfrageteil,
    neuer Tab rechts neben dem aktiven, Zustand je Tab beim Wechsel,
    Anfordern über Navigation mit eingeklappter Filterleiste, direkter
    Aufruf mit der Abfrage der URL, Aktualität nach Änderungen in anderen
    Tabs, Schließen und Wiederöffnen, Speicherung im Browser (höchstens 40,
    lazy), Tastatur in der Leiste, mobil (`oberflaeche.md` 27.1, E-201).
  - Kontextmenü „Gehe zur Gegenbuchung“ (`km-gegenbuchung`, Untermenü
    `km-gegenbuchung-<konto_id>` bei mehreren Gegenseiten), Auswahl der
    Buchung im Ziel, Nachladen, Filter-Reset mit Hinweis, Fehlerfälle, kein
    Protokolleintrag (`oberflaeche.md` 27.2, 27.3, E-200).
- **Bezug:** K 5, K 14; T 19.
- **Tests:** `tests/app/m17/` (Marker `m17`, Hilfen `tests/hilfen/m17.py`);
  nur Browsertests mit Playwright wie M8, keine `kern`-Tests (E-202).
- **Spezifikation:** `oberflaeche.md` 27 (Hinweis in 8.2); `openapi.yaml`
  unverändert (2.14.0); E-199 bis E-202.
- **Abhängigkeiten:** M8 (Oberfläche), M11 (Kategorie-Ansicht), M12
  (Filterleiste eingeklappt, `km-mehrfach`).
- **Status:** spezifiziert und getestet (`tests/app/m17/`, Marker `m17`);
  Implementierung auf dem Feature-Branch `feature/tabs-gegenbuchung`,
  Abnahme offen.

## M18 – Dokumente an Buchungen

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`dokumente`, E-206). Die Nummer M14 bleibt an das Feature `update` vergeben.

- **Umfang:**
  - Objekt `dokument` (PDF, JPEG, PNG, WebP, E-Mail; Typ nur am Inhalt,
    gesäuberter Dateiname, gleicher Inhalt nur einmal gespeichert), an
    mindestens einer Buchung; `Buchung.belege` (`dokumente.md` 1).
  - REST: Anhängen (Upload, auch Kamera), gespiegelte Mail anhängen,
    Lesen, Umbenennen, Löschen, Verknüpfen, Lösen, Dokumente einer Buchung,
    Inhalt mit eigenen Sicherheitsköpfen, Mail zerlegt, entschärftes
    Mail-HTML, Mail-Anhänge (`dokumente.md` 2).
  - Protokoll: Objekt `dokument`, `dokument_ids` an Buchungen, sechs
    Aktionen, Dokumente entfallen mit ihrer letzten Buchung in derselben
    Änderung (`protokoll.md` 15); Sicherung nur bei Vorhandensein
    (`sicherung.md` 2.7).
  - Oberfläche: Marke je Zeile, Abschnitt in den Einzelheiten,
    Mail-Auswahl, Betrachter mit „Hängt an“ und Verknüpfen, Kontextmenü,
    Dateien auf Zeilen ziehen, mobil Kamera (`oberflaeche.md` 28).
- **Bezug:** K 4, K 5, K 14; T 3.5, T 3.6, T 4, T 19.
- **Tests:** `tests/app/m18/` (Marker `m18`, Hilfen `tests/hilfen/m18.py`);
  REST, Protokoll, Sicherung und Schutz als `kern`, Oberfläche mit
  Playwright wie M8 (E-207 bis E-209).
- **Spezifikation:** `dokumente.md`; `datenmodell.md` 7; `protokoll.md` 15;
  `sicherung.md` 2.7; `sicherheit.md` 8; `oberflaeche.md` 28;
  `openapi.yaml` 2.15.0; E-206 bis E-210.
- **Abhängigkeiten:** M3, M6, M7, M8, M9, M15, M17.
- **Status:** spezifiziert und getestet (`tests/app/m18/`, Marker `m18`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M19 – ALF-BanCo-Import und Kategorien zusammenführen

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`alfbanco-import`, überarbeitete Fassung, E-211).

- **Umfang:**
  - Import des QIF-Exports von ALF-BanCo in ein gewähltes Bestandskonto über
    Python (`kontor.importer.alfbanco.importiere_alfbanco`) und
    `POST /api/import/alfbanco`: Kodierung, Datum, Betrag, Kategorien mit
    Art und Zuordnung, Klassen als Tags, Umbuchungen und „Anfangssalden“,
    Herkunftskennung `alf:<konto_id>:…`, Idempotenz, Dubletten auch gegen
    frühere ALF-BanCo-Buchungen (`alfbanco.md` 1–4).
  - `POST /api/kategorien/zusammenfuehren` mit Probelauf, Sperren,
    Kreditbezug und Übernahme der `extern_id` (`alfbanco.md` 5).
  - Protokoll `import_alfbanco` und `kategorien_zusammenfuehren`
    (`protokoll.md` 16); Oberfläche: Format „ALF-BanCo“, Mehrfachauswahl im
    Kategorienbaum, Kontextmenü und Dialog (`oberflaeche.md` 29).
- **Bezug:** K 12, K 14; T 3.5–3.7, T 5, T 6, T 19.
- **Tests:** `tests/app/m19/` (Marker `m19`, Hilfen `tests/hilfen/m19.py`);
  REST und Python-API als `kern`, Oberfläche mit Playwright wie M8
  (E-212 bis E-214).
- **Spezifikation:** `alfbanco.md`; `datenmodell.md` 8; `python-api.md` 19;
  `protokoll.md` 16; `sicherheit.md` 8; `oberflaeche.md` 29;
  `openapi.yaml` 2.16.0; E-211 bis E-215.
- **Abhängigkeiten:** M1, M3, M4, M5, M7, M8.
- **Status:** spezifiziert und getestet (`tests/app/m19/`, Marker `m19`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M20 – Mail-Abgleich: erwartete Zahlungen

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`mail-abgleich`, E-216). Setzt M18 voraus.

- **Umfang:**
  - Konfiguration `mail_abgleich` (Vorgabe aus, ausgeliefert an) und
    `mail_abgleich_frist_tage` (`python-api.md` 20, `betrieb.md` 3).
  - Erkennung von Bestell-, Zahlungs-, Erstattungs- und Stornomails von
    Amazon und PayPal aus dem Mail-Spiegel; Objekt `erwartung` mit
    Bankanteil, Idempotenz, zwei Postfächer (`erwartungen.md` 2, 3).
  - Abgleich nach Abruf, Lauf, Planer-Takt und per REST; Benachrichtigung
    `erwartung_ueberfaellig` (einmal); Kandidaten, automatische und manuelle
    Zuordnung mit Dokumenten (M18), Lösen, verwaiste Bezüge
    (`erwartungen.md` 4–6).
  - Protokoll (Quelle `mail`, sieben Aktionen, `protokoll.md` 17),
    Sicherung (`sicherung.md` 2.8), Seite „Was kommt noch?“
    (`oberflaeche.md` 30).
- **Bezug:** K 1, K 10, K 14; T 3.5, T 3.6, T 17, T 19, T 21.
- **Tests:** `tests/app/m20/` (Marker `m20`, Hilfen `tests/hilfen/m20.py`);
  REST, Python, Konfiguration, Protokoll und Sicherung als `kern`,
  Oberfläche (Desktop) mit Playwright wie M8 (E-217 bis E-219).
- **Spezifikation:** `erwartungen.md`; `python-api.md` 20; `betrieb.md` 3;
  `protokoll.md` 17; `benachrichtigungen.md` 9; `sicherung.md` 2.8;
  `oberflaeche.md` 30; `openapi.yaml` 2.17.0; E-216 bis E-220.
- **Abhängigkeiten:** M3, M6, M7, M8, M9, M17, M18.
- **Status:** spezifiziert und getestet (`tests/app/m20/`, Marker `m20`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M21 – Berichte: Einzelbuchungen, Zoom, Tooltip; Sprungziel mittig

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Features
`diagramm-dunkel` und Sprungziel, E-221).

- **Umfang:**
  - Einzelbuchungen je Zeile der Berichtstabellen (Kontostand, Einnahmen
    und Ausgaben) mit Betrag und Links in die Kontoansicht
    (`oberflaeche.md` 31.1).
  - Tabelle folgt dem Zoom des Diagramms mit Hinweis (31.2); Tooltips im
    Thema (31.3, nicht automatisiert).
  - Sprünge zu einer Buchung rollen sie in die vertikale Mitte (31.4,
    ersetzt in 26.4).
- **Bezug:** K 5, K 11; T 11, T 19.
- **Tests:** `tests/app/m21/` (Marker `m21`, Hilfen `tests/hilfen/m21.py`);
  nur Browsertests, keine `kern` (E-221, E-222).
- **Spezifikation:** `oberflaeche.md` 26.4, 31; `openapi.yaml` unverändert
  (2.17.0); E-221, E-222.
- **Abhängigkeiten:** M5, M8, M15, M16, M17.
- **Status:** spezifiziert und getestet (`tests/app/m21/`, Marker `m21`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M22 – Buchungsliste: Spaltenbreiten und Markierung

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`spalten-markierung`, E-223).

- **Umfang:**
  - Spaltenbreiten der Desktop-Liste: Trenner je Spalte, Ziehen (40–1200 px),
    Doppelklick passt an, Kopfmenü „anpassen“/„zurücksetzen“, Speicherung im
    Browser je Listenart (`oberflaeche.md` 32.1).
  - Markierung `data-markierung` (abgeglichen, kategorisiert, importiert) mit
    Darstellung (32.2); Zusatzmarken „wiederkehrend“ und „durch Mail
    bestätigt“ mit Titel (32.3, setzt M20 voraus).
- **Bezug:** K 5, K 14; T 19.
- **Tests:** `tests/app/m22/` (Marker `m22`); nur Browsertests, keine `kern`
  (E-223, E-224).
- **Spezifikation:** `oberflaeche.md` 32; `openapi.yaml` unverändert (2.17.0);
  E-223, E-224.
- **Abhängigkeiten:** M3, M5/M16, M8, M11, M17, M20.
- **Status:** spezifiziert und getestet (`tests/app/m22/`, Marker `m22`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M23 – Geheimnisse mit dem Login-Passwort geschützt, gemerkte PIN, Gmail mit App-Passwort

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Features
`geheimnisse` und `gmail-app-passwort`, E-228). Die Nummer M14 bleibt an das
Feature `update` vergeben.

- **Umfang:**
  - Schutz der Geheimnisse (außer `ntfy_token`) mit dem Login-Passwort,
    abschaltbar (Vorgabe aus), Sperrzustand je App-Instanz, Entsperren über
    REST oder Login, Sperren, Passwortänderung und Zurücksetzen
    (`geheimnisschutz.md` 1, 2).
  - Gemerkte Bank-PIN unter dem Schutz, PIN-Quelle, Löschen bei falscher PIN
    (`geheimnisschutz.md` 4, 5).
  - Postfach mit App-Passwort (`LOGIN` statt XOAUTH2, ändert K 13 für diese
    Postfächer), Verbindungstest, Vorrang vor OAuth2 (`geheimnisschutz.md` 6).
  - `LimitCORE=0` (`betrieb.md` 4.1); Oberfläche `oberflaeche.md` 33.
  - Kein Protokoll, nichts in der Sicherung (Betriebszustand).
- **Bezug:** K 6, K 13; T 16, T 18.
- **Tests:** `tests/app/m23/` (Marker `m23`, Hilfen `tests/hilfen/m23.py`,
  IMAP-Attrappe mit App-Passwörtern, E-230); REST, Python und Betrieb als
  `kern`, Oberfläche (Desktop) mit Playwright wie M8 (E-229, E-231).
- **Spezifikation:** `geheimnisschutz.md`; `geheimnisse.md` 4; `mail.md`;
  `sicherheit.md` 4.9; `synchronisation.md` 12; `betrieb.md` 4.1;
  `python-api.md` 14.2; `protokoll.md` 18; `sicherung.md` 2.6;
  `oberflaeche.md` 33; `openapi.yaml` 2.18.0; E-228 bis E-232.
- **Abhängigkeiten:** M2, M6, M7, M8.
- **Status:** spezifiziert und getestet (`tests/app/m23/`, Marker `m23`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M24 – Mail-Abgleich: Serien, Kachel, Kategorie bei Erstattungen, Mock-Mails

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`mail-abgleich`, Fortsetzung, E-233). Ergänzt M20 rückwärtskompatibel.

- **Umfang:**
  - Serien wiederkehrender Buchungen als abgeleitete Einträge von
    `GET /api/erwartungen` (`grund=serie`, `serien=ja`), ohne Speicherung,
    Protokoll, Sicherung oder Benachrichtigung (`erwartungen.md` 13.1).
  - Kategorie bei Erstattungen: Umbuchung von „Unkategorisiert“ auf die
    Kategorie der ursprünglichen Buchung in derselben Änderung
    (`erwartungen.md` 13.2, `protokoll.md` 19).
  - Eingebauter Mock-Datensatz mit Amazon-/PayPal-Mails und Umsätzen
    (`erwartungen.md` 13.3).
  - Kachel „Was kommt noch?“ auf der Finanzübersicht, Serien auf
    `/erwartet` (`oberflaeche.md` 34).
- **Bezug:** K 1, K 9, K 14; T 3.5, T 3.6, T 19.
- **Tests:** `tests/app/m24/` (Marker `m24`, Hilfen `tests/hilfen/m24.py`,
  Serien über die Referenzkette); 13.1 und 13.2 als `kern`, 13.3 REST ohne
  `kern`, Oberfläche mit Playwright (E-234 bis E-236).
- **Spezifikation:** `erwartungen.md` 13; `protokoll.md` 19;
  `oberflaeche.md` 34; `openapi.yaml` 2.19.0; E-233 bis E-237.
- **Abhängigkeiten:** M5, M8, M16, M17, M18, M20.
- **Status:** spezifiziert und getestet (`tests/app/m24/`, Marker `m24`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M25 – Betragsfilter für wiederkehrende Buchungen

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-13 (Feature
`betragsfilter-wiederkehrend`, E-238). Ergänzt und ändert M16.

- **Umfang:**
  - Betragsfilter `aus`, `toleranz`, `mindestschwelle`; Vorgabe der Instanz
    (ausgeliefert `toleranz` 10 %, Betriebszustand) und eigene Einstellung je
    Empfänger (Buchbestand) (`wiederkehrend.md` 9.1, 9.3).
  - Kette mit Filter: Anker-Kandidaten, übergangene Einträge, Bruchgrund
    `betrag`, Mehrheitsregel der Vorgabe; Begründung mit Rolle
    `anderer_betrag` und Angaben zum Filter; Ereignisse (`wiederkehrend.md`
    9.2, 9.3.5).
  - Protokoll (`wiederkehrend_filter_setzen`), Sicherung (`schemaversion`
    6), Oberfläche `oberflaeche.md` 35.
  - M16-Tests mit Vorgabe `aus` (E-244).
- **Bezug:** K 9; T 3.5, T 3.6, T 10.
- **Tests:** `tests/app/m25/` (Marker `m25`, Hilfen `tests/hilfen/m25.py`,
  Referenzkette mit Filtern in `tests/hilfen/wiederkehrend_orakel.py`); REST,
  Kette, Begründung, Protokoll, Sicherung, Ereignisse als `kern`, Oberfläche
  mit Playwright (E-239 bis E-241); Referenz und Mutanten in der
  Selbstprüfung (E-243).
- **Spezifikation:** `wiederkehrend.md` 9; `protokoll.md` 20;
  `sicherung.md` 10; `oberflaeche.md` 35; `openapi.yaml` 2.20.0; E-238 bis
  E-244.
- **Abhängigkeiten:** M3, M5, M8, M9, M16.
- **Status:** spezifiziert und getestet (`tests/app/m25/`, Marker `m25`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M26 – Bedienung auf dem Handy

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-16 (Feature
`UXMobile`, schon auf main der App, E-246). Ändert das mobile Layout von M8 und
M17.

- **Umfang:**
  - Kopfzeile mit `suche-knopf` und `tabs-knopf`, Tab-Liste mobil zum
    Aufklappen, gekürzter Mock-Hinweis (`oberflaeche.md` 36.2).
  - Kontoansicht: lange Berührung beginnt den Auswahlmodus statt des
    Kontextmenüs, `auswahl-kopf`, `mehrfach-mehr`, Zurück beendet die Auswahl,
    schwebender Erfassen-Knopf (36.3); Wischgesten ohne Dauergrenze mit
    Hinweis (36.4).
  - Menüs und Dialoge als Blatt vom unteren Rand, Fokus nicht im Textfeld,
    Viewport `interactive-widget=resizes-content` (36.5); Tabellen als
    Karten, Suchtreffer, Filterleiste, Diagramme (36.6).
  - Statische Dateien unter `/oeffentlich/` mit `Cache-Control: no-cache`
    und `ETag`, 304 bei passendem `If-None-Match` (36.8, `sicherheit.md` 6).
  - Sechs frühere Browsertests angepasst (Definition 9, E-248).
- **Bezug:** K 5, K 14; T 19.
- **Tests:** `tests/app/m26/` (Marker `m26`, Hilfen `tests/hilfen/m26.py`);
  nur 36.8 als `kern` (REST ohne Browser), sonst Browsertests (E-247).
- **Spezifikation:** `oberflaeche.md` 36; `sicherheit.md` 6; `openapi.yaml`
  unverändert (2.20.0); E-246 bis E-248.
- **Abhängigkeiten:** M8, M17.
- **Status:** spezifiziert und getestet (`tests/app/m26/`, Marker `m26`);
  Feature auf main der App, Abnahme offen.

## M27 – Verdacht, Personen, Filter, Dubletten, Mail-Liste, Statistik

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-16 (Feature
`sammel`, REST-Teil, E-249). Rückwärtskompatibel: alles nur auf Anfrage oder
optional im Schema.

- **Umfang:**
  - Label „Verdächtig“ nur mit `verdacht=ja` (Empfänger unbekannt, Betrag mit
    robustem z), abgeleitet, nie gespeichert (`sammel.md` 1).
  - Tags an Empfängern (`tag_ids`, Personen als Tags), Zusammenführen,
    Tag löschen, Protokoll, Sicherung `schemaversion` ≥ 7 (2, `protokoll.md`
    21, `sicherung.md` 11).
  - Filter `zweck_gleich`, `zweck_leer`, `zweck_aehnlich`,
    `empfaenger_aehnlich` (3).
  - `POST /api/dubletten` (Aktion `dublette_anlegen`) und Vorschläge mit
    `vorschlaege=ja` (4).
  - Mail-Liste mit `reihenfolge`, `zuordnung`, `postfach`, `warum`, `stand`
    (`mail.md` 6.6).
  - `GET /api/statistik`, experimentell (6).
- **Bezug:** K 5, K 9, K 13; T 3.5, T 3.6.
- **Tests:** `tests/app/m27/` (Marker `m27`, Hilfen `tests/hilfen/m27.py`);
  alle REST-Tests `kern` außer der Inhaltsprüfung der Statistik (E-250).
- **Spezifikation:** `sammel.md`; `mail.md` 6.6; `protokoll.md` 21;
  `sicherung.md` 11; `openapi.yaml` 2.21.0; E-249 bis E-251.
- **Abhängigkeiten:** M3, M7, M9, M12, M20, M25.
- **Status:** spezifiziert und getestet (`tests/app/m27/`, Marker `m27`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M28 – Oberfläche aus `feature/sammel`

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-16
(Oberflächenteil von `sammel`, E-252). Vorrang vor M27; ändert M8, M12, M13,
M15, M16, M17, M22, M24, M25 in der Oberfläche.

- **Umfang:** Person Torsten/Tina mit Pflichtdialog und Personenknopf
  (`oberflaeche.md` 37.1); Navigation in fünf Gruppen, Alt+1…7, Palette
  (37.2); Routen `/mail`, `/statistik`, `/wiederkehrend` entfällt (37.3, 37.4);
  Tab-Kontextmenü (37.5); Kontoblatt mit Gruppierung, Ausschnitt, Stiften,
  Kontextmenü, Filtern, Dublette, Bestätigen, Label „Verdächtig“, Kürzeln
  (37.6–37.11); Mail-Blatt, Statistik, Empfänger, Split-Vorlagen, Dubletten,
  leere Werte, Listenbreite (37.12).
- **Bezug:** K 5, K 14; T 19.
- **Tests:** `tests/app/m28/` (Marker `m28`, Hilfen `tests/hilfen/m28.py`);
  Browsertests und ein REST-Test der Routen, keine `kern` (E-255); Person in
  allen Browsertests (E-253); frühere Tests nach Definition 13 angepasst
  (E-254).
- **Spezifikation:** `oberflaeche.md` 37; `openapi.yaml` 2.21.0 (M27);
  E-252 bis E-255.
- **Abhängigkeiten:** M8, M17, M26, M27.
- **Status:** spezifiziert und getestet (`tests/app/m28/`, Marker `m28`);
  Implementierung auf dem Feature-Branch, Abnahme offen.

## M29 – Bankabruf über FinTS/camt und Bankzugang in der Oberfläche

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-19 (Feature
`fints-camt`, `spec/definitionen/definition-1-fints-camt.md`, E-258). Ersetzt
M10 und ändert Teile von M6 und M11.

- **Umfang:**
  - Nur noch die Bank-Plugins `mock` und `fints`; `aqbanking` entfällt samt
    Konfiguration und Fehlerklasse (`bankzugang.md` 2, `python-api.md` 21).
  - FinTS-Plugin: `tan_verfahren()`, Kontenliste aus den
    SEPA-Kontoverbindungen, camt in der Version der Bank (.08, sonst .07 bis
    .02; kein Ausweichen auf MT940), Datumsformen, TAN bei der Anmeldung
    (`fints.md` 3.0–3.5a).
  - Synchronisation: ausgewählte Konten des Bankzugangs, TAN bei der
    Anmeldung im Lauf, Bankzugang ohne Neustart wirksam, Übergang alter
    Bank-Kennungen (`synchronisation.md` 21, `bankzugang.md` 3).
  - Bankzugang über REST (`/api/bank/zugang…`), Diagnoseprotokoll ohne
    persönliche Daten (`bankzugang.md` 4, 5), Oberfläche `oberflaeche.md` 38.
  - Betriebszustand: kein Protokoll, nichts in der Sicherung.
- **Bezug:** K 3, K 6; T 6, T 7, T 16, T 19, T 21.
- **Tests:** `tests/app/m29/` (Marker `m29`, Hilfen `tests/hilfen/m29.py`);
  FinTS-Attrappe mit zusätzlichen Betriebsarten (E-263); Übergang über
  `kontor.sync.kennungen_als_alt_markieren` (E-264); Oberfläche mit Playwright
  wie M8; `tests/app/m10/` und der AqBanking-Teil von M11 entfernt, M6 und
  der gemeinsame Plugin-Test angepasst (E-259 bis E-261).
- **Spezifikation:** `bankzugang.md`; `fints.md` 3–3.5a, 6;
  `synchronisation.md` 21; `python-api.md` 21; `plugins.md` 12;
  `oberflaeche.md` 38; `openapi.yaml` 2.22.0; E-258 bis E-267.
- **Abhängigkeiten:** M2, M3, M6, M7, M8, M9, M11, M23.
- **Status:** spezifiziert und getestet (`tests/app/m29/`, Marker `m29`);
  Implementierung auf main von kontor-app (Version 0.21 ff.), Abnahme offen.

## M30 – Kontor-Ausdrücke, Filter im Kontoblatt, Regeleditor und Regel-Tags

Meilenstein-Definition vom 2026-11-19 mit Nachtrag 1 (Features `ausdruecke`,
`regeleditor-feinschliff`, `regel-tags`, `regel-anwenden-fenster`,
`spec/definitionen/definition-2-ausdruecke-regeln.md` und
`definition-2-nachtrag.md`), übernommen auf Auftrag vom 2026-11-22 (E-268).
Ändert Teile von M2, M3, M8, M9, M11, M12, M17, M26 und M28.

- **Umfang:**
  - Ausdruckssprache für Regel-Bedingungen und Filter (Felder, Operatoren,
    Datumsangaben, Freitext, kanonische Schreibweise; `ausdruecke.md` 2).
  - `GET /api/ausdruck/sprache`, `POST /api/ausdruck/pruefen` (Fehlerstelle,
    kanonischer Text, Datumsangaben), `POST /api/ausdruck/als-regel`
    (`ausdruecke.md` 4).
  - Parameter `filter` und `stichtag` an `GET /api/buchungen` und am Export,
    `markierungen` (`ausdruecke.md` 5).
  - Regeln mit `ausdruck` oder `bedingungen`, Kategorie optional, Tags
    (`tag_ids`); erste passende Regel mit Kategorie, Tags aller passenden
    Regeln; `POST /api/regeln/reihenfolge`, `/test`, `/erklaeren`,
    `POST /api/regeln/{id}/anwenden`; Verweise beim Löschen und
    Zusammenführen (`kategorisierung.md` 8, `loeschen.md` 8).
  - Protokoll (Aktion `regeln_reihenfolge`, Protokollform der Regel,
    `protokoll.md` 22), Sicherung `schemaversion` ≥ 9 (`sicherung.md` 12).
  - Oberfläche: Ausdrucksfeld, Filter im Kontoblatt mit Baukasten statt der
    Einzelfelder, Regelliste, Regeleditor mit Testbereich, Fenster „Regel
    anwenden“, Tag-Dialog mit vorhandenen Tags, Fehlermeldungen mit Feld und
    Regel (`oberflaeche.md` 39).
- **Bezug:** K 5, K 7, K 14; T 3.5, T 3.6, T 8, T 19.
- **Tests:** `tests/app/m30/` (Marker `m30`, Hilfen `tests/hilfen/m30.py`);
  REST-Tests als `kern`, Oberfläche mit Playwright wie M8 (nicht `kern`);
  Lesarten E-272, E-274; Umstellung der Datenbank und ältere Sicherungen
  nicht prüfbar (E-273); frühere Tests und Hilfen nachgezogen (E-271);
  Selbstprüfung ohne Referenz für M30 (E-275).
- **Spezifikation:** `ausdruecke.md`; `kategorisierung.md` 8;
  `protokoll.md` 22; `sicherung.md` 12; `loeschen.md` 8; `datenmodell.md`
  19; `oberflaeche.md` 39; `openapi.yaml` 2.23.0; E-268 bis E-276.
- **Abhängigkeiten:** M2, M3, M8, M9, M11, M12, M17, M19, M27, M28.
- **Status:** spezifiziert und getestet (`tests/app/m30/`, Marker `m30`);
  Implementierung auf main von kontor-app (Version 0.31 ff.), Abnahme offen.

## M31 – Übrige Features vor dem Sammelbranch: Einzelheiten, Branch-Anzeige, Lernmodell-Transparenz, automatische Regeln, Testinstanz, Monatsbericht und Berichte, Einstellungen in Bereichen, Bestellnummer-Mails, Gruppierung

Meilenstein-Definition 3 vom 2026-11-22 (`spec/definitionen/definition-3-uebrige-features-vor-sammel3.md`),
übernommen auf Auftrag ohne gesonderte Freigabe („direkt weiter“, E-277).
Ändert Teile von M8, M13, M20, M23, M28 und M29.

- **Umfang:**
  - Lernmodell: Erklärung je Buchung, Übersicht, Schwelle und
    `regeln_automatisch` als Einstellung der Instanz, automatisch angelegte
    Regeln mit Sperre beim Löschen, Mock-Lerndaten (`lernmodell.md` 8–10).
  - Monatsbericht und neun weitere Berichte (`berichte.md` 6).
  - Mails über die Amazon-Bestellnummer an der Buchung, erwartete Zahlungen
    im Betrieb vorerst aus (`erwartungen.md` 14).
  - Branch statt Version außerhalb von main (`version.md` 6); Testinstanz
    (`betrieb.md` 9).
  - Oberfläche `oberflaeche.md` 40 (Einzelheiten, Namen, Lernmodell,
    Einstellungen in Bereichen, Mail-Datum, Gruppierung mit Abschnitt und
    Tiefe, Berichtswahl).
  - Protokoll `protokoll.md` 23, Sicherung `sicherung.md` 13, Konfiguration
    `python-api.md` 22, `openapi.yaml` 2.24.0.
- **Bezug:** K 2, K 5, K 7, K 11, K 13, K 14; T 3.5, T 3.6, T 8, T 15, T 19, T 21.
- **Tests:** `tests/app/m31/` (Marker `m31`, Hilfen `tests/hilfen/m31.py`);
  REST und Konfiguration als `kern`, Oberfläche mit Playwright (nicht `kern`);
  Lesarten E-279 bis E-288; frühere Tests nachgezogen (E-291); W-015/W-016
  gelöst (E-289, E-290); Selbstprüfung ohne Referenz für M31 (E-292).
- **Spezifikation:** wie Umfang; E-277 bis E-292.
- **Abhängigkeiten:** M4, M5, M8, M9, M13, M18, M20, M25, M27, M28, M29, M30.
- **Status:** spezifiziert und getestet (`tests/app/m31/`, Marker `m31`);
  Implementierung auf main von kontor-app (Version 0.37), Abnahme offen.

## M32 – Sammelbranch `feature/sammel3`: Kontonamen, Empfänger, Tags, Mail-Blatt, Anbieter-Beschreibungen, PayPal, Konfiguration, UX-Durchgang, Änderungsprotokoll, geplante Zahlungen, HTTPS

Meilenstein-Definition 4 vom 2026-11-22 (`spec/definitionen/definition-4-sammelbranch-sammel3.md` mit Anlagen
unter `spec/definitionen/anlagen/`), übernommen auf Auftrag ohne gesonderte Freigabe („direkt weiter“, E-293).
**Nicht rückwärtskompatibel;** ändert Teile von M1, M3, M4, M8, M9, M19, M20, M27, M28 und M31 (E-307).

- **Umfang:**
  - Kontonamen je Ebene eindeutig (409 `konto_existiert`), Bereinigen bei Import und Einspielen
    (`sammel3.md` 1).
  - Standardkategorie je Empfänger entfällt; `GET /api/empfaenger/anzahlen`,
    `GET /api/empfaenger/{id}/konten` (`sammel3.md` 2).
  - Statistische Analyse entfällt (`sammel3.md` 3).
  - Mail-Liste mit `suche`, `gruppieren`, Zuordnen von Hand, `betrag` der angehängten Buchungen; Bilder fremder
    Server auf Wunsch (`sammel3.md` 8).
  - Anbieter-Beschreibungen (`anbieter_verzeichnis`), PayPal nach Betrag, Zeitfenster und Händler
    (`sammel3.md` 9).
  - `GET /api/konfiguration` (`sammel3.md` 11); geplante Zahlungen mit Wiederholung, Fortsetzung, Zuordnung
    nach Namen und Vorschau (`sammel3.md` 14); Betrieb hinter HTTPS (`sammel3.md` 15, `betrieb.md` 10).
  - Oberfläche `oberflaeche.md` 41 (Navigation mit Tags und Konfiguration, Empfänger, Dubletten, Bestätigung
    mit „B-<Name>“, Spalten, Auswahl-Summen, Tags-Seite, Einzelheiten im Änderungsprotokoll, Erfolgsmeldung nur
    mit Einstellung, Mail-Blatt, Handy-Kontoblatt, Tabs).
  - `openapi.yaml` 2.25.0, `protokoll.md` 24, `sicherung.md` 14 (`schemaversion` ≥ 10), `python-api.md` 23.
- **Bezug:** K 4, K 5, K 7, K 11, K 13, K 14; T 3.5, T 3.6, T 3.7, T 8, T 14, T 19, T 21.
- **Tests:** `tests/app/m32/` (Marker `m32`, Hilfen `tests/hilfen/m32.py`); REST und Konfiguration als `kern`,
  Oberfläche mit Playwright (nicht `kern`); Lesarten E-295 bis E-306; frühere Tests nachgezogen (E-307);
  Widersprüche W-017 bis W-021 gelöst (E-309 bis E-311); Selbstprüfung ohne Referenz für M32 (E-308).
- **Spezifikation:** `sammel3.md`; `oberflaeche.md` 41; E-293 bis E-314.
- **Abhängigkeiten:** M3, M4, M8, M9, M18, M19, M20, M27, M28, M30, M31.
- **Status:** spezifiziert und getestet (`tests/app/m32/`, Marker `m32`); Implementierung auf main von
  kontor-app (Version 0.37), Abnahme offen.
