# Versionsnummer, Release und About-Fenster – Meilenstein 13

Freigegebene Meilenstein-Definition des Auftraggebers vom 2026-11-10 (E-176
bis E-180). Die Oberfläche (Abschnitt 4 der Definition) steht in
`oberflaeche.md` 24. Abkürzungen: K = `konzept.md`, T = `testkonzept.md`,
E = `entscheidungen.md`.

Rückwärtskompatibel (E-029): Ein neuer Endpunkt `GET /api/version`, ein
neuer Knopf in der Navigation und ein Dialog. Datenmodell, Protokoll und
Sicherung bleiben unverändert; `GET /api/gesundheit` bleibt in Form und
Feldern unverändert und öffentlich (5).

## 1. Versionsnummer

1.1 **Schema `MAJOR.MINOR`:** `MAJOR` ist eine nicht negative ganze Zahl ohne
führende Null (`0`, `1`, `12`), `MINOR` besteht aus mindestens zwei Ziffern
und wird zweistellig mit führender Null geschrieben (`00` … `99`). Nach `99`
zählt Minor ohne Grenze weiter (`0.99` → `0.100`). Beispiele: `0.01`,
`0.07`, `1.00`, `2.13`.

Als regulärer Ausdruck (E-177; ab Minor 100 ohne führende Null):

```text
^(0|[1-9][0-9]*)\.([0-9]{2}|[1-9][0-9]{2,})$
```

Gültig: `0.00`, `0.01`, `0.07`, `0.99`, `0.100`, `1.00`, `2.13`, `12.05`.
Ungültig: `0.1`, `0.7`, `1.0`, `01.00`, `0.012`, `0.01.1`, `v0.01`,
`0.01.dev0`, ` 0.01`, `0.01 `, ``.

1.2 **Hochzählen:** Bei jedem Release steigt Minor um 1 (`0.07` → `0.08`).
Major steigt nur auf ausdrückliche Anweisung und setzt Minor auf `00`
(`0.08` → `1.00`). Major steigt nie von selbst, auch nicht nach `0.99`.

1.3 **Startwert:** Vor dem ersten Release lautet die Version `0.00`; das erste
Release ist `0.01`.

1.4 **Eine Quelle, überall gleich:** `kontor.__version__`, `GET /api/status`
→ `version`, `GET /api/gesundheit` → `version`, `GET /api/version` →
`version`, die Versionsanzeige der Oberfläche (`oberflaeche.md` 24.1, auch in
der ausgelieferten Hülle) und `app_version` im Manifest einer Sicherung
(`sicherung.md` 3.2) nennen dieselbe Zeichenkette im Schema 1.1.

1.5 **PEP 440:** Die Zeichenkette ist PEP-440-gültig (`python-api.md` 1).
Paketwerkzeuge dürfen sie normalisieren (`0.07` → `0.7` im Namen von Wheel
und Quellpaket); Anzeige, Tag und alle REST-Antworten verwenden immer die
Schreibweise nach 1.1.

## 2. Release (Repository kontor-app, GitHub)

2.1 **Auslöser:** Jeder Push auf `main` (also jeder Merge eines
Feature-Branches) ist ein Release mit Minor + 1. Ein Release mit Major + 1
wird von Hand gestartet (Workflow „Release“, Option „major“). Ein von Hand
gestarteter Lauf ohne „major“ ist ein gewöhnliches Minor-Release.

2.2 **Ablauf eines Releases:** eigene Tests von kontor-app ausführen (Abbruch
bei Fehlschlag, dann keine neue Version); neue Version bestimmen; Version als
eigenen Commit auf `main` festhalten; Tag `v<Version>` (z. B. `v0.01`)
setzen; Wheel und Quellpaket bauen; Paket installieren und prüfen, dass es
die neue Version und Build-Angaben meldet; Commit und Tag gemeinsam pushen;
GitHub-Release „Kontor <Version>“ mit automatisch erzeugten Notizen sowie
Wheel und Quellpaket als Anhängen anlegen.

2.3 **Fehlerfälle:** Gibt es den Tag schon, bricht das Release ohne Änderung
ab. Schlägt ein Schritt vor dem Pushen fehl, entsteht weder Commit noch Tag
noch Release auf GitHub. Schlägt nur das Anlegen des GitHub-Releases fehl,
bleiben Commit und Tag bestehen; das Release wird für diesen Tag nachgeholt,
die Version steigt dabei nicht erneut. Der Versions-Commit des Releases löst
kein weiteres Release aus. Releases laufen nie parallel.

2.4 Seit dem Testumbau (D-253) laufen vor jedem Release die Gesamttests (eigene Tests und `gesamt-tests/`);
das Release folgt nur bei Grün. 2.1–2.3 selbst werden nicht durch Tests geprüft (E-176). Auch 1.2 und 1.3 sind über die Schnittstellen der App nicht
beobachtbar (eine laufende App kennt nur ihre eigene Version) und werden
nicht getestet; geprüft wird das Schema 1.1 und die Gleichheit 1.4.

