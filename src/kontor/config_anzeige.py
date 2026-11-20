"""Konfiguration einer Instanz zum Nachsehen (D-235): gesetzte Umgebungsvariablen und geltende Werte.

Nur lesend. Geheimnisse stehen nach den Regeln des Projekts nicht in der Umgebung; trotzdem gibt diese Anzeige nie
den Wert einer Variable oder Einstellung aus, deren Name nach einem Geheimnis klingt.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
import re
from collections.abc import Mapping

from .config import KontorConfig

# Geheimnisse und Zugangskennungen der Bank (Benutzerkennung, Kunden-ID): nie ausgeben, nur „gesetzt“
_GEHEIM = re.compile(r"(?i)secret|token(?!_url)|passwor|password|(?:^|_)pin(?:$|_(?!quelle))|apikey|api_key"
                     r"|credential(?!s_(?:dir|verzeichnis))|fints_benutzer|fints_kunden_id")
# Einstellungen, deren Variable nicht KONTOR_<NAME> heißt
_VARIABLE = {"credentials_verzeichnis": "CREDENTIALS_DIRECTORY"}
_ZUSATZ = ("CREDENTIALS_DIRECTORY",)


def _geheim(name: str) -> bool:
    return _GEHEIM.search(name) is not None


def _json(wert):
    """Wert einer Einstellung für die Antwort: Wahrheitswert und Zahl bleiben, alles andere als Text."""
    if wert is None or isinstance(wert, (bool, int)):
        return wert
    if isinstance(wert, (pathlib.Path, dt.date)):
        return str(wert)
    if isinstance(wert, (list, tuple, set, frozenset)):
        return ", ".join(str(x) for x in wert)
    return str(wert)


def variable(name: str) -> str:
    return _VARIABLE.get(name, "KONTOR_" + name.upper())


def anzeige(config: KontorConfig, umgebung: Mapping[str, str]) -> dict:
    felder = dataclasses.fields(config)
    bekannt = {variable(f.name) for f in felder}
    gesetzt = sorted(n for n in umgebung if n.startswith("KONTOR_") or n in _ZUSATZ)
    wirksam = []
    for f in felder:
        wert = getattr(config, f.name)
        if f.default is not dataclasses.MISSING:
            vorgabe = f.default
        elif f.default_factory is not dataclasses.MISSING:
            vorgabe = f.default_factory()
        else:
            vorgabe = None
        verborgen = _geheim(f.name)
        wirksam.append({"name": f.name, "variable": variable(f.name), "gesetzt": variable(f.name) in umgebung,
                        "wert": ("verborgen" if wert not in (None, "") else None) if verborgen else _json(wert),
                        "vorgabe": None if verborgen else _json(vorgabe),
                        "geaendert": _json(wert) != _json(vorgabe), "verborgen": verborgen})
    return {
        "umgebung": [{"variable": n, "wert": None if _geheim(n) else umgebung[n], "verborgen": _geheim(n),
                      "bekannt": n in bekannt} for n in gesetzt],
        "wirksam": wirksam,
    }
