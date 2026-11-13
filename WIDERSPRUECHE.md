# Widersprüche zwischen Tests und Spezifikation

Hier dokumentiert der Implementierungs-Thread Tests aus kontor-tests, die der
Spezifikation widersprechen (je Eintrag `W-xxx`: Testdatei/Testname, was der
Test erwartet, was die Spezifikation sagt mit Fundstelle, warum das
widersprüchlich ist). Gelöst werden Widersprüche nur von einem Test-Thread.

## W-001 Zufallsfolgen im Rückgängig-Test wählen aus einer leeren Kontenliste (erledigt)

- **Betroffene Tests:** `tests/app/m3/test_m3_rueckgaengig.py::test_zufaellige_folgen_rueckwaerts`
  und `::test_zufaelliges_rueckgaengig_gegen_orakel` (kontor-tests Commit `ae6eacf`).
- **Was der Test tut:** Die Hilfsfunktion `_ausfuehren` führt für die Operation
  `konto_weg` ohne Vorbedingung eine Zufallsauswahl aus der aktuellen Kontenliste aus.
  Sind alle Konten bereits gelöscht (z. B. Folge `konto_weg`, `konto_weg`, `konto_weg`
  nach dem Anlegen von nur zwei Konten), wählt Hypothesis aus einer leeren Liste und
  bricht mit `InvalidArgument: Cannot sample from a length-zero sequence` ab, bevor eine
  Anfrage an die Anwendung gesendet wird.
- **Was die Spezifikation sagt:** Das Löschen unbenutzter Konten ist erlaubt
  (`datenmodell.md` 2, `DELETE /api/konten/{id}`); ein Buch ohne Konten ist ein gültiger
  Zustand. Für die übrigen Operationen prüft `_ausfuehren` jeweils, ob die Auswahlliste
  nicht leer ist (`… and bs`, `… and tags`), nur bei `konto_weg` fehlt diese Prüfung.
- **Warum widersprüchlich:** Der Fehlschlag ist ein Fehler im Testablauf, nicht in der
  Anwendung; der Test bewertet in diesem Fall kein Verhalten der Anwendung. Er tritt im
  Standardprofil (Testlauf laut TESTS_AUSFUEHREN.md) nicht auf, wohl aber mit
  `HYPOTHESIS_PROFILE=gruendlich`. Vorschlag: `elif op == "konto_weg" and konten:`.

- **Status:** vom Test-Thread behoben (laut Koordination); erledigt.

## W-002 M1-Tests verlangen, dass das Szenario `beitragsaenderung` unbekannt ist (erledigt)

- **Betroffene Tests:** `tests/app/test_paket.py::test_ungueltige_konfiguration[mock_modus=True,mock_szenario=beitragsaenderung]`,
  `tests/app/test_plugins.py::test_unbekanntes_szenario[MockBank]` und `::test_unbekanntes_szenario[MockMail]`
  (kontor-tests Commit `ffe104c`).
- **Was die Tests erwarten:** `KontorConfig(mock_modus=True, mock_szenario="beitragsaenderung")` sowie
  `MockBankPlugin(…, "beitragsaenderung")` und `MockMailPlugin(…, "beitragsaenderung")` werfen
  `KonfigurationsFehler` (der Name diente in M1 als Beispiel für ein unbekanntes Szenario).
- **Was die Spezifikation sagt:** Ab M4 ist `beitragsaenderung` ein gültiges Szenario:
  `plugins.md` 8 („`KontorConfig.mock_szenario`, `KONTOR_MOCK_SZENARIO` und `MockBankPlugin` akzeptieren den Wert
  `"beitragsaenderung"`“, Mail-Mock „normal“), `python-api.md` 10.1 und 10.3, `vorlagen.md` 7, E-076. Die
  M4-Tests `tests/app/m4/test_m4_paket.py::test_szenario_beitragsaenderung_erlaubt`,
  `::test_mock_beitragsaenderung_liefert_anderen_betrag` und `::test_eingebauter_datensatz_mit_beitragsaenderung`
  verlangen genau das.