## 3. REST: `GET /api/version`

3.1 **Schutz und Methoden:** Geschützt wie alle Endpunkte außer
`sicherheit.md` 3.1 (ohne Anmeldung bei aktiver Anmeldung `401`
`nicht_angemeldet`, auch für andere Methoden). Nur `GET`; andere Methoden
`405` `methode_nicht_erlaubt` (wie bei den übrigen Lese-Endpunkten).
Query-Parameter haben keine Wirkung (auch unbekannte führen nicht zu `422`,
E-178).

3.2 **Antwort `200`** (Schema `Versionsangaben`), JSON-Objekt mit genau diesen
Feldern:

| Feld | Typ | Inhalt |
| --- | --- | --- |
| `name` | str | immer `"Kontor"` |
| `version` | str | Versionsnummer nach 1.1 |
| `commit` | str oder null | gekürzter Commit-Hash des Builds (Hexadezimal in Kleinbuchstaben, 7–40 Zeichen, E-178); null ohne Release-Build |
| `build_datum` | str oder null | Zeitpunkt des Builds in UTC (ISO 8601, `JJJJ-MM-TTTHH:MM:SS[.f]Z`); null ohne Release-Build |
| `entwicklungsstand` | bool | true, wenn die App nicht aus einem Release-Build stammt (dann `commit` und `build_datum` null); false genau dann, wenn `commit` und `build_datum` beide gesetzt sind |
| `python` | str | Python-Version der laufenden App (`platform.python_version()`, z. B. `"3.12.4"`) |
| `repository` | str | `https://`-Adresse des Quellcode-Repositorys (mit Host, ohne Benutzer- oder Passwortteil) |
| `modus` | str | `"mock"` oder `"echt"` wie `GET /api/status` |
| `datenbank` | str | absoluter Pfad der aktiven Datenbankdatei (`KontorConfig.aktive_datenbank`, im Mock-Modus die Mock-Datenbank); gleich nach `Path.resolve()` |
| `datenbank_schema` | int ≥ 1 | Schemaversion der App-Datenbank |
| `sicherung_schema` | int ≥ 1 | Schemaversion, mit der neue Sicherungen erzeugt werden (wie `schemaversion` im Manifest einer frisch erzeugten Sicherung, `sicherung.md` 3.2) |

`datenbank_schema` und `sicherung_schema` sind voneinander unabhängig; sie
dürfen gleich sein, müssen es aber nicht (E-178).

3.3 **Kein fachlicher Zustand:** Der Aufruf ändert nichts, erzeugt keinen
Protokolleintrag und nichts in der Sicherung (Manifest `anzahl` und
`inhalt_sha256` bleiben gleich). Die Antwort enthält keine Geheimnisse (kein
Passwort, kein Sitzungs- oder CSRF-Token, keine PIN, keine Tokens).

## 4. Oberfläche

Siehe `oberflaeche.md` 24 (Versionsanzeige `version-knopf`, About-Fenster
`ueber-dialog`, Bedienung, Fehlerfall).

## 5. Abgrenzung

Keine Änderung an Datenmodell, Protokoll, Sicherung (außer dass `app_version`
dem Schema 1.1 folgt) oder an Tests früherer Meilensteine. `GET
/api/gesundheit` bleibt öffentlich und unverändert in Form und Feldern; ihr
Wert `version` folgt 1.1 (1.4). Die Schemas `Status`, `Gesundheit` und
`SicherungManifest` in `openapi.yaml` bleiben unverändert (nur Beschreibung);
das Muster 1.1 prüfen das neue Schema `Versionsangaben` und die Tests von
M13 (E-177).

## 6. Meilenstein 31: Branch statt Version außerhalb von main (Definition 3, D-178; E-285)

- Die Anwendung liest den Branch aus dem Git-Verzeichnis ihres Quellbaums
  (ohne Git aufzurufen; Worktrees mit `.git`-Datei). Für Releases, losgelösten
  HEAD und Namen außerhalb von `[A-Za-z0-9._/-]` gibt es keinen Branch.
- Ist der Branch nicht `main`, enthält die ausgelieferte Hülle statt „Version
  x.yy“ im Fuß der Navigation den Link `zweig-link` (`<a>`, `href` =
  `<repository>/tree/<Branch>`, `target="_blank"`), und `version-knopf`
  trägt den Text „Über“ und öffnet weiter das About-Fenster; dort steht
  zusätzlich `ueber-zweig` mit dem Branch.
- Auf `main` und in Releases bleibt alles wie in 1–5 und `oberflaeche.md`
  24 (kein `zweig-link`, kein `ueber-zweig`). `GET /api/version` bleibt
  unverändert.
