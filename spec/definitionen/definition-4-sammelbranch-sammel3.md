# Meilenstein-Definition: Sammelbranch `feature/sammel3` (D-218 bis D-239)

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

**Anlagen** (Anleitungen der Anwendung, kein Code): `anlagen/ANBIETER.md` (Format der Anbieter-Beschreibungen, zu
D-230/D-232), `anlagen/HTTPS.md` (zu D-239), `anlagen/TESTINSTANZ.md`.

**Innerhalb dieses Pakets ersetzt:** D-232 ersetzt die Annahme aus D-230 zur PayPal-Zuordnung. D-236 ändert die
Reihenfolge in der Zuordnungsspalte der Mail-Liste (D-227: jetzt Marke, Betrag, Ziel, „+n“), den Ort der Auswahl-Summen
(D-231) und die Darstellung der Dubletten (D-222). D-238 benennt den Grund „Manuell“ in der Oberfläche in „Geplant“ um.

**Nicht automatisch prüfbar:** Die Skripte aus D-239 brauchen root, systemd und Tailscale. Prüfbar ohne das sind die
ausgelieferten Dateien (Vorhandensein, Aufrufe, Hilfe), die Startwarnung und das Verhalten hinter einem
TLS-Proxy auf Loopback (Herkunftsprüfung mit `oeffentliche_url`, Secure-Cookie).

## 1 Kontonamen je Ebene eindeutig

### D-218 Kontonamen je Hierarchieebene eindeutig (Sammelbranch `feature/sammel3`)
- **Anlass:** Auftrag vom 2026-11-19: Kategorien dürfen auf ihrer Ebene nur einmal mit gleichem Namen vorkommen.
  Abgestimmt: Vergleich ohne Groß-/Kleinschreibung, gilt für alle Konten, Altbestand automatisch zusammenführen,
  Importe führen zusammen, alles andere wird abgelehnt. Ändert `datenmodell.md` („Keine Eindeutigkeit gefordert“).
- **Regel:** Unter demselben Elternkonto ist ein Name nur einmal erlaubt; verglichen wird ohne Leerraum am Rand und ohne
  Unterschied von Groß- und Kleinschreibung. Auf der obersten Ebene gilt das je Kontoklasse (Bestand, Aufwand, Ertrag, Eigenkapital): „Zinsen“
  als Aufwand und als Ertrag bleiben nebeneinander möglich, zwei Bestandskonten „Giro“ nicht.
- **Ablehnen:** Anlegen, Umbenennen, Verschieben, Löschen mit hochrutschenden Unterkonten, Zusammenführen mit
  mitwandernden Unterkategorien und Rückgängig enden mit 409 `konto_existiert` (`details.konto_ids`), auch im
  Probelauf. Geprüft wird am Ende jeder protokollierten Änderung, die Konten berührt.
- **Bereinigen** (Altbestand beim Start, nach jedem Import, nach dem Einspielen einer Sicherung): gleichnamige
  Kategorien (Aufwand/Ertrag) werden in die mit der kleinsten ID zusammengeführt (Buchungen, Regeln, Vorlagen,
  Unterkategorien wandern mit; entstehen dadurch neue Dubletten, werden auch sie bereinigt). Bestandskonten,
  Eigenkapitalkonten und Kategorien mit Kreditbezug werden nicht zusammengeführt, sondern bekommen den Zusatz
  „(2)“, „(3)“ …; zwei Bankkonten automatisch zu vereinen wäre nicht umkehrbar und fachlich falsch.
- **Altbestand:** eine Änderung im Protokoll (Aktion `kategorien_zusammenfuehren`, Quelle `manuell`,
  Beschreibung „Gleichnamige Konten bereinigt“); ihr Rückgängig wird nach obiger Regel abgelehnt.
- **Importe:** Warnungen `konto_zusammengefasst` bzw. `konto_umbenannt` (Referenz: Name). Die zweite Kategorie
  behält keine eigene `extern_id`; ein erneuter Import legt sie deshalb kurz an und führt sie wieder zusammen
  (Bestand danach unverändert, der Zähler `kategorien_neu` nennt sie aber erneut).
- **Technische Konten** („Unkategorisiert“, „Korrekturen“): gibt es beim ersten Bedarf schon ein gleichnamiges
  Eigenkapitalkonto ohne Kennung auf der obersten Ebene, wird es übernommen statt ein zweites anzulegen.
- **Synchronisation:** ein neu angelegtes Bankkonto bekommt bei Namensgleichheit den Zusatz „(2)“.

## 2 Empfänger: Regel erstellen, Standardkategorie entfällt, Anzeigen im Konto

### D-219 Standardkategorie je Empfänger entfällt; „Regel erstellen…“ im Empfänger-Tab
- **Anlass:** Auftrag vom 2026-11-19; abgestimmt: ganz entfernen, vorhandene in Regeln umwandeln.
- **Umwandlung:** Beim Start (eine Änderung „Standardkategorien in Regeln umgewandelt“, Aktion `regel_anlegen`)
  und beim Einspielen älterer Sicherungen wird aus jeder Standardkategorie die Regel „Empfänger ist <Name>“ →
  Kategorie, am Ende der Regelliste (entspricht der bisherigen Stufe nach den Regeln).
