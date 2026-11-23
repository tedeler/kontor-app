# Meilenstein-Definition: übrige Features seit M28 (ohne FinTS/camt, ohne Ausdrücke/Regeln)

Stand: 2026-11-22. Gehört zum Auftrag „kontor-tests auf den Stand von main bringen“. Alle beschriebenen Features
sind in der Anwendung auf main (Version 0.37) umgesetzt und mit dem Auftraggeber im Lauf der Arbeit abgestimmt; er hat
auf eine gesonderte Freigabe dieser Definition verzichtet („direkt weiter“).

**Form:** Diese Definition ist aus den Entscheidungen der Implementierung zusammengestellt (Nummern `D-xxx`), bereinigt
um Verweise auf den Programmcode. Sie beschreibt Verhalten: Endpunkte, Felder, Fehlercodes, `data-testid`,
Konfiguration, Protokoll, Sicherung, Oberfläche. Vereinzelt stehen noch interne Namen (Tabellen, Logger, Schlüssel im
Browser-Speicher); sie sind keine Vorgabe, außer wo ein Test sie von außen braucht (z. B. ein Schlüssel im
Browser-Speicher, um eine Einstellung vorab zu setzen). Zahlen wie „Datenbankschema n“ sind intern; verbindlich ist nur
die Schemaversion der Sicherungsdatei.

**Lesart:** Spätere Einträge gehen früheren vor; maßgeblich ist der Endstand. Wo ein Eintrag etwas „ersetzt“, steht es
dabei. Abschnitte „Anlass“, „Verworfen“, „Messung“ sind Hintergrund, kein Prüfgegenstand. Hinweise „Folge für die
Abnahme“ nennen frühere Abnahmetests, die das neue Verhalten berührt.

**Offene Punkte:** Wo eine Angabe fehlt (genaue Feldnamen einer Antwort, Fehlercode eines Randfalls), entscheidet der
Test-Thread nach Spezifikation und Konzept und hält es als `E-xxx` fest; die Implementierung richtet sich danach oder
meldet einen Widerspruch als Text.

**Nicht hier:** FinTS/camt und Bankzugang (D-197 bis D-204) stehen in der Projektdatei
`claude/meilenstein-fints-camt.md`; Ausdrücke, Filter, Regeleditor, Regel-Tags und das Anwenden-Fenster (D-185 bis D-196,
D-214 bis D-216) in `claude/meilenstein-ausdruecke-regeln.md` und `claude/meilenstein-ausdruecke-regeln-nachtrag.md`.

**Später geändert (Sammelbranch, Definition 4):** Die Standardkategorie je Empfänger entfällt (D-219) – wo D-179 sie
erwähnt, gilt das nicht mehr. Die Seite und der Endpunkt der statistischen Analyse entfallen (D-221). Die Meldung mit
„Rückgängig“ nach Änderungen ist ausgeliefert ausgeschaltet (D-234).

## 1 Einzelheiten einer Buchung: gegliederte Darstellung, lesbarer Verwendungszweck, Schreibweise von Namen

### D-175 Einzelheiten: gegliederte Darstellung und lesbarer Verwendungszweck (feature/detailansicht, Entwurf)
- **Kopf:** Empfänger und Betrag (Summe der Splits auf dem angezeigten Konto, `details-betrag`) groß, darunter
  Wochentag/Datum und der Status als farbige Marke; Randfarbe nach Ein-/Ausgang, 🔒 bei gesperrten Buchungen.
  Stifte, `data-feld` und Inline-Editoren bleiben wie in 37.8 (Namen nur für Vorleser verborgen).
- **Verwendungszweck nur in der Anzeige zerlegt**, gespeichert bleibt der Originaltext:
  Buchungsarten als Marken („Lastschrift / Belastung“, „Kartenzahlung“ …), SEPA-Schlüssel (EREF+, MREF+,
  CRED+, SVWZ+ …) als benannte Angaben, dazu Karte (mit Kartenart), ISO-Zeitpunkt und „Ref.“. Auch an
  zusammengeklebten Zeilen („BELASTUNGCAFE“) wird getrennt; Buchungsarten links nur nach Nicht-Buchstaben,
  rechts nicht vor Kleinbuchstaben. Wird nichts erkannt, erscheint der Text unverändert; sonst ist der
  Originaltext aufklappbar.
- Buchungssätze als Karten (eigenes Konto zurückgenommen, „Unkategorisiert“ hervorgehoben), Tags als Marken,
  Verdachtshinweis mit Warnsymbol (vorher wirkungslose Hintergrundfarbe wegen `--hg-1`).

### D-176 Verwendungszweck: ausgeschriebene Schlüssel, PayPal, Amazon (ergänzt D-175)
- Ausgeschriebene Schlüssel wie bei comdirect („END-TO-END-REF.:“, „MANDATSREF.:“, „GLÄUBIGER-ID:“,
  „KUNDENREFERENZ:“) gliedern wie SEPA-Schlüssel; „Ref.“ beendet den Wert davor. Ein „CORE“/„B2B“/„COR1“ direkt
  vor „ / “ ist das Lastschriftverfahren und wird eigene Angabe. Leere Werte und „NOTPROVIDED“ entfallen.
- PayPal („<Kennung>/PP.<Nr>.PP/. <Händler>, IHR EINKAUF BEI <Händler>“): Marke „PayPal“, Kennung als
  PayPal-Referenz, Text „Einkauf bei <Händler>“. Amazon-Bestellnummern (`ddd-ddddddd-ddddddd`, auch mit x
  maskiert) als Bestellnummer. Kennungen, die schon als Angabe stehen, erscheinen nicht noch einmal im Text.
- Sichtbar bleiben Karte, Zeitpunkt, Bestellnummer und Verfahren; technische Kennungen (Referenzen, Mandat,
  Gläubiger-ID, PayPal) sind unter „Referenzen (n)“ aufklappbar.

