#!/usr/bin/env bash
# kontor-test.sh - Bedienhilfe fuer die Kontor-Testinstanz
#
# Fasst die wiederkehrenden Schritte zusammen: Branch holen, Datenbank und
# Konfiguration kopieren, starten, pruefen, stoppen. Die eigentliche Arbeit
# erledigt "python -m kontor.testinstanz" (ab Kontor 0.22); dieses Skript
# ruft es auf, merkt sich den zuletzt benutzten Branch und zeigt Status,
# Protokoll und Adresse an.
#
# Ziel: /usr/local/bin/kontor-test (Rechte 0755), siehe TESTINSTANZ.md (D-213).
#
# Aufruf als root auf dem Server:
#   kontor-test start <branch>     Branch einrichten, Daten kopieren, starten
#   kontor-test demo [branch]      Branch (Vorgabe main) mit Demodaten starten:
#                                  erfundener Haushalt zum Vorfuehren, ohne
#                                  Anmeldung; die echten Daten werden nicht gelesen
#   kontor-test neu                dasselbe wie zuletzt (start oder demo) noch einmal
#   kontor-test stop               Testinstanz anhalten (Datenkopie bleibt)
#   kontor-test loeschen           anhalten und Daten (Kopie oder Demodaten) loeschen
#   kontor-test status             Zustand, Branch und Adresse anzeigen
#   kontor-test log                Protokoll mitlesen (Strg+C beendet)
#
# <branch>: "feature/monatsbericht", kurz "monatsbericht", oder "main".
#
# HTTPS: Ist Kontor mit "kontor-https einrichten" auf HTTPS umgestellt (D-239),
# steht in der Umgebungsdatei der Testinstanz ihre https-Adresse
# (KONTOR_OEFFENTLICHE_URL). Dann schaltet "start"/"neu" die Tailscale-Freigabe
# fuer die Testinstanz ein und "stop"/"loeschen" wieder aus; sonst bleibt alles
# wie bisher bei http.

set -euo pipefail

PYTHON="${KONTOR_PYTHON:-/opt/kontor/venv/bin/python}"
DIENST="kontor-test.service"
ENV_DATEI="${KONTOR_TEST_ENV:-/etc/kontor/kontor-test.env}"
MERKDATEI="${KONTOR_TEST_MERKDATEI:-/root/.kontor-test-branch}"
TAILSCALE="${KONTOR_TAILSCALE:-tailscale}"
WARTEZEIT=30   # Sekunden, bis der Port antworten muss

# Der Port steht in der Umgebungsdatei der Testinstanz und laesst sich dort aendern.
port() {
    local p=""
    if [ -r "$ENV_DATEI" ]; then
        p="$(sed -n 's/^KONTOR_PORT=\([0-9][0-9]*\)[[:space:]]*$/\1/p' "$ENV_DATEI" | tail -n 1)"
    fi
    echo "${p:-8081}"
}

fehler() { echo "Fehler: $*" >&2; exit 1; }

