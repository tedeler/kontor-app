#!/usr/bin/env bash
# kontor-https.sh - Kontor nur noch ueber HTTPS (Tailscale Serve) erreichbar machen
#
# Kontor spricht selbst kein TLS. Dieses Skript stellt den Tailscale-Dienst
# davor: er nimmt HTTPS mit einem gueltigen Zertifikat entgegen und reicht die
# Anfragen an Kontor auf 127.0.0.1 weiter. Kontor ist danach nur noch fuer
# Geraete im eigenen Tailnet erreichbar; der bisherige Zugang ueber http und
# Port entfaellt. Die Testinstanz bekommt einen eigenen HTTPS-Port.
#
# Ziel: /usr/local/bin/kontor-https (Rechte 0755), siehe HTTPS.md (D-239).
#
# Aufruf als root auf dem Server (Debian):
#   kontor-https einrichten        HTTPS einschalten (wiederholbar)
#   kontor-https status            Einstellungen, Freigaben und Erreichbarkeit zeigen
#   kontor-https zurueck           HTTPS ausschalten, vorherige Einstellungen herstellen
#
# Optionen fuer "einrichten":
#   --tailscale-installieren       Tailscale mit dem offiziellen Installationsskript einrichten, falls es fehlt
#   --name <name>                  DNS-Name statt des von Tailscale gemeldeten (z. B. kontor.<tailnet>.ts.net)
#   --test-port <port>             HTTPS-Port der Testinstanz (Vorgabe 8443)

set -euo pipefail

PYTHON="${KONTOR_PYTHON:-/opt/kontor/venv/bin/python}"
TAILSCALE="${KONTOR_TAILSCALE:-tailscale}"
HAUPT_ENV="${KONTOR_HAUPT_ENV:-/etc/kontor/kontor.env}"
TEST_ENV="${KONTOR_TEST_ENV:-/etc/kontor/kontor-test.env}"
DIENST="kontor.service"
TEST_DIENST="kontor-test.service"
SICHERUNG_ENDUNG=".vor-https"
WARTEZEIT=40          # Sekunden, bis Kontor nach dem Neustart antworten muss
VARIABLEN=(KONTOR_HOST KONTOR_SITZUNG_COOKIE_SECURE KONTOR_OEFFENTLICHE_URL)

fehler() { echo "Fehler: $*" >&2; exit 1; }
hinweis() { echo "Hinweis: $*" >&2; }