### D-177 Empfängernamen in normaler Schreibweise (nur Anzeige)
- Namen, die ganz in Groß- oder ganz in Kleinbuchstaben vorliegen („AMAZON“, „amazon“), zeigt die Oberfläche in
  normaler Schreibweise („Amazon“): erster Buchstabe je Wort groß (auch nach Bindestrich und Schrägstrich),
  kleine Wörter mitten im Namen klein („Cafe am Markt“), bekannte Abkürzungen und Rechtsformen in üblicher Form. Gemischt geschriebene Namen („eBay GmbH“)
  bleiben unverändert, weil sie bewusst so erfasst sind.
- Nur Anzeige (`nameAnzeige`): Buchungsliste der Kontoansicht, Kopf der Einzelheiten, Suchergebnisse und
  Einzelbuchungen der Berichte. Gespeichert, gesucht, gefiltert und in Auswahllisten/Empfängerverwaltung wird
  der Name wie erfasst; Texte vom Server (z. B. Verdachtshinweis) bleiben unverändert.
- Verwendungszweck (Frage aus D-175): bleibt beim Import unverändert; die Gliederung erfolgt nur in der Anzeige,
  damit alte und neue Buchungen für Regeln, Lernmodell und Dublettenerkennung gleich aussehen.

## 2 Branch statt Version außerhalb von main

### D-178 Branch statt Version außerhalb von main
- **Anlass:** Auf einem Entwicklungsstand soll man sofort sehen, welcher Branch läuft, und ihn im Repository öffnen
  können.
- **Entscheidung:** Die Anwendung liest den Branch aus dem Git-Verzeichnis ihres Quellbaums. Git wird dabei nicht
  aufgerufen, Worktrees mit einer `.git`-Datei werden unterstützt. Für Releases, bei losgelöstem
  HEAD und für Namen außerhalb von `[A-Za-z0-9._/-]` liefert sie None.
- Ist der Branch nicht `main`, schreibt der Server beim Ausliefern der Hülle statt „Version x.yy“ den Link
  `zweig-link` („⎇ Branch“, auf `<Repository>/tree/<Branch>`, neues Fenster) in den Fuß der Navigation. Der Knopf
  `version-knopf` heißt dann „Über“ und öffnet weiter das About-Fenster. Dort steht zusätzlich die Zeile „Branch“
  (`ueber-zweig`). Auf main und in Releases bleibt alles wie bisher.
- `GET /api/version` bleibt unverändert, der Branch steht nur in der Hülle. Der

## 3 Lernmodell: automatische Regeln, Erklärung je Buchung, Seite „Lernmodell“, Einstellungen, Mock-Lerndaten

### D-179 Automatisch angelegte Regeln aus dem Gelernten (Feature `lernmodell-transparenz`, in Arbeit)
- **Auftrag (2026-11-16):** Gelerntes wird automatisch zur sichtbaren Regel, sofern das System danach genauso gut
  kategorisiert. Messung auf dem M4-Lerndatensatz des Generators (30 Startwerte, rund 7.900 Prüfbuchungen):
  Genauigkeit 98,40 % und Abdeckung 84,94 % mit und ohne automatische Regeln; 1.373 Prüfbuchungen liefen über eine
  automatische Regel, alle richtig.
- **Auslöser:** Ein Empfänger hat in der Trainingsmenge (lernmodell.md 3) mindestens 5 Buchungen derselben
  Kategorie, diese Kategorie hat mindestens 95 % seiner Buchungen in der Trainingsmenge, und alle seine Buchungen der Trainingsmenge aus den letzten 365 Tagen (App-Uhr) haben diese Kategorie
  (mindestens eine). Keine Regel, wenn der Empfänger eine Standardkategorie hat, wenn schon eine automatische Regel
  für ihn besteht oder gesperrt ist, oder wenn eine aktive Regel seine jüngste Buchung bereits trifft.
- **Regel:** Name = Empfängername (die Liste zeigt die Kategorie dahinter), Bedingung `empfaenger gleich <Name>`, aktiv, Priorität wie beim
  Anlegen ohne Angabe (ans Ende). Vermerk in `regel_automatisch` (Objektart `regel`); die Regel trägt in API und
  Protokollform zusätzlich `automatisch: true` und `empfaenger_id` (nur bei automatischen Regeln, sonst fehlen die
  Felder). Sonst eine gewöhnliche Regel: bearbeitbar, abschaltbar, löschbar.
- **Löschen** einer automatischen Regel sperrt den Empfänger (`empfaenger_lernregel_sperre`, Objektart
  `empfaenger`, Form `lernregel_gesperrt: true` nur bei gesperrten); Rückgängig hebt die Sperre mit auf.
- **Zeitpunkt:** nach jeder Änderung mit Quelle `manuell` oder `import`, die Buchungen berührt, für die Empfänger
  dieser Buchungen (vorher und nachher), als **eigene Änderung** `quelle = "lernmodell"`, `aktion =
  "regel_automatisch"` direkt danach. Die Oberfläche legt beide Änderungen als einen Rückgängig-Schritt ab und
  meldet „Regel „…“ automatisch angelegt.“ mit Link zu den Regeln. Synchronisation, Regeln, Lernmodell und
  Rückgängig lösen nichts aus (sie erzeugen keine neuen bestätigten Zuordnungen bzw. sollen nicht zurückwirken).
- **Einstellung:** `regeln_automatisch` / `KONTOR_REGELN_AUTOMATISCH`, Vorgabe aus (bestehende Abnahmetests
  unverändert); die ausgelieferte `kontor.env` schaltet ein. Die Seite „Lernmodell“ soll den Schalter später
  übernehmen.
- **Bekannte Grenze:** Die Bedingung vergleicht den Namen. Wird der Empfänger umbenannt, greift die Regel nicht
  mehr; die Regel wird nicht nachgezogen.
- Schema: Datenbank 13, Sicherungsdatei 8 (neue Tabellen `regel_automatisch`, `empfaenger_lernregel_sperre`;
  ältere Sicherungen ohne sie).

