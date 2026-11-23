# Oberfläche (Single-Page-Anwendung) – Meilenstein 8, 11, 12, 13, 15 bis 22

Verbindlich für Implementierung und Tests. Umsetzung von K 5
(Benutzeroberfläche, native Bedienung), K 6 (TAN-Seite mit QR-Code,
„QR-Code speichern“/„Teilen“), K 14 (mobile Ansicht) und T 19 (Oberfläche,
Desktop und mobil). Die Oberfläche bedient ausschließlich die
REST-Schnittstelle aus `openapi.yaml` (2.8.0); M8 führt außer
`POST /api/benachrichtigungen/test` (`benachrichtigungen.md` 8, E-138)
keinen Endpunkt ein.
Abkürzungen: K = `konzept.md`, T = `testkonzept.md`, E = `entscheidungen.md`.

Tests sprechen die Oberfläche **nur** über die hier festgelegten Merkmale an:
`data-testid`-Werte (im Folgenden kurz „`x`“ für `[data-testid="x"]`),
ARIA-Rollen und -Attribute, die genannten `data-*`-Attribute, Routen,
Tastaturkürzel und Gesten. Aussehen, Texte (außer den genannten), Aufbau des
DOM, Framework und interner Code sind frei. Zusätzliche Elemente sind
erlaubt. Ein `data-testid` kommt auf einer Seite höchstens einmal vor
(Bezeichner mit `<id>` je Objekt einmal).

## 1. Grundsätze

1. **Single-Page-Anwendung:** Navigation innerhalb der Oberfläche lädt die
   Seite nicht neu (History API, `pushState`); Zurück/Vor des Browsers
   funktioniert. Jede Route aus 3 ist zusätzlich als direkter Aufruf
   (Lesezeichen, Link aus einer Push-Nachricht, Neuladen) erreichbar.
2. **Nur REST:** Alle Daten kommen aus `/api/…` (`fetch`,
   `credentials: "same-origin"`); jede Wirkung entsteht durch die dort
   spezifizierten Operationen. Die Oberfläche hält keinen eigenen
   fachlichen Zustand, der von der REST-Schnittstelle abweichen kann: Nach
   jeder eigenen Änderung zeigt sie den Zustand, den die REST-Antworten
   ergeben (neu laden ist erlaubt).
3. **Keine fremden Quellen:** Skripte, Stile, Schriften, Bilder und Symbole
   kommen von derselben Herkunft (kein CDN, keine externen Schriften, keine
   Analysedienste). Der Browser stellt keine Anfrage an einen anderen Host.
4. **CSP-konform** (`sicherheit.md` 6, 7.2): kein Inline-Skript, keine
   `on…`-Attribute, kein `javascript:`-URL, kein `eval`. Im Browser darf
   keine Verletzung der Content-Security-Policy auftreten.
5. **Texte aus dem Buchbestand** (Namen, Verwendungszwecke, Memos, Tags,
   Meldungen des Servers) werden immer als Text gesetzt (`textContent`,
   Attributwerte), nie als HTML. Ein Verwendungszweck wie
   `<img src=x> & "Café"` erscheint wörtlich.
6. **Sprache:** Deutsch, `<html lang="de">`.
7. **Keine Laufzeitfehler:** Unbehandelte Ausnahmen (`window.onerror`,
   unbehandelte Promise-Ablehnungen) dürfen in keinem Ablauf auftreten.
8. **Fehlerantworten** der REST-Schnittstelle (4xx) werden als Meldung
   (6.3) mit der `meldung` des Servers angezeigt; der angezeigte Zustand
   bleibt der des Servers (keine „optimistische“ Änderung bleibt stehen).

## 2. Auslieferung durch den Server

- Für jede Route aus 3 (auch mit Abfrage, z. B. `/konten/5?von=2024-01-01`)
  liefert `GET` 200 `text/html; charset=utf-8` mit derselben Hülle
  (`sicherheit.md` 7.2: ohne Texte aus dem Buchbestand, `Cache-Control:
  no-store`); bei eingeschalteter Anmeldung ohne Sitzung 303 nach
  `/anmelden?weiter=…` (`sicherheit.md` 3.2).
- Die Hülle enthält:
  - `<meta name="viewport" content="width=device-width, initial-scale=1">`
    (ohne `maximum-scale`, ohne `user-scalable=no`),
  - `<meta name="color-scheme" content="light dark">`,
  - `<link rel="manifest" href="/oeffentlich/manifest.webmanifest">`,
  - Skripte nur als `<script src="…">` derselben Herkunft (z. B.
    `type="module"`),
  - im Mock-Modus den Mock-Hinweis nach `plugins.md` 6 (`id="mock-hinweis"`,
    Text enthält „Mock-Modus“, ohne Skript sichtbar), zusätzlich mit
    `data-testid="mock-hinweis"`; im Echtmodus nicht die Zeichenkette
    `mock-hinweis`.
- Statische Dateien der Oberfläche (Skripte, Stile, Symbole, Manifest)
  liegen unter `/oeffentlich/` (`sicherheit.md` 3.1, 7.3), der Service
  Worker unter `/sw.js` (18).
- `/anmelden` (`sicherheit.md` 3.4) verlinkt ebenfalls das Manifest.

## 3. Routen

| Route | Seite (`seite-<name>`) | Titel (`<h1>`, `document.title` = Titel + „ – Kontor“) | Navigation |
| --- | --- | --- | --- |
| `/` | `seite-uebersicht` | Finanzübersicht | `nav-uebersicht` |
| `/konten` | `seite-konten` | Konten | `nav-konten` |
| `/konten/<id>` | `seite-konto` | Name des Kontos | `nav-konten` |
| `/kategorien` | `seite-kategorien` | Kategorien | `nav-kategorien` |
| `/wiederkehrend` | `seite-wiederkehrend` | Wiederkehrende Buchungen | `nav-wiederkehrend` |
| `/kredite` | `seite-kredite` | Kredite | `nav-kredite` |
| `/kredite/<id>` | `seite-kredit` | Name des Kredits | `nav-kredite` |
| `/berichte` | `seite-berichte` | Berichte | `nav-berichte` |
| `/import` | `seite-import` | Import | `nav-import` |
| `/einstellungen` | `seite-einstellungen` | Einstellungen | `nav-einstellungen` |
| `/protokoll` | `seite-protokoll` | Änderungsprotokoll | `nav-protokoll` |
| `/empfaenger` | `seite-empfaenger` | Empfänger | `nav-empfaenger` |
| `/regeln` | `seite-regeln` | Regeln | `nav-regeln` |
| `/vorlagen` | `seite-vorlagen` | Split-Vorlagen | `nav-vorlagen` |
| `/dubletten` | `seite-dubletten` | Dubletten | `nav-dubletten` |
| `/sync` | `seite-sync` | Synchronisation | `nav-sync` |
| `/benachrichtigungen` | `seite-benachrichtigungen` | Benachrichtigungen | – (Glocke 4.2) |
| `/suche?q=<text>` | `seite-suche` | Suche | – (Suchfeld 4.2) |
| `/tan/<id>` | `seite-tan` | TAN-Freigabe | – (Link aus Benachrichtigung) |
| `/mail/postfaecher/<id>` | `seite-postfach` | Adresse des Postfachs | `nav-einstellungen` |

- Die ersten acht Navigationseinträge entsprechen K 5 in dieser
  Reihenfolge; danach folgen `nav-protokoll`, `nav-empfaenger`,
  `nav-regeln`, `nav-vorlagen`, `nav-dubletten`, `nav-sync`.
- Nicht existierende Objekte (`/konten/999999`) und unbekannte Pfade
  innerhalb der Oberfläche zeigen `seite-nicht-gefunden` (h1 „Nicht
  gefunden“); der Server darf für unbekannte Pfade stattdessen 404 liefern
  (`sicherheit.md` 7.2).
- Jede Seite trägt `data-geladen="ja"`, sobald ihre Daten geladen und
  dargestellt sind, und `data-geladen="nein"`, solange sie (neu) lädt. Das
  Wurzelelement `app` trägt `data-bereit="ja"`, sobald die erste Seite
  dargestellt ist, und `data-layout="desktop"` bzw. `data-layout="mobil"`
  (16). Tests warten auf diese Zustände, nie auf feste Zeiten.

## 4. Grundgerüst

### 4.1 Bereiche

- `app-kopf` (`<header>`, Rolle `banner`), `navigation` (`<nav>`,
  `aria-label="Hauptnavigation"`), `hauptbereich` (`<main>`, genau eines
  je Seite). Jede Seite hat genau ein `<h1>`.
- Navigationseinträge `nav-<ziel>` sind Links (`<a href="/…">`); der
  Eintrag der aktuellen Seite trägt `aria-current="page"`, alle anderen
  nicht.

### 4.2 Kopfzeile (`app-kopf`)

| Element | Zweck |
| --- | --- |
| `mock-hinweis` | Mock-Hinweis (2, im Mock-Modus) – auf jeder Seite, in beiden Layouts ohne Interaktion sichtbar und innerhalb des sichtbaren Bereichs (fest oder klebend oben), nie verdeckt oder einklappbar |
| `menue-knopf` | nur mobil sichtbar (16): blendet die Navigation ein, `aria-expanded`, `aria-controls` |
| `suche-feld` | Suchfeld (Rolle `searchbox`); Enter → `/suche?q=<text>` |
| `sync-starten` | `POST /api/sync` (15.4) |
| `benachrichtigungen-knopf` | Link nach `/benachrichtigungen`; `benachrichtigungen-anzahl` mit `data-anzahl` = Zahl der ungelesenen (`GET /api/benachrichtigungen?gelesen=false`), aktualisiert nach jeder Aktion und mindestens alle 60 s |
| `rueckgaengig-knopf`, `wiederholen-knopf` | wie Strg+Z bzw. Strg+Umschalt+Z (11); `disabled`, wenn der jeweilige Stapel leer ist |
| `befehlspalette-knopf` | öffnet die Befehlspalette (12.3) |

### 4.3 Meldungen

- Bereich `meldungen` mit `role="status"` und `aria-live="polite"`.
  Jede Meldung ist ein Element `meldung` mit `data-art` = `erfolg`,
  `fehler` oder `hinweis`; Fehlermeldungen tragen zusätzlich
  `role="alert"`. Eine Meldung bleibt mindestens 5 s sichtbar oder bis
  `meldung-schliessen`; es sind höchstens drei gleichzeitig sichtbar.
- Erfolgsmeldungen eigener Änderungen enthalten `meldung-rueckgaengig`
  (wie Strg+Z, 11).
- Fehler der REST-Schnittstelle: `data-art="fehler"`, Text enthält die
  `meldung` der Fehlerantwort.

## 5. Darstellung von Werten

- **Beträge:** Text nach `Intl.NumberFormat("de-DE", {style: "currency",
  currency: "EUR"})`, also Vorzeichen `-` (U+002D), Tausenderpunkt,
  Dezimalkomma, zwei Nachkommastellen, geschütztes Leerzeichen (U+00A0),
  `€` – z. B. `-1.234,56 €`, `0,00 €`. Jedes Element, das einen Betrag
  zeigt, trägt `data-betrag` = Betrag in Cent (Ganzzahl, Dezimalziffern
  mit optionalem `-`).
- **Betragseingaben:** deutsche Schreibweise `[-]Ziffern[,Ziffern]` mit
  höchstens zwei Nachkommastellen; Tausenderpunkte (`1.234,56`) sind
  erlaubt; Leerraum am Rand wird ignoriert. Anderes ist ungültig (Feld
  `aria-invalid="true"`, keine Anfrage).
- **Datum:** Text `TT.MM.JJJJ` (zweistellig mit führender Null);
  `data-datum` = ISO `JJJJ-MM-TT`. Zeitpunkte: `TT.MM.JJJJ HH:MM` in der
  Zeitzone des Browsers, `data-zeitpunkt` = Wert der REST-Antwort.
- **Status:** `importiert` → „Importiert“, `vorlaeufig` → „Vorläufig“,
  `bestaetigt` → „Bestätigt“, `abgeglichen` → „Abgeglichen“;
  `data-status` = Wert der REST-Antwort.
- **Kategorien** werden mit ihrem Pfad angezeigt, Ebenen getrennt durch
  ` › ` (U+203A mit Leerzeichen), z. B. „Wohnen › Miete“.

## 6. Finanzübersicht (`/`)

- Tabelle `uebersicht-tabelle` aus `GET /api/kontenuebersicht`: je
  Bestandskonto (Art `girokonto`, `sparkonto`, `kreditkonto`) eine Zeile
  `uebersicht-konto-<konto_id>` mit Zellen `[data-feld="name"]` und
  `[data-feld="saldo"]` (`data-betrag` = `saldo_gesamt`). Unterkonten
  folgen ihrem Elternkonto (Baumreihenfolge, Geschwister nach Name mit
  `localeCompare(…, "de")`) und tragen `aria-level` (Wurzel = 1).
- Geschlossene Konten sind ausgeblendet; das Kontrollkästchen
  `uebersicht-geschlossene` blendet sie ein (`data-geschlossen="ja"`).
- `uebersicht-summe` mit `data-betrag` = `summe_bestand`.
- Ab M11 darunter einklappbar die Kategorien (22.1).
- Klick oder Enter auf eine Zeile → `/konten/<id>`; Rechtsklick bzw. lange
  Berührung → Kontextmenü für Konten (8.2).

## 7. Kontoansicht (`/konten/<id>`)

### 7.1 Filter

- `filter-umschalten` (`aria-expanded`) blendet die Filterleiste
  `filter-leiste` ein und aus (ab M12 in beiden Layouts anfangs
  ausgeblendet, 23.1; bis M11: Desktop anfangs eingeblendet, mobil
  anfangs ausgeblendet). `filter-anzahl` trägt `data-anzahl` = Zahl der
  gesetzten Filter.
- Felder und Abbildung auf `GET /api/buchungen` (immer zusätzlich
  `konto_id=<id>`):

| Element | Art | Parameter |
| --- | --- | --- |
| `filter-von`, `filter-bis` | `<input type="date">` | `von`, `bis` |
| `filter-betrag-min`, `filter-betrag-max` | Texteingabe, Euro (5) | `betrag_min`, `betrag_max` (Cent) |
| `filter-empfaenger` | `<select>`: leer, `ohne` („ohne Empfänger“), je Empfänger dessen ID | `empfaenger_id` bzw. `ohne_empfaenger=true` |
| `filter-verwendungszweck` | Texteingabe | `verwendungszweck` |
| `filter-freitext` | Texteingabe | `suche` |
| `filter-kategorie` | `<select>`: leer, je Kategorie (Art `aufwand`/`ertrag`) deren ID, Beschriftung = Pfad | `kategorie_id` |
| `filter-unterkategorien` | Kontrollkästchen | `unterkategorien=true` |
| `filter-tag` | `<select>`: leer, je Tag dessen ID | `tag_id` |
| `filter-status-<status>` | Kontrollkästchen je Status | `status` (mehrfach) |
| `filter-zuruecksetzen` | Knopf | entfernt alle Filter |

- Wirksam wird ein Filter bei `change` (Auswahlfelder, Datum,
  Kontrollkästchen) bzw. bei Enter oder Verlassen des Feldes
  (Texteingaben). Leere Felder bedeuten „kein Filter“.
- **URL:** Die gesetzten Filter und die Sortierung stehen als Abfrage mit
  genau den REST-Parameternamen in der URL (`replaceState`), z. B.
  `/konten/5?von=2024-03-01&bis=2024-03-31&status=bestaetigt`. Ein direkter
  Aufruf mit Abfrage setzt die Felder entsprechend. Ein Filterwechsel
  hebt die Auswahl auf (7.4).

### 7.2 Buchungsliste

- `buchungsliste` mit `role="grid"` und `aria-multiselectable="true"`;
  Kopfzeile mit Spaltenköpfen (`role="columnheader"`). Sortierbare
  Spalten `spalte-datum`, `spalte-empfaenger`, `spalte-betrag` (Knöpfe
  im Spaltenkopf; der Spaltenkopf trägt `aria-sort` = `ascending`,
  `descending` oder `none`). Vorgabe: `sortierung=-datum`. Klick auf die
  aktive Spalte kehrt die Richtung um, Klick auf eine andere Spalte sortiert
  sie aufsteigend.
- Die Liste zeigt genau die Einträge von `GET /api/buchungen` mit
  `konto_id=<id>`, den Filtern, der Sortierung und `pro_seite=200` in
  derselben Reihenfolge. `buchungsliste-mehr` lädt die nächste Seite und
  hängt sie an; es ist sichtbar, solange weniger als `gesamt` Einträge
  geladen sind.
- `buchungsliste-anzahl` mit `data-anzahl` = `gesamt`;
  `buchungsliste-summe` mit `data-betrag` = `summe`;
  `buchungsliste-leer` sichtbar genau bei `gesamt = 0`.
- Zeile `buchung-<id>` (`role="row"`, `aria-selected="true|false"`,
  `data-status`, `data-vorschlag="ja|nein"`) mit Zellen
  (`role="gridcell"`, `data-feld`):

| `data-feld` | Inhalt |
| --- | --- |
| `datum` | Datum (5), `data-datum` |
| `empfaenger` | Name oder leer, `data-empfaenger-id` (leer ohne Empfänger) |
| `verwendungszweck` | Verwendungszweck |
| `kategorie` | `data-kategorie-id` = `kategorie_id` oder leer; Text: Pfad der Kategorie; ohne `kategorie_id` (`datenmodell.md` 3.2) bei mehreren Gegensplits „Gesplittet“, ohne Gegensplit (Umbuchung zwischen Bestandskonten) „Umbuchung“, sonst der Pfad des einen Gegensplit-Kontos (z. B. „Korrekturen“) |
| `tags` | Tag-Namen, je Tag ein Element `tag` mit `data-tag-id` |
| `status` | Status (5) |
| `betrag` | `betrag` der Listenantwort (`datenmodell.md` 3.3, aus Sicht dieses Kontos), `data-betrag` |

- **Vorschläge** (K 7): Zeilen mit `vorschlag ≠ null` tragen
  `data-vorschlag="ja"`; die Kategoriezelle enthält zusätzlich
  `vorschlag-marke` und die Knöpfe `vorschlag-annehmen-<id>` und
  `vorschlag-ablehnen-<id>` (`POST /api/buchungen/{id}/vorschlag`). Ein
  Klick auf diese Knöpfe ändert die Auswahl nicht.
- Ein Konto mit `ist_kategorie = true` lässt sich ebenso öffnen (alle
  Buchungen dieser Kategorie). Ab M11 mit denselben Funktionen und einer
  Spalte für das Bestandskonto (22.2).

### 7.3 Seitenpanels der Kontoansicht

- `panel-kategorien`: Kategorienbaum (13.1) als Ablageziel für Drag and
  Drop (10).
- `panel-details`: Einzelheiten der fokussierten Buchung (7.4): alle
  Splits als `details-split-<split_id>` mit Konto (Pfad), `data-betrag`
  und Memo, dazu Tags und Herkunftskennungen.
- Anordnung, Größe und Einklappen: 15.

### 7.4 Auswahl und Fokus (Mehrfachauswahl wie im Dateimanager)

Die Liste hat einen **Fokus** (eine Zeile, `tabindex="0"`, alle anderen
`-1`), einen **Anker** und eine **Auswahl** (Menge von Zeilen,
`aria-selected`). „Bereich(a, b)“ sind alle geladenen Zeilen zwischen a und
b einschließlich, in Anzeigereihenfolge.

| Eingabe | Auswahl | Anker | Fokus |
| --- | --- | --- | --- |
| Klick | {Zeile} | Zeile | Zeile |
| Strg+Klick (macOS ⌘+Klick) | Zeile umschalten (hinzu bzw. weg) | Zeile | Zeile |
| Umschalt+Klick | Bereich(Anker, Zeile); ohne Anker wie Klick | unverändert | Zeile |
| Strg+Umschalt+Klick | bisherige Auswahl ∪ Bereich(Anker, Zeile) | unverändert | Zeile |
| Pfeil ab/auf, Pos1, Ende | {neue Fokuszeile} | neue Fokuszeile | nächste/vorige/erste/letzte Zeile |
| Umschalt+Pfeil ab/auf | Bereich(Anker, neue Fokuszeile) | unverändert | nächste/vorige |
| Strg+Pfeil ab/auf | unverändert | unverändert | nächste/vorige |
| Leertaste | Fokuszeile umschalten | Fokuszeile | unverändert |
| Strg+A (Fokus in der Liste) | alle geladenen Zeilen | unverändert | unverändert |
| Esc (ohne offenes Menü/Dialog) | leer | unverändert | unverändert |

- `auswahl-anzahl` mit `data-anzahl` = Zahl der ausgewählten Zeilen.
- Nach dem Neuladen der Liste nach einer Änderung bleiben Zeilen, die noch
  vorhanden sind, ausgewählt; Fokus und Anker bleiben, wenn ihre Zeile
  noch vorhanden ist.
- Mobil: 16.3.

### 7.5 Mehrfachbearbeitung (K 5)

`mehrfach-leiste` ist genau dann sichtbar, wenn mindestens eine Zeile
ausgewählt ist. Sie enthält:

| Element | Wirkung auf die Auswahl `A` (IDs aufsteigend) |
| --- | --- |
| `mehrfach-kategorie` | Kategorie-Auswahl (9.1); dann bei `|A| = 1` `PUT /api/buchungen/{id}/kategorie`, sonst `POST /api/buchungen/mehrfach/kategorie` mit `buchung_ids = A` |
| `mehrfach-tags` | Tag-Auswahl (9.2): `POST /api/buchungen/mehrfach/tags` mit `buchung_ids = A` und `hinzufuegen` bzw. `entfernen` |
| `mehrfach-vorschlag-annehmen`, `mehrfach-vorschlag-ablehnen` | `POST /api/buchungen/mehrfach/vorschlag` für die Buchungen aus `A` mit Vorschlag; deaktiviert, wenn keine einen Vorschlag hat |
| `mehrfach-loeschen` | Rückfrage (9.5), dann `DELETE /api/buchungen/{id}` je Buchung (aufsteigend); ab M15 bei `\|A\| > 1` eine Anfrage `POST /api/buchungen/mehrfach/loeschen` (25.2) |
| `auswahl-aufheben` | leert die Auswahl |

Schlägt eine Anfrage fehl (z. B. 409 `buchung_gesperrt`), zeigt die
Oberfläche den Fehler; die Mehrfach-Endpunkte sind atomar, die Liste zeigt
danach den Stand des Servers.

### 7.6 Inline-Bearbeitung (K 5)

- Bearbeitbar sind die Zellen `datum`, `verwendungszweck` und `kategorie`
  (nur bei genau einem Gegensplit). Start: Doppelklick auf die Zelle oder
  F2 auf der Fokuszeile (bearbeitet `verwendungszweck`).
- Der Editor ist ein Element `inline-editor` mit `data-feld` in der Zelle:
  `<input type="date">` für `datum`, `<input type="text">` (Text komplett
  markiert) für `verwendungszweck`, `<select>` mit allen Kategorien (Wert
  = ID, Beschriftung = Pfad) für `kategorie`. Er erhält den Fokus.
- **Übernehmen:** Enter, Tab oder Verlassen des Editors; beim `<select>`
  zusätzlich jede Auswahländerung. **Abbrechen:** Esc (kein Request, alter
  Wert).
- Anfragen: `datum`, `verwendungszweck` → `PATCH /api/buchungen/{id}`
  mit genau diesem Feld; `kategorie` → `PUT /api/buchungen/{id}/kategorie`.
  Unveränderter Wert → keine Anfrage. Fehler → Meldung, Zelle zeigt wieder
  den Stand des Servers.
- Gesperrte Buchungen (`abgestimmt` oder Status `abgeglichen`): Die
  Oberfläche darf den Editor gar nicht erst öffnen; öffnet sie ihn, meldet
  sie den Fehler des Servers. In beiden Fällen ändert sich nichts.

## 8. Kontextmenüs (K 5)

### 8.1 Allgemein

- Rechtsklick (Desktop), lange Berührung (mobil, 16.4), Umschalt+F10 oder
  die Kontextmenü-Taste (auf dem fokussierten Element) öffnen ein Menü
  `kontextmenue` (`role="menu"`) mit Einträgen `role="menuitem"`;
  nicht anwendbare Einträge tragen `aria-disabled="true"` und lösen nichts
  aus. Das Browsermenü erscheint dabei nicht (außer in Texteingaben).
- Es ist höchstens ein Menü offen. Beim Öffnen erhält der erste aktive
  Eintrag den Fokus; Pfeil ab/auf wechselt zwischen aktiven Einträgen
  (umlaufend), Enter/Leertaste oder Klick führt aus und schließt; Esc oder
  ein Klick außerhalb schließt ohne Wirkung und gibt den Fokus an das
  auslösende Element zurück. Das Menü liegt vollständig im sichtbaren
  Bereich.
- **Auswahl:** Rechtsklick auf eine Buchung außerhalb der Auswahl setzt
  die Auswahl zuerst auf diese Zeile (wie Klick); innerhalb der Auswahl
  bleibt sie. Das Menü wirkt auf die Auswahl.

### 8.2 Einträge

Buchungen (Zeilen `buchung-<id>`, auch Suchtreffer):

| Eintrag | aktiv, wenn | Wirkung |
| --- | --- | --- |
| `km-kategorie` „Kategorie setzen…“ | immer | wie `mehrfach-kategorie` (7.5) |
| `km-tags` „Tags…“ | immer | wie `mehrfach-tags` |
| `km-splitten` „Splitten…“ | genau eine Buchung | Split-Dialog (9.3) |
| `km-dublette` „Als Dublette markieren…“ | genau eine Buchung, die in einem offenen Dublettenverdacht (`GET /api/dubletten?status=offen`) als `buchung_id` oder in `kandidat_ids` vorkommt | Dubletten-Dialog (9.6) |
| `km-vorschlag-annehmen`, `km-vorschlag-ablehnen` | mindestens eine Buchung mit Vorschlag | wie 7.5 |
| `km-bearbeiten` „Verwendungszweck bearbeiten“ | genau eine Buchung | Inline-Editor (7.6) |
| `km-loeschen` „Löschen…“ | immer | wie `mehrfach-loeschen` |

Ab M12 zusätzlich `km-status` und `km-mehrfach` (23.3), ab M17
`km-gegenbuchung` direkt nach `km-mehrfach` (27.2).

Konten und Kategorien (`uebersicht-konto-<id>`, `kontenbaum-konto-<id>`,
`kategorie-<id>`):

| Eintrag | Wirkung |
| --- | --- |
| `km-konto-oeffnen` | `/konten/<id>` |
| `km-konto-umbenennen` | Eingabe `umbenennen-eingabe` an Ort und Stelle; Enter → `PATCH /api/konten/{id}` `{name}`, Esc bricht ab |
| `km-konto-unterkonto` | Dialog `konto-dialog` mit `konto-name`, `konto-speichern` → `POST /api/konten` mit gleicher `art` und `eltern_id = id` |
| `km-konto-verschieben` „Verschieben nach…“ | Ziel-Auswahl (9.4) → `PATCH /api/konten/{id}` `{eltern_id}` |
| `km-konto-loeschen` „Löschen…“ | 9.7 (`loeschen.md` 5) |

## 9. Dialoge