hilfe() {
    # Kopfkommentar ohne Shebang und ohne fuehrendes "# " ausgeben
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

pruefe_root() {
    [ "$(id -u)" -eq 0 ] || fehler "Bitte als root ausfuehren."
}

# ---------------------------------------------------------------- Umgebungsdateien

# wert <variable> <datei>: letzter gesetzter Wert, leer wenn nicht gesetzt
wert() {
    [ -r "$2" ] || return 0
    sed -n "s/^$1=\(.*\)$/\1/p" "$2" | tail -n 1 | sed 's/[[:space:]]*$//'
}

# setze <variable> <wert> <datei>: vorhandene Zeile ersetzen, sonst anhaengen (auskommentierte Zeilen bleiben)
setze() {
    local var="$1" neu="$2" datei="$3" tmp
    tmp="$(mktemp "${datei}.XXXXXX")"
    if grep -q "^${var}=" "$datei"; then
        awk -v var="$var" -v neu="$neu" 'BEGIN { FS = "=" } $1 == var { print var "=" neu; next } { print }' "$datei" > "$tmp"
    else
        cat "$datei" > "$tmp"
        printf '%s=%s\n' "$var" "$neu" >> "$tmp"
    fi
    chmod --reference="$datei" "$tmp"
    chown --reference="$datei" "$tmp"
    mv "$tmp" "$datei"
}

# entferne <variable> <datei>
entferne() {
    local var="$1" datei="$2" tmp
    tmp="$(mktemp "${datei}.XXXXXX")"
    awk -v var="$var" 'BEGIN { FS = "=" } $1 == var { next } { print }' "$datei" > "$tmp"
    chmod --reference="$datei" "$tmp"
    chown --reference="$datei" "$tmp"
    mv "$tmp" "$datei"
}

# Stand vor der Umstellung einmal festhalten (spaetere Laeufe ueberschreiben ihn nicht)
sichere() {
    local datei="$1"
    if [ ! -e "${datei}${SICHERUNG_ENDUNG}" ]; then
        cp -p "$datei" "${datei}${SICHERUNG_ENDUNG}"
        echo "    Stand vorher gesichert: ${datei}${SICHERUNG_ENDUNG}"
    fi
}

# Die drei Variablen auf den gesicherten Stand zurueckstellen (nicht gesetzte entfallen)
stelle_zurueck() {
    local datei="$1" var alt
    [ -e "$datei" ] || return 0
    [ -e "${datei}${SICHERUNG_ENDUNG}" ] || { hinweis "Keine Sicherung ${datei}${SICHERUNG_ENDUNG}: $datei bleibt unveraendert."; return 0; }
    for var in "${VARIABLEN[@]}"; do
        if grep -q "^${var}=" "${datei}${SICHERUNG_ENDUNG}"; then
            alt="$(wert "$var" "${datei}${SICHERUNG_ENDUNG}")"
            setze "$var" "$alt" "$datei"
        else
            entferne "$var" "$datei"
        fi
    done
    echo "    Zurueckgestellt: $datei"
}

port_aus() {
    local p
    p="$(wert KONTOR_PORT "$1")"
    echo "${p:-$2}"
}

# HTTPS-Port aus einer Adresse wie https://name:8443 (ohne Angabe 443)
https_port() {
    local p
    p="$(printf '%s' "$1" | sed -n 's#^https://[^/:]*:\([0-9][0-9]*\).*$#\1#p')"
    echo "${p:-443}"
}

# ---------------------------------------------------------------- Tailscale

tailscale_vorhanden() { command -v "$TAILSCALE" > /dev/null 2>&1; }

tailscale_installieren() {
    [ -e /etc/debian_version ] || fehler "Die automatische Installation ist nur fuer Debian vorgesehen."
    echo "==> Installiere Tailscale (offizielles Installationsskript von tailscale.com)"
    if ! command -v curl > /dev/null 2>&1; then
        apt-get update
        apt-get install -y curl
    fi
    curl -fsSL https://tailscale.com/install.sh | sh
}

# Meldet "<Zustand> <DNS-Name>" des eigenen Geraets
tailscale_stand() {
    "$TAILSCALE" status --json 2>/dev/null | "$PYTHON" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    print("unbekannt -"); raise SystemExit
name = ((d.get("Self") or {}).get("DNSName") or "").rstrip(".")
print(d.get("BackendState") or "unbekannt", name or "-")'
}

freigeben() {     # freigeben <https-port> <lokaler port>
    "$TAILSCALE" serve --bg --https="$1" "http://127.0.0.1:$2"
}

freigabe_beenden() {
    "$TAILSCALE" serve --https="$1" off > /dev/null 2>&1 || true
}

# ---------------------------------------------------------------- Kontor

warte_auf_port() {
    local i
    for ((i = 0; i < WARTEZEIT; i++)); do
        if (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

dienst_aktiv() { systemctl is-active --quiet "$1"; }

erreichbar() {    # erreichbar <adresse>: fragt /api/gesundheit ueber HTTPS ab
    "$PYTHON" -c '
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1] + "/api/gesundheit", timeout=20) as r:
        raise SystemExit(0 if r.status == 200 else 1)
except Exception:
    raise SystemExit(1)' "$1"
}

# ---------------------------------------------------------------- Befehle

einrichten() {
    local installieren=0 name="" test_https=8443
    while [ $# -gt 0 ]; do
        case "$1" in
            --tailscale-installieren) installieren=1 ;;
            --name) [ $# -ge 2 ] || fehler "--name braucht einen Wert."; name="$2"; shift ;;
            --test-port) [ $# -ge 2 ] || fehler "--test-port braucht einen Wert."; test_https="$2"; shift ;;
            *) fehler "Unbekannte Option: $1" ;;
        esac
        shift
    done
    case "$test_https" in ''|*[!0-9]*) fehler "--test-port muss eine Zahl sein." ;; esac
    [ "$test_https" != "443" ] || fehler "Port 443 gehoert der Hauptinstanz; fuer die Testinstanz einen anderen waehlen."

    pruefe_root
    [ -x "$PYTHON" ] || fehler "$PYTHON nicht gefunden. Laeuft hier Kontor?"
    [ -f "$HAUPT_ENV" ] || fehler "$HAUPT_ENV nicht gefunden."

    if ! tailscale_vorhanden; then
        if [ "$installieren" -eq 1 ]; then
            tailscale_installieren
            tailscale_vorhanden || fehler "Tailscale ist nach der Installation nicht aufrufbar."
        else
            fehler "Tailscale ist nicht installiert. Mit --tailscale-installieren richtet das Skript es ein (siehe HTTPS.md)."
        fi
    fi

    local zustand gemeldet
    read -r zustand gemeldet <<< "$(tailscale_stand)"
    if [ "$zustand" != "Running" ]; then
        fehler "Tailscale ist nicht verbunden (Zustand: ${zustand}). Zuerst 'tailscale up' ausfuehren und anmelden, dann dieses Skript erneut starten."
    fi
    if [ -z "$name" ]; then
        [ "$gemeldet" != "-" ] || fehler "Tailscale meldet keinen DNS-Namen. MagicDNS in der Admin-Konsole einschalten oder --name angeben."
        name="$gemeldet"
    fi
    case "$name" in *[!A-Za-z0-9.-]*|'') fehler "Ungueltiger Name: $name" ;; esac

    local port adresse
    port="$(port_aus "$HAUPT_ENV" 8000)"
    adresse="https://${name}"

    echo "==> Gebe Kontor ueber HTTPS frei: ${adresse} -> 127.0.0.1:${port}"
    if ! freigeben 443 "$port"; then
        echo >&2
        echo "Tailscale konnte die Freigabe nicht einrichten. An Kontor wurde nichts geaendert." >&2
        echo "Haeufigste Ursache: In der Tailscale-Admin-Konsole (DNS) sind MagicDNS oder" >&2
        echo "die HTTPS-Zertifikate noch nicht eingeschaltet." >&2
        exit 1
    fi

    echo "==> Stelle die Hauptinstanz um ($HAUPT_ENV)"
    sichere "$HAUPT_ENV"
    setze KONTOR_HOST 127.0.0.1 "$HAUPT_ENV"
    setze KONTOR_SITZUNG_COOKIE_SECURE 1 "$HAUPT_ENV"
    setze KONTOR_OEFFENTLICHE_URL "$adresse" "$HAUPT_ENV"

    echo "==> Starte Kontor neu"
    systemctl restart "$DIENST"
    if ! warte_auf_port "$port"; then
        echo "Kontor antwortet nach ${WARTEZEIT} s nicht auf Port ${port}." >&2
        echo "Protokoll: journalctl -u ${DIENST} -n 30    Zurueck: $0 zurueck" >&2
        exit 1
    fi

    # Testinstanz: Umgebungsdatei anlegen (falls noch keine da ist) und umstellen. Die Freigabe selbst
    # schaltet "kontor-test start" ein und "kontor-test stop" wieder aus.
    local test_adresse="${adresse}:${test_https}" test_port
    echo "==> Stelle die Testinstanz um ($TEST_ENV)"
    if [ ! -e "$TEST_ENV" ]; then
        "$PYTHON" -c 'import importlib.resources as r, sys
