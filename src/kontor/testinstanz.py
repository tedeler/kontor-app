"""Testinstanz für Entwicklungsbranches (D-205).

Eine zweite, getrennte Kontor-Instanz auf demselben Server: eigenes Programmverzeichnis mit dem Quellbaum eines
Branches, eigenes Datenverzeichnis mit einer Kopie der Datenbank, eigener Port, Mock-Modus. Die Hauptinstanz wird
dabei nur gelesen (konsistente Kopie über die Online-Sicherung von SQLite) und sonst nicht berührt.

Aufruf als root mit dem Python der Hauptinstanz::

    /opt/kontor/venv/bin/python -m kontor.testinstanz einrichten feature/<kurzname>
    /opt/kontor/venv/bin/python -m kontor.testinstanz demo [<branch>]
    /opt/kontor/venv/bin/python -m kontor.testinstanz stoppen [--loeschen]

``demo`` (Feature demodaten) füllt die Testinstanz statt mit einer Kopie mit einem erfundenen Haushalt zum
Vorführen: Die Hauptinstanz wird dabei gar nicht gelesen, die Anmeldung ist ausgeschaltet.

Aus der Kopie werden alle Geheimnisse (Chiffretexte, verpackter Datenschlüssel), offene TAN-Anforderungen und der
gespeicherte Bankzugang entfernt, bevor die Testinstanz sie zu sehen bekommt.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources

from . import version as versionsinfo

DIENST = "kontor-test.service"
DATENBANK = "kontor-test.sqlite3"
DEMO_MOCKDATEN = "demo-mockdaten.json"
# Zusatz zur Umgebungsdatei, solange die Testinstanz Demodaten zeigt. Ein Drop-in der Unit lässt ihn nach der
# gewöhnlichen Umgebungsdatei lesen (spätere Angaben gelten); die ausgelieferte Unit bleibt unverändert.
DEMO_DROPIN = """# Kontor – Testinstanz mit Demodaten: Zusatz-Umgebungsdatei nach kontor-test.env lesen.
# Geschrieben von „python -m kontor.testinstanz demo“, entfernt von „… einrichten“.
[Service]
EnvironmentFile=-{env}
"""
DEMO_ENV = """# Kontor – Testinstanz mit Demodaten (erfundener Haushalt zum Vorführen).
# Geschrieben von „python -m kontor.testinstanz demo“, entfernt von „… einrichten“. Nicht von Hand ändern;
# eigene Einstellungen gehören in kontor-test.env.
# Ohne Anmeldung: Die Demodaten sind erfunden, jeder im erlaubten Netz darf sie sehen und ändern.
KONTOR_ANMELDUNG=0
# Bank und Postfächer der Mock-Plugins: die erfundene Welt, aus der die Demodaten gebaut sind
KONTOR_MOCK_DATEN={mockdaten}
# Erfundene Personen des Demo-Haushalts (demodaten.DEMO_BENUTZER)
KONTOR_BENUTZER=Anna,Ben
"""
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
# Tabellen, deren Inhalt die Testinstanz nie bekommt (nur falls in dieser Schemaversion vorhanden)
_LEEREN = ("geheimnis", "geheimnis_huelle", "tan_anforderung")
# Betriebszustand in ``meta``, der zum echten Bankzugang gehört
_META_ENTFERNEN = ("bank!_fints!_%", "bank!_diagnose")


class TestinstanzFehler(Exception):
    __test__ = False  # kein pytest-Testfall


@dataclass(frozen=True)
class Orte:
    """Pfade der Haupt- und der Testinstanz (in Tests auf ein temporäres Verzeichnis umgebogen)."""

    haupt_env: pathlib.Path = pathlib.Path("/etc/kontor/kontor.env")
    programm: pathlib.Path = pathlib.Path("/opt/kontor-test")
    daten: pathlib.Path = pathlib.Path("/var/lib/kontor-test")
    env: pathlib.Path = pathlib.Path("/etc/kontor/kontor-test.env")
    unit: pathlib.Path = pathlib.Path("/etc/systemd/system") / DIENST
    benutzer: str | None = "kontor"

    @property
    def quelle(self) -> pathlib.Path:
        return self.programm / "src"

    @property
    def venv(self) -> pathlib.Path:
        return self.programm / "venv"

    @property
    def datenbank(self) -> pathlib.Path:
        return self.daten / DATENBANK

    @property
    def demo_mockdaten(self) -> pathlib.Path:
        return self.daten / DEMO_MOCKDATEN

    @property
    def demo_env(self) -> pathlib.Path:
        return self.env.with_name(self.env.stem + "-demo" + self.env.suffix)

    @property
    def demo_dropin(self) -> pathlib.Path:
        return self.unit.with_name(self.unit.name + ".d") / "demo.conf"


Befehl = Callable[[list[str]], None]


def _ausfuehren(args: list[str]) -> None:
    umgebung = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    r = subprocess.run(args, capture_output=True, text=True, timeout=1800, check=False, env=umgebung)  # noqa: S603
    if r.returncode != 0:
        letzte = (r.stderr or "").strip().splitlines()[-1:] or [""]
        raise TestinstanzFehler(f"„{' '.join(args[:3])} …“ schlug fehl (Rückgabecode {r.returncode}). {letzte[0]}"
                                .strip())


def branch_pruefen(name: str) -> str:
    """Nur gewöhnliche Branchnamen; nichts, was Git oder die Shell als Option oder Pfad deuten könnte."""
    if not _BRANCH.match(name) or ".." in name or "//" in name or name.endswith(("/", ".", ".lock")):
        raise TestinstanzFehler(f"„{name}“ ist kein gültiger Branchname.")
    return name


def hauptdatenbank(haupt_env: pathlib.Path) -> pathlib.Path:
    """Pfad der Datenbank der Hauptinstanz aus deren Umgebungsdatei (``KONTOR_DATENBANK``)."""
    try:
        zeilen = haupt_env.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise TestinstanzFehler(f"Die Umgebungsdatei der Hauptinstanz ({haupt_env}) ist nicht lesbar.") from None
    for zeile in zeilen:
        schluessel, trenner, wert = zeile.strip().partition("=")
        if trenner and schluessel.strip() == "KONTOR_DATENBANK" and wert.strip():
            return pathlib.Path(wert.strip().strip("\"'"))
    raise TestinstanzFehler(f"In {haupt_env} steht kein KONTOR_DATENBANK.")


def bereinigen(con: sqlite3.Connection) -> None:
    """Geheimnisse, offene TAN-Anforderungen und den gespeicherten Bankzugang aus der Kopie entfernen."""
    vorhanden = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for tabelle in _LEEREN:
        if tabelle in vorhanden:
            con.execute(f"DELETE FROM {tabelle}")  # noqa: S608 – feste Tabellennamen aus _LEEREN
    if "meta" in vorhanden:
        for muster in _META_ENTFERNEN:
            con.execute("DELETE FROM meta WHERE schluessel LIKE ? ESCAPE '!'", (muster,))
    con.commit()


def _belegt(datenbank: pathlib.Path) -> int:
    """Bytes der Datenbank samt WAL (die Kopie enthält auch, was noch im WAL steht)."""
    return sum(d.stat().st_size for d in (datenbank, datenbank.with_name(datenbank.name + "-wal")) if d.exists())


def _mb(n: float) -> str:
    return f"{n / 1e6:.0f}"


def daten_kopieren(quelle: pathlib.Path, ziel: pathlib.Path) -> None:
    """Konsistente Kopie der laufenden Datenbank; die Quelle wird nur lesend geöffnet.

    D-256: Vor dem Kopieren wird der freie Platz geprüft (die alte Kopie zählt als frei) und die alte Kopie entfernt
    – die Testinstanz ist zu diesem Zeitpunkt gestoppt. Die Kopie entsteht neben dem Ziel und wird bereinigt; mit
    ``secure_delete`` werden gelöschte Geheimnisse überschrieben, freie Seiten fallen weg (``incremental_vacuum``,
    ohne ``auto_vacuum`` wie bisher ``VACUUM``, das vorübergehend noch einmal die Größe der Daten braucht).
    """
    if not quelle.is_file():
        raise TestinstanzFehler(f"Die Datenbank der Hauptinstanz ({quelle}) gibt es nicht.")
    if ziel.exists() and ziel.resolve() == quelle.resolve():
        raise TestinstanzFehler("Die Testinstanz darf nicht die Datenbank der Hauptinstanz benutzen.")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    neu = ziel.with_name(ziel.name + ".neu")
    _weg(neu)
    con_q = con_z = None
    try:
        con_q = sqlite3.connect(f"{quelle.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
        inkrementell = con_q.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        noetig = int(_belegt(quelle) * (1.1 if inkrementell else 2.1)) + 64 * 1024
        frei = shutil.disk_usage(ziel.parent).free + (_belegt(ziel) if ziel.exists() else 0)
        if frei < noetig:
            raise TestinstanzFehler(f"Zu wenig freier Platz für die Kopie der Datenbank in {ziel.parent}: frei "
                                    f"{_mb(frei)} MB (einschließlich der alten Kopie), nötig etwa {_mb(noetig)} MB.")
        _weg(ziel)   # Platz der alten Kopie freigeben, bevor die neue entsteht
        con_z = sqlite3.connect(neu, isolation_level=None)
        con_q.backup(con_z)
        # WAL der Quelle übernimmt die Kopie als Vorgabe; für das Ersetzen braucht es eine einzelne Datei
        con_z.execute("PRAGMA journal_mode = DELETE")
        con_z.execute("PRAGMA secure_delete = ON")
        bereinigen(con_z)
        if inkrementell:
            con_z.execute("PRAGMA incremental_vacuum").fetchall()
        else:
            con_z.execute("VACUUM")
    except sqlite3.Error as e:
        for c in (con_z, con_q):
            if c is not None:
                c.close()
        con_q = con_z = None
        _weg(neu)
        # SQLite-Meldungen nennen nur Ursachen (z. B. „database or disk is full“), keine Inhalte
        raise TestinstanzFehler(f"Die Datenbank ließ sich nicht kopieren ({type(e).__name__}: {e}).") from None
    finally:
        for c in (con_z, con_q):
            if c is not None:
                c.close()
    os.replace(neu, ziel)
    os.chmod(ziel, 0o600)


def _weg(datenbank: pathlib.Path) -> None:
    for datei in (datenbank, datenbank.with_name(datenbank.name + "-wal"),
                  datenbank.with_name(datenbank.name + "-shm"), datenbank.with_name(datenbank.name + "-journal")):
        with contextlib.suppress(FileNotFoundError):
            datei.unlink()


def _besitz(pfad: pathlib.Path, benutzer: str | None) -> None:
    if benutzer is not None:
        try:
            shutil.chown(pfad, user=benutzer, group=benutzer)
        except (LookupError, OSError):
            raise TestinstanzFehler(f"{pfad} ließ sich nicht dem Benutzer {benutzer} übergeben.") from None


def betriebsdateien(orte: Orte) -> None:
    """Unit immer aktualisieren, die Umgebungsdatei nur anlegen (eigene Anpassungen bleiben erhalten)."""
    b = resources.files("kontor.betrieb")
    orte.unit.parent.mkdir(parents=True, exist_ok=True)
    orte.unit.write_text(b.joinpath(DIENST).read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(orte.unit, 0o644)
    if not orte.env.exists():
        orte.env.parent.mkdir(parents=True, exist_ok=True)
        orte.env.write_text(b.joinpath("kontor-test.env").read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(orte.env, 0o640)
        if orte.benutzer is not None:
            with contextlib.suppress(LookupError, OSError):
                shutil.chown(orte.env, user="root", group=orte.benutzer)


def _demo_entfernen(orte: Orte) -> None:
    for datei in (orte.demo_dropin, orte.demo_env, orte.demo_mockdaten,
                  orte.demo_mockdaten.with_name(DEMO_MOCKDATEN + ".neu")):
        with contextlib.suppress(FileNotFoundError):
            datei.unlink()
    with contextlib.suppress(OSError):
        orte.demo_dropin.parent.rmdir()


def _programm_einrichten(branch: str, orte: Orte, befehl: Befehl, repository: str) -> None:
    """Branch in ein neues Verzeichnis klonen (scheitert das, bleibt eine laufende Testinstanz unberührt) →
    Testinstanz stoppen → Quellbaum ersetzen und in die eigene Umgebung installieren."""
    orte.programm.mkdir(parents=True, exist_ok=True)
    neu = orte.programm / "src.neu"
    shutil.rmtree(neu, ignore_errors=True)
    try:
        befehl(["git", "clone", "--quiet", "--depth", "1", "--single-branch", "--branch", branch, repository,
                str(neu)])
    except TestinstanzFehler:
        shutil.rmtree(neu, ignore_errors=True)
        raise
    # Einstellungen einer früheren Vorführung mit Demodaten zurücknehmen (wieder Anmeldung, eingebaute Mock-Bank);
    # ``demo`` schreibt sie nach dem Aufbau neu
    _demo_entfernen(orte)
    betriebsdateien(orte)
    befehl(["systemctl", "daemon-reload"])
    befehl(["systemctl", "stop", DIENST])
    shutil.rmtree(orte.quelle, ignore_errors=True)
    os.replace(neu, orte.quelle)
    if not (orte.venv / "bin" / "pip").exists():
        befehl([sys.executable, "-m", "venv", str(orte.venv)])
    # Editierbar installieren: so findet Kontor den Branch in .git/HEAD und zeigt ihn statt der Version (D-178)
    befehl([str(orte.venv / "bin" / "pip"), "install", "--no-input", "--disable-pip-version-check", "--editable",
            str(orte.quelle)])
    orte.daten.mkdir(parents=True, exist_ok=True)
    os.chmod(orte.daten, 0o700)


def einrichten(branch: str, orte: Orte | None = None, befehl: Befehl | None = None,
               repository: str = versionsinfo.REPOSITORY) -> str:
    """Branch holen, installieren, Daten kopieren und die Testinstanz starten. Gibt eine Meldung zurück.

    Reihenfolge: prüfen → Branch in ein neues Verzeichnis klonen (scheitert das, bleibt eine laufende Testinstanz
    unberührt) → Testinstanz stoppen → Quellbaum ersetzen und installieren → Datenkopie ersetzen → starten.
    """
    orte = orte or Orte()
    befehl = befehl or _ausfuehren
    branch_pruefen(branch)
    quelle_db = hauptdatenbank(orte.haupt_env)
    if not quelle_db.is_file():
        raise TestinstanzFehler(f"Die Datenbank der Hauptinstanz ({quelle_db}) gibt es nicht.")
    _programm_einrichten(branch, orte, befehl, repository)
    daten_kopieren(quelle_db, orte.datenbank)
    _besitz(orte.daten, orte.benutzer)
    _besitz(orte.datenbank, orte.benutzer)
    befehl(["systemctl", "start", DIENST])
    return (f"Die Testinstanz läuft mit dem Branch {branch} und einer Kopie der Daten (Mock-Modus). "
            f"Port und Einstellungen: {orte.env}.")


def demo(branch: str = "main", orte: Orte | None = None, befehl: Befehl | None = None,
         repository: str = versionsinfo.REPOSITORY) -> str:
    """Branch holen, installieren, Demodaten aufbauen und die Testinstanz ohne Anmeldung starten.

    Die Hauptinstanz wird nicht gelesen: Die Daten baut der Generator des Branches (``python -m kontor.demodaten``
    in der Umgebung der Testinstanz) aus einer erfundenen Welt. Eine frühere Datenkopie wird vorher entfernt.
    """
    orte = orte or Orte()
    befehl = befehl or _ausfuehren
    branch_pruefen(branch)
    _programm_einrichten(branch, orte, befehl, repository)
    _weg(orte.datenbank)     # nie eine Kopie echter Daten liegen lassen, auch wenn der Aufbau scheitert
    _weg(orte.datenbank.with_name(orte.datenbank.name + ".neu"))
    befehl([str(orte.venv / "bin" / "python"), "-m", "kontor.demodaten", str(orte.datenbank),
            str(orte.demo_mockdaten)])
    orte.demo_env.parent.mkdir(parents=True, exist_ok=True)
    orte.demo_env.write_text(DEMO_ENV.format(mockdaten=orte.demo_mockdaten), encoding="utf-8")
    orte.demo_dropin.parent.mkdir(parents=True, exist_ok=True)
    orte.demo_dropin.write_text(DEMO_DROPIN.format(env=orte.demo_env), encoding="utf-8")
    for datei in (orte.demo_env, orte.demo_dropin):
        os.chmod(datei, 0o644)
    befehl(["systemctl", "daemon-reload"])
    _besitz(orte.daten, orte.benutzer)
    for datei in (orte.datenbank, orte.demo_mockdaten):
        if datei.exists():
            _besitz(datei, orte.benutzer)
    befehl(["systemctl", "start", DIENST])
    return (f"Die Testinstanz läuft mit dem Branch {branch} und Demodaten (erfundener Haushalt, Mock-Modus, ohne "
            f"Anmeldung). Port und Einstellungen: {orte.env}.")


def stoppen(orte: Orte | None = None, befehl: Befehl | None = None, loeschen: bool = False) -> str:
    """Testinstanz stoppen; mit ``loeschen`` auch die Datenkopie entfernen."""
    orte = orte or Orte()
    befehl = befehl or _ausfuehren
    befehl(["systemctl", "stop", DIENST])
    if not loeschen:
        return "Die Testinstanz ist gestoppt. Die Datenkopie bleibt bis zum nächsten Einrichten liegen."
    _weg(orte.datenbank)
    _weg(orte.datenbank.with_name(orte.datenbank.name + ".neu"))
    _demo_entfernen(orte)
    return "Die Testinstanz ist gestoppt, die Daten (Kopie oder Demodaten) sind gelöscht."


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m kontor.testinstanz",
                                description="Zweite Kontor-Instanz für einen Entwicklungsbranch (Mock-Modus, Kopie "
                                            "der Daten oder Demodaten). Die Hauptinstanz bleibt unberührt.")
    sub = p.add_subparsers(dest="aktion", required=True)
    e = sub.add_parser("einrichten", help="Branch installieren, Daten kopieren, Testinstanz starten")
    e.add_argument("branch", help="Branch im Repository, z. B. feature/kurzname")
    d = sub.add_parser("demo", help="Branch installieren, Demodaten aufbauen (erfundener Haushalt), ohne Anmeldung "
                                    "starten; die Hauptinstanz wird nicht gelesen")
    d.add_argument("branch", nargs="?", default="main", help="Branch im Repository (Vorgabe: main)")
    s = sub.add_parser("stoppen", help="Testinstanz stoppen")
    s.add_argument("--loeschen", action="store_true", help="auch die Datenkopie löschen")
    args = p.parse_args(argv)
    if os.geteuid() != 0:
        print("Bitte als root ausführen.", file=sys.stderr)
        return 2
    try:
        if args.aktion == "einrichten":
            meldung = einrichten(args.branch)
        elif args.aktion == "demo":
            meldung = demo(args.branch)
        else:
            meldung = stoppen(loeschen=args.loeschen)
    except (TestinstanzFehler, OSError, subprocess.SubprocessError) as fehler:
        text = str(fehler) if isinstance(fehler, TestinstanzFehler) else f"Fehlgeschlagen ({type(fehler).__name__})."
        print(text, file=sys.stderr)
        return 1
    print(meldung)
    return 0


if __name__ == "__main__":
    sys.exit(main())