- **Warum widersprüchlich:** Beide Erwartungen schließen sich aus; keine Implementierung kann zugleich die M1-
  und die M4-Tests erfüllen. Die M1-Tests wurden mit M4 nicht angepasst (E-029 setzt voraus, dass M4 das
  Verhalten früherer Tests nicht ändert; hier wurde ein früher „unbekannter“ Wert zu einem bekannten).
  Vorschlag: in den drei M1-Tests einen weiterhin unbekannten Namen verwenden (z. B. `gibtsnicht`).
- **Umgang:** Umgesetzt ist die M4-Spezifikation; die drei M1-Tests schlugen fehl.
- **Status:** vom Test-Thread behoben (E-095, kontor-tests Commit `cc45364`: die M1-Fälle verwenden
  `gibtsnicht_m1`); geprüft beim M9-Lauf, die drei Tests sind grün. Erledigt.

## W-003 Tilgungsplan: entfallende Nullrate verletzt die Summeninvariante

- **Betroffener Test:** `tests/app/m5/test_m5_tilgungsplan.py::test_zufaellige_plaene_gleich_orakel`
  (kontor-tests Commit `dbe9a7c`), Hilfsfunktion `tests/hilfen/kredit_orakel.py::pruefe_plan_eigenschaften`.
- **Was der Test erwartet:** Für jeden Plan gilt `summe_tilgung + summe_sondertilgung = restschuld`. Hypothesis
  findet (deterministisch, Profil `standard` mit `derandomize`) die Parameter `restschuld = 1`,
  `stand_datum = 2020-01-01`, `sollzins = 0`, `zinsmethode = 30/360`, `rate = 1`,
  `erste_faelligkeit = 2020-01-02`, `sondertilgungen = [{datum: 2020-01-02, betrag: 1}]`.
  Anwendung und Orakel `kredit_orakel.plan` liefern übereinstimmend einen leeren Plan (`zeilen = []`,
  `summe_sondertilgung = 0`); der erste Vergleich `ist == soll` ist grün, erst die Eigenschaftsprüfung scheitert
  (`0 + 0 ≠ 1`).
- **Was die Spezifikation sagt:** `kredite.md` 3.5 Schritt 3: „Ist dabei `rate_i = 0` (nur möglich, wenn eine
  Sondertilgung genau bei Beginn alles getilgt hat), entfällt die Zeile.“ Zugleich 3.5 „Plan“: „es gilt
  `summe_tilgung + summe_sondertilgung = restschuld`“.
- **Warum widersprüchlich:** Die Klammer trifft nicht zu: `rate_i = 0` entsteht auch, wenn eine Sondertilgung die
  Restschuld *irgendwo* in der Periode vollständig tilgt und der Zins auf 0 Cent rundet (Sollzins 0 oder sehr kleine
  Restschuld). Entfällt die Zeile, entfällt mit ihr die Sondertilgung aus `summe_sondertilgung`, und die
  Summeninvariante ist verletzt. Beide Sätze der Spezifikation lassen sich in diesem Fall nicht zugleich erfüllen;
  das Orakel des Tests folgt Schritt 3 genauso wie die Anwendung. Vorschlag: Die Zeile nur entfallen lassen, wenn
  zusätzlich `sondertilgung = 0` ist (sonst eine Zeile mit `rate = 0`, `tilgung = 0` und der Sondertilgung
  behalten), oder die Invariante auf nicht leere Pläne bzw. „ohne entfallene Zeile“ einschränken.
- **Umgang:** Umgesetzt war zunächst `kredite.md` 3.5 Schritt 3 wörtlich (gleiches Ergebnis wie das Orakel des
  Tests).
- **Status:** vom Test-Thread behoben (E-111, kontor-tests Commit `3649524`/`8cece3c`: die Zeile mit
  `rate = 0` bleibt im Plan und wird nie einer Zahlung zugeordnet); umgesetzt, der Test ist grün. Erledigt.

## W-004 M2-Test verlangt `SyncStatus` ohne das M6-Feld `pin_quelle` (erledigt)

