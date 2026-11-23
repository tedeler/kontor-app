# Auftrag an den Test-Thread: kontor-tests auf den Stand von main bringen

Stand 2026-11-22. Auftraggeber: der Projektinhaber, übermittelt durch den Implementierungs-Thread des Sammelbranchs.

## Rolle und Grenzen (unbedingt einhalten)

- Du bist ein **Test-Thread** des Projekts Kontor. Du arbeitest **nur** im Klon
  `/home/claude/test-thread/kontor-tests` (Repository `tedeler/kontor-tests`, Branch `main`). Lies dort zuerst
  `CLAUDE.md` vollständig und halte dich daran (Spezifikation, Entscheidungen `E-xxx`, Marker, Selbstprüfung, Git).
- **Kein Anwendungscode.** Auf dieser Maschine liegt der Anwendungscode und ist als Python-Paket `kontor` installiert.
  Für dich gilt ohne Ausnahme:
  - die Verzeichnisse `/home/claude/kontor-app` und `/home/claude/kontor-tests` (der Lese-Klon des
    Implementierungs-Threads) **nicht öffnen, nicht auflisten, nicht durchsuchen**;
  - das Paket `kontor` nicht importieren, nicht inspizieren, seinen Ort nicht nachschlagen (`pip show`, `site-packages`,
    `python -c "import kontor"` und Ähnliches sind tabu);
  - **keine App-Tests gegen die installierte Anwendung laufen lassen.** Wo du Tests ausführst, dann nur
    `tests/generator`, `tests/spec`, die Selbstprüfung (`python -m tests._selbstpruefung`, läuft gegen die Referenz im
    Repository) und Sammelläufe (`--collect-only`); App-Tests höchstens mit `--ohne-app`.
  Erwartungswerte kommen aus der Definition, der Spezifikation, dem Generator oder eigener Rechnung – nie aus einer
  Ausgabe der Anwendung.
- Nur synthetische Daten (Test-IBANs mit BLZ 00000000, Adressen unter `example.invalid`), keine Secrets, keine
  Fremdsysteme (Bank, Mail, ntfy, Tailscale).
- Alles auf Deutsch. Git: `user.name` „Kontor Test-Thread“, direkt auf `main`, kleine Commits, vor jedem Push
  `git pull --rebase origin main`, kein Force-Push, keine Branches, keine Pull Requests. Push mit
  `git -c push.negotiate=true push origin main`. Nichts im Projektchat posten; dein Abschlussbericht geht als Antwort
  an den Auftraggeber dieses Auftrags.

## Lage

kontor-tests steht bei Meilenstein 28. Die Anwendung auf main (Version 0.37) enthält seither viele Features, die
kontor-tests noch nicht kennt. Deshalb sind dort zurzeit viele Abnahmetests rot (Liste: `abnahme-stand-main.txt` in
diesem Verzeichnis – nur Testnamen, als Hinweis, welche früheren Tests vom neuen Verhalten berührt sind).

Die Meilenstein-Definitionen liegen in `/home/claude/test-thread/definitionen/`:

| Paket | Datei | Inhalt |
| --- | --- | --- |
| 1 | `definition-1-fints-camt.md` | Bankabruf über FinTS/camt, Bankzugang in der Oberfläche (freigegeben 2026-11-19) |
| 2 | `definition-2-ausdruecke-regeln.md`, `definition-2-nachtrag.md` | Kontor-Ausdrücke, Filter im Kontoblatt, Regeleditor, Regel-Tags, Anwenden-Fenster, Tag-Dialog |
| 3 | `definition-3-uebrige-features-vor-sammel3.md` | Einzelheiten/Verwendungszweck, Branch-Anzeige, Lernmodell-Transparenz und automatische Regeln, Testinstanz, Monatsbericht, Einstellungen in Bereichen, Bestellnummer-Mails, Gruppierung im Kontoblatt, Berichte |
| 4 | `definition-4-sammelbranch-sammel3.md` (+ `anlagen/`) | Sammelbranch: Kontonamen, Empfänger, Tags-Seite, Mail-Blatt, Anbieter-Beschreibungen, PayPal, Konfiguration, UX-Durchgang, Änderungsprotokoll-Einzelheiten, geplante Zahlungen, HTTPS |

