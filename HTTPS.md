# Kontor nur noch über HTTPS (Tailscale)

Diese Anleitung stellt eine laufende Kontor-Installation auf HTTPS um (D-239).
Danach ist Kontor ausschließlich unter einer `https://`-Adresse erreichbar, mit
einem gültigen Zertifikat und ohne Warnung im Browser – aber nur noch für
Geräte, die im eigenen Tailnet angemeldet sind.

Die Umstellung erledigt das Skript `kontor-https`. Es lässt sich beliebig oft
ausführen und mit einem Befehl vollständig zurücknehmen.

## So funktioniert es

```
Browser ──HTTPS──▶ Tailscale-Dienst auf dem Server ──http──▶ Kontor auf 127.0.0.1
                   (Zertifikat, Port 443)                    (Port 8000)
```

- Kontor spricht selbst kein TLS (`sicherheit.md` 12). Es lauscht nach der
  Umstellung nur noch auf `127.0.0.1` und ist von außen nicht mehr direkt
  erreichbar.
- Davor steht „Tailscale Serve“: Der Tailscale-Dienst auf dem Server nimmt
  HTTPS entgegen, besorgt und erneuert das Zertifikat selbst und reicht die
  Anfragen an Kontor weiter.
- Die Adresse ist der Tailscale-Name des Servers, z. B.
  `https://kontor.<tailnet>.ts.net`. Die Testinstanz bekommt denselben Namen
  mit eigenem Port: `https://kontor.<tailnet>.ts.net:8443`.

## Voraussetzungen

| Was | Wie prüfen |
| --- | --- |
| Kontor läuft als Dienst auf Debian (README, „Installation als systemd-Dienst“) | `systemctl is-active kontor` |
| Tailscale ist auf dem **Kontor-Server** installiert und angemeldet | `tailscale status` |
| MagicDNS ist für das Tailnet eingeschaltet | Tailscale-Admin-Konsole, Bereich „DNS“ |
| HTTPS-Zertifikate sind für das Tailnet eingeschaltet | ebenda, „HTTPS Certificates“ |
| Jedes Gerät, das Kontor nutzen soll, ist im Tailnet | Tailscale-App auf Rechner und Handy |

Hinweise:

- **Tailscale fehlt auf dem Server:** `kontor-https einrichten
  --tailscale-installieren` installiert es mit dem offiziellen
  Installationsskript von tailscale.com. Danach einmal `tailscale up`
  ausführen, dem angezeigten Link folgen und das Skript erneut starten.
- **Proxmox-LXC-Container:** Tailscale braucht im Container das Gerät
  `/dev/net/tun`. In einem unprivilegierten Container muss es der Host
  durchreichen (Tailscale-Dokumentation, Stichwort „LXC“); ohne das startet
  `tailscaled` nicht. Das ist eine Einstellung am Proxmox-Host, nicht in Kontor.
- **Der Name im Zertifikat ist öffentlich einsehbar.** Zertifikate werden in
  öffentlichen Protokollen verzeichnet; der Name des Servers und des Tailnets
  (`kontor.<tailnet>.ts.net`) ist damit bekannt, der Inhalt nicht.

## Einrichten

1. Als root auf dem Kontor-Server anmelden.
2. Skript ablegen (einmalig; nach einem Kontor-Update bei Bedarf wiederholen):

   ```bash
   B=$(/opt/kontor/venv/bin/python -c 'import importlib.resources as r; print(r.files("kontor.betrieb"))')
   install -m 0755 "$B/kontor-https.sh" /usr/local/bin/kontor-https
   install -m 0755 "$B/kontor-test.sh"  /usr/local/bin/kontor-test
   ```

3. Umstellen:

   ```bash
   kontor-https einrichten
   ```

4. Die ausgegebene Adresse im Browser öffnen und neu anmelden.
5. Lesezeichen ändern. Die auf dem Handy installierte App (PWA) entfernen und
   von der neuen Adresse aus neu „Zum Home-Bildschirm“ hinzufügen.

### Was das Skript tut

In dieser Reihenfolge; scheitert ein Schritt, bleibt alles davor Geänderte
benannt und rücknehmbar:

1. Prüft: root, Kontor vorhanden, Tailscale installiert und verbunden; liest
   den Tailscale-Namen des Servers.
2. Richtet die HTTPS-Freigabe ein (`tailscale serve --bg --https=443
   http://127.0.0.1:<Port>`). **Scheitert das, wird an Kontor nichts
   geändert** – meist fehlen MagicDNS oder die HTTPS-Zertifikate.