- **Betroffener Test:** `tests/app/m2/test_m2_sync.py::test_laeufe_und_status` (kontor-tests Commit `10855a3`).
- **Was der Test erwartet:** `GET /api/sync/status` ist exakt gleich einem Objekt mit genau den acht Schlüsseln
  `automatisch`, `intervall_minuten`, `laeuft`, `jetzt`, `naechster_lauf`, `letzter_lauf`,
  `offene_tan_anforderung`, `pin_vorhanden` (Vergleich mit `==`, zusätzliche Schlüssel lassen ihn scheitern).
- **Was die Spezifikation sagt:** `fints.md` 5: „`GET /api/sync/status`: zusätzliches Feld `pin_quelle`
  (`eingabe` | `systemd-creds`; im Schema optional, in M6-Tests Pflicht)“; `synchronisation.md` 18.1:
  „`SyncStatus` erhält das Feld `pin_quelle`.“ Der M6-Test `tests/app/m6/test_m6_pin_systemd.py::test_vorgabe_eingabe`
  verlangt das Feld auch bei der Vorgabe `eingabe` im Mock-Modus (`status(mock_api)["pin_quelle"] == "eingabe"`).
  E-029: neue Felder bestehender Antwortschemas sind im Schema optional, Tests früherer Meilensteine bleiben
  unverändert.
- **Warum widersprüchlich:** Dieselbe Instanz (Mock-Modus, Vorgabe `eingabe`) müsste das Feld für den M6-Test
  liefern und für den M2-Test weglassen. Der M2-Test prüft auf exakte Gleichheit und verträgt damit keine
  rückwärtskompatible Erweiterung nach E-029. Vorschlag: im M2-Test nur die acht Schlüssel vergleichen
  (z. B. `{k: st[k] for k in (...)}`) oder `pin_quelle` dort zulassen.
- **Umgang:** Umgesetzt ist die Spezifikation (`pin_quelle` immer vorhanden); der M2-Test schlägt fehl.
- **Status:** vom Test-Thread behoben (E-124, kontor-tests Commit `954bd3f`: Antwortobjekte der Testhilfe
  erlauben zusätzliche, im Schema optionale Felder); der M2-Test ist gegen den M6-Stand wieder grün
  (`-m m2`: 226/226). Erledigt.

## W-005 Nicht spezifizierter Endpunkt `POST /api/benachrichtigungen/test` (Spezifikationslücke, erledigt)

- **Art:** offene Spezifikationslücke, kein Widerspruch eines Tests.
- **Sachverhalt:** In M6 hat der Implementierungs-Thread (D-076) für die Weboberfläche „Anbindungen“ eine
  Test-Benachrichtigung über `POST /api/benachrichtigungen/test` ergänzt. `openapi.yaml` (2.7.0) führt diesen
  Pfad nicht; nach den Projektregeln darf die Anwendung keine REST-Endpunkte anbieten, die nicht im Vertrag stehen.
- **Betroffene Stellen:** `openapi.yaml` (fehlender Pfad), `benachrichtigungen.md` (keine Regel für eine
  Test-Zustellung), K 13 (Benachrichtigungen per Push, Einrichtung prüfbar).
- **Bitte an den Test-Thread:** Endpunkt spezifizieren (Pfad, Körper, Antwort, Fehlercodes, Verhalten je Plugin
  `keins`/`mock`/`ntfy`, ob die Test-Nachricht in der Benachrichtigungsliste erscheint, kein Protokolleintrag)
  oder ausdrücklich verwerfen; dann wird die Implementierung angepasst.
- **Umgang:** Der Endpunkt bleibt vorerst bestehen (bei eingeschalteter Anmeldung geschützt wie jeder andere
  Pfad, CSRF-Token nötig).
- **Status:** vom Test-Thread spezifiziert (E-138, `benachrichtigungen.md` 8, `openapi.yaml` 2.8.0, Schema
  `TestBenachrichtigung`). In M8 angepasst: Antwort `{plugin, zugestellt, gesendet, fehler}`; Mock ohne Aufruf von
  `senden` (`gesendet = false`); ntfy genau ein Versuch, Fehlschlag als 200 mit `zugestellt = false` und
  `fehler {code: benachrichtigung_fehler, meldung, status}` (vorher 409); Link auf `/einstellungen`, Schlüssel
  `test:<App-Uhr>`; 409 `kein_benachrichtigungs_plugin` mit `details = {}`. Die zehn Tests in
  `tests/app/m8/test_m8_testbenachrichtigung.py` sind grün. Erledigt.

