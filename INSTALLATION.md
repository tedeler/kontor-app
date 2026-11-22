# Kontor auf einem Debian-Server installieren

Diese Anleitung richtet Kontor auf einer frischen Debian-13-Maschine mit
systemd ein und macht es über Tailscale ausschließlich per HTTPS erreichbar.
Die Befehle werden als `root` ausgeführt. Die Maschine braucht Internetzugang;
Router-Ports müssen nicht freigegeben werden.

## 1. Tailscale installieren und verbinden

```bash
apt update
apt install -y curl
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up
```

Den angezeigten Anmeldelink öffnen und den Server dem eigenen Tailnet
hinzufügen. In der Tailscale-Admin-Konsole außerdem unter **DNS** MagicDNS und
**HTTPS Certificates** einschalten. Auch jedes Gerät, das Kontor verwenden
soll, muss mit demselben Tailnet verbunden sein.

## 2. Kontor installieren

```bash
apt install -y python3 python3-venv git openssl
install -d /opt/kontor
git clone https://github.com/tedeler/kontor-app /opt/kontor/src
python3 -m venv /opt/kontor/venv
/opt/kontor/venv/bin/pip install /opt/kontor/src
B=$(/opt/kontor/venv/bin/python -c 'import importlib.resources as r; print(r.files("kontor.betrieb"))')
```

Benutzer, Konfiguration und Dienstdateien anlegen:

```bash
install -m 0644 "$B/kontor.sysusers" /etc/sysusers.d/kontor.conf
systemd-sysusers
install -d -m 0750 -o root -g kontor /etc/kontor
install -m 0640 -o root -g kontor "$B/kontor.env" /etc/kontor/kontor.env
install -m 0644 "$B/kontor.service" "$B/kontor-sicherung.service" \
  "$B/kontor-sicherung.timer" "$B/kontor-update.path" \
  "$B/kontor-update.service" /etc/systemd/system/
```

Die PIN wird in dieser Anleitung später in der Oberfläche eingegeben. Daher
den entsprechenden systemd-Drop-in installieren und den Datenschlüssel
verschlüsselt ablegen:

```bash
install -D -m 0644 "$B/pin-eingabe.conf" \
  /etc/systemd/system/kontor.service.d/pin-eingabe.conf
openssl rand -base64 32 | systemd-creds encrypt --with-key=host \
  --name=kontor-geheimnisschluessel - \
  /etc/kontor/kontor-geheimnisschluessel.cred
```

Die verschlüsselte Datei nicht löschen: Ohne sie sind gespeicherte Geheimnisse
nicht mehr lesbar. Durch `--with-key=host` ist sie an diesen Server gebunden.

## 3. Kontor starten und HTTPS einschalten

```bash
systemctl daemon-reload
systemctl enable kontor.service
systemctl enable --now kontor-sicherung.timer kontor-update.path
install -m 0755 "$B/kontor-https.sh" /usr/local/bin/kontor-https
install -m 0755 "$B/kontor-test.sh" /usr/local/bin/kontor-test
kontor-https einrichten
```

Das Skript bindet Kontor nur noch an `127.0.0.1` und richtet Tailscale Serve
mit HTTPS ein. Es zeigt anschließend die Adresse an, zum Beispiel
`https://kontor.mein-tailnet.ts.net`. Wenn die Einrichtung wegen fehlender
Tailscale-HTTPS-Freigabe scheitert, die DNS-/Zertifikatseinstellungen der
Admin-Konsole prüfen und `kontor-https einrichten` erneut ausführen.

## 4. Anmelden

Den einmaligen Einrichtungscode als `root` ausgeben und im Browser zusammen
mit einem Haushaltspasswort eingeben:

```bash
cat /var/lib/kontor/kontor.sqlite3.einrichtung
```

Die HTTPS-Adresse nur auf einem Gerät öffnen, auf dem Tailscale verbunden ist.
Den Einrichtungscode nicht weitergeben. Danach in Kontor unter **Import** den
eigenen KMyMoney- oder GnuCash-Datenstand übernehmen. Keine echten Bankdaten
in öffentlichen oder fremden Testsystemen verwenden.

## Prüfen und Hilfe

```bash
kontor-https status
systemctl status kontor
journalctl -u kontor -n 50
```

Weitere Details, Rücknahme der HTTPS-Umstellung und Fehlersuche stehen in
[HTTPS.md](HTTPS.md). Die ausführliche Dienstinstallation samt
LXC-Hinweisen und Updates steht im [README](README.md).