Alle Dialoge: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` auf
ihre Überschrift; beim Öffnen erhält das erste Eingabefeld (sonst der erste
Knopf) den Fokus; Tab bleibt im Dialog; Esc schließt ohne Wirkung; danach
erhält das auslösende Element den Fokus zurück. Fehler des Servers stehen im
Dialog in `dialog-fehler` (`role="alert"`); der Dialog bleibt dann offen.

### 9.1 Kategorie-Auswahl (`kategorie-auswahl`)

- `kategorie-auswahl-suche` (Texteingabe, Fokus) filtert die Liste
  `kategorie-auswahl-liste` (`role="listbox"`) mit Einträgen
  `kategorie-option-<id>` (`role="option"`, Beschriftung = Pfad) für alle
  Konten der Art `aufwand` und `ertrag`, in Baumreihenfolge. Filter wie die
  Befehlspalette (12.3) über den Pfad.
- Pfeil ab/auf markiert (`aria-selected`), Enter oder Klick übernimmt sofort
  und schließt; dann wirkt die auslösende Aktion.

### 9.2 Tag-Auswahl (`tag-auswahl`)

- `tag-auswahl-name` (Texteingabe mit Vorschlägen der vorhandenen Tags),
  Knöpfe `tag-auswahl-hinzufuegen` und `tag-auswahl-entfernen`.
- Der Name wird mit vorhandenen Tags nach `casefold` verglichen.
  Hinzufügen eines unbekannten Namens legt den Tag zuerst an
  (`POST /api/tags`), danach `mehrfach/tags` mit `hinzufuegen`. Entfernen
  eines unbekannten Namens → Fehler im Dialog, keine Anfrage.

### 9.3 Split-Dialog (`split-dialog`)

- Je Split eine Zeile `split-zeile-<i>` (`i` = 0, 1, … in Reihenfolge der
  Splits) mit `split-konto-<i>` (`<select>`, alle Konten, Wert = ID,
  Beschriftung = Pfad), `split-betrag-<i>` (Euro mit Vorzeichen wie
  gespeichert, 5), `split-memo-<i>` und `split-entfernen-<i>`.
- `split-hinzufuegen` hängt eine leere Zeile an (nächster Index).
  `split-rest` zeigt die Summe aller Beträge (`data-betrag`).
- `split-speichern` ist genau dann aktiv, wenn mindestens zwei Zeilen
  vorhanden sind, jede ein Konto und einen gültigen Betrag hat und die
  Summe 0 ist; es sendet `PUT /api/buchungen/{id}/splits` mit den Zeilen in
  Anzeigereihenfolge (`konto_id`, `betrag`, `memo`). `split-abbrechen`
  schließt ohne Wirkung.

### 9.4 Ziel-Auswahl (`ziel-auswahl`)

Für „Verschieben nach…“: Liste (`role="listbox"`) mit `ziel-option-wurzel`
(„Oberste Ebene“, `eltern_id = null`) und `ziel-option-<id>` für alle
Konten derselben Klasse (`datenmodell.md` 2) außer dem Konto selbst und
seinen Nachfahren. Enter oder Klick übernimmt.

### 9.5 Rückfrage (`bestaetigen-dialog`)

Text mit dem Gegenstand (z. B. „3 Buchungen löschen?“), Knöpfe
`bestaetigen-ja` und `bestaetigen-nein`; anfangs hat `bestaetigen-nein`
den Fokus.

### 9.6 Dubletten-Dialog (`dublette-dialog`)

Zeigt den offenen Verdacht zur Buchung: je Kandidat `dublette-kandidat-<id>`
(Datum, Empfänger, Betrag) mit `dublette-zusammenfuehren-<id>`
(`POST /api/dubletten/{verdacht_id}/aufloesen`
`{"entscheidung": "zusammenfuehren", "behalten_id": <id>}`) und
`dublette-keine` (`{"entscheidung": "keine_dublette"}`).

### 9.7 Konto löschen (`loeschen-dialog`, `loeschen.md` 5)

1. Die Oberfläche ruft zuerst `POST /api/konten/{id}/loeschen` mit
   `{"buchungen": "unkategorisiert", "konflikte": "behalten",
   "trocken": true}` auf.
2. Sind `buchungen_betroffen`, `unterkonten`, `regeln_geaendert` und
   `regeln_geloescht` leer (unbenutztes Konto): Rückfrage (9.5), dann
   `DELETE /api/konten/{id}`.
3. Sonst `loeschen-dialog` mit `loeschen-anzahl-buchungen`,
   `loeschen-anzahl-unterkonten`, `loeschen-anzahl-regeln` (je
   `data-anzahl`: Länge von `buchungen_betroffen`, `unterkonten`,
   `regeln_geaendert` ∪ `regeln_geloescht`) und den Optionsfeldern
   `loeschen-wahl-loeschen`, `loeschen-wahl-elternkonto` (deaktiviert bei
   Wurzelkonten), `loeschen-wahl-unkategorisiert` – **ohne Vorauswahl**.
4. Nach der Wahl Probelauf mit dieser Variante. Gibt es
   `konfliktbuchungen`, zeigt `loeschen-konflikte` je Buchung
   `loeschen-konflikt-<id>` und die Optionsfelder
   `loeschen-konflikte-loeschen` / `loeschen-konflikte-behalten` (ohne
   Vorauswahl, Pflicht). Gibt es `gesperrt`, ist das Kontrollkästchen
   `loeschen-gesperrte-bestaetigen` Pflicht (`gesperrte_einbeziehen`).
5. `loeschen-ausfuehren` ist erst aktiv, wenn alle Pflichtangaben gemacht
   sind; es sendet die Operation ohne `trocken` (`konflikte` ohne
   Konfliktbuchungen: `"behalten"`). `loeschen-abbrechen` schließt ohne
   Wirkung. Danach ist der Vorgang wie jede eigene Änderung rückgängig zu
   machen (11).

### 9.8 Buchung erfassen (`erfassen-dialog`)

In der Kontoansicht öffnet `buchung-erfassen` den Dialog für
`POST /api/buchungen/erfassen` (`buchhaltungspflege.md` 3) mit
`konto_id` = aktuelles Konto: `erfassen-art` (`<select>`: `ausgabe`,
`einnahme`, `umbuchung`, `korrektur`), `erfassen-datum` (date),
`erfassen-betrag` (Euro, positiv), `erfassen-empfaenger` (Text →
`empfaenger_name`, leer → weglassen), `erfassen-verwendungszweck`,
`erfassen-kategorie` (`<select>` Kategorien, für `ausgabe`/`einnahme`),
`erfassen-gegenkonto` (`<select>` Bestandskonten, für `umbuchung`),
`erfassen-speichern`.

## 10. Drag and Drop (K 5)

- **Buchung auf Kategorie:** Eine Zeile der Buchungsliste lässt sich auf
  einen Eintrag `kategorie-<id>` in `panel-kategorien` ziehen. Liegt die
  Zeile in der Auswahl, wird die ganze Auswahl gezogen, sonst wird die
  Auswahl vorher auf diese Zeile gesetzt. Ablegen wirkt wie
  `mehrfach-kategorie` mit dieser Kategorie (7.5).
  Enthält die gezogene Auswahl eine nicht kategorisierbare Buchung
  (`datenmodell.md` 3.2), darf die Oberfläche die Ablage ablehnen (keine
  Anfrage) oder die Anfrage senden und die Ablehnung (422
  `nicht_kategorisierbar`) als Fehlermeldung zeigen; der Bestand bleibt
  unverändert (E-151). Gleiches gilt für Wischen nach links (16.4).
- **Kategorien umsortieren:** Ein Eintrag `kategorie-<id>` (in
  `panel-kategorien` oder auf `/kategorien`) lässt sich auf einen anderen
  Eintrag derselben Klasse ziehen → `PATCH /api/konten/{id}`
  `{"eltern_id": <ziel>}` (wird Unterkategorie), oder auf die
  Gruppenüberschrift `kategorien-gruppe-aufwand` bzw.
  `kategorien-gruppe-ertrag` seiner Klasse → `{"eltern_id": null}`.
  Ablegen auf sich selbst, einen Nachfahren oder eine andere Klasse ändert
  nichts (keine oder abgelehnte Anfrage). Eine Reihenfolge außer der
  Hierarchie gibt es nicht (Geschwister nach Name, E-144).
- **Bedienung:** mit der Maus (Taste drücken, mindestens 4 px bewegen,
  über dem Ziel loslassen). Die Umsetzung ist frei (HTML-Drag-and-Drop
  oder Zeigerereignisse); sie muss mit echten Mausereignissen funktionieren.
  Während des Ziehens zeigt ein Ziel, ob es die Ablage annimmt.
- **Ohne Maus:** Kontextmenü „Kategorie setzen…“ bzw. „Verschieben
  nach…“; mobil Wischen (16.4).

## 11. Rückgängig und Wiederholen (K 5, K 14)

Rückgängig in der Oberfläche **ist** Rückgängig im Änderungsprotokoll
(`protokoll.md` 6); es gibt keinen zweiten Mechanismus.

- **Stapel:** Die Oberfläche führt je Browser-Tab einen Rückgängig- und
  einen Wiederholen-Stapel (nur im Arbeitsspeicher, beim Neuladen leer).
  Ein Eintrag ist eine nicht leere Liste von Änderungs-IDs.
- **Eintrag anlegen:** Vor jeder eigenen Operation mit Wirkung auf den
  Buchbestand (Inline-Bearbeitung, Kategorie/Tags/Vorschläge setzen,
  Löschen, Splitten, Drag and Drop, Umbenennen, Verschieben, Konto anlegen
  oder löschen, Erfassen, Dubletten, Import, Jahresabgleich) merkt sie die
  höchste Änderungs-ID `m` (`GET /api/aenderungen?pro_seite=1`); nach dem
  Erfolg liest sie die Änderungen mit `id > m` und legt die IDs derjenigen,
  deren `gruppe` nicht mit `sync:` beginnt, als **einen** Eintrag auf den
  Rückgängig-Stapel (bei mehreren Anfragen, z. B. Tag anlegen und zuordnen
  oder Mehrfachlöschen, alle zusammen). Entsteht keine Änderung, entsteht
  kein Eintrag. Jeder neue Eintrag leert den Wiederholen-Stapel.
- **Strg+Z** (⌘+Z), `rueckgaengig-knopf`, `meldung-rueckgaengig`, Befehl
  `rueckgaengig`: obersten Eintrag `E` nehmen; bei einer ID
  `POST /api/aenderungen/{id}/rueckgaengig`, bei mehreren
  `POST /api/aenderungen/rueckgaengig` `{"aenderung_ids": E}`. Erfolg →
  die Antwort `U` (Rückgängig-Änderung) kommt als `[U.id]` auf den
  Wiederholen-Stapel; Meldung „Rückgängig: …“. Fehler (409
  `rueckgaengig_konflikt`, `bereits_rueckgaengig`) → Fehlermeldung, `E`
  wird verworfen. Leerer Stapel → Hinweis, keine Anfrage.
- **Strg+Umschalt+Z** oder **Strg+Y**, `wiederholen-knopf`, Befehl
  `wiederholen`: obersten Eintrag `[U.id]` des Wiederholen-Stapels
  rückgängig machen (`protokoll.md` 6.3); die Antwort `R` kommt als
  `[R.id]` auf den Rückgängig-Stapel.
- Danach lädt die Oberfläche die angezeigten Daten neu.
- Strg+Z in einer Texteingabe (auch im `inline-editor`) bleibt das
  Rückgängig des Browsers für den Text; bei offenem Dialog wirkt Strg+Z
  nicht auf den Stapel.
- Die Seite `/protokoll` bietet unabhängig davon Rückgängig je Änderung
  (13.9).

## 12. Tastatur

### 12.1 Globale Kürzel

Einbuchstabige Kürzel (`/`, `?`) und Alt-Kürzel wirken nicht, solange der
Fokus in einer Texteingabe, einem Auswahlfeld oder einem Editor liegt.

| Kürzel | Wirkung |
| --- | --- |
| Strg+K, ⌘+K, Strg+Umschalt+P | Befehlspalette öffnen (12.3) |
| `/` | Fokus in `suche-feld` |
| `?` | Tastaturhilfe `tastatur-hilfe` (Dialog mit allen Kürzeln) |
| Strg+Z, ⌘+Z | Rückgängig (11) |
| Strg+Umschalt+Z, ⌘+Umschalt+Z, Strg+Y | Wiederholen (11) |
| Alt+1 … Alt+8 | die ersten acht Navigationsziele (3) in dieser Reihenfolge |
| Esc | oberste Ebene schließen (Menü, Dialog, Palette, mobiles Menü); sonst Auswahl leeren |

### 12.2 Kürzel der Buchungsliste (Fokus in der Liste)

Pfeiltasten, Pos1, Ende, Leertaste, Strg+A und Umschalt-Varianten nach 7.4;
F2 Inline-Bearbeitung (7.6); Entf „Löschen…“ für die Auswahl (Rückfrage);
Enter öffnet die Einzelheiten (`panel-details` zeigt die Fokuszeile, mobil
als Dialog); Umschalt+F10 oder Kontextmenü-Taste: Kontextmenü.

### 12.3 Befehlspalette

- `befehlspalette` (`role="dialog"`) mit `befehlspalette-eingabe`
  (`role="combobox"`, `aria-expanded`, `aria-controls` auf die Liste,
  `aria-activedescendant` auf den aktiven Eintrag, Fokus beim Öffnen) und
  `befehlspalette-liste` (`role="listbox"`) mit Einträgen `befehl-<id>`
  (`role="option"`; der aktive trägt `aria-selected="true"`).
- **Treffer:** Eingabe und Beschriftung werden normalisiert (Unicode NFKD,
  diakritische Zeichen entfernt nach vorheriger Ersetzung ä→ae, ö→oe,
  ü→ue, ß→ss, dann `casefold`); ein Eintrag passt, wenn jedes Wort der
  Eingabe (durch Leerraum getrennt) Teilzeichenkette der normalisierten
  Beschriftung ist. Leere Eingabe zeigt alle. Reihenfolge: die festen
  Befehle in der Reihenfolge der Tabelle, dann die Konten nach Name.
  Der erste Treffer ist aktiv; Pfeil ab/auf wechselt; Enter oder Klick
  führt aus und schließt; Esc schließt ohne Wirkung (Fokus zurück).
- Feste Befehle:

| `id` | Beschriftung | Wirkung |
| --- | --- | --- |
| `gehe-uebersicht` | Gehe zu: Finanzübersicht | `/` |
| `gehe-konten` | Gehe zu: Konten | `/konten` |
| `gehe-kategorien` | Gehe zu: Kategorien | `/kategorien` |
| `gehe-wiederkehrend` | Gehe zu: Wiederkehrende Buchungen | `/wiederkehrend` |
| `gehe-kredite` | Gehe zu: Kredite | `/kredite` |
| `gehe-berichte` | Gehe zu: Berichte | `/berichte` |
| `gehe-import` | Gehe zu: Import | `/import` |
| `gehe-einstellungen` | Gehe zu: Einstellungen | `/einstellungen` |
| `gehe-protokoll` | Gehe zu: Änderungsprotokoll | `/protokoll` |
| `gehe-empfaenger` | Gehe zu: Empfänger | `/empfaenger` |
| `gehe-regeln` | Gehe zu: Regeln | `/regeln` |
| `gehe-vorlagen` | Gehe zu: Split-Vorlagen | `/vorlagen` |
| `gehe-dubletten` | Gehe zu: Dubletten | `/dubletten` |
| `gehe-sync` | Gehe zu: Synchronisation | `/sync` |
| `gehe-benachrichtigungen` | Gehe zu: Benachrichtigungen | `/benachrichtigungen` |
| `rueckgaengig` | Rückgängig | 11 |
| `wiederholen` | Wiederholen | 11 |
| `synchronisieren` | Bankkonten jetzt synchronisieren | wie `sync-starten` |
| `thema-system` | Design: wie System | 17 |
| `thema-hell` | Design: Hell | 17 |
| `thema-dunkel` | Design: Dunkel | 17 |
| `layout-zuruecksetzen` | Layout zurücksetzen | 15 |
| `abmelden` | Abmelden | nur bei aktiver Anmeldung (19) |

- Dazu je offenes Bestandskonto `konto-<id>` „Konto öffnen: <Name>“ →
  `/konten/<id>`.

## 13. Weitere Seiten

### 13.1 Kategorien (`/kategorien`) und Kategorienbaum

- Baum `kategorienbaum` (`role="tree"`) mit den Gruppen
  `kategorien-gruppe-aufwand` („Ausgaben“) und `kategorien-gruppe-ertrag`
  („Einnahmen“); Einträge `kategorie-<id>` (`role="treeitem"`,
  `aria-level` ab 1 für Wurzelkategorien, `aria-expanded` bei Einträgen mit
  Unterkategorien, Unterkategorien in einem Element `role="group"`
  innerhalb des Eintrags). Geschwister nach Name (`localeCompare(…,
  "de")`). Anfangs ist alles aufgeklappt.
- Derselbe Baum steht in `panel-kategorien` (7.3).
- Drag and Drop nach 10, Kontextmenü nach 8.2; `kategorie-anlegen` legt
  eine Wurzelkategorie an (Dialog `konto-dialog` mit `konto-name` und
  `konto-art` = `aufwand`/`ertrag`).

### 13.2 Einstellungen (`/einstellungen`)

| Element | Zweck |
| --- | --- |
| `einstellung-thema` | `<select>` `system`/`hell`/`dunkel` (17) |
| `layout-zuruecksetzen` | Layout zurücksetzen (15) |
| `zustellung-status` | `GET /api/benachrichtigungen/zustellung`: `data-plugin` = `plugin` |
| `benachrichtigung-test` | „Test-Benachrichtigung senden“: `POST /api/benachrichtigungen/test` (E-138); deaktiviert bei Plugin `keins` |
| `benachrichtigung-test-ergebnis` | Ergebnis: `data-zugestellt` = `ja`/`nein`, `data-gesendet` = `ja`/`nein`; Text nennt bei Fehlschlag die Meldung und den HTTP-Status; im Mock-Modus mit Plugin `mock` einen Hinweis, dass nichts übertragen wurde |
| `pin-status` | `data-vorhanden` = `ja`/`nein` (`GET /api/sync/status`) |
| `pin-verwerfen` | `DELETE /api/sync/pin` |
| `geheimnis-<name>` | je per REST schreibbarem Geheimnis (`ntfy_token`, `oauth_client_secret`, `geheimnisse.md` 4): `data-gesetzt` = `ja`, wenn es in `GET /api/geheimnisse` unter `eintraege` steht, sonst `nein`; `geheimnis-wert-<name>` (`type="password"`, nie vorbelegt, nach dem Speichern geleert) mit `geheimnis-speichern-<name>` (`PUT`) und `geheimnis-loeschen-<name>` (`DELETE`) |
| `sicherung-herunterladen` | Link auf `/api/sicherung` (Download) |
| `sicherung-datei`, `sicherung-pruefen`, `sicherung-einspielen` | `POST /api/sicherung/einspielen` erst als Probelauf, dann nach Rückfrage mit Bestätigung (`sicherung.md` 4) |
| `postfaecher` | Liste der Postfächer mit Links nach `/mail/postfaecher/<id>` |
| `abmelden` | nur bei aktiver Anmeldung (19) |
| `status-modus` | `data-modus` = `modus` aus `GET /api/status` |

### 13.3 Konten (`/konten`)

Baum der Bestandskonten `kontenbaum` mit `kontenbaum-konto-<id>`
(Kontextmenü 8.2); `konto-anlegen` öffnet `konto-dialog` mit `konto-name`,
`konto-art` (`girokonto`, `sparkonto`, `kreditkonto`), `konto-iban`.
`abstimmen` je Konto (`kontenbaum-abstimmen-<id>`) öffnet
`abstimmung-dialog` mit `abstimmung-stichtag`, `abstimmung-saldo`,
`abstimmung-pruefen` (Probelauf) und `abstimmung-speichern`
(`POST /api/abstimmungen`).

### 13.4 Kredite (`/kredite`, `/kredite/<id>`) und Kreditabgleich

- `kredite-liste` mit `kredit-<id>` (Name, `restschuld` und `rate` mit
  `data-betrag`); Klick → `/kredite/<id>`.
- `/kredite/<id>`: Parameter, Tilgungsplan `tilgungsplan` aus
  `GET /api/kredite/{id}/plan` (Zeilen `plan-zeile-<nr>`, `nr` ab 1),
  bisherige Abgleiche `abgleich-<jahr>`.
- **Jahresabgleich** (K 10): `abgleich-jahr` (Zahl), `abgleich-restschuld`,
  `abgleich-zinsen` (Euro, 5), `abgleich-pruefen` → `POST
  /api/kredite/{id}/jahresabgleich` mit `trocken: true`; Ergebnis
  `abgleich-ergebnis` mit `abgleich-restschuld-berechnet`,
  `abgleich-zinsen-berechnet`, `abgleich-differenz-restschuld`,
  `abgleich-differenz-zinsen` (je `data-betrag`) und je Korrektursplit
  `abgleich-korrektur-<i>`. `abgleich-bestaetigen` sendet denselben Abgleich
  ohne `trocken`; danach erscheint `abgleich-<jahr>`. Fehler (409
  `kredit_jahr_abgeglichen`) → Meldung.

### 13.5 Wiederkehrende Buchungen (`/wiederkehrend`)

`wiederkehrend-tabelle` aus `GET /api/wiederkehrend` mit Zeilen
`serie-<schluessel>` (Empfänger, Rhythmus, Betrag und Jahreskosten mit
`data-betrag`, nächste Fälligkeit mit `data-datum`, `data-status`).
Ab M16: Menü je Serie und Begründung (26.3).

### 13.6 Berichte (`/berichte`)

Kontostandsverlauf (K 11): `bericht-konten` (`<select multiple>`, Wert =
Konto-ID), `bericht-von`, `bericht-bis` (`<input type="date">`),
`bericht-intervall` (`<select>`: `tag`, `woche`, `monat`, `jahr`); jede
Änderung lädt den Bericht neu; Diagramm
`bericht-diagramm` (SVG oder Canvas, `role="img"`, `aria-label`) mit einer
Linie je Konto und Tabelle `bericht-tabelle` (Zeile je Stichtag
`bericht-zeile-<datum>`, Zelle je Konto `[data-konto-id]` mit
`data-betrag`) aus `GET /api/berichte/kontostand`. Export: Links
`export-csv` und `export-pdf` auf `/api/export/buchungen.csv` bzw.
`.pdf`.

### 13.7 Import (`/import`)

`import-format` (`kmymoney`/`gnucash`), `import-datei`
(`<input type="file">`), `import-starten` → `POST /api/import/kmymoney`
bzw. `/gnucash`. Ergebnis `import-ergebnis` mit `data-erfolgreich` =
`ja`/`nein` und `import-zahl-<feld>` (`data-anzahl`) für jedes Zählfeld des
`ImportErgebnis` (z. B. `import-zahl-buchungen_neu`), Fehler und Warnungen
als Liste `import-meldung` (Text mit `code`).

### 13.8 Suche (`/suche?q=<text>`)

Aus `GET /api/suche`: `suche-anzahl` (`data-anzahl` = `buchungen_gesamt`),
Treffer `treffer-konto-<id>`, `treffer-empfaenger-<id>`, `treffer-tag-<id>`
und Buchungszeilen `buchung-<id>` (Kontextmenü 8.2).

### 13.9 Änderungsprotokoll (`/protokoll`)

`protokoll-liste` aus `GET /api/aenderungen` (neueste zuerst, 50 je Seite,
`protokoll-mehr`): `aenderung-<id>` mit Zeitpunkt, Quelle, Beschreibung,
`data-quelle`, `data-wirksam` = `ja`/`nein`; bei wirksamen
`aenderung-rueckgaengig-<id>` (`POST /api/aenderungen/{id}/rueckgaengig`). Ab M15
zusätzlich `aenderung-bis-<id>` (25.1).

### 13.10 Übrige Seiten (Mindestumfang)

| Seite | Mindestens |
| --- | --- |
| `/empfaenger` | `empfaenger-<id>` je Empfänger (Name, Aliase, Standardkategorie); Umbenennen, Aliase, Standardkategorie (`PATCH`), Zusammenführen (`empfaenger-zusammenfuehren`) |
| `/regeln` | `regel-<id>` je Regel; `regeln-anwenden` (`POST /api/regeln/anwenden`) |
| `/vorlagen` | `vorlage-<id>` je Vorlage; `vorlagen-anwenden` |
| `/dubletten` | `verdacht-<id>` je offenem Verdacht mit den Aktionen aus 9.6 |
| `/sync` | `sync-status` (`data-laeuft`), Läufe `lauf-<id>` (`data-status`), Bankkonten `bankkonto-<iban>` mit Entscheidung bei `konto_fehlt` |
| `/benachrichtigungen` | `benachrichtigung-<id>` (`data-gelesen`), Link `benachrichtigung-link-<id>` auf `link` (falls gesetzt), `benachrichtigung-gelesen-<id>` |
| `/mail/postfaecher/<id>` | Status, `postfach-anmelden` (`POST …/anmeldung`, zeigt `autorisierung_url` als Link `postfach-autorisierung-link`), `postfach-antwort-url` und `postfach-abschliessen` |

## 14. TAN-Seite (`/tan/<id>`, K 6)

- Aus `GET /api/tan-anforderungen/{id}`: `tan-status` (`data-status`),
  `tan-challenge` (Anweisungstext der Bank), `tan-gueltig-bis`
  (`data-zeitpunkt`).
- Bei `status = "offen"` und `hat_bild`: Bild `tan-bild` (`<img>` mit
  `src` auf `/api/tan-anforderungen/{id}/bild` oder einer daraus erzeugten
  `blob:`-URL, `alt` nicht leer), im mobilen Layout höchstens so breit wie
  der sichtbare Bereich.
- `tan-bild-speichern` („QR-Code speichern“): lädt genau die Bytes des
  Bildes als Datei `kontor-tan-<id>.<endung>` herunter (`png` für
  `image/png`, `jpg` für `image/jpeg`, `gif` für `image/gif`, sonst `bin`).
- `tan-bild-teilen` („Teilen“): nur sichtbar, wenn
  `navigator.canShare({files: [datei]})` wahr ist; ruft
  `navigator.share({files: [datei], title: "TAN-Freigabe"})` mit derselben
  Datei (Name und Typ wie beim Speichern, Inhalt = Bildbytes). Abbruch
  durch den Anwender (`AbortError`) ist kein Fehler.
- `tan-eingabe` (`autocomplete="one-time-code"`, nicht vorbelegt) und
  `tan-senden` → `POST /api/tan-anforderungen/{id}/antwort`;
  `tan-abbrechen` → Rückfrage, dann `POST …/abbrechen`.
  Erfolg → `tan-status` zeigt den neuen Status, `tan-ergebnis` mit
  `data-lauf-status` = Status des Laufs. `422 tan_ungueltig` →
  `tan-fehler` (`role="alert"`), Eingabe geleert, Anforderung bleibt offen.
- Bei `abgelaufen`, `abgebrochen`, `beantwortet`: kein Bild, keine Eingabe.
- Die TAN steht nie in URL, `localStorage`, `sessionStorage`, IndexedDB oder
  Cache; das Eingabefeld ist nach dem Senden leer. Dasselbe gilt für die
  PIN (15.4).

## 15. Panels und Layout (K 5)

### 15.1 Aufbau

- Die Kontoansicht hat zwei Andockbereiche `bereich-links` und
  `bereich-rechts` neben der Buchungsliste. Panels: `panel-kategorien`
  (Vorgabe: links, Breite 240 px) und `panel-details` (Vorgabe: rechts,
  Breite 320 px), beide ausgeklappt.
- Jedes Panel `panel-<p>` trägt `data-bereich` = `links`/`rechts` und
  `data-eingeklappt` = `ja`/`nein`; es hat einen Kopf `panel-kopf-<p>`
  (Griff zum Verschieben, Überschrift), `panel-einklappen-<p>`
  (`aria-expanded`), `panel-verschieben-<p>` (wechselt den Bereich, für die
  Tastatur) und an der zur Liste zeigenden Kante den Griff
  `panel-groesse-<p>` (`role="separator"`, `aria-orientation="vertical"`,
  `aria-valuenow` = Breite in px, `aria-valuemin="160"`,
  `aria-valuemax="600"`, fokussierbar).
- Panels in einem Bereich stehen nebeneinander; Reihenfolge von außen
  (Fensterrand) nach innen (Liste) nach `position`.

### 15.2 Bedienung

- **Größe ändern:** Ziehen von `panel-groesse-<p>` um `dx` px ändert die
  Breite um `dx` (links: nach rechts = breiter; rechts: nach links =
  breiter), begrenzt auf 160–600 px. Tastatur auf dem fokussierten Griff:
  im linken Bereich Pfeil rechts +16 px, Pfeil links −16 px; im rechten
  Bereich Pfeil links +16 px, Pfeil rechts −16 px; Pos1 = 160, Ende = 600.
  Die gemessene Breite (`getBoundingClientRect().width`) des Panels
  entspricht `aria-valuenow` (±1 px).
- **Einklappen:** `panel-einklappen-<p>` schaltet um; eingeklappt ist das
  Panel höchstens 48 px breit und zeigt nur Kopf/Knopf.
- **Verschieben:** Ziehen von `panel-kopf-<p>` in den anderen Bereich
  (während des Ziehens sind beide Bereiche als Ablage `ablage-links` und
  `ablage-rechts` mindestens 48 px breit sichtbar) oder
  `panel-verschieben-<p>`. Das Panel kommt an die innerste Stelle (größte
  `position`) des Zielbereichs.

### 15.3 Speicherung

- Jede Änderung wird sofort im `localStorage` des Browsers unter dem
  Schlüssel `kontor.layout` gespeichert (E-141):
  `{"version": 1, "panels": {"<p>": {"bereich": "links"|"rechts",
  "position": int, "breite": int, "eingeklappt": bool}}}`.
  Beim Laden gilt dieser Stand; fehlt er oder ist er ungültig, gelten die
  Vorgaben. Das Layout gilt je Browser und Gerät, nicht je Server.
- `layout-zuruecksetzen` (Einstellungen, Befehl) entfernt den Schlüssel
  und stellt die Vorgaben her.
- Im mobilen Layout (16) werden Panels nicht angedockt; das gespeicherte
  Layout bleibt unverändert erhalten.

### 15.4 Synchronisation und PIN

`sync-starten` → `POST /api/sync` `{}`. Ergebnis als Meldung (Status des
Laufs). Wartet der Lauf auf eine TAN, enthält die Meldung den Link
`sync-tan-link` nach `/tan/<tan_anforderung_id>`. Ist `fehler.code`
`bank_pin_fehlt` oder `bank_pin_falsch`, öffnet sich `pin-dialog` mit
`pin-eingabe` (`type="password"`, `autocomplete="off"`) und `pin-senden`
→ `PUT /api/sync/pin`, danach erneut `POST /api/sync`. 409 (`sync_laeuft`,
`tan_ausstehend`) → Meldung.

## 16. Mobile Ansicht (K 14)

### 16.1 Umschaltung

Ist der sichtbare Bereich schmaler als 768 CSS-Pixel, gilt das mobile
Layout (`app` mit `data-layout="mobil"`), sonst das Desktop-Layout. Der
Wechsel geschieht ohne Neuladen.

### 16.2 Navigation und Seiten

- Die Navigation ist anfangs verborgen. `menue-knopf` blendet sie als
  Menü über dem Inhalt ein (`aria-expanded="true"`, Fokus auf den ersten
  Eintrag), dazu `menue-hintergrund`. Ein Eintrag navigiert und schließt
  das Menü; Esc, `menue-hintergrund` oder erneutes Tippen auf
  `menue-knopf` schließen es (Fokus zurück auf `menue-knopf`).
- Navigationseinträge und Knöpfe sind mindestens 44 × 44 px groß.
- Kein waagerechtes Scrollen der Seite: `document.documentElement
  .scrollWidth ≤ window.innerWidth` auf jeder Seite.
- Der Mock-Hinweis bleibt oben sichtbar.

### 16.3 Kompakte Buchungsliste

- `buchungsliste` mit `data-kompakt="ja"` (Desktop `nein`); je Zeile
  mindestens Datum, Empfänger (ohne Empfänger: Verwendungszweck), Betrag
  und Kategorie; Zeilen mindestens 44 px hoch; die Spalte
  `verwendungszweck` darf ausgeblendet sein.
- Tippen auf eine Zeile ohne Auswahl öffnet die Einzelheiten
  (`panel-details` als Dialog mit `details-schliessen`); ist mindestens eine
  Zeile ausgewählt (Auswahlmodus), schaltet Tippen die Zeile um.
- `panel-kategorien` wird nicht angezeigt; die Filterleiste ist anfangs
  ausgeblendet (`filter-umschalten`); `mehrfach-leiste` liegt am unteren
  Rand.

### 16.4 Gesten (ersetzen Rechtsklick und Drag and Drop, E-145)

| Geste | Erkennung | Wirkung |
| --- | --- | --- |
| lange Berührung | Finger ≥ 500 ms ohne Bewegung über 10 px | Kontextmenü wie Rechtsklick (8); kein Tippen danach |
| nach rechts wischen | waagerecht ≥ 80 px nach rechts, senkrecht ≤ 40 px, ≤ 1 000 ms | Buchungszeile: Auswahl der Zeile umschalten (ersetzt Strg+Klick) |
| nach links wischen | wie oben nach links | Buchungszeile: Kategorie-Auswahl (9.1) für die Zeile bzw. die Auswahl, wenn sie darin liegt (ersetzt Drag and Drop auf eine Kategorie) |

- Lange Berührung auf `kategorie-<id>` bzw. Konten öffnet das
  Kontomenü; „Verschieben nach…“ ersetzt dort das Umsortieren per Drag and
  Drop.
- Gesten werden aus Touch- bzw. Pointer-Ereignissen selbst erkannt (Tests
  erzeugen echte Touch-Ereignisse); senkrechtes Scrollen der Liste bleibt
  möglich.

## 17. Helles und dunkles Design (K 5)

- `<html>` trägt `data-thema` = `hell` oder `dunkel` (wirksames Design).
- Einstellung `system` (Vorgabe), `hell` oder `dunkel` in
  `localStorage["kontor.thema"]`; bei `system` folgt das Design
  `prefers-color-scheme` und wechselt bei einer Änderung der
  Systemeinstellung sofort ohne Neuladen.
- Dunkel: Hintergrund des Hauptbereichs mit relativer Leuchtdichte
  (WCAG) < 0,2; hell: > 0,7. Normaler Text hat in beiden Designs ein
  Kontrastverhältnis ≥ 4,5 : 1 zu seinem Hintergrund.

## 18. Installierbare Web-App (PWA, K 5)

- **Manifest** `/oeffentlich/manifest.webmanifest` (öffentlich,
  `Content-Type: application/manifest+json`) mit `id` `/`, `name`
  „Kontor“, `short_name` „Kontor“, `lang` `de`, `start_url` `/`, `scope`
  `/`, `display` `standalone`, `background_color` und `theme_color`
  (`#rrggbb`) und `icons` mit mindestens einem PNG 192 × 192 und einem PNG
  512 × 512 (`purpose` fehlt oder enthält `any`) sowie mindestens einem
  Symbol mit `purpose` `maskable`; alle Symbole unter `/oeffentlich/`, die
  angegebene Größe stimmt mit der Datei überein.