- **Entfällt:** die Stufe „Standardkategorie“ bei Synchronisation und Erfassen (neu: Kreditrate → Vorlage → Regel →
  Lernmodell → „Unkategorisiert“), Feld und Spalte im Empfänger-Tab. `standardkategorie_id` bleibt als Feld der
  Empfängerform stehen und ist immer `null`, damit ältere Protokolleinträge und Sicherungen lesbar bleiben; ein
  anderer Wert wird mit 422 `kategorie_ungueltig` abgelehnt. Die Spalte der Datenbank und der Sicherungsdatei
  bleibt (leer). Alte Vorschläge mit Quelle `standardkategorie` bleiben gültig.
- **Kontextmenü `em-regel` „Regel erstellen…“:** öffnet den Regeleditor mit dem Namen des Empfängers und dem
  Ausdruck `empf == "<Name>" or empf == "<Alias>" …`; Kategorie und Tags wählt der Nutzer dort.

### D-220 Empfänger-Tab: „Anzeigen im Konto …“
- Kontextmenü `em-im-konto`: öffnet das Kontoblatt eines Bestandskontos mit dem Empfänger als Filter
  (`/konten/<id>?empfaenger_id=<id>`). Mit Buchungen auf mehreren Konten ein Untermenü (`em-im-konto-<konto-id>`,
  die meistbenutzten zuerst, mit Anzahl), ohne Buchungen ausgegraut. Neuer lesender Endpunkt
  `GET /api/empfaenger/{id}/konten` → `[{konto_id, anzahl}]` (noch nicht im OpenAPI-Vertrag).

## 3 Statistische Analyse entfällt

### D-221 Statistische Analyse entfällt
- Seite `/statistik` (jetzt 404), Navigationseintrag, Palettenbefehl und `GET /api/statistik` (D-145) sind
  entfernt; die Aussagen stehen in den Berichten (D-217).## D-222 Dubletten: zur Buchung springen
- Jede Buchung eines Verdachts oder Vorschlags auf `/dubletten` zeigt ihren Verwendungszweck und je Bestandskonto
  einen Verweis „Zeigen in: <Konto>“ (`dublette-buchung-<id>-konto-<konto-id>`), der wie in den Berichten ins
  Kontoblatt springt und die Buchung markiert.

## 4 Dubletten: zur Buchung springen


## 5 Bestätigung mit Tag „B-<Name>“

### D-223 Bestätigung trägt das Tag „B-<Name>“
- Abgestimmt: Die Bestätigung von Buchungen und Empfängern nutzt die Tags „B-Torsten“ / „B-Tina“ statt „Torsten“ /
  „Tina“. Vorhandene Tags werden beim Start (eine Änderung, Aktion `tag_umbenennen`) und beim Einspielen älterer
  Sicherungen umbenannt; gibt es das neue Tag schon, wandern die Zuordnungen dorthin. `data-bestaetigt` und
  `data-person` nennen weiter den Namen der Person.

## 6 Kontoblatt: Spalten, Summen der Auswahl, Bereichsauswahl bei Gruppierung

### D-224 Kontoblatt: Spalten ein- und ausblenden
- Kontextmenü der Kopfzeile: „Spalten ein- und ausblenden“ (`km-spalten-wahl`) mit einem Eintrag je Spalte
  (`km-spalte-<feld>`, Haken = sichtbar). Mindestens eine Spalte bleibt. Gemerkt im Browser je Listenart (Konto,
  Kategorie) unter `kontor.spalten.aus`; in der kompakten Ansicht (Handy) ohne Wirkung. Die Zellen bleiben im
  Dokument (`data-spalten-aus` an der Liste, per CSS versteckt).

### D-231 Kontoblatt: Summen der markierten Buchungen
- **Anlass:** Auftrag vom 2026-11-20 („markieren von Mails im Kontoblatt“ – gelesen als: markierte Buchungen im
  Kontoblatt): Beim Markieren immer die Summe der Ausgaben, der Einnahmen und über alles zeigen.
- Sobald Buchungen markiert sind, stehen neben „n ausgewählt“ drei Beträge aus Sicht des Blatts: Ausgaben
  (`auswahl-ausgaben`), Einnahmen (`auswahl-einnahmen`) und Summe (`auswahl-summe`), je mit `data-betrag` in Cent;
  ohne Markierung ist `auswahl-summen` verborgen. Auf dem Handy stehen sie im Auswahlkopf
  (`auswahl-kopf-summen`). Gerechnet wird mit den geladenen Zeilen in ganzen Cent.