3. Sichert `/etc/kontor/kontor.env` einmalig als `kontor.env.vor-https` und
   setzt dort drei Werte (alles andere bleibt, auch Kommentare):

   | Variable | Wert | Wozu |
   | --- | --- | --- |
   | `KONTOR_HOST` | `127.0.0.1` | Kontor nur noch lokal erreichbar; kein Zugang mehr über http |
   | `KONTOR_SITZUNG_COOKIE_SECURE` | `1` | Das Sitzungs-Cookie wird nur über HTTPS gesendet |
   | `KONTOR_OEFFENTLICHE_URL` | `https://<name>` | Kontor kennt seine eigene Adresse: für die Herkunftsprüfung und für Links in Benachrichtigungen |

4. Startet Kontor neu und wartet, bis es antwortet.
5. Stellt die Testinstanz genauso um (`/etc/kontor/kontor-test.env`, Adresse
   mit Port 8443). Gibt es die Datei noch nicht, wird sie aus der
   ausgelieferten Vorlage angelegt. Läuft die Testinstanz gerade, wird sie neu
   gestartet und freigegeben.
6. Fragt Kontor über die neue Adresse ab und nennt beide Adressen.

Optionen:

| Option | Bedeutung |
| --- | --- |
| `--tailscale-installieren` | Tailscale einrichten, falls es fehlt |
| `--name <name>` | anderen DNS-Namen verwenden als den von Tailscale gemeldeten |
| `--test-port <port>` | HTTPS-Port der Testinstanz (Vorgabe 8443; nicht 443) |

## Testinstanz

An der Bedienung ändert sich nichts: `kontor-test start <branch>`, `neu`,
`stop`, `loeschen`, `status`, `log` wie in [TESTINSTANZ.md](TESTINSTANZ.md).

Nach der Umstellung gilt zusätzlich:

- `kontor-test start <branch>` und `kontor-test neu` schalten die
  HTTPS-Freigabe der Testinstanz ein und geben ihre Adresse aus, z. B.
  `https://kontor.<tailnet>.ts.net:8443`.
- `kontor-test stop` und `kontor-test loeschen` schalten die Freigabe wieder
  aus.
- Das Skript erkennt HTTPS daran, dass in `/etc/kontor/kontor-test.env` eine
  `https://`-Adresse unter `KONTOR_OEFFENTLICHE_URL` steht. Ohne diese Zeile
  verhält es sich wie bisher (http, Port 8081).
- Anderer HTTPS-Port: `kontor-https einrichten --test-port 9443`.
- Beide Instanzen teilen sich weiterhin das Sitzungs-Cookie (gleicher Name,
  anderer Port): Wer in der einen angemeldet ist, ist es auch in der anderen.

## Prüfen

```bash
kontor-https status
```

zeigt die gesetzten Werte beider Instanzen, ob Kontor über HTTPS antwortet,
und die Freigaben von Tailscale. Erwartet wird etwa:

```
Hauptinstanz (/etc/kontor/kontor.env)
  KONTOR_HOST=127.0.0.1
  KONTOR_SITZUNG_COOKIE_SECURE=1
  KONTOR_OEFFENTLICHE_URL=https://kontor.<tailnet>.ts.net
Testinstanz (/etc/kontor/kontor-test.env)
  KONTOR_OEFFENTLICHE_URL=https://kontor.<tailnet>.ts.net:8443
Erreichbarkeit: https://kontor.<tailnet>.ts.net antwortet.
Freigaben (tailscale serve status):
  https://kontor.<tailnet>.ts.net (tailnet only)
  |-- / proxy http://127.0.0.1:8000
```

Dieselben Werte zeigt in Kontor die Seite „Konfiguration“.

## Zurücknehmen

```bash
kontor-https zurueck
```

beendet beide Freigaben, stellt die drei Variablen in beiden Umgebungsdateien
auf den Stand von `*.vor-https` zurück (nicht gesetzte entfallen) und startet
die Dienste neu. Kontor ist danach wieder wie vorher über http erreichbar.
Andere Änderungen, die inzwischen an den Umgebungsdateien gemacht wurden,
bleiben erhalten.

## Was sich im Betrieb ändert

- **Zugriff nur über Tailscale.** Auch zu Hause im WLAN muss das Gerät im
  Tailnet sein. Dafür geht es von unterwegs genauso.
