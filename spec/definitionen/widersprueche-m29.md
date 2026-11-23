# Widersprüche aus dem Lauf der M29-Abnahmetests gegen die Anwendung (2026-11-22)

Vom Implementierungs-Thread als Text gemeldet. Nur ein Test-Thread löst sie (Test oder Spezifikation anpassen,
Entscheidung `E-…` anlegen).

## W-015 600 Zeilen des Diagnoseprotokolls

- Test: `tests/app/m29/test_m29_diagnose.py::test_hoechstens_600_zeilen_aelteste_zuerst`.
- Der Test misst die Zeilenzahl des ersten Abrufs und wiederholt den Abruf so oft, wie es bei gleicher Zeilenzahl
  je Abruf nötig wäre, um 600 zu überschreiten. Danach erwartet er genau 600 Zeilen.
- Spezifikation (`bankzugang.md`, Diagnoseprotokoll; E-265 Punkt 11): höchstens 600 Zeilen, älteste zuerst;
  Wortlaut und Aufbau der Zeilen sind frei. Gleiche Zeilenzahl je Abruf ist nicht festgelegt.
- Beobachtung: Der erste Abruf einer Instanz schreibt mehr Zeilen als die folgenden (einmalige Angaben, z. B. zu
  Bankparametern und Synchronisierung; etwa 66 gegenüber 37). Die Schleife endet unter 600, die Grenze wird nie
  erreicht.
- Vorschlag: wiederholen, bis 600 erreicht sind oder die Zeilenzahl nicht mehr wächst (mit Obergrenze), dann
  prüfen.

## W-016 Attrappe ändert die Benutzerparameter ohne neue Version

- Test: `tests/app/m29/test_m29_bankzugang_rest.py::test_konten_abrufen_behaelt_auswahl_und_ersetzt_die_liste`.
- Der Test schaltet mitten im Test die Attrappe auf `upd_ohne_konten` und erwartet beim nächsten Kontenabruf
  derselben App-Instanz fünf Konten ohne Namen und Inhaber.
- Spezifikation (`fints.md` 6): BPD und UPD werden bei der Dialoginitialisierung nur bei veralteter Version
  gesendet – das Verhalten einer FinTS-Bank.
- Beobachtung: Die Attrappe ändert den Inhalt der Benutzerparameter, meldet aber dieselbe UPD-Version. Ein Kunde,
  der die Version schon kennt, bekommt standardgemäß keine neuen UPD und ergänzt mit den bekannten Einträgen
  weiter (drei Konten mit Namen).
- Vorschlag: Die Attrappe erhöht die UPD-Version, sobald eine Betriebsart `upd_…` umgeschaltet wird (oder der
  Test nutzt je Zustand eine eigene Bank-Instanz, die eine neue Version meldet).