- **Installierbarkeit:** Chromium meldet für `/` keine Hinderungsgründe
  (`Page.getInstallabilityErrors` leer).
- **Service Worker** `/sw.js` (JavaScript, `Cache-Control: no-cache` oder
  `no-store`), registriert mit Bereich `/`; nach dem Neuladen steuert er die
  Seite (`navigator.serviceWorker.controller`).
- **Offline:** Der Service Worker legt die Hülle und die statischen Dateien
  in Caches mit dem Namenspräfix `kontor-` ab. Navigationen: zuerst Netz,
  bei Netzfehler die zwischengespeicherte Hülle. Ohne Netz zeigt die
  Oberfläche `offline-hinweis` (`role="status"`, Text enthält „offline“
  ohne Beachtung der Groß-/Kleinschreibung) und keine veralteten Daten;
  kommt das Netz zurück, verschwindet der Hinweis und die Seite lädt ihre
  Daten.
- **Keine Daten im Browser:** Antworten unter `/api/` werden nie in
  Caches abgelegt. `localStorage`/`sessionStorage` enthalten nur Schlüssel
  mit dem Präfix `kontor.` ohne Texte aus dem Buchbestand; IndexedDB wird
  nicht für Buchbestand genutzt.

## 19. Anmeldung in der Oberfläche (M7)

- Bei aktiver Anmeldung (`GET /api/anmeldung`: `aktiv = true`) sendet die
  Oberfläche bei jeder schreibenden Anfrage `X-Kontor-CSRF` mit dem
  `csrf_token` aus `GET /api/anmeldung` (`sicherheit.md` 4.6). Antwortet
  der Server 401, wechselt sie nach `/anmelden?weiter=<p>` mit dem
  aktuellen Pfad samt Abfrage, kodiert wie `sicherheit.md` 3.2 (alles außer
  `A–Z a–z 0–9 - . _ ~ /` prozentkodiert, z. B. `/anmelden?weiter=/kategorien`);
  bei 403 `csrf_ungueltig` liest sie den Status einmal neu und wiederholt
  die Anfrage einmal.
- Anmeldeseite `/anmelden` (`sicherheit.md` 3.4): Absenden mit Enter im
  Passwortfeld; falsches Passwort → `anmeldung-fehler` (`role="alert"`),
  Feld geleert; 429 → `anmeldung-fehler` mit der Wartezeit. Erfolg →
  `weiter` (3.4).
- `abmelden` (Einstellungen, Befehl) → `POST /api/anmeldung/abmelden`,
  danach `/anmelden`.
- Bei abgeschalteter Anmeldung gibt es `abmelden` nicht.

## 20. Barrierefreiheit

- Landmarken nach 4.1, eine `<h1>` je Seite, Rollen und Zustände nach
  7.2 (Raster), 8 (Menü), 9 (Dialoge), 12.3 (Combobox/Listbox), 13.1
  (Baum), 15.1 (Trenner).
- Jedes bedienbare Element (Links, Knöpfe, Eingaben, Auswahlfelder,
  Elemente mit Rolle `button`, `menuitem`, `option`, `treeitem`,
  `checkbox`, `separator`) hat einen nicht leeren zugänglichen Namen
  (Text, `aria-label`, `aria-labelledby`, `<label>`, `title`, `alt`).
- Der Tastaturfokus ist sichtbar (`outline` oder `box-shadow` am
  fokussierten Element bei Tastaturbedienung).
- Alle Funktionen aus 7–12 sind ohne Maus erreichbar; Drag and Drop und
  Gesten haben die Alternativen aus 10 und 16.4.
- Bei `prefers-reduced-motion: reduce` keine Animationen und Übergänge.
- Die Vergrößerung im Browser ist nicht gesperrt (2).

## 21. Testumgebung (verbindlich für die Tests)

- **Server:** `kontor.app.create_app(config)` mit eigener temporärer
  Datenbank, gestartet mit uvicorn auf `127.0.0.1` und freiem Port im
  Testprozess; Mock-Modus (`mock_heute = 2024-12-31`), wo nicht anders
  angegeben. Wirkungen werden zusätzlich über die REST-Schnittstelle
  derselben laufenden App geprüft (`tests/hilfen/m8.py`).
- **Browser:** Playwright für Python mit Chromium (bzw. installiertem
  Chrome) headless, ohne Proxy; Namensauflösung außer `127.0.0.1` ist
  gesperrt, jede Anfrage an eine andere Herkunft gilt als Fehler. Ohne
  startbaren Browser werden die Browsertests mit Meldung übersprungen
  (Marker `browser`).
- **Desktop:** 1280 × 800, Gerätefaktor 1, ohne Touch. **Handy:** 390 ×
  844, Gerätefaktor 3, `is_mobile`, `has_touch`. Beide mit `locale
  de-DE`, Zeitzone `Europe/Berlin`, `reduced_motion = reduce`, Farbschema
  hell (außer in 17).
- **Gesten:** lange Berührung = `touchStart`, 800 ms halten, `touchEnd`;
  Wischen = `touchStart`, acht `touchMove` über 160 px in etwa 200 ms,
  `touchEnd` (CDP `Input.dispatchTouchEvent`). **Maus-Drag:** Taste
  drücken, 10 px bewegen, in Schritten zum Ziel bewegen, loslassen.
- **Warten:** nur auf Zustände (`data-geladen`, Sichtbarkeit, Attribute,
  REST-Stand), höchstens 10 s je Erwartung.
- In jedem Test werden unbehandelte Fehler der Seite, CSP-Verletzungen und
  Anfragen an fremde Herkünfte erfasst; jedes davon lässt den Test
  scheitern.

## 22. Meilenstein 11: Ergänzungen

Auftrag des Anwenders vom 2026-11-09 (E-158, E-163 bis E-165). Alles aus
1–21 gilt weiter; hier stehen nur Ergänzungen. Tests: `tests/app/m11/`.

### 22.1 Finanzübersicht: Kategorien (ergänzt 6)

- Unter `uebersicht-tabelle` (und nach `uebersicht-summe`), optisch
  abgesetzt (eigene Überschrift „Kategorien“), steht der Bereich
  `uebersicht-kategorien` mit dem Umschalter
  `uebersicht-kategorien-umschalten` (`aria-expanded`, `aria-controls` =
  ID des Inhalts). **Anfangs eingeklappt**; der Zustand bleibt im
  Browser-Speicher wie das Layout (15.3, Schlüssel frei) und überlebt das
  Neuladen. Eingeklappt sind die Zeilen nicht sichtbar (nicht im
  Zugänglichkeitsbaum).
- Inhalt: Gruppen in dieser Reihenfolge `uebersicht-gruppe-aufwand`
  („Ausgaben“), `uebersicht-gruppe-ertrag` („Einnahmen“),
  `uebersicht-gruppe-eigenkapital` („Sonstige“, z. B. „Unkategorisiert“,
  „Korrekturen“; die Gruppe fehlt, wenn es kein solches Konto gibt). Je Konto
  der Art eine Zeile `uebersicht-kategorie-<id>` mit `[data-feld="name"]`
  und `[data-feld="saldo"]`, Baumreihenfolge und `aria-level` wie 6.
- `data-betrag` = `saldo_gesamt` (Rohwert aus `GET /api/kontenuebersicht`).
  Angezeigt wird bei `ertrag` und `eigenkapital` der Wert mit umgekehrtem
  Vorzeichen, bei `aufwand` der Rohwert (Ausgaben und Einnahmen erscheinen
  also positiv; `datenmodell.md` 2 erlaubt das Umkehren zur Anzeige).
- Je Gruppe `uebersicht-summe-<art>` mit `data-betrag` = Summe `saldo`
  aller Konten dieser Art (Rohwert), Anzeige wie die Zeilen.
- Geschlossene Konten wie 6 (ausgeblendet, `uebersicht-geschlossene` blendet
  sie ein). Klick/Enter → `/konten/<id>`, Kontextmenü wie 8.2.
- Die Bestandskonten, `uebersicht-summe` und ihre Reihenfolge bleiben
  unverändert. Zeitraum: wie die Bestandskonten alle Buchungen (kein
  Stichtag); Auswertungen nach Zeitraum bleiben den Berichten (13.6).

### 22.2 Buchungsliste einer Kategorie (ersetzt den letzten Punkt von 7.2)

Die Kontoansicht `/konten/<id>` eines Kontos, das kein Bestandskonto ist
(`aufwand`, `ertrag`, `eigenkapital`), bietet **dieselben Funktionen** wie die
eines Bestandskontos: Filter und URL (7.1), Sortierung, Seiten, Anzahl und
Summe (7.2), Vorschläge, Seitenpanels (7.3), Auswahl (7.4),
Mehrfachbearbeitung (7.5), Inline-Bearbeitung (7.6), Kontextmenüs (8),
Dialoge (9), Drag and Drop (10), Rückgängig (11), Tastatur (12), mobile
Ansicht (16). Abweichungen:

- Die Seite trägt `data-kontoklasse` = Klasse des Kontos (`bestand`,
  `aufwand`, `ertrag`, `eigenkapital`) – auch bei Bestandskonten.
- **Zusätzliche Spalte** `data-feld="konto"` (nach `kategorie`) mit dem
  Bestandskonto der Buchung: Gibt es genau ein Konto der Klasse `bestand`
  unter ihren Splits, dessen Pfad und `data-konto-id`; bei mehreren
  „Mehrere“, ohne eines leer (`data-konto-id` jeweils leer). Die Spalte
  `kategorie` bleibt (nützlich mit Unterkategorien und zum Umkategorisieren).
- **Filter** `filter-kategorie` heißt hier `filter-konto` und listet die
  Bestandskonten (Beschriftung = Pfad); er bildet auf den REST-Parameter
  `kategorie_id` ab (der jedes Konto akzeptiert). `filter-unterkategorien`
  entfällt.
- **Unterkonten:** In der Kontoansicht jedes Kontos (auch Bestandskonten)
  gibt es das Kontrollkästchen `filter-unterkonten` → REST-Parameter
  `unterkonten=true` (`datenmodell.md` 16). Anfangs aus.
- `betrag`, `summe` und die Sortierung nach Betrag sind die Werte der REST-
  Liste aus Sicht dieses Kontos (mit `unterkonten` einschließlich seiner
  Unterkonten): Ausgaben in einer Ausgabenkategorie sind positiv,
  Erstattungen negativ (Rohwerte, keine Umkehr).
- Ablegen per Drag and Drop auf die eigene Kategorie ändert nichts (keine
  oder abgelehnte Anfrage); nach jeder Änderung, durch die eine Buchung die
  Filterbedingung nicht mehr erfüllt (z. B. umkategorisiert), verschwindet
  sie aus der Liste, und Anzahl und Summe werden neu geladen.

### 22.3 Empfänger zusammenführen (ergänzt 13.10)

- Auf `/empfaenger` trägt jede Zeile `empfaenger-<id>` ein Kontrollkästchen
  `empfaenger-auswahl-<id>`. `empfaenger-zusammenfuehren` ist aktiv, sobald
  mindestens zwei ausgewählt sind, und öffnet den Dialog
  `zusammenfuehren-dialog` mit:
  - `zusammenfuehren-ziel` (`<select>` über die ausgewählten Empfänger,
    vorbelegt mit dem mit den meisten Buchungen, bei Gleichstand kleinste
    `id`; Buchungszahl aus `GET /api/buchungen?empfaenger_id=…&pro_seite=1`
    `gesamt` oder einer gleichwertigen Abfrage),
  - `zusammenfuehren-name` (Text, vorbelegt mit dem Namen des Ziels; darf
    geändert werden – neuer Name des zusammengeführten Empfängers),
  - einer Vorschau `zusammenfuehren-aliase`: die Namen und Aliase, die
    danach als Suchtexte (Aliase) gelten,
  - `zusammenfuehren-ausfuehren` → `POST /api/empfaenger/{ziel}/zusammenfuehren`
    mit `quelle_ids` = übrige Ausgewählte und `name` (nur wenn geändert;
    `buchhaltungspflege.md` 2.6). Fehler (z. B. 409 `empfaenger_existiert`)
    erscheinen als Meldung im Dialog; der Dialog bleibt offen.
- Danach zeigt die Liste nur noch das Ziel mit allen Aliasen; Rückgängig
  über das Protokoll (11) stellt alle wieder her.

### 22.4 Synchronisation: Kontostand (ergänzt 13.10 `/sync`)

- Je Bankkonto `bankkonto-<iban>` das Element `bankkonto-saldo` mit
  `data-status` = `saldo_abgleich.status` des letzten Laufs, in dem das
  Konto erfolgreich verarbeitet wurde (leer, wenn es keinen gibt), und bei
  `stimmt`/`ausgeglichen` Bank-Saldo, Stichtag und Differenz; bei
  `ausgeglichen` ein Link `bankkonto-ausgleich-<iban>` auf
  `/konten/<konto_id>` (`kontostand.md` 2).

## 23. Meilenstein 12: Bearbeiten, Massenänderungen, Filterleiste

Auftrag des Anwenders vom 2026-11-09 (E-167 bis E-173). Alles aus 1–22
gilt weiter; hier stehen nur Ergänzungen. Fachliche Regeln:
`datenmodell.md` 17. Tests: `tests/app/m12/`.

### 23.1 Filterleiste anfangs eingeklappt (ersetzt den Anfangszustand in 7.1)

- Jede Kontoansicht (auch einer Kategorie, 22.2) beginnt mit
  ausgeblendeter `filter-leiste` (nicht sichtbar, nicht im
  Zugänglichkeitsbaum) und `filter-umschalten` mit `aria-expanded="false"`
  und `aria-controls` = ID der Filterleiste – auf Desktop und mobil, beim
  Aufruf, bei Navigation und beim Neuladen, auch wenn die URL Filter
  enthält. Der Zustand wird nicht gespeichert (E-172).
- `filter-umschalten` blendet die Leiste ein und aus und setzt
  `aria-expanded`. Filter setzen, `filter-zuruecksetzen` und das Neuladen
  der Liste nach Änderungen lassen den Zustand unverändert.
- `filter-anzahl` ist auch bei ausgeblendeter Leiste sichtbar (am oder im
  Umschalter) und trägt `data-anzahl` = Zahl der gesetzten Filter (7.1); ist
  sie größer als 0, enthält ihr Text die Zahl.
- Die Filter wirken unabhängig vom Zustand der Leiste (eine aus der URL
  gefilterte Liste ist auch eingeklappt gefiltert).

### 23.2 Inline-Bearbeitung (ergänzt 7.6)

Zusätzlich bearbeitbar sind die Zellen `empfaenger`, `status` und
`betrag`; Start per Doppelklick auf die Zelle. Editor, Übernehmen,
Abbrechen, „unveränderter Wert → keine Anfrage“ und Fehleranzeige wie 7.6;
beim `<select>` übernimmt jede Auswahländerung.

| Zelle | Editor (`inline-editor`, `data-feld`) | Anfrage |
| --- | --- | --- |
| `empfaenger` | `<select>`: Option `""` („ohne Empfänger“), dann je Empfänger aus `GET /api/empfaenger` (Reihenfolge der Antwort) dessen ID, Beschriftung = Name; vorbelegt mit dem aktuellen Wert | `PATCH /api/buchungen/{id}` `{empfaenger_id}` (`""` → `null`) |
| `status` | `<select>` mit den vier Werten in der Reihenfolge `importiert`, `vorlaeufig`, `bestaetigt`, `abgeglichen` (Wert = REST-Wert, Beschriftung wie 5); vorbelegt | `POST /api/buchungen/mehrfach/aendern` `{buchung_ids: [id], status}` |
| `betrag` | `<input type="text">`, Betragseingabe (5), vorbelegt mit dem Betrag der Zeile in Eingabeschreibweise ohne Währungszeichen (z. B. `-20,00`) | `PUT /api/buchungen/{id}/splits` |

- **Status** ist auch bei gesperrten Buchungen bearbeitbar. Ist der
  bisherige Status `abgeglichen` und der neue ein anderer, erscheint zuerst
  die Rückfrage `bestaetigen-dialog` (9.5; der Text sagt, dass die Buchung
  abgeglichen ist und danach bearbeitet werden kann): `bestaetigen-ja`
  sendet die Anfrage mit `entsperren: true`, `bestaetigen-nein` oder Esc
  sendet nichts, die Zelle zeigt wieder den alten Status.
- **Empfänger:** gesperrte Buchungen wie 7.6 (kein Editor oder Fehler des
  Servers, keine Änderung).
- **Betrag** ist genau dann bearbeitbar, wenn die Buchung nicht gesperrt
  ist, genau zwei Splits hat und genau einer davon auf dem Konto der
  Ansicht (`konto_id` der Seite) liegt. Für den eingegebenen Wert `v` (Cent,
  aus Sicht dieses Kontos wie die Spalte) sendet die Oberfläche die beiden
  Splits in bisheriger Reihenfolge mit unveränderten `konto_id` und `memo`:
  der Split auf dem Konto `v`, der andere `−v`. Ungültige Eingabe →
  `aria-invalid="true"`, keine Anfrage. Andere Buchungen öffnen keinen
  Betrags-Editor; für sie gibt es den Split-Dialog (9.3, `km-splitten`).
- Nach Erfolg wird die Liste neu geladen; Fehler → Meldung (4.3) mit der
  `meldung` des Servers, die Zelle zeigt den Stand des Servers.

### 23.3 Mehrfachbearbeitung und Kontextmenü (ergänzt 7.5 und 8.2)

Zusätzlich in `mehrfach-leiste` (Auswahl `A`, IDs aufsteigend; auch bei
`|A| = 1`):

| Element | Wirkung |
| --- | --- |
| `mehrfach-status` | Status-Auswahl (23.4), dann `POST /api/buchungen/mehrfach/aendern` mit `buchung_ids = A` und `status` |
| `mehrfach-bearbeiten` | Bearbeiten-Dialog (23.5) |

Zusätzliche Kontextmenü-Einträge für Buchungen (8.2), eingefügt vor
`km-loeschen` (das der letzte Eintrag bleibt):

| Eintrag | aktiv, wenn | Wirkung |
| --- | --- | --- |
| `km-status` „Status setzen…“ | immer | wie `mehrfach-status` |
| `km-mehrfach` „Bearbeiten…“ | immer | wie `mehrfach-bearbeiten` |

- **Bestätigung:** Enthält `A` Buchungen mit Status `abgeglichen` und ist
  der gewählte Status ein anderer, erscheint vor der Anfrage
  `bestaetigen-dialog` (Text nennt die Zahl dieser Buchungen);
  `bestaetigen-ja` sendet mit `entsperren: true`, `bestaetigen-nein` sendet
  nichts.
- Erfolg → Erfolgsmeldung mit `meldung-rueckgaengig` (4.3), Liste neu
  geladen, Auswahl wie 7.4. Fehler (z. B. 409 `buchung_gesperrt`) →
  Fehlermeldung mit der `meldung` des Servers; da der Endpunkt atomar ist,
  ändert sich nichts.

### 23.4 Status-Auswahl (`status-auswahl`)

Dialog (9) mit den Knöpfen `status-waehlen-importiert`,
`status-waehlen-vorlaeufig`, `status-waehlen-bestaetigt`,
`status-waehlen-abgeglichen` (in dieser Reihenfolge, Beschriftung wie 5).
Ein Klick schließt den Dialog und löst die Aktion aus (mit Bestätigung wie
23.3). Esc schließt ohne Wirkung.

### 23.5 Bearbeiten-Dialog (`mehrfach-dialog`)

- `mehrfach-dialog-anzahl` mit `data-anzahl` = `|A|`.
- Je Feld `f` aus `status`, `datum`, `empfaenger`, `verwendungszweck` ein
  Kontrollkästchen `mehrfach-an-<f>` (anfangs aus) und eine Eingabe
  `mehrfach-wert-<f>`: `status` als `<select>` wie 23.2, `datum` als
  `<input type="date">`, `empfaenger` als `<select>` wie 23.2 (`""` = ohne
  Empfänger), `verwendungszweck` als Texteingabe. Eine Eingabe in
  `mehrfach-wert-<f>` setzt `mehrfach-an-<f>`.
- `mehrfach-entsperren` (Kontrollkästchen, anfangs aus) ist genau dann
  sichtbar, wenn `mehrfach-an-status` gesetzt ist, `A` Buchungen mit Status
  `abgeglichen` enthält und der gewählte Status ein anderer ist.
- `mehrfach-uebernehmen` ist genau dann aktiv, wenn mindestens ein
  Kontrollkästchen `mehrfach-an-<f>` gesetzt ist, ein gesetztes `datum`
  nicht leer ist und ein sichtbares `mehrfach-entsperren` gesetzt ist. Es
  sendet **eine** Anfrage `POST /api/buchungen/mehrfach/aendern` mit
  `buchung_ids = A` und genau den angehakten Feldern (`empfaenger` →
  `empfaenger_id`, `""` → `null`; `verwendungszweck` darf leer sein), dazu
  `entsperren: true`, wenn `mehrfach-entsperren` sichtbar und gesetzt ist.
  Erfolg schließt den Dialog (Meldung, Liste wie 23.3); Fehler stehen in
  `dialog-fehler`, der Dialog bleibt offen (9).
- `mehrfach-abbrechen` und Esc schließen ohne Wirkung.


## 24. Meilenstein 13: Versionsanzeige und About-Fenster

Freigegebene Meilenstein-Definition vom 2026-11-10 (`version.md`, E-176 bis
E-180). Alles aus 1–23 gilt weiter; hier stehen nur Ergänzungen. Tests:
`tests/app/m13/`.

### 24.1 Versionsanzeige (`version-knopf`)

- In der Hauptnavigation (`navigation`) steht als letztes Element ein Knopf
  (`<button>`, `data-testid` `version-knopf`, `aria-haspopup="dialog"`) mit
  dem Text `Version <Version>`, z. B. `Version 0.01` (`<Version>` wie
  `GET /api/version` → `version`, `version.md` 1.1). „Als letztes Element“
  heißt: innerhalb von `navigation` und in Dokumentreihenfolge nach allen
  Navigationseinträgen `nav-<ziel>` (E-179).
- Er ist **kein Navigationseintrag**: keine `data-testid` mit Präfix `nav-`;
  die Liste der Navigationseinträge aus 3 (Bezeichner und Reihenfolge) bleibt
  unverändert.
- Desktop: am unteren Rand der Navigationsleiste, ohne Interaktion sichtbar
  (unterhalb des letzten Navigationseintrags, innerhalb der Leiste). Mobil:
  im eingeblendeten Menü (16.2) unten, mit einer Trefferfläche von mindestens
  44 px Höhe.
- Die Anzeige steht bereits in der **ausgelieferten Hülle** (2), also auch
  offline: Die Hülle enthält genau ein Element mit `data-testid`
  `version-knopf`, ein `<button>` mit dem Text `Version <Version>`
  (Leerraum zusammengefasst). Wo es in der Hülle steht, ist frei, solange es
  in der laufenden Oberfläche nach 24.1 in der Navigation steht. Die Version
  ist kein Text aus dem Buchbestand (`sicherheit.md` 7.2 bleibt erfüllt).

### 24.2 About-Fenster (`ueber-dialog`)

- Klick (oder Enter/Leertaste) auf `version-knopf` lädt `GET /api/version`
  und öffnet danach einen modalen Dialog (9: `role="dialog"`,
  `aria-modal="true"`, `aria-labelledby` auf die Überschrift, `data-testid`
  `ueber-dialog`, Titel „Über Kontor“). Die Angaben werden bei jedem Öffnen
  neu geladen (E-179). Mobil wird dabei zuerst das Menü geschlossen
  (`menue-knopf` mit `aria-expanded="false"`).
- Inhalt (Werte aus der Antwort von `GET /api/version`):

| `data-testid` | Inhalt |
| --- | --- |
| `ueber-version` | genau `Version <version>` |
| `ueber-build` | Release-Build (`entwicklungsstand = false`): Build-Datum (Format frei) und Commit (enthält `commit` wörtlich); sonst „Entwicklungsstand (nicht über die Release-CI gebaut)“ |
| `ueber-modus` | genau „Mock-Modus“ (`modus = mock`) oder „Echtbetrieb“ (`modus = echt`) |
| `ueber-python` | enthält `python` |
| `ueber-datenbank` | enthält `datenbank` (Pfad der aktiven Datenbank) |
| `ueber-schema` | genau `Datenbank <datenbank_schema> · Sicherung <sicherung_schema>` (Mittelpunkt U+00B7, Leerraum zusammengefasst) |
| `ueber-repository` | Link (`<a>`) mit `href` = `repository`, `target="_blank"`, `rel` mit `noopener` |

### 24.3 Bedienung

- Knopf „Schließen“ (`ueber-schliessen`) erhält beim Öffnen den Fokus (geht
  der Regel aus 9 „erstes Eingabefeld, sonst erster Knopf“ vor).
- `ueber-schliessen`, das Schließen-Kreuz (`ueber-x`, Knopf mit
  zugänglichem Namen) und Esc schließen den Dialog ohne Wirkung.
- Danach hat auf dem Desktop `version-knopf` den Fokus, mobil `menue-knopf`
  (das Menü bleibt geschlossen; geht der Regel aus 9 „das auslösende Element“
  vor, weil der Auslöser im geschlossenen Menü verborgen ist).
- Tab und Umschalt+Tab bleiben im Dialog (9). Mobil kein waagerechtes
  Scrollen (16.2), auch nicht bei geöffnetem Dialog.

### 24.4 Fehlerfall

Schlägt `GET /api/version` fehl, öffnet sich kein Dialog; es erscheint die
übliche Fehlermeldung (4.3, `data-art="fehler"`; bei 4xx mit der `meldung`
des Servers, 1 Nr. 8), bei 401 die Weiterleitung zur Anmeldung (19:
`/anmelden?weiter=<aktueller Pfad>`).

## 25. Meilenstein 15: Sammelpaket Bedienung

Freigegebene Meilenstein-Definition vom 2026-11-10 (E-181 bis E-188). Alles
aus 1–24 gilt weiter; hier stehen nur Ergänzungen. Fachliche Regeln:
`protokoll.md` 6.2a, `datenmodell.md` 18, `synchronisation.md` 20. Tests:
`tests/app/m15/`. Nicht Teil der Abnahme: Optik (Farben, Kreisel, genaue
Zeiten der Ergebnisanzeige) und das Aussehen der Diagramme (25.7).

### 25.1 Änderungsprotokoll: Rückgängig bis hierher (ergänzt 13.9)

- Jeder Eintrag `aenderung-<id>` der geladenen Liste hat zusätzlich den
  Knopf `aenderung-bis-<id>` „Bis hierher rückgängig“, solange in der
  geladenen Liste eine wirksame Änderung mit ID `≥ id` steht (die neueste
  Änderung ist stets wirksam, E-182).
- Zeiger oder Fokus auf `aenderung-bis-<id>` heben alle Einträge
  `aenderung-<k>` der Liste mit `k ≥ id` hervor (Klasse `bis-markiert`),
  alle anderen nicht; danach (Zeiger weg, Fokus weg) trägt kein Eintrag die
  Klasse.
- Klick: zuerst `bestaetigen-dialog` (9.5). `bestaetigen-ja` sendet
  `POST /api/aenderungen/rueckgaengig` mit genau `{"bis_id": id}`;
  `bestaetigen-nein` sendet nichts.
- Erfolg: Erfolgsmeldung (4.3, `data-art="erfolg"`), deren Text die Anzahl
  der zurückgenommenen Änderungen (`rueckgaengig_von` der Antwort) als Zahl
  enthält; die Liste wird neu geladen. Fehler (409, 404, 422): Fehlermeldung
  mit der `meldung` des Servers.

### 25.2 Mehrere Buchungen löschen (ersetzt die Anfrage in 7.5)

- `mehrfach-leiste` → `mehrfach-loeschen` und Kontextmenü `km-loeschen`
  (8.2): nach der Rückfrage (9.5) bei `|A| > 1` genau **eine** Anfrage
  `POST /api/buchungen/mehrfach/loeschen` mit `buchung_ids = A`
  (aufsteigend), bei `|A| = 1` wie bisher `DELETE /api/buchungen/{id}`.
  Kein weiteres `DELETE`.
- Im Änderungsprotokoll erscheint genau ein Eintrag (`mehrfach_loeschen`);
  Strg+Z (11) nimmt ihn in einem Schritt zurück (eine Anfrage
  `POST /api/aenderungen/{id}/rueckgaengig`).
- Fehler (409 `buchung_gesperrt`) → Fehlermeldung mit der `meldung` des
  Servers; nichts ändert sich.

### 25.3 Buchungen verschieben (Dialog `verschieben-dialog`)

- In der Kontoansicht eines **Bestandskontos** (`data-kontoklasse =
  "bestand"`, 22.2) gibt es `mehrfach-verschieben` in `mehrfach-leiste`,
  den Kontextmenü-Eintrag `km-verschieben` „Verschieben…“ für Buchungen
  (wirkt auf die Auswahl, 8.1) und `konto-verschieben` im Seitenkopf (auch ohne Auswahl).
  In der Ansicht einer Kategorie (kein Bestandskonto) fehlen alle drei.
- Alle öffnen `verschieben-dialog` (9) für das angezeigte Konto (Quellkonto)
  mit:
  - `verschieben-ziel`: `<select>` mit einer leeren ersten Option (Wert
    `""`, anfangs gewählt) und danach je anderem Bestandskonto (Art
    `girokonto`, `sparkonto`, `kreditkonto`, ohne das Quellkonto) einer
    Option mit Wert = Konto-ID und Beschriftung = Pfad (5), in
    Baumreihenfolge (6).
  - `verschieben-auswahl` (Radio) „die n ausgewählten Buchungen“, nur aktiv
    (nicht `disabled`) mit Auswahl.
  - `verschieben-herkunft` (Radio) „alle Buchungen dieses Kontos aus einem
    Import oder einer Synchronisation“ mit `verschieben-herkunft-wahl`
    (`<select>`, Werte = `gruppe` aus `GET /api/konten/{id}/herkunft` in
    deren Reihenfolge; eine leere erste Option mit Wert `""` ist erlaubt).
    Die Auswahl ist nur aktiv, wenn die Liste nicht leer ist.
  - `verschieben-ok` ist erst aktiv, wenn ein Ziel gewählt ist und ein
    Umfang (bei `verschieben-herkunft` mit gewählter Gruppe). Es sendet
    genau eine Anfrage `POST /api/buchungen/mehrfach/verschieben` mit
    `von_konto_id` = Quellkonto, `nach_konto_id` = Ziel und entweder
    `buchung_ids` = Auswahl (aufsteigend) oder `gruppe`.
  - Esc schließt ohne Wirkung (9).
- Erfolg: Der Dialog schließt, Erfolgsmeldung (4.3) mit
  `meldung-rueckgaengig`, Liste neu geladen (die verschobenen Buchungen
  fehlen). Rückgängig wie jede Aktion (11). Fehler stehen in
  `dialog-fehler`; der Dialog bleibt offen.
- Trägt das Quellkonto eine IBAN, weist der Dialog darauf hin, dass künftige
  Umsätze weiter in diesem Konto landen, bis das Synchronisationskonto
  geändert wird (Text frei, kein Prüfmerkmal).

### 25.4 Zuordnung unbekannter Bankkonten und Kontoeinstellungen

