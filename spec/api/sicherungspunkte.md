# Sicherungspunkte – stündliche inkrementelle Sicherung, Zurück und Vorwärts, kurzes Änderungsprotokoll

Verbindlich für Implementierung und Tests (Feature `sicherung-stuendlich`, D-302). Ergänzt `sicherung.md`
(Abschnitt 15), `protokoll.md` (Abschnitt 26), `betrieb.md` (Abschnitt 8) und `oberflaeche.md` (Abschnitt 49).
Konzept und Abstimmung mit dem Auftraggeber: Projektdokument `feature-sicherung-stuendlich.md` (2026-11-26).

## 1. Begriffe

- **Gesicherter Zustand:** alles, was eine Sicherungsdatei nach `sicherung.md` enthält (Tabellen der
  Sicherungsdatei), ab Schemaversion 11 zusätzlich die Einstellungen der Instanz (`einstellung`, 2.2).
- **Sicherungspunkt (Punkt):** ein unveränderlicher, gespeicherter gesicherter Zustand mit Kennung, Zeitpunkt,
  Marken, Prüfwert und Chronik.
- **Prüfwert:** SHA-256 über den gesicherten Zustand **ohne Begleitzustand** (2.3). Zwei Stände mit gleichem
  Prüfwert gelten als gleich.
- **Bezugspunkt:** der Punkt, dem der aktuelle Stand zuletzt entsprach (nach einem neuen Punkt dieser, nach einem
  Wechsel der Zielpunkt).
- **Anker:** ein Punkt, der den ganzen Zustand enthält. Alle anderen Punkte enthalten die Zeilendifferenz zu einem
  älteren Punkt (ihrer **Basis**).

## 2. Umfang

### 2.1 Inhalt

Genau die Tabellen der Sicherungsdatei (`sicherung.md` 2, Schemaversion 11). Nicht enthalten: Änderungsprotokoll,
Geheimnisse, Anmeldung und Sitzungen, Bankzugang, Mail-Spiegel, Postfachzustand, Benachrichtigungen,
Synchronisationsläufe, Importvorgänge.

### 2.2 Einstellungen (Schemaversion 11 der Sicherungsdatei)

Neue Tabelle `einstellung (schluessel TEXT PRIMARY KEY, wert TEXT)` mit den in der Instanz gesetzten Werten von
`lern_regeln_automatisch`, `lern_schwelle_promille`, `wk_filter_modus` und `wk_filter_toleranz`. Beim Einspielen
einer Sicherung ab Version 11 werden diese vier Einstellungen ersetzt (fehlende entfernt); bei älteren Sicherungen
bleiben die aktuellen Werte. Sicherungen der Versionen 1 bis 10 lassen sich weiter einspielen.

### 2.3 Begleitzustand

`id_zaehler` und `sync_konto_zustand` ändern sich auch ohne fachliche Änderung (Abruf ohne neue Umsätze, angelegt
und wieder gelöscht). Sie zählen nicht zum Prüfwert, stehen aber vollständig in jedem Punkt und werden mit ihm
hergestellt.

## 3. Entstehen von Punkten

### 3.1 Regel „keine leeren Punkte“

Ein neuer Punkt entsteht nur, wenn der Prüfwert des aktuellen Stands vom Prüfwert des Bezugspunkts abweicht.
Sonst wird nur die Prüfung vermerkt (`zuletzt_geprueft`). Gilt für jede Art.

### 3.2 Arten und Marken

| Marke | Anlass |
| --- | --- |
| `stuendlich` | stündlicher Lauf (`python -m kontor.sicherung stunde`) |
| `von_hand` | `POST /api/sicherung/punkte` |
| `vor_wiederherstellung` | Schritt 1 jedes Einspielens (5.1) |
| `aus_datei` | Stand nach dem Einspielen einer hochgeladenen Datei |
| `vor_update` | Lauf mit `--marke vor_update` (Update-Dienst) |

Entspricht der Stand bei einem Anlass schon einem Punkt, bekommt dieser Punkt die Marke dazu; ein Punkt kann
mehrere Marken tragen. Ein Name (`name`, 1–100 Zeichen) ist optional.

### 3.3 Anker

Ein Punkt wird als Anker gespeichert, wenn es noch keinen Punkt gibt, wenn er der erste Punkt eines
Kalendermonats (UTC) ist, wenn sich die Schemaversion der Datenbank seit der Basis geändert hat oder wenn die
Basis nicht herstellbar ist.

### 3.4 Basis