### D-233 Kontoblatt: Bereichsauswahl bei Gruppierung und anderer Sortierung
- **Anlass:** Fehlerbericht vom 2026-11-20: Nach Zeitraum gruppiert und nicht nach Datum sortiert, stimmen
  Darstellung und Markieren nicht.
- **Ursache:** Umschalt+Klick und Umschalt+Pfeil bestimmten den Bereich in der Reihenfolge der geladenen Liste
  (z. B. nach Betrag über alle Zeiträume), nicht in der angezeigten Reihenfolge (je Zeitraum). Dadurch wurden
  Buchungen quer durch die Zeiträume markiert. Jetzt gilt die angezeigte Reihenfolge; Buchungen in zugeklappten
  Zeiträumen gehören nicht zum Bereich.
- **Nicht gefunden:** eine davon unabhängige falsche Darstellung. Aufbau der Zeiträume, Reihenfolge innerhalb der
  Zeiträume und der gezeichnete Ausschnitt bei 700 Buchungen waren mit Sortierung nach Betrag und Empfänger
  richtig (geprüft im Browser).

## 7 Tags als eigene Ansicht

### D-225 Tags als eigene Ansicht
- Neue Seite `/tags` (Navigation `navlink-tags` nach „Kategorien“, Palette „Gehe zu: Tags“): Liste aller Tags mit
  Zahl der Buchungen, Anlegen, Umbenennen, Löschen. Ein Klick auf ein Tag zeigt darunter seine Buchungen (höchstens
  500, neueste zuerst) mit Summe und „Im Konto zeigen“; die Wahl steht in der Adresse (`?tag=<id>`). Anders als
  bei Kategorien öffnet sich kein Kontoblatt, weil Tags kein Konto sind; die Tag-Verwaltung in den Einstellungen
  bleibt.

## 8 Mail-Blatt und Mail-Ansicht

### D-226 Mail-Blatt: Darstellung, Suche, Mail von Hand zuordnen
- **Darstellung:** drei Spalten (Empfangen, Absender und Betreff, Zuordnung). Datum („Heute“, „Gestern“ oder
  Datum) und Uhrzeit stehen untereinander und brechen nicht um; Absender einzeilig, Betreff höchstens zweizeilig;
  das Postfach erscheint nur, wenn mehrere Postfächer gemischt gezeigt werden.
- **Suche** (`mail-suche`, REST `suche`): jedes Wort muss in Absender, Betreff oder Text vorkommen (ohne
  Groß-/Kleinschreibung und Umlautunterschied); wirkt zusammen mit Postfach und Zuordnungsfilter, steht in der
  Adresse.
- **Zuordnen von Hand** (`mail-zuordnen` „Buchung zuordnen…“, `POST /api/mail/nachrichten/{id}/buchung` mit
  `buchung_id`, Aktion `dokument_aus_mail`): Dialog mit Buchungen von 14 Tagen vor bis 30 Tage nach der Mail
  (Zeitraum änderbar, Textsuche); Buchungen, deren Betrag in der Mail steht, zuerst und mit „Betrag passt“. Die
  Mail wird als Dokument an die Buchung gehängt und gilt im Mail-Blatt als zugeordnet („Von Hand“). Der Vermerk
  steht wie bei der Bestellnummer in `bestellmail` (leere Nummer, Betriebszustand); er entfällt, wenn das Dokument
  von der Buchung gelöst wird.
- Behoben: Der Lesebereich zeigte bei angehängten Mails „[object HTMLUListElement]“.

### D-227 Mail-Blatt: Zuordnung in der Liste als eine Zeile
- **Anlass:** Rückmeldung vom 2026-11-20: Die Zuordnungsspalte war unübersichtlich (mehrere Marken, dieselbe
  Buchung mehrfach, Begründungstexte in der Zeile).
- Die Spalte zeigt je Mail genau eine Zeile: Marke („Zugeordnet“, „Erwartet“, „Überfällig“), Ziel (erste Buchung als
  Sprung ins Kontoblatt bzw. Händler der erwarteten Zahlung), „+n“ für weitere, Betrag. Jede Buchung zählt einmal,
  auch wenn sie über Bestellnummer und erwartete Zahlung zugleich zugeordnet ist. Ohne Zuordnung steht „–“.
  Weg der Zuordnung als Tooltip; Begründungen, Kennung und alle Buchungen stehen nur im Lesebereich.

### D-228 Mail-Blatt: Mails derselben Zuordnung stehen beieinander
- **Anlass:** Auftrag vom 2026-11-20: Mails gruppieren, die zur gleichen Buchungszuordnung gehören.
- **Gruppe:** Mails, die dieselbe Buchung oder dieselbe erwartete Zahlung betreffen (auch mittelbar über eine
  dritte Mail), bilden eine Gruppe – gleich, ob über Bestellnummer, erwartete Zahlung oder von Hand zugeordnet.