## W-006 Reihenfolge der Panels im rechten Bereich (Panel nach dem Verschieben „innen“) (erledigt)

- **Betroffener Test:** `tests/app/m8/test_m8_panels_mobil.py::test_verschieben_per_drag_und_knopf`
  (kontor-tests Commit `d53f74b`).
- **Was der Test erwartet:** Nach dem Ziehen von `panel-kategorien` in den rechten Bereich gilt
  `liste.x < details.x < kategorien.x`, d. h. das verschobene Panel steht rechts vom Details-Panel, also am
  Fensterrand. Zugleich prüft er (wie spezifiziert) `position(kategorien) > position(details)`; die Meldung des
  Tests lautet „das verschobene Panel kommt nach innen (größte position)“.
- **Was die Spezifikation sagt:** `oberflaeche.md` 15.1: „Panels in einem Bereich stehen nebeneinander; Reihenfolge
  von außen (Fensterrand) nach innen (Liste) nach `position`.“ 15.2: „Das Panel kommt an die innerste Stelle
  (größte `position`) des Zielbereichs.“
- **Warum widersprüchlich:** Im rechten Bereich ist „außen“ der rechte Fensterrand und „innen“ die Liste links
  davon. Das Panel mit der größten `position` steht daher direkt neben der Liste, also *links* vom Details-Panel
  (`liste.x < kategorien.x < details.x`). Der Test erwartet die umgekehrte Anordnung, die nur entsteht, wenn beide
  Bereiche unabhängig von der Seite von links nach rechts nach `position` sortiert werden – das widerspricht 15.1
  für den rechten Bereich. Vorschlag: im Test `liste.x < kat.x < det.x` prüfen (oder 15.1 ändern).
- **Umgang:** Umgesetzt ist 15.1/15.2 (rechter Bereich in der Darstellung von innen nach außen nach aufsteigender
  `position`); der Test schlägt fehl.
- **Status:** vom Test-Thread behoben (kontor-tests Commit `174b292`: der Test erwartet `liste.x < kat.x < det.x`); grün. Erledigt.

## W-007 Umbuchung als zu kategorisierende Buchung (Drag and Drop, Wischen nach links) (erledigt)

- **Betroffene Tests:** `tests/app/m8/test_m8_split_dnd.py::test_buchung_auf_kategorie_ziehen` und
  `tests/app/m8/test_m8_panels_mobil.py::test_wischen_links_setzt_kategorie_und_rueckgaengig` (Commit `d53f74b`).
- **Was die Tests erwarten:** Die dritte Buchung der Girokonto-Liste (`r[2]`, nach `-datum`) wird per Drag and Drop
  auf „Kino“ bzw. per Wischen nach links auf „Mobilität“ kategorisiert; erwartet wird eine Änderung
  `kategorie_setzen` bzw. `kategorie_id` = Zielkategorie.
- **Was die Spezifikation sagt:** Im Datensatz `m8/oberflaeche.kmy` ist `r[2]` die Buchung „Sparrate“ vom
  15.12.2024 mit den Splits Girokonto −500,00 € und Tagesgeld +500,00 € – eine Umbuchung zwischen zwei
  Bestandskonten ohne Gegensplit. `datenmodell.md` 3.2: „Eine Buchung ist kategorisierbar, wenn sie genau einen
  Gegensplit hat“ (Gegensplits = Splits auf Nicht-Bestandskonten); „Nicht kategorisierbare Buchungen werden
  abgelehnt (422 `nicht_kategorisierbar`)“. `oberflaeche.md` 10/16.4: Ablegen bzw. Wischen „wirkt wie
  `mehrfach-kategorie`“, also `PUT /api/buchungen/{id}/kategorie`.