### D-180 Lernmodell: Doppelzählung Empfänger/Verwendungszweck bleibt
- Geprüft wurde, Zweckwörter, die auch im Empfängernamen stehen, nicht zusätzlich als Merkmal zu zählen. Messung
  wie D-179: Genauigkeit unverändert 98,40 %, Abdeckung 84,94 % → 84,63 %. Die Sicherheit ist auf diesen Daten
  nicht überhöht (Vorhersagen mit 50–60 % stimmen zu 90 %). Das Verfahren aus lernmodell.md 4 bleibt daher
  unverändert; die Verlässlichkeit der Prozentangabe soll stattdessen auf echten Daten angezeigt werden.

### D-181 Lerndaten nach echten Kontoauszugsmustern
- 3000 synthetische Buchungen eines Girokontos (09/2022–10/2026) nach Mustern des Auftraggebers: Miete, Gehalt,
  Supermärkte mit Uhrzeit/Terminal/Kartennummer, PayPal mit Händler im Zweck, Amazon ohne Artikel, Tankstelle
  (Kraftstoff/Shop), Lastschriften mit Mandat, Abos, Gutschriften, Umbuchungen auf eigene Konten, drei neue
  Empfänger in der Prüfzeit, etwa 3 % falsch erfasste Kategorien. Ältere 80 % kategorisiert, neueste 20 % auf
  „Unkategorisiert“ mit bekannter Wahrheit. Alle Namen und Nummern erfunden bzw. Beispielwerte.
- Messung 2026-11-16 (574 Prüfbuchungen mit Kategorie): Lernmodell allein 89,0 % Abdeckung, 99,2 % Genauigkeit;
  mit automatischen Regeln (16 Regeln) 89,5 % Abdeckung, 99,2 % Genauigkeit. Amazon bleibt erwartungsgemäß meist
  ohne Vorschlag (3 von 47), PayPal wird über den Händler im Zweck erkannt.

### D-182 „Lernmodell anwenden“ heißt „Vorschläge für unkategorisierte Buchungen“; Einschätzung ohne Vorschlag
- Der Knopf auf der Seite Regeln (`lernmodell-anwenden`, `POST /api/lernmodell/anwenden`) heißt jetzt
  „Vorschläge für unkategorisierte Buchungen“ und erklärt im Tooltip, was geschieht: nur Buchungen auf
  „Unkategorisiert“, ab 70 % ein Vorschlag, kein Training (das Modell lernt ohnehin laufend). Die Meldung nennt das
  Ergebnis („5 von 7 unkategorisierten Buchungen haben einen Vorschlag erhalten; 2 bleiben offen“).
- „Regeln anwenden“ meldet jetzt die Zahl der Vorschläge. Vorher las die Oberfläche das nicht vorhandene Feld
  `geaendert` und zeigte nie eine Zahl.
- Einzelheiten einer unkategorisierten Buchung ohne Vorschlag zeigen „Kein Vorschlag“ mit Grund (unbekannte
  Merkmale, beste Kategorie unter der Schwelle, oder: das Modell würde vorschlagen) und die Kandidaten des
  Lernmodells ab 1 % mit „Übernehmen“ (`details-einschaetzung`, `details-einschaetzung-grund`,
  `details-einschaetzung-kandidaten`, `details-kandidat-<id>`). Lesezugriff über `POST /api/lernmodell/vorhersage`.

### D-183 Transparenz des Lernmodells: Erklärung je Buchung, Seite „Lernmodell“, Einstellungen der Instanz
- **`GET /api/buchungen/{id}/lernmodell`** (Lesezugriff): `grund` (`vorschlag`, `unter_schwelle`, `unbekannt`,
  `kein_modell`), Vorhersage wie 5.3, `beste_kategorie_id`, `vergleich_kategorie_id` (zweitbeste), je Merkmal der
  Buchung die Zählungen `anzahl` = N(f), `anzahl_kategorie`, `anzahl_vergleich`, die drei häufigsten Kategorien und
  `faktor_promille` = ⌊1000 · Faktor(beste)/Faktor(zweite)⌋ mit Faktor = (N_c(f)+1)/(N_c+2) (lernmodell.md 4), dazu
  der Grundwert N_c/n. Das Produkt aller Faktoren ist genau P(beste)/P(zweite): keine Näherung, das Verfahren
  bleibt unverändert. `aehnliche`: bis zu 5 Trainingsbuchungen mit den meisten gemeinsamen Merkmalen (Empfänger
  zählt dreifach, Betrag nicht).
- **`GET /api/lernmodell/uebersicht`** (Lesezugriff, zwischengespeichert bis zur nächsten Änderung oder
  Schwellenänderung): Güte wie lernmodell.md 6 auf den eigenen Daten (Trainingsmenge nach Datum, neueste 20 %,
  höchstens 2000, als Prüfung), Vorschläge/richtig je Schwelle 50–95 %, Verlässlichkeit je Zehntel der Sicherheit,
  je Kategorie Beispiele, Prüfung, erkannt, häufigste Verwechslungen und die fünf stärksten Merkmale.
- **`GET`/`PUT /api/lernmodell/einstellungen`**: `schwelle_promille` (500–990, Vorgabe 700) und
  `regeln_automatisch` (Vorgabe aus `KONTOR_REGELN_AUTOMATISCH`) als **Einstellung der Instanz in `meta`**, nicht im
  Änderungsprotokoll und nicht in der Sicherung – wie die Vorgabe des Betragsfilters (D-137). Abweichend vom
  Konzept (dort: Änderung im Protokoll), weil eine Schwelle kein Buchbestand ist. `GET /api/lernmodell` meldet die
  wirksame Schwelle; mit der Vorgabe 700 ist alles wie lernmodell.md.
- **Oberfläche:** Einzelheiten zeigen bei Vorschlägen des Lernmodells „Warum dieser Vorschlag?“, bei Buchungen ohne
  Vorschlag „Warum?“ (aufklappbar, `lern-warum`): Satz, Merkmale mit Balken (dafür/dagegen gegenüber der
  nächstbesten Kategorie), Verwendungszweck mit markierten Wörtern, ähnliche Buchungen (Links `/buchungen/<id>`).
  Neue Seite `/lernmodell`, erreichbar über „Lernmodell …“ auf der Seite Regeln und den
  Link in der Erklärung. **Kein Eintrag in der Navigation**: die Navigation ist in oberflaeche.md 37.2 fest
  aufgezählt (16 Links); ein Eintrag gehört in die Meilenstein-Definition.

