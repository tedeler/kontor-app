# Widersprüche aus dem Lauf der M30/M31-Abnahmetests gegen die Anwendung (2026-11-22)

Vom Implementierungs-Thread als Text gemeldet. Nur ein Test-Thread löst sie (Test oder Spezifikation anpassen,
Entscheidung `E-…` anlegen).

## W-017 Erklärung des Lernmodells bei `grund = unbekannt`: bekannte Betragsmerkmale

- Test: `tests/app/m31/test_m31_lernmodell.py::test_erklaerung_unbekannt` (über `m31.erklaerung_soll`).
- Der Test erwartet bei `unbekannt` keine Merkmale mit Zählung: Jeder Eintrag außerhalb des Orakels muss
  `anzahl = 0` haben. Im Testbestand hat die neue Buchung denselben Betrag wie die Trainingsbuchung (−1,00 €),
  ihr Betragsmerkmal `b:-3` ist also bekannt (N(f) = 1).
- Spezifikation `lernmodell.md` 8.1: `merkmale` = „je bekanntem Merkmal f ∈ F ein Eintrag … `anzahl` = N(f)“;
  `unbekannt` heißt nur „kein Merkmal der Gruppen E/V“. Für bekannte Betragsmerkmale gilt die Regel weiter.
- Vorschlag: Das Orakel liefert bei `unbekannt` die bekannten Merkmale mit `anzahl` = N(f) (ohne beste
  Kategorie: `anzahl_kategorie` 0, `anzahl_vergleich` 0, `faktor_promille` null), oder der Test wählt einen
  anderen Betrag.

## W-018 Ähnliche Buchungen: Testdaten ohne eindeutig beste Buchung

- Test: `tests/app/m31/test_m31_lernmodell.py::test_erklaerung_mehrere_merkmale_exakt`.
- Der Test setzt voraus, dass genau eine Trainingsbuchung das höchste Gewicht hat (`… [1] < gewicht(beste)`).
  In seinen eigenen Daten haben zwei Buchungen von „Bäckerei Korn“ das Gewicht 5 (Empfänger 3 + zwei Wörter):
  „Brötchen Kartenzahlung Filiale“ und „Kuchen Kartenzahlung“ gegen „Kuchen Brötchen Kartenzahlung“. Die
  Vorbedingung scheitert, bevor die Antwort der App geprüft wird.
- Vorschlag: Testdaten so ändern, dass die beste Buchung eindeutig ist, oder bei Gleichstand nur „eine der
  besten zuerst“ prüfen (Reihenfolge bei Gleichstand ist in 8.1 nicht festgelegt).

## W-019 Mock-Lerndaten: 3000 Buchungen und der Anfangsbestand

- Test: `tests/app/m31/test_m31_lernmodell.py::test_lerndaten_laden_und_rueckgaengig` (`len(bs) == 3000`).
- Definition 3 (Mock-Lerndaten): „3000 synthetische Buchungen eines Girokontos (09/2022–10/2026) nach Mustern …“.
  Die Anwendung legt zusätzlich eine Eröffnungsbuchung „Anfangsbestand“ gegen ein Eigenkapitalkonto an (damit
  der Kontostand nicht negativ beginnt); das sind 3001 Buchungen. Die Definition nennt den Anfangsbestand nicht,
  schließt ihn aber auch nicht aus; er ist keine Buchung nach den Mustern.
- Vorschlag: 3000 Buchungen nach den Mustern plus höchstens eine Eröffnungsbuchung gegen Eigenkapital zulassen
  (z. B. `len(bs) in (3000, 3001)` und die zusätzliche nur gegen ein Konto der Art `eigenkapital`).

## W-020 Bankzugang: Elemente in „Erweitert“ als sofort sichtbar erwartet

- Tests: `tests/app/m29/test_m29_oberflaeche.py::test_felder_vorbelegt_mit_den_wirksamen_werten` (erwartet
  `bankzugang-diagnose-aktiv`, `bankzugang-diagnose-laden` sichtbar),
  `::test_abrufen_speichert_zuerst_und_spricht_die_bank_sonst_nicht_an[…]` (füllt `bankzugang-produkt_id`),
  `::test_diagnose_schalten_und_laden` (kreuzt `bankzugang-diagnose-aktiv` an).
- Definition 3, Abschnitt 6 (D-207): „Erweitert“ (`<details>`, eingeklappt) enthält Kunden-ID und Produkt-ID
  sowie das Diagnoseprotokoll; offen von Anfang an nur, wenn darin etwas fehlt oder läuft (Produkt-ID leer,
  Diagnose eingeschaltet). Ein Suchtreffer klappt „Erweitert“ auf.
- Die Elemente sind also im Dokument, aber eingeklappt nicht sichtbar. Vorschlag: `m29.bankzugang_oeffnen`
  (oder die Tests) klappen „Erweitert“ im Abschnitt auf, bevor sie diese Elemente bedienen; für die Prüfung des
  Anfangszustands nur die Elemente außerhalb von „Erweitert“ als sichtbar erwarten.

## W-021 Gruppierung: Vergleich Liste gegen Tupel in `_pruefe_tiefe`

- Tests: `tests/app/m31/test_m31_oberflaeche.py::test_leiste_und_tiefen`, `::test_tiefe_aus_der_adresse[…]`,
  `::test_zugeklappt_bleibt_beim_wechsel_der_tiefe`.
- `_pruefe_tiefe` vergleicht `sorted(m28.balken(seite))` mit `sorted((x["ebene"], s) …)`. `m28.balken` liefert
  aus `evaluate_all` Listen (`[["jahr", "2024"]]`), die Erwartung Tupel (`[("jahr", "2024")]`); Listen und Tupel
  sind in Python nie gleich. Die App zeichnet genau die erwarteten Balken (gemessen: `[["jahr", "2024"]]` für
  `tiefe=jahr` mit den Daten aus `m17.daten`).
- Vorschlag: in `_pruefe_tiefe` (oder in `m28.balken`) in Tupel umwandeln.

## Hinweis (kein Widerspruch): Tests, die Definition 4 nachziehen muss

- `tests/app/m31/test_m31_oberflaeche.py::test_route_lernmodell_ohne_navigationseintrag` erwartet über
  `m8.NAV_LINKS` den Link `navlink-statistik`; Definition 4 (D-221) entfernt `/statistik`.
- `tests/app/m31/test_m31_bestellnummer.py::test_mail_liste_angehaengt_stand_und_filter`: die Einträge von
  `angehaengt` tragen nach Definition 4 (D-236) zusätzlich `betrag`; das Schema verbietet bisher Zusatzfelder.