**Nach jedem Lauf aus der Oberfläche** (`sync-starten`, PIN-Dialog 25.5,
Synchronisationsseite): Für jedes Bankkonto in `uebersprungen` mit `status
= "nicht_zugeordnet"` öffnet sich nacheinander (Reihenfolge der Liste) der
Dialog `zuordnung-dialog` (9). Sein Text nennt Name und IBAN des
Bankkontos (IBAN mit oder ohne Leerzeichen-Gruppen). Inhalt:

- Radio `zuordnung-vorhanden` mit `zuordnung-konto` (`<select>`, Wert =
  Konto-ID; Optionen: alle Bestandskonten ohne IBAN, Beschriftung = Pfad).
  Gibt es ein Bestandskonto ohne IBAN mit genau dem Namen des Bankkontos,
  ist `zuordnung-vorhanden` gewählt und dieses Konto vorgewählt.
- Radio `zuordnung-neu` mit `zuordnung-name` (Texteingabe, Vorgabe: Name des
  Bankkontos) und `zuordnung-art` (`<select>` mit `girokonto`, `sparkonto`,
  `kreditkonto`; Vorgabe: `art` des Bankkontos).
- `zuordnung-ok`: bei `zuordnung-vorhanden` `PATCH /api/konten/{id}` mit
  genau `{"iban": <iban>}`, bei `zuordnung-neu` `POST /api/konten` mit
  `{name, art, iban}`; danach der nächste Dialog. Fehler stehen in
  `dialog-fehler`, der Dialog bleibt offen.
- `zuordnung-spaeter` überspringt dieses Bankkonto (keine Anfrage), Esc
  bricht die ganze Reihe ab (keine Anfrage).
- Wurde in der Reihe mindestens ein Bankkonto zugeordnet, startet die
  Oberfläche nach dem letzten Dialog bzw. dem Abbruch sofort einen weiteren
  Lauf (`POST /api/sync` `{}`); für ihn gilt dasselbe.

**Synchronisationsseite** `/sync` (ergänzt 13.10): Abschnitt
`sync-nicht-zugeordnet` mit je einem Eintrag `nicht-zugeordnet-<iban>` für
die Bankkonten mit `status = "nicht_zugeordnet"` aus `uebersprungen` des
letzten Laufs (`GET /api/sync/status` → `letzter_lauf`), deren IBAN kein
Konto trägt, jeweils mit dem Knopf `zuordnen-<iban>` (öffnet
`zuordnung-dialog` für dieses Bankkonto). Ohne solche Bankkonten ist der
Abschnitt leer oder fehlt.

**Kontoeinstellungen** (Dialog `konto-einstellungen`), erreichbar über den
Kontextmenü-Eintrag `km-konto-einstellungen` „Einstellungen…“ für Konten und
Kategorien (8.2) und den Knopf `konto-einstellungen-oeffnen` im Seitenkopf
der Kontoansicht:

| Element | Inhalt |
| --- | --- |
| `einstellungen-name` | Texteingabe, vorbelegt mit `name` |
| `einstellungen-sync` | nur bei Bestandskonten: `<select>` „Synchronisationskonto“ mit `""` (keins), je bekanntem Bankkonto (IBANs aus `GET /api/sync/konten` sowie `konten` und `uebersprungen` des letzten Laufs) einer Option mit Wert = IBAN, und `"*"` „Andere IBAN eingeben…“. Optionen von IBANs, die ein **anderes** Konto trägt, sind `disabled`. Vorgewählt ist die IBAN des Kontos bzw. `""` |
| `einstellungen-iban` | Texteingabe, sichtbar genau bei `einstellungen-sync = "*"` |
| `einstellungen-eroeffnet` | `<input type="date">`, vorbelegt mit `eroeffnet_am` (leer bei null) |
| `einstellungen-geschlossen` | Kontrollkästchen, vorbelegt mit `geschlossen` |
| `einstellungen-notiz` | Texteingabe (auch mehrzeilig), vorbelegt mit `notiz` |

- `einstellungen-speichern` sendet `PATCH /api/konten/{id}` mit **genau den
  geänderten Feldern** (`name`, `iban` – `""` → `null`, Wert des Selects
  bzw. bei `"*"` die Eingabe –, `eroeffnet_am` – leer → `null` –,
  `geschlossen`, `notiz`). Ohne Änderung schließt der Dialog ohne Anfrage.
  Erfolg schließt den Dialog; Fehler (z. B. 422 `iban_ungueltig`, 409
  `iban_existiert`) stehen in `dialog-fehler`, der Dialog bleibt offen.
- Esc schließt ohne Wirkung (9).

### 25.5 PIN-Dialog gesperrt mit Statusanzeige (ergänzt 15.4)

- Nach `pin-senden` bzw. Enter in `pin-eingabe` ist `pin-dialog` bis zum
  Ergebnis gesperrt: `data-gesperrt="ja"` und `aria-busy="true"` am Dialog;
  `pin-eingabe`, `pin-senden` und `pin-abbrechen` (Knopf „Abbrechen“ des
  Dialogs, ab M15 mit dieser Kennung) sind `disabled`; Esc schließt nicht. Sonst trägt der Dialog `data-gesperrt="nein"`.
- `pin-dialog-status` (`role="status"`) zeigt die Phase in `data-phase`:

| `data-phase` | Text (Inhalt der Zahlen frei) |
| --- | --- |
| `pin` | „Übergebe die PIN …“ |
| `verbinden` | „Verbinde mit der Bank …“ |
| `abruf` | „Rufe Umsätze ab … (n von m: Konto)“ – aus dem laufenden Lauf in `GET /api/sync/status` (`letzter_lauf.konten`), höchstens etwa jede Sekunde abgefragt |
| `tan` | „Die Bank verlangt eine TAN-Freigabe.“ |
| `fertig` | Ergebnistext (neue Buchungen, nicht zugeordnete Bankkonten) |
| `fehler` | Fehlertext |

  Während `pin`, `verbinden` und `abruf` dreht ein Kreisel (bei
  `prefers-reduced-motion: reduce` steht er still).
- PIN falsch oder fehlend (Lauf mit `fehler.code` `bank_pin_falsch` bzw.
  `bank_pin_fehlt`): Der Dialog bleibt offen und wird entsperrt
  (`data-gesperrt="nein"`), `dialog-fehler` meldet „Die Bank hat die PIN
  abgelehnt. Bitte erneut eingeben.“, und der Fokus steht in `pin-eingabe`.
- Sonst schließt der Dialog nach kurzer Anzeige des Ergebnisses (etwa 1 s,
  bei Fehler oder TAN etwa 2 s). Danach Meldung wie bisher (15.4, TAN mit
  Link `sync-tan-link`), dann 25.4.

### 25.6 Vorschläge je Zeile (ergänzt 7.2 und 7.3)

Für Zeilen mit `vorschlag ≠ null`:

- Die Kategoriezelle zeigt den Pfad der vorgeschlagenen Kategorie
  (`vorschlag.kategorie_id`) in einem Element mit der Klasse
  `vorschlag-kategorie`.
- `vorschlag-marke` trägt `data-quelle` (= `vorschlag.quelle`) und
  `data-sicherheit` (= `vorschlag.sicherheit` in Promille, leer ohne
  Sicherheit). Text: bei `lernmodell` die Sicherheit in ganzen Prozent,
  kaufmännisch gerundet `⌊(Promille + 5) / 10⌋` mit Prozentzeichen („87 %“,
  Leerzeichen auch geschützt), bei `regel` „Regel“, bei
  `standardkategorie` „Empf.“. `title` bzw. `aria-label` nennen die Quelle
  ausführlich: „Vorschlag des Lernmodells, Sicherheit 87 %“, „Vorschlag der
  Regel „<Name>““, „Vorschlag: Standardkategorie des Empfängers“.
- `vorschlag-annehmen-<id>` und `vorschlag-ablehnen-<id>` bleiben in der
  Zelle (7.2). Desktop: bei Zeiger, Fokus oder Auswahl der Zeile voll
  sichtbar; mobil immer.
- Einzelheiten (`panel-details` bzw. mobiler Dialog, 7.3): Abschnitt
  `details-vorschlag` mit `data-quelle` zeigt die vorgeschlagene Kategorie,
  die Quelle mit Sicherheit und das vorherige Konto
  (`vorher_konto_id`, Pfad) sowie die Knöpfe `details-vorschlag-annehmen`
  und `details-vorschlag-ablehnen` (wie 7.2). Dazu die Liste
  `details-vorschlag-kandidaten` mit den Kandidaten des Lernmodells für diese
  Buchung (`POST /api/lernmodell/vorhersage` mit `{buchung_id}`, ohne
  Wirkung) mit einer Sicherheit ab 1 % (≥ 10 Promille). Je Kandidat außer
  dem vorgeschlagenen gibt es den Knopf `details-kandidat-<kategorie_id>`
  „Übernehmen“: `PUT /api/buchungen/{id}/kategorie` mit dieser Kategorie.

### 25.7 Berichtsgrafiken (ergänzt 13.6)

- `bericht-diagramm` bleibt `role="img"` mit nicht leerem `aria-label`.
  Ohne gewählte Konten oder ohne Daten zeigt es einen Hinweistext. Mit Daten
  ist es ein interaktives Diagramm (Plotly) mit einer Stufenlinie je Konto
  (bei mehreren Konten zusätzlich „Summe“), Legende, Tooltip mit Betrag und
  Zoom; `data-reihen` = Anzahl der gewählten Konten (ohne „Summe“).
- Einnahmen und Ausgaben: Der Abschnitt hat einen Knopf mit dem
  zugänglichen Namen „berechnen“ (Groß-/Kleinschreibung frei); danach
  erscheint über der Tabelle `bericht-ea-diagramm` (`role="img"`, nicht
  leeres `aria-label`) mit Balken für Einnahmen (positiv) und Ausgaben
  (negativ) je Zeitraum und einer Linie für den Saldo
  (`GET /api/berichte/einnahmen-ausgaben`).
- Achsen und Tooltips zeigen Beträge im Format 5 („1.234,56 €“); Werte und
  Achsenteilung beruhen auf ganzen Cent.
- Alle Ressourcen kommen von Kontor selbst (`/oeffentlich/…`), keine
  Anfrage an eine andere Herkunft (1 Nr. 3, 21); die CSP bleibt unverändert
  (`sicherheit.md` 6). Ist die Grafikbibliothek nicht ladbar (offline),
  erscheint das bisherige einfache Diagramm (weiter mit `role="img"` und
  `aria-label`).

## 26. Meilenstein 16: Begründung wiederkehrender Buchungen

Freigegebene Meilenstein-Definition vom 2026-11-11, Abschnitt 3 (E-192,
E-196). Alles aus 1–25 gilt weiter; hier stehen nur Ergänzungen. Fachliche
Regeln: `wiederkehrend.md` 2.2 und 8. Tests: `tests/app/m16/`. Nicht Teil
der Abnahme: Wortlaut der Sätze (`text`), Gestaltung (Farben,
Hervorhebungsdauer) und ob Alt+Rechtsklick in einer Desktopumgebung den
Browser erreicht (manche Fenstermanager fangen ihn ab; die Tests lösen das
Menü mit Alt über Playwright aus).

### 26.1 Begründungsdialog (`wiederkehrend-begruendung`)

Dialog `wiederkehrend-begruendung` (`role="dialog"`) mit den Daten aus `GET
/api/buchungen/{id}/wiederkehrend` (Stichtag: Vorgabe *heute*):

- `wk-urteil` mit `data-urteil` = Gesamturteil. Text beginnt mit
  „Wiederkehrend? Ja“ (bei `wiederkehrend`) bzw. „Wiederkehrend? Nein“
  (sonst), gefolgt von einer kurzen Erläuterung. Darunter steht der Stichtag
  (Datum nach 5).
- Ohne Einträge: `wk-text` mit dem `text` der Antwort.
- Je Eintrag `wk-eintrag` mit `data-urteil`, Gruppenbeschriftung,
  `wk-eintrag-text` (Satz des Eintrags) und einem Hinweis auf Gruppengröße
  und Toleranz.
- Je Eintrag eine einklappbare Liste `wk-buchungen` mit allen Buchungen der
  Gruppe: Zeilen `wk-buchung` mit `data-id` und `data-rolle`, Spalten Datum,
  Betrag und Rolle („Glied n“, „zusätzlich“, „vor Beginn“, „–“). Die
  angefragte Buchung ist mit „(diese Buchung)“ gekennzeichnet und hat die
  Klasse `wk-betroffen`.
- Je geprüftem Rhythmus ein einklappbarer Abschnitt `wk-rhythmus-<rhythmus>`
  mit Kopfzeile (Länge, Mindestanzahl, erfüllt/nicht erfüllt) und dem
  Kettenprotokoll als nummerierte Liste von `wk-schritt` mit
  `data-ergebnis` und `data-grund`. Der zuletzt geprüfte Rhythmus ist
  aufgeklappt. Schritte, an denen die angefragte Buchung beteiligt ist (als
  `von`, `vorgaenger`, übersprungen oder `fremd`), haben die Klasse
  `wk-betroffen`.
- `wk-ausgeschlossen` je ausgeschlossenem Konto.
- `wk-schliessen` „Schließen“ und Escape schließen den Dialog. Der Fokus
  kehrt zum Auslöser zurück.

### 26.2 Kontoblatt: versteckter Eintrag (ergänzt 8.2 und 12.3)

- Rechtsklick auf eine Buchung **mit gedrückter Alt-Taste**, ebenso
  Alt+Umschalt+F10 und Alt+Menütaste: Das Kontextmenü (`kontextmenue`)
  enthält zusätzlich als letzten Eintrag `km-wiederkehrend` „Warum (nicht)
  wiederkehrend?“. Er ist nur bei genau einer gewählten Buchung aktiv und
  öffnet 26.1 für diese Buchung.
- Ohne Alt fehlt der Eintrag. Das Menü ist sonst unverändert (8.2).
- Befehlspalette: Ist auf einer Kontoansicht genau eine Buchung gewählt, gibt
  es den Eintrag `befehl-wiederkehrend-warum` „Markierte Buchung: Warum
  (nicht) wiederkehrend?“, sonst fehlt er. Das ist der Weg auf dem
  Smartphone.

### 26.3 Seite „Wiederkehrende Buchungen“ (ergänzt 13.5)

- Jede Zeile `serie-<schluessel>` ist fokussierbar und hat als letzte Zelle
  einen Knopf `wk-menue-<schluessel>` („…“, `aria-haspopup="menu"`,
  `aria-label` mit dem Empfängernamen). Die Kopfzeile hat dafür eine Spalte,
  deren Beschriftung nur für Screenreader sichtbar ist. Die Testkennung
  beginnt bewusst nicht mit `serie-`.
- Dasselbe Menü (`kontextmenue`) öffnen der Knopf, Rechtsklick auf die Zeile,
  Umschalt+F10 oder Menütaste auf der fokussierten Zeile und lange Berührung
  (mobil). Einträge:
  - `km-serie-begruendung` „Warum wiederkehrend?“ öffnet 26.1 für die jüngste
    Buchung der Serie (letzte ID in `buchung_ids`).
  - `km-serie-springen` „Letzte Buchung im Kontoblatt zeigen“ öffnet
    `/konten/<konto_id>?buchung=<id>` mit derselben Buchung (26.4).
- Bei einer leeren Liste enthält `wiederkehrend-tabelle` keine Zeilen
  `serie-<schluessel>`, und außerhalb von Seitenkopf (mit „Jetzt prüfen“),
  Summenzeile und Tabellenkopf steht als Text nur der Hinweis „Keine
  wiederkehrenden Buchungen erkannt.“; nirgends erscheint „null“ (E-204).
  Seitenkopf, Knopf und Summenzeile bleiben wie bisher.

### 26.4 Sprungziel im Kontoblatt (ergänzt 7.1)

- Der Query-Parameter `buchung=<id>` der Kontoansicht ist kein Filter. Nach
  dem Laden lädt die Ansicht bei Bedarf weitere Seiten nach, bis die Buchung
  in der Liste ist oder alle Seiten geladen sind.
- Dann ist genau diese Buchung gewählt (`aria-selected="true"`) und
  fokussiert, in den sichtbaren Bereich gerollt (ab M21: in die vertikale Mitte, 31.4) und kurz hervorgehoben. Der
  Parameter wird aus der Adresse entfernt (`replaceState`). Die übrigen
  Filterparameter bleiben.
- Ist die Buchung mit den Filtern nicht in der Liste, erscheint ein Hinweis
  (Meldung 4.3 mit `data-art="hinweis"`, E-196), und nichts ist gewählt.
- Ein ungültiger Wert (keine Ganzzahl) wird ignoriert.

## 27. Meilenstein 17: Tabs der Ansichten und Gehe zur Gegenbuchung

Freigegebene Meilenstein-Definition vom 2026-11-11 (Feature
`tabs-gegenbuchung`, dort als M16 bezeichnet, E-199 bis E-202). Alles aus
1–26 gilt weiter; hier stehen nur Ergänzungen. Reine Oberfläche: keine
neuen Endpunkte, Felder oder Konfigurationsschlüssel (`openapi.yaml`
unverändert), kein fachlicher Zustand, nichts im Protokoll oder in der
Sicherung. Tests: `tests/app/m17/`.

### 27.1 Tabs der Ansichten

#### 27.1.1 Grundsatz

- Jede Ansicht (jede Route aus 3, auch die Kontoansicht einer Kategorie und
  „Nicht gefunden“) wird in einem Tab gezeigt. Ein Tab gehört zu genau
  einem **Pfad ohne Abfrageteil**; `/konten/3?status=offen` und
  `/konten/3` sind derselbe Tab.
- Höchstens ein Tab je Pfad. Wird eine Ansicht angefordert, deren Tab offen
  ist, wird dieser Tab aktiv; sonst entsteht ein neuer Tab **rechts neben
  dem bisher aktiven** und wird aktiv.
- Genau ein Tab ist aktiv. Im Hauptbereich steht nur die Ansicht des
  aktiven Tabs; jede `data-testid` einer Ansicht kommt im Dokument
  höchstens einmal vor (inaktive Tabs hängen nicht im Dokument).
- Die URL in der Adresszeile ist immer die des aktiven Tabs (Pfad und
  dessen aktueller Abfrageteil).

#### 27.1.2 Tab-Leiste

- `tab-leiste` (`role="tablist"`, mit `aria-label`) steht über dem
  Hauptbereich, außerhalb von `hauptbereich`, sichtbar, sobald mindestens
  ein Tab offen ist – auf Desktop und mobil. Passen nicht alle Tabs in die
  Breite, ist die Leiste waagrecht scrollbar; der aktive Tab wird in den
  sichtbaren Bereich gebracht.
- Je Tab ein Element `tab` (`role="tab"`) mit
  - `data-pfad` = Pfad ohne Abfrageteil,
  - `aria-selected="true"` für den aktiven, sonst `"false"`,
  - einem Link `tab-titel` (`href` = Pfad samt gespeichertem Abfrageteil)
    mit dem Titel des Tabs,
  - einem Knopf `tab-schliessen` mit `aria-label`, das den Titel enthält.
- Titel: in der Kontoansicht (Konto oder Kategorie) der Name des Kontos;
  sonst der Seitentitel der Ansicht (3, z. B. „Finanzübersicht“, „Nicht
  gefunden“), nie leer.
- Reihenfolge der Tabs = Reihenfolge des Öffnens nach 27.1.1.

#### 27.1.3 Zustand eines offenen Tabs

- Solange die Seite geöffnet ist, behält ein offener Tab beim Wechsel zu
  einem anderen Tab seinen vollständigen Zustand: Filter und Sortierung
  (samt Abfrageteil der URL), Auswahl und Fokuszeile (7.4), nachgeladene
  Seiten der Buchungsliste, aufgeklappte Filterleiste, Inhalt der Panels und
  Scrollstände.
- **Wechsel über den Tab** (Klick auf `tab-titel`, Leertaste auf dem
  fokussierten Tab) sowie **Zurück/Vor** des Browsers zeigen den Tab genau
  in diesem Zustand, ohne ihn neu aufzubauen.
- **Anfordern über Navigation oder Link** (Navigationsleiste, Links und
  Zeilen in Ansichten, Befehlspalette, „Gehe zur Gegenbuchung“) ohne
  Abfrageteil aktiviert den offenen Tab mit Filtern, Sortierung, Auswahl und
  Scrollstand; die Filterleiste der Kontoansicht beginnt dabei aber
  eingeklappt (23.1, E-172). Das gilt auch, wenn der angeforderte Tab
  bereits aktiv ist und eigene Filter hat.
- Ein Link **mit** Abfrageteil, der sich vom gespeicherten unterscheidet,
  baut die Ansicht mit diesem Abfrageteil neu auf (frischer Zustand, Filter
  aus der URL).
- Dieselbe Ansicht mit exakt der aktuellen URL erneut anfordern baut sie wie
  bisher neu auf.
- Ein **direkter Aufruf** (Adresszeile, Neuladen, Lesezeichen) zeigt immer
  genau den Abfrageteil der URL, auch wenn für den Pfad ein Tab mit anderen
  Filtern gespeichert ist.

#### 27.1.4 Aktualität

- Eine Änderung am Buchbestand aus irgendeinem Tab (alle Operationen nach
  7.4) wirkt in den anderen Tabs spätestens beim nächsten Zeigen: Ein bereits
  geladener anderer Tab zeigt dann den Stand des Servers (Zahlen, Beträge,
  Zeilen) und behält Filter, Sortierung und – soweit die Buchungen noch
  vorhanden sind – die Auswahl.
- Offline (18) werden in inaktiven Tabs keine veralteten Daten gezeigt;
  nach der Rückkehr laden sie beim Zeigen neu.

#### 27.1.5 Schließen und Wiederöffnen

- Schließen über `tab-schliessen`, Mittelklick auf den Tab oder Entf auf
  dem fokussierten Tab. Ein inaktiver Tab verschwindet, der aktive bleibt
  unverändert.
- Wird der aktive Tab geschlossen, wird sein **rechter Nachbar** aktiv, ohne
  rechten Nachbarn der linke; war es der letzte Tab, öffnet die
  Finanzübersicht (`/`) in einem neuen Tab. Die URL folgt dem neuen aktiven
  Tab.
- Ein geschlossener Tab hat keinen Zustand mehr; später angefordert öffnet
  er als neuer Tab mit frischem Zustand (keine Auswahl, keine Filter außer
  denen der angeforderten URL).

#### 27.1.6 Speicherung

- Die Liste der offenen Tabs (Pfad, Abfrageteil, Titel), ihre Reihenfolge
  und der aktive Tab werden im Browser gespeichert (Gerätezustand wie Layout
  und Design, kein fachlicher Zustand, nicht im Protokoll und nicht in der
  Sicherung, E-141). Gespeichert werden höchstens 40 Tabs. Ort und Format
  der Speicherung sind frei.
- Nach dem Neuladen oder einem neuen Aufruf der Anwendung im selben Browser
  stehen die gespeicherten Tabs wieder in der Leiste. Aktiv ist der Tab der
  aufgerufenen URL (27.1.3, direkter Aufruf); die übrigen Tabs laden ihre
  Ansicht erst, wenn sie aktiv werden, und zwar mit ihrem gespeicherten
  Abfrageteil.
- Auswahl, Fokus, nachgeladene Seiten und Scrollstände werden nicht
  gespeichert.
- Ist der Browser-Speicher nicht verfügbar oder sein Inhalt ungültig,
  beginnt die Oberfläche ohne gespeicherte Tabs und funktioniert sonst
  unverändert.

#### 27.1.7 Tastatur und Zugänglichkeit

- In der Tab-Leiste: Pfeil rechts/links bewegen den Fokus zum
  nächsten/vorigen Tab (umlaufend), Pos1/Ende zum ersten/letzten; Leertaste
  und Enter aktivieren den fokussierten Tab; Entf schließt ihn. Nur der
  aktive Tab ist per Tabulatortaste erreichbar.
- Strg-/Umschalt-/Mittelklick auf `tab-titel` öffnet den Link wie ein
  Browser (bzw. schließt bei Mittelklick nach 27.1.5) und wechselt nicht den
  Tab.

### 27.2 Kontextmenü „Gehe zur Gegenbuchung“ (ergänzt 8.2 und 23.3)

| testid / Text | aktiv bei | Wirkung |
| --- | --- | --- |
| `km-gegenbuchung` „Gehe zur Gegenbuchung“, bei mehreren Gegenseiten „Gehe zur Gegenbuchung…“ | genau eine gewählte Buchung mit mindestens einer Gegenseite | unten |

- Der Eintrag steht im Kontextmenü jeder Buchungszeile der Kontoansicht
  (Konto und Kategorie) direkt nach „Bearbeiten…“ (`km-mehrfach`);
  „Löschen…“ bleibt der letzte Eintrag. Bei mehreren gewählten Buchungen
  oder ohne Gegenseite ist er vorhanden, aber deaktiviert
  (`aria-disabled="true"`).
- **Gegenseiten** einer Buchung in der Ansicht von Konto K sind die Konten
  aller Splits mit `konto_id` ≠ K – Bestandskonten wie Kategorien – in der
  Reihenfolge der Splits, jedes Konto nur einmal.
- Bedienbar wie alle Kontextmenüs (8.1): Rechtsklick,
  Umschalt+F10/Kontextmenü-Taste, lange Berührung (mobil, 16.4).
- **Genau eine Gegenseite G:** Die Kontoansicht `/konten/<G>` wird nach
  27.1.1/27.1.3 angefordert (offener Tab wird aktiv, sonst neuer Tab). Dort
  ist danach genau diese Buchung ausgewählt (`aria-selected="true"` auf
  `buchung-<id>`, `auswahl-anzahl` 1), sie hat den Fokus und ist sichtbar.
- **Mehrere Gegenseiten:** An derselben Stelle öffnet ein Untermenü
  (`role="menu"`) mit je einem Eintrag `km-gegenbuchung-<konto_id>` je
  Gegenseite in der obigen Reihenfolge; der Text enthält den Namen des
  Kontos. Der erste Eintrag hat den Fokus; Pfeiltasten, Enter und Esc wie in
  jedem Kontextmenü. Die Wahl eines Eintrags wirkt wie bei genau einer
  Gegenseite mit diesem Konto.
- Ist die Buchung in der Zielansicht nicht unter den geladenen Zeilen,
  werden weitere Seiten geladen, bis sie da ist. Wird sie durch Filter des
  Ziel-Tabs ausgeblendet, werden alle Filter außer der Sortierung
  zurückgesetzt (`filter-anzahl` = 0, URL ohne Filter), und es erscheint
  eine Meldung (4.3) mit `data-art="hinweis"` und dem Text „Filter
  zurückgesetzt, damit die Buchung sichtbar ist.“
- Der Sprung ändert keine Daten: nur Lesezugriffe, kein Eintrag im
  Änderungsprotokoll, kein Eintrag auf dem Rückgängig-Stapel (11).

### 27.3 Fehlerfälle

- Gegenkonto inzwischen gelöscht: Die Zielansicht zeigt
  `seite-nicht-gefunden` in ihrem Tab.
- Buchung inzwischen gelöscht oder nicht mehr auf dem Gegenkonto: Meldung
  mit `data-art="fehler"` und dem Text „Die Buchung ist in dieser Ansicht
  nicht enthalten.“; die Zielansicht bleibt ohne Auswahl offen.

### 27.4 Abgrenzung

- Keine Begrenzung der Zahl offener Tabs in der laufenden Seite, kein „Alle
  schließen“, kein Ziehen von Tabs.
- Nicht Teil der Abnahme (E-201): Scrollstände und Inhalt der Panels beim
  Wechsel, das Verhalten offline (27.1.4 zweiter Punkt), Aussehen und
  Position des Untermenüs.

## 28. Meilenstein 18: Dokumente an Buchungen

Übernahme von Abschnitt 5 der Definition M18 (E-206). Verweise auf die
Abschnitte 1–4 meinen `dokumente.md`, Verweise auf 5.x diesen Abschnitt 28.x.
Prüfmerkmale: E-209.

Alle Änderungen laufen wie andere Operationen der Oberfläche (Rückgängig mit Strg+Z über
das Protokoll, Erfolgsmeldung, Neuladen mit dem Stand des Servers). Neue Moduldatei in
der Service-Worker-Liste (eigener Test der Hülle bleibt grün).

### 28.1 Marke je Zeile

- Zeilen von Buchungen mit `belege` haben einen Knopf `beleg-marke-<buchung_id>` mit Text
  „📎“ (bei mehr als einem Dokument „📎<n>“), `data-anzahl` = Anzahl, `title` =
  Dateinamen durch Zeilenumbruch getrennt, `aria-label` „<n> Dokument(e) ansehen“.
  Desktop: am Ende der Zelle Verwendungszweck; mobil (Spalte ausgeblendet): am Ende der
  Empfängerzelle. Ohne Dokumente keine Marke.
- Klick auf die Marke öffnet den Betrachter (5.4) mit dem ersten Dokument der Buchung;
  die Marke ist kein Ziehgriff.

### 28.2 Einzelheiten (`panel-details`, mobil Dialog)

Abschnitt `details-dokumente` (`data-anzahl`, `data-buchung-id`), Überschrift
„Dokumente“:

- je Dokument `details-dokument-<dokument_id>` mit Knopf `dokument-ansehen-<id>`
  (Symbol + Dateiname; öffnet den Betrachter bei diesem Dokument, Blättern über alle
  Dokumente der Buchung) und `dokument-loesen-<id>` („×“, löst von dieser Buchung;
  Meldung „„<name>“ von der Buchung gelöst.“ bzw. bei der letzten Verknüpfung
  „„<name>“ entfernt.“);
- ohne Dokumente der Text „Keine Dokumente. Datei hierher ziehen oder anhängen.“;
- Knöpfe `dokument-anhaengen` „Datei anhängen…“ (Dateiauswahl, mehrere Dateien,
  `accept` mit PDF, `.eml`, JPEG, PNG, WebP), nur mobil `dokument-foto` „📷 Foto
  aufnehmen“ (Dateiauswahl `accept="image/*"` mit `capture="environment"`), `dokument-mail`
  „E-Mail…“ (5.3).
- Die Dateiauswahl ist ein verstecktes `<input type="file">`
  (`dokument-datei-eingabe` bzw. `dokument-kamera-eingabe`), das sofort geöffnet wird
  (Playwright: `expect_file_chooser`). Je gewählter Datei ein Upload und **eine eigene
  Änderung** (einzeln rückgängig); Quelle `upload` bzw. `kamera`. Fehler (Typ unbekannt,
  zu groß) erscheinen als Fehlermeldung; die übrigen Dateien werden trotzdem hochgeladen.
- Kamera: Fotos werden vor dem Hochladen im Browser auf höchstens 2400 px Kantenlänge als
  JPEG verkleinert (ein JPEG ≤ 2400 px und unter 2 MiB bleibt unverändert).

### 28.3 E-Mail anhängen (`mail-auswahl-dialog`)

- Dialog (`role="dialog"`) mit Suchfeld `mail-auswahl-suche`, Liste `mail-auswahl-liste`
  (`role="listbox"`), Einträge `mail-auswahl-<nachricht_id>` (`role="option"`, Betreff
  oder „(ohne Betreff)“, Absender, Empfangszeit), neueste zuerst, höchstens 200 sichtbar;
  Suche filtert Absender und Betreff (ohne Groß-/Kleinschreibung).
  `mail-auswahl-abbrechen`, `mail-auswahl-schliessen`.