- **Liste:** `GET /api/mail/nachrichten?gruppieren=ja` stellt eine Gruppe an die Stelle ihrer ersten Mail (nach der
  gewählten Reihenfolge), die übrigen Mails der Gruppe direkt dahinter; jede Mail trägt `gruppe` (ID der ersten
  Mail, sonst `null`). Ohne den Parameter bleiben Reihenfolge und Antwort wie bisher. Gruppiert wird innerhalb
  der gefilterten Menge (Postfach, Zuordnungsfilter, Suche); eine Gruppe kann über eine Seitengrenze reichen.
- **Oberfläche:** Das Mail-Blatt fordert immer gruppiert an. Die erste Mail zeigt die Zuordnung und „n Mails zu
  dieser Zuordnung“, die folgenden sind eingerückt und zeigen „↳ gehört dazu“; ein Balken am linken Rand
  verbindet die Gruppe (`data-gruppe`, `data-gruppe-rolle` = `kopf`/`folge`/`ende`).

### D-229 Mail-Ansicht: Bilder fremder Server auf Wunsch nachladen
- **Anlass:** Auftrag vom 2026-11-20: In der Mail-Ansicht des Kontoblatts fehlen die Bilder der Mail. Bisher
  entfernte die Ansicht jede fremde Bildadresse (Schutz vor Zählpixeln, dokumente.md); das bleibt die Vorgabe.
- **Nachladen:** Enthält die Mail Bilder fremder Server, zeigt die Ansicht eine Leiste (`mail-bilder-leiste`) mit der
  Anzahl, dem Knopf „Bilder laden“ (`mail-bilder-laden`) und dem Haken „immer laden“ (`mail-bilder-immer`, gemerkt
  im Browser unter `kontor.mail.bilder`). Erst dann lädt der Browser die Bilder direkt vom fremden Server; der
  Kontor-Server ruft nie selbst fremde Adressen ab.
- **Schnittstelle:** `GET /api/dokumente/{id}/mail/html?bilder=ja` lässt Bildadressen mit `http(s)://` (und `//`,
  als https) in `<img src>`, `background` und `url(…)` in Stilen stehen und liefert die Inhaltsrichtlinie mit
  `img-src data: https: http:`; alles andere bleibt wie bisher (keine Skripte, kein `srcset`, kein `@import`, keine
  Schriften, `sandbox`, kein Referrer). `GET /api/dokumente/{id}/mail/bilder` → `{"anzahl": n}`.
- **Folge:** Mit geladenen Bildern erfährt der Absender, dass und von welcher Adresse die Mail geöffnet wurde.

## 9 Anbieter-Beschreibungen und PayPal-Zuordnung

### D-230 Anbieter-Beschreibungen: Mail-Abgleich als zuladbare Module
- **Anlass:** Auftrag vom 2026-11-20: den Abgleich von Mail und Buchung für Amazon verallgemeinern und als
  zuladbare Module beschreiben (mit regulären Ausdrücken), damit er auch für PayPal und weitere Anbieter gilt.
- **Lösung:** Eine Beschreibung (TOML) nennt Absender, Kennung, Mailarten mit Rolle
  (`ausgabe`, `erstattung`, `storno`), Bausteine für Beträge und Texte und die Bankseite (Namen, Kennungsmuster).
  Mitgeliefert `amazon.toml` und `paypal.toml`; weitere aus `anbieter_verzeichnis`
  (`KONTOR_ANBIETER_VERZEICHNIS`). Beschreibung des Formats: `ANBIETER.md`.
- **Verallgemeinert:** (1) Erwartete Zahlungen: Schlüssel `<anbieter>:<mailart>:<kennung>` (für Amazon und PayPal
  unverändert), Storno und Erstattung beziehen sich auf die Mailart mit Rolle `ausgabe`. (2) „Name steht in der
  Buchung“: aus `bank.namen` statt des fest eingebauten „amzn“. (3) Anhängen über die Kennung (bisher nur
  Amazon-Bestellnummer, D-208): für jeden Anbieter mit `bank.kennung`; für PayPal der 17-stellige Transaktionscode,
  gesucht nur in PayPal-Mails (`alle_mails` aus), für Amazon weiter in allen Mails.
- **Datenbank:** Schemaversion 15: das Feld `anbieter` einer erwarteten Zahlung lässt jeden Namen einer Beschreibung zu (Tabelle wird
  umgebaut, Inhalt und Zähler bleiben). Gemerkte Kennungen der Mails (`bestellmail_nummer`) werden einmal neu
  gesucht, wenn sich die Muster ändern (`meta.bestellmail_muster`).
- **Grenzen:** Der Grund einer erwarteten Zahlung bleibt `bestellung` oder `paypal` (Vertrag der Schnittstelle).
  Python-`re` kennt kein Zeitlimit; geschützt wird über die Länge der Ausdrücke (500) und des ausgewerteten Textes
  (200 000 Zeichen). Beschreibungen sind Dateien des Betreibers, nicht aus der Oberfläche änderbar.
