# Testinstanz starten

Die Testinstanz ist eine zweite, getrennte Kontor-Instanz auf demselben Server
(D-205). Sie zeigt einen Entwicklungsbranch mit einer Kopie der Daten auf
Port 8081. Die Hauptinstanz wird dabei nur gelesen; Änderungen in der
Testinstanz kommen nie dorthin zurück.

Für die wiederkehrenden Schritte gibt es das Bedienskript `kontor-test`
(D-213). Es ruft `python -m kontor.testinstanz` auf, merkt sich den zuletzt
benutzten Branch und zeigt Zustand, Protokoll und Adresse an.

## Voraussetzungen

- Root-Zugang im Container der Hauptinstanz.
- `git` sowie Netzzugang zu GitHub und PyPI auf dem Server.
- Der Branch ist gepusht.

## Einmalig: Skript einrichten

Das Skript wird mit Kontor ausgeliefert (Paket `kontor.betrieb`). Nach dem
Update der Hauptinstanz auf eine Version, die es enthält:

```bash
B=$(/opt/kontor/venv/bin/python -c 'import importlib.resources as r; print(r.files("kontor.betrieb"))')
install -m 0755 "$B/kontor-test.sh" /usr/local/bin/kontor-test
```

Nach späteren Updates genügt derselbe `install`-Aufruf, falls sich das Skript
geändert hat.

## Starten

1. Als root auf dem Server anmelden.
2. Branch einrichten und starten: `kontor-test start monatsbericht`
3. Warten, bis das Skript die Adresse ausgibt, z. B. `http://10.0.0.12:8081` –
   oder, wenn Kontor auf HTTPS umgestellt ist, `https://kontor.<tailnet>.ts.net:8443`
   (siehe „Mit HTTPS“ unten).
   Das erste Einrichten legt eine eigene virtuelle Umgebung an und dauert länger.
4. Adresse im Browser öffnen und mit dem Haushaltspasswort anmelden.

Beim Branch reicht der Kurzname; daraus wird `feature/monatsbericht`. Ein
vollständiger Name (mit `/`) oder `main` geht ebenfalls.

Der Befehl erledigt in einem Zug:

- Branch holen und in eine eigene Umgebung unter `/opt/kontor-test` installieren
- Datenbank per Online-Sicherung aus der laufenden Hauptinstanz nach
  `/var/lib/kontor-test` kopieren
- Geheimnisse, offene TAN-Anforderungen und den gespeicherten Bankzugang aus
  der Kopie entfernen
- Unit `kontor-test.service` und, falls noch nicht vorhanden, die
  Umgebungsdatei `/etc/kontor/kontor-test.env` ablegen (Mock-Modus, Port 8081,
  kein zeitgesteuerter Abruf, kein Mail-Abruf, keine Update-Suche)
- Dienst starten und prüfen, ob der Port antwortet

## Wiederkehrende Aufgaben

| Aufgabe | Befehl |
| --- | --- |
| Neuen Stand des Branches holen und Daten frisch kopieren | `kontor-test neu` |
| Anderen Branch testen | `kontor-test start <branch>` |
| Zustand, Branch und Adresse anzeigen | `kontor-test status` |
| Protokoll mitlesen | `kontor-test log` |
| Anhalten, Datenkopie behalten | `kontor-test stop` |
| Anhalten und Datenkopie löschen | `kontor-test loeschen` |

`kontor-test neu` verwendet den Branch vom letzten `start`; das Skript merkt
ihn sich in `/root/.kontor-test-branch`.

## Mit HTTPS

Ist Kontor mit `kontor-https einrichten` auf HTTPS umgestellt
([HTTPS.md](HTTPS.md), D-239), bleibt die Bedienung gleich:

- `kontor-test start <branch>` und `kontor-test neu` geben die Testinstanz
  zusätzlich über Tailscale frei (eigener HTTPS-Port, Vorgabe 8443) und nennen
  die https-Adresse.
- `kontor-test stop` und `kontor-test loeschen` nehmen die Freigabe zurück.
- `kontor-test status` zeigt die https-Adresse.

Das Skript erkennt HTTPS an einer `https://`-Adresse unter
`KONTOR_OEFFENTLICHE_URL` in `/etc/kontor/kontor-test.env`; `kontor-https`
trägt sie dort ein. Nach einem Kontor-Update, das dieses Skript ändert, den
`install`-Aufruf von oben wiederholen.

## Gut zu wissen

- **Jedes Einrichten ersetzt alles.** Branch und Datenkopie werden neu
  aufgebaut; was in der Testinstanz geändert wurde, ist danach weg.
- **Kein Autostart.** Nach einem Neustart des Servers bleibt die Testinstanz
  aus, bis sie wieder gestartet wird.
- **Mock-Modus.** Ein Branch, der am echten Bankabruf arbeitet, lässt sich
  hier nicht gegen die Bank prüfen.
- **Gemeinsames Sitzungs-Cookie.** Wer in der einen Instanz angemeldet ist, ist
  es auch in der anderen; eine neue Anmeldung in der einen meldet in diesem
  Browser die andere ab. Der Hinweisbalken „Mock-Modus“ und der Branchname
  unten in der Navigation zeigen, wo man ist.
- **Port ändern.** `KONTOR_PORT` in `/etc/kontor/kontor-test.env`; die Datei
  bleibt bei erneutem Einrichten erhalten, das Skript liest den Port von dort.
- **Fehlgeschlagenes Holen ist harmlos.** Ist der Branch unbekannt oder das
  Netz weg, bleibt eine laufende Testinstanz unberührt.

## Wenn etwas nicht klappt

| Anzeichen | Was tun |
| --- | --- |
| `/opt/kontor/venv/bin/python nicht gefunden` | Nicht im Container der Hauptinstanz, oder Kontor liegt woanders (dann `KONTOR_PYTHON=<pfad>` voranstellen). |
| `No module named kontor.testinstanz` | Hauptinstanz ist älter als 0.22; zuerst aktualisieren. |
| Klonen scheitert | Branchnamen prüfen; ist er gepusht, erreicht der Server GitHub? |
| Port antwortet nicht | Das Skript zeigt die letzten Protokollzeilen; mehr mit `kontor-test log`. |
| „Die HTTPS-Freigabe ist fehlgeschlagen“ | Die Testinstanz läuft, ist aber nur auf dem Server selbst erreichbar. `kontor-https status` ansehen, dann `kontor-test neu`; siehe [HTTPS.md](HTTPS.md). |
| Dienst startet nicht, Hinweise auf Rechte oder Pfade | Betrifft vermutlich die Härtung der Unit oder die Rechte des Benutzers `kontor`; Protokollauszug an den Implementierungs-Thread geben. |

## Ohne Skript

```bash
/opt/kontor/venv/bin/python -m kontor.testinstanz einrichten feature/<kurzname>
/opt/kontor/venv/bin/python -m kontor.testinstanz stoppen
/opt/kontor/venv/bin/python -m kontor.testinstanz stoppen --loeschen
journalctl -u kontor-test -f
```
