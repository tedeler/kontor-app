"""Verzögerter Zugriff auf die Anwendung – nur über Namen aus python-api.md.

Testmodule importieren ``kontor`` nie auf Modulebene, damit Generator- und
Spezifikationstests auch ohne installierte Anwendung laufen und App-Tests mit
einer klaren Meldung fehlschlagen (siehe tests/app/conftest.py).
"""

from __future__ import annotations

import importlib
import os
from types import ModuleType

MELDUNG_FEHLT = (
    "Die Anwendung (Python-Paket 'kontor') ist nicht installiert oder nicht importierbar.\n"
    "Installation: pip install -e <pfad-zu-kontor-app>  (siehe TESTS_AUSFUEHREN.md).\n"
    "Nur Generator-/Spezifikationstests: pytest tests/generator tests/spec  "
    "oder App-Tests überspringen: pytest --ohne-app (bzw. KONTOR_TESTS_OHNE_APP=1)"
)


def ohne_app(config) -> bool:
    """True, wenn App-Tests bei fehlender Anwendung übersprungen werden sollen."""
    wert = os.environ.get("KONTOR_TESTS_OHNE_APP", "").strip().lower()
    return bool(config.getoption("--ohne-app")) or wert in ("1", "true", "ja", "yes", "on")


def modul(name: str) -> ModuleType:
    return importlib.import_module(name)


def app_importfehler() -> BaseException | None:
    try:
        importlib.import_module("kontor")
    except Exception as e:  # noqa: BLE001
        return e
    return None


def KontorConfig():  # noqa: N802 - spiegelt den Klassennamen
    return modul("kontor.config").KontorConfig


def create_app(config):
    return modul("kontor.app").create_app(config)


def importiere_kmy(config, quelle, **kw):
    return modul("kontor.importer.kmymoney").importiere_kmy(config, quelle, **kw)


def fehler() -> ModuleType:
    return modul("kontor.fehler")


def plugins() -> ModuleType:
    return modul("kontor.plugins")