hilfe() {
    # Kopfkommentar ohne Shebang und ohne fuehrendes "# " ausgeben
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

pruefe_umgebung() {
    [ "$(id -u)" -eq 0 ] || fehler "Bitte als root ausfuehren."
    [ -x "$PYTHON" ] || fehler "$PYTHON nicht gefunden. Laeuft hier die Hauptinstanz (ab 0.22)?"
}

# "monatsbericht" -> "feature/monatsbericht"; "main" und Namen mit "/" bleiben.
branch_name() {
    case "$1" in
        main|*/*) echo "$1" ;;
        *)        echo "feature/$1" ;;
    esac
}

# https-Adresse der Testinstanz aus der Umgebungsdatei; leer, wenn HTTPS nicht eingerichtet ist
https_adresse() {
    local a=""
    if [ -r "$ENV_DATEI" ]; then
        a="$(sed -n 's/^KONTOR_OEFFENTLICHE_URL=\(https:\/\/.*\)$/\1/p' "$ENV_DATEI" | tail -n 1 | sed 's/[[:space:]]*$//')"
    fi
    echo "$a"
}

# HTTPS-Port aus der Adresse (https://name:8443 -> 8443, ohne Angabe 443)
https_port() {
    local p
    p="$(https_adresse | sed -n 's#^https://[^/:]*:\([0-9][0-9]*\).*$#\1#p')"
    echo "${p:-443}"
}

adresse() {
    local ip a
    a="$(https_adresse)"
    if [ -n "$a" ]; then
        echo "$a"
        return
    fi
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "http://${ip:-<container-ip>}:$(port)"
}

# Tailscale-Freigabe der Testinstanz ein- und ausschalten (nur wenn HTTPS eingerichtet ist)
freigabe_ein() {
    [ -n "$(https_adresse)" ] || return 0
    echo "==> Gebe die Testinstanz ueber HTTPS frei (Port $(https_port))"
    if ! "$TAILSCALE" serve --bg --https="$(https_port)" "http://127.0.0.1:$(port)" > /dev/null; then
        echo "Die HTTPS-Freigabe ist fehlgeschlagen; die Testinstanz laeuft, ist aber nur auf dem Server selbst erreichbar." >&2
        echo "Pruefen: kontor-https status   Wiederholen: $0 neu" >&2
        exit 1
    fi
}

freigabe_aus() {
    [ -n "$(https_adresse)" ] || return 0
    "$TAILSCALE" serve --https="$(https_port)" off > /dev/null 2>&1 || true
}

warte_auf_port() {
    local i p
    p="$(port)"
    for ((i = 0; i < WARTEZEIT; i++)); do
        if (exec 3<>"/dev/tcp/127.0.0.1/${p}") 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# Zuletzt Eingerichtetes aus der Merkdatei: "<branch>" (Datenkopie) oder "demo <branch>"
gemerkte_art() {
    local erstes rest
    read -r erstes rest < "$MERKDATEI" || true
    if [ "$erstes" = "demo" ] && [ -n "$rest" ]; then echo "demo"; else echo "kopie"; fi
}

gemerkter_branch() {
    local erstes rest
    read -r erstes rest < "$MERKDATEI" || true
    if [ "$erstes" = "demo" ] && [ -n "$rest" ]; then echo "$rest"; else echo "$erstes"; fi
}

# einrichten <kopie|demo> <branch>
einrichten() {
    local art="$1" branch="$2"
    if [ "$art" = "demo" ]; then
        echo "==> Richte Testinstanz mit Demodaten ein: ${branch}"
        echo "    (Branch holen, installieren, erfundenen Haushalt aufbauen, starten)"
        "$PYTHON" -m kontor.testinstanz demo "$branch"
        echo "demo $branch" > "$MERKDATEI"
    else
        echo "==> Richte Testinstanz ein: ${branch}"
        echo "    (Branch holen, installieren, Daten kopieren, starten)"
        "$PYTHON" -m kontor.testinstanz einrichten "$branch"
        echo "$branch" > "$MERKDATEI"
    fi

    echo "==> Warte auf Port $(port) ..."
    if warte_auf_port; then
        freigabe_ein
        echo "==> Testinstanz laeuft: $(adresse)"
        if [ "$art" = "demo" ]; then
            echo "    Demodaten (erfundener Haushalt), ohne Anmeldung."
        else
            echo "    Anmeldung mit dem Haushaltspasswort."
        fi
    else
        echo "Die Testinstanz antwortet nach ${WARTEZEIT} s nicht auf Port $(port)." >&2
        echo "Letzte Protokollzeilen:" >&2
        journalctl -u "$DIENST" -n 30 --no-pager >&2 || true
        exit 1
    fi
}

befehl="${1:-hilfe}"
case "$befehl" in
    start)
        pruefe_umgebung
        [ $# -ge 2 ] || fehler "Branch fehlt. Beispiel: $0 start monatsbericht"
        einrichten kopie "$(branch_name "$2")"
        ;;
    demo)
        pruefe_umgebung
        einrichten demo "$(branch_name "${2:-main}")"
        ;;
    neu)
        pruefe_umgebung
        [ -s "$MERKDATEI" ] || fehler "Noch kein Branch gemerkt. Zuerst: $0 start <branch> oder $0 demo"
        einrichten "$(gemerkte_art)" "$(gemerkter_branch)"
        ;;
    stop)
        pruefe_umgebung
        freigabe_aus
        "$PYTHON" -m kontor.testinstanz stoppen
        echo "==> Testinstanz angehalten. Die Daten bleiben erhalten."
        ;;
    loeschen)
        pruefe_umgebung
        freigabe_aus
        "$PYTHON" -m kontor.testinstanz stoppen --loeschen
        echo "==> Testinstanz angehalten, Daten geloescht."
        ;;
    status)
        if systemctl is-active --quiet "$DIENST"; then
            echo "Zustand: laeuft"
            echo "Adresse: $(adresse)"
        else
            echo "Zustand: angehalten"
        fi
        if [ -s "$MERKDATEI" ]; then
            echo "Branch:  $(gemerkter_branch) (zuletzt mit diesem Skript eingerichtet)"
            if [ "$(gemerkte_art)" = "demo" ]; then
                echo "Daten:   Demodaten (erfundener Haushalt), ohne Anmeldung"
            else
                echo "Daten:   Kopie der Hauptinstanz"
            fi
        fi
        ;;
    log)
        exec journalctl -u "$DIENST" -n 50 -f
        ;;
    hilfe|-h|--help)
        hilfe
        ;;
    *)
        hilfe >&2
        exit 2
        ;;
esac