### D-184 Mock-Lerndaten eingecheckt; automatische Regeln mit Toleranz im letzten Jahr
- Die 3000 Lerndaten (D-181) gehören zum Mock: sie werden mit der Anwendung ausgeliefert. `POST /api/mock/lerndaten` lädt sie im Mock-Modus in einen
  Bestand ohne Buchungen (sonst 409 `bestand_nicht_leer`; außerhalb des Mock-Modus 409 `nur_mock_modus`), als eine
  Änderung `quelle = "import"`, `aktion = "mock_lerndaten"` (rückgängig zu machen). Die Seite Import bietet im
  Mock-Modus den Knopf „Lerndaten laden (3.000 Buchungen)“.
- **Ersetzt in D-179 die Bedingung „in den letzten 365 Tagen nie anders“:** in den 365 Tagen bis zur jüngsten
  Buchung des Empfängers in der Trainingsmenge (bzw. bis heute, falls früher) ebenfalls mindestens 95 %. Das
  Fenster hängt damit an der Geschichte des Empfängers, nicht an der Uhr. Beim Laden auf einmal verhinderte sonst ein einzelner Fehlgriff (3 % der Lerndaten) die Regel für
  häufige Empfänger wie den Supermarkt, während sie beim schrittweisen Erfassen früh entstand.

## 4 Testinstanz für Entwicklungsstände

### D-205 Testinstanz für Entwicklungsbranches statt Branch-Wechsel im Update-Dienst
- **Anlass:** Ein Entwicklungsbranch soll sich mit den echten Daten ausprobieren lassen. Der Update-Dienst (D-107)
  installiert nur Releases mit Prüfsumme, und ein Branch kann das Schema migrieren; ein Zurück auf main gäbe es nur
  über Sicherung und Wiederherstellung. Mit dem Auftraggeber abgestimmt (2026-11-19): kein Branch-Wechsel im
  Update-Dienst, sondern eine zweite, getrennte Instanz. M14 und der About-Dialog bleiben unverändert.
- **Entscheidung:** Ausgeliefert werden `kontor-test.service` und `kontor-test.env` sowie die Kommandozeile
  `python -m kontor.testinstanz` (`einrichten <Branch>`, `stoppen [--loeschen]`, als root mit dem Python der
  Hauptinstanz). Programm unter `/opt/kontor-test` (Quellbaum `src`, eigene virtuelle Umgebung `venv`), Daten unter
  `/var/lib/kontor-test`, Port 8081.
- **Mock-Modus:** Die Testinstanz läuft mit `KONTOR_MOCK_MODUS=1`; ihre Mock-Datenbank ist die Datenkopie. Damit
  sind Bank-, Mail- und Benachrichtigungs-Plugin Attrappen, die Update-Suche entfällt, und die Oberfläche zeigt den
  Hinweisbalken. Zeitgesteuerter Abruf und Mail-Abruf sind zusätzlich abgeschaltet. Folge: Ein Branch, der am
  echten Bankabruf arbeitet, lässt sich so nicht gegen die Bank prüfen – das ist gewollt.
- **Datenkopie:** Online-Sicherung von SQLite aus der laufenden Hauptdatenbank (nur lesend geöffnet, Pfad aus
  `KONTOR_DATENBANK` in `/etc/kontor/kontor.env`). Vor der Übergabe werden `geheimnis`, `geheimnis_huelle`,
  `tan_anforderung` geleert und `meta.bank_fints_…` sowie `meta.bank_diagnose` entfernt; danach `VACUUM`, damit die
  Chiffretexte auch nicht in freien Seiten bleiben. Die Kopie ersetzt eine frühere erst, wenn sie fertig ist.
- **Anmeldung:** Haushaltspasswort und Sitzungen bleiben in der Kopie (nur Hashes). Das Sitzungs-Cookie gilt je
  Rechnername, nicht je Port; mit übernommenen Sitzungen ist man in beiden Instanzen angemeldet, statt sich
  gegenseitig abzumelden.
- **Installation des Branches:** `git clone --depth 1 --branch` in ein neues Verzeichnis, dann editierbar
  installieren. Nur so findet die Anwendung (D-178) den Branch und zeigt den Branch statt der Version. Ein
  Git-Archiv oder Wheel hätte keinen Branchnamen. Schlägt das Klonen fehl (Branch unbekannt, kein Netz), bleibt
  eine laufende Testinstanz unberührt. Branchnamen werden streng geprüft (kein führendes `-`, kein `..`).
- **Benutzer:** dasselbe Systemkonto `kontor`, kein zweites. Die Trennung leistet die Unit:
  `StateDirectory=kontor-test`, `ProtectSystem=strict` und `InaccessiblePaths` für `/var/lib/kontor` und
  `/etc/kontor/kontor.env`; keine `LoadCredentialEncrypted`-Zeile, gleiche Härtung wie `kontor.service`.
- **Betrieb:** Kein `[Install]`-Abschnitt (startet nicht beim Hochfahren), keine Sicherungs-Unit, kein
  Update-Verzeichnis. Die Unit wird bei jedem Einrichten erneuert, die Umgebungsdatei nur angelegt.
- **Nicht im Umfang:** Rückweg von Änderungen aus der Testinstanz in die Hauptinstanz; Auswahl in der Oberfläche.

### D-213 Bedienskript und Anleitung für die Testinstanz (ergänzt D-205)
- **Auftrag (2026-11-19):** Eine Anleitung zum Starten der Testinstanz und ein Skript für die wiederkehrenden
  Schritte; auf ausdrückliche Anweisung ohne Meilenstein-Definition und Abnahmetests auf main gemergt (Branch
  `feature/testinstanz-skript`).
- **Entscheidung:** `betrieb/kontor-test.sh` (Paketdaten, Ziel `/usr/local/bin/kontor-test`) mit den Befehlen
  `start <branch>`, `neu`, `stop`, `loeschen`, `status`, `log`. Das Skript kopiert selbst nichts: Branch holen,
  Daten kopieren und Starten bleibt allein Sache von `python -m kontor.testinstanz` (D-205); das Skript ruft es
  auf, wartet bis zu 30 s auf den Port und zeigt die Adresse, bei Misserfolg die letzten Protokollzeilen.