- Ohne gespiegelte Mails: „Keine abgerufenen E-Mails. Postfächer richtest du unter
  Einstellungen ein.“; keine Treffer: „Keine passende E-Mail.“
- Klick oder Enter/Leertaste auf einen Eintrag hängt die Mail an (2.2) an alle Ziel-
  Buchungen und schließt den Dialog; Fehler im Dialog (`dialog-fehler`).

### 28.4 Betrachter (`dokument-betrachter`)

- Dialog mit Titel = Dateiname, `data-typ` = `mime_typ`, `data-dokument-id`;
  Leiste: `betrachter-voriges` / `betrachter-naechstes` (Blättern zyklisch, auch mit
  Pfeil links/rechts außerhalb von Eingabefeldern) und `betrachter-zaehler` („i / n“) –
  nur sichtbar bei mindestens zwei Dokumenten; `betrachter-herunterladen` (Link auf
  `…/inhalt?herunterladen=true` mit `download`); `betrachter-schliessen`. (Hat der
  PDF-Rahmen den Fokus, erreicht Esc die Seite nicht; Tests schließen mit dem Knopf.)
- **PDF:** Rahmen `betrachter-pdf` mit `src="/api/dokumente/<id>/inhalt"`; mobil
  zusätzlich Link `betrachter-oeffnen` „PDF öffnen“ (`target="_blank"`).
- **Bild:** `betrachter-bild` (`<img src=…/inhalt>`, `alt` = Dateiname); Klick schaltet
  die vergrößerte Ansicht (Klasse `gross`) um.
- **E-Mail:** Bereich `betrachter-mail` mit Kopf `mail-kopf` (`mail-von`, An/Cc/Datum,
  `mail-betreff`); bei HTML zunächst der Rahmen `mail-html` (`src=…/mail/html`, Attribut
  `sandbox="allow-popups allow-popups-to-escape-sandbox"`, `referrerpolicy="no-referrer"`)
  und Umschalter `mail-ansicht-umschalten` („Als Text zeigen“ ↔ „Formatiert zeigen“), sonst
  bzw. umgeschaltet `mail-text` (`<pre>` mit `text`); Liste `mail-anhaenge` der Anhänge mit
  `inline = false`: `mail-anhang-<nr>`, bei PDF/JPEG/PNG/WebP/GIF ein Knopf
  `mail-anhang-ansehen-<nr>` (zeigt den Anhang im Betrachter; `betrachter-zur-mail` führt
  zurück, Blättern ist dabei ausgeblendet), immer `mail-anhang-laden-<nr>` „Herunterladen“.
- **Hängt an:** unter jedem Dokument (nicht unter Mail-Anhängen) der Abschnitt
  `betrachter-buchungen` (`data-anzahl`), „Hängt an 1 Buchung“ / „Hängt an <n>
  Buchungen“, je Buchung `betrachter-buchung-<id>` mit `betrachter-zur-buchung-<id>`
  (Datum · Empfänger · Betrag; schließt den Betrachter und springt zur Buchung in der
  Kontoansicht des ersten Bestandskontos ihrer Splits, sonst ihres ersten Kontos – wie
  „Gehe zur Gegenbuchung“, `oberflaeche.md` 27.2) und `betrachter-loesen-<id>` (löst; war
  es die letzte Buchung, schließt der Betrachter), dazu `betrachter-verknuepfen` „Mit
  weiteren Buchungen verknüpfen…“.
- **Verknüpfen (`verknuepfen-dialog`):** Suchfeld `verknuepfen-suche` (Suche wie
  `suche` der Buchungsliste über alle Konten, neueste zuerst, höchstens 50 Treffer,
  verzögert ca. 250 ms), Liste `verknuepfen-liste` mit Kästchen
  `verknuepfen-buchung-<id>` (schon verknüpfte angehakt und gesperrt, Zusatz „(schon
  verknüpft)“), `verknuepfen-ok` (gesperrt ohne neue Auswahl; Text „Verknüpfen“ bzw. „Mit
  <n> Buchungen verknüpfen“), `verknuepfen-abbrechen`, `verknuepfen-schliessen`. OK →
  2.6, Dialog schließt, der Abschnitt „Hängt an“ zeigt die neue Anzahl.

### 28.5 Kontextmenü der Buchungsliste (ergänzt 8.2, 23.3)

Nach „Gehe zur Gegenbuchung“ und vor „Auf anderes Konto verschieben…“:

- `km-dokument-anhaengen` „Dokument anhängen…“ – Dateiauswahl, an **alle gewählten**
  Buchungen (ein Dokument, mehrere Verknüpfungen);
- nur mobil `km-dokument-foto` „Foto aufnehmen…“ – Kamera, an alle gewählten;
- `km-dokument-mail` „E-Mail anhängen…“ – 5.3, an alle gewählten;
- `km-dokumente-ansehen` „Dokumente ansehen“ – Betrachter mit den Dokumenten der
  Buchung; **aktiv nur bei genau einer gewählten Buchung mit Dokumenten**, sonst
  `aria-disabled="true"`. *(Abweichung von D-123, das „für alle gewählten Buchungen“
  nannte.)*
- Mobil über das lange Drücken (16.4) dieselben Einträge.

### 28.6 Dateien auf eine Zeile ziehen (Desktop)

- Dateien aus dem Betriebssystem (Drag-Daten mit Typ `Files`) über einer Zeile: die Zeile
  trägt `data-ablage="ja"`, solange sie Ziel ist. Ablegen lädt jede Datei hoch (5.2) an
  diese Buchung; ist die Zeile gewählt und sind mehrere Buchungen gewählt, an **alle
  gewählten**.
- Ziehen ohne Dateien (bestehendes Drag and Drop von Buchungen, M8) ist unverändert.
  Ablage ohne Datei-Inhalt → Hinweis „Hier lassen sich nur Dateien ablegen.“
- Test: `drop`-Ereignis mit einem `DataTransfer`, das eine `File` enthält, auf die Zeile
  auslösen (`dragover` vorher).


## 29. Meilenstein 19: ALF-BanCo-Import und Kategorien zusammenführen

Übernahme von Abschnitt 7 der Definition M19 (E-211). Verweise auf die
Abschnitte 1–6 meinen `alfbanco.md`, Verweise auf 7.x diesen Abschnitt 29.x.
Prüfmerkmale: E-214.

### 29.1 Import-Seite (ergänzt `oberflaeche.md` 13.7)

- `import-format` hat zusätzlich die Option `alfbanco` („ALF-BanCo (QIF-Export, eine
  Datei je Konto)“).
- Nur bei `alfbanco` sichtbar: Auswahl `import-konto` (erste Option leer „– Konto wählen
  –“, dann alle Bestandskonten in Baumfolge mit Kontopfad als Text, `value` = Konto-ID)
  und Hinweis `import-hinweis-alfbanco`. Bei anderen Formaten sind beide verborgen.
- `import-starten` sendet `POST /api/import/alfbanco` mit `datei` und `konto_id`. Ohne
  Datei oder ohne gewähltes Konto erscheint eine Fehlermeldung (Meldung 4.3,
  `data-art="fehler"`), keine Anfrage.
- Ergebnis wie 13.7 (`import-ergebnis` mit `data-erfolgreich`, `import-zahl-<feld>`,
  `import-meldung`); bei 422 `import-ergebnis` mit `data-erfolgreich="nein"` und einer
  `import-meldung`, die den Code enthält. Rückgängig mit Strg+Z wie jede Änderung.

### 29.2 Mehrfachauswahl im Kategorienbaum (ergänzt `oberflaeche.md` 13.1)

- `kategorienbaum` trägt `aria-multiselectable="true"`; jeder Eintrag `kategorie-<id>`
  trägt `aria-selected` = `true`/`false` (anfangs alle `false`).
- Klick auf den Namen markiert genau diesen Eintrag; Strg/⌘-Klick schaltet ihn um;
  Umschalt-Klick markiert den Bereich der sichtbaren Einträge vom zuletzt angeklickten bis
  zu diesem (ohne Strg ersetzt er die Markierung, mit Strg ergänzt er sie); Leertaste
  schaltet den fokussierten Eintrag um; Esc hebt alle Markierungen auf. Klick auf den
  Auf-/Zuklappschalter markiert nicht.
- Die Markierung bleibt beim Neuzeichnen des Baums erhalten (z. B. nach Änderungen).

### 29.3 Kontextmenü (ergänzt `oberflaeche.md` 8.2)

- Für Kategorien (Art `aufwand`/`ertrag`) steht im Kontomenü an **erster** Stelle
  `km-kategorie-zusammenfuehren`: Text „Zusammenführen in…“; im Kategorienbaum, wenn der
  angeklickte Eintrag markiert ist und mehrere markiert sind, „<n> Kategorien
  zusammenführen in…“ mit allen markierten als Quellen, sonst nur der angeklickte. Für
  Bestandskonten gibt es den Eintrag nicht. Die übrigen Einträge (`km-konto-…`) bleiben.

### 29.4 Dialog `zusammenfuehren-dialog`

- Titel „„<Name>“ zusammenführen“ bzw. „<n> Kategorien zusammenführen“.
- `zusammenfuehren-quellen`: Kontopfade der Quellen (Teile mit „ › “), durch „, “ getrennt.
- `zusammenfuehren-suche` (`type="search"`, anfangs fokussiert) filtert die Liste
  `zusammenfuehren-ziele` (`role="listbox"`) ohne Groß-/Kleinschreibung nach Teiltext des
  Kontopfads (nicht passende Optionen `hidden`).
- Optionen `zusammenfuehren-ziel-<id>` (`role="option"`, `aria-selected`) für alle
  Kategorien außer den Quellen (Unterkategorien der Quellen sind erlaubt) in Baumfolge;
  Text = Kontopfad, bei Einnahmen mit Zusatz „ (Einnahme)“. Klick wählt; Pfeil auf/ab in
  der Liste wählt die nächste/vorige sichtbare Option.
- `zusammenfuehren-loeschen` (Kontrollkästchen, anfangs gesetzt) = `quellen_loeschen`.
- Nach jeder Wahl des Ziels und jedem Umschalten von `zusammenfuehren-loeschen` ein
  Probelauf (`trocken = true`); `zusammenfuehren-vorschau` zeigt danach „<n> Buchungen
  werden auf „<Zielpfad>“ umgebucht“ (ggf. mit „, <m> Unterkategorien wandern mit“, „, <k>
  Regeln werden umgestellt“) und trägt `data-anzahl` = Anzahl `buchungen_umgebucht`.
- Meldet der Probelauf gesperrte Buchungen, erscheint das Kontrollkästchen
  `zusammenfuehren-gesperrte-bestaetigen`; sonst ist es verborgen.
- `zusammenfuehren-ausfuehren` ist deaktiviert, bis ein Ziel gewählt und der Probelauf
  erfolgreich ist und – bei gesperrten Buchungen – die Bestätigung gesetzt ist. Klick
  sendet den echten Lauf (mit `gesperrte_einbeziehen = true`, falls gesperrte Buchungen
  gemeldet wurden), schließt den Dialog, meldet „Zusammengeführt in „<Name>“.“ und lädt
  neu; der Baum zeigt die gelöschten Quellen nicht mehr. Fehler erscheinen im Dialog
  (`dialog-fehler`). Rückgängig mit Strg+Z.
- `zusammenfuehren-abbrechen` und Esc schließen ohne Änderung.

## 30. Meilenstein 20: Was kommt noch? (erwartete Zahlungen)

Übernahme von Abschnitt 8 der Definition M20 (E-216). Verweise auf die
Abschnitte 1–7 meinen `erwartungen.md`. Prüfmerkmale: E-219.

- Route `/erwartet` (Seite `seite-erwartet`, Titel „Was kommt noch?“), in `SPA_ROUTEN`.
  Navigationslink `navlink-erwartet` (nicht `nav-…`; die feste Liste aus M8 bleibt
  unverändert), mobil ausgeblendet. Befehlspalette: `befehl-gehe-erwartet` „Gehe zu: Was
  kommt noch? (erwartete Zahlungen)“, nach den festen „Gehe zu“-Einträgen bis „Gehe zu:
  Synchronisation“ und vor „Gehe zu: Benachrichtigungen“.
- Seitenattribut `data-aktiv` = `ja`/`nein` (= `aktiv`); ausgeschaltet zusätzlich ein
  Hinweis im Infotext `erwartet-summe` („Der Mail-Abgleich ist ausgeschaltet …“).
- Werkzeuge: `erwartet-abgleichen` „Jetzt abgleichen“ (`POST …/abgleich`, Meldung
  „Abgeglichen: n neu erkannt, m zugeordnet.“; Fehler als Meldung), `erwartet-neu`
  „Erwartete Zahlung anlegen…“.
- Schnellfilter `erwartet-filter` als Chips (`aria-pressed`):
  `erwartet-grund-<grund>` (alle vier Gründe, mehrfach), `erwartet-zustand-offen`,
  `-ueberfaellig`, `-erfuellt`, `-geschlossen` (= `guthaben`+`storniert`+`erledigt`;
  mehrfach; Vorgabe „Offen“; das Abwählen des letzten Chips setzt wieder „Offen“),
  `erwartet-faellig-alle`/`-0`/`-7`/`-30` (Fällig bis heute + n Tage), Suchfeld
  `erwartet-suche` (verzögert). Zustand im Abfrageteil der Adresse (`grund`, `zustand`
  außer der Vorgabe, `faellig`, `suche`, je Tab, M17); direkter Aufruf setzt die Chips.
- `erwartet-summe`: „n Eintrag/Einträge“, „· k überfällig“, „noch offen:“ mit Betrag
  (`data-betrag` = `summe_offen`).
- Tabelle `erwartet-tabelle` (Spalten Fällig, Grund, Händler mit Beschreibung, Kennung bzw.
  Referenz, Betrag (`vorzeichen_betrag`), Zustand, Aktionen) mit Zeilen `erwartung-<id>`
  (`data-zustand` = `ueberfaellig` oder `zustand`, `data-grund`), Reihenfolge wie die API;
  leer: `erwartet-leer`. Zustandstext „überfällig“ bzw. „offen (Rest …)“ bei Teilzahlung.
- Aktionen je Zeile: Knopf `erwartung-menue-<id>`, Rechtsklick, Umschalt+F10/Kontextmenü-
  Taste → Menü mit `km-erwartung-details`, `km-erwartung-bearbeiten`; nur offen:
  `km-erwartung-erledigt`, `km-erwartung-guthaben`, `km-erwartung-storniert`; nur
  geschlossen: `km-erwartung-oeffnen`; nur manuell: `km-erwartung-loeschen` (mit
  Bestätigung). Doppelklick oder Enter öffnet die Details.
- Dialog `erwartung-dialog` (Anlegen/Bearbeiten): `erwartung-richtung` (beim Bearbeiten
  gesperrt), `erwartung-haendler`, `erwartung-betrag` (Euro mit Komma),
  `erwartung-datum`, `erwartung-frist`, `erwartung-beschreibung`, `erwartung-ok`;
  ungültiger Betrag → Fehler im Dialog.
- Dialog `erwartung-details`: Angaben (`erwartung-zustand`), Mails `erwartung-mails`,
  Zuordnungen `erwartung-buchungen` mit „Zeigen“ (Sprung `/konten/<konto_id>?buchung=<id>`)
  und `erwartung-loesen-<buchung_id>`, Knopf `erwartung-belege` (öffnet den Betrachter aus
  M18), bei `offen` Kandidaten `erwartung-kandidaten` mit Einträgen `kandidat-<id>` und
  `kandidat-zuordnen-<id>`; Schließen `erwartung-details-schliessen`. `/erwartet?id=<id>`
  öffnet die Details dieser Erwartung (Link der Benachrichtigung).
- Jede Wirkung läuft über das Protokoll (Rückgängig wie M8).
- Mobil: dieselbe Seite (Aufruf über Befehlspalette/Adresse); Tests nur Desktop als Pflicht.

## 31. Meilenstein 21: Berichte (Einzelbuchungen, Zoom, Tooltip) und Sprungziel mittig

Übernahme der freigegebenen Definition M21 vom 2026-11-13 (E-221). Reine
Oberfläche: keine neuen Endpunkte, `openapi.yaml` unverändert, kein
fachlicher Zustand, kein Protokolleintrag. 31.4 ersetzt in 26.4 „in den
sichtbaren Bereich gerollt“ durch „in die vertikale Mitte“. Verweise auf
1–5 meinen die Unterabschnitte 31.1–31.5. Prüfmerkmale: E-222.

### 31.1 Einzelbuchungen in den Berichtstabellen (ergänzt `oberflaeche.md` 13.6, 25.7)

Betrifft die Tabelle `bericht-tabelle` (Kontostandsverlauf, eine Zeile je Stichtag)
und die Tabelle der Einnahmen/Ausgaben (eine Zeile je Zeitraum) auf `/berichte`.

- Jede Datenzeile (`tbody tr`) erhält in ihrer **ersten Zelle vorn** einen Knopf
  (`<button type="button">`):
  - Kontostand: `bericht-aufklappen-<i>`; Einnahmen/Ausgaben: `bericht-ea-aufklappen-<i>`
    (`i` = Index der Zeile ab 0 in der Reihenfolge der Tabelle).
  - `aria-expanded` = `false`/`true`; `aria-label` „Einzelbuchungen zeigen“ bzw.
    „Einzelbuchungen ausblenden“. Der Knopf hat **keinen Textinhalt** (Symbol nur über
    CSS), d. h. der `textContent` der ersten Zelle bleibt gegenüber vorher unverändert.
  - Die Datenzeile trägt nach dem ersten Klick `data-offen` = `ja`/`nein`.
- **Die Detailzeile entsteht erst beim ersten Aufklappen** (vorher gibt es sie nicht im
  Dokument; die Anzahl der Zeilen der Tabelle bleibt bis dahin unverändert). Sie folgt
  unmittelbar auf die Datenzeile: `<tr>` mit `bericht-details-<i>` bzw.
  `bericht-ea-details-<i>`, eine Zelle über alle Spalten (`colspan`). Zuklappen blendet sie
  aus (`hidden`), erneutes Aufklappen zeigt sie wieder (ohne neue Zeile).
- **Zeitraum der Detailzeile:**
  - Kontostand, Zeile i > 0: Buchungsdatum **nach** dem Stichtag der Zeile i−1 bis
    **einschließlich** Stichtag i; Zeile 0: nur Buchungen am ersten Stichtag.
  - Einnahmen/Ausgaben: `von` bis `bis` des Zeitraums der Zeile (wie in
    `GET /api/berichte/einnahmen-ausgaben`), **ohne Umbuchungen** (`ist_umbuchung`).
- **Quelle:** `GET /api/buchungen` mit `von`, `bis`, `sortierung=datum`, `pro_seite=500`
  je im Bericht gewähltem Konto (`konto_id`); ohne Kontoauswahl eine Abfrage ohne
  `konto_id`. Ergebnisse werden über die Buchungs-ID vereinigt und nach Datum, dann ID
  aufsteigend sortiert. Liefert eine Abfrage `gesamt` > Anzahl der Einträge, steht unter
  der Tabelle der Hinweis „Nur die ersten 500 Buchungen je Konto.“
- **Inhalt:** Tabelle mit den Spalten Datum, Empfänger („–“ ohne Empfänger),
  Verwendungszweck, Betrag, „Im Konto zeigen“; eine Zeile je Buchung
  `bericht-buchung-<id>` bzw. `bericht-ea-buchung-<id>` mit `data-id` = Buchungs-ID.
  Ohne Buchungen der Text „Keine Buchungen in diesem Zeitraum.“ (Klasse `leer`). Bei einem
  Fehler der Abfrage eine Meldung mit `role="alert"` in der Detailzeile.
- **Betrag** (Zelle mit `data-betrag` in Cent): Summe der Splits der Buchung auf den
  gewählten Konten; ohne Kontoauswahl Summe der Splits auf Bestandskonten
  (Kontoarten Aktiv/Passiv wie `datenmodell.md`).
- **Knöpfe je Konto:** Für jedes an der Buchung beteiligte Konto (verschiedene
  `konto_id` der Splits) ein Link `bericht-buchung-<id>-konto-<konto_id>` (bzw. mit
  `bericht-ea-`), Text = Kontoname, `href` = `/konten/<konto_id>?buchung=<id>`; gewählte
  Konten stehen zuerst. Ein normaler Linksklick springt innerhalb der Oberfläche wie
  „Gehe zur Gegenbuchung“ (`oberflaeche.md` 27.2: vorhandener Tab des Kontos wird
  verwendet, die Buchung ist danach gewählt und fokussiert, verdeckende Filter werden
  mit Hinweis zurückgesetzt). Mit Strg/⌘/Umschalt/Alt oder Mittelklick bleibt es ein
  gewöhnlicher Link (neuer Browser-Tab, nicht getestet).

### 31.2 Tabelle folgt dem Zoom des Diagramms

- Wird die x-Achse des Diagramms (Plotly) auf einen Bereich gezoomt oder verschoben,
  zeigt die Tabelle darunter nur die Zeilen, deren x-Wert (Stichtag bzw. `von` des
  Zeitraums) im sichtbaren Bereich liegt; die übrigen Datenzeilen bleiben im Dokument,
  sind aber `hidden` (ihre Detailzeilen ebenfalls). Kein neuer Abruf.
- Über der Tabelle steht dann der Hinweis `bericht-zoom-hinweis` bzw.
  `bericht-ea-zoom-hinweis` mit dem Text „Tabelle zeigt den Ausschnitt TT.MM.JJJJ –
  TT.MM.JJJJ (n von m Zeilen). Doppelklick ins Diagramm zeigt wieder alles.“; ohne Zoom
  ist er `hidden`.
- Autorange (Doppelklick ins Diagramm) zeigt wieder alle Zeilen und verbirgt den Hinweis.
- Ist Plotly nicht verfügbar (Ersatzgrafik als SVG), entfällt das Verhalten.
- Test: Zoom kann über das Diagrammelement mit der öffentlichen Plotly-Funktion
  `Plotly.relayout(<Diagrammelement>, {"xaxis.range": [a, b]})` bzw.
  `{"xaxis.autorange": true}` ausgelöst werden (Plotly ist eine öffentliche Bibliothek der
  Seite, `window.Plotly`); das Diagrammelement ist das Element `bericht-diagramm` bzw.
  `bericht-ea-diagramm` selbst (mit Plotly gezeichnet: Klasse `js-plotly-plot`).
- „Letzte Buchung im Kontoblatt zeigen“ ist `km-serie-springen` (M16); beide Namen
  meinen denselben Eintrag.

### 31.3 Tooltip im Thema

- Die Tooltips (Hover-Beschriftung) der Plotly-Diagramme verwenden die Farben des
  aktuellen Themas (Hintergrund, Rand, Text wie die Seite), auch im dunklen Thema.
- Der Reihenname steht im Text des Tooltips selbst („<Reihe>: <Betrag>“, bei
  Einnahmen/Ausgaben „Einnahmen <Zeitraum>: <Betrag>“ usw.), nicht in einem
  getrennten Namensfeld. Optisch; nicht automatisiert getestet (höchstens: Diagramm
  zeichnet ohne Konsolenfehler in beiden Themen).

### 31.4 Sprungziel immer mittig (ersetzt in `oberflaeche.md` 26.4 „in den sichtbaren Bereich gerollt“)

- Alle Sprünge zu einer Buchung in der Kontoansicht – Abfrageteil `?buchung=<id>`,
  „Gehe zur Gegenbuchung“ (`km-gegenbuchung`), Knöpfe der Einzelbuchungen (1),
  „Letzte Buchung im Kontoblatt zeigen“ und `km-serie-springen` (M16) – wählen die
  Buchung (`aria-selected="true"`, einzige Auswahl), fokussieren sie, rollen sie in die
  **vertikale Mitte** des Listenbereichs und heben sie kurz hervor (ca. 2 s).
- Prüfbar: nach dem Sprung zu einer Buchung weit unten in einer langen Liste liegt die
  Mitte der Zeile höchstens eine Zeilenhöhe von der Mitte des sichtbaren
  Scrollbereichs der Liste entfernt (sofern die Liste so weit rollen kann). Die
  waagerechte Scrollposition der Liste bleibt beim Sprung unverändert.
- Mobil (`data-layout="mobil"`) gilt dasselbe; die Zeile liegt danach nicht unter der
  unten fest stehenden Mehrfachleiste.

### 31.5 Abgrenzung

- `openapi.yaml` unverändert; keine Änderung an Berichtsendpunkten.
- Tests in `tests/app/m21/` (Marker `m21`), nur Browsertests.
- Abhängigkeiten: M5 (Berichte), M8, M15 (25.7 Berichtsgrafiken), M16 (Sprungziel), M17
  (Tabs, Gegenbuchung).

## 32. Meilenstein 22: Spaltenbreiten und Markierung der Buchungsliste

Übernahme der freigegebenen Definition M22 vom 2026-11-13 (E-223). Reine
Oberfläche: keine neuen Endpunkte, `openapi.yaml`, Datenmodell und Protokoll
unverändert. 32.3.2 setzt M20 (`erwartungen.md`) voraus. Verweise auf 1–4
meinen die Unterabschnitte 32.1–32.4. Prüfmerkmale: E-224.

Betrifft die Buchungsliste `buchungsliste` der Kontoansicht eines Bestandskontos und einer
Kategorie (`oberflaeche.md` 7.2, 22.2).

### 32.1 Spaltenbreiten (nur Desktop-Liste)

- **Spalten** der Liste, in dieser Reihenfolge (Feldnamen):
  Bestandskonto `datum`, `empfaenger`, `verwendungszweck`, `kategorie`, `tags`, `status`,
  `betrag`; Kategorie-Ansicht zusätzlich `konto` nach `kategorie`. Jede Kopfzelle
  (`role="columnheader"`) trägt am rechten Rand einen Trenner
  `spalte-trenner-<feld>` mit `role="separator"`, `aria-orientation="vertical"` und
  `aria-label` „Breite der Spalte <Spaltentitel>“. In der mobilen Liste
  (`data-layout="mobil"`, kompakte Darstellung) gibt es keine Trenner.
- **Klick** auf einen Trenner sortiert nicht (die Sortierung der Spalte bleibt; `aria-sort`
  unverändert, keine neue Abfrage).
- **Ziehen** eines Trenners mit der linken Maustaste ändert die Breite seiner Spalte um die
  waagerechte Mausbewegung, begrenzt auf **40–1200 px** (ganze Pixel). Beim ersten Ziehen
  (oder Anpassen) werden alle Spalten auf ihre aktuell gezeichnete Breite festgelegt, so
  dass sich die Breiten der übrigen Spalten dabei nicht ändern (Abweichung ≤ 1 px).
  Kopfzelle und die Zellen derselben Spalte aller Zeilen haben danach dieselbe Breite.
- **Doppelklick** auf einen Trenner setzt die Spalte auf die Breite ihres breitesten
  Inhalts aus Kopfzelle und allen geladenen Zeilen (ohne Abschneiden gemessen, plus
  höchstens wenige Pixel), wieder begrenzt auf 40–1200 px. Folge: Kein Text der Spalte ist
  danach abgeschnitten (für jede Zelle der Spalte gilt `scrollWidth` ≤ `clientWidth` + 1
  des Textinhalts bzw. der Zelle). Ein Doppelklick sortiert nicht.
- Ist die Summe der Breiten größer als die Breite der Liste, wird die Liste waagerecht
  geblättert (horizontaler Scrollbereich); Kopf und Zeilen bleiben bündig.
- **Kontextmenü des Listenkopfs** (Rechtsklick auf die Kopfzeile, nur Desktop):
  - `km-spalten-anpassen` „Alle Spalten an den Inhalt anpassen“: wie Doppelklick für alle
    Spalten.
  - `km-spalten-zuruecksetzen` „Spaltenbreiten zurücksetzen“: verwirft alle eigenen
    Breiten dieser Listenart, die Liste zeigt wieder das Vorgaberaster (gleiche Breiten
    wie ohne jede Änderung). Deaktiviert (`aria-disabled="true"` wie andere inaktive
    Menüeinträge), solange keine eigene Breite gesetzt ist.
  - Das Kontextmenü des Kopfs ist nicht das Kontextmenü einer Buchung (kein `km-…` einer
    Zeile, die Auswahl bleibt unverändert).
- **Speicherung im Browser:** Eigene Breiten werden im Browser-Speicher (`localStorage`,
  Schlüssel `kontor.spalten`) gemerkt, getrennt nach Listenart `konto` (alle
  Bestandskonten gemeinsam) und `kategorie` (alle Kategorien gemeinsam). Nach Neuladen der
  Seite und in einer anderen Kontoansicht derselben Listenart gelten dieselben Breiten;
  die andere Listenart bleibt unberührt. Ungültige oder fremde Inhalte unter dem
  Schlüssel werden ignoriert (Vorgaberaster, kein Fehler); ohne Browser-Speicher (Zugriff
  wirft) funktioniert alles, nur ohne Merken (M17 1.6).
- Die Breiten sind kein fachlicher Zustand: keine REST-Anfrage, kein Protokolleintrag.

### 32.2 Markierung des Bearbeitungsstands

Jede Zeile der Buchungsliste (Desktop und mobil) trägt das Attribut `data-markierung`
nach dieser Rangfolge (erste zutreffende Regel gilt):

1. `abgeglichen`: Status der Buchung ist `abgeglichen` **oder** die Buchung ist
   abgestimmt (`abgestimmt` wahr, Kontenabstimmung M3).
2. `kategorisiert`: kein Split der Buchung liegt auf der Kategorie „Unkategorisiert“
   (`extern_id = "kontor:unkategorisiert"`). Umbuchungen und Splitbuchungen zählen dazu;
   der Status ist dabei gleichgültig (auch `importiert`).
3. `importiert`: Status `importiert` (und mindestens ein Split auf „Unkategorisiert“).
4. sonst **kein** Attribut `data-markierung` (z. B. `vorlaeufig` oder `bestaetigt` mit Split
   auf „Unkategorisiert“).

Darstellung: schmaler farbiger Streifen am linken Rand der Zeile und leichte Tönung
(grün für `kategorisiert`, grau für `importiert`, grün-grau für `abgeglichen`), im hellen
und dunklen Thema. Hover und Auswahl überdecken die Tönung, der Streifen bleibt. Die
Markierung folgt Änderungen (nach Kategorisieren, Statuswechsel, Rückgängig zeigt die neu
geladene Liste den neuen Wert). Farben werden nicht getestet, nur dass die drei Werte
optisch unterscheidbar sind (verschiedene berechnete `background-image` bzw.
`background-color` der Zeile).

### 32.3 Zusatzmarken vor dem Empfänger

#### 32.3.1 Wiederkehrend

- Zeilen, deren Buchung in `buchung_ids` einer Serie von `GET /api/wiederkehrend` steht
  (alle Serien, auch `ausbleibend` und `beendet`), tragen `data-wiederkehrend="ja"`;
  andere Zeilen haben das Attribut nicht.
- Vor dem Empfänger erscheint „↻“ nur über CSS (Pseudo-Element); der `textContent` der
  Empfängerzelle bleibt unverändert. Der Titel (`title`) der Empfängerzelle lautet
  „<Empfänger> – wiederkehrende Buchung“ (ohne Empfänger: nur die Hinweise, siehe 3.3).
