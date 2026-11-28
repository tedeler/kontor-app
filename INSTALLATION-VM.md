# Kontor in einer VM mit Debian 13 und Tailscale installieren

Alle Befehle werden **als root** ausgeführt (`su -` bzw. `sudo -i`). Diese Anleitung beschreibt die Installation in einer eigenen virtuellen Maschine (z. B. unter Proxmox VE) mit
Debian 13 „trixie“. Zugriff gibt es danach nur über HTTPS und nur aus dem eigenen Tailnet. Für einen
Proxmox-LXC-Container gilt die Anleitung in der [README](README.md#installation-als-systemd-dienst-im-proxmox-lxc-container),
für HTTPS die Anleitung in [HTTPS.md](HTTPS.md).

```
Handy / Laptop (im Tailnet) ──HTTPS──▶ VM: Tailscale (Port 443, Zertifikat) ──http──▶ Kontor auf 127.0.0.1:8000
```

Ablauf in Kurzform: VM anlegen → Debian installieren → Kontor installieren → Tailscale anmelden →
`kontor-https einrichten` → Login über die https-Adresse einrichten.

## Unterschiede zum LXC-Container

| Thema | LXC-Container | VM |
| --- | --- | --- |
| Tailscale | Der Host muss `/dev/net/tun` durchreichen | läuft ohne Zusatzeinstellung |
| Härtung der Unit | braucht `nesting=1` | keine Voraussetzung |
| `systemd-creds` | meist nur `--with-key=host` | mit virtuellem TPM: Schlüssel aus Host-Schlüssel **und** TPM |
| Sicherung von außen | Container-Snapshot/-Backup | VM-Snapshot/-Backup (mit Gast-Agent konsistent) |
| Ressourcen | sehr sparsam | etwas mehr Arbeitsspeicher und Platte |

Kontor selbst wird in beiden Fällen gleich installiert und bedient.

## 1. VM anlegen (Beispiel Proxmox VE)

| Einstellung | Empfehlung |
| --- | --- |
| Betriebssystem | Debian 13 Netinstall-ISO (amd64) |
| System | Maschine `q35`, BIOS `OVMF (UEFI)` mit EFI-Disk; **TPM-State hinzufügen (v2.0)**; QEMU Guest Agent an |
| Festplatte | VirtIO SCSI, 16 GB (Datenbank, Sicherungen, venv für die Testinstanz) |
| CPU | 2 Kerne, Typ `host` |
| Arbeitsspeicher | 2 GB (1 GB reicht ohne Testinstanz) |
| Netz | VirtIO, Bridge ins Heimnetz; feste IP (DHCP-Reservierung am Router); **keine Portweiterleitung** |

Das virtuelle TPM ist optional, macht die verschlüsselten Geheimnisse aber an diese VM gebunden (siehe Schritt 5).

## 2. Debian 13 installieren

1. Von der ISO starten, „Install“ (ohne grafische Oberfläche).
2. Bei der Softwareauswahl **nur** „SSH server“ und „Standard-Systemwerkzeuge“ ankreuzen, keine Desktop-Umgebung.
3. Nach dem Neustart als root anmelden (Konsole oder SSH) und das System aktualisieren:

   ```bash
   apt update && apt full-upgrade -y
   apt install -y python3 python3-venv git curl openssl sudo qemu-guest-agent unattended-upgrades
   apt install -y tpm2-tools          # nur mit virtuellem TPM
   systemctl enable --now qemu-guest-agent
   ```

   Debian 13 bringt Python 3.13 mit (Kontor verlangt ≥ 3.11). `unattended-upgrades` spielt
   Sicherheitsupdates von Debian automatisch ein.
4. Prüfen, ob das TPM erkannt wird (nur mit TPM):

   ```bash
   systemd-analyze has-tpm2        # früher: systemd-creds has-tpm2
   ```

   Erwartet wird `yes` und darunter nur Zeilen mit `+` (`+firmware`, `+driver`, `+system`, `+subsystem`,
   `+libraries`). Bedeutung der `-`-Zeilen:

   | Zeile | Ursache | Abhilfe |
   | --- | --- | --- |
   | `-firmware`, `-driver` | Die VM sieht kein TPM | In Proxmox unter Hardware „TPM-State“ (v2.0) hinzufügen, dann die VM **herunterfahren und neu starten** (ein Neustart innerhalb der VM übernimmt neue Hardware nicht). Prüfen: `ls /dev/tpm*` |
   | `-libraries` mit `libtss2-…` | Die TPM-Bibliotheken fehlen | `apt install tpm2-tools` (bringt `libtss2-esys`, `-rc`, `-mu` mit); prüfen: `ldconfig -p \| grep libtss2` |

   Bleibt es bei `partial` oder `no`, funktioniert Kontor trotzdem: `systemd-creds` nimmt dann nur den
   Host-Schlüssel (wie im LXC-Container).

## 3. Kontor installieren

```bash
git clone https://github.com/tedeler/kontor-app /opt/kontor/src
python3 -m venv /opt/kontor/venv
/opt/kontor/venv/bin/pip install /opt/kontor/src
B=$(/opt/kontor/venv/bin/python -c 'import importlib.resources as r; print(r.files("kontor.betrieb"))')
```

## 4. Benutzer, Units und Umgebungsdatei

```bash
install -D -m 0644 "$B/kontor.sysusers" /etc/sysusers.d/kontor.conf && systemd-sysusers
install -d -m 0750 -o root -g kontor /etc/kontor
install -m 0640 -o root -g kontor "$B/kontor.env" /etc/kontor/kontor.env
install -m 0644 "$B/kontor.service" "$B/kontor-sicherung.service" "$B/kontor-sicherung.timer" \
  "$B/kontor-update.path" "$B/kontor-update.service" /etc/systemd/system/
install -m 0755 "$B/kontor-https.sh" /usr/local/bin/kontor-https
install -m 0755 "$B/kontor-test.sh"  /usr/local/bin/kontor-test
```

`/etc/kontor/kontor.env` enthält keine Geheimnisse; Anmeldung, Heimnetz, `systemd-creds` und die empfohlenen
Automatiken sind voreingestellt. FinTS wird später in der Oberfläche eingerichtet, ntfy und Mail bei Bedarf
in dieser Datei (README, „Konfiguration der echten Anbindungen“).

## 5. Geheimnisse verschlüsselt ablegen

Ohne `--with-key` wählt `systemd-creds` selbst: mit TPM den Host-Schlüssel **und** das TPM, sonst nur den
Host-Schlüssel. Daher erst Schritt 2.4 klären, dann die Dateien anlegen; wer später ein TPM nachrüstet, legt sie
neu an, damit sie es nutzen. Die PIN wird nie in eine Datei, Umgebungsvariable oder Kommandozeile geschrieben.

```bash
systemd-ask-password -n "Banking-PIN:" | systemd-creds encrypt --name=kontor-bank-pin - /etc/kontor/kontor-bank-pin.cred
openssl rand -base64 32 | systemd-creds encrypt --name=kontor-geheimnisschluessel - /etc/kontor/kontor-geheimnisschluessel.cred
```

Wer die PIN lieber nur in der Oberfläche eingibt, legt nur den Geheimnisschlüssel an und zusätzlich:

```bash
install -D -m 0644 "$B/pin-eingabe.conf" /etc/systemd/system/kontor.service.d/pin-eingabe.conf
```

und ändert in `/etc/kontor/kontor.env` die Zeile auf `KONTOR_BANK_PIN_QUELLE=eingabe`. Ohne diese Änderung bleibt
Kontor bei `systemd-creds` (der Wert aus der Umgebungsdatei hat Vorrang vor dem im Drop-in) und jeder Abruf
scheitert mit „PIN fehlt“. Prüfen: `ls /run/credentials/kontor.service/` zeigt bei PIN aus der Datei
`kontor-bank-pin`.

Wichtig: Mit TPM lassen sich die `.cred`-Dateien nur in **dieser** VM entschlüsseln. Das TPM-State-Laufwerk
gehört deshalb in das VM-Backup (Proxmox sichert es mit). Geht es verloren, beide Dateien neu anlegen; im
Geheimnisspeicher abgelegte Tokens und Passwörter müssen dann neu eingetragen werden.

## 6. Kontor starten

```bash
systemctl daemon-reload
systemctl enable --now kontor.service kontor-sicherung.timer kontor-update.path
journalctl -u kontor -n 30
curl -s http://127.0.0.1:8000/api/gesundheit
```

Den Login noch **nicht** über http einrichten, sondern erst nach der Umstellung auf HTTPS (Schritt 8).

## 7. Tailscale einrichten und auf HTTPS umstellen

1. In der Tailscale-Admin-Konsole unter **DNS** „MagicDNS“ und „HTTPS Certificates“ einschalten (einmalig je
   Tailnet).
2. Tailscale in der VM installieren und anmelden:

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   tailscale up --hostname=kontor
   ```

   Dem angezeigten Link folgen und die VM im eigenen Konto freigeben. Der Name `kontor` ergibt später die
   Adresse `https://kontor.<tailnet>.ts.net`.
3. In der Admin-Konsole bei der Maschine `kontor` **„Disable key expiry“** wählen. Sonst muss sich die VM
   nach etwa sechs Monaten neu anmelden und Kontor ist so lange nicht erreichbar.
4. Umstellen:

   ```bash
   kontor-https einrichten
   kontor-https status
   ```

   Das Skript richtet `tailscale serve` ein, setzt `KONTOR_HOST=127.0.0.1`, `KONTOR_SITZUNG_COOKIE_SECURE=1`
   und `KONTOR_OEFFENTLICHE_URL=https://kontor.<tailnet>.ts.net` und startet Kontor neu. Einzelheiten,
   Rücknahme und Fehlersuche: [HTTPS.md](HTTPS.md).

Danach lauscht Kontor nur noch auf 127.0.0.1; aus dem Heimnetz ist ohne Tailscale nur noch SSH erreichbar.
Wer auch SSH nur über Tailscale will, schaltet es mit `tailscale set --ssh` ein und kann den SSH-Dienst danach
auf die Tailscale-Adresse beschränken.

## 8. Login einrichten

1. Einrichtungscode lesen: `cat /var/lib/kontor/kontor.sqlite3.einrichtung`
2. Auf einem Gerät im Tailnet `https://kontor.<tailnet>.ts.net/anmelden` öffnen, Code und Haushaltspasswort
   (12–1024 Zeichen) eingeben.

Alternativ direkt auf der VM:

```bash
set -a; . /etc/kontor/kontor.env; set +a; sudo -u kontor -E /opt/kontor/venv/bin/python -m kontor.anmeldung passwort-setzen
```

## 9. Daten übernehmen und Bank einrichten

- **Import:** KMyMoney-, GnuCash- oder ALF-BanCo-Datei in der Oberfläche unter **Import** hochladen.
- **Bankzugang:** Einstellungen → Bank, siehe README, „Bankzugang (FinTS) einrichten“.
- **Gmail über OAuth:** `KONTOR_OAUTH_REDIRECT_URI=https://kontor.<tailnet>.ts.net/oauth2/rueckruf` setzen und
  in der Google-Konsole eintragen (HTTPS.md, „Was sich im Betrieb ändert“).
- **Handy:** Tailscale-App installieren, im selben Tailnet anmelden, die https-Adresse öffnen und als App
  „Zum Home-Bildschirm“ hinzufügen.

## 10. Betrieb

| Aufgabe | So geht es |
| --- | --- |
| Kontor-Update | About-Dialog → „Aktualisieren“ (README, „Updates“) |
| Debian-Updates | automatisch über `unattended-upgrades`; gelegentlich `apt full-upgrade` und Neustart |
| Tailscale-Update | kommt mit den Debian-Updates (Paketquelle von Tailscale) |
| Stündliche Sicherungspunkte | `kontor-sicherung.timer` nach `/var/lib/kontor/sicherungen`; Verzeichnis zusätzlich außerhalb der VM ablegen (README, „Datensicherung im Betrieb“) |
| Sicherung der ganzen VM | Proxmox-Backup bzw. -Snapshot; mit dem Gast-Agenten wird das Dateisystem dabei kurz eingefroren |
| Testinstanz | `kontor-test start <branch>`, Adresse `https://kontor.<tailnet>.ts.net:8443` ([TESTINSTANZ.md](TESTINSTANZ.md)) |
| Protokoll | `journalctl -u kontor -f` |
| Zustand HTTPS | `kontor-https status` |

## Wenn etwas nicht klappt

| Anzeichen | Abhilfe |
| --- | --- |
| `systemd-analyze has-tpm2` meldet `partial` oder `no` | siehe Tabelle in Schritt 2.4; ohne TPM funktioniert alles mit dem Host-Schlüssel |
| Kontor startet nicht: Credential lässt sich nicht entschlüsseln | `.cred`-Dateien wurden auf einer anderen Maschine oder vor einem TPM-Tausch angelegt: Schritt 5 wiederholen |
| Seite lädt nicht | Gerät im Tailnet? `tailscale status` auf dem Gerät und in der VM |
| Nach Monaten plötzlich nicht erreichbar | Schlüssel der VM abgelaufen: `tailscale up` in der VM, danach „Disable key expiry“ |
| Synchronisation meldet „PIN fehlt“ trotz PIN-Datei | `ls /run/credentials/kontor.service/`: fehlt `kontor-bank-pin`, ist `pin-eingabe.conf` installiert – entfernen (`/etc/systemd/system/kontor.service.d/`), `systemctl daemon-reload`, Neustart |
| `systemd-creds encrypt` meldet `InteractiveAuthenticationRequired` | nicht als root aufgerufen: erst `su -` bzw. `sudo -i` |
| Weitere Fehlerbilder | [HTTPS.md](HTTPS.md#wenn-etwas-nicht-klappt) |