- Ein Branchname ohne `/` außer `main` wird zu `feature/<name>` ergänzt. Der zuletzt eingerichtete Branch steht
  in `/root/.kontor-test-branch` (nur nach erfolgreichem Einrichten geschrieben); `neu` richtet ihn erneut ein.
- Der Port kommt aus `KONTOR_PORT` in `/etc/kontor/kontor-test.env`, ersatzweise 8081.
- Anleitung: `TESTINSTANZ.md` im Wurzelverzeichnis, Verweis in der README.
- **Nicht geprüft:** Lauf unter systemd auf dem echten Server (wie bei D-205).

## 5 Monatsbericht

### D-206 Monatsbericht: Ausgaben eines Monats rein statistisch (Feature `monatsbericht`)
- **Anlass:** Auftrag vom 2026-11-19: ein Bericht, der ohne Kategorien eine bessere Übersicht über die Ausgaben
  eines Monats gibt; Tabellen und Grafiken ansprechend und interaktiv.
- **Entscheidung:** Neuer lesender Endpunkt `GET /api/berichte/monat` (`monat=JJJJ-MM`, Vorgabe der laufende
  Monat der App-Uhr; `konto_id` mehrfach, nur Bestandskonten, Vorgabe alle Bestandskonten ohne Darlehenskonten)
  und die Seite `/berichte/monat`. Kein Zustand, kein Protokoll, nichts in der Sicherung. Noch nicht im
  OpenAPI-Vertrag; das folgt mit der Meilenstein-Definition.
- **Was eine Ausgabe ist:** Die Wirkung einer Buchung ist die negierte Summe ihrer Splits auf Konten, die keine
  Bestandskonten sind. Wirkung 0 ist eine Umbuchung zwischen eigenen Konten und zählt nicht (die Anzahl wird
  genannt); von einer Kreditrate zählt so nur der Zinsanteil. Negative Wirkung ist eine Ausgabe, positive eine
  Einnahme. Ein Eingang, der nur gegen Aufwandskonten gebucht ist, gilt als Erstattung und mindert die Ausgaben
  (wie im Bericht Einnahmen und Ausgaben). Das ist die einzige Stelle, an der die Kontoart der Gegenseite
  eingeht; eine nicht kategorisierte Erstattung zählt als Einnahme.
- **Fest und variabel:** Fest sind Ausgaben, die zu einer Serie der Erkennung wiederkehrender Buchungen gehören
  (Serienerkennung zum Stichtag, mit den Betragsfiltern). Alles andere ist variabel.
- **Laufender Monat:** Stichtag ist heute. Vergleiche in der Kachel „Ausgaben“ beziehen sich dann auf den Stand
  des Vormonats und des Schnitts am selben Tag, nicht auf deren Monatssumme. Hochrechnung = bisherige Ausgaben
  + noch fällige feste Zahlungen aktiver Serien + variabler Tagesschnitt der 90 Tage vor Monatsbeginn mal
  Resttage (ohne Vorgeschichte der Tagesschnitt des laufenden Monats).
- **Vergleiche:** Verlaufsschnitt über die letzten sechs Monate mit Daten; Monatsvergleich über zwölf Monate;
  „üblich“ je Empfänger ist der Monatsschnitt der letzten sechs Monate mit Daten. Ausreißer: Ausgabe außerhalb
  einer Serie, robustes z ≥ 3,5 gegenüber mindestens vier früheren Ausgaben an denselben Empfänger in zwölf
  Monaten und mindestens 5 € über deren Median. Neue Empfänger: keine Buchung in den zwölf Monaten davor.
  Größenklassen fest: unter 10 €, 10–50 €, 50–200 €, 200–1 000 €, ab 1 000 €.
- **Oberfläche:** Kein neuer Eintrag in der Navigation (die Abnahmetests zählen deren Einträge auf); erreichbar
  über den Knopf „Monatsbericht“ auf der Seite Berichte und die Befehlspalette. Monat und Konten stehen in der
  Adresse (`?monat=`, `?konto=`), der Tab merkt sie sich. Diagramme mit dem vorhandenen Plotly-Paket; Kalender,
  Balken und Anteile sind HTML, damit sie ohne Plotly und mit Tastatur bedienbar bleiben.

## 6 Einstellungen in Bereichen mit Suche

### D-207 Einstellungen in Bereichen mit Suche (Feature `einstellungen`, in Arbeit)
- **Anlass:** Die Einstellungen waren eine lange Seite mit elf Abschnitten; einzelne Einstellungen waren schwer zu
  finden, Seltenes (Diagnoseprotokoll, Produkt-ID, OAuth-Client-Secret) stand gleichrangig neben Alltäglichem.
