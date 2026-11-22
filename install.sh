#!/usr/bin/env bash
# Installation nach INSTALLATION.md im Branch docs/debian-tailscale-install.
set +x
set -Eeuo pipefail

schritt="Vorprüfung"
trap 'printf "Fehler: %s fehlgeschlagen. Die Installation kann unvollständig sein; vorhandene Dateien vor einem erneuten Versuch prüfen.\n" "$schritt" >&2' ERR

fehler() {
    printf 'Fehler: %s\n' "$1" >&2
    exit 1
}

tailscale_hinweis() {
    printf '%s\n' \
        'Tailscale muss bereits installiert und mit dem Tailnet verbunden sein.' \
        'Als root „tailscale up“ ausführen und den Anmeldelink öffnen.' \
        'In der Tailscale-Admin-Konsole MagicDNS und HTTPS-Zertifikate aktivieren.' >&2
    exit 1
}

[[ $EUID -eq 0 ]] || fehler 'Dieses Skript muss als root ausgeführt werden.'

# Tailscale gibt sein JSON mit zwei Leerzeichen je Ebene aus. Nur das
# BackendState-Feld auf der obersten Ebene darf die Installation freigeben.
command -v tailscale >/dev/null 2>&1 || tailscale_hinweis
if ! status="$(tailscale status --json 2>/dev/null)" ||
   ! printf '%s\n' "$status" | grep -Eq '^  "BackendState": "Running",?$'; then
    tailscale_hinweis
fi
unset status

[[ -r /etc/os-release ]] || fehler 'Debian-Version konnte nicht ermittelt werden.'
# shellcheck source=/dev/null
. /etc/os-release
[[ ${ID:-} == debian && ${VERSION_ID:-} == 13 ]] ||
    fehler 'Dieses Skript ist für Debian 13 bestimmt.'
[[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1 &&
    systemctl show --property=Version --value >/dev/null 2>&1 ||
    fehler 'Ein laufendes systemd wird benötigt.'

for pfad in /opt/kontor /opt/kontor-test /etc/kontor /var/lib/kontor \
    /var/lib/kontor-test /etc/sysusers.d/kontor.conf \
    /etc/systemd/system/kontor.service /etc/systemd/system/kontor.service.d \
    /etc/systemd/system/kontor-sicherung.service /etc/systemd/system/kontor-sicherung.timer \
    /etc/systemd/system/kontor-update.path /etc/systemd/system/kontor-update.service \
    /etc/systemd/system/kontor-test.service /usr/local/bin/kontor-https \
    /usr/local/bin/kontor-test /usr/lib/systemd/system/kontor.service \
    /usr/lib/systemd/system/kontor-sicherung.service /usr/lib/systemd/system/kontor-sicherung.timer \
    /usr/lib/systemd/system/kontor-update.path /usr/lib/systemd/system/kontor-update.service \
    /usr/lib/systemd/system/kontor-test.service; do
    [[ ! -e $pfad && ! -L $pfad ]] ||
        fehler "Vorhandene Kontor-Datei oder -Installation: $pfad. Es wurde nichts geändert."
done
if getent passwd kontor >/dev/null || getent group kontor >/dev/null; then
    fehler 'Der Benutzer oder die Gruppe kontor existiert bereits. Es wurde nichts geändert.'
fi

schritt="Paketinstallation"
printf 'Installiere benötigte Debian-Pakete …\n'
apt-get update >/dev/null
apt-get install -y python3 python3-venv git openssl >/dev/null

schritt="Installation von Kontor"
printf 'Installiere Kontor unter /opt/kontor …\n'
install -d /opt/kontor
git clone https://github.com/tedeler/kontor-app /opt/kontor/src
python3 -m venv /opt/kontor/venv
/opt/kontor/venv/bin/pip install /opt/kontor/src
B=$(/opt/kontor/venv/bin/python -c 'import importlib.resources as r; print(r.files("kontor.betrieb"))')

schritt="Einrichtung von Benutzer, Konfiguration und Diensten"
install -D -m 0644 "$B/kontor.sysusers" /etc/sysusers.d/kontor.conf
systemd-sysusers
install -d -m 0750 -o root -g kontor /etc/kontor
install -m 0640 -o root -g kontor "$B/kontor.env" /etc/kontor/kontor.env
install -m 0644 "$B/kontor.service" "$B/kontor-sicherung.service" \
    "$B/kontor-sicherung.timer" "$B/kontor-update.path" \
    "$B/kontor-update.service" /etc/systemd/system/
install -D -m 0644 "$B/pin-eingabe.conf" \
    /etc/systemd/system/kontor.service.d/pin-eingabe.conf

schritt="Erstellung des verschlüsselten Datenschlüssels"
openssl rand -base64 32 2>/dev/null | systemd-creds encrypt --with-key=host \
    --name=kontor-geheimnisschluessel - \
    /etc/kontor/kontor-geheimnisschluessel.cred >/dev/null 2>&1

schritt="Aktivierung der Dienste"
systemctl daemon-reload
systemctl enable kontor.service
systemctl enable --now kontor-sicherung.timer kontor-update.path
install -m 0755 "$B/kontor-https.sh" /usr/local/bin/kontor-https
install -m 0755 "$B/kontor-test.sh" /usr/local/bin/kontor-test

schritt="HTTPS-Einrichtung"
env -u KONTOR_PYTHON -u KONTOR_TAILSCALE -u KONTOR_HAUPT_ENV -u KONTOR_TEST_ENV \
    /usr/local/bin/kontor-https einrichten