- **Warum widersprüchlich:** Die Oberfläche sendet die spezifizierte Anfrage; der Server lehnt sie für eine
  Umbuchung nach `datenmodell.md` 3.2 mit 422 ab (die Oberfläche zeigt die Fehlermeldung, 1 Nr. 8). Keine
  vertragsgemäße Implementierung kann die Umbuchung kategorisieren. Die übrigen Teile der Tests (Auswahl ziehen
  `r[4..6]`, Wischen auf `r[6]`, `r[7]`) funktionieren. Vorschlag: im Test eine kategorisierbare Buchung wählen
  (z. B. die erste Buchung mit `kategorie_id ≠ null`).
- **Umgang:** Spezifikation umgesetzt; beide Tests schlagen am ersten Schritt fehl.
- **Status:** vom Test-Thread geklärt (E-151, `oberflaeche.md` 10, kontor-tests `bf35445`): Tests wählen kategorisierbare Buchungen nach der Generator-Wahrheit; für Umbuchungen sendet die Oberfläche die Anfrage und zeigt die Ablehnung 422 `nicht_kategorisierbar` als Fehlermeldung (so bereits umgesetzt). Neue Tests grün. Erledigt.

## W-008 Protokollseite: IDs aus `data-testid` mit `slice(9)` gelesen (erledigt)

- **Betroffener Test:** `tests/app/m8/test_m8_bearbeiten.py::test_protokollseite` (Commit `d53f74b`).
- **Was der Test erwartet:** Er liest die angezeigten Änderungs-IDs mit
  `Number(e.getAttribute('data-testid').slice(9))` und vergleicht sie mit den IDs aus `GET /api/aenderungen`.
- **Was die Spezifikation sagt:** `oberflaeche.md` 13.9: Einträge `aenderung-<id>`. Das Präfix `aenderung-` hat zehn
  Zeichen; `"aenderung-2".slice(9)` ergibt `"-2"`, die Zahl also `-2`.
- **Warum widersprüchlich:** Für jede vertragsgemäße Oberfläche liefert der Test negative IDs (`[-2, -1]` statt
  `[2, 1]`); die Reihenfolge der Oberfläche stimmt mit der REST-Antwort überein. Vorschlag: `slice(10)`.
- **Umgang:** `aenderung-<id>` wie spezifiziert; der Test schlägt fehl.
- **Status:** vom Test-Thread behoben (kontor-tests `bf35445`); `test_protokollseite` ist grün. Erledigt.

## W-009 Kodierung von `weiter` bei der Weiterleitung des Servers zur Anmeldung (erledigt)

- **Betroffener Test:** `tests/app/m8/test_m8_anmeldung_a11y.py::test_anmelden_und_weiterleiten[desktop]` und
  `[handy]` (Commit `d53f74b`).
- **Was der Test erwartet:** Der direkte Aufruf von `/kredite` ohne Sitzung landet auf
  `/anmelden?weiter=%2Fkredite` (Schrägstrich kodiert).
- **Was die Spezifikation sagt:** Die Weiterleitung beim direkten Aufruf erzeugt der Server: `sicherheit.md` 3.2
  „303 mit `Location: /anmelden?weiter=<p>` … prozentkodiert nach RFC 3986 (jedes Zeichen außer
  `A–Z a–z 0–9 - . _ ~ /` kodiert)“ – der Schrägstrich bleibt also unkodiert. Der M7-Test
  `tests/app/m7/test_m7_anmeldung.py::test_oberflaeche_leitet_zur_anmeldung` prüft genau das
  (`quote(pfad, safe="/-._~")`). `oberflaeche.md` 19 („prozentkodiert“) betrifft die Weiterleitung der Oberfläche
  nach einer 401-Antwort; dort kodiert die Oberfläche auch `/` (`test_sitzung_beendet_fuehrt_zur_anmeldung`
  erwartet `%2Fkategorien` und ist grün).
- **Warum widersprüchlich:** Der Server kann nicht zugleich `/anmelden?weiter=/kredite` (M7, sicherheit.md 3.2) und
  `/anmelden?weiter=%2Fkredite` (M8-Test) liefern. Vorschlag: im M8-Test die Form nach `sicherheit.md` 3.2
  erwarten oder beide Formen zulassen.