- **Entscheidung:**
  - Sechs Bereiche: Allgemein (Design, Layout, Angaben zur Instanz), Bank (Bankzugang, PIN), Mail (Postfächer,
    Abruf), Benachrichtigungen (Zustellung, Test, ntfy-Token), Sicherheit (Anmeldung, Schutz der Geheimnisse),
    Daten und Sicherung (Datensicherung, Tags). Der Abschnitt „Geheimnisse“ entfällt: Jedes Geheimnis steht bei
    seiner Aufgabe (ntfy-Token bei den Benachrichtigungen, OAuth-Client-Secret bei Mail).
  - Navigation: am Desktop eine Spalte links neben dem Inhalt, am Handy eine Liste, die in den Bereich führt
    (Rückweg „Alle Einstellungen“). Reiter scheiden aus (zu eng am Handy, wachsen schlecht). Gezeigt wird immer
    genau ein Bereich; ohne Angabe am Desktop „Allgemein“, am Handy nur die Liste.
  - Adresse: `/einstellungen?bereich=<name>`. Der Bereich steht im Abfrageteil und nicht im Pfad, damit die
    Einstellungen ein einziger Tab bleiben (Tabs hängen am Pfad, D-119). Unbekannter Wert wie ohne Angabe. Der
    Wechsel des Bereichs lädt nichts nach (alle Bereiche werden einmal aufgebaut, die übrigen sind `hidden`).
  - Stand je Bereich in der Navigation (`einstellungen-status-<name>`, `data-zustand` = `ok`/`offen`/`fehler`/
    `neutral`), z. B. „Bankzugang unvollständig“, „Zugang vollständig · 2 von 3 Konten ausgewählt · PIN fehlt“.
    Die Bedeutung steht im Text; der farbige Punkt ist nur Beigabe.
  - Suche über den Bereichen (`einstellungen-suche`): filtert beim Tippen ein festes Verzeichnis der Einstellungen
    mit Synonymen („backup“ → Sicherung, „dunkelmodus“ → Design), Umlaute gefaltet wie in der Befehlspalette. Ein
    Treffer führt in den Bereich, klappt „Erweitert“ auf, rollt hin, hebt kurz hervor und setzt den Fokus. Einträge,
    die es in dieser Instanz nicht gibt (Bankzugang im Mock-Modus), erscheinen nicht.
  - „Erweitert“ (`<details>`, eingeklappt, nennt im Titel seinen Inhalt): Kunden-ID und Produkt-ID, Diagnoseprotokoll,
    OAuth-Client-Secret. Offen von Anfang an, wenn darin etwas fehlt oder läuft (Pflichtfeld Produkt-ID leer,
    Diagnose eingeschaltet). Was aufgeklappt wurde, bleibt über das Neuladen nach einer Aktion offen (nur im
    Arbeitsspeicher des Fensters).
  - Bankzugang in vier Schritten (Zugangsdaten, Bank-PIN, TAN-Verfahren, Konten), jeder Knopf bei seinem Schritt,
    die Meldung erscheint im Schritt der Aktion. Stand der PIN und „PIN verwerfen“ stehen im Schritt 2 (bisher
    eigener Abschnitt); im Mock-Modus bleiben sie eine eigene Karte.
  - Alle bisherigen `data-testid` bleiben unverändert; neu sind nur `einstellungen-…`, `passwort-alt`/`-neu`/
    `-aendern`, `postfach-neu-adresse`/`-anlegen`, `mail-abrufen`. Keine Änderung an Endpunkten oder Datenmodell.
  - Keine Einträge je Bereich in der Befehlspalette: Zwei Abnahmetests (M8, M28) prüfen deren Trefferlisten.
- **Folge für die Abnahme:** Sieben Browsertests öffnen `/einstellungen` und bedienen Elemente, die jetzt in einem
  anderen Bereich liegen (im Dokument vorhanden, aber nicht sichtbar): M8 `test_einstellungen_geheimnis_und_sicherung`,
  `test_einstellungen_test_benachrichtigung_mock`/`_ntfy`, `test_pin_dialog`, `test_schreiben_mit_csrf_und_abmelden`;
  M23 `test_einstellungen_schutz`; M28 `test_abmelden_vergisst_person`. Sie brauchen nur den Bereich in der Adresse.
  Das klärt der Test-Thread mit der Meilenstein-Definition. Die übrigen Browsertests verhalten sich wie auf main
  (dort schlagen 49 unabhängig von diesem Feature fehl).

## 7 Mails über die Bestellnummer an die Buchung; Datum der Mail

### D-208 Mails über die Amazon-Bestellnummer an die Buchung, erwartete Zahlungen vorerst aus (Feature `amazon-bestellnummer`)
- **Auftrag (2026-11-19):** Die erwarteten Zahlungen (D-128) sind dem Auftraggeber noch zu fehleranfällig und
  werden vorerst abgeschaltet. Stattdessen: Trägt eine Buchung eine Amazon-Bestellnummer, hängen alle Mails mit
  dieser Nummer im Betreff oder Text an dieser Buchung.
- **Erwartete Zahlungen:** Der Code bleibt unverändert hinter `mail_abgleich`. Die ausgelieferten
  Umgebungsdateien (`kontor.env`, `kontor-test.env`) setzen `KONTOR_MAIL_ABGLEICH=0`. Vorhandene erwartete
  Zahlungen und ihre Zuordnungen bleiben in der Datenbank, es entstehen keine neuen und keine Meldungen
  „überfällig“. Eine schon installierte `/etc/kontor/kontor.env` ändert sich durch ein Update nicht; dort muss
  die Zeile von Hand umgestellt werden.
- **Neue Einstellung** `mail_bestellnummer` (`KONTOR_MAIL_BESTELLNUMMER`, Wahrheitswert wie die anderen Schalter,
  Vorgabe aus, ausgeliefert an). Vorgabe aus, damit bestehende Abläufe und Abnahmetests unverändert bleiben.
- **Regel:** Bestellnummer = `ddd-ddddddd-ddddddd` ohne angrenzende Ziffer. Gesucht wird in Verwendungszweck und
  Empfängername jeder Buchung (zusätzlich ohne Leerraum, weil Bankzeilen die Nummer umbrechen) und in Betreff und
  Text jeder gespiegelten Mail, unabhängig vom Absender. Je Treffer hängt die ganze Mail und jeder PDF-Anhang als
  Dokument (Quelle `mail`) an der Buchung. Beträge, Datum und Anbietername spielen keine Rolle. Mehrere Buchungen
  mit derselben Nummer (Teillieferungen) bekommen alle dieselben Mails; dieselbe Mail in zwei Postfächern zählt
  einmal. Hängt ein Dokument gleichen Inhalts schon an der Buchung, entsteht kein zweites.
- **Wann:** nach jedem Mail-Abruf und nach jedem Synchronisationslauf mit Endstatus, nach den erwarteten
  Zahlungen. Eine Änderung im Protokoll (Quelle `mail`, Aktion `bestellmail_anhaengen`) entsteht nur, wenn etwas
  angehängt wurde; sie lässt sich rückgängig machen.