Die Pakete bauen aufeinander auf (Paket 4 ändert Teile von 2 und 3). Welches Paket **dein** Auftrag ist, steht in der
Nachricht, mit der du gestartet wurdest; die anderen Pakete bearbeiten andere Test-Threads vor oder nach dir. Sieh in
`spec/meilensteine.md`, `spec/api/entscheidungen.md` und `ERGEBNIS.md` nach, was schon übernommen ist, und setze dort
auf.

## Was zu tun ist (je Paket)

1. Die Definition(en) deines Pakets unverändert unter `spec/definitionen/` ablegen und committen (beim ersten Paket
   auch `AUFTRAG.md`), damit sie dauerhaft im Projekt-Repository stehen.
2. Die Definition in die Spezifikation übernehmen: betroffene Dateien unter `spec/api/` (auch `openapi.yaml`),
   `spec/meilensteine.md` (neue Meilensteine; die Nummern vergibst du, fortlaufend ab der nächsten freien),
   Entscheidungen `E-xxx` für jede Übernahme, jede Lücke und jede Änderung an Früherem. Danach
   `python -m pytest tests/spec`.
3. Abnahmetests schreiben: `tests/app/m<N>/` mit Marker `m<N>` (in `tests/conftest.py` und `pytest.ini` eintragen),
   Hilfen unter `tests/hilfen/`. REST über `tests/hilfen/api.py`, Browsertests wie in den bisherigen Meilensteinen.
   Schwerpunkt: Verhalten an REST und Konfiguration, Protokoll und Rückgängig, Sicherung (Rundreise), Fehlerfälle;
   Oberfläche über `data-testid` wie in der Definition genannt.
4. **Frühere Tests nachziehen**, die dem neuen Verhalten widersprechen: anpassen oder entfernen, jeweils mit
   Entscheidung (Beispiele: Meilenstein 10 entfällt; Einzelfelder der Filterleiste entfallen; Standardkategorie je
   Empfänger entfällt; statistische Analyse entfällt; Meldung mit „Rückgängig“ nur noch mit Einstellung;
   Kontonamen je Ebene eindeutig; Sicherungsdatei mit höherer Schemaversion). Die Liste `abnahme-stand-main.txt` hilft
   beim Finden; maßgeblich ist aber die Definition, nicht die Liste. Tests, die laut Liste rot sind, deren Erwartung
   nach der Definition aber weiter gilt, **nicht** ändern – das ist dann ein Fehler der Anwendung.
5. Selbstprüfung nach `CLAUDE.md`: Referenz grün, Mutanten rot. Wo neue Kern-Tests keine Referenz bekommen, wie bei
   M18–M24 und M27 verfahren (`OHNE_REFERENZ`) und das als Entscheidung festhalten. Die Referenz klein halten.
6. Abschluss nach `CLAUDE.md` („Vor dem Abschluss eines Auftrags“): `python -m pytest --voll tests/generator tests/spec`
   grün, `--voll --collect-only -q` ohne Sammelfehler, Selbstprüfung festgehalten, `ERGEBNIS.md` und `CLAUDE.md`
   (Meilensteinliste, Marker) aktualisiert, `git status` sauber, alles gepusht.

## Umfang mit Augenmaß

Das Paket ist groß. Gehe in dieser Reihenfolge vor und committe und pushe nach jedem Schritt, damit nichts verloren
geht: (a) Definition ablegen, (b) Spezifikation und Entscheidungen, (c) frühere Tests nachziehen, (d) neue Tests je
Abschnitt der Definition – zuerst REST/Konfiguration/Protokoll/Sicherung, dann Oberfläche, (e) Selbstprüfung und
Abschluss. Reicht deine Zeit nicht für alles, ist ein sauberer, gepushter Zwischenstand mit einer genauen Liste des
Offenen in `ERGEBNIS.md` besser als ein unvollständiger Arbeitsstand auf der Platte.

Wo die Definition eine Angabe offen lässt, entscheide selbst (Entscheidung `E-xxx`, knapp begründet) und schreibe
den Test danach. Rate keine Einzelheiten der Oberfläche, die die Definition nicht nennt (Texte, Farben, Anordnung);
prüfe dort nur, was genannt ist.

## Abschlussbericht (deine letzte Antwort)

Kurz und genau: übernommene Meilensteine mit Nummern, Zahl neuer und geänderter Tests, neue Entscheidungen
(`E-…` bis `E-…`), letzter Commit, Ergebnis von Spec-Tests, Sammellauf und Selbstprüfung, und eine Liste dessen, was
offen geblieben ist oder wo die Definition unklar war (als Text, damit der Implementierungs-Thread es klären kann).
