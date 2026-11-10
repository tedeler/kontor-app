"""Versionsnummer und Build-Angaben (Feature Versionierung, D-105).

Die Versionsnummer steht in der Paketdatei ``VERSION`` im Schema ``MAJOR.MINOR`` mit mindestens zweistelligem
Minor (``0.07``, ``1.00``). Sie gibt die zuletzt veröffentlichte bzw. die gerade gebaute Version an; hochgezählt
wird sie nur von der Release-CI (``.github/workflows/release.yml``).

Die optionale Paketdatei ``build.json`` schreibt die Release-CI beim Bauen (Commit, Build-Datum). Fehlt sie, läuft
ein Entwicklungsstand aus dem Quellbaum.
"""

from __future__ import annotations

import json
import platform
import re
from importlib import resources
from typing import Any

NAME = "Kontor"
REPOSITORY = "https://github.com/tedeler/kontor-app"
MUSTER = re.compile(r"^(0|[1-9][0-9]*)\.([0-9]{2,})$")


def _paketdatei(name: str) -> str | None:
    try:
        return resources.files("kontor").joinpath(name).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def zerlegen(text: str) -> tuple[int, int]:
    """``"0.07"`` → ``(0, 7)``; ValueError bei anderem Format."""
    m = MUSTER.match(text.strip())
    if not m:
        raise ValueError("Versionsnummer muss die Form MAJOR.MINOR haben (z. B. 0.07)")
    return int(m.group(1)), int(m.group(2))


def formatieren(major: int, minor: int) -> str:
    return f"{major}.{minor:02d}"


def naechste(text: str, major: bool = False) -> str:
    """Nächste Version: Minor + 1, mit ``major=True`` Major + 1 und Minor 00."""
    ma, mi = zerlegen(text)
    return formatieren(ma + 1, 0) if major else formatieren(ma, mi + 1)


def _lesen() -> str:
    text = (_paketdatei("VERSION") or "0.00").strip()
    zerlegen(text)  # Formatfehler sofort beim Import zeigen
    return text


VERSION = _lesen()


def build() -> dict[str, Any]:
    """Build-Angaben aus ``build.json``; ohne Datei ein Entwicklungsstand."""
    roh = _paketdatei("build.json")
    try:
        daten = json.loads(roh) if roh else {}
    except ValueError:
        daten = {}
    if not isinstance(daten, dict):
        daten = {}
    commit = daten.get("commit") if isinstance(daten.get("commit"), str) else None
    datum = daten.get("build_datum") if isinstance(daten.get("build_datum"), str) else None
    return {"commit": commit[:12] if commit else None, "build_datum": datum, "entwicklungsstand": roh is None}


def info() -> dict[str, Any]:
    """Angaben ohne Laufzeitbezug (Name, Version, Build, Python, Repository)."""
    return {"name": NAME, "version": VERSION, **build(), "python": platform.python_version(),
            "repository": REPOSITORY}

