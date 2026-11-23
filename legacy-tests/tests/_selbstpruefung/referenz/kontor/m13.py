"""WEGWERF-REFERENZ M13: GET /api/version – kein Anwendungscode, kein Vorbild für die Implementierung."""

from __future__ import annotations

import platform
from pathlib import Path

from fastapi import FastAPI

from . import __version__, mutant
from .sicherung import SCHEMAVERSION

REPOSITORY = "https://example.invalid/kontor-referenz"


def m13_einbinden(app: FastAPI, config, modus: str) -> None:
    pfad = Path(config.aktive_datenbank)
    datenbank = str(pfad if mutant("m13_datenbank_relativ") else pfad.resolve())

    @app.get("/api/version")
    def version():
        d = {"name": "Kontor", "version": __version__, "commit": None, "build_datum": None,
             "entwicklungsstand": not mutant("m13_entwicklungsstand_falsch"), "python": platform.python_version(),
             "repository": REPOSITORY, "modus": modus, "datenbank": datenbank, "datenbank_schema": 1,
             "sicherung_schema": SCHEMAVERSION}
        if mutant("m13_feld_fehlt"):
            del d["sicherung_schema"]
        return d
