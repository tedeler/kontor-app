# Widersprüche aus dem Gesamtlauf der Abnahme gegen die Anwendung (2026-11-22)

Vom Implementierungs-Thread als Text gemeldet (Stand kontor-tests `fca9a20`). Nur ein Test-Thread löst sie.

## W-027 M18: „Girokonto“ zweimal auf oberster Ebene

- Tests: `tests/app/m18/test_m18_inhalt_mail.py::test_mail_ansicht_nur_html_und_ohne_betreff`,
  `::test_aus_mail_mock_aus_feldern_gebaut`.
- `_konto_und_buchung` legt bei jedem Aufruf „Girokonto“ neu an; die Tests rufen es zweimal in derselben App
  auf. Seit M32 (`sammel3.md` 1, Kontonamen je Ebene eindeutig) antwortet die App beim zweiten Mal 409
  `konto_existiert`. Das ist das in Paket 4 genannte Risiko für Tests ohne Referenz.
- Vorschlag: vorhandenes Konto wiederverwenden oder eindeutige Namen.

## W-028 M2: `test_aendern` nimmt an, dass `ausdruck` beim Ändern der Bedingungen gleich bleibt

- Test: `tests/app/m2/test_m2_regeln_api.py::test_aendern` (`r3 == {**r2, "bedingungen": neue_bed, …}`).
- `kategorisierung.md` 8.1: `ausdruck` ist der kanonische Text der Bedingung, Regeln der bisherigen Form werden
  gleichbedeutend übersetzt; `PATCH` mit `bedingungen` ersetzt die Bedingung. Nach dem `PATCH` zeigt `ausdruck`
  also die neuen Bedingungen (z. B. `betrag <= -50.01`), nicht mehr den alten Text.
- Vorschlag: `ausdruck` beim Vergleich ausnehmen oder die Übersetzung der neuen Bedingungen erwarten.

## W-029 M3: Löschorakel – `ausdruck` nach dem Löschen eines Elternkontos

- Test: `tests/app/m3/test_m3_konto_loeschen.py::test_loeschen_gegen_orakel` (Fall: G1 mit Unterkonto G2
  löschen, Regel mit Bedingung `konto_id = G2`).
- Erwartet `ausdruck = 'konto == "G1:G2"'`; die App liefert `'konto == "G2"'`.
- `ausdruecke.md` 2.x: Konten stehen mit dem vollen Pfad, gespeichert wird der Bezug; nach einer Umbenennung zeigt
  der Ausdruck den neuen Namen. Nach dem Löschen von G1 steht G2 auf der obersten Ebene, sein voller Pfad ist
  „G2“. Das Orakel übernimmt den Text von vorher.
- Vorschlag: `ausdruck` im Orakel aus dem neuen Pfad bilden oder im Vergleich ausnehmen.

## W-030 M19: `empfaenger_geaendert` nach M32

- Test: `tests/app/m19/test_m19_zusammenfuehren.py::test_mit_loeschen_gegen_orakel`
  (`erg["empfaenger_geaendert"] == [x["emp"]]`).
- `sammel3.md` 2.1 (Z. 117): ohne Standardkategorie ist `empfaenger_geaendert` immer `[]`. Der Test wurde in
  E-307 auf „ohne Standardkategorie“ umgestellt, die Erwartung aber nicht.
- Vorschlag: `[]` erwarten.