- **Offen:** Ob der PayPal-Transaktionscode im Verwendungszweck der Bank steht, ist mit echten Auszügen zu prüfen;
  sonst greift für PayPal nur Betrag und Name.

### D-232 PayPal: Zuordnung nach Betrag, Zeitfenster und Händlername (ersetzt die Annahme aus D-230)
- **Anlass:** Recherche vom 2026-11-20: Die PayPal-Lastschrift nennt keinen Transaktionscode. Der Verwendungszweck
  lautet „PP.1234.PP . HAENDLER, Ihr Einkauf bei HAENDLER“, die End-to-End-Referenz trägt eine 13-stellige Nummer,
  die in keiner Mail steht (PayPals Aktivitäten-Export kennt ein Feld „Bank Reference ID“ mit 13 Zeichen; ob es
  dieselbe Nummer ist, ist ungeprüft). Auftrag: Heuristik aus gleichem Betrag, Datum ± 5 Tage und Händlername in
  Teilen im Verwendungszweck.
- **Beschreibung PayPal:** `bank.kennung` entfällt; neu `bank.haendler` (Händler aus „PP.….PP . <Händler>, Ihr
  E…“), `haendler_noetig = true`, `tage_vor = 5`, `tage_nach = 5`. Diese Angaben stehen jedem Anbieter offen
  (`ANBIETER.md`); Amazon bleibt unverändert (3 Tage davor, 45 danach, Kennung oder Name).
- **Regel bei `haendler_noetig`:** Automatisch zugeordnet wird, wenn genau eine freie Buchung im Fenster den
  gleichen Betrag hat und den Händler der Mail in Teilen nennt: ein Wort des Namens mit
  mindestens 4 Zeichen irgendwo im Text, kürzere nur als ganzes Wort, Allerweltswörter zählen nicht; ein gekürzter
  Name der Bank zählt, wenn er der Anfang des zusammengeschriebenen Namens ist. Als PayPal-Buchung gilt, was
  „paypal“ nennt oder dem Muster des Verwendungszwecks entspricht. Nennt die Mail keinen Händler, wird nichts
  automatisch zugeordnet. Andere Buchungen gleichen Betrags ohne den Händler stören nicht mehr.
- **Folge für die Abnahme:** `m20/test_m20_zuordnung.py::test_automatisch_ueber_betrag_nur_eindeutig` ist rot: Der
  Test erwartet, dass eine zweite Buchung gleichen Betrags ohne Anbieter die Zuordnung der PayPal-Buchung
  verhindert. Für den Test-Thread als Änderung von erwartungen.md 5.2 zu übernehmen.

## 10 Meldung mit „Rückgängig“ ausgeschaltet

### D-234 Meldung mit „Rückgängig“ nach Änderungen ist ausgeschaltet
- **Anlass:** Auftrag vom 2026-11-20: Die Rückgängig-Anzeige nach Aktionen stört.
- Die Erfolgsmeldung mit `meldung-rueckgaengig` nach eigenen Änderungen erscheint nicht mehr, außer sie wird unter
  Einstellungen → Allgemein eingeschaltet (`einstellung-erfolgsmeldung`, gemerkt im Browser unter
  `kontor.meldung.erfolg`). Rückgängig bleibt über die Kopfzeile, Strg+Z und die Palette. Fehlermeldungen, Hinweise
  (z. B. automatisch angelegte Regel) und die Meldung nach einem Rückgängig selbst bleiben.
- **Folge für die Abnahme:** Browsertests, die die Erfolgsmeldung erwarten (oberflaeche.md 4.3), brauchen die
  Einstellung vorab, wie die Person (`browser_fixtures.neue_seite`).

## 11 Seite „Konfiguration“

### D-235 Seite „Konfiguration“ (Umgebungsdatei zum Nachsehen)
- **Anlass:** Auftrag vom 2026-11-20: eine Seite, die alle in der Umgebungsdatei gesetzten Konfigurationen zeigt; sie
  soll später in einem Entwicklermodus verschwinden.
- **Seite `/konfiguration`** (Navigation `navlink-konfiguration` unter „Betrieb“, auf dem Handy nicht in der
  Navigation; Palette „Gehe zu: Konfiguration“), nur lesend: (1) „In der Umgebung gesetzt“ – alle Variablen
  `KONTOR_…` (und `CREDENTIALS_DIRECTORY`) des laufenden Prozesses mit ihrem Text; Variablen, die Kontor nicht
  kennt, tragen „unbekannt“. (2) „Was gilt“ – jede Einstellung mit geltendem Wert, Vorgabe und Name der Variable,
  Abweichungen von der Vorgabe hervorgehoben und filterbar.
- **Schnittstelle** `GET /api/konfiguration` → `{umgebung: [{variable, wert, verborgen, bekannt}], wirksam: [{name,
  variable, gesetzt, wert, vorgabe, geaendert, verborgen}]}`; geschützt wie alle Endpunkte (Anmeldung).