- Schlägt `GET /api/wiederkehrend` fehl, fehlt die Marke; die Liste funktioniert.

#### 32.3.2 Durch Mail bestätigt (setzt M20 voraus)

- Zeilen, deren Buchung in `buchung_ids` einer Erwartung aus `GET /api/erwartungen` mit
  Grund `bestellung`, `paypal` oder `rueckerstattung` steht – in **beliebigem** Zustand
  (`offen`, `erfuellt`, `guthaben`, `storniert`, `erledigt`) –, tragen `data-mail="ja"`.
  Manuelle Erwartungen (Grund `manuell`) setzen die Marke nicht.
- Vor dem Empfänger erscheint „✉“ (nur CSS; Text der Zelle unverändert); bei beiden Marken
  „↻ ✉“.
- Der Titel der Empfängerzelle enthält „durch Mail bestätigt: <Grundtext> <Händler>
  <Kennung>“ (Grundtext „Bestellung“, „PayPal-Zahlung“, „Rückerstattung“; leere Teile
  entfallen). Gehört die Buchung zu mehreren solchen Erwartungen, nennt der Titel die
  erste in der Reihenfolge der Antwort.
- Ist der Mail-Abgleich ausgeschaltet oder schlägt die Abfrage fehl, fehlt die Marke.

#### 32.3.3 Titel bei mehreren Hinweisen

Der Titel der Empfängerzelle setzt sich aus Empfängername (falls vorhanden) und den
Hinweisen in der Reihenfolge „wiederkehrende Buchung“, „durch Mail bestätigt: …“ zusammen,
getrennt durch „ – “. Ohne Hinweise bleibt der Titel wie bisher.

### 32.4 Abgrenzung

- `openapi.yaml` unverändert. Tests in `tests/app/m22/` (Marker `m22`), nur Browsertests.
- Abhängigkeiten: M3 (Abstimmung), M5/M16 (wiederkehrend), M8, M11 (Kategorie-Ansicht),
  M17 (Browser-Speicher), M20 (Erwartungen, nur 3.2).

## 33. Meilenstein 23: Schutz der Geheimnisse, gemerkte PIN, App-Passwort

Übernahme von Abschnitt 8 der Definition M23 (E-228). Verweise auf die Abschnitte
2–6 meinen `geheimnisschutz.md`. Browsertests, keine `kern`; Prüfmerkmale: E-231.

- **Sperrleiste:** Ist die Instanz gesperrt, steht über der Tab-Leiste `sperr-leiste` (`role="status"`) mit dem
  Text „Kontor ist gesperrt …“ und dem Knopf `sperr-entsperren`. Ohne Schutz oder entsperrt gibt es sie nicht bzw.
  sie ist `hidden`. Geprüft beim Laden, alle 60 s und nach Aktionen in den Einstellungen.
- **Entsperren-Dialog** `entsperren-dialog`: Passwortfeld `entsperren-passwort` (`type=password`), Knopf
  `entsperren-ok` (auch Enter). Leer → Fehler im Dialog; falsches Passwort → Fehlermeldung im Dialog, Dialog bleibt
  offen; richtig → Dialog schließt, Meldung „Entsperrt.“, Sperrleiste verschwindet. Das Feld wird nach jedem
  Versuch geleert.
- **Einstellungen** (`/einstellungen`, nach dem PIN-Abschnitt) Abschnitt „Schutz der Geheimnisse“:
  `schutz-status` mit `data-aktiv` (`ja`/`nein`) und `data-gesperrt` (`ja`/`nein`), Passwortfeld
  `schutz-passwort`; Knöpfe je Zustand: aus → `schutz-einschalten`; ein und entsperrt → `schutz-sperren`,
  `schutz-ausschalten`, bei gemerkter PIN `schutz-pin-vergessen`; ein und gesperrt → `schutz-entsperren`,
  `schutz-ausschalten`. Aktionen rufen 2.2/2.3 bzw. `DELETE /api/sync/pin/gemerkt` und laden die Seite neu.
- **PIN-Dialog** (`pin-dialog`, `oberflaeche.md`): Kontrollkästchen `pin-merken`, sichtbar genau bei Schutz ein
  und entsperrt; angehakt sendet der Dialog `PUT /api/sync/pin/gemerkt`, sonst wie bisher `PUT /api/sync/pin`.
- **Postfachseite** (`/mail/postfaecher/<id>`) Abschnitt „Zugang mit App-Passwort (empfohlen für Gmail)“ vor dem
  OAuth2-Abschnitt: Anleitung, Feld `postfach-ordner` (vorbelegt mit `ordner`), Passwortfeld
  `postfach-app-passwort`, Knopf `postfach-app-speichern` (ändert ggf. zuerst den Ordner per
  `PATCH /api/mail/postfaecher/{id}`, dann 6.1; Erfolg: Meldung mit Zahl der Nachrichten, Seite neu geladen,
  `postfach-status` `data-anmeldung="angemeldet"`; Fehler: Text in `postfach-app-ergebnis` mit `role="status"`),
  Knopf `postfach-app-entfernen` (6.2). Das Passwortfeld wird nach dem Absenden geleert.

## 34. Meilenstein 24: Kachel „Was kommt noch?“ und Serien auf `/erwartet`

Übernahme der Abschnitte 2 und 4 der Definition M24 (E-233); ergänzt 30. Verweise
auf „1.1“ usw. meinen `erwartungen.md` 13.1.1 usw. Browsertests, keine `kern`;
Prüfmerkmale: E-236.

### 34.1 Kachel „Was kommt noch?“ auf der Finanzübersicht [browser]

- Auf `/` (Finanzübersicht, Desktop und mobil) erscheint am Ende der Seite ein Link `kachel-erwartet`
  (`<a href="/erwartet">`), **nur** wenn der Mail-Abgleich eingeschaltet ist (`aktiv = true`); sonst fehlt er.
  Schlägt die Abfrage fehl, fehlt die Kachel, die Seite funktioniert.
- Zahlen = `GET /api/erwartungen?grund=bestellung&grund=paypal&grund=rueckerstattung&grund=manuell` (Zustand
  `offen` einschließlich überfälliger, **ohne Serien**):
  Text „Was kommt noch?“, dann „<anzahl> offen“, bei `ueberfaellig` > 0 zusätzlich „· <k> überfällig“
  (hervorgehoben), dann „· “ und der Betrag `summe_offen` (Element mit `data-betrag` = `summe_offen` in Cent).
  Bei 0 Einträgen „0 offen“ und Betrag 0 (die Kachel wird trotzdem gezeigt).
- Ein Klick öffnet `/erwartet` in der Oberfläche (Tab nach M17).

### 34.2 Seite `/erwartet` mit Serien [browser] (ergänzt `oberflaeche.md` 30)

- Schnellfilter: zusätzlicher Chip `erwartet-grund-serie` „Serie“ (fünf Grund-Chips). Ist **kein** Grund-Chip
  gewählt, fragt die Seite mit `serien=ja` ab (Serien sichtbar); mit gewählten Gründen nur diese (Serien nur mit
  dem Chip „Serie“).
- Abfrageteil der Adresse: ohne gewählten Grund steht dort zusätzlich `serien=ja` (siehe 6, offener Punkt);
  Tests prüfen die übrigen Parameter wie in M20 (Teilmenge).
- Zeile eines Serieneintrags: `erwartung-<id>` mit allen Zeichen außer `a–z`, `A–Z`, `0–9`, `-` durch `-`
  ersetzt, z. B. `erwartung-serie-1-1-ausgabe`; `data-grund="serie"`, `data-zustand` `offen` bzw.
  `ueberfaellig`; Grund-Marke „Serie“; Händler mit Beschreibung; Betrag `vorzeichen_betrag`.
- Doppelklick oder Enter auf die Zeile öffnet `/wiederkehrend` (kein Detaildialog).
- Menüknopf `erwartung-menue-<id>` mit der **unveränderten** ID (z. B. `erwartung-menue-serie:1:1:ausgabe`),
  Rechtsklick, Umschalt+F10/Kontextmenü-Taste: Menü nur mit `km-erwartung-serie` „Serie ansehen“
  (→ `/wiederkehrend`) und `km-erwartung-konto` „Konto öffnen“ (→ `/konten/<konto_id>`); keine Einträge zum
  Bearbeiten, Schließen oder Löschen.
- Summenzeile `erwartet-summe` zählt Serien mit (wie `anzahl`/`summe_offen` der Abfrage).

## 35. Meilenstein 25: Betragsfilter wiederkehrender Buchungen

Übernahme von Abschnitt 7 der Definition M25 (E-238); Verweise auf „3.x“ meinen
`wiederkehrend.md` 9.3.x. Browsertests, keine `kern`; Prüfmerkmale: E-241.

- **Einstellungen**, Abschnitt „Wiederkehrende Buchungen“:
  - Vorgabe: Auswahl `wk-vorgabe-modus` (`toleranz`, `aus`), Zahlenfeld `wk-vorgabe-toleranz` (nur bei Toleranz
    sichtbar) und Knopf `wk-vorgabe-speichern`. Speichern schreibt die Vorgabe, ohne Rückgängig-Eintrag, und lädt neu.
  - Tabelle `wk-filter-liste` mit einer Zeile `wk-filter-<empfaenger_id>` (`data-modus`) je eigener Einstellung:
    Name, Kurztext („Toleranz ±n %“, „nur Beträge ab x €“, „aus (jeder Betrag zählt)“), Knopf „Ändern …“ (öffnet den
    Dialog) und `wk-filter-entfernen-<id>` (DELETE, mit Rückgängig).
  - Ohne eigene Einstellungen statt der Tabelle der Hinweis „Alle Empfänger verwenden die Vorgabe.“
  - Knopf `wk-filter-neu` öffnet den Dialog mit Empfängerauswahl.
- **Dialog `wk-filter-dialog`:**
  - `wk-filter-empfaenger` erscheint nur ohne vorgegebenen Empfänger.
  - `wk-filter-modus` mit den Werten `vorgabe` („wie Vorgabe“), `toleranz`, `mindestschwelle` und `aus`.
  - `wk-filter-toleranz` (Prozent) und `wk-filter-betrag` (Euro, Vorzeichen egal) sind je nach Modus sichtbar.
  - `wk-filter-speichern`: bei `vorgabe` DELETE, falls eine eigene Einstellung bestand, sonst schließt der Dialog
    ohne Anfrage; sonst PUT. Speichern läuft mit Rückgängig, und Fehler erscheinen im Dialog.
- **Begründungsdialog** (M16): Hinweis `wk-betragsfilter` mit `data-modus` und `data-quelle`, Text =
  `betragsfilter_text` des Eintrags. Bei Buchungen mit Empfänger der Knopf `wk-filter-oeffnen` (`aria-label`
  „Betragsfilter für <Name>“): schließt den Begründungsdialog und öffnet `wk-filter-dialog` für diesen Empfänger.
- Rolle `anderer_betrag` erscheint in der Rollenliste als „anderer Betrag“.

## 36. Meilenstein 26: Bedienung auf dem Handy

Übernahme der Definition M26 (Feature `UXMobile`, E-246). Reine Oberfläche plus ein Antwortkopf (36.8):
keine neuen Endpunkte, kein fachlicher Zustand, kein Protokoll, nichts in der Sicherung; `openapi.yaml`
unverändert. Browsertests mit den Geräten aus 21 (`desktop`, `handy`), keine `kern` außer 36.8 (REST ohne
Browser). Prüfmerkmale: E-247. **Ab M28 (37) entfallen** die Seite `/wiederkehrend` und damit 36.6.2.

### 36.1 Geltungsbereich

1. Alles Folgende gilt nur im mobilen Layout (`app` mit `data-layout="mobil"`, 16.1).
2. Im Desktop-Layout ändert sich nichts (auch auf einem Desktop-Fenster mit Touch bleibt lange Berührung =
   Kontextmenü). Die neuen Elemente `suche-knopf`, `tabs-knopf`, `tabs-zahl`, `auswahl-kopf` (mit Inhalt) und
   `mehrfach-mehr` sind im Desktop-Layout vorhanden, aber nicht sichtbar.
3. In keiner Ansicht entsteht im mobilen Layout waagerechtes Scrollen der Seite (16.2; auch Karten aus 36.6 und
   die Tab-Liste aus 36.2.3).

### 36.2 Kopfzeile (`app-kopf`)

1. **Eine** Zeile mit, in dieser Reihenfolge: `menue-knopf`, `suche-knopf`, Synchronisation, Rückgängig,
   Wiederholen, Befehlspalette, Benachrichtigungen, `tabs-knopf` (ab M28 danach `person-knopf`, 37.1). Unter
   390 CSS-Pixel Breite darf „Wiederholen“ fehlen. Alle Knöpfe mindestens 44 × 44 px.
2. **Suche:** `suche-feld` ist anfangs nicht sichtbar. `suche-knopf` (`aria-controls`, `aria-expanded`
   `false`/`true`, `aria-label` „Suche einblenden“/„Suche ausblenden“) blendet es als zweite Zeile ein und setzt
   den Fokus hinein; erneutes Betätigen blendet es aus. Verliert das **leere** Feld den Fokus (nicht an
   `suche-knopf`), wird es ausgeblendet; mit Inhalt bleibt es sichtbar. Absenden wie bisher (13.8).
3. **Tabs** (ersetzt mobil 27.1.2 „sichtbar … auf Desktop und mobil“):
   - `tab-leiste` ist mobil **nicht sichtbar**, solange sie nicht aufgeklappt ist; sie bleibt mit allen Rollen und
     Attributen aus 27.1 im Dokument.
   - `tabs-knopf` (`aria-controls="tab-leiste"`, `aria-expanded`) zeigt in `tabs-zahl` die Zahl offener Tabs;
     `aria-label` „Geöffnete Ansichten (n)“.
   - Betätigen klappt `tab-leiste` als **senkrechte Liste** über dem Inhalt auf (`aria-expanded="true"`); der
     aktive Tab liegt vollständig innerhalb der Liste und erhält den Fokus.
   - Wahl eines Tabs (Titel) wechselt dorthin und klappt die Liste zu; Schließen (×) lässt sie offen. Esc,
     erneutes Betätigen von `tabs-knopf` und Tippen außerhalb von Liste und Knopf klappen sie zu. Ohne offene Tabs
     ist sie zu.
   - Wechselt das Layout zu Desktop, ist die Liste zu und die Leiste wieder dauerhaft sichtbar (27.1.2).
   - Alles Übrige aus 27 gilt unverändert.
4. Der Mock-Hinweis ist einzeilig gekürzt; Tippen zeigt den ganzen Text, erneutes Tippen kürzt wieder. Er bleibt
   oben sichtbar.

### 36.3 Kontoansicht: Tippen, lange Berührung, Auswahlmodus (ersetzt für Buchungszeilen 16.4 „lange Berührung“)

1. **Ohne Auswahl:** Tippen auf eine Buchungszeile öffnet die Einzelheiten (16.3).
2. **Lange Berührung** (≥ 500 ms ohne Bewegung über 10 px) auf eine Buchungszeile öffnet **kein** Kontextmenü,
   sondern wählt die Zeile aus (`aria-selected="true"`) und beginnt den Auswahlmodus; im Auswahlmodus nimmt sie
   die Zeile hinzu (ausgewählte bleiben ausgewählt). Danach öffnen sich keine Einzelheiten (`panel-details`
   bleibt verborgen) und kein Menü. Ein vom Browser ausgelöstes `contextmenu` öffnet in der Buchungsliste
   ebenfalls kein Menü.
3. **Auswahlmodus** besteht genau dann, wenn mindestens eine Buchung ausgewählt ist:
   - `buchungsliste` trägt `data-auswahlmodus="ja"` (sonst fehlt es oder ist `nein`); jede Zeile zeigt links
     eine Marke, ausgewählte ein Häkchen (maßgeblich bleibt `aria-selected`).
   - Tippen auf eine Zeile schaltet deren Auswahl um; Einzelheiten öffnen sich nicht.
   - `auswahl-kopf` (`role="toolbar"`, `aria-label` „Auswahlmodus“) ist sichtbar, seine Oberkante ≥ Unterkante
     von `app-kopf` − 1 px (Rückgängig bleibt bedienbar); er enthält `auswahl-beenden` (`aria-label` „Auswahl
     beenden“), `auswahl-kopf-anzahl` („1 ausgewählt“ bzw. „n ausgewählt“, `aria-live="polite"`) und
     `auswahl-alle` (wählt alle geladenen Buchungen der Liste).
   - `mehrfach-leiste` ist sichtbar und zeigt **nur** Kategorie, Tags, Löschen und `mehrfach-mehr` („Mehr“,
     `aria-haspopup="menu"`); die übrigen Knöpfe bleiben im Dokument, unsichtbar. `mehrfach-mehr` öffnet das
     Kontextmenü der Auswahl mit denselben Einträgen wie ein Rechtsklick auf eine ausgewählte Zeile (8.2,
     inkl. `km-status`, `km-splitten` bei genau einer, `km-gegenbuchung`); Wirkung unverändert.
   - `buchung-erfassen` ist nicht sichtbar.
4. **Beenden:** `auswahl-beenden`, das Abwählen der letzten Zeile oder die Zurück-Navigation des Browsers heben
   die Auswahl auf (`data-auswahlmodus` nicht `ja`, `auswahl-kopf` verborgen). Die Zurück-Navigation verlässt
   die Ansicht nicht (Pfad und Abfrageteil gleich, kein Tab-Wechsel). Endet der Auswahlmodus anders, führt eine
   spätere Zurück-Navigation normal zur vorigen Ansicht (kein „leerer“ Schritt).
5. Unverändert: Rechtsklick und Tastaturwege zum Kontextmenü auf Buchungszeilen; lange Berührung in anderen
   Ansichten (Kontenbaum, Kategorien, Tabs) öffnet weiter das jeweilige Kontextmenü (16.4).
6. Außerhalb des Auswahlmodus ist `buchung-erfassen` ein schwebender Knopf unten rechts (sichtbar, nicht im
   Seitenfluss); `filter-umschalten`, Konto-Einstellungen und Verschieben stehen mit dem Kontonamen in einer Zeile.

### 36.4 Wischgesten (ergänzt 16.4)

1. Wirkung unverändert: nach rechts schaltet die Auswahl um, nach links öffnet die Kategorieauswahl.
2. Ausgelöst bei ≥ 80 CSS-Pixel waagerecht und ≤ 40 senkrecht; im mobilen Layout **ohne Dauergrenze** (im
   Desktop-Layout mit Touch gilt ≤ 1 000 ms weiter).
3. Während des Wischens folgt die Zeile dem Finger (höchstens 160 px); dahinter erscheint ein Element der Klasse
   `wisch-hinweis` (`aria-hidden="true"`, `data-richtung` `rechts`/`links`, `data-bereit` `ja` ab 80 CSS-Pixel,
   sonst `nein`; Text rechts „✓ Auswählen“ bzw. „✕ Abwählen“, links „Kategorie …“). Wird der senkrechte Weg
   größer als 40 px, verschwindet der Hinweis. Nach Loslassen oder Abbruch ist er verborgen und die Zeile ohne
   Verschiebung. Senkrechtes Scrollen bleibt möglich.

### 36.5 Menüs und Dialoge als Blatt vom unteren Rand

1. **Kontextmenüs** (alle) erscheinen unten über die ganze Breite (links 0, rechts = Breite, Unterkante =
   Unterkante des sichtbaren Bereichs, je ±2 px); Einträge mindestens 48 px hoch. Einträge mit
   `aria-disabled="true"` sind mobil nicht sichtbar (bleiben im Dokument). Bedienung unverändert.
2. **Dialoge** (`role="dialog"`) erscheinen unten über die ganze Breite (Unterkante unten, höchstens 92 % der
   Höhe, Inhalt scrollbar); die Befehlspalette oben über die ganze Breite. Tippen auf den abgedunkelten Bereich
   wirkt wie Esc.
3. Beim Öffnen eines Dialogs liegt der Fokus **nicht** in einem Textfeld (Texteingabe, `textarea`), sondern im
   Dialog. Ausdrücklich festgelegter Startfokus (Befehlspalette, TAN-Eingabe, Entsperren) bleibt.
4. `<meta name="viewport">` enthält `interactive-widget=resizes-content`.

### 36.6 Tabellen als Karten

1. Mobil ohne sichtbare Kopfzeile (`thead` nicht sichtbar), je Zeile eine Karte: Bezeichnung und Betrag in der
   ersten Zeile der Karte (gleiche Höhe ±8 px, Betrag am rechten Rand), übrige Angaben darunter: Finanzübersicht
   (`uebersicht-tabelle`, auch Kategorientabellen), Konten (`kontenbaum`), `wiederkehrend-tabelle` (bis M28),
   Tilgungsplan, Berichte (`bericht-tabelle`, Einnahmen/Ausgaben, Einzelbuchungen), `wk-filter-liste` (bis M28),
   Empfänger. `data-testid`, Rollen, Zustandsattribute und Inhalte bleiben; Links und Knöpfe bedienbar. Desktop:
   unverändert Tabellen (Zeilen `display: table-row`, Kopfzeile sichtbar).
2. *(Bis M28.)* Wiederkehrende Buchungen als Karten, Tippen auf die Karte öffnet das Menü der Serie (26.3).
3. **Suchtreffer** (`/suche`): Buchungstreffer kompakt (Empfänger und Betrag oben, Datum und Kategorie
   darunter); Tippen öffnet die Kontoansicht des Kontos mit der Buchung ausgewählt und fokussiert (wie `?buchung=`).
4. **Filterleiste** der Kontoansicht: Felder zweispaltig, kein Feld breiter als die Liste.
5. **Diagramme:** Werkzeugleiste von Plotly mobil ausgeblendet; Diagramme passen in die Breite.

### 36.7 Kein klebender Hover

Mobil auf Geräten ohne Hover zeigt eine Zeile nach dem Tippen keine Hervorhebung, die wie eine Auswahl aussieht.
Nicht automatisiert getestet.

### 36.8 Auslieferung statischer Dateien [kern, REST ohne Browser]

1. Antworten unter `/oeffentlich/` (und `/static/`, falls vorhanden) mit Status 200 tragen `Cache-Control:
   no-cache` (sofern die Datei keine eigene Angabe hat) und einen `ETag`. Eine bedingte Anfrage mit passendem
   `If-None-Match` ergibt 304 ohne Körper (`sicherheit.md` 6).
2. `/sw.js` (18), die Hülle (`no-store`) und `/api/` (`no-store`) bleiben wie festgelegt.
3. Nach einem Update zeigt die Oberfläche spätestens nach zweimaligem Neuladen den neuen Stand, auch mit aktivem
   Service Worker. Nicht automatisiert getestet; der Offline-Fall aus 18 bleibt.

### 36.9 Abgelöste Festlegungen

Mobil abgelöst: 16.4 „lange Berührung“ für Buchungszeilen (durch 36.3), die Dauergrenze der Wischgesten (durch
36.4.2), 27.1.2 Sichtbarkeit der Tab-Leiste (durch 36.2.3). Die sechs Browsertests, die das alte Verhalten
prüften, sind nach Definition 9 angepasst (E-248).

## 37. Meilenstein 28: Oberfläche aus `feature/sammel`

Übernahme der Definition M28 (Auftraggeber, 2026-11-16, kontor-app D-145 bis D-168, Oberflächenteil; E-252).
Die REST-Teile stehen in `sammel.md` und `mail.md` 6.6 (M27). Bei Widersprüchen zwischen M27 und M28 gilt
M28; insbesondere entfällt die Route `/wiederkehrend` (37.3). Verweise auf „M27“ meinen `sammel.md`, auf
„Abschnitt n“ diesen Abschnitt 37.n. Neue Tests sind Browsertests ohne `kern`; geänderte frühere Tests:
E-253, E-254; Prüfmerkmale: E-255. Ersetzt bzw. ergänzt: 3 (Navigation, Routen), 7.6/23.2
(Doppelklick-Bearbeiten), 8.2 (Kontextmenü), 12.1/12.3 (Alt+8, Palette), 13.5/26/35 und 34.2
(wiederkehrende Buchungen in der Oberfläche), 25.3 (Verschieben), 27 (Tab-Kontextmenü), 32.3 (Marke ↻).

### 37.1 Person (wer gerade da ist)

- Der Haushalt hat **ein** Passwort (M7) und genau zwei Personen mit festen Namen **„Torsten“** und
  **„Tina“** (nicht konfigurierbar).
- Die gewählte Person wird im Browser gemerkt (`localStorage`, Schlüssel `kontor.person`, Wert genau
  `Torsten` oder `Tina`; jeder andere Wert gilt als „keine Person“). Abmelden (M7) vergisst sie.
- **Pflichtdialog:** Ist beim Start der Oberfläche (jede Seite der Hülle, nach `data-bereit="ja"` am
  Element `app`) keine Person gemerkt, öffnet sich sofort der modale Dialog `person-dialog` mit dem
  Titel „Wer bist du?“, einem erklärenden Satz und den Knöpfen `person-torsten` und `person-tina`. Er
  hat **keinen** „Abbrechen“-Knopf und lässt sich mit Esc nicht schließen; er verdeckt die Seite, bis eine
  Person gewählt ist. Danach schließt er sich, die Person ist gemerkt, die aktuelle Seite lädt neu.
  Im Dialog erscheint nirgends der Text „null“.
- **Personenknopf** `person-knopf` in der Kopfleiste (rechts, nach den übrigen Kopfknöpfen):
  - Text = Name der Person, ohne Person „Wer?“; `data-person` = Name (leer ohne Person);
    `data-kurz` = erster Buchstabe (ohne Person „?“).
  - `aria-label` „Angemeldet als <Name>. Benutzer wechseln.“ bzw. „Wer bist du?“.
  - Klick öffnet `person-dialog` mit Titel „Benutzer wechseln“, den beiden Personen (die aktuelle
    hervorgehoben) und `person-abbrechen`; Abbrechen und Esc ändern nichts.
  - Mobil (`data-layout="mobil"`) zeigt der Knopf sichtbar nur den Anfangsbuchstaben in einem Kreis;
    die Kopfleiste ist dabei nicht breiter als das Gerät (kein waagerechtes Scrollen der Seite,
    `document.documentElement.scrollWidth <= innerWidth`).
- **Ohne Browser-Speicher** (Zugriff wirft, M17 1.6) gilt die im Dialog gewählte Person für die Dauer der
  geladenen Seite (37.14 C1); der Pflichtdialog erscheint dann bei jedem Neuladen erneut.
- Für **alle Browsertests** (auch früherer Meilensteine): Vor dem ersten Laden die Person setzen
  (`localStorage["kontor.person"] = "Torsten"` über ein Init-Skript des Browserkontexts) oder den
  Pflichtdialog über `person-torsten` beantworten.

### 37.2 Navigation in Themengruppen (ersetzt `oberflaeche.md` 3, Liste der Einträge)

Die Navigation besteht aus fünf Gruppen, je ein Abschnitt mit Überschrift (`h2`, `data-testid`
`nav-gruppe-<g>`, als `aria-labelledby` des Abschnitts) und Links in dieser Reihenfolge:

| Gruppe (`nav-gruppe-…`) | Überschrift | Links (`data-testid` → Ziel) |
| --- | --- | --- |
| `buchhaltung` | Buchhaltung | `nav-uebersicht` → `/`, `nav-konten` → `/konten`, `nav-kategorien` → `/kategorien`, `nav-empfaenger` → `/empfaenger`, `nav-kredite` → `/kredite` |
| `zahlungen` | Zahlungen | `navlink-erwartet` → `/erwartet`, `navlink-mail` → `/mail` |
| `auswertung` | Auswertung | `nav-berichte` → `/berichte`, `navlink-statistik` → `/statistik` |
| `regeln` | Regeln | `nav-regeln` → `/regeln`, `nav-vorlagen` → `/vorlagen`, `nav-dubletten` → `/dubletten` |
| `betrieb` | Betrieb | `nav-import` → `/import`, `nav-sync` → `/sync`, `nav-protokoll` → `/protokoll`, `nav-einstellungen` → `/einstellungen` |

- `nav-wiederkehrend` entfällt. Der Versionsknopf (M13) bleibt das letzte Element der Navigation.
- Die Links in Dokumentreihenfolge (alle `a[data-testid]` der Navigation) sind genau die 16 obigen in
  dieser Reihenfolge; `aria-current="page"` wie bisher am Link der aktuellen Seite.
- Jede Gruppe hat einen eigenen Farbton (nicht getestet).
- **Alt+1 … Alt+7**: Finanzübersicht, Konten, Kategorien, Kredite, Berichte, Import, Einstellungen.
  **Alt+8 hat keine Wirkung mehr** (bisher wiederkehrende Buchungen).
- Befehlspalette: „Gehe zu“-Einträge in dieser Reihenfolge: `befehl-gehe-uebersicht`, `-konten`,
  `-kategorien`, `-kredite`, `-berichte`, `-import`, `-einstellungen`, `-protokoll`, `-empfaenger`,
  `-regeln`, `-vorlagen`, `-dubletten`, `-sync`, `-erwartet`, `-mail`, `-statistik`,
  `-benachrichtigungen`; danach `befehl-rueckgaengig`, `befehl-wiederholen` und die übrigen wie bisher.
  `befehl-gehe-wiederkehrend` und `befehl-wiederkehrend-warum` entfallen.

### 37.3 Routen

- Neu: `/mail` (Mail-Blatt, `seite-mail`), `/statistik` (Statistische Analyse, `seite-statistik`).
  Beide liefern bei direktem Aufruf die Hülle (HTTP 200) und zeigen die Seite.
- **Entfallen:** `/wiederkehrend`. Ein direkter Aufruf liefert HTTP **404** (keine Hülle); innerhalb der
  Oberfläche zeigt eine Navigation dorthin `seite-nicht-gefunden`. Die REST-Endpunkte der Erkennung
  wiederkehrender Buchungen (`/api/wiederkehrend…`, M5/M16/M25) bleiben unverändert erreichbar.
- Adresse `/mail`: Abfrageteil `postfach=<id>`, `filter=zugeordnet|erwartet|keine`, `seite=<n>` (ab 2),
  `id=<nachricht>`; Vorgaben werden nicht geschrieben.
- Adresse Kontoblatt: zusätzlich `gruppierung=datum` (6); Filter aus 9 als `zweck_gleich`,
  `zweck_aehnlich`, `zweck_leer=true`, `empfaenger_aehnlich` (Parameter wie M27).
- Adresse `/statistik`: `konto=<id>`.

### 37.4 Wiederkehrende Buchungen aus der Bedienung entfernt (D-146)

Entfallen in der Oberfläche (die REST-Endpunkte bleiben):
- Seite `/wiederkehrend` samt `wiederkehrend-tabelle`, Menüs je Serie (`wk-menue-…`, `km-serie-…`).
- Kontextmenüeintrag „Warum wiederkehrend?“ (`km-wiederkehrend`, M16, auch mit Alt) und Begründungsdialog.
- Abschnitt Betragsfilter in den Einstellungen (`wk-vorgabe-…`, `wk-filter-…`, M25).
- Marke „↻“ der Buchungsliste: Zeilen tragen kein `data-wiederkehrend` mehr (M22 3.1).
- Auf `/erwartet`: Chip `erwartet-grund-serie`, Serienzeilen und `km-erwartung-serie`/`km-erwartung-konto`
  (M24); die Seite fragt keine Serien mehr ab und zeigt nur Erwartungen aus Mails und manuelle.