Ein neuer Punkt bezieht sich auf den Bezugspunkt. Beim Ausdünnen (4) wird die Basis eines behaltenen Punkts, der
älter als die Stundenstufe ist, auf den Anker seiner Kette umgestellt; die Kette ist dadurch höchstens
Anker → Tages-/Wochen-/Monatspunkt → Stundenpunkte lang.

### 3.5 Prüfung

Nach dem Schreiben wird die Datei wieder gelesen, auf die Zeilen-Hashes der Basis angewendet und der Prüfwert
verglichen (Sofortprüfung); misslingt das bei einer Differenz, wird der Punkt als Anker geschrieben. Herstellen und
Herunterladen prüfen die Prüfsumme jeder Datei der Kette und den Prüfwert jedes Glieds.

Einmal am Tag (erster stündlicher Lauf eines Kalendertags) prüft ein **Prüflauf** jeden Punkt durch Herstellen;
das Ergebnis steht in `GET /api/sicherung/punkte` unter `prueflauf` (`{tag, zeitpunkt, fehler}`).

## 4. Ausdünnen

Läuft nach jedem stündlichen Lauf. Bezug ist der Zeitpunkt des Laufs.

| Stufe | Alter | behalten |
| --- | --- | --- |
| Stunden | bis `stunden` (48) Stunden | jeder Punkt |
| Tage | bis `tage` (30) Tage | der jüngste Punkt jedes Kalendertags |
| Wochen | bis `wochen` (26) Wochen | der jüngste Punkt jeder ISO-Woche |
| Monate | bis `monate` (24) Monate | der jüngste Punkt jedes Kalendermonats |

Zusätzlich bleiben: angeheftete Punkte, Punkte mit Marke `von_hand`, `vor_wiederherstellung`, `aus_datei` oder
`vor_update` bis 30 Tage und der Bezugspunkt. Wird der Anker einer Kette nicht behalten, wird der älteste behaltene
Punkt dieser Kette zum neuen Anker. Behaltene Punkte außerhalb der Stundenstufe und Punkte, deren Basis entfällt,
bekommen den Anker ihrer Kette als Basis. Ihr Zustand bleibt dabei gleich.

Ausdünnen schreibt neue Dateien zuerst, prüft sie durch Herstellen gegen den Prüfwert und entfernt erst dann alte.

## 5. Einspielen und Wechsel

### 5.1 Ablauf

Gilt für `POST /api/sicherung/punkte/{kennung}/wechseln` und `POST /api/sicherung/einspielen`.

0. Prüfungen wie `sicherung.md` 5.1 (bei einem Punkt: Herstellen und Prüfwert). Keine Synchronisation
   (409 `sync_laeuft`, `tan_ausstehend`), kein Mail-Abruf (409 `mail_abruf_laeuft`).
1. In einer Schreibtransaktion (andere Schreibzugriffe warten): aktuellen Stand als Punkt sichern
   (Marke `vor_wiederherstellung`; bei gleichem Stand Marke am bestehenden Punkt). Scheitert das:
   409 `sicherung_vorher_fehlgeschlagen`, nichts geändert.
2. In derselben Transaktion: alle Tabellen des gesicherten Zustands leeren, Ziel einfügen, Nacharbeiten wie
   `sicherung.md` 5.3, Prüfwert gegen den Sollwert prüfen (Abweichung: 500 `intern`, Rückabwicklung),
   Änderung `sicherung_einspielen` ins Protokoll.
3. Bezugspunkt setzen: der Zielpunkt bzw. bei einer Datei der neue Punkt mit Marke `aus_datei`.

Unverändert bleiben Geheimnisse, Anmeldung, Sitzungen, Bankzugang, Mail-Spiegel (solange das Postfach bleibt),
das Änderungsprotokoll und die Sicherungspunkte.

### 5.2 Fehler beim Wechsel

- 404 `nicht_gefunden`: unbekannte Kennung.
- 409 `punkt_nicht_herstellbar`: Datei fehlt, Prüfsumme oder Prüfwert stimmen nicht.
- 409 `stand_unveraendert`: Der aktuelle Stand entspricht dem Punkt.
- 409 `bestaetigung_erforderlich` ohne `bestaetigt=true`.

## 6. Kurzes Änderungsprotokoll

Nach jedem stündlichen Lauf werden Änderungen entfernt, die älter als `protokoll_stunden` (1) Stunden sind, wenn
der Stand bei diesem Lauf durch einen geprüften Punkt gesichert ist. Mit ihnen entfallen ihre Einträge, die
Vermerke in `sicherung_zustand` und `sync_wiederherstellung` sowie Beleginhalte, die weder ein Dokument noch ein
verbliebener Protokolleintrag braucht. Rückgängig-Paare werden nur zusammen entfernt. Vorher wird die Herkunft
angelegter Buchungen (Gruppe `import:<id>`, `sync:<id>`) dauerhaft vermerkt, sodass `GET /api/konten/{id}/herkunft`
und das Verschieben nach Gruppe weiter wirken. `GET /api/aenderungen` liefert zusätzlich `gekuerzt_bis`
(Zeitpunkt der jüngsten entfernten Änderung oder `null`).