- **`KONTOR_ERLAUBTE_NETZE` schützt nicht mehr.** Alle Anfragen kommen jetzt
  von 127.0.0.1 (dem Tailscale-Dienst). Wer Kontor erreichen darf, regelt
  Tailscale: zunächst jedes Gerät des Tailnets, feiner über die
  Zugriffsregeln in der Admin-Konsole. Das Haushaltspasswort bleibt zusätzlich
  nötig.
- **Nie `tailscale funnel` verwenden.** Funnel würde Kontor ins öffentliche
  Internet stellen. Das Skript benutzt nur `tailscale serve`.
- **Neu anmelden.** Die Sitzung der alten http-Adresse gilt unter der neuen
  Adresse nicht.
- **Freigabe überlebt Neustarts.** `tailscale serve --bg` bleibt nach einem
  Neustart des Servers bestehen. Die Testinstanz startet weiterhin nicht von
  selbst.
- **Postfach über Google-OAuth:** `KONTOR_OAUTH_REDIRECT_URI` muss auf die neue
  Adresse zeigen (`https://<name>/oauth2/rueckruf`) und in der Google-Konsole
  eingetragen sein. Mit App-Passwort entfällt das.
- **Kontor-Update:** unverändert. Ein Update fasst die Umgebungsdateien nicht
  an; die Umstellung bleibt.

## Wenn etwas nicht klappt

| Anzeichen | Ursache und Abhilfe |
| --- | --- |
| „Tailscale ist nicht installiert“ | `kontor-https einrichten --tailscale-installieren`, dann `tailscale up`. |
| „Tailscale ist nicht verbunden“ | `tailscale up` ausführen und anmelden. Im LXC-Container: fehlt `/dev/net/tun`? (`journalctl -u tailscaled`) |
| „Tailscale konnte die Freigabe nicht einrichten“ | MagicDNS und HTTPS-Zertifikate in der Admin-Konsole einschalten, dann erneut. An Kontor wurde nichts geändert. |
| Browser: Seite lädt nicht | Ist das Gerät im Tailnet? `tailscale status` auf dem Gerät. |
| Erste Abfrage dauert lange oder scheitert | Das erste Zertifikat braucht bis zu einer Minute; danach `kontor-https status`. |
| Anmelden oder Speichern meldet „Die Anfrage kommt nicht von dieser Seite“ (403) | `KONTOR_OEFFENTLICHE_URL` fehlt oder nennt eine andere Adresse als die im Browser. `kontor-https einrichten` setzt sie; das Protokoll (`journalctl -u kontor`) warnt beim Start davor. |
| Anmeldung „vergisst“ sich sofort | Kontor wird noch über http aufgerufen, das Cookie aber nur über HTTPS gesendet: die https-Adresse benutzen. |
| Testinstanz: „Die HTTPS-Freigabe ist fehlgeschlagen“ | `kontor-https status` ansehen; ist der Port (8443) schon anders belegt, `kontor-https einrichten --test-port <port>`, dann `kontor-test neu`. |
| Kontor antwortet nach der Umstellung gar nicht | `journalctl -u kontor -n 30`; zurück mit `kontor-https zurueck`. |

## Ohne Skript

Dieselben Schritte von Hand (Hauptinstanz, Port 8000):

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000
# in /etc/kontor/kontor.env:
#   KONTOR_HOST=127.0.0.1
#   KONTOR_SITZUNG_COOKIE_SECURE=1
#   KONTOR_OEFFENTLICHE_URL=https://<name aus "tailscale status">
systemctl restart kontor
```

Testinstanz (Port 8081, HTTPS-Port 8443): dieselben drei Zeilen in
`/etc/kontor/kontor-test.env` mit `:8443` an der Adresse, dann
`tailscale serve --bg --https=8443 http://127.0.0.1:8081`. Freigabe beenden:
`tailscale serve --https=8443 off`; alle Freigaben anzeigen:
`tailscale serve status`.

## Anderer Proxy statt Tailscale

Kontor verlangt nur die drei Variablen oben. Jeder Reverse-Proxy auf demselben
Rechner (Caddy, nginx) funktioniert genauso, wenn er HTTPS entgegennimmt und
an `127.0.0.1:<Port>` weiterreicht. Das Skript `kontor-https` richtet nur den
Weg über Tailscale ein; Zertifikat und Zugriffsbeschränkung sind bei einem
anderen Proxy dessen Aufgabe.
