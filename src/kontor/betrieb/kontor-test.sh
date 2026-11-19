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
#   kontor-test neu                dasselbe mit dem zuletzt benutzten Branch
#   kontor-test stop               Testinstanz anhalten (Datenkopie bleibt)
#   kontor-test loeschen           anhalten und Datenkopie loeschen
#   kontor-test status             Zustand, Branch und Adresse anzeigen
#   kontor-test log                Protokoll mitlesen (Strg+C beendet)
#
# <branch>: "feature/monatsbericht", kurz "monatsbericht", oder "main".

set -euo pipefail

PYTHON="${KONTOR_PYTHON:-/opt/kontor/venv/bin/python}"
DIENST="kontor-test.service"
ENV_DATEI="${KONTOR_TEST_ENV:-/etc/kontor/kontor-test.env}"
MERKDATEI="${KONTOR_TEST_MERKDATEI:-/root/.kontor-test-branch}"
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

adresse() {
    local ip
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo "http://${ip:-<container-ip>}:$(port)"
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

einrichten() {
    local branch="$1"
    echo "==> Richte Testinstanz ein: ${branch}"
    echo "    (Branch holen, installieren, Daten kopieren, starten)"
    "$PYTHON" -m kontor.testinstanz einrichten "$branch"
    echo "$branch" > "$MERKDATEI"

    echo "==> Warte auf Port $(port) ..."
    if warte_auf_port; then
        echo "==> Testinstanz laeuft: $(adresse)"
        echo "    Anmeldung mit dem Haushaltspasswort."
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
        einrichten "$(branch_name "$2")"
        ;;
    neu)
        pruefe_umgebung
        [ -s "$MERKDATEI" ] || fehler "Noch kein Branch gemerkt. Zuerst: $0 start <branch>"
        einrichten "$(cat "$MERKDATEI")"
        ;;
    stop)
        pruefe_umgebung
        "$PYTHON" -m kontor.testinstanz stoppen
        echo "==> Testinstanz angehalten. Die Datenkopie bleibt erhalten."
        ;;
    loeschen)
        pruefe_umgebung
        "$PYTHON" -m kontor.testinstanz stoppen --loeschen
        echo "==> Testinstanz angehalten, Datenkopie geloescht."
        ;;
    status)
        if systemctl is-active --quiet "$DIENST"; then
            echo "Zustand: laeuft"
            echo "Adresse: $(adresse)"
        else
            echo "Zustand: angehalten"
        fi
        if [ -s "$MERKDATEI" ]; then
            echo "Branch:  $(cat "$MERKDATEI") (zuletzt mit diesem Skript eingerichtet)"
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