- **Umgang:** `sicherheit.md` 3.2 umgesetzt (M7-Test grün); der M8-Test schlägt in beiden Layouts fehl. Nach der
  Anmeldung führt `weiter` korrekt nach `/kredite`.
- **Status:** vom Test-Thread behoben (Commit `174b292`: `oberflaeche.md` 19 kodiert wie `sicherheit.md` 3.2, beide Tests erwarten `weiter=/…`); die Oberfläche kodiert nach einer 401-Antwort ebenso. Grün. Erledigt.

Stand: Meilenstein 8 (getestet gegen kontor-tests `bf35445`); kein offener Eintrag.

## W-010 Abstimmungsdialog: Test prüft das Schließen ohne Warten (erledigt)

- **Test:** `tests/app/m8/test_m8_seiten.py::test_konten_anlegen_und_abstimmen` (Zeile mit
  `assert d.count() == 0 or d.is_hidden()`).
- **Erwartung des Tests:** Sobald der Server die Abstimmung gespeichert hat (Abfrage über REST), soll der Dialog
  im selben Augenblick geschlossen sein; geprüft wird einmalig ohne Warten.
- **Spezifikation:** `oberflaeche.md` (Abstimmungsdialog, Dialoge schließen nach erfolgreicher Operation) verlangt
  das Schließen nach dem Erfolg, nennt aber keinen Zeitpunkt vor dem Eintreffen der Antwort im Browser.
- **Warum widersprüchlich:** Der Server ist fertig, bevor seine Antwort im Browser ankommt; erst dann kann die
  Oberfläche den Erfolg erkennen und schließen. Unter Last (parallele Browsertests) liegt dazwischen messbar Zeit,
  der Test schlägt dann schwankend fehl (2 von 14 Läufen mit `-n 4`). Vorschlag: auf das Schließen warten
  (Playwright-`expect(...).to_be_hidden()` bzw. `to_have_count(0)`), wie an anderen Stellen der M8-Tests.
- **Erledigt:** kontor-tests `8ed01bc` (E-205) wartet auf das Schließen; 5 Läufe mit `-n 4` grün.

## W-011 M20: Inhaltsprüfsumme im Rundreise-Test ohne `postfach`

- **Test:** `tests/app/m20/test_m20_rest.py::test_sicherung_rundreise`, letzte Prüfung (Inhaltsprüfsumme
  unabhängig aus den Protokollformen).
- **Erwartung des Tests:** Prüfsumme über die Objektarten aus M9 sowie `dokument` und `erwartung` – ohne
  `postfach`, obwohl der Test ein Postfach anlegt.
- **Spezifikation:** `sicherung.md` (Objekt `postfach`, „genau dann, wenn die Sicherung mindestens ein Postfach
  enthält“), E-109: optionale Objektarten ab M5 stehen bei Vorhandensein in `anzahl` und Inhaltsprüfsumme.
- **Widerspruch:** Die Protokollformen stimmen überein; der Unterschied liegt allein in der fehlenden Objektart
  `postfach`. Dem Test-Thread am 2026-11-13 als Text gemeldet.

## W-012 M22: Ziehen an einem nicht sichtbaren Spaltentrenner

- **Test:** `tests/app/m22/test_m22_oberflaeche.py::test_jede_spalte_laesst_sich_ziehen` (Spalte `kategorie`,
  Zurückziehen um −30 px).
- **Erwartung des Tests:** Jeder Trenner lässt sich nacheinander verbreitern und verschmälern, ohne die Liste zu
  rollen.
- **Spezifikation:** `oberflaeche.md` (M22 1): ist die Summe der Breiten größer als die Liste, wird waagerecht
  geblättert; dass alle Trenner ohne Blättern sichtbar sind, ist nicht verlangt.
- **Widerspruch:** Bei 1280 px mit Detailpanel ist die Liste schon im Vorgaberaster waagerecht blätterbar; nach dem
  Verbreitern liegt der Trenner außerhalb des sichtbaren Bereichs, unter dem Größengriff des Detailpanels. Dem
  Test-Thread am 2026-11-13 als Text gemeldet.