- **Gemerkt wird** je (Buchung, Nachrichten-ID), dass die Mail behandelt ist (Tabelle `bestellmail`,
  Betriebszustand: nicht protokolliert, nicht in der Sicherung). Löst der Anwender ein so angehängtes Dokument
  oder macht er die Änderung rückgängig, kommt die Mail nicht von selbst wieder. Nach dem Einspielen einer
  Sicherung wird das Gemerkte geleert und neu geprüft.
- **Mail-Liste:** Mit `mail_bestellnummer` trägt jeder Eintrag von `GET /api/mail/nachrichten` das Feld
  `angehaengt` (Buchungen mit `id`, `datum`, `konto_id`, `empfaenger`, `verwendungszweck`, `nummer`, `warum`);
  solche Mails zählen in `stand` und im Filter als `zugeordnet`. Ohne die Einstellung fehlt das Feld (Vertrag
  `openapi.yaml` unverändert). Die Seite `/mail` zeigt die Buchung mit der Marke „Bestellnummer“.
- **Abnahmetests:** `tests/app/m20/test_m20_erkennung.py::test_ausgelieferte_umgebungsdatei` erwartet
  `KONTOR_MAIL_ABGLEICH=1` und ist damit bewusst rot, bis die Meilenstein-Definition dieses Features übernommen
  ist. Alle übrigen Tests von M6, M9, M18, M20, M24 und M27 verhalten sich wie auf main.

### D-209 Bestellnummer auch im Quelltext der Mail suchen (ergänzt D-208)
- **Anlass:** Eine Buchung mit Amazon-Bestellnummer bekam keine Mails, obwohl das Postfach sieben Mails mit der
  Nummer enthält (Bestellt, Versendet, In Zustellung, Zugestellt).
- **Vermutete Ursache (an echten Mails nicht prüfbar):** Der gespiegelte Text einer Mail ist nur ihr erster
  Klartextteil (mail.md 3.3). Steht die Nummer nur im HTML-Teil oder in der Adresse eines Verweises, fand D-208 sie
  nicht.
- **Entscheidung:** Zusätzlich zu Betreff und gespiegeltem Text werden alle Textteile der Rohfassung im Quelltext
  durchsucht (Klartext und HTML samt Verweisadressen). Jede Mail wird einmal durchsucht; die gefundenen Nummern
  stehen in `bestellmail_nummer` (Betriebszustand). Mails ohne Rohfassung (Mock, zu große Mails) zählen wie
  bisher nur mit Betreff und Text.
- Jeder Lauf schreibt eine Zeile ins Log (`kontor.bestellmail`, Stufe INFO) mit der Zahl der angehängten Mails.

### D-210 Datum der E-Mail in den Einzelheiten (Feature `mail-datum`)
- **Auftrag (2026-11-19):** Im Abschnitt „Dokumente“ der Einzelheiten soll bei angehängten E-Mails das Datum der
  Mail stehen.
- **Entscheidung:** Neben jeder angehängten E-Mail steht ihr Datum (`dokument-datum-<id>`, Tag.Monat.Jahr in
  Ortszeit, voller Zeitpunkt im Tooltip und in `data-zeitpunkt`), vor der Größe. Andere Dokumente bekommen kein
  Datum. Mails ohne lesbares Datum zeigen nichts.
- **Quelle:** das Feld `datum` der vorhandenen Mail-Ansicht `GET /api/dokumente/{id}/mail` (Kopfzeile `Date`),
  je Dokument einmal gelesen und für die Sitzung gemerkt. Kein neues Feld in `belege` oder im Dokument, damit der
  Vertrag `openapi.yaml` unverändert bleibt.

## 8 Kontoblatt: Gruppierung nach Datum

### D-211 Gruppierung nach Datum: vier feste Abschnitte je Monat (Feature `kontoblatt-gruppierung`)
- **Anlass:** Zwischen Monat und Tag fehlte eine Ebene; ein Monat mit vielen Buchungen zerfiel sofort in bis zu
  31 Tagesbalken. Kalenderwochen scheiden aus, weil sie am Monatswechsel geteilt werden müssten.
- **Entscheidung** (mit dem Auftraggeber am 2026-11-19 abgestimmt): „nach Datum“ zeigt Jahr → Monat → Abschnitt →
  Tag (ergänzt D-152). Jeder Monat hat vier feste Abschnitte: 1.–7., 8.–14., 15.–21. und 22. bis Monatsende
  (7 bis 10 Tage). Die Grenzen sind in jedem Monat gleich, damit feste Zahlungen (Miete, Gehalt) immer im selben
  Abschnitt stehen und die Abschnitte zusammen genau den Monat ergeben.
  - Beschriftung ist nur der Datumsbereich mit dem tatsächlichen Monatsende („08.–14.11.“, „22.–29.02.“), kein
    Wort wie „Woche“. Kalenderwochen bleiben als Filter (`kw46`) erhalten, nicht als Gruppierung.
  - Schlüssel des Abschnitts: `JJJJ-MM-a1` … `-a4` (`data-periode`, `periode-…`, `periode-summe-…` usw. wie bei den
    anderen Ebenen), `data-ebene="abschnitt"`. Abschnitte ohne Buchung erscheinen nicht.
  - Balken, Zahlen, Klappen, Pfeiltasten und „Alles zusammenklappen/aufklappen“ wie bei den übrigen Ebenen. Keine
    Änderung an Endpunkten, Adresse (`?gruppierung=datum`) oder Datenmodell.
  - Der
- **Folge für die Abnahme:** Abnahmetests, die die Folge oder Anzahl der Balken unter einem Monat fest erwarten
  (Monat direkt gefolgt von Tagen), brauchen die neue Ebene; das klärt der Test-Thread mit der Meilenstein-Definition.

### D-212 Tiefe der Gruppierung wählbar (Feature `kontoblatt-gruppierung`)
- **Anlass:** Mit D-211 hat die Gruppierung vier Ebenen. Auf ruhigen Konten ist das zu viel, und ein Tag mit einer
  einzigen Buchung belegt zwei Zeilen (Tagesbalken und Buchung).
