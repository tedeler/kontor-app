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

## Vorführen mit Demodaten

Für eine Vorführung ohne die eigenen Bankbewegungen füllt `kontor-test demo` die
Testinstanz mit einem erfundenen Haushalt (D-285). Die Datenbank der
Hauptinstanz wird dabei nicht gelesen.

1. Als root auf dem Server: `kontor-test demo` (zeigt `main`) oder
   `kontor-test demo <branch>`.
2. Adresse im Browser öffnen. **Es gibt keine Anmeldung**: Die Daten sind
   erfunden, jeder im erlaubten Netz darf sie sehen und ändern.
3. Nach der Vorführung: `kontor-test neu` baut dieselbe Demo frisch auf,
   `kontor-test start <branch>` kehrt zur Datenkopie mit Anmeldung zurück,
   `kontor-test loeschen` räumt alles weg.

Der Aufbau dauert auf dem Entwicklungsrechner rund 15 Sekunden. Enthalten sind:

- Girokonto und Sparbuch der „Musterbank“ über gut drei Jahre bis drei Tage vor
  dem Tag des Aufbaus: über 2000 Buchungen, die Kontostände stimmen mit der
  Mock-Bank überein.
- 14 Kategorien, sechs davon Unterkategorien (Wohnen › Nebenkosten, Energie;
  Mobilität › Tanken, Bahn & ÖPNV; Freizeit › Restaurant; Einkommen › Gehalt).
- Zwei Kredite: Wohnungsdarlehen (mit Sondertilgung und Jahresabgleichen samt
  Korrekturbuchung) und Autokredit; die Raten sind in Zins und Tilgung geteilt.
- Zwei Postfächer mit rund 250 Mails (Bestellungen, Erstattungen, Zahlungen,
  Abschlagsmitteilungen); etwa zwei Drittel hängen als Dokument an Buchungen,
  dazu rund 20 Belege als PDF.
- Acht Regeln von Hand (eine vergibt nur ein Tag) und die automatisch gelernten,
  eine Split-Vorlage, Tags, wiederkehrende Zahlungen, geplante Zahlungen,
  Abstimmungen zum Jahresende, Änderungsprotokoll und Abrufe mit glaubwürdigen
  Zeiten.

Zum Zeigen liegt bereit:

| Was | Wo |
| --- | --- |
| Neue Umsätze und Mails holen | „Synchronisation“ und „Mails abrufen“ bringen beim ersten Mal sicher Neues (eine Bestellung samt Mail, die sich an die Buchung hängt); für die folgenden 60 Tage kommt laufend etwas nach |
| Vorschläge prüfen und bestätigen | Girokonto: die letzten drei Wochen sind vorläufig (Regel oder Lernmodell) |
| Unkategorisiertes zuordnen | neue Empfänger ohne Vorgeschichte (Gartencenter, Schuhhaus, Tierarzt) |
| Split-Vorlage anpassen | Die Stadtwerke haben den Abschlag erhöht; die Vorlage passt nicht mehr (Benachrichtigung) |
| Dublette auflösen | Ein von Hand notiertes Abendessen kam noch einmal von der Bank. Der Abruf hat den Kontostand deshalb ausgeglichen; nach dem Zusammenführen nimmt der nächste Abruf den Ausgleich zurück |
| Wiederkehrendes | „Was kommt noch?“: Verträge, ein gekündigtes Fitnessstudio, eine Preiserhöhung beim Streaming, eine überfällige Erstattung |
| Mails von Hand zuordnen | Mail-Blatt, „Nicht erkannt“: Zahlungsmails von PayPal ohne Buchung |
| Berichte | alle Berichte haben drei Jahre Stoff; Tags „Urlaub 2024“ bis „Urlaub 2026“, „Auto“ |

Gut zu wissen:

- Die Demo ist auf den Tag des Aufbaus bezogen. Liegt er länger zurück, vorher
  `kontor-test neu`.
- Bestätigungen tragen die Tags der beiden Personen, die die Anwendung kennt.
- Alles ist erfunden: Namen, Beträge, Bestellnummern; die IBANs sind Test-IBANs
  mit Bankleitzahl 00000000, Mailadressen liegen unter `example.invalid`.
- Die Demo-Einstellungen stehen in `/etc/kontor/kontor-test-demo.env` und einem
  Drop-in der Unit; `kontor-test start` und `kontor-test loeschen` entfernen
  beides wieder.

## Wiederkehrende Aufgaben

| Aufgabe | Befehl |
| --- | --- |
| Neuen Stand des Branches holen und Daten frisch kopieren (nach `demo`: Demodaten neu aufbauen) | `kontor-test neu` |
| Anderen Branch testen | `kontor-test start <branch>` |
| Mit Demodaten vorführen (ohne Anmeldung) | `kontor-test demo [branch]` |
| Zustand, Branch und Adresse anzeigen | `kontor-test status` |
| Protokoll mitlesen | `kontor-test log` |
| Anhalten, Datenkopie behalten | `kontor-test stop` |
| Anhalten und Daten (Kopie oder Demodaten) löschen | `kontor-test loeschen` |

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
/opt/kontor/venv/bin/python -m kontor.testinstanz demo [<branch>]
/opt/kontor/venv/bin/python -m kontor.testinstanz stoppen
/opt/kontor/venv/bin/python -m kontor.testinstanz stoppen --loeschen
journalctl -u kontor-test -f
```