### 37.5 Tabs: Kontextmenü (ergänzt `oberflaeche.md` 27)

- Rechtsklick auf einen Tab (`role="tab"` in `tab-leiste`) und Umschalt+F10/Kontextmenütaste auf einem
  fokussierten Tab öffnen `kontextmenue` (`aria-label` „Tab „<Titel>““) mit
  `km-tab-schliessen` „Schließen“, `km-tab-andere` „Andere Tabs schließen“ (bei nur einem Tab
  `aria-disabled="true"`), `km-tab-alle` „Alle Tabs schließen“.
- Schließen wirkt wie ×. „Andere“ behält den angeklickten Tab; war er nicht aktiv, wird er aktiv und
  gezeigt. „Alle“ leert die Leiste; danach zeigt die Oberfläche die Finanzübersicht (wie nach dem
  Schließen des letzten Tabs, M17). Der gespeicherte Tab-Zustand (M17) folgt.
- Mobil öffnet eine lange Berührung auf einem Tab dasselbe Menü.

### 37.6 Kontoblatt: Gruppierung nach Datum (D-150 bis D-152)

- Über der Liste die Gruppe „Buchungen gruppieren“ (`role="group"`) mit den Knöpfen
  `gruppierung-keine` „Keine“ und `gruppierung-datum` „nach Datum“ (`aria-pressed`), daneben
  `gruppierung-zu` „Alles zusammenklappen“ und `gruppierung-auf` „Alles aufklappen“.
- „nach Datum“ setzt `?gruppierung=datum` (kein Parameter von `GET /api/buchungen`), „Keine“ entfernt
  ihn. Direkter Aufruf mit dem Parameter gruppiert sofort; andere Werte gelten als „Keine“.
- Gruppiert lädt das Blatt **alle** Buchungen des aktuellen Filters (Seiten zu 500, M27/M1-Filter
  unverändert); „Weitere laden“ entfällt dann.
- Darstellung: Jahre, darin Monate, darin Tage, darin die Buchungen. Reihenfolge der Knoten folgt der
  Datumsrichtung der Sortierung (Sortierung `datum` aufsteigend, sonst absteigend); Buchungen eines Tages
  in der Reihenfolge der Liste.
- Jeder Knoten ist ein Balken (`role="row"`, `data-periode` = Schlüssel, `data-ebene` = `jahr`|`monat`|`tag`)
  mit Knopf `periode-<Schlüssel>` (`aria-expanded`), Text „JJJJ“, „<Monatsname> JJJJ“ bzw. „TT.MM.JJJJ“, und
  den Zahlen `periode-eingang-<S>` (Summe der positiven Beträge), `periode-ausgang-<S>` (Summe der
  negativen), `periode-summe-<S>` (beides zusammen) – jeweils mit `data-betrag` in Cent – und
  `periode-anzahl-<S>` (`data-anzahl`, Text „1 Buchung“/„n Buchungen“). Schlüssel: `JJJJ`, `JJJJ-MM`,
  `JJJJ-MM-TT`. Betrag je Buchung = Feld `betrag` der Buchungsliste.
- Anfangs ist alles aufgeklappt. Klick auf Balken oder Knopf klappt um; ein zugeklappter Knoten verbirgt
  alle Ebenen darunter (Balken und Buchungen sind dann nicht im Dokument). Auf einem fokussierten
  Periodenknopf: Pfeil links klappt zu, Pfeil rechts klappt auf.
- `gruppierung-zu` klappt alle Jahre, Monate und Tage zu, `gruppierung-auf` alle auf. Beide sind
  deaktiviert ohne Gruppierung, `gruppierung-zu` wenn schon alles zu, `gruppierung-auf` wenn alles auf.
- Auswahl, Tastatur (Pfeile über sichtbare Buchungen), Kontextmenü und Einzelheiten wirken wie ohne
  Gruppierung auf die sichtbaren Buchungen.

### 37.7 Kontoblatt: Ausschnitt bei langen Listen (D-151)

- Hat die Liste mehr als **100** Einträge (Buchungszeilen plus Periodenbalken), sind nur die Einträge im
  sichtbaren Bereich samt kleinem Puffer im Dokument; die Liste behält die volle Scrollhöhe. Rollen zeigt
  die übrigen Einträge.
- Prüfbarkeit (37.14 C3): Die Liste trägt dann `aria-rowcount` = Anzahl aller Einträge
  (einschließlich Kopfzeile), jeder gezeichnete Eintrag `aria-rowindex` (Kopf = 1). Tests ermitteln die
  vollständige Reihenfolge durch Rollen und Sammeln nach `aria-rowindex`.
- Sprungziele (M16/M17/M21: `?buchung=`, Gegenbuchung, Mail-Blatt) zeichnen die Zielbuchung, wählen,
  fokussieren und rollen sie wie bisher in die Mitte.

### 37.8 Kontoblatt: Bearbeiten über Stifte in den Einzelheiten (D-161, ersetzt Inline-Bearbeitung aus
`oberflaeche.md` 8.3 und M12 23.1 per Doppelklick)

- **Doppelklick** auf eine Zelle der Buchungsliste öffnet **keinen** Editor mehr (weder Empfänger, Status,
  Betrag noch Verwendungszweck); er tut nichts außer der Auswahl.
- F2 und `km-bearbeiten` („Verwendungszweck bearbeiten“) öffnen weiterhin den Editor `inline-editor`
  für den Verwendungszweck in der Zeile (wie bisher).
- Im Panel Einzelheiten hat jeder Bestandteil einen Stift (`button`, `data-testid` `stift-<feld>`,
  `aria-label` „<Name> bearbeiten“): `stift-datum`, `stift-empfaenger`, `stift-verwendungszweck`,
  `stift-splits` (öffnet den Split-Dialog), `stift-tags` (Tag-Auswahl), `stift-status`.
  - Datum, Empfänger, Verwendungszweck, Status: Der Editor (`inline-editor`, `data-feld`) erscheint in der
    Zeile der Einzelheiten (Datumfeld, Empfängerauswahl, Textfeld, Statusauswahl). Enter oder Verlassen
    übernimmt, Esc bricht ohne Anfrage ab; Auswahllisten übernehmen bei Änderung. Wirkung wie bisher
    (PATCH bzw. Statusänderung mit Rückfrage bei `abgeglichen`, M12), ein Rückgängig-Schritt.
  - Bei abgestimmten oder abgeglichenen Buchungen sind alle Stifte außer `stift-status` und `stift-tags`
    deaktiviert.
- Der Betrag wird über den Split-Dialog bearbeitet (kein eigener Stift).

### 37.9 Kontoblatt: Kontextmenü (ergänzt `oberflaeche.md` 9, M12, M15, M17, M18)

Reihenfolge der Einträge einer Buchungsauswahl (Desktop, ohne Alt):
`km-kategorie`, `km-tags`, `km-splitten`, `km-dublette`, `km-vorschlag-annehmen`,
`km-vorschlag-ablehnen`, `km-bearbeiten`, `km-status`, `km-bestaetigen` (nur mit Person),
`km-filter`, `km-mehrfach`, `km-gegenbuchung`, `km-dokument-anhaengen`, `km-dokument-mail`,
`km-dokumente-ansehen`, `km-loeschen`. Mobil zusätzlich `km-dokument-foto` nach
`km-dokument-anhaengen`.

- **Kürzel-Anzeige:** Einträge mit Kürzel (Abschnitt 11) zeigen es rechts nur als Darstellung; der
  Text des Eintrags (`textContent`) bleibt unverändert (z. B. genau „Gehe zur Gegenbuchung“). Mobil keine
  Kürzel.
- **Verschieben (D-160):** `km-verschieben` „Auf anderes Konto verschieben…“ erscheint nur, wenn das Menü
  mit gehaltener **Alt**-Taste geöffnet wird (Alt+Rechtsklick, Alt+Umschalt+F10, Alt+Kontextmenütaste),
  dann vor `km-loeschen`; mobil immer; in der Kategorie-Ansicht nie. Der Knopf `konto-verschieben` in der
  Titelzeile entfällt. `mehrfach-verschieben` in der Auswahlleiste nur mobil.
- **Filter (D-158):** `km-filter` „Filter“ (aktiv bei genau einer Buchung) öffnet das Untermenü
  `untermenue` (Pfeil rechts, Klick, Mauszeiger) mit
  - `km-filter-empfaenger` „gleicher Empfänger“ (deaktiviert ohne Empfänger): setzt den Filter Empfänger
    auf deren Empfänger;
  - `km-filter-zweck` „Gleicher Verwendungszweck“: Filter `zweck_gleich` = Verwendungszweck (leerer
    Zweck: `zweck_leer=true`);
  - `km-filter-zweck-aehnlich` „ähnlicher Verwendungszweck“: `zweck_aehnlich` (leer: wie oben);
  - `km-filter-empfaenger-aehnlich` „ähnlicher Empfänger“ (deaktiviert ohne Empfänger):
    `empfaenger_aehnlich` = Empfängername.
  Wirkung: die übrigen Werte dieser Gruppe werden ersetzt, Auswahl geleert, Filterleiste geöffnet und zeigt
  den gesetzten Wert (zurücksetzbar über `filter-zuruecksetzen` und das jeweilige Feld), Adresse und Liste
  wie bei jedem Filter. Bedeutung der Filter: M27.
- **Als Dublette markieren (D-165):** `km-dublette` ist aktiv bei genau einer Buchung mit offenem Verdacht
  (wie bisher) **oder** bei genau zwei gewählten Buchungen. Für zwei Buchungen öffnet sich der bisherige
  Dublettendialog (`dublette-erklaerung`, je Buchung `dublette-zusammenfuehren-<id>` „Diese behalten“,
  „Keine Dublette“, `dublette-abbrechen`). Abbrechen speichert nichts (keine Anfrage). „Diese behalten“
  bzw. „Keine Dublette“ legt den Verdacht an und löst ihn in einem Rückgängig-Schritt auf (REST M27);
  jede der beiden kann behalten werden. Bei drei und mehr Buchungen deaktiviert.

### 37.10 Bestätigen durch eine Person, Label „Verdächtig“ (D-155 bis D-159)

- **Bestätigen einer Buchung:** `km-bestaetigen` (nur mit gewählter Person), Kürzel `b`, und in den
  Einzelheiten der Absatz `buchung-bestaetigung` („Bestätigt von A und B.“ bzw. „Noch von niemandem
  bestätigt.“) mit Knopf `buchung-bestaetigen` (ohne Person statt des Knopfs „Oben rechts wählen, wer du
  bist.“).
  - Text: „Als <Person> bestätigen“; tragen alle Ziele schon den Namen der Person: „Bestätigung von
    <Person> zurücknehmen“.
  - Bestätigen setzt an alle Ziele den Tag mit dem Namen der Person (wird bei Bedarf angelegt) und setzt
    Buchungen im Status `importiert` auf `bestaetigt`; andere Status bleiben (auch `vorlaeufig`).
    Zurücknehmen entfernt nur den eigenen Namen, der Status bleibt. Beide Personen können dieselbe Buchung
    bestätigen. Ein Strg+Z nimmt Tag und Status zusammen zurück.
  - Darstellung: Personen-Tags in der Spalte Tags mit `data-person` = Name; die Zeile trägt
    `data-bestaetigt` = Namen durch Leerzeichen getrennt.
- **Label „Verdächtig“:** Trägt eine Buchung laut REST ein Feld `verdacht` (M27), zeigt die Spalte Tags
  zusätzlich `data-testid="verdacht"` mit Text „Verdächtig“, `data-grund` = `verdacht.grund`, `title` und
  `aria-label` = `verdacht.text`; die Zeile trägt `data-verdacht` = Grund; die Einzelheiten zeigen
  `verdacht-erklaerung` mit `verdacht.text`. Ohne Feld nichts davon. Nach Bestätigen (Status `bestaetigt`)
  verschwindet das Label mit dem Neuladen.
- **Empfänger bestätigen (D-156):** Seite `/empfaenger`, Spalte „Bestätigt“ mit Personen-Tags
  (`data-person`), Zeile mit `data-bestaetigt`. Je Zeile Knopf `empfaenger-bestaetigen-<id>` „Als <Person>
  bestätigen“ / „Bestätigung von <Person> zurücknehmen“ (ohne Person deaktiviert); Kopfknopf
  `empfaenger-bestaetigen` für die Auswahl („Auswahl als <Person> bestätigen“, deaktiviert ohne Person oder
  Auswahl); Kontextmenü `em-bestaetigen`. Wirkung: Tag der Person an den Empfängern setzen/entfernen
  (REST M27, `tag_ids`), je Aktion ein Rückgängig-Schritt. Zusammenführen behält die Bestätigungen am Ziel.

### 37.11 Kontoblatt: Tastaturkürzel (D-167)

Einzelne Tasten ohne Strg/Alt/⌘; wirksam nur, wenn der Fokus im Kontoblatt außerhalb von Textfeldern,
Auswahllisten, Dialogen, Menüs und dem Kategorienbaum liegt. Ziel der Aktionen: die markierten Buchungen,
ohne Markierung die fokussierte.

| Taste | Wirkung |
| --- | --- |
| `k` | Kategorie setzen (wie `km-kategorie`) |
| `t` | Tags (wie `km-tags`) |
| `s` | Status setzen (wie `km-status`) |
| `b` | als Person bestätigen bzw. zurücknehmen (wie `km-bestaetigen`); ohne Person Hinweis |
| `a` / `A` | Vorschlag annehmen / ablehnen |
| `e` | Bearbeiten… (`km-mehrfach`) |
| `x` | Splitten… (nur genau eine) |
| `d` | Als Dublette markieren… (Bedingung wie 9; sonst Hinweis) |
| `g` | Gehe zur Gegenbuchung (genau eine; ohne Gegenbuchung Hinweis) |
| `m` / `M` | Dokument anhängen… / E-Mail anhängen… |
| `n` | Neue Buchung erfassen |

Vortaste **`f` (Filter):** `f` Filterleiste ein/aus; `v` Von; `b` Bis; `z` Verwendungszweck; `e` Empfänger;
`k` Kategorie (in einer Kategorie: Konto); `t` Tag; `s` Status; `r` Betrag ab; jeweils Fokus ins Feld (Leiste
wird geöffnet); `u` mit Unterkonten umschalten; `U` mit Unterkategorien umschalten (in Kategorien Hinweis);
`.` gleicher Empfänger, `,` gleicher Verwendungszweck, `;` ähnlicher Verwendungszweck wie die markierte
Buchung (wie 9); `m`/`l`/`j` Zeitraum dieser Monat / letzter Monat / dieses Jahr (nach Browserdatum, setzt
Von/Bis); `0` alle Filter zurücksetzen. Esc in einem Filterfeld setzt den Fokus zurück in die Liste.

Vortaste **`v` (Ansicht):** `g` Gruppierung Keine ↔ nach Datum; `+`/`-` alles auf-/zuklappen; `o`
Sortierspalte wechseln; `r` Sortierrichtung umkehren; `d`/`k` Panel Einzelheiten/Kategorien ein-/ausklappen;
`a` Spaltenbreiten an den Inhalt; `0` Spaltenbreiten zurücksetzen; `,` Konto-Einstellungen.

- Nach einer Vortaste erscheint `kuerzel-hinweis` (`role="status"`, `data-vortaste` = `f`|`v`) mit den
  möglichen zweiten Tasten. Esc bricht ab (Hinweis verschwindet), Umschalt allein bricht nicht ab, eine
  unbelegte zweite Taste wird gemeldet (Meldung) und bricht ab.
- `?` (Tastaturhilfe `tastatur-hilfe`) zeigt im Kontoblatt zusätzlich die Tabellen
  `tastatur-hilfe-aktionen`, `tastatur-hilfe-filter`, `tastatur-hilfe-ansicht`.
- Befehlspalette im Kontoblatt: zusätzlich je Kürzel ein Eintrag „Kontoblatt (<Gruppe>): <Text> [<Taste>]“
  hinter den übrigen Befehlen; Auswahl führt die Wirkung aus. Außerhalb des Kontoblatts keine solchen
  Einträge.
- Bild↑/Bild↓ in der Liste bewegen die Auswahl seitenweise.

### 37.12 Weitere Seiten

#### 37.12.1 Mail-Blatt `/mail` (D-147, D-153 bis D-155)

- Kopf „Mail-Blatt“ mit `mail-abrufen` („Mails abrufen“; während des Abrufs deaktiviert, Text „Abruf
  läuft…“; danach `mail-abruf-ergebnis` je Postfach „<Adresse>: n neu, m schon da“ bzw. Fehlermeldung).
- `mail-stand`: je Postfach `mail-postfach-<id>` („<Name>: n Mails, zuletzt erfolgreich …“, „noch nie
  abgerufen“, „inaktiv“, „letzter Abruf fehlgeschlagen (…)“); ohne Postfach „Kein Postfach eingerichtet.“
- `mail-filter`: Auswahl `mail-konto` („Alle Konten“ und je Postfach Bezeichnung oder Adresse) und die Chips
  `mail-filter-alle`, `-zugeordnet` („Buchung zugeordnet“), `-erwartet` („Nur erwartet“), `-keine`
  („Nicht erkannt“) mit `aria-pressed` und der Anzahl in Klammern aus `stand` (M27); Zahlen und Liste
  gelten für das gewählte Postfach.
- `mail-blaetter`: `mail-neuer` „Neuere“, `mail-block` („a–b von n (neueste|älter)“ bzw. „Keine Mails in
  dieser Auswahl“), `mail-aelter` „Ältere“; 100 Mails je Seite, neueste zuerst.
- `mail-liste`: Tabelle `mail-tabelle` (Empfangen, Absender mit Postfach, Betreff bzw. „(ohne Betreff)“,
  Zuordnung kurz) mit Zeilen `mail-<id>` (`aria-selected`, `data-zuordnung` = `zugeordnet`|`erwartet`|
  `keine`); leer `mail-leer` mit erklärendem Text; während des Ladens `mail-laden`.
- Auswahl: Klick wählt; anfangs die erste Mail der Seite (bzw. `?id=`). Pfeil ↓/↑ (Fokus nicht in Feld,
  Knopf oder Link) wählt die nächste/vorige; am Seitenende bzw. -anfang wird die nächste/vorige Seite
  geladen und deren erste/letzte Mail gewählt. Enter auf einer Zeile setzt den Fokus in den Inhalt.
- Inhalt `mail-lesen`: Betreff, Von, Postfach, Empfangen, Stand; `mail-zuordnungen` mit je Erwartung
  `mail-erwartung-<id>` (`data-zustand`, Link nach `/erwartet?id=<id>`, Kennung, Betrag, Zustand) und deren
  Buchungen: Knopf `mail-buchung-<bid>` („TT.MM.JJJJ <Empfänger|Konto>“) springt ins Kontoblatt des Kontos
  zur Buchung (wie Gegenbuchung, M17); `mail-warum-<bid>` nennt den Grund der Zuordnung (M27); ohne
  Zuordnung `mail-ohne-zuordnung`. `mail-text` = Text der Mail.
- Desktop: Liste und Inhalt nebeneinander mit getrennten Rollbereichen (Rollen der Liste bewegt den Inhalt
  nicht). Mobil Inhalt unter der Liste.

#### 37.12.2 Statistische Analyse `/statistik` (D-145, experimentell)

- Kopf „Statistische Analyse“ mit `statistik-konto` (offene Bestandskonten; Vorgabe erstes bzw. `?konto=`;
  Wechsel ändert die Adresse und lädt). Hinweistext beginnt mit „Experimentell.“
- Abschnitte `statistik-fixkosten`, `statistik-reihen`, `statistik-ungewoehnlich`, `statistik-rauschen`,
  `statistik-ausgeschlossen` aus `GET /api/statistik` (M27). Ohne Bestandskonto „Kein Bestandskonto
  vorhanden.“ Inhaltliche Werte werden nicht in der Oberfläche getestet (experimentell); geprüft werden
  Erreichbarkeit, Abschnitte, Kontowechsel und keine Konsolenfehler.

#### 37.12.3 Empfänger markieren (D-166, ergänzt `oberflaeche.md` 22.3)

- Tabelle `empfaenger-liste` (`aria-multiselectable="true"`), Zeilen `empfaenger-<id>` mit
  `aria-selected`; Kästchen `empfaenger-auswahl-<id>` bleiben und spiegeln die Auswahl;
  `empfaenger-auswahl-anzahl` (`data-anzahl`, Text „n ausgewählt“/„keine Auswahl“).
- Maus: Klick wählt genau einen, Strg/⌘-Klick schaltet um, Umschalt-Klick Bereich ab Anker,
  Strg+Umschalt-Klick fügt Bereich hinzu; Doppelklick öffnet `empfaenger-dialog`.
- Tastatur auf einer Zeile: Pfeile, Pos1/Ende (wählen), Umschalt+Pfeil (Bereich), Strg+Pfeil (nur Fokus),
  Leertaste (umschalten), Strg+A (alle), Esc (Auswahl aufheben), Enter/F2 (Dialog), Umschalt+F10 /
  Kontextmenütaste (Menü).
- Rechtsklick auf eine nicht markierte Zeile markiert nur sie. Menü: `em-zusammenfuehren`
  „n Empfänger zusammenführen…“ (ab zwei; derselbe Dialog wie `empfaenger-zusammenfuehren`),
  `em-bestaetigen` (mit Person), `em-bearbeiten` (genau einer). Mobil: Tippen schaltet um, lange Berührung
  öffnet das Menü.

#### 37.12.4 Split-Dialog und Split-Vorlagen (D-162 bis D-164)

- Split-Dialog: je Zeile `split-ausgleichen-<i>` „Split Ausgleichen“: setzt den Betrag dieser Zeile auf die
  negative Summe der übrigen Zeilen (ganze Cent; leere/ungültige zählen 0; Rest 0 → 0), ohne zu speichern.
- Darunter `split-vorlage-name` (Vorgabe: Empfängername, sonst Verwendungszweck) und `split-vorlage`
  „Diesen Split zur Vorlage machen“: legt eine Split-Vorlage an (Teile = Kategorie-Teile mit Betrag und
  Memo, Bedingung Empfänger gleich), Meldung, ein Rückgängig-Schritt; der Dialog bleibt offen.
- Seite `/vorlagen`: je Vorlage `vorlage-<id>` mit `vorlage-regel-<id>` („Empfänger <x> · Splitbetrag
  <Betrag>“, `vorlage-empfaenger-<id>`, `vorlage-splitbetrag-<id>` mit `data-betrag` = Gesamtbetrag), Felder
  `vorlage-empfaenger-feld-<id>`, `vorlage-splitbetrag-feld-<id>`, `vorlage-regel-speichern-<id>`,
  `vorlage-loeschen-<id>` (mit Rückfrage). Speichern setzt die Bedingung Empfänger gleich und verteilt eine
  geänderte Summe in ganzen Cent auf einen Teil (kein Teil wird 0, Summe nicht 0; sonst Fehlermeldung).

#### 37.12.5 Dubletten (D-165)

- Seite `/dubletten`: Hinweis `dubletten-regel` zur Vorschlagsregel; Vorschläge (REST M27) erscheinen
  wie offene Verdachte und lassen sich mit „Diese behalten“ / „Keine Dublette“ auflösen.

#### 37.12.6 Darstellung leerer Werte (D-154)

- Fehlende Werte erscheinen in keiner Seite als die Wörter „null“, „None“ oder „undefined“. Texte aus dem
  Buchbestand werden unverändert gezeigt (37.14 C2).

#### 37.12.7 Listenbreite (D-168)

- Die Buchungsliste wächst ohne eigene Spaltenbreiten nicht nach dem längsten Inhalt: Bei einem
  Verwendungszweck von 300 Zeichen ist die Liste im Desktop (1280 px, Panels offen) nicht breiter als ihr
  Bereich und liegt nicht unter dem Panel Einzelheiten. Eigene Breiten (M22) wie bisher.

### 37.13 Abgelöste Festlegungen und frühere Tests

Abschnitt 13 der Definition ordnet die Abweichungen der früheren Browsertests zu (A: Person in allen
Browsertests, B: Navigation/Routen/Palette, C: wiederkehrende Buchungen, D: kein Doppelklick-Bearbeiten,
E: Verschieben nur mit Alt, F: Ausschnitt langer Listen, G: Meldung über langem Menü, H: M26, I: REST M27,
J: Speicher gesperrt). Umsetzung: E-253 (A, J) und E-254 (B–G, I).

### 37.14 Bekannte Abweichungen der Anwendung (Codefehler der Definition)

- C1: Ohne Browser-Speicher wird die gewählte Person nicht im Arbeitsspeicher gehalten (verlangt: volle
  Funktion ohne Speicher, 27.1/M17 1.6).
- C2: Wörter „null“, „None“, „undefined“ werden auch aus Texten des Buchbestands entfernt (verlangt:
  unverändert, 37.12.6).
- C3: Im Ausschnitt fehlen `aria-rowcount`/`aria-rowindex` (verlangt: 37.7).
- C4: Die Tastaturhilfe nennt Alt+1 … Alt+8 (verlangt: Alt+1 … Alt+7).

## 38. Meilenstein 29: Bankzugang in den Einstellungen

Übernahme von Abschnitt 7 der Definition „Bankabruf über FinTS/camt und
Bankzugang in der Oberfläche“ (E-258). REST: `bankzugang.md` 4. Browsertests,
keine `kern`; Prüfmerkmale: E-265.

Die Seite „Einstellungen“ (`/einstellungen`) zeigt einen Abschnitt
`bankzugang` mit den Attributen `data-aenderbar` und `data-vollstaendig`
(`ja`/`nein`, aus `GET /api/bank/zugang`).

Ist der Zugang nicht änderbar (Mock-Modus), enthält der Abschnitt nur den
Hinweis `bankzugang-hinweis` (keines der Elemente der folgenden Tabelle).

Sonst:

| `data-testid` | Element |
| --- | --- |
| `bankzugang-url`, `-blz`, `-benutzer`, `-kunden_id`, `-produkt_id` | Eingabefelder, vorbelegt mit den wirksamen Werten |
| `bankzugang-tan-verfahren` | Auswahl (`<select>`); erster Eintrag „automatisch“ (leerer Wert), dazu der gespeicherte Wert und nach dem Abruf die Verfahren der Bank (Wert = dreistellige Nummer) |
| `bankzugang-speichern` | speichert die Felder (`PUT /api/bank/zugang`) |
| `bankzugang-pin`, `bankzugang-pin-senden` | Kennwortfeld (`type="password"`) und Knopf; übergibt die PIN an den Arbeitsspeicher des Servers (`PUT /api/sync/pin`), das Feld ist danach leer |
| `bankzugang-pin-status` | `data-vorhanden` `ja`/`nein` |
| `bankzugang-verfahren-abrufen` | füllt die Auswahl der TAN-Verfahren (`POST /api/bank/zugang/tan-verfahren`) |
| `bankzugang-konten-abrufen` | ruft die Konten ab (`POST /api/bank/zugang/konten/abrufen`) |
| `bankzugang-meldung` | Statuszeile, `data-art` `hinweis` oder `fehler`; verborgen ohne Text |
| `bankzugang-tan` | Bereich der TAN-Anforderung, sonst verborgen: `bankzugang-tan-challenge`, `bankzugang-tan-bild` (nur mit Grafik), `bankzugang-tan-eingabe`, `bankzugang-tan-senden` |
| `bankzugang-konten` | Liste der Konten; je Konto ein Ankreuzfeld `bankzugang-konto` mit `data-iban` (dieses `data-testid` kommt je Konto einmal vor, Ausnahme von 1); dazu `bankzugang-konten-speichern` (`PUT /api/bank/zugang/konten`) |
| `bankzugang-diagnose` | Ankreuzfeld `bankzugang-diagnose-aktiv`, Knöpfe `bankzugang-diagnose-laden` und `bankzugang-diagnose-kopieren`, Ausgabe `bankzugang-diagnose-zeilen` mit `data-zeilen` (Anzahl) |

Verhalten:

- „TAN-Verfahren abrufen“ und „Konten abrufen“ speichern zuerst geänderte
  Felder; scheitert das Speichern, wird die Bank nicht angesprochen.
- Validierungsfehler erscheinen in der Statuszeile mit Feldname und Meldung
  (`data-art="fehler"`).
- Verlangt der Kontenabruf eine TAN, erscheint der TAN-Bereich. Nach einer
  falschen TAN bleibt er offen und das Eingabefeld ist leer; nach Erfolg oder
  einem anderen Fehler verschwindet er.
- Nach dem Abruf zeigt die Statuszeile die Anzahl der Konten; bei null Konten
  eine Fehlermeldung.
- Ohne abgerufene Konten nennt die Liste, dass dann alle Konten der Bank
  synchronisiert werden.
- Stammen alle Angaben aus der Vorbelegung, steht ein Hinweis darauf unter
  dem Abschnitt.
- Der Abschnitt lädt keine Ressourcen von außen und nutzt keinen
  Browser-Speicher. PIN und TAN stehen nie in der Adresse, nie im
  Browser-Speicher und nach dem Absenden nicht mehr im Dokument.

## 39. Meilenstein 30: Ausdrucksfeld, Filter im Kontoblatt, Regeleditor, Anwenden-Fenster, Tag-Dialog

Übernahme der Abschnitte 7 bis 10 der Definition „Kontor-Ausdrücke …“ und
ihres Nachtrags 1 (`spec/definitionen/definition-2-…`, E-268). Ändert 7.1,
12.2, 16.3, 22.2, 23.1, 27, 36.3, 36.6 und 37.9/37.11 (39.7). Geprüft wird
nur, was hier genannt ist (E-274); Texte nur, wo sie wörtlich dastehen.

### 39.1 Ausdrucksfeld

Ein Ausdrucksfeld mit der Kennung `<k>` besteht aus dem Textfeld `<k>`, der
Marke `<k>-status` (`data-status`: `leer`, `pruefe`, `ok`, `fehler`) und der
Zeile `<k>-fehler`.

- Die Eingabe wird nach kurzer Tipppause geprüft (`POST
  /api/ausdruck/pruefen`). Bei einem Fehler trägt das Textfeld
  `aria-invalid="true"`, die Fehlerzeile nennt Spalte und Meldung, und die
  Fehlerstelle ist hervorgehoben.
- Felder, Kurzformen, Schlüsselwörter und Datumswörter werden zur
  Vervollständigung angeboten.
- Das Feld wächst mit dem Inhalt. Statt eines Code-Editors gibt es ein
  Textfeld mit Hervorhebung.

### 39.2 Filter im Kontoblatt (ersetzt 7.1 und 23.1)

| `data-testid` | Element |
| --- | --- |
| `filter-ausdruck` | Ausdrucksfeld (Kontext `filter`) über der Liste, immer sichtbar |
| `filter-zusammenfassung` | Teile des Filters in Worten und Zahl der Buchungen |
| `filter-schnell-<wert>` | Zeitraum: `heute`, `-7d`, `-30d`, `dieser_monat`, `letzter_monat`, `dieses_jahr`, `letztes_jahr` |
| `filter-ausdruck-leeren` | leert den Filter |
| `filter-ausdruck-menue` | „Jahr festschreiben“, „Als Regel speichern…“ |
| `filter-baukasten-umschalten` | klappt den Baukasten ein und aus (`aria-expanded`), trägt `filter-anzahl` mit `data-anzahl` |
| `filter-leiste`, `filter-baukasten` | Baukasten; Zeilen `bk-<n>-feld`, `bk-<n>-op`, `bk-<n>-wert`, `bk-<n>-weg` |
| `filter-baukasten-hinweis` | erscheint, wenn der Ausdruck nicht in den Baukasten passt |
| `filter-zuruecksetzen` | setzt alle Filter zurück |
| `filter-alt-<name>` | Filter ohne Entsprechung im Ausdruck; `<name>` ist der Name des Adressparameters |

