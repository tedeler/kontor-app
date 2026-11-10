"""Aktualisierung über GitHub-Releases (Feature `update`, D-107).

Zwei Teile mit getrennten Rechten:

- **Prüfdienst** (``UpdateDienst``) im Kontor-Prozess (Benutzer ``kontor``): fragt beim Start und danach alle
  ``update_intervall_stunden`` die GitHub-API nach dem neuesten Release und hält das Ergebnis im Arbeitsspeicher
  (Betriebszustand: nicht in Datenbank, Protokoll oder Sicherung). Auf Wunsch legt er im Verzeichnis
  ``update_verzeichnis`` einen Auftrag ``auftrag.json`` ab – mehr darf er nicht.
- **Update-Programm** (``python -m kontor.aktualisierung ausfuehren``), gestartet von der systemd-Unit
  ``kontor-update.service`` (root), sobald ``auftrag.json`` existiert (``kontor-update.path``). Es vertraut dem
  Auftrag nur die gewünschte Versionsnummer an, fragt die API selbst, lädt das Wheel, prüft dessen SHA-256 gegen
  den Digest der API, legt eine Datensicherung an (``kontor-sicherung.service``), installiert ins venv und
  startet Kontor neu. Das Ergebnis steht in ``ergebnis.json``.

Im Mock-Modus wird nie geprüft (keine Verbindung zu Fremdsystemen).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from . import version as versionsinfo
from .config import KontorConfig
from .netz import http_anfrage
from .validierung import ApiFehler

log = logging.getLogger("kontor.aktualisierung")

AUFTRAG = "auftrag.json"
LAEUFT = "laeuft.json"
ERGEBNIS = "ergebnis.json"
WHEEL = re.compile(r"^kontor-[0-9][0-9A-Za-z.]*-py3-none-any\.whl$")
SHA256 = re.compile(r"^sha256:([0-9a-f]{64})$")
ERSTE_PRUEFUNG_SEKUNDEN = 30
TIMEOUT_SEKUNDEN = 15


def _jetzt() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def neuer(a: str, b: str) -> bool:
    """True, wenn Version ``a`` neuer als ``b`` ist (beide ``MAJOR.MINOR``)."""
    return versionsinfo.zerlegen(a) > versionsinfo.zerlegen(b)


def release_auswerten(daten: Any) -> dict:
    """Antwort von ``GET /repos/{o}/{r}/releases/latest`` → ``{version, release_url, wheel_url, sha256}``.

    ``ValueError`` mit deutscher Meldung, wenn das Release nicht passt (Tag ``vMAJOR.MINOR``, genau ein Wheel mit
    SHA-256-Digest). Entwürfe und Vorabversionen zählen nicht.
    """
    if not isinstance(daten, dict):
        raise ValueError("Unerwartete Antwort von GitHub.")
    if daten.get("draft") or daten.get("prerelease"):
        raise ValueError("Das neueste Release ist ein Entwurf oder eine Vorabversion.")
    tag = daten.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("Das neueste Release hat keinen Tag der Form vMAJOR.MINOR.")
    try:
        version = versionsinfo.formatieren(*versionsinfo.zerlegen(tag[1:]))
    except ValueError:
        raise ValueError("Das neueste Release hat keinen Tag der Form vMAJOR.MINOR.") from None
    wheels = [a for a in daten.get("assets") or [] if isinstance(a, dict) and WHEEL.match(str(a.get("name", "")))]
    if len(wheels) != 1:
        raise ValueError(f"Release {version} enthält kein eindeutiges Wheel.")
    a = wheels[0]
    m = SHA256.match(str(a.get("digest") or ""))
    url = a.get("browser_download_url")
    if not m or not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"Release {version}: Wheel ohne Prüfsumme oder Download-Adresse.")
    release_url = daten.get("html_url") if isinstance(daten.get("html_url"), str) else None
    return {"version": version, "release_url": release_url, "wheel_url": url, "sha256": m.group(1)}


# ====================================================================== Prüfdienst (Kontor-Prozess)


class UpdateDienst:
    """Prüft auf neue Releases und nimmt Update-Aufträge an. Zustand nur im Arbeitsspeicher."""

    def __init__(self, config: KontorConfig, abrufen: Callable[[str], Any] | None = None) -> None:
        self.config = config
        self._abrufen = abrufen or self._api_abrufen
        self._sperre = threading.Lock()
        self._stand: dict[str, Any] = {"geprueft_um": None, "neueste_version": None, "release_url": None,
                                       "fehler": None}
        self._halt = threading.Event()
        self._thread: threading.Thread | None = None
        if self.verzeichnis is not None:
            with contextlib.suppress(OSError):
                self.verzeichnis.mkdir(parents=True, exist_ok=True)

    @property
    def verzeichnis(self) -> pathlib.Path | None:
        return None if self.config.mock_modus else self.config.update_verzeichnis

    @property
    def automatisch(self) -> bool:
        return self.config.update_pruefen and not self.config.mock_modus

    # ------------------------------------------------------------ Prüfen
    def _api_abrufen(self, url: str) -> Any:
        a = http_anfrage(self.config, "GET", url, None, {
            "Accept": "application/vnd.github+json", "User-Agent": f"Kontor/{versionsinfo.VERSION}",
            "X-GitHub-Api-Version": "2022-11-28"}, TIMEOUT_SEKUNDEN)
        if a.status == 404:
            raise ValueError("Es gibt noch kein veröffentlichtes Release.")
        if a.status != 200:
            raise ValueError(f"GitHub antwortete mit Status {a.status}.")
        try:
            return json.loads(a.koerper)
        except ValueError:
            raise ValueError("Unerwartete Antwort von GitHub.") from None

    def pruefen(self) -> dict:
        """Eine Prüfung jetzt; Fehler landen im Stand (nie die Antwort der Gegenstelle)."""
        if self.config.mock_modus:
            raise ApiFehler(409, "update_mock", "Im Mock-Modus wird nicht nach Aktualisierungen gesucht.")
        neu: dict[str, Any] = {"geprueft_um": _jetzt(), "neueste_version": None, "release_url": None, "fehler": None}
        try:
            r = release_auswerten(self._abrufen(self.config.update_url))
            neu.update(neueste_version=r["version"], release_url=r["release_url"])
        except ValueError as e:
            neu["fehler"] = str(e)
        except Exception as e:  # noqa: BLE001 – Netz-/TLS-/Protokollfehler jeder Art; nur die Art, nie Fremdtext
            neu["fehler"] = f"GitHub nicht erreichbar ({type(e).__name__})."
        if neu["fehler"]:
            log.warning("Suche nach Aktualisierungen fehlgeschlagen: %s", neu["fehler"])
        with self._sperre:
            self._stand = neu
        return self.status()

    # ------------------------------------------------------------ Status
    def _datei(self, name: str) -> pathlib.Path | None:
        return self.verzeichnis / name if self.verzeichnis is not None else None

    def laeuft(self) -> bool:
        return any(p is not None and p.exists() for p in (self._datei(AUFTRAG), self._datei(LAEUFT)))

    def letztes_ergebnis(self) -> dict | None:
        p = self._datei(ERGEBNIS)
        if p is None:
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(d, dict) or not isinstance(d.get("erfolg"), bool):
            return None
        return {"version": d.get("version") if isinstance(d.get("version"), str) else None,
                "erfolg": d["erfolg"],
                "meldung": d.get("meldung") if isinstance(d.get("meldung"), str) else "",
                "zeit": d.get("zeit") if isinstance(d.get("zeit"), str) else None}

    def status(self) -> dict:
        with self._sperre:
            s = dict(self._stand)
        aktuell = versionsinfo.VERSION
        verfuegbar = bool(s["neueste_version"]) and neuer(s["neueste_version"], aktuell)
        laeuft = self.laeuft()
        return {"version": aktuell, "automatisch": self.automatisch,
                "intervall_stunden": self.config.update_intervall_stunden,
                **s, "verfuegbar": verfuegbar, "eingerichtet": self.verzeichnis is not None, "laeuft": laeuft,
                "installierbar": verfuegbar and self.verzeichnis is not None and not laeuft,
                "letztes_ergebnis": self.letztes_ergebnis()}

    # ------------------------------------------------------------ Auftrag
    def installieren(self, version: str) -> dict:
        if self.config.mock_modus:
            raise ApiFehler(409, "update_mock", "Im Mock-Modus kann Kontor nicht aktualisiert werden.")
        if self.verzeichnis is None:
            raise ApiFehler(409, "update_nicht_eingerichtet",
                            "Der Update-Dienst ist nicht eingerichtet (KONTOR_UPDATE_VERZEICHNIS, kontor-update.path).")
        if self.laeuft():
            raise ApiFehler(409, "update_laeuft", "Eine Aktualisierung läuft bereits.")
        s = self.status()
        if not s["verfuegbar"] or s["neueste_version"] != version:
            raise ApiFehler(409, "update_nicht_verfuegbar",
                            f"Version {version} ist nicht die neueste verfügbare Version.")
        ziel = self.verzeichnis / AUFTRAG
        with tempfile.NamedTemporaryFile("w", dir=self.verzeichnis, prefix=".auftrag-", delete=False,
                                         encoding="utf-8") as f:
            json.dump({"version": version, "angefordert_um": _jetzt()}, f)
        os.chmod(f.name, 0o644)
        os.replace(f.name, ziel)
        log.info("Aktualisierung auf Version %s angefordert", version)
        return self.status()

    # ------------------------------------------------------------ Planer
    def starten(self) -> None:
        if not self.automatisch or self._thread is not None:
            return

        def schleife() -> None:
            warten = ERSTE_PRUEFUNG_SEKUNDEN
            while not self._halt.wait(warten):
                self.pruefen()
                warten = self.config.update_intervall_stunden * 3600

        self._thread = threading.Thread(target=schleife, name="kontor-update", daemon=True)
        self._thread.start()

    def beenden(self) -> None:
        self._halt.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


# ====================================================================== Update-Programm (root, systemd)


class UpdateFehler(Exception):
    pass


def _laden(url: str, timeout: float = 60) -> bytes:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise UpdateFehler("Nur HTTPS-Adressen sind erlaubt.")
    anfrage = urllib.request.Request(url, headers={"User-Agent": f"Kontor-Update/{versionsinfo.VERSION}",
                                                   "Accept": "application/octet-stream, application/json"})
    with urllib.request.urlopen(anfrage, timeout=timeout) as a:  # noqa: S310 – Schema oben geprüft
        return a.read()


def ausfuehren(verzeichnis: pathlib.Path, venv: pathlib.Path, api_url: str, *,
               laden: Callable[[str], bytes] = _laden,
               befehl: Callable[[list[str]], None] | None = None,
               installiert: str | None = None) -> dict:
    """Einen Auftrag abarbeiten. Gibt das Ergebnis zurück und schreibt es nach ``ergebnis.json``.

    Reihenfolge: Auftrag lesen und entfernen → Release über die API prüfen → Wheel laden, SHA-256 prüfen →
    Datensicherung → ``pip install`` → Ergebnis schreiben → Kontor neu starten.
    """
    def ausfuehren_befehl(args: list[str]) -> None:
        r = subprocess.run(args, capture_output=True, text=True, timeout=900, check=False)  # noqa: S603
        if r.returncode != 0:
            raise UpdateFehler(f"„{' '.join(args[:3])} …“ schlug fehl (Rückgabecode {r.returncode}).")

    befehl = befehl or ausfuehren_befehl
    installiert = installiert or versionsinfo.VERSION
    auftrag = verzeichnis / AUFTRAG
    laeuft = verzeichnis / LAEUFT
    version = None
    ergebnis: dict[str, Any]
    try:
        try:
            d = json.loads(auftrag.read_text(encoding="utf-8"))
            version = versionsinfo.formatieren(*versionsinfo.zerlegen(str(d.get("version", ""))))
        except (OSError, ValueError, AttributeError):
            raise UpdateFehler("Der Auftrag ist ungültig.") from None
        finally:
            with contextlib.suppress(OSError):
                auftrag.unlink()
        laeuft.write_text(json.dumps({"version": version, "seit": _jetzt()}), encoding="utf-8")
        os.chmod(laeuft, 0o644)
        if not neuer(version, installiert):
            raise UpdateFehler(f"Version {version} ist nicht neuer als die installierte {installiert}.")
        try:
            r = release_auswerten(json.loads(laden(api_url)))
        except ValueError as e:
            raise UpdateFehler(str(e)) from None
        if r["version"] != version:
            raise UpdateFehler(f"Das neueste Release ist {r['version']}, angefordert war {version}.")
        daten = laden(r["wheel_url"])
        if hashlib.sha256(daten).hexdigest() != r["sha256"]:
            raise UpdateFehler("Die Prüfsumme des heruntergeladenen Pakets stimmt nicht.")
        befehl(["systemctl", "start", "kontor-sicherung.service"])
        with tempfile.TemporaryDirectory(prefix="kontor-update-") as tmp:
            name = urllib.parse.urlsplit(r["wheel_url"]).path.rsplit("/", 1)[-1]
            if not WHEEL.match(name):
                raise UpdateFehler("Unerwarteter Dateiname des Pakets.")
            datei = pathlib.Path(tmp) / name
            datei.write_bytes(daten)
            befehl([str(venv / "bin" / "pip"), "install", "--no-input", "--disable-pip-version-check",
                    "--upgrade", str(datei)])
        ergebnis = {"version": version, "erfolg": True, "zeit": _jetzt(),
                    "meldung": f"Kontor wurde auf Version {version} aktualisiert."}
    except (UpdateFehler, OSError, subprocess.SubprocessError) as e:
        meldung = str(e) if isinstance(e, UpdateFehler) else f"Aktualisierung fehlgeschlagen ({type(e).__name__})."
        ergebnis = {"version": version, "erfolg": False, "zeit": _jetzt(), "meldung": meldung}
    with contextlib.suppress(OSError):
        ziel = verzeichnis / ERGEBNIS
        ziel.write_text(json.dumps(ergebnis, ensure_ascii=False), encoding="utf-8")
        os.chmod(ziel, 0o644)
    with contextlib.suppress(OSError):
        laeuft.unlink()
    if ergebnis["erfolg"]:
        with contextlib.suppress(UpdateFehler, OSError, subprocess.SubprocessError):
            befehl(["systemctl", "restart", "kontor.service"])
    return ergebnis


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m kontor.aktualisierung",
                                description="Kontor aus einem GitHub-Release aktualisieren (Update-Dienst).")
    sub = p.add_subparsers(dest="befehl", required=True)
    a = sub.add_parser("ausfuehren", help="Auftrag im Verzeichnis abarbeiten (von kontor-update.service)")
    a.add_argument("--verzeichnis", type=pathlib.Path, required=True)
    a.add_argument("--venv", type=pathlib.Path, required=True)
    args = p.parse_args(argv)
    if not (args.verzeichnis / AUFTRAG).exists():
        print("Kein Auftrag vorhanden.", file=sys.stderr)
        return 0
    url = (os.environ.get("KONTOR_UPDATE_URL") or "").strip() or KontorConfig.__dataclass_fields__["update_url"].default
    erg = ausfuehren(args.verzeichnis, args.venv, url)
    print(erg["meldung"], file=sys.stderr)
    return 0 if erg["erfolg"] else 1


if __name__ == "__main__":
    sys.exit(main())
