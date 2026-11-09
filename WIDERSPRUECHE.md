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

## W-004 M2-Test verlangt `SyncStatus` ohne das M6-Feld `pin_quelle`

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
- **Status:** offen.

Stand: Meilenstein 6, ein offener Widerspruch (W-004).