sys.stdout.write(r.files("kontor.betrieb").joinpath("kontor-test.env").read_text(encoding="utf-8"))' > "$TEST_ENV"
        chmod 0640 "$TEST_ENV"
        chown --reference="$HAUPT_ENV" "$TEST_ENV"
        cp -p "$TEST_ENV" "${TEST_ENV}${SICHERUNG_ENDUNG}"
        echo "    Angelegt aus der ausgelieferten Vorlage."
    else
        sichere "$TEST_ENV"
    fi
    setze KONTOR_HOST 127.0.0.1 "$TEST_ENV"
    setze KONTOR_SITZUNG_COOKIE_SECURE 1 "$TEST_ENV"
    setze KONTOR_OEFFENTLICHE_URL "$test_adresse" "$TEST_ENV"
    if dienst_aktiv "$TEST_DIENST"; then
        test_port="$(port_aus "$TEST_ENV" 8081)"
        systemctl restart "$TEST_DIENST"
        warte_auf_port "$test_port" || hinweis "Die Testinstanz antwortet nicht auf Port ${test_port} (kontor-test log)."
        freigeben "$test_https" "$test_port" || hinweis "Freigabe der Testinstanz fehlgeschlagen (kontor-test neu wiederholt sie)."
    fi

    echo "==> Pruefe ${adresse}"
    if erreichbar "$adresse"; then
        echo "    Kontor antwortet ueber HTTPS."
    else
        hinweis "Noch keine Antwort ueber HTTPS. Das erste Zertifikat kann bis zu einer Minute brauchen;"
        hinweis "spaeter mit '$0 status' erneut pruefen. Dieser Server muss den Namen selbst aufloesen koennen."
    fi

    echo
    echo "Fertig. Kontor ist jetzt nur noch ueber Tailscale erreichbar:"
    echo "  Hauptinstanz: ${adresse}"
    echo "  Testinstanz:  ${test_adresse}   (nach 'kontor-test start <branch>')"
    echo "Lesezeichen und die installierte App auf die neue Adresse umstellen."
    echo "Zuruecknehmen: $0 zurueck"
}