- **Entscheidung** (mit dem Auftraggeber am 2026-11-19 abgestimmt): Die Leiste über der Liste heißt jetzt
  „Keine | Jahr | Monat | Abschnitt | Tag“ und ersetzt „Keine | nach Datum“ (ergänzt D-152). Die gewählte Ebene ist
  die tiefste, alle darüber bleiben; die Buchungen stehen direkt unter der tiefsten Ebene. Eine Ebene in der Mitte
  lässt sich nicht auslassen (Monat → Tag ohne Abschnitt gibt es nicht); dem Auftraggeber reicht die Tiefe.
  - Adresse: `?gruppierung=datum&tiefe=jahr|monat|abschnitt`. Ohne `tiefe` und bei unbekanntem Wert gilt „Tag“
    (volle Tiefe), bestehende Adressen bleiben damit gültig; „Tag“ wird nicht in die Adresse geschrieben. `tiefe`
    ist wie `gruppierung` Ansicht und kein Parameter der Buchungsliste.
  - Kennungen: `gruppierung-keine` wie bisher, neu `gruppierung-jahr`, `gruppierung-monat`,
    `gruppierung-abschnitt`. Der Knopf „Tag“ behält die bisherige Kennung `gruppierung-datum`, weil er dieselbe
    Wirkung hat wie bisher „nach Datum“. Gedrückt (`aria-pressed`) ist immer genau ein Knopf.
  - Kürzel `v g` schaltet der Reihe nach: keine → Jahr → Monat → Abschnitt → Tag → keine (bisher keine ↔ nach Datum).
  - Zugeklappte Perioden bleiben beim Wechsel der Tiefe zugeklappt. Klappen, Summen und „Alles
    zusammenklappen/aufklappen“ gelten für die sichtbaren Ebenen.
  - Der
- **Folge für die Abnahme:** Tests, die die Beschriftung „nach Datum“ erwarten oder mit `v g` zweimal hin und zurück
  schalten, brauchen die neue Leiste bzw. Reihenfolge; das klärt der Test-Thread mit der Meilenstein-Definition.

## 9 Berichtswahl und weitere Berichte

### D-217 Berichtswahl und neun weitere Berichte (Feature `berichte`)
- **Anlass:** Auftrag vom 2026-11-19: alle vorgeschlagenen Berichte umsetzen; die Berichtsart wird auf der
  Berichtsseite gewählt.
- **Berichtswahl:** Alle Berichte liegen unter `/berichte?art=<name>` in einem Tab; eine Leiste oben wechselt die
  Art. Ohne `art` (und mit `art=uebersicht`) erscheint die bisherige Seite mit Kontostandsverlauf und
  Einnahmen/Ausgaben unverändert, damit bestehende Adressen und Abnahmetests gelten. Der Monatsbericht ist die Art
  `monat`; die frühere Adresse `/berichte/monat` führt dorthin. Der Palettenbefehl „Gehe zu: Monatsbericht“ und
  der Knopf auf der Berichtsseite (D-206) entfallen, die Leiste ersetzt beide. Kein neuer Eintrag in Navigation
  oder Palette.
- **Endpunkte** (alle lesend, kein Zustand, noch nicht im OpenAPI-Vertrag): `GET /api/berichte/vertraege`, `jahr`,
  `vorschau`, `vermoegen`, `kategorien`, `empfaenger`, `geldfluss`, `qualitaet`, `tags`. Unbekannte Parameter sind
  ein Validierungsfehler.
- **Gemeinsame Grundlage:** die Wirkung einer Buchung wie in D-206. Neu, auch für den Monatsbericht: Splits auf
  Eigenkapitalkonten außer „Unkategorisiert“ (Anfangsbestand, Korrekturen) sind neutral wie Bestandskonten; ein
  Anfangsbestand ist also keine Einnahme.
- **Verträge:** Serien der Erkennung wiederkehrender Buchungen. Eine Serie, deren letzte Buchung nur Bestands- und
  Eigenkapitalkonten berührt, ist eine Umbuchung (Sparrate) und erscheint nicht. Jahreskosten = aktueller Betrag
  mal Zahlungen je Jahr; „neu“ = erste Zahlung in den letzten 90 Tagen.
- **Jahr:** Der Vergleich mit dem Vorjahr bis zum laufenden Monat erscheint nur, wenn das Vorjahr in jedem dieser
  Monate Buchungen hat.
- **Vorschau:** Vorgabe sind die offenen Girokonten. Ereignisse sind die fälligen Zahlungen aktiver Serien
  (hier einschließlich Umbuchungen, weil sie das Konto verlassen) und die Raten aktiver Kredite, sofern nicht
  schon eine Serie mit gleichem Betrag auf dem Zahlungskonto erkannt ist. Übliche Ausgaben: variabler Tagesschnitt
  der letzten 90 Tage. „Frei bis zum nächsten Eingang“ = Stand heute minus feste Zahlungen und übliche Ausgaben
  bis zum nächsten erkannten Eingang.
- **Vermögen:** alle Bestandskonten zum Monatsende; Guthaben ist die Summe der positiven, Schulden die der
  negativen Stände. Tilgung = Abstand zum höchsten Monatsendstand der Schuld.
- **Kategorien und Geldfluss:** Unterkategorien zählen in ihre Hauptkategorie. „Unkategorisiert“ folgt der
  Richtung der Buchung. Schnitt über die bis zu sechs Vormonate mit Buchungen. Im Geldfluss wandert eine im
  Saldo negative Kategorie auf die andere Seite; die Lücke heißt „Übrig“ oder „Aus dem Bestand“. Das Flussbild
  ist handgezeichnetes SVG (das vorhandene Plotly-Paket kennt kein Flussdiagramm); auf dem Handy stehen nur die
  beiden Tabellen.
- **Tags:** Eine Buchung trägt ihre eigenen Tags und die ihres Empfängers. Mit mehreren Tags zählt sie bei jedem
  voll; deshalb gibt es keine Summe über alle Tags, nur „mit Tag“ und „ohne Tag“. Vergleich für zwei bis vier Tags.
- **Datenqualität:** betrachtet die letzten zwölf Monate ohne Umbuchungen. Tags gelten als freiwillig und gehen
  in keine Bewertung ein.