## 7. Schnittstelle

### 7.1 `GET /api/sicherung/punkte`

Antwort 200:

- `punkte`: neueste zuerst; je Punkt `kennung`, `zeitpunkt`, `marken`, `name`, `angeheftet`, `anker`, `basis`,
  `eltern`, `groesse` (Bytes der eigenen Datei), `groesse_herstellen` (Summe der Kette), `aenderungen`
  (`{tabelle: {neu, geaendert, geloescht}}` gegenüber dem Eltern-Punkt), `geprueft_am`, `chronik_anzahl`,
  `aktuell` (ist Bezugspunkt und Stand unverändert), `verlassen` (liegt nicht auf dem Weg zum Bezugspunkt und ist
  nicht jünger als dieser auf dessen Ast).
- `gesamt`: `groesse` (alle Dateien), `stufen` (`{stunden, tage, wochen, monate, angeheftet, basis}` → Bytes;
  `basis` = Punkte außerhalb aller Stufen, die nur noch als Grundlage dienen), `anzahl`.
- `bezugspunkt`, `unveraendert` (bool), `zuletzt_geprueft`, `naechster_lauf`, `jetzt` (Uhr des Servers), `frei`
  (Bytes auf dem Datenträger).

### 7.2 Weitere Endpunkte

- `POST /api/sicherung/punkte` mit `{name?}`: 201 neuer Punkt bzw. 200 bestehender Punkt mit `neu = false`.
- `PATCH /api/sicherung/punkte/{kennung}` mit `name` (string oder null) und/oder `angeheftet` (bool).
- `GET /api/sicherung/punkte/{kennung}/vergleich`: Unterschied zum aktuellen Stand wie `sicherung.md` 5.2.
- `GET /api/sicherung/punkte/{kennung}/chronik`: Liste `{zeitpunkt, quelle, aktion, beschreibung}`.
- `GET /api/sicherung/punkte/{kennung}/datei`: eigenständige Sicherungsdatei nach `sicherung.md` 3
  (`kontor-sicherung-<modus>-<zeit>.zip`, Zeit = Zeitpunkt des Punkts).
- `POST /api/sicherung/punkte/{kennung}/wechseln?bestaetigt=true`: 5.1; Antwort wie `SicherungErgebnis`
  ergänzt um `vorher` (Kennung des Punkts vor dem Wechsel) und `ziel`.

## 8. Betrieb

- **D-307: Der Dienst selbst** (`kontor.service`) prüft jede Minute, ob für die laufende Stunde schon eine Prüfung
  vorliegt, und führt sonst den stündlichen Lauf aus (nur mit `planer_starten`, abschaltbar mit
  `KONTOR_SICHERUNG_IM_DIENST=0`). Grund: Ein Update erneuert die installierten systemd-Units nicht; ein Server mit
  der Unit von vor D-302 ruft weiter täglich den alten Aufruf auf. Dieser alte Aufruf legt zusätzlich einen
  Sicherungspunkt an. Timer und Dienst schließen sich über die Dateisperre und Regel 3.1 aus.
- Jede Prüfung wird im Stand vermerkt (Stundenstufe, höchstens 400); `GET /api/sicherung/punkte` liefert die
  Prüfungen ohne neuen Punkt als `pruefungen` (`{zeitpunkt, kennung, neu, marke}`, neueste zuerst).

- Ablage `sicherung_verzeichnis` (`KONTOR_SICHERUNG_VERZEICHNIS`, Vorgabe `sicherungen` neben der Datenbank),
  darin `punkte-echt/` bzw. `punkte-mock/`; Verzeichnisse 0700, Dateien 0600. Nur auf dem Server.
- `python -m kontor.sicherung stunde [--verzeichnis <pfad>] [--marke vor_update]`: stündlicher Lauf (Punkt bei
  Änderung, Ausdünnen, Protokoll kürzen). `kontor-sicherung.timer` stündlich. Der bisherige Aufruf
  `--verzeichnis <pfad> [--behalten N]` schreibt weiter eine volle ZIP-Datei.
- Aufbewahrung: `KONTOR_SICHERUNG_STUNDEN` (48), `_TAGE` (30), `_WOCHEN` (26), `_MONATE` (24);
  `KONTOR_PROTOKOLL_STUNDEN` (1, 0 = nicht kürzen).