- Gefiltert wird nach kurzer Tipppause oder Enter, aber nur mit gültigem
  Ausdruck. Bei einem Fehler bleibt die letzte gültige Liste stehen.
- Der Filter steht in der Adresse als `filter=…`.
- Treffer in Empfänger und Verwendungszweck sind hervorgehoben.
- Ein Zeitraum-Knopf ersetzt einen vorhandenen `datum`-Teil auf oberster
  Ebene oder hängt ihn mit `and` an.
- Der Baukasten ist beim Öffnen einer Kontoansicht eingeklappt (`filter-leiste`
  nicht sichtbar, `filter-baukasten-umschalten` mit `aria-expanded="false"`).
  Baukasten und Ausdrucksfeld sind gekoppelt: Eine Änderung im einen
  schreibt das andere.
- Der Baukasten ersetzt die bisherigen Einzelfelder (Von, Bis, Betrag,
  Empfänger, Verwendungszweck, Freitext, Kategorie, Tag, Status:
  `filter-von`, `filter-bis`, `filter-betrag-min`, `filter-betrag-max`,
  `filter-empfaenger`, `filter-verwendungszweck`, `filter-freitext`,
  `filter-kategorie`, `filter-unterkategorien`, `filter-tag`,
  `filter-status-<status>`). Den Knopf `filter-umschalten` gibt es nicht
  mehr. `filter-unterkonten` und `filter-konto` (22.2) nennt die Definition
  nicht; sie bleiben in `filter-leiste` (E-274).
- `filter-anzahl` trägt `data-anzahl` = 0 ohne Filter, sonst eine Zahl ≥ 1.
- Alte Adressen: `von`, `bis`, `empfaenger_id`, `ohne_empfaenger`,
  `verwendungszweck`, `zweck_gleich`, `zweck_leer`, `suche`, `kategorie_id`
  ohne Unterkategorien, `tag_id` und `status` werden beim Öffnen in den
  Ausdruck übernommen; die Liste zeigt dieselben Buchungen wie zuvor.
- Ohne Entsprechung im Ausdruck bleiben `betrag_min`, `betrag_max`,
  `zweck_aehnlich`, `empfaenger_aehnlich` und `kategorie_id` mit
  Unterkategorien; sie erscheinen als `filter-alt-<name>` mit
  Entfernen-Knopf.
- „Als Regel speichern…“ nennt die Teile, die nicht übernommen werden, und
  öffnet nach Bestätigung den Regeleditor mit dem Regel-Ausdruck
  (`POST /api/ausdruck/als-regel`).
- Tastenkürzel (ersetzen die Kürzel der Einzelfelder aus 37.11): `f a`
  Ausdrucksfeld, `f f` Baukasten, `f h`/`w`/`d`/`m`/`l`/`j`/`J` Zeiträume,
  `f x` Zeitraum entfernen.
- Die Einträge des Untermenüs `km-filter` (37.9) setzen weiter einen Filter
  mit derselben Trefferliste; ob er im Ausdruck oder als `filter-alt-<name>`
  erscheint, folgt den beiden Punkten über alte Adressen.

### 39.3 Regelliste (Seite `/regeln`)

Je Regel `regel-<id>` mit Griff `regel-griff-<id>`, Schalter
`regel-aktiv-<id>`, Name, Ziel `regel-ziel-<id>` und Ausdruck
`regel-ausdruck-<id>`; Knöpfe Bearbeiten, Duplizieren, Löschen.

- Das Ziel zeigt die Kategorie und je vergebenem Tag „+ Name“. Ohne
  Kategorie und ohne Tags steht „(keine Aktion)“.
- Reihenfolge per Ziehen oder Alt+↑/↓ am Griff; jede Änderung ist ein
  Rückgängig-Schritt (`regeln_reihenfolge`).
- `regel-anlegen` öffnet den Editor, `regeln-anwenden` bleibt.

### 39.4 Regeleditor (`regel-dialog`)

| `data-testid` | Element |
| --- | --- |
| `regel-name`, `regel-aktiv` | Name und Aktiv-Schalter |
| `regel-modus-baukasten`, `regel-modus-ausdruck` | Reiter; Vorgabe Ausdruck, die letzte Wahl wird gemerkt |
| `regel-ausdruck` | Ausdrucksfeld (Kontext `regel`) |
| `bk-<n>-feld`, `-op`, `-wert`, `-weg`, `bk-plus`, `bk-gruppe-plus` | Baukasten |
| `regel-baukasten-ausdruck`, `regel-ausdruck-kopieren` | erzeugter Ausdruck und Kopieren |
| `regel-baukasten-hinweis` | erklärt, warum der Baukasten nicht geht |
| `regel-uebernehmen` | Bedingung und Kategorie einer anderen Regel übernehmen |
| `regel-kategorie` | Kategorie; erster Eintrag „– keine Kategorie –“ mit leerem Wert |
| `regel-tag-eingabe`, `regel-tag-hinzufuegen` | Tag wählen oder neuen Namen eingeben |
| `regel-tags` | Tags der Regel; je Tag `regel-tag-entfernen-<name>` |
| `regel-prioritaet` | unter „Weitere Einstellungen“; leer = ans Ende |
| `regel-speichern`, `regel-speichern-anwenden` | Speichern |

- Passt ein Ausdruck nicht in den Baukasten, ist der Reiter gesperrt; es
  gehen keine Teile verloren.
- Die bisherige Zeilenform („empfaenger enthaelt Bäckerei“) wird weiter
  angenommen.
- Kategorie: Bei einer neuen Regel ist die erste Kategorie vorgewählt.
  „keine Kategorie“ ist vorgewählt bei einer Regel, die nur Tags vergibt.
- Tags: Enter, Komma oder „Hinzufügen“ übernimmt die Eingabe. Ein
  vorhandener Tag wird unabhängig von der Schreibung erkannt; ein Name kommt
  nur einmal vor. Ein unbekannter Name ist als „(neu)“ gekennzeichnet.
- Neue Tags entstehen erst beim Speichern, zusammen mit der Regel in einem
  Rückgängig-Schritt. Abbrechen legt nichts an.
- Speichern ohne Kategorie und ohne Tags meldet „Die Regel braucht eine
  Kategorie oder mindestens einen Tag.“ und markiert das Kategorie-Feld.
- Leerer Name: Der Name wird vorgeschlagen aus dem ersten Text der Bedingung
  und der Kategorie, ohne Kategorie den Tags mit `#` (z. B. „AMAZON →
  Amazon“, „Einkauf → #Urlaub“). Der Vorschlag steht als Platzhalter im Feld
  und wird beim Speichern übernommen.

### 39.5 Testbereich (`regel-test`) und Fenster „Regel anwenden“

| `data-testid` | Element |
| --- | --- |
| `regel-test-konto` | Quellkonto, Vorgabe alle Konten |
| `test-zeitraum-12m`, `-jahr`, `-vorjahr`, `-alle` | Zeitraum der getesteten Buchungen (`aria-pressed`), Vorgabe 12 Monate |
| `test-zahlen` | Zählzeile mit `data-anzahl` (Treffer) und `data-tags` (Treffer, die Tags erhielten) |
| `test-status` | Zustand der Aktualisierung |
| `test-wirkung-<wirkung>`, `test-wirkung-alle` | Einschränkung auf eine Wirkung, mit `data-anzahl` |
| `test-liste` | Treffer; je Buchung `test-treffer-<id>` mit Kopfzeile `test-zeile-<id>` |
| `test-uebernehmen-<id>`, `test-warum-<id>` | „→ Bedingung“ und „Warum?“ in den Einzelheiten |
| `test-leer`, `test-alle` | Hinweis ohne Buchungen im Zeitraum und „Alle Buchungen testen“ |
| `test-nicht-erfasst` | Buchungen mit der Kategorie, die nicht treffen |
| `regel-test-anwenden` | Anwenden |

- Ein eigenes Filterfeld für die Testmenge gibt es nicht. Die Bedingung der
  Regel filtert; eingrenzen lassen sich nur Zeitraum und Quellkonto.
- Der Test läuft nach jeder erfolgreichen Prüfung der Bedingung und nach
  jeder Änderung von Kategorie, Tags, Zeitraum oder Quellkonto. `regel-test`
  trägt `data-geladen` (`ja`/`nein`) und `data-veraltet` (`ja`/`nein`).
- Die Zählzeile lautet „n Treffer in m Buchungen (Zeitraum)“.
- Ohne Bedingung zeigt der Testbereich die Buchungen des Zeitraums.
  „→ Bedingung“ übernimmt `empf == "<Empfänger>" and dir == "<Richtung>"`,
  ohne Empfänger ein Wort aus dem Verwendungszweck.
- Ist die Bedingung ungültig, bleibt das letzte gültige Ergebnis als
  veraltet gekennzeichnet stehen. Scheitert der Test aus einem anderen
  Grund, verschwindet das alte Ergebnis und die Zählzeile nennt den Grund.
- Ohne gewählte Kategorie läuft der Test und zeigt die Treffer.
- Ein Klick auf eine Trefferzeile klappt die Einzelheiten auf:
  Verwendungszweck, Kategorie vorher → nachher, die Tags, die dazukämen,
  „→ Bedingung“ und „Warum?“.
- Anwenden-Knopf: ohne Tags „Auf n Buchung(en) anwenden…“; mit Kategorie und
  Tags „Anwenden: n × Kategorie, m × Tags…“; nur mit Tags „Tags an m
  Buchung(en) vergeben…“. Er ist gesperrt, wenn sich nichts ändern würde.

**Fenster „Regel anwenden“** (Nachtrag 1): Anwenden speichert eine neue oder
geänderte Regel zuerst und öffnet dann `regel-anwenden-dialog`.

| `data-testid` | Element |
| --- | --- |
| `regel-anwenden-umfang` | „Zeitraum: …“ mit dem gewählten Zeitraum in Worten (12 Monate, dieses Jahr, Vorjahr, alle), dazu das Quellkonto, wenn eines gewählt ist |
| `regel-anwenden-kategorie` | Zahl der unkategorisierten Buchungen und Name der Kategorie; fehlt bei Regeln ohne Kategorie und wenn es keine solche Buchung gibt |
| `regel-anwenden-abweichende` | Ankreuzfeld „auch n Buchung(en) mit anderer Kategorie überschreiben“; nur wenn es solche Buchungen gibt |
| `regel-anwenden-tags` | Zahl der Buchungen, die Tags erhalten, und die Tags; nur bei Regeln mit Tags |
| `regel-anwenden-nichts` | Hinweis, dass die Regel im gewählten Umfang nichts ändert |
| `regel-anwenden-ok` | führt aus (`POST /api/regeln/{id}/anwenden`); verborgen, wenn sich nichts ändern würde |

- Das Fenster zeigt nie den Ausdruck des Zeitraums und nie leere Platzhalter
  wie „null“.
- Nach dem Anwenden meldet die Oberfläche die Zahl der geänderten Buchungen
  oder „Keine Buchung geändert.“

### 39.6 Fehlermeldungen, Ressourcen

- Lehnt der Server eine Eingabe mit `validierung` ab, zeigen Dialoge und
  Meldungen zusätzlich zu „Die Anfrage ist ungültig.“ je betroffenem Feld
  den Feldnamen und die Regel, z. B. „Name: 1–200 Zeichen (ohne
  Rand-Leerraum).“. Übergebene Werte erscheinen nie.
- Die Oberfläche lädt für Ausdrucksfeld und Editor keine Ressourcen von
  außen.

### 39.7 Tag-Dialog im Kontoblatt (ergänzt 9.2, Nachtrag 1)

Der Dialog `tag-auswahl` öffnet sich wie bisher für eine oder mehrere
Buchungen (Kontextmenü, Taste `t`, Stift in den Einzelheiten,
`mehrfach-tags`).

- Neu ist `tag-auswahl-vorhanden` (`data-geladen` `ja`/`nein`): die Tags der
  gewählten Buchungen, nach Namen sortiert. Bei mehreren Buchungen steht je
  Tag „(alle)“ oder „(n von m)“. Ohne Tags steht „Noch keine Tags.“
- Je Tag gibt es den Knopf `tag-auswahl-weg-<tag-id>`. Er entfernt den Tag
  von allen gewählten Buchungen. Das ist eine Änderung `mehrfach_tags` und
  ein Rückgängig-Schritt. Der Dialog bleibt danach offen und zeigt den neuen
  Stand.
- `tag-auswahl-name`, `tag-auswahl-hinzufuegen` und `tag-auswahl-entfernen`
  verhalten sich unverändert: Hinzufügen legt einen unbekannten Tag zuerst
  an; Entfernen eines unbekannten Namens ist ein Fehler im Dialog ohne
  Anfrage; beide schließen den Dialog nach Erfolg.
- Sind mehr als 50 der gewählten Buchungen in der Liste noch nicht geladen,
  zeigt der Dialog die Tags der übrigen nicht und sagt das. Hinzufügen und
  Entfernen wirken trotzdem auf alle gewählten Buchungen.

### 39.8 Abgelöste Festlegungen und frühere Tests

- 7.1 (Tabelle der Einzelfelder, `filter-umschalten`), 23.1
  (`filter-umschalten`; der Anfangszustand „eingeklappt“ gilt jetzt für den
  Baukasten und `filter-baukasten-umschalten`), 12.2/37.11 (Kürzel der
  Einzelfelder), 36.3 Punkt zur Zeile mit `filter-umschalten` und 36.6.4
  (zweispaltige Filterleiste) gelten nicht mehr.
- Die Seite `/regeln` (13.10) hat zusätzlich die Elemente aus 39.3 bis 39.5.
- Angepasste und entfernte frühere Tests: E-271.

## 40. Meilenstein 31: Einzelheiten, Lernmodell, Einstellungen in Bereichen, Mail-Datum, Gruppierung, Berichtswahl

Übernahme der Abschnitte 1, 3, 6, 7, 8 und 9 der Definition 3 (E-277).
Browsertests, keine `kern`; Prüfmerkmale E-286 bis E-288. Nur, was hier
genannt ist, ist Vertrag.

### 40.1 Einzelheiten und Schreibweise von Namen (D-175 bis D-177)

- Kopf der Einzelheiten mit `details-betrag` (Summe der Splits auf dem
  angezeigten Konto, `data-betrag` in Cent), Datum, Status als Marke;
  Stifte und Editoren wie 37.8. Der Verwendungszweck wird nur in der Anzeige
  gegliedert (Buchungsarten, SEPA- und ausgeschriebene Schlüssel, PayPal,
  Amazon-Bestellnummern, Referenzen aufklappbar); gespeichert, gesucht und
  gefiltert wird der Originaltext.
- **Namen in normaler Schreibweise (nur Anzeige):** Ganz groß oder ganz klein
  geschriebene Empfängernamen erscheinen in der Buchungsliste der
  Kontoansicht, im Kopf der Einzelheiten, in Suchergebnissen und in den
  Einzelbuchungen der Berichte mit großem Anfangsbuchstaben je Wort (auch
  nach `-` und `/`), kleinen Wörtern mitten im Namen klein („CAFE AM MARKT“ →
  „Cafe am Markt“), bekannte Abkürzungen und Rechtsformen in üblicher Form.
  Gemischt geschriebene Namen bleiben unverändert. REST, Auswahllisten und
  Empfängerverwaltung zeigen den Namen wie erfasst.

### 40.2 Lernmodell (D-182, D-183)

- `lernmodell-anwenden` (Seite Regeln) heißt „Vorschläge für unkategorisierte
  Buchungen“ und ruft weiter `POST /api/lernmodell/anwenden`.
- Einzelheiten einer unkategorisierten Buchung ohne Vorschlag:
  `details-einschaetzung` mit `details-einschaetzung-grund` und
  `details-einschaetzung-kandidaten`; je Kandidat des Lernmodells ab 1 %
  (`POST /api/lernmodell/vorhersage`, `sicherheit ≥ 10`) ein Eintrag
  `details-kandidat-<kategorie_id>` mit „Übernehmen“.
- Erklärung `lern-warum` (aufklappbar) bei Vorschlägen des Lernmodells und
  bei Buchungen ohne Vorschlag (`GET /api/buchungen/{id}/lernmodell`).
- Neue Route `/lernmodell` (Seite „Lernmodell“), erreichbar von der Seite
  Regeln und aus der Erklärung; **kein** Eintrag in der Navigation (37.2
  bleibt bei 16 Links).

### 40.3 Einstellungen in Bereichen (D-207, ersetzt die Gliederung von 13.2)

- Sechs Bereiche, Kennung `<name>` (E-286): `allgemein` (Design, Layout,
  Angaben zur Instanz), `bank` (Bankzugang, PIN), `mail` (Postfächer, Abruf,
  OAuth-Client-Secret), `benachrichtigungen` (Zustellung, Test, ntfy-Token),
  `sicherheit` (Anmeldung, Abmelden, Passwort, Schutz der Geheimnisse),
  `daten` (Datensicherung, Tags). Der Abschnitt „Geheimnisse“ entfällt; jedes
  Geheimnis steht bei seiner Aufgabe.
- Adresse `/einstellungen?bereich=<name>`; unbekannter Wert wie ohne Angabe.
  Gezeigt wird genau ein Bereich (die übrigen sind im Dokument, aber
  `hidden`); ohne Angabe am Desktop `allgemein`, am Handy nur die Liste der
  Bereiche (Rückweg „Alle Einstellungen“). Die Einstellungen bleiben ein Tab.
- Navigation der Bereiche mit `einstellungen-status-<name>` je Bereich,
  `data-zustand` ∈ {`ok`, `offen`, `fehler`, `neutral`}.
- Suche `einstellungen-suche` über den Bereichen (Verzeichnis mit Synonymen;
  Einträge, die es in der Instanz nicht gibt, erscheinen nicht).
- „Erweitert“ (`<details>`, eingeklappt): Kunden-ID und Produkt-ID,
  Diagnoseprotokoll, OAuth-Client-Secret; offen von Anfang an, wenn darin
  etwas fehlt oder läuft (Produkt-ID leer, Diagnose eingeschaltet).
- Bankzugang in vier Schritten; Stand der PIN (`pin-status`) und
  `pin-verwerfen` im Bereich `bank` (im Mock-Modus als eigene Karte).
- Alle bisherigen `data-testid` bleiben; neu: `einstellungen-…`,
  `passwort-alt`, `passwort-neu`, `passwort-aendern`, `postfach-neu-adresse`,
  `postfach-neu-anlegen`, `mail-abrufen`. Keine Einträge je Bereich in der
  Befehlspalette.
- Zuordnung der bisherigen Elemente (E-286): `allgemein`: `einstellung-thema`,
  `layout-zuruecksetzen`, `status-modus`; `bank`: `bankzugang`, `pin-status`,
  `pin-verwerfen`; `mail`: `postfaecher`, `postfach-neu-adresse`,
  `mail-abrufen`, `geheimnis-oauth_client_secret`; `benachrichtigungen`:
  `zustellung-status`, `benachrichtigung-test`, `geheimnis-ntfy_token`;
  `sicherheit`: `abmelden`, `schutz-status`; `daten`:
  `sicherung-herunterladen`, `sicherung-datei`.

### 40.4 Datum angehängter E-Mails (D-210)

Im Abschnitt Dokumente der Einzelheiten steht bei jeder angehängten E-Mail
`dokument-datum-<id>` (Tag.Monat.Jahr in Ortszeit, `data-zeitpunkt` = voller
Zeitpunkt aus `GET /api/dokumente/{id}/mail` → `datum`); andere Dokumente und
Mails ohne lesbares Datum haben keines.

### 40.5 Gruppierung: Abschnitte und Tiefe (D-211, D-212; ergänzt 37.6)

- Ebenen Jahr → Monat → **Abschnitt** → Tag. Abschnitte je Monat fest:
  1.–7., 8.–14., 15.–21., 22. bis Monatsende; Schlüssel `JJJJ-MM-a1` …
  `JJJJ-MM-a4`, `data-ebene="abschnitt"`, Text nur der Datumsbereich mit dem
  tatsächlichen Monatsende (`08.–14.11.`, `22.–29.02.`, Halbgeviertstrich).
  Abschnitte ohne Buchung erscheinen nicht. Balken, Zahlen, Klappen, Pfeile,
  `gruppierung-zu`/`-auf` wie bei den übrigen Ebenen.
- Leiste „Keine | Jahr | Monat | Abschnitt | Tag“: `gruppierung-keine`,
  `gruppierung-jahr`, `gruppierung-monat`, `gruppierung-abschnitt`,
  `gruppierung-datum` („Tag“, volle Tiefe); genau einer `aria-pressed="true"`.
- Adresse `?gruppierung=datum&tiefe=jahr|monat|abschnitt`; ohne `tiefe` oder
  bei unbekanntem Wert volle Tiefe („Tag“, nicht in die Adresse geschrieben).
  Die gewählte Ebene ist die tiefste; die Buchungen stehen direkt darunter.
- `v g` schaltet keine → Jahr → Monat → Abschnitt → Tag → keine.
  Zugeklappte Perioden bleiben beim Wechsel der Tiefe zugeklappt.

### 40.6 Berichtswahl (D-217)

Alle Berichte unter `/berichte?art=<name>` in einem Tab (`uebersicht`,
`monat`, `vertraege`, `jahr`, `vorschau`, `vermoegen`, `kategorien`,
`empfaenger`, `geldfluss`, `qualitaet`, `tags`). Ohne `art` und mit
`art=uebersicht` die bisherige Seite (31) unverändert. `/berichte/monat`
führt zu `/berichte?art=monat`. Kein neuer Eintrag in Navigation oder
Palette.

## 41. Meilenstein 32: Oberfläche aus dem Sammelbranch `feature/sammel3`

Übernahme der Oberflächenteile der Definition 4 (E-293; fachlich
`sammel3.md`). Browsertests, keine `kern`; Lesarten E-306. Nur, was hier
genannt ist, ist Vertrag; Texte, Farben und Anordnung darüber hinaus nicht.

### 41.1 Navigation, Palette, Routen (ändert 37.2, 37.3)

- Gruppe `buchhaltung`: `navlink-tags` → `/tags` direkt nach `nav-kategorien`.
- Gruppe `auswertung`: nur noch `nav-berichte`; `navlink-statistik` entfällt.
- Gruppe `betrieb`: zusätzlich `navlink-konfiguration` → `/konfiguration`;
  die Stelle in der Gruppe ist nicht festgelegt (E-306). Auf dem Handy ist er
  nicht sichtbar (fehlt oder verborgen).
- Die übrigen Links bleiben in der Reihenfolge von 37.2 (Hilfe
  `m8.NAV_LINKS`, ohne `navlink-konfiguration`).
- Befehlspalette: `befehl-gehe-statistik` entfällt; neu `befehl-gehe-tags`
  („Gehe zu: Tags“) und `befehl-gehe-konfiguration` („Gehe zu:
  Konfiguration“), Stelle unter den „Gehe zu“-Einträgen nicht festgelegt; die
  übrigen in der Reihenfolge von 37.2.
- Routen `/tags` (`seite-tags`) und `/konfiguration` (`seite-konfiguration`)
  liefern bei direktem Aufruf die Hülle; `/statistik` → HTTP 404.

### 41.2 Empfänger (D-219, D-220, D-236/10)

- Keine Spalte und kein Feld „Standardkategorie“ mehr.
- Kontextmenü: `em-regel` („Regel erstellen…“) öffnet den Regeleditor
  (`regel-editor`, 39.3) mit dem Namen des Empfängers als Regelname und dem
  Ausdruck `empf == "<Name>"` (je Alias `or empf == "<Alias>"`).
  `em-im-konto` („Anzeigen im Konto …“): mit Buchungen auf genau einem
  Bestandskonto öffnet er `/konten/<konto-id>?empfaenger_id=<id>`; auf mehreren
  ein Untermenü mit `em-im-konto-<konto-id>` (Reihenfolge wie
  `GET /api/empfaenger/{id}/konten`); ohne Buchungen `aria-disabled="true"`.
- `empfaenger-suche` filtert die Liste über Name und Aliase,
  `empfaenger-treffer` nennt die Zahl (`data-anzahl`, Festlegung E-306).
- Je Zeile `empfaenger-menue-<id>` („⋯“) öffnet dasselbe Menü wie der
  Rechtsklick; `empfaenger-bestaetigen-<id>` bleibt.

### 41.3 Dubletten (D-222, D-236/11)

Jede Buchung eines Verdachts oder Vorschlags zeigt ihren Verwendungszweck und
je Bestandskonto `dublette-buchung-<id>-konto-<konto-id>`; er öffnet das
Kontoblatt des Kontos mit der Buchung markiert (Sprungziel `?buchung=<id>`,
26). Abweichende Angaben tragen `data-abweichung`. Knopftext „Diese behalten“
unverändert.

### 41.4 Bestätigen (D-223, ändert 37.10)

„Als <Person> bestätigen“ setzt das Tag „B-<Person>“ (z. B. „B-Torsten“);
`data-bestaetigt` und `data-person` nennen weiter den Namen der Person.

### 41.5 Kontoblatt: Spalten (D-224)

Kontextmenü der Kopfzeile: `km-spalten-wahl` mit je Spalte `km-spalte-<feld>`
(`aria-checked` = sichtbar, Festlegung E-306). Mindestens eine Spalte bleibt
sichtbar. Gemerkt im Browser je Listenart (Schlüssel `kontor.spalten.aus`);
die Zellen bleiben im Dokument, die Liste trägt `data-spalten-aus` mit den
ausgeblendeten Feldern (durch Leerzeichen oder Komma getrennt, E-306). Auf
dem Handy ohne Wirkung.

### 41.6 Kontoblatt: Summen der Auswahl, Bereichsauswahl (D-231, D-233, D-236/6)

- Sind Buchungen markiert, zeigt `auswahl-summen` `auswahl-ausgaben`,
  `auswahl-einnahmen` und `auswahl-summe`, je mit `data-betrag` (Cent, Sicht
  des Blatts, aus den geladenen Zeilen); ohne Markierung ist `auswahl-summen`
  verborgen. Einnahmen = Summe der positiven Beträge, Summe = Summe aller;
  Ausgaben = Summe der negativen Beträge (Vorzeichen frei, E-306). Handy: im
  Auswahlkopf `auswahl-kopf-summen`.
- Umschalt+Klick und Umschalt+Pfeil markieren in der **angezeigten**
  Reihenfolge (bei Gruppierung je Zeitraum); Buchungen zugeklappter Zeiträume
  gehören nicht zum Bereich.
- `gruppierung-zu`/`-auf` heißen sichtbar „Alle zu“/„Alle auf“; „Alles
  zusammenklappen“/„Alles aufklappen“ stehen als `aria-label`.

### 41.7 Tags (D-225, D-236/7–8)

Seite `/tags`: je Tag die Zahl der Buchungen, Anlegen, `tag-umbenennen-<id>`,
`tag-loeschen-<id>`. Ein Klick auf ein Tag schreibt `?tag=<id>` in die
Adresse und zeigt darunter seine Buchungen (höchstens 500, neueste zuerst)
mit Summe und „Im Konto zeigen“; es öffnet sich kein Kontoblatt. Die
Tag-Verwaltung der Einstellungen bleibt.

### 41.8 Änderungsprotokoll: Einzelheiten (D-237)

Je Zeile `aenderung-einzelheiten-<id>` öffnet `aenderung-dialog` mit
Zeitpunkt, Quelle, Aktion, Umfang, Stand und je Objekt einem Abschnitt
`ae-eintrag-<objekt>-<objekt_id>` (bei „geändert“ nur die abweichenden
Angaben mit Vorher und Nachher). Große Änderungen: zuerst 50 Abschnitte,
„Weitere anzeigen“ in Schritten von 50. Nur lesend, kein Rückgängig im Fenster.

### 41.9 Erfolgsmeldung mit „Rückgängig“ (D-234, ändert 4.3)

Die Erfolgsmeldung mit `meldung-rueckgaengig` nach eigenen Änderungen
erscheint nur, wenn unter Einstellungen → Allgemein
`einstellung-erfolgsmeldung` eingeschaltet ist (Schalter, gemerkt im Browser
unter `kontor.meldung.erfolg`). Vorgabe aus. Rückgängig über Kopfzeile,
Strg+Z und Palette bleibt; Fehlermeldungen, Hinweise und die Meldung nach
einem Rückgängig bleiben. Tests, die die Meldung erwarten, schalten sie vorher
über die Einstellung ein (Hilfe `m32.erfolgsmeldung_einschalten`, E-306).

### 41.10 Mail-Blatt und Mail-Ansicht (D-226 bis D-229, D-236/1, 5, 9)

- `mail-suche` (Adresse `suche=<text>`, Festlegung E-306) filtert über
  `GET /api/mail/nachrichten?suche=`.
- `mail-zuordnen` („Buchung zuordnen…“) öffnet den Auswahldialog;
  das Zuordnen ruft `POST /api/mail/nachrichten/{id}/buchung`.
- Das Mail-Blatt fordert immer gruppiert an; Zeilen einer Gruppe tragen
  `data-gruppe` (ID der ersten Mail) und `data-gruppe-rolle` ∈ {`kopf`,
  `folge`, `ende`}.
- Handy: keine Mail vorgewählt, die Liste steht zuerst; Antippen öffnet den
  Lesebereich, `mail-lesen-schliessen` schließt ihn. Desktop: erste Mail
  vorgewählt (37).
- Mail-Ansicht: bei Bildern fremder Server `mail-bilder-leiste` mit
  `mail-bilder-laden` und `mail-bilder-immer` (gemerkt unter
  `kontor.mail.bilder`); ohne solche Bilder keine Leiste. Leere Teile zeigen
  nie „null“.

### 41.11 Handy-Kontoblatt (D-236/4, ändert 36 und 39.2 am Handy)

Am Handy sind Filterfeld (`filter-ausdruck`), Zeitraum-Knöpfe
(`filter-schnell-<wert>`) und Gruppierung (`gruppierung-*`) eingeklappt;
`ansicht-umschalten` („Filter und Gruppierung“, `aria-expanded`) klappt sie
auf. Der Baukasten-Umschalter (`filter-baukasten-umschalten`) bleibt
sichtbar. Am Desktop ändert sich nichts. Tests am Handy klappen über
`m8.ansicht_aufklappen` auf (E-307).

### 41.12 Tabs (D-236/14)

Ab sechs offenen Tabs steht am Ende der Tab-Leiste `tab-andere-schliessen`
(„Andere schließen“): schließt alle außer dem aktiven. Bei weniger Tabs fehlt
er (oder ist verborgen).

### 41.13 Konfiguration (D-235)

Seite `/konfiguration` (`seite-konfiguration`), nur lesend, aus
`GET /api/konfiguration`; Werte mit `verborgen` erscheinen nie im Dokument.

### 41.14 Übrige Punkte des UX-Durchgangs

D-236/2, 3, 12, 13 (klebende Betragsspalte, Gruppenbalken, rote Frist,
Kachel) sind Darstellung und werden nicht geprüft.
