# Nachtrag 1 zur Meilenstein-Definition „Kontor-Ausdrücke, Filter im Kontoblatt, Regeleditor und Regel-Tags“

Stand: 2026-11-19, **Entwurf zur Freigabe**, gehört zu `definition-2-ausdruecke-regeln.md`. Feature `regel-anwenden-fenster`, in kontor-app auf main (Entscheidung D-216). Beschreibt nur Verhalten.

## 1 Fenster „Regel anwenden“ (ersetzt den letzten Punkt in 9.3 der Definition)

Anwenden speichert eine neue oder geänderte Regel zuerst und öffnet dann `regel-anwenden-dialog`.

| `data-testid` | Element |
| --- | --- |
| `regel-anwenden-umfang` | „Zeitraum: …“ mit dem gewählten Zeitraum in Worten (12 Monate, dieses Jahr, Vorjahr, alle), dazu das Quellkonto, wenn eines gewählt ist |
| `regel-anwenden-kategorie` | Zahl der unkategorisierten Buchungen und Name der Kategorie; fehlt bei Regeln ohne Kategorie und wenn es keine solche Buchung gibt |
| `regel-anwenden-abweichende` | Ankreuzfeld „auch n Buchung(en) mit anderer Kategorie überschreiben“; nur wenn es solche Buchungen gibt |
| `regel-anwenden-tags` | Zahl der Buchungen, die Tags erhalten, und die Tags; nur bei Regeln mit Tags |
| `regel-anwenden-nichts` | Hinweis, dass die Regel im gewählten Umfang nichts ändert |
| `regel-anwenden-ok` | führt aus; verborgen, wenn sich nichts ändern würde |

- Das Fenster zeigt nie den Ausdruck des Zeitraums und nie leere Platzhalter wie „null“.
- Nach dem Anwenden meldet die Oberfläche die Zahl der geänderten Buchungen oder „Keine Buchung geändert.“

## 2 Tag-Dialog im Kontoblatt (ergänzt `oberflaeche.md` 9.2)

Der Dialog `tag-auswahl` öffnet sich wie bisher für eine oder mehrere Buchungen (Kontextmenü, Taste `t`, Stift in den Einzelheiten, `mehrfach-tags`).

- Neu ist `tag-auswahl-vorhanden` (`data-geladen` `ja`/`nein`): die Tags der gewählten Buchungen, nach Namen sortiert. Bei mehreren Buchungen steht je Tag „(alle)“ oder „(n von m)“. Ohne Tags steht „Noch keine Tags.“
- Je Tag gibt es den Knopf `tag-auswahl-weg-<tag-id>`. Er entfernt den Tag von allen gewählten Buchungen. Das ist eine Änderung `mehrfach_tags` und ein Rückgängig-Schritt. Der Dialog bleibt danach offen und zeigt den neuen Stand.
- `tag-auswahl-name`, `tag-auswahl-hinzufuegen` und `tag-auswahl-entfernen` verhalten sich unverändert: Hinzufügen legt einen unbekannten Tag zuerst an; Entfernen eines unbekannten Namens ist ein Fehler im Dialog ohne Anfrage; beide schließen den Dialog nach Erfolg.
- Sind mehr als 50 der gewählten Buchungen in der Liste noch nicht geladen, zeigt der Dialog die Tags der übrigen nicht und sagt das. Hinzufügen und Entfernen wirken trotzdem auf alle gewählten Buchungen.