- **Nie ausgegeben** werden Werte, deren Name nach einem Geheimnis klingt (Secret, Token außer `…_token_url`,
  Passwort, PIN außer `bank_pin_quelle`), sowie die Bank-Zugangskennungen `fints_benutzer` und `fints_kunden_id`;
  dort steht nur „verborgen“. Andere Umgebungsvariablen des Prozesses erscheinen nicht.
- **Grenze:** Gezeigt wird die Umgebung des Prozesses, nicht die Datei selbst; Kommentare und auskommentierte Zeilen
  der Datei sieht man nicht, dafür auch Werte aus der systemd-Unit.

## 12 UX-Durchgang

### D-236 UX-Durchgang auf `feature/sammel3`: 14 Funde umgesetzt
- **Anlass:** Auftrag vom 2026-11-20: UX-Tests ausführen, Verbesserungen mit Screenshots begründen; danach
  „Alle“ umsetzen. Geprüft im Mock-Modus mit synthetischen Daten, Desktop 1280 × 800 und Handy 390 × 844.
- **1 Mail-Ansicht:** leere Teile (Bilder-Leiste, Anhänge) erschienen als Wort „null“; sie entfallen jetzt.
- **2 Kontoblatt, Betrag:** die Betragsspalte klebt beim seitlichen Rollen am rechten Rand (Desktop); ist die Liste
  schmaler als 46 rem, gelten kleinere Mindestbreiten für Empfänger, Zweck und Kategorie. Eigene Spaltenbreiten
  (M22) bleiben unberührt. Die Vorgabe der Panels (beide offen, M8) ist bewusst nicht geändert.
- **3 Gruppenbalken:** so breit wie der sichtbare Teil der Liste, bleibt beim seitlichen Rollen stehen; in schmalen
  Listen nur die Zahlen (Eingang, Ausgang, „= Summe“), ohne Wörter und Buchungszahl. Alle `data-testid` bleiben.
- **4 Handy-Kontoblatt:** Filterfeld, Zeitraum-Chips und Gruppierung sind am Handy eingeklappt; `ansicht-umschalten`
  („Filter und Gruppierung“) klappt sie auf, ein Punkt zeigt einen aktiven Filter. „Baukasten“ bleibt sichtbar
  (oberflaeche.md 23.1). Am Desktop ändert sich nichts an der Sichtbarkeit.
- **5 Handy-Mail-Blatt:** keine Mail vorgewählt, die Liste steht zuerst (je Mail eine Karte); Antippen öffnet den
  Lesebereich, `mail-lesen-schliessen` schließt ihn. Am Desktop bleibt die erste Mail vorgewählt (oberflaeche.md 37).
- **6 Auswahl-Summen:** die Gruppierung steht jetzt in der Zeile der Zeitraum-Chips; die Infozeile gehört Anzahl,
  Summe und Auswahl allein, die Liste springt beim Markieren nicht mehr. Die Knöpfe heißen sichtbar „Alle zu“ /
  „Alle auf“; „Alles zusammenklappen“ / „Alles aufklappen“ (oberflaeche.md) stehen als `aria-label` und Tooltip.
- **7/8 Tags:** Datum ohne Umbruch, Knöpfe klein am Zeilenende (`tag-umbenennen-<id>`, `tag-loeschen-<id>`), am Handy
  Stift und Papierkorb mit Abstand, gewähltes Tag deutlich markiert, Sprungziele als Links mit „↗“ (gilt für alle
  Einzelbuchungstabellen, auch in den Berichten).
- **9 Mail-Blatt:** Status einzeilig (voller Text im Element, gekürzt angezeigt), Blättern unter der Liste, Betreff
  fett und Absender darüber in normaler Schrift, in der Zuordnung steht der Betrag vor dem Namen und wird nie
  gekürzt. Dafür trägt jede über Bestellnummer oder von Hand angehängte Buchung in der Mailliste `betrag` (Summe
  auf den Bestandskonten).
- **10 Empfänger:** Suche über Name und Aliase (`empfaenger-suche`, `empfaenger-treffer`; Tastatur und Strg+A folgen
  den sichtbaren Zeilen, verborgene verlieren die Auswahl), Spalte „Buchungen“ über `GET /api/empfaenger/anzahlen`
  → `[{empfaenger_id, anzahl}]` (nur lesend, Empfänger ohne Buchung fehlen), „Bearbeiten…“ ersetzt durch
  `empfaenger-menue-<id>` („⋯“, dasselbe Menü wie der Rechtsklick). `empfaenger-bestaetigen-<id>` bleibt mit Text.
- **11 Dubletten:** Gegenüberstellung als Tabelle, eine Spalte je Buchung, abweichende Angaben hervorgehoben
  (`data-abweichung`); Überschrift in Worten statt „Verdacht n (aehnlich)“; Hinweis, dass „Diese behalten“ die
  andere Buchung löscht. Knopftext „Diese behalten“ unverändert (oberflaeche.md).