zurueck() {
    pruefe_root
    [ -f "$HAUPT_ENV" ] || fehler "$HAUPT_ENV nicht gefunden."
    local test_adresse
    test_adresse="$(wert KONTOR_OEFFENTLICHE_URL "$TEST_ENV")"
    echo "==> Beende die HTTPS-Freigaben"
    if tailscale_vorhanden; then
        freigabe_beenden 443
        case "$test_adresse" in https://*) freigabe_beenden "$(https_port "$test_adresse")" ;; esac
    fi
    echo "==> Stelle die Einstellungen zurueck"
    stelle_zurueck "$HAUPT_ENV"
    stelle_zurueck "$TEST_ENV"
    systemctl restart "$DIENST"
    if dienst_aktiv "$TEST_DIENST"; then
        systemctl restart "$TEST_DIENST"
    fi
    local host port
    host="$(wert KONTOR_HOST "$HAUPT_ENV")"
    port="$(port_aus "$HAUPT_ENV" 8000)"
    echo "Fertig. Kontor lauscht wieder auf ${host:-127.0.0.1}:${port} (http)."
}

status() {
    local adresse test_adresse
    adresse="$(wert KONTOR_OEFFENTLICHE_URL "$HAUPT_ENV")"
    test_adresse="$(wert KONTOR_OEFFENTLICHE_URL "$TEST_ENV")"
    echo "Hauptinstanz ($HAUPT_ENV)"
    echo "  KONTOR_HOST=$(wert KONTOR_HOST "$HAUPT_ENV")"
    echo "  KONTOR_SITZUNG_COOKIE_SECURE=$(wert KONTOR_SITZUNG_COOKIE_SECURE "$HAUPT_ENV")"
    echo "  KONTOR_OEFFENTLICHE_URL=${adresse}"
    echo "Testinstanz ($TEST_ENV)"
    echo "  KONTOR_OEFFENTLICHE_URL=${test_adresse}"
    case "$adresse" in
        https://*)
            if [ -x "$PYTHON" ] && erreichbar "$adresse"; then
                echo "Erreichbarkeit: ${adresse} antwortet."
            else
                echo "Erreichbarkeit: ${adresse} antwortet NICHT."
            fi
            ;;
        *)  echo "HTTPS ist nicht eingerichtet." ;;
    esac
    if tailscale_vorhanden; then
        echo "Freigaben (tailscale serve status):"
        "$TAILSCALE" serve status 2>&1 | sed 's/^/  /' || true
    else
        echo "Tailscale ist nicht installiert."
    fi
}

befehl="${1:-hilfe}"
[ $# -gt 0 ] && shift
case "$befehl" in
    einrichten)        einrichten "$@" ;;
    zurueck)           zurueck ;;
    status)            status ;;
    hilfe|-h|--help)   hilfe ;;
    *)                 hilfe >&2; exit 2 ;;
esac
