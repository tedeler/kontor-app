# Widersprüche zwischen Tests und Spezifikation

Hier dokumentiert der Implementierungs-Thread Tests aus kontor-tests, die der
Spezifikation widersprechen (je Eintrag `W-xxx`: Testdatei/Testname, was der
Test erwartet, was die Spezifikation sagt mit Fundstelle, warum das
widersprüchlich ist). Gelöst werden Widersprüche nur von einem Test-Thread.

## W-001 Zufallsfolgen im Rückgängig-Test wählen aus einer leeren Kontenliste

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

Stand: Meilenstein 3, getestet gegen kontor-tests Commit `ae6eacf`.