- **12 Was kommt noch?:** bei überfälligen Einträgen sind nur Frist und Zustand rot, nicht die ganze Zeile.
- **13 Finanzübersicht:** Abstand in der Kachel, „Kategorien einblenden“ als Knopf mit Pfeil.
- **14 Tabs:** ab sechs Tabs steht am Ende der Leiste `tab-andere-schliessen` („Andere schließen“). Die Regel „jede
  Ansicht ein Tab“ (M17) bleibt; verworfen wurde, Navigationspunkte im selben Tab zu öffnen, weil das die
  freigegebene Definition ändern würde.
- **Nicht geändert:** grüne Hinterlegung kategorisierter Zeilen (M22).

## 13 Änderungsprotokoll: Einzelheiten je Änderung

### D-237 Änderungsprotokoll: Einzelheiten je Änderung in einem eigenen Fenster
- **Anlass:** Auftrag vom 2026-11-21 im Sammelthread: Das Änderungsprotokoll zeigt für jede Änderung eine
  detaillierte Liste der Änderungen in einem Extrafenster.
- **Entscheidung:** Jede Zeile des Protokolls hat den Knopf „Einzelheiten…“ (`aenderung-einzelheiten-<id>`; Tooltip:
  Umfang in Worten). Er öffnet das Fenster `aenderung-dialog` mit Zeitpunkt, Quelle, Vorgang (Code der Aktion),
  Umfang („3 Buchungen geändert, 1 Tag angelegt“), Stand (wirksam / rückgängig gemacht durch #n) und je betroffenem
  Objekt einem Abschnitt `ae-eintrag-<objekt>-<id>`: bei „geändert“ nur die abweichenden Angaben mit Vorher und
  Nachher, bei „angelegt“ und „gelöscht“ alle nicht leeren Angaben. Kennungen erscheinen als Namen (Konto mit Pfad,
  Empfänger, Tags; bei gelöschten Objekten aus derselben Änderung, sonst „#id“), Beträge in Euro, Datumsangaben
  deutsch, die Aufteilung je Split als „Konto: Betrag (Notiz)“.
- **Große Änderungen** (Import, Sicherung): zunächst 50 Objekte, „Weitere anzeigen“ in Schritten von 50; ab sechs
  Objekten ein Suchfeld über Titel und Angaben.
- **Daten:** `GET /api/aenderungen/{id}` (vorhanden, unverändert); kein neuer Endpunkt, nur lesend, kein
  Protokolleintrag.
- **Nicht enthalten:** Rückgängig aus dem Fenster heraus (bleibt in der Liste).

## 14 Geplante Zahlungen

### D-238 Geplante Zahlungen: Wiederholung, Vorschau, Zuordnung nach Namen
- **Anlass:** Auftrag vom 2026-11-21 im Sammelthread nach dem Vergleich mit KMyMoney und GnuCash: Zahlungen, die
  Kontor noch nicht aus der Vergangenheit ablesen kann (neuer Vertrag, einmalige Rechnung, seltene Beiträge), von
  Hand planen – einmalig oder mit Wiederholung –, in der Vorschau sehen und mit der Bankbuchung erledigen.
- **Grundlage:** Von Hand angelegte erwartete Zahlungen (Grund `manuell`, M20) gab es schon. Sie heißen in der
  Oberfläche jetzt „Geplant“; der Knopf auf „Was kommt noch?“ heißt „Zahlung planen…“ (`erwartet-neu` unverändert).
- **Wiederholung:** `POST`/`PATCH /api/erwartungen` nehmen `wiederholung` (`keine`, `monatlich`,
  `vierteljaehrlich`, `halbjaehrlich`, `jaehrlich`) und `wiederholung_bis` (Datum oder `null`); nur für Grund
  `manuell` (sonst 422 `wiederholung_nur_geplant`), ein Ende ohne Wiederholung ist 422 `wiederholung_fehlt`. Die
  Antwort trägt `wiederholung: {rhythmus, bis}` nur, wenn eine besteht – Einträge ohne Wiederholung sehen aus wie
  bisher (auch im Protokoll und in der Inhaltsprüfsumme der Sicherung).
- **Fortsetzung:** Wird eine solche Zahlung erfüllt (Buchung zugeordnet) oder als „erledigt“ geschlossen, entsteht in
  derselben Änderung die nächste: gleiche Angaben, Datum um den Rhythmus weiter (am Tag im Monat der ersten
  Fälligkeit, in kürzeren Monaten am Monatsletzten), gleiche Frist in Tagen. Keine Folge, wenn das Ende
  überschritten wäre oder es schon eine gibt. „Storniert“ und Löschen beenden die Wiederholung. Wird die Zahlung
  wieder offen (Zustand zurück, Zuordnung gelöst, Buchung gelöscht), entfällt ihre noch unberührte Folge.
  Rückgängig stellt beides gemeinsam wieder her.
- **Zuordnung:** Das Zeitfenster bleibt wie in erwartungen.md 5.1 (3 Tage vor dem Datum bis 45 Tage danach). Der
  Name passt, wenn ein aussagekräftiges Wort im Verwendungszweck oder Empfänger steht (wie D-232); automatisch
  zugeordnet wird die einzige Buchung mit gleichem Betrag, in der der Name steht – andere Buchungen mit gleichem
  Betrag stören nicht mehr. Der automatische Abgleich läuft weiter nur mit `mail_abgleich` (erwartungen.md).
- **Vorschau:** `GET /api/berichte/vorschau` enthält offene geplante Zahlungen samt Wiederholungen bis zum Ende des
  Zeitraums als Ereignisse mit `quelle = "geplant"`, `konto_id = null`, `rhythmus` (oder `einmalig`) und
  `erwartung_id`; schon fällige stehen am Folgetag. Sie zählen bei jeder Kontenwahl (geplante Zahlungen haben kein
  Konto) und werden nicht mit erkannten Serien abgeglichen: Wer eine schon erkannte Serie zusätzlich plant, sieht
  sie doppelt.
- **Datenmodell:** Tabelle `erwartung_wiederholung` (Rhythmus, Tag, Ende, Vorgänger) als Teil der Objektart
  `erwartung`; Datenbankschema 16, Sicherungsdatei Schemaversion 10 (ältere Sicherungen: ohne Wiederholungen).

## 15 Betrieb nur über HTTPS

### D-239 Betrieb nur über HTTPS: Tailscale Serve, Skript `kontor-https`
- **Anlass:** Auftrag vom 2026-11-21 im Sammelthread: künftig nur noch über HTTPS arbeiten, mit Tailscale; ein
  Installationsskript für Debian; die Testinstanz bleibt per Skript leicht startbar; gut dokumentiert.
- **Grundsatz bleibt:** Kontor spricht kein TLS (`sicherheit.md` 12, `betrieb.md` 2: `proxy_headers=False`). Am
  Anwendungsserver ändert sich nichts außer einer Warnung beim Start.
- **Weg:** Tailscale Serve auf dem Kontor-Server nimmt HTTPS mit dem Zertifikat des Tailnet-Namens entgegen und
  reicht an Kontor auf 127.0.0.1 weiter. Verworfen: eigener Proxy mit eigener Zertifizierungsstelle (Zertifikat
  auf jedem Gerät installieren) und Let's Encrypt über eine eigene Domain (mehr Einrichtung); Tailscale ist
  vorhanden. Nie Funnel (öffentliches Internet).
- **Skript** `kontor-https` (`betrieb/kontor-https.sh`, Ziel `/usr/local/bin/kontor-https`):
  `einrichten [--tailscale-installieren] [--name <name>] [--test-port <port>]`, `status`, `zurueck`. Reihenfolge
  beim Einrichten: prüfen → Freigabe einrichten (scheitert sie, bleibt Kontor unverändert) → Umgebungsdatei einmalig
  als `*.vor-https` sichern → `KONTOR_HOST=127.0.0.1`, `KONTOR_SITZUNG_COOKIE_SECURE=1`,
  `KONTOR_OEFFENTLICHE_URL=https://<name>` setzen → Neustart → Testinstanz ebenso (Adresse mit Port, Vorgabe
  8443; Umgebungsdatei bei Bedarf aus der Vorlage) → Abfrage über HTTPS. Wiederholbar; `zurueck` stellt genau diese
  drei Variablen aus der Sicherung wieder her und beendet die Freigaben. Die ausgelieferte `kontor.env` bleibt bei
  `0.0.0.0` (betrieb.md 3); umgestellt wird nur die installierte Datei.
- **`KONTOR_OEFFENTLICHE_URL` ist hinter dem Proxy Pflicht:** Kontor sieht nur `http`, der Browser meldet die
  `https`-Herkunft; die Herkunftsprüfung (`sicherheit.md` 4.6) lässt sie nur über die öffentliche Adresse zu. Fehlt
  sie bei `KONTOR_SITZUNG_COOKIE_SECURE=1`, warnt Kontor beim Start.
- **Netzbeschränkung:** `KONTOR_ERLAUBTE_NETZE` sieht hinter dem Proxy nur 127.0.0.1 und schützt nicht mehr; den
  Zugriff regelt das Tailnet (dokumentiert in HTTPS.md).
- **Testinstanz:** `kontor-test` bleibt die Bedienung. Steht in `kontor-test.env` eine `https://`-Adresse, schaltet
  `start`/`neu` die Freigabe (`tailscale serve --bg --https=<port>`) ein, `stop`/`loeschen` aus; `status` und die
  Ausgabe nennen die https-Adresse. Ohne die Zeile unverändert http.
- **Tailscale installieren** nur auf ausdrücklichen Wunsch (`--tailscale-installieren`, offizielles
  Installationsskript); die Anmeldung (`tailscale up`) bleibt ein Schritt von Hand, weil sie einen Browser braucht.

