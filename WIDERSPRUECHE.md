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

Stand: Meilenstein 9, keine offenen Widersprüche.
